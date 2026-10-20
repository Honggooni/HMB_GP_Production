"""Actual SDK atomic accordion publication; private synthetic graph, no inference."""
from __future__ import annotations

from collections import Counter
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
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
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


def payload(event):
    return getattr(getattr(event, "wrapped_event", None), "payload", None)


def assert_no_values(document):
    if isinstance(document, dict):
        assert not {"value", "default_value", "ui_options", "trait_ui_options"} & set(document)
        for value in document.values():
            assert_no_values(value)
    elif isinstance(document, list):
        for value in document:
            assert_no_values(value)


def exercise(engine):
    import HMBAgentLibrary as agents
    import HMB_Agent_Shot_Switch_Native_Host_Regression as native
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.node_events import GetAllNodeInfoRequest, SerializeNodeToCommandsRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.serialization.values import decode_value

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(item for item in schema.nodes if item.class_name == "HMBAgentLibrary")
    library.register_new_node_type(agents.HMBAgentLibrary, definition.metadata)
    try:
        native.exercise(engine)
        node = engine.node_manager.get_node_by_name("Private native Agent")
        root = node.root_ui_element
        body = list(node._hmb_native_editor_elements)
        body_ids = [(id(item), item.element_id) for item in body]
        element_ids = {(id(item), item.element_id) for item in root.children}
        parent_ids = {id(item): id(item._parent) for item in root.children}
        connections = engine.flow_manager.get_connections()
        catalog = deepcopy(node._hmb_shot_catalog_snapshot)
        channel = catalog["channel_uuid"]
        template = node._hmb_native_slot_snapshot()
        archived_key = "__hmb_atomic_initial_children__"
        node._hmb_shot_slots[archived_key] = deepcopy(template)
        for number in (4, 5):
            shot = {"shot_uuid": f"{number:08d}-2222-4222-8222-222222222222", "number": number,
                    "name": f"Synthetic {number}", "revision": 1}
            catalog["shots"].append(shot)
        source = engine.node_manager.get_node_by_name("Private synthetic list source")
        own_children = {}
        own_outputs = {}
        for shot in catalog["shots"]:
            number = shot["number"]
            children = {name: node.get_parameter_by_name(name).append_child_parameter()
                        for name in ("tools", "rulesets")}
            for name, child in children.items():
                output_name = f"{name}_source_{number}"
                source.add_parameter(Parameter(name=output_name, type="Tool" if name == "tools" else "str",
                    default_value=None if name == "tools" else f"Own rule {number}", allowed_modes={ParameterMode.OUTPUT}))
                send(engine, CreateConnectionRequest(source_node_name=source.name,
                    source_parameter_name=output_name, target_node_name=node.name,
                    target_parameter_name=child.name, initial_setup=True))
                send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=child.name,
                    value=None if name == "tools" else f"Own rule {number}", initial_setup=True))
            slot = deepcopy(template)
            slot["values"].update(prompt=f"Public prompt {number}", additional_context=f"Own context {number}",
                tools=[], rulesets=[f"Own rule {number}"],
                agent_memory={"runs": [], "fixture_shot": number, "explicit_off": False})
            slot["children"] = {children["tools"].name: None, children["rulesets"].name: f"Own rule {number}"}
            slot["outputs"] = {"output": f"Distinct final output {number}", "logs": f"Own log {number}", "agent": None}
            slot["result"] = {"status": "succeeded", "run_id": f"synthetic-slot-{number}"}
            node._hmb_shot_slots[node._hmb_slot_key(channel, shot["shot_uuid"])] = slot
            node._hmb_shot_results.pop(node._hmb_slot_key(channel, shot["shot_uuid"]), None)
            own_children[number] = children
            own_outputs[number] = slot["outputs"]["output"]
        node._hmb_active_slot_key = archived_key
        edge_ids = set(connections.connections)
        catalog["generation"] += 1
        document = {key: catalog[key] for key in ("channel_uuid", "generation", "shots")}
        catalog["metadata_sha256"] = hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        node._hmb_shot_catalog_snapshot = catalog
        node._hmb_layout_shot_editor()
        prompt_by_uuid = {shot["shot_uuid"]: f"Public prompt {shot['number']}" for shot in catalog["shots"]}
        prompt = SimpleNamespace(_hmb_prompt_shot_document=lambda **identity:
                                 {"visible_prompt": prompt_by_uuid[identity["shot_uuid"]]})
        measurements = []
        original_put = engine.event_manager.put_event
        original_add, original_remove = type(root).add_child, type(root).remove_child
        with mock.patch.object(node, "_hmb_manager_prompt_owner", return_value=prompt):
            def select(number, *, expanded=True):
                row_name = agents._AGENT_SHOT_ROW_PREFIX + str(number)
                row = deepcopy(node.get_parameter_value(row_name))
                row["action"] = {"kind": "select", "request_id": uuid4().hex, "expanded": expanded}
                send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=row_name, value=row))

            def assert_own_slots():
                assert len(set(own_outputs.values())) == 5
                for shot in catalog["shots"]:
                    number = shot["number"]
                    slot = node._hmb_shot_slots[node._hmb_slot_key(channel, shot["shot_uuid"])]
                    assert slot["outputs"]["output"] == own_outputs[number]
                    assert slot["values"]["additional_context"] == f"Own context {number}"
                    assert slot["values"]["agent_memory"]["fixture_shot"] == number
                    assert slot["values"]["agent_memory"]["explicit_off"] is False
                    assert set(slot["children"]) == {child.name for child in own_children[number].values()}
                    assert slot["children"][own_children[number]["rulesets"].name] == f"Own rule {number}"
                    assert node._hmb_agent_shot_preview(channel_uuid=channel, shot_uuid=shot["shot_uuid"])["text"] == own_outputs[number]

            for number in (1, 2, 3, 4, 5, 4, 3, 2, 1, 3, 5, 3, 5):
                events = []
                counts = Counter()
                def put(event):
                    events.append(event)
                    return original_put(event)
                def add(owner, *args, **kwargs):
                    if owner is root:
                        counts["root_add"] += 1
                    return original_add(owner, *args, **kwargs)
                def remove(owner, *args, **kwargs):
                    if owner is root:
                        counts["root_remove"] += 1
                    return original_remove(owner, *args, **kwargs)
                row_name = agents._AGENT_SHOT_ROW_PREFIX + str(number)
                with mock.patch.object(engine.event_manager, "put_event", put), \
                     mock.patch.object(type(root), "add_child", add), mock.patch.object(type(root), "remove_child", remove):
                    select(number)
                structures = [value for event in events if type(value := payload(event)).__name__ == "AlterElementEvent"
                              and value.element_details.get("element_id") == root.element_id]
                assert len(structures) == 1
                assert counts["root_add"] == counts["root_remove"] == 0
                assert not [event for event in events if type(payload(event)).__name__ == "RemoveElementEvent"]
                assert_no_values(structures[0].element_details["children"])
                names = [item.name for item in root.children]
                index = names.index(row_name)
                assert root.children[index + 1:index + 1 + len(body)] == body
                if number < 5:
                    assert names[index + 1 + len(body)] == agents._AGENT_SHOT_ROW_PREFIX + str(number + 1)
                assert body_ids == [(id(item), item.element_id) for item in node._hmb_native_editor_elements]
                assert element_ids == {(id(item), item.element_id) for item in root.children}
                assert parent_ids == {id(item): id(item._parent) for item in root.children}
                assert edge_ids == set(connections.connections)
                assert node.parameter_output_values["output"] == own_outputs[number]
                assert node._native_parameter_value("additional_context") == f"Own context {number}"
                assert node._hmb_slot_list_children("tools") == [own_children[number]["tools"]]
                assert node._hmb_slot_list_children("rulesets") == [own_children[number]["rulesets"]]
                for name, child in own_children[number].items():
                    incoming = connections.get_incoming_connections_to_parameter(node, child)
                    assert len(incoming) == 1 and incoming[0].source_parameter.name == f"{name}_source_{number}"
                assert_own_slots()
                measurements.append({"shot": number, "root_remove": 0, "root_add": 0, "structural_alter": 1,
                                     "all_execution_events": len(events)})
            for number in range(1, 6):
                events = []
                with mock.patch.object(engine.event_manager, "put_event", side_effect=lambda event: (events.append(event), original_put(event))[-1]):
                    select(number, expanded=False)
                    assert not node._hmb_shot_editor_expanded
                    assert all(item.ui_options.get("hide") is True for item in body)
                    select(number, expanded=True)
                    assert node._hmb_shot_editor_expanded
                assert not [event for event in events if type(payload(event)).__name__ == "RemoveElementEvent"]
                assert node.parameter_output_values["output"] == own_outputs[number]
                assert_own_slots()
            select(1)
            assert_own_slots()
        # The fixed root descriptors preserve values if a native stream writes
        # after order capture but before the structural message is enqueued.
        before = list(root.children)
        desired = list(reversed(before))
        events = []
        original_track = root.track_change
        added_child = []
        def track(key, value):
            original_track(key, value)
            if key == "children":
                node.parameter_output_values["output"] = "Concurrent native output"
                # Structural publication must not replay a stale snapshot of
                # a native list that gained a child after root order capture.
                added_child.append(node.get_parameter_by_name("rulesets").append_child_parameter())
                assert all("children" not in item for item in value)
        with mock.patch.object(root, "track_change", track), \
             mock.patch.object(engine.event_manager, "put_event", side_effect=lambda event: (events.append(event), original_put(event))[-1]):
            assert node._hmb_publish_editor_element_order(desired) is True
        assert node.parameter_output_values["output"] == "Concurrent native output"
        assert len(added_child) == 1 and node.get_parameter_by_name(added_child[0].name) is added_child[0]
        output_events = [value.element_details for event in events
                         if type(value := payload(event)).__name__ == "AlterElementEvent"
                         and value.element_details.get("parameter_name") == "output"]
        assert any(value.get("value") == "Concurrent native output" for value in output_events)
        assert_no_values(root.get_changes().get("children", []))
        node._hmb_publish_editor_element_order(before)
        # Exact no-op, rejected stale memberships and deleted callbacks emit no
        # event and never fall through to the expensive remove/add path.
        with mock.patch.object(engine.event_manager, "put_event") as put:
            assert node._hmb_publish_editor_element_order(list(root.children)) is False
            for invalid in (before[:-1], [before[0], *before[:-1]]):
                try:
                    node._hmb_publish_editor_element_order(invalid)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Stale or duplicated membership was accepted")
            node._hmb_node_deleted = True
            assert node._hmb_publish_editor_element_order(desired) is False
            node._hmb_node_deleted = False
            put.assert_not_called()
        # A host without either publication API must fail before changing its
        # local tree, rather than claim delivery after an unbroadcast mutation.
        unsupported = object.__new__(agents.HMBAgentLibrary)
        unsupported._hmb_node_deleted = False
        unsupported.root_ui_element = SimpleNamespace(children=list(before))
        unsupported.reorder_elements = None
        try:
            unsupported._hmb_publish_editor_element_order(desired)
        except RuntimeError as error:
            assert "publication is unavailable" in str(error)
        else:
            raise AssertionError("Missing publication capability claimed success")
        assert unsupported.root_ui_element.children == before
        # A failed publish restores the authoritative order and keeps a bounded
        # rollback snapshot; no success is claimed or fallback reparent tried.
        with mock.patch.object(node, "emit_parameter_changes", side_effect=RuntimeError("Synthetic publish failure")):
            try:
                node._hmb_publish_editor_element_order(desired)
            except RuntimeError:
                pass
            else:
                raise AssertionError("A failed publication claimed success")
        assert root.children == before
        assert root.get_changes()["children"] == node._hmb_editor_structure(before)
        node.emit_parameter_changes()
        # Editor GetAll and the actual SDK serializer see the same authoritative
        # order/active UUID. Serialization does not alter the live tree or edges.
        info = send(engine, GetAllNodeInfoRequest(node_name=node.name))
        assert [item["element_id"] for item in info.root_node_element["children"]] == [item.element_id for item in before]
        saved_rulesets = next(item for item in info.root_node_element["children"] if item.get("name") == "rulesets")
        assert added_child[0].element_id in {item["element_id"] for item in saved_rulesets["children"]}
        pool = {}
        saved = send(engine, SerializeNodeToCommandsRequest(node_name=node.name,
            unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True))
        values = {indirect.set_parameter_value_command.parameter_name: decode_value(deepcopy(pool[indirect.unique_value_uuid]))
                  for indirect in saved.set_parameter_value_commands}
        assert values[agents._AGENT_WIDGET_PARAMETER]["shot"]["shot_uuid"] == catalog["shots"][0]["shot_uuid"]
        assert values[agents._AGENT_SHOT_STORE_PARAMETER]["active"] == node._hmb_active_slot_key
        assert len(values[agents._AGENT_SHOT_STORE_PARAMETER]["slots"]) >= 5
        assert root.children == before and edge_ids == set(connections.connections)
        print("HMB_AGENT_ATOMIC_ACCORDION_MEASUREMENTS=" + json.dumps(measurements))
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-agent-atomic-accordion-") as temporary:
        keys = ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY")
        overrides = {key: str(Path(temporary) / key) for key in keys}
        for path in overrides.values():
            Path(path).mkdir()
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            for target, name in ((socket, "create_connection"), (socket.socket, "connect"), (socket, "getaddrinfo")):
                stack.enter_context(mock.patch.object(target, name, deny))
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
            except ImportError:
                print("HMB_AGENT_ATOMIC_ACCORDION_HOST=SKIP (installed SDK required)")
                return
            import HMBAgentLibrary as agents
            import _hmb_shot_routing as routing
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, return_value=False))
            stack.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", deny))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                engine.event_manager.initialize_queue()
                exercise(engine)
        assert ATTEMPTS == []
    print("HMB_AGENT_ATOMIC_ACCORDION_HOST=PASS (one structural event; no remove/add; native outputs, IDs, edges and serialization preserved)")
    print("HMB_AGENT_ATOMIC_ACCORDION_EXTERNAL_WORK=0")


if __name__ == "__main__":
    main()
