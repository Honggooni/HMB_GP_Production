"""Actual installed SDK raw Reset guard and approved refresh in a synthetic flow.

Only media probing and optional HMB routing are deferred. Native construction,
connections, locking, Reset refusal, refresh and Color LUT state stay real.
Two tiny local FFmpeg fixtures are preservation witnesses; no paid generation,
network, live application, user workflow or installed product is accessed.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
NETWORK_ATTEMPTS = 0


def no_network(*_args, **_kwargs):
    global NETWORK_ATTEMPTS
    NETWORK_ATTEMPTS += 1
    raise AssertionError("Native header reset/refresh must not access network/provider/Broker")


async def exercise(engine, folder: Path) -> dict:
    from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
    from griptape_nodes.exe_types.node_types import DataNode
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, ListConnectionsForNodeRequest
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import (
        CreateNodeRequest, ResetNodeToDefaultsRequest, SetLockNodeStateRequest,
    )
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    import HMBColorLUTLibrary as lut
    import _hmb_library_bootstrap as bootstrap
    import _hmb_connection_management as connection_api
    import _hmb_shot_routing as routing
    from _hmb_video_tools import _find_ffmpeg

    source_file = folder / "synthetic-source.mp4"
    completed_file = folder / "synthetic-completed.mp4"
    subprocess.run([_find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=32x32:r=12",
                    "-frames:v", "2", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source_file)],
                   check=True, timeout=20, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    completed_file.write_bytes(source_file.read_bytes())
    file_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source_file, completed_file)}
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(row for row in schema.nodes if row.class_name == "HMBColorLUTLibrary")
    library.register_lazy_node_type("HMBColorLUTLibrary", definition.metadata, lambda: lut.HMBColorLUTLibrary)
    engine.event_manager.initialize_queue()
    ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="SyntheticNativeHeaderReset"))
    assert ensured.succeeded(), ensured.result_details
    flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)

    def register(node):
        from _hmb_fixture_sdk import register_fixture_node
        register_fixture_node(engine, flow, node)

    source = DataNode(name="SyntheticNativeSource")
    source.add_parameter(Parameter(name="source", type="dict", output_type="dict", default_value={},
                                   allowed_modes={ParameterMode.OUTPUT}))
    register(source)
    sink = DataNode(name="SyntheticNativeSink")
    sink.add_parameter(Parameter(name="video", type="str", input_types=["str"], default_value="",
                                 allowed_modes={ParameterMode.INPUT}))
    register(sink)
    unrelated = DataNode(name="SyntheticUntouchedNode", metadata={"position": {"x": -20, "y": 45}})
    unrelated.add_parameter(Parameter(name="literal", type="str", default_value="Preserve this authored value"))
    register(unrelated)
    unrelated.set_parameter_value("literal", "User-authored other-node input")
    unrelated_before = (deepcopy(unrelated.metadata), deepcopy(dict(unrelated.parameter_values)), deepcopy(dict(unrelated.parameter_output_values)))
    source_snapshot = {"schema": "hmb-generated-video-source", "version": 1, "path": str(source_file),
                       "url": str(source_file), "completed": True, "generation_id": "synthetic-native-reset"}
    source.parameter_output_values["source"] = deepcopy(source_snapshot)

    # Only the preview worker and independent, deferred Shot discovery are out
    # of scope. All reset connection/lifecycle handlers run through the SDK.
    with ExitStack() as patches:
        patches.enter_context(mock.patch.object(lut, "_usage_bridge", side_effect=no_network))
        patches.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", return_value=None))
        patches.enter_context(mock.patch.object(bootstrap, "_hmb_coordinate_native_editor_update", return_value={"status": "unsupported"}))
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile",
                     "schedule_post_deletion_reconcile", "reconcile_shot_routing"):
            patches.enter_context(mock.patch.object(routing, name))
        queue_source = patches.enter_context(mock.patch.object(lut.HMBColorLUTLibrary, "_queue_source"))
        owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
        owner._registrations = set()
        owner.before_library_nodes_loaded(schema, library)
        created = engine.handle_request(CreateNodeRequest(node_type="HMBColorLUTLibrary", specific_library_name=schema.name,
            node_name="SyntheticNativeColorLUT", override_parent_flow_name=flow.name,
            create_error_proxy_on_failure=False))
        assert created.succeeded(), created.result_details
        old = engine.node_manager.get_node_by_name(created.node_name)
        old.metadata.update(position={"x": 123, "y": 456}, size={"width": 1370, "height": 1175},
                            synthetic_instance_note="Must not migrate into a fresh native Reset instance")
        state = lut.default_state()
        state.update(revision=31, preset_name="Authored grade", settings={**lut.default_settings(), "enabled": True, "exposure": 1.25},
                     source=deepcopy(source_snapshot), result={"path": str(completed_file), "url": str(completed_file)},
                     output={"codec": "ffv1", "manual_output_enabled": True, "path": str(completed_file)})
        authored = engine.handle_request(SetParameterValueRequest(node_name=old.name, parameter_name=lut.UI,
            value=deepcopy(state), initial_setup=True))
        assert authored.succeeded(), authored.result_details
        old.parameter_output_values["video_url"] = str(completed_file)
        for request in (CreateConnectionRequest(source_node_name=source.name, source_parameter_name="source",
                        target_node_name=old.name, target_parameter_name=lut.SOURCE),
                        CreateConnectionRequest(source_node_name=old.name, source_parameter_name="video_url",
                        target_node_name=sink.name, target_parameter_name="video")):
            result = engine.handle_request(request)
            assert result.succeeded(), result.result_details
        assert old._hmb_color_lut_state["settings"]["exposure"] == 1.25
        assert old._hmb_color_lut_state["source"]["path"] == str(source_file)
        before_metadata = deepcopy(old.metadata)
        before_state = deepcopy(old._hmb_color_lut_state)
        before_outputs = deepcopy(dict(old.parameter_output_values))
        reset = await engine.ahandle_request(ResetNodeToDefaultsRequest(node_name=old.name))
        assert reset.failed(), reset.result_details
        assert engine.node_manager.get_node_by_name(old.name) is old and not old._hmb_node_deleted
        assert old.metadata == before_metadata and old._hmb_color_lut_state == before_state
        assert dict(old.parameter_output_values) == before_outputs

        view = engine.handle_request(connection_api.HMBGetNodeConnectionsRequest(node_name=old.name))
        assert view.succeeded() and view.can_refresh, view.result_details
        refreshed = await engine.ahandle_request(connection_api.HMBManageNodeConnectionsRequest(
            node_name=old.name, operation="refresh", expected_state_token=view.state_token,
            broadcast_result=False))
        assert refreshed.succeeded(), refreshed.result_details
        assert engine.node_manager.get_node_by_name(old.name) is old and not old._hmb_node_deleted
        assert old.metadata == before_metadata and old._hmb_color_lut_state == before_state
        assert dict(old.parameter_output_values) == before_outputs
        connections = engine.handle_request(ListConnectionsForNodeRequest(node_name=old.name))
        assert connections.succeeded(), connections.result_details
        assert [(edge.source_node_name, edge.source_parameter_name, edge.target_parameter_name)
                for edge in connections.incoming_connections] == [(source.name, "source", lut.SOURCE)]
        assert [(edge.source_parameter_name, edge.target_node_name, edge.target_parameter_name)
                for edge in connections.outgoing_connections] == [("video_url", sink.name, "video")]
        assert source.parameter_output_values["source"] == source_snapshot
        assert engine.node_manager.get_node_by_name(unrelated.name) is unrelated
        assert (unrelated.metadata, dict(unrelated.parameter_values), dict(unrelated.parameter_output_values)) == unrelated_before
        assert all(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in file_hashes.items())

        # The native lock icon contract must prevent a destructive Reset.
        lock = engine.handle_request(SetLockNodeStateRequest(node_name=old.name, lock=True))
        assert lock.succeeded(), lock.result_details
        locked_view = engine.handle_request(connection_api.HMBGetNodeConnectionsRequest(node_name=old.name))
        assert locked_view.succeeded() and locked_view.can_refresh is False
        rejected = await engine.ahandle_request(connection_api.HMBManageNodeConnectionsRequest(
            node_name=old.name, operation="refresh", expected_state_token=locked_view.state_token,
            broadcast_result=False))
        assert rejected.failed() and engine.node_manager.get_node_by_name(old.name) is old
        assert not old._hmb_node_deleted
        assert old._hmb_color_lut_state == before_state and dict(old.parameter_output_values) == before_outputs
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in file_hashes.items())
        assert NETWORK_ATTEMPTS == 0, "Optional exception handling hid a forbidden transport attempt"
        return {"status": "PASS", "native_reset": "rejected without mutation", "approved_refresh": "state and wires preserved",
                "compatible_incoming_wires": 1, "compatible_outgoing_wires": 1,
                "custom_position_and_size": "preserved", "other_node_and_two_local_videos": "preserved",
                "locked_refresh": "rejected", "preview_worker_calls": queue_source.call_count,
                "network_calls": NETWORK_ATTEMPTS, "paid_requests": 0, "user_workflow_changes": 0}


def main():
    if importlib.util.find_spec("griptape_nodes") is None:
        print("HMB_COLOR_LUT_NATIVE_HEADER_RESET_HOST=SKIP (installed SDK required)")
        return
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-lut-native-header-reset-", ignore_cleanup_errors=True) as temporary:
        folder = Path(temporary)
        environment = {name: str(folder / name) for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
            "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        with mock.patch.dict(os.environ, environment), mock.patch.object(socket, "create_connection", no_network):
            os.chdir(folder)
            logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:
                    print(json.dumps(asyncio.run(exercise(engine, folder)), ensure_ascii=False))
            finally:
                os.chdir(previous)
                logging.shutdown()


if __name__ == "__main__":
    main()
