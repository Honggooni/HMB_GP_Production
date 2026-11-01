"""Actual retained SDK async Apply, latest-intent, failure and pending-save fences."""
from __future__ import annotations
import asyncio
import base64
from copy import deepcopy
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
STANDARD = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
EDITOR = Path.home() / "AppData/Local/ai.griptape.nodes.desktop/current/resources/editor-bundle"
OUT = Path(os.environ.get("HMB_BASH_APPLY_WORKER_REPORT_DIR",str(ROOT/"reports/regression-checks/HMB_Image_Bash_Apply_Worker_Host_Regression")))
OUT.mkdir(parents=True, exist_ok=True)
RESULT = {}

def deny(*args, **kwargs): raise AssertionError("Provider/network is forbidden")

async def exercise(engine, directory, extension=None):
    import HMBImageBash as product
    from PIL import Image
    from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
    from griptape_nodes.exe_types.node_types import DataNode, NodeResolutionState
    from griptape_nodes.files.file import File
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest
    def png(color):
        buffer = BytesIO(); Image.new("RGBA", (4, 2), color).save(buffer, "PNG", compress_level=0); return buffer.getvalue()
    source_path = directory / "source.png"; source_path.write_bytes(png("red"))
    records = [{"source_uid": "synthetic-source", "url": str(source_path), "name": "Source"}]
    context = {"schema": product.CONTEXT_SCHEMA, "workspace_id": "worker-workspace", "revision": 1, "ready": True, "records": records}
    class Source(DataNode):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.add_parameter(Parameter(name="IMAGE_BASH_IMAGES_OUT", type="list[str]", output_type="list[str]", default_value=[], allowed_modes={ParameterMode.OUTPUT}))
            self.add_parameter(Parameter(name="IMAGE_BASH_CONTEXT_OUT", type="dict", output_type="dict", default_value={}, allowed_modes={ParameterMode.OUTPUT}))
        def process(self):
            for name in ("IMAGE_BASH_IMAGES_OUT", "IMAGE_BASH_CONTEXT_OUT"):
                self.parameter_output_values[name] = self.get_parameter_value(name)
        def _hmb_image_bash_catalog(self):
            value = self.get_parameter_value("IMAGE_BASH_CONTEXT_OUT")
            return {"schema": "hmb-image-bash-workspace-catalog-v1", "channel_uuid": "worker-channel",
                    "workspaces": ([{"workspace_id": value["workspace_id"], "name": "HMBImageBash", "revision": value["revision"], "count": len(value["records"])}] if value else [])}
    # Native serialization uses the actual class name; the fixture must keep
    # the registered production type name instead of serializing "Source".
    Source.__name__ = Source.__qualname__ = "HMBImageAssetLibrary"
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    for kind, cls in (("HMBImageBash", product.HMBImageBash), ("HMBImageAssetLibrary", Source)):
        metadata = next(row.metadata for row in schema.nodes if row.class_name == kind)
        library.register_lazy_node_type(kind, metadata, lambda cls=cls: cls)
    engine.event_manager.initialize_queue()
    def send(request):
        request.broadcast_result = False; result = engine.handle_request(request)
        assert result.succeeded(), str(result.result_details); return result
    ensured = send(EnsureWorkflowAndFlowRequest(flow_name="BashWorkerActualSDK"))
    def create(kind, name):
        result = send(CreateNodeRequest(node_type=kind, node_name=name, specific_library_name=schema.name,
            override_parent_flow_name=ensured.flow_name, initial_setup=True, create_error_proxy_on_failure=False))
        return engine.node_manager.get_node_by_name(result.node_name)
    node, source = create("HMBImageBash", "WorkerBash"), create("HMBImageAssetLibrary", "WorkerSource")
    node.metadata.update(hmb_image_bash_workspace_id=context["workspace_id"], hmb_image_bash_channel_uuid="worker-channel")
    for src, dst in (("IMAGE_BASH_IMAGES_OUT", "input_images"), ("IMAGE_BASH_CONTEXT_OUT", "image_bash_context")):
        send(CreateConnectionRequest(source_node_name=source.name, source_parameter_name=src,
            target_node_name=node.name, target_parameter_name=dst, initial_setup=True))
    def set_value(name, value, target=None, initial=False):
        # This fake producer mirrors the consumer notifications the real
        # ImageAsset publisher sends after updating its own workspace catalog.
        if name == "image_bash_context" and target is None:
            source.set_parameter_value("IMAGE_BASH_CONTEXT_OUT", deepcopy(value))
        return send(SetParameterValueRequest(node_name=(target or node).name, parameter_name=name, value=value, initial_setup=initial))
    set_value("IMAGE_BASH_IMAGES_OUT", [str(source_path)], target=source)
    set_value("IMAGE_BASH_CONTEXT_OUT", context, target=source)
    for key, value in (("canvas_size", "custom"), ("width", 4), ("height", 2), ("output_file", str(directory / "output.png"))): set_value(key, value)
    children = list(node.get_parameter_by_name("input_images").get_child_parameters())
    child = children[0] if children else node.get_parameter_by_name("input_images").append_child_parameter()
    set_value(child.name, {"value": str(source_path), "type": "ImageUrlArtifact"})
    set_value("image_bash_context", context)
    async def settled():
        await asyncio.sleep(.005)  # Include original sync-fallback host completion tick.
        for _ in range(300):
            if node._hmb_apply_pending is None and node._hmb_prepare_pending is None and not node._hmb_apply_work["active"]: return
            await asyncio.sleep(.01)
        raise AssertionError("Async Apply did not settle")
    def candidate(commit, color="green"):
        value = deepcopy(node.get_parameter_value("bash_image"))
        value["value"] = "data:image/png;base64," + base64.b64encode(png(color)).decode()
        value["meta"]["created_at"] = commit
        return value
    try:
        await settled()
        if extension is not None:
            await extension(engine, node, source, set_value, candidate, png, directory, context, records, settled, send)
            return
        set_value("bash_image", candidate("first")); await settled()
        assert node.parameter_output_values.get("output_image"), node.get_parameter_value("HMB_BASH_STATUS")
        # A deliberate native Resolve must drain its pending Apply even when
        # resolving its real upstream node re-publishes identical inputs.
        real_calculate = product.HMBImageBash._calculate_apply
        run_entered, run_release = threading.Event(), threading.Event()
        echo_preserved = []
        def run_blocked(task, live):
            run_entered.set(); assert run_release.wait(3)
            return real_calculate(task, live)
        def same_input_upstream():
            pending = node._hmb_apply_pending
            set_value("image_bash_context", context)
            echo_preserved.append(node._hmb_apply_pending is pending and pending is not None)
            for name in ("IMAGE_BASH_IMAGES_OUT", "IMAGE_BASH_CONTEXT_OUT"):
                source.parameter_output_values[name] = source.get_parameter_value(name)
        with mock.patch.object(product.HMBImageBash, "_calculate_apply", side_effect=run_blocked), \
             mock.patch.object(source, "process", side_effect=same_input_upstream):
            set_value("bash_image", candidate("pending-native-run", "green"))
            assert run_entered.wait(1)
            source.state = NodeResolutionState.UNRESOLVED
            timer = threading.Timer(.05, run_release.set); timer.daemon = True; timer.start()
            try:
                resolved = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(node_name=node.name, broadcast_result=False)), 5)
            finally:
                run_release.set(); timer.join(1)
            assert resolved.succeeded(), str(getattr(resolved, "validation_exceptions", resolved.result_details))
            await settled()
        assert echo_preserved and all(echo_preserved)
        assert node.get_parameter_value("bash_image")["meta"]["hmb_image_bash"]["apply"]["editor_commit"] == "pending-native-run"
        RESULT["blocked_worker_native_resolve_identical_upstream_echo_preserves_apply"] = True
        # A genuinely new revision cancels that same blocked Apply, retains
        # its authored draft and never writes its unverified PNG.
        before_cancel_bytes = (directory / "output.png").read_bytes()
        run_entered.clear(); run_release.clear()
        with mock.patch.object(product.HMBImageBash, "_calculate_apply", side_effect=run_blocked):
            set_value("bash_image", candidate("cancel-by-real-revision", "blue"))
            assert run_entered.wait(1)
            old_task = node._hmb_apply_pending
            set_value("image_bash_context", {**context, "revision": 2})
            assert node._hmb_apply_pending is None and node._hmb_prepare_pending is not None
            run_release.set(); await settled()
        assert node.get_parameter_value("bash_image")["meta"]["created_at"] == "cancel-by-real-revision"
        assert node.get_parameter_value("bash_image")["meta"]["hmb_image_bash"]["apply"]["editor_commit"] == "pending-native-run"
        assert (directory / "output.png").read_bytes() == before_cancel_bytes
        set_value("image_bash_context", context); await settled()
        set_value("bash_image", candidate("restored-after-revision", "green")); await settled()
        RESULT["actual_revision_change_cancels_blocked_apply_without_output_or_scene_loss"] = True
        original_document = deepcopy(node.get_parameter_value("bash_image"))
        original_output = node.parameter_output_values["output_image"]
        original_png = File(original_output.value).read_bytes()
        entered, release = threading.Event(), threading.Event()
        calculate = product.HMBImageBash._calculate_apply
        host_thread = threading.get_ident(); worker_threads = []; active = 0; peak = 0; guard = threading.Lock()
        def blocked(task, live):
            nonlocal active, peak
            with guard: active += 1; peak = max(peak, active)
            worker_threads.append(threading.get_ident()); entered.set()
            try:
                assert release.wait(3), "Synthetic read gate timed out"
                return calculate(task, live)
            finally:
                with guard: active -= 1
        with mock.patch.object(product.HMBImageBash, "_calculate_apply", side_effect=blocked):
            draft = candidate("pending-save", "blue")
            draft["meta"]["konva_json"]["lines"].append({"points": [0, 0, 1, 1], "stroke": "red", "strokeWidth": 1})
            start = time.perf_counter_ns(); set_value("bash_image", draft); queued_ns = time.perf_counter_ns() - start
            assert entered.wait(1)
            assert node.parameter_output_values["output_image"] == original_output
            assert node.get_parameter_value("bash_image")["meta"]["hmb_image_bash"]["apply"] == original_document["meta"]["hmb_image_bash"]["apply"]
            assert "검증 중" in node.get_parameter_value("HMB_BASH_STATUS")
            pulses = 0
            for _ in range(5): await asyncio.sleep(.002); pulses += 1
            commands = send(SerializeFlowToCommandsRequest(flow_name=ensured.flow_name, include_create_flow_command=True))
            saved = await engine.ahandle_request(SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=commands.serialized_flow_commands,
                file_name="saved-pending", file_path=str(directory / "saved-pending.py"), display_name="Pending draft", broadcast_result=False))
            assert saved.succeeded(), str(saved.result_details)
            saved_draft = deepcopy(node.get_parameter_value("bash_image"))
            # New saves inherit the old pending marker from the native editor.
            for index in range(10): set_value("bash_image", candidate("newer-" + str(index), "yellow"))
            latest = deepcopy(node.get_parameter_value("bash_image"))
            latest["meta"]["viewport"] = {"x": 77, "y": 23, "scale": 2}
            set_value("bash_image", latest, initial=True)
            release.set(); await settled()
        assert peak == 1 and all(thread != host_thread for thread in worker_threads)
        assert node.get_parameter_value("bash_image")["meta"]["hmb_image_bash"]["apply"]["editor_commit"] == "newer-9"
        assert node.get_parameter_value("bash_image")["meta"]["viewport"] == latest["meta"]["viewport"]
        assert File(node.parameter_output_values["output_image"].value).read_bytes() == png("yellow")
        RESULT.update(queued_handler_ns=queued_ns, host_pulses_while_worker_blocked=pulses, worker_peak=peak,
                      latest_intent=True, inherited_pending_marker=True, viewport_preserved=True, real_retained_handler=True)
        before = deepcopy(node.get_parameter_value("bash_image")); output = node.parameter_output_values["output_image"]
        invalid = candidate("invalid-png"); invalid["value"] = "data:image/png;base64," + base64.b64encode(b"not png").decode()
        set_value("bash_image", invalid); await settled()
        failed = node.get_parameter_value("bash_image")
        assert failed["value"] == invalid["value"]
        assert failed["meta"]["konva_json"] == invalid["meta"]["konva_json"]
        assert failed["meta"]["hmb_image_bash"]["apply"] == before["meta"]["hmb_image_bash"]["apply"]
        assert failed["meta"]["hmb_image_bash"]["pending_apply"]["phase"] == "error"
        assert node.parameter_output_values["output_image"] == output
        assert "실패" in node.get_parameter_value("HMB_BASH_STATUS")
        RESULT["invalid_png_preserves_draft_and_previous_receipt_output"] = True
        finish = product.HMBImageBash._finish_apply; captured = []
        with mock.patch.object(product.HMBImageBash, "_finish_apply", side_effect=lambda *args, **kwargs: captured.append((args, kwargs)), autospec=True):
            set_value("bash_image", candidate("changed-after-worker"))
            for _ in range(100):
                if captured: break
                await asyncio.sleep(.01)
        assert captured
        stat = source_path.stat(); source_path.write_bytes(png("blue")); os.utime(source_path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        args, kwargs = captured[0]; finish(*args, **kwargs)
        failed = node.get_parameter_value("bash_image")
        assert failed["meta"]["created_at"] == "changed-after-worker"
        assert failed["meta"]["hmb_image_bash"]["apply"] == before["meta"]["hmb_image_bash"]["apply"]
        assert node.parameter_output_values["output_image"] == output
        source_path.write_bytes(png("red"))
        RESULT["changed_bytes_after_worker_before_commit_rejected"] = True
        # The separate real ImageAsset/native integration fixture owns fresh
        # process pending/failed-draft replay. The fake Source cold-UID failure
        # is retained in worker-host-first..fourth logs, never counted as PASS.
        RESULT["fake_source_cold_replay_replaced_by_real_imageasset_fixture"] = True
        node._sync_metadata_with_input_images(); await settled()
        original_scene = deepcopy(node.get_parameter_value("bash_image"))
        # A new source is prepared in the shared worker without rebuilding the
        # old scene or reading File through SDK from its background thread.
        second_path = directory / "second.png"; second_path.write_bytes(png("purple"))
        records2 = records + [{"source_uid": "second-source", "url": str(second_path), "name": "Second"}]
        set_value("IMAGE_BASH_IMAGES_OUT", [row["url"] for row in records2], target=source, initial=True)
        parent = node.get_parameter_by_name("input_images")
        children = list(parent.get_child_parameters())
        second = parent.append_child_parameter() if len(children) < 2 else children[1]
        set_value(second.name, {"value": str(second_path), "type": "ImageUrlArtifact"})
        set_value("input_images", [row["url"] for row in records2])
        context2 = {**context, "revision": 2, "records": records2}
        entered, release = threading.Event(), threading.Event()
        calculate_prepare = product.HMBImageBash._calculate_prepare
        prepare_threads = []; prepare_peak = 0; prepare_active = 0
        def blocked_prepare(task, live):
            nonlocal prepare_peak, prepare_active
            with guard: prepare_active += 1; prepare_peak = max(prepare_peak, prepare_active)
            prepare_threads.append(threading.get_ident()); entered.set()
            try:
                assert release.wait(3)
                return calculate_prepare(task, live)
            finally:
                with guard: prepare_active -= 1
        original_file_read = File.read_bytes
        def checked_file_read(instance, *args, **kwargs):
            assert threading.get_ident() == host_thread, "Worker called SDK File.read_bytes"
            return original_file_read(instance, *args, **kwargs)
        with mock.patch.object(product.HMBImageBash, "_calculate_prepare", side_effect=blocked_prepare), \
             mock.patch.object(File, "read_bytes", checked_file_read):
            start = time.perf_counter_ns(); set_value("image_bash_context", context2); prepare_queued_ns = time.perf_counter_ns() - start
            assert entered.wait(1), (node.get_parameter_value("HMB_BASH_STATUS"), node.get_parameter_value("input_images"), node.get_parameter_value("image_bash_context"), node._hmb_apply_work)
            during = deepcopy(node.get_parameter_value("bash_image"))
            assert during["meta"]["konva_json"] == original_scene["meta"]["konva_json"]
            assert during["value"] == original_scene["value"]
            assert node._hmb_prepare_phase == "preparing"
            for _ in range(5): await asyncio.sleep(.002)
            for revision in range(3, 13):
                context2 = {**context2, "revision": revision}
                set_value("image_bash_context", context2)
            current = deepcopy(node.get_parameter_value("bash_image"))
            current["meta"].pop("viewport", None); current.pop("id", None); current.pop("reference", None)
            node._set_project(current)  # host viewport bookkeeping, no Apply intent
            release.set(); await settled()
        prepared = deepcopy(node.get_parameter_value("bash_image"))
        assert node._hmb_prepare_phase == "ready", node.get_parameter_value("HMB_BASH_STATUS")
        assert {r["source_uid"] for r in prepared["meta"]["input_images"]} == {r["source_uid"] for r in records2}
        assert "viewport" not in prepared["meta"] and "id" not in prepared and "reference" not in prepared
        assert prepare_peak == 1 and all(t != host_thread for t in prepare_threads)
        assert prepared["meta"]["hmb_image_bash"]["workspace_revision"] == 12
        RESULT.update(prepare_handler_ns=prepare_queued_ns, prepare_worker_peak=prepare_peak,
            prepare_host_pulses=5, prepare_latest_intent=True, prepare_preserves_scene_until_ready=True,
            worker_sdk_file_calls=0, viewport_envelope_removal_preserved=True)
        # Native uploaded PNG paths also use pure snapshot reads off-host.
        local_png = directory / "native-uploaded.png"; local_png.write_bytes(png("orange"))
        uploaded = candidate("local-native-PNG"); uploaded["value"] = str(local_png)
        with mock.patch.object(File, "read_bytes", checked_file_read):
            set_value("bash_image", uploaded); await settled()
        assert File(node.parameter_output_values["output_image"].value).read_bytes() == png("orange")
        RESULT["uploaded_local_png_worker_sdk_file_calls"] = 0
        # Unsupported external transports retain SDK policy and the original
        # synchronous path; a mocked response avoids any network operation.
        original_read = product._read_bytes; remote_reads = []
        def allowed_remote(url):
            if url == "https://offline-fixture.invalid/render.png":
                remote_reads.append(url); return png("pink")
            return original_read(url)
        remote = candidate("remote-PNG-fallback"); remote["value"] = "https://offline-fixture.invalid/render.png"
        with mock.patch.object(product, "_read_bytes", side_effect=allowed_remote), \
             mock.patch.object(product.HMBImageBash, "_calculate_apply", side_effect=AssertionError("Remote policy was bypassed by snapshot")):
            set_value("bash_image", remote); await settled()
        assert remote_reads == [remote["value"]]
        assert File(node.parameter_output_values["output_image"].value).read_bytes() == png("pink")
        RESULT["remote_sdk_policy_synchronous_fallback_preserved"] = True
        # A captured prepare completion cannot outrank a disconnected lease.
        captured_prepare = []; finish_prepare = product.HMBImageBash._finish_prepare
        with mock.patch.object(product.HMBImageBash, "_finish_prepare", side_effect=lambda *a, **k: captured_prepare.append((a, k)), autospec=True):
            set_value("image_bash_context", {**context2, "revision": 13})
            for _ in range(200):
                if captured_prepare: break
                await asyncio.sleep(.005)
        assert captured_prepare
        before_stale = deepcopy(node.get_parameter_value("bash_image"))
        send(DeleteConnectionRequest(source_node_name=source.name, source_parameter_name="IMAGE_BASH_CONTEXT_OUT",
            target_node_name=node.name, target_parameter_name="image_bash_context"))
        args, kwargs = captured_prepare[0]; finish_prepare(*args, **kwargs)
        assert node._hmb_prepare_pending is None
        assert node._hmb_prepare_phase != "preparing", node.get_parameter_value("HMB_BASH_STATUS")
        assert node.get_parameter_value("bash_image") == before_stale
        send(CreateConnectionRequest(source_node_name=source.name, source_parameter_name="IMAGE_BASH_CONTEXT_OUT",
            target_node_name=node.name, target_parameter_name="image_bash_context", initial_setup=True))
        set_value("image_bash_context", {**context2, "revision": 14}); await settled()
        latest_before_failure = deepcopy(node.get_parameter_value("bash_image"))
        invalid = candidate("latest-invalid-png"); invalid["value"] = "data:image/png;base64," + base64.b64encode(b"invalid").decode()
        set_value("bash_image", invalid); await settled()
        failed = node.get_parameter_value("bash_image")
        assert failed["meta"]["konva_json"] == latest_before_failure["meta"]["konva_json"]
        assert {r["source_uid"] for r in failed["meta"]["input_images"]} == {r["source_uid"] for r in records2}
        assert node._hmb_prepare_phase == "ready"  # bad output never blocks draft editor recovery
        assert failed["meta"]["hmb_image_bash"]["pending_apply"]["phase"] == "error"
        RESULT.update(stale_prepare_lease_rejected=True, stale_prepare_actionable_not_forever_pending=True,
            next_apply_failure_preserves_latest_sources_scene=True, failed_output_keeps_input_ready=True)
        RESULT["status"] = "PASS"
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)

if __name__ == "__main__":
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="bash-worker-host-", dir=OUT) as folder:
        directory = Path(folder)
        env = {key: str(directory / key) for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        for value in env.values(): Path(value).mkdir()
        env.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(STANDARD), HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(EDITOR))
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", side_effect=deny):
            os.chdir(directory); logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine: asyncio.run(exercise(engine, directory))
            finally:
                os.chdir(previous); logging.shutdown()
    (OUT / "WORKER-HOST-RESULT.json").write_text(json.dumps(RESULT, indent=2), encoding="utf-8")
    print(json.dumps(RESULT))
