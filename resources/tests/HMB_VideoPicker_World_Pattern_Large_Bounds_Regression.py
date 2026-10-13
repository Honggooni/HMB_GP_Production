"""Real world-pattern shader planning for large assets, with an offline Maya API.

No Maya process, render, user scene, or network is used. Shader attribute writes
and host report validation are real; only the DCC node API is represented here.
"""
from __future__ import annotations

import copy
import importlib.util
import math
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = Path(os.environ.get("HMB_WORLD_PATTERN_RUNNER", str(
    ROOT / "resources/maya/HMB_Maya_Background_Preview.py")))
POLICY = "vp2_repeat_safe_cell_v1"
LIMIT = 4096.0


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Import the renderer without initializing Maya or running its main entry point.
with mock.patch.dict(sys.modules, {
    "maya": types.ModuleType("maya"),
    "maya.cmds": types.ModuleType("maya.cmds"),
}):
    runner = load_module("hmb_large_world_pattern_runner", RUNNER_PATH)
picker = load_module("hmb_large_world_pattern_picker", ROOT / "HMBVideoPickerLibrary.py")


class SceneAPI:
    def __init__(self, bounds, scale=(1.0, 1.0, 1.0)):
        self.bounds = list(bounds)
        self.scale = tuple(scale)
        self.attributes = {}
        self.connections = []
        self.parent_constraints = []
        self.scale_constraints = []
        self.parents = []
        self.positions = []

    def exactWorldBoundingBox(self, shapes, **kwargs):
        assert shapes == ["|Environment|SkyShape"]
        assert kwargs == {"ignoreInvisible": False}
        return self.bounds

    def objExists(self, name):
        return True

    def nodeType(self, name):
        return "transform" if name == "|Environment" else "grid"

    def shadingNode(self, node_type, **kwargs):
        return kwargs["name"]

    def createNode(self, node_type, **kwargs):
        return kwargs["name"]

    def attributeQuery(self, attribute, **kwargs):
        return ["Off:Planar:Spherical:Cylindrical:Ball:Cubic:TriPlanar"]

    def setAttr(self, attribute, *values, **kwargs):
        self.attributes[attribute] = tuple(values)

    def connectAttr(self, source, destination, **kwargs):
        self.connections.append((source, destination))

    def parentConstraint(self, root, anchor, **kwargs):
        self.parent_constraints.append((root, anchor, kwargs))
        return [anchor + "_parentConstraint"]

    def scaleConstraint(self, root, anchor, **kwargs):
        self.scale_constraints.append((root, anchor, kwargs))
        return [anchor + "_scaleConstraint"]

    def getAttr(self, attribute):
        assert attribute.endswith(".scale")
        return [self.scale]

    def parent(self, node, anchor, **kwargs):
        self.parents.append((node, anchor, kwargs))
        return [anchor + "|" + node]

    def xform(self, node, **kwargs):
        self.positions.append((node, kwargs))


def confirmation(row):
    row = copy.deepcopy(row)
    row["reference_frame"] = 101.0
    report = {
        "profile": picker.MAYA_WORLD_PATTERN_PROFILE,
        "coordinate_space": "background_root", "camera_anchored": False,
        "uv_dependent": False, "root_scale_followed": True,
        "world_cell_scale_compensated": True,
        "base_cell_world_units": 15.0, "density_multiplier": 3.0,
        "cell_size_world_units": 5.0, "reference_frame": 101.0,
        "pattern_binding_count": 1, "projection_node_count": 1,
        "projector_node_count": 1, "patterns": [row],
        "repeat_safety_policy": POLICY, "texture_repeat_limit": LIMIT,
        "requested_cell_size_world_units": 5.0,
        "adaptive_binding_count": int(row.get("adaptive_cell_applied", False)),
    }
    return {"world_pattern_profile": picker.MAYA_WORLD_PATTERN_PROFILE,
            "world_pattern_report": report,
            "world_pattern_render_options": {
                key: True for key in ("output_transform_disabled", "multisample_disabled",
                    "line_aa_disabled", "ssao_disabled", "motion_blur_disabled")}}


class LargeWorldPatternTests(unittest.TestCase):
    def plan(self, bounds, pattern="sky_grid", scale=(1.0, 1.0, 1.0)):
        scene = SceneAPI(bounds, scale)
        with tempfile.TemporaryDirectory(prefix="hmb-large-pattern-") as directory, \
                mock.patch.object(runner, "cmds", scene), \
                mock.patch.object(runner, "_world_pattern_texture", return_value=("place2d", "gridTexture")), \
                mock.patch.object(runner, "_projected_surface_group", return_value="patternSG"):
            group, row, projection = runner._world_projected_pattern_group(
                "LargePattern", pattern, "|Environment", ["|Environment|SkyShape"], directory, 5.0)
        self.assertEqual(group, "patternSG")
        self.assertTrue(projection)
        self.assertEqual(row["world_bounds"], list(bounds))
        self.assertEqual(row["repeat_safety_policy"], POLICY)
        self.assertEqual(row["texture_repeat_limit"], LIMIT)
        self.assertEqual(row["requested_cell_size_world_units"], 5.0)
        effective = row["effective_cell_size_world_units"]
        self.assertTrue(math.isfinite(effective) and effective >= 5.0)
        self.assertEqual(row["cell_size_world_units"], effective)
        self.assertAlmostEqual(row["cell_scale_factor"], effective / 5.0)
        self.assertEqual(list(scene.attributes["place2d.repeatU"]), [row["baked_repeat_count"][0]])
        self.assertEqual(list(scene.attributes["place2d.repeatV"]), [row["baked_repeat_count"][1]])
        for repeat in row["baked_repeat_count"]:
            self.assertTrue(math.isfinite(repeat) and 1.0 <= repeat <= LIMIT)
        # The finite root-space coverage stays at its measured size. Density
        # is adjusted explicitly, not by detaching or shrinking the projector.
        width = max(bounds[3] - bounds[0], 5.0)
        height = max(bounds[4] - bounds[1], 5.0)
        depth = max(bounds[5] - bounds[2], 5.0)
        expected_extents = [width, depth, max(height * 2, 5.0)] if pattern == "floor_grid" else [max(width, height, depth, 5.0)] * 3
        self.assertEqual(row["projector_extent_world_units"], expected_extents)
        self.assertEqual(len(scene.parent_constraints), 1)
        self.assertEqual(len(scene.scale_constraints), 1)
        self.assertEqual(scene.parent_constraints[0][0], "|Environment")
        self.assertEqual(scene.scale_constraints[0][0], "|Environment")
        self.assertFalse(row["camera_anchored"])
        self.assertFalse(row["uv_dependent"])
        self.assertTrue(row["root_scale_followed"])
        self.assertTrue(row["world_cell_scale_compensated"])
        self.assertEqual(scene.attributes[row["scale_compensator_node"] + ".operation"], (2,))
        axes = ("scaleX", "scaleZ", "scaleY") if pattern == "floor_grid" else ("scaleX", "scaleY", "scaleZ")
        for destination_axis, source_axis in zip("XYZ", axes):
            self.assertIn((row["anchor_node"] + "." + source_axis,
                           row["scale_compensator_node"] + ".input2" + destination_axis), scene.connections)
        center = [(bounds[i] + bounds[i + 3]) / 2.0 for i in range(3)]
        self.assertEqual(scene.positions[0][1]["translation"], center)
        return row

    def test_reported_sky_grid_failure_is_bounded_and_accepted_by_host(self):
        row = self.plan((0, 0, 0, 5791.818 * 5.0, 100, 200))
        self.assertTrue(row["adaptive_cell_applied"])
        self.assertAlmostEqual(max(row["requested_repeat_count"]), 5791.818)
        self.assertGreater(row["effective_cell_size_world_units"], 5.0)
        report = picker._validate_world_pattern_runner_confirmation(confirmation(row))
        self.assertEqual(report["adaptive_binding_count"], 1)

    def test_all_patterns_handle_huge_translated_nonuniform_roots(self):
        for pattern in ("sky_grid", "floor_grid", "direction_checker", "position_pattern"):
            with self.subTest(pattern=pattern):
                row = self.plan((-1000, 2500, -9000, 2e8, 9000, 5e7), pattern, (2.0, 0.5, -3.0))
                self.assertTrue(row["adaptive_cell_applied"])
                picker._validate_world_pattern_runner_confirmation(confirmation(row))

    def test_small_and_exact_limit_keep_authored_density(self):
        for extent in (50.0, 4096.0 * 5.0):
            with self.subTest(extent=extent):
                row = self.plan((0, 0, 0, extent, 10, 10))
                self.assertFalse(row["adaptive_cell_applied"])
                self.assertEqual(row["effective_cell_size_world_units"], 5.0)
                self.assertEqual(row["cell_scale_factor"], 1.0)
                self.assertEqual(row["requested_repeat_count"], row["baked_repeat_count"])
                picker._validate_world_pattern_runner_confirmation(confirmation(row))

    def test_next_float_above_limit_is_safe(self):
        row = self.plan((0, 0, 0, math.nextafter(4096.0 * 5.0, math.inf), 10, 10))
        self.assertTrue(row["adaptive_cell_applied"])
        self.assertLessEqual(max(row["baked_repeat_count"]), LIMIT)

    def test_invalid_bounds_and_zero_root_scale_still_fail_closed(self):
        for bounds in ((0, 0, 0, float("nan"), 1, 1), (0, 0, 0, 1e13, 1, 1)):
            with self.subTest(bounds=bounds), self.assertRaises(RuntimeError):
                self.plan(bounds)
        with self.assertRaises(RuntimeError):
            self.plan((0, 0, 0, 30000, 1, 1), scale=(0, 1, 1))

    def test_host_rejects_false_density_and_safety_reports(self):
        good = confirmation(self.plan((0, 0, 0, 5791.818 * 5.0, 100, 200)))
        mutations = (
            ("effective_cell_size_world_units", 5.0),
            ("cell_size_world_units", 5.0),
            ("cell_scale_factor", 1.0),
            ("baked_repeat_count", [5791.818, 5791.818]),
            ("baked_repeat_count", [float("nan"), 4096]),
            ("requested_repeat_count", [1.0, 1.0]),
            ("texture_repeat_limit", 9999.0),
            ("adaptive_cell_applied", False),
            ("repeat_safety_policy", "unverified"),
        )
        for key, value in mutations:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                bad = copy.deepcopy(good)
                bad["world_pattern_report"]["patterns"][0][key] = value
                picker._validate_world_pattern_runner_confirmation(bad)
        for key, value in (("adaptive_binding_count", 0), ("texture_repeat_limit", 9999.0)):
            with self.subTest(report=key), self.assertRaises(RuntimeError):
                bad = copy.deepcopy(good)
                bad["world_pattern_report"][key] = value
                picker._validate_world_pattern_runner_confirmation(bad)

    def test_marker_metadata_uses_exact_root_and_pattern_effective_cell(self):
        row = self.plan((0, 0, 0, 5791.818 * 5.0, 100, 200))
        other_root = dict(row, subject_root="|AnotherEnvironment", effective_cell_size_world_units=90.0)
        other_pattern = dict(row, pattern="floor_grid", effective_cell_size_world_units=80.0)
        binding = {"color": "Sky Grid", "asset_id": "test-sky", "subject_root": "|Environment"}
        with mock.patch.dict(runner.MARKER_PATTERNS, {"Sky Grid": "sky_grid"}, clear=True), \
                mock.patch.dict(runner.MARKER_COLORS, {}, clear=True):
            markers = runner._marker_payload([binding], world_pattern_report={
                "patterns": [other_root, other_pattern, row]})
            profile = markers[0]["shading_profile"]
            self.assertEqual(profile["cell_size_world_units"], row["effective_cell_size_world_units"])
            self.assertEqual(profile["effective_cell_size_world_units"], row["effective_cell_size_world_units"])
            self.assertEqual(profile["requested_cell_size_world_units"], 5.0)
            self.assertEqual(profile["repeat_safety_policy"], POLICY)
            self.assertEqual(profile["baked_repeat_count"], row["baked_repeat_count"])
            self.assertTrue(profile["adaptive_cell_applied"])
            for report in (None, {"patterns": [other_root, other_pattern]}, {"patterns": [row, copy.deepcopy(row)]}):
                legacy = runner._marker_payload([binding], world_pattern_report=report)[0]["shading_profile"]
                self.assertEqual(legacy["cell_size_world_units"], 5.0)
                self.assertFalse(legacy.get("adaptive_cell_applied", False))


if __name__ == "__main__":
    unittest.main()
