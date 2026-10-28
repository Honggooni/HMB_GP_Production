"""Scoped CGT discovery and explicitly committed task-start operations.

The vendor SDK keeps login globals and disables certificate validation. Run it
only in a short-lived child with a verified, origin-scoped transport. No CGT
token, password, or account session is returned to the node or written to disk.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "hmb-cgt-own-tasks"
WORK_START_PLAN_SCHEMA = "hmb-cgt-work-start-plan-v1"
WORK_START_RESULT_SCHEMA = "hmb-cgt-work-start-result-v1"
TRUST_ROOT_SHA256 = "1576e52257f9880faf65020926bcd6f77d57dbaed3dd88243e9dd3987fc006b1"
MAX_TASKS = 2000
_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def _failure(code: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "version": 1, "status": code, "tasks": [], "projects": []}


def _text(value: Any, maximum: int = 256) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(ord(char) < 32 for char in value):
        raise ValueError("SOURCE_SCHEMA")
    return value


def _id(value: Any) -> str:
    text = _text(value, 36)
    if not _GUID.fullmatch(text):
        raise ValueError("SOURCE_SCHEMA")
    return text


def _owners(value: Any) -> set[str]:
    if isinstance(value, list):
        return {_id(item).lower() for item in value}
    if isinstance(value, str):
        return {item.lower() for item in _GUID.findall(value)}
    raise ValueError("SOURCE_SCHEMA")


def catalog(project_id: str = "", *, binding: dict[str, Any] | None = None,
            cgt_project_id: str | None = None) -> dict[str, Any]:
    """Finite child process; never import the vendor SDK into the engine."""
    if (not isinstance(project_id, str) or (project_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project_id))
            or (binding is not None and not project_id)):
        return _failure("SELECT_GP_PROJECT")
    if cgt_project_id is not None and (not isinstance(cgt_project_id, str) or not _GUID.fullmatch(cgt_project_id)):
        return _failure("PROJECT_UNAVAILABLE")
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "APPDATA", "LOCALAPPDATA", "USERPROFILE",
               "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP", "HMB_CGT_SDK_PATH"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", NO_PROXY="127.0.0.1,localhost,::1")
    options: dict[str, Any] = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--read-own"],
            input=json.dumps({"project_id": project_id, "cgt_project_id": cgt_project_id, "binding": binding}).encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=40, env=env, **options)
        if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
            return _failure("SDK_UNAVAILABLE")
        data = json.loads(result.stdout)
        if data.get("schema") != SCHEMA or data.get("version") != 1:
            return _failure("SOURCE_SCHEMA")
        return data
    except subprocess.TimeoutExpired:
        return _failure("TIMEOUT")
    except (OSError, ValueError, TypeError):
        return _failure("SDK_UNAVAILABLE")


def verify_binding(binding: dict[str, Any], project_id: str, snapshot: dict[str, Any]) -> None:
    """Compare saved source identities with a newly authenticated own-task read."""
    if snapshot.get("status") != "ready":
        raise ValueError("CGT 본인 작업을 다시 확인할 수 없습니다. 새로고침 후 확정하세요.")
    scope = binding.get("cgt_scope") or {}
    if (binding.get("cgt_account_id") != snapshot.get("account_id")
            or scope.get("project_id") != snapshot.get("project", {}).get("id")
            or scope.get("project_db") != snapshot.get("project", {}).get("database")
            or scope.get("origin") != snapshot.get("origin")
            or scope.get("account_id") != snapshot.get("account_id")
            or str(snapshot.get("project", {}).get("entity", "")).lower() != project_id.lower()):
        raise ValueError("CGT 계정 또는 프로젝트가 변경되었습니다. 창을 닫고 다시 선택하세요.")
    tasks = {row["task_id"]: row for row in snapshot.get("tasks", [])}
    for member in binding.get("members", []):
        if member.get("origin") != "cgt":
            continue
        task = tasks.get(member.get("cgt_task_id"))
        if (not task or member.get("cgt_identity") != task.get("identity")
                or member.get("source_name") != task.get("source_name")
                or member.get("artist") != task.get("artist") or member.get("status") != task.get("status")
                or scope.get("pipeline_id") != task.get("pipeline_id")):
            raise ValueError("CGT 샷 이름·배정·상태가 변경되었습니다. 새로고침 후 다시 선택하세요.")


def plan_wait_to_work_transition(
    previous_binding: dict[str, Any],
    committed_binding: dict[str, Any],
    project_id: str,
    snapshot: dict[str, Any],
    *,
    commit_request_id: str,
) -> dict[str, Any]:
    """Plan a start notice after an explicit local commit, without writing CGT.

    The installed SDK's status update has no expected-status/revision argument.
    A read followed by that update could overwrite a concurrent status change.
    Therefore this plan is deliberately not an SDK command and is not wired to
    save/load, preview, catalog or hierarchy confirmation. A future transport
    must enforce ``Wait`` -> ``Work`` atomically on the server before submission
    can be enabled. Existing ``Work`` and all other statuses are skipped.

    Callers must supply the state from before and after a successful explicit
    local shot commit. Only newly introduced CGT task identities are considered;
    an existing binding reopened or reconfirmed never starts work again.
    """
    if (not isinstance(previous_binding, dict) or not isinstance(committed_binding, dict)
            or not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project_id)
            or not isinstance(snapshot, dict) or not isinstance(commit_request_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", commit_request_id)):
        raise ValueError("INVALID_WORK_START_COMMIT")
    prior_members, members = previous_binding.get("members", []), committed_binding.get("members", [])
    if (not isinstance(prior_members, list) or not isinstance(members, list)
            or len(prior_members) > 5 or len(members) > 5
            or any(not isinstance(member, dict) for member in [*prior_members, *members])):
        raise ValueError("INVALID_WORK_START_BINDING")
    result: dict[str, Any] = {
        "schema": WORK_START_PLAN_SCHEMA, "status": "no_changes",
        "commit_request_id": commit_request_id, "transitions": [], "skipped": [],
        "submission_enabled": False, "requires_atomic_status_transition": True,
    }
    current_members = [member for member in members if member.get("origin") == "cgt"]
    if not current_members:
        return result
    if (snapshot.get("tls_verified") is not True or snapshot.get("hostname_verified") is not True
            or snapshot.get("can_bind") is not True or snapshot.get("truncated") is not False):
        raise ValueError("CGT_WORK_START_SOURCE_UNVERIFIED")
    scope = committed_binding.get("cgt_scope") or {}
    if not isinstance(scope, dict) or scope.get("module") != "shot" or scope.get("module_type") != "task":
        raise ValueError("CGT_WORK_START_SCOPE_CHANGED")
    for key in ("project_id", "pipeline_id", "account_id"):
        _id(scope.get(key))
    rows = snapshot.get("tasks")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("CGT_WORK_START_SOURCE_UNVERIFIED")
    row_ids = [_id(row.get("task_id")).lower() for row in rows]
    member_ids = [_id(member.get("cgt_task_id")).lower() for member in current_members]
    if len(set(row_ids)) != len(row_ids) or len(set(member_ids)) != len(member_ids):
        raise ValueError("CGT_WORK_START_DUPLICATE_TASK")
    verify_binding(committed_binding, project_id, snapshot)
    prior_ids = {
        _id(member.get("cgt_task_id")).lower()
        for member in prior_members if member.get("origin") == "cgt"
    }
    tasks = {row["task_id"].lower(): row for row in rows}
    for member in current_members:
        task_id = member["cgt_task_id"]
        task = tasks[task_id.lower()]
        identity = member.get("cgt_identity")
        if (not isinstance(identity, dict) or identity.get("task_id") != task_id
                or identity.get("pipeline_id") != scope["pipeline_id"]):
            raise ValueError("CGT_WORK_START_IDENTITY_CHANGED")
        _id(identity.get("entity_id"))
        if task_id.lower() in prior_ids:
            reason = "existing_binding"
        elif task.get("status") == "Work":
            reason = "already_work"
        elif task.get("status") != "Wait":
            reason = "other_status"
        else:
            result["transitions"].append({
                "task_id": task_id, "entity_id": identity["entity_id"],
                "pipeline_id": scope["pipeline_id"], "expected_status": "Wait", "status": "Work",
            })
            continue
        result["skipped"].append({"task_id": task_id, "reason": reason})
    if result["transitions"]:
        result.update(status="requires_atomic_status_transition", scope={
            key: scope[key] for key in ("origin", "project_id", "project_db", "module", "module_type", "pipeline_id", "account_id")
        })
    return result


def _claim_native_work_start(snapshot: dict[str, Any], member: dict[str, Any], commit_id: str) -> bool:
    """Durably claim one identity before mutation; existing claims never retry."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise OSError("Receipt directory unavailable")
    root = Path(local)
    if not root.is_absolute():
        raise OSError("Receipt directory unavailable")
    identity = member["cgt_identity"]
    key_data = {"origin": snapshot["origin"], "account": _id(snapshot["account_id"]).lower(),
                "project": _id(snapshot["project"]["id"]).lower(),
                "task": _id(member["cgt_task_id"]).lower(),
                "entity": _id(identity["entity_id"]).lower(), "pipeline": _id(identity["pipeline_id"]).lower()}
    digest = hashlib.sha256(json.dumps(key_data, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def ensure_directory(path: Path) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            path.mkdir()
            info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise OSError("Receipt directory is not safe")

    # LOCALAPPDATA is supplied by the operating system; never follow a link in
    # either dedicated child directory, including a pre-existing reparse point.
    info = root.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise OSError("Receipt root is not safe")
    app_dir = root / "HMB_GP_Production"
    ensure_directory(app_dir)
    receipts = app_dir / "cgt-work-start-receipts"
    ensure_directory(receipts)
    filename = receipts / (digest + ".json")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(filename, flags, 0o600)
    except FileExistsError:
        return False
    payload = json.dumps({"schema": "hmb-cgt-start-claim-v1", "identity_sha256": digest,
                          "commit_sha256": hashlib.sha256(commit_id.encode("utf-8")).hexdigest(),
                          "state": "attempted"}, separators=(",", ":")).encode("ascii")
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return True


def _native_start_own_wait(request: dict[str, Any]) -> dict[str, Any]:
    """One-shot native update after explicit commit; no compare-and-set guarantee."""
    project = request.get("project_id")
    previous = request.get("previous_binding")
    committed = request.get("committed_binding")
    commit_id = request.get("commit_request_id")
    selected = request.get("cgt_project_id")
    include_bound_wait = request.get("include_bound_wait", False)
    if (not isinstance(project, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project)
            or not isinstance(commit_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", commit_id)
            or not isinstance(previous, dict) or not isinstance(committed, dict)
            or type(include_bound_wait) is not bool):
        raise ValueError("INVALID_BINDING")
    old_members, members = previous.get("members", []), committed.get("members", [])
    if (not isinstance(old_members, list) or not isinstance(members, list)
            or len(old_members) > 5 or len(members) > 5
            or any(not isinstance(item, dict) for item in [*old_members, *members])):
        raise ValueError("INVALID_BINDING")
    live_members = [row for row in members if row.get("origin") == "cgt"]
    if not live_members:
        return {"schema": WORK_START_RESULT_SCHEMA, "version": 1, "status": "completed",
                "commit_request_id": commit_id, "tasks": [], "observed_tasks": [],
                "updated_count": 0, "already_work_count": 0, "skipped_count": 0,
                "failed_count": 0, "atomic_compare_and_set": False}
    scope = committed.get("cgt_scope") or {}
    if not isinstance(scope, dict) or scope.get("module") != "shot" or scope.get("module_type") != "task":
        raise ValueError("INVALID_BINDING")
    project_guid = _id(scope.get("project_id"))
    if selected is not None and (not isinstance(selected, str) or selected.lower() != project_guid.lower()):
        raise ValueError("SOURCE_CHANGED")
    old_ids = {_id(row.get("cgt_task_id")).lower() for row in old_members if row.get("origin") == "cgt"}
    live_ids = [_id(row.get("cgt_task_id")).lower() for row in live_members]
    if len(live_ids) != len(set(live_ids)):
        raise ValueError("INVALID_BINDING")

    def after_read(tw, snapshot, start_one):
        if (snapshot.get("status") != "ready" or snapshot.get("tls_verified") is not True
                or snapshot.get("hostname_verified") is not True or snapshot.get("can_bind") is not True
                or snapshot.get("truncated") is not False):
            raise ValueError("SOURCE_CHANGED")
        rows = {row["task_id"].lower(): row for row in snapshot.get("tasks", [])}
        # Status can change since the committed UI snapshot; identity, owner,
        # source name and scope cannot. Preserve the current-status check below.
        checked_members = []
        for member in members:
            item = dict(member)
            if item.get("origin") == "cgt":
                row = rows.get(_id(item.get("cgt_task_id")).lower())
                if row is None:
                    raise ValueError("SOURCE_CHANGED")
                item["status"] = row["status"]
            checked_members.append(item)
        verify_binding({**committed, "members": checked_members}, project, snapshot)
        db, account = snapshot["project"]["database"], snapshot["account_id"]
        fields = ["task.id", "shot.id", "eps.entity", "shot.entity", "pipeline.id", "pipeline.entity", "task.account_id", "task.artist", "task.status"]

        observed_tasks = {}
        def current_status(member):
            task_id = _id(member["cgt_task_id"])
            filters = [["task.account_id", "has", account], "and", ["pipeline.entity", "=", "AI_Shot"], "and", ["task.id", "in", [task_id]]]
            ids = tw.task.get_id(db, "shot", filters, limit="200", start_num="0")
            if not isinstance(ids, list) or len(ids) != 1 or _id(ids[0]).lower() != task_id.lower():
                raise ValueError("SOURCE_CHANGED")
            data = tw.task.get(db, "shot", ids, fields, limit="200")
            if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
                raise ValueError("SOURCE_CHANGED")
            row, identity = data[0], member.get("cgt_identity")
            if (not isinstance(identity, dict) or _id(row.get("task.id")).lower() != task_id.lower()
                    or _id(row.get("shot.id")).lower() != _id(identity.get("entity_id")).lower()
                    or _id(row.get("pipeline.id")).lower() != _id(identity.get("pipeline_id")).lower()
                    or row.get("pipeline.entity") != "AI_Shot"
                    or account.lower() not in _owners(row.get("task.account_id"))
                    or _text(row.get("shot.entity")) != member.get("source_name")
                    or _text(row.get("task.artist")) != member.get("artist")):
                raise ValueError("SOURCE_CHANGED")
            status = _text(row.get("task.status"))
            observed_tasks[task_id.lower()] = {"task_id": task_id, "identity": dict(identity),
                "source_name": member["source_name"], "artist": member["artist"], "status": status}
            return status

        outcomes = []
        stopped = False
        for member in live_members:
            task_id = _id(member["cgt_task_id"])
            if task_id.lower() in old_ids and not include_bound_wait:
                outcomes.append({"task_id": task_id, "outcome": "existing_binding"})
                continue
            if stopped:
                outcomes.append({"task_id": task_id, "outcome": "not_attempted"})
                continue
            try:
                status = current_status(member)
            except Exception:
                outcomes.append({"task_id": task_id, "outcome": "read_failed"})
                stopped = True
                continue
            if status != "Wait":
                outcomes.append({"task_id": task_id, "outcome": "already_work" if status == "Work" else "other_status"})
                continue
            try:
                claimed = _claim_native_work_start(snapshot, member, commit_id)
            except Exception:
                outcomes.append({"task_id": task_id, "outcome": "receipt_unavailable"})
                stopped = True
                continue
            if not claimed:
                outcomes.append({"task_id": task_id, "outcome": "prior_write_unconfirmed"})
                continue
            acknowledged = False
            try:
                acknowledged = start_one(task_id) is True
            except Exception:
                pass
            try:
                observed = current_status(member)
            except Exception:
                observed = None
            if acknowledged and observed == "Work":
                outcomes.append({"task_id": task_id, "outcome": "confirmed_work"})
            else:
                outcomes.append({"task_id": task_id, "outcome": "write_unconfirmed"})
                stopped = True
        updated = sum(row["outcome"] == "confirmed_work" for row in outcomes)
        already = sum(row["outcome"] == "already_work" for row in outcomes)
        failed = sum(row["outcome"] in {"read_failed", "receipt_unavailable", "write_unconfirmed", "prior_write_unconfirmed"} for row in outcomes)
        skipped = len(outcomes) - updated - already - failed
        status = ("unknown" if any(row["outcome"] in {"write_unconfirmed", "prior_write_unconfirmed"} for row in outcomes)
                  else "partial" if failed and updated else "failed" if failed else "completed")
        return {"schema": WORK_START_RESULT_SCHEMA, "version": 1, "status": status,
                "commit_request_id": commit_id, "tasks": outcomes, "observed_tasks": list(observed_tasks.values()),
                "updated_count": updated, "already_work_count": already, "skipped_count": skipped,
                "failed_count": failed, "atomic_compare_and_set": False}

    result = _read_own({"project_id": project, "cgt_project_id": project_guid}, _after_read=after_read)
    if result.get("schema") != WORK_START_RESULT_SCHEMA:
        return {"schema": WORK_START_RESULT_SCHEMA, "version": 1, "status": "failed",
                "commit_request_id": commit_id, "tasks": [], "observed_tasks": [],
                "updated_count": 0, "already_work_count": 0, "skipped_count": 0,
                "failed_count": len(live_members), "atomic_compare_and_set": False}
    return result


def start_own_wait_after_commit(project_id: str, *, previous_binding: dict[str, Any],
                                committed_binding: dict[str, Any], commit_request_id: str,
                                cgt_project_id: str | None = None,
                                include_bound_wait: bool = False) -> dict[str, Any]:
    """Run the explicitly committed native start once in an isolated child.

    Call only once after a successful explicit local commit; save/reopen must
    never invoke this operation. The child durably claims each Task before its
    single write attempt and does not retry an unconfirmed claim automatically.
    Only an explicit user reconfirm may set include_bound_wait=True; the child
    still requires a freshly verified Wait status and the same durable claim.
    """
    request = {"project_id": project_id, "previous_binding": previous_binding,
               "committed_binding": committed_binding, "commit_request_id": commit_request_id,
               "cgt_project_id": cgt_project_id, "include_bound_wait": include_bound_wait}
    if (not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project_id)
            or not isinstance(commit_request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", commit_request_id)
            or not isinstance(previous_binding, dict) or not isinstance(committed_binding, dict)
            or type(include_bound_wait) is not bool
            or (cgt_project_id is not None and (not isinstance(cgt_project_id, str) or not _GUID.fullmatch(cgt_project_id)))):
        raise ValueError("INVALID_BINDING")
    encoded = json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 65536:
        raise ValueError("INVALID_BINDING")
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP", "HMB_CGT_SDK_PATH"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", NO_PROXY="127.0.0.1,localhost,::1")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    uncertain = {"schema": WORK_START_RESULT_SCHEMA, "version": 1, "status": "unknown",
                 "commit_request_id": commit_request_id, "tasks": [], "observed_tasks": [],
                 "updated_count": 0, "already_work_count": 0, "skipped_count": 0,
                 "failed_count": 0, "atomic_compare_and_set": False}
    try:
        result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--start-own-wait"],
            input=encoded, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=90, env=env, **options)
        if result.returncode or len(result.stdout) > 65536:
            return uncertain
        data = json.loads(result.stdout)
        if (not isinstance(data, dict) or data.get("schema") != WORK_START_RESULT_SCHEMA
                or data.get("version") != 1 or data.get("commit_request_id") != commit_request_id
                or data.get("status") not in {"completed", "partial", "failed", "unknown"}
                or data.get("atomic_compare_and_set") is not False or not isinstance(data.get("tasks"), list)
                or len(data["tasks"]) > 5 or not isinstance(data.get("observed_tasks"), list)
                or len(data["observed_tasks"]) > 5
                or any(type(data.get(key)) is not int or not 0 <= data[key] <= 5 for key in
                       ("updated_count", "already_work_count", "skipped_count", "failed_count"))):
            return uncertain
        for row in data["tasks"]:
            if (not isinstance(row, dict) or set(row) != {"task_id", "outcome"}
                    or not isinstance(row["task_id"], str) or not _GUID.fullmatch(row["task_id"])
                    or row["outcome"] not in {"existing_binding", "not_attempted", "read_failed", "already_work", "other_status", "confirmed_work", "write_unconfirmed", "receipt_unavailable", "prior_write_unconfirmed"}):
                return uncertain
        for row in data["observed_tasks"]:
            if (not isinstance(row, dict) or set(row) != {"task_id", "identity", "source_name", "artist", "status"}
                    or not isinstance(row["task_id"], str) or not _GUID.fullmatch(row["task_id"])
                    or not isinstance(row["identity"], dict)
                    or any(not isinstance(row[key], str) or len(row[key]) > 256 for key in ("source_name", "artist", "status"))):
                return uncertain
        return data
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError):
        return uncertain


def _read_own(request: dict[str, Any], *, _after_read=None) -> dict[str, Any]:
    project_key = request.get("project_id", "")
    binding = request.get("binding")
    selected_project_id = request.get("cgt_project_id")
    if (not isinstance(project_key, str) or (project_key and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project_key))
            or (binding is not None and not project_key)):
        return _failure("SELECT_GP_PROJECT")
    if selected_project_id is not None and (not isinstance(selected_project_id, str) or not _GUID.fullmatch(selected_project_id)):
        return _failure("PROJECT_UNAVAILABLE")
    sdk = Path(os.environ.get("HMB_CGT_SDK_PATH") or "C:/CgTeamWork_v7/bin/base")
    if not (sdk / "cgtw2.py").is_file():
        return _failure("SDK_UNAVAILABLE")
    sys.path.insert(0, str(sdk))
    socket.setdefaulttimeout(5)
    import cgtw2
    import websocket
    from requests.adapters import HTTPAdapter
    websocket.setdefaulttimeout(5)
    # A no-argument tw() retrieves the normal client session over its supported
    # local transport. Direct password/API-key login is never used here.
    tw = cgtw2.tw()
    account = _id(tw.login.account_id())
    if not tw.login.is_login():
        return _failure("LOGIN_REQUIRED")
    origin = "https://" + str(cgtw2.G_tw_http_ip)
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        return _failure("INVALID_ORIGIN")
    trust = json.loads((Path(__file__).parent / "resources/cgt/server-trust.json").read_text("utf-8"))
    context = ssl.create_default_context()
    if origin == trust.get("origin"):
        pem = trust.get("root_ca_pem", "")
        if hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest() != TRUST_ROOT_SHA256:
            return _failure("TRUST_CHANGED")
        context.load_verify_locations(cadata=pem)

    class VerifiedAdapter(HTTPAdapter):
        def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
            kwargs["ssl_context"] = context
            return super().init_poolmanager(connections, maxsize, block=block, **kwargs)

    session = cgtw2.G_cgtw_session
    session.trust_env = False
    session.mount(origin + "/", VerifiedAdapter())
    original_post = session.post
    allowed = {("account", "get"), ("project", "get_id"), ("project", "get"),
               ("task", "fields_and_str"), ("task", "get_id"), ("task", "get")}
    active_write = None

    def verified_post(url, *args, **kwargs):
        if url != origin + "/api.php":
            raise ValueError("INVALID_ORIGIN")
        operation = json.loads(kwargs.get("data", {}).get("data", "{}"))
        if (operation.get("controller"), operation.get("method")) not in allowed:
            if not (active_write and not active_write.get("used") and operation.get("controller") == "task"
                    and operation.get("method") == "update_task_status"
                    and operation.get("db") == active_write["db"]
                    and operation.get("module") == "shot"
                    and operation.get("task_id_array") == [active_write["task_id"]]
                    and operation.get("status") == "Work"
                    and operation.get("dom_array") == []
                    and operation.get("retake_pipeline_id_array") == []):
                raise ValueError("READ_SCOPE_REJECTED")
            # The vendor SDK can retry after a token error. One claim permits
            # only one network POST, even if that first call raises or times out.
            active_write["used"] = True
        kwargs.update(verify=True, timeout=(5, 10), allow_redirects=False)
        response = original_post(url, *args, **kwargs)
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("INVALID_ORIGIN")
        return response

    session.post = verified_post
    people = tw.account.get([account], ["account.id", "account.entity", "account.name"])
    if len(people) != 1 or people[0].get("account.id") != account:
        return _failure("LOGIN_REQUIRED")
    who = people[0]
    # Return the signed-in client's actual visible projects. A GP token only
    # chooses the initial default; a separate immutable CGT ID chooses a
    # browsing source. Database names always come from this authenticated read.
    ids = tw.project.get_id([])
    sources = tw.project.get(ids, ["project.id", "project.entity", "project.full_name", "project.database", "project.status"]) if ids else []
    projects = [{"id": _id(source["project.id"]), "entity": _text(source["project.entity"]),
                 "name": _text(source["project.full_name"]), "database": _text(source["project.database"]),
                 "status": _text(str(source.get("project.status") or ""))} for source in sources]
    if len({row["id"].lower() for row in projects}) != len(projects):
        return _failure("SOURCE_SCHEMA")
    candidates = [row for row in projects if (
        row["id"].lower() == selected_project_id.lower() if selected_project_id is not None
        else bool(project_key) and row["entity"].lower() == project_key.lower())]
    project = candidates[0] if len(candidates) == 1 else None
    result = {"schema": SCHEMA, "version": 1, "status": "ready", "origin": origin, "account_id": account,
              "account": _text(who["account.entity"]), "account_name": _text(who["account.name"]),
              "project": project, "projects": projects, "tasks": [], "truncated": False,
              "can_bind": bool(project and project_key and project["entity"].lower() == project_key.lower()),
              "tls_verified": True, "hostname_verified": True}
    if project is None:
        if selected_project_id is not None or binding is not None:
            result["status"] = "PROJECT_UNAVAILABLE"
        return result
    if binding is not None and (not result["can_bind"]
            or (binding.get("cgt_scope") or {}).get("project_id") != project["id"]):
        result.update(status="SOURCE_CHANGED", can_bind=False)
        return result
    def task_failure(code: str) -> dict[str, Any]:
        # Keep the authenticated project picker usable when a browsed
        # project's Shot schema or own-task read is unavailable.
        return {**result, "status": code, "tasks": [], "can_bind": False}

    db = project["database"]
    needed = ["task.id", "shot.id", "eps.entity", "shot.entity", "pipeline.id", "pipeline.entity", "task.account_id", "task.artist", "task.status"]
    fields = {item["sign"] for item in tw.task.fields_and_str(db, "shot")}
    if not set(needed).issubset(fields):
        return task_failure("SOURCE_SCHEMA")
    # 'has' is the installed CGT plugin's own-task operator for the account
    # assignment field. Equality on this multi-account field returns no rows.
    query = [["task.account_id", "has", account], "and", ["pipeline.entity", "=", "AI_Shot"]]
    selected = [row.get("cgt_task_id") for row in (binding or {}).get("members", []) if row.get("origin") == "cgt"]
    if binding is not None:
        if not selected or len(selected) > 5:
            return task_failure("INVALID_BINDING")
        query += ["and", ["task.id", "in", [_id(item) for item in selected]]]
    tasks = []
    truncated = False
    for offset in range(0, MAX_TASKS + 1, 200):
        page = tw.task.get_id(db, "shot", query, limit="200", start_num=str(offset))
        if not isinstance(page, list) or len(page) > 200:
            return task_failure("SOURCE_SCHEMA")
        if offset >= MAX_TASKS:
            truncated = bool(page)
            break
        data = tw.task.get(db, "shot", page, needed, limit="200") if page else []
        if len(data) != len(page):
            return task_failure("SOURCE_CHANGED")
        for row in data:
            if account.lower() not in _owners(row["task.account_id"]) or row["pipeline.entity"] != "AI_Shot":
                return task_failure("OWNERSHIP_CHANGED")
            task_id = _id(row["task.id"])
            pipeline = _id(row["pipeline.id"])
            identity = {"entity_id": _id(row["shot.id"]), "task_id": task_id, "pipeline_id": pipeline}
            tasks.append({"task_id": task_id, "identity": identity, "source_name": _text(row["shot.entity"]),
                          "episode": _text(row["eps.entity"]), "pipeline_id": pipeline,
                          "artist": _text(row["task.artist"]), "status": _text(row["task.status"])})
        if len(page) < 200:
            break
    if len({row["task_id"] for row in tasks}) != len(tasks):
        return task_failure("SOURCE_CHANGED")
    tasks.sort(key=lambda row: (row["episode"], row["source_name"], row["task_id"]))
    result.update(tasks=tasks, truncated=truncated)
    if binding is not None:
        verify_binding(binding, project_key, result)
    if _after_read is not None:
        def start_one(task_id: str) -> Any:
            nonlocal active_write
            if active_write is not None:
                raise ValueError("READ_SCOPE_REJECTED")
            active_write = {"db": db, "task_id": _id(task_id)}
            try:
                return tw.task.update_task_status(db, "shot", [task_id], "Work", note="", image_list=[], retake_pipeline_id_list=[])
            finally:
                active_write = None
        return _after_read(tw, result, start_one)
    return result


_SAFE_FAILURE_CODES = frozenset({
    "SELECT_GP_PROJECT", "PROJECT_UNAVAILABLE", "SOURCE_SCHEMA", "SOURCE_CHANGED",
    "OWNERSHIP_CHANGED", "LOGIN_REQUIRED", "INVALID_ORIGIN", "TRUST_CHANGED",
    "READ_SCOPE_REJECTED", "INVALID_BINDING", "SDK_UNAVAILABLE", "TIMEOUT", "TLS_REJECTED",
    "ACCESS_DENIED", "RATE_LIMITED", "SERVER_UNAVAILABLE", "CONNECTION_FAILED", "REQUEST_REJECTED",
})


def _classify_read_failure(exc: BaseException) -> str:
    """Classify without returning arbitrary SDK/server exception text."""
    if isinstance(exc, ValueError) and len(exc.args) == 1 and isinstance(exc.args[0], str):
        if exc.args[0] in _SAFE_FAILURE_CODES:
            return exc.args[0]
    if isinstance(exc, ssl.SSLError):
        return "TLS_REJECTED"
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
        return "TIMEOUT"
    transport_types = set()
    for cls in type(exc).__mro__:
        if cls.__module__.startswith(("requests.exceptions", "urllib3.exceptions")):
            transport_types.add(cls.__name__)
            if cls.__name__ == "SSLError":
                return "TLS_REJECTED"
            if cls.__name__ in {"Timeout", "ConnectTimeout", "ReadTimeout"}:
                return "TIMEOUT"
    if "HTTPError" in transport_types:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if type(status) is int:
            if status == 401:
                return "LOGIN_REQUIRED"
            if status == 403:
                return "ACCESS_DENIED"
            if status == 429:
                return "RATE_LIMITED"
            if 500 <= status <= 599:
                return "SERVER_UNAVAILABLE"
            if 400 <= status <= 499:
                return "REQUEST_REJECTED"
    if "ConnectionError" in transport_types:
        return "CONNECTION_FAILED"
    detail = str(exc).lower()
    for words, category in [
        (("certificate verify failed", "hostname mismatch", "certificate has expired", "sslerror"), "TLS_REJECTED"),
        (("please login", "not login", "token has expired", "account_id"), "LOGIN_REQUIRED"),
        (("timed out", "timeout"), "TIMEOUT"),
        (("cgt 계정", "cgt 샷", "본인 작업"), "SOURCE_CHANGED"),
    ]:
        if any(word in detail for word in words):
            return category
    return "SDK_UNAVAILABLE"


def _main(*, start_own_wait: bool = False) -> None:
    result = _failure("SDK_UNAVAILABLE")
    commit_id = ""
    try:
        source = sys.stdin.buffer.read(65537)
        if len(source) > 65536:
            raise ValueError("INVALID_BINDING")
        request = json.loads(source)
        if start_own_wait and isinstance(request, dict):
            candidate = request.get("commit_request_id")
            if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", candidate):
                commit_id = candidate
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = _native_start_own_wait(request) if start_own_wait else _read_own(request)
    except Exception as exc:
        # Vendor exceptions can include request/session material. Classify in
        # memory; never print or persist their text or traceback.
        result = ({"schema": WORK_START_RESULT_SCHEMA, "version": 1, "status": "unknown",
                   "commit_request_id": commit_id, "tasks": [], "observed_tasks": [],
                   "updated_count": 0, "already_work_count": 0, "skipped_count": 0,
                   "failed_count": 0, "atomic_compare_and_set": False}
                  if start_own_wait else _failure(_classify_read_failure(exc)))
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__" and sys.argv[1:] in (["--read-own"], ["--start-own-wait"]):
    _main(start_own_wait=sys.argv[1:] == ["--start-own-wait"])
