from pathlib import Path
import copy
import importlib.util
import json
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")


full_motion_report = {
    "profile": picker.MOTION_GUIDE_PROFILE,
    "appearance_authority": "zero",
    "motion_authority": "derived_decoder_of_video1_only",
    "target_count": 1,
    "targets": [{
        "target_index": 1,
        "face_channels": [{"group": "eyelid"}],
    }],
    "face_semantics": {
        "schema": "hmb-maya-face-semantics",
        "schema_version": 2,
        "channel_source_policy": (
            "final_evaluated_blendshape_weight_raw_value"
        ),
        "controller_policy": (
            "connected_numeric_nurbs_curve_controller_plug_raw_value_provenance_only"
        ),
        "localization_policy": (
            "read_only_blendshape_target_delta_heatmap_then_bounded_fail_closed_surface_completion"
        ),
        "raster_policy": (
            "surface_pinned_brow_eyelid_mouth_jaw_landmarks_only;"
            "raw_nurbs_curve_geometry_never_rendered"
        ),
        "visibility_policy": (
            "front_facing_vertex_normal_plus_camera_ray_first_hit_visible_only"
        ),
        "partial_contour_policy": (
            "defined_face_edge_both_endpoints_front_facing_first_hit_visible"
        ),
        "visibility_opportunity_policy": (
            "target_visible_defined_face_edge_both_endpoints_front_facing_"
            "first_hit_visible_and_minimum_screen_span"
        ),
        "ray_scope": "authored_visible_character_target_meshes",
        "unknown_alias_policy": (
            "raw_alias_and_value_preserved_sidecar_only_no_raster_guess"
        ),
        "target_count": 1,
        "channel_count": 3,
        "driver_count": 3,
        "landmark_count": 165,
        "rasterized_sample_count": 62,
        "curve_geometry_rendered": False,
    },
    "motion_frames": [
        {
            "frame_index": frame_index,
            "maya_frame": 101 + frame_index,
            "targets": [{
                "target_index": 1,
                "face": {
                    "detailed_vertex_paths": [
                        f"|Rig|Face|eyelidShape.vtx[{index}]"
                        for index in range(500)
                    ],
                },
            }],
        }
        for frame_index in range(62)
    ],
}
full_motion_report_before = copy.deepcopy(full_motion_report)

state = picker._default_widget_state()
state.update({
    "active_slot_count": 1,
    "videos": [{
        "video_slot": 1,
        "video_path": "C:/scene/motion.mp4",
        "media_kind": picker.MOTION_GUIDE_MEDIA_KIND,
        "video_role": "maya_motion_guide_companion",
        "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
        "motion_guide_report": full_motion_report,
        "source_fps": 24,
        "decoded_frame_count": 62,
        "start_frame": 101,
        "end_frame": 162,
        "has_maya_frame_range": True,
    }],
})

normalized = picker._parse_state(state)
state_report = normalized["videos"][0]["motion_guide_report"]
assert "motion_frames" not in state_report
assert state_report["motion_frame_count"] == 62
assert state_report["motion_frames_in_sidecar"] is True
assert state_report["appearance_authority"] == "zero"
assert state_report["semantic_groups"] == ["eyelid"]
assert state_report["targets"][0]["semantic_groups"] == ["eyelid"]
assert state_report["targets"][0]["face_channel_count"] == 1
assert "face_channels" not in state_report["targets"][0]
# Compaction must not mutate the full report that is written to the sidecar.
assert full_motion_report == full_motion_report_before
assert len(full_motion_report["motion_frames"]) == 62
assert len(full_motion_report["motion_frames"][0]["targets"][0]["face"]["detailed_vertex_paths"]) == 500

node = picker.HMBVideoPickerLibrary.__new__(picker.HMBVideoPickerLibrary)
payload = node._build_picker_payload(state)
payload_report = payload["videos"][0]["motion_guide_report"]
assert "motion_frames" not in payload_report
assert payload_report["motion_frame_count"] == 62
assert payload_report["semantic_groups"] == ["eyelid"]
assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) < 65536
assert picker._compact_motion_guide_report_for_state(state_report) == state_report


def assert_no_heavy_motion_keys(value):
    if isinstance(value, dict):
        assert not set(value).intersection({
            "motion_frames",
            "face_channels",
            "face_drivers",
            "face_landmarks",
            "face_edges",
            "detailed_vertex_paths",
        })
        for nested in value.values():
            assert_no_heavy_motion_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_heavy_motion_keys(nested)


assert_no_heavy_motion_keys(state_report)
full_prompt_summary = prompt._picker_motion_guide_summary({
    "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
    "motion_guide_report": full_motion_report,
})
compact_prompt_summary = prompt._picker_motion_guide_summary({
    "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
    "motion_guide_report": state_report,
})
assert compact_prompt_summary == full_prompt_summary
assert compact_prompt_summary["semantic_face"] is True
assert compact_prompt_summary["semantic_groups"] == ["eyelid"]

# The asset catalog is not capped at five and duplicate legacy slot numbers are
# migrated into six distinct stable records. Every record must still compact
# the original multi-megabyte report before entering widget state.
collision_state = picker._default_widget_state()
collision_state.update({
    "active_slot_count": 5,
    "videos": [
        {
            "video_slot": 1,
            "video_path": f"C:/scene/motion_{index}.mp4",
            "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
            "motion_guide_report": full_motion_report,
        }
        for index in range(6)
    ],
})
collision_state = picker._parse_state(collision_state)
assert len(collision_state["videos"]) == 6
assert len({item["video_uid"] for item in collision_state["videos"]}) == 6
assert collision_state["slot_recovery_fallbacks"] == []
for collision_item in collision_state["videos"]:
    collision_report = collision_item["motion_guide_report"]
    assert "motion_frames" not in collision_report
    assert "face_channels" not in collision_report["targets"][0]
    assert_no_heavy_motion_keys(collision_report)


dag_details = " | ".join(
    f"|Rig|CTRL_{index}|CTRL_{index}Shape: unsupported depth shape type nurbsCurve"
    for index in range(148)
)
full_depth_error = (
    "Depth shader assignment verification failed for 148 of 333 surface paths: "
    + dag_details
)
assert picker._compact_auxiliary_failure_warning(
    "@video2 Depth",
    full_depth_error,
    language="ko",
) == "Depth 실패: 지원되지 않는 컨트롤 148개"

warning_state = picker._default_widget_state()
warning_state["warnings"] = [
    "Optional Depth artifact failed: " + full_depth_error,
    "Depth 실패: 지원되지 않는 컨트롤 148개",
]
picker._append_activity_log(warning_state, "ERROR", full_depth_error)
warning_state = picker._parse_state(warning_state)
assert len(warning_state["warnings"]) == 1
assert warning_state["warnings"][0] == (
    "Depth 실패: 지원되지 않는 컨트롤 148개"
)
assert len(warning_state["warnings"][0]) <= picker._UI_WARNING_MESSAGE_LIMIT
assert "CTRL_147" not in warning_state["warnings"][0]
assert warning_state["activity_log"][-1]["level"] == "ERROR"
assert len(warning_state["activity_log"][-1]["message"]) <= picker._UI_ACTIVITY_MESSAGE_LIMIT
assert "CTRL_147" not in warning_state["activity_log"][-1]["message"]

with tempfile.TemporaryDirectory() as temporary:
    log_path = Path(temporary) / "picker.log"
    picker._append_full_diagnostic_log(
        log_path,
        "HMB OPTIONAL ARTIFACT ERROR",
        full_depth_error,
    )
    disk_text = log_path.read_text(encoding="utf-8")
    assert "CTRL_147" in disk_text
    assert full_depth_error in disk_text


print(
    "HMB Picker state compaction regression: PASS "
    "(full Motion frames and DAG errors stay on disk; UI/PICKER_OUT remain bounded)"
)
