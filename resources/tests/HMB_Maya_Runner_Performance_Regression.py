# -*- coding: utf-8 -*-
"""Fast, Maya-free regression checks for marker, depth, and frame progress."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
CATALOG_PATH = ROOT / "resources" / "picker" / "HMB_Marker_Catalog.json"

maya_package = types.ModuleType("maya")
maya_cmds_module = types.ModuleType("maya.cmds")
maya_package.cmds = maya_cmds_module
sys.modules.setdefault("maya", maya_package)
sys.modules.setdefault("maya.cmds", maya_cmds_module)

spec = importlib.util.spec_from_file_location("HMB_Maya_Runner_Performance_Regression", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)

runner_source = RUNNER_PATH.read_text(encoding="utf-8")
runner_tree = ast.parse(runner_source, filename=str(RUNNER_PATH))
assert runner.MAYA_WORLD_PATTERN_PROFILE == "hmb_maya_world_root_projection_v1"
assert runner.WORLD_PATTERN_BASE_CELL_WORLD_UNITS == 15.0
assert runner.WORLD_PATTERN_DENSITY_MULTIPLIER == 3.0
assert runner.WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS == 5.0
assert (
    runner.WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS
    * runner.WORLD_PATTERN_DENSITY_MULTIPLIER
    == runner.WORLD_PATTERN_BASE_CELL_WORLD_UNITS
), "The approved grid must remain exactly three times denser than the base grid."
world_group_source = inspect.getsource(runner._world_projected_pattern_group)
projected_surface_source = inspect.getsource(runner._projected_surface_group)
assert '"projection"' in world_group_source
assert '"place3dTexture"' in world_group_source
assert '".placementMatrix"' in world_group_source
assert "parentConstraint(" in world_group_source
assert "scaleConstraint(" in world_group_source
assert '"multiplyDivide"' in world_group_source
assert '"camera_anchored": False' in world_group_source
assert '"uv_dependent": False' in world_group_source
assert '"root_scale_followed": True' in world_group_source
assert '"world_cell_scale_compensated": True' in world_group_source
assert "cmds.file" not in world_group_source
# The report key is the only legitimate use of the word camera in this helper.
assert "camera" not in world_group_source.replace('"camera_anchored"', "")
assert "_connect_authored_transparency(" in projected_surface_source
run_source = inspect.getsource(runner.run)
reference_frame_statement = (
    'job["_world_pattern_reference_frame"] = float(frames[0])'
)
assert reference_frame_statement in run_source
assert run_source.index(reference_frame_statement) < run_source.index(
    "_apply_marker_shaders(bindings, job)"
)

# All render-time shader and projector nodes are temporary in the opened Maya
# process. The source scene may be opened and queried, but never renamed/saved.
for candidate in ast.walk(runner_tree):
    if not isinstance(candidate, ast.Call):
        continue
    if not (
        isinstance(candidate.func, ast.Attribute)
        and isinstance(candidate.func.value, ast.Name)
        and candidate.func.value.id == "cmds"
        and candidate.func.attr == "file"
    ):
        continue
    keyword_names = {keyword.arg for keyword in candidate.keywords}
    assert not ({"save", "saveAs", "rename"} & keyword_names), (
        "The Maya preview runner must never save or rename the user's source scene."
    )
assert runner.SCREEN_SPACE_PATTERN_PROFILE == "hmb_screen_space_pattern_post_v2"
assert runner.SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR == 3
assert runner.SCREEN_SPACE_PATTERN_CELL_DIVISOR == 24
assert runner.POSITION_PATTERN_REPEATS == 3
assert runner.DEPTH_PLAYBLAST_PROFILE == "hmb_camera_space_depth_v7"
assert runner.DEPTH_NEAR_COLOR == 0.9
assert runner.DEPTH_FAR_COLOR == 0.0
assert runner.DEPTH_CAMERA_NEAR_SAFETY_MARGIN == 0.1
assert runner.DEPTH_CONTRAST_EXPONENT == 1.0
assert runner.DEPTH_FOREGROUND_NEAR_PERCENTILE == 0.01
assert runner.DEPTH_FOREGROUND_FAR_PERCENTILE == 0.99
assert runner.DEPTH_GENERIC_FAR_PERCENTILE == 0.95
assert runner.DEPTH_GENERIC_PERCENTILE_MIN_SHAPES == 20
assert runner.DEPTH_SCREEN_VERTEX_SAMPLE_LIMIT == 128
assert runner.DEPTH_SCREEN_POLYGON_CENTER_SAMPLE_LIMIT == 64
assert runner.MOTION_GUIDE_PROFILE == "hmb_target_neutral_motion_guide_v5"
assert runner.MOTION_GUIDE_SCHEMA == "hmb-maya-motion-guide"
assert runner.MOTION_GUIDE_SCHEMA_VERSION == 2
assert runner.MOTION_GUIDE_MAX_FACE_CHANNELS_PER_TARGET == 256
assert runner.MOTION_GUIDE_MAX_FACE_DRIVERS_PER_TARGET == 256
assert runner.MOTION_GUIDE_FACE_BROW_RGB == (176, 96, 255)
assert runner.MOTION_GUIDE_FACE_EYE_RGB == (48, 196, 255)
assert runner.MOTION_GUIDE_FACE_MOUTH_RGB == (255, 72, 180)
assert runner.MOTION_GUIDE_FACE_JAW_RGB == (255, 176, 64)
assert runner.MOTION_GUIDE_FACE_FIRST_HIT_TOLERANCE_FRACTION == 0.005
assert runner._motion_face_semantic("brow_l_up")["group"] == "brow"
assert runner._motion_face_semantic("brow_l_up")["side"] == "left"
assert runner._motion_face_semantic("eye_r_close_dn")["group"] == "eyelid"
assert runner._motion_face_semantic("eye_r_close_dn")["side"] == "right"
assert runner._motion_face_semantic("m_a")["action"] == "phoneme_a"
assert runner._motion_face_semantic("jawOpen")["group"] == "jaw"
assert runner._motion_face_semantic("tongue_out")["raster_eligible"] is False
assert runner._motion_face_occlusion_meshes([
    {"face_landmark_runtime": []},
]) == []
delta_reader_source = runner_source[
    runner_source.index("def _motion_face_blendshape_delta_scores("):
    runner_source.index("def _motion_face_object_points(")
]
assert "setAttr" not in delta_reader_source, (
    "Blend Shape localization must remain read-only and must not mutate Maya."
)
assert "verified_surface_symmetry_mirror" not in runner_source
assert runner_source.index("output_paths, frame_map = _render_frames(") < runner_source.index(
    ") = _render_depth_pass("
), "The color pass must be complete before the temporary depth shader is applied."
assert '"depth_sidecar_path"' in runner_source
assert '"depth_range_report"' in runner_source
assert '"hardwareRenderingGlobals.renderDepthOfField"' in runner_source
assert '"hardwareRenderingGlobals.hwFogEnable"' in runner_source
assert 'getattr(dag_path, "isTemplated", None)' in runner_source
assert "def _potentially_visible_unsupported_depth_drawables(" in runner_source
assert runner._read_job_bindings({"bindings": []}) == []
assert runner._read_job_bindings({
    "bindings": [{
        "group_name": "ExcludedIdea",
        "color": "Red",
        "enabled": False,
    }],
}) == []
assert runner._character_outline_mode({}) == runner.CHARACTER_OUTLINE_NATIVE
assert runner._character_outline_mode(
    {"character_outline_mode": "native_lambert"}
) == runner.CHARACTER_OUTLINE_NATIVE
assert runner._character_outline_mode(
    {"character_outline_mode": "pfx_toon"}
) == runner.CHARACTER_OUTLINE_PFX
try:
    runner._character_outline_mode({"character_outline_mode": "unexpected"})
except RuntimeError:
    pass
else:
    raise AssertionError("Unknown character outline modes must fail closed.")
assert "color in CHARACTER_MARKERS and outline_mode == CHARACTER_OUTLINE_PFX" in runner_source
assert "character_outline_mode=CHARACTER_OUTLINE_NATIVE" in runner_source

runner._load_marker_catalog({
    "marker_catalog_path": str(CATALOG_PATH),
    "marker_catalog_version": 4,
})
assert runner.MARKER_PATTERNS == {
    "Direction Checker": "direction_checker",
    "Sky Grid": "sky_grid",
    "Floor Grid": "floor_grid",
    "Position Pattern": "position_pattern",
}
payload_binding = [{
    "color": "Red",
    "asset_id": "Hero",
    "subject_root": "|Hero",
    "group_name": "Hero",
    "full_dag_path": "|Hero",
    "maya_uuid": "hero-uuid",
}]
native_payload = runner._marker_payload(payload_binding)[0]
assert native_payload["visual_profile"] == "color_stable_lambert_profile"
assert native_payload["out_rim"] == ""
assert native_payload["shading_profile"]["out_rim"] == "none"
pfx_payload = runner._marker_payload(
    payload_binding,
    character_outline_mode="pfx_toon",
)[0]
assert pfx_payload["visual_profile"] == "lambert_with_pfxToon_profile"
assert pfx_payload["out_rim"] == "pfxToon_profile"
assert pfx_payload["shading_profile"]["out_rim_opacity"] == 0.08

shader_calls = {
    "surface": [],
    "lambert": [],
    "pattern": [],
    "screen_pattern": [],
    "assign": [],
}
shader_originals = {
    "_surface_shader": runner._surface_shader,
    "_lambert_shader": runner._lambert_shader,
    "_pattern_shader": runner._pattern_shader,
    "_screen_space_pattern_shader": runner._screen_space_pattern_shader,
    "_assign": runner._assign,
    "_all_renderable_shapes": runner._all_renderable_shapes,
    "_marker_renderable_shapes": runner._marker_renderable_shapes,
    "_descendant_shapes": runner._descendant_shapes,
    "_ensure_authored_cutout_snapshot": (
        runner._ensure_authored_cutout_snapshot
    ),
    "_long_names": runner._long_names,
}
try:
    runner._surface_shader = lambda name, rgb: shader_calls["surface"].append((name, rgb)) or ("surface:" + name)
    runner._lambert_shader = lambda name, rgb: shader_calls["lambert"].append((name, rgb)) or ("lambert:" + name)
    runner._pattern_shader = lambda name, pattern, folder: shader_calls["pattern"].append((name, pattern)) or ("pattern:" + name)
    runner._screen_space_pattern_shader = (
        lambda name, id_rgb: shader_calls["screen_pattern"].append(
            (name, id_rgb)
        )
        or ("screen-pattern:" + name)
    )
    runner._assign = lambda shapes, group: shader_calls["assign"].append((tuple(shapes), group)) or []
    runner._all_renderable_shapes = lambda: []
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    runner._descendant_shapes = lambda root: [root + "Shape"]
    runner._ensure_authored_cutout_snapshot = lambda job, shapes: {
        shape: {"shape": shape, "alpha_driven": False}
        for shape in shapes
    }
    runner._long_names = lambda nodes: list(nodes)
    dispatch_bindings = []
    for index, color in enumerate(("Sky Blue", "Sky Blue", "Mint", "Beige"), start=1):
        dispatch_bindings.append({
            "color": color,
            "subject_root": "|Solid{0}".format(index),
            "asset_id": "Solid{0}".format(index),
        })
    for index, color in enumerate(("Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"), start=1):
        dispatch_bindings.append({
            "color": color,
            "subject_root": "|Pattern{0}".format(index),
            "asset_id": "Pattern{0}".format(index),
        })
    assert runner._apply_marker_shaders(
        dispatch_bindings,
        {
            "result_path": "C:/tmp/hmb-marker-result.json",
            "character_outline_mode": "native_lambert",
            "screen_space_patterns": True,
            "require_full_smooth_geometry": True,
        },
    ) == []
finally:
    for name, value in shader_originals.items():
        setattr(runner, name, value)

assert shader_calls["surface"] == [], (
    "Unassigned Maya geometry must never receive a fallback shader or enter "
    "the Color Picker render."
)
assert [item[0] for item in shader_calls["lambert"]] == [
    "HMB_Sky_Blue", "HMB_Sky_Blue", "HMB_Mint", "HMB_Beige",
]
assert [item[1] for item in shader_calls["lambert"]] == [
    runner.MARKER_COLORS["Sky Blue"],
    runner.MARKER_COLORS["Sky Blue"],
    runner.MARKER_COLORS["Mint"],
    runner.MARKER_COLORS["Beige"],
]
assert shader_calls["pattern"] == []
# This block intentionally exercises the legacy compositor. Its categorical
# shader may only be selected by the explicit screen_space_patterns flag.
assert [item[0] for item in shader_calls["screen_pattern"]] == [
    "HMB_Direction_Checker", "HMB_Sky_Grid", "HMB_Floor_Grid", "HMB_Position_Pattern",
]
assert [item[1] for item in shader_calls["screen_pattern"]] == [
    runner.MARKER_PATTERN_IDS["Direction Checker"],
    runner.MARKER_PATTERN_IDS["Sky Grid"],
    runner.MARKER_PATTERN_IDS["Floor Grid"],
    runner.MARKER_PATTERN_IDS["Position Pattern"],
]
assert sum(1 for _shapes, group in shader_calls["assign"] if group == "lambert:HMB_Sky_Blue") == 2
try:
    runner._apply_marker_shaders([], {
        "screen_space_patterns": True,
        "world_space_patterns": True,
    })
except RuntimeError as exc:
    assert "cannot be enabled together" in str(exc)
else:
    raise AssertionError(
        "Legacy screen fallback and world projection must be mutually exclusive."
    )


class WorldPatternCmds:
    """Minimal deterministic Maya cmds model for the projected pattern graph."""

    ENUMS = (
        "Off:Planar:Spherical:Cylindrical:Ball:Cubic:TriPlanar:"
        "Concentric:Perspective"
    )

    def __init__(self):
        self.nodes = []
        self.attributes = []
        self.connections = []
        self.constraints = []
        self.scale_constraints = []
        self.parents = []
        self.transforms = []
        self.set_nodes = []

    def objExists(self, _node):
        return True

    def nodeType(self, node):
        leaf = str(node).rsplit("|", 1)[-1]
        if leaf in {"Ground", "Set", "Dome", "Backdrop"}:
            return "transform"
        if leaf.endswith("_Checker"):
            return "checker"
        if leaf.endswith("_Grid"):
            return "grid"
        if leaf.endswith("_File"):
            return "file"
        if leaf.endswith("_Projection"):
            return "projection"
        if leaf.endswith("_Projector"):
            return "place3dTexture"
        if leaf.endswith("_Place2d"):
            return "place2dTexture"
        return "transform"

    def exactWorldBoundingBox(self, _shapes, **_kwargs):
        # Non-square dimensions expose accidental repeat/axis swaps.
        return [0.0, 0.0, 0.0, 30.0, 10.0, 45.0]

    def shadingNode(self, node_type, **kwargs):
        name = str(kwargs.get("name") or node_type)
        self.nodes.append((node_type, name, tuple(sorted(kwargs.items()))))
        return name

    def createNode(self, node_type, **kwargs):
        name = str(kwargs.get("name") or node_type)
        self.nodes.append((node_type, name, tuple(sorted(kwargs.items()))))
        return name

    def sets(self, *_args, **kwargs):
        name = str(kwargs.get("name") or "WorldPatternSG")
        self.set_nodes.append((name, tuple(sorted(kwargs.items()))))
        return name

    def attributeQuery(self, _attribute, **_kwargs):
        return [self.ENUMS]

    def setAttr(self, plug, *values, **kwargs):
        self.attributes.append((plug, values, tuple(sorted(kwargs.items()))))

    def getAttr(self, plug, **_kwargs):
        if plug.endswith("_RootAnchor.scale"):
            # Non-uniform scale makes axis mistakes observable while the
            # multiplyDivide graph preserves a five-world-unit cell.
            return [(2.0, 3.0, 4.0)]
        return 0.0

    def connectAttr(self, source, target, **kwargs):
        self.connections.append((source, target, tuple(sorted(kwargs.items()))))

    def parentConstraint(self, source, target, **kwargs):
        name = target + "_parentConstraint"
        self.constraints.append((source, target, tuple(sorted(kwargs.items()))))
        return [name]

    def scaleConstraint(self, source, target, **kwargs):
        name = target + "_scaleConstraint"
        self.scale_constraints.append(
            (source, target, tuple(sorted(kwargs.items())))
        )
        return [name]

    def parent(self, child, parent, **kwargs):
        self.parents.append((child, parent, tuple(sorted(kwargs.items()))))
        return [child]

    def xform(self, node, **kwargs):
        self.transforms.append((node, tuple(sorted(kwargs.items()))))


def build_world_pattern(pattern, root, name, texture_folder):
    fake = WorldPatternCmds()
    original_cmds = runner.cmds
    runner.cmds = fake
    try:
        group, report, projection = runner._world_projected_pattern_group(
            name,
            pattern,
            root,
            [root + "|shape"],
            str(texture_folder),
            runner.WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS,
        )
    finally:
        runner.cmds = original_cmds
    return fake, group, report, projection


with tempfile.TemporaryDirectory(prefix="hmb_world_pattern_graph_") as temp_dir:
    graph_root = Path(temp_dir)
    projection_contract = {
        "direction_checker": ("TriPlanar", "XYZ"),
        "sky_grid": ("TriPlanar", "XYZ"),
        "floor_grid": ("Planar", "XZ"),
        "position_pattern": ("TriPlanar", "XYZ"),
    }
    graph_snapshots = {}
    for index, (pattern, expected_projection) in enumerate(
        projection_contract.items(),
        start=1,
    ):
        name = "HMB_World_{0}".format(pattern)
        root = "|" + ("Ground" if pattern == "floor_grid" else "Set")
        fake, group, report, projection = build_world_pattern(
            pattern,
            root,
            name,
            graph_root,
        )
        assert group == name + "_SurfaceShaderSG"
        assert projection == name + "_Projection"
        assert (report["projection_type"], report["projection_axis"]) == (
            expected_projection
        )
        assert report["cell_size_world_units"] == 5.0
        assert report["camera_anchored"] is False
        assert report["uv_dependent"] is False
        assert report["subject_root"] == root
        assert report["projection_node"] == name + "_Projection"
        assert report["projector_node"] == name + "_Projector"
        assert report["anchor_node"] == name + "_RootAnchor"
        if pattern == "floor_grid":
            # XZ dimensions are 30 x 45. The 5-unit cell yields 6 x 9
            # repeats; the former 15-unit grid yielded only 2 x 3.
            assert report["baked_repeat_count"] == [6.0, 9.0]
            assert report["projector_extent_world_units"] == [30.0, 45.0, 20.0]
        else:
            assert report["baked_repeat_count"] == [9.0, 9.0]
            assert report["projector_extent_world_units"] == [45.0, 45.0, 45.0]

        node_types = [record[0] for record in fake.nodes]
        assert node_types.count("projection") == 1
        assert node_types.count("place3dTexture") == 1
        assert node_types.count("place2dTexture") == 1
        assert node_types.count("surfaceShader") == 1
        assert node_types.count("transform") == 1
        assert node_types.count("multiplyDivide") == 1
        assert len(fake.set_nodes) == 1
        assert len(fake.constraints) == 1
        assert len(fake.scale_constraints) == 1
        assert fake.constraints[0][0] == root
        assert fake.constraints[0][1] == name + "_RootAnchor"
        assert fake.scale_constraints[0][0] == root
        assert fake.scale_constraints[0][1] == name + "_RootAnchor"
        assert report["root_scale_followed"] is True
        assert report["world_cell_scale_compensated"] is True
        assert report["scale_constraint_node"] == (
            name + "_RootAnchor_scaleConstraint"
        )
        assert report["scale_compensator_node"] == (
            name + "_WorldScaleCompensator"
        )
        assert (
            name + "_Projector.worldInverseMatrix[0]",
            name + "_Projection.placementMatrix",
        ) in [(source, target) for source, target, _kwargs in fake.connections]
        placement_sources = [
            source
            for source, target, _kwargs in fake.connections
            if target.endswith(".placementMatrix")
        ]
        assert placement_sources == [
            name + "_Projector.worldInverseMatrix[0]"
        ]
        assert not any(
            "camera" in (source + " " + target).lower()
            for source, target, _kwargs in fake.constraints
        )

        graph_snapshot = (
            tuple(fake.nodes),
            tuple(fake.attributes),
            tuple(fake.connections),
            tuple(fake.constraints),
            tuple(fake.scale_constraints),
            tuple(fake.parents),
            tuple(fake.transforms),
            tuple(fake.set_nodes),
        )
        graph_snapshots[pattern] = graph_snapshot
        repeated_fake, _group, repeated_report, _projection = build_world_pattern(
            pattern,
            root,
            name,
            graph_root,
        )
        repeated_snapshot = (
            tuple(repeated_fake.nodes),
            tuple(repeated_fake.attributes),
            tuple(repeated_fake.connections),
            tuple(repeated_fake.constraints),
            tuple(repeated_fake.scale_constraints),
            tuple(repeated_fake.parents),
            tuple(repeated_fake.transforms),
            tuple(repeated_fake.set_nodes),
        )
        assert repeated_snapshot == graph_snapshot
        assert repeated_report == report

    assert len(graph_snapshots) == 4


# A projected cutout variant must reuse the same projection output while
# reconnecting the scene-authored alpha source. A flat-color variant would
# preserve the silhouette but silently destroy the selected pattern.
cutout_calls = {"surface": [], "assign": []}
cutout_originals = {
    "_ensure_authored_cutout_snapshot": runner._ensure_authored_cutout_snapshot,
    "_projected_surface_group": runner._projected_surface_group,
    "_assign": runner._assign,
    "_long_names": runner._long_names,
}
try:
    runner._ensure_authored_cutout_snapshot = lambda _job, _shapes: {
        "|Set|OpaqueShape": {
            "shape": "|Set|OpaqueShape",
            "alpha_driven": False,
        },
        "|Set|LeafCardShape": {
            "shape": "|Set|LeafCardShape",
            "alpha_driven": True,
            "source_plug": "leafFile.outTransparency",
        },
    }
    runner._projected_surface_group = (
        lambda name, projection, transparency_source="": (
            cutout_calls["surface"].append(
                (name, projection, transparency_source)
            )
            or (name + "SG")
        )
    )
    runner._assign = lambda shapes, group: (
        cutout_calls["assign"].append((tuple(shapes), group)) or []
    )
    runner._long_names = lambda nodes: list(nodes)
    cutout_job = {}
    cutout_cache = {}
    cutout_warnings, opaque_shapes, verified_cutouts = (
        runner._assign_world_pattern_preserving_cutouts(
            ["|Set|OpaqueShape", "|Set|LeafCardShape"],
            "HMB_World_SharedSG",
            "HMB_World_Pattern",
            "HMB_World_Pattern_Projection",
            cutout_job,
            cutout_cache,
        )
    )
finally:
    for name, value in cutout_originals.items():
        setattr(runner, name, value)

assert cutout_warnings == []
assert opaque_shapes == ["|Set|OpaqueShape"]
assert verified_cutouts == ["|Set|LeafCardShape"]
cutout_token = runner._cutout_variant_token("leafFile.outTransparency")
assert cutout_calls["surface"] == [(
    "HMB_World_Pattern_Cutout_" + cutout_token,
    "HMB_World_Pattern_Projection",
    "leafFile.outTransparency",
)]
assert cutout_calls["assign"] == [
    (("|Set|OpaqueShape",), "HMB_World_SharedSG"),
    (
        ("|Set|LeafCardShape",),
        "HMB_World_Pattern_Cutout_" + cutout_token + "SG",
    ),
]


# High-level dispatch must select Maya world projection by default when the
# explicit production flag is present and publish one deterministic report
# row per bound pattern. The legacy screen compositor remains opt-in only.
world_dispatch_calls = {
    "world": [],
    "assign_world": [],
    "screen": [],
    "assign": [],
}
world_dispatch_originals = {
    "_world_projected_pattern_group": runner._world_projected_pattern_group,
    "_assign_world_pattern_preserving_cutouts": (
        runner._assign_world_pattern_preserving_cutouts
    ),
    "_screen_space_pattern_shader": runner._screen_space_pattern_shader,
    "_assign": runner._assign,
    "_all_renderable_shapes": runner._all_renderable_shapes,
    "_marker_renderable_shapes": runner._marker_renderable_shapes,
    "_descendant_shapes": runner._descendant_shapes,
    "_ensure_authored_cutout_snapshot": (
        runner._ensure_authored_cutout_snapshot
    ),
    "_long_names": runner._long_names,
}


def fake_world_group(name, pattern, root, shapes, _folder, cell_units):
    projection_type, projection_axis = runner._world_pattern_projection_type(
        pattern
    )
    world_dispatch_calls["world"].append(
        (name, pattern, root, tuple(shapes), cell_units)
    )
    projection = name + "_Projection"
    return name + "SG", {
        "pattern": pattern,
        "subject_root": root,
        "projection_type": projection_type,
        "projection_axis": projection_axis,
        "cell_size_world_units": cell_units,
        "projection_node": projection,
        "projector_node": name + "_Projector",
        "anchor_node": name + "_RootAnchor",
        "constraint_node": name + "_RootAnchor_parentConstraint",
        "scale_constraint_node": name + "_RootAnchor_scaleConstraint",
        "scale_compensator_node": name + "_WorldScaleCompensator",
        "root_scale_followed": True,
        "world_cell_scale_compensated": True,
        "camera_anchored": False,
        "uv_dependent": False,
    }, projection


try:
    runner._world_projected_pattern_group = fake_world_group
    runner._assign_world_pattern_preserving_cutouts = (
        lambda shapes, group, name, projection, _job, _cache: (
            world_dispatch_calls["assign_world"].append(
                (tuple(shapes), group, name, projection)
            )
            or ([], list(shapes), [])
        )
    )
    runner._screen_space_pattern_shader = (
        lambda name, rgb: world_dispatch_calls["screen"].append((name, rgb))
        or (name + "ScreenSG")
    )
    runner._assign = lambda shapes, group: (
        world_dispatch_calls["assign"].append((tuple(shapes), group)) or []
    )
    runner._all_renderable_shapes = lambda: []
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    runner._descendant_shapes = lambda root: [root + "|shape"]
    runner._ensure_authored_cutout_snapshot = lambda _job, shapes: {
        shape: {"shape": shape, "alpha_driven": False}
        for shape in shapes
    }
    runner._long_names = lambda nodes: list(nodes)
    world_job = {
        "result_path": "C:/tmp/hmb-world-result.json",
        "world_space_patterns": True,
        "world_pattern_profile": runner.MAYA_WORLD_PATTERN_PROFILE,
        "world_pattern_cell_units": 5.0,
        "world_pattern_density_multiplier": 3.0,
        "_world_pattern_reference_frame": 101.0,
        "require_full_smooth_geometry": True,
    }
    world_bindings = [
        {
            "color": color,
            "subject_root": "|Pattern{0}".format(index),
            "asset_id": "Pattern{0}".format(index),
        }
        for index, color in enumerate(
            (
                "Direction Checker",
                "Sky Grid",
                "Floor Grid",
                "Position Pattern",
            ),
            start=1,
        )
    ]
    assert runner._apply_marker_shaders(world_bindings, world_job) == []
finally:
    for name, value in world_dispatch_originals.items():
        setattr(runner, name, value)

assert len(world_dispatch_calls["world"]) == 4
assert len(world_dispatch_calls["assign_world"]) == 4
assert world_dispatch_calls["screen"] == []
assert all(call[-1] == 5.0 for call in world_dispatch_calls["world"])
world_report = world_job["_world_pattern_report"]
assert world_report["profile"] == runner.MAYA_WORLD_PATTERN_PROFILE
assert world_report["coordinate_space"] == "background_root"
assert world_report["camera_anchored"] is False
assert world_report["uv_dependent"] is False
assert world_report["root_scale_followed"] is True
assert world_report["world_cell_scale_compensated"] is True
assert world_report["base_cell_world_units"] == 15.0
assert world_report["density_multiplier"] == 3.0
assert world_report["cell_size_world_units"] == 5.0
assert world_report["reference_frame"] == 101.0
assert world_report["pattern_binding_count"] == 4
assert world_report["projection_node_count"] == 4
assert world_report["projector_node_count"] == 4
assert [
    (
        row["pattern"],
        row["projection_type"],
        row["projection_axis"],
        row["reference_frame"],
        row["root_scale_followed"],
        row["world_cell_scale_compensated"],
    )
    for row in world_report["patterns"]
] == [
    ("direction_checker", "TriPlanar", "XYZ", 101.0, True, True),
    ("sky_grid", "TriPlanar", "XYZ", 101.0, True, True),
    ("floor_grid", "Planar", "XZ", 101.0, True, True),
    ("position_pattern", "TriPlanar", "XYZ", 101.0, True, True),
]


class AssignedScopeCmds:
    def __init__(self):
        self.members = []
        self.layer_visible = True
        self.set_calls = []

    def createDisplayLayer(self, **_kwargs):
        return "HMB_Picker_Excluded"

    def editDisplayLayerMembers(self, _layer, members=None, **kwargs):
        if kwargs.get("query"):
            return list(self.members)
        self.members = list(members or [])
        return list(self.members)

    def setAttr(self, plug, value, **_kwargs):
        self.set_calls.append((plug, value))
        if plug == "HMB_Picker_Excluded.visibility":
            self.layer_visible = bool(value)

    def getAttr(self, plug, **_kwargs):
        if plug == "HMB_Picker_Excluded.visibility":
            return self.layer_visible
        return True

    def ls(self, node=None, **_kwargs):
        return [node] if node else []

    def nodeType(self, _node):
        return "mesh"


scope_cmds = AssignedScopeCmds()
scope_originals = {
    "cmds": runner.cmds,
    "_validated_picker_hidden_paths": runner._validated_picker_hidden_paths,
    "_descendant_shapes": runner._descendant_shapes,
    "_marker_renderable_shapes": runner._marker_renderable_shapes,
    "_all_scope_drawable_shapes": runner._all_scope_drawable_shapes,
}
try:
    runner.cmds = scope_cmds
    runner._validated_picker_hidden_paths = lambda _job: ["|Prop"]
    runner._descendant_shapes = lambda root: {
        "|Hero": ["|Hero|HeroShape", "|Hero|AuthoredHiddenShape"],
        "|Prop": ["|Prop|PropShape"],
    }.get(root, [])
    runner._marker_renderable_shapes = lambda shapes: [
        shape for shape in shapes if not shape.endswith("AuthoredHiddenShape")
    ]
    runner._all_scope_drawable_shapes = lambda: [
        "|Hero|HeroShape",
        "|Hero|AuthoredHiddenShape",
        "|Prop|PropShape",
        "|Set|UnassignedShape",
        "|Rig|ControllerShape",
    ]
    scope_job = {"hidden_paths": ["|Prop"]}
    hidden, scope_report = runner._apply_assigned_render_scope(
        [
            {"subject_root": "|Hero", "color": "Red"},
            {"subject_root": "|Prop", "color": "Sky Grid"},
        ],
        scope_job,
    )
finally:
    for name, value in scope_originals.items():
        setattr(runner, name, value)

assert hidden == ["|Prop"]
assert scope_job["_render_scope_shapes"] == ["|Hero|HeroShape"]
assert scope_job["_render_scope_binding_shapes"]["|Hero"] == [
    "|Hero|HeroShape"
]
assert scope_job["_render_scope_binding_shapes"]["|Prop"] == []
assert scope_job["_depth_foreground_shapes"] == ["|Hero|HeroShape"]
assert scope_job["_depth_range_shape_roles"] == {
    "|Hero|HeroShape": {
        "root": "|Hero",
        "marker": "Red",
        "role": "foreground",
    },
}
assert set(scope_cmds.members) == {
    "|Hero|AuthoredHiddenShape",
    "|Prop|PropShape",
    "|Set|UnassignedShape",
    "|Rig|ControllerShape",
}
assert scope_cmds.set_calls == [("HMB_Picker_Excluded.visibility", False)]
assert scope_report["allowed_shape_path_count"] == 1
assert scope_report["excluded_shape_path_count"] == 4
assert scope_report["proxy_preview_recovery_enabled"] is False


class DepthShaderCmds:
    def __init__(self):
        self.nodes = []
        self.attributes = {}
        self.connections = []
        self.assignments = []
        self.node_index = 0

    def listRelatives(self, camera, **_kwargs):
        return [camera + "|cameraShape"]

    def ls(self, node=None, **_kwargs):
        return [node] if node else []

    def listSets(self, **_kwargs):
        return []

    def listConnections(self, *_args, **_kwargs):
        return []

    def nodeType(self, node):
        if node.endswith("cameraShape"):
            return "camera"
        if node.endswith("HeroShape"):
            return "mesh"
        if node.endswith("SetSurface"):
            return "nurbsSurface"
        return "transform"

    def getAttr(self, plug):
        if plug.endswith(".nearClipPlane"):
            return 0.25
        if plug.endswith(".farClipPlane"):
            return 2000.0
        return self.attributes.get(plug, 0)

    def objExists(self, _node):
        return False

    def isConnected(self, _source, _target):
        return False

    def shadingNode(self, node_type, **kwargs):
        self.node_index += 1
        name = str(kwargs.get("name") or node_type).replace("#", "")
        node = "{0}{1}".format(name, self.node_index)
        self.nodes.append((node_type, node, dict(kwargs)))
        return node

    def setAttr(self, plug, *values, **_kwargs):
        self.attributes[plug] = values[0] if len(values) == 1 else tuple(values)

    def connectAttr(self, source, target, **_kwargs):
        self.connections.append((source, target))

    def sets(self, *args, **kwargs):
        if kwargs.get("renderable") and kwargs.get("empty"):
            self.node_index += 1
            return str(kwargs.get("name") or "DepthSG").replace("#", "") + str(
                self.node_index
            )
        assert args and kwargs.get("edit") and kwargs.get("forceElement")
        self.assignments.append((args[0], kwargs["forceElement"]))
        return args[0]


depth_cmds = DepthShaderCmds()
depth_originals = {
    "cmds": runner.cmds,
    "_all_depth_renderable_shapes": runner._all_depth_renderable_shapes,
    "_marker_renderable_shapes": runner._marker_renderable_shapes,
    "_assert_depth_drawables_supported": runner._assert_depth_drawables_supported,
    "_depth_camera_world_inverse_matrix": runner._depth_camera_world_inverse_matrix,
    "_depth_shape_representative_camera_depth": runner._depth_shape_representative_camera_depth,
    "_verify_depth_shader_assignment": runner._verify_depth_shader_assignment,
}
try:
    runner.cmds = depth_cmds
    runner._assert_depth_drawables_supported = lambda _camera=None: None
    runner._all_depth_renderable_shapes = lambda *_args, **_kwargs: [
        "|Hero|HeroShape",
        "|Set|SetSurface",
    ]
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    runner._depth_camera_world_inverse_matrix = lambda _camera: (object(), object())
    runner._depth_shape_representative_camera_depth = (
        lambda shape, _matrix, _om, frame=None: (
            1.0 if shape.endswith("HeroShape") else 100.0
        )
    )
    runner._verify_depth_shader_assignment = lambda assignments: {
        "shape_path_count": len(assignments),
        "mesh_path_count": 1,
        "nurbs_surface_path_count": 1,
        "verified_shape_path_count": len(assignments),
        "verified_mesh_face_count": 12,
    }
    depth_report, assign_depth_frame = runner._apply_depth_shader(
        "|shotCamera",
        {
            "depth_profile": runner.DEPTH_PLAYBLAST_PROFILE,
            "depth_near": 1.0,
            "depth_far": 100.0,
        },
    )
    assign_depth_frame(101.0, 0, 2)
    assign_depth_frame(102.0, 1, 2)
finally:
    runner.cmds = depth_originals["cmds"]
    runner._all_depth_renderable_shapes = depth_originals[
        "_all_depth_renderable_shapes"
    ]
    runner._marker_renderable_shapes = depth_originals[
        "_marker_renderable_shapes"
    ]
    runner._assert_depth_drawables_supported = depth_originals[
        "_assert_depth_drawables_supported"
    ]
    runner._depth_camera_world_inverse_matrix = depth_originals[
        "_depth_camera_world_inverse_matrix"
    ]
    runner._depth_shape_representative_camera_depth = depth_originals[
        "_depth_shape_representative_camera_depth"
    ]
    runner._verify_depth_shader_assignment = depth_originals[
        "_verify_depth_shader_assignment"
    ]

assert depth_report["profile"] == runner.DEPTH_PLAYBLAST_PROFILE
assert depth_report["normalization_policy"] == "fixed_shot_range_clamped_to_camera"
assert depth_report["near"] == 1.0
assert depth_report["far"] == 100.0
assert depth_report["direction"] == "near_white_far_black"
assert depth_report["background"] == "pure_black"
assert depth_report["encoding_curve"] == "normalized_power"
assert depth_report["contrast_exponent"] == 1.0
assert depth_report["near_color"] == 0.9
assert depth_report["far_color"] == 0.0
assert depth_report["output_value_range"] == [0.0, 0.9]
assert depth_report["camera_near_safety_margin"] == 0.1
assert depth_report["reserved_output_value_range"] == [0.9, 1.0]
assert depth_report["temporal_normalization"] == "fixed_for_complete_sequence"
assert depth_report["renderable_shape_count"] == 2
assert depth_report["mesh_shape_count"] == 1
assert depth_report["nurbs_surface_shape_count"] == 1
assert depth_report["source"] == "object_bbox_camera_depth"
assert (
    depth_report["assignment_mode"]
    == "color_picker_style_shared_gray_material_buckets"
)
assert depth_report["depth_update_scope"] == "per_shape_path_per_output_frame"
assert (
    depth_report["representative_depth"]
    == "median_positive_camera_depth_of_world_bbox_corners"
)
assert depth_report["shader_model"] == "surfaceShader"
assert depth_report["grayscale_bucket_count"] == 256
assert depth_report["standard_nodes"] == ["surfaceShader"]
assert depth_report["proxy_preview_recovery"] == {
    "candidate_shape_count": 0,
    "candidate_path_count": 0,
    "recovered_shape_count": 0,
    "recovered_path_count": 0,
    "recovered_paths": [],
    "source_paths": [],
}
assert depth_report["assignment_verification"] == {
    "shape_path_count": 2,
    "mesh_path_count": 1,
    "nurbs_surface_path_count": 1,
    "verified_shape_path_count": 2,
    "verified_mesh_face_count": 24,
    "rendered_frame_count": 2,
    "expected_frame_assignment_count": 4,
    "verified_frame_assignment_count": 4,
}
assert [item[0] for item in depth_cmds.nodes] == ["surfaceShader"] * 256
assert len(depth_cmds.connections) == 256
assert len(depth_cmds.assignments) == 2, (
    "Unchanged depth buckets must not be reassigned on the second frame."
)
depth_palette_values = sorted(
    value
    for plug, value in depth_cmds.attributes.items()
    if plug.endswith(".outColor")
)
assert len(depth_palette_values) == 256
assert depth_palette_values[0] == (0.0, 0.0, 0.0)
assert depth_palette_values[-1] == (0.9, 0.9, 0.9)
assert all(value[0] == value[1] == value[2] for value in depth_palette_values)
assert runner._depth_grayscale_bucket_index(10.0, 10.0, 110.0) == 255
assert runner._depth_grayscale_bucket_index(110.0, 10.0, 110.0) == 0
assert runner._depth_grayscale_bucket_index(50.96, 10.0, 110.0) == 151
assert runner._depth_grayscale_bucket_index(-100.0, 10.0, 110.0) == 255
assert runner._depth_grayscale_bucket_index(1000.0, 10.0, 110.0) == 0
assert "samplerInfo" not in runner_source
assert "pointCameraZ" not in runner_source


class MotionSelectionCmds:
    def __init__(self):
        self.hero_joints = [
            "|HeroRig|Root_JNT",
            "|HeroRig|Root_JNT|Pelvis_JNT",
            "|HeroRig|Root_JNT|Pelvis_JNT|Spine_JNT",
            "|HeroRig|Root_JNT|Pelvis_JNT|Spine_JNT|Head_JNT",
            "|HeroRig|Root_JNT|L|changedRoot_JNT",
            "|HeroRig|Root_JNT|R|changedRoot_JNT",
            "|HeroRig|C_AllLip_Head_JNT",
            "|HeroRig|Arm_FK_JNT",
            "|HeroRig|SpineTwist_JNT",
            "|HeroRig|ShirtSleeveRoot_JNT",
            "|HeroRig|IndexFinger_JNT",
            "|HeroRig|sk_Spine_JNT",
            "|HeroRig|facialAllRig_GRP|BD_HeadTop_JNT",
            "|HeroRig|BD_jawBind_JNT",
            "|HeroRig|L_Arm5_End2",
        ]
        self.parent = {
            joint: "|HeroRig|Root_JNT"
            for joint in self.hero_joints
            if joint != "|HeroRig|Root_JNT"
        }

    def objExists(self, _node):
        return True

    def nodeType(self, node):
        if node in self.hero_joints:
            return "joint"
        if str(node).endswith("Shape"):
            return "mesh"
        return "transform"

    def listHistory(self, shape, **_kwargs):
        if "Hero" in shape:
            return ["HeroSkin"]
        if "Duplicate" in shape:
            return ["DuplicateSkin"]
        return []

    def skinCluster(self, cluster, **kwargs):
        assert kwargs.get("query") is True
        if cluster in {"HeroSkin", "DuplicateSkin"}:
            return list(self.hero_joints)
        return []

    def ls(self, node=None, **kwargs):
        if kwargs.get("type") == "skinCluster":
            values = list(node or []) if isinstance(node, (list, tuple)) else [node]
            return [value for value in values if str(value).endswith("Skin")]
        if kwargs.get("uuid"):
            return ["uuid:" + str(node)]
        if node is None:
            return []
        return list(node) if isinstance(node, (list, tuple)) else [node]

    def listRelatives(self, node, **kwargs):
        if kwargs.get("parent"):
            parent = self.parent.get(node, "")
            return [parent] if parent else []
        if kwargs.get("type") == "joint":
            return list(self.hero_joints) if node == "|HeroRig" else []
        return []


motion_selection_cmds = MotionSelectionCmds()
motion_selection_original_cmds = runner.cmds
try:
    runner.cmds = motion_selection_cmds
    motion_records, motion_audit = runner._motion_target_records(
        [
            {
                "full_dag_path": "|HeroA",
                "asset_id": "HeroA",
                "color": "Red",
                "picker_order": 1,
            },
            {
                "full_dag_path": "|HeroDuplicate",
                "asset_id": "HeroDuplicate",
                "color": "Green",
                "picker_order": 2,
            },
            {
                "full_dag_path": "|Background",
                "asset_id": "Background",
                "color": "Sky Blue",
                "picker_order": 3,
            },
        ],
        job={
            "_render_scope_binding_shapes": {
                "|HeroA": ["|HeroA|HeroShape"],
                "|HeroDuplicate": ["|HeroDuplicate|DuplicateShape"],
                "|Background": ["|Background|BackgroundShape"],
            },
        },
        with_report=True,
    )
finally:
    runner.cmds = motion_selection_original_cmds

assert [record["asset_id"] for record in motion_records] == [
    "HeroA",
    "Background",
]
hero_motion = motion_records[0]
background_motion = motion_records[1]
assert hero_motion["mode"] == "joint_hierarchy"
assert hero_motion["joint_selection"]["source"] == (
    "weighted_skin_cluster_influences"
)
assert background_motion["mode"] == "rigid_transform"
assert background_motion["joint_selection"]["source"] == (
    "background_marker_rigid_transform"
)
selected_labels = {
    runner._dag_leaf_without_namespace(joint)
    for joint in hero_motion["joints"]
}
assert "Root_JNT" in selected_labels
assert "Pelvis_JNT" in selected_labels
assert "Spine_JNT" in selected_labels
assert "Head_JNT" in selected_labels
for excluded_label in (
    "C_AllLip_Head_JNT",
    "Arm_FK_JNT",
    "SpineTwist_JNT",
    "ShirtSleeveRoot_JNT",
    "IndexFinger_JNT",
    "sk_Spine_JNT",
    "BD_HeadTop_JNT",
    "BD_jawBind_JNT",
    "L_Arm5_End2",
):
    assert excluded_label not in selected_labels
changed_root_ids = [
    runner._motion_joint_stable_id(joint)
    for joint in hero_motion["joints"]
    if joint.endswith("changedRoot_JNT")
]
assert len(changed_root_ids) == 2
assert len(set(changed_root_ids)) == 2
assert motion_audit["duplicate_skeleton_count"] == 1
assert motion_audit["excluded_joint_count"] == 9
assert motion_audit["output_target_count"] == 2


class DepthBBoxCmds:
    def __init__(self):
        self.calls = []

    def exactWorldBoundingBox(self, shape, **kwargs):
        self.calls.append((shape, dict(kwargs)))
        if shape == "|FrontInstance|sharedShape":
            return [-1.0, -1.0, -9.0, 1.0, 1.0, -1.0]
        if shape == "|BehindInstance|sharedShape":
            return [-1.0, -1.0, 2.0, 1.0, 1.0, 4.0]
        raise AssertionError(shape)


class DepthBBoxPoint:
    def __init__(self, x, y, z, w):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.w = float(w)

    def __mul__(self, _matrix):
        return self


depth_bbox_cmds = DepthBBoxCmds()
try:
    runner.cmds = depth_bbox_cmds
    depth_bbox_om = types.SimpleNamespace(MPoint=DepthBBoxPoint)
    assert runner._depth_shape_representative_camera_depth(
        "|FrontInstance|sharedShape",
        object(),
        depth_bbox_om,
        frame=101.0,
    ) == 5.0
    assert runner._depth_shape_representative_camera_depth(
        "|BehindInstance|sharedShape",
        object(),
        depth_bbox_om,
        frame=101.0,
    ) == -3.0
finally:
    runner.cmds = depth_originals["cmds"]
assert [item[0] for item in depth_bbox_cmds.calls] == [
    "|FrontInstance|sharedShape",
    "|BehindInstance|sharedShape",
]
assert all(
    item[1].get("ignoreInvisible") is False
    for item in depth_bbox_cmds.calls
)

try:
    runner.cmds = depth_cmds
    runner._assert_depth_drawables_supported = lambda _camera=None: None
    clip_depth_report = runner._depth_range(
        "|shotCamera",
        {"depth_profile": runner.DEPTH_PLAYBLAST_PROFILE},
    )
finally:
    runner.cmds = depth_originals["cmds"]
    runner._assert_depth_drawables_supported = depth_originals[
        "_assert_depth_drawables_supported"
    ]
assert (
    clip_depth_report["normalization_policy"]
    == "camera_clip_planes_fallback"
)
assert clip_depth_report["near"] == 0.25
assert clip_depth_report["far"] == 2000.0


class RawDepthOptionsCmds:
    def __init__(self):
        self.attributes = {}
        self.output_transform_enabled = True
        self.output_transform_targets = []

    def displayRGBColor(self, *_args):
        return None

    def objExists(self, _plug):
        return True

    def setAttr(self, plug, value, **_kwargs):
        self.attributes[plug] = value

    def getAttr(self, plug):
        return self.attributes.get(plug, 1)

    def colorManagementPrefs(self, query=False, edit=False, **kwargs):
        if edit or query:
            self.output_transform_targets.append(kwargs.get("outputTarget"))
        if edit and "outputTransformEnabled" in kwargs:
            self.output_transform_enabled = bool(kwargs["outputTransformEnabled"])
        if query and kwargs.get("outputTransformEnabled"):
            return self.output_transform_enabled
        return None


raw_options_cmds = RawDepthOptionsCmds()
try:
    runner.cmds = raw_options_cmds
    raw_options_report = runner._set_viewport_render_options(depth_mode=True)
finally:
    runner.cmds = depth_originals["cmds"]
for required_key in (
    "output_transform_disabled",
    "multisample_disabled",
    "line_aa_disabled",
    "ssao_disabled",
    "motion_blur_disabled",
    "depth_of_field_disabled",
    "fog_disabled",
):
    assert raw_options_report[required_key] is True
assert raw_options_cmds.attributes[
    "hardwareRenderingGlobals.renderDepthOfField"
] == 0
assert raw_options_cmds.output_transform_targets == ["renderer", "renderer"]

depth_shader_group_source = inspect.getsource(
    runner._create_depth_grayscale_buckets
)
assert "fresh=True" in depth_shader_group_source
assert raw_options_cmds.attributes["hardwareRenderingGlobals.hwFogEnable"] == 0


class AllPathsFailureCmds:
    def ls(self, **kwargs):
        assert kwargs.get("allPaths") is True
        raise RuntimeError("allPaths unavailable")


try:
    runner.cmds = AllPathsFailureCmds()
    runner._all_depth_renderable_shapes()
except RuntimeError as exc:
    assert "enumerate every mesh instance DAG path" in str(exc)
else:
    raise AssertionError("Depth instance enumeration must fail closed.")
finally:
    runner.cmds = depth_originals["cmds"]


class ProxyPreviewRecoveryCmds:
    output = "|Proxy|redshiftProxyPlaceholderShape"
    parent = "|Proxy"
    proxy_node = "redshiftProxy1"

    def __init__(self, source_face_counts=(24,), locked_plugs=()):
        self.sources = [
            "|Proxy|cachedPreviewShape{0}".format(index + 1)
            for index in range(len(source_face_counts))
        ]
        self.face_counts = {self.output: 0}
        self.face_counts.update(dict(zip(self.sources, source_face_counts)))
        self.attributes = {
            self.output + ".intermediateObject": False,
            self.output + ".visibility": True,
        }
        for source in self.sources:
            self.attributes[source + ".intermediateObject"] = True
            self.attributes[source + ".visibility"] = True
        self.locked_plugs = set(locked_plugs)
        self.set_calls = []

    def ls(self, *args, **kwargs):
        if kwargs.get("uuid"):
            path = args[0]
            if path == self.output:
                return ["output-uuid"]
            if path in self.sources:
                return ["source-{0}".format(self.sources.index(path) + 1)]
            return []
        if kwargs.get("dag") and kwargs.get("type") == "mesh":
            assert kwargs.get("allPaths") is True
            return [self.output] + list(self.sources)
        return list(args)

    def listConnections(self, plug, **kwargs):
        if plug == self.output + ".inMesh":
            assert kwargs.get("source") is True
            assert kwargs.get("destination") is False
            return [self.proxy_node + ".outMesh"]
        return []

    def nodeType(self, node):
        if node == self.proxy_node:
            return "unknown"
        if node in [self.output] + self.sources:
            return "mesh"
        return "transform"

    def unknownNode(self, _node, query=False, **kwargs):
        assert query is True
        if kwargs.get("realClassName"):
            return "RedshiftProxyMesh"
        if kwargs.get("plugin"):
            return "redshift4maya"
        return ""

    def listRelatives(self, node, **kwargs):
        if node == self.output and kwargs.get("parent"):
            return [self.parent]
        if node == self.parent and kwargs.get("shapes"):
            return [self.output] + list(self.sources)
        return []

    def attributeQuery(self, attribute, node=None, exists=False, **_kwargs):
        assert attribute == "intermediateObject" and exists
        return node in [self.output] + self.sources

    def polyEvaluate(self, shape, face=False, **_kwargs):
        assert face is True
        return self.face_counts.get(shape, 0)

    def objExists(self, plug):
        return plug in self.attributes

    def getAttr(self, plug, settable=False, **_kwargs):
        if settable:
            return plug not in self.locked_plugs
        return self.attributes[plug]

    def setAttr(self, plug, value, **_kwargs):
        if plug in self.locked_plugs:
            raise RuntimeError("simulated locked attribute")
        self.attributes[plug] = value
        self.set_calls.append((plug, value))

    def refresh(self, **_kwargs):
        return None


proxy_recovery_originals = {
    "cmds": runner.cmds,
    "_marker_renderable_shapes": runner._marker_renderable_shapes,
    "_depth_mesh_polygon_count_api": runner._depth_mesh_polygon_count_api,
}
proxy_cmds = ProxyPreviewRecoveryCmds()
try:
    runner.cmds = proxy_cmds
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    runner._depth_mesh_polygon_count_api = (
        lambda shape: int(proxy_cmds.face_counts.get(shape, 0))
    )
    proxy_restore = {"attributes": []}
    proxy_failures = []
    proxy_report = runner._recover_scene_saved_proxy_previews(
        proxy_restore,
        proxy_failures,
    )
finally:
    for name, value in proxy_recovery_originals.items():
        setattr(runner, name, value)

assert proxy_failures == []
assert proxy_report == {
    "candidate_shape_count": 1,
    "candidate_path_count": 1,
    "recovered_shape_count": 1,
    "recovered_path_count": 1,
    "recovered_paths": [proxy_cmds.output],
    "source_paths": [proxy_cmds.sources[0]],
}
assert proxy_cmds.attributes[proxy_cmds.output + ".visibility"] is False
assert (
    proxy_cmds.attributes[proxy_cmds.sources[0] + ".intermediateObject"]
    is False
)
assert proxy_restore["attributes"] == [
    (proxy_cmds.sources[0] + ".intermediateObject", True),
    (proxy_cmds.output + ".visibility", True),
]
assert not hasattr(proxy_cmds, "connectAttr"), (
    "Proxy recovery must never connect cached outMesh to an invalid output."
)

for case_name, source_faces, locked_plug, api_faces, expected_text in (
    ("missing", (), "", 0, "found 0"),
    ("ambiguous", (12, 24), "", 12, "found 2"),
    (
        "locked",
        (24,),
        "|Proxy|cachedPreviewShape1.intermediateObject",
        24,
        "locked or connected",
    ),
    ("api_zero", (24,), "", 0, "MFnMesh.numPolygons returned 0"),
):
    case_cmds = ProxyPreviewRecoveryCmds(
        source_face_counts=source_faces,
        locked_plugs=[locked_plug] if locked_plug else [],
    )
    try:
        runner.cmds = case_cmds
        runner._marker_renderable_shapes = lambda shapes: list(shapes)
        runner._depth_mesh_polygon_count_api = lambda _shape, value=api_faces: value
        case_restore = {"attributes": []}
        case_failures = []
        case_report = runner._recover_scene_saved_proxy_previews(
            case_restore,
            case_failures,
        )
    finally:
        for name, value in proxy_recovery_originals.items():
            setattr(runner, name, value)
    assert case_failures, case_name + " must fail closed"
    assert expected_text in " | ".join(case_failures), (
        case_name,
        case_failures,
    )
    assert case_report["candidate_shape_count"] == 1
    assert case_report["recovered_shape_count"] in (0, 1)


class UnsupportedDrawableCmds:
    def ls(self, **kwargs):
        assert kwargs.get("allPaths") is True
        return ["|SmokeCacheShape"]

    def nodeType(self, _path):
        return "gpuCache"


try:
    runner.cmds = UnsupportedDrawableCmds()
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    unsupported_drawables = (
        runner._potentially_visible_unsupported_depth_drawables()
    )
finally:
    runner.cmds = depth_originals["cmds"]
    runner._marker_renderable_shapes = depth_originals[
        "_marker_renderable_shapes"
    ]
assert unsupported_drawables == [
    {"path": "|SmokeCacheShape", "type": "gpuCache"}
]


class TemplatedDagPath:
    def isVisible(self):
        return True

    def isTemplated(self):
        return True


assert runner._depth_api_camera_points(
    {
        "shape": "|Templated|Shape",
        "dag_path": TemplatedDagPath(),
        "function": object(),
    },
    None,
    object(),
    101.0,
) is None


class SampleMMatrix:
    def __init__(self, values):
        self.values = values


class SampleMPoint:
    def __init__(self, x, y, z, w):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.w = float(w)

    def __mul__(self, _matrix):
        return self


open_maya_module = types.ModuleType("maya.api.OpenMaya")
open_maya_module.MMatrix = SampleMMatrix
open_maya_module.MPoint = SampleMPoint
maya_api_module = types.ModuleType("maya.api")
maya_api_module.OpenMaya = open_maya_module
maya_package.api = maya_api_module
sys.modules["maya.api"] = maya_api_module
sys.modules["maya.api.OpenMaya"] = open_maya_module


class SampleDepthCmds:
    def __init__(self):
        self.frame = 77.0
        self.bbox_calls = []
        self.bounds = {
            # Crosses the camera near plane: raw depth [-5, 50]. The fixed
            # interval intersection must preserve clip_near=1, not collapse to
            # the four depth-50 corners that passed the old corner filter.
            "|NearCross|shape": [-0.5, -0.5, -50.0, 0.5, 0.5, 5.0],
            "|Visible|shape": [-1.0, -1.0, -80.0, 1.0, 1.0, -10.0],
            "|Behind|shape": [-1.0, -1.0, 2.0, 1.0, 1.0, 4.0],
            "|Lateral|shape": [1000.0, -1.0, -20.0, 1002.0, 1.0, -10.0],
        }

    def nodeType(self, _node):
        return "mesh" if _node.endswith("shape") else "transform"

    def objExists(self, _name):
        return True

    def ls(self, node=None, **_kwargs):
        if node is None:
            return []
        return list(node) if isinstance(node, (list, tuple)) else [node]

    def listRelatives(self, camera, **kwargs):
        if kwargs.get("shapes") and kwargs.get("type") == "camera":
            return [camera + "|cameraShape"]
        return []

    def currentTime(self, value=None, query=False, edit=False, **_kwargs):
        if query:
            return self.frame
        if edit:
            self.frame = float(value)
        return self.frame

    def exactWorldBoundingBox(self, shape, **_kwargs):
        self.bbox_calls.append(shape)
        return list(self.bounds[shape])

    def getAttr(self, plug):
        if plug.endswith(".worldInverseMatrix[0]"):
            return [
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ]
        if plug.endswith(".nearClipPlane"):
            return 1.0
        if plug.endswith(".farClipPlane"):
            return 100.0
        if plug.endswith(".orthographic"):
            return 0
        if plug.endswith(".panZoomEnabled") or plug.endswith(".shakeEnabled"):
            return 0
        if (
            plug.endswith(".horizontalFilmOffset")
            or plug.endswith(".verticalFilmOffset")
            or plug.endswith(".filmRollValue")
        ):
            return 0.0
        if plug.endswith(".horizontalFilmAperture"):
            return 1.417
        if plug.endswith(".verticalFilmAperture"):
            return 0.945
        if plug.endswith(".focalLength"):
            return 35.0
        if plug == "defaultResolution.deviceAspectRatio":
            return 1.5
        if (
            plug.endswith(".overscan")
            or plug.endswith(".lensSqueezeRatio")
            or plug.endswith(".cameraScale")
        ):
            return 1.0
        raise RuntimeError("Unexpected attribute: {0}".format(plug))


sample_cmds = SampleDepthCmds()
sample_originals = {
    "cmds": runner.cmds,
    "_all_depth_renderable_shapes": runner._all_depth_renderable_shapes,
    "_marker_renderable_shapes": runner._marker_renderable_shapes,
}
try:
    runner.cmds = sample_cmds
    runner._all_depth_renderable_shapes = lambda *_args, **_kwargs: list(sample_cmds.bounds)
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    sampled_report = runner._sampled_shot_depth_range(
        "|shotCamera",
        [101.0],
        1500,
        1000,
    )
finally:
    for name, value in sample_originals.items():
        setattr(runner, name, value)

assert sampled_report["near"] == 45.0
assert sampled_report["far"] == 50.0
assert sampled_report["mesh_shape_count"] == 4
assert sampled_report["sample_count"] == 1
assert sampled_report["considered_bbox_count"] == 4
assert sampled_report["intersected_bbox_count"] == 2
assert sampled_report["intersected_sample_count"] == 2
assert sampled_report["representative_sample_count"] == 2
assert sampled_report["range_basis"] == (
    "complete_sequence_screen_valid_shape_representative_extrema_fallback"
)
assert sampled_report["range_candidate_scope"] == (
    "screen_valid_shapes_small_scene_fallback"
)
assert sampled_report["foreground_representative_sample_count"] == 0
assert sampled_report["context_representative_sample_count"] == 2
assert sampled_report["rejected_bbox_count"] == 2
assert sampled_report["clip_rejected_bbox_count"] == 1
assert sampled_report["frustum_rejected_bbox_count"] == 1
assert sampled_report["visibility_rejected_bbox_count"] == 0
assert sampled_report["invalid_bbox_count"] == 0
assert sampled_report["frame_reports"] == [{
    "frame": 101.0,
    "camera_near_clip": 1.0,
    "camera_far_clip": 100.0,
    "considered_bbox_count": 4,
    "intersected_bbox_count": 2,
    "rejected_bbox_count": 2,
    "near": 1.0,
    "far": 80.0,
    "representative_near": 45.0,
    "representative_far": 50.0,
    "foreground_intersected_bbox_count": 0,
    "context_intersected_bbox_count": 2,
    "foreground_representative_near": None,
    "foreground_representative_far": None,
    "screen_sample_tested_bbox_count": 0,
    "screen_sample_visible_bbox_count": 0,
    "screen_sample_rejected_bbox_count": 0,
    "bbox_fallback_candidate_count": 2,
    "role_excluded_bbox_count": 0,
    "frustum_filter": "perspective_output_aspect_gate",
}]
assert sample_cmds.frame == 77.0
assert sample_cmds.bbox_calls == list(sample_cmds.bounds)
assert all(isinstance(item, str) for item in sample_cmds.bbox_calls)


# Actor markers define the effective 0.0..0.9 normalization population while
# large set/context geometry remains rendered and auditable.
foreground_cmds = SampleDepthCmds()
foreground_cmds.bounds = {
    "|ActorNear|shape": [-1.0, -1.0, -20.0, 1.0, 1.0, -10.0],
    "|ActorFar|shape": [-1.0, -1.0, -40.0, 1.0, 1.0, -30.0],
    "|WholeMap|shape": [-1.0, -1.0, -90.0, 1.0, 1.0, -80.0],
}
foreground_job = {
    "_depth_foreground_shapes": [
        "|ActorNear|shape",
        "|ActorFar|shape",
    ],
    "_depth_range_shape_roles": {
        "|ActorNear|shape": {
            "root": "|ActorNear",
            "marker": "Red",
            "role": "foreground",
        },
        "|ActorFar|shape": {
            "root": "|ActorFar",
            "marker": "Green",
            "role": "foreground",
        },
        "|WholeMap|shape": {
            "root": "|WholeMap",
            "marker": "Sky Grid",
            "role": "context",
        },
    },
}
try:
    runner.cmds = foreground_cmds
    runner._all_depth_renderable_shapes = (
        lambda *_args, **_kwargs: list(foreground_cmds.bounds)
    )
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    foreground_report = runner._sampled_shot_depth_range(
        "|shotCamera",
        [101.0],
        1500,
        1000,
        job=foreground_job,
    )
finally:
    for name, value in sample_originals.items():
        setattr(runner, name, value)

assert abs(foreground_report["near"] - 15.2) < 1.0e-9
assert abs(foreground_report["far"] - 34.8) < 1.0e-9
assert foreground_report["range_candidate_scope"] == (
    "screen_valid_foreground_actor_shapes"
)
assert foreground_report["foreground_shape_path_count"] == 2
assert foreground_report["context_shape_path_count"] == 1
assert foreground_report["foreground_representative_sample_count"] == 2
assert foreground_report["context_representative_sample_count"] == 0
assert foreground_report["screen_rejected_representative_sample_count"] == 0
assert foreground_report["role_excluded_representative_sample_count"] == 1
assert foreground_report["rejection_accounting_policy"] == (
    "disjoint_normalization_outcomes"
)
assert foreground_report["representative_sample_count"] == sum((
    foreground_report["foreground_representative_sample_count"],
    foreground_report["context_representative_sample_count"],
    foreground_report["screen_rejected_representative_sample_count"],
    foreground_report["role_excluded_representative_sample_count"],
))
assert foreground_report["renderable_shape_count"] == 3


# Without Actor markers, a sufficiently populated generic scene uses the
# deterministic per-shape temporal-extrema P95 fallback instead of one remote
# bbox consuming the complete range.
generic_cmds = SampleDepthCmds()
generic_cmds.bounds = {
    "|Generic{0:02d}|shape".format(index): [
        -1.0,
        -1.0,
        -float(index + 12),
        1.0,
        1.0,
        -float(index + 10),
    ]
    for index in range(20)
}
try:
    runner.cmds = generic_cmds
    runner._all_depth_renderable_shapes = (
        lambda *_args, **_kwargs: list(generic_cmds.bounds)
    )
    runner._marker_renderable_shapes = lambda shapes: list(shapes)
    generic_report = runner._sampled_shot_depth_range(
        "|shotCamera",
        [101.0],
        1500,
        1000,
    )
finally:
    for name, value in sample_originals.items():
        setattr(runner, name, value)

assert abs(generic_report["near"] - 11.95) < 1.0e-9
assert abs(generic_report["far"] - 29.05) < 1.0e-9
assert generic_report["fallback_percentile"] == 0.95
assert generic_report["normalization_candidate_shape_path_count"] == 20
assert generic_report["range_candidate_scope"] == (
    "screen_valid_shapes_generic_robust_fallback"
)
assert generic_report["range_basis"] == (
    "complete_sequence_screen_valid_shape_temporal_extrema_percentiles"
)


class ApiBoundPoint:
    def __init__(self, x, y, z):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class ApiBoundingBox:
    def __init__(self, values):
        self.min = ApiBoundPoint(values[0], values[1], values[2])
        self.max = ApiBoundPoint(values[3], values[4], values[5])


class ApiDagPath:
    def __init__(self, owner, shape):
        self.owner = owner
        self.shape = shape

    def isVisible(self):
        return True

    def inclusiveMatrix(self):
        return SampleMMatrix([])


class ApiSelectionList:
    def __init__(self):
        self.shape = ""

    def add(self, shape):
        self.shape = shape

    def getDagPath(self, _index):
        return ApiDagPath(api_cmds, self.shape)


class ApiMFnDagNode:
    def __init__(self, dag_path):
        self.dag_path = dag_path

    @property
    def boundingBox(self):
        frame = int(self.dag_path.owner.frame)
        return ApiBoundingBox(
            self.dag_path.owner.frame_bounds[frame][self.dag_path.shape]
        )


class ApiDepthCmds(SampleDepthCmds):
    def __init__(self):
        super().__init__()
        self.exact_bbox_calls = 0
        shapes = (
            "|NearInstance|sharedShape",
            "|FarInstance|sharedShape",
            "|Set|surfaceShape",
        )
        self.frame_bounds = {
            101: dict((shape, [-1, -1, -20, 1, 1, -10]) for shape in shapes),
            102: dict((shape, [-1, -1, -300, 1, 1, -200]) for shape in shapes),
            103: dict((shape, [-1, -1, -25, 1, 1, -15]) for shape in shapes),
        }

    def nodeType(self, node):
        if node.endswith("cameraShape"):
            return "camera"
        if node.endswith("surfaceShape"):
            return "nurbsSurface"
        if node.endswith("sharedShape"):
            return "mesh"
        return "transform"

    def exactWorldBoundingBox(self, *_args, **_kwargs):
        self.exact_bbox_calls += 1
        raise AssertionError("API-backed depth range must not use cmds bbox")

    def getAttr(self, plug):
        clip_ranges = {
            101: (1.0, 100.0),
            102: (2.0, 400.0),
            103: (0.5, 80.0),
        }
        if plug.endswith(".nearClipPlane"):
            return clip_ranges[int(self.frame)][0]
        if plug.endswith(".farClipPlane"):
            return clip_ranges[int(self.frame)][1]
        return super().getAttr(plug)


class ScreenSelectionList(ApiSelectionList):
    def getDagPath(self, _index):
        return ApiDagPath(screen_cmds, self.shape)


class ScreenMFnMesh:
    def __init__(self, dag_path):
        self.dag_path = dag_path

    @property
    def numVertices(self):
        return len(self.dag_path.owner.mesh_points[self.dag_path.shape])

    @property
    def numPolygons(self):
        return len(self.dag_path.owner.mesh_polygons[self.dag_path.shape])

    def getPoints(self, _space):
        owner = self.dag_path.owner
        owner.mesh_sample_calls[self.dag_path.shape] = (
            owner.mesh_sample_calls.get(self.dag_path.shape, 0) + 1
        )
        return list(owner.mesh_points[self.dag_path.shape])

    def getPolygonVertices(self, polygon_index):
        return list(
            self.dag_path.owner.mesh_polygons[self.dag_path.shape][
                int(polygon_index)
            ]
        )


class ScreenDepthCmds(ApiDepthCmds):
    def __init__(self):
        super().__init__()
        self.frame = 101.0
        self.mesh_sample_calls = {}
        self.frame_bounds = {101: {
            "|CountryDog|shape": [-100.0, -1.0, -7.0, 100.0, 1.0, -5.0],
            "|TentenNear|shape": [-1.0, -1.0, -20.0, 1.0, 1.0, -10.0],
            "|TentenFar|shape": [-1.0, -1.0, -40.0, 1.0, 1.0, -30.0],
            "|WholeMap|shape": [-1.0, -1.0, -90.0, 1.0, 1.0, -80.0],
        }}
        self.mesh_points = {
            "|CountryDog|shape": [
                SampleMPoint(-100, -1, -6, 1),
                SampleMPoint(-90, -1, -6, 1),
                SampleMPoint(-90, 1, -6, 1),
                SampleMPoint(-100, 1, -6, 1),
                SampleMPoint(90, -1, -6, 1),
                SampleMPoint(100, -1, -6, 1),
                SampleMPoint(100, 1, -6, 1),
                SampleMPoint(90, 1, -6, 1),
            ],
            "|TentenNear|shape": [
                SampleMPoint(-1, -1, -20, 1),
                SampleMPoint(1, -1, -20, 1),
                SampleMPoint(1, 1, -10, 1),
                SampleMPoint(-1, 1, -10, 1),
            ],
            "|TentenFar|shape": [
                SampleMPoint(-1, -1, -40, 1),
                SampleMPoint(1, -1, -40, 1),
                SampleMPoint(1, 1, -30, 1),
                SampleMPoint(-1, 1, -30, 1),
            ],
            "|WholeMap|shape": [
                SampleMPoint(-1, -1, -90, 1),
                SampleMPoint(1, -1, -90, 1),
                SampleMPoint(1, 1, -80, 1),
                SampleMPoint(-1, 1, -80, 1),
            ],
        }
        self.mesh_polygons = {
            "|CountryDog|shape": [[0, 1, 2, 3], [4, 5, 6, 7]],
            "|TentenNear|shape": [[0, 1, 2, 3]],
            "|TentenFar|shape": [[0, 1, 2, 3]],
            "|WholeMap|shape": [[0, 1, 2, 3]],
        }

    def nodeType(self, node):
        if node.endswith("|cameraShape"):
            return "camera"
        if node.endswith("|shape"):
            return "mesh"
        return "transform"


api_cmds = ApiDepthCmds()
api_shapes = [
    "|NearInstance|sharedShape",
    "|FarInstance|sharedShape",
    "|Set|surfaceShape",
]
api_originals = {
    "cmds": runner.cmds,
    "_all_depth_renderable_shapes": runner._all_depth_renderable_shapes,
    "MSelectionList": getattr(open_maya_module, "MSelectionList", None),
    "MFnDagNode": getattr(open_maya_module, "MFnDagNode", None),
}
api_progress = []
original_api_progress = runner._write_progress
try:
    runner.cmds = api_cmds
    runner._all_depth_renderable_shapes = lambda *_args, **_kwargs: list(api_shapes)
    open_maya_module.MSelectionList = ApiSelectionList
    open_maya_module.MFnDagNode = ApiMFnDagNode
    runner._write_progress = lambda _job, stage, _message, **extra: (
        api_progress.append((stage, dict(extra)))
    )
    api_report = runner._sampled_shot_depth_range(
        "|shotCamera",
        [101.0, 102.0, 103.0],
        2000,
        1000,
        job={"progress_path": "C:/tmp/depth-progress.json"},
    )
finally:
    runner.cmds = api_originals["cmds"]
    runner._all_depth_renderable_shapes = api_originals[
        "_all_depth_renderable_shapes"
    ]
    runner._write_progress = original_api_progress
    for name in ("MSelectionList", "MFnDagNode"):
        original = api_originals[name]
        if original is None:
            delattr(open_maya_module, name)
        else:
            setattr(open_maya_module, name, original)

assert api_report["evaluation_backend"] == "maya_api_2_dag_bounds"
assert api_report["evaluated_frames"] == [101.0, 102.0, 103.0]
assert api_report["camera_near_clip_min"] == 0.5
assert api_report["camera_near_clip_max"] == 2.0
assert api_report["camera_far_clip_min"] == 80.0
assert api_report["camera_far_clip_max"] == 400.0
assert api_report["camera_clip_animated"] is True
assert api_report["near"] == 15.0
assert api_report["far"] == 250.0
assert api_report["representative_sample_count"] == 9
assert api_report["mesh_shape_count"] == 2
assert api_report["nurbs_surface_shape_count"] == 1
assert api_cmds.exact_bbox_calls == 0
assert [item[1].get("completed_frames") for item in api_progress] == [0, 1, 2, 3]


# A bbox can conservatively cross the camera gate while every real mesh
# surface sample remains offscreen.  Such an Actor must not define the v6
# normalization range, and context must not pay mesh-sampling cost while a
# foreground marker population exists.
screen_cmds = ScreenDepthCmds()
screen_shapes = list(screen_cmds.frame_bounds[101])
screen_job = {
    "_depth_foreground_shapes": [
        "|CountryDog|shape",
        "|TentenNear|shape",
        "|TentenFar|shape",
    ],
    "_depth_range_shape_roles": {
        "|CountryDog|shape": {
            "root": "|CountryDog",
            "marker": "Red",
            "role": "foreground",
        },
        "|TentenNear|shape": {
            "root": "|Tenten",
            "marker": "Green",
            "role": "foreground",
        },
        "|TentenFar|shape": {
            "root": "|Tenten",
            "marker": "Green",
            "role": "foreground",
        },
        "|WholeMap|shape": {
            "root": "|WholeMap",
            "marker": "Sky Grid",
            "role": "context",
        },
    },
}
screen_originals = {
    "cmds": runner.cmds,
    "_all_depth_renderable_shapes": runner._all_depth_renderable_shapes,
    "MSelectionList": getattr(open_maya_module, "MSelectionList", None),
    "MFnDagNode": getattr(open_maya_module, "MFnDagNode", None),
    "MFnMesh": getattr(open_maya_module, "MFnMesh", None),
    "MSpace": getattr(open_maya_module, "MSpace", None),
}
try:
    runner.cmds = screen_cmds
    runner._all_depth_renderable_shapes = lambda *_args, **_kwargs: list(
        screen_shapes
    )
    open_maya_module.MSelectionList = ScreenSelectionList
    open_maya_module.MFnDagNode = ApiMFnDagNode
    open_maya_module.MFnMesh = ScreenMFnMesh
    open_maya_module.MSpace = types.SimpleNamespace(kObject=0)
    screen_report = runner._sampled_shot_depth_range(
        "|shotCamera",
        [101.0],
        1500,
        1000,
        job=screen_job,
    )
finally:
    runner.cmds = screen_originals["cmds"]
    runner._all_depth_renderable_shapes = screen_originals[
        "_all_depth_renderable_shapes"
    ]
    for name in ("MSelectionList", "MFnDagNode", "MFnMesh", "MSpace"):
        original = screen_originals[name]
        if original is None:
            delattr(open_maya_module, name)
        else:
            setattr(open_maya_module, name, original)

assert abs(screen_report["near"] - 15.2) < 1.0e-9, screen_report
assert abs(screen_report["far"] - 34.8) < 1.0e-9, screen_report
assert screen_report["screen_sample_tested_bbox_count"] == 3
assert screen_report["screen_sample_visible_bbox_count"] == 2
assert screen_report["screen_sample_rejected_bbox_count"] == 1
assert screen_report["screen_rejected_representative_sample_count"] == 1
assert screen_report["role_excluded_representative_sample_count"] == 1
assert screen_report["representative_sample_count"] == sum((
    screen_report["foreground_representative_sample_count"],
    screen_report["context_representative_sample_count"],
    screen_report["screen_rejected_representative_sample_count"],
    screen_report["role_excluded_representative_sample_count"],
))
assert screen_cmds.mesh_sample_calls == {
    "|CountryDog|shape": 1,
    "|TentenNear|shape": 1,
    "|TentenFar|shape": 1,
}
screen_bindings = {
    item["root"]: item for item in screen_report["binding_range_reports"]
}
assert screen_bindings["|CountryDog"]["screen_rejected_shape_path_count"] == 1
assert screen_bindings["|CountryDog"]["normalization_candidate_sample_count"] == 0
assert screen_bindings["|CountryDog"]["selected_for_normalization"] is False
assert screen_bindings["|Tenten"]["screen_visible_shape_path_count"] == 2
assert screen_bindings["|Tenten"]["normalization_candidate_sample_count"] == 2
assert screen_bindings["|Tenten"]["selected_for_normalization"] is True
assert screen_bindings["|WholeMap"]["role_excluded_shape_path_count"] == 1
assert screen_report["range_extrema_sources"]["near"]["shape"] == (
    "|TentenNear|shape"
)

try:
    runner.cmds = depth_cmds
    runner._depth_range(
        "|shotCamera",
        {"depth_profile": "unsupported-depth-profile"},
    )
except RuntimeError:
    pass
else:
    raise AssertionError("Unknown depth profiles must fail closed.")
finally:
    runner.cmds = depth_originals["cmds"]


class VisibilityCmds:
    def __init__(self):
        self.values = {}
        self.inputs = {}
        self.layers = {}

    @staticmethod
    def _attribute(plug):
        return plug.rsplit(".", 1)[-1] if "." in plug else ""

    def ls(self, node=None, long=False, **_kwargs):
        if node is None:
            return []
        return [node]

    def attributeQuery(self, attribute, node=None, exists=False):
        return bool(exists and attribute == "intermediateObject")

    def objExists(self, name):
        if "." not in name:
            return True
        return self._attribute(name) in {
            "visibility",
            "lodVisibility",
            "template",
            "overrideEnabled",
            "overrideVisibility",
            "intermediateObject",
        }

    def getAttr(self, plug):
        if plug in self.values:
            return self.values[plug]
        return {
            "visibility": True,
            "lodVisibility": True,
            "template": False,
            "overrideEnabled": False,
            "overrideVisibility": True,
            "intermediateObject": False,
        }[self._attribute(plug)]

    def listConnections(
        self,
        target,
        source=True,
        destination=False,
        plugs=False,
        type=None,
    ):
        del source, destination, plugs
        if type == "displayLayer":
            return list(self.layers.get(target, []))
        return list(self.inputs.get(target, []))


visibility_cmds = VisibilityCmds()
runner.cmds = visibility_cmds

visible_a = "|Asset|VisibleA|SharedShape"
visible_b = "|Asset|VisibleB|SharedShape"
static_hidden = "|Asset|HiddenPose|SharedShape"
animated_hidden = "|Asset|AnimatedPose|SharedShape"
driven_hidden = "|Asset|DrivenPose|SharedShape"
lod_hidden = "|Asset|LodHidden|LodShape"
override_hidden = "|Asset|OverrideHidden|OverrideShape"
template_hidden = "|Asset|TemplateHidden|TemplateShape"
layer_hidden = "|Asset|LayerHidden|LayerShape"
animated_layer_hidden = "|Asset|AnimatedLayerHidden|LayerShape"
intermediate_hidden = "|Asset|VisibleA|IntermediateShape"

visibility_cmds.values["|Asset|HiddenPose.visibility"] = False
visibility_cmds.values["|Asset|AnimatedPose.visibility"] = False
visibility_cmds.inputs["|Asset|AnimatedPose.visibility"] = ["animatedVisibility"]
visibility_cmds.values["|Asset|DrivenPose.visibility"] = False
visibility_cmds.inputs["|Asset|DrivenPose.visibility"] = ["visibilityCondition"]
visibility_cmds.values["|Asset|LodHidden.lodVisibility"] = False
visibility_cmds.values["|Asset|OverrideHidden.overrideEnabled"] = True
visibility_cmds.values["|Asset|OverrideHidden.overrideVisibility"] = False
visibility_cmds.values["|Asset|TemplateHidden.template"] = True
visibility_cmds.layers[layer_hidden] = ["hiddenLayer"]
visibility_cmds.values["hiddenLayer.visibility"] = False
visibility_cmds.layers[animated_layer_hidden] = ["animatedHiddenLayer"]
visibility_cmds.values["animatedHiddenLayer.visibility"] = False
visibility_cmds.inputs["animatedHiddenLayer.visibility"] = ["layerVisibilityCurve"]
visibility_cmds.values[intermediate_hidden + ".intermediateObject"] = True

filtered = runner._marker_renderable_shapes(
    [
        visible_a,
        visible_b,
        static_hidden,
        animated_hidden,
        driven_hidden,
        lod_hidden,
        override_hidden,
        template_hidden,
        layer_hidden,
        animated_layer_hidden,
        intermediate_hidden,
    ]
)
assert set(filtered) == {
    visible_a,
    visible_b,
    animated_hidden,
    driven_hidden,
    animated_layer_hidden,
}
assert runner._is_intermediate_shape(intermediate_hidden) is True
assert runner._is_intermediate_shape(visible_a) is False
assert visible_a in filtered and visible_b in filtered, "Legitimate visible instances must not be UUID-deduplicated."


class RenderCmds:
    def __init__(self, root):
        self.root = Path(root)
        self.images_rule = "images"
        self.capture_folder = None
        self.prefix = ""
        self.frames = []
        self.render_kwargs = []

    def listRelatives(self, camera, **_kwargs):
        return [camera + "|cameraShape"]

    def workspace(
        self,
        query=False,
        rootDirectory=False,
        fileRuleEntry=None,
        fileRule=None,
    ):
        if query and rootDirectory:
            return str(self.root)
        if fileRuleEntry == "images":
            return self.images_rule
        if fileRule:
            self.images_rule = fileRule[1]
            self.capture_folder = Path(fileRule[1])
        return ""

    def setAttr(self, plug, value, **_kwargs):
        if plug == "defaultRenderGlobals.imageFilePrefix":
            self.prefix = value

    def currentTime(self, frame, **_kwargs):
        self.frames.append(frame)

    def ogsRender(self, **_kwargs):
        self.render_kwargs.append(dict(_kwargs))
        assert self.capture_folder is not None
        self.capture_folder.mkdir(parents=True, exist_ok=True)
        (self.capture_folder / (self.prefix + ".png")).write_bytes(b"png")
        return True


with tempfile.TemporaryDirectory(prefix="hmb_maya_runner_regression_") as temp_dir:
    render_cmds = RenderCmds(temp_dir)
    runner.cmds = render_cmds
    progress = []
    original_write_progress = runner._write_progress

    def capture_progress(job, stage, message, **extra):
        progress.append((job, stage, message, extra))

    runner._write_progress = capture_progress
    try:
        outputs, frame_map = runner._render_frames(
            camera="|shotCamera",
            frame_values=[101.0, 102.0],
            width=1280,
            height=720,
            frames_folder=str(Path(temp_dir) / "frames"),
            output_name="marker",
            job={
                "progress_path": str(Path(temp_dir) / "progress.json"),
                "screen_space_patterns": True,
            },
            progress_stage="rendering_frames",
        )
    finally:
        runner._write_progress = original_write_progress

    assert render_cmds.frames == [101.0, 102.0]
    assert all(
        item.get("enableMultisample") is False
        for item in render_cmds.render_kwargs
    )
    assert len(outputs) == 2 and all(Path(path).is_file() for path in outputs)
    assert [item["maya_frame"] for item in frame_map] == [101.0, 102.0]
    assert [item[3]["frame_status"] for item in progress] == [
        "started",
        "completed",
        "started",
        "completed",
    ]
    assert [item[3]["frame_index"] for item in progress] == [1, 1, 2, 2]
    assert [item[3]["completed_frames"] for item in progress] == [0, 1, 1, 2]
    assert all(item[1] == "rendering_frames" for item in progress)
    assert all(item[3]["frame_count"] == 2 for item in progress)

    depth_pass_calls = []
    depth_helper_originals = {
        "_apply_depth_shader": runner._apply_depth_shader,
        "_set_viewport_render_options": runner._set_viewport_render_options,
        "_write_progress": runner._write_progress,
    }
    def fake_apply_depth_shader(
        camera,
        job,
        frame_values=None,
        width=None,
        height=None,
    ):
        depth_pass_calls.append(
            ("shader", camera, dict(job), list(frame_values or []), width, height)
        )
        report = {
            "profile": runner.DEPTH_PLAYBLAST_PROFILE,
            "near": 1.0,
            "far": 100.0,
            "assignment_verification": {
                "shape_path_count": 1,
                "mesh_path_count": 1,
                "nurbs_surface_path_count": 0,
                "verified_shape_path_count": 0,
                "verified_mesh_face_count": 0,
                "rendered_frame_count": 0,
                "expected_frame_assignment_count": 0,
                "verified_frame_assignment_count": 0,
            },
        }

        def assign_frame(_frame, _index, _count):
            verification = report["assignment_verification"]
            verification["verified_shape_path_count"] = 1
            verification["verified_mesh_face_count"] += 12
            verification["rendered_frame_count"] += 1
            verification["expected_frame_assignment_count"] += 1
            verification["verified_frame_assignment_count"] += 1

        return report, assign_frame

    runner._apply_depth_shader = fake_apply_depth_shader
    runner._set_viewport_render_options = lambda **kwargs: (
        depth_pass_calls.append(("options", dict(kwargs)))
        or {"output_transform_disabled": True}
    )
    runner._write_progress = capture_progress
    try:
        depth_outputs, depth_frame_map, depth_metadata = runner._render_depth_pass(
            camera="|shotCamera",
            frame_values=[101.0, 102.0],
            width=1280,
            height=720,
            frames_folder=str(Path(temp_dir) / "depth_frames"),
            output_name="marker_depth",
            job={
                "progress_path": str(Path(temp_dir) / "depth_progress.json"),
                "depth_profile": runner.DEPTH_PLAYBLAST_PROFILE,
            },
        )
    finally:
        for name, value in depth_helper_originals.items():
            setattr(runner, name, value)

    assert [item[0] for item in depth_pass_calls] == ["shader", "options"]
    assert depth_pass_calls[0][3:] == ([101.0, 102.0], 1280, 720)
    assert depth_pass_calls[1][1]["depth_mode"] is True
    assert depth_metadata["profile"] == runner.DEPTH_PLAYBLAST_PROFILE
    assert depth_metadata["render_options"]["output_transform_disabled"] is True
    assert depth_metadata["assignment_verification"]["rendered_frame_count"] == 2
    assert (
        depth_metadata["assignment_verification"][
            "verified_frame_assignment_count"
        ]
        == 2
    )
    assert len(depth_outputs) == 2 and all(
        Path(path).is_file() for path in depth_outputs
    )
    assert [item["maya_frame"] for item in depth_frame_map] == [101.0, 102.0]
    assert render_cmds.frames == [101.0, 102.0, 101.0, 102.0]
    assert all(
        item.get("enableMultisample") is False
        for item in render_cmds.render_kwargs
    )
    depth_progress = [
        item for item in progress if item[1] == "rendering_depth_frames"
    ]
    assert depth_progress[0][3]["completed_frames"] == 0
    assert [item[3].get("frame_status") for item in depth_progress[1:]] == [
        "started",
        "completed",
        "started",
        "completed",
    ]


class RunCmds:
    @staticmethod
    def about(version=False):
        return "2027" if version else ""

    @staticmethod
    def ls(*_args, **_kwargs):
        return []


with tempfile.TemporaryDirectory(prefix="hmb_maya_depth_run_") as temp_dir:
    temp_root = Path(temp_dir)
    scene_path = temp_root / "shot.mb"
    scene_path.write_bytes(b"maya")
    color_frames = temp_root / "color_frames"
    depth_frames = temp_root / "depth_frames"
    color_sidecar = temp_root / "color.hmb.json"
    depth_sidecar = temp_root / "depth.hmb.json"
    result_path = temp_root / "result.json"
    job_path = temp_root / "job.json"
    job = {
        "operation": "render",
        "scene_path": str(scene_path),
        "result_path": str(result_path),
        "sidecar_path": str(color_sidecar),
        "frames_folder": str(color_frames),
        "output_name": "shot_color",
        "camera": "|shotCamera",
        "width": 1280,
        "height": 720,
        "start_frame": 101.0,
        "end_frame": 101.0,
        "fps": 24.0,
        "apply_marker_shaders": True,
        "force_high_quality_viewport": True,
        "require_full_smooth_geometry": True,
        "screen_space_patterns": True,
        "screen_space_pattern_profile": runner.SCREEN_SPACE_PATTERN_PROFILE,
        "marker_catalog_version": 4,
        "generate_depth_playblast": True,
        "depth_frames_folder": str(depth_frames),
        "depth_output_name": "shot_depth",
        "depth_sidecar_path": str(depth_sidecar),
        "depth_profile": runner.DEPTH_PLAYBLAST_PROFILE,
    }
    runner._write_json(str(job_path), job)
    run_calls = []
    run_originals = {
        "cmds": runner.cmds,
        "_open_scene_for_job": runner._open_scene_for_job,
        "_load_marker_catalog": runner._load_marker_catalog,
        "_read_job_bindings": runner._read_job_bindings,
        "_resolve_camera": runner._resolve_camera,
        "_assert_depth_drawables_supported": runner._assert_depth_drawables_supported,
        "_apply_marker_shaders": runner._apply_marker_shaders,
        "_apply_assigned_render_scope": runner._apply_assigned_render_scope,
        "_apply_full_smooth_viewport": runner._apply_full_smooth_viewport,
        "_restore_full_smooth_viewport": runner._restore_full_smooth_viewport,
        "_set_viewport_render_options": runner._set_viewport_render_options,
        "_render_frames": runner._render_frames,
        "_render_depth_pass": runner._render_depth_pass,
        "_marker_payload": runner._marker_payload,
        "_write_progress": runner._write_progress,
        "_emit_console": runner._emit_console,
    }

    def fake_color_frames(**kwargs):
        run_calls.append("color")
        folder = Path(kwargs["frames_folder"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (kwargs["output_name"] + ".000000.png")
        path.write_bytes(b"color")
        return [str(path)], [{
            "sequence_index": 0,
            "maya_frame": 101.0,
            "file": path.name,
        }]

    def fake_depth_pass(**kwargs):
        run_calls.append("depth")
        folder = Path(kwargs["frames_folder"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (kwargs["output_name"] + ".000000.png")
        path.write_bytes(b"depth")
        return [str(path)], [{
            "sequence_index": 0,
            "maya_frame": 101.0,
            "file": path.name,
        }], {
            "profile": runner.DEPTH_PLAYBLAST_PROFILE,
            "near": 1.0,
            "far": 100.0,
            "direction": "near_white_far_black",
            "background": "pure_black",
        }

    try:
        runner.cmds = RunCmds()
        runner._open_scene_for_job = (
            lambda _job: run_calls.append("open") or str(scene_path)
        )
        runner._load_marker_catalog = lambda _job: {}
        runner._read_job_bindings = lambda _job: [{
            "color": "Red",
            "asset_id": "Hero",
            "subject_root": "|Hero",
        }]
        runner._resolve_camera = lambda _camera: "|shotCamera"
        runner._assert_depth_drawables_supported = (
            lambda _camera=None: run_calls.append("depth_preflight")
        )
        runner._apply_marker_shaders = (
            lambda _bindings, _job: run_calls.append("marker") or []
        )
        runner._apply_assigned_render_scope = (
            lambda _bindings, _job: (
                run_calls.append("scope") or [],
                {
                    "policy": "maya_authored_visible_and_color_bound_and_picker_visible",
                    "allowed_shape_path_count": 1,
                    "excluded_shape_path_count": 0,
                },
            )
        )
        runner._apply_full_smooth_viewport = (
            lambda _job: (
                run_calls.append("quality") or {"attributes": []},
                {"profile": runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE},
            )
        )
        runner._restore_full_smooth_viewport = (
            lambda _state: run_calls.append("restore") or []
        )
        runner._set_viewport_render_options = lambda **_kwargs: {
            "output_transform_disabled": True,
        }
        runner._render_frames = fake_color_frames
        runner._render_depth_pass = fake_depth_pass
        runner._marker_payload = lambda _bindings, **_kwargs: []
        runner._write_progress = lambda *_args, **_kwargs: None
        runner._emit_console = lambda *_args, **_kwargs: None
        run_result = runner.run(str(job_path))
    finally:
        for name, value in run_originals.items():
            setattr(runner, name, value)

    assert run_calls.count("open") == 1
    # Depth preflight belongs to the optional Depth pass and must not run ahead
    # of, or block, a valid Color render.
    assert "depth_preflight" not in run_calls
    assert run_calls.index("scope") < run_calls.index("color")
    assert run_calls.index("color") < run_calls.index("depth")
    assert run_calls.index("depth") < run_calls.index("restore")
    assert run_result["ok"] is True
    assert run_result["frame_count"] == 1
    assert run_result["depth_frame_count"] == 1
    assert Path(run_result["depth_frames_folder"]).resolve() == depth_frames.resolve()
    assert run_result["depth_output_name"] == "shot_depth"
    assert Path(run_result["depth_sidecar_path"]).resolve() == depth_sidecar.resolve()
    assert run_result["depth_profile"] == runner.DEPTH_PLAYBLAST_PROFILE
    assert run_result["depth_range_report"]["near"] == 1.0
    assert color_sidecar.is_file()
    assert depth_sidecar.is_file()
    color_payload = runner._read_json(str(color_sidecar))
    depth_payload = runner._read_json(str(depth_sidecar))
    assert color_payload["screen_space_pattern_profile"] == (
        runner.SCREEN_SPACE_PATTERN_PROFILE
    )
    assert color_payload["screen_space_postprocess_pending"] is True
    assert depth_payload["schema"] == "hmb-maya-depth-playblast"
    assert depth_payload["profile"] == runner.DEPTH_PLAYBLAST_PROFILE
    assert depth_payload["frame_count"] == 1
    assert depth_payload["depth_range_report"]["background"] == "pure_black"


with tempfile.TemporaryDirectory(prefix="hmb_maya_independent_aux_") as temp_dir:
    temp_root = Path(temp_dir)
    scene_path = temp_root / "shot.mb"
    scene_path.write_bytes(b"maya")
    color_frames = temp_root / "color_frames"
    depth_frames = temp_root / "depth_frames"
    motion_frames = temp_root / "motion_frames"
    color_sidecar = temp_root / "color.hmb.json"
    depth_sidecar = temp_root / "depth.hmb.json"
    motion_sidecar = temp_root / "motion.hmb.json"
    result_path = temp_root / "result.json"
    job_path = temp_root / "job.json"
    runner._write_json(str(job_path), {
        "operation": "render",
        "scene_path": str(scene_path),
        "result_path": str(result_path),
        "sidecar_path": str(color_sidecar),
        "frames_folder": str(color_frames),
        "output_name": "shot_color",
        "camera": "|shotCamera",
        "width": 1280,
        "height": 720,
        "start_frame": 101.0,
        "end_frame": 101.0,
        "fps": 24.0,
        "apply_marker_shaders": True,
        "force_high_quality_viewport": True,
        "screen_space_patterns": True,
        "screen_space_pattern_profile": runner.SCREEN_SPACE_PATTERN_PROFILE,
        "generate_depth_playblast": True,
        "depth_frames_folder": str(depth_frames),
        "depth_output_name": "shot_depth",
        "depth_sidecar_path": str(depth_sidecar),
        "depth_profile": runner.DEPTH_PLAYBLAST_PROFILE,
        "generate_motion_guide": True,
        "motion_guide_frames_folder": str(motion_frames),
        "motion_guide_output_name": "shot_motion",
        "motion_guide_sidecar_path": str(motion_sidecar),
        "motion_guide_profile": runner.MOTION_GUIDE_PROFILE,
    })
    independent_calls = []
    originals = {
        "cmds": runner.cmds,
        "_open_scene_for_job": runner._open_scene_for_job,
        "_load_marker_catalog": runner._load_marker_catalog,
        "_read_job_bindings": runner._read_job_bindings,
        "_resolve_camera": runner._resolve_camera,
        "_apply_marker_shaders": runner._apply_marker_shaders,
        "_apply_assigned_render_scope": runner._apply_assigned_render_scope,
        "_apply_full_smooth_viewport": runner._apply_full_smooth_viewport,
        "_restore_full_smooth_viewport": runner._restore_full_smooth_viewport,
        "_set_viewport_render_options": runner._set_viewport_render_options,
        "_render_frames": runner._render_frames,
        "_render_depth_pass": runner._render_depth_pass,
        "_render_motion_guide_pass": runner._render_motion_guide_pass,
        "_marker_payload": runner._marker_payload,
        "_write_progress": runner._write_progress,
        "_emit_console": runner._emit_console,
    }

    def independent_color(**kwargs):
        independent_calls.append("color")
        folder = Path(kwargs["frames_folder"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (kwargs["output_name"] + ".000000.png")
        path.write_bytes(b"color")
        return [str(path)], [{
            "sequence_index": 0,
            "maya_frame": 101.0,
            "file": path.name,
        }]

    def failed_depth(**_kwargs):
        independent_calls.append("depth_failed")
        raise RuntimeError("synthetic depth failure")

    def successful_motion(**kwargs):
        independent_calls.append("motion")
        folder = Path(kwargs["frames_folder"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (kwargs["output_name"] + ".000000.png")
        path.write_bytes(b"motion")
        return [str(path)], [{
            "sequence_index": 0,
            "maya_frame": 101.0,
            "file": path.name,
        }], {
            "profile": runner.MOTION_GUIDE_PROFILE,
            "target_count": 1,
        }

    try:
        runner.cmds = RunCmds()
        runner._open_scene_for_job = lambda _job: str(scene_path)
        runner._load_marker_catalog = lambda _job: {}
        runner._read_job_bindings = lambda _job: [{
            "color": "Red",
            "asset_id": "Hero",
            "subject_root": "|Hero",
        }]
        runner._resolve_camera = lambda _camera: "|shotCamera"
        runner._apply_marker_shaders = lambda _bindings, _job: []
        runner._apply_assigned_render_scope = lambda _bindings, _job: (
            [],
            {
                "policy": "maya_authored_visible_and_color_bound_and_picker_visible",
                "allowed_shape_path_count": 1,
                "excluded_shape_path_count": 0,
            },
        )
        runner._apply_full_smooth_viewport = lambda _job: (
            {"attributes": []},
            {"profile": runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE},
        )
        runner._restore_full_smooth_viewport = lambda _state: []
        runner._set_viewport_render_options = lambda **_kwargs: {}
        runner._render_frames = independent_color
        runner._render_depth_pass = failed_depth
        runner._render_motion_guide_pass = successful_motion
        runner._marker_payload = lambda _bindings, **_kwargs: []
        runner._write_progress = lambda *_args, **_kwargs: None
        runner._emit_console = lambda *_args, **_kwargs: None
        independent_result = runner.run(str(job_path))
    finally:
        for name, value in originals.items():
            setattr(runner, name, value)

    assert independent_calls == ["color", "depth_failed", "motion"]
    assert independent_result["ok"] is True
    assert independent_result["artifacts"]["color"]["ok"] is True
    assert independent_result["artifacts"]["depth"]["ok"] is False
    assert "synthetic depth failure" in independent_result["artifacts"]["depth"]["error"]
    assert independent_result["artifacts"]["motion_guide"]["ok"] is True
    assert color_sidecar.is_file()
    assert not depth_sidecar.exists()
    assert motion_sidecar.is_file()


class AuxiliaryScopeCmds:
    def __init__(self):
        self.layers = {}
        self.attributes = {}
        self.node_types = {
            "|Visible|meshShape": "mesh",
            "|Visible|surfaceShape": "nurbsSurface",
            "|EyeOff|meshShape": "mesh",
            "|Rig|aim_CTRLShape": "nurbsCurve",
            "|Rig|pivot_LOCShape": "locator",
        }

    def objExists(self, name):
        if name in self.layers or name in self.attributes:
            return True
        return name in self.node_types

    def nodeType(self, name):
        return self.node_types[name]

    def createDisplayLayer(self, empty=False, name="", number=1):
        assert empty is True
        self.layers[name] = []
        self.attributes[name + ".visibility"] = True
        return name

    def editDisplayLayerMembers(
        self,
        layer,
        members=None,
        noRecurse=False,
        query=False,
        fullNames=False,
    ):
        if query:
            assert fullNames is True
            return list(self.layers.get(layer, []))
        assert noRecurse is True
        self.layers[layer] = list(members or [])

    def ls(self, values=None, long=False, **_kwargs):
        if isinstance(values, (list, tuple, set)):
            return list(values)
        return [values] if values else []

    def setAttr(self, plug, value):
        self.attributes[plug] = value

    def getAttr(self, plug):
        return self.attributes[plug]


# Removing Color's temporary exclusion layer must not reveal a Picker-eye-off
# shape in the no-assignment auxiliary scope. The authored-visible universe and
# the Picker-enabled subset are persisted separately for this reason.
aux_cmds = AuxiliaryScopeCmds()
original_cmds = runner.cmds
original_marker_renderable_shapes = runner._marker_renderable_shapes
try:
    runner.cmds = aux_cmds
    runner._marker_renderable_shapes = lambda shapes: sorted(set(shapes))
    aux_job = {
        "_auxiliary_authored_visible_shapes": [
            "|Visible|meshShape",
            "|Visible|surfaceShape",
            "|EyeOff|meshShape",
            "|Rig|aim_CTRLShape",
            "|Rig|pivot_LOCShape",
        ],
        "_auxiliary_fallback_shapes": [
            "|Visible|meshShape",
            "|Visible|surfaceShape",
        ],
    }
    aux_report = runner._prepare_unassigned_auxiliary_scope(
        aux_job,
        ["|EyeOff"],
        {},
    )
    defensive_depth_scope = runner._all_depth_renderable_shapes({
        "_render_scope_shapes": [
            "|Visible|meshShape",
            "|Visible|surfaceShape",
            "|Rig|aim_CTRLShape",
            "|Rig|pivot_LOCShape",
        ],
    })
    defensive_cutout_scope = runner._authored_cutout_scope_shapes({
        "_viewport_quality_scope_shapes": [
            "|Visible|meshShape",
            "|Visible|surfaceShape",
            "|Rig|aim_CTRLShape",
            "|Rig|pivot_LOCShape",
        ],
    })
finally:
    runner.cmds = original_cmds
    runner._marker_renderable_shapes = original_marker_renderable_shapes

assert aux_job["_render_scope_shapes"] == [
    "|Visible|meshShape",
    "|Visible|surfaceShape",
]
assert aux_report["supported_surface_types"] == ["mesh", "nurbsSurface"]
assert aux_report["allowed_shape_path_count"] == 2
assert aux_report["excluded_shape_path_count"] == 3
assert aux_report["unsupported_control_shape_path_count"] == 2
assert aux_report["unsupported_control_shape_type_counts"] == {
    "locator": 1,
    "nurbsCurve": 1,
}
assert aux_report["unsupported_control_shape_paths"] == [
    "|Rig|aim_CTRLShape",
    "|Rig|pivot_LOCShape",
]
assert aux_cmds.layers["HMB_Picker_Aux_Excluded"] == [
    "|EyeOff|meshShape",
    "|Rig|aim_CTRLShape",
    "|Rig|pivot_LOCShape",
]
assert defensive_depth_scope == [
    "|Visible|meshShape",
    "|Visible|surfaceShape",
]
assert defensive_cutout_scope == defensive_depth_scope


# Motion visibility work is cached only inside one evaluated frame.  A fresh
# cache must re-evaluate animated DAG/layer state on the next frame.
motion_visibility_calls = []
original_motion_path_visible = runner._motion_path_visible
try:
    runner._motion_path_visible = lambda path: (
        motion_visibility_calls.append(path) or path != "|Hidden"
    )
    first_frame_cache = {}
    first_frame_performance = {}
    assert runner._motion_cached_path_visible(
        "|Visible",
        first_frame_cache,
        first_frame_performance,
    ) is True
    assert runner._motion_cached_path_visible(
        "|Visible",
        first_frame_cache,
        first_frame_performance,
    ) is True
    assert motion_visibility_calls == ["|Visible"]
    assert first_frame_performance == {
        "path_visibility_cache_miss_count": 1,
        "path_visibility_cache_hit_count": 1,
    }
    assert runner._motion_cached_path_visible(
        "|Visible",
        {},
    ) is True
    assert motion_visibility_calls == ["|Visible", "|Visible"]
finally:
    runner._motion_path_visible = original_motion_path_visible


# Root visibility and shape `any()` retain the old boolean result while
# genuinely short-circuiting later Maya visibility queries.
target_visibility_calls = []


def hidden_root_visibility(path):
    target_visibility_calls.append(path)
    return False


assert runner._motion_target_visible(
    {
        "source_root": "|HiddenRoot",
        "shapes": ["|HiddenRoot|shapeA", "|HiddenRoot|shapeB"],
    },
    hidden_root_visibility,
) is False
assert target_visibility_calls == ["|HiddenRoot"]

target_visibility_calls = []


def first_shape_visibility(path):
    target_visibility_calls.append(path)
    return path in {"|VisibleRoot", "|VisibleRoot|shapeA"}


target_performance = {}
assert runner._motion_target_visible(
    {
        "source_root": "|VisibleRoot",
        "shapes": ["|VisibleRoot|shapeA", "|VisibleRoot|shapeB"],
    },
    first_shape_visibility,
    target_performance,
) is True
assert target_visibility_calls == ["|VisibleRoot", "|VisibleRoot|shapeA"]
assert target_performance == {
    "target_shape_visibility_check_count": 1,
    "target_shape_any_short_circuit_count": 1,
}


# Face occluders are filtered once per frame before any landmark ray.  The ray
# helper consumes that visible-only list and must not re-query DAG visibility.
occluder_visibility_calls = []
occluder_performance = {}
visible_occluders = runner._motion_face_visible_occlusion_meshes(
    [
        {"shape": "|FaceA|shape"},
        {"shape": "|FaceB|shape"},
        {"shape": "|HiddenFace|shape"},
    ],
    lambda path: (
        occluder_visibility_calls.append(path)
        or path != "|HiddenFace|shape"
    ),
    occluder_performance,
)
assert [item["shape"] for item in visible_occluders] == [
    "|FaceA|shape",
    "|FaceB|shape",
]
assert occluder_visibility_calls == [
    "|FaceA|shape",
    "|FaceB|shape",
    "|HiddenFace|shape",
]
assert occluder_performance == {
    "face_occluder_candidate_mesh_sample_count": 3,
    "face_occluder_visible_mesh_sample_count": 2,
}


class MotionRayOM:
    class MSpace:
        kWorld = 0

    @staticmethod
    def MFloatPoint(*values):
        return values

    @staticmethod
    def MFloatVector(*values):
        return values


class MotionRayMesh:
    def __init__(self):
        self.calls = 0

    def closestIntersection(self, *_args):
        self.calls += 1
        return (object(), 10.0)


ray_mesh = MotionRayMesh()
original_motion_path_visible = runner._motion_path_visible
try:
    runner._motion_path_visible = lambda _path: (_ for _ in ()).throw(
        AssertionError("A prefiltered face ray must not query DAG visibility.")
    )
    ray_performance = {}
    ray_hit = runner._motion_face_closest_ray_hit(
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 10.0],
        [{
            "shape": "|FaceA|shape",
            "target_index": 1,
            "om": MotionRayOM,
            "mesh_function": ray_mesh,
        }],
        1.0,
        performance=ray_performance,
    )
finally:
    runner._motion_path_visible = original_motion_path_visible
assert ray_hit["shape"] == "|FaceA|shape"
assert ray_mesh.calls == 1
assert ray_performance["face_mesh_intersection_test_count"] == 1


# First-hit tolerance is bounded to 0.5% of the face diagonal.  A hit exactly
# on that boundary is accepted; a farther hit is treated as occlusion.
original_face_closest_ray_hit = runner._motion_face_closest_ray_hit
tolerance_extra_distances = []
tolerance_hit_distance = [9.5]


def tolerance_hit(
    _origin,
    _point,
    _records,
    maximum_extra_distance,
    performance=None,
):
    tolerance_extra_distances.append(float(maximum_extra_distance))
    return {
        "distance": tolerance_hit_distance[0],
        "point_distance": 10.0,
        "shape": "|FaceA|shape",
        "target_index": 1,
    }


def tolerance_sample():
    return {
        "front_facing": True,
        "in_frame": True,
        "_world_point": [0.0, 0.0, 10.0],
        "_surface_shape": "|FaceA|shape",
    }


try:
    runner._motion_face_closest_ray_hit = tolerance_hit
    boundary_sample = runner._motion_face_apply_ray_visibility(
        tolerance_sample(),
        {"camera_origin": [0.0, 0.0, 0.0]},
        1,
        [{"shape": "|FaceA|shape"}],
        100.0,
    )
    tolerance_hit_distance[0] = 9.4999
    outside_sample = runner._motion_face_apply_ray_visibility(
        tolerance_sample(),
        {"camera_origin": [0.0, 0.0, 0.0]},
        1,
        [{"shape": "|FaceA|shape"}],
        100.0,
    )
finally:
    runner._motion_face_closest_ray_hit = original_face_closest_ray_hit
assert tolerance_extra_distances == [0.5, 0.5]
assert boundary_sample["visible"] is True
assert outside_sample["visible"] is False


# The authored current face contract is exactly ten semantic slots.  A complete
# set is retained unchanged, while completion policy makes no topology symmetry
# claim and does not need to mutate Maya state.
complete_face_slots = [
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
complete_face_candidates = [
    {
        "region": region,
        "side": side,
        "vertex_index": index,
    }
    for index, (region, side) in enumerate(complete_face_slots)
]
original_face_object_points = runner._motion_face_object_points
try:
    runner._motion_face_object_points = lambda _runtime: [
        [float(index % 3), float(index // 3), 0.1 * float(index % 2)]
        for index in range(10)
    ]
    completed_face, completion_audit = (
        runner._motion_face_complete_bilateral_and_jaw(
            complete_face_candidates,
            {"shape": "|Hero|faceShape"},
            [],
        )
    )
finally:
    runner._motion_face_object_points = original_face_object_points
assert {
    (item["region"], item["side"])
    for item in completed_face
} == set(complete_face_slots)
assert len(completed_face) == 10
assert completion_audit["mirrored_count"] == 0
assert completion_audit["inferred_jaw_count"] == 0
assert completion_audit["mirror_policy"] == (
    "bounded_two_pair_bilateral_offset_no_topology_symmetry_claim"
)


# Projection/front-facing evaluation happens before rays.  Two arbitrary
# landmarks are insufficient: both endpoints must belong to one declared edge.
base_face_target = {
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


def projected_face_sample(item, _projection):
    return dict(item["sample"])


def make_face_sample(index, front=True, in_frame=True):
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
        "_surface_shape": "|FaceA|shape",
    }


face_originals = {
    "_motion_face_numeric_value": runner._motion_face_numeric_value,
    "_motion_face_landmark_projection_sample": (
        runner._motion_face_landmark_projection_sample
    ),
    "_motion_face_closest_ray_hit": runner._motion_face_closest_ray_hit,
}
try:
    runner._motion_face_numeric_value = lambda _plug: 0.5
    runner._motion_face_landmark_projection_sample = projected_face_sample
    no_ray_target = dict(base_face_target)
    no_ray_target["face_landmark_runtime"] = [
        {"sample": make_face_sample(0, front=True)},
        {"sample": make_face_sample(1, front=False)},
        {"sample": make_face_sample(2, front=True)},
    ]
    runner._motion_face_closest_ray_hit = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(
            AssertionError("The frame-level front gate must skip every ray.")
        )
    )
    no_ray_performance = {}
    no_ray_frame = runner._motion_face_frame_sample(
        no_ray_target,
        {"camera_origin": [0.0, 0.0, 0.0]},
        [],
        100,
        100,
        performance=no_ray_performance,
    )
    assert no_ray_frame["rasterized"] is False
    assert no_ray_frame["visibility_opportunity"] is False
    assert no_ray_frame["visibility_reason"] == (
        "back_facing_edge_on_or_out_of_frame"
    )
    assert no_ray_frame["channel_values"] == [0.5]
    assert no_ray_frame["driver_values"] == [0.5]
    assert no_ray_performance["face_landmark_projection_sample_count"] == 3
    assert no_ray_performance["face_landmark_front_in_frame_sample_count"] == 2
    assert no_ray_performance["face_frame_ray_gate_short_circuit_count"] == 1
    assert no_ray_performance["face_landmark_ray_skip_count"] == 2
    assert no_ray_performance.get("face_landmark_ray_test_count", 0) == 0

    visible_target = dict(base_face_target)
    visible_target["face_landmark_runtime"] = [
        {"sample": make_face_sample(0)},
        {"sample": make_face_sample(1)},
        {"sample": make_face_sample(2, front=False)},
    ]
    visible_ray_calls = []

    def visible_ray_hit(_origin, point, records, _extra, performance=None):
        visible_ray_calls.append((list(point), len(records)))
        runner._motion_perf_increment(
            performance,
            "face_mesh_intersection_test_count",
            len(records),
        )
        return {
            "distance": 10.0,
            "shape": "|FaceA|shape",
            "target_index": 1,
            "point_distance": 10.0,
        }

    runner._motion_face_closest_ray_hit = visible_ray_hit
    visible_performance = {}
    visible_frame = runner._motion_face_frame_sample(
        visible_target,
        {"camera_origin": [0.0, 0.0, 0.0]},
        [{"shape": "|FaceA|shape"}],
        100,
        100,
        performance=visible_performance,
    )
finally:
    for name, value in face_originals.items():
        setattr(runner, name, value)

assert len(visible_ray_calls) == 2
assert visible_frame["rasterized"] is True
assert visible_frame["visibility_opportunity"] is True
assert visible_frame["visibility_reason"] == (
    "front_facing_camera_ray_visible_face_surface"
)
assert len(visible_frame["guide_points"]) == 2
assert visible_frame["guide_segments"] == base_face_target["face_edges"][:1]
assert visible_performance["face_landmark_ray_test_count"] == 2
assert visible_performance["face_mesh_intersection_test_count"] == 2

assert '"motion_performance_telemetry"' in runner_source
assert '"hmb-motion-performance-counters"' in runner_source

print("HMB Maya marker-instance, camera-depth, and per-frame progress regression: PASS")
