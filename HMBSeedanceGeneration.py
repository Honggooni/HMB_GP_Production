from __future__ import annotations

import asyncio
import base64
import binascii
import ctypes
import hashlib
import hmac
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
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import weakref
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager, nullcontext, suppress
from copy import copy, deepcopy
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlencode, urljoin, urlparse
from uuid import UUID, uuid4

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


def _write_generation_sidecar(file_path: Path, metadata: Any) -> None:
    """Use the installed host's sidecar API, without retrying a partial write."""

    parameters = inspect.signature(write_sidecar).parameters
    engine_parameter = parameters.get("engine")
    if engine_parameter is None:
        # Older hosts accept only (file_path, metadata).
        write_sidecar(file_path, metadata)
        return
    from griptape_nodes.retained_mode.engine import current_engine

    engine = current_engine()
    if engine_parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
        write_sidecar(file_path, metadata, engine)
    else:
        write_sidecar(file_path, metadata, engine=engine)


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
import _hmb_review as _review
import _hmb_broker_config as _broker_config
import _hmb_my_box_node as _my_box_node
import _hmb_reference_leases as _reference_leases
from _hmb_image_limits import inspect_seedance_image_payload
from _hmb_project import PROJECTS, project_from_asset_payload, resolve_project
from _hmb_build_diagnostics import get_build_diagnostics as _get_build_diagnostics
from _hmb_common import (
    _broker_load_bearer_token_readonly,
    _broker_load_bearer_token_from_path_readonly,
)

logger = logging.getLogger("griptape_nodes")
_WEB_RERENDER_SESSION_EPOCH = str(uuid4())

GT_CLOUD_API_KEY_SECRET = "GT_CLOUD_API_KEY"
GT_CLOUD_BUCKET_ID_SECRET = "GT_CLOUD_BUCKET_ID"
TOS_ACCESS_KEY_ID_SECRET = "TOS_ACCESS_KEY_ID"
TOS_SECRET_ACCESS_KEY_SECRET = "TOS_SECRET_ACCESS_KEY"
TOS_BUCKET_NAME_SECRET = "TOS_BUCKET_NAME"
AI_BROKER_INTERNAL_ORIGIN = "http://192.168.203.245:8080"
AI_BROKER_SERVER_URL = _broker_config.DEFAULT_BROKER_BASE_URL
# This is the same operated Broker behind its public gateway, not a general
# credential fallback for user-entered third-party addresses.
_BROKER_LEGACY_AUTH_GATEWAY = "https://app.funnyflux.kr/GripTapeServer"
_BROKER_LEGACY_AUTH_MIGRATION_LOCK = threading.RLock()
_BROKER_SETTING_NODES: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()
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
_WORKFLOW_CHECKPOINT_LOCKS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Lock
] = weakref.WeakKeyDictionary()
_WORKFLOW_CHECKPOINT_LOCKS_GUARD = threading.Lock()
_RECOVERY_JOURNAL_OWNERS: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()
_RECOVERY_JOURNAL_OWNERS_GUARD = threading.Lock()
_DRAFT_OWNERS: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()
_DRAFT_OWNERS_GUARD = threading.Lock()

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
# Keep MP4 as the compatibility fallback for existing 2.0 workflows. Only
# freshly created 2.5 nodes start with the post-production MOV option.
DEFAULT_OUTPUT_FORMAT = "mp4"
NEW_NODE_OUTPUT_FORMAT = "mov"
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
GENERATION_MODE_METADATA_SCHEMA = "hmb-generation-mode-v1"
GENERATION_MODE_METADATA_FIELD = "hmb_generation_mode"
GENERATION_TASK_METADATA_FIELD = "hmb_generation_task"
GENERATION_SHOT_METADATA_SCHEMA = "hmb-generation-shot-metadata"
GENERATION_SHOT_METADATA_FIELD = "hmb_shot"
BROKER_SEEDANCE_DRAFT_CAPABILITIES_VERSION = 3
DRAFT_ACTION_OFF = "Off"
DRAFT_ACTION_PREVIEW = "Draft 480p"
DRAFT_ACTION_FINAL = "Finalize Draft 1080p"
DRAFT_ACTION_CHOICES = (DRAFT_ACTION_OFF, DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL)
DRAFT_SOURCE_PARAMETER = "HMB_SEEDANCE_DRAFT_SOURCE"
DRAFT_SOURCES_PARAMETER = "HMB_SEEDANCE_DRAFT_SOURCES"
PROJECT_SELECTION_SCHEMA = "hmb-imageasset-project-selection-v1"
ONLY_PROJECT_SELECTION_SCHEMA = "hmb-only-project-selection-v1"
ONLY_PROJECT_PARAMETER = "only_project"
ONLY_PROJECT_UNSELECTED = "Select Project"


class _ProjectSelectionChanged(ValueError):
    """The captured local selection lost authority before a create request."""


class _ProjectSelectionRequired(ValueError):
    """No explicit or connected project; only legacy Final may use its source."""


DRAFT_OWNER_PARAMETER = "HMB_SEEDANCE_DRAFT_OWNER"
DRAFT_SOURCE_TTL_MS = 604800000
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
    # Ordinary 480p is independent from the explicit, separately billed Draft flow.
    SEEDANCE_2_5_MODEL_ID: ("480p", "720p", "1080p"),
}

MODEL_DEFAULT_RESOLUTIONS = {
    SEEDANCE_2_0_MODEL_ID: "1080p",
    SEEDANCE_2_0_FAST_MODEL_ID: "720p",
    SEEDANCE_2_5_MODEL_ID: "720p",
}

MODEL_DURATION_CHOICES = {
    SEEDANCE_2_0_MODEL_ID: (-1, *range(4, 16)),
    SEEDANCE_2_0_FAST_MODEL_ID: (-1, *range(4, 16)),
    # Ordinary 2.5 generation uses literal 4–30 seconds. Video Editing keeps
    # the source video's duration and is narrowed to -1 by its task-specific
    # synchronization and validation below.
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


def _normalize_returned_last_frame(
    data: bytes | bytearray, max_bytes: int = MAX_LAST_FRAME_BYTES,
) -> bytes:
    """Accept bounded provider JPEG/PNG frames; publish a validated PNG."""
    from io import BytesIO
    import warnings
    from PIL import Image, UnidentifiedImageError

    raw = bytes(data)
    if not raw or len(raw) > max_bytes:
        raise RuntimeError("Returned last-frame image exceeds the size limit or is empty.")

    class BoundedPNGBuffer(BytesIO):
        def write(self, value):
            if self.tell() + len(value) > max_bytes:
                raise RuntimeError("Converted last-frame PNG exceeds the size limit.")
            return super().write(value)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                kind = str(image.format or "").upper()
                width, height = image.size
                if kind not in {"PNG", "JPEG"} or not (width > 0 and height > 0 and width * height <= 100_000_000):
                    raise RuntimeError("Returned last frame must be a bounded PNG or JPEG image.")
                image.verify()
            with Image.open(BytesIO(raw)) as image:
                image.load()
                if kind == "PNG":
                    if not _is_valid_png(raw):
                        raise RuntimeError("Returned last-frame PNG is invalid.")
                    return raw
                with BoundedPNGBuffer() as output:
                    image.convert("RGB").save(output, format="PNG")
                    normalized = output.getvalue()
        if not _is_valid_png(normalized):
            raise RuntimeError("Converted last-frame PNG is invalid.")
        return normalized
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise RuntimeError("Returned last frame is not a valid PNG or JPEG image.") from exc

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
SHOT_FINISH_LOOK_INPUT_PARAMETER = "SHOT_FINISH_LOOK_IN"
GENERATED_VIDEO_SOURCE_PARAMETER = "HMB_GENERATED_VIDEO_SOURCE"
GENERATED_VIDEO_SOURCE_SCHEMA = "hmb-generated-video-source"
FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA = "hmb-finish-look-shot-snapshot"
FINISH_LOOK_SHOT_SNAPSHOT_VERSION = 2
SHOT_PICKER_LEGACY_JSON_MAX_BYTES = 1024 * 1024
SHOT_AUTOCLAIM_ENABLED_PARAMETER = "HMB_SHOT_AUTOCLAIM_ENABLED"
SEEDANCE_EXECUTION_MODE_METADATA = "hmb_seedance_execution_mode"
SEEDANCE_EXECUTION_MODE_SCHEMA = "hmb-seedance-execution-mode"
SEEDANCE_MODE_SELECTION_SCHEMA = "hmb-seedance-mode-selection"
SHOT_SELECTOR_PARAMETER = "shot_selector"
SEEDANCE_SHOT_WIDGET_PARAMETER = "HMB_SEEDANCE_SHOT_UI"
SEEDANCE_SHOT_WIDGET_NAME = "HMBSeedanceGenerationWidget"
SEEDANCE_SHOT_WIDGET_LIBRARY_NAME = "HMB_GP_Production"
SEEDANCE_SHOT_WIDGET_HEIGHT = 64
SEEDANCE_REFRESH_COMMAND_PARAMETER = "HMB_SEEDANCE_REFRESH_COMMAND"
SEEDANCE_PREFLIGHT_PARAMETER = "HMB_SEEDANCE_PREFLIGHT"
SEEDANCE_PREFLIGHT_SCHEMA = "hmb-seedance-render-preflight"
BROKER_SERVER_URL_PARAMETER = "broker_server_url"
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
        "접수 여부가 불명확합니다. 결과 조회는 기존 요청만 확인하며, 새 Run은 별도 렌더를 제출합니다. 중복 과금될 수 있습니다."
    ),
    "failed": "작업 상태 또는 결과 수신을 확인해야 합니다.",
    "succeeded": "",
}


def _seedance_local_preview_value(value: Any = None) -> dict[str, str]:
    """Accept only the bounded original-source/loopback read-only preview pair."""
    if not isinstance(value, dict) or set(value) != {"source", "url"}:
        return {}
    source, url = value.get("source"), value.get("url")
    if (not isinstance(source, str) or not source.strip() or len(source) > 4096
            or not isinstance(url, str) or not url or len(url) > 8192
            or re.search(r"[\x00-\x1f\x7f]", source + url)
            or "\\" in url):
        return {}
    try:
        # A drive letter is a local path, not a URL scheme. File/HTTP/data/asset
        # URLs are never resolved or proxied through this optional local path.
        if urlparse(source).scheme and not re.match(r"^[A-Za-z]:[\\/]", source):
            return {}
        parsed = urlparse(url)
        host = parsed.hostname or ""
        loopback = host.casefold() == "localhost" or ipaddress.ip_address(host).is_loopback
        if (parsed.scheme not in {"http", "https"} or not loopback
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.port == 0
                or not parsed.path.startswith(("/workspace/", "/external/"))):
            return {}
    except (ValueError, TypeError):
        return {}
    return {"source": source, "url": url}


def _seedance_generation_preview_value(value: Any = None) -> dict[str, Any]:
    """Return the bounded, browser-safe runtime preview contract.

    The optional original local preview is an engine-minted loopback read URL.
    Provider URLs/bodies and browser-supplied task authority remain excluded.
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
    result = {
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
    local_preview = _seedance_local_preview_value(source.get("local_preview"))
    if local_preview:
        result["local_preview"] = local_preview
    return result


def _seedance_refresh_command_value(value: Any = None) -> dict[str, Any]:
    """Normalize the one-shot browser command without accepting a task ID."""

    source = value if isinstance(value, dict) else {}
    action = str(source.get("action") or "").strip().lower()
    action_id = str(source.get("action_id") or "").strip()
    if (
        source.get("schema") != SEEDANCE_REFRESH_COMMAND_SCHEMA
        or source.get("version") != SEEDANCE_REFRESH_COMMAND_VERSION
        or action not in {"refresh_existing", "open_gallery", "finalize_draft", "cancel_draft_final"}
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
    result = {
        "schema": SEEDANCE_REFRESH_COMMAND_SCHEMA,
        "version": SEEDANCE_REFRESH_COMMAND_VERSION,
        "action": action,
        "action_id": action_id,
        "issued_at_ms": issued_at_ms,
    }
    if action in {"finalize_draft", "cancel_draft_final"}:
        expected = source.get("expected_draft_job_id")
        if not isinstance(expected, str) or re.fullmatch(r"job-(?:mybox-)?[0-9a-f]{32}", expected) is None:
            result.update(action="", action_id="")
        else:
            result["expected_draft_job_id"] = expected
    return result


def _generated_video_origin(value: Any = None) -> dict[str, Any]:
    """Accept only an explicitly captured Shot identity, never infer one."""
    if not isinstance(value, dict):
        return {}
    channel = _seedance_uuid_text(value.get("channel_uuid"))
    shot = _seedance_uuid_text(value.get("shot_uuid"))
    instance = _seedance_uuid_text(value.get("source_node_instance_id"))
    number = value.get("number")
    name = str(value.get("name") or "").strip()
    if (not channel or not shot or not instance or type(number) is not int
            or not 1 <= number <= 5 or not name or len(name) > 128):
        return {}
    return {"channel_uuid": channel, "shot_uuid": shot, "number": number,
            "name": name, "source_node_instance_id": instance}


def _generation_submission_shot(value: Any) -> dict[str, Any]:
    """Project only the frozen creation identity, never a live selector or path.

    Titles remain optional Broker display metadata. Keep the existing public
    name exclusion rules; an unsafe/blank name falls back to its captured slot
    number without exporting a path, URL or credential-like value.
    """
    fields = {"channel_uuid", "shot_uuid", "source_node_instance_id", "number", "name"}
    if not isinstance(value, dict) or set(value) != fields:
        return {}
    if (type(value.get("number")) is not int or not 1 <= value["number"] <= 5
            or any(not isinstance(value.get(key), str)
                or not value[key]
                or _seedance_uuid_text(value[key]) != value[key]
                for key in fields - {"number", "name"})
            or not isinstance(value.get("name"), str)):
        return {}
    name = _review._public_shot_name(value["name"])
    if not name or any(0xD800 <= ord(character) <= 0xDFFF for character in name):
        name = f"Shot {value['number']}"
    return {key: (name if key == "name" else value[key]) for key in fields}


def _generated_video_source_value(value: Any = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    origin = _generated_video_origin(value)
    task_id = str(value.get("task_id") or "").strip()
    path = str(value.get("path") or "").strip()
    revision = value.get("result_revision")
    if (not origin or value.get("schema") != GENERATED_VIDEO_SOURCE_SCHEMA
            or value.get("version") != 1 or value.get("completed") is not True
            or not task_id or _TASK_ID_PATTERN.fullmatch(task_id) is None
            or value.get("generation_id") != task_id
            or type(revision) is not int or not 1 <= revision <= 2_147_483_647
            or not path or len(path) > 4096 or not Path(path).is_absolute()
            or str(value.get("url") or "") != path):
        return {}
    return {"schema": GENERATED_VIDEO_SOURCE_SCHEMA, "version": 1, **origin,
            "generation_id": task_id, "task_id": task_id,
            "result_revision": revision, "path": path, "url": path,
            "completed": True}


def _seedance_draft_source_value(value: Any = None) -> dict[str, Any]:
    """Retain only local job identity, project and origin; never prompt or media URLs."""
    if (not isinstance(value, dict) or not isinstance(value.get("broker_server_url"), str)
            or not value["broker_server_url"]
            or re.fullmatch(r"job-[0-9a-f]{32}", str(value.get("draft_job_id") or "")) is None):
        return {}
    try:
        project = resolve_project(value, default_legacy=False)
        if any(value.get(key) != project[key] for key in ("project_id", "project_name")):
            return {}
        origin = _broker_validated_server_url(str(value.get("broker_server_url") or ""))
    except (ValueError, TypeError, _BrokerError):
        return {}
    result = {"draft_job_id": value["draft_job_id"],
              **{key: project[key] for key in ("project_id", "project_name")}, "broker_server_url": origin}
    if "generation_origin" in value:
        generation_origin = _generated_video_origin(value.get("generation_origin"))
        owner = _seedance_uuid_text(value.get("owner_id"))
        created = value.get("created_at_ms")
        if (not owner or type(created) is not int or not 0 < created < 9_999_999_999_999
                or value.get("completed") is not True
                or (value.get("generation_origin") != {} and not generation_origin)):
            return {}
        result.update(generation_origin=generation_origin, owner_id=owner,
                      created_at_ms=created, completed=True)
        bindings = value.get("source_bindings", {})
        if not isinstance(bindings, dict) or set(bindings) - {"image_asset", "video_picker"}:
            return {}
        if any(not _seedance_uuid_text(item) for item in bindings.values()):
            return {}
        result["source_bindings"] = dict(bindings)
    for name in ("final_request_id", "final_job_id"):
        identifier = value.get(name)
        if identifier:
            if not isinstance(identifier, str) or _TASK_ID_PATTERN.fullmatch(identifier) is None:
                return {}
            result[name] = identifier
    return result


def _seedance_draft_final_request_id(draft_job_id: str) -> str:
    """Share one Final intent with the authenticated web review workflow."""
    if not isinstance(draft_job_id, str) or re.fullmatch(r"job-[0-9a-f]{32}", draft_job_id) is None:
        raise ValueError("Finalization requires a canonical Broker Draft task ID.")
    return "hmb-draft-final-v1-" + draft_job_id


_DRAFT_FINAL_SERVER_STATES = frozenset({"available", "source_pending", "reserved", "running",
    "completed", "consumed", "expired", "unknown", "not_draft"})
_DRAFT_FINAL_HIDDEN_STATES = frozenset({"completed", "consumed", "expired", "not_draft"})
_DRAFT_FINAL_SYNC_SECONDS = 10.0


def _seedance_draft_final_state_value(value: Any, source: dict[str, Any]) -> dict[str, Any]:
    """Keep only the authenticated, exact-source advisory projection."""
    required = {"schema", "state_schema", "state", "is_draft", "eligible", "consumed", "source_task_id",
                "checked_at", "expires_at", "owner_user_id", "project_id", "project_name",
                "child_task_id", "child_status", "idempotency_key"}
    if (not isinstance(value, dict) or not required.issubset(value)
            or value.get("schema") != "hmb-review-draft-final-v1"
            or value.get("state_schema") != "hmb-draft-final-state-v1"
            or value.get("source_task_id") != source["draft_job_id"]
            or not isinstance(value.get("state"), str) or value["state"] not in _DRAFT_FINAL_SERVER_STATES
            or type(value.get("is_draft")) is not bool
            or type(value.get("eligible")) is not bool
            or value.get("consumed") is not None and type(value["consumed"]) is not bool
            or type(value.get("checked_at")) is not int or value["checked_at"] <= 0
            or abs(time.time() - value["checked_at"]) > 300
            or type(value.get("owner_user_id")) is not int or value["owner_user_id"] <= 0
            or value.get("idempotency_key") != _seedance_draft_final_request_id(source["draft_job_id"])
            or any(value.get(key) != source[key] for key in ("project_id", "project_name"))):
        raise _BrokerProtocolError("Broker returned an invalid Draft Final state.")
    child = value.get("child_task_id")
    child_status = value.get("child_status")
    expires = value.get("expires_at")
    if (child is not None and (not isinstance(child, str) or re.fullmatch(r"job-[0-9a-f]{32}", child) is None)
            or child_status is not None and (not isinstance(child_status, str) or len(child_status) > 64
                or re.fullmatch(r"[A-Za-z0-9_-]+", child_status) is None)
            or expires is not None and (type(expires) is not int or expires <= 0)
            or child is None and child_status is not None
            or value["eligible"] != (value["state"] == "available")
            or value["eligible"] and (value.get("is_draft") is not True
                or value.get("consumed") is not False or child is not None
                or expires is None or expires <= max(value["checked_at"], time.time() - 300))
            or value["state"] in {"reserved", "running", "completed", "consumed"}
                and (value.get("is_draft") is not True or value.get("consumed") is not True
                     or child is None or child_status is None)
            or value["state"] == "unknown" and value.get("consumed") is not None):
        raise _BrokerProtocolError("Broker returned an inconsistent Draft Final state.")
    return {key: value.get(key) for key in ("state", "eligible", "consumed", "source_task_id",
        "checked_at", "expires_at", "owner_user_id", "project_id", "project_name",
        "child_task_id", "child_status", "idempotency_key")}


class _SeedanceDraftOutputDestination:
    """A distinct no-overwrite video path for each explicit paid Draft action."""
    _existing_file_policy = ExistingFilePolicy.FAIL
    _append = False
    _create_parents = True

    def __init__(self, location: str) -> None:
        self.location = location

    def resolve(self) -> str:
        return self.location


class _SeedanceResolvedOutputDestination:
    """Freeze the effective save path while retaining the SDK file policy."""

    def __init__(self, destination: Any, location: str) -> None:
        self._destination = destination
        self.location = location

    def resolve(self) -> str:
        return self.location

    def __getattr__(self, name: str) -> Any:
        return getattr(self._destination, name)


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
    broker_server_url = ""
    if task_id:
        try:
            # Saved workflows predating per-node Broker selection belong to
            # the historical fixed endpoint. If an environment override is
            # active, their origin is unknowable and recovery fails closed.
            if "broker_server_url" in source:
                explicit_origin = str(source.get("broker_server_url") or "")
                broker_server_url = (
                    _broker_validated_server_url(explicit_origin)
                    if explicit_origin else ""
                )
            elif os.environ.get("HMB_AI_BROKER_URL", AI_BROKER_INTERNAL_ORIGIN).rstrip("/") == AI_BROKER_INTERNAL_ORIGIN:
                broker_server_url = AI_BROKER_INTERNAL_ORIGIN
        except _BrokerError:
            # A corrupt explicit origin must not silently redirect a paid
            # task to the current node setting or another server.
            broker_server_url = ""

    def bounded_integer(raw: Any, maximum: int) -> int:
        if not isinstance(raw, int) or isinstance(raw, bool):
            return 0
        return min(maximum, max(0, raw))

    checkpoint = {
        "schema": SEEDANCE_RECOVERY_SCHEMA,
        "version": SEEDANCE_RECOVERY_VERSION,
        "journal_id": _seedance_uuid_text(source.get("journal_id")),
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
        "broker_server_url": broker_server_url,
        "generation_origin": _generated_video_origin(source.get("generation_origin")) if task_id else {},
        "reference_lease_id": _reference_leases.lease_id(source.get("reference_lease_id")) if task_id else "",
    }
    if source.get("draft_action") in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}:
        checkpoint["draft_action"] = source["draft_action"]
        try:
            checkpoint["draft_project"] = resolve_project(source.get("draft_project"), default_legacy=False)
        except (ValueError, TypeError):
            checkpoint["draft_project"] = {}
        bindings = source.get("draft_source_bindings")
        if isinstance(bindings, dict) and not set(bindings) - {"image_asset", "video_picker"} and all(_seedance_uuid_text(item) for item in bindings.values()):
            checkpoint["draft_source_bindings"] = dict(bindings)
        started = source.get("draft_started_at_ms")
        if type(started) is int and 0 < started < 9_999_999_999_999:
            checkpoint["draft_started_at_ms"] = started
    if task_id and source.get("queue_only_headers"):
        import _hmb_queue_admission as queue
        checkpoint["queue_only_headers"] = queue.identity(source["queue_only_headers"])
    draft_source = _seedance_draft_source_value(source.get("draft_source"))
    if draft_source:
        checkpoint["draft_source"] = draft_source
    if task_id and source.get("shot_hierarchy"):
        try:
            hierarchy = _shot_routing.normalize_shot_hierarchy(source["shot_hierarchy"])
            origin = checkpoint["generation_origin"]
            if (hierarchy["channel_uuid"] == origin.get("channel_uuid")
                    and _shot_routing.hierarchy_derived_names(hierarchy).get(origin.get("shot_uuid")) == origin.get("name")):
                checkpoint["shot_hierarchy"] = hierarchy
        except (ValueError, TypeError, KeyError):
            # Optional management data cannot discard an existing paid Task.
            pass
    return checkpoint


def _workflow_checkpoint_lock() -> asyncio.Lock:
    """Coordinate local checkpoint writes without touching host workflow saves."""

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


def _seedance_recovery_journal_path(journal_id: str) -> Path:
    identity = _seedance_uuid_text(journal_id)
    if not identity:
        raise ValueError("The local recovery journal identity is missing.")
    root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return root / "HMB_GP_Production" / "generation-recovery" / f"{identity}.json"


def _write_seedance_recovery_journal(checkpoint: dict[str, Any]) -> None:
    """Atomically persist task metadata only, never a workflow, prompt or key."""
    checkpoint = _seedance_recovery_value(checkpoint)
    path = _seedance_recovery_journal_path(checkpoint["journal_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(checkpoint, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


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
    draft: Any = None,
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
        "draft": _seedance_draft_ui_value(draft),
        "remote_prompt_route": _seedance_remote_prompt_route_value(
            remote_prompt_route
        ),
    }


def _seedance_draft_ui_value(value: Any = None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {"visible": source.get("visible") is True,
            "action": source.get("action") if source.get("action") in DRAFT_ACTION_CHOICES else DRAFT_ACTION_OFF,
            "preview_available": source.get("preview_available") is True,
            "final_available": source.get("final_available") is True,
            "job_id": str(source.get("job_id") or "")[:128],
            "effective_resolution": str(source.get("effective_resolution") or "")[:16],
            "busy": source.get("busy") is True,
            "final_busy": source.get("final_busy") is True,
            "active_action": source.get("active_action") if source.get("active_action") in DRAFT_ACTION_CHOICES else DRAFT_ACTION_OFF,
            "cancel_available": source.get("cancel_available") is True,
            "active_job_id": str(source.get("active_job_id") or "")[:128],
            "reason": str(source.get("reason") or "")[:400],
            **({"final_state": str(source.get("final_state") or "")[:32],
                "final_visible": source.get("final_visible") is True,
                "final_task_id": str(source.get("final_task_id") or "")[:128]}
               if "final_state" in source else {})}


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

_TOS_RPC_BYTES = 32 * 1024
_TOS_RUNTIME_REQUIREMENT = "tos==2.9.2"
_TOS_HELPER_SOURCE = r'''
import contextlib, importlib, importlib.metadata, importlib.util, json, logging, re, sys
from pathlib import Path
from urllib.parse import urlparse

protocol = sys.stdout
class DiscardOutput:
    def write(self, value):
        return len(value)
    def flush(self):
        pass
sys.stdout = DiscardOutput()
logging.disable(logging.CRITICAL)
client = None
request = {}
reply = {"version": 1, "ok": False}
try:
    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768:
        raise ValueError("request")
    request = json.loads(raw)
    if not isinstance(request, dict) or type(request.get("version")) is not int or request.get("version") != 1:
        raise ValueError("protocol")
    root = Path(request["runtime_root"]).resolve(strict=True)
    if Path(sys.prefix).resolve() != root or sys.prefix == sys.base_prefix or sys.version_info[:2] != (3, 12):
        raise ValueError("environment")
    for name, version in (("tos", "2.9.2"), ("wrapt", "1.16.0")):
        if importlib.metadata.version(name) != version:
            raise ValueError("dependency")
        spec = importlib.util.find_spec(name)
        Path(spec.origin).resolve(strict=True).relative_to(root)
    if request.get("operation") == "probe":
        importlib.import_module("tos")
        importlib.import_module("wrapt")
        reply = {"version": 1, "ok": True, "runtime_root": str(root),
                 "python": sys.version.split()[0], "tos_version": "2.9.2",
                 "wrapt_version": "1.16.0", "isolated": True}
    else:
        auth = request["auth"]
        if not isinstance(auth, dict) or any(not isinstance(auth.get(k), str) or not 0 < len(auth[k]) <= 4096 for k in ("ak", "sk", "endpoint", "region")):
            raise ValueError("auth")
        endpoint = urlparse("https://" + auth["endpoint"])
        if (not re.fullmatch(r"tos(?:-[a-z0-9]+)+\.volces\.com", auth["endpoint"])
                or endpoint.netloc != auth["endpoint"] or endpoint.path or endpoint.query or endpoint.fragment):
            raise ValueError("endpoint")
        bucket, key = request["bucket"], request["key"]
        if (not isinstance(bucket, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket)
                or not isinstance(key, str) or not re.fullmatch(r"hmb-seedance-temp/[0-9a-f]{32}\.[a-z0-9]{1,12}", key)):
            raise ValueError("object")
        operation = request["operation"]
        if operation not in {"put", "presign", "delete"}:
            raise ValueError("operation")
        tos_module = importlib.import_module("tos")
        client = tos_module.TosClientV2(auth["ak"], auth["sk"], auth["endpoint"], auth["region"],
            connection_time=10, socket_timeout=30, max_retry_count=0)
        if operation == "put":
            path = Path(request["path"]).resolve(strict=True)
            if not path.is_file() or not 0 < path.stat().st_size <= 1073741824:
                raise ValueError("file")
            content_type = request["content_type"]
            if not isinstance(content_type, str) or not re.fullmatch(r"[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+", content_type):
                raise ValueError("content_type")
            response = client.put_object_from_file(bucket, key, str(path), content_type=content_type)
            status = int(getattr(response, "status_code", 200) or 200)
            if not 200 <= status < 300:
                raise ValueError("upload")
            reply = {"version": 1, "ok": True, "status_code": status}
        elif operation == "presign":
            expires = request["expires"]
            if type(expires) is not int or not 3600 <= expires <= 2592000:
                raise ValueError("expires")
            response = client.pre_signed_url(tos_module.HttpMethodType.Http_Method_Get, bucket, key, expires=expires)
            value = str(getattr(response, "signed_url", "") or "").strip()
            parsed = urlparse(value)
            if (not 0 < len(value) <= 16384 or parsed.scheme != "https" or not parsed.hostname
                    or parsed.username or parsed.password or parsed.fragment):
                raise ValueError("signed_url")
            reply = {"version": 1, "ok": True, "signed_url": value}
        else:
            client.delete_object(bucket, key)
            reply = {"version": 1, "ok": True}
except BaseException:
    reply = {"version": 1, "ok": False}
    # A failed put may have reached storage even when its response was lost.
    if client is not None and isinstance(request, dict) and request.get("operation") == "put":
        with contextlib.suppress(Exception):
            client.delete_object(request["bucket"], request["key"])
finally:
    if client is not None:
        with contextlib.suppress(Exception):
            client.close()
    encoded = json.dumps(reply, ensure_ascii=True, separators=(",", ":"))
    protocol.write(encoded if len(encoded) <= 32768 else '{"version":1,"ok":false}')
    protocol.flush()
'''


def _isolated_tos_runtime_python() -> Path:
    """Return only the dedicated, non-system-site-packages TOS environment."""
    try:
        library_root = _THIS_DIR.resolve(strict=True)
        runtime = (library_root / ".venv-tos").resolve(strict=True)
        runtime.relative_to(library_root)
        configuration = runtime / "pyvenv.cfg"
        if configuration.stat().st_size > 16384:
            raise ValueError("TOS runtime configuration is oversized")
        data = configuration.read_text(encoding="utf-8")
        isolation = re.findall(r"(?im)^include-system-site-packages\s*=\s*([^\r\n]+)", data)
        if [value.strip().lower() for value in isolation] != ["false"]:
            raise ValueError("TOS runtime must be isolated")
        # A normal POSIX venv interpreter is a symlink to its base Python.
        # Invoke the venv entry path so Python reads this environment's cfg;
        # the child verifies its actual sys.prefix before reading credentials.
        python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        python.parent.resolve(strict=True).relative_to(runtime)
        if not python.is_file():
            raise ValueError("TOS runtime interpreter is missing")
        return python
    except (OSError, ValueError, RuntimeError):
        raise RuntimeError(
            "The isolated Volcengine TOS runtime is not ready. Automatic preparation may still be running; "
            "retry after it finishes or restart Griptape to complete the guarded setup. "
            "The HMB installer -PrepareTosRuntime option can also prepare .venv-tos. "
            "No TOS upload or render was submitted."
        ) from None


@dataclass
class _IsolatedTOSResponse:
    status_code: int = 200
    signed_url: str = ""


class _IsolatedTOSModule:
    class HttpMethodType:
        Http_Method_Get = "GET"


class _IsolatedTOSClient:
    """One bounded stdio child per operation; no TOS import in the engine."""

    def __init__(self, python: Path, auth: dict[str, str], *, is_live: Any) -> None:
        self._python = python
        self._runtime_root = python.parent.parent
        self._auth = dict(auth)
        self._is_live = is_live
        self._lock = threading.RLock()
        self._closed = False

    def _request(self, operation: str, bucket: str, key: str, **arguments: Any) -> dict[str, Any]:
        with self._lock:
            if self._closed or operation != "delete" and not self._is_live():
                raise RuntimeError("TOS media preparation was cancelled; no render was submitted.")
            request = {"version": 1, "runtime_root": str(self._runtime_root), "auth": self._auth,
                       "operation": operation, "bucket": bucket, "key": key, **arguments}
            raw = json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > _TOS_RPC_BYTES:
                raise RuntimeError("TOS helper request exceeds its bounded contract.")
            # Proxy variables and unrelated API credentials must not reach this
            # process. The selected TOS credentials travel only through stdin.
            environment = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if name in os.environ}
            process = None
            try:
                process = subprocess.Popen(
                    [str(self._python), "-I", "-B", "-c", _TOS_HELPER_SOURCE],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    cwd=str(self._runtime_root), env=environment, close_fds=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                deadline = time.monotonic() + (180.0 if operation == "put" else 45.0)
                first = True
                while True:
                    if time.monotonic() >= deadline or operation != "delete" and not self._is_live():
                        raise RuntimeError("TOS helper timed out or media preparation was cancelled.")
                    try:
                        output, _unused = process.communicate(input=raw if first else None, timeout=0.1)
                        break
                    except subprocess.TimeoutExpired:
                        first = False
                if operation != "delete" and not self._is_live():
                    raise RuntimeError("TOS media preparation was cancelled.")
                if process.returncode != 0 or len(output) > _TOS_RPC_BYTES:
                    raise ValueError("TOS helper response")
                result = json.loads(output)
                if (not isinstance(result, dict) or type(result.get("version")) is not int or result.get("version") != 1
                        or result.get("ok") is not True):
                    raise ValueError("TOS helper operation failed")
                return result
            except Exception:
                # Never propagate SDK stderr, credentials or signed URLs in an
                # exception chain owned by the native editor.
                raise RuntimeError("The isolated TOS operation failed or was cancelled. Check its runtime and storage settings.") from None
            finally:
                if process is not None and process.poll() is None:
                    with suppress(Exception):
                        process.kill()
                    with suppress(Exception):
                        process.communicate(timeout=2.0)

    def put_object_from_file(self, bucket: str, key: str, path: str, *, content_type: str) -> _IsolatedTOSResponse:
        try:
            result = self._request("put", bucket, key, path=path, content_type=content_type)
            return _IsolatedTOSResponse(status_code=int(result.get("status_code", 200)))
        except Exception:
            with suppress(Exception):
                self.delete_object(bucket, key)
            raise

    def pre_signed_url(self, method: Any, bucket: str, key: str, *, expires: int) -> _IsolatedTOSResponse:
        if method != "GET":
            raise ValueError("TOS media signing supports only GET.")
        result = self._request("presign", bucket, key, expires=expires)
        value = result.get("signed_url")
        parsed = urlparse(value) if isinstance(value, str) else None
        if (parsed is None or len(value) > 16384 or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment):
            raise RuntimeError("TOS did not return a signed HTTPS URL.")
        return _IsolatedTOSResponse(signed_url=value)

    def delete_object(self, bucket: str, key: str) -> None:
        self._request("delete", bucket, key)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._auth.clear()
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
    directory.mkdir(parents=True, exist_ok=True)
    if selected_origin != shared_origin:
        digest = hashlib.sha256(selected_origin.encode("ascii")).hexdigest()
        return directory / f"access_token_v2_{digest}.dpapi"
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


def _captured_display_title_operation_id(task_id: str, casecard_sha256: str, name: str) -> str:
    """One stable metadata operation per original Task, snapshot and literal name."""
    from uuid import NAMESPACE_URL, uuid5

    identity = json.dumps({"task_id": task_id, "casecard_sha256": casecard_sha256, "name": name},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(uuid5(NAMESPACE_URL, "hmb-captured-display-title-v1:" + identity))


def _captured_display_title_request(task_id: str, record: dict[str, Any],
                                   legacy_wire: dict[str, Any]) -> dict[str, Any]:
    """Attest only the saved creation name; never consult a live node or media."""
    if (not isinstance(record, dict) or record.get("task_id") != task_id
            or not isinstance(task_id, str) or _TASK_ID_PATTERN.fullmatch(task_id) is None):
        raise _BrokerProtocolError("Captured title has no exact original Task binding.")
    public = _review.public_evidence(record)
    name = public.get("shot", {}).get("name")
    if not isinstance(name, str) or not name:
        raise _BrokerProtocolError("Captured title has no saved public creation name.")
    legacy = deepcopy(public)
    legacy["shot"].pop("name")
    if legacy_wire != _review.public_evidence(legacy):
        raise _BrokerProtocolError("Captured title differs from the immutable casecard.")
    digest = _review._digest(legacy_wire)
    payload = {"schema": "hmb-captured-display-title", "version": 1,
               "operation_id": _captured_display_title_operation_id(task_id, digest, name),
               "name": name, "expected_casecard_sha256": digest,
               "case_id": public.get("case_id"), "input_evidence_sha256": public.get("input_evidence_sha256"),
               "project_id": public.get("project_id"), "project_name": public.get("project_name"),
               "provider": "volcengine_ark", "model": public.get("settings", {}).get("model_id"),
               "shot": {key: public.get("shot", {}).get(key) for key in
                        ("channel_uuid", "shot_uuid", "source_node_instance_id", "number")}}
    _validate_captured_display_title_request(task_id, payload)
    return payload


def _validate_captured_display_title_request(task_id: str, payload: dict[str, Any]) -> None:
    expected = {"schema", "version", "operation_id", "name", "expected_casecard_sha256", "case_id",
                "input_evidence_sha256", "project_id", "project_name", "provider", "model", "shot"}
    if (not isinstance(payload, dict) or set(payload) != expected
            or payload.get("schema") != "hmb-captured-display-title"
            or type(payload.get("version")) is not int or payload["version"] != 1
            or payload.get("provider") != "volcengine_ark"
            or payload.get("model") not in {SEEDANCE_2_0_MODEL_ID, SEEDANCE_2_0_FAST_MODEL_ID, SEEDANCE_2_5_MODEL_ID}
            or not isinstance(payload.get("name"), str)
            or _review._public_shot_name(payload["name"]) != payload["name"] or not payload["name"]
            or not _review._public_id(payload.get("case_id"))
            or not _review._hash(payload.get("expected_casecard_sha256"))
            or not _review._hash(payload.get("input_evidence_sha256"))):
        raise _BrokerProtocolError("Invalid captured display-title metadata.")
    shot = payload.get("shot")
    if (not isinstance(shot, dict) or set(shot) != {"channel_uuid", "shot_uuid", "source_node_instance_id", "number"}
            or any(not isinstance(shot[key], str) or not _review._public_id(shot[key]) for key in
                   ("channel_uuid", "shot_uuid", "source_node_instance_id"))
            or type(shot["number"]) is not int or not 1 <= shot["number"] <= 5):
        raise _BrokerProtocolError("Captured display-title Shot binding is invalid.")
    try:
        project = _review.resolve_project(payload, default_legacy=False)
    except (ValueError, TypeError):
        raise _BrokerProtocolError("Captured display-title project is invalid.") from None
    if any(payload.get(key) != project[key] for key in ("project_id", "project_name")):
        raise _BrokerProtocolError("Captured display-title project is not canonical.")
    expected_operation = _captured_display_title_operation_id(task_id, payload["expected_casecard_sha256"], payload["name"])
    if payload.get("operation_id") != expected_operation:
        raise _BrokerProtocolError("Captured display-title operation is not bound to the original snapshot.")


def _validate_captured_display_title_response(result: dict[str, Any], task_id: str,
                                             *, request: dict[str, Any] | None = None) -> None:
    expected = {"schema", "version", "task_id", "captured_title", "_http_status"}
    if request is not None:
        expected.add("created")
    if (not isinstance(result, dict) or set(result) != expected
            or result.get("schema") != "hmb-captured-display-title"
            or type(result.get("version")) is not int or result["version"] != 1
            or result.get("task_id") != task_id
            or type(result.get("_http_status")) is not int
            or result["_http_status"] not in ({200, 201} if request is not None else {200})
            or request is not None and (type(result.get("created")) is not bool
                or result["created"] != (result["_http_status"] == 201))):
        raise _BrokerProtocolError("Broker returned an invalid captured display-title response.")
    title = result.get("captured_title")
    if title is None and request is None:
        return
    expected_title = {"operation_id", "name", "provenance", "verified_generation_input", "created_at"}
    if (not isinstance(title, dict) or set(title) != expected_title
            or not isinstance(title.get("name"), str) or not title["name"]
            or _review._public_shot_name(title["name"]) != title["name"]
            or title.get("provenance") != "owner_attested_creation_snapshot"
            or title.get("verified_generation_input") is not False
            or type(title.get("created_at")) is not int or not 0 < title["created_at"] <= 10**15):
        raise _BrokerProtocolError("Broker returned invalid captured-title provenance.")
    try:
        operation = str(UUID(title.get("operation_id")))
    except (ValueError, TypeError, AttributeError):
        raise _BrokerProtocolError("Broker returned an invalid captured-title operation.") from None
    if operation != title["operation_id"]:
        raise _BrokerProtocolError("Broker returned a noncanonical captured-title operation.")
    if request is not None and any(title[key] != request[key] for key in ("operation_id", "name")):
        raise _BrokerProtocolError("Broker acknowledged another captured-title snapshot.")


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
            "project_id",
            "project_name",
            "project_selection_schema",
            "draft",
            "draft_job_id",
            GENERATION_MODE_METADATA_FIELD,
            GENERATION_TASK_METADATA_FIELD,
            GENERATION_SHOT_METADATA_FIELD,
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
            "project_id",
            "project_name",
            "project_selection_schema",
            GENERATION_MODE_METADATA_FIELD,
            GENERATION_TASK_METADATA_FIELD,
            GENERATION_SHOT_METADATA_FIELD,
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
        | _SEEDANCE_V2_FIELDS
        | frozenset({"draft", "draft_job_id"}),
    }
    def __init__(
        self, *, opener: Any | None = None, server_url: str | None = None,
    ) -> None:
        self._opener = opener if opener is not None else _broker_build_opener()
        self._server_url = _broker_validated_server_url(server_url)
        self._seedance_capabilities: dict[str, Any] | None = None
        self._generation_mode_metadata_capability: dict[str, frozenset[str]] = {}
        self._generation_shot_metadata_supported = False
        self._generation_mode_metadata_checked_at: float | None = None
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

    @staticmethod
    def _review_task_path(task_id: str) -> str:
        if not isinstance(task_id, str) or _TASK_ID_PATTERN.fullmatch(task_id) is None or len(task_id) > 256:
            raise _BrokerProtocolError("Invalid review Task ID.")
        return "/api/v1/reviews/tasks/" + quote(task_id, safe="")

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
                or type(result.get("page_size")) is not int or result["page_size"] != 20
                or not (retention or manual_retention)):
            raise _BrokerProtocolError("Broker review portal capabilities are unsupported.")
        return result

    def require_generation_project_selection(self, schema: str, *, timeout: float = 5) -> None:
        if schema == PROJECT_SELECTION_SCHEMA:
            return
        if schema != ONLY_PROJECT_SELECTION_SCHEMA:
            raise _BrokerProtocolError("The generation project selection schema is unsupported.")
        admission = self.queue_admission(timeout=timeout)
        if admission is not None:
            self._queue_admission_headers(admission, "only")
        capabilities = {"project_routing": admission.profile("project_routing")} if admission is not None else self.review_capabilities()
        routing = capabilities.get("project_routing")
        supported = routing.get("generation_project_selection_schemas") if isinstance(routing, dict) else None
        if (not isinstance(supported, list) or not supported
                or any(not isinstance(item, str) for item in supported)
                or ONLY_PROJECT_SELECTION_SCHEMA not in supported):
            raise _BrokerProtocolError(
                "This Broker does not support manual Only project selection yet. No media was uploaded or render submitted."
            )

    def get_draft_final_state(self, source: dict[str, Any], *, timeout: float = 5) -> dict[str, Any]:
        record = _seedance_draft_source_value(source)
        if not record or record["broker_server_url"] != self.server_url:
            raise _BrokerProtocolError("Draft status has no exact Broker source binding.")
        # This advisory request must not clear a saved credential on a 401.
        # It never performs refresh, reservation, submission, or media download.
        readonly = copy(self)
        readonly._clear_access_token = lambda: None
        result = readonly._request_json("GET", self._review_task_path(record["draft_job_id"]) + "/draft-final",
                                        payload=None, timeout=timeout)
        return _seedance_draft_final_state_value(result, record)

    def put_task_casecard(self, task_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        if evidence.get("schema") != _review.SCHEMA or evidence.get("version") != 1:
            raise _BrokerProtocolError("Invalid supplemental casecard.")
        evidence = _review.public_evidence(evidence)
        result = self._request_json("PUT", self._review_task_path(task_id) + "/casecard",
                                    payload=evidence, timeout=5,
                                    idempotency_key=_review._digest(evidence))
        if (result.get("casecard") != evidence or type(result.get("created")) is not bool
                or result.get("task_id", task_id) != task_id):
            raise _BrokerProtocolError("Broker did not acknowledge the exact supplemental casecard.")
        return result

    def get_task_casecard(self, task_id: str) -> dict[str, Any] | None:
        result = self._request_json("GET", self._review_task_path(task_id) + "/casecard",
                                    payload=None, timeout=5)
        card = result.get("casecard")
        if ("casecard" not in result or result.get("task_id", task_id) != task_id
                or card is not None and (not isinstance(card, dict)
                    or card.get("schema") != _review.SCHEMA or type(card.get("version")) is not int
                    or card["version"] != 1 or _review.public_evidence(card) != card)):
            raise _BrokerProtocolError("Broker returned an invalid supplemental casecard.")
        return card

    def get_task_captured_title(self, task_id: str) -> dict[str, Any] | None:
        result = self._request_json("GET", self._review_task_path(task_id) + "/captured-title",
                                    payload=None, timeout=5)
        _validate_captured_display_title_response(result, task_id)
        return result["captured_title"]

    def post_task_captured_title(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _validate_captured_display_title_request(task_id, payload)
        result = self._request_json("POST", self._review_task_path(task_id) + "/captured-title",
                                    payload=payload, timeout=5, idempotency_key=payload["operation_id"])
        _validate_captured_display_title_response(result, task_id, request=payload)
        return result

    def post_task_feedback(self, task_id: str, review: dict[str, Any], *, library_version: str = "") -> dict[str, Any]:
        try:
            review_id = str(UUID(str(review.get("review_id") or review.get("client_review_id") or "")))
        except (ValueError, AttributeError, TypeError):
            raise _BrokerProtocolError("Invalid review identity.") from None
        score, category = review.get("score"), review.get("category")
        if type(score) is not int or score not in {1, 2, 3, 4, 5} or category not in {
            "identity", "motion", "camera", "material", "environment", "other"}:
            raise _BrokerProtocolError("Invalid review score or category.")
        body = {"client_review_id": review_id, "score": score, "category": category,
                "note": str(review.get("note") or "")[:4000],
                "input_evidence_sha256": _review._hash(review.get("input_evidence_sha256")),
                "library_version": _review._public_text(library_version, 80)}
        return self._request_json("POST", self._review_task_path(task_id) + "/feedback",
                                  payload=body, timeout=5, idempotency_key=review_id)

    def task_feedback(self, task_id: str, *, is_live: Any = lambda: True) -> dict[str, Any]:
        path = self._review_task_path(task_id) + "/feedback"
        rows, cursor, seen = [], "", set()
        for _page in range(5):
            if not is_live():
                return {"items": rows, "has_more": True, "cancelled": True}
            result = self._request_json("GET", path + ("?" + urlencode({"cursor": cursor}) if cursor else ""),
                                        payload=None, timeout=5)
            items = result.get("items")
            if not isinstance(items, list) or len(items) > 20 or result.get("task_id", task_id) != task_id:
                raise _BrokerProtocolError("Invalid feedback page.")
            rows.extend(items)
            more = result.get("has_more") is True
            next_cursor = result.get("next_cursor")
            if not more:
                return {"items": rows, "has_more": False}
            if not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 2048 or next_cursor in seen:
                raise _BrokerProtocolError("Invalid feedback pagination.")
            seen.add(next_cursor)
            cursor = next_cursor
        return {"items": rows, "has_more": True}

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
    ) -> dict[str, Any]:
        if not path.startswith("/") or path.startswith("//"):
            raise _BrokerProtocolError("FN AI Broker request path is invalid.")
        if submission and path in {"/api/v1/generate/video", "/api/v1/generate/image"}:
            import _hmb_queue_admission as queue
            queue.validate_create(payload, path, queue_operation, queue_only=queue_admission is not None)
        body = None
        with self._reference_auth_lock:
            token = self._load_access_token()
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
        return self._reference_auth_response(result, reference_auth_epoch,
            account=method.upper() == "GET" and path == "/api/me")

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

    @staticmethod
    def _resolve_advertised_output_format(requested_format: str, formats: Any) -> str:
        """Resolve only an explicit valid provider list, never a failed lookup."""
        if (not isinstance(formats, (list, tuple, set, frozenset)) or not formats
                or any(not isinstance(value, str) or value not in OUTPUT_FORMAT_CHOICES for value in formats)):
            raise _BrokerProtocolError("FN AI Broker output format capabilities are malformed.")
        if requested_format in formats:
            return requested_format
        if requested_format == "mov" and "mp4" in formats:
            return "mp4"
        raise _BrokerProtocolError("FN AI Broker has not enabled the selected Seedance output format.")

    def _remember_generation_mode_capability(self, response: Any) -> None:
        """Cache optional display provenance, independently of model features."""
        self._generation_mode_metadata_checked_at = time.monotonic()
        self._generation_mode_metadata_capability = {}
        self._generation_shot_metadata_supported = False
        if (not isinstance(response, dict)
                or response.get("schema") != BROKER_SEEDANCE_CAPABILITIES_SCHEMA
                or type(response.get("version")) is not int
                or response["version"] not in {BROKER_SEEDANCE_CAPABILITIES_VERSION,
                                               BROKER_SEEDANCE_DRAFT_CAPABILITIES_VERSION}
                or not isinstance(response.get("models"), dict)):
            return
        capability = response.get("generation_mode_metadata")
        if (not isinstance(capability, dict)
                or capability.get("schema") != GENERATION_MODE_METADATA_SCHEMA
                or capability.get("field") != GENERATION_MODE_METADATA_FIELD
                or capability.get("task_field") != GENERATION_TASK_METADATA_FIELD):
            return
        modes, tasks = capability.get("choices"), capability.get("tasks")
        if (not isinstance(modes, list) or not isinstance(tasks, list)
                or any(type(value) is not str for value in modes + tasks)):
            return
        self._generation_mode_metadata_capability = {
            "modes": frozenset(modes).intersection({"only", "shot"}),
            "tasks": frozenset(tasks).intersection(TASK_STORAGE_CHOICES),
        }
        shot = response.get("generation_shot_metadata")
        self._generation_shot_metadata_supported = bool(
            isinstance(shot, dict)
            and shot.get("schema") == GENERATION_SHOT_METADATA_SCHEMA
            and type(shot.get("version")) is int and shot["version"] == 1
            and shot.get("field") == GENERATION_SHOT_METADATA_FIELD
            and shot.get("enabled") is True
        )

    def _apply_generation_mode_metadata(self, payload: dict[str, Any], *,
                                        task: str, timeout: float) -> None:
        """Send captured provenance only when this Broker advertises support.

        Absence or failure of this optional feature must preserve legacy render
        semantics. Neither Task nor Only is inferred from the project's schema,
        Draft state, prompt or current widget controls.
        """
        mode = payload.pop(GENERATION_MODE_METADATA_FIELD, None)
        captured_task = payload.pop(GENERATION_TASK_METADATA_FIELD, None)
        captured_shot = _generation_submission_shot(payload.pop(GENERATION_SHOT_METADATA_FIELD, None))
        if type(mode) is not str or mode not in {"only", "shot"}:
            mode = None
        if (type(captured_task) is not str or captured_task not in TASK_STORAGE_CHOICES
                or captured_task != task
                or payload.get("input_mode") not in (None, TASK_INPUT_MODES[captured_task])
                or payload.get("omni_reference_task_type") not in
                   (None, TASK_OMNI_REFERENCE_TYPES.get(captured_task))):
            captured_task = None
        if mode is None and captured_task is None:
            return
        checked = self._generation_mode_metadata_checked_at
        if checked is None or time.monotonic() - checked >= 30.0:
            try:
                readonly = copy(self)
                readonly._clear_access_token = lambda: None
                response = readonly._request_json("GET", BROKER_SEEDANCE_CAPABILITIES_PATH,
                    payload=None, timeout=max(1.0, min(float(timeout), 5.0)))
            except Exception:
                # A pre-V27 Broker, a failed discovery, or a rolling upgrade
                # must not turn optional display metadata into a render gate.
                response = None
            self._remember_generation_mode_capability(response)
        capability = self._generation_mode_metadata_capability
        if mode in capability.get("modes", ()):
            payload[GENERATION_MODE_METADATA_FIELD] = mode
        if captured_task in capability.get("tasks", ()):
            payload[GENERATION_TASK_METADATA_FIELD] = captured_task
        if (mode == "shot" and mode in capability.get("modes", ())
                and self._generation_shot_metadata_supported and captured_shot):
            payload[GENERATION_SHOT_METADATA_FIELD] = captured_shot

    def require_seedance_features(
        self,
        *,
        model_id: str,
        task: str,
        output_format: str,
        return_last_frame: bool,
        timeout: float = 10.0,
        allow_output_fallback: bool = False,
        refresh: bool = False,
        draft: bool = False,
    ) -> str:
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
        ) and not (refresh and model == SEEDANCE_2_5_MODEL_ID and self._seedance_capabilities is not None):
            return requested_format
        if model != SEEDANCE_2_5_MODEL_ID:
            raise _BrokerProtocolError(
                "Advanced Seedance task/output features require Seedance 2.5."
            )

        capability = (None if refresh else
                      getattr(self, "_seedance_draft_task_capabilities", None) if draft else
                      self._seedance_capabilities)
        if capability is None:
            try:
                response = self._queue_syntax(
                    BROKER_SEEDANCE_CAPABILITIES_PATH + ("?draft=1" if draft else ""),
                    name="video_syntax",
                    timeout=max(1.0, min(float(timeout), 30.0)),
                )
            except Exception as exc:
                raise _BrokerProtocolError(
                    "FN AI Broker Seedance 2.5 capabilities could not be verified. "
                    "No render was submitted."
                ) from exc
            if (
                not isinstance(response, dict)
                or response.get("schema") != BROKER_SEEDANCE_CAPABILITIES_SCHEMA
                or type(response.get("version")) is not int
                or response.get("version") not in {BROKER_SEEDANCE_CAPABILITIES_VERSION, BROKER_SEEDANCE_DRAFT_CAPABILITIES_VERSION}
                or not isinstance(response.get("models"), dict)
            ):
                raise _BrokerProtocolError(
                    "FN AI Broker returned an invalid Seedance capability contract."
                )
            self._remember_generation_mode_capability(response)
            models = response["models"]
            profile = models.get(SEEDANCE_2_5_MODEL_ID)
            if not isinstance(profile, dict):
                raise _BrokerProtocolError(
                    "FN AI Broker does not advertise the Seedance 2.5 profile."
                )
            tasks = profile.get("tasks")
            formats = profile.get("draft_output_formats") if draft else profile.get("output_formats")
            if draft and "draft_output_formats" not in profile and requested_format == "mp4" and not getattr(self, "_seedance_draft_formats_declared", False):
                # Legacy authenticated Draft contracts predate the format list
                # and permit only the established MP4 request.
                formats = ["mp4"]
            if (
                not isinstance(tasks, list)
                or not all(isinstance(value, str) for value in tasks)
                or not isinstance(formats, list)
                or not formats
                or not all(isinstance(value, str) and value in OUTPUT_FORMAT_CHOICES for value in formats)
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
            if draft:
                self._seedance_draft_task_capabilities = capability
            else:
                self._seedance_capabilities = capability

        task_slug = TASK_BROKER_SLUGS[authored_task]
        if task_slug not in capability["tasks"]:
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled the selected Seedance 2.5 task."
            )
        effective_format = self._resolve_advertised_output_format(requested_format, capability["output_formats"])
        if effective_format != requested_format and not allow_output_fallback:
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled the selected Seedance output format."
            )
        if return_last_frame and not capability["return_last_frame"]:
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled returned Seedance last frames."
            )
        return effective_format

    def require_seedance_draft_features(self, *, timeout: float = 10.0,
                                       output_format: str = DEFAULT_OUTPUT_FORMAT,
                                       allow_output_fallback: bool = False) -> str:
        """Authenticate the exact Draft contract before uploads or either paid POST."""
        requested_format = str(output_format or "").strip().lower()
        if requested_format not in OUTPUT_FORMAT_CHOICES:
            raise _BrokerProtocolError("Unsupported Seedance Draft output format. No render was submitted.")
        response = self._queue_syntax(
            BROKER_SEEDANCE_CAPABILITIES_PATH + "?draft=1", name="video_syntax",
            timeout=max(1.0, min(float(timeout), 30.0)),
        )
        profile = response.get("models", {}).get(SEEDANCE_2_5_MODEL_ID) if isinstance(response, dict) and isinstance(response.get("models"), dict) else None
        if (not isinstance(response, dict)
                or response.get("schema") != BROKER_SEEDANCE_CAPABILITIES_SCHEMA
                or type(response.get("version")) is not int
                or response.get("version") != BROKER_SEEDANCE_DRAFT_CAPABILITIES_VERSION
                or not isinstance(profile, dict)
                or profile.get("draft_generation") is not True
                or profile.get("draft_preview_resolution") != "480p"
                or profile.get("draft_final_resolution") != "1080p"
                or profile.get("draft_source_reference") != "broker_job_id"
                or type(profile.get("draft_source_ttl_seconds")) is not int
                or profile.get("draft_source_ttl_seconds") != 604800):
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled Seedance 2.5 Draft. No render was submitted."
            )
        self._remember_generation_mode_capability(response)
        # A missing legacy list proves no MOV limitation. Keep old MP4 callers,
        # but stop fresh MOV requests until the server declares its actual formats.
        draft_formats = profile.get("draft_output_formats")
        if "draft_output_formats" not in profile:
            if requested_format == "mp4" and not getattr(self, "_seedance_draft_formats_declared", False):
                return requested_format
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled MOV Draft/Final. Update the Broker before rendering. No render was submitted."
            )
        if not isinstance(draft_formats, list):
            raise _BrokerProtocolError("FN AI Broker Draft output format capabilities are malformed. No render was submitted.")
        effective_format = self._resolve_advertised_output_format(requested_format, draft_formats)
        self._seedance_draft_formats_declared = True
        if effective_format != requested_format and not allow_output_fallback:
            raise _BrokerProtocolError(
                "FN AI Broker has not enabled MOV Draft/Final. No render was submitted."
            )
        return effective_format

    def generate_seedance(
        self,
        payload: dict[str, Any],
        *,
        timeout: float,
        queue_only_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if set(payload) - self._ALLOWED_GENERATION_FIELDS:
            raise _BrokerProtocolError(
                "Seedance Broker payload contained unsupported fields."
            )
        admission = self.queue_admission(timeout=min(float(timeout), 15))
        if queue_only_headers is not None:
            import _hmb_queue_admission as queue
            expected_headers = queue.identity(queue_only_headers)
            if admission is None or admission.headers != expected_headers:
                raise queue.QueueAdmissionError("Maintenance admission changed after the request checkpoint. No create was attempted.")
        queue_operation = "draft_final" if payload.get("draft_job_id") else "only" if payload.get("project_selection_schema") == ONLY_PROJECT_SELECTION_SCHEMA else "video"
        queue_kwargs = {}
        if admission is not None:
            self._queue_admission_headers(admission, queue_operation)
            queue_kwargs = {"queue_admission": admission, "queue_operation": queue_operation}
            models = json.loads(admission._document).get("video_models")
            if not isinstance(models, list) or {"provider": "volcengine_ark", "model": payload.get("model")} not in models:
                raise _BrokerProtocolError("This maintenance queue does not advertise the selected video model.")
        request_payload = {
            key: value
            for key, value in payload.items()
            if value is not None and value != []
        }
        if "project_id" in request_payload or "project_name" in request_payload:
            project = resolve_project(request_payload, default_legacy=False)
            if any(request_payload.get(key) != project[key] for key in ("project_id", "project_name")):
                raise _BrokerProtocolError("Seedance Broker project metadata is not canonical.")
        if "project_selection_schema" in request_payload and (
            request_payload["project_selection_schema"] not in (PROJECT_SELECTION_SCHEMA, ONLY_PROJECT_SELECTION_SCHEMA)
            or not all(key in request_payload for key in ("project_id", "project_name"))
        ):
            raise _BrokerProtocolError("Seedance Broker selected-project provenance is invalid.")
        if request_payload.get("project_selection_schema") == ONLY_PROJECT_SELECTION_SCHEMA:
            self.require_generation_project_selection(ONLY_PROJECT_SELECTION_SCHEMA, timeout=min(timeout, 5))
        request_payload["provider"] = "volcengine_ark"
        model = str(request_payload.get("model") or "").strip()
        if not model:
            raise _BrokerProtocolError("Seedance Broker model is missing.")
        model_fields = self._MODEL_GENERATION_FIELDS.get(model)
        if model_fields is None:
            raise _BrokerProtocolError(
                "Selected Seedance model is not supported by the HMB Broker contract."
            )
        draft_source = request_payload.get("draft_job_id")
        draft = request_payload.get("draft", False)
        if type(draft) is not bool or ("draft" in request_payload and model != SEEDANCE_2_5_MODEL_ID):
            raise _BrokerProtocolError("Draft requires Seedance 2.5 and a literal boolean.")
        if draft_source is not None:
            allowed = {"provider", "model", "draft_job_id", "quality", "resolution", "output_format", "client_request_id", "project_id", "project_name"}
            final_resolution = request_payload.get("resolution", request_payload.get("quality"))
            if (model != SEEDANCE_2_5_MODEL_ID or not isinstance(draft_source, str)
                    or re.fullmatch(r"job-[0-9a-f]{32}", draft_source) is None
                    or final_resolution != "1080p"
                    or ("quality" in request_payload and request_payload["quality"] != final_resolution)
                    or request_payload.get("output_format", DEFAULT_OUTPUT_FORMAT) not in OUTPUT_FORMAT_CHOICES
                    or not isinstance(request_payload.get("client_request_id"), str)
                    or _TASK_ID_PATTERN.fullmatch(request_payload["client_request_id"]) is None
                    or set(request_payload) - allowed):
                raise _BrokerProtocolError("Draft final submission must contain only a local Broker Draft ID, 1080p target and supported output format.")
            self.require_seedance_draft_features(
                timeout=min(float(timeout), 30.0),
                output_format=str(request_payload.get("output_format", DEFAULT_OUTPUT_FORMAT)),
            )
            if admission is not None:
                state = self._request_json("GET", self._review_task_path(draft_source) + "/draft-final", payload=None, timeout=min(timeout, 15))
                if (state.get("source_task_id") != draft_source or state.get("owner_user_id") != admission.principal_id
                        or state.get("state") != "available" or state.get("eligible") is not True or state.get("child_task_id")
                        or type(state.get("expires_at")) is not int or time.time() >= state["expires_at"]
                        or any(state.get(k) != request_payload[k] for k in ("project_id", "project_name") if k in request_payload)):
                    raise _BrokerProtocolError("Draft Final source is unavailable, expired or already reserved. Retrieve the same Task.")
            return self._request_json("POST", "/api/v1/generate/video", payload=request_payload, timeout=timeout,
                                      submission=True,
                                      idempotency_key=str(request_payload.get("client_request_id") or ""), **queue_kwargs)
        if draft:
            if request_payload.get("quality") != "480p" or request_payload.get("resolution") != "480p":
                raise _BrokerProtocolError("Draft previews require 480p.")
            self.require_seedance_draft_features(
                timeout=min(float(timeout), 30.0),
                output_format=str(request_payload.get("output_format", DEFAULT_OUTPUT_FORMAT)),
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
            if advanced_v2 or self._seedance_capabilities is not None:
                self.require_seedance_features(
                    model_id=model,
                    task=task,
                    output_format=requested_format,
                    return_last_frame=requested_last_frame,
                    timeout=min(float(timeout), 30.0),
                    refresh=True,
                    draft=bool(draft),
                )
            if advanced_v2:
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
        self._apply_generation_mode_metadata(request_payload, task=task, timeout=timeout)
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
            **queue_kwargs,
        )

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
                    re.escape(broker.path.rstrip("/")) + r"/api/assets/[A-Za-z0-9_-]{43}", candidate.path
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
            accept = "image/png,image/jpeg,application/octet-stream"
        elif media_type == "video":
            accept = "video/mp4,video/quicktime,application/octet-stream"
        else:
            raise _BrokerProtocolError("Broker result media type is invalid.")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": accept,
                "Authorization": "Bearer " + self._load_access_token(),
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
        if media_type == "image":
            try:
                return _normalize_returned_last_frame(raw, max_bytes=max_bytes)
            except RuntimeError as exc:
                raise _BrokerProtocolError(
                    "Downloaded result is not a valid PNG image."
                ) from exc
        return raw


class LocalReferenceVideoError(RuntimeError):
    """A selected local/project video cannot be resolved or read."""


class _AgentResultUnavailable(RuntimeError):
    """A handled upstream failure: do not submit a replacement render."""


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
        self._hmb_reference_upload_lease_id = ""
        self._submission_outcome_unknown = False
        self._detached_submission_tasks: set[asyncio.Task[Any]] = set()
        self._broker_bridge_instance: _HMBAIBrokerBridge | None = None
        self._broker_action_lock = threading.Lock()
        self._broker_action_running = False
        self._generation_refresh_lock = threading.Lock()
        self._generation_refresh_running = False
        self._generation_run_active = threading.Event()
        self._hmb_draft_finalize_pending = False
        self._hmb_draft_finalize_task = None
        self._hmb_draft_final_context = None
        self._hmb_draft_controls_syncing = False
        self._hmb_draft_pending_source = {}
        self._hmb_draft_final_status_cache: dict[str, Any] = {}
        self._hmb_draft_final_status_future = None
        self._hmb_draft_final_status_scope: tuple[str, ...] = ()
        self._hmb_generation_preview_state = _seedance_generation_preview_value()
        self._hmb_generation_recovery_restore_fingerprint: (
            tuple[Any, ...] | None
        ) = None
        self._hmb_last_saved_recovery_revision = 0
        self._hmb_recovery_journal_owner_id = ""
        self._hmb_generation_started_monotonic: float | None = None
        self._hmb_generation_started_at_ms = 0
        self._hmb_generation_media_revision = 0
        self._hmb_last_success_video: VideoUrlArtifact | None = None
        self._hmb_generated_source_instance_id = str(uuid4())
        self._hmb_generated_video_source: dict[str, Any] = {}
        self._hmb_generated_video_source_published: dict[str, Any] = {}
        self._hmb_generation_run_origin: dict[str, Any] = {}
        self._hmb_review_case_id = ""
        self._hmb_review_inputs: dict[str, Any] = {}
        self._hmb_review_stage = ""
        self._hmb_review_stage_started = time.monotonic()
        self._hmb_review_stage_seconds: dict[str, float] = {}
        self._hmb_review_sync_lock = threading.Lock()
        self._hmb_review_sync_jobs: set[tuple[str, str]] = set()
        self._hmb_review_sync_epoch = 0
        self._hmb_last_success_last_frame_url: ImageUrlArtifact | None = None
        self._hmb_output_format_initial_setup_seen = False
        self._hmb_return_last_frame_initial_setup_seen = False
        self._hmb_output_contract_syncing = False
        self._hmb_pending_generation_action = False
        self._hmb_generation_action_only_update = False
        self._hmb_pending_generation_command_id = ""
        self._hmb_pending_generation_command_action = ""
        self._hmb_pending_gallery_origin = ""
        self._hmb_processed_generation_command_ids: set[str] = set()
        self._hmb_node_deleted = False
        self._hmb_my_box_controller_instance = None
        self._hmb_my_box_parameters_ready = False
        self._hmb_preflight_epoch = 0
        self._hmb_preflight_task = None
        self._hmb_preflight_command_ids: set[str] = set()
        self._hmb_preflight_active_request_id = ""
        self._hmb_preflight_client_sequences = {}
        self._hmb_preflight_active_client_session = ""
        self._hmb_preflight_publishing = False
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
        self._hmb_mode_instance_id = uuid4().hex
        self._hmb_mode_state_revision = 0
        self._hmb_mode_state_key = None

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
        self.add_parameter(
            ParameterDict(
                name=SHOT_FINISH_LOOK_INPUT_PARAMETER,
                type="dict",
                input_types=["dict"],
                accept_any=False,
                default_value={},
                tooltip=(
                    "Hidden exact Finish Look dependency for the selected Shot. "
                    "The public Agent prompt route remains unchanged."
                ),
                allowed_modes={ParameterMode.INPUT},
                hide=True,
                hide_label=True,
                hide_property=True,
                serializable=False,
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

        # A separate, non-serializable property isolates inspection from Shot
        # selection, Draft/Resume commands and all generation inputs.
        preflight_kwargs = {
            "name": SEEDANCE_PREFLIGHT_PARAMETER, "type": "dict",
            "default_value": {"schema": SEEDANCE_PREFLIGHT_SCHEMA, "version": 1,
                "phase": "idle", "request_id": "", "rows": [], "issues": []},
            "allowed_modes": {ParameterMode.PROPERTY}, "serializable": False,
            "tooltip": "Read-only same-flow Shot readiness; never runs or submits a render.",
            "ui_options": {"display_name": "", "is_full_width": True, "hide_label": True,
                "hide_handles": True, "height": 38, "min_height": 38, "max_height": 38,
                "widget_height": 38, "resizable": False, "expandable": False},
        }
        if Widget is not None:
            preflight_kwargs["traits"] = {Widget(name=SEEDANCE_SHOT_WIDGET_NAME,
                library=SEEDANCE_SHOT_WIDGET_LIBRARY_NAME)}
        self.add_parameter(Parameter(**preflight_kwargs))

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
                default_value=MODEL_NAME_SEEDANCE_2_5,
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
        broker_url_kwargs: dict[str, Any] = {
            "name": BROKER_SERVER_URL_PARAMETER,
            "default_value": _broker_display_server_url(),
            "tooltip": (
                "Shared FN AI Broker address for every Generator on this Windows account. "
                "Settings survive restarts and library updates. Clear to disconnect; "
                "existing tasks retain their original server."
            ),
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
                broker_url_parameter = ParameterString(
                    **{
                        **broker_url_kwargs,
                        "traits": {
                            Widget(
                                name=SEEDANCE_SHOT_WIDGET_NAME,
                                library=SEEDANCE_SHOT_WIDGET_LIBRARY_NAME,
                            )
                        },
                    }
                )
            else:
                broker_url_parameter = ParameterString(**broker_url_kwargs)
        except Exception:
            broker_url_parameter = ParameterString(**broker_url_kwargs)
            if Widget is not None:
                with suppress(Exception):
                    broker_url_parameter.add_trait(
                        Widget(
                            name=SEEDANCE_SHOT_WIDGET_NAME,
                            library=SEEDANCE_SHOT_WIDGET_LIBRARY_NAME,
                        )
                    )
        self.add_parameter(broker_url_parameter)
        _BROKER_SETTING_NODES[str(id(self))] = self
        _broker_config.subscribe_broker_changes(self._on_shared_broker_address_changed)
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
                        MODEL_TASK_CHOICES[SEEDANCE_2_5_MODEL_ID]
                    ),
                },
            )
        )
        self.add_parameter(
            ParameterString(
                name=ONLY_PROJECT_PARAMETER,
                default_value=ONLY_PROJECT_UNSELECTED,
                tooltip=(
                    "Project for manual Only-mode renders. Select explicitly when no "
                    "ImageAsset project is connected. A connected ImageAsset remains "
                    "authoritative; a different manual selection is rejected."
                ),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=[ONLY_PROJECT_UNSELECTED, *(
                    PROJECTS[key]["project_name"] for key in ("superwings12", "katuri8")
                ), _my_box_node.protocol.MY_BOX_LABEL])},
                ui_options={"display_name": "Project (Only)", "simple_dropdown": [
                    ONLY_PROJECT_UNSELECTED, *(PROJECTS[key]["project_name"] for key in ("superwings12", "katuri8")), _my_box_node.protocol.MY_BOX_LABEL
                ]},
            )
        )
        # Keep private Only controls beside its explicit selection. The native
        # status/Broker/recovery footer must remain the final UI children.
        _my_box_node.install_parameters(self)
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
                    "10 files; 2.0 models retain the 3-file limit. All models "
                    "require at least one reference image or video with audio."
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
                default_value=MODEL_DEFAULT_RESOLUTIONS[SEEDANCE_2_5_MODEL_ID],
                tooltip=(
                    "Seedance 2.0 defaults to 1080p. Seedance 2.5 and Fast "
                    "default to 720p; 2.5 also offers 480p and 1080p."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=list(MODEL_RESOLUTIONS[SEEDANCE_2_5_MODEL_ID]))},
            )
            ParameterString(
                name="draft_action", default_value=DRAFT_ACTION_OFF,
                tooltip=("Seedance 2.5 Only or Shot at 480p. MOV is the default; an explicit MP4-only provider support list uses MP4. "
                         "After reviewing the Draft, use the dedicated Draft final button once to run only this Generator at 1080p. "
                         "Both stages are separate paid renders. No automatic final render is submitted."),
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=list(DRAFT_ACTION_CHOICES))},
                ui_options={"display_name": "Draft Action", "simple_dropdown": [DRAFT_ACTION_OFF, DRAFT_ACTION_PREVIEW]},
                hide=True,
            )
            ParameterString(
                name="ratio",
                default_value="16:9",
                tooltip="Output aspect ratio.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=list(RATIOS))},
            )
            ParameterInt(
                name="duration",
                default_value=4,
                tooltip=(
                    "Duration: Seedance 2.0 supports 4-15 seconds or -1 smart "
                    "duration; ordinary Seedance 2.5 generation uses 4-30 "
                    "seconds. Video Editing is locked to -1 and preserves "
                    "the source video's duration."
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
                        MODEL_DURATION_CHOICES[SEEDANCE_2_5_MODEL_ID]
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
                default_value=NEW_NODE_OUTPUT_FORMAT,
                tooltip=(
                    "Seedance 2.5 output container. New nodes default to MOV for "
                    "post-production and may require an external "
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
                name="draft_job_id", default_value="",
                tooltip=("Completed Draft LOCAL Broker job ID (job-...). Stored after Draft success. "
                         "Finalization reuses its original prompt/media/settings on the Broker; "
                         "current Generator settings are not resubmitted. Source valid for 7 days."),
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"display_name": "Draft Broker Job ID", "readonly": True}, hide=True,
            )
            ParameterDict(
                name=DRAFT_SOURCE_PARAMETER, default_value={},
                allowed_modes={ParameterMode.PROPERTY}, hide=True,
                ui_options={"hide": True, "hide_property": True, "hide_label": True, "hide_handles": True},
            )
            ParameterDict(
                name=DRAFT_SOURCES_PARAMETER, default_value={"version": 1, "sources": {}},
                allowed_modes={ParameterMode.PROPERTY}, hide=True,
                ui_options={"hide": True, "hide_property": True, "hide_label": True, "hide_handles": True},
            )
            ParameterString(
                name=DRAFT_OWNER_PARAMETER, default_value=str(uuid4()),
                allowed_modes={ParameterMode.PROPERTY}, hide=True,
                ui_options={"hide": True, "hide_property": True, "hide_label": True, "hide_handles": True},
            )
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
                # Rendering progress is shown by the HMB overlay. Pulsing this
                # read-only retained preview also leaves the native player in
                # its loading state while a different result is being prepared.
                pulse_on_run=False,
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
                hide=False,
                hide_property=True,
                hide_label=False,
                ui_options={
                    "display_name": "video_url",
                    "pulse_on_run": True,
                    # Griptape classifies every VideoUrlArtifact as an
                    # expandable media row even when its property editor is
                    # hidden. Keep this output-only alias in a normal grid
                    # row so its cable endpoint stays centred on its label.
                    "grid_item": True,
                    "hide": False,
                    "hide_property": True,
                    "hide_label": False,
                    "hide_handles": False,
                },
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
        self.add_parameter(
            ParameterDict(
                name=GENERATED_VIDEO_SOURCE_PARAMETER,
                default_value={},
                tooltip="Verified completed video with its immutable generation Shot identity.",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                settable=False,
                hide=True, hide_property=True, hide_label=True,
                ui_options={"hide": True, "hide_property": True, "hide_handles": True},
            )
        )
        self._output_file = ProjectFileParameter(
            node=self,
            name="output_file",
            default_filename=f"volcengine_seedance_video.{NEW_NODE_OUTPUT_FORMAT}",
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
                default_value=_seedance_recovery_value({"journal_id": str(uuid4())}),
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
        self._claim_generation_recovery_journal(
            _seedance_recovery_value(self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER))
        )
        self._hmb_my_box_parameters_ready = True
        self._update_parameter_visibility()
        _shot_routing.schedule_post_registration_reconcile(self)

    def _hmb_my_box_controller(self) -> Any:
        controller = getattr(self, "_hmb_my_box_controller_instance", None)
        if controller is None:
            controller = _my_box_node.MyBoxController(self,
                broker_factory=getattr(self, "_hmb_my_box_broker_factory", None),
                journal_root=getattr(self, "_hmb_my_box_journal_root", None))
            self._hmb_my_box_controller_instance = controller
        return controller

    def _hmb_my_box_existing_task(self) -> bool:
        controller = getattr(self, "_hmb_my_box_controller_instance", None)
        return bool((controller is not None and controller.handles_existing())
            or str(self.parameter_output_values.get("generation_id") or "").startswith("job-mybox-"))

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
            if (isinstance(subscription, dict)
                    and subscription.get("participant_kind") == "seedance"
                    and not subscription.get("enabled")):
                suspended = getattr(candidate, "_hmb_suspended_shot_identity", None)
                if isinstance(suspended, dict):
                    subscription = {**subscription, **suspended, "enabled": True}
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
        if (checkpoint_task_id and persisted.get("task_id") == checkpoint_task_id
                and persisted.get("draft_action") in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}):
            if not output_file:
                raise _BrokerProtocolError("The saved Draft output path is unavailable. No new render was submitted.")
            # Refresh and explicit Resume share the exact paid-stage path and
            # reject collisions instead of inheriting project overwrite policy.
            return _SeedanceDraftOutputDestination(output_file)
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
        self._assert_operation_project_selection()
        context = getattr(self, "_hmb_draft_final_context", None)
        if isinstance(context, dict):
            try:
                source = self._validated_draft_final_source(context["source"], allow_reserved=True)
                if self._draft_source_record().get("draft_job_id") != source["draft_job_id"]:
                    return False
            except (ValueError, RuntimeError):
                return False
        return bool(
            not require_registered
            or self._runtime_node_is_live(require_registered=True)
        )

    async def _discard_unsent_generation_checkpoint(self, *, reason: str) -> None:
        """Clear a provisional identity after proving no create call began."""
        await self._run_blocking_generation_stage(self._reject_unsubmitted_reference_lease)
        self._release_unsubmitted_draft_reservation()
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["generation_status"] = ""
        self.parameter_output_values["provider_response"] = None
        self._clear_generation_recovery_checkpoint()
        if self._runtime_node_is_live(require_registered=True):
            await self._force_save_generation_recovery_checkpoint(
                required=False,
                reason=reason,
            )

    def _claim_generation_recovery_journal(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        """Fork a copied live node's journal, but retain identity on real reopen."""
        identity = checkpoint["journal_id"]
        if not identity:
            return checkpoint
        changed = False
        with _RECOVERY_JOURNAL_OWNERS_GUARD:
            if bool(getattr(self, "_hmb_node_deleted", False)):
                return checkpoint
            owner = _RECOVERY_JOURNAL_OWNERS.get(identity)
            if owner is not None and owner is not self and owner._runtime_node_is_live(require_registered=True):
                checkpoint = dict(checkpoint, journal_id=str(uuid4()))
                identity = checkpoint["journal_id"]
                changed = True
            previous = self._hmb_recovery_journal_owner_id
            if previous != identity and _RECOVERY_JOURNAL_OWNERS.get(previous) is self:
                _RECOVERY_JOURNAL_OWNERS.pop(previous, None)
            _RECOVERY_JOURNAL_OWNERS[identity] = self
            self._hmb_recovery_journal_owner_id = identity
        if changed:
            self.set_parameter_value(SEEDANCE_RECOVERY_PARAMETER, checkpoint, emit_change=False)
        return checkpoint

    def _capture_generated_video_origin(self) -> dict[str, Any]:
        """Capture the selected Shot synchronously before generation awaits."""
        try:
            subscription = self._hmb_shot_channel_subscription()
        except Exception:
            return {}
        if not subscription.get("enabled"):
            return {}
        instance = getattr(self, "_hmb_generated_source_instance_id", "")
        if not instance:
            instance = self._hmb_generated_source_instance_id = str(uuid4())
        return _generated_video_origin({
            "channel_uuid": subscription.get("channel_uuid"),
            "shot_uuid": subscription.get("shot_uuid"),
            "number": subscription.get("shot_number"),
            "name": subscription.get("shot_name"),
            "source_node_instance_id": instance,
        })

    def _hmb_generated_video_source_snapshot(self) -> dict[str, Any]:
        if self._hmb_my_box_controller().current_output_is_private():
            return {}
        source = _generated_video_source_value(getattr(self, "_hmb_generated_video_source", None))
        if not source:
            source = _generated_video_source_value(
                self.get_parameter_value(GENERATED_VIDEO_SOURCE_PARAMETER)
            )
        if not source:
            source = self._restore_completed_video_source_for_lut()
        return deepcopy(source)

    def _restore_completed_video_source_for_lut(self) -> dict[str, Any]:
        """Adopt a saved pre-LUT success, without rendering or downloading again."""
        if self._hmb_my_box_controller().current_output_is_private():
            return {}
        if getattr(self, "_hmb_node_deleted", False):
            return {}
        artifact = self.parameter_output_values.get("VIDEO_OUT") or self.parameter_output_values.get("video_url")
        location = str(getattr(artifact, "value", artifact) or "").strip()
        if not location or urlparse(location).scheme in {"http", "https"}:
            return {}
        checkpoint = _seedance_recovery_value(self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER))
        widget = self.get_parameter_value(SEEDANCE_SHOT_WIDGET_PARAMETER)
        preview = _seedance_generation_preview_value(widget.get("generation") if isinstance(widget, dict) else {})
        if preview["phase"] != "succeeded" and checkpoint.get("stage") != "local_succeeded":
            return {}
        task_id = str(preview.get("job_id") or checkpoint.get("task_id") or self.parameter_output_values.get("generation_id") or "")
        identity = _generated_video_origin(checkpoint.get("generation_origin"))
        if not identity:
            identity = self._capture_generated_video_origin()
            # Old exports encode their Shot number in the filename. Do not
            # assign a stale Shot 1 movie to a newly selected Shot 2.
            match = re.search(r"_shot_(\d+)(?:_|\.)", location, re.IGNORECASE)
            if not identity or not match or int(match.group(1)) != identity["number"]:
                return {}
        try:
            resolved = File(location).resolve()
            path = Path(str(getattr(resolved, "location", resolved)))
            if not path.is_absolute() or not path.is_file():
                return {}
        except Exception:
            return {}
        source = _generated_video_source_value({"schema": GENERATED_VIDEO_SOURCE_SCHEMA, "version": 1,
            **identity, "generation_id": task_id, "task_id": task_id, "result_revision": 1,
            "path": str(path), "url": str(path), "completed": True})
        if source:
            self._hmb_generated_video_source = deepcopy(source)
            self.parameter_values[GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(source)
            self.parameter_output_values[GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(source)
        return source

    def _hmb_publish_generated_video_source(self, *, force: bool = False) -> bool:
        """Republish the last success without executing this generator."""
        if getattr(self, "_hmb_node_deleted", False):
            return False
        source = self._hmb_generated_video_source_snapshot()
        if not source:
            return False
        self.parameter_output_values[GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(source)
        if not force and source == getattr(self, "_hmb_generated_video_source_published", None):
            return True
        publisher = getattr(self, "publish_update_to_parameter", None)
        try:
            if callable(publisher):
                publisher(GENERATED_VIDEO_SOURCE_PARAMETER, deepcopy(source))
        except Exception:
            return False
        self._hmb_generated_video_source_published = deepcopy(source)
        return True

    def _record_completed_video_source(
        self, origin: Any, generation_id: str, saved: Any,
    ) -> bool:
        """Publish only verified local success; failed/legacy runs keep the last one."""
        identity = _generated_video_origin(origin)
        if not identity or getattr(self, "_hmb_node_deleted", False):
            return False
        try:
            resolved = saved.resolve()
            path = str(getattr(resolved, "location", resolved))
        except Exception:
            path = str(getattr(saved, "location", "") or "")
        if not Path(path).is_absolute():
            path = str(getattr(saved, "location", "") or "")
        previous = self._hmb_generated_video_source_snapshot()
        source = _generated_video_source_value({
            "schema": GENERATED_VIDEO_SOURCE_SCHEMA, "version": 1,
            **identity, "generation_id": generation_id, "task_id": generation_id,
            "result_revision": min(2_147_483_647, int(previous.get("result_revision") or 0) + 1),
            "path": path, "url": path, "completed": True,
        })
        if not source:
            return False
        if previous and all(previous.get(key) == value for key, value in source.items()
                            if key != "result_revision"):
            source = previous
        self._hmb_generated_video_source = deepcopy(source)
        self.parameter_values[GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(source)
        self.parameter_output_values[GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(source)
        # The resulting route belongs to the completed origin even if the UI
        # has already selected another Shot. This never invokes upstream work.
        try:
            _shot_routing.reconcile_completed_video_routes(self)
        except Exception:
            logger.warning("%s completed-video route refresh was unavailable.", self.name)
        return self._hmb_publish_generated_video_source()

    def _generation_recovery_state(self) -> dict[str, Any]:
        """Use this node's saved/live checkpoint, never newer external state.

        A journal is written independently of native Save. Its newer task may
        belong to edits explicitly discarded when closing the workflow. The
        shared UUID identifies a checkpoint lineage, not permission to replace
        the user's saved task or pair its saved video with a different render.
        Explicit Refresh still uses the saved/live task ID; legacy serialized
        outputs below are migrated only from this same node instance.
        """

        checkpoint = _seedance_recovery_value(
            self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER)
        )
        checkpoint = self._claim_generation_recovery_journal(checkpoint)
        journal_id = checkpoint["journal_id"]
        if checkpoint["task_id"]:
            return checkpoint
        if checkpoint["updated_at_ms"]:
            # An explicit clear is a durable tombstone, not an invitation to
            # revive an old non-serializable generation_id from the host.
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
                "journal_id": journal_id,
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
                        and str(provider_response.get("id") or "").strip() == generation_id
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
                "broker_server_url": (
                    AI_BROKER_INTERNAL_ORIGIN
                    if os.environ.get("HMB_AI_BROKER_URL", AI_BROKER_INTERNAL_ORIGIN).rstrip("/") == AI_BROKER_INTERNAL_ORIGIN
                    else ""
                ),
            }
        )
        return checkpoint

    def _authoritative_existing_generation_id(self) -> str:
        """Resolve the same-task identity used by every manual refresh path.

        Griptape may briefly replay non-serializable output parameters after the
        durable recovery property has hydrated.  An unresolved checkpoint is
        therefore selected before a possibly stale output ID.  For completed
        history the existing output/resume behavior remains primary, while
        ``resume_generation_id`` can never redirect an unresolved paid task.
        """

        if _my_box_node.is_selected(self):
            checkpoint = self._hmb_my_box_controller().checkpoint()
            if checkpoint:
                return str(checkpoint.get("job_id") or checkpoint.get("client_request_id") or "")
        if self._hmb_my_box_existing_task():
            return str(self.parameter_output_values.get("generation_id") or "")
        checkpoint = self._generation_recovery_state()
        checkpoint_id = str(checkpoint.get("task_id") or "").strip()
        checkpoint_status = str(checkpoint.get("status") or "").strip().lower()
        checkpoint_requires_resolution = bool(
            checkpoint_id
            and checkpoint.get("stage") != "local_succeeded"
            and checkpoint.get("terminal") is not True
            and checkpoint_status not in TERMINAL_FAILURE_STATUSES
        )
        output_id = self.parameter_output_values.get("generation_id")
        resume_id = self.get_parameter_value("resume_generation_id")
        candidates = (
            (checkpoint_id, output_id, resume_id)
            if checkpoint_requires_resolution
            else (output_id, resume_id, checkpoint_id)
        )
        for candidate in candidates:
            task_id = str(candidate or "").strip()
            if not task_id:
                continue
            try:
                return self._validate_task_id(task_id)
            except _BrokerProtocolError:
                continue
        return ""

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

        previous = self._generation_recovery_state()
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
        current_output_file = str(source_params.get("_hmb_output_file") or self._current_recovery_output_file())
        default_output_file = str(
            getattr(self._output_file, "_default_filename", "") or ""
        ).strip()
        output_file = (
            current_output_file or default_output_file
            if stage == "pre_submit"
            else previous_output_file or current_output_file or default_output_file
        )
        saved_origin = (
            str(previous.get("broker_server_url") or "")
            if stage != "pre_submit" and previous.get("task_id") else ""
        )
        operation_origin = str(source_params.get("_hmb_broker_server_url") or "")
        if stage != "pre_submit" and previous.get("task_id") and not (
            saved_origin or operation_origin
        ):
            raise _BrokerProtocolError(
                "The saved Broker task has no trustworthy server origin. No request was sent."
            )
        broker_server_url = _broker_validated_server_url(
            operation_origin or saved_origin
            or self.get_parameter_value(BROKER_SERVER_URL_PARAMETER)
        )
        checkpoint = _seedance_recovery_value(
            {
                "journal_id": previous["journal_id"] or str(uuid4()),
                "revision": min(
                    2_147_483_647,
                    int(previous.get("revision") or 0) + 1,
                ),
                "stage": stage,
                "task_id": task_id,
                "task_identity": task_identity,
                "status": status,
                "terminal": terminal,
                "updated_at_ms": max(int(time.time() * 1000), previous["updated_at_ms"] + 1),
                "model_id": model_id,
                "output_format": raw_format,
                "return_last_frame": return_last_frame,
                "output_file": output_file,
                "broker_server_url": broker_server_url,
                "draft_action": previous.get("draft_action", source_params.get("draft_action")) if stage != "pre_submit" else source_params.get("draft_action"),
                "draft_project": source_params.get("_hmb_draft_project", previous.get("draft_project")),
                "draft_source": source_params.get("_hmb_draft_source", previous.get("draft_source")),
                "draft_source_bindings": source_params.get("_hmb_draft_source_bindings", previous.get("draft_source_bindings")),
                "draft_started_at_ms": source_params.get("_hmb_draft_started_at_ms", previous.get("draft_started_at_ms")),
                "generation_origin": (
                    source_params.get("_hmb_generation_origin")
                    if "_hmb_generation_origin" in source_params
                    else previous.get("generation_origin")
                    if stage != "pre_submit" and previous.get("task_id") == task_id
                    else {}
                ),
                "shot_hierarchy": (
                    source_params.get("_hmb_shot_hierarchy", {}) if stage == "pre_submit"
                    else previous.get("shot_hierarchy", {})
                ),
                "reference_lease_id": (
                    source_params.get("_hmb_reference_upload_lease_id", "") if stage == "pre_submit"
                    else previous.get("reference_lease_id", "")
                ),
                "queue_only_headers": source_params.get("_hmb_queue_only_headers", {}) if stage == "pre_submit" else previous.get("queue_only_headers", {}),
            }
        )
        self.set_parameter_value(
            SEEDANCE_RECOVERY_PARAMETER,
            checkpoint,
            emit_change=False,
        )
        try:
            _review.bind_task_origin(checkpoint["task_id"], checkpoint["broker_server_url"])
            if source_params.get("project_id"):
                _review.bind_task_project(checkpoint["task_id"], source_params)
        except (OSError, ValueError, TypeError):
            # Optional review routing never replaces the paid recovery journal
            # or changes submission/retrieval success.
            logger.warning("Optional Task review origin could not be recorded.")
        self._hmb_generation_recovery_restore_fingerprint = None
        return checkpoint

    def _clear_generation_recovery_checkpoint(self) -> None:
        previous = _seedance_recovery_value(self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER))
        self.set_parameter_value(
            SEEDANCE_RECOVERY_PARAMETER,
            _seedance_recovery_value({
                "journal_id": previous["journal_id"] or str(uuid4()),
                "revision": previous["revision"] + 1,
                "updated_at_ms": max(int(time.time() * 1000), previous["updated_at_ms"] + 1),
            }),
            emit_change=False,
        )
        self._hmb_generation_recovery_restore_fingerprint = None

    async def _force_save_generation_recovery_checkpoint(
        self,
        *,
        required: bool,
        reason: str,
    ) -> bool:
        """Persist only task recovery metadata; stock Save/auto-save stay untouched.

        The historical method name is retained for the submission boundary.
        No workflow API, registry mutation, editor event or whole-graph save is
        allowed here. Required persistence still precedes the billable POST.
        """

        if bool(getattr(self, "_hmb_node_deleted", False)):
            if required:
                raise RuntimeError("The Generator was deleted or reset. No new render was submitted.")
            return False
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
                async with _workflow_checkpoint_lock():
                    if bool(getattr(self, "_hmb_node_deleted", False)):
                        raise RuntimeError("The Generator was deleted or reset; its recovery journal is retired.")
                    checkpoint = self._generation_recovery_state()
                    if not checkpoint["journal_id"]:
                        checkpoint["journal_id"] = str(uuid4())
                        self.set_parameter_value(SEEDANCE_RECOVERY_PARAMETER, checkpoint, emit_change=False)
                    await asyncio.to_thread(self._write_live_generation_recovery_journal, checkpoint)
                if bool(getattr(self, "_hmb_node_deleted", False)):
                    raise RuntimeError("The Generator was deleted or reset; its recovery journal is retired.")
                self._hmb_last_saved_recovery_revision = int(
                    checkpoint.get("revision") or 0
                )
                return True
            except Exception as exc:
                failure = exc
                if bool(getattr(self, "_hmb_node_deleted", False)):
                    if required:
                        raise RuntimeError("The Generator was deleted or reset. No new render was submitted.") from exc
                    return False
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
                "No render was submitted. Check local recovery-folder write access and disk space, then retry."
            ) from failure
        return False

    def _write_live_generation_recovery_journal(self, checkpoint: dict[str, Any]) -> None:
        """Reject queued writes from a deleted/Reset instance.

        Native Reset creates a separate journal identity. Its previous node
        cannot resume publishing recovery state after replacement.
        """
        with self._generation_refresh_lock:
            if bool(getattr(self, "_hmb_node_deleted", False)):
                raise RuntimeError("The Generator was deleted or reset; its recovery journal is retired.")
            _write_seedance_recovery_journal(checkpoint)

    def _retire_deleted_generation_recovery(self) -> None:
        """Detach only this deleted instance. Never cancel a server task or delete media.

        Native Reset deletes the old instance too, so Reset and Delete/New have
        exactly the same local retirement semantics, even for uncertain jobs.
        The host also calls this hook when closing a whole workflow. Keep the
        diagnostic disk record, but never load it into a reopened saved node.
        A newly created node has a new UUID and no prior task or result.
        """
        identity = _seedance_uuid_text(getattr(self, "_hmb_recovery_journal_owner_id", ""))
        with _RECOVERY_JOURNAL_OWNERS_GUARD:
            owns_journal = bool(identity and _RECOVERY_JOURNAL_OWNERS.get(identity) is self)
            if owns_journal:
                _RECOVERY_JOURNAL_OWNERS.pop(identity, None)
        self._hmb_recovery_journal_owner_id = ""
        self._hmb_generation_recovery_restore_fingerprint = None
        self._hmb_last_saved_recovery_revision = 0
        for key in ("generation_id", "generation_status"):
            self.parameter_output_values[key] = ""
        self.parameter_output_values["provider_response"] = None
        self._hmb_generation_preview_state = _seedance_generation_preview_value()

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

        current = (self.parameter_output_values.get("VIDEO_OUT")
                   or self.parameter_output_values.get("video_url"))
        if (self._generation_artifact_is_present(current)
                and current is self.parameter_output_values.get("video_url")
                and not self.parameter_output_values.get("VIDEO_OUT")
                and str(getattr(current, "value", "")).startswith(("http://127.0.0.1:", "http://localhost:", "http://[::1]:"))):
            # The visible property can contain a temporary loopback read URL;
            # it is never the canonical generated file retained for rerenders.
            current = getattr(self, "_hmb_last_success_video", None)
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
        self._record_review_stage(phase, job_id)
        self._sync_seedance_shot_widget(emit_change=True)

    def _record_review_stage(self, phase: str, task_id: str = "") -> None:
        """Observe status transitions without changing recovery or billing authority."""
        if (_my_box_node.is_selected(self) or task_id.startswith("job-mybox-")
                or getattr(getattr(self, "_hmb_my_box_controller_instance", None), "_busy", False)):
            return
        previous = getattr(self, "_hmb_review_stage", "")
        if phase == previous:
            return
        now = time.monotonic()
        durations = getattr(self, "_hmb_review_stage_seconds", {})
        if previous:
            durations[previous] = durations.get(previous, 0.) + max(0., now - getattr(self, "_hmb_review_stage_started", now))
        self._hmb_review_stage = phase
        self._hmb_review_stage_started = now
        self._hmb_review_stage_seconds = durations
        if task_id:
            try:
                _review.update_case(task_id, case_id=getattr(self, "_hmb_review_case_id", ""),
                                    status=phase, stage_elapsed_seconds=durations)
            except (OSError, ValueError, TypeError):
                logger.warning("Local task evidence update unavailable (%s).", phase)

    def _start_review_case(self, client_request_id: str, submitted_prompt: str) -> None:
        try:
            source = None if self._draft_final_requested() else self._manual_agent_prompt_source()
            getter = getattr(source, "_hmb_agent_reference_observation_snapshot", None)
            managed = getattr(self, "_hmb_managed_agent_request", None)
            observation = (deepcopy(managed["record"].get("observation") or {})
                           if isinstance(managed, dict)
                           else getter() if callable(getter) else {"status": "not_available"})
            self._hmb_review_case_id = _review.start_case(
                client_request_id, getattr(self, "_hmb_review_inputs", {}), submitted_prompt,
                _get_build_diagnostics(), observation if isinstance(observation, dict) else {},
            )
        except Exception as exc:
            # Optional evidence failure must not change the paid-task protocol.
            self._hmb_review_case_id = ""
            logger.warning("Local task evidence preparation unavailable (%s).", type(exc).__name__)

    def _review_origin_for_task(self, task_id: str) -> str:
        self._validate_task_id(task_id)
        pinned = _review.task_origin(task_id)
        checkpoint = self._generation_recovery_state()
        if pinned:
            origin = _broker_validated_server_url(pinned)
            if (checkpoint.get("task_id") == task_id and checkpoint.get("broker_server_url")
                    and _broker_validated_server_url(checkpoint["broker_server_url"]) != origin):
                raise _BrokerProtocolError("This Task has conflicting Broker origin evidence.")
            return origin
        if checkpoint.get("task_id") == task_id and checkpoint.get("broker_server_url"):
            origin = _broker_validated_server_url(checkpoint["broker_server_url"])
            _review.bind_task_origin(task_id, origin)
            return origin
        # The current settings panel is never authority for an older Task.
        raise _BrokerProtocolError("This Task has no recorded Broker origin.")

    def _review_sync_is_live(self, epoch: int) -> bool:
        return (self._runtime_node_is_live(require_registered=True)
                and int(getattr(self, "_hmb_review_sync_epoch", 0)) == epoch)

    def _set_captured_title_sync_state(self, task_id: str, status: str, reason: str = "") -> None:
        """Keep title metadata separate from generation and casecard status."""
        self._hmb_captured_title_sync_state = {"task_id": task_id, "status": status, "reason": reason}
        notice = "[CAPTURED_TITLE_SYNC] The saved video name could not be synchronized. Review metadata can be retried."
        try:
            # A background result must not replace another Task's active render status.
            current = self._authoritative_existing_generation_id()
            active = getattr(self, "_generation_run_active", None)
            if current != task_id or callable(getattr(active, "is_set", None)) and active.is_set():
                return
            getter = getattr(self, "get_parameter_value", None)
            publisher = getattr(self, "publish_update_to_parameter", None)
            if not callable(getter) or not callable(publisher):
                return
            previous = str(getter("status_details") or "")
            lines = [line for line in previous.splitlines() if line != notice]
            if status in {"failed", "login_required"}:
                lines.append(notice)
            updated = "\n".join(lines)
            if updated != previous:
                setter = getattr(self, "set_parameter_value", None)
                if callable(setter):
                    setter("status_details", updated)
                publisher("status_details", updated)
        except Exception:
            # Optional display publication cannot turn a completed render into failure.
            pass

    def _sync_captured_display_title(self, bridge: _HMBAIBrokerBridge, task_id: str,
                                     record: dict[str, Any], capabilities: dict[str, Any],
                                     *, is_live: Any) -> None:
        if not (capabilities.get("captured_title_supported") is True
                and capabilities.get("captured_title_schema") == "hmb-captured-display-title"
                and type(capabilities.get("captured_title_version")) is int
                and capabilities["captured_title_version"] == 1):
            if is_live():
                self._set_captured_title_sync_state(task_id, "unsupported")
            return
        try:
            evidence = _review.public_evidence(record)
            if not evidence.get("shot", {}).get("name"):
                if is_live():
                    self._set_captured_title_sync_state(task_id, "not_available")
                return
            # This authenticated whole-record lookup is mandatory even if an old
            # local sync digest is known. The digest alone is not owner authority.
            existing = bridge.get_task_casecard(task_id)
            if not is_live():
                return
            if existing == _review.public_evidence(evidence):
                self._set_captured_title_sync_state(task_id, "embedded")
                return
            legacy = deepcopy(evidence)
            legacy["shot"].pop("name")
            legacy_wire = _review.public_evidence(legacy)
            if existing != legacy_wire:
                raise _BrokerProtocolError("The immutable captured-title casecard does not match.")
            payload = _captured_display_title_request(task_id, record, legacy_wire)
            title = bridge.get_task_captured_title(task_id)
            if not is_live():
                return
            if title is not None:
                # Preserve any existing attestation; never replace it with today's
                # mutable Library title or write a competing metadata operation.
                if title.get("name") != payload["name"]:
                    raise _BrokerProtocolError("The Task already has another captured display name.")
            else:
                bridge.post_task_captured_title(task_id, payload)
                if not is_live():
                    return
            self._set_captured_title_sync_state(task_id, "synced")
        except Exception as exc:
            if is_live():
                status = "login_required" if isinstance(exc, _BrokerAuthenticationError) else "failed"
                self._set_captured_title_sync_state(task_id, status, "portal_title_" + status)
                logger.warning("Optional captured video name sync unavailable (%s).", type(exc).__name__)

    def _sync_review_task(self, task_id: str, origin: str, epoch: int) -> None:
        """Optional metadata only; never create/refresh/download a generation."""
        live = lambda: self._review_sync_is_live(epoch)
        if not live():
            return
        record = _review.read_case(task_id)
        try:
            if record:
                _review.mark_server_sync(task_id, status="pending")
            bridge = self._create_broker_bridge(server_url=origin)
            capabilities = bridge.review_capabilities()
            if not live():
                return
            if record:
                evidence = _review.public_evidence(record)
                digest = _review._digest(evidence)
                synced = record.get("server_sync", {})
                binding_confirmed = False
                # A pre-name binding is immutable. Reuse only its exact saved
                # digest; no current Shot lookup or retrospective title write.
                if "name" in evidence.get("shot", {}):
                    legacy = deepcopy(evidence)
                    legacy["shot"].pop("name")
                    legacy_digest = _review._digest(legacy)
                    if synced.get("evidence_sha256") == legacy_digest:
                        evidence = legacy
                        digest = legacy_digest
                    elif synced.get("status") != "synced" or synced.get("evidence_sha256") != digest:
                        existing = bridge.get_task_casecard(task_id)
                        if not live():
                            return
                        if existing is not None:
                            # Bridge PUT applies the existing projection once
                            # more (e.g. sparse observation defaults). Compare
                            # that exact wire shape while keeping saved hashes.
                            if existing == _review.public_evidence(legacy):
                                evidence, digest = legacy, legacy_digest
                            elif existing != _review.public_evidence(evidence):
                                raise _BrokerProtocolError("The immutable casecard differs from the saved Task inputs.")
                            binding_confirmed = True
                if not binding_confirmed and (synced.get("status") != "synced" or synced.get("evidence_sha256") != digest):
                    result = bridge.put_task_casecard(task_id, evidence)
                    if result.get("task_id", task_id) != task_id:
                        raise _BrokerProtocolError("Review evidence response belongs to another Task.")
                    if not live():
                        return
                _review.mark_server_sync(task_id, status="synced", evidence_sha256=digest)
                self._sync_captured_display_title(bridge, task_id, record, capabilities, is_live=live)
                if not live():
                    return
                for row in record.get("reviews", []):
                    if not live():
                        return
                    if row.get("server_sync", {}).get("status") == "synced":
                        continue
                    try:
                        bridge.post_task_feedback(task_id, row,
                                                  library_version=record.get("build", {}).get("library_version", ""))
                    except _BrokerError:
                        if live():
                            _review.mark_review_sync(task_id, row["review_id"], status="failed", reason="broker_request_failed")
                        raise
                    if live():
                        _review.mark_review_sync(task_id, row["review_id"], status="synced")
            feedback = bridge.task_feedback(task_id, is_live=live)
            if live() and not feedback.get("cancelled"):
                _review.cache_server_feedback(task_id, feedback["items"], has_more=feedback["has_more"])
        except Exception as exc:
            status = ("login_required" if isinstance(exc, _BrokerAuthenticationError) else
                      "unsupported" if isinstance(exc, _BrokerError) and getattr(exc, "status_code", 0) in {404, 405, 501}
                      else "failed")
            if live() and record:
                with suppress(OSError, ValueError, TypeError):
                    _review.mark_server_sync(task_id, status=status,
                                             reason="portal_" + status)
            logger.warning("Optional Task review sync unavailable (%s).", type(exc).__name__)

    def _schedule_review_sync(self, task_id: str) -> bool:
        if not self._runtime_node_is_live(require_registered=True):
            return False
        try:
            origin = self._review_origin_for_task(task_id)
        except (OSError, ValueError, TypeError, _BrokerError):
            return False
        key = (hashlib.sha256(origin.encode()).hexdigest(), task_id)
        epoch = int(getattr(self, "_hmb_review_sync_epoch", 0))
        lock = getattr(self, "_hmb_review_sync_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._hmb_review_sync_lock = lock
            self._hmb_review_sync_jobs = set()
        with lock:
            if key in self._hmb_review_sync_jobs:
                return False
            self._hmb_review_sync_jobs.add(key)
        def worker() -> None:
            try:
                self._sync_review_task(task_id, origin, epoch)
            finally:
                with lock:
                    self._hmb_review_sync_jobs.discard(key)
        try:
            threading.Thread(target=worker, name=f"{self.name}-review-sync", daemon=True).start()
            return True
        except Exception:
            with lock:
                self._hmb_review_sync_jobs.discard(key)
            return False

    def _schedule_open_review_gallery(self, origin: str) -> None:
        """Acknowledge command first; open only an ordinary authenticated page."""
        epoch = int(getattr(self, "_hmb_review_sync_epoch", 0))
        origin = _broker_validated_server_url(origin)
        def launch() -> None:
            if not self._review_sync_is_live(epoch):
                return
            try:
                if self._selected_broker_server_url() != origin:
                    return
                webbrowser.open(origin + "/reviews", new=2, autoraise=True)
                task_id = self._authoritative_existing_generation_id()
                if task_id:
                    self._schedule_review_sync(task_id)
            except Exception as exc:
                logger.warning("Review gallery could not open (%s).", type(exc).__name__)
        try:
            event_loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if event_loop is not None and event_loop.is_running():
                event_loop.call_soon_threadsafe(lambda: threading.Thread(
                    target=launch, name=f"{self.name}-gallery-open", daemon=True).start())
                return
        except Exception:
            pass
        threading.Thread(target=launch, name=f"{self.name}-gallery-open", daemon=True).start()

    def _restore_saved_generation_media_revision(
        self, generation_id: str, artifact: Any,
    ) -> None:
        """Resume the counter from matching completed-file provenance, never UI."""
        if not generation_id or getattr(self, "_hmb_node_deleted", False):
            return
        source = _generated_video_source_value(
            self.get_parameter_value(GENERATED_VIDEO_SOURCE_PARAMETER)
        )
        if not source or source.get("task_id") != generation_id:
            return
        output_id = str(self.parameter_output_values.get("generation_id") or "").strip()
        if output_id and output_id != generation_id:
            return
        location = getattr(artifact, "value", None)
        if not isinstance(location, str) or not location:
            return
        if urlparse(location).scheme and not re.match(r"^[A-Za-z]:[\\/]", location):
            return
        try:
            resolved = File(location).resolve()
            path = Path(str(getattr(resolved, "location", resolved))).resolve()
            if not path.is_file() or path != Path(source["path"]).resolve():
                return
        except Exception:
            return
        previous = int(getattr(self, "_hmb_generation_media_revision", 0))
        restored = max(previous, source["result_revision"])
        if restored != previous:
            self._hmb_generation_media_revision = restored
            # A later provenance replay must not be hidden by an earlier
            # recovery fingerprint made before that property was available.
            self._hmb_generation_recovery_restore_fingerprint = None

    def _restore_generation_recovery_preview(self) -> None:
        """Recreate only the same-task UI action after workflow hydration."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        checkpoint = self._generation_recovery_state()
        generation_id = str(checkpoint.get("task_id") or "").strip()
        refresh_native = getattr(self, "_refresh_native_local_video_preview", None)
        if callable(refresh_native):
            refresh_native()
        current_video = self.parameter_output_values.get(
            "VIDEO_OUT"
        ) or self.parameter_output_values.get("video_url")
        video_present = self._generation_artifact_is_locally_available(
            current_video
        )
        if video_present:
            self._restore_saved_generation_media_revision(generation_id, current_video)
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
                and str(provider_response.get("id") or "").strip() == generation_id
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
        current_generation_id = str(
            self.parameter_output_values.get("generation_id") or ""
        ).strip()
        current_generation_status = str(
            self.parameter_output_values.get("generation_status") or ""
        ).strip().lower()
        provider_matches = bool(
            isinstance(provider_response, dict)
            and str(provider_response.get("id") or "").strip() == generation_id
            and str(provider_response.get("status") or "").strip().lower()
            == restored_status
            and (not terminal or provider_response.get("terminal") is True)
        )
        outputs_match_recovery = bool(
            current_generation_id == generation_id
            and current_generation_status == restored_status
            and provider_matches
        )
        if (
            self._hmb_generation_recovery_restore_fingerprint == fingerprint
            and outputs_match_recovery
        ):
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
        if stage != "local_succeeded" and (
            status == "submission_unknown"
            or (
                isinstance(provider_response, dict)
                and str(provider_response.get("id") or "") == checkpoint["task_id"]
                and provider_response.get("resubmit_allowed") is False
                and provider_response.get("error_code")
                in {"submission_unknown", "provider_overdue"}
            )
        ):
            return True
        terminal = bool(
            checkpoint.get("terminal") is True
            or status in TERMINAL_FAILURE_STATUSES
            or (
                isinstance(provider_response, dict)
                and str(provider_response.get("id") or "").strip() == checkpoint["task_id"]
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
                "VIDEO_OUT"
            ) or self.parameter_output_values.get("video_url")
            return not self._generation_artifact_is_locally_available(
                current_video
            )
        return True

    def _assert_new_submission_is_safe(self, *, explicit_run: bool = False) -> None:
        """Unresolved history prevents automatic replay, not a fresh explicit Run.

        The live run/refresh lock in ``aprocess`` still serializes this node.
        Do not clear or mark the previous remote task terminal here: preflight
        may fail, and Refresh must still be able to inspect the saved identity.
        Only a validated new pre-submit checkpoint replaces that identity.
        """
        if not self._generation_recovery_blocks_new_submission():
            return
        checkpoint = self._generation_recovery_state()
        if explicit_run:
            logger.warning(
                "%s explicit Run supersedes unresolved task %s (%s). "
                "The remote task was not cancelled; duplicate charges are possible. "
                "No automatic resubmission is enabled.",
                self.name, checkpoint["task_id"], checkpoint.get("status"),
            )
            return
        self._restore_generation_recovery_preview()
        raise RuntimeError(
            "A previously submitted Seedance task still requires confirmation. "
            f"Task ID: {checkpoint['task_id']}. Click Status > Refresh / Retrieve "
            "Result (or the central Existing Task Result button) to resolve this "
            "same request first. A confirmed failed/cancelled/expired task or a "
            "successfully retrieved video allows the next explicit Run. "
            "A replacement render was not submitted."
        )

    def _request_existing_generation_refresh(self) -> None:
        """Accept one browser pulse without accepting any browser task ID."""

        preview = _seedance_generation_preview_value(
            self._hmb_generation_preview_state
        )
        authoritative_id = self._authoritative_existing_generation_id()
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

    def _on_finalize_draft_clicked(self, _button: Any, _details: Any, *, action_id: str = "",
                                   expected_draft_job_id: str = "") -> Any:
        """Capture one exact completed Draft and dispatch only this Generator."""
        if _my_box_node.is_selected(self):
            return self._hmb_my_box_controller().schedule_final(_details, expected_draft_job_id)
        reserved_here = False
        try:
            if not self._runtime_node_is_live(require_registered=True):
                raise ValueError("The Generator is inactive.")
            self._assert_draft_final_flow_idle()
            source = self._validated_draft_final_source()
            if expected_draft_job_id != source["draft_job_id"]:
                raise ValueError("The selected Draft changed. Review the current Shot before finalizing.")
            event_loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if event_loop is None or not event_loop.is_running():
                raise ValueError("The engine event loop is unavailable; no Final was submitted.")
            with self._generation_refresh_lock:
                if (self._generation_run_active.is_set() or self._generation_refresh_running
                        or self._hmb_draft_finalize_pending):
                    return NodeMessageResult(success=True, details="Generator is busy; no duplicate Final was scheduled.",
                                             response=_details, altered_workflow_state=False)
                self._hmb_draft_finalize_pending = True
                self._hmb_draft_pending_source = deepcopy(source)
                reserved_here = True
            clear = getattr(self, "clear_cancellation", None)
            if callable(clear):
                clear()
            command_id = action_id or "final-" + uuid4().hex
            future = asyncio.run_coroutine_threadsafe(self._run_draft_final(source, command_id), event_loop)
            self._hmb_draft_finalize_future = future
            def finished(_future: Any) -> None:
                # Cancellation before the coroutine's first instruction has
                # no finally block, so release only that unstarted dispatch.
                def release_unstarted() -> None:
                    if (getattr(self, "_hmb_draft_finalize_future", None) is _future
                            and self._hmb_draft_finalize_task is None):
                        with self._generation_refresh_lock:
                            self._hmb_draft_finalize_pending = False
                            self._hmb_draft_pending_source = {}
                        with suppress(Exception):
                            self._sync_seedance_shot_widget(emit_change=True)
                if _future.cancelled():
                    event_loop.call_soon_threadsafe(release_unstarted)
            future.add_done_callback(finished)
            with suppress(Exception):
                self._sync_seedance_shot_widget(emit_change=True)
            return NodeMessageResult(success=True, details="Finalize 1080p was scheduled for this Draft only.",
                                     response=_details, altered_workflow_state=False)
        except Exception as exc:
            if reserved_here:
                with self._generation_refresh_lock:
                    self._hmb_draft_finalize_pending = False
                    self._hmb_draft_pending_source = {}
            return NodeMessageResult(success=False, details=str(exc), response=_details, altered_workflow_state=False)

    async def _run_draft_final(self, source: dict[str, Any], action_id: str) -> None:
        """No StartFlow/ResolveNode or upstream execution is invoked here."""
        self._hmb_draft_finalize_task = asyncio.current_task()
        try:
            if not self._runtime_node_is_live(require_registered=True) or self.is_cancellation_requested:
                raise ValueError("Finalization was cancelled before execution.")
            self._assert_draft_final_flow_idle()
            source = self._validated_draft_final_source(source)
            current = self._draft_source_record()
            if current.get("draft_job_id") != source["draft_job_id"]:
                raise ValueError("The completed Draft changed before Finalization started.")
            params = self._get_parameters()
            params.update(draft_action=DRAFT_ACTION_FINAL, draft_job_id=source["draft_job_id"],
                          _hmb_draft_source=deepcopy(source), _hmb_draft_supported=True,
                          model_id=SEEDANCE_2_5_MODEL_ID, resolution="1080p", output_format="mov",
                          return_last_frame=False, resume_generation_id="", prompt="", first_frame=None,
                          last_frame=None, reference_images=[], video_references=[], video_reference_slots=[], reference_audio=[],
                          _hmb_generation_origin=deepcopy(source.get("generation_origin", {})))
            self._hmb_draft_final_context = {"source": source, "params": params,
                "client_request_id": _seedance_draft_final_request_id(source["draft_job_id"]),
                "action_id": action_id}
            await self.aprocess()
        except Exception as exc:
            logger.warning("%s Finalization was not started: %s", self.name, str(exc))
            self._set_status_results(was_successful=False, result_details=str(exc))
        finally:
            self._hmb_draft_final_context = None
            self._hmb_draft_finalize_task = None
            with self._generation_refresh_lock:
                self._hmb_draft_finalize_pending = False
                self._hmb_draft_pending_source = {}
            with suppress(Exception):
                self._update_parameter_visibility()
                self._sync_seedance_shot_widget(emit_change=True)

    def _cancel_draft_final(self, expected_draft_job_id: str) -> Any:
        active = self._active_draft_job_id()
        if not active or active != expected_draft_job_id or not self._hmb_draft_finalize_pending:
            return NodeMessageResult(success=False, details="The active Draft Final changed; nothing was cancelled.",
                                     response=None, altered_workflow_state=False)
        cancel = getattr(self, "request_cancellation", None)
        if callable(cancel):
            cancel()
        future = getattr(self, "_hmb_draft_finalize_future", None)
        if future is not None:
            future.cancel()
        return NodeMessageResult(success=True,
            details="Final stop requested. An accepted remote task remains available through Refresh / Retrieve Result.",
            response=None, altered_workflow_state=False)

    def _active_draft_job_id(self) -> str:
        context = getattr(self, "_hmb_draft_final_context", None)
        source = context.get("source", {}) if isinstance(context, dict) else getattr(self, "_hmb_draft_pending_source", {})
        return str(source.get("draft_job_id") or "") if self._hmb_draft_finalize_pending else ""

    @staticmethod
    def _assert_draft_final_flow_idle() -> None:
        try:
            manager = GriptapeNodes.FlowManager()
            check = getattr(manager, "check_for_existing_running_flow", None)
            if not callable(check):
                raise ValueError("Engine execution state is unavailable.")
            if check():
                raise ValueError("Wait for the current workflow to finish before Finalize 1080p.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Engine execution state is unavailable; no Final was submitted.") from exc

    def _release_unsubmitted_draft_reservation(self) -> None:
        """Release only when no POST began or create was definitively rejected."""
        recovery = self._generation_recovery_state()
        source = _seedance_draft_source_value(recovery.get("draft_source"))
        if (source and source.get("final_request_id") == recovery.get("task_id")
                and recovery.get("task_identity") == "client_request"):
            source.pop("final_request_id", None)
            self._store_draft_source(source)

    def _local_original_generation_preview(self) -> dict[str, str]:
        """Mint a read URL for the existing original; never publish or convert it."""
        if getattr(self, "_hmb_node_deleted", False):
            return {}
        artifact = (self.parameter_output_values.get("VIDEO_OUT")
                    or self.parameter_output_values.get("video_url")
                    or getattr(self, "_hmb_last_success_video", None))
        source = getattr(artifact, "value", None)
        if (not isinstance(source, str) or not source.strip()
                or len(source) > 4096 or re.search(r"[\x00-\x1f\x7f]", source)):
            return {}
        try:
            if urlparse(source).scheme and not re.match(r"^[A-Za-z]:[\\/]", source):
                return {}
            from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
            from griptape_nodes.files.path_utils import canonicalize_to_posix, strip_windows_long_path_prefix

            driver = self.engine.static_files_manager.storage_driver
            if not isinstance(driver, LocalStorageDriver):
                return {}  # A cloud/custom driver must never receive this file.
            resolved = File(source).resolve()
            path = Path(str(getattr(resolved, "location", resolved))).resolve()
            if not path.is_file():
                return {}
            before = path.stat()
            identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size,
                                     stat.st_mtime_ns, stat.st_ctime_ns)
            url = driver.create_signed_download_url(path)
            if identity(before) != identity(path.stat()):
                return {}  # Never bind a read URL across an original replacement.
            preview = _seedance_local_preview_value({"source": source, "url": url})
            if not preview:
                return {}
            # Prove the URL's path as well as its host: a driver returning an
            # unrelated local resource cannot bind it to this original source.
            absolute = Path(strip_windows_long_path_prefix(path))
            workspace = Path(strip_windows_long_path_prefix(driver.workspace_directory)).resolve()
            try:
                relative = absolute.relative_to(workspace)
                expected = f"{driver.base_url}/{relative.as_posix()}"
            except ValueError:
                external = canonicalize_to_posix(str(absolute)).removeprefix("/")
                expected = f"{driver.base_url.rsplit('/workspace', 1)[0]}/external/{external}"
            if urlparse(url)._replace(query="").geturl() != expected:
                return {}
            current = (self.parameter_output_values.get("VIDEO_OUT")
                       or self.parameter_output_values.get("video_url")
                       or getattr(self, "_hmb_last_success_video", None))
            if (getattr(self, "_hmb_node_deleted", False) or current is not artifact
                    or getattr(current, "value", None) != source):
                return {}
            return preview
        except Exception:
            # Preview is optional; an absent/incompatible local server must not
            # change the completed Task, existing artifact, or generation path.
            return {}

    def _native_local_video_preview_artifact(self, artifact: Any) -> Any:
        """Project an original file into the native player without conversion.

        VIDEO_OUT, recovery and finishing provenance keep the original local
        MOV/MP4. Only the read-only video_url property receives the exact local
        storage read URL. The desktop otherwise requests MOV conversion and can
        keep its center loading indicator after the original is already ready.
        """
        if artifact is None or getattr(self, "_hmb_node_deleted", False):
            return artifact
        try:
            preview = self._local_original_generation_preview()
            source = str(getattr(artifact, "value", "") or "")
            if not preview or preview.get("source") != source:
                return artifact
            url = preview["url"]
            key = (id(artifact), source, url)
            cached = getattr(self, "_hmb_native_local_video_preview", None)
            if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == key:
                return cached[1]
            # A workflow can already contain this exact read URL. Reuse its
            # artifact ID as well, instead of restarting playback on hydration.
            current = self.parameter_output_values.get("video_url")
            if (current is not artifact and getattr(current, "value", None) == url
                    and getattr(current, "name", None) == getattr(artifact, "name", None)):
                projected = current
            else:
                metadata = getattr(artifact, "meta", None)
                projected = VideoUrlArtifact(value=url,
                    name=getattr(artifact, "name", None) or Path(source).name,
                    meta=deepcopy(metadata) if isinstance(metadata, dict) else {})
            self._hmb_native_local_video_preview = (key, projected)
            return projected
        except Exception:
            # Optional display transport must never turn a saved render into
            # a failure, change Task identity, or fall back to server media.
            return artifact

    def get_display_value_for_output(self, parameter_name: str, output_value: Any) -> Any:
        """Project native output replay as well as ordinary completion events.

        The SDK restores is_output=True values directly into its output dict;
        it does not call set_parameter_value or after_value_set. Both the dict's
        AlterElementEvent and the initial GetAllNodeInfo/GetNodeElementDetails
        snapshot use this supported display hook. Keep raw saved file identity
        intact and never rely on a guessed deserialization lifecycle callback.
        """
        if parameter_name == "video_url":
            projected = self._native_local_video_preview_artifact(output_value)
            if projected is not output_value:
                return projected
        parent = getattr(super(), "get_display_value_for_output", None)
        return parent(parameter_name, output_value) if callable(parent) else output_value

    def _refresh_native_local_video_preview(self) -> None:
        """Remint a local read URL after saved outputs and recovery hydrate."""
        if getattr(self, "_hmb_node_deleted", False):
            return
        artifact = (self.parameter_output_values.get("VIDEO_OUT")
                    or self.parameter_output_values.get("video_url")
                    or getattr(self, "_hmb_last_success_video", None))
        source = str(getattr(artifact, "value", "") or "")
        if not source or urlparse(source).scheme in {"http", "https"}:
            return
        projected = self._native_local_video_preview_artifact(artifact)
        if projected is artifact:
            return
        if self.parameter_output_values.get("VIDEO_OUT") is not artifact:
            self.parameter_output_values["VIDEO_OUT"] = artifact
        self._hmb_last_success_video = artifact
        if self.parameter_output_values.get("video_url") is not projected:
            self.parameter_output_values["video_url"] = projected

    def _generation_preview_for_widget(self) -> dict[str, Any]:
        """Build trusted display state for both stored values and UI events."""
        generation = dict(self._hmb_generation_preview_state)
        generation.pop("local_preview", None)
        local_preview = self._local_original_generation_preview()
        if local_preview:
            generation["local_preview"] = local_preview
        return generation

    def _sync_seedance_shot_widget(
        self, *, emit_change: bool = False, available_catalog: dict[str, Any] | None = None,
    ) -> None:
        parameter = self.get_parameter_by_name(SEEDANCE_SHOT_WIDGET_PARAMETER)
        if parameter is None:
            return
        identity = self._shot_identity()
        if available_catalog is None:
            available_catalog = self._hmb_available_seedance_shot_catalog(
                self._hmb_shot_catalog_snapshot
            )
        next_value = _seedance_widget_value(
            {
                "channel_uuid": identity["channel_uuid"],
                "shot_uuid": identity["shot_uuid"],
            },
            available_catalog,
            self._generation_preview_for_widget(),
            getattr(self, "_hmb_remote_prompt_route", None),
            self._draft_ui_state(),
        )
        mode_fields = getattr(self, "_hmb_seedance_mode_widget_fields", None)
        if callable(mode_fields):
            next_value.update(mode_fields())
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
        available_catalog: dict[str, Any] | None = None,
    ) -> None:
        previous_identity = self._shot_identity()
        requested = self._shot_uuid(requested_shot_uuid)
        snapshot = self._hmb_shot_catalog_snapshot
        available_snapshot = (available_catalog if available_catalog is not None
                              else self._hmb_available_seedance_shot_catalog(snapshot))
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
        self._sync_seedance_shot_widget(available_catalog=available_snapshot)

    def _hmb_seedance_mode_intent(self) -> dict[str, Any]:
        """Read optional author intent; never treat it as source/media authority.

        Native node metadata is already preserved by old workflow loaders.  No
        new required parameter or changed legacy save command is introduced.
        """
        metadata = getattr(self, "metadata", None)
        if not isinstance(metadata, dict) or SEEDANCE_EXECUTION_MODE_METADATA not in metadata:
            return {}
        raw = metadata[SEEDANCE_EXECUTION_MODE_METADATA]
        if (not isinstance(raw, dict) or raw.get("schema") != SEEDANCE_EXECUTION_MODE_SCHEMA
                or type(raw.get("version")) is not int or raw.get("version") != 1 or type(raw.get("revision")) is not int
                or not 0 < raw["revision"] <= 9007199254740991
                or type(raw.get("mode")) is not str
                or raw.get("mode") not in {"only", "shot"}):
            return {"mode": "invalid", "revision": 0}
        value = {"mode": raw["mode"], "revision": raw["revision"]}
        if value["mode"] == "shot":
            channel, shot = self._shot_uuid(raw.get("channel_uuid")), self._shot_uuid(raw.get("shot_uuid"))
            if not channel or not shot:
                return {"mode": "invalid", "revision": raw["revision"]}
            value.update(channel_uuid=channel, shot_uuid=shot,
                         shot_number=raw.get("shot_number", 1), shot_name=str(raw.get("shot_name") or "")[:128])
        return value

    def _hmb_seedance_requested_shot_identity(self) -> dict[str, Any]:
        intent = self._hmb_seedance_mode_intent()
        if intent.get("mode") == "shot":
            return {key: intent[key] for key in ("channel_uuid", "shot_uuid", "shot_number", "shot_name")}
        if intent:
            return {}
        suspended = getattr(self, "_hmb_suspended_shot_identity", None)
        if isinstance(suspended, dict) and self._shot_uuid(suspended.get("channel_uuid")) and self._shot_uuid(suspended.get("shot_uuid")):
            return dict(suspended)
        identity = self._shot_identity()
        return identity if identity.get("channel_uuid") and identity.get("shot_uuid") else {}

    def _hmb_seedance_execution_mode(self) -> str:
        intent = self._hmb_seedance_mode_intent()
        if intent.get("mode") == "only":
            return "only"
        if intent.get("mode") == "invalid":
            return "waiting"
        identity = self._shot_identity()
        if intent.get("mode") == "shot":
            catalog = getattr(self, "_hmb_shot_catalog_snapshot", None)
            matched = (isinstance(catalog, dict) and catalog.get("channel_uuid") == intent["channel_uuid"]
                       and any(isinstance(row, dict) and row.get("shot_uuid") == intent["shot_uuid"]
                               for row in catalog.get("shots", [])))
            return "shot" if (matched and all(identity.get(key) == intent[key] for key in ("channel_uuid", "shot_uuid"))) else "waiting"
        if identity.get("channel_uuid") and identity.get("shot_uuid"):
            return "shot"
        if self._hmb_seedance_requested_shot_identity():
            return "waiting"
        return "auto" if self.get_parameter_value(SHOT_AUTOCLAIM_ENABLED_PARAMETER) is True else "only"

    def _hmb_commit_seedance_mode(self, requested_uuid: str = "") -> None:
        """Commit one explicit selection without touching media, tasks or controls."""
        selected = None
        catalog = getattr(self, "_hmb_shot_catalog_snapshot", None)
        if requested_uuid:
            available = self._hmb_available_seedance_shot_catalog(catalog)
            selected = next((row for row in (available or {}).get("shots", [])
                             if row.get("shot_uuid") == requested_uuid), None)
            if selected is None:
                raise ValueError("The requested Shot is no longer available. Select it again.")
        revision = self._hmb_seedance_mode_intent().get("revision", 0) + 1
        if revision > 9007199254740991:
            raise ValueError("Generator selection revision is exhausted.")
        value = {"schema": SEEDANCE_EXECUTION_MODE_SCHEMA, "version": 1,
                 "revision": revision, "mode": "shot" if selected else "only"}
        if selected is not None:
            value.update(channel_uuid=catalog["channel_uuid"], shot_uuid=selected["shot_uuid"],
                         shot_number=selected["number"], shot_name=selected["name"])
        self.metadata = {**dict(getattr(self, "metadata", {}) or {}), SEEDANCE_EXECUTION_MODE_METADATA: value}
        controller = getattr(self, "_hmb_my_box_controller_instance", None)
        if controller is not None:
            controller.invalidate()

    def _hmb_seedance_mode_widget_fields(self) -> dict[str, Any]:
        intent = self._hmb_seedance_mode_intent()
        mode = self._hmb_seedance_execution_mode()
        pending = self._hmb_seedance_requested_shot_identity()
        # A legacy bound UUID absent from the UI catalog is a pending Shot,
        # never evidence that the user explicitly chose independent Only.
        catalog = getattr(self, "_hmb_shot_catalog_snapshot", None)
        if mode == "shot" and (not isinstance(catalog, dict)
                or catalog.get("channel_uuid") != pending.get("channel_uuid")
                or not any(row.get("shot_uuid") == pending.get("shot_uuid") for row in catalog.get("shots", []) if isinstance(row, dict))):
            mode = "waiting"
        requested = ("shot" if intent.get("mode") == "invalid" else intent.get("mode")) or ("shot" if pending else "only" if mode == "only" else "auto")
        fields = {"execution_mode": mode, "requested_mode": requested,
                  "execution_mode_revision": intent.get("revision", 0),
                  "pending_shot": {"channel_uuid": str(pending.get("channel_uuid") or ""),
                                   "shot_uuid": str(pending.get("shot_uuid") or ""),
                                   "number": pending.get("shot_number", 1), "name": str(pending.get("shot_name") or "")[:128]}}
        key = json.dumps(fields, sort_keys=True, ensure_ascii=False)
        if key != getattr(self, "_hmb_mode_state_key", None):
            self._hmb_mode_state_key = key
            self._hmb_mode_state_revision = int(getattr(self, "_hmb_mode_state_revision", 0)) + 1
        if not getattr(self, "_hmb_mode_instance_id", ""):
            self._hmb_mode_instance_id = uuid4().hex
        return {**fields, "execution_mode_state_revision": self._hmb_mode_state_revision,
                "execution_mode_instance": self._hmb_mode_instance_id}

    def _assert_only_mode_inputs(self) -> None:
        """Only never invokes a shared Shot Agent/Prompt manager implicitly."""
        if self._hmb_seedance_execution_mode() != "only":
            return
        source = self._manual_agent_prompt_source()
        manager_api = getattr(source, "_hmb_shot_manager_enabled", None)
        if callable(manager_api) and manager_api():
            raise _AgentResultUnavailable(
                "Only mode cannot run the shared HMB Shot Agent. Use a Standard Agent or a direct prompt, or explicitly select a Shot.")

    def _shot_identity(self) -> dict[str, Any]:
        intent_getter = getattr(self, "_hmb_seedance_mode_intent", None)
        intent = intent_getter() if callable(intent_getter) else {}
        if intent.get("mode") == "only":
            return {"channel_uuid": "", "shot_uuid": "", "shot_number": 1, "shot_name": SHOT_ONLY_LABEL}
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
            self._hmb_refresh_managed_prompt_projection()
            self._sync_seedance_shot_widget(emit_change=True)

    def _hmb_managed_prompt_projection(self) -> str | None:
        """Read this Generator's public Shot text, never the Agent's open row.

        ``None`` keeps ordinary/Only/legacy prompt inputs native.  An exact
        manager edge opts into per-Shot presentation, including an empty result
        for a Shot that has not run.  The bounded retained connection index is
        read directly: rendering/saving a prompt must not reconcile the graph
        or perform a whole-Flow discovery pass.
        """
        if hasattr(self, "_web_owner") or bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        identity = self._shot_identity()
        if not identity.get("channel_uuid") or not identity.get("shot_uuid"):
            return None
        try:
            connections = GriptapeNodes.FlowManager().get_connections()
            prompt = self.get_parameter_by_name("prompt")
            edges = connections.get_incoming_connections_to_parameter(self, prompt) if prompt is not None else []
        except Exception:
            return None
        if not isinstance(edges, (list, tuple)) or len(edges) != 1:
            return None
        edge = edges[0]
        if (getattr(edge, "target_node", None) is not self
                or getattr(getattr(edge, "target_parameter", None), "name", "") != "prompt"
                or getattr(getattr(edge, "source_parameter", None), "name", "") != "output"):
            return None
        source = getattr(edge, "source_node", None)
        manager = getattr(source, "_hmb_shot_manager_enabled", None)
        preview = getattr(source, "_hmb_agent_shot_preview", None)
        if not callable(manager) or not callable(preview):
            return None
        try:
            if manager() is not True:
                return None
            # The edge object carries the actual node instance, so a deleted
            # or replaced owner cannot donate another instance's visible text.
            if bool(getattr(source, "_hmb_node_deleted", False)):
                return ""
            value = preview(channel_uuid=identity["channel_uuid"], shot_uuid=identity["shot_uuid"])
        except Exception:
            return ""
        if not isinstance(value, dict) or not isinstance(value.get("text"), str):
            return ""
        shot = value.get("shot")
        if (not isinstance(shot, dict)
                or any(shot.get(key) != identity.get(key)
                       for key in ("channel_uuid", "shot_uuid"))):
            return ""
        return value["text"]

    def _get_raw_parameter_value(self, param_name: str) -> Any:
        if param_name == "prompt":
            projected = self._hmb_managed_prompt_projection()
            if projected is not None:
                return projected
        return super()._get_raw_parameter_value(param_name)

    def _hmb_refresh_managed_prompt_projection(
        self, *, source_node: Any = None, channel_uuid: str = "", shot_uuid: str = "", force: bool = False,
    ) -> bool:
        """Refresh only an exact manager-owned prompt; never execute an Agent."""
        if bool(getattr(self, "_hmb_prompt_projection_syncing", False)):
            return False
        identity = self._shot_identity()
        if ((channel_uuid and channel_uuid != identity.get("channel_uuid"))
                or (shot_uuid and shot_uuid != identity.get("shot_uuid"))):
            return False
        if source_node is not None:
            try:
                connections = GriptapeNodes.FlowManager().get_connections()
                parameter = self.get_parameter_by_name("prompt")
                edges = connections.get_incoming_connections_to_parameter(self, parameter) if parameter is not None else []
                if len(edges) != 1 or getattr(edges[0], "source_node", None) is not source_node:
                    return False
            except Exception:
                return False
        projected = self._hmb_managed_prompt_projection()
        if projected is None:
            return False
        if not force and getattr(self, "parameter_values", {}).get("prompt") == projected:
            return False
        self._hmb_prompt_projection_syncing = True
        try:
            # Store the same value that SDK serialization and native UI events
            # read.  Public graph ports remain unchanged for old workflows.
            super().set_parameter_value("prompt", projected)
        finally:
            self._hmb_prompt_projection_syncing = False
        return True

    def after_incoming_connection(self, source_node: Any, source_parameter: Any, target_parameter: Any) -> None:
        result = super().after_incoming_connection(source_node, source_parameter, target_parameter)
        if getattr(target_parameter, "name", "") == "prompt":
            self._hmb_refresh_managed_prompt_projection(source_node=source_node, force=True)
        return result

    @staticmethod
    def _agent_route_subscription(source_node: Any, identity: dict[str, Any]) -> Any:
        """Describe this Generator's Shot independently of the open Agent row.

        This is UI decoration only. The physical edge and immutable per-run
        result continue to establish execution authority.
        """
        try:
            manager = getattr(source_node, "_hmb_shot_manager_enabled", None)
            if callable(manager) and manager():
                declared = source_node._hmb_agent_shot_subscriptions()
                if not isinstance(declared, (list, tuple)) or len(declared) > 5:
                    return None
                fields = ("channel_uuid", "shot_uuid", "shot_number", "shot_name")
                exact = [item for item in declared if isinstance(item, dict)
                         and item.get("participant_kind") == "agent" and item.get("enabled") is True
                         and all(item.get(key) == identity.get(key) for key in fields)]
                return exact[0] if len(exact) == 1 else None
            getter = getattr(source_node, "_hmb_shot_channel_subscription", None)
            return getter() if callable(getter) else None
        except Exception:
            return None

    def _hmb_prepare_remote_prompt_route(self, source_node: Any) -> bool:
        """Pre-arm exact old/new edge hiding before retained-mode mutation.

        The real graph edge remains execution authority. This bounded UI-only
        descriptor is published first so neither the initial connection nor a
        Shot A -> B replacement can paint a transient cable.
        """

        identity = self._shot_identity()
        subscription = self._agent_route_subscription(source_node, identity)
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
        subscription = self._agent_route_subscription(source_node, identity)
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
        suspended = getattr(self, "_hmb_suspended_shot_identity", None)
        intent_getter = getattr(self, "_hmb_seedance_mode_intent", None)
        intent = intent_getter() if callable(intent_getter) else {}
        if intent.get("mode") == "invalid":
            self._hmb_shot_route_status = {"ok": False, "code": "mode_invalid", "details": "Select Only or a valid Shot again."}
            return
        if intent.get("mode") == "only":
            identity = {"channel_uuid": "", "shot_uuid": ""}
            suspended = None
        elif intent.get("mode") == "shot":
            identity = {key: intent[key] for key in ("channel_uuid", "shot_uuid", "shot_number", "shot_name")}
            if identity["channel_uuid"] != snapshot["channel_uuid"]:
                self._hmb_shot_route_status = {"ok": False, "code": "remote_waiting", "details": "Waiting for the selected Shot publisher."}
                return
            suspended = identity
        if (not identity["shot_uuid"] and isinstance(suspended, dict)
                and suspended.get("channel_uuid") == snapshot["channel_uuid"]):
            identity = suspended
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
        if (not intent and identity.get("channel_uuid") and identity.get("shot_uuid")
                and selected is None):
            # Legacy auto-bound workflows have no explicit mode metadata yet.
            # Removing one Shot must retain its exact owner just like removing
            # the whole publisher. Otherwise clearing the visible quartet lets
            # this Generator claim another Shot on the following routing turn.
            # Persist the pending identity so saving while it is absent is safe.
            pending_identity = dict(identity)
            self._hmb_suspended_shot_identity = pending_identity
            suspended = pending_identity
            self.metadata = {
                **dict(getattr(self, "metadata", {}) or {}),
                SEEDANCE_EXECUTION_MODE_METADATA: {
                    "schema": SEEDANCE_EXECUTION_MODE_SCHEMA,
                    "version": 1,
                    "revision": 1,
                    "mode": "shot",
                    **pending_identity,
                },
            }
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
            not intent
            and not identity.get("shot_uuid")
            and not isinstance(suspended, dict)
            and self.get_parameter_value(SHOT_AUTOCLAIM_ENABLED_PARAMETER)
        )
        self._apply_seedance_shot_selection(
            selected["shot_uuid"] if isinstance(selected, dict) else "",
            fallback_to_available=fallback_to_available,
            available_catalog=available_snapshot,
        )
        if self._shot_identity().get("shot_uuid"):
            self._hmb_suspended_shot_identity = None
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
        if not identity["shot_uuid"]:
            suspended = getattr(self, "_hmb_suspended_shot_identity", None)
            if isinstance(suspended, dict):
                identity = suspended
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

        identity = self._shot_identity()
        if str(reason) == "publisher_unavailable":
            if identity["channel_uuid"] and identity["shot_uuid"]:
                # A temporary missing publisher must not reassign this node by
                # display number or borrow a standalone Picker's new channel.
                self._hmb_suspended_shot_identity = {
                    "channel_uuid": identity["channel_uuid"],
                    "shot_uuid": identity["shot_uuid"],
                }
        else:
            self._hmb_suspended_shot_identity = None
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
        mode_getter = getattr(self, "_hmb_seedance_execution_mode", None)
        if callable(mode_getter) and mode_getter() == "only":
            self._hmb_shot_route_status.update(ok=True, code="only", details="Only mode has no managed Shot dependency.")
        return self._hmb_shot_channel_subscription()

    def _hmb_reject_duplicate_shot_selection(
        self,
        reason: str = "duplicate_seedance_shot",
    ) -> dict[str, Any]:
        """Fail a duplicate claim closed by returning this generator to Only."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()
        self._hmb_suspended_shot_identity = None
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
        if (strict and isinstance(result, dict)
                and result.get("code") == "workflow_migration_failed"
                and self._hmb_seedance_execution_mode() != "only"):
            raise RuntimeError(
                "Legacy Shot connections need confirmation. Reconnect the original Prompt/Agent "
                "to their own Shots before rendering. Original inputs and recovery records are preserved."
            )
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

        if param_name == BROKER_SERVER_URL_PARAMETER:
            # Workflow hydration is never permission to replace the user's
            # PC-wide setting. Old serialized per-node values are ignored.
            if initial_setup:
                super().set_parameter_value(param_name, _broker_display_server_url(),
                    initial_setup=True, emit_change=emit_change, skip_before_value_set=True)
                return
            try:
                selected = _broker_config.normalize_broker_base_url(value, allow_empty=True)
            except ValueError as exc:
                raise _BrokerUnavailableError(str(exc)) from exc
            current = _broker_display_server_url()
            if selected != current:
                for node in tuple(_BROKER_SETTING_NODES.values()):
                    active = getattr(node, "_generation_run_active", None)
                    if ((active is not None and active.is_set())
                            or getattr(node, "_generation_refresh_running", False)
                            or getattr(node, "_broker_action_running", False)
                            or getattr(node, "_hmb_draft_finalize_pending", False)):
                        raise ValueError("Wait for active Broker work to finish before changing the shared address.")
            _broker_config.save_broker_base_url(selected)
            self._on_shared_broker_address_changed(selected)
            return
        if param_name == SEEDANCE_RECOVERY_PARAMETER:
            value = _seedance_recovery_value(value)
            if not value["journal_id"]:
                previous = _seedance_recovery_value(self.get_parameter_value(param_name))
                value["journal_id"] = previous["journal_id"] or str(uuid4())
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
        elif param_name == "prompt":
            projected = self._hmb_managed_prompt_projection()
            if projected is not None:
                value = projected
                if (not initial_setup
                        and getattr(self, "parameter_values", {}).get("prompt") == projected):
                    # The shared native Agent output port also echoes its
                    # currently displayed Shot on ordinary editor changes.
                    # An authenticated managed receiver already has its own
                    # exact UUID result; do not publish the same full native
                    # parameter again to every connected Generator. Hydration
                    # and unmanaged/Only inputs keep the native setter path.
                    return

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
        elif param_name == "draft_action" and initial_setup:
            # Native cold replay can restore Draft before its 480p resolution
            # and Only selection. A constructor's Off-only visible menu must
            # not coerce a known saved action to Off before callbacks can run.
            if not isinstance(value, str) or value not in DRAFT_ACTION_CHOICES:
                raise ValueError("Unsupported saved Draft action.")
            draft_parameter = self.get_parameter_by_name("draft_action")
            if draft_parameter is not None:
                draft_parameter.ui_options = {**draft_parameter.ui_options,
                    "simple_dropdown": list(DRAFT_ACTION_CHOICES)}
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
                # Native saved workflows restore exact dynamic child names
                # before replaying the parent aggregate and child values.
                # Reuse those children during equal-length hydration so a
                # later saved child write/connection still addresses the same
                # parameter. Explicit edits and count changes retain the
                # existing rebuild behavior.
                saved_children = (
                    list(container.get_child_parameters()) if initial_setup else []
                )
                reuse_saved_children = bool(initial_setup) and len(saved_children) == len(values)
                if not reuse_saved_children:
                    container.clear_list()
                parent_setter = super().set_parameter_value
                self._hmb_list_parent_syncing = True
                try:
                    for index, item in enumerate(values):
                        child = (
                            saved_children[index]
                            if reuse_saved_children
                            else container.append_child_parameter()
                        )
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
        if (param_name in {ONLY_PROJECT_PARAMETER, _my_box_node.CHECKPOINT_PARAMETER}
                and getattr(self, "_hmb_my_box_parameters_ready", False)):
            # Hydration suppresses after_value_set; selection itself remains
            # pure and does not contact/create a personal server workspace.
            self._update_parameter_visibility()
            if param_name == _my_box_node.CHECKPOINT_PARAMETER and _my_box_node.is_selected(self):
                self._hmb_my_box_controller().schedule_local_restore()
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

        if parameter.name == SEEDANCE_PREFLIGHT_PARAMETER:
            current = self.get_parameter_value(SEEDANCE_PREFLIGHT_PARAMETER)
            if not isinstance(value, dict) or value.get("schema") != SEEDANCE_PREFLIGHT_SCHEMA or value.get("version") != 1:
                return current
            action = value.get("action")
            request_id = value.get("request_id")
            if action not in {"inspect", "cancel"} or not isinstance(request_id, str) or re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
                return current
            command = {"schema": SEEDANCE_PREFLIGHT_SCHEMA, "version": 1,
                "action": action, "request_id": request_id}
            if "client_session" in value or "sequence" in value:
                session, sequence = value.get("client_session"), value.get("sequence")
                if not isinstance(session, str) or re.fullmatch(r"[0-9a-f]{32}", session) is None or type(sequence) is not int or not 0 < sequence <= 9007199254740991:
                    return current
                command.update(client_session=session, sequence=sequence)
            return command
        normalized = value
        if parameter.name == SEEDANCE_RECOVERY_PARAMETER:
            normalized = _seedance_recovery_value(value)
        elif parameter.name == BROKER_SERVER_URL_PARAMETER:
            normalized = _broker_config.normalize_broker_base_url(value, allow_empty=True)
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
            self._hmb_pending_generation_command_action = ""
            self._hmb_pending_gallery_origin = ""
            action_id = normalized["action_id"]
            processed_ids = getattr(
                self,
                "_hmb_processed_generation_command_ids",
                set(),
            )
            preview = _seedance_generation_preview_value(
                self._hmb_generation_preview_state
            )
            authoritative_id = self._authoritative_existing_generation_id()
            if (normalized["action"] == "open_gallery" and action_id and action_id not in processed_ids
                    and self._runtime_node_is_live(require_registered=True)):
                self._hmb_pending_generation_command_id = action_id
                self._hmb_pending_generation_command_action = "open_gallery"
                self._hmb_pending_gallery_origin = self._selected_broker_server_url()
            elif (normalized["action"] == "finalize_draft" and action_id and action_id not in processed_ids
                    and self._runtime_node_is_live(require_registered=True)
                    and self._draft_ui_state()["final_available"]
                    and ((self._draft_ui_state().get("job_id") if _my_box_node.is_selected(self)
                          else self._draft_source_record().get("draft_job_id")) == normalized.get("expected_draft_job_id"))):
                self._hmb_pending_generation_command_id = action_id
                self._hmb_pending_generation_command_action = "finalize_draft"
            elif (normalized["action"] == "cancel_draft_final" and action_id and action_id not in processed_ids
                    and self._hmb_draft_finalize_pending
                    and self._active_draft_job_id() == normalized.get("expected_draft_job_id")):
                self._hmb_pending_generation_command_id = action_id
                self._hmb_pending_generation_command_action = "cancel_draft_final"
            elif (
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
                    self._hmb_pending_generation_command_action = "refresh_existing"
        elif parameter.name == SEEDANCE_SHOT_WIDGET_PARAMETER:
            self._hmb_generation_action_only_update = False
            selection_request = value.get("selection_request") if isinstance(value, dict) else None
            current_mode = getattr(self, "_hmb_seedance_mode_widget_fields", None)
            if (not self._hmb_shot_syncing and callable(current_mode)
                    and isinstance(value, dict)
                    and (selection_request is not None or "execution_mode" in value)):
                fields = current_mode()
                raw_shot = value.get("shot") if isinstance(value.get("shot"), dict) else {}
                requested_uuid = self._shot_uuid(raw_shot.get("shot_uuid"))
                valid_request = (
                    isinstance(selection_request, dict)
                    and selection_request.get("schema") == SEEDANCE_MODE_SELECTION_SCHEMA
                    and selection_request.get("version") == 1
                    and type(selection_request.get("expected_revision")) is int
                    and selection_request["expected_revision"] == fields["execution_mode_revision"]
                    and selection_request.get("expected_instance") == fields["execution_mode_instance"]
                    and selection_request.get("mode") == ("shot" if requested_uuid else "only")
                )
                if valid_request and requested_uuid:
                    available = self._hmb_available_seedance_shot_catalog(self._hmb_shot_catalog_snapshot) or {}
                    valid_request = (self._shot_uuid(raw_shot.get("channel_uuid")) == available.get("channel_uuid")
                                     and any(row.get("shot_uuid") == requested_uuid for row in available.get("shots", [])))
                if not valid_request and value.get("request") != {"action": "refresh_existing"}:
                    # Progress/property echoes are not user mode selections.
                    # Return the canonical state without advancing mode intent.
                    self._hmb_generation_action_only_update = True
                    canonical = _seedance_widget_value(
                        self._shot_identity(), self._hmb_available_seedance_shot_catalog(self._hmb_shot_catalog_snapshot),
                        self._generation_preview_for_widget(), getattr(self, "_hmb_remote_prompt_route", None), self._draft_ui_state())
                    canonical.update(fields)
                    return canonical
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
                authoritative_id = self._authoritative_existing_generation_id()
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
                self._generation_preview_for_widget(),
                getattr(self, "_hmb_remote_prompt_route", None),
            )
            if callable(current_mode):
                normalized.update(current_mode())
            if isinstance(selection_request, dict) and not action_only:
                normalized["selection_request"] = dict(selection_request)
        parent = getattr(super(), "before_value_set", None)
        if callable(parent):
            parent_value = parent(parameter, normalized)
            if parent_value is not None:
                normalized = parent_value
        return normalized

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Mirror Standard Seedance media visibility for the selected mode."""
        controller = getattr(self, "_hmb_my_box_controller_instance", None)
        if controller is not None and parameter.name in {ONLY_PROJECT_PARAMETER, BROKER_SERVER_URL_PARAMETER}:
            controller.invalidate()
        if parameter.name == _my_box_node.CHECKPOINT_PARAMETER:
            if _my_box_node.is_selected(self):
                self._hmb_my_box_controller().schedule_local_restore()
            return None
        if parameter.name == SEEDANCE_PREFLIGHT_PARAMETER:
            if not getattr(self, "_hmb_preflight_publishing", False):
                self._hmb_handle_preflight_command(value)
            return None
        authored_draft = self.get_parameter_value("draft_action")
        expected_resolution = "480p" if authored_draft == DRAFT_ACTION_PREVIEW else "1080p"
        if (parameter.name == "resolution" and str(value) != expected_resolution
                and not self._hmb_draft_controls_syncing
                and authored_draft in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}):
            model = str(self.get_parameter_value("model_id") or "")
            if MODEL_ID_ALIASES.get(model, model) == SEEDANCE_2_5_MODEL_ID:
                self.set_parameter_value("draft_action", DRAFT_ACTION_OFF, emit_change=False)
                self.publish_update_to_parameter("draft_action", DRAFT_ACTION_OFF)
        if parameter.name == "draft_action" and not self._hmb_draft_controls_syncing:
            model = str(self.get_parameter_value("model_id") or "")
            if (MODEL_ID_ALIASES.get(model, model) == SEEDANCE_2_5_MODEL_ID and self._draft_mode_supported()
                    and value in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}):
                self._hmb_draft_controls_syncing = True
                try:
                    resolution = "480p" if value == DRAFT_ACTION_PREVIEW else "1080p"
                    self.set_parameter_value("resolution", resolution, emit_change=False)
                    self.publish_update_to_parameter("resolution", resolution)
                finally:
                    self._hmb_draft_controls_syncing = False
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
            "draft_action",
            "resolution",
            "draft_job_id",
            DRAFT_SOURCE_PARAMETER,
            DRAFT_SOURCES_PARAMETER,
            ONLY_PROJECT_PARAMETER,
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
                self._hmb_suspended_shot_identity = None
                self._set_hidden_control_value(
                    SHOT_AUTOCLAIM_ENABLED_PARAMETER,
                    False,
                )
            requested = (
                value.get("shot", {}).get("shot_uuid")
                if isinstance(value, dict) and isinstance(value.get("shot"), dict)
                else ""
            )
            commit_mode = getattr(self, "_hmb_commit_seedance_mode", None)
            if not self._hmb_autoclaim_in_progress and callable(commit_mode):
                commit_mode(self._shot_uuid(requested))
            self._apply_seedance_shot_selection(
                requested,
                fallback_to_available=bool(requested),
            )
            self._reconcile_shared_shot_routing()
            self._update_parameter_visibility()
        elif not self._hmb_shot_syncing and parameter.name == SHOT_SELECTOR_PARAMETER:
            if not self._hmb_autoclaim_in_progress:
                self._hmb_suspended_shot_identity = None
                self._set_hidden_control_value(
                    SHOT_AUTOCLAIM_ENABLED_PARAMETER,
                    False,
                )
            selected = self._hmb_shot_selector_map.get(str(value or ""))
            commit_mode = getattr(self, "_hmb_commit_seedance_mode", None)
            if not self._hmb_autoclaim_in_progress and callable(commit_mode):
                commit_mode(selected.get("shot_uuid", "") if isinstance(selected, dict) else "")
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
        if parameter.name == BROKER_SERVER_URL_PARAMETER:
            self._broker_bridge_instance = None
            for name, reset_value in (
                ("broker_connection_status", "Not checked"),
                ("broker_account", "—"),
            ):
                if self.get_parameter_by_name(name) is not None:
                    self.set_parameter_value(name, reset_value, emit_change=False)
                    publisher = getattr(self, "publish_update_to_parameter", None)
                    if callable(publisher):
                        publisher(name, reset_value)
        if parameter.name == SEEDANCE_REFRESH_COMMAND_PARAMETER:
            action_id = str(
                getattr(self, "_hmb_pending_generation_command_id", "") or ""
            ).strip()
            self._hmb_pending_generation_command_id = ""
            command_action = str(getattr(self, "_hmb_pending_generation_command_action", ""))
            gallery_origin = str(getattr(self, "_hmb_pending_gallery_origin", ""))
            self._hmb_pending_generation_command_action = ""
            self._hmb_pending_gallery_origin = ""
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
                if command_action == "open_gallery":
                    self._schedule_open_review_gallery(gallery_origin)
                elif command_action == "finalize_draft":
                    expected = value.get("expected_draft_job_id") if isinstance(value, dict) else ""
                    self._on_finalize_draft_clicked(None, None, action_id=action_id, expected_draft_job_id=expected)
                elif command_action == "cancel_draft_final":
                    expected = value.get("expected_draft_job_id") if isinstance(value, dict) else ""
                    self._cancel_draft_final(str(expected or ""))
                else:
                    self._schedule_existing_generation_refresh()
        elif parameter.name == SEEDANCE_SHOT_WIDGET_PARAMETER:
            action_requested = self._hmb_pending_generation_action
            self._hmb_pending_generation_action = False
            self._hmb_generation_action_only_update = False
            if action_requested:
                self._schedule_existing_generation_refresh()
        if not self._hmb_shot_syncing and parameter.name in {"draft_action", "resolution", "draft_job_id", DRAFT_SOURCE_PARAMETER,
                               DRAFT_SOURCES_PARAMETER, "model_id", SHOT_SELECTOR_PARAMETER,
                               SHOT_UUID_PARAMETER, SHOT_CHANNEL_UUID_PARAMETER, BROKER_SERVER_URL_PARAMETER,
                               ONLY_PROJECT_PARAMETER}:
            with suppress(Exception):
                self._sync_seedance_shot_widget(emit_change=True)
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

    def _on_shared_broker_address_changed(self, value: str) -> None:
        if self.get_parameter_by_name(BROKER_SERVER_URL_PARAMETER) is None:
            return
        if self.get_parameter_value(BROKER_SERVER_URL_PARAMETER) == value:
            return
        super().set_parameter_value(BROKER_SERVER_URL_PARAMETER, value,
            emit_change=True, skip_before_value_set=True)

    def _selected_broker_server_url(self) -> str:
        # A claimed background web execution is a frozen operation, not a
        # new submission from the live desktop node.
        web_params = getattr(self, "_web_params", None)
        if isinstance(web_params, dict) and web_params.get("_hmb_broker_server_url"):
            return _broker_validated_server_url(web_params["_hmb_broker_server_url"])
        return _broker_validated_server_url()

    def _broker_server_for_task(
        self, task_id: str, *, checkpoint: dict[str, Any] | None = None,
    ) -> str:
        recovery = checkpoint if checkpoint is not None else self._generation_recovery_state()
        if task_id and recovery.get("task_id") == task_id:
            saved_origin = str(recovery.get("broker_server_url") or "")
            if not saved_origin:
                raise _BrokerProtocolError(
                    "The saved Broker task has no trustworthy server origin. No request was sent."
                )
            return _broker_validated_server_url(saved_origin)
        return self._selected_broker_server_url()

    def _create_broker_bridge(
        self, *, server_url: str | None = None,
    ) -> _HMBAIBrokerBridge:
        return _HMBAIBrokerBridge(server_url=server_url)

    def _get_broker_bridge(
        self, *, server_url: str | None = None,
    ) -> _HMBAIBrokerBridge:
        selected_origin = _broker_validated_server_url(server_url) if server_url is not None else self._selected_broker_server_url()
        current = self._broker_bridge_instance
        if current is None or getattr(current, "server_url", selected_origin) != selected_origin:
            self._broker_bridge_instance = self._create_broker_bridge(server_url=selected_origin)
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
        if self._generation_run_active.is_set() or self._generation_refresh_running or self._hmb_draft_finalize_pending:
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

    async def _ensure_broker_connected(
        self, *, server_url: str | None = None,
    ) -> _HMBAIBrokerBridge:
        bridge = self._get_broker_bridge(server_url=server_url)
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
        if getattr(self, "_hmb_parameter_visibility_syncing", False):
            self._hmb_parameter_visibility_pending = True
            return
        self._hmb_parameter_visibility_syncing = True
        try:
            # SDK Options traits can restore their storage-union choices when
            # a dependent task/resolution value is normalized. Reapply the
            # visible choices after those callbacks, without recursive updates.
            for _ in range(3):
                self._hmb_parameter_visibility_pending = False
                self._update_parameter_visibility_impl()
                if not self._hmb_parameter_visibility_pending:
                    break
        finally:
            self._hmb_parameter_visibility_syncing = False

    def _update_parameter_visibility_impl(self) -> None:
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
        draft_state = self._draft_ui_state()
        draft_parameter = self.get_parameter_by_name("draft_action")
        if draft_parameter is not None:
            choices = [DRAFT_ACTION_OFF]
            if draft_state["preview_available"] or (draft_state["busy"] and draft_state["action"] == DRAFT_ACTION_PREVIEW):
                choices.append(DRAFT_ACTION_PREVIEW)
            if draft_state["final_available"] or (draft_state["busy"] and draft_state["action"] == DRAFT_ACTION_FINAL):
                choices.append(DRAFT_ACTION_FINAL)
            draft_parameter.ui_options = {**draft_parameter.ui_options, "simple_dropdown": choices}
        if draft_state["visible"]:
            self.show_parameter_by_name("draft_action")
            if draft_state["job_id"]:
                self.show_parameter_by_name("draft_job_id")
            else:
                self.hide_parameter_by_name("draft_job_id")
        else:
            self.hide_parameter_by_name(["draft_action", "draft_job_id"])
        draft_output_fixed = (
            seedance_25_active
            and self._draft_mode_supported()
            and (
                draft_state["action"] in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}
                or self._hmb_draft_finalize_pending
                or isinstance(self._hmb_draft_final_context, dict)
            )
        )
        manual_output_controls = seedance_25_active and not draft_output_fixed
        if self._draft_only_mode():
            self.show_parameter_by_name(ONLY_PROJECT_PARAMETER)
        else:
            self.hide_parameter_by_name(ONLY_PROJECT_PARAMETER)
        for name in (_my_box_node.TITLE_PARAMETER,):
            if self.get_parameter_by_name(name) is not None:
                (self.show_parameter_by_name if _my_box_node.is_selected(self) else self.hide_parameter_by_name)(name)
        legacy_source = self.get_parameter_by_name(_my_box_node.SOURCE_PARAMETER)
        if legacy_source is not None and (not legacy_source.hide or not legacy_source.hide_property):
            legacy_source.update_ui_options({"hide": True, "hide_property": True})
        if manual_output_controls:
            self.show_parameter_by_name(["output_format", "return_last_frame"])
        else:
            self.hide_parameter_by_name(["output_format", "return_last_frame"])
        if model_id == SEEDANCE_2_0_MODEL_ID:
            self.show_parameter_by_name("priority")
        else:
            self.hide_parameter_by_name("priority")
        if manual_output_controls and bool(
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

        # Editing, Only-mode First/Last Frame and Extension require adaptive
        # ratio. Shot executes Reference to Video, so its authored frame/extend
        # ratio remains independent until the node returns to Only mode.
        ratio_choices = (
            ("adaptive",)
            if model_id == SEEDANCE_2_5_MODEL_ID
            and (
                current_task == TASK_VIDEO_EDITING
                or (
                    current_task in {TASK_FIRST_LAST_FRAME, TASK_VIDEO_EXTENSION}
                    and not self._hmb_shot_channel_subscription().get("enabled")
                )
            )
            else RATIOS
        )
        ratio_parameter = self.get_parameter_by_name("ratio")
        if ratio_parameter is not None:
            visible_ratio_choices = list(ratio_choices)
            if (
                ratio_parameter.ui_options.get("simple_dropdown")
                != visible_ratio_choices
            ):
                ratio_parameter.ui_options = {
                    **ratio_parameter.ui_options,
                    "simple_dropdown": visible_ratio_choices,
                }
            if self.get_parameter_value("ratio") not in ratio_choices:
                self.set_parameter_value("ratio", "adaptive")
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
        if not isinstance(value, dict) or (set(value) != required and not (
                source_kind == "image_asset" and set(value) == required | {"project_id"})):
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
        project_fields = {}
        if source_kind == "image_asset" and "project_id" in value:
            project_id = value["project_id"]
            if not isinstance(project_id, str) or len(project_id) > 256:
                raise RuntimeError("Seedance ImageAsset project identity is invalid.")
            project_fields["project_id"] = project_id
            metadata_document.update(project_fields)
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
            **project_fields,
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

    @staticmethod
    def _finish_look_source_subscription(
        source_node: Any, expected_subscription: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Resolve a manager's exact Shot without selecting its visible editor."""

        try:
            manager = getattr(source_node, "_hmb_shot_manager_enabled", None)
            manager_flag = manager() if callable(manager) else False
            if type(manager_flag) is not bool:
                raise ValueError("Finish Look manager state is unavailable")
            if manager_flag is False:
                return HMBSeedanceGeneration._direct_source_subscription(source_node, "finish_look")
            getter = getattr(source_node, "_hmb_finish_look_shot_subscriptions", None)
            if not callable(getter):
                getter = getattr(source_node, "_hmb_shot_manager_subscriptions", None)
            declared = getter() if callable(getter) else None
            if not isinstance(declared, (list, tuple)) or not 1 <= len(declared) <= 5:
                raise ValueError("Invalid Finish Look manager catalog")
            fields = ("channel_uuid", "shot_uuid", "shot_number", "shot_name")
            identities, numbers, channels = set(), set(), set()
            for row in declared:
                if (not isinstance(row, dict)
                        or row.get("schema") != "hmb-shot-channel-subscription"
                        or type(row.get("version")) is not int or row["version"] != 1
                        or row.get("participant_kind") != "finish_look" or row.get("enabled") is not True
                        or type(row.get("shot_number")) is not int or not 1 <= row["shot_number"] <= 5
                        or any(not isinstance(row.get(key), str) or not row[key].strip()
                               or row[key] != row[key].strip() for key in ("channel_uuid", "shot_uuid", "shot_name"))):
                    raise ValueError("Invalid Finish Look manager subscription")
                key = (row["channel_uuid"], row["shot_uuid"])
                if key in identities or row["shot_number"] in numbers:
                    raise ValueError("Ambiguous Finish Look manager subscription")
                identities.add(key)
                numbers.add(row["shot_number"])
                channels.add(row["channel_uuid"])
            exact = [row for row in declared
                     if all(row.get(key) == expected_subscription.get(key) for key in fields)]
            if len(channels) != 1 or len(exact) != 1:
                raise ValueError("Finish Look manager has no exact selected Shot")
            return dict(exact[0])
        except Exception as exc:
            raise RuntimeError("Seedance Finish Look source does not match the selected Shot identity.") from exc

    @staticmethod
    def _validate_finish_look_shot_snapshot(
        value: Any,
        *,
        expected_subscription: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Verify the sidecar, then compile only its canonical Character Beauty."""

        if isinstance(value, dict) and value.get("version") == 1:
            # The retired snapshot carried only a state hash, not the state.
            # Its prose can contain removed film instructions and must never be
            # reused, guessed from text, or stripped out of the user's prompt.
            raise RuntimeError(
                "Seedance Finish Look snapshot requires a Character Beauty refresh. "
                "Refresh or reopen the Finish Look node so it republishes its saved "
                "settings in the current format. Retired filter instructions were not applied."
            )

        required = {
            "schema",
            "version",
            "channel_uuid",
            "shot_uuid",
            "shot_number",
            "shot_name",
            "generation",
            "finish_look_sha256",
            "state_sha256",
            "finish_look_out",
            "finish_look_state",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RuntimeError("Seedance Finish Look snapshot shape is invalid.")
        if (
            value.get("schema") != FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA
            or type(value.get("version")) is not int
            or value.get("version") != FINISH_LOOK_SHOT_SNAPSHOT_VERSION
        ):
            raise RuntimeError("Seedance Finish Look snapshot version is invalid.")
        if (
            str(value.get("channel_uuid") or "")
            != str(expected_subscription.get("channel_uuid") or "")
            or str(value.get("shot_uuid") or "")
            != str(expected_subscription.get("shot_uuid") or "")
            or value.get("shot_number") != expected_subscription.get("shot_number")
            or value.get("shot_name") != expected_subscription.get("shot_name")
        ):
            raise RuntimeError("Seedance Finish Look snapshot does not match the selected Shot.")
        generation = value.get("generation")
        instruction = value.get("finish_look_out")
        finish_sha256 = str(value.get("finish_look_sha256") or "").casefold()
        state_sha256 = str(value.get("state_sha256") or "").casefold()
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or not 1 <= generation <= (1 << 53) - 1
            or not isinstance(instruction, str)
            or re.fullmatch(r"[0-9a-f]{64}", finish_sha256) is None
            or re.fullmatch(r"[0-9a-f]{64}", state_sha256) is None
            or not hmac.compare_digest(
                finish_sha256,
                hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
            )
        ):
            raise RuntimeError("Seedance Finish Look snapshot integrity is invalid.")
        state = value.get("finish_look_state")
        try:
            encoded_state = json.dumps(
                state,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("Seedance Finish Look state integrity is invalid.") from exc
        if not hmac.compare_digest(state_sha256, hashlib.sha256(encoded_state).hexdigest()):
            raise RuntimeError("Seedance Finish Look state integrity is invalid.")
        if (
            not isinstance(state, dict)
            or set(state) != {"schema_version", "beauty"}
            or type(state.get("schema_version")) is not int
            or state["schema_version"] != 2
        ):
            raise RuntimeError(
                "Seedance Finish Look state requires a Character Beauty refresh. "
                "Republish the Finish Look node before rendering."
            )
        try:
            from HMBFinishLookLibrary import (
                compile_finish_look_prompt,
                validate_finish_look_state,
            )

            canonical_state = validate_finish_look_state(state)
            # Even correctly hashed saved prose is not execution authority.
            # Recompile with the active Beauty-only implementation so an older
            # full-frame film block cannot return after workflow hydration.
            instruction = compile_finish_look_prompt(canonical_state)
        except Exception as exc:
            raise RuntimeError("Seedance Finish Look Character Beauty state is invalid.") from exc
        return {
            **value,
            "finish_look_out": instruction,
            "finish_look_state": canonical_state,
            "finish_look_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
            "state_sha256": hashlib.sha256(
                json.dumps(
                    canonical_state,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest(),
        }

    @staticmethod
    def _compose_finish_look_prompt(base_prompt: Any, finish_look: Any) -> str:
        """Append verified Character Beauty without rewriting Agent/user text."""

        base = str(base_prompt or "")
        finish = str(finish_look or "")
        if not finish:
            return base
        return (
            "HMB RESOLVED SHOT INSTRUCTION\n"
            f"{base}\n\n"
            "HMB FINISH LOOK — APPLY AFTER THE RESOLVED GLOBAL LOOK (VERBATIM)\n"
            f"{finish}\n\n"
            "HMB FINAL RENDER RULES\n"
            "Apply the verbatim Finish Look block after the resolved Global Look and before "
            "final rendering. It may affect only Character Beauty. "
            "Apply Character Beauty exclusively to character-owned surfaces, including the "
            "face, body, hair, costume, and character materials; never apply it to the "
            "background, environment, sky, ground, set dressing, independent props, FX, or "
            "the camera image as a whole. It must not alter "
            "character identity, design, geometry, camera, framing, animation, timing, FX "
            "placement, environment content, or the Global Look's lighting direction and "
            "composition. Preserve the resolved character's facial structure, feature "
            "placement, proportions, silhouette, material boundaries, markings, and "
            "asymmetries through authored expressions, deformation, perspective, and "
            "occlusion. Apply the user's stated brightness, saturation, glow, diffusion, "
            "and other Beauty values inside that scope while retaining those design "
            "features. Character-surface soft focus affects optical treatment only; "
            "continue the resolved subject and camera motion and source timing."
        )

    def _hmb_agent_generation_settings(self) -> dict[str, Any]:
        """Read this Shot's execution settings without changing graph or controls.

        Mirror model-control normalization and the Shot Reference-to-Video
        execution copy. Calling ``_get_parameters`` here would run setters and
        could recursively wake the upstream Agent; this optional context must
        remain a read-only observation of the downstream request.
        """

        subscription = self._hmb_shot_channel_subscription()
        if not subscription.get("enabled"):
            return {}
        raw_model = str(
            self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0
        ).strip()
        model_id = MODEL_ID_ALIASES.get(raw_model, raw_model)
        if model_id not in MODEL_RESOLUTIONS:
            return {}
        resolution = str(self.get_parameter_value("resolution") or "")
        previous_model = str(getattr(self, "_hmb_model_switch_previous_id", "") or "")
        if (
            raw_model in RETIRED_SEEDANCE_MODEL_VALUES
            or bool(getattr(self, "_hmb_retired_model_migration_pending", False))
            or resolution not in MODEL_RESOLUTIONS[model_id]
            or (
                previous_model
                and previous_model != model_id
                and resolution == MODEL_DEFAULT_RESOLUTIONS.get(previous_model)
            )
        ):
            resolution = MODEL_DEFAULT_RESOLUTIONS[model_id]
        authored_task = str(self.get_parameter_value(TASK_PARAMETER) or TASK_REFERENCE_TO_VIDEO)
        if authored_task not in MODEL_TASK_CHOICES[model_id]:
            authored_task = TASK_REFERENCE_TO_VIDEO
        duration_choices = MODEL_DURATION_CHOICES[model_id]
        if model_id == SEEDANCE_2_5_MODEL_ID:
            if authored_task == TASK_VIDEO_EDITING:
                duration_choices = (-1,)
            elif authored_task == TASK_VIDEO_EXTENSION:
                duration_choices = DURATION_STORAGE_CHOICES
        duration = self.get_parameter_value("duration")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration not in duration_choices
        ):
            duration = -1 if authored_task == TASK_VIDEO_EDITING else 5
        if duration not in MODEL_DURATION_CHOICES[model_id]:
            duration = 5
        ratio = str(self.get_parameter_value("ratio") or "adaptive")
        if ratio not in RATIOS or (
            model_id == SEEDANCE_2_5_MODEL_ID and authored_task == TASK_VIDEO_EDITING
        ):
            ratio = "adaptive"
        output_format = str(
            self.get_parameter_value("output_format") or DEFAULT_OUTPUT_FORMAT
        ).strip().lower()
        if output_format not in OUTPUT_FORMAT_CHOICES or model_id != SEEDANCE_2_5_MODEL_ID:
            output_format = DEFAULT_OUTPUT_FORMAT
        draft_action = self.get_parameter_value("draft_action") or DRAFT_ACTION_OFF
        if draft_action not in DRAFT_ACTION_CHOICES or model_id != SEEDANCE_2_5_MODEL_ID:
            draft_action = DRAFT_ACTION_OFF
        return {
            "model_id": model_id,
            "task": TASK_REFERENCE_TO_VIDEO,
            "duration_seconds": duration if duration > 0 else None,
            "duration_mode": "explicit" if duration > 0 else "provider_smart",
            "aspect_ratio": ratio,
            "resolution": resolution,
            "generate_audio": bool(self.get_parameter_value("generate_audio")),
            "output_format": output_format,
            "draft_action": draft_action,
            "return_last_frame": bool(self.get_parameter_value("return_last_frame"))
            if model_id == SEEDANCE_2_5_MODEL_ID else False,
        }

    def _resolve_exact_shot_generation_inputs(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        # A newly added or deserialized Seedance node may still have a blank
        # durable quartet. Reconcile the same-flow catalog before deciding
        # whether remote execution can proceed; a missing catalog fails closed.
        mode_getter = getattr(self, "_hmb_seedance_execution_mode", None)
        if not callable(mode_getter) or mode_getter() != "only":
            self._reconcile_shared_shot_routing(strict=True)
        if callable(mode_getter) and mode_getter() == "waiting":
            raise ValueError("The selected Shot is waiting for its original library binding. Restore that Shot, or explicitly select Only.")
        only_guard = getattr(self, "_assert_only_mode_inputs", None)
        if callable(only_guard):
            only_guard()
        selection = self._capture_imageasset_project_selection()
        params = {**params, **selection["project"], "_hmb_imageasset_project_selection": selection}
        subscription = self._hmb_shot_channel_subscription()
        # Capture the actual resolved execution branch, not the pre-reconcile
        # selector or the ImageAsset/manual project's provenance schema.
        params["_hmb_generation_mode"] = "shot" if subscription["enabled"] else "only"
        if not subscription["enabled"]:
            resolved = dict(params)
            resolved["prompt"] = str(params.get("prompt") or "")
            # Only has no exact Shot finishing source. Discard a previous
            # bound-Shot transient sidecar without touching authored text.
            resolved["_hmb_finish_look_out"] = ""
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
        draft_source_bindings: dict[str, str] = {}
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
            exact_snapshot_api = getattr(source_node, "_hmb_shot_routing_snapshot_for", None)
            if callable(exact_snapshot_api):
                raw_snapshot = exact_snapshot_api(
                    channel_uuid=subscription["channel_uuid"],
                    shot_uuid=subscription["shot_uuid"],
                )
            else:
                try:
                    raw_snapshot = snapshot_api(subscription["channel_uuid"])
                except TypeError:
                    raw_snapshot = snapshot_api()
            source_snapshot = self._validate_direct_media_snapshot(
                raw_snapshot,
                source_kind=source_kind,
                expected_channel_uuid=subscription["channel_uuid"],
            )
            draft_source_bindings[source_kind] = source_snapshot["publisher_instance_uuid"]
            if source_kind == "image_asset" and "project_id" in source_snapshot:
                snapshot_project = resolve_project(source_snapshot, default_legacy=False)
                if snapshot_project["project_id"] != params["project_id"]:
                    raise RuntimeError("The selected ImageAsset project changed during input preparation.")
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

        finish_look_out = ""
        finish_node = self._exact_incoming_source(
            SHOT_FINISH_LOOK_INPUT_PARAMETER,
            "SHOT_FINISH_LOOK_OUT",
            required=False,
        )
        if finish_node is not None:
            finish_subscription = self._finish_look_source_subscription(finish_node, subscription)
            if (
                finish_subscription.get("channel_uuid") != subscription["channel_uuid"]
                or finish_subscription.get("shot_uuid") != subscription["shot_uuid"]
                or finish_subscription.get("shot_number") != subscription["shot_number"]
                or finish_subscription.get("shot_name") != subscription["shot_name"]
            ):
                raise RuntimeError(
                    "Seedance Finish Look source does not match the selected Shot identity."
                )
            manager = getattr(finish_node, "_hmb_shot_manager_enabled", None)
            if callable(manager) and manager() is True:
                snapshot_api = getattr(finish_node, "_hmb_finish_look_shot_snapshot_for", None)
                if not callable(snapshot_api):
                    raise RuntimeError("Seedance Finish Look manager does not expose its per-Shot snapshot API.")
                # The shared physical output may display another open row.
                # Its value is not authority for this Generator's execution.
                finish_snapshot = snapshot_api(channel_uuid=subscription["channel_uuid"],
                                               shot_uuid=subscription["shot_uuid"])
            else:
                snapshot_api = getattr(finish_node, "_hmb_finish_look_shot_snapshot", None)
                if not callable(snapshot_api):
                    raise RuntimeError("Seedance Finish Look source does not expose its atomic snapshot API.")
                routed_snapshot = self.get_parameter_value(SHOT_FINISH_LOOK_INPUT_PARAMETER)
                try:
                    finish_snapshot = snapshot_api(routed_snapshot if routed_snapshot else None)
                except TypeError:
                    finish_snapshot = snapshot_api()
            finish_snapshot = self._validate_finish_look_shot_snapshot(
                finish_snapshot,
                expected_subscription=subscription,
            )
            finish_look_out = finish_snapshot["finish_look_out"]

        resolved = dict(params)
        resolved["prompt"] = str(params.get("prompt") or "")
        # Keep the Agent prompt untouched through normal validation. The exact
        # Finish Look sidecar is composed only at Broker payload construction,
        # after the upstream Agent has published its final text.
        resolved["_hmb_finish_look_out"] = finish_look_out
        resolved[TASK_PARAMETER] = TASK_REFERENCE_TO_VIDEO
        reference_duration_choices = MODEL_DURATION_CHOICES.get(model_id, ())
        if (
            "duration" in resolved
            and resolved.get("duration") not in reference_duration_choices
        ):
            # Only may author a task-specific smart duration (-1) for Video
            # Editing or Extension. Shot always executes Reference to Video,
            # whose 2.5 duration is explicit. Normalize only this execution
            # copy; returning to Only restores the untouched authored controls.
            resolved["duration"] = 5
        resolved["first_frame"] = None
        resolved["last_frame"] = None
        resolved["reference_images"] = list(images)
        resolved["video_references"] = list(videos)
        resolved["video_reference_slots"] = []
        resolved["reference_audio"] = []
        resolved["input_mode"] = INPUT_MODE_MULTIMODAL_REFERENCES
        if params.get("draft_action") == DRAFT_ACTION_PREVIEW:
            resolved["_hmb_draft_source_bindings"] = draft_source_bindings
        return resolved

    def _project_incoming_connections(self, node: Any) -> list[Any]:
        """Read registered edges, including hidden/list-child inputs, without reconciliation."""
        from griptape_nodes.retained_mode.events.connection_events import (
            ListConnectionsForNodeRequest, ListConnectionsForNodeResultSuccess,
        )
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(
            node_name=str(node.name), include_internal=True, broadcast_result=False,
            failure_log_level=logging.DEBUG,
        ))
        if not isinstance(result, ListConnectionsForNodeResultSuccess):
            raise ValueError("ImageAsset project connections are unavailable. No render was submitted.")
        incoming = getattr(result, "incoming_connections", None)
        if not isinstance(incoming, (list, tuple)) or len(incoming) > 256:
            raise ValueError("ImageAsset project connection data is invalid.")
        return list(incoming)

    def _capture_imageasset_project_selection(self) -> dict[str, Any]:
        """Resolve only exact registered ImageAsset paths in this Generator's flow.

        Neither Agent execution caches nor Prompt text/media are project authority.
        The private snapshot pins node instances and edges for this operation only.
        """
        if isinstance(self, _HMBWebRerenderExecution):
            return self._web_owner._capture_imageasset_project_selection()
        from griptape_nodes.node_library.library_registry import LibraryRegistry

        manager = GriptapeNodes.NodeManager()
        owner_name = str(self.name)
        if manager.get_node_by_name(owner_name) is not self or getattr(self, "_hmb_node_deleted", False):
            raise ValueError("Generator project source is not registered.")
        flow_name = manager.get_node_parent_flow_by_name(owner_name)
        if not isinstance(flow_name, str) or not flow_name:
            raise ValueError("Generator project flow is unavailable.")
        classes: dict[str, type] = {}
        visited: set[int] = set()
        active: set[int] = set()
        sources: dict[int, dict[str, Any]] = {}
        edges: set[tuple[int, str, int, str]] = set()
        supported = {"HMBImageAssetLibrary", "HMBPromptLibrary", "HMBAgentLibrary"}
        intent_getter = getattr(self, "_hmb_seedance_mode_intent", None)
        mode_intent = intent_getter() if callable(intent_getter) else {}
        independent = mode_intent.get("mode") == "only"
        mode_guard = ({"mode_guard": {key: mode_intent.get(key) for key in
                       ("mode", "channel_uuid", "shot_uuid")}}
                      if mode_intent.get("mode") in {"only", "shot"} else {})

        def registered(node: Any) -> None:
            name = str(getattr(node, "name", "") or "")
            if (not name or manager.get_node_by_name(name) is not node
                    or getattr(node, "_hmb_node_deleted", False)
                    or manager.get_node_parent_flow_by_name(name) != flow_name):
                raise ValueError("ImageAsset project source was removed, replaced, or belongs to another flow.")

        def kind(node: Any) -> str:
            registered(node)
            metadata = getattr(node, "metadata", None)
            if not isinstance(metadata, dict) or metadata.get("library") != "HMB_GP_Production":
                return ""
            name = metadata.get("node_type")
            if name not in supported:
                return ""
            if name not in classes:
                classes[name] = LibraryRegistry.get_library("HMB_GP_Production").get_node_class(name)
            if not isinstance(classes[name], type) or type(node) is not classes[name]:
                raise ValueError("ImageAsset project source class is not the registered library class.")
            return str(name)

        def walk(node: Any, node_kind: str, depth: int = 0) -> None:
            if depth > 3 or id(node) in active or len(visited) > 32:
                raise ValueError("ImageAsset project source topology is cyclic or too large.")
            registered(node)
            if id(node) in visited:
                return
            active.add(id(node))
            if node_kind == "HMBImageAssetLibrary":
                getter = getattr(node, "_hmb_project_identity", None)
                if not callable(getter):
                    raise ValueError("Selected ImageAsset project identity is unavailable.")
                project = resolve_project(getter(), default_legacy=False)
                sources[id(node)] = {key: project[key] for key in ("project_id", "project_name")}
            else:
                for edge in self._project_incoming_connections(node):
                    # SDK IncomingConnection omits target_node_name; the typed
                    # node-scoped response supplies that identity.
                    if str(getattr(edge, "target_node_name", node.name) or "") != str(node.name):
                        raise ValueError("ImageAsset project edge target does not match its registered node.")
                    target = str(getattr(edge, "target_parameter_name", "") or "")
                    source_port = str(getattr(edge, "source_parameter_name", "") or "")
                    if independent and node_kind == "generator" and target in {
                        SHOT_ASSET_INPUT_PARAMETER, "SHOT_PROMPT_IN", "SHOT_IMAGE_IN", "SHOT_VIDEO_IN", "prompt"
                    }:
                        # Only's project comes from its explicit selector or a
                        # manually connected IMAGE_OUT, never a managed Shot chain.
                        continue
                    allowed: dict[str, set[str]] = {}
                    strict = False
                    if node_kind == "generator":
                        if target == SHOT_ASSET_INPUT_PARAMETER:
                            allowed = {"HMBImageAssetLibrary": {"SHOT_ASSET_OUT"}}; strict = True
                        elif self._connection_targets_parameter_or_list_child("reference_images", target):
                            allowed = {"HMBImageAssetLibrary": {"IMAGE_OUT"}}
                        elif target in {"prompt", "SHOT_PROMPT_IN"}:
                            allowed = {"HMBAgentLibrary": {"output"}, "HMBPromptLibrary": {"PROMPT_OUT"}}
                            strict = target == "SHOT_PROMPT_IN"
                        elif target == "SHOT_IMAGE_IN":
                            allowed = {"HMBPromptLibrary": {"SHOT_IMAGE_OUT"}}; strict = True
                    elif node_kind == "HMBAgentLibrary" and target == "SHOT_PROMPT_IN":
                        allowed = {"HMBPromptLibrary": {"PROMPT_OUT"}}; strict = True
                    elif node_kind == "HMBPromptLibrary":
                        if target == "SHOT_ASSET_IN":
                            allowed = {"HMBImageAssetLibrary": {"SHOT_ASSET_OUT"}}; strict = True
                        elif target == "IMAGE_ASSET_IN":
                            allowed = {"HMBImageAssetLibrary": {"IMAGE_ASSET_OUT", "IMAGE_OUT"}}
                    if not allowed:
                        continue
                    source_name = str(getattr(edge, "source_node_name", "") or "")
                    source = manager.get_node_by_name(source_name) if source_name else None
                    if source is None:
                        raise ValueError("ImageAsset project edge source is unavailable.")
                    source_kind = kind(source)
                    if source_kind not in allowed:
                        if strict or source_kind:
                            raise ValueError("ImageAsset project route uses an unsupported source.")
                        continue  # Ordinary text/media cannot assert a selected project.
                    if source_port not in allowed[source_kind]:
                        raise ValueError("ImageAsset project route uses the wrong source port.")
                    edges.add((id(source), source_port, id(node), target))
                    walk(source, source_kind, depth + 1)
            active.remove(id(node))
            visited.add(id(node))

        walk(self, "generator")
        explicit_project = self._selected_only_project() if self._draft_only_mode() else {}
        if not sources:
            if explicit_project:
                return {"schema": ONLY_PROJECT_SELECTION_SCHEMA, "project": explicit_project,
                        "flow": flow_name, "owner": id(self), "sources": [], "edges": [],
                        "selection_source": "only_explicit", **mode_guard}
            if self._draft_only_mode():
                raise _ProjectSelectionRequired(
                    "Select Project (Only), or connect an ImageAsset library project, before rendering.")
            raise _ProjectSelectionRequired("Select and connect an ImageAsset library project before rendering.")
        identities = list(sources.values())
        if any(identity != identities[0] for identity in identities[1:]):
            raise ValueError("Connected ImageAsset sources belong to different projects.")
        if explicit_project and explicit_project != identities[0]:
            raise ValueError("The Only project selection does not match the connected ImageAsset project.")
        return {"schema": PROJECT_SELECTION_SCHEMA, "project": dict(identities[0]),
                "flow": flow_name, "owner": id(self),
                "sources": sorted(sources), "edges": sorted(edges), **mode_guard}

    def _selected_only_project(self) -> dict[str, str]:
        value = self.get_parameter_value(ONLY_PROJECT_PARAMETER)
        if value in (None, "", ONLY_PROJECT_UNSELECTED):
            return {}
        if not isinstance(value, str):
            raise ValueError("Select a valid Project (Only) before rendering.")
        project = resolve_project(value, default_legacy=False)
        if project["project_id"] not in {"superwings12", "katuri8"}:
            raise ValueError("This project is not active. Select Super Wings 12 or Katuri 8 in Project (Only).")
        return {key: project[key] for key in ("project_id", "project_name")}

    def _hmb_generation_project(self) -> dict[str, str]:
        return dict(self._capture_imageasset_project_selection()["project"])

    def _assert_imageasset_project_selection(self, selection: dict[str, Any]) -> None:
        try:
            current = self._capture_imageasset_project_selection()
        except Exception as exc:
            raise _ProjectSelectionChanged("The selected ImageAsset project is unavailable. No render was submitted.") from exc
        if selection != current:
            raise _ProjectSelectionChanged("The selected ImageAsset project or connection changed. Run again with the selected project.")

    def _assert_operation_project_selection(self) -> None:
        guard = getattr(self, "_hmb_project_selection_guard", None)
        if not isinstance(guard, dict):
            return  # Final, Resume and authenticated Web use original task provenance.
        if threading.get_ident() == guard["thread"]:
            self._assert_imageasset_project_selection(guard["selection"])
            return
        async def validate() -> None:
            self._assert_imageasset_project_selection(guard["selection"])
        loop = guard["loop"]
        if not loop.is_running():
            raise _ProjectSelectionChanged("Project selection validation is unavailable. No render was submitted.")
        pending = asyncio.run_coroutine_threadsafe(validate(), loop)
        try:
            pending.result(timeout=10.0)
        except TimeoutError as exc:
            raise _ProjectSelectionChanged("Project selection validation timed out. No render was submitted.") from exc
        finally:
            if not pending.done():
                pending.cancel()

    @staticmethod
    def _hmb_preflight_issue(code: str, message: str, severity: str = "error") -> dict[str, str]:
        return {"code": code, "message": message[:300], "severity": severity}

    @staticmethod
    def _hmb_preflight_kind(node: Any) -> str:
        """Only actual registered HMB classes can describe a readiness route."""
        metadata = getattr(node, "metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        kind = metadata.get("node_type") if isinstance(metadata, dict) else None
        if metadata.get("library") != "HMB_GP_Production" or kind not in {
            "HMBImageAssetLibrary", "HMBVideoPickerLibrary", "HMBPromptLibrary",
            "HMBAgentLibrary", "HMBFinishLookLibrary", "HMBSeedanceGeneration",
        } or getattr(node, "_hmb_node_deleted", False):
            return ""
        from griptape_nodes.node_library.library_registry import LibraryRegistry
        return kind if type(node) is LibraryRegistry.get_library("HMB_GP_Production").get_node_class(kind) else ""

    @staticmethod
    def _hmb_preflight_declares(node: Any, kind: str, expected: dict[str, Any]) -> bool:
        hook = {"agent": "_hmb_agent_shot_subscriptions", "prompt": "_hmb_prompt_shot_subscriptions",
            "finish_look": "_hmb_finish_look_shot_subscriptions"}[kind]
        manager = getattr(node, "_hmb_shot_manager_enabled", None)
        manager_flag = manager() if callable(manager) else False
        if type(manager_flag) is not bool:
            return False
        rows = getattr(node, hook)() if manager_flag else [node._hmb_shot_channel_subscription()]
        if not isinstance(rows, (list, tuple)) or len(rows) > SHOT_ROUTING_MAX_SHOTS:
            return False
        fields = ("channel_uuid", "shot_uuid", "shot_number", "shot_name")
        return sum(isinstance(row, dict) and row.get("enabled") is True
            and row.get("participant_kind") == kind and all(row.get(key) == expected[key] for key in fields)
            for row in rows) == 1

    def _hmb_preflight_parameters(self, *, bound: bool) -> dict[str, Any]:
        """Read execution copies; deliberately never call mutating _get_parameters."""
        def read(name: str, default: Any = None) -> Any:
            value = self.get_parameter_value(name)
            return default if value is None else value
        model = str(read("model_id", MODEL_NAME_SEEDANCE_2_5)).strip()
        model = MODEL_ID_ALIASES.get(model, model)
        task = TASK_REFERENCE_TO_VIDEO if bound else str(read(TASK_PARAMETER, TASK_REFERENCE_TO_VIDEO))
        if not bound and model != SEEDANCE_2_5_MODEL_ID:
            task = INPUT_MODE_TASKS.get(str(read("input_mode", INPUT_MODE_MULTIMODAL_REFERENCES)), task)
        videos = self._get_list_input(VIDEO_REFERENCES_PARAMETER)
        if not videos and not self._list_input_is_authoritative(VIDEO_REFERENCES_PARAMETER):
            videos = [read(f"reference_video_{n}") for n in range(1, LEGACY_VIDEO_REFERENCE_SLOTS + 1)
                if self._has_reference_value(read(f"reference_video_{n}"))]
        params = {name: read(name, default) for name, default in {
            "duration": 4, "resolution": MODEL_DEFAULT_RESOLUTIONS.get(model, "720p"),
            "ratio": "adaptive", "poll_interval_seconds": 30, "generation_timeout_seconds": 3600,
            "execution_expires_after": 172800, "priority": 0, "return_last_frame": False,
            "first_frame": None, "last_frame": None, "tos_url_validity_seconds": 172800,
            "local_video_upload_service": LOCAL_VIDEO_UPLOAD_GRIPTAPE,
            "tos_region": DEFAULT_TOS_REGION, "tos_endpoint": DEFAULT_TOS_ENDPOINT,
            "resume_generation_id": "", "draft_action": DRAFT_ACTION_OFF, "draft_job_id": "",
        }.items()}
        params.update(model_id=model, task=task, prompt=str(read("prompt", "")),
            output_format=str(read("output_format", NEW_NODE_OUTPUT_FORMAT if model == SEEDANCE_2_5_MODEL_ID else DEFAULT_OUTPUT_FORMAT)).lower(),
            reference_images=self._get_list_input("reference_images"), video_references=videos,
            reference_audio=self._get_list_input("reference_audio"), _hmb_draft_supported=True)
        if model != SEEDANCE_2_5_MODEL_ID:
            params.update(draft_action=DRAFT_ACTION_OFF, priority=params["priority"] if model == SEEDANCE_2_0_MODEL_ID else 0)
        if params["draft_action"] in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}:
            params.update(resolution="480p" if params["draft_action"] == DRAFT_ACTION_PREVIEW else "1080p", return_last_frame=False)
            if not params["resume_generation_id"]:
                params["output_format"] = "mov"
            raw_source = read(DRAFT_SOURCE_PARAMETER, {})
            if not params["draft_job_id"] and isinstance(raw_source, dict):
                params["draft_job_id"] = raw_source.get("draft_job_id", "")
        if task == TASK_TEXT_ONLY:
            params.update(first_frame=None, last_frame=None, reference_images=[], video_references=[], reference_audio=[])
        elif task == TASK_FIRST_LAST_FRAME:
            params.update(reference_images=[], video_references=[], reference_audio=[])
        else:
            params.update(first_frame=None, last_frame=None)
        return params

    def _hmb_preflight_row(self, expected: dict[str, Any], *, nodes: dict[str, Any], source: Any = None,
            source_snapshot: Any = None, source_issue: str = "") -> dict[str, Any]:
        bound = bool(expected.get("shot_uuid"))
        row = {"channel_uuid": expected.get("channel_uuid", ""), "shot_uuid": expected.get("shot_uuid", ""),
            "number": expected.get("shot_number", 1), "name": expected.get("shot_name", SHOT_ONLY_LABEL),
            "generator": str(self.name)[:128], "model": "", "task": "", "resolution": "", "output": "",
            "media": {"images": 0, "videos": 0, "audio": 0}, "connections": {}, "issues": []}
        issue = lambda code, message, severity="error": row["issues"].append(self._hmb_preflight_issue(code, message, severity))
        params = self._hmb_preflight_parameters(bound=bound)
        sparse = bool(params["resume_generation_id"] or params["draft_action"] == DRAFT_ACTION_FINAL)
        row.update(model=MODEL_DISPLAY_NAME_BY_ID.get(params["model_id"], "알 수 없는 모델"),
            task="기존 Task 조회" if params["resume_generation_id"] else "Draft Final" if sparse else params["task"] if params["task"] in TASK_STORAGE_CHOICES else "알 수 없는 작업",
            resolution=params["resolution"] if params["resolution"] in {item for values in MODEL_RESOLUTIONS.values() for item in values} else "확인 필요")
        edges = self._project_incoming_connections(self)
        def edge_source(target: str, port: str, kind: str) -> Any:
            matches = [edge for edge in edges if str(getattr(edge, "target_parameter_name", "")) == target]
            if not matches:
                row["connections"][kind] = "선택 사항 / 미연결"
                return None
            if len(matches) != 1:
                raise ValueError("ambiguous")
            edge = matches[0]
            node = nodes.get(str(getattr(edge, "source_node_name", "")))
            if node is None or self._hmb_preflight_kind(node) != kind or getattr(edge, "source_parameter_name", "") != port:
                raise ValueError("foreign_source")
            row["connections"][kind] = "연결됨"
            return node
        try:
            project = self._capture_imageasset_project_selection()["project"]
            row["project"] = str(project["project_name"])
            if bound and source is not None:
                canonical_project = resolve_project(source._hmb_project_identity(), default_legacy=False)
                if project["project_id"] != canonical_project["project_id"]:
                    issue("project_mixed", "ImageAsset와 Generator의 프로젝트가 다릅니다.")
        except Exception:
            issue("project_unverified", "프로젝트 연결 또는 Project (Only) 선택을 확인하세요.", "warning" if sparse else "error")
        if bound and not sparse:
            identity = self._hmb_shot_channel_subscription()
            if any(identity.get(key) != expected.get(key) for key in ("channel_uuid", "shot_uuid", "shot_number", "shot_name")):
                issue("shot_identity", "ImageAsset의 UUID·순서·변경 이름과 Generator 연결이 일치하지 않습니다.")
            params.update(reference_images=[], video_references=[], reference_audio=[])
            try:
                image = edge_source(SHOT_ASSET_INPUT_PARAMETER, "SHOT_ASSET_OUT", "HMBImageAssetLibrary")
                if image is not None and image is not source:
                    raise ValueError("foreign_image_source")
                if source_issue:
                    issue("image_snapshot_unverified", "ImageAsset 선택 미디어 캐시가 준비되지 않았습니다. 준비 후 다시 점검하세요.", "warning")
                elif isinstance(source_snapshot, dict):
                    shot = next(item for item in source_snapshot["shots"] if item["shot_uuid"] == expected["shot_uuid"])
                    if (shot["number"], shot["name"]) != (expected["shot_number"], expected["shot_name"]):
                        raise ValueError("image_identity")
                    selected = [source_snapshot["media_by_source_uid"][uid] for uid in shot["selected_source_uids"]]
                    if selected and image is None:
                        issue("image_edge_missing", "선택한 이미지가 있지만 Generator의 ImageAsset 입력선이 없습니다.")
                    if image is not None:
                        params["reference_images"] = selected
                picker = edge_source(SHOT_PICKER_INPUT_PARAMETER, "SHOT_PICKER_OUT", "HMBVideoPickerLibrary")
                if picker is not None:
                    if self._direct_source_subscription(picker, "video_picker").get("channel_uuid") != expected["channel_uuid"]:
                        raise ValueError("picker_channel")
                    snap = self._validate_direct_media_snapshot(picker._hmb_shot_routing_snapshot(expected["channel_uuid"], validate_media=False),
                        source_kind="video_picker", expected_channel_uuid=expected["channel_uuid"])
                    selected = next(item for item in snap["shots"] if item["shot_uuid"] == expected["shot_uuid"])
                    if (selected["number"], selected["name"]) != (expected["shot_number"], expected["shot_name"]):
                        raise ValueError("picker_identity")
                    params["video_references"] = [snap["media_by_source_uid"][uid] for uid in selected["selected_source_uids"]]
                else:
                    available = [candidate for candidate in nodes.values()
                        if self._hmb_preflight_kind(candidate) == "HMBVideoPickerLibrary"
                        and candidate._hmb_shot_channel_subscription().get("channel_uuid") == expected["channel_uuid"]]
                    if len(available) > 1:
                        issue("picker_duplicate", "이 채널의 VideoPicker 소스가 중복되었습니다.")
                    elif available:
                        try:
                            snap = self._validate_direct_media_snapshot(available[0]._hmb_shot_routing_snapshot(expected["channel_uuid"], validate_media=False),
                                source_kind="video_picker", expected_channel_uuid=expected["channel_uuid"])
                            selected = next(item for item in snap["shots"] if item["shot_uuid"] == expected["shot_uuid"])
                            if selected["selected_source_uids"]:
                                issue("picker_edge_missing", "Picker에 선택한 영상이 있지만 Generator의 Picker 입력선이 없습니다.")
                        except Exception:
                            issue("picker_unverified", "미연결 Picker의 선택 상태를 확인하지 못했습니다.", "warning")
                finish = edge_source(SHOT_FINISH_LOOK_INPUT_PARAMETER, "SHOT_FINISH_LOOK_OUT", "HMBFinishLookLibrary")
                if finish is not None and not self._hmb_preflight_declares(finish, "finish_look", expected):
                    raise ValueError("finish_identity")
                agent_edges = [edge for edge in edges if getattr(edge, "target_parameter_name", "") == "prompt"]
                if len(agent_edges) > 1:
                    raise ValueError("ambiguous_prompt")
                if agent_edges:
                    edge = agent_edges[0]; agent = nodes.get(str(getattr(edge, "source_node_name", "")))
                    if agent is not None and self._hmb_preflight_kind(agent) == "HMBAgentLibrary":
                        if getattr(edge, "source_parameter_name", "") != "output" or not self._hmb_preflight_declares(agent, "agent", expected):
                            raise ValueError("agent_identity")
                        upstream = [item for item in self._project_incoming_connections(agent)
                            if getattr(item, "target_parameter_name", "") == "SHOT_PROMPT_IN"]
                        if len(upstream) != 1:
                            raise ValueError("prompt_missing")
                        prompt = nodes.get(str(getattr(upstream[0], "source_node_name", "")))
                        if (prompt is None or self._hmb_preflight_kind(prompt) != "HMBPromptLibrary"
                                or getattr(upstream[0], "source_parameter_name", "") != "PROMPT_OUT"
                                or not self._hmb_preflight_declares(prompt, "prompt", expected)):
                            raise ValueError("prompt_identity")
                        row["connections"]["Prompt → Agent"] = "UUID 일치"
                        # StartFlow also validates a placeholder before Agent output
                        # exists. This sentinel is private to the copied validator.
                        if not params["prompt"].strip():
                            params["prompt"] = "HMB connected prompt pending execution"
                    else:
                        issue("manual_prompt", "일반 Prompt 입력 경로를 사용합니다. Agent 실행 여부는 점검하지 않습니다.", "warning")
                        if not params["prompt"].strip():
                            params["prompt"] = "HMB connected prompt pending execution"
            except Exception:
                issue("source_route", "Prompt·Agent·Finish·ImageAsset·Picker 중 연결선 또는 정확한 Shot UUID를 확인하세요.")
        elif sparse:
            issue("sparse_existing_task", "기존 Task 조회/Final은 새 Prompt·미디어·Agent를 요구하지 않습니다.", "info")
            if params["draft_action"] == DRAFT_ACTION_FINAL:
                issue("final_server_unverified", "Final 사용 가능 여부는 서버의 같은 Draft Task 상태 확인이 필요합니다.", "warning")
        row["media"] = {"images": len(params["reference_images"]), "videos": len(params["video_references"]), "audio": len(params["reference_audio"])}
        if source_issue and bound and not sparse:
            row["media"]["images"] = None
        try:
            validation = dict(params)
            if source_issue and bound and not sparse and not any(validation[key] for key in ("reference_images", "video_references", "reference_audio")):
                validation["reference_images"] = ["HMB unverified cached media placeholder"]
            self._validate_parameters(validation)
            if not params["resume_generation_id"]:
                self._validate_broker_model(params["model_id"])
        except Exception as exc:
            # Native validation never includes prompt/media contents. Remove
            # authored repr strings before reporting its bounded diagnostic.
            diagnostic = re.sub(r"(['\"]).*?\1", "[값]", str(exc))[:260]
            if "Unsupported" in diagnostic or "does not support" in diagnostic:
                diagnostic = "선택한 모델·작업·해상도·출력 형식의 지원 여부를 확인하세요."
            issue("settings_invalid", diagnostic or "모델·작업·미디어 수량·설정을 확인하세요.")
        raw_output = self.get_parameter_value("output_file")
        output = str(getattr(raw_output, "location", getattr(raw_output, "value", raw_output)) or "").strip()
        row["output"] = output.replace("\\", "/").split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1][:128]
        if not output:
            issue("output_missing", "출력 파일 경로가 비어 있습니다.", "warning" if sparse else "error")
        elif "\x00" in output or any(part == ".." for part in output.replace("\\", "/").split("/")):
            issue("output_invalid", "출력 경로에 허용되지 않은 구성 요소가 있습니다.")
        if output and Path(output).suffix.lower() not in {".mp4", ".mov"}:
            issue("output_extension", "출력 파일 확장자를 MP4/MOV로 확인하세요.", "warning")
        issue("offline_scope", "파일 접근·서버 권한·실제 미디어 디코딩은 실행하지 않았습니다.", "info")
        row["status"] = "error" if any(item["severity"] == "error" for item in row["issues"]) else "warning" if any(item["severity"] == "warning" for item in row["issues"]) else "ready"
        return row

    def _hmb_render_preflight_report(self) -> dict[str, Any]:
        """Inspect registered same-flow state only; no reconcile/prepare/execute."""
        flow_name, candidates = _shot_routing._same_flow_nodes(self)
        result = {"schema": SEEDANCE_PREFLIGHT_SCHEMA, "version": 1, "phase": "complete", "request_id": "",
            "checked_at_ms": int(time.time() * 1000), "flow": flow_name, "rows": [], "issues": [],
            "scope": "only", "channel_uuid": "", "ok": False,
            "notice": "점검 시점의 로컬 연결·설정 검사입니다. 서버 지원·계정·실제 파일 접근·디코딩은 미확인입니다. 업로드·Agent·렌더·연결 변경 없음. 정책은 Agent에서 적용하며 정책 없음은 렌더를 차단하지 않습니다."}
        if not flow_name or self not in candidates:
            result["issues"].append(self._hmb_preflight_issue("unregistered", "현재 Flow의 등록된 Generator를 다시 여세요."))
            return result
        nodes = {str(node.name): node for node in candidates if not getattr(node, "_hmb_node_deleted", False)}
        identity = self._hmb_shot_channel_subscription()
        if self.get_parameter_value("resume_generation_id") or self.get_parameter_value("draft_action") == DRAFT_ACTION_FINAL:
            result["scope"] = "existing_task"
            result["rows"] = [self._hmb_preflight_row(identity, nodes=nodes)]
        elif not identity.get("enabled"):
            result["rows"] = [self._hmb_preflight_row(identity, nodes=nodes)]
        else:
            channel = identity["channel_uuid"]; result.update(scope="shots", channel_uuid=channel)
            sources = [node for node in nodes.values() if self._hmb_preflight_kind(node) == "HMBImageAssetLibrary"
                and node._hmb_shot_channel_subscription().get("channel_uuid") == channel]
            if len(sources) != 1:
                result["issues"].append(self._hmb_preflight_issue("catalog_source", "이 채널의 정확한 ImageAsset 소스가 없거나 중복되었습니다."))
                return result
            source = sources[0]
            catalog = self._validate_shot_catalog_snapshot(source._hmb_shot_routing_catalog())
            snapshot, source_issue = None, ""
            try:
                snapshot = self._validate_direct_media_snapshot(source._hmb_shot_routing_snapshot(channel, cached_only=True),
                    source_kind="image_asset", expected_channel_uuid=channel)
            except Exception:
                source_issue = "cache_unavailable"
            generators = [node for node in nodes.values() if self._hmb_preflight_kind(node) == "HMBSeedanceGeneration"]
            output_keys: dict[str, list[dict[str, Any]]] = {}
            for shot in sorted(catalog["shots"], key=lambda item: item["number"]):
                expected = {"channel_uuid": channel, "shot_uuid": shot["shot_uuid"], "shot_number": shot["number"], "shot_name": shot["name"]}
                matches = [node for node in generators if all(node._hmb_shot_channel_subscription().get(key) == expected[key] for key in ("channel_uuid", "shot_uuid"))]
                if len(matches) != 1:
                    result["rows"].append({"number": shot["number"], "name": shot["name"], "channel_uuid": channel,
                        "shot_uuid": shot["shot_uuid"], "generator": " / ".join(str(node.name)[:128] for node in matches),
                        "status": "error", "media": {}, "connections": {}, "issues": [self._hmb_preflight_issue(
                            "generator_missing" if not matches else "generator_duplicate", "이 Shot UUID의 Generator가 없습니다." if not matches else "동일 Shot UUID를 사용하는 Generator가 중복되었습니다.")]})
                    continue
                node = matches[0]
                try:
                    row = node._hmb_preflight_row(expected, nodes=nodes, source=source, source_snapshot=snapshot, source_issue=source_issue)
                except Exception:
                    row = {"number": shot["number"], "name": shot["name"], "generator": str(node.name)[:128], "status": "error",
                        "media": {}, "connections": {}, "issues": [self._hmb_preflight_issue("row_unavailable", "이 Shot의 현재 입력을 읽지 못했습니다. 다른 Shot은 계속 점검했습니다.")]}
                result["rows"].append(row)
                raw = node.get_parameter_value("output_file")
                output = str(getattr(raw, "location", getattr(raw, "value", raw)) or "").replace("\\", "/").casefold()
                if output:
                    output_keys.setdefault(output, []).append(row)
            for duplicate_rows in output_keys.values():
                if len(duplicate_rows) > 1:
                    for row in duplicate_rows:
                        row["issues"].append(self._hmb_preflight_issue("output_duplicate", "여러 Generator가 같은 출력 파일 경로를 사용합니다.")); row["status"] = "error"
            if any(node._hmb_shot_channel_subscription().get("enabled") and node._hmb_shot_channel_subscription().get("channel_uuid") != channel for node in generators):
                result["issues"].append(self._hmb_preflight_issue("other_project_channel", "같은 Flow에 다른 프로젝트/채널의 Generator도 있습니다. 이 표는 선택한 채널만 점검합니다.", "warning"))
            known = {shot["shot_uuid"] for shot in catalog["shots"]}
            if any(node._hmb_shot_channel_subscription().get("channel_uuid") == channel
                    and node._hmb_shot_channel_subscription().get("shot_uuid") not in known for node in generators):
                result["issues"].append(self._hmb_preflight_issue("orphan_generator", "같은 채널에 ImageAsset에서 삭제되었거나 존재하지 않는 Shot UUID의 Generator가 있습니다.", "warning"))
        result["ok"] = bool(result["rows"]) and all(row["status"] != "error" for row in result["rows"]) and not any(item["severity"] == "error" for item in result["issues"])
        return result

    def _hmb_publish_preflight(self, value: dict[str, Any]) -> None:
        if getattr(self, "_hmb_node_deleted", False):
            return
        self._hmb_preflight_publishing = True
        try:
            super().set_parameter_value(SEEDANCE_PREFLIGHT_PARAMETER, value, initial_setup=True, emit_change=False)
            publisher = getattr(self, "publish_update_to_parameter", None)
            if callable(publisher):
                publisher(SEEDANCE_PREFLIGHT_PARAMETER, deepcopy(value))
        finally:
            self._hmb_preflight_publishing = False

    def _hmb_handle_preflight_command(self, value: Any) -> None:
        if not isinstance(value, dict) or value.get("action") not in {"inspect", "cancel"}:
            return
        request_id = value.get("request_id", "")
        if not isinstance(request_id, str) or re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
            return
        if value["action"] == "cancel" and request_id != self._hmb_preflight_active_request_id:
            return  # A late cancel may never retire a newer inspection.
        session, sequence = value.get("client_session"), value.get("sequence")
        if session is not None or sequence is not None:
            if not isinstance(session, str) or re.fullmatch(r"[0-9a-f]{32}", session) is None or type(sequence) is not int or not 0 < sequence <= 9007199254740991:
                return
            sequences = self._hmb_preflight_client_sequences
            if value["action"] == "inspect":
                if self._hmb_preflight_active_request_id and session != self._hmb_preflight_active_client_session:
                    self._hmb_publish_preflight({"schema": SEEDANCE_PREFLIGHT_SCHEMA, "version": 1, "phase": "stale", "request_id": request_id,
                        "rows": [], "ok": False, "issues": [self._hmb_preflight_issue("inspection_busy", "다른 점검 요청이 진행 중입니다. 완료 후 다시 점검하세요.", "warning")]})
                    return
                if sequence <= sequences.get(session, 0):
                    return  # Reordered or replayed commands cannot cancel the latest request.
                if session not in sequences and len(sequences) >= 64:
                    sequences.pop(next(iter(sequences)))  # No other session can evict the in-flight owner.
                sequences.pop(session, None)
                sequences[session] = sequence
        elif value["action"] == "inspect" and self._hmb_preflight_active_request_id and request_id != self._hmb_preflight_active_request_id:
            return  # Legacy nonce-only callers cannot supersede an in-flight request.
        seen = self._hmb_preflight_command_ids
        key = value["action"] + ":" + request_id
        if key in seen:
            return
        seen.add(key)
        if len(seen) > 256:
            seen.clear(); seen.add(key)
        self._hmb_preflight_epoch += 1
        epoch = self._hmb_preflight_epoch
        self._hmb_preflight_active_request_id = request_id if value["action"] == "inspect" else ""
        self._hmb_preflight_active_client_session = (session or "") if value["action"] == "inspect" else ""
        previous = self._hmb_preflight_task
        if previous is not None and not previous.done():
            previous.cancel()
        if value["action"] == "cancel":
            self._hmb_publish_preflight({"schema": SEEDANCE_PREFLIGHT_SCHEMA, "version": 1,
                "phase": "cancelled", "request_id": request_id, "rows": [], "issues": []})
            return
        def release_owner() -> None:
            if epoch == self._hmb_preflight_epoch and self._hmb_preflight_active_request_id == request_id:
                self._hmb_preflight_active_request_id = ""
                self._hmb_preflight_active_client_session = ""
        try:
            requested_identity = self._hmb_shot_channel_subscription()
        except Exception:
            release_owner()
            return
        async def inspect_state():
            try:
                await asyncio.sleep(0)
                try:
                    report = self._hmb_render_preflight_report()
                except Exception:
                    report = {"schema": SEEDANCE_PREFLIGHT_SCHEMA, "version": 1, "phase": "complete", "rows": [], "ok": False,
                        "issues": [self._hmb_preflight_issue("inspection_unavailable", "점검 중 연결 상태가 변경되었거나 아직 준비되지 않았습니다. 다시 점검하세요.")]}
                if epoch == self._hmb_preflight_epoch and not self._hmb_node_deleted:
                    if self._hmb_shot_channel_subscription() != requested_identity:
                        report.update(phase="stale", rows=[], ok=False, issues=[self._hmb_preflight_issue(
                            "selection_changed", "점검 중 Shot 선택이 변경되었습니다. 다시 점검하세요.", "warning")])
                    report["request_id"] = request_id
                    self._hmb_publish_preflight(report)
            except Exception:
                pass  # A disconnected display can retry; never lease it indefinitely.
            finally:
                release_owner()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Direct native callers can use the pure report API. UI inspection
            # runs only on the host loop, never a filesystem/network thread.
            try:
                self._hmb_publish_preflight({"schema": SEEDANCE_PREFLIGHT_SCHEMA, "version": 1, "phase": "complete", "request_id": request_id,
                    "rows": [], "ok": False, "issues": [self._hmb_preflight_issue("event_loop_unavailable", "엔진이 준비된 후 다시 점검하세요.", "warning")]})
            finally:
                release_owner()
        else:
            self._hmb_preflight_task = loop.create_task(inspect_state())

    def _get_parameters(self) -> dict[str, Any]:
        final_context = self._active_draft_final_context()
        if final_context is not None:
            self._validated_draft_final_source(final_context["source"], allow_reserved=True)
            return deepcopy(final_context["params"])
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
        params = {
            "resume_generation_id": str(
                self.get_parameter_value("resume_generation_id") or ""
            ).strip(),
            "model_id": model_id,
            "draft_action": self.get_parameter_value("draft_action") or DRAFT_ACTION_OFF,
            "draft_job_id": str(self.get_parameter_value("draft_job_id") or "").strip(),
            "_hmb_draft_only": self._draft_only_mode(),
            "_hmb_draft_supported": self._draft_mode_supported(),
            "_hmb_draft_source": self._draft_source_record(),
            TASK_PARAMETER: str(
                self.get_parameter_value(TASK_PARAMETER)
                or TASK_REFERENCE_TO_VIDEO
            ),
            "input_mode": self.get_parameter_value("input_mode")
            or INPUT_MODE_MULTIMODAL_REFERENCES,
            "prompt": str(
                self._hmb_managed_agent_request["record"]["text"]
                if isinstance(getattr(self, "_hmb_managed_agent_request", None), dict)
                else self.get_parameter_value("prompt") or ""
            ),
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
                self.get_parameter_value("output_format")
                or (NEW_NODE_OUTPUT_FORMAT if model_id == SEEDANCE_2_5_MODEL_ID else DEFAULT_OUTPUT_FORMAT)
            ).strip().lower(),
            "return_last_frame": bool(
                self.get_parameter_value("return_last_frame")
            ),
            "execution_expires_after": self.get_parameter_value(
                "execution_expires_after"
            ),
            "priority": (
                self.get_parameter_value("priority")
                if model_id == SEEDANCE_2_0_MODEL_ID
                else 0
            ),
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
        # Hidden Only-only controls are dormant outside their supported mode.
        # Preserve the authored selection for a lossless return to Only, but
        # never let it override or block an ordinary Shot/2.0 run.
        if model_id != SEEDANCE_2_5_MODEL_ID or params["_hmb_draft_supported"] is not True:
            params["draft_action"] = DRAFT_ACTION_OFF
        if params["draft_action"] in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}:
            params["resolution"] = "480p" if params["draft_action"] == DRAFT_ACTION_PREVIEW else "1080p"
            if not params["resume_generation_id"]:
                params["output_format"] = "mov"
            params["return_last_frame"] = False
        if params["draft_action"] == DRAFT_ACTION_FINAL and not params["resume_generation_id"]:
            source = self._validated_draft_final_source()
            params["_hmb_draft_source"] = source
            params["draft_job_id"] = source["draft_job_id"]
        return params

    def _draft_only_mode(self) -> bool:
        mode_getter = getattr(self, "_hmb_seedance_execution_mode", None)
        mode = mode_getter() if callable(mode_getter) else ""
        if mode == "only":
            return True
        if mode == "waiting":
            return False
        identity = self._shot_identity()
        return bool(not identity.get("shot_uuid") and self.get_parameter_value(SHOT_SELECTOR_PARAMETER) == SHOT_ONLY_LABEL)

    def _draft_mode_supported(self) -> bool:
        identity = self._shot_identity()
        return bool(self._draft_only_mode() or (identity.get("channel_uuid") and identity.get("shot_uuid")))

    def _draft_owner_id(self) -> str:
        identifier = _seedance_uuid_text(self.get_parameter_value(DRAFT_OWNER_PARAMETER))
        if not identifier:
            return ""
        changed = False
        with _DRAFT_OWNERS_GUARD:
            owner = _DRAFT_OWNERS.get(identifier)
            if owner is not None and owner is not self and owner._runtime_node_is_live(require_registered=True):
                identifier = str(uuid4())
                changed = True
            _DRAFT_OWNERS[identifier] = self
        if changed:
            # A live duplicate gets a new owner; a genuine reopen retains its
            # serialized owner after the old runtime object has gone away.
            self.set_parameter_value(DRAFT_OWNER_PARAMETER, identifier, emit_change=False)
        return identifier

    def _draft_source_key(self, source: dict[str, Any] | None = None) -> str:
        origin = (source.get("generation_origin") or {}) if source is not None else self._shot_identity()
        owner = (source or {}).get("owner_id") or self._draft_owner_id()
        return ":".join((str(origin.get("channel_uuid") or "only"), str(origin.get("shot_uuid") or "only"), str(owner)))

    def _store_draft_source(self, value: dict[str, Any]) -> None:
        # Web-created Drafts belong to their server operation journal. Never
        # publish them as native one-use Final sources on the retained node.
        if getattr(self, "_web_owner", None) is not None:
            return
        source = _seedance_draft_source_value(value)
        if not source:
            raise ValueError("The completed Draft source record is invalid.")
        raw = self.get_parameter_value(DRAFT_SOURCES_PARAMETER)
        records = dict(raw.get("sources", {})) if isinstance(raw, dict) and isinstance(raw.get("sources"), dict) else {}
        records[self._draft_source_key(source)] = source
        # Five production Shots plus Only; bounded even after channel changes.
        records = dict(list(records.items())[-64:])
        self.set_parameter_value(DRAFT_SOURCES_PARAMETER, {"version": 1, "sources": records}, emit_change=False)
        if not source.get("generation_origin"):
            self.set_parameter_value(DRAFT_SOURCE_PARAMETER, source, emit_change=False)

    def _active_draft_final_context(self) -> dict[str, Any] | None:
        context = getattr(self, "_hmb_draft_final_context", None)
        try:
            own_task = asyncio.current_task() is getattr(self, "_hmb_draft_finalize_task", None)
        except RuntimeError:
            own_task = False
        # Blocking submission helpers execute in a worker thread; their source
        # is separately fenced by _submission_start_is_authorized.
        return context if isinstance(context, dict) and own_task else None

    def _draft_source_record(self) -> dict[str, Any]:
        if getattr(self, "_web_owner", None) is not None:
            return {}
        raw = self.get_parameter_value(DRAFT_SOURCES_PARAMETER)
        records = raw.get("sources", {}) if isinstance(raw, dict) else {}
        source = _seedance_draft_source_value(records.get(self._draft_source_key())) if isinstance(records, dict) else {}
        if not source and self._draft_only_mode():
            source = _seedance_draft_source_value(self.get_parameter_value(DRAFT_SOURCE_PARAMETER))
            if source.get("generation_origin"):
                source = {}
        recovered = _seedance_draft_source_value(self._generation_recovery_state().get("draft_source"))
        if recovered and (not recovered.get("generation_origin") and self._draft_only_mode()
                          or recovered.get("generation_origin") and self._draft_source_key(recovered) == self._draft_source_key()):
            if not source or (source["draft_job_id"] == recovered["draft_job_id"] and recovered.get("final_request_id")):
                if source.get("draft_job_id") == recovered["draft_job_id"] and source.get("final_job_id"):
                    recovered["final_job_id"] = source["final_job_id"]
                source = recovered
        return source

    def _validate_draft_shot_binding(self, source: dict[str, Any]) -> None:
        origin = source.get("generation_origin") or {}
        current = self._shot_identity()
        if (source.get("owner_id") != self._draft_owner_id()
                or (origin.get("channel_uuid"), origin.get("shot_uuid")) !=
                (current.get("channel_uuid"), current.get("shot_uuid"))):
            raise ValueError("This Draft belongs to a different Generator or Shot.")
        catalog = _seedance_widget_catalog(getattr(self, "_hmb_shot_catalog_snapshot", None))
        if (not catalog or catalog["channel_uuid"] != origin["channel_uuid"]
                or not any(item["shot_uuid"] == origin["shot_uuid"] for item in catalog["shots"])):
            raise ValueError("The Draft Shot was deleted or its channel is unavailable.")
        bindings: dict[str, str] = {}
        for parameter, port, kind in ((SHOT_ASSET_INPUT_PARAMETER, "SHOT_ASSET_OUT", "image_asset"),
                                      (SHOT_PICKER_INPUT_PARAMETER, "SHOT_PICKER_OUT", "video_picker")):
            node = self._exact_incoming_source(parameter, port, required=False)
            if node is None:
                continue
            if getattr(node, "_hmb_node_deleted", False):
                raise ValueError("The Draft Shot source was deleted.")
            subscription = self._direct_source_subscription(node, kind)
            if subscription.get("channel_uuid") != origin["channel_uuid"]:
                raise ValueError("The Draft Shot source was rebound to another channel.")
            snapshot_api = getattr(node, "_hmb_shot_routing_catalog" if kind == "image_asset" else "_hmb_shot_routing_snapshot", None)
            if not callable(snapshot_api):
                raise ValueError("The Draft Shot source identity is unavailable.")
            snapshot = snapshot_api() if kind == "image_asset" else snapshot_api(origin["channel_uuid"], validate_media=False)
            if (not isinstance(snapshot, dict) or snapshot.get("channel_uuid") != origin["channel_uuid"]
                    or not any(isinstance(item, dict) and item.get("shot_uuid") == origin["shot_uuid"]
                               for item in snapshot.get("shots", []))):
                raise ValueError("The completed Draft Shot is missing from its source.")
            publisher = _seedance_uuid_text(snapshot.get("publisher_instance_uuid"))
            if not publisher:
                raise ValueError("The Draft source publisher identity is unavailable.")
            bindings[kind] = publisher
        if not bindings:
            raise ValueError("The Draft Shot source is disconnected.")
        if bindings != source.get("source_bindings"):
            raise ValueError("The Draft Shot source publisher was replaced or disconnected.")
        project = self._hmb_generation_project()
        if any(project.get(key) != source.get(key) for key in ("project_id", "project_name")):
            raise ValueError("The selected project does not match the completed Draft.")

    def _draft_final_status_identity(self, source: dict[str, Any]) -> tuple[str, ...]:
        bridge = self._get_broker_bridge(server_url=source["broker_server_url"])
        if bridge.server_url != source["broker_server_url"]:
            raise _BrokerProtocolError("The Draft status Broker origin changed.")
        credential = bridge._load_access_token()
        if not credential:
            raise _BrokerAuthenticationError("Connect to the original Broker to check this Draft.")
        return (source["broker_server_url"], source["project_id"], source["project_name"],
                source["draft_job_id"], hashlib.sha256(credential.encode("utf-8")).hexdigest())

    def _apply_draft_final_server_state(self, source: dict[str, Any], identity: tuple[str, ...],
                                      state: dict[str, Any]) -> bool:
        current = self._draft_source_record()
        if (not self._runtime_node_is_live(require_registered=True)
                or any(current.get(key) != source.get(key) for key in
                       ("draft_job_id", "broker_server_url", "project_id", "project_name"))
                or self._draft_final_status_identity(source) != identity):
            return False
        previous = getattr(self, "_hmb_draft_final_status_cache", {})
        owner_user_id = None
        if previous.get("identity") == identity:
            old_state = previous.get("value", {})
            owner_user_id = previous.get("owner_user_id") or old_state.get("owner_user_id")
            if owner_user_id and state.get("owner_user_id") not in (None, owner_user_id):
                raise _BrokerProtocolError("The authenticated Draft owner changed during status reconciliation.")
            # Never turn a known child or consumed Final into a new intent on
            # a delayed available/expired projection or transient GET error.
            if old_state.get("consumed") is True and state.get("consumed") is not True:
                state = {**old_state, "state": "unknown" if old_state.get("state") not in
                         _DRAFT_FINAL_HIDDEN_STATES else old_state["state"], "eligible": False}
            elif old_state.get("child_task_id") and not state.get("child_task_id"):
                state = {**state, "state": "unknown", "consumed": None, "child_task_id": old_state["child_task_id"],
                         "child_status": old_state.get("child_status"), "eligible": False}
        self._hmb_draft_final_status_cache = {"identity": identity, "value": deepcopy(state),
            "owner_user_id": owner_user_id or state.get("owner_user_id"), "received_at": time.monotonic()}
        child = state.get("child_task_id")
        if child:
            record = self._draft_source_record()
            if record.get("draft_job_id") == source["draft_job_id"] and not record.get("final_job_id"):
                self._store_draft_source({**record, "final_job_id": child})
        return True

    async def _query_draft_final_server_state(self, source: dict[str, Any], *, bridge: Any = None) -> dict[str, Any]:
        identity = self._draft_final_status_identity(source)
        if bridge is None:
            bridge = self._get_broker_bridge(server_url=source["broker_server_url"])
        try:
            state = await asyncio.to_thread(bridge.get_draft_final_state, source, timeout=5.0)
            if not self._apply_draft_final_server_state(source, identity, state):
                raise _BrokerProtocolError("The Draft or Broker account changed while checking Final status.")
        except Exception:
            with suppress(Exception):
                self._apply_draft_final_server_state(source, identity, {"state": "unknown", "eligible": False,
                    "consumed": None, "source_task_id": source["draft_job_id"], "child_task_id": None})
            raise
        return deepcopy(self._hmb_draft_final_status_cache["value"])

    def _schedule_draft_final_status_sync(self, source: dict[str, Any], identity: tuple[str, ...]) -> None:
        if getattr(self, "_web_owner", None) is not None or not self._runtime_node_is_live(require_registered=True):
            return
        future = getattr(self, "_hmb_draft_final_status_future", None)
        if future is not None and not future.done():
            if getattr(self, "_hmb_draft_final_status_scope", ()) == identity:
                return
            future.cancel()
        try:
            loop = getattr(GriptapeNodes.EventManager(), "event_loop", None)
            if loop is None or not loop.is_running():
                return
            self._hmb_draft_final_status_scope = identity
            self._hmb_draft_final_status_future = asyncio.run_coroutine_threadsafe(
                self._poll_draft_final_server_state(deepcopy(source), identity), loop)
        except (RuntimeError, AttributeError):
            return

    async def _poll_draft_final_server_state(self, source: dict[str, Any], identity: tuple[str, ...]) -> None:
        while self._runtime_node_is_live(require_registered=True):
            try:
                if (self._draft_source_record().get("draft_job_id") != source["draft_job_id"]
                        or self._draft_final_status_identity(source) != identity):
                    return
                state = await self._query_draft_final_server_state(source)
            except asyncio.CancelledError:
                raise
            except Exception:
                state = {"state": "unknown", "eligible": False, "consumed": None,
                         "source_task_id": source["draft_job_id"], "child_task_id": None}
                with suppress(Exception):
                    if not self._apply_draft_final_server_state(source, identity, state):
                        return
            with suppress(Exception):
                self._sync_seedance_shot_widget(emit_change=True)
            if state.get("state") in _DRAFT_FINAL_HIDDEN_STATES:
                return
            await asyncio.sleep(_DRAFT_FINAL_SYNC_SECONDS)

    def _draft_final_server_snapshot(self, source: dict[str, Any]) -> dict[str, Any]:
        try:
            identity = self._draft_final_status_identity(source)
        except Exception:
            return {"state": "unavailable", "eligible": False, "child_task_id": None}
        cached = getattr(self, "_hmb_draft_final_status_cache", {})
        if cached.get("identity") == identity and cached.get("value", {}).get("state") in _DRAFT_FINAL_HIDDEN_STATES:
            return deepcopy(cached["value"])
        self._schedule_draft_final_status_sync(source, identity)
        if cached.get("identity") == identity:
            value = cached.get("value", {})
            if time.monotonic() - cached.get("received_at", 0) <= _DRAFT_FINAL_SYNC_SECONDS + 5:
                return deepcopy(value)
        return {"state": "checking", "eligible": False, "child_task_id": None}

    def _validated_draft_final_source(self, source: dict[str, Any] | None = None, *, allow_reserved: bool = False) -> dict[str, Any]:
        model = str(self.get_parameter_value("model_id") or "")
        if MODEL_ID_ALIASES.get(model, model) != SEEDANCE_2_5_MODEL_ID:
            raise ValueError("Draft finalization requires Seedance 2.5.")
        record = _seedance_draft_source_value(source if source is not None else self._draft_source_record())
        if not record:
            raise ValueError("Complete a Draft for this Shot before finalizing.")
        if record.get("owner_id") and record["owner_id"] != self._draft_owner_id():
            raise ValueError("This Draft belongs to a different Generator.")
        if record.get("generation_origin"):
            self._validate_draft_shot_binding(record)
        elif not self._draft_only_mode():
            raise ValueError("This Draft has no verified Shot identity.")
        else:
            try:
                project = self._hmb_generation_project()
            except _ProjectSelectionRequired:
                project = {}  # A legacy Only Final retains its original project.
            if project and any(project.get(key) != record[key] for key in ("project_id", "project_name")):
                raise ValueError("The selected Only project does not match the completed Draft.")
        created = record.get("created_at_ms")
        if created is not None and (created > int(time.time() * 1000) or int(time.time() * 1000) >= created + DRAFT_SOURCE_TTL_MS):
            raise ValueError("This Draft has expired. Create a new 480p Draft.")
        if record.get("final_job_id") or (record.get("final_request_id") and not allow_reserved):
            raise ValueError("This Draft already has a Final request. Use Refresh / Retrieve Result for that task.")
        # Legacy Only records retain their original Broker; Shot mode must
        # still be bound to the same configured production endpoint.
        if record.get("generation_origin") and record["broker_server_url"] != self._selected_broker_server_url():
            raise ValueError("The selected Broker does not match the completed Draft.")
        return deepcopy(record)

    def _draft_ui_state(self) -> dict[str, Any]:
        if _my_box_node.is_selected(self):
            return self._hmb_my_box_controller().draft_ui_state()
        model = str(self.get_parameter_value("model_id") or "")
        supported = MODEL_ID_ALIASES.get(model, model) == SEEDANCE_2_5_MODEL_ID and self._draft_mode_supported()
        resolution = str(self.get_parameter_value("resolution") or "")
        action = self.get_parameter_value("draft_action") or DRAFT_ACTION_OFF
        source = self._draft_source_record() if supported else {}
        busy = bool(self._generation_run_active.is_set() or self._generation_refresh_running
                    or getattr(self, "_hmb_draft_finalize_pending", False))
        active_action = getattr(self, "_hmb_active_draft_action", DRAFT_ACTION_OFF) if busy else DRAFT_ACTION_OFF
        if self._hmb_draft_finalize_pending or isinstance(getattr(self, "_hmb_draft_final_context", None), dict):
            active_action = DRAFT_ACTION_FINAL
        final_busy = bool(busy and supported and active_action == DRAFT_ACTION_FINAL)
        final_available = False
        reason = ""
        final_state = "unavailable"
        final_task_id = ""
        if supported and source:
            server = self._draft_final_server_snapshot(source)
            final_state = str(server.get("state") or "unknown")
            final_task_id = str(server.get("child_task_id") or source.get("final_job_id") or "")
            try:
                self._validated_draft_final_source(source)
                final_available = not busy and final_state == "available" and server.get("eligible") is True
            except (ValueError, RuntimeError) as exc:
                reason = str(exc)
                if source.get("final_job_id") and final_state in {"available", "checking", "unavailable"}:
                    final_state = "consumed"
                elif source.get("final_request_id") and final_state in {"available", "checking", "unavailable"}:
                    final_state = "unknown"
                elif "expired" in reason.lower() and not final_task_id:
                    final_state = "expired"
            if not final_available and not reason:
                reason = {"checking": "Final 상태를 확인하고 있습니다.",
                    "reserved": "이 Draft의 Final 요청이 접수되었습니다. 웹에서 같은 Task를 확인하세요.",
                    "running": "이 Draft의 Final이 처리 중입니다. 웹에서 같은 Task를 확인하세요.",
                    "unknown": "Final 상태를 확인할 수 없습니다. 새 렌더 대신 기존 Task를 조회하세요.",
                    "source_pending": "Draft가 완료된 뒤 Final을 사용할 수 있습니다.",
                    "unavailable": "원래 Broker에 연결해 Final 상태를 확인하세요."}.get(final_state, "")
        elif supported:
            reason = "Complete a 480p Draft to enable Finalize 1080p."
        return _seedance_draft_ui_value({"visible": supported and (resolution == "480p" or bool(source)),
            "action": action if supported else DRAFT_ACTION_OFF,
            "preview_available": supported and resolution == "480p" and not busy,
            "final_available": final_available, "job_id": source.get("draft_job_id", ""),
            "effective_resolution": "1080p" if action == DRAFT_ACTION_FINAL else "480p" if action == DRAFT_ACTION_PREVIEW and supported else resolution,
            "busy": busy, "final_busy": final_busy, "active_action": active_action,
            "cancel_available": bool(self._hmb_draft_finalize_pending and self._active_draft_job_id()),
            "active_job_id": self._active_draft_job_id(), "reason": "Generator is busy." if busy else reason,
            "final_state": final_state, "final_visible": bool(source) and final_state not in _DRAFT_FINAL_HIDDEN_STATES
                and (not busy or final_busy),
            "final_task_id": final_task_id})

    def _draft_final_requested(self) -> bool:
        if isinstance(getattr(self, "_hmb_draft_final_context", None), dict):
            return True
        model = str(self.get_parameter_value("model_id") or "")
        return bool(self.get_parameter_value("draft_action") == DRAFT_ACTION_FINAL
                    and MODEL_ID_ALIASES.get(model, model) == SEEDANCE_2_5_MODEL_ID
                    and self._draft_mode_supported())

    @staticmethod
    def _validate_draft_parameters(params: dict[str, Any]) -> str:
        action = params.get("draft_action", DRAFT_ACTION_OFF)
        if action not in DRAFT_ACTION_CHOICES:
            raise ValueError("Unsupported Draft action.")
        if action == DRAFT_ACTION_OFF:
            return action
        if params.get("model_id") != SEEDANCE_2_5_MODEL_ID or not (params.get("_hmb_draft_only") is True or params.get("_hmb_draft_supported") is True):
            raise ValueError("Draft requires Seedance 2.5 in Only or a verified Shot.")
        expected = "480p" if action == DRAFT_ACTION_PREVIEW else "1080p"
        if params.get("resolution") != expected or params.get("output_format") not in OUTPUT_FORMAT_CHOICES or params.get("return_last_frame") is not False:
            raise ValueError("Draft uses a 480p preview or 1080p final in MOV or legacy MP4, without last-frame output.")
        if action == DRAFT_ACTION_FINAL and re.fullmatch(r"job-[0-9a-f]{32}", params.get("draft_job_id", "")) is None:
            raise ValueError("Finalize Draft requires a completed LOCAL Broker Draft job ID (job-...).")
        return action

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

        if self._validate_draft_parameters(params) == DRAFT_ACTION_FINAL:
            # Finalization sends no new prompt/media/input/duration/audio settings.
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
                raise ValueError(
                    "Video Editing duration must be -1 so the output matches "
                    "the source video."
                )
            if task == TASK_VIDEO_EXTENSION:
                raise ValueError(
                    "Video Extension duration must be -1 or an integer from 4 "
                    "through 30."
                )
            if model_id == SEEDANCE_2_5_MODEL_ID:
                raise ValueError(
                    f"{model_name} duration must be an integer from 4 through "
                    f"{maximum_duration}."
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
            if audio and not (images or videos):
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
        if params.get("resume_generation_id") or params.get("draft_action") == DRAFT_ACTION_FINAL:
            return params
        only_guard = getattr(self, "_assert_only_mode_inputs", None)
        if callable(only_guard):
            only_guard()
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

    def _validate_local_render_preflight(self) -> dict[str, Any]:
        """Validate this render before its managed Agent or billable submission."""
        params = self._get_parameters_for_start_validation()
        self._validate_parameters(params)
        if not params.get("resume_generation_id"):
            self._validate_broker_model(params.get("model_id"))
        return params

    def _record_local_render_preflight(self) -> None:
        # SDK validation exceptions reject the entire Flow, including unrelated
        # Shots. Keep native structural errors global, but recheck HMB render
        # admission at execution and publish this Shot's explicit Skipped result.
        # This record is diagnostic only: a later repaired binding must recover.
        if _my_box_node.is_selected(self):
            # Private selection is validated without production project/Agent IO.
            try:
                self._hmb_my_box_controller().validate_start()
            except Exception as exc:
                self._hmb_local_preflight_failure = self._safe_exception_message(exc)
            else:
                self._hmb_local_preflight_failure = ""
            return
        try:
            self._validate_local_render_preflight()
        except Exception as exc:
            self._hmb_local_preflight_failure = self._safe_exception_message(exc)
        else:
            self._hmb_local_preflight_failure = ""

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []
        self._record_local_render_preflight()
        return exceptions or None

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        self._record_local_render_preflight()
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
    def _validate_data_uri(cls, kind: str, value: str, *, reference_ordinal: int = 1) -> str:
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
        if kind == "image":
            cls._validate_image_content(decoded, mime, reference_ordinal=reference_ordinal)
        encoded = base64.b64encode(decoded).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _validate_image_content(content: bytes, mime: str, *, media_name: str = "",
                                reference_ordinal: int = 1) -> dict[str, Any]:
        info = inspect_seedance_image_payload(
            content, media_name=media_name, reference_ordinal=reference_ordinal,
        )
        actual = info["mime_type"]
        aliases = {"image/heic": "image/heif"}
        if aliases.get(mime, mime) != aliases.get(actual, actual):
            raise ValueError(
                f"Image reference {reference_ordinal} has a file type different from its declared MIME type."
            )
        return info

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
            if kind == "image":
                cls._validate_image_content(path.read_bytes(), mime, media_name=path.name)
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
        python = _isolated_tos_runtime_python()
        client = _IsolatedTOSClient(
            python,
            {"ak": access_key, "sk": secret_key, "endpoint": endpoint, "region": region},
            is_live=lambda: not bool(getattr(self, "_hmb_node_deleted", False))
            and not bool(getattr(self, "is_cancellation_requested", False))
            and self._runtime_node_is_live(require_registered=True),
        )
        return _IsolatedTOSModule, client, bucket_name

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
        *, reference_ordinal: int = 1,
    ) -> tuple[bytes, str, str]:
        """Read one bounded image candidate without changing saved parameters."""

        reference = cls._coerce_reference_value(value)
        text = str(reference).strip()
        if text.startswith("data:"):
            normalized = cls._validate_data_uri("image", text, reference_ordinal=reference_ordinal)
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
            content = path.read_bytes()
            cls._validate_image_content(content, mime, media_name=path.name,
                                        reference_ordinal=reference_ordinal)
            return content, mime, path.name
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
        ordinal = 0
        for value in values:
            if not self._has_reference_value(value):
                continue
            ordinal += 1
            text = str(self._coerce_reference_value(value)).strip()
            if text.startswith(("http://", "https://", "asset://")):
                continue
            # Validate all local inputs before creating any upload. In
            # particular, a later oversized reference must not leave earlier
            # references partially uploaded before its error is reported.
            self._read_image_for_cloud_upload(value, reference_ordinal=ordinal)
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
        self._assert_operation_project_selection()
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
        # Only preparation-local, never-submitted objects remain on these
        # lists. Accepted/possibly accepted objects belong to a process lease.
        uploads = list(reversed(self._temporary_video_uploads))
        self._temporary_video_uploads = []
        self._delete_temporary_video_uploads(uploads)
        tos_uploads = list(reversed(self._temporary_tos_video_uploads))
        self._temporary_tos_video_uploads = []
        self._delete_temporary_tos_video_uploads(tos_uploads)

    def _defer_temporary_video_upload_cleanup(self) -> None:
        """Hold unknown inputs; a timer is not evidence of remote completion."""
        uploads = list(reversed(self._temporary_video_uploads))
        self._temporary_video_uploads = []
        tos_uploads = list(reversed(self._temporary_tos_video_uploads))
        self._temporary_tos_video_uploads = []
        _reference_leases.hold_unscoped(uploads, tos_uploads)

    def _bind_temporary_reference_lease(self, bridge: Any, origin: str, client_id: str, *, scope: str = "video") -> str:
        principal_scope = getattr(bridge, "_reference_principal_scope", None)
        with principal_scope() if callable(principal_scope) else nullcontext("") as principal:
            identifier = _reference_leases.acquire(origin=origin, principal=principal,
                client_request_id=client_id, cloud=self._temporary_video_uploads,
                tos=self._temporary_tos_video_uploads, scope=scope)
        self._hmb_reference_upload_lease_id = identifier
        self._hmb_reference_upload_origin = origin
        self._hmb_reference_upload_bridge = bridge
        self._hmb_reference_upload_client_id = client_id
        # Transfer ownership only after the metadata journal is durable.
        self._temporary_video_uploads = []
        self._temporary_tos_video_uploads = []
        return identifier

    def _reject_unsubmitted_reference_lease(self) -> None:
        uploads, tos = _reference_leases.reject_unsubmitted(getattr(self, "_hmb_reference_upload_lease_id", ""))
        self._delete_temporary_video_uploads(uploads)
        self._delete_temporary_tos_video_uploads(tos)

    def _observe_reference_lease(self, response: Any, *, bridge: Any, origin: str, requested_id: str,
                                 identifier: str = "", private_scope: bool = False) -> None:
        """Private cleanup only: never restore credentials or publish UI here."""
        try:
            if not private_scope:
                self._normalize_broker_task(response, fallback_job_id=requested_id, server_url=origin)
            identifier = identifier or getattr(self, "_hmb_reference_upload_lease_id", "")
            principal_scope = getattr(bridge, "_reference_principal_scope", None)
            with principal_scope(response) if callable(principal_scope) else nullcontext("") as principal:
                uploads, tos = _reference_leases.observe(identifier, origin=origin, principal=principal,
                    requested_id=requested_id, response=response)
        except (OSError, ValueError, TypeError, _BrokerError):
            # An unavailable journal or malformed lookup cannot authorize
            # deletion. The process-owned handles remain held for remote TTL.
            return
        self._delete_temporary_video_uploads(uploads)
        self._delete_temporary_tos_video_uploads(tos)

    def _observe_reference_lease_response(self, response: Any, bridge: Any, origin: str,
                                        requested_id: str, identifier: str) -> None:
        self._observe_reference_lease(response, bridge=bridge, origin=origin,
            requested_id=requested_id, identifier=identifier)

    def _build_broker_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Map the HMB media contract to the FN AI Broker Seedance schema."""
        self._assert_operation_project_selection()
        self._validate_parameters(params)
        self._validate_broker_model(params.get("model_id"))
        if params.get("draft_action") == DRAFT_ACTION_FINAL:
            source = _seedance_draft_source_value(params.get("_hmb_draft_source"))
            resolved_project = (source if source.get("draft_job_id") == params["draft_job_id"] else resolve_project(params))
            project = {key: resolved_project[key] for key in ("project_id", "project_name")}
            params["_hmb_draft_project"] = dict(project)
            return {"provider": "volcengine_ark", "model": SEEDANCE_2_5_MODEL_ID,
                    "draft_job_id": params["draft_job_id"], "resolution": "1080p", "output_format": params["output_format"], **project}
        submitted_prompt = self._compose_finish_look_prompt(
            params.get("prompt"),
            params.get("_hmb_finish_look_out"),
        )
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
            "prompt": submitted_prompt,
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
        if not isinstance(self, _HMBWebRerenderExecution):
            captured_mode = params.get("_hmb_generation_mode")
            if type(captured_mode) is str and captured_mode in {"only", "shot"}:
                payload[GENERATION_MODE_METADATA_FIELD] = captured_mode
                payload[GENERATION_TASK_METADATA_FIELD] = task
                if captured_mode == "shot":
                    captured_shot = _generation_submission_shot(params.get("_hmb_generation_origin"))
                    if captured_shot:
                        payload[GENERATION_SHOT_METADATA_FIELD] = captured_shot
        project = resolve_project(params)
        payload.update({key: project[key] for key in ("project_id", "project_name")})
        selection = params.get("_hmb_imageasset_project_selection")
        if not isinstance(self, _HMBWebRerenderExecution) and isinstance(selection, dict):
            if (selection.get("schema") not in (PROJECT_SELECTION_SCHEMA, ONLY_PROJECT_SELECTION_SCHEMA)
                    or selection.get("project") != {key: project[key] for key in ("project_id", "project_name")}):
                raise ValueError("The captured ImageAsset project does not match the generation request.")
            payload["project_selection_schema"] = selection["schema"]
        if params.get("draft_action") == DRAFT_ACTION_PREVIEW:
            payload["draft"] = True
            params["_hmb_draft_project"] = {key: project[key] for key in ("project_id", "project_name")}
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
    def _broker_result_url(
        cls, value: Any, *, depth: int = 0, server_url: str | None = None,
    ) -> str:
        if depth > 5:
            return ""
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith(("http://", "https://")):
                return candidate
            if candidate.startswith("/") and not candidate.startswith("//"):
                base = _broker_validated_server_url(server_url)
                prefix = urlparse(base).path.rstrip("/")
                prefixed_asset = bool(prefix and re.fullmatch(
                    re.escape(prefix) + r"/api/assets/[A-Za-z0-9_-]{43}", urlparse(candidate).path))
                return _broker_config.join_broker_url(base, candidate, allow_prefixed=prefixed_asset)
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
                        value.get(key), depth=depth + 1, server_url=server_url,
                    )
                    if candidate:
                        return candidate
        if isinstance(value, list):
            for item in value:
                candidate = cls._broker_result_url(
                    item, depth=depth + 1, server_url=server_url,
                )
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
        server_url: str | None = None,
    ) -> str:
        """Find one explicitly named result URL without confusing media roles."""

        if depth > 5:
            return ""
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).casefold() in names:
                    candidate = cls._broker_result_url(
                        item, depth=depth + 1, server_url=server_url,
                    )
                    if candidate:
                        return candidate
            for key in ("content", "response", "result", "data", "output"):
                if key in value:
                    candidate = cls._broker_named_result_url(
                        value.get(key),
                        names,
                        depth=depth + 1,
                        server_url=server_url,
                    )
                    if candidate:
                        return candidate
        elif isinstance(value, list):
            for item in value:
                candidate = cls._broker_named_result_url(
                    item,
                    names,
                    depth=depth + 1,
                    server_url=server_url,
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
        server_url: str | None = None,
    ) -> dict[str, Any]:
        raw_status = response.get("status")
        status = cls._normalize_broker_status(raw_status)
        video_url = cls._broker_result_url(response, server_url=server_url)
        last_frame_url = cls._broker_named_result_url(
            response,
            frozenset({"last_frame_url", "lastframe_url"}),
            server_url=server_url,
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
        task.update(_reference_leases.safe_queue_fields(response))
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
        if (
            response.get("resubmit_allowed") is False
            and error_code in {"submission_unknown", "provider_overdue"}
        ):
            # A Broker recovery window ending is not proof that the provider
            # render failed or never started. Keep this identity unresolved
            # even if that Broker row itself is labelled failed/terminal.
            task["status"] = "submission_unknown"
            task["terminal"] = False
        if "provider_job_id" in response:
            task["provider_task_registered"] = bool(
                str(response.get("provider_job_id") or "").strip()
            )
        if status in TERMINAL_FAILURE_STATUSES or response.get("error") or response.get("detail"):
            safe_detail = _broker_error_details(response)
            if safe_detail:
                task["error_details"] = safe_detail
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
        safe_detail = _broker_safe_error_text(task.get("error_details"))
        if safe_detail:
            parts.append("Server details: " + safe_detail)
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

    @staticmethod
    def _broker_unconfirmed_task_message(task: dict[str, Any], generation_id: str) -> str:
        safe_detail = _broker_safe_error_text(task.get("error_details"))
        return (
            f"FN AI Broker task {generation_id} still needs provider confirmation "
            f"({task.get('error_code') or 'submission_unknown'}). The Broker ended "
            "its recovery window without confirming a failed or unsubmitted render. "
            "The task ID was retained. Use Status > Refresh / Retrieve Result for "
            "this same task, or ask the Broker administrator to reconcile its provider "
            "record. A new explicit Run with Resume Task ID empty submits a separate "
            "render without cancelling the previous task; duplicate charges are possible."
        ) + ("\nServer details: " + safe_detail if safe_detail else "")

    def _set_broker_task_outputs(
        self,
        task: dict[str, Any],
        *,
        generation_id: str,
        status: str,
        preview_action: str = "none",
        requested_generation_id: str = "",
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
            "maintenance_queued",
            "maintenance_state",
            "submission_outcome_unknown",
        ):
            if name in task:
                provider_response[name] = task[name]
        safe_detail = _broker_safe_error_text(task.get("error_details"))
        if safe_detail:
            provider_response["error_details"] = safe_detail
        self.parameter_output_values["provider_response"] = provider_response
        self._retire_failed_resume_id(
            task, generation_id, requested_generation_id=requested_generation_id
        )
        self._publish_generation_preview(
            self._generation_preview_phase_for_status(status),
            generation_id=generation_id,
            action=preview_action,
        )

    def _retire_failed_resume_id(
        self,
        task: dict[str, Any],
        generation_id: str,
        *,
        requested_generation_id: str = "",
    ) -> None:
        """Release only the Resume field for this confirmed failed lookup.

        Keep the task ID, error and recovery checkpoint for audit/Refresh. This
        does not submit anything: the user must explicitly Run again. A validated
        lookup may promote a client key to a Broker job ID; either identity then
        refers to the same failed request. Never clear another manually entered ID.
        """
        if (
            getattr(self, "_hmb_node_deleted", False)
            or not generation_id
            or str(task.get("id") or "") != generation_id
            or str(task.get("status") or "").strip().lower() not in TERMINAL_FAILURE_STATUSES
            or (
                task.get("resubmit_allowed") is False
                and task.get("error_code") in {"submission_unknown", "provider_overdue"}
            )
        ):
            return
        resume_id = str(self.get_parameter_value("resume_generation_id") or "").strip()
        if resume_id and resume_id in {generation_id, requested_generation_id}:
            self.set_parameter_value("resume_generation_id", "")

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
        # The active Run/Refresh pins a bridge before result retrieval. Never
        # reselect today's UI origin while downloading an older paid task.
        bridge = self._broker_bridge_instance or self._get_broker_bridge()
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

        bridge = self._broker_bridge_instance or self._get_broker_bridge()
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
            accept="image/png,image/jpeg,application/octet-stream",
            max_bytes=MAX_LAST_FRAME_BYTES,
            media_label="Last-frame image",
        )
        try:
            return _normalize_returned_last_frame(image_bytes)
        except RuntimeError as exc:
            raise RuntimeError("Downloaded last frame is not a valid PNG image.") from exc

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
        self.parameter_output_values["VIDEO_OUT"] = previous_video
        self.parameter_output_values["video_url"] = self._native_local_video_preview_artifact(previous_video)
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
            # More than one cancellation can arrive while the upload/cleanup
            # thread is still running. Keep shielding every wait: cancelling
            # its Task does not stop that thread or its late temporary writes.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            with suppress(Exception, asyncio.CancelledError):
                task.result()
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

    def _build_generation_output_destination(self, *, draft: bool = False) -> Any:
        build = self._output_file.build_file
        parameters = inspect.signature(build).parameters
        accepts_index = "_index" in parameters or any(
            item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters.values()
        )
        # Draft adds its immutable task suffix before publication. Seed the
        # SDK's required save_node_output index before resolving that base;
        # ProjectFileParameter still preserves any connected destination policy.
        return build(_index=1) if draft and accepts_index else build()

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
        start_state_lock = threading.RLock()
        cancel_before_start = threading.Event()
        submission_started = False
        submission_prompt = getattr(self, "_hmb_agent_submission_prompt", None)
        reference_lease = getattr(self, "_hmb_reference_upload_lease_id", "")
        reference_origin = getattr(self, "_hmb_reference_upload_origin", "")
        reference_bridge = getattr(self, "_hmb_reference_upload_bridge", None)
        reference_client = getattr(self, "_hmb_reference_upload_client_id", "")

        def invoke_paced_submission() -> Any:
            nonlocal submission_started
            global _BROKER_SUBMISSION_LAST_STARTED
            # Project validation can await the engine loop after a reserved
            # slot. Keep that wait inside the cadence boundary so later slots
            # cannot overtake it and bunch their actual create starts together.
            with _BROKER_SUBMISSION_CADENCE_LOCK:
                _broker_wait_for_submission_slot()
                with start_state_lock:
                    if cancel_before_start.is_set() or not self._submission_start_is_authorized(
                        require_registered=False
                    ):
                        raise _SubmissionCancelledBeforeStart()
                    # The cadence gate can wait for several sibling submissions.
                    # Recheck the captured upstream run after that wait, before a
                    # billable request can begin. Manual inputs have no run token.
                    if getattr(self, "_hmb_expected_agent_result", None) is not None:
                        self._assert_agent_result_available(submission_prompt, allow_resume=False)
                    submission_started = True
                _BROKER_SUBMISSION_LAST_STARTED = time.monotonic()
            def check_before_http() -> None:
                with start_state_lock:
                    if cancel_before_start.is_set() or not self._submission_start_is_authorized(require_registered=False):
                        raise _SubmissionCancelledBeforeStart()
                    if getattr(self, "_hmb_expected_agent_result", None) is not None:
                        self._assert_agent_result_available(submission_prompt, allow_resume=False)

            def note_rejected() -> None:
                nonlocal submission_started
                with start_state_lock:
                    submission_started = False

            def note_started() -> None:
                nonlocal submission_started
                with start_state_lock:
                    check_before_http()
                    submission_started = True

            previous = getattr(_BROKER_NATIVE_SUBMISSION_CONTEXT, "callbacks", None)
            _BROKER_NATIVE_SUBMISSION_CONTEXT.callbacks = (check_before_http, note_rejected, note_started)
            try:
                # Capability refreshes happen here. The transport additionally
                # paces actual POSTs and rechecks this native run after waits.
                result = function(*args, **kwargs)
                self._observe_reference_lease(result, bridge=reference_bridge,
                    origin=reference_origin, requested_id=reference_client, identifier=reference_lease)
                return result
            finally:
                _BROKER_NATIVE_SUBMISSION_CONTEXT.callbacks = previous

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
                _write_generation_sidecar(published, metadata)
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
        recovery_at_download = self._generation_recovery_state()
        completed_origin = _generated_video_origin(
            recovery_at_download.get("generation_origin")
            if recovery_at_download.get("task_id") == generation_id else None
        )
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
        self.parameter_output_values["VIDEO_OUT"] = artifact
        self.parameter_output_values["video_url"] = self._native_local_video_preview_artifact(artifact)
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
        completed_draft_source = {}
        if recovery_at_download.get("draft_action") == DRAFT_ACTION_PREVIEW:
            completed_draft_source = _seedance_draft_source_value({
                "draft_job_id": generation_id,
                **recovery_at_download.get("draft_project", {}),
                "broker_server_url": recovery_at_download.get("broker_server_url"),
                "generation_origin": completed_origin,
                "owner_id": self._draft_owner_id(),
                "completed": True,
                "created_at_ms": recovery_at_download.get("draft_started_at_ms") or recovery_at_download.get("updated_at_ms"),
                "source_bindings": recovery_at_download.get("draft_source_bindings", {}),
            })
            if completed_draft_source:
                self._store_draft_source(completed_draft_source)
                current = self._draft_source_record()
                displayed_id = current.get("draft_job_id", "")
                self.set_parameter_value("draft_job_id", displayed_id, emit_change=False)
                with suppress(Exception):
                    self.publish_update_to_parameter("draft_job_id", displayed_id)
                # The retained one-use Draft final button advertises the next
                # action. Keep every authored generation setting unchanged;
                # its 1080p override belongs only to the explicit Final request.
        elif recovery_at_download.get("draft_action") == DRAFT_ACTION_FINAL:
            completed_draft_source = _seedance_draft_source_value(recovery_at_download.get("draft_source"))
            if completed_draft_source:
                completed_draft_source["final_job_id"] = generation_id
                self._store_draft_source(completed_draft_source)
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
                "_hmb_generation_origin": completed_origin,
                **({"_hmb_draft_source": completed_draft_source} if completed_draft_source else {}),
            },
        )
        # Stage the verified source before the persistence await. Normal workflow
        # saves retain this property; the journal retains the pending origin.
        self._record_completed_video_source(completed_origin, generation_id, saved)
        try:
            _review.update_case(generation_id, case_id=getattr(self, "_hmb_review_case_id", ""),
                                status="succeeded", output=saved.location,
                                stage_elapsed_seconds=getattr(self, "_hmb_review_stage_seconds", {}))
        except (OSError, ValueError, TypeError):
            logger.warning("Local completed-task evidence is unavailable.")
        await self._force_save_generation_recovery_checkpoint(
            required=False,
            reason="local_succeeded",
        )
        with suppress(Exception):
            self._update_parameter_visibility()
            self._sync_seedance_shot_widget(emit_change=True)
        self._submission_outcome_unknown = False
        if not self._runtime_node_is_live(require_registered=True):
            return
        with suppress(Exception):
            self._schedule_review_sync(generation_id)
        self._set_status_results(
            was_successful=True,
            result_details=(
                f"SUCCESS: FN AI Broker task {generation_id} succeeded.\n"
                f"Saved {effective_output_format.upper()}: {saved.location}"
            ),
        )

    async def _reuse_saved_generation_result(
        self, generation_id: str, checkpoint: dict[str, Any] | None = None,
    ) -> bool:
        """Restore an exact completed task without publishing its file again.

        A True result also consumes a callback made stale during validation;
        that callback must not fall through to downloading the old task.
        """
        checkpoint = deepcopy(checkpoint if checkpoint is not None else self._generation_recovery_state())
        if (checkpoint.get("stage") != "local_succeeded"
                or checkpoint.get("task_id") != generation_id):
            return False
        if (not self._runtime_node_is_live(require_registered=True)
                or bool(getattr(self, "is_cancellation_requested", False))):
            return True
        output_id = str(self.parameter_output_values.get("generation_id") or "").strip()
        if output_id and output_id != generation_id:
            raise RuntimeError("The saved video belongs to a different current task.")

        def saved_source() -> tuple[dict[str, Any], dict[str, Any]]:
            # Do not call the legacy source snapshot: it may adopt an artifact
            # using today's Shot selection instead of its completed-task owner.
            return (deepcopy(getattr(self, "_hmb_generated_video_source", {}) or {}),
                    deepcopy(self.get_parameter_value(GENERATED_VIDEO_SOURCE_PARAMETER) or {}))

        raw_sources = saved_source()
        def artifact_values() -> tuple[str, str]:
            return tuple(str(getattr(value, "value", value) or "") for value in (
                self.parameter_output_values.get("video_url"),
                self.parameter_output_values.get("VIDEO_OUT")))
        original_artifacts = artifact_values()
        sources = []
        for raw in raw_sources:
            if not raw:
                continue
            source = _generated_video_source_value(raw)
            if not source:
                raise RuntimeError("The saved video source is invalid.")
            sources.append(source)
        if sources and any(source != sources[0] for source in sources[1:]):
            raise RuntimeError("The saved video source records disagree.")
        if sources and sources[0].get("task_id") != generation_id:
            if _generated_video_origin(checkpoint.get("generation_origin")):
                raise RuntimeError("The saved video source does not match this completed task.")
            # Only intentionally keeps a previous Shot's routable source. It
            # is not evidence for this new result; verify Only's own persisted
            # destination + artifact below without changing that older source.
            sources = []

        def artifact_path(artifact: Any) -> Path | None:
            text = str(getattr(artifact, "value", artifact) or "").strip()
            if not text or urlparse(text).scheme in {"http", "https"}:
                return None
            resolved = File(text).resolve()
            return Path(str(getattr(resolved, "location", resolved))).resolve()

        if sources:
            path = Path(sources[0]["path"]).resolve()
        else:
            # Older/Only exports have no Shot provenance. Their persisted save
            # target and actual artifact must agree; the current output field
            # is editable and is never evidence for this older task.
            saved_target = str(checkpoint.get("output_file") or "").strip()
            current = self.parameter_output_values.get("VIDEO_OUT") or self.parameter_output_values.get("video_url")
            path = artifact_path(current)
            if (not saved_target or path is None
                    or path != artifact_path(saved_target)):
                raise RuntimeError("This completed task has no matching saved-video provenance.")

        def validate_saved_file() -> tuple[int, ...] | None:
            try:
                before = path.stat()
            except FileNotFoundError:
                return None  # Recover the same task's missing file normally.
            if not path.is_file() or before.st_size <= 0:
                raise RuntimeError("The saved video is empty or is not a regular file.")
            identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size,
                                     stat.st_mtime_ns, stat.st_ctime_ns)
            _validate_decodable_mp4_file(path)
            verified = path.stat()
            if identity(before) != identity(verified):
                raise RuntimeError("The saved video changed while it was being verified.")
            return identity(verified)

        validation_error = None
        file_identity = None
        try:
            file_identity = await asyncio.to_thread(validate_saved_file)
        except Exception as exc:
            validation_error = exc
        if (not self._runtime_node_is_live(require_registered=True)
                or bool(getattr(self, "is_cancellation_requested", False))
                or self._generation_recovery_state() != checkpoint
                or str(self.parameter_output_values.get("generation_id") or "").strip() != output_id
                or saved_source() != raw_sources
                or artifact_values() != original_artifacts):
            return True
        if validation_error is not None:
            raise validation_error
        if file_identity is None:
            return False

        artifact = self.parameter_output_values.get("VIDEO_OUT")
        if artifact_path(artifact) != path:
            artifact = self.parameter_output_values.get("video_url")
        if artifact_path(artifact) != path:
            artifact = VideoUrlArtifact(value=str(path), name=path.name)
        self.parameter_output_values["VIDEO_OUT"] = artifact
        self.parameter_output_values["video_url"] = self._native_local_video_preview_artifact(artifact)
        self._hmb_last_success_video = artifact
        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["generation_status"] = "succeeded"
        previous = self.parameter_output_values.get("provider_response")
        response = {"transport": "fn_ai_broker", "id": generation_id, "status": "succeeded"}
        if isinstance(previous, dict) and previous.get("id") == generation_id:
            if type(previous.get("provider_task_registered")) is bool:
                response["provider_task_registered"] = previous["provider_task_registered"]
        self.parameter_output_values["provider_response"] = response
        self._submission_outcome_unknown = False
        self._publish_generation_preview("succeeded", generation_id=generation_id, action="none")
        self._set_status_results(
            was_successful=True,
            result_details=(f"SUCCESS: FN AI Broker task {generation_id} succeeded.\n"
                            f"Verified existing saved video: {path}"),
        )
        return True

    async def _refresh_async(self) -> None:
        """Refresh one Broker job without ever creating a replacement task."""
        if _my_box_node.is_selected(self) or self._hmb_my_box_existing_task():
            await self._hmb_my_box_controller().run(refresh=True)
            return
        if not self._runtime_node_is_live(require_registered=True):
            return
        # A running generation already owns automatic polling.  Mixing a
        # manual refresh into it can race output publication even though both
        # operations target the same server job.
        if self._generation_run_active.is_set():
            return
        generation_id = ""
        operation_phase = "broker_lookup"
        try:
            generation_id = self._authoritative_existing_generation_id()
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
            broker_origin = self._broker_server_for_task(generation_id)
            bridge = await self._ensure_broker_connected(server_url=broker_origin)
            if not self._runtime_node_is_live(require_registered=True):
                return
            if self._authoritative_existing_generation_id() != generation_id:
                return
            # Refresh retrieves status for this authoritative job only.  In
            # particular, an uncertain submission never replays
            # generate_seedance (the create-task request) here.
            response = await asyncio.to_thread(
                bridge.refresh_job,
                generation_id,
                timeout=300,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            if self._authoritative_existing_generation_id() != generation_id:
                return
            task = self._normalize_broker_task(
                response,
                fallback_job_id=generation_id,
                server_url=broker_origin,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            status = str(task["status"])
            recovery_contract = self._generation_recovery_state()
            requested_generation_id = generation_id
            # Retrieval is not a new Final submission. In particular an
            # authored Final menu, expired source or consumed final_request_id
            # must not prevent downloading this already accepted task.
            same_task = recovery_contract.get("task_id") == requested_generation_id
            raw_model = str((recovery_contract.get("model_id") if same_task else "")
                            or self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0)
            refresh_params = {
                "model_id": MODEL_ID_ALIASES.get(raw_model, raw_model),
                "output_format": (recovery_contract.get("output_format") if same_task else "")
                    or self.get_parameter_value("output_format") or DEFAULT_OUTPUT_FORMAT,
                "return_last_frame": bool(recovery_contract.get("return_last_frame")) if same_task
                    else bool(self.get_parameter_value("return_last_frame")),
                "_hmb_broker_server_url": broker_origin,
            }
            refresh_params["_hmb_generation_origin"] = _generated_video_origin(
                recovery_contract.get("generation_origin")
                if recovery_contract.get("task_id") == requested_generation_id else None
            )
            resolved_generation_id = str(task["id"])
            preserve_local_success = bool(
                recovery_contract.get("stage") == "local_succeeded"
                and recovery_contract.get("task_id") == requested_generation_id
            )
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
            await self._run_blocking_generation_stage(self._observe_reference_lease_response,
                response, bridge, broker_origin, requested_generation_id,
                recovery_contract.get("reference_lease_id", ""))
            if preserve_local_success:
                operation_phase = "local_validation"
                if await self._reuse_saved_generation_result(generation_id, recovery_contract):
                    return
            if status == "succeeded":
                operation_phase = "local_result"
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
                requested_generation_id=requested_generation_id,
                preview_action=(
                    "refresh_existing"
                    if status in {"queued", "running", "submission_unknown"}
                    else "none"
                ),
            )
            if not preserve_local_success:
                self._set_generation_recovery_checkpoint(
                    stage=(
                        "remote_succeeded"
                        if status == "succeeded"
                        else "submission_unknown"
                        if status == "submission_unknown"
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
            if status == "submission_unknown":
                self._set_status_results(
                    was_successful=False,
                    result_details=self._broker_unconfirmed_task_message(task, generation_id),
                )
                return
            if status in TERMINAL_FAILURE_STATUSES:
                self._set_status_results(
                    was_successful=False,
                    result_details=self._broker_terminal_failure_message(
                        task, generation_id
                    ) + " The task is confirmed terminal. The next explicit Run "
                    "can start a new render; Refresh did not submit one.",
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
            if bool(getattr(self, "is_cancellation_requested", False)):
                return
            if generation_id and self._authoritative_existing_generation_id() != generation_id:
                return
            if operation_phase != "local_validation" and generation_id:
                # A failed GET cannot undo an independently verified local
                # success. This path never creates a replacement server task.
                try:
                    if await self._reuse_saved_generation_result(generation_id):
                        return
                except Exception as local_exc:
                    exc = local_exc
                    operation_phase = "local_result"
            recovery_checkpoint = self._generation_recovery_state()
            if operation_phase in {"local_result", "local_validation"}:
                self._publish_generation_preview(
                    "failed", generation_id=generation_id, action="refresh_existing",
                )
                self._set_status_results(
                    was_successful=False,
                    result_details=(
                        f"Task result retrieval / local save failed ({type(exc).__name__}). "
                        f"Existing task ID: {generation_id or 'ID'}. "
                        "Check the saved video, destination permissions and available disk space. "
                        "Existing files were preserved; no new render was submitted. "
                        "Refresh / Retrieve Result checks this same task."
                    ),
                )
                return
            missing_client_request = bool(
                isinstance(exc, _BrokerError)
                and exc.status_code in {404, 410}
                and recovery_checkpoint.get("task_identity") == "client_request"
                and recovery_checkpoint.get("task_id") == generation_id
            )
            if missing_client_request:
                # A bare 404/410 can be a different account/server, an older
                # Broker without client-key lookup, or a missing audit record.
                # It does not prove the provider never accepted this request.
                # A structured expired task was handled above as terminal.
                self._publish_generation_preview(
                    "submission_unknown", generation_id=generation_id,
                    action="refresh_existing",
                )
                self._set_status_results(
                    was_successful=False,
                    result_details=(
                        f"The Broker could not find client request {generation_id} "
                        f"(HTTP {exc.status_code}). This alone does not confirm that "
                        "no render was accepted. The saved ID was retained. Check "
                        "the same Broker server and login used for submission, then "
                        "click Status > Refresh / Retrieve Result. If it still cannot "
                        "be found, ask the Broker administrator to confirm the request's "
                        "provider-side outcome; no replacement render was submitted."
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
                or self._hmb_draft_finalize_pending
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
        controller = getattr(self, "_hmb_my_box_controller_instance", None)
        if controller is not None:
            controller.invalidate(deleted=True)
        if not bool(getattr(self, "_hmb_node_deleted", False)):
            self._hmb_node_deleted = True
            draft_status_future = getattr(self, "_hmb_draft_final_status_future", None)
            if draft_status_future is not None:
                draft_status_future.cancel()
            final_future = getattr(self, "_hmb_draft_finalize_future", None)
            if final_future is not None:
                final_future.cancel()
            self._hmb_review_sync_epoch = int(getattr(self, "_hmb_review_sync_epoch", 0)) + 1
            with self._generation_refresh_lock:
                self._generation_run_active.clear()
                self._generation_refresh_running = False
            with self._broker_action_lock:
                self._broker_action_running = False
            for task in tuple(self._detached_submission_tasks):
                with suppress(Exception):
                    task.cancel()
            self._detached_submission_tasks.clear()
            self._retire_deleted_generation_recovery()
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
        self._hmb_project_selection_guard = None
        self._hmb_review_case_id = ""
        self._hmb_review_inputs = {}
        self._hmb_review_stage = ""
        self._hmb_review_stage_started = time.monotonic()
        self._hmb_review_stage_seconds = {}
        self._hmb_generation_run_origin = (
            {} if str(self.get_parameter_value("resume_generation_id") or "").strip()
            else self._capture_generated_video_origin()
        )
        self._hmb_reference_upload_lease_id = self._generation_recovery_state().get("reference_lease_id", "")
        await self._run_blocking_generation_stage(
            self._cleanup_temporary_video_uploads
        )
        self._submission_outcome_unknown = False
        try:
            await self._process_generation_impl()
        finally:
            self._hmb_project_selection_guard = None
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
        recovery_before_run = self._generation_recovery_state()
        if (requested_resume_id
                and await self._reuse_saved_generation_result(requested_resume_id, recovery_before_run)):
            return
        if (
            requested_resume_id
            and requested_resume_id == recovery_before_run.get("task_id")
            and not self._generation_recovery_blocks_new_submission()
        ):
            # Saved pre-patch workflows can still contain a Resume ID whose
            # confirmed failure was already recorded. Run starts fresh; Refresh
            # remains available for inspecting that preserved terminal record.
            self._retire_failed_resume_id(
                {
                    "id": requested_resume_id,
                    "status": recovery_before_run.get("status"),
                },
                requested_resume_id,
            )
            requested_resume_id = str(
                self.get_parameter_value("resume_generation_id") or ""
            ).strip()
        if not requested_resume_id or (
            self._generation_recovery_blocks_new_submission()
            and requested_resume_id != recovery_before_run.get("task_id")
        ):
            # Run without an explicit Resume ID means a fresh render, even if
            # an older request is still unknown/running remotely. This is not
            # a retry loop: one new client key and at most one create per Run.
            # An explicit Resume remains a same-task, non-billable lookup.
            self._assert_new_submission_is_safe(explicit_run=not requested_resume_id)
        self._set_safe_defaults()
        self._begin_generation_preview()
        self._set_generation_status("resolving_inputs", generation_id="")
        params = self._get_parameters()
        self._hmb_project_selection_guard = None
        draft_action = params.get("draft_action", DRAFT_ACTION_OFF)
        self._hmb_active_draft_action = draft_action
        draft_final = draft_action == DRAFT_ACTION_FINAL
        if not params["resume_generation_id"] and not draft_final:
            # Resolve and validate the selected ImageAsset/VideoPicker Shot
            # before destination preparation, authentication, uploads, or a
            # billable Broker create-task request. Prompt text remains manual.
            params = self._resolve_exact_shot_generation_inputs(params)
            if not isinstance(self, _HMBWebRerenderExecution):
                selection = params.get("_hmb_imageasset_project_selection")
                if not isinstance(selection, dict):
                    raise ValueError("A verified selected ImageAsset project is required before rendering.")
                self._assert_imageasset_project_selection(selection)
                self._hmb_project_selection_guard = {"selection": deepcopy(selection),
                    "loop": asyncio.get_running_loop(), "thread": threading.get_ident()}
            resolved_origin = self._capture_generated_video_origin()
            captured_origin = _generated_video_origin(getattr(self, "_hmb_generation_run_origin", None))
            if captured_origin and captured_origin != resolved_origin:
                raise ValueError("The selected Shot changed before generation inputs were prepared. Run the selected Shot again.")
            params["_hmb_generation_origin"] = captured_origin or resolved_origin
            if isinstance(self, _HMBWebRerenderExecution):
                params["_hmb_shot_hierarchy"] = deepcopy(self._web_params.get("_hmb_shot_hierarchy", {}))
            else:
                origin = params["_hmb_generation_origin"]
                params["_hmb_shot_hierarchy"] = _shot_routing.capture_shot_hierarchy(
                    self, origin.get("channel_uuid", ""), origin.get("shot_uuid", "")
                )
        else:
            params["_hmb_generation_origin"] = _generated_video_origin(
                params.get("_hmb_draft_source", {}).get("generation_origin") if draft_final and not params["resume_generation_id"] else
                recovery_before_run.get("generation_origin")
                if recovery_before_run.get("task_id") == params["resume_generation_id"] else None
            )
            params["_hmb_shot_hierarchy"] = deepcopy(recovery_before_run.get("shot_hierarchy", {}))
        self._validate_parameters(params)
        resume_generation_id = params["resume_generation_id"]
        decode_verifier: _MP4DecodeVerifier | None = None

        advanced_seedance_v2 = bool(
            not resume_generation_id
            and not draft_final
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
        prevalidated_destination = None
        if (not resume_generation_id and draft_action == DRAFT_ACTION_OFF
                and params.get("output_format") == DEFAULT_OUTPUT_FORMAT):
            # MP4 cannot fall back to another format. Preserve the established
            # local output rejection before Broker authentication for this path.
            prevalidated_destination = self._build_generation_output_destination()
            self._preflight_output_destination(prevalidated_destination, DEFAULT_OUTPUT_FORMAT)

        self._set_generation_status("connecting_broker", generation_id="")
        broker_origin = (
            self._broker_server_for_task(
                resume_generation_id, checkpoint=recovery_before_run,
            ) if resume_generation_id else self._selected_broker_server_url()
        )
        draft_source = _seedance_draft_source_value(params.get("_hmb_draft_source"))
        if (not resume_generation_id and draft_final
                and draft_source.get("draft_job_id") == params.get("draft_job_id")):
            broker_origin = draft_source["broker_server_url"]
        bridge = await self._ensure_broker_connected(server_url=broker_origin)
        params["_hmb_broker_server_url"] = broker_origin
        if not resume_generation_id:
            discover_queue = getattr(bridge, "queue_admission", None)
            admission = await asyncio.to_thread(discover_queue, refresh=True) if callable(discover_queue) else None
            if admission is not None:
                selected_project = params.get("_hmb_imageasset_project_selection")
                operation = "draft_final" if draft_final else "only" if isinstance(selected_project, dict) and selected_project.get("schema") == ONLY_PROJECT_SELECTION_SCHEMA else "video"
                params["_hmb_queue_only_headers"] = bridge._queue_admission_headers(admission, operation)
        if not self._runtime_node_is_live(require_registered=True):
            return
        if draft_final and not resume_generation_id and not isinstance(self, _HMBWebRerenderExecution):
            state = await self._query_draft_final_server_state(draft_source, bridge=bridge)
            if state.get("state") != "available" or state.get("eligible") is not True:
                raise _BrokerProtocolError(
                    "This Draft Final is already reserved, unavailable, or awaiting confirmation. "
                    "Review the existing Draft/Final task on the web; no new render was submitted."
                )
        selection = params.get("_hmb_imageasset_project_selection")
        if (not resume_generation_id and not draft_final and isinstance(selection, dict)
                and selection.get("schema") == ONLY_PROJECT_SELECTION_SCHEMA):
            await asyncio.to_thread(bridge.require_generation_project_selection,
                                    ONLY_PROJECT_SELECTION_SCHEMA, timeout=5.0)
            self._assert_operation_project_selection()
        authored_output_format = str(params.get("output_format") or DEFAULT_OUTPUT_FORMAT)
        if not resume_generation_id and draft_action != DRAFT_ACTION_OFF:
            params["output_format"] = await asyncio.to_thread(
                bridge.require_seedance_draft_features, timeout=10.0,
                output_format=str(params.get("output_format") or DEFAULT_OUTPUT_FORMAT),
                allow_output_fallback=True,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
        if advanced_seedance_v2:
            # Task-declared 2.5 modes must be advertised by the authenticated
            # Broker before any reference media is uploaded or any billable
            # create-task request can be made. The legacy Text/Frame v1 contract
            # returns immediately.
            params["output_format"] = await asyncio.to_thread(
                bridge.require_seedance_features,
                model_id=str(params["model_id"]),
                task=str(params.get(TASK_PARAMETER) or TASK_REFERENCE_TO_VIDEO),
                output_format=str(
                    params.get("output_format") or DEFAULT_OUTPUT_FORMAT
                ),
                return_last_frame=bool(params.get("return_last_frame")),
                timeout=10.0,
                allow_output_fallback=draft_action == DRAFT_ACTION_OFF,
                refresh=True,
                draft=draft_action != DRAFT_ACTION_OFF,
            )
            if not self._runtime_node_is_live(require_registered=True):
                return

        if not resume_generation_id and params["output_format"] != authored_output_format:
            logger.info("%s using provider-supported %s for this request and save target; authored %s is unchanged.",
                        self.name, str(params["output_format"]).upper(), authored_output_format.upper())
        # Freeze the request and save target together only after authenticated
        # format selection. Resume uses its original format and never resolves anew.
        self._set_generation_status("preparing_output", generation_id="")
        resume_draft_checkpoint = bool(
            resume_generation_id and recovery_before_run.get("task_id") == resume_generation_id
            and recovery_before_run.get("draft_action") in {DRAFT_ACTION_PREVIEW, DRAFT_ACTION_FINAL}
        )
        resume_output_checkpoint = bool(
            resume_generation_id and recovery_before_run.get("task_id") == resume_generation_id
            and recovery_before_run.get("output_file")
        )
        if resume_draft_checkpoint and not recovery_before_run.get("output_file"):
            raise _BrokerProtocolError("The saved Draft output path is unavailable. No new render was submitted.")
        if resume_output_checkpoint:
            if not recovery_before_run.get("output_file"):
                raise _BrokerProtocolError("The saved Draft output path is unavailable. No new render was submitted.")
            destination = self._build_recovery_output_destination(recovery_before_run)
            params["_hmb_output_file"] = recovery_before_run["output_file"]
            saved_format = str(recovery_before_run.get("output_format") or "").strip().lower()
            if saved_format not in OUTPUT_FORMAT_CHOICES:
                saved_suffix = Path(recovery_before_run["output_file"]).suffix.lower().lstrip(".")
                saved_format = saved_suffix if saved_suffix in OUTPUT_FORMAT_CHOICES else DEFAULT_OUTPUT_FORMAT
            params["output_format"] = saved_format
            if resume_draft_checkpoint:
                params["return_last_frame"] = False
            elif type(recovery_before_run.get("return_last_frame")) is bool:
                params["return_last_frame"] = recovery_before_run["return_last_frame"]
        else:
            destination = (prevalidated_destination if prevalidated_destination is not None else
                           self._build_generation_output_destination(draft=draft_action != DRAFT_ACTION_OFF))
        draft_client_request_id = ""
        if not resume_generation_id and draft_action != DRAFT_ACTION_OFF:
            context = self._active_draft_final_context()
            draft_client_request_id = (context["client_request_id"] if context is not None else
                _seedance_draft_final_request_id(params["draft_job_id"]) if draft_action == DRAFT_ACTION_FINAL else
                self._new_generation_client_request_id())
            if draft_action == DRAFT_ACTION_PREVIEW:
                params["_hmb_draft_started_at_ms"] = int(time.time() * 1000)
            draft_output_format = str(params["output_format"])
            base = self._normalized_video_output_path(destination.resolve(), draft_output_format)
            phase = "draft480p" if draft_action == DRAFT_ACTION_PREVIEW else "final1080p"
            unique_path = base.with_name(f"{base.stem}-{phase}-{draft_client_request_id}.{draft_output_format}")
            destination = _SeedanceDraftOutputDestination(str(unique_path))
            params["_hmb_output_file"] = str(unique_path)
        preflight_output = self._preflight_output_destination(
            destination,
            str(params.get("output_format") or DEFAULT_OUTPUT_FORMAT),
        )
        if not resume_generation_id and draft_action == DRAFT_ACTION_OFF:
            destination = _SeedanceResolvedOutputDestination(
                destination, str(preflight_output),
            )
            params["_hmb_output_file"] = str(preflight_output)

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
                task_identity=(
                    "client_request"
                    if recovery_before_run.get("task_id") == generation_id
                    and recovery_before_run.get("task_identity") == "client_request"
                    else "broker_task"
                ),
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
            if not draft_final:
                self._assert_operation_project_selection()
                try:
                    self._hmb_review_inputs = await self._run_blocking_generation_stage(
                        _review.capture_inputs, params,
                    )
                except (OSError, ValueError, TypeError):
                    self._hmb_review_inputs = {"status": "capture_unavailable"}
                params = await self._run_blocking_generation_stage(
                    self._prepare_video_references_for_run,
                    params,
                )
                self._assert_operation_project_selection()
            if not self._runtime_node_is_live(require_registered=True):
                return
            payload = await self._run_blocking_generation_stage(
                self._build_broker_payload,
                params,
            )
            self._assert_agent_result_available(str(params.get("prompt") or ""), allow_resume=False)
            client_request_id = draft_client_request_id or self._new_generation_client_request_id()
            payload["client_request_id"] = client_request_id
            await self._run_blocking_generation_stage(
                self._start_review_case, client_request_id, str(payload.get("prompt") or ""),
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            params["_hmb_reference_upload_lease_id"] = await self._run_blocking_generation_stage(
                self._bind_temporary_reference_lease, bridge, broker_origin, client_request_id)
            self._set_broker_task_outputs(
                {"id": client_request_id, "status": "submitting"},
                generation_id=client_request_id,
                status="submitting",
            )
            if draft_final:
                final_source = _seedance_draft_source_value(params.get("_hmb_draft_source"))
                if final_source:
                    final_source["final_request_id"] = client_request_id
                    params["_hmb_draft_source"] = final_source
                    self._store_draft_source(final_source)
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
                # blocks a corrected retry after the local journal write is
                # fixed. Atomic replacement failed before persisting this
                # mutation; the user's workflow is never written by HMB.
                self.parameter_output_values["generation_id"] = ""
                self.parameter_output_values["provider_response"] = None
                self._release_unsubmitted_draft_reservation()
                await self._run_blocking_generation_stage(self._reject_unsubmitted_reference_lease)
                self._clear_generation_recovery_checkpoint()
                self._set_generation_status(
                    "failed",
                    generation_id="",
                    preview_action="none",
                )
                raise
            try:
                self._assert_agent_result_available(str(params.get("prompt") or ""), allow_resume=False)
            except _AgentResultUnavailable:
                await self._discard_unsent_generation_checkpoint(reason="agent_result_changed_before_submission")
                raise
            try:
                authorized = self._submission_start_is_authorized(require_registered=True)
            except _ProjectSelectionChanged:
                await self._discard_unsent_generation_checkpoint(reason="project_selection_changed_before_submission")
                raise
            if not authorized:
                await self._discard_unsent_generation_checkpoint(
                    reason="cancelled_after_pre_submit_save",
                )
                raise asyncio.CancelledError(
                    "Seedance submission was cancelled before the create request started."
                )
            try:
                import _hmb_queue_admission as queue
                response, submission_cancelled = await self._await_submission_result(
                    bridge.generate_seedance,
                    payload,
                    timeout=min(float(timeout), 1200.0),
                    **({"queue_only_headers": params["_hmb_queue_only_headers"]} if params.get("_hmb_queue_only_headers") else {}),
                )
                try:
                    if not isinstance(response, dict):
                        raise _BrokerProtocolError("FN AI Broker returned an invalid task response.")
                    task = self._normalize_broker_task(
                        response, server_url=broker_origin,
                    )
                except _BrokerError as exc:
                    # Keep the pre-submit client key and reference uploads if
                    # the accepted response lacks a usable task identity/status.
                    # This is not a rejection and must use the existing unknown
                    # submission checkpoint/Refresh path, never a second POST.
                    raise _BrokerProtocolError(
                        "FN AI Broker returned an incomplete task response. "
                        "Submission could not be confirmed; use Refresh / Retrieve Result.",
                        submission_outcome_unknown=True,
                    ) from exc
            except queue.QueueAdmissionError:
                # This local exception can only originate before the HTTP
                # create boundary. It is never inferred from response JSON.
                await self._discard_unsent_generation_checkpoint(reason="queue_admission_changed_before_submission")
                raise
            except _ProjectSelectionChanged:
                await self._discard_unsent_generation_checkpoint(reason="project_selection_changed_at_submission_gate")
                raise
            except _AgentResultUnavailable:
                await self._discard_unsent_generation_checkpoint(
                    reason="agent_result_changed_at_submission_gate",
                )
                raise
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
                if getattr(exc, "_hmb_web_submission_not_started", False) is True:
                    # The web prepared handshake failed before the normal
                    # create transport. Its provisional key is not a task.
                    await self._discard_unsent_generation_checkpoint(
                        reason="web_prepared_not_submitted",
                    )
                    self._set_generation_status("failed", generation_id="", preview_action="none")
                elif exc.submission_outcome_unknown:
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
                    # A gateway 404/5xx is not storage-release evidence, even
                    # when the legacy UI classifies that HTTP as a rejection.
                    if exc.status_code in {400, 401, 403, 409, 413, 422, 429}:
                        await self._run_blocking_generation_stage(self._reject_unsubmitted_reference_lease)
                    self._release_unsubmitted_draft_reservation()
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
                    "Retrieve Result to check this same ID. A new explicit Run submits "
                    "a separate render and may incur duplicate charges."
                )

            requested_generation_id = generation_id
            response = await asyncio.to_thread(
                bridge.refresh_job,
                generation_id,
                timeout=min(300.0, max(1.0, deadline - now)),
            )
            if not self._runtime_node_is_live(require_registered=True):
                return
            task = self._normalize_broker_task(
                response,
                fallback_job_id=generation_id,
                server_url=broker_origin,
            )
            provisional = self._generation_recovery_state()
            resolving_client_request = bool(
                provisional.get("task_identity") == "client_request"
                and provisional.get("task_id") == generation_id
            )
            if str(task["id"]) != generation_id and not resolving_client_request:
                raise _BrokerError("FN AI Broker returned a different task ID.")
            await self._run_blocking_generation_stage(self._observe_reference_lease_response,
                response, bridge, broker_origin, requested_generation_id,
                provisional.get("reference_lease_id", ""))
            if resolving_client_request:
                # Resume Task ID can explicitly resume the saved client key.
                # Only its first successful same-key lookup may promote that
                # provisional identity to the canonical Broker job ID.
                generation_id = str(task["id"])
                self._set_generation_recovery_checkpoint(
                    stage="accepted", task_id=generation_id,
                    task_identity="broker_task", status=str(task["status"]),
                    params=params,
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False, reason="resume_client_request_resolved",
                )
            status = str(task["status"])
            if not self._runtime_node_is_live(require_registered=True):
                return
            self._set_broker_task_outputs(
                task,
                generation_id=generation_id,
                status=status,
                requested_generation_id=requested_generation_id,
            )
            logger.info(
                "%s FN AI Broker task %s status: %s",
                self.name,
                generation_id,
                status,
            )
            if status == "submission_unknown":
                self._submission_outcome_unknown = True
                self._set_generation_recovery_checkpoint(
                    stage="submission_unknown", task_id=generation_id,
                    task_identity="broker_task", status=status, params=params,
                )
                await self._force_save_generation_recovery_checkpoint(
                    required=False, reason="provider_confirmation_required",
                )
                raise RuntimeError(self._broker_unconfirmed_task_message(task, generation_id))
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


    def _new_generation_client_request_id(self) -> str:
        """Ordinary Run always creates a new intent; web requests override privately."""
        return "hmb-" + uuid4().hex

    def _hmb_web_rerender_capture_inputs(self) -> dict[str, Any]:
        """Read a local execution snapshot without editing any retained node.

        This private value stays inside the engine. It is not a browser request
        body and contains native source references which the public readiness
        projection intentionally excludes. Authored Prompt text is never read.
        """
        if not self._runtime_node_is_live(require_registered=True):
            raise RuntimeError("The connected Generator is no longer available.")
        from _hmb_connection_management import target_has_suspended_role
        if target_has_suspended_role(self):
            raise RuntimeError("[HMB_CONNECTION_DETACHED] Restore the Generator connections before requesting a web rerender.")
        agent = self._manual_agent_prompt_source()
        if agent is None or not callable(getattr(agent, "_hmb_run_web_rerender", None)):
            raise RuntimeError("Connect an HMB Agent before requesting a web rerender.")
        if target_has_suspended_role(agent):
            raise RuntimeError("[HMB_CONNECTION_DETACHED] Restore the Agent connections before requesting a web rerender.")
        view = _HMBWebRerenderExecution.read_view(self)
        params = view._get_parameters()
        params["resume_generation_id"] = ""
        params = view._resolve_exact_shot_generation_inputs(params)
        params.pop("prompt", None)
        params["_hmb_generation_origin"] = deepcopy(self._capture_generated_video_origin())
        origin = params["_hmb_generation_origin"]
        params["_hmb_shot_hierarchy"] = _shot_routing.capture_shot_hierarchy(
            self, origin.get("channel_uuid", ""), origin.get("shot_uuid", "")
        )
        params["_hmb_broker_server_url"] = self._selected_broker_server_url()
        # Validation needs text, but neither original Prompt text nor this
        # non-submitted sentinel is put into the returned execution snapshot.
        view._validate_parameters(dict(params, prompt="Web rerender readiness"))
        try:
            flow_name = str(GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name))
        except Exception as exc:
            raise RuntimeError("The Generator workflow binding is unavailable.") from exc
        target = {
            "flow_name": flow_name,
            "node_name": str(self.name),
            "runtime_instance_id": str(self._hmb_generated_source_instance_id),
            "session_epoch": _WEB_RERENDER_SESSION_EPOCH,
            "agent_name": str(agent.name),
            "agent_instance_id": str(id(agent)),
            "project_id": params["project_id"],
            "shot_selection": {key: _web_rerender_plain(self.get_parameter_value(key)) for key in (
                SHOT_SELECTOR_PARAMETER, SHOT_CHANNEL_UUID_PARAMETER, SHOT_UUID_PARAMETER,
                SHOT_NUMBER_PARAMETER, SHOT_NAME_PARAMETER)},
        }
        source_bindings = []
        for port, source_port in (
            (SHOT_ASSET_INPUT_PARAMETER, "SHOT_ASSET_OUT"),
            (SHOT_PICKER_INPUT_PARAMETER, "SHOT_PICKER_OUT"),
            (SHOT_FINISH_LOOK_INPUT_PARAMETER, "SHOT_FINISH_LOOK_OUT"),
        ):
            source = self._exact_incoming_source(port, source_port, required=False)
            if source is not None:
                source_bindings.append({"port": port, "source": str(source.name), "instance": str(id(source))})
        references = _web_rerender_reference_identity(params)
        digest = _web_rerender_digest({"target": target, "params": params,
                                      "source_bindings": source_bindings, "references": references,
                                      "source_snapshots": view._web_source_snapshots})
        images = list(params.get("reference_images") or [])
        if params.get("first_frame") is not None:
            images.insert(0, params["first_frame"])
        if params.get("last_frame") is not None:
            images.append(params["last_frame"])
        media = {"schema": "hmb-agent-reference-media", "version": 1,
                 "images": [{"token": f"@image{index + 1}", "source": str(self._coerce_reference_value(value)),
                             "source_type": "generator_reference"} for index, value in enumerate(images)],
                 "videos": [{"token": f"@video{index + 1}", "source": str(self._coerce_reference_value(value)),
                             "source_type": "generator_reference"}
                            for index, value in enumerate(params.get("video_references") or [])]}
        origin = params.get("_hmb_generation_origin") or {}
        for kind, records_key, destination in (("image_asset", "ordered_assets", media["images"]),
                                               ("video_picker", "ordered_videos", media["videos"])):
            raw = view._web_source_snapshots.get(kind, {})
            shot = next((row for row in raw.get("shots", []) if row.get("shot_uuid") == origin.get("shot_uuid")), {})
            metadata = {row.get("source_uid"): row.get("metadata", {}) for row in raw.get(records_key, [])}
            for record, uid in zip(destination, shot.get("selected_source_uids", [])):
                info = deepcopy(metadata.get(uid) or {})
                record["identity"] = {"source_uid": uid}
                for key in ("frame_metadata", "frame_domain", "source_type", "image_main_type", "image_sub_type",
                            "video_main_type", "video_sub_type", "reference_scope", "frame_ranges", "control_role"):
                    if key in info:
                        record[key] = info[key]
                role = str(info.get("generation_role") or info.get("video_role") or "").lower()
                if kind == "video_picker" and "video_sub_type" not in record:
                    subtype = {"original": "Original Preview", "mask": "Mask", "depth": "Depth",
                               "motion_guide": "Motion Guide"}.get(role)
                    if subtype:
                        record["video_sub_type"] = subtype
        return {"schema": "hmb-web-rerender-generator-snapshot", "version": 1,
                "project": {key: params[key] for key in ("project_id", "project_name")},
                "target": target, "params": deepcopy(params), "media_snapshot": deepcopy(media),
                "generation_settings": {key: deepcopy(params[key]) for key in _review.SETTINGS if key in params},
                "agent_name": str(agent.name), "source_bindings": source_bindings,
                "references": references, "binding_fingerprint": digest}

    def _hmb_web_rerender_readiness(self) -> dict[str, Any]:
        """Bounded local readiness; the worker adds auth, policy and lease checks."""
        reason = ""
        try:
            with self._generation_refresh_lock:
                if self._generation_run_active.is_set() or self._generation_refresh_running or self._hmb_draft_finalize_pending:
                    raise RuntimeError("The connected Generator is busy.")
            if self._hmb_web_rerender_recovery_blocked():
                raise RuntimeError("An earlier Generator submission still requires confirmation.")
            snapshot = self._hmb_web_rerender_capture_inputs()
        except Exception as exc:
            reason = str(exc)[:240]
            snapshot = {}
        return {"ready": not reason, "reason": reason, "target": snapshot.get("target", {}),
                "binding_fingerprint": snapshot.get("binding_fingerprint", "")}

    def _hmb_web_rerender_recovery_blocked(self) -> bool:
        """Read readiness without journal adoption or legacy artifact filesystem IO."""
        checkpoint = _seedance_recovery_value(self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER))
        task_id = str(checkpoint.get("task_id") or self.parameter_output_values.get("generation_id") or "")
        if not task_id:
            return False
        status = str(checkpoint.get("status") or self.parameter_output_values.get("generation_status") or "")
        response = self.parameter_output_values.get("provider_response")
        if status == "submission_unknown" or (isinstance(response, dict) and response.get("id") == task_id
                and response.get("resubmit_allowed") is False):
            return True
        if checkpoint.get("stage") == "local_succeeded" or checkpoint.get("terminal") or status in TERMINAL_FAILURE_STATUSES:
            return False
        # Legacy completed outputs can be ready without touching their paths.
        # The new operation has separate media preflight and its own output path.
        return not (not checkpoint.get("stage") and status in BROKER_SUCCESS_STATUSES
                    and self._generation_artifact_is_present(self.parameter_output_values.get("VIDEO_OUT")
                        or self.parameter_output_values.get("video_url")))

    @asynccontextmanager
    async def _hmb_web_rerender_claim(self, snapshot: dict[str, Any]):
        """Serialize web Agent + render with native Run and native Refresh."""
        from _hmb_connection_management import execution_reservation
        claim = None
        try:
            # Connection changes and activation share one short reservation.
            # Never retain it while awaiting the Agent, uploads, or rendering.
            with execution_reservation():
                with self._generation_refresh_lock:
                    if self._generation_run_active.is_set() or self._generation_refresh_running or self._hmb_draft_finalize_pending:
                        raise RuntimeError("The connected Generator is busy.")
                    if self._hmb_web_rerender_recovery_blocked():
                        raise RuntimeError("An earlier Generator submission still requires confirmation.")
                    claim = _HMBWebRerenderClaim(self, deepcopy(snapshot))
                    self._hmb_web_rerender_active_claim = claim
                    self._generation_run_active.set()
                    self._hmb_active_draft_action = DRAFT_ACTION_OFF
                self._hmb_web_rerender_validate_claim(claim)
            yield claim
        finally:
            if claim is not None:
                with execution_reservation():
                    with self._generation_refresh_lock:
                        if getattr(self, "_hmb_web_rerender_active_claim", None) is claim:
                            self._hmb_web_rerender_active_claim = None
                            self._generation_run_active.clear()
                        claim.active = False

    def _hmb_web_rerender_validate_claim(self, claim: Any) -> None:
        if (not isinstance(claim, _HMBWebRerenderClaim) or claim.owner is not self
                or not claim.active or getattr(self, "_hmb_web_rerender_active_claim", None) is not claim):
            raise RuntimeError("The web rerender reservation is no longer valid.")
        current = self._hmb_web_rerender_capture_inputs()
        if (current["target"] != claim.snapshot.get("target")
                or current["binding_fingerprint"] != claim.snapshot.get("binding_fingerprint")
                or _web_rerender_digest(current) != _web_rerender_digest(claim.snapshot)):
            raise RuntimeError("The Generator inputs or connection changed; request a new web rerender.")

    async def _hmb_web_rerender_prepare_media(self, claim: Any) -> dict[str, Any]:
        """Check selected local bytes off the engine loop, before invoking Agent."""
        self._hmb_web_rerender_validate_claim(claim)
        identity = await asyncio.to_thread(_web_rerender_reference_identity, claim.snapshot["params"], True)
        self._hmb_web_rerender_validate_claim(claim)
        if claim.media_identity is not None and identity != claim.media_identity:
            raise RuntimeError("A web rerender reference changed after the request was prepared.")
        claim.media_identity = identity
        prepared = deepcopy(claim.snapshot["params"])
        if claim.parent_settings is None:
            raise ValueError("web_rerender_parent_settings_contract_required")
        prepared = _web_rerender_apply_parent_settings(prepared, claim.parent_settings)
        replacements = {}
        for row in identity:
            if "resolved_path" not in row:
                continue
            field, index = row["field"], row["index"]
            current = prepared.get(field)
            authored = current[index] if isinstance(current, (list, tuple)) else current
            replacements[str(self._coerce_reference_value(authored))] = row["resolved_path"]
            if isinstance(current, (list, tuple)):
                current = list(current)
                current[index] = row["resolved_path"]
                prepared[field] = current
            else:
                prepared[field] = row["resolved_path"]
        # Legacy slots are redundant once the canonical ordered references
        # have been captured; do not re-resolve a different project later.
        prepared["video_reference_slots"] = []
        claim.prepared_params = prepared
        media = deepcopy(claim.snapshot["media_snapshot"])
        for row in media["images"] + media["videos"]:
            row["source"] = replacements.get(row["source"], row["source"])
        return media

    def _hmb_web_rerender_bind_parent_settings(self, claim: Any, frozen: dict[str, Any]) -> None:
        """Bind verified sparse wire controls before invoking either paid stage."""
        self._hmb_web_rerender_validate_claim(claim)
        if claim.parent_wire_settings is not None and _web_rerender_digest(claim.parent_wire_settings) != _web_rerender_digest(frozen):
            raise ValueError("web_rerender_parent_settings_changed")
        settings, context = _web_rerender_parent_execution_settings(frozen)
        candidate = _web_rerender_apply_parent_settings(claim.snapshot["params"], settings)
        validated = dict(deepcopy(candidate), prompt="Web rerender validation")
        _HMBWebRerenderExecution.read_view(self)._validate_parameters(validated)
        if {key: validated[key] for key in _WEB_RERENDER_PARENT_SETTINGS} != settings:
            raise ValueError("web_rerender_parent_settings_would_change")
        claim.parent_wire_settings = deepcopy(frozen)
        claim.parent_settings = settings
        claim.parent_generation_context = context

    async def _hmb_web_rerender_execute(
        self, claim: Any, agent_result: dict[str, Any], *, client_request_id: str,
        output_directory: str | Path, checkpoint_sink: Any, submission_bridge: Any,
        parent_task_id: str = "", command_id: str = "",
    ) -> dict[str, Any]:
        """Run a worker-authorized intent in an isolated, non-registered facade.

        The worker owns durable command deduplication and Broker authorization.
        A raw browser parameter cannot invoke this API or supply a valid claim.
        """
        self._hmb_web_rerender_validate_claim(claim)
        if claim.executed:
            raise RuntimeError("This web rerender reservation has already been executed.")
        if not callable(checkpoint_sink) or submission_bridge is None:
            raise ValueError("A durable checkpoint sink and command-bound Broker bridge are required.")
        if claim.media_identity is None:
            raise RuntimeError("Prepare the web rerender references before running the Agent.")
        await self._hmb_web_rerender_prepare_media(claim)
        client_request_id = self._validate_task_id(client_request_id)
        if not isinstance(agent_result, dict):
            raise ValueError("A completed Agent result is required.")
        text = agent_result.get("text")
        if (not isinstance(text, str) or not text.strip() or not agent_result.get("run_id")
                or hashlib.sha256(text.encode("utf-8")).hexdigest() != agent_result.get("output_sha256")):
            raise ValueError("The Agent result does not match its completed output.")
        claim.executed = True
        run = _HMBWebRerenderExecution.for_request(
            self, claim, agent_result, client_request_id, Path(output_directory),
            checkpoint_sink, submission_bridge, parent_task_id, command_id,
        )
        try:
            await run._process_generation()
        except BaseException:
            # The sink already holds pre-submit identity before any POST. Save
            # the last observable state too, without replacing the source node.
            with suppress(Exception):
                await run._force_save_generation_recovery_checkpoint(required=False, reason="web_interrupted")
            raise
        return {"task_id": str(run.parameter_output_values.get("generation_id") or ""),
                "project_id": claim.snapshot["project"]["project_id"],
                "project_name": claim.snapshot["project"]["project_name"],
                "client_request_id": client_request_id, "parent_task_id": parent_task_id,
                "command_id": command_id, "case_id": run._hmb_review_case_id,
                "status": str(run.parameter_output_values.get("generation_status") or ""),
                "checkpoint": deepcopy(run._generation_recovery_state()),
                "video": _web_rerender_plain(run.parameter_output_values.get("VIDEO_OUT")
                    or run.parameter_output_values.get("video_url")),
                "agent_run_id": agent_result["run_id"]}

    async def aprocess(self) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            return
        with self._generation_refresh_lock:
            if (
                self._generation_refresh_running
                or self._generation_run_active.is_set()
                or (self._hmb_draft_finalize_pending and asyncio.current_task() is not self._hmb_draft_finalize_task)
            ):
                return
            self._generation_run_active.set()
            self._hmb_active_draft_action = DRAFT_ACTION_OFF
        try:
            await self._aprocess_impl()
        finally:
            with self._generation_refresh_lock:
                self._generation_run_active.clear()
                self._hmb_active_draft_action = DRAFT_ACTION_OFF
            with suppress(Exception):
                self._update_parameter_visibility()
                self._sync_seedance_shot_widget(emit_change=True)

    async def _aprocess_impl(self) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            return
        if _my_box_node.is_selected(self):
            # Never enter production preflight, managed Agent, public recovery
            # ledger or review publishing for a private Only invocation.
            self._clear_execution_status()
            self._hmb_expected_agent_result = None
            self._hmb_agent_submission_prompt = None
            self._hmb_managed_agent_request = None
            self._hmb_project_selection_guard = None
            raw_model = str(self.get_parameter_value("model_id") or "")
            await self._hmb_my_box_controller().run(final=(MODEL_ID_ALIASES.get(raw_model, raw_model) == SEEDANCE_2_5_MODEL_ID
                and self.get_parameter_value("draft_action") == DRAFT_ACTION_FINAL))
            return
        self._clear_execution_status()
        self._hmb_expected_agent_result = None
        self._hmb_agent_submission_prompt = None
        self._hmb_managed_agent_request = None
        try:
            try:
                self._validate_local_render_preflight()
            except Exception as exc:
                self._hmb_local_preflight_failure = self._safe_exception_message(exc)
                self._publish_agent_result_skipped(
                    "Render preflight failed before Agent execution or submission: "
                    + self._hmb_local_preflight_failure
                    + " Independent Shots continue."
                )
                return
            self._hmb_local_preflight_failure = ""
            await self._prepare_managed_agent_shot()
            self._assert_agent_result_available()
            await self._process_generation()
        except _AgentResultUnavailable as exc:
            self._publish_agent_result_skipped(str(exc))
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
                and bool(generation_id)
                and str(provider_response.get("id") or "").strip() == generation_id
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
                        "terminal. The next explicit Run can start a new render. "
                        "Refresh / Retrieve Result only retrieves the same "
                        "final state; it does not resume, restart, or duplicate "
                        "a render. No automatic render was submitted."
                    )
                else:
                    safe_message += (
                        f"\nExisting task ID: {generation_id}. The server render can "
                        "continue after a disconnect. Use Refresh / Retrieve Result to "
                        "check this same task without creating a duplicate. A new "
                        "explicit Run with Resume Task ID empty submits a separate "
                        "render; the previous task is not cancelled and duplicate "
                        "charges are possible."
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
                    "\nA new explicit Run with Resume Task ID empty submits a separate "
                    "render. The previous task is not cancelled; duplicate charges "
                    "are possible. No automatic resubmission was performed."
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
            # A handled per-shot failure is a Failed result, not a global DAG
            # exception. Other shots (including their active polling) continue.
            logger.error("%s failed; independent shots continue: %s", self.name, safe_message)

        finally:
            # The frozen request belongs to this explicit Generator run only.
            # Never leave another Shot's result in the author's prompt control.
            managed = getattr(self, "_hmb_managed_agent_request", None)
            if isinstance(managed, dict):
                release = getattr(managed["source"], "_hmb_release_agent_shot_result", None)
                if callable(release):
                    with suppress(Exception):
                        release(channel_uuid=managed["channel_uuid"], shot_uuid=managed["shot_uuid"],
                                run_id=managed.get("record", {}).get("result", {}).get("run_id", ""),
                                generator=self)
            self._hmb_managed_agent_request = None

    def _managed_agent_input_fingerprint(self, params: Mapping[str, Any]) -> str:
        """Compare billable inputs around inference, excluding editor-only data."""
        keys = ("model_id", TASK_PARAMETER, "input_mode", "resolution", "ratio", "duration",
                "generate_audio", "watermark", "output_format", "return_last_frame",
                "draft_action", "draft_job_id", "resume_generation_id", "first_frame", "last_frame",
                "reference_images", "video_references", "video_reference_slots", "reference_audio",
                "_hmb_finish_look_out", "_hmb_draft_source_bindings")
        return self._canonical_sha256({key: params.get(key) for key in keys})

    async def _prepare_managed_agent_shot(self) -> None:
        """Pull one exact Shot from a manager without executing sibling Agents.

        A shared SDK dependency runs once per node, so a manager dependency
        prepares its catalog only. Each Generator owns its own immutable model
        result and cancellation scope. Legacy single-shot and Only paths keep
        their normal upstream execution contract.
        """
        if str(self.get_parameter_value("resume_generation_id") or "").strip() or self._draft_final_requested():
            return
        mode_getter = getattr(self, "_hmb_seedance_execution_mode", None)
        if callable(mode_getter) and mode_getter() == "only":
            self._assert_only_mode_inputs()
            return
        source = self._manual_agent_prompt_source()
        enabled = getattr(source, "_hmb_shot_manager_enabled", None)
        if not callable(enabled) or not enabled():
            return
        self._reconcile_shared_shot_routing(strict=True)
        subscription = self._hmb_shot_channel_subscription()
        if not subscription.get("enabled"):
            raise _AgentResultUnavailable("Select a Shot before using an Agent manager. No render was submitted.")
        channel, shot = subscription["channel_uuid"], subscription["shot_uuid"]
        owner_api = getattr(source, "_hmb_manager_prompt_owner", None)
        run_api = getattr(source, "_hmb_run_agent_shot", None)
        if not callable(owner_api) or not callable(run_api):
            raise _AgentResultUnavailable("The connected Agent manager needs a compatible Prompt manager.")
        prompt_owner = owner_api(channel_uuid=channel, shot_uuid=shot)
        # Validate project and direct source identity before any model call.
        # This validation copy is never persisted or submitted as a prompt.
        validation = self._resolve_exact_shot_generation_inputs(self._get_parameters())
        selection = validation.get("_hmb_imageasset_project_selection")
        if not isinstance(selection, dict):
            raise _AgentResultUnavailable("The selected Shot project is unavailable. No render was submitted.")
        prepared_inputs = self._managed_agent_input_fingerprint(validation)
        origin = self._capture_generated_video_origin()
        record = await run_api(channel_uuid=channel, shot_uuid=shot,
                               prompt_owner=prompt_owner, generator=self)
        if isinstance(record, dict):
            # Retain the ticket immediately so every later validation/cancel
            # path can release it, including an input edit during inference.
            self._hmb_managed_agent_request = {
                "source": source, "channel_uuid": channel, "shot_uuid": shot,
                "record": deepcopy(record),
            }
        if not self._runtime_node_is_live(require_registered=True) or self.is_cancellation_requested:
            raise asyncio.CancelledError()
        self._assert_imageasset_project_selection(selection)
        current = self._hmb_shot_channel_subscription()
        current_origin = self._capture_generated_video_origin()
        if (self._manual_agent_prompt_source() is not source
                or current.get("channel_uuid") != channel or current.get("shot_uuid") != shot
                or any(current_origin.get(key) != origin.get(key)
                       for key in ("channel_uuid", "shot_uuid", "source_node_instance_id"))):
            raise _AgentResultUnavailable("The selected Shot changed during Agent execution. No render was submitted.")
        current_inputs = self._resolve_exact_shot_generation_inputs(self._get_parameters())
        if self._managed_agent_input_fingerprint(current_inputs) != prepared_inputs:
            raise _AgentResultUnavailable(
                "The selected Shot media or generation settings changed during Agent execution. "
                "Run this Shot again; no render was submitted."
            )
        if not isinstance(record, dict) or not isinstance(record.get("result"), dict):
            raise _AgentResultUnavailable("The Shot Agent returned no completed result. No render was submitted.")
        # Display name/number may legitimately change after the worker returns.
        # The frozen ticket stays byte-for-byte intact; current catalog metadata
        # supplies the submission label, while immutable UUIDs own the result.
        identity_fields = ("channel_uuid", "shot_uuid")
        result_shot = record.get("shot")
        if (not isinstance(result_shot, dict)
                or any(result_shot.get(key) != current.get(key) for key in identity_fields)):
            raise _AgentResultUnavailable("The Agent result belongs to a different Shot. No render was submitted.")
        text, result = record.get("text"), record["result"]
        if (not isinstance(text, str) or not text.strip() or result.get("status") != "succeeded"
                or not result.get("run_id")
                or hashlib.sha256(text.strip().encode("utf-8")).hexdigest() != result.get("output_sha256")):
            raise _AgentResultUnavailable("The Shot Agent has no completed final text. No render was submitted.")
        self._hmb_managed_agent_request = {
            "source": source, "channel_uuid": channel, "shot_uuid": shot,
            "record": deepcopy(record),
        }

    def _assert_agent_result_available(self, prompt: str | None = None, *, allow_resume: bool = True) -> None:
        """Gate only failed/pending Agent results, never prompt meaning or roles."""
        if allow_resume and str(self.get_parameter_value("resume_generation_id") or "").strip():
            return  # Retrieving an already submitted task does not need an Agent.
        if self._draft_final_requested():
            return  # Explicit Draft finalization inherits the Broker's immutable source inputs.
        managed = getattr(self, "_hmb_managed_agent_request", None)
        text = str((managed["record"]["text"] if prompt is None and isinstance(managed, dict)
                    else self.get_parameter_value("prompt") if prompt is None else prompt) or "").strip()
        reserved_errors = (
            "[HMB EXECUTION FAILED]", "[HMB EXECUTION CANCELLED]",
            "[HMB OUTPUT BLOCKED]", "[HMB LOCAL POLICY REQUIRED]",
            "[HMB CONNECTION CHECK FAILED]", "[HMB SOURCE CONTRACT INVALID]",
            "[HMB PROJECT POLICY PENDING]",
        )
        try:
            source = self._manual_agent_prompt_source()
        except Exception:
            raise _AgentResultUnavailable(
                "Agent prompt connection is unavailable. No new render was submitted."
            ) from None
        if isinstance(managed, dict):
            if source is not managed["source"]:
                raise _AgentResultUnavailable("Agent manager connection changed before submission.")
            getter = getattr(source, "_hmb_agent_shot_result", None)
            if not callable(getter):
                raise _AgentResultUnavailable("The Shot Agent result is unavailable.")
            record = getter(channel_uuid=managed["channel_uuid"], shot_uuid=managed["shot_uuid"],
                            run_id=managed["record"]["result"]["run_id"], generator=self)
            snapshot = record.get("result") if isinstance(record, dict) else None
            if (not isinstance(snapshot, dict) or snapshot != managed["record"]["result"]
                    or record.get("shot") != managed["record"]["shot"]
                    or record.get("text") != managed["record"]["text"]):
                raise _AgentResultUnavailable("The selected Shot Agent result changed before submission.")
            getter = lambda: snapshot
        else:
            manager_api = getattr(source, "_hmb_shot_manager_enabled", None)
            if callable(manager_api) and manager_api():
                raise _AgentResultUnavailable("The selected Shot Agent has not been prepared for this Generator run.")
            getter = getattr(source, "_hmb_execution_result_snapshot", None)
        if not callable(getter):
            if text.startswith(reserved_errors):
                raise _AgentResultUnavailable("Upstream Agent failed. No new render was submitted; independent shots continue.")
            if getattr(self, "_hmb_expected_agent_result", None) is not None:
                raise _AgentResultUnavailable("Agent source changed during preparation. No new render was submitted.")
            return  # Manual text/other nodes and valid saved legacy outputs stay native.
        try:
            snapshot = getter()
        except Exception:
            raise _AgentResultUnavailable(
                "Agent execution result is unavailable. No new render was submitted."
            ) from None
        if not isinstance(snapshot, dict):
            raise _AgentResultUnavailable("Agent execution result is unavailable. No new render was submitted.")
        status = snapshot.get("status")
        if status == "created" or snapshot.get("code") == "AGENT_CREATED":
            raise _AgentResultUnavailable(
                "Upstream Agent only created an object (AGENT_CREATED); no model result is available. "
                "Connect the intended HMB Prompt/Shot and run the Agent before rendering. "
                "No new render was submitted."
            )
        if status in {"failed", "running"}:
            fallback_code = "AGENT_RUNNING" if status == "running" else "AGENT_FAILED"
            code = str(snapshot.get("code") or fallback_code)
            if code not in {
                "MODEL_TIMEOUT", "MODEL_CREDENTIAL", "MODEL_ACCESS", "MODEL_RATE_LIMIT",
                "MODEL_NETWORK", "MODEL_PROVIDER", "HOST_ADAPTER", "EMPTY_OUTPUT",
                "OUTPUT_UNAVAILABLE", "POLICY_UNAVAILABLE", "SOURCE_UNAVAILABLE", "CANCELLED",
                "PROJECT_POLICY_PENDING",
            }:
                code = fallback_code
            raise _AgentResultUnavailable(
                f"Upstream Agent has no completed result ({code}). No new render was submitted; independent shots continue."
            )
        if text.startswith(reserved_errors):
            raise _AgentResultUnavailable("Upstream Agent failed. No new render was submitted; independent shots continue.")
        if not text:
            raise _AgentResultUnavailable("Upstream Agent has no final text. No new render was submitted.")
        expected = str(snapshot.get("output_sha256") or "")
        if status == "succeeded" and expected and hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
            raise _AgentResultUnavailable("Agent result changed or has not reached this Generator yet. No stale prompt was submitted.")
        token = (id(source), str(snapshot.get("run_id") or ""), expected)
        previous = getattr(self, "_hmb_expected_agent_result", None)
        if previous is not None and token != previous:
            raise _AgentResultUnavailable("Agent result changed during preparation. No new render was submitted.")
        self._hmb_expected_agent_result = token
        if not allow_resume:
            self._hmb_agent_submission_prompt = text

    def _publish_agent_result_skipped(self, message: str) -> None:
        if not self._runtime_node_is_live(require_registered=True):
            return
        # Output maps can be cleared by the host before a new run; the durable
        # recovery record remains authoritative for existing paid tasks.
        checkpoint = self._generation_recovery_state()
        generation_id = str(self.parameter_output_values.get("generation_id") or checkpoint.get("task_id") or "").strip()
        if generation_id:
            self.parameter_output_values["generation_id"] = generation_id
            self.parameter_output_values["generation_status"] = str(
                self.parameter_output_values.get("generation_status") or checkpoint.get("status") or ""
            )
            self._publish_generation_preview("failed", generation_id=generation_id, action="refresh_existing")
            message += f" Existing task {generation_id} is preserved; Refresh / Retrieve Result checks that same task."
        else:
            self._set_generation_status("skipped", generation_id="")
        self._set_status_results(was_successful=False, result_details=f"SKIPPED: {message}")
        logger.error("%s skipped: %s", self.name, message)

def _web_rerender_plain(value: Any) -> Any:
    """Stable private serialization of native reference artifacts, never repr()."""
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_web_rerender_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _web_rerender_plain(item) for key, item in value.items()}
    native_value = getattr(value, "value", None)
    if isinstance(native_value, (str, Path)):
        return str(native_value)
    raise ValueError("The Generator contains an unsupported reference value.")


def _web_rerender_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_web_rerender_plain(value), ensure_ascii=False,
                                     sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _web_rerender_reference_identity(params: dict[str, Any], inspect_files: bool = False) -> list[dict[str, Any]]:
    result = []
    for field in ("reference_images", "video_references", "reference_audio", "first_frame", "last_frame"):
        raw = params.get(field)
        values = list(raw) if isinstance(raw, (list, tuple)) else [raw] if raw is not None else []
        for index, value in enumerate(values):
            text = str(HMBSeedanceGeneration._coerce_reference_value(value))
            record = {"field": field, "index": index, "source_sha256": hashlib.sha256(text.encode()).hexdigest()}
            if inspect_files and not text.startswith(("http://", "https://", "data:", "asset://")):
                path = Path(text)
                if not path.is_absolute():
                    path = Path(File(text).resolve())
                if not path.is_file():
                    raise ValueError("A selected web rerender reference is no longer available.")
                stat = path.stat()
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                after = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("A selected web rerender reference changed while being read.")
                record.update(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, content_sha256=digest.hexdigest(),
                              resolved_path=str(path))
            result.append(record)
    return result


_WEB_RERENDER_PARENT_SETTINGS = frozenset({
    "model_id", "task", "input_mode", "resolution", "ratio", "duration",
    "generate_audio", "watermark", "output_format", "return_last_frame",
    "execution_expires_after", "priority",
    "draft_action",
})


def _web_rerender_parent_execution_settings(frozen: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map parent wire values without reading any current node controls.

    Absent optional controls below are execution-facade scaffolding only. The
    command-bound final opener restores the parent's sparse wire key set and
    the Agent context includes only values actually present in that request.
    """
    from _hmb_web_rerender import PARENT_SETTINGS_FIELDS
    if not isinstance(frozen, dict) or set(frozen) - PARENT_SETTINGS_FIELDS:
        raise ValueError("web_rerender_parent_settings_unsupported")
    mode = frozen.get("input_mode")
    task = INPUT_MODE_TASKS.get(mode)
    omni = frozen.get("omni_reference_task_type")
    if omni is not None:
        task = {value: key for key, value in TASK_OMNI_REFERENCE_TYPES.items()}.get(omni)
        if mode != INPUT_MODE_MULTIMODAL_REFERENCES or task is None:
            raise ValueError("web_rerender_parent_task_mode_mismatch")
    if task is None:
        raise ValueError("web_rerender_parent_input_mode_unsupported")
    model = frozen.get("model")
    resolution = frozen.get("quality", frozen.get("resolution"))
    if model not in MODEL_RESOLUTIONS or resolution not in MODEL_RESOLUTIONS[model]:
        raise ValueError("web_rerender_parent_resolution_unsupported")
    if model == SEEDANCE_2_5_MODEL_ID and "quality" in frozen and "resolution" in frozen and frozen["quality"] != frozen["resolution"]:
        raise ValueError("web_rerender_parent_resolution_conflict")
    if model != SEEDANCE_2_5_MODEL_ID and omni is not None:
        raise ValueError("web_rerender_parent_task_unsupported")
    if "draft" in frozen and type(frozen["draft"]) is not bool:
        raise ValueError("web_rerender_parent_draft_invalid_type")
    if frozen.get("draft") is True and (
        model != SEEDANCE_2_5_MODEL_ID or resolution != "480p"
        or any(frozen[key] != "480p" for key in ("quality", "resolution") if key in frozen)
    ):
        raise ValueError("web_rerender_parent_draft_requires_seedance25_480p")
    mappings = {"model": "model_id", "input_mode": "input_mode", "quality": "resolution",
                "aspect_ratio": "ratio", "ratio": "ratio", "duration_seconds": "duration", "duration": "duration",
                "generate_audio": "generate_audio", "watermark": "watermark", "output_format": "output_format",
                "return_last_frame": "return_last_frame", "execution_expires_after": "execution_expires_after", "priority": "priority"}
    context = {mappings[key]: deepcopy(value) for key, value in frozen.items() if key in mappings}
    context.update(model_id=model, resolution=resolution, task=task, input_mode=mode)
    if "draft" in frozen:
        context["draft_action"] = DRAFT_ACTION_PREVIEW if frozen["draft"] else DRAFT_ACTION_OFF
    # These are never advertised as authoritative parent settings when absent.
    settings = {"ratio": "adaptive", "watermark": False, "output_format": "mp4", "return_last_frame": False,
                "execution_expires_after": 86400, "priority": 0, "draft_action": DRAFT_ACTION_OFF, **context}
    if not {"duration", "generate_audio"}.issubset(settings):
        raise ValueError("web_rerender_parent_settings_incomplete")
    return settings, context


def _web_rerender_apply_parent_settings(
    params: dict[str, Any], settings: dict[str, Any],
) -> dict[str, Any]:
    """Replace rendering controls while preserving the connected source snapshot.

    This receives a verified Broker contract, never browser-controlled values.
    Exact types and a complete key set prevent missing values, False, and zero
    from turning into the current Generator's authoring defaults.
    """
    if not isinstance(settings, dict) or set(settings) != _WEB_RERENDER_PARENT_SETTINGS:
        raise ValueError("web_rerender_parent_settings_unsupported_or_incomplete")
    for key in ("model_id", "task", "input_mode", "resolution", "ratio", "output_format"):
        if type(settings[key]) is not str or not settings[key]:
            raise ValueError("web_rerender_parent_settings_invalid_type")
    for key in ("duration", "execution_expires_after", "priority"):
        if type(settings[key]) is not int:
            raise ValueError("web_rerender_parent_settings_invalid_type")
    for key in ("generate_audio", "watermark", "return_last_frame"):
        if type(settings[key]) is not bool:
            raise ValueError("web_rerender_parent_settings_invalid_type")
    if settings["draft_action"] not in {DRAFT_ACTION_OFF, DRAFT_ACTION_PREVIEW}:
        raise ValueError("web_rerender_parent_draft_action_unsupported")
    if settings["draft_action"] == DRAFT_ACTION_PREVIEW and (
        settings["model_id"] != SEEDANCE_2_5_MODEL_ID or settings["resolution"] != "480p"
    ):
        raise ValueError("web_rerender_parent_draft_requires_seedance25_480p")
    if settings["model_id"] not in BROKER_SUPPORTED_MODEL_IDS:
        raise ValueError("web_rerender_parent_model_unsupported")
    if TASK_INPUT_MODES.get(settings["task"]) != settings["input_mode"]:
        raise ValueError("web_rerender_parent_task_mode_mismatch")
    if settings["model_id"] != SEEDANCE_2_5_MODEL_ID and (
        settings["output_format"] != DEFAULT_OUTPUT_FORMAT or settings["return_last_frame"] is not False
    ):
        raise ValueError("web_rerender_parent_output_settings_unsupported")
    result = deepcopy(params)
    for key in _review.SETTINGS:
        result.pop(key, None)
    result.update(deepcopy(settings))
    result["draft_job_id"] = ""
    result.pop("_hmb_draft_source", None)
    if settings["draft_action"] == DRAFT_ACTION_PREVIEW:
        result["_hmb_draft_supported"] = True
    return result


@dataclass(eq=False)
class _HMBWebRerenderClaim:
    owner: Any
    snapshot: dict[str, Any]
    active: bool = True
    executed: bool = False
    media_identity: Any = None
    prepared_params: Any = None
    parent_wire_settings: Any = None
    parent_settings: Any = None
    parent_generation_context: Any = None


class _HMBWebRerenderOutput:
    def __init__(self, path: Path, node_name: str):
        self.path, self.node_name = path, node_name
        self._default_filename = str(path)

    def build_file(self) -> Any:
        return ProjectFileDestination.from_situation(
            str(self.path), ProjectFileParameter.DEFAULT_SITUATION, node_name=self.node_name,
        )


class _HMBWebRerenderSource:
    """Consume source metadata with an explicit no-filesystem readiness mode."""
    def __init__(self, source: Any, snapshots: dict[str, Any], kind: str):
        self.source, self.snapshots, self.kind = source, snapshots, kind

    def __getattr__(self, name: str) -> Any:
        return getattr(self.source, name)

    def _hmb_shot_routing_snapshot(self, channel_uuid: str = "") -> dict[str, Any]:
        method = self.source._hmb_shot_routing_snapshot
        if self.kind == "video_picker":
            raw = method(channel_uuid, validate_media=False)
        else:
            raw = method(channel_uuid, cached_only=True)
        self.snapshots[self.kind] = deepcopy(raw)
        return raw

    def _hmb_shot_routing_snapshot_for(self, *, channel_uuid: str, shot_uuid: str) -> dict[str, Any]:
        method = getattr(self.source, "_hmb_shot_routing_snapshot_for", None)
        if callable(method):
            options = ({"validate_media": False} if self.kind == "video_picker"
                       else {"cached_only": True})
            raw = method(channel_uuid=channel_uuid, shot_uuid=shot_uuid, **options)
            self.snapshots[self.kind] = deepcopy(raw)
            return raw
        return self._hmb_shot_routing_snapshot(channel_uuid)


class _HMBWebRerenderExecution(HMBSeedanceGeneration):
    """Request-local adapter for the production pipeline, never registered in a flow.

    All UI/output dictionaries, upload lists, checkpoints and observation state
    are request owned. The source object remains the sole liveness authority.
    """

    @classmethod
    def read_view(cls, owner: HMBSeedanceGeneration) -> Any:
        view = object.__new__(cls)
        view.__dict__.update(owner.__dict__)
        view._web_owner = owner
        view._web_request = False
        view._web_claim = None
        view._hmb_draft_final_context = None
        view._hmb_draft_finalize_task = None
        view._hmb_draft_finalize_pending = False
        view._hmb_project_selection_guard = None
        # Web rerenders use immutable parent settings, not the owner's local
        # Draft controls. Disable before capturing inputs / binding the claim;
        # doing this only in for_request is too late for readiness validation.
        view._web_parameter_cache = {"draft_action": DRAFT_ACTION_OFF, "draft_job_id": ""}
        view._web_source_snapshots = {}
        view.parameter_values = deepcopy(getattr(owner, "parameter_values", {}))
        view.parameter_output_values = {}
        return view

    @classmethod
    def for_request(cls, owner: HMBSeedanceGeneration, claim: _HMBWebRerenderClaim,
                    agent_result: dict[str, Any], client_request_id: str, output_directory: Path,
                    checkpoint_sink: Any, bridge: Any, parent_task_id: str, command_id: str) -> Any:
        run = cls.read_view(owner)
        run._web_request = True
        run._web_claim = claim
        run._web_loop = asyncio.get_running_loop()
        run._web_engine_thread = threading.get_ident()
        run._web_agent_result = deepcopy(agent_result)
        run._web_client_request_id = client_request_id
        run._web_checkpoint_sink = checkpoint_sink
        run._web_parent_task_id = parent_task_id
        run._web_command_id = command_id
        run._web_params = deepcopy(claim.prepared_params)
        run._web_params["prompt"] = agent_result["text"]
        run._web_params["resume_generation_id"] = ""
        if run._web_params.get("draft_action", DRAFT_ACTION_OFF) not in {DRAFT_ACTION_OFF, DRAFT_ACTION_PREVIEW}:
            raise ValueError("web_rerender_parent_draft_action_unsupported")
        run._web_params.setdefault("draft_action", DRAFT_ACTION_OFF)
        run._web_params["draft_job_id"] = ""
        run._web_parameter_cache.update(run._web_params)
        run._web_parameter_cache[BROKER_SERVER_URL_PARAMETER] = run._web_params["_hmb_broker_server_url"]
        run._web_parameter_cache[SEEDANCE_RECOVERY_PARAMETER] = _seedance_recovery_value({"journal_id": str(uuid4())})
        run._temporary_video_uploads = []
        run._temporary_tos_video_uploads = []
        run._hmb_reference_upload_lease_id = ""
        run._detached_submission_tasks = set()
        run._submission_outcome_unknown = False
        run._broker_bridge_instance = bridge
        run._hmb_generation_run_origin = deepcopy(run._web_params.get("_hmb_generation_origin") or {})
        run._hmb_generation_preview_state = _seedance_generation_preview_value()
        run._hmb_generation_recovery_restore_fingerprint = None
        run._hmb_generation_started_monotonic = None
        run._hmb_generation_started_at_ms = 0
        run._hmb_generation_media_revision = 0
        run._hmb_last_success_video = None
        run._hmb_last_success_last_frame_url = None
        run._hmb_generated_video_source = {}
        run._hmb_generated_video_source_published = {}
        run._hmb_review_case_id = ""
        run._hmb_review_stage_seconds = {}
        run._hmb_review_sync_jobs = set()
        run._hmb_review_sync_lock = threading.Lock()
        run._hmb_expected_agent_result = (agent_result["run_id"], agent_result["output_sha256"])
        run._hmb_agent_submission_prompt = agent_result["text"]
        output_directory = output_directory.resolve()
        output_directory.mkdir(parents=True, exist_ok=True)
        suffix = str(run._web_params.get("output_format") or "mp4")
        basename = hashlib.sha256(client_request_id.encode()).hexdigest()
        run._output_file = _HMBWebRerenderOutput(output_directory / f"{basename}.{suffix}", owner.name)
        run._last_frame_file = _HMBWebRerenderOutput(output_directory / f"{basename}_last.png", owner.name)
        return run

    def get_parameter_value(self, name: str) -> Any:
        if name == "prompt" and not self._web_request:
            return ""
        if name in self._web_parameter_cache:
            return deepcopy(self._web_parameter_cache[name])
        value = deepcopy(self._web_owner.get_parameter_value(name))
        self._web_parameter_cache[name] = value
        return deepcopy(value)

    def set_parameter_value(self, name: str, value: Any, *args: Any, **kwargs: Any) -> None:
        self._web_parameter_cache[name] = deepcopy(value)
        self.parameter_values[name] = deepcopy(value)

    def publish_update_to_parameter(self, *args: Any, **kwargs: Any) -> None:
        pass

    def _synchronize_model_resolution(self) -> str:
        raw = str(self.get_parameter_value("model_id") or MODEL_NAME_SEEDANCE_2_0).strip()
        return MODEL_ID_ALIASES.get(raw, raw)

    def _exact_incoming_source(self, target_parameter_name: str, expected_source_parameter_name: str,
                               *, required: bool = True) -> Any:
        source = self._web_owner._exact_incoming_source(
            target_parameter_name, expected_source_parameter_name, required=required,
        )
        kind = {SHOT_ASSET_INPUT_PARAMETER: "image_asset", SHOT_PICKER_INPUT_PARAMETER: "video_picker"}.get(target_parameter_name)
        return _HMBWebRerenderSource(source, self._web_source_snapshots, kind) if source is not None and kind else source

    def _reconcile_shared_shot_routing(self, *, strict: bool = False) -> dict[str, Any]:
        # Reconciliation can rewrite several real nodes and graph edges. Web
        # requests only consume an already connected, hydrated source contract.
        status = getattr(self._web_owner, "_hmb_shot_route_status", {})
        if strict and self._hmb_shot_channel_subscription()["enabled"] and status and not status.get("ok", True):
            raise RuntimeError("The connected Generator Shot is not ready.")
        return {"ok": True, "code": "read_only_snapshot", "changed": 0}

    def _get_parameters(self) -> dict[str, Any]:
        return deepcopy(self._web_params) if self._web_request else super()._get_parameters()

    def _resolve_exact_shot_generation_inputs(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._web_request:
            self._web_owner._hmb_web_rerender_validate_claim(self._web_claim)
            return deepcopy(params)
        return super()._resolve_exact_shot_generation_inputs(params)

    def _capture_generated_video_origin(self) -> dict[str, Any]:
        if self._web_request:
            return deepcopy(self._web_params.get("_hmb_generation_origin") or {})
        return self._web_owner._capture_generated_video_origin()

    def _runtime_node_is_live(self, *, require_registered: bool = False) -> bool:
        owner = self._web_owner
        live = (not bool(getattr(owner, "_hmb_node_deleted", False))
                if self._web_request and threading.get_ident() != self._web_engine_thread
                else owner._runtime_node_is_live(require_registered=True))
        return bool(live and (
            not self._web_request or (self._web_claim.active
                and getattr(owner, "_hmb_web_rerender_active_claim", None) is self._web_claim)))

    @property
    def is_cancellation_requested(self) -> bool:
        return bool(getattr(self._web_owner, "is_cancellation_requested", False))

    def _submission_start_is_authorized(self, *, require_registered: bool) -> bool:
        if not self._runtime_node_is_live(require_registered=True) or self.is_cancellation_requested:
            return False
        self._validate_request_on_engine_loop()
        if threading.get_ident() != self._web_engine_thread:
            current = _web_rerender_reference_identity(self._web_claim.snapshot["params"], True)
            if current != self._web_claim.media_identity:
                raise _AgentResultUnavailable("A web rerender reference changed before submission.")
        return True

    def _validate_request_on_engine_loop(self) -> None:
        async def validate() -> None:
            self._web_owner._hmb_web_rerender_validate_claim(self._web_claim)
        try:
            if threading.get_ident() == self._web_engine_thread:
                self._web_owner._hmb_web_rerender_validate_claim(self._web_claim)
            else:
                future = asyncio.run_coroutine_threadsafe(validate(), self._web_loop)
                try:
                    future.result(timeout=10)
                except BaseException:
                    future.cancel()
                    raise
        except (RuntimeError, ValueError, TimeoutError) as exc:
            raise _AgentResultUnavailable("The web rerender target changed before submission.") from exc

    def _assert_agent_result_available(self, prompt: str | None = None, *, allow_resume: bool = True) -> None:
        self._validate_request_on_engine_loop()
        text = self._web_agent_result["text"] if prompt is None else prompt
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != self._web_agent_result["output_sha256"]:
            raise _AgentResultUnavailable("The web Agent result changed before submission.")

    def _new_generation_client_request_id(self) -> str:
        return self._web_client_request_id

    def _generation_recovery_state(self) -> dict[str, Any]:
        return _seedance_recovery_value(self.get_parameter_value(SEEDANCE_RECOVERY_PARAMETER))

    def _claim_generation_recovery_journal(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        return checkpoint

    def _current_recovery_output_file(self) -> str:
        return str(self._output_file.path)

    async def _force_save_generation_recovery_checkpoint(self, *, required: bool, reason: str) -> bool:
        checkpoint = deepcopy(self._generation_recovery_state())
        checkpoint.update(parent_task_id=self._web_parent_task_id, command_id=self._web_command_id,
                          client_request_id=self._web_client_request_id, case_id=self._hmb_review_case_id,
                          project_id=self._web_params["project_id"], project_name=self._web_params["project_name"])
        try:
            result = self._web_checkpoint_sink(checkpoint, reason=reason, required=required)
            if inspect.isawaitable(result):
                await result
            return True
        except Exception:
            if required:
                raise
            logger.warning("Web rerender checkpoint update was unavailable; its saved request identity remains authoritative.")
            return False

    def _get_broker_bridge(self, *, server_url: str | None = None) -> Any:
        expected = self._web_params["_hmb_broker_server_url"]
        if server_url is not None and _broker_validated_server_url(server_url) != expected:
            raise _BrokerProtocolError("The web rerender Broker origin changed.")
        return self._broker_bridge_instance

    def _apply_broker_snapshot(self, *args: Any, **kwargs: Any) -> None:
        pass

    def _sync_seedance_shot_widget(self, *args: Any, **kwargs: Any) -> None:
        pass

    def _publish_generation_preview(self, phase: str, *, generation_id: str | None = None,
                                    **kwargs: Any) -> None:
        self._hmb_generation_preview_state = {"phase": phase, "job_id": generation_id or ""}
        self._record_review_stage(phase, generation_id or "")

    def _record_completed_video_source(self, *args: Any, **kwargs: Any) -> None:
        pass

    def _set_status_results(self, **kwargs: Any) -> None:
        self._web_status_results = deepcopy(kwargs)

    def _start_review_case(self, client_request_id: str, submitted_prompt: str) -> None:
        inputs = deepcopy(self._hmb_review_inputs)
        inputs["web_rerender"] = {"parent_task_id": self._web_parent_task_id, "command_id": self._web_command_id}
        self._hmb_review_case_id = _review.start_case(
            client_request_id, inputs, submitted_prompt, _get_build_diagnostics(),
            deepcopy(self._web_agent_result.get("observation") or {}),
        )


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
    "SHOT_FINISH_LOOK_INPUT_PARAMETER",
    "FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA",
    "FINISH_LOOK_SHOT_SNAPSHOT_VERSION",
    "GENERATION_PREVIEW_SCHEMA",
    "GENERATION_PREVIEW_VERSION",
    "GENERATION_PREVIEW_PHASES",
    "SEEDANCE_RECOVERY_PARAMETER",
    "SEEDANCE_RECOVERY_SCHEMA",
    "SEEDANCE_RECOVERY_VERSION",
]
