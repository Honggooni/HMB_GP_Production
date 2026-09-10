"""Actual installed Griptape node/parameter construction, no network or user state."""
from __future__ import annotations
import copy
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest import mock

ROOT = Path(os.environ.get("HMB_COLOR_LUT_TEST_ROOT", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))


def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.exe_types.node_types import DataNode
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    with tempfile.TemporaryDirectory(prefix="hmb-lut-host-") as directory:
        root = Path(directory)
        env = {key: str(root / key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA")}
        env["GTN_CONFIG_WORKSPACE_DIRECTORY"] = str(root)
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                # Mimic Desktop's resolved static origin without starting any
                # network server or altering the user's application config.
                GriptapeNodes.StaticFilesManager()._static_server_base_url = "http://127.0.0.1:43219"
                import HMBColorLUTLibrary as lut
                import _hmb_shot_routing as routing
                ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(display_name="LUT archive", flow_name="LUTArchive"))
                from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
                workflow = WorkflowRegistry.get_workflow_by_name(GriptapeNodes.ContextManager().get_current_workflow_name())
                workflow.file_path = "shots/example.py"
                assert lut._workflow_data_directory() == root / "shots" / "data"
                workflow.file_path = str(root / "moved" / "example.py")
                assert lut._workflow_data_directory() == root / "moved" / "data"
                workflow.file_path = None
                assert lut._workflow_data_directory() == root / "data"
                with mock.patch.object(routing, "schedule_post_registration_reconcile"), mock.patch.object(routing, "reconcile_shot_routing"):
                    node = lut.HMBColorLUTLibrary(name="Color LUT Host")
                    assert isinstance(node, DataNode), type(node).__mro__
                    parameter = node.get_parameter_by_name(lut.UI)
                    assert parameter.ui_options["expandable"] is True
                    assert parameter.ui_options["width"] == lut.COLOR_LUT_WIDGET_WIDTH
                    assert parameter.ui_options["height"] == lut.COLOR_LUT_WIDGET_HEIGHT
                    initial_size = {"width": lut.COLOR_LUT_NODE_WIDTH, "height": lut.COLOR_LUT_NODE_HEIGHT}
                    assert node.metadata["size"] == initial_size
                    manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
                    declared = next(item["metadata"] for item in manifest["nodes"] if item["class_name"] == "HMBColorLUTLibrary")
                    for options in (declared, declared["ui_options"]):
                        assert {key: options[key] for key in initial_size} == initial_size
                    saved_metadata = {"size": {"width": 1370, "height": 1175}, "position": {"x": 12, "y": 34}}
                    restored_node = lut.HMBColorLUTLibrary(name="Restored Color LUT", metadata=copy.deepcopy(saved_metadata))
                    restored_node.process()
                    restored_node._publish()
                    assert restored_node.metadata == saved_metadata, "Existing user size and position must not change."
                    restored_node.after_node_deleted()
                    assert node.get_parameter_value(lut.UI)["profiles"] == []
                    state = copy.deepcopy(node.get_parameter_value(lut.UI))
                    state["revision"] += 1
                    state["settings"] = {"enabled": True, "contrast": 2}
                    node.set_parameter_value(lut.UI, state)
                    assert node._hmb_color_lut_state["settings"]["contrast"] == 2
                    assert node._hmb_color_lut_state["settings"]["enabled"] is True
                    fine_settings = {**lut.default_settings(), "enabled":True, "exposure":.25, "temperature":-.75,
                                     "contrast":1.25, "saturation":-1.75, "shadows":2.25, "highlights":-2.75}
                    state = copy.deepcopy(node.get_parameter_value(lut.UI))
                    state["revision"] += 1
                    state["settings"] = fine_settings
                    node.set_parameter_value(lut.UI, state)
                    assert node._hmb_color_lut_state["settings"] == fine_settings
                    node.process()
                    assert not node._worker
                    # Exercise actual native Generator snapshot -> real local
                    # probing -> real encoder, replacing only paid generation.
                    import HMBSeedanceGeneration as seedance
                    from _hmb_video_tools import _find_ffmpeg
                    clip = root / "volcengine_seedance_video_shot_01_원본.mp4"
                    subprocess.run([_find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=96x64:r=30",
                        "-t", "0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
                    generator = seedance.HMBSeedanceGeneration(name="Completed Generator")
                    shot = {"channel_uuid": "11111111-1111-4111-8111-111111111111", "shot_uuid": "22222222-2222-4222-8222-222222222222", "number": 1, "name": "Shot 1"}
                    origin = {**shot, "source_node_instance_id": "33333333-3333-4333-8333-333333333333"}
                    # The user's pre-LUT workflow retains VIDEO_OUT plus a
                    # local_succeeded checkpoint, but no generated-source field.
                    from griptape.artifacts.video_url_artifact import VideoUrlArtifact
                    generator.parameter_output_values["VIDEO_OUT"] = VideoUrlArtifact(value=str(clip), name=clip.name)
                    generator.parameter_values[seedance.SEEDANCE_RECOVERY_PARAMETER] = {
                        "stage": "local_succeeded", "status": "succeeded", "task_id": "saved-before-lut", "task_identity": "broker_task"}
                    with mock.patch.object(generator, "_hmb_shot_channel_subscription", return_value={
                        "enabled": True, "channel_uuid": shot["channel_uuid"], "shot_uuid": shot["shot_uuid"], "shot_number": 1, "shot_name": "Shot 1"}):
                        restored = generator._hmb_generated_video_source_snapshot()
                        assert restored["path"] == str(clip) and restored["shot_uuid"] == shot["shot_uuid"]
                    node._hmb_color_lut_state["shot"] = shot
                    assert generator._record_completed_video_source(origin, "offline-completed", SimpleNamespace(resolve=lambda: str(clip), location=str(clip)))
                    assert node._hmb_hydrate_color_lut_from_source(generator)
                    node._source_worker.join(timeout=30)
                    assert node._hmb_color_lut_state["source"].get("path") == str(clip), node._hmb_color_lut_state["status"]
                    assert node._hmb_color_lut_state["source"]["fps"] == 30
                    node._hmb_color_lut_state["output"] = {"codec": "hevc10", "manual_output_enabled": True, "path": str(root / "final.mp4")}
                    node._command({"id": "host-local-export", "action": "export"})
                    node._worker.join(timeout=60)
                    assert node._hmb_color_lut_state["status"]["phase"] == "complete", node._hmb_color_lut_state["status"]
                    assert Path(node._hmb_color_lut_state["result"]["path"]).is_file()
                    assert node._hmb_color_lut_state["result"]["shot"]["shot_uuid"] == shot["shot_uuid"]
                    assert Path(node._hmb_color_lut_state["result"]["lut_path"]).parent == root / "data"
                    assert Path(node._hmb_color_lut_state["result"]["metadata_path"]).is_file()
                    archive = json.loads(Path(node._hmb_color_lut_state["result"]["metadata_path"]).read_text(encoding="utf-8"))
                    assert archive["settings"] == fine_settings
                    assert node.parameter_output_values["video_url"]
                    node.after_node_deleted()
                    assert node._hmb_node_deleted
    print("HMB_COLOR_LUT_HOST=PASS (real Generator snapshot, DataNode/Widget, property update, original probe, 30fps, HEVC10 encode, output publication, no paid generation, deletion)")


if __name__ == "__main__":
    main()
