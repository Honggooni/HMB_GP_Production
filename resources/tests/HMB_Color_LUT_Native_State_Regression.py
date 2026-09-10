"""Regress real host SetParameterValue and native lifecycle state collisions."""
from __future__ import annotations
import copy
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from unittest import mock

ROOT = Path(os.environ.get("HMB_COLOR_LUT_TEST_ROOT", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))


def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest, SetParameterValueResultSuccess
    with tempfile.TemporaryDirectory(prefix="hmb-lut-native-state-") as directory:
        root = Path(directory)
        env = {key: str(root / key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA")}
        env["GTN_CONFIG_WORKSPACE_DIRECTORY"] = str(root)
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                GriptapeNodes.StaticFilesManager()._static_server_base_url = "http://127.0.0.1:43219"
                engine.event_manager.initialize_queue()
                import HMBColorLUTLibrary as lut
                import _hmb_shot_routing as routing
                from _hmb_video_tools import _find_ffmpeg
                clip = root / "영상 불러오기.mp4"
                subprocess.run([_find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=96x64:r=30",
                    "-t", "0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
                ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(display_name="Color LUT Native State", flow_name="ColorLUTNativeState"))
                flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
                with mock.patch.object(routing, "schedule_post_registration_reconcile"), mock.patch.object(routing, "reconcile_shot_routing"):
                    node = lut.HMBColorLUTLibrary(name="HMB Color LUT State Regression")
                    flow.add_node(node)
                    engine.object_manager.add_object_by_name(node.name, node)
                    engine.node_manager._name_to_parent_flow_name[node.name] = flow.name
                    assert "VIDEO_IN" not in {p.name for p in node.parameters}

                    def send(value):
                        result = engine.handle_request(SetParameterValueRequest(node_name=node.name, parameter_name=lut.UI, value=value, data_type="dict"))
                        assert isinstance(result, SetParameterValueResultSuccess), str(result)

                    # Desktop resets native resolution state during registration,
                    # hydration and invalidation. This reproduced the reported
                    # 'string indices must be integers' before the namespace fix.
                    for native in NodeResolutionState:
                        node.state = native
                        value = copy.deepcopy(node.get_parameter_value(lut.UI))
                        value["revision"] += 1
                        value["settings"]["contrast"] = 2
                        send(value)
                        assert isinstance(node.state, NodeResolutionState)
                        assert node.get_parameter_value(lut.UI)["settings"]["contrast"] == 2
                    assert isinstance(node.state, NodeResolutionState)

                    # Use the exact embedded command payload from the production
                    # widget, substituting only the human-operated native dialog.
                    for iteration, chosen in enumerate(("", str(clip), str(clip)) * 3):
                        node.state = NodeResolutionState.UNRESOLVED
                        value = copy.deepcopy(node.get_parameter_value(lut.UI))
                        value.pop("shot_states", None)
                        value["revision"] += 1
                        value[lut.UI.replace("HMB_COLOR_LUT_UI_STATE", "__hmb_color_lut_command__")] = {
                            "id": f"browse-{iteration}-{time.time_ns()}", "action": "browse_video", "state": copy.deepcopy(value)}
                        with mock.patch.object(lut, "_browse", return_value=chosen) as dialog:
                            send(value)
                            node._worker.join(timeout=15)
                            if node._source_worker:
                                node._source_worker.join(timeout=15)
                            assert dialog.call_count == 1, (chosen, node._seen_commands)
                        value = node.get_parameter_value(lut.UI)
                        assert value["status"]["phase"] != "error", value["status"]
                        if chosen:
                            assert value["source"].get("path") == chosen, (value["status"], value["source"], node._source_pending, node._hmb_color_lut_state["source"], node._pending_source_key)
                            assert value["source"]["fps"] == 30
                        assert isinstance(node.state, NodeResolutionState)
                        assert "__hmb_color_lut_command__" not in value
                    assert node.get_parameter_value(lut.UI)["source"]["path"] == str(clip)
                    node.after_node_deleted()
    print("HMB_COLOR_LUT_NATIVE_STATE=PASS (real retained SetParameterValue, all native states, browse/cancel/rebrowse, Korean path, single shared preview, no native video input)")


if __name__ == "__main__":
    main()
