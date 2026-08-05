from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"


class FakeCutoutCmds(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("maya.cmds")
        self.shapes = [
            "|Actor|MouthShape",
            "|Actor|OpacityShape",
            "|Actor|GlassShape",
            "|Actor|BodyShape",
        ]
        self.node_types: dict[str, str] = {
            "|Actor": "transform",
            **{shape: "mesh" for shape in self.shapes},
            "MouthSG": "shadingEngine",
            "OpacitySG": "shadingEngine",
            "GlassSG": "shadingEngine",
            "BodySG": "shadingEngine",
            "MouthMat": "lambert",
            "OpacityMat": "standardSurface",
            "GlassMat": "lambert",
            "BodyMat": "lambert",
            "MouthFile": "file",
            "OpacityFile": "file",
        }
        self.shape_groups = {
            "|Actor|MouthShape": ["MouthSG"],
            "|Actor|OpacityShape": ["OpacitySG"],
            "|Actor|GlassShape": ["GlassSG"],
            "|Actor|BodyShape": ["BodySG"],
        }
        self.connections: dict[str, str] = {
            "MouthSG.surfaceShader": "MouthMat.outColor",
            "OpacitySG.surfaceShader": "OpacityMat.outColor",
            "GlassSG.surfaceShader": "GlassMat.outColor",
            "BodySG.surfaceShader": "BodyMat.outColor",
            "MouthMat.transparency": "MouthFile.outTransparency",
            "OpacityMat.opacity": "OpacityFile.outAlpha",
        }
        self.values: dict[str, Any] = {
            "MouthMat.transparency": [(0.0, 0.0, 0.0)],
            "OpacityMat.opacity": [(1.0, 1.0, 1.0)],
            # Static legacy transparency is glass, not a texture-alpha card.
            "GlassMat.transparency": [(0.5, 0.5, 0.5)],
            "BodyMat.transparency": [(0.0, 0.0, 0.0)],
        }
        self.attributes = {
            "MouthMat.outTransparency",
            "OpacityMat.outTransparency",
            "GlassMat.outTransparency",
            "BodyMat.outTransparency",
            "MouthFile.outTransparency",
            "OpacityFile.outAlpha",
            *self.values,
        }
        self.assignments: list[tuple[str, str]] = []
        self.smooth_modes = dict((shape, 0) for shape in self.shapes)
        self.smooth_edits: list[str] = []

    def ls(self, *items, **kwargs):
        if items:
            return [str(items[0])]
        if kwargs.get("type") == "mesh":
            return list(self.shapes)
        if kwargs.get("type") in {"nurbsSurface", "displayLayer"}:
            return []
        return list(self.shapes)

    def nodeType(self, node: str):
        return self.node_types.get(node, "unknown")

    def getClassification(self, node_type: str):
        if node_type == "file":
            return ["texture/2d:drawdb/shader/texture/2d/file"]
        return []

    def objExists(self, name: str):
        if name in self.node_types or name in self.attributes:
            return True
        if "." in name:
            node, attribute = name.split(".", 1)
            if node not in self.node_types:
                return False
            node_type = self.node_types[node]
            if node_type == "shadingEngine" and attribute == "surfaceShader":
                return True
            if node_type == "lambert" and attribute in {
                "outColor",
                "color",
                "transparency",
                "diffuse",
                "translucence",
                "translucenceDepth",
                "ambientColor",
                "incandescence",
            }:
                return True
            if node_type == "surfaceShader" and attribute in {
                "outColor",
                "outTransparency",
                "outGlowColor",
            }:
                return True
        return False

    def listSets(self, **kwargs):
        if kwargs.get("type") == 1:
            return list(self.shape_groups.get(str(kwargs.get("object")), []))
        return []

    def listConnections(self, target: str, **kwargs):
        if kwargs.get("type") == "displayLayer":
            return []
        if kwargs.get("type") == "shadingEngine":
            return list(self.shape_groups.get(target, []))
        source = self.connections.get(target)
        if not source:
            return []
        return [source if kwargs.get("plugs") else source.split(".", 1)[0]]

    def getAttr(self, plug: str, **kwargs):
        if kwargs.get("settable"):
            return True
        if plug.endswith(".intermediateObject"):
            return False
        if plug in self.values:
            return self.values[plug]
        raise RuntimeError(f"Unknown fake attribute: {plug}")

    def setAttr(self, plug: str, *values, **_kwargs):
        self.attributes.add(plug)
        self.values[plug] = values[0] if len(values) == 1 else tuple(values)

    def shadingNode(self, node_type: str, **kwargs):
        requested = str(kwargs["name"])
        if requested.endswith("#"):
            base = requested[:-1]
            index = 1
            actual = f"{base}{index}"
            while actual in self.node_types:
                index += 1
                actual = f"{base}{index}"
        else:
            actual = requested
        self.node_types[actual] = node_type
        return actual

    def sets(self, *items, **kwargs):
        if kwargs.get("renderable") and kwargs.get("empty"):
            requested = str(kwargs["name"])
            if requested.endswith("#"):
                requested = requested[:-1] + "1"
            self.node_types[requested] = "shadingEngine"
            return requested
        if kwargs.get("edit") and kwargs.get("forceElement"):
            self.assignments.append((str(items[0]), str(kwargs["forceElement"])))
            return str(kwargs["forceElement"])
        return ""

    def connectAttr(self, source: str, target: str, **_kwargs):
        self.connections[target] = source

    def isConnected(self, source: str, target: str):
        return self.connections.get(target) == source

    def attributeQuery(self, attribute: str, node: str, **kwargs):
        if kwargs.get("exists") and attribute == "intermediateObject":
            return node in self.shapes
        return False

    def listRelatives(self, *_args, **_kwargs):
        return []

    def displayLevelOfDetail(self, **kwargs):
        if kwargs.get("query"):
            return False
        return None

    def displaySmoothness(
        self,
        shape: str,
        query: bool = False,
        polygonObject=None,
        **_kwargs,
    ):
        if query and polygonObject is True:
            return [self.smooth_modes[shape]]
        if polygonObject is not None:
            self.smooth_modes[shape] = int(polygonObject)
            self.smooth_edits.append(shape)
        return None

    def refresh(self, **_kwargs):
        return None


fake_cmds = FakeCutoutCmds()
maya_module = types.ModuleType("maya")
maya_module.cmds = fake_cmds
sys.modules["maya"] = maya_module
sys.modules["maya.cmds"] = fake_cmds

spec = importlib.util.spec_from_file_location(
    "HMB_Maya_Background_Preview_Cutout_Regression",
    RUNNER_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load Maya runner: {RUNNER_PATH}")
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


job: dict[str, Any] = {}
snapshot = runner._ensure_authored_cutout_snapshot(job, fake_cmds.shapes)
mouth = snapshot["|Actor|MouthShape"]
opacity = snapshot["|Actor|OpacityShape"]
glass = snapshot["|Actor|GlassShape"]
body = snapshot["|Actor|BodyShape"]
assert mouth["alpha_driven"] is True
assert mouth["source_plug"] == "MouthMat.outTransparency"
assert mouth["evidence_kind"] == "spatial_texture_alpha"
assert opacity["alpha_driven"] is True
assert opacity["source_plug"] == "OpacityMat.outTransparency"
assert opacity["evidence_kind"] == "explicit_opacity"
assert glass["alpha_driven"] is False
assert body["alpha_driven"] is False
assert job["_authored_cutout_report"] == {
    "policy": "preserve_authored_material_out_transparency_v1",
    "captured_shape_path_count": 4,
    "alpha_driven_shape_path_count": 2,
    "source_plug_count": 2,
    "verified_shape_path_count": 0,
    "ambiguous_shape_path_count": 0,
    "unsupported_shape_path_count": 0,
}

# Marker assignment keeps the shared SG fast path for solid geometry and glass,
# while each distinct authored alpha output gets a temporary Lambert variant.
runner.MARKER_COLORS = {"Red": (1.0, 0.0, 0.0)}
runner.MARKER_PATTERNS = {}
runner.CHARACTER_MARKERS = {"Red"}
runner.BACKGROUND_MARKERS = set()
runner._descendant_shapes = lambda _root: list(fake_cmds.shapes)
marker_job = {
    **job,
    "_render_scope_binding_shapes": {"|Actor": list(fake_cmds.shapes)},
}
source_connections_before = {
    "MouthMat.transparency": fake_cmds.connections["MouthMat.transparency"],
    "OpacityMat.opacity": fake_cmds.connections["OpacityMat.opacity"],
}
assert runner._apply_marker_shaders(
    [{"color": "Red", "subject_root": "|Actor"}],
    marker_job,
) == []
assigned = dict(fake_cmds.assignments)
assert assigned["|Actor|BodyShape"] == assigned["|Actor|GlassShape"]
assert "Cutout" not in assigned["|Actor|BodyShape"]
assert "Cutout" in assigned["|Actor|MouthShape"]
assert "Cutout" in assigned["|Actor|OpacityShape"]
assert assigned["|Actor|MouthShape"] != assigned["|Actor|OpacityShape"]
assert marker_job["_marker_cutout_transparency"]["verified_shape_path_count"] == 2
assert source_connections_before == {
    "MouthMat.transparency": fake_cmds.connections["MouthMat.transparency"],
    "OpacityMat.opacity": fake_cmds.connections["OpacityMat.opacity"],
}

# Depth variants are cached per (grayscale bucket, source alpha plug), connect
# material.outTransparency, and never modify the source material inputs.
depth_cache: dict[tuple[int, str], str] = {}
mouth_depth = runner._depth_cutout_surface_group(
    128,
    "MouthMat.outTransparency",
    depth_cache,
)
assert mouth_depth == runner._depth_cutout_surface_group(
    128,
    "MouthMat.outTransparency",
    depth_cache,
)
opacity_depth = runner._depth_cutout_surface_group(
    128,
    "OpacityMat.outTransparency",
    depth_cache,
)
assert mouth_depth != opacity_depth
for group, source in (
    (mouth_depth, "MouthMat.outTransparency"),
    (opacity_depth, "OpacityMat.outTransparency"),
):
    shader = fake_cmds.connections[group + ".surfaceShader"].split(".", 1)[0]
    assert fake_cmds.connections[shader + ".outTransparency"] == source

# Smooth Preview 3 is skipped only for the two cutout records.  Static glass
# transparency remains on the ordinary solid-geometry quality path.
runner._unresolved_proxy_plugins = lambda: []
runner._set_attr_with_restore = lambda *_args, **_kwargs: False
runner._emit_console = lambda *_args, **_kwargs: None
smooth_job = {
    "_viewport_quality_scope_shapes": list(fake_cmds.shapes),
    "_authored_cutout_snapshot": dict(snapshot),
    "_authored_cutout_report": dict(job["_authored_cutout_report"]),
}
_restore, smooth_report = runner._apply_full_smooth_viewport(smooth_job)
assert smooth_report["alpha_cutout_smooth_preserved_count"] == 2
assert smooth_report["smooth_mesh_shape_count"] == 2
assert set(fake_cmds.smooth_edits) == {
    "|Actor|GlassShape",
    "|Actor|BodyShape",
}
assert fake_cmds.smooth_modes["|Actor|MouthShape"] == 0
assert fake_cmds.smooth_modes["|Actor|OpacityShape"] == 0
assert fake_cmds.smooth_modes["|Actor|GlassShape"] == 3
assert fake_cmds.smooth_modes["|Actor|BodyShape"] == 3


source = RUNNER_PATH.read_text(encoding="utf-8")
assert 'range_report["cutout_transparency"]' in source
assert '"policy": CUTOUT_TRANSPARENCY_POLICY' in source
assert "_depth_cutout_surface_group(" in source
assert "_assign_marker_group_preserving_cutouts(" in source
assert "alpha_cutout_smooth_preserved_count" in source

print(
    "HMB authored cutout transparency snapshot, Marker/Depth variants, "
    "glass exclusion, and Smooth Preview preservation regression: PASS"
)
