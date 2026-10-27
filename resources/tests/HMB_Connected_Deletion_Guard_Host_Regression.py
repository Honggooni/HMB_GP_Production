"""Isolated installed-SDK pre-mutation deletion guard contracts.

Native create/connection/reset/flow/save/load/clear handlers remain real.  No
desktop graph, provider, account, media upload or model execution is accessed.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib
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
sys.path[:0] = [str(ROOT), str(ROOT / "resources/tests")]
sys.dont_write_bytecode = True
import HMB_Seedance_Execution_Mode_Host_Regression as harness


def snapshot(engine):
    """Retained identity, authored results, wires and context before mutation."""
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
    nodes = {}; edges = set()
    for name, flow in engine.node_manager._name_to_parent_flow_name.items():
        node = engine.node_manager.get_node_by_name(name)
        nodes[name] = (id(node), flow, deepcopy(node.metadata),
            deepcopy(dict(node.parameter_values)), deepcopy(dict(node.parameter_output_values)),
            getattr(node, "deleted_calls", 0), getattr(node.parent_group, "name", None))
        result = harness.send(engine, ListConnectionsForNodeRequest(node_name=name, include_internal=True))
        for edge in result.outgoing_connections:
            edges.add((name, edge.source_parameter_name, edge.target_node_name,
                       edge.target_parameter_name, bool(getattr(edge, "is_node_group_internal", False))))
    context = engine.context_manager
    return dict(nodes=nodes, edges=edges, flows=deepcopy(engine.flow_manager._name_to_parent_name),
        objects={name: id(obj) for name, obj in engine.object_manager._name_to_objects.items()},
        workflow=context.get_current_workflow_name() if context.has_current_workflow() else None,
        flow=context.get_current_flow().name if context.has_current_flow() else None,
        node=context.get_current_node().name if context.has_current_node() else None)


async def exercise(engine, _phase, out):
    from griptape_nodes.exe_types.node_types import DataNode
    from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
    from griptape_nodes.exe_types.core_types import ParameterMode
    from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest, ResetNodeToDefaultsRequest
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, DeleteFlowRequest, SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
    from griptape_nodes.retained_mode.events.workflow_events import (
        DeleteWorkflowRequest, SaveWorkflowFileFromSerializedFlowRequest,
        RunWorkflowFromScratchRequest, RunWorkflowFromRegistryRequest, RegisterWorkflowRequest)
    bootstrap = importlib.import_module("_hmb_library_bootstrap")
    guard = importlib.import_module("_hmb_deletion_guard")
    routing = importlib.import_module("_hmb_shot_routing")
    migration = importlib.import_module("_hmb_workflow_migration")

    class FutureHMBTool(DataNode):
        def __init__(self, name, metadata=None):
            super().__init__(name, metadata)
            self.deleted_calls = 0
            self.deps = []
            self.subscription = None
            self.manager = False
            self.manager_rows = []
            self.execution_mode = "shot"
            self.completed_source = {}
            self.standalone_catalog = {}
            for port, mode in (("input", ParameterMode.INPUT), ("output", ParameterMode.OUTPUT)):
                self.add_parameter(ParameterString(name=port, default_value="unchanged", allowed_modes={mode, ParameterMode.PROPERTY}))
            self.parameter_output_values["output"] = "cached result preserved"

        def process(self):
            harness.deny()

        def after_node_deleted(self):
            self.deleted_calls += 1

        def _hmb_deletion_dependencies(self):
            return self.deps

        def _hmb_shot_channel_subscription(self):
            return self.subscription

        def _hmb_shot_manager_enabled(self): return self.manager
        def _hmb_prompt_shot_subscriptions(self): return self.manager_rows
        def _hmb_agent_shot_subscriptions(self): return self.manager_rows
        def _hmb_finish_look_shot_subscriptions(self): return self.manager_rows
        def _hmb_seedance_execution_mode(self): return self.execution_mode
        def _hmb_generated_video_source_snapshot(self): return self.completed_source
        def _hmb_standalone_shot_routing_catalog(self): return self.standalone_catalog

    # The guard is metadata-driven: these are real native instances with real
    # retained wires, including one type that is absent from the product list.
    schema = harness.register(engine, {})
    library = LibraryRegistry.get_library(schema.name)
    metadata = schema.nodes[0].metadata
    library.register_lazy_node_type("FutureHMBTool", metadata, lambda: FutureHMBTool)
    engine.event_manager.initialize_queue()
    manager = engine.event_manager
    owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
    owner._registrations = set()
    with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
        owner.before_library_nodes_loaded(schema, library)
    assert len(owner._registrations) == 1, "Real library-load hook did not register guard"
    registration = next(iter(owner._registrations))
    assert registration.deletion_handlers is not None
    harness.record("actual_before_library_nodes_loaded_installs_typed_handlers_and_guard")

    def create(name, flow=None, hmb=True):
        result = harness.send(engine, CreateNodeRequest(node_type="FutureHMBTool", specific_library_name=schema.name,
            node_name=name, override_parent_flow_name=flow, initial_setup=True, create_error_proxy_on_failure=False))
        node = engine.node_manager.get_node_by_name(result.node_name)
        if not hmb: node.metadata["library"] = "Ordinary_External_Library"
        return node

    def wire(source, target, *, internal=False):
        edge = dict(source_node_name=source.name, source_parameter_name="output", target_node_name=target.name, target_parameter_name="input")
        harness.send(engine, CreateConnectionRequest(**edge, initial_setup=True, is_node_group_internal=internal))
        return edge

    async def blocked(request, label):
        before = snapshot(engine)
        request.broadcast_result = False
        result = await engine.ahandle_request(request)
        assert not result.succeeded(), (label, type(result).__name__, str(result.result_details))
        assert guard.CODE in str(result.result_details), (label, str(result.result_details))
        assert snapshot(engine) == before, label + " partially mutated the retained graph"
        harness.record(label, result_type=type(result).__name__, retained_state_unchanged=True)

    def subscription(kind, channel="guard-channel", enabled=True):
        return dict(schema=routing.SUBSCRIPTION_SCHEMA, version=1, participant_kind=kind,
            enabled=enabled, channel_uuid=channel, shot_uuid="guard-shot", shot_number=1, shot_name="Kept shot")

    try:
        with ExitStack() as patches:
            patches.enter_context(mock.patch.object(registration, "start_web_worker", lambda: None))
            patches.enter_context(mock.patch.object(migration, "schedule_loaded_flow_migrations", lambda *a: None))
            for key in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                patches.enter_context(mock.patch.object(routing, key, lambda *a, **k: False))
            flow = harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="DeletionGuardSDK")).flow_name
            source, target = create("connected source"), create("connected target")
            edge = wire(source, target)
            before = snapshot(engine)
            for names in (None, "connected source", [""], [17], ["not retained"] * 4097):
                invalid = engine.handle_request(guard.HMBCheckNodeDeletionRequest(node_names=names, broadcast_result=False))
                assert not invalid.succeeded() and snapshot(engine) == before
            harness.record("malformed_or_oversized_batch_preflight_fails_without_mutation", cases=5)
            for node in (source, target):
                await blocked(DeleteNodeRequest(node_name=node.name), "native_delete_" + node.name.replace(" ", "_"))
                request = ResetNodeToDefaultsRequest(node_name=node.name)
                request.force = True
                await blocked(request, "native_reset_force_" + node.name.replace(" ", "_"))
            with engine.context_manager.node(node=source):
                await blocked(DeleteNodeRequest(), "implicit_current_context_delete_does_not_pop_node")
                await blocked(ResetNodeToDefaultsRequest(), "implicit_current_context_reset_does_not_pop_node")

            # Every current exported HMB type and a hypothetical future type
            # receives the same protection; class-specific behavior is not faked.
            for definition in schema.nodes:
                source.metadata["node_type"] = definition.class_name
                check = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[source.name]))
                assert check.can_delete is False and source.name in check.blocked
            source.metadata["node_type"] = "FutureHMBTool2040"
            await blocked(DeleteNodeRequest(node_name=source.name), "future_HMB_metadata_type_is_protected")
            harness.record("all_manifest_HMB_types_share_metadata_protection", types=len(schema.nodes))

            hidden_source, hidden_target = create("hidden REMOTE source"), create("Only with real wire")
            hidden_target.subscription = subscription("seedance", enabled=False)
            hidden_edge = wire(hidden_source, hidden_target, internal=True)
            await blocked(DeleteNodeRequest(node_name=hidden_target.name), "Only_real_internal_wire_still_blocks_delete")
            await blocked(DeleteNodeRequest(node_name=hidden_source.name), "hidden_internal_REMOTE_outgoing_blocks_delete")

            publisher, remote = create("remote authority"), create("remote subscriber")
            publisher.subscription = subscription("image_asset")
            remote.subscription = subscription("video_picker")
            await blocked(DeleteNodeRequest(node_name=publisher.name), "catalog_only_remote_authority_blocks_delete")
            await blocked(DeleteNodeRequest(node_name=remote.name), "catalog_only_remote_subscriber_blocks_delete")
            remote.subscription = subscription("video_picker", enabled=False)
            assert not guard.connected_targets(engine, [remote.name])
            harness.record("Only_disabled_subscription_without_wire_does_not_block")

            def remote_role(name, kind, case_flow, channel="remote-case"):
                node = create(name, case_flow)
                node.subscription = subscription(kind, channel)
                return node

            def assert_remote_peers(node, expected, label):
                before = snapshot(engine)
                peers = set(guard.connected_targets(engine, [node.name]).get(node.name, []))
                assert peers == {item.name for item in expected}, (label, peers, [item.name for item in expected])
                assert snapshot(engine) == before
                harness.record(label, actual_peers=sorted(peers), retained_state_unchanged=True)

            # No ImageAsset in this isolated native flow: standalone Picker is
            # a supported Seedance/LUT authority, but not a Finish authority.
            standalone_flow = harness.send(engine, CreateFlowRequest(parent_flow_name=flow, flow_name="Standalone remote", set_as_new_context=False)).flow_name
            standalone = remote_role("standalone Picker", "video_picker", standalone_flow)
            standalone_gen = remote_role("standalone Seedance", "seedance", standalone_flow)
            assert_remote_peers(standalone_gen, [standalone], "standalone_Picker_to_Seedance_before_wire_is_protected")
            assert_remote_peers(standalone, [standalone_gen], "standalone_Picker_inverse_dependency_is_protected")
            standalone_gen.execution_mode = "only"
            assert_remote_peers(standalone_gen, [], "explicit_Only_no_wire_is_not_a_remote_dependency")
            standalone_gen.execution_mode = "waiting"
            assert_remote_peers(standalone_gen, [], "waiting_no_wire_is_not_a_remote_dependency")
            standalone_gen.execution_mode = "only"
            standalone_finish = remote_role("unsupported standalone Finish", "finish_look", standalone_flow)
            assert_remote_peers(standalone_finish, [], "standalone_Picker_to_Finish_is_not_invented")
            standalone_lut = remote_role("standalone LUT", "color_lut", standalone_flow)
            assert_remote_peers(standalone_lut, [standalone], "standalone_Picker_to_LUT_before_wire_is_protected")

            manager_flow = harness.send(engine, CreateFlowRequest(parent_flow_name=flow, flow_name="Inactive manager slot", set_as_new_context=False)).flow_name
            managed_asset = remote_role("manager source", "image_asset", manager_flow, "manager-case")
            managed_prompt = remote_role("manager Prompt", "prompt", manager_flow, "manager-case")
            managed_agent = remote_role("manager Agent", "agent", manager_flow, "manager-case")
            for node, kind in ((managed_prompt, "prompt"), (managed_agent, "agent")):
                node.manager = True
                node.manager_rows = []
                for number in range(1, 6):
                    row = subscription(kind, "manager-case")
                    row.update(shot_uuid=f"managed-{number}", shot_number=number, shot_name=f"Slot {number}")
                    node.manager_rows.append(row)
                node.subscription = deepcopy(node.manager_rows[0])
            managed_gen = remote_role("managed Shot5 Generator", "seedance", manager_flow, "manager-case")
            managed_gen.subscription.update(shot_uuid="managed-5", shot_number=5, shot_name="Slot 5")
            assert_remote_peers(managed_gen, [managed_asset, managed_agent], "inactive_manager_Shot5_exact_agent_dependency_retained")
            assert_remote_peers(managed_agent, [managed_asset, managed_prompt, managed_gen], "manager_all5_rows_protect_exact_prompt_and_inactive_target")
            managed_gen.subscription["shot_name"] = "Foreign name"
            assert_remote_peers(managed_gen, [managed_asset], "mismatched_manager_Shot5_name_cannot_select_agent")

            ambiguous_flow = harness.send(engine, CreateFlowRequest(parent_flow_name=flow, flow_name="Ambiguous remote", set_as_new_context=False)).flow_name
            first_pub = remote_role("duplicate publisher A", "image_asset", ambiguous_flow, "duplicate-case")
            second_pub = remote_role("duplicate publisher B", "image_asset", ambiguous_flow, "duplicate-case")
            ambiguous = remote_role("ambiguous subscriber", "seedance", ambiguous_flow, "duplicate-case")
            assert_remote_peers(ambiguous, [], "duplicate_publisher_does_not_invent_remote_owner")
            second_pub.subscription = None
            first_pub._hmb_catalog_search_authority = {"shot_routing": {"publisher_instance_uuid": "current publisher", "channel_uuid": "duplicate-case"}}
            ambiguous._hmb_shot_catalog_snapshot = {"publisher_instance_uuid": "foreign publisher", "channel_uuid": "duplicate-case"}
            assert_remote_peers(ambiguous, [], "explicit_foreign_publisher_receipt_rejects_scalar_match")

            receipt_flow = harness.send(engine, CreateFlowRequest(parent_flow_name=flow, flow_name="Completed accepted origin", set_as_new_context=False)).flow_name
            receipt_source = remote_role("completed Only Generator", "seedance", receipt_flow, "receipt-case")
            receipt_source.execution_mode = "only"
            receipt_target = remote_role("accepted LUT origin", "color_lut", receipt_flow, "receipt-case")
            receipt = dict(schema="hmb-generated-video-source", version=1, completed=True,
                channel_uuid="receipt-case", shot_uuid="guard-shot", source_node_instance_id="native-instance-a",
                task_id="job-synthetic-kept", generation_id="job-synthetic-kept", result_revision=4,
                path="offline-original-preserved.mov")
            receipt_source._hmb_generated_video_source = receipt
            receipt_target._hmb_color_lut_state = {"source": deepcopy(receipt)}
            # The snapshot getter can resolve a file and publish parameters.
            # The deletion preflight must read the cached receipt instead.
            with mock.patch.object(receipt_source, "_hmb_generated_video_source_snapshot", harness.deny):
                assert_remote_peers(receipt_target, [receipt_source], "accepted_completed_origin_protects_Only_generator_to_LUT_without_resolving")
                receipt_target._hmb_color_lut_state["source"]["source_node_instance_id"] = "foreign same-name instance"
                assert_remote_peers(receipt_target, [], "mismatched_completed_source_instance_is_not_a_binding")
                receipt_target._hmb_color_lut_state = {"source": {}}
                assert_remote_peers(receipt_target, [], "offered_completed_receipt_without_accepted_LUT_origin_is_not_a_binding")

            future, declared = create("future dependency owner"), create("future dependency peer")
            future.deps = [declared]
            await blocked(DeleteNodeRequest(node_name=future.name), "future_exact_dependency_owner_blocks")
            await blocked(DeleteNodeRequest(node_name=declared.name), "future_exact_dependency_peer_blocks")
            stale = FutureHMBTool(declared.name)
            other_flow = harness.send(engine, CreateFlowRequest(parent_flow_name=flow, flow_name="Foreign", set_as_new_context=False)).flow_name
            foreign = create("foreign exact object", other_flow)
            future.deps = [stale, foreign]
            assert not guard.connected_targets(engine, [future.name, declared.name])
            harness.record("stale_same_name_and_exact_foreign_flow_dependencies_ignored")
            future.deps = "invalid contract"
            before = snapshot(engine)
            failed = await engine.ahandle_request(DeleteNodeRequest(node_name=future.name, broadcast_result=False))
            assert not failed.succeeded() and "HMB_DELETE_CHECK_FAILED" in str(failed.result_details)
            assert snapshot(engine) == before
            future.deps = []
            harness.record("unreadable_future_dependency_contract_fails_closed_without_mutation")

            # Native parent_group is an exact BaseNodeGroup object, including
            # nesting; the public read-only batch query expands its descendants.
            outer = BaseNodeGroup("outer group", metadata={"library": "Native_Group"})
            inner = BaseNodeGroup("inner group", metadata={"library": "Native_Group"})
            native_flow = engine.flow_manager.get_flow_by_name(flow)
            for group in (outer, inner):
                native_flow.add_node(group); engine.object_manager.add_object_by_name(group.name, group)
                engine.node_manager._name_to_parent_flow_name[group.name] = flow
            inner.add_nodes_to_group([target]); outer.add_nodes_to_group([inner])
            assert target.parent_group is inner and inner.parent_group is outer
            before = snapshot(engine)
            check = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[outer.name, source.name, source.name]))
            assert not check.can_delete and source.name in check.blocked and target.name in check.blocked
            assert outer.metadata["library"] != schema.name and outer.name in check.hmb_node_names
            assert snapshot(engine) == before
            harness.record("native_nested_parent_group_batch_preflight_no_partial_mutation")
            await blocked(DeleteNodeRequest(node_name=outer.name), "direct_native_nested_group_delete_blocks_before_any_mutation")
            await blocked(ResetNodeToDefaultsRequest(node_name=outer.name), "direct_native_nested_group_reset_blocks_before_any_mutation")

            # Put an unconnected node before connected descendants so a late
            # nested veto would be observable as a partial deletion.
            clean = create("unconnected first")
            nested = harness.send(engine, CreateFlowRequest(parent_flow_name=flow, flow_name="Nested", set_as_new_context=False)).flow_name
            nested_clean = create("nested unconnected first", nested)
            nested_a, nested_b = create("nested A", nested), create("nested B", nested)
            wire(nested_a, nested_b)
            await blocked(DeleteFlowRequest(flow_name=flow), "top_parent_flow_preflight_blocks_before_child_or_node_deletion")
            await blocked(DeleteFlowRequest(), "implicit_current_flow_delete_does_not_pop_flow")
            await blocked(DeleteFlowRequest(flow_name=nested), "nested_flow_preflight_blocks_before_unconnected_first_node")
            await blocked(ClearAllObjectStateRequest(i_know_what_im_doing=True), "force_ClearAll_blocked_before_context_or_objects_change")
            current_workflow = engine.context_manager.get_current_workflow_name()
            await blocked(DeleteWorkflowRequest(name=current_workflow), "active_DeleteWorkflow_blocked_before_registry_or_context_change")
            await harness.asend(engine, DeleteNodeRequest(node_name=clean.name))
            unconnected = create("unconnected reset")
            original_id = id(unconnected)
            await harness.asend(engine, ResetNodeToDefaultsRequest(node_name=unconnected.name))
            assert id(engine.node_manager.get_node_by_name(unconnected.name)) != original_id
            harness.record("unconnected_delete_and_native_reset_remain_available")

            # Normal New/Close releases loaded view without deleting a saved
            # file. Its permission must not leak to a subsequent direct clear.
            await harness.asend(engine, guard.HMBPrepareWorkflowTransitionRequest())
            assert not engine.node_manager._name_to_parent_flow_name
            flow = harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="SavedDeletionGuardSDK")).flow_name
            source, target = create("saved guard source"), create("saved guard target")
            wire(source, target)
            commands = harness.send(engine, SerializeFlowToCommandsRequest(flow_name=flow)).serialized_flow_commands
            saved = out / "private-connected-guard-workflow.py"
            saved_result = await harness.asend(engine, SaveWorkflowFileFromSerializedFlowRequest(
                serialized_flow_commands=commands, file_name=saved.stem, file_path=str(saved), display_name="Private deletion fixture"))
            digest = saved.read_bytes()
            loaded = await harness.asend(engine, RunWorkflowFromScratchRequest(file_path=str(saved)))
            assert engine.node_manager.get_node_by_name(source.name) is not source
            assert saved.read_bytes() == digest
            await blocked(ClearAllObjectStateRequest(i_know_what_im_doing=True), "direct_force_clear_after_scratch_load_is_not_authorized")
            harness.record("native_save_and_Scratch_load_replace_connected_view_without_deleting_source")
            # Registry load is a second native entry, not an imitation loader.
            from griptape_nodes.node_library.workflow_registry import read_workflow_metadata
            registered = harness.send(engine, RegisterWorkflowRequest(metadata=read_workflow_metadata(saved), file_name=str(saved)))
            registry_name = registered.workflow_name
            await harness.asend(engine, RunWorkflowFromRegistryRequest(workflow_name=registry_name, run_with_clean_slate=True))
            await blocked(ClearAllObjectStateRequest(i_know_what_im_doing=True), "direct_force_clear_after_registry_load_is_not_authorized")
            assert saved.read_bytes() == digest
            harness.record("native_registry_clean_slate_load_remains_available")
            await harness.asend(engine, guard.HMBPrepareWorkflowTransitionRequest())
            stable_handler = registration.deletion_handlers
            owner.before_library_unregistered(schema, library)
            assert not registration.active
            inactive = engine.handle_request(guard.HMBCheckNodeDeletionRequest(node_names=[], broadcast_result=False))
            assert not inactive.succeeded(), "Detached typed handler must fail closed"
            before = snapshot(engine)
            inactive_transition = await engine.ahandle_request(guard.HMBPrepareWorkflowTransitionRequest(broadcast_result=False))
            assert not inactive_transition.succeeded() and snapshot(engine) == before
            with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
                owner.before_library_nodes_loaded(schema, library)
            assert len(owner._registrations) == 1
            registration = next(iter(owner._registrations))
            assert registration.deletion_handlers is not None, "Refresh failed to rebind typed request handlers"
            assert registration.deletion_handlers is stable_handler
            assert stable_handler.owner_ref() is registration and stable_handler.engine_ref() is engine
            assert harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[])).can_delete
            flow = harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="After library refresh")).flow_name
            source, target = create("refreshed source"), create("refreshed target")
            wire(source, target)
            await blocked(DeleteNodeRequest(node_name=source.name), "real_library_refresh_preserves_central_guard")
            harness.record("actual_library_unload_reload_rebinds_typed_preflight_and_transition")
            assert not harness.ATTEMPTS
    finally:
        # The explicit view transition is the only intended connected teardown.
        if registration.active:
            await engine.ahandle_request(guard.HMBPrepareWorkflowTransitionRequest(broadcast_result=False))
        owner.before_library_unregistered(schema, library)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "reports/predeploy-usability-fixes-20261024/connected-deletion-sdk")
    out = parser.parse_args().out.resolve(); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hmb-connected-deletion-") as temp:
        env = {key: str(Path(temp) / key) for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR", "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        for value in env.values(): Path(value).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", harness.deny):
            from griptape_nodes.retained_mode.engine import engine_scope
            logging.disable(logging.CRITICAL)
            passed = False
            try:
                with engine_scope() as engine:
                    with asyncio.Runner() as runner:
                        runner.run(exercise(engine, "connected-deletion", out))
                passed = True
            finally:
                result = dict(passed=passed and not harness.ATTEMPTS, cases=harness.RESULTS,
                    provider_or_paid_calls=0, forbidden_execution_attempts=len(harness.ATTEMPTS),
                    source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                        for name in ("_hmb_deletion_guard.py", "_hmb_library_bootstrap.py")},
                    scope="Installed native SDK; retained synthetic nodes and all current HMB metadata types; no live desktop, provider or render")
                (out / "connected-deletion-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                logging.shutdown()
    print(json.dumps(dict(passed=True, cases=len(harness.RESULTS), paid_calls=0)))


if __name__ == "__main__": main()
