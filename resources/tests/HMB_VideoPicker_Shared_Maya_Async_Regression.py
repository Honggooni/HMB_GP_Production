"""Single Maya staging and captured destination under actual Picker lifecycle methods.

Only retained-bus publication and Maya rendering are isolated: class state merge,
before/store/after command handling, worker locks, cancellation and atomic catalog
commit are production methods. This is not a real Maya rendering test.
"""
from pathlib import Path
import copy
import importlib.util
import json
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("HMBVideoPickerLibrary", ROOT / "HMBVideoPickerLibrary.py")
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)
picker._request_parameter_value = lambda *_a, **_k: False
picker._find_mayabatch = lambda: Path("C:/Program Files/Autodesk/Maya2027/bin/mayabatch.exe")
picker._maya_display_version = lambda _p: "2027"


def update_widget(node, state):
    parameter = picker._get_parameter_obj(node, picker.WIDGET_STATE_PARAMETER)
    value = node.before_value_set(parameter, json.dumps(state))
    node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, value)
    node.after_value_set(parameter, value)


def make_node(scene):
    node = picker.HMBVideoPickerLibrary(name="shared_maya_async")
    node._sync_outputs_from_state = lambda _state: ""
    state = node._picker_state()
    rows = []
    for number in range(1, 6):
        row = copy.deepcopy(state["picker_shots"][0])
        row.update({"workspace_uuid": f"00000000-0000-4000-8000-{number:012d}",
                    "bound_shot_uuid": f"10000000-0000-4000-8000-{number:012d}",
                    "number": number, "name": f"Shot {number}"})
        rows.append(row)
    state.update({
        "picker_shots": rows, "active_picker_shot_uuid": rows[0]["workspace_uuid"],
        "scene_path": str(scene), "scene_request_path": str(scene), "scene_draft_path": str(scene),
        "scene_stage": "OUTLINER_READY", "status": "OUTLINER_READY", "native_read_ready": True,
        "native_metadata": {"scene_path": str(scene)},
        "selected_camera": "cameraA", "camera": "cameraA",
        "cameras": [{"name": "cameraA", "full_path": "|cameraA", "default_camera": False}],
        "start_frame": 101.0, "end_frame": 162.0, "current_frame": 125.0,
        "source_fps": 24.0, "output_width": 1280, "output_height": 720,
        "original_enabled": False, "mask_enabled": True, "depth_enabled": False, "motion_guide_enabled": False,
        "outliner_nodes": [{"name": "Hero", "full_path": "|Hero", "maya_uuid": "heroA"}],
        "selected_outliner_uuid": "heroA", "selected_color": "Red",
        "slot_assignments": [{"video_slot": 1, "bindings": [{"full_dag_path": "|Hero", "maya_uuid": "heroA", "group_name": "Hero", "color": "Red"}]}],
    })
    node._store_initial_parameter_value("MAYA_SCENE", str(scene))
    node._write_state(state)
    return node, rows


def start_generation(node, media, request_target=None):
    entered, release = threading.Event(), threading.Event()
    captured = {}
    node._prepare_run_state = lambda *_a, **_k: None

    def maya_stage(_scene, _slot, context=None, **_kwargs):
        captured["context"] = context
        stale = node._operation_stage_state(context)
        captured["state"] = copy.deepcopy(stale)
        entered.set()
        assert release.wait(10), "test timed out waiting for navigation"
        node._assert_operation_current(context, "simulated Maya completion")
        stale = picker._append_video_asset(stale, {
            "video_path": str(media), "video_url": media.as_uri(),
            "generation_role": "mask", "media_kind": picker.MASK_MEDIA_KIND,
            "source_fps": 24, "source_frame_count": 62, "camera": "cameraA",
            "start_frame": 101, "end_frame": 162,
        }, picker_shot_uuid=context.picker_shot_uuid)
        node._write_state(stale)
        captured["post_progress"] = node._picker_state()
        return {"depth_succeeded": False, "motion_guide_succeeded": False}

    node._maya_mode = maya_stage
    state = node._picker_state()
    if request_target:
        state["operation_requested_picker_shot_uuid"] = request_target
    worker = threading.Thread(target=node._start_ui_operation, args=("run_video", state))
    worker.start()
    assert entered.wait(10), node._picker_state().get("message")
    return worker, release, captured


def finish(worker, release):
    release.set()
    worker.join(10)
    assert not worker.is_alive(), "Maya worker failed to release its lock"


with tempfile.TemporaryDirectory(prefix="hmb-shared-maya-") as temp:
    root = Path(temp)
    scene_a, scene_b = root / "scene_A.ma", root / "scene_B.ma"
    scene_a.write_text("// Maya staging A", encoding="utf-8")
    scene_b.write_text("// Maya staging B", encoding="utf-8")
    media = root / "result.mp4"
    media.write_bytes(b"isolated-validated-result")

    # A current per-Shot cursor edit must project to top-level before parse,
    # which otherwise writes an obsolete top-level cursor back into its row.
    node, rows = make_node(scene_a)
    authoritative = node._picker_state()
    authoritative["preview_frame"] = 17.0
    authoritative = picker._parse_state(authoritative)
    incoming = copy.deepcopy(authoritative)
    incoming["preview_frame"] = 42.0
    incoming["picker_shots"][0]["preview_frame"] = 42.0
    incoming["picker_shots"][0]["revision"] += 1
    merged = node._merge_widget_state(authoritative, incoming)
    assert merged["preview_frame"] == 42.0
    assert merged["picker_shots"][0]["preview_frame"] == 42.0
    reloaded = picker._parse_state(json.dumps(merged))
    assert reloaded["preview_frame"] == 42.0
    assert reloaded["current_frame"] == 125.0
    assert node._merge_widget_state(reloaded, authoritative)["preview_frame"] == 42.0

    node, rows = make_node(scene_a)
    worker, release, capture = start_generation(node, media)
    for row in rows[1:]:
        state = picker._activate_picker_workspace_projection(node._picker_state(), row["workspace_uuid"])
        state["preview_frame"] = float(row["number"] * 7)
        for edited_row in state["picker_shots"]:
            if edited_row["workspace_uuid"] == row["workspace_uuid"]:
                edited_row["preview_frame"] = state["preview_frame"]
                edited_row["revision"] += 1
        update_widget(node, state)
        assert node._picker_state()["active_picker_shot_uuid"] == row["workspace_uuid"]
        assert node._operation_is_current(capture["context"])
        assert node._picker_state()["current_frame"] == 125.0
        assert node._picker_state()["native_read_ready"] is True
        assert node._picker_state()["preview_frame"] == float(row["number"] * 7)
    finish(worker, release)
    result = node._picker_state()
    assert result["active_picker_shot_uuid"] == rows[-1]["workspace_uuid"], (result["active_picker_shot_uuid"], capture.get("post_progress", {}).get("active_picker_shot_uuid"), result.get("message"))
    assert capture["post_progress"]["active_picker_shot_uuid"] == rows[-1]["workspace_uuid"]
    assert len(result["videos"]) == 1, result.get("message")
    assert result["videos"][0]["picker_shot_uuid"] == rows[0]["workspace_uuid"]
    assert Path(result["scene_path"]) == scene_a, result["scene_path"]
    assert result["selected_camera"] == "cameraA"
    assert result["slot_assignments"][0]["bindings"][0]["color"] == "Red"
    assert result["current_frame"] == 125.0
    assert result["preview_frame"] == 35.0
    assert picker._parse_state(json.dumps(result))["preview_frame"] == 35.0
    assert capture["post_progress"]["preview_frame"] == 35.0

    # A late command retains the click-time destination without moving the UI.
    node, rows = make_node(scene_a)
    node._write_state(picker._activate_picker_workspace_projection(node._picker_state(), rows[-1]["workspace_uuid"]))
    worker, release, capture = start_generation(node, media, rows[1]["workspace_uuid"])
    assert capture["context"].picker_shot_uuid == rows[1]["workspace_uuid"]
    assert node._picker_state()["active_picker_shot_uuid"] == rows[-1]["workspace_uuid"]
    finish(worker, release)
    assert node._picker_state()["videos"][0]["picker_shot_uuid"] == rows[1]["workspace_uuid"]

    # New scene selection waits: no second Maya worker and no discarded A result.
    node, rows = make_node(scene_a)
    worker, release, capture = start_generation(node, media)
    node._store_initial_parameter_value("MAYA_SCENE", str(scene_b))
    node._schedule_scene_selection(str(scene_b), "regression")
    assert node._operation_is_current(capture["context"])
    assert not node._hmb_cancel_requested.is_set()
    assert Path(node._picker_state()["scene_path"]) == scene_a
    finish(worker, release)
    result = node._picker_state()
    assert len(result["videos"]) == 1
    assert Path(result["scene_path"]) == scene_b
    assert result["native_read_ready"] is False
    assert result["outliner_nodes"] == []
    assert result["slot_assignments"] == [{"video_slot": 1, "bindings": []}]
    assert Path(picker._maya_scene_path_text(picker._raw_parameter_value(node, "MAYA_SCENE"))) == scene_b

    # Genuine authored changes still cancel; navigation is not an input edit.
    node, rows = make_node(scene_a)
    worker, release, capture = start_generation(node, media)
    edited = node._picker_state()
    edited["slot_assignments"][0]["bindings"][0]["color"] = "Blue"
    update_widget(node, edited)
    assert not node._operation_is_current(capture["context"])
    assert node._hmb_cancel_requested.is_set()
    finish(worker, release)
    assert node._picker_state()["videos"] == []
    assert node._picker_state()["slot_assignments"][0]["bindings"][0]["color"] == "Blue"

    node, rows = make_node(scene_a)
    worker, release, capture = start_generation(node, media)
    removed = picker._activate_picker_workspace_projection(node._picker_state(), rows[1]["workspace_uuid"])
    removed["picker_shots"] = [r for r in removed["picker_shots"] if r["workspace_uuid"] != rows[0]["workspace_uuid"]]
    node._write_state(removed)
    assert not node._operation_is_current(capture["context"])
    assert node._hmb_cancel_requested.is_set()
    finish(worker, release)
    assert node._picker_state()["videos"] == []

    # Snapshot rendering identity ignores the displayed clip and Shot, while
    # both its Maya frame and captured association remain explicit.
    node, rows = make_node(scene_a)
    state = node._picker_state()
    state["snapshot_frame"] = 125
    first_digest = picker._operation_input_digest("render_snapshot", str(scene_a), state, 1)
    for row in rows:
        changed = picker._activate_picker_workspace_projection(state, row["workspace_uuid"])
        changed["preview_frame"] = 1000
        changed["snapshot_request_video_uid"] = "different-preview-association"
        assert picker._operation_input_digest("render_snapshot", str(scene_a), changed, 1) == first_digest
    state["snapshot_frame"] = 126
    assert picker._operation_input_digest("render_snapshot", str(scene_a), state, 1) != first_digest

    # A Snapshot finishing for another Shot must not manufacture a legacy
    # duplicate from stale active/path scalars on an empty destination view.
    node, rows = make_node(scene_a)
    state = picker._append_video_asset(node._picker_state(), {
        "video_uid": "snapshot-video-A", "video_path": str(media),
        "source_fps": 24, "source_frame_count": 62,
    }, picker_shot_uuid=rows[0]["workspace_uuid"])
    state = picker._activate_picker_workspace_projection(state, rows[1]["workspace_uuid"])
    record_a = {"snapshot_uid": "snapshot-A", "video_uid": "snapshot-video-A", "frame": 125,
                "path": str(root / "snapshot-A.png"), "created_at_ms": 1000}
    appended = picker._append_snapshot_history_record(state, record_a, picker_shot_uuid=rows[0]["workspace_uuid"])
    assert len(appended["snapshots"]) == 1
    assert appended["active_picker_shot_uuid"] == rows[1]["workspace_uuid"]
    assert appended["active_snapshot_uid"] == ""
    assert appended["snapshot_active"] is False
    assert appended["snapshot_path"] == appended["snapshot_url"] == ""
    assert appended["picker_shots"][0]["active_snapshot_uid"] == "snapshot-A"
    assert appended["picker_shots"][1]["active_snapshot_uid"] == ""
    returned = picker._activate_picker_workspace_projection(appended, rows[0]["workspace_uuid"])
    assert returned["active_snapshot_uid"] == "snapshot-A"
    assert returned["snapshot_frame"] == 125
    blank = copy.deepcopy(returned)
    picker._restore_picker_workspace_projection(blank, blank["picker_shots"][1])
    blank = picker._parse_state(blank)
    assert len(blank["snapshots"]) == 1 and blank["active_snapshot_uid"] == ""

    # Production worker Snapshot125 remains valid while viewing Shot2's150.
    node, rows = make_node(scene_a)
    state = picker._append_video_asset(node._picker_state(), {
        "video_uid": "snapshot-video-A", "video_path": str(media),
        "source_fps": 24, "source_frame_count": 62,
    }, picker_shot_uuid=rows[0]["workspace_uuid"])
    state = picker._append_snapshot_history_record(state, {
        "snapshot_uid": "snapshot-B", "frame": 150,
        "path": str(root / "snapshot-B.png"), "created_at_ms": 999,
    }, picker_shot_uuid=rows[1]["workspace_uuid"])
    state["snapshot_frame"] = 125
    state["snapshot_request_frame"] = 125
    state["snapshot_request_video_uid"] = "snapshot-video-A"
    node._write_state(state)
    entered, release = threading.Event(), threading.Event()
    snapshot_capture = {}

    def snapshot_worker(_scene, _slot, context=None, **_kwargs):
        snapshot_capture["context"] = context
        frozen = node._operation_stage_state(context)
        assert frozen["snapshot_request_frame"] == 125
        entered.set()
        assert release.wait(10)
        node._assert_operation_current(context, "Snapshot simulated completion")
        result = picker._append_snapshot_history_record(node._picker_state(), record_a,
                                                       picker_shot_uuid=context.picker_shot_uuid)
        node._write_state(node._mark_operation_finished(result))
        return {"snapshot_uid": "snapshot-A"}

    node._snapshot_mode = snapshot_worker
    worker = threading.Thread(target=node._start_ui_operation, args=("render_snapshot", node._picker_state()))
    worker.start()
    assert entered.wait(10)
    selected = picker._activate_picker_workspace_projection(node._picker_state(), rows[1]["workspace_uuid"])
    for row in selected["picker_shots"]:
        row["revision"] += 1
    update_widget(node, selected)
    assert node._picker_state()["snapshot_frame"] == 150
    assert node._picker_state()["snapshot_request_frame"] == 125
    assert node._operation_is_current(snapshot_capture["context"])
    finish(worker, release)
    result = node._picker_state()
    assert len(result["snapshots"]) == 2
    assert result["active_picker_shot_uuid"] == rows[1]["workspace_uuid"]
    assert result["active_snapshot_uid"] == "snapshot-B"
    assert result["snapshot_frame"] == 150
    assert result["current_frame"] == 125
    assert result["snapshot_request_frame"] is None
    returned = picker._activate_picker_workspace_projection(result, rows[0]["workspace_uuid"])
    assert returned["active_snapshot_uid"] == "snapshot-A"
    assert returned["snapshot_frame"] == 125
    assert len(picker._parse_state(json.dumps(returned))["snapshots"]) == 2

print("HMB VideoPicker shared Maya async regression: PASS (navigation, captured target, scene queue, input cancellation, deleted target)")
