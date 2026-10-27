"""Local, durable and reversible connection management for every HMB node.

Only official retained connection/metadata requests mutate the graph. A short
transaction holds node callbacks so disconnecting never becomes a destructive
source-clear operation. Durable per-relation fences stop automatic rebinding.
No provider, renderer, media decoder, file probe or account operation is used.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
import threading
from typing import Any
from uuid import UUID, uuid4
import weakref

LIBRARY = "HMB_GP_Production"
IDENTITY = "hmb_connection_identity_v1"
STATE = "hmb_connection_management_v1"
FENCES = "hmb_connection_fences_v1"
_INTERNAL = ContextVar("hmb_connection_management_internal", default=False)
_LOCK = threading.RLock()
_HANDLERS = globals().get("_HANDLERS", weakref.WeakKeyDictionary())


def _metadata(node: Any) -> dict:
    value = getattr(node, "metadata", None)
    return value if isinstance(value, dict) else {}


def _id(node: Any) -> str:
    value = _metadata(node).get(IDENTITY)
    try:
        return str(UUID(value)) if isinstance(value, str) else ""
    except ValueError:
        return ""


def _state(node: Any) -> dict:
    value = _metadata(node).get(STATE)
    return value if isinstance(value, dict) and value.get("version") == 1 else {}


def is_detached(node: Any) -> bool:
    return _state(node).get("detached") is True


def _kind(node: Any) -> str:
    from _hmb_shot_routing import _subscription_for
    sub = _subscription_for(node)
    return sub.kind if sub is not None else str(_metadata(node).get("node_type") or type(node).__name__)


def _fences(node: Any) -> tuple[dict, ...]:
    raw = _metadata(node).get(FENCES)
    return tuple(value for value in raw if isinstance(value, dict)) if isinstance(raw, list) else ()


def target_has_suspended_role(node: Any, source_kind: str = "") -> bool:
    identity = _id(node)
    return is_detached(node) or any(
        row.get("target_id") == identity and (not source_kind or row.get("source_kind") == source_kind)
        for row in _fences(node))


def relationship_suspended(source: Any, target: Any, *, source_parameter: str = "", target_parameter: str = "") -> bool:
    if _INTERNAL.get():
        return False
    if is_detached(source) or is_detached(target):
        return True
    identity = _id(target)
    if not identity:
        return False
    for row in _fences(target):
        if row.get("target_id") != identity:
            continue
        port = row.get("target_parameter_name")
        if target_parameter and port:
            if port == target_parameter:
                return True  # Do not route around the original source lease.
            continue
        if row.get("source_id") == _id(source) or row.get("source_kind") == _kind(source):
            return True
    return False


def transaction_active() -> bool:
    return _INTERNAL.get()


@contextmanager
def execution_reservation():
    """Serialize short execution reservations with connection changes.

    Acquire before a node's own execution lock; release before any await,
    provider call or media work. This does not bypass connection fences.
    """
    with _LOCK:
        yield


def _inventory(engine: Any) -> tuple[dict[str, Any], dict[str, str]]:
    from _hmb_deletion_guard import _retained_nodes, _parent
    nodes = _retained_nodes(engine)
    return nodes, {name: _parent(engine, node) for name, node in nodes.items()}


def _context(engine: Any) -> tuple[str, str]:
    manager = engine.context_manager
    if not manager.has_current_workflow() or not manager.has_current_flow():
        raise ValueError("현재 워크플로와 flow를 먼저 여세요.")
    return manager.get_current_workflow_name(), manager.get_current_flow().name


def _busy(node: Any) -> bool:
    state = getattr(node, "state", None)
    if (bool(getattr(node, "lock", False)) or bool(getattr(node, "_hmb_node_deleted", False))
            or str(getattr(state, "value", state)).casefold() == "resolving"
            or str(getattr(state, "name", "")).casefold() == "resolving"):
        return True
    if any(getattr(node, key, False) is True for key in (
            "_busy", "_hmb_run_in_progress", "_hmb_execution_pending", "_hmb_process_running",
            "_broker_action_running", "_generation_refresh_running")):
        return True
    if getattr(node, "_hmb_active_operation", None) is not None or getattr(node, "_hmb_pending_operation_id", ""):
        return True
    # Web rerenders run in an isolated facade while the retained Generator can
    # remain RESOLVED. Its owner event/claim still protects the live sources.
    generation_active = getattr(node, "_generation_run_active", None)
    if (callable(getattr(generation_active, "is_set", None)) and generation_active.is_set()
            or getattr(node, "_hmb_web_rerender_active_claim", None) is not None):
        return True
    locks = getattr(node, "_hmb_shot_execution_locks", {})
    locks = list(locks.values()) if isinstance(locks, dict) else []
    locks.append(getattr(node, "_hmb_process_lock", None))
    if any(callable(getattr(lock, "locked", None)) and lock.locked() for lock in locks):
        return True
    if bool(getattr(node, "_hmb_shot_workers", {})):
        return True
    callback = getattr(node, "_hmb_web_rerender_busy", None)
    if callable(callback) and callback() is True:
        return True
    for key in ("_worker", "_web_upload_worker"):
        worker = getattr(node, key, None)
        if callable(getattr(worker, "is_alive", None)) and worker.is_alive():
            return True
    for key in ("_hmb_draft_finalize_future", "_hmb_draft_final_status_future"):
        future = getattr(node, key, None)
        if callable(getattr(future, "done", None)) and not future.done():
            return True
    return getattr(getattr(node, "_hmb_my_box_controller_instance", None), "_busy", False) is True


def _wire_rows(engine: Any, node: Any) -> list[dict]:
    from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
    result = engine.handle_request(ListConnectionsForNodeRequest(node_name=node.name, include_internal=True, broadcast_result=False))
    if not result.succeeded():
        raise ValueError("선 연결 상태를 확인하지 못했습니다.")
    retained_edges = tuple(engine.flow_manager.get_connections().connections.values())
    rows = {}
    for incoming, edges in ((True, result.incoming_connections), (False, result.outgoing_connections)):
        for edge in edges:
            value = {"source_node_name": str(edge.source_node_name) if incoming else node.name,
                     "target_node_name": node.name if incoming else str(edge.target_node_name),
                     "source_parameter_name": str(edge.source_parameter_name),
                     "target_parameter_name": str(edge.target_parameter_name)}
            # Public Incoming/OutgoingConnection DTOs omit the internal flag.
            # Preserve it from the current retained edge, without mutating it.
            value["is_node_group_internal"] = any(
                getattr(current, "is_node_group_internal", False)
                for current in retained_edges
                if current.source_node.name == value["source_node_name"]
                and current.target_node.name == value["target_node_name"]
                and current.source_parameter.name == value["source_parameter_name"]
                and current.target_parameter.name == value["target_parameter_name"])
            rows[tuple(value.values())] = value
    return list(rows.values())


def _shots(source: Any, target: Any) -> list[dict]:
    from _hmb_shot_routing import _subscription_for, _manager_shot_subscriptions, _is_shot_manager
    sub = _subscription_for(target)
    if sub is None:
        return []
    rows = _manager_shot_subscriptions(target, sub.kind) if _is_shot_manager(target) else (sub,)
    return [dict(channel_uuid=row.channel_uuid, shot_uuid=row.shot_uuid, number=row.shot_number, name=row.shot_name)
            for row in rows if row.enabled and row.channel_uuid and row.shot_uuid]


def _relations(engine: Any, node: Any, nodes: dict, parents: dict) -> list[dict]:
    from _hmb_deletion_guard import _remote_pairs, _remote_catalog, _remote_document
    from _hmb_shot_routing import _subscription_for
    flow = parents[node.name]
    scope = {name: value for name, value in nodes.items() if parents[name] == flow}
    authorities = {}
    for value in scope.values():
        sub = _subscription_for(value)
        if sub is not None and sub.kind == "image_asset" and sub.enabled:
            catalog = _remote_catalog(sub, _remote_document(value, "HMB_IMAGE_ASSET_STATE"))
            authorities.setdefault(sub.channel_uuid, []).append((value, catalog))
    result = [dict(kind="wire", **row) for row in _wire_rows(engine, node)]
    for source, target in sorted(_remote_pairs(scope, parents)):
        if node.name in (source, target):
            result.append(dict(kind="remote", source_node_name=source, target_node_name=target,
                               source_parameter_name="", target_parameter_name="",
                               shots=_shots(nodes[source], nodes[target])))
    for row in result:
        row["peer_name"] = row["target_node_name"] if row["source_node_name"] == node.name else row["source_node_name"]
        row.setdefault("shots", _shots(nodes.get(row["source_node_name"]), nodes.get(row["target_node_name"])))
        channels = {shot.get("channel_uuid") for shot in row["shots"]}
        if len(channels) == 1:
            candidates = authorities.get(next(iter(channels)), [])
            if len(candidates) == 1:
                publisher, catalog = candidates[0]
                row["authority"] = dict(node_name=publisher.name, node_id=_id(publisher),
                                        publisher_instance_uuid=catalog.get("publisher_instance_uuid", ""))
        source, target = nodes.get(row["source_node_name"]), nodes.get(row["target_node_name"])
        if _kind(source) == "seedance" and _kind(target) == "color_lut":
            from _hmb_deletion_guard import _remote_completed_source
            origin = _remote_completed_source(source)
            if origin:
                row["origin"] = {key: origin[key] for key in ("channel_uuid", "shot_uuid", "source_node_instance_id",
                    "task_id", "generation_id", "result_revision", "path")}
        if _kind(source) == "image_asset" and _metadata(target).get("node_type") == "HMBImageBash":
            from _hmb_deletion_guard import _remote_document
            context = _remote_document(target, "image_bash_context")
            if context.get("workspace_id"):
                row["workspace_id"] = context["workspace_id"]
    return result


def _endpoint(nodes: dict, parents: dict, identity: str, flow: str) -> Any:
    matches = [node for name, node in nodes.items() if _id(node) == identity]
    if len(matches) != 1 or parents[matches[0].name] != flow or bool(getattr(matches[0], "_hmb_node_deleted", False)):
        raise ValueError("원본 연결 상대가 없거나 복제·다른 flow로 변경되었습니다. 기존 결과는 유지됩니다.")
    return matches[0]


def _record_key(row: dict) -> tuple:
    return tuple(row.get(key, "") for key in ("owner_id", "kind", "source_id", "target_id",
                 "source_parameter_name", "target_parameter_name"))


def _missing_records(node: Any, nodes: dict, parents: dict, flow: str) -> tuple[list[dict], str]:
    records = list(_fences(node)) + list(_state(node).get("recipe", {}).get("relations", []))
    unique = {_record_key(row): row for row in records if isinstance(row, dict)}
    missing, invalid = [], ""
    for row in unique.values():
        absent = False
        for identity in {row.get("owner_id"), row.get("source_id"), row.get("target_id")}:
            if not identity:
                invalid = "연결 기록의 원본 식별자를 확인하지 못했습니다."
                break
            matches = [value for value in nodes.values() if _id(value) == identity]
            if len(matches) > 1 or matches and parents[matches[0].name] != flow:
                invalid = "복제된 식별자 또는 다른 flow의 상대는 삭제된 연결로 정리할 수 없습니다."
                break
            absent |= not matches
        else:
            if absent:
                missing.append(row)
    return missing, invalid


def _restore_metadata(engine: Any, node: Any, old: dict) -> None:
    # Native metadata is merge-only. Broadcast explicit invalid values first,
    # so a stale editor cannot re-save a failed transaction's new fence keys.
    removed = set(_metadata(node)) - set(old)
    neutral = {IDENTITY: "", STATE: {}, FENCES: []}
    _persist(engine, node, {**old, **{key: deepcopy(neutral.get(key)) for key in removed}})


def _forget_missing(engine: Any, node: Any) -> dict:
    nodes, parents = _inventory(engine)
    context = _context(engine)
    missing, invalid = _missing_records(node, nodes, parents, context[1])
    if invalid or not missing:
        raise ValueError(invalid or "삭제된 상대의 연결 기록이 없습니다. 살아 있는 원본 기록은 정리하지 않습니다.")
    keys = {_record_key(row) for row in missing}
    affected = {name: value for name, value in nodes.items() if parents[name] == context[1] and (
        value is node or any(_record_key(row) in keys for row in _fences(value))
        or any(_record_key(row) in keys for row in _state(value).get("recipe", {}).get("relations", [])))}
    if any(_busy(value) for value in affected.values()):
        raise ValueError("연결된 툴의 실행을 마치고 편집 잠금을 해제하세요.")
    old_metadata = {name: deepcopy(value.metadata) for name, value in affected.items()}
    def verify():
        if _context(engine) != context or any(engine.node_manager.get_node_by_name(name) is not value for name, value in affected.items()):
            raise ValueError("연결 기록 정리 중 현재 워크플로 또는 노드가 바뀌었습니다.")
    try:
        with _hold_callbacks(list(affected.values()), engine):
            for value in affected.values():
                verify()
                metadata = {FENCES: [row for row in _fences(value) if _record_key(row) not in keys]}
                state = _state(value)
                if state.get("detached") is True:
                    recipe = deepcopy(state.get("recipe", {}))
                    recipe["relations"] = [row for row in recipe.get("relations", []) if _record_key(row) not in keys]
                    metadata[STATE] = ({**state, "recipe": recipe} if recipe["relations"] else {"version": 1, "detached": False})
                _persist(engine, value, metadata)
                verify()
    except Exception:
        verify()
        with _hold_callbacks(list(affected.values()), engine):
            for name, value in affected.items():
                _restore_metadata(engine, value, old_metadata[name])
        raise
    # Deliberately no reconcile, source hydration, file access or execution.
    return describe(engine, node.name)


def _held_membership_is_live(node: Any, expected: set, row: dict) -> bool:
    """Validate held intent against the current exact publisher, not saved UI."""
    if not (is_detached(node) or target_has_suspended_role(node)) or not expected:
        return False
    if getattr(node, "_hmb_manual_rebind", {}).get("required"):
        return False
    from _hmb_shot_routing import _same_flow_nodes, _subscription_for, _is_shot_manager
    from _hmb_deletion_guard import _remote_catalog, _remote_document
    if not _is_shot_manager(node):
        return False
    flow, nodes = _same_flow_nodes(node)
    if not flow or len({channel for channel, _shot in expected}) != 1:
        return False
    channel = next(iter(expected))[0]
    sources = [value for value in nodes if (sub := _subscription_for(value)) is not None
               and sub.enabled and sub.kind == "image_asset" and sub.channel_uuid == channel]
    if len(sources) != 1:
        return False
    source = sources[0]
    catalog = _remote_catalog(_subscription_for(source), _remote_document(source, "HMB_IMAGE_ASSET_STATE"))
    proof = row.get("authority", {})
    if (not proof.get("node_id") or _id(source) != proof["node_id"]
            or proof.get("publisher_instance_uuid") != catalog.get("publisher_instance_uuid")):
        return False
    actual = {(channel, value.get("shot_uuid")) for value in catalog.get("shots", []) if isinstance(value, dict)}
    return expected <= actual


def _validate_shots(row: dict, source: Any, target: Any) -> None:
    if row.get("origin"):
        from _hmb_deletion_guard import _remote_completed_source
        current = _remote_completed_source(source)
        if any(current.get(key) != value for key, value in row["origin"].items()):
            raise ValueError("원본 완료 Task 또는 결과 origin이 변경되었습니다.")
    if row.get("workspace_id"):
        from _hmb_deletion_guard import _remote_document
        state = _remote_document(source, "HMB_IMAGE_ASSET_STATE")
        workspace = state.get("image_bash_workspace", {})
        context = _remote_document(target, "image_bash_context")
        if workspace.get("workspace_id") != row["workspace_id"] or context.get("workspace_id") != row["workspace_id"]:
            raise ValueError("원본 Image Bash 작업 공간이 변경되었습니다.")
    if row.get("kind") != "remote":
        return
    from _hmb_shot_routing import _subscription_for, _manager_shot_subscriptions, _is_shot_manager
    from _hmb_deletion_guard import _remote_catalog, _remote_document
    expected = {(shot.get("channel_uuid"), shot.get("shot_uuid")) for shot in row.get("shots", [])
                if isinstance(shot, dict) and shot.get("channel_uuid") and shot.get("shot_uuid")}
    if not expected:
        return
    for node in (source, target):
        sub = _subscription_for(node)
        if sub is None or not sub.enabled:
            # Completed Generator -> LUT follows the accepted result origin,
            # independently of that Generator's current Only/page selector.
            if node is source and row.get("target_kind") == "color_lut" and row.get("source_kind") == "seedance":
                continue
            if _held_membership_is_live(node, expected, row):
                continue
            raise ValueError("원래 샷 바인딩이 해제되거나 변경되었습니다.")
        if sub.kind in {"image_asset", "video_picker"}:
            parameter = "HMB_IMAGE_ASSET_STATE" if sub.kind == "image_asset" else "HMB_PICKER_STATE"
            document = _remote_document(node, parameter)
            catalog = _remote_catalog(sub, document)
            declared = catalog.get("shots")
            if sub.kind == "video_picker" and not document.get("channel_uuid"):
                declared = [{"shot_uuid": item.get("workspace_uuid")} for item in document.get("picker_shots", [])]
            if isinstance(declared, list):
                actual = {(sub.channel_uuid, item.get("shot_uuid")) for item in declared if isinstance(item, dict)}
                if not expected <= actual:
                    raise ValueError("원본 목록에서 샷이 삭제·변경되어 다시 연결할 수 없습니다.")
        else:
            declared = _manager_shot_subscriptions(node, sub.kind) if _is_shot_manager(node) else (sub,)
            actual = {(item.channel_uuid, item.shot_uuid) for item in declared if item.enabled}
            if not expected <= actual:
                if _held_membership_is_live(node, expected, row):
                    continue
                raise ValueError("원래 샷 UUID가 현재 바인딩과 다릅니다.")


def describe(engine: Any, node_name: str) -> dict:
    nodes, parents = _inventory(engine)
    context = _context(engine)
    node = nodes.get(node_name)
    if node is None or _metadata(node).get("library") != LIBRARY or parents[node_name] != context[1]:
        raise ValueError("현재 flow에 등록된 HMB 툴을 선택하세요.")
    state = _state(node)
    detached = is_detached(node)
    rows = deepcopy(state.get("recipe", {}).get("relations", [])) if detached else _relations(engine, node, nodes, parents)
    if not isinstance(rows, list):
        raise ValueError("보존된 연결 복구 정보가 올바르지 않습니다.")
    reason = ""
    missing, missing_reason = _missing_records(node, nodes, parents, context[1])
    displayed = {_record_key(row) for row in rows}
    for row in missing:
        if _record_key(row) not in displayed:
            row = deepcopy(row)
            row["peer_name"] = row["target_node_name"] if row["source_node_name"] == node.name else row["source_node_name"]
            row.setdefault("shots", [])
            rows.append(row)
    if detached:
        for row in rows:
            try:
                source = _endpoint(nodes, parents, row["source_id"], context[1])
                target = _endpoint(nodes, parents, row["target_id"], context[1])
                row.update(source_node_name=source.name, target_node_name=target.name,
                           peer_name=target.name if source is node else source.name)
            except (KeyError, ValueError) as exc:
                reason = str(exc)
                break
    peers = {node_name}
    for row in rows:
        peers.update((row.get("source_node_name"), row.get("target_node_name")))
    if not reason and any(name not in nodes or parents[name] != context[1] for name in peers):
        reason = "연결 상대가 없거나 다른 flow에 있습니다."
    elif not reason and any(_busy(nodes[name]) for name in peers):
        reason = "연결된 툴의 실행을 마치고 편집 잠금을 해제하세요."
    elif not reason and any(_id(nodes[name]) and sum(_id(value) == _id(nodes[name]) for value in nodes.values()) != 1 for name in peers):
        reason = "복제된 노드 식별자가 있습니다. 원본 연결을 확인하세요."
    if detached and not reason:
        try:
            recipe = state.get("recipe", {})
            if recipe.get("flow_name") != context[1]:
                raise ValueError("원래 flow에서 다시 연결하세요.")
            for row in rows:
                source = _endpoint(nodes, parents, row["source_id"], context[1])
                target = _endpoint(nodes, parents, row["target_id"], context[1])
                if any(value is not node and is_detached(value) for value in (source, target)):
                    raise ValueError("연결 상대가 별도로 해제되어 있습니다. 상대의 연결 상태를 먼저 복구하세요.")
                _validate_shots(row, source, target)
        except (KeyError, ValueError) as exc:
            reason = str(exc)
    token = hashlib.sha256(json.dumps({
        "context": context, "node": (node.name, id(node), _id(node)), "state": state,
        "relations": rows, "peers": [(name, id(nodes.get(name)), _id(nodes[name]) if name in nodes else "")
                                          for name in sorted(name for name in peers if isinstance(name, str))],
    }, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    affected_missing = {name: value for name, value in nodes.items() if any(_id(value) in
        {row.get("owner_id"), row.get("source_id"), row.get("target_id")} for row in missing)}
    forget_reason = missing_reason or ("연결된 툴의 실행을 마치고 편집 잠금을 해제하세요."
        if _busy(node) or any(_busy(value) for value in affected_missing.values()) else "")
    return dict(node_name=node.name, detached=detached, state_token=token,
                can_disconnect=bool(rows) and not detached and not reason,
                can_reconnect=bool(rows) and detached and not reason,
                can_forget_missing=bool(missing) and not forget_reason,
                missing_count=len(missing), forget_missing_reason=forget_reason or (
                    f"삭제된 상대의 연결 기록 {len(missing)}개를 정리할 수 있습니다." if missing else "삭제된 상대의 연결 기록이 없습니다."),
                connections=rows, details=reason or ("연결 해제됨 · 샷과 결과 보존" if detached else "현재 연결 상태"))


def _persist(engine: Any, node: Any, values: dict) -> None:
    from griptape_nodes.retained_mode.events.node_events import SetNodeMetadataRequest
    result = engine.handle_request(SetNodeMetadataRequest(node_name=node.name, metadata=values, broadcast_result=True))
    if not result.succeeded() or any(_metadata(node).get(key) != value for key, value in values.items()):
        raise ValueError("연결 관리 상태를 저장하지 못했습니다.")


@contextmanager
def _hold_callbacks(nodes: list[Any], engine: Any):
    # Supported native request handlers always invoke these callbacks, including
    # initial_setup=True. Hold exact instances only for this synchronous command.
    names = ("before_incoming_connection", "after_incoming_connection", "before_outgoing_connection",
             "after_outgoing_connection", "before_incoming_connection_removed", "after_incoming_connection_removed",
             "before_outgoing_connection_removed", "after_outgoing_connection_removed", "remove_parameter_value",
             "make_node_unresolved", "kill_parameter_children")
    saved = []
    sentinel = object()
    token = _INTERNAL.set(True)
    try:
        for node in nodes:
            for name in names:
                if callable(getattr(node, name, None)):
                    previous = vars(node).get(name, sentinel)
                    saved.append((node, name, previous))
                    original = getattr(node, name)
                    setattr(node, name, lambda *a, _original=original, **k: None if _INTERNAL.get() else _original(*a, **k))
        connections = engine.flow_manager.get_connections()
        previous_unresolve = vars(connections).get("unresolve_future_nodes", sentinel)
        original_unresolve = connections.unresolve_future_nodes
        connections.unresolve_future_nodes = lambda *a, **k: None if _INTERNAL.get() else original_unresolve(*a, **k)
        yield
    finally:
        if "connections" in locals():
            if previous_unresolve is sentinel:
                vars(connections).pop("unresolve_future_nodes", None)
            else:
                connections.unresolve_future_nodes = previous_unresolve
        for node, name, previous in reversed(saved):
            if previous is sentinel:
                vars(node).pop(name, None)
            else:
                setattr(node, name, previous)
        _INTERNAL.reset(token)


def _native(engine: Any, operation: str, row: dict) -> None:
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
    values = {key: row[key] for key in ("source_node_name", "source_parameter_name", "target_node_name", "target_parameter_name")}
    request = (CreateConnectionRequest(**values, initial_setup=True,
                    is_node_group_internal=row.get("is_node_group_internal", False), broadcast_result=True)
               if operation == "create" else DeleteConnectionRequest(**values, broadcast_result=True))
    result = engine.handle_request(request)
    if not result.succeeded():
        raise ValueError(str(result.result_details))


def manage(engine: Any, node_name: str, operation: str, expected_state_token: str) -> dict:
    if operation not in {"disconnect", "reconnect", "forget_missing"} or not isinstance(expected_state_token, str) or not expected_state_token:
        raise ValueError("연결 관리 요청이 올바르지 않습니다.")
    with _LOCK:
        before = describe(engine, node_name)
        if before["state_token"] != expected_state_token:
            raise ValueError("연결 상태가 변경되었습니다. 다시 조회한 뒤 시도하세요.")
        if not before["can_" + operation]:
            raise ValueError((before.get("forget_missing_reason") if operation == "forget_missing" else before["details"])
                             or "이 연결 상태에서 실행할 수 없습니다.")
        if operation == "forget_missing":
            return _forget_missing(engine, engine.node_manager.get_node_by_name(node_name))
        nodes, parents = _inventory(engine)
        node, context = nodes[node_name], _context(engine)
        relations = deepcopy(before["connections"])
        participants = {node.name: node}
        for row in relations:
            participants.update({name: nodes[name] for name in (row["source_node_name"], row["target_node_name"])})
        original_metadata = {name: deepcopy(value.metadata) for name, value in participants.items()}
        changed = []
        def verify():
            if _context(engine) != context or any(engine.node_manager.get_node_by_name(name) is not value for name, value in participants.items()):
                raise ValueError("연결 관리 중 워크플로 또는 노드가 변경되었습니다.")
        def persist(value, metadata):
            verify()
            _persist(engine, value, metadata)
            verify()
        def native(action, row):
            verify()
            _native(engine, action, row)
            verify()
        try:
            with _hold_callbacks(list(participants.values()), engine):
                for value in participants.values():
                    if not _id(value):
                        persist(value, {IDENTITY: str(uuid4())})
                owner_id = _id(node)
                if operation == "disconnect":
                    for row in relations:
                        source, target = nodes[row["source_node_name"]], nodes[row["target_node_name"]]
                        row.update(source_id=_id(source), target_id=_id(target),
                                   source_kind=_kind(source), target_kind=_kind(target), owner_id=owner_id)
                        authority = row.get("authority")
                        if isinstance(authority, dict) and authority.get("node_name") in participants:
                            authority["node_id"] = _id(participants[authority["node_name"]])
                    recipe = {"flow_name": context[1], "relations": relations}
                    for value in participants.values():
                        fences = list(_fences(value))
                        fences.extend(deepcopy(row) for row in relations if value.name in (row["source_node_name"], row["target_node_name"]))
                        persist(value, {FENCES: fences})
                    persist(node, {STATE: {"version": 1, "detached": True, "recipe": recipe}})
                    for row in relations:
                        if row["kind"] == "wire":
                            changed.append(row)
                            native("delete", row)
                else:
                    # Re-resolve persistent leases, never a same-name substitute.
                    for row in relations:
                        source = _endpoint(nodes, parents, row["source_id"], context[1])
                        target = _endpoint(nodes, parents, row["target_id"], context[1])
                        _validate_shots(row, source, target)
                        row.update(source_node_name=source.name, target_node_name=target.name)
                        if _busy(source) or _busy(target):
                            raise ValueError("연결 상대가 실행 중이거나 잠겨 있습니다.")
                        if any(value is not node and is_detached(value) for value in (source, target)):
                            raise ValueError("연결 상대가 별도로 해제되어 있습니다.")
                        if row["kind"] != "wire":
                            continue
                        if (source.get_parameter_by_name(row["source_parameter_name"]) is None
                                or target.get_parameter_by_name(row["target_parameter_name"]) is None):
                            raise ValueError("원래 연결 포트가 없습니다.")
                        incoming = [edge for edge in _wire_rows(engine, target)
                                    if edge["target_node_name"] == target.name and edge["target_parameter_name"] == row["target_parameter_name"]]
                        exact = lambda edge: all(edge[key] == row[key] for key in (
                            "source_node_name", "source_parameter_name", "target_node_name", "target_parameter_name"))
                        if any(not exact(edge) for edge in incoming):
                            raise ValueError("대상 입력을 다른 연결이 사용하고 있습니다. 기존 연결은 유지됩니다.")
                        existing = engine.flow_manager.get_connections().get_existing_connection_for_restricted_scenario(
                            source, source.get_parameter_by_name(row["source_parameter_name"]), is_source=True)
                        if existing is not None and (
                                existing.target_node is not target or existing.target_parameter.name != row["target_parameter_name"]):
                            raise ValueError("원본 control 출력을 다른 연결이 사용하고 있습니다.")
                    for row in relations:
                        if row["kind"] == "wire" and not any(all(edge[key] == row[key] for key in (
                                "source_node_name", "source_parameter_name", "target_node_name", "target_parameter_name"))
                                for edge in _wire_rows(engine, nodes[row["target_node_name"]])):
                            changed.append(row)
                            native("create", row)
                    for value in participants.values():
                        persist(value, {FENCES: [row for row in _fences(value) if row.get("owner_id") != owner_id]})
                    persist(node, {STATE: {"version": 1, "detached": False}})
                verify()
        except Exception:
            verify()  # Never replay old names into a replacement workflow.
            with _hold_callbacks(list(participants.values()), engine):
                errors = []
                for row in reversed(changed):
                    try:
                        exists = any(all(edge[key] == row[key] for key in (
                            "source_node_name", "source_parameter_name", "target_node_name", "target_parameter_name"))
                            for edge in _wire_rows(engine, nodes[row["target_node_name"]]))
                        if (operation == "disconnect" and not exists) or (operation == "reconnect" and exists):
                            native("create" if operation == "disconnect" else "delete", row)
                    except Exception as exc:
                        errors.append(str(exc))
                for name, value in participants.items():
                    old = original_metadata[name]
                    try:
                        verify()
                        _restore_metadata(engine, value, old)
                        verify()
                    except Exception as exc:
                        errors.append(str(exc))
                if errors:
                    raise RuntimeError("연결 관리 복구를 완료하지 못했습니다. 추가 작업을 멈추고 연결 상태를 확인하세요.")
            raise
        if operation == "reconnect":
            from _hmb_shot_routing import schedule_post_hydration_reconcile
            schedule_post_hydration_reconcile(node)
        return describe(engine, node_name)


def guard_request(engine: Any, request: Any) -> Any:
    if _INTERNAL.get():
        return None
    kind = type(request).__name__
    if kind == "CreateConnectionRequest":
        source_name, target_name = request.source_node_name, request.target_node_name
        context = engine.context_manager
        if context.has_current_node():
            current_name = context.get_current_node().name
            source_name, target_name = source_name or current_name, target_name or current_name
        if not source_name or not target_name:
            return None
        try:
            source = engine.node_manager.get_node_by_name(source_name)
            target = engine.node_manager.get_node_by_name(target_name)
        except KeyError:
            return None
        if relationship_suspended(source, target, source_parameter=request.source_parameter_name, target_parameter=request.target_parameter_name):
            from griptape_nodes.retained_mode.events.connection_events import CreateConnectionResultFailure
            return CreateConnectionResultFailure(result_details="[HMB_CONNECTION_DETACHED] 연결 관리에서 원래 연결을 다시 연결하세요. 샷과 결과는 유지됩니다.")
    elif kind == "ResolveNodeRequest":
        try:
            node = engine.node_manager.get_node_by_name(request.node_name)
        except KeyError:
            return None
        if is_detached(node) or target_has_suspended_role(node):
            from griptape_nodes.retained_mode.events.execution_events import ResolveNodeResultFailure
            error = ValueError("[HMB_CONNECTION_DETACHED] 연결이 해제되어 있습니다. 연결 관리에서 다시 연결한 뒤 실행하세요.")
            return ResolveNodeResultFailure(validation_exceptions=[error], result_details=str(error))
    return None


def install_request_handlers(engine: Any, registration: Any) -> Any:
    from dataclasses import dataclass, field
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayloadSuccess, ResultPayloadFailure
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    from griptape_nodes.retained_mode.request_handlers import handles
    previous = _HANDLERS.get(engine)
    if previous is not None:
        previous.owner_ref = weakref.ref(registration)
        return previous
    if "HMBGetNodeConnectionsRequest" not in globals():
        @PayloadRegistry.register
        @dataclass
        class HMBGetNodeConnectionsRequest(RequestPayload):
            node_name: str = ""

        @PayloadRegistry.register
        @dataclass
        class HMBManageNodeConnectionsRequest(RequestPayload):
            node_name: str = ""
            operation: str = ""
            expected_state_token: str = ""

        @PayloadRegistry.register
        @dataclass
        class HMBNodeConnectionsResultSuccess(ResultPayloadSuccess):
            node_name: str = ""
            detached: bool = False
            state_token: str = ""
            can_disconnect: bool = False
            can_reconnect: bool = False
            can_forget_missing: bool = False
            missing_count: int = 0
            forget_missing_reason: str = ""
            connections: list[dict] = field(default_factory=list)
            details: str = ""

        @PayloadRegistry.register
        @dataclass
        class HMBNodeConnectionsResultFailure(ResultPayloadFailure):
            pass
        for cls in (HMBGetNodeConnectionsRequest, HMBManageNodeConnectionsRequest,
                    HMBNodeConnectionsResultSuccess, HMBNodeConnectionsResultFailure):
            globals()[cls.__name__] = cls

    class Handlers:
        def __init__(self, owner_ref, engine_ref):
            self.owner_ref, self.engine_ref = owner_ref, engine_ref

        def reply(self, request, mutation=False):
            owner, current = self.owner_ref(), self.engine_ref()
            try:
                if owner is None or not owner.active or current is None:
                    raise ValueError("HMB 라이브러리를 새로고침한 뒤 다시 시도하세요.")
                if not isinstance(request.node_name, str) or not request.node_name or len(request.node_name) > 512:
                    raise ValueError("HMB 툴 이름이 올바르지 않습니다.")
                value = (manage(current, request.node_name, request.operation, request.expected_state_token)
                         if mutation else describe(current, request.node_name))
                return globals()["HMBNodeConnectionsResultSuccess"](**value, result_details="HMB local connection management completed.")
            except Exception as exc:
                return globals()["HMBNodeConnectionsResultFailure"](result_details=str(exc))

        @handles(globals()["HMBGetNodeConnectionsRequest"])
        def get(self, request):
            return self.reply(request)

        @handles(globals()["HMBManageNodeConnectionsRequest"])
        def change(self, request):
            return self.reply(request, True)

    handler = Handlers(weakref.ref(registration), weakref.ref(engine))
    engine.event_manager.register_request_handlers(handler)
    _HANDLERS[engine] = handler
    return handler
