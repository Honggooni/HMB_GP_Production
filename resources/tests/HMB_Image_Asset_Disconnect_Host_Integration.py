from __future__ import annotations

import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.retained_mode.events.connection_events import (
        CreateConnectionRequest,
        CreateConnectionResultSuccess,
        ListConnectionsForNodeRequest,
        ListConnectionsForNodeResultSuccess,
    )
    from griptape_nodes.retained_mode.events.parameter_events import (
        AddParameterToNodeRequest,
        AddParameterToNodeResultSuccess,
        SetParameterValueRequest,
        SetParameterValueResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
except Exception:
    print("HMB ImageAsset guarded disconnect host integration: SKIP (host unavailable)")
    raise SystemExit(0)

import HMBImageAssetLibrary as asset_library


class ImageSource(asset_library.DataNode):
    def __init__(self, name: str, value: object, output_type: str = "str"):
        super().__init__(name=name)
        asset_library._safe_add_parameter(
            self,
            name="IMAGE_OUT",
            type=output_type,
            output_type=output_type,
            default_value=value,
            allowed_modes=asset_library._mode_set("OUTPUT"),
            settable=False,
            ui_options={"hide_property": True},
        )
        asset_library.set_output(self, "IMAGE_OUT", value)


def register(flow: ControlFlow, node: object) -> None:
    flow.add_node(node)
    GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name


def add_import_slot(target: asset_library.HMBImageAssetLibrary) -> str:
    result = GriptapeNodes.handle_request(
        AddParameterToNodeRequest(
            node_name=target.name,
            parent_container_name=asset_library.IMAGE_IMPORT_PARAMETER,
        )
    )
    assert isinstance(result, AddParameterToNodeResultSuccess), (
        type(result).__name__,
        getattr(result, "result_details", ""),
    )
    return result.parameter_name


def connect(
    source: ImageSource,
    target: asset_library.HMBImageAssetLibrary,
    target_parameter_name: str,
) -> None:
    result = GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=source.name,
            source_parameter_name="IMAGE_OUT",
            target_node_name=target.name,
            target_parameter_name=target_parameter_name,
        )
    )
    assert isinstance(result, CreateConnectionResultSuccess), (
        type(result).__name__,
        getattr(result, "result_details", ""),
    )


def incoming(target: asset_library.HMBImageAssetLibrary) -> list[object]:
    result = GriptapeNodes.handle_request(
        ListConnectionsForNodeRequest(node_name=target.name)
    )
    assert isinstance(result, ListConnectionsForNodeResultSuccess)
    target_names = asset_library._image_import_target_parameter_names(target)
    return [
        edge
        for edge in result.incoming_connections
        if edge.target_parameter_name in target_names
    ]


GriptapeNodes.EventManager().initialize_queue()
stamp = time.time_ns()
flow = ControlFlow(name=f"HMBImageDisconnectFlow_{stamp}")
GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)

image_a = "https://example.test/host-disconnect-a.png"
image_b = "https://example.test/host-disconnect-b.png"
source_a = ImageSource(f"HMBImageSourceA_{stamp}", image_a)
source_b = ImageSource(f"HMBImageSourceB_{stamp}", image_b)
target = asset_library.HMBImageAssetLibrary(name=f"HMBImageTarget_{stamp}")
for item in (source_a, source_b, target):
    register(flow, item)
connect(source_a, target, add_import_slot(target))
connect(source_b, target, add_import_slot(target))
target._apply_import_value([image_a, image_b])
uid_a = asset_library._normalize_import_input(image_a, [])[0][0]["source_uid"]
uid_b = asset_library._normalize_import_input(image_b, [])[0][0]["source_uid"]
initial_incoming = incoming(target)
assert {edge.source_node_name for edge in initial_incoming} == {
    source_a.name,
    source_b.name,
}, [
    (
        edge.source_node_name,
        edge.source_parameter_name,
        edge.target_parameter_name,
    )
    for edge in initial_incoming
]

disconnect_state = target._current_state()
disconnect_state["disconnect_import_uid"] = uid_a
disconnect_result = GriptapeNodes.handle_request(
    SetParameterValueRequest(
        node_name=target.name,
        parameter_name=asset_library.WIDGET_STATE_PARAMETER,
        value=json.dumps(disconnect_state),
        data_type="str",
    )
)
assert isinstance(disconnect_result, SetParameterValueResultSuccess), (
    type(disconnect_result).__name__,
    getattr(disconnect_result, "result_details", ""),
)
assert [edge.source_node_name for edge in incoming(target)] == [source_b.name]
remaining = [
    row["source_uid"]
    for row in target._current_state()["assets"]
    if row["source_kind"] == "user"
]
assert remaining == [uid_b], remaining

compound = ImageSource(
    f"HMBImageCompound_{stamp}",
    [image_a, image_b],
    output_type="list[str]",
)
compound_target = asset_library.HMBImageAssetLibrary(
    name=f"HMBImageCompoundTarget_{stamp}"
)
for item in (compound, compound_target):
    register(flow, item)
connect(compound, compound_target, asset_library.IMAGE_IMPORT_PARAMETER)
compound_target._apply_import_value([image_a, image_b])
compound_state = compound_target._current_state()
compound_state["disconnect_import_uid"] = uid_a
compound_result = GriptapeNodes.handle_request(
    SetParameterValueRequest(
        node_name=compound_target.name,
        parameter_name=asset_library.WIDGET_STATE_PARAMETER,
        value=json.dumps(compound_state),
        data_type="str",
    )
)
assert isinstance(compound_result, SetParameterValueResultSuccess)
assert [edge.source_node_name for edge in incoming(compound_target)] == [compound.name]
compound_after = compound_target._current_state()
assert "multiple images" in compound_after["error"]
assert compound_after["disconnect_import_uid"] == ""
assert {
    row["source_uid"]
    for row in compound_after["assets"]
    if row["source_kind"] == "user"
} == {uid_a, uid_b}


print("HMB ImageAsset guarded disconnect host integration: PASS")
