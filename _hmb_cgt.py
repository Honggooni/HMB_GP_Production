"""Read-only CGT task discovery through the installed, signed-in CGT client.

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
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "hmb-cgt-own-tasks"
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


def _read_own(request: dict[str, Any]) -> dict[str, Any]:
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

    def verified_post(url, *args, **kwargs):
        if url != origin + "/api.php":
            raise ValueError("INVALID_ORIGIN")
        operation = json.loads(kwargs.get("data", {}).get("data", "{}"))
        if (operation.get("controller"), operation.get("method")) not in allowed:
            raise ValueError("READ_SCOPE_REJECTED")
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
    return result


def _main() -> None:
    result = _failure("SDK_UNAVAILABLE")
    try:
        source = sys.stdin.buffer.read(65537)
        if len(source) > 65536:
            raise ValueError("INVALID_BINDING")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = _read_own(json.loads(source))
    except Exception as exc:
        # Vendor exceptions can include request/session material. Classify in
        # memory; never print or persist their text or traceback.
        detail = str(exc).lower()
        code = "SDK_UNAVAILABLE"
        for words, category in [
            (("certificate verify failed", "hostname mismatch", "certificate has expired", "sslerror"), "TLS_REJECTED"),
            (("please login", "not login", "token has expired", "account_id"), "LOGIN_REQUIRED"),
            (("timed out", "timeout"), "TIMEOUT"),
            (("cgt 계정", "cgt 샷", "본인 작업"), "SOURCE_CHANGED"),
        ]:
            if any(word in detail for word in words):
                code = category
                break
        result = _failure(code)
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__" and sys.argv[1:] == ["--read-own"]:
    _main()
