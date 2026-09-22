"""Offline contracts for multi-object masks and Snapshot retry readiness."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "hmb_picker_multi_snapshot_regression", ROOT / "HMBVideoPickerLibrary.py"
)
assert spec and spec.loader
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)


def binding(name: str, color: str, order: int) -> dict:
    return {
        "group_name": name, "full_dag_path": "|" + name,
        "maya_uuid": "uuid-" + name, "color": color, "enabled": True,
        "video_slot": 1, "picker_order": order,
    }


node = picker.HMBVideoPickerLibrary(name="Multi Selection Snapshot Regression")
with tempfile.TemporaryDirectory(prefix="hmb-picker-multi-snapshot-") as temporary:
    scene = Path(temporary) / "scene.ma"
    scene.write_text("// simulated Maya scene", encoding="utf-8")
    roots = [
        {"name": "ActorA", "full_path": "|ActorA", "maya_uuid": "uuid-ActorA",
         "depth_meshes": [{"name": "Face", "full_path": "|ActorA|Face",
                           "maya_uuid": "uuid-Face", "node_kind": "mesh",
                           "parent_path": "|ActorA"}]},
        {"name": "ActorB", "full_path": "|ActorB", "maya_uuid": "uuid-ActorB"},
        {"name": "ActorC", "full_path": "|ActorC", "maya_uuid": "uuid-ActorC"},
    ]
    base = picker._parse_state({
        "scene_path": str(scene), "scene_request_path": str(scene),
        "native_read_ready": True, "selected_camera": "|camera",
        "start_frame": 101.0, "end_frame": 125.0, "source_fps": 24.0,
        "outliner_nodes": roots, "selected_outliner_path": "|ActorA",
        "slot_assignments": [{"video_slot": 1, "bindings": [
            binding("ActorA", "Red", 1), binding("ActorB", "Blue", 2),
            binding("ActorC", "Red", 3),
        ]}],
    })
    assert base["selected_outliner_paths"] == ["|ActorA"]
    scope = base["outliner_selection_scope"]
    multi = picker._parse_state(dict(
        base, selected_outliner_paths=["|ActorA", "|ActorB", "|ActorA|Face", "|ActorB", "|missing"],
        outliner_selection_scope=scope, outliner_selection_anchor="|ActorA",
    ))
    assert multi["selected_outliner_paths"] == ["|ActorA", "|ActorB", "|ActorA|Face"]
    assert picker._parse_state(multi)["selected_outliner_paths"] == multi["selected_outliner_paths"]
    cleared = picker._parse_state(dict(multi, selected_outliner_paths=[]))
    assert cleared["selected_outliner_paths"] == []
    assert cleared["selected_outliner_path"] == ""
    assert picker._parse_state(cleared)["selected_outliner_paths"] == []
    other_shot = copy.deepcopy(multi)
    other_shot["active_picker_shot_uuid"] = "other-shot"
    picker._normalize_outliner_selection_fields(other_shot)
    assert other_shot["selected_outliner_paths"] == ["|ActorA"]
    assert other_shot["outliner_selection_scope"] != scope

    # One widget transaction applies the selected targets together. Other
    # targets already using that marker retain their explicit object identity.
    edited = copy.deepcopy(multi)
    for entry in edited["slot_assignments"][0]["bindings"]:
        if entry["full_dag_path"] in edited["selected_outliner_paths"]:
            entry["color"] = "Red"
    merged = node._merge_widget_state(base, edited)
    job_bindings = node._selected_slot_job_bindings(merged, 1)
    assert [entry["color"] for entry in job_bindings] == ["Red", "Red", "Red"]
    assert [entry["asset_id"] for entry in job_bindings] == ["ActorA", "ActorB", "ActorC"]
    assert merged["selected_outliner_paths"] == edited["selected_outliner_paths"]
    markers = picker._normalize_markers(job_bindings, 1)
    assert len(markers) == 3 and len({entry["maya_uuid"] for entry in markers}) == 3
    assert len(picker._normalize_markers(markers + [copy.deepcopy(markers[0])], 1)) == 3
    stale = dict(edited, state_revision=1)
    latest = dict(base, state_revision=2)
    assert node._merge_widget_state(latest, stale)["slot_assignments"] == latest["slot_assignments"]

    # Snapshot command uses the exact latest authored selection even if the
    # independent HMB_PICKER_STATE transport has not delivered it yet.
    captured = []
    node._picker_state = lambda: copy.deepcopy(base)
    node._start_ui_operation = lambda action, state: captured.append((action, copy.deepcopy(state)))
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "render_snapshot", "action_id": "latest-snapshot-authoring",
        "payload": {"scene_path": str(scene), "snapshot_frame": 112.0,
                    "authoring_state": {"slot_assignments": edited["slot_assignments"]}},
    })
    assert captured and captured[0][0] == "render_snapshot"
    assert captured[0][1]["slot_assignments"] == edited["slot_assignments"]
    assert captured[0][1]["snapshot_request_frame"] == 112.0

    # Shot navigation before delivery changes only the catalog destination
    # view, not the shared Maya authoring stage. Snapshot retains click-time A.
    rows = []
    for number in (1, 2):
        row = copy.deepcopy(base["picker_shots"][0])
        row.update(workspace_uuid=f"00000000-0000-4000-8000-{number:012d}",
                   bound_shot_uuid=f"10000000-0000-4000-8000-{number:012d}",
                   number=number, name=f"Shot {number}")
        rows.append(row)
    viewing_b = picker._parse_state(dict(base, picker_shots=rows,
                                        active_picker_shot_uuid=rows[1]["workspace_uuid"]))
    captured.clear()
    node._hmb_pending_operation_id = ""
    node._picker_state = lambda: copy.deepcopy(viewing_b)
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "render_snapshot", "action_id": "snapshot-captured-shot-a",
        "payload": {"scene_path": str(scene), "snapshot_frame": 112.0,
                    "picker_shot_uuid": rows[0]["workspace_uuid"],
                    "authoring_state": {"slot_assignments": base["slot_assignments"]}},
    })
    assert captured and captured[0][1]["active_picker_shot_uuid"] == rows[1]["workspace_uuid"]
    assert captured[0][1]["slot_assignments"] == viewing_b["slot_assignments"]
    context = node._create_operation_context("render_snapshot", str(scene), captured[0][1])
    assert context.picker_shot_uuid == rows[0]["workspace_uuid"]
    published = picker._append_snapshot_history_record(viewing_b, {
        "snapshot_uid": "snapshot-from-a", "frame": 112.0,
        "path": str(scene.parent / "snapshot-from-a.png"), "created_at_ms": 1000,
    }, picker_shot_uuid=context.picker_shot_uuid)
    assert published["active_picker_shot_uuid"] == rows[1]["workspace_uuid"]
    assert published["picker_shots"][0]["active_snapshot_uid"] == "snapshot-from-a"
    assert published["picker_shots"][1]["active_snapshot_uid"] == ""
    assert published["slot_assignments"] == viewing_b["slot_assignments"]

    # New global color edits after the navigation are not overwritten by a
    # delayed Snapshot. Acknowledge/cancel only this stale command, not a node.
    newer_b = copy.deepcopy(viewing_b)
    newer_b["slot_assignments"][0]["bindings"][0]["color"] = "Green"
    captured.clear()
    written = []
    node._hmb_pending_operation_id = ""
    node._picker_state = lambda: copy.deepcopy(newer_b)
    node._write_state = lambda state: written.append(copy.deepcopy(state))
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "render_snapshot", "action_id": "snapshot-stale-old-colors",
        "payload": {"scene_path": str(scene), "snapshot_frame": 112.0,
                    "picker_shot_uuid": rows[0]["workspace_uuid"],
                    "authoring_state": {"slot_assignments": base["slot_assignments"]}},
    })
    assert captured == [] and written
    assert written[-1]["slot_assignments"] == newer_b["slot_assignments"]
    assert written[-1]["active_picker_shot_uuid"] == rows[1]["workspace_uuid"]
    assert written[-1]["backend_ack_action_id"] == "snapshot-stale-old-colors"
    assert written[-1]["pending_action"] == written[-1]["pending_action_id"] == ""
    assert "Current settings were preserved" in written[-1]["message"]

    class ReachedMayaDetection(Exception):
        pass

    original_find_maya = picker._find_mayabatch
    picker._find_mayabatch = lambda: (_ for _ in ()).throw(ReachedMayaDetection())
    try:
        for status in ("OUTLINER_READY", "FAILED", "CANCELLED"):
            retained = dict(base, status=status, scene_stage=status,
                            original_enabled=True, mask_enabled=False,
                            slot_assignments=[{"video_slot": 1, "bindings": []}])
            node._operation_stage_state = lambda _context, state=retained: copy.deepcopy(state)
            assert node._selected_slot_job_bindings(retained, 1) == []
            try:
                node._snapshot_mode(str(scene), 1)
            except ReachedMayaDetection:
                pass
            else:
                raise AssertionError("Completed READ must permit an uncolored Snapshot retry.")
        try:
            node._snapshot_mode(str(scene.parent / "missing.ma"), 1)
        except ReachedMayaDetection:
            raise AssertionError("A missing Snapshot scene reached Maya detection.")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("A missing Snapshot scene was accepted.")
    finally:
        picker._find_mayabatch = original_find_maya

print("VideoPicker multi-object same-color, scoped selection, atomic Snapshot authoring and retry: PASS")
