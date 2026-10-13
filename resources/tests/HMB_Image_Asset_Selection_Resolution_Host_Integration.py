"""Offline native SDK dispatch/heartbeat and immediate downstream Run regression."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    from griptape_nodes.retained_mode.engine import current_engine
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, SetParameterValueRequest
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
except ImportError:
    print("ImageAsset selection native SDK: SKIP (SDK unavailable)")
    raise SystemExit(0)

import HMBImageAssetLibrary as asset
from HMB_Image_Asset_Selection_Resolution_Async_Regression import selected_state


class ImageSink(asset.DataNode):
    def __init__(self, name):
        super().__init__(name=name)
        self.observed = []
        asset._safe_add_parameter(self, name="images", type="list[str]", default_value=[],
                                 input_types=["list[str]"], allowed_modes=asset._mode_set("INPUT"))

    def process(self):
        self.observed.append(self.get_parameter_value("images"))


def register(flow, node):
    flow.add_node(node)
    GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name


async def main():
    GriptapeNodes.EventManager().initialize_queue()
    flow = ControlFlow(name="ImageAssetSelectionOfflineFlow", engine=current_engine())
    GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)
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

    def manifest(_path):
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
        return {}

    async def wait_until(predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
        assert predicate(), "Native fixture completion timed out"

    with patch.object(asset, "_read_asset_manifest", manifest), \
         patch.object(asset, "_verified_project_relative_path", lambda row, *_: row["relative_path"]), \
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


asyncio.run(main())
print("ImageAsset selection native SDK dispatch/heartbeat/immediate Run: PASS")
