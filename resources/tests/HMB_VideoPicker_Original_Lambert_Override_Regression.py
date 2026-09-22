from __future__ import annotations

import ast
import copy
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
PICKER_PATH = ROOT / "HMBVideoPickerLibrary.py"
RUNNER_PATH = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"


def function_source(source: str, path: Path, name: str) -> str:
    tree = ast.parse(source, filename=str(path))
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1
    return ast.get_source_segment(source, matches[0]) or ""


picker_source = PICKER_PATH.read_text(encoding="utf-8")
original_source = function_source(
    picker_source,
    PICKER_PATH,
    "_render_original_preview_mode",
)
color_source = function_source(picker_source, PICKER_PATH, "_maya_mode")
read_source = function_source(picker_source, PICKER_PATH, "_read_scene_mode")
assert '"apply_original_lambert_override": True' in original_source
assert '"original_material_override_profile"' in original_source
assert "apply_original_lambert_override" not in color_source
assert "original_material_override_profile" not in color_source
assert "apply_original_lambert_override" not in read_source
assert "original_material_override_profile" not in read_source


class EmptyMayaCmds(types.ModuleType):
    pass


empty_cmds = EmptyMayaCmds("maya.cmds")
maya_module = types.ModuleType("maya")
maya_module.cmds = empty_cmds
sys.modules["maya"] = maya_module
sys.modules["maya.cmds"] = empty_cmds
spec = importlib.util.spec_from_file_location(
    "HMB_Maya_Background_Preview_Original_Lambert_Regression",
    RUNNER_PATH,
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


BASE_SCOPE_SHAPES = ["meshA", "meshB", "meshC", "meshD", "meshE"]


class FakeMaterialCmds(types.ModuleType):
    def __init__(
        self,
        fail_target: str = "",
        fail_restore_target: str = "",
        fail_viewport_attr: str = "",
        fail_color_source: str = "",
    ) -> None:
        super().__init__("maya.cmds")
        self.fail_target = fail_target
        self.fail_restore_target = fail_restore_target
        self.fail_viewport_attr = fail_viewport_attr
        self.fail_color_source = fail_color_source
        self.counter = 0
        self.node_types: dict[str, str] = {
            "meshA": "mesh",
            "meshB": "mesh",
            "meshC": "mesh",
            "meshD": "mesh",
            "meshE": "mesh",
            "RedMat": "RedshiftStandardMaterial",
            "BlueMat": "RedshiftMaterial",
            "SolidMat": "standardSurface",
            "AlphaMat": "RedshiftStandardMaterial",
            "ExistingLambert": "lambert",
            "redFile": "file",
            "blueFile": "file",
            "alphaColorFile": "file",
            "alphaMaskFile": "file",
            "redSG": "shadingEngine",
            "redSG2": "shadingEngine",
            "blueSG": "shadingEngine",
            "solidSG": "shadingEngine",
            "alphaSG": "shadingEngine",
            "existingSG": "shadingEngine",
        }
        self.members: dict[str, list[str]] = {
            "redSG": ["meshA.f[0:3]"],
            "redSG2": ["meshA.f[4:7]"],
            "blueSG": ["meshB"],
            "solidSG": ["meshC"],
            "alphaSG": ["meshD"],
            "existingSG": ["meshE"],
        }
        self.connections: dict[str, str] = {
            "redSG.surfaceShader": "RedMat.outColor",
            "redSG2.surfaceShader": "RedMat.outColor",
            "blueSG.surfaceShader": "BlueMat.outColor",
            "solidSG.surfaceShader": "SolidMat.outColor",
            "alphaSG.surfaceShader": "AlphaMat.outColor",
            "existingSG.surfaceShader": "ExistingLambert.outColor",
            "RedMat.base_color": "redFile.outColor",
            "BlueMat.diffuse_color": "blueFile.outColor",
            "AlphaMat.base_color": "alphaColorFile.outColor",
            "AlphaMat.opacity_color": "alphaMaskFile.outColor",
        }
        self.values: dict[str, Any] = {
            "SolidMat.baseColor": [(0.12, 0.34, 0.56)],
            "hardwareRenderingGlobals.lightingMode": 2,
            "hardwareRenderingGlobals.renderMode": 0,
        }
        self.attr_types: dict[str, str] = {}
        for plug in (
            "RedMat.base_color",
            "BlueMat.diffuse_color",
            "SolidMat.baseColor",
            "AlphaMat.base_color",
            "AlphaMat.opacity_color",
            "redFile.outColor",
            "blueFile.outColor",
            "alphaColorFile.outColor",
            "alphaMaskFile.outColor",
            "RedMat.outColor",
            "BlueMat.outColor",
            "SolidMat.outColor",
            "AlphaMat.outColor",
            "ExistingLambert.outColor",
        ):
            self.attr_types[plug] = "double3"
        for plug in (
            "hardwareRenderingGlobals.lightingMode",
            "hardwareRenderingGlobals.renderMode",
        ):
            self.attr_types[plug] = "long"
        self.deleted: list[str] = []

    def ls(self, *nodes, **kwargs):
        if nodes:
            return [str(node) for node in nodes]
        if kwargs.get("type") == "shadingEngine":
            return sorted(self.members)
        return []

    def sets(self, group, query=False, **_kwargs):
        assert query is True
        return list(self.members.get(group) or [])

    def listSets(self, type=0, object="", **_kwargs):
        assert type == 1
        target = str(object)
        result = []
        for group, members in self.members.items():
            for member in members:
                member_shape = str(member).split(".", 1)[0]
                if member_shape == target:
                    result.append(group)
                    break
        return sorted(result)

    def objExists(self, name):
        if name in self.node_types or name in self.attr_types:
            return True
        if name in self.connections or name in self.values:
            return True
        if "." in str(name):
            return False
        node = str(name).split(".", 1)[0]
        return node in self.node_types

    def nodeType(self, node):
        return self.node_types[node]

    def unknownNode(self, _node, query=False, **kwargs):
        assert query is True
        if kwargs.get("plugin"):
            return "redshift4maya"
        if kwargs.get("realClassName"):
            return "RedshiftColorCorrection"
        return ""

    def listConnections(
        self,
        target,
        source=False,
        destination=False,
        plugs=False,
        **_kwargs,
    ):
        assert source is True and destination is False and plugs is True
        if "." in str(target):
            value = self.connections.get(str(target))
            return [value] if value else []
        prefix = str(target) + "."
        return sorted(
            source_plug
            for destination_plug, source_plug in self.connections.items()
            if destination_plug.startswith(prefix)
        )

    def getAttr(self, plug, **kwargs):
        if kwargs.get("type"):
            return self.attr_types.get(plug, "double3")
        if plug in self.values:
            return self.values[plug]
        raise RuntimeError("No mocked value: {0}".format(plug))

    def listAttr(self, node, **_kwargs):
        prefix = str(node) + "."
        return sorted(
            plug[len(prefix):]
            for plug in self.attr_types
            if plug.startswith(prefix)
        )

    def setAttr(self, plug, *values, **kwargs):
        if plug == self.fail_viewport_attr:
            raise RuntimeError("intentional viewport verification failure")
        if len(values) == 1:
            self.values[plug] = values[0]
        else:
            self.values[plug] = [tuple(values)]
        if kwargs.get("type") == "string":
            self.attr_types[plug] = "string"
        else:
            self.attr_types.setdefault(
                plug,
                "double3" if len(values) == 3 else "double",
            )

    def shadingNode(self, node_type, asShader=False, name="", **kwargs):
        as_utility = bool(kwargs.get("asUtility"))
        as_texture = bool(kwargs.get("asTexture"))
        assert (
            (node_type == "lambert" and asShader is True)
            or (node_type == "place2dTexture" and as_utility)
            or (node_type == "file" and as_texture)
        )
        self.counter += 1
        node = name.rstrip("#") + str(self.counter)
        self.node_types[node] = node_type
        if node_type == "lambert":
            for attribute in (
                "color",
                "colorR",
                "colorG",
                "colorB",
                "ambientColor",
                "incandescence",
                "transparency",
                "transparencyR",
                "transparencyG",
                "transparencyB",
                "diffuse",
                "translucence",
                "translucenceDepth",
                "outColor",
            ):
                self.attr_types[node + "." + attribute] = (
                    "double3"
                    if attribute in (
                        "color",
                        "ambientColor",
                        "incandescence",
                        "transparency",
                        "outColor",
                    )
                    else "double"
                )
        elif node_type == "place2dTexture":
            vector_attributes = {
                "coverage",
                "translateFrame",
                "repeatUV",
                "offset",
                "noiseUV",
                "vertexUvOne",
                "vertexUvTwo",
                "vertexUvThree",
                "vertexCameraOne",
                "outUV",
                "outUvFilterSize",
            }
            for attribute in (
                "coverage",
                "translateFrame",
                "rotateFrame",
                "mirrorU",
                "mirrorV",
                "stagger",
                "wrapU",
                "wrapV",
                "repeatUV",
                "offset",
                "rotateUV",
                "noiseUV",
                "vertexUvOne",
                "vertexUvTwo",
                "vertexUvThree",
                "vertexCameraOne",
                "outUV",
                "outUvFilterSize",
            ):
                self.attr_types[node + "." + attribute] = (
                    "double3" if attribute in vector_attributes else "double"
                )
        else:
            vector_attributes = {
                "coverage",
                "translateFrame",
                "repeatUV",
                "offset",
                "noiseUV",
                "vertexUvOne",
                "vertexUvTwo",
                "vertexUvThree",
                "vertexCameraOne",
                "uvCoord",
                "uvFilterSize",
                "outColor",
            }
            for attribute in (
                "coverage",
                "translateFrame",
                "rotateFrame",
                "mirrorU",
                "mirrorV",
                "stagger",
                "wrapU",
                "wrapV",
                "repeatUV",
                "offset",
                "rotateUV",
                "noiseUV",
                "vertexUvOne",
                "vertexUvTwo",
                "vertexUvThree",
                "vertexCameraOne",
                "uvCoord",
                "uvFilterSize",
                "fileTextureName",
                "outColor",
                "outAlpha",
            ):
                if attribute == "fileTextureName":
                    attr_type = "string"
                elif attribute in vector_attributes:
                    attr_type = "double3"
                else:
                    attr_type = "double"
                self.attr_types[node + "." + attribute] = attr_type
        return node

    def createNode(self, node_type, name="", **_kwargs):
        assert node_type == "reverse"
        self.counter += 1
        node = name.rstrip("#") + str(self.counter)
        self.node_types[node] = "reverse"
        for attribute in (
            "input",
            "inputX",
            "inputY",
            "inputZ",
            "output",
            "outputX",
            "outputY",
            "outputZ",
        ):
            self.attr_types[node + "." + attribute] = (
                "double3" if attribute in ("input", "output") else "double"
            )
        return node

    def connectAttr(self, source, target, force=False):
        assert force is True
        if (
            self.fail_color_source == source
            and "HMB_Original_" in target
            and target.endswith(".color")
        ):
            raise RuntimeError("intentional incompatible shader output")
        if self.fail_target == target and "HMB_Original_" in source:
            raise RuntimeError("intentional SG swap failure")
        if (
            self.fail_restore_target == target
            and "HMB_Original_" not in source
        ):
            raise RuntimeError("intentional SG restore failure")
        self.connections[target] = source

    def isConnected(self, source, target):
        return self.connections.get(target) == source

    def delete(self, node):
        self.deleted.append(node)
        self.node_types.pop(node, None)
        for plug in list(self.attr_types):
            if plug.startswith(node + "."):
                self.attr_types.pop(plug, None)
                self.values.pop(plug, None)
        for target, source in list(self.connections.items()):
            if target.startswith(node + ".") or source.startswith(node + "."):
                self.connections.pop(target, None)


def original_connections(fake: FakeMaterialCmds) -> dict[str, str]:
    return {
        group: fake.connections[group + ".surfaceShader"]
        for group in fake.members
    }




# The fake Maya foundation above is retained for portable SG-membership tests.
# No old per-material/color/alpha/renderer-fallback expectations remain.
PROFILE = "maya-midgray-solid-studio-v1"
assert runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE == PROFILE


class MidgrayCmds(FakeMaterialCmds):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.node_types.update({
            "meshF": "mesh",
            "outsideMesh": "mesh",
            "emptySurfaceSG": "shadingEngine",
            "outsideSG": "shadingEngine",
            "displacementMap": "file",
            "volumeMat": "volumeShader",
        })
        self.members["emptySurfaceSG"] = ["meshF"]
        self.members["outsideSG"] = ["outsideMesh"]
        self.connections.update({
            "outsideSG.surfaceShader": "RedMat.outColor",
            "redSG.displacementShader": "displacementMap.outAlpha",
            "alphaSG.volumeShader": "volumeMat.outColor",
            "ExistingLambert.incandescence": "redFile.outColor",
        })
        self.values["redFile.fileTextureName"] = "P:/unavailable/team/texture.png"
        self.values["alphaMaskFile.fileTextureName"] = "//unreachable.invalid/share/alpha.png"
        self.authored_reads = []
        self.output_transform_enabled = True
        self.render_mode_labels = "Wire:Shaded:Wire on Shaded:Textured"
        for attribute in (
            "ssaoEnable", "shadows", "bloomEnable", "motionBlurEnable",
            "renderDepthOfField", "hwFogEnable", "xrayMode",
        ):
            self.values["hardwareRenderingGlobals." + attribute] = 1

    def attributeQuery(self, attribute, node="", listEnum=False):
        assert attribute == "renderMode" and node == "hardwareRenderingGlobals" and listEnum
        return [self.render_mode_labels]

    def colorManagementPrefs(self, **kwargs):
        assert kwargs.get("outputTarget") == "renderer"
        if kwargs.get("edit"):
            self.output_transform_enabled = bool(kwargs["outputTransformEnabled"])
        return self.output_transform_enabled

    def setAttr(self, plug, *values, **kwargs):
        if plug == self.fail_viewport_attr:
            raise RuntimeError("intentional viewport verification failure: " + plug)
        return super().setAttr(plug, *values, **kwargs)

    def _guard_authored_read(self, node, operation):
        node = str(node).split(".", 1)[0]
        if (node not in self.members and node != "hardwareRenderingGlobals"
                and not node.startswith("HMB_Original_")
                and self.node_types.get(node) not in ("mesh", "transform")):
            self.authored_reads.append((operation, node))
            raise AssertionError("Original must not evaluate authored appearance: " + node)

    def nodeType(self, node):
        self._guard_authored_read(node, "nodeType")
        return self.node_types.get(str(node), "")

    def getAttr(self, plug, **kwargs):
        self._guard_authored_read(plug, "getAttr")
        return super().getAttr(plug, **kwargs)

    def listAttr(self, node, **kwargs):
        self._guard_authored_read(node, "listAttr")
        return super().listAttr(node, **kwargs)

    def listConnections(self, target, **kwargs):
        self._guard_authored_read(target, "listConnections")
        return super().listConnections(target, **kwargs)

    def objExists(self, name):
        if "." in str(name):
            node, attr = str(name).split(".", 1)
            if node in self.members and attr in ("surfaceShader", "displacementShader", "volumeShader"):
                return True
        return super().objExists(name)

    def disconnectAttr(self, source, target):
        assert self.connections.get(target) == source
        if target == self.fail_restore_target and source.startswith("HMB_Original_"):
            raise RuntimeError("intentional empty SG restore failure")
        self.connections.pop(target)

    def delete(self, node):
        assert node.startswith("HMB_Original_"), "Never delete source materials/textures."
        super().delete(node)


def controller_for(fake, scope=None):
    runner.cmds = fake
    return runner._OriginalLambertOverrideController({
        "apply_original_lambert_override": True,
        "original_material_override_profile": PROFILE,
        "_viewport_quality_scope_shapes": list(
            BASE_SCOPE_SHAPES + ["meshF"] if scope is None else scope
        ),
    })


# Missing textures, unknown renderer materials, authored Lambert, cutout alpha,
# emission and displacement must all be irrelevant to the disposable shader.
fake = MidgrayCmds()
connections_before = copy.deepcopy(fake.connections)
members_before = copy.deepcopy(fake.members)
nodes_before = copy.deepcopy(fake.node_types)
controller = controller_for(fake)
with mock.patch.object(
    runner, "_original_texture_dependency_report",
    side_effect=AssertionError("texture dependency read"),
), mock.patch.object(
    runner, "_original_material_authority_records",
    side_effect=AssertionError("material authority read"),
):
    applied = controller.apply()
assert applied["temporary_lambert_count"] == 1
assert applied["contributing_shading_engine_count"] == 7
assert applied["swapped_shading_engine_count"] == 7
assert applied["base_color"] == [0.5, 0.5, 0.5]
assert applied["diffuse"] == 0.45
assert applied["fill_color"] == [0.22, 0.22, 0.22]
for field in (
    "authored_materials_ignored", "textures_ignored", "opaque_surface_verified",
    "shading_group_membership_preserved",
):
    assert applied[field] is True, field
assert fake.authored_reads == []
assert fake.members == members_before
sources = {
    fake.connections[group + ".surfaceShader"]
    for group in fake.members if group != "outsideSG"
}
assert len(sources) == 1
shader = next(iter(sources)).split(".", 1)[0]
assert fake.values[shader + ".color"] == [(0.5, 0.5, 0.5)]
assert fake.values[shader + ".diffuse"] == 0.45
assert fake.values[shader + ".incandescence"] == [(0.22, 0.22, 0.22)]
for attribute in ("ambientColor", "transparency"):
    assert fake.values[shader + "." + attribute] == [(0.0, 0.0, 0.0)]
assert not any(target.startswith(shader + ".") for target in fake.connections)
assert "redSG.displacementShader" not in fake.connections
assert "alphaSG.volumeShader" not in fake.connections
assert fake.connections["outsideSG.surfaceShader"] == connections_before["outsideSG.surfaceShader"]
restored = controller.finish()
assert restored["restore_ok"] is True and restored["status"] == "restored"
assert fake.connections == connections_before
assert fake.members == members_before
assert fake.node_types == nodes_before
assert fake.deleted == [shader]
assert controller.finish() == restored
assert fake.deleted == [shader], "Repeated finish must not double-delete."

# Explicit empty scope is a no-op, not a request to modify every scene SG.
empty = MidgrayCmds()
empty_before = copy.deepcopy(empty.connections)
empty_controller = controller_for(empty, [])
empty_report = empty_controller.apply()
assert empty_report["temporary_lambert_count"] == 0
assert empty_report["contributing_shading_engine_count"] == 0
assert empty_report["swapped_shading_engine_count"] == 0
assert empty_controller.finish()["restore_ok"] is True
assert empty.connections == empty_before and not empty.deleted

# A partial apply must roll back every already-touched SG/face assignment.
failing = MidgrayCmds(fail_target="redSG.surfaceShader")
failing_before = copy.deepcopy(failing.connections)
failing_controller = controller_for(failing)
try:
    failing_controller.apply()
except RuntimeError as exc:
    assert "intentional SG swap failure" in str(exc)
else:
    raise AssertionError("SG assignment failure was accepted.")
assert failing.connections == failing_before
assert failing.authored_reads == []
assert all(not node.startswith("HMB_Original_") for node in failing.node_types)

# Preserve temporary nodes if restoration fails; never report partial restoration
# as success and never delete the shader beneath a still-connected SG.
for target in ("blueSG.surfaceShader", "emptySurfaceSG.surfaceShader", "redSG.displacementShader"):
    restore_failure = MidgrayCmds(fail_restore_target=target)
    bad_controller = controller_for(restore_failure)
    bad_controller.apply()
    temporary_nodes = list(bad_controller.created_nodes)
    try:
        bad_controller.finish()
    except RuntimeError as exc:
        assert "restore" in str(exc).lower()
    else:
        raise AssertionError("Failed restoration was accepted: " + target)
    assert bad_controller.report["restore_ok"] is False
    assert bad_controller.report["status"] == "restore_failed"
    assert bad_controller.report["temporary_nodes_retained_on_restore_failure"] is True
    assert all(node in restore_failure.node_types for node in temporary_nodes)
    assert not set(temporary_nodes).intersection(restore_failure.deleted)
    if target.endswith(".surfaceShader"):
        assert restore_failure.connections.get(target, "").startswith("HMB_Original_"), (
            "Failed surface restoration must keep the usable neutral shader connected."
        )

# Default studio-like shape lighting and solid (non-textured) smooth rendering
# apply only to Original. Marker output still uses its existing textured mode.
viewport = MidgrayCmds()
runner.cmds = viewport
options = runner._set_viewport_render_options(
    preserve_authored_look=True, original_lambert_mode=True,
)
assert viewport.values["hardwareRenderingGlobals.lightingMode"] == 0
assert viewport.values["hardwareRenderingGlobals.renderMode"] == 1
assert options["default_lighting_verified"] is True
assert options["solid_render_mode_verified"] is True
assert options["soft_shading_verified"] is True
assert viewport.output_transform_enabled is False
for attribute in ("ssaoEnable", "shadows", "bloomEnable", "motionBlurEnable",
                  "renderDepthOfField", "hwFogEnable", "xrayMode"):
    assert viewport.values["hardwareRenderingGlobals." + attribute] == 0
# Native enum values may vary across supported Maya releases.
viewport.render_mode_labels = "Wire=0:Textured=4:Smooth Shaded=7"
runner._set_viewport_render_options(preserve_authored_look=True, original_lambert_mode=True)
assert viewport.values["hardwareRenderingGlobals.renderMode"] == 7
marker = MidgrayCmds()
runner.cmds = marker
marker_options = runner._set_viewport_render_options(
    preserve_authored_look=True, marker_mode=True,
)
assert marker.values["hardwareRenderingGlobals.renderMode"] == 4
assert marker_options["textured_render_mode_verified"] is True
for attr in ("hardwareRenderingGlobals.lightingMode", "hardwareRenderingGlobals.renderMode"):
    runner.cmds = MidgrayCmds(fail_viewport_attr=attr)
    try:
        runner._set_viewport_render_options(
            preserve_authored_look=True, original_lambert_mode=True,
        )
    except RuntimeError as exc:
        assert attr in str(exc)
    else:
        raise AssertionError("Unverifiable viewport state was accepted: " + attr)

# Sidecar validation must reject obsolete appearance profiles and inconsistent
# or unfinished restoration evidence, even when the MP4 itself is readable.
picker_spec = importlib.util.spec_from_file_location(
    "HMB_Midgray_Picker_Test", PICKER_PATH,
)
assert picker_spec is not None and picker_spec.loader is not None
picker = importlib.util.module_from_spec(picker_spec)
sys.modules[picker_spec.name] = picker
picker_spec.loader.exec_module(picker)
assert picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE == PROFILE
valid_report = {
    **restored,
    "default_lighting_verified": True,
    "solid_render_mode_verified": True,
    "soft_shading_verified": True,
}
assert picker._original_material_report_is_valid(valid_report)
for field, value in (
    ("profile", "per_source_material_lambert_texture_preserving_v1"),
    ("requested", False), ("status", "applied"), ("restore_ok", False),
    ("base_color", [0.4, 0.5, 0.5]), ("diffuse", 0.9),
    ("fill_color", [0.0, 0.0, 0.0]), ("soft_shading_verified", False),
    ("authored_materials_ignored", False), ("textures_ignored", False),
    ("opaque_surface_verified", False), ("default_lighting_verified", False),
    ("solid_render_mode_verified", False), ("shading_group_membership_preserved", False),
    ("temporary_lambert_count", 2), ("temporary_lambert_count", True),
    ("contributing_shading_engine_count", 6), ("swapped_shading_engine_count", 6),
    ("temporary_nodes_retained_on_restore_failure", True),
):
    invalid = copy.deepcopy(valid_report)
    invalid[field] = value
    assert not picker._original_material_report_is_valid(invalid), (field, value)

print("HMB VideoPicker texture-free shared midgray Original regression passed.")
