"""Installed SDK contract for explicit HMB detach/reconnect, without execution.

Synthetic five-Shot authoring is saved and replayed by native SDK commands.
All provider/model/render/upload boundaries are forbidden.  No desktop or
running engine is accessed.
"""
from __future__ import annotations
import ast
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
sys.dont_write_bytecode = True
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
import HMB_Library_Lifecycle_Order_Host_Regression as base

CASES = []
ATTEMPTS = []
PRODUCTS = ("_hmb_connection_management.py", "_hmb_deletion_guard.py", "_hmb_shot_routing.py",
            "_hmb_library_bootstrap.py", "HMBPromptLibrary.py")


def deny(*args, **kwargs):
    ATTEMPTS.append("forbidden_execution_or_transport")
    raise AssertionError("Common connection SDK fixture cannot execute, render or use transport")


def record(name, **facts):
    CASES.append(dict(name=name, passed=True, **facts))


def edges(engine):
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
    result = set()
    for name in tuple(engine.node_manager._name_to_parent_flow_name):
        listing = base.send(engine, ListConnectionsForNodeRequest(node_name=name, include_internal=True))
        for edge in listing.outgoing_connections:
            result.add((name, edge.source_parameter_name, edge.target_node_name, edge.target_parameter_name))
    return result


def authoring(nodes):
    """Only artist inputs/settings/results: exclude derived UI clocks/catalog ACKs."""
    source, picker, prompt, agent, finish = (nodes[k] for k in base.KINDS[:5])
    generator_fields = ("model_id", "task", "resolution", "duration", "ratio", "output_format", "output_file", "generate_audio", "resume_generation_id")
    return dict(
        source_shots=deepcopy(source._current_state()["shot_routing"]["shots"]),
        picker_memberships=deepcopy(picker._picker_state()["shot_selections"]),
        prompt_documents=deepcopy(prompt._hmb_prompt_merge_snapshot()["materialized_documents"]),
        agent_slots=deepcopy(agent._hmb_shot_slots), agent_results=deepcopy(agent._hmb_shot_results),
        finish_documents=deepcopy(finish._hmb_finish_documents),
        generators={node.name: dict(values={key:deepcopy(node.get_parameter_value(key)) for key in generator_fields},
            outputs={key:deepcopy(node.parameter_output_values.get(key)) for key in ("generation_id", "generation_status", "result_details", "video_url", "was_successful")})
            for node in nodes[base.KINDS[5]]})


def hooks(engine, modules, patches):
    import _hmb_library_bootstrap as bootstrap
    patches.enter_context(mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a, **k:None))
    patches.enter_context(mock.patch.object(modules[base.KINDS[0]].HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k:False))
    patches.enter_context(mock.patch.object(modules[base.KINDS[5]]._HMBAIBrokerBridge, "_request_json", deny))
    for kind, module in modules.items():
        patches.enter_context(mock.patch.object(getattr(module, kind), "process", deny))
    library, schema = base.register(engine, modules)
    owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
    owner._registrations = set()
    owner.before_library_nodes_loaded(schema, library)
    engine.event_manager.initialize_queue()
    assert owner._registrations
    return library, schema, owner


async def setup(engine, modules, folder, schema):
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    base.send(engine, EnsureWorkflowAndFlowRequest(flow_name="OfflineCommonConnections"))
    state = base.create_project(modules[base.KINDS[0]], folder / "media")
    nodes = {}
    for kind in base.KINDS[:5]:
        result = base.send(engine, CreateNodeRequest(node_type=kind, specific_library_name=schema.name,
            node_name="Connection " + kind, create_error_proxy_on_failure=False))
        node = engine.node_manager.get_node_by_name(result.node_name)
        nodes[kind] = node
        if kind == base.KINDS[0]:
            node._hmb_initial_catalog_scan_pending = False
            node._resolution_cache_for_state(deepcopy(state))
            node._cache_shot_routing_snapshot(deepcopy(state), force=True)
            node._publish_state(deepcopy(state))
        await asyncio.sleep(.03)
    source, picker, prompt, agent, finish = (nodes[k] for k in base.KINDS[:5])
    await base.settle(lambda: len(getattr(agent, "_hmb_shot_catalog_snapshot", {}).get("shots", [])) == 5, seconds=3)
    shots = source._hmb_shot_routing_snapshot()["shots"]
    pickers, prompts, finishes = (modules[kind] for kind in (base.KINDS[1], base.KINDS[2], base.KINDS[4]))
    picker_state = picker._picker_state()
    picker_state["picker_shots"] = [pickers._new_picker_workspace_row(number,
        bound_shot_uuid=shot["shot_uuid"]) for number, shot in enumerate(shots, 1)]
    picker_state["active_picker_shot_uuid"] = picker_state["picker_shots"][0]["workspace_uuid"]
    picker._write_state(picker_state)
    picker_state = picker._picker_state()
    picker._hmb_verified_media = (picker._execution_media_identity(picker_state), {})
    picker._sync_outputs_from_state(picker_state, enforce_media_availability=False)
    prompt_state = prompt._current_state()
    text_key = next(iter(prompts.TEXT_FIELD_DEFAULTS))
    for shot in shots:
        prompt_state = prompts._select_prompt_shot_document(prompt_state, dict(shot, channel_uuid=base.CHANNEL))
        prompt_state = base.prompt_rows_from_state(prompt, prompt_state)[0]
        prompt_state["text"][text_key] = f"Retained Prompt {shot['number']}: {{literal}} RGB(12, 34, 56) OFF 0"
        prompt_state = prompts._store_prompt_shot_document(prompt_state)
        finish_state = deepcopy(finish._widget_state)
        finish_state["shot"] = dict(shot, channel_uuid=base.CHANNEL)
        base.send(engine, SetParameterValueRequest(node_name=finish.name, parameter_name=finishes.WIDGET_PARAMETER_NAME, value=finish_state))
        finish_state = deepcopy(finish._widget_state)
        finish_state["finish_look"]["beauty"].update(enabled=True, brightness=1+shot["number"]/10)
        base.send(engine, SetParameterValueRequest(node_name=finish.name, parameter_name=finishes.WIDGET_PARAMETER_NAME, value=finish_state))
    base.send(engine, SetParameterValueRequest(node_name=prompt.name, parameter_name=prompts.WIDGET_PARAMETER_NAME,
        value=prompts._json_dumps(prompt_state), initial_setup=True))
    prompt._sync_prompt_output_now()
    for number in (1, 2, 3, 4, 5, 2):
        row_name = "HMB_AGENT_SHOT_ROW_" + str(number)
        row = deepcopy(agent.get_parameter_value(row_name))
        row["action"] = dict(kind="select", request_id=uuid4().hex, expanded=True)
        base.send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name=row_name, value=row))
        base.send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name="additional_context", value=f"Connection retained Shot {number}: OFF 0 {{literal}}"))
        base.send(engine, SetParameterValueRequest(node_name=agent.name, parameter_name="output_schema", value={"type":"object", "properties":{f"slot{number}":{"type":"string"}}}))
        key = agent._hmb_active_slot_key
        agent._hmb_shot_results[key] = dict(status="succeeded", text=f"Retained output {number}", run_id=f"saved-result-{number}")
    agent._hmb_persist_shot_store()
    nodes[base.KINDS[5]] = []
    for number in range(1, 6):
        result = base.send(engine, CreateNodeRequest(node_type=base.KINDS[5], specific_library_name=schema.name,
            node_name=f"Retained Generator {number}", create_error_proxy_on_failure=False))
        node = engine.node_manager.get_node_by_name(result.node_name)
        for key, value in dict(resolution="480p", duration=4+number, output_file=f"retained-{number}.mov", resume_generation_id="job-"+str(number)*32).items():
            node.set_parameter_value(key, value, initial_setup=True)
        node.parameter_output_values.update(generation_id="job-"+str(number)*32,
            generation_status="queued", result_details=f"Retained Task {number}: not submitted by fixture", was_successful=False)
        nodes[base.KINDS[5]].append(node)
        await asyncio.sleep(.03)
    await base.settle(lambda: all(node._hmb_shot_channel_subscription()["enabled"] for node in nodes[base.KINDS[5]]), seconds=3)
    return nodes


async def exercise(engine, modules, folder, out):
    from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowRequest, RunWorkflowFromScratchRequest
    import _hmb_shot_routing as routing
    with ExitStack() as patches:
        library, schema, owner = hooks(engine, modules, patches)
        try:
            api = importlib.import_module("_hmb_connection_management")
            nodes = await setup(engine, modules, folder, schema)
            agent = nodes[base.KINDS[3]]
            original_edges, expected = edges(engine), authoring(nodes)

            def get(node):
                return base.send(engine, api.HMBGetNodeConnectionsRequest(node_name=node.name))

            async def manage(node, operation, *, token=None):
                view = get(node)
                return await engine.ahandle_request(api.HMBManageNodeConnectionsRequest(node_name=node.name,
                    operation=operation, expected_state_token=view.state_token if token is None else token,
                    broadcast_result=False))

            before_metadata = {name:deepcopy(engine.node_manager.get_node_by_name(name).metadata)
                for name in engine.node_manager._name_to_parent_flow_name}
            view = get(agent)
            assert not view.detached and view.can_disconnect and view.connections
            assert before_metadata == {name:deepcopy(engine.node_manager.get_node_by_name(name).metadata) for name in before_metadata}
            assert authoring(nodes) == expected and edges(engine) == original_edges
            record("initial_connection_query_is_read_only_with_five_shot_authoring_and_TaskIDs")
            durations = []
            with ExitStack() as getter_guards:
                for node in nodes[base.KINDS[5]]:
                    getter_guards.enter_context(mock.patch.object(node, "_hmb_generated_video_source_snapshot", deny))
                for _ in range(10):
                    start = time.perf_counter(); get(agent); durations.append((time.perf_counter()-start)*1000)
            assert authoring(nodes) == expected and edges(engine) == original_edges
            record("ten_read_only_queries_do_not_resolve_generated_media_or_mutate_authoring",
                installed_SDK_fixture_ms=dict(min=min(durations), max=max(durations), mean=sum(durations)/len(durations)))

            deleted = await engine.ahandle_request(DeleteNodeRequest(node_name=agent.name, broadcast_result=False))
            assert not deleted.succeeded() and "HMB_DELETE_CONNECTED" in str(deleted.result_details)
            record("connected_actual_Agent_delete_denied_before_detach")

            # A neighbour executing a model/render makes a topology mutation
            # unsafe even when the selected Agent itself is idle.
            from griptape_nodes.exe_types.node_types import NodeResolutionState
            busy_peer = nodes[base.KINDS[5]][2]
            old_state = busy_peer.state
            busy_peer.state = NodeResolutionState.RESOLVING
            try:
                busy_view = get(agent)
                denied = await manage(agent, "disconnect")
                assert not busy_view.can_disconnect and not denied.succeeded()
                assert authoring(nodes) == expected and edges(engine) == original_edges
                record("busy_connected_peer_rejects_detach_without_mutation_or_execution")
            finally:
                busy_peer.state = old_state
            locked = threading.Lock(); locked.acquire()
            worker = SimpleNamespace(is_alive=lambda: True)
            future = SimpleNamespace(done=lambda: False)
            active_generation = threading.Event(); active_generation.set()
            busy_shapes = (
                (nodes[base.KINDS[1]], "_hmb_active_operation", {"operation":"fixture"}),
                (nodes[base.KINDS[1]], "_hmb_pending_operation_id", "fixture-pending"),
                (nodes[base.KINDS[1]], "_hmb_process_lock", locked),
                (agent, "_hmb_shot_workers", {"fixture-slot":worker}),
                (agent, "_hmb_shot_execution_locks", {"fixture-slot":locked}),
                (agent, "_hmb_web_rerender_busy", lambda: True),
                (busy_peer, "_broker_action_running", True),
                (busy_peer, "_generation_refresh_running", True),
                (busy_peer, "_generation_run_active", active_generation),
                (busy_peer, "_hmb_web_rerender_active_claim", object()),
                (busy_peer, "_hmb_draft_finalize_future", future),
                (busy_peer, "_hmb_draft_final_status_future", future),
                (busy_peer, "_hmb_my_box_controller_instance", SimpleNamespace(_busy=True)),
                (agent, "_worker", worker), (agent, "_web_upload_worker", worker))
            try:
                for busy_node, field, value in busy_shapes:
                    selected = busy_node if busy_node is nodes[base.KINDS[1]] else agent
                    with mock.patch.object(busy_node, field, value, create=True):
                        state = get(selected)
                        refusal = await manage(selected, "disconnect")
                        assert not state.can_disconnect and not refusal.succeeded(), field
                        assert edges(engine) == original_edges and authoring(nodes) == expected, field
                record("actual_Picker_Agent_Generator_busy_fields_and_common_worker_shapes_reject_mutation", branches=len(busy_shapes))
            finally:
                locked.release()
            with mock.patch.object(busy_peer, "_generation_run_active", threading.Event()), mock.patch.object(busy_peer, "_hmb_web_rerender_active_claim", None, create=True):
                assert get(agent).can_disconnect
            record("finished_web_generation_releases_connection_controls")
            with mock.patch.object(agent, "_hmb_thumbnail_worker", worker, create=True), mock.patch.object(agent, "_hmb_catalog_observer", worker, create=True):
                assert get(agent).can_disconnect
            record("passive_thumbnail_and_catalog_observer_do_not_lock_connection_controls")

            detached = await manage(agent, "disconnect")
            assert detached.succeeded(), str(detached.result_details)
            assert get(agent).detached
            for _ in range(3):
                routing.reconcile_shot_routing(nodes[base.KINDS[0]])
                await asyncio.sleep(.03)
            after_edges = edges(engine)
            assert not any(agent.name in (edge[0], edge[2]) for edge in after_edges)
            assert after_edges == {edge for edge in original_edges if agent.name not in (edge[0], edge[2])}
            assert authoring(nodes) == expected
            record("disconnect_wire_and_REMOTE_holds_auto_rebind_and_preserves_all_five_documents_results_TaskIDs")
            assert not importlib.import_module("_hmb_deletion_guard").connected_targets(engine, [agent.name])

            # Recipes/peer UUIDs must survive native save and generated replay;
            # replay itself performs no model or provider execution.
            saved = Path(base.send(engine, SaveWorkflowRequest(file_name=str(folder/"detached-common.py"), display_name="Private detached connection fixture")).file_path)
            await asyncio.sleep(.06)  # Native detached serializer post hooks release their admission.
            saved_bytes = saved.read_bytes()
            identities = {name:deepcopy(engine.node_manager.get_node_by_name(name).metadata.get("hmb_connection_identity_v1"))
                for name in engine.node_manager._name_to_parent_flow_name}
            recipe = deepcopy(agent.metadata.get("hmb_connection_management_v1"))
            assert recipe and any(identities.values())
            deletion = importlib.import_module("_hmb_deletion_guard")
            await base.asend(engine, deletion.HMBPrepareWorkflowTransitionRequest())
            await asyncio.sleep(.03)
            saved_text = saved.read_text("utf-8")
            tree = ast.parse(saved_text)
            fn = next(item for item in tree.body if isinstance(item, ast.AsyncFunctionDef))
            omitted = {line for item in fn.body if "RegisterLibraryFromFileRequest" in ast.unparse(item)
                for line in range(item.lineno, item.end_lineno+1)}
            replay = folder/"private-detached-replay.py"
            replay.write_text("".join(text for line,text in enumerate(saved_text.splitlines(keepends=True),1) if line not in omitted), encoding="utf-8")
            # Native file-open owns context setup and deferred hydration. The
            # only omitted command re-registers the already loaded library.
            await base.asend(engine, RunWorkflowFromScratchRequest(file_path=str(replay)))
            for kind in base.KINDS[:5]: nodes[kind] = engine.node_manager.get_node_by_name(nodes[kind].name)
            nodes[base.KINDS[5]] = [engine.node_manager.get_node_by_name(node.name) for node in nodes[base.KINDS[5]]]
            agent = nodes[base.KINDS[3]]
            await asyncio.sleep(.15)
            assert get(agent).detached and not any(agent.name in (edge[0], edge[2]) for edge in edges(engine))
            assert agent.metadata["hmb_connection_management_v1"] == recipe
            assert {name:deepcopy(engine.node_manager.get_node_by_name(name).metadata.get("hmb_connection_identity_v1")) for name in identities} == identities
            assert authoring(nodes) == expected
            assert saved.read_bytes() == saved_bytes
            record("detached_native_save_and_generated_reopen_preserves_peer_UUID_recipe_and_five_shot_authoring")

            reconnected = await manage(agent, "reconnect")
            if not reconnected.succeeded():
                diagnostics = []
                for row in get(agent).connections:
                    source_node = engine.node_manager.get_node_by_name(row["source_node_name"])
                    target_node = engine.node_manager.get_node_by_name(row["target_node_name"])
                    def declared(node):
                        sub = routing._subscription_for(node)
                        if sub is None: return []
                        values = routing._manager_shot_subscriptions(node, sub.kind) if routing._is_shot_manager(node) else (sub,)
                        return [dict(enabled=value.enabled, channel=value.channel_uuid, shot=value.shot_uuid, number=value.shot_number, name=value.shot_name) for value in values]
                    try:
                        api._validate_shots(row, source_node, target_node); problem = ""
                    except Exception as exc: problem = str(exc)
                    diagnostics.append(dict(source=source_node.name, target=target_node.name, expected=row.get("shots"),
                        source_declared=declared(source_node), target_declared=declared(target_node), error=problem))
                (out/"reconnect-shot-diagnostic.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
            assert reconnected.succeeded(), str(reconnected.result_details)
            await base.settle(lambda: edges(engine) == original_edges, seconds=3)
            assert authoring(nodes) == expected and not get(agent).detached
            record("exact_original_peers_reconnect_without_reexecution_or_authoring_loss")

            # A recipe cannot silently reconnect a Shot removed after detach.
            # Restore the synthetic authored source afterwards; no render is
            # submitted by either source update or the rejected reconnect.
            assert (await manage(agent, "disconnect")).succeeded()
            source = nodes[base.KINDS[0]]
            original_source_state = deepcopy(source._current_state())
            four = deepcopy(original_source_state)
            four["shot_routing"]["shots"] = four["shot_routing"]["shots"][:4]
            source._cache_shot_routing_snapshot(four, force=True)
            source._publish_state(four)
            await asyncio.sleep(.1)
            before_failed = edges(engine)
            refused = await manage(agent, "reconnect")
            assert not refused.succeeded() and edges(engine) == before_failed
            assert all(node.get_parameter_value("resume_generation_id") == "job-"+str(number)*32
                for number, node in enumerate(nodes[base.KINDS[5]], 1))
            record("removed_Shot_in_detached_recipe_rejects_reconnect_without_losing_existing_TaskIDs")
            source._cache_shot_routing_snapshot(original_source_state, force=True)
            source._publish_state(original_source_state)
            await asyncio.sleep(.1)
            assert (await manage(agent, "reconnect")).succeeded()

            # Detaching a real Only Generator with no links is a no-op, never
            # an invitation to auto-select a Shot when restored.
            from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
            import HMB_Seedance_Execution_Mode_Host_Regression as modes
            only_name = base.send(engine, CreateNodeRequest(node_type=base.KINDS[5], specific_library_name=schema.name,
                node_name="Explicit Only connection test", override_parent_flow_name="OfflineCommonConnections",
                create_error_proxy_on_failure=False)).node_name
            only = engine.node_manager.get_node_by_name(only_name)
            modes.select(engine, modules[base.KINDS[5]], only)
            before_only_edges = edges(engine)
            before_only_values = deepcopy(dict(only.parameter_values))
            only_view = get(only)
            assert not only_view.can_disconnect
            await manage(only, "disconnect")
            await manage(only, "reconnect")
            assert only._hmb_seedance_execution_mode() == "only"
            assert edges(engine) == before_only_edges and dict(only.parameter_values) == before_only_values
            record("unbound_explicit_Only_generator_cannot_gain_a_Shot_through_connection_controls")
            record("actual_five_Shot_roundtrip_complete", generators=len(nodes[base.KINDS[5]]))
            await future_wire_cases(engine, api, schema, library, folder)
            assert not ATTEMPTS
        finally:
            owner.before_library_unregistered(schema, library)


async def future_wire_cases(engine, api, schema, library, folder):
    from griptape_nodes.exe_types.node_types import DataNode
    from griptape_nodes.exe_types.core_types import ParameterMode
    from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import (
        CreateNodeRequest, DeleteNodeRequest, DuplicateSelectedNodesRequest, MoveNodeToNewFlowRequest, SetNodeMetadataRequest)
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
    from griptape_nodes.retained_mode.events.object_events import RenameObjectRequest
    from griptape_nodes.retained_mode.events.connection_events import (
        CreateConnectionRequest, DeleteConnectionRequest, CreateConnectionResultFailure, DeleteConnectionResultFailure)

    class FutureHMBConnectionTool(DataNode):
        def __init__(self, name, metadata=None):
            super().__init__(name, metadata)
            for port, mode in (("input", ParameterMode.INPUT), ("output", ParameterMode.OUTPUT)):
                self.add_parameter(ParameterString(name=port, default_value="retained local "+port,
                    allowed_modes={mode, ParameterMode.PROPERTY}))
            self.parameter_output_values["output"] = "future cached result"
        def process(self): deny()

    library.register_lazy_node_type("FutureHMBConnectionTool", schema.nodes[0].metadata, lambda:FutureHMBConnectionTool)
    flow = base.send(engine, CreateFlowRequest(parent_flow_name="OfflineCommonConnections", flow_name="Future connection contracts", set_as_new_context=True)).flow_name

    def make(name):
        result = base.send(engine, CreateNodeRequest(node_type="FutureHMBConnectionTool", specific_library_name=schema.name,
            node_name=name, override_parent_flow_name=flow, create_error_proxy_on_failure=False))
        return engine.node_manager.get_node_by_name(result.node_name)

    def wire(source, target, *, internal=False):
        edge = dict(source_node_name=source.name, source_parameter_name="output", target_node_name=target.name, target_parameter_name="input")
        base.send(engine, CreateConnectionRequest(**edge, initial_setup=True, is_node_group_internal=internal))
        return edge

    def get(node): return base.send(engine, api.HMBGetNodeConnectionsRequest(node_name=node.name))

    async def manage(node, operation, token=None):
        view = get(node)
        return await engine.ahandle_request(api.HMBManageNodeConnectionsRequest(node_name=node.name,
            operation=operation, expected_state_token=view.state_token if token is None else token,
            broadcast_result=False))

    def retained():
        return dict(edges=edges(engine), nodes={name:dict(object=id(node), metadata=deepcopy(node.metadata),
            values=deepcopy(dict(node.parameter_values)), outputs=deepcopy(dict(node.parameter_output_values)))
            for name in engine.node_manager._name_to_parent_flow_name
            if isinstance((node:=engine.node_manager.get_node_by_name(name)), FutureHMBConnectionTool)})

    source, a, b = make("future source"), make("future target A"), make("future target B")
    edge_a, edge_b = wire(source, a), wire(source, b)
    initial = get(source)
    assert initial.can_disconnect and len(initial.connections) == 2
    original = retained()
    # Inject one real native edge deletion, then a native refusal on the next
    # edge. The implementation must undo the first deletion and its recipe.
    manager = engine.event_manager
    original_delete = manager._request_type_to_manager[DeleteConnectionRequest]
    original_metadata_handler = manager._request_type_to_manager[SetNodeMetadataRequest]
    metadata_writes = []
    def observe_metadata_write(request):
        result = original_metadata_handler(request)
        metadata_writes.append(dict(node=request.node_name, values=deepcopy(request.metadata),
            broadcast=request.broadcast_result, succeeded=result.succeeded()))
        return result
    count = [0]
    def fail_second_delete(request):
        count[0] += 1
        if count[0] == 2: return DeleteConnectionResultFailure(result_details="Injected private native deletion failure")
        return original_delete(request)
    with mock.patch.dict(manager._request_type_to_manager, {DeleteConnectionRequest:fail_second_delete,
            SetNodeMetadataRequest:observe_metadata_write}):
        failed = await manage(source, "disconnect")
    assert count[0] >= 2 and not failed.succeeded()
    after_rollback = retained()
    neutral = {"hmb_connection_identity_v1":"", "hmb_connection_management_v1":{}, "hmb_connection_fences_v1":[]}
    for name, before_node in original["nodes"].items():
        after_metadata = after_rollback["nodes"][name]["metadata"]
        introduced = {key for key in neutral if key not in before_node["metadata"] and key in after_metadata}
        for key, value in neutral.items():
            if key not in before_node["metadata"] and after_metadata.get(key) == value:
                after_metadata.pop(key, None)
        final_write = next((row for row in reversed(metadata_writes) if row["node"] == name), None)
        if final_write is not None:
            assert final_write["broadcast"] is True and final_write["succeeded"]
            assert all(final_write["values"].get(key) == neutral[key] for key in introduced)
    assert after_rollback == original
    record("partial_native_disconnect_failure_rolls_back_edges_inputs_results_and_broadcasts_neutral_absent_metadata", neutral_only_for_previously_absent_reserved_keys=True)

    detached = await manage(source, "disconnect")
    assert detached.succeeded() and get(source).detached
    after_detach = retained()
    with engine.context_manager.node(node=source):
        refused = engine.handle_request(CreateConnectionRequest(source_parameter_name="output",
            target_node_name=a.name, target_parameter_name="input", initial_setup=True, broadcast_result=False))
        assert not refused.succeeded() and "HMB_CONNECTION_DETACHED" in str(refused.result_details)
    with engine.context_manager.node(node=a):
        refused = engine.handle_request(CreateConnectionRequest(source_node_name=source.name,
            source_parameter_name="output", target_parameter_name="input", initial_setup=True, broadcast_result=False))
        assert not refused.succeeded() and "HMB_CONNECTION_DETACHED" in str(refused.result_details)
    assert retained() == after_detach
    record("implicit_Current_Node_source_and_target_cannot_bypass_detached_connection_fence")
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
    refused = await engine.ahandle_request(ResolveNodeRequest(node_name=source.name, broadcast_result=False))
    assert not refused.succeeded() and "HMB_CONNECTION_DETACHED" in str(refused.result_details)
    assert retained() == after_detach and not ATTEMPTS
    record("detached_execution_is_rejected_before_process_or_provider")
    stale = await manage(source, "reconnect", initial.state_token)
    assert not stale.succeeded() and retained() == after_detach
    record("stale_connection_panel_token_cannot_reconnect_after_topology_change")

    original_create = manager._request_type_to_manager[CreateConnectionRequest]
    count = [0]
    def fail_second_create(request):
        count[0] += 1
        if count[0] == 2: return CreateConnectionResultFailure(result_details="Injected private native creation failure")
        return original_create(request)
    with mock.patch.dict(manager._request_type_to_manager, {CreateConnectionRequest:fail_second_create}):
        failed = await manage(source, "reconnect")
    assert count[0] >= 2 and not failed.succeeded()
    assert retained() == after_detach
    record("partial_native_reconnect_failure_removes_first_restored_edge_and_preserves_recipe")

    other = make("unrelated occupied source")
    occupied = dict(source_node_name=other.name, source_parameter_name="output", target_node_name=a.name, target_parameter_name="input")
    public_occupy = engine.handle_request(CreateConnectionRequest(**occupied, initial_setup=True, broadcast_result=False))
    if not public_occupy.succeeded():
        # A native/plugin race can bypass the pre-dispatch hook. Reconnect must
        # still revalidate occupancy instead of clobbering that existing edge.
        native_occupy = engine.flow_manager.on_create_connection_request(CreateConnectionRequest(**occupied, initial_setup=True, broadcast_result=False))
        assert native_occupy.succeeded(), str(native_occupy.result_details)
    before = retained()
    failed = await manage(source, "reconnect")
    assert not failed.succeeded() and retained() == before
    assert (other.name, "output", a.name, "input") in edges(engine)
    record("occupied_target_input_is_never_overwritten_by_recipe_reconnect")
    base.send(engine, DeleteConnectionRequest(**occupied))
    assert (await manage(source, "reconnect")).succeeded()
    assert not get(source).detached
    record("future_unknown_HMB_type_reconnects_original_exact_peers")

    await manage(source, "disconnect")
    await base.asend(engine, DeleteNodeRequest(node_name=a.name))
    replacement = make(a.name)
    assert replacement is not a
    before = retained()
    failed = await manage(source, "reconnect")
    assert not failed.succeeded() and retained() == before
    record("same_name_replacement_cannot_acquire_missing_original_peer_recipe")

    moving_source, moving_peer = make("moving source"), make("moving exact peer")
    wire(moving_source, moving_peer)
    assert (await manage(moving_source, "disconnect")).succeeded()
    foreign_flow = base.send(engine, CreateFlowRequest(parent_flow_name="OfflineCommonConnections", flow_name="Foreign reconnect scope", set_as_new_context=False)).flow_name
    base.send(engine, MoveNodeToNewFlowRequest(node_name=moving_peer.name, target_flow_name=foreign_flow))
    before = retained()
    failed = await manage(moving_source, "reconnect")
    assert not failed.succeeded() and retained() == before
    record("exact_peer_moved_to_other_flow_cannot_reconnect_cross_scope")

    clone_source, original_peer = make("clone source"), make("clone original peer")
    wire(clone_source, original_peer)
    assert (await manage(clone_source, "disconnect")).succeeded()
    original_uuid = deepcopy(original_peer.metadata.get("hmb_connection_identity_v1"))
    duplicated = await base.asend(engine, DuplicateSelectedNodesRequest(nodes_to_duplicate=[[original_peer.name, "0"]]))
    assert len(duplicated.node_names) == 1
    clone = engine.node_manager.get_node_by_name(duplicated.node_names[0])
    assert clone is not original_peer
    before = retained()
    result = await manage(clone_source, "reconnect")
    if clone.metadata.get("hmb_connection_identity_v1") == original_uuid:
        assert not result.succeeded() and retained() == before
    else:
        assert result.succeeded()
        assert (clone_source.name, "output", original_peer.name, "input") in edges(engine)
        assert (clone_source.name, "output", clone.name, "input") not in edges(engine)
    record("native_clone_copied_metadata_identity_cannot_be_confused_with_original_peer")

    rename_source, rename_peer = make("rename source"), make("rename original peer")
    wire(rename_source, rename_peer)
    assert (await manage(rename_source, "disconnect")).succeeded()
    expected_uuid = deepcopy(rename_peer.metadata["hmb_connection_identity_v1"])
    recipe_before_rename = deepcopy(rename_source.metadata["hmb_connection_management_v1"])
    base.send(engine, RenameObjectRequest(object_name=rename_peer.name, requested_name="renamed exact original peer", allow_next_closest_name_available=False))
    assert rename_peer.metadata["hmb_connection_identity_v1"] == expected_uuid
    renamed_view = get(rename_source)
    assert renamed_view.can_reconnect
    assert rename_source.metadata["hmb_connection_management_v1"] == recipe_before_rename
    restored = await manage(rename_source, "reconnect")
    assert restored.succeeded(), str(restored.result_details)
    assert (rename_source.name, "output", rename_peer.name, "input") in edges(engine)
    record("native_peer_rename_keeps_exact_UUID_and_reconnects_current_name_without_rewriting_saved_recipe_on_query")

    internal_source, internal_target = make("internal original source"), make("internal original target")
    wire(internal_source, internal_target, internal=True)
    def retained_internal_flag():
        matches = [connection for connection in engine.flow_manager.get_connections().connections.values()
            if connection.source_node is internal_source and connection.target_node is internal_target
            and connection.source_parameter.name == "output" and connection.target_parameter.name == "input"]
        assert len(matches) == 1
        return matches[0].is_node_group_internal
    assert retained_internal_flag() is True
    internal_view = get(internal_source)
    assert any(row.get("is_node_group_internal") is True for row in internal_view.connections)
    assert (await manage(internal_source, "disconnect")).succeeded()
    assert (await manage(internal_source, "reconnect")).succeeded()
    assert retained_internal_flag() is True
    record("native_internal_connection_flag_survives_disconnect_and_reconnect_despite_public_DTO_omission")

    for protected, label in ((moving_source, "foreign_flow_peer"), (clone_source, "live_or_duplicate_peer")):
        before = retained()
        view = get(protected)
        refused = await manage(protected, "forget_missing")
        assert not view.can_forget_missing and not refused.succeeded()
        assert retained() == before
        record("forget_missing_rejects_"+label+"_without_mutation")

    orphan_source, orphan_target = make("orphan original source"), make("orphan preserved target")
    wire(orphan_source, orphan_target)
    assert (await manage(orphan_source, "disconnect")).succeeded()
    before = retained()
    assert not get(orphan_target).can_forget_missing
    refused = await manage(orphan_target, "forget_missing")
    assert not refused.succeeded() and retained() == before
    record("forget_missing_cannot_erase_a_live_original_owner_fence")
    await base.asend(engine, DeleteNodeRequest(node_name=orphan_source.name))
    assert get(orphan_target).can_forget_missing
    replacement_source = make(orphan_source.name)
    assert replacement_source is not orphan_source
    before = retained()
    bypass = engine.handle_request(CreateConnectionRequest(source_node_name=replacement_source.name,
        source_parameter_name="output", target_node_name=orphan_target.name, target_parameter_name="input",
        initial_setup=True, broadcast_result=False))
    assert not bypass.succeeded() and "HMB_CONNECTION_DETACHED" in str(bypass.result_details)
    assert retained() == before
    record("deleted_original_owner_same_name_replacement_is_blocked_before_explicit_orphan_cleanup")
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    old_state = orphan_target.state
    orphan_target.state = NodeResolutionState.RESOLVING
    try:
        before = retained()
        refused = await manage(orphan_target, "forget_missing")
        assert not get(orphan_target).can_forget_missing and not refused.succeeded()
        assert retained() == before
        record("orphan_cleanup_rejects_busy_target_without_mutation")
    finally:
        orphan_target.state = old_state
    target_values = deepcopy(dict(orphan_target.parameter_values))
    target_outputs = deepcopy(dict(orphan_target.parameter_output_values))
    before_edges = edges(engine)
    forgotten = await manage(orphan_target, "forget_missing")
    assert forgotten.succeeded(), str(forgotten.result_details)
    assert not get(orphan_target).can_forget_missing
    assert dict(orphan_target.parameter_values) == target_values and dict(orphan_target.parameter_output_values) == target_outputs
    assert edges(engine) == before_edges  # Explicit cleanup performs no rebind/reconcile.
    wire(replacement_source, orphan_target)
    assert (replacement_source.name, "output", orphan_target.name, "input") in edges(engine)
    record("explicit_orphan_cleanup_preserves_inputs_results_and_allows_normal_new_connection_without_auto_rebind")

    deleted = await engine.ahandle_request(DeleteNodeRequest(node_name=source.name, broadcast_result=False))
    assert deleted.succeeded(), str(deleted.result_details)
    record("explicitly_detached_future_HMB_can_be_deleted")


async def fixture_smoke(engine, modules, folder, out):
    with ExitStack() as patches:
        library, schema, owner = hooks(engine, modules, patches)
        try:
            nodes = await setup(engine, modules, folder, schema)
            state = authoring(nodes)
            assert len(state["source_shots"]) == 5
            assert len(state["agent_results"]) == 5 and len(state["generators"]) == 5
            assert all(row["values"]["resume_generation_id"].startswith("job-") for row in state["generators"].values())
            record("five_Shot_offline_authoring_and_retained_Task_fixture_ready")
        finally:
            owner.before_library_unregistered(schema, library)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "reports/predeploy-usability-fixes-20261024/common-connection-sdk")
    parser.add_argument("--fixture-only", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    source_before = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in PRODUCTS}
    started = time.perf_counter()
    passed = False
    with tempfile.TemporaryDirectory(prefix="hmb-common-connection-") as temp:
        folder = Path(temp)
        env = {key:str(folder/key) for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR", "GTN_CONFIG_WORKSPACE_DIRECTORY", "HMB_IMAGE_PROJECTS_ROOT")}
        for value in env.values(): Path(value).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", deny):
            from griptape_nodes.retained_mode.engine import engine_scope
            modules = {kind:importlib.import_module(kind) for kind in base.KINDS}
            logging.disable(logging.CRITICAL)
            try:
                with engine_scope() as engine:
                    with asyncio.Runner() as runner: runner.run((fixture_smoke if args.fixture_only else exercise)(engine, modules, folder, out))
                passed = True
            finally:
                logging.shutdown()
                source_after = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in PRODUCTS}
                result = dict(passed=passed and not ATTEMPTS and source_before==source_after, cases=CASES,
                    provider_or_paid_calls=0, forbidden_execution_attempts=len(ATTEMPTS),
                    source_stable=source_before==source_after, source_before=source_before, source_after=source_after,
                    elapsed_seconds=time.perf_counter()-started,
                    scope="Private installed SDK, synthetic ten-node five-Shot fixture plus future HMB native wires; no desktop/provider/render")
                (out/"common-connection-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(passed=result["passed"], cases=len(CASES), source_stable=result["source_stable"], paid_calls=0)))
    assert result["passed"]


if __name__ == "__main__": main()
