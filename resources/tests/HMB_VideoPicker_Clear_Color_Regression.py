"""Clear one Outliner color without reviving history or changing saved media."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "hmb_picker_clear_color_regression", ROOT / "HMBVideoPickerLibrary.py"
)
assert spec and spec.loader
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)


def binding(path: str, color: str, order: int) -> dict:
    return {
        "group_name": path.rsplit("|", 1)[-1], "full_dag_path": path,
        "maya_uuid": "uuid-" + path, "color": color, "enabled": True,
        "video_slot": 1, "picker_order": order,
    }


node = picker.HMBVideoPickerLibrary(name="Clear Outliner Color Regression")
with tempfile.TemporaryDirectory(prefix="hmb-picker-clear-color-") as temporary:
    folder = Path(temporary)
    scene = folder / "scene.ma"
    scene.write_text("// offline Maya fixture", encoding="utf-8")
    roots = [
        {"name": "ActorA", "full_path": "|ActorA", "maya_uuid": "uuid-|ActorA",
         "depth_meshes": [{"name": "Face", "full_path": "|ActorA|Face",
                           "maya_uuid": "uuid-|ActorA|Face", "node_kind": "mesh",
                           "parent_path": "|ActorA"}]},
        {"name": "ActorB", "full_path": "|ActorB", "maya_uuid": "uuid-|ActorB"},
    ]
    bindings = [binding("|ActorA", "Red", 1), binding("|ActorA|Face", "Blue", 2),
                binding("|ActorB", "Red", 3)]
    base = picker._parse_state({
        "scene_path": str(scene), "scene_request_path": str(scene),
        "native_read_ready": True, "selected_camera": "|camera",
        "start_frame": 101.0, "end_frame": 125.0, "source_fps": 24.0,
        "outliner_nodes": roots, "selected_outliner_path": "|ActorA|Face",
        "slot_assignments": [{"video_slot": 1, "bindings": bindings}],
        "slot_visibility": [{"video_slot": 1, "hidden_paths": ["|ActorB"]}],
    })
    saved_markers = node._selected_slot_job_bindings(base, 1)
    rows = []
    videos = []
    for number in (1, 2):
        uid = f"saved-video-{number}"
        row = copy.deepcopy(base["picker_shots"][0])
        row.update(workspace_uuid=f"00000000-0000-4000-8000-{number:012d}",
                   bound_shot_uuid=f"10000000-0000-4000-8000-{number:012d}",
                   number=number, name=f"Shot {number}", video_asset_uids=[uid],
                   selected_video_uids=[uid], preview_video_uid=uid)
        rows.append(row)
        videos.append({
            "video_uid": uid, "source_uid": uid, "label": uid,
            "video_path": str(folder / (uid + ".mp4")),
            "generation_role": "mask", "media_kind": "maya_mask_playblast",
            "selected": number == 1, "selection_order": 1 if number == 1 else 0,
            "video_slot": 1 if number == 1 else 0,
            "source_fps": 24.0, "decoded_frame_count": 25,
            "markers": copy.deepcopy(saved_markers),
        })
    base = picker._parse_state(dict(base, videos=videos, picker_shots=rows,
                                    active_picker_shot_uuid=rows[0]["workspace_uuid"]))
    assert len(base["videos"]) == 2 and len(base["picker_shots"]) == 2
    historical_media = copy.deepcopy(base["videos"])
    historical_shots = copy.deepcopy(base["picker_shots"])

    # The UI removes the exact explicit row, never all rows sharing its color.
    # Clearing a child leaves its parent color available for normal inheritance.
    for target in ("|ActorA|Face", "|ActorA", "|ActorB"):
        edited = copy.deepcopy(base)
        edited["slot_assignments"][0]["bindings"] = [
            item for item in edited["slot_assignments"][0]["bindings"]
            if item["full_dag_path"] != target
        ]
        if edited["selected_outliner_path"] == target:
            edited["selected_color"] = ""
        merged = node._merge_widget_state(base, edited)
        actual = node._selected_slot_job_bindings(merged, 1)
        assert [item["full_dag_path"] for item in actual] == [
            item["full_dag_path"] for item in saved_markers if item["full_dag_path"] != target
        ]
        assert merged["outliner_nodes"] == base["outliner_nodes"]
        assert merged["slot_visibility"] == base["slot_visibility"]
        assert merged["depth_settings"] == base["depth_settings"]
        assert merged["videos"] == historical_media
        assert merged["picker_shots"] == historical_shots
        restored = picker._parse_state(json.dumps(merged, ensure_ascii=False))
        assert restored["slot_assignments"] == merged["slot_assignments"]
        assert node._selected_slot_job_bindings(restored, 1) == actual

    cleared = copy.deepcopy(base)
    cleared["slot_assignments"] = [{"video_slot": 1, "bindings": []}]
    cleared["selected_color"] = ""
    cleared = node._merge_widget_state(base, cleared)
    assert node._selected_slot_job_bindings(cleared, 1) == []
    assert picker._parse_state(json.dumps(cleared))["slot_assignments"] == cleared["slot_assignments"]

    # READ may infer old catalog markers only if an editable row is absent,
    # never when an explicit empty row records removal of the last assignment.
    history = [{"video_slot": 1, "markers": saved_markers}]
    assert picker._normalize_slot_assignments(cleared["slot_assignments"], 1, history) == cleared["slot_assignments"]
    for legacy in (None, []):
        inferred = picker._normalize_slot_assignments(legacy, 1, history)
        assert len(inferred[0]["bindings"]) == 3
    assert history[0]["markers"] == saved_markers

    # Defaults must not erase the difference between an old missing field and
    # an explicitly cleared field during real JSON hydration. The inactive
    # Shot is deliberately first, with a conflicting color, to reject catalog
    # order as authoring authority.
    legacy_save = copy.deepcopy(base)
    del legacy_save["slot_assignments"]
    other_video = copy.deepcopy(legacy_save["videos"][1])
    other_video["markers"][0]["color"] = "Green"
    other_video["frame_metadata"]["available_color_picks"] = ["Green", "Blue", "Red"]
    legacy_save["videos"] = [other_video, legacy_save["videos"][0]]
    migrated = picker._parse_state(json.dumps(legacy_save))
    assert node._selected_slot_job_bindings(migrated, 1) == saved_markers
    assert migrated["videos"] == legacy_save["videos"]
    assert migrated["picker_shots"] == historical_shots
    assert picker._parse_state(json.dumps(migrated))["slot_assignments"] == migrated["slot_assignments"]
    for explicit_empty in (None, [], [{"video_slot": 1, "bindings": []}]):
        empty_save = dict(legacy_save, slot_assignments=explicit_empty)
        assert picker._parse_state(json.dumps(empty_save))["slot_assignments"] == [
            {"video_slot": 1, "bindings": []}
        ]
    no_primary_save = copy.deepcopy(legacy_save)
    for item in no_primary_save["videos"]:
        item.update(selected=False, selection_order=0, video_slot=0)
    assert picker._parse_state(no_primary_save)["slot_assignments"] == [
        {"video_slot": 1, "bindings": []}
    ]

    # A delayed state echo must not reintroduce colors after the clear commits.
    stale = copy.deepcopy(base)
    stale["state_revision"] = 2
    latest = copy.deepcopy(cleared)
    latest["state_revision"] = 3
    assert node._merge_widget_state(latest, stale)["slot_assignments"] == cleared["slot_assignments"]

    # Snapshot/Playblast's independent command path carries the latest clear,
    # even before the ordinary HMB_PICKER_STATE echo arrives.
    captured = []
    node._picker_state = lambda: copy.deepcopy(base)
    node._start_ui_operation = lambda action, state: captured.append((action, copy.deepcopy(state)))
    for action in ("render_snapshot", "run_video"):
        node._hmb_pending_operation_id = ""
        node._handle_picker_command({
            "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
            "runtime_instance_id": node._hmb_runtime_instance_id,
            "action": action, "action_id": "clear-before-" + action,
            "payload": {"scene_path": str(scene), "snapshot_frame": 112.0,
                        "authoring_state": {"slot_assignments": cleared["slot_assignments"]}},
        })
        assert captured[-1][0] == action
        assert node._selected_slot_job_bindings(captured[-1][1], 1) == []
        assert captured[-1][1]["slot_visibility"] == base["slot_visibility"]

    # Exercise actual metadata-only READ, mocking only the Maya subprocess and
    # publication boundary. No Maya, renderer, network, or user media is opened.
    committed = [copy.deepcopy(cleared)]
    node._picker_state = lambda: copy.deepcopy(committed[0])
    node._write_state = lambda state: committed.__setitem__(0, picker._parse_state(state))
    node._sync_outputs_from_state = lambda state: None
    node._ensure_parameters = lambda: None
    node._wait_for_process_with_progress = lambda *args, **kwargs: 0
    scanned = []

    class OfflineMayaScan:
        returncode = 0
        pid = 4242

        def __init__(self, command, **kwargs):
            job = json.loads(Path(kwargs["env"]["HMB_VIDEO_PICKER_JOB"]).read_text(encoding="utf-8"))
            assert job["operation"] == "scan" and job["generate_original_video"] is False
            scanned.append(job)
            Path(job["result_path"]).write_text(json.dumps({
                "ok": True, "operation": "scan", "maya_version": "2027",
                "scene_path": str(scene), "selected_camera": "|camera",
                "cameras": [{"name": "camera", "full_path": "|camera", "default_camera": False}],
                "start_frame": 101.0, "end_frame": 125.0, "current_frame": 101.0,
                "fps": 24.0, "outliner_nodes": roots, "warnings": [],
                "scene_dependency_paths": [str(scene)],
            }), encoding="utf-8")
            self.stdout = io.StringIO("")

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    with patch.object(picker, "_find_mayabatch", lambda: folder / "Maya2027/bin/mayabatch.exe"), \
         patch.object(picker, "_find_maya_project", lambda path: None), \
         patch.object(picker.subprocess, "Popen", OfflineMayaScan):
        result = node._read_scene_mode(str(scene))
    assert result["mode"] == "scan" and len(scanned) == 1
    after_read = committed[0]
    assert after_read["status"] == "OUTLINER_READY"
    assert after_read["slot_assignments"] == [{"video_slot": 1, "bindings": []}]
    assert node._selected_slot_job_bindings(after_read, 1) == []
    assert after_read["slot_visibility"] == base["slot_visibility"]
    assert after_read["videos"] == historical_media
    assert after_read["picker_shots"] == historical_shots
    assert [row["full_path"] for row in after_read["outliner_nodes"]] == ["|ActorA", "|ActorB"]

    # A missing-field legacy save survives the same real parse -> READ path,
    # while the explicit clear above remains empty through that entire path.
    committed[0] = picker._parse_state(json.dumps(legacy_save))
    with patch.object(picker, "_find_mayabatch", lambda: folder / "Maya2027/bin/mayabatch.exe"), \
         patch.object(picker, "_find_maya_project", lambda path: None), \
         patch.object(picker.subprocess, "Popen", OfflineMayaScan):
        result = node._read_scene_mode(str(scene))
    assert result["mode"] == "scan" and len(scanned) == 2
    assert committed[0]["status"] == "OUTLINER_READY"
    assert node._selected_slot_job_bindings(committed[0], 1) == saved_markers
    assert committed[0]["videos"] == migrated["videos"]
    assert committed[0]["picker_shots"] == migrated["picker_shots"]
    assert committed[0]["slot_visibility"] == migrated["slot_visibility"]

print("VideoPicker explicit color clear, save/reload, command payload and READ persistence: PASS")
