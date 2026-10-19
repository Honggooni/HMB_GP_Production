from __future__ import annotations

import ast
import copy
import fnmatch
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
        if kwargs.get("type"):
            return sorted(node for node, kind in self.node_types.items() if kind == kwargs["type"])
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
PROFILE = "maya-midgray-solid-studio-v4-eye-groups"
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
        self.values.update({
            "defaultRenderGlobals.imageFormat": 51,
            "defaultRenderGlobals.animation": 1,
            "defaultRenderGlobals.putFrameBeforeExt": 0,
            "defaultRenderGlobals.extensionPadding": 4,
        })
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
        if (node not in self.members
                and node not in ("hardwareRenderingGlobals", "defaultRenderGlobals")
                and not node.startswith("HMB_Original_")
                and self.node_types.get(node) not in ("mesh", "nurbsSurface", "nurbsCurve", "locator", "joint", "transform", "objectSet")):
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


class EyeMidgrayCmds(MidgrayCmds):
    """An authored native eye graph and exact face memberships, not a renderer stub."""

    EYE_LEFT = "|hero:ROOT|hero:Face_GRP|hero:eye_GEO_GRP|hero:Eye_L_GEO|hero:renderShape"
    EYE_RIGHT = "|hero:ROOT|hero:Face_GRP|hero:eye_GRP|hero:nested_GRP|hero:Eye_R_GEO|hero:renderShape"
    BODY = "|hero:ROOT|hero:Body_GEO|hero:bodyShape"
    BROW = "|hero:ROOT|hero:Face_GRP|hero:Eyebrow_L_GEO|hero:renderShape"
    EYE_LEFT_OWNER = EYE_LEFT.rsplit("|", 1)[0]
    EYE_RIGHT_OWNER = EYE_RIGHT.rsplit("|", 1)[0]
    BODY_OWNER = BODY.rsplit("|", 1)[0]
    BROW_OWNER = BROW.rsplit("|", 1)[0]
    # Real Maya SG queries name transform owners for whole objects and faces.
    BODY_MEMBERS = [BODY_OWNER + ".f[0:3]", BODY_OWNER + ".f[4:7]"]
    EYE_MEMBERS = [EYE_RIGHT_OWNER + ".f[0:7]"]

    def __init__(self, texture_directory, fail_split_after=0, fail_membership_restore=False):
        super().__init__()
        self.fail_split_after = fail_split_after
        self.fail_membership_restore = fail_membership_restore
        self.split_moves = 0
        self.assignment_calls = []
        self.alias_paths = {}
        self.object_sets = {"AIPicker_SET": [self.EYE_LEFT_OWNER, self.EYE_RIGHT_OWNER]}
        self.set_query_count = 0
        self.eye_nodes = {
            "EyeMat", "EyeBump", "EyeColor", "EyeAlpha", "EyeNormal", "EyeDisplacement",
        }
        for shape in (self.EYE_LEFT, self.EYE_RIGHT, self.BODY, self.BROW):
            segments = shape.split("|")[1:]
            for index in range(1, len(segments)):
                self.node_types["|" + "|".join(segments[:index])] = "transform"
            self.node_types[shape] = "mesh"
        self.node_types.update({
            "AIPicker_SET": "objectSet",
            "eyeOnlySG": "shadingEngine", "sharedEyeBodySG": "shadingEngine",
            "browSG": "shadingEngine", "EyeMat": "lambert", "EyeBump": "bump2d",
            "EyeColor": "file", "EyeAlpha": "file", "EyeNormal": "file",
            "EyeDisplacement": "file",
        })
        self.members = {
            "eyeOnlySG": [self.EYE_LEFT_OWNER],
            "sharedEyeBodySG": self.EYE_MEMBERS + self.BODY_MEMBERS,
            "browSG": [self.BROW_OWNER],
        }
        self.connections = {
            "eyeOnlySG.surfaceShader": "EyeMat.outColor",
            "eyeOnlySG.displacementShader": "EyeDisplacement.outAlpha",
            "sharedEyeBodySG.surfaceShader": "EyeMat.outColor",
            "sharedEyeBodySG.displacementShader": "EyeDisplacement.outAlpha",
            "browSG.surfaceShader": "AlphaMat.outColor",
            "EyeMat.color": "EyeColor.outColor",
            "EyeMat.transparency": "EyeAlpha.outColor",
            "EyeMat.normalCamera": "EyeBump.outNormal",
            "EyeBump.bumpValue": "EyeNormal.outAlpha",
        }
        self.values.update({
            "EyeMat.color": [(0.15, 0.35, 0.7)],
            "EyeMat.transparency": [(0.12, 0.12, 0.12)],
            "EyeMat.incandescence": [(0.03, 0.04, 0.05)],
            "EyeMat.diffuse": 0.8,
            "EyeBump.bumpDepth": 0.15,
        })
        for node in ("EyeColor", "EyeAlpha", "EyeNormal", "EyeDisplacement"):
            texture_path = texture_directory / (node + ".png")
            texture_path.write_bytes(b"authored-eye-texture-" + node.encode())
            self.values[node + ".fileTextureName"] = str(texture_path)
            self.attr_types[node + ".fileTextureName"] = "string"
            # Native file output plugs exist even without a cached output value.
            self.attr_types[node + ".outColor"] = "double3"
            self.attr_types[node + ".outAlpha"] = "double"
        for plug in self.values:
            if plug.startswith("Eye"):
                self.attr_types.setdefault(plug, "double3" if isinstance(self.values[plug], list) else "double")
        for plug in self.connections:
            if plug.startswith("Eye"):
                self.attr_types.setdefault(plug, "double3")

    def _guard_authored_read(self, node, operation):
        if str(node).split(".", 1)[0] not in self.eye_nodes:
            super()._guard_authored_read(node, operation)

    def ls(self, *nodes, **kwargs):
        if nodes:
            result = []
            for node in nodes:
                if isinstance(node, (tuple, list)):
                    result.extend(self.ls(*node, **kwargs))
                else:
                    name = str(node)
                    owner, separator, component = name.partition(".")
                    matches = self.alias_paths.get(owner)
                    if matches is None:
                        matches = [owner] if owner in self.node_types else [candidate for candidate in self.node_types if fnmatch.fnmatchcase(candidate, owner)]
                    if kwargs.get("dag"):
                        matches = [candidate for candidate in self.node_types if any(candidate == path or candidate.startswith(path + "|") for path in matches)]
                    if kwargs.get("type"):
                        matches = [candidate for candidate in matches if self.node_types.get(candidate) == kwargs["type"]]
                    if kwargs.get("shapes"):
                        matches = [candidate for candidate in matches if self.node_types.get(candidate) in ("mesh", "nurbsSurface", "nurbsCurve")]
                    result.extend(candidate + ("." + component if separator else "") for candidate in matches)
            return sorted(set(result))
        return super().ls(**kwargs)

    def nodeType(self, node, **kwargs):
        result = super().nodeType(node)
        return ["dagNode", "shape", result] if kwargs.get("inherited") and result in ("mesh", "nurbsSurface") else result

    def duplicate(self, node, inputConnections=False, name="", **kwargs):
        assert inputConnections and not kwargs
        assert self.node_types[node] not in ("mesh", "transform", "shadingEngine")
        self.counter += 1
        clone = name.rstrip("#") + str(self.counter)
        self.node_types[clone] = self.node_types[node]
        for mapping in (self.attr_types, self.values, self.connections):
            for plug, value in list(mapping.items()):
                if plug.startswith(node + "."):
                    mapping[clone + plug[len(node):]] = copy.deepcopy(value)
        return [clone]

    def listConnections(self, target, **kwargs):
        if kwargs.get("connections"):
            self._guard_authored_read(target, "listConnections")
            assert kwargs.get("source") and not kwargs.get("destination") and kwargs.get("plugs")
            result = []
            for destination, source in sorted(self.connections.items()):
                if destination.startswith(str(target) + "."):
                    result.extend((destination, source))
            return result
        return super().listConnections(target, **kwargs)

    def unknownNode(self, node, query=False, **kwargs):
        assert query and self.node_types[node] == "unknown"
        if kwargs.get("plugin"):
            return "redshift4maya"
        if kwargs.get("realClassName"):
            return "RedshiftColorCorrection" if node == "EyeCorrection" else "RedshiftMaterial"
        raise AssertionError(kwargs)

    def listSets(self, type=0, object="", **_kwargs):
        assert type == 1
        target = str(object)
        owners = {target}
        if self.node_types.get(target) in ("mesh", "nurbsSurface"):
            owners.add(target.rsplit("|", 1)[0])
        return sorted(group for group, members in self.members.items()
                      if any(str(member).split(".", 1)[0] in owners for member in members))

    def attributeQuery(self, attribute, node="", **kwargs):
        if attribute == "intermediateObject" and kwargs.get("exists"):
            return self.node_types.get(node) in ("mesh", "nurbsSurface")
        return super().attributeQuery(attribute, node=node, **kwargs)

    def getAttr(self, plug, **kwargs):
        if str(plug).endswith(".intermediateObject"):
            return self.values.get(plug, 0)
        return super().getAttr(plug, **kwargs)

    def listRelatives(self, node, **kwargs):
        node = str(node)
        if kwargs.get("parent"):
            return [node.rsplit("|", 1)[0]] if "|" in node and node.rsplit("|", 1)[0] else []
        children = [candidate for candidate in self.node_types if candidate.startswith(node + "|") and (kwargs.get("allDescendents") or kwargs.get("ad") or candidate.rsplit("|", 1)[0] == node)]
        if kwargs.get("shapes"):
            children = [candidate for candidate in children if self.node_types[candidate] in ("mesh", "nurbsSurface")]
        if kwargs.get("noIntermediate"):
            children = [candidate for candidate in children if not self.values.get(candidate + ".intermediateObject", 0)]
        if kwargs.get("type"):
            children = [candidate for candidate in children if self.node_types[candidate] == kwargs["type"]]
        return sorted(children)

    def sets(self, group=None, query=False, **kwargs):
        if query:
            if self.node_types.get(group) == "objectSet":
                self.set_query_count += 1
                return list(self.object_sets.get(group, []))
            return list(self.members.get(group, []))
        if kwargs.get("empty"):
            assert kwargs.get("renderable") and kwargs.get("noSurfaceShader")
            self.counter += 1
            created = kwargs["name"].rstrip("#") + str(self.counter)
            self.node_types[created] = "shadingEngine"
            self.members[created] = []
            return created
        assert kwargs.get("edit") and kwargs.get("forceElement") in self.members
        target = kwargs["forceElement"]
        members = list(group) if isinstance(group, (tuple, list)) else [group]
        self.assignment_calls.append((target, list(members)))
        if self.fail_membership_restore and target == "sharedEyeBodySG":
            raise RuntimeError("intentional shared body membership restore failure")
        for member in members:
            for existing in self.members.values():
                while member in existing:
                    existing.remove(member)
            self.members[target].append(member)
            if target.startswith("HMB_Original_"):
                self.split_moves += 1
                if self.fail_split_after and self.split_moves >= self.fail_split_after:
                    raise RuntimeError("intentional partial body membership assignment failure")
        return target

    def setAttr(self, plug, *values, **kwargs):
        assert not str(plug).split(".", 1)[0].startswith("Eye"), "Never modify an authored eye value."
        return super().setAttr(plug, *values, **kwargs)

    def connectAttr(self, source, target, **kwargs):
        assert not str(target).split(".", 1)[0].startswith("Eye"), "Never rewire the authored eye graph."
        return super().connectAttr(source, target, **kwargs)

    def disconnectAttr(self, source, target):
        assert not str(target).split(".", 1)[0].startswith("Eye"), "Never disconnect the authored eye graph."
        return super().disconnectAttr(source, target)

    def delete(self, node):
        self.members.pop(node, None)
        return super().delete(node)

    def snapshot(self):
        return copy.deepcopy((self.node_types, self.members, self.connections, self.values, self.attr_types, self.object_sets))

    def authored_eye_snapshot(self):
        return copy.deepcopy((
            {node: kind for node, kind in self.node_types.items() if node in self.eye_nodes},
            {plug: value for plug, value in self.connections.items() if plug.split(".", 1)[0] in self.eye_nodes or plug.split(".", 1)[0] in ("eyeOnlySG", "sharedEyeBodySG")},
            {plug: value for plug, value in self.values.items() if plug.split(".", 1)[0] in self.eye_nodes},
        ))


def configure_pass_sets(fake, sets):
    for name in list(fake.node_types):
        if fake.node_types[name] == "objectSet":
            fake.node_types.pop(name)
    fake.object_sets = copy.deepcopy(sets)
    fake.node_types.update({name: "objectSet" for name in sets})


def add_surface(fake, path, kind="mesh"):
    segments = path.split("|")[1:]
    for index in range(1, len(segments)):
        fake.node_types["|" + "|".join(segments[:index])] = "transform"
    fake.node_types[path] = kind
    return path


# Original material preservation is governed solely by the two exact pass SETs.
# objectSet membership. Legacy names never implicitly preserve a surface.
with tempfile.TemporaryDirectory(prefix="hmb-authored-eye-") as texture_root:
    texture_directory = Path(texture_root)
    # No set, an empty set, and similarly named sets are all deliberate no-pass
    # states. Neither legacy group grants a fallback material exception.
    for set_names in ({}, {"AIPicker_SET": []}, {"aipicker_set": [EyeMidgrayCmds.EYE_LEFT_OWNER]},
                      {"AIPicker_SET_extra": [EyeMidgrayCmds.EYE_LEFT_OWNER]},
                      {"hero:AIPicker_set": [EyeMidgrayCmds.EYE_LEFT_OWNER]}):
        no_pass = EyeMidgrayCmds(texture_directory)
        configure_pass_sets(no_pass, set_names)
        runner.cmds = no_pass
        before = no_pass.snapshot()
        assert runner._original_pass_set_shapes() == set(), set_names
        assert not runner._original_eye_shape(no_pass.EYE_LEFT)
        assert not runner._original_eye_shape(no_pass.EYE_RIGHT)
        assert no_pass.snapshot() == before
    no_pass.node_types["|ROOT|AIPicker_SET"] = "transform"
    add_surface(no_pass, "|ROOT|AIPicker_SET|geometry|surfaceShape")
    assert runner._original_pass_set_shapes() == set(), "A same-name DAG group is not an objectSet."

    # The new M set contributes to Original independently, and both exact
    # names union their memberships. The M-only Mask policy is separate.
    for prefix in ("", "studio:hero:"):
        pair = EyeMidgrayCmds(texture_directory)
        configure_pass_sets(pair, {
            prefix + "AIPicker_SET": [pair.EYE_LEFT_OWNER],
            prefix + "AIPickerM_SET": [pair.EYE_RIGHT_OWNER + ".f[0:2]"],
            prefix + "AIPickerM_SET_extra": [pair.BODY_OWNER],
        })
        runner.cmds = pair
        assert runner._original_pass_set_shapes() == {pair.EYE_LEFT, pair.EYE_RIGHT}
        assert runner._mask_pass_set_shapes() == {pair.EYE_RIGHT}
        pair_before = pair.snapshot()
        pair_controller = controller_for(pair, [pair.EYE_LEFT, pair.EYE_RIGHT])
        pair_report = pair_controller.apply()
        assert pair_report["material_pass_sources"] == ["AIPicker_SET", "AIPickerM_SET"]
        assert pair_report["material_pass_shape_count"] == pair_report["preserved_eye_shape_count"] == 2
        assert pair_controller.finish()["restore_ok"] and pair.snapshot() == pair_before

    # Recursively nested sets, including a cycle, preserve exactly their members.
    # An unreferenced set must not expand the pass merely because it exists.
    nested = EyeMidgrayCmds(texture_directory)
    configure_pass_sets(nested, {
        "AIPicker_SET": ["Parts_SET", nested.EYE_LEFT_OWNER],
        "Parts_SET": ["Inner_SET", nested.EYE_LEFT_OWNER],
        "Inner_SET": ["AIPicker_SET", nested.EYE_RIGHT],
        "Unrelated_SET": [nested.BODY_OWNER],
    })
    runner.cmds = nested
    before = nested.snapshot()
    assert runner._original_pass_set_shapes() == {nested.EYE_LEFT, nested.EYE_RIGHT}
    assert nested.set_query_count == 3, "Cycle detection must visit each reachable set once."
    assert nested.snapshot() == before
    nested.set_query_count = 0
    assert not runner._original_eye_shape(nested.EYE_LEFT, set()), "A supplied empty cache is authoritative."
    assert nested.set_query_count == 0, "Do not reread sets when a cache was supplied."

    # Each exact namespaced set contributes only its explicit members.
    namespaced = EyeMidgrayCmds(texture_directory)
    other = add_surface(namespaced, "|other:ROOT|other:Body_GRP|other:renderShape")
    configure_pass_sets(namespaced, {
        "studio:hero:AIPicker_SET": [namespaced.EYE_LEFT_OWNER],
        "other:AIPicker_SET": [other],
        "other:AIPicker_SET_old": [namespaced.BODY],
    })
    runner.cmds = namespaced
    assert runner._original_pass_set_shapes() == {namespaced.EYE_LEFT, other}
    assert not runner._original_eye_shape(namespaced.EYE_RIGHT), "Do not expand a namespace to sibling objects."
    assert not runner._original_eye_shape(namespaced.BODY)

    # Group members expand all final drawable descendants, with construction
    # meshes and control curves excluded. The group name itself is unrestricted.
    descendants = EyeMidgrayCmds(texture_directory)
    first = add_surface(descendants, "|setRoot|Any_GRP|nested_GRP|meshOwner|meshShape")
    second = add_surface(descendants, "|setRoot|Any_GRP|nested_GRP|nurbsOwner|nurbsShape", "nurbsSurface")
    history = add_surface(descendants, "|setRoot|Any_GRP|nested_GRP|meshOwner|historyShape")
    descendants.values[history + ".intermediateObject"] = 1
    add_surface(descendants, "|setRoot|Any_GRP|control|controlShape", "nurbsCurve")
    configure_pass_sets(descendants, {"AIPicker_SET": ["|setRoot|Any_GRP"]})
    runner.cmds = descendants
    assert runner._original_pass_set_shapes() == {first, second}

    # Component membership expresses an object pass, rather than shading only
    # selected faces. It must not spill into any other surface of an ancestor.
    for component in (EyeMidgrayCmds.EYE_LEFT + ".f[0:3]", EyeMidgrayCmds.EYE_LEFT_OWNER + ".f[0:3]",
                      EyeMidgrayCmds.EYE_LEFT + ".vtx[1:2]"):
        component_pass = EyeMidgrayCmds(texture_directory)
        configure_pass_sets(component_pass, {"AIPicker_SET": [component]})
        runner.cmds = component_pass
        assert runner._original_pass_set_shapes() == {component_pass.EYE_LEFT}, component

    # A concrete instance member preserves only that concrete DAG instance.
    # allPaths on the object's short name must never broaden an exact member.
    instance = EyeMidgrayCmds(texture_directory)
    instance_a = add_surface(instance, "|instanceA|sharedOwner|sharedShape")
    instance_b = add_surface(instance, "|instanceB|sharedOwner|sharedShape")
    instance.alias_paths["sharedShape"] = [instance_a, instance_b]
    instance.alias_paths["sharedOwner"] = [instance_a.rsplit("|", 1)[0], instance_b.rsplit("|", 1)[0]]
    configure_pass_sets(instance, {"AIPicker_SET": [instance_a]})
    runner.cmds = instance
    assert runner._original_pass_set_shapes() == {instance_a}
    assert runner._original_eye_shape(instance_a)
    assert not runner._original_eye_shape(instance_b)
    configure_pass_sets(instance, {"AIPicker_SET": [instance_a.rsplit("|", 1)[0]]})
    assert runner._original_pass_set_shapes() == {instance_a}
    for ambiguous_member in ("sharedShape", "sharedOwner"):
        configure_pass_sets(instance, {"AIPicker_SET": [ambiguous_member]})
        before = instance.snapshot()
        try:
            runner._original_pass_set_shapes()
        except RuntimeError as exc:
            assert "AIPicker_SET" in str(exc)
        else:
            raise AssertionError("Ambiguous set membership must fail before material edits: " + ambiguous_member)
        assert instance.snapshot() == before
    configure_pass_sets(instance, {"AIPicker_SET": ["deletedOrUnloadedObject"]})
    try:
        runner._original_pass_set_shapes()
    except RuntimeError as exc:
        assert "one exact object path" in str(exc)
    else:
        raise AssertionError("Missing pass members must fail closed, not silently become gray.")
    with mock.patch.object(instance, "sets", side_effect=RuntimeError("set membership unavailable")):
        try:
            runner._original_pass_set_shapes()
        except RuntimeError as exc:
            assert "could not read AIPicker_SET|AIPickerM_SET membership" in str(exc)
        else:
            raise AssertionError("Unreadable pass-set membership must fail before material edits.")

    eyes = EyeMidgrayCmds(texture_directory)
    original_eye_graph = eyes.authored_eye_snapshot()
    all_before = eyes.snapshot()
    eye_controller = controller_for(eyes, [eyes.EYE_LEFT, eyes.EYE_RIGHT, eyes.BODY, eyes.BROW])
    assert runner._original_eye_shape(eyes.EYE_LEFT)
    assert runner._original_eye_shape(eyes.EYE_RIGHT)
    assert not runner._original_eye_shape(eyes.BROW)
    assert not runner._original_eye_shape(eyes.BODY)
    assert runner._original_pass_set_shapes() == {eyes.EYE_LEFT, eyes.EYE_RIGHT}
    eyes.set_query_count = 0
    eye_applied = eye_controller.apply()
    assert eyes.set_query_count == 1, "Resolve each pass set once per controller capture, not once per SG member."
    assert eye_applied["material_pass_source"] == "AIPicker_SET|AIPickerM_SET"
    assert eye_applied["material_pass_sources"] == ["AIPicker_SET", "AIPickerM_SET"]
    assert eye_applied["material_pass_shape_count"] == 2
    assert eye_applied["preserved_eye_shape_count"] == 2
    assert eye_applied["preserved_eye_component_count"] == 8
    assert eye_applied["preserved_eye_shading_engine_count"] == 2
    assert eye_applied["split_shading_engine_count"] == 1
    assert eye_applied["split_body_member_count"] == 2
    assert eye_applied["contributing_shading_engine_count"] == 3
    assert eye_applied["swapped_shading_engine_count"] == 1
    assert eye_applied["temporary_lambert_count"] == 1
    assert eye_applied["eye_texture_dependency_count"] == 4
    for field in ("eye_materials_preserved", "eye_assignments_preserved", "eye_textures_enabled", "eye_dependency_preflight_passed", "opaque_surface_verified"):
        assert eye_applied[field] is True, field
    assert eyes.authored_eye_snapshot() == original_eye_graph, "Color/alpha/normal/displacement and eye shading must remain exact during capture."
    assert eyes.members["eyeOnlySG"] == [eyes.EYE_LEFT_OWNER]
    assert eyes.members["sharedEyeBodySG"] == eyes.EYE_MEMBERS
    split_group = next(group for group in eyes.members if group.startswith("HMB_Original_"))
    assert sorted(eyes.members[split_group]) == eyes.BODY_MEMBERS
    body_shader = eyes.connections[split_group + ".surfaceShader"].split(".", 1)[0]
    assert eyes.connections["browSG.surfaceShader"] == body_shader + ".outColor"
    assert eyes.values[body_shader + ".color"] == [(0.5, 0.5, 0.5)]
    assert eyes.values[body_shader + ".transparency"] == [(0.0, 0.0, 0.0)]
    assert not any(plug.startswith(body_shader + ".") for plug in eyes.connections), "Body gray must have no authored eye texture input."
    assert eyes.authored_reads == [], "Appearance queries may inspect eyes only."
    eye_restored = eye_controller.finish()
    assert eye_restored["restore_ok"] and eye_restored["status"] == "restored"
    assert eyes.snapshot() == all_before, "All exact face memberships, graph connections and authored values must restore."
    assert len(eyes.deleted) == 2 and all(node.startswith("HMB_Original_") for node in eyes.deleted)
    assert eye_controller.finish() == eye_restored and len(eyes.deleted) == 2

    # Eye-only scenes need no neutral shader or assignment rewrite.
    eye_only = EyeMidgrayCmds(texture_directory)
    eye_only_before = eye_only.snapshot()
    eye_only_controller = controller_for(eye_only, [eye_only.EYE_LEFT])
    eye_only_report = eye_only_controller.apply()
    assert eye_only_report["temporary_lambert_count"] == 0
    assert eye_only_report["preserved_eye_shading_engine_count"] == 1
    assert eye_only_report["split_shading_engine_count"] == 0
    assert not eye_only.assignment_calls and not eye_only_controller.created_nodes
    assert eye_only.snapshot() == eye_only_before
    assert eye_only_controller.finish()["restore_ok"]
    assert eye_only.snapshot() == eye_only_before

    # Arbitrarily named group members recursively preserve mesh/NURBS surfaces.
    # Exact set names also work with nested namespaces; DAG names are irrelevant.
    for group_name in ("Unrelated_GRP", "Body_GRP"):
        for namespace in ("", "studio:hero:"):
            for surface_type in ("mesh", "nurbsSurface"):
                grouped = EyeMidgrayCmds(texture_directory)
                surface = "|ROOT|{0}{1}|nested_GRP|Body_Eyebrow_GEO|surfaceShape".format(namespace, group_name)
                segments = surface.split("|")[1:]
                for index in range(1, len(segments)):
                    grouped.node_types["|" + "|".join(segments[:index])] = "transform"
                grouped.node_types[surface] = surface_type
                owner = surface.rsplit("|", 1)[0]
                grouped.members = {"eyeOnlySG": [owner + ".f[0:3]" if surface_type == "mesh" else owner]}
                configure_pass_sets(grouped, {namespace + "AIPicker_SET": ["|ROOT|" + namespace + group_name]})
                grouped_before = grouped.snapshot()
                grouped_controller = controller_for(grouped, [surface])
                assert runner._original_eye_shape(surface), surface
                grouped_report = grouped_controller.apply()
                assert grouped_report["preserved_eye_shape_count"] == 1
                assert grouped_report["preserved_eye_component_count"] == (4 if surface_type == "mesh" else 0)
                assert grouped_report["temporary_lambert_count"] == 0
                assert not grouped.assignment_calls and not grouped_controller.created_nodes
                assert grouped.snapshot() == grouped_before
                assert grouped_controller.finish()["restore_ok"]
                assert grouped.snapshot() == grouped_before

    # Both former exact names, eye-like names, and face assignments outside the
    # set must become gray. Shader sharing and group ancestry grant no exception.
    for outside_group in ("eye_GEO_GRP", "eye_GRP", "Eyes_GRP", "eye_GEO_GRP_extra", "eye_GRP2", "Eye_GRP", "eye_GRP:Body_GRP"):
        outside = EyeMidgrayCmds(texture_directory)
        surface = "|ROOT|" + outside_group + "|Iris_GEO|eyeShape"
        segments = surface.split("|")[1:]
        for index in range(1, len(segments)):
            outside.node_types["|" + "|".join(segments[:index])] = "transform"
        outside.node_types[surface] = "mesh"
        outside.members = {"sharedEyeBodySG": [surface.rsplit("|", 1)[0] + ".f[0:3]"]}
        outside_before = outside.snapshot()
        outside_controller = controller_for(outside, [surface])
        assert not runner._original_eye_shape(surface), surface
        outside_report = outside_controller.apply()
        assert outside_report["preserved_eye_shape_count"] == 0
        assert outside_report["preserved_eye_shading_engine_count"] == 0
        assert outside_report["temporary_lambert_count"] == 1
        assert outside.connections["sharedEyeBodySG.surfaceShader"].startswith("HMB_Original_")
        assert outside_controller.finish()["restore_ok"]
        assert outside.snapshot() == outside_before
    outside.node_types["|ROOT|eye_GRP"] = "mesh"
    assert not runner._original_eye_shape("|ROOT|eye_GRP"), "A surface name is not a pass group."

    # Set group descendants preserve body/brow-named meshes and face assignments.
    # The same EyeMat on an object outside the set grants no exception.
    combined = EyeMidgrayCmds(texture_directory)
    head = "|hero:ROOT|hero:Face_GRP|hero:eye_GRP|hero:Body_Eyebrow_GEO|hero:HeadShape"
    combined.node_types[head.rsplit("|", 1)[0]] = "transform"
    combined.node_types[head] = "mesh"
    head_owner = head.rsplit("|", 1)[0]
    eye_face_member = head_owner + ".f[0:3]"
    combined.members = {"sharedEyeBodySG": [eye_face_member, combined.BODY_OWNER]}
    configure_pass_sets(combined, {"AIPicker_SET": [head_owner]})
    combined.values[combined.BODY_OWNER + ".visibility"] = 0
    history_shape = head_owner + "|hero:HeadOrigShape"
    combined.node_types[history_shape] = "mesh"
    combined.values[history_shape + ".intermediateObject"] = 1
    combined_before = combined.snapshot()
    combined_eye_graph = combined.authored_eye_snapshot()
    combined_controller = controller_for(combined, [head, combined.BODY])
    # This render-scope helper deliberately filters concrete shape paths; it
    # does not expand transform owners. Calling it from member resolution was
    # the native bug, so the fake must never make that old call pass.
    assert runner._depth_supported_surface_shapes([head_owner]) == []
    assert runner._depth_supported_surface_shapes([combined.BODY_OWNER]) == []
    combined_applied = combined_controller.apply()
    assert combined_applied["preserved_eye_shape_count"] == 1
    assert combined_applied["preserved_eye_component_count"] == 4
    assert combined_applied["preserved_eye_shading_engine_count"] == 1
    assert combined_applied["split_shading_engine_count"] == 1
    assert combined_applied["split_body_member_count"] == 1
    assert combined_applied["swapped_shading_engine_count"] == 0
    assert combined.members["sharedEyeBodySG"] == [eye_face_member]
    combined_split = next(group for group in combined.members if group.startswith("HMB_Original_"))
    assert combined.members[combined_split] == [combined.BODY_OWNER]
    assert combined.authored_eye_snapshot() == combined_eye_graph
    combined_body_shader = combined.connections[combined_split + ".surfaceShader"].split(".", 1)[0]
    assert combined.values[combined_body_shader + ".color"] == [(0.5, 0.5, 0.5)]
    assert combined_controller.finish()["restore_ok"]
    assert combined.snapshot() == combined_before

    # A whole transform must identify exactly one final mesh/NURBS surface.
    # Zero children and two final shapes are ambiguous and fail before edits.
    for child_count in (0, 2):
        invalid_owner = EyeMidgrayCmds(texture_directory)
        invalid_owner.members = {"sharedEyeBodySG": invalid_owner.EYE_MEMBERS + [invalid_owner.BODY_OWNER]}
        if child_count == 0:
            invalid_owner.node_types.pop(invalid_owner.BODY)
        else:
            invalid_owner.node_types[invalid_owner.BODY_OWNER + "|hero:secondBodyShape"] = "mesh"
        invalid_owner_before = invalid_owner.snapshot()
        invalid_owner_controller = controller_for(invalid_owner, [invalid_owner.EYE_RIGHT])
        try:
            invalid_owner_controller.apply()
        except RuntimeError as exc:
            assert "cannot be resolved exactly" in str(exc)
            assert "one surface" in str(exc)
        else:
            raise AssertionError("Non-unique transform surface membership was accepted: " + str(child_count))
        assert invalid_owner.snapshot() == invalid_owner_before
        assert not invalid_owner.assignment_calls and not invalid_owner_controller.created_nodes

    # Maya may move some members before raising. Roll back that partial split,
    # including a body shader already attached to the preceding brow SG.
    partial_eye = EyeMidgrayCmds(texture_directory, fail_split_after=1)
    partial_before = partial_eye.snapshot()
    partial_controller = controller_for(partial_eye, [partial_eye.EYE_LEFT, partial_eye.EYE_RIGHT, partial_eye.BODY, partial_eye.BROW])
    try:
        partial_controller.apply()
    except RuntimeError as exc:
        assert "partial body membership" in str(exc)
    else:
        raise AssertionError("A partially failed body/eye SG split was accepted.")
    assert partial_eye.snapshot() == partial_before
    assert partial_controller.report["restore_ok"] is True
    assert all(node.startswith("HMB_Original_") for node in partial_eye.deleted)

    # Ambiguous instance membership must fail before modifying any connection.
    ambiguous = EyeMidgrayCmds(texture_directory)
    ambiguous.members["sharedEyeBodySG"] = ambiguous.EYE_MEMBERS + ["bodyInstance"]
    ambiguous.alias_paths["bodyInstance"] = [ambiguous.BODY, "|second:ROOT|second:bodyShape"]
    ambiguous_before = ambiguous.snapshot()
    ambiguous_controller = controller_for(ambiguous, [ambiguous.EYE_RIGHT])
    try:
        ambiguous_controller.apply()
    except RuntimeError as exc:
        assert "cannot be resolved exactly" in str(exc)
    else:
        raise AssertionError("Ambiguous instanced body membership was accepted.")
    assert ambiguous.snapshot() == ambiguous_before and not ambiguous.assignment_calls
    assert not ambiguous_controller.created_nodes

    # A preserved shader without usable textures is a failed capture, never a
    # successful gray-eye fallback. This also covers normal/displacement maps.
    for unavailable_node in ("EyeNormal", "EyeDisplacement"):
        missing_eye = EyeMidgrayCmds(texture_directory)
        missing_eye.values[unavailable_node + ".fileTextureName"] = str(texture_directory / "missing-eye-texture.png")
        missing_before = missing_eye.snapshot()
        missing_controller = controller_for(missing_eye, [missing_eye.EYE_LEFT])
        try:
            missing_controller.apply()
        except RuntimeError as exc:
            assert "cannot preserve the authored eye appearance" in str(exc)
        else:
            raise AssertionError("Unavailable authored eye texture was accepted: " + unavailable_node)
        assert missing_eye.snapshot() == missing_before and not missing_controller.created_nodes

    # An unavailable renderer eye uses a native temporary shader. The native
    # file color/alpha inputs remain live, while shared body faces stay opaque gray.
    unavailable_eye = EyeMidgrayCmds(texture_directory)
    unavailable_eye.node_types["EyeMat"] = "unknown"
    unavailable_before = unavailable_eye.snapshot()
    authored_inputs = {plug: source for plug, source in unavailable_eye.connections.items()
                       if plug.split(".", 1)[0] in unavailable_eye.eye_nodes}
    unavailable_controller = controller_for(unavailable_eye, [
        unavailable_eye.EYE_LEFT, unavailable_eye.EYE_RIGHT, unavailable_eye.BODY, unavailable_eye.BROW,
    ])
    fallback_report = unavailable_controller.apply()
    fallback_shader = unavailable_eye.connections["eyeOnlySG.surfaceShader"].split(".", 1)[0]
    assert fallback_shader.startswith("HMB_Original_EyeFallback_Lambert")
    assert unavailable_eye.node_types[fallback_shader] == "lambert"
    assert unavailable_eye.connections["sharedEyeBodySG.surfaceShader"] == fallback_shader + ".outColor"
    assert unavailable_eye.connections[fallback_shader + ".color"] == "EyeColor.outColor"
    assert unavailable_eye.connections[fallback_shader + ".transparency"] == "EyeAlpha.outColor"
    assert unavailable_eye.values[fallback_shader + ".incandescence"] == [(0.03, 0.04, 0.05)]
    assert {plug: source for plug, source in unavailable_eye.connections.items()
            if plug.split(".", 1)[0] in unavailable_eye.eye_nodes} == authored_inputs
    assert unavailable_eye.members["sharedEyeBodySG"] == unavailable_eye.EYE_MEMBERS
    split_group = next(group for group in unavailable_eye.members
                       if group.startswith("HMB_Original_Midgray_SplitSG"))
    body_shader = unavailable_eye.connections[split_group + ".surfaceShader"].split(".", 1)[0]
    assert body_shader != fallback_shader
    assert unavailable_eye.values[body_shader + ".color"] == [(0.5, 0.5, 0.5)]
    assert unavailable_eye.values[body_shader + ".transparency"] == [(0.0, 0.0, 0.0)]
    assert body_shader + ".color" not in unavailable_eye.connections
    assert runner._original_plugin_dependency_report(fallback_shader + ".outColor")["unavailable_plugin_nodes"] == []
    assert fallback_report["eye_fallback_applied"] and fallback_report["eye_fallback_verified"]
    assert fallback_report["eye_dependency_preflight_passed"]
    for key, expected in {
        "eye_fallback_shading_engine_count": 2, "eye_fallback_shape_count": 2,
        "eye_fallback_material_count": 1, "eye_fallback_texture_connection_count": 4,
        "eye_unavailable_plugin_dependency_count": 1, "temporary_lambert_count": 1,
    }.items():
        assert fallback_report[key] == expected, (key, fallback_report[key])
    for record in fallback_report["eye_fallback_records"]:
        assert record["source_shader_plug"] == "EyeMat.outColor"
        assert record["native_shader"] == fallback_shader
        assert record["color_mode"] == "native_texture" and record["color_source"] == "EyeColor.outColor"
        assert record["texture_connection_count"] == 2
        assert record["unavailable_plugin_nodes"][0]["plugin"] == "redshift4maya"
    fallback_restored = unavailable_controller.finish()
    assert fallback_restored["restore_ok"] and fallback_restored["eye_materials_preserved"]
    assert unavailable_eye.snapshot() == unavailable_before

    # Cached numeric color is preferred to the Maya default; no usable authored
    # color leaves the native Lambert default. Neither branch edits authored DG.
    for color_mode, expected_color in (("cached_numeric", (0.15, 0.35, 0.7)),
                                       ("maya_default", (0.5, 0.5, 0.5))):
        numeric_eye = EyeMidgrayCmds(texture_directory)
        numeric_eye.node_types["EyeMat"] = "unknown"
        numeric_eye.connections.pop("EyeMat.color")
        if color_mode == "maya_default":
            for plug in ("EyeMat.color", "EyeMat.diffuse"):
                numeric_eye.values.pop(plug, None)
                numeric_eye.attr_types.pop(plug, None)
        numeric_before = numeric_eye.snapshot()
        numeric_controller = controller_for(numeric_eye, [numeric_eye.EYE_LEFT])
        numeric_report = numeric_controller.apply()
        numeric_record = numeric_report["eye_fallback_records"][0]
        numeric_shader = numeric_record["native_shader"]
        assert numeric_record["color_mode"] == color_mode and numeric_record["color_source"] == ""
        assert numeric_eye.values[numeric_shader + ".color"] == [expected_color]
        assert numeric_shader + ".color" not in numeric_eye.connections
        numeric_controller.finish()
        assert numeric_eye.snapshot() == numeric_before

    # A native utility containing a missing renderer input must be cloned before
    # rewiring. The original blend and unknown renderer graph remain untouched.
    wrapped_eye = EyeMidgrayCmds(texture_directory)
    wrapped_eye.node_types.update({"EyeMat": "unknown", "EyeCorrection": "unknown", "EyeBlend": "blendColors"})
    wrapped_eye.eye_nodes.update(("EyeCorrection", "EyeBlend"))
    wrapped_eye.connections.update({
        "EyeMat.color": "EyeBlend.output", "EyeBlend.color1": "EyeCorrection.outColor",
        "EyeCorrection.input": "EyeColor.outColor",
    })
    wrapped_eye.values.update({"EyeBlend.color1": [(0.2, 0.3, 0.4)], "EyeBlend.color2": [(0.0, 0.0, 0.0)],
                              "EyeBlend.blender": 1.0, "EyeCorrection.input": [(0.15, 0.35, 0.7)]})
    wrapped_eye.attr_types.update({"EyeBlend.output": "double3", "EyeBlend.color1": "double3",
                                  "EyeBlend.color2": "double3", "EyeBlend.blender": "double",
                                  "EyeCorrection.input": "double3", "EyeCorrection.outColor": "double3"})
    wrapped_before = wrapped_eye.snapshot()
    wrapped_inputs = copy.deepcopy(wrapped_eye.connections)
    wrapped_controller = controller_for(wrapped_eye, [wrapped_eye.EYE_LEFT])
    wrapped_report = wrapped_controller.apply()
    wrapped_record = wrapped_report["eye_fallback_records"][0]
    assert wrapped_record["color_source"].startswith("HMB_Original_EyeNativeGraph")
    assert wrapped_record["color_source"].endswith(".output")
    assert wrapped_eye.node_types[wrapped_record["color_source"].split(".", 1)[0]] == "blendColors"
    for destination, incoming in wrapped_inputs.items():
        if destination.split(".", 1)[0] in wrapped_eye.eye_nodes:
            assert wrapped_eye.connections[destination] == incoming
    assert wrapped_report["eye_unavailable_plugin_dependency_count"] == 2
    assert runner._original_plugin_dependency_report(wrapped_record["native_shader"] + ".outColor")["unavailable_plugin_nodes"] == []
    wrapped_controller.finish()
    assert wrapped_eye.snapshot() == wrapped_before

    # Missing native textures do not qualify for default-shader substitution.
    missing_fallback_eye = EyeMidgrayCmds(texture_directory)
    missing_fallback_eye.node_types["EyeMat"] = "unknown"
    missing_fallback_eye.values["EyeColor.fileTextureName"] = str(texture_directory / "missing-native-color.png")
    missing_fallback_before = missing_fallback_eye.snapshot()
    missing_fallback_controller = controller_for(missing_fallback_eye, [missing_fallback_eye.EYE_LEFT])
    try:
        missing_fallback_controller.apply()
    except RuntimeError as exc:
        assert "texture" in str(exc).lower()
    else:
        raise AssertionError("A missing fallback texture was accepted.")
    assert missing_fallback_eye.snapshot() == missing_fallback_before
    assert not missing_fallback_controller.created_nodes

    # A failed authored SG restore cannot advertise a successful fallback capture.
    failed_fallback_eye = EyeMidgrayCmds(texture_directory)
    failed_fallback_eye.node_types["EyeMat"] = "unknown"
    failed_fallback_eye.fail_restore_target = "eyeOnlySG.surfaceShader"
    failed_fallback_controller = controller_for(failed_fallback_eye, [failed_fallback_eye.EYE_LEFT])
    failed_fallback_controller.apply()
    retained_fallback_nodes = list(failed_fallback_controller.created_nodes)
    try:
        failed_fallback_controller.finish()
    except RuntimeError as exc:
        assert "restore" in str(exc).lower()
    else:
        raise AssertionError("An unrestored authored eye SG was accepted.")
    assert not failed_fallback_controller.report["restore_ok"]
    assert not failed_fallback_controller.report["eye_materials_preserved"]
    assert failed_fallback_controller.report["temporary_nodes_retained_on_restore_failure"]
    assert all(node in failed_fallback_eye.node_types for node in retained_fallback_nodes)

    # A failed membership restore keeps the temporary body shader alive and
    # cannot publish a sidecar claiming that eye assignments restored exactly.
    eye_restore_failure = EyeMidgrayCmds(texture_directory, fail_membership_restore=True)
    eye_restore_controller = controller_for(eye_restore_failure, [eye_restore_failure.EYE_RIGHT, eye_restore_failure.BODY])
    eye_restore_controller.apply()
    retained = list(eye_restore_controller.created_nodes)
    try:
        eye_restore_controller.finish()
    except RuntimeError as exc:
        assert "restore" in str(exc).lower()
    else:
        raise AssertionError("Failed shared eye/body restoration was accepted.")
    assert eye_restore_controller.report["restore_ok"] is False
    assert eye_restore_controller.report["eye_assignments_preserved"] is False
    assert all(node in eye_restore_failure.node_types for node in retained)
    assert not set(retained).intersection(eye_restore_failure.deleted)


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
assert viewport.values["defaultRenderGlobals.imageFormat"] == 32
assert viewport.values["defaultRenderGlobals.animation"] == 0
assert viewport.values["defaultRenderGlobals.putFrameBeforeExt"] == 1
assert viewport.values["defaultRenderGlobals.extensionPadding"] == 6
for attribute in ("ssaoEnable", "shadows", "bloomEnable", "motionBlurEnable",
                  "renderDepthOfField", "hwFogEnable", "xrayMode"):
    assert viewport.values["hardwareRenderingGlobals." + attribute] == 0
# Native enum values may vary across supported Maya releases.
viewport.render_mode_labels = "Wire=0:Textured=4:Smooth Shaded=7"
runner._set_viewport_render_options(preserve_authored_look=True, original_lambert_mode=True)
assert viewport.values["hardwareRenderingGlobals.renderMode"] == 7
# Preserved eye inputs require textured VP2 capture; body shading remains the
# verified midgray Lambert even when the global capture mode is textured.
eye_viewport = MidgrayCmds()
eye_viewport.render_mode_labels = "Wire=0:Textured=4:Smooth Shaded=7"
runner.cmds = eye_viewport
eye_options = runner._set_viewport_render_options(
    preserve_authored_look=True, original_lambert_mode=True, original_eye_textures=True,
)
assert eye_viewport.values["hardwareRenderingGlobals.renderMode"] == 4
assert eye_options["textured_render_mode_verified"] is True
assert eye_options["solid_render_mode_verified"] is False
assert eye_options["default_lighting_verified"] is True
assert eye_options["soft_shading_verified"] is True
# Observed Maya 2027 labels use "Shaded And Textured", not "Textured".
eye_viewport.render_mode_labels = "Wire:Shaded:Wire On Shaded:Default Material:Shaded And Textured:Wire On Shaded And Textured:Bounding Box"
native_eye_options = runner._set_viewport_render_options(
    preserve_authored_look=True, original_lambert_mode=True, original_eye_textures=True,
)
assert eye_viewport.values["hardwareRenderingGlobals.renderMode"] == 4
assert native_eye_options["textured_render_mode_verified"] is True
assert native_eye_options["solid_render_mode_verified"] is False
native_body_options = runner._set_viewport_render_options(
    preserve_authored_look=True, original_lambert_mode=True,
)
assert eye_viewport.values["hardwareRenderingGlobals.renderMode"] == 1
assert native_body_options["solid_render_mode_verified"] is True
assert native_body_options["textured_render_mode_verified"] is False

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
    "textured_render_mode_verified": False,
    "soft_shading_verified": True,
}
assert picker._original_material_report_is_valid(valid_report)
for field, value in (
    ("profile", "per_source_material_lambert_texture_preserving_v1"),
    ("profile", "maya-midgray-solid-studio-v1"),
    ("profile", "maya-midgray-solid-studio-v2"),
    ("profile", "maya-midgray-solid-studio-v3"),
    ("requested", False), ("status", "applied"), ("restore_ok", False),
    ("base_color", [0.4, 0.5, 0.5]), ("diffuse", 0.9),
    ("fill_color", [0.0, 0.0, 0.0]), ("soft_shading_verified", False),
    ("authored_materials_ignored", False), ("textures_ignored", False),
    ("opaque_surface_verified", False), ("default_lighting_verified", False),
    ("solid_render_mode_verified", False), ("shading_group_membership_preserved", False),
    ("temporary_lambert_count", 2), ("temporary_lambert_count", True),
    ("contributing_shading_engine_count", 6), ("swapped_shading_engine_count", 6),
    ("temporary_nodes_retained_on_restore_failure", True),
    ("authored_material_ignore_scope", "all_surfaces"),
    ("eye_materials_preserved", False), ("eye_assignments_preserved", False),
    ("eye_dependency_preflight_passed", False), ("eye_textures_enabled", True),
    ("preserved_eye_shape_count", True), ("preserved_eye_component_count", True),
    ("preserved_eye_component_count", 1), ("eye_texture_dependency_count", 1),
    ("preserved_eye_shading_engine_count", 1),
    ("split_shading_engine_count", 1), ("split_body_member_count", 1),
    ("eye_missing_texture_dependency_count", 1), ("eye_unavailable_plugin_dependency_count", 1),
):
    invalid = copy.deepcopy(valid_report)
    invalid[field] = value
    assert not picker._original_material_report_is_valid(invalid), (field, value)

valid_eye_report = {**eye_restored, **eye_options}
assert picker._original_material_report_is_valid(valid_eye_report)
for field, value in (
    ("eye_textures_enabled", False), ("eye_materials_preserved", False),
    ("eye_assignments_preserved", False), ("eye_dependency_preflight_passed", False),
    ("solid_render_mode_verified", True), ("textured_render_mode_verified", False),
    ("preserved_eye_shape_count", 0), ("preserved_eye_shading_engine_count", 0),
    ("split_shading_engine_count", 0), ("split_body_member_count", 0),
    ("eye_missing_texture_dependency_count", 1), ("eye_unavailable_plugin_dependency_count", 1),
    ("temporary_lambert_count", 0), ("contributing_shading_engine_count", 4),
    ("inspected_shading_engine_count", 2),
):
    invalid_eye_report = dict(valid_eye_report, **{field: value})
    assert not picker._original_material_report_is_valid(invalid_eye_report), (field, value)

# Validate the report produced by the actual fallback controller, then corrupt
# its evidence. A profile/flag alone cannot turn an unavailable shader into proof.
valid_fallback_report = {**fallback_restored, **eye_options}
assert picker._original_material_report_is_valid(valid_fallback_report)
for key in (
    "eye_fallback_policy", "eye_fallback_applied", "eye_fallback_verified",
    "eye_fallback_records", "eye_fallback_shading_engine_count", "eye_fallback_shape_count",
    "eye_fallback_material_count", "eye_fallback_texture_connection_count",
):
    for valid in (valid_report, valid_fallback_report):
        missing = copy.deepcopy(valid)
        missing.pop(key)
        assert not picker._original_material_report_is_valid(missing), key
for field, value in (
    ("eye_fallback_policy", "unverified_gray_eye"), ("eye_fallback_applied", False),
    ("eye_fallback_verified", False), ("eye_fallback_verified", 1),
    ("restore_ok", False), ("eye_materials_preserved", False),
    ("eye_assignments_preserved", False), ("eye_dependency_preflight_passed", False),
    ("eye_missing_texture_dependency_count", 1), ("eye_unavailable_plugin_dependency_count", 0),
    ("eye_fallback_shading_engine_count", 1), ("eye_fallback_shape_count", 1),
    ("eye_fallback_material_count", 2), ("eye_fallback_texture_connection_count", 3),
    ("eye_fallback_shading_engine_count", True), ("eye_fallback_shape_count", -1),
    ("eye_fallback_records", []), ("eye_unavailable_plugin_nodes", []),
):
    invalid = copy.deepcopy(valid_fallback_report)
    invalid[field] = value
    assert not picker._original_material_report_is_valid(invalid), (field, value)
for field, value in (
    ("source_shader_plug", "EyeMat"), ("source_shader_plug", ".outColor"),
    ("source_shader_plug", "EyeMat."), ("native_shader", "EyeMat"),
    ("native_shader", "NativeLambert.outColor"), ("reason", "generic_default"),
    ("color_mode", "renderer_gray"), ("color_source", ""),
    ("color_value", [0.5, float("nan"), 0.5]), ("color_value", [True, 0.5, 0.5]),
    ("texture_connection_count", 0), ("texture_connection_count", True),
    ("affected_shapes", []), ("affected_shapes", [EyeMidgrayCmds.EYE_LEFT] * 2),
    ("unavailable_plugin_nodes", []),
):
    invalid = copy.deepcopy(valid_fallback_report)
    invalid["eye_fallback_records"][0][field] = value
    assert not picker._original_material_report_is_valid(invalid), (field, value)
# Duplicate SGs, inconsistent plug-in unions and native shaders that are still
# the declared unavailable node must also be rejected.
invalid = copy.deepcopy(valid_fallback_report)
invalid["eye_fallback_records"][1]["shading_engine"] = invalid["eye_fallback_records"][0]["shading_engine"]
assert not picker._original_material_report_is_valid(invalid)
for field, value in (("state", "available"), ("plugin", None), ("real_class", None)):
    invalid = copy.deepcopy(valid_fallback_report)
    invalid["eye_fallback_records"][0]["unavailable_plugin_nodes"][0][field] = value
    assert not picker._original_material_report_is_valid(invalid), field
invalid = copy.deepcopy(valid_fallback_report)
invalid["eye_unavailable_plugin_nodes"][0]["real_class"] = "DifferentRendererClass"
assert not picker._original_material_report_is_valid(invalid)
invalid = copy.deepcopy(valid_fallback_report)
invalid["eye_fallback_records"][0]["native_shader"] = "EyeMat"
assert not picker._original_material_report_is_valid(invalid)
for field, value in (("eye_fallback_applied", True), ("eye_fallback_verified", True),
                     ("eye_fallback_material_count", 1), ("eye_fallback_records", valid_fallback_report["eye_fallback_records"]),
                     ("eye_unavailable_plugin_nodes", valid_fallback_report["eye_unavailable_plugin_nodes"])):
    invalid = copy.deepcopy(valid_report)
    invalid[field] = value
    assert not picker._original_material_report_is_valid(invalid), field

# Keeping the report profile for saved-workflow compatibility must not reuse
# an old name-based Original cache. Invalidation is read-only and never deletes
# the user's prior validated MP4 or its sidecar.
with tempfile.TemporaryDirectory(prefix="hmb-aipicker-cache-") as cache_dir:
    cache_root = Path(cache_dir)
    cache_scene = cache_root / "asset.mb"
    cache_scene.write_bytes(b"scene-cache-fixture")
    cache_state = picker._default_widget_state()
    cache_state.update(scene_path=str(cache_scene), scene_request_path=str(cache_scene),
                       selected_camera="|shotCam", camera="|shotCam", start_frame=1.0,
                       end_frame=2.0, source_fps=24.0, output_width=640, output_height=360,
                       native_metadata={"scene_path": str(cache_scene), "start_frame": 1.0,
                                        "end_frame": 2.0, "fps": 24.0})
    manifest = picker._scene_dependency_manifest_path(cache_scene)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"schema": picker.ORIGINAL_DEPENDENCY_MANIFEST_SCHEMA,
                                   "version": picker.ORIGINAL_DEPENDENCY_MANIFEST_VERSION,
                                   "scene_path": str(cache_scene), "paths": [str(cache_scene)]}), encoding="utf-8")
    cache_state["native_metadata"]["dependency_manifest_path"] = str(manifest)
    cache_fields = picker._original_preview_cache_fields(cache_scene, cache_state)
    assert cache_fields["original_material_pass_source"] == "AIPicker_SET|AIPickerM_SET"
    cache_video, cache_sidecar = picker._original_preview_paths(cache_scene)
    cache_video.parent.mkdir(parents=True, exist_ok=True)
    def cache_box(kind, payload):
        return (8 + len(payload)).to_bytes(4, "big") + kind + payload
    original_cache_bytes = cache_box(b"ftyp", b"isom\x00\x00\x02\x00isom") + cache_box(b"mdat", b"fixture") + cache_box(b"moov", b"meta")
    cache_video.write_bytes(original_cache_bytes)
    new_metadata = {"schema": "hmb-original-playblast", **cache_fields,
                    "assignment_mode": picker.ORIGINAL_LAMBERT_ASSIGNMENT_MODE,
                    "original_material_override_report": copy.deepcopy(valid_report),
                    "accepted_read_dependency_fingerprint": cache_fields["scene_dependency_fingerprint"],
                    "scene_dependency_paths": [str(cache_scene)], "video_size_bytes": len(original_cache_bytes)}
    cache_sidecar.write_text(json.dumps(new_metadata), encoding="utf-8")
    assert picker._original_preview_cache_is_valid(cache_scene, cache_state, cache_video, cache_sidecar)
    for target, missing in (("metadata", True), ("metadata", False), ("report", True), ("report", False)):
        legacy = copy.deepcopy(new_metadata)
        holder = legacy if target == "metadata" else legacy["original_material_override_report"]
        key = "original_material_pass_source" if target == "metadata" else "material_pass_source"
        if missing:
            holder.pop(key, None)
        else:
            holder[key] = "eye_GEO_GRP|eye_GRP"
        serialized = json.dumps(legacy)
        cache_sidecar.write_text(serialized, encoding="utf-8")
        assert not picker._original_preview_cache_is_valid(cache_scene, cache_state, cache_video, cache_sidecar), (target, missing)
        assert cache_video.read_bytes() == original_cache_bytes
        assert cache_sidecar.read_text(encoding="utf-8") == serialized

print("HMB VideoPicker neutral-body/AIPicker_SET authored-material Original regression passed.")
