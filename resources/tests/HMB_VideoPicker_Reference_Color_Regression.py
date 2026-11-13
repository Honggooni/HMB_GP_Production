"""Repeated references retain independent colors through persistence and job creation."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("reference_color_picker", ROOT / "HMBVideoPickerLibrary.py")
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)

names = ["FireflyAa", "FireflyAa1", "crowd:FireflyAa", "fireflyAa"]
roots = [dict(name=name, full_path="|CHARACTERS|" + name + ":Root",
              maya_uuid="SHARED-REFERENCE-UUID", reference_node=name + "RN") for name in names]
bindings = [dict(group_name=row["name"], full_dag_path=row["full_path"],
                 maya_uuid=row["maya_uuid"], reference_node=row["reference_node"],
                 reference_file="C:/assets/FireflyAa.mb", color="Red", enabled=True,
                 video_slot=1, picker_order=i + 1) for i, row in enumerate(roots)]
node = picker.HMBVideoPickerLibrary(name="Reference Color Regression")
with tempfile.TemporaryDirectory(prefix="hmb-reference-color-") as tmp:
    scene = Path(tmp) / "references.mb"
    scene.write_bytes(b"isolated state fixture")
    state = picker._parse_state(dict(scene_path=str(scene), scene_request_path=str(scene),
        native_read_ready=True, selected_camera="|camera", start_frame=1, end_frame=2,
        source_fps=24, outliner_nodes=roots, selected_outliner_path=roots[1]["full_path"],
        slot_assignments=[dict(video_slot=1, bindings=bindings + [copy.deepcopy(bindings[0])])]))
    assert len(state["slot_assignments"][0]["bindings"]) == 4
    paths = [row["full_path"] for row in roots]
    assert state["selected_outliner_path"] == paths[1]
    original = copy.deepcopy(state)
    for color in picker.MARKER_ORDER:
        edited = copy.deepcopy(state)
        for row in edited["slot_assignments"][0]["bindings"]:
            row["color"] = color
        merged = node._merge_widget_state(state, edited)
        save = Path(tmp) / "saved-state.json"
        save.write_text(json.dumps(merged), encoding="utf-8")
        reopened = picker._parse_state(json.loads(save.read_text(encoding="utf-8")))
        job = node._selected_slot_job_bindings(reopened, 1)
        assert [row["full_dag_path"] for row in job] == paths
        assert {row["color"] for row in job} == {color}
        assert len(picker._normalize_markers(job + copy.deepcopy(job), 1)) == 4
        assert len({row["maya_uuid"] for row in job}) == 1
        for row in job:
            cue = picker._emitter_identity_from_cue(row, job)
            assert cue["subject_root"] == row["full_dag_path"]
        assert picker._emitter_identity_from_cue({"maya_uuid": "SHARED-REFERENCE-UUID"}, job) == {}
        assert picker._emitter_identity_from_cue({"color": color}, job) == {}
        assert picker._emitter_identity_from_cue({"subject_root": "|missing", "color": color}, job) == {}

    # A later recolor or clear must affect only that exact reference.
    edited = copy.deepcopy(state)
    edited["slot_assignments"][0]["bindings"][1]["color"] = "Blue"
    edited["slot_assignments"][0]["bindings"].pop(2)
    merged = node._merge_widget_state(state, edited)
    job = node._selected_slot_job_bindings(merged, 1)
    assert [row["full_dag_path"] for row in job] == [paths[0], paths[1], paths[3]]
    assert [row["color"] for row in job] == ["Red", "Blue", "Red"]
    assert state == original
    assert picker._operation_input_digest("run_video", str(scene), state, 1) != picker._operation_input_digest("run_video", str(scene), merged, 1)

    # Actual command admission carries all instances, without launching a DCC.
    node._picker_state = lambda: copy.deepcopy(state)
    received = []
    node._start_ui_operation = lambda action, value: received.append((action, copy.deepcopy(value)))
    for action in ("render_snapshot", "run_video"):
        node._hmb_pending_operation_id = ""
        node._handle_picker_command(dict(schema=picker.COMMAND_SCHEMA, version=picker.COMMAND_VERSION,
            runtime_instance_id=node._hmb_runtime_instance_id, action=action, action_id="reference-" + action,
            payload=dict(scene_path=str(scene), snapshot_frame=1,
                         authoring_state=dict(slot_assignments=state["slot_assignments"]))))
        assert received[-1][0] == action
        assert [row["full_dag_path"] for row in node._selected_slot_job_bindings(received[-1][1], 1)] == paths

    # Legacy pathless UUID rows still deduplicate; exact paths remain case-sensitive.
    legacy = dict(bindings[0], full_dag_path="")
    assert len(picker._normalize_assignment_bindings([legacy, copy.deepcopy(legacy)], 1)) == 1

print("Repeated reference colors: PASS (16 markers, save/reopen, recolor/clear, Snapshot/Playblast admission)")
