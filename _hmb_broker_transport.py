"""Shared authenticated FN AI Broker transport for HMB clients."""
from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager, suppress
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote, urlencode, urlparse
from uuid import uuid4

import _hmb_broker_config as _broker_config
import _hmb_reference_leases as _reference_leases
from _hmb_common import _broker_load_bearer_token_readonly, _broker_load_bearer_token_from_path_readonly

logger = logging.getLogger("griptape_nodes")

AI_BROKER_INTERNAL_ORIGIN = "http://192.168.203.245:8080"
AI_BROKER_SERVER_URL = _broker_config.DEFAULT_BROKER_BASE_URL
# This is the same operated Broker behind its public gateway, not a general
# credential fallback for user-entered third-party addresses.
_BROKER_LEGACY_AUTH_GATEWAY = "https://app.funnyflux.kr/GripTapeServer"
_BROKER_LEGACY_AUTH_MIGRATION_LOCK = threading.RLock()

AI_BROKER_MAX_JSON_BYTES = 16 * 1024 * 1024
AI_BROKER_DEVICE_AUTH_TIMEOUT_SECONDS = 5 * 60
AI_BROKER_DEVICE_POLL_SECONDS = 2.0
AI_BROKER_DEVICE_START_BACKOFF_SECONDS = (0.0, 0.5, 1.5)
AI_BROKER_DEVICE_POLL_MAX_CONSECUTIVE_TRANSPORT_ERRORS = 3
# Five Shot generators prepare and later poll independently.  Only their
# billable Broker POST starts are paced because the production Broker rejects
# same-account creates that arrive less than one second apart.  The lock is
# released before network I/O, so accepted remote renders continue together.
AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 1.20
_BROKER_SUBMISSION_CADENCE_LOCK = threading.RLock()
_BROKER_SUBMISSION_LAST_STARTED = 0.0
# This second boundary is after capability checks and JSON serialization.
# Opaque in-memory credential digests separate local Broker account queues;
# the server remains authoritative across clients and provider snapshots.
_BROKER_HTTP_SUBMISSION_GUARD = threading.Lock()
_BROKER_HTTP_SUBMISSION_STATES: dict[tuple[str, str], dict[str, Any]] = {}
_BROKER_NATIVE_SUBMISSION_CONTEXT = threading.local()
AI_BROKER_INTERVAL_RETRY_MAX_ATTEMPTS = 5
AI_BROKER_INTERVAL_RETRY_MAX_SECONDS = 15.0
AI_BROKER_INTERVAL_RETRY_MARGIN_SECONDS = 0.20

BROKER_FAILURE_STATUSES = {"failed", "error", "rejected"}
BROKER_CANCELLED_STATUSES = {"cancelled", "canceled"}
BROKER_EXPIRED_STATUSES = {"expired"}

MAX_REQUEST_BYTES = 64 * 1024 * 1024

_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")

_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")

_BROKER_ERROR_DETAIL_LIMIT = 3000
_BROKER_ERROR_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:authorization|proxy[-_ ]authorization|api[-_ ]?key|provider[-_ ]?key|"
    r"access[-_ ]key[-_ ]id|secret[-_ ]access[-_ ]key|access[-_ ]token|refresh[-_ ]token|"
    r"client[-_ ]secret|key|token|secret|password|passwd|credential|cookie|signature)"
    r"\b[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"
)
_BROKER_ERROR_FIELDS = frozenset({
    "error", "errors", "detail", "details", "message", "msg", "reason", "code", "error_code", "type",
    "param", "parameter", "field", "loc", "request_id", "requestid",
})


def _broker_safe_error_text(value: Any, *, secret: str = "") -> str:
    """Bounded diagnostic text, not an executable/raw provider response."""

    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    text = str(value)
    # Never truncate in the middle of a secret before redacting it.
    if len(text) > 64 * 1024:
        return "[Oversized server detail omitted]"
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = re.sub(r"(?i)\bBasic\s+[A-Za-z0-9+/=]+", "Basic [REDACTED]", text)
    # Error URLs may contain credentials in userinfo, query, fragment or path.
    text = re.sub(r"(?i)\b(?:https?|s3|tos)://[^\s\"'<>]+", "[URL REDACTED]", text)
    text = re.sub(r"(?i)\bdata:[^\s\"'<>]+", "[MEDIA DATA REDACTED]", text)
    text = re.sub(r"(?im)\b(?:authorization|proxy-authorization|set-cookie|cookie)\s*:\s*[^\r\n]+",
                  "[AUTH HEADER REDACTED]", text)
    text = _BROKER_ERROR_SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:ib_|sk-|AKIA|ASIA)[A-Za-z0-9_-]{16,}\b", "[REDACTED]", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)
    text = " ".join(text.split())
    if len(text) > _BROKER_ERROR_DETAIL_LIMIT:
        text = text[:_BROKER_ERROR_DETAIL_LIMIT] + " [truncated]"
    return text


# Volcengine Ark error-codes: only documented categories, never input echoes.
_VOLC_REASON = {
    "InputTextSensitiveContentDetected": "입력 프롬프트 심사 거절",
    "InputImageSensitiveContentDetected": "입력 이미지 심사 거절",
    "InputVideoSensitiveContentDetected": "입력 영상 심사 거절",
    "InputAudioSensitiveContentDetected": "입력 음원 심사 거절",
    "OutputTextSensitiveContentDetected": "생성 텍스트 심사 거절",
    "OutputImageSensitiveContentDetected": "생성 이미지 심사 거절",
    "OutputVideoSensitiveContentDetected": "생성 영상 심사 거절",
    "OutputAudioSensitiveContentDetected": "생성 음원 심사 거절",
    "SensitiveContentDetected": "콘텐츠 심사 거절 · 대상 미확인",
    "InvalidParameter": "요청 파라미터 오류",
    "InvalidParameterValue": "요청 파라미터 값 오류",
    "MissingParameter": "필수 파라미터 누락",
    "UnsupportedParameter": "지원하지 않는 파라미터",
    "InvalidRequest": "잘못된 요청", "InvalidImage": "입력 이미지 형식 오류",
    "InvalidVideo": "입력 영상 형식 오류", "InvalidAudio": "입력 음원 형식 오류",
    "Unauthorized": "공급자 인증 오류", "AuthenticationError": "공급자 인증 오류",
    "AccessDenied": "공급자 접근 권한 오류", "Forbidden": "공급자 접근 권한 오류",
    "QuotaExceeded": "공급자 할당량 초과", "InsufficientBalance": "공급자 잔액 부족",
    "RateLimitExceeded": "공급자 요청 한도 초과", "TooManyRequests": "공급자 요청 한도 초과",
    "ServiceUnavailable": "공급자 서비스 이용 불가", "InternalServerError": "공급자 내부 오류",
}
_VOLC_PARAMS = frozenset("model resolution duration duration_seconds ratio aspect_ratio output_format draft draft_job_id generate_audio seed watermark camera_fixed content prompt image_url video_url audio_url return_last_frame".split())
_VOLC_SUFFIX = {"PolicyViolation": "저작권 제한 가능성", "PrivacyInformation": "실존 인물 관련 가능성",
                "TaskTypeMismatch": "요청한 작업 유형 불일치", "TaskTypeConstraint": "작업 유형별 조건 불충족"}


def _volc_failure_reason(response: Any) -> str:
    """Present structured evidence; never infer moderation from HTTP status or message text."""
    if not isinstance(response, dict):
        return ""
    result = response.get("result")
    diagnostic = response.get("provider_failure_diagnostics")
    if diagnostic is None and isinstance(result, dict):
        diagnostic = result.get("provider_failure_diagnostics")
    projected = isinstance(diagnostic, dict) and diagnostic.get("schema") == "hmb-provider-failure-diagnostics-v1"
    if projected and diagnostic.get("code") == "InvalidParameter" and isinstance(diagnostic.get("reference_failure"), dict):
        message = response.get("error")
        if isinstance(message, str) and re.fullmatch(
            r"참조 (?:이미지|영상|오디오|미디어) (?:다운로드|처리) 시간 초과 "
            r"\([\w가-힣 .()·\[\]-]{1,155}\)\. 해당 (?:이미지|영상|오디오|미디어) 파일을 다시 첨부해 주세요\.",
            message,
        ):
            return _broker_safe_error_text(message)
    error = diagnostic if projected else response.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str) and 0 < len(code) <= 128:
            family, _, suffix = code.partition(".")
            label = _VOLC_REASON.get(family)
            if label:
                moderation = "SensitiveContentDetected" in family
                if ((moderation and suffix == "PolicyViolation")
                        or (family in {"InputImageSensitiveContentDetected", "InputVideoSensitiveContentDetected"}
                            and suffix == "PrivacyInformation")
                        or (family == "InvalidParameter" and suffix in {"TaskTypeMismatch", "TaskTypeConstraint"})):
                    label += " · " + _VOLC_SUFFIX[suffix]
                elif suffix and (moderation or suffix.lower() not in _VOLC_PARAMS):
                    code = family
                params = error.get("parameters") if projected else [error.get("param")]
                fields = [p for p in params[:16] if isinstance(p, str) and p in _VOLC_PARAMS] if isinstance(params, list) else []
                return f"{label} ({code})" + (" · 관련 필드: " + ", ".join(dict.fromkeys(fields)) if fields else "")
    if projected:
        status = diagnostic.get("http_status")
        http = f" · HTTP {status}" if type(status) is int and 400 <= status <= 599 else ""
        return "Volcengine 오류 · 상세 사유 미확인" + http
    if any(response.get(key) == "Volcengine create rejected the request (HTTP 400)." for key in ("error", "detail", "message")):
        return "Volcengine 생성 요청 거절 (HTTP 400) · 공급자 상세 코드가 없어 사유를 확인할 수 없습니다."
    return ""



def _broker_error_details(response: Any, *, secret: str = "") -> str:
    """Keep failure reasons/field paths, excluding credentials and input echoes."""

    if not isinstance(response, dict):
        return ""
    parts: list[str] = []

    def visit(value: Any, label: str, depth: int = 0) -> None:
        if depth > 5 or len(parts) >= 16:
            return
        if isinstance(value, dict):
            for key, item in list(value.items())[:64]:
                if str(key).lower() in _BROKER_ERROR_FIELDS:
                    visit(item, f"{label}.{key}", depth + 1)
        elif isinstance(value, list):
            for item in value[:16]:
                visit(item, label, depth + 1)
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
                try:
                    nested = json.loads(value) if len(value) <= 64 * 1024 else None
                except (ValueError, RecursionError):
                    nested = None
                if isinstance(nested, (dict, list)):
                    visit(nested, label, depth + 1)
                    return
            safe = _broker_safe_error_text(value, secret=secret)
            if safe:
                parts.append(f"{label}: {safe}")

    for field in ("error", "errors", "detail", "details", "message", "error_code", "code", "request_id"):
        if field in response:
            visit(response[field], field)
    return _broker_safe_error_text("; ".join(parts))


class _BrokerError(RuntimeError):
    """Broker failure with sanitized diagnostics, never raw bodies/credentials."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        submission_outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.submission_outcome_unknown = submission_outcome_unknown
        # Only the create-call catch may promote this to True. Keeping it out of
        # the constructor prevents errors from accepted task polling/retrieval
        # paths from inheriting create-rejection semantics.
        self.definitive_submission_rejection = False


class _BrokerUnavailableError(_BrokerError):
    pass


class _CloudReferenceCheckError(_BrokerError):
    """Project only safe, bounded fields from the Broker's Cloud preflight report."""

    limits = {"first_frame": 1, "last_frame": 1, "image_urls": 30, "video_urls": 10, "audio_urls": 10}
    codes = frozenset({
        "invalid_cloud_url", "griptape_signed_url_required", "upload_digest_required", "reference_size_limit",
        "cloud_http_status", "cloud_length_mismatch", "cloud_encoding_invalid", "cloud_sha256_mismatch",
        "cloud_timeout", "cloud_transport_error", "cloud_request_invalid", "cloud_reference_count",
        "cloud_preflight_busy",
    })

    @staticmethod
    def _metric(value: Any) -> str:
        return str(value) if type(value) is int and 0 <= value < 10**12 else "미제공"

    @classmethod
    def from_body(cls, body: bytes, status: int, *, private: bool) -> "_CloudReferenceCheckError | None":
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            return None
        code = data.get("error_code") if isinstance(data, dict) else None
        if not isinstance(code, str) or code not in cls.codes:
            return None
        message = f"Griptape Cloud 참조 검사 실패 · {code} (HTTP {status})"
        error = cls(message, status_code=status)
        error.rows = []
        if private:
            error.args = (message + "\nMy Box는 오류 코드만 제공합니다. 파일별 시도 내역은 이 요청의 브로커 로그에서 확인하세요.",)
            return error
        files = data.get("files")
        for row in files[:50] if isinstance(files, list) else ():
            if not isinstance(row, dict):
                continue
            field, index, attempts = row.get("field"), row.get("index"), row.get("attempts")
            if (not isinstance(field, str) or field not in cls.limits or type(index) is not int
                    or not 0 <= index < cls.limits[field] or not isinstance(attempts, list) or not 1 <= len(attempts) <= 2
                    or not isinstance(attempts[-1], dict) or attempts[-1].get("result") == "ok"):
                continue
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                result = attempt.get("result")
                if not isinstance(result, str) or result not in cls.codes:
                    continue
                if result == "cloud_sha256_mismatch":
                    stage = "SHA-256 대조"
                elif type(attempt.get("first_byte_ms")) is int:
                    stage = "본문 수신"
                elif type(attempt.get("headers_ms")) is int:
                    stage = "헤더 수신 후, 첫 바이트 수신 전"
                else:
                    stage = "응답 헤더 수신 전"
                error.rows.append((field, index,
                    f"{stage} · {result} · 시도 {cls._metric(attempt.get('number'))} · "
                    f"수신 {cls._metric(attempt.get('bytes'))} B · 소요 {cls._metric(attempt.get('total_ms'))} ms"))
        if error.rows:
            error.with_sources({})
        else:
            error.args = (message + "\n파일별 내역이 응답에 없습니다. 브로커 로그에서 이 요청을 확인하세요.",)
        return error

    def with_sources(self, sources: dict) -> None:
        if self.rows:
            lines = [str(self).split("\n", 1)[0]]
            for field, index, detail in self.rows:
                source = sources.get((field, index))
                label = f"슬롯 {source[0]} · {source[1]}" if source else "원본 슬롯 미확인"
                lines.append(f"{field}[{index}] · {label} · {detail}")
            self.args = ("\n".join(lines),)


class _BrokerAuthenticationError(_BrokerError):
    pass


class _BrokerProtocolError(_BrokerError):
    pass


class _DraftFinalPreflightError(_BrokerProtocolError):
    """The Final capability check failed before the create request was sent."""


class _SubmissionCancelledBeforeStart(RuntimeError):
    """Internal marker: local cancellation won before the billable POST."""


@dataclass(frozen=True)
class _BrokerAccountSnapshot:
    state: str
    connected: bool
    account: str


class _BrokerDataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class _BrokerNoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _broker_build_opener() -> Any:
    """Build the existing Broker opener without inheriting machine proxies."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _BrokerNoRedirectHandler(),
    )


def _broker_wait_for_submission_slot() -> None:
    """Reserve the next local Broker-create start without serializing renders."""

    global _BROKER_SUBMISSION_LAST_STARTED
    with _BROKER_SUBMISSION_CADENCE_LOCK:
        now = time.monotonic()
        remaining = (
            _BROKER_SUBMISSION_LAST_STARTED
            + AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS
            - now
        )
        if remaining > 0:
            time.sleep(remaining)
        _BROKER_SUBMISSION_LAST_STARTED = time.monotonic()


def _broker_check_native_submission() -> None:
    callbacks = getattr(_BROKER_NATIVE_SUBMISSION_CONTEXT, "callbacks", None)
    if callbacks is not None:
        callbacks[0]()


def _broker_note_native_interval_rejection() -> None:
    callbacks = getattr(_BROKER_NATIVE_SUBMISSION_CONTEXT, "callbacks", None)
    if callbacks is not None:
        callbacks[1]()


def _broker_note_native_http_start() -> None:
    callbacks = getattr(_BROKER_NATIVE_SUBMISSION_CONTEXT, "callbacks", None)
    if callbacks is not None:
        callbacks[2]()


def _broker_wait_for_http_submission(request: Any, origin: str, *, deadline: float | None = None) -> bool:
    identity = hashlib.sha256(str(request.get_header("Authorization") or "").encode("utf-8")).hexdigest()
    key = (origin, identity)
    with _BROKER_HTTP_SUBMISSION_GUARD:
        state = _BROKER_HTTP_SUBMISSION_STATES.setdefault(key, {"lock": threading.Lock(), "last": 0.0})
    while not state["lock"].acquire(timeout=0.10):
        _broker_check_native_submission()
        if deadline is not None and time.monotonic() >= deadline:
            return False
    try:
        if deadline is not None and time.monotonic() >= deadline:
            return False
        slot_time = state["last"] + AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS
        while time.monotonic() < slot_time:
            _broker_check_native_submission()
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(min(0.10, max(0.0, slot_time - time.monotonic())))
        _broker_check_native_submission()
        state["last"] = time.monotonic()
        return True
    finally:
        state["lock"].release()


def _broker_interval_rejection_delay(body: bytes) -> float | None:
    """Recognize only the Broker's pre-provider minimum-interval rejection."""
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        return None
    if not isinstance(payload, dict) or any(payload.get(key) for key in ("job_id", "provider_job_id", "task_id")):
        return None
    if payload.get("error_code") == "submission_interval_limited":
        milliseconds = payload.get("retry_after_ms")
        if (payload.get("retryable") is True and payload.get("provider_create_sent") is False
                and type(milliseconds) is int and 0 <= milliseconds <= 5_000):
            return milliseconds / 1000.0
        return None
    if set(payload) - {"error", "request_id"}:
        return None
    # The existing Broker emits this exact, single-purpose Korean sentence.
    # Quota, concurrency, maintenance and arbitrary 429 messages are excluded.
    message = payload.get("error")
    match = re.fullmatch(r"다음 요청까지 ([0-9]+\.[0-9])초 기다려야 합니다\.", message or "") if isinstance(message, str) else None
    if not match:
        return None
    delay = float(match.group(1))
    return delay if 0.0 <= delay <= 5.0 else None


def _broker_log_transport_error(
    *,
    stage: str,
    attempt: int,
    exc: BaseException,
    server_url: str,
) -> None:
    """Log transport diagnostics without values that can contain credentials."""
    parsed = urlparse(server_url)
    host = re.sub(r"[^A-Za-z0-9.:-]", "?", parsed.hostname or "")[:253]
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError:
        port = 0

    reason = exc.reason if isinstance(exc, urllib.error.URLError) else None

    def _error_number(value: Any) -> int | None:
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool)
            else None
        )

    errno_value = _error_number(getattr(reason, "errno", None))
    if errno_value is None:
        errno_value = _error_number(getattr(exc, "errno", None))
    winerror_value = _error_number(getattr(reason, "winerror", None))
    if winerror_value is None:
        winerror_value = _error_number(getattr(exc, "winerror", None))

    logger.warning(
        "FN AI Broker transport failure stage=%s attempt=%d "
        "exception=%s reason=%s errno=%s winerror=%s host=%s port=%d",
        stage,
        attempt,
        type(exc).__name__,
        type(reason).__name__ if reason is not None else "none",
        errno_value,
        winerror_value,
        host,
        port,
    )


def _broker_validated_server_url(raw_url: str | None = None) -> str:
    """Resolve the durable common setting, or validate an explicitly pinned task."""
    try:
        value = _broker_config.load_broker_base_url() if raw_url is None else raw_url
        return _broker_config.normalize_broker_base_url(value)
    except (ValueError, OSError) as exc:
        raise _BrokerUnavailableError(str(exc)) from exc


def _broker_display_server_url() -> str:
    try:
        return _broker_config.load_broker_base_url()
    except (ValueError, OSError):
        return ""

def _broker_token_path(*, server_url: str | None = None) -> Path:
    selected_origin = _broker_validated_server_url(server_url)
    shared_origin = AI_BROKER_INTERNAL_ORIGIN
    root = Path(os.environ.get("APPDATA") or Path.home())
    directory = root / "FNAIBroker"
    if selected_origin != shared_origin:
        digest = hashlib.sha256(selected_origin.encode("ascii")).hexdigest()
        return directory / f"access_token_v2_{digest}.dpapi"
    current = directory / "access_token_v2.dpapi"
    legacy = root / "CompanyAIBroker" / "access_token_v2.dpapi"
    if not current.is_file() and legacy.is_file():
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, current)
    return current


def _broker_dpapi(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise _BrokerUnavailableError(
            "FN AI Broker token protection requires Windows DPAPI."
        )
    buffer = ctypes.create_string_buffer(data)
    source = _BrokerDataBlob(
        len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    destination = _BrokerDataBlob()
    operation = (
        ctypes.windll.crypt32.CryptProtectData
        if protect
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    if not operation(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(destination),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def _broker_save_token(
    token: str, *, server_url: str | None = None, only_if_missing: bool = False,
) -> None:
    value = str(token or "").strip()
    if not value:
        raise _BrokerProtocolError("FN AI Broker returned an empty access token.")
    selected = _broker_validated_server_url(server_url)
    with _BROKER_LEGACY_AUTH_MIGRATION_LOCK:
        if (only_if_missing and selected == _BROKER_LEGACY_AUTH_GATEWAY
                and _broker_legacy_migration_block_path(selected).exists()):
            raise _BrokerAuthenticationError("FN AI Broker login is required.")
        destination = _broker_token_path(server_url=selected)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.stem}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(_broker_dpapi(value.encode("utf-8"), protect=True))
                stream.flush()
                os.fsync(stream.fileno())
            if only_if_missing:
                # Publish a complete protected file without replacing a login
                # made by another process during credential verification.
                if os.name == "nt":
                    os.rename(temporary, destination)
                else:
                    os.link(temporary, destination)
            else:
                os.replace(temporary, destination)
            if selected == _BROKER_LEGACY_AUTH_GATEWAY and not only_if_missing:
                _broker_legacy_migration_block_path(selected).unlink(missing_ok=True)
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()


def _broker_legacy_migration_block_path(server_url: str | None = None) -> Path:
    return _broker_token_path(server_url=server_url).with_suffix(".no-legacy")


def _broker_clear_token(*, server_url: str | None = None) -> None:
    selected_origin = _broker_validated_server_url(server_url)
    with _BROKER_LEGACY_AUTH_MIGRATION_LOCK:
        if selected_origin != AI_BROKER_INTERNAL_ORIGIN:
            if selected_origin == _BROKER_LEGACY_AUTH_GATEWAY:
                # A rejected/cleared scoped login must not silently switch back
                # to an old account, including after restarting the editor.
                marker = _broker_legacy_migration_block_path(selected_origin)
                marker.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with marker.open("xb") as stream:
                        stream.write(b"Scoped login cleared; explicit authentication required.\n")
                except FileExistsError:
                    pass
            with suppress(FileNotFoundError):
                _broker_token_path(server_url=selected_origin).unlink()
            return
        root = Path(os.environ.get("APPDATA") or Path.home())
        for path in (
            root / "FNAIBroker" / "access_token_v2.dpapi",
            root / "CompanyAIBroker" / "access_token_v2.dpapi",
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _broker_load_token(*, server_url: str | None = None) -> str:
    try:
        selected_origin = _broker_validated_server_url(server_url)
        if selected_origin == AI_BROKER_INTERNAL_ORIGIN:
            return _broker_load_bearer_token_readonly()
        return _broker_load_bearer_token_from_path_readonly(
            _broker_token_path(server_url=selected_origin)
        )
    except RuntimeError as exc:
        raise _BrokerAuthenticationError(
            str(exc) or "The saved FN AI Broker login is unavailable. Connect again."
        ) from exc


def _broker_read_json(response: Any, *, max_bytes: int) -> Any:
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise _BrokerProtocolError("FN AI Broker response was too large.")
    try:
        return json.loads(raw or b"{}")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _BrokerProtocolError("FN AI Broker returned invalid JSON.") from exc


def _broker_same_origin(url: str, origin_url: str) -> bool:
    def _origin(value: str) -> tuple[str, str, int]:
        parsed = urlparse(value)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("invalid origin")
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        return parsed.scheme.lower(), (parsed.hostname or "").lower(), port

    try:
        return _origin(url) == _origin(origin_url)
    except (TypeError, ValueError):
        return False


def _broker_require_exact_response_url(response: Any, expected_url: str) -> None:
    getter = getattr(response, "geturl", None)
    if not callable(getter) or str(getter()) != expected_url:
        raise _BrokerProtocolError(
            "FN AI Broker response origin or path was invalid."
        )


def _broker_migrate_legacy_gateway_token(*, server_url: str) -> str:
    """Adopt an existing user's login only after this gateway authenticates it.

    No create/device-login request is made. The original protected credential
    and all task origins remain untouched. This runs at the background Bridge
    authentication boundary, never when loading settings or constructing UI.
    """
    selected = _broker_validated_server_url(server_url)
    if selected != _BROKER_LEGACY_AUTH_GATEWAY:
        raise _BrokerAuthenticationError("FN AI Broker login is required.")
    with _BROKER_LEGACY_AUTH_MIGRATION_LOCK:
        path = _broker_token_path(server_url=selected)
        if path.exists():
            return _broker_load_token(server_url=selected)
        if _broker_legacy_migration_block_path(selected).exists():
            raise _BrokerAuthenticationError("FN AI Broker login is required.")
        try:
            token = _broker_load_bearer_token_readonly()
        except RuntimeError as exc:
            raise _BrokerAuthenticationError("FN AI Broker login is required.") from exc
        url = _broker_config.join_broker_url(selected, "/api/me")
        request = urllib.request.Request(
            url, headers={"Accept": "application/json", "Authorization": "Bearer " + token},
            method="GET",
        )
        try:
            with _broker_build_opener().open(request, timeout=10) as response:
                _broker_require_exact_response_url(response, url)
                if int(getattr(response, "status", 0)) != 200:
                    raise _BrokerProtocolError("FN AI Broker login could not be verified.")
                account = _broker_read_json(response, max_bytes=64 * 1024)
            mappings = [account]
            if isinstance(account, dict) and isinstance(account.get("user"), dict):
                mappings.append(account["user"])
            if (not isinstance(account, dict)
                    or not _HMBAIBrokerBridge._account_from_mapping(account)
                    or any(row.get("enabled") is False
                           or str(row.get("approval_status") or "").lower() in {"pending", "rejected", "blocked"}
                           for row in mappings if isinstance(row, dict))):
                raise _BrokerProtocolError("FN AI Broker account authentication could not be verified.")
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise _BrokerAuthenticationError(
                    "The existing FN AI Broker login was not accepted by the gateway.",
                    status_code=exc.code,
                ) from exc
            raise _BrokerError(
                "FN AI Broker gateway authentication is temporarily unavailable.",
                status_code=exc.code,
            ) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise _BrokerUnavailableError(
                "FN AI Broker gateway authentication did not respond. The existing login was preserved."
            ) from exc
        # Never replace a newer scoped login established during verification.
        if path.exists():
            return _broker_load_token(server_url=selected)
        if _broker_legacy_migration_block_path(selected).exists():
            raise _BrokerAuthenticationError("FN AI Broker login is required.")
        try:
            _broker_save_token(token, server_url=selected, only_if_missing=True)
        except FileExistsError:
            return _broker_load_token(server_url=selected)
        except OSError as exc:
            raise _BrokerUnavailableError(
                "FN AI Broker could not save the verified gateway login. The existing login was preserved."
            ) from exc
        return token


def _broker_device_login(
    *, opener: Any | None = None, server_url: str | None = None,
) -> dict[str, Any]:
    """Authorize this Windows account once and persist the resulting Broker token."""
    server_url = _broker_validated_server_url(server_url)
    request_opener = opener if opener is not None else _broker_build_opener()

    for start_attempt, backoff_seconds in enumerate(
        AI_BROKER_DEVICE_START_BACKOFF_SECONDS,
        start=1,
    ):
        if backoff_seconds:
            time.sleep(backoff_seconds)
        start_request = urllib.request.Request(
            _broker_config.join_broker_url(server_url, "/api/device/start"),
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request_opener.open(start_request, timeout=10) as response:
                _broker_require_exact_response_url(response, start_request.full_url)
                start_result = _broker_read_json(
                    response, max_bytes=2 * 1024 * 1024
                )
                if int(getattr(response, "status", 0) or 0) != 201:
                    raise _BrokerProtocolError(
                        "FN AI Broker device authorization response was invalid."
                    )
            break
        except urllib.error.HTTPError as exc:
            raise _BrokerAuthenticationError(
                "FN AI Broker device authorization could not be started.",
                status_code=exc.code,
            ) from exc
        except _BrokerError:
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            _broker_log_transport_error(
                stage="device_start",
                attempt=start_attempt,
                exc=exc,
                server_url=server_url,
            )
            if start_attempt == len(AI_BROKER_DEVICE_START_BACKOFF_SECONDS):
                raise _BrokerUnavailableError(
                    "FN AI Broker device authorization service is unavailable."
                ) from exc

    if not isinstance(start_result, dict):
        raise _BrokerProtocolError(
            "FN AI Broker device authorization response was invalid."
        )
    device_code = str(start_result.get("device_code") or "").strip()
    device_secret = str(start_result.get("device_secret") or "").strip()
    verification_url = str(start_result.get("verification_url") or "").strip()
    parsed_verification = urlparse(verification_url)
    expected_verification = urlparse(server_url)
    gateway_path = expected_verification.path.rstrip("/")
    if (
        _TASK_ID_PATTERN.fullmatch(device_code) is None
        or len(device_secret) < 20
        or not _broker_same_origin(verification_url, server_url)
        or parsed_verification.path not in {gateway_path, gateway_path + "/"}
        or parsed_verification.fragment
        or parsed_verification.query != urlencode({"device": device_code})
    ):
        raise _BrokerProtocolError(
            "FN AI Broker device authorization response was invalid."
        )

    try:
        browser_opened = webbrowser.open(verification_url, new=2, autoraise=True)
    except Exception as exc:
        raise _BrokerUnavailableError(
            "Could not open the FN AI Broker authorization page."
        ) from exc
    if not browser_opened:
        raise _BrokerUnavailableError(
            "Could not open the FN AI Broker authorization page."
        )

    token_payload = json.dumps(
        {"device_code": device_code, "device_secret": device_secret},
        separators=(",", ":"),
    ).encode("utf-8")
    deadline = time.monotonic() + AI_BROKER_DEVICE_AUTH_TIMEOUT_SECONDS
    consecutive_transport_errors = 0
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        token_request = urllib.request.Request(
            _broker_config.join_broker_url(server_url, "/api/device/token"),
            data=token_payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request_opener.open(
                token_request,
                timeout=min(10.0, remaining),
            ) as response:
                _broker_require_exact_response_url(response, token_request.full_url)
                token_result = _broker_read_json(
                    response, max_bytes=2 * 1024 * 1024
                )
                status_code = int(getattr(response, "status", 200))
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 410}:
                raise _BrokerAuthenticationError(
                    "FN AI Broker authorization expired. Connect again.",
                    status_code=exc.code,
                ) from exc
            raise _BrokerAuthenticationError(
                "FN AI Broker device authorization failed.",
                status_code=exc.code,
            ) from exc
        except _BrokerError:
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            consecutive_transport_errors += 1
            _broker_log_transport_error(
                stage="device_token_poll",
                attempt=consecutive_transport_errors,
                exc=exc,
                server_url=server_url,
            )
            if (
                consecutive_transport_errors
                >= AI_BROKER_DEVICE_POLL_MAX_CONSECUTIVE_TRANSPORT_ERRORS
            ):
                raise _BrokerUnavailableError(
                    "FN AI Broker authorization polling was interrupted."
                ) from exc
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(AI_BROKER_DEVICE_POLL_SECONDS, remaining))
            continue

        consecutive_transport_errors = 0
        if not isinstance(token_result, dict):
            raise _BrokerProtocolError(
                "FN AI Broker device token response was invalid."
            )
        if status_code == 202 or str(token_result.get("status") or "").lower() == "pending":
            time.sleep(AI_BROKER_DEVICE_POLL_SECONDS)
            continue
        access_token = str(token_result.get("access_token") or "").strip()
        if status_code == 200 and access_token:
            _broker_save_token(access_token, server_url=server_url)
            return {"status": "connected"}
        raise _BrokerProtocolError(
            "FN AI Broker device token response was invalid."
        )

    raise _BrokerAuthenticationError(
        "FN AI Broker authorization timed out. Connect again."
    )


class _HMBAIBrokerBridge:
    """Authenticated HTTP transport with shared account and submission state."""
    _MAX_ERROR_CLASSIFICATION_BYTES = 64 * 1024

    def __init__(
        self, *, opener: Any | None = None, server_url: str | None = None,
    ) -> None:
        self._opener = opener if opener is not None else _broker_build_opener()
        self._server_url = _broker_validated_server_url(server_url)
        # Private transport evidence only. Neither bearer digests nor response
        # proofs enter parameters, checkpoints, journals or public JSON.
        self._reference_auth_lock = threading.RLock()
        self._reference_auth_digest = ""
        self._reference_auth_epoch = 0
        self._reference_verified_epoch = -1
        self._reference_account_fingerprint = ""
        self._reference_response_proofs: dict[int, tuple[Any, int, str]] = {}
        self._queue_admission_binding = None
        self._queue_admission_checked_epoch = None

    def queue_admission(self, *, timeout: float = 15, refresh: bool = False) -> Any:
        """Discover queue acceptance without asserting renderer/key readiness."""
        import _hmb_queue_admission as queue
        with self._reference_auth_lock:
            self._load_access_token()
            binding = getattr(self, "_queue_admission_binding", None)
            if binding is not None and not refresh:
                self._queue_admission_headers(binding[0], next(iter(binding[0].operations)))
                return binding[0]
            if not refresh and getattr(self, "_queue_admission_checked_epoch", None) == self._reference_auth_epoch:
                return None
            self._queue_admission_binding = None
            checked_epoch = self._reference_auth_epoch
        try:
            raw = self._request_json("GET", queue.PATH, payload=None, timeout=timeout)
        except _BrokerError as exc:
            if exc.status_code in (404, 405, 501):
                with self._reference_auth_lock:
                    if checked_epoch == self._reference_auth_epoch:
                        self._queue_admission_checked_epoch = checked_epoch
                return None  # Older native Brokers do not implement this opt-in.
            raise
        admission = queue.parse(raw)
        if admission is None:
            with self._reference_auth_lock:
                if checked_epoch == self._reference_auth_epoch:
                    self._queue_admission_checked_epoch = checked_epoch
            return None
        with self._reference_principal_scope(raw) as principal:
            verified = bool(principal)
        if not verified:
            # Image Run may not have needed Connect yet. Only /api/me proves
            # the credential owner; never trust a principal supplied by a UI.
            self._request_json("GET", "/api/me", payload=None, timeout=timeout)
            raw = self._request_json("GET", queue.PATH, payload=None, timeout=timeout)
            admission = queue.parse(raw)
            if admission is None:
                return None
        with self._reference_principal_scope(raw) as principal:
            expected = _reference_leases.principal_fingerprint({"id": admission.principal_id}, self.server_url)
            if not principal or principal != expected:
                raise queue.QueueAdmissionError("Maintenance admission belongs to another credential owner.")
            self._queue_admission_binding = (admission, self._reference_auth_epoch, principal, self.server_url, self)
        return admission

    def _queue_admission_headers(self, admission: Any, operation: str) -> dict[str, str]:
        import _hmb_queue_admission as queue
        with self._reference_auth_lock:
            self._load_access_token()
            binding = getattr(self, "_queue_admission_binding", None)
            if (binding is None or binding[0] is not admission or binding[1] != self._reference_auth_epoch
                    or binding[2] != self._reference_account_fingerprint or binding[3] != self.server_url or binding[4] is not self
                    or self._reference_verified_epoch != self._reference_auth_epoch):
                raise queue.QueueAdmissionError("Maintenance admission authentication changed. Refresh before submitting.")
            admission.require(operation)
            return admission.headers

    def _queue_syntax(self, path: str, *, name: str, timeout: float) -> dict[str, Any]:
        admission = self.queue_admission(timeout=timeout)
        return admission.profile(name) if admission is not None else self._request_json("GET", path, payload=None, timeout=timeout)

    @property
    def server_url(self) -> str:
        return self._server_url

    def review_capabilities(self) -> dict[str, Any]:
        result = self._request_json("GET", "/api/v1/reviews/capabilities", payload=None, timeout=5)
        mounted_page = urlparse(self.server_url).path.rstrip("/") + "/reviews"
        retention = (type(result.get("retention_days")) is int and result["retention_days"] == 30)
        manual_retention = (result.get("retention_days", False) is None
                            and result.get("automatic_deletion") is False
                            and result.get("retention_policy") == "manual_only")
        if (result.get("schema") != "hmb-review-portal" or type(result.get("version")) is not int
                or result["version"] != 1 or result.get("review_portal") is not True
                or not isinstance(result.get("page_url"), str)
                or result["page_url"] not in {"/reviews", mounted_page}
                or type(result.get("page_size")) is not int or result["page_size"] not in (15, 20, 30)
                or not (retention or manual_retention)):
            raise _BrokerProtocolError("Broker review portal capabilities are unsupported.")
        return result

    def _load_access_token(self) -> str:
        with self._reference_auth_lock:
            try:
                try:
                    token = _broker_load_token(server_url=self.server_url)
                except _BrokerAuthenticationError:
                    # A corrupt or rejected scoped credential is never overwritten by
                    # the old login. Only a previously unconfigured official gateway
                    # may verify and adopt the existing user's protected token.
                    if (self.server_url != _BROKER_LEGACY_AUTH_GATEWAY
                            or _broker_token_path(server_url=self.server_url).exists()):
                        raise
                    token = _broker_migrate_legacy_gateway_token(server_url=self.server_url)
            except Exception:
                self._forget_reference_auth()
                raise
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            if digest != self._reference_auth_digest:
                self._forget_reference_auth()
                self._reference_auth_digest = digest
            return token

    def _clear_access_token(self) -> None:
        with self._reference_auth_lock:
            self._forget_reference_auth()
            _broker_clear_token(server_url=self.server_url)

    def _forget_reference_auth(self) -> None:
        with self._reference_auth_lock:
            self._reference_auth_epoch += 1
            self._reference_auth_digest = ""
            self._reference_verified_epoch = -1
            self._reference_account_fingerprint = ""
            self._reference_response_proofs.clear()
            self._queue_admission_binding = None
            self._queue_admission_checked_epoch = None

    def _reference_auth_response(self, response: dict[str, Any], epoch: int, *, account: bool = False) -> dict[str, Any]:
        """Keep evidence beside the exact response object, never inside it."""
        with self._reference_auth_lock:
            if epoch != self._reference_auth_epoch or not self._reference_auth_digest:
                return response
            if account:
                principal = _reference_leases.principal_fingerprint(response, self.server_url)
                if principal != self._reference_account_fingerprint:
                    self._reference_response_proofs.clear()
                    self._queue_admission_binding = None
                    self._queue_admission_checked_epoch = None
                self._reference_account_fingerprint = principal
                self._reference_verified_epoch = epoch if principal else -1
            principal = self._reference_account_fingerprint
            if principal and self._reference_verified_epoch == epoch:
                self._reference_response_proofs[id(response)] = (response, epoch, principal)
                # Strong object identity prevents id reuse; bounded retention
                # makes old/evicted responses conservative cleanup holds.
                while len(self._reference_response_proofs) > 16:
                    self._reference_response_proofs.pop(next(iter(self._reference_response_proofs)))
        return response

    @contextmanager
    def _reference_principal_scope(self, response: Any = None) -> Iterator[str]:
        """Hold auth continuity through lease capture/observation without I/O."""
        with self._reference_auth_lock:
            principal = self._reference_account_fingerprint
            if (not self._reference_auth_digest
                    or self._reference_verified_epoch != self._reference_auth_epoch):
                principal = ""
            if response is not None:
                proof = self._reference_response_proofs.get(id(response))
                if (not proof or proof[0] is not response
                        or proof[1] != self._reference_auth_epoch or proof[2] != principal):
                    principal = ""
            yield principal

    def _reference_transfer_response(self, raw: Any, checked: dict[str, Any]) -> dict[str, Any]:
        """Carry evidence only across an explicit successful private projection."""
        with self._reference_principal_scope(raw) as principal:
            if principal:
                self._reference_auth_response(checked, self._reference_auth_epoch)
        return checked

    @staticmethod
    def _safe_account(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", value).strip()
        return cleaned[:128]

    @classmethod
    def _account_from_mapping(cls, value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        for name in (
            "display_name",
            "username",
            "user_name",
            "name",
            "user_id",
            "id",
        ):
            account = cls._safe_account(value.get(name))
            if account:
                return account
        return cls._account_from_mapping(value.get("user"))

    @classmethod
    def _safe_http_error_message(
        cls, exc: urllib.error.HTTPError, *, body: bytes | None = None, secret: str = ""
    ) -> str:
        status_code = int(getattr(exc, "code", 0) or 0)
        if body is None:
            try:
                body = exc.read(cls._MAX_ERROR_CLASSIFICATION_BYTES + 1)
            except Exception:
                body = b""
        if len(body) > cls._MAX_ERROR_CLASSIFICATION_BYTES:
            body = b""
        try:
            detail = json.loads(body or b"{}")
        except (UnicodeError, json.JSONDecodeError):
            detail = {}
        error_code = (
            str(detail.get("error_code") or "").strip().casefold()
            if isinstance(detail, dict)
            else ""
        )
        provider_reason = _volc_failure_reason(detail)
        if provider_reason:
            return provider_reason + f" [Broker HTTP {status_code}]"
        lowered = body.decode("utf-8", "replace").casefold()
        summary = cls._http_error_summary(status_code, error_code, lowered)
        safe_detail = _broker_error_details(detail, secret=secret)
        return summary + ("\nServer details: " + safe_detail if safe_detail else "")

    @staticmethod
    def _http_error_summary(status_code: int, error_code: str, lowered: str) -> str:
        # Classification and submission/retry decisions remain unchanged.
        if status_code == 413 or error_code == "request_body_too_large" or any(
            token in lowered
            for token in ("request body", "too large", "payload", "너무 큽")
        ):
            return (
                "FN AI Broker rejected an oversized reference-media request "
                f"(HTTP {status_code}). Update/restart the Broker media build or "
                "reduce embedded image/audio data."
            )
        if status_code != 400:
            return f"FN AI Broker request failed with HTTP {status_code}."
        if any(
            token in lowered
            for token in (
                "image_url",
                "video_url",
                "audio_url",
                "reference",
                "base64",
                "data uri",
                "data_uri",
            )
        ):
            return (
                "FN AI Broker rejected the reference-media fields (HTTP 400). "
                "Check the connected image, video, and audio inputs."
            )
        if any(
            token in lowered
            for token in (
                "duration",
                "quality",
                "resolution",
                "aspect_ratio",
                "generate_audio",
                "content_filter",
                "web_search",
            )
        ):
            return (
                "FN AI Broker rejected the generation settings (HTTP 400). "
                "Check duration, resolution, ratio, and audio settings."
            )
        if "prompt" in lowered:
            return (
                "FN AI Broker rejected the prompt/content combination (HTTP 400). "
                "Provide a prompt or supported reference media."
            )
        if "model" in lowered:
            return "FN AI Broker rejected the selected model (HTTP 400)."
        return (
            "FN AI Broker rejected the generation request (HTTP 400). "
            "Check the model settings and connected reference media."
        )

    def _open_create_request(self, request: Any, *, timeout: float) -> Any:
        """Retry only an exact, same-origin, pre-provider interval rejection."""
        from _hmb_web_rerender import CommandSubmissionOpener

        # A leased web operation permits one attempted POST. Its server row
        # and fence must never be bypassed by native cooldown retry logic.
        if isinstance(self._opener, CommandSubmissionOpener):
            _broker_wait_for_http_submission(request, self.server_url)
            _broker_note_native_http_start()
            return self._opener.open(request, timeout=timeout)
        started = time.monotonic()
        last_rejection = None
        for attempt in range(AI_BROKER_INTERVAL_RETRY_MAX_ATTEMPTS):
            deadline = started + AI_BROKER_INTERVAL_RETRY_MAX_SECONDS if attempt else None
            available = _broker_wait_for_http_submission(request, self.server_url, deadline=deadline)
            if attempt and (not available or time.monotonic() >= deadline):
                last_rejection._hmb_interval_retry_exhausted = True
                raise last_rejection
            try:
                _broker_note_native_http_start()
                return self._opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as exc:
                if exc.code != 429:
                    raise
                _broker_require_exact_response_url(exc, request.full_url)
                body = exc.read(self._MAX_ERROR_CLASSIFICATION_BYTES + 1)
                if len(body) > self._MAX_ERROR_CLASSIFICATION_BYTES:
                    body = b""
                # Retain the bounded body for the normal diagnostic path.
                exc._hmb_interval_response_body = body
                delay = _broker_interval_rejection_delay(body)
                if delay is None:
                    raise
                last_rejection = exc
                _broker_note_native_interval_rejection()
                pause = delay + AI_BROKER_INTERVAL_RETRY_MARGIN_SECONDS
                if (attempt + 1 >= AI_BROKER_INTERVAL_RETRY_MAX_ATTEMPTS
                        or time.monotonic() - started + pause > AI_BROKER_INTERVAL_RETRY_MAX_SECONDS):
                    exc._hmb_interval_retry_exhausted = True
                    raise
                deadline = time.monotonic() + pause
                while time.monotonic() < deadline:
                    _broker_check_native_submission()
                    time.sleep(min(0.10, max(0.0, deadline - time.monotonic())))
        raise AssertionError("Broker submission retry budget was not enforced.")

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None,
        timeout: float,
        submission: bool = False,
        idempotency_key: str = "",
        queue_admission: Any = None,
        queue_operation: str = "",
        expected_auth_digest: str = "",
    ) -> dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise _BrokerProtocolError("FN AI Broker request path is invalid.")
        if submission and path in {"/api/v1/generate/video", "/api/v1/generate/image"}:
            import _hmb_queue_admission as queue
            queue.validate_create(payload, path, queue_operation, queue_only=queue_admission is not None)
        body = None
        with self._reference_auth_lock:
            token = self._load_access_token()
            if expected_auth_digest and hashlib.sha256(token.encode("utf-8")).hexdigest() != expected_auth_digest:
                raise _DraftFinalPreflightError("The Broker account changed before the Draft Final request.")
            reference_auth_epoch = self._reference_auth_epoch
            queue_headers = {}
            if queue_admission is not None:
                if not submission or method.upper() != "POST" or path not in {"/api/v1/generate/video", "/api/v1/generate/image"}:
                    raise _BrokerProtocolError("Queue admission is restricted to an explicit create request.")
                queue_headers = self._queue_admission_headers(queue_admission, queue_operation)
        headers = {"Accept": "application/json", "Authorization": "Bearer " + token}
        headers.update(queue_headers)
        if idempotency_key:
            if _TASK_ID_PATTERN.fullmatch(idempotency_key) is None:
                raise _BrokerProtocolError(
                    "FN AI Broker idempotency key is invalid."
                )
            headers["Idempotency-Key"] = idempotency_key
        if payload is not None:
            body = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            if len(body) > MAX_REQUEST_BYTES:
                raise ValueError(
                    "FN AI Broker request body exceeds the 64 MB limit. "
                    "Reduce or externally host reference media."
                )
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            _broker_config.join_broker_url(self.server_url, path),
            data=body,
            headers=headers,
            method=method.upper(),
        )
        try:
            open_request = self._open_create_request if (submission and method.upper() == "POST"
                                                        and path == "/api/v1/generate/video") else self._opener.open
            with open_request(request, timeout=timeout) as response:
                _broker_require_exact_response_url(response, request.full_url)
                result = _broker_read_json(
                    response, max_bytes=AI_BROKER_MAX_JSON_BYTES
                )
                status_code = int(getattr(response, "status", 200))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                with suppress(Exception):
                    self._clear_access_token()
                raise _BrokerAuthenticationError(
                    "FN AI Broker login has expired.\n"
                    + self._safe_http_error_message(
                        exc, secret=headers["Authorization"][7:]
                    ),
                    status_code=401,
                ) from exc
            error_body: bytes | None = getattr(exc, "_hmb_interval_response_body", None)
            if (exc.code == 404 and method == "POST" and path == "/api/v1/preflight/griptape-cloud"
                    and self.server_url == _broker_config.DEFAULT_BROKER_BASE_URL and payload == {}
                    and not submission):
                _broker_require_exact_response_url(exc, request.full_url)
                content_type = (exc.headers or {}).get("Content-Type", "").partition(";")[0].strip().lower()
                if content_type == "application/json":
                    with exc:
                        error_body = exc.read(1025)
                    try:
                        missing = json.loads(error_body) if len(error_body) <= 1024 else None
                    except (UnicodeError, ValueError):
                        missing = None
                    if missing == {"error": "API를 찾을 수 없습니다"}:
                        return {"_http_status": 404, **missing}
            if submission and path == "/api/v1/generate/video" and exc.code in {422, 429}:
                if error_body is None:
                    try:
                        error_body = exc.read(self._MAX_ERROR_CLASSIFICATION_BYTES + 1)
                    except OSError:
                        error_body = b""
                if len(error_body) <= self._MAX_ERROR_CLASSIFICATION_BYTES:
                    cloud_error = _CloudReferenceCheckError.from_body(
                        error_body, exc.code, private=isinstance(payload, dict) and "my_box_selection" in payload,
                    )
                    if cloud_error is not None:
                        raise cloud_error from None
            if (
                not submission
                and method.upper() == "POST"
                and re.fullmatch(r"/api/v1/jobs/[^/]+/refresh", path)
                and (exc.code == 410 or 500 <= int(exc.code) <= 599)
            ):
                # Some Broker builds return the durable task's failure inside
                # HTTP 502. A status lookup is not a create request: consume an
                # explicit terminal job record, not the gateway code alone.
                # The caller still verifies exact/canonical task identity.
                _broker_require_exact_response_url(exc, request.full_url)
                try:
                    error_body = exc.read(self._MAX_ERROR_CLASSIFICATION_BYTES + 1)
                    if len(error_body) > self._MAX_ERROR_CLASSIFICATION_BYTES:
                        error_body = b""
                    terminal_result = json.loads(error_body or b"{}")
                except (OSError, UnicodeError, json.JSONDecodeError):
                    terminal_result = {}
                terminal_id = str(
                    terminal_result.get("job_id")
                    or terminal_result.get("id")
                    or terminal_result.get("task_id")
                    or ""
                ).strip() if isinstance(terminal_result, dict) else ""
                if (
                    isinstance(terminal_result, dict)
                    and _TASK_ID_PATTERN.fullmatch(terminal_id) is not None
                    and str(terminal_result.get("status") or "").strip().lower()
                    in (BROKER_FAILURE_STATUSES | BROKER_CANCELLED_STATUSES | BROKER_EXPIRED_STATUSES)
                ):
                    terminal_result["_http_status"] = int(exc.code)
                    return self._reference_auth_response(terminal_result, reference_auth_epoch)
            message = self._safe_http_error_message(
                    exc, body=error_body, secret=headers["Authorization"][7:]
                )
            if getattr(exc, "_hmb_interval_retry_exhausted", False):
                message += "\nBroker submission cooldown retry limit reached. These interval-rejected requests did not start a provider render."
            raise _BrokerError(
                message,
                status_code=exc.code,
                # A gateway/server failure does not prove that an idempotent
                # create was never accepted upstream. Preserve the provisional
                # client request ID and recover through Refresh instead of
                # allowing a second create with a different key.
                submission_outcome_unknown=bool(
                    submission and 500 <= int(exc.code) <= 599
                ),
            ) from exc
        except _BrokerError as exc:
            # The POST has already crossed the transport boundary. An invalid
            # JSON/origin response cannot prove that it was never accepted.
            # HTTP rejections are classified separately above; preflight errors
            # normally occur before this try block. The command-bound web
            # opener also completes a separate prepared handshake inside open;
            # only its internal exception marker proves the create never began.
            # Response bodies and caller payloads cannot set this marker.
            if submission and getattr(exc, "_hmb_web_submission_not_started", False) is not True:
                exc.submission_outcome_unknown = True
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            not_started = getattr(exc, "_hmb_web_submission_not_started", False) is True
            _broker_log_transport_error(
                stage="broker_web_prepared" if not_started else "broker_submission" if submission else "broker_request",
                attempt=1,
                exc=exc,
                server_url=self.server_url,
            )
            unavailable = _BrokerUnavailableError(
                "FN AI Broker did not respond.",
                submission_outcome_unknown=bool(submission and not not_started),
            )
            if not_started:
                unavailable._hmb_web_submission_not_started = True
            raise unavailable from exc
        if not isinstance(result, dict):
            raise _BrokerProtocolError(
                "FN AI Broker returned an invalid response.",
                submission_outcome_unknown=submission,
            )
        result["_http_status"] = status_code
        account_read = method.upper() == "GET" and path == "/api/me"
        result = self._reference_auth_response(result, reference_auth_epoch, account=account_read)
        return result

    def account_snapshot(self, *, connect: bool) -> _BrokerAccountSnapshot:
        # Only this call's authenticated /api/me response can authorize release
        # of temporary references. Never reuse a prior account after 401/error.
        with self._reference_auth_lock:
            self._reference_account_fingerprint = ""
            self._reference_verified_epoch = -1
            self._reference_response_proofs.clear()
        login_result: dict[str, Any] = {}
        me_result: dict[str, Any] = {}
        try:
            me_result = self._request_json(
                "GET", "/api/me", payload=None, timeout=3
            )
            logged_in = True
        except _BrokerAuthenticationError:
            logged_in = False
        except _BrokerError:
            raise
        if not logged_in:
            if not connect:
                return _BrokerAccountSnapshot("login_required", False, "")
            login_result = _broker_device_login(opener=self._opener, server_url=self.server_url)
            status = str(login_result.get("status") or "").strip().lower()
            if status in {"pending", "rejected", "blocked"}:
                return _BrokerAccountSnapshot("approval_" + status, False, "")
        account = self._account_from_mapping(login_result)
        me = (
            me_result
            if logged_in
            else self._request_json("GET", "/api/me", payload=None, timeout=10)
        )
        account = self._account_from_mapping(me) or account
        # The transport binds only the principal from this exact /api/me
        # request's bearer epoch. A late response cannot revive an old account.
        return _BrokerAccountSnapshot("connected", True, account)

    def refresh_job(self, job_id: str, *, timeout: float = 300) -> dict[str, Any]:
        value = str(job_id or "").strip()
        if _TASK_ID_PATTERN.fullmatch(value) is None:
            raise _BrokerProtocolError("FN AI Broker job ID is invalid.")
        return self._request_json(
            "POST",
            "/api/v1/jobs/" + quote(value, safe="") + "/refresh",
            payload=None,
            timeout=timeout,
        )
