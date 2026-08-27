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
    ) -> None:
        super().__init__("maya.cmds")
        self.fail_target = fail_target
        self.fail_restore_target = fail_restore_target
        self.fail_viewport_attr = fail_viewport_attr
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


fake = FakeMaterialCmds()
runner.cmds = fake
before_members = copy.deepcopy(fake.members)
before_connections = original_connections(fake)
controller = runner._OriginalLambertOverrideController(
    {
        "original_material_override_profile": (
            runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE
        ),
        "_viewport_quality_scope_shapes": list(BASE_SCOPE_SHAPES),
    }
)
applied = controller.apply()
assert applied["temporary_lambert_count"] == 4
assert applied["existing_lambert_count"] == 1
assert applied["swapped_shading_engine_count"] == 5
assert applied["texture_connection_count"] == 3
assert applied["numeric_color_count"] == 1
assert applied["transparency_transfer_count"] == 1
assert fake.members == before_members

red_shader = fake.connections["redSG.surfaceShader"].split(".", 1)[0]
red_shader_2 = fake.connections["redSG2.surfaceShader"].split(".", 1)[0]
blue_shader = fake.connections["blueSG.surfaceShader"].split(".", 1)[0]
solid_shader = fake.connections["solidSG.surfaceShader"].split(".", 1)[0]
alpha_shader = fake.connections["alphaSG.surfaceShader"].split(".", 1)[0]
assert red_shader == red_shader_2
assert len({red_shader, blue_shader, solid_shader, alpha_shader}) == 4
assert fake.connections[red_shader + ".color"] == "redFile.outColor"
assert fake.connections[blue_shader + ".color"] == "blueFile.outColor"
assert fake.connections[alpha_shader + ".color"] == "alphaColorFile.outColor"
assert fake.values[solid_shader + ".color"] == [(0.12, 0.34, 0.56)]
reverse_nodes = [
    node for node, node_type in fake.node_types.items() if node_type == "reverse"
]
assert len(reverse_nodes) == 1
reverse_node = reverse_nodes[0]
assert fake.connections[reverse_node + ".input"] == "alphaMaskFile.outColor"
assert fake.connections[alpha_shader + ".transparency"] == reverse_node + ".output"
assert fake.connections["existingSG.surfaceShader"] == "ExistingLambert.outColor"

restored = controller.finish()
assert restored["restore_ok"] is True
assert restored["status"] == "restored"
assert fake.members == before_members
assert original_connections(fake) == before_connections
assert all(
    not node_type in ("reverse",)
    and not (node_type == "lambert" and node.startswith("HMB_Original_"))
    for node, node_type in fake.node_types.items()
)


# A mid-transaction SG failure must restore every earlier surface connection,
# preserve every component membership and remove all temporary Maya nodes.
failing_fake = FakeMaterialCmds(fail_target="solidSG.surfaceShader")
runner.cmds = failing_fake
failure_members = copy.deepcopy(failing_fake.members)
failure_connections = original_connections(failing_fake)
failing_controller = runner._OriginalLambertOverrideController(
    {
        "original_material_override_profile": (
            runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE
        ),
        "_viewport_quality_scope_shapes": list(BASE_SCOPE_SHAPES),
    }
)
try:
    failing_controller.apply()
except RuntimeError as exc:
    assert "intentional SG swap failure" in str(exc)
else:
    raise AssertionError("The mocked Original Lambert SG failure was not raised.")
assert failing_fake.members == failure_members
assert original_connections(failing_fake) == failure_connections
assert all(
    not node.startswith("HMB_Original_")
    for node in failing_fake.node_types
)


# Only SGs intersecting the accepted Original render scope may be inspected or
# swapped.  An authored but statically hidden/out-of-scope material must remain
# byte-for-byte connected and must not inflate any material report count.
scoped_fake = FakeMaterialCmds()
scoped_fake.node_types.update({
    "OutsideMat": "RedshiftMaterial",
    "outsideFile": "file",
    "outsideSG": "shadingEngine",
})
scoped_fake.members["outsideSG"] = ["meshOutside"]
scoped_fake.connections.update({
    "outsideSG.surfaceShader": "OutsideMat.outColor",
    "OutsideMat.diffuse_color": "outsideFile.outColor",
})
for plug in (
    "OutsideMat.outColor",
    "OutsideMat.diffuse_color",
    "outsideFile.outColor",
):
    scoped_fake.attr_types[plug] = "double3"
runner.cmds = scoped_fake
outside_connection = scoped_fake.connections["outsideSG.surfaceShader"]
scoped_controller = runner._OriginalLambertOverrideController(
    {
        "original_material_override_profile": (
            runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE
        ),
        "_viewport_quality_scope_shapes": list(BASE_SCOPE_SHAPES),
    }
)
scoped_applied = scoped_controller.apply()
assert scoped_applied["inspected_shading_engine_count"] == 6
assert scoped_applied["source_material_count"] == 5
assert scoped_applied["temporary_lambert_count"] == 4
assert scoped_applied["swapped_shading_engine_count"] == 5
assert scoped_fake.connections["outsideSG.surfaceShader"] == outside_connection
assert all("OutsideMat" not in node for node in scoped_controller.created_nodes)
scoped_controller.finish()
assert scoped_fake.connections["outsideSG.surfaceShader"] == outside_connection


# A recognized renderer utility is already evaluable in this Maya process. Keep
# its exact output connection; never silently bypass it to one upstream file.
ambiguous_fake = FakeMaterialCmds()
ambiguous_fake.node_types.update({
    "PluginUtility": "RedshiftColorLayer",
    "utilityFileA": "file",
    "utilityFileB": "file",
})
ambiguous_fake.connections.update({
    "PluginUtility.inputA": "utilityFileA.outColor",
    "PluginUtility.inputB": "utilityFileB.outColor",
})
for plug in (
    "PluginUtility.outColor",
    "PluginUtility.inputA",
    "PluginUtility.inputB",
    "utilityFileA.outColor",
    "utilityFileB.outColor",
):
    ambiguous_fake.attr_types[plug] = "double3"
runner.cmds = ambiguous_fake
assert runner._original_supported_source("PluginUtility.outColor") == (
    "PluginUtility.outColor"
)

loaded_plugin_fake = FakeMaterialCmds()
loaded_plugin_fake.node_types["LoadedCorrection"] = "RedshiftColorCorrection"
loaded_plugin_fake.connections.update({
    "RedMat.base_color": "LoadedCorrection.outColor",
    "LoadedCorrection.input": "redFile.outColor",
})
for plug in ("LoadedCorrection.outColor", "LoadedCorrection.input"):
    loaded_plugin_fake.attr_types[plug] = "double3"
runner.cmds = loaded_plugin_fake
loaded_plugin_controller = runner._OriginalLambertOverrideController({
    "original_material_override_profile": runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
    "_viewport_quality_scope_shapes": list(BASE_SCOPE_SHAPES),
})
loaded_plugin_applied = loaded_plugin_controller.apply()
assert loaded_plugin_applied["loaded_plugin_passthrough_count"] == 1
assert loaded_plugin_applied["plugin_fallback_count"] == 0
assert loaded_plugin_applied["texture_identity_preserved"] is True
loaded_red_shader = loaded_plugin_fake.connections[
    "redSG.surfaceShader"
].split(".", 1)[0]
assert loaded_plugin_fake.connections[loaded_red_shader + ".color"] == (
    "LoadedCorrection.outColor"
)
loaded_plugin_controller.finish()


# A recognized Redshift dependency remains exact, while a real Maya unknown node
# requests a numeric fallback instead of being mislabeled or connected.
for upstream_type, fallback_required in (
    ("RedshiftColorCorrection", False),
    ("unknown", True),
):
    dependent_fake = FakeMaterialCmds()
    dependent_fake.node_types.update({
        "NativeUtility": "multiplyDivide",
        "PluginUpstream": upstream_type,
    })
    dependent_fake.connections[
        "NativeUtility.input1"
    ] = "PluginUpstream.outColor"
    for plug in (
        "NativeUtility.input1",
        "NativeUtility.outColor",
        "PluginUpstream.outColor",
    ):
        dependent_fake.attr_types[plug] = "double3"
    runner.cmds = dependent_fake
    if fallback_required:
        try:
            runner._original_supported_source("NativeUtility.outColor")
        except runner._OriginalPluginFallbackRequired as exc:
            dependency_message = str(exc)
            assert "unavailable plug-in node" in dependency_message
            assert "PluginUpstream" in dependency_message
        else:
            raise AssertionError("An unknown renderer node did not request fallback.")
    else:
        assert runner._original_supported_source("NativeUtility.outColor") == (
            "NativeUtility.outColor"
        )


# Reproduce the reported namespaced rsColorCorrection failure. The material's
# captured value is applied to the disposable Lambert, the Original pass stays
# publishable, and the authored SG graph is restored afterwards.
fallback_fake = FakeMaterialCmds()
fallback_fake.node_types.update({
    "NativeUtility": "multiplyDivide",
    "BlackGoldenBoy:rsColorCorrection7": "unknown",
})
fallback_fake.connections.update({
    "RedMat.base_color": "NativeUtility.outColor",
    "NativeUtility.input1": "BlackGoldenBoy:rsColorCorrection7.outColor",
})
fallback_fake.values["RedMat.base_color"] = [(0.21, 0.31, 0.41)]
for plug in (
    "NativeUtility.input1",
    "NativeUtility.outColor",
    "BlackGoldenBoy:rsColorCorrection7.outColor",
):
    fallback_fake.attr_types[plug] = "double3"
runner.cmds = fallback_fake
fallback_before = original_connections(fallback_fake)
fallback_controller = runner._OriginalLambertOverrideController({
    "original_material_override_profile": runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
    "_viewport_quality_scope_shapes": list(BASE_SCOPE_SHAPES),
})
fallback_applied = fallback_controller.apply()
assert fallback_applied["plugin_fallback_count"] == 1
assert fallback_applied["plugin_fallback_material_count"] == 1
assert fallback_applied["plugin_fallback_node_count"] == 1
assert fallback_applied["numeric_color_count"] == 2
assert fallback_applied["texture_connection_count"] == 2
assert fallback_applied["texture_identity_preserved"] is False
assert "BlackGoldenBoy:rsColorCorrection7" in fallback_applied["warnings"][0]
fallback_red_shader = fallback_fake.connections[
    "redSG.surfaceShader"
].split(".", 1)[0]
assert fallback_fake.values[fallback_red_shader + ".color"] == [
    (0.21, 0.31, 0.41)
]
assert fallback_red_shader + ".color" not in fallback_fake.connections
fallback_finished = fallback_controller.finish()
assert fallback_finished["restore_ok"] is True
assert original_connections(fallback_fake) == fallback_before


# A loaded renderer texture remains the source itself. No filename-only Maya
# file clone is created, so color space, UDIM, UV, and sequence behavior are not
# silently re-authored.
loaded_texture_fake = FakeMaterialCmds()
loaded_texture_fake.node_types["PluginTexture"] = "RedshiftTextureSampler"
loaded_texture_fake.attr_types.update({
    "PluginTexture.outColor": "double3",
    "PluginTexture.texturePath": "string",
    "PluginTexture.description": "string",
})
fallback_texture_path = "C:/textures/hero_diffuse.<UDIM>.png"
loaded_texture_fake.values.update({
    "PluginTexture.texturePath": fallback_texture_path,
    "PluginTexture.description": "hero diffuse source",
})
runner.cmds = loaded_texture_fake
assert runner._original_supported_source("PluginTexture.outColor") == (
    "PluginTexture.outColor"
)
assert not [
    node
    for node, node_type in loaded_texture_fake.node_types.items()
    if node.startswith("HMB_Original_")
    and node_type in ("file", "place2dTexture")
]


# A recognized renderer input on an authored Lambert is evaluable and retained.
existing_lambert_fake = FakeMaterialCmds()
existing_lambert_fake.node_types["HiddenPlugin"] = "RedshiftColorCorrection"
existing_lambert_fake.attr_types.update({
    "ExistingLambert.color": "double3",
    "HiddenPlugin.outColor": "double3",
})
existing_lambert_fake.connections[
    "ExistingLambert.color"
] = "HiddenPlugin.outColor"
runner.cmds = existing_lambert_fake
runner._original_assert_existing_lambert_is_native("ExistingLambert")


# If that same node is genuinely unknown, the authored Lambert is temporarily
# rebuilt with a deterministic numeric color and restored like every other SG.
unknown_lambert_fake = FakeMaterialCmds()
unknown_lambert_fake.node_types["BlackGoldenBoy:rsColorCorrection8"] = "unknown"
unknown_lambert_fake.attr_types.update({
    "ExistingLambert.color": "double3",
    "BlackGoldenBoy:rsColorCorrection8.outColor": "double3",
})
unknown_lambert_fake.connections[
    "ExistingLambert.color"
] = "BlackGoldenBoy:rsColorCorrection8.outColor"
runner.cmds = unknown_lambert_fake
unknown_lambert_before = original_connections(unknown_lambert_fake)
unknown_lambert_controller = runner._OriginalLambertOverrideController({
    "original_material_override_profile": runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
    "_viewport_quality_scope_shapes": list(BASE_SCOPE_SHAPES),
})
unknown_lambert_applied = unknown_lambert_controller.apply()
assert unknown_lambert_applied["existing_lambert_count"] == 0
assert unknown_lambert_applied["temporary_lambert_count"] == 5
assert unknown_lambert_applied["plugin_fallback_count"] == 1
assert unknown_lambert_applied["plugin_fallback_material_count"] == 1
assert unknown_lambert_applied["texture_identity_preserved"] is False
unknown_lambert_controller.finish()
assert original_connections(unknown_lambert_fake) == unknown_lambert_before


# Original must use Maya Default Lighting and smooth shaded/textured Viewport
# 2.0.  Both read-back verifications are mandatory; failure of either setting
# aborts before an Original artifact can be accepted.
viewport_fake = FakeMaterialCmds()
runner.cmds = viewport_fake
viewport_report = runner._set_viewport_render_options(
    preserve_authored_look=True,
    original_lambert_mode=True,
)
assert viewport_report["default_lighting_verified"] is True
assert viewport_report["textured_render_mode_verified"] is True
assert viewport_fake.values["hardwareRenderingGlobals.lightingMode"] == 0
assert viewport_fake.values["hardwareRenderingGlobals.renderMode"] == 4
for viewport_attr in (
    "hardwareRenderingGlobals.lightingMode",
    "hardwareRenderingGlobals.renderMode",
):
    failing_viewport_fake = FakeMaterialCmds(
        fail_viewport_attr=viewport_attr
    )
    runner.cmds = failing_viewport_fake
    try:
        runner._set_viewport_render_options(
            preserve_authored_look=True,
            original_lambert_mode=True,
        )
    except RuntimeError as exc:
        viewport_message = str(exc)
        assert "Original Maya Lambert compatibility" in viewport_message
        assert viewport_attr in viewport_message
    else:
        raise AssertionError(
            "Original did not fail closed when {0} was unverifiable.".format(
                viewport_attr
            )
        )


# If even one authored SG connection cannot be restored, deleting temporary
# nodes would leave that SG disconnected.  Keep every temporary node alive,
# fail the publication, and report the incomplete restoration explicitly.
restore_failing_fake = FakeMaterialCmds(
    fail_restore_target="blueSG.surfaceShader"
)
runner.cmds = restore_failing_fake
restore_controller = runner._OriginalLambertOverrideController(
    {
        "original_material_override_profile": (
            runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE
        ),
        "_viewport_quality_scope_shapes": list(BASE_SCOPE_SHAPES),
    }
)
restore_controller.apply()
temporary_nodes = list(restore_controller.created_nodes)
try:
    restore_controller.finish()
except RuntimeError as exc:
    assert "intentional SG restore failure" in str(exc)
else:
    raise AssertionError("The mocked SG restoration failure was not raised.")
assert restore_controller.report["restore_ok"] is False
assert restore_controller.report["status"] == "restore_failed"
assert all(node in restore_failing_fake.node_types for node in temporary_nodes)
assert not set(temporary_nodes).intersection(restore_failing_fake.deleted)
assert "HMB_Original_" in restore_failing_fake.connections[
    "blueSG.surfaceShader"
]
for group in restore_failing_fake.members:
    source = restore_failing_fake.connections.get(group + ".surfaceShader", "")
    assert source, "A failed restoration must not leave any SG disconnected."
    assert source.split(".", 1)[0] in restore_failing_fake.node_types


# A cached Original is publishable only when its finished material report is a
# self-consistent account of the actual swap.  Boolean success flags alone are
# insufficient because an applied/incomplete or arithmetically impossible
# report would otherwise allow a stale or partially restored artifact.
picker_spec = importlib.util.spec_from_file_location(
    "HMBVideoPickerLibrary_Original_Lambert_Cache_Regression",
    PICKER_PATH,
)
assert picker_spec is not None and picker_spec.loader is not None
picker = importlib.util.module_from_spec(picker_spec)
sys.modules[picker_spec.name] = picker
picker_spec.loader.exec_module(picker)


def mp4_box(box_type: bytes, payload: bytes) -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + box_type + payload


with tempfile.TemporaryDirectory(prefix="HMB_Original_Lambert_Cache_") as root:
    cache_root = Path(root)
    scene_path = cache_root / "shot.mb"
    scene_path.write_bytes(b"Original Lambert cache scene")
    state = picker._default_widget_state()
    state.update({
        "scene_path": str(scene_path),
        "selected_camera": "|shotCam",
        "camera": "|shotCam",
        "start_frame": 1001.0,
        "end_frame": 1002.0,
        "source_fps": 24.0,
        "output_width": 1280,
        "output_height": 720,
        "native_metadata": {
            "scene_path": str(scene_path),
            "start_frame": 1001.0,
            "end_frame": 1002.0,
            "fps": 24.0,
        },
    })
    manifest_path = picker._scene_dependency_manifest_path(scene_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({
            "schema": picker.ORIGINAL_DEPENDENCY_MANIFEST_SCHEMA,
            "version": picker.ORIGINAL_DEPENDENCY_MANIFEST_VERSION,
            "scene_path": str(scene_path),
            "paths": [str(scene_path)],
        }),
        encoding="utf-8",
    )
    state["native_metadata"]["dependency_manifest_path"] = str(manifest_path)
    expected = picker._original_preview_cache_fields(scene_path, state)
    video_path, sidecar_path = picker._original_preview_paths(scene_path)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(
        mp4_box(b"ftyp", b"isom\x00\x00\x02\x00isom")
        + mp4_box(b"mdat", b"lambert")
        + mp4_box(b"moov", b"meta")
    )
    valid_report = {
        "profile": picker.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
        "requested": True,
        "status": "restored",
        "inspected_shading_engine_count": 6,
        "source_material_count": 5,
        "temporary_lambert_count": 4,
        "existing_lambert_count": 1,
        "texture_connection_count": 3,
        "numeric_color_count": 1,
        "loaded_plugin_passthrough_count": 0,
        "loaded_plugin_nodes": [],
        "plugin_fallback_count": 0,
        "plugin_fallback_material_count": 0,
        "plugin_fallback_node_count": 0,
        "plugin_fallback_records": [],
        "texture_identity_preserved": True,
        "warnings": [],
        "transparency_transfer_count": 1,
        "emission_transfer_count": 0,
        "swapped_shading_engine_count": 5,
        "shading_group_membership_preserved": True,
        "one_lambert_per_source_material": True,
        "default_lighting_verified": True,
        "textured_render_mode_verified": True,
        "temporary_nodes_retained_on_restore_failure": False,
        "restore_ok": True,
    }
    metadata = {
        "schema": "hmb-original-playblast",
        **copy.deepcopy(expected),
        "assignment_mode": picker.ORIGINAL_LAMBERT_ASSIGNMENT_MODE,
        "original_material_override_report": valid_report,
        "accepted_read_dependency_fingerprint": expected[
            "scene_dependency_fingerprint"
        ],
        "scene_dependency_paths": [str(scene_path)],
        "video_size_bytes": video_path.stat().st_size,
    }

    def cache_accepts(report: dict[str, Any]) -> bool:
        candidate = copy.deepcopy(metadata)
        candidate["original_material_override_report"] = report
        sidecar_path.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return picker._original_preview_cache_is_valid(
            scene_path,
            state,
            video_path,
            sidecar_path,
        )

    assert cache_accepts(valid_report)
    degraded_report = copy.deepcopy(valid_report)
    degraded_report.update({
        "texture_connection_count": 2,
        "numeric_color_count": 2,
        "plugin_fallback_count": 1,
        "plugin_fallback_material_count": 1,
        "plugin_fallback_node_count": 2,
        "plugin_fallback_records": [{
            "material": "RedMat",
            "attribute": "base_color",
            "source_nodes": ["NativeUtility"],
            "unavailable_nodes": [
                {"node": "BlackGoldenBoy:rsColorCorrection7"},
                {"node": "BlackGoldenBoy:rsColorCorrection8"},
            ],
            "fallback_mode": "captured_numeric",
            "fallback_value": [0.21, 0.31, 0.41],
        }],
        "texture_identity_preserved": False,
        "warnings": ["Original used a numeric plug-in fallback."],
    })
    assert cache_accepts(degraded_report)
    inconsistent_reports = []
    for field, value in (
        ("status", "applied"),
        ("requested", False),
        ("inspected_shading_engine_count", 3),
        ("source_material_count", 6),
        ("temporary_lambert_count", -1),
        ("temporary_lambert_count", True),
        ("texture_connection_count", 2),
        ("swapped_shading_engine_count", 3),
        ("default_lighting_verified", False),
        ("textured_render_mode_verified", False),
        ("temporary_nodes_retained_on_restore_failure", True),
        ("plugin_fallback_material_count", 2),
        ("plugin_fallback_records", [{}]),
        ("texture_identity_preserved", False),
    ):
        invalid = copy.deepcopy(valid_report)
        invalid[field] = value
        inconsistent_reports.append(invalid)
    for invalid_report in inconsistent_reports:
        assert not cache_accepts(invalid_report), invalid_report


print("HMB VideoPicker Original per-material Lambert override regression passed.")
