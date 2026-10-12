"""Local, Task-ID-linked production evidence. Never submits or edits policy."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

SCHEMA = "hmb-generation-casecard"
VERSION = 1
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_HASH_FILE_BYTES = 64 * 1024 * 1024
_LOCK = threading.RLock()
SETTINGS = ("model_id", "task", "input_mode", "resolution", "ratio", "duration",
            "generate_audio", "watermark", "output_format", "return_last_frame",
            "execution_expires_after", "priority", "seed", "camera_fixed")
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_HASH = re.compile(r"[0-9a-f]{64}")
_SYNC_STATES = {"pending", "synced", "failed", "unsupported", "login_required"}


def _public_id(value: Any) -> str:
    text = str(value or "")
    return text if _TASK_ID.fullmatch(text) else ""


def _hash(value: Any) -> str:
    text = str(value or "").lower()
    return text if _HASH.fullmatch(text) else ""


def _public_text(value: Any, limit: int = 128) -> str:
    text = str(value or "")
    if (len(text) > limit or re.search(r"https?://|data:|Bearer\s|[\\/?#\x00-\x1f]", text, re.I)):
        return ""
    return text


def _public_number(value: Any) -> int | float | None:
    # JSON integers need not fit a float. Reject out-of-range values before
    # isfinite converts them, so optional evidence cannot fail with overflow.
    return value if type(value) in {int, float} and abs(value) <= 10**15 and math.isfinite(value) else None


def public_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Supplemental evidence only. Broker stored prompt stays authoritative.

    This projection never carries a local path, source URL, credential, prompt
    text, arbitrary diagnostics key or current-node settings into an old Task.
    """
    if "inputs" not in record and "client_prompt_sha256" in record:
        flat = record.get("build") if isinstance(record.get("build"), dict) else {}
        record = {**record, "prompt_sha256": record.get("client_prompt_sha256"),
                  "inputs": {"settings": record.get("settings"), "references": record.get("references"),
                             "generation_origin": record.get("shot")},
                  "build": {"library_version": flat.get("library_version"), "channel": flat.get("channel"),
                            "runtime": {"fingerprint_sha256": flat.get("runtime_fingerprint_sha256")},
                            "package": {"build_fingerprint_sha256": flat.get("build_fingerprint_sha256")},
                            "policy": {"policy_version": flat.get("policy_version"),
                                       "policy_pair_sha256": flat.get("policy_pair_sha256"),
                                       "envelope_sha256": flat.get("policy_envelope_sha256"),
                                       "signature_status": flat.get("policy_signature_status")}}}
    inputs = record.get("inputs") if isinstance(record.get("inputs"), dict) else {}
    build = record.get("build") if isinstance(record.get("build"), dict) else {}
    references = []
    raw_references = inputs.get("references")
    for row in (raw_references if isinstance(raw_references, list) else [])[:96]:
        if not isinstance(row, dict):
            continue
        reference = {key: _public_text(row.get(key)) for key in ("role", "kind", "content_status")}
        reference.update({key: _hash(row.get(key)) for key in ("source_identity_sha256", "content_sha256")})
        for key in ("index", "bytes"):
            value = _public_number(row.get(key))
            if value is not None:
                reference[key] = value
        references.append(reference)
    settings = {}
    for key in SETTINGS:
        if not isinstance(inputs.get("settings"), dict) or key not in inputs["settings"]:
            continue
        value = inputs["settings"][key]
        if type(value) in {bool, type(None)} or _public_number(value) is not None:
            settings[key] = value
        elif isinstance(value, str):
            cleaned = _public_text(value, 256)
            if cleaned:
                settings[key] = cleaned
    origin = inputs.get("generation_origin") if isinstance(inputs.get("generation_origin"), dict) else {}
    shot = {key: _public_id(origin.get(key)) for key in ("channel_uuid", "shot_uuid", "source_node_instance_id")}
    if type(origin.get("number")) is int and 1 <= origin["number"] <= 5:
        shot["number"] = origin["number"]
    policy = build.get("policy") if isinstance(build.get("policy"), dict) else {}
    runtime = build.get("runtime") if isinstance(build.get("runtime"), dict) else {}
    package = build.get("package") if isinstance(build.get("package"), dict) else {}
    public_build = {"library_version": _public_text(build.get("library_version")),
                    "channel": _public_id(build.get("channel")),
                    "runtime_fingerprint_sha256": _hash(runtime.get("fingerprint_sha256")),
                    "build_fingerprint_sha256": _hash(package.get("build_fingerprint_sha256")),
                    "policy_version": _public_text(policy.get("policy_version")),
                    "policy_pair_sha256": _hash(policy.get("policy_pair_sha256")),
                    "policy_envelope_sha256": _hash(policy.get("envelope_sha256")),
                    "policy_signature_status": _public_id(policy.get("signature_status"))}
    raw_observation = record.get("agent_observation")
    observation = {}
    if isinstance(raw_observation, dict):
        observation = {key: _public_id(raw_observation.get(key)) for key in
                       ("schema", "run_id", "sampling_policy", "status", "agent_status", "native_input_status")}
        observation["machine_sha256"] = _hash(raw_observation.get("machine_sha256"))
        for field in ("coverage", "skips", "groups"):
            rows = []
            raw_rows = raw_observation.get(field)
            for row in (raw_rows if isinstance(raw_rows, list) else [])[:256]:
                if not isinstance(row, dict):
                    continue
                item = {key: _public_id(row.get(key)) for key in
                        ("kind", "observation_role", "video_uid", "source_uid", "bundle_run_id", "sample_group_id",
                         "status", "reason", "pts_status", "sample_reason", "alignment_status") if key in row}
                token = str(row.get("media_token") or "")
                if re.fullmatch(r"@(image|video)[1-9][0-9]{0,2}", token):
                    item["media_token"] = token
                for key in ("requested_seek_seconds", "decoded_pts_seconds", "requested_source_frame", "decode_seek_seconds"):
                    if key in row:
                        item[key] = _public_number(row[key])
                if "normalized_pts_seconds" in row:
                    pts = row["normalized_pts_seconds"]
                    item["normalized_pts_seconds"] = ([_public_number(v) for v in pts[:8]]
                                                      if isinstance(pts, list) else _public_number(pts))
                if isinstance(row.get("media_tokens"), list):
                    item["media_tokens"] = [v for v in row["media_tokens"][:8]
                                             if isinstance(v, str) and re.fullmatch(r"@(image|video)[1-9][0-9]{0,2}", v)]
                rows.append(item)
            observation[field] = rows
        budget = raw_observation.get("budget_summary")
        observation["budget_summary"] = {key: _public_number(budget.get(key)) for key in
            ("attachment_limit", "image_limit", "encoded_byte_limit", "preparation_seconds_limit", "attachments_prepared",
             "attachments_delivered", "encoded_bytes_prepared", "elapsed_seconds") if key in budget} if isinstance(budget, dict) else {}
    return {"schema": SCHEMA, "version": 1,
            "case_id": _hash(record.get("case_id")), "input_evidence_sha256": _hash(record.get("input_evidence_sha256")),
            "client_prompt_sha256": _hash(record.get("prompt_sha256")), "build": public_build,
            "shot": shot, "settings": settings, "references": references, "agent_observation": observation}


def bind_task_origin(task_id: str, origin: str, *, root: Path | str | None = None) -> None:
    """Private credential-free routing metadata, never a public casecard field."""
    if not _public_id(task_id):
        raise ValueError("Invalid Task ID.")
    parsed = urlsplit(origin)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("Invalid Task origin.")
    canonical = origin.rstrip("/")
    path = review_root(root) / "task-origins" / (hashlib.sha256(task_id.encode()).hexdigest() + ".json")
    with _LOCK:
        previous = _read(path)
        if path.exists() and previous is None:
            raise ValueError("Task origin record is unreadable.")
        if previous and (previous.get("task_id") != task_id or previous.get("origin") != canonical):
            raise ValueError("Task origin is immutable.")
        if not previous:
            _write(path, {"schema": "hmb-private-task-origin", "version": 1,
                          "task_id": task_id, "origin": canonical})


def task_origin(task_id: str, *, root: Path | str | None = None) -> str:
    if not _public_id(task_id):
        return ""
    record = _read(review_root(root) / "task-origins" / (hashlib.sha256(task_id.encode()).hexdigest() + ".json"))
    return str(record.get("origin") or "") if record and record.get("schema") == "hmb-private-task-origin" and record.get("task_id") == task_id else ""


def mark_server_sync(task_id: str, *, status: str, evidence_sha256: str = "", reason: str = "",
                     root: Path | str | None = None) -> dict[str, Any] | None:
    if status not in _SYNC_STATES:
        raise ValueError("Invalid sync state.")
    with _LOCK:
        record = read_case(task_id, root=root)
        if not record:
            return None
        record["server_sync"] = {"status": status, "evidence_sha256": _hash(evidence_sha256),
                                 "reason": _public_id(reason), "updated_at": _now()}
        _write(review_root(root) / "cases" / (record["case_id"] + ".json"), record)
        return deepcopy(record["server_sync"])


def mark_review_sync(task_id: str, review_id: str, *, status: str, reason: str = "",
                     root: Path | str | None = None) -> None:
    if status not in _SYNC_STATES:
        raise ValueError("Invalid sync state.")
    with _LOCK:
        record = read_case(task_id, root=root)
        if not record:
            return
        for row in record.get("reviews", []):
            if row.get("review_id") == review_id:
                row["server_sync"] = {"status": status, "reason": _public_id(reason), "updated_at": _now()}
                _write(review_root(root) / "cases" / (record["case_id"] + ".json"), record)
                return


def cache_server_feedback(task_id: str, rows: list[dict[str, Any]], *, has_more: bool = False,
                          root: Path | str | None = None) -> dict[str, Any]:
    """Read-only web feedback projection; never replaces locally authored notes."""
    if not _public_id(task_id):
        raise ValueError("Invalid Task ID.")
    cleaned = []
    seen = set()
    for row in rows[:100]:
        if (not isinstance(row, dict) or row.get("task_id", task_id) != task_id
                or type(row.get("score")) is not int or row["score"] not in {1, 2, 3, 4, 5}
                or row.get("category") not in {"identity", "motion", "camera", "material", "environment", "other"}):
            raise ValueError("Invalid server feedback.")
        identity = _public_id(row.get("client_review_id") or row.get("review_id") or row.get("id"))
        if not identity or identity in seen:
            continue
        seen.add(identity)
        cleaned.append({"review_id": identity, "score": row["score"], "category": row["category"],
                        "note": str(row.get("note") or "")[:4000], "created_at": _public_text(row.get("created_at"), 80),
                        "input_evidence_sha256": _hash(row.get("input_evidence_sha256")),
                        "source": "broker_owned_task_feedback", "authority": "untrusted_evidence_only"})
    snapshot = {"schema": "hmb-server-task-feedback", "version": 1, "task_id": task_id,
                "items": cleaned, "has_more": bool(has_more), "retrieved_at": _now()}
    with _LOCK:
        _write(review_root(root) / "server-feedback" / (hashlib.sha256(task_id.encode()).hexdigest() + ".json"), snapshot)
    return deepcopy(snapshot)


def read_server_feedback(task_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    if not _public_id(task_id):
        return None
    record = _read(review_root(root) / "server-feedback" / (hashlib.sha256(task_id.encode()).hexdigest() + ".json"))
    return deepcopy(record) if record and record.get("task_id") == task_id and record.get("schema") == "hmb-server-task-feedback" else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def review_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "HMB_GP_Production" / "reviews" / "v1"


def _write(path: Path, value: dict[str, Any]) -> None:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError("Casecard exceeds its bounded local record size.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAX_RECORD_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def describe_reference(value: Any, *, role: str, index: int) -> dict[str, Any]:
    """Fingerprint the authored source, before uploads replace its identity."""
    raw = value
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("url") or raw.get("path") or ""
    elif not isinstance(raw, (str, Path)):
        raw = getattr(raw, "value", "")
    text = str(raw or "")
    result: dict[str, Any] = {"role": role, "index": index,
                              "source_identity_sha256": hashlib.sha256(text.encode()).hexdigest()}
    if text.startswith("data:"):
        result.update(kind="inline", content_status="source_identity_only")
        return result
    parsed = urlsplit(text)
    if parsed.scheme in {"http", "https"}:
        # Signed query strings and private URLs never enter the casecard.
        result.update(kind="remote", content_status="not_downloaded")
        return result
    path = Path(text)
    try:
        if path.is_file():
            stat = path.stat()
            result.update(kind="local", path=str(path.resolve()), bytes=stat.st_size,
                          mtime_ns=stat.st_mtime_ns, content_status="size_limit")
            if stat.st_size <= MAX_HASH_FILE_BYTES:
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                if path.stat().st_mtime_ns == stat.st_mtime_ns and path.stat().st_size == stat.st_size:
                    result.update(content_sha256=digest.hexdigest(), content_status="full_sha256")
                else:
                    result["content_status"] = "changed_while_reading"
            return result
    except (OSError, ValueError):
        pass
    result.update(kind="unresolved", content_status="unavailable")
    return result


def capture_inputs(params: dict[str, Any]) -> dict[str, Any]:
    references = []
    for role, field in (("image", "reference_images"), ("video", "video_references"),
                        ("audio", "reference_audio"), ("first_frame", "first_frame"),
                        ("last_frame", "last_frame")):
        raw = params.get(field)
        values = raw if isinstance(raw, (list, tuple)) else [raw] if raw else []
        references.extend(describe_reference(value, role=role, index=index)
                          for index, value in enumerate(values[:32]))
    settings = {name: params[name] for name in SETTINGS
                if name in params and isinstance(params[name], (str, bool, int, float, type(None)))}
    return {"settings": settings, "references": references,
            "generation_origin": deepcopy(params.get("_hmb_generation_origin") or {})}


def start_case(client_request_id: str, inputs: dict[str, Any], submitted_prompt: str,
               diagnostics: dict[str, Any], observation: dict[str, Any],
               *, root: Path | str | None = None) -> str:
    if not client_request_id or len(client_request_id) > 256:
        raise ValueError("A bounded client request ID is required.")
    base = review_root(root)
    case_id = hashlib.sha256(client_request_id.encode()).hexdigest()
    with _LOCK:
        path = base / "cases" / (case_id + ".json")
        previous = _read(path)
        if previous is not None:
            return case_id  # Recovery cannot replace the original evidence.
        prompt = str(submitted_prompt)
        record = {"schema": SCHEMA, "version": VERSION, "case_id": case_id,
                  "client_request_id": client_request_id, "task_id": "",
                  "created_at": _now(), "updated_at": _now(), "status": "prepared",
                  "inputs": deepcopy(inputs), "submitted_prompt": prompt[:50000],
                  "prompt_truncated": len(prompt) > 50000,
                  "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                  "build": deepcopy(diagnostics), "agent_observation": deepcopy(observation),
                  "stage_elapsed_seconds": {}, "reviews": []}
        record["input_evidence_sha256"] = _digest({key: record[key] for key in
            ("inputs", "prompt_sha256", "build", "agent_observation")})
        _write(path, record)
        _write(base / "tasks" / (hashlib.sha256(client_request_id.encode()).hexdigest() + ".json"),
               {"task_id": client_request_id, "case_id": case_id})
    return case_id


def read_case(task_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    if not task_id or len(task_id) > 256:
        return None
    base = review_root(root)
    alias = _read(base / "tasks" / (hashlib.sha256(task_id.encode()).hexdigest() + ".json"))
    if not alias or alias.get("task_id") != task_id:
        return None
    case_id = str(alias.get("case_id") or "")
    if len(case_id) != 64 or any(c not in "0123456789abcdef" for c in case_id):
        return None
    result = _read(base / "cases" / (case_id + ".json"))
    if not result or result.get("schema") != SCHEMA or result.get("case_id") != case_id:
        return None
    if task_id not in {result.get("task_id"), result.get("client_request_id")}:
        return None
    return result


def update_case(task_id: str, *, case_id: str = "", status: str = "",
                stage_elapsed_seconds: dict[str, float] | None = None,
                output: Any = None, root: Path | str | None = None) -> dict[str, Any] | None:
    if not task_id or len(task_id) > 256:
        return None
    base = review_root(root)
    with _LOCK:
        record = read_case(task_id, root=base)
        if record is None and case_id and len(case_id) == 64 and all(c in "0123456789abcdef" for c in case_id):
            candidate = _read(base / "cases" / (case_id + ".json"))
            # Bind the new authoritative ID only once; never attach a later render.
            if candidate and candidate.get("schema") == SCHEMA and candidate.get("task_id") in {"", task_id}:
                record = candidate
                record["task_id"] = task_id
        if record is None:
            return None  # Historical tasks cannot invent current inputs.
        if case_id != record["case_id"]:
            # A historical-task refresh knows its status, not that render's
            # original in-process timing. Keep recorded durations intact.
            stage_elapsed_seconds = None
        if status:
            record["status"] = str(status)[:80]
        if stage_elapsed_seconds is not None:
            record["stage_elapsed_seconds"] = {str(k)[:80]: round(max(0., float(v)), 4)
                for k, v in list(stage_elapsed_seconds.items())[:64] if _public_number(v) is not None}
        if output is not None:
            record["output"] = describe_reference(output, role="generated_video", index=0)
        record["updated_at"] = _now()
        _write(base / "cases" / (record["case_id"] + ".json"), record)
        _write(base / "tasks" / (hashlib.sha256(task_id.encode()).hexdigest() + ".json"),
               {"task_id": task_id, "case_id": record["case_id"]})
        return record


def save_review(task_id: str, *, score: int, category: str, note: str,
                root: Path | str | None = None) -> dict[str, Any]:
    if isinstance(score, bool) or score not in {1, 2, 3, 4, 5}:
        raise ValueError("Rating must be 1 through 5.")
    if category not in {"identity", "motion", "camera", "material", "environment", "other"}:
        raise ValueError("Unknown feedback category.")
    base = review_root(root)
    with _LOCK:
        record = read_case(task_id, root=base)
        if record is None:
            raise ValueError("This task has no recorded input evidence on this PC.")
        review = {"review_id": uuid4().hex, "created_at": _now(), "task_id": task_id,
                  "score": score, "category": category, "note": str(note).strip()[:4000],
                  "input_evidence_sha256": record["input_evidence_sha256"],
                  "policy_action": "proposal_requires_human_review"}
        if len(record["reviews"]) >= 100:
            raise ValueError("This casecard already contains 100 reviews.")
        record["reviews"].append(review)
        record["updated_at"] = _now()
        _write(base / "cases" / (record["case_id"] + ".json"), record)
        return review


def export_feedback_summary(*, root: Path | str | None = None) -> dict[str, Any]:
    cases = []
    for path in sorted((review_root(root) / "cases").glob("*.json")):
        record = _read(path)
        if record and record.get("schema") == SCHEMA and record.get("reviews"):
            cases.append({"task_id": record.get("task_id") or record.get("client_request_id"),
                          "case_id": record["case_id"], "input_evidence_sha256": record["input_evidence_sha256"],
                          "library_version": record.get("build", {}).get("library_version"),
                          "reviews": record["reviews"]})
    return {"schema": "hmb-feedback-evidence-summary", "version": 1, "generated_at": _now(),
            "authority": "untrusted_evidence_only", "policy_action": "proposal_requires_human_review",
            "cases": cases}
