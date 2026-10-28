"""Common pre-mutation deletion protection for current and future HMB tools.

Wire dependencies include hidden REMOTE edges. Non-wire tools may declare
``_hmb_deletion_dependencies() -> iterable[BaseNode]``; only exact retained
objects in the same flow are accepted. Merely offering a Shot in a dropdown
is not a binding. No provider, media resolution or filesystem work belongs here.
"""
from __future__ import annotations

import importlib
import inspect
import functools
import threading
import weakref
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

LIBRARY = "HMB_GP_Production"
CODE = "HMB_DELETE_CONNECTED"
PROTECTION_VERSION = 2
LIFETIME_GATE_ATTRIBUTE = "_hmb_connected_deletion_lifetime_v2"
REENTRANT_BARRIER_ATTRIBUTE = "_hmb_connected_deletion_reentrant_v2"
HANDLER_BARRIER_ATTRIBUTE = "_hmb_connected_deletion_handler_v2"
_DESTRUCTIVE = {
    "DeleteNodeRequest": ("node_events", "DeleteNodeResultFailure"),
    "ResetNodeToDefaultsRequest": ("node_events", "ResetNodeToDefaultsResultFailure"),
    "DeleteFlowRequest": ("flow_events", "DeleteFlowResultFailure"),
    "ClearAllObjectStateRequest": ("object_events", "ClearAllObjectStateResultFailure"),
    "DeleteWorkflowRequest": ("workflow_events", "DeleteWorkflowResultFailure"),
}
# An engine-owned workflow replacement releases the in-memory graph. It does
# not delete its saved source. A direct force-clear is still guarded.
_LOAD_PARENTS = {"RunWorkflowFromScratchRequest", "RunWorkflowFromRegistryRequest",
                 "HMBPrepareWorkflowTransitionRequest"}
_TEARDOWN_CHILDREN = {"ClearAllObjectStateRequest", "DeleteFlowRequest", "DeleteNodeRequest"}
_teardown_engine: ContextVar[int | None] = ContextVar("hmb_deletion_load_teardown", default=None)
_reset_identity: ContextVar[tuple[int, str] | None] = ContextVar("hmb_deletion_reset_identity", default=None)
_reset_handoff: ContextVar[Any] = ContextVar("hmb_deletion_reset_handoff", default=None)
_subflow_teardown: ContextVar[Any] = ContextVar("hmb_deletion_subflow_teardown", default=None)
_group_mutation: ContextVar[Any] = ContextVar("hmb_deletion_group_mutation", default=None)
_HANDLERS = globals().get("_HANDLERS", weakref.WeakKeyDictionary())
_checked_delete_identity: ContextVar[Any] = ContextVar("hmb_checked_delete_identity", default=None)
_BINDING_BARRIERS = globals().get("_BINDING_BARRIERS", weakref.WeakKeyDictionary())
_BINDING_BARRIERS_LOCK = globals().get("_BINDING_BARRIERS_LOCK", threading.RLock())


@contextmanager
def binding_mutation(node: Any, *, operation: str = "", parameter: str = ""):
    """Reserve a retained HMB flow briefly while a binding state is changed.

    Constructors and standalone unit tests have no retained owner and stay
    untouched. Cooperative HMB writers share the same reservation as deletion;
    arbitrary direct state mutations do not participate in this contract.
    """
    with _BINDING_BARRIERS_LOCK:
        barriers = tuple(_BINDING_BARRIERS.values())
    owned = None
    for barrier in barriers:
        engine = barrier.engine_ref()
        if engine is None:
            continue
        try:
            name = getattr(node, "name", None)
            inventory = engine.node_manager._name_to_parent_flow_name
            if not isinstance(inventory, dict):
                raise RuntimeError("retained inventory unavailable")
            if not name or name not in inventory:
                continue
            if engine.node_manager.get_node_by_name(name) is not node:
                continue  # A stale same-name object cannot mutate the live node.
            flow = _parent(engine, node)
            if not flow:
                raise RuntimeError("retained parent unavailable")
        except Exception as exc:
            # A registered-looking HMB object must not mutate when the same
            # engine's ownership inventory cannot be verified. Constructors
            # with a positively absent name remain a no-op above.
            if _is_hmb(node):
                raise RuntimeError("[HMB_DELETE_CHECK_FAILED] 노드의 작업 컨텍스트를 확인하지 못했습니다.") from exc
            continue
        if owned is not None:
            raise RuntimeError("[HMB_DELETE_CHECK_FAILED] 노드의 작업 컨텍스트가 중복되었습니다.")
        owned = (barrier, engine, name)
    if owned is None:
        yield
        return
    barrier, engine, name = owned
    with barrier.lock:
        inventory = engine.node_manager._name_to_parent_flow_name
        flow = inventory.get(name) if isinstance(inventory, dict) else None
        if not flow:
            raise RuntimeError("[HMB_DELETE_CHECK_FAILED] 노드의 작업 컨텍스트를 확인하지 못했습니다.")
        group_scope = _group_mutation.get()
        own_group_change = group_scope is not None and group_scope[0] == id(barrier) and flow in group_scope[1]
        active_subflow = any((active := reference()) is not None and
                             (getattr(active, "metadata", {}) or {}).get("subflow_name") == flow
                             for reference in barrier.active_groups.values())
        permit = _reset_handoff.get()
        allowed_parameters = ({"PROJECT_ROOT", "IMAGE_IMPORT_IN", "HMB_IMAGE_ASSET_STATE", "HMB_IMAGE_ASSET_THUMBNAIL_PATCH"}
                              if type(node).__name__ == "HMBImageAssetLibrary" else {"HMB_PICKER_STATE"})
        allowed_operation = (operation in {"_publish_state", "_cache_shot_routing_snapshot"}
                             and type(node).__name__ == "HMBImageAssetLibrary") or (
            operation in {"set_parameter_value", "after_value_set"} and parameter in allowed_parameters)
        authorized_reset_handoff = bool(allowed_operation and permit and permit.get("active") and permit.get("thread") == threading.get_ident()
            and permit.get("barrier") is barrier and permit.get("node") is node
            and permit.get("flow") == flow and engine.node_manager.get_node_by_name(name) is node)
        if (barrier.identity_changes or (barrier.deleting_flows.get(flow, 0) and not authorized_reset_handoff)
                or ((barrier.moving_flows.get(flow, 0) or active_subflow) and not own_group_change)):
            raise RuntimeError("[HMB_DELETE_IN_PROGRESS] 같은 작업의 노드 삭제가 진행 중입니다. 완료 후 다시 시도하세요.")
        barrier._increment(barrier.binding_changes, [flow])
    try:
        yield
    finally:
        with barrier.lock:
            barrier._decrement(barrier.binding_changes, [flow])


def hmb_binding_mutation(fn: Any) -> Any:
    """Mark a synchronous HMB binding-state entry point as cooperative."""
    if inspect.iscoroutinefunction(fn):
        raise TypeError("HMB binding mutation decorators only support synchronous methods")
    @functools.wraps(fn)
    def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
        first = args[0] if args else kwargs.get("param_name", kwargs.get("parameter"))
        parameter = first if isinstance(first, str) else getattr(first, "name", "")
        with binding_mutation(node, operation=fn.__name__, parameter=parameter):
            return fn(node, *args, **kwargs)
    return wrapped


def hmb_binding_management(fn: Any) -> Any:
    """Adapt the explicit connection-management function to the same scope."""
    @functools.wraps(fn)
    def wrapped(engine: Any, node_name: str, *args: Any, **kwargs: Any) -> Any:
        node = engine.node_manager.get_node_by_name(node_name)
        with binding_mutation(node):
            return fn(engine, node_name, *args, **kwargs)
    return wrapped


class _HandlerDeletionBarrier:
    """Final check at the SDK handler boundary, including direct calls.

    This guards normal dispatch even when a foreign pre-dispatch hook has
    replaced the hook chain. It also checks again after all pre-dispatch hooks.
    It is not by itself a graph mutation lock across awaits in the SDK.
    """

    def __init__(self, engine: Any, manager: Any) -> None:
        self.engine_ref = weakref.ref(engine)
        self.manager_ref = weakref.ref(manager)
        self.entries: list[tuple[Any, Any, str, Any, Any]] = []
        self.lock = threading.RLock()
        self.deleting: dict[str, int] = {}
        self.creating: dict[str, int] = {}
        self.deleting_flows: dict[str, int] = {}
        self.binding_changes: dict[str, int] = {}
        self.moving_flows: dict[str, int] = {}
        self.active_groups: dict[int, Any] = {}
        self.identity_changes = 0
        self.active_reset_flows: dict[str, Any] = {}

    @staticmethod
    def _increment(table: dict[str, int], names: list[str]) -> None:
        for name in names:
            table[name] = table.get(name, 0) + 1

    @staticmethod
    def _decrement(table: dict[str, int], names: list[str]) -> None:
        for name in names:
            remaining = table[name] - 1
            if remaining:
                table[name] = remaining
            else:
                del table[name]

    def _begin_delete(self, request: Any, evaluate: Any) -> tuple[Any, list[str], list[str]]:
        from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
        try:
            engine = self.engine_ref()
            with self.lock:
                # Scope/flow ownership is read while moves cannot begin, and
                # an already active move makes deletion retry rather than
                # observe a partially transferred node.
                if self.moving_flows or self.identity_changes:
                    return GenericResultFailure(result_details="[HMB_CONNECTION_IN_PROGRESS] 노드 이동이 진행 중입니다. 완료 후 다시 시도하세요."), [], []
                retained = _retained_nodes(engine)
                reset = _reset_identity.get()
                if reset and len(reset) > 2 and reset[2].get("active") and reset[0] == id(self) and type(request).__name__ == "DeleteNodeRequest":
                    state = reset[2]
                    name = getattr(request, "node_name", None)
                    target = retained.get(name)
                    if (target is not state["original"] and not
                            (state.get("cleanup") is True and target is state.get("replacement"))
                            and target is not None and _parent(engine, target) == state["flow"]):
                        return GenericResultFailure(result_details="[HMB_DELETE_IN_PROGRESS] 초기화 중인 작업의 다른 노드는 삭제할 수 없습니다."), [], []
                expected = _checked_delete_identity.get()
                if expected is not None and type(request).__name__ == "DeleteNodeRequest":
                    target_name, target_ref = expected
                    if (getattr(request, "node_name", None) != target_name
                            or retained.get(target_name) is not target_ref()):
                        return GenericResultFailure(result_details="[HMB_DELETE_SELECTION_CHANGED] 선택한 노드가 바뀌어 삭제를 중단했습니다."), [], []
                names = [name for name in _scope(engine, request)
                         if name in retained and _is_hmb(retained[name])]
                flows = sorted({_parent(engine, retained[name]) for name in names})
                for flow in flows:
                    active_reset = self.active_reset_flows.get(flow)
                    if active_reset is None:
                        continue
                    request_name = getattr(request, "node_name", None)
                    target = retained.get(request_name)
                    same_scope = bool(reset and len(reset) > 2 and reset[2] is active_reset and active_reset.get("active"))
                    permitted = same_scope and type(request).__name__ == "DeleteNodeRequest" and (
                        target is active_reset["original"] or (active_reset.get("cleanup") is True and target is active_reset.get("replacement")))
                    if not permitted:
                        return GenericResultFailure(result_details="[HMB_DELETE_IN_PROGRESS] 초기화 중인 작업의 다른 노드는 삭제할 수 없습니다."), [], []
                if any(name in self.creating for name in names) or any(flow in self.binding_changes for flow in flows):
                    return GenericResultFailure(result_details=(
                        "[HMB_CONNECTION_IN_PROGRESS] 연결이 변경 중입니다. 완료 후 삭제를 다시 시도하세요.")), [], []
                self._increment(self.deleting, names)
                self._increment(self.deleting_flows, flows)
                prepared_reset = None
                if type(request).__name__ == "ResetNodeToDefaultsRequest" and len(names) == 1 and len(flows) == 1:
                    prepared_reset = {"original": retained[names[0]], "flow": flows[0], "replacement": None, "active": True}
                    self.active_reset_flows[flows[0]] = prepared_reset
            try:
                denial = evaluate(request)
            except BaseException:
                with self.lock:
                    if prepared_reset is not None and self.active_reset_flows.get(prepared_reset["flow"]) is prepared_reset:
                        self.active_reset_flows.pop(prepared_reset["flow"], None)
                    self._decrement(self.deleting, names)
                    self._decrement(self.deleting_flows, flows)
                raise
            if denial is not None:
                with self.lock:
                    if prepared_reset is not None and self.active_reset_flows.get(prepared_reset["flow"]) is prepared_reset:
                        self.active_reset_flows.pop(prepared_reset["flow"], None)
                    self._decrement(self.deleting, names)
                    self._decrement(self.deleting_flows, flows)
                return denial, [], []
            return None, names, flows
        except Exception:
            return GenericResultFailure(result_details="[HMB_DELETE_CHECK_FAILED] 삭제 예약을 확인하지 못해 요청을 중단했습니다."), [], []

    def is_installed(self) -> bool:
        manager = self.manager_ref()
        mapping = getattr(manager, "_request_type_to_manager", None)
        return (manager is not None and isinstance(mapping, dict)
                and getattr(manager, HANDLER_BARRIER_ATTRIBUTE, None) is self
                and len(self.entries) == len(_DESTRUCTIVE) + 6
                and all(mapping.get(request_type) is wrapper and getattr(owner, name, None) is wrapper
                        for request_type, owner, name, _original, wrapper in self.entries))

    def prepare(self) -> None:
        engine, manager = self.engine_ref(), self.manager_ref()
        mapping = getattr(manager, "_request_type_to_manager", None)
        if engine is None or not isinstance(mapping, dict):
            raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 삭제 핸들러 등록을 확인할 수 없습니다.")
        handlers = dict(_DESTRUCTIVE)
        handlers["CreateConnectionRequest"] = ("connection_events", "CreateConnectionResultFailure")
        handlers["CreateNodeRequest"] = ("node_events", "CreateNodeResultFailure")
        handlers["MoveNodeToNewFlowRequest"] = ("node_events", "MoveNodeToNewFlowResultFailure")
        handlers["RenameObjectRequest"] = ("object_events", "RenameObjectResultFailure")
        handlers["AddNodesToNodeGroupRequest"] = ("node_events", "AddNodesToNodeGroupResultFailure")
        handlers["RemoveNodeFromNodeGroupRequest"] = ("node_events", "RemoveNodeFromNodeGroupResultFailure")
        for name, (module_name, _result_name) in handlers.items():
            request_type = getattr(importlib.import_module(
                "griptape_nodes.retained_mode.events." + module_name), name)
            original = mapping.get(request_type)
            owner = getattr(original, "__self__", None)
            method_name = getattr(original, "__name__", "")
            if owner is None or not method_name or getattr(owner, method_name, None) != original:
                raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 삭제 핸들러 소유권을 확인할 수 없습니다.")

            def check(request: Any, _engine_ref: Any = self.engine_ref) -> Any:
                engine = _engine_ref()
                if engine is None:
                    from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
                    return GenericResultFailure(result_details="[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 엔진을 확인할 수 없습니다.")
                # The migration transaction transfers retained identities first;
                # it is an existing trusted in-process scope, not a request flag.
                import sys
                migration = sys.modules.get("_hmb_workflow_migration")
                if migration is not None and migration.mutation_is_internal():
                    return None
                return guard_request(engine, request)

            if name == "CreateNodeRequest":
                if inspect.iscoroutinefunction(original):
                    raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 노드 생성 경계가 동기 방식이 아닙니다.")
                def make_create(fn: Any) -> Any:
                    @functools.wraps(fn)
                    def wrapped(request: Any) -> Any:
                        reset = _reset_identity.get()
                        result = fn(request)
                        if reset and len(reset) > 2 and reset[2].get("active") and reset[0] == id(self):
                            state = reset[2]
                            original_node = state["original"]
                            if (getattr(request, "node_name", None) == reset[1] + "_temp"
                                    and getattr(request, "override_parent_flow_name", None) == state["flow"]
                                    and getattr(request, "node_type", None) == type(original_node).__name__
                                    and getattr(request, "specific_library_name", None) == (getattr(original_node, "metadata", {}) or {}).get("library")
                                    and result.succeeded() and getattr(result, "node_name", None) == reset[1] + "_temp"):
                                engine = self.engine_ref()
                                replacement = engine.node_manager.get_node_by_name(result.node_name)
                                if (type(replacement) is type(original_node) and _parent(engine, replacement) == state["flow"]):
                                    state["replacement"] = replacement
                        return result
                    return wrapped
                wrapper = make_create(original)
            elif name in {"AddNodesToNodeGroupRequest", "RemoveNodeFromNodeGroupRequest"}:
                if inspect.iscoroutinefunction(original):
                    raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 그룹 변경 경계가 동기 방식이 아닙니다.")
                result_type = getattr(importlib.import_module(
                    "griptape_nodes.retained_mode.events." + module_name), _result_name)
                def make_group_change(fn: Any, failure: Any) -> Any:
                    @functools.wraps(fn)
                    def wrapped(request: Any) -> Any:
                        engine = self.engine_ref()
                        if engine is None:
                            return failure(result_details="[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 엔진을 확인할 수 없습니다.")
                        with self.lock:
                            inventory = engine.node_manager._name_to_parent_flow_name
                            if not isinstance(inventory, dict):
                                return failure(result_details="[HMB_DELETE_CHECK_FAILED] 그룹 소속을 확인할 수 없습니다.")
                            group_name = getattr(request, "node_group_name", None)
                            names = getattr(request, "node_names", None)
                            if not isinstance(names, list):
                                return failure(result_details="[HMB_DELETE_CHECK_FAILED] 그룹 노드를 확인할 수 없습니다.")
                            group = engine.node_manager.get_node_by_name(group_name) if group_name in inventory else None
                            subflow = (getattr(group, "metadata", {}) or {}).get("subflow_name") if group else None
                            flows = {inventory.get(name) for name in [group_name, *names]}
                            flows.update((getattr(request, "flow_name", None), subflow))
                            flows = sorted(flow for flow in flows if isinstance(flow, str) and flow)
                            if (self.identity_changes or any(flow in self.deleting_flows or flow in self.moving_flows
                                                             or flow in self.binding_changes for flow in flows)):
                                return failure(result_details="[HMB_CONNECTION_IN_PROGRESS] 그룹 연결 또는 삭제가 진행 중입니다.")
                            self._increment(self.moving_flows, flows)
                            group_ref = weakref.ref(group) if group is not None else None
                            if group_ref is not None:
                                self.active_groups[id(group)] = group_ref
                        group_flows = set(flows)
                        token = _group_mutation.set((id(self), group_flows, group_ref))
                        try:
                            return fn(request)
                        finally:
                            _group_mutation.reset(token)
                            with self.lock:
                                if group_ref is not None:
                                    self.active_groups.pop(id(group), None)
                                self._decrement(self.moving_flows, sorted(group_flows))
                    return wrapped
                wrapper = make_group_change(original, result_type)
            elif name == "RenameObjectRequest":
                if inspect.iscoroutinefunction(original):
                    raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 이름 변경 경계가 동기 방식이 아닙니다.")
                def make_rename(fn: Any) -> Any:
                    @functools.wraps(fn)
                    def wrapped(request: Any) -> Any:
                        from griptape_nodes.retained_mode.events.object_events import RenameObjectResultFailure
                        reset = _reset_identity.get()
                        old_name = getattr(request, "object_name", None)
                        new_name = getattr(request, "requested_name", None)
                        internal = (reset is not None and len(reset) > 2 and reset[2].get("active") and reset[0] == id(self)
                                    and old_name == reset[1] + "_temp" and new_name == reset[1])
                        if internal:
                            return fn(request)
                        with self.lock:
                            if self.deleting_flows or self.binding_changes or self.moving_flows:
                                return RenameObjectResultFailure(next_available_name=None, result_details="[HMB_CONNECTION_IN_PROGRESS] 연결이나 삭제가 진행 중입니다. 완료 후 이름을 변경하세요.")
                            self.identity_changes += 1
                        try:
                            return fn(request)
                        finally:
                            with self.lock:
                                self.identity_changes -= 1
                    return wrapped
                wrapper = make_rename(original)
            elif name == "MoveNodeToNewFlowRequest":
                if inspect.iscoroutinefunction(original):
                    raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 노드 이동 경계가 동기 방식이 아닙니다.")
                def make_move(fn: Any) -> Any:
                    @functools.wraps(fn)
                    def wrapped(request: Any) -> Any:
                        from griptape_nodes.retained_mode.events.node_events import MoveNodeToNewFlowResultFailure
                        engine = self.engine_ref()
                        if engine is None:
                            return MoveNodeToNewFlowResultFailure(result_details="[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 엔진을 확인할 수 없습니다.")
                        name = getattr(request, "node_name", None)
                        if name is None and engine.context_manager.has_current_node():
                            name = engine.context_manager.get_current_node().name
                        with self.lock:
                            inventory = engine.node_manager._name_to_parent_flow_name
                            if not isinstance(inventory, dict):
                                return MoveNodeToNewFlowResultFailure(result_details="[HMB_DELETE_CHECK_FAILED] 노드 소속을 확인할 수 없습니다.")
                            flows = list(dict.fromkeys(flow for flow in (
                                inventory.get(name), getattr(request, "target_flow_name", None)) if isinstance(flow, str) and flow))
                            marker = _subflow_teardown.get()
                            group = marker[1]() if marker is not None and marker[0] == id(self) else None
                            child = None
                            if group is not None and name:
                                try:
                                    child = engine.node_manager.get_node_by_name(name)
                                except (KeyError, ValueError):
                                    pass
                            owned_move = (group is not None and child is not None
                                and engine.node_manager.get_node_by_name(group.name) is group
                                and getattr(group, "nodes", {}).get(name) is child
                                and getattr(child, "parent_group", None) is group
                                and inventory.get(name) == group.metadata.get("subflow_name")
                                and getattr(request, "target_flow_name", None) == inventory.get(group.name))
                            # The scoped teardown may cross only reservations
                            # held exclusively by this very delete. Never
                            # borrow another concurrent delete's flow lease.
                            conflicting_delete = any(
                                flow in self.deleting_flows and not (
                                    owned_move and flow in marker[2] and self.deleting_flows[flow] == 1)
                                for flow in flows)
                            group_scope = _group_mutation.get()
                            scope_group = (group_scope[2]() if group_scope is not None and group_scope[0] == id(self)
                                           and group_scope[2] is not None else None)
                            created_subflow = (getattr(scope_group, "metadata", {}) or {}).get("subflow_name") if scope_group else None
                            if (scope_group is not None and isinstance(created_subflow, str) and created_subflow in flows
                                    and created_subflow not in group_scope[1]
                                    and inventory.get(scope_group.name) in group_scope[1]):
                                if (created_subflow in self.moving_flows or created_subflow in self.deleting_flows
                                        or created_subflow in self.binding_changes):
                                    return MoveNodeToNewFlowResultFailure(result_details="[HMB_CONNECTION_IN_PROGRESS] 해당 작업의 연결 또는 삭제가 진행 중입니다.")
                                self._increment(self.moving_flows, [created_subflow])
                                group_scope[1].add(created_subflow)
                            own_group_change = (group_scope is not None and group_scope[0] == id(self)
                                                and all(flow in group_scope[1] for flow in flows))
                            active_conflict = any((active := reference()) is not None and active is not scope_group
                                                  and (getattr(active, "metadata", {}) or {}).get("subflow_name") in flows
                                                  for reference in self.active_groups.values())
                            conflicting_move = ((any(flow in self.moving_flows for flow in flows) and not own_group_change)
                                                or active_conflict)
                            if (self.identity_changes or any(flow in self.binding_changes for flow in flows)
                                    or conflicting_delete or conflicting_move):
                                return MoveNodeToNewFlowResultFailure(result_details="[HMB_CONNECTION_IN_PROGRESS] 해당 작업의 연결 또는 삭제가 진행 중입니다.")
                            self._increment(self.moving_flows, flows)
                        try:
                            return fn(request)
                        finally:
                            with self.lock:
                                self._decrement(self.moving_flows, flows)
                    return wrapped
                wrapper = make_move(original)
            elif name == "CreateConnectionRequest":
                if inspect.iscoroutinefunction(original):
                    raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 연결 생성 경계가 동기 방식이 아닙니다.")
                def make_connection(fn: Any) -> Any:
                    @functools.wraps(fn)
                    def wrapped(request: Any) -> Any:
                        from griptape_nodes.retained_mode.events.connection_events import CreateConnectionResultFailure
                        engine = self.engine_ref()
                        if engine is None:
                            return CreateConnectionResultFailure(result_details="[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 엔진을 확인할 수 없습니다.")
                        permit = _reset_handoff.get()
                        if permit and permit.get("active") and permit.get("barrier") is self:
                            return CreateConnectionResultFailure(result_details="[HMB_DELETE_IN_PROGRESS] 초기화 중에는 새 연결을 만들 수 없습니다.")
                        source = getattr(request, "source_node_name", None)
                        target = getattr(request, "target_node_name", None)
                        if source is None or target is None:
                            current = engine.context_manager.get_current_node().name if engine.context_manager.has_current_node() else None
                            source, target = source or current, target or current
                        names = list(dict.fromkeys(name for name in (source, target) if isinstance(name, str)))
                        with self.lock:
                            inventory = engine.node_manager._name_to_parent_flow_name
                            if (not isinstance(inventory, dict) or any(inventory.get(name) in self.active_reset_flows for name in names)):
                                return CreateConnectionResultFailure(result_details=(
                                    "[HMB_DELETE_IN_PROGRESS] 초기화 중인 작업에는 새 연결을 만들 수 없습니다."))
                            if source in self.deleting or target in self.deleting:
                                return CreateConnectionResultFailure(result_details=(
                                    "[HMB_DELETE_IN_PROGRESS] 해당 노드 삭제가 진행 중입니다. 완료 후 연결을 다시 시도하세요."))
                            self._increment(self.creating, names)
                        try:
                            return fn(request)
                        finally:
                            with self.lock:
                                self._decrement(self.creating, names)
                    return wrapped
                wrapper = make_connection(original)
            elif inspect.iscoroutinefunction(original):
                def make_async(fn: Any, evaluate: Any) -> Any:
                    @functools.wraps(fn)
                    async def wrapped(request: Any) -> Any:
                        denial, selected, flows = self._begin_delete(request, evaluate)
                        if denial is not None:
                            return denial
                        engine = self.engine_ref()
                        reset_state = None
                        if type(request).__name__ == "ResetNodeToDefaultsRequest" and len(selected) == 1:
                            original_node = engine.node_manager.get_node_by_name(selected[0])
                            with self.lock:
                                reset_state = self.active_reset_flows.get(_parent(engine, original_node))
                                if reset_state is None or reset_state.get("original") is not original_node:
                                    raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] 초기화 대상 예약을 확인하지 못했습니다.")
                        token = (_reset_identity.set((id(self), selected[0], reset_state)) if reset_state else None)
                        subflow_token = None
                        try:
                            plain_group = None
                            if type(request).__name__ == "DeleteNodeRequest":
                                reset = _reset_identity.get()
                                if reset and len(reset) > 2 and reset[2].get("active") and reset[0] == id(self) and getattr(request, "node_name", None) == reset[1]:
                                    from _hmb_shot_routing import _subscription_for, SINGLETON_KINDS
                                    import _hmb_shot_routing as routing
                                    from griptape_nodes.retained_mode.events.node_events import DeleteNodeResultFailure
                                    state = reset[2]
                                    owner = state["original"]
                                    sub = _subscription_for(owner)
                                    if sub is not None and sub.kind in SINGLETON_KINDS:
                                        replacement = state.get("replacement")
                                        if (replacement is None or engine.node_manager.get_node_by_name(owner.name) is not owner
                                                or engine.node_manager.get_node_by_name(replacement.name) is not replacement
                                                or _parent(engine, replacement) != state["flow"]):
                                            return DeleteNodeResultFailure(result_details="[HMB_RESET_HANDOFF_FAILED] 원본 샷을 보존할 대체 노드를 확인하지 못했습니다.")
                                        permit = {"active": True, "thread": threading.get_ident(), "barrier": self,
                                                  "node": replacement, "flow": state["flow"]}
                                        handoff_token = _reset_handoff.set(permit)
                                        try:
                                            exporter = getattr(owner, "_hmb_export_reset_handoff", None)
                                            adopter = getattr(replacement, "_hmb_adopt_reset_handoff", None)
                                            payload = exporter() if callable(exporter) else None
                                            transferred = isinstance(payload, dict) and callable(adopter) and adopter(payload) is True
                                            if transferred:
                                                with routing._ROUTING_LOCK:
                                                    routing._SINGLETON_RESET_HANDOFFS[replacement] = weakref.ref(owner)
                                        except Exception:
                                            transferred = False
                                        finally:
                                            permit["active"] = False
                                            _reset_handoff.reset(handoff_token)
                                        if not transferred:
                                            return DeleteNodeResultFailure(result_details="[HMB_RESET_HANDOFF_FAILED] 기존 샷과 미디어를 보존하지 못해 초기화를 중단했습니다.")
                                from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
                                from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup
                                engine = self.engine_ref()
                                target = getattr(request, "node_name", None)
                                if target is None and engine.context_manager.has_current_node():
                                    target = engine.context_manager.get_current_node().name
                                try:
                                    group = engine.node_manager.get_node_by_name(target) if target else None
                                except (KeyError, ValueError):
                                    group = None
                                if isinstance(group, SubflowNodeGroup):
                                    subflow_token = _subflow_teardown.set((id(self), weakref.ref(group), frozenset(flows)))
                                elif type(group) is BaseNodeGroup and selected:
                                    plain_group = group
                            result = await fn(request)
                            if reset_state and not result.succeeded():
                                replacement = reset_state.get("replacement")
                                try:
                                    retained = engine.node_manager.get_node_by_name(replacement.name) if replacement is not None else None
                                    edges = tuple(engine.flow_manager.get_connections().connections.values())
                                    object_manager = engine.object_manager
                                    original_name = selected[0]
                                    if (replacement is not None and retained is replacement
                                            and not object_manager.has_object_with_name(original_name)
                                            and _parent(engine, replacement) == reset_state["flow"]
                                            and not any(edge.source_node is replacement or edge.target_node is replacement for edge in edges)):
                                        from griptape_nodes.retained_mode.events.object_events import RenameObjectRequest
                                        from griptape_nodes.retained_mode.events.node_events import ResetNodeToDefaultsResultSuccess, ResetNodeToDefaultsResultFailure
                                        try:
                                            rename = object_manager.on_rename_object_request(RenameObjectRequest(
                                                object_name=replacement.name, requested_name=original_name,
                                                allow_next_closest_name_available=False))
                                            restored = rename.succeeded() and engine.node_manager.get_node_by_name(original_name) is replacement
                                        except Exception:
                                            restored = False
                                        if restored:
                                            result = ResetNodeToDefaultsResultSuccess(node_name=original_name,
                                                failed_incoming_connections=[], failed_outgoing_connections=[],
                                                result_details="초기화 후 원래 노드 이름을 복구했습니다.")
                                        else:
                                            result = ResetNodeToDefaultsResultFailure(result_details=(
                                                "[HMB_RESET_RENAME_FAILED] 원래 이름을 복구하지 못했습니다. "
                                                f"샷과 미디어는 {replacement.name} 노드에 보존되어 있습니다. "
                                                "해당 노드를 삭제하지 말고 연결과 이름을 확인하세요."))
                                    if (replacement is not None and retained is replacement
                                            and engine.node_manager.get_node_by_name(reset_state["original"].name) is reset_state["original"]
                                            and _parent(engine, replacement) == reset_state["flow"]
                                            and not any(edge.source_node is replacement or edge.target_node is replacement for edge in edges)):
                                        from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest
                                        reset_state["cleanup"] = True
                                        try:
                                            await engine.node_manager.on_delete_node_request(DeleteNodeRequest(node_name=replacement.name))
                                        finally:
                                            reset_state["cleanup"] = False
                                except (KeyError, ValueError):
                                    # A replacement changed or acquired a connection: never remove it blindly.
                                    pass
                            if plain_group is not None and result.succeeded():
                                # SDK plain groups otherwise leave live members
                                # pointing at an already-deleted group object.
                                # Do this only after success and only for exact
                                # still-retained members of the deleted group.
                                members = []
                                for member in tuple(plain_group.nodes.values()):
                                    try:
                                        if (getattr(member, "parent_group", None) is plain_group
                                                and engine.node_manager.get_node_by_name(member.name) is member):
                                            members.append(member)
                                    except (KeyError, ValueError):
                                        continue
                                plain_group.remove_nodes_from_group(members)
                            return result
                        finally:
                            if subflow_token is not None:
                                _subflow_teardown.reset(subflow_token)
                            if token is not None:
                                reset_state["active"] = False
                                with self.lock:
                                    if self.active_reset_flows.get(reset_state["flow"]) is reset_state:
                                        self.active_reset_flows.pop(reset_state["flow"], None)
                                _reset_identity.reset(token)
                            with self.lock:
                                self._decrement(self.deleting, selected)
                                self._decrement(self.deleting_flows, flows)
                    return wrapped
                wrapper = make_async(original, check)
            else:
                def make_sync(fn: Any, evaluate: Any) -> Any:
                    @functools.wraps(fn)
                    def wrapped(request: Any) -> Any:
                        denial, selected, flows = self._begin_delete(request, evaluate)
                        if denial is not None:
                            return denial
                        try:
                            return fn(request)
                        finally:
                            with self.lock:
                                self._decrement(self.deleting, selected)
                                self._decrement(self.deleting_flows, flows)
                    return wrapped
                wrapper = make_sync(original, check)
            self.entries.append((request_type, owner, method_name, original, wrapper))

    def install(self) -> None:
        manager = self.manager_ref()
        mapping = manager._request_type_to_manager
        installed = []
        try:
            for request_type, owner, name, original, wrapper in self.entries:
                if mapping.get(request_type) is not original or getattr(owner, name, None) != original:
                    raise RuntimeError("SDK 삭제 핸들러가 설치 중 변경됐습니다.")
                setattr(owner, name, wrapper)
                mapping[request_type] = wrapper
                installed.append((request_type, owner, name, original, wrapper))
            setattr(manager, HANDLER_BARRIER_ATTRIBUTE, self)
            if not self.is_installed():
                raise RuntimeError("SDK 삭제 핸들러 보호 등록에 실패했습니다.")
            with _BINDING_BARRIERS_LOCK:
                _BINDING_BARRIERS[self.engine_ref()] = self
        except Exception:
            for request_type, owner, name, original, wrapper in reversed(installed):
                if mapping.get(request_type) is wrapper:
                    mapping[request_type] = original
                if getattr(owner, name, None) is wrapper:
                    setattr(owner, name, original)
            if getattr(manager, HANDLER_BARRIER_ATTRIBUTE, None) is self:
                delattr(manager, HANDLER_BARRIER_ATTRIBUTE)
            raise


def install_handler_barrier(engine: Any) -> Any:
    manager = engine.event_manager
    existing = getattr(manager, HANDLER_BARRIER_ATTRIBUTE, None)
    if existing is not None:
        if (not callable(getattr(existing, "engine_ref", None)) or existing.engine_ref() is not engine
                or not callable(getattr(existing, "is_installed", None)) or not existing.is_installed()):
            raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 삭제 핸들러 보호 소유권이 변경됐습니다.")
        return existing
    barrier = _HandlerDeletionBarrier(engine, manager)
    barrier.prepare()
    barrier.install()
    return barrier


class _ReentrantDeletionBarrier:
    """Guard destructive SDK requests even inside another pre-dispatch hook.

    Some SDKs deliberately skip *all* hooks during re-entrant dispatch. Wrap
    that boundary once per engine and only add the missing destructive check;
    normal dispatch and non-destructive nested requests stay SDK-owned.
    """

    def __init__(self, engine: Any, manager: Any, original: Any, failure: Any) -> None:
        self.engine_ref = weakref.ref(engine)
        self.manager_ref = weakref.ref(manager)
        self.original = original
        self.failure = failure
        self.wrapper = self._invoke

    def is_installed(self) -> bool:
        manager = self.manager_ref()
        return (manager is not None
                and getattr(manager, REENTRANT_BARRIER_ATTRIBUTE, None) is self
                and getattr(manager, "_run_pre_dispatch_hooks", None) is self.wrapper
                and getattr(manager, "_hook_evaluation", None) is not None)

    def _invoke(self, request: Any, context: Any) -> Any:
        manager, engine = self.manager_ref(), self.engine_ref()
        if manager is None or engine is None:
            return self.failure(result_details="[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 엔진을 확인할 수 없습니다.")
        if (getattr(manager._hook_evaluation, "active", False) is True
                and type(request).__name__ in _DESTRUCTIVE):
            try:
                # A nested call bypasses the lifetime gate as well as every
                # other hook. Do not let an unready or replaced barrier become
                # a way to remove any HMB node during a hot update.
                ready, _ = protection_readiness(engine)
                if not ready and any(_is_hmb(node) for node in _retained_nodes(engine).values()):
                    return self.failure(result_details="[HMB_DELETE_GUARD_NOT_READY] 재진입 삭제 보호가 준비되지 않아 요청을 중단했습니다.")
                return guard_request(engine, request)
            except Exception:
                return self.failure(result_details="[HMB_DELETE_CHECK_FAILED] 재진입 삭제 보호를 확인하지 못해 요청을 중단했습니다.")
        return self.original(request, context)


def install_reentrant_barrier(engine: Any) -> Any:
    """Install only when the SDK's re-entrant hook boundary is identifiable."""
    from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure

    manager = engine.event_manager
    lock = getattr(manager, "_pre_dispatch_hooks_lock", None)
    if not callable(getattr(lock, "__enter__", None)) or getattr(manager, "_hook_evaluation", None) is None:
        raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 재진입 보호 경계를 확인할 수 없습니다.")
    with lock:
        barrier = getattr(manager, REENTRANT_BARRIER_ATTRIBUTE, None)
        if barrier is not None:
            if (not callable(getattr(barrier, "engine_ref", None)) or barrier.engine_ref() is not engine
                    or not callable(getattr(barrier, "is_installed", None)) or not barrier.is_installed()):
                raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 재진입 보호 소유권이 변경됐습니다.")
            install_handler_barrier(engine)
            return barrier
        original = getattr(manager, "_run_pre_dispatch_hooks", None)
        if not callable(original):
            raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 재진입 보호 함수가 없습니다.")
        try:
            inspect.signature(original).bind(object(), object())
        except (TypeError, ValueError) as exc:
            raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 재진입 보호 함수 형식이 다릅니다.") from exc
        barrier = _ReentrantDeletionBarrier(engine, manager, original, GenericResultFailure)
        setattr(manager, "_run_pre_dispatch_hooks", barrier.wrapper)
        setattr(manager, REENTRANT_BARRIER_ATTRIBUTE, barrier)
        if not barrier.is_installed():
            raise RuntimeError("[HMB_DELETE_GUARD_NOT_READY] SDK 재진입 보호 등록에 실패했습니다.")
        try:
            install_handler_barrier(engine)
        except Exception:
            if getattr(manager, "_run_pre_dispatch_hooks", None) is barrier.wrapper:
                setattr(manager, "_run_pre_dispatch_hooks", original)
            if getattr(manager, REENTRANT_BARRIER_ATTRIBUTE, None) is barrier:
                delattr(manager, REENTRANT_BARRIER_ATTRIBUTE)
            raise
        return barrier


def protection_readiness(engine: Any) -> tuple[bool, str]:
    """Report the installed engine gate, never an optimistic library lease."""
    gate = getattr(engine.event_manager, LIFETIME_GATE_ATTRIBUTE, None)
    if (getattr(gate, "protection_version", None) != PROTECTION_VERSION
            or not callable(getattr(gate, "engine_ref", None))
            or gate.engine_ref() is not engine
            or getattr(gate, "installed", False) is not True):
        return False, "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호가 준비되지 않았습니다. Griptape를 다시 시작하세요."
    try:
        installed = callable(getattr(gate, "is_registered", None)) and gate.is_registered()
    except Exception:
        installed = False
    if not installed:
        gate.ready = False
        gate.readiness_error = "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 요청 gate가 등록되어 있지 않습니다. 라이브러리를 새로고침하거나 Griptape를 다시 시작하세요."
        return False, gate.readiness_error
    if getattr(gate, "ready", False) is not True:
        return False, str(getattr(gate, "readiness_error", "")) or "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 초기화가 완료되지 않았습니다."
    barrier = getattr(engine.event_manager, REENTRANT_BARRIER_ATTRIBUTE, None)
    if (not callable(getattr(barrier, "engine_ref", None)) or barrier.engine_ref() is not engine
            or not callable(getattr(barrier, "is_installed", None)) or not barrier.is_installed()):
        return False, "[HMB_DELETE_GUARD_NOT_READY] 재진입 삭제 보호가 준비되지 않았습니다. Griptape를 다시 시작하세요."
    handler = getattr(engine.event_manager, HANDLER_BARRIER_ATTRIBUTE, None)
    if (not callable(getattr(handler, "engine_ref", None)) or handler.engine_ref() is not engine
            or not callable(getattr(handler, "is_installed", None)) or not handler.is_installed()):
        return False, "[HMB_DELETE_GUARD_NOT_READY] 삭제 핸들러 보호가 준비되지 않았습니다. Griptape를 다시 시작하세요."
    return True, ""


def _is_hmb(node: Any) -> bool:
    metadata = getattr(node, "metadata", None)
    return isinstance(metadata, dict) and metadata.get("library") == LIBRARY


def _retained_nodes(engine: Any) -> dict[str, Any]:
    # Read-only inventory also distinguishes an old same-name Python object
    # from the live one after a load/reset. Never trust node names alone.
    mapping = engine.node_manager._name_to_parent_flow_name
    return {name: engine.node_manager.get_node_by_name(name) for name in tuple(mapping)}


def _parent(engine: Any, node: Any) -> str:
    return engine.node_manager.get_node_parent_flow_by_name(node.name)


def _wire_peers(engine: Any, node: Any, retained: dict[str, Any]) -> set[str]:
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
    result = engine.handle_request(ListConnectionsForNodeRequest(
        node_name=node.name, include_internal=True, broadcast_result=False))
    if not result.succeeded():
        raise ValueError("connection inventory unavailable")
    names = {edge.source_node_name for edge in result.incoming_connections}
    names.update(edge.target_node_name for edge in result.outgoing_connections)
    return {name for name in names if name in retained}


def _remote_document(node: Any, parameter: str) -> dict[str, Any]:
    """Read an already-retained value; never call a resolving snapshot API."""
    import json
    getter = getattr(node, "get_parameter_value", None)
    try:
        value = getter(parameter) if callable(getter) else None
        value = getattr(value, "value", value)
        if isinstance(value, str):
            value = json.loads(value)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError, AttributeError):
        return {}


def _remote_catalog(subscription: Any, document: dict[str, Any]) -> dict[str, Any]:
    """A bounded current catalog/watermark, not a dropdown or media snapshot."""
    kind, node = subscription.kind, subscription.node
    if kind == "image_asset":
        state = getattr(node, "_hmb_catalog_search_authority", None)
        state = document or (state if isinstance(state, dict) else {})
        value = state.get("shot_routing")
    elif kind == "video_picker":
        value = getattr(node, "_hmb_shot_catalog_snapshot", None)
        if not isinstance(value, dict) or not value:
            value = {"publisher_instance_uuid": document.get("accepted_shot_catalog_publisher_instance_uuid"),
                     "channel_uuid": document.get("accepted_shot_catalog_channel_uuid")}
    elif kind == "prompt":
        image = document.get("image_asset")
        value = image.get("shot_catalog_routing") if isinstance(image, dict) else None
    elif kind in {"agent", "finish_look"}:
        value = getattr(node, "_hmb_shot_catalog_snapshot", None) or document.get("shot_catalog")
    elif kind == "color_lut":
        state = getattr(node, "_hmb_color_lut_state", None)
        value = state.get("shot_catalog") if isinstance(state, dict) else document.get("shot_catalog")
    else:
        value = getattr(node, "_hmb_shot_catalog_snapshot", None)
    return value if isinstance(value, dict) else {}


def _remote_completed_source(node: Any) -> dict[str, Any]:
    # The normal snapshot getter may restore provenance by probing a file and
    # writing parameters. Deletion preflight must only read existing receipts.
    value = getattr(node, "_hmb_generated_video_source", None)
    if not isinstance(value, dict) or not value:
        value = _remote_document(node, "HMB_GENERATED_VIDEO_SOURCE")
    if (not isinstance(value, dict) or value.get("schema") != "hmb-generated-video-source"
            or value.get("version") != 1 or value.get("completed") is not True
            or not value.get("task_id") or value.get("generation_id") != value.get("task_id")
            or type(value.get("result_revision")) is not int or value["result_revision"] < 1
            or any(not value.get(key) for key in
                   ("channel_uuid", "shot_uuid", "source_node_instance_id", "path"))):
        return {}
    return value


def _remote_pairs(nodes: dict[str, Any], parents: dict[str, str]) -> set[tuple[str, str]]:
    from _hmb_shot_routing import (
        _subscription_for, _single, _manager_prompt_for_agent, _agent_for_target,
        _manager_shot_subscriptions, _is_shot_manager,
    )
    pairs: set[tuple[str, str]] = set()
    subscriptions = {name: sub for name, node in nodes.items()
                     if _is_hmb(node) and (sub := _subscription_for(node)) is not None}
    parameter_names = {"image_asset": "HMB_IMAGE_ASSET_STATE", "video_picker": "HMB_PICKER_STATE",
                       "prompt": "HMB_UI_STATE", "agent": "HMB_AGENT_UI",
                       "finish_look": "HMB_FINISH_LOOK_UI_STATE", "color_lut": "HMB_COLOR_LUT_UI_STATE"}
    documents = {name: _remote_document(sub.node, parameter_names[sub.kind])
                 if sub.kind in parameter_names else {} for name, sub in subscriptions.items()}
    catalogs = {name: _remote_catalog(sub, documents[name]) for name, sub in subscriptions.items()}
    rows = {name: (_manager_shot_subscriptions(sub.node, sub.kind)
                   if _is_shot_manager(sub.node) else (sub,)) for name, sub in subscriptions.items()}

    def add(source: Any, target: Any) -> None:
        if (source is not None and target is not None and source.node is not target.node
                and nodes.get(source.node_name) is source.node and nodes.get(target.node_name) is target.node
                and parents[source.node_name] == parents[target.node_name]):
            pairs.add((source.node_name, target.node_name))

    def agrees(authority: Any, target: Any) -> bool:
        if not target.enabled or target.channel_uuid != authority.channel_uuid:
            return False
        source_catalog, target_catalog = catalogs[authority.node_name], catalogs[target.node_name]
        # Absence keeps the supported legacy scalar contract. Explicit foreign
        # publisher/channel evidence cannot be promoted to a current binding.
        for key in ("publisher_instance_uuid", "channel_uuid"):
            if source_catalog.get(key) and target_catalog.get(key) and source_catalog[key] != target_catalog[key]:
                return False
        declared = source_catalog.get("shots")
        if target.kind != "video_picker" and isinstance(declared, list):
            return any(isinstance(row, dict) and row.get("shot_uuid") == target.shot_uuid for row in declared)
        return True

    for flow in set(parents[name] for name in subscriptions):
        values = tuple(sub for name, sub in subscriptions.items() if parents[name] == flow)
        images = tuple(sub for sub in values if sub.kind == "image_asset" and sub.enabled)
        standalone = tuple(sub for sub in values if sub.kind == "video_picker" and sub.enabled
                           and not documents[sub.node_name].get("channel_uuid"))

        def authority(target: Any) -> Any:
            selected, duplicate = _single(values, kind="image_asset", channel_uuid=target.channel_uuid)
            if not duplicate and selected is not None and agrees(selected, target):
                return selected
            # Exact current router policy: standalone Picker advertises only
            # to Seedance/LUT. Prompt, Agent and Finish still require ImageAsset.
            if not images and target.kind in {"seedance", "color_lut"} and len(standalone) == 1:
                selected = standalone[0]
                if selected.channel_uuid == target.channel_uuid and target.enabled:
                    state = documents[selected.node_name]
                    declared = state.get("picker_shots")
                    if not isinstance(declared, list) or any(
                            isinstance(row, dict) and row.get("workspace_uuid") == target.shot_uuid for row in declared):
                        return selected
            return None

        eligible = tuple(sub for sub in values if sub.enabled and (
            sub.kind == "image_asset" or any(authority(row) is not None for row in rows[sub.node_name])))
        for target in eligible:
            if target.kind == "image_asset":
                continue
            active_rows = tuple(row for row in rows[target.node_name] if authority(row) is not None)
            for row in active_rows:
                add(authority(row), row)
                if row.kind in {"prompt", "seedance"}:
                    picker, duplicate = _single(eligible, kind="video_picker", channel_uuid=row.channel_uuid)
                    if not duplicate:
                        add(picker, row)
                if row.kind == "seedance":
                    agent, duplicate = _agent_for_target(row, eligible)
                    if (not duplicate and agent is not None and authority(agent) is not None
                            and (agent.shot_number, agent.shot_name) == (row.shot_number, row.shot_name)):
                        add(agent, row)
                    finish, duplicate = _single(eligible, kind="finish_look", channel_uuid=row.channel_uuid, shot_uuid=row.shot_uuid)
                    if (not duplicate and finish is not None and authority(finish) is not None
                            and (finish.shot_number, finish.shot_name) == (row.shot_number, row.shot_name)):
                        add(finish, row)
            if target.kind == "agent" and active_rows:
                prompt, duplicate = (_manager_prompt_for_agent(target, eligible) if _is_shot_manager(target.node)
                    else _single(eligible, kind="prompt", channel_uuid=target.channel_uuid, shot_uuid=target.shot_uuid))
                if not duplicate and prompt is not None and authority(prompt) is not None:
                    add(prompt, target)

        completed: dict[tuple[str, str], list[tuple[Any, dict[str, Any]]]] = {}
        for source in values:
            if source.kind == "seedance":
                receipt = _remote_completed_source(source.node)
                if receipt:
                    completed.setdefault((receipt["channel_uuid"], receipt["shot_uuid"]), []).append((source, receipt))
        for target in values:
            if target.kind != "color_lut" or not target.enabled:
                continue
            candidates = completed.get((target.channel_uuid, target.shot_uuid), ())
            if len(candidates) != 1:
                continue
            source, receipt = candidates[0]
            state = getattr(target.node, "_hmb_color_lut_state", None)
            previous = state.get("source") if isinstance(state, dict) else documents[target.node_name].get("source")
            keys = ("channel_uuid", "shot_uuid", "source_node_instance_id", "task_id", "generation_id", "result_revision")
            # A completed file merely offered for the selected Shot is not a
            # binding. A matching already-accepted LUT origin is required.
            if (not isinstance(previous, dict) or not previous
                    or any(previous.get(key) != receipt.get(key) for key in keys)
                    or (previous.get("_reference_path") or previous.get("path")) != receipt.get("path")):
                continue
            add(source, target)
    # Future HMB non-wire bindings join this contract without editing a type
    # allowlist. Returning stale/foreign objects never protects an unrelated node.
    for name, node in nodes.items():
        if not _is_hmb(node) or bool(getattr(node, "_hmb_node_deleted", False)):
            continue
        getter = getattr(node, "_hmb_deletion_dependencies", None)
        if not callable(getter):
            continue
        peers = getter()
        if not isinstance(peers, (list, tuple, set, frozenset)):
            raise ValueError("invalid deletion dependency contract")
        for peer in peers:
            peer_name = getattr(peer, "name", None)
            if (peer is not node and nodes.get(peer_name) is peer and not bool(getattr(peer, "_hmb_node_deleted", False))
                    and parents[peer_name] == parents[name]):
                pairs.add((peer_name, name))
    from _hmb_connection_management import relationship_suspended
    return {(source, target) for source, target in pairs
            if not relationship_suspended(nodes[source], nodes[target])}


def connected_targets(engine: Any, node_names: list[str]) -> dict[str, list[str]]:
    """Read-only batch preflight, also usable before an editor deletes edges."""
    retained = _retained_nodes(engine)
    targets = [retained[name] for name in dict.fromkeys(node_names)
               if name in retained and _is_hmb(retained[name])]
    if not targets:
        return {}
    parents = {name: _parent(engine, node) for name, node in retained.items()}
    # Restrict all non-wire observations to flows involved in this request.
    flows = {parents[node.name] for node in targets}
    scoped = {name: node for name, node in retained.items() if parents[name] in flows}
    pairs = _remote_pairs(scoped, parents)
    blocked = {}
    for node in targets:
        peers = _wire_peers(engine, node, retained)
        for source, target in pairs:
            if node.name == source:
                peers.add(target)
            elif node.name == target:
                peers.add(source)
        if peers:
            blocked[node.name] = sorted(peers)
    return blocked


def _scope(engine: Any, request: Any) -> list[str]:
    name = type(request).__name__
    retained = _retained_nodes(engine)
    if name in {"DeleteNodeRequest", "ResetNodeToDefaultsRequest"}:
        target = getattr(request, "node_name", None)
        if target is None and engine.context_manager.has_current_node():
            target = engine.context_manager.get_current_node().name
        return _selection_scope(engine, [target]) if target in retained else []
    if name == "DeleteWorkflowRequest":
        context = engine.context_manager
        if not context.has_current_workflow() or request.name != context.get_current_workflow_name():
            return []
    if name != "DeleteFlowRequest":
        return list(retained)
    target = getattr(request, "flow_name", None)
    if target is None and engine.context_manager.has_current_flow():
        target = engine.context_manager.get_current_flow().name
    if not target:
        return []
    def within(flow: str) -> bool:
        visited = set()
        while flow and flow not in visited:
            if flow == target:
                return True
            visited.add(flow)
            flow = engine.flow_manager.get_parent_flow(flow)
            if flow is not None and not isinstance(flow, str):
                flow = flow.name
        return False
    return [key for key, node in retained.items() if within(_parent(engine, node))]


def _group_owned_descendants(retained: dict[str, Any], names: list[str]) -> set[str]:
    """Find actual group members, including nested group membership."""
    result = set(names)
    for name, node in retained.items():
        owner = getattr(node, "parent_group", None)
        seen = set()
        while owner is not None and id(owner) not in seen:
            seen.add(id(owner))
            owner_name = owner if isinstance(owner, str) else getattr(owner, "name", None)
            if owner_name in names:
                result.add(name)
                break
            owner = getattr(retained.get(owner_name), "parent_group", None)
    return result


def _subflow_inventory(engine: Any, names: list[str], retained: dict[str, Any]) -> dict[str, set[str]]:
    """Include every retained node in a group's actual nested flow tree."""
    from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup
    result: dict[str, set[str]] = {}
    for name in names:
        group = retained.get(name)
        if not isinstance(group, SubflowNodeGroup):
            continue
        root = group.metadata.get("subflow_name") if isinstance(group.metadata, dict) else None
        if not isinstance(root, str) or not root:
            continue
        members = set()
        for candidate, node in retained.items():
            flow, seen = _parent(engine, node), set()
            while flow and flow not in seen:
                if flow == root:
                    members.add(candidate)
                    break
                seen.add(flow)
                flow = engine.flow_manager.get_parent_flow(flow)
                if flow is not None and not isinstance(flow, str):
                    flow = flow.name
        result[name] = members
    return result


def _selection_scope(engine: Any, names: list[str]) -> list[str]:
    """Include both group membership and actual subflow descendants."""
    retained = _retained_nodes(engine)
    result = _group_owned_descendants(retained, names)
    for members in _subflow_inventory(engine, list(result), retained).values():
        result.update(members)
    return sorted(result)


def _subflow_ungrouped(engine: Any, names: list[str]) -> dict[str, list[str]]:
    """Refuse anomalous contents before native group teardown has side effects.

    Native group teardown moves members first and then deletes its subflow;
    ungrouped retained objects there would otherwise be deleted or cause a
    late refusal after members were already moved.
    """
    retained = _retained_nodes(engine)
    result = {}
    for name, contents in _subflow_inventory(engine, names, retained).items():
        owned = _group_owned_descendants(retained, [name])
        ungrouped = sorted(contents - owned)
        if ungrouped and any(_is_hmb(retained[item]) for item in contents | {name}):
            result[name] = ungrouped
    return result


def _group_receipt(node: Any) -> Any:
    parent = getattr(node, "parent_group", None)
    return parent if parent is None or isinstance(parent, str) else weakref.ref(parent)


def _same_group(node: Any, receipt: Any) -> bool:
    parent = getattr(node, "parent_group", None)
    return receipt() is parent if isinstance(receipt, weakref.ReferenceType) else receipt == parent


def message(blocked: dict[str, list[str]]) -> str:
    rows = [f"{name} → {', '.join(peers)}" for name, peers in blocked.items()]
    return (f"[{CODE}] 연결된 HMB 툴은 삭제하거나 초기화할 수 없습니다.\n"
            + "\n".join(rows)
            + "\n선 연결과 리모트 샷 바인딩을 먼저 해제하세요. 기존 샷과 결과는 유지됩니다.")


def guard_request(engine: Any, request: Any) -> Any:
    kind = type(request).__name__
    if kind not in _DESTRUCTIVE:
        return None
    # The lifetime hook must not authorize normal dispatch if its re-entrant
    # companion was removed, replaced, or could not be verified. Standard-only
    # graphs stay SDK-owned; an inventory error fails closed.
    try:
        ready, _ = protection_readiness(engine)
        if not ready and any(_is_hmb(node) for node in _retained_nodes(engine).values()):
            from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
            return GenericResultFailure(result_details="[HMB_DELETE_GUARD_NOT_READY] 삭제 보호가 준비되지 않아 요청을 중단했습니다.")
    except Exception:
        from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
        return GenericResultFailure(result_details="[HMB_DELETE_CHECK_FAILED] 삭제 보호 소유권을 확인하지 못해 요청을 중단했습니다.")
    from griptape_nodes.retained_mode.managers.event_manager import current_request_type
    parent = current_request_type()
    parent_name = parent.__name__ if parent is not None else ""
    if kind == "ClearAllObjectStateRequest" and parent_name in _LOAD_PARENTS:
        _teardown_engine.set(id(engine))
        return None
    if (_teardown_engine.get() == id(engine) and parent_name in _TEARDOWN_CHILDREN
            and kind in _TEARDOWN_CHILDREN):
        return None
    # A marker cannot authorize a later independent client request, even when
    # it is dispatched on a thread/task reused after the completed load.
    if not parent_name:
        _teardown_engine.set(None)
    module_name, result_name = _DESTRUCTIVE[kind]
    result_type = getattr(importlib.import_module(
        "griptape_nodes.retained_mode.events." + module_name), result_name)
    try:
        scope = _scope(engine, request)
        blocked = connected_targets(engine, scope)
        ungrouped = (_subflow_ungrouped(engine, scope)
                     if kind in {"DeleteNodeRequest", "ResetNodeToDefaultsRequest"} else {})
    except Exception:
        return result_type(result_details=(
            "[HMB_DELETE_CHECK_FAILED] 연결 상태를 확인하지 못해 삭제를 중단했습니다. "
            "연결 상태를 새로고침한 뒤 다시 시도하세요. 기존 데이터는 유지됩니다."))
    if blocked:
        return result_type(result_details=message(blocked))
    if ungrouped:
        rows = [f"{name} → {', '.join(nodes)}" for name, nodes in ungrouped.items()]
        return result_type(result_details=("[HMB_SUBFLOW_UNGROUPED] 그룹 하위 작업에 그룹에 속하지 않은 노드가 있어 "
            "삭제를 중단했습니다. 해당 노드를 그룹에 추가하거나 다른 작업으로 옮긴 뒤 다시 시도하세요.\n" + "\n".join(rows)))
    return None


def install_request_handlers(engine: Any, registration: Any) -> Any:
    """Public read-only preflight + explicit normal workflow-view transition.

    Direct Delete/Clear/Reset requests remain guarded. The transition request
    is the editor's existing New/Close view action after its save/discard UI;
    it releases the loaded view, never deletes a saved workflow or media file.
    """
    install_reentrant_barrier(engine)
    from dataclasses import dataclass, field, fields
    from griptape_nodes.retained_mode.events.base_events import (
        RequestPayload, ResultPayloadSuccess, ResultPayloadFailure)
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    from griptape_nodes.retained_mode.request_handlers import handles

    payload_names = ("HMBCheckNodeDeletionRequest", "HMBCheckNodeDeletionResultSuccess",
                     "HMBCheckNodeDeletionResultFailure", "HMBPrepareWorkflowTransitionRequest",
                     "HMBDeleteCheckedNodeRequest", "HMBDeleteCheckedNodeResultSuccess",
                     "HMBDeleteCheckedNodeResultFailure")
    for name in payload_names:
        registered = PayloadRegistry.get_type(name)
        if registered is not None and globals().get(name) is not registered:
            raise RuntimeError("[HMB_DELETE_GUARD_RESTART_REQUIRED] 이전 삭제 보호 payload가 Engine에 남아 있습니다. Griptape를 다시 시작하세요.")
    existing_result = globals().get("HMBCheckNodeDeletionResultSuccess")
    if existing_result is not None and not {
            "protection_ready", "protection_version", "readiness_error", "check_token"}.issubset(
                {row.name for row in fields(existing_result)}):
        raise RuntimeError("[HMB_DELETE_GUARD_RESTART_REQUIRED] 이전 삭제 보호 응답 형식이 남아 있습니다. Griptape를 다시 시작하세요.")

    # The SDK owns one handler per payload type and forbids duplicate
    # registration. Keep that handler stable over a library refresh, changing
    # only its weak lease to the current registration. During an unload gap,
    # retained HMB data can still use the engine-owned read-only preflight.
    previous = _HANDLERS.get(engine)
    if previous is not None:
        previous.owner_ref = weakref.ref(registration)
        return previous

    # Payload registry types must keep their identity across library refreshes.
    if "HMBCheckNodeDeletionRequest" not in globals():
        @PayloadRegistry.register
        @dataclass
        class HMBCheckNodeDeletionRequest(RequestPayload):
            node_names: list[str] = field(default_factory=list)

        @PayloadRegistry.register
        @dataclass
        class HMBCheckNodeDeletionResultSuccess(ResultPayloadSuccess):
            can_delete: bool = False
            blocked: dict[str, list[str]] = field(default_factory=dict)
            hmb_node_names: list[str] = field(default_factory=list)
            message: str = ""
            protection_ready: bool = False
            protection_version: int = PROTECTION_VERSION
            readiness_error: str = ""
            check_token: str = ""

        @PayloadRegistry.register
        @dataclass
        class HMBCheckNodeDeletionResultFailure(ResultPayloadFailure):
            protection_ready: bool = False
            protection_version: int = PROTECTION_VERSION
            readiness_error: str = ""

        @PayloadRegistry.register
        @dataclass
        class HMBPrepareWorkflowTransitionRequest(RequestPayload):
            pass

        @PayloadRegistry.register
        @dataclass
        class HMBDeleteCheckedNodeRequest(RequestPayload):
            node_name: str = ""
            check_token: str = ""

        @PayloadRegistry.register
        @dataclass
        class HMBDeleteCheckedNodeResultSuccess(ResultPayloadSuccess):
            node_name: str = ""

        @PayloadRegistry.register
        @dataclass
        class HMBDeleteCheckedNodeResultFailure(ResultPayloadFailure):
            node_name: str = ""

        for cls in (HMBCheckNodeDeletionRequest, HMBCheckNodeDeletionResultSuccess,
                    HMBCheckNodeDeletionResultFailure, HMBPrepareWorkflowTransitionRequest,
                    HMBDeleteCheckedNodeRequest, HMBDeleteCheckedNodeResultSuccess,
                    HMBDeleteCheckedNodeResultFailure):
            globals()[cls.__name__] = cls

    check_type = globals()["HMBCheckNodeDeletionRequest"]
    transition_type = globals()["HMBPrepareWorkflowTransitionRequest"]
    checked_type = globals()["HMBDeleteCheckedNodeRequest"]
    class Handlers:
        def __init__(self, owner_reference: Any, engine_reference: Any) -> None:
            self.owner_ref = owner_reference
            self.engine_ref = engine_reference
            self.selections: dict[str, Any] = {}
            self.selection_lock = threading.RLock()

        def _issue_selection(self, current: Any, selected: list[str], names: list[str], retained: dict[str, Any]) -> str:
            # An in-memory, short-lived identity receipt. It is never persisted
            # or accepted as authorization to bypass the final connection guard.
            if any(name not in retained for name in names):
                raise ValueError("selection contains a missing node")
            now = time.monotonic()
            token = secrets.token_urlsafe(32)
            identities = {name: (weakref.ref(retained[name]), _parent(current, retained[name]),
                                 _group_receipt(retained[name])) for name in names}
            with self.selection_lock:
                self.selections = {key: value for key, value in self.selections.items() if value["until"] > now}
                if len(self.selections) >= 64:
                    self.selections.pop(next(iter(self.selections)))
                self.selections[token] = {"until": now + 60, "nodes": identities,
                    "selected": set(selected), "consumed": set(), "inflight": set(),
                    "scopes": {name: set(_selection_scope(current, [name])) for name in selected}}
            return token

        @handles(check_type)
        def check(self, request: Any) -> Any:
            owner, current = self.owner_ref(), self.engine_ref()
            failure = globals()["HMBCheckNodeDeletionResultFailure"]
            if current is None:
                return failure(result_details="HMB 삭제 보호를 사용할 수 없습니다. 라이브러리를 새로고침하세요.")
            if (not isinstance(request.node_names, list) or len(request.node_names) > 4096
                    or any(not isinstance(name, str) or not name for name in request.node_names)):
                return failure(result_details="삭제할 노드 목록이 올바르지 않습니다.")
            try:
                retained = _retained_nodes(current)
                if ((owner is None or not owner.active)
                        and not any(_is_hmb(node) for node in retained.values())):
                    return failure(result_details="HMB 삭제 보호를 사용할 수 없습니다. 라이브러리를 새로고침하세요.")
                ready, readiness_error = protection_readiness(current)
                if not ready:
                    return failure(result_details=readiness_error, readiness_error=readiness_error)
                names = _selection_scope(current, request.node_names)
                blocked = connected_targets(current, names)
                ungrouped = _subflow_ungrouped(current, names)
                for group_name, nodes in ungrouped.items():
                    blocked[group_name] = sorted(set(blocked.get(group_name, ())) | set(nodes))
                hmb = {name for name in names if name in retained and _is_hmb(retained[name])}
                # A selected standard group owns its HMB children. Keep that
                # group visible until native deletion succeeds as well; a new
                # child connection between preflight and Delete must not leave
                # the editor optimistically missing the refused group.
                selected = set(request.node_names)
                for name in tuple(hmb):
                    owner = getattr(retained[name], "parent_group", None)
                    seen = set()
                    while owner is not None and id(owner) not in seen:
                        seen.add(id(owner))
                        owner_name = owner if isinstance(owner, str) else getattr(owner, "name", None)
                        if owner_name in selected:
                            hmb.add(owner_name)
                        owner = getattr(retained.get(owner_name), "parent_group", None)
                return globals()["HMBCheckNodeDeletionResultSuccess"](
                    can_delete=not blocked, blocked=blocked, hmb_node_names=sorted(hmb),
                    message=(("[HMB_SUBFLOW_UNGROUPED] 그룹 하위 작업에 그룹에 속하지 않은 노드가 있어 "
                              "삭제를 중단했습니다. 해당 노드를 그룹에 추가하거나 다른 작업으로 옮긴 뒤 다시 시도하세요.\n"
                              + "\n".join(f"{name} → {', '.join(nodes)}" for name, nodes in ungrouped.items()))
                             if ungrouped else message(blocked) if blocked else ""),
                    result_details="HMB deletion preflight completed.",
                    protection_ready=True,
                    check_token=self._issue_selection(current, request.node_names, names, retained) if not blocked else "")
            except Exception:
                return failure(result_details="[HMB_DELETE_CHECK_FAILED] 연결 상태 확인에 실패하여 삭제하지 않았습니다.")

        @handles(checked_type)
        async def delete_checked(self, request: Any) -> Any:
            from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest
            failure = globals()["HMBDeleteCheckedNodeResultFailure"]
            current = self.engine_ref()
            error = "[HMB_DELETE_SELECTION_CHANGED] 선택 상태가 바뀌었거나 확인이 만료됐습니다. 연결 상태를 다시 확인하세요."
            identity = None
            acquired = False
            submitted = False
            try:
                if (current is None or not isinstance(request.node_name, str) or not request.node_name
                        or not isinstance(request.check_token, str) or not 1 <= len(request.check_token) <= 128):
                    return failure(node_name=request.node_name, result_details=error)
                with self.selection_lock:
                    selection = self.selections.get(request.check_token)
                    if (selection is None or selection["until"] <= time.monotonic()
                            or request.node_name not in selection["selected"]
                            or request.node_name in selection["consumed"]
                            or request.node_name in selection["inflight"]):
                        return failure(node_name=request.node_name, result_details=error)
                    retained = _retained_nodes(current)
                    identity = selection["nodes"].get(request.node_name)
                    if (identity is None or retained.get(request.node_name) is not identity[0]()
                            or _parent(current, retained[request.node_name]) != identity[1]
                            or not _same_group(retained[request.node_name], identity[2])):
                        return failure(node_name=request.node_name, result_details=error)
                    # Groups must still own the same retained descendants. A
                    # child explicitly deleted earlier in this selection is gone.
                    scope = _selection_scope(current, [request.node_name])
                    if set(scope) != selection["scopes"][request.node_name] - selection["consumed"]:
                        return failure(node_name=request.node_name, result_details=error)
                    for name in scope:
                        recorded = selection["nodes"].get(name)
                        if (recorded is None or name in selection["consumed"]
                                or retained.get(name) is not recorded[0]()
                                or _parent(current, retained[name]) != recorded[1]
                                or not _same_group(retained[name], recorded[2])):
                            return failure(node_name=request.node_name, result_details=error)
                    selection["inflight"].add(request.node_name)
                    acquired = True
                marker = _checked_delete_identity.set((request.node_name, identity[0]))
                try:
                    # A receipt is never an automatic retry ticket, including
                    # native failure/unknown outcomes that may have side effects.
                    with self.selection_lock:
                        selection["consumed"].add(request.node_name)
                    submitted = True
                    result = await current.ahandle_request(DeleteNodeRequest(node_name=request.node_name))
                finally:
                    _checked_delete_identity.reset(marker)
                if not result.succeeded():
                    return failure(node_name=request.node_name, result_details=result.result_details)
                return globals()["HMBDeleteCheckedNodeResultSuccess"](
                    node_name=request.node_name, result_details="Checked node deletion completed.")
            except Exception:
                return failure(node_name=request.node_name, result_details=(
                    "[HMB_DELETE_OUTCOME_UNKNOWN] 삭제 결과를 확인하지 못했습니다. 같은 요청을 반복하지 말고 현재 노드 상태를 다시 확인하세요."
                    if submitted else "[HMB_DELETE_CHECK_FAILED] 선택 상태를 확인하지 못해 삭제를 중단했습니다."))
            finally:
                if acquired:
                    with self.selection_lock:
                        selected = self.selections.get(getattr(request, "check_token", ""))
                        if selected is not None:
                            selected["inflight"].discard(getattr(request, "node_name", ""))

        @handles(transition_type)
        async def transition(self, request: Any) -> Any:
            from griptape_nodes.retained_mode.events.object_events import (
                ClearAllObjectStateRequest, ClearAllObjectStateResultFailure)
            owner, current = self.owner_ref(), self.engine_ref()
            if current is None:
                return ClearAllObjectStateResultFailure(result_details="HMB 워크플로 전환을 사용할 수 없습니다.")
            try:
                ready, readiness_error = protection_readiness(current)
                retained = _retained_nodes(current)
                if not ready:
                    return ClearAllObjectStateResultFailure(result_details=readiness_error)
                if ((owner is None or not owner.active)
                        and not any(_is_hmb(node) for node in retained.values())):
                    return ClearAllObjectStateResultFailure(result_details="HMB 워크플로 전환을 사용할 수 없습니다.")
            except Exception:
                return ClearAllObjectStateResultFailure(result_details="[HMB_DELETE_CHECK_FAILED] 워크플로 전환 상태를 확인하지 못했습니다.")
            token = _teardown_engine.set(id(current))
            try:
                return await current.ahandle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))
            finally:
                _teardown_engine.reset(token)

    handler = Handlers(weakref.ref(registration), weakref.ref(engine))
    engine.event_manager.register_request_handlers(handler)
    _HANDLERS[engine] = handler
    return handler
