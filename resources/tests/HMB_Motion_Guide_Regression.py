from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBPromptLibrary as prompt  # noqa: E402
import HMBVideoPickerLibrary as picker  # noqa: E402


assert picker.MOTION_GUIDE_PROFILE == "hmb_target_neutral_motion_guide_v5"
assert picker.LEGACY_MOTION_GUIDE_PROFILES == frozenset({
    "hmb_target_neutral_motion_guide_v4",
})
assert picker.MOTION_GUIDE_COMPATIBLE_PROFILES == frozenset({
    picker.MOTION_GUIDE_PROFILE,
})
assert prompt.PICKER_LEGACY_MOTION_GUIDE_PROFILES == frozenset({
    "hmb_target_neutral_motion_guide_v4",
})
assert prompt.PICKER_MOTION_GUIDE_PROFILES == frozenset({
    prompt.PICKER_MOTION_GUIDE_PROFILE,
})
assert picker.MOTION_GUIDE_RUNNER_SCHEMA_VERSION == 2
assert picker.MOTION_GUIDE_SIDECAR_SCHEMA_VERSION == 2
assert picker.MOTION_GUIDE_MEDIA_KIND == "maya_motion_guide"
assert picker.PRIMARY_COLOR_VIDEO_SLOT == 1
assert picker.AUXILIARY_VIDEO_SLOTS == (2, 3, 4, 5)
assert picker._default_widget_state()["motion_guide_enabled"] is False
assert (
    "Motion Guide / Retargeting Reference"
    in prompt.VIDEO_SOURCE_TYPE_CHOICES
)
assert "Derived Motion Decoding Only" in prompt.VIDEO_CONTROL_ROLE_CHOICES
assert prompt.VIDEO_ROLE_COMPATIBILITY[
    "Motion Guide / Retargeting Reference"
] == {"Derived Motion Decoding Only"}


# A companion request always binds generation identity to @video1.
base_state = picker._default_widget_state()
base_state.update({
    "active_slot_count": 4,
    "selected_video_slot": 4,
    "selected_camera": "|camera",
    "output_width": 320,
    "output_height": 180,
    "slot_assignments": [
        {
            "video_slot": 1,
            "bindings": [{
                "full_dag_path": "|Hero",
                "maya_uuid": "hero-uuid",
                "group_name": "Hero",
                "color": "Red",
                "enabled": True,
                "picker_order": 1,
            }],
        },
        {"video_slot": 2, "bindings": []},
        {"video_slot": 3, "bindings": []},
        {
            "video_slot": 4,
            "bindings": [{
                "full_dag_path": "|Manual",
                "maya_uuid": "manual-uuid",
                "group_name": "Manual",
                "color": "Green",
                "enabled": True,
                "picker_order": 1,
            }],
        },
    ],
})
manual_digest = picker._operation_input_digest(
    "run_video",
    "C:/shot.mb",
    base_state,
    4,
)
motion_state = copy.deepcopy(base_state)
motion_state["motion_guide_enabled"] = True
motion_digest = picker._operation_input_digest(
    "run_video",
    "C:/shot.mb",
    motion_state,
    4,
)
assert motion_digest != manual_digest
assert motion_digest == picker._operation_input_digest(
    "run_video",
    "C:/shot.mb",
    motion_state,
    1,
)


# PICKER_OUT schema v5 transports one strict typed auxiliary bundle companion
# in selected catalog order. Legacy slot 3 becomes transient @video2 without
# changing the motion asset's stable UID.
bundle_id = "motion-guide-regression-bundle"
payload_state = picker._default_widget_state()
payload_state.update({
    "active_slot_count": 3,
    "scene_path": "C:/shot.mb",
    "videos": [
        {
            "video_slot": 1,
            "video_uid": "motion-regression-color",
            "video_path": "C:/color.mp4",
            "camera": "|camera",
            "bundle_run_id": bundle_id,
            "generation_role": "mask",
            "media_kind": picker.MASK_MEDIA_KIND,
            "source_fps": 24,
            "output_fps": 24,
            "source_frame_count": 3,
            "output_frame_count": 3,
            "decoded_frame_count": 3,
            "start_frame": 101,
            "end_frame": 103,
            "output_width": 320,
            "output_height": 180,
            "has_maya_frame_range": True,
            "markers": [{
                "asset_id": "Hero",
                "group_name": "Hero",
                "full_dag_path": "|Hero",
                "maya_uuid": "hero-uuid",
                "color": "Red",
                "video_slot": 1,
                "picker_order": 1,
            }],
        },
        {
            "video_slot": 3,
            "video_uid": "motion-regression-guide",
            "video_path": "C:/motion.mp4",
            "camera": "|camera",
            "bundle_run_id": bundle_id,
            "media_kind": picker.MOTION_GUIDE_MEDIA_KIND,
            "generation_role": "motion_guide",
            "video_role": "maya_motion_guide_companion",
            "source_type_hint": picker.MOTION_GUIDE_SOURCE_TYPE,
            "control_role_hint": picker.MOTION_GUIDE_CONTROL_ROLE,
            "source_video_slot": 1,
            "companion_of_video_slot": 1,
            "source_video_uid": "motion-regression-color",
            "companion_video_uid": "motion-regression-color",
            "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
            "motion_guide_report": {
                "appearance_authority": "zero",
                "motion_authority": "derived_decoder_of_video1_only",
                "targets": [{
                    "face_channels": [{"group": "brow"}],
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
                    "curve_geometry_rendered": False,
                    "target_count": 1,
                    "channel_count": 1,
                    "driver_count": 0,
                    "landmark_count": 0,
                    "rasterized_sample_count": 0,
                    "visibility_opportunity_count": 0,
                    "hidden_or_occluded_sample_count": 3,
                },
            },
            "source_fps": 24,
            "output_fps": 24,
            "source_frame_count": 3,
            "output_frame_count": 3,
            "decoded_frame_count": 3,
            "start_frame": 101,
            "end_frame": 103,
            "output_width": 320,
            "output_height": 180,
            "has_maya_frame_range": True,
            "markers": [],
        },
    ],
})
node = picker.HMBVideoPickerLibrary.__new__(
    picker.HMBVideoPickerLibrary
)
picker_payload = node._build_picker_payload(payload_state)
assert picker_payload["schema_version"] == 5
assert [item["video_slot"] for item in picker_payload["videos"]] == [1, 2]
assert [item["selection_order"] for item in picker_payload["videos"]] == [1, 2]
assert picker_payload["ordered_video_uids"] == [
    "motion-regression-color",
    "motion-regression-guide",
]
primary_payload, motion_payload = picker_payload["videos"]
assert primary_payload["bundle_run_id"] == bundle_id
assert motion_payload["bundle_run_id"] == bundle_id
assert motion_payload["media_kind"] == "maya_motion_guide"
assert motion_payload["markers"] == []
assert motion_payload["motion_guide_profile"] == picker.MOTION_GUIDE_PROFILE
assert motion_payload["motion_guide_report"]["appearance_authority"] == "zero"
assert motion_payload["generation_role"] == "motion_guide"
assert motion_payload["source_video_uid"] == "motion-regression-color"
assert motion_payload["companion_video_uid"] == "motion-regression-color"
assert motion_payload["source_video_slot"] == 1
assert motion_payload["companion_of_video_slot"] == 1


# Prompt auto-classifies only the exact matching bundle and restores previous
# manual values when a later Picker payload breaks that identity.
prompt_state = prompt._default_widget_state()
prompt_state["videos"] = [
    prompt._default_video_item(index)
    for index in range(1, 3)
]
prompt_state["videos"][1].update({
    "label": "manual-motion-row",
    "present": True,
    "video_main_type": "Custom / Context",
    "video_sub_type": "Context",
})
applied = prompt._apply_picker_payload(
    prompt_state,
    picker_payload,
    connected=True,
)
motion_row = applied["videos"][1]
assert motion_row["video_main_type"] == "Maya Preview / Playblast"
assert motion_row["video_sub_type"] == "Motion Guide"
assert motion_row["source_type"] == "Motion Guide / Retargeting Reference"
assert motion_row["control_role"] == "Derived Motion Decoding Only"
assert motion_row["present"] is True
assert (
    motion_row["picker_auto_motion_guide"]["bundle_run_id"]
    == bundle_id
)
assert motion_row["picker_motion_guide_summary"] == {
    "profile": picker.MOTION_GUIDE_PROFILE,
    "semantic_face": True,
    "target_count": 1,
    "channel_count": 1,
    "driver_count": 0,
    "landmark_count": 0,
    "rasterized_sample_count": 0,
    "hidden_or_occluded_sample_count": 3,
    "semantic_groups": ["brow"],
    "final_blendshape_values_in_sidecar": True,
    "raw_curve_geometry_rendered": False,
}
compiled_prompt = prompt._build_data_only_prompt_package(applied)
compiled_lines = compiled_prompt.splitlines()
assert len(compiled_lines) == 7
compiled_job = json.loads(
    compiled_lines[compiled_lines.index("HMB JOB DATA (JSON):") + 1]
)
compiled_motion = compiled_job["videos"][1]
assert compiled_motion["source_type"] == "Motion Guide / Retargeting Reference"
assert compiled_motion["control_role"] == "Derived Motion Decoding Only"
assert compiled_motion["companion"]["kind"] == "motion_guide"
assert compiled_motion["companion"]["validated"] is True

bad_payload = copy.deepcopy(picker_payload)
bad_payload["videos"][1]["bundle_run_id"] = "other-bundle"
released = prompt._apply_picker_payload(
    applied,
    bad_payload,
    connected=True,
)
released_row = released["videos"][1]
assert released_row["label"] == "manual-motion-row"
assert released_row["video_main_type"] == "Custom / Context"
assert released_row["video_sub_type"] == "Context"
assert released_row["source_type"] == "Custom"
assert released_row["control_role"] == "Context Only"
assert released_row["present"] is True
assert released_row["picker_auto_motion_guide"] == {}
assert released_row["picker_motion_guide_summary"] == {}

missing_bundle_payload = copy.deepcopy(picker_payload)
missing_bundle_payload["videos"][1].pop("bundle_run_id")
missing_bundle = prompt._apply_picker_payload(
    prompt_state,
    missing_bundle_payload,
    connected=True,
)
assert (
    missing_bundle["videos"][1]["source_type"]
    != "Motion Guide / Retargeting Reference"
)

for retired_profile in (
    "hmb_target_neutral_motion_guide_v2",
    "hmb_target_neutral_motion_guide_v3",
    "hmb_target_neutral_motion_guide_v4",
):
    retired_payload = copy.deepcopy(picker_payload)
    retired_payload["videos"][1]["motion_guide_profile"] = retired_profile
    retired_applied = prompt._apply_picker_payload(
        prompt_state,
        retired_payload,
        connected=True,
    )
    assert (
        retired_applied["videos"][1]["source_type"]
        != "Motion Guide / Retargeting Reference"
    )
    assert retired_applied["videos"][1]["picker_motion_guide_summary"] == {}
    # The catalog's explicit generation role remains a stable type identity,
    # while Prompt still rejects retired quality profiles above.
    assert picker._is_generated_motion_guide_video_item(
        retired_payload["videos"][1]
    )


# Frame/raster/report validation is fail-closed and checks inherited visibility.
Image, _chops, ImageDraw, _unidentified, _version = (
    picker._screen_space._require_pillow()
)
with tempfile.TemporaryDirectory() as temp_dir:
    folder = Path(temp_dir)
    frame_paths = []
    for index in range(3):
        path = folder / f"motion.{index:06d}.png"
        image = Image.new("RGB", (32, 18), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.line((4 + index, 14, 16 + index, 4), fill=(245, 245, 245), width=2)
        draw.ellipse((8 + index, 8, 12 + index, 12), fill=(255, 224, 0))
        image.save(path)
        frame_paths.append(path)

    frame_map = [
        {
            "sequence_index": index,
            "maya_frame": 101 + index,
            "file": frame_paths[index].name,
        }
        for index in range(3)
    ]
    color_sidecar = {
        "camera": "|camera",
        "fps": 24,
        "start_frame": 101,
        "end_frame": 103,
        "frame_count": 3,
        "resolution": {"width": 32, "height": 18},
        "frame_map": frame_map,
        "hidden_paths": ["|HiddenSet"],
    }
    report = {
        "profile": picker.MOTION_GUIDE_PROFILE,
        "space": "camera_screen_normalized",
        "representation": (
            "target_neutral_core_motion_plus_visible_face_semantic_rgb"
        ),
        "source": (
            "maya_skin_influence_transform_blendshape_and_curve_driver_evaluation"
        ),
        "target_count": 1,
        "joint_target_count": 1,
        "rigid_target_count": 0,
        "total_point_samples": 9,
        "visible_target_samples": 3,
        "visibility_policy": (
            "shared_hidden_paths_plus_target_shape_animated_dag_layer_visibility"
        ),
        "joint_selection_policy": (
            "weighted_skin_influences_then_direct_or_character_reference_core_fallback"
        ),
        "occlusion_policy": (
            "micro_face_rig_helper_and_duplicate_skeleton_points_excluded;"
            "core_body_motion_intent_preserved_through_self_occlusion;"
            "face_surface_front_facing_and_character_mesh_first_hit_only"
        ),
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
            "curve_geometry_rendered": False,
            "target_count": 0,
            "channel_count": 0,
            "driver_count": 0,
            "landmark_count": 0,
            "channel_sample_count": 0,
            "driver_sample_count": 0,
            "rasterized_sample_count": 0,
            "visibility_opportunity_count": 0,
            "hidden_or_occluded_sample_count": 0,
        },
        "appearance_authority": "zero",
        "camera_authority": "zero_independent_authority",
        "motion_authority": "derived_decoder_of_video1_only",
        "hidden_paths": ["|HiddenSet"],
        "targets": [{
            "target_index": 1,
            "face_channel_count": 0,
            "face_driver_count": 0,
            "face_landmark_count": 0,
            "face_channels": [],
            "face_drivers": [],
            "face_landmarks": [],
            "face_edges": [],
        }],
        "motion_frames": [
            {
                "sequence_index": index,
                "maya_frame": 101 + index,
                "targets": [{
                    "target_index": 1,
                    "visible": True,
                    "face": {
                        "available": False,
                        "raster_ready": False,
                        "rasterized": False,
                        "visibility_opportunity": False,
                        "visibility_reason": "no_face_channels",
                        "channel_values": [],
                        "driver_values": [],
                        "landmarks": [],
                        "guide_points": [],
                        "guide_segments": [],
                    },
                }],
            }
            for index in range(3)
        ],
        "palette": {
            "face_brow": list(picker.MOTION_GUIDE_FACE_BROW_RGB),
            "face_eyelid": list(picker.MOTION_GUIDE_FACE_EYELID_RGB),
            "face_mouth": list(picker.MOTION_GUIDE_FACE_MOUTH_RGB),
            "face_jaw": list(picker.MOTION_GUIDE_FACE_JAW_RGB),
        },
    }
    motion_sidecar = {
        "schema": "hmb-maya-motion-guide",
        "schema_version": picker.MOTION_GUIDE_RUNNER_SCHEMA_VERSION,
        "profile": picker.MOTION_GUIDE_PROFILE,
        "camera": "|camera",
        "fps": 24,
        "start_frame": 101,
        "end_frame": 103,
        "frame_count": 3,
        "resolution": {"width": 32, "height": 18},
        "frame_map": frame_map,
        "hidden_paths": ["|HiddenSet"],
        "motion_guide_report": report,
    }
    result = {
        "motion_guide_profile": picker.MOTION_GUIDE_PROFILE,
        "motion_guide_frame_count": 3,
        "motion_guide_frame_map": frame_map,
        "motion_guide_report": report,
    }
    validation = picker._validate_motion_guide_inputs(
        result=result,
        color_sidecar=color_sidecar,
        motion_sidecar=motion_sidecar,
        motion_frame_paths=frame_paths,
        expected_frame_count=3,
        expected_fps=24,
        expected_start_frame=101,
        expected_end_frame=103,
        expected_width=32,
        expected_height=18,
    )
    assert validation["validated"] is True
    assert validation["frame_map_match"] is True
    assert validation["visibility_match"] is True
    assert validation["guide_pixel_observed"] is True
    assert validation["face_pixel_observed"] is False
    assert validation["face_semantics"]["channel_count"] == 0
    assert validation["appearance_authority"] == "zero"

    semantic_report = copy.deepcopy(report)
    semantic_target = semantic_report["targets"][0]
    semantic_target.update({
        "face_channel_count": 1,
        "face_driver_count": 1,
        "face_channels": [{
            "id": "blendshape-uuid:weight[0]",
            "alias": "mouthSmile",
            "blendshape": "face_BS",
            "blendshape_id": "blendshape-uuid",
            "weight_index": 0,
            "weight_plug": "face_BS.weight[0]",
            "group": "mouth",
            "side": "center",
            "action": "smile",
            "raster_eligible": True,
            "controller_plugs": ["face_CTL.smile"],
            "affected_shapes": ["|Hero|faceShape"],
        }],
        "face_drivers": [{
            "id": "face-controller-uuid:smile",
            "plug": "face_CTL.smile",
            "node": "face_CTL",
            "node_id": "face-controller-uuid",
            "label": "face_CTL",
        }],
    })
    semantic_report["face_semantics"].update({
        "target_count": 1,
        "channel_count": 1,
        "driver_count": 1,
        "channel_sample_count": 3,
        "driver_sample_count": 3,
        "hidden_or_occluded_sample_count": 3,
    })
    for frame in semantic_report["motion_frames"]:
        frame["targets"][0]["face"].update({
            "available": True,
            "visibility_reason": "insufficient_surface_pinned_controller_landmarks",
            "channel_values": [0.5],
            "driver_values": [1.0],
        })
    semantic_motion_sidecar = copy.deepcopy(motion_sidecar)
    semantic_motion_sidecar["motion_guide_report"] = semantic_report
    semantic_result = copy.deepcopy(result)
    semantic_result["motion_guide_report"] = semantic_report
    semantic_validation = picker._validate_motion_guide_inputs(
        result=semantic_result,
        color_sidecar=color_sidecar,
        motion_sidecar=semantic_motion_sidecar,
        motion_frame_paths=frame_paths,
        expected_frame_count=3,
        expected_fps=24,
        expected_start_frame=101,
        expected_end_frame=103,
        expected_width=32,
        expected_height=18,
    )
    assert semantic_validation["face_semantics"]["channel_count"] == 1
    assert semantic_validation["face_semantics"]["semantic_groups"] == [
        "mouth"
    ]

    raster_report = copy.deepcopy(semantic_report)
    raster_target = raster_report["targets"][0]
    raster_target["face_landmark_count"] = 3
    raster_target["face_landmarks"] = [
        {
            "id": f"face:landmark-{index}",
            "region": "mouth",
            "side": "center",
            "controller_id": "face-controller-uuid",
            "controller_label": "face_CTL",
            "mesh_id": "face-mesh-uuid",
            "mesh": "|Hero|faceShape",
            "vertex_index": index,
            "channel_ids": ["blendshape-uuid:weight[0]"],
            "surface_snap_distance": 0.01,
            "anchor_method": (
                "semantic_bilateral_jaw_surface_profile_inference"
                if index == 0
                else (
                    "semantic_bilateral_jaw_midpoint_surface_inference"
                    if index == 1
                    else "semantic_face_axis_center_surface_fallback"
                )
            ),
            "anchor_confidence": 0.9,
        }
        for index in range(3)
    ]
    raster_target["face_edges"] = [
        {"from": "face:landmark-0", "to": "face:landmark-1", "region": "mouth"},
        {"from": "face:landmark-1", "to": "face:landmark-2", "region": "mouth"},
    ]
    raster_target["face_landmark_audit"] = {
        "surface_completion": {
            "jaw_center_candidate_evidence": [{
                "stage": "bilateral_jaw_surface_profile",
                "status": "accepted",
                "rejection": "",
                "downward_progress_fraction": 0.09,
                "jaw_midpoint_lateral_drift_fraction": 0.01,
                "mouth_center_lateral_drift_fraction": 0.06,
                "mouth_center_lateral_offset_fraction": 0.05,
                "maximum_center_drift_fraction": 0.04,
                "bilateral_span_position": 0.5,
                "bilateral_jaw_span_fraction": 0.10,
                "surface_snap_fraction": 0.02,
                "surface_vertex_count": 100,
                "scanned_candidate_count": 4,
                "eligible_candidate_count": 2,
                "selection_score_policy": (
                    "surface_distance_then_vertex_index"
                ),
                "selected_score": [0.02, 42],
            }],
        },
    }
    raster_report["face_semantics"].update({
        "landmark_count": 3,
        "rasterized_sample_count": 1,
        "visibility_opportunity_count": 1,
        "hidden_or_occluded_sample_count": 2,
    })
    first_face = raster_report["motion_frames"][0]["targets"][0]["face"]
    first_face.update({
        "raster_ready": True,
        "rasterized": True,
        "visibility_opportunity": True,
        "visibility_reason": "front_facing_camera_ray_visible_face_surface",
        "landmarks": [
            {
                "id": f"face:landmark-{index}",
                "region": "mouth",
                "side": "center",
                "x": 0.30 + index * 0.10,
                "y": 0.50,
                "camera_depth": 10.0,
                "in_frame": True,
                "front_facing": True,
                "normal_view_dot": 0.9,
                "camera_ray_visible": True,
                "visible": True,
                "occluder_shape": "|Hero|faceShape",
            }
            for index in range(3)
        ],
        "guide_points": [
            {
                "id": f"face:landmark-{index}",
                "region": "mouth",
                "side": "center",
                "x": 0.30 + index * 0.10,
                "y": 0.50,
            }
            for index in range(3)
        ],
        "guide_segments": copy.deepcopy(raster_target["face_edges"]),
    })
    for frame in raster_report["motion_frames"][1:]:
        frame["targets"][0]["face"]["raster_ready"] = True
        frame["targets"][0]["face"]["visibility_reason"] = (
            "camera_ray_occluded_or_unverified"
        )
    raster_frame_paths = []
    for index, source_path in enumerate(frame_paths):
        target_path = folder / f"motion.face.{index:06d}.png"
        image = Image.open(source_path).convert("RGB")
        if index == 0:
            draw = ImageDraw.Draw(image)
            draw.line(
                (10, 9, 16, 9),
                fill=picker.MOTION_GUIDE_FACE_MOUTH_RGB,
                width=2,
            )
        image.save(target_path)
        raster_frame_paths.append(target_path)
    raster_motion_sidecar = copy.deepcopy(motion_sidecar)
    raster_motion_sidecar["motion_guide_report"] = raster_report
    raster_result = copy.deepcopy(result)
    raster_result["motion_guide_report"] = raster_report
    raster_validation = picker._validate_motion_guide_inputs(
        result=raster_result,
        color_sidecar=color_sidecar,
        motion_sidecar=raster_motion_sidecar,
        motion_frame_paths=raster_frame_paths,
        expected_frame_count=3,
        expected_fps=24,
        expected_start_frame=101,
        expected_end_frame=103,
        expected_width=32,
        expected_height=18,
    )
    assert raster_validation["face_pixel_observed"] is True
    assert raster_validation["face_semantics"]["rasterized_sample_count"] == 1

    missed_opportunity_report = copy.deepcopy(raster_report)
    missed_opportunity_report["face_semantics"][
        "rasterized_sample_count"
    ] = 0
    missed_opportunity_report["motion_frames"][0]["targets"][0]["face"][
        "rasterized"
    ] = False
    missed_opportunity_motion = copy.deepcopy(motion_sidecar)
    missed_opportunity_motion["motion_guide_report"] = (
        missed_opportunity_report
    )
    missed_opportunity_result = copy.deepcopy(result)
    missed_opportunity_result["motion_guide_report"] = (
        missed_opportunity_report
    )
    try:
        picker._validate_motion_guide_inputs(
            result=missed_opportunity_result,
            color_sidecar=color_sidecar,
            motion_sidecar=missed_opportunity_motion,
            motion_frame_paths=raster_frame_paths,
            expected_frame_count=3,
            expected_fps=24,
            expected_start_frame=101,
            expected_end_frame=103,
            expected_width=32,
            expected_height=18,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Visible face-edge opportunity without raster output was accepted."
        )

    def rejected(mutator, label):
        bad_result = copy.deepcopy(result)
        bad_color = copy.deepcopy(color_sidecar)
        bad_motion = copy.deepcopy(motion_sidecar)
        bad_paths = list(frame_paths)
        mutator(bad_result, bad_color, bad_motion, bad_paths)
        try:
            picker._validate_motion_guide_inputs(
                result=bad_result,
                color_sidecar=bad_color,
                motion_sidecar=bad_motion,
                motion_frame_paths=bad_paths,
                expected_frame_count=3,
                expected_fps=24,
                expected_start_frame=101,
                expected_end_frame=103,
                expected_width=32,
                expected_height=18,
            )
        except RuntimeError:
            return
        raise AssertionError(f"Malformed Motion Guide was accepted: {label}")

    rejected(
        lambda _r, _c, m, _p: m.update(camera="|otherCamera"),
        "camera mismatch",
    )
    rejected(
        lambda _r, _c, m, _p: m.update(hidden_paths=[]),
        "visibility mismatch",
    )
    rejected(
        lambda r, _c, _m, _p: r.update(
            motion_guide_profile="wrong"
        ),
        "profile mismatch",
    )
    rejected(
        lambda r, _c, _m, _p: r["motion_guide_report"].update(
            motion_authority="independent"
        ),
        "independent motion authority",
    )

    def mutate_both_reports(r, m, callback):
        callback(r["motion_guide_report"])
        m["motion_guide_report"] = copy.deepcopy(
            r["motion_guide_report"]
        )

    rejected(
        lambda r, _c, m, _p: mutate_both_reports(
            r,
            m,
            lambda payload: payload["face_semantics"].update(
                curve_geometry_rendered=True
            ),
        ),
        "raw curve geometry rendered",
    )
    rejected(
        lambda r, _c, m, _p: mutate_both_reports(
            r,
            m,
            lambda payload: payload["face_semantics"].update(
                channel_count=1
            ),
        ),
        "face descriptor count mismatch",
    )

    nonfinite_report = copy.deepcopy(semantic_report)
    nonfinite_report["motion_frames"][0]["targets"][0]["face"][
        "channel_values"
    ][0] = float("inf")
    nonfinite_motion = copy.deepcopy(motion_sidecar)
    nonfinite_motion["motion_guide_report"] = nonfinite_report
    nonfinite_result = copy.deepcopy(result)
    nonfinite_result["motion_guide_report"] = nonfinite_report
    try:
        picker._validate_motion_guide_inputs(
            result=nonfinite_result,
            color_sidecar=color_sidecar,
            motion_sidecar=nonfinite_motion,
            motion_frame_paths=frame_paths,
            expected_frame_count=3,
            expected_fps=24,
            expected_start_frame=101,
            expected_end_frame=103,
            expected_width=32,
            expected_height=18,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Non-finite face channel sample was accepted.")

    rogue_path = folder / "motion.rogue.png"
    rogue_image = Image.open(frame_paths[0]).convert("RGB")
    rogue_image.putpixel((0, 0), (1, 2, 3))
    rogue_image.save(rogue_path)
    rejected(
        lambda _r, _c, _m, paths: paths.__setitem__(0, rogue_path),
        "unexpected raster RGB",
    )

    undeclared_face_path = folder / "motion.undeclared-face.png"
    undeclared_face_image = Image.open(frame_paths[0]).convert("RGB")
    undeclared_face_image.putpixel(
        (0, 0), picker.MOTION_GUIDE_FACE_MOUTH_RGB
    )
    undeclared_face_image.save(undeclared_face_path)
    rejected(
        lambda _r, _c, _m, paths: paths.__setitem__(0, undeclared_face_path),
        "undeclared semantic face RGB",
    )


maya_mode_source = inspect.getsource(
    picker.HMBVideoPickerLibrary._maya_mode
)
for anchor in (
    '"generate_motion_guide": motion_guide_enabled',
    '"motion_guide_frames_folder"',
    "_validate_motion_guide_inputs(",
    'label=f"@video{motion_guide_video_slot} Motion Guide"',
    '"bundle_run_id": bundle_run_id',
    "project_motion_guide_artifact",
    "staged_motion_guide_video_path",
):
    assert anchor in maya_mode_source, anchor
runner_source = (
    ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
).read_text(encoding="utf-8")
for anchor in (
    "def _render_motion_guide_pass(",
    "maya_skin_influence_transform_blendshape_and_curve_driver_evaluation",
    "hmb-maya-face-semantics",
    "raw_nurbs_curve_geometry_never_rendered",
    "derived_decoder_of_video1_only",
    "shared_hidden_paths_plus_target_shape_animated_dag_layer_visibility",
    "MOTION_GUIDE_BACKGROUND_RGB = (0, 0, 0)",
):
    assert anchor in runner_source, anchor

widget_source = (
    ROOT / "widgets" / "HMBVideoPickerLibraryWidget_v032.js"
).read_text(encoding="utf-8")
for anchor in (
    'id="motion-guide-toggle"',
    "include_motion_guide: motionGuideEnabled",
):
    assert anchor in widget_source, anchor
# Per-frame Motion diagnostics stay in the sidecar/file report and are not
# duplicated into the picker node UI.
assert "motion_guide_report" not in widget_source
assert 'data-inherited-visibility=\\"1\\"' not in widget_source

print("HMB Motion Guide regression passed.")
