"""Maya-free Ghost shader isolation, exact palette and authored-alpha regression."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
maya = types.ModuleType("maya")
maya.cmds = types.ModuleType("maya.cmds")
sys.modules.setdefault("maya", maya)
sys.modules.setdefault("maya.cmds", maya.cmds)
spec = importlib.util.spec_from_file_location("hmb_ghost_flat_shader_regression", RUNNER)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
catalog_path = ROOT / "resources" / "picker" / "HMB_Marker_Catalog.json"
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
runner._load_marker_catalog({
    "marker_catalog_path": str(catalog_path),
    "marker_catalog_version": catalog["version"],
})
assert len(runner.CHARACTER_MARKERS) == 8
assert len(runner.BACKGROUND_MARKERS) == 8
assert len(runner.MARKER_OPTIONS) == 16
assert runner.MARKER_COLORS["Cyan"] == (0.0, 217 / 255, 217 / 255)
assert runner.MARKER_COLORS["Lavender"] == (184 / 255, 166 / 255, 217 / 255)
solid_rgb8 = {
    name: tuple(round(channel * 255) for channel in rgb)
    for name, rgb in runner.MARKER_COLORS.items()
}
assert len(set(solid_rgb8.values())) == len(solid_rgb8), "Actor/Ghost solid colors overlap"
actor_rgb8 = {solid_rgb8[name] for name in runner.CHARACTER_MARKERS}
ghost_rgb8 = {solid_rgb8[name] for name in runner.BACKGROUND_MARKERS if name in solid_rgb8}
assert actor_rgb8.isdisjoint(ghost_rgb8), "Actor/Ghost categories share an RGB color"
pattern_ids = set(runner.MARKER_PATTERN_IDS.values())
assert len(pattern_ids) == 4
assert set(solid_rgb8.values()).isdisjoint(pattern_ids), "Solid marker aliases a reserved Pattern ID"
for color in ("Cyan", "Lavender"):
    rgb8 = tuple(round(channel * 255) for channel in runner.MARKER_COLORS[color])
    assert rgb8 not in pattern_ids, "New solid marker aliases a screen-space Pattern ID"


class ShaderCommands:
    def __init__(self):
        self.nodes = {"authoredAlpha": "file"}
        self.values = {}
        self.connections = {}

    def objExists(self, name):
        return name.split(".", 1)[0] in self.nodes

    def shadingNode(self, node_type, *, asShader, name):
        assert asShader is True
        assert node_type in {"lambert", "surfaceShader"}
        if name.endswith("#"):
            prefix = name[:-1]
            suffix = 1
            while prefix + str(suffix) in self.nodes:
                suffix += 1
            name = prefix + str(suffix)
        assert name not in self.nodes
        self.nodes[name] = node_type
        return name

    def setAttr(self, plug, *values, **kwargs):
        assert self.objExists(plug)
        assert kwargs.get("type") in {None, "double3"}
        self.values[plug] = values if len(values) > 1 else values[0]

    def sets(self, *, renderable, noSurfaceShader, empty, name):
        assert renderable and noSurfaceShader and empty
        if name.endswith("#"):
            name = name[:-1] + str(len(self.nodes))
        assert name not in self.nodes
        self.nodes[name] = "shadingEngine"
        return name

    def isConnected(self, source, destination):
        return self.connections.get(destination) == source

    def connectAttr(self, source, destination, *, force):
        assert force is True
        assert self.objExists(source) and self.objExists(destination)
        self.connections[destination] = source


fake = ShaderCommands()
runner.cmds = fake
assignments = {}
alpha_shapes = {"|GhostMint|shape", "|GhostLavender|shape"}
runner._descendant_shapes = lambda root: [root + "|shape"]
runner._marker_renderable_shapes = lambda shapes: [item for item in shapes if "Hidden" not in item]
runner._long_names = lambda names: list(names)
runner._ensure_authored_cutout_snapshot = lambda _job, shapes: {
    shape: {
        "alpha_driven": shape in alpha_shapes,
        "source_plug": "authoredAlpha.outTransparency" if shape in alpha_shapes else "",
    }
    for shape in shapes
}


def assign(shapes, group):
    for shape in shapes:
        assignments[shape] = group
    return []


runner._assign = assign
actors = [
    {"color": name, "asset_id": "Actor" + name, "subject_root": "|Actor" + name}
    for name in sorted(runner.CHARACTER_MARKERS)
]
ghosts = [
    {"color": "Sky Blue", "asset_id": "GhostSky", "subject_root": "|GhostSky"},
    {"color": "Mint", "asset_id": "GhostMint", "subject_root": "|GhostMint"},
    {"color": "Beige", "asset_id": "GhostBeige", "subject_root": "|GhostBeige"},
    {"color": "Lavender", "asset_id": "GhostLavender", "subject_root": "|GhostLavender"},
    {"color": "Sky Blue", "asset_id": "GhostRepeat", "subject_root": "|GhostRepeat"},
]
hidden = {"color": "Mint", "asset_id": "HiddenGhost", "subject_root": "|HiddenGhost"}
job = {"result_path": str(ROOT / "reports" / "unused-ghost-result.json")}
warnings = runner._apply_marker_shaders(actors + ghosts + [hidden], job)
assert len(warnings) == 1 and "authored-hidden" in warnings[0]
assert "|HiddenGhost|shape" not in assignments
assert job["_marker_cutout_transparency"]["verified_shape_path_count"] == 2

for record in actors + ghosts:
    shape = record["subject_root"] + "|shape"
    group = assignments[shape]
    shader = fake.connections[group + ".surfaceShader"].rsplit(".", 1)[0]
    rgb = runner.MARKER_COLORS[record["color"]]
    if record in ghosts:
        assert fake.nodes[shader] == "surfaceShader"
        assert "_Ghost" in shader
        assert fake.values[shader + ".outColor"] == rgb
        assert fake.values[shader + ".outGlowColor"] == (0.0, 0.0, 0.0)
        assert shader + ".diffuse" not in fake.values
        assert shader + ".specularColor" not in fake.values
        if shape in alpha_shapes:
            assert fake.connections[shader + ".outTransparency"] == "authoredAlpha.outTransparency"
        else:
            assert fake.values[shader + ".outTransparency"] == (0.0, 0.0, 0.0)
    else:
        assert fake.nodes[shader] == "lambert"
        assert fake.values[shader + ".color"] == rgb
        assert fake.values[shader + ".diffuse"] == 0.55
        assert fake.values[shader + ".ambientColor"] == (0.0, 0.0, 0.0)
        assert fake.values[shader + ".incandescence"] == tuple(channel * 0.25 for channel in rgb)

assert assignments["|GhostSky|shape"] == assignments["|GhostRepeat|shape"]
actor_values = {plug: value for plug, value in fake.values.items() if "_Lambert." in plug}
runner._apply_marker_shaders([
    {"color": "Beige", "asset_id": "ActorRed", "subject_root": "|ActorRed"},
], copy.deepcopy(job))
assert {plug: value for plug, value in fake.values.items() if "_Lambert." in plug} == actor_values
assert "_Ghost_SurfaceShader" in assignments["|ActorRed|shape"]

payload = runner._marker_payload(actors + ghosts)
for record in payload[:len(actors)]:
    assert record["shader_model"] == "lambert"
    assert record["visual_profile"] == "color_stable_lambert_profile"
for record in payload[len(actors):]:
    assert record["shader_model"] == "surfaceShader"
    assert record["visual_profile"] == "ghost_flat_unlit_palette_v1"
    assert record["shading_profile"]["palette_rgb"] == list(runner.MARKER_COLORS[record["color"]])
    assert record["shading_profile"]["lighting_response"] == "unlit_palette"
    assert record["shading_profile"]["specular"] is False
    assert record["shading_profile"]["receives_shadows"] is False

# Legacy catalogs embedded in existing jobs retain their original RGB/shaders.
legacy_catalog = copy.deepcopy(catalog)
legacy_catalog["version"] = 4
legacy_catalog["character"] = [row for row in catalog["character"] if row["name"] != "Cyan"]
legacy_catalog["background"] = [row for row in catalog["background"] if row["name"] != "Lavender"]
with tempfile.TemporaryDirectory(prefix="hmb-maya-legacy-palette-") as directory:
    legacy_path = Path(directory) / "catalog.json"
    legacy_path.write_text(json.dumps(legacy_catalog), encoding="utf-8")
    runner._load_marker_catalog({"marker_catalog_path": str(legacy_path), "marker_catalog_version": 4})
    assert len(runner.MARKER_OPTIONS) == 14
    assert len(runner.CHARACTER_MARKERS) == 7
    assert len(runner.BACKGROUND_MARKERS) == 7
    assert "Cyan" not in runner.MARKER_OPTIONS and "Lavender" not in runner.MARKER_OPTIONS
    assert runner.MARKER_PATTERN_IDS == {
        row["name"]: tuple(row["screen_space_id_rgb"])
        for row in legacy_catalog["background"] if row["kind"] == "pattern"
    }
    for row in legacy_catalog["character"] + legacy_catalog["background"]:
        if row["kind"] == "solid":
            assert runner.MARKER_COLORS[row["name"]] == tuple(row["rgb"])

print("HMB VideoPicker Ghost flat shader: PASS (4 exact Ghost colors, 8 Actors, legacy 14-choice jobs, Pattern ID separation, alpha cutout, repeat color, recolor and hidden-object isolation)")
