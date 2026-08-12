from __future__ import annotations

import asyncio
import base64
import binascii
import ctypes
import importlib
import ipaddress
import json
import logging
import mimetypes
import os
import re
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Iterator
from contextlib import suppress
from copy import deepcopy
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse
from uuid import uuid4

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import (
    GriptapeCloudStorageDriver,
)
from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import (
    ProjectFileParameter,
)
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_button import ParameterButton
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import MacroPath
from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import write_sidecar
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from _hmb_mp4_verify import (
    MP4DecodeVerifier as _MP4DecodeVerifier,
    MP4_DECODE_PROBE_MAX_OUTPUT_BYTES,
    MP4_DECODE_PROBE_PACKET_LIMIT,
    MP4_DECODE_PROBE_TIMEOUT_SECONDS,
    MP4_DECODE_VERIFIER_START_TIMEOUT_SECONDS,
    resolve_mp4_decode_verifier as _resolve_mp4_decode_verifier,
    validate_decodable_mp4_file as _validate_decodable_mp4_file,
)

logger = logging.getLogger("griptape_nodes")

GT_CLOUD_API_KEY_SECRET = "GT_CLOUD_API_KEY"
GT_CLOUD_BUCKET_ID_SECRET = "GT_CLOUD_BUCKET_ID"
TOS_ACCESS_KEY_ID_SECRET = "TOS_ACCESS_KEY_ID"
TOS_SECRET_ACCESS_KEY_SECRET = "TOS_SECRET_ACCESS_KEY"
TOS_BUCKET_NAME_SECRET = "TOS_BUCKET_NAME"
AI_BROKER_SERVER_URL = os.environ.get(
    "HMB_AI_BROKER_URL", "http://192.168.203.245:8080"
).rstrip("/")
AI_BROKER_MAX_JSON_BYTES = 16 * 1024 * 1024
AI_BROKER_DEVICE_AUTH_TIMEOUT_SECONDS = 5 * 60
AI_BROKER_DEVICE_POLL_SECONDS = 2.0
AI_BROKER_DEVICE_START_BACKOFF_SECONDS = (0.0, 0.5, 1.5)
AI_BROKER_DEVICE_POLL_MAX_CONSECUTIVE_TRANSPORT_ERRORS = 3

LOCAL_VIDEO_UPLOAD_GRIPTAPE = "Griptape Cloud (Existing)"
LOCAL_VIDEO_UPLOAD_TOS = "Volcengine TOS"
LOCAL_VIDEO_UPLOAD_SERVICES = (
    LOCAL_VIDEO_UPLOAD_GRIPTAPE,
    LOCAL_VIDEO_UPLOAD_TOS,
)
DEFAULT_TOS_REGION = "cn-beijing"
DEFAULT_TOS_ENDPOINT = "tos-cn-beijing.volces.com"


def _is_structurally_valid_mp4(value: bytes | bytearray) -> bool:
    """Require complete top-level ftyp, moov, and mdat boxes before publish."""

    data = bytes(value)
    if len(data) < 32:
        return False
    offset = 0
    boxes = 0
    saw_movie_box = False
    saw_media_data_box = False
    while offset + 8 <= len(data) and boxes < 4096:
        size = int.from_bytes(data[offset : offset + 4], "big")
        box_type = data[offset + 4 : offset + 8]
        header_size = 8
        if size == 1:
            if offset + 16 > len(data):
                return False
            size = int.from_bytes(data[offset + 8 : offset + 16], "big")
            header_size = 16
        elif size == 0:
            size = len(data) - offset
        if size < header_size or offset + size > len(data):
            return False
        if boxes == 0:
            if box_type != b"ftyp" or size < header_size + 8:
                return False
            if (size - header_size - 8) % 4 != 0:
                return False
        elif box_type == b"moov" and size > header_size:
            saw_movie_box = True
        elif box_type == b"mdat" and size > header_size:
            saw_media_data_box = True
        offset += size
        boxes += 1
    return offset == len(data) and saw_movie_box and saw_media_data_box


DEFAULT_TOS_URL_VALIDITY_SECONDS = 24 * 60 * 60
MIN_TOS_URL_VALIDITY_SECONDS = 60 * 60
MAX_TOS_URL_VALIDITY_SECONDS = 30 * 24 * 60 * 60
TOS_TEMP_OBJECT_PREFIX = "hmb-seedance-temp"

INPUT_MODE_TEXT_ONLY = "Text Only"
INPUT_MODE_FIRST_LAST_FRAME = "First/Last Frame"
INPUT_MODE_MULTIMODAL_REFERENCES = "Multimodal References"

MODEL_NAME_SEEDANCE_2_0 = "Seedance 2.0"
MODEL_NAME_SEEDANCE_2_0_FAST = "Seedance 2.0 Fast"
MODEL_NAME_SEEDANCE_2_0_MINI = "Seedance 2.0 Mini"

SEEDANCE_2_0_MODEL_ID = "doubao-seedance-2-0-260128"
SEEDANCE_2_0_FAST_MODEL_ID = "doubao-seedance-2-0-fast-260128"
SEEDANCE_2_0_MINI_MODEL_ID = "doubao-seedance-2-0-mini-260615"

# The FN AI Broker Volcengine adapter accepts the full, Fast, and Mini Seedance
# 2.0 endpoints. Keep this allowlist explicit so an arbitrary catalog entry can
# never be submitted merely because it contains "seedance" in its name.
BROKER_SUPPORTED_MODEL_IDS = frozenset(
    {
        SEEDANCE_2_0_MODEL_ID,
        SEEDANCE_2_0_FAST_MODEL_ID,
        SEEDANCE_2_0_MINI_MODEL_ID,
    }
)

# Old display and BytePlus model values remain accepted so saved workflows migrate
# without silently submitting an obsolete provider model id.
MODEL_ID_ALIASES = {
    MODEL_NAME_SEEDANCE_2_0: SEEDANCE_2_0_MODEL_ID,
    MODEL_NAME_SEEDANCE_2_0_FAST: SEEDANCE_2_0_FAST_MODEL_ID,
    MODEL_NAME_SEEDANCE_2_0_MINI: SEEDANCE_2_0_MINI_MODEL_ID,
    "dreamina-seedance-2-0-260128": SEEDANCE_2_0_MODEL_ID,
    "dreamina-seedance-2-0-fast-260128": SEEDANCE_2_0_FAST_MODEL_ID,
    "dreamina-seedance-2-0-mini-260615": SEEDANCE_2_0_MINI_MODEL_ID,
    SEEDANCE_2_0_MODEL_ID: SEEDANCE_2_0_MODEL_ID,
    SEEDANCE_2_0_FAST_MODEL_ID: SEEDANCE_2_0_FAST_MODEL_ID,
    SEEDANCE_2_0_MINI_MODEL_ID: SEEDANCE_2_0_MINI_MODEL_ID,
}

MODEL_RESOLUTIONS = {
    SEEDANCE_2_0_MODEL_ID: ("4k", "1080p", "720p", "480p"),
    SEEDANCE_2_0_FAST_MODEL_ID: ("720p", "480p"),
    SEEDANCE_2_0_MINI_MODEL_ID: ("720p", "480p"),
}

MODEL_DEFAULT_RESOLUTIONS = {
    SEEDANCE_2_0_MODEL_ID: "1080p",
    SEEDANCE_2_0_FAST_MODEL_ID: "720p",
    SEEDANCE_2_0_MINI_MODEL_ID: "720p",
}

RATIOS = ("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
TERMINAL_FAILURE_STATUSES = {"failed", "cancelled", "expired"}
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}

BROKER_ACTIVE_STATUSES = {
    "pending",
    "queued",
    "running",
    "processing",
    "submitted",
    "in_progress",
}
BROKER_SUCCESS_STATUSES = {"completed", "succeeded", "success", "done"}
BROKER_FAILURE_STATUSES = {"failed", "error", "rejected"}
BROKER_CANCELLED_STATUSES = {"cancelled", "canceled"}
BROKER_EXPIRED_STATUSES = {"expired"}

MAX_REFERENCE_IMAGES = 9
MAX_VIDEO_REFERENCES = 3
MAX_REFERENCE_AUDIO = 3
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
MAX_ATOMIC_OUTPUT_CANDIDATES = 10_000
AMBIGUOUS_UPLOAD_CLEANUP_DELAY_SECONDS = 30 * 60

VIDEO_REFERENCES_PARAMETER = "VIDEO_REFERENCES"

IMAGE_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
}
AUDIO_MIME_BY_SUFFIX = {
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
}
ALLOWED_IMAGE_MIMES = frozenset(IMAGE_MIME_BY_SUFFIX.values())
ALLOWED_AUDIO_MIMES = frozenset(AUDIO_MIME_BY_SUFFIX.values())
AUDIO_MIME_ALIASES = {
    "audio/mpeg": "audio/mp3",
    "audio/x-mp3": "audio/mp3",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
}

_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_BROKER_PUBLIC_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TOS_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?i)(authorization|(?:^|[_-])key(?:$|[_-])|api[_-]?key|provider[_-]?key|"
    r"token|secret|credential|cookie|session|exchange[_-]?code|usage[_-]?code)"
)
_DATA_URI_PATTERN = re.compile(
    r"^data:(?P<mime>[-\w.+/]+);base64,(?P<data>[A-Za-z0-9+/=\r\n]+)$",
    re.DOTALL,
)

class _BrokerError(RuntimeError):
    """Safe Broker failure without response bodies or credential values."""

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


class _BrokerUnavailableError(_BrokerError):
    pass


class _BrokerAuthenticationError(_BrokerError):
    pass


class _BrokerProtocolError(_BrokerError):
    pass


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
    """Build a Broker-only opener that never inherits machine proxy settings."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _BrokerNoRedirectHandler(),
    )


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


def _broker_validated_server_url() -> str:
    parsed = urlparse(AI_BROKER_SERVER_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise _BrokerUnavailableError("FN AI Broker server URL is invalid.")
    if parsed.username is not None or parsed.password is not None:
        raise _BrokerUnavailableError(
            "FN AI Broker server URL must not contain credentials."
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise _BrokerUnavailableError(
            "FN AI Broker server URL must contain only an origin."
        )
    return AI_BROKER_SERVER_URL


def _broker_token_path() -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home())
    directory = root / "FNAIBroker"
    directory.mkdir(parents=True, exist_ok=True)
    current = directory / "access_token_v2.dpapi"
    legacy = root / "CompanyAIBroker" / "access_token_v2.dpapi"
    if not current.is_file() and legacy.is_file():
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


def _broker_save_token(token: str) -> None:
    value = str(token or "").strip()
    if not value:
        raise _BrokerProtocolError("FN AI Broker returned an empty access token.")
    destination = _broker_token_path()
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(_broker_dpapi(value.encode("utf-8"), protect=True))
    os.replace(temporary, destination)


def _broker_clear_token() -> None:
    root = Path(os.environ.get("APPDATA") or Path.home())
    for path in (
        root / "FNAIBroker" / "access_token_v2.dpapi",
        root / "CompanyAIBroker" / "access_token_v2.dpapi",
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _broker_load_token() -> str:
    path = _broker_token_path()
    if not path.is_file():
        raise _BrokerAuthenticationError("FN AI Broker login is required.")
    try:
        token = _broker_dpapi(path.read_bytes(), protect=False).decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise _BrokerAuthenticationError(
            "The saved FN AI Broker login is unavailable. Connect again."
        ) from exc
    token = token.strip()
    if not token:
        raise _BrokerAuthenticationError("FN AI Broker login is required.")
    return token


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


def _broker_device_login(*, opener: Any | None = None) -> dict[str, Any]:
    """Authorize this Windows account once and persist the resulting Broker token."""
    server_url = _broker_validated_server_url()
    request_opener = opener if opener is not None else _broker_build_opener()

    for start_attempt, backoff_seconds in enumerate(
        AI_BROKER_DEVICE_START_BACKOFF_SECONDS,
        start=1,
    ):
        if backoff_seconds:
            time.sleep(backoff_seconds)
        start_request = urllib.request.Request(
            server_url + "/api/device/start",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request_opener.open(start_request, timeout=10) as response:
                start_result = _broker_read_json(
                    response, max_bytes=2 * 1024 * 1024
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
    if (
        _TASK_ID_PATTERN.fullmatch(device_code) is None
        or len(device_secret) < 20
        or not _broker_same_origin(verification_url, server_url)
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
            server_url + "/api/device/token",
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
            _broker_save_token(access_token)
            return {"status": "connected"}
        raise _BrokerProtocolError(
            "FN AI Broker device token response was invalid."
        )

    raise _BrokerAuthenticationError(
        "FN AI Broker authorization timed out. Connect again."
    )


class _HMBAIBrokerBridge:
    _MAX_ERROR_CLASSIFICATION_BYTES = 64 * 1024
    _ALLOWED_GENERATION_FIELDS = frozenset(
        {
            "provider",
            "model",
            "prompt",
            "input_mode",
            "first_frame",
            "last_frame",
            "image_urls",
            "video_urls",
            "audio_urls",
            "duration_seconds",
            "quality",
            "resolution",
            "aspect_ratio",
            "generate_audio",
            "watermark",
            "web_search",
            "content_filter",
            "return_last_frame",
            "execution_expires_after",
            "priority",
            "client_request_id",
        }
    )
    _COMMON_SEEDANCE_FIELDS = frozenset(
        {
            "provider",
            "model",
            "prompt",
            "image_urls",
            "video_urls",
            "audio_urls",
            "duration_seconds",
            "quality",
            "resolution",
            "aspect_ratio",
            "generate_audio",
            "watermark",
            "web_search",
            "content_filter",
            "client_request_id",
        }
    )
    _REFERENCE_MODE_FIELDS = frozenset(
        {
            "input_mode",
            "first_frame",
            "last_frame",
            "return_last_frame",
            "execution_expires_after",
        }
    )
    _MODEL_GENERATION_FIELDS = {
        SEEDANCE_2_0_MODEL_ID: _COMMON_SEEDANCE_FIELDS
        | _REFERENCE_MODE_FIELDS
        | frozenset({"priority"}),
        SEEDANCE_2_0_FAST_MODEL_ID: _COMMON_SEEDANCE_FIELDS
        | _REFERENCE_MODE_FIELDS,
        SEEDANCE_2_0_MINI_MODEL_ID: _COMMON_SEEDANCE_FIELDS
        | _REFERENCE_MODE_FIELDS,
    }
    def __init__(self, *, opener: Any | None = None) -> None:
        self._opener = opener if opener is not None else _broker_build_opener()

    @property
    def server_url(self) -> str:
        return _broker_validated_server_url()

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
    def _safe_http_error_message(cls, exc: urllib.error.HTTPError) -> str:
        status_code = int(getattr(exc, "code", 0) or 0)
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
        lowered = body.decode("utf-8", "replace").casefold()
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

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None,
        timeout: float,
        submission: bool = False,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise _BrokerProtocolError("FN AI Broker request path is invalid.")
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + _broker_load_token(),
        }
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
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.server_url + path,
            data=body,
            headers=headers,
            method=method.upper(),
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                result = _broker_read_json(
                    response, max_bytes=AI_BROKER_MAX_JSON_BYTES
                )
                status_code = int(getattr(response, "status", 200))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                with suppress(Exception):
                    _broker_clear_token()
                raise _BrokerAuthenticationError(
                    "FN AI Broker login has expired.", status_code=401
                ) from exc
            if exc.code == 410 and not submission:
                try:
                    expired_result = json.loads(
                        exc.read(self._MAX_ERROR_CLASSIFICATION_BYTES) or b"{}"
                    )
                except (UnicodeError, json.JSONDecodeError):
                    expired_result = {}
                if (
                    isinstance(expired_result, dict)
                    and str(expired_result.get("status") or "").strip().lower()
                    in BROKER_EXPIRED_STATUSES
                ):
                    expired_result["_http_status"] = 410
                    return expired_result
            raise _BrokerError(
                self._safe_http_error_message(exc),
                status_code=exc.code,
            ) from exc
        except _BrokerError:
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            _broker_log_transport_error(
                stage="broker_submission" if submission else "broker_request",
                attempt=1,
                exc=exc,
                server_url=self.server_url,
            )
            raise _BrokerUnavailableError(
                "FN AI Broker did not respond.",
                submission_outcome_unknown=submission,
            ) from exc
        if not isinstance(result, dict):
            raise _BrokerProtocolError(
                "FN AI Broker returned an invalid response."
            )
        result["_http_status"] = status_code
        return result

    def account_snapshot(self, *, connect: bool) -> _BrokerAccountSnapshot:
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
            login_result = _broker_device_login()
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
        return _BrokerAccountSnapshot("connected", True, account)

    def generate_seedance(
        self,
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        if set(payload) - self._ALLOWED_GENERATION_FIELDS:
            raise _BrokerProtocolError(
                "Seedance Broker payload contained unsupported fields."
            )
        request_payload = {
            key: value
            for key, value in payload.items()
            if value is not None and value != []
        }
        request_payload["provider"] = "volcengine_ark"
        model = str(request_payload.get("model") or "").strip()
        if not model:
            raise _BrokerProtocolError("Seedance Broker model is missing.")
        model_fields = self._MODEL_GENERATION_FIELDS.get(model)
        if model_fields is None:
            raise _BrokerProtocolError(
                "Selected Seedance model is not supported by the HMB Broker contract."
            )
        priority = request_payload.get("priority")
        if model != SEEDANCE_2_0_MODEL_ID and priority not in (None, 0):
            raise _BrokerProtocolError(
                "Task priority is supported only by the full Seedance 2.0 model."
            )
        request_payload = {
            key: value for key, value in request_payload.items() if key in model_fields
        }
        client_request_id = str(
            request_payload.get("client_request_id") or ""
        ).strip()
        if client_request_id and _TASK_ID_PATTERN.fullmatch(client_request_id) is None:
            raise _BrokerProtocolError(
                "Seedance Broker client request ID is invalid."
            )
        return self._request_json(
            "POST",
            "/api/v1/generate/video",
            payload=request_payload,
            timeout=timeout,
            submission=True,
            idempotency_key=client_request_id,
        )

    def refresh_job(self, job_id: str, *, timeout: float = 60) -> dict[str, Any]:
        value = str(job_id or "").strip()
        if _TASK_ID_PATTERN.fullmatch(value) is None:
            raise _BrokerProtocolError("FN AI Broker job ID is invalid.")
        return self._request_json(
            "POST",
            "/api/v1/jobs/" + quote(value, safe="") + "/refresh",
            payload=None,
            timeout=timeout,
        )

    def is_trusted_broker_url(self, url: str) -> bool:
        candidate = urlparse(str(url or ""))
        broker = urlparse(self.server_url)

        def origin(parsed: Any) -> tuple[str, str, int]:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return parsed.scheme.lower(), (parsed.hostname or "").lower(), port

        try:
            return origin(candidate) == origin(broker)
        except ValueError:
            return False

    def download_trusted_result(self, url: str, *, max_bytes: int) -> bytes:
        if not self.is_trusted_broker_url(url):
            raise _BrokerProtocolError(
                "Broker authorization was refused for an external URL."
            )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "video/mp4,application/octet-stream",
                "Authorization": "Bearer " + _broker_load_token(),
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=300) as response:
                raw = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise _BrokerError(
                f"FN AI Broker result download failed with HTTP {exc.code}.",
                status_code=exc.code,
            ) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            _broker_log_transport_error(
                stage="broker_result_download",
                attempt=1,
                exc=exc,
                server_url=self.server_url,
            )
            raise _BrokerUnavailableError(
                "FN AI Broker result download failed."
            ) from exc
        if len(raw) > max_bytes:
            raise _BrokerProtocolError("Downloaded video exceeds the size limit.")
        if len(raw) < 12 or raw[4:8] != b"ftyp":
            raise _BrokerProtocolError(
                "Downloaded result is not a valid MP4 container."
            )
        return raw


class LocalReferenceVideoError(RuntimeError):
    """A selected local/project video cannot be resolved or read."""


class HMBSeedanceGeneration(SuccessFailureNode):
    """Generate video with a supported Seedance model through FN AI Broker.

    This retains the existing HMB node identity, accepts ordered image and video
    lists from the HMB media libraries, and keeps provider credentials on the
    Broker server. Former scalar video inputs remain hidden for saved-workflow
    compatibility. No provider API key is exposed through node parameters,
    outputs, logs, or serialized workflow state.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "HMB_GP_Production"
        self.description = (
            "Generate video with a supported Seedance model through the "
            "authenticated FN AI Broker using server-managed provider credentials."
        )
        self._temporary_video_uploads: list[
            tuple[GriptapeCloudStorageDriver, Path]
        ] = []
        self._temporary_tos_video_uploads: list[tuple[Any, str, str]] = []
        self._submission_outcome_unknown = False
        self._detached_submission_tasks: set[asyncio.Task[Any]] = set()
        self._broker_bridge_instance: _HMBAIBrokerBridge | None = None
        self._last_broker_payload: dict[str, Any] | None = None
        self._broker_action_lock = threading.Lock()
        self._broker_action_running = False
        self._generation_refresh_lock = threading.Lock()
        self._generation_refresh_running = False
        self._generation_run_active = threading.Event()

        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value=MODEL_NAME_SEEDANCE_2_0,
                tooltip=(
                    "Volcengine Seedance 2.0 model. The full model defaults to "
                    "1080p (1K); Fast and Mini support up to 720p."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            MODEL_NAME_SEEDANCE_2_0,
                            MODEL_NAME_SEEDANCE_2_0_FAST,
                            MODEL_NAME_SEEDANCE_2_0_MINI,
                        ]
                    )
                },
                ui_options={"display_name": "Model"},
            )
        )
        self.add_parameter(
            ParameterString(
                name="input_mode",
                default_value=INPUT_MODE_MULTIMODAL_REFERENCES,
                tooltip=(
                    "Text Only, First/Last Frame, or Multimodal References. "
                    "The HMB default remains Multimodal References."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            INPUT_MODE_TEXT_ONLY,
                            INPUT_MODE_FIRST_LAST_FRAME,
                            INPUT_MODE_MULTIMODAL_REFERENCES,
                        ]
                    )
                },
                ui_options={"display_name": "Input Mode"},
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="Text prompt for the selected Seedance model.",
                multiline=True,
                placeholder_text="Describe the desired video...",
                allow_output=False,
                ui_options={"display_name": "Prompt"},
            )
        )
        self.add_parameter(
            ParameterImage(
                name="first_frame",
                default_value=None,
                tooltip="First-frame image for First/Last Frame mode.",
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
                ui_options={"display_name": "First Frame"},
            )
        )
        self.add_parameter(
            ParameterImage(
                name="last_frame",
                default_value=None,
                tooltip="Optional last-frame image for First/Last Frame mode.",
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
                ui_options={"display_name": "Last Frame"},
            )
        )
        self.add_parameter(
            Parameter(
                name="reference_images",
                type="list[str]",
                input_types=[
                    "list[str]",
                    "list[ImageUrlArtifact]",
                    "list[ImageArtifact]",
                    "list[BytePlusImageAssetReference]",
                ],
                default_value=[],
                tooltip=(
                    "Ordered reference-image list from HMBImageAssetLibrary "
                    "Video Generation Out (0-9). Connect the entire selection "
                    "with one wire; list order becomes Seedance image order."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
                ui_options={
                    "display_name": "Reference Images",
                    "hide_property": True,
                },
            )
        )

        # Keep the former three scalar ports registered but hidden so workflows
        # saved with those exact parameter names continue to resolve. New HMB
        # workflows use the ordered VIDEO_REFERENCES list below.
        for index in range(1, MAX_VIDEO_REFERENCES + 1):
            video_parameter = Parameter(
                name=f"reference_video_{index}",
                type="VideoUrlArtifact",
                input_types=[
                    "VideoUrlArtifact",
                    "BytePlusVideoAssetReference",
                ],
                default_value="",
                tooltip=(
                    f"Optional reference video {index}. Public URLs and asset:// "
                    "references pass through; a local MP4 can be temporarily "
                    "published through the selected upload service at execution time."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
                hide=True,
                ui_options={
                    "display_name": f"Legacy Reference Video {index}",
                    "hide": True,
                    "hide_property": True,
                },
            )
            self.add_parameter(video_parameter)
            video_parameter.set_badge(
                variant="cloud-upload",
                title="Media Upload",
                message=(
                    "Local video files are temporarily uploaded through the selected "
                    "service so the selected Seedance model can read them. The temporary "
                    "object is deleted when this node execution ends."
                ),
                hide_clear_button=False,
            )

        # The Picker publishes one ordered list. Reusing the existing HMB list
        # name also restores workflows created before the temporary scalar UI.
        self.add_parameter(
            Parameter(
                name=VIDEO_REFERENCES_PARAMETER,
                type="list[str]",
                input_types=[
                    "list[str]",
                    "list[VideoUrlArtifact]",
                    "list[BytePlusVideoAssetReference]",
                ],
                output_type="list[str]",
                default_value=[],
                tooltip=(
                    "Ordered reference-video list from HMBVideoPickerLibrary "
                    "VIDEO OUT (0-3). Connect the complete selected list with "
                    "one wire; Picker selection order becomes Seedance order."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide=False,
                hide_property=True,
                ui_options={
                    "display_name": "Reference Videos",
                    "hide": False,
                    "hide_property": True,
                },
            )
        )
        self.add_parameter(
            ParameterList(
                name="reference_audio",
                input_types=[
                    "AudioArtifact",
                    "AudioUrlArtifact",
                    "str",
                    "BytePlusAudioAssetReference",
                ],
                default_value=[],
                tooltip=(
                    "Optional reference audio (0-3). Local MP3/WAV files are "
                    "encoded as data URIs; audio requires an image or video reference."
                ),
                allowed_modes={ParameterMode.INPUT},
                ui_options={
                    "display_name": "Reference Audio",
                    "expander": True,
                    "hide_property": True,
                },
                max_items=MAX_REFERENCE_AUDIO,
            )
        )

        with ParameterGroup(name="Generation Settings") as generation_settings:
            ParameterString(
                name="resolution",
                default_value=MODEL_DEFAULT_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID],
                tooltip=(
                    "Full Seedance 2.0 defaults to 1080p (1K). Fast and Mini support "
                    "480p and 720p."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=list(MODEL_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID]))},
            )
            ParameterString(
                name="ratio",
                default_value="adaptive",
                tooltip="Output aspect ratio.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=list(RATIOS))},
            )
            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Duration: 4-15 seconds, or -1 for smart duration.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[-1, *range(4, 16)])},
            )
            ParameterBool(
                name="generate_audio",
                default_value=False,
                tooltip="Generate audio with the video. Disabled by default on new nodes.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        self.add_node_element(generation_settings)

        with ParameterGroup(name="Volcengine Advanced") as advanced_settings:
            ParameterString(
                name="resume_generation_id",
                default_value="",
                tooltip=(
                    "Resume polling and download for an existing FN AI Broker task ID. "
                    "When set, this node skips the billable create-task POST."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Resume Task ID"},
            )
            ParameterBool(
                name="watermark",
                default_value=False,
                tooltip="Add the provider watermark.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterBool(
                name="return_last_frame",
                default_value=False,
                tooltip="Ask Ark to return the generated last-frame URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterInt(
                name="execution_expires_after",
                default_value=172800,
                tooltip="Provider task expiry in seconds (3600-259200).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterInt(
                name="priority",
                default_value=0,
                tooltip=(
                    "Provider task priority (0-9), supported by the full "
                    "Seedance 2.0 model only."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterInt(
                name="poll_interval_seconds",
                default_value=30,
                tooltip="Seconds between task status checks.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterInt(
                name="generation_timeout_seconds",
                default_value=3600,
                tooltip="Maximum local polling time in seconds.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterBool(
                name="auto_publish_local_videos",
                default_value=True,
                tooltip=(
                    "Temporarily publish local reference MP4 files through the "
                    "selected upload service."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Auto Publish Local Videos"},
            )
            ParameterString(
                name="local_video_upload_service",
                default_value=LOCAL_VIDEO_UPLOAD_GRIPTAPE,
                tooltip=(
                    "Existing storage remains the default for saved workflows. "
                    "Choose Volcengine TOS to keep local-video publication inside "
                    "the Volcengine account."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=list(LOCAL_VIDEO_UPLOAD_SERVICES))},
                ui_options={"display_name": "Local Video Upload"},
            )
            ParameterString(
                name="tos_region",
                default_value=DEFAULT_TOS_REGION,
                tooltip="Region of the private TOS bucket.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "TOS Region"},
            )
            ParameterString(
                name="tos_endpoint",
                default_value=DEFAULT_TOS_ENDPOINT,
                tooltip="Public HTTPS endpoint for the TOS bucket region.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "TOS Endpoint"},
            )
            ParameterInt(
                name="tos_url_validity_seconds",
                default_value=DEFAULT_TOS_URL_VALIDITY_SECONDS,
                tooltip=(
                    "Validity of the temporary signed HTTPS URL. 86400 seconds "
                    "is recommended so queued tasks have time to fetch the video."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "TOS URL Validity (seconds)"},
            )
        advanced_settings.ui_options = {"collapsed": True}
        self.add_node_element(advanced_settings)

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                default_value=None,
                tooltip="Safe FN AI Broker task metadata without credential fields.",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
                hide_property=True,
                hide=True,
            )
        )
        self.add_parameter(
            ParameterVideo(
                name="video_url",
                default_value=None,
                tooltip="Downloaded MP4 preview; use VIDEO OUT for connections.",
                allowed_modes={ParameterMode.PROPERTY},
                settable=False,
                pulse_on_run=True,
                clickable_file_browser=False,
                ui_options={"display_name": "Video"},
            )
        )
        self.add_parameter(
            Parameter(
                name="VIDEO_OUT",
                type="VideoUrlArtifact",
                output_type="VideoUrlArtifact",
                default_value=None,
                tooltip="HMB alias of the downloaded local MP4 output.",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
                hide_property=True,
                ui_options={"display_name": "VIDEO OUT", "pulse_on_run": True},
            )
        )
        self.add_parameter(
            ParameterString(
                name="last_frame_url",
                default_value="",
                tooltip="Optional provider URL for the generated last frame.",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
                hide_property=True,
                hide=True,
            )
        )
        self._output_file = ProjectFileParameter(
            node=self,
            name="output_file",
            default_filename="volcengine_seedance_video.mp4",
        )
        self._output_file.add_parameter()
        self._create_status_parameters(
            result_details_tooltip=(
                "FN AI Broker task result, local output path, or a safe error message."
            ),
            result_details_placeholder="Generation status will appear here.",
            parameter_group_initially_collapsed=True,
        )
        status_group = self.status_component.get_parameter_group()
        status_group.add_child(
            ParameterString(
                name="generation_id",
                default_value="",
                tooltip=(
                    "FN AI Broker task ID. Preserved so an accepted task can be "
                    "retrieved without another create request."
                ),
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
                hide=True,
                hide_property=True,
            )
        )
        status_group.add_child(
            ParameterString(
                name="generation_status",
                default_value="",
                tooltip="Latest known FN AI Broker task status.",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )
        )
        status_group.add_child(
            ParameterButton(
                name="generation_refresh",
                label="Refresh / Retrieve Result",
                icon="refresh-cw",
                variant="secondary",
                full_width=True,
                tooltip=(
                    "Re-check this exact Broker task. Refresh never submits a "
                    "replacement render or creates a second charge."
                ),
                on_click=self._on_refresh_clicked,
            )
        )
        with ParameterGroup(name="AI Broker", collapsed=True) as broker_group:
            ParameterString(
                name="broker_connection_status",
                default_value="Not checked",
                tooltip="Current FN AI Broker authentication state.",
                allowed_modes={ParameterMode.PROPERTY},
                settable=False,
                serializable=False,
                ui_options={"display_name": "connection_status"},
            )
            ParameterString(
                name="broker_account",
                default_value="—",
                tooltip="Connected Broker account display name.",
                allowed_modes={ParameterMode.PROPERTY},
                settable=False,
                serializable=False,
                ui_options={"display_name": "account"},
            )
            self._broker_connect_button = ParameterButton(
                name="broker_connect_refresh",
                label="Connect / Refresh",
                icon="refresh-cw",
                variant="secondary",
                full_width=True,
                tooltip=(
                    "Use the saved permanent token, or open the one-time Broker "
                    "authorization page when this Windows account is not connected."
                ),
                on_click=self._on_broker_connect_clicked,
            )
            ParameterString(
                name="broker_notice",
                default_value=(
                    "Sign up once in the Browser. This Windows account stores only "
                    "a protected permanent access token; provider credentials and "
                    "usage controls remain on the Broker server."
                ),
                tooltip="FN AI Broker credential boundary.",
                allowed_modes={ParameterMode.PROPERTY},
                settable=False,
                serializable=False,
                multiline=True,
                ui_options={"display_name": ""},
            )
        self.add_node_element(broker_group)
        self._update_parameter_visibility()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Mirror Standard Seedance media visibility for the selected mode."""
        if parameter.name in {
            "model_id",
            "input_mode",
            "local_video_upload_service",
        }:
            self._update_parameter_visibility()
        return super().after_value_set(parameter, value)

    def _create_broker_bridge(self) -> _HMBAIBrokerBridge:
        return _HMBAIBrokerBridge()

    def _get_broker_bridge(self) -> _HMBAIBrokerBridge:
        if self._broker_bridge_instance is None:
            self._broker_bridge_instance = self._create_broker_bridge()
        return self._broker_bridge_instance

    @staticmethod
    def _broker_connection_label(state: str) -> str:
        return {
            "connected": "Connected",
            "login_required": "Login required",
            "approval_pending": "Approval pending",
            "approval_rejected": "Approval rejected",
            "approval_blocked": "Approval blocked",
            "unavailable": "Unavailable",
            "error": "Connection error",
        }.get(str(state or "").strip().lower(), "Not checked")

    @staticmethod
    def _broker_error_snapshot(exc: Exception) -> _BrokerAccountSnapshot:
        if isinstance(exc, _BrokerAuthenticationError):
            state = "login_required"
        elif isinstance(exc, _BrokerUnavailableError):
            state = "unavailable"
        else:
            state = "error"
        return _BrokerAccountSnapshot(
            state=state,
            connected=False,
            account="",
        )

    def _apply_broker_snapshot(self, snapshot: _BrokerAccountSnapshot) -> None:
        values = {
            "broker_connection_status": self._broker_connection_label(snapshot.state),
            "broker_account": snapshot.account if snapshot.connected and snapshot.account else "—",
        }
        try:
            for name, value in values.items():
                self.set_parameter_value(name, value, emit_change=False)
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    publisher(name, value)
        finally:
            with self._broker_action_lock:
                self._broker_action_running = False
            try:
                self._broker_connect_button.state = "normal"
            except Exception:
                pass
            emitter = getattr(self, "emit_parameter_changes", None)
            if callable(emitter):
                try:
                    emitter()
                except Exception:
                    pass

    def _schedule_broker_snapshot(self, snapshot: _BrokerAccountSnapshot) -> None:
        try:
            event_loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if event_loop is not None and event_loop.is_running():
                event_loop.call_soon_threadsafe(self._apply_broker_snapshot, snapshot)
                return
        except Exception:
            pass
        self._apply_broker_snapshot(snapshot)

    def _on_broker_connect_clicked(self, _button: Any, _details: Any) -> None:
        with self._broker_action_lock:
            if self._broker_action_running:
                return
            self._broker_action_running = True
        try:
            self._broker_connect_button.state = "loading"
        except Exception:
            pass

        def _worker() -> None:
            try:
                snapshot = self._get_broker_bridge().account_snapshot(connect=True)
            except Exception as exc:
                logger.warning(
                    "%s FN AI Broker connection check failed safely: %s",
                    self.name,
                    type(exc).__name__,
                )
                snapshot = self._broker_error_snapshot(exc)
            self._schedule_broker_snapshot(snapshot)

        try:
            threading.Thread(
                target=_worker,
                name=f"{self.name}-broker-connect",
                daemon=True,
            ).start()
        except Exception:
            self._apply_broker_snapshot(
                self._broker_error_snapshot(_BrokerUnavailableError("unavailable"))
            )

    async def _ensure_broker_connected(self) -> _HMBAIBrokerBridge:
        bridge = self._get_broker_bridge()
        try:
            snapshot = await asyncio.to_thread(
                bridge.account_snapshot,
                connect=True,
            )
        except Exception as exc:
            snapshot = self._broker_error_snapshot(exc)
            self._apply_broker_snapshot(snapshot)
            if isinstance(exc, _BrokerError):
                raise
            raise _BrokerUnavailableError(
                "FN AI Broker connection could not be established."
            ) from exc
        self._apply_broker_snapshot(snapshot)
        if not snapshot.connected:
            raise _BrokerAuthenticationError(
                "FN AI Broker connection or approval is required."
            )
        return bridge

    def _update_parameter_visibility(self) -> None:
        self._synchronize_model_resolution()
        input_mode = self.get_parameter_value("input_mode") or INPUT_MODE_MULTIMODAL_REFERENCES
        if input_mode == INPUT_MODE_MULTIMODAL_REFERENCES:
            self.hide_parameter_by_name("first_frame")
            self.hide_parameter_by_name("last_frame")
            self.show_parameter_by_name("reference_images")
            self.show_parameter_by_name(VIDEO_REFERENCES_PARAMETER)
            self.show_parameter_by_name("reference_audio")
            self.hide_parameter_by_name(
                ["reference_video_1", "reference_video_2", "reference_video_3"]
            )
        elif input_mode == INPUT_MODE_FIRST_LAST_FRAME:
            self.show_parameter_by_name("first_frame")
            self.show_parameter_by_name("last_frame")
            self.hide_parameter_by_name("reference_images")
            self.hide_parameter_by_name(VIDEO_REFERENCES_PARAMETER)
            self.hide_parameter_by_name("reference_audio")
            self.hide_parameter_by_name(
                ["reference_video_1", "reference_video_2", "reference_video_3"]
            )
        else:
            self.hide_parameter_by_name("first_frame")
            self.hide_parameter_by_name("last_frame")
            self.hide_parameter_by_name("reference_images")
            self.hide_parameter_by_name(VIDEO_REFERENCES_PARAMETER)
            self.hide_parameter_by_name("reference_audio")
            self.hide_parameter_by_name(
                ["reference_video_1", "reference_video_2", "reference_video_3"]
            )
        if (
            self.get_parameter_value("local_video_upload_service")
            == LOCAL_VIDEO_UPLOAD_TOS
        ):
            for name in ("tos_region", "tos_endpoint", "tos_url_validity_seconds"):
                self.show_parameter_by_name(name)
        else:
            self.hide_parameter_by_name(
                ["tos_region", "tos_endpoint", "tos_url_validity_seconds"]
            )

    def _synchronize_model_resolution(self) -> str:
        """Apply the selected Volcengine model's exact resolution contract."""
        raw_model = self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
        model_id = MODEL_ID_ALIASES.get(str(raw_model), str(raw_model))
        supported = MODEL_RESOLUTIONS.get(model_id)
        if supported is None:
            return model_id

        parameter = self.get_parameter_by_name("resolution")
        if parameter is not None:
            choices = list(supported)
            if parameter.ui_options.get("simple_dropdown") != choices:
                parameter.ui_options = {
                    **parameter.ui_options,
                    "simple_dropdown": choices,
                }

        current = str(self.get_parameter_value("resolution") or "")
        if current not in supported:
            self.set_parameter_value(
                "resolution", MODEL_DEFAULT_RESOLUTIONS[model_id]
            )
        return model_id

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        return [value]

    @staticmethod
    def _has_reference_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, dict)):
            return bool(value)
        return True

    def _get_list_input(self, name: str) -> list[Any]:
        """Read the current list value, then an older serialized top-level value."""
        current = [
            value
            for value in self._as_list(self.get_parameter_value(name))
            if self._has_reference_value(value)
        ]
        if current:
            return current
        # Griptape's ParameterList getter (still used by reference_audio) reads
        # child elements and intentionally ignores a former top-level serialized
        # value. Retain that value as a migration fallback only when the current
        # input has no populated values.
        return [
            value
            for value in self._as_list(self.parameter_values.get(name))
            if self._has_reference_value(value)
        ]

    def _get_parameters(self) -> dict[str, Any]:
        model_id = self._synchronize_model_resolution()
        legacy_video_slots = [
            self.get_parameter_value(f"reference_video_{index}")
            for index in range(1, MAX_VIDEO_REFERENCES + 1)
        ]
        ordered_video_references = self._get_list_input(VIDEO_REFERENCES_PARAMETER)
        if ordered_video_references:
            # The public one-wire list is authoritative. Empty active slots also
            # prevent upload preparation and legacy gap checks from switching
            # back to stale scalar values.
            video_reference_slots: list[Any] = []
            video_references = ordered_video_references
        else:
            video_reference_slots = legacy_video_slots
            video_references = [
                value
                for value in legacy_video_slots
                if self._has_reference_value(value)
            ]
        return {
            "resume_generation_id": str(
                self.get_parameter_value("resume_generation_id") or ""
            ).strip(),
            "model_id": model_id,
            "input_mode": self.get_parameter_value("input_mode")
            or INPUT_MODE_MULTIMODAL_REFERENCES,
            "prompt": str(self.get_parameter_value("prompt") or ""),
            "first_frame": self.get_parameter_value("first_frame"),
            "last_frame": self.get_parameter_value("last_frame"),
            "reference_images": self._get_list_input("reference_images"),
            "video_reference_slots": video_reference_slots,
            "video_references": video_references,
            "reference_audio": self._get_list_input("reference_audio"),
            "resolution": str(
                self.get_parameter_value("resolution")
                or MODEL_DEFAULT_RESOLUTIONS.get(
                    model_id, MODEL_DEFAULT_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID]
                )
            ),
            "ratio": str(self.get_parameter_value("ratio") or "adaptive"),
            "duration": self.get_parameter_value("duration"),
            "generate_audio": bool(self.get_parameter_value("generate_audio")),
            "watermark": bool(self.get_parameter_value("watermark")),
            "return_last_frame": bool(
                self.get_parameter_value("return_last_frame")
            ),
            "execution_expires_after": self.get_parameter_value(
                "execution_expires_after"
            ),
            "priority": self.get_parameter_value("priority"),
            "poll_interval_seconds": self.get_parameter_value(
                "poll_interval_seconds"
            ),
            "generation_timeout_seconds": self.get_parameter_value(
                "generation_timeout_seconds"
            ),
            "auto_publish_local_videos": bool(
                self.get_parameter_value("auto_publish_local_videos")
            ),
            "local_video_upload_service": str(
                self.get_parameter_value("local_video_upload_service")
                or LOCAL_VIDEO_UPLOAD_GRIPTAPE
            ),
            "tos_region": str(
                self.get_parameter_value("tos_region") or DEFAULT_TOS_REGION
            ).strip(),
            "tos_endpoint": str(
                self.get_parameter_value("tos_endpoint") or DEFAULT_TOS_ENDPOINT
            ).strip(),
            "tos_url_validity_seconds": self.get_parameter_value(
                "tos_url_validity_seconds"
            ),
        }

    def _validate_parameters(self, params: dict[str, Any]) -> None:
        poll_interval = params["poll_interval_seconds"]
        timeout = params["generation_timeout_seconds"]
        if not isinstance(poll_interval, int) or isinstance(poll_interval, bool):
            raise ValueError("poll_interval_seconds must be a positive integer.")
        if not isinstance(timeout, int) or isinstance(timeout, bool):
            raise ValueError("generation_timeout_seconds must be a positive integer.")
        if poll_interval <= 0 or timeout <= 0:
            raise ValueError("Polling interval and generation timeout must be positive.")
        if poll_interval > timeout:
            raise ValueError(
                "poll_interval_seconds cannot exceed generation_timeout_seconds."
            )

        upload_service = params.get(
            "local_video_upload_service", LOCAL_VIDEO_UPLOAD_GRIPTAPE
        )
        if upload_service not in LOCAL_VIDEO_UPLOAD_SERVICES:
            raise ValueError(f"Unsupported local video upload service: {upload_service!r}.")
        if upload_service == LOCAL_VIDEO_UPLOAD_TOS:
            validity = params.get("tos_url_validity_seconds")
            if not isinstance(validity, int) or isinstance(validity, bool):
                raise ValueError("tos_url_validity_seconds must be an integer.")
            if not MIN_TOS_URL_VALIDITY_SECONDS <= validity <= MAX_TOS_URL_VALIDITY_SECONDS:
                raise ValueError(
                    "tos_url_validity_seconds must be between 3600 and 2592000."
                )
            if not params.get("tos_region"):
                raise ValueError("TOS Region cannot be blank.")
            self._normalize_tos_endpoint(params.get("tos_endpoint", ""))

        resume_generation_id = params.get("resume_generation_id", "")
        if resume_generation_id:
            self._validate_task_id(resume_generation_id)
            return

        model_id = params["model_id"]
        if model_id not in MODEL_RESOLUTIONS:
            raise ValueError(f"Unsupported Volcengine Seedance model: {model_id!r}.")

        resolution = params["resolution"]
        supported_resolutions = MODEL_RESOLUTIONS[model_id]
        if resolution not in supported_resolutions:
            supported = ", ".join(supported_resolutions)
            raise ValueError(
                f"{model_id} does not support {resolution}; choose one of: {supported}."
            )
        if params["ratio"] not in RATIOS:
            raise ValueError(
                f"Unsupported ratio {params['ratio']!r}; choose one of: {', '.join(RATIOS)}."
            )

        duration = params["duration"]
        if not isinstance(duration, int) or isinstance(duration, bool):
            raise ValueError("Duration must be an integer.")
        if duration != -1 and not 4 <= duration <= 15:
            raise ValueError("Duration must be -1 or an integer from 4 through 15.")

        images = params["reference_images"]
        videos = params["video_references"]
        audio = params["reference_audio"]
        if len(images) > MAX_REFERENCE_IMAGES:
            raise ValueError(
                f"Seedance 2.0 accepts at most {MAX_REFERENCE_IMAGES} reference images; "
                f"received {len(images)}."
            )
        if len(videos) > MAX_VIDEO_REFERENCES:
            raise ValueError(
                f"Seedance 2.0 accepts at most {MAX_VIDEO_REFERENCES} reference videos; "
                f"received {len(videos)}. No references were discarded."
            )
        video_slots = params.get("video_reference_slots") or []
        if len(video_slots) >= 2:
            if self._has_reference_value(video_slots[1]) and not self._has_reference_value(
                video_slots[0]
            ):
                raise ValueError(
                    "reference_video_2 requires reference_video_1 to be connected first."
                )
        if len(video_slots) >= 3:
            if self._has_reference_value(video_slots[2]) and not self._has_reference_value(
                video_slots[1]
            ):
                raise ValueError(
                    "reference_video_3 requires reference_video_2 to be connected first."
                )
        if len(audio) > MAX_REFERENCE_AUDIO:
            raise ValueError(
                f"Seedance 2.0 accepts at most {MAX_REFERENCE_AUDIO} reference audio files; "
                f"received {len(audio)}."
            )

        input_mode = params["input_mode"]
        has_frames = bool(params["first_frame"] or params["last_frame"])
        has_references = bool(images or videos or audio)
        if input_mode == INPUT_MODE_TEXT_ONLY:
            if has_frames or has_references:
                raise ValueError(
                    "Text Only mode does not accept frame or reference media inputs."
                )
        elif input_mode == INPUT_MODE_FIRST_LAST_FRAME:
            if has_references:
                raise ValueError(
                    "First/Last Frame mode does not accept multimodal reference lists."
                )
            if params["last_frame"] and not params["first_frame"]:
                raise ValueError("Last Frame requires First Frame to be connected first.")
            if not has_frames and not params["prompt"].strip():
                raise ValueError(
                    "First/Last Frame mode requires a prompt or at least one frame."
                )
        elif input_mode == INPUT_MODE_MULTIMODAL_REFERENCES:
            if has_frames:
                raise ValueError(
                    "Multimodal References mode does not accept first_frame/last_frame."
                )
            if audio and not (images or videos):
                raise ValueError(
                    "Reference audio requires at least one reference image or video."
                )
        else:
            raise ValueError(f"Unsupported input mode: {input_mode!r}.")

        if not params["prompt"].strip() and not (has_frames or has_references):
            raise ValueError("Provide a prompt or supported media input before generation.")

        expires = params["execution_expires_after"]
        if not isinstance(expires, int) or isinstance(expires, bool):
            raise ValueError("execution_expires_after must be an integer.")
        if not 3600 <= expires <= 259200:
            raise ValueError("execution_expires_after must be between 3600 and 259200.")

        priority = params["priority"]
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an integer.")
        if not 0 <= priority <= 9:
            raise ValueError("priority must be between 0 and 9.")
        if model_id != SEEDANCE_2_0_MODEL_ID and priority != 0:
            raise ValueError(
                "priority is supported only by the full Seedance 2.0 model. "
                "Use priority 0 for Fast or Mini."
            )

    @staticmethod
    def _validate_broker_model(model_id: Any) -> None:
        if model_id not in BROKER_SUPPORTED_MODEL_IDS:
            raise ValueError(
                "FN AI Broker supports the Volcengine Seedance 2.0, Fast, and "
                "Mini model IDs only."
            )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        try:
            params = self._get_parameters()
            self._validate_parameters(params)
            if not params.get("resume_generation_id"):
                self._validate_broker_model(params.get("model_id"))
        except Exception as exc:
            exceptions.append(exc)
        return exceptions or None

    @staticmethod
    def _normalize_audio_mime(mime: str) -> str:
        lowered = mime.lower()
        return AUDIO_MIME_ALIASES.get(lowered, lowered)

    @staticmethod
    def _is_non_public_http_url(value: str) -> bool:
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname:
            return True
        if hostname == "localhost" or hostname.endswith(".localhost"):
            return True
        if hostname.endswith(".local"):
            return True
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return False
        return not address.is_global

    @staticmethod
    def _coerce_reference_value(value: Any, *, depth: int = 0) -> str | Path:
        if depth > 5:
            raise ValueError("Media reference nesting is too deep.")
        if isinstance(value, Path):
            return value
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("value", "url", "path", "location"):
                if key in value and value[key] is not None:
                    return HMBSeedanceGeneration._coerce_reference_value(
                        value[key], depth=depth + 1
                    )
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            serialized = to_dict()
            if serialized is not value:
                return HMBSeedanceGeneration._coerce_reference_value(
                    serialized, depth=depth + 1
                )
        for attribute in ("value", "location", "path"):
            candidate = getattr(value, attribute, None)
            if candidate is not None and candidate is not value:
                return HMBSeedanceGeneration._coerce_reference_value(
                    candidate, depth=depth + 1
                )
        raise ValueError(
            f"Unsupported media reference value of type {type(value).__name__}."
        )

    @classmethod
    def _validate_data_uri(cls, kind: str, value: str) -> str:
        match = _DATA_URI_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError(
                f"{kind} data URI must use a valid base64 encoding."
            )
        mime = match.group("mime").lower()
        if kind == "audio":
            mime = cls._normalize_audio_mime(mime)
            allowed_mimes = ALLOWED_AUDIO_MIMES
            maximum = MAX_AUDIO_BYTES
        elif kind == "image":
            allowed_mimes = ALLOWED_IMAGE_MIMES
            maximum = MAX_IMAGE_BYTES
        else:
            raise ValueError("Video references cannot be embedded as data URIs.")
        if mime not in allowed_mimes:
            raise ValueError(f"Unsupported {kind} data URI MIME type: {mime}.")
        try:
            decoded = base64.b64decode(match.group("data"), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"Invalid base64 data in {kind} reference.") from exc
        if not decoded:
            raise ValueError(f"{kind.capitalize()} reference is empty.")
        exceeds_limit = (
            len(decoded) >= maximum if kind == "image" else len(decoded) > maximum
        )
        if exceeds_limit:
            limit_mb = maximum // (1024 * 1024)
            raise ValueError(
                f"{kind.capitalize()} reference must be "
                f"{'smaller than' if kind == 'image' else 'no larger than'} {limit_mb} MB."
            )
        encoded = base64.b64encode(decoded).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @classmethod
    def _prepare_media_reference(cls, kind: str, value: Any) -> str:
        reference = cls._coerce_reference_value(value)
        text = str(reference).strip()
        if not text:
            raise ValueError(f"{kind.capitalize()} reference cannot be empty.")

        if text.startswith("data:"):
            return cls._validate_data_uri(kind, text)
        if text.startswith("asset://"):
            if not text.removeprefix("asset://").strip("/"):
                raise ValueError("asset:// reference is missing its asset ID.")
            return text
        if text.startswith(("http://", "https://")):
            if cls._is_non_public_http_url(text):
                raise ValueError(
                    f"{kind.capitalize()} URL must be publicly reachable by Volcengine; "
                    "localhost and private-network URLs are not supported."
                )
            return text

        try:
            # Griptape project artifacts intentionally use portable paths such as
            # ``inputs\\shot\\playblast.mp4``. File.resolve() anchors those paths
            # to the active project workspace instead of the engine process cwd.
            path = Path(File(text).resolve())
        except FileLoadError as exc:
            raise ValueError(
                f"Could not resolve {kind} reference in the active Griptape project: {text}"
            ) from exc
        if not path.exists():
            raise ValueError(
                f"{kind.capitalize()} reference file does not exist in the active "
                f"Griptape project: {text} (resolved to {path})"
            )
        if not path.is_file():
            raise ValueError(f"{kind.capitalize()} reference is not a file: {path}")
        if kind == "video":
            raise ValueError(
                "Volcengine Ark does not accept Base64/local video references. "
                "Upload the MP4 to a public http(s) URL or register a Volcengine "
                "asset:// reference before running this node."
            )

        suffix = path.suffix.lower()
        if kind == "image":
            mime = IMAGE_MIME_BY_SUFFIX.get(suffix)
            maximum = MAX_IMAGE_BYTES
        elif kind == "audio":
            mime = AUDIO_MIME_BY_SUFFIX.get(suffix)
            maximum = MAX_AUDIO_BYTES
        else:
            raise ValueError(f"Unsupported media kind: {kind!r}.")
        if mime is None:
            guessed, _ = mimetypes.guess_type(path.name)
            raise ValueError(
                f"Unsupported {kind} file type {suffix or guessed or '<none>'}: {path.name}"
            )
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"{kind.capitalize()} reference is empty: {path}")
        exceeds_limit = size >= maximum if kind == "image" else size > maximum
        if exceeds_limit:
            limit_mb = maximum // (1024 * 1024)
            raise ValueError(
                f"{kind.capitalize()} reference must be "
                f"{'smaller than' if kind == 'image' else 'no larger than'} "
                f"{limit_mb} MB: {path.name}"
            )
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _get_optional_secret(name: str) -> str:
        try:
            value = GriptapeNodes.SecretsManager().get_secret(
                name, should_error_on_not_found=False
            )
        except Exception:
            return ""
        return str(value or "").strip()

    def _create_gt_cloud_storage_driver(self) -> GriptapeCloudStorageDriver:
        api_key = self._get_optional_secret(GT_CLOUD_API_KEY_SECRET)
        if not api_key:
            raise RuntimeError(
                "GT_CLOUD_API_KEY is missing. Sign in to Griptape Cloud or add "
                "the key in Griptape Settings > Secrets."
            )
        base_url = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai").strip()
        bucket_id = self._get_optional_secret(GT_CLOUD_BUCKET_ID_SECRET)
        if bucket_id:
            if not GriptapeCloudStorageDriver.bucket_exists(
                bucket_id,
                base_url=base_url,
                api_key=api_key,
                timeout=30.0,
            ):
                raise RuntimeError(
                    "GT_CLOUD_BUCKET_ID does not identify an accessible Griptape "
                    "Cloud bucket. Correct it or clear it to use the default bucket."
                )
        else:
            bucket_id = str(
                GriptapeCloudStorageDriver.get_default_bucket_id(
                    base_url=base_url,
                    api_key=api_key,
                    timeout=30.0,
                )
                or ""
            ).strip()
            if not bucket_id:
                raise RuntimeError(
                    "No default Griptape Cloud storage bucket is available."
                )
        return GriptapeCloudStorageDriver(
            workspace_directory=GriptapeNodes.ConfigManager().workspace_path,
            bucket_id=bucket_id,
            api_key=api_key,
            base_url=base_url,
            request_timeout=30.0,
        )

    @staticmethod
    def _normalize_tos_endpoint(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("TOS Endpoint cannot be blank.")
        parsed = urlparse(text if "://" in text else f"https://{text}")
        if parsed.scheme.lower() != "https":
            raise ValueError("TOS Endpoint must use HTTPS.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("TOS Endpoint must contain only the official HTTPS host.")
        if parsed.path not in ("", "/"):
            raise ValueError("TOS Endpoint must not contain a path.")
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not re.fullmatch(r"tos(?:-[a-z0-9]+)+\.volces\.com", hostname):
            raise ValueError(
                "TOS Endpoint must be an official public tos-*.volces.com host."
            )
        if parsed.port not in (None, 443):
            raise ValueError("TOS Endpoint must use the default HTTPS port 443.")
        return hostname

    def _create_tos_storage_context(
        self, params: dict[str, Any]
    ) -> tuple[Any, Any, str]:
        access_key = self._get_optional_secret(TOS_ACCESS_KEY_ID_SECRET)
        secret_key = self._get_optional_secret(TOS_SECRET_ACCESS_KEY_SECRET)
        bucket_name = self._get_optional_secret(TOS_BUCKET_NAME_SECRET)
        missing = [
            name
            for name, value in (
                (TOS_ACCESS_KEY_ID_SECRET, access_key),
                (TOS_SECRET_ACCESS_KEY_SECRET, secret_key),
                (TOS_BUCKET_NAME_SECRET, bucket_name),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Volcengine TOS setup is incomplete. Add these names in "
                "Griptape Settings > Secrets: " + ", ".join(missing)
            )
        if not _TOS_BUCKET_PATTERN.fullmatch(bucket_name):
            raise ValueError(
                "TOS_BUCKET_NAME must be 3-63 lowercase letters, digits, or hyphens."
            )
        endpoint = self._normalize_tos_endpoint(params["tos_endpoint"])
        region = str(params["tos_region"] or "").strip()
        try:
            tos_module = importlib.import_module("tos")
        except ImportError as exc:
            raise RuntimeError(
                "The Volcengine TOS Python SDK is not installed. Reinstall or "
                "upgrade the HMB library so its pinned tos dependency is installed."
            ) from exc
        try:
            client = tos_module.TosClientV2(
                access_key,
                secret_key,
                endpoint,
                region,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not initialize the Volcengine TOS client. Check TOS Region, "
                "Endpoint, and the separately scoped TOS credentials."
            ) from exc
        return tos_module, client, bucket_name

    @staticmethod
    def _resolve_local_video_path(value: str) -> Path:
        try:
            path = Path(File(value).resolve())
        except FileLoadError as exc:
            raise LocalReferenceVideoError(
                f"Could not resolve local reference video in the active project: {value}"
            ) from exc
        if not path.is_file():
            raise LocalReferenceVideoError(
                f"Local reference video does not exist in the active project: {value}"
            )
        size = path.stat().st_size
        if size <= 0:
            raise LocalReferenceVideoError(
                f"Local reference video is empty: {value}"
            )
        if size > MAX_DOWNLOAD_BYTES:
            raise LocalReferenceVideoError(
                "Local reference video exceeds the 1 GB safety limit."
            )
        return path

    @classmethod
    def _read_local_video_for_upload(cls, value: str) -> tuple[Path, bytes]:
        path = cls._resolve_local_video_path(value)
        try:
            return path, path.read_bytes()
        except OSError as exc:
            raise LocalReferenceVideoError(
                f"Local reference video cannot be read: {value}"
            ) from exc

    def _upload_local_video_to_tos(
        self,
        local_path: Path,
        params: dict[str, Any],
        context: tuple[Any, Any, str],
    ) -> str:
        tos_module, client, bucket_name = context
        suffix = local_path.suffix.lower() or ".mp4"
        object_key = f"{TOS_TEMP_OBJECT_PREFIX}/{uuid4().hex}{suffix}"
        content_type = mimetypes.guess_type(local_path.name)[0] or "video/mp4"
        uploaded = False
        try:
            response = client.put_object_from_file(
                bucket_name,
                object_key,
                str(local_path),
                content_type=content_type,
            )
            status_code = int(getattr(response, "status_code", 200) or 200)
            if not 200 <= status_code < 300:
                raise RuntimeError(f"TOS upload returned HTTP {status_code}.")
            uploaded = True
            signed = client.pre_signed_url(
                tos_module.HttpMethodType.Http_Method_Get,
                bucket_name,
                object_key,
                expires=int(params["tos_url_validity_seconds"]),
            )
            signed_url = str(getattr(signed, "signed_url", "") or "").strip()
            if not signed_url.startswith("https://"):
                raise RuntimeError("TOS did not return a signed HTTPS URL.")
        except Exception:
            if uploaded:
                with suppress(Exception):
                    client.delete_object(bucket_name, object_key)
            if not any(item[0] is client for item in self._temporary_tos_video_uploads):
                close = getattr(client, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()
            raise
        self._temporary_tos_video_uploads.append(
            (client, bucket_name, object_key)
        )
        return signed_url

    def _prepare_video_references_for_run(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Publish only local video inputs without changing their selected order."""
        video_slots = params.get("video_reference_slots") or []
        if any(self._has_reference_value(value) for value in video_slots):
            references = [
                (f"reference_video_{index}", value, False)
                for index, value in enumerate(video_slots, start=1)
                if self._has_reference_value(value)
            ]
        else:
            references = [
                (VIDEO_REFERENCES_PARAMETER, value, True)
                for value in params.get("video_references") or []
                if self._has_reference_value(value)
            ]

        prepared: list[str] = []
        driver: GriptapeCloudStorageDriver | None = None
        tos_context: tuple[Any, Any, str] | None = None
        for _parameter_name, value, _scratch_parameter in references:
            reference = self._coerce_reference_value(value)
            text = str(reference).strip()
            if text.startswith(("http://", "https://", "asset://", "data:")):
                prepared.append(self._prepare_media_reference("video", text))
                continue
            if not params.get("auto_publish_local_videos", True):
                prepared.append(self._prepare_media_reference("video", value))
                continue

            try:
                upload_service = params.get(
                    "local_video_upload_service", LOCAL_VIDEO_UPLOAD_GRIPTAPE
                )
                if upload_service == LOCAL_VIDEO_UPLOAD_TOS:
                    local_path = self._resolve_local_video_path(text)
                    if tos_context is None:
                        tos_context = self._create_tos_storage_context(params)
                    public_url = self._upload_local_video_to_tos(
                        local_path, params, tos_context
                    )
                else:
                    local_path, content = self._read_local_video_for_upload(text)
                    if driver is None:
                        driver = self._create_gt_cloud_storage_driver()
                    remote_path = (
                        Path("artifact_url_storage")
                        / uuid4().hex
                        / local_path.name
                    )
                    self._temporary_video_uploads.append((driver, remote_path))
                    public_url = driver.upload_file(
                        path=remote_path,
                        file_content=content,
                        timeout=120.0,
                    )
            except LocalReferenceVideoError:
                # Preserve the actionable local/project-path diagnosis. The
                # generic upload-service hint is only appropriate after a
                # readable local file reached the selected storage service.
                raise
            except Exception as exc:
                raise RuntimeError(
                    "Local reference-video publishing failed through the selected "
                    "upload service. Check its credentials, bucket, region, and "
                    "endpoint, then retry. Alternatively provide a public https:// "
                    "URL or Volcengine asset:// reference."
                ) from exc
            prepared.append(self._prepare_media_reference("video", public_url))

        updated = dict(params)
        updated["video_references"] = prepared
        return updated

    @staticmethod
    def _delete_temporary_video_uploads(
        uploads: list[tuple[GriptapeCloudStorageDriver, Path]],
    ) -> None:
        for driver, remote_path in uploads:
            with suppress(Exception):
                driver.delete_file(remote_path)

    @staticmethod
    def _delete_temporary_tos_video_uploads(
        uploads: list[tuple[Any, str, str]],
    ) -> None:
        clients: dict[int, Any] = {}
        for client, bucket_name, object_key in uploads:
            clients[id(client)] = client
            with suppress(Exception):
                client.delete_object(bucket_name, object_key)
        for client in clients.values():
            close = getattr(client, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()

    def _cleanup_temporary_video_uploads(self) -> None:
        uploads = list(reversed(self._temporary_video_uploads))
        self._temporary_video_uploads = []
        self._delete_temporary_video_uploads(uploads)
        tos_uploads = list(reversed(self._temporary_tos_video_uploads))
        self._temporary_tos_video_uploads = []
        self._delete_temporary_tos_video_uploads(tos_uploads)

    def _defer_temporary_video_upload_cleanup(self) -> None:
        uploads = list(reversed(self._temporary_video_uploads))
        self._temporary_video_uploads = []
        tos_uploads = list(reversed(self._temporary_tos_video_uploads))
        self._temporary_tos_video_uploads = []
        cleanup_targets = (
            (self._delete_temporary_video_uploads, uploads, "cloud"),
            (self._delete_temporary_tos_video_uploads, tos_uploads, "tos"),
        )
        for cleanup, pending, label in cleanup_targets:
            if not pending:
                continue
            timer = threading.Timer(
                AMBIGUOUS_UPLOAD_CLEANUP_DELAY_SECONDS,
                cleanup,
                args=(pending,),
            )
            timer.name = f"{self.name}-ambiguous-{label}-upload-cleanup"
            timer.daemon = True
            timer.start()

    def _build_broker_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Map the HMB media contract to the FN AI Broker Seedance schema."""
        self._validate_parameters(params)
        self._validate_broker_model(params.get("model_id"))
        broker_resolution = (
            "720x1280"
            if params["ratio"] in {"9:16", "3:4"}
            else "1280x720"
        )
        payload: dict[str, Any] = {
            "provider": "volcengine_ark",
            "model": params["model_id"],
            "prompt": params["prompt"].strip(),
            "input_mode": params["input_mode"],
            "duration_seconds": params["duration"],
            "quality": params["resolution"],
            "resolution": broker_resolution,
            "aspect_ratio": params["ratio"],
            "generate_audio": params["generate_audio"],
            "watermark": params["watermark"],
            "web_search": False,
            "content_filter": True,
            "return_last_frame": params["return_last_frame"],
            "execution_expires_after": params["execution_expires_after"],
        }
        if params["model_id"] == SEEDANCE_2_0_MODEL_ID:
            payload["priority"] = params["priority"]
        if params["input_mode"] == INPUT_MODE_FIRST_LAST_FRAME:
            if params["first_frame"]:
                payload["first_frame"] = [
                    self._prepare_media_reference("image", params["first_frame"])
                ]
            if params["last_frame"]:
                payload["last_frame"] = [
                    self._prepare_media_reference("image", params["last_frame"])
                ]
        elif params["input_mode"] == INPUT_MODE_MULTIMODAL_REFERENCES:
            payload["image_urls"] = [
                self._prepare_media_reference("image", value)
                for value in params["reference_images"]
            ]
            payload["video_urls"] = [
                self._prepare_media_reference("video", value)
                for value in params["video_references"]
            ]
            payload["audio_urls"] = [
                self._prepare_media_reference("audio", value)
                for value in params["reference_audio"]
            ]
        payload = {
            key: value
            for key, value in payload.items()
            if value is not None and value != []
        }
        encoded_payload = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded_payload) > MAX_REQUEST_BYTES:
            raise ValueError(
                "FN AI Broker request body exceeds the 64 MB limit. "
                "Reduce or externally host reference media."
            )
        return payload

    @staticmethod
    def _normalize_broker_status(value: Any) -> str:
        status = str(value or "").strip().lower().replace("-", "_")
        if status in BROKER_ACTIVE_STATUSES:
            return "running" if status in {"running", "processing", "in_progress"} else "queued"
        if status in BROKER_SUCCESS_STATUSES:
            return "succeeded"
        if status in BROKER_FAILURE_STATUSES:
            return "failed"
        if status in BROKER_CANCELLED_STATUSES:
            return "cancelled"
        if status in BROKER_EXPIRED_STATUSES:
            return "expired"
        return ""

    @classmethod
    def _broker_result_url(cls, value: Any, *, depth: int = 0) -> str:
        if depth > 5:
            return ""
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith(("http://", "https://")):
                return candidate
            if candidate.startswith("/") and not candidate.startswith("//"):
                return urljoin(AI_BROKER_SERVER_URL + "/", candidate)
            return ""
        if isinstance(value, dict):
            for key in (
                "video_url",
                "output",
                "url",
                "content",
                "response",
                "result",
                "data",
            ):
                if key in value:
                    candidate = cls._broker_result_url(
                        value.get(key), depth=depth + 1
                    )
                    if candidate:
                        return candidate
        if isinstance(value, list):
            for item in value:
                candidate = cls._broker_result_url(item, depth=depth + 1)
                if candidate:
                    return candidate
        return ""

    @classmethod
    def _normalize_broker_task(
        cls,
        response: dict[str, Any],
        *,
        fallback_job_id: str = "",
    ) -> dict[str, Any]:
        raw_status = response.get("status")
        status = cls._normalize_broker_status(raw_status)
        video_url = cls._broker_result_url(response)
        if not status and video_url:
            status = "succeeded"
        if not status:
            raise _BrokerError("FN AI Broker response did not include a known status.")
        generation_id = str(
            response.get("job_id")
            or response.get("id")
            or response.get("task_id")
            or fallback_job_id
            or ""
        ).strip()
        if not generation_id and status == "succeeded":
            generation_id = "broker-completed-" + uuid4().hex
        generation_id = cls._validate_task_id(generation_id)
        task: dict[str, Any] = {
            "id": generation_id,
            "status": status,
            "broker_status": str(raw_status or status).strip().lower(),
        }
        error_code = str(response.get("error_code") or "").strip().lower()
        if _BROKER_PUBLIC_CODE_PATTERN.fullmatch(error_code):
            task["error_code"] = error_code
        if status in TERMINAL_FAILURE_STATUSES or response.get("terminal") is True:
            task["terminal"] = True
        if isinstance(response.get("resubmit_allowed"), bool):
            task["resubmit_allowed"] = response["resubmit_allowed"]
        recovery_action = str(response.get("recovery_action") or "").strip().lower()
        if _BROKER_PUBLIC_CODE_PATTERN.fullmatch(recovery_action):
            task["recovery_action"] = recovery_action
        if "provider_job_id" in response:
            task["provider_task_registered"] = bool(
                str(response.get("provider_job_id") or "").strip()
            )
        if video_url:
            task["content"] = {"video_url": video_url}
        return task

    @staticmethod
    def _broker_terminal_failure_message(
        task: dict[str, Any], generation_id: str
    ) -> str:
        status = str(task.get("status") or "failed")
        error_code = str(task.get("error_code") or "")
        parts = [
            f"FN AI Broker task {generation_id} ended with status {status}."
        ]
        if error_code:
            parts.append(f"Broker error code: {error_code}.")
        if error_code == "submission_unknown":
            parts.append(
                "Provider acceptance could not be confirmed because no provider "
                "task ID was returned. This Broker job is terminal and automatic "
                "resubmission is disabled. Contact an administrator to verify "
                "provider-side activity before starting another render."
            )
        elif task.get("resubmit_allowed") is False:
            parts.append("Automatic resubmission is disabled for this terminal job.")
        if (
            task.get("recovery_action") == "contact_admin"
            and error_code != "submission_unknown"
        ):
            parts.append("Contact an administrator before starting another render.")
        return " ".join(parts)

    def _set_broker_task_outputs(
        self,
        task: dict[str, Any],
        *,
        generation_id: str,
        status: str,
    ) -> None:
        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["generation_status"] = status
        provider_response = {
            "transport": "fn_ai_broker",
            "id": generation_id,
            "status": status,
        }
        for name in (
            "error_code",
            "terminal",
            "resubmit_allowed",
            "recovery_action",
            "provider_task_registered",
        ):
            if name in task:
                provider_response[name] = task[name]
        self.parameter_output_values["provider_response"] = provider_response

    async def _download_broker_video(self, url: str) -> bytes:
        bridge = self._get_broker_bridge()
        if bridge.is_trusted_broker_url(url):
            return await asyncio.to_thread(
                bridge.download_trusted_result,
                url,
                max_bytes=MAX_DOWNLOAD_BYTES,
            )
        return await self._download_video(url)

    @staticmethod
    def _redact_sensitive(value: Any, secret: str = "") -> Any:
        if isinstance(value, dict):
            return {
                str(key): (
                    "[SIGNED_URL_REDACTED]"
                    if str(key).lower() in {"video_url", "last_frame_url"}
                    else "[REDACTED]"
                    if _SENSITIVE_FIELD_PATTERN.search(str(key))
                    else HMBSeedanceGeneration._redact_sensitive(item, secret)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                HMBSeedanceGeneration._redact_sensitive(item, secret)
                for item in value
            ]
        if isinstance(value, tuple):
            return tuple(
                HMBSeedanceGeneration._redact_sensitive(item, secret)
                for item in value
            )
        if isinstance(value, str):
            redacted = value.replace(secret, "[REDACTED]") if secret else value
            return _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
        return value

    @classmethod
    def _safe_exception_message(cls, exc: BaseException, secret: str = "") -> str:
        message = str(exc) or type(exc).__name__
        return str(cls._redact_sensitive(message, secret))


    @staticmethod
    def _resolve_host_addresses(hostname: str, port: int) -> set[str]:
        try:
            return {str(ipaddress.ip_address(hostname))}
        except ValueError:
            pass
        try:
            records = socket.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise RuntimeError(
                "Could not resolve the Volcengine video download host."
            ) from exc
        return {
            str(record[4][0]).split("%", 1)[0]
            for record in records
            if record and record[4]
        }

    async def _validate_download_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Volcengine returned an invalid video download URL.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Video download URL must not contain user credentials.")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("Video download URL contains an invalid port.") from exc
        addresses = await asyncio.to_thread(
            self._resolve_host_addresses, parsed.hostname, port
        )
        if not addresses:
            raise RuntimeError("Video download host resolved to no addresses.")
        for address in addresses:
            try:
                resolved = ipaddress.ip_address(address)
            except ValueError as exc:
                raise RuntimeError(
                    "Video download host returned an invalid address."
                ) from exc
            if not resolved.is_global:
                raise ValueError(
                    "Video download URL resolved to a private, loopback, link-local, "
                    "or otherwise non-public address."
                )

    async def _download_video(self, url: str) -> bytes:
        timeout = httpx.Timeout(connect=20.0, read=300.0, write=60.0, pool=20.0)
        current_url = url
        attempts = 0
        redirects = 0
        while attempts < 3:
            await self._validate_download_url(current_url)
            try:
                # External signed result URLs are downloaded without Broker
                # authorization; its access token must never leave Broker origin.
                async with httpx.AsyncClient(
                    timeout=timeout, follow_redirects=False
                ) as client:
                    async with client.stream(
                        "GET",
                        current_url,
                        headers={"Accept": "video/mp4,application/octet-stream"},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise RuntimeError(
                                    "Video download redirect did not include a destination."
                                )
                            redirects += 1
                            if redirects > 5:
                                raise RuntimeError(
                                    "Video download exceeded the five-redirect limit."
                                )
                            current_url = urljoin(current_url, location)
                            continue

                        if response.status_code in RETRYABLE_HTTP_STATUSES:
                            attempts += 1
                            if attempts < 3:
                                await self._sleep(min(2 ** (attempts - 1), 5))
                                continue
                        if not response.is_success:
                            raise RuntimeError(
                                f"Video download failed with HTTP {response.status_code}."
                            )

                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                declared_length = int(content_length)
                            except ValueError as exc:
                                raise RuntimeError(
                                    "Video download returned an invalid Content-Length."
                                ) from exc
                            if declared_length > MAX_DOWNLOAD_BYTES:
                                raise RuntimeError(
                                    "Downloaded video exceeds the 1 GB safety limit."
                                )

                        content_type = response.headers.get("content-type", "").lower()
                        if "json" in content_type or "text/html" in content_type:
                            raise RuntimeError(
                                "Volcengine video URL returned a non-video response."
                            )

                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(content) + len(chunk) > MAX_DOWNLOAD_BYTES:
                                raise RuntimeError(
                                    "Downloaded video exceeds the 1 GB safety limit."
                                )
                            content.extend(chunk)
            except httpx.TransportError as exc:
                attempts += 1
                if attempts < 3:
                    await self._sleep(min(2 ** (attempts - 1), 5))
                    continue
                raise RuntimeError(
                    f"Video download failed ({type(exc).__name__})."
                ) from exc

            if not content:
                raise RuntimeError("Volcengine returned an empty video file.")
            video_bytes = bytes(content)
            if not _is_structurally_valid_mp4(video_bytes):
                raise RuntimeError(
                    "Downloaded result is not a valid MP4 container."
                )
            return video_bytes
        raise RuntimeError("Video download exhausted its retry limit.")

    @staticmethod
    def _extract_video_url(task: dict[str, Any]) -> str | None:
        content = task.get("content")
        if isinstance(content, dict):
            value = content.get("video_url")
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                value = item.get("video_url") or item.get("url")
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value
        return None

    @staticmethod
    def _extract_last_frame_url(task: dict[str, Any]) -> str:
        content = task.get("content")
        if isinstance(content, dict):
            value = content.get("last_frame_url")
            if isinstance(value, str):
                return value
        return ""


    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["generation_status"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
        self.parameter_output_values["VIDEO_OUT"] = None
        self.parameter_output_values["last_frame_url"] = ""

    @staticmethod
    def _validate_task_id(value: Any) -> str:
        task_id = str(value or "").strip()
        if not task_id:
            raise _BrokerProtocolError("Generation task ID is missing.")
        if _TASK_ID_PATTERN.fullmatch(task_id) is None:
            raise _BrokerProtocolError(
                "Generation task ID is invalid; polling was not attempted."
            )
        return task_id

    def _monotonic(self) -> float:
        return time.monotonic()

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    @staticmethod
    def _output_destination_policy(destination: Any) -> ExistingFilePolicy:
        policy = getattr(
            destination,
            "_existing_file_policy",
            ExistingFilePolicy.OVERWRITE,
        )
        if isinstance(policy, ExistingFilePolicy):
            return policy
        try:
            return ExistingFilePolicy(str(policy).strip().lower())
        except ValueError as exc:
            raise RuntimeError(
                "Output destination has an unsupported collision policy."
            ) from exc

    @staticmethod
    def _normalized_mp4_output_path(value: str | Path) -> Path:
        path = Path(value)
        if path.suffix.lower() not in {".mp4", ".m4v"}:
            path = path.with_suffix(".mp4")
        return path

    @classmethod
    def _output_destination_candidate_records(
        cls,
        destination: Any,
    ) -> Iterator[tuple[Path, int | None]]:
        """Yield collision candidates and any project-macro index they bind."""

        destination_file = getattr(destination, "_file", None)
        file_path = getattr(destination_file, "_file_path", None)
        if isinstance(file_path, MacroPath):
            index_segment = next(
                (
                    segment
                    for segment in file_path.parsed_macro.segments
                    if getattr(getattr(segment, "info", None), "name", "")
                    == "_index"
                ),
                None,
            )
            if index_segment is not None:
                variables = dict(file_path.variables)
                bound_index = variables.get("_index")
                if isinstance(bound_index, int) and not isinstance(bound_index, bool):
                    start_index = bound_index
                elif bool(getattr(index_segment.info, "is_required", False)):
                    start_index = 1
                else:
                    yield cls._normalized_mp4_output_path(destination.resolve()), None
                    start_index = 1
                for index in range(
                    start_index,
                    start_index + MAX_ATOMIC_OUTPUT_CANDIDATES,
                ):
                    indexed_path = MacroPath(
                        parsed_macro=file_path.parsed_macro,
                        variables={**variables, "_index": index},
                    )
                    yield (
                        cls._normalized_mp4_output_path(File(indexed_path).resolve()),
                        index,
                    )
                return

        base_path = cls._normalized_mp4_output_path(destination.resolve())
        yield base_path, None
        for index in range(1, MAX_ATOMIC_OUTPUT_CANDIDATES + 1):
            yield (
                base_path.with_name(f"{base_path.stem}_{index}{base_path.suffix}"),
                None,
            )

    @classmethod
    def _output_destination_candidates(
        cls,
        destination: Any,
    ) -> Iterator[Path]:
        """Yield collision candidates without reserving or writing a file."""

        for candidate, _macro_index in cls._output_destination_candidate_records(
            destination
        ):
            yield candidate

    @classmethod
    def _preflight_output_destination(cls, destination: Any) -> Path:
        """Resolve and write-probe the local target before any billable POST."""

        if bool(getattr(destination, "_append", False)):
            raise ValueError("Generated MP4 output does not support append mode.")
        policy = cls._output_destination_policy(destination)
        candidates = cls._output_destination_candidate_records(destination)
        selected: Path | None = None
        for candidate, _macro_index in candidates:
            if policy is not ExistingFilePolicy.CREATE_NEW or not candidate.exists():
                selected = candidate
                break
        if selected is None:
            raise FileExistsError(
                "No unused generated-video output filename is available."
            )
        if policy is ExistingFilePolicy.FAIL and selected.exists():
            raise FileExistsError(f"Generated-video output already exists: {selected}")
        if selected.exists() and not selected.is_file():
            raise IsADirectoryError(f"Generated-video output is not a file: {selected}")
        create_parents = bool(getattr(destination, "_create_parents", True))
        if not selected.parent.exists():
            if not create_parents:
                raise FileNotFoundError(
                    "Generated-video output directory does not exist: "
                    f"{selected.parent}"
                )
            selected.parent.mkdir(parents=True, exist_ok=True)
        if not selected.parent.is_dir():
            raise NotADirectoryError(
                f"Generated-video output parent is not a directory: {selected.parent}"
            )
        cls._probe_output_parent_writable(selected.parent)
        return selected

    @staticmethod
    def _probe_output_parent_writable(parent: Path) -> None:
        """Verify sibling staging is writable before a billable submission."""

        probe = parent / f".hmb-seedance.{uuid4().hex}.output-probe"
        try:
            with probe.open("xb") as stream:
                if stream.write(b"\x00") != 1:
                    raise OSError(
                        "Generated-video output write probe was incomplete."
                    )
                stream.flush()
        finally:
            with suppress(FileNotFoundError):
                probe.unlink()

    @staticmethod
    def _publish_output_without_overwrite(stage: Path, destination: Path) -> bool:
        """Publish a complete sibling file while refusing an existing name."""

        try:
            os.link(stage, destination)
        except FileExistsError:
            return False
        except OSError:
            if os.name != "nt":
                raise
            try:
                os.rename(stage, destination)
            except FileExistsError:
                return False
        else:
            with suppress(OSError):
                stage.unlink()
        return True

    @staticmethod
    async def _await_filesystem_commit(function: Any, *args: Any) -> Any:
        """Finish a started atomic filesystem operation before cancellation."""

        operation = asyncio.create_task(asyncio.to_thread(function, *args))
        cancellation_requested = False
        while True:
            try:
                result = await asyncio.shield(operation)
                break
            except asyncio.CancelledError:
                cancellation_requested = True
                continue
        if cancellation_requested:
            logger.warning(
                "Cancellation arrived during generated-video publication; "
                "the atomic commit completed before success was returned."
            )
        return result

    async def _await_submission_result(
        self,
        function: Any,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, bool]:
        """Return promptly on cancellation while the started POST finishes off-task."""

        operation = asyncio.create_task(
            asyncio.to_thread(function, *args, **kwargs)
        )
        try:
            return await asyncio.shield(operation), False
        except asyncio.CancelledError:
            # A running Python worker thread cannot be reclaimed safely. Detach it,
            # retain a strong reference until completion, and expose the only safe
            # remote-state claim: this idempotent submission may have been accepted.
            self._submission_outcome_unknown = True
            generation_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            if generation_id:
                self._set_broker_task_outputs(
                    {"id": generation_id, "status": "submission_unknown"},
                    generation_id=generation_id,
                    status="submission_unknown",
                )
            self._detached_submission_tasks.add(operation)

            def consume_detached_result(completed: asyncio.Task[Any]) -> None:
                self._detached_submission_tasks.discard(completed)
                try:
                    completed.result()
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    logger.warning(
                        "%s detached Broker submission finished after local "
                        "cancellation with %s; remote state remains unknown.",
                        self.name,
                        type(exc).__name__,
                    )

            operation.add_done_callback(consume_detached_result)
            raise

    @classmethod
    async def _atomic_publish_completed_mp4(
        cls,
        destination: Any,
        content: bytes,
        verifier: _MP4DecodeVerifier | None = None,
    ) -> File:
        if not _is_structurally_valid_mp4(content):
            raise RuntimeError("Generated result is not a valid MP4 container.")
        cls._preflight_output_destination(destination)
        policy = cls._output_destination_policy(destination)
        candidates = cls._output_destination_candidate_records(destination)
        published: Path | None = None
        published_macro_index: int | None = None
        for candidate, macro_index in candidates:
            if policy is ExistingFilePolicy.CREATE_NEW and candidate.exists():
                continue
            create_parents = bool(getattr(destination, "_create_parents", True))
            if not candidate.parent.exists():
                if not create_parents:
                    raise FileNotFoundError(
                        "Generated-video output directory does not exist: "
                        f"{candidate.parent}"
                    )
                candidate.parent.mkdir(parents=True, exist_ok=True)
            stage = candidate.parent / (
                f".{candidate.stem}.{uuid4().hex}.partial{candidate.suffix}"
            )
            try:
                written_stage = await File(str(stage)).awrite_bytes(
                    content,
                    existing_file_policy=ExistingFilePolicy.FAIL,
                    append=False,
                    create_parents=False,
                    coerce_extension_to_match_bytes=False,
                )
                if Path(written_stage) != stage or stage.stat().st_size != len(content):
                    raise OSError(
                        "Generated-video staging file was not written completely."
                    )
                # Container structure alone cannot prove that the compressed
                # video stream is decodable. Probe the complete sibling stage
                # before either overwrite or create-new publication can expose
                # it at the final destination.
                await asyncio.to_thread(
                    _validate_decodable_mp4_file,
                    stage,
                    verifier,
                )
                if policy is ExistingFilePolicy.OVERWRITE:
                    await cls._await_filesystem_commit(os.replace, stage, candidate)
                    claimed = True
                else:
                    claimed = await cls._await_filesystem_commit(
                        cls._publish_output_without_overwrite,
                        stage,
                        candidate,
                    )
                if claimed:
                    published = candidate
                    published_macro_index = macro_index
                    break
                if policy is ExistingFilePolicy.FAIL:
                    raise FileExistsError(
                        f"Generated-video output already exists: {candidate}"
                    )
            finally:
                with suppress(OSError):
                    stage.unlink()
            if policy is not ExistingFilePolicy.CREATE_NEW:
                break
        if published is None:
            raise FileExistsError(
                "No unused generated-video output filename is available."
            )

        metadata = getattr(
            getattr(destination, "_file", None),
            "_file_metadata",
            None,
        )
        if metadata is not None:
            metadata = deepcopy(metadata)
            situation = getattr(metadata, "situation", None)
            variables = getattr(situation, "variables", None)
            if isinstance(variables, dict):
                if "file_extension" in variables:
                    variables["file_extension"] = published.suffix.lstrip(".")
                if published_macro_index is not None:
                    variables["_index"] = published_macro_index
            try:
                write_sidecar(published, metadata)
            except Exception as exc:
                logger.warning(
                    "Generated MP4 was saved, but its metadata sidecar could not "
                    "be written: %s",
                    type(exc).__name__,
                )
        saved = File(str(published))
        mapper = getattr(destination, "_map_to_macro_file", None)
        if callable(mapper):
            try:
                saved = mapper(saved)
            except Exception as exc:
                logger.warning(
                    "Could not map generated MP4 to a project macro: %s",
                    type(exc).__name__,
                )
        return saved

    async def _save_completed_task(
        self,
        final_task: dict[str, Any],
        generation_id: str,
        destination: Any,
        verifier: _MP4DecodeVerifier | None = None,
    ) -> None:
        video_download_url = self._extract_video_url(final_task)
        if not video_download_url:
            raise RuntimeError(
                "FN AI Broker task succeeded but the video URL was missing."
            )
        video_bytes = await self._download_broker_video(video_download_url)
        saved = await self._atomic_publish_completed_mp4(
            destination,
            video_bytes,
            verifier,
        )
        artifact = VideoUrlArtifact(value=saved.location, name=saved.name)
        self.parameter_output_values["video_url"] = artifact
        self.parameter_output_values["VIDEO_OUT"] = artifact
        self.parameter_output_values["last_frame_url"] = (
            self._extract_last_frame_url(final_task)
        )
        self._set_status_results(
            was_successful=True,
            result_details=(
                f"SUCCESS: FN AI Broker task {generation_id} succeeded.\n"
                f"Saved MP4: {saved.location}"
            ),
        )

    async def _refresh_async(self) -> None:
        """Refresh one Broker job without ever creating a replacement task."""
        generation_id = ""
        try:
            generation_id = str(
                self.parameter_output_values.get("generation_id")
                or self.get_parameter_value("resume_generation_id")
                or ""
            ).strip()
            if not generation_id:
                if self._generation_run_active.is_set():
                    return
                self._set_status_results(
                    was_successful=False,
                    result_details=(
                        "No FN AI Broker task ID is available. Run the node once or "
                        "put a confirmed task ID into Resume Task ID."
                    ),
                )
                return
            bridge = await self._ensure_broker_connected()
            generation_id = self._validate_task_id(generation_id)
            try:
                response = await asyncio.to_thread(
                    bridge.refresh_job,
                    generation_id,
                    timeout=60,
                )
            except _BrokerError as exc:
                retry_payload = self._last_broker_payload
                retry_same_request = (
                    exc.status_code == 404
                    and self.parameter_output_values.get("generation_status")
                    == "submission_unknown"
                    and isinstance(retry_payload, dict)
                    and retry_payload.get("client_request_id") == generation_id
                )
                if not retry_same_request:
                    raise
                self._set_broker_task_outputs(
                    {"id": generation_id, "status": "retrying_same_request"},
                    generation_id=generation_id,
                    status="retrying_same_request",
                )
                try:
                    response = await asyncio.to_thread(
                        bridge.generate_seedance,
                        dict(retry_payload),
                        timeout=60,
                    )
                except _BrokerError:
                    self.parameter_output_values["generation_status"] = (
                        "submission_unknown"
                    )
                    raise
            task = self._normalize_broker_task(
                response,
                fallback_job_id=generation_id,
            )
            status = str(task["status"])
            self._set_broker_task_outputs(
                task,
                generation_id=generation_id,
                status=status,
            )
            if status == "succeeded":
                destination = self._output_file.build_file()
                self._preflight_output_destination(destination)
                await self._save_completed_task(task, generation_id, destination)
                return
            if status in TERMINAL_FAILURE_STATUSES:
                self._set_status_results(
                    was_successful=False,
                    result_details=self._broker_terminal_failure_message(
                        task, generation_id
                    ),
                )
                return
            self.status_component.clear_execution_status(
                initial_message=(
                    f"FN AI Broker task {generation_id} is still {status} on the "
                    "server. Rendering continues even if this node disconnects. "
                    "Refresh / Retrieve Result checks this same job only and never "
                    "starts a duplicate render."
                )
            )
        except Exception as exc:
            safe_detail = (
                str(exc) if isinstance(exc, _BrokerError) else type(exc).__name__
            )
            known_status = str(
                self.parameter_output_values.get("generation_status") or ""
            ).strip().lower()
            known_response = self.parameter_output_values.get("provider_response")
            known_terminal = known_status in TERMINAL_FAILURE_STATUSES or bool(
                isinstance(known_response, dict)
                and known_response.get("terminal") is True
            )
            if known_terminal:
                terminal_task = (
                    dict(known_response)
                    if isinstance(known_response, dict)
                    else {}
                )
                terminal_task["status"] = known_status or "failed"
                detail = (
                    self._broker_terminal_failure_message(
                        terminal_task,
                        generation_id or "ID",
                    )
                    + " Refresh could not contact the Broker and did not resume, "
                    "restart, or duplicate this known terminal job. Details: "
                    + safe_detail
                )
            else:
                detail = (
                    "The Broker connection is currently unavailable, but the existing "
                    f"task {generation_id or 'ID'} may still be rendering. Refresh / "
                    "Retrieve Result checks the same job without creating a duplicate. "
                    "Details: "
                    + safe_detail
                )
            self._set_status_results(
                was_successful=False,
                result_details=detail,
            )

    def _on_refresh_clicked(self, _button: Any, _details: Any) -> None:
        with self._generation_refresh_lock:
            if self._generation_refresh_running:
                return
            self._generation_refresh_running = True

        def _finished(_future: Any = None) -> None:
            with self._generation_refresh_lock:
                self._generation_refresh_running = False

        try:
            event_loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if event_loop is not None and event_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._refresh_async(), event_loop
                )
                future.add_done_callback(_finished)
                return
        except Exception:
            pass

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._refresh_async())
            finally:
                loop.close()
                _finished()

        try:
            threading.Thread(
                target=_runner,
                name=f"{self.name}-refresh",
                daemon=True,
            ).start()
        except Exception:
            _finished()
            raise

    async def _process_generation(self) -> None:
        self._cleanup_temporary_video_uploads()
        self._submission_outcome_unknown = False
        try:
            await self._process_generation_impl()
        finally:
            if self._submission_outcome_unknown:
                self._defer_temporary_video_upload_cleanup()
            else:
                self._cleanup_temporary_video_uploads()

    async def _process_generation_impl(self) -> None:
        """Submit and poll Seedance exclusively through the FN AI Broker."""
        self._set_safe_defaults()
        params = self._get_parameters()
        self._validate_parameters(params)
        resume_generation_id = params["resume_generation_id"]
        decode_verifier: _MP4DecodeVerifier | None = None

        # Resolve the save target before the billable Broker POST.
        destination = self._output_file.build_file()
        self._preflight_output_destination(destination)
        if not resume_generation_id:
            # A new render can incur usage. Prove that this installation can
            # decode-verify the completed MP4 before contacting/authenticating
            # with the Broker or preparing any temporary reference uploads.
            decode_verifier = await asyncio.to_thread(
                _resolve_mp4_decode_verifier
            )
            logger.info(
                "%s using MP4 decode verifier %s (%s)",
                self.name,
                decode_verifier.executable,
                decode_verifier.backend,
            )
        # The Broker generation request is the sole usage/quota/accounting authority.
        bridge = await self._ensure_broker_connected()

        started = self._monotonic()
        timeout = params["generation_timeout_seconds"]
        deadline = started + timeout
        poll_interval = params["poll_interval_seconds"]
        final_task: dict[str, Any] | None = None

        if resume_generation_id:
            generation_id = self._validate_task_id(resume_generation_id)
            self._set_broker_task_outputs(
                {"id": generation_id, "status": "resuming"},
                generation_id=generation_id,
                status="resuming",
            )
            logger.info("%s resuming FN AI Broker task %s", self.name, generation_id)
        else:
            params = self._prepare_video_references_for_run(params)
            payload = self._build_broker_payload(params)
            client_request_id = "hmb-" + uuid4().hex
            payload["client_request_id"] = client_request_id
            self._last_broker_payload = dict(payload)
            self._set_broker_task_outputs(
                {"id": client_request_id, "status": "submitting"},
                generation_id=client_request_id,
                status="submitting",
            )
            try:
                response, submission_cancelled = await self._await_submission_result(
                    bridge.generate_seedance,
                    payload,
                    timeout=min(float(timeout), 1200.0),
                )
            except _BrokerError as exc:
                if exc.submission_outcome_unknown:
                    self._submission_outcome_unknown = True
                    self.parameter_output_values["generation_status"] = (
                        "submission_unknown"
                    )
                    self.parameter_output_values["provider_response"] = {
                        "transport": "fn_ai_broker",
                        "id": client_request_id,
                        "status": "submission_unknown",
                    }
                raise
            task = self._normalize_broker_task(response)
            generation_id = str(task["id"])
            status = str(task["status"])
            self._submission_outcome_unknown = False
            self._set_broker_task_outputs(
                task,
                generation_id=generation_id,
                status=status,
            )
            logger.info(
                "%s submitted Seedance model %s through FN AI Broker as task %s",
                self.name,
                params["model_id"],
                generation_id,
            )
            if status == "succeeded":
                final_task = task
            elif status in TERMINAL_FAILURE_STATUSES:
                raise RuntimeError(
                    self._broker_terminal_failure_message(task, generation_id)
                )
            if submission_cancelled:
                self.parameter_output_values["generation_status"] = "cancelled_locally"
                raise asyncio.CancelledError(
                    "Local cancellation arrived during submission. The FN AI Broker "
                    f"task ID was recovered as {generation_id}; use Refresh / Retrieve "
                    "Result for this same task."
                )

        while final_task is None:
            if self.is_cancellation_requested:
                self.parameter_output_values["generation_status"] = "cancelled_locally"
                raise asyncio.CancelledError(
                    "Local Broker polling stopped, but the server render continues. "
                    "Use Refresh / Retrieve Result for this same task."
                )
            now = self._monotonic()
            if now >= deadline:
                self.parameter_output_values["generation_status"] = "timed_out"
                raise TimeoutError(
                    f"FN AI Broker task {generation_id} did not finish within "
                    f"{timeout} seconds. The server render continues; use Refresh / "
                    "Retrieve Result for this same ID instead of starting a new render."
                )

            response = await asyncio.to_thread(
                bridge.refresh_job,
                generation_id,
                timeout=min(60.0, max(1.0, deadline - now)),
            )
            task = self._normalize_broker_task(
                response,
                fallback_job_id=generation_id,
            )
            if str(task["id"]) != generation_id:
                raise _BrokerError("FN AI Broker returned a different task ID.")
            status = str(task["status"])
            self._set_broker_task_outputs(
                task,
                generation_id=generation_id,
                status=status,
            )
            logger.info(
                "%s FN AI Broker task %s status: %s",
                self.name,
                generation_id,
                status,
            )
            if status == "succeeded":
                final_task = task
                break
            if status in TERMINAL_FAILURE_STATUSES:
                raise RuntimeError(
                    self._broker_terminal_failure_message(task, generation_id)
                )
            remaining = deadline - self._monotonic()
            if remaining > 0:
                await self._sleep(min(poll_interval, remaining))

        await self._save_completed_task(
            final_task,
            generation_id,
            destination,
            decode_verifier,
        )


    async def aprocess(self) -> None:
        self._generation_run_active.set()
        try:
            await self._aprocess_impl()
        finally:
            self._generation_run_active.clear()

    async def _aprocess_impl(self) -> None:
        self._clear_execution_status()
        try:
            await self._process_generation()
        except asyncio.CancelledError:
            generation_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            resume_guidance = (
                f" Use Refresh / Retrieve Result for the same task {generation_id}; "
                "it never starts a replacement render."
                if generation_id
                else ""
            )
            self._set_status_results(
                was_successful=False,
                result_details=(
                    (
                        "CANCELLED: Local Seedance polling stopped. The FN AI Broker "
                        "task continues remotely and may still incur charges."
                        if generation_id
                        else "CANCELLED: Generation stopped before a task ID was received."
                    )
                    + resume_guidance
                ),
            )
            raise
        except Exception as exc:
            safe_message = self._safe_exception_message(exc)
            generation_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            generation_status = str(
                self.parameter_output_values.get("generation_status") or ""
            ).strip()
            provider_response = self.parameter_output_values.get("provider_response")
            terminal = generation_status in TERMINAL_FAILURE_STATUSES or (
                isinstance(provider_response, dict)
                and provider_response.get("terminal") is True
            )
            if generation_id:
                if terminal:
                    safe_message += (
                        f"\nExisting task ID: {generation_id}. This Broker job is "
                        "terminal. Refresh / Retrieve Result only retrieves the same "
                        "final state; it does not resume, restart, or duplicate "
                        "a render."
                    )
                else:
                    safe_message += (
                        f"\nExisting task ID: {generation_id}. The server render can "
                        "continue after a disconnect. Use Refresh / Retrieve Result to "
                        "check this same task without creating a duplicate."
                    )
            submission_unknown = (
                isinstance(exc, _BrokerError) and exc.submission_outcome_unknown
            )
            if submission_unknown:
                self.parameter_output_values["generation_status"] = (
                    "submission_unknown"
                )
                safe_message += (
                    "\nRefresh / Retrieve Result will use the same client request ID. "
                    "If the server never received the first POST, it repeats the exact "
                    "request with that same idempotency key, never a new key."
                    "\nTemporary local video uploads are being retained for up to "
                    "30 minutes so an accepted remote task can still fetch them."
                )
            elif not self.parameter_output_values.get("generation_status"):
                self.parameter_output_values["generation_status"] = "failed"
            self._set_status_results(
                was_successful=False,
                result_details=f"FAILURE: {safe_message}",
            )
            self._handle_failure_exception(RuntimeError(safe_message))

__all__ = [
    "GT_CLOUD_API_KEY_SECRET",
    "GT_CLOUD_BUCKET_ID_SECRET",
    "TOS_ACCESS_KEY_ID_SECRET",
    "TOS_SECRET_ACCESS_KEY_SECRET",
    "TOS_BUCKET_NAME_SECRET",
    "HMBSeedanceGeneration",
    "LOCAL_VIDEO_UPLOAD_GRIPTAPE",
    "LOCAL_VIDEO_UPLOAD_TOS",
    "MAX_REFERENCE_IMAGES",
    "MAX_VIDEO_REFERENCES",
    "MAX_REFERENCE_AUDIO",
    "VIDEO_REFERENCES_PARAMETER",
]
