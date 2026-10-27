"""Installed SDK: five saved Prompt/Agent editors consolidate without execution."""
from __future__ import annotations

import asyncio
import ast
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import inspect
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
CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOTS = [{"shot_uuid": f"33333333-3333-4333-8333-{number:012d}", "number": number,
    "name": f"Renamed authored asset {number}", "revision": number, "selected_source_uids": []} for number in range(1, 6)]
EXECUTED = []
NETWORK = []
NATIVE_HYDRATION_SCHEDULER = None


def no_network(*args, **kwargs):
    NETWORK.append(True)
    raise AssertionError("Consolidation attempted network transport")


def no_execution(*args, **kwargs):
    EXECUTED.append(True)
    raise AssertionError("Consolidation executed a model or render")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def disconnect_fixture_nodes(engine, flow, names):
    """Use the public connection command before intentionally deleting fixtures.

    Snapshot native inputs/outputs and five-Shot stores separately from the
    connection metadata. A teardown must obey the same protection as the UI.
    """
    import _hmb_connection_management as connections
    import _hmb_deletion_guard as deletion

    def authored():
        return {name: deepcopy({
            "inputs": dict(node.parameter_values),
            "outputs": dict(node.parameter_output_values),
            "agent_slots": getattr(node, "_hmb_shot_slots", None),
            "agent_results": getattr(node, "_hmb_shot_results", None),
            "finish_documents": getattr(node, "_hmb_finish_documents", None),
        }) for name, node in flow.nodes.items()}

    identities = {name: id(node) for name, node in flow.nodes.items()}
    before = authored()
    engine.context_manager.push_flow(flow)
    try:
        for name in names:
            state = send(engine, connections.HMBGetNodeConnectionsRequest(node_name=name))
            if state.can_disconnect:
                send(engine, connections.HMBManageNodeConnectionsRequest(
                    node_name=name, operation="disconnect", expected_state_token=state.state_token))
            assert not deletion.connected_targets(engine, [name]), name
        assert identities == {name: id(node) for name, node in flow.nodes.items()}
        assert authored() == before, "Explicit fixture detach changed saved inputs or Shot results"
    finally:
        engine.context_manager.pop_flow()


def register_library(engine):
    import HMBImageAssetLibrary as images
    import HMBPromptLibrary as prompts
    import HMBAgentLibrary as agents
    import HMBSeedanceGeneration as generators
    import HMBVideoPickerLibrary as pickers
    from _hmb_library_bootstrap import HMBProductionLibrary
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    advanced = HMBProductionLibrary()
    library = LibraryRegistry.generate_new_library(schema, advanced_library=advanced)
    classes = {cls.__name__: cls for cls in (images.HMBImageAssetLibrary, prompts.HMBPromptLibrary,
        agents.HMBAgentLibrary, generators.HMBSeedanceGeneration, pickers.HMBVideoPickerLibrary)}
    for definition in schema.nodes:
        cls = classes.get(definition.class_name)
        if cls:
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    advanced.before_library_nodes_loaded(schema, library)
    return library, advanced, images, prompts, agents, generators


async def canonical_case(engine, directory):
    engine.event_manager.initialize_queue()
    import _hmb_workflow_migration as migration
    import _hmb_shot_routing as routing
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    library, advanced, images, prompts, agents, generators = register_library(engine)
    try:
        ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="CanonicalLegacyFive"))
        flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
        migration.mark_flow_migration_pending(engine, flow.name)
        def create(kind, name):
            result = send(engine, CreateNodeRequest(node_type=kind, specific_library_name="HMB_GP_Production",
                node_name=name, initial_setup=True))
            return engine.node_manager.get_node_by_name(result.node_name)
        source = create("HMBImageAssetLibrary", "Renamed Image Library")
        source._hmb_initial_catalog_scan_pending = False
        catalog_document = {"channel_uuid": CHANNEL, "generation": 1,
            "shots": [{key: row[key] for key in ("shot_uuid", "number", "name", "revision")} for row in SHOTS]}
        catalog = {"schema": "hmb-shot-routing-catalog", "version": 1, "publisher_instance_uuid": PUBLISHER,
            **catalog_document, "metadata_sha256": digest(catalog_document)}
        source._hmb_shot_routing_catalog = lambda: deepcopy(catalog)
        source._hmb_project_identity = lambda: {"project_id": "katuri8", "project_name": "까투리8"}
        prompt_nodes, agent_nodes, generator_nodes = [], [], []
        for number, shot in enumerate(SHOTS, 1):
            prompt = create("HMBPromptLibrary", f"Renamed Prompt {number}")
            state = prompt._hmb_prompt_merge_snapshot()["state"]
            state["multi_shot_enabled"] = False
            state["shot"] = {"channel_uuid": CHANNEL, **shot}
            state["text"]["PRESERVED_TEXT"] = f"Authored literal {number} {{{{SIGN}}}}"
            prompt.set_parameter_value(prompts.WIDGET_PARAMETER_NAME, prompts._json_dumps(state), initial_setup=True)
            prompt_nodes.append(prompt)
            agent = create("HMBAgentLibrary", f"Renamed Agent {number}")
            agent.set_parameter_value(agents._AGENT_WIDGET_PARAMETER, agent._hmb_widget_value(
                shot={"channel_uuid": CHANNEL, **shot}, shot_catalog=catalog, shot_manager=True), initial_setup=True)
            agent.set_parameter_value("additional_context", f"Native settings {number}", initial_setup=True)
            agent.set_parameter_value("output_schema", {"type": "object", "properties": {str(number): {"type": "string"}}}, initial_setup=True)
            rule = agent.get_parameter_by_name("rulesets").add_child_parameter()
            agent.set_parameter_value(rule.name, {"name": f"Authored rules {number}", "rules": [f"Rule {number}"]}, initial_setup=True)
            agent.parameter_output_values["output"] = f"Preserved final text {number}"
            agent.parameter_output_values["logs"] = f"Preserved result log {number}"
            agent_nodes.append(agent)
            generator = create("HMBSeedanceGeneration", f"Renamed Generator {number}")
            for key, value in (("shot_channel_uuid", CHANNEL), ("shot_uuid", shot["shot_uuid"]),
                ("shot_number", number), ("shot_name", shot["name"]), ("resolution", "480p"),
                ("resume_generation_id", "job-" + str(number) * 32), ("draft_job_id", "job-" + str(number + 1) * 32)):
                generator.set_parameter_value(key, value, initial_setup=True)
            generator_nodes.append(generator)
            for src, out, dst, inp in ((source, "SHOT_ASSET_OUT", prompt, "SHOT_ASSET_IN"),
                (prompt, "PROMPT_OUT", agent, "SHOT_PROMPT_IN"), (agent, "output", generator, "prompt"),
                (source, "SHOT_ASSET_OUT", generator, "SHOT_ASSET_IN")):
                send(engine, CreateConnectionRequest(source_node_name=src.name, source_parameter_name=out,
                    target_node_name=dst.name, target_parameter_name=inp, initial_setup=True))
        original = {node.name: migration._raw_node_state(node) for node in flow.nodes.values()}
        original_edges = migration._edge_records(engine, set(flow.nodes))
        exported = {node.name: node._hmb_export_agent_authoring_state() for node in agent_nodes}
        result = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
        assert result["ok"] and result["code"] == "consolidated", result
        assert len(flow.nodes) == 8 and len(result["removed_nodes"]) == 8
        assert flow.nodes[prompt_nodes[0].name] is prompt_nodes[0] and flow.nodes[agent_nodes[0].name] is agent_nodes[0]
        for node in generator_nodes:
            assert migration._raw_node_state(node) == original[node.name], node.name
        documents = prompt_nodes[0]._hmb_prompt_merge_snapshot()["materialized_documents"]
        for number, shot in enumerate(SHOTS, 1):
            document = json.loads(documents[CHANNEL + "/" + shot["shot_uuid"]])
            assert document["text"]["PRESERVED_TEXT"] == f"Authored literal {number} {{{{SIGN}}}}"
            key = agent_nodes[0]._hmb_slot_key(CHANNEL, shot["shot_uuid"])
            slot = agent_nodes[0]._hmb_shot_slots[key]
            assert slot["values"]["additional_context"] == f"Native settings {number}"
            assert slot["outputs"]["output"] == f"Preserved final text {number}"
            assert slot["values"]["output_schema"] == exported[agent_nodes[number - 1].name]["native_slot"]["values"]["output_schema"]
        from griptape_nodes.serialization.values import decode_value
        backup = decode_value(json.loads(Path(result["backup_path"]).read_text(encoding="utf-8")))
        assert set(backup["nodes"]) == set(original) and backup["edges"] == original_edges
        assert all(backup["nodes"][name]["raw"] == value for name, value in original.items())
        assert len(result["aliases"]) == 10 and all(item["node_name"] in flow.nodes for item in result["aliases"].values())
        assert not migration.flow_migration_pending(engine, flow.name)
        again = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
        assert again["ok"] and again["code"] == "already_single"
        print("PASS actual Prompt5+Agent5 -> one each; authored UUID/name/text/native rules/schema/results, Generator Resume/Draft/480p, exact edges and full recovery retained")
        # Restore the durable pre-migration document using real SDK node replay,
        # then force one final deletion to fail. A rollback must restore all 16.
        await migration._restore(engine, flow, backup, set(result["aliases"]))
        assert migration._edge_records(engine, set(flow.nodes)) == original_edges
        before_failure = migration._stamp(engine, flow)
        deleted = {"count": 0}
        original_send = migration._send
        async def fail_third_delete(host, request, expected):
            if type(request).__name__ == "DeleteNodeRequest":
                deleted["count"] += 1
                if deleted["count"] == 3:
                    raise RuntimeError("Injected one-time structural deletion failure")
            return await original_send(host, request, expected)
        with mock.patch.object(migration, "_send", fail_third_delete):
            failed = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
        assert not failed["ok"] and failed["rollback"] == "verified", failed
        assert migration._stamp(engine, flow) == before_failure
        await asyncio.sleep(0.05)
        assert migration._stamp(engine, flow) == before_failure
        blocked_route = routing.reconcile_shot_routing(flow.nodes[source.name])
        assert blocked_route["code"] == "workflow_migration_failed" and not blocked_route["ok"]
        assert migration._stamp(engine, flow) == before_failure
        print("PASS injected partial deletion failure restores every exact original node name/input/output/edge; no partial consolidation")
        original_import = prompts.HMBPromptLibrary._hmb_import_prompt_documents
        def fail_after_prompt_commit(self, *args, **kwargs):
            original_import(self, *args, **kwargs)
            raise RuntimeError("Injected failure after the first Prompt state commit")
        with mock.patch.object(prompts.HMBPromptLibrary, "_hmb_import_prompt_documents", fail_after_prompt_commit):
            failed_import = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
        assert not failed_import["ok"] and failed_import["rollback"] == "verified", failed_import
        assert migration._stamp(engine, flow) == before_failure
        deleted["count"] = 0
        async def cancel_third_delete(host, request, expected):
            if type(request).__name__ == "DeleteNodeRequest":
                deleted["count"] += 1
                if deleted["count"] == 3:
                    raise asyncio.CancelledError()
            return await original_send(host, request, expected)
        with mock.patch.object(migration, "_send", cancel_third_delete):
            try:
                await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("Cancellation was not propagated after rollback")
        assert migration.last_migration_result(engine, flow.name)["rollback"] == "verified"
        assert migration._stamp(engine, flow) == before_failure
        await asyncio.sleep(0.05)
        assert migration._stamp(engine, flow) == before_failure
        print("PASS first-hook post-commit failure and cancellation during deletion each finish a verified rollback before releasing the flow")
        from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest
        removed_names = [name for name, node in flow.nodes.items()
            if node.metadata.get("node_type") in {"HMBAgentLibrary", "HMBSeedanceGeneration"}]
        disconnect_fixture_nodes(engine, flow, removed_names)
        for name in removed_names:
            send(engine, DeleteNodeRequest(node_name=name))
        prompt_only = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
        assert prompt_only["ok"] and set(prompt_only["survivors"]) == {"prompt"}, prompt_only
        assert len(flow.nodes) == 2
        prompt = flow.nodes[prompt_only["survivors"]["prompt"]]
        state = prompt._hmb_prompt_merge_snapshot()["state"]
        state["multi_shot_enabled"] = False
        state["shot_documents"] = {}
        prompt._hmb_write_merged_prompt_state(prompts._json_dumps(state))
        preserved = state["text"]["PRESERVED_TEXT"]
        edges_before_upgrade = migration._edge_records(engine, set(flow.nodes))
        upgraded = await migration.migrate_flow(engine, flow.name, backup_root=directory / "backups")
        assert upgraded["ok"] and upgraded["code"] == "consolidated", upgraded
        assert prompt._hmb_shot_manager_enabled() and prompt._hmb_prompt_merge_snapshot()["state"]["text"]["PRESERVED_TEXT"] == preserved
        assert migration._edge_records(engine, set(flow.nodes)) == edges_before_upgrade
        print("PASS Prompt-only legacy flow consolidates without requiring an Agent; legacy single Prompt upgrades in place without changing inputs/edges")
        from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, DeserializeFlowFromCommandsRequest
        from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
        from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowWithCurrentStateRequest
        other = send(engine, CreateFlowRequest(flow_name="UnrelatedEditableFlow", parent_flow_name=None, set_as_new_context=True))
        before_guard = migration._stamp(engine, flow)
        with migration._LOCK:
            migration._INFLIGHT.setdefault(engine, set()).add(flow.name)
        try:
            blocked_requests = [
                CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name="HMB_GP_Production", override_parent_flow_name=flow.name),
                CreateConnectionRequest(source_node_name=source.name, source_parameter_name="SHOT_ASSET_OUT", target_node_name=prompt.name, target_parameter_name="SHOT_ASSET_IN"),
                SetParameterValueRequest(node_name=prompt.name, parameter_name=prompts.WIDGET_PARAMETER_NAME, value="unwanted concurrent edit"),
                DeserializeFlowFromCommandsRequest(serialized_flow_commands=backup["flow_commands"]),
                RunWorkflowWithCurrentStateRequest(file_path=str(directory / "does_not_exist.py")),
            ]
            for request in blocked_requests:
                response = engine.handle_request(request)
                assert not response.succeeded() and "consolidation" in str(response.result_details), type(request).__name__
            assert migration._stamp(engine, flow) == before_guard
        finally:
            with migration._LOCK:
                migration._INFLIGHT.get(engine, set()).discard(flow.name)
        # One ordinary standalone editor requires no Shot choice when there is
        # no publisher and no saved binding. Preserve it without consolidation.
        legacy_agent = create("HMBAgentLibrary", "Single legacy unbound Agent")
        legacy_agent.set_parameter_value("additional_context", "Unassigned authored native value", initial_setup=True)
        legacy_raw = legacy_agent._hmb_widget_value(shot={}, shot_catalog={}, shot_manager=True)
        legacy_raw.pop("shot_manager", None)
        legacy_agent._hmb_capture_saved_parameter_value(agents._AGENT_WIDGET_PARAMETER, legacy_raw)
        agent_before = deepcopy(migration._raw_node_state(legacy_agent))
        agent_only = await migration.migrate_flow(engine, other.flow_name, backup_root=directory / "backups")
        assert agent_only["ok"] and agent_only["code"] == "standalone_preserved", agent_only
        assert migration._raw_node_state(legacy_agent) == agent_before
        assert engine.node_manager.get_node_by_name(legacy_agent.name) is legacy_agent
        assert not migration.flow_migration_blocked(engine, other.flow_name)
        assert not agent_only.get("backup_path")
        print("PASS explicit cross-flow-target mutations/load are blocked during commit; one standalone legacy Agent is preserved exactly without an invented Shot choice")
        # A library unload invalidates the queued generation, clears loading,
        # and retains an explicit blocked result without running migration.
        before_unload = migration._stamp(engine, flow)
        migration.mark_flow_migration_pending(engine, flow.name)
        migration.schedule_loaded_flow_migrations(engine)
        advanced.before_library_unregistered(library.get_library_data(), library)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not migration.flow_migration_pending(engine, flow.name)
        assert migration.flow_migration_blocked(engine, flow.name)["code"] == "workflow_migration_failed"
        assert migration._stamp(engine, flow) == before_unload
        print("PASS unload invalidates queued coordinator and clears pending without changing the graph")
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


async def actual_saved_file_case(engine, directory, *, complete_manual_rebind=False):
    """Replay the untouched user document in an isolated engine from a copy.

    Only the library registration line is replaced: source-under-test classes
    are already registered locally. Every authored value/connection is original.
    """
    engine.event_manager.initialize_queue()
    import _hmb_workflow_migration as migration
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowWithCurrentStateRequest
    # The working document changes as its owner saves the upgraded graph. Use
    # the immutable pre-update capture for this legacy5+5 migration contract.
    fixture = ROOT / "reports/finish-look-manager-20261015/preupdate-workflows/hmb_draft_shot_live_test_20261013_v002.py"
    source = Path(os.environ.get("HMB_LEGACY_MIGRATION_WORKFLOW", str(fixture)))
    if not source.is_file():
        print("SKIP real saved document case (host-specific fixture absent)")
        return
    original_bytes = source.read_bytes()
    if "HMB_LEGACY_MIGRATION_WORKFLOW" not in os.environ:
        assert hashlib.sha256(original_bytes).hexdigest() == "1829690768c5b9327c76a6e3261a5b905b3942a97a20622b291f3fe2bcc0bfea", "Immutable legacy5+5 fixture changed"
    tree = ast.parse(original_bytes.decode("utf-8-sig"))
    values = next(ast.literal_eval(node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "top_level_unique_values_dict" for target in node.targets))
    node_names = {}
    expected = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Attribute) or not isinstance(node.value.value, ast.Await):
            continue
        outer = node.value.value.value
        if not isinstance(outer, ast.Call) or not outer.args or not isinstance(outer.args[0], ast.Call):
            continue
        inner = outer.args[0]
        if ast.unparse(inner.func) != "CreateNodeRequest":
            continue
        arguments = {item.arg: ast.literal_eval(item.value) for item in inner.keywords if isinstance(item.value, ast.Constant)}
        node_names[ast.unparse(node.targets[0])] = (arguments.get("node_name"), arguments.get("node_type"))
    assert sum(kind == "HMBPromptLibrary" for _, kind in node_names.values()) == 5
    assert sum(kind == "HMBAgentLibrary" for _, kind in node_names.values()) == 5
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or ast.unparse(node.func) != "SetParameterValueRequest":
            continue
        keywords = {item.arg: item.value for item in node.keywords}
        if not isinstance(keywords.get("node_name"), ast.Name) or keywords["node_name"].id not in node_names:
            continue
        value = keywords.get("value")
        if not isinstance(value, ast.Call) or not value.args or not isinstance(value.args[0], ast.Subscript):
            continue
        key = ast.literal_eval(value.args[0].slice)
        expected[(node_names[keywords["node_name"].id][0], ast.literal_eval(keywords["parameter_name"]),
            ast.literal_eval(keywords.get("is_output", ast.Constant(False))))] = values[key]
    text = original_bytes.decode("utf-8-sig")
    lines = text.splitlines(keepends=True)
    replaced = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)
                and isinstance(node.value.value, ast.Call) and node.value.value.args
                and isinstance(node.value.value.args[0], ast.Call)
                and ast.unparse(node.value.value.args[0].func) == "RegisterLibraryFromFileRequest"):
            assert node.lineno == node.end_lineno
            lines[node.lineno - 1] = "    pass  # Current HMB source is registered in this isolated SDK fixture.\n"
            replaced += 1
    assert replaced == 1
    controlled = directory / "actual_saved_document.py"
    controlled.write_text("".join(lines), encoding="utf-8")
    library, advanced, images, prompts, agents, generators = register_library(engine)
    try:
        result = await engine.ahandle_request(RunWorkflowWithCurrentStateRequest(file_path=str(controlled), broadcast_result=False))
        assert result.succeeded(), str(result.result_details)
        outcome = None
        for _ in range(100):
            for flow_name in tuple(engine.flow_manager._name_to_parent_name):
                candidate = migration.last_migration_result(engine, flow_name)
                if candidate is not None:
                    outcome = candidate
                    break
            if outcome is not None:
                break
            await asyncio.sleep(0.02)
        if outcome and not outcome["ok"] and outcome.get("backup_path"):
            from griptape_nodes.serialization.values import decode_value
            failed_backup = decode_value(json.loads(Path(outcome["backup_path"]).read_text(encoding="utf-8")))
            diagnostic = {name: {"active": item.get("active_subscription"), "slots": list(item.get("slots", {})),
                "legacy_widget_present": isinstance(item.get("legacy_widget"), dict)}
                for name, item in failed_backup["authoring_exports"].items() if item.get("schema") == "hmb-agent-authoring-export"}
            print("FAILED_SAVED_AGENT_EXPORTS=" + json.dumps(diagnostic, ensure_ascii=False))
        manual_rebound_originals = False
        if outcome and outcome.get("code") == "migration_conflict" and outcome.get("manual_rebind_editors"):
            # Current release requires a human choice for old independent
            # editors. The original real file contains two unbound Agents;
            # silently archiving/deleting them is no longer the approved path.
            # The separate ManualRebindHost covers ten actual UI confirmations,
            # consolidation, native inputs and Generator recovery preservation.
            flow = engine.flow_manager.get_flow_by_name(outcome["flow_name"])
            assert len(flow.nodes) == len(failed_backup["nodes"]) == 17
            assert migration._edge_records(engine, set(flow.nodes)) == failed_backup["edges"]
            assert len(failed_backup["edges"]) == 26
            unbound_names = []
            for name, exported in failed_backup["authoring_exports"].items():
                if exported.get("schema") != "hmb-agent-authoring-export":
                    continue
                raw = expected.get((name, agents._AGENT_WIDGET_PARAMETER, False))
                if isinstance(raw, str):
                    raw = json.loads(raw)
                if isinstance(raw, dict) and not raw.get("shot", {}).get("shot_uuid"):
                    unbound_names.append(name)
                    assert exported.get("legacy_widget") == raw
                    node = flow.nodes[name]
                    assert node._hmb_native_slot_snapshot() == exported["native_slot"]
                    assert getattr(node, "_hmb_manual_rebind", {}).get("required") is True
            assert len(unbound_names) == 2
            assert set(outcome["manual_rebind_editors"]) == set(unbound_names)
            assert source.read_bytes() == original_bytes
            print("PASS original saved Prompt5/Agent5/Gen5 preserved: two independent Agents require explicit rebind before consolidation; backup17/edges26; models/renders0")
            if complete_manual_rebind:
                # This is an explicit fixture user's choice, never a production
                # rule deriving ownership from a node name or display number.
                publisher = next(node for node in flow.nodes.values()
                    if node.metadata.get("node_type") == "HMBImageAssetLibrary")
                catalog = publisher._hmb_shot_routing_catalog()
                targets = sorted(catalog["shots"], key=lambda row: row["number"])[3:5]
                for index, (name, shot) in enumerate(zip(sorted(unbound_names), targets), 1):
                    node = flow.nodes[name]
                    confirmed = node._hmb_apply_manual_rebind({"kind": "manual_rebind",
                        "request_id": f"{index:032x}", "channel_uuid": catalog["channel_uuid"],
                        "shot_uuid": shot["shot_uuid"],
                        "expected_source_digest": node._hmb_manual_rebind["expected_source_digest"]})
                    assert confirmed["ok"] is True
                for _ in range(250):
                    await asyncio.sleep(.02)
                    retried = migration.last_migration_result(engine, flow.name)
                    if retried and retried.get("code") == "consolidated":
                        break
                assert retried and retried.get("ok") is True and retried.get("code") == "consolidated", retried
                assert len(flow.nodes) == 9
                assert len([node for node in flow.nodes.values() if node.metadata.get("node_type") == "HMBPromptLibrary"]) == 1
                assert len([node for node in flow.nodes.values() if node.metadata.get("node_type") == "HMBAgentLibrary"]) == 1
                assert source.read_bytes() == original_bytes
                print("PASS fixture user explicitly reconnected the two original independent Agents; one Prompt/Agent manager, five Generators; no inferred binding or execution")
                manual_rebound_originals = True
                outcome = retried
            else:
                return
        assert outcome and outcome["ok"] and outcome["code"] == "consolidated", outcome
        flow = engine.flow_manager.get_flow_by_name(outcome["flow_name"])
        assert len(flow.nodes) == 9 and len(outcome["removed_nodes"]) == 8, outcome
        from griptape_nodes.serialization.values import decode_value
        backup = decode_value(json.loads(Path(outcome["backup_path"]).read_text(encoding="utf-8")))
        assert len(backup["nodes"]) == 17 and len(backup["edges"]) == 26
        manager = flow.nodes[outcome["survivors"]["agent"]]
        unbound = []
        for name, exported in backup["authoring_exports"].items():
            if exported.get("schema") != "hmb-agent-authoring-export":
                continue
            raw = expected.get((name, agents._AGENT_WIDGET_PARAMETER, False))
            if isinstance(raw, str):
                raw = json.loads(raw)
            if isinstance(raw, dict) and not raw.get("shot", {}).get("shot_uuid"):
                unbound.append(name)
                archive = manager._hmb_agent_migration_archives[name]
                if manual_rebound_originals:
                    assert failed_backup["authoring_exports"][name]["legacy_widget"] == raw
                    assert exported["active_subscription"]["enabled"] is True
                    assert any(item.get("legacy_widget") == raw
                        and item.get("native_slot") == failed_backup["authoring_exports"][name]["native_slot"]
                        for item in archive["source_archives"].values())
                    assert not exported["native_slot"]["outputs"].get("output")
                else:
                    assert exported.get("legacy_widget") == raw, name
                    assert not exported["active_subscription"].get("enabled"), name
                    assert archive["unbound_slots"] and archive["source_digest"] == exported["digest"]
        assert len(unbound) == 2, unbound
        for name, saved in backup["nodes"].items():
            if saved["raw"]["metadata"].get("node_type") == "HMBSeedanceGeneration":
                assert migration._raw_node_state(flow.nodes[name]) == saved["raw"], name
        assert source.read_bytes() == original_bytes
        print("PASS original saved file Prompt5/Agent5/Gen5+Picker+Image -> one Prompt/Agent; legacy unbound4/5 archived without guessed Shot; exact Generator Resume/Draft/results retained")
        # Re-open a real SDK serialization of that now-single graph. The load
        # coordinator must resume the publisher even when no contraction is
        # necessary; a real router ACK proves it is not stranded as pending.
        import _hmb_shot_routing as routing
        from griptape_nodes.retained_mode.events.flow_events import (
            SerializeFlowToCommandsRequest, DeleteFlowRequest, DeserializeFlowFromCommandsRequest)
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name)).serialized_flow_commands
        old_name = flow.name
        disconnect_fixture_nodes(engine, flow, tuple(flow.nodes))
        send(engine, DeleteFlowRequest(flow_name=old_name))
        with migration._LOCK:
            migration._RESULTS.get(engine, {}).pop(old_name, None)
        with mock.patch.object(routing, "schedule_post_hydration_reconcile", NATIVE_HYDRATION_SCHEDULER):
            loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
                serialized_flow_commands=serialized, broadcast_result=False))
            assert loaded.succeeded(), str(loaded.result_details)
            reloaded = engine.flow_manager.get_flow_by_name(loaded.flow_name)
            publisher = next(node for node in reloaded.nodes.values()
                if node.metadata.get("node_type") == "HMBImageAssetLibrary")
            for _ in range(100):
                resumed = migration.last_migration_result(engine, loaded.flow_name)
                if resumed and getattr(publisher, "_hmb_last_reconciled_shot_catalog_identity", ""):
                    break
                await asyncio.sleep(0.02)
            assert resumed and resumed["ok"] and resumed["code"] == "already_single", resumed
            assert not migration.flow_migration_pending(engine, loaded.flow_name)
            assert getattr(publisher, "_hmb_last_reconciled_shot_catalog_identity", ""), (
                getattr(publisher, "_hmb_hydration_adopted", None),
                getattr(publisher, "_hmb_reserved_shot_catalog_identity", None), resumed)
            assert not getattr(publisher, "_hmb_reserved_shot_catalog_identity", "")
            assert len(reloaded.nodes) == 9
        print("PASS saved singleton SDK reload resumes exactly its ImageAsset publisher and completes a real ready ACK after event-loop drain")
    finally:
        LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)


def main():
    global NATIVE_HYDRATION_SCHEDULER
    with tempfile.TemporaryDirectory(prefix="hmb-workflow-consolidation-") as directory:
        temporary = Path(directory)
        overrides = {key: str(temporary / leaf) for key, leaf in (("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("LOCALAPPDATA", "local"),
            ("APPDATA", "app"), ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "images"))}
        for target in overrides.values():
            Path(target).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, overrides), ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket, "create_connection", no_network))
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
            except ImportError:
                print("HMB_WORKFLOW_CONSOLIDATION_HOST=SKIP (installed SDK required)")
                return
            import _hmb_shot_routing as routing
            NATIVE_HYDRATION_SCHEDULER = routing.schedule_post_hydration_reconcile
            import HMBAgentLibrary as agents
            import HMBSeedanceGeneration as generators
            import HMBImageAssetLibrary as images
            import _hmb_library_bootstrap as bootstrap
            stack.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k: None))
            for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                stack.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
            stack.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
            stack.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", no_execution))
            stack.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", no_execution))
            logging.disable(logging.CRITICAL)
            with engine_scope() as engine:
                asyncio.run(canonical_case(engine, temporary))
            with engine_scope() as engine:
                asyncio.run(actual_saved_file_case(engine, temporary))
            assert EXECUTED == [] and NETWORK == []
    print("HMB_WORKFLOW_CONSOLIDATION_HOST=PASS (actual SDK structure; no models/renders/network/user graph changes)")


if __name__ == "__main__":
    main()
