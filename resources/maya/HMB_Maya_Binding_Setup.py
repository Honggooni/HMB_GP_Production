# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds

DATA_NODE = "HMBVideoPickerData"
VALID_COLORS = (
    "Red",
    "Green",
    "Blue",
    "Yellow",
    "Orange",
    "Purple",
    "Pink",
    "Sky Blue",
    "Mint",
    "Beige",
    "Direction Checker",
    "Sky Grid",
    "Floor Grid",
    "Position Pattern",
)
REPEATABLE_COLORS = frozenset((
    "Sky Blue",
    "Mint",
    "Beige",
    "Direction Checker",
    "Sky Grid",
    "Floor Grid",
    "Position Pattern",
))


def _clean(value):
    return str(value or "").strip()


def _allows_repeated_color(value):
    return _clean(value) in REPEATABLE_COLORS


def _long_names(nodes):
    result = []
    for node in nodes or []:
        matches = cmds.ls(node, long=True) or [node]
        for match in matches:
            if match not in result:
                result.append(match)
    return result


def _resolve_exact(node_name):
    name = _clean(node_name)
    if not name:
        raise RuntimeError("Maya node name is empty.")
    matches = cmds.ls(name, long=True) or []
    if not matches and cmds.objExists(name):
        matches = [name]
    matches = sorted(set(matches))
    if not matches:
        raise RuntimeError("Maya node not found: {0}".format(name))
    if len(matches) != 1:
        raise RuntimeError("Maya node name is ambiguous: {0} -> {1}".format(name, matches))
    return matches[0]


def _add_string(node, attribute, value):
    if not cmds.attributeQuery(attribute, node=node, exists=True):
        cmds.addAttr(node, longName=attribute, dataType="string")
    cmds.setAttr(node + "." + attribute, _clean(value), type="string")


def clear_metadata():
    nodes = []
    nodes.extend(cmds.ls("HMBMarkerBinding_*", type="network", long=True) or [])
    nodes.extend(cmds.ls("*:HMBMarkerBinding_*", type="network", long=True) or [])
    if cmds.objExists(DATA_NODE):
        nodes.extend(cmds.ls(DATA_NODE, long=True) or [DATA_NODE])
    nodes.extend(cmds.ls("*:" + DATA_NODE, type="network", long=True) or [])
    for node in sorted(set(nodes), key=lambda item: len(item), reverse=True):
        if cmds.objExists(node):
            if cmds.referenceQuery(node, isNodeReferenced=True):
                raise RuntimeError("Referenced HMB metadata cannot be deleted: {0}".format(node))
            cmds.delete(node)


def create_data_node(clear_existing=True):
    if clear_existing:
        clear_metadata()
    if cmds.objExists(DATA_NODE):
        data_node = DATA_NODE
    else:
        data_node = cmds.createNode("network", name=DATA_NODE)
    if not cmds.attributeQuery("bindings", node=data_node, exists=True):
        cmds.addAttr(data_node, longName="bindings", attributeType="message", multi=True)
    if not cmds.attributeQuery("shotCamera", node=data_node, exists=True):
        cmds.addAttr(data_node, longName="shotCamera", attributeType="message")
    return data_node


def _next_binding_index(data_node):
    indices = cmds.getAttr(data_node + ".bindings", multiIndices=True) or []
    return max(indices) + 1 if indices else 0


def create_binding(root, color, asset_id, display_name="", main_type="", sub_type="", enabled=True, data_node=None):
    root = _resolve_exact(root)
    color = _clean(color)
    asset_id = _clean(asset_id)
    if color not in VALID_COLORS:
        raise RuntimeError("Unsupported marker color: {0}".format(color))
    if not asset_id:
        raise RuntimeError("Asset ID is required.")
    if data_node is None:
        data_node = create_data_node(clear_existing=False)
    data_node = _resolve_exact(data_node)

    for node in cmds.ls("HMBMarkerBinding_*", type="network") or []:
        existing_color = cmds.getAttr(node + ".markerColor") if cmds.objExists(node + ".markerColor") else ""
        existing_asset = cmds.getAttr(node + ".assetId") if cmds.objExists(node + ".assetId") else ""
        roots = (
            _long_names(cmds.listConnections(node + ".subjectRoot", source=True, destination=False) or [])
            if cmds.objExists(node + ".subjectRoot")
            else []
        )
        if existing_color == color and not _allows_repeated_color(color):
            raise RuntimeError("Marker color is already assigned: {0}".format(color))
        if existing_asset == asset_id:
            raise RuntimeError("Asset ID is already assigned: {0}".format(asset_id))
        if root in roots:
            raise RuntimeError("Subject root is already assigned: {0}".format(root))

    index = _next_binding_index(data_node)
    binding = cmds.createNode("network", name="HMBMarkerBinding_{0:02d}".format(index + 1))
    cmds.addAttr(binding, longName="enabled", attributeType="bool", defaultValue=bool(enabled))
    cmds.setAttr(binding + ".enabled", bool(enabled))
    _add_string(binding, "markerColor", color)
    _add_string(binding, "assetId", asset_id)
    _add_string(binding, "displayName", display_name or asset_id)
    cmds.addAttr(binding, longName="subjectRoot", attributeType="message")
    cmds.connectAttr(root + ".message", binding + ".subjectRoot", force=True)
    cmds.connectAttr(binding + ".message", "{0}.bindings[{1}]".format(data_node, index), force=True)
    return binding


def register_camera(camera, data_node=None):
    camera = _resolve_exact(camera)
    if cmds.nodeType(camera) == "camera":
        parents = cmds.listRelatives(camera, parent=True, fullPath=True) or []
        if not parents:
            raise RuntimeError("Camera shape has no transform: {0}".format(camera))
        camera = parents[0]
    shapes = cmds.listRelatives(camera, shapes=True, fullPath=True, type="camera") or []
    if len(shapes) != 1:
        raise RuntimeError("The registered node must contain one camera shape: {0}".format(camera))
    if data_node is None:
        data_node = create_data_node(clear_existing=False)
    data_node = _resolve_exact(data_node)
    existing = cmds.listConnections(data_node + ".shotCamera", source=True, destination=False, plugs=True) or []
    for source in existing:
        try:
            cmds.disconnectAttr(source, data_node + ".shotCamera")
        except Exception:
            pass
    cmds.connectAttr(camera + ".message", data_node + ".shotCamera", force=True)
    return camera


def validate():
    if not cmds.objExists(DATA_NODE):
        raise RuntimeError("HMBVideoPickerData is missing.")
    bindings = cmds.listConnections(DATA_NODE + ".bindings", source=True, destination=False, type="network") or []
    if not bindings:
        raise RuntimeError("No HMB marker bindings are connected.")
    colors = set()
    assets = set()
    roots = set()
    report = []
    for node in sorted(set(bindings)):
        enabled = bool(cmds.getAttr(node + ".enabled")) if cmds.objExists(node + ".enabled") else True
        if not enabled:
            continue
        color = cmds.getAttr(node + ".markerColor") if cmds.objExists(node + ".markerColor") else ""
        asset = cmds.getAttr(node + ".assetId") if cmds.objExists(node + ".assetId") else ""
        root_list = _long_names(
            cmds.listConnections(node + ".subjectRoot", source=True, destination=False) or []
        )
        root = root_list[0] if root_list else ""
        if color not in VALID_COLORS:
            raise RuntimeError("Invalid marker color on {0}: {1}".format(node, color))
        if color in colors and not _allows_repeated_color(color):
            raise RuntimeError("Duplicate marker color: {0}".format(color))
        if not asset or asset in assets:
            raise RuntimeError("Missing or duplicate Asset ID: {0}".format(asset))
        if not root or root in roots:
            raise RuntimeError("Missing or duplicate subject root: {0}".format(root))
        colors.add(color)
        assets.add(asset)
        roots.add(root)
        report.append({"binding": node, "color": color, "asset_id": asset, "root": root})
    camera = _long_names(
        cmds.listConnections(DATA_NODE + ".shotCamera", source=True, destination=False) or []
    )
    if not camera:
        raise RuntimeError("No shot camera is registered.")
    return {"data_node": DATA_NODE, "camera": camera[0], "bindings": report}
