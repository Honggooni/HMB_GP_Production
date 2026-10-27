"""Keep ordinary legacy editors usable without inventing a Shot publisher."""
from __future__ import annotations

import asyncio
import argparse
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("standalone_migration_fixture",
    ROOT / "resources/tests/HMB_Workflow_Consolidation_Host_Regression.py")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)


def boundary_cases(migration):
    prompt = SimpleNamespace(name="Prompt", metadata={"library": "HMB_GP_Production",
        "node_type": "HMBPromptLibrary"}, _hmb_shot_channel_subscription=lambda: {})
    agent = SimpleNamespace(name="Agent", metadata={"library": "HMB_GP_Production",
        "node_type": "HMBAgentLibrary"})
    groups = {"prompt": [prompt], "agent": [agent], "finish_look": []}
    exports = {"Prompt": {"state": {"shot": {"channel_uuid": "", "shot_uuid": ""}}},
        "Agent": {"active_subscription": {"enabled": False}, "legacy_widget": {}}}
    flow = SimpleNamespace(nodes={"Prompt": prompt, "Agent": agent})
    allowed = lambda: migration._single_standalone_editors(flow, groups, exports)
    assert allowed()
    checks = 1
    # Reject identities in active subscriptions, archived slots and documents;
    # detached editors must not bypass the existing explicit rebind safeguard.
    for field in ("channel_uuid", "shot_uuid", "publisher_instance_uuid", "bound_shot_uuid"):
        for location in ("active_subscription", "legacy_widget", "migration_archives"):
            previous = deepcopy(exports["Agent"])
            exports["Agent"][location] = {"nested": [{field: "saved-identity"}]}
            assert not allowed(), (field, location)
            exports["Agent"] = previous
            checks += 1
    exports["Agent"]["active_subscription"]["enabled"] = True
    assert not allowed()
    exports["Agent"]["active_subscription"]["enabled"] = False
    agent._hmb_manual_rebind = {"required": True}
    assert not allowed()
    del agent._hmb_manual_rebind
    groups["agent"].append(agent)
    assert not allowed()
    groups["agent"].pop()
    flow.nodes["ImageAsset"] = SimpleNamespace(metadata={"library": "HMB_GP_Production",
        "node_type": "HMBImageAssetLibrary"})
    assert not allowed()
    del flow.nodes["ImageAsset"]
    assert not migration._single_standalone_editors(flow,
        {"prompt": [], "agent": [], "finish_look": []}, {})
    assert allowed()
    checks += 6
    identity = "11111111-1111-4111-8111-111111111111\x1f22222222-2222-4222-8222-222222222222"
    for kind, exported in (
        ("agent", {"slots": {identity: {"inputs": {}, "outputs": {}}}}),
        ("agent", {"results": {identity: {"text": "retained"}}}),
        ("agent", {"private_cache": {"slots": {identity: {}}}}),
        ("agent", {"active_slot_key": identity}),
        ("prompt", {"materialized_documents": {identity.replace("\x1f", "/"): "{}"}}),
        ("prompt", {"state": {"shot_documents": {identity.replace("\x1f", "/"): "{}"}}}),
        ("finish_look", {"documents": {identity: {}}}),
        ("finish_look", {"private_cache": {"remote_owners": {identity: "owner"}}}),
    ):
        assert migration._has_saved_editor_store_identity(kind, exported)
        checks += 1
    for kind, exported in (
        ("agent", {"slots": {"__hmb_only__": {}, "__hmb_default_settings__": {}}}),
        ("prompt", {"materialized_documents": {"__unbound__": "{}"}}),
        ("finish_look", {"documents": {"__standalone__": {}}}),
        ("agent", {"native_slot": {"inputs": {"output_schema": {"slots": {identity: {}}}}}}),
    ):
        assert not migration._has_saved_editor_store_identity(kind, exported)
        checks += 1
    # Exact Agent slot payloads are authored data, never ownership authority.
    # The same names in subscriptions, unknown fields or legacy widgets still
    # reject the standalone fast path, even when malformed rather than UUIDs.
    payload = {"values": {"output_schema": {"type": "object", "properties": {
        "shot_uuid": {"type": "string"}, "channel_uuid": {"type": "null"}}}},
        "children": {"shot_uuid": "Authored tool argument"},
        "outputs": {"output": {"shot_uuid": "User result", "channel_uuid": None}}}
    locations = (
        {"native_slot": payload}, {"slots": {"__hmb_only__": payload}},
        {"private_cache": {"slots": {"__hmb_only__": payload}}},
        {"archives": {"source": {"native_slot": payload}}},
        {"archives": {"source": {"original_slots": {"__hmb_only__": payload}}}},
        {"private_cache": {"archives": {"source": {"source_archives": {
            "earlier": {"unbound_slots": {"__hmb_only__": payload}}}}}}},
    )
    for authored in locations:
        previous = deepcopy(exports["Agent"])
        exports["Agent"].update(deepcopy(authored))
        assert migration._has_saved_shot_identity(exports["Agent"])
        assert allowed(), authored
        exports["Agent"] = previous
        checks += 1
    for authority in (
        {"active_subscription": {"shot_uuid": {"type": "string"}}},
        {"legacy_widget": {"native_slot": payload}},
        {"native_slot": {"values": {"shot_uuid": "invalid-but-saved"}}},
        {"native_slot": {"shot_uuid": {"type": "string"}}},
        {"native_slot": {"result": {"shot_uuid": "invalid-but-saved"}}},
        {"unknown": {"native_slot": payload}},
        {"archives": {"source": {"original_slots": {identity: payload}}}},
        {"archives": {"source": {"request_records": [{"shot": {"shot_uuid": "saved"}}]}}},
    ):
        previous = deepcopy(exports["Agent"])
        exports["Agent"].update(deepcopy(authority))
        assert not allowed(), authority
        exports["Agent"] = previous
        checks += 1
    return checks


async def exercise(engine, directory):
    import _hmb_workflow_migration as migration
    import _hmb_shot_routing as routing
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    engine.event_manager.initialize_queue()
    _, _, _, prompts, agents, _ = base.register_library(engine)
    try:
        ensured = base.send(engine, EnsureWorkflowAndFlowRequest(flow_name="LegacyStandalone"))
        flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
        def create(kind, name):
            result = base.send(engine, CreateNodeRequest(node_type=kind,
                specific_library_name="HMB_GP_Production", node_name=name, initial_setup=True))
            return engine.node_manager.get_node_by_name(result.node_name)
        prompt = create("HMBPromptLibrary", "Legacy Prompt")
        state = prompt._hmb_prompt_merge_snapshot()["state"]
        state["multi_shot_enabled"] = False
        state["text"]["PRESERVED_TEXT"] = "Standalone literal {{KEEP}}"
        prompt.set_parameter_value(prompts.WIDGET_PARAMETER_NAME, prompts._json_dumps(state), initial_setup=True)
        agent = create("HMBAgentLibrary", "Legacy Agent")
        agent.set_parameter_value(agents._AGENT_WIDGET_PARAMETER,
            agent._hmb_widget_value(shot_manager=False), initial_setup=True)
        agent.set_parameter_value("prompt", "Existing original prompt", initial_setup=True)
        agent.set_parameter_value("additional_context", "Authored local context", initial_setup=True)
        schema = {"type": "object", "properties": {"shot_uuid": {"type": "string"},
            "channel_uuid": {"type": "null"}}}
        agent.set_parameter_value("output_schema", schema, initial_setup=True)
        agent.parameter_output_values["output"] = {"shot_uuid": "Existing user result", "channel_uuid": None}
        agent.parameter_output_values["logs"] = "Historical result logs"
        base.send(engine, CreateConnectionRequest(source_node_name=prompt.name,
            source_parameter_name="PROMPT_OUT", target_node_name=agent.name,
            target_parameter_name="prompt", initial_setup=True))
        groups, exports = migration._capture_editors(flow)
        assert migration._single_standalone_editors(flow, groups, exports)
        baseline = {name: deepcopy(migration._raw_node_state(node)) for name, node in flow.nodes.items()}
        edges = migration._edge_records(engine, set(flow.nodes))
        identities = {name: id(node) for name, node in flow.nodes.items()}
        # The old path attempted unsupported consolidation even though there is
        # no publisher/Shot ownership, and blocked otherwise valid local work.
        with mock.patch.object(migration, "_single_standalone_editors", return_value=False):
            old = await migration.migrate_flow(engine, flow.name, backup_root=directory / "old")
        assert not old["ok"] and old["code"] == "migration_conflict", old
        assert migration.flow_migration_blocked(engine, flow.name)
        assert baseline == {name: migration._raw_node_state(node) for name, node in flow.nodes.items()}
        for _ in range(2):
            migration.mark_flow_migration_pending(engine, flow.name)
            with mock.patch.object(routing, "schedule_post_hydration_reconcile") as resume:
                current = await migration.migrate_flow(engine, flow.name, backup_root=directory / "new")
                resume.assert_not_called()
            assert current["ok"] and current["code"] == "standalone_preserved", current
            assert not migration.flow_migration_pending(engine, flow.name)
            assert migration.flow_migration_blocked(engine, flow.name) is None
            assert current["executed_nodes"] == 0 and current["removed_nodes"] == []
            assert baseline == {name: migration._raw_node_state(node) for name, node in flow.nodes.items()}
            assert identities == {name: id(node) for name, node in flow.nodes.items()}
            assert edges == migration._edge_records(engine, set(flow.nodes))
            assert not (directory / "new").exists()
        # A detached durable store can retain only its composite map key. The
        # real SDK restore path accepts it; native slot bodies have no UUID
        # fields, so scanning dictionary values alone misses this ownership.
        from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
        bound_key = base.CHANNEL + "\x1f" + base.SHOTS[0]["shot_uuid"]
        retained_slot = agent._hmb_native_slot_snapshot()
        store = {"schema": agents._AGENT_SHOT_STORE_SCHEMA, "version": 1,
            "active": "__hmb_only__", "slots": {bound_key: retained_slot}, "results": {}}
        base.send(engine, SetParameterValueRequest(node_name=agent.name,
            parameter_name=agents._AGENT_SHOT_STORE_PARAMETER, value=store, initial_setup=True))
        groups, exports = migration._capture_editors(flow)
        assert exports[agent.name]["slots"][bound_key] == retained_slot
        assert migration._has_saved_editor_authoring_identity("agent", exports[agent.name])
        assert migration._has_saved_editor_store_identity("agent", exports[agent.name])
        assert not migration._single_standalone_editors(flow, groups, exports)
        detached_before = {name: deepcopy(migration._raw_node_state(node)) for name, node in flow.nodes.items()}
        guarded = await migration.migrate_flow(engine, flow.name, backup_root=directory / "detached")
        assert not guarded["ok"] and guarded["code"] == "migration_conflict", guarded
        assert detached_before == {name: migration._raw_node_state(node) for name, node in flow.nodes.items()}
        assert edges == migration._edge_records(engine, set(flow.nodes))
        print("STANDALONE_MIGRATION_EVIDENCE " + json.dumps({"boundary_checks": boundary_cases(migration),
            "previous_false_block_reproduced": True, "repeat_noop_exact": 2,
            "detached_key_only_store_reproduced_and_protected": True,
            "authored_nodes_preserved": len(baseline), "wires_preserved": len(edges),
            "executed_nodes": len(base.EXECUTED), "network_attempts": len(base.NETWORK)}))
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


async def roundtrip(engine, directory, phase):
    """Real SDK commands cross a disk file and two fresh Python processes."""
    import hashlib
    import _hmb_workflow_migration as migration
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.flow_events import (
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest)
    from griptape_nodes.serialization.values import encode_value, decode_value
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    engine.event_manager.initialize_queue()
    _, _, _, prompts, agents, _ = base.register_library(engine)
    path = directory / "standalone-sdk-commands.json"
    schema = {"type": "object", "properties": {"shot_uuid": {"type": "string"},
        "channel_uuid": {"type": "null"}}}
    output = {"shot_uuid": "An authored result, not a binding", "channel_uuid": None}
    try:
        if phase == "write":
            ensured = base.send(engine, EnsureWorkflowAndFlowRequest(flow_name="StandaloneSchemaRoundtrip"))
            flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
            def create(kind, name):
                result = base.send(engine, CreateNodeRequest(node_type=kind,
                    specific_library_name="HMB_GP_Production", node_name=name, initial_setup=True))
                return engine.node_manager.get_node_by_name(result.node_name)
            prompt = create("HMBPromptLibrary", "Schema Prompt")
            state = prompt._hmb_prompt_merge_snapshot()["state"]
            state["multi_shot_enabled"] = False
            state["text"]["PRESERVED_TEXT"] = "Authored standalone source {{KEEP}}"
            prompt.set_parameter_value(prompts.WIDGET_PARAMETER_NAME, prompts._json_dumps(state), initial_setup=True)
            agent = create("HMBAgentLibrary", "Schema Agent")
            agent.set_parameter_value(agents._AGENT_WIDGET_PARAMETER,
                agent._hmb_widget_value(shot_manager=False), initial_setup=True)
            agent.set_parameter_value("model_provider", "griptape_cloud", initial_setup=True)
            agent.set_parameter_value("model", agent._model_access.model_choices[0], initial_setup=True)
            agent.set_parameter_value("output_schema", schema, initial_setup=True)
            agent.set_parameter_value("additional_context", "Authored standalone context", initial_setup=True)
            agent.set_parameter_value("prompt", "Preserved native prompt", initial_setup=True)
            agent.parameter_output_values["output"] = deepcopy(output)
            agent.parameter_output_values["logs"] = "Preserved native logs"
            base.send(engine, CreateConnectionRequest(source_node_name=prompt.name,
                source_parameter_name="PROMPT_OUT", target_node_name=agent.name,
                target_parameter_name="prompt", initial_setup=True))
            agent._hmb_capture_active_slot()
            agent._hmb_persist_shot_store(emit_change=False)
            groups, exports = migration._capture_editors(flow)
            assert migration._single_standalone_editors(flow, groups, exports)
            commands = base.send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name)).serialized_flow_commands
            encoded = encode_value(commands)
            path.write_text(json.dumps(encoded, ensure_ascii=False), encoding="utf-8")
            expected = {"writer_pid": os.getpid(), "schema": schema, "output": output,
                "agent_inputs": {key: deepcopy(agent.parameter_values.get(key)) for key in
                    ("model_provider", "model", "prompt", "additional_context", "output_schema")},
                "edges": migration._edge_records(engine, set(flow.nodes))}
            (directory / "expected.json").write_text(json.dumps(encode_value(expected), ensure_ascii=False), encoding="utf-8")
        else:
            saved = path.read_bytes()
            expected = decode_value(json.loads((directory / "expected.json").read_text("utf-8")))
            assert expected["writer_pid"] != os.getpid()
            context = base.send(engine, EnsureWorkflowAndFlowRequest(flow_name="ReadOnlyReopenContext"))
            while engine.context_manager.has_current_flow():
                engine.context_manager.pop_flow()
            base.send(engine, DeleteFlowRequest(flow_name=context.flow_name))
            loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
                serialized_flow_commands=decode_value(json.loads(saved)), broadcast_result=False))
            assert loaded.succeeded(), str(loaded.result_details)
            flow = engine.flow_manager.get_flow_by_name(loaded.flow_name)
            assert set(flow.nodes) == {"Schema Prompt", "Schema Agent"}
            agent, prompt = flow.nodes["Schema Agent"], flow.nodes["Schema Prompt"]
            groups, exports = migration._capture_editors(flow)
            assert migration._single_standalone_editors(flow, groups, exports)
            assert agent.parameter_values["output_schema"] == schema == expected["schema"]
            assert agent.parameter_output_values["output"] == output == expected["output"]
            assert agent.parameter_output_values["logs"] == "Preserved native logs"
            actual_inputs = {key: agent.parameter_values.get(key) for key in expected["agent_inputs"]}
            assert actual_inputs == expected["agent_inputs"], {
                key: {"expected": expected["agent_inputs"][key], "actual": actual_inputs[key]}
                for key in actual_inputs if actual_inputs[key] != expected["agent_inputs"][key]}
            assert prompt._hmb_prompt_merge_snapshot()["state"]["text"]["PRESERVED_TEXT"] == "Authored standalone source {{KEEP}}"
            assert expected["edges"] == migration._edge_records(engine, set(flow.nodes))
            identities = {name: id(node) for name, node in flow.nodes.items()}
            migration.mark_flow_migration_pending(engine, flow.name)
            result = await migration.migrate_flow(engine, flow.name, backup_root=directory / "unexpected-backup")
            assert result["ok"] and result["code"] == "standalone_preserved", result
            assert result["removed_nodes"] == [] and result["executed_nodes"] == 0
            assert identities == {name: id(node) for name, node in flow.nodes.items()}
            assert agent.parameter_values["output_schema"] == schema
            assert agent.parameter_output_values["output"] == output
            assert expected["edges"] == migration._edge_records(engine, set(flow.nodes))
            assert not (directory / "unexpected-backup").exists()
            assert path.read_bytes() == saved
            print("STANDALONE_SDK_SEPARATE_PROCESS_EVIDENCE " + json.dumps({
                "writer_pid": expected["writer_pid"], "reader_pid": os.getpid(),
                "sdk_serialized_sha256": hashlib.sha256(saved).hexdigest(),
                "separate_processes": True, "schema_dict_identity_fields_preserved": True,
                "structured_output_identity_string_and_null_preserved": True,
                "agent_model_and_inputs_preserved": True, "nodes": len(flow.nodes),
                "wires": len(expected["edges"]), "migration_code": result["code"],
                "executed_nodes": len(base.EXECUTED), "network_attempts": len(base.NETWORK)}))
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roundtrip-phase", choices=("write", "read"))
    parser.add_argument("--roundtrip-dir", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hmb-standalone-migration-") as directory:
        temporary = Path(directory)
        overrides = {key: str(temporary / key) for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME",
            "XDG_CACHE_HOME", "LOCALAPPDATA", "APPDATA", "GTN_CONFIG_WORKSPACE_DIRECTORY", "HMB_IMAGE_PROJECTS_ROOT")}
        for path in overrides.values():
            Path(path).mkdir()
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket, "create_connection", base.no_network))
            from griptape_nodes.retained_mode.engine import engine_scope
            import _hmb_shot_routing as routing
            import HMBAgentLibrary as agents
            import HMBSeedanceGeneration as generators
            import HMBImageAssetLibrary as images
            import _hmb_library_bootstrap as bootstrap
            import _hmb_workflow_migration as migration
            stack.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k: None))
            if args.roundtrip_phase:
                stack.enter_context(mock.patch.object(migration, "schedule_loaded_flow_migrations", lambda *a, **k: None))
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
            stack.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
            stack.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", base.no_execution))
            stack.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", base.no_execution))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                if args.roundtrip_phase:
                    assert args.roundtrip_dir and args.roundtrip_dir.is_dir()
                    asyncio.run(roundtrip(engine, args.roundtrip_dir, args.roundtrip_phase))
                else:
                    asyncio.run(exercise(engine, temporary))
            assert base.NETWORK == [] and base.EXECUTED == []
    if args.roundtrip_phase:
        return
    with tempfile.TemporaryDirectory(prefix="hmb-standalone-two-process-") as directory:
        for phase in ("write", "read"):
            completed = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                "--roundtrip-phase", phase, "--roundtrip-dir", directory], cwd=ROOT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1"),
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-5000:]
            print(completed.stdout, end="")
    print("HMB_WORKFLOW_STANDALONE_LEGACY_HOST=PASS")


if __name__ == "__main__":
    main()
