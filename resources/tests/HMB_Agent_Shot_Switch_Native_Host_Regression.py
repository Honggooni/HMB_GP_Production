"""Actual Standard Agent Shot switch with stable connected native list children.

Synthetic private engine/profile only. This test never loads a user workflow,
reads policy plaintext, runs a model, or accesses the desktop's retained graph.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(
    Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
ATTEMPTS = []


def deny(*args, **kwargs):
    ATTEMPTS.append(True)
    raise AssertionError("No provider, execution or external I/O is permitted")


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def exercise(engine):
    import HMBAgentLibrary as agents
    from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    send(engine, EnsureWorkflowAndFlowRequest(flow_name="PrivateNativeAgentSwitch"))
    flow = engine.flow_manager.get_flow_by_name("PrivateNativeAgentSwitch")
    node = agents.HMBAgentLibrary(name="Private native Agent")
    node.metadata.update(library="HMB_GP_Production", node_type="HMBAgentLibrary")
    source = agents.DataNode(name="Private synthetic list source")
    source.add_parameter(Parameter(name="ruleset_text", type="str", default_value="Synthetic rule", allowed_modes={ParameterMode.OUTPUT}))
    source.add_parameter(Parameter(name="tool_state", type="Tool", default_value=None, allowed_modes={ParameterMode.OUTPUT}))
    for item in (node, source):
        flow.add_node(item)
        engine.object_manager.add_object_by_name(item.name, item)
        engine.node_manager._name_to_parent_flow_name[item.name] = flow.name
    children = {key: node.get_parameter_by_name(key).append_child_parameter()
                for key in ("tools", "rulesets")}
    for name, child in children.items():
        send(engine, CreateConnectionRequest(source_node_name=source.name,
            source_parameter_name="tool_state" if name == "tools" else "ruleset_text",
            target_node_name=node.name, target_parameter_name=child.name, initial_setup=True))
    child_ids = {name: (id(child), child.element_id, child.name) for name, child in children.items()}
    connections = engine.flow_manager.get_connections()
    edge_ids = set(connections.connections)
    body_ids = [(id(item), item.element_id) for item in node._hmb_native_editor_elements]
    channel = "11111111-1111-4111-8111-111111111111"
    shots = [{"shot_uuid": f"{number:08d}-2222-4222-8222-222222222222", "number": number,
              "name": f"Synthetic {number}", "revision": 1} for number in range(1, 4)]
    document = {"channel_uuid": channel, "generation": 1, "shots": shots}
    node._hmb_shot_catalog_snapshot = {"schema": "hmb-shot-routing-catalog", "version": 1,
        "publisher_instance_uuid": "33333333-3333-4333-8333-333333333333", **document,
        "metadata_sha256": hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}
    template = node._hmb_native_slot_snapshot()
    model_choices = node._provider._model_access.model_choices
    assert len(model_choices) > 1
    model = next(value for value in model_choices if value != node._native_parameter_value("model"))
    for shot in shots:
        slot = deepcopy(template)
        slot["values"]["model_provider"] = "griptape_cloud"
        slot["values"]["model"] = model
        slot["values"]["additional_context"] = "Same native settings"
        slot["values"]["include_details"] = False
        slot["values"]["agent_memory"] = {"runs": [], "explicit_zero": 0, "explicit_off": False}
        slot["outputs"]["output"] = f"Exact result {shot['number']}"
        node._hmb_shot_slots[node._hmb_slot_key(channel, shot["shot_uuid"])] = slot
    # A saved third-party provider can return to the actual Cloud provider.
    # The native callback resets its dependent model choices/default; the
    # desired model equal to the pre-change value must still be restored.
    node.parameter_values["model_provider"] = "synthetic-former-provider"
    node.parameter_values["model"] = model
    node._hmb_active_slot_key = node._hmb_slot_key(channel, shots[0]["shot_uuid"])
    with mock.patch.object(node._provider, "on_provider_changed", wraps=node._provider.on_provider_changed) as changed:
        node._hmb_switch_native_slot(channel, shots[1]["shot_uuid"])
        changed.assert_called_once_with("griptape_cloud")
        assert node._native_parameter_value("model") == model
        assert node._native_parameter_value("include_details") is False
        assert node._native_parameter_value("agent_memory")["explicit_zero"] == 0
        assert type(node._native_parameter_value("agent_memory")["explicit_zero"]) is int
        assert node._native_parameter_value("agent_memory")["explicit_off"] is False
        changed.reset_mock()
        node._hmb_switch_native_slot(channel, shots[2]["shot_uuid"])
        changed.assert_not_called()
    assert child_ids == {name: (id(child), child.element_id, child.name) for name, child in children.items()}
    assert set(connections.connections) == edge_ids
    for name, child in children.items():
        assert node.get_parameter_by_name(child.name) is child
        assert len(connections.get_incoming_connections_to_parameter(node, child)) == 1
    assert body_ids == [(id(item), item.element_id) for item in node._hmb_native_editor_elements]
    for index in (1, 2):
        preview = node._hmb_agent_shot_preview(channel_uuid=channel, shot_uuid=shots[index]["shot_uuid"])
        assert preview["text"] == f"Exact result {index + 1}"
    # An obsolete browser row must receive a bounded canonical rejection,
    # without replacing the successful ACK or touching native selection/Run.
    node.parameter_values[agents._AGENT_WIDGET_PARAMETER] = node._hmb_widget_value(
        {"channel_uuid": channel, **shots[2]}, node._hmb_shot_catalog_snapshot)
    node._hmb_row_action_ack = {node._hmb_slot_key(channel, shots[1]["shot_uuid"]): "a" * 32}
    node._hmb_layout_shot_editor()
    active = node._hmb_active_slot_key
    values = deepcopy({key: node._native_parameter_value(key) for key in agents._AGENT_NATIVE_SETTING_KEYS})
    row_name = agents._AGENT_SHOT_ROW_PREFIX + "2"
    row = deepcopy(node.get_parameter_value(row_name))
    row["shot"]["channel_uuid"] = "stale-channel"
    row["action"] = {"kind": "run_selected", "request_id": "b" * 32}
    request = SetParameterValueRequest(node_name=node.name, parameter_name=row_name, value=row)
    request.broadcast_result = False
    rejected = engine.handle_request(request)
    assert not rejected.succeeded()
    canonical = node.get_parameter_value(row_name)
    assert canonical["request_id"] == "a" * 32
    assert canonical["rejected_request_id"] == "b" * 32
    assert canonical["error_code"] == "SHOT_IDENTITY_UNAVAILABLE"
    assert canonical["shot"]["channel_uuid"] == channel and canonical["selected"] is False
    assert node._hmb_active_slot_key == active
    assert values == {key: node._native_parameter_value(key) for key in agents._AGENT_NATIVE_SETTING_KEYS}
    assert not node._hmb_shot_workers


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-agent-switch-native-") as temporary:
        base = Path(temporary)
        keys = ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY")
        overrides = {key: str(base / key) for key in keys}
        for path in overrides.values():
            Path(path).mkdir()
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket, "create_connection", deny))
            stack.enter_context(mock.patch.object(socket.socket, "connect", deny))
            stack.enter_context(mock.patch.object(socket, "getaddrinfo", deny))
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
            except ImportError:
                print("HMB_AGENT_SHOT_SWITCH_NATIVE_HOST=SKIP (installed SDK required)")
                return
            import _hmb_shot_routing as routing
            import HMBAgentLibrary as agents
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, return_value=False))
            stack.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", deny))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                engine.event_manager.initialize_queue()
                exercise(engine)
        assert ATTEMPTS == []
    print("HMB_AGENT_SHOT_SWITCH_NATIVE_HOST=PASS (native provider hooks, exact previews, connected child UID and edge preservation)")
    print("HMB_AGENT_SHOT_SWITCH_EXTERNAL_WORK=0")


if __name__ == "__main__":
    main()
