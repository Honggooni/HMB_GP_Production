"""Process-owned temporary references; durable metadata never reconstructs clients.

An accepted/possibly accepted task can outlive the editor, including maintenance
intake. Only verified same-origin/account/task terminal evidence releases its
owned handles. There is deliberately no journal reader, expiry worker or timer.
"""
from __future__ import annotations

from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

_LOCK = threading.RLock()
_OWNED: dict[str, dict[str, Any]] = {}
_UNSCOPED: list[tuple[list[Any], list[Any]]] = []
_PROCESS_EPOCH = uuid4().hex
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_QUEUE_STATES = frozenset(("waiting", "dispatching", "uncertain", "blocked", "linked"))


def lease_id(value: Any) -> str:
    try:
        return str(UUID(value)) if isinstance(value, str) else ""
    except (ValueError, AttributeError):
        return ""


def principal_fingerprint(me: Any, origin: str) -> str:
    """Hash stable authenticated identity, never display name or credentials."""
    if not isinstance(me, dict):
        return ""
    user = me.get("user") if isinstance(me.get("user"), dict) else me
    identity = user.get("id", user.get("user_id"))
    if type(identity) not in (str, int) or not str(identity).strip() or len(str(identity)) > 256:
        return ""
    return hashlib.sha256(json.dumps([origin, str(identity)], separators=(",", ":")).encode()).hexdigest()


def safe_queue_fields(response: Any) -> dict[str, Any]:
    """Bounded metadata only; do not serialize arbitrary server fields."""
    if not isinstance(response, dict):
        return {}
    result = {}
    if type(response.get("maintenance_queued")) is bool:
        result["maintenance_queued"] = response["maintenance_queued"]
    if isinstance(response.get("maintenance_state"), str) and response["maintenance_state"] in _QUEUE_STATES:
        result["maintenance_state"] = response["maintenance_state"]
    if type(response.get("submission_outcome_unknown")) is bool:
        result["submission_outcome_unknown"] = response["submission_outcome_unknown"]
    return result


def _remote_identifier(value: Any) -> str:
    # Only the explicit storage path/key created by this process is accepted.
    text = str(value).replace("\\", "/") if isinstance(value, (str, Path, PurePosixPath)) else ""
    if (not text or len(text) > 4096 or text.startswith(("/", "."))
            or ":" in text or "?" in text or "#" in text
            or any(ord(char) < 32 for char in text) or ".." in PurePosixPath(text).parts):
        raise ValueError("Temporary reference identifier is invalid.")
    return text


def _journal_path(identifier: str) -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home() / ".local/share")
    return root / "HMB_GP_Production" / "reference-leases" / (identifier + ".json")


def _write(record: dict[str, Any]) -> None:
    # Explicit allowlist: clients, callbacks, signed URLs, prompts and tokens
    # never enter this document. The private journal is not a cleanup command.
    data = {key: record[key] for key in ("lease_id", "origin", "account_fingerprint",
        "process_epoch", "client_request_id", "task_id", "queue_held", "unresolved", "scope", "remote_objects")}
    data.update(schema="hmb-reference-lease-v1", version=1, updated_at_ms=int(time.time() * 1000))
    target = _journal_path(record["lease_id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("." + target.stem + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        with suppress(OSError):
            temporary.unlink()


def acquire(*, origin: str, principal: str, client_request_id: str, cloud: list[Any],
            tos: list[Any], scope: str = "video") -> str:
    """Capture this run's real handles before POST; journal failure blocks POST."""
    if not cloud and not tos:
        return ""
    parsed = urlsplit(origin)
    if (not parsed.hostname or parsed.scheme not in {"http", "https"} or parsed.query or parsed.fragment
            or parsed.username or parsed.password or not _IDENTITY.fullmatch(client_request_id)
            or scope not in {"video", "my_box"}):
        raise ValueError("Temporary reference lease scope is invalid.")
    objects = ([{"service": "cloud", "path": _remote_identifier(path)} for _, path in cloud]
        + [{"service": "tos", "bucket": _remote_identifier(bucket), "key": _remote_identifier(key)}
           for _, bucket, key in tos])
    identifier = str(uuid4())
    record = dict(lease_id=identifier, origin=origin, account_fingerprint=principal or "unverified-" + _PROCESS_EPOCH,
        process_epoch=_PROCESS_EPOCH, client_request_id=client_request_id, task_id="", queue_held=False,
        unresolved=True, scope=scope, remote_objects=objects, cloud=list(cloud), tos=list(tos))
    with _LOCK:
        _write(record)
        _OWNED[identifier] = record
    return identifier


def _take(record: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    _write(dict(record, unresolved=False))  # Failed write leaves real handles held.
    record["unresolved"] = False
    return record.pop("cloud", []), record.pop("tos", [])


def reject_unsubmitted(identifier: str) -> tuple[list[Any], list[Any]]:
    """Caller has proven this create never started, or was explicitly rejected."""
    with _LOCK:
        record = _OWNED.get(lease_id(identifier))
        if not record or record["task_id"] or record["queue_held"] or not record["unresolved"]:
            return [], []
        return _take(record)


def observe(identifier: str, *, origin: str, principal: str, requested_id: str,
            response: Any) -> tuple[list[Any], list[Any]]:
    """Observe a validated response from the original create/same-key lookup.

    Lookup authorization/normal protocol validation belongs to the caller. A
    copied lease ID, current UI selection or a same-named Shot is no authority.
    """
    if not isinstance(response, dict):
        return [], []
    with _LOCK:
        record = _OWNED.get(lease_id(identifier))
        if (not record or not record["unresolved"] or record["origin"] != origin
                or not principal or record["account_fingerprint"] != principal
                or requested_id not in {record["client_request_id"], record["task_id"]}):
            return [], []
        explicit_client = response.get("client_request_id")
        if explicit_client is not None and explicit_client != record["client_request_id"]:
            return [], []
        task = response.get("job_id") or response.get("task_id") or response.get("id")
        if not isinstance(task, str) or not _IDENTITY.fullmatch(task):
            return [], []
        if record["task_id"] and record["task_id"] != task:
            return [], []
        record["task_id"] = task
        if response.get("maintenance_queued") is True:
            record["queue_held"] = True
        status = str(response.get("status") or "").lower()
        error = response.get("error")
        code = str(response.get("error_code") or (error.get("code") if isinstance(error, dict) else "") or "").lower()
        unknown = (response.get("submission_outcome_unknown") is True or status == "submission_unknown"
            or code in {"submission_unknown", "provider_overdue", "image_submission_unknown", "my_box_submission_unknown"})
        queue_state = response.get("maintenance_state")
        queue_present = response.get("maintenance_queued") is True or isinstance(queue_state, str) and queue_state in _QUEUE_STATES
        blocked_terminal = (record["scope"] == "video" and response.get("maintenance_queued") is True
            and queue_state == "blocked" and response.get("terminal") is True and status == "failed")
        # My Box's wire always declares resubmit_allowed=False, including a
        # real completed result; failed intake there has no terminal proof.
        native_terminal = (not queue_present and not unknown and
            ((record["scope"] == "video" and status in {"completed", "succeeded", "success", "failed", "failure"}
              and response.get("resubmit_allowed") is not False)
             or (record["scope"] == "my_box" and (status == "completed" or
                 status == "failed" and response.get("terminal") is True))))
        if not unknown and (blocked_terminal or native_terminal):
            return _take(record)
        _write(record)
        return [], []


def pending_metadata(identifier: str) -> dict[str, Any]:
    """Nonsecret diagnostic snapshot only; never return a storage client."""
    with _LOCK:
        record = _OWNED.get(lease_id(identifier))
        if not record:
            return {}
        return {key: record[key] for key in ("lease_id", "origin", "account_fingerprint", "process_epoch",
            "client_request_id", "task_id", "queue_held", "unresolved", "scope")}


def hold_unscoped(cloud: list[Any], tos: list[Any]) -> None:
    """Conservative fallback for a legacy interrupted call without a lease.

    No origin/task may be invented and these handles must never become a
    subsequent Run's cleanup targets. Remote retention remains authoritative.
    """
    if cloud or tos:
        with _LOCK:
            _UNSCOPED.append((list(cloud), list(tos)))
