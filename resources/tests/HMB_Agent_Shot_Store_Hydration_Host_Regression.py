"""Actual SDK saved-property hydration before any deserialize callback.

Only synthetic five-slot authoring state; no saved user file, execution, media,
network request, live desktop engine, or paid render is used.
"""
from __future__ import annotations
import ast
from contextlib import ExitStack
from copy import deepcopy
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
    raise AssertionError("Hydration fixture must not execute or use networking")


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def exercise(engine, folder):
    import HMBAgentLibrary as agents
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowRequest
    from griptape_nodes.exe_types.core_types import ParameterMode
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(item for item in schema.nodes if item.class_name == "HMBAgentLibrary")
    library.register_new_node_type(agents.HMBAgentLibrary, definition.metadata)
    try:
        send(engine, EnsureWorkflowAndFlowRequest(flow_name="SavedAgentHydrationSynthetic"))
        created = send(engine, CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name="HMB_GP_Production",
            node_name="Synthetic Agent", initial_setup=True))
        node = engine.node_manager.get_node_by_name(created.node_name)
        # Older saved builds contain these five now-inert project literals.
        # Accept their exact strings without recreating path access or routing.
        legacy = {
            "project": "  Legacy Project  ", "episode": "old-e201",
            "shot": "old-s003c001__", "projects_root": "Z:/missing/{literal}/never-inspect",
            "project_load_path": "\\\\missing-server\\legacy\\saved.py",
        }
        identities = {}
        for name in legacy:
            parameter = node.get_parameter_by_name(name)
            identities[name] = parameter.element_id
            assert parameter.allowed_modes == {ParameterMode.PROPERTY}
            assert parameter.serializable is True
            assert parameter.allow_variable_substitution is False
            assert all(parameter.ui_options.get(key) is True for key in (
                "hide", "hide_property", "hide_label", "hide_handles"))
            assert not parameter.children
        native_before = node._hmb_native_slot_snapshot()
        route_before = deepcopy(node._hmb_shot_catalog_snapshot)
        editor_before = [(p.name, p.element_id) for p in node._hmb_native_editor_elements]
        with ExitStack() as passive:
            for method in ("_refresh_agent_shot_route", "_refresh_routed_prompt_preview",
                           "_hmb_capture_active_slot", "_hmb_request_shot_store_persist"):
                passive.enter_context(mock.patch.object(node, method, side_effect=deny))
            for initial in (True, False):
                for name, value in legacy.items():
                    send(engine, SetParameterValueRequest(node_name=node.name,
                        parameter_name=name, value=value, initial_setup=initial))
        for _ in range(3):
            node._remove_legacy_hmb_elements()
        node.after_deserialize()
        assert {name: node.parameter_values[name] for name in legacy} == legacy
        assert node._hmb_native_slot_snapshot() == native_before
        assert node._hmb_shot_catalog_snapshot == route_before
        assert [(p.name, p.element_id) for p in node._hmb_native_editor_elements] == editor_before
        assert not (set(legacy) & set(node._hmb_native_slot_snapshot()["values"]))
        assert not (set(legacy) & {p.name for p in node._hmb_native_editor_elements})
        assert not ({"PROJECT", "Task"} & {p.name for p in node.root_ui_element.children})
        for name in legacy:
            parameter = node.get_parameter_by_name(name)
            assert parameter.element_id == identities[name]
            assert parameter.allowed_modes == {ParameterMode.PROPERTY}
            assert all(parameter.ui_options.get(key) is True for key in (
                "hide", "hide_property", "hide_label", "hide_handles"))
        # Capture a genuine native setting/body from the actual Standard Agent.
        for name, value in (("prompt", "Current selected authoring body"),
                            ("additional_context", "Saved selected native context")):
            send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=name, value=value, initial_setup=True))
        active_body = node._hmb_native_slot_snapshot()
        active = "synthetic-channel\x1fsynthetic-shot-2"
        slots = {}
        for key, text in (("__hmb_only__", "Independent authoring body"),
                ("__hmb_default_settings__", ""),
                ("synthetic-channel\x1fsynthetic-shot-1", "First dormant authored body"),
                (active, "Current selected authoring body"),
                ("synthetic-channel\x1fsynthetic-shot-3", "Third dormant authored body"),
                ("synthetic-channel\x1fsynthetic-shot-4", "Fourth dormant authored body"),
                ("synthetic-channel\x1fsynthetic-shot-5", "Fifth dormant authored body")):
            slots[key] = deepcopy(active_body)
            slots[key]["values"]["prompt"] = text
        store = {"schema": agents._AGENT_SHOT_STORE_SCHEMA, "version": 1,
            "manager": True, "editor_expanded": True, "active": active, "slots": slots,
            "results": {"synthetic-channel\x1fsynthetic-shot-1": {"status": "succeeded", "run_id": "saved-synthetic"}},
            "migration_archives": {"Original independent Agent": {"authored": "Preserved archive"}}}
        # Simulate the generated saved build: property initial_setup requests,
        # without relying on after_deserialize (which that path never promises).
        with mock.patch.object(node, "after_deserialize", side_effect=AssertionError("No repair callback")):
            # A first save adds the constructor's empty hidden input to old
            # files. Replaying it is not an authoritative Prompt deletion.
            send(engine, SetParameterValueRequest(node_name=node.name,
                parameter_name=agents._AGENT_SHOT_PROMPT_INPUT_PARAMETER, value="", initial_setup=True))
            assert node.parameter_values["prompt"] == "Current selected authoring body"
            send(engine, SetParameterValueRequest(node_name=node.name,
                parameter_name=agents._AGENT_SHOT_STORE_PARAMETER, value=deepcopy(store), initial_setup=True))
            assert node._hmb_shot_slots == slots
            assert node._hmb_active_slot_key == active
            assert node._hmb_shot_results == store["results"]
            assert node._hmb_agent_migration_archives == store["migration_archives"]
            for _ in range(5):
                send(engine, SetParameterValueRequest(node_name=node.name,
                    parameter_name=agents._AGENT_SHOT_PROMPT_INPUT_PARAMETER, value="", initial_setup=True))
                node._refresh_routed_prompt_preview()
            assert node.parameter_values["prompt"] == "Current selected authoring body"
            assert node._hmb_shot_slots == slots
            assert node._hmb_shot_results == store["results"]
            # The first real live native callback was the desktop loss trigger.
            send(engine, SetParameterValueRequest(node_name=node.name, parameter_name="additional_context",
                value="Saved selected native context", initial_setup=False))
            assert node.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER] == store
            assert node._hmb_shot_slots == slots and node._hmb_active_slot_key == active
            for _ in range(30):
                node._hmb_persist_shot_store()
            assert node.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER] == store
        # User edits still update only the selected UUID after hydration.
        send(engine, SetParameterValueRequest(node_name=node.name, parameter_name="additional_context",
            value="One intentional selected-Shot edit", initial_setup=False))
        edited = deepcopy(store)
        edited["slots"][active]["values"]["additional_context"] = "One intentional selected-Shot edit"
        assert node.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER] == edited
        # An ordinary official property write also repairs an already-loaded
        # older class's raw/cache split, without UI selection or inference.
        send(engine, SetParameterValueRequest(node_name=node.name,
            parameter_name=agents._AGENT_SHOT_STORE_PARAMETER, value=deepcopy(store), initial_setup=False))
        assert node._hmb_shot_slots == slots and node._hmb_active_slot_key == active
        assert node.parameter_values[agents._AGENT_SHOT_STORE_PARAMETER] == store
        # The SDK serializer must still discover the hidden parameters in the
        # UI tree. Replay only their generated literal setters into a new node.
        saved = send(engine, SaveWorkflowRequest(file_name=str(folder / "inert-legacy.py"),
            display_name="Offline Agent legacy property preservation"))
        tree = ast.parse(Path(saved.file_path).read_text(encoding="utf-8"))
        tables = {}
        for assignment in ast.walk(tree):
            if isinstance(assignment, ast.Assign) and isinstance(assignment.value, ast.Dict):
                for target in assignment.targets:
                    if isinstance(target, ast.Name) and "unique_values" in target.id:
                        tables[target.id] = {ast.literal_eval(key): value
                            for key, value in zip(assignment.value.keys, assignment.value.values)}
        serialized = {}
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "SetParameterValueRequest"):
                continue
            keywords = {k.arg:k.value for k in call.keywords}
            name_ast = keywords.get("parameter_name")
            if isinstance(name_ast, ast.Constant) and name_ast.value in legacy:
                value_ast = keywords["value"]
                if isinstance(value_ast, ast.Call):
                    assert isinstance(value_ast.func, ast.Name) and value_ast.func.id == "decode_value"
                    assert len(value_ast.args) == 1 and not value_ast.keywords
                    reference = value_ast.args[0]
                    assert isinstance(reference, ast.Subscript) and isinstance(reference.value, ast.Name)
                    value_ast = tables[reference.value.id][ast.literal_eval(reference.slice)]
                value = ast.literal_eval(value_ast)
                assert isinstance(value, str)  # No workflow code or pickle is executed.
                serialized[name_ast.value] = value
        assert serialized == legacy, serialized
        reopened_name = send(engine, CreateNodeRequest(node_type="HMBAgentLibrary",
            specific_library_name="HMB_GP_Production", node_name="Reopened Legacy Agent", initial_setup=True)).node_name
        reopened = engine.node_manager.get_node_by_name(reopened_name)
        for name, value in serialized.items():
            send(engine, SetParameterValueRequest(node_name=reopened_name,
                parameter_name=name, value=value, initial_setup=True))
        reopened.after_deserialize()
        assert {name: reopened.parameter_values[name] for name in legacy} == legacy
        for name in legacy:
            send(engine, SetParameterValueRequest(node_name=reopened_name,
                parameter_name=name, value="", initial_setup=True))
        reopened._remove_legacy_hmb_elements()
        assert all(reopened.parameter_values[name] == "" for name in legacy)
        print("HMB_AGENT_INERT_LEGACY_PROPERTIES=PASS (five exact saved literals; hidden PROPERTY only; idempotent; native SDK save and literal replay; empty values retained)")
        print("HMB_AGENT_SHOT_STORE_HYDRATION_HOST=PASS (actual SDK initial setup; five slots and selected UUID preserved before first live callback)")
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


def main():
    with tempfile.TemporaryDirectory(prefix="hmb-agent-store-hydration-") as temporary:
        base = Path(temporary)
        overrides = {key: str(base / leaf) for key, leaf in (
            ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
            ("LOCALAPPDATA", "local"), ("APPDATA", "app"), ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"))}
        for directory in overrides.values():
            Path(directory).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket, "create_connection", deny))
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
            except ImportError:
                print("HMB_AGENT_SHOT_STORE_HYDRATION_HOST=SKIP (installed SDK required)")
                return
            import _hmb_shot_routing as routing
            import HMBAgentLibrary as agents
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, lambda *args, **kwargs: False))
            stack.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", deny))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                exercise(engine, base)
        assert ATTEMPTS == []
    print("HMB_AGENT_SHOT_STORE_HYDRATION_EXTERNAL_WORK=0")


if __name__ == "__main__":
    main()
