from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import types

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")


def shader_depth_range_report(frame_values=None) -> dict:
    evaluated_frames = list(frame_values or [101.0 + index for index in range(120)])
    return {
        "profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "space": "camera",
        "source": "object_bbox_camera_depth",
        "assignment_mode": "color_picker_style_shared_gray_material_buckets",
        "depth_update_scope": "per_shape_path_per_output_frame",
        "representative_depth": (
            "median_positive_camera_depth_of_world_bbox_corners"
        ),
        "normalization_policy": "screen_valid_foreground_percentile_bounds",
        "near": 10.5,
        "far": 30.25,
        "camera_near_clip": 0.1,
        "camera_far_clip": 1000.0,
        "camera_near_clip_min": 0.1,
        "camera_near_clip_max": 0.1,
        "camera_far_clip_min": 1000.0,
        "camera_far_clip_max": 1000.0,
        "camera_clip_animated": False,
        "camera_origin_distance": 0.0,
        "camera_clip_is_hard_safety_boundary": True,
        "range_evaluation_scope": "complete_requested_sequence",
        "range_evaluated_frame_count": len(evaluated_frames),
        "shot_range_sample": {
            "evaluation_scope": "complete_requested_sequence",
            "evaluated_frame_count": len(evaluated_frames),
            "evaluated_frames": evaluated_frames,
            "representative_sample_count": 2 * len(evaluated_frames),
            "foreground_representative_sample_count": 2 * len(evaluated_frames),
            "context_representative_sample_count": 0,
            "screen_rejected_representative_sample_count": 0,
            "role_excluded_representative_sample_count": 0,
            "normalization_candidate_shape_path_count": 2,
            "screen_sample_tested_bbox_count": 2 * len(evaluated_frames),
            "screen_sample_visible_bbox_count": 2 * len(evaluated_frames),
            "screen_sample_rejected_bbox_count": 0,
            "bbox_fallback_candidate_count": 0,
            "foreground_near_percentile": 0.01,
            "foreground_far_percentile": 0.99,
            "generic_far_percentile": 0.95,
            "generic_percentile_min_shapes": 20,
            "screen_sample_policy": "deterministic_api_mesh_vertices_and_polygon_centers;bbox_fallback_when_sampling_unavailable",
            "rejection_accounting_policy": "disjoint_normalization_outcomes",
            "screen_vertex_sample_limit": 128,
            "screen_polygon_center_sample_limit": 64,
            "range_candidate_scope": "screen_valid_foreground_actor_shapes",
            "range_basis": "complete_sequence_screen_valid_foreground_representative_percentiles",
            "near_anchor": "effective_screen_valid_foreground_near",
            "fallback_percentile": None,
            "fallback_reason": "",
            "range_extrema_sources": {
                "near": {
                    "frame": evaluated_frames[0],
                    "shape": "|Tenten|NearShape",
                    "root": "|Tenten",
                    "marker": "Red",
                    "role": "foreground",
                    "representative_depth": 10.5,
                    "screen_sample_policy": "api_mesh_vertex_polygon_center_screen_visible",
                    "used_bbox_fallback": False,
                    "screen_inside_sample_count": 4,
                },
                "far": {
                    "frame": evaluated_frames[-1],
                    "shape": "|Tenten|FarShape",
                    "root": "|Tenten",
                    "marker": "Red",
                    "role": "foreground",
                    "representative_depth": 30.25,
                    "screen_sample_policy": "api_mesh_vertex_polygon_center_screen_visible",
                    "used_bbox_fallback": False,
                    "screen_inside_sample_count": 4,
                },
            },
            "binding_range_reports": [{
                "root": "|Tenten",
                "marker": "Red",
                "role": "foreground",
                "shape_path_count": 2,
                "representative_sample_count": 2 * len(evaluated_frames),
                "representative_near": 10.5,
                "representative_far": 30.25,
                "normalization_candidate_sample_count": 2 * len(evaluated_frames),
                "normalization_candidate_near": 10.5,
                "normalization_candidate_far": 30.25,
                "screen_tested_shape_path_count": 2,
                "screen_visible_shape_path_count": 2,
                "screen_rejected_shape_path_count": 0,
                "bbox_fallback_shape_path_count": 0,
                "role_excluded_shape_path_count": 0,
                "screen_sample_count": 2 * len(evaluated_frames),
                "screen_visible_sample_count": 2 * len(evaluated_frames),
                "screen_sample_policy_counts": {
                    "api_mesh_vertex_polygon_center_screen_visible": 2 * len(evaluated_frames),
                },
                "selected_for_normalization": True,
            }],
        },
        "near_color": [0.9, 0.9, 0.9],
        "far_color": [0.0, 0.0, 0.0],
        "output_value_range": [0.0, 0.9],
        "camera_near_safety_margin": 0.1,
        "reserved_output_value_range": [0.9, 1.0],
        "direction": "near_white_far_black",
        "background": "pure_black",
        "temporal_normalization": "fixed_for_complete_sequence",
        "encoding_curve": "normalized_power",
        "contrast_exponent": picker.DEPTH_CONTRAST_EXPONENT,
        "renderable_shape_count": 2,
        "mesh_shape_count": 2,
        "nurbs_surface_shape_count": 0,
        "proxy_preview_recovery": {
            "candidate_shape_count": 0,
            "candidate_path_count": 0,
            "recovered_shape_count": 0,
            "recovered_path_count": 0,
            "recovered_paths": [],
            "source_paths": [],
        },
        "assignment_verification": {
            "shape_path_count": 2,
            "mesh_path_count": 2,
            "nurbs_surface_path_count": 0,
            "verified_shape_path_count": 2,
            "verified_mesh_face_count": 24,
            "rendered_frame_count": len(evaluated_frames),
            "expected_frame_assignment_count": 2 * len(evaluated_frames),
            "verified_frame_assignment_count": 2 * len(evaluated_frames),
        },
        "shader_model": "surfaceShader",
        "grayscale_bucket_count": 256,
        "standard_nodes": ["surfaceShader"],
        "cutout_transparency": {
            "policy": "preserve_authored_material_out_transparency_v1",
            "captured_shape_path_count": 2,
            "alpha_driven_shape_path_count": 1,
            "source_plug_count": 1,
            "verified_shape_path_count": 1,
            "ambiguous_shape_path_count": 0,
            "unsupported_shape_path_count": 0,
        },
        "render_options": {
            "output_transform_disabled": True,
            "multisample_disabled": True,
            "line_aa_disabled": True,
            "ssao_disabled": True,
            "motion_blur_disabled": True,
            "depth_of_field_disabled": True,
            "fog_disabled": True,
        },
    }


def depth_video(path: str, slot: int = 2) -> dict:
    return {
        "video_slot": slot,
        "video_uid": "depth-regression-depth",
        "source_uid": "depth-regression-depth",
        "video_path": path,
        "camera": "|shotCam",
        "markers": [],
        "source_fps": 24.0,
        "output_fps": 24.0,
        "output_width": 1280,
        "output_height": 720,
        "source_frame_count": 120,
        "output_frame_count": 120,
        "decoded_frame_count": 120,
        "source_duration_seconds": 5.0,
        "output_duration_seconds": 5.0,
        "start_frame": 101.0,
        "end_frame": 220.0,
        "has_maya_frame_range": True,
        "media_kind": picker.DEPTH_MEDIA_KIND,
        "generation_role": "depth",
        "video_role": "maya_depth_companion",
        "source_type_hint": picker.DEPTH_SOURCE_TYPE,
        "control_role_hint": picker.DEPTH_CONTROL_ROLE,
        "companion_of_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "source_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "companion_video_uid": "depth-regression-mask",
        "source_video_uid": "depth-regression-mask",
        "pair_run_id": "depth-regression-pair-id",
        "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "depth_range_report": shader_depth_range_report(),
    }


# Shader Depth authority is deliberately pinned. v1-v6 remain cleanup-only;
# any future semantic change requires an explicit contract migration.
assert picker.DEPTH_PLAYBLAST_PROFILE == "hmb_camera_space_depth_v7"
assert picker.LEGACY_DEPTH_PLAYBLAST_PROFILES == frozenset({
    "hmb_camera_space_depth_v1",
    "hmb_camera_space_depth_v2",
    "hmb_camera_space_depth_v3",
    "hmb_camera_space_depth_v4",
    "hmb_camera_space_depth_v5",
    "hmb_camera_space_depth_v6",
})
assert picker.DEPTH_CONTRAST_EXPONENT == 1.0


# Default, parse, merge, and operation-digest contracts.
default_state = picker._default_widget_state()
assert default_state["depth_enabled"] is False
assert default_state["active_slot_count"] == 1

parsed_depth = picker._parse_state({
    **default_state,
    "depth_enabled": True,
    "active_slot_count": 2,
    "selected_video_slot": 2,
})
assert parsed_depth["depth_enabled"] is True
assert parsed_depth["active_slot_count"] == 1
assert picker._parse_state(parsed_depth) == parsed_depth

authoritative = picker._parse_state({
    **default_state,
    "status": "PROCESSING",
    "message": "backend-owned",
    "state_revision": 12,
    "active_slot_count": 2,
    "depth_enabled": False,
})
incoming = picker._parse_state({
    **authoritative,
    "status": "READY",
    "message": "stale widget text",
    "state_revision": 13,
    "depth_enabled": True,
})
merged = picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, incoming)
assert merged["depth_enabled"] is True
assert merged["status"] == "PROCESSING"
assert merged["message"] == "backend-owned"
assert merged["state_revision"] == 13

with tempfile.TemporaryDirectory() as temp_dir:
    scene = Path(temp_dir) / "depth_digest.mb"
    scene.write_bytes(b"Maya scene digest fixture")
    digest_state = picker._parse_state({
        **default_state,
        "scene_path": str(scene),
        "scene_request_path": str(scene),
        "selected_camera": "|shotCam",
        "active_slot_count": 2,
        "selected_video_slot": 1,
        "slot_assignments": [
            {
                "video_slot": 1,
                "bindings": [{
                    "group_name": "Hero",
                    "full_dag_path": "|Hero",
                    "maya_uuid": "hero-uuid",
                    "color": "Red",
                    "enabled": True,
                    "video_slot": 1,
                    "picker_order": 1,
                }],
            },
            {"video_slot": 2, "bindings": []},
        ],
    })
    color_only_digest = picker._operation_input_digest(
        "run_video", scene, digest_state, 1
    )
    paired_state = copy.deepcopy(digest_state)
    paired_state["depth_enabled"] = True
    paired_digest = picker._operation_input_digest(
        "run_video", scene, paired_state, 1
    )
    assert paired_digest != color_only_digest
    assert (
        picker._operation_input_digest("run_video", scene, paired_state, 2)
        == paired_digest
    )
    assert (
        picker._operation_input_digest("read_scene", scene, paired_state, 1)
        == picker._operation_input_digest("read_scene", scene, digest_state, 1)
    )


# PICKER_OUT schema v5 carries stable-UID typed generated companions in the
# user's selected catalog order.
payload_state = picker._parse_state({
    **default_state,
    "scene_path": "C:/show/shot/depth_contract.mb",
    "active_slot_count": 2,
    "selected_video_slot": 1,
    "depth_enabled": True,
    "pair_run_id": "depth-regression-pair-id",
    "videos": [
        {
            "video_slot": 1,
            "video_uid": "depth-regression-mask",
            "source_uid": "depth-regression-mask",
            "video_path": "C:/show/shot/depth_contract_playblast_1.mp4",
            "generation_role": "mask",
            "media_kind": picker.MASK_MEDIA_KIND,
            "camera": "|shotCam",
            "markers": [{
                "color": "Red",
                "asset_id": "Hero",
                "group_name": "Hero",
                "subject_root": "|Hero",
                "full_dag_path": "|Hero",
                "video_slot": 1,
                "picker_order": 1,
            }],
            "source_fps": 24.0,
            "output_fps": 24.0,
            "output_width": 1280,
            "output_height": 720,
            "source_frame_count": 120,
            "output_frame_count": 120,
            "decoded_frame_count": 120,
            "source_duration_seconds": 5.0,
            "output_duration_seconds": 5.0,
            "start_frame": 101.0,
            "end_frame": 220.0,
            "has_maya_frame_range": True,
            "pair_run_id": "depth-regression-pair-id",
        },
        depth_video("C:/show/shot/depth_contract_depth_playblast_2.mp4"),
    ],
})
payload_builder = object.__new__(picker.HMBVideoPickerLibrary)
payload = payload_builder._build_picker_payload(payload_state)
assert payload["schema"] == "hmb-prompt-library-picker-binding"
assert payload["schema_version"] == 5
assert [item["video_slot"] for item in payload["videos"]] == [1, 2]
assert payload["ordered_video_uids"] == [
    "depth-regression-mask",
    "depth-regression-depth",
]
assert [item["video_slot"] for item in payload["markers"]] == [1]

depth_payload = payload["videos"][1]
assert depth_payload["video_slot"] == 2
assert depth_payload["markers"] == []
assert depth_payload["media_kind"] == picker.DEPTH_MEDIA_KIND
assert depth_payload["generation_role"] == "depth"
assert depth_payload["video_role"] == "maya_depth_companion"
assert depth_payload["source_type_hint"] == picker.DEPTH_SOURCE_TYPE
assert depth_payload["control_role_hint"] == picker.DEPTH_CONTROL_ROLE
assert depth_payload["companion_of_video_slot"] == 1
assert depth_payload["source_video_slot"] == 1
assert depth_payload["companion_video_uid"] == "depth-regression-mask"
assert depth_payload["source_video_uid"] == "depth-regression-mask"
assert depth_payload["pair_run_id"] == "depth-regression-pair-id"
assert payload["videos"][0]["pair_run_id"] == depth_payload["pair_run_id"]
assert depth_payload["depth_profile"] == picker.DEPTH_PLAYBLAST_PROFILE
assert depth_payload["depth_range_report"] == shader_depth_range_report()
assert depth_payload["fps"] == payload["videos"][0]["fps"] == 24.0
assert depth_payload["frame_count"] == payload["videos"][0]["frame_count"] == 120
assert (depth_payload["width"], depth_payload["height"]) == (1280, 720)
assert payload_builder._build_picker_payload(payload_state)["run_id"] == payload["run_id"]
assert prompt._picker_video_is_generated_depth(
    depth_payload,
    2,
    "depth-regression-pair-id",
)
assert not prompt._picker_video_is_generated_depth(
    {**depth_payload, "pair_run_id": "stale-pair"},
    2,
    "depth-regression-pair-id",
)
assert not prompt._picker_video_is_generated_depth(
    depth_payload,
    2,
    "",
)
assert not prompt._picker_video_is_generated_depth(
    {key: value for key, value in depth_payload.items() if key != "pair_run_id"},
    2,
    "",
), "Generated Depth must never be recognized without a non-empty pair identity."


def prompt_payload_with_pairs(
    primary_pair_run_id: str | None,
    depth_pair_run_id: str | None,
    run_id: str,
) -> dict:
    value = copy.deepcopy(payload)
    value["run_id"] = run_id
    for item, pair_run_id in zip(
        value["videos"],
        (primary_pair_run_id, depth_pair_run_id),
    ):
        if pair_run_id is None:
            item.pop("pair_run_id", None)
        else:
            item["pair_run_id"] = pair_run_id
    return value


def assert_auto_depth_preserved_as_independent_media(
    state: dict,
    expected_main_type: str = "Select Video Main Type",
) -> None:
    item = state["videos"][1]
    assert item["label"] == "depth_contract_depth_playblast_2"
    assert item["present"] is True
    assert item["video_main_type"] == expected_main_type
    assert item["video_sub_type"] == ""
    assert item["source_type"] == "Role Required / Select Video Type"
    assert item["custom_source_type"] == ""
    assert item["control_role"] == ""
    assert item["custom_control_role"] == ""
    assert item["picker_auto_label"] == "depth_contract_depth_playblast_2"
    assert item["picker_auto_depth"] == {}


def assert_removed_picker_depth_source_released(state: dict) -> None:
    item = state["videos"][1]
    assert item["label"] == ""
    # An unstructured empty input is not an authoritative catalog deletion.
    # Release typed bundle authority, but preserve the stable UID row as an
    # independently usable/manual reference until v5 explicitly selects zero.
    assert item["present"] is True
    assert item["manual"] is True
    assert item["video_uid"] == "depth-regression-depth"
    assert item["source_type"] == "Role Required / Select Video Type"
    assert item["custom_source_type"] == ""
    assert item["control_role"] == ""
    assert item["custom_control_role"] == ""
    assert item["picker_auto_label"] == ""
    assert item["picker_auto_depth"] == {}


def prompt_payload_without_depth(run_id: str) -> dict:
    value = copy.deepcopy(valid_prompt_payload)
    value["run_id"] = run_id
    value["active_slot_count"] = 1
    value["selected_video_count"] = 1
    value["ordered_video_uids"] = ["depth-regression-mask"]
    value["selection_id"] = f"selection-{run_id}"
    value["videos"] = [value["videos"][0]]
    value["markers"] = [
        item
        for item in value.get("markers", [])
        if int(item.get("video_slot") or 1) == 1
    ]
    value["frame_metadata"] = [
        item
        for item in value.get("frame_metadata", [])
        if int(str(item.get("video_slot") or "1").replace("@video", "")) == 1
    ]
    return value


# Matching pair identity adds bundle confidence. A later stale, blank, pairless,
# empty, disconnected, or non-Maya payload releases only that confidence; the
# already supplied Depth media remains independently usable.
valid_prompt_payload = prompt_payload_with_pairs(
    "depth-regression-pair-id",
    "depth-regression-pair-id",
    "prompt-pair-valid",
)
valid_prompt_state = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    valid_prompt_payload,
    connected=True,
)
valid_prompt_depth = valid_prompt_state["videos"][1]
assert valid_prompt_depth["present"] is True
assert valid_prompt_depth["video_main_type"] == "Maya Preview / Playblast"
assert valid_prompt_depth["video_sub_type"] == "Depth"
assert valid_prompt_depth["source_type"] == "Depth / Spatial Reference"
assert (
    valid_prompt_depth["control_role"]
    == "Spatial Alignment Verification Only"
)
assert (
    valid_prompt_depth["picker_auto_depth"]["pair_run_id"]
    == "depth-regression-pair-id"
)

normalized_malformed_provenance = prompt._normalize_picker_auto_depth({
    "pair_run_id": "  normalized-pair  ",
    "ignored_top_level": "drop",
    "fields": {
        "present": {
            "assigned": "false",
            "previous": "true",
            "ignored": "drop",
        },
        "label": {
            "assigned": " generated-depth ",
            "previous": " manual-depth ",
        },
        "forbidden_field": {
            "assigned": "unsafe",
            "previous": "unsafe",
        },
        "source_type": [],
    },
})
assert normalized_malformed_provenance == {
    "pair_run_id": "normalized-pair",
    "fields": {
        "label": {
            "assigned": "generated-depth",
            "previous": "manual-depth",
        },
        "present": {
            "assigned": False,
            "previous": True,
        },
    },
}
assert prompt._normalize_picker_auto_depth([]) == {}
assert prompt._normalize_picker_auto_depth({"fields": []}) == {}

mismatched_prompt_state = prompt._apply_picker_payload(
    copy.deepcopy(valid_prompt_state),
    prompt_payload_with_pairs(
        "depth-regression-pair-id",
        "stale-depth-pair-id",
        "prompt-pair-mismatch",
    ),
    connected=True,
)
assert_auto_depth_preserved_as_independent_media(mismatched_prompt_state)

blank_prompt_state = prompt._apply_picker_payload(
    copy.deepcopy(valid_prompt_state),
    prompt_payload_with_pairs("", "", "prompt-pair-blank"),
    connected=True,
)
assert_auto_depth_preserved_as_independent_media(blank_prompt_state)

pairless_prompt_state = prompt._apply_picker_payload(
    copy.deepcopy(valid_prompt_state),
    prompt_payload_with_pairs(None, None, "prompt-pair-missing"),
    connected=True,
)
assert_auto_depth_preserved_as_independent_media(pairless_prompt_state)

empty_connected_prompt_state = prompt._apply_picker_payload(
    copy.deepcopy(valid_prompt_state),
    {},
    connected=True,
)
assert_removed_picker_depth_source_released(empty_connected_prompt_state)

disconnected_prompt_state = prompt._apply_picker_payload(
    copy.deepcopy(valid_prompt_state),
    {},
    connected=False,
)
# A real edge disconnect restores the complete pre-Picker Prompt snapshot.
# The independently usable UID row above is retained only while the Picker
# edge still exists but temporarily publishes no structured media.
assert len(disconnected_prompt_state["videos"]) == 1
assert disconnected_prompt_state["videos"][0]["present"] is False
assert disconnected_prompt_state["videos"][0]["video_uid"] == ""
assert disconnected_prompt_state["picker"]["enabled"] is False

non_maya_prompt_payload = copy.deepcopy(valid_prompt_payload)
non_maya_prompt_payload["mode"] = "external_video"
non_maya_prompt_state = prompt._apply_picker_payload(
    copy.deepcopy(valid_prompt_state),
    non_maya_prompt_payload,
    connected=True,
)
assert non_maya_prompt_state["videos"] == valid_prompt_state["videos"]
# A foreign-mode object is not allowed to overwrite structured Picker state,
# but the no-loss input contract retains it as ordinary user intent.
assert any(
    item.get("source") == "PICKER_IN"
    and "foreign mode or schema" in item.get("reason", "")
    for item in non_maya_prompt_state.get("source_intent_fallbacks", [])
)
non_maya_lines = prompt._build_data_only_prompt_package(
    non_maya_prompt_state
).splitlines()
assert len(non_maya_lines) == 7
assert json.loads(
    non_maya_lines[non_maya_lines.index("USER DESCRIPTION DATA (JSON):") + 1]
) == {}

# Legacy local slot suppression cannot override a UID-managed Picker order.
# Selection/deletion is authored in the catalog, so reconnecting the same
# authoritative selection restores the typed row without renumbering identity.
deleted_depth_source_state = copy.deepcopy(valid_prompt_state)
deleted_depth_source_state["videos"][1] = prompt._default_video_item(2)
deleted_depth_source_state["videos"][1]["manual"] = True
deleted_depth_source_state["picker"]["slot_suppressions"] = {
    "2": prompt._picker_payload_id(valid_prompt_payload),
}
deleted_depth_prompt_state = prompt._apply_picker_payload(
    deleted_depth_source_state,
    valid_prompt_payload,
    connected=True,
)
assert deleted_depth_prompt_state["videos"][1]["video_uid"] == (
    "depth-regression-depth"
)
assert deleted_depth_prompt_state["videos"][1]["source_type"] == (
    "Depth / Spatial Reference"
)
assert deleted_depth_prompt_state["videos"][1]["picker_auto_depth"]
assert deleted_depth_prompt_state["videos"][0]["present"] is True
assert deleted_depth_prompt_state["picker"]["run_id"] == prompt._picker_payload_id(
    valid_prompt_payload
)

slot_missing_prompt_state = prompt._apply_picker_payload(
    copy.deepcopy(valid_prompt_state),
    prompt_payload_without_depth("prompt-color-only-slot-missing"),
    connected=True,
)
assert len(slot_missing_prompt_state["videos"]) == 1
assert slot_missing_prompt_state["videos"][0]["video_uid"] == (
    "depth-regression-mask"
)
assert slot_missing_prompt_state["picker"]["selected_video_count"] == 1
assert slot_missing_prompt_state["picker"]["ordered_video_uids"] == [
    "depth-regression-mask"
]
assert any(
    item.get("video_uid") == "depth-regression-depth"
    for item in slot_missing_prompt_state["picker"]["dormant_video_rows"]
)


# Saved states from the release immediately before provenance support may keep
# readable media, but their legacy role fields are deliberately not migrated.
legacy_auto_state = copy.deepcopy(valid_prompt_state)
legacy_auto_state["videos"][1].pop("picker_auto_depth", None)
legacy_auto_state["videos"][1].pop("video_main_type", None)
legacy_auto_state["videos"][1].pop("video_sub_type", None)
legacy_auto_state["videos"][1].pop("picker_auto_video_main_type", None)
legacy_auto_state["videos"][1].pop("picker_auto_video_sub_type", None)
legacy_invalid_state = prompt._apply_picker_payload(
    legacy_auto_state,
    prompt_payload_with_pairs(
        "depth-regression-pair-id",
        "stale-depth-pair-id",
        "prompt-pair-legacy-fingerprint",
    ),
    connected=True,
)
assert_auto_depth_preserved_as_independent_media(
    legacy_invalid_state,
    expected_main_type="",
)
legacy_invalid_state["videos"][1]["label"] = "manual-new-label"
legacy_invalid_state["videos"][1]["present"] = True
legacy_reactivated_prompt = prompt._build_data_only_prompt_package(
    legacy_invalid_state
)
legacy_lines = legacy_reactivated_prompt.splitlines()
legacy_job = json.loads(
    legacy_lines[legacy_lines.index("HMB JOB DATA (JSON):") + 1]
)
legacy_depth = legacy_job["videos"][1]
assert legacy_depth["source_type"] == ""
assert legacy_depth["control_role"] == ""


# Manual values that existed before Picker temporarily classified @video2 as
# generated Depth are restored after pair invalidation.
manual_prompt_base = prompt._default_widget_state()
manual_prompt_base["videos"] = [
    prompt._default_video_item(1),
    {
        **prompt._default_video_item(2),
        "label": "manual-auxiliary",
        "present": True,
        "video_main_type": "Custom / Context",
        "video_sub_type": "Custom",
        "custom_source_type": "Manual source type",
        "custom_control_role": "Manual control role",
        "manual": True,
    },
]
manual_then_valid = prompt._apply_picker_payload(
    manual_prompt_base,
    valid_prompt_payload,
    connected=True,
)
manual_then_mismatch = prompt._apply_picker_payload(
    manual_then_valid,
    prompt_payload_with_pairs(
        "depth-regression-pair-id",
        "stale-depth-pair-id",
        "prompt-pair-manual-restore",
    ),
    connected=True,
)
restored_manual_depth = manual_then_mismatch["videos"][1]
assert restored_manual_depth["label"] == "manual-auxiliary"
assert restored_manual_depth["present"] is True
assert restored_manual_depth["source_type"] == "Custom"
assert restored_manual_depth["custom_source_type"] == "Manual source type"
assert restored_manual_depth["control_role"] == "Custom Role"
assert restored_manual_depth["custom_control_role"] == "Manual control role"
assert restored_manual_depth["picker_auto_depth"] == {}


def assert_manual_depth_restored(state: dict) -> None:
    item = state["videos"][1]
    assert item["label"] == "manual-auxiliary"
    assert item["present"] is True
    assert item["source_type"] == "Custom"
    assert item["custom_source_type"] == "Manual source type"
    assert item["control_role"] == "Custom Role"
    assert item["custom_control_role"] == "Manual control role"
    assert item["picker_auto_depth"] == {}


manual_disconnect = prompt._apply_picker_payload(
    copy.deepcopy(manual_then_valid),
    {},
    connected=False,
)
assert_manual_depth_restored(manual_disconnect)

manual_non_maya = prompt._apply_picker_payload(
    copy.deepcopy(manual_then_valid),
    non_maya_prompt_payload,
    connected=True,
)
assert manual_non_maya["videos"] == manual_then_valid["videos"]
assert any(
    item.get("source") == "PICKER_IN"
    and "foreign mode or schema" in item.get("reason", "")
    for item in manual_non_maya.get("source_intent_fallbacks", [])
)
manual_non_maya_lines = prompt._build_data_only_prompt_package(
    manual_non_maya
).splitlines()
assert json.loads(
    manual_non_maya_lines[
        manual_non_maya_lines.index("USER DESCRIPTION DATA (JSON):") + 1
    ]
) == {}

manual_deleted_source = copy.deepcopy(manual_then_valid)
manual_deleted_source["videos"][1] = prompt._default_video_item(2)
manual_deleted_source["videos"][1]["manual"] = True
manual_deleted_source["picker"]["slot_suppressions"] = {
    "2": prompt._picker_payload_id(valid_prompt_payload),
}
manual_deleted = prompt._apply_picker_payload(
    manual_deleted_source,
    valid_prompt_payload,
    connected=True,
)
assert manual_deleted["videos"][1]["video_uid"] == "depth-regression-depth"
assert manual_deleted["videos"][1]["source_type"] == (
    "Depth / Spatial Reference"
)
assert manual_deleted["videos"][1]["picker_auto_depth"]
assert manual_deleted["videos"][0]["present"] is True

manual_slot_missing = prompt._apply_picker_payload(
    copy.deepcopy(manual_then_valid),
    prompt_payload_without_depth("prompt-manual-color-only-slot-missing"),
    connected=True,
)
assert len(manual_slot_missing["videos"]) == 1
assert manual_slot_missing["videos"][0]["video_uid"] == (
    "depth-regression-mask"
)
dormant_manual_depth = next(
    item
    for item in manual_slot_missing["picker"]["dormant_video_rows"]
    if item.get("video_uid") == "depth-regression-depth"
)
assert dormant_manual_depth["picker_auto_depth"]["fields"]["label"][
    "previous"
] == "manual-auxiliary"
assert dormant_manual_depth["picker_auto_depth"]["fields"]["source_type"][
    "previous"
] == "Custom"


# A manual edit made while a valid pair is active supersedes Picker ownership
# and is not cleared by the invalidating payload.
manual_override_state = copy.deepcopy(valid_prompt_state)
manual_override_depth = manual_override_state["videos"][1]
manual_override_depth.update({
    "label": "user-edited-depth",
    "present": True,
    "video_main_type": "Motion Reference",
    "video_sub_type": "Local Motion",
    "custom_source_type": "User source note",
    "custom_control_role": "User role note",
})
manual_override_result = prompt._apply_picker_payload(
    manual_override_state,
    prompt_payload_with_pairs(
        "depth-regression-pair-id",
        "stale-depth-pair-id",
        "prompt-pair-user-override",
    ),
    connected=True,
)
preserved_override = manual_override_result["videos"][1]
assert preserved_override["label"] == "user-edited-depth"
assert preserved_override["present"] is True
assert preserved_override["source_type"] == "Motion Reference"
assert preserved_override["custom_source_type"] == "User source note"
assert preserved_override["control_role"] == "Local Motion Detail Only"
assert preserved_override["custom_control_role"] == "User role note"
assert preserved_override["picker_auto_depth"] == {}


# Publishing a new Mask appends one immutable catalog asset. Existing catalog
# rows (including a validated typed Depth) and Maya authoring metadata are not
# replaced, renumbered, or cleared.
fixture_pair_run_id = "paired-regression-run-id"
publish_state = picker._parse_state({
    **default_state,
    "active_slot_count": 2,
    "selected_video_slot": 1,
    "depth_enabled": True,
    "pair_run_id": fixture_pair_run_id,
    "video_path": "C:/show/shot/new_color.mp4",
    "video_url": "file:///C:/show/shot/new_color.mp4",
    "camera": "|shotCam",
    "markers": [{
        "color": "Red",
        "asset_id": "Hero",
        "group_name": "Hero",
        "subject_root": "|Hero",
        "full_dag_path": "|Hero",
        "video_slot": 1,
        "picker_order": 1,
    }],
    "source_fps": 24.0,
    "output_fps": 24.0,
    "output_width": 1280,
    "output_height": 720,
    "source_frame_count": 120,
    "output_frame_count": 120,
    "decoded_frame_count": 120,
    "source_duration_seconds": 5.0,
    "output_duration_seconds": 5.0,
    "start_frame": 101.0,
    "end_frame": 220.0,
    "has_maya_frame_range": True,
    "slot_assignments": [
        {
            "video_slot": 1,
            "bindings": [{
                "group_name": "Hero",
                "full_dag_path": "|Hero",
                "maya_uuid": "hero-uuid",
                "color": "Red",
                "enabled": True,
                "video_slot": 1,
                "picker_order": 1,
            }],
        },
        {
            "video_slot": 2,
            "bindings": [{
                "group_name": "StaleDepthBinding",
                "full_dag_path": "|StaleDepthBinding",
                "maya_uuid": "stale-depth-uuid",
                "color": "Green",
                "enabled": True,
                "video_slot": 2,
                "picker_order": 1,
            }],
        },
    ],
    "slot_visibility": [
        {"video_slot": 1, "hidden_paths": ["|KeepColorHidden"]},
        {"video_slot": 2, "hidden_paths": ["|StaleDepthHidden"]},
    ],
    "snapshot_active": True,
    "snapshot_frame": 160.0,
    "snapshot_video_slot": 2,
    "snapshot_data_uri": "data:image/png;base64,AA==",
    "snapshot_path": "C:/show/shot/stale-depth-snapshot.png",
    "snapshots": [
        {
            "video_slot": 1,
            "frame": 150.0,
            "data_uri": "data:image/png;base64,AQ==",
            "path": "C:/show/shot/keep-color-snapshot.png",
        },
        {
            "video_slot": 2,
            "frame": 160.0,
            "data_uri": "data:image/png;base64,AA==",
            "path": "C:/show/shot/stale-depth-snapshot.png",
        },
    ],
    "videos": [
        {
            "video_slot": 1,
            "video_path": "C:/show/shot/stale_color.mp4",
            "markers": [],
        },
        {
            **depth_video("C:/show/shot/generated_depth.mp4"),
            "pair_run_id": fixture_pair_run_id,
        },
    ],
})
captured_state = {}
publish_node = object.__new__(picker.HMBVideoPickerLibrary)
publish_node._write_state = lambda state: captured_state.update(
    {"value": copy.deepcopy(state)}
)
publish_node._sync_outputs_from_state = lambda state: json.dumps(
    {"video_slots": [item["video_slot"] for item in state["videos"]]}
)
publish_result = publish_node._publish_outputs(publish_state, 1)
assert json.loads(publish_result)["video_slots"] == [1, 2, 3]
published = captured_state["value"]
assert [item["video_slot"] for item in published["videos"]] == [1, 2, 3]
published_color, published_depth, published_mask = published["videos"]
assert published_color["video_path"] == "C:/show/shot/stale_color.mp4"
assert published_depth["video_path"] == "C:/show/shot/generated_depth.mp4"
assert published_depth["markers"] == []
assert published_depth["media_kind"] == picker.DEPTH_MEDIA_KIND
assert published_depth["companion_of_video_slot"] == 1
assert published_depth["source_video_slot"] == 1
assert published_depth["depth_profile"] == picker.DEPTH_PLAYBLAST_PROFILE
assert published_depth["depth_range_report"] == shader_depth_range_report()
pair_run_id = str(published.get("pair_run_id") or "")
assert pair_run_id == fixture_pair_run_id
assert published_depth["pair_run_id"] == pair_run_id
assert published_mask["video_path"] == "C:/show/shot/new_color.mp4"
assert published_mask["markers"][0]["color"] == "Red"
assert published_mask["generation_role"] == "mask"
assert published_mask["media_kind"] == picker.MASK_MEDIA_KIND
assert published_mask["pair_run_id"] == pair_run_id
assert len({item["video_uid"] for item in published["videos"]}) == 3

assignments_by_slot = {
    int(item["video_slot"]): item["bindings"]
    for item in published["slot_assignments"]
}
visibility_by_slot = {
    int(item["video_slot"]): item["hidden_paths"]
    for item in published["slot_visibility"]
}
assert assignments_by_slot[1][0]["group_name"] == "Hero"
assert assignments_by_slot[2][0]["group_name"] == "StaleDepthBinding"
assert visibility_by_slot[1] == ["|KeepColorHidden"]
assert visibility_by_slot[2] == ["|StaleDepthHidden"]
assert [item["video_slot"] for item in published["snapshots"]] == [1, 2]
# A successful Generate keeps immutable Snapshot history and its navigation
# pointer, but returns the shared viewport to Video mode.
assert published["viewport_mode"] == "video"
assert published["snapshot_active"] is False
assert published["active_snapshot_uid"] == published["snapshots"][-1]["snapshot_uid"]
assert published["snapshot_video_slot"] == 2
# Snapshot history retains its stable UID/path/content hash without embedding
# heavyweight PNG bytes back into serialized Picker state.
assert published["snapshot_data_uri"] == ""
assert published["snapshot_sha256"] == published["snapshots"][-1]["sha256"]
assert published["snapshot_path"].endswith("/stale-depth-snapshot.png")
published_payload = publish_node._build_picker_payload(published)
assert published_payload["schema_version"] == 5
assert published_payload["videos"][1]["markers"] == []
assert published_payload["videos"][1]["media_kind"] == picker.DEPTH_MEDIA_KIND
assert published_payload["videos"][1]["pair_run_id"] == pair_run_id
assert published_payload["videos"][2]["pair_run_id"] == pair_run_id
maya_mode_source = inspect.getsource(picker.HMBVideoPickerLibrary._maya_mode)
assert "bundle_run_id = (" in maya_mode_source
assert "pair_run_id = bundle_run_id if depth_succeeded else \"\"" in maya_mode_source
assert maya_mode_source.count('"pair_run_id": pair_run_id') >= 4


# A later Mask-only publish appends again and does not delete or overwrite the
# existing generated companion.
color_only_state = copy.deepcopy(publish_state)
color_only_state["depth_enabled"] = False
color_only_state["pair_run_id"] = ""
color_only_state["video_path"] = "C:/show/shot/color_only_new.mp4"
color_only_state["videos"][0]["video_path"] = "C:/show/shot/color_only_old.mp4"
color_only_state["videos"][1] = depth_video(
    "C:/show/shot/stale_generated_depth.mp4"
)
color_only_state["videos"][1]["depth_profile"] = "hmb_camera_space_depth_v1"
color_only_state["videos"][1]["depth_range_report"] = {
    "space": "camera",
    "source": "samplerInfo.pointCameraZ",
    "normalization_policy": "sampled_shot_camera_bounds",
    "encoding_curve": "normalized_power",
    "contrast_exponent": 0.25,
}
# Selection is Shot-local and UID-authored. Explicitly leave the retained
# legacy Depth asset out of this Shot's ordered selected subset.
color_only_state["picker_shots"][0]["selected_video_uids"] = [
    color_only_state["videos"][0]["video_uid"]
]
assert picker._is_generated_depth_video_item(color_only_state["videos"][1])
color_only_captured = {}
color_only_node = object.__new__(picker.HMBVideoPickerLibrary)
color_only_node._write_state = lambda state: color_only_captured.update(
    {"value": copy.deepcopy(state)}
)
color_only_node._sync_outputs_from_state = lambda state: json.dumps(
    {"video_slots": [item["video_slot"] for item in state["videos"]]}
)
color_only_result = color_only_node._publish_outputs(color_only_state, 1)
assert json.loads(color_only_result)["video_slots"] == [1, 0, 2]
color_only_published = color_only_captured["value"]
assert len(color_only_published["videos"]) == 3
assert color_only_published["videos"][0]["video_path"].endswith(
    "/color_only_old.mp4"
)
assert color_only_published["videos"][2]["video_path"].endswith(
    "/color_only_new.mp4"
)
assert color_only_published["videos"][1]["video_path"].endswith(
    "/stale_generated_depth.mp4"
)
# The old Depth remains in the catalog but was not selected in this fixture;
# append must not silently reactivate or positionally bind it to the new Mask.
assert color_only_published["videos"][1]["selected"] is False
assert color_only_published["videos"][1]["selection_order"] == 0
assert color_only_published["videos"][1]["video_slot"] == 0
assert [
    item["video_uid"]
    for item in color_only_node._build_picker_payload(color_only_published)[
        "videos"
    ]
] == [
    color_only_published["videos"][0]["video_uid"],
    color_only_published["videos"][2]["video_uid"],
]
assert not color_only_published.get("pair_run_id")


# A manually supplied @video2 is not a generated companion and must remain
# untouched by a Color-only @video1 generation.
manual_video2 = {
    "video_slot": 2,
    "video_uid": "manual-preserve-auxiliary",
    "source_uid": "manual-preserve-auxiliary",
    "video_path": "C:/show/shot/manual_depth_or_auxiliary.mp4",
    "camera": "",
    "markers": [],
    "source_fps": 24.0,
    "output_fps": 24.0,
    "output_width": 1280,
    "output_height": 720,
    "source_frame_count": 120,
    "output_frame_count": 120,
    "decoded_frame_count": 120,
    "source_duration_seconds": 5.0,
    "output_duration_seconds": 5.0,
    "start_frame": 101.0,
    "end_frame": 220.0,
    "has_maya_frame_range": True,
}
manual_state = copy.deepcopy(publish_state)
manual_state["depth_enabled"] = False
manual_state["pair_run_id"] = ""
manual_state["video_path"] = "C:/show/shot/manual-preserve-new-color.mp4"
manual_state["videos"] = [
    {
        "video_slot": 1,
        "video_uid": "manual-preserve-color",
        "source_uid": "manual-preserve-color",
        "video_path": "C:/show/shot/manual-preserve-old-color.mp4",
        "markers": [],
    },
    manual_video2,
]
manual_state["picker_shots"][0]["video_asset_uids"] = [
    "manual-preserve-color",
    "manual-preserve-auxiliary",
]
manual_state["picker_shots"][0]["selected_video_uids"] = [
    "manual-preserve-color",
    "manual-preserve-auxiliary",
]
manual_state["picker_shots"][0]["preview_video_uid"] = (
    "manual-preserve-color"
)
manual_captured = {}
manual_node = object.__new__(picker.HMBVideoPickerLibrary)
manual_node._write_state = lambda state: manual_captured.update(
    {"value": copy.deepcopy(state)}
)
manual_node._sync_outputs_from_state = lambda state: json.dumps(
    {"video_slots": [item["video_slot"] for item in state["videos"]]}
)
manual_result = manual_node._publish_outputs(manual_state, 1)
assert json.loads(manual_result)["video_slots"] == [1, 2, 3]
manual_published = manual_captured["value"]
assert manual_published["videos"][1]["video_path"].endswith(
    "/manual_depth_or_auxiliary.mp4"
)
assert not manual_published["videos"][1].get("media_kind")
assert manual_published["videos"][2]["video_path"].endswith(
    "/manual-preserve-new-color.mp4"
)


# The Picker must fail closed on the Maya shader Depth v7 contract before it
# labels or encodes @video2 as a valid Depth companion.  These tests keep a
# valid `result` while corrupting the sidecar so a runner result cannot mask a
# stale, malformed, or semantically incompatible sidecar.
validate_depth = getattr(picker, "_validate_depth_companion_inputs", None)
assert callable(validate_depth), (
    "HMBVideoPickerLibrary must expose _validate_depth_companion_inputs() so "
    "Depth schema, timing, frame-map, and raster validation are one testable "
    "fail-closed boundary."
)


def assert_depth_invalid(
    label: str,
    *,
    result: dict,
    color_sidecar: dict,
    depth_sidecar: dict,
    color_frame_paths: list[Path],
    depth_frame_paths: list[Path],
) -> None:
    try:
        validate_depth(
            result=result,
            color_sidecar=color_sidecar,
            depth_sidecar=depth_sidecar,
            color_frame_paths=color_frame_paths,
            depth_frame_paths=depth_frame_paths,
            expected_frame_count=2,
            expected_fps=24.0,
            expected_start_frame=101.0,
            expected_end_frame=102.0,
            expected_width=64,
            expected_height=36,
        )
    except (RuntimeError, ValueError):
        return
    raise AssertionError(f"Malformed Depth contract was accepted: {label}")


with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    color_frames = []
    depth_frames = []
    for index in range(2):
        color_path = root / f"color.{index:06d}.png"
        depth_path = root / f"depth.{index:06d}.png"
        Image.new(
            "RGB",
            (64, 36),
            (20 + index, 80 + index, 140 + index),
        ).save(color_path)
        # A smooth two-dimensional ramp represents the required linear
        # camera-space signal: broad continuous tonal coverage, low
        # saturation, and mostly small neighbour differences.
        depth_image = Image.new("L", (64, 36), 0)
        depth_pixels = depth_image.load()
        for y in range(36):
            for x in range(64):
                value = int(round(255 * (x + y) / (63 + 35)))
                depth_pixels[x, y] = value
        depth_image.save(depth_path)
        color_frames.append(color_path)
        depth_frames.append(depth_path)

    frame_times = [101.0, 102.0]
    color_sidecar = {
        "camera": "|shotCam",
        "fps": 24.0,
        "start_frame": 101.0,
        "end_frame": 102.0,
        "frame_count": 2,
        "resolution": {"width": 64, "height": 36},
        "frame_map": [
            {
                "sequence_index": index,
                "maya_frame": frame,
                "file": color_frames[index].name,
            }
            for index, frame in enumerate(frame_times)
        ],
    }
    depth_range_report = shader_depth_range_report(frame_times)
    depth_sidecar = {
        "schema": "hmb-maya-depth-playblast",
        "schema_version": 1,
        "profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "camera": "|shotCam",
        "fps": 24.0,
        "start_frame": 101.0,
        "end_frame": 102.0,
        "frame_count": 2,
        "resolution": {"width": 64, "height": 36},
        "frame_map": [
            {
                "sequence_index": index,
                "maya_frame": frame,
                "file": depth_frames[index].name,
            }
            for index, frame in enumerate(frame_times)
        ],
        "depth_range_report": depth_range_report,
    }
    result = {
        "ok": True,
        "camera": "|shotCam",
        "fps": 24.0,
        "frame_count": 2,
        "depth_frame_count": 2,
        "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "depth_range_report": copy.deepcopy(depth_range_report),
        "depth_frame_map": copy.deepcopy(depth_sidecar["frame_map"]),
    }

    def result_matching_range(sidecar: dict) -> dict:
        value = copy.deepcopy(result)
        value["depth_range_report"] = copy.deepcopy(
            sidecar["depth_range_report"]
        )
        return value

    validation_report = validate_depth(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert isinstance(validation_report, dict)
    assert validation_report["profile"] == picker.DEPTH_PLAYBLAST_PROFILE
    assert validation_report["validated"] is True
    assert validation_report["frame_count"] == 2
    assert validation_report["frame_map_match"] is True
    assert validation_report["cutout_transparency"] == (
        depth_range_report["cutout_transparency"]
    )
    assert validation_report["grayscale_min"] == 0
    assert validation_report["grayscale_max"] == 255
    assert validation_report["grayscale_channel_tolerance"] == 2
    assert validation_report["grayscale_source_max_channel_spread"] == 0
    assert validation_report["grayscale_source_drift_pixel_count"] == 0
    assert validation_report["grayscale_source_drift_frame_indices"] == []
    assert validation_report["grayscale_normalized"] is False
    assert validation_report["quality_passed_frames"] == 2
    assert validation_report["quality_required_frames"] == 2
    assert validation_report["diagnostic_status"] == "continuous_detail"
    assert validation_report["diagnostic_warnings"] == []
    assert validation_report["content_heuristics_blocking"] is False
    assert all(
        frame_report["passed"]
        for frame_report in validation_report["quality_frame_reports"]
    )
    assert (
        validation_report["quality_medians"]["meaningful_levels"]
        >= picker.DEPTH_QUALITY_MIN_MEANINGFUL_LEVELS
    )
    assert validation_report["quality_thresholds"] == {
        "minimum_meaningful_levels": picker.DEPTH_QUALITY_MIN_MEANINGFUL_LEVELS,
        "minimum_normalized_entropy": picker.DEPTH_QUALITY_MIN_NORMALIZED_ENTROPY,
        "maximum_white_saturation_ratio": picker.DEPTH_QUALITY_MAX_WHITE_SATURATION,
        "minimum_smooth_neighbor_ratio": picker.DEPTH_QUALITY_MIN_SMOOTH_NEIGHBORS,
        "maximum_large_jump_ratio": picker.DEPTH_QUALITY_MAX_LARGE_JUMPS,
        "minimum_pass_fraction": picker.DEPTH_QUALITY_MIN_PASS_FRACTION,
        "minimum_diagnostic_foreground_pixels": (
            picker.DEPTH_QUALITY_MIN_DIAGNOSTIC_FOREGROUND_PIXELS
        ),
        "measurement_scope": "nonzero_foreground_only",
        "blocking": False,
    }
    assert validation_report["background_contract"] == "pure_black"

    # Production-shaped evidence keeps screen rejection and Actor-priority
    # role exclusion mutually exclusive: 88 = 51 + 0 + 1 + 36.
    production_count_sidecar = copy.deepcopy(depth_sidecar)
    production_sample = production_count_sidecar["depth_range_report"][
        "shot_range_sample"
    ]
    production_sample.update({
        "representative_sample_count": 88,
        "foreground_representative_sample_count": 51,
        "context_representative_sample_count": 0,
        "screen_rejected_representative_sample_count": 1,
        "role_excluded_representative_sample_count": 36,
        "normalization_candidate_shape_path_count": 2,
        "screen_sample_tested_bbox_count": 52,
        "screen_sample_visible_bbox_count": 51,
        "screen_sample_rejected_bbox_count": 1,
        "bbox_fallback_candidate_count": 0,
        "binding_range_reports": [
            {
                "root": "|Tenten",
                "marker": "Red",
                "role": "foreground",
                "shape_path_count": 2,
                "representative_sample_count": 51,
                "representative_near": 10.5,
                "representative_far": 30.25,
                "normalization_candidate_sample_count": 51,
                "normalization_candidate_near": 10.5,
                "normalization_candidate_far": 30.25,
                "screen_tested_shape_path_count": 2,
                "screen_visible_shape_path_count": 2,
                "screen_rejected_shape_path_count": 0,
                "bbox_fallback_shape_path_count": 0,
                "role_excluded_shape_path_count": 0,
                "screen_sample_count": 51,
                "screen_visible_sample_count": 51,
                "screen_sample_policy_counts": {
                    "api_mesh_vertex_polygon_center_screen_visible": 51,
                },
                "selected_for_normalization": True,
            },
            {
                "root": "|CountryDog",
                "marker": "Green",
                "role": "foreground",
                "shape_path_count": 1,
                "representative_sample_count": 1,
                "representative_near": 22.0,
                "representative_far": 22.0,
                "normalization_candidate_sample_count": 0,
                "normalization_candidate_near": None,
                "normalization_candidate_far": None,
                "screen_tested_shape_path_count": 1,
                "screen_visible_shape_path_count": 0,
                "screen_rejected_shape_path_count": 1,
                "bbox_fallback_shape_path_count": 0,
                "role_excluded_shape_path_count": 0,
                "screen_sample_count": 1,
                "screen_visible_sample_count": 0,
                "screen_sample_policy_counts": {
                    "api_mesh_vertex_polygon_center_screen_rejected": 1,
                },
                "selected_for_normalization": False,
            },
            {
                "root": "|WholeMap",
                "marker": "Sky Grid",
                "role": "context",
                "shape_path_count": 18,
                "representative_sample_count": 36,
                "representative_near": 80.0,
                "representative_far": 100.0,
                "normalization_candidate_sample_count": 0,
                "normalization_candidate_near": None,
                "normalization_candidate_far": None,
                "screen_tested_shape_path_count": 0,
                "screen_visible_shape_path_count": 0,
                "screen_rejected_shape_path_count": 0,
                "bbox_fallback_shape_path_count": 0,
                "role_excluded_shape_path_count": 18,
                "screen_sample_count": 0,
                "screen_visible_sample_count": 0,
                "screen_sample_policy_counts": {
                    "context_not_sampled_foreground_priority": 36,
                },
                "selected_for_normalization": False,
            },
        ],
    })
    production_count_report = validate_depth(
        result=result_matching_range(production_count_sidecar),
        color_sidecar=color_sidecar,
        depth_sidecar=production_count_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert production_count_report["validated"] is True

    overlapping_rejection_counts = copy.deepcopy(production_count_sidecar)
    overlapping_rejection_counts["depth_range_report"]["shot_range_sample"][
        "screen_rejected_representative_sample_count"
    ] = 37
    assert_depth_invalid(
        "overlapping screen-rejected and role-excluded evidence",
        result=result_matching_range(overlapping_rejection_counts),
        color_sidecar=color_sidecar,
        depth_sidecar=overlapping_rejection_counts,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    overlapping_binding_policies = copy.deepcopy(production_count_sidecar)
    overlapping_binding_policies["depth_range_report"]["shot_range_sample"][
        "binding_range_reports"
    ][2]["screen_sample_policy_counts"] = {
        "context_not_sampled_foreground_priority": 36,
        "api_mesh_vertex_polygon_center_screen_rejected": 1,
    }
    assert_depth_invalid(
        "overlapping binding rejection policies",
        result=result_matching_range(overlapping_binding_policies),
        color_sidecar=color_sidecar,
        depth_sidecar=overlapping_binding_policies,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    invalid_schema = copy.deepcopy(depth_sidecar)
    invalid_schema["schema"] = "hmb-depth-playblast"
    assert_depth_invalid(
        "runner sidecar schema",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=invalid_schema,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    invalid_version = copy.deepcopy(depth_sidecar)
    invalid_version["schema_version"] = 2
    assert_depth_invalid(
        "runner sidecar schema version",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=invalid_version,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    invalid_profile = copy.deepcopy(depth_sidecar)
    invalid_profile["profile"] = "hmb_camera_space_depth_v3"
    assert_depth_invalid(
        "legacy camera-space sidecar profile",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=invalid_profile,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    mismatched_map = copy.deepcopy(depth_sidecar)
    mismatched_map["frame_map"][1]["maya_frame"] = 103.0
    assert_depth_invalid(
        "Color/Depth frame map",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=mismatched_map,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    mismatched_result_map = copy.deepcopy(result)
    mismatched_result_map["depth_frame_map"][1]["maya_frame"] = 103.0
    assert_depth_invalid(
        "Depth result/sidecar frame map",
        result=mismatched_result_map,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    mismatched_fps = copy.deepcopy(depth_sidecar)
    mismatched_fps["fps"] = 25.0
    assert_depth_invalid(
        "Depth FPS",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=mismatched_fps,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    mismatched_range = copy.deepcopy(depth_sidecar)
    mismatched_range["end_frame"] = 103.0
    assert_depth_invalid(
        "Depth start/end frame",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=mismatched_range,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    invalid_semantics = copy.deepcopy(depth_sidecar)
    invalid_semantics["depth_range_report"]["direction"] = (
        "near_black_far_white"
    )
    assert_depth_invalid(
        "Depth direction semantics",
        result=result_matching_range(invalid_semantics),
        color_sidecar=color_sidecar,
        depth_sidecar=invalid_semantics,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    missing_proxy_recovery = copy.deepcopy(depth_sidecar)
    missing_proxy_recovery["depth_range_report"].pop(
        "proxy_preview_recovery"
    )
    assert_depth_invalid(
        "proxy preview recovery evidence",
        result=result_matching_range(missing_proxy_recovery),
        color_sidecar=color_sidecar,
        depth_sidecar=missing_proxy_recovery,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    incomplete_proxy_recovery = copy.deepcopy(depth_sidecar)
    incomplete_proxy_recovery["depth_range_report"][
        "proxy_preview_recovery"
    ].update({
        "candidate_shape_count": 1,
        "candidate_path_count": 1,
    })
    assert_depth_invalid(
        "incomplete proxy preview recovery",
        result=result_matching_range(incomplete_proxy_recovery),
        color_sidecar=color_sidecar,
        depth_sidecar=incomplete_proxy_recovery,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    missing_assignment_verification = copy.deepcopy(depth_sidecar)
    missing_assignment_verification["depth_range_report"].pop(
        "assignment_verification"
    )
    assert_depth_invalid(
        "shader assignment verification evidence",
        result=result_matching_range(missing_assignment_verification),
        color_sidecar=color_sidecar,
        depth_sidecar=missing_assignment_verification,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    incomplete_assignment_verification = copy.deepcopy(depth_sidecar)
    incomplete_assignment_verification["depth_range_report"][
        "assignment_verification"
    ]["verified_shape_path_count"] = 1
    assert_depth_invalid(
        "incomplete shader assignment verification",
        result=result_matching_range(incomplete_assignment_verification),
        color_sidecar=color_sidecar,
        depth_sidecar=incomplete_assignment_verification,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    incomplete_frame_assignment_verification = copy.deepcopy(depth_sidecar)
    incomplete_frame_assignment_verification["depth_range_report"][
        "assignment_verification"
    ]["verified_frame_assignment_count"] -= 1
    assert_depth_invalid(
        "incomplete per-frame shader assignment verification",
        result=result_matching_range(incomplete_frame_assignment_verification),
        color_sidecar=color_sidecar,
        depth_sidecar=incomplete_frame_assignment_verification,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    missing_cutout_evidence = copy.deepcopy(depth_sidecar)
    missing_cutout_evidence["depth_range_report"].pop(
        "cutout_transparency"
    )
    assert_depth_invalid(
        "authored cutout-transparency evidence",
        result=result_matching_range(missing_cutout_evidence),
        color_sidecar=color_sidecar,
        depth_sidecar=missing_cutout_evidence,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    invalid_cutout_reports = (
        (
            "unsupported cutout policy",
            {"policy": "ignore_authored_transparency"},
        ),
        (
            "unverified alpha-driven shape",
            {"verified_shape_path_count": 0},
        ),
        (
            "alpha count exceeds capture",
            {
                "captured_shape_path_count": 0,
                "alpha_driven_shape_path_count": 1,
            },
        ),
        (
            "incomplete cutout shape capture",
            {"captured_shape_path_count": 1},
        ),
        (
            "source count exceeds alpha shapes",
            {"source_plug_count": 2},
        ),
        (
            "ambiguous authored cutout",
            {"ambiguous_shape_path_count": 1},
        ),
        (
            "unsupported authored cutout",
            {"unsupported_shape_path_count": 1},
        ),
        (
            "negative cutout count",
            {"source_plug_count": -1},
        ),
    )
    for label, replacements in invalid_cutout_reports:
        invalid_cutout = copy.deepcopy(depth_sidecar)
        invalid_cutout["depth_range_report"][
            "cutout_transparency"
        ].update(replacements)
        assert_depth_invalid(
            label,
            result=result_matching_range(invalid_cutout),
            color_sidecar=color_sidecar,
            depth_sidecar=invalid_cutout,
            color_frame_paths=color_frames,
            depth_frame_paths=depth_frames,
        )

    def assert_invalid_range_field(label: str, field: str, value) -> None:
        invalid = copy.deepcopy(depth_sidecar)
        invalid["depth_range_report"][field] = value
        assert_depth_invalid(
            label,
            result=result_matching_range(invalid),
            color_sidecar=color_sidecar,
            depth_sidecar=invalid,
            color_frame_paths=color_frames,
            depth_frame_paths=depth_frames,
        )

    # The v7 shader contract is fixed for the whole shot. Legacy range
    # contracts and any per-frame normalization are rejected.
    for label, field, value in (
        ("camera space", "space", "relative_inverse"),
        ("object bbox camera-depth source", "source", "samplerInfo.pointCameraZ"),
        (
            "Color Picker assignment mode",
            "assignment_mode",
            "samplerInfo_shader_network",
        ),
        (
            "per-frame DAG-path update scope",
            "depth_update_scope",
            "single_setup_assignment",
        ),
        (
            "bbox median representative depth",
            "representative_depth",
            "object_origin_camera_depth",
        ),
        ("surfaceShader model", "shader_model", "lambert"),
        ("v7 range report profile", "profile", "hmb_camera_space_depth_v3"),
        ("pure-black background", "background", "gray"),
        (
            "fixed-shot normalization",
            "normalization_policy",
            "per_frame_minmax",
        ),
        (
            "fixed complete-sequence normalization",
            "temporal_normalization",
            "per_frame",
        ),
        ("near-detail encoding curve", "encoding_curve", "linear"),
        ("near-detail contrast exponent", "contrast_exponent", 0.25),
        ("256 grayscale buckets", "grayscale_bucket_count", 255),
        ("surfaceShader-only nodes", "standard_nodes", ["samplerInfo"]),
        ("near-white color", "near_color", [0.0, 0.0, 0.0]),
        ("far-black color", "far_color", [1.0, 1.0, 1.0]),
        ("finite near distance", "near", float("nan")),
        ("positive near distance", "near", 0.0),
        ("ordered near/far range", "far", 10.0),
        ("positive camera near clip", "camera_near_clip", 0.0),
        ("ordered camera clip range", "camera_far_clip", 0.05),
        ("near distance inside camera clip", "near", 0.05),
        ("far distance inside camera clip", "far", 1000.1),
    ):
        assert_invalid_range_field(label, field, value)

    missing_screen_extrema = copy.deepcopy(depth_sidecar)
    missing_screen_extrema["depth_range_report"]["shot_range_sample"][
        "range_extrema_sources"
    ] = {}
    assert_depth_invalid(
        "screen-valid extrema evidence",
        result=result_matching_range(missing_screen_extrema),
        color_sidecar=color_sidecar,
        depth_sidecar=missing_screen_extrema,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    missing_binding_evidence = copy.deepcopy(depth_sidecar)
    missing_binding_evidence["depth_range_report"]["shot_range_sample"][
        "binding_range_reports"
    ] = []
    assert_depth_invalid(
        "screen-valid binding evidence",
        result=result_matching_range(missing_binding_evidence),
        color_sidecar=color_sidecar,
        depth_sidecar=missing_binding_evidence,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    inconsistent_screen_counts = copy.deepcopy(depth_sidecar)
    inconsistent_screen_counts["depth_range_report"]["shot_range_sample"][
        "screen_sample_rejected_bbox_count"
    ] = 1
    assert_depth_invalid(
        "screen-visible/rejected shape accounting",
        result=result_matching_range(inconsistent_screen_counts),
        color_sidecar=color_sidecar,
        depth_sidecar=inconsistent_screen_counts,
        color_frame_paths=color_frames,
        depth_frame_paths=depth_frames,
    )

    wrong_size_path = root / "depth-wrong-size.png"
    Image.new("RGB", (32, 18), (0, 0, 0)).save(wrong_size_path)
    assert_depth_invalid(
        "actual Depth raster dimensions",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=[wrong_size_path, depth_frames[1]],
    )

    wrong_color_size_path = root / "color-wrong-size.png"
    Image.new("RGB", (32, 18), (20, 80, 140)).save(
        wrong_color_size_path
    )
    assert_depth_invalid(
        "actual Color raster dimensions",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=[wrong_color_size_path, color_frames[1]],
        depth_frame_paths=depth_frames,
    )

    nongray_path = root / "depth-nongray.png"
    nongray_image = Image.new("RGB", (64, 36), (0, 0, 0))
    nongray_image.putpixel((12, 12), (120, 90, 120))
    nongray_image.save(nongray_path)
    assert_depth_invalid(
        "Depth RGB channels",
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=[nongray_path, depth_frames[1]],
    )

    near_gray_paths = []
    for index, source_path in enumerate(depth_frames):
        near_gray_path = root / f"depth-near-gray.{index:06d}.png"
        with Image.open(source_path) as source_image:
            near_gray_image = source_image.convert("RGB")
        if index == 0:
            near_gray_image.putpixel((12, 12), (120, 122, 121))
            near_gray_image.putpixel((13, 12), (0, 1, 0))
        near_gray_image.save(near_gray_path)
        near_gray_paths.append(near_gray_path)
    near_gray_report = validate_depth(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=near_gray_paths,
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert near_gray_report["validated"] is True
    assert near_gray_report["grayscale_channel_tolerance"] == 2
    assert near_gray_report["grayscale_source_max_channel_spread"] == 2
    assert near_gray_report["grayscale_source_drift_pixel_count"] == 2
    assert near_gray_report["grayscale_source_drift_frame_indices"] == [0]
    assert near_gray_report["grayscale_normalized"] is True
    for near_gray_path in near_gray_paths:
        with Image.open(near_gray_path) as normalized_image:
            assert normalized_image.mode == "L"
    with Image.open(near_gray_paths[0]) as normalized_image:
        assert normalized_image.getpixel((12, 12)) == 121
        assert normalized_image.getpixel((13, 12)) == 0

    excessive_path = root / "depth-excessive-chroma.png"
    excessive_image = Image.new("RGB", (64, 36), (0, 0, 0))
    excessive_image.putpixel((14, 12), (120, 123, 121))
    excessive_image.save(excessive_path)
    excessive_source_bytes = excessive_path.read_bytes()
    try:
        validate_depth(
            result=result,
            color_sidecar=color_sidecar,
            depth_sidecar=depth_sidecar,
            color_frame_paths=color_frames,
            depth_frame_paths=[excessive_path, depth_frames[1]],
            expected_frame_count=2,
            expected_fps=24.0,
            expected_start_frame=101.0,
            expected_end_frame=102.0,
            expected_width=64,
            expected_height=36,
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "Depth shader raster must contain grayscale only" in message
        assert "maximum spread 3" in message
        assert "(120, 123, 121)" in message
        assert str(excessive_path) in message
    else:
        raise AssertionError("A three-LSB Depth chroma deviation was accepted.")
    assert excessive_path.read_bytes() == excessive_source_bytes

    # Grayscale is a full-sequence contract, not just a quality-sample
    # heuristic. Frame 3 is intentionally absent from the seven-frame sample
    # selected for an eight-frame run and must still fail before any rewrite.
    full_frame_times = [101.0 + index for index in range(8)]
    full_color_frames = []
    full_depth_frames = []
    for index in range(8):
        color_path = root / f"full-color.{index:06d}.png"
        depth_path = root / f"full-depth.{index:06d}.png"
        Image.new("RGB", (64, 36), (20, 80, 140)).save(color_path)
        depth_image = Image.new("L", (64, 36), 0)
        depth_pixels = depth_image.load()
        for y in range(36):
            for x in range(64):
                depth_pixels[x, y] = int(
                    round(255 * (x + y) / (63 + 35))
                )
        if index == 3:
            depth_image = depth_image.convert("RGB")
            depth_image.putpixel((18, 14), (90, 93, 91))
        depth_image.save(depth_path)
        full_color_frames.append(color_path)
        full_depth_frames.append(depth_path)
    full_range_report = shader_depth_range_report(full_frame_times)
    full_color_sidecar = {
        "camera": "|shotCam",
        "fps": 24.0,
        "start_frame": 101.0,
        "end_frame": 108.0,
        "frame_count": 8,
        "resolution": {"width": 64, "height": 36},
        "frame_map": [
            {
                "sequence_index": index,
                "maya_frame": frame,
                "file": full_color_frames[index].name,
            }
            for index, frame in enumerate(full_frame_times)
        ],
    }
    full_depth_sidecar = {
        "schema": "hmb-maya-depth-playblast",
        "schema_version": 1,
        "profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "camera": "|shotCam",
        "fps": 24.0,
        "start_frame": 101.0,
        "end_frame": 108.0,
        "frame_count": 8,
        "resolution": {"width": 64, "height": 36},
        "frame_map": [
            {
                "sequence_index": index,
                "maya_frame": frame,
                "file": full_depth_frames[index].name,
            }
            for index, frame in enumerate(full_frame_times)
        ],
        "depth_range_report": full_range_report,
    }
    full_result = {
        "ok": True,
        "camera": "|shotCam",
        "fps": 24.0,
        "frame_count": 8,
        "depth_frame_count": 8,
        "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "depth_range_report": copy.deepcopy(full_range_report),
        "depth_frame_map": copy.deepcopy(full_depth_sidecar["frame_map"]),
    }
    full_source_bytes = [path.read_bytes() for path in full_depth_frames]
    try:
        validate_depth(
            result=full_result,
            color_sidecar=full_color_sidecar,
            depth_sidecar=full_depth_sidecar,
            color_frame_paths=full_color_frames,
            depth_frame_paths=full_depth_frames,
            expected_frame_count=8,
            expected_fps=24.0,
            expected_start_frame=101.0,
            expected_end_frame=108.0,
            expected_width=64,
            expected_height=36,
        )
    except RuntimeError as exc:
        assert "frame 3" in str(exc)
        assert "maximum spread 3" in str(exc)
    else:
        raise AssertionError(
            "Full-sequence grayscale validation skipped an unsampled frame."
        )
    assert [path.read_bytes() for path in full_depth_frames] == full_source_bytes

    no_black_path = root / "depth-no-black.png"
    no_black_image = Image.new("L", (64, 36), 16)
    no_black_pixels = no_black_image.load()
    for y in range(36):
        for x in range(64):
            no_black_pixels[x, y] = 16 + int(
                round(223 * (x + y) / (63 + 35))
            )
    no_black_image.save(no_black_path)
    no_black_report = validate_depth(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=[no_black_path, no_black_path],
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert no_black_report["validated"] is True
    assert no_black_report["grayscale_min"] == 16
    assert no_black_report["grayscale_max"] == 239
    assert no_black_report["quality_passed_frames"] == 2
    assert no_black_report["diagnostic_status"] == "continuous_detail"
    assert no_black_report["quality_medians"]["black_background_ratio"] == 0.0
    assert no_black_report["background_contract"] == "pure_black"

    binary_mask_path = root / "depth-binary-mask.png"
    binary_mask = Image.new("L", (64, 36), 0)
    binary_pixels = binary_mask.load()
    for y in range(36):
        for x in range(32, 64):
            binary_pixels[x, y] = 255
    binary_mask.save(binary_mask_path)
    binary_report = validate_depth(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=[binary_mask_path, binary_mask_path],
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert binary_report["validated"] is True
    assert binary_report["diagnostic_status"] == "mask_like_candidate"
    assert binary_report["diagnostic_warnings"]
    assert binary_report["content_heuristics_blocking"] is False

    all_black_path = root / "depth-all-black.png"
    Image.new("RGB", (64, 36), (0, 0, 0)).save(all_black_path)
    all_black_report = validate_depth(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=[all_black_path, all_black_path],
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert all_black_report["validated"] is True
    assert all_black_report["diagnostic_status"] == "no_visible_depth"
    assert all_black_report["diagnostic_warnings"] == []
    assert all_black_report["quality_passed_frames"] == 2
    assert all_black_report["quality_medians"]["foreground_coverage_ratio"] == 0.0
    assert all_black_report["quality_medians"]["black_background_ratio"] == 1.0

    flat_path = root / "depth-flat-card.png"
    flat_image = Image.new("L", (64, 36), 0)
    flat_pixels = flat_image.load()
    for y in range(8, 28):
        for x in range(16, 48):
            flat_pixels[x, y] = 128
    flat_image.save(flat_path)
    flat_report = validate_depth(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=[flat_path, flat_path],
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert flat_report["validated"] is True
    assert flat_report["diagnostic_status"] == "flat_depth"
    assert flat_report["diagnostic_warnings"] == []

    sparse_path = root / "depth-sparse-object.png"
    sparse_image = Image.new("L", (64, 36), 0)
    sparse_pixels = sparse_image.load()
    for y in range(4):
        for x in range(4):
            sparse_pixels[x, y] = 40 + (x * 4) + y
    sparse_image.save(sparse_path)
    sparse_report = validate_depth(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_frames,
        depth_frame_paths=[sparse_path, sparse_path],
        expected_frame_count=2,
        expected_fps=24.0,
        expected_start_frame=101.0,
        expected_end_frame=102.0,
        expected_width=64,
        expected_height=36,
    )
    assert sparse_report["validated"] is True
    assert sparse_report["diagnostic_status"] == "sparse_unrated"
    assert sparse_report["diagnostic_warnings"] == []


# Bundle publication uses real temporary files and restores every prior target.
with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    staged_dir = root / "staged"
    target_dir = root / "published"
    staged_dir.mkdir()
    target_dir.mkdir()
    names = ("color.mp4", "color.hmb.json", "depth.mp4", "depth.hmb.json")
    staged_targets = []
    old_bytes = {}
    new_bytes = {}
    for index, name in enumerate(names):
        staged = staged_dir / name
        target = target_dir / name
        old_bytes[target] = f"old-{index}-{name}".encode("utf-8")
        new_bytes[target] = f"new-{index}-{name}".encode("utf-8")
        target.write_bytes(old_bytes[target])
        staged.write_bytes(new_bytes[target])
        staged_targets.append((staged, target))

    records = picker.HMBVideoPickerLibrary._publish_playblast_bundle(
        staged_targets,
        root / "success-backup",
    )
    assert len(records) == 4
    assert all(not staged.exists() for staged, _target in staged_targets)
    assert all(target.read_bytes() == new_bytes[target] for _staged, target in staged_targets)

    picker.HMBVideoPickerLibrary._restore_playblast_bundle(records)
    assert all(target.read_bytes() == old_bytes[target] for _staged, target in staged_targets)


# A failure after three real replacements rolls back old files and removes a
# newly-created target that did not exist before the attempted bundle publish.
with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    staged_dir = root / "staged"
    target_dir = root / "published"
    staged_dir.mkdir()
    target_dir.mkdir()

    color_stage = staged_dir / "color.mp4"
    color_json_stage = staged_dir / "color.hmb.json"
    depth_stage = staged_dir / "depth.mp4"
    missing_depth_json_stage = staged_dir / "missing-depth.hmb.json"
    color_target = target_dir / "color.mp4"
    color_json_target = target_dir / "color.hmb.json"
    depth_target = target_dir / "depth.mp4"
    depth_json_target = target_dir / "depth.hmb.json"

    color_target.write_bytes(b"old-color")
    color_json_target.write_bytes(b"old-color-json")
    depth_json_target.write_bytes(b"old-depth-json")
    color_stage.write_bytes(b"new-color")
    color_json_stage.write_bytes(b"new-color-json")
    depth_stage.write_bytes(b"new-depth")

    try:
        picker.HMBVideoPickerLibrary._publish_playblast_bundle(
            [
                (color_stage, color_target),
                (color_json_stage, color_json_target),
                (depth_stage, depth_target),
                (missing_depth_json_stage, depth_json_target),
            ],
            root / "failure-backup",
        )
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("A missing staged Depth sidecar must fail bundle publication.")

    assert color_target.read_bytes() == b"old-color"
    assert color_json_target.read_bytes() == b"old-color-json"
    assert not depth_target.exists()
    assert depth_json_target.read_bytes() == b"old-depth-json"


# The deterministic per-artifact publication transaction must be serialized,
# not merely each os.replace call.  Otherwise one Picker node can roll back a
# second node's successful project copy/state publication.
playblast_publish_guard = getattr(picker, "_playblast_publish_guard", None)
assert callable(playblast_publish_guard), (
    "A scene-scoped _playblast_publish_guard() is required for deterministic "
    "per-artifact targets."
)

maya_mode_tree = ast.parse(
    textwrap.dedent(inspect.getsource(picker.HMBVideoPickerLibrary._maya_mode))
)
guard_nodes = []
for node in ast.walk(maya_mode_tree):
    if not isinstance(node, ast.With):
        continue
    for item in node.items:
        context_expr = item.context_expr
        if (
            isinstance(context_expr, ast.Call)
            and isinstance(context_expr.func, ast.Name)
            and context_expr.func.id == "_playblast_publish_guard"
        ):
            guard_nodes.append(node)
assert len(guard_nodes) == 1, (
    "_maya_mode must have one explicit scene-scoped Playblast publish "
    "transaction."
)


def ast_call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


guarded_call_names = [
    ast_call_name(node)
    for node in ast.walk(guard_nodes[0])
    if isinstance(node, ast.Call)
]
assert guarded_call_names.count("_publish_validated_playblast_artifact") == 3
assert "_copy_video_to_griptape_project" in guarded_call_names
assert "_publish_outputs" in guarded_call_names


# Verify that the guard is not only a per-process threading lock.  A child
# interpreter announces that it is about to acquire the same scene lock; it
# must remain blocked until this process releases the guard.
with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    scene_path = root / "guard-contract.mb"
    scene_path.write_bytes(b"guard contract scene")
    ready_path = root / "child-ready.txt"
    entered_path = root / "child-entered.txt"
    child_code = "\n".join([
        "from pathlib import Path",
        "import sys",
        "sys.path.insert(0, sys.argv[1])",
        "import HMBVideoPickerLibrary as picker",
        "scene = Path(sys.argv[2])",
        "ready = Path(sys.argv[3])",
        "entered = Path(sys.argv[4])",
        "ready.write_text('ready', encoding='utf-8')",
        "with picker._playblast_publish_guard(scene):",
        "    entered.write_text('entered', encoding='utf-8')",
    ])
    child = None
    with playblast_publish_guard(scene_path):
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                child_code,
                str(ROOT),
                str(scene_path),
                str(ready_path),
                str(entered_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ready_deadline = time.monotonic() + 10.0
        while not ready_path.is_file() and time.monotonic() < ready_deadline:
            if child.poll() is not None:
                break
            time.sleep(0.025)
        assert ready_path.is_file(), (
            "Child guard process did not reach its acquisition boundary: "
            + (child.stdout.read() if child.stdout else "")
        )
        time.sleep(0.25)
        assert child.poll() is None
        assert not entered_path.exists(), (
            "_playblast_publish_guard did not serialize a second process for "
            "the same Maya scene."
        )
    child_output, _ = child.communicate(timeout=10.0)
    assert child.returncode == 0, child_output
    assert entered_path.read_text(encoding="utf-8") == "entered"


# Runner-returned locations are an untrusted process boundary.  Normalized
# aliases of the exact requested staging path are accepted, while omissions
# and any other target fail before they can become cleanup/downstream paths.
with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir).resolve()
    expected = root / "staged" / "frames"
    normalized_alias = expected.parent / "." / expected.name
    assert picker._validated_runner_result_path(
        {"frames_folder": str(normalized_alias)},
        "frames_folder",
        expected,
    ) == expected.resolve()
    for invalid_result in (
        {},
        {"frames_folder": ""},
        {"frames_folder": str(root / "foreign" / "frames")},
    ):
        try:
            picker._validated_runner_result_path(
                invalid_result,
                "frames_folder",
                expected,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError(
                "A missing or mismatched Maya runner path was accepted."
            )

maya_mode_source = textwrap.dedent(
    inspect.getsource(picker.HMBVideoPickerLibrary._maya_mode)
)
for runner_field in (
    "frames_folder",
    "sidecar_path",
    "depth_frames_folder",
    "depth_sidecar_path",
):
    assert (
        f'"{runner_field}",' in maya_mode_source
        and "_validated_runner_result_path(" in maya_mode_source
    ), f"_maya_mode does not validate runner path {runner_field!r}."
assert maya_mode_source.index(
    "actual_frames_folder = _validated_runner_result_path("
) < maya_mode_source.index(
    "self._register_cleanup_dir(actual_frames_folder)"
)
assert '"generate_depth_playblast": depth_enabled' in maya_mode_source
assert '"depth_profile": (' in maya_mode_source
assert "actual_depth_frames_folder = _validated_runner_result_path(" in maya_mode_source
assert "actual_depth_sidecar = _validated_runner_result_path(" in maya_mode_source
assert maya_mode_source.index(
    "actual_depth_frames_folder = _validated_runner_result_path("
) < maya_mode_source.index(
    "self._register_cleanup_dir(actual_depth_frames_folder)"
)
assert "_generate_depth_anything_sequence(" not in maya_mode_source
assert "depth-anything/Depth-Anything" not in maya_mode_source


# Project copies and their Griptape metadata sidecars participate in the same
# rollback transaction.  Fake Griptape modules exercise overwrite, CREATE_NEW
# alternates, post-write failures, and unsafe-return rejection without a live
# project.
module_names = (
    "griptape_nodes_library",
    "griptape_nodes_library.utils",
    "griptape_nodes_library.utils.ffmpeg_utils",
    "griptape_nodes_library.utils.macro_path_utils",
    "griptape_nodes",
    "griptape_nodes.files",
    "griptape_nodes.files.file",
    "griptape_nodes.files.project_file",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.events",
    "griptape_nodes.retained_mode.events.os_events",
    "griptape_nodes.retained_mode.file_metadata",
    "griptape_nodes.retained_mode.file_metadata.sidecar_metadata",
)
saved_modules = {
    name: sys.modules.get(name)
    for name in module_names
}
saved_artifact_class = picker.VideoUrlArtifact
try:
    fake_modules = {
        name: types.ModuleType(name)
        for name in module_names
    }
    for package_name in (
        "griptape_nodes_library",
        "griptape_nodes_library.utils",
        "griptape_nodes",
        "griptape_nodes.files",
        "griptape_nodes.retained_mode",
        "griptape_nodes.retained_mode.events",
        "griptape_nodes.retained_mode.file_metadata",
    ):
        fake_modules[package_name].__path__ = []
    sys.modules.update(fake_modules)

    class FakeArtifact:
        def __init__(self, value="", meta=None):
            self.value = value
            self.meta = dict(meta or {})

    class ExternalResolution:
        resolved_path = ""
        is_external = True

    class FakeExistingFilePolicy:
        CREATE_NEW = "create_new"
        OVERWRITE = "overwrite"

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = root / "source.mp4"
        project_target = root / "project" / "video.mp4"
        metadata_target = root / "metadata" / "video.mp4.json"
        source.write_bytes(b"source-video")
        control = {
            "actual": project_target,
            "policy": FakeExistingFilePolicy.OVERWRITE,
            "write_actual": True,
            "written_bytes": None,
            "macro_fail": False,
            "metadata_resolve_fail_for": None,
            "metadata_same_as_media": False,
            "metadata_write_fail": False,
            "metadata_bytes": None,
            "write_content_types": [],
        }

        def metadata_path_for(media_path):
            return root / "metadata" / f"{Path(media_path).name}.json"

        class FakeDestinationFile:
            def _build_file_metadata(self):
                return {"situation": "copy_external_file"}

        class FakeSavedFile:
            def __init__(self, path):
                self.path = Path(path)

            def resolve(self):
                return str(self.path)

        class FakeFileDestination:
            def write_bytes(self, content):
                control["write_content_types"].append(type(content))
                if type(content) is not bytes:
                    raise TypeError("write() argument must be str, not mmap.mmap")
                actual = Path(control["actual"])
                if control["write_actual"]:
                    actual.parent.mkdir(parents=True, exist_ok=True)
                    actual.write_bytes(
                        control["written_bytes"]
                        if control["written_bytes"] is not None
                        else content
                    )
                return FakeSavedFile(actual)

        class FakeProjectFileDestination:
            def __init__(self):
                self._existing_file_policy = control["policy"]
                self._file = FakeDestinationFile()

            @classmethod
            def from_situation(cls, **_kwargs):
                return cls()

            def resolve(self):
                return str(project_target)

        def fake_resolve_to_macro_path(value):
            value_path = Path(value).resolve()
            if value_path == source.resolve():
                return ExternalResolution()
            if control["macro_fail"]:
                raise RuntimeError("simulated macro post-processing failure")
            return types.SimpleNamespace(
                resolved_path=f"{{inputs}}/{value_path.name}",
                is_external=False,
            )

        def fake_resolve_sidecar_path(media_path):
            media_path = Path(media_path).resolve()
            fail_for = control["metadata_resolve_fail_for"]
            if fail_for is not None and media_path == Path(fail_for).resolve():
                raise RuntimeError("simulated metadata resolution failure")
            if control["metadata_same_as_media"]:
                return media_path
            return metadata_path_for(media_path)

        def fake_write_sidecar(media_path, _sidecar_content):
            if control["metadata_write_fail"]:
                return
            metadata_path = metadata_path_for(media_path)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_bytes(
                control["metadata_bytes"]
                if control["metadata_bytes"] is not None
                else (
                    json.dumps({
                        "schema_version": 1,
                        "source": Path(media_path).name,
                    }).encode("utf-8")
                )
            )

        fake_modules[
            "griptape_nodes_library.utils.ffmpeg_utils"
        ].extract_video_player_metadata = lambda _path: {"duration": 1.0}
        fake_modules[
            "griptape_nodes_library.utils.macro_path_utils"
        ].resolve_to_macro_path = fake_resolve_to_macro_path
        fake_modules["griptape_nodes_library.utils"].ffmpeg_utils = (
            fake_modules["griptape_nodes_library.utils.ffmpeg_utils"]
        )
        fake_modules[
            "griptape_nodes.files.file"
        ].FileDestination = FakeFileDestination
        fake_modules[
            "griptape_nodes.files.project_file"
        ].ProjectFileDestination = FakeProjectFileDestination
        fake_modules[
            "griptape_nodes.retained_mode.events.os_events"
        ].ExistingFilePolicy = FakeExistingFilePolicy
        fake_modules[
            "griptape_nodes.retained_mode.file_metadata.sidecar_metadata"
        ]._resolve_sidecar_path = fake_resolve_sidecar_path
        fake_modules[
            "griptape_nodes.retained_mode.file_metadata.sidecar_metadata"
        ].write_sidecar = fake_write_sidecar
        picker.VideoUrlArtifact = FakeArtifact

        fake_node = types.SimpleNamespace(name="DepthRegressionPicker")
        project_target.parent.mkdir(parents=True, exist_ok=True)
        metadata_target.parent.mkdir(parents=True, exist_ok=True)
        project_target.write_bytes(b"old-project-video")
        metadata_target.write_bytes(b"old-project-metadata")
        records = []
        artifact, returned_path = picker._copy_video_to_griptape_project(
            fake_node,
            source,
            1,
            transaction_records=records,
            backup_folder=root / "overwrite-backup",
        )
        assert returned_path == "{inputs}/video.mp4"
        assert artifact.value == "{inputs}/video.mp4"
        assert project_target.read_bytes() == source.read_bytes()
        assert control["write_content_types"] == [bytes]
        assert json.loads(metadata_target.read_text(encoding="utf-8"))[
            "source"
        ] == "video.mp4"
        picker.HMBVideoPickerLibrary._restore_playblast_bundle(records)
        assert project_target.read_bytes() == b"old-project-video"
        assert metadata_target.read_bytes() == b"old-project-metadata"

        project_target.unlink()
        metadata_target.unlink()
        control.update({
            "actual": project_target,
            "policy": FakeExistingFilePolicy.CREATE_NEW,
            "write_actual": True,
            "macro_fail": False,
        })
        records = []
        picker._copy_video_to_griptape_project(
            fake_node,
            source,
            2,
            transaction_records=records,
            backup_folder=root / "create-backup",
        )
        assert project_target.is_file()
        assert metadata_target.is_file()
        picker.HMBVideoPickerLibrary._restore_playblast_bundle(records)
        assert not project_target.exists()
        assert not metadata_target.exists()

        # A real CREATE_NEW alternate is removed on rollback while a pre-existing
        # orphan metadata sidecar at that exact alternate is restored.
        project_target.write_bytes(b"planned-existing")
        alternate_target = project_target.with_name("video_1.mp4")
        alternate_metadata = metadata_path_for(alternate_target)
        alternate_metadata.write_bytes(b"old-alternate-metadata")
        control.update({
            "actual": alternate_target,
            "policy": FakeExistingFilePolicy.CREATE_NEW,
            "write_actual": True,
            "macro_fail": False,
            "metadata_resolve_fail_for": None,
        })
        records = []
        picker._copy_video_to_griptape_project(
            fake_node,
            source,
            1,
            transaction_records=records,
            backup_folder=root / "alternate-backup",
        )
        assert alternate_target.read_bytes() == source.read_bytes()
        assert json.loads(alternate_metadata.read_text(encoding="utf-8"))[
            "source"
        ] == "video_1.mp4"
        picker.HMBVideoPickerLibrary._restore_playblast_bundle(records)
        assert project_target.read_bytes() == b"planned-existing"
        assert not alternate_target.exists()
        assert alternate_metadata.read_bytes() == b"old-alternate-metadata"

        # Once an alternate is proven to be an allowed CREATE_NEW derivative,
        # it is enrolled before payload verification; a corrupt write result is
        # therefore removed when validation fails.
        corrupt_target = project_target.with_name("video_4.mp4")
        control.update({
            "actual": corrupt_target,
            "policy": FakeExistingFilePolicy.CREATE_NEW,
            "write_actual": True,
            "written_bytes": b"corrupt-video",
            "macro_fail": False,
            "metadata_resolve_fail_for": None,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "corrupt-alternate-backup",
            )
        except RuntimeError as exc:
            assert "does not match the requested video" in str(exc)
        else:
            raise AssertionError("A corrupt CREATE_NEW payload was accepted.")
        assert not corrupt_target.exists()
        assert not metadata_path_for(corrupt_target).exists()
        control["written_bytes"] = None

        # Rewriting a metadata sidecar to identical bytes is valid.  Deleting
        # the snapshotted target before write makes a silent write failure
        # observable without comparing old and new content.
        identical_metadata = (
            b'{"schema_version": 1, "source": "video.mp4"}'
        )
        project_target.write_bytes(b"old-before-identical-metadata")
        metadata_target.write_bytes(identical_metadata)
        control.update({
            "actual": project_target,
            "policy": FakeExistingFilePolicy.OVERWRITE,
            "write_actual": True,
            "metadata_bytes": identical_metadata,
            "metadata_write_fail": False,
        })
        records = []
        picker._copy_video_to_griptape_project(
            fake_node,
            source,
            1,
            transaction_records=records,
            backup_folder=root / "identical-metadata-backup",
        )
        assert metadata_target.read_bytes() == identical_metadata
        picker.HMBVideoPickerLibrary._restore_playblast_bundle(records)
        assert project_target.read_bytes() == b"old-before-identical-metadata"
        assert metadata_target.read_bytes() == identical_metadata

        project_target.write_bytes(b"old-before-metadata-write-failure")
        metadata_target.write_bytes(b"old-metadata-before-write-failure")
        control.update({
            "actual": project_target,
            "policy": FakeExistingFilePolicy.OVERWRITE,
            "write_actual": True,
            "metadata_bytes": None,
            "metadata_write_fail": True,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "metadata-write-failure-backup",
            )
        except RuntimeError as exc:
            assert "metadata sidecar was not created" in str(exc)
        else:
            raise AssertionError("A silent metadata write failure was accepted.")
        assert (
            project_target.read_bytes()
            == b"old-before-metadata-write-failure"
        )
        assert (
            metadata_target.read_bytes()
            == b"old-metadata-before-write-failure"
        )
        control["metadata_write_fail"] = False

        # The media is enrolled before metadata path resolution.  If that
        # post-write step fails, neither the new alternate nor a sidecar remains.
        resolver_failure_target = project_target.with_name("video_2.mp4")
        resolver_failure_metadata = metadata_path_for(
            resolver_failure_target
        )
        control.update({
            "actual": resolver_failure_target,
            "policy": FakeExistingFilePolicy.CREATE_NEW,
            "write_actual": True,
            "macro_fail": False,
            "metadata_resolve_fail_for": resolver_failure_target,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "resolver-error-backup",
            )
        except RuntimeError as exc:
            assert "simulated metadata resolution failure" in str(exc)
        else:
            raise AssertionError("A metadata post-write failure was accepted.")
        assert not resolver_failure_target.exists()
        assert not resolver_failure_metadata.exists()

        # A corrupt resolver must never let metadata cleanup unlink the MP4.
        project_target.write_bytes(b"old-before-same-path-resolver")
        control.update({
            "actual": project_target,
            "policy": FakeExistingFilePolicy.OVERWRITE,
            "write_actual": True,
            "metadata_resolve_fail_for": None,
            "metadata_same_as_media": True,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "same-path-resolver-backup",
            )
        except RuntimeError as exc:
            assert "returned the media file itself" in str(exc)
        else:
            raise AssertionError("A same-path metadata resolver was accepted.")
        assert project_target.read_bytes() == b"old-before-same-path-resolver"
        control["metadata_same_as_media"] = False

        # A partial/non-object sidecar is rejected and both prior files return.
        project_target.write_bytes(b"old-before-invalid-sidecar")
        metadata_target.write_bytes(b"old-before-invalid-sidecar-metadata")
        control.update({
            "actual": project_target,
            "policy": FakeExistingFilePolicy.OVERWRITE,
            "write_actual": True,
            "metadata_bytes": b"{partial-json",
            "metadata_write_fail": False,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "invalid-sidecar-backup",
            )
        except RuntimeError as exc:
            assert "not a valid JSON object" in str(exc)
        else:
            raise AssertionError("An invalid project metadata sidecar was accepted.")
        assert project_target.read_bytes() == b"old-before-invalid-sidecar"
        assert (
            metadata_target.read_bytes()
            == b"old-before-invalid-sidecar-metadata"
        )
        control["metadata_bytes"] = None

        # Macro/artifact post-processing happens after both media and metadata
        # records exist, so its exception also leaves no orphan.
        macro_failure_target = project_target.with_name("video_3.mp4")
        macro_failure_metadata = metadata_path_for(macro_failure_target)
        control.update({
            "actual": macro_failure_target,
            "policy": FakeExistingFilePolicy.CREATE_NEW,
            "write_actual": True,
            "macro_fail": True,
            "metadata_resolve_fail_for": None,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "macro-error-backup",
            )
        except RuntimeError as exc:
            assert "simulated macro post-processing failure" in str(exc)
        else:
            raise AssertionError("A macro post-write failure was accepted.")
        assert not macro_failure_target.exists()
        assert not macro_failure_metadata.exists()
        control["macro_fail"] = False

        # A path outside the planned project parent is rejected and never
        # registered for deletion, even when a faulty writer reports it.
        outside_target = root / "outside" / "valuable.mp4"
        outside_target.parent.mkdir(parents=True, exist_ok=True)
        outside_target.write_bytes(b"valuable-existing-bytes")
        control.update({
            "actual": outside_target,
            "policy": FakeExistingFilePolicy.CREATE_NEW,
            "write_actual": False,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "scope-escape-backup",
            )
        except RuntimeError as exc:
            assert "unsafe project copy destination" in str(exc)
        else:
            raise AssertionError("A project-copy scope escape was accepted.")
        assert outside_target.read_bytes() == b"valuable-existing-bytes"

        # Even an otherwise valid same-parent derivative cannot be treated as
        # new unless the destination policy is explicitly CREATE_NEW.
        overwrite_alternate = project_target.with_name("video_7.mp4")
        overwrite_alternate.write_bytes(b"valuable-overwrite-target")
        control.update({
            "actual": overwrite_alternate,
            "policy": FakeExistingFilePolicy.OVERWRITE,
            "write_actual": False,
        })
        try:
            picker._copy_video_to_griptape_project(
                fake_node,
                source,
                1,
                transaction_records=[],
                backup_folder=root / "non-create-new-backup",
            )
        except RuntimeError as exc:
            assert "unsafe project copy destination" in str(exc)
        else:
            raise AssertionError(
                "A non-CREATE_NEW alternate destination was accepted."
            )
        assert overwrite_alternate.read_bytes() == b"valuable-overwrite-target"
finally:
    picker.VideoUrlArtifact = saved_artifact_class
    for module_name, saved_module in saved_modules.items():
        if saved_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = saved_module

project_copy_source = textwrap.dedent(
    inspect.getsource(picker._copy_video_to_griptape_project)
)
assert "copy_external_file_to_project" not in project_copy_source
assert "FileDestination.write_bytes(" in project_copy_source
assert project_copy_source.index(
    "_created_publish_target_record("
) < project_copy_source.index(
    "_resolve_sidecar_path(actual_target)"
)

for artifact_records in (
    "color_project_records",
    "depth_project_records",
    "motion_project_records",
):
    assert f"transaction_records={artifact_records}" in maya_mode_source
for auxiliary_records in (
    "depth_project_records",
    "motion_project_records",
):
    assert any(
        isinstance(call, ast.Call)
        and ast_call_name(call) == "_restore_playblast_bundle"
        and any(
            isinstance(argument, ast.Name)
            and argument.id == auxiliary_records
            for argument in call.args
        )
        for call in ast.walk(guard_nodes[0])
    )
# Successfully committed records are still accumulated so a later Picker-state
# publication failure can restore every artifact without crossing transactions.
assert any(
    isinstance(call, ast.Call)
    and ast_call_name(call) == "_restore_playblast_bundle"
    and any(
        isinstance(argument, ast.Name)
        and argument.id == "project_publish_records"
        for argument in call.args
    )
    for call in ast.walk(guard_nodes[0])
)

# Griptape versions use both natural and zero-padded CREATE_NEW suffixes.
# Accept only a positive numeric suffix in the exact planned family.
planned_create_new = Path("C:/approved/inputs/videos/testLL_playblast_1.mp4")
for accepted_name in (
    "testLL_playblast_1_1.mp4",
    "testLL_playblast_1_01.mp4",
    "testLL_playblast_1_001.mp4",
    "testLL_playblast_1_0001.mp4",
):
    assert picker._is_allowed_project_create_new_path(
        planned_create_new,
        planned_create_new.with_name(accepted_name),
    ), accepted_name
for rejected in (
    Path("C:/approved/inputs/videos/testLL_playblast_1_000.mp4"),
    Path("C:/approved/inputs/videos/other_001.mp4"),
    Path("C:/approved/inputs/videos/testLL_playblast_1_001.mov"),
    Path("C:/outside/testLL_playblast_1_001.mp4"),
):
    assert not picker._is_allowed_project_create_new_path(
        planned_create_new,
        rejected,
    ), rejected


print("HMB Depth companion regression passed.")
