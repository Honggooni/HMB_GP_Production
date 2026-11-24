"""Offline native SDK dispatch/heartbeat and immediate downstream Run regression."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, os.environ.get("HMB_IMAGE_ASSET_TEST_ROOT", str(ROOT)))
# The SDK binds its config paths on import. Keep the developer's Desktop
# settings and catalog out of both the native dispatch and the wired journey.
_profile = tempfile.TemporaryDirectory(prefix="hmb-imageasset-execution-")
_base = Path(_profile.name)
os.environ.update(XDG_CONFIG_HOME=str(_base / "config"), XDG_DATA_HOME=str(_base / "data"),
                  LOCALAPPDATA=str(_base / "local"), APPDATA=str(_base / "app"),
                  GTN_CONFIG_WORKSPACE_DIRECTORY=str(_base), HMB_IMAGE_PROJECTS_ROOT=str(_base / "projects"))
try:
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    from griptape_nodes.retained_mode.engine import current_engine, engine_scope
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, SetParameterValueRequest
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
except ImportError:
    print("ImageAsset selection native SDK: SKIP (SDK unavailable)")
    raise SystemExit(0)

import HMBImageAssetLibrary as asset
from HMB_Image_Asset_Selection_Resolution_Async_Regression import fixture_manifest, selected_state


class ImageSink(asset.DataNode):
    def __init__(self, name):
        super().__init__(name=name)
        self.observed = []
        asset._safe_add_parameter(self, name="images", type="list[str]", default_value=[],
                                 input_types=["list[str]"], allowed_modes=asset._mode_set("INPUT"))

    def process(self):
        self.observed.append(self.get_parameter_value("images"))


def register(flow, node):
    from _hmb_fixture_sdk import register_fixture_node
    register_fixture_node(GriptapeNodes, flow, node)


async def check_wired_image_with_existing_shot(workspace):
    """Resolve the SDK's dynamic image slot and an already-selected project image together."""
    from griptape_nodes.retained_mode.engine import NO_WORKFLOW
    from PIL import Image
    from _hmb_fixture_sdk import ensure_fixture_flow
    import HMBPromptLibrary as prompt
    import HMBSeedanceGeneration as seedance
    from base64 import b64decode
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema

    standard = Path(os.environ.get("HMB_STANDARD_LIBRARY_ROOT",
                                   Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
    sys.path.insert(0, str(standard))
    from griptape_nodes_library.image.load_image import LoadImage

    current_engine().event_manager.initialize_queue()
    flow = ensure_fixture_flow(GriptapeNodes, "WiredImageExistingShot")
    schema = LibrarySchema.model_validate_json((Path(asset.__file__).parent / "griptape-nodes-library.json").read_bytes())
    registered = LibraryRegistry.generate_new_library(schema)
    standard_schema = LibrarySchema.model_validate_json((standard / "griptape_nodes_library.json").read_bytes())
    standard_library = LibraryRegistry.generate_new_library(standard_schema)
    load_entry = next(item for item in standard_schema.nodes if item.class_name == "LoadImage")
    standard_library.register_lazy_node_type("LoadImage", load_entry.metadata, lambda: LoadImage)
    for cls in (asset.HMBImageAssetLibrary, seedance.HMBSeedanceGeneration):
        entry = next(item for item in schema.nodes if item.class_name == cls.__name__)
        registered.register_lazy_node_type(entry.class_name, entry.metadata, lambda cls=cls: cls)

    with patch.dict(os.environ, HMB_IMAGE_THUMBNAIL_CACHE=str(workspace / "thumbnails")):
        path = workspace / "inputs/images/Dingo.jpg"
        path.parent.mkdir(parents=True)
        Image.new("RGB", (32, 24), "orange").save(path)
        catalog = workspace / "projects"
        project = catalog / "superwings12" / "Ai_Ct_image"
        (project / ".json").mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(project / "Anchor.png")
        (project / ".json/hmb_image_assets.json").write_text(json.dumps({"assets": [{
            "path": "Anchor.png", "asset_id": "Anchor", "image_name": "Anchor",
            "image_main_type": "Custom / Context", "image_sub_type": "Context",
        }]}), encoding="utf-8")
        image = LoadImage(name="Dingo")
        image.metadata.update(library=standard_schema.name, node_type="LoadImage")
        register(flow, image)
        image.set_parameter_value("path", str(path))
        with patch.object(asset, "DEFAULT_PROJECTS_ROOT", catalog):
            library = asset.HMBImageAssetLibrary(name="HMB ImageAsset Library")
            library.metadata.update(library=schema.name, node_type="HMBImageAssetLibrary")
            register(flow, library)
            library._hmb_initial_catalog_scan_pending = False
            library._hmb_hydration_adopted = True
            state = asset._load_project_catalog(catalog, {})
            if not state["project_root"]:
                state = asset._select_catalog_project(state, state["projects"][0]["path"])
            anchor = next(row for row in state["assets"] if row["registered"])
            anchor.update(selected=True, selection_order=1)
            state["shot_routing"]["shots"][0]["selected_source_uids"] = [anchor["source_uid"]]
            library._sync_output(state, force=True)
            library._publish_state(state)
            slot = await GriptapeNodes.ahandle_request(AddParameterToNodeRequest(
                node_name=library.name, parent_container_name=asset.IMAGE_IMPORT_PARAMETER))
            assert not slot.failed(), slot
            connection = await GriptapeNodes.ahandle_request(CreateConnectionRequest(
                source_node_name=image.name, source_parameter_name="image",
                target_node_name=library.name, target_parameter_name=slot.parameter_name))
            assert not connection.failed(), connection
            shot_id = state["shot_routing"]["active_shot_uuid"]
            checked_state_reads = []
            original_prepare = library._execution_preparation_identity

            def record_widget_read():
                checked_state_reads.append((library.get_parameter_value(asset.WIDGET_STATE_PARAMETER),
                                            library.parameter_values[asset.WIDGET_STATE_PARAMETER]))
                return original_prepare()

            for attempt in (1, 2):
                if attempt == 2:
                    # Saved nodes can restore the old Parameter declaration.
                    library.get_parameter_by_name(asset.WIDGET_STATE_PARAMETER).allow_variable_substitution = True
                with patch.object(library, "_execution_preparation_identity", record_widget_read):
                    result = await GriptapeNodes.ahandle_request(ResolveNodeRequest(node_name=library.name))
                assert not result.failed(), (attempt, str(result.result_details))
                assert image.parameter_output_values.get("image"), (image.state, image.get_parameter_value("result_details"))
                assert image.parameter_output_values["image"].value == "{inputs}/images/Dingo.jpg"
                assert checked_state_reads
                for sdk_value, stored_json in checked_state_reads:
                    assert sdk_value == stored_json, "Workflow variables changed an opaque JSON document during Resolve"
                    assert json.loads(sdk_value)["shot_routing"]["active_shot_uuid"] == shot_id
                    assert "{inputs}/images/Dingo.jpg" in stored_json
                checked_state_reads.clear()
                updated = library._current_state()
                imports = [row for row in updated["assets"] if row["source_kind"] == "user"]
                assert len(imports) == 1 and imports[0]["image_name"] == "Dingo", imports
                media = library._hmb_import_media_by_uid[imports[0]["source_uid"]]
                assert getattr(media, "value", None) == "{inputs}/images/Dingo.jpg", media
                assert asset._local_import_source(imports[0], media).samefile(path)
                assert updated["shot_routing"]["active_shot_uuid"] == shot_id
                assert anchor["source_uid"] in updated["shot_routing"]["shots"][0]["selected_source_uids"]
                assert any(row["source_uid"] == anchor["source_uid"] and row["selected"] for row in updated["assets"])
                output = library.parameter_output_values[asset.MEDIA_OUTPUT_PARAMETER]
                assert anchor["path"] in output
                output_reference = getattr(output[1], "value", output[1])
                assert asset._resolve_import_file_reference(output_reference).samefile(path)

            # A peer can publish an acknowledgement while the node is still
            # verifying the same images off-thread. Only the cursor advances.
            entered = threading.Event()
            release = threading.Event()
            prepare = library._prepare_execution_files

            def paused_prepare(*args):
                entered.set()
                assert release.wait(4), "Timed out waiting for peer publication"
                return prepare(*args)

            with patch.object(library, "_prepare_execution_files", paused_prepare):
                pending = asyncio.create_task(GriptapeNodes.ahandle_request(ResolveNodeRequest(node_name=library.name)))
                try:
                    assert await asyncio.to_thread(entered.wait, 3)
                    live = library._current_state()
                    newer = dict(library._cache_shot_routing_snapshot(live, normalized=True))
                    newer["generation"] = live["shot_routing"]["generation"] + 1
                    library._persist_shot_routing_facts(live, newer)
                    assert library._current_state()["shot_routing"]["generation"] == newer["generation"]
                finally:
                    release.set()
                result = await pending
            assert not result.failed(), str(result.result_details)
            assert library._current_state()["shot_routing"]["generation"] >= newer["generation"]
            run = library.aprocess

            async def run_without_ambient_workflow():
                with current_engine().bind_workflow(NO_WORKFLOW):
                    await run()

            with patch.object(library, "aprocess", run_without_ambient_workflow):
                result = await GriptapeNodes.ahandle_request(ResolveNodeRequest(node_name=library.name))
            assert not result.failed(), str(result.result_details)
            assert library._current_state()["shot_routing"]["active_shot_uuid"] == shot_id
            downstream = prompt.HMBPromptLibrary(name="HMBPrompt")
            register(flow, downstream)
            wire = await GriptapeNodes.ahandle_request(CreateConnectionRequest(
                source_node_name=library.name, source_parameter_name=asset.OUTPUT_PARAMETER,
                target_node_name=downstream.name, target_parameter_name=prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME))
            assert wire.succeeded(), wire.result_details
            result = await GriptapeNodes.ahandle_request(ResolveNodeRequest(node_name=downstream.name))
            assert result.succeeded(), str(result.result_details)
            received = downstream.get_parameter_value(prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME)
            received = json.loads(received) if isinstance(received, str) else received
            assert [(row["order_key"], row["selection_order"]) for row in received["ordered_images"]] == [
                (anchor["source_uid"], 1), (imports[0]["source_uid"], 2),
            ], received["ordered_images"]
            generator = seedance.HMBSeedanceGeneration(name="Wired Shot Generator")
            generator.metadata.update(library=schema.name, node_type="HMBSeedanceGeneration")
            register(flow, generator)
            shot = library._current_state()["shot_routing"]
            for name, value in (("shot_channel_uuid", shot["channel_uuid"]), ("shot_uuid", shot_id),
                                ("shot_number", 1), ("shot_name", "Shot 1")):
                generator.set_parameter_value(name, value, initial_setup=True)
            wire = await GriptapeNodes.ahandle_request(CreateConnectionRequest(
                source_node_name=library.name, source_parameter_name="SHOT_ASSET_OUT",
                target_node_name=generator.name, target_parameter_name="SHOT_ASSET_IN", initial_setup=True))
            assert wire.succeeded(), wire.result_details
            params = generator._resolve_exact_shot_generation_inputs({**generator._get_parameters(), "model_id": seedance.SEEDANCE_2_5_MODEL_ID,
                "duration": 4, "resolution": "480p", "prompt": "Use @image1 and @image2"})
            prepared, _ = generator._prepare_image_references_for_run(params, cloud_driver=None)
            payload = generator._build_broker_payload(prepared)
            decoded = [b64decode(uri.split(",", 1)[1], validate=True) for uri in payload["image_urls"]]
            assert decoded == [(project / "Anchor.png").read_bytes(), path.read_bytes()]
            # Verify the retained widget's browser resource, not just the original file used by Prompt.
            from urllib.parse import unquote, urlsplit
            uid = imports[0]["source_uid"]
            async with asyncio.timeout(5):
                while True:
                    value = library.get_parameter_value(asset.WIDGET_STATE_PARAMETER)
                    visible = json.loads(value) if isinstance(value, str) else value
                    row = next(item for item in visible["assets"] if item["source_uid"] == uid)
                    if row.get("thumbnail_url"):
                        break
                    await asyncio.sleep(.02)
            assert row["media_ref_kind"] == "artifact" and row["path"] == "{inputs}/images/Dingo.jpg"
            assert row["selected"] and row["selection_order"] == 2
            preview_url = urlsplit(row["thumbnail_url"])
            assert preview_url.scheme in {"http", "https"}
            name = Path(unquote(preview_url.path)).name
            if "/staticfiles/" in preview_url.path:
                generated = workspace / "staticfiles" / name
            else:
                assert preview_url.hostname in {"localhost", "127.0.0.1", "::1"}
                assert re.fullmatch(r"[0-9a-f]{64}\.(?:png|webp)", name)
                generated = Path(asset._ASSET_THUMBNAIL_CACHE_ROOT) / name
                driver = GriptapeNodes.StaticFilesManager().storage_driver
                assert preview_url == urlsplit(driver.create_signed_download_url(generated))
            with Image.open(generated) as preview:
                assert preview.size == (32, 24)
                red, green, blue = preview.convert("RGB").getpixel((16, 12))
                assert red > 220 and green > 100 and blue < 50
            await current_engine().aclose_workflow(library.workflow)
            assert not library._scan_owner_is_current(), "Closed workflow still owns pending execution"
    print("Standard LoadImage -> ImageAsset -> HMBPrompt: macro JPEG, first/repeat Resolve, legacy declaration, "
          "preserved Shot and image order, peer publication, unbound callback, retired workflow PASS")


async def main():
    GriptapeNodes.EventManager().initialize_queue()
    flow = ControlFlow(name="ImageAssetSelectionOfflineFlow", engine=current_engine())

    from _hmb_fixture_sdk import ensure_fixture_flow
    flow = ensure_fixture_flow(GriptapeNodes, flow.name)
    source = asset.HMBImageAssetLibrary(name="ImageAssetSelectionOfflineSource")
    sink = ImageSink("ImageAssetSelectionOfflineSink")
    register(flow, source)
    register(flow, sink)
    source._hmb_initial_catalog_scan_pending = False
    source._hmb_hydration_adopted = True
    old = selected_state("old")
    old["catalog_root"] = str(asset.DEFAULT_PROJECTS_ROOT).replace("\\", "/")
    entered = threading.Event()
    release = threading.Event()
    read_threads = []
    preparation_threads = []
    publication_threads = []
    main_thread = threading.get_ident()
    force_mode = {"block": False}
    force_entered = threading.Event()
    force_release = threading.Event()
    force_finished = threading.Event()
    original_prepare = source._prepare_execution_files
    original_publish = asset._stage_and_notify_image_output_pair

    def prepare(*args):
        preparation_threads.append(threading.get_ident())
        try:
            return original_prepare(*args)
        finally:
            force_finished.set()

    source._prepare_execution_files = prepare

    def publish(*args, **kwargs):
        publication_threads.append(threading.get_ident())
        return original_publish(*args, **kwargs)

    def manifest(path):
        read_threads.append(threading.current_thread().name)
        if threading.current_thread().name == "HMBImageAssetSelection":
            entered.set()
            assert release.wait(4), "Native fixture worker was not released"
        elif threading.get_ident() != main_thread:
            force_entered.set()
            if force_mode["block"]:
                assert force_release.wait(4), "Force verification fixture was not released"
            else:
                time.sleep(0.25)
        return fixture_manifest(path)

    async def wait_until(predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
        assert predicate(), "Native fixture completion timed out"

    with patch.object(asset, "_read_asset_manifest", manifest), \
         patch.object(asset, "_verified_project_relative_path",
                      lambda row, state, records: row["relative_path"] if row["relative_path"].casefold() in records else ""), \
         patch.object(asset, "_state_catalog_is_current", return_value=True), \
         patch.object(asset, "_state_project_belongs_to_catalog", return_value=True), \
         patch.object(asset, "_stage_and_notify_image_output_pair", publish):
        source._sync_output(old, force=True)
        source._publish_state(old)
        result = await GriptapeNodes.ahandle_request(CreateConnectionRequest(
            source_node_name=source.name, source_parameter_name=asset.MEDIA_OUTPUT_PARAMETER,
            target_node_name=sink.name, target_parameter_name="images",
        ))
        assert not result.failed(), result
        source.state = NodeResolutionState.RESOLVED
        sink.state = NodeResolutionState.RESOLVED
        new = selected_state("new")
        new["catalog_root"] = old["catalog_root"]
        new[asset.WIDGET_RUNTIME_LEASE_KEY] = source._hmb_widget_runtime_lease
        new[asset.UI_EDIT_REVISION_KEY] = old[asset.UI_EDIT_REVISION_KEY] + 1
        heartbeat = asyncio.Event()
        asyncio.get_running_loop().call_later(0.01, heartbeat.set)
        started = time.perf_counter()
        result = await GriptapeNodes.ahandle_request(SetParameterValueRequest(
            node_name=source.name, parameter_name=asset.WIDGET_STATE_PARAMETER,
            value=json.dumps(new), data_type="str",
        ))
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert not result.failed(), result
        await wait_until(entered.is_set)
        await asyncio.wait_for(heartbeat.wait(), timeout=0.2)
        assert not release.is_set()
        assert elapsed_ms < 150, elapsed_ms
        assert source.state != NodeResolutionState.RESOLVED, source.state
        assert sink.state != NodeResolutionState.RESOLVED, sink.state
        assert source.parameter_output_values[asset.MEDIA_OUTPUT_PARAMETER] == [old["assets"][0]["path"]]
        reads_before_catalog = len(read_threads)
        assert source._hmb_shot_routing_catalog()["shots"]
        assert len(read_threads) == reads_before_catalog
        try:
            source._hmb_shot_routing_snapshot(cached_only=True)
        except ValueError as exc:
            assert "still preparing" in str(exc)
        else:
            raise AssertionError("Pending selection reused old Shot readiness")
        run_heartbeat = asyncio.Event()
        run_heartbeat_ms = []
        def tick():
            run_heartbeat_ms.append((time.perf_counter() - run_started) * 1000)
            run_heartbeat.set()
        run_request = asyncio.create_task(GriptapeNodes.ahandle_request(ResolveNodeRequest(node_name=sink.name)))
        await wait_until(force_entered.is_set)
        assert not force_finished.is_set()
        run_started = time.perf_counter()
        asyncio.get_running_loop().call_later(0.01, tick)
        await asyncio.wait_for(run_heartbeat.wait(), timeout=0.15)
        assert not force_finished.is_set()
        assert run_heartbeat_ms[0] < 150, run_heartbeat_ms
        result = await run_request
        assert not result.failed(), result
        await wait_until(lambda: bool(sink.observed))
        assert preparation_threads, "Immediate downstream Run skipped changed ImageAsset source"
        assert all(tid != main_thread for tid in preparation_threads)
        assert all(tid == main_thread for tid in publication_threads)
        assert sink.observed[-1] == [new["assets"][0]["path"]], sink.observed
        release.set()
        await asyncio.sleep(0.05)
        assert source.parameter_output_values[asset.MEDIA_OUTPUT_PARAMETER] == [new["assets"][0]["path"]]

        # Cancellation retires the awaiting execution only. The isolated file
        # worker can finish later, but has no node reference or publication API.
        force_mode["block"] = True
        force_entered.clear()
        force_finished.clear()
        before_cancel = deepcopy(dict(source.parameter_output_values))
        cancelled = asyncio.create_task(source.aprocess())
        await wait_until(force_entered.is_set)
        cancelled.cancel()
        try:
            await cancelled
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Execution task did not cancel")
        force_release.set()
        await wait_until(force_finished.is_set)
        await asyncio.sleep(0.02)
        assert dict(source.parameter_output_values) == before_cancel

        # A newer project/selection owns the UI while old verification runs.
        force_release.clear()
        force_entered.clear()
        force_finished.clear()
        changed = asyncio.create_task(source.aprocess())
        await wait_until(force_entered.is_set)
        latest = selected_state("latest", "ProjectB")
        latest["catalog_root"] = old["catalog_root"]
        latest[asset.WIDGET_RUNTIME_LEASE_KEY] = source._hmb_widget_runtime_lease
        latest[asset.UI_EDIT_REVISION_KEY] = new[asset.UI_EDIT_REVISION_KEY] + 1
        result = await GriptapeNodes.ahandle_request(SetParameterValueRequest(
            node_name=source.name, parameter_name=asset.WIDGET_STATE_PARAMETER,
            value=json.dumps(latest), data_type="str",
        ))
        assert not result.failed(), result
        await wait_until(lambda: source.parameter_output_values[asset.MEDIA_OUTPUT_PARAMETER] == [latest["assets"][0]["path"]])
        after_project_change = deepcopy(dict(source.parameter_output_values))
        force_release.set()
        try:
            await changed
        except ValueError as exc:
            assert "changed" in str(exc)
        else:
            raise AssertionError("Old execution accepted a changed project")
        assert dict(source.parameter_output_values) == after_project_change

        # A pending project scan cannot report successful execution with the
        # previous pair; a thumbnail-only busy flag must still publish freshly.
        force_mode["block"] = False
        source_state = source._current_state()
        source_state["scan_busy"] = True
        source._publish_state(source_state)
        before_busy = deepcopy(dict(source.parameter_output_values))
        try:
            await source.aprocess()
        except ValueError as exc:
            assert getattr(exc, "hmb_image_asset_selection_preparing", False)
        else:
            raise AssertionError("Pending project scan allowed old outputs to execute")
        assert dict(source.parameter_output_values) == before_busy
        source_state["scan_busy"] = False
        source_state["thumbnail_busy"] = True
        source._publish_state(source_state)
        source.parameter_output_values[asset.MEDIA_OUTPUT_PARAMETER] = ["obsolete-output"]
        await source.aprocess()
        assert source.parameter_output_values[asset.MEDIA_OUTPUT_PARAMETER] == [latest["assets"][0]["path"]]

        # Preserve process-time IMAGE_IMPORT_IN handling when an old host or
        # programmatic assignment did not dispatch its normal input callback.
        imported = "https://example.test/no-callback-import.png"
        imported_slot = await GriptapeNodes.ahandle_request(AddParameterToNodeRequest(
            node_name=source.name, parent_container_name=asset.IMAGE_IMPORT_PARAMETER,
        ))
        assert not imported_slot.failed(), imported_slot
        source.parameter_values[imported_slot.parameter_name] = imported
        assert imported in asset._flatten_import_values(asset._get_parameter_raw(source, asset.IMAGE_IMPORT_PARAMETER))
        assert all(row.get("path") != imported for row in source._current_state()["assets"])
        await source.aprocess()
        assert any(row.get("path") == imported for row in source._current_state()["assets"])
        assert any(value == imported for value in source._hmb_import_media_by_uid.values())
        print(json.dumps({"native_set_parameter_ms": round(elapsed_ms, 3),
                          "heartbeat_during_blocked_share": True,
                          "source_and_sink_invalidated": True,
                          "immediate_downstream_run_latest_media": True,
                          "run_heartbeat_during_250ms_manifest_ms": round(run_heartbeat_ms[0], 3),
                          "preparation_off_owner_loop": True,
                          "publication_on_owner_loop": True,
                          "cancelled_execution_cannot_publish": True,
                          "changed_project_execution_cannot_publish": True,
                          "pending_project_execution_rejected": True,
                          "thumbnail_busy_execution_fresh": True,
                          "initial_import_without_callback_preserved": True,
                          "selection_worker_reads": read_threads.count("HMBImageAssetSelection"),
                          "paid_calls": 0}))
    release.set()


from hmb_host_workflow import run_in_fixture_workflow


async def check_dispatch(_engine):
    await main()


async def check_wired(_engine, workspace):
    await check_wired_image_with_existing_shot(workspace)


with engine_scope() as engine:
    asyncio.run(run_in_fixture_workflow(engine, "ImageAssetSelectionOfflineFlow", check_dispatch))
with engine_scope() as engine:
    asyncio.run(run_in_fixture_workflow(engine, "WiredImageExistingShot", check_wired, _base))
print("ImageAsset selection native SDK dispatch/heartbeat/immediate Run: PASS")
