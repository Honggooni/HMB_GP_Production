from __future__ import annotations

import asyncio
import base64
import binascii
import ctypes
import hashlib
import importlib
import inspect
import ipaddress
import io
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
import weakref
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
from griptape.artifacts import ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import (
    GriptapeCloudStorageDriver,
)
try:
    from griptape_nodes.drivers.cloud_credentials import resolve_cloud_credential
except ImportError:  # Older Griptape hosts expose only GT_CLOUD_API_KEY.
    resolve_cloud_credential = None  # type: ignore[assignment]
from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterList,
    ParameterMode,
)

try:
    from griptape_nodes.exe_types.core_types import NodeMessageResult
except ImportError:  # Compatibility for older hosts and lightweight test stubs.
    @dataclass
    class NodeMessageResult:  # type: ignore[no-redef]
        success: bool
        details: str
        response: Any = None
        altered_workflow_state: bool = True

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
from griptape_nodes.files.project_file import ProjectFileDestination
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import MacroPath
from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import write_sidecar
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

try:
    from griptape_nodes.traits.widget import Widget
except Exception:  # Older Griptape Nodes builds keep the legacy selector alive.
    Widget = None  # type: ignore[assignment]

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
import _hmb_shot_routing as _shot_routing
from _hmb_common import (
    _broker_load_bearer_token_readonly,
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
# Five Shot generators prepare and later poll independently.  Only their
# billable Broker POST starts are paced because the production Broker rejects
# same-account creates that arrive less than one second apart.  The lock is
# released before network I/O, so accepted remote renders continue together.
AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 1.20
_BROKER_SUBMISSION_CADENCE_LOCK = threading.Lock()
_BROKER_SUBMISSION_LAST_STARTED = 0.0
_WORKFLOW_CHECKPOINT_LOCKS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Lock
] = weakref.WeakKeyDictionary()
_WORKFLOW_CHECKPOINT_LOCKS_GUARD = threading.Lock()

LOCAL_VIDEO_UPLOAD_GRIPTAPE = "Griptape Cloud (Existing)"
LOCAL_VIDEO_UPLOAD_TOS = "Volcengine TOS"
LOCAL_VIDEO_UPLOAD_SERVICES = (
    LOCAL_VIDEO_UPLOAD_GRIPTAPE,
    LOCAL_VIDEO_UPLOAD_TOS,
)
DEFAULT_TOS_REGION = "cn-beijing"
DEFAULT_TOS_ENDPOINT = "tos-cn-beijing.volces.com"


def _is_structurally_valid_mp4(value: bytes | bytearray) -> bool:
    """Require a complete ISO-BMFF video container before publication.

    Both MP4 and QuickTime MOV use the same top-level ``ftyp``/``moov``/``mdat``
    structure.  The requested container brand is checked separately at the
    final publication boundary.
    """

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


def _iso_bmff_brands(value: bytes | bytearray) -> tuple[bytes, ...]:
    """Return the bounded ``ftyp`` major/compatible brands for a valid file."""

    data = bytes(value)
    if not _is_structurally_valid_mp4(data) or len(data) < 24:
        return ()
    size = int.from_bytes(data[0:4], "big")
    header_size = 16 if size == 1 else 8
    if size == 1:
        size = int.from_bytes(data[8:16], "big")
    elif size == 0:
        size = len(data)
    if size < header_size + 8 or size > len(data):
        return ()
    payload = data[header_size:size]
    major = payload[0:4]
    compatibles = tuple(
        payload[index : index + 4]
        for index in range(8, len(payload), 4)
        if len(payload[index : index + 4]) == 4
    )
    return (major, *compatibles)


def _video_container_matches_format(
    value: bytes | bytearray,
    output_format: str,
) -> bool:
    """Refuse MP4/MOV extension spoofing at the final local-save boundary."""

    brands = _iso_bmff_brands(value)
    if not brands:
        return False
    requested = str(output_format or "").strip().lower()
    has_quicktime_brand = b"qt  " in brands
    if requested == "mov":
        return has_quicktime_brand
    if requested == "mp4":
        return not has_quicktime_brand
    return False


def _is_valid_png(value: bytes | bytearray) -> bool:
    """Validate a bounded PNG payload before it can become a local artifact."""

    data = bytes(value)
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    try:
        from io import BytesIO

        from PIL import Image, UnidentifiedImageError

        with Image.open(BytesIO(data)) as opened:
            if str(opened.format or "").upper() != "PNG":
                return False
            width, height = opened.size
            if width <= 0 or height <= 0 or width * height > 100_000_000:
                return False
            opened.verify()
    except (OSError, ValueError, UnidentifiedImageError):
        return False
    return True


DEFAULT_TOS_URL_VALIDITY_SECONDS = 24 * 60 * 60
MIN_TOS_URL_VALIDITY_SECONDS = 60 * 60
MAX_TOS_URL_VALIDITY_SECONDS = 30 * 24 * 60 * 60
TOS_TEMP_OBJECT_PREFIX = "hmb-seedance-temp"

INPUT_MODE_TEXT_ONLY = "Text Only"
INPUT_MODE_FIRST_LAST_FRAME = "First/Last Frame"
INPUT_MODE_MULTIMODAL_REFERENCES = "Multimodal References"

OUTPUT_FORMAT_CHOICES = ("mp4", "mov")
DEFAULT_OUTPUT_FORMAT = "mp4"
LAST_FRAME_FILENAME = "seedance_2_5_last_frame.png"
_AUTO_VIDEO_OUTPUT_NAME_PATTERN = re.compile(
    r"^volcengine_seedance_video(?:_shot_0[1-5])?\.(?:mp4|mov)$",
    re.IGNORECASE,
)
_AUTO_LAST_FRAME_NAME_PATTERN = re.compile(
    r"^seedance_2_5_last_frame(?:_shot_0[1-5])?\.png$",
    re.IGNORECASE,
)

# ``Task`` is the authored Seedance operation. ``input_mode`` remains a hidden
# compatibility field for workflows saved before Task existed and is derived
# from this value before validation/submission.
TASK_PARAMETER = "task"
TASK_TEXT_ONLY = "Text Only"
TASK_FIRST_LAST_FRAME = "First/Last Frame"
TASK_REFERENCE_TO_VIDEO = "Reference to Video"
TASK_VIDEO_EDITING = "Video Editing"
TASK_VIDEO_EXTENSION = "Video Extension"
TASK_STORAGE_CHOICES = (
    TASK_TEXT_ONLY,
    TASK_FIRST_LAST_FRAME,
    TASK_REFERENCE_TO_VIDEO,
    TASK_VIDEO_EDITING,
    TASK_VIDEO_EXTENSION,
)
TASK_INPUT_MODES = {
    TASK_TEXT_ONLY: INPUT_MODE_TEXT_ONLY,
    TASK_FIRST_LAST_FRAME: INPUT_MODE_FIRST_LAST_FRAME,
    TASK_REFERENCE_TO_VIDEO: INPUT_MODE_MULTIMODAL_REFERENCES,
    TASK_VIDEO_EDITING: INPUT_MODE_MULTIMODAL_REFERENCES,
    TASK_VIDEO_EXTENSION: INPUT_MODE_MULTIMODAL_REFERENCES,
}
TASK_BROKER_SLUGS = {
    TASK_TEXT_ONLY: "text_to_video",
    TASK_FIRST_LAST_FRAME: "first_last_frame",
    TASK_REFERENCE_TO_VIDEO: "reference_to_video",
    TASK_VIDEO_EDITING: "video_editing",
    TASK_VIDEO_EXTENSION: "video_extension",
}
TASK_OMNI_REFERENCE_TYPES = {
    TASK_REFERENCE_TO_VIDEO: "reference",
    TASK_VIDEO_EDITING: "edit",
    TASK_VIDEO_EXTENSION: "extend",
}
BROKER_SEEDANCE_CAPABILITIES_PATH = "/api/v1/generate/video/capabilities"
BROKER_SEEDANCE_CAPABILITIES_SCHEMA = "hmb-seedance-generation-capabilities"
BROKER_SEEDANCE_CAPABILITIES_VERSION = 2
INPUT_MODE_TASKS = {
    INPUT_MODE_TEXT_ONLY: TASK_TEXT_ONLY,
    INPUT_MODE_FIRST_LAST_FRAME: TASK_FIRST_LAST_FRAME,
    INPUT_MODE_MULTIMODAL_REFERENCES: TASK_REFERENCE_TO_VIDEO,
}

MODEL_NAME_SEEDANCE_2_0 = "Seedance 2.0"
MODEL_NAME_SEEDANCE_2_0_FAST = "Seedance 2.0 Fast"
MODEL_NAME_SEEDANCE_2_5 = "Seedance 2.5"

SEEDANCE_2_0_MODEL_ID = "doubao-seedance-2-0-260128"
SEEDANCE_2_0_FAST_MODEL_ID = "doubao-seedance-2-0-fast-260128"
SEEDANCE_2_5_MODEL_ID = "doubao-seedance-2-5-260628"

MODEL_TASK_CHOICES = {
    SEEDANCE_2_0_MODEL_ID: TASK_STORAGE_CHOICES[:3],
    SEEDANCE_2_0_FAST_MODEL_ID: TASK_STORAGE_CHOICES[:3],
    SEEDANCE_2_5_MODEL_ID: TASK_STORAGE_CHOICES,
}

# Keep the exact HMB client-approved Volcengine IDs explicit so an arbitrary
# catalog entry can never be submitted merely because its name contains
# "seedance".  The corresponding BytePlus ``dreamina-*`` IDs below are saved-
# workflow aliases only; HMB's China-region route submits ``doubao-*`` IDs and
# the Broker independently authorizes every model server-side.
BROKER_SUPPORTED_MODEL_IDS = frozenset(
    {
        SEEDANCE_2_0_MODEL_ID,
        SEEDANCE_2_0_FAST_MODEL_ID,
        SEEDANCE_2_5_MODEL_ID,
    }
)

# Mini is retired by the Broker. These exact historical serialized values are
# recognized solely to migrate an old workflow once to the active full-model
# default. They are never members of an active allowlist or request schema.
RETIRED_SEEDANCE_MODEL_VALUES = frozenset(
    {
        "Seedance 2.0 Mini",
        "dreamina-seedance-2-0-mini-260615",
        "doubao-seedance-2-0-mini-260615",
    }
)

# Old active display and BytePlus values remain accepted so saved workflows
# migrate without silently submitting an obsolete provider model id. Retired
# Mini values canonicalize to the current safe default before validation.
MODEL_ID_ALIASES = {
    MODEL_NAME_SEEDANCE_2_0: SEEDANCE_2_0_MODEL_ID,
    MODEL_NAME_SEEDANCE_2_0_FAST: SEEDANCE_2_0_FAST_MODEL_ID,
    MODEL_NAME_SEEDANCE_2_5: SEEDANCE_2_5_MODEL_ID,
    "dreamina-seedance-2-0-260128": SEEDANCE_2_0_MODEL_ID,
    "dreamina-seedance-2-0-fast-260128": SEEDANCE_2_0_FAST_MODEL_ID,
    "dreamina-seedance-2-5-260628": SEEDANCE_2_5_MODEL_ID,
    SEEDANCE_2_0_MODEL_ID: SEEDANCE_2_0_MODEL_ID,
    SEEDANCE_2_0_FAST_MODEL_ID: SEEDANCE_2_0_FAST_MODEL_ID,
    SEEDANCE_2_5_MODEL_ID: SEEDANCE_2_5_MODEL_ID,
    **{
        retired: SEEDANCE_2_0_MODEL_ID
        for retired in RETIRED_SEEDANCE_MODEL_VALUES
    },
}
MODEL_DISPLAY_NAME_BY_ID = {
    SEEDANCE_2_0_MODEL_ID: MODEL_NAME_SEEDANCE_2_0,
    SEEDANCE_2_0_FAST_MODEL_ID: MODEL_NAME_SEEDANCE_2_0_FAST,
    SEEDANCE_2_5_MODEL_ID: MODEL_NAME_SEEDANCE_2_5,
}

MODEL_RESOLUTIONS = {
    SEEDANCE_2_0_MODEL_ID: ("4k", "1080p", "720p", "480p"),
    SEEDANCE_2_0_FAST_MODEL_ID: ("720p", "480p"),
    # Seedance 2.5 production contract: 720p default and optional 1080p
    # (10-bit HEVC).  480p is intentionally not exposed.
    SEEDANCE_2_5_MODEL_ID: ("720p", "1080p"),
}

MODEL_DEFAULT_RESOLUTIONS = {
    SEEDANCE_2_0_MODEL_ID: "1080p",
    SEEDANCE_2_0_FAST_MODEL_ID: "720p",
    SEEDANCE_2_5_MODEL_ID: "720p",
}

MODEL_DURATION_CHOICES = {
    SEEDANCE_2_0_MODEL_ID: (-1, *range(4, 16)),
    SEEDANCE_2_0_FAST_MODEL_ID: (-1, *range(4, 16)),
    # The 2.5 Broker contract is literal 4–30 seconds; smart-duration (-1)
    # is not sent for this model.
    SEEDANCE_2_5_MODEL_ID: (*range(4, 31),),
}

# The converter-facing set is the union of every active model. It is wider
# than any one visible dropdown so host delivery order cannot coerce a saved
# 2.0 smart duration or a 2.5 long duration before model_id is known.
DURATION_STORAGE_CHOICES = (-1, *range(4, 31))

MODEL_REFERENCE_LIMITS = {
    SEEDANCE_2_0_MODEL_ID: (9, 3, 3),
    SEEDANCE_2_0_FAST_MODEL_ID: (9, 3, 3),
    SEEDANCE_2_5_MODEL_ID: (30, 10, 10),
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

# Local preparation states are intentionally distinct from server task states.
# They provide immediate feedback while disk/network preparation runs off the
# event loop and are converted to ``failed`` if execution stops before POST.
LOCAL_PRE_SUBMISSION_STATUSES = frozenset(
    {
        "resolving_inputs",
        "preparing_output",
        "connecting_broker",
        "preparing_media",
    }
)

# Absolute library bounds match Seedance 2.5.  Older models keep their lower
# limits in ``MODEL_REFERENCE_LIMITS`` and fail before any Broker submission.
MAX_REFERENCE_IMAGES = 30
MAX_VIDEO_REFERENCES = 10
MAX_REFERENCE_AUDIO = 10
LEGACY_VIDEO_REFERENCE_SLOTS = 3
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
MAX_LAST_FRAME_BYTES = 64 * 1024 * 1024
MEDIA_BASE64_READ_CHUNK_BYTES = 3 * 256 * 1024
CLOUD_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
MAX_ATOMIC_OUTPUT_CANDIDATES = 10_000
AMBIGUOUS_UPLOAD_CLEANUP_DELAY_SECONDS = 30 * 60
_CLOUD_DRIVER_UNSET = object()

VIDEO_REFERENCES_PARAMETER = "VIDEO_REFERENCES"
SHOT_PROMPT_INPUT_PARAMETER = "SHOT_PROMPT_IN"
SHOT_IMAGE_INPUT_PARAMETER = "SHOT_IMAGE_IN"
SHOT_VIDEO_INPUT_PARAMETER = "SHOT_VIDEO_IN"
SHOT_ASSET_INPUT_PARAMETER = "SHOT_ASSET_IN"
SHOT_PICKER_INPUT_PARAMETER = "SHOT_PICKER_IN"
SHOT_PICKER_LEGACY_JSON_MAX_BYTES = 1024 * 1024
SHOT_AUTOCLAIM_ENABLED_PARAMETER = "HMB_SHOT_AUTOCLAIM_ENABLED"
SHOT_SELECTOR_PARAMETER = "shot_selector"
SEEDANCE_SHOT_WIDGET_PARAMETER = "HMB_SEEDANCE_SHOT_UI"
SEEDANCE_SHOT_WIDGET_NAME = "HMBSeedanceGenerationWidget"
SEEDANCE_SHOT_WIDGET_LIBRARY_NAME = "HMB_GP_Production"
SEEDANCE_SHOT_WIDGET_HEIGHT = 64
SEEDANCE_REFRESH_COMMAND_PARAMETER = "HMB_SEEDANCE_REFRESH_COMMAND"
SEEDANCE_REFRESH_COMMAND_SCHEMA = "hmb-seedance-refresh-command"
SEEDANCE_REFRESH_COMMAND_VERSION = 1
SEEDANCE_RECOVERY_PARAMETER = "HMB_SEEDANCE_RECOVERY"
SEEDANCE_RECOVERY_SCHEMA = "hmb-seedance-generation-recovery"
SEEDANCE_RECOVERY_VERSION = 1
SEEDANCE_RECOVERY_STAGES = frozenset(
    {
        "",
        "pre_submit",
        "accepted",
        "resume",
        "submission_unknown",
        "cancelled_locally",
        "timed_out",
        "terminal",
        "remote_succeeded",
        "local_succeeded",
        "refresh",
    }
)
SHOT_CHANNEL_UUID_PARAMETER = "shot_channel_uuid"
SHOT_UUID_PARAMETER = "shot_uuid"
SHOT_NUMBER_PARAMETER = "shot_number"
SHOT_NAME_PARAMETER = "shot_name"
SHOT_ROUTING_MAX_SHOTS = 5
SHOT_CONNECTION_PENDING_LABEL = "Shot connection pending"
# Compatibility export for tests and saved integrations that imported the old
# constant name.  It remains a diagnostic label; the visible independent mode
# is the ordinary prompt-only ``Only`` choice.
SHOT_REMOTE_WAITING_LABEL = SHOT_CONNECTION_PENDING_LABEL
SHOT_ONLY_LABEL = "Only"
SHOT_UNAVAILABLE_LABEL = SHOT_ONLY_LABEL

GENERATION_PREVIEW_SCHEMA = "hmb-seedance-generation-preview"
GENERATION_PREVIEW_VERSION = 1
GENERATION_PREVIEW_PHASES = frozenset(
    {
        "idle",
        "preparing",
        "submitting",
        "queued",
        "running",
        "retrieving",
        "downloading",
        "verifying",
        "cancelled_locally",
        "timed_out",
        "submission_unknown",
        "failed",
        "succeeded",
    }
)
GENERATION_PREVIEW_REFRESH_PHASES = frozenset(
    {
        "queued",
        "running",
        "cancelled_locally",
        "timed_out",
        "submission_unknown",
        "failed",
    }
)
GENERATION_PREVIEW_GUIDANCE = {
    "idle": "",
    "preparing": "입력과 출력 위치를 확인하고 있습니다.",
    "submitting": "새 작업을 서버에 제출하고 있습니다.",
    "queued": "서버 렌더 대기열에서 순서를 기다리고 있습니다.",
    "running": "서버에서 영상을 생성하고 있습니다.",
    "retrieving": "새 작업을 만들지 않고 기존 작업 결과만 확인하고 있습니다.",
    "downloading": "완료된 영상을 내려받고 있습니다.",
    "verifying": "영상 파일을 검증하고 안전하게 저장하고 있습니다.",
    "cancelled_locally": (
        "서버 렌더는 계속될 수 있습니다. 기존 작업 결과만 확인합니다."
    ),
    "timed_out": (
        "자동 조회 시간이 끝났습니다. 기존 작업 결과만 다시 확인합니다."
    ),
    "submission_unknown": (
        "제출 응답을 확인하지 못했습니다. 새 작업을 만들지 않고 기존 요청만 확인합니다."
    ),
    "failed": "작업 상태 또는 결과 수신을 확인해야 합니다.",
    "succeeded": "",
}


def _seedance_generation_preview_value(value: Any = None) -> dict[str, Any]:
    """Return the bounded, browser-safe runtime preview contract.

    This value deliberately contains no media path, signed URL, provider body,
    or browser-supplied identifier.  The custom widget receives only enough
    state to explain an empty preview and request a same-job refresh.
    """

    source = value if isinstance(value, dict) else {}
    phase = str(source.get("phase") or "idle").strip().lower()
    if phase not in GENERATION_PREVIEW_PHASES:
        phase = "idle"

    job_id = str(source.get("job_id") or "").strip()
    if not job_id or _TASK_ID_PATTERN.fullmatch(job_id) is None:
        job_id = ""

    def bounded_nonnegative_integer(raw: Any, maximum: int) -> int:
        if not isinstance(raw, int) or isinstance(raw, bool):
            return 0
        return min(maximum, max(0, raw))

    started_at_ms = bounded_nonnegative_integer(
        source.get("started_at_ms"),
        9_999_999_999_999,
    )
    elapsed_seconds = bounded_nonnegative_integer(
        source.get("elapsed_seconds"),
        7 * 24 * 60 * 60,
    )
    media_revision = bounded_nonnegative_integer(
        source.get("media_revision"),
        2_147_483_647,
    )
    requested_action = str(source.get("action") or "none").strip().lower()
    action = (
        "refresh_existing"
        if requested_action == "refresh_existing"
        and job_id
        and phase in GENERATION_PREVIEW_REFRESH_PHASES
        else "none"
    )
    return {
        "schema": GENERATION_PREVIEW_SCHEMA,
        "version": GENERATION_PREVIEW_VERSION,
        "phase": phase,
        "job_id": job_id,
        "started_at_ms": started_at_ms,
        "elapsed_seconds": elapsed_seconds,
        "guidance": GENERATION_PREVIEW_GUIDANCE[phase],
        "action": action,
        "has_existing_video": source.get("has_existing_video") is True,
        "media_revision": media_revision,
    }


def _seedance_refresh_command_value(value: Any = None) -> dict[str, Any]:
    """Normalize the one-shot browser command without accepting a task ID."""

    source = value if isinstance(value, dict) else {}
    action = str(source.get("action") or "").strip().lower()
    action_id = str(source.get("action_id") or "").strip()
    if (
        source.get("schema") != SEEDANCE_REFRESH_COMMAND_SCHEMA
        or source.get("version") != SEEDANCE_REFRESH_COMMAND_VERSION
        or action != "refresh_existing"
        or not action_id
        or len(action_id) > 128
        or _TASK_ID_PATTERN.fullmatch(action_id) is None
    ):
        action = ""
        action_id = ""
    issued_at_ms = source.get("issued_at_ms")
    if not isinstance(issued_at_ms, int) or isinstance(issued_at_ms, bool):
        issued_at_ms = 0
    issued_at_ms = min(9_999_999_999_999, max(0, issued_at_ms))
    return {
        "schema": SEEDANCE_REFRESH_COMMAND_SCHEMA,
        "version": SEEDANCE_REFRESH_COMMAND_VERSION,
        "action": action,
        "action_id": action_id,
        "issued_at_ms": issued_at_ms,
    }


def _seedance_recovery_value(value: Any = None) -> dict[str, Any]:
    """Normalize the durable, non-sensitive same-task recovery checkpoint."""

    source = value if isinstance(value, dict) else {}
    task_id = str(source.get("task_id") or "").strip()
    if not task_id or _TASK_ID_PATTERN.fullmatch(task_id) is None:
        task_id = ""
    identity = str(source.get("task_identity") or "").strip().lower()
    if identity not in {"client_request", "broker_task"} or not task_id:
        identity = ""
    status = str(source.get("status") or "").strip().lower().replace("-", "_")
    allowed_statuses = (
        BROKER_ACTIVE_STATUSES
        | BROKER_SUCCESS_STATUSES
        | BROKER_FAILURE_STATUSES
        | BROKER_CANCELLED_STATUSES
        | BROKER_EXPIRED_STATUSES
        | LOCAL_PRE_SUBMISSION_STATUSES
        | {
            "",
            "submitting",
            "resuming",
            "retrieving",
            "downloading",
            "verifying",
            "cancelled_locally",
            "timed_out",
            "submission_unknown",
            "succeeded",
            "failed",
        }
    )
    if status not in allowed_statuses or not task_id:
        status = ""
    stage = str(source.get("stage") or "").strip().lower()
    if stage not in SEEDANCE_RECOVERY_STAGES or not task_id:
        stage = ""
    model_id = str(source.get("model_id") or "").strip()
    if model_id not in MODEL_DISPLAY_NAME_BY_ID:
        model_id = ""
    output_format = str(source.get("output_format") or "").strip().lower()
    if output_format not in OUTPUT_FORMAT_CHOICES:
        output_format = ""
    output_file = str(source.get("output_file") or "").strip()
    if (
        len(output_file) > 4096
        or output_file.lower().startswith(("http://", "https://", "data:"))
    ):
        output_file = ""

    def bounded_integer(raw: Any, maximum: int) -> int:
        if not isinstance(raw, int) or isinstance(raw, bool):
            return 0
        return min(maximum, max(0, raw))

    return {
        "schema": SEEDANCE_RECOVERY_SCHEMA,
        "version": SEEDANCE_RECOVERY_VERSION,
        "revision": bounded_integer(source.get("revision"), 2_147_483_647),
        "stage": stage,
        "task_id": task_id,
        "task_identity": identity,
        "status": status,
        "terminal": source.get("terminal") is True,
        "updated_at_ms": bounded_integer(
            source.get("updated_at_ms"), 9_999_999_999_999
        ),
        "model_id": model_id,
        "output_format": output_format,
        "return_last_frame": source.get("return_last_frame") is True,
        "output_file": output_file,
    }


def _workflow_checkpoint_lock() -> asyncio.Lock:
    """Return one save coordinator per event loop without binding stale loops."""

    loop = asyncio.get_running_loop()
    with _WORKFLOW_CHECKPOINT_LOCKS_GUARD:
        lock = _WORKFLOW_CHECKPOINT_LOCKS.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            _WORKFLOW_CHECKPOINT_LOCKS[loop] = lock
        return lock


def _seedance_uuid_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return text if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        text,
    ) else ""


def _seedance_widget_catalog(value: Any) -> dict[str, Any]:
    """Normalize the bounded backend catalog exposed to the custom widget."""

    if not isinstance(value, dict) or set(value) != {
        "schema", "version", "publisher_instance_uuid", "channel_uuid",
        "generation", "metadata_sha256", "shots",
    }:
        return {}
    publisher = _seedance_uuid_text(value.get("publisher_instance_uuid"))
    channel = _seedance_uuid_text(value.get("channel_uuid"))
    generation = value.get("generation")
    metadata_sha256 = str(value.get("metadata_sha256") or "").strip().casefold()
    if (
        value.get("schema") != "hmb-shot-routing-catalog"
        or value.get("version") != 1
        or not publisher
        or not channel
        or not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
        or re.fullmatch(r"[0-9a-f]{64}", metadata_sha256) is None
        or not isinstance(value.get("shots"), list)
        or not 1 <= len(value["shots"]) <= SHOT_ROUTING_MAX_SHOTS
    ):
        return {}
    shots: list[dict[str, Any]] = []
    shot_ids: set[str] = set()
    numbers: set[int] = set()
    for raw in value["shots"]:
        if not isinstance(raw, dict) or set(raw) != {
            "shot_uuid", "number", "name", "revision",
        }:
            return {}
        shot_uuid = _seedance_uuid_text(raw.get("shot_uuid"))
        number = raw.get("number")
        revision = raw.get("revision")
        name = " ".join(str(raw.get("name") or "").split())
        if (
            not shot_uuid
            or shot_uuid in shot_ids
            or not isinstance(number, int)
            or isinstance(number, bool)
            or not 1 <= number <= SHOT_ROUTING_MAX_SHOTS
            or number in numbers
            or not isinstance(raw.get("name"), str)
            or raw.get("name") != name
            or not name
            or len(name) > 128
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 0
        ):
            return {}
        shot_ids.add(shot_uuid)
        numbers.add(number)
        shots.append({
            "shot_uuid": shot_uuid,
            "number": number,
            "name": name,
            "revision": revision,
        })
    shots.sort(key=lambda item: (item["number"], item["shot_uuid"]))
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": publisher,
        "channel_uuid": channel,
        "generation": generation,
        "metadata_sha256": metadata_sha256,
        "shots": shots,
    }


def _seedance_widget_value(
    shot: Any = None,
    shot_catalog: Any = None,
    generation: Any = None,
    remote_prompt_route: Any = None,
) -> dict[str, Any]:
    """Build the sole backend-authoritative Seedance custom-widget value."""

    catalog = _seedance_widget_catalog(shot_catalog)
    raw_shot = shot if isinstance(shot, dict) else {}
    requested_channel = _seedance_uuid_text(raw_shot.get("channel_uuid"))
    requested_uuid = _seedance_uuid_text(raw_shot.get("shot_uuid"))
    selected = None
    if catalog and requested_channel == catalog["channel_uuid"] and requested_uuid:
        selected = next(
            (item for item in catalog["shots"] if item["shot_uuid"] == requested_uuid),
            None,
        )
    shot_value = {
        "channel_uuid": catalog["channel_uuid"] if selected else "",
        "shot_uuid": selected["shot_uuid"] if selected else "",
        "number": selected["number"] if selected else 1,
        "name": selected["name"] if selected else SHOT_ONLY_LABEL,
    }
    return {
        "schema": "hmb-seedance-shot-ui",
        "schema_version": 2,
        "shot_catalog": catalog,
        "shot": shot_value,
        "generation": _seedance_generation_preview_value(generation),
        "remote_prompt_route": _seedance_remote_prompt_route_value(
            remote_prompt_route
        ),
    }


def _seedance_remote_prompt_route_value(value: Any = None) -> dict[str, Any]:
    """Normalize the UI-only descriptor for one managed public prompt edge.

    This descriptor never carries prompt text and never grants execution
    authority.  The retained-mode connection remains the sole source of truth;
    the widget uses these bounded endpoint names only to hide that exact edge
    line while the host keeps both public ports visibly connected.
    """

    disconnected = {
        "schema": "hmb-seedance-remote-prompt-route",
        "version": 1,
        "connected": False,
        "source_node_name": "",
        "previous_source_node_name": "",
        "target_node_name": "",
        "previous_target_node_name": "",
        "source_parameter": "output",
        "target_parameter": "prompt",
    }
    if not isinstance(value, dict) or value.get("connected") is not True:
        return disconnected
    source_name = value.get("source_node_name")
    previous_source_name = value.get("previous_source_node_name", "")
    target_name = value.get("target_node_name")
    previous_target_name = value.get("previous_target_node_name", "")
    if (
        not isinstance(source_name, str)
        or not isinstance(previous_source_name, str)
        or not isinstance(target_name, str)
        or not isinstance(previous_target_name, str)
    ):
        return disconnected
    source_name = source_name.strip()
    previous_source_name = previous_source_name.strip()
    target_name = target_name.strip()
    previous_target_name = previous_target_name.strip()
    if (
        not source_name
        or not target_name
        or len(source_name) > 512
        or len(previous_source_name) > 512
        or len(target_name) > 512
        or len(previous_target_name) > 512
        or any(
            ord(character) < 32
            for character in (
                source_name
                + previous_source_name
                + target_name
                + previous_target_name
            )
        )
    ):
        return disconnected
    return {
        **disconnected,
        "connected": True,
        "source_node_name": source_name,
        "previous_source_node_name": (
            previous_source_name
            if previous_source_name != source_name
            else ""
        ),
        "target_node_name": target_name,
        "previous_target_node_name": (
            previous_target_name
            if previous_target_name != target_name
            else ""
        ),
    }


def _merge_seedance_remote_prompt_route_aliases(
    current: Any,
    discovered: Any,
) -> dict[str, Any]:
    """Retain one reset-era alias for each exact public edge endpoint.

    Griptape resets a node through a temporary replacement name and then
    renames that same object back to the original name. React Flow may retain
    temporary endpoint names in the edge ``data-id`` while publishing final
    names in its aria label. Both proven names for each endpoint therefore
    describe the same retained edge during this bounded transition; prompt
    execution authority still comes only from the real connection.
    """

    current_route = _seedance_remote_prompt_route_value(current)
    next_route = _seedance_remote_prompt_route_value(discovered)
    if not next_route["connected"] or not current_route["connected"]:
        return next_route

    def previous_alias(
        current_name: str,
        current_previous_name: str,
        next_name: str,
        next_previous_name: str,
    ) -> str:
        if next_previous_name and next_previous_name != next_name:
            return next_previous_name
        return next(
            (
                name
                for name in (current_name, current_previous_name)
                if name and name != next_name
            ),
            "",
        )

    previous_source_name = previous_alias(
        current_route["source_node_name"],
        current_route["previous_source_node_name"],
        next_route["source_node_name"],
        next_route["previous_source_node_name"],
    )
    previous_target_name = previous_alias(
        current_route["target_node_name"],
        current_route["previous_target_node_name"],
        next_route["target_node_name"],
        next_route["previous_target_node_name"],
    )
    return _seedance_remote_prompt_route_value(
        {
            **next_route,
            "previous_source_node_name": previous_source_name,
            "previous_target_node_name": previous_target_name,
        }
    )

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
_SIGNED_URL_QUERY_PATTERN = re.compile(
    r"(?i)(?P<base>https?://[^\s'\"<>?#]+)\?[^\s'\"<>#]*"
)
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
        # Only the create-call catch may promote this to True. Keeping it out of
        # the constructor prevents errors from accepted task polling/retrieval
        # paths from inheriting create-rejection semantics.
        self.definitive_submission_rejection = False


class _BrokerUnavailableError(_BrokerError):
    pass


class _BrokerAuthenticationError(_BrokerError):
    pass


class _BrokerProtocolError(_BrokerError):
    pass


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
    try:
        return _broker_load_bearer_token_readonly()
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
            "task",
            "omni_reference_task_type",
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
            "output_format",
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
            "execution_expires_after",
        }
    )
    _SEEDANCE_V2_FIELDS = frozenset(
        {"omni_reference_task_type", "output_format", "return_last_frame"}
    )
    _MODEL_GENERATION_FIELDS = {
        SEEDANCE_2_0_MODEL_ID: _COMMON_SEEDANCE_FIELDS
        | _REFERENCE_MODE_FIELDS
        | frozenset({"priority"}),
        SEEDANCE_2_0_FAST_MODEL_ID: _COMMON_SEEDANCE_FIELDS
        | _REFERENCE_MODE_FIELDS,
        SEEDANCE_2_5_MODEL_ID: _COMMON_SEEDANCE_FIELDS
        | _REFERENCE_MODE_FIELDS
        | _SEEDANCE_V2_FIELDS,
    }
    def __init__(self, *, opener: Any | None = None) -> None:
        self._opener = opener if opener is not None else _broker_build_opener()
        self._seedance_capabilities: dict[str, Any] | None = None

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
                _broker_require_exact_response_url(response, request.full_url)
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

    @staticmethod
    def _seedance_v2_requested(
        *,
        task: str,
        output_format: str,
        return_last_frame: bool,
    ) -> bool:
        return bool(
            task
            in {
                TASK_REFERENCE_TO_VIDEO,
                TASK_VIDEO_EDITING,
                TASK_VIDEO_EXTENSION,
            }
            or output_format == "mov"
            or return_last_frame
        )

    def require_seedance_features(
        self,
        *,
        model_id: str,
        task: str,
        output_format: str,
        return_last_frame: bool,
        timeout: float = 10.0,
    ) -> None:
        """Prove advanced 2.5 support before upload or billable submission.

        The currently deployed Broker can continue serving the established v1
        Text/Frame MP4 contract. Explicit 2.5 Reference-to-Video, editing,
        extension, MOV, and returned frames are sent only after an authenticated
        capability document confirms the exact v2 model/task/output contract.
        """

        model = str(model_id or "").strip()
        authored_task = str(task or "").strip()
        requested_format = str(output_format or DEFAULT_OUTPUT_FORMAT).strip().lower()
        if requested_format not in OUTPUT_FORMAT_CHOICES:
            raise _BrokerProtocolError("Seedance output format is unsupported.")
        if authored_task not in TASK_STORAGE_CHOICES:
            raise _BrokerProtocolError("Seedance Broker task is unsupported.")
        if not self._seedance_v2_requested(
            task=authored_task,
            output_format=requested_format,
            return_last_frame=bool(return_last_frame),
        ):
            return
        if model != SEEDANCE_2_5_MODEL_ID:
            raise _BrokerProtocolError(
                "Advanced Seedance task/output features require Seedance 2.5."
            )

        capability = self._seedance_capabilities
        if capability is None:
            try:
                response = self._request_json(
                    "GET",
                    BROKER_SEEDANCE_CAPABILITIES_PATH,
                    payload=None,
                    timeout=max(1.0, min(float(timeout), 30.0)),
                )
            except Exception as exc:
                raise _BrokerProtocolError(
                    "FN AI Broker has not enabled the Seedance 2.5 advanced "
                    "generation contract. No media was uploaded and no render "
                    "was submitted."
                ) from exc
            if (
                not isinstance(response, dict)
                or response.get("schema") != BROKER_SEEDANCE_CAPABILITIES_SCHEMA
                or response.get("version") != BROKER_SEEDANCE_CAPABILITIES_VERSION
                or not isinstance(response.get("models"), dict)
            ):
                raise _BrokerProtocolError(
                    "FN AI Broker returned an invalid Seedance capability contract."
                )
            models = response["models"]
            profile = models.get(SEEDANCE_2_5_MODEL_ID)
            if not isinstance(profile, dict):
                raise _BrokerProtocolError(
                    "FN AI Broker does not advertise the Seedance 2.5 profile."
                )
            tasks = profile.get("tasks")
            formats = profile.get("output_formats")
            if (
                not isinstance(tasks, list)
                or not all(isinstance(value, str) for value in tasks)
                or not isinstance(formats, list)
                or not all(isinstance(value, str) for value in formats)
                or not isinstance(profile.get("return_last_frame"), bool)
            ):
                raise _BrokerProtocolError(
                    "FN AI Broker Seedance 2.5 capabilities are malformed."
                )
            capability = {
                "tasks": frozenset(tasks),
                "output_formats": frozenset(
                    str(value).strip().lower() for value in formats
                ),
                "return_last_frame": profile["return_last_frame"],
            }
            self._seedance_capabilities = capability

        task_slug = TASK_BROKER_SLUGS[authored_task]
        if task_slug not in capability["tasks"]:
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled the selected Seedance 2.5 task."
            )
        if requested_format not in capability["output_formats"]:
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled the selected Seedance output format."
            )
        if return_last_frame and not capability["return_last_frame"]:
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled returned Seedance last frames."
            )

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
        task = str(request_payload.get(TASK_PARAMETER) or "").strip()
        if task:
            if task not in TASK_STORAGE_CHOICES:
                raise _BrokerProtocolError("Seedance Broker task is unsupported.")
            if task not in MODEL_TASK_CHOICES[model]:
                raise _BrokerProtocolError(
                    "Selected Seedance model does not support the requested task."
                )
        elif model == SEEDANCE_2_5_MODEL_ID:
            task = INPUT_MODE_TASKS.get(
                str(request_payload.get("input_mode") or ""),
                TASK_REFERENCE_TO_VIDEO,
            )

        requested_format = str(
            request_payload.get("output_format") or DEFAULT_OUTPUT_FORMAT
        ).strip().lower()
        requested_last_frame = request_payload.get("return_last_frame", False)
        if model == SEEDANCE_2_5_MODEL_ID:
            if requested_format not in OUTPUT_FORMAT_CHOICES:
                raise _BrokerProtocolError("Seedance output format is unsupported.")
            if not isinstance(requested_last_frame, bool):
                raise _BrokerProtocolError(
                    "Seedance return_last_frame must be a boolean."
                )
            advanced_v2 = self._seedance_v2_requested(
                task=task,
                output_format=requested_format,
                return_last_frame=requested_last_frame,
            )
            if advanced_v2:
                self.require_seedance_features(
                    model_id=model,
                    task=task,
                    output_format=requested_format,
                    return_last_frame=requested_last_frame,
                    timeout=min(float(timeout), 30.0),
                )
                # Task is an HMB authoring value, not a Volcengine request
                # field. Stock Seedance 2.5 declares only the three reference
                # subtasks through omni_reference_task_type; text and frame
                # requests omit it and are inferred from their content roles.
                request_payload.pop(TASK_PARAMETER, None)
                omni_task = TASK_OMNI_REFERENCE_TYPES.get(task)
                if omni_task:
                    request_payload["omni_reference_task_type"] = omni_task
                else:
                    request_payload.pop("omni_reference_task_type", None)
                request_payload["output_format"] = requested_format
                request_payload["return_last_frame"] = requested_last_frame
            else:
                # Established Text/Frame v1 Broker requests remain byte-for-byte
                # compatible. Reference-to-Video is always task-declared above.
                request_payload.pop(TASK_PARAMETER, None)
                request_payload.pop("omni_reference_task_type", None)
                request_payload.pop("output_format", None)
                request_payload.pop("return_last_frame", None)
        else:
            # Stale 2.5-only UI values can survive a saved model switch, but
            # neither 2.0 request may carry them to the server.
            request_payload.pop(TASK_PARAMETER, None)
            request_payload.pop("omni_reference_task_type", None)
            request_payload.pop("output_format", None)
            request_payload.pop("return_last_frame", None)
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
        raw_url = str(url or "")
        candidate = urlparse(raw_url)
        broker = urlparse(self.server_url)

        def origin(parsed: Any) -> tuple[str, str, int]:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return parsed.scheme.lower(), (parsed.hostname or "").lower(), port

        try:
            return (
                re.fullmatch(
                    r"/api/assets/[A-Za-z0-9_-]{43}", candidate.path
                )
                is not None
                and "%" not in raw_url
                and origin(candidate) == origin(broker)
                and candidate.username is None
                and candidate.password is None
                and candidate.query == ""
                and candidate.fragment == ""
            )
        except ValueError:
            return False

    def download_trusted_result(
        self,
        url: str,
        *,
        max_bytes: int,
        media_type: str = "video",
    ) -> bytes:
        if not self.is_trusted_broker_url(url):
            raise _BrokerProtocolError(
                "Broker authorization was refused for an external URL."
            )
        if media_type == "image":
            accept = "image/png,application/octet-stream"
        elif media_type == "video":
            accept = "video/mp4,video/quicktime,application/octet-stream"
        else:
            raise _BrokerProtocolError("Broker result media type is invalid.")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": accept,
                "Authorization": "Bearer " + _broker_load_token(),
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=300) as response:
                _broker_require_exact_response_url(response, request.full_url)
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
            raise _BrokerProtocolError("Downloaded media exceeds the size limit.")
        if media_type == "video" and (
            len(raw) < 12 or raw[4:8] != b"ftyp"
        ):
            raise _BrokerProtocolError(
                "Downloaded result is not a valid video container."
            )
        if media_type == "image" and not _is_valid_png(raw):
            raise _BrokerProtocolError(
                "Downloaded result is not a valid PNG image."
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
        self._broker_action_lock = threading.Lock()
        self._broker_action_running = False
        self._generation_refresh_lock = threading.Lock()
        self._generation_refresh_running = False
        self._generation_run_active = threading.Event()
        self._hmb_generation_preview_state = _seedance_generation_preview_value()
        self._hmb_generation_recovery_restore_fingerprint: (
            tuple[Any, ...] | None
        ) = None
        self._hmb_last_saved_recovery_revision = 0
        self._hmb_generation_started_monotonic: float | None = None
        self._hmb_generation_started_at_ms = 0
        self._hmb_generation_media_revision = 0
        self._hmb_last_success_video: VideoUrlArtifact | None = None
        self._hmb_last_success_last_frame_url: ImageUrlArtifact | None = None
        self._hmb_output_format_initial_setup_seen = False
        self._hmb_return_last_frame_initial_setup_seen = False
        self._hmb_output_contract_syncing = False
        self._hmb_pending_generation_action = False
        self._hmb_generation_action_only_update = False
        self._hmb_pending_generation_command_id = ""
        self._hmb_processed_generation_command_ids: set[str] = set()
        self._hmb_node_deleted = False
        self._hmb_delete_parent_called = False
        self._hmb_model_migration_active = False
        self._hmb_retired_model_migration_pending = False
        self._hmb_model_initial_setup_seen = False
        self._hmb_resolution_initial_setup_seen = False
        self._hmb_task_initial_setup_seen = False
        self._hmb_task_syncing = False
        self._hmb_input_mode_initial_setup_seen = False
        self._hmb_input_mode_syncing = False
        self._hmb_explicit_list_authority: set[str] = set()
        self._hmb_shot_syncing = False
        self._hmb_shared_routing_in_progress = False
        self._hmb_shot_catalog_snapshot: dict[str, Any] | None = None
        self._hmb_shot_catalog_generation = 0
        self._hmb_shot_selector_map: dict[str, dict[str, Any]] = {}
        self._hmb_shot_route_status: dict[str, Any] = {}
        self._hmb_remote_prompt_route = _seedance_remote_prompt_route_value()
        self._hmb_autoclaim_in_progress = False

        self.add_parameter(
            ParameterString(
                name=SHOT_SELECTOR_PARAMETER,
                default_value=SHOT_ONLY_LABEL,
                tooltip="Legacy Shot selector state retained for saved-workflow compatibility.",
                allowed_modes={ParameterMode.PROPERTY},
                serializable=False,
                hide=True,
                hide_property=True,
                hide_label=True,
                traits={Options(choices=[SHOT_ONLY_LABEL])},
                ui_options={
                    "display_name": "",
                    "simple_dropdown": [SHOT_ONLY_LABEL],
                    "hide": True,
                    "hide_property": True,
                    "hide_label": True,
                    "hide_handles": True,
                    "height": 1,
                    "min_height": 0,
                    "max_height": 1,
                    "is_full_width": True,
                },
            )
        )
        for shot_parameter in (
            ParameterString(
                name=SHOT_CHANNEL_UUID_PARAMETER,
                default_value="",
                allowed_modes={ParameterMode.PROPERTY},
                hide=True,
                hide_property=True,
                hide_label=True,
                ui_options={
                    "display_name": "", "compact": True, "height": 1,
                    "min_height": 0, "max_height": 1, "is_full_width": True,
                    "hide": True, "hide_property": True, "hide_label": True,
                    "hide_handles": True,
                },
            ),
            ParameterString(
                name=SHOT_UUID_PARAMETER,
                default_value="",
                allowed_modes={ParameterMode.PROPERTY},
                hide=True,
                hide_property=True,
                hide_label=True,
                ui_options={
                    "display_name": "", "compact": True, "height": 1,
                    "min_height": 0, "max_height": 1, "is_full_width": True,
                    "hide": True, "hide_property": True, "hide_label": True,
                    "hide_handles": True,
                },
            ),
            ParameterInt(
                name=SHOT_NUMBER_PARAMETER,
                default_value=0,
                allowed_modes={ParameterMode.PROPERTY},
                hide=True,
                hide_property=True,
                hide_label=True,
                ui_options={
                    "display_name": "", "compact": True, "height": 1,
                    "min_height": 0, "max_height": 1, "is_full_width": True,
                    "hide": True, "hide_property": True, "hide_label": True,
                    "hide_handles": True,
                },
            ),
            ParameterString(
                name=SHOT_NAME_PARAMETER,
                default_value="",
                allowed_modes={ParameterMode.PROPERTY},
                hide=True,
                hide_property=True,
                hide_label=True,
                ui_options={
                    "display_name": "", "compact": True, "height": 1,
                    "min_height": 0, "max_height": 1, "is_full_width": True,
                    "hide": True, "hide_property": True, "hide_label": True,
                    "hide_handles": True,
                },
            ),
        ):
            self.add_parameter(shot_parameter)

        self.add_parameter(
            ParameterString(
                name=SHOT_PROMPT_INPUT_PARAMETER,
                default_value="",
                tooltip="Hidden exact Agent final-text dependency for the selected Shot.",
                allowed_modes={ParameterMode.INPUT},
                hide=True,
                hide_label=True,
                hide_property=True,
                ui_options={
                    "display_name": "",
                    "hide": True,
                    "hide_property": True,
                    "hide_label": True,
                    "hide_handles": True,
                    "height": 1,
                    "min_height": 0,
                    "max_height": 1,
                    "is_full_width": True,
                },
            )
        )
        hidden_shot_input_ui = {
            "display_name": "",
            "hide": True,
            "hide_property": True,
            "hide_label": True,
            "hide_handles": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "is_full_width": True,
        }
        self.add_parameter(
            Parameter(
                name=SHOT_ASSET_INPUT_PARAMETER,
                type="str",
                input_types=["str"],
                default_value="",
                tooltip=(
                    "Hidden exact ImageAsset Shot source dependency. Media is "
                    "read from the source's private atomic snapshot."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide=True,
                hide_label=True,
                hide_property=True,
                ui_options=dict(hidden_shot_input_ui),
            )
        )
        self.add_parameter(
            ParameterDict(
                name=SHOT_PICKER_INPUT_PARAMETER,
                type="dict",
                input_types=["dict"],
                accept_any=False,
                default_value={},
                tooltip=(
                    "Hidden exact VideoPicker Shot source dependency. Legacy "
                    "serialized JSON is migrated to a dict; media is read from "
                    "the source's private atomic snapshot."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide=True,
                hide_label=True,
                hide_property=True,
                ui_options=dict(hidden_shot_input_ui),
            )
        )
        for name, tooltip in (
            (
                SHOT_IMAGE_INPUT_PARAMETER,
                "Hidden ordered Prompt image dependency for the selected Shot.",
            ),
            (
                SHOT_VIDEO_INPUT_PARAMETER,
                "Hidden ordered Prompt video dependency for the selected Shot.",
            ),
        ):
            self.add_parameter(
                Parameter(
                    name=name,
                    type="list[str]",
                    input_types=["list[str]"],
                    default_value=[],
                    tooltip=tooltip,
                    allowed_modes={ParameterMode.INPUT},
                    hide=True,
                    hide_property=True,
                    ui_options={
                        "display_name": "",
                        "hide": True,
                        "hide_property": True,
                        "hide_label": True,
                        "hide_handles": True,
                        "height": 1,
                        "min_height": 0,
                        "max_height": 1,
                        "is_full_width": True,
                    },
                )
            )

        shot_widget_kwargs: dict[str, Any] = {
            "name": SEEDANCE_SHOT_WIDGET_PARAMETER,
            "type": "dict",
            "input_types": ["dict"],
            "default_value": _seedance_widget_value(
                generation=self._hmb_generation_preview_state
            ),
            "tooltip": "Select one backend-verified production Shot.",
            "allowed_modes": {ParameterMode.PROPERTY},
            "serializable": False,
            "ui_options": {
                "display_name": "HMBSeedanceGeneration",
                "is_full_width": True,
                "height": SEEDANCE_SHOT_WIDGET_HEIGHT,
                "min_height": SEEDANCE_SHOT_WIDGET_HEIGHT,
                "max_height": SEEDANCE_SHOT_WIDGET_HEIGHT,
                "widget_height": SEEDANCE_SHOT_WIDGET_HEIGHT,
                "default_height": SEEDANCE_SHOT_WIDGET_HEIGHT,
                "preferred_height": SEEDANCE_SHOT_WIDGET_HEIGHT,
                "initial_height": SEEDANCE_SHOT_WIDGET_HEIGHT,
                "expandable": False,
                "resizable": False,
                "compact": True,
            },
        }
        try:
            if Widget is not None:
                shot_widget_parameter = Parameter(
                    **{
                        **shot_widget_kwargs,
                        "traits": {
                            Widget(
                                name=SEEDANCE_SHOT_WIDGET_NAME,
                                library=SEEDANCE_SHOT_WIDGET_LIBRARY_NAME,
                            )
                        },
                    }
                )
            else:
                shot_widget_parameter = Parameter(**shot_widget_kwargs)
        except Exception:
            shot_widget_parameter = Parameter(**shot_widget_kwargs)
            if Widget is not None:
                with suppress(Exception):
                    shot_widget_parameter.add_trait(
                        Widget(
                            name=SEEDANCE_SHOT_WIDGET_NAME,
                            library=SEEDANCE_SHOT_WIDGET_LIBRARY_NAME,
                        )
                    )
        self.add_parameter(shot_widget_parameter)

        # A separate, zero-height custom-widget parameter carries one-shot
        # refresh commands. Reusing HMB_SEEDANCE_SHOT_UI would make Griptape
        # reconcile the durable Shot/catalog value; programmatically clicking
        # the native ParameterButton can leave React waiting forever when its
        # SendNodeMessage response is lost. This bridge contains no task ID.
        refresh_command_kwargs: dict[str, Any] = {
            "name": SEEDANCE_REFRESH_COMMAND_PARAMETER,
            "type": "dict",
            "input_types": ["dict"],
            "default_value": _seedance_refresh_command_value(),
            "tooltip": "Ephemeral minimal command transport for existing-task retrieval.",
            "allowed_modes": {ParameterMode.PROPERTY},
            "serializable": False,
            "ui_options": {
                "display_name": "",
                "is_full_width": True,
                "height": 1,
                "min_height": 0,
                "max_height": 1,
                "widget_height": 1,
                "expandable": False,
                "resizable": False,
                "compact": True,
                "hide_label": True,
                "hide_handles": True,
            },
        }
        try:
            if Widget is not None:
                refresh_command_parameter = Parameter(
                    **{
                        **refresh_command_kwargs,
                        "traits": {
                            Widget(
                                name=SEEDANCE_SHOT_WIDGET_NAME,
                                library=SEEDANCE_SHOT_WIDGET_LIBRARY_NAME,
                            )
                        },
                    }
                )
            else:
                refresh_command_parameter = Parameter(**refresh_command_kwargs)
        except Exception:
            refresh_command_parameter = Parameter(**refresh_command_kwargs)
            if Widget is not None:
                with suppress(Exception):
                    refresh_command_parameter.add_trait(
                        Widget(
                            name=SEEDANCE_SHOT_WIDGET_NAME,
                            library=SEEDANCE_SHOT_WIDGET_LIBRARY_NAME,
                        )
                    )
        self.add_parameter(refresh_command_parameter)

        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value=MODEL_NAME_SEEDANCE_2_0,
                tooltip=(
                    "Select Seedance 2.0, 2.0 Fast, or 2.5. Seedance 2.5 "
                    "supports 4-30 second generations and optional 1080p HEVC; "
                    "the existing 2.0 contracts remain unchanged."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            MODEL_NAME_SEEDANCE_2_0,
                            MODEL_NAME_SEEDANCE_2_0_FAST,
                            MODEL_NAME_SEEDANCE_2_5,
                        ]
                    )
                },
                ui_options={"display_name": "Model"},
            )
        )
        self.add_parameter(
            ParameterString(
                name=TASK_PARAMETER,
                default_value=TASK_REFERENCE_TO_VIDEO,
                tooltip=(
                    "Seedance 2.5 task. Only mode keeps the authored value; a "
                    "routed Shot executes Reference to Video with its exact "
                    "same-Shot media without changing the saved task."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=list(TASK_STORAGE_CHOICES))},
                ui_options={
                    "display_name": "Task",
                    "simple_dropdown": list(
                        MODEL_TASK_CHOICES[SEEDANCE_2_0_MODEL_ID]
                    ),
                },
            )
        )
        self.add_parameter(
            ParameterString(
                name="input_mode",
                default_value=INPUT_MODE_MULTIMODAL_REFERENCES,
                tooltip=(
                    "Seedance 2.0/2.0 Fast input mode. Multimodal References "
                    "accepts ordered image, video, and audio references. This "
                    "same field remains the saved compatibility mode for 2.5."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                hide=True,
                hide_property=True,
                hide_label=True,
                traits={
                    Options(
                        choices=[
                            INPUT_MODE_TEXT_ONLY,
                            INPUT_MODE_FIRST_LAST_FRAME,
                            INPUT_MODE_MULTIMODAL_REFERENCES,
                        ]
                    )
                },
                ui_options={
                    "display_name": "",
                    "hide": True,
                    "hide_property": True,
                    "hide_label": True,
                    "hide_handles": True,
                    "simple_dropdown": [
                        INPUT_MODE_TEXT_ONLY,
                        INPUT_MODE_FIRST_LAST_FRAME,
                        INPUT_MODE_MULTIMODAL_REFERENCES,
                    ],
                },
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value="",
                tooltip=(
                    "Text prompt for the selected Seedance model. Enter it directly or "
                    "manually connect an HMBAgentLibrary output. Shot media is resolved "
                    "independently from ImageAsset and VideoPicker."
                ),
                multiline=True,
                placeholder_text="Describe the desired video...",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                allow_output=False,
                ui_options={"display_name": "Prompt"},
            )
        )
        hidden_routing_control_ui = {
            "display_name": "",
            "hide": True,
            "hide_property": True,
            "hide_label": True,
            "hide_handles": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "is_full_width": True,
        }
        self.add_parameter(
            ParameterBool(
                name=SHOT_AUTOCLAIM_ENABLED_PARAMETER,
                default_value=True,
                allowed_modes={ParameterMode.PROPERTY},
                hide=True,
                hide_property=True,
                hide_label=True,
                ui_options=dict(hidden_routing_control_ui),
            )
        )
        self.add_parameter(
            ParameterImage(
                name="first_frame",
                default_value=None,
                tooltip="First-frame image for First/Last Frame mode.",
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
                ui_options={
                    "display_name": "First Frame",
                    "hide_property": True,
                },
            )
        )
        self.add_parameter(
            ParameterImage(
                name="last_frame",
                default_value=None,
                tooltip="Optional last-frame image for First/Last Frame mode.",
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
                ui_options={
                    "display_name": "Last Frame",
                    "hide_property": True,
                },
            )
        )
        self.add_parameter(
            ParameterList(
                name="reference_images",
                # Keep the graph payload list[str]-compatible while giving
                # each stock list row the native image handle colour.
                type="ImageUrlArtifact",
                input_types=[
                    "str",
                    "ImageUrlArtifact",
                    "ImageArtifact",
                    "BytePlusImageAssetReference",
                ],
                output_type="str",
                default_value="",
                tooltip=(
                    "Ordered reference images for Only mode. Add individual items or "
                    "connect HMBImageAssetLibrary's complete list to the top handle. "
                    "List order becomes Seedance image order."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide=False,
                ui_options={
                    "display_name": "Reference Images",
                    "hide": False,
                    "hide_property": True,
                    "hide_label": False,
                    "hide_handles": False,
                },
                max_items=MAX_REFERENCE_IMAGES,
            )
        )

        # Keep the former three scalar ports registered but hidden so workflows
        # saved with those exact parameter names continue to resolve. New HMB
        # workflows use the ordered VIDEO_REFERENCES list below.
        for index in range(1, LEGACY_VIDEO_REFERENCE_SLOTS + 1):
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
            ParameterList(
                name=VIDEO_REFERENCES_PARAMETER,
                # Keep the graph payload list[str]-compatible while giving
                # each stock list row the native video handle colour.
                type="VideoUrlArtifact",
                input_types=[
                    "str",
                    "VideoUrlArtifact",
                    "BytePlusVideoAssetReference",
                ],
                output_type="str",
                default_value="",
                tooltip=(
                    "Ordered reference videos for Only mode. Add individual items or "
                    "connect HMBVideoPickerLibrary's complete list to the top handle. "
                    "Picker selection order becomes Seedance order."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide=False,
                ui_options={
                    "display_name": "Reference Videos",
                    "hide": False,
                    "hide_property": True,
                    "hide_label": False,
                    "hide_handles": False,
                },
                max_items=MAX_VIDEO_REFERENCES,
            )
        )
        self.add_parameter(
            ParameterList(
                name="reference_audio",
                # This was already inferred from the first input type. Make it
                # explicit so the stock audio handle remains orange if the
                # compatibility input ordering changes later.
                type="AudioArtifact",
                input_types=[
                    "AudioArtifact",
                    "AudioUrlArtifact",
                    "str",
                    "BytePlusAudioAssetReference",
                ],
                default_value=[],
                tooltip=(
                    "Optional ordered reference audio. Seedance 2.5 accepts up to "
                    "10 files and permits audio-only reference input; 2.0 models "
                    "retain the 3-file limit and require image or video context."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide=False,
                ui_options={
                    "display_name": "Reference Audio",
                    "hide": False,
                    "hide_property": True,
                    "hide_label": False,
                    "hide_handles": False,
                },
                max_items=MAX_REFERENCE_AUDIO,
            )
        )

        with ParameterGroup(name="Generation Settings") as generation_settings:
            ParameterString(
                name="resolution",
                default_value=MODEL_DEFAULT_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID],
                tooltip=(
                    "Seedance 2.0 defaults to 1080p. Seedance 2.5 and Fast "
                    "default to 720p; 2.5 also offers 1080p 10-bit HEVC."
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
                tooltip=(
                    "Duration: Seedance 2.0 supports 4-15 seconds or -1 smart "
                    "duration; Seedance 2.5 uses an explicit 4-30 seconds."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                # The static converter must accept the union so saved 2.0
                # smart duration and 2.5 long duration both survive hydration
                # regardless of parameter order.
                # The visible dropdown is narrowed per model below.
                traits={
                    Options(
                        choices=list(DURATION_STORAGE_CHOICES)
                    )
                },
                ui_options={
                    "simple_dropdown": list(
                        MODEL_DURATION_CHOICES[SEEDANCE_2_0_MODEL_ID]
                    )
                },
            )
            ParameterBool(
                name="generate_audio",
                default_value=False,
                tooltip="Generate audio with the video. Disabled by default on new nodes.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterString(
                name="output_format",
                default_value=DEFAULT_OUTPUT_FORMAT,
                tooltip=(
                    "Seedance 2.5 output container. MP4 is the compatible default; "
                    "MOV is intended for post-production and may require an external "
                    "HEVC-capable player. Seedance 2.0 always uses MP4."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=list(OUTPUT_FORMAT_CHOICES))},
                ui_options={
                    "display_name": "Output Format",
                    "simple_dropdown": list(OUTPUT_FORMAT_CHOICES),
                },
                hide=True,
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
                tooltip=(
                    "Seedance 2.5 only: download the generated last frame into "
                    "a verified local PNG output. No signed provider URL is saved."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide=True,
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
                    "When Griptape Cloud authentication and a bucket are ready, "
                    "temporarily publish local image and video references as Cloud "
                    "HTTPS URLs. Otherwise images keep the Base64 JSON path and "
                    "videos use an already-supported fallback transport."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Auto Publish Local Videos"},
            )
            ParameterString(
                name="local_video_upload_service",
                default_value=LOCAL_VIDEO_UPLOAD_GRIPTAPE,
                tooltip=(
                    "Used for local video only when Griptape Cloud is unavailable. "
                    "Choose Volcengine TOS for the existing signed-HTTPS fallback; "
                    "public HTTPS and asset:// references always pass through."
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
                tooltip=(
                    "Downloaded local MP4/MOV preview; use the video_url output "
                    "connector for connections. Some 10-bit HEVC MOV files require an "
                    "external player even when the file saved successfully."
                ),
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
                tooltip="HMB alias of the verified local MP4/MOV output.",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
                hide_property=True,
                ui_options={"display_name": "video_url", "pulse_on_run": True},
            )
        )
        self.add_parameter(
            ParameterImage(
                name="last_frame_url",
                default_value=None,
                tooltip="Verified local PNG of the generated last frame.",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
                hide=True,
                ui_options={"display_name": "Last Frame Image"},
            )
        )
        self._output_file = ProjectFileParameter(
            node=self,
            name="output_file",
            default_filename="volcengine_seedance_video.mp4",
        )
        self._output_file.add_parameter()
        self._last_frame_file = ProjectFileParameter(
            node=self,
            name="last_frame_file",
            default_filename=LAST_FRAME_FILENAME,
            ui_options={"hide": True},
        )
        self._last_frame_file.add_parameter()
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
                hide=False,
                hide_property=False,
                ui_options={"display_name": "Task ID"},
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
                # Keep the Status fallback visible even after a completed video
                # has replaced the viewport recovery overlay.  The callback
                # acknowledges immediately and schedules a same-task-only
                # refresh, so this control never creates a replacement render.
                state="normal",
                hide=False,
                hide_property=False,
                serializable=False,
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

        # Unlike the browser preview and one-shot command parameters, this
        # bounded checkpoint is serialized with the workflow. It contains no
        # prompt, media, signed URL, provider body, or credential. Its sole
        # purpose is to recover the same paid Broker task after a hard restart.
        #
        # Keep it as the final node parameter. Griptape Nodes 0.95.1 replays
        # saved parameter commands sequentially; placing this hydration
        # sentinel after video/status outputs guarantees that the recovery UI
        # observes the fully restored local artifact before deciding whether a
        # same-task retrieval button is required.
        self.add_parameter(
            ParameterDict(
                name=SEEDANCE_RECOVERY_PARAMETER,
                default_value=_seedance_recovery_value(),
                tooltip="Durable same-task Seedance crash recovery checkpoint.",
                allowed_modes={ParameterMode.PROPERTY},
                settable=False,
                serializable=True,
                hide=True,
                hide_property=True,
                hide_label=True,
                ui_options={
                    "display_name": "",
                    "hide": True,
                    "hide_property": True,
                    "hide_label": True,
                    "hide_handles": True,
                    "height": 1,
                    "min_height": 0,
                    "max_height": 1,
                    "is_full_width": True,
                },
            )
        )
        self._update_parameter_visibility()
        _shot_routing.schedule_post_registration_reconcile(self)

    @staticmethod
    def _shot_uuid(value: Any) -> str:
        text = str(value or "").strip().casefold()
        return text if re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            text,
        ) else ""

    @staticmethod
    def _canonical_sha256(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def _validate_shot_catalog_snapshot(cls, value: Any) -> dict[str, Any]:
        required = {
            "schema", "version", "publisher_instance_uuid", "channel_uuid",
            "generation", "metadata_sha256", "shots",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RuntimeError("HMB Shot catalog has unknown or missing fields.")
        if value.get("schema") != "hmb-shot-routing-catalog" or value.get("version") != 1:
            raise RuntimeError("HMB Shot catalog schema is invalid.")
        publisher = cls._shot_uuid(value.get("publisher_instance_uuid"))
        channel = cls._shot_uuid(value.get("channel_uuid"))
        generation = value.get("generation")
        if (
            not publisher or not channel
            or not isinstance(generation, int) or isinstance(generation, bool)
            or generation <= 0
        ):
            raise RuntimeError("HMB Shot catalog publisher identity is invalid.")
        raw_shots = value.get("shots")
        if (
            not isinstance(raw_shots, list)
            or not 1 <= len(raw_shots) <= SHOT_ROUTING_MAX_SHOTS
        ):
            raise RuntimeError("HMB Shot catalog collections are invalid.")
        shots: list[dict[str, Any]] = []
        shot_ids: set[str] = set()
        numbers: set[int] = set()
        for raw in raw_shots:
            if not isinstance(raw, dict) or set(raw) != {
                "shot_uuid", "number", "name", "revision",
            }:
                raise RuntimeError("HMB Shot catalog record is invalid.")
            shot_uuid = cls._shot_uuid(raw.get("shot_uuid"))
            number = raw.get("number")
            revision = raw.get("revision")
            name = str(raw.get("name") or "").strip()
            if (
                not shot_uuid or shot_uuid in shot_ids or not name
                or not isinstance(raw.get("name"), str)
                or raw.get("name") != name
                or len(name) > 128
                or not isinstance(number, int) or isinstance(number, bool)
                or not 1 <= number <= SHOT_ROUTING_MAX_SHOTS or number in numbers
                or not isinstance(revision, int) or isinstance(revision, bool) or revision < 0
            ):
                raise RuntimeError("HMB Shot catalog identity/revision is invalid.")
            shot_ids.add(shot_uuid)
            numbers.add(number)
            shots.append({
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
            })
        metadata_document = {
            "channel_uuid": channel,
            "generation": generation,
            "shots": shots,
        }
        metadata_hash = str(value.get("metadata_sha256") or "").strip().casefold()
        if metadata_hash != cls._canonical_sha256(metadata_document):
            raise RuntimeError("HMB Shot catalog metadata hash does not match.")
        return {
            **deepcopy(value),
            "publisher_instance_uuid": publisher,
            "channel_uuid": channel,
            "shots": shots,
            "metadata_sha256": metadata_hash,
        }

    def _set_shot_value(
        self,
        name: str,
        value: Any,
        *,
        emit_change: bool = False,
    ) -> None:
        if self.get_parameter_value(name) == value:
            return
        try:
            self.set_parameter_value(name, value, emit_change=emit_change)
        except TypeError:
            self.set_parameter_value(name, value)

    def _set_hidden_control_value(self, name: str, value: Any) -> None:
        """Persist one hidden routing control without exposing a graph handle."""

        if self.get_parameter_value(name) == value:
            return
        try:
            self.set_parameter_value(name, value, emit_change=False)
        except TypeError:
            self.set_parameter_value(name, value)

    def _set_seedance_shot_choices(self, labels: list[str]) -> None:
        # Prompt-only generation is always available.  Remote Shot choices are
        # appended only when at least one exact same-flow media publisher is
        # available; no placeholder can accidentally become an executable Shot.
        choices = [SHOT_ONLY_LABEL, *list(labels)]
        parameter = self.get_parameter_by_name(SHOT_SELECTOR_PARAMETER)
        if parameter is None:
            return
        for child in getattr(parameter, "_children", ()):
            if isinstance(child, Options):
                with suppress(Exception):
                    child.choices = choices
        parameter.ui_options = {
            **dict(getattr(parameter, "ui_options", {}) or {}),
            "simple_dropdown": choices,
        }

    def _hmb_other_seedance_shot_claims(
        self,
        channel_uuid: str = "",
    ) -> set[tuple[str, str]]:
        """Return exact Shot claims owned by other Seedance nodes in this flow."""

        claims: set[tuple[str, str]] = set()
        try:
            same_flow = getattr(_shot_routing, "_same_flow_nodes")
            _flow_name, nodes = same_flow(self)
        except Exception:
            return claims
        for candidate in nodes:
            if candidate is self or bool(getattr(candidate, "_hmb_node_deleted", False)):
                continue
            getter = getattr(candidate, "_hmb_shot_channel_subscription", None)
            if not callable(getter):
                continue
            try:
                subscription = getter()
            except Exception:
                continue
            if (
                isinstance(subscription, dict)
                and subscription.get("participant_kind") == "seedance"
                and subscription.get("enabled")
                and subscription.get("channel_uuid")
                and subscription.get("shot_uuid")
                and (
                    not channel_uuid
                    or subscription.get("channel_uuid") == channel_uuid
                )
            ):
                claims.add(
                    (
                        str(subscription["channel_uuid"]),
                        str(subscription["shot_uuid"]),
                    )
                )
        return claims

    def _hmb_available_seedance_shot_catalog(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:
        """Expose Shots backed by one or both exact same-flow media sources."""

        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("shots"), list):
            return {}
        channel_uuid = str(snapshot.get("channel_uuid") or "")
        source_counts = {"image_asset": 0, "video_picker": 0}
        try:
            same_flow = getattr(_shot_routing, "_same_flow_nodes")
            _flow_name, nodes = same_flow(self)
        except Exception:
            nodes = []
        for candidate in nodes:
            if bool(getattr(candidate, "_hmb_node_deleted", False)):
                continue
            getter = getattr(candidate, "_hmb_shot_channel_subscription", None)
            if not callable(getter):
                continue
            try:
                subscription = getter()
            except Exception:
                continue
            if (
                not isinstance(subscription, dict)
                or not subscription.get("enabled")
                or subscription.get("channel_uuid") != channel_uuid
            ):
                continue
            participant_kind = str(
                subscription.get("participant_kind") or ""
            )
            if participant_kind in source_counts:
                source_counts[participant_kind] += 1
        if (
            any(count > 1 for count in source_counts.values())
            or not any(count == 1 for count in source_counts.values())
        ):
            return {}
        claimed = {
            shot_uuid
            for claim_channel, shot_uuid in self._hmb_other_seedance_shot_claims(
                channel_uuid
            )
            if claim_channel == channel_uuid
        }
        current = self._shot_identity()
        current_uuid = (
            current["shot_uuid"]
            if current["channel_uuid"] == channel_uuid
            else ""
        )
        shots = [
            deepcopy(item)
            for item in snapshot["shots"]
            if isinstance(item, dict)
            and (
                str(item.get("shot_uuid") or "") not in claimed
                or str(item.get("shot_uuid") or "") == current_uuid
            )
        ]
        return {**deepcopy(snapshot), "shots": shots} if shots else {}

    def _current_recovery_output_file(self) -> str:
        raw = self.get_parameter_value("output_file")
        location = getattr(raw, "location", getattr(raw, "value", raw))
        text = str(location or "").strip()
        if (
            len(text) > 4096
            or text.lower().startswith(("http://", "https://", "data:"))
        ):
            return ""
        return text

    def _build_recovery_output_destination(
        self,
        checkpoint: dict[str, Any],
    ) -> Any:
        """Rebuild the submitted task's saved output target, not today's UI value."""

        persisted = _seedance_recovery_value(
            self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER)
        )
        checkpoint_task_id = str(checkpoint.get("task_id") or "").strip()
        output_file = str(persisted.get("output_file") or "").strip()
        if (
            not checkpoint_task_id
            or persisted.get("task_id") != checkpoint_task_id
            or not output_file
        ):
            # v0.6.46 and older workflows only have legacy output fields. Their
            # live ProjectFileParameter may be connected to a destination
            # provider, so preserve that host contract rather than synthesizing
            # a new destination from the migration-only recovery view.
            return self._output_file.build_file()
        situation = str(
            getattr(
                self._output_file,
                "_situation_name",
                ProjectFileParameter.DEFAULT_SITUATION,
            )
            or ProjectFileParameter.DEFAULT_SITUATION
        )
        return ProjectFileDestination.from_situation(
            output_file,
            situation,
            node_name=self.name,
        )

    def _submission_start_is_authorized(
        self,
        *,
        require_registered: bool,
    ) -> bool:
        """Fail closed when Stop/delete wins before the billable POST starts."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return False
        if bool(getattr(self, "is_cancellation_requested", False)):
            return False
        return bool(
            not require_registered
            or self._runtime_node_is_live(require_registered=True)
        )

    async def _discard_unsent_generation_checkpoint(self, *, reason: str) -> None:
        """Clear a provisional identity after proving no create call began."""

        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["generation_status"] = ""
        self.parameter_output_values["provider_response"] = None
        self._clear_generation_recovery_checkpoint()
        if self._runtime_node_is_live(require_registered=True):
            await self._force_save_generation_recovery_checkpoint(
                required=False,
                reason=reason,
            )

    def _generation_recovery_state(self) -> dict[str, Any]:
        """Return the durable checkpoint, migrating older serialized outputs."""

        checkpoint = _seedance_recovery_value(
            self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER)
        )
        if checkpoint["task_id"]:
            return checkpoint

        generation_id = str(
            self.parameter_output_values.get("generation_id") or ""
        ).strip()
        if not generation_id or _TASK_ID_PATTERN.fullmatch(generation_id) is None:
            return checkpoint
        status = str(
            self.parameter_output_values.get("generation_status") or ""
        ).strip().lower().replace("-", "_")
        provider_response = self.parameter_output_values.get("provider_response")
        raw_model = str(
            self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
        ).strip()
        model_id = MODEL_ID_ALIASES.get(raw_model, "")
        checkpoint = _seedance_recovery_value(
            {
                "revision": 1,
                "stage": (
                    "pre_submit"
                    if status == "submitting"
                    else "terminal"
                    if status in TERMINAL_FAILURE_STATUSES
                    else "accepted"
                ),
                "task_id": generation_id,
                "task_identity": (
                    "client_request"
                    if status in {"submitting", "submission_unknown"}
                    and generation_id.startswith("hmb-")
                    else "broker_task"
                ),
                "status": status,
                "terminal": bool(
                    status in TERMINAL_FAILURE_STATUSES
                    or (
                        isinstance(provider_response, dict)
                        and provider_response.get("terminal") is True
                    )
                ),
                "updated_at_ms": int(time.time() * 1000),
                "model_id": model_id,
                "output_format": str(
                    self.get_parameter_value("output_format")
                    or DEFAULT_OUTPUT_FORMAT
                ).strip().lower(),
                "return_last_frame": bool(
                    self.get_parameter_value("return_last_frame")
                ),
                "output_file": self._current_recovery_output_file(),
            }
        )
        return checkpoint

    def _set_generation_recovery_checkpoint(
        self,
        *,
        stage: str,
        task_id: str,
        task_identity: str,
        status: str,
        params: dict[str, Any] | None = None,
        terminal: bool = False,
    ) -> dict[str, Any]:
        """Update the serializable, bounded checkpoint without emitting UI state."""

        previous = _seedance_recovery_value(
            self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER)
        )
        source_params = params if isinstance(params, dict) else {}
        raw_model = str(
            source_params.get("model_id")
            or previous.get("model_id")
            or self.get_parameter_value("model_id")
            or MODEL_NAME_SEEDANCE_2_0
        ).strip()
        model_id = MODEL_ID_ALIASES.get(raw_model, raw_model)
        raw_format = str(
            source_params.get("output_format")
            or previous.get("output_format")
            or self.get_parameter_value("output_format")
            or DEFAULT_OUTPUT_FORMAT
        ).strip().lower()
        return_last_frame = (
            bool(source_params.get("return_last_frame"))
            if "return_last_frame" in source_params
            else bool(previous.get("return_last_frame"))
            if previous.get("task_id")
            else bool(self.get_parameter_value("return_last_frame"))
        )
        # Capture the UI destination exactly once, at the durable pre-submit
        # boundary.  A successful create replaces the client request identity
        # with the Broker task ID, so task-ID equality cannot identify the same
        # render across that transition.  Every later stage therefore retains
        # the submitted destination even if the user edits the visible field.
        previous_output_file = str(previous.get("output_file") or "")
        current_output_file = self._current_recovery_output_file()
        default_output_file = str(
            getattr(self._output_file, "_default_filename", "") or ""
        ).strip()
        output_file = (
            current_output_file or default_output_file
            if stage == "pre_submit"
            else previous_output_file or current_output_file or default_output_file
        )
        checkpoint = _seedance_recovery_value(
            {
                "revision": min(
                    2_147_483_647,
                    int(previous.get("revision") or 0) + 1,
                ),
                "stage": stage,
                "task_id": task_id,
                "task_identity": task_identity,
                "status": status,
                "terminal": terminal,
                "updated_at_ms": int(time.time() * 1000),
                "model_id": model_id,
                "output_format": raw_format,
                "return_last_frame": return_last_frame,
                "output_file": output_file,
            }
        )
        self.set_parameter_value(
            SEEDANCE_RECOVERY_PARAMETER,
            checkpoint,
            emit_change=False,
        )
        self._hmb_generation_recovery_restore_fingerprint = None
        return checkpoint

    def _clear_generation_recovery_checkpoint(self) -> None:
        self.set_parameter_value(
            SEEDANCE_RECOVERY_PARAMETER,
            _seedance_recovery_value(),
            emit_change=False,
        )
        self._hmb_generation_recovery_restore_fingerprint = None

    async def _force_save_generation_recovery_checkpoint(
        self,
        *,
        required: bool,
        reason: str,
    ) -> bool:
        """Persist the current workflow, serializing all five nodes in order.

        A pre-submit save is fail-closed: no successful save means no billable
        POST. Once the Broker has accepted a request, bounded retries are best
        effort because the earlier client-request checkpoint is already safe.
        """

        checkpoint = self._generation_recovery_state()
        if not checkpoint["task_id"] and required:
            raise RuntimeError(
                "Seedance recovery checkpoint has no valid task identity. "
                "No render was submitted."
            )

        failure: Exception | None = None
        attempts = 1 if required else 3
        for attempt in range(1, attempts + 1):
            try:
                from griptape_nodes.retained_mode.events.workflow_events import (
                    SaveWorkflowRequest,
                    SaveWorkflowResultSuccess,
                )

                async with _workflow_checkpoint_lock():
                    context_factory = getattr(GriptapeNodes, "ContextManager", None)
                    request_handler = getattr(GriptapeNodes, "ahandle_request", None)
                    if not callable(context_factory) or not callable(request_handler):
                        raise RuntimeError("The host workflow save API is unavailable.")
                    context = context_factory()
                    if not context.has_current_workflow():
                        raise RuntimeError("There is no active workflow to save.")
                    current_name = str(context.get_current_workflow_name() or "")
                    if not current_name:
                        raise RuntimeError("The active workflow identity is missing.")
                    first_save = current_name.startswith("unsaved:")
                    result = await request_handler(
                        SaveWorkflowRequest(
                            file_name=None if first_save else current_name,
                            broadcast_result=first_save,
                            create_versioned=False,
                            overwrite_existing=True,
                        )
                    )
                    if not isinstance(result, SaveWorkflowResultSuccess):
                        raise RuntimeError("The host rejected the workflow save.")
                self._hmb_last_saved_recovery_revision = int(
                    checkpoint.get("revision") or 0
                )
                return True
            except Exception as exc:
                failure = exc
                if attempt < attempts:
                    await asyncio.sleep(0.05 * attempt)

        logger.warning(
            "%s could not persist Seedance recovery checkpoint %s (%s; %s).",
            self.name,
            checkpoint["task_id"],
            reason,
            type(failure).__name__ if failure is not None else "UnknownError",
        )
        if required:
            raise RuntimeError(
                "Seedance recovery checkpoint could not be saved. "
                "No render was submitted. Save the workflow and try again."
            ) from failure
        return False

    @staticmethod
    def _generation_artifact_is_present(value: Any) -> bool:
        if value is None:
            return False
        location = getattr(value, "value", value)
        return bool(str(location or "").strip())

    @staticmethod
    def _generation_artifact_is_locally_available(value: Any) -> bool:
        if value is None:
            return False
        location = getattr(value, "value", value)
        text = str(location or "").strip()
        if not text:
            return False
        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"}:
            return True
        try:
            resolved = File(text).resolve()
            resolved_text = str(
                getattr(resolved, "location", getattr(resolved, "value", resolved))
                or ""
            ).strip()
        except Exception:
            resolved_text = text
        return bool(resolved_text and Path(resolved_text).is_file())

    def _capture_last_success_video(self) -> VideoUrlArtifact | None:
        """Keep the last complete preview visible while another task runs."""

        current = self.parameter_output_values.get("video_url")
        if self._generation_artifact_is_present(current):
            self._hmb_last_success_video = current
            current_frame = self.parameter_output_values.get("last_frame_url")
            self._hmb_last_success_last_frame_url = (
                current_frame
                if isinstance(current_frame, ImageUrlArtifact)
                else None
            )
        return self._hmb_last_success_video

    def _begin_generation_preview(self) -> None:
        self._capture_last_success_video()
        self._hmb_generation_started_monotonic = self._monotonic()
        self._hmb_generation_started_at_ms = int(time.time() * 1000)
        self._publish_generation_preview(
            "preparing",
            generation_id="",
            action="none",
        )

    @staticmethod
    def _generation_preview_phase_for_status(status: Any) -> str:
        normalized = str(status or "").strip().lower().replace("-", "_")
        if normalized in LOCAL_PRE_SUBMISSION_STATUSES or normalized in {
            "connecting_broker",
            "preparing_media",
        }:
            return "preparing"
        if normalized == "submitting":
            return "submitting"
        if normalized in {"queued", "resuming"}:
            return "queued"
        if normalized == "running":
            return "running"
        if normalized == "retrieving":
            return "retrieving"
        if normalized == "succeeded":
            # A completed remote job is not a usable preview until its MP4 has
            # been downloaded, decode-verified, and atomically published.
            return "downloading"
        if normalized == "cancelled_locally":
            return "cancelled_locally"
        if normalized == "timed_out":
            return "timed_out"
        if normalized == "submission_unknown":
            return "submission_unknown"
        if normalized in TERMINAL_FAILURE_STATUSES or normalized in {
            "failed",
            "result_failed",
        }:
            return "failed"
        return "idle"

    def _publish_generation_preview(
        self,
        phase: str,
        *,
        generation_id: str | None = None,
        action: str = "none",
        has_existing_video: bool | None = None,
    ) -> None:
        """Publish one authoritative, bounded state to the custom widget."""

        if getattr(self, "_hmb_node_deleted", False):
            return
        job_id = (
            str(generation_id).strip()
            if generation_id is not None
            else str(self.parameter_output_values.get("generation_id") or "").strip()
        )
        started_monotonic = self._hmb_generation_started_monotonic
        elapsed_seconds = 0
        if started_monotonic is not None:
            elapsed_seconds = max(
                0,
                int(self._monotonic() - started_monotonic),
            )
        state = _seedance_generation_preview_value(
            {
                "phase": phase,
                "job_id": job_id,
                "started_at_ms": self._hmb_generation_started_at_ms,
                "elapsed_seconds": elapsed_seconds,
                "action": action,
                "has_existing_video": (
                    self._generation_artifact_is_present(
                        self._capture_last_success_video()
                    )
                    if has_existing_video is None
                    else bool(has_existing_video)
                ),
                "media_revision": self._hmb_generation_media_revision,
            }
        )
        self._hmb_generation_preview_state = state
        self._sync_seedance_shot_widget(emit_change=True)

    def _restore_generation_recovery_preview(self) -> None:
        """Recreate only the same-task UI action after workflow hydration."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        checkpoint = self._generation_recovery_state()
        generation_id = str(checkpoint.get("task_id") or "").strip()
        current_video = self.parameter_output_values.get(
            "video_url"
        ) or self.parameter_output_values.get("VIDEO_OUT")
        video_present = self._generation_artifact_is_locally_available(
            current_video
        )
        if not generation_id:
            fingerprint = ("idle", "", video_present)
            if self._hmb_generation_recovery_restore_fingerprint == fingerprint:
                return
            self._hmb_generation_started_monotonic = None
            self._hmb_generation_started_at_ms = 0
            self._publish_generation_preview(
                "idle",
                generation_id="",
                action="none",
                has_existing_video=video_present,
            )
            self._hmb_generation_recovery_restore_fingerprint = fingerprint
            return

        status = str(checkpoint.get("status") or "").strip().lower()
        provider_response = self.parameter_output_values.get("provider_response")
        terminal = bool(
            checkpoint.get("terminal") is True
            or status in TERMINAL_FAILURE_STATUSES
            or (
                isinstance(provider_response, dict)
                and provider_response.get("terminal") is True
            )
        )
        if status == "submitting":
            restored_status = "submission_unknown"
            phase = "submission_unknown"
            action = "refresh_existing"
        elif status in {"pending", "queued", "submitted", "resuming"}:
            restored_status = "queued" if status != "resuming" else "resuming"
            phase = "queued"
            action = "refresh_existing"
        elif status in {"running", "processing", "in_progress"}:
            restored_status = "running"
            phase = "running"
            action = "refresh_existing"
        elif status in {
            "retrieving",
            "downloading",
            "verifying",
            "cancelled_locally",
            "timed_out",
            "submission_unknown",
        }:
            restored_status = status
            phase = (
                status
                if status in GENERATION_PREVIEW_PHASES
                else "submission_unknown"
            )
            # A local crash during retrieval/publication still recovers the
            # exact server task; no create endpoint is reachable from this UI.
            if phase in {"retrieving", "downloading", "verifying"}:
                phase = "submission_unknown"
            action = "refresh_existing"
        elif terminal:
            restored_status = status or "failed"
            phase = "failed"
            action = "none"
        elif status in BROKER_SUCCESS_STATUSES or status == "succeeded":
            restored_status = "succeeded"
            phase = "succeeded" if video_present else "failed"
            action = "none" if video_present else "refresh_existing"
        else:
            restored_status = status or "submission_unknown"
            phase = "failed"
            action = "refresh_existing"

        fingerprint = (
            generation_id,
            restored_status,
            terminal,
            video_present,
            int(checkpoint.get("revision") or 0),
        )
        if self._hmb_generation_recovery_restore_fingerprint == fingerprint:
            return
        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["generation_status"] = restored_status
        if isinstance(provider_response, dict) and str(
            provider_response.get("id") or ""
        ).strip() == generation_id:
            restored_response = dict(provider_response)
            restored_response["status"] = restored_status
            if terminal:
                restored_response["terminal"] = True
            self.parameter_output_values["provider_response"] = restored_response
        else:
            self.parameter_output_values["provider_response"] = {
                "transport": "fn_ai_broker",
                "id": generation_id,
                "status": restored_status,
                **({"terminal": True} if terminal else {}),
            }
        if video_present:
            self._hmb_last_success_video = current_video
        persisted_checkpoint = _seedance_recovery_value(
            self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER)
        )
        if not persisted_checkpoint["task_id"]:
            # In-memory migration for v0.6.46 workflows whose serialized output
            # fields predate the dedicated recovery checkpoint.
            self.set_parameter_value(
                SEEDANCE_RECOVERY_PARAMETER,
                checkpoint,
                emit_change=False,
            )
        self._hmb_generation_started_monotonic = None
        self._publish_generation_preview(
            phase,
            generation_id=generation_id,
            action=action,
            has_existing_video=video_present,
        )
        self._hmb_generation_recovery_restore_fingerprint = fingerprint

    def _generation_recovery_blocks_new_submission(self) -> bool:
        checkpoint = self._generation_recovery_state()
        if not checkpoint["task_id"]:
            return False
        status = str(checkpoint.get("status") or "").strip().lower()
        stage = str(checkpoint.get("stage") or "").strip().lower()
        provider_response = self.parameter_output_values.get("provider_response")
        terminal = bool(
            checkpoint.get("terminal") is True
            or status in TERMINAL_FAILURE_STATUSES
            or (
                isinstance(provider_response, dict)
                and provider_response.get("terminal") is True
            )
        )
        if terminal:
            return False
        if status in BROKER_SUCCESS_STATUSES or status == "succeeded":
            # ``local_succeeded`` is persisted only after the remote result was
            # downloaded, decoded, verified, atomically published, and exposed
            # as this node's output.  Griptape does not reliably serialize the
            # video artifact outputs, so a reopened node must use this durable
            # checkpoint as the authoritative consumed-result signal.  Keep the
            # task ID for audit/recovery history; the next explicit Run replaces
            # it with the new pre-submit checkpoint.
            if stage == "local_succeeded":
                # Do not re-check provider_response/video_url here.  Griptape
                # can hydrate the hidden recovery property before output
                # parameters during StartFlow, which made a genuinely consumed
                # result look unconfirmed and permanently blocked re-rendering.
                # Identity is historical metadata; ``local_succeeded`` is the
                # durable backend-authored proof and is written only after the
                # result has passed local publication verification.
                return False

            # A remote success is not yet safe to retire: the visible local
            # artifact can belong to an earlier render.  Only stage-less legacy
            # checkpoints retain the pre-v0.6.48 artifact compatibility path.
            if stage:
                return True
            current_video = self.parameter_output_values.get(
                "video_url"
            ) or self.parameter_output_values.get("VIDEO_OUT")
            return not self._generation_artifact_is_locally_available(
                current_video
            )
        return True

    def _assert_new_submission_is_safe(self) -> None:
        if not self._generation_recovery_blocks_new_submission():
            return
        checkpoint = self._generation_recovery_state()
        self._restore_generation_recovery_preview()
        raise RuntimeError(
            "A previously submitted Seedance task still requires confirmation. "
            f"Task ID: {checkpoint['task_id']}. Use the central Existing Task "
            "Result button; a replacement render was not submitted."
        )

    def _request_existing_generation_refresh(self) -> None:
        """Accept one browser pulse without accepting any browser task ID."""

        preview = _seedance_generation_preview_value(
            self._hmb_generation_preview_state
        )
        authoritative_id = str(
            self.parameter_output_values.get("generation_id") or ""
        ).strip()
        if (
            preview["action"] != "refresh_existing"
            or not authoritative_id
            or preview["job_id"] != authoritative_id
            or self._generation_run_active.is_set()
        ):
            return
        try:
            self._validate_task_id(authoritative_id)
        except _BrokerProtocolError:
            return
        self._on_refresh_clicked(None, None)

    def _schedule_existing_generation_refresh(self) -> None:
        """Launch an overlay refresh after the current value-set request returns."""

        def launch() -> None:
            if bool(getattr(self, "_hmb_node_deleted", False)):
                return
            self._request_existing_generation_refresh()

        try:
            event_loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if event_loop is not None and event_loop.is_running():
                # after_value_set runs inside the retained-mode request. Queue
                # the action for the next loop turn so refresh publication
                # cannot re-enter and stall that same synchronous transaction.
                event_loop.call_soon_threadsafe(launch)
                return
        except Exception:
            pass

        # Headless/compatibility hosts may not expose a running engine loop.
        # Keep their value-set callback non-blocking as well.
        threading.Thread(
            target=launch,
            name=f"{self.name}-refresh-dispatch",
            daemon=True,
        ).start()

    def _sync_seedance_shot_widget(self, *, emit_change: bool = False) -> None:
        parameter = self.get_parameter_by_name(SEEDANCE_SHOT_WIDGET_PARAMETER)
        if parameter is None:
            return
        identity = self._shot_identity()
        available_catalog = self._hmb_available_seedance_shot_catalog(
            self._hmb_shot_catalog_snapshot
        )
        next_value = _seedance_widget_value(
            {
                "channel_uuid": identity["channel_uuid"],
                "shot_uuid": identity["shot_uuid"],
            },
            available_catalog,
            self._hmb_generation_preview_state,
            getattr(self, "_hmb_remote_prompt_route", None),
        )
        try:
            current = self.get_parameter_value(SEEDANCE_SHOT_WIDGET_PARAMETER)
        except Exception:
            current = getattr(parameter, "default_value", None)
        parameter.default_value = deepcopy(next_value)
        last_published = getattr(
            self,
            "_hmb_last_published_seedance_shot_widget",
            None,
        )
        needs_explicit_publish = bool(
            emit_change
            and (
                not hasattr(
                    self,
                    "_hmb_last_published_seedance_shot_widget",
                )
                or last_published != next_value
            )
        )
        if current == next_value and not needs_explicit_publish:
            return
        self._hmb_shot_syncing = True
        try:
            if current != next_value:
                self._set_shot_value(
                    SEEDANCE_SHOT_WIDGET_PARAMETER,
                    next_value,
                    # Runtime preview publication has one authority path.
                    # Calling set_parameter_value(..., emit_change=True) and
                    # then the explicit publisher duplicated the same retained-
                    # mode update, amplifying React/WebSocket work.
                    emit_change=False,
                )
            if needs_explicit_publish:
                # One explicit value event is sufficient for runtime progress;
                # lifecycle invalidation here would duplicate the same state
                # and can cascade through every selected React node.
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    publisher(SEEDANCE_SHOT_WIDGET_PARAMETER, next_value)
                    self._hmb_last_published_seedance_shot_widget = deepcopy(
                        next_value
                    )
        finally:
            self._hmb_shot_syncing = False

    def _apply_seedance_shot_selection(
        self,
        requested_shot_uuid: Any,
        *,
        fallback_to_available: bool = True,
    ) -> None:
        previous_identity = self._shot_identity()
        requested = self._shot_uuid(requested_shot_uuid)
        snapshot = self._hmb_shot_catalog_snapshot
        available_snapshot = self._hmb_available_seedance_shot_catalog(snapshot)
        available_shots = (
            available_snapshot.get("shots", [])
            if isinstance(available_snapshot, dict)
            else []
        )
        selected = None
        if requested and isinstance(snapshot, dict):
            selected = next(
                (
                    item for item in available_shots
                    if isinstance(item, dict) and item.get("shot_uuid") == requested
                ),
                None,
            )
        if selected is None and fallback_to_available and isinstance(snapshot, dict):
            current_uuid = previous_identity.get("shot_uuid")
            selected = next(
                (
                    item for item in available_shots
                    if isinstance(item, dict)
                    and item.get("shot_uuid") == current_uuid
                ),
                None,
            )
        if selected is None and fallback_to_available and isinstance(snapshot, dict):
            selected = next(
                (
                    item for item in available_shots
                    if isinstance(item, dict) and item.get("shot_uuid")
                ),
                None,
            )
        self._hmb_shot_syncing = True
        try:
            if isinstance(selected, dict) and isinstance(snapshot, dict):
                label = next(
                    (
                        label for label, item in self._hmb_shot_selector_map.items()
                        if item.get("shot_uuid") == selected["shot_uuid"]
                    ),
                    SHOT_ONLY_LABEL,
                )
                self._set_shot_value(SHOT_CHANNEL_UUID_PARAMETER, snapshot["channel_uuid"])
                self._set_shot_value(SHOT_UUID_PARAMETER, selected["shot_uuid"])
                self._set_shot_value(SHOT_NUMBER_PARAMETER, selected["number"])
                self._set_shot_value(SHOT_NAME_PARAMETER, selected["name"])
                self._set_shot_value(SHOT_SELECTOR_PARAMETER, label)
            else:
                self._set_shot_value(SHOT_CHANNEL_UUID_PARAMETER, "")
                self._set_shot_value(SHOT_UUID_PARAMETER, "")
                self._set_shot_value(SHOT_NUMBER_PARAMETER, 0)
                self._set_shot_value(SHOT_NAME_PARAMETER, "")
                self._set_shot_value(SHOT_SELECTOR_PARAMETER, SHOT_ONLY_LABEL)
        finally:
            self._hmb_shot_syncing = False
        # Five concurrent Shot generators must never publish into the same
        # legacy default path. Only HMB-managed defaults are renamed; explicit
        # output destinations and connected FileOutputSettings remain owned by
        # the user/workflow.
        self._sync_shot_output_filenames()
        # Mutate silently here. The router's final status pass publishes one
        # complete widget state after any Agent route has also been pre-armed.
        # _sync_seedance_shot_widget remembers explicit publications, so an
        # equal backend value still reaches a newly mounted React widget once.
        self._sync_seedance_shot_widget()

    def _shot_identity(self) -> dict[str, Any]:
        channel = self._shot_uuid(self.get_parameter_value(SHOT_CHANNEL_UUID_PARAMETER))
        shot_uuid = self._shot_uuid(self.get_parameter_value(SHOT_UUID_PARAMETER))
        bound = bool(channel and shot_uuid)
        try:
            number = int(self.get_parameter_value(SHOT_NUMBER_PARAMETER) or 1)
        except (TypeError, ValueError, OverflowError):
            number = 1
        number = max(1, min(SHOT_ROUTING_MAX_SHOTS, number))
        name = (
            str(
                self.get_parameter_value(SHOT_NAME_PARAMETER) or f"Shot {number}"
            ).strip()[:128]
            or f"Shot {number}"
        ) if bound else SHOT_ONLY_LABEL
        return {
            "channel_uuid": channel if bound else "",
            "shot_uuid": shot_uuid if bound else "",
            "shot_number": number if bound else 1,
            "shot_name": name if bound else SHOT_ONLY_LABEL,
        }

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        identity = self._shot_identity()
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": "seedance",
            "enabled": bool(identity["channel_uuid"] and identity["shot_uuid"]),
            **identity,
        }

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if isinstance(value, dict):
            self._hmb_shot_route_status = deepcopy(value)
            current_route = _seedance_remote_prompt_route_value(
                getattr(self, "_hmb_remote_prompt_route", None)
            )
            discovered_route = self._current_remote_prompt_route()
            if discovered_route["connected"]:
                self._hmb_remote_prompt_route = (
                    _merge_seedance_remote_prompt_route_aliases(
                        current_route,
                        discovered_route,
                    )
                )
            elif (
                value.get("ok") is True
                and value.get("code") == "ready"
                and current_route["connected"]
                and self._shot_identity()["shot_uuid"]
            ):
                # A reset replacement can briefly be undiscoverable between
                # its temporary and final names. Keep the already-proven,
                # pre-armed descriptor for that one ready Shot; a real
                # disconnect/Only transition still clears it below.
                self._hmb_remote_prompt_route = current_route
            else:
                self._hmb_remote_prompt_route = discovered_route
            self._sync_seedance_shot_widget(emit_change=True)

    def _hmb_prepare_remote_prompt_route(self, source_node: Any) -> bool:
        """Pre-arm exact old/new edge hiding before retained-mode mutation.

        The real graph edge remains execution authority. This bounded UI-only
        descriptor is published first so neither the initial connection nor a
        Shot A -> B replacement can paint a transient cable.
        """

        identity = self._shot_identity()
        subscription_getter = getattr(
            source_node,
            "_hmb_shot_channel_subscription",
            None,
        )
        try:
            subscription = (
                subscription_getter()
                if callable(subscription_getter)
                else None
            )
        except Exception:
            return False
        if (
            not identity["channel_uuid"]
            or not identity["shot_uuid"]
            or not isinstance(subscription, dict)
            or subscription.get("participant_kind") != "agent"
            or subscription.get("enabled") is not True
            or self._shot_uuid(subscription.get("channel_uuid"))
            != identity["channel_uuid"]
            or self._shot_uuid(subscription.get("shot_uuid"))
            != identity["shot_uuid"]
            or subscription.get("shot_number") != identity["shot_number"]
            or subscription.get("shot_name") != identity["shot_name"]
        ):
            return False
        current = _seedance_remote_prompt_route_value(
            getattr(self, "_hmb_remote_prompt_route", None)
        )
        next_source_name = str(getattr(source_node, "name", ""))
        prepared = _merge_seedance_remote_prompt_route_aliases(
            current,
            {
                "connected": True,
                "source_node_name": next_source_name,
                "target_node_name": str(getattr(self, "name", "")),
            },
        )
        if not prepared["connected"]:
            return False
        if prepared != current:
            self._hmb_remote_prompt_route = prepared
            self._sync_seedance_shot_widget(emit_change=True)
        return True

    def _current_remote_prompt_route(self) -> dict[str, Any]:
        """Describe one proven same-Shot public Agent prompt connection."""

        disconnected = _seedance_remote_prompt_route_value()
        identity = self._shot_identity()
        if not identity["channel_uuid"] or not identity["shot_uuid"]:
            return disconnected
        try:
            source_node = self._manual_agent_prompt_source()
        except Exception:
            # UI decoration is fail-visible. Runtime prompt text is accepted
            # independently; direct Shot media retains its own strict proof.
            return disconnected
        if source_node is None:
            return disconnected
        subscription_getter = getattr(
            source_node,
            "_hmb_shot_channel_subscription",
            None,
        )
        try:
            subscription = (
                subscription_getter()
                if callable(subscription_getter)
                else None
            )
        except Exception:
            return disconnected
        if (
            not isinstance(subscription, dict)
            or subscription.get("participant_kind") != "agent"
            or subscription.get("enabled") is not True
            or self._shot_uuid(subscription.get("channel_uuid"))
            != identity["channel_uuid"]
            or self._shot_uuid(subscription.get("shot_uuid"))
            != identity["shot_uuid"]
            or subscription.get("shot_number") != identity["shot_number"]
            or subscription.get("shot_name") != identity["shot_name"]
        ):
            return disconnected
        return _seedance_remote_prompt_route_value(
            {
                "connected": True,
                "source_node_name": str(getattr(source_node, "name", "")),
                "target_node_name": str(getattr(self, "name", "")),
            }
        )

    def _hmb_reconcile_shot_routing(self, routing_snapshot: Any) -> None:
        snapshot = self._validate_shot_catalog_snapshot(routing_snapshot)
        identity = self._shot_identity()
        if identity["channel_uuid"] and identity["channel_uuid"] != snapshot["channel_uuid"]:
            raise RuntimeError("Seedance Shot channel does not match the ImageAsset publisher.")
        previous = self._hmb_shot_catalog_snapshot
        if isinstance(previous, dict) and previous.get("channel_uuid") == snapshot["channel_uuid"]:
            previous_generation = int(previous.get("generation") or 0)
            if snapshot["generation"] < previous_generation:
                raise RuntimeError("Seedance Shot catalog generation moved backwards.")
            if snapshot["generation"] == previous_generation and (
                snapshot["metadata_sha256"] != previous.get("metadata_sha256")
            ):
                raise RuntimeError("Seedance Shot catalog changed without a new generation.")
        selected = next(
            (item for item in snapshot["shots"] if item["shot_uuid"] == identity["shot_uuid"]),
            None,
        )
        self._hmb_shot_catalog_snapshot = snapshot
        self._hmb_shot_catalog_generation = snapshot["generation"]
        available_snapshot = self._hmb_available_seedance_shot_catalog(snapshot)
        available_shots = (
            available_snapshot.get("shots", [])
            if isinstance(available_snapshot, dict)
            else []
        )
        if isinstance(selected, dict) and selected not in available_shots:
            selected = None
        labels: list[str] = []
        selector_map: dict[str, dict[str, Any]] = {}
        for item in available_shots:
            label = f"{item['number']:02d} · {item['name']}"
            labels.append(label)
            selector_map[label] = item
        self._set_seedance_shot_choices(labels)
        self._hmb_shot_selector_map = selector_map
        # A fresh node auto-adopts Shot 1.  Once the user explicitly chooses
        # Only, later catalog refreshes must preserve that independent mode.
        # Existing UUIDs retain authority across rename/renumber.  A deleted
        # UUID must never silently become another Shot merely because that Shot
        # inherited its display number; only a fresh, still-auto-claiming node
        # may adopt the first available UUID.
        fallback_to_available = bool(
            not identity.get("shot_uuid")
            and self.get_parameter_value(SHOT_AUTOCLAIM_ENABLED_PARAMETER)
        )
        self._apply_seedance_shot_selection(
            selected["shot_uuid"] if isinstance(selected, dict) else "",
            fallback_to_available=fallback_to_available,
        )
        self._hmb_shot_route_status = {
            "schema": "hmb-shot-routing-status",
            "version": 1,
            "ok": True,
            "code": (
                "catalog_ready"
                if self._hmb_shot_channel_subscription()["enabled"]
                else "remote_waiting"
            ),
            "details": "",
        }

    def _hmb_reconcile_replacement_shot_routing(
        self,
        routing_snapshot: Any,
    ) -> None:
        """Adopt one router-proven replacement for an orphaned Image channel.

        The ordinary catalog callback deliberately rejects channel changes.
        The central reconciler calls this narrower entry point only after it has
        proven that the saved channel is absent, exactly one new Image publisher
        is active, and all old managed edges have been removed.
        """

        snapshot = self._validate_shot_catalog_snapshot(routing_snapshot)
        identity = self._shot_identity()
        if (
            not identity["channel_uuid"]
            or identity["channel_uuid"] == snapshot["channel_uuid"]
        ):
            self._hmb_reconcile_shot_routing(snapshot)
            return
        # Validation happens before mutation. Once the central reconciler has
        # established orphan replacement, discard only remote authority and the
        # obsolete quartet, then let the strict callback adopt the new first Shot.
        self._hmb_clear_shot_routing_catalog("channel_replaced")
        self._hmb_reconcile_shot_routing(snapshot)

    def _hmb_clear_shot_routing_catalog(
        self,
        reason: str = "publisher_unavailable",
    ) -> dict[str, Any]:
        """Clear remote authority without touching standalone generation inputs."""

        self._hmb_shot_catalog_snapshot = None
        self._hmb_shot_catalog_generation = 0
        self._hmb_shot_selector_map = {}
        self._set_seedance_shot_choices([])
        self._apply_seedance_shot_selection("", fallback_to_available=False)
        self._hmb_shot_route_status = {
            "schema": "hmb-shot-routing-status",
            "version": 1,
            "ok": False,
            "code": "remote_waiting",
            "details": str(reason or "publisher_unavailable").strip()[:128],
        }
        return self._hmb_shot_channel_subscription()

    def _hmb_reject_duplicate_shot_selection(
        self,
        reason: str = "duplicate_seedance_shot",
    ) -> dict[str, Any]:
        """Fail a duplicate claim closed by returning this generator to Only."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()
        self._set_hidden_control_value(
            SHOT_AUTOCLAIM_ENABLED_PARAMETER,
            False,
        )
        self._apply_seedance_shot_selection(
            "",
            fallback_to_available=False,
        )
        self._hmb_shot_route_status = {
            "schema": "hmb-shot-routing-status",
            "version": 1,
            "ok": False,
            "code": str(reason or "duplicate_seedance_shot").strip()[:128],
            "details": "Duplicate Shot ownership was rejected; Only mode is active.",
        }
        return self._hmb_shot_channel_subscription()

    def _reconcile_shared_shot_routing(self, *, strict: bool = False) -> dict[str, Any]:
        if self._hmb_shared_routing_in_progress:
            return {"ok": True, "code": "reentrant", "changed": 0}
        initial_enabled = bool(self._hmb_shot_channel_subscription()["enabled"])
        self._hmb_shared_routing_in_progress = True
        try:
            result = _shot_routing.reconcile_shot_routing(self)
            if not initial_enabled and self._hmb_shot_channel_subscription()["enabled"]:
                result = _shot_routing.reconcile_shot_routing(self)
        finally:
            self._hmb_shared_routing_in_progress = False
        if strict and self._hmb_shot_channel_subscription()["enabled"]:
            if not isinstance(result, dict):
                raise RuntimeError("Seedance Shot routing result is invalid.")
            prefix = str(getattr(self, "name", "") or "") + ":"
            failures = result.get("failures")
            own_failures = [
                str(item)
                for item in (failures if isinstance(failures, (list, tuple)) else ())
                if str(item).startswith(prefix)
            ]
            if own_failures:
                raise RuntimeError("Seedance Shot routing is incomplete or ambiguous.")
            status = self._hmb_shot_route_status
            if isinstance(status, dict) and status and not bool(status.get("ok", True)):
                raise RuntimeError("Seedance Shot routing is incomplete or ambiguous.")
        return result if isinstance(result, dict) else {
            "ok": False,
            "code": "invalid_result",
            "changed": 0,
        }

    def _hmb_post_registration_shot_discovery(self) -> None:
        """Adopt an already-hydrated Shot/Agent chain after node registration.

        Registration order is not guaranteed by the host.  A newly dragged or
        recreated Seedance node therefore performs one authoritative same-flow
        discovery pass instead of waiting for another ImageAsset/Prompt/Agent
        edit event before discovering its exact hidden Shot connections.
        """

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        try:
            self._reconcile_shared_shot_routing()
        finally:
            self._restore_generation_recovery_preview()

    def _hmb_post_hydration_state_restore(self) -> None:
        """Restore durable preview state after the newest serialized replay."""

        self._restore_generation_recovery_preview()

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Intercept retired/unknown model values before Options coercion.

        Griptape's Options converter replaces an out-of-list saved value with
        the first choice before node callbacks run. Inspecting the raw value at
        this boundary is therefore required both to migrate retired Mini
        workflows and to prevent an unknown model from silently becoming Full.
        """

        if param_name == SEEDANCE_RECOVERY_PARAMETER:
            value = _seedance_recovery_value(value)
        elif param_name == SHOT_PICKER_INPUT_PARAMETER:
            if isinstance(value, dict):
                value = deepcopy(value)
            elif isinstance(value, str):
                text = value.strip()
                parsed_value: Any = {}
                if (
                    text
                    and len(text) <= SHOT_PICKER_LEGACY_JSON_MAX_BYTES
                    and len(text.encode("utf-8", errors="ignore"))
                    <= SHOT_PICKER_LEGACY_JSON_MAX_BYTES
                ):
                    with suppress(TypeError, ValueError):
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            parsed_value = deepcopy(parsed)
                value = parsed_value
            else:
                value = {}

        previous_model_id = ""
        if param_name == "model_id":
            previous_model_raw = str(
                self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
            ).strip()
            previous_model_id = MODEL_ID_ALIASES.get(
                previous_model_raw,
                previous_model_raw,
            )
            raw_model = str(value or "").strip()
            if raw_model in RETIRED_SEEDANCE_MODEL_VALUES:
                self._hmb_retired_model_migration_pending = True
                value = MODEL_NAME_SEEDANCE_2_0
            elif raw_model not in MODEL_ID_ALIASES:
                raise ValueError(
                    f"Unsupported Volcengine Seedance model: {raw_model!r}."
                )
            else:
                value = MODEL_DISPLAY_NAME_BY_ID[MODEL_ID_ALIASES[raw_model]]
        elif param_name == TASK_PARAMETER:
            raw_task = str(value or "").strip()
            if raw_task not in TASK_STORAGE_CHOICES:
                raise ValueError(f"Unsupported Seedance task: {raw_task!r}.")
            # Task can arrive before model_id during saved-workflow hydration
            # or connected-input delivery. Keep the converter permissive until
            # both values are known, then narrow/fallback deterministically.
            task_parameter = self.get_parameter_by_name(TASK_PARAMETER)
            if task_parameter is not None:
                task_parameter.ui_options = {
                    **task_parameter.ui_options,
                    "simple_dropdown": list(TASK_STORAGE_CHOICES),
                }
            value = raw_task
        elif param_name == "output_format":
            raw_format = str(value or "").strip().lower()
            if raw_format not in OUTPUT_FORMAT_CHOICES:
                raise ValueError(
                    f"Unsupported Seedance output format: {raw_format!r}."
                )
            output_parameter = self.get_parameter_by_name("output_format")
            if output_parameter is not None:
                output_parameter.ui_options = {
                    **output_parameter.ui_options,
                    "simple_dropdown": list(OUTPUT_FORMAT_CHOICES),
                }
            value = raw_format
        elif param_name == "duration":
            # Griptape's Options converter reads ``simple_dropdown`` as the
            # accepted value set. Use the 2.5 superset while storing the raw
            # value so duration=16..30 survives serialized hydration and a
            # connected duration value that arrives before its paired model.
            # Runtime delivery narrows the UI immediately; duration-first
            # hydration narrows when its serialized model value arrives.
            duration_parameter = self.get_parameter_by_name("duration")
            if duration_parameter is not None:
                duration_parameter.ui_options = {
                    **duration_parameter.ui_options,
                    "simple_dropdown": list(
                        DURATION_STORAGE_CHOICES
                    ),
                }

        authority = getattr(self, "_hmb_explicit_list_authority", None)
        if authority is None:
            authority = set()
            self._hmb_explicit_list_authority = authority
        parent_container_name = ""
        with suppress(Exception):
            parameter = self.get_parameter_by_name(param_name)
            parent_container_name = str(
                getattr(parameter, "parent_container_name", "") or ""
            )
        for list_name in (
            "reference_images",
            VIDEO_REFERENCES_PARAMETER,
            "reference_audio",
        ):
            if param_name == list_name or parent_container_name == list_name:
                authority.add(list_name)

        if param_name in {
            "reference_images",
            VIDEO_REFERENCES_PARAMETER,
            "reference_audio",
        } and isinstance(value, (list, tuple)) and not bool(
            getattr(self, "_hmb_list_parent_syncing", False)
        ) and not self._has_incoming_parameter_connection(param_name):
            container = self.get_parameter_by_name(param_name)
            if isinstance(container, ParameterList):
                # ParameterList's public value is its ordered child sequence;
                # assigning the container directly otherwise stores a hidden
                # top-level cache that its getter intentionally ignores.
                values = list(value)
                container.clear_list()
                parent_setter = super().set_parameter_value
                self._hmb_list_parent_syncing = True
                try:
                    for item in values:
                        child = container.append_child_parameter()
                        parent_setter(
                            child.name,
                            item,
                            initial_setup=initial_setup,
                            emit_change=emit_change,
                            skip_before_value_set=skip_before_value_set,
                        )
                    if not values:
                        parent_setter(
                            param_name,
                            [],
                            initial_setup=initial_setup,
                            emit_change=emit_change,
                            skip_before_value_set=skip_before_value_set,
                        )
                finally:
                    self._hmb_list_parent_syncing = False
                return
        parent = super().set_parameter_value
        if param_name == "model_id" and not initial_setup:
            self._hmb_model_switch_previous_id = previous_model_id
        child_list_sync = parent_container_name in {
            "reference_images",
            VIDEO_REFERENCES_PARAMETER,
            "reference_audio",
        }
        previous_list_sync = bool(
            getattr(self, "_hmb_list_parent_syncing", False)
        )
        if child_list_sync:
            # BaseNode recomputes a ParameterList's aggregate value by calling
            # this override again after one child is set. Mark that recursive
            # parent write as an aggregate echo so it cannot clear and recreate
            # the very child whose stable identity Griptape just hydrated.
            self._hmb_list_parent_syncing = True
        try:
            parent(
                param_name,
                value,
                initial_setup=initial_setup,
                emit_change=emit_change,
                skip_before_value_set=skip_before_value_set,
            )
        finally:
            if child_list_sync:
                self._hmb_list_parent_syncing = previous_list_sync
            if param_name == "model_id" and not initial_setup:
                with suppress(AttributeError):
                    del self._hmb_model_switch_previous_id
        if param_name == "resolution" and initial_setup:
            self._hmb_resolution_initial_setup_seen = True
        if param_name == TASK_PARAMETER and initial_setup:
            self._hmb_task_initial_setup_seen = True
        if param_name == "input_mode" and initial_setup:
            self._hmb_input_mode_initial_setup_seen = True
        if param_name == "output_format" and initial_setup:
            self._hmb_output_format_initial_setup_seen = True
        if param_name == "return_last_frame" and initial_setup:
            self._hmb_return_last_frame_initial_setup_seen = True
        if param_name == "output_format" and not initial_setup:
            self._sync_output_filename(str(value))
        if param_name in {"output_file", "last_frame_file"}:
            # Serialized legacy defaults can arrive before or after the hidden
            # Shot quartet. Re-evaluate both managed names after either value
            # is hydrated; a user-authored path never matches the managed-name
            # patterns and is therefore left byte-for-byte intact.
            self._sync_shot_output_filenames()
        if param_name in {"output_format", "return_last_frame"} and (
            not initial_setup
            or bool(getattr(self, "_hmb_model_initial_setup_seen", False))
        ):
            self._synchronize_model_output_contract()
        if param_name == "duration" and not initial_setup:
            duration_parameter = self.get_parameter_by_name("duration")
            raw_model = str(
                self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
            ).strip()
            current_model_id = MODEL_ID_ALIASES.get(raw_model, raw_model)
            current_task = str(
                self.get_parameter_value(TASK_PARAMETER)
                or TASK_REFERENCE_TO_VIDEO
            )
            if (
                current_model_id == SEEDANCE_2_5_MODEL_ID
                and current_task == TASK_VIDEO_EDITING
            ):
                current_choices = (-1,)
            elif (
                current_model_id == SEEDANCE_2_5_MODEL_ID
                and current_task == TASK_VIDEO_EXTENSION
            ):
                current_choices = DURATION_STORAGE_CHOICES
            else:
                current_choices = MODEL_DURATION_CHOICES.get(current_model_id)
            if duration_parameter is not None and current_choices is not None:
                duration_parameter.ui_options = {
                    **duration_parameter.ui_options,
                    "simple_dropdown": list(current_choices),
                }
        if (
            param_name == "model_id"
            and initial_setup
            and self.get_parameter_by_name("resolution") is not None
        ):
            # ``initial_setup`` deliberately bypasses the ordinary after-value
            # callback, so synchronize the dependent controls explicitly.
            self._hmb_model_initial_setup_seen = True
            inherited_constructor_default = not bool(
                getattr(self, "_hmb_resolution_initial_setup_seen", False)
            )
            if inherited_constructor_default:
                self._hmb_model_switch_previous_id = previous_model_id
            try:
                self._synchronize_model_resolution()
            finally:
                if inherited_constructor_default:
                    with suppress(AttributeError):
                        del self._hmb_model_switch_previous_id
        elif param_name == TASK_PARAMETER and initial_setup:
            if bool(getattr(self, "_hmb_model_initial_setup_seen", False)):
                self._synchronize_model_resolution()
        elif param_name in {"output_format", "return_last_frame"} and initial_setup:
            if bool(getattr(self, "_hmb_model_initial_setup_seen", False)):
                self._synchronize_model_output_contract()
        elif param_name == "duration" and initial_setup:
            if bool(getattr(self, "_hmb_model_initial_setup_seen", False)):
                # Model-first hydration can finalize immediately. Duration-
                # first hydration remains in the permissive union until its
                # serialized model arrives and performs this same sync.
                self._synchronize_model_resolution()
        if initial_setup and param_name in {
            SHOT_CHANNEL_UUID_PARAMETER,
            SHOT_UUID_PARAMETER,
            SHOT_NUMBER_PARAMETER,
            SHOT_NAME_PARAMETER,
            SEEDANCE_RECOVERY_PARAMETER,
        }:
            self._schedule_post_hydration_shot_reconcile()

    def _schedule_post_hydration_shot_reconcile(self) -> bool:
        """Supersede constructor work after one authoritative Shot value loads."""

        scheduler = getattr(
            _shot_routing,
            "schedule_post_hydration_reconcile",
            None,
        )
        return bool(callable(scheduler) and scheduler(self))

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:
        """Reject browser-supplied catalogs and canonicalize widget Shot requests."""

        normalized = value
        if parameter.name == SEEDANCE_RECOVERY_PARAMETER:
            normalized = _seedance_recovery_value(value)
        elif parameter.name == "model_id":
            model_value = str(value or "").strip()
            if model_value in RETIRED_SEEDANCE_MODEL_VALUES:
                # Persist the migration as the active display value. Future
                # loads no longer need the compatibility path, while unknown
                # values remain untouched so validation can fail closed.
                self._hmb_retired_model_migration_pending = True
                # The retired Mini resolution happened to overlap with Full,
                # so membership validation alone cannot distinguish a stale
                # 480p/720p value from an intentional Full selection. The
                # after-value callback completes the atomic pair after the
                # canonical model value itself has been stored.
                normalized = MODEL_NAME_SEEDANCE_2_0
        elif parameter.name == SEEDANCE_REFRESH_COMMAND_PARAMETER:
            normalized = _seedance_refresh_command_value(value)
            self._hmb_pending_generation_command_id = ""
            action_id = normalized["action_id"]
            processed_ids = getattr(
                self,
                "_hmb_processed_generation_command_ids",
                set(),
            )
            preview = _seedance_generation_preview_value(
                self._hmb_generation_preview_state
            )
            authoritative_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            if (
                normalized["action"] == "refresh_existing"
                and action_id
                and action_id not in processed_ids
                and preview["action"] == "refresh_existing"
                and authoritative_id
                and preview["job_id"] == authoritative_id
                and not self._generation_run_active.is_set()
            ):
                try:
                    self._validate_task_id(authoritative_id)
                except _BrokerProtocolError:
                    pass
                else:
                    self._hmb_pending_generation_command_id = action_id
        elif parameter.name == SEEDANCE_SHOT_WIDGET_PARAMETER:
            request = value.get("request") if isinstance(value, dict) else None
            action_only = bool(
                isinstance(request, dict)
                and set(request) == {"action"}
                and request.get("action") == "refresh_existing"
            )
            if action_only:
                self._hmb_generation_action_only_update = True
                preview = _seedance_generation_preview_value(
                    self._hmb_generation_preview_state
                )
                authoritative_id = str(
                    self.parameter_output_values.get("generation_id") or ""
                ).strip()
                self._hmb_pending_generation_action = bool(
                    preview["action"] == "refresh_existing"
                    and authoritative_id
                    and preview["job_id"] == authoritative_id
                )
                identity = self._shot_identity()
                requested_shot = {
                    "channel_uuid": identity["channel_uuid"],
                    "shot_uuid": identity["shot_uuid"],
                }
                current_widget = self.get_parameter_value(
                    SEEDANCE_SHOT_WIDGET_PARAMETER
                )
                stored_catalog = (
                    current_widget.get("shot_catalog")
                    if isinstance(current_widget, dict)
                    else None
                )
                normalized_stored_catalog = _seedance_widget_catalog(stored_catalog)
                stored_has_current_shot = bool(
                    normalized_stored_catalog
                    and any(
                        item.get("shot_uuid") == identity["shot_uuid"]
                        for item in normalized_stored_catalog["shots"]
                    )
                )
                authoritative_catalog = (
                    normalized_stored_catalog
                    if stored_has_current_shot
                    else self._hmb_available_seedance_shot_catalog(
                        self._hmb_shot_catalog_snapshot
                    )
                )
            else:
                requested_shot = value.get("shot") if isinstance(value, dict) else None
                authoritative_catalog = self._hmb_available_seedance_shot_catalog(
                    self._hmb_shot_catalog_snapshot
                )
            normalized = _seedance_widget_value(
                requested_shot,
                authoritative_catalog,
                self._hmb_generation_preview_state,
                getattr(self, "_hmb_remote_prompt_route", None),
            )
        parent = getattr(super(), "before_value_set", None)
        if callable(parent):
            parent_value = parent(parameter, normalized)
            if parent_value is not None:
                normalized = parent_value
        return normalized

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Mirror Standard Seedance media visibility for the selected mode."""
        if parameter.name == "model_id" and self._hmb_retired_model_migration_pending:
            resolution_parameter = self.get_parameter_by_name("resolution")
            if resolution_parameter is not None:
                resolution_parameter.ui_options = {
                    **resolution_parameter.ui_options,
                    "simple_dropdown": list(MODEL_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID]),
                }
            self.set_parameter_value(
                "resolution",
                MODEL_DEFAULT_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID],
            )
            self._hmb_retired_model_migration_pending = False
        if (
            parameter.name == "input_mode"
            and not self._hmb_input_mode_syncing
            and not self._hmb_task_syncing
        ):
            raw_model = str(
                self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
            ).strip()
            active_model = MODEL_ID_ALIASES.get(raw_model, raw_model)
            # The stock 2.0 nodes author Input Mode directly. Keep the hidden
            # task mirror synchronized so existing validation/payload code and
            # a later switch to 2.5 preserve the same semantic operation.
            if active_model != SEEDANCE_2_5_MODEL_ID:
                mirrored_task = INPUT_MODE_TASKS.get(str(value or "").strip())
                if (
                    mirrored_task
                    and self.get_parameter_value(TASK_PARAMETER) != mirrored_task
                ):
                    self._hmb_task_syncing = True
                    try:
                        self.set_parameter_value(TASK_PARAMETER, mirrored_task)
                    finally:
                        self._hmb_task_syncing = False
        if parameter.name in {
            "model_id",
            TASK_PARAMETER,
            "input_mode",
            "output_format",
            "return_last_frame",
            "local_video_upload_service",
            SHOT_CHANNEL_UUID_PARAMETER,
            SHOT_UUID_PARAMETER,
            SHOT_NUMBER_PARAMETER,
            SHOT_NAME_PARAMETER,
        }:
            self._update_parameter_visibility()
        if (
            not self._hmb_shot_syncing
            and not self._hmb_generation_action_only_update
            and parameter.name == SEEDANCE_SHOT_WIDGET_PARAMETER
        ):
            if not self._hmb_autoclaim_in_progress:
                self._set_hidden_control_value(
                    SHOT_AUTOCLAIM_ENABLED_PARAMETER,
                    False,
                )
            requested = (
                value.get("shot", {}).get("shot_uuid")
                if isinstance(value, dict) and isinstance(value.get("shot"), dict)
                else ""
            )
            self._apply_seedance_shot_selection(
                requested,
                fallback_to_available=bool(requested),
            )
            self._reconcile_shared_shot_routing()
            self._update_parameter_visibility()
        elif not self._hmb_shot_syncing and parameter.name == SHOT_SELECTOR_PARAMETER:
            if not self._hmb_autoclaim_in_progress:
                self._set_hidden_control_value(
                    SHOT_AUTOCLAIM_ENABLED_PARAMETER,
                    False,
                )
            selected = self._hmb_shot_selector_map.get(str(value or ""))
            self._apply_seedance_shot_selection(
                selected.get("shot_uuid") if isinstance(selected, dict) else "",
                fallback_to_available=isinstance(selected, dict),
            )
            self._reconcile_shared_shot_routing()
            self._update_parameter_visibility()
        elif not self._hmb_shot_syncing and parameter.name in {
            SHOT_CHANNEL_UUID_PARAMETER,
            SHOT_UUID_PARAMETER,
            SHOT_NUMBER_PARAMETER,
            SHOT_NAME_PARAMETER,
        }:
            self._reconcile_shared_shot_routing()
        result = super().after_value_set(parameter, value)
        if parameter.name == SEEDANCE_REFRESH_COMMAND_PARAMETER:
            action_id = str(
                getattr(self, "_hmb_pending_generation_command_id", "") or ""
            ).strip()
            self._hmb_pending_generation_command_id = ""
            if action_id:
                processed_ids = getattr(
                    self,
                    "_hmb_processed_generation_command_ids",
                    None,
                )
                if not isinstance(processed_ids, set):
                    processed_ids = set()
                    self._hmb_processed_generation_command_ids = processed_ids
                processed_ids.add(action_id)
                if len(processed_ids) > 256:
                    retained = set(tuple(processed_ids)[-127:])
                    retained.add(action_id)
                    self._hmb_processed_generation_command_ids = retained
                self._schedule_existing_generation_refresh()
        elif parameter.name == SEEDANCE_SHOT_WIDGET_PARAMETER:
            action_requested = self._hmb_pending_generation_action
            self._hmb_pending_generation_action = False
            self._hmb_generation_action_only_update = False
            if action_requested:
                self._schedule_existing_generation_refresh()
        return result

    def _restore_seedance_shot_route(self) -> None:
        """Re-arm routing only after serialized prompt/Shot state is hydrated."""

        # Workflows saved before Task existed serialize only input_mode. Migrate
        # that legacy field once unless an authored Task was replayed explicitly.
        if (
            not bool(getattr(self, "_hmb_task_initial_setup_seen", False))
            and bool(getattr(self, "_hmb_input_mode_initial_setup_seen", False))
        ):
            legacy_task = INPUT_MODE_TASKS.get(
                str(self.get_parameter_value("input_mode") or "")
            )
            if legacy_task:
                with suppress(Exception):
                    self.set_parameter_value(TASK_PARAMETER, legacy_task)

        # Complete model-dependent dropdown narrowing after every serialized
        # field has replayed. This makes model-first and duration-first loading
        # equivalent and repairs invalid cross-model values deterministically.
        with suppress(Exception):
            self._synchronize_model_resolution()
        with suppress(Exception):
            _shot_routing.schedule_post_hydration_reconcile(self)
        with suppress(Exception):
            self._reconcile_shared_shot_routing()
        with suppress(Exception):
            self._sync_seedance_shot_widget()
        with suppress(Exception):
            self._update_parameter_visibility()

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        parent = getattr(super(), "after_deserialize", None)
        result = parent(*args, **kwargs) if callable(parent) else None
        self._restore_seedance_shot_route()
        self._restore_generation_recovery_preview()
        return result

    def after_load(self, *args: Any, **kwargs: Any) -> Any:
        parent = getattr(super(), "after_load", None)
        result = parent(*args, **kwargs) if callable(parent) else None
        self._restore_seedance_shot_route()
        self._restore_generation_recovery_preview()
        return result

    def on_loaded(self, *args: Any, **kwargs: Any) -> Any:
        parent = getattr(super(), "on_loaded", None)
        result = parent(*args, **kwargs) if callable(parent) else None
        self._restore_seedance_shot_route()
        self._restore_generation_recovery_preview()
        return result

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

    def _runtime_node_is_live(self, *, require_registered: bool = False) -> bool:
        """Verify that this exact runtime object still owns its node name."""

        if getattr(self, "_hmb_node_deleted", False):
            return False
        node_name = str(getattr(self, "name", "") or "").strip()
        if not node_name:
            return not require_registered
        try:
            registered = GriptapeNodes.NodeManager().get_node_by_name(node_name)
        except Exception:
            # Constructor-time synchronous configuration is valid before the
            # retained-mode graph owns the node. Background callbacks must
            # never use that exception as permission to publish.
            return not require_registered
        return registered is self

    def _apply_broker_snapshot(
        self,
        snapshot: _BrokerAccountSnapshot,
        *,
        require_registered: bool = False,
    ) -> None:
        if not self._runtime_node_is_live(require_registered=require_registered):
            with self._broker_action_lock:
                self._broker_action_running = False
            return
        values = {
            "broker_connection_status": self._broker_connection_label(snapshot.state),
            "broker_account": snapshot.account if snapshot.connected and snapshot.account else "—",
        }
        try:
            for name, value in values.items():
                if not self._runtime_node_is_live(
                    require_registered=require_registered
                ):
                    return
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
            if callable(emitter) and self._runtime_node_is_live(
                require_registered=require_registered
            ):
                try:
                    emitter()
                except Exception:
                    pass

    def _schedule_broker_snapshot(self, snapshot: _BrokerAccountSnapshot) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            with self._broker_action_lock:
                self._broker_action_running = False
            return
        def apply_if_live() -> None:
            self._apply_broker_snapshot(snapshot, require_registered=True)

        try:
            event_loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if event_loop is not None and event_loop.is_running():
                event_loop.call_soon_threadsafe(apply_if_live)
                return
        except Exception:
            pass
        apply_if_live()

    def _on_broker_connect_clicked(self, _button: Any, _details: Any) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            return
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
                self._broker_error_snapshot(_BrokerUnavailableError("unavailable")),
                require_registered=True,
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

    @staticmethod
    def _default_output_filename(
        output_format: str,
        shot_number: int = 0,
    ) -> str:
        suffix = (
            f"_shot_{shot_number:02d}"
            if 1 <= int(shot_number or 0) <= SHOT_ROUTING_MAX_SHOTS
            else ""
        )
        return f"volcengine_seedance_video{suffix}.{output_format}"

    @staticmethod
    def _default_last_frame_filename(shot_number: int = 0) -> str:
        suffix = (
            f"_shot_{shot_number:02d}"
            if 1 <= int(shot_number or 0) <= SHOT_ROUTING_MAX_SHOTS
            else ""
        )
        return f"seedance_2_5_last_frame{suffix}.png"

    def _bound_output_shot_number(self) -> int:
        identity = self._shot_identity()
        return (
            int(identity["shot_number"])
            if identity.get("channel_uuid") and identity.get("shot_uuid")
            else 0
        )

    @staticmethod
    def _replace_managed_filename(current_text: str, filename: str) -> str:
        current_path = Path(current_text)
        updated = current_path.with_name(filename)
        return filename if current_text == current_path.name else str(updated)

    def _sync_output_filename(self, output_format: str) -> None:
        requested = str(output_format or "").strip().lower()
        if requested not in OUTPUT_FORMAT_CHOICES:
            return
        current_value = self.get_parameter_value("output_file")
        if current_value in (None, ""):
            return
        current_text = str(current_value)
        current_path = Path(current_text)
        if _AUTO_VIDEO_OUTPUT_NAME_PATTERN.fullmatch(current_path.name) is None:
            return
        updated_value = self._replace_managed_filename(
            current_text,
            self._default_output_filename(
                requested,
                self._bound_output_shot_number(),
            ),
        )
        if current_text == updated_value:
            return
        super().set_parameter_value("output_file", updated_value)
        with suppress(Exception):
            self.publish_update_to_parameter("output_file", updated_value)

    def _sync_last_frame_filename(self) -> None:
        current_value = self.get_parameter_value("last_frame_file")
        if current_value in (None, ""):
            return
        current_text = str(current_value)
        current_path = Path(current_text)
        if _AUTO_LAST_FRAME_NAME_PATTERN.fullmatch(current_path.name) is None:
            return
        updated_value = self._replace_managed_filename(
            current_text,
            self._default_last_frame_filename(
                self._bound_output_shot_number(),
            ),
        )
        if current_text == updated_value:
            return
        super().set_parameter_value("last_frame_file", updated_value)
        with suppress(Exception):
            self.publish_update_to_parameter("last_frame_file", updated_value)

    def _sync_shot_output_filenames(
        self,
        output_format: str | None = None,
    ) -> None:
        requested = str(
            output_format
            or self.get_parameter_value("output_format")
            or DEFAULT_OUTPUT_FORMAT
        ).strip().lower()
        self._sync_output_filename(requested)
        self._sync_last_frame_filename()

    def _synchronize_model_output_contract(
        self,
        model_id: str | None = None,
    ) -> None:
        if bool(getattr(self, "_hmb_output_contract_syncing", False)):
            return
        raw_model = str(
            self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
        ).strip()
        active_model = model_id or MODEL_ID_ALIASES.get(raw_model, raw_model)
        self._hmb_output_contract_syncing = True
        try:
            output_format = str(
                self.get_parameter_value("output_format") or DEFAULT_OUTPUT_FORMAT
            ).strip().lower()
            if output_format not in OUTPUT_FORMAT_CHOICES:
                output_format = DEFAULT_OUTPUT_FORMAT
            if active_model != SEEDANCE_2_5_MODEL_ID:
                output_format = DEFAULT_OUTPUT_FORMAT
                if self.get_parameter_value("output_format") != output_format:
                    super().set_parameter_value("output_format", output_format)
                if bool(self.get_parameter_value("return_last_frame")):
                    super().set_parameter_value("return_last_frame", False)
            self._sync_shot_output_filenames(output_format)
        finally:
            self._hmb_output_contract_syncing = False

    def _update_parameter_visibility(self) -> None:
        model_id = self._synchronize_model_resolution()
        task = str(
            self.get_parameter_value(TASK_PARAMETER) or TASK_REFERENCE_TO_VIDEO
        )
        shot_enabled = False
        with suppress(Exception):
            subscription = self._hmb_shot_channel_subscription()
            shot_enabled = bool(
                isinstance(subscription, dict) and subscription.get("enabled")
            )
        # Match the native model contracts instead of presenting one shared
        # label for two different concepts: 2.0 authors an Input Mode, while
        # 2.5 authors a Task. Shot routing hides either selector because its
        # exact media fixes the effective reference operation at execution.
        task_visible = bool(not shot_enabled and model_id == SEEDANCE_2_5_MODEL_ID)
        input_mode_visible = bool(
            not shot_enabled and model_id != SEEDANCE_2_5_MODEL_ID
        )
        selector_contracts = (
            (TASK_PARAMETER, task_visible, "Task"),
            ("input_mode", input_mode_visible, "Input Mode"),
        )
        for name, visible, label in selector_contracts:
            parameter = self.get_parameter_by_name(name)
            if parameter is None:
                continue
            parameter.ui_options = {
                **parameter.ui_options,
                "display_name": label if visible else "",
                "hide": not visible,
                "hide_property": not visible,
                "hide_label": not visible,
                "hide_handles": True,
            }

        # Manual rows belong exclusively to Only mode. Shot mode hides them and
        # resolves immutable media snapshots at execution without clearing the
        # authored children, so Only -> Shot -> Only is lossless.
        self.hide_parameter_by_name(
            [
                "first_frame",
                "last_frame",
                "reference_images",
                VIDEO_REFERENCES_PARAMETER,
                "reference_audio",
                "reference_video_1",
                "reference_video_2",
                "reference_video_3",
            ]
        )
        if not shot_enabled and task == TASK_FIRST_LAST_FRAME:
            self.show_parameter_by_name(["first_frame", "last_frame"])
        manual_references_visible = bool(
            not shot_enabled
            and task
            in {
                TASK_REFERENCE_TO_VIDEO,
                TASK_VIDEO_EDITING,
                TASK_VIDEO_EXTENSION,
            }
        )
        reference_labels = {
            "reference_images": "Reference Images",
            VIDEO_REFERENCES_PARAMETER: "Reference Videos",
            "reference_audio": "Reference Audio",
        }
        for name, label in reference_labels.items():
            parameter = self.get_parameter_by_name(name)
            if parameter is None:
                continue
            parameter.hide = not manual_references_visible
            parameter.ui_options = {
                **parameter.ui_options,
                "display_name": label if manual_references_visible else "",
                "hide": not manual_references_visible,
                "hide_property": True,
                "hide_label": not manual_references_visible,
                "hide_handles": not manual_references_visible,
            }
            if manual_references_visible:
                self.show_parameter_by_name(name)

        raw_model = str(
            self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
        ).strip()
        model_id = MODEL_ID_ALIASES.get(raw_model, raw_model)
        seedance_25_active = model_id == SEEDANCE_2_5_MODEL_ID
        if seedance_25_active:
            self.show_parameter_by_name(["output_format", "return_last_frame"])
        else:
            self.hide_parameter_by_name(["output_format", "return_last_frame"])
        if seedance_25_active and bool(
            self.get_parameter_value("return_last_frame")
        ):
            self.show_parameter_by_name(["last_frame_url", "last_frame_file"])
        else:
            self.hide_parameter_by_name(["last_frame_url", "last_frame_file"])
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
        """Apply the selected Volcengine model's generation contract."""
        raw_model = self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
        raw_model_text = str(raw_model).strip()
        model_id = MODEL_ID_ALIASES.get(raw_model_text, raw_model_text)
        migrated_retired_model = bool(
            self._hmb_retired_model_migration_pending
            or raw_model_text in RETIRED_SEEDANCE_MODEL_VALUES
        )
        if (
            raw_model_text in RETIRED_SEEDANCE_MODEL_VALUES
            and not self._hmb_model_migration_active
        ):
            self._hmb_model_migration_active = True
            try:
                self.set_parameter_value("model_id", MODEL_NAME_SEEDANCE_2_0)
            finally:
                self._hmb_model_migration_active = False
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
        previous_model_id = str(
            getattr(self, "_hmb_model_switch_previous_id", "") or ""
        )
        inherited_previous_default = bool(
            previous_model_id
            and previous_model_id != model_id
            and current == MODEL_DEFAULT_RESOLUTIONS.get(previous_model_id)
        )
        if (
            migrated_retired_model
            or current not in supported
            or inherited_previous_default
        ):
            self.set_parameter_value(
                "resolution", MODEL_DEFAULT_RESOLUTIONS[model_id]
            )

        task_parameter = self.get_parameter_by_name(TASK_PARAMETER)
        task_choices = MODEL_TASK_CHOICES[model_id]
        if task_parameter is not None:
            visible_task_choices = list(task_choices)
            if task_parameter.ui_options.get("simple_dropdown") != visible_task_choices:
                task_parameter.ui_options = {
                    **task_parameter.ui_options,
                    "simple_dropdown": visible_task_choices,
                }
        current_task = str(
            self.get_parameter_value(TASK_PARAMETER) or TASK_REFERENCE_TO_VIDEO
        )
        if current_task not in TASK_STORAGE_CHOICES:
            current_task = TASK_REFERENCE_TO_VIDEO
        if current_task not in task_choices:
            current_task = TASK_REFERENCE_TO_VIDEO
            self._hmb_task_syncing = True
            try:
                self.set_parameter_value(TASK_PARAMETER, current_task)
            finally:
                self._hmb_task_syncing = False

        derived_input_mode = TASK_INPUT_MODES[current_task]
        if self.get_parameter_value("input_mode") != derived_input_mode:
            self._hmb_input_mode_syncing = True
            try:
                self.set_parameter_value("input_mode", derived_input_mode)
            finally:
                self._hmb_input_mode_syncing = False

        if model_id == SEEDANCE_2_5_MODEL_ID and current_task == TASK_VIDEO_EDITING:
            duration_choices = (-1,)
        elif model_id == SEEDANCE_2_5_MODEL_ID and current_task == TASK_VIDEO_EXTENSION:
            duration_choices = DURATION_STORAGE_CHOICES
        else:
            duration_choices = MODEL_DURATION_CHOICES[model_id]
        duration_parameter = self.get_parameter_by_name("duration")
        if duration_parameter is not None:
            visible_duration_choices = list(duration_choices)
            if (
                duration_parameter.ui_options.get("simple_dropdown")
                != visible_duration_choices
            ):
                duration_parameter.ui_options = {
                    **duration_parameter.ui_options,
                    "simple_dropdown": visible_duration_choices,
                }
            current_duration = self.get_parameter_value("duration")
            if (
                not isinstance(current_duration, int)
                or isinstance(current_duration, bool)
                or current_duration not in duration_choices
            ):
                self.set_parameter_value(
                    "duration",
                    -1 if current_task == TASK_VIDEO_EDITING else 5,
                )
        if migrated_retired_model:
            self._hmb_retired_model_migration_pending = False
        self._synchronize_model_output_contract(model_id)
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

    def _has_incoming_parameter_connection(self, name: str) -> bool:
        """Return True for an incoming edge on *name* or one of its list rows."""

        try:
            registered = GriptapeNodes.NodeManager().get_node_by_name(
                str(self.name)
            )
        except (KeyError, ValueError):
            return False
        except Exception:
            registered = self
        if registered is not self:
            return False
        try:
            from griptape_nodes.retained_mode.retained_mode import RetainedMode  # type: ignore

            result = RetainedMode.get_connections_for_node(str(self.name))
        except Exception:
            result = None
        incoming = getattr(result, "incoming_connections", None)
        if isinstance(incoming, (list, tuple)):
            return any(
                self._connection_targets_parameter_or_list_child(
                    str(name),
                    str(getattr(item, "target_parameter_name", "") or ""),
                )
                for item in incoming
            )
        if result is not None:
            return False

        # Compatibility fallback for older hosts and isolated regression stubs
        # that expose only the parameter-scoped retained-mode query. Query the
        # parent plus every surviving dynamic row; older APIs do not expand a
        # ParameterList parent query to its children.
        query_names = [str(name)]
        container = None
        with suppress(Exception):
            container = self.get_parameter_by_name(str(name))
        if isinstance(container, ParameterList):
            with suppress(Exception):
                query_names.extend(
                    str(child.name)
                    for child in container.get_child_parameters()
                    if str(getattr(child, "name", "") or "")
                )
        for query_name in dict.fromkeys(query_names):
            try:
                result = RetainedMode.get_connections_for_parameter(
                    query_name,
                    str(self.name),
                )
            except Exception:
                continue
            incoming = getattr(result, "incoming_connections", None)
            if isinstance(incoming, (list, tuple)) and any(
                self._connection_targets_parameter_or_list_child(
                    str(name),
                    str(getattr(item, "target_parameter_name", "") or ""),
                )
                for item in incoming
            ):
                return True
        return False

    def _connection_targets_parameter_or_list_child(
        self,
        parent_name: str,
        target_name: str,
    ) -> bool:
        """Match a retained edge to a parameter or a stable ParameterList row."""

        parent = str(parent_name or "")
        target = str(target_name or "")
        if not parent or not target:
            return False
        if target == parent:
            return True
        parameter = None
        with suppress(Exception):
            parameter = self.get_parameter_by_name(target)
        if str(getattr(parameter, "parent_container_name", "") or "") == parent:
            return True
        container = None
        with suppress(Exception):
            container = self.get_parameter_by_name(parent)
        return bool(
            isinstance(container, ParameterList)
            and target.startswith(f"{parent}_ParameterListUniqueParamID_")
        )

    def _discard_dangling_owned_list_connections_before_delete(self) -> int:
        """Remove only invalid edges whose HMB list row no longer exists.

        Griptape validates both endpoint parameters before deleting an edge. A
        historic parent-list hydration could replace a connected dynamic row,
        leaving the retained connection object alive after that row disappeared.
        Such an edge makes the host abort deletion/reset before it can release
        this generator's Shot. During the node's deletion hook it is safe to
        discard only those already-invalid, HMB-owned list-row edges directly;
        valid user connections continue through the normal host lifecycle.
        """

        try:
            connections = GriptapeNodes.FlowManager().get_connections()
            incoming_index = getattr(connections, "incoming_index", {})
            connection_map = getattr(connections, "connections", {})
            by_parameter = incoming_index.get(str(self.name), {})
        except Exception:
            return 0
        if not isinstance(by_parameter, dict) or not isinstance(connection_map, dict):
            return 0

        owned_lists = (
            "reference_images",
            VIDEO_REFERENCES_PARAMETER,
            "reference_audio",
        )
        connection_ids = {
            connection_id
            for values in tuple(by_parameter.values())
            if isinstance(values, (list, tuple, set))
            for connection_id in tuple(values)
        }
        removed = 0
        failed: list[str] = []
        remover = getattr(connections, "remove_connection_by_object", None)
        for connection_id in connection_ids:
            connection = connection_map.get(connection_id)
            if connection is None:
                continue
            target_node = getattr(connection, "target_node", None)
            if target_node is not self:
                continue
            target_parameter = getattr(connection, "target_parameter", None)
            target_name = str(getattr(target_parameter, "name", "") or "")
            if not target_name or self.get_parameter_by_name(target_name) is not None:
                continue
            if not any(
                self._connection_targets_parameter_or_list_child(
                    parent_name,
                    target_name,
                )
                for parent_name in owned_lists
            ):
                continue
            if not callable(remover) or remover(connection) is not True:
                failed.append(target_name)
                continue
            removed += 1
        if failed:
            raise ValueError(
                "Unable to release dangling HMB list connection(s): "
                + ", ".join(sorted(set(failed)))
            )
        if removed:
            logger.warning(
                "Removed %d dangling HMB list connection(s) before deleting %s.",
                removed,
                self.name,
            )
        return removed

    def _get_list_input(self, name: str) -> list[Any]:
        """Read the current list value, then an older serialized top-level value."""
        current = [
            value
            for value in self._as_list(self.get_parameter_value(name))
            if self._has_reference_value(value)
        ]
        if self._has_incoming_parameter_connection(name):
            return current
        if current:
            return current
        if name in getattr(self, "_hmb_explicit_list_authority", set()):
            return []
        # Griptape's ParameterList getter (still used by reference_audio) reads
        # child elements and intentionally ignores a former top-level serialized
        # value. Retain that value only for a legacy workflow that has not since
        # authored, connected, or explicitly cleared the current list.
        return [
            value
            for value in self._as_list(self.parameter_values.get(name))
            if self._has_reference_value(value)
        ]

    def _list_input_is_authoritative(self, name: str) -> bool:
        return bool(
            self._has_incoming_parameter_connection(name)
            or name in getattr(self, "_hmb_explicit_list_authority", set())
        )

    def _exact_incoming_source(
        self,
        target_parameter_name: str,
        expected_source_parameter_name: str,
        *,
        required: bool = True,
    ) -> Any:
        try:
            from griptape_nodes.retained_mode.retained_mode import RetainedMode  # type: ignore

            result = RetainedMode.get_connections_for_parameter(
                target_parameter_name,
                str(self.name),
            )
        except Exception as exc:
            raise RuntimeError(
                f"Seedance could not inspect {target_parameter_name} Shot routing."
            ) from exc
        incoming = getattr(result, "incoming_connections", None)
        if not isinstance(incoming, (list, tuple)):
            raise RuntimeError(
                f"Seedance {target_parameter_name} Shot routing result is malformed."
            )
        matches = [
            item for item in incoming
            if str(getattr(item, "target_parameter_name", "") or "")
            == target_parameter_name
        ]
        if not matches and not required:
            return None
        if len(matches) != 1:
            raise RuntimeError(
                f"Seedance {target_parameter_name} requires exactly one upstream Shot source."
            )
        connection = matches[0]
        if str(getattr(connection, "source_parameter_name", "") or "") != expected_source_parameter_name:
            raise RuntimeError(
                f"Seedance {target_parameter_name} is connected to the wrong source port."
            )
        source_node_name = str(getattr(connection, "source_node_name", "") or "").strip()
        if not source_node_name:
            raise RuntimeError(
                f"Seedance {target_parameter_name} source identity is missing."
            )
        source_node = GriptapeNodes.NodeManager().get_node_by_name(source_node_name)
        if source_node is None:
            raise RuntimeError(
                f"Seedance {target_parameter_name} source node is unavailable."
            )
        return source_node

    def _manual_agent_prompt_source(self) -> Any | None:
        """Return a manually connected HMBAgent output, otherwise no authority.

        Ordinary text/property inputs and other prompt-producing nodes remain
        valid Seedance inputs.  An object that exposes the HMB Agent snapshot
        API opts into strict exact-Shot parity and must use its public
        ``output`` port.
        """

        try:
            from griptape_nodes.retained_mode.retained_mode import RetainedMode  # type: ignore

            result = RetainedMode.get_connections_for_parameter(
                "prompt",
                str(self.name),
            )
        except Exception as exc:
            raise RuntimeError("Seedance could not inspect its prompt connection.") from exc
        incoming = getattr(result, "incoming_connections", None)
        if not isinstance(incoming, (list, tuple)):
            raise RuntimeError("Seedance prompt connection result is malformed.")
        matches = [
            item
            for item in incoming
            if str(getattr(item, "target_parameter_name", "") or "") == "prompt"
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise RuntimeError("Seedance prompt connection is ambiguous.")
        connection = matches[0]
        source_name = str(getattr(connection, "source_node_name", "") or "").strip()
        if not source_name:
            raise RuntimeError("Seedance prompt source identity is missing.")
        source_node = GriptapeNodes.NodeManager().get_node_by_name(source_name)
        if source_node is None:
            raise RuntimeError("Seedance prompt source node is unavailable.")
        subscription_getter = getattr(
            source_node,
            "_hmb_shot_channel_subscription",
            None,
        )
        try:
            source_subscription = (
                subscription_getter() if callable(subscription_getter) else None
            )
        except Exception:
            source_subscription = None
        if (
            not isinstance(source_subscription, dict)
            or source_subscription.get("participant_kind") != "agent"
        ):
            return None
        if str(getattr(connection, "source_parameter_name", "") or "") != "output":
            raise RuntimeError("Seedance HMBAgent prompt must use the Agent output port.")
        return source_node

    @classmethod
    def _validate_direct_media_snapshot(
        cls,
        value: Any,
        *,
        source_kind: str,
        expected_channel_uuid: str,
    ) -> dict[str, Any]:
        """Validate one atomic ImageAsset or VideoPicker source publication."""

        if source_kind == "image_asset":
            schema = "hmb-shot-routing-snapshot"
            records_key = "ordered_assets"
            shot_fields = {
                "shot_uuid", "number", "name", "revision", "selected_source_uids",
            }
        elif source_kind == "video_picker":
            schema = "hmb-picker-shot-routing-snapshot"
            records_key = "ordered_videos"
            shot_fields = {
                "shot_uuid", "number", "name", "revision", "selected_source_uids",
                "picker_payload",
            }
        else:
            raise RuntimeError("Seedance direct Shot source kind is invalid.")
        required = {
            "schema", "version", "publisher_instance_uuid", "channel_uuid",
            "generation", "metadata_sha256", "media_sha256", "shots",
            records_key, "media_by_source_uid",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RuntimeError(
                f"Seedance {source_kind} Shot snapshot has unknown or missing fields."
            )
        channel = cls._shot_uuid(value.get("channel_uuid"))
        expected_channel = cls._shot_uuid(expected_channel_uuid)
        publisher = str(value.get("publisher_instance_uuid") or "").strip()
        generation = value.get("generation")
        if (
            value.get("schema") != schema
            or value.get("version") != 1
            or not publisher
            or len(publisher) > 128
            or not channel
            or channel != expected_channel
            or not isinstance(generation, int)
            or isinstance(generation, bool)
            or not 0 <= generation <= 10**12
        ):
            raise RuntimeError(f"Seedance {source_kind} Shot snapshot identity is invalid.")

        raw_shots = value.get("shots")
        if not isinstance(raw_shots, list) or not 1 <= len(raw_shots) <= SHOT_ROUTING_MAX_SHOTS:
            raise RuntimeError(f"Seedance {source_kind} Shot list is invalid.")
        shots: list[dict[str, Any]] = []
        shot_ids: set[str] = set()
        shot_numbers: set[int] = set()
        for raw in raw_shots:
            if not isinstance(raw, dict) or set(raw) != shot_fields:
                raise RuntimeError(f"Seedance {source_kind} Shot record is malformed.")
            shot_uuid = cls._shot_uuid(raw.get("shot_uuid"))
            number = raw.get("number")
            name = str(raw.get("name") or "").strip()
            revision = raw.get("revision")
            selected = raw.get("selected_source_uids")
            if (
                not shot_uuid
                or shot_uuid in shot_ids
                or not isinstance(number, int)
                or isinstance(number, bool)
                or not 1 <= number <= SHOT_ROUTING_MAX_SHOTS
                or number in shot_numbers
                or not name
                or len(name) > 128
                or not isinstance(revision, int)
                or isinstance(revision, bool)
                or not 0 <= revision <= 10**12
                or not isinstance(selected, list)
            ):
                raise RuntimeError(f"Seedance {source_kind} Shot identity is invalid.")
            selected_uids = [str(item or "").strip() for item in selected]
            if (
                any(not item or len(item) > 1024 for item in selected_uids)
                or len(set(selected_uids)) != len(selected_uids)
            ):
                raise RuntimeError(f"Seedance {source_kind} Shot addresses are invalid.")
            normalized = {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
                "selected_source_uids": selected_uids,
            }
            if source_kind == "video_picker":
                if not isinstance(raw.get("picker_payload"), dict):
                    raise RuntimeError("Seedance VideoPicker payload is invalid.")
                normalized["picker_payload"] = deepcopy(raw["picker_payload"])
            shots.append(normalized)
            shot_ids.add(shot_uuid)
            shot_numbers.add(number)

        raw_records = value.get(records_key)
        raw_media = value.get("media_by_source_uid")
        if not isinstance(raw_records, list) or not isinstance(raw_media, dict):
            raise RuntimeError(f"Seedance {source_kind} source arrays are invalid.")
        records: list[dict[str, Any]] = []
        ordered_uids: list[str] = []
        for raw in raw_records:
            if not isinstance(raw, dict) or set(raw) != {"source_uid", "metadata"}:
                raise RuntimeError(f"Seedance {source_kind} source record is malformed.")
            source_uid = str(raw.get("source_uid") or "").strip()
            metadata = raw.get("metadata")
            if (
                not source_uid
                or len(source_uid) > 1024
                or source_uid in ordered_uids
                or not isinstance(metadata, dict)
            ):
                raise RuntimeError(f"Seedance {source_kind} source address is invalid.")
            ordered_uids.append(source_uid)
            records.append({"source_uid": source_uid, "metadata": deepcopy(metadata)})
        if set(raw_media) != set(ordered_uids):
            raise RuntimeError(f"Seedance {source_kind} metadata/media addresses differ.")
        media: dict[str, str] = {}
        for source_uid in ordered_uids:
            media_value = raw_media.get(source_uid)
            if not isinstance(media_value, str) or not media_value:
                raise RuntimeError(f"Seedance {source_kind} media value is unavailable.")
            media[source_uid] = media_value
        known_uids = set(ordered_uids)
        if any(
            uid not in known_uids
            for shot in shots
            for uid in shot["selected_source_uids"]
        ):
            raise RuntimeError(f"Seedance {source_kind} Shot addresses unpublished media.")
        metadata_document = {
            "channel_uuid": channel,
            "generation": generation,
            "shots": shots,
            records_key: records,
        }
        descriptors = [
            {
                "source_uid": uid,
                "media_value_sha256": hashlib.sha256(media[uid].encode("utf-8")).hexdigest(),
            }
            for uid in ordered_uids
        ]
        if str(value.get("metadata_sha256") or "").strip().casefold() != cls._canonical_sha256(metadata_document):
            raise RuntimeError(f"Seedance {source_kind} metadata hash does not match.")
        if str(value.get("media_sha256") or "").strip().casefold() != cls._canonical_sha256({"media_descriptors": descriptors}):
            raise RuntimeError(f"Seedance {source_kind} media hash does not match.")
        return {
            "schema": schema,
            "version": 1,
            "publisher_instance_uuid": publisher,
            "channel_uuid": channel,
            "generation": generation,
            "metadata_sha256": str(value["metadata_sha256"]).strip().casefold(),
            "media_sha256": str(value["media_sha256"]).strip().casefold(),
            "shots": shots,
            records_key: records,
            "media_by_source_uid": media,
        }

    @staticmethod
    def _direct_source_subscription(source_node: Any, expected_kind: str) -> dict[str, Any]:
        getter = getattr(source_node, "_hmb_shot_channel_subscription", None)
        try:
            subscription = getter() if callable(getter) else None
        except Exception as exc:
            raise RuntimeError("Seedance direct Shot source identity is unavailable.") from exc
        if (
            not isinstance(subscription, dict)
            or subscription.get("participant_kind") != expected_kind
            or not subscription.get("enabled")
        ):
            raise RuntimeError(f"Seedance {expected_kind} source identity is invalid.")
        return subscription

    def _resolve_exact_shot_generation_inputs(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        # A newly added or deserialized Seedance node may still have a blank
        # durable quartet. Reconcile the same-flow catalog before deciding
        # whether remote execution can proceed; a missing catalog fails closed.
        self._reconcile_shared_shot_routing(strict=True)
        subscription = self._hmb_shot_channel_subscription()
        if not subscription["enabled"]:
            resolved = dict(params)
            resolved["prompt"] = str(params.get("prompt") or "")
            task = str(params.get(TASK_PARAMETER) or "").strip()
            if not task:
                task = INPUT_MODE_TASKS.get(
                    str(params.get("input_mode") or ""),
                    TASK_REFERENCE_TO_VIDEO,
                )
            resolved[TASK_PARAMETER] = task
            resolved["input_mode"] = TASK_INPUT_MODES.get(
                task,
                str(params.get("input_mode") or INPUT_MODE_MULTIMODAL_REFERENCES),
            )
            if task == TASK_TEXT_ONLY:
                resolved["first_frame"] = None
                resolved["last_frame"] = None
                resolved["reference_images"] = []
                resolved["video_references"] = []
                resolved["video_reference_slots"] = []
                resolved["reference_audio"] = []
            elif task == TASK_FIRST_LAST_FRAME:
                resolved["reference_images"] = []
                resolved["video_references"] = []
                resolved["video_reference_slots"] = []
                resolved["reference_audio"] = []
            elif task in {
                TASK_REFERENCE_TO_VIDEO,
                TASK_VIDEO_EDITING,
                TASK_VIDEO_EXTENSION,
            }:
                resolved["first_frame"] = None
                resolved["last_frame"] = None
            return resolved

        image_node = self._exact_incoming_source(
            SHOT_ASSET_INPUT_PARAMETER,
            "SHOT_ASSET_OUT",
            required=False,
        )
        picker_node = self._exact_incoming_source(
            SHOT_PICKER_INPUT_PARAMETER,
            "SHOT_PICKER_OUT",
            required=False,
        )
        model_id = str(params.get("model_id") or "")
        if image_node is None and picker_node is None:
            raise RuntimeError("Seedance selected Shot has no direct media source.")
        if image_node is not None and image_node is picker_node:
            raise RuntimeError("Seedance ImageAsset and VideoPicker sources must be distinct.")
        expected_identity = (
            int(subscription["shot_number"]),
            str(subscription["shot_name"]),
        )
        images: list[str] = []
        videos: list[str] = []
        for source_node, source_kind in (
            (image_node, "image_asset"),
            (picker_node, "video_picker"),
        ):
            if source_node is None:
                continue
            source_subscription = self._direct_source_subscription(
                source_node,
                source_kind,
            )
            if source_subscription.get("channel_uuid") != subscription["channel_uuid"]:
                raise RuntimeError(
                    "Seedance direct sources do not match the selected Shot channel."
                )
            snapshot_api = getattr(source_node, "_hmb_shot_routing_snapshot", None)
            if not callable(snapshot_api):
                raise RuntimeError(
                    "Seedance direct source does not expose the atomic Shot snapshot API."
                )
            try:
                raw_snapshot = snapshot_api(subscription["channel_uuid"])
            except TypeError:
                raw_snapshot = snapshot_api()
            source_snapshot = self._validate_direct_media_snapshot(
                raw_snapshot,
                source_kind=source_kind,
                expected_channel_uuid=subscription["channel_uuid"],
            )
            source_shot = next(
                (
                    item for item in source_snapshot["shots"]
                    if item["shot_uuid"] == subscription["shot_uuid"]
                ),
                None,
            )
            if not isinstance(source_shot, dict):
                raise RuntimeError("Seedance selected Shot is missing from a direct source.")
            if (
                int(source_shot["number"]),
                str(source_shot["name"]),
            ) != expected_identity:
                raise RuntimeError(
                    "Seedance selected Shot identity does not match its direct sources."
                )
            selected_media = [
                source_snapshot["media_by_source_uid"][uid]
                for uid in source_shot["selected_source_uids"]
            ]
            if source_kind == "image_asset":
                images = selected_media
            else:
                videos = selected_media
        image_limit, video_limit, _audio_limit = MODEL_REFERENCE_LIMITS.get(
            model_id,
            MODEL_REFERENCE_LIMITS[SEEDANCE_2_0_MODEL_ID],
        )
        model_name = MODEL_DISPLAY_NAME_BY_ID.get(model_id, "Seedance")
        if len(images) > image_limit:
            raise ValueError(
                f"Selected Shot contains {len(images)} images; {model_name} accepts "
                f"at most {image_limit}. No request was submitted."
            )
        if len(videos) > video_limit:
            raise ValueError(
                f"Selected Shot contains {len(videos)} videos; {model_name} accepts "
                f"at most {video_limit}. No request was submitted."
            )

        resolved = dict(params)
        resolved["prompt"] = str(params.get("prompt") or "")
        resolved[TASK_PARAMETER] = TASK_REFERENCE_TO_VIDEO
        reference_duration_choices = MODEL_DURATION_CHOICES.get(model_id, ())
        if (
            "duration" in resolved
            and resolved.get("duration") not in reference_duration_choices
        ):
            # Only may author Video Editing with its required smart duration
            # (-1). Shot always executes Reference to Video, whose 2.5 duration
            # is explicit. Normalize only this execution copy; returning to
            # Only restores the untouched authored Task and duration controls.
            resolved["duration"] = 5
        resolved["first_frame"] = None
        resolved["last_frame"] = None
        resolved["reference_images"] = list(images)
        resolved["video_references"] = list(videos)
        resolved["video_reference_slots"] = []
        resolved["reference_audio"] = []
        resolved["input_mode"] = INPUT_MODE_MULTIMODAL_REFERENCES
        return resolved

    def _get_parameters(self) -> dict[str, Any]:
        model_id = self._synchronize_model_resolution()
        legacy_video_slots = [
            self.get_parameter_value(f"reference_video_{index}")
            for index in range(1, LEGACY_VIDEO_REFERENCE_SLOTS + 1)
        ]
        ordered_video_references = self._get_list_input(VIDEO_REFERENCES_PARAMETER)
        if ordered_video_references or self._list_input_is_authoritative(
            VIDEO_REFERENCES_PARAMETER
        ):
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
            TASK_PARAMETER: str(
                self.get_parameter_value(TASK_PARAMETER)
                or TASK_REFERENCE_TO_VIDEO
            ),
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
            "output_format": str(
                self.get_parameter_value("output_format") or DEFAULT_OUTPUT_FORMAT
            ).strip().lower(),
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

        resume_generation_id = params.get("resume_generation_id", "")
        if resume_generation_id:
            # Resuming an existing Broker task performs no reference upload.
            # Validate only the task ID and polling controls used by this path;
            # stale or incomplete TOS authoring settings must not make an
            # already-submitted result unrecoverable.
            self._validate_task_id(resume_generation_id)
            return

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

        model_id = params["model_id"]
        if model_id not in MODEL_RESOLUTIONS:
            raise ValueError(f"Unsupported Volcengine Seedance model: {model_id!r}.")
        model_name = MODEL_DISPLAY_NAME_BY_ID[model_id]
        task = str(params.get(TASK_PARAMETER) or "").strip()
        if not task:
            task = INPUT_MODE_TASKS.get(
                str(params.get("input_mode") or ""),
                TASK_REFERENCE_TO_VIDEO,
            )
        if task not in TASK_STORAGE_CHOICES:
            raise ValueError(f"Unsupported Seedance task: {task!r}.")
        if task not in MODEL_TASK_CHOICES[model_id]:
            raise ValueError(f"{model_name} does not support task {task!r}.")

        output_format = str(
            params.get("output_format") or DEFAULT_OUTPUT_FORMAT
        ).strip().lower()
        if output_format not in OUTPUT_FORMAT_CHOICES:
            raise ValueError(
                f"Unsupported Seedance output format: {output_format!r}."
            )
        return_last_frame = params.get("return_last_frame", False)
        if not isinstance(return_last_frame, bool):
            raise ValueError("return_last_frame must be a boolean.")
        params["output_format"] = output_format
        params["return_last_frame"] = return_last_frame
        if model_id != SEEDANCE_2_5_MODEL_ID:
            # Saved/browser values may outlive a model switch, but the 2.0
            # contract remains MP4-only and has no returned-frame output.
            output_format = DEFAULT_OUTPUT_FORMAT
            params["output_format"] = DEFAULT_OUTPUT_FORMAT
            params["return_last_frame"] = False

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
        if model_id == SEEDANCE_2_5_MODEL_ID and task == TASK_VIDEO_EDITING:
            duration_choices = (-1,)
        elif model_id == SEEDANCE_2_5_MODEL_ID and task == TASK_VIDEO_EXTENSION:
            duration_choices = DURATION_STORAGE_CHOICES
        else:
            duration_choices = MODEL_DURATION_CHOICES[model_id]
        if duration not in duration_choices:
            maximum_duration = max(duration_choices)
            if task == TASK_VIDEO_EDITING:
                raise ValueError("Video Editing duration must be -1.")
            if task == TASK_VIDEO_EXTENSION:
                raise ValueError(
                    "Video Extension duration must be -1 or an integer from 4 "
                    "through 30."
                )
            raise ValueError(
                f"{model_name} duration must be -1 or an integer from 4 through "
                f"{maximum_duration}."
            )

        images = params["reference_images"]
        videos = params["video_references"]
        audio = params["reference_audio"]
        image_limit, video_limit, audio_limit = MODEL_REFERENCE_LIMITS[model_id]
        if len(images) > image_limit:
            raise ValueError(
                f"{model_name} accepts at most {image_limit} reference images; "
                f"received {len(images)}."
            )
        if len(videos) > video_limit:
            raise ValueError(
                f"{model_name} accepts at most {video_limit} reference videos; "
                f"received {len(videos)}. No references were discarded."
            )
        if len(audio) > audio_limit:
            raise ValueError(
                f"{model_name} accepts at most {audio_limit} reference audio files; "
                f"received {len(audio)}."
            )

        input_mode = TASK_INPUT_MODES[task]
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
            if model_id == SEEDANCE_2_5_MODEL_ID and params["ratio"] != "adaptive":
                raise ValueError(
                    "Seedance 2.5 First/Last Frame mode requires adaptive ratio."
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
            if (
                model_id != SEEDANCE_2_5_MODEL_ID
                and audio
                and not (images or videos)
            ):
                raise ValueError(
                    "Reference audio requires at least one reference image or video."
                )
        else:
            raise ValueError(f"Unsupported input mode: {input_mode!r}.")

        prompt = str(params["prompt"] or "").strip()
        if (
            model_id == SEEDANCE_2_5_MODEL_ID
            and task == TASK_REFERENCE_TO_VIDEO
            and not has_references
        ):
            raise ValueError(
                "Reference to Video requires at least one reference image, video, "
                "or audio input."
            )
        if task in {TASK_VIDEO_EDITING, TASK_VIDEO_EXTENSION}:
            if model_id != SEEDANCE_2_5_MODEL_ID:
                raise ValueError(f"{task} is supported only by Seedance 2.5.")
            if not videos:
                raise ValueError(f"{task} requires at least one reference video.")
            if params["ratio"] != "adaptive":
                raise ValueError(f"{task} requires adaptive ratio.")

        if not prompt and not (has_frames or has_references):
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
                "Use priority 0 for Fast or Seedance 2.5."
            )

    @staticmethod
    def _validate_broker_model(model_id: Any) -> None:
        if model_id not in BROKER_SUPPORTED_MODEL_IDS:
            raise ValueError(
                "FN AI Broker supports only the active Volcengine Seedance 2.0, "
                "Seedance 2.0 Fast, and Seedance 2.5 model IDs."
            )

    def _get_parameters_for_start_validation(self) -> dict[str, Any]:
        """Resolve safe graph inputs without requiring an upstream result yet."""

        params = self._get_parameters()
        if params.get("resume_generation_id"):
            return params
        # Hidden ImageAsset/VideoPicker Shot wires are authoritative but are not
        # represented in the public parameter lists. Resolve them during
        # StartFlow validation as well as execution so a valid media-backed Shot
        # is not rejected as an empty node.
        params = self._resolve_exact_shot_generation_inputs(params)
        # The graph validator runs before connected Prompt/Agent nodes. A
        # temporary sentinel validates only the connection shape; it never
        # enters runtime state or a Broker payload. Execution reads the actual
        # connected output without imposing a second semantic contract.
        if (
            not str(params.get("prompt") or "").strip()
            and self._has_incoming_parameter_connection("prompt")
        ):
            params = dict(params)
            params["prompt"] = "HMB connected prompt pending execution"
        return params

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        try:
            params = self._get_parameters_for_start_validation()
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

    @staticmethod
    def _encode_local_media_data_uri(path: Path, mime: str) -> str:
        """Base64-encode a bounded local file without a whole-file raw copy."""

        encoded = io.StringIO()
        encoded.write(f"data:{mime};base64,")
        with path.open("rb") as stream:
            remainder = b""
            while True:
                chunk = stream.read(MEDIA_BASE64_READ_CHUNK_BYTES)
                if not chunk:
                    break
                chunk = remainder + chunk
                boundary = len(chunk) - (len(chunk) % 3)
                if boundary:
                    encoded.write(
                        base64.b64encode(chunk[:boundary]).decode("ascii")
                    )
                remainder = chunk[boundary:]
            if remainder:
                encoded.write(base64.b64encode(remainder).decode("ascii"))
        return encoded.getvalue()

    @classmethod
    def _projected_prepared_reference_json_bytes(
        cls,
        kind: str,
        value: Any,
    ) -> int:
        """Project the exact JSON string size before loading local media bytes."""

        reference = cls._coerce_reference_value(value)
        text = str(reference).strip()
        if not text:
            raise ValueError(f"{kind.capitalize()} reference cannot be empty.")

        if text.startswith("data:"):
            match = _DATA_URI_PATTERN.fullmatch(text)
            if match is None:
                # The normal validator supplies the precise error. This value
                # can never be submitted, so only a bounded projection is needed.
                return len(text.encode("utf-8")) + 2
            mime = match.group("mime").lower()
            if kind == "audio":
                mime = cls._normalize_audio_mime(mime)
            compact_size = len(match.group("data"))
            compact_size -= match.group("data").count("\r")
            compact_size -= match.group("data").count("\n")
            return len(f"data:{mime};base64,".encode("utf-8")) + compact_size + 2
        if text.startswith(("asset://", "http://", "https://")):
            return len(
                json.dumps(text, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            )

        try:
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
        base64_size = 4 * ((size + 2) // 3)
        return len(f"data:{mime};base64,".encode("ascii")) + base64_size + 2

    @classmethod
    def _preflight_broker_media_size(
        cls,
        payload: dict[str, Any],
        reference_fields: tuple[tuple[str, str, list[Any]], ...],
    ) -> None:
        """Reject an oversized request before any local media is materialized."""

        projected_payload = dict(payload)
        for field, _kind, values in reference_fields:
            if values:
                projected_payload[field] = ["" for _value in values]
        projected_bytes = len(
            json.dumps(
                projected_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if projected_bytes > MAX_REQUEST_BYTES:
            raise ValueError(
                "FN AI Broker request body exceeds the 64 MB limit. "
                "Reduce or externally host reference media."
            )
        for _field, kind, values in reference_fields:
            for value in values:
                # Each placeholder already contributed the two quote bytes.
                projected_bytes += (
                    cls._projected_prepared_reference_json_bytes(kind, value) - 2
                )
                if projected_bytes > MAX_REQUEST_BYTES:
                    raise ValueError(
                        "FN AI Broker request body exceeds the 64 MB limit. "
                        "Reduce or externally host reference media."
                    )

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
        try:
            return cls._encode_local_media_data_uri(path, mime)
        except OSError as exc:
            raise ValueError(
                f"{kind.capitalize()} reference cannot be read: {path}"
            ) from exc

    @staticmethod
    def _get_optional_secret(name: str) -> str:
        try:
            value = GriptapeNodes.SecretsManager().get_secret(
                name, should_error_on_not_found=False
            )
        except Exception:
            return ""
        return str(value or "").strip()

    @staticmethod
    def _normalize_gt_cloud_base_url(value: str) -> str:
        text = str(value or "").strip().rstrip("/")
        parsed = urlparse(text)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(
                "Griptape Cloud must use a credential-free HTTPS service URL."
            )
        return text

    @staticmethod
    def _resolve_gt_cloud_credential() -> str:
        secrets_manager = GriptapeNodes.SecretsManager()
        if callable(resolve_cloud_credential):
            try:
                value = resolve_cloud_credential(
                    secrets_manager,
                    secret_name=GT_CLOUD_API_KEY_SECRET,
                )
            except Exception:
                value = ""
        else:
            try:
                value = secrets_manager.get_secret(
                    GT_CLOUD_API_KEY_SECRET,
                    should_error_on_not_found=False,
                )
            except Exception:
                value = ""
        return str(value or "").strip()

    def _create_gt_cloud_storage_driver(self) -> GriptapeCloudStorageDriver:
        cloud_credential = self._resolve_gt_cloud_credential()
        if not cloud_credential:
            raise RuntimeError(
                "Griptape Cloud authentication is unavailable. Sign in to "
                "Griptape Cloud or add GT_CLOUD_API_KEY in Settings > Secrets."
            )
        base_url = self._normalize_gt_cloud_base_url(
            os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        )
        bucket_id = self._get_optional_secret(GT_CLOUD_BUCKET_ID_SECRET)
        if bucket_id:
            if not GriptapeCloudStorageDriver.bucket_exists(
                bucket_id,
                base_url=base_url,
                api_key=cloud_credential,
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
                    api_key=cloud_credential,
                    timeout=30.0,
                )
                or ""
            ).strip()
            if not bucket_id:
                raise RuntimeError(
                    "No default Griptape Cloud storage bucket is available."
                )
        config_manager = GriptapeNodes.ConfigManager()
        driver_kwargs = {
            "bucket_id": bucket_id,
            "api_key": cloud_credential,
            "base_url": base_url,
            "request_timeout": 30.0,
        }
        try:
            driver_parameters = inspect.signature(
                GriptapeCloudStorageDriver
            ).parameters
        except (TypeError, ValueError):
            driver_parameters = {}
        if "config_manager" in driver_parameters:
            # Current Griptape hosts require the ConfigManager itself so the
            # storage driver can resolve the active workspace safely.
            return GriptapeCloudStorageDriver(config_manager, **driver_kwargs)
        # Compatibility with older hosts whose driver accepted only the
        # resolved workspace directory.
        return GriptapeCloudStorageDriver(
            workspace_directory=config_manager.workspace_path,
            **driver_kwargs,
        )

    def _try_create_gt_cloud_storage_driver(
        self,
    ) -> GriptapeCloudStorageDriver | None:
        """Return one verified Cloud driver, or select the existing fallbacks.

        Missing authentication, an unavailable default bucket, or an inaccessible
        configured bucket means Cloud transport is not ready for this run.  The
        caller keeps images on the bounded Base64 JSON path and videos on their
        already-supported public URL / asset / explicitly selected TOS path.
        """

        try:
            return self._create_gt_cloud_storage_driver()
        except Exception as exc:
            logger.info(
                "%s Griptape Cloud media transport is unavailable; using existing "
                "media fallbacks (%s).",
                self.name,
                type(exc).__name__,
            )
            return None

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

    @staticmethod
    def _iter_local_video_upload_chunks(path: Path) -> Iterator[bytes]:
        """Yield one local upload as bounded chunks for signed HTTP storage."""

        try:
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(CLOUD_UPLOAD_READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
        except OSError as exc:
            raise LocalReferenceVideoError(
                f"Local reference video cannot be read: {path}"
            ) from exc

    @classmethod
    def _require_cloud_https_url(cls, value: Any, *, label: str) -> str:
        text = str(value or "").strip()
        parsed = urlparse(text)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or cls._is_non_public_http_url(text)
        ):
            raise RuntimeError(
                f"Griptape Cloud returned an invalid public HTTPS {label} URL."
            )
        return text

    @classmethod
    def _read_image_for_cloud_upload(
        cls,
        value: Any,
    ) -> tuple[bytes, str, str]:
        """Read one bounded image candidate without changing saved parameters."""

        reference = cls._coerce_reference_value(value)
        text = str(reference).strip()
        if text.startswith("data:"):
            normalized = cls._validate_data_uri("image", text)
            match = _DATA_URI_PATTERN.fullmatch(normalized)
            if match is None:  # _validate_data_uri already guarantees this.
                raise ValueError("Image data URI is invalid.")
            mime = match.group("mime").lower()
            content = base64.b64decode(match.group("data"), validate=True)
            suffix = next(
                (
                    candidate
                    for candidate, candidate_mime in IMAGE_MIME_BY_SUFFIX.items()
                    if candidate_mime == mime
                ),
                ".img",
            )
            return content, mime, f"reference-image{suffix}"

        try:
            path = Path(File(text).resolve())
        except FileLoadError as exc:
            raise ValueError(
                "Could not resolve image reference in the active Griptape project: "
                f"{text}"
            ) from exc
        if not path.is_file():
            raise ValueError(
                "Image reference file does not exist in the active Griptape "
                f"project: {text}"
            )
        mime = IMAGE_MIME_BY_SUFFIX.get(path.suffix.lower())
        if mime is None:
            raise ValueError(f"Unsupported image file type: {path.name}")
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"Image reference is empty: {path}")
        if size >= MAX_IMAGE_BYTES:
            raise ValueError(
                f"Image reference must be smaller than "
                f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB: {path.name}"
            )
        try:
            return path.read_bytes(), mime, path.name
        except OSError as exc:
            raise ValueError(f"Image reference cannot be read: {path}") from exc

    def _upload_image_to_griptape_cloud(
        self,
        driver: GriptapeCloudStorageDriver,
        value: Any,
    ) -> str:
        content, _mime, filename = self._read_image_for_cloud_upload(value)
        remote_path = Path("artifact_url_storage") / uuid4().hex / filename
        self._temporary_video_uploads.append((driver, remote_path))

        create_upload = getattr(driver, "create_signed_upload_url", None)
        create_download = getattr(driver, "create_signed_download_url", None)
        if not callable(create_upload) or not callable(create_download):
            public_url = driver.upload_file(
                path=remote_path,
                file_content=content,
                timeout=120.0,
            )
            return self._require_cloud_https_url(
                public_url,
                label="download",
            )

        upload = create_upload(remote_path)
        if not isinstance(upload, dict):
            raise RuntimeError(
                "Griptape Cloud returned an invalid signed upload contract."
            )
        method = str(upload.get("method") or "PUT").upper()
        upload_url = self._require_cloud_https_url(
            upload.get("url"),
            label="upload",
        )
        if method not in {"PUT", "POST"}:
            raise RuntimeError("Griptape Cloud returned an invalid upload method.")
        headers = {
            str(key): str(header_value)
            for key, header_value in dict(upload.get("headers") or {}).items()
            if str(key).lower() != "content-length"
        }
        headers["Content-Length"] = str(len(content))
        response = httpx.request(
            method,
            upload_url,
            content=content,
            headers=headers,
            timeout=120.0,
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        return self._require_cloud_https_url(
            create_download(remote_path),
            label="download",
        )

    def _upload_local_video_to_griptape_cloud(
        self,
        driver: GriptapeCloudStorageDriver,
        local_path: Path,
        remote_path: Path,
    ) -> str:
        """Stream through the driver's signed URL, with legacy fallback.

        Griptape Nodes 0.95 exposes signed upload/download methods, while older
        compatible drivers expose only ``upload_file(bytes)``.  Prefer the
        streaming contract so a large reference does not require a second
        whole-file bytes allocation; retain the legacy path for old hosts and
        test doubles.
        """

        create_upload = getattr(driver, "create_signed_upload_url", None)
        create_download = getattr(driver, "create_signed_download_url", None)
        if not callable(create_upload) or not callable(create_download):
            _path, content = self._read_local_video_for_upload(str(local_path))
            return self._require_cloud_https_url(
                driver.upload_file(
                    path=remote_path,
                    file_content=content,
                    timeout=120.0,
                ),
                label="download",
            )

        upload = create_upload(remote_path)
        if not isinstance(upload, dict):
            raise RuntimeError(
                "Cloud storage returned an invalid signed upload contract."
            )
        method = str(upload.get("method") or "PUT").upper()
        upload_url = self._require_cloud_https_url(
            upload.get("url"),
            label="upload",
        )
        if method not in {"PUT", "POST"}:
            raise RuntimeError(
                "Cloud storage returned an invalid signed upload method."
            )
        headers = {
            str(key): str(value)
            for key, value in dict(upload.get("headers") or {}).items()
            if str(key).lower() != "content-length"
        }
        headers["Content-Length"] = str(local_path.stat().st_size)
        response = httpx.request(
            method,
            upload_url,
            content=self._iter_local_video_upload_chunks(local_path),
            headers=headers,
            timeout=120.0,
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        return self._require_cloud_https_url(
            create_download(remote_path),
            label="download",
        )

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

    def _prepare_image_references_for_run(
        self,
        params: dict[str, Any],
        cloud_driver: Any = _CLOUD_DRIVER_UNSET,
    ) -> tuple[dict[str, Any], Any]:
        """Prefer Cloud HTTPS for embeddable images, preserving Base64 fallback."""

        values = [
            params.get("first_frame"),
            params.get("last_frame"),
            *(params.get("reference_images") or []),
        ]
        candidates: list[Any] = []
        for value in values:
            if not self._has_reference_value(value):
                continue
            text = str(self._coerce_reference_value(value)).strip()
            if text.startswith(("http://", "https://", "asset://")):
                continue
            candidates.append(value)

        if not candidates:
            return dict(params), cloud_driver
        if cloud_driver is _CLOUD_DRIVER_UNSET:
            cloud_driver = self._try_create_gt_cloud_storage_driver()
        if cloud_driver is None:
            # `_build_broker_payload` retains the bounded canonical Base64 JSON
            # conversion for local/data-URI image references.
            return dict(params), None

        def prepare(value: Any) -> Any:
            if not self._has_reference_value(value):
                return value
            text = str(self._coerce_reference_value(value)).strip()
            if text.startswith(("http://", "https://", "asset://")):
                return value
            return self._upload_image_to_griptape_cloud(cloud_driver, value)

        updated = dict(params)
        updated["first_frame"] = prepare(params.get("first_frame"))
        updated["last_frame"] = prepare(params.get("last_frame"))
        updated["reference_images"] = [
            prepare(value) for value in params.get("reference_images") or []
        ]
        return updated, cloud_driver

    def _prepare_video_references_for_run(
        self,
        params: dict[str, Any],
        cloud_driver: Any = _CLOUD_DRIVER_UNSET,
    ) -> dict[str, Any]:
        """Prepare image/video transport without changing selected media order."""

        params, cloud_driver = self._prepare_image_references_for_run(
            params,
            cloud_driver,
        )
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
                local_path = self._resolve_local_video_path(text)
                upload_service = params.get(
                    "local_video_upload_service", LOCAL_VIDEO_UPLOAD_GRIPTAPE
                )
                if cloud_driver is _CLOUD_DRIVER_UNSET:
                    cloud_driver = self._try_create_gt_cloud_storage_driver()
                if cloud_driver is not None:
                    remote_path = (
                        Path("artifact_url_storage")
                        / uuid4().hex
                        / local_path.name
                    )
                    self._temporary_video_uploads.append(
                        (cloud_driver, remote_path)
                    )
                    public_url = self._upload_local_video_to_griptape_cloud(
                        cloud_driver,
                        local_path,
                        remote_path,
                    )
                elif upload_service == LOCAL_VIDEO_UPLOAD_TOS:
                    if tos_context is None:
                        tos_context = self._create_tos_storage_context(params)
                    public_url = self._upload_local_video_to_tos(
                        local_path, params, tos_context
                    )
                else:
                    raise RuntimeError(
                        "Griptape Cloud authentication or bucket access is not "
                        "available for this local video. Use a public HTTPS URL, "
                        "a Volcengine asset:// reference, or select a configured "
                        "Volcengine TOS transport."
                    )
            except LocalReferenceVideoError:
                # Preserve the actionable local/project-path diagnosis. The
                # generic upload-service hint is only appropriate after a
                # readable local file reached the selected storage service.
                raise
            except Exception as exc:
                raise RuntimeError(
                    "Local reference-video publishing failed through an allowed "
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
        # Seedance 2.5 uses the provider's canonical resolution enum.  Keeping
        # the legacy 720-pixel dimensions here produced contradictory requests
        # such as ``quality=1080p`` beside ``resolution=1280x720``.  Aspect
        # ratio is transported independently, so 2.5 must publish the exact
        # validated 720p/1080p choice for every orientation.  Preserve the
        # established pixel-shaped Broker compatibility field for 2.0.
        broker_resolution = (
            params["resolution"]
            if params["model_id"] == SEEDANCE_2_5_MODEL_ID
            else (
                "720x1280"
                if params["ratio"] in {"9:16", "3:4"}
                else "1280x720"
            )
        )
        task = str(params.get(TASK_PARAMETER) or TASK_REFERENCE_TO_VIDEO)
        input_mode = TASK_INPUT_MODES[task]
        payload: dict[str, Any] = {
            "provider": "volcengine_ark",
            "model": params["model_id"],
            "prompt": params["prompt"].strip(),
            TASK_PARAMETER: task,
            "input_mode": input_mode,
            "duration_seconds": params["duration"],
            "quality": params["resolution"],
            "resolution": broker_resolution,
            "aspect_ratio": params["ratio"],
            "generate_audio": params["generate_audio"],
            "watermark": params["watermark"],
            "web_search": False,
            "content_filter": True,
            "execution_expires_after": params["execution_expires_after"],
        }
        if params["model_id"] == SEEDANCE_2_5_MODEL_ID:
            payload["output_format"] = str(
                params.get("output_format") or DEFAULT_OUTPUT_FORMAT
            )
            payload["return_last_frame"] = bool(
                params.get("return_last_frame", False)
            )
        if params["model_id"] == SEEDANCE_2_0_MODEL_ID:
            payload["priority"] = params["priority"]
        reference_fields: tuple[tuple[str, str, list[Any]], ...] = ()
        if input_mode == INPUT_MODE_FIRST_LAST_FRAME:
            reference_fields = (
                (
                    "first_frame",
                    "image",
                    [params["first_frame"]] if params["first_frame"] else [],
                ),
                (
                    "last_frame",
                    "image",
                    [params["last_frame"]] if params["last_frame"] else [],
                ),
            )
        elif input_mode == INPUT_MODE_MULTIMODAL_REFERENCES:
            reference_fields = (
                ("image_urls", "image", list(params["reference_images"])),
                ("video_urls", "video", list(params["video_references"])),
                ("audio_urls", "audio", list(params["reference_audio"])),
            )
        self._preflight_broker_media_size(payload, reference_fields)
        if input_mode == INPUT_MODE_FIRST_LAST_FRAME:
            if params["first_frame"]:
                payload["first_frame"] = [
                    self._prepare_media_reference("image", params["first_frame"])
                ]
            if params["last_frame"]:
                payload["last_frame"] = [
                    self._prepare_media_reference("image", params["last_frame"])
                ]
        elif input_mode == INPUT_MODE_MULTIMODAL_REFERENCES:
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
    def _broker_named_result_url(
        cls,
        value: Any,
        names: frozenset[str],
        *,
        depth: int = 0,
    ) -> str:
        """Find one explicitly named result URL without confusing media roles."""

        if depth > 5:
            return ""
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).casefold() in names:
                    candidate = cls._broker_result_url(item, depth=depth + 1)
                    if candidate:
                        return candidate
            for key in ("content", "response", "result", "data", "output"):
                if key in value:
                    candidate = cls._broker_named_result_url(
                        value.get(key),
                        names,
                        depth=depth + 1,
                    )
                    if candidate:
                        return candidate
        elif isinstance(value, list):
            for item in value:
                candidate = cls._broker_named_result_url(
                    item,
                    names,
                    depth=depth + 1,
                )
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
        last_frame_url = cls._broker_named_result_url(
            response,
            frozenset({"last_frame_url", "lastframe_url"}),
        )
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
        if video_url or last_frame_url:
            task["content"] = {}
            if video_url:
                task["content"]["video_url"] = video_url
            if last_frame_url:
                task["content"]["last_frame_url"] = last_frame_url
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
        preview_action: str = "none",
    ) -> None:
        if getattr(self, "_hmb_node_deleted", False):
            return
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
        self._publish_generation_preview(
            self._generation_preview_phase_for_status(status),
            generation_id=generation_id,
            action=preview_action,
        )

    def _set_generation_status(
        self,
        status: str,
        *,
        generation_id: str | None = None,
        preview_action: str = "none",
    ) -> None:
        if getattr(self, "_hmb_node_deleted", False):
            return
        self.parameter_output_values["generation_status"] = status
        self._publish_generation_preview(
            self._generation_preview_phase_for_status(status),
            generation_id=generation_id,
            action=preview_action,
        )

    async def _download_broker_video(self, url: str) -> bytes:
        bridge = self._get_broker_bridge()
        if bridge.is_trusted_broker_url(url):
            return await asyncio.to_thread(
                bridge.download_trusted_result,
                url,
                max_bytes=MAX_DOWNLOAD_BYTES,
                media_type="video",
            )
        return await self._download_video(url)

    async def _download_broker_image(self, url: str) -> bytes:
        """Download one returned PNG without leaking Broker auth off-origin."""

        bridge = self._get_broker_bridge()
        if bridge.is_trusted_broker_url(url):
            return await asyncio.to_thread(
                bridge.download_trusted_result,
                url,
                max_bytes=MAX_LAST_FRAME_BYTES,
                media_type="image",
            )
        return await self._download_image(url)

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
            redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
            # httpx status errors include the complete request URL. Signed
            # Cloud/TOS URLs carry credentials in their query string, so retain
            # only the non-secret origin/path in every public error message.
            return _SIGNED_URL_QUERY_PATTERN.sub(
                r"\g<base>?[REDACTED]",
                redacted,
            )
        return value

    @classmethod
    def _safe_exception_message(cls, exc: BaseException, secret: str = "") -> str:
        message = str(exc) or type(exc).__name__
        return str(cls._redact_sensitive(message, secret))


    @staticmethod
    def _resolve_host_addresses(hostname: str, port: int) -> tuple[str, ...]:
        try:
            return (str(ipaddress.ip_address(hostname)),)
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
        addresses: list[str] = []
        for record in records:
            if not record or not record[4]:
                continue
            address = str(record[4][0]).split("%", 1)[0]
            if address not in addresses:
                addresses.append(address)
        return tuple(addresses)

    async def _validate_download_url(self, url: str) -> tuple[str, ...]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(
                "External result download URL must use HTTPS."
            )
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Video download URL must not contain user credentials.")
        try:
            port = parsed.port or 443
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
        return addresses

    @staticmethod
    def _pinned_download_target(
        url: str,
        address: str,
    ) -> tuple[str, str, str]:
        """Return an IP-pinned URL plus the original HTTP Host and TLS SNI.

        DNS is resolved and classified before this helper is called.  The
        socket target is then the validated literal address, so HTTPX cannot
        perform a second attacker-controlled lookup between validation and
        connection.  The original hostname remains both the Host header and
        TLS SNI/certificate identity.
        """

        parsed = urlparse(url)
        hostname = str(parsed.hostname or "")
        if not hostname:
            raise ValueError("External result download URL has no hostname.")
        try:
            port = parsed.port or 443
        except ValueError as exc:
            raise ValueError("Video download URL contains an invalid port.") from exc
        normalized_address = str(ipaddress.ip_address(address))
        ip_authority = (
            f"[{normalized_address}]"
            if ":" in normalized_address
            else normalized_address
        )
        if parsed.port is not None:
            ip_authority = f"{ip_authority}:{port}"

        try:
            sni_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(
                "External result download URL contains an invalid hostname."
            ) from exc
        host_authority = (
            f"[{sni_hostname}]" if ":" in sni_hostname else sni_hostname
        )
        if parsed.port is not None:
            host_authority = f"{host_authority}:{port}"
        pinned_url = parsed._replace(netloc=ip_authority).geturl()
        return pinned_url, host_authority, sni_hostname

    async def _download_external_media(
        self,
        url: str,
        *,
        accept: str,
        max_bytes: int,
        media_label: str,
    ) -> bytes:
        timeout = httpx.Timeout(connect=20.0, read=300.0, write=60.0, pool=20.0)
        current_url = url
        attempts = 0
        redirects = 0
        while attempts < 3:
            validated_addresses = await self._validate_download_url(current_url)
            pinned_url, host_header, sni_hostname = self._pinned_download_target(
                current_url,
                validated_addresses[attempts % len(validated_addresses)],
            )
            try:
                # External signed result URLs are downloaded without Broker
                # authorization; its access token must never leave Broker origin.
                # Environment proxies are disabled so the validated public IP
                # remains the actual socket destination.
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "GET",
                        pinned_url,
                        headers={"Accept": accept, "Host": host_header},
                        extensions={"sni_hostname": sni_hostname},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise RuntimeError(
                                    f"{media_label} download redirect did not include a destination."
                                )
                            redirects += 1
                            if redirects > 5:
                                raise RuntimeError(
                                    f"{media_label} download exceeded the five-redirect limit."
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
                                f"{media_label} download failed with HTTP {response.status_code}."
                            )

                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                declared_length = int(content_length)
                            except ValueError as exc:
                                raise RuntimeError(
                                    f"{media_label} download returned an invalid Content-Length."
                                ) from exc
                            if declared_length > max_bytes:
                                raise RuntimeError(
                                    f"Downloaded {media_label.lower()} exceeds the safety limit."
                                )

                        content_type = response.headers.get("content-type", "").lower()
                        if "json" in content_type or "text/html" in content_type:
                            raise RuntimeError(
                                f"Result {media_label.lower()} URL returned a non-media response."
                            )

                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(content) + len(chunk) > max_bytes:
                                raise RuntimeError(
                                    f"Downloaded {media_label.lower()} exceeds the safety limit."
                                )
                            content.extend(chunk)
            except httpx.TransportError as exc:
                attempts += 1
                if attempts < 3:
                    await self._sleep(min(2 ** (attempts - 1), 5))
                    continue
                raise RuntimeError(
                    f"{media_label} download failed ({type(exc).__name__})."
                ) from exc

            if not content:
                raise RuntimeError(f"Result returned an empty {media_label.lower()} file.")
            return bytes(content)
        raise RuntimeError(f"{media_label} download exhausted its retry limit.")

    async def _download_video(self, url: str) -> bytes:
        video_bytes = await self._download_external_media(
            url,
            accept="video/mp4,video/quicktime,application/octet-stream",
            max_bytes=MAX_DOWNLOAD_BYTES,
            media_label="Video",
        )
        if not _is_structurally_valid_mp4(video_bytes):
            raise RuntimeError(
                "Downloaded result is not a valid MP4/MOV container."
            )
        return video_bytes

    async def _download_image(self, url: str) -> bytes:
        image_bytes = await self._download_external_media(
            url,
            accept="image/png,application/octet-stream",
            max_bytes=MAX_LAST_FRAME_BYTES,
            media_label="Last-frame image",
        )
        if not _is_valid_png(image_bytes):
            raise RuntimeError("Downloaded last frame is not a valid PNG image.")
        return image_bytes

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
        if getattr(self, "_hmb_node_deleted", False):
            return
        previous_video = self._capture_last_success_video()
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["generation_status"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = previous_video
        self.parameter_output_values["VIDEO_OUT"] = previous_video
        self.parameter_output_values["last_frame_url"] = (
            self._hmb_last_success_last_frame_url
            if previous_video is not None
            else None
        )

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

    async def _run_blocking_generation_stage(
        self,
        operation: Any,
        *args: Any,
    ) -> Any:
        """Run blocking preparation without freezing the host event loop.

        ``asyncio.to_thread`` work keeps running when its awaiter is cancelled.
        Shield it and wait for completion before propagating cancellation so a
        late upload cannot append temporary objects after cleanup has already
        run. This preserves the existing no-leak/no-duplicate submission
        contract while allowing the canvas and controls to keep painting.
        """

        task = asyncio.create_task(asyncio.to_thread(operation, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            with suppress(Exception):
                await task
            raise

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
    def _normalized_video_output_path(
        value: str | Path,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
    ) -> Path:
        requested = str(output_format or "").strip().lower()
        if requested not in OUTPUT_FORMAT_CHOICES:
            raise ValueError(f"Unsupported video output format: {requested!r}.")
        path = Path(value)
        desired_suffix = "." + requested
        compatible_suffixes = {".mp4", ".m4v"} if requested == "mp4" else {".mov"}
        if path.suffix.lower() not in compatible_suffixes:
            path = path.with_suffix(desired_suffix)
        return path

    @staticmethod
    def _normalized_mp4_output_path(value: str | Path) -> Path:
        """Backward-compatible wrapper for existing MP4 publication tests."""

        return HMBSeedanceGeneration._normalized_video_output_path(value, "mp4")

    @classmethod
    def _output_destination_candidate_records(
        cls,
        destination: Any,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
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
                    yield (
                        cls._normalized_video_output_path(
                            destination.resolve(), output_format
                        ),
                        None,
                    )
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
                        cls._normalized_video_output_path(
                            File(indexed_path).resolve(), output_format
                        ),
                        index,
                    )
                return

        base_path = cls._normalized_video_output_path(
            destination.resolve(), output_format
        )
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
        output_format: str = DEFAULT_OUTPUT_FORMAT,
    ) -> Iterator[Path]:
        """Yield collision candidates without reserving or writing a file."""

        for candidate, _macro_index in cls._output_destination_candidate_records(
            destination,
            output_format,
        ):
            yield candidate

    @classmethod
    def _preflight_output_destination(
        cls,
        destination: Any,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
    ) -> Path:
        """Resolve and write-probe the local target before any billable POST."""

        if bool(getattr(destination, "_append", False)):
            raise ValueError("Generated video output does not support append mode.")
        policy = cls._output_destination_policy(destination)
        candidates = cls._output_destination_candidate_records(
            destination,
            output_format,
        )
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
        """Pace a create POST, then preserve its cancellation-safe outcome."""

        # Keep cadence reservation and the actual POST in the same worker so a
        # delayed OS reschedule cannot compress two creates back together.
        # A small state lock lets local cancellation win safely while the
        # worker is still queued behind the cadence gate.
        start_state_lock = threading.Lock()
        cancel_before_start = threading.Event()
        submission_started = False

        def invoke_paced_submission() -> Any:
            nonlocal submission_started
            _broker_wait_for_submission_slot()
            with start_state_lock:
                if cancel_before_start.is_set() or not self._submission_start_is_authorized(
                    require_registered=False
                ):
                    raise _SubmissionCancelledBeforeStart()
                submission_started = True
            return function(*args, **kwargs)

        operation = asyncio.create_task(asyncio.to_thread(invoke_paced_submission))
        try:
            return await asyncio.shield(operation), False
        except asyncio.CancelledError:
            with start_state_lock:
                started_remotely = submission_started
                if not started_remotely:
                    cancel_before_start.set()

            self._detached_submission_tasks.add(operation)

            def consume_detached_result(completed: asyncio.Task[Any]) -> None:
                self._detached_submission_tasks.discard(completed)
                try:
                    completed.result()
                except (asyncio.CancelledError, _SubmissionCancelledBeforeStart):
                    return
                except Exception as exc:
                    logger.warning(
                        "%s detached Broker submission finished after local "
                        "cancellation with %s; remote state remains unknown.",
                        self.name,
                        type(exc).__name__,
                    )

            operation.add_done_callback(consume_detached_result)
            if not started_remotely:
                # No remote request was made, so ordinary cancellation cleanup
                # remains authoritative and no ambiguous task is reported.
                raise

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
                    preview_action="refresh_existing",
                )
            raise

    @classmethod
    async def _atomic_publish_completed_video(
        cls,
        destination: Any,
        content: bytes,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        verifier: _MP4DecodeVerifier | None = None,
    ) -> File:
        requested = str(output_format or "").strip().lower()
        if requested not in OUTPUT_FORMAT_CHOICES:
            raise ValueError(f"Unsupported video output format: {requested!r}.")
        if not _video_container_matches_format(content, requested):
            raise RuntimeError(
                f"Generated result is not a valid {requested.upper()} container."
            )
        cls._preflight_output_destination(destination, requested)
        policy = cls._output_destination_policy(destination)
        candidates = cls._output_destination_candidate_records(
            destination,
            requested,
        )
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
                    "Generated video was saved, but its metadata sidecar could not "
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
                    "Could not map generated video to a project macro: %s",
                    type(exc).__name__,
                )
        return saved

    @classmethod
    async def _atomic_publish_completed_mp4(
        cls,
        destination: Any,
        content: bytes,
        verifier: _MP4DecodeVerifier | None = None,
    ) -> File:
        """Compatibility wrapper retained for existing MP4-only callers."""

        return await cls._atomic_publish_completed_video(
            destination,
            content,
            "mp4",
            verifier,
        )

    @classmethod
    async def _atomic_publish_completed_png(
        cls,
        destination: Any,
        content: bytes,
    ) -> File:
        """Validate and atomically publish an optional returned last frame."""

        if not _is_valid_png(content):
            raise RuntimeError("Generated last frame is not a valid PNG image.")
        if bool(getattr(destination, "_append", False)):
            raise ValueError("Generated last-frame output does not support append mode.")
        base_path = Path(destination.resolve())
        if base_path.suffix.lower() != ".png":
            base_path = base_path.with_suffix(".png")
        policy = cls._output_destination_policy(destination)
        candidates = [base_path]
        if policy is ExistingFilePolicy.CREATE_NEW:
            candidates.extend(
                base_path.with_name(f"{base_path.stem}_{index}.png")
                for index in range(1, MAX_ATOMIC_OUTPUT_CANDIDATES + 1)
            )
        published: Path | None = None
        for candidate in candidates:
            if policy is ExistingFilePolicy.CREATE_NEW and candidate.exists():
                continue
            if policy is ExistingFilePolicy.FAIL and candidate.exists():
                raise FileExistsError(
                    f"Generated last-frame output already exists: {candidate}"
                )
            if candidate.exists() and not candidate.is_file():
                raise IsADirectoryError(
                    f"Generated last-frame output is not a file: {candidate}"
                )
            create_parents = bool(getattr(destination, "_create_parents", True))
            if not candidate.parent.exists():
                if not create_parents:
                    raise FileNotFoundError(
                        "Generated last-frame output directory does not exist: "
                        f"{candidate.parent}"
                    )
                candidate.parent.mkdir(parents=True, exist_ok=True)
            cls._probe_output_parent_writable(candidate.parent)
            stage = candidate.parent / (
                f".{candidate.stem}.{uuid4().hex}.partial.png"
            )
            try:
                written = await File(str(stage)).awrite_bytes(
                    content,
                    existing_file_policy=ExistingFilePolicy.FAIL,
                    append=False,
                    create_parents=False,
                    coerce_extension_to_match_bytes=False,
                )
                if Path(written) != stage or stage.stat().st_size != len(content):
                    raise OSError(
                        "Generated last-frame staging file was not written completely."
                    )
                if not _is_valid_png(stage.read_bytes()):
                    raise RuntimeError(
                        "Generated last-frame staging file failed PNG verification."
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
                    break
            finally:
                with suppress(OSError):
                    stage.unlink()
        if published is None:
            raise FileExistsError(
                "No unused generated last-frame output filename is available."
            )
        saved = File(str(published))
        mapper = getattr(destination, "_map_to_macro_file", None)
        if callable(mapper):
            try:
                saved = mapper(saved)
            except Exception as exc:
                logger.warning(
                    "Could not map generated last frame to a project macro: %s",
                    type(exc).__name__,
                )
        return saved

    async def _save_completed_task(
        self,
        final_task: dict[str, Any],
        generation_id: str,
        destination: Any,
        verifier: _MP4DecodeVerifier | None = None,
        *,
        model_id: str | None = None,
        output_format: str | None = None,
        return_last_frame: bool | None = None,
    ) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            return
        video_download_url = self._extract_video_url(final_task)
        if not video_download_url:
            raise RuntimeError(
                "FN AI Broker task succeeded but the video URL was missing."
            )
        self._publish_generation_preview(
            "downloading",
            generation_id=generation_id,
        )
        video_bytes = await self._download_broker_video(video_download_url)
        if not self._runtime_node_is_live(require_registered=True):
            return
        self._publish_generation_preview(
            "verifying",
            generation_id=generation_id,
        )
        if model_id is None:
            raw_model = str(
                self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
            ).strip()
            effective_model_id = MODEL_ID_ALIASES.get(raw_model, raw_model)
        else:
            effective_model_id = str(model_id).strip()
        requested_format = str(
            output_format
            if output_format is not None
            else self.get_parameter_value("output_format")
            or DEFAULT_OUTPUT_FORMAT
        ).strip().lower()
        effective_output_format = (
            requested_format
            if effective_model_id == SEEDANCE_2_5_MODEL_ID
            else DEFAULT_OUTPUT_FORMAT
        )
        saved = await self._atomic_publish_completed_video(
            destination,
            video_bytes,
            effective_output_format,
            verifier,
        )
        if not self._runtime_node_is_live(require_registered=True):
            return
        artifact = VideoUrlArtifact(value=saved.location, name=saved.name)
        frame_artifact: ImageUrlArtifact | None = None
        requested_last_frame = (
            bool(return_last_frame)
            if return_last_frame is not None
            else bool(self.get_parameter_value("return_last_frame"))
        )
        wants_last_frame = bool(
            effective_model_id == SEEDANCE_2_5_MODEL_ID and requested_last_frame
        )
        if wants_last_frame:
            last_frame_download_url = self._extract_last_frame_url(final_task)
            if last_frame_download_url:
                try:
                    frame_bytes = await self._download_broker_image(
                        last_frame_download_url
                    )
                    frame_destination = self._last_frame_file.build_file()
                    saved_frame = await self._atomic_publish_completed_png(
                        frame_destination,
                        frame_bytes,
                    )
                    frame_artifact = ImageUrlArtifact(
                        value=saved_frame.location,
                        name=saved_frame.name,
                    )
                except Exception as exc:
                    # The paid, verified video remains a success. Never include
                    # the signed frame URL in the warning or persistent state.
                    logger.warning(
                        "Generated video was saved, but its optional last frame "
                        "could not be published locally (%s).",
                        type(exc).__name__,
                    )
            else:
                logger.warning(
                    "Generated video was saved, but the requested last frame "
                    "was absent from the Broker result."
                )
        if not self._runtime_node_is_live(require_registered=True):
            return
        self.parameter_output_values["video_url"] = artifact
        self.parameter_output_values["VIDEO_OUT"] = artifact
        self.parameter_output_values["last_frame_url"] = frame_artifact
        self._hmb_last_success_video = artifact
        self._hmb_last_success_last_frame_url = frame_artifact
        self._hmb_generation_media_revision = min(
            2_147_483_647,
            self._hmb_generation_media_revision + 1,
        )
        self._publish_generation_preview(
            "succeeded",
            generation_id=generation_id,
        )
        self._set_generation_recovery_checkpoint(
            stage="local_succeeded",
            task_id=generation_id,
            # Reaching this boundary proves that the Broker returned a
            # completed task and that its video was downloaded, decoded,
            # verified, and atomically published.  A recovery that began with
            # an idempotent ``client_request`` identity is therefore promoted
            # to an authoritative Broker task here.  Keeping the provisional
            # identity would make the completed render block every later Run.
            task_identity="broker_task",
            status="succeeded",
            params={
                "model_id": effective_model_id,
                "output_format": effective_output_format,
                "return_last_frame": requested_last_frame,
            },
        )
        await self._force_save_generation_recovery_checkpoint(
            required=False,
            reason="local_succeeded",
        )
        self._submission_outcome_unknown = False
        if not self._runtime_node_is_live(require_registered=True):
            return
        self._set_status_results(
            was_successful=True,
            result_details=(
                f"SUCCESS: FN AI Broker task {generation_id} succeeded.\n"
                f"Saved {effective_output_format.upper()}: {saved.location}"
            ),
        )

    async def _refresh_async(self) -> None:
        """Refresh one Broker job without ever creating a replacement task."""
        if not self._runtime_node_is_live(require_registered=True):
            return
        # A running generation already owns automatic polling.  Mixing a
        # manual refresh into it can race output publication even though both
        # operations target the same server job.
        if self._generation_run_active.is_set():
            return
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
            if self._hmb_generation_started_monotonic is None:
                self._hmb_generation_started_monotonic = self._monotonic()
                self._hmb_generation_started_at_ms = int(time.time() * 1000)
            generation_id = self._validate_task_id(generation_id)
            self._publish_generation_preview(
                "retrieving",
                generation_id=generation_id,
                action="none",
            )
            bridge = await self._ensure_broker_connected()
            if not self._runtime_node_is_live(require_registered=True):
                return
            # Refresh retrieves status for this authoritative job only.  In
            # particular, an uncertain submission never replays
            # generate_seedance (the create-task request) here.
            response = await asyncio.to_thread(
                bridge.refresh_job,
                generation_id,
                timeout=60,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            task = self._normalize_broker_task(
                response,
                fallback_job_id=generation_id,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            status = str(task["status"])
            refresh_params = self._get_parameters()
            recovery_contract = self._generation_recovery_state()
            requested_generation_id = generation_id
            resolved_generation_id = str(task["id"])
            if (
                resolved_generation_id != requested_generation_id
                and not (
                    recovery_contract.get("task_identity") == "client_request"
                    and recovery_contract.get("task_id")
                    == requested_generation_id
                )
            ):
                raise _BrokerProtocolError(
                    "FN AI Broker returned a different task ID while refreshing "
                    "an identity that was not a matching provisional request."
                )
            # A successful status lookup resolves a provisional idempotency
            # key into an actual Broker task.  The Broker may retain the same
            # hmb-* value or return a canonical job ID; either form is now an
            # authoritative task identity and must replace the provisional
            # recovery identity.
            generation_id = resolved_generation_id
            recovery_destination = (
                self._build_recovery_output_destination(recovery_contract)
                if status == "succeeded"
                else None
            )
            if recovery_contract.get("task_id") == requested_generation_id:
                if recovery_contract.get("model_id"):
                    refresh_params["model_id"] = recovery_contract["model_id"]
                if recovery_contract.get("output_format"):
                    refresh_params["output_format"] = recovery_contract[
                        "output_format"
                    ]
                refresh_params["return_last_frame"] = bool(
                    recovery_contract.get("return_last_frame")
                )
            self._set_broker_task_outputs(
                task,
                generation_id=generation_id,
                status=status,
                preview_action=(
                    "refresh_existing"
                    if status in {"queued", "running"}
                    else "none"
                ),
            )
            self._set_generation_recovery_checkpoint(
                stage=(
                    "remote_succeeded"
                    if status == "succeeded"
                    else "terminal"
                    if status in TERMINAL_FAILURE_STATUSES
                    or task.get("terminal") is True
                    else "refresh"
                ),
                task_id=generation_id,
                task_identity="broker_task",
                status=status,
                params=refresh_params,
                terminal=bool(
                    status in TERMINAL_FAILURE_STATUSES
                    or task.get("terminal") is True
                ),
            )
            await self._force_save_generation_recovery_checkpoint(
                required=False,
                reason="manual_refresh",
            )
            if status == "succeeded":
                refresh_output_format = str(
                    refresh_params.get("output_format") or DEFAULT_OUTPUT_FORMAT
                )
                destination = recovery_destination
                if destination is None:
                    raise RuntimeError(
                        "Seedance recovery output destination is unavailable."
                    )
                self._preflight_output_destination(
                    destination,
                    refresh_output_format,
                )
                await self._save_completed_task(
                    task,
                    generation_id,
                    destination,
                    model_id=str(refresh_params["model_id"]),
                    output_format=refresh_output_format,
                    return_last_frame=bool(
                        refresh_params.get("return_last_frame")
                    ),
                )
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
            if not self._runtime_node_is_live(require_registered=True):
                return
            recovery_checkpoint = self._generation_recovery_state()
            definitive_missing_client_request = bool(
                isinstance(exc, _BrokerError)
                and exc.status_code in {404, 410}
                and recovery_checkpoint.get("task_identity") == "client_request"
                and recovery_checkpoint.get("task_id") == generation_id
            )
            if definitive_missing_client_request:
                # The durable pre-submit identity can legitimately exist even
                # when the process stopped before POST. Only an explicit Broker
                # not-found/gone response for that provisional identity proves
                # that no same-task recovery remains and permits a later create.
                self.parameter_output_values["generation_id"] = ""
                self.parameter_output_values["provider_response"] = None
                self._clear_generation_recovery_checkpoint()
                self._set_generation_status(
                    "failed",
                    generation_id="",
                    preview_action="none",
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False,
                    reason="client_request_not_found",
                )
                self._set_status_results(
                    was_successful=False,
                    result_details=(
                        "The Broker confirmed that the saved pre-submit request no "
                        "longer identifies a server task. Recovery was cleared; no "
                        "replacement render was started automatically."
                    ),
                )
                return
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
                preview_action = "none"
            else:
                detail = (
                    "The Broker connection is currently unavailable, but the existing "
                    f"task {generation_id or 'ID'} may still be rendering. Refresh / "
                    "Retrieve Result checks the same job without creating a duplicate. "
                    "Details: "
                    + safe_detail
                )
                preview_action = "refresh_existing" if generation_id else "none"
            self._publish_generation_preview(
                "failed",
                generation_id=generation_id,
                action=preview_action,
            )
            self._set_status_results(
                was_successful=False,
                result_details=detail,
            )

    def _on_refresh_clicked(
        self,
        _button: Any,
        _details: Any,
    ) -> NodeMessageResult:
        if not self._runtime_node_is_live(require_registered=True):
            return NodeMessageResult(
                success=False,
                details="Seedance refresh is unavailable because the node is inactive.",
                response=_details,
                altered_workflow_state=False,
            )
        with self._generation_refresh_lock:
            if (
                self._generation_refresh_running
                or self._generation_run_active.is_set()
            ):
                return NodeMessageResult(
                    success=True,
                    details=(
                        "Seedance refresh was acknowledged, but this node is already "
                        "busy; no duplicate request was scheduled."
                    ),
                    response=_details,
                    altered_workflow_state=False,
                )
            self._generation_refresh_running = True

        def _finished(_future: Any = None) -> None:
            with self._generation_refresh_lock:
                self._generation_refresh_running = False

        try:
            event_loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if event_loop is not None and event_loop.is_running():
                # Retained parameter/output state belongs to Griptape's engine
                # loop. _refresh_async offloads Broker and media blocking work,
                # so scheduling the coroutine here keeps node mutation ordered
                # without occupying the loop during network I/O.
                future = asyncio.run_coroutine_threadsafe(
                    self._refresh_async(), event_loop
                )
                future.add_done_callback(_finished)
                return NodeMessageResult(
                    success=True,
                    details="Existing Seedance task refresh was scheduled.",
                    response=_details,
                    altered_workflow_state=False,
                )
        except Exception:
            pass

        def _runner() -> None:
            # Compatibility hosts without an initialized EventManager loop use
            # an isolated fallback. Normal desktop execution takes the ordered
            # engine-loop path above.
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
        except Exception as exc:
            _finished()
            logger.warning(
                "%s could not schedule the existing-task refresh (%s).",
                self.name,
                type(exc).__name__,
            )
            return NodeMessageResult(
                success=False,
                details="Existing Seedance task refresh could not be scheduled.",
                response=_details,
                altered_workflow_state=False,
            )
        return NodeMessageResult(
            success=True,
            details="Existing Seedance task refresh was scheduled.",
            response=_details,
            altered_workflow_state=False,
        )

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        """Invalidate every delayed Broker/UI callback without blocking delete."""

        # Run before marking this object deleted. If recovery cannot remove an
        # already-invalid dynamic-list edge, raising ValueError lets the host
        # abort cleanly without leaving a live node that has surrendered Shot
        # ownership.
        self._discard_dangling_owned_list_connections_before_delete()
        if not bool(getattr(self, "_hmb_node_deleted", False)):
            self._hmb_node_deleted = True
            with self._generation_refresh_lock:
                self._generation_run_active.clear()
                self._generation_refresh_running = False
            with self._broker_action_lock:
                self._broker_action_running = False
            for task in tuple(self._detached_submission_tasks):
                with suppress(Exception):
                    task.cancel()
            self._detached_submission_tasks.clear()
            # Release this exact (channel_uuid, shot_uuid) claim while the host
            # still exposes the deleted object as a same-flow anchor.  The
            # shared helper excludes `_hmb_node_deleted`, so surviving Seedance
            # selectors immediately regain the Shot without another user edit.
            with suppress(Exception):
                _shot_routing.schedule_post_deletion_reconcile(self)
        if bool(getattr(self, "_hmb_delete_parent_called", False)):
            return None
        self._hmb_delete_parent_called = True
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None

    async def _process_generation(self) -> None:
        await self._run_blocking_generation_stage(
            self._cleanup_temporary_video_uploads
        )
        self._submission_outcome_unknown = False
        try:
            await self._process_generation_impl()
        finally:
            if self._submission_outcome_unknown:
                self._defer_temporary_video_upload_cleanup()
            else:
                await self._run_blocking_generation_stage(
                    self._cleanup_temporary_video_uploads
                )

    async def _process_generation_impl(self) -> None:
        """Submit and poll Seedance exclusively through the FN AI Broker."""
        if not self._runtime_node_is_live(require_registered=True):
            return
        requested_resume_id = str(
            self.get_parameter_value("resume_generation_id") or ""
        ).strip()
        if not requested_resume_id:
            self._assert_new_submission_is_safe()
        self._set_safe_defaults()
        self._begin_generation_preview()
        self._set_generation_status("resolving_inputs", generation_id="")
        params = self._get_parameters()
        if not params["resume_generation_id"]:
            # Resolve and validate the selected ImageAsset/VideoPicker Shot
            # before destination preparation, authentication, uploads, or a
            # billable Broker create-task request. Prompt text remains manual.
            params = self._resolve_exact_shot_generation_inputs(params)
        self._validate_parameters(params)
        resume_generation_id = params["resume_generation_id"]
        decode_verifier: _MP4DecodeVerifier | None = None

        # Resolve the save target before the billable Broker POST.
        self._set_generation_status("preparing_output", generation_id="")
        destination = self._output_file.build_file()
        self._preflight_output_destination(
            destination,
            str(params.get("output_format") or DEFAULT_OUTPUT_FORMAT),
        )
        advanced_seedance_v2 = bool(
            not resume_generation_id
            and params.get("model_id") == SEEDANCE_2_5_MODEL_ID
            and _HMBAIBrokerBridge._seedance_v2_requested(
                task=str(
                    params.get(TASK_PARAMETER) or TASK_REFERENCE_TO_VIDEO
                ),
                output_format=str(
                    params.get("output_format") or DEFAULT_OUTPUT_FORMAT
                ),
                return_last_frame=bool(params.get("return_last_frame")),
            )
        )
        if not resume_generation_id:
            # A new render can incur usage. Prove that this installation can
            # decode-verify the completed MP4 before contacting/authenticating
            # with the Broker or preparing any temporary reference uploads.
            decode_verifier = await self._run_blocking_generation_stage(
                _resolve_mp4_decode_verifier
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            logger.info(
                "%s using MP4 decode verifier %s (%s)",
                self.name,
                decode_verifier.executable,
                decode_verifier.backend,
            )
        # The Broker generation request is the sole usage/quota/accounting authority.
        self._set_generation_status("connecting_broker", generation_id="")
        bridge = await self._ensure_broker_connected()
        if not self._runtime_node_is_live(require_registered=True):
            return
        if advanced_seedance_v2:
            # Task-declared 2.5 modes must be advertised by the authenticated
            # Broker before any reference media is uploaded or any billable
            # create-task request can be made. The legacy Text/Frame v1 contract
            # returns immediately.
            await asyncio.to_thread(
                bridge.require_seedance_features,
                model_id=str(params["model_id"]),
                task=str(params.get(TASK_PARAMETER) or TASK_REFERENCE_TO_VIDEO),
                output_format=str(
                    params.get("output_format") or DEFAULT_OUTPUT_FORMAT
                ),
                return_last_frame=bool(params.get("return_last_frame")),
                timeout=10.0,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return

        started = self._monotonic()
        timeout = params["generation_timeout_seconds"]
        deadline = started + timeout
        poll_interval = params["poll_interval_seconds"]
        final_task: dict[str, Any] | None = None

        if resume_generation_id:
            generation_id = self._validate_task_id(resume_generation_id)
            if not self._runtime_node_is_live(require_registered=True):
                return
            self._set_broker_task_outputs(
                {"id": generation_id, "status": "resuming"},
                generation_id=generation_id,
                status="resuming",
            )
            self._set_generation_recovery_checkpoint(
                stage="resume",
                task_id=generation_id,
                task_identity="broker_task",
                status="resuming",
                params=params,
            )
            await self._force_save_generation_recovery_checkpoint(
                required=False,
                reason="resume",
            )
            logger.info("%s resuming FN AI Broker task %s", self.name, generation_id)
        else:
            if not self._runtime_node_is_live(require_registered=True):
                return
            self._set_generation_status("preparing_media", generation_id="")
            params = await self._run_blocking_generation_stage(
                self._prepare_video_references_for_run,
                params,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            payload = await self._run_blocking_generation_stage(
                self._build_broker_payload,
                params,
            )
            client_request_id = "hmb-" + uuid4().hex
            payload["client_request_id"] = client_request_id
            if not self._runtime_node_is_live(require_registered=True):
                return
            self._set_broker_task_outputs(
                {"id": client_request_id, "status": "submitting"},
                generation_id=client_request_id,
                status="submitting",
            )
            self._set_generation_recovery_checkpoint(
                stage="pre_submit",
                task_id=client_request_id,
                task_identity="client_request",
                status="submitting",
                params=params,
            )
            # This is the billing boundary. A hard restart is recoverable only
            # when the idempotent client identity is on disk before the POST.
            try:
                await self._force_save_generation_recovery_checkpoint(
                    required=True,
                    reason="pre_submit",
                )
            except Exception:
                # No POST was reached. Remove the in-memory provisional ID so
                # the current session neither claims a remote render exists nor
                # blocks a corrected retry after the workflow-save problem is
                # fixed. The failed save cannot have persisted this mutation,
                # and the previously saved workflow remains untouched on disk.
                self.parameter_output_values["generation_id"] = ""
                self.parameter_output_values["provider_response"] = None
                self._clear_generation_recovery_checkpoint()
                self._set_generation_status(
                    "failed",
                    generation_id="",
                    preview_action="none",
                )
                raise
            if not self._submission_start_is_authorized(
                require_registered=True
            ):
                await self._discard_unsent_generation_checkpoint(
                    reason="cancelled_after_pre_submit_save",
                )
                raise asyncio.CancelledError(
                    "Seedance submission was cancelled before the create request started."
                )
            try:
                response, submission_cancelled = await self._await_submission_result(
                    bridge.generate_seedance,
                    payload,
                    timeout=min(float(timeout), 1200.0),
                )
            except _SubmissionCancelledBeforeStart:
                await self._discard_unsent_generation_checkpoint(
                    reason="cancelled_at_submission_gate",
                )
                raise asyncio.CancelledError(
                    "Seedance submission was cancelled before the create request started."
                ) from None
            except asyncio.CancelledError:
                if not self._submission_outcome_unknown:
                    await self._discard_unsent_generation_checkpoint(
                        reason="cancelled_before_submission_start",
                    )
                raise
            except _BrokerError as exc:
                if not self._runtime_node_is_live(require_registered=True):
                    return
                if exc.submission_outcome_unknown:
                    if not self._runtime_node_is_live(require_registered=True):
                        return
                    self._submission_outcome_unknown = True
                    self._set_generation_status(
                        "submission_unknown",
                        generation_id=client_request_id,
                        preview_action="refresh_existing",
                    )
                    self.parameter_output_values["provider_response"] = {
                        "transport": "fn_ai_broker",
                        "id": client_request_id,
                        "status": "submission_unknown",
                    }
                    self._set_generation_recovery_checkpoint(
                        stage="submission_unknown",
                        task_id=client_request_id,
                        task_identity="client_request",
                        status="submission_unknown",
                        params=params,
                    )
                    await self._force_save_generation_recovery_checkpoint(
                        required=False,
                        reason="submission_unknown",
                    )
                elif (
                    exc.status_code is not None
                    and not exc.submission_outcome_unknown
                ):
                    # An HTTP response is a definitive create rejection, not a
                    # disconnect with an accepted task hiding behind it. The
                    # hmb-* value is only this client's idempotency key until a
                    # successful Broker response returns an authoritative job ID.
                    exc.definitive_submission_rejection = True
                    self.parameter_output_values["generation_id"] = ""
                    self.parameter_output_values["provider_response"] = None
                    self._set_generation_status(
                        "failed",
                        generation_id="",
                        preview_action="none",
                    )
                    self._clear_generation_recovery_checkpoint()
                    await self._force_save_generation_recovery_checkpoint(
                        required=False,
                        reason="definitive_submission_rejection",
                    )
                raise
            if not self._runtime_node_is_live(require_registered=True):
                return
            task = self._normalize_broker_task(response)
            generation_id = str(task["id"])
            status = str(task["status"])
            self._submission_outcome_unknown = False
            if not self._runtime_node_is_live(require_registered=True):
                return
            self._set_broker_task_outputs(
                task,
                generation_id=generation_id,
                status=status,
            )
            self._set_generation_recovery_checkpoint(
                stage=(
                    "remote_succeeded"
                    if status == "succeeded"
                    else "terminal"
                    if status in TERMINAL_FAILURE_STATUSES
                    or task.get("terminal") is True
                    else "accepted"
                ),
                task_id=generation_id,
                task_identity="broker_task",
                status=status,
                params=params,
                terminal=bool(
                    status in TERMINAL_FAILURE_STATUSES
                    or task.get("terminal") is True
                ),
            )
            # If this best-effort save fails, the required pre-submit save still
            # retains the same idempotent client request for safe retrieval.
            await self._force_save_generation_recovery_checkpoint(
                required=False,
                reason="broker_accepted",
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
                if not self._runtime_node_is_live(require_registered=True):
                    return
                self._set_generation_status(
                    "cancelled_locally",
                    generation_id=generation_id,
                    preview_action="refresh_existing",
                )
                self._set_generation_recovery_checkpoint(
                    stage="cancelled_locally",
                    task_id=generation_id,
                    task_identity="broker_task",
                    status="cancelled_locally",
                    params=params,
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False,
                    reason="submission_cancelled_locally",
                )
                raise asyncio.CancelledError(
                    "Local cancellation arrived during submission. The FN AI Broker "
                    f"task ID was recovered as {generation_id}; use Refresh / Retrieve "
                    "Result for this same task."
                )

        while final_task is None:
            if not self._runtime_node_is_live(require_registered=True):
                return
            if self.is_cancellation_requested:
                if not self._runtime_node_is_live(require_registered=True):
                    return
                self._set_generation_status(
                    "cancelled_locally",
                    generation_id=generation_id,
                    preview_action="refresh_existing",
                )
                self._set_generation_recovery_checkpoint(
                    stage="cancelled_locally",
                    task_id=generation_id,
                    task_identity="broker_task",
                    status="cancelled_locally",
                    params=params,
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False,
                    reason="poll_cancelled_locally",
                )
                raise asyncio.CancelledError(
                    "Local Broker polling stopped, but the server render continues. "
                    "Use Refresh / Retrieve Result for this same task."
                )
            now = self._monotonic()
            if now >= deadline:
                if not self._runtime_node_is_live(require_registered=True):
                    return
                self._set_generation_status(
                    "timed_out",
                    generation_id=generation_id,
                    preview_action="refresh_existing",
                )
                self._set_generation_recovery_checkpoint(
                    stage="timed_out",
                    task_id=generation_id,
                    task_identity="broker_task",
                    status="timed_out",
                    params=params,
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False,
                    reason="poll_timed_out",
                )
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
            if not self._runtime_node_is_live(require_registered=True):
                return
            task = self._normalize_broker_task(
                response,
                fallback_job_id=generation_id,
            )
            if str(task["id"]) != generation_id:
                raise _BrokerError("FN AI Broker returned a different task ID.")
            status = str(task["status"])
            if not self._runtime_node_is_live(require_registered=True):
                return
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
                self._set_generation_recovery_checkpoint(
                    stage="remote_succeeded",
                    task_id=generation_id,
                    task_identity="broker_task",
                    status="succeeded",
                    params=params,
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False,
                    reason="remote_succeeded",
                )
                final_task = task
                break
            if status in TERMINAL_FAILURE_STATUSES:
                self._set_generation_recovery_checkpoint(
                    stage="terminal",
                    task_id=generation_id,
                    task_identity="broker_task",
                    status=status,
                    params=params,
                    terminal=True,
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False,
                    reason="broker_terminal",
                )
                raise RuntimeError(
                    self._broker_terminal_failure_message(task, generation_id)
                )
            remaining = deadline - self._monotonic()
            if remaining > 0:
                await self._sleep(min(poll_interval, remaining))
                if not self._runtime_node_is_live(require_registered=True):
                    return

        if not self._runtime_node_is_live(require_registered=True):
            return
        await self._save_completed_task(
            final_task,
            generation_id,
            destination,
            decode_verifier,
            model_id=str(params["model_id"]),
            output_format=str(
                params.get("output_format") or DEFAULT_OUTPUT_FORMAT
            ),
            return_last_frame=bool(params.get("return_last_frame")),
        )


    async def aprocess(self) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            return
        with self._generation_refresh_lock:
            if (
                self._generation_refresh_running
                or self._generation_run_active.is_set()
            ):
                return
            self._generation_run_active.set()
        try:
            await self._aprocess_impl()
        finally:
            with self._generation_refresh_lock:
                self._generation_run_active.clear()

    async def _aprocess_impl(self) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            return
        self._clear_execution_status()
        try:
            await self._process_generation()
        except asyncio.CancelledError:
            if not self._runtime_node_is_live(require_registered=True):
                return
            generation_id = str(
                self.parameter_output_values.get("generation_id") or ""
            ).strip()
            current_status = str(
                self.parameter_output_values.get("generation_status") or ""
            ).strip().lower()
            if generation_id and current_status != "submission_unknown":
                self._set_generation_status(
                    "cancelled_locally",
                    generation_id=generation_id,
                    preview_action="refresh_existing",
                )
            elif not generation_id:
                self._publish_generation_preview("failed", generation_id="")
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
            if not self._runtime_node_is_live(require_registered=True):
                return
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
            submission_unknown = (
                isinstance(exc, _BrokerError) and exc.submission_outcome_unknown
            )
            definitive_submission_rejection = bool(
                isinstance(exc, _BrokerError)
                and exc.definitive_submission_rejection
            )
            if definitive_submission_rejection:
                safe_message += (
                    "\nThe Broker definitively rejected this create request; "
                    "no new render was started."
                )
            if generation_id:
                if submission_unknown:
                    safe_message += (
                        f"\nClient request ID: {generation_id}. Broker acceptance "
                        "could not be confirmed, so a remote task may still exist."
                    )
                elif terminal:
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
            if submission_unknown:
                if not self._runtime_node_is_live(require_registered=True):
                    return
                self._set_generation_status(
                    "submission_unknown",
                    generation_id=generation_id,
                    preview_action="refresh_existing",
                )
                safe_message += (
                    "\nRefresh / Retrieve Result checks the same client request ID "
                    "only. It never repeats the create-task request or creates a new "
                    "idempotency key."
                    "\nTemporary local video uploads are being retained for up to "
                    "30 minutes so an accepted remote task can still fetch them."
                )
            elif (
                not self.parameter_output_values.get("generation_status")
                or generation_status in LOCAL_PRE_SUBMISSION_STATUSES
            ):
                if not self._runtime_node_is_live(require_registered=True):
                    return
                self._set_generation_status(
                    "failed",
                    generation_id=generation_id,
                )
            else:
                self._publish_generation_preview(
                    "failed",
                    generation_id=generation_id,
                    action=(
                        "refresh_existing"
                        if generation_id and not terminal
                        else "none"
                    ),
                )
            if not self._runtime_node_is_live(require_registered=True):
                return
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
    "MODEL_NAME_SEEDANCE_2_5",
    "SEEDANCE_2_5_MODEL_ID",
    "MODEL_DURATION_CHOICES",
    "DURATION_STORAGE_CHOICES",
    "MODEL_REFERENCE_LIMITS",
    "TASK_PARAMETER",
    "TASK_TEXT_ONLY",
    "TASK_FIRST_LAST_FRAME",
    "TASK_REFERENCE_TO_VIDEO",
    "TASK_VIDEO_EDITING",
    "TASK_VIDEO_EXTENSION",
    "TASK_STORAGE_CHOICES",
    "MODEL_TASK_CHOICES",
    "MAX_REFERENCE_IMAGES",
    "MAX_VIDEO_REFERENCES",
    "MAX_REFERENCE_AUDIO",
    "LEGACY_VIDEO_REFERENCE_SLOTS",
    "VIDEO_REFERENCES_PARAMETER",
    "GENERATION_PREVIEW_SCHEMA",
    "GENERATION_PREVIEW_VERSION",
    "GENERATION_PREVIEW_PHASES",
    "SEEDANCE_RECOVERY_PARAMETER",
    "SEEDANCE_RECOVERY_SCHEMA",
    "SEEDANCE_RECOVERY_VERSION",
]
