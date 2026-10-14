"""Authenticated web requests for the existing local HMB execution pipeline.

The web supplies a prompt and a command identity, never Python or node state.
Only a live, engine-owned Generator snapshot may authorize an Agent execution.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
from copy import copy, deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any
from uuid import UUID, uuid4
import weakref

import _hmb_review as _review
from _hmb_project import resolve_project

logger = logging.getLogger(__name__)
PROTOCOL = "hmb-web-rerender-v1"
POLICY_APPLICATION = "preserved_parent"
PROJECT_ROUTING_SCHEMA = "hmb-project-routing-v1"
PROJECT_IDS = frozenset({"dinoster5", "katuri8", "superwings12"})
PARENT_SETTINGS_SCHEMA = "hmb-rerender-parent-settings-v1"
PARENT_SETTINGS_FIELDS = frozenset({
    "model", "input_mode", "quality", "resolution", "aspect_ratio", "ratio",
    "duration_seconds", "duration", "generate_audio", "output_format", "watermark",
    "return_last_frame", "execution_expires_after", "priority", "omni_reference_task_type",
})
PARENT_SETTINGS_CONTRACT_FIELDS = (
    "frozen_generation_settings_schema", "frozen_generation_settings",
    "frozen_generation_settings_sha256", "frozen_generation_settings_binding_sha256",
)
API_ROOT = "/api/v1/reviews/rerender"
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,200}\Z")
_MAX_DOCUMENT = 8 * 1024 * 1024
_TERMINAL = frozenset({"completed", "failed", "uncertain", "cancelled"})


def _json(value: Any) -> str:
    result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(result.encode("utf-8")) > _MAX_DOCUMENT:
        raise ValueError("web_rerender_record_too_large")
    return result


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("invalid_web_rerender_identity")
    return value


def _require_parent_policy_identity(value: Any) -> None:
    if (not isinstance(value, dict) or value.get("mode") != POLICY_APPLICATION
            or value.get("reinjected") is not False):
        raise ValueError("web_rerender_policy_mode_mismatch")


def parent_generation_settings(command: Any) -> dict[str, Any]:
    """Verify the Broker's sparse original request, including parent binding."""
    if not isinstance(command, dict) or command.get("frozen_generation_settings_schema") != PARENT_SETTINGS_SCHEMA:
        raise ValueError("web_rerender_parent_settings_contract_required")
    settings = command.get("frozen_generation_settings")
    if not isinstance(settings, dict) or set(settings) - PARENT_SETTINGS_FIELDS:
        raise ValueError("web_rerender_parent_settings_unsupported")
    if not {"model", "input_mode", "generate_audio"}.issubset(settings) or not (
        {"quality", "resolution"} & settings.keys()
    ) or not ({"duration", "duration_seconds"} & settings.keys()):
        raise ValueError("web_rerender_parent_settings_incomplete")
    for key, value in settings.items():
        expected = (bool if key in {"generate_audio", "watermark", "return_last_frame"}
                    else int if key in {"duration", "duration_seconds", "execution_expires_after", "priority"}
                    else str)
        if type(value) is not expected or (expected is str and (not value or len(value) > 256)):
            raise ValueError("web_rerender_parent_settings_invalid_type")
    for left, right in (("duration", "duration_seconds"), ("ratio", "aspect_ratio")):
        if left in settings and right in settings and settings[left] != settings[right]:
            raise ValueError("web_rerender_parent_settings_alias_conflict")
    digest = _digest(settings)
    if command.get("frozen_generation_settings_sha256") != digest:
        raise ValueError("web_rerender_parent_settings_integrity_failed")
    project = _project_identity(command, strict=True)
    binding = {"schema": PARENT_SETTINGS_SCHEMA, "parent_task_id": _identifier(command.get("parent_task_id")),
               **project, "frozen_generation_settings_sha256": digest}
    if command.get("frozen_generation_settings_binding_sha256") != _digest(binding):
        raise ValueError("web_rerender_parent_settings_binding_mismatch")
    return deepcopy(settings)


def _project_identity(value: Any, *, strict: bool = False) -> dict[str, str]:
    identity = resolve_project(value, default_legacy=not strict)
    public = {key: identity[key] for key in ("project_id", "project_name")}
    if strict and (not isinstance(value, dict) or any(value.get(key) != item for key, item in public.items())):
        raise ValueError("web_rerender_project_identity_mismatch")
    return public


def runtime_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        raise RuntimeError("web_rerender_local_storage_unavailable")
    return Path(base) / "HMB_GP_Production" / "web-rerender" / "v1"


class OperationJournal:
    """A durable gate before either paid call, shared by local engine processes.

    An interrupted Agent call is never restarted just because its worker lease
    expired. Saved Agent results may be consumed once; uncertain video submits
    keep their original render key for the Broker's existing recovery path.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else runtime_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "operations.sqlite3"
        with closing(self._connect()) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS identity (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("""CREATE TABLE IF NOT EXISTS operations (
                operation_key TEXT PRIMARY KEY, origin TEXT NOT NULL,
                owner_key TEXT NOT NULL, command_id TEXT NOT NULL,
                render_key TEXT NOT NULL, command_hash TEXT NOT NULL,
                state TEXT NOT NULL, document TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            )""")

    def worker_id(self) -> str:
        with closing(self._connect()) as connection:
            connection.execute("INSERT OR IGNORE INTO identity VALUES('worker_id', ?)", (str(uuid4()),))
            return _uuid(connection.execute("SELECT value FROM identity WHERE name='worker_id'").fetchone()[0])

    def descendants(self, origin: str, owner_key: str, parent: str, project_id: str = "") -> list[str]:
        """Recover confirmed Broker jobs, never provisional submission keys."""
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT state,render_key,document FROM operations WHERE origin=? AND owner_key=? "
                                      "ORDER BY updated_at DESC LIMIT 1000", (origin, owner_key)).fetchall()
        edges = []
        for row in rows:
            document = json.loads(row["document"])
            if project_id and _project_identity(document.get("command"))["project_id"] != project_id:
                continue
            # execute writes result only after the Broker acknowledges child
            # identity. A failed/unknown operation's arbitrary result is not
            # that acknowledgement, and its client key is never a child job.
            result = document.get("result") or {}
            child = str(result.get("task_id") or "") if row["state"] in {"submitted", "completed"} else ""
            if not child or child == row["render_key"]:
                child = ""
                checkpoint = document.get("checkpoint") or {}
                if (checkpoint.get("task_identity") == "broker_task"
                        and checkpoint.get("stage") in {"accepted", "remote_succeeded", "local_succeeded",
                                                        "terminal", "cancelled_locally", "timed_out"}
                        and checkpoint.get("status") not in {"submitting", "submission_unknown"}
                        and checkpoint.get("broker_server_url") == origin):
                    candidate = str(checkpoint.get("task_id") or "")
                    if candidate != row["render_key"]:
                        child = candidate
            source = str(document["command"].get("parent_task_id") or "")
            if _ID.fullmatch(child) and _ID.fullmatch(source):
                edges.append((source, child))
        found = [parent]
        for _ in range(32):
            added = [child for source, child in edges if source in found and child not in found]
            if not added:
                break
            found = list(dict.fromkeys([*found, *added]))[:32]
        return found[1:]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def key(origin: str, owner_key: str, command_id: str) -> str:
        return _digest([origin, owner_key, _identifier(command_id)])

    def accept(self, *, origin: str, owner_key: str, command: dict[str, Any]) -> dict[str, Any]:
        command_id = _identifier(command["command_id"])
        render_key = _identifier(command["render_key"])
        # Lease credentials and transport timestamps are deliberately excluded.
        authored = {key: deepcopy(command.get(key)) for key in (
            "command_id", "render_key", "parent_task_id", "review_id",
            "target_id", "binding_fingerprint", "prompt", "project_id", "project_name")}
        authored.update({field: deepcopy(command[field]) for field in PARENT_SETTINGS_CONTRACT_FIELDS if field in command})
        fingerprint = _digest(authored)
        key = self.key(origin, owner_key, command_id)
        document = {"command": authored, "agent_result": None, "checkpoint": None,
                    "result": None, "error_code": ""}
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT * FROM operations WHERE operation_key=?", (key,)).fetchone()
                if row is not None:
                    if row["command_hash"] != fingerprint or row["render_key"] != render_key:
                        raise ValueError("web_rerender_operation_conflict")
                else:
                    connection.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?)", (
                        key, origin, owner_key, command_id, render_key, fingerprint,
                        "accepted", _json(document), now, now))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self.read(key)

    def read(self, key: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM operations WHERE operation_key=?", (key,)).fetchone()
        if row is None:
            raise KeyError("web_rerender_operation_missing")
        result = dict(row)
        result["document"] = json.loads(result["document"])
        return result

    def transition(self, key: str, expected: set[str], state: str, **updates: Any) -> dict[str, Any]:
        if not expected or not state:
            raise ValueError("invalid_web_rerender_transition")
        if set(updates) - {"agent_result", "checkpoint", "result", "error_code"}:
            raise ValueError("invalid_web_rerender_record_fields")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT state,document FROM operations WHERE operation_key=?", (key,)).fetchone()
                if row is None or row["state"] not in expected:
                    raise RuntimeError("web_rerender_already_consumed")
                document = json.loads(row["document"])
                document.update(deepcopy(updates))
                connection.execute("UPDATE operations SET state=?,document=?,updated_at=? WHERE operation_key=?",
                                   (state, _json(document), time.time(), key))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self.read(key)

    def checkpoint(self, key: str, checkpoint: dict[str, Any], reason: str, required: bool) -> None:
        del reason, required  # Every checkpoint uses the same durable transaction.
        row = self.read(key)
        if row["state"] in _TERMINAL:
            raise RuntimeError("web_rerender_operation_is_terminal")
        self.transition(key, {row["state"]}, row["state"], checkpoint=checkpoint)

    def output_directory(self, key: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", key) is None:
            raise ValueError("invalid_web_rerender_output_identity")
        target = self.root / "results" / key
        target.mkdir(parents=True, exist_ok=True)
        return target


def request_fingerprint(payload: dict[str, Any]) -> str:
    """Exact v1 Broker canonical request; never hash credentials into evidence."""
    ignored = {"client_request_id", "idempotency_key", "api_key", "access_token", "authorization"}
    canonical = {key: value for key, value in payload.items() if str(key).lower() not in ignored}
    canonical["model"] = str(payload.get("model") or "")
    canonical["provider"] = "volcengine_ark"
    # The Generator already bounds the full media request at 64 MiB. Its
    # canonical fingerprint must not inherit the journal's 8 MiB record limit.
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _uuid(value: Any) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("invalid_web_rerender_uuid")
    return value


class BrokerProtocol:
    def __init__(self, bridge: Any, worker_id: str, session_id: str) -> None:
        self.bridge = bridge
        self.worker_id = _uuid(worker_id)
        self.session_id = _uuid(session_id)
        self.owner_key = ""
        self.project_routing_ready = False
        self.parent_settings_ready = False
        self.optional_policy_status_supported = False
        self.policy_status_capability_checked = False
        self.policy_status_capability_checked_at = 0.0

    def discover_capabilities(self) -> None:
        capabilities = self.bridge._request_json("GET", "/api/v1/reviews/capabilities", payload=None, timeout=10)
        if not self._project_capability(capabilities):
            raise ValueError("web_rerender_project_server_upgrade_required")
        if capabilities.get("parent_settings_contract") != PARENT_SETTINGS_SCHEMA:
            raise ValueError("web_rerender_parent_settings_server_upgrade_required")
        self.parent_settings_ready = True
        self.optional_policy_status_supported = (
            capabilities.get("optional_project_policy_status_supported") is True
            and capabilities.get("optional_project_policy_status_schema") == "hmb-optional-agent-policy-status-v1"
        )
        self.policy_status_capability_checked = True
        self.policy_status_capability_checked_at = time.monotonic()

    def request(self, method: str, suffix: str, body: Any = None) -> dict[str, Any]:
        if not suffix.startswith("/") or ".." in suffix or "?" in suffix:
            raise ValueError("invalid_web_rerender_route")
        result = self.bridge._request_json(method, API_ROOT + suffix, payload=body, timeout=10)
        if not isinstance(result, dict):
            raise ValueError("invalid_web_rerender_response")
        return result

    def heartbeat(self, targets: list[dict[str, Any]], *, register: bool = False) -> None:
        # Read-only discovery must precede registration on an older strict
        # server; it must not clear the old worker's advertised targets.
        if not self.project_routing_ready or not self.parent_settings_ready:
            self.discover_capabilities()
        compatible_targets = []
        for target in targets[:16]:
            target = dict(target)
            if not self.optional_policy_status_supported:
                if target.get("policy_status") == "absent":
                    continue
                target.pop("policy_status", None)
            compatible_targets.append(target)
        body = {"worker_id": self.worker_id, "session_id": self.session_id, "targets": compatible_targets}
        reply = self.request("POST", "/worker/register" if register else "/worker/heartbeat", body)
        if (reply.get("schema") != PROTOCOL or reply.get("worker_id") != self.worker_id
                or reply.get("session_id") != self.session_id or reply.get("registered") is not True):
            raise ValueError("invalid_web_rerender_registration")
        owner = reply.get("user_id", reply.get("owner_key"))
        if type(owner) is not int or owner <= 0:
            raise ValueError("web_rerender_owner_unavailable")
        owner = str(owner)
        if self.owner_key and owner != self.owner_key:
            raise ValueError("web_rerender_account_changed")
        self.owner_key = owner
        self.project_routing_ready = self._project_capability(reply)
        if not self.project_routing_ready:
            raise ValueError("web_rerender_project_server_upgrade_required")
        self.parent_settings_ready = reply.get("parent_settings_contract") == PARENT_SETTINGS_SCHEMA
        if not self.parent_settings_ready:
            raise ValueError("web_rerender_parent_settings_server_upgrade_required")

    @staticmethod
    def _project_capability(reply: Any) -> bool:
        capability = reply.get("project_routing") if isinstance(reply, dict) else None
        ids = capability.get("project_ids") if isinstance(capability, dict) else None
        return bool(isinstance(capability, dict) and capability.get("schema") == PROJECT_ROUTING_SCHEMA
                    and isinstance(ids, list) and all(isinstance(item, str) for item in ids)
                    and len(ids) == len(PROJECT_IDS) and set(ids) == PROJECT_IDS)

    def claim(self, target_id: str) -> dict[str, Any] | None:
        reply = self.request("POST", "/worker/claim", {
            "worker_id": self.worker_id, "session_id": self.session_id, "target_id": _uuid(target_id)})
        command = reply.get("command")
        if command is None:
            return None
        if not isinstance(command, dict):
            raise ValueError("invalid_web_rerender_command")
        operation = _uuid(command.get("operation_id"))
        if (command.get("target_id") != target_id or command.get("session_id") != self.session_id
                or command.get("render_key") != "hmb-web-rerender-" + operation):
            raise ValueError("web_rerender_command_binding_mismatch")
        _uuid(command.get("lease_id"))
        if type(command.get("fence")) is not int or command["fence"] < 1:
            raise ValueError("invalid_web_rerender_fence")
        prompt = command.get("web_prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 54000:
            raise ValueError("invalid_web_rerender_prompt")
        if command.get("web_prompt_sha256") != hashlib.sha256(prompt.encode("utf-8")).hexdigest():
            raise ValueError("web_rerender_prompt_integrity_failed")
        # The execution mode is never decided by arbitrary caller fields.
        for field, expected in (("exclude_authored_prompt", True), ("preserve_connected_sources", True),
                                ("policy_required", False), ("input_mode", "web_only"),
                                ("policy_application", POLICY_APPLICATION), ("policy_reinjected", False)):
            if (command.get(field) is not expected if isinstance(expected, bool) else command.get(field) != expected):
                raise ValueError("web_rerender_execution_contract_mismatch")
        _project_identity(command, strict=True)
        parent_generation_settings(command)
        return command

    def credentials(self, command: dict[str, Any]) -> dict[str, Any]:
        return {"worker_id": self.worker_id, "session_id": self.session_id,
                "lease_id": command["lease_id"], "fence": command["fence"]}

    def renew(self, command: dict[str, Any]) -> None:
        reply = self.request("POST", "/commands/" + _uuid(command["operation_id"]) + "/lease",
                             self.credentials(command))
        if reply.get("operation_id") != command["operation_id"] or reply.get("fence") != command["fence"]:
            raise ValueError("web_rerender_lease_changed")

    def result(self, command: dict[str, Any], event: str, **fields: Any) -> dict[str, Any]:
        reply = self.request("POST", "/commands/" + _uuid(command["operation_id"]) + "/result",
                             {**self.credentials(command), "event": event, **fields})
        public = reply.get("command")
        if not isinstance(public, dict) or public.get("operation_id") != command["operation_id"]:
            raise ValueError("invalid_web_rerender_result_ack")
        return public


class CommandSubmissionOpener:
    """Bind the final *normal* Generator request to one leased web operation.

    Normal bridge validation/filtering and its provider/error/timeout handling
    remain intact. Only the exact create endpoint receives the claim headers.
    """
    def __init__(self, opener: Any, protocol: BrokerProtocol, command: dict[str, Any],
                 journal: OperationJournal, key: str, agent_result: dict[str, Any],
                 lease_live: threading.Event, submitted_prompt: str | None = None) -> None:
        self.opener, self.protocol, self.command = opener, protocol, deepcopy(command)
        self.journal, self.key = journal, key
        self.agent_result = deepcopy(agent_result)
        self.lease_live = lease_live
        self.submitted_prompt = submitted_prompt
        self._lock = threading.Lock()
        self._attempted = False

    def open(self, request: Any, *, timeout: float) -> Any:
        expected = self.protocol.bridge.server_url + "/api/v1/generate/video"
        if request.full_url != expected or request.get_method() != "POST":
            return self.opener.open(request, timeout=timeout)
        with self._lock:
            if self._attempted or not self.lease_live.is_set():
                raise RuntimeError("web_rerender_submission_already_attempted_or_lease_lost")
            body = json.loads(request.data.decode("utf-8"))
            key = self.command["render_key"]
            if body.get("client_request_id") != key or request.get_header("Idempotency-key") != key:
                raise ValueError("web_rerender_render_key_mismatch")
            text = self.agent_result.get("text")
            digest = self.agent_result.get("output_sha256")
            if not isinstance(text, str) or digest != hashlib.sha256(text.encode("utf-8")).hexdigest():
                raise ValueError("web_rerender_agent_result_integrity_failed")
            _require_parent_policy_identity(self.agent_result.get("policy_identity"))
            expected_prompt = text if self.submitted_prompt is None else self.submitted_prompt
            if body.get("prompt") != expected_prompt:
                raise ValueError("web_rerender_submitted_prompt_mismatch")
            project = _project_identity(self.command, strict=True)
            if _project_identity(body, strict=True) != project:
                raise ValueError("web_rerender_submitted_project_mismatch")
            frozen = parent_generation_settings(self.command)
            if set(body) & {"seed", "camera_fixed", "codec", "video_codec", "task"}:
                raise ValueError("web_rerender_submitted_settings_unsupported")
            if body.get("model") != frozen["model"]:
                raise ValueError("web_rerender_submitted_model_mismatch")
            # The normal bridge may omit model-specific defaults or use wire
            # aliases. Restore exactly the parent's present settings keys;
            # never leak facade-only validation values into the child request.
            for field in PARENT_SETTINGS_FIELDS:
                body.pop(field, None)
            body.update(frozen)
            request.data = json.dumps(body, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"), allow_nan=False).encode("utf-8")
            request.remove_header("Content-length")
            try:
                self.protocol.result(self.command, "prepared", agent_output=text,
                                     agent_output_sha256=digest, render_payload_sha256=request_fingerprint(body),
                                     policy_application=POLICY_APPLICATION, policy_reinjected=False, **project)
            except Exception as exc:
                # Host-only provenance: this acknowledgement failed before the
                # actual video POST. Never add this marker to request JSON or
                # to errors raised after delegating the final create request.
                exc._hmb_web_submission_not_started = True
                raise
            self.journal.transition(self.key, {"render_preparing"}, "submitting")
            self._attempted = True
            # No retry below this line: the provider may have accepted the call.
            request.add_header("X-HMB-Rerender-Operation", self.command["operation_id"])
            request.add_header("X-HMB-Rerender-Lease", self.command["lease_id"])
            request.add_header("X-HMB-Rerender-Fence", str(self.command["fence"]))
            if not self.lease_live.is_set():
                raise RuntimeError("web_rerender_lease_lost_before_submission")
            return self.opener.open(request, timeout=timeout)


def command_bridge(protocol: BrokerProtocol, command: dict[str, Any], journal: OperationJournal,
                   key: str, agent_result: dict[str, Any], lease_live: threading.Event,
                   submitted_prompt: str | None = None) -> Any:
    bridge = copy(protocol.bridge)
    bridge._opener = CommandSubmissionOpener(bridge._opener, protocol, command,
                                            journal, key, agent_result, lease_live, submitted_prompt)
    return bridge


class EngineWorker:
    """One outbound-only worker on the existing ORCHESTRATOR event loop.

    Readiness contains identities, hashes and status only. Private snapshots
    remain in this process, and all blocking Broker/file work runs off-loop.
    """

    def __init__(self, engine: Any, journal: OperationJournal | None = None) -> None:
        self.engine = weakref.ref(engine)
        self.journal = journal or OperationJournal()
        self.worker_id = self.journal.worker_id()
        self.session_id = str(uuid4())
        self.protocols: dict[str, BrokerProtocol] = {}
        self.targets: Any = weakref.WeakKeyDictionary()
        self.target_origins: Any = weakref.WeakKeyDictionary()
        self.target_projects: Any = weakref.WeakKeyDictionary()
        self.policy_cache: Any = weakref.WeakKeyDictionary()
        self.active: dict[str, asyncio.Task] = {}
        self.leases: dict[str, threading.Event] = {}
        self.children: dict[str, list[str]] = {}
        self.credential_digests: dict[str, str] = {}
        self.active_origins: dict[str, str] = {}
        self.stopped = False
        self.task: asyncio.Task | None = None
        self.last_error = ""

    def _nodes(self) -> list[Any]:
        engine = self.engine()
        if engine is None or engine.library_manager.is_worker is not False:
            return []
        manager = engine.node_manager
        names = tuple(getattr(manager, "_name_to_parent_flow_name", {}))
        nodes = []
        for name in names:
            try:
                node = manager.get_node_by_name(name)
                if type(node).__name__ == "HMBSeedanceGeneration" and callable(
                        getattr(node, "_hmb_web_rerender_capture_inputs", None)):
                    nodes.append(node)
            except (KeyError, ValueError):
                continue
        return nodes[:16]

    async def _policy(self, agent: Any, project_id: str) -> dict[str, Any]:
        cache = self.policy_cache.setdefault(agent, {})
        cached = cache.get(project_id)
        now = time.monotonic()
        if cached is not None and now - cached[0] < 30:
            return cached[1]
        status = await asyncio.to_thread(agent._hmb_web_rerender_policy_status, project_id=project_id)
        cache[project_id] = (now, status)
        return status

    async def _parent_task_id(self, node: Any, origin: str) -> str:
        """Read output/recovery identity without adopting a journal or Resume input.

        Native get_parameter_value reads inputs/defaults, not output-only Task
        IDs. Keep filesystem evidence off the engine loop, and never advertise
        a saved Task on a different Broker merely because settings changed.
        These local facts establish routing only; the Broker checks ownership.
        """
        outputs = getattr(node, "parameter_output_values", {})
        checkpoint = node.get_parameter_value("HMB_SEEDANCE_RECOVERY")
        checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
        checkpoint_id = str(checkpoint.get("task_id") or "").strip()
        if checkpoint.get("updated_at_ms") and not checkpoint_id:
            return ""  # An explicit cleared recovery record is a tombstone.
        output_id = str(outputs.get("generation_id") or "").strip()
        parent = output_id or checkpoint_id
        if _ID.fullmatch(parent) is None:
            return ""
        pinned = await asyncio.to_thread(_review.task_origin, parent)
        saved = str(checkpoint.get("broker_server_url") or "") if checkpoint_id == parent else ""
        if pinned and saved and pinned.rstrip("/") != saved.rstrip("/"):
            return ""
        recorded = pinned or saved
        return parent if recorded and recorded.rstrip("/") == origin.rstrip("/") else ""

    def _rotate_target(self, node: Any, origin: str) -> str:
        """Fence the old binding; its task callback retains cleanup ownership."""
        previous = self.targets.get(node)
        if previous is not None:
            live = self.leases.get(previous)
            if live is not None:
                live.clear()
            active = self.active.get(previous)
            if active is not None:
                active.cancel()
            self.children.pop(previous, None)
        target_id = str(uuid4())
        self.targets[node] = target_id
        self.target_origins[node] = origin
        return target_id

    async def _target(self, node: Any) -> tuple[BrokerProtocol, dict[str, Any], dict[str, Any], Any] | None:
        engine = self.engine()
        if engine is None:
            return None
        origin = node._selected_broker_server_url()
        if self.target_origins.get(node) != origin:
            # Rotate before authentication: even an unreachable new Broker must
            # immediately lose the old command's authority and child lineage.
            self._rotate_target(node, origin)
        protocol = self.protocols.get(origin)
        if protocol is None:
            bridge = node._create_broker_bridge(server_url=origin)
            protocol = BrokerProtocol(bridge, self.worker_id, self.session_id)
            self.protocols[origin] = protocol
        # Only a local change detector; this hash never establishes ownership,
        # leaves the process or replaces the authenticated server user_id.
        credential = await asyncio.to_thread(protocol.bridge._load_access_token)
        credential_digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()
        previous = self.credential_digests.get(origin)
        self.credential_digests[origin] = credential_digest
        if previous is not None and previous != credential_digest:
            for active_id, active_origin in tuple(self.active_origins.items()):
                if active_origin == origin:
                    event = self.leases.get(active_id)
                    if event is not None:
                        event.clear()
                    task = self.active.get(active_id)
                    if task is not None:
                        task.cancel()
            protocol = BrokerProtocol(node._create_broker_bridge(server_url=origin), self.worker_id, str(uuid4()))
            self.protocols[origin] = protocol
            for bound_node in tuple(self.targets):
                if bound_node._selected_broker_server_url() == origin:
                    self._rotate_target(bound_node, origin)
        target_id = self.targets[node]
        # This snapshot is strictly metadata-only. Byte availability and content
        # are verified separately by prepare_media after taking the node claim.
        snapshot = node._hmb_web_rerender_capture_inputs()
        project = _project_identity(snapshot.get("project"))
        if self.target_projects.get(node) != project["project_id"]:
            target_id = self._rotate_target(node, origin)
            self.target_projects[node] = project["project_id"]
        agent = engine.node_manager.get_node_by_name(snapshot["agent_name"])
        policy = await self._policy(agent, project["project_id"])
        policy_status = str(policy.get("policy_status") or (
            "available" if policy.get("policy_verified", policy.get("ready")) is True else "unavailable"
        ))
        if policy_status == "absent" and (
                not protocol.policy_status_capability_checked
                or (not protocol.optional_policy_status_supported
                    and time.monotonic() - protocol.policy_status_capability_checked_at >= 30.0)):
            await asyncio.to_thread(protocol.discover_capabilities)
        if policy_status == "absent" and not protocol.optional_policy_status_supported:
            # Older strict servers cannot accept the truthful absent-policy
            # descriptor. Keep their wire contract until support is advertised.
            return None
        readiness = node._hmb_web_rerender_readiness()
        own_busy = target_id in self.active
        busy = own_busy or bool(agent._hmb_web_rerender_busy()) or not readiness.get("ready")
        parent = await self._parent_task_id(node, origin)
        if parent:
            recorded_project = await asyncio.to_thread(_review.task_project, parent)
            if recorded_project["project_id"] != project["project_id"]:
                parent = ""
        descendants = (await asyncio.to_thread(self.journal.descendants, origin, protocol.owner_key, parent, project["project_id"])
                       if protocol.owner_key and parent else [])
        parents = [p for p in [parent, *descendants, *self.children.get(target_id, [])] if _ID.fullmatch(p or "")]
        parents = list(dict.fromkeys(parents))[-32:]
        current_origin = node._selected_broker_server_url()
        current_snapshot = node._hmb_web_rerender_capture_inputs()
        if current_origin != origin or current_snapshot["binding_fingerprint"] != snapshot["binding_fingerprint"]:
            # Authentication, policy and journal reads yield to the engine.
            # Discard a descriptor if settings changed during those awaits.
            self._rotate_target(node, current_origin)
            return None
        target = snapshot["target"]
        try:
            workflow = str(engine.context_manager.get_current_workflow_name())
        except Exception:
            workflow = str(target["flow_name"])
        descriptor = {
            "target_id": target_id, "workflow_id": workflow[:200],
            "agent_node_id": str(agent.name)[:200], "generator_node_id": str(node.name)[:200],
            "graph_revision": _digest([target, snapshot["source_bindings"]]),
            "snapshot_sha256": snapshot["binding_fingerprint"],
            "parent_task_ids": parents, "ready": bool(not busy and parents and policy.get("ready") is True),
            "busy": busy, "policy_verified": policy.get("policy_verified", policy.get("ready")) is True,
            "policy_version": str(policy.get("version") or "")[:200],
            "policy_application": POLICY_APPLICATION, "policy_reinjected": False,
            "frozen_generation_settings_schema": PARENT_SETTINGS_SCHEMA,
            **project,
        }
        if protocol.optional_policy_status_supported:
            descriptor["policy_status"] = policy_status
        return protocol, descriptor, snapshot, agent

    async def tick(self) -> None:
        grouped: dict[str, list[tuple[Any, dict[str, Any], dict[str, Any], Any]]] = {
            origin: [] for origin in self.protocols}
        for node in self._nodes():
            try:
                info = await self._target(node)
                if info is not None:
                    protocol, descriptor, snapshot, agent = info
                    grouped.setdefault(protocol.bridge.server_url, []).append((node, descriptor, snapshot, agent))
            except Exception:
                # Removing unavailable targets from the heartbeat disables old
                # buttons. Never leak node paths or exception text to the web.
                if node in self.targets:
                    self._rotate_target(node, self.target_origins.get(node, ""))
                self.last_error = "target_unavailable"
        for origin, items in grouped.items():
            protocol = self.protocols[origin]
            try:
                await asyncio.to_thread(protocol.heartbeat, [item[1] for item in items], register=not protocol.owner_key)
                self.last_error = ""
                for node, descriptor, snapshot, agent in items:
                    target_id = descriptor["target_id"]
                    if (not descriptor["ready"] or target_id in self.active or self.stopped
                            or (descriptor.get("policy_status") == "absent"
                                and not protocol.optional_policy_status_supported)):
                        continue
                    command = await asyncio.to_thread(protocol.claim, target_id)
                    if command is None:
                        continue
                    if (command.get("snapshot_sha256") != snapshot["binding_fingerprint"]
                            or command.get("parent_task_id") not in descriptor["parent_task_ids"]
                            or _project_identity(command, strict=True) != _project_identity(descriptor, strict=True)):
                        await asyncio.to_thread(protocol.result, command, "failed", error_code="target_changed")
                        continue
                    task = asyncio.create_task(self.execute(node, agent, snapshot, protocol, command))
                    self.active[target_id] = task
                    self.active_origins[target_id] = origin
                    task.add_done_callback(lambda done, target=target_id: self._finished(target, done))
            except Exception as exc:
                protocol.parent_settings_ready = False
                self.last_error = ("parent_settings_server_upgrade_required"
                                   if isinstance(exc, ValueError) and str(exc) == "web_rerender_parent_settings_server_upgrade_required"
                                   else "broker_unavailable_or_auth_required")
        await asyncio.to_thread(self._save_status, grouped)

    def _finished(self, target_id: str, task: asyncio.Task) -> None:
        if self.active.get(target_id) is task:
            self.active.pop(target_id, None)
            self.active_origins.pop(target_id, None)
        if not task.cancelled():
            task.exception()  # Retrieve failures without logging prompts/paths.

    def _save_status(self, grouped: dict[str, Any]) -> None:
        document = {"schema": PROTOCOL, "session_id": self.session_id,
                    "updated_at": time.time(), "active_commands": len(self.active),
                    "error_code": self.last_error,
                    "targets": [{**entry[1], "ready": bool(entry[1]["ready"] and self.protocols[origin].parent_settings_ready)}
                                for origin, items in grouped.items() for entry in items]}
        path = self.journal.root / ("worker-" + self.session_id + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(_json(document), encoding="utf-8")
        os.replace(temporary, path)

    async def _renew(self, protocol: BrokerProtocol, command: dict[str, Any], live: threading.Event,
                     execution_task: asyncio.Task | None) -> None:
        try:
            while live.is_set() and not self.stopped:
                await asyncio.sleep(25)
                if not live.is_set() or self.stopped:
                    return
                await asyncio.to_thread(protocol.renew, command)
        except Exception:
            live.clear()
            # The Agent can be waiting for another run's per-node reservation.
            # Losing the lease must cancel that wait before it can enter a
            # paid call later. Agent cancellation drains any native worker
            # before releasing its reservation or clearing its facade.
            if execution_task is not None and not execution_task.done():
                execution_task.cancel()

    async def execute(self, node: Any, agent: Any, snapshot: dict[str, Any],
                      protocol: BrokerProtocol, command: dict[str, Any]) -> None:
        target_id = command["target_id"]
        project = _project_identity(command, strict=True)
        if project != _project_identity(snapshot.get("project")):
            raise ValueError("web_rerender_source_project_mismatch")
        normalized = {"command_id": command["operation_id"], "render_key": command["render_key"],
                      "parent_task_id": command["parent_task_id"], "review_id": command["review_id"],
                      "target_id": target_id, "binding_fingerprint": command["snapshot_sha256"],
                      "prompt": command["web_prompt"], **project}
        normalized.update({field: deepcopy(command[field]) for field in PARENT_SETTINGS_CONTRACT_FIELDS if field in command})
        record = await asyncio.to_thread(self.journal.accept, origin=protocol.bridge.server_url,
                                         owner_key=protocol.owner_key, command=normalized)
        key = record["operation_key"]
        # Any prior Agent attempt is consumed permanently. In particular an
        # expired lease cannot turn an uncertain response into a second call.
        if record["state"] != "accepted" or command.get("state") != "claimed":
            return
        try:
            await asyncio.to_thread(self.journal.transition, key, {"accepted"}, "validating")
        except RuntimeError:
            return  # Another engine already consumed this operation.
        live = threading.Event()
        live.set()
        self.leases[target_id] = live
        renew = asyncio.create_task(self._renew(protocol, command, live, asyncio.current_task()))
        try:
            async with node._hmb_web_rerender_claim(snapshot) as claim:
                frozen_settings = parent_generation_settings(command)
                node._hmb_web_rerender_bind_parent_settings(claim, frozen_settings)
                media = await node._hmb_web_rerender_prepare_media(claim)
                if not live.is_set() or self.stopped:
                    raise RuntimeError("lease_lost")
                await asyncio.to_thread(self.journal.transition, key, {"validating"}, "agent_running")
                await asyncio.to_thread(protocol.result, command, "agent_started")
                if not live.is_set() or self.stopped:
                    raise RuntimeError("lease_lost")
                authority = agent._hmb_issue_web_rerender_authority(
                    request_id=command["operation_id"], generator=node, owner_key=protocol.owner_key)
                result = await agent._hmb_run_web_rerender(
                    command["web_prompt"], media, deepcopy(claim.parent_generation_context), authority)
                _require_parent_policy_identity(result.get("policy_identity"))
                # Store only safe output identity. Observations may contain
                # implementation details and policy content stays in Agent.
                saved = {field: deepcopy(result.get(field)) for field in
                         ("text", "run_id", "output_sha256", "policy_identity")}
                await asyncio.to_thread(self.journal.transition, key, {"agent_running"},
                                         "agent_done", agent_result=saved)
                if not live.is_set() or self.stopped:
                    raise RuntimeError("lease_lost")
                await asyncio.to_thread(self.journal.transition, key, {"agent_done"}, "render_preparing")

                async def checkpoint(value: dict[str, Any], *, reason: str, required: bool) -> None:
                    await asyncio.to_thread(self.journal.checkpoint, key, value, reason, required)

                submitted_prompt = node._compose_finish_look_prompt(
                    result["text"], snapshot["params"].get("_hmb_finish_look_out"))
                bridge = command_bridge(protocol, command, self.journal, key, saved, live, submitted_prompt)
                directory = await asyncio.to_thread(self.journal.output_directory, key)
                output = await node._hmb_web_rerender_execute(
                    claim, result, client_request_id=command["render_key"], output_directory=directory,
                    checkpoint_sink=checkpoint, submission_bridge=bridge,
                    parent_task_id=command["parent_task_id"], command_id=command["operation_id"])
                task_id = str(output.get("task_id") or "")
                if not _ID.fullmatch(task_id) or task_id == command["parent_task_id"]:
                    raise RuntimeError("missing_child_task")
                self.children.setdefault(target_id, []).append(task_id)
                # Broker is authoritative for provider completion. A local
                # download failure must not rewrite a succeeded provider job.
                ack = await asyncio.to_thread(protocol.result, command, "ack", child_task_id=task_id)
                state = "completed" if ack.get("state") == "completed" else "submitted"
                await asyncio.to_thread(self.journal.transition, key,
                                         {"submitting", "render_preparing"}, state, result=output)
        except BaseException as exc:
            row = await asyncio.to_thread(self.journal.read, key)
            if row["state"] not in _TERMINAL and row["state"] != "submitted":
                uncertain = row["state"] in {"agent_running", "submitting"}
                state = "uncertain" if uncertain else "failed"
                error_code = "execution_uncertain" if uncertain else "execution_failed"
                if (row["state"] == "agent_running"
                        and getattr(exc, "_hmb_web_output_contract_failed", False) is True):
                    state, error_code = "failed", "web_rerender_output_contract_invalid"
                if (row["state"] == "render_preparing"
                        and getattr(exc, "_hmb_web_submission_not_started", False) is True):
                    status = getattr(exc, "status_code", None)
                    error_code = (f"prepared_http_{status}" if type(status) is int and 100 <= status <= 599
                                  else "prepared_request_failed")
                await asyncio.to_thread(self.journal.transition, key, {row["state"]}, state,
                                         error_code=error_code)
                try:
                    await asyncio.to_thread(protocol.result, command, "failed",
                                             error_code=error_code)
                except Exception:
                    pass  # Lease expiry still fences all future submissions.
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            live.clear()
            renew.cancel()
            await asyncio.gather(renew, return_exceptions=True)
            if self.leases.get(target_id) is live:
                self.leases.pop(target_id, None)

    async def run(self) -> None:
        while not self.stopped and self.engine() is not None:
            try:
                await self.tick()
            except Exception:
                self.last_error = "worker_check_failed"
            await asyncio.sleep(5 if not self.last_error else 20)

    def stop(self) -> None:
        self.stopped = True
        for event in tuple(self.leases.values()):
            event.clear()
        for task in tuple(self.active.values()):
            task.cancel()
        if self.task is not None:
            self.task.cancel()


_WORKERS: Any = weakref.WeakKeyDictionary()
_PENDING_STARTS: Any = weakref.WeakKeyDictionary()
_WORKERS_LOCK = threading.RLock()


def ensure_engine_worker(engine: Any) -> None:
    """Schedule only on a live desktop engine, never start an SDK/worker runtime."""
    if engine.library_manager.is_worker is not False:
        return
    loop = engine.event_manager.event_loop
    if loop is None or loop.is_closed() or not loop.is_running():
        return
    with _WORKERS_LOCK:
        current = _WORKERS.get(engine)
        if current is not None and not current.stopped and current.task is not None and not current.task.done():
            return
        if engine in _PENDING_STARTS:
            return
        ticket = object()
        _PENDING_STARTS[engine] = ticket

    def start() -> None:
        with _WORKERS_LOCK:
            if _PENDING_STARTS.get(engine) is not ticket:
                return
            _PENDING_STARTS.pop(engine, None)
            from griptape_nodes.retained_mode.engine import engine_scope
            with engine_scope(engine):
                worker = EngineWorker(engine)
                worker.task = asyncio.create_task(worker.run())
                _WORKERS[engine] = worker

    loop.call_soon_threadsafe(start)


def stop_engine_worker(engine: Any) -> None:
    with _WORKERS_LOCK:
        _PENDING_STARTS.pop(engine, None)
        worker = _WORKERS.pop(engine, None)
    if worker is not None:
        loop = engine.event_manager.event_loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(worker.stop)
