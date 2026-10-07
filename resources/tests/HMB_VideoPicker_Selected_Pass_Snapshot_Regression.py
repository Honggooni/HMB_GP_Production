"""Selected Snapshot pass boundaries, immutable history and deletion ACKs."""
from __future__ import annotations
import ast
import copy
from dataclasses import replace
import importlib.util
import itertools
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hmb_selected_snapshot_regression", ROOT / "HMBVideoPickerLibrary.py")
assert spec and spec.loader
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)

# Execute the production runner's real auxiliary path guard and result
# promotion without importing Maya or rendering. A duplicated mock contract
# previously allowed Depth Snapshot to share its Color staging paths.
runner_path = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
runner_tree = ast.parse(runner_path.read_text(encoding="utf-8-sig"))
runner_run = next(node for node in runner_tree.body if isinstance(node, ast.FunctionDef) and node.name == "run")
runner_try = next(node for node in runner_run.body if isinstance(node, ast.Try))
depth_guard = next(node for node in runner_try.body if isinstance(node, ast.If)
                   and isinstance(node.test, ast.Name) and node.test.id == "generate_depth_playblast"
                   and any(isinstance(child, ast.Constant) and child.value ==
                           "Depth frames folder must be separate from the color frames folder."
                           for child in ast.walk(node)))
auxiliary_promotion = next(node for node in runner_try.body if isinstance(node, ast.If)
                           and isinstance(node.test, ast.Name) and node.test.id == "capture_auxiliary_only")
depth_guard_code = compile(ast.Module(body=[depth_guard], type_ignores=[]), str(runner_path), "exec")
auxiliary_promotion_code = compile(ast.Module(body=[auxiliary_promotion], type_ignores=[]), str(runner_path), "exec")

def validate_native_depth_paths(job):
    namespace = {"os": os, "_clean": picker._clean, "job": job,
                 "frames_folder": os.path.abspath(job["frames_folder"]),
                 "generate_depth_playblast": True}
    exec(depth_guard_code, namespace)
    return namespace

def promote_native_depth_result(result):
    namespace = {"result": result, "capture_auxiliary_only": True, "capture_pass": "depth"}
    exec(auxiliary_promotion_code, namespace)
    return result

def png(width, height, color):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    raw = (b"\0" + bytes(color) * width) * height
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")

with tempfile.TemporaryDirectory(prefix="hmb-selected-snapshot-") as temporary:
    root = Path(temporary)
    scene = root / "scene.ma"
    scene.write_text("// Snapshot fake scene\n", encoding="utf-8")
    bindings = [{"group_name": f"Actor{index}", "full_dag_path": f"|Actor{index}",
                 "maya_uuid": f"actor-{index}", "color": "Red", "enabled": True,
                 "video_slot": 1, "picker_order": index + 1} for index in range(6)]
    base = picker._parse_state({
        "scene_path": str(scene), "scene_request_path": str(scene),
        "native_read_ready": True, "selected_camera": "|Camera",
        "start_frame": 101.0, "end_frame": 180.0, "source_fps": 24.0,
        "snapshot_request_frame": 145.0, "snapshot_frame": 145.0,
        "output_width": 640, "output_height": 360,
        "outliner_nodes": [{"name": item["group_name"], "full_path": item["full_dag_path"],
                           "maya_uuid": item["maya_uuid"]} for item in bindings],
        "slot_assignments": [{"video_slot": 1, "bindings": bindings}],
    })
    node = picker.HMBVideoPickerLibrary(name="Selected Snapshot Regression")
    stored = [copy.deepcopy(base)]
    node._picker_state = lambda: copy.deepcopy(stored[0])
    node._write_state = lambda state: stored.__setitem__(0, copy.deepcopy(state))
    node._assert_operation_current = lambda *args: None
    node._register_active_process = lambda *args: None
    node._clear_active_process = lambda *args: None
    node._wait_for_process_with_progress = lambda *args, **kwargs: 0
    node._register_cleanup_dir = lambda *args: None
    captured = []
    mask_slots = []
    hidden_slots = []
    fail_role = [""]
    bad_layer = [False]
    original_bindings = node._selected_slot_job_bindings
    def selected_bindings(state, slot):
        mask_slots.append(slot)
        return original_bindings(state, 1)
    node._selected_slot_job_bindings = selected_bindings
    node._selected_slot_hidden_paths = lambda state, slot: hidden_slots.append(slot) or ["|Excluded"]

    # Range hints are optional and cannot establish a Color prerequisite.
    with mock.patch.object(node, "_selected_slot_job_bindings", side_effect=ValueError("unassigned Color row")):
        assert node._depth_range_job_bindings(base, 2) == []
    optional_hints = node._depth_range_job_bindings(base, 2)
    assert len(optional_hints) == 6
    optional_hints[0]["full_dag_path"] = "|ChangedCopy"
    assert base["slot_assignments"][0]["bindings"][0]["full_dag_path"] == "|Actor0"

    class FakeProcess:
        def __init__(self, command, *, env, **kwargs):
            job = json.loads(Path(env["HMB_TEST_JOB"]).read_text(encoding="utf-8"))
            captured.append(copy.deepcopy(job))
            role = "original" if job.get("apply_original_lambert_override") else "depth" if job.get("capture_pass") == "depth" else "mask"
            assert job["operation"] == "snapshot", "Never encode a complete video to produce a still."
            assert job["start_frame"] == job["end_frame"] == 145.0
            assert job["camera"] == "|Camera"
            assert job["world_space_patterns"] is (role == "mask")
            assert job["world_pattern_profile"] == (picker.MAYA_WORLD_PATTERN_PROFILE if role == "mask" else "")
            if role != "depth":
                assert "depth_range_bindings" not in job
            if role == "mask":
                assert job["apply_marker_shaders"] is True and job["capture_pass"] == "color"
                assert len(job["bindings"]) == 6
                assert [item["full_dag_path"] for item in job["bindings"]] == [item["full_dag_path"] for item in bindings]
            elif role == "original":
                assert job["apply_marker_shaders"] is False
                assert job["original_material_override_profile"] == picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE
                assert job["bindings"] == job["hidden_paths"] == []
            else:
                assert job["bindings"] == []
                assert job["generate_depth_playblast"] is True
                assert job["depth_profile"] == picker.DEPTH_PLAYBLAST_PROFILE
                assert job["depth_range_mode"] == base["depth_settings"]["range"]
                assert [item["full_dag_path"] for item in job["depth_range_bindings"]] == (
                    [item["full_dag_path"] for item in bindings]
                )
                assert job["depth_range_bindings"] is not job["bindings"]
                validate_native_depth_paths(job)
                # Both guards must stay live, including the sidecar guard that
                # the original same-folder bug never reached.
                for auxiliary_field, color_field, message in (
                    ("depth_frames_folder", "frames_folder", "Depth frames folder"),
                    ("depth_sidecar_path", "sidecar_path", "Depth sidecar path"),
                ):
                    collision = dict(job)
                    collision[auxiliary_field] = collision[color_field]
                    try:
                        validate_native_depth_paths(collision)
                    except RuntimeError as exc:
                        assert message in str(exc)
                    else:
                        raise AssertionError("The actual native path collision guard did not run.")
            if role != "original":
                assert job["hidden_paths"] == ["|Excluded"]
            folder = Path(job["depth_frames_folder"] if role == "depth" else job["frames_folder"])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f'{job["output_name"]}.000000.png').write_bytes(png(
                job["width"], job["height"], {"original": (128,128,128), "mask": (255,0,0), "depth": (64,64,64)}[role]))
            sidecar = {"camera": job["camera"], "start_frame": 145.0, "end_frame": 145.0,
                       "fps": 24.0, "frame_count": 1, "markers": job["bindings"],
                       "original_material_override_profile": picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
                       "original_material_override_report": {"test_role": role},
                       "capture_render_layer": {"capture_layer": "Original" if bad_layer[0] else "defaultRenderLayer",
                                                "default_layer_verified": True, "restored": True, "restore_ok": True},
                       "warnings": []}
            captured_sidecar = job["depth_sidecar_path"] if role == "depth" else job["sidecar_path"]
            picker._write_json(Path(captured_sidecar), sidecar)
            result = {
                "ok": fail_role[0] != role, "error": "intentional selected-pass failure",
                "capture_pass": job.get("capture_pass", ""),
                "capture_render_layer": sidecar["capture_render_layer"],
                "frames_folder": job["frames_folder"], "sidecar_path": job["sidecar_path"]}
            if role == "depth":
                result.update(depth_frames_folder=str(folder),
                              depth_output_name=job["depth_output_name"],
                              depth_sidecar_path=captured_sidecar,
                              depth_frame_count=1,
                              depth_frame_map=[{"sequence_index": 0, "maya_frame": 145.0}])
                promote_native_depth_result(result)
                assert not Path(job["frames_folder"]).exists(), "Depth-only Snapshot rendered an unchecked Color image."
                assert not Path(job["sidecar_path"]).exists(), "Depth-only Snapshot published an unchecked Color sidecar."
            picker._write_json(Path(job["result_path"]), result)

    with mock.patch.object(picker, "_find_mayabatch", return_value=root / "mayabatch.exe"), \
         mock.patch.object(picker, "_maya_display_version", return_value="2027"), \
         mock.patch.object(picker, "_maya_subprocess_environment", side_effect=lambda job: {"HMB_TEST_JOB": str(job)}), \
         mock.patch.object(picker.subprocess, "Popen", FakeProcess), \
         mock.patch.object(picker, "_validate_full_smooth_confirmation") as quality, \
         mock.patch.object(picker, "_validate_world_pattern_runner_confirmation") as mask_check, \
         mock.patch.object(picker, "_original_material_report_is_valid", side_effect=lambda report: report.get("test_role") == "original") as eye_check, \
         mock.patch.object(picker, "_validate_depth_companion_inputs") as depth_check:
        for flags in itertools.product((False, True), repeat=3):
            if not any(flags):
                continue
            choices = dict(base, original_enabled=flags[0], mask_enabled=flags[1], depth_enabled=flags[2])
            stored[0] = copy.deepcopy(choices)
            expected = [role for role, enabled in zip(("original", "mask", "depth"), flags) if enabled]
            context = node._create_operation_context("render_snapshot", str(scene), choices)
            context = replace(context, mask_authoring_slot=2)
            assert list(context.selected_roles) == expected
            captured.clear(); mask_slots.clear(); hidden_slots.clear()
            quality.reset_mock(); mask_check.reset_mock(); eye_check.reset_mock(); depth_check.reset_mock()
            result = node._snapshot_mode(str(scene), 8, context)
            history = stored[0]["snapshots"]
            assert [record["artifact_type"] for record in history] == expected
            assert len({record["snapshot_uid"] for record in history}) == len(expected)
            assert {record["snapshot_batch_uid"] for record in history} == {result["snapshot_batch_uid"]}
            assert len({record["sha256"] for record in history}) == len(expected)
            assert all(record["frame"] == 145.0 and Path(record["path"]).is_file() for record in history)
            assert stored[0]["active_snapshot_uid"] == history[-1]["snapshot_uid"]
            assert stored[0]["viewport_mode"] == "snapshot"
            assert result["snapshot"] == history[-1]["path"]
            assert len(captured) == len(expected), "Unchecked passes must never launch."
            assert mask_slots == ([2] * (int(flags[1]) + int(flags[2])))
            assert hidden_slots == ([2] * (int(flags[1]) + int(flags[2])))
            assert quality.call_count == len(expected)
            assert mask_check.call_count == int(flags[1])
            assert eye_check.call_count == int(flags[0])
            assert depth_check.call_count == int(flags[2])
            baseline_digest = picker._operation_input_digest("render_snapshot", str(scene), choices, 1)
            for field in ("original_enabled", "mask_enabled", "depth_enabled"):
                changed = copy.deepcopy(choices); changed[field] = not changed[field]
                assert picker._operation_input_digest("render_snapshot", str(scene), changed, 1) != baseline_digest
            if flags[2]:
                # Native reference/proxy metadata changes exact hint resolution,
                # so it must invalidate Depth identity even when path/color are
                # unchanged. Color's historic binding projection omits it.
                changed_hint = copy.deepcopy(choices)
                changed_hint["slot_assignments"][0]["bindings"][0][
                    "reference_file"
                ] = "C:/references/replaced_actor.mb"
                assert picker._operation_input_digest(
                    "render_snapshot", str(scene), changed_hint, 1
                ) != baseline_digest
                video_digest = picker._operation_input_digest(
                    "run_video", str(scene), choices, 1
                )
                assert picker._operation_input_digest(
                    "run_video", str(scene), changed_hint, 1
                ) != video_digest
            normalized = picker._parse_state(stored[0])
            assert [(record["artifact_type"], record["snapshot_batch_uid"]) for record in normalized["snapshots"]] == [(record["artifact_type"], record["snapshot_batch_uid"]) for record in history]
            changed_record = copy.deepcopy(history[-1])
            changed_record["artifact_type"] = "original" if changed_record["artifact_type"] != "original" else "mask"
            try:
                picker._append_snapshot_history_record(normalized, changed_record)
            except ValueError:
                pass
            else:
                raise AssertionError("An existing Snapshot UID changed artifact type.")

        unsupported = dict(base, original_enabled=False, mask_enabled=False, depth_enabled=False, motion_guide_enabled=True)
        try:
            node._create_operation_context("render_snapshot", str(scene), unsupported)
        except ValueError as exc:
            assert "Motion Guide" in str(exc)
        else:
            raise AssertionError("Motion-only Snapshot must give a clear unsupported still-output error.")

        # A failed selected sibling cannot publish a partial batch or replace history.
        prior = copy.deepcopy(stored[0]["snapshots"])
        stored[0].update(original_enabled=True, mask_enabled=True, depth_enabled=False)
        context = node._create_operation_context("render_snapshot", str(scene), stored[0])
        fail_role[0] = "mask"
        cache_before = set(node._snapshot_cache_root(scene).glob("*.png"))
        try:
            node._snapshot_mode(str(scene), 1, context)
        except RuntimeError as exc:
            assert "intentional selected-pass failure" in str(exc)
        else:
            raise AssertionError("A failed selected Snapshot sibling was accepted.")
        assert stored[0]["snapshots"] == prior
        assert set(node._snapshot_cache_root(scene).glob("*.png")) == cache_before
        fail_role[0] = ""
        bad_layer[0] = True
        try:
            node._snapshot_mode(str(scene), 1, context)
        except RuntimeError as exc:
            assert "render-layer capture" in str(exc)
        else:
            raise AssertionError("An authored Original layer image was published as the selected pass.")
        assert stored[0]["snapshots"] == prior
        assert set(node._snapshot_cache_root(scene).glob("*.png")) == cache_before
        bad_layer[0] = False

    # Command transport carries the clicked choices before the state echo arrives.
    stored[0] = copy.deepcopy(base)
    accepted = []
    node._start_ui_operation = lambda action, state: accepted.append((action, copy.deepcopy(state)))
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "render_snapshot", "action_id": "typed-snapshot-command",
        "payload": {"scene_path": str(scene), "snapshot_frame": 145.0,
                    "include_original": True, "include_mask": False, "include_depth": True}})
    assert accepted and picker._snapshot_choice_roles(accepted[-1][1]) == ["original", "depth"]

    # Durable delete terminal states reconcile optimistic frontend tombstones.
    stored[0] = dict(base, snapshots=prior, active_snapshot_uid=prior[-1]["snapshot_uid"], viewport_mode="snapshot")
    stored[0] = picker._parse_state(stored[0])
    node._hmb_pending_operation_id = ""
    node._hmb_active_operation = None
    target = prior[-1]
    node._handle_delete_snapshot_action({"backend_ack_action_id": "delete-removed"}, snapshot_uid=target["snapshot_uid"])
    assert stored[0]["snapshot_delete_results"]["delete-removed"]["status"] == "removed"
    assert target["snapshot_uid"] not in {record["snapshot_uid"] for record in stored[0]["snapshots"]}
    node._handle_delete_snapshot_action({"backend_ack_action_id": "delete-absent"}, snapshot_uid=target["snapshot_uid"])
    assert stored[0]["snapshot_delete_results"]["delete-absent"]["status"] == "absent"
    node._hmb_pending_operation_id = "running"
    keep = stored[0]["snapshots"][0]["snapshot_uid"]
    before = copy.deepcopy(stored[0]["snapshots"])
    node._handle_delete_snapshot_action({"backend_ack_action_id": "delete-rejected"}, snapshot_uid=keep)
    assert stored[0]["snapshot_delete_results"]["delete-rejected"]["status"] == "rejected"
    assert stored[0]["snapshots"] == before

print("HMB selected-pass Snapshot regression: PASS (7 combinations, native path guards/result promotion, frozen choices, typed history, batch failure, delete ACK)")
