# -*- coding: utf-8 -*-
"""Maya-free regression for Motion Guide body structure and eye contours."""

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
    "HMB_Motion_Eye_Body_Regression",
    RUNNER_PATH,
)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)


class FakeCmds:
    def __init__(self):
        self.parents = {}
        self.keyed_plugs = set()

    def ls(self, *items, **kwargs):
        if kwargs.get("uuid"):
            return ["uuid:" + str(items[0])]
        if items:
            item = items[0]
            if isinstance(item, (list, tuple)):
                return list(item)
            return [item]
        return []

    def listRelatives(self, node, **kwargs):
        if kwargs.get("parent"):
            parent = self.parents.get(node)
            return [parent] if parent else []
        return []

    def nodeType(self, node, **kwargs):
        if kwargs.get("inherited"):
            return []
        if str(node).endswith("Shape"):
            return "mesh"
        if str(node).startswith("blendShape"):
            return "blendShape"
        return "transform"

    def listHistory(self, _node, **_kwargs):
        return []

    def listAttr(self, _node, **_kwargs):
        return ["translateX", "translateY", "translateZ", "unused"]

    def getAttr(self, plug, **kwargs):
        if kwargs.get("type"):
            return "double"
        return {
            "|Hero|C_eye_CTL.translateX": 1.25,
            "|Hero|C_eye_CTL.translateY": -0.25,
            "|Hero|C_eye_CTL.translateZ": 0.5,
            "|Hero|C_eye_CTL.unused": 0.0,
        }.get(plug, 0.0)

    def keyframe(self, plug, **_kwargs):
        return 4 if plug in self.keyed_plugs else 0


fake_cmds = FakeCmds()
runner.cmds = fake_cmds


# L/R suffixes used by the shipped JettMini eyelid rig must retain side.
assert runner._motion_face_semantic("C_dnEyeLidBase01L_CRV")["side"] == "left"
assert runner._motion_face_semantic("C_dnEyeLidBase01R_CRV")["side"] == "right"


# Six weighted but disconnected implementation joints are not a usable body.
# A character-reference expansion is required even though the raw count is six.
poor_influences = [
    "|Hero|L_armBridgeStart_JNT",
    "|Hero|R_armBridgeStart_JNT",
    "|Hero|L_ankle_JNT",
    "|Hero|R_ankle_JNT",
    "|Hero|L_ball_JNT",
    "|Hero|R_ball_JNT",
]
reference_skeleton = [
    "|Hero|Root_JNT",
    "|Hero|Root_JNT|Pelvis_JNT",
    "|Hero|Root_JNT|Pelvis_JNT|Spine_JNT",
    "|Hero|Root_JNT|Pelvis_JNT|Spine_JNT|Chest_JNT",
    "|Hero|Root_JNT|Pelvis_JNT|Spine_JNT|Chest_JNT|Neck_JNT",
    "|Hero|Root_JNT|Pelvis_JNT|Spine_JNT|Chest_JNT|Neck_JNT|Head_JNT",
]
for joint in poor_influences:
    fake_cmds.parents[joint] = "|Hero"
for joint in reference_skeleton:
    parts = [part for part in joint.split("|") if part]
    fake_cmds.parents[joint] = (
        "|" + "|".join(parts[:-1]) if len(parts) > 1 else ""
    )

original_skin_influences = runner._motion_skin_influence_joints
original_reference_joints = runner._motion_reference_or_namespace_joints
try:
    runner._motion_skin_influence_joints = (
        lambda _shapes: (list(poor_influences), ["skinCluster1"])
    )
    runner._motion_reference_or_namespace_joints = (
        lambda _root: list(reference_skeleton)
    )
    selected, joint_audit = runner._motion_joint_selection(
        "|Hero",
        shapes=["|Hero|bodyShape"],
        allow_skeleton=True,
        allow_reference_fallback=True,
    )
finally:
    runner._motion_skin_influence_joints = original_skin_influences
    runner._motion_reference_or_namespace_joints = original_reference_joints

assert runner._motion_root_joint(poor_influences) == ""
assert joint_audit["source"] == "character_reference_structural_fallback"
assert joint_audit["pre_fallback_selected_joint_count"] == 6
assert joint_audit["pre_fallback_connected_edge_count"] == 0
assert joint_audit["pre_fallback_semantic_root_count"] == 0
assert "no_connected_joint_edges" in joint_audit["structural_fallback_reasons"]
assert "no_semantic_root_joint" in joint_audit["structural_fallback_reasons"]
assert joint_audit["connected_edge_count"] >= 5
assert joint_audit["semantic_root_count"] >= 1
assert set(reference_skeleton).issubset(set(selected))


# Target-local eye controls are sidecar drivers only when they carry real keys.
fake_cmds.keyed_plugs = {
    "|Hero|C_eye_CTL.translateX",
    "|Hero|C_eye_CTL.translateY",
    "|Hero|C_eye_CTL.translateZ",
}
original_controller_nodes = runner._motion_face_target_controller_nodes
try:
    runner._motion_face_target_controller_nodes = (
        lambda _root: ["|Hero|C_eye_CTL"]
    )
    keyed_drivers, keyed_audit = runner._motion_face_keyed_semantic_drivers(
        "|Hero"
    )
    deduped_drivers, deduped_audit = (
        runner._motion_face_keyed_semantic_drivers(
            "|Hero",
            existing_drivers=[{
                "id": "uuid:|Hero|C_eye_CTL:translateX",
                "plug": "Hero:C_eye_CTL.translateX",
            }],
        )
    )
finally:
    runner._motion_face_target_controller_nodes = original_controller_nodes

assert {item["plug"] for item in keyed_drivers} == fake_cmds.keyed_plugs
assert all(
    item["provenance"] == "target_local_keyed_semantic_controller"
    for item in keyed_drivers
)
assert all(item["curve_geometry_rendered"] is False for item in keyed_drivers)
assert all(item["animation_evidence"]["key_count"] == 4 for item in keyed_drivers)
assert keyed_audit["keyed_semantic_driver_count"] == 3
assert keyed_audit["keyed_semantic_rejected_nonanimated_count"] == 1
assert keyed_audit["policy"] == (
    "target_scope_semantic_curve_control_keyed_numeric_plugs_only"
)
assert {item["plug"] for item in deduped_drivers} == {
    "|Hero|C_eye_CTL.translateY",
    "|Hero|C_eye_CTL.translateZ",
}
assert deduped_audit["keyed_semantic_driver_count"] == 2


# An animated ancestor transform is valid deformation evidence for a final lid.
lid_shape = "|Hero|C_upEyeLid_GEO|C_upEyeLid_GEOShape"
eye_card = "|Hero|eyesInPlane|eyesInPlaneShape"
dummy_shape = "|Hero|L_eyeDummy|L_eyeDummyShape"
original_incoming = runner._motion_face_incoming_plugs
original_path_visible = runner._motion_path_visible
original_visibility_kind = runner._visibility_connection_kind
original_intermediate = runner._is_intermediate_shape
original_diagonal = runner._motion_face_surface_diagonal
original_mesh_runtime = runner._motion_face_mesh_runtime
original_edge_indices = runner._motion_face_semantic_mesh_edge_indices
original_world_point = runner._motion_face_world_point
try:
    runner._motion_face_incoming_plugs = (
        lambda plug: ["animCurveHero.output"]
        if plug == "|Hero.rotateY"
        else []
    )
    runner._motion_path_visible = lambda _shape: True
    runner._visibility_connection_kind = lambda _node: ""
    runner._is_intermediate_shape = lambda _shape: False
    runner._motion_face_surface_diagonal = lambda _shape: 2.0
    runner._motion_face_mesh_runtime = lambda shape: {
        "shape": shape,
        "shape_id": "runtime:" + shape,
    }
    runner._motion_face_semantic_mesh_edge_indices = lambda _runtime: (
        [(0, 0, 1)],
        {
            "topology_edge_count": 1,
            "boundary_edge_count": 1,
            "selected_edge_count": 1,
            "selection_source": "boundary_edges",
            "selection_limit": (
                runner.MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE
            ),
        },
    )
    runner._motion_face_world_point = (
        lambda _runtime, vertex_index: [float(vertex_index), 0.0, 0.0]
    )

    deformation = runner._motion_face_semantic_mesh_deformation_evidence(
        lid_shape
    )
    assert deformation["eligible"] is True
    assert "|Hero" in deformation["driven_transform_nodes"]
    assert "|Hero.rotateY" in deformation["driven_transform_plugs"]

    semantic_job = {
        "_authored_cutout_snapshot": {
            lid_shape: {"shape": lid_shape, "alpha_driven": False},
            eye_card: {
                "shape": eye_card,
                "alpha_driven": True,
                "source_plug": "eyeFile.outTransparency",
                "source_material": "eyeMaterial",
                "evidence_kind": "out_transparency_input",
                "shading_group": "eyeMaterialSG",
            },
            dummy_shape: {"shape": dummy_shape, "alpha_driven": False},
        }
    }
    channels = [{
        "id": "lid-channel",
        "group": "eyelid",
        "side": "center",
        "raster_eligible": True,
    }]
    landmarks, edges, _runtime, semantic_audit = (
        runner._motion_face_semantic_surface_landmarks(
            [lid_shape, eye_card, dummy_shape],
            channels,
            job=semantic_job,
        )
    )

    assert semantic_audit["policy"] == (
        "render_scope_nonintermediate_deformed_visible_semantic_mesh_edges"
    )
    assert semantic_audit["appearance_authority"] == "zero"
    assert semantic_audit["curve_geometry_rendered"] is False
    assert semantic_audit["accepted_surface_count"] == 1
    assert semantic_audit["surfaces"][0]["shape"] == lid_shape
    assert {item["mesh"] for item in landmarks} == {lid_shape}
    assert all(
        item["anchor_method"] == "render_scope_semantic_mesh_vertex"
        for item in landmarks
    )
    assert len(landmarks) == 2
    assert len(edges) == 1
    alpha_rejection = next(
        item
        for item in semantic_audit["rejections"]
        if item["shape"] == eye_card
    )
    assert alpha_rejection["reason"] == "alpha_driven_card_excluded"
    assert alpha_rejection["source_plug"] == "eyeFile.outTransparency"
    assert any(
        item["shape"] == dummy_shape
        and item["reason"] == "helper_or_target_name"
        for item in semantic_audit["rejections"]
    )

    bounded_lids = [
        "|Hero|L_eyeLid{0}_GEO|L_eyeLid{0}_GEOShape".format(index)
        for index in range(runner.MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES + 1)
    ]
    bounded_job = {
        "_authored_cutout_snapshot": {
            shape: {"shape": shape, "alpha_driven": False}
            for shape in bounded_lids
        }
    }
    bounded_landmarks, bounded_edges, _runtime, bounded_audit = (
        runner._motion_face_semantic_surface_landmarks(
            bounded_lids,
            channels,
            job=bounded_job,
        )
    )
    assert bounded_audit["accepted_surface_count"] == (
        runner.MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES
    )
    assert bounded_audit["truncated_surface_count"] == 1
    assert any(
        item["reason"] == "semantic_surface_limit_exceeded"
        for item in bounded_audit["rejections"]
    )
    assert len(bounded_landmarks) <= (
        runner.MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES
        * runner.MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE
    )
    assert len(bounded_edges) <= (
        runner.MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES
        * runner.MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE
    )
finally:
    runner._motion_face_incoming_plugs = original_incoming
    runner._motion_path_visible = original_path_visible
    runner._visibility_connection_kind = original_visibility_kind
    runner._is_intermediate_shape = original_intermediate
    runner._motion_face_surface_diagonal = original_diagonal
    runner._motion_face_mesh_runtime = original_mesh_runtime
    runner._motion_face_semantic_mesh_edge_indices = original_edge_indices
    runner._motion_face_world_point = original_world_point


# Eye pixels come only from verified spatial edges. Keyed drivers alone do not
# invent a gaze glyph or other screen-space control geometry.
original_numeric_value = runner._motion_face_numeric_value
original_projection_sample = runner._motion_face_landmark_projection_sample
original_ray_visibility = runner._motion_face_apply_ray_visibility
try:
    runner._motion_face_numeric_value = lambda _plug: 1.0

    def projection_sample(landmark_runtime, _projection):
        first = landmark_runtime["id"] == "eye-a"
        x = 0.2 if first else 0.8
        return {
            "id": landmark_runtime["id"],
            "region": "eyelid",
            "side": "center",
            "x": x,
            "y": 0.5,
            "front_facing": True,
            "in_frame": True,
            "visible": False,
            "_pixel_x": x * 99.0,
            "_pixel_y": 49.5,
        }

    runner._motion_face_landmark_projection_sample = projection_sample

    def visible_sample(sample, *_args, **_kwargs):
        sample["camera_ray_visible"] = True
        sample["visible"] = True
        return sample

    runner._motion_face_apply_ray_visibility = visible_sample
    spatial_target = {
        "target_index": 1,
        "face_channels": [{"weight_plug": "lidBS.weight[0]"}],
        "face_drivers": [],
        "face_landmark_audit": {
            "raster_ready": True,
            "surface_diagonal": 2.0,
        },
        "face_landmark_runtime": [{"id": "eye-a"}, {"id": "eye-b"}],
        "face_edges": [{
            "from": "eye-a",
            "to": "eye-b",
            "region": "eyelid",
        }],
    }
    spatial_frame = runner._motion_face_frame_sample(
        spatial_target,
        projection={},
        visible_mesh_records=[],
        width=100,
        height=100,
    )
    assert spatial_frame["rasterized"] is True
    spatial_canvas = runner._motion_canvas(100, 100)
    runner._motion_draw_face_frame(
        spatial_canvas,
        100,
        100,
        spatial_frame,
    )
    assert bytes(runner.MOTION_GUIDE_FACE_EYE_RGB) in bytes(spatial_canvas)

    driver_only_target = {
        "target_index": 1,
        "face_channels": [],
        "face_drivers": [{"plug": "|Hero|C_eye_CTL.translateX"}],
        "face_landmark_audit": {"raster_ready": False},
        "face_landmark_runtime": [],
        "face_edges": [],
    }
    driver_only_frame = runner._motion_face_frame_sample(
        driver_only_target,
        projection={},
        visible_mesh_records=[],
        width=100,
        height=100,
    )
    assert driver_only_frame["available"] is False
    assert driver_only_frame["rasterized"] is False
    driver_only_canvas = runner._motion_canvas(100, 100)
    unchanged = bytes(driver_only_canvas)
    runner._motion_draw_face_frame(
        driver_only_canvas,
        100,
        100,
        driver_only_frame,
    )
    assert bytes(driver_only_canvas) == unchanged
finally:
    runner._motion_face_numeric_value = original_numeric_value
    runner._motion_face_landmark_projection_sample = original_projection_sample
    runner._motion_face_apply_ray_visibility = original_ray_visibility


print("Motion eye/body regression checks passed.")
