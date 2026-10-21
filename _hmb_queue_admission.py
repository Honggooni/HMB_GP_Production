"""Read-only maintenance admission grammar, separate from renderer readiness.

An admission document is not authority by itself. The authenticated Bridge must
issue and retain the exact object for this origin and credential epoch. Saved
header identities are audit/recovery data only; they never authorize a new POST.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

PATH = "/api/v1/maintenance-intake/capabilities"
SCHEMA = "hmb-maintenance-queue-only-capabilities-v1"
SOURCE_PREFIX = "hmb-queue-only-source://"
MAX_GENERATION = 9007199254740991
OPERATIONS = frozenset(("video", "only", "image", "draft_final"))
_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_TASK = re.compile(r"job-mybox-[a-f0-9]{32}\Z")


class QueueAdmissionError(ValueError):
    """A request was not submitted because its admission proof is invalid."""
    submission_outcome_unknown = False
    definitive_submission_rejection = True


def identity(value: Any) -> dict[str, str]:
    """Validate the three durable, nonsecret headers without granting authority."""
    if (not isinstance(value, dict) or set(value) != {
            "X-HMB-Queue-Only", "X-HMB-Intake-Generation", "X-HMB-Intake-Source"}
            or value["X-HMB-Queue-Only"] != "1"
            or not isinstance(value["X-HMB-Intake-Generation"], str)
            or re.fullmatch(r"0|[1-9][0-9]{0,15}", value["X-HMB-Intake-Generation"]) is None
            or int(value["X-HMB-Intake-Generation"]) > MAX_GENERATION
            or not isinstance(value["X-HMB-Intake-Source"], str)
            or _SOURCE.fullmatch(value["X-HMB-Intake-Source"]) is None):
        raise QueueAdmissionError("Maintenance queue identity is invalid. No request was submitted.")
    return dict(value)


@dataclass(frozen=True, eq=False)
class QueueAdmission:
    generation: int
    source_instance: str
    principal_id: int
    operations: frozenset[str]
    _document: str

    @property
    def headers(self) -> dict[str, str]:
        return identity({"X-HMB-Queue-Only": "1", "X-HMB-Intake-Generation": str(self.generation),
                         "X-HMB-Intake-Source": self.source_instance})

    def profile(self, name: str) -> dict[str, Any]:
        value = json.loads(self._document).get(name)
        if not isinstance(value, dict):
            raise QueueAdmissionError("The requested maintenance grammar is unavailable.")
        return value

    @property
    def workspace_intent(self) -> dict[str, Any] | None:
        return json.loads(self._document).get("workspace_intent")

    def require(self, operation: str) -> None:
        if operation not in self.operations:
            raise QueueAdmissionError("Maintenance queue admission does not allow this operation.")


def parse(raw: Any) -> QueueAdmission | None:
    if (not isinstance(raw, dict) or raw.get("schema") != SCHEMA or type(raw.get("version")) is not int
            or raw["version"] != 1 or type(raw.get("admission_generation")) is not int
            or not 0 <= raw["admission_generation"] <= MAX_GENERATION
            or not isinstance(raw.get("source_instance"), str) or _SOURCE.fullmatch(raw["source_instance"]) is None
            or not isinstance(raw.get("principal"), dict) or type(raw["principal"].get("id")) is not int
            or raw["principal"]["id"] <= 0 or not isinstance(raw["principal"].get("username"), str)
            or not raw["principal"]["username"] or len(raw["principal"]["username"]) > 256
            or any(ord(c) < 32 or ord(c) == 127 for c in raw["principal"]["username"])
            or raw.get("generation_ready") is not False or raw.get("native_readiness_verified") is not False
            or raw.get("execution_revalidation_required") is not True or type(raw.get("queue_only")) is not bool):
        raise QueueAdmissionError("Broker maintenance admission contract is invalid.")
    if raw.get("mode") != "capture":
        if (not isinstance(raw.get("mode"), str) or not re.fullmatch(r"[a-z_]{1,32}", raw["mode"])
                or raw["queue_only"] or any(k in raw for k in ("video_syntax", "image_syntax", "only_syntax", "workspace_intent"))):
            raise QueueAdmissionError("Broker maintenance mode is inconsistent.")
        return None
    operations = raw.get("operations")
    if (raw["queue_only"] is not True or not isinstance(operations, list) or not operations
            or any(not isinstance(op, str) or op not in OPERATIONS for op in operations)
            or len(set(operations)) != len(operations)):
        raise QueueAdmissionError("Broker maintenance operations are invalid.")
    image, only, video = (raw.get(k) for k in ("image_syntax", "only_syntax", "video_syntax"))
    if (not isinstance(video, dict) or video.get("schema") != "hmb-seedance-generation-capabilities"
            or type(video.get("version")) is not int or video["version"] != 3
            or not isinstance(image, dict) or image.get("enabled") is not False
            or not isinstance(image.get("models"), list)
            or any(not isinstance(m, dict) or m.get("enabled") is not False or m.get("credential_ready") is not False for m in image["models"])
            or not isinstance(only, dict) or only.get("enabled") is not False or only.get("generation_enabled") is not False
            or only.get("reason_code") != "maintenance_queue_only"):
        raise QueueAdmissionError("Maintenance syntax must not advertise native generation readiness.")
    # Reuse exact native syntax parsers; this never flips their readiness flags.
    from _hmb_image_generation import parse_capabilities as image_capabilities
    from _hmb_my_box import parse_capabilities as only_capabilities, _workspace
    image_capabilities(image)
    parsed_only = only_capabilities(only)
    intent = raw.get("workspace_intent")
    if intent is not None:
        checked = _workspace(intent)
        if (set(intent) != {"workspace_id", "created_at", "scope", "selection"}
                or type(intent.get("created_at")) is not int or intent["created_at"] != 0
                or checked is None or parsed_only.workspace is not None):
            raise QueueAdmissionError("Deferred workspace intent conflicts with an existing workspace.")
    if parsed_only.workspace is None and intent is None and "only" in operations:
        raise QueueAdmissionError("Private maintenance admission has no workspace target.")
    try:
        snapshot = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise QueueAdmissionError("Maintenance admission is not a JSON snapshot.") from exc
    if len(snapshot.encode("utf-8")) > 1024 * 1024:
        raise QueueAdmissionError("Maintenance admission exceeds its size limit.")
    return QueueAdmission(raw["admission_generation"], raw["source_instance"], raw["principal"]["id"], frozenset(operations), snapshot)


def discover(bridge: Any, *, timeout: float = 15) -> QueueAdmission | None:
    """Legacy injected transports have no admission capability and stay native."""
    method = getattr(bridge, "queue_admission", None)
    return method(timeout=timeout, refresh=True) if callable(method) else None


def require_bound(bridge: Any, admission: QueueAdmission, operation: str) -> dict[str, str]:
    verifier = getattr(bridge, "_queue_admission_headers", None)
    if not callable(verifier):
        raise QueueAdmissionError("Queue admission has no authenticated transport binding.")
    return verifier(admission, operation)


def source_marker(task_id: str) -> str:
    if not isinstance(task_id, str) or _TASK.fullmatch(task_id) is None:
        raise QueueAdmissionError("Private queue source Task ID is invalid.")
    return SOURCE_PREFIX + task_id


def validate_create(payload: Any, path: str, operation: str, *, queue_only: bool) -> None:
    if not isinstance(payload, dict):
        raise QueueAdmissionError("A queue create requires an immutable native request body.")
    expected = "image" if path == "/api/v1/generate/image" else "draft_final" if payload.get("draft_job_id") else "only" if (
        payload.get("my_box_selection") or payload.get("project_selection_schema") == "hmb-only-project-selection-v1") else "video"
    if queue_only and operation != expected:
        raise QueueAdmissionError("Queue operation does not match its native route and body.")
    for field in ("first_frame", "last_frame", "image_urls", "video_urls", "audio_urls", "reference_images"):
        values = payload.get(field, [])
        for value in values if isinstance(values, list) else [values]:
            if isinstance(value, str) and value.startswith(SOURCE_PREFIX):
                if not queue_only or field != "video_urls" or source_marker(value[len(SOURCE_PREFIX):]) != value:
                    raise QueueAdmissionError("Private source intents require explicit video queue admission.")
                from _hmb_my_box import normalize_selection
                normalize_selection(payload.get("my_box_selection"))
