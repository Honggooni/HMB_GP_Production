"""Common pre-mutation deletion protection for current and future HMB tools.

Wire dependencies include hidden REMOTE edges. Non-wire tools may declare
``_hmb_deletion_dependencies() -> iterable[BaseNode]``; only exact retained
objects in the same flow are accepted. Merely offering a Shot in a dropdown
is not a binding. No provider, media resolution or filesystem work belongs here.
"""
from __future__ import annotations

import importlib
import weakref
from contextvars import ContextVar
from typing import Any

LIBRARY = "HMB_GP_Production"
CODE = "HMB_DELETE_CONNECTED"
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
_HANDLERS = globals().get("_HANDLERS", weakref.WeakKeyDictionary())


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


def _selection_scope(engine: Any, names: list[str]) -> list[str]:
    """Include group descendants before the editor starts a batch teardown."""
    retained = _retained_nodes(engine)
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
    return sorted(result)


def message(blocked: dict[str, list[str]]) -> str:
    rows = [f"{name} → {', '.join(peers)}" for name, peers in blocked.items()]
    return (f"[{CODE}] 연결된 HMB 툴은 삭제하거나 초기화할 수 없습니다.\n"
            + "\n".join(rows)
            + "\n선 연결과 리모트 샷 바인딩을 먼저 해제하세요. 기존 샷과 결과는 유지됩니다.")


def guard_request(engine: Any, request: Any) -> Any:
    kind = type(request).__name__
    if kind not in _DESTRUCTIVE:
        return None
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
        blocked = connected_targets(engine, _scope(engine, request))
    except Exception:
        return result_type(result_details=(
            "[HMB_DELETE_CHECK_FAILED] 연결 상태를 확인하지 못해 삭제를 중단했습니다. "
            "연결 상태를 새로고침한 뒤 다시 시도하세요. 기존 데이터는 유지됩니다."))
    return result_type(result_details=message(blocked)) if blocked else None


def install_request_handlers(engine: Any, registration: Any) -> Any:
    """Public read-only preflight + explicit normal workflow-view transition.

    Direct Delete/Clear/Reset requests remain guarded. The transition request
    is the editor's existing New/Close view action after its save/discard UI;
    it releases the loaded view, never deletes a saved workflow or media file.
    """
    from dataclasses import dataclass, field
    from griptape_nodes.retained_mode.events.base_events import (
        RequestPayload, ResultPayloadSuccess, ResultPayloadFailure)
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    from griptape_nodes.retained_mode.request_handlers import handles

    # The SDK owns one handler per payload type and forbids duplicate
    # registration. Keep that handler stable over a library refresh, changing
    # only its weak lease to the current registration. Unload leaves it inert.
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

        @PayloadRegistry.register
        @dataclass
        class HMBCheckNodeDeletionResultFailure(ResultPayloadFailure):
            pass

        @PayloadRegistry.register
        @dataclass
        class HMBPrepareWorkflowTransitionRequest(RequestPayload):
            pass

        for cls in (HMBCheckNodeDeletionRequest, HMBCheckNodeDeletionResultSuccess,
                    HMBCheckNodeDeletionResultFailure, HMBPrepareWorkflowTransitionRequest):
            globals()[cls.__name__] = cls

    check_type = globals()["HMBCheckNodeDeletionRequest"]
    transition_type = globals()["HMBPrepareWorkflowTransitionRequest"]
    class Handlers:
        def __init__(self, owner_reference: Any, engine_reference: Any) -> None:
            self.owner_ref = owner_reference
            self.engine_ref = engine_reference

        @handles(check_type)
        def check(self, request: Any) -> Any:
            owner, current = self.owner_ref(), self.engine_ref()
            failure = globals()["HMBCheckNodeDeletionResultFailure"]
            if owner is None or not owner.active or current is None:
                return failure(result_details="HMB 삭제 보호를 사용할 수 없습니다. 라이브러리를 새로고침하세요.")
            if (not isinstance(request.node_names, list) or len(request.node_names) > 4096
                    or any(not isinstance(name, str) or not name for name in request.node_names)):
                return failure(result_details="삭제할 노드 목록이 올바르지 않습니다.")
            try:
                names = _selection_scope(current, request.node_names)
                blocked = connected_targets(current, names)
                retained = _retained_nodes(current)
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
                    message=message(blocked) if blocked else "", result_details="HMB deletion preflight completed.")
            except Exception:
                return failure(result_details="[HMB_DELETE_CHECK_FAILED] 연결 상태 확인에 실패하여 삭제하지 않았습니다.")

        @handles(transition_type)
        async def transition(self, request: Any) -> Any:
            from griptape_nodes.retained_mode.events.object_events import (
                ClearAllObjectStateRequest, ClearAllObjectStateResultFailure)
            owner, current = self.owner_ref(), self.engine_ref()
            if owner is None or not owner.active or current is None:
                return ClearAllObjectStateResultFailure(result_details="HMB 워크플로 전환을 사용할 수 없습니다.")
            token = _teardown_engine.set(id(current))
            try:
                return await current.ahandle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))
            finally:
                _teardown_engine.reset(token)

    handler = Handlers(weakref.ref(registration), weakref.ref(engine))
    engine.event_manager.register_request_handlers(handler)
    _HANDLERS[engine] = handler
    return handler
