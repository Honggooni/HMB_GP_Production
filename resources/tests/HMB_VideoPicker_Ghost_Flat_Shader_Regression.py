"""Maya-free Ghost shader isolation, exact palette and authored-alpha regression."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch


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
assert len(runner.CHARACTER_MARKERS) == 10
assert len(runner.BACKGROUND_MARKERS) == 9
assert len(runner.MARKER_OPTIONS) == 19
assert runner.MARKER_COLORS["Cyan"] == (0.0, 217 / 255, 217 / 255)
assert runner.MARKER_COLORS["Lavender"] == (184 / 255, 166 / 255, 217 / 255)
assert runner.MARKER_COLORS["Teal"] == (0, 128 / 255, 128 / 255)
assert runner.MARKER_COLORS["Brown"] == (139 / 255, 69 / 255, 19 / 255)
assert runner.MARKER_COLORS["Olive"] == (128 / 255, 128 / 255, 0)
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
for color in ("Cyan", "Lavender", "Teal", "Brown", "Olive"):
    rgb8 = tuple(round(channel * 255) for channel in runner.MARKER_COLORS[color])
    assert rgb8 not in pattern_ids, "New solid marker aliases a screen-space Pattern ID"


class ShaderCommands:
    def __init__(self):
        self.nodes = {"authoredAlpha": "file"}
        self.values = {}
        self.connections = {}

    def ls(self, *args, **kwargs):
        assert not args and kwargs == {"type": "objectSet", "long": True}
        return [name for name, kind in self.nodes.items() if kind == "objectSet"]

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
    {"color": "Olive", "asset_id": "GhostOlive", "subject_root": "|GhostOlive"},
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
for version, historical_size in ((4, 7), (5, 8)):
    legacy_path = Path(__file__).with_name("fixtures") / f"marker_catalog_v{version}.json"
    legacy_catalog = json.loads(legacy_path.read_text(encoding="utf-8"))
    runner._load_marker_catalog({"marker_catalog_path": str(legacy_path), "marker_catalog_version": version})
    assert len(runner.MARKER_OPTIONS) == historical_size * 2
    assert len(runner.CHARACTER_MARKERS) == historical_size
    assert len(runner.BACKGROUND_MARKERS) == historical_size
    assert {"Teal", "Brown", "Olive"}.isdisjoint(runner.MARKER_OPTIONS)
    assert ("Cyan" in runner.MARKER_OPTIONS) == (version == 5)
    assert ("Lavender" in runner.MARKER_OPTIONS) == (version == 5)
    assert runner.MARKER_PATTERN_IDS == {
        row["name"]: tuple(row["screen_space_id_rgb"])
        for row in legacy_catalog["background"] if row["kind"] == "pattern"
    }
    for row in legacy_catalog["character"] + legacy_catalog["background"]:
        if row["kind"] == "solid":
            assert runner.MARKER_COLORS[row["name"]] == tuple(row["rgb"])

# Older retained engines wrote the then-current version into the job but used
# the mutable installed palette path. Exercise those actual version pairs.
paths = {version: Path(__file__).with_name('fixtures') / f'marker_catalog_v{version}.json'
         for version in (4, 5)}
paths[6] = catalog_path
for expected, installed in ((4, 5), (4, 6), (5, 6)):
    original = json.loads(paths[expected].read_text(encoding='utf-8'))
    active = runner._load_marker_catalog({'marker_catalog_version': expected, 'marker_catalog_path': str(paths[installed])})
    for group in ('character', 'background'):
        definitions = {row['name']: row for row in active[group]}
        for row in original[group]:
            assert definitions[row['name']] == row
            if row['kind'] == 'solid':
                assert runner.MARKER_COLORS[row['name']] == tuple(row['rgb'])
            else:
                assert runner.MARKER_PATTERNS[row['name']] == row['pattern']
                assert runner.MARKER_PATTERN_IDS[row['name']] == tuple(row['screen_space_id_rgb'])
    assert active['version'] == installed
    if installed == 6:
        assert {'Teal','Brown','Olive'}.issubset(runner.MARKER_COLORS)

with TemporaryDirectory() as scratch:
    tested = TestCase()
    for expected, installed in ((6, 5), (5, 4), (7, 6)):
        with tested.assertRaisesRegex(RuntimeError, f'expected {expected}, got {installed}'):
            runner._load_marker_catalog({'marker_catalog_version': expected, 'marker_catalog_path': str(paths[installed])})
    for group, name, field, replacement in (
        ('character', 'Red', 'rgb', [0.5, 0.1, 0.0]),
        ('background', 'Sky Grid', 'screen_space_id_rgb', [0, 254, 255]),
    ):
        changed = copy.deepcopy(catalog)
        next(row for row in changed[group] if row['name'] == name)[field] = replacement
        changed_path = Path(scratch) / 'changed.json'
        changed_path.write_text(json.dumps(changed), encoding='utf-8')
        with tested.assertRaisesRegex(RuntimeError, 'expected 5, got 6'):
            runner._load_marker_catalog({'marker_catalog_version': 5, 'marker_catalog_path': str(changed_path)})

    pinned_job = {'marker_catalog_version': 5, 'marker_catalog_snapshot': json.loads(paths[5].read_text(encoding='utf-8'))}
    with patch.object(runner, '_read_json', side_effect=AssertionError('Pinned jobs must not open the live palette')):
        for disk_path in (str(changed_path), str(Path(scratch) / 'missing.json')):
            loaded = runner._load_marker_catalog(dict(pinned_job, marker_catalog_path=disk_path))
            assert loaded['version'] == 5 and 'Teal' not in runner.MARKER_COLORS
        for invalid in (None, [], {}, dict(pinned_job['marker_catalog_snapshot'], version=6),
                        dict(pinned_job['marker_catalog_snapshot'], version=5.1)):
            with tested.assertRaises(RuntimeError):
                runner._load_marker_catalog(dict(pinned_job, marker_catalog_snapshot=invalid, marker_catalog_path=str(paths[5])))
        invalid_rgb = copy.deepcopy(pinned_job)
        invalid_rgb['marker_catalog_snapshot']['character'][0]['rgb'] = [1, 0, 1.5]
        with tested.assertRaisesRegex(RuntimeError, 'invalid RGB'):
            runner._load_marker_catalog(invalid_rgb)

print("HMB VideoPicker Ghost flat shader: PASS (exact colors and shader assignment, archived and mixed v4/v5/v6 jobs, changed RGB/IDs and downgrades rejected)")
