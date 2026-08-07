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
import secrets
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager, suppress
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
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
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

ARK_API_KEY_SECRET = "ARK_API_KEY"
GT_CLOUD_API_KEY_SECRET = "GT_CLOUD_API_KEY"
GT_CLOUD_BUCKET_ID_SECRET = "GT_CLOUD_BUCKET_ID"
TOS_ACCESS_KEY_ID_SECRET = "TOS_ACCESS_KEY_ID"
TOS_SECRET_ACCESS_KEY_SECRET = "TOS_SECRET_ACCESS_KEY"
TOS_BUCKET_NAME_SECRET = "TOS_BUCKET_NAME"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
CREATE_TASK_PATH = "/contents/generations/tasks"
AI_BROKER_SERVER_URL = os.environ.get(
    "HMB_AI_BROKER_URL", "http://192.168.203.245:8080"
).rstrip("/")
AI_BROKER_CGTW_SERVERS = frozenset(
    {
        "192.168.200.18:8383",
        "cgteamwork.funnyflux.kr:443",
    }
)
AI_BROKER_MAX_JSON_BYTES = 16 * 1024 * 1024

USAGE_GENERATOR_ID = "HMBSeedance20VideoGeneration"
USAGE_SCHEMA_VERSION = 1
USAGE_LEDGER_ROOT = Path(
    r"\\fin-rcomp1\Composite_Team\00.CompSource\Griptape_list"
)
USAGE_LOCAL_QUEUE_ROOT = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    / "HMB"
    / "SeedanceUsageQueue"
    / USAGE_GENERATOR_ID
)
USAGE_TIMEZONE = timezone(timedelta(hours=9), name="Asia/Seoul")
USAGE_LEDGER_LOCK_WAIT_SECONDS = 5.0
USAGE_LEDGER_STALE_LOCK_SECONDS = 120.0
USAGE_PRICING_VERSION = "2026-08-05-public-list"

LOCAL_VIDEO_UPLOAD_GRIPTAPE = "Griptape Cloud (Existing)"
LOCAL_VIDEO_UPLOAD_TOS = "Volcengine TOS"
LOCAL_VIDEO_UPLOAD_SERVICES = (
    LOCAL_VIDEO_UPLOAD_GRIPTAPE,
    LOCAL_VIDEO_UPLOAD_TOS,
)
DEFAULT_TOS_REGION = "cn-beijing"
DEFAULT_TOS_ENDPOINT = "tos-cn-beijing.volces.com"
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
    SEEDANCE_2_0_MODEL_ID: ("480p", "720p", "1080p", "4k"),
    SEEDANCE_2_0_FAST_MODEL_ID: ("480p", "720p"),
    SEEDANCE_2_0_MINI_MODEL_ID: ("480p", "720p"),
}

# Public list prices in CNY per one million tokens. They are stored with every
# task so a later price change cannot rewrite historical estimates.
USAGE_PRICE_CNY_PER_MILLION = {
    SEEDANCE_2_0_MODEL_ID: {
        "with_video_input": Decimal("28"),
        "without_video_input": Decimal("46"),
    },
    SEEDANCE_2_0_FAST_MODEL_ID: {
        "with_video_input": Decimal("22"),
        "without_video_input": Decimal("37"),
    },
    SEEDANCE_2_0_MINI_MODEL_ID: {
        "with_video_input": Decimal("14"),
        "without_video_input": Decimal("23"),
    },
}

RATIOS = ("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
TERMINAL_FAILURE_STATUSES = {"failed", "cancelled", "expired"}
ACTIVE_STATUSES = {"queued", "running"}
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
POST_REQUEST_TIMEOUT_SECONDS = 300.0
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
_USAGE_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
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

_USAGE_FLUSH_GUARD = threading.Lock()


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


def _broker_normalize_cgtw_server(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw if "://" in raw else f"//{raw}")
        scheme = parsed.scheme.lower()
        if scheme not in {"", "http", "https"}:
            return ""
        if (
            parsed.username is not None
            or parsed.password is not None
            or not parsed.hostname
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            return ""
        port = parsed.port
    except (TypeError, ValueError):
        return ""

    hostname = parsed.hostname.lower().rstrip(".")
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
    return f"{hostname}:{port}" if port is not None else hostname


def _broker_cgtw_session() -> tuple[Any, str]:
    cgtw_base = r"C:\CgTeamWork_v7\bin\base"
    if cgtw_base not in sys.path:
        sys.path.insert(0, cgtw_base)
    try:
        import cgtw2  # type: ignore[import-not-found]
    except Exception as exc:
        raise _BrokerAuthenticationError(
            "CGTeamwork is unavailable for FN AI Broker login."
        ) from exc
    session = cgtw2.tw()
    token = str(session.login.token() or "")
    server = _broker_normalize_cgtw_server(session.login.http_server_ip())
    if not token or server not in AI_BROKER_CGTW_SERVERS:
        raise _BrokerAuthenticationError(
            "CGTeamwork login is required for FN AI Broker."
        )
    return session, token


def _broker_read_json(response: Any, *, max_bytes: int) -> Any:
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise _BrokerProtocolError("FN AI Broker response was too large.")
    try:
        return json.loads(raw or b"{}")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _BrokerProtocolError("FN AI Broker returned invalid JSON.") from exc


def _broker_auto_login() -> dict[str, Any]:
    """Exchange CGTeamwork auth and return only non-sensitive account state."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _, cgtw_token = _broker_cgtw_session()
    server_url = _broker_validated_server_url()
    opener = urllib.request.build_opener(_BrokerNoRedirectHandler())
    try:
        with opener.open(
            server_url + "/api/auth/cgtw/public-key", timeout=8
        ) as response:
            key_data = _broker_read_json(response, max_bytes=2 * 1024 * 1024)
    except _BrokerError:
        raise
    except Exception as exc:
        raise _BrokerUnavailableError(
            "FN AI Broker authentication service is unavailable."
        ) from exc
    if not isinstance(key_data, dict) or not isinstance(
        key_data.get("public_key"), str
    ):
        raise _BrokerProtocolError(
            "FN AI Broker public-key response was invalid."
        )
    response_key = os.urandom(32)
    public_key = serialization.load_pem_public_key(key_data["public_key"].encode())
    encrypted = public_key.encrypt(
        json.dumps(
            {
                "token": cgtw_token,
                "issued_at": int(time.time()),
                "nonce": secrets.token_urlsafe(24),
                "response_key": base64.b64encode(response_key).decode("ascii"),
                "retry_rejected": True,
                "widget_flow_id": "hmb-seedance-2-0",
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    request = urllib.request.Request(
        server_url + "/api/auth/cgtw",
        json.dumps(
            {"encrypted_payload": base64.b64encode(encrypted).decode("ascii")}
        ).encode("utf-8"),
        {"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with opener.open(request, timeout=15) as response:
            wrapped = _broker_read_json(response, max_bytes=2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read(2 * 1024 * 1024) or b"{}")
        except Exception:
            detail = {}
        status = str(detail.get("request_status") or "").strip().lower()
        if status in {"pending", "rejected", "blocked"}:
            return {"status": status}
        raise _BrokerAuthenticationError(
            "FN AI Broker CGTeamwork authentication failed.",
            status_code=exc.code,
        ) from exc
    except _BrokerError:
        raise
    except Exception as exc:
        raise _BrokerUnavailableError(
            "FN AI Broker authentication service is unavailable."
        ) from exc
    if not isinstance(wrapped, dict):
        raise _BrokerProtocolError(
            "FN AI Broker authentication response was invalid."
        )
    try:
        clear = AESGCM(response_key).decrypt(
            base64.b64decode(wrapped["iv"]),
            base64.b64decode(wrapped["encrypted_response"]),
            b"fn-ai-cgtw-v1",
        )
        result = json.loads(clear)
    except Exception as exc:
        raise _BrokerProtocolError(
            "FN AI Broker authentication response was invalid."
        ) from exc
    if not isinstance(result, dict):
        raise _BrokerProtocolError(
            "FN AI Broker authentication response was invalid."
        )
    _broker_save_token(str(result.get("access_token") or ""))
    display_name = result.get("display_name")
    return {
        "status": "connected",
        "display_name": display_name if isinstance(display_name, str) else "",
    }


class _HMBAIBrokerBridge:
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
            "aspect_ratio",
            "generate_audio",
            "watermark",
            "return_last_frame",
            "execution_expires_after",
            "priority",
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
            "aspect_ratio",
            "generate_audio",
            "watermark",
        }
    )
    _MODEL_GENERATION_FIELDS = {
        SEEDANCE_2_0_MODEL_ID: _COMMON_SEEDANCE_FIELDS,
        SEEDANCE_2_0_FAST_MODEL_ID: _COMMON_SEEDANCE_FIELDS
        | frozenset(
            {
                "input_mode",
                "first_frame",
                "last_frame",
                "return_last_frame",
                "execution_expires_after",
            }
        ),
        SEEDANCE_2_0_MINI_MODEL_ID: _COMMON_SEEDANCE_FIELDS,
    }
    _PROMPT_REQUIRED_MODELS = frozenset(
        {SEEDANCE_2_0_MODEL_ID, SEEDANCE_2_0_MINI_MODEL_ID}
    )

    def __init__(self, *, opener: Any | None = None) -> None:
        self._opener = opener or urllib.request.build_opener(
            _BrokerNoRedirectHandler()
        )

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

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None,
        timeout: float,
        submission: bool = False,
    ) -> dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise _BrokerProtocolError("FN AI Broker request path is invalid.")
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + _broker_load_token(),
        }
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
            raise _BrokerError(
                f"FN AI Broker request failed with HTTP {exc.code}.",
                status_code=exc.code,
            ) from exc
        except _BrokerError:
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
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
            login_result = _broker_auto_login()
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
        if model in self._PROMPT_REQUIRED_MODELS and not str(
            request_payload.get("prompt") or ""
        ).strip():
            raise _BrokerProtocolError(
                "The selected FN AI Broker Seedance model requires a prompt."
            )
        if model != SEEDANCE_2_0_FAST_MODEL_ID:
            if request_payload.get("first_frame") or request_payload.get("last_frame"):
                raise _BrokerProtocolError(
                    "First/Last Frame mode currently requires Seedance 2.0 Fast "
                    "on FN AI Broker."
                )
            if request_payload.get("return_last_frame") is True:
                raise _BrokerProtocolError(
                    "Return Last Frame currently requires Seedance 2.0 Fast "
                    "on FN AI Broker."
                )
            expires = request_payload.get("execution_expires_after")
            if expires not in (None, 172800):
                raise _BrokerProtocolError(
                    "Custom task expiry currently requires Seedance 2.0 Fast "
                    "on FN AI Broker."
                )
        priority = request_payload.get("priority")
        if priority not in (None, 0):
            raise _BrokerProtocolError(
                "Task priority is not supported by the current FN AI Broker "
                "Seedance schema."
            )
        request_payload = {
            key: value for key, value in request_payload.items() if key in model_fields
        }
        return self._request_json(
            "POST",
            "/api/v1/generate/video",
            payload=request_payload,
            timeout=timeout,
            submission=True,
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


class VolcengineAPIError(RuntimeError):
    """Provider error that never stores an authorization value."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_json: dict[str, Any] | None = None,
        submission_outcome: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_json = response_json
        self.submission_outcome = submission_outcome


class HMBSeedance20VideoGeneration(SuccessFailureNode):
    """Generate Seedance 2.0 video through the authenticated FN AI Broker.

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
            "Generate Seedance 2.0 video through the authenticated FN AI Broker "
            "using server-managed provider credentials."
        )
        self._temporary_video_uploads: list[
            tuple[GriptapeCloudStorageDriver, Path]
        ] = []
        self._temporary_tos_video_uploads: list[tuple[Any, str, str]] = []
        self._submission_outcome_unknown = False
        self._usage_identity: dict[str, str] | None = None
        self._usage_context: dict[str, Any] = {}
        self._broker_bridge_instance: _HMBAIBrokerBridge | None = None
        self._broker_action_lock = threading.Lock()
        self._broker_action_running = False
        self._generation_refresh_lock = threading.Lock()
        self._generation_refresh_running = False

        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value=MODEL_NAME_SEEDANCE_2_0,
                tooltip="Volcengine Seedance 2.0 model variant.",
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
                tooltip="Text prompt for Seedance 2.0.",
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
                    "service so Volcengine Seedance 2.0 can read them. The temporary "
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
                default_value="720p",
                tooltip="480p/720p; Standard also supports 1080p and 4k.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["480p", "720p", "1080p", "4k"])},
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
            default_filename="volcengine_seedance_2_0_video.mp4",
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
                    "Use safe GET requests to re-check a known task or list "
                    "candidates after an ambiguous submission."
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
                    "Connect with the active CGTeamwork account or refresh the "
                    "current FN AI Broker session."
                ),
                on_click=self._on_broker_connect_clicked,
            )
            ParameterString(
                name="broker_notice",
                default_value=(
                    "Provider credentials stay on the Broker server and are never "
                    "stored in this node."
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
        raw_model = self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
        model_id = MODEL_ID_ALIASES.get(str(raw_model), str(raw_model))
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
            "resolution": str(self.get_parameter_value("resolution") or "720p"),
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

    @staticmethod
    def _validated_usage_user_id(value: Any) -> str:
        user_id = str(value or "").strip()
        if not user_id or _USAGE_USER_ID_PATTERN.fullmatch(user_id) is None:
            raise ValueError("Griptape user ID is missing or unsafe for usage storage.")
        if user_id in {".", ".."}:
            raise ValueError("Griptape user ID is unsafe for usage storage.")
        return user_id

    def _capture_usage_identity(self) -> dict[str, str] | None:
        """Capture the logged-in account without persisting a login credential."""
        if self._usage_identity is not None:
            return dict(self._usage_identity)
        try:
            user = GriptapeNodes.UserManager().user
            if user is None:
                logger.warning(
                    "%s usage ledger skipped because no logged-in user was available.",
                    USAGE_GENERATOR_ID,
                )
                return None
            raw_user_id = (
                user.get("id") if isinstance(user, dict) else getattr(user, "id", "")
            )
            user_id = self._validated_usage_user_id(raw_user_id)
        except Exception as exc:
            logger.warning(
                "%s could not resolve the logged-in user for usage accounting: %s",
                USAGE_GENERATOR_ID,
                type(exc).__name__,
            )
            return None
        self._usage_identity = {"user_id": user_id}
        return dict(self._usage_identity)

    def _prepare_usage_tracking(
        self, params: dict[str, Any], *, existing_task: bool
    ) -> None:
        identity = self._capture_usage_identity()
        self._usage_context = {
            "identity": identity,
            "model": str(params.get("model_id") or ""),
            "resolution": str(params.get("resolution") or ""),
            "ratio": str(params.get("ratio") or ""),
            "duration": params.get("duration"),
            "generate_audio": bool(params.get("generate_audio")),
            # A resumed/recovered task may have been authored with different
            # inputs. Preserve an existing ledger value rather than guessing.
            "has_video_input": (
                None
                if existing_task
                else bool(params.get("video_references"))
            ),
        }
        if identity is not None:
            self._schedule_usage_flush()

    @staticmethod
    def _usage_nonnegative_int(value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _usage_decimal_text(value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    @staticmethod
    def _usage_now() -> datetime:
        return datetime.now(USAGE_TIMEZONE)

    @classmethod
    def _usage_task_datetime(cls, task: dict[str, Any]) -> datetime:
        for field in ("updated_at", "created_at"):
            timestamp = cls._usage_nonnegative_int(task.get(field))
            if timestamp is None:
                continue
            try:
                return datetime.fromtimestamp(
                    timestamp, tz=timezone.utc
                ).astimezone(USAGE_TIMEZONE)
            except (OSError, OverflowError, ValueError):
                continue
        return cls._usage_now()

    @classmethod
    def _usage_price(
        cls, model: str, has_video_input: bool | None
    ) -> Decimal | None:
        if has_video_input is None:
            return None
        rates = USAGE_PRICE_CNY_PER_MILLION.get(model)
        if not rates:
            return None
        key = "with_video_input" if has_video_input else "without_video_input"
        return rates[key]

    def _build_usage_event(
        self, task: dict[str, Any], generation_id: str, status: str
    ) -> dict[str, Any] | None:
        identity = self._usage_context.get("identity")
        if not isinstance(identity, dict):
            return None
        user_id = self._validated_usage_user_id(identity.get("user_id"))
        task_id = self._validate_task_id(generation_id)
        safe_status = str(status or "unknown").strip().lower() or "unknown"
        model = str(task.get("model") or self._usage_context.get("model") or "")
        usage = task.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        completion_tokens = self._usage_nonnegative_int(
            usage.get("completion_tokens")
        )
        total_tokens = self._usage_nonnegative_int(usage.get("total_tokens"))
        has_video_input = self._usage_context.get("has_video_input")
        if not isinstance(has_video_input, bool):
            has_video_input = None
        rate = self._usage_price(model, has_video_input)
        estimated_cost = (
            Decimal(total_tokens) * rate / Decimal(1_000_000)
            if total_tokens is not None and rate is not None
            else None
        )
        task_datetime = self._usage_task_datetime(task)
        recorded_at = self._usage_now()
        duration = task.get("duration", self._usage_context.get("duration"))
        if not isinstance(duration, (int, str)) or isinstance(duration, bool):
            duration = None
        resolution = str(
            task.get("resolution") or self._usage_context.get("resolution") or ""
        )
        ratio = str(task.get("ratio") or self._usage_context.get("ratio") or "")
        return {
            "schema_version": USAGE_SCHEMA_VERSION,
            "generator": USAGE_GENERATOR_ID,
            "user_id": user_id,
            "task_id": task_id,
            "billing_month": task_datetime.strftime("%Y-%m"),
            "status": safe_status,
            "model": model or None,
            "resolution": resolution or None,
            "ratio": ratio or None,
            "duration_seconds": duration,
            "generate_audio": self._usage_context.get("generate_audio"),
            "has_video_input": has_video_input,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "usage_source": (
                "provider_response" if total_tokens is not None else "not_returned"
            ),
            "pricing_version": USAGE_PRICING_VERSION if rate is not None else None,
            "rate_cny_per_million_tokens": (
                self._usage_decimal_text(rate) if rate is not None else None
            ),
            "estimated_cost_cny": (
                self._usage_decimal_text(estimated_cost)
                if estimated_cost is not None
                else None
            ),
            "provider_created_at": self._usage_nonnegative_int(task.get("created_at")),
            "provider_updated_at": self._usage_nonnegative_int(task.get("updated_at")),
            "recorded_at": recorded_at.isoformat(),
        }

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n"
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            with suppress(OSError):
                temporary.unlink()

    @classmethod
    def _enqueue_usage_event(cls, event: dict[str, Any]) -> Path:
        if event.get("generator") != USAGE_GENERATOR_ID:
            raise ValueError("Usage event belongs to a different generator.")
        user_id = cls._validated_usage_user_id(event.get("user_id"))
        cls._validate_task_id(event.get("task_id"))
        queue_directory = USAGE_LOCAL_QUEUE_ROOT / user_id
        queue_path = queue_directory / f"{time.time_ns()}-{uuid4().hex}.json"
        cls._write_json_atomic(queue_path, event)
        return queue_path

    @classmethod
    @contextmanager
    def _usage_ledger_lock(cls, user_directory: Path):
        lock_path = user_directory / ".usage-ledger.lock"
        deadline = time.monotonic() + USAGE_LEDGER_LOCK_WAIT_SECONDS
        acquired = False
        while not acquired:
            try:
                lock_path.mkdir()
                acquired = True
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                    if age >= USAGE_LEDGER_STALE_LOCK_SECONDS:
                        lock_path.rmdir()
                        continue
                except (FileNotFoundError, OSError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for the usage ledger lock.")
                time.sleep(0.05)
        try:
            yield
        finally:
            if acquired:
                with suppress(OSError):
                    lock_path.rmdir()

    @classmethod
    def _new_usage_ledger(cls, user_id: str) -> dict[str, Any]:
        return {
            "schema_version": USAGE_SCHEMA_VERSION,
            "generator": USAGE_GENERATOR_ID,
            "user_id": user_id,
            "months": {},
        }

    @classmethod
    def _recompute_usage_month(cls, month: dict[str, Any]) -> None:
        tasks = month.get("tasks")
        if not isinstance(tasks, dict):
            tasks = {}
            month["tasks"] = tasks
        total_tokens = 0
        total_cost = Decimal("0")
        succeeded = 0
        failed = 0
        pending = 0
        unknown = 0
        for task in tasks.values():
            if not isinstance(task, dict):
                continue
            tokens = cls._usage_nonnegative_int(task.get("total_tokens"))
            if tokens is not None:
                total_tokens += tokens
            try:
                cost = task.get("estimated_cost_cny")
                if cost is not None:
                    total_cost += Decimal(str(cost))
            except (InvalidOperation, TypeError, ValueError):
                pass
            status = str(task.get("status") or "unknown").lower()
            if status == "succeeded":
                succeeded += 1
            elif status in TERMINAL_FAILURE_STATUSES:
                failed += 1
            elif status in {
                "submitted",
                "queued",
                "running",
                "resuming",
                "timed_out",
                "cancelled_locally",
            }:
                pending += 1
            else:
                unknown += 1
        month["summary"] = {
            "task_count": len(tasks),
            "succeeded": succeeded,
            "failed": failed,
            "pending": pending,
            "unknown": unknown,
            "total_tokens": total_tokens,
            "estimated_cost_cny": cls._usage_decimal_text(total_cost),
        }

    @classmethod
    def _merge_usage_event(
        cls, ledger: dict[str, Any], event: dict[str, Any]
    ) -> dict[str, Any]:
        user_id = cls._validated_usage_user_id(event.get("user_id"))
        if ledger.get("generator") != USAGE_GENERATOR_ID:
            raise ValueError("Usage ledger belongs to a different generator.")
        if ledger.get("user_id") != user_id:
            raise ValueError("Usage ledger user ID does not match the event.")
        if ledger.get("schema_version") != USAGE_SCHEMA_VERSION:
            raise ValueError("Unsupported usage ledger schema version.")
        months = ledger.get("months")
        if not isinstance(months, dict):
            raise ValueError("Usage ledger months value is invalid.")
        billing_month = str(event.get("billing_month") or "")
        if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", billing_month) is None:
            raise ValueError("Usage event billing month is invalid.")
        task_id = cls._validate_task_id(event.get("task_id"))

        existing: dict[str, Any] = {}
        existing_month_key: str | None = None
        for month_key, month_value in list(months.items()):
            if not isinstance(month_value, dict):
                raise ValueError("Usage ledger month entry is invalid.")
            tasks = month_value.get("tasks")
            if tasks is None:
                tasks = {}
                month_value["tasks"] = tasks
            if not isinstance(tasks, dict):
                raise ValueError("Usage ledger task map is invalid.")
            candidate = tasks.pop(task_id, None)
            if isinstance(candidate, dict):
                if not existing or str(candidate.get("last_recorded_at") or "") >= str(
                    existing.get("last_recorded_at") or ""
                ):
                    existing = candidate
                    existing_month_key = month_key

        allowed_fields = (
            "status",
            "model",
            "resolution",
            "ratio",
            "duration_seconds",
            "generate_audio",
            "has_video_input",
            "completion_tokens",
            "total_tokens",
            "usage_source",
            "pricing_version",
            "rate_cny_per_million_tokens",
            "estimated_cost_cny",
            "provider_created_at",
            "provider_updated_at",
        )
        event_recorded_at = str(event.get("recorded_at") or "")
        existing_recorded_at = str(existing.get("last_recorded_at") or "")
        incoming_is_newer = not existing_recorded_at or (
            event_recorded_at >= existing_recorded_at
        )
        merged = dict(existing)
        if not merged.get("first_recorded_at"):
            merged["first_recorded_at"] = event_recorded_at
        for field in allowed_fields:
            value = event.get(field)
            if value is None:
                continue
            if incoming_is_newer or merged.get(field) is None:
                merged[field] = value
        if incoming_is_newer:
            merged["last_recorded_at"] = event_recorded_at
        merged["task_id"] = task_id
        merged["generator"] = USAGE_GENERATOR_ID

        destination_month = (
            billing_month
            if incoming_is_newer or existing_month_key is None
            else existing_month_key
        )
        destination = months.setdefault(destination_month, {"tasks": {}})
        if not isinstance(destination, dict):
            raise ValueError("Usage ledger destination month is invalid.")
        destination_tasks = destination.setdefault("tasks", {})
        if not isinstance(destination_tasks, dict):
            raise ValueError("Usage ledger destination task map is invalid.")
        destination_tasks[task_id] = merged

        for month_key, month_value in list(months.items()):
            tasks = month_value.get("tasks") if isinstance(month_value, dict) else None
            if not isinstance(tasks, dict) or not tasks:
                months.pop(month_key, None)
                continue
            cls._recompute_usage_month(month_value)
        ledger["updated_at"] = cls._usage_now().isoformat()
        return ledger

    @classmethod
    def _write_usage_event_to_share(cls, event: dict[str, Any]) -> None:
        if event.get("generator") != USAGE_GENERATOR_ID:
            raise ValueError("Usage event belongs to a different generator.")
        user_id = cls._validated_usage_user_id(event.get("user_id"))
        user_directory = USAGE_LEDGER_ROOT / user_id
        user_directory.mkdir(parents=True, exist_ok=True)
        ledger_path = user_directory / f"{user_id}.json"
        with cls._usage_ledger_lock(user_directory):
            if ledger_path.exists():
                try:
                    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        "Existing usage ledger is unreadable and was not overwritten."
                    ) from exc
                if not isinstance(ledger, dict):
                    raise ValueError(
                        "Existing usage ledger is invalid and was not overwritten."
                    )
            else:
                ledger = cls._new_usage_ledger(user_id)
            updated = cls._merge_usage_event(ledger, event)
            cls._write_json_atomic(ledger_path, updated)

    @classmethod
    def _flush_usage_queue(cls) -> None:
        if not USAGE_LOCAL_QUEUE_ROOT.exists():
            return
        for queue_path in sorted(USAGE_LOCAL_QUEUE_ROOT.glob("*/*.json")):
            try:
                event = json.loads(queue_path.read_text(encoding="utf-8"))
                if not isinstance(event, dict):
                    continue
                if event.get("generator") != USAGE_GENERATOR_ID:
                    continue
                cls._write_usage_event_to_share(event)
                queue_path.unlink()
            except (OSError, TimeoutError):
                # The durable local event remains for the next execution.
                break
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "%s retained an invalid usage queue item: %s",
                    USAGE_GENERATOR_ID,
                    type(exc).__name__,
                )

    @classmethod
    def _schedule_usage_flush(cls) -> None:
        if not _USAGE_FLUSH_GUARD.acquire(blocking=False):
            return

        def _runner() -> None:
            try:
                cls._flush_usage_queue()
            except Exception as exc:
                logger.warning(
                    "%s background usage sync stopped safely: %s",
                    USAGE_GENERATOR_ID,
                    type(exc).__name__,
                )
            finally:
                _USAGE_FLUSH_GUARD.release()

        thread = threading.Thread(
            target=_runner,
            name="HMBSeedance20-usage-sync",
            daemon=True,
        )
        thread.start()

    def _record_usage_task(
        self, task: dict[str, Any], generation_id: str, status: str
    ) -> None:
        """Durably queue an invisible usage snapshot without affecting a render."""
        try:
            event = self._build_usage_event(task, generation_id, status)
            if event is None:
                return
            self._enqueue_usage_event(event)
            self._schedule_usage_flush()
        except Exception as exc:
            logger.warning(
                "%s usage snapshot was skipped safely: %s",
                USAGE_GENERATOR_ID,
                type(exc).__name__,
            )

    def _record_current_usage_status(self, status: str | None = None) -> None:
        generation_id = str(
            self.parameter_output_values.get("generation_id") or ""
        ).strip()
        if not generation_id:
            return
        response = self.parameter_output_values.get("provider_response")
        task = dict(response) if isinstance(response, dict) else {}
        task["id"] = generation_id
        effective_status = str(
            status
            or self.parameter_output_values.get("generation_status")
            or task.get("status")
            or "unknown"
        )
        task["status"] = effective_status
        self._record_usage_task(task, generation_id, effective_status)

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

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        try:
            self._validate_parameters(self._get_parameters())
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
                    return HMBSeedance20VideoGeneration._coerce_reference_value(
                        value[key], depth=depth + 1
                    )
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            serialized = to_dict()
            if serialized is not value:
                return HMBSeedance20VideoGeneration._coerce_reference_value(
                    serialized, depth=depth + 1
                )
        for attribute in ("value", "location", "path"):
            candidate = getattr(value, attribute, None)
            if candidate is not None and candidate is not value:
                return HMBSeedance20VideoGeneration._coerce_reference_value(
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

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        self._validate_parameters(params)
        content: list[dict[str, Any]] = []
        prompt = params["prompt"].strip()
        if prompt:
            content.append({"type": "text", "text": prompt})

        if params["input_mode"] == INPUT_MODE_FIRST_LAST_FRAME:
            if params["first_frame"]:
                first_frame = self._prepare_media_reference(
                    "image", params["first_frame"]
                )
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": first_frame},
                        "role": "first_frame",
                    }
                )
            if params["last_frame"]:
                last_frame = self._prepare_media_reference(
                    "image", params["last_frame"]
                )
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": last_frame},
                        "role": "last_frame",
                    }
                )
        elif params["input_mode"] == INPUT_MODE_MULTIMODAL_REFERENCES:
            for value in params["reference_images"]:
                prepared = self._prepare_media_reference("image", value)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": prepared},
                        "role": "reference_image",
                    }
                )
            for value in params["video_references"]:
                prepared = self._prepare_media_reference("video", value)
                content.append(
                    {
                        "type": "video_url",
                        "video_url": {"url": prepared},
                        "role": "reference_video",
                    }
                )
            for value in params["reference_audio"]:
                prepared = self._prepare_media_reference("audio", value)
                content.append(
                    {
                        "type": "audio_url",
                        "audio_url": {"url": prepared},
                        "role": "reference_audio",
                    }
                )

        payload: dict[str, Any] = {
            "model": params["model_id"],
            "content": content,
            "resolution": params["resolution"],
            "ratio": params["ratio"],
            "duration": params["duration"],
            "generate_audio": params["generate_audio"],
            "watermark": params["watermark"],
            "return_last_frame": params["return_last_frame"],
            "execution_expires_after": params["execution_expires_after"],
        }
        if params["model_id"] == SEEDANCE_2_0_MODEL_ID:
            payload["priority"] = params["priority"]
        encoded_payload = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded_payload) > MAX_REQUEST_BYTES:
            raise ValueError(
                "Volcengine Ark request body exceeds the 64 MB limit. "
                "Reduce or externally host reference media."
            )
        return payload

    def _build_broker_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Map the HMB media contract to the FN AI Broker Seedance schema."""
        self._validate_parameters(params)
        payload: dict[str, Any] = {
            "provider": "volcengine_ark",
            "model": params["model_id"],
            "prompt": params["prompt"].strip(),
            "input_mode": params["input_mode"],
            "duration_seconds": params["duration"],
            "quality": params["resolution"],
            "aspect_ratio": params["ratio"],
            "generate_audio": params["generate_audio"],
            "watermark": params["watermark"],
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
        if video_url:
            task["content"] = {"video_url": video_url}
        return task

    def _set_broker_task_outputs(
        self,
        task: dict[str, Any],
        *,
        generation_id: str,
        status: str,
    ) -> None:
        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["generation_status"] = status
        self.parameter_output_values["provider_response"] = {
            "transport": "fn_ai_broker",
            "id": generation_id,
            "status": status,
        }

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
                    else HMBSeedance20VideoGeneration._redact_sensitive(item, secret)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                HMBSeedance20VideoGeneration._redact_sensitive(item, secret)
                for item in value
            ]
        if isinstance(value, tuple):
            return tuple(
                HMBSeedance20VideoGeneration._redact_sensitive(item, secret)
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
    def _get_api_key() -> str:
        try:
            api_key = GriptapeNodes.SecretsManager().get_secret(ARK_API_KEY_SECRET)
        except Exception as exc:
            raise RuntimeError(
                "Could not read ARK_API_KEY from Griptape Secrets. "
                "Open Settings > Secrets and save the Volcengine Ark API key."
            ) from exc
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError(
                "ARK_API_KEY is missing. Add the user-owned Volcengine Ark key "
                "to Griptape Settings > Secrets before running this node."
            )
        return api_key.strip()

    @staticmethod
    def _provider_error_detail(
        status_code: int, response_json: dict[str, Any] | None, fallback: str
    ) -> str:
        if response_json:
            error = response_json.get("error")
            if isinstance(error, dict):
                code = error.get("code") or error.get("type")
                message = error.get("message") or error.get("detail")
                if code and message:
                    return f"HTTP {status_code} {code}: {message}"
                if message:
                    return f"HTTP {status_code}: {message}"
            if isinstance(error, str) and error:
                return f"HTTP {status_code}: {error}"
            message = response_json.get("message")
            if isinstance(message, str) and message:
                return f"HTTP {status_code}: {message}"
        return f"HTTP {status_code}: {fallback[:500]}"

    @staticmethod
    def _network_error_phase(exc: BaseException) -> str:
        if isinstance(exc, httpx.ProxyError):
            return "proxy"
        if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError)):
            return "connection"
        if isinstance(exc, httpx.PoolTimeout):
            return "connection-pool"
        if isinstance(exc, (httpx.WriteTimeout, httpx.WriteError)):
            return "request-send"
        if isinstance(
            exc,
            (
                httpx.ReadTimeout,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.DecodingError,
                httpx.TooManyRedirects,
            ),
        ):
            return "response-receive"
        return "transport"

    @staticmethod
    def _submission_diagnostic(
        *,
        error_type: str,
        phase: str,
        attempt_id: str,
        started_at_epoch: int,
    ) -> dict[str, Any]:
        return {
            "submission_outcome": "unknown",
            "network_error_type": error_type,
            "network_phase": phase,
            "local_attempt_id": attempt_id,
            "started_at_epoch": started_at_epoch,
        }

    async def _request_json(
        self,
        method: str,
        path: str,
        api_key: str,
        payload: dict[str, Any] | None = None,
        *,
        retry: bool = False,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        retry_allowed = retry and method in {"GET", "HEAD", "OPTIONS"}
        attempts = 3 if retry_allowed else 1
        url = f"{ARK_BASE_URL}/{path.lstrip('/')}"
        local_attempt_id = uuid4().hex
        started_at_epoch = int(time.time())
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        for attempt in range(attempts):
            if deadline is None:
                operation_timeout = (
                    POST_REQUEST_TIMEOUT_SECONDS if method == "POST" else 120.0
                )
            else:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        "Generation polling deadline expired during a Volcengine request."
                    )
                operation_timeout = min(120.0, remaining)
            timeout = httpx.Timeout(
                operation_timeout,
                connect=min(20.0, operation_timeout),
                pool=min(20.0, operation_timeout),
            )
            if method == "POST" and self.is_cancellation_requested:
                raise asyncio.CancelledError(
                    "Generation was cancelled before the create request started."
                )
            try:
                async with httpx.AsyncClient(
                    timeout=timeout, follow_redirects=False
                ) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        json=payload if method != "GET" else None,
                    )
            except asyncio.CancelledError as exc:
                if method != "POST":
                    raise
                diagnostic = self._submission_diagnostic(
                    error_type="CancelledDuringSubmission",
                    phase="submission",
                    attempt_id=local_attempt_id,
                    started_at_epoch=started_at_epoch,
                )
                raise VolcengineAPIError(
                    "Volcengine task submission was interrupted after it started; "
                    "the outcome is unknown. The POST was attempted once and was not "
                    "retried. Check recent Ark tasks before running again.",
                    response_json={"submission_diagnostic": diagnostic},
                    submission_outcome="unknown",
                ) from exc
            except httpx.RequestError as exc:
                if retry_allowed and attempt + 1 < attempts:
                    delay = min(2**attempt, 5)
                    if deadline is not None:
                        remaining = deadline - self._monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                "Generation polling deadline expired after a network error."
                            ) from exc
                        delay = min(delay, remaining)
                    await self._sleep(delay)
                    continue
                if method == "POST":
                    error_type = type(exc).__name__
                    phase = self._network_error_phase(exc)
                    diagnostic = self._submission_diagnostic(
                        error_type=error_type,
                        phase=phase,
                        attempt_id=local_attempt_id,
                        started_at_epoch=started_at_epoch,
                    )
                    raise VolcengineAPIError(
                        f"Volcengine task submission outcome is unknown: {error_type} "
                        f"during the {phase} phase. The POST was attempted once and "
                        "was not retried. Use Refresh / Retrieve Result to list recent "
                        "candidate tasks before running again.",
                        response_json={"submission_diagnostic": diagnostic},
                        submission_outcome="unknown",
                    ) from exc
                raise VolcengineAPIError(
                    f"Volcengine network request failed ({type(exc).__name__})."
                ) from exc

            response_json: dict[str, Any] | None = None
            try:
                decoded = response.json()
                if isinstance(decoded, dict):
                    response_json = decoded
            except Exception:
                response_json = None

            if response.status_code in RETRYABLE_HTTP_STATUSES and retry_allowed:
                if attempt + 1 < attempts:
                    delay = min(2**attempt, 5)
                    if deadline is not None:
                        remaining = deadline - self._monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                "Generation polling deadline expired after a transient HTTP error."
                            )
                        delay = min(delay, remaining)
                    await self._sleep(delay)
                    continue
            if not response.is_success:
                safe_json = self._redact_sensitive(response_json, api_key)
                safe_text = str(
                    self._redact_sensitive(response.text[:500], api_key)
                )
                detail = self._provider_error_detail(
                    response.status_code,
                    safe_json if isinstance(safe_json, dict) else None,
                    safe_text,
                )
                submission_outcome = None
                if method == "POST":
                    submission_outcome = (
                        "rejected" if response.status_code < 500 else "unknown"
                    )
                    if submission_outcome == "unknown":
                        detail += (
                            " Submission outcome is unknown; do not run another POST "
                            "until recent Ark tasks have been checked."
                        )
                        diagnostic = self._submission_diagnostic(
                            error_type=f"HTTP{response.status_code}",
                            phase="response",
                            attempt_id=local_attempt_id,
                            started_at_epoch=started_at_epoch,
                        )
                        safe_response = (
                            dict(safe_json) if isinstance(safe_json, dict) else {}
                        )
                        safe_response["submission_diagnostic"] = diagnostic
                        safe_json = safe_response
                raise VolcengineAPIError(
                    detail,
                    status_code=response.status_code,
                    response_json=(
                        safe_json if isinstance(safe_json, dict) else None
                    ),
                    submission_outcome=submission_outcome,
                )
            if response_json is None:
                submission_outcome = "unknown" if method == "POST" else None
                message = (
                    "Volcengine returned a successful HTTP response without a JSON "
                    "object."
                )
                if method == "POST":
                    message += (
                        " The submission outcome is unknown; do not run another "
                        "POST until recent Ark tasks have been checked."
                    )
                response_diagnostic = None
                if method == "POST":
                    response_diagnostic = {
                        "submission_diagnostic": self._submission_diagnostic(
                            error_type="InvalidJSONResponse",
                            phase="response-decode",
                            attempt_id=local_attempt_id,
                            started_at_epoch=started_at_epoch,
                        )
                    }
                raise VolcengineAPIError(
                    message,
                    response_json=response_diagnostic,
                    submission_outcome=submission_outcome,
                )
            return response_json

        raise VolcengineAPIError("Volcengine request exhausted its retry limit.")

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
                # The signed result URL is intentionally downloaded without Ark
                # Authorization; forwarding the API key to object storage is unsafe.
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
            if len(video_bytes) < 12 or video_bytes[4:8] != b"ftyp":
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

    @staticmethod
    def _extract_task_failure(task: dict[str, Any], status: str) -> str:
        error = task.get("error")
        if isinstance(error, dict):
            code = error.get("code") or error.get("type")
            message = error.get("message") or error.get("detail")
            if code and message:
                return f"Volcengine task {status}: {code} - {message}"
            if message:
                return f"Volcengine task {status}: {message}"
        if isinstance(error, str) and error:
            return f"Volcengine task {status}: {error}"
        return f"Volcengine task ended with status {status}."

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["generation_status"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
        self.parameter_output_values["VIDEO_OUT"] = None
        self.parameter_output_values["last_frame_url"] = ""

    def _set_task_outputs(
        self,
        task: dict[str, Any],
        *,
        api_key: str,
        generation_id: str,
        status: str,
    ) -> None:
        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["generation_status"] = status
        self.parameter_output_values["provider_response"] = self._redact_sensitive(
            task, api_key
        )

    @staticmethod
    def _validate_task_id(value: Any) -> str:
        task_id = str(value or "").strip()
        if not task_id:
            raise VolcengineAPIError(
                "Generation task ID is missing."
            )
        if _TASK_ID_PATTERN.fullmatch(task_id) is None:
            raise VolcengineAPIError(
                "Generation task ID is invalid; polling was not attempted."
            )
        return task_id

    def _monotonic(self) -> float:
        return time.monotonic()

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def _save_completed_task(
        self, final_task: dict[str, Any], generation_id: str, destination: Any
    ) -> None:
        video_download_url = self._extract_video_url(final_task)
        if not video_download_url:
            raise RuntimeError(
                "FN AI Broker task succeeded but the video URL was missing."
            )
        video_bytes = await self._download_broker_video(video_download_url)
        saved = await destination.awrite_bytes(video_bytes)
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

    @staticmethod
    def _preflight_output_destination(destination: Any) -> None:
        """Validate an output target without rejecting engine-assigned versions.

        Some team project templates require ``{_index}`` in their output macro.
        The Griptape write path assigns that version immediately before writing,
        so an earlier plain ``resolve()`` cannot supply it.  Ignore only that
        single expected preflight failure; every other destination error still
        fails before a task can be submitted.
        """
        try:
            destination.resolve()
        except Exception as exc:
            marker = "missing required variables:"
            details = str(exc)
            if marker not in details:
                raise
            missing = {
                name.strip()
                for name in details.rsplit(marker, 1)[1].split(",")
                if name.strip()
            }
            if missing != {"_index"}:
                raise
            logger.debug(
                "Output preflight deferred because the project assigns {_index} "
                "when the completed video is written."
            )

    @staticmethod
    def _task_items(response: dict[str, Any]) -> list[dict[str, Any]]:
        items = response.get("items")
        if not isinstance(items, list):
            data = response.get("data")
            if isinstance(data, dict):
                items = data.get("items")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    async def _list_ambiguous_submission_candidates(
        self, api_key: str, diagnostic: dict[str, Any]
    ) -> None:
        response = await self._request_json(
            "GET",
            f"{CREATE_TASK_PATH}?page_num=1&page_size=100",
            api_key,
            retry=True,
        )
        started_at = int(diagnostic.get("started_at_epoch") or 0)
        expected_model = str(diagnostic.get("model") or "").strip()
        candidates: list[dict[str, Any]] = []
        for item in self._task_items(response):
            task_id = str(item.get("id") or "").strip()
            model = str(item.get("model") or "").strip()
            status = str(item.get("status") or "unknown").strip().lower()
            try:
                created_at = int(item.get("created_at") or 0)
            except (TypeError, ValueError):
                created_at = 0
            if not task_id or _TASK_ID_PATTERN.fullmatch(task_id) is None:
                continue
            if expected_model and model and model != expected_model:
                continue
            if started_at and created_at:
                if created_at < started_at - 120 or created_at > started_at + 900:
                    continue
            candidates.append(
                {
                    "id": task_id,
                    "status": status,
                    "model": model or expected_model,
                    "created_at": created_at,
                }
            )
            if len(candidates) >= 5:
                break

        if not candidates:
            self._set_status_results(
                was_successful=False,
                result_details=(
                    "No matching recent Ark task was found for the ambiguous "
                    "submission. This does not prove that no task was accepted. "
                    "Check the Ark task list again before creating another task."
                ),
            )
            return
        lines = [
            f"- {item['id']} | {item['status']} | created_at={item['created_at']}"
            for item in candidates
        ]
        self._set_status_results(
            was_successful=False,
            result_details=(
                "Possible Ark tasks for the ambiguous submission:\n"
                + "\n".join(lines)
                + "\nConfirm the correct task, then copy its ID into Resume Task ID. "
                "The node will not choose or submit automatically."
            ),
        )

    async def _refresh_direct_async(self) -> None:
        try:
            api_key = self._get_api_key()
            generation_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            if not generation_id:
                provider_response = self.parameter_output_values.get(
                    "provider_response"
                )
                diagnostic = (
                    provider_response.get("submission_diagnostic")
                    if isinstance(provider_response, dict)
                    else None
                )
                if (
                    self.parameter_output_values.get("generation_status")
                    == "submission_unknown"
                    and isinstance(diagnostic, dict)
                ):
                    await self._list_ambiguous_submission_candidates(
                        api_key, diagnostic
                    )
                    return
                self._set_status_results(
                    was_successful=False,
                    result_details=(
                        "No Volcengine task ID is available. Run the node once or put "
                        "a confirmed task ID into Resume Task ID."
                    ),
                )
                return

            generation_id = self._validate_task_id(generation_id)
            if not self._usage_context:
                self._prepare_usage_tracking(
                    self._get_parameters(), existing_task=True
                )
            task = await self._request_json(
                "GET",
                f"{CREATE_TASK_PATH}/{quote(generation_id, safe='')}",
                api_key,
                retry=True,
            )
            status = str(task.get("status") or "").strip().lower()
            if not status:
                raise VolcengineAPIError(
                    "Volcengine task response did not include a status."
                )
            self._set_task_outputs(
                task,
                api_key=api_key,
                generation_id=generation_id,
                status=status,
            )
            if status == "succeeded":
                self._record_usage_task(task, generation_id, status)
                destination = self._output_file.build_file()
                self._preflight_output_destination(destination)
                await self._save_completed_task(task, generation_id, destination)
                return
            if status in TERMINAL_FAILURE_STATUSES:
                self._record_usage_task(task, generation_id, status)
                safe_task = self._redact_sensitive(task, api_key)
                detail = self._extract_task_failure(
                    safe_task if isinstance(safe_task, dict) else {}, status
                )
                self._set_status_results(
                    was_successful=False,
                    result_details=detail,
                )
                return
            self._set_status_results(
                was_successful=False,
                result_details=(
                    f"Volcengine task {generation_id} is still {status}. "
                    "Click Refresh / Retrieve Result again later."
                ),
            )
        except Exception as exc:
            self._set_status_results(
                was_successful=False,
                result_details=(
                    "Refresh failed safely without creating a task: "
                    + self._safe_exception_message(exc)
                ),
            )

    async def _refresh_async(self) -> None:
        """Refresh one Broker job without ever creating a replacement task."""
        try:
            bridge = await self._ensure_broker_connected()
            generation_id = str(
                self.parameter_output_values.get("generation_id")
                or self.get_parameter_value("resume_generation_id")
                or ""
            ).strip()
            if not generation_id:
                self._set_status_results(
                    was_successful=False,
                    result_details=(
                        "No FN AI Broker task ID is available. Run the node once or "
                        "put a confirmed task ID into Resume Task ID."
                    ),
                )
                return
            generation_id = self._validate_task_id(generation_id)
            response = await asyncio.to_thread(
                bridge.refresh_job,
                generation_id,
                timeout=60,
            )
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
                    result_details=(
                        f"FN AI Broker task {generation_id} ended with status {status}."
                    ),
                )
                return
            self._set_status_results(
                was_successful=False,
                result_details=(
                    f"FN AI Broker task {generation_id} is still {status}. "
                    "Click Refresh / Retrieve Result again later."
                ),
            )
        except Exception as exc:
            safe_detail = (
                str(exc) if isinstance(exc, _BrokerError) else type(exc).__name__
            )
            self._set_status_results(
                was_successful=False,
                result_details=(
                    "Broker refresh failed safely without creating a task: "
                    + safe_detail
                ),
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

        # Resolve the save target before the billable Broker POST.
        destination = self._output_file.build_file()
        self._preflight_output_destination(destination)
        # Usage is intentionally not collected or displayed for Broker renders.
        self._usage_context = {}
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
            try:
                response = await asyncio.to_thread(
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
                        "status": "submission_unknown",
                    }
                raise
            task = self._normalize_broker_task(response)
            generation_id = str(task["id"])
            status = str(task["status"])
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
                    f"FN AI Broker task ended with status {status}."
                )

        while final_task is None:
            if self.is_cancellation_requested:
                self.parameter_output_values["generation_status"] = "cancelled_locally"
                raise asyncio.CancelledError(
                    "Local Broker polling was cancelled. The remote task may continue."
                )
            now = self._monotonic()
            if now >= deadline:
                self.parameter_output_values["generation_status"] = "timed_out"
                raise TimeoutError(
                    f"FN AI Broker task {generation_id} did not finish within "
                    f"{timeout} seconds. Put this ID into Resume Task ID to continue "
                    "without creating another billed task."
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
                    f"FN AI Broker task ended with status {status}."
                )
            remaining = deadline - self._monotonic()
            if remaining > 0:
                await self._sleep(min(poll_interval, remaining))

        await self._save_completed_task(final_task, generation_id, destination)

    async def _process_direct_generation_impl(self) -> None:
        """Legacy direct-Ark implementation retained only for regression isolation."""
        self._set_safe_defaults()
        params = self._get_parameters()
        self._validate_parameters(params)
        resume_generation_id = params["resume_generation_id"]

        # Resolve the save target before the billable POST. This catches missing
        # project/macro configuration without creating or overwriting a file.
        # A required {_index} is deferred to the engine's collision-safe write.
        destination = self._output_file.build_file()
        self._preflight_output_destination(destination)

        self._prepare_usage_tracking(
            params, existing_task=bool(resume_generation_id)
        )

        api_key = self._get_api_key()
        if resume_generation_id:
            payload = None
        else:
            params = self._prepare_video_references_for_run(params)
            payload = self._build_payload(params)
        if resume_generation_id:
            generation_id = self._validate_task_id(resume_generation_id)
            self._set_task_outputs(
                {"id": generation_id, "status": "resuming"},
                api_key=api_key,
                generation_id=generation_id,
                status="resuming",
            )
            logger.info("%s resuming Volcengine task %s", self.name, generation_id)
        else:
            try:
                create_response = await self._request_json(
                    "POST",
                    CREATE_TASK_PATH,
                    api_key,
                    payload,
                    retry=False,
                )
            except VolcengineAPIError as exc:
                if exc.submission_outcome == "unknown":
                    self._submission_outcome_unknown = True
                    diagnostic_source = exc.response_json or {}
                    diagnostic = diagnostic_source.get("submission_diagnostic")
                    if isinstance(diagnostic, dict):
                        diagnostic["model"] = params["model_id"]
                raise
            safe_create_response = self._redact_sensitive(create_response, api_key)
            self.parameter_output_values["provider_response"] = safe_create_response
            self.parameter_output_values["generation_status"] = (
                "submission_response_received"
            )
            try:
                generation_id = self._validate_task_id(create_response.get("id"))
            except VolcengineAPIError as exc:
                self._submission_outcome_unknown = True
                unknown_response = (
                    dict(safe_create_response)
                    if isinstance(safe_create_response, dict)
                    else {}
                )
                diagnostic = self._submission_diagnostic(
                    error_type="InvalidTaskIdResponse",
                    phase="response-validation",
                    attempt_id=uuid4().hex,
                    started_at_epoch=int(time.time()),
                )
                diagnostic["model"] = params["model_id"]
                unknown_response["submission_diagnostic"] = diagnostic
                raise VolcengineAPIError(
                    "Volcengine accepted the create request but did not return a valid "
                    "task ID. The submission outcome is unknown; check recent Ark tasks "
                    "before running again.",
                    response_json=unknown_response,
                    submission_outcome="unknown",
                ) from exc
            initial_status = str(create_response.get("status") or "queued").lower()
            self._set_task_outputs(
                create_response,
                api_key=api_key,
                generation_id=generation_id,
                status=initial_status,
            )
            self._record_usage_task(
                create_response, generation_id, initial_status
            )
            logger.info(
                "%s submitted Volcengine model %s as task %s",
                self.name,
                params["model_id"],
                generation_id,
            )

        poll_path = f"{CREATE_TASK_PATH}/{quote(generation_id, safe='')}"
        started = self._monotonic()
        timeout = params["generation_timeout_seconds"]
        deadline = started + timeout
        poll_interval = params["poll_interval_seconds"]
        final_task: dict[str, Any] | None = None

        while True:
            if self.is_cancellation_requested:
                self.parameter_output_values["generation_status"] = "cancelled_locally"
                raise asyncio.CancelledError(
                    "Local polling was cancelled. The provider task may continue."
                )
            now = self._monotonic()
            if now >= deadline:
                self.parameter_output_values["generation_status"] = "timed_out"
                raise TimeoutError(
                    f"Volcengine task {generation_id} did not finish within {timeout} seconds. "
                    "The provider task may still be running. Put this ID into "
                    "Resume Task ID to continue without creating another billed task."
                )

            task = await self._request_json(
                "GET", poll_path, api_key, retry=True, deadline=deadline
            )
            status = str(task.get("status") or "").strip().lower()
            if not status:
                raise VolcengineAPIError(
                    "Volcengine task response did not include a status."
                )
            self._set_task_outputs(
                task,
                api_key=api_key,
                generation_id=generation_id,
                status=status,
            )
            logger.info("%s Volcengine task %s status: %s", self.name, generation_id, status)

            if status == "succeeded":
                self._record_usage_task(task, generation_id, status)
                final_task = task
                break
            if status in TERMINAL_FAILURE_STATUSES:
                self._record_usage_task(task, generation_id, status)
                safe_task = self._redact_sensitive(task, api_key)
                raise RuntimeError(
                    self._extract_task_failure(
                        safe_task if isinstance(safe_task, dict) else {}, status
                    )
                )
            if status not in ACTIVE_STATUSES:
                raise RuntimeError(
                    f"Volcengine returned unknown task status {status!r}; stopped safely."
                )
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                continue
            await self._sleep(min(poll_interval, remaining))

        await self._save_completed_task(final_task, generation_id, destination)

    async def aprocess(self) -> None:
        self._clear_execution_status()
        try:
            await self._process_generation()
        except asyncio.CancelledError:
            generation_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            resume_guidance = (
                f" Use Resume Task ID {generation_id} to continue without a new POST."
                if generation_id
                else ""
            )
            self._set_status_results(
                was_successful=False,
                result_details=(
                    (
                        "CANCELLED: Local Seedance polling stopped. The FN AI Broker "
                        "task may continue remotely and may still incur charges."
                        if generation_id
                        else "CANCELLED: Generation stopped before a task ID was received."
                    )
                    + resume_guidance
                ),
            )
            self._record_current_usage_status("cancelled_locally")
            raise
        except Exception as exc:
            safe_message = self._safe_exception_message(exc)
            generation_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            if generation_id:
                safe_message += (
                    f"\nExisting task ID: {generation_id}. Set Resume Task ID to this "
                    "value before rerunning so the node does not create a duplicate task."
                )
            submission_unknown = (
                isinstance(exc, VolcengineAPIError)
                and exc.submission_outcome == "unknown"
            ) or (
                isinstance(exc, _BrokerError)
                and exc.submission_outcome_unknown
            )
            if submission_unknown:
                self.parameter_output_values["generation_status"] = (
                    "submission_unknown"
                )
                safe_message += (
                    "\nTemporary local video uploads are being retained for up to "
                    "30 minutes so an accepted remote task can still fetch them."
                )
            elif not self.parameter_output_values.get("generation_status"):
                self.parameter_output_values["generation_status"] = "failed"
            if isinstance(exc, VolcengineAPIError) and exc.response_json:
                self.parameter_output_values["provider_response"] = exc.response_json
            self._set_status_results(
                was_successful=False,
                result_details=f"FAILURE: {safe_message}",
            )
            self._record_current_usage_status()
            self._handle_failure_exception(RuntimeError(safe_message))
__all__ = [
    "ARK_API_KEY_SECRET",
    "GT_CLOUD_API_KEY_SECRET",
    "GT_CLOUD_BUCKET_ID_SECRET",
    "TOS_ACCESS_KEY_ID_SECRET",
    "TOS_SECRET_ACCESS_KEY_SECRET",
    "TOS_BUCKET_NAME_SECRET",
    "HMBSeedance20VideoGeneration",
    "LOCAL_VIDEO_UPLOAD_GRIPTAPE",
    "LOCAL_VIDEO_UPLOAD_TOS",
    "MAX_REFERENCE_IMAGES",
    "MAX_VIDEO_REFERENCES",
    "MAX_REFERENCE_AUDIO",
    "VIDEO_REFERENCES_PARAMETER",
]
