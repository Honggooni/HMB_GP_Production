"""Actual SDK saved-property hydration before any deserialize callback.

Only synthetic five-slot authoring state; no saved user file, execution, media,
network request, live desktop engine, or paid render is used.
"""
from __future__ import annotations
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


def exercise(engine):
    import HMBAgentLibrary as agents
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(item for item in schema.nodes if item.class_name == "HMBAgentLibrary")
    library.register_new_node_type(agents.HMBAgentLibrary, definition.metadata)
    try:
        send(engine, EnsureWorkflowAndFlowRequest(flow_name="SavedAgentHydrationSynthetic"))
        created = send(engine, CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name="HMB_GP_Production",
            node_name="Synthetic Agent", initial_setup=True))
        node = engine.node_manager.get_node_by_name(created.node_name)
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
                ("synthetic-channel\x1fsynthetic-shot-3", "Third dormant authored body")):
            slots[key] = deepcopy(active_body)
            slots[key]["values"]["prompt"] = text
        store = {"schema": agents._AGENT_SHOT_STORE_SCHEMA, "version": 1,
            "manager": True, "editor_expanded": True, "active": active, "slots": slots,
            "results": {"synthetic-channel\x1fsynthetic-shot-1": {"status": "succeeded", "run_id": "saved-synthetic"}},
            "migration_archives": {"Original independent Agent": {"authored": "Preserved archive"}}}
        # Simulate the generated saved build: property initial_setup requests,
        # without relying on after_deserialize (which that path never promises).
        with mock.patch.object(node, "after_deserialize", side_effect=AssertionError("No repair callback")):
            send(engine, SetParameterValueRequest(node_name=node.name,
                parameter_name=agents._AGENT_SHOT_STORE_PARAMETER, value=deepcopy(store), initial_setup=True))
            assert node._hmb_shot_slots == slots
            assert node._hmb_active_slot_key == active
            assert node._hmb_shot_results == store["results"]
            assert node._hmb_agent_migration_archives == store["migration_archives"]
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
                exercise(engine)
        assert ATTEMPTS == []
    print("HMB_AGENT_SHOT_STORE_HYDRATION_EXTERNAL_WORK=0")


if __name__ == "__main__":
    main()
