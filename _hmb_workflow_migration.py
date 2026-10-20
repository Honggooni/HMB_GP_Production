"""Consolidate fully hydrated HMB editors without executing their work.

Only the ordinary, exact same-channel Shot topology is contracted. Unsupported
connections and conflicting documents leave the graph intact. Every mutation
has a durable SDK-encoded recovery snapshot before it starts.
"""
from __future__ import annotations

import asyncio
import contextvars
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import threading
import sys
from typing import Any
from uuid import uuid4
import weakref

SCHEMA = "hmb-workflow-migration"
METADATA_KEY = "hmb_workflow_migration"
_LIBRARY = "HMB_GP_Production"
_KINDS = {"HMBPromptLibrary": "prompt", "HMBAgentLibrary": "agent",
    "HMBFinishLookLibrary": "finish_look"}
_EXPORT_HOOKS = {"prompt": "_hmb_prompt_merge_snapshot", "agent": "_hmb_export_agent_authoring_state",
    "finish_look": "_hmb_finish_merge_snapshot"}
_LOCK = threading.RLock()
_PENDING: Any = weakref.WeakKeyDictionary()
_INFLIGHT: Any = weakref.WeakKeyDictionary()
_RESULTS: Any = weakref.WeakKeyDictionary()
_SCHEDULE_GENERATIONS: Any = weakref.WeakKeyDictionary()
_BLOCKED: Any = weakref.WeakKeyDictionary()
_MANUAL_REBINDS: Any = weakref.WeakKeyDictionary()
_INTERNAL = contextvars.ContextVar("hmb_workflow_migration_internal", default=False)


class MigrationConflict(RuntimeError):
    """The existing graph cannot be contracted without guessing or losing work."""


def _require(value: Any, message: str) -> None:
    if not value:
        raise MigrationConflict(message)


def _encoded(value: Any) -> Any:
    from griptape_nodes.serialization.values import encode_value
    return encode_value(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_encoded(value), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _kind(node: Any) -> str | None:
    metadata = getattr(node, "metadata", {})
    if not isinstance(metadata, dict) or metadata.get("library") != _LIBRARY:
        return None
    return _KINDS.get(metadata.get("node_type"))


def mark_flow_migration_pending(engine: Any, flow_name: str) -> None:
    if isinstance(flow_name, str) and flow_name:
        with _LOCK:
            _PENDING.setdefault(engine, set()).add(flow_name)


def flow_migration_pending(engine: Any, flow_name: str) -> bool:
    with _LOCK:
        return flow_name in _PENDING.get(engine, ()) or flow_name in _INFLIGHT.get(engine, ())


def flow_migration_blocked(engine: Any, flow_name: str) -> dict[str, Any] | None:
    with _LOCK:
        return deepcopy(_BLOCKED.get(engine, {}).get(flow_name))


def _node_manual_rebind_required(node: Any) -> bool:
    value = getattr(node, "_hmb_manual_rebind", None)
    pending = getattr(node, "_hmb_manual_rebind_pending", None)
    return bool(isinstance(value, dict) and value.get("required")) or bool(callable(pending) and pending())


def _finish_manual_rebind(engine: Any, flow: Any, editors: list[Any]) -> None:
    """Retire transaction-only export filters after the graph verifies."""
    _require(not any(_node_manual_rebind_required(node) for node in editors),
        "Confirm every original editor before completing its recovery")
    for node in editors:
        clear = getattr(node, "_hmb_clear_manual_rebind", None)
        manual = getattr(node, "_hmb_manual_rebind", None)
        if callable(clear) and isinstance(manual, dict) and manual.get("status") == "confirmed":
            clear("verified_workflow_consolidation")
    with _LOCK:
        _MANUAL_REBINDS.get(engine, {}).pop(flow.name, None)


def _manual_rebind_context(node: Any, expected_source_digest: str) -> tuple[Any, Any, dict, dict]:
    from griptape_nodes.retained_mode.engine import current_engine
    engine = current_engine()
    _require(engine is not None, "Manual rebind requires the current workflow engine")
    name = str(getattr(node, "name", ""))
    _require(engine.node_manager.get_node_by_name(name) is node,
        "The original editor was deleted or replaced; reopen the saved workflow")
    flow_name = engine.node_manager.get_node_parent_flow_by_name(name)
    flow = _registered_flow(engine, flow_name)
    _require(not flow_migration_pending(engine, flow_name),
        "Wait for the workflow connection check to finish before reconnecting a Shot")
    _require(not engine.flow_manager.check_for_existing_running_flow(),
        "Stop the running workflow before reconnecting an existing Shot")
    with _LOCK:
        transaction = _MANUAL_REBINDS.get(engine, {}).get(flow_name)
        entry = transaction.get("nodes", {}).get(name) if isinstance(transaction, dict) else None
        _require(isinstance(entry, dict) and entry["node"]() is node
            and entry["digest"] == expected_source_digest and not entry.get("confirmed"),
            "The manual rebind request is stale; use the current editor notice")
    backup = Path(transaction["backup_path"])
    _require(backup.is_file() and hashlib.sha256(backup.read_bytes()).hexdigest() == transaction["backup_sha256"],
        "The original recovery snapshot is unavailable; no Shot was rebound")
    return engine, flow, transaction, entry


def validate_manual_rebind(node: Any, expected_source_digest: str, *, channel_uuid: str, shot_uuid: str) -> dict[str, Any]:
    """Validate one explicit human choice; never guess from a name or number."""
    engine, flow, transaction, entry = _manual_rebind_context(node, expected_source_digest)
    publisher = transaction["publisher"]()
    _require(publisher is not None and flow.nodes.get(publisher.name) is publisher,
        "The ImageAsset publisher was replaced; reopen the existing workflow")
    candidates = [item for item in flow.nodes.values() if isinstance(getattr(item, "metadata", None), dict)
        and item.metadata.get("library") == _LIBRARY
        and item.metadata.get("node_type") == "HMBImageAssetLibrary"]
    _require(candidates == [publisher], "Choose one ImageAsset publisher before reconnecting Shots")
    catalog = publisher._hmb_shot_routing_catalog()
    _require(catalog.get("publisher_instance_uuid") == transaction["publisher_instance_uuid"]
        and catalog.get("channel_uuid") == channel_uuid
        and sum(row.get("shot_uuid") == shot_uuid for row in catalog.get("shots", [])) == 1,
        "The selected Shot no longer belongs to the original ImageAsset publisher")
    with _LOCK:
        _require(not any(other is not entry and other.get("confirmed")
            and other["kind"] == entry["kind"]
            and other.get("target") == (channel_uuid, shot_uuid)
            for other in transaction["nodes"].values()),
            "Another original editor was already assigned to this Shot; choose its own Shot")
    return {"ok": True, "backup_path": transaction["backup_path"]}


def confirm_manual_rebind(node: Any, expected_source_digest: str) -> dict[str, Any]:
    """Resume consolidation only after every original editor was confirmed."""
    engine, flow, transaction, entry = _manual_rebind_context(node, expected_source_digest)
    exported = getattr(node, _EXPORT_HOOKS[entry["kind"]])()
    subscription = _subscription(node, exported)
    _require(subscription.get("enabled") is True, "Select the exact target Shot before confirming")
    channel, shot = subscription.get("channel_uuid"), subscription.get("shot_uuid")
    validate_manual_rebind(node, expected_source_digest, channel_uuid=channel, shot_uuid=shot)
    with _LOCK:
        _require(not entry.get("confirmed"), "This original editor was already confirmed")
        _require(not any(other is not entry and other.get("confirmed")
            and other["kind"] == entry["kind"] and other.get("target") == (channel, shot)
            for other in transaction["nodes"].values()),
            "Another original editor was already assigned to this Shot")
        entry.update(confirmed=True, target=(channel, shot))
        remaining = [name for name, item in transaction["nodes"].items() if not item.get("confirmed")]
    retry_scheduled = False
    if not remaining:
        # Confirmation is committed above. A closing host event loop can reject
        # call_soon_threadsafe after the scheduler's liveness check; that must
        # not make an editor roll back a target already recorded in the ledger.
        # Keep the original graph and its blocked execution state for reopen.
        try:
            mark_flow_migration_pending(engine, flow.name)
            schedule_loaded_flow_migrations(engine)
            retry_scheduled = flow_migration_pending(engine, flow.name)
        except Exception:
            clear_flow_migration_pending(engine, flow.name)
            logging.getLogger("griptape_nodes").warning(
                "Manual Shot rebind was recorded; consolidation awaits workflow reopen")
    return {"ok": True, "code": "manual_rebind_recorded", "remaining_editors": remaining,
            "migration_retry_scheduled": retry_scheduled, "backup_path": transaction["backup_path"]}


def _offer_manual_rebind(engine: Any, flow: Any, exports: dict[str, Any], recovery: Path) -> list[str]:
    """Expose readonly choices only after preserving the complete original graph."""
    publishers = [node for node in flow.nodes.values() if isinstance(getattr(node, "metadata", None), dict)
        and node.metadata.get("library") == _LIBRARY and node.metadata.get("node_type") == "HMBImageAssetLibrary"]
    if len(publishers) != 1:
        return []
    publisher = publishers[0]
    catalog = publisher._hmb_shot_routing_catalog()
    if not isinstance(catalog, dict) or not catalog.get("shots"):
        return []
    prepared = {}
    transaction = {"publisher": weakref.ref(publisher),
        "publisher_instance_uuid": catalog["publisher_instance_uuid"],
        "backup_path": str(recovery), "backup_sha256": hashlib.sha256(recovery.read_bytes()).hexdigest(),
        "nodes": prepared}
    with _LOCK:
        _MANUAL_REBINDS.setdefault(engine, {})[flow.name] = transaction
    for name, exported in exports.items():
        node = flow.nodes.get(name)
        kind = _kind(node)
        prepare = getattr(node, "_hmb_prepare_manual_rebind", None)
        if kind not in {"prompt", "agent"} or not callable(prepare):
            continue
        subscription = _subscription(node, exported)
        current_shot = next((row for row in catalog["shots"]
            if row.get("shot_uuid") == subscription.get("shot_uuid")), None)
        if (subscription.get("enabled") is True
                and subscription.get("channel_uuid") == catalog["channel_uuid"]
                and isinstance(current_shot, dict)
                and current_shot.get("number") == subscription.get("shot_number")
                and current_shot.get("name") == subscription.get("shot_name")
                and not _node_manual_rebind_required(node)):
            continue  # Exact, already valid original bindings stay untouched.
        digest = str(exported.get("state_sha256") if kind == "prompt" else exported.get("digest") or "")
        if not digest:
            continue
        entry = {"node": weakref.ref(node), "digest": digest, "kind": kind, "confirmed": False}
        prepared[name] = entry
        try:
            accepted = prepare(deepcopy(catalog), {"required": True,
                "reason": "기존 샷 연결을 확인한 뒤 직접 다시 선택하세요. 원본 입력은 복구 파일에 보존되어 있습니다.",
                "backup_path": str(recovery), "source_node_name": name,
                "publisher_node_name": publisher.name, "expected_source_digest": digest})
            if accepted is False:
                prepared.pop(name, None)
        except Exception:
            prepared.pop(name, None)
            logging.getLogger("griptape_nodes").warning("Manual Shot rebind choices could not be prepared for %s", name)
    return list(prepared)


def _block_flow(engine: Any, flow_name: str, value: dict[str, Any]) -> None:
    with _LOCK:
        _BLOCKED.setdefault(engine, {})[flow_name] = {"code": "workflow_migration_failed",
            "reason": value.get("reason", value.get("code", "Consolidation did not complete")),
            "backup_path": value.get("backup_path"), "rollback": value.get("rollback", "not_needed")}


def pending_flow_names(engine: Any) -> tuple[str, ...]:
    with _LOCK:
        return tuple(_PENDING.get(engine, ()))


def clear_flow_migration_pending(engine: Any, flow_name: str) -> None:
    with _LOCK:
        _PENDING.get(engine, set()).discard(flow_name)


def cancel_queued_flow_migrations(engine: Any) -> None:
    """Invalidate only queued work; a started transaction must commit/restore."""
    with _LOCK:
        _SCHEDULE_GENERATIONS[engine] = _SCHEDULE_GENERATIONS.get(engine, 0) + 1
        for name in _PENDING.get(engine, ()):
            _block_flow(engine, name, {"reason": "Library unloaded before editor consolidation completed"})
        _PENDING.pop(engine, None)


def mutation_is_internal() -> bool:
    return _INTERNAL.get() is True


def last_migration_result(engine: Any, flow_name: str) -> dict[str, Any] | None:
    with _LOCK:
        return deepcopy(_RESULTS.get(engine, {}).get(flow_name))


def _result(engine: Any, flow_name: str, value: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        _RESULTS.setdefault(engine, {})[flow_name] = deepcopy(value)
    if value.get("ok") is not True:
        logging.getLogger("griptape_nodes").warning("HMB editor consolidation for %s: %s; recovery: %s",
            flow_name, value.get("reason", value.get("code")), value.get("backup_path"))
    return value


def flow_migration_inflight(engine: Any, flow_name: str | None = None) -> bool:
    with _LOCK:
        names = _INFLIGHT.get(engine, ())
        return bool(names) if flow_name is None else flow_name in names


def _edge_records(engine: Any, node_names: set[str]) -> list[dict[str, Any]]:
    records = []
    connections = engine.flow_manager.get_connections()
    for connection in tuple(connections.connections.values()):
        if connection.source_node.name not in node_names and connection.target_node.name not in node_names:
            continue
        records.append({"source_node_name": connection.source_node.name,
            "source_parameter_name": connection.source_parameter.name,
            "target_node_name": connection.target_node.name,
            "target_parameter_name": connection.target_parameter.name,
            "is_node_group_internal": bool(getattr(connection, "is_node_group_internal", False))})
    return sorted(records, key=_edge_key)


def _edge_key(edge: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(edge[key] for key in ("source_node_name", "source_parameter_name",
        "target_node_name", "target_parameter_name", "is_node_group_internal"))


def _registered_flow(engine: Any, flow_name: str) -> Any:
    flow = engine.flow_manager.get_flow_by_name(flow_name)
    _require(isinstance(getattr(flow, "nodes", None), dict), "Unsupported flow inventory")
    for name, node in flow.nodes.items():
        _require(engine.node_manager._name_to_parent_flow_name.get(name) == flow_name
            and engine.object_manager._name_to_objects.get(name) is node,
            "Unregistered or moved node in the migration flow")
    return flow


def _raw_node_state(node: Any) -> dict[str, Any]:
    return {"metadata": deepcopy(node.metadata),
        "parameter_values": deepcopy(dict(node.parameter_values)),
        "parameter_output_values": deepcopy(dict(node.parameter_output_values))}


def _stamp(engine: Any, flow: Any) -> str:
    return _digest({"nodes": {name: _raw_node_state(node) for name, node in flow.nodes.items()},
        "metadata": flow.metadata, "edges": _edge_records(engine, set(flow.nodes))})


async def _send(engine: Any, request: Any, expected: Any) -> Any:
    if type(request).__name__ == "DeleteNodeRequest":
        # Native deletion enters a Node context even with an explicit name.
        # Its only suspending path cancels a running flow: migration forbids
        # that path, including a fresh check immediately before dispatch.
        _require(not engine.flow_manager.check_for_existing_running_flow(),
            "A workflow started; editor deletion was refused")
        node_name = getattr(request, "node_name", None)
        _require(isinstance(node_name, str) and bool(node_name), "Migration deletion requires an explicit node")
        flow = _registered_flow(engine, engine.node_manager.get_node_parent_flow_by_name(node_name))
        _require(flow.nodes.get(node_name) is engine.node_manager.get_node_by_name(node_name),
            "Migration deletion node changed")
        return _structural_request(engine, flow, request, expected)
    request.broadcast_result = True
    result = await engine.ahandle_request(request)
    _require(isinstance(result, expected), "SDK structure operation failed: " + type(request).__name__)
    return result


def _structural_request(engine: Any, flow: Any, request: Any, expected: Any) -> Any:
    """Scope one synchronous SDK operation without yielding caller context."""
    _require(_registered_flow(engine, flow.name) is flow, "Migration structure flow changed")
    request.broadcast_result = True
    with engine.context_manager.flow(flow=flow):
        result = engine.handle_request(request)
    _require(not inspect.isawaitable(result), "SDK structure operation returned an awaitable")
    _require(isinstance(result, expected), "SDK structure operation failed: " + type(request).__name__)
    return result


def _capture_editors(flow: Any) -> tuple[dict[str, list[Any]], dict[str, dict[str, Any]]]:
    groups: dict[str, list[Any]] = {kind: [] for kind in _KINDS.values()}
    exports = {}
    for node in flow.nodes.values():
        kind = _kind(node)
        if kind is None:
            continue
        _require(not getattr(node, "_hmb_node_deleted", False), "An HMB editor is being deleted")
        _require(getattr(node, "parent_group", None) is None,
            "Grouped editors require a group-aware migration; originals retained")
        getter = getattr(node, _EXPORT_HOOKS[kind], None)
        _require(callable(getter), "This HMB editor does not support lossless consolidation")
        exports[node.name] = deepcopy(getter())
        _encoded(exports[node.name])  # Reject values which a durable backup would omit.
        groups[kind].append(node)
    return groups, exports


def _subscription(node: Any, export: dict[str, Any]) -> dict[str, Any]:
    if _kind(node) in {"agent", "finish_look"}:
        value = export.get("active_subscription", {})
    else:
        value = getattr(node, "_hmb_shot_channel_subscription", lambda: {})()
    return deepcopy(value) if isinstance(value, dict) else {}


def _validate_source_identity(engine: Any, flow: Any, groups: dict[str, list[Any]],
    exports: dict[str, Any], edges: list[dict[str, Any]]) -> None:
    """Authored UUIDs must still identify the registered same-flow publisher."""
    catalogs = {}
    for node in flow.nodes.values():
        if node.metadata.get("library") != _LIBRARY or node.metadata.get("node_type") != "HMBImageAssetLibrary":
            continue
        catalog = node._hmb_shot_routing_catalog()
        _require(isinstance(catalog, dict) and catalog.get("schema") == "hmb-shot-routing-catalog"
            and catalog.get("version") == 1 and isinstance(catalog.get("shots"), list),
            "ImageAsset publisher has no verified Shot catalog")
        document = {key: catalog[key] for key in ("channel_uuid", "generation", "shots")}
        _require(_digest(document) == catalog.get("metadata_sha256"), "ImageAsset catalog fingerprint changed")
        _require(catalog["channel_uuid"] not in catalogs, "Several ImageAsset publishers claim the same channel")
        catalogs[catalog["channel_uuid"]] = (node, catalog, node._hmb_project_identity())
    from _hmb_project import resolve_project
    for kind, nodes in groups.items():
        for node in nodes:
            subscription = _subscription(node, exports[node.name])
            _require(not _node_manual_rebind_required(node),
                "An original Prompt/Agent still needs its explicit Shot rebind confirmation")
            if subscription.get("enabled") is not True:
                legacy = (kind == "prompt" and not node._hmb_shot_manager_enabled()) or (
                    kind == "agent" and isinstance(exports[node.name].get("legacy_widget"), dict)
                    and node.metadata.get(METADATA_KEY, {}).get("schema") != SCHEMA)
                _require(not legacy,
                    "An original Prompt/Agent needs an explicit Shot selection before consolidation; originals retained")
                continue
            owner = catalogs.get(subscription.get("channel_uuid"))
            _require(owner is not None, "A legacy Shot has no authoritative ImageAsset publisher")
            source, catalog, project = owner
            shot = next((item for item in catalog["shots"] if item.get("shot_uuid") == subscription.get("shot_uuid")), None)
            _require(shot is not None and shot.get("number") == subscription.get("shot_number")
                and shot.get("name") == subscription.get("shot_name"), "A legacy Shot no longer matches its publisher")
            if kind == "prompt":
                _require(any(edge["source_node_name"] == source.name and edge["target_node_name"] == node.name
                    and edge["source_parameter_name"] == "SHOT_ASSET_OUT" and edge["target_parameter_name"] == "SHOT_ASSET_IN"
                    for edge in edges), "A legacy Prompt lacks its exact ImageAsset input")
                asset = exports[node.name].get("state", {}).get("image_asset", {})
                canonical_project = resolve_project(project, default_legacy=False)
                if asset.get("project_id"):
                    selected_project = resolve_project(asset["project_id"], default_legacy=False)
                    _require(selected_project["project_id"] == canonical_project["project_id"],
                        "A Prompt project differs from its registered ImageAsset publisher")


def _planned_edges(engine: Any, flow: Any, mapping: dict[str, str],
    edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Contraction is allowed only when actual port cardinalities still hold."""
    from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
    planned: dict[tuple[Any, ...], dict[str, Any]] = {}
    for original in edges:
        edge = dict(original)
        for side in ("source", "target"):
            field = side + "_node_name"
            edge[field] = mapping.get(edge[field], edge[field])
        source = engine.node_manager.get_node_by_name(edge["source_node_name"])
        target = engine.node_manager.get_node_by_name(edge["target_node_name"])
        source_parameter = source.get_parameter_by_name(edge["source_parameter_name"])
        target_parameter = target.get_parameter_by_name(edge["target_parameter_name"])
        _require(source_parameter is not None and target_parameter is not None,
            "A legacy port has no matching consolidated port")
        control = source_parameter.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value
        if source is target:
            _require(control, "Consolidation would create a data self-connection")
            continue  # Internal control steps collapse into the one editor.
        old_source = original["source_node_name"]
        if old_source in mapping and old_source != edge["source_node_name"] and not control:
            source_kind = _kind(engine.node_manager.get_node_by_name(old_source))
            allowed = (source_kind == "prompt" and edge["source_parameter_name"] == "PROMPT_OUT"
                and _kind(target) == "agent" and edge["target_parameter_name"] == "SHOT_PROMPT_IN") or (
                source_kind == "agent" and edge["source_parameter_name"] == "output"
                and target.metadata.get("library") == _LIBRARY
                and target.metadata.get("node_type") == "HMBSeedanceGeneration"
                and edge["target_parameter_name"] == "prompt") or (
                source_kind == "finish_look" and edge["source_parameter_name"] == "SHOT_FINISH_LOOK_OUT"
                and target.metadata.get("library") == _LIBRARY
                and target.metadata.get("node_type") == "HMBSeedanceGeneration"
                and edge["target_parameter_name"] == "SHOT_FINISH_LOOK_IN")
            _require(allowed, "An external legacy output needs a per-Shot port alias; originals retained")
        planned[_edge_key(edge)] = edge
    data_inputs: dict[tuple[str, str], tuple[str, str]] = {}
    control_outputs: dict[tuple[str, str], tuple[str, str]] = {}
    adjacency: dict[str, set[str]] = {}
    for edge in planned.values():
        source = engine.node_manager.get_node_by_name(edge["source_node_name"])
        parameter = source.get_parameter_by_name(edge["source_parameter_name"])
        upstream = (edge["source_node_name"], edge["source_parameter_name"])
        downstream = (edge["target_node_name"], edge["target_parameter_name"])
        if parameter.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value:
            _require(upstream not in control_outputs or control_outputs[upstream] == downstream,
                "Several legacy control outputs cannot share one output port")
            control_outputs[upstream] = downstream
        else:
            _require(downstream not in data_inputs or data_inputs[downstream] == upstream,
                "Several legacy input sources cannot share one input port")
            data_inputs[downstream] = upstream
        adjacency.setdefault(upstream[0], set()).add(downstream[0])
    visiting: set[str] = set()
    done: set[str] = set()
    def visit(name: str) -> None:
        _require(name not in visiting, "Consolidation would create a dependency cycle")
        if name in done:
            return
        visiting.add(name)
        for target in adjacency.get(name, ()):
            visit(target)
        visiting.remove(name)
        done.add(name)
    for name in adjacency:
        visit(name)
    return sorted(planned.values(), key=_edge_key)


async def _snapshot(engine: Any, flow: Any, exports: dict[str, Any]) -> dict[str, Any]:
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest, SerializeFlowToCommandsResultSuccess
    from griptape_nodes.retained_mode.events.node_events import SerializeNodeToCommandsRequest, SerializeNodeToCommandsResultSuccess
    flow_result = _structural_request(engine, flow, SerializeFlowToCommandsRequest(flow_name=flow.name), SerializeFlowToCommandsResultSuccess)
    nodes = {}
    for node in flow.nodes.values():
        pool: dict[str, Any] = {}
        result = _structural_request(engine, flow, SerializeNodeToCommandsRequest(node_name=node.name,
            unique_parameter_uuid_to_values=pool, serialize_all_parameter_values=True), SerializeNodeToCommandsResultSuccess)
        nodes[node.name] = {"commands": deepcopy(result.serialized_node_commands),
            "values": deepcopy(result.set_parameter_value_commands), "value_pool": deepcopy(pool),
            "raw": _raw_node_state(node)}
    value = {"schema": SCHEMA + "-recovery", "version": 1, "flow_name": flow.name,
        "flow_commands": deepcopy(flow_result.serialized_flow_commands), "flow_metadata": deepcopy(flow.metadata),
        "nodes": nodes, "edges": _edge_records(engine, set(flow.nodes)), "authoring_exports": deepcopy(exports)}
    _encoded(value)
    return value


def _write_recovery(snapshot: dict[str, Any], backup_root: Path | None) -> Path:
    if backup_root is None:
        backup_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / _LIBRARY / "workflow-migration"
    root = backup_root.resolve()
    directory = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    _require(directory.resolve().is_relative_to(root), "Unsafe migration recovery path")
    path = directory / "recovery.json"
    data = (json.dumps(_encoded(snapshot), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _require(path.read_bytes() == data, "Migration recovery snapshot was not persisted")
    return path


async def _restore(engine: Any, flow: Any, snapshot: dict[str, Any], affected: set[str]) -> None:
    from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest, DeleteNodeResultSuccess, DeserializeNodeFromCommandsRequest, DeserializeNodeFromCommandsResultSuccess
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest, SetParameterValueResultSuccess
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, CreateConnectionResultSuccess, DeleteConnectionRequest, DeleteConnectionResultSuccess
    from griptape_nodes.serialization.values import decode_value
    current = _edge_records(engine, set(flow.nodes))
    for edge in current:
        if edge["source_node_name"] in affected or edge["target_node_name"] in affected:
            values = {key: value for key, value in edge.items() if key != "is_node_group_internal"}
            await _send(engine, DeleteConnectionRequest(**values), DeleteConnectionResultSuccess)
    for name in affected:
        if name in flow.nodes:
            await _send(engine, DeleteNodeRequest(node_name=name), DeleteNodeResultSuccess)
    for name in snapshot["nodes"]:
        if name not in affected:
            continue
        saved = snapshot["nodes"][name]
        commands = deepcopy(saved["commands"])
        commands.create_node_command.node_name = name
        commands.create_node_command.override_parent_flow_name = flow.name
        result = _structural_request(engine, flow, DeserializeNodeFromCommandsRequest(serialized_node_commands=commands), DeserializeNodeFromCommandsResultSuccess)
        _require(result.node_name == name, "Rollback could not restore the exact original node name")
        for indirect in saved["values"]:
            request = deepcopy(indirect.set_parameter_value_command)
            request.node_name = name
            request.value = decode_value(deepcopy(saved["value_pool"][indirect.unique_value_uuid]))
            request.initial_setup = True
            _structural_request(engine, flow, request, SetParameterValueResultSuccess)
    for name, saved in snapshot["nodes"].items():
        node = flow.nodes[name]
        node.metadata.clear()
        node.metadata.update(deepcopy(saved["raw"]["metadata"]))
        node.parameter_values.clear()
        node.parameter_values.update(deepcopy(saved["raw"]["parameter_values"]))
        node.parameter_output_values.clear()
        node.parameter_output_values.update(deepcopy(saved["raw"]["parameter_output_values"]))
        prompt_export = snapshot.get("authoring_exports", {}).get(name)
        if isinstance(prompt_export, dict) and prompt_export.get("schema") == "hmb-prompt-merge-snapshot":
            current = node._hmb_prompt_merge_snapshot()
            node._hmb_restore_prompt_merge_snapshot(prompt_export, expected_state_sha256=current["state_sha256"])
    existing = {_edge_key(edge) for edge in _edge_records(engine, set(flow.nodes))}
    for edge in snapshot["edges"]:
        if _edge_key(edge) not in existing:
            await _send(engine, CreateConnectionRequest(**edge, initial_setup=True), CreateConnectionResultSuccess)
    # Connection callbacks may project source values while restoring the edges.
    # The captured authored/input and produced/output maps are the final source
    # of truth for rollback, so restore them again after those callbacks finish.
    for name, saved in snapshot["nodes"].items():
        node = flow.nodes[name]
        node.metadata.clear()
        node.metadata.update(deepcopy(saved["raw"]["metadata"]))
        node.parameter_values.clear()
        node.parameter_values.update(deepcopy(saved["raw"]["parameter_values"]))
        node.parameter_output_values.clear()
        node.parameter_output_values.update(deepcopy(saved["raw"]["parameter_output_values"]))
        editor_export = snapshot.get("authoring_exports", {}).get(name)
        if isinstance(editor_export, dict) and editor_export.get("schema") == "hmb-prompt-merge-snapshot":
            current = node._hmb_prompt_merge_snapshot()
            restored = node._hmb_restore_prompt_merge_snapshot(editor_export, expected_state_sha256=current["state_sha256"])
            _require(restored["state_sha256"] == editor_export["state_sha256"], "Prompt rollback authoring baseline differs")
        elif isinstance(editor_export, dict) and editor_export.get("schema") == "hmb-agent-authoring-export":
            _require(node._hmb_restore_agent_authoring_state(editor_export) is True,
                "Agent rollback private authoring state differs")
        elif isinstance(editor_export, dict) and editor_export.get("schema") == "hmb-finish-authoring-export":
            _require(node._hmb_restore_finish_merge_snapshot(editor_export) is True,
                "Finish Look rollback private authoring state differs")
    flow.metadata.clear()
    flow.metadata.update(deepcopy(snapshot["flow_metadata"]))
    _require(_edge_records(engine, set(flow.nodes)) == snapshot["edges"], "Rollback connection verification failed")
    for name, saved in snapshot["nodes"].items():
        _require(_digest(_raw_node_state(flow.nodes[name])) == _digest(saved["raw"]), "Rollback node state verification failed: " + name)


async def migrate_flow(engine: Any, flow_name: str, *, backup_root: Path | None = None) -> dict[str, Any]:
    """Migrate one idle, fully hydrated flow; never resolve/run any node."""
    with _LOCK:
        if flow_name in _INFLIGHT.get(engine, ()):
            return _result(engine, flow_name, {"ok": False, "code": "migration_already_running", "flow_name": flow_name})
        _INFLIGHT.setdefault(engine, set()).add(flow_name)
        _BLOCKED.get(engine, {}).pop(flow_name, None)
    token = _INTERNAL.set(True)
    recovery: Path | None = None
    snapshot = None
    changed = False
    committed = False
    affected: set[str] = set()
    survivors: dict[str, Any] = {}
    stage = "preflight"
    try:
        _require(not engine.flow_manager.check_for_existing_running_flow(), "A workflow is running; consolidation was deferred")
        flow = _registered_flow(engine, flow_name)
        groups, exports = _capture_editors(flow)
        existing = [node for nodes in groups.values() for node in nodes]
        requires_upgrade = any(_node_manual_rebind_required(node)
            or not bool(getattr(node, "_hmb_shot_manager_enabled", lambda: False)())
            or (_kind(node) in {"agent", "finish_look"} and isinstance(exports[node.name].get("legacy_widget"), dict)
                and node.metadata.get(METADATA_KEY, {}).get("schema") != SCHEMA) for node in existing)
        if all(len(nodes) <= 1 for nodes in groups.values()) and not requires_upgrade:
            # Loading an already consolidated graph suspended its constructor
            # callbacks too. Resume its exact publisher once after pending clears.
            _finish_manual_rebind(engine, flow, existing)
            committed = True
            return _result(engine, flow_name, {"ok": True, "code": "already_single", "flow_name": flow_name})
        survivors = {kind: nodes[0] for kind, nodes in groups.items() if nodes}
        affected = {node.name for nodes in groups.values() for node in nodes}
        mapping = {node.name: survivors[kind].name for kind, nodes in groups.items() for node in nodes}
        aliases = {node.name: {"node_name": survivors[kind].name, "participant_kind": kind,
            "subscription": _subscription(node, exports[node.name])} for kind, nodes in groups.items() for node in nodes}
        channels = {item["subscription"].get("channel_uuid") for item in aliases.values() if item["subscription"].get("enabled") is True}
        _require(len(channels) <= 1, "Editors from different Shot channels cannot be combined")
        original_edges = _edge_records(engine, set(flow.nodes))
        _validate_source_identity(engine, flow, groups, exports, original_edges)
        _require(all(edge["source_node_name"] in flow.nodes and edge["target_node_name"] in flow.nodes
            for edge in original_edges), "Cross-flow connections require a subtree-aware migration; originals retained")
        planned_edges = _planned_edges(engine, flow, mapping, original_edges)
        baseline = _stamp(engine, flow)
        snapshot = await _snapshot(engine, flow, exports)
        _require(_stamp(engine, flow) == baseline, "The flow changed during migration preparation")
        recovery = _write_recovery(snapshot, backup_root)
        _require(_stamp(engine, flow) == baseline, "The flow changed before migration started")
        documents: dict[str, str] = {}
        for node in groups["prompt"]:
            export = exports[node.name]
            candidate = export.get("materialized_documents", export.get("documents", {}))
            _require(isinstance(candidate, dict), "Prompt snapshot has no document collection")
            for key, value in candidate.items():
                if key in documents and documents[key] != value:
                    module = sys.modules.get(type(node).__module__)
                    fingerprint = getattr(module, "_prompt_document_intent_fingerprint", None)
                    _require(callable(fingerprint) and fingerprint(documents[key]) == fingerprint(value),
                        "Conflicting Prompt documents for the same Shot")
                    continue
                documents[key] = value
        # Hooks commit their base SDK values before returning a snapshot; even
        # an exception after that write belongs inside the rollback boundary.
        changed = True
        prompt = survivors.get("prompt")
        if prompt is not None:
            stage = "import_prompt"
            prompt._hmb_import_prompt_documents(documents,
                expected_state_sha256=exports[prompt.name]["state_sha256"])
        for node in groups["agent"]:
            stage = "import_agent:" + node.name
            survivors["agent"]._hmb_import_agent_authoring_state(exports[node.name], source_alias=node.name)
        finish = survivors.get("finish_look")
        if finish is not None:
            stage = "import_finish_look"
            finish._hmb_import_finish_documents([exports[node.name] for node in groups["finish_look"]],
                expected_state_sha256=exports[finish.name]["digest"])
        metadata = {"schema": SCHEMA, "version": 1, "flow_name": flow_name,
            "aliases": aliases, "backup_path": str(recovery),
            "archived_unbound_nodes": [node.name for node in groups["agent"]
                if exports[node.name].get("active_subscription", {}).get("enabled") is not True],
            "archived_unbound_finish_nodes": [node.name for node in groups["finish_look"]
                if exports[node.name].get("active_subscription", {}).get("enabled") is not True]}
        for node in survivors.values():
            node.metadata[METADATA_KEY] = deepcopy(metadata)
        flow.metadata[METADATA_KEY] = deepcopy(metadata)
        from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, CreateConnectionResultSuccess, DeleteConnectionRequest, DeleteConnectionResultSuccess
        from griptape_nodes.retained_mode.events.node_events import DeleteNodeRequest, DeleteNodeResultSuccess
        original_keys = {_edge_key(edge) for edge in original_edges}
        planned_keys = {_edge_key(edge) for edge in planned_edges}
        # Remove only replaced edges. Identical source/media/control edges stay.
        stage = "rewire"
        for edge in original_edges:
            if _edge_key(edge) not in planned_keys:
                await _send(engine, DeleteConnectionRequest(**{key: value for key, value in edge.items() if key != "is_node_group_internal"}), DeleteConnectionResultSuccess)
        for edge in planned_edges:
            if _edge_key(edge) not in original_keys:
                await _send(engine, CreateConnectionRequest(**edge, initial_setup=True), CreateConnectionResultSuccess)
        _require(_edge_records(engine, set(flow.nodes)) == planned_edges, "Consolidated connections did not verify before deletion")
        # State hooks and all surviving connections are verified before deletion.
        for kind, nodes in groups.items():
            for node in nodes[1:]:
                stage = "delete:" + node.name
                await _send(engine, DeleteNodeRequest(node_name=node.name), DeleteNodeResultSuccess)
        _require(all(sum(_kind(node) == kind for node in flow.nodes.values()) == 1 for kind, nodes in groups.items() if nodes), "Consolidated editor count is not one per kind")
        _require(_edge_records(engine, set(flow.nodes)) == planned_edges, "Consolidated connections changed during final cleanup")
        stage = "complete_manual_rebind"
        _finish_manual_rebind(engine, flow, list(survivors.values()))
        committed = True
        return _result(engine, flow_name, {"ok": True, "code": "consolidated", "flow_name": flow_name,
            "survivors": {kind: node.name for kind, node in survivors.items()},
            "aliases": aliases, "backup_path": str(recovery), "removed_nodes": sorted(affected - {node.name for node in survivors.values()}),
            "original_edges": len(original_edges), "consolidated_edges": len(planned_edges), "executed_nodes": 0})
    except BaseException as error:
        rollback = "not_needed"
        if changed and snapshot is not None:
            try:
                restoration = asyncio.create_task(_restore(engine, flow, snapshot, affected))
                while True:
                    try:
                        await asyncio.shield(restoration)
                        break
                    except asyncio.CancelledError:
                        if restoration.done():
                            restoration.result()
                            break
                        # A second stop cannot leave the first stop's rollback
                        # half-applied. Propagate cancellation after restoration.
                        continue
                rollback = "verified"
            except BaseException as restore_error:
                rollback = "failed: " + type(restore_error).__name__ + ": " + str(restore_error)
        if not isinstance(error, Exception):
            value = {"ok": False, "code": "migration_cancelled", "flow_name": flow_name,
                "rollback": rollback, "backup_path": str(recovery) if recovery else None, "executed_nodes": 0}
            _block_flow(engine, flow_name, value)
            _result(engine, flow_name, value)
            raise
        value = {"ok": False, "code": "migration_conflict" if isinstance(error, MigrationConflict) else "migration_failed",
            "flow_name": flow_name, "reason": str(error), "rollback": rollback,
            "stage": stage,
            "backup_path": str(recovery) if recovery else None, "executed_nodes": 0}
        if isinstance(error, MigrationConflict) and rollback in {"not_needed", "verified"}:
            # Even a preflight mismatch needs a durable original before a team
            # member explicitly reconnects legacy editors. Never infer a Shot
            # from its display number, delete originals, or admit old outputs.
            try:
                flow = _registered_flow(engine, flow_name)
                _groups, current_exports = _capture_editors(flow)
                if recovery is None:
                    preserved = await _snapshot(engine, flow, current_exports)
                    recovery = _write_recovery(preserved, backup_root)
                    value["backup_path"] = str(recovery)
                value["manual_rebind_editors"] = _offer_manual_rebind(engine, flow, current_exports, recovery)
            except Exception:
                # Original nodes remain intact if recovery/choice preparation
                # is unavailable. Do not present that state as a successful fix.
                value["manual_rebind_editors"] = []
        _block_flow(engine, flow_name, value)
        return _result(engine, flow_name, value)
    finally:
        _INTERNAL.reset(token)
        with _LOCK:
            _INFLIGHT.get(engine, set()).discard(flow_name)
            _PENDING.get(engine, set()).discard(flow_name)
        # Resume normal routing only after a verified commit. Failed/restored
        # legacy graphs remain explicitly suspended, not in a loading spinner.
        try:
            flow = _registered_flow(engine, flow_name)
            first = next((node for node in flow.nodes.values() if node.metadata.get("library") == _LIBRARY
                and node.metadata.get("node_type") == "HMBImageAssetLibrary"), None)
            if first is None:
                first = next((node for node in flow.nodes.values() if _kind(node) is not None), None)
            if committed and first is not None:
                from _hmb_shot_routing import schedule_post_hydration_reconcile
                reserve_publisher = getattr(first, "_reconcile_hmb_shot_routing", None)
                if callable(reserve_publisher):
                    reserve_publisher()
                else:
                    schedule_post_hydration_reconcile(first)
        except Exception:
            pass


def schedule_loaded_flow_migrations(engine: Any) -> None:
    """Post-dispatch notification schedules work outside the hook's context."""
    names = pending_flow_names(engine)
    if not names:
        return
    with _LOCK:
        generation = _SCHEDULE_GENERATIONS.get(engine, 0)
    loop = getattr(engine.event_manager, "event_loop", None)
    if loop is None or loop.is_closed() or not loop.is_running():
        # Unsupported/no-loop hosts retain originals and report no success.
        for name in names:
            clear_flow_migration_pending(engine, name)
        return
    async def coordinator() -> None:
        from griptape_nodes.retained_mode.engine import engine_scope
        with engine_scope(engine):
            for name in names:
                with _LOCK:
                    if _SCHEDULE_GENERATIONS.get(engine, 0) != generation:
                        return
                await migrate_flow(engine, name)
    def start() -> None:
        asyncio.create_task(coordinator(), context=contextvars.Context())
    loop.call_soon_threadsafe(start, context=contextvars.Context())
