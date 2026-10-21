"""Metadata-only Color LUT usage contract over the existing Broker bridge.

Import and validation are offline. This module stores no state, opens no files,
constructs no credentials and never submits render/media requests. A usage POST
is sent once; an uncertain response is recovered only by the same operation GET.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit
import uuid

CAPABILITIES_API = "/api/v1/color-lut/usage-capabilities"
EVENTS_API = "/api/v1/color-lut/usage-events"
EVENT_SCHEMA = "hmb-color-lut-usage-event"
CAPABILITIES_SCHEMA = "hmb-color-lut-usage-capabilities"
RECEIPT_SCHEMA = "hmb-color-lut-usage-receipt"
MAX_BODY_BYTES = 8192
STAGES = ("local_export", "web_upload")
CODECS = ("hevc10", "prores", "ffv1")
PRESET_CLASSES = ("custom", "personal")
STEP_KEYS = ("exposure", "temperature", "contrast", "saturation", "shadows", "highlights")
SETTINGS_FIELDS = frozenset(("enabled", "precision_version", *STEP_KEYS))
EVENT_FIELDS = frozenset(("schema", "version", "export_operation_id", "stage", "settings", "settings_sha256",
                          "codec", "preset_classification", "export_sha256", "source_task_id", "upload_idempotency_key"))
CAPABILITIES_FIELDS = frozenset(("schema", "version", "enabled", "ready", "persistence_scope", "media_stored",
    "pixel_transform_verified", "max_body_bytes", "stages", "codecs", "preset_classifications",
    "settings_precision_version", "settings_step", "settings_min", "settings_max", "local_export_attestation",
    "web_upload_attestation", "web_upload_enabled", "event_path", "lookup_path", "count_basis"))
RECEIPT_FIELDS = frozenset(("schema", "version", "export_operation_id", "stage", "created", "attestation_kind",
    "settings_sha256", "export_sha256", "codec", "preset_classification", "recorded_at", "recorded_stages",
    "export_usage_count", "count_basis", "pixel_transform_verified", "media_stored"))
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TASK = re.compile(r"job-[0-9a-f]{32}\Z")
_PREFIX = re.compile(r"(?:/[A-Za-z0-9._~-]+)*\Z")


class ColorLUTUsageError(ValueError):
    """Sanitized failure: never copy a transport message or server body here."""

    def __init__(self, code: str, *, status_code: int | None = None,
                 submission_outcome_unknown: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.submission_outcome_unknown = submission_outcome_unknown


def _fail(code: str = "COLOR_LUT_USAGE_INVALID_CONTRACT") -> None:
    raise ColorLUTUsageError(code)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


def _operation(value: Any) -> str:
    try:
        parsed = uuid.UUID(value) if type(value) is str else None
        if parsed is None or str(parsed) != value or parsed.version != 4 or parsed.variant != uuid.RFC_4122:
            _fail("COLOR_LUT_USAGE_INVALID_OPERATION")
    except (ValueError, AttributeError):
        _fail("COLOR_LUT_USAGE_INVALID_OPERATION")
    return value


def normalize_usage_settings(value: Any) -> dict[str, Any]:
    """Strict v2 quarter-grid strengths, serialized exactly as GP normalization."""
    if (type(value) is not dict or set(value) != SETTINGS_FIELDS or type(value.get("enabled")) is not bool
            or type(value.get("precision_version")) is not int or value["precision_version"] != 2):
        _fail("COLOR_LUT_USAGE_INVALID_SETTINGS")
    result = {"enabled": value["enabled"], "precision_version": 2}
    for key in STEP_KEYS:
        number = value[key]
        if type(number) not in (int, float) or not -3 <= number <= 3 or not math.isfinite(number):
            _fail("COLOR_LUT_USAGE_INVALID_SETTINGS")
        if number * 4 != math.floor(number * 4):
            _fail("COLOR_LUT_USAGE_INVALID_SETTINGS")
        strength = math.floor(number * 4 + 0.5) / 4
        result[key] = max(-3, min(3, strength))
    return result


def settings_sha256(settings: Any) -> str:
    return hashlib.sha256(_canonical(normalize_usage_settings(settings)).encode("utf-8")).hexdigest()


def validate_event(value: Any) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != EVENT_FIELDS or value.get("schema") != EVENT_SCHEMA
            or type(value.get("version")) is not int or value["version"] != 1):
        _fail("COLOR_LUT_USAGE_INVALID_EVENT")
    _operation(value["export_operation_id"])
    for key, choices in (("stage", STAGES), ("codec", CODECS), ("preset_classification", PRESET_CLASSES)):
        if type(value[key]) is not str or value[key] not in choices:
            _fail("COLOR_LUT_USAGE_INVALID_EVENT")
    for key in ("settings_sha256", "export_sha256"):
        if type(value[key]) is not str or _HASH.fullmatch(value[key]) is None:
            _fail("COLOR_LUT_USAGE_INVALID_EVENT")
    settings = normalize_usage_settings(value["settings"])
    if settings_sha256(settings) != value["settings_sha256"]:
        _fail("COLOR_LUT_USAGE_SETTINGS_HASH_MISMATCH")
    if value["stage"] == "local_export":
        if value["source_task_id"] is not None or value["upload_idempotency_key"] is not None:
            _fail("COLOR_LUT_USAGE_INVALID_EVENT")
    elif (type(value["source_task_id"]) is not str or _TASK.fullmatch(value["source_task_id"]) is None
          or type(value["upload_idempotency_key"]) is not str or _HASH.fullmatch(value["upload_idempotency_key"]) is None):
        _fail("COLOR_LUT_USAGE_INVALID_EVENT")
    result = dict(value, settings=settings)
    if len(_canonical(result).encode("utf-8")) > MAX_BODY_BYTES:
        _fail("COLOR_LUT_USAGE_BODY_TOO_LARGE")
    return result


def build_event(*, export_operation_id: str, stage: str, settings: Any, codec: str,
                preset_classification: str, export_sha256: str, source_task_id: str | None = None,
                upload_idempotency_key: str | None = None) -> dict[str, Any]:
    normalized = normalize_usage_settings(settings)
    return validate_event({"schema": EVENT_SCHEMA, "version": 1, "export_operation_id": export_operation_id,
        "stage": stage, "settings": normalized, "settings_sha256": settings_sha256(normalized), "codec": codec,
        "preset_classification": preset_classification, "export_sha256": export_sha256,
        "source_task_id": source_task_id, "upload_idempotency_key": upload_idempotency_key})


def _response(value: Any, fields: frozenset[str], statuses: tuple[int, ...]) -> dict[str, Any]:
    if type(value) is not dict or set(value) - {"_http_status"} != fields:
        _fail()
    if "_http_status" in value and (type(value["_http_status"]) is not int or value["_http_status"] not in statuses):
        _fail()
    return {key: value[key] for key in fields}


def validate_capabilities(value: Any, *, server_url: str = "") -> dict[str, Any]:
    result = _response(value, CAPABILITIES_FIELDS, (200,))
    if (result["schema"] != CAPABILITIES_SCHEMA or type(result["version"]) is not int or result["version"] != 1
            or result["persistence_scope"] != "metadata_only" or result["media_stored"] is not False
            or result["pixel_transform_verified"] is not False or type(result["max_body_bytes"]) is not int
            or result["max_body_bytes"] != MAX_BODY_BYTES or result["stages"] != list(STAGES)
            or result["codecs"] != list(CODECS) or result["preset_classifications"] != list(PRESET_CLASSES)
            or type(result["settings_precision_version"]) is not int or result["settings_precision_version"] != 2
            or type(result["settings_step"]) not in (int, float) or result["settings_step"] != 0.25
            or type(result["settings_min"]) not in (int, float) or result["settings_min"] != -3
            or type(result["settings_max"]) not in (int, float) or result["settings_max"] != 3
            or result["local_export_attestation"] != "client_attested"
            or result["web_upload_attestation"] != "server_upload_receipt"
            or result["count_basis"] != "distinct_user_export_operation"):
        _fail()
    if any(type(result[key]) is not bool for key in ("enabled", "ready", "web_upload_enabled")):
        _fail()
    event_path = result["event_path"]
    if type(event_path) is not str or not event_path.endswith(EVENTS_API):
        _fail()
    prefix = event_path[:-len(EVENTS_API)]
    if (_PREFIX.fullmatch(prefix) is None or any(part in (".", "..") for part in prefix.split("/"))
            or result["lookup_path"] != event_path + "/{export_operation_id}/{stage}"):
        _fail()
    if server_url:
        try:
            parsed = urlsplit(server_url)
            expected_prefix = parsed.path.rstrip("/")
            if (parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username is not None
                    or parsed.password is not None or parsed.query or parsed.fragment
                    or _PREFIX.fullmatch(expected_prefix) is None
                    or any(part in (".", "..") for part in expected_prefix.split("/"))):
                _fail()
        except (ValueError, TypeError):
            _fail()
        if prefix != expected_prefix:
            _fail()
    elif prefix:
        _fail()
    # Announced mounted paths are validated, but never followed. The shared
    # bridge retains and validates its configured gateway for the fixed routes.
    return json.loads(_canonical(result))


def validate_receipt(value: Any, event: Any, *, lookup: bool = False) -> dict[str, Any]:
    expected = validate_event(event)
    result = _response(value, RECEIPT_FIELDS, (200,) if lookup else (200, 201))
    if (result["schema"] != RECEIPT_SCHEMA or type(result["version"]) is not int or result["version"] != 1
            or type(result["created"]) is not bool or (lookup and result["created"])
            or result["attestation_kind"] != ("client_attested" if expected["stage"] == "local_export" else "server_upload_receipt")
            or type(result["recorded_at"]) is not int or result["recorded_at"] < 0
            or type(result["export_usage_count"]) is not int or result["export_usage_count"] != 1
            or result["count_basis"] != "distinct_user_export_operation"
            or result["pixel_transform_verified"] is not False or result["media_stored"] is not False):
        _fail("COLOR_LUT_USAGE_INVALID_RECEIPT")
    for key in ("export_operation_id", "stage", "settings_sha256", "export_sha256", "codec", "preset_classification"):
        if result[key] != expected[key]:
            _fail("COLOR_LUT_USAGE_RECEIPT_MISMATCH")
    stages = result["recorded_stages"]
    if (type(stages) is not list or not stages or any(type(stage) is not str or stage not in STAGES for stage in stages)
            or stages != [stage for stage in STAGES if stage in stages] or expected["stage"] not in stages):
        _fail("COLOR_LUT_USAGE_INVALID_RECEIPT")
    if "_http_status" in value and result["created"] != (value["_http_status"] == 201):
        _fail("COLOR_LUT_USAGE_INVALID_RECEIPT")
    return json.loads(_canonical(result))


def _status(error: Exception) -> int | None:
    for key in ("status_code", "code"):
        value = getattr(error, key, None)
        if type(value) is int and 100 <= value <= 599:
            return value
    return None


def _timeout(value: Any) -> float:
    if type(value) not in (int, float) or not 0 < value <= 60 or not math.isfinite(value):
        _fail("COLOR_LUT_USAGE_INVALID_TIMEOUT")
    return float(value)


def _request(bridge: Any, method: str, path: str, *, payload: dict[str, Any] | None, timeout: float) -> Any:
    request = getattr(bridge, "_request_json", None)
    if not callable(request):
        _fail("COLOR_LUT_USAGE_BRIDGE_REQUIRED")
    return request(method, path, payload=payload, timeout=timeout, submission=False)


def check_capabilities(bridge: Any, *, timeout: float = 15) -> dict[str, Any]:
    timeout = _timeout(timeout)
    try:
        result = validate_capabilities(_request(bridge, "GET", CAPABILITIES_API, payload=None, timeout=timeout),
                                       server_url=getattr(bridge, "server_url", ""))
    except ColorLUTUsageError:
        raise
    except Exception as exc:
        raise ColorLUTUsageError("COLOR_LUT_USAGE_UNAVAILABLE", status_code=_status(exc)) from None
    if not result["enabled"] or not result["ready"]:
        _fail("COLOR_LUT_USAGE_UNAVAILABLE")
    return result


def retrieve_event(bridge: Any, event: Any, *, timeout: float = 15) -> dict[str, Any]:
    expected, timeout = validate_event(event), _timeout(timeout)
    path = EVENTS_API + "/" + expected["export_operation_id"] + "/" + expected["stage"]
    try:
        result = _request(bridge, "GET", path, payload=None, timeout=timeout)
    except Exception as exc:
        status = _status(exc)
        raise ColorLUTUsageError("COLOR_LUT_USAGE_EVENT_NOT_FOUND" if status == 404 else "COLOR_LUT_USAGE_LOOKUP_UNAVAILABLE",
                                status_code=status) from None
    return validate_receipt(result, expected, lookup=True)


def submit_event(bridge: Any, event: Any, *, timeout: float = 15,
                 capabilities: Any = None) -> dict[str, Any]:
    """At most one POST. Recovery never changes identity or replays that POST."""
    expected, timeout = validate_event(event), _timeout(timeout)
    caps = check_capabilities(bridge, timeout=timeout) if capabilities is None else validate_capabilities(
        capabilities, server_url=getattr(bridge, "server_url", ""))
    if not caps["enabled"] or not caps["ready"]:
        _fail("COLOR_LUT_USAGE_UNAVAILABLE")
    if not callable(getattr(bridge, "_request_json", None)):
        _fail("COLOR_LUT_USAGE_BRIDGE_REQUIRED")
    # web_upload_enabled controls media upload, not metadata observations of
    # already successful uploads. Preserve this distinction when it is False.
    try:
        raw = _request(bridge, "POST", EVENTS_API, payload=expected, timeout=timeout)
        return validate_receipt(raw, expected)
    except Exception as exc:
        status = _status(exc)
        if status is not None and 400 <= status <= 499 and status != 409:
            raise ColorLUTUsageError("COLOR_LUT_USAGE_SUBMISSION_REJECTED", status_code=status) from None
    try:
        return retrieve_event(bridge, expected, timeout=timeout)
    except ColorLUTUsageError as exc:
        raise ColorLUTUsageError("COLOR_LUT_USAGE_SUBMISSION_PENDING", status_code=exc.status_code,
                                submission_outcome_unknown=True) from None
