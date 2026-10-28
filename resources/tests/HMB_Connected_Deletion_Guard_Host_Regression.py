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
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, DeleteNodeRequest, ResetNodeToDefaultsRequest, GetNodeMetadataRequest, MoveNodeToNewFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, DeleteFlowRequest, SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest, RenameObjectRequest
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
    preexisting = {"enabled": False, "node_name": None, "results": []}
    def preexisting_owner_hook(request, context):
        if preexisting["enabled"] and isinstance(request, GetNodeMetadataRequest):
            preexisting["results"].append(engine.handle_request(DeleteNodeRequest(node_name=preexisting["node_name"])))
        return None
    manager.add_pre_dispatch_hook(preexisting_owner_hook)
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
        details = str(result.result_details)
        assert (guard.CODE in details or (not guard.protection_readiness(engine)[0]
                and any(code in details for code in ("HMB_DELETE_CHECK_FAILED", "HMB_DELETE_GUARD_NOT_READY")))), (label, details)
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
            barrier = getattr(manager, guard.REENTRANT_BARRIER_ATTRIBUTE)
            assert barrier.is_installed() and barrier.engine_ref() is engine
            assert guard.install_reentrant_barrier(engine) is barrier
            # This independent owner registered before HMB. Its hook runs
            # before the lifetime gate but cannot re-enter a destructive route.
            assert manager._pre_dispatch_hooks.index(preexisting_owner_hook) < manager._pre_dispatch_hooks.index(registration.deletion_protection.hook)
            preexisting.update(enabled=True, node_name=source.name)
            before_preexisting = snapshot(engine)
            try:
                assert engine.handle_request(GetNodeMetadataRequest(node_name=target.name)).succeeded()
            finally:
                preexisting['enabled'] = False
            assert len(preexisting['results']) == 1 and not preexisting['results'][0].succeeded()
            assert guard.CODE in str(preexisting['results'][0].result_details)
            assert snapshot(engine) == before_preexisting
            assert preexisting_owner_hook in manager._pre_dispatch_hooks
            harness.record("preexisting_other_hook_reentrant_delete_is_blocked_and_owner_preserved")

            # A different SDK hook can dispatch recursively. SDK 0.102.0
            # normally skips its *whole* hook list in this case, so verify the
            # real request path, including failure-before-mutation semantics.
            def forced_reset():
                request = ResetNodeToDefaultsRequest(node_name=source.name)
                request.force = True
                return request
            for label, make_request in (
                ("node", lambda: DeleteNodeRequest(node_name=source.name)),
                ("forced_reset", forced_reset),
                ("flow", lambda: DeleteFlowRequest(flow_name=flow)),
                ("forced_clear", lambda: ClearAllObjectStateRequest(i_know_what_im_doing=True)),
            ):
                for async_outer in (False, True):
                    seen = []
                    def other_owner_hook(request, context):
                        if isinstance(request, GetNodeMetadataRequest):
                            seen.append(engine.handle_request(make_request()))
                        return None
                    manager.add_pre_dispatch_hook(other_owner_hook)
                    before_reentrant = snapshot(engine)
                    try:
                        outer_request = GetNodeMetadataRequest(node_name=target.name, broadcast_result=False)
                        outer = await engine.ahandle_request(outer_request) if async_outer else engine.handle_request(outer_request)
                    finally:
                        manager.remove_pre_dispatch_hook(other_owner_hook)
                    assert outer.succeeded() and len(seen) == 1 and not seen[0].succeeded(), (label, seen)
                    assert guard.CODE in str(seen[0].result_details), (label, seen[0].result_details)
                    assert snapshot(engine) == before_reentrant, "nested " + label + " mutated graph"
                    harness.record("other_hook_reentrant_" + label + ("_async" if async_outer else "_sync"))

            # A disconnected HMB node is still removable from a nested request.
            unlinked = create("nested unconnected deletion")
            nested = []
            def ordinary_hook(request, context):
                if isinstance(request, GetNodeMetadataRequest):
                    nested.append(engine.handle_request(DeleteNodeRequest(node_name=unlinked.name)))
                return None
            manager.add_pre_dispatch_hook(ordinary_hook)
            try:
                assert engine.handle_request(GetNodeMetadataRequest(node_name=target.name)).succeeded()
            finally:
                manager.remove_pre_dispatch_hook(ordinary_hook)
            assert len(nested) == 1 and nested[0].succeeded()
            assert unlinked.name not in engine.node_manager._name_to_parent_flow_name
            harness.record("other_hook_reentrant_unconnected_deletion_remains_native")

            # A UI preflight describes object identities, not reusable names.
            checked = create("checked unconnected")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[checked.name]))
            assert receipt.can_delete and receipt.check_token
            removed = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=checked.name, check_token=receipt.check_token, broadcast_result=False))
            assert removed.succeeded() and checked.name not in engine.node_manager._name_to_parent_flow_name
            before_repeat = snapshot(engine)
            repeated = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=checked.name, check_token=receipt.check_token, broadcast_result=False))
            assert not repeated.succeeded() and snapshot(engine) == before_repeat
            harness.record("checked_deletion_is_one_use_per_selected_object")

            old = create("checked same name")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[old.name]))
            harness.send(engine, DeleteNodeRequest(node_name=old.name))
            replacement = create(old.name)
            before_replacement = snapshot(engine)
            refused = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=replacement.name, check_token=receipt.check_token, broadcast_result=False))
            assert not refused.succeeded() and snapshot(engine) == before_replacement
            harness.send(engine, DeleteNodeRequest(node_name=replacement.name))
            harness.record("checked_deletion_refuses_same_name_replacement_before_mutation")

            checked_source, checked_target = create("checked source"), create("checked target")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[checked_source.name]))
            wire(checked_source, checked_target)
            before_late = snapshot(engine)
            refused = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=checked_source.name, check_token=receipt.check_token, broadcast_result=False))
            assert not refused.succeeded() and snapshot(engine) == before_late
            harness.record("checked_identity_receipt_never_bypasses_new_connection_guard")

            expired = create("checked expired")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[expired.name]))
            before_expired = snapshot(engine)
            with mock.patch.object(guard.time, "monotonic", return_value=guard.time.monotonic() + 61):
                refused = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                    node_name=expired.name, check_token=receipt.check_token, broadcast_result=False))
            assert not refused.succeeded() and snapshot(engine) == before_expired
            harness.send(engine, DeleteNodeRequest(node_name=expired.name))
            harness.record("expired_selection_receipt_refuses_without_side_effects")

            checked_group = BaseNodeGroup("checked group", metadata={"library": "Native_Group"})
            checked_flow = engine.flow_manager.get_flow_by_name(flow)
            checked_flow.add_node(checked_group)
            engine.object_manager.add_object_by_name(checked_group.name, checked_group)
            engine.node_manager._name_to_parent_flow_name[checked_group.name] = flow
            child = create("checked child")
            checked_group.add_nodes_to_group([child])
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[checked_group.name]))
            added = create("checked late child")
            checked_group.add_nodes_to_group([added])
            before_group_change = snapshot(engine)
            refused = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=checked_group.name, check_token=receipt.check_token, broadcast_result=False))
            assert not refused.succeeded() and snapshot(engine) == before_group_change
            harness.record("checked_group_refuses_changed_descendant_set")
            inner_groups = [BaseNodeGroup(name, metadata={"library": "Native_Group"})
                            for name in ("checked inner one", "checked inner two")]
            for group in inner_groups:
                checked_flow.add_node(group)
                engine.object_manager.add_object_by_name(group.name, group)
                engine.node_manager._name_to_parent_flow_name[group.name] = flow
            checked_group.add_nodes_to_group(inner_groups)
            checked_group.delete_nodes_from_group([added])
            inner_groups[0].add_nodes_to_group([added])
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[checked_group.name]))
            inner_groups[0].delete_nodes_from_group([added])
            inner_groups[1].add_nodes_to_group([added])
            before_reparent = snapshot(engine)
            refused = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=checked_group.name, check_token=receipt.check_token, broadcast_result=False))
            assert not refused.succeeded() and snapshot(engine) == before_reparent
            harness.record("checked_group_refuses_reparenting_with_identical_descendant_names")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(
                node_names=[checked_group.name, child.name, added.name, *(group.name for group in inner_groups)]))
            for selected in (child, added, *inner_groups, checked_group):
                removed = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                    node_name=selected.name, check_token=receipt.check_token, broadcast_result=False))
                assert removed.succeeded()
            harness.record("checked_children_then_group_accepts_only_original_selected_objects")

            # Native Subflow teardown relocates children before deleting its
            # empty subflow. Only the owning delete context may make that move.
            from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup
            from griptape_nodes.retained_mode.events.node_events import MoveNodeToNewFlowRequest
            class ProbeSubflow(SubflowNodeGroup):
                async def aprocess(self):
                    raise AssertionError("node execution is forbidden in this test")
            def make_subflow(suffix):
                group = ProbeSubflow("private subflow " + suffix, metadata={"library": "Native_Group"})
                checked_flow.add_node(group)
                engine.object_manager.add_object_by_name(group.name, group)
                engine.node_manager._name_to_parent_flow_name[group.name] = flow
                member = create("private member " + suffix)
                group.add_nodes_to_group([member])
                return group, member

            from griptape_nodes.retained_mode.events.node_events import (
                AddNodesToNodeGroupRequest, RemoveNodeFromNodeGroupRequest)
            for use_receipt in (False, True):
                suffix = "checked" if use_receipt else "direct"
                group = BaseNodeGroup("private plain " + suffix, metadata={"library": "Native_Group"})
                checked_flow.add_node(group)
                engine.object_manager.add_object_by_name(group.name, group)
                engine.node_manager._name_to_parent_flow_name[group.name] = flow
                member = create("private plain member " + suffix)
                outsider = create("private plain connected " + suffix)
                peer = create("private plain peer " + suffix, hmb=False)
                wire(outsider, peer)
                group.add_nodes_to_group([member])
                saved_values = (deepcopy(dict(member.parameter_values)), deepcopy(dict(member.parameter_output_values)))
                receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
                entered, finish = asyncio.Event(), asyncio.Event()
                original_cancel = engine.node_manager.cancel_conditionally
                async def plain_pending_cancel(*args, **kwargs):
                    if args[2] is group:
                        entered.set()
                        await finish.wait()
                    return await original_cancel(*args, **kwargs)
                request = (guard.HMBDeleteCheckedNodeRequest(node_name=group.name, check_token=receipt.check_token, broadcast_result=False)
                           if use_receipt else DeleteNodeRequest(node_name=group.name, broadcast_result=False))
                with mock.patch.object(engine.node_manager, "cancel_conditionally", plain_pending_cancel):
                    pending_delete = asyncio.create_task(engine.ahandle_request(request))
                    await asyncio.wait_for(entered.wait(), timeout=5)
                    added = await engine.ahandle_request(AddNodesToNodeGroupRequest(
                        node_names=[outsider.name], node_group_name=group.name, flow_name=flow, broadcast_result=False))
                    removed = await engine.ahandle_request(RemoveNodeFromNodeGroupRequest(
                        node_names=[member.name], node_group_name=group.name, flow_name=flow, broadcast_result=False))
                    assert not added.succeeded() and not removed.succeeded()
                    assert outsider.parent_group is None and member.parent_group is group
                    finish.set()
                    assert (await asyncio.wait_for(pending_delete, timeout=5)).succeeded()
                assert group.name not in engine.node_manager._name_to_parent_flow_name
                assert engine.node_manager.get_node_by_name(member.name) is member and member.parent_group is None
                assert (dict(member.parameter_values), dict(member.parameter_output_values)) == saved_values
                assert outsider.parent_group is None and guard.connected_targets(engine, [outsider.name])[outsider.name] == [peer.name]
                harness.record("plain_group_" + suffix + "_blocks_concurrent_membership_and_releases_live_child")

            unrelated_group = BaseNodeGroup("private unrelated plain group", metadata={"library": "Native_Group"})
            checked_flow.add_node(unrelated_group)
            engine.object_manager.add_object_by_name(unrelated_group.name, unrelated_group)
            engine.node_manager._name_to_parent_flow_name[unrelated_group.name] = flow
            standard_member = create("private unrelated standard member", hmb=False)
            unrelated_group.add_nodes_to_group([standard_member])
            deleted = await engine.ahandle_request(DeleteNodeRequest(node_name=unrelated_group.name, broadcast_result=False))
            assert deleted.succeeded()
            # Preserve the SDK's own behavior for a standard-only group.
            assert standard_member.parent_group is unrelated_group
            harness.record("plain_group_standard_only_behavior_is_not_modified")

            group, member = make_subflow("normal membership")
            extra = create("private normal membership extra")
            added = await engine.ahandle_request(AddNodesToNodeGroupRequest(
                node_names=[extra.name], node_group_name=group.name, flow_name=flow, broadcast_result=False))
            assert added.succeeded() and extra.parent_group is group
            removed = await engine.ahandle_request(RemoveNodeFromNodeGroupRequest(
                node_names=[extra.name], node_group_name=group.name, flow_name=flow, broadcast_result=False))
            assert removed.succeeded() and extra.parent_group is None
            assert engine.node_manager.get_node_parent_flow_by_name(extra.name) == flow
            assert (await engine.ahandle_request(DeleteNodeRequest(node_name=group.name, broadcast_result=False))).succeeded()
            harness.record("subflow_group_membership_still_works_outside_delete")

            for use_receipt in (False, True):
                group, member = make_subflow("checked" if use_receipt else "direct")
                peer = create("private connected peer " + str(use_receipt), hmb=False)
                group.add_nodes_to_group([peer])
                connection = wire(member, peer)
                before = snapshot(engine)
                if use_receipt:
                    denied = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
                    assert not denied.can_delete and member.name in denied.blocked
                else:
                    denied = await engine.ahandle_request(DeleteNodeRequest(node_name=group.name, broadcast_result=False))
                    assert not denied.succeeded()
                assert snapshot(engine) == before
                harness.send(engine, DeleteConnectionRequest(**connection))
                retained_values = (deepcopy(dict(member.parameter_values)), deepcopy(dict(member.parameter_output_values)))
                if use_receipt:
                    receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
                    deleted = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                        node_name=group.name, check_token=receipt.check_token, broadcast_result=False))
                else:
                    deleted = await engine.ahandle_request(DeleteNodeRequest(node_name=group.name, broadcast_result=False))
                assert deleted.succeeded(), (type(deleted).__name__, str(deleted.result_details))
                assert group.name not in engine.node_manager._name_to_parent_flow_name
                assert engine.node_manager.get_node_by_name(member.name) is member
                assert member.parent_group is None and engine.node_manager.get_node_parent_flow_by_name(member.name) == flow
                assert (dict(member.parameter_values), dict(member.parameter_output_values)) == retained_values
                harness.record("subflow_" + ("checked" if use_receipt else "direct") + "_preserves_child_and_blocks_connections")

            group, member = make_subflow("concurrent move")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
            entered, finish = asyncio.Event(), asyncio.Event()
            original_cancel = engine.node_manager.cancel_conditionally
            async def group_pending_cancel(*args, **kwargs):
                entered.set()
                await finish.wait()
                return await original_cancel(*args, **kwargs)
            with mock.patch.object(engine.node_manager, "cancel_conditionally", group_pending_cancel):
                pending_group = asyncio.create_task(engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                    node_name=group.name, check_token=receipt.check_token, broadcast_result=False)))
                await asyncio.wait_for(entered.wait(), timeout=5)
                move = await engine.ahandle_request(MoveNodeToNewFlowRequest(
                    node_name=member.name, target_flow_name=flow, broadcast_result=False))
                assert not move.succeeded() and member.parent_group is group
                finish.set()
                assert (await asyncio.wait_for(pending_group, timeout=5)).succeeded()
            assert member.parent_group is None and engine.node_manager.get_node_parent_flow_by_name(member.name) == flow
            harness.record("subflow_delete_blocks_unrelated_concurrent_move_but_allows_owned_teardown")

            group, member = make_subflow("other delete lease")
            unrelated = create("parent flow pending unrelated delete")
            entered, finish = asyncio.Event(), asyncio.Event()
            original_cancel = engine.node_manager.cancel_conditionally
            async def unrelated_pending_cancel(*args, **kwargs):
                if args[2] is unrelated:
                    entered.set()
                    await finish.wait()
                return await original_cancel(*args, **kwargs)
            with mock.patch.object(engine.node_manager, "cancel_conditionally", unrelated_pending_cancel):
                other_delete = asyncio.create_task(engine.ahandle_request(DeleteNodeRequest(
                    node_name=unrelated.name, broadcast_result=False)))
                await asyncio.wait_for(entered.wait(), timeout=5)
                receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
                refused = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                    node_name=group.name, check_token=receipt.check_token, broadcast_result=False))
                assert not refused.succeeded() and member.parent_group is group
                assert engine.node_manager.get_node_parent_flow_by_name(member.name) == group.metadata["subflow_name"]
                finish.set()
                assert (await asyncio.wait_for(other_delete, timeout=5)).succeeded()
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
            assert (await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=group.name, check_token=receipt.check_token, broadcast_result=False))).succeeded()
            assert member.parent_group is None
            harness.record("subflow_owned_move_never_borrows_another_delete_reservation")

            # A retained node can exist in the actual subflow without being
            # recorded as a member. Native teardown would move group members
            # before discovering a protected node in a nested flow.
            group, member = make_subflow("ungrouped nested")
            nested_flow = harness.send(engine, CreateFlowRequest(
                flow_name="private nested orphan flow", parent_flow_name=group.metadata["subflow_name"],
                set_as_new_context=False)).flow_name
            orphan = create("private nested ungrouped HMB", flow=nested_flow)
            orphan_peer = create("private nested ungrouped peer", flow=nested_flow, hmb=False)
            connection = wire(orphan, orphan_peer)
            before = snapshot(engine)
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
            assert not receipt.can_delete and orphan.name in receipt.blocked
            direct = await engine.ahandle_request(DeleteNodeRequest(node_name=group.name, broadcast_result=False))
            assert not direct.succeeded() and snapshot(engine) == before
            assert member.parent_group is group
            harness.record("subflow_nested_ungrouped_connected_refuses_before_any_move")
            harness.send(engine, DeleteConnectionRequest(**connection))
            before = snapshot(engine)
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
            assert not receipt.can_delete and "HMB_SUBFLOW_UNGROUPED" in receipt.message
            direct = await engine.ahandle_request(DeleteNodeRequest(node_name=group.name, broadcast_result=False))
            assert not direct.succeeded() and "HMB_SUBFLOW_UNGROUPED" in str(direct.result_details)
            assert snapshot(engine) == before and member.parent_group is group
            harness.record("subflow_nested_ungrouped_unconnected_refuses_without_side_effect")
            for node in (orphan, orphan_peer):
                moved = await engine.ahandle_request(MoveNodeToNewFlowRequest(
                    node_name=node.name, target_flow_name=flow, broadcast_result=False))
                assert moved.succeeded()
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[group.name]))
            assert receipt.can_delete
            deleted = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                node_name=group.name, check_token=receipt.check_token, broadcast_result=False))
            assert deleted.succeeded() and member.parent_group is None
            assert engine.node_manager.get_node_by_name(orphan.name) is orphan
            harness.record("subflow_delete_recovers_after_ungrouped_nodes_moved_to_safety")

            # Failure while resolving the SDK's group type must not strand the
            # deletion reservation or prevent a subsequent ordinary delete.
            import builtins
            group, member = make_subflow("missing sdk group")
            original_import = builtins.__import__
            def reject_group_import(name, *args, **kwargs):
                if name == "griptape_nodes.exe_types.node_groups.subflow_node_group":
                    raise ImportError("synthetic missing SDK group API")
                return original_import(name, *args, **kwargs)
            before = snapshot(engine)
            with mock.patch.object(builtins, "__import__", side_effect=reject_group_import):
                result = await engine.ahandle_request(DeleteNodeRequest(node_name=group.name, broadcast_result=False))
            assert not result.succeeded() and snapshot(engine) == before
            handler_barrier = getattr(manager, guard.HANDLER_BARRIER_ATTRIBUTE)
            assert not handler_barrier.deleting and not handler_barrier.deleting_flows
            assert (await engine.ahandle_request(DeleteNodeRequest(node_name=group.name, broadcast_result=False))).succeeded()
            assert member.parent_group is None
            harness.record("subflow_sdk_import_failure_releases_delete_reservation")

            pending = create("checked pending")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[pending.name]))
            entered, finish = asyncio.Event(), asyncio.Event()
            original_cancel = engine.node_manager.cancel_conditionally
            async def pending_cancel(*args, **kwargs):
                entered.set()
                await finish.wait()
                return await original_cancel(*args, **kwargs)
            with mock.patch.object(engine.node_manager, "cancel_conditionally", pending_cancel):
                first_delete = asyncio.create_task(engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                    node_name=pending.name, check_token=receipt.check_token, broadcast_result=False)))
                await asyncio.wait_for(entered.wait(), timeout=5)
                for _ in range(2):
                    duplicate = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                        node_name=pending.name, check_token=receipt.check_token, broadcast_result=False))
                    assert not duplicate.succeeded() and pending.deleted_calls == 0
                finish.set()
                assert (await asyncio.wait_for(first_delete, timeout=5)).succeeded()
            assert pending.deleted_calls == 1
            harness.record("rejected_duplicate_cannot_release_another_checked_request_lease")

            failed_native = create("checked native failure")
            receipt = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[failed_native.name]))
            with mock.patch.object(failed_native, "after_node_deleted", side_effect=ValueError("isolated failure")) as callback:
                refused = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                    node_name=failed_native.name, check_token=receipt.check_token, broadcast_result=False))
                assert not refused.succeeded() and callback.call_count == 1
                refused_again = await engine.ahandle_request(guard.HMBDeleteCheckedNodeRequest(
                    node_name=failed_native.name, check_token=receipt.check_token, broadcast_result=False))
                assert not refused_again.succeeded() and callback.call_count == 1
            harness.send(engine, DeleteNodeRequest(node_name=failed_native.name))
            harness.record("checked_receipt_is_not_retried_after_native_failure")

            # A later hook can add a connection after the original preflight.
            # The final handler check must see it before deletion begins.
            late_source, late_target = create("late source"), create("late target")
            late_results = []
            def late_connection(request, context):
                if isinstance(request, DeleteNodeRequest) and request.node_name == late_source.name:
                    late_results.append(engine.handle_request(CreateConnectionRequest(
                        source_node_name=late_source.name, source_parameter_name="output",
                        target_node_name=late_target.name, target_parameter_name="input",
                        initial_setup=True, broadcast_result=False)))
                return None
            manager.add_pre_dispatch_hook(late_connection)
            try:
                late_delete = await engine.ahandle_request(DeleteNodeRequest(
                    node_name=late_source.name, broadcast_result=False))
            finally:
                manager.remove_pre_dispatch_hook(late_connection)
            assert len(late_results) == 1 and late_results[0].succeeded()
            assert not late_delete.succeeded() and guard.CODE in str(late_delete.result_details)
            assert late_source.name in engine.node_manager._name_to_parent_flow_name
            assert guard.connected_targets(engine, [late_source.name])[late_source.name] == [late_target.name]
            harness.record("connection_added_after_preflight_denied_at_handler")

            # A foreign replacement of pre-dispatch cannot bypass the final
            # handler; ownership loss fails closed and the graph stays intact.
            before_foreign_bypass = snapshot(engine)
            original_dispatch = manager._run_pre_dispatch_hooks
            manager._run_pre_dispatch_hooks = lambda request, context: None
            try:
                assert not guard.protection_readiness(engine)[0]
                foreign_bypass = await engine.ahandle_request(DeleteNodeRequest(
                    node_name=source.name, broadcast_result=False))
                assert not foreign_bypass.succeeded()
                assert "HMB_DELETE_GUARD_NOT_READY" in str(foreign_bypass.result_details)
            finally:
                manager._run_pre_dispatch_hooks = original_dispatch
            assert snapshot(engine) == before_foreign_bypass
            harness.record("nondelegating_hook_replacement_denied_at_handler")

            direct_source, direct_target = create("direct source"), create("direct target")
            wire(direct_source, direct_target)
            before_direct = snapshot(engine)
            direct = await engine.node_manager.on_delete_node_request(
                DeleteNodeRequest(node_name=direct_source.name, broadcast_result=False))
            assert not direct.succeeded() and guard.CODE in str(direct.result_details)
            assert snapshot(engine) == before_direct
            harness.record("direct_manager_delete_denied_at_handler")

            # A native delete can await cancellation after the handler check.
            # A connection to its reserved HMB node must fail while that await
            # is active; unrelated connections remain available.
            for direct_create in (False, True):
                await_source, await_target = create("await source"), create("await target")
                other_source, other_target = create("other source"), create("other target")
                original_cancel = engine.node_manager.cancel_conditionally
                observed = []
                async def cancel_with_connection(*args, **kwargs):
                    await asyncio.sleep(0)
                    request = CreateConnectionRequest(
                        source_node_name=await_source.name, source_parameter_name="output",
                        target_node_name=await_target.name, target_parameter_name="input",
                        initial_setup=True, broadcast_result=False)
                    observed.append(engine.flow_manager.on_create_connection_request(request)
                                    if direct_create else engine.handle_request(request))
                    observed.append(engine.handle_request(CreateConnectionRequest(
                        source_node_name=other_source.name, source_parameter_name="output",
                        target_node_name=other_target.name, target_parameter_name="input",
                        initial_setup=True, broadcast_result=False)))
                    return await original_cancel(*args, **kwargs)
                with mock.patch.object(engine.node_manager, "cancel_conditionally", cancel_with_connection):
                    outcome = await engine.ahandle_request(DeleteNodeRequest(
                        node_name=await_source.name, broadcast_result=False))
                assert len(observed) == 2 and not observed[0].succeeded() and observed[1].succeeded()
                assert "HMB_DELETE_IN_PROGRESS" in str(observed[0].result_details)
                assert outcome.succeeded() and await_source.name not in engine.node_manager._name_to_parent_flow_name
                assert guard.connected_targets(engine, [other_source.name])[other_source.name] == [other_target.name]
                harness.record("wire_connection_during_delete_await_denied_" + ("direct" if direct_create else "request"))

            # No reservation may leak if a native delete callback raises.
            failure_source, failure_target = create("failure source"), create("failure target")
            async def cancelled_with_error(*args, **kwargs):
                await asyncio.sleep(0)
                raise RuntimeError("synthetic deletion error")
            with mock.patch.object(engine.node_manager, "cancel_conditionally", cancelled_with_error):
                try:
                    await engine.node_manager.on_delete_node_request(DeleteNodeRequest(
                        node_name=failure_source.name, broadcast_result=False))
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("synthetic error did not propagate")
            assert failure_source.name not in getattr(manager, guard.HANDLER_BARRIER_ATTRIBUTE).deleting
            wire(failure_source, failure_target)
            assert guard.connected_targets(engine, [failure_source.name])[failure_source.name] == [failure_target.name]
            harness.record("wire_reservation_released_on_delete_error")

            # Cooperative remote writers use the same flow reservation as the
            # delete handler, with neither lock held across SDK async work.
            remote_source, remote_target = create("changing remote source"), create("changing remote target")
            original_cancel = engine.node_manager.cancel_conditionally
            remote_results = []
            async def cancel_with_cooperative_binding(*args, **kwargs):
                await asyncio.sleep(0)
                try:
                    with guard.binding_mutation(remote_target):
                        remote_source.subscription = subscription("image_asset", "race-channel")
                        remote_target.subscription = subscription("video_picker", "race-channel")
                except RuntimeError as exc:
                    remote_results.append(str(exc))
                return await original_cancel(*args, **kwargs)
            with mock.patch.object(engine.node_manager, "cancel_conditionally", cancel_with_cooperative_binding):
                result = await engine.ahandle_request(DeleteNodeRequest(
                    node_name=remote_source.name, broadcast_result=False))
            assert result.succeeded() and len(remote_results) == 1 and "HMB_DELETE_IN_PROGRESS" in remote_results[0]
            assert remote_target.subscription is None
            harness.record("cooperative_remote_mutation_during_delete_is_denied")

            writer_source = create("active remote writer")
            before_writer = snapshot(engine)
            with guard.binding_mutation(writer_source):
                outcome = await engine.ahandle_request(DeleteNodeRequest(
                    node_name=writer_source.name, broadcast_result=False))
            assert not outcome.succeeded() and "HMB_CONNECTION_IN_PROGRESS" in str(outcome.result_details)
            assert snapshot(engine) == before_writer
            harness.record("active_remote_mutation_denies_delete_before_mutation")

            destination = harness.send(engine, CreateFlowRequest(
                parent_flow_name=flow, flow_name="Reservation destination", set_as_new_context=False)).flow_name
            moving_node = create("binding moving node")
            with guard.binding_mutation(moving_node):
                move = engine.handle_request(MoveNodeToNewFlowRequest(
                    node_name=moving_node.name, target_flow_name=destination, broadcast_result=False))
                assert not move.succeeded() and "HMB_CONNECTION_IN_PROGRESS" in str(move.result_details)
            assert engine.node_manager.get_node_parent_flow_by_name(moving_node.name) == flow
            move = engine.handle_request(MoveNodeToNewFlowRequest(
                node_name=moving_node.name, target_flow_name=destination, broadcast_result=False))
            assert move.succeeded() and engine.node_manager.get_node_parent_flow_by_name(moving_node.name) == destination
            harness.record("flow_move_serialized_with_binding_mutation")

            moving_source, moving_peer = create("deleting while move"), create("move while deleting")
            original_cancel = engine.node_manager.cancel_conditionally
            move_results = []
            async def cancel_with_move(*args, **kwargs):
                await asyncio.sleep(0)
                move_results.append(engine.handle_request(MoveNodeToNewFlowRequest(
                    node_name=moving_peer.name, target_flow_name=destination, broadcast_result=False)))
                return await original_cancel(*args, **kwargs)
            with mock.patch.object(engine.node_manager, "cancel_conditionally", cancel_with_move):
                outcome = await engine.ahandle_request(DeleteNodeRequest(node_name=moving_source.name, broadcast_result=False))
            assert outcome.succeeded() and len(move_results) == 1 and not move_results[0].succeeded()
            assert "HMB_CONNECTION_IN_PROGRESS" in str(move_results[0].result_details)
            assert engine.node_manager.get_node_parent_flow_by_name(moving_peer.name) == flow
            harness.record("flow_move_denied_during_delete_await")

            rename_node = create("rename mutation node")
            with guard.binding_mutation(rename_node):
                rename = engine.handle_request(RenameObjectRequest(object_name=rename_node.name,
                    requested_name="renamed mutation node", broadcast_result=False))
                assert not rename.succeeded() and "HMB_CONNECTION_IN_PROGRESS" in str(rename.result_details), (type(rename).__name__, rename.result_details)
            assert rename_node.name == "rename mutation node"
            rename = engine.handle_request(RenameObjectRequest(object_name=rename_node.name,
                requested_name="renamed mutation node", broadcast_result=False))
            assert rename.succeeded() and rename_node.name == "renamed mutation node"
            harness.record("node_rename_serialized_with_binding_mutation")

            renaming_source, renaming_peer = create("deleting during rename"), create("rename during deletion")
            original_cancel = engine.node_manager.cancel_conditionally
            rename_results = []
            async def cancel_with_rename(*args, **kwargs):
                await asyncio.sleep(0)
                rename_results.append(engine.handle_request(RenameObjectRequest(object_name=renaming_peer.name,
                    requested_name="should not be renamed", broadcast_result=False)))
                return await original_cancel(*args, **kwargs)
            with mock.patch.object(engine.node_manager, "cancel_conditionally", cancel_with_rename):
                outcome = await engine.ahandle_request(DeleteNodeRequest(node_name=renaming_source.name, broadcast_result=False))
            assert outcome.succeeded() and len(rename_results) == 1 and not rename_results[0].succeeded()
            assert "HMB_CONNECTION_IN_PROGRESS" in str(rename_results[0].result_details)
            assert renaming_peer.name == "rename during deletion"
            harness.record("node_rename_denied_during_delete_await")

            # A foreign wrapper must not be replaced or reported as ready.
            current_wrapper = manager._run_pre_dispatch_hooks
            def foreign_wrapper(request, context):
                return current_wrapper(request, context)
            manager._run_pre_dispatch_hooks = foreign_wrapper
            try:
                assert not guard.protection_readiness(engine)[0]
                before_foreign = snapshot(engine)
                foreign_result = engine.handle_request(DeleteNodeRequest(node_name=source.name))
                assert not foreign_result.succeeded() and "HMB_DELETE_GUARD_NOT_READY" in str(foreign_result.result_details)
                assert snapshot(engine) == before_foreign
                try:
                    guard.install_reentrant_barrier(engine)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("foreign wrapper was silently accepted")
                assert manager._run_pre_dispatch_hooks is foreign_wrapper
            finally:
                manager._run_pre_dispatch_hooks = current_wrapper
            assert guard.protection_readiness(engine)[0]
            harness.record("foreign_hook_wrapper_is_not_replaced_and_readiness_fails_closed")
            readiness = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[source.name]))
            assert readiness.protection_ready is True and readiness.protection_version == 2
            assert readiness.readiness_error == "" and not readiness.can_delete
            lifetime_gate = getattr(manager, guard.LIFETIME_GATE_ATTRIBUTE)
            assert lifetime_gate.engine_ref() is engine and lifetime_gate.manager_ref() is manager
            harness.record("version2_readiness_requires_installed_engine_lifetime_gate")
            manager.remove_pre_dispatch_hook(lifetime_gate.hook)
            assert guard.protection_readiness(engine)[0] is False
            missing_hook = engine.handle_request(guard.HMBCheckNodeDeletionRequest(node_names=[source.name], broadcast_result=False))
            assert not missing_hook.succeeded() and not missing_hook.protection_ready
            await blocked(DeleteNodeRequest(node_name=source.name), "removed_lifetime_hook_fails_readiness_and_active_lease_still_protects")
            with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
                owner.before_library_nodes_loaded(schema, library)
            assert lifetime_gate.is_registered() and guard.protection_readiness(engine) == (True, "")
            assert sum(hook is lifetime_gate.hook for hook in manager._pre_dispatch_hooks) == 1
            harness.record("missing_lifetime_hook_is_repaired_only_through_official_idempotent_API")
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
            for candidate in (publisher, remote):
                nested_remote = []
                def nested_remote_hook(request, context):
                    if isinstance(request, GetNodeMetadataRequest):
                        nested_remote.append(engine.handle_request(DeleteNodeRequest(node_name=candidate.name)))
                    return None
                manager.add_pre_dispatch_hook(nested_remote_hook)
                before_remote = snapshot(engine)
                try:
                    assert engine.handle_request(GetNodeMetadataRequest(node_name=target.name)).succeeded()
                finally:
                    manager.remove_pre_dispatch_hook(nested_remote_hook)
                assert len(nested_remote) == 1 and not nested_remote[0].succeeded()
                assert guard.CODE in str(nested_remote[0].result_details)
                assert snapshot(engine) == before_remote
                harness.record("other_hook_reentrant_live_remote_blocks_" + candidate.name.replace(" ", "_"))

            # Turning the gate unready must also block nested *unconnected*
            # HMB deletion while retained HMB data remains in the engine.
            nested_unready_node = create("nested unready node")
            nested_unready = []
            def unready_hook(request, context):
                if isinstance(request, GetNodeMetadataRequest):
                    nested_unready.append(engine.handle_request(DeleteNodeRequest(node_name=nested_unready_node.name)))
                return None
            manager.add_pre_dispatch_hook(unready_hook)
            gate_ready_before = lifetime_gate.ready
            lifetime_gate.ready = False
            unready_snapshot = snapshot(engine)
            try:
                assert engine.handle_request(GetNodeMetadataRequest(node_name=target.name)).succeeded()
            finally:
                lifetime_gate.ready = gate_ready_before
                manager.remove_pre_dispatch_hook(unready_hook)
            assert len(nested_unready) == 1 and not nested_unready[0].succeeded()
            assert "HMB_DELETE_GUARD_NOT_READY" in str(nested_unready[0].result_details)
            assert snapshot(engine) == unready_snapshot
            harness.send(engine, DeleteNodeRequest(node_name=nested_unready_node.name))
            harness.record("unready_gate_blocks_reentrant_unconnected_until_ready")
            # Git Update can unregister the library while its retained graph
            # remains visible. This is not permission to remove wires/nodes.
            stable_handler = registration.deletion_handlers
            owner.before_library_unregistered(schema, library)
            assert not registration.active and not owner._registrations
            gap = harness.send(engine, guard.HMBCheckNodeDeletionRequest(node_names=[source.name, publisher.name]))
            assert gap.protection_ready is True and gap.protection_version == 2 and not gap.can_delete
            await blocked(DeleteNodeRequest(node_name=source.name), "unload_gap_wire_delete_before_mutation")
            forced = ResetNodeToDefaultsRequest(node_name=source.name); forced.force = True
            await blocked(forced, "unload_gap_forced_reset_before_mutation")
            await blocked(DeleteNodeRequest(node_name=publisher.name), "unload_gap_live_remote_delete_before_mutation")
            await blocked(ClearAllObjectStateRequest(i_know_what_im_doing=True), "unload_gap_forced_clear_before_mutation")
            with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
                owner.before_library_nodes_loaded(schema, library)
            registration = next(iter(owner._registrations))
            assert preexisting_owner_hook in manager._pre_dispatch_hooks
            assert registration.deletion_handlers is stable_handler
            assert registration.deletion_protection is lifetime_gate
            harness.record("retained_unload_gap_read_only_preflight_and_stable_reload")
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
            # Optional compatibility must never switch off an installed gate.
            with mock.patch.object(bootstrap, "_acquire_windows_transport_close_guard", side_effect=RuntimeError("optional fixture failure")):
                owner.before_library_nodes_loaded(schema, library)
            assert guard.protection_readiness(engine) == (True, "")
            await blocked(DeleteNodeRequest(node_name=source.name), "optional_bootstrap_failure_cannot_disable_deletion_gate")

            # A failed typed-handler initialization is visible and retains the
            # engine gate instead of reporting a silently successful load.
            owner.before_library_unregistered(schema, library)
            with mock.patch.object(guard, "install_request_handlers", side_effect=RuntimeError("critical fixture failure")):
                try:
                    owner.before_library_nodes_loaded(schema, library)
                except bootstrap._DeletionProtectionError as exc:
                    assert "HMB_DELETE_GUARD_NOT_READY" in str(exc)
                else:
                    raise AssertionError("Critical deletion initialization was silently ignored")
            registration = next(iter(owner._registrations))
            failed = engine.handle_request(guard.HMBCheckNodeDeletionRequest(node_names=[source.name], broadcast_result=False))
            assert not failed.succeeded() and not failed.protection_ready and failed.protection_version == 2
            assert "HMB_DELETE_GUARD_NOT_READY" in failed.readiness_error
            await blocked(DeleteNodeRequest(node_name=source.name), "critical_install_failure_retains_backend_wire_gate")
            with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
                owner.before_library_nodes_loaded(schema, library)
            assert guard.protection_readiness(engine) == (True, "")
            harness.record("critical_handler_failure_is_explicit_and_retry_restores_readiness")

            for api in ("add_pre_dispatch_hook", "remove_pre_dispatch_hook", "register_request_handlers"):
                with mock.patch.object(manager, api, None):
                    try:
                        owner.before_library_nodes_loaded(schema, library)
                    except bootstrap._DeletionProtectionError as exc:
                        assert "HMB_DELETE_GUARD_UNSUPPORTED" in str(exc)
                    else:
                        raise AssertionError("Missing required SDK API was silently accepted: " + api)
                    assert guard.protection_readiness(engine)[0] is False
                    await blocked(DeleteNodeRequest(node_name=source.name), "unsupported_API_keeps_existing_gate_" + api)
                with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
                    owner.before_library_nodes_loaded(schema, library)
            harness.record("all_required_SDK_APIs_fail_explicitly_without_losing_existing_protection")

            callback = lifetime_gate.callback
            check_type = guard.HMBCheckNodeDeletionRequest
            stable_handler = registration.deletion_handlers
            with mock.patch.object(guard, "PROTECTION_VERSION", 1), mock.patch.object(guard, "install_request_handlers", harness.deny), mock.patch.object(importlib, "reload", harness.deny):
                try:
                    owner.before_library_nodes_loaded(schema, library)
                except bootstrap._DeletionProtectionError as exc:
                    assert "HMB_DELETE_GUARD_RESTART_REQUIRED" in str(exc)
                else:
                    raise AssertionError("A cached legacy helper was silently promoted to ready")
                assert lifetime_gate.callback is None and lifetime_gate.ready is False
                assert guard.HMBCheckNodeDeletionRequest is check_type and registration.deletion_handlers is stable_handler
                await blocked(DeleteNodeRequest(node_name=source.name), "cached_legacy_helper_retains_exact_backend_callback")
            with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
                owner.before_library_nodes_loaded(schema, library)
            assert guard.protection_readiness(engine) == (True, "")
            # Evicting a module does not evict SDK payload classes. A new
            # helper generation must never overwrite a registered old class.
            from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
            registry_before = PayloadRegistry.get_registry()
            get_type = PayloadRegistry.get_type
            foreign_payload = type("OldDeletionPayloadFixture", (), {})
            owner.before_library_unregistered(schema, library)
            with mock.patch.object(PayloadRegistry, "get_type", side_effect=lambda name: (
                    foreign_payload if name == "HMBCheckNodeDeletionResultSuccess" else get_type(name))):
                try:
                    owner.before_library_nodes_loaded(schema, library)
                except bootstrap._DeletionProtectionError as exc:
                    assert "HMB_DELETE_GUARD_RESTART_REQUIRED" in str(exc)
                else:
                    raise AssertionError("A foreign SDK payload generation was overwritten")
            registration = next(iter(owner._registrations))
            assert PayloadRegistry.get_registry() == registry_before
            await blocked(DeleteNodeRequest(node_name=source.name), "foreign_payload_generation_keeps_backend_gate_without_overwrite")
            with mock.patch.object(bootstrap._Registration, "start_web_worker", lambda *a: None):
                owner.before_library_nodes_loaded(schema, library)
            assert guard.protection_readiness(engine) == (True, "")
            harness.record("registered_foreign_payload_identity_requires_restart_without_registry_mutation")
            with mock.patch.object(bootstrap, "current_engine", None):
                try:
                    owner.before_library_nodes_loaded(schema, library)
                except bootstrap._DeletionProtectionError as exc:
                    assert "HMB_DELETE_GUARD_UNSUPPORTED" in str(exc)
                else:
                    raise AssertionError("Missing main Engine context was silently accepted")
            harness.record("cached_legacy_protocol_never_reimports_or_reregisters_payloads_and_main_context_failure_is_explicit")
            # Healthy New/Close releases only the view, including during Git
            # unload. Its saved source and media references remain untouched.
            commands = harness.send(engine, SerializeFlowToCommandsRequest(flow_name=flow)).serialized_flow_commands
            saved_gap = out / "unload-close-preserved-workflow.py"
            await harness.asend(engine, SaveWorkflowFileFromSerializedFlowRequest(
                serialized_flow_commands=commands, file_name=saved_gap.stem, file_path=str(saved_gap), display_name="Unload close fixture"))
            saved_bytes = saved_gap.read_bytes()
            owner.before_library_unregistered(schema, library)
            assert not registration.active and guard.protection_readiness(engine) == (True, "")
            await harness.asend(engine, guard.HMBPrepareWorkflowTransitionRequest(broadcast_result=False))
            assert not engine.node_manager._name_to_parent_flow_name and saved_gap.read_bytes() == saved_bytes
            inactive_empty = engine.handle_request(guard.HMBCheckNodeDeletionRequest(node_names=[], broadcast_result=False))
            assert not inactive_empty.succeeded()
            harness.record("healthy_unload_gap_New_Close_releases_view_and_preserves_saved_source")

            harness.send(engine, EnsureWorkflowAndFlowRequest(flow_name="Standard only after unload"))
            for callback in (None, harness.deny):
                standard = create("ordinary independent", hmb=False)
                with mock.patch.object(lifetime_gate, "callback", callback):
                    deleted = await engine.ahandle_request(DeleteNodeRequest(node_name=standard.name, broadcast_result=False))
                assert deleted.succeeded() and standard.name not in engine.node_manager._name_to_parent_flow_name
            harness.record("positively_standard_only_graph_is_native_owned_even_when_guard_callback_is_unavailable")
            standard = create("ordinary unknown inventory", hmb=False)
            before_unknown = snapshot(engine)
            with mock.patch.object(engine.node_manager, "_name_to_parent_flow_name", None):
                unknown = await engine.ahandle_request(DeleteNodeRequest(node_name=standard.name, broadcast_result=False))
                assert not unknown.succeeded() and "HMB_DELETE_CHECK_FAILED" in str(unknown.result_details)
            assert snapshot(engine) == before_unknown
            harness.send(engine, DeleteNodeRequest(node_name=standard.name))
            harness.record("unknown_retained_inventory_fails_closed_before_native_mutation")
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
