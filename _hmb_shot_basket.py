"""Retained-mode launcher and shot selection for HMB 로동마트."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
from threading import RLock, Thread
from time import monotonic
from typing import Any
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary, ref


_LIBRARY = "HMB_GP_Production"
_MARKER = "hmb_shot_basket_v1"
_NODES = {
    "sound": ("HMBSoundLibrary", "HMB Sound Library", 0, -760),
    "image": ("HMBImageAssetLibrary", "HMB ImageAsset Library", 0, 0),
    "video": ("HMBVideoPickerLibrary", "HMB VideoPicker", 0, 1250),
    "prompt": ("HMBPromptLibrary", "HMBPrompt", 1800, 0),
    "agent": ("HMBAgentLibrary", "HMB Agent", 3600, 0),
    "generator": ("HMBSeedanceGeneration", "HMB Seedance Generation", 4900, 0),
}
_KINDS = {"image", "video", "sound"}
_PAGE_SIZE = 40
_BATCH_LIMIT = 64
_STAGED_VIDEO_LIMIT = 24
_ENGINES: WeakKeyDictionary = WeakKeyDictionary()
_HANDLERS: WeakKeyDictionary = WeakKeyDictionary()
_REGISTRY_LOCK = RLock()
_LOG = logging.getLogger(__name__)


class BasketError(ValueError):
    """An error message safe to send back to the editor."""


@dataclass
class _Session:
    lock: Any = field(default_factory=RLock)
    discovery_lock: Any = field(default_factory=RLock)
    discovery_busy: bool = False
    discovery_at: float = 0
    projects: list[dict] = field(default_factory=list)
    prewarm_library: Any = None
    prewarm_pending: bool = False
    prewarmed_types: set[str] = field(default_factory=set)
    cgt_preparation: Any = None
    cgt_scope: tuple = ()
    receipts: dict[tuple, tuple[list[dict], dict]] = field(default_factory=dict)
    staged_videos: dict[tuple, dict[str, dict]] = field(default_factory=dict)
    browsing: set[tuple] = field(default_factory=set)


def _session(engine: Any) -> _Session:
    with _REGISTRY_LOCK:
        return _ENGINES.setdefault(engine, _Session())


def _cgt_scope(engine):
    context = engine.context_manager
    return (context.get_current_workflow_name() if context.has_current_workflow() else "",
            getattr(context.get_current_flow(), "name", "") if context.has_current_flow() else "")


def prepared_cgt_reader(engine, project_id):
    """Capture on the host loop; consume only for display, never commit."""
    session = _session(engine)
    if session.cgt_scope != _cgt_scope(engine) or session.cgt_preparation is None:
        return None
    return session.cgt_preparation.reader(project_id)


def _prepare_cgt(engine, session, project_id=""):
    from _hmb_cgt import CatalogPreparation
    scope = _cgt_scope(engine)
    if session.cgt_preparation is None or session.cgt_scope != scope:
        if session.cgt_preparation is not None:
            session.cgt_preparation.cancel()
        session.cgt_preparation = CatalogPreparation()
        session.cgt_scope = scope
    session.cgt_preparation.prepare(project_id)


def _text(value: Any, limit: int = 256) -> str:
    if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 for char in value):
        raise BasketError("로동마트 요청 형식을 확인하세요.")
    return value.strip()


def _uuid(value: Any) -> str:
    try:
        return str(UUID(value)) if isinstance(value, str) else ""
    except ValueError:
        return ""


def _project_options(session: _Session) -> tuple[list[dict], bool]:
    def discover() -> None:
        from HMBImageAssetLibrary import DEFAULT_PROJECTS_ROOT, _discover_project_catalog

        try:
            projects = _discover_project_catalog(DEFAULT_PROJECTS_ROOT)["projects"]
        except Exception:
            _LOG.debug("HMB shot basket project discovery failed", exc_info=True)
            projects = []
        with session.discovery_lock:
            session.projects = projects
            session.discovery_at = monotonic()
            session.discovery_busy = False

    with session.discovery_lock:
        expiry = 60 if session.projects else 10
        if not session.discovery_busy and (not session.discovery_at or monotonic() - session.discovery_at > expiry):
            session.discovery_busy = True
            Thread(target=discover, daemon=True, name="HMB-Basket-Projects").start()
        return list(session.projects), session.discovery_busy


def _active_flow(engine: Any, expected: str, *, exact: bool = False) -> Any:
    context = engine.context_manager
    flow = context.get_current_flow() if context.has_current_flow() else None
    actual = getattr(flow, "name", "")
    if (expected or exact) and actual != expected:
        raise BasketError("작업공간이 바뀌었습니다. 로동마트를 다시 여세요.")
    if flow is not None and engine.flow_manager.get_flow_by_name(actual) is not flow:
        raise BasketError("현재 작업공간의 연결을 확인할 수 없습니다.")
    return flow


def _prewarm_library(engine: Any, session: _Session) -> None:
    """Resolve lazy classes on the SDK loop without constructing nodes."""
    from griptape_nodes.node_library.library_registry import LibraryRegistry

    loop = engine.event_manager.event_loop
    if loop is None or not loop.is_running() or session.prewarm_pending:
        return
    try:
        library = LibraryRegistry.get_library(_LIBRARY)
    except Exception:
        return
    if session.prewarm_library is not library:
        session.prewarm_library = library
        session.prewarmed_types.clear()
    registered = library.get_registered_nodes()
    prioritized = [node_type for node_type, *_ in _NODES.values() if node_type in registered]
    remaining = iter(node_type for node_type in dict.fromkeys([*prioritized, *registered])
                     if node_type not in session.prewarmed_types)
    session.prewarm_pending = True
    engine_ref = ref(engine)

    def resolve_next() -> None:
        current = engine_ref()
        with session.lock:
            try:
                if current is None or LibraryRegistry.get_library(_LIBRARY) is not library:
                    session.prewarm_pending = False
                    return
                node_type = next(remaining, None)
                if node_type is None:
                    session.prewarm_pending = False
                    return
                try:
                    library.get_node_class(node_type)
                except Exception:
                    _LOG.debug("HMB shot basket class prewarm failed for %s", node_type, exc_info=True)
                session.prewarmed_types.add(node_type)
                loop.call_later(0.05, resolve_next)
            except Exception:
                session.prewarm_pending = False
                _LOG.debug("HMB shot basket class prewarm was interrupted", exc_info=True)

    try:
        loop.call_soon_threadsafe(resolve_next)
    except RuntimeError:
        session.prewarm_pending = False


def _nodes(engine: Any, flow: Any) -> dict[str, Any]:
    nodes = getattr(flow, "nodes", None)
    runtime = getattr(engine, "current_workflow_or_none", None)
    if callable(runtime):
        parents = runtime().nodes.name_to_parent_flow_name
    else:
        parents = getattr(engine.node_manager, "_name_to_parent_flow_name", None)
    lookup = engine.object_manager.attempt_get_object_by_name
    if not all(isinstance(value, dict) for value in (nodes, parents)):
        raise BasketError("이 편집기의 작업공간 구조를 확인할 수 없습니다.")
    if ({name for name, parent in parents.items() if parent == flow.name} != set(nodes)
            or any(lookup(name) is not node for name, node in nodes.items())):
        raise BasketError("작업공간을 준비 중입니다. 잠시 뒤 다시 시도하세요.")
    return nodes


def _owned_nodes(engine: Any, flow: Any) -> dict[str, Any]:
    nodes = _nodes(engine, flow)
    if not nodes:
        return {}
    kinds = {}
    ownership = set()
    for node in nodes.values():
        metadata = getattr(node, "metadata", {}) or {}
        marker = metadata.get(_MARKER)
        if not isinstance(marker, dict):
            continue
        kind = marker.get("kind")
        owner = _uuid(marker.get("workspace_id"))
        if (not owner or not isinstance(kind, str) or kind not in _NODES or kind in kinds
                or metadata.get("library") != _LIBRARY or metadata.get("node_type") != _NODES[kind][0]):
            raise BasketError("로동마트 노드의 소유 관계를 확인할 수 없습니다.")
        ownership.add(owner)
        kinds[kind] = node
    if len(ownership) > 1 or (kinds and kinds.keys() != _NODES.keys()):
        raise BasketError("로동마트 노드 구성이 변경되었습니다. 현재 노드를 확인하세요.")
    return kinds


def _ensure_empty_flow(engine: Any, flow: Any) -> Any:
    from _hmb_library_bootstrap import _empty_maps, _registered_unsaved_workflow
    from griptape_nodes.retained_mode.events.context_events import (
        EnsureWorkflowAndFlowRequest, EnsureWorkflowAndFlowResultSuccess,
    )

    context = engine.context_manager
    workflow_name = context.get_current_workflow_name() if context.has_current_workflow() else ""
    if workflow_name and not _registered_unsaved_workflow(workflow_name):
        raise BasketError("새 빈 작업공간에서 로동마트를 시작하세요.")
    if flow is not None:
        parents = getattr(engine.flow_manager, "_name_to_parent_name", {})
        if (not isinstance(parents, dict) or flow.name not in parents or parents[flow.name] is not None
                or flow.name in parents.values() or _nodes(engine, flow)):
            raise BasketError("새 빈 작업공간에서 로동마트를 시작하세요.")
        return flow
    current_runtime = getattr(engine, "current_workflow_or_none", None)
    no_workflow_runtime = not workflow_name and callable(current_runtime) and current_runtime() is None
    if not no_workflow_runtime and _empty_maps(engine) is None:
        raise BasketError("새 빈 작업공간을 먼저 여세요.")
    result = engine.handle_request(EnsureWorkflowAndFlowRequest(display_name="HMB 로동마트"))
    if (not isinstance(result, EnsureWorkflowAndFlowResultSuccess)
            or not result.created_flow or not _registered_unsaved_workflow(result.workflow_name)
            or (workflow_name and result.workflow_name != workflow_name)):
        raise BasketError("새 작업공간을 준비할 수 없습니다.")
    return _active_flow(engine, result.flow_name, exact=True)


def _rollback(engine: Any, flow: Any, created: dict[str, Any]) -> None:
    """Only remove objects whose exact retained identity belongs to this attempt."""
    from _hmb_connection_management import describe, manage
    from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest

    if _active_flow(engine, flow.name, exact=True) is not flow:
        return
    nodes = _nodes(engine, flow)
    if any(created.get(name) is not node for name, node in nodes.items()):
        raise BasketError("생성 중 다른 노드가 추가되었습니다. 현재 작업공간을 확인하세요.")
    for node in reversed(tuple(created.values())):
        info = describe(engine, node.name)
        if info.get("can_disconnect"):
            manage(engine, node.name, "disconnect", info["state_token"])
    for node in reversed(tuple(created.values())):
        if _nodes(engine, flow).get(node.name) is not node:
            continue
        with engine.context_manager.flow(flow=flow):
            result = engine.handle_request(DeleteNodeRequest(node_name=node.name, broadcast_result=True))
        if not result.succeeded():
            raise BasketError("만든 노드 일부를 정리하지 못했습니다. 작업공간을 확인하세요.")


def _select_project(node: Any, project: dict, projects: list[dict], shot_name: str) -> None:
    from HMBImageAssetLibrary import UI_EDIT_REVISION_KEY, WIDGET_STATE_PARAMETER, _json_text

    state = node._current_state()
    state.update(projects=projects, project_root=project["path"], project_id="", project_uid="",
                 project_cache_uid="", folder_signature="", selected_folder_path="",
                 expanded_folders=["$root"], selected_main_type="", selected_sub_type="",
                 selected_source_view="project")
    if shot_name:
        routing = state["shot_routing"]
        first = routing["shots"][0]
        first.update(name=shot_name, name_is_custom=True, revision=first["revision"] + 1)
        routing["generation"] += 1
    state[UI_EDIT_REVISION_KEY] += 1
    node.set_parameter_value(WIDGET_STATE_PARAMETER, _json_text(state))


def _create(engine: Any, flow: Any, project: dict | None, projects: list[dict], shot_name: str,
            *, cgt_setup: bool = False) -> tuple[Any, dict]:
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest

    for node_type, *_ in _NODES.values():
        library = LibraryRegistry.get_library_for_node_type(node_type, _LIBRARY)
        if library.get_library_data().name != _LIBRARY:
            raise BasketError("HMB 라이브러리의 등록 상태를 확인하세요.")
    flow = _ensure_empty_flow(engine, flow)
    workspace_id = str(uuid4())
    marker = {"workspace_id": workspace_id, "project_id": project["project_id"] if project else "",
              "shot_name": shot_name}
    if project is None:
        marker["reserved"] = True
    if cgt_setup:
        marker["cgt_required"] = True
    created = {}
    kinds = {}
    try:
        # Load the native Agent first so a missing Standard dependency does
        # not require creating and rolling back the rest of the workspace.
        for kind in ("agent", "image", "video", "sound", "prompt", "generator"):
            node_type, name, x, y = _NODES[kind]
            if (_active_flow(engine, flow.name, exact=True) is not flow
                    or _nodes(engine, flow) != created):
                raise BasketError("작업공간이 변경되어 노드 생성을 멈췄습니다.")
            with engine.context_manager.flow(flow=flow):
                result = engine.handle_request(CreateNodeRequest(
                    node_type=node_type, specific_library_name=_LIBRARY, node_name=name,
                    override_parent_flow_name=flow.name, create_error_proxy_on_failure=False,
                    set_as_new_context=False, broadcast_result=True,
                    metadata={"position": {"x": x, "y": y}, _MARKER: {**marker, "kind": kind}},
                ))
            if not result.succeeded():
                raise BasketError("필요한 HMB 노드를 만들 수 없습니다.")
            node = _nodes(engine, flow)[result.node_name]
            if node.metadata.get(_MARKER, {}).get("workspace_id") != workspace_id:
                raise BasketError("새 HMB 노드의 소유 관계를 확인할 수 없습니다.")
            created[node.name] = node
            kinds[kind] = node
        if project is not None:
            _select_project(kinds["image"], project, projects, shot_name)
    except Exception:
        try:
            _rollback(engine, flow, created)
        except Exception as cleanup:
            _LOG.debug("HMB shot basket rollback failed", exc_info=True)
            raise BasketError("노드 생성이 중단되었고 일부 노드가 남았을 수 있습니다. 작업공간을 확인하세요.") from cleanup
        raise
    return flow, kinds


def _bind_prepared(engine: Any, flow: Any, kinds: dict, project: dict, projects: list[dict],
                   shot_name: str, cgt_setup: bool) -> None:
    from HMBImageAssetLibrary import UI_EDIT_REVISION_KEY

    nodes = _nodes(engine, flow)
    parents = getattr(engine.flow_manager, "_name_to_parent_name", {})
    image = kinds["image"]
    state = image._current_state()
    markers = {kind: node.metadata[_MARKER] for kind, node in kinds.items()}
    if (len(nodes) != len(kinds) or not isinstance(parents, dict) or flow.name not in parents
            or parents[flow.name] is not None or flow.name in parents.values()
            or any(marker.get("reserved") is not True or marker.get("project_id")
                   or marker.get("shot_name") for marker in markers.values())
            or any(not _node_ready(node) or node.metadata.get("position") != {"x": _NODES[kind][2], "y": _NODES[kind][3]}
                   for kind, node in kinds.items())
            or state.get(UI_EDIT_REVISION_KEY) or state.get("project_root") or state.get("project_id")):
        raise BasketError("준비한 작업공간이 변경되었습니다. 현재 노드와 프로젝트를 확인하세요.")
    for kind, node in kinds.items():
        node.metadata[_MARKER] = {
            "workspace_id": markers[kind]["workspace_id"], "kind": kind,
            "project_id": project["project_id"], "shot_name": shot_name,
            **({"cgt_required": True} if cgt_setup else {}),
        }
    try:
        _select_project(image, project, projects, shot_name)
    except Exception:
        # A setter may fail after committing the requested project. Keep its
        # ownership in that case so retry cannot apply a different project.
        selected_root = image._current_state().get("project_root", "").replace("\\", "/").rstrip("/")
        if selected_root != project["path"].replace("\\", "/").rstrip("/"):
            for kind, node in kinds.items():
                node.metadata[_MARKER] = markers[kind]
        raise


def _shot_state(kinds: dict, shot_uuid: str = "") -> tuple[dict, dict | None]:
    state = kinds["image"]._current_state()
    routing = state.get("shot_routing") or {}
    target = shot_uuid or routing.get("active_shot_uuid")
    shot = next((row for row in routing.get("shots", []) if row.get("shot_uuid") == target), None)
    if shot_uuid and shot is None:
        raise BasketError("현재 작업의 샷을 다시 선택하세요.")
    return state, shot


def _node_ready(node: Any) -> bool:
    from _hmb_connection_management import is_detached

    return not (getattr(node, "lock", False) or getattr(node, "_hmb_node_deleted", False)
                or str(getattr(node, "state", "")).casefold() == "resolving" or is_detached(node))


def _basket_shots(state: dict, marker: dict) -> list[dict]:
    routing = state["shot_routing"]
    if marker.get("cgt_required") is not True:
        return routing["shots"]

    from _hmb_shot_routing import hierarchy_project_key, validate_shot_hierarchy_routing

    if not state.get("project_id") or state["project_id"] != marker["project_id"]:
        return []
    try:
        binding = validate_shot_hierarchy_routing(state.get("shot_hierarchy"), routing)
    except ValueError:
        return []
    if binding.get("version") != 2 or binding["project_identity"] != hierarchy_project_key(state):
        return []
    slots = {row["gp_shot_uuid"] for row in binding["members"] if row["origin"] == "cgt"}
    return [row for row in routing["shots"] if row["shot_uuid"] in slots]


def _status(flow: Any, kinds: dict, projects: list[dict], discovering: bool) -> dict:
    result = {
        "ok": True, "flow_name": getattr(flow, "name", ""), "project_id": "",
        "shot_uuid": "", "shots": [], "nodes": {kind: node.name for kind, node in kinds.items()},
        "projects": [{key: row[key] for key in ("project_id", "name")} for row in projects],
    }
    marker = kinds["image"].metadata[_MARKER] if kinds else {}
    if not kinds or marker.get("reserved") is True:
        result["status"] = "discovering" if discovering and not projects else "empty" if projects else "unavailable"
        if kinds:
            result["prepared"] = True
        elif flow is not None and flow.nodes:
            result["status"] = "occupied"
        return result
    state, shot = _shot_state(kinds)
    target = marker["project_id"]
    shots = _basket_shots(state, marker)
    if marker.get("cgt_required") is True:
        result.update(cgt_required=True, cgt_bound=bool(shots))
        if shot not in shots:
            shot = next(iter(shots), None)
    result["project_id"] = state.get("project_id") or target
    result["shot_uuid"] = shot["shot_uuid"] if shot else ""
    result["shots"] = [{key: row[key] for key in ("shot_uuid", "name", "number")} for row in shots]
    result["status"] = "ready"
    # CGT assignment uses project identity, not the media catalog. A matching
    # project can open its own-task picker while thumbnails/files keep loading.
    assignment_ready = (result.get("cgt_required") is True and not result.get("cgt_bound")
                        and state.get("project_id") == target and not state.get("error"))
    if state.get("scan_busy") and not assignment_ready:
        result["status"] = "preparing"
    elif state.get("error") or state.get("project_id") != target:
        result.update(status="unavailable", message="프로젝트의 이미지 라이브러리 준비 상태를 확인하세요.")
    if assignment_ready and state.get("scan_busy"):
        result["media_preparing"] = True
    return result


def _picker_shot(state: dict, shot_uuid: str, channel_uuid: str) -> dict | None:
    if state.get("channel_uuid") != channel_uuid:
        return None
    return next((row for row in state.get("picker_shots", []) if row.get("bound_shot_uuid") == shot_uuid), None)


def _sound_selected(state: dict, shot_uuid: str, channel_uuid: str) -> dict[str, list[dict]]:
    result = {}
    for track in state["tracks"]:
        if track["shot_uuid"] == shot_uuid and track["channel_uuid"] == channel_uuid:
            result.setdefault(track["source_uid"], []).append(track)
    return result


def _video_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(value)).replace("\\", "/") if value else ""


def _image_selectable(row: dict) -> bool:
    return bool(row.get("registered") or row.get("source_kind") == "user")


def _catalog(kinds: dict, image: dict, shot: dict, kind: str, query: str, offset: int,
             staged: dict[str, dict], browsing: bool) -> dict:
    shot_uuid = shot["shot_uuid"]
    channel_uuid = image["shot_routing"]["channel_uuid"]
    staged_results = {}
    if kind == "image":
        rows = [row for row in image["assets"] if _image_selectable(row)]
        selected = set(shot["selected_source_uids"])
    elif kind == "video":
        node = kinds[kind]
        with node._hmb_catalog_state_commit():
            state = node._picker_state()
            target = _picker_shot(state, shot_uuid, channel_uuid)
            if target is None:
                return {"status": "preparing", "items": [], "next_offset": None}
            owned = set(target["video_asset_uids"])
            rows = [row for row in state["videos"] if row.get("video_uid") in owned]
            selected = set(target["selected_video_uids"])
            registered = {_video_key(row.get("import_source_path", "")): row["video_uid"] for row in rows}
            jobs = {job["source_key"]: job["status"] for job in node._hmb_video_import_jobs.values()
                    if job["picker_shot_uuid"] == target["workspace_uuid"]}
        for uid, source in staged.items():
            actual_uid = registered.get(source["key"])
            if actual_uid:
                staged_results[uid] = {"status": "applied" if actual_uid in selected else "registered",
                                       "source_uid": actual_uid, "selected": actual_uid in selected}
            elif source.get("submitted"):
                status = "pending" if jobs.get(source["key"]) not in {None, "failed"} else "failed"
                staged_results[uid] = {"status": status, "selected": False}
        rows = [{"source_uid": uid, "name": row["name"], "staged": True}
                for uid, row in staged.items() if row["key"] not in registered] + rows
    else:
        node = kinds[kind]
        with node._lock:
            state = node._state_sound
            if state["channel_uuid"] != channel_uuid or state["busy"] and not state["assets"]:
                return {"status": "preparing", "items": [], "next_offset": None}
            rows = list(state["assets"])
            selected = set(_sound_selected(state, shot_uuid, channel_uuid))
    items = []
    matched = 0
    result = {"status": "ready", "items": items, "next_offset": None,
              "browse_pending": browsing, "staged_results": staged_results}
    for row in rows:
        uid = row.get("source_uid") or row.get("video_uid")
        name = row.get("image_name") or row.get("name") or row.get("video_name") or row.get("label") or uid
        if (not isinstance(uid, str) or not uid or len(uid) > 256
                or not isinstance(name, str) or query not in name.casefold()):
            continue
        matched += 1
        if matched <= offset:
            continue
        if len(items) == _PAGE_SIZE:
            result["next_offset"] = offset + _PAGE_SIZE
            break
        items.append({"kind": kind, "source_uid": uid, "name": name[:256],
                      "selected": uid in selected, **({"staged": True} if row.get("staged") else {})})
    return result


def _item_result(item: dict, status: str, message: str = "", *, accepted_pending: bool = False) -> dict:
    result = {**item, "status": status, "ok": status in {"applied", "unchanged"}}
    if message:
        result["message"] = message
    if accepted_pending:
        result["accepted_pending"] = True
    return result


def _selections(items: list[dict], current: list[str], available: set[str], limit: int) -> tuple[list[str], list[dict]]:
    desired = list(current)
    results = []
    # Release existing slots before accepting new selections in the same batch.
    for item in sorted(items, key=lambda row: row["selected"]):
        uid, selected = item["source_uid"], item["selected"]
        if uid not in available:
            results.append(_item_result(item, "failed", "현재 샷의 소스 목록을 다시 확인하세요."))
        elif selected == (uid in desired):
            results.append(_item_result(item, "unchanged"))
        elif not selected:
            desired.remove(uid)
            results.append(_item_result(item, "applied"))
        elif len(desired) >= limit:
            results.append(_item_result(item, "failed", "샷에서 선택할 수 있는 소스 수를 초과했습니다."))
        else:
            desired.append(uid)
            results.append(_item_result(item, "applied"))
    return desired, results


def _apply_images(node: Any, state: dict, shot: dict, items: list[dict]) -> list[dict]:
    from HMBImageAssetLibrary import (
        IMAGE_ASSET_EDIT_SCHEMA, MAX_SELECTED_IMAGES, MAX_SHOT_IMAGES, UI_EDIT_REVISION_KEY,
        WIDGET_RUNTIME_LEASE_KEY, WIDGET_STATE_PARAMETER, _json_text,
    )

    routing = state["shot_routing"]
    other_members = {uid for row in routing["shots"] if row is not shot for uid in row["selected_source_uids"]}
    original = list(shot["selected_source_uids"])
    global_order = [row["source_uid"] for row in sorted(state["assets"], key=lambda row: row["selection_order"])
                    if row["selected"]]
    preserved = set(global_order) - (set(original) - other_members)
    available = {row["source_uid"] for row in state["assets"] if _image_selectable(row)}
    desired, results = _selections(items, original, available, MAX_SHOT_IMAGES)
    removed = set(original) - set(desired) - other_members
    selected = [uid for uid in global_order if uid not in removed]
    new = [uid for uid in desired if uid not in selected]
    if len(selected) + len(new) > MAX_SELECTED_IMAGES:
        room = max(0, MAX_SELECTED_IMAGES - len(selected))
        rejected = set(new[room:])
        desired = [uid for uid in desired if uid not in rejected]
        new = new[:room]
        results = [_item_result(row, "failed", "이미지 라이브러리 선택 한도를 초과했습니다.")
                   if row["source_uid"] in rejected else row for row in results]
    if desired == original:
        return results
    # A global asset may be shared by several Shots. Preserve its global
    # membership until the last Shot removes it and keep existing order.
    if not preserved.issubset(set(selected) | set(new)):
        raise BasketError("다른 샷의 이미지 선택이 바뀌었습니다.")
    shot.update(selected_source_uids=desired, revision=shot["revision"] + 1,
                media_count=0, metadata_sha256="", media_sha256="")
    routing["generation"] += 1
    edit = {
        "schema": IMAGE_ASSET_EDIT_SCHEMA, "version": 1,
        UI_EDIT_REVISION_KEY: state[UI_EDIT_REVISION_KEY] + 1,
        WIDGET_RUNTIME_LEASE_KEY: state[WIDGET_RUNTIME_LEASE_KEY],
        "scan_revision": state["scan_revision"],
        "thumbnail_revision": state["thumbnail_revision"],
        "catalog_identity": {key: state[key] for key in (
            "catalog_root", "project_root", "project_uid", "project_cache_uid",
            "manifest_signature", "folder_signature", "scan_revision",
        )},
        "selected_source_uids": selected + new,
        "edits": {"shot_routing": routing},
    }
    node.set_parameter_value(WIDGET_STATE_PARAMETER, _json_text(edit))
    _, live = _shot_state({"image": node}, shot["shot_uuid"])
    if live["selected_source_uids"] != desired:
        raise BasketError("이미지 선택 반영을 확인하지 못했습니다. 목록을 다시 확인하세요.")
    return results


def _apply_videos(node: Any, shot_uuid: str, channel_uuid: str, items: list[dict]) -> list[dict]:
    from HMBVideoPickerLibrary import MAX_SELECTED_VIDEOS
    from _hmb_deletion_guard import binding_mutation

    with binding_mutation(node), node._hmb_catalog_state_commit():
        state = node._picker_state()
        target = _picker_shot(state, shot_uuid, channel_uuid)
        if target is None:
            return [_item_result(item, "busy", "VideoPicker의 샷 연결을 준비 중입니다.") for item in items]
        original = target["selected_video_uids"]
        desired, results = _selections(items, original, set(target["video_asset_uids"]), MAX_SELECTED_VIDEOS)
        if desired == original:
            return results
        target.update(selected_video_uids=desired, revision=target["revision"] + 1)
        if state.get("active_picker_shot_uuid") == target["workspace_uuid"]:
            order = {uid: index for index, uid in enumerate(desired, 1)}
            for row in state["videos"]:
                index = order.get(row.get("video_uid"), 0)
                row.update(selected=bool(index), selection_order=index, video_slot=index)
        node._write_state(state)
        written = node._picker_state()
        current = _picker_shot(written, shot_uuid, channel_uuid)
        if current is None or current["selected_video_uids"] != desired:
            raise BasketError("영상 선택 반영을 확인하지 못했습니다. 목록을 다시 확인하세요.")
        node._reconcile_shared_shot_routing()
        node._sync_outputs_from_state(written)
        return results


def _apply_sounds(node: Any, shot_uuid: str, channel_uuid: str, items: list[dict]) -> list[dict]:
    from _hmb_deletion_guard import binding_mutation

    results = []
    with binding_mutation(node), node._lock:
        state = node._state_sound
        for item in sorted(items, key=lambda row: row["selected"]):
            uid, selected = item["source_uid"], item["selected"]
            if state["channel_uuid"] != channel_uuid or state["busy"]:
                results.append(_item_result(item, "busy", "음원 준비가 끝나면 다시 적용하세요."))
                continue
            if shot_uuid not in {row["shot_uuid"] for row in state["shot_catalog"].get("shots", [])}:
                results.append(_item_result(item, "busy", "Sound Library의 샷 연결을 준비 중입니다."))
                continue
            tracks = _sound_selected(state, shot_uuid, channel_uuid).get(uid, [])
            if bool(tracks) == selected:
                results.append(_item_result(item, "unchanged"))
                continue
            if len(tracks) > 1:
                results.append(_item_result(item, "failed", "복제된 음원은 Sound Library에서 인스턴스를 선택해 해제하세요."))
                continue
            command = {"id": str(uuid4()), "action": "shot_add" if selected else "remove",
                       "source_uid": uid, "shot_uuid": shot_uuid}
            if tracks:
                command["instance_id"] = tracks[0]["instance_id"]
            try:
                node._command(command)
            except ValueError:
                results.append(_item_result(item, "failed", "음원 연결을 적용할 수 없습니다. 현재 목록을 확인하세요."))
                continue
            results.append(_item_result(item, "pending" if selected else "applied", accepted_pending=selected))
    return results


def _batch(value: Any) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= _BATCH_LIMIT:
        raise BasketError("적용할 소스를 1개 이상 선택하세요.")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise BasketError("적용할 소스의 형식을 확인하세요.")
        kind = _text(item.get("kind"))
        uid = _text(item.get("source_uid"))
        selected = item.get("selected")
        if kind not in _KINDS or not uid or type(selected) is not bool or (kind, uid) in seen:
            raise BasketError("적용할 소스 목록에 잘못된 항목 또는 중복이 있습니다.")
        seen.add((kind, uid))
        result.append({"kind": kind, "source_uid": uid, "selected": selected})
    return result


def _apply_staged_videos(node: Any, shot_uuid: str, channel_uuid: str, items: list[dict],
                         staged: dict[str, dict]) -> list[dict]:
    from HMBVideoPickerLibrary import MAX_VIDEO_IMPORT_BATCH
    from _hmb_deletion_guard import binding_mutation

    with binding_mutation(node), node._hmb_catalog_state_commit():
        state = node._picker_state()
        target = _picker_shot(state, shot_uuid, channel_uuid)
        if target is None:
            return [_item_result(item, "busy", "VideoPicker의 샷 연결을 준비 중입니다.") for item in items]
        workspace = target["workspace_uuid"]
        existing = {_video_key(row.get("import_source_path", "")): row["video_uid"]
                    for row in state["videos"] if row.get("video_uid") in target["video_asset_uids"]}
        jobs = node._hmb_video_import_jobs
        to_import = []
        results = []
        for item in items:
            uid = item["source_uid"]
            source = staged[uid]
            original_uid = existing.get(source["key"])
            job = next((row for row in jobs.values() if row["picker_shot_uuid"] == workspace
                        and row["source_key"] == source["key"]), None)
            if original_uid:
                translated = {**item, "source_uid": original_uid}
                result = _apply_videos(node, shot_uuid, channel_uuid, [translated])[0]
                if item["selected"] and result["ok"] and source.pop("submitted", False):
                    result = _item_result(item, "applied")
                results.append({**result, "source_uid": uid})
            elif not item["selected"]:
                status = "busy" if job and job["status"] != "failed" else "unchanged"
                if status == "unchanged":
                    staged.pop(uid, None)
                results.append(_item_result(item, status))
            elif job and job["status"] != "failed":
                results.append(_item_result(item, "pending"))
            elif source.pop("submitted", False):
                results.append(_item_result(item, "failed", "MP4 등록을 완료하지 못했습니다. VideoPicker에서 파일을 확인하세요."))
            elif len(to_import) >= MAX_VIDEO_IMPORT_BATCH:
                results.append(_item_result(item, "busy", "등록할 MP4 수가 많습니다. 잠시 뒤 다시 적용하세요."))
            else:
                to_import.append((item, source))
        if to_import:
            node._commit_video_import_sources(
                [{"source_path": source["path"], "label": ""} for _, source in to_import],
                captured_picker_shot_uuid=workspace, action_id=str(uuid4()), background=True)
            queued = {row["source_key"] for row in jobs.values()
                      if row["picker_shot_uuid"] == workspace and row["status"] != "failed"}
            for item, source in to_import:
                if source["key"] in queued:
                    source["submitted"] = True
                    results.append(_item_result(item, "pending", accepted_pending=True))
                else:
                    results.append(_item_result(item, "failed", "이 샷에 MP4를 더 등록할 수 없습니다."))
        return results


def _apply(kinds: dict, state: dict, shot: dict, items: list[dict], staged: dict[str, dict]) -> list[dict]:
    results = {}
    shot_uuid = shot["shot_uuid"]
    channel_uuid = state["shot_routing"]["channel_uuid"]
    for kind in ("image", "video", "sound"):
        selected = [item for item in items if item["kind"] == kind]
        if not selected:
            continue
        node = kinds[kind]
        if not _node_ready(node):
            rows = [_item_result(item, "busy", "라이브러리 잠금과 연결 상태를 확인하세요.") for item in selected]
        else:
            try:
                if kind == "image":
                    rows = _apply_images(node, state, shot, selected)
                elif kind == "video":
                    existing = [item for item in selected if item["source_uid"] not in staged]
                    pending = [item for item in selected if item["source_uid"] in staged]
                    rows = _apply_videos(node, shot_uuid, channel_uuid, existing) if existing else []
                    if pending:
                        rows.extend(_apply_staged_videos(node, shot_uuid, channel_uuid, pending, staged))
                else:
                    rows = _apply_sounds(node, shot_uuid, channel_uuid, selected)
            except Exception as exc:
                _LOG.debug("HMB shot basket %s selection failed", kind, exc_info=True)
                detail = str(exc) if isinstance(exc, BasketError) else "라이브러리 목록을 새로 확인한 뒤 다시 적용하세요."
                rows = [_item_result(item, "failed", detail) for item in selected]
        results.update({(row["kind"], row["source_uid"]): row for row in rows})
    return [results[item["kind"], item["source_uid"]] for item in items]


def _browse_video(node: Any, shot_uuid: str, channel_uuid: str, session: _Session, scope: tuple) -> None:
    from HMBVideoPickerLibrary import _choose_video_asset_files

    if not _node_ready(node):
        raise BasketError("VideoPicker 잠금과 연결 상태를 확인하세요.")
    target = _picker_shot(node._picker_state(), shot_uuid, channel_uuid)
    if target is None:
        raise BasketError("VideoPicker의 샷 연결을 준비 중입니다.")
    if scope in session.browsing:
        return
    if not node._hmb_video_browse_lock.acquire(blocking=False):
        raise BasketError("이미 MP4 파일 선택 창이 열려 있습니다.")
    session.browsing.add(scope)

    def choose() -> None:
        paths = []
        try:
            if not node._hmb_node_deleted:
                paths = _choose_video_asset_files("")
        except Exception:
            _LOG.debug("HMB shot basket MP4 picker failed", exc_info=True)
        finally:
            node._hmb_video_browse_lock.release()
        with session.lock:
            session.browsing.discard(scope)
            if not paths or node._hmb_node_deleted:
                return
            if scope not in session.staged_videos and len(session.staged_videos) >= 16:
                del session.staged_videos[next(iter(session.staged_videos))]
            staged = session.staged_videos.setdefault(scope, {})
            existing = {row["key"] for row in staged.values()}
            for path in paths[:_STAGED_VIDEO_LIMIT]:
                name = Path(path)
                key = _video_key(path)
                if len(staged) >= _STAGED_VIDEO_LIMIT:
                    break
                if name.suffix.casefold() != ".mp4" or key in existing:
                    continue
                staged[f"staged-video-{uuid4().hex}"] = {"key": key, "path": path, "name": name.stem}
                existing.add(key)

    try:
        Thread(target=choose, name="HMB-Basket-MP4-Dialog", daemon=True).start()
    except Exception:
        node._hmb_video_browse_lock.release()
        session.browsing.discard(scope)
        raise


def _handle_scoped_request(engine: Any, payload: dict) -> dict:
    bind = getattr(engine, "bind_workflow", None)
    workflow_name = _text(payload.get("workflow_name", ""), 512)
    flow_name = _text(payload.get("flow_name", ""), 512)
    if not callable(bind) or not (workflow_name or flow_name):
        return handle_workspace_request(engine, payload)
    matches = []
    for runtime in engine.open_workflows.all_open():
        if workflow_name and engine.workflow_registry.get(runtime.workflow_id).name != workflow_name:
            continue
        if flow_name and (not runtime.context.has_current_flow()
                          or runtime.context.get_current_flow().name != flow_name):
            continue
        matches.append(runtime)
    if len(matches) != 1:
        raise BasketError("현재 작업공간의 연결을 확인할 수 없습니다.")
    with bind(matches[0]):
        return handle_workspace_request(engine, payload)


def handle_workspace_request(engine: Any, request: dict) -> dict:
    """Use the active retained flow and return bounded, path-free results."""
    if not isinstance(request, dict):
        raise BasketError("로동마트 요청 형식을 확인하세요.")
    action = _text(request.get("action"))
    if action not in {"status", "prepare", "create", "catalog", "apply", "browse"}:
        raise BasketError("지원하지 않는 로동마트 요청입니다.")
    session = _session(engine)
    expected = _text(request.get("flow_name", ""), 512)
    expected_workflow = _text(request.get("workflow_name", ""), 512)
    with session.lock:
        context = engine.context_manager
        if expected_workflow and (not context.has_current_workflow()
                or context.get_current_workflow_name() != expected_workflow):
            raise BasketError("작업공간이 바뀌었습니다. 로동마트를 다시 여세요.")
        flow = _active_flow(engine, expected, exact=action != "status")
        kinds = _owned_nodes(engine, flow) if flow is not None else {}
        projects, discovering = _project_options(session) if action in {"status", "prepare", "create"} else ([], False)
        response = _status(flow, kinds, projects, discovering)
        if action == "status":
            if request.get("prewarm") is True:
                _prewarm_library(engine, session)
                project_id = _text(request.get("project_id", ""))
                if not project_id or any(row["project_id"] == project_id for row in projects):
                    _prepare_cgt(engine, session, project_id)
            return response
        if action == "prepare" or (action == "create" and response.get("prepared")):
            from _hmb_library_bootstrap import _registered_unsaved_workflow

            if flow is None or not _registered_unsaved_workflow(expected_workflow):
                raise BasketError("새 빈 작업공간에서 로동마트를 시작하세요.")
        if action == "prepare":
            if kinds:
                return response
            flow, kinds = _create(engine, flow, None, projects, "")
            return {**_status(flow, kinds, projects, discovering), "created": True, "changed": True}
        if action == "create":
            project_id = _text(request.get("project_id"))
            shot_name = _text(request.get("shot_name", ""), 64)
            cgt_setup = request.get("cgt_setup", False)
            if type(cgt_setup) is not bool or (cgt_setup and shot_name):
                raise BasketError("CGT에서 에피소드와 컷을 선택하세요.")
            if kinds and not response.get("prepared"):
                marker = kinds["image"].metadata[_MARKER]
                if (marker["project_id"] != project_id or marker.get("shot_name", "") != shot_name
                        or (marker.get("cgt_required") is True) != cgt_setup):
                    raise BasketError("이미 준비된 작업공간입니다. 새 작업은 빈 작업공간에서 시작하세요.")
                return response
            if response["status"] == "occupied":
                raise BasketError("새 빈 작업공간에서 로동마트를 시작하세요.")
            if discovering and not projects:
                return response
            project = next((row for row in projects if row["project_id"] == project_id), None)
            if project is None:
                raise BasketError("현재 프로젝트 목록에서 다시 선택하세요.")
            if response.get("prepared"):
                _bind_prepared(engine, flow, kinds, project, projects, shot_name, cgt_setup)
                return {**_status(flow, kinds, projects, False), "created": False, "changed": True, "bound": True}
            flow, kinds = _create(engine, flow, project, projects, shot_name, cgt_setup=cgt_setup)
            return {**_status(flow, kinds, projects, False), "created": True, "changed": True}
        if not kinds:
            raise BasketError("로동마트 작업공간을 먼저 준비하세요.")
        shot_uuid = _uuid(request.get("shot_uuid"))
        if not shot_uuid:
            raise BasketError("적용할 샷을 먼저 선택하세요.")
        if response["status"] != "ready":
            return {**response, "items": [], "next_offset": None}
        state, shot = _shot_state(kinds, shot_uuid)
        if shot not in _basket_shots(state, kinds["image"].metadata[_MARKER]):
            raise BasketError("ImageAsset의 샷 추가에서 CGT 컷을 연결한 뒤 소스를 담으세요.")
        response["shot_uuid"] = shot_uuid
        request_id = _text(request.get("request_id", ""), 128)
        workspace_id = kinds["image"].metadata[_MARKER]["workspace_id"]
        scope = (workspace_id, expected, shot_uuid)
        staged = session.staged_videos.get(scope, {})
        if action == "catalog":
            kind = _text(request.get("kind"))
            query = _text(request.get("query", ""), 128).casefold()
            offset = request.get("offset", 0)
            if kind not in _KINDS or type(offset) is not int or not 0 <= offset <= 20000:
                raise BasketError("소스 목록을 다시 선택하세요.")
            return {**response, **_catalog(kinds, state, shot, kind, query, offset, staged,
                                          kind == "video" and scope in session.browsing)}
        if action == "browse":
            if request.get("kind") != "video":
                raise BasketError("파일 찾기는 VideoPicker의 MP4 등록을 사용합니다.")
            _browse_video(kinds["video"], shot_uuid, state["shot_routing"]["channel_uuid"], session, scope)
            return {**response, "status": "pending", "message": "MP4를 선택한 뒤 목록에서 담고 적용하세요."}
        items = _batch(request.get("items"))
        receipt_key = (*scope, request_id)
        cached = session.receipts.get(receipt_key) if request_id else None
        settled = {}
        if cached is not None:
            if cached[0] != items:
                raise BasketError("이미 사용한 적용 요청입니다. 목록을 다시 확인하세요.")
            settled = {(row["kind"], row["source_uid"]): row for row in cached[1]["items"]
                       if row["status"] not in {"pending", "busy"}}
        outstanding = [row for row in items if (row["kind"], row["source_uid"]) not in settled]
        current = _apply(kinds, state, shot, outstanding, staged)
        settled.update({(row["kind"], row["source_uid"]): row for row in current})
        results = [settled[row["kind"], row["source_uid"]] for row in items]
        complete = all(row["ok"] for row in results)
        response.update(ok=complete, status="ready" if complete else "partial", items=results,
                        changed=any(row["status"] == "applied" for row in current),
                        accepted_pending=any(row.get("accepted_pending") for row in current))
        if request_id:
            if len(session.receipts) >= 128:
                del session.receipts[next(iter(session.receipts))]
            session.receipts[receipt_key] = (items, response)
        return response


def install_request_handlers(engine: Any, registration: Any) -> Any:
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayloadFailure, ResultPayloadSuccess
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
    from griptape_nodes.retained_mode.request_handlers import handles

    with _REGISTRY_LOCK:
        previous = _HANDLERS.get(engine)
        if previous is not None:
            previous.owner_ref = ref(registration)
            return previous
        if "HMBShotBasketRequest" not in globals():
            @PayloadRegistry.register
            @dataclass
            class HMBShotBasketRequest(RequestPayload):
                action: str = ""
                payload: dict = field(default_factory=dict)

            @PayloadRegistry.register
            @dataclass
            class HMBShotBasketResultSuccess(ResultPayloadSuccess):
                data: dict = field(default_factory=dict)

            @PayloadRegistry.register
            @dataclass
            class HMBShotBasketResultFailure(ResultPayloadFailure):
                pass

            for cls in (HMBShotBasketRequest, HMBShotBasketResultSuccess, HMBShotBasketResultFailure):
                globals()[cls.__name__] = cls

        class Handler:
            owner_ref = ref(registration)
            engine_ref = ref(engine)

            @handles(globals()["HMBShotBasketRequest"])
            def request(self, request):
                owner, current = self.owner_ref(), self.engine_ref()
                try:
                    if owner is None or not owner.active or current is None:
                        raise BasketError("HMB 라이브러리를 새로고침한 뒤 로동마트를 다시 여세요.")
                    if not isinstance(request.payload, dict):
                        raise BasketError("로동마트 요청 형식을 확인하세요.")
                    data = _handle_scoped_request(current, {**request.payload, "action": request.action})
                    return globals()["HMBShotBasketResultSuccess"](
                        data=data, result_details="HMB shot basket request completed.")
                except Exception as exc:
                    _LOG.debug("HMB shot basket request failed", exc_info=True)
                    detail = str(exc) if isinstance(exc, BasketError) else "로동마트 요청을 완료하지 못했습니다. 현재 작업공간을 확인하세요."
                    return globals()["HMBShotBasketResultFailure"](result_details=detail)

        handler = Handler()
        engine.event_manager.register_request_handlers(handler)
        _HANDLERS[engine] = handler
        return handler
