# -*- coding: utf-8 -*-
"""Maya-free safety regression for semantic Motion Guide face anchors."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"

maya_package = types.ModuleType("maya")
maya_cmds_module = types.ModuleType("maya.cmds")
maya_package.cmds = maya_cmds_module
sys.modules.setdefault("maya", maya_package)
sys.modules.setdefault("maya.cmds", maya_cmds_module)

spec = importlib.util.spec_from_file_location(
    "HMB_Motion_Face_Safety_Regression",
    RUNNER_PATH,
)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)

runner_source = RUNNER_PATH.read_text(encoding="utf-8")
assert runner.MOTION_GUIDE_FACE_FIRST_HIT_TOLERANCE_FRACTION == 0.005
assert "verified_surface_symmetry_mirror" not in runner_source
delta_reader_source = runner_source[
    runner_source.index("def _motion_face_blendshape_delta_scores("):
    runner_source.index("def _motion_face_object_points(")
]
assert "setAttr" not in delta_reader_source


# The current authored face result is complete only with all ten coarse slots.
complete_slots = [
    ("brow", "left"),
    ("brow", "right"),
    ("eyelid", "left"),
    ("eyelid", "right"),
    ("mouth", "left"),
    ("mouth", "center"),
    ("mouth", "right"),
    ("jaw", "left"),
    ("jaw", "center"),
    ("jaw", "right"),
]
complete_candidates = [
    {"region": region, "side": side, "vertex_index": index}
    for index, (region, side) in enumerate(complete_slots)
]
original_object_points = runner._motion_face_object_points
try:
    runner._motion_face_object_points = lambda _runtime: [
        [float(index % 3), float(index // 3), float(index % 2) * 0.1]
        for index in range(10)
    ]
    completed, complete_audit = runner._motion_face_complete_bilateral_and_jaw(
        complete_candidates,
        {"shape": "|Hero|faceShape"},
        [],
    )
finally:
    runner._motion_face_object_points = original_object_points
assert {(item["region"], item["side"]) for item in completed} == set(
    complete_slots
)
assert len(completed) == 10
assert complete_audit["mirrored_count"] == 0
assert complete_audit["inferred_jaw_count"] == 0
assert complete_audit["mirror_policy"] == (
    "bounded_two_pair_bilateral_offset_no_topology_symmetry_claim"
)


# When both jaw sides are already localized but the direct mouth-center offset
# would resolve back to the mouth vertex, the bilateral jaw midpoint provides
# a bounded same-surface center anchor.
midpoint_points = [
    [-1.0, 2.0, 0.0],
    [1.0, 2.0, 0.0],
    [-1.0, 1.0, 0.0],
    [1.0, 1.0, 0.0],
    [-1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [-1.0, -1.0, 0.0],
    [1.0, -1.0, 0.0],
    [0.0, -1.0, 0.0],
]
midpoint_candidates = [
    {"region": "brow", "side": "left", "vertex_index": 0},
    {"region": "brow", "side": "right", "vertex_index": 1},
    {"region": "eyelid", "side": "left", "vertex_index": 2},
    {"region": "eyelid", "side": "right", "vertex_index": 3},
    {"region": "mouth", "side": "left", "vertex_index": 4},
    {"region": "mouth", "side": "center", "vertex_index": 5},
    {"region": "mouth", "side": "right", "vertex_index": 6},
    {"region": "jaw", "side": "left", "vertex_index": 7},
    {"region": "jaw", "side": "right", "vertex_index": 8},
]
original_world_point = runner._motion_face_world_point
try:
    runner._motion_face_object_points = lambda _runtime: midpoint_points
    runner._motion_face_world_point = (
        lambda _runtime, vertex_index: list(midpoint_points[vertex_index])
    )
    midpoint_completed, midpoint_audit = (
        runner._motion_face_complete_bilateral_and_jaw(
            midpoint_candidates,
            {"shape": "|Hero|faceShape"},
            [{"id": "jaw-center", "group": "jaw", "side": "center"}],
        )
    )
finally:
    runner._motion_face_object_points = original_object_points
    runner._motion_face_world_point = original_world_point
midpoint_center = next(
    item
    for item in midpoint_completed
    if (item["region"], item["side"]) == ("jaw", "center")
)
assert midpoint_center["vertex_index"] == 9
assert midpoint_center["anchor_source"] == (
    "semantic_bilateral_jaw_midpoint_surface_inference"
)
assert midpoint_center["channel_ids"] == {"jaw-center"}
assert midpoint_audit["inferred_jaw_count"] == 1
midpoint_evidence = next(
    item
    for item in midpoint_audit["jaw_evidence"]
    if item["side"] == "center"
)
assert midpoint_evidence["bilateral_span_position"] == 0.5
assert midpoint_evidence["downward_progress_fraction"] > 0.02


# If the bilateral midpoint resolves to a surface point that is too close to
# mouth center, preserve that rejection and test the -up*0.10 diagonal fallback
# against all the same center/span/snap gates.
fallback_points = [
    [-1.0, 2.0, 0.0],
    [1.0, 2.0, 0.0],
    [-1.0, 1.0, 0.0],
    [1.0, 1.0, 0.0],
    [-1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [-1.0, -0.05, 0.0],
    [1.0, -0.05, 0.0],
    [0.0, -0.05, 0.0],
    [0.0, -0.40, 0.0],
]
try:
    runner._motion_face_object_points = lambda _runtime: fallback_points
    runner._motion_face_world_point = (
        lambda _runtime, vertex_index: list(fallback_points[vertex_index])
    )
    fallback_completed, fallback_audit = (
        runner._motion_face_complete_bilateral_and_jaw(
            midpoint_candidates,
            {"shape": "|Dog|faceShape"},
            [{"id": "jaw-center", "group": "jaw", "side": "center"}],
        )
    )
finally:
    runner._motion_face_object_points = original_object_points
    runner._motion_face_world_point = original_world_point
fallback_center = next(
    item
    for item in fallback_completed
    if (item["region"], item["side"]) == ("jaw", "center")
)
assert fallback_center["vertex_index"] == 10
assert fallback_center["anchor_source"] == (
    "semantic_face_axis_center_surface_fallback"
)
assert "jaw:center:insufficient_downward_progress" in fallback_audit[
    "completion_rejections"
]
fallback_evidence = next(
    item
    for item in fallback_audit["jaw_evidence"]
    if item["method"] == "semantic_face_axis_center_surface_fallback"
)
assert fallback_evidence["desired_offset_fraction"] == 0.10
assert fallback_evidence["downward_progress_fraction"] >= 0.02
assert 0.0 <= fallback_evidence["bilateral_span_position"] <= 1.0


# A muzzle can put mouth:center on a shallower surface than both side-mouth
# pairs.  In that case the fixed axis candidate remains too far from surface,
# while the bilateral jaw profile supplies a same-surface depth coordinate and
# an independently evidenced mean side downward distance.
profile_points = [
    [-1.0, 2.0, 0.0],
    [1.0, 2.0, 0.0],
    [-1.0, 1.0, 0.0],
    [1.0, 1.0, 0.0],
    [-1.0, 0.0, 0.0],
    [0.5, -0.35, 0.0],
    [1.0, 0.0, 0.0],
    [-1.0, -0.40, 1.0],
    [1.0, -0.40, 1.0],
    [0.0, -0.40, 1.0],
    [0.0, -0.75, 1.0],
]
try:
    runner._motion_face_object_points = lambda _runtime: profile_points
    runner._motion_face_world_point = (
        lambda _runtime, vertex_index: list(profile_points[vertex_index])
    )
    profile_completed, profile_audit = (
        runner._motion_face_complete_bilateral_and_jaw(
            midpoint_candidates,
            {"shape": "|Muzzle|faceShape"},
            [{"id": "jaw-center", "group": "jaw", "side": "center"}],
        )
    )
finally:
    runner._motion_face_object_points = original_object_points
    runner._motion_face_world_point = original_world_point
profile_center = next(
    item
    for item in profile_completed
    if (item["region"], item["side"]) == ("jaw", "center")
)
assert profile_center["vertex_index"] == 10
assert profile_center["anchor_source"] == (
    "semantic_bilateral_jaw_surface_profile_inference"
)
assert "jaw:center:insufficient_downward_progress" in profile_audit[
    "completion_rejections"
]
assert "jaw:center:fallback_surface_snap_outside_bound" in profile_audit[
    "completion_rejections"
]
profile_evidence = next(
    item
    for item in profile_audit["jaw_evidence"]
    if item["method"] == "semantic_bilateral_jaw_surface_profile_inference"
)
assert profile_evidence["left_downward_progress_fraction"] >= 0.02
assert profile_evidence["right_downward_progress_fraction"] >= 0.02
assert profile_evidence["side_downward_disagreement_fraction"] == 0.0
assert profile_evidence["bilateral_span_position"] == 0.5
assert profile_evidence["surface_snap_fraction"] == 0.0
profile_candidate_audit = profile_audit["jaw_center_candidate_evidence"][-1]
assert profile_candidate_audit["status"] == "accepted"
assert profile_candidate_audit["jaw_midpoint_lateral_drift_fraction"] == 0.0
assert profile_candidate_audit["mouth_center_lateral_offset_fraction"] > (
    profile_candidate_audit["maximum_center_drift_fraction"]
)


# Rejected profile candidates retain every decision metric so a live Maya
# probe can distinguish snap, progress, span, and center failures.
rejected_profile_points = [list(point) for point in profile_points]
rejected_profile_points[10][0] = 0.16
try:
    runner._motion_face_object_points = lambda _runtime: rejected_profile_points
    runner._motion_face_world_point = (
        lambda _runtime, vertex_index: list(
            rejected_profile_points[vertex_index]
        )
    )
    rejected_profile_completed, rejected_profile_audit = (
        runner._motion_face_complete_bilateral_and_jaw(
            midpoint_candidates,
            {"shape": "|MuzzleOffset|faceShape"},
            [{"id": "jaw-center", "group": "jaw", "side": "center"}],
        )
    )
finally:
    runner._motion_face_object_points = original_object_points
    runner._motion_face_world_point = original_world_point
assert ("jaw", "center") not in {
    (item["region"], item["side"])
    for item in rejected_profile_completed
}
rejected_candidate_audit = rejected_profile_audit[
    "jaw_center_candidate_evidence"
][-1]
assert rejected_candidate_audit["status"] == "rejected"
assert rejected_candidate_audit["rejection"] == (
    "jaw:center:profile_no_eligible_surface_vertex"
)
assert rejected_candidate_audit["nearest_scanned_rejection"] == (
    "jaw:center:profile_lateral_center_drift_outside_bound"
)
rejected_metrics = rejected_candidate_audit["nearest_scanned_metrics"]
for metric in (
    "downward_progress_fraction",
    "jaw_midpoint_lateral_drift_fraction",
    "mouth_center_lateral_drift_fraction",
    "maximum_center_drift_fraction",
    "bilateral_span_position",
    "surface_snap_fraction",
):
    assert metric in rejected_metrics, metric
assert "bilateral_jaw_span_fraction" in rejected_candidate_audit
assert rejected_candidate_audit["scanned_candidate_count"] > 0
assert rejected_candidate_audit["eligible_candidate_count"] == 0


# The geometrically nearest point may fail the unchanged center strip while a
# slightly farther point in the same 0.06-diagonal snap sphere is safe.  The
# safe point wins by deterministic (distance, vertex_index) scoring only after
# all semantic gates have run.
ranked_profile_points = [list(point) for point in rejected_profile_points]
ranked_profile_points.append([0.0, -0.57, 1.0])
try:
    runner._motion_face_object_points = lambda _runtime: ranked_profile_points
    runner._motion_face_world_point = (
        lambda _runtime, vertex_index: list(
            ranked_profile_points[vertex_index]
        )
    )
    ranked_completed, ranked_audit = (
        runner._motion_face_complete_bilateral_and_jaw(
            midpoint_candidates,
            {"shape": "|MuzzleRanked|faceShape"},
            [{"id": "jaw-center", "group": "jaw", "side": "center"}],
        )
    )
finally:
    runner._motion_face_object_points = original_object_points
    runner._motion_face_world_point = original_world_point
ranked_center = next(
    item
    for item in ranked_completed
    if (item["region"], item["side"]) == ("jaw", "center")
)
assert ranked_center["vertex_index"] == 11
ranked_candidate_audit = ranked_audit["jaw_center_candidate_evidence"][-1]
assert ranked_candidate_audit["status"] == "accepted"
assert ranked_candidate_audit["nearest_scanned_vertex_index"] == 10
assert ranked_candidate_audit["nearest_scanned_rejection"] == (
    "jaw:center:profile_lateral_center_drift_outside_bound"
)
assert ranked_candidate_audit["scanned_candidate_count"] >= 2
assert ranked_candidate_audit["eligible_candidate_count"] >= 1
assert ranked_candidate_audit["selection_score_policy"] == (
    "surface_distance_then_vertex_index"
)
assert ranked_candidate_audit["selected_score"][1] == 11


# Conflicting lateral evidence must not be promoted to a topology-symmetry
# claim.  This keeps rotated or irregular rigs fail-closed.
conflicting_candidates = [
    {"region": "brow", "side": "left", "vertex_index": 0},
    {"region": "eyelid", "side": "left", "vertex_index": 1},
    {"region": "eyelid", "side": "right", "vertex_index": 2},
    {"region": "mouth", "side": "left", "vertex_index": 3},
    {"region": "mouth", "side": "right", "vertex_index": 4},
]
conflicting_points = [
    [-1.0, 1.5, 0.0],
    [-1.0, 1.0, 0.0],
    [1.0, 1.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0],
]
try:
    runner._motion_face_object_points = lambda _runtime: conflicting_points
    conflicted, conflict_audit = runner._motion_face_complete_bilateral_and_jaw(
        conflicting_candidates,
        {"shape": "|Irregular|faceShape"},
        [{"id": "brow-right", "group": "brow", "side": "right"}],
    )
finally:
    runner._motion_face_object_points = original_object_points
assert ("brow", "right") not in {
    (item["region"], item["side"]) for item in conflicted
}
assert "brow:right:bilateral_direction_disagreement" in conflict_audit[
    "completion_rejections"
]


# First-hit tolerance is exactly 0.5% of the face diagonal.
original_closest_hit = runner._motion_face_closest_ray_hit
hit_distance = [9.5]
extra_distances = []


def closest_hit(_origin, _point, _records, extra, performance=None):
    extra_distances.append(float(extra))
    return {
        "distance": hit_distance[0],
        "point_distance": 10.0,
        "shape": "|Hero|faceShape",
        "target_index": 1,
    }


def ray_sample():
    return {
        "front_facing": True,
        "in_frame": True,
        "_world_point": [0.0, 0.0, 10.0],
        "_surface_shape": "|Hero|faceShape",
    }


try:
    runner._motion_face_closest_ray_hit = closest_hit
    boundary = runner._motion_face_apply_ray_visibility(
        ray_sample(),
        {"camera_origin": [0.0, 0.0, 0.0]},
        1,
        [{"shape": "|Hero|faceShape"}],
        100.0,
    )
    hit_distance[0] = 9.4999
    outside = runner._motion_face_apply_ray_visibility(
        ray_sample(),
        {"camera_origin": [0.0, 0.0, 0.0]},
        1,
        [{"shape": "|Hero|faceShape"}],
        100.0,
    )
finally:
    runner._motion_face_closest_ray_hit = original_closest_hit
assert extra_distances == [0.5, 0.5]
assert boundary["visible"] is True
assert outside["visible"] is False


# Two visible points may rasterize only when they are endpoints of the same
# declared semantic edge.  Unrelated points short-circuit every ray.
target = {
    "target_index": 1,
    "face_channels": [{"weight_plug": "face.weight[0]"}],
    "face_drivers": [],
    "face_landmark_audit": {"raster_ready": True, "surface_diagonal": 100.0},
    "face_edges": [
        {"from": "face:0", "to": "face:1", "region": "mouth"},
        {"from": "face:1", "to": "face:2", "region": "mouth"},
    ],
}


def projected_sample(item, _projection):
    return dict(item["sample"])


def sample(index, front):
    return {
        "id": "face:{0}".format(index),
        "region": "mouth",
        "side": "center",
        "x": 0.1 + index * 0.3,
        "y": 0.5,
        "camera_depth": 10.0,
        "in_frame": True,
        "front_facing": bool(front),
        "normal_view_dot": 0.9 if front else -0.9,
        "camera_ray_visible": False,
        "visible": False,
        "occluder_shape": "",
        "_pixel_x": float(10 + index * 30),
        "_pixel_y": 50.0,
        "_world_point": [0.0, 0.0, 10.0],
        "_surface_shape": "|Hero|faceShape",
    }


original_numeric_value = runner._motion_face_numeric_value
original_projection_sample = runner._motion_face_landmark_projection_sample
original_closest_hit = runner._motion_face_closest_ray_hit
try:
    runner._motion_face_numeric_value = lambda _plug: 0.5
    runner._motion_face_landmark_projection_sample = projected_sample
    runner._motion_face_closest_ray_hit = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(
            AssertionError("Unrelated face points must not trigger a ray.")
        )
    )
    unrelated_target = dict(target)
    unrelated_target["face_landmark_runtime"] = [
        {"sample": sample(0, True)},
        {"sample": sample(1, False)},
        {"sample": sample(2, True)},
    ]
    performance = {}
    unrelated_frame = runner._motion_face_frame_sample(
        unrelated_target,
        {"camera_origin": [0.0, 0.0, 0.0]},
        [],
        100,
        100,
        performance=performance,
    )
finally:
    runner._motion_face_numeric_value = original_numeric_value
    runner._motion_face_landmark_projection_sample = original_projection_sample
    runner._motion_face_closest_ray_hit = original_closest_hit
assert unrelated_frame["rasterized"] is False
assert unrelated_frame["visibility_opportunity"] is False
assert performance.get("face_landmark_ray_test_count", 0) == 0
assert performance["face_frame_ray_gate_short_circuit_count"] == 1


print("HMB Motion face safety regression: PASS")
