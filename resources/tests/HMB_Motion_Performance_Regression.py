# -*- coding: utf-8 -*-
"""Maya-free regression coverage for Motion Guide work short-circuits."""

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
    "HMB_Motion_Performance_Regression",
    RUNNER_PATH,
)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)


# A path is evaluated once per caller-owned frame cache, never across frames.
visibility_calls = []
original_path_visible = runner._motion_path_visible
try:
    runner._motion_path_visible = lambda path: (
        visibility_calls.append(path) or True
    )
    cache = {}
    counters = {}
    assert runner._motion_cached_path_visible("|Hero", cache, counters)
    assert runner._motion_cached_path_visible("|Hero", cache, counters)
    assert visibility_calls == ["|Hero"]
    assert counters == {
        "path_visibility_cache_miss_count": 1,
        "path_visibility_cache_hit_count": 1,
    }
    assert runner._motion_cached_path_visible("|Hero", {})
    assert visibility_calls == ["|Hero", "|Hero"]
finally:
    runner._motion_path_visible = original_path_visible


# Root false and the first true shape both terminate visibility traversal.
calls = []
assert runner._motion_target_visible(
    {"source_root": "|Hidden", "shapes": ["shapeA", "shapeB"]},
    lambda path: calls.append(path) or False,
) is False
assert calls == ["|Hidden"]

calls = []


def first_shape_visible(path):
    calls.append(path)
    return path in {"|Visible", "shapeA"}


target_counters = {}
assert runner._motion_target_visible(
    {"source_root": "|Visible", "shapes": ["shapeA", "shapeB"]},
    first_shape_visible,
    target_counters,
) is True
assert calls == ["|Visible", "shapeA"]
assert target_counters == {
    "target_shape_visibility_check_count": 1,
    "target_shape_any_short_circuit_count": 1,
}


# Occluder visibility is evaluated exactly once by the per-frame prefilter.
calls = []
occluder_counters = {}
visible_records = runner._motion_face_visible_occlusion_meshes(
    [
        {"shape": "faceA"},
        {"shape": "faceB"},
        {"shape": "hiddenFace"},
    ],
    lambda path: calls.append(path) or path != "hiddenFace",
    occluder_counters,
)
assert [record["shape"] for record in visible_records] == ["faceA", "faceB"]
assert calls == ["faceA", "faceB", "hiddenFace"]
assert occluder_counters == {
    "face_occluder_candidate_mesh_sample_count": 3,
    "face_occluder_visible_mesh_sample_count": 2,
}


class RayOM:
    class MSpace:
        kWorld = 0

    MFloatPoint = staticmethod(lambda *values: values)
    MFloatVector = staticmethod(lambda *values: values)


class RayMesh:
    def __init__(self):
        self.calls = 0

    def closestIntersection(self, *_args):
        self.calls += 1
        return (object(), 10.0)


# The ray helper trusts its visible-only input and never repeats DAG queries.
ray_mesh = RayMesh()
original_path_visible = runner._motion_path_visible
try:
    runner._motion_path_visible = lambda _path: (_ for _ in ()).throw(
        AssertionError("Ray traversal repeated a DAG visibility query.")
    )
    ray_counters = {}
    hit = runner._motion_face_closest_ray_hit(
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 10.0],
        [{
            "shape": "faceA",
            "target_index": 1,
            "om": RayOM,
            "mesh_function": ray_mesh,
        }],
        1.0,
        performance=ray_counters,
    )
finally:
    runner._motion_path_visible = original_path_visible
assert hit["shape"] == "faceA"
assert ray_mesh.calls == 1
assert ray_counters == {"face_mesh_intersection_test_count": 1}


def face_sample(index, front=True, in_frame=True):
    return {
        "id": "face:{0}".format(index),
        "region": "mouth",
        "side": "center",
        "x": round(0.1 + index * 0.3, 7),
        "y": 0.5,
        "camera_depth": 10.0,
        "in_frame": bool(in_frame),
        "front_facing": bool(front),
        "normal_view_dot": 0.9 if front else -0.9,
        "camera_ray_visible": False,
        "visible": False,
        "occluder_shape": "",
        "_pixel_x": float(10 + index * 30),
        "_pixel_y": 50.0,
        "_world_point": [0.0, 0.0, 10.0],
        "_surface_shape": "faceA",
    }


base_target = {
    "target_index": 1,
    "face_channels": [{"weight_plug": "face.weight[0]"}],
    "face_drivers": [{"plug": "face_CTL.smile"}],
    "face_landmark_audit": {
        "raster_ready": True,
        "surface_diagonal": 100.0,
    },
    "face_edges": [
        {"from": "face:0", "to": "face:1", "region": "mouth"},
        {"from": "face:1", "to": "face:2", "region": "mouth"},
    ],
}
projection = {"camera_origin": [0.0, 0.0, 0.0]}
originals = {
    "numeric": runner._motion_face_numeric_value,
    "projection": runner._motion_face_landmark_projection_sample,
    "ray": runner._motion_face_closest_ray_hit,
}
try:
    runner._motion_face_numeric_value = lambda _plug: 0.5
    runner._motion_face_landmark_projection_sample = (
        lambda item, _projection: dict(item["sample"])
    )

    # One front/in-frame point preserves values and rejects the raster without
    # issuing even one ray.
    gated_target = dict(base_target)
    gated_target["face_landmark_runtime"] = [
        {"sample": face_sample(0)},
        {"sample": face_sample(1, front=False)},
        {"sample": face_sample(2, front=False)},
    ]
    runner._motion_face_closest_ray_hit = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(AssertionError("Frame gate failed."))
    )
    gated_counters = {}
    gated = runner._motion_face_frame_sample(
        gated_target,
        projection,
        [],
        100,
        100,
        performance=gated_counters,
    )
    assert gated["visibility_reason"] == (
        "back_facing_edge_on_or_out_of_frame"
    )
    assert gated["channel_values"] == [0.5]
    assert gated["driver_values"] == [0.5]
    assert gated_counters["face_landmark_projection_sample_count"] == 3
    assert gated_counters["face_landmark_front_in_frame_sample_count"] == 1
    assert gated_counters["face_frame_ray_gate_short_circuit_count"] == 1
    assert gated_counters["face_landmark_ray_skip_count"] == 1
    assert gated_counters.get("face_landmark_ray_test_count", 0) == 0

    # Two eligible points are a valid partial contour and must issue rays.
    visible_target = dict(base_target)
    visible_target["face_landmark_runtime"] = [
        {"sample": face_sample(0)},
        {"sample": face_sample(1)},
        {"sample": face_sample(2, front=False)},
    ]

    def visible_hit(_origin, _point, records, _extra, performance=None):
        runner._motion_perf_increment(
            performance,
            "face_mesh_intersection_test_count",
            len(records),
        )
        return {
            "distance": 10.0,
            "shape": "faceA",
            "target_index": 1,
            "point_distance": 10.0,
        }

    runner._motion_face_closest_ray_hit = visible_hit
    visible_counters = {}
    visible = runner._motion_face_frame_sample(
        visible_target,
        projection,
        [{"shape": "faceA"}],
        100,
        100,
        performance=visible_counters,
    )
finally:
    runner._motion_face_numeric_value = originals["numeric"]
    runner._motion_face_landmark_projection_sample = originals["projection"]
    runner._motion_face_closest_ray_hit = originals["ray"]

assert visible["rasterized"] is True
assert visible["visibility_reason"] == (
    "front_facing_camera_ray_visible_face_surface"
)
assert len(visible["guide_points"]) == 2
assert visible["guide_segments"] == base_target["face_edges"][:1]
assert visible_counters["face_landmark_ray_test_count"] == 2
assert visible_counters["face_mesh_intersection_test_count"] == 2

source = RUNNER_PATH.read_text(encoding="utf-8")
assert '"motion_performance_telemetry"' in source
assert '"hmb-motion-performance-counters"' in source

print("HMB Motion Guide performance regression: PASS")
