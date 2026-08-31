from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
import asyncio
import base64
import copy
import contextvars
import hashlib
import importlib.util
from io import BytesIO
import json
import logging
import os
import re
import shutil
import stat
import struct
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Sequence
import unicodedata
from urllib.parse import unquote, urlparse
import uuid
import weakref


_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _load_hmb_common():
    module_path = _THIS_DIR / "_hmb_common.py"
    module_name = "_hmb_gp_production_common"
    existing = sys.modules.get(module_name)
    if (
        existing is not None
        and Path(getattr(existing, "__file__", "")).resolve() == module_path.resolve()
    ):
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load HMB common module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_hmb = _load_hmb_common()
try:
    import _hmb_shot_routing  # type: ignore
except Exception:
    _hmb_shot_routing = None  # type: ignore

DataNode = _hmb.DataNode
Parameter = _hmb.Parameter
ParameterMode = _hmb.ParameterMode
set_output = _hmb.set_output
parameter_exists = getattr(
    _hmb,
    "parameter_exists",
    lambda node, name: name in getattr(node, "parameters", {}),
)

IMAGE_SOURCE_TYPE_CHOICES = _hmb.IMAGE_SOURCE_TYPE_CHOICES
IMAGE_MAIN_TYPE_UNCLASSIFIED = _hmb.IMAGE_MAIN_TYPE_UNCLASSIFIED
IMAGE_MAIN_TYPE_CHOICES = _hmb.IMAGE_MAIN_TYPE_CHOICES
IMAGE_SUB_TYPE_CHOICES = _hmb.IMAGE_SUB_TYPE_CHOICES
IMAGE_SOURCE_TYPE_UNCLASSIFIED = _hmb.IMAGE_SOURCE_TYPE_UNCLASSIFIED
IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED = _hmb.IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED
ACTOR_COLOR_PICK_CHOICES = _hmb.ACTOR_COLOR_PICK_CHOICES
OBJECT_COLOR_PICK_CHOICES = _hmb.OBJECT_COLOR_PICK_CHOICES
image_color_pick_choices_for_taxonomy = _hmb.image_color_pick_choices_for_taxonomy
image_sub_type_choices_for_main_type = _hmb.image_sub_type_choices_for_main_type
image_taxonomy_wire_pair = _hmb.image_taxonomy_wire_pair
image_taxonomy_payload = _hmb.image_taxonomy_payload

try:
    from griptape_nodes.traits.file_system_picker import FileSystemPicker  # type: ignore
except Exception:
    FileSystemPicker = None  # type: ignore

try:
    from griptape_nodes.exe_types.param_types.parameter_string import (  # type: ignore
        ParameterString,
    )
except Exception:
    ParameterString = None  # type: ignore

try:
    from griptape_nodes.exe_types.core_types import ParameterList  # type: ignore
except Exception:
    ParameterList = None  # type: ignore

try:
    from griptape_nodes.traits.widget import Widget  # type: ignore
except Exception:
    Widget = None  # type: ignore


WIDGET_NAME = "HMBImageAssetLibraryWidget"
WIDGET_LIBRARY_NAME = "HMB_GP_Production"
WIDGET_STATE_PARAMETER = "HMB_IMAGE_ASSET_STATE"
THUMBNAIL_PATCH_PARAMETER = "HMB_IMAGE_ASSET_THUMBNAIL_PATCH"
THUMBNAIL_BRIDGE_WIDGET_NAME = "HMBImageAssetThumbnailPatchBridgeWidget"
THUMBNAIL_BRIDGE_SCHEMA = "hmb-image-asset-thumbnail-bridge"
THUMBNAIL_BRIDGE_VERSION = 1
PROJECT_ROOT_PARAMETER = "PROJECT_ROOT"
IMAGE_IMPORT_PARAMETER = "IMAGE_IMPORT_IN"
OUTPUT_PARAMETER = "IMAGE_ASSET_OUT"
MEDIA_OUTPUT_PARAMETER = "IMAGE_OUT"
SHOT_ASSET_OUTPUT_PARAMETER = "SHOT_ASSET_OUT"
OUTPUT_DISPLAY_NAME = "ASSET_OUT"
MEDIA_OUTPUT_DISPLAY_NAME = "Video Generation Out"
STATE_SCHEMA = "hmb-image-asset-library-state"
OUTPUT_SCHEMA = "hmb-image-asset-library-binding"
STATE_VERSION = 4
RESET_HANDOFF_SCHEMA = "hmb-image-asset-reset-handoff"
RESET_HANDOFF_VERSION = 1
RESET_HANDOFF_IDENTITY_CONTRACT = (
    "preserve-channel-shot-new-publisher-runtime-v1"
)
UI_EDIT_REVISION_KEY = "ui_edit_revision"
MAX_UI_EDIT_REVISION = (1 << 53) - 1
OUTPUT_VERSION = 4
IMAGE_BINDING_CAPABILITY_SCHEMA = "hmb-image-source-binding-capabilities"
IMAGE_BINDING_CAPABILITY_VERSION = 1
IMAGE_AUTHORITY_SCOPE_SCHEMA = "hmb-image-source-authority-scope"
IMAGE_AUTHORITY_SCOPE_VERSION = 1
MAX_ASSETS = 5000
MAX_FOLDERS = 5000
MAX_PROJECTS = 500
MAX_SELECTED_IMAGES = 50
MAX_SHOTS = 5
MAX_SHOT_IMAGES = 30
MAX_THUMBNAIL_HYDRATION_BATCH = 64
SHOT_ROUTING_SCHEMA = "hmb-shot-routing"
SHOT_ROUTING_VERSION = 1
SHOT_ROUTING_SNAPSHOT_SCHEMA = "hmb-shot-routing-snapshot"
SHOT_ROUTING_SNAPSHOT_VERSION = 1
SHOT_ROUTING_CATALOG_SCHEMA = "hmb-shot-routing-catalog"
SHOT_ROUTING_CATALOG_VERSION = 1
MAX_IMPORT_BYTES = 100 * 1024 * 1024
MAX_IMPORT_BASE64_CHARS = ((MAX_IMPORT_BYTES + 2) // 3) * 4 + 4096
try:
    _CONFIGURED_IMPORT_TOTAL_BYTES = int(
        os.environ.get("HMB_IMAGE_IMPORT_TOTAL_BYTES", 512 * 1024 * 1024)
    )
except (TypeError, ValueError):
    _CONFIGURED_IMPORT_TOTAL_BYTES = 512 * 1024 * 1024
MAX_IMPORT_TOTAL_BYTES = max(MAX_IMPORT_BYTES, _CONFIGURED_IMPORT_TOTAL_BYTES)
MAX_INPUT_NESTING = 64
MAX_INPUT_NODES = max(MAX_ASSETS * 16, 8192)
MANIFEST_NAMES = ("hmb_image_assets.json", ".hmb_image_assets.json")
ASSET_METADATA_DIRECTORY_NAME = ".json"
ASSET_MANIFEST_SCHEMA = "hmb-image-assets"
ASSET_MANIFEST_VERSION = 1
ASSET_MANIFEST_LOCK_NAME = ".hmb_image_assets.lock"
ASSET_MANIFEST_LOCK_TIMEOUT_SECONDS = 10.0
DEFAULT_PROJECTS_ROOT = Path(
    os.environ.get(
        "HMB_IMAGE_PROJECTS_ROOT",
        r"\\fin-rcomp1\Composite_Team\projects_AI",
    )
)
IMAGE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
        ".gif",
        ".exr",
    }
)
ASSET_NODE_WIDTH = 1400
ASSET_NODE_HEIGHT = 1200
_LOGGER = logging.getLogger("griptape_nodes")
_DIAGNOSTIC_PREFIX = "[HMB_GP_Production][HMBImageAssetLibrary]"
_ASSET_MANIFEST_LOCK_GUARD = threading.Lock()
_ASSET_MANIFEST_LOCKS: Dict[str, threading.Lock] = {}
_ASSET_MANIFEST_CACHE_LOCK = threading.Lock()
_ASSET_MANIFEST_CACHE: Dict[
    tuple[str, str], Dict[str, Dict[str, Any]]
] = {}
_ASSET_MANIFEST_CACHE_LIMIT = 32
_ASSET_RESOLUTION_CACHE_LIMIT = 256
_ASSET_THUMBNAIL_LOCK = threading.Lock()
_ASSET_THUMBNAIL_URLS: "OrderedDict[str, str]" = OrderedDict()
try:
    _ASSET_THUMBNAIL_CACHE_MAX_ENTRIES = max(
        64,
        min(
            4096,
            int(os.environ.get("HMB_IMAGE_THUMBNAIL_CACHE_ENTRIES", "1024")),
        ),
    )
except (TypeError, ValueError):
    _ASSET_THUMBNAIL_CACHE_MAX_ENTRIES = 1024
try:
    _ASSET_THUMBNAIL_CACHE_MAX_BYTES = max(
        32 * 1024 * 1024,
        min(
            2 * 1024 * 1024 * 1024,
            int(
                os.environ.get(
                    "HMB_IMAGE_THUMBNAIL_CACHE_BYTES",
                    str(256 * 1024 * 1024),
                )
            ),
        ),
    )
except (TypeError, ValueError):
    _ASSET_THUMBNAIL_CACHE_MAX_BYTES = 256 * 1024 * 1024
_ASSET_THUMBNAIL_CACHE_ROOT = Path(
    os.environ.get("HMB_IMAGE_THUMBNAIL_CACHE", "")
    or (
        Path(os.environ["LOCALAPPDATA"])
        / "HMB_GP_Production"
        / "cache"
        / "image_thumbnails"
        if os.environ.get("LOCALAPPDATA")
        else _THIS_DIR / ".tmp" / "image_thumbnails"
    )
)
_ASSET_THUMBNAIL_CACHE_WARNING_EMITTED = False
_ASSET_THUMBNAIL_CACHE_PRUNE_PENDING = False
_ASSET_THUMBNAIL_CACHE_DEFER_COUNT = 0
_ASSET_CATALOG_INDEX_ROOT = _ASSET_THUMBNAIL_CACHE_ROOT.parent / "image_catalogs"
_ASSET_CATALOG_INDEX_SCHEMA = "hmb-image-asset-catalog-index"
_ASSET_CATALOG_INDEX_VERSION = 2
_ASSET_CATALOG_INDEX_MAX_BYTES = 32 * 1024 * 1024
_ASSET_CATALOG_INDEX_LOCK = threading.Lock()
_ASSET_THUMBNAIL_CACHE_PROCESS_LOCK_NAME = ".hmb-thumbnail-cache.lock"
_ASSET_PROJECT_CACHE_UID_FIELD = "project_cache_uid"
_ASSET_PROJECT_CACHE_UID_PREFIX = "hmbpc1:"
_ASSET_PROJECT_CACHE_UID_LOCK = threading.Lock()
_ASSET_PROJECT_CACHE_UIDS: "OrderedDict[tuple[str, str], str]" = OrderedDict()
_ASSET_PROJECT_CACHE_UID_LIMIT = 64
_SHARED_CATALOG_CACHE_LOCK = threading.RLock()
_SHARED_CATALOG_CACHE: "OrderedDict[tuple[str, str, str], Dict[str, Any]]" = OrderedDict()
_SHARED_CATALOG_ROOT_BINDINGS: "OrderedDict[str, tuple[str, str, str]]" = OrderedDict()
_SHARED_CATALOG_CACHE_LIMIT = 32
CATALOG_PROBE_OPERATION = "catalog_probe"
CATALOG_PROBE_MANIFEST_SECONDS = 3.0
CATALOG_PROBE_FOLDER_SECONDS = 10.0
CATALOG_PROBE_STABLE_WRITE_SECONDS = 1.0


def _diagnostic_exception(context: str, exc: BaseException) -> None:
    try:
        _LOGGER.exception("%s %s: %s", _DIAGNOSTIC_PREFIX, context, exc)
    except Exception:
        return


def _diagnostic_warning(context: str, message: Any) -> None:
    try:
        _LOGGER.warning("%s %s: %s", _DIAGNOSTIC_PREFIX, context, _clean(message))
    except Exception:
        return


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _project_root_text(value: Any) -> str:
    """Resolve FileSystemPicker values without recursive/cyclic traversal."""
    keys = ("path", "file_path", "filepath", "value", "uri", "url", "filename")
    stack: List[tuple[Any, int]] = [(value, 0)]
    visited: set[int] = set()
    examined = 0
    while stack and examined < MAX_INPUT_NODES:
        current, depth = stack.pop()
        examined += 1
        if current is None or depth > MAX_INPUT_NESTING:
            continue
        if isinstance(current, Path):
            return str(current)
        if isinstance(current, bytes):
            return current.decode("utf-8", errors="replace").strip()
        if isinstance(current, dict):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            for key in reversed(keys):
                if key in current:
                    stack.append((current.get(key), depth + 1))
            continue
        if isinstance(current, (list, tuple, set)):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            items = list(current)
            for item in reversed(items):
                stack.append((item, depth + 1))
            continue
        if not isinstance(current, str):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            found_attribute = False
            for attribute in reversed(keys):
                try:
                    candidate = getattr(current, attribute, None)
                except Exception:
                    continue
                if candidate is not None:
                    found_attribute = True
                    stack.append((candidate, depth + 1))
            if found_attribute:
                continue
        text = _clean(current).strip('"').strip("'")
        if text[:1] in {"[", "{"} and depth < MAX_INPUT_NESTING:
            try:
                stack.append((json.loads(text), depth + 1))
                continue
            except Exception:
                pass
        if text.casefold().startswith("file:"):
            text = _decode_file_uri(text)
        return os.path.expandvars(text)
    return ""


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _default_thumbnail_bridge(runtime_instance_id: Any = "") -> Dict[str, Any]:
    return {
        "schema": THUMBNAIL_BRIDGE_SCHEMA,
        "version": THUMBNAIL_BRIDGE_VERSION,
        "runtime_instance_id": _clean(runtime_instance_id),
        "operation": "idle",
        "phase": "idle",
        "request_id": "",
    }


def _normalize_thumbnail_bridge(value: Any) -> Dict[str, Any]:
    raw = _parse_mapping(value)
    bridge = _default_thumbnail_bridge(raw.get("runtime_instance_id"))
    operation = _clean(raw.get("operation")).casefold()
    phase = _clean(raw.get("phase")).casefold()
    if operation == CATALOG_PROBE_OPERATION and phase in {"request", "result"}:
        bridge.update(
            {
                "operation": CATALOG_PROBE_OPERATION,
                "phase": phase,
                "request_id": _clean(raw.get("request_id"))[:128],
                "project_uid": _clean(raw.get("project_uid"))[:128],
                "project_cache_uid": _clean(raw.get("project_cache_uid"))[:256],
                "project_root": _project_root_text(raw.get("project_root"))
                .replace("\\", "/")[:4096],
                "manifest_signature": _clean(raw.get("manifest_signature"))[:128],
                "folder_signature": _clean(raw.get("folder_signature"))[:128],
                "scan_revision": _non_negative_int(raw.get("scan_revision")),
                "probe_kind": (
                    "folder"
                    if _clean(raw.get("probe_kind")).casefold() == "folder"
                    else "manifest"
                ),
            }
        )
        if phase == "result":
            outcome = _clean(raw.get("outcome")).casefold()
            bridge["outcome"] = (
                outcome
                if outcome in {"no_change", "changed", "deferred", "offline"}
                else "deferred"
            )
        return bridge
    if operation != "hydrate" or phase not in {"request", "result"}:
        return bridge
    bridge.update(
        {
            "operation": "hydrate",
            "phase": phase,
            "request_id": _clean(raw.get("request_id"))[:128],
            "project_uid": _clean(raw.get("project_uid"))[:128],
            "project_cache_uid": _clean(raw.get("project_cache_uid"))[:256],
            "manifest_signature": _clean(raw.get("manifest_signature"))[:128],
            "scan_revision": _non_negative_int(raw.get("scan_revision")),
            "thumbnail_revision": _non_negative_int(raw.get("thumbnail_revision")),
        }
    )
    ids = raw.get("asset_library_ids")
    if isinstance(ids, list):
        bridge["asset_library_ids"] = list(
            # Match the canonical path-derived identity contract. Truncating
            # only the compact bridge prevents a completed thumbnail from
            # resolving back to its card and leaves the loader spinning.
            dict.fromkeys(_clean(item)[:512] for item in ids if _clean(item))
        )[:MAX_THUMBNAIL_HYDRATION_BATCH]
    if phase == "result":
        entries = raw.get("completed_assets")
        bridge["completed_assets"] = [
            {
                # Asset-library IDs and source UIDs are path-derived and the
                # canonical widget/backend contract permits up to 512 chars.
                # Truncating them only on the compact bridge makes a completed
                # thumbnail impossible to match back to its card, leaving the
                # presentation loader active forever even though the file was
                # generated successfully.
                "asset_library_id": _clean(item.get("asset_library_id"))[:512],
                "source_uid": _clean(item.get("source_uid"))[:512],
                "media_signature": _clean(item.get("media_signature"))[:128],
                "thumbnail_url": _clean(item.get("thumbnail_url"))[:4096],
            }
            for item in (entries if isinstance(entries, list) else [])
            if isinstance(item, dict) and _clean(item.get("asset_library_id"))
        ][:MAX_THUMBNAIL_HYDRATION_BATCH]
        failed = raw.get("failed_asset_library_ids")
        bridge["failed_asset_library_ids"] = list(
            dict.fromkeys(
                _clean(item)[:512]
                for item in (failed if isinstance(failed, list) else [])
                if _clean(item)
            )
        )[:MAX_THUMBNAIL_HYDRATION_BATCH]
    return bridge


def _parse_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _mode_set(*names: str):
    if ParameterMode is None:
        return None
    values = {
        getattr(ParameterMode, name)
        for name in names
        if getattr(ParameterMode, name, None) is not None
    }
    return values or None


def _parameter_attempts(kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
    modern = dict(kwargs)
    if modern.get("allowed_modes") is not None:
        modern.pop("allow_input", None)
        modern.pop("allow_output", None)
        modern.pop("allow_property", None)
    attempts = [modern]
    reduced = dict(modern)
    reduced.pop("settable", None)
    attempts.append(reduced)
    legacy = dict(kwargs)
    legacy.pop("settable", None)
    legacy.pop("allowed_modes", None)
    attempts.append(legacy)
    return attempts


def _safe_add_parameter(node: Any, **kwargs: Any) -> None:
    last: Exception | None = None
    for attempt in _parameter_attempts(kwargs):
        try:
            node.add_parameter(Parameter(**attempt))
            return
        except Exception as exc:
            last = exc
    raise last or RuntimeError(f"Unable to add parameter {kwargs.get('name')}")


def _get_parameter_obj(node: Any, name: str) -> Any:
    try:
        getter = getattr(node, "get_parameter_by_name", None)
        if callable(getter):
            return getter(name)
    except Exception:
        pass
    parameters = getattr(node, "parameters", {})
    return parameters.get(name) if isinstance(parameters, dict) else None


def _get_parameter_raw(node: Any, name: str) -> Any:
    try:
        return node.get_parameter_value(name)
    except Exception:
        parameter = _get_parameter_obj(node, name)
        return getattr(parameter, "default_value", "") if parameter is not None else ""


def _set_parameter_value(node: Any, name: str, value: Any) -> None:
    try:
        node.set_parameter_value(name, value)
        return
    except Exception:
        parameter = _get_parameter_obj(node, name)
        if parameter is not None:
            parameter.default_value = value


def _taxonomy_payload() -> Dict[str, Any]:
    return image_taxonomy_payload()


def _normalize_image_taxonomy_fields(raw: Any) -> Dict[str, Any]:
    """Normalize fields against the current shared authoring contract."""
    source = raw if isinstance(raw, dict) else {}
    main_type = _clean(source.get("image_main_type"))
    sub_type = _clean(source.get("image_sub_type"))
    if (
        main_type not in IMAGE_MAIN_TYPE_CHOICES
        or main_type == IMAGE_MAIN_TYPE_UNCLASSIFIED
        or sub_type not in image_sub_type_choices_for_main_type(main_type)
    ):
        return {
            "image_main_type": IMAGE_MAIN_TYPE_UNCLASSIFIED,
            "image_sub_type": "",
            "source_type": IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
            "scope_candidate": "",
            "custom_source_type": "",
            "color_pick_candidates": [],
        }
    wire_pair = image_taxonomy_wire_pair(main_type, sub_type)
    if wire_pair is None:
        return {
            "image_main_type": IMAGE_MAIN_TYPE_UNCLASSIFIED,
            "image_sub_type": "",
            "source_type": IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
            "scope_candidate": "",
            "custom_source_type": "",
            "color_pick_candidates": [],
        }
    source_type, scope_candidate = wire_pair
    custom_source_type = (
        _clean(source.get("custom_source_type"))
        if main_type == "Custom / Context" and sub_type == "Custom"
        else ""
    )
    return {
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "source_type": source_type,
        "scope_candidate": scope_candidate,
        "custom_source_type": custom_source_type,
        "color_pick_candidates": image_color_pick_choices_for_taxonomy(
            main_type,
            sub_type,
        ),
    }


def _selectable_source_types() -> List[str]:
    return [
        value
        for value in IMAGE_SOURCE_TYPE_CHOICES
        if value not in {
            IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
            IMAGE_SOURCE_TYPE_UNCLASSIFIED,
            "Ignore / Unused",
        }
    ]


def _natural_key(value: Any) -> List[Any]:
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", _clean(value))
    ]


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = int(
            getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
        )
    except Exception:
        attributes = 0
    return bool(
        path.is_symlink()
        or attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    )


def _looks_like_direct_project(root: Path) -> bool:
    metadata_root = root / ASSET_METADATA_DIRECTORY_NAME
    if any((metadata_root / name).is_file() for name in MANIFEST_NAMES) or any(
        (root / name).is_file() for name in MANIFEST_NAMES
    ):
        return True
    try:
        children = list(root.iterdir())
    except Exception:
        return False
    visible_directories = [
        child
        for child in children
        if child.is_dir()
        and not child.name.startswith(".")
        and not _is_reparse_point(child)
    ]
    if not visible_directories:
        return True
    if any(
        child.is_file() and child.suffix.casefold() in IMAGE_EXTENSIONS
        for child in children
    ):
        return True
    taxonomy_keys = {
        _taxonomy_key(value)
        for value in _selectable_source_types()
    }
    return any(
        child.is_dir()
        and not _is_reparse_point(child)
        and _taxonomy_key(child.name) in taxonomy_keys
        for child in children
    )


def _discover_project_catalog(projects_root: Any) -> Dict[str, Any]:
    root_text = _project_root_text(projects_root) or str(DEFAULT_PROJECTS_ROOT)
    root = Path(root_text).expanduser()
    try:
        root = root.resolve()
    except Exception:
        root = Path(root_text)
    if not root.is_dir():
        raise ValueError(
            f"Projects root does not exist or is not a directory: {root}"
        )

    project_paths: List[Path]
    if _looks_like_direct_project(root):
        project_paths = [root]
    else:
        project_paths = []
        try:
            candidates = list(root.iterdir())
        except Exception as exc:
            raise ValueError(f"Unable to enumerate projects in {root}: {exc}") from exc
        for candidate in candidates:
            if len(project_paths) >= MAX_PROJECTS:
                break
            try:
                if not candidate.is_dir() or _is_reparse_point(candidate):
                    continue
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except Exception:
                continue
            project_paths.append(resolved)
        project_paths.sort(key=lambda value: _natural_key(value.name))

    projects = [
        {
            "project_id": _project_id(path),
            "project_uid": _project_uid(path),
            "name": path.name,
            "path": str(path).replace("\\", "/"),
        }
        for path in project_paths
    ]
    return {
        "catalog_root": str(root).replace("\\", "/"),
        "projects": projects,
        "warning": (
            f"Project catalog reached the {MAX_PROJECTS}-project safety limit."
            if len(projects) >= MAX_PROJECTS
            else ""
        ),
    }


def _taxonomy_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z]+", "", _clean(value).casefold())


def _asset_dimensions(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
            return max(0, int(width)), max(0, int(height))
    except Exception:
        return 0, 0


def _exr_header_dimensions(header: bytes) -> tuple[int, int] | None:
    """Read OpenEXR's dataWindow without requiring an optional OpenEXR plugin."""
    if len(header) < 9 or header[:4] != b"\x76\x2f\x31\x01":
        return None
    offset = 8

    def read_c_string(position: int) -> tuple[bytes, int]:
        end = header.find(b"\0", position)
        if end < 0:
            raise ValueError("OpenEXR header contains an unterminated field.")
        return header[position:end], end + 1

    while offset < len(header):
        name, offset = read_c_string(offset)
        if not name:
            break
        attribute_type, offset = read_c_string(offset)
        if offset + 4 > len(header):
            raise ValueError("OpenEXR header is truncated.")
        size = struct.unpack_from("<I", header, offset)[0]
        offset += 4
        if size > 16 * 1024 * 1024 or offset + size > len(header):
            raise ValueError("OpenEXR header attribute is invalid or truncated.")
        value = header[offset : offset + size]
        offset += size
        if name == b"dataWindow" and attribute_type == b"box2i" and size == 16:
            x_min, y_min, x_max, y_max = struct.unpack("<4i", value)
            width = x_max - x_min + 1
            height = y_max - y_min + 1
            if width <= 0 or height <= 0:
                raise ValueError("OpenEXR dataWindow has invalid dimensions.")
            return width, height
    raise ValueError("OpenEXR header has no valid dataWindow attribute.")


def _verified_image_dimensions(source: Any) -> tuple[int, int]:
    """Decode enough of an image to reject corrupt or zero-sized registrations."""
    header = b""
    if isinstance(source, (str, Path)):
        try:
            with Path(source).open("rb") as stream:
                header = stream.read(1024 * 1024)
        except Exception as exc:
            raise ValueError(f"Image data could not be read safely: {exc}") from exc
    elif hasattr(source, "read"):
        try:
            position = source.tell()
            header = source.read(1024 * 1024)
            source.seek(position)
        except Exception:
            header = b""
    if header[:4] == b"\x76\x2f\x31\x01":
        dimensions = _exr_header_dimensions(header)
        if dimensions is None:
            raise ValueError("OpenEXR image header is invalid.")
        return dimensions
    try:
        from PIL import Image

        with Image.open(source) as image:
            width, height = (int(image.size[0]), int(image.size[1]))
            image.verify()
    except Exception as exc:
        raise ValueError(f"Image data could not be decoded safely: {exc}") from exc
    if width <= 0 or height <= 0:
        raise ValueError("Image width and height must both be greater than zero.")
    return width, height


def _asset_content_probe(path: Path, size: int) -> str:
    """Hash bounded file samples so equal stat metadata cannot alias content."""

    sample_size = 32 * 1024
    digest = hashlib.sha256()
    digest.update(str(max(0, int(size))).encode("ascii"))
    with path.open("rb") as stream:
        first = stream.read(sample_size)
        digest.update(first)
        if size > sample_size:
            stream.seek(max(sample_size, size - sample_size))
            digest.update(stream.read(sample_size))
    return digest.hexdigest()


def _asset_file_facts(
    path: Path,
    *,
    project_uid: Any = "",
    relative_path: Any = "",
) -> tuple[Path, int, int, str]:
    """Return the stable path+size+mtime identity used by staged media work."""

    resolved = path.resolve()
    details = resolved.stat()
    if not resolved.is_file() or _is_reparse_point(resolved):
        raise ValueError("Image asset is not a regular file.")
    size = max(0, int(details.st_size))
    mtime_ns = max(
        0,
        int(
            getattr(
                details,
                "st_mtime_ns",
                int(float(details.st_mtime) * 1_000_000_000),
            )
        ),
    )
    portable_uid = _clean(project_uid)
    portable_relative = _clean(relative_path).replace("\\", "/").strip("/")
    if portable_uid and portable_relative:
        identity = f"project|{portable_uid}|{portable_relative.casefold()}"
    else:
        identity = os.path.normcase(str(resolved)).replace("\\", "/")
    content_probe = _asset_content_probe(resolved, size)
    signature_text = "|".join(
        (identity, str(size), str(mtime_ns), content_probe)
    )
    signature = hashlib.sha256(signature_text.encode("utf-8")).hexdigest()
    return resolved, size, mtime_ns, signature


def _thumbnail_cache_paths(
    signature: str,
    extension: str = "webp",
) -> tuple[Path, Path]:
    cache_root = Path(_ASSET_THUMBNAIL_CACHE_ROOT)
    safe_signature = signature if re.fullmatch(r"[0-9a-f]{64}", signature) else ""
    if not safe_signature:
        raise ValueError("Thumbnail cache signature is invalid.")
    safe_extension = extension if extension in {"webp", "png"} else "webp"
    return (
        cache_root / f"{safe_signature}.json",
        cache_root / f"{safe_signature}.{safe_extension}",
    )


def _read_persistent_thumbnail_cache(
    signature: str,
) -> tuple[bytes, str, int, int] | None:
    """Read one bounded local thumbnail entry without trusting cached paths."""

    try:
        metadata_path, _ = _thumbnail_cache_paths(signature)
        if (
            not metadata_path.is_file()
            or _is_reparse_point(metadata_path)
            or metadata_path.stat().st_size > 16 * 1024
        ):
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict) or metadata.get("signature") != signature:
            return None
        extension = _clean(metadata.get("extension")).casefold()
        if extension not in {"webp", "png"}:
            return None
        _, media_path = _thumbnail_cache_paths(signature, extension)
        media_size = media_path.stat().st_size
        if (
            not media_path.is_file()
            or _is_reparse_point(media_path)
            or media_size <= 0
            or media_size > 8 * 1024 * 1024
        ):
            return None
        width = max(0, int(metadata.get("width") or 0))
        height = max(0, int(metadata.get("height") or 0))
        payload = media_path.read_bytes()
        # File mtimes provide a low-cost persistent LRU across processes.
        try:
            os.utime(metadata_path, None)
            os.utime(media_path, None)
        except Exception:
            pass
        return payload, extension, width, height
    except Exception:
        return None


def _prune_persistent_thumbnail_cache(cache_root: Path) -> None:
    """Keep only a bounded set of cache entries and remove safe orphan files."""

    try:
        entries: List[tuple[int, int, Path, Path | None]] = []
        referenced_media: set[str] = set()
        for metadata_path in cache_root.glob("*.json"):
            if not re.fullmatch(r"[0-9a-f]{64}\.json", metadata_path.name):
                continue
            try:
                metadata_stat = metadata_path.stat()
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                extension = _clean(
                    metadata.get("extension") if isinstance(metadata, dict) else ""
                ).casefold()
                media_path = (
                    cache_root / f"{metadata_path.stem}.{extension}"
                    if extension in {"webp", "png"}
                    else None
                )
                media_size = (
                    media_path.stat().st_size
                    if media_path is not None and media_path.is_file()
                    else 0
                )
                if media_path is not None:
                    referenced_media.add(media_path.name)
                entries.append(
                    (
                        max(
                            int(metadata_stat.st_mtime_ns),
                            int(media_path.stat().st_mtime_ns)
                            if media_path is not None and media_path.is_file()
                            else 0,
                        ),
                        max(0, int(metadata_stat.st_size)) + max(0, int(media_size)),
                        metadata_path,
                        media_path,
                    )
                )
            except Exception:
                try:
                    metadata_path.unlink(missing_ok=True)
                except Exception:
                    pass
        entries.sort(key=lambda item: item[0])
        total_bytes = sum(item[1] for item in entries)
        while entries and (
            len(entries) > _ASSET_THUMBNAIL_CACHE_MAX_ENTRIES
            or total_bytes > _ASSET_THUMBNAIL_CACHE_MAX_BYTES
        ):
            _mtime, size, metadata_path, media_path = entries.pop(0)
            total_bytes -= size
            try:
                metadata_path.unlink(missing_ok=True)
            except Exception:
                pass
            if media_path is not None:
                try:
                    media_path.unlink(missing_ok=True)
                except Exception:
                    pass
        for media_path in cache_root.iterdir():
            if (
                media_path.suffix.casefold() not in {".webp", ".png"}
                or not re.fullmatch(r"[0-9a-f]{64}\.(?:webp|png)", media_path.name)
                or media_path.name in referenced_media
            ):
                continue
            try:
                media_path.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        return


@contextmanager
def _thumbnail_cache_process_lock(cache_root: Path):
    """Serialize cache commit/prune pairs across local Griptape processes."""

    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / _ASSET_THUMBNAIL_CACHE_PROCESS_LOCK_NAME
    if _is_reparse_point(lock_path):
        raise ValueError("Thumbnail cache lock must not be a reparse point.")
    deadline = time.monotonic() + ASSET_MANIFEST_LOCK_TIMEOUT_SECONDS
    descriptor = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.fstat(descriptor).st_size < 1:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        while not acquired:
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0)
                acquired = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Timed out waiting for thumbnail cache maintenance."
                    )
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.lockf(descriptor, fcntl.LOCK_UN, 1, 0)
            except Exception as exc:
                _diagnostic_exception("Thumbnail cache lock release failed", exc)
        try:
            os.close(descriptor)
        except Exception as exc:
            _diagnostic_exception("Thumbnail cache lock cleanup failed", exc)


def _write_persistent_thumbnail_cache(
    signature: str,
    payload: bytes,
    extension: str,
    width: int,
    height: int,
    *,
    prune: bool = True,
) -> None:
    global _ASSET_THUMBNAIL_CACHE_PRUNE_PENDING
    global _ASSET_THUMBNAIL_CACHE_WARNING_EMITTED
    try:
        metadata_path, media_path = _thumbnail_cache_paths(signature, extension)
        cache_root = metadata_path.parent
        cache_root.mkdir(parents=True, exist_ok=True)
        metadata = _json_text(
            {
                "schema": "hmb-image-thumbnail-cache",
                "version": 1,
                "signature": signature,
                "extension": extension,
                "width": max(0, int(width)),
                "height": max(0, int(height)),
            }
        ).encode("utf-8")
        nonce = f"{os.getpid()}.{uuid.uuid4().hex}"
        temporary_media = cache_root / f".{media_path.name}.{nonce}.tmp"
        temporary_metadata = cache_root / f".{metadata_path.name}.{nonce}.tmp"
        with _thumbnail_cache_process_lock(cache_root):
            try:
                temporary_media.write_bytes(payload)
                temporary_metadata.write_bytes(metadata)
                os.replace(temporary_media, media_path)
                os.replace(temporary_metadata, metadata_path)
                other_extension = "png" if extension == "webp" else "webp"
                _, other_path = _thumbnail_cache_paths(signature, other_extension)
                other_path.unlink(missing_ok=True)
            finally:
                temporary_media.unlink(missing_ok=True)
                temporary_metadata.unlink(missing_ok=True)
            if prune:
                _prune_persistent_thumbnail_cache(cache_root)
            else:
                _ASSET_THUMBNAIL_CACHE_PRUNE_PENDING = True
    except Exception as exc:
        if not _ASSET_THUMBNAIL_CACHE_WARNING_EMITTED:
            _ASSET_THUMBNAIL_CACHE_WARNING_EMITTED = True
            _diagnostic_warning("Persistent thumbnail cache write failed", exc)


def _generate_thumbnail_payload(path: Path) -> tuple[bytes, str, int, int]:
    from PIL import Image

    with Image.open(path) as image:
        image.seek(0)
        width, height = max(0, int(image.size[0])), max(0, int(image.size[1]))
        resampling = getattr(
            getattr(Image, "Resampling", Image),
            "LANCZOS",
            1,
        )
        image.thumbnail((360, 360), resampling)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert(
                "RGBA" if "transparency" in image.info else "RGB"
            )
        output = BytesIO()
        extension = "webp"
        try:
            image.save(output, format="WEBP", quality=76, method=4)
        except Exception:
            output = BytesIO()
            extension = "png"
            image.save(output, format="PNG", optimize=True)
    return output.getvalue(), extension, width, height


def _publish_thumbnail_payload(
    payload: bytes,
    extension: str,
    asset_library_id: str,
    signature: str,
) -> str:
    from griptape_nodes.retained_mode.griptape_nodes import (  # type: ignore
        GriptapeNodes,
    )

    safe_asset_id = re.sub(r"[^0-9A-Za-z_-]+", "_", asset_library_id)[:32]
    filename = f"hmb_asset_thumb_{safe_asset_id}_{signature[:24]}.{extension}"
    return _clean(
        GriptapeNodes.StaticFilesManager().save_static_file(payload, filename)
    )


def _flush_persistent_thumbnail_cache_prune() -> None:
    """Prune once after a staged hydration batch, not once per new image."""

    global _ASSET_THUMBNAIL_CACHE_PRUNE_PENDING
    with _ASSET_THUMBNAIL_LOCK:
        if not _ASSET_THUMBNAIL_CACHE_PRUNE_PENDING:
            return
        _ASSET_THUMBNAIL_CACHE_PRUNE_PENDING = False
        cache_root = Path(_ASSET_THUMBNAIL_CACHE_ROOT)
        try:
            with _thumbnail_cache_process_lock(cache_root):
                _prune_persistent_thumbnail_cache(cache_root)
        except Exception as exc:
            # Cache maintenance is fail-open; the next batch can retry it.
            _ASSET_THUMBNAIL_CACHE_PRUNE_PENDING = True
            _diagnostic_warning("Thumbnail cache prune deferred", exc)


def _asset_thumbnail_url(
    path: Path,
    asset_library_id: str,
    media_signature: Any = "",
) -> str:
    """Hydrate one browser thumbnail through a bounded persistent local cache."""

    try:
        resolved, _size, _mtime_ns, path_signature = _asset_file_facts(path)
        signature = _clean(media_signature) or path_signature
    except Exception:
        return ""

    with _ASSET_THUMBNAIL_LOCK:
        cached_url = _ASSET_THUMBNAIL_URLS.get(signature)
        if cached_url:
            _ASSET_THUMBNAIL_URLS.move_to_end(signature)
            return cached_url
        cached = _read_persistent_thumbnail_cache(signature)
        if cached is None:
            try:
                payload, extension, width, height = _generate_thumbnail_payload(
                    resolved
                )
            except Exception:
                return ""
            _write_persistent_thumbnail_cache(
                signature,
                payload,
                extension,
                width,
                height,
                prune=_ASSET_THUMBNAIL_CACHE_DEFER_COUNT <= 0,
            )
        else:
            payload, extension, _width, _height = cached
        try:
            url = _publish_thumbnail_payload(
                payload,
                extension,
                asset_library_id,
                signature,
            )
        except Exception:
            return ""
        if url:
            while (
                len(_ASSET_THUMBNAIL_URLS)
                >= _ASSET_THUMBNAIL_CACHE_MAX_ENTRIES
            ):
                try:
                    _ASSET_THUMBNAIL_URLS.popitem(last=False)
                except KeyError:
                    break
            _ASSET_THUMBNAIL_URLS[signature] = url
        return url


def _asset_thumbnail_url_for_media(
    path: Path,
    asset_library_id: str,
    media_signature: str,
) -> str:
    """Keep legacy two-argument test/host overrides source-compatible."""

    try:
        return _asset_thumbnail_url(path, asset_library_id, media_signature)
    except TypeError as exc:
        try:
            return _asset_thumbnail_url(path, asset_library_id)
        except TypeError:
            raise exc


def _thumbnail_url_is_live(media_signature: Any, thumbnail_url: Any) -> bool:
    """Return whether this process actually published the serialized URL."""

    signature = _clean(media_signature)
    url = _clean(thumbnail_url)
    if not signature or not url:
        return False
    with _ASSET_THUMBNAIL_LOCK:
        return _clean(_ASSET_THUMBNAIL_URLS.get(signature)) == url


def _flatten_import_values(value: Any) -> List[Any]:
    """Flatten aggregate inputs iteratively while ignoring cyclic containers."""
    flattened: List[Any] = []
    stack: List[tuple[Any, int]] = [(value, 0)]
    visited: set[int] = set()
    examined = 0
    while stack and len(flattened) < MAX_ASSETS and examined < MAX_INPUT_NODES:
        current, depth = stack.pop()
        examined += 1
        if current is None or depth > MAX_INPUT_NESTING:
            continue
        if isinstance(current, str):
            text = current.strip()
            if not text:
                continue
            if text.startswith("[") and depth < MAX_INPUT_NESTING:
                try:
                    stack.append((json.loads(text), depth + 1))
                    continue
                except Exception:
                    pass
            flattened.append(current)
            continue
        if isinstance(current, (list, tuple)):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            for item in reversed(current):
                stack.append((item, depth + 1))
            continue
        flattened.append(current)
    return flattened


def _canonical_import_input_identity(value: Any) -> str:
    """Fingerprint one authoritative IMAGE_IMPORT_IN aggregate without I/O.

    Griptape 0.122 reports one graph edit through both the connection hook and
    ``after_value_set``.  The descriptor intentionally hashes immutable input
    material instead of Python object identity, so an equal deep-copied host
    artifact coalesces with the first callback before dimensions/files are read.
    """

    descriptors: List[Dict[str, Any]] = []
    for raw in _flatten_import_values(value):
        artifact_value = _artifact_field(raw, "value")
        artifact_name = _clean(
            _artifact_field(raw, "name")
            or _artifact_field(raw, "filename")
        )
        byte_value: bytes | bytearray | memoryview | None = None
        if isinstance(raw, (bytes, bytearray, memoryview)):
            byte_value = raw
        elif isinstance(artifact_value, (bytes, bytearray, memoryview)):
            byte_value = artifact_value
        if byte_value is not None:
            descriptors.append(
                {
                    "kind": "bytes",
                    "length": len(byte_value),
                    "sha256": hashlib.sha256(byte_value).hexdigest(),
                    "name": artifact_name,
                }
            )
            continue
        reference: str = ""
        if isinstance(raw, Path):
            reference = str(raw)
        elif isinstance(raw, str):
            reference = raw.strip()
        elif isinstance(artifact_value, (str, Path)):
            reference = _clean(artifact_value)
        if reference:
            encoded = reference.encode("utf-8", errors="surrogatepass")
            descriptors.append(
                {
                    "kind": "reference",
                    "length": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "name": artifact_name,
                }
            )
            continue
        embedded = _artifact_field(raw, "base64")
        if isinstance(embedded, str) and embedded.strip():
            encoded = embedded.strip().encode("utf-8", errors="surrogatepass")
            descriptors.append(
                {
                    "kind": "reference",
                    "length": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "name": artifact_name,
                }
            )
            continue
        if callable(embedded):
            function = getattr(embedded, "__func__", embedded)
            descriptors.append(
                {
                    "kind": "callable-embedded",
                    "callable": (
                        f"{getattr(function, '__module__', '')}."
                        f"{getattr(function, '__qualname__', type(function).__qualname__)}"
                    ),
                    # Do not invoke opaque media merely to dedupe a callback.
                    # Same-object Griptape hook pairs coalesce; a new opaque
                    # owner is conservatively treated as a changed event and is
                    # read once by normal validation.
                    "owner_id": id(getattr(embedded, "__self__", raw)),
                    "name": artifact_name,
                }
            )
            continue
        # Unsupported values are rejected/ignored by normal import validation.
        # Keep only a stable type marker; a failed application never commits the
        # resulting identity latch.
        descriptors.append(
            {
                "kind": "unsupported",
                "type": f"{type(raw).__module__}.{type(raw).__qualname__}",
                "name": artifact_name,
            }
        )
    canonical = json.dumps(
        descriptors,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _state_has_live_imports(state: Any) -> bool:
    normalized = _normalize_state(state)
    return any(
        _clean(asset.get("source_kind")) == "user"
        and _non_negative_int(asset.get("import_index")) > 0
        for asset in normalized.get("assets", [])
        if isinstance(asset, dict)
    )


_IMPORT_EMBEDDED_UNSET = object()


def _import_payload_size(
    value: Any,
    resolved_embedded: Any = _IMPORT_EMBEDDED_UNSET,
) -> int:
    """Return a conservative byte estimate without decoding embedded media."""
    artifact_value = _artifact_field(value, "value")
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    if isinstance(artifact_value, (bytes, bytearray)):
        return len(artifact_value)
    embedded = (
        _artifact_field(value, "base64")
        if resolved_embedded is _IMPORT_EMBEDDED_UNSET
        else resolved_embedded
    )
    if callable(embedded):
        try:
            embedded = embedded()
        except Exception:
            embedded = None
    if not isinstance(embedded, str) and isinstance(value, str):
        embedded = value if value.startswith("data:image/") else None
    if isinstance(embedded, str) and embedded:
        encoded = embedded.split(",", 1)[1] if embedded.startswith("data:") and "," in embedded else embedded
        return min(MAX_IMPORT_BYTES + 1, (len(encoded) * 3) // 4 + 3)
    reference = value if isinstance(value, (str, Path)) else artifact_value
    if isinstance(reference, (str, Path)):
        text = _clean(reference)
        if text and not text.startswith(("http://", "https://", "blob:", "data:")):
            try:
                candidate = Path(_decode_file_uri(text)).expanduser().resolve()
                if candidate.is_file():
                    return max(0, int(candidate.stat().st_size))
            except Exception:
                pass
    return 0


def _artifact_field(value: Any, field: str) -> Any:
    if isinstance(value, dict):
        return value.get(field)
    try:
        return getattr(value, field, None)
    except Exception:
        return None


def _decode_file_uri(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme.casefold() != "file":
        return value
    path = unquote(parsed.path or "")
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return path


def _base64_dimensions(value: str) -> tuple[int, int]:
    payload = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    if not payload or len(payload) > MAX_IMPORT_BASE64_CHARS:
        return 0, 0
    try:
        encoded = re.sub(r"\s+", "", payload)
        decoded = base64.b64decode(encoded, validate=True)
        if len(decoded) > MAX_IMPORT_BYTES:
            return 0, 0
        return _verified_image_dimensions(BytesIO(decoded))
    except Exception:
        return 0, 0


def _bytes_dimensions(value: bytes) -> tuple[int, int]:
    if not value or len(value) > MAX_IMPORT_BYTES:
        return 0, 0
    try:
        return _verified_image_dimensions(BytesIO(value))
    except Exception:
        return 0, 0


def _import_record(
    value: Any,
    index: int,
    resolved_embedded: Any = _IMPORT_EMBEDDED_UNSET,
) -> tuple[Dict[str, Any], Any] | None:
    media_value = value
    reference = ""
    media_ref_kind = "artifact"
    artifact_value = _artifact_field(value, "value")
    artifact_name = _clean(
        _artifact_field(value, "name")
        or _artifact_field(value, "filename")
    )
    artifact_bytes = (
        bytes(artifact_value)
        if isinstance(artifact_value, (bytes, bytearray))
        else bytes(value)
        if isinstance(value, (bytes, bytearray))
        else None
    )
    if isinstance(value, Path):
        reference = str(value)
    elif isinstance(value, str):
        reference = value.strip()
    elif isinstance(artifact_value, str):
        reference = artifact_value.strip()
    elif artifact_bytes:
        reference = "bytes:" + hashlib.sha256(artifact_bytes).hexdigest()
        media_ref_kind = "bytes"
    else:
        embedded = (
            _artifact_field(value, "base64")
            if resolved_embedded is _IMPORT_EMBEDDED_UNSET
            else resolved_embedded
        )
        if isinstance(embedded, str) and embedded.strip():
            reference = embedded.strip()
            media_ref_kind = "embedded"
            if (
                resolved_embedded is not _IMPORT_EMBEDDED_UNSET
                and callable(_artifact_field(value, "base64"))
            ):
                # Preserve the once-resolved payload so output synchronization
                # does not invoke the opaque provider a second time.
                media_value = reference
        elif callable(embedded):
            try:
                embedded = embedded()
            except Exception:
                embedded = None
            if isinstance(embedded, str) and embedded.strip():
                reference = embedded.strip()
                media_ref_kind = "embedded"
                media_value = reference
    if not reference:
        return None

    width = 0
    height = 0
    display_reference = ""
    thumbnail_path: Path | None = None
    identity_material = reference
    image_name = ""
    extension = ""
    if media_ref_kind == "bytes" and artifact_bytes is not None:
        identity_material = hashlib.sha256(artifact_bytes).hexdigest()
        width, height = _bytes_dimensions(artifact_bytes)
        name_path = Path(artifact_name) if artifact_name else None
        image_name = (
            name_path.stem
            if name_path is not None and name_path.stem
            else f"Imported Image {index:02d}"
        )
        extension = (
            name_path.suffix.casefold()
            if name_path is not None
            and name_path.suffix.casefold() in IMAGE_EXTENSIONS
            else ""
        )
    elif media_ref_kind == "embedded" or reference.startswith("data:image/"):
        media_ref_kind = "embedded"
        identity_material = hashlib.sha256(reference.encode("utf-8")).hexdigest()
        width, height = _base64_dimensions(reference)
        image_name = (
            Path(artifact_name).stem
            if artifact_name and Path(artifact_name).stem
            else f"Imported Image {index:02d}"
        )
        extension = (
            Path(artifact_name).suffix.casefold()
            if artifact_name
            and Path(artifact_name).suffix.casefold() in IMAGE_EXTENSIONS
            else _embedded_extension(reference)
        )
    elif reference.startswith(("http://", "https://", "blob:")):
        media_ref_kind = "url"
        display_reference = reference
        parsed_path = unquote(urlparse(reference).path)
        image_name = Path(parsed_path).stem or f"Imported Image {index:02d}"
        extension = Path(parsed_path).suffix.casefold()
    else:
        path_text = _decode_file_uri(reference)
        path = Path(path_text).expanduser()
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if resolved.is_file() and resolved.suffix.casefold() in IMAGE_EXTENSIONS:
            media_ref_kind = "path"
            display_reference = str(resolved).replace("\\", "/")
            identity_material = display_reference.casefold()
            image_name = resolved.stem
            extension = resolved.suffix.casefold()
            width, height = _asset_dimensions(resolved)
            thumbnail_path = resolved
            media_value = display_reference
        else:
            media_ref_kind = "url" if ":" in reference else "artifact"
            display_reference = reference
            image_name = Path(reference).stem or f"Imported Image {index:02d}"
            extension = Path(reference).suffix.casefold()

    source_uid = "import:" + hashlib.sha256(
        f"{media_ref_kind}\n{identity_material}".encode("utf-8")
    ).hexdigest()[:24]
    thumbnail_url = (
        _asset_thumbnail_url(thumbnail_path, source_uid)
        if thumbnail_path is not None
        else ""
    )
    asset_id_base = re.sub(r"\s+", "_", image_name).strip("_") or f"Import_{index:02d}"
    record = {
        "asset_library_id": source_uid,
        "source_uid": source_uid,
        "source_kind": "user",
        "asset_project_uid": "",
        "asset_id": asset_id_base,
        "image_name": image_name,
        "path": display_reference,
        "thumbnail_url": thumbnail_url,
        "relative_path": "",
        "extension": extension,
        "width": width,
        "height": height,
        # New imports are intentionally unclassified.  Legacy taxonomy values
        # are never inferred from their folder or copied from a previous schema.
        "image_main_type": IMAGE_MAIN_TYPE_UNCLASSIFIED,
        "image_sub_type": "",
        "source_type": IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
        "custom_source_type": "",
        "scope_candidate": "",
        "color_pick_candidates": [],
        "selected": True,
        "selection_order": 0,
        "import_index": index,
        "media_ref_kind": media_ref_kind,
        "connected": True,
    }
    return record, media_value


def _normalize_import_input(
    value: Any,
    previous_assets: Sequence[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    previous = {
        _clean(asset.get("source_uid") or asset.get("asset_library_id")): asset
        for asset in previous_assets
        if isinstance(asset, dict)
        and _clean(asset.get("source_kind")) == "user"
    }
    imports: List[Dict[str, Any]] = []
    media_by_uid: Dict[str, Any] = {}
    seen: set[str] = set()
    flattened = _flatten_import_values(value)
    total_bytes = 0
    for index, raw in enumerate(flattened, start=1):
        artifact_value = _artifact_field(raw, "value")
        has_direct_value = bool(
            isinstance(raw, (str, Path, bytes, bytearray, memoryview))
            or isinstance(
                artifact_value,
                (str, Path, bytes, bytearray, memoryview),
            )
        )
        resolved_embedded: Any = _IMPORT_EMBEDDED_UNSET
        if not has_direct_value:
            resolved_embedded = _artifact_field(raw, "base64")
            if callable(resolved_embedded):
                try:
                    resolved_embedded = resolved_embedded()
                except Exception:
                    resolved_embedded = None
        item_bytes = _import_payload_size(raw, resolved_embedded)
        if item_bytes > MAX_IMPORT_BYTES:
            raise ValueError(
                f"Imported image {index} exceeds the "
                f"{MAX_IMPORT_BYTES // (1024 * 1024)} MiB per-image safety budget."
            )
        total_bytes += item_bytes
        if total_bytes > MAX_IMPORT_TOTAL_BYTES:
            raise ValueError(
                "Combined IMAGE_IMPORT_IN media exceeds the configured "
                f"{MAX_IMPORT_TOTAL_BYTES // (1024 * 1024)} MiB safety budget. "
                "Raise HMB_IMAGE_IMPORT_TOTAL_BYTES for an approved larger batch."
            )
        imported = _import_record(raw, index, resolved_embedded)
        if imported is None:
            continue
        record, media_value = imported
        uid = record["source_uid"]
        if uid in seen:
            continue
        seen.add(uid)
        prior = previous.get(uid)
        if prior is not None:
            for field in (
                "asset_id",
                "image_name",
                "selected",
                "selection_order",
            ):
                if field in prior:
                    record[field] = prior[field]
        imports.append(record)
        media_by_uid[uid] = media_value
    return imports, media_by_uid


def _embedded_extension(value: str) -> str:
    if value.startswith("data:image/"):
        mime = value[11:].split(";", 1)[0].split(",", 1)[0].casefold()
        if mime == "jpeg":
            return ".jpg"
        if re.fullmatch(r"[a-z0-9.+-]+", mime or ""):
            candidate = f".{mime}"
            if candidate in IMAGE_EXTENSIONS:
                return candidate
    return ".png"


def _project_id(root: Path) -> str:
    return root.name


def _project_identity_key(value: Any) -> str:
    """Return the mount-independent logical identity used by shared projects."""
    return unicodedata.normalize("NFC", _clean(value)).casefold()


def _project_uid_from_id(project_id: Any) -> str:
    identity = _project_identity_key(project_id)
    digest = hashlib.sha256(
        f"hmb-image-project-v2\n{identity}".encode("utf-8")
    ).hexdigest()[:24]
    return f"hmbp2:{digest}"


def _project_uid(root: Path) -> str:
    # A drive letter, mapped drive, and UNC alias can all name the same shared
    # project.  The project folder name is already the identity component used
    # by asset_library_id, so use the same logical identity here instead of an
    # absolute-path hash.
    return _project_uid_from_id(_project_id(root))


def _valid_project_cache_uid(value: Any) -> str:
    candidate = _clean(value).casefold()
    if re.fullmatch(r"hmbpc1:[0-9a-f]{32,64}", candidate):
        return candidate
    return ""


def _invalidate_project_cache_uid(root: Path) -> None:
    try:
        root_key = os.path.normcase(str(root.resolve()))
    except Exception:
        return
    with _ASSET_PROJECT_CACHE_UID_LOCK:
        stale = [key for key in _ASSET_PROJECT_CACHE_UIDS if key[0] == root_key]
        for key in stale:
            _ASSET_PROJECT_CACHE_UIDS.pop(key, None)


def _project_cache_uid(root: Path) -> str:
    """Return a cache identity that is portable yet separates same-name shows.

    A manifest-backed UUID survives mapped-drive/UNC aliases and project copies.
    Projects that have never written managed metadata fall back to the directory
    file identity, which is still safe for independent same-named projects.
    """

    resolved = root.resolve()
    root_key = os.path.normcase(str(resolved))
    try:
        manifest_signature = _asset_manifest_signature(resolved)
    except Exception:
        manifest_signature = ""
    cache_key = (root_key, manifest_signature)
    with _ASSET_PROJECT_CACHE_UID_LOCK:
        cached = _ASSET_PROJECT_CACHE_UIDS.get(cache_key)
        if cached:
            _ASSET_PROJECT_CACHE_UIDS.move_to_end(cache_key)
            return cached

    persisted = ""
    try:
        manifest_path = _existing_asset_manifest_path(resolved)
        if (
            manifest_path is not None
            and manifest_path.is_file()
            and not _is_reparse_point(manifest_path)
            and manifest_path.stat().st_size <= 2 * 1024 * 1024
        ):
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                persisted = _valid_project_cache_uid(
                    payload.get(_ASSET_PROJECT_CACHE_UID_FIELD)
                )
    except Exception:
        persisted = ""

    if persisted:
        identity = persisted
    else:
        details = resolved.stat()
        device = max(0, int(getattr(details, "st_dev", 0) or 0))
        inode = max(0, int(getattr(details, "st_ino", 0) or 0))
        stable_location = (
            f"file-id|{device}|{inode}"
            if device or inode
            else f"path|{root_key}"
        )
        digest = hashlib.sha256(
            (
                f"hmb-image-project-cache-v1\n"
                f"{_project_identity_key(_project_id(resolved))}\n{stable_location}"
            ).encode("utf-8")
        ).hexdigest()[:32]
        identity = f"{_ASSET_PROJECT_CACHE_UID_PREFIX}{digest}"

    with _ASSET_PROJECT_CACHE_UID_LOCK:
        _ASSET_PROJECT_CACHE_UIDS[cache_key] = identity
        _ASSET_PROJECT_CACHE_UIDS.move_to_end(cache_key)
        while len(_ASSET_PROJECT_CACHE_UIDS) > _ASSET_PROJECT_CACHE_UID_LIMIT:
            _ASSET_PROJECT_CACHE_UIDS.popitem(last=False)
    return identity


def _match_catalog_project(
    projects: Sequence[Dict[str, Any]],
    *,
    previous_path: Any = "",
    previous_uid: Any = "",
    previous_project_id: Any = "",
) -> Dict[str, Any] | None:
    """Restore one selection across drive-letter/UNC aliases and v1 UIDs."""
    path_key = _clean(previous_path).replace("\\", "/").casefold()
    if path_key:
        exact = [
            item
            for item in projects
            if _clean(item.get("path")).replace("\\", "/").casefold()
            == path_key
        ]
        if len(exact) == 1:
            return exact[0]

    uid = _clean(previous_uid)
    if uid:
        uid_matches = [
            item
            for item in projects
            if _clean(item.get("project_uid")) == uid
        ]
        if len(uid_matches) == 1:
            return uid_matches[0]

    project_key = _project_identity_key(previous_project_id)
    if project_key:
        legacy_matches = [
            item
            for item in projects
            if _project_identity_key(item.get("project_id")) == project_key
        ]
        if len(legacy_matches) == 1:
            return legacy_matches[0]
    return None


def _asset_library_id(project_id: str, relative_path: str) -> str:
    payload = f"{project_id}\n{relative_path.casefold()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _is_user_import_relative_path(value: Any) -> bool:
    relative = Path(_clean(value).replace("\\", "/"))
    directory_keys = [_taxonomy_key(part) for part in relative.parts[:-1]]
    return bool(
        directory_keys
        and (
            directory_keys[0] in {"user", "userimports"}
            or (
                directory_keys[0] == "custom"
                and len(directory_keys) > 1
                and directory_keys[1] in {"user", "userimports"}
            )
        )
    )


def _verified_project_relative_path(
    asset: Dict[str, Any],
    state: Dict[str, Any],
    manifest_records: Dict[str, Dict[str, Any]] | None = None,
) -> str:
    """Return the trusted project-relative path, or blank for non-assets.

    Frontend state is not sufficient to grant verified-asset authority. The
    selected file must still resolve inside the active project, match the
    server-derived library identity, and not be an IMAGE_IMPORT_IN cache.
    """
    if (
        _clean(asset.get("source_kind")).casefold() != "project"
        or not bool(asset.get("registered"))
    ):
        return ""
    project_root = _clean(state.get("project_root"))
    project_id = _clean(state.get("project_id"))
    project_uid = _clean(state.get("project_uid"))
    asset_project_uid = _clean(asset.get("asset_project_uid"))
    if (
        not project_root
        or not project_id
        or not project_uid
        or asset_project_uid != project_uid
    ):
        return ""
    root = Path(project_root)
    path = Path(_clean(asset.get("path")))
    try:
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        relative = resolved_path.relative_to(resolved_root)
    except Exception:
        return ""
    if (
        not resolved_path.is_file()
        or resolved_path.suffix.casefold() not in IMAGE_EXTENSIONS
        or _is_reparse_point(resolved_path)
    ):
        return ""
    relative_text = relative.as_posix()
    if (
        _is_user_import_relative_path(relative_text)
        or _clean(asset.get("asset_library_id"))
        != _asset_library_id(project_id, relative_text)
    ):
        return ""
    try:
        records = (
            manifest_records
            if isinstance(manifest_records, dict)
            else _read_asset_manifest(resolved_root)
        )
        manifest_record = records.get(relative_text.casefold())
    except Exception:
        return ""
    if not isinstance(manifest_record, dict):
        return ""
    manifest_taxonomy = _normalize_image_taxonomy_fields(manifest_record)
    authoritative_fields = (
        ("asset_id", _clean(manifest_record.get("asset_id"))),
        (
            "image_name",
            _clean(manifest_record.get("image_name") or manifest_record.get("name")),
        ),
        ("image_main_type", manifest_taxonomy["image_main_type"]),
        ("image_sub_type", manifest_taxonomy["image_sub_type"]),
        ("source_type", manifest_taxonomy["source_type"]),
        ("custom_source_type", manifest_taxonomy["custom_source_type"]),
        (
            "scope_candidate",
            manifest_taxonomy["scope_candidate"],
        ),
    )
    if any(
        expected and _clean(asset.get(field)) != expected
        for field, expected in authoritative_fields
    ):
        return ""
    return relative_text


def _asset_metadata_directory(root: Path, *, create: bool = False) -> Path:
    """Return the hidden project-management directory without following redirects."""
    resolved_root = root.resolve()
    metadata_root = resolved_root / ASSET_METADATA_DIRECTORY_NAME
    if create:
        metadata_root.mkdir(exist_ok=True)
    if metadata_root.exists():
        if not metadata_root.is_dir() or _is_reparse_point(metadata_root):
            raise ValueError(
                f"{ASSET_METADATA_DIRECTORY_NAME} must be a regular project directory."
            )
        try:
            metadata_root.resolve().relative_to(resolved_root)
        except Exception as exc:
            raise ValueError(
                f"{ASSET_METADATA_DIRECTORY_NAME} resolves outside the project."
            ) from exc
    return metadata_root


def _existing_asset_manifest_path(root: Path) -> Path | None:
    """Prefer the managed layout while retaining read compatibility with root files."""
    metadata_root = _asset_metadata_directory(root)
    candidates = [
        *(metadata_root / name for name in MANIFEST_NAMES),
        *(root.resolve() / name for name in MANIFEST_NAMES),
    ]
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _asset_manifest_path(root: Path) -> Path:
    """Return the canonical writable manifest path inside the .json directory."""
    return _asset_metadata_directory(root, create=True) / MANIFEST_NAMES[0]


def _cleanup_legacy_asset_metadata(root: Path) -> None:
    """Best-effort cleanup after the canonical .json manifest is durable."""
    resolved_root = root.resolve()
    metadata_root = _asset_metadata_directory(resolved_root)
    obsolete_paths = [
        *(resolved_root / name for name in MANIFEST_NAMES),
        resolved_root / ASSET_MANIFEST_LOCK_NAME,
        *(metadata_root / name for name in MANIFEST_NAMES[1:]),
    ]
    for path in obsolete_paths:
        if not path.exists():
            continue
        if _is_reparse_point(path):
            _diagnostic_warning("Legacy asset metadata cleanup skipped", path)
            continue
        try:
            path.unlink()
        except OSError as exc:
            # A mixed-version client may still hold the former root lock. The
            # canonical write remains valid and the next writer retries cleanup.
            _diagnostic_warning("Legacy asset metadata cleanup deferred", exc)


def _asset_manifest_lock(root: Path) -> threading.Lock:
    try:
        key = str(root.resolve()).casefold()
    except Exception:
        key = str(root).casefold()
    with _ASSET_MANIFEST_LOCK_GUARD:
        return _ASSET_MANIFEST_LOCKS.setdefault(key, threading.Lock())


@contextmanager
def _asset_manifest_process_lock(root: Path):
    """Serialize manifest writers with a persistent OS/SMB byte-range lock."""
    lock_path = (
        _asset_metadata_directory(root, create=True) / ASSET_MANIFEST_LOCK_NAME
    )
    if _is_reparse_point(lock_path):
        raise ValueError(
            "Image asset manifest lock must not be a symlink or reparse point."
        )
    deadline = time.monotonic() + ASSET_MANIFEST_LOCK_TIMEOUT_SECONDS
    descriptor = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.fstat(descriptor).st_size < 1:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        while not acquired:
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0)
                acquired = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Timed out waiting for another user to finish updating "
                        "the shared image asset manifest."
                    )
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.lockf(descriptor, fcntl.LOCK_UN, 1, 0)
            except Exception as exc:
                _diagnostic_exception("Manifest lock release failed", exc)
        try:
            os.close(descriptor)
        except Exception as exc:
            _diagnostic_exception("Manifest lock descriptor cleanup failed", exc)


def _asset_manifest_signature(root: Path) -> str:
    """Return a low-cost signature that changes after an atomic manifest edit."""
    root = root.resolve()
    root_stat = root.stat()
    if not root.is_dir():
        raise ValueError(f"Project root is not a directory: {root}")
    manifest_path = _existing_asset_manifest_path(root)
    if manifest_path is None:
        payload = f"missing|{root_stat.st_dev}|{root_stat.st_ino}"
    else:
        if _is_reparse_point(manifest_path):
            raise ValueError(
                "Image asset manifest must not be a symlink or reparse point."
            )
        manifest_stat = manifest_path.stat()
        payload = "|".join(
            (
                manifest_path.relative_to(root).as_posix().casefold(),
                str(manifest_stat.st_size),
                str(manifest_stat.st_mtime_ns),
                str(manifest_stat.st_ctime_ns),
                str(manifest_stat.st_dev),
                str(manifest_stat.st_ino),
            )
        )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _folder_metadata_signature_from_inventory(
    root: Path,
    folder_paths: Sequence[str],
    image_paths: Sequence[Path],
) -> str:
    digest = hashlib.sha256()
    directory_count = 0
    image_count = 0
    for relative in sorted(set(folder_paths), key=_natural_key)[:MAX_FOLDERS]:
        try:
            stat_result = (root / Path(relative)).stat()
        except Exception:
            continue
        directory_count += 1
        digest.update(
            (
                f"d|{relative.casefold()}|{stat_result.st_mtime_ns}|"
                f"{getattr(stat_result, 'st_ctime_ns', 0)}\n"
            ).encode("utf-8")
        )
    for candidate in sorted(
        image_paths,
        key=lambda path: str(path).casefold(),
    )[:MAX_ASSETS]:
        try:
            relative = candidate.relative_to(root).as_posix()
            stat_result = candidate.stat()
        except Exception:
            continue
        image_count += 1
        digest.update(
            (
                f"f|{relative.casefold()}|{stat_result.st_size}|"
                f"{stat_result.st_mtime_ns}|"
                f"{getattr(stat_result, 'st_ctime_ns', 0)}\n"
            ).encode("utf-8")
        )
    digest.update(f"counts|{directory_count}|{image_count}".encode("utf-8"))
    return digest.hexdigest()[:24]


def _project_folder_metadata_signature(project_root: Any) -> str:
    """Hash bounded image/directory metadata without opening image content.

    Network file notification delivery is not reliable enough to be the sole
    authority.  This intentionally cheap fallback sees raw files copied by a
    teammate while leaving dimensions/thumbnail decoding to the eventual
    changed-catalog scan.
    """

    root_text = _project_root_text(project_root)
    if not root_text:
        return ""
    root = Path(root_text).expanduser().resolve()
    if not root.is_dir() or _is_reparse_point(root):
        raise ValueError(f"Project root is unavailable: {root}")
    folder_paths: List[str] = []
    image_paths: List[Path] = []
    for current_text, directory_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_text)
        safe_directories: List[str] = []
        for name in sorted(directory_names, key=_natural_key):
            if name.startswith(".") or len(folder_paths) >= MAX_FOLDERS:
                continue
            candidate = current / name
            try:
                relative = candidate.relative_to(root).as_posix()
                if _is_reparse_point(candidate):
                    continue
            except Exception:
                continue
            safe_directories.append(name)
            folder_paths.append(relative)
        directory_names[:] = safe_directories
        for name in sorted(file_names, key=_natural_key):
            if len(image_paths) >= MAX_ASSETS:
                break
            candidate = current / name
            if candidate.suffix.casefold() not in IMAGE_EXTENSIONS:
                continue
            try:
                relative = candidate.relative_to(root)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if _is_reparse_point(candidate):
                    continue
            except Exception:
                continue
            image_paths.append(candidate)
    return _folder_metadata_signature_from_inventory(root, folder_paths, image_paths)


def _asset_manifest_cache_root_key(root: Path) -> str:
    return os.path.normcase(str(root.resolve()))


def _invalidate_asset_manifest_cache(root: Path) -> None:
    """Drop cached parses for one project after a local manifest write."""
    try:
        root_key = _asset_manifest_cache_root_key(root)
    except Exception:
        return
    with _ASSET_MANIFEST_CACHE_LOCK:
        stale_keys = [
            key for key in _ASSET_MANIFEST_CACHE if key[0] == root_key
        ]
        for key in stale_keys:
            _ASSET_MANIFEST_CACHE.pop(key, None)


def _load_asset_manifest_document(
    root: Path,
) -> tuple[Path, Any, List[Any]]:
    """Load the editable manifest without discarding legacy container metadata."""
    manifest_path = _asset_manifest_path(root)
    source_path = _existing_asset_manifest_path(root)
    if source_path is None:
        payload: Any = {
            "schema": ASSET_MANIFEST_SCHEMA,
            "version": ASSET_MANIFEST_VERSION,
            "assets": [],
        }
        return manifest_path, payload, payload["assets"]
    if _is_reparse_point(source_path):
        raise ValueError("Image asset manifest must not be a symlink or reparse point.")
    try:
        if source_path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Image asset manifest exceeds 2 MiB.")
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Unable to read {source_path.name}: {exc}") from exc
    records = payload.get("assets") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"{manifest_path.name} must contain an assets list.")
    if len(records) > MAX_ASSETS:
        raise ValueError(
            f"{manifest_path.name} exceeds the {MAX_ASSETS}-asset safety limit."
        )
    return manifest_path, payload, records


def _write_asset_manifest_record(root: Path, record: Dict[str, Any]) -> Path:
    """Atomically create one record; an existing project-relative path is immutable."""
    lock = _asset_manifest_lock(root)
    with lock:
        with _asset_manifest_process_lock(root):
            return _write_asset_manifest_record_locked(root, record)


def _write_asset_manifest_record_locked(
    root: Path,
    record: Dict[str, Any],
) -> Path:
    """Write one record while both in-process and shared-file locks are held."""
    relative_text = _clean(record.get("path")).replace("\\", "/")
    relative_key = relative_text.casefold()
    manifest_path, payload, records = _load_asset_manifest_document(root)
    matching_indices = [
        index
        for index, raw in enumerate(records)
        if isinstance(raw, dict)
        and _clean(raw.get("path") or raw.get("relative_path"))
        .replace("\\", "/")
        .casefold()
        == relative_key
    ]
    if len(matching_indices) > 1:
        raise ValueError(
            f"{manifest_path.name} contains duplicate records for {relative_text}."
        )
    if not matching_indices and len(records) >= MAX_ASSETS:
        raise ValueError(
            f"{manifest_path.name} reached the {MAX_ASSETS}-asset safety limit."
        )

    asset_id_key = _clean(record.get("asset_id")).casefold()
    image_name_key = _clean(record.get("image_name")).casefold()
    for index, raw in enumerate(records):
        if not isinstance(raw, dict) or index in matching_indices:
            continue
        other_path = _clean(raw.get("path") or raw.get("relative_path"))
        if (
            asset_id_key
            and _clean(raw.get("asset_id")).casefold() == asset_id_key
        ):
            raise ValueError(
                f"Asset ID {_clean(record.get('asset_id'))!r} is already registered "
                f"for {other_path or 'another image'}."
            )
        if (
            image_name_key
            and _clean(raw.get("image_name") or raw.get("name")).casefold()
            == image_name_key
        ):
            raise ValueError(
                f"Image Name {_clean(record.get('image_name'))!r} is already "
                f"registered for {other_path or 'another image'}."
            )

    updated_records = list(records)
    if matching_indices:
        raise ValueError(
            "This image asset is already registered and cannot be edited. "
            "Only unregistered assets can be added."
        )
    else:
        updated_records.append(dict(record))

    persisted_cache_uid = (
        _valid_project_cache_uid(payload.get(_ASSET_PROJECT_CACHE_UID_FIELD))
        if isinstance(payload, dict)
        else ""
    )
    if not persisted_cache_uid:
        # Freeze the already-active directory identity into managed metadata.
        # Generating a different UUID here would invalidate every media
        # signature during the first Add and make the just-hydrated cards go
        # blank until a later full catalog refresh.
        persisted_cache_uid = _valid_project_cache_uid(
            _project_cache_uid(root)
        ) or f"{_ASSET_PROJECT_CACHE_UID_PREFIX}{uuid.uuid4().hex}"
    if isinstance(payload, dict):
        output_payload: Any = dict(payload)
    else:
        output_payload = {
            "schema": ASSET_MANIFEST_SCHEMA,
            "version": ASSET_MANIFEST_VERSION,
        }
    output_payload[_ASSET_PROJECT_CACHE_UID_FIELD] = persisted_cache_uid
    output_payload["assets"] = updated_records
    encoded = json.dumps(
        output_payload,
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Image asset manifest would exceed 2 MiB.")

    temporary = manifest_path.with_name(
        f".{manifest_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, manifest_path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    _invalidate_asset_manifest_cache(root)
    _invalidate_project_cache_uid(root)
    _cleanup_legacy_asset_metadata(root)
    return manifest_path


def _read_asset_manifest(root: Path) -> Dict[str, Dict[str, Any]]:
    resolved_root = root.resolve()
    signature = _asset_manifest_signature(resolved_root)
    root_key = _asset_manifest_cache_root_key(resolved_root)
    cache_key = (root_key, signature)
    with _ASSET_MANIFEST_CACHE_LOCK:
        cached = _ASSET_MANIFEST_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    manifest_path = _existing_asset_manifest_path(resolved_root)
    if manifest_path is None:
        overrides: Dict[str, Dict[str, Any]] = {}
    else:
        try:
            if manifest_path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Image asset manifest exceeds 2 MiB.")
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Unable to read {manifest_path.name}: {exc}") from exc
        records = payload.get("assets") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError(f"{manifest_path.name} must contain an assets list.")
        overrides = {}
        for raw in records[:MAX_ASSETS]:
            if not isinstance(raw, dict):
                continue
            relative_text = _clean(
                raw.get("path") or raw.get("relative_path")
            ).replace(
                "\\",
                "/",
            )
            if relative_text:
                overrides[relative_text.casefold()] = raw

    # Do not cache a parse under an obsolete signature if another workstation
    # atomically replaces the shared manifest while this process is reading it.
    if _asset_manifest_signature(resolved_root) == signature:
        with _ASSET_MANIFEST_CACHE_LOCK:
            stale_keys = [
                key for key in _ASSET_MANIFEST_CACHE if key[0] == root_key
            ]
            for key in stale_keys:
                _ASSET_MANIFEST_CACHE.pop(key, None)
            while len(_ASSET_MANIFEST_CACHE) >= _ASSET_MANIFEST_CACHE_LIMIT:
                _ASSET_MANIFEST_CACHE.pop(next(iter(_ASSET_MANIFEST_CACHE)))
            _ASSET_MANIFEST_CACHE[cache_key] = dict(overrides)
    return overrides


def _scan_project_assets(project_root: Any) -> Dict[str, Any]:
    """Scan one selected project and classify image files with common taxonomy."""
    root_text = _project_root_text(project_root)
    if not root_text:
        return {
            "project_root": "",
            "project_id": "",
            "project_uid": "",
            "project_cache_uid": "",
            "manifest_signature": "",
            "folder_signature": "",
            "folders": [],
            "assets": [],
            "warnings": [],
        }
    root = Path(root_text).expanduser()
    try:
        root = root.resolve()
    except Exception:
        root = Path(root_text)
    if not root.is_dir():
        raise ValueError(f"Project root does not exist or is not a directory: {root}")

    project_id = _project_id(root)
    project_uid = _project_uid(root)
    project_cache_uid = _project_cache_uid(root)
    manifest_signature = _asset_manifest_signature(root)
    manifest_overrides = _read_asset_manifest(root)
    paths: List[Path] = []
    folders: List[str] = []
    warnings: List[str] = []
    for current_text, directory_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_text)
        safe_directories: List[str] = []
        for name in directory_names:
            if name.startswith(".") or len(folders) >= MAX_FOLDERS:
                continue
            candidate = current / name
            try:
                relative = candidate.relative_to(root)
                if _is_reparse_point(candidate):
                    continue
                candidate.resolve().relative_to(root)
            except Exception:
                continue
            safe_directories.append(name)
            folders.append(relative.as_posix())
        directory_names[:] = safe_directories
        if len(paths) >= MAX_ASSETS:
            continue
        for name in file_names:
            if len(paths) >= MAX_ASSETS:
                break
            path = current / name
            if path.suffix.casefold() not in IMAGE_EXTENSIONS:
                continue
            try:
                relative = path.relative_to(root)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if _is_reparse_point(path):
                    continue
                path.resolve().relative_to(root)
            except Exception:
                warnings.append(
                    f"{name}: skipped because it resolves outside "
                    "the selected Project Root."
                )
                continue
            paths.append(path)
    paths.sort(key=lambda value: str(value.relative_to(root)).casefold())
    folders = sorted(set(folders), key=_natural_key)
    folder_signature = _folder_metadata_signature_from_inventory(
        root,
        folders,
        paths,
    )

    stem_counts: Dict[str, int] = {}
    for path in paths:
        stem_key = path.stem.casefold()
        stem_counts[stem_key] = stem_counts.get(stem_key, 0) + 1

    assets: List[Dict[str, Any]] = []
    for path in paths:
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        override = manifest_overrides.get(relative_text.casefold())
        registered = override is not None
        override_values = override or {}
        taxonomy = _normalize_image_taxonomy_fields(override_values)
        image_main_type = taxonomy["image_main_type"]
        image_sub_type = taxonomy["image_sub_type"]
        source_type = taxonomy["source_type"]
        custom_source_type = taxonomy["custom_source_type"]
        scope_candidate = taxonomy["scope_candidate"]

        default_asset_id = path.stem
        if stem_counts.get(path.stem.casefold(), 0) > 1:
            default_asset_id = relative.with_suffix("").as_posix()
        asset_id = _clean(override_values.get("asset_id")) or default_asset_id
        image_name = (
            _clean(
                override_values.get("image_name") or override_values.get("name")
            )
            or path.stem
        )
        library_id = _asset_library_id(project_id, relative_text)
        width, height = _asset_dimensions(path)
        try:
            _resolved, _size, _mtime_ns, media_signature = _asset_file_facts(
                path,
                project_uid=project_cache_uid,
                relative_path=relative_text,
            )
        except Exception:
            media_signature = ""
        color_candidates = taxonomy["color_pick_candidates"]
        is_user_import = _is_user_import_relative_path(relative_text)
        assets.append(
            {
                "asset_library_id": library_id,
                "source_uid": f"project:{library_id}",
                "source_kind": "user" if is_user_import else "project",
                "import_source_uid": _clean(override_values.get("import_source_uid")),
                "asset_project_uid": project_uid,
                "asset_id": asset_id,
                "image_name": image_name,
                "path": str(path).replace("\\", "/"),
                # Catalog discovery is metadata-first. Browser-safe thumbnails
                # are hydrated later for the selected/visible bounded window.
                "thumbnail_url": "",
                "media_signature": media_signature,
                "relative_path": relative_text,
                "extension": path.suffix.casefold(),
                "width": width,
                "height": height,
                "image_main_type": image_main_type,
                "image_sub_type": image_sub_type,
                "source_type": source_type,
                "custom_source_type": custom_source_type,
                "scope_candidate": scope_candidate,
                "color_pick_candidates": color_candidates,
                "registered": registered,
                "selected": bool(
                    registered and override_values.get("selected", False)
                ),
                "selection_order": _non_negative_int(
                    override_values.get("selection_order")
                ),
                "import_index": 0,
                "media_ref_kind": "path",
                "connected": True,
            }
        )
    if len(paths) >= MAX_ASSETS:
        warnings.append(
            f"Project scan reached the {MAX_ASSETS}-asset safety limit."
        )
    if len(folders) >= MAX_FOLDERS:
        warnings.append(
            f"Project scan reached the {MAX_FOLDERS}-folder safety limit."
        )
    return {
        "project_root": str(root).replace("\\", "/"),
        "project_id": project_id,
        "project_uid": project_uid,
        "project_cache_uid": project_cache_uid,
        "manifest_signature": manifest_signature,
        "folder_signature": folder_signature,
        "folders": folders,
        "assets": assets,
        "warnings": warnings,
    }


def _normalize_asset(raw: Any) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    library_id = _clean(raw.get("asset_library_id") or raw.get("asset_key"))
    asset_id = _clean(raw.get("asset_id"))
    image_name = _clean(raw.get("image_name") or raw.get("label"))
    path = _clean(raw.get("path") or raw.get("asset_path")).replace("\\", "/")
    if not library_id or not asset_id or not image_name:
        return None
    source_kind = _clean(raw.get("source_kind")).casefold()
    if source_kind not in {"project", "user"}:
        source_kind = "user"
    registered = source_kind == "project" and bool(raw.get("registered"))
    source_uid = _clean(raw.get("source_uid")) or (
        f"project:{library_id}" if source_kind == "project" else library_id
    )
    taxonomy = _normalize_image_taxonomy_fields(raw)
    image_main_type = taxonomy["image_main_type"]
    image_sub_type = taxonomy["image_sub_type"]
    source_type = taxonomy["source_type"]
    scope_candidate = taxonomy["scope_candidate"]
    allowed_colors = taxonomy["color_pick_candidates"]
    raw_colors = raw.get("color_pick_candidates")
    if not isinstance(raw_colors, (list, tuple)):
        raw_colors = allowed_colors
    colors = [
        _clean(value)
        for value in raw_colors
        if _clean(value) in allowed_colors
    ]
    try:
        width = max(0, int(raw.get("width") or 0))
        height = max(0, int(raw.get("height") or 0))
    except Exception:
        width = 0
        height = 0
    return {
        "asset_library_id": library_id,
        "source_uid": source_uid,
        "source_kind": source_kind,
        "import_source_uid": _clean(raw.get("import_source_uid")),
        "asset_project_uid": _clean(raw.get("asset_project_uid")),
        "asset_id": asset_id,
        "image_name": image_name,
        "path": path,
        "thumbnail_url": _clean(raw.get("thumbnail_url")),
        "media_signature": _clean(raw.get("media_signature"))[:64],
        "relative_path": _clean(raw.get("relative_path")).replace("\\", "/"),
        "extension": _clean(raw.get("extension")).casefold(),
        "width": width,
        "height": height,
        "image_main_type": image_main_type,
        "image_sub_type": image_sub_type,
        "source_type": source_type,
        "custom_source_type": taxonomy["custom_source_type"],
        "scope_candidate": scope_candidate,
        "color_pick_candidates": list(dict.fromkeys(colors)),
        "registered": registered,
        "selected": bool(raw.get("selected")) and (
            source_kind == "user" or registered
        ),
        "selection_order": _non_negative_int(raw.get("selection_order")),
        "import_index": _non_negative_int(raw.get("import_index")),
        "media_ref_kind": _clean(raw.get("media_ref_kind")) or "path",
        "connected": bool(raw.get("connected", True)),
    }


def _normalize_folder_paths(
    value: Any,
    assets: Sequence[Dict[str, Any]] = (),
) -> List[str]:
    """Return safe project-relative folders, including parents used by assets."""
    paths: set[str] = set()

    def add_path(raw: Any) -> None:
        text = _clean(raw).replace("\\", "/").strip("/")
        if not text:
            return
        parts = [part for part in text.split("/") if part and part != "."]
        if not parts or any(part == ".." for part in parts):
            return
        current: List[str] = []
        for part in parts:
            current.append(part)
            paths.add("/".join(current))

    if isinstance(value, (list, tuple)):
        for raw in value[:MAX_FOLDERS]:
            add_path(raw)
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        relative = _clean(asset.get("relative_path")).replace("\\", "/").strip("/")
        if "/" in relative:
            add_path(relative.rsplit("/", 1)[0])
    return sorted(paths, key=_natural_key)[:MAX_FOLDERS]


def _build_asset_tree(
    project_root: str,
    project_id: str,
    folders: Sequence[str],
    assets: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a persistent tree from folders that really exist in the project."""
    root: Dict[str, Any] = {
        "kind": "root",
        "id": "$root",
        "label": Path(project_root).name if project_root else "Select Project",
        "path": project_root,
        "folder_path": "",
        "asset_count": 0,
        "children": [],
    }
    folder_nodes: Dict[str, Dict[str, Any]] = {"": root}
    for folder_path in _normalize_folder_paths(folders, assets):
        parent_path = folder_path.rsplit("/", 1)[0] if "/" in folder_path else ""
        node = {
            "kind": "folder",
            "id": f"folder:{folder_path.casefold()}",
            "label": folder_path.rsplit("/", 1)[-1],
            "value": folder_path,
            "folder_path": folder_path,
            "asset_count": 0,
            "children": [],
        }
        folder_nodes[folder_path] = node
        folder_nodes.get(parent_path, root)["children"].append(node)

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        relative = _clean(asset.get("relative_path")).replace("\\", "/").strip("/")
        parent_path = relative.rsplit("/", 1)[0] if "/" in relative else ""
        parent = folder_nodes.get(parent_path, root)
        parent["children"].append(
            {
                "kind": "asset",
                "id": _clean(asset.get("asset_library_id")),
                "label": _clean(asset.get("image_name")),
                "asset_id": _clean(asset.get("asset_id")),
                "selected": bool(asset.get("selected")),
            }
        )

    def finalize(node: Dict[str, Any]) -> int:
        folders_only = [
            child for child in node["children"] if child.get("kind") == "folder"
        ]
        asset_nodes = [
            child for child in node["children"] if child.get("kind") == "asset"
        ]
        folders_only.sort(key=lambda item: _natural_key(item.get("label")))
        asset_nodes.sort(key=lambda item: _natural_key(item.get("label")))
        count = len(asset_nodes)
        for child in folders_only:
            count += finalize(child)
        node["children"] = [*folders_only, *asset_nodes]
        node["asset_count"] = count
        return count

    finalize(root)
    return root


def _normalize_project_catalog(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    projects: List[Dict[str, str]] = []
    seen: set[str] = set()
    for raw in value[:MAX_PROJECTS]:
        if not isinstance(raw, dict):
            continue
        path = _clean(raw.get("path")).replace("\\", "/")
        name = _clean(raw.get("name")) or (Path(path).name if path else "")
        project_id = _clean(raw.get("project_id"))
        project_uid = _clean(raw.get("project_uid"))
        key = path.casefold()
        if not path or not name or not project_id or key in seen:
            continue
        seen.add(key)
        projects.append(
            {
                "project_id": project_id,
                "project_uid": project_uid,
                "name": name,
                "path": path,
            }
        )
    projects.sort(key=lambda item: _natural_key(item["name"]))
    return projects


def _compact_selection_order(assets: List[Dict[str, Any]]) -> None:
    selected = [
        (index, asset)
        for index, asset in enumerate(assets)
        if bool(asset.get("selected"))
    ]
    selected.sort(
        key=lambda pair: (
            _non_negative_int(pair[1].get("selection_order")) or MAX_ASSETS + pair[0],
            pair[0],
        )
    )
    for _index, asset in selected[MAX_SELECTED_IMAGES:]:
        asset["selected"] = False
        asset["selection_order"] = 0
    selected = selected[:MAX_SELECTED_IMAGES]
    for order, (_index, asset) in enumerate(selected, start=1):
        asset["selection_order"] = order
    for asset in assets:
        if not bool(asset.get("selected")):
            asset["selection_order"] = 0


def _normalize_asset_registration_request(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    request_id = _clean(value.get("request_id"))[:128]
    asset_library_id = _clean(value.get("asset_library_id"))[:512]
    source_kind = (
        "user"
        if _clean(value.get("source_kind")).casefold() == "user"
        else "project"
    )
    relative_path = _clean(value.get("relative_path")).replace("\\", "/")[:1024]
    source_uid = _clean(value.get("source_uid"))[:512]
    target_folder = _clean(value.get("target_folder")).replace("\\", "/")[:1024]
    if (
        not request_id
        or not asset_library_id
        or (source_kind == "project" and not relative_path)
        or (source_kind == "user" and not source_uid)
    ):
        return {}
    return {
        "request_id": request_id,
        "project_uid": _clean(value.get("project_uid"))[:256],
        "asset_library_id": asset_library_id,
        "source_kind": source_kind,
        "source_uid": source_uid,
        "relative_path": relative_path,
        "target_folder": target_folder,
        "image_name": _clean(value.get("image_name"))[:256],
        "asset_id": _clean(value.get("asset_id"))[:256],
        "image_main_type": _clean(value.get("image_main_type"))[:256],
        "image_sub_type": _clean(value.get("image_sub_type"))[:256],
        "custom_source_type": _clean(value.get("custom_source_type"))[:256],
    }


def _normalize_asset_registration_result(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    request_id = _clean(value.get("request_id"))[:128]
    if not request_id:
        return {}
    return {
        "request_id": request_id,
        "ok": bool(value.get("ok")),
        "asset_library_id": _clean(value.get("asset_library_id"))[:512],
        "message": _clean(value.get("message"))[:1000],
    }


def _normalize_thumbnail_request(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    request_id = _clean(value.get("request_id"))[:128]
    project_uid = _clean(value.get("project_uid"))[:256]
    raw_ids = value.get("asset_library_ids")
    if not isinstance(raw_ids, (list, tuple)):
        return {}
    asset_library_ids: List[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        library_id = _clean(raw_id)[:512]
        if not library_id or library_id in seen:
            continue
        seen.add(library_id)
        asset_library_ids.append(library_id)
        if len(asset_library_ids) >= MAX_THUMBNAIL_HYDRATION_BATCH:
            break
    if not request_id or not project_uid or not asset_library_ids:
        return {}
    return {
        "request_id": request_id,
        "project_uid": project_uid,
        "project_cache_uid": _clean(value.get("project_cache_uid"))[:256],
        "manifest_signature": _clean(value.get("manifest_signature"))[:128],
        "scan_revision": _non_negative_int(value.get("scan_revision")),
        "asset_library_ids": asset_library_ids,
    }


def _normalize_thumbnail_result(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    request_id = _clean(value.get("request_id"))[:128]
    if not request_id:
        return {}

    def normalized_ids(field: str) -> List[str]:
        raw_ids = value.get(field)
        if not isinstance(raw_ids, (list, tuple)):
            return []
        result: List[str] = []
        seen: set[str] = set()
        for raw_id in raw_ids:
            library_id = _clean(raw_id)[:512]
            if library_id and library_id not in seen:
                seen.add(library_id)
                result.append(library_id)
            if len(result) >= MAX_THUMBNAIL_HYDRATION_BATCH:
                break
        return result

    return {
        "request_id": request_id,
        "project_uid": _clean(value.get("project_uid"))[:256],
        "project_cache_uid": _clean(value.get("project_cache_uid"))[:256],
        "manifest_signature": _clean(value.get("manifest_signature"))[:128],
        "scan_revision": _non_negative_int(value.get("scan_revision")),
        "completed_asset_library_ids": normalized_ids(
            "completed_asset_library_ids"
        ),
        "failed_asset_library_ids": normalized_ids("failed_asset_library_ids"),
    }


def _normalize_disconnect_import_uid(value: Any) -> str:
    source_uid = _clean(value)[:512]
    return source_uid if source_uid.startswith("import:") else ""


def _uuid_text(value: Any) -> str:
    text = _clean(value)
    try:
        return str(uuid.UUID(text))
    except (ValueError, TypeError, AttributeError):
        return ""


def _new_uuid_text() -> str:
    return str(uuid.uuid4())


def _sha256_canonical(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_shot_routing(
    value: Any,
    ordered_selected_source_uids: Sequence[str],
) -> Dict[str, Any]:
    """Normalize compact, serializable per-shot membership only.

    Media is deliberately excluded from widget state.  A legacy workflow gets
    one Shot 1 containing its first 30 selected assets, so existing selection
    behavior remains useful without migration UI.
    """
    raw = value if isinstance(value, dict) else {}
    master = list(dict.fromkeys(
        _clean(item) for item in ordered_selected_source_uids if _clean(item)
    ))
    master_set = set(master)
    publisher_instance_uuid = _uuid_text(raw.get("publisher_instance_uuid"))
    channel_uuid = _uuid_text(raw.get("channel_uuid"))
    seen_shot_uuids: set[str] = set()
    shots: List[Dict[str, Any]] = []
    compacted = False
    raw_shots = raw.get("shots")
    for item in (
        raw_shots[:MAX_SHOTS] if isinstance(raw_shots, list) else []
    ):
        if not isinstance(item, dict):
            continue
        shot_uuid = _uuid_text(item.get("shot_uuid"))
        if not shot_uuid or shot_uuid in seen_shot_uuids:
            shot_uuid = _new_uuid_text()
        seen_shot_uuids.add(shot_uuid)
        selected_source_uids: List[str] = []
        for raw_uid in (
            item.get("selected_source_uids")
            if isinstance(item.get("selected_source_uids"), list)
            else []
        ):
            source_uid = _clean(raw_uid)
            if (
                source_uid
                and source_uid in master_set
                and source_uid not in selected_source_uids
            ):
                selected_source_uids.append(source_uid)
            if len(selected_source_uids) >= MAX_SHOT_IMAGES:
                break
        number = len(shots) + 1
        previous_number = _non_negative_int(item.get("number")) or number
        previous_name = _clean(item.get("name"))[:128]
        name_is_custom = item.get("name_is_custom")
        if not isinstance(name_is_custom, bool):
            name_is_custom = bool(
                previous_name and previous_name != f"Shot {previous_number}"
            )
        reindexed = previous_number != number
        compacted = compacted or reindexed
        name = (
            (previous_name or f"Shot {number}")
            if name_is_custom
            else f"Shot {number}"
        )
        revision = max(0, _non_negative_int(item.get("revision")))
        if reindexed:
            revision += 1
        metadata_sha256 = _clean(item.get("metadata_sha256")).casefold()
        media_sha256 = _clean(item.get("media_sha256")).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", metadata_sha256):
            metadata_sha256 = ""
        if not re.fullmatch(r"[0-9a-f]{64}", media_sha256):
            media_sha256 = ""
        shots.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "name_is_custom": name_is_custom,
                "revision": revision,
                "selected_source_uids": selected_source_uids,
                "media_count": min(
                    len(selected_source_uids),
                    _non_negative_int(item.get("media_count")),
                ),
                "metadata_sha256": metadata_sha256,
                "media_sha256": media_sha256,
            }
        )
    if not shots:
        shots = [
            {
                "shot_uuid": _new_uuid_text(),
                "number": 1,
                "name": "Shot 1",
                "name_is_custom": False,
                "revision": 1 if master else 0,
                "selected_source_uids": master[:MAX_SHOT_IMAGES],
                "media_count": 0,
                "metadata_sha256": "",
                "media_sha256": "",
            }
        ]
    active_shot_uuid = _uuid_text(raw.get("active_shot_uuid"))
    if active_shot_uuid not in {item["shot_uuid"] for item in shots}:
        active_shot_uuid = shots[0]["shot_uuid"]
    return {
        "schema": SHOT_ROUTING_SCHEMA,
        "version": SHOT_ROUTING_VERSION,
        "publisher_instance_uuid": publisher_instance_uuid or _new_uuid_text(),
        "channel_uuid": channel_uuid or _new_uuid_text(),
        "generation": (
            max(1, _non_negative_int(raw.get("generation")) or 1)
            + (1 if compacted else 0)
        ),
        "active_shot_uuid": active_shot_uuid,
        "expanded": bool(raw.get("expanded", False)),
        "shots": shots,
    }


def _shot_routing_catalog_identity(
    state: Any,
    *,
    normalized: bool = False,
) -> str:
    """Hash every ImageAsset fact that can change a routing pass.

    ``active_shot_uuid`` is intentionally not part of the public compact
    catalog, but it is part of the ImageAsset subscription used by the central
    router.  Including it in this private scheduling identity ensures that a
    pure Shot selection change cannot be mistaken for a presentation-only
    echo and skipped before the router sees the new subscription.
    """

    normalized_state = state if normalized else _normalize_state(state)
    routing = normalized_state["shot_routing"]
    return _sha256_canonical(
        {
            "publisher_instance_uuid": routing["publisher_instance_uuid"],
            "channel_uuid": routing["channel_uuid"],
            "generation": routing["generation"],
            "active_shot_uuid": routing["active_shot_uuid"],
            "shots": [
                {
                    "shot_uuid": shot["shot_uuid"],
                    "number": shot["number"],
                    "name": shot["name"],
                    "revision": shot["revision"],
                }
                for shot in routing["shots"]
            ],
        }
    )


def _default_state() -> Dict[str, Any]:
    state = {
        "schema": STATE_SCHEMA,
        "version": STATE_VERSION,
        "catalog_root": str(DEFAULT_PROJECTS_ROOT).replace("\\", "/"),
        "projects": [],
        "project_root": "",
        "project_id": "",
        "project_uid": "",
        "project_cache_uid": "",
        "manifest_signature": "",
        "folder_signature": "",
        "taxonomy": _taxonomy_payload(),
        "folders": [],
        "assets": [],
        "tree": _build_asset_tree("", "", [], []),
        "root_edit_enabled": False,
        "selected_folder_path": "",
        "expanded_folders": ["$root"],
        "selected_main_type": "",
        "selected_sub_type": "",
        "selected_source_view": "project",
        "search": "",
        "language": "ko",
        "asset_view_mode": "image",
        UI_EDIT_REVISION_KEY: 0,
        "scan_revision": 0,
        "refresh_revision": 0,
        "scan_busy": False,
        "scan_request_id": "",
        "thumbnail_request": {},
        "thumbnail_result": {},
        "thumbnail_revision": 0,
        "thumbnail_busy": False,
        "asset_registration_request": {},
        "asset_registration_result": {},
        "disconnect_import_uid": "",
        "warnings": [],
        "error": "",
        "status": {
            "asset_count": 0,
            "selected_count": 0,
        },
    }
    state["shot_routing"] = _normalize_shot_routing({}, [])
    return state


def _normalize_state(value: Any) -> Dict[str, Any]:
    source = _parse_mapping(value)
    state = _default_state()
    catalog_root = (
        _clean(source.get("catalog_root")).replace("\\", "/")
        or str(DEFAULT_PROJECTS_ROOT).replace("\\", "/")
    )
    projects = _normalize_project_catalog(source.get("projects"))
    project_root = _clean(source.get("project_root")).replace("\\", "/")
    project_id = _clean(source.get("project_id"))
    project_uid = _clean(source.get("project_uid"))
    project_cache_uid = _clean(source.get("project_cache_uid"))
    assets: List[Dict[str, Any]] = []
    seen_library_ids: set[str] = set()
    seen_asset_ids: set[str] = set()
    raw_assets = source.get("assets")
    if isinstance(raw_assets, list):
        for raw in raw_assets[:MAX_ASSETS]:
            asset = _normalize_asset(raw)
            if asset is None:
                continue
            if asset["asset_library_id"] in seen_library_ids:
                continue
            if asset["asset_id"] in seen_asset_ids:
                asset["selected"] = False
            seen_library_ids.add(asset["asset_library_id"])
            seen_asset_ids.add(asset["asset_id"])
            assets.append(asset)
    _compact_selection_order(assets)
    ordered_selected_source_uids = [
        _clean(asset.get("source_uid"))
        for asset in sorted(
            (asset for asset in assets if bool(asset.get("selected"))),
            key=lambda asset: _non_negative_int(asset.get("selection_order")),
        )
        if _clean(asset.get("source_uid"))
    ]
    folders = _normalize_folder_paths(source.get("folders"), assets)
    selected_folder_path = (
        _clean(source.get("selected_folder_path")).replace("\\", "/").strip("/")
    )
    if selected_folder_path not in folders:
        selected_folder_path = ""
    expanded_folders: List[str] = []
    raw_expanded = source.get("expanded_folders")
    if isinstance(raw_expanded, list):
        for raw in raw_expanded:
            folder = _clean(raw).replace("\\", "/").strip("/")
            if raw == "$root" or folder == "$root":
                folder = "$root"
            if folder == "$root" or folder in folders:
                if folder not in expanded_folders:
                    expanded_folders.append(folder)
    if not isinstance(raw_expanded, list) and project_root:
        expanded_folders = ["$root"]
    selected_main_type = _clean(source.get("selected_main_type"))
    selected_sub_type = _clean(source.get("selected_sub_type"))
    if selected_main_type == IMAGE_MAIN_TYPE_UNCLASSIFIED:
        selected_main_type = ""
    if selected_main_type not in IMAGE_MAIN_TYPE_CHOICES:
        selected_main_type = ""
    if (
        selected_sub_type
        and selected_sub_type
        not in image_sub_type_choices_for_main_type(selected_main_type)
    ):
        selected_sub_type = ""
    selected_source_view = _clean(source.get("selected_source_view")).casefold()
    if selected_source_view not in {"project", "user"}:
        selected_source_view = "project"
    try:
        scan_revision = max(0, int(source.get("scan_revision") or 0))
    except Exception:
        scan_revision = 0
    try:
        refresh_revision = max(0, int(source.get("refresh_revision") or 0))
    except Exception:
        refresh_revision = 0
    try:
        ui_edit_revision = int(source.get(UI_EDIT_REVISION_KEY) or 0)
    except Exception:
        ui_edit_revision = 0
    ui_edit_revision = max(
        0,
        min(MAX_UI_EDIT_REVISION, ui_edit_revision),
    )
    warnings = source.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    state.update(
        {
            "catalog_root": catalog_root,
            "projects": projects,
            "project_root": project_root,
            "project_id": project_id,
            "project_uid": project_uid,
            "project_cache_uid": project_cache_uid,
            "manifest_signature": _clean(source.get("manifest_signature"))[:128],
            "folder_signature": _clean(source.get("folder_signature"))[:128],
            "folders": folders,
            "assets": assets,
            "shot_routing": _normalize_shot_routing(
                source.get("shot_routing"),
                ordered_selected_source_uids,
            ),
            "tree": _build_asset_tree(project_root, project_id, folders, assets),
            "root_edit_enabled": bool(source.get("root_edit_enabled", False)),
            "selected_folder_path": selected_folder_path,
            "expanded_folders": expanded_folders,
            "selected_main_type": selected_main_type,
            "selected_sub_type": selected_sub_type,
            "selected_source_view": selected_source_view,
            "search": _clean(source.get("search"))[:256],
            "language": (
                "en"
                if _clean(source.get("language")).casefold() == "en"
                else "ko"
            ),
            "asset_view_mode": (
                "detail"
                if _clean(source.get("asset_view_mode")).casefold() == "detail"
                else "image"
            ),
            UI_EDIT_REVISION_KEY: ui_edit_revision,
            "scan_revision": scan_revision,
            "refresh_revision": refresh_revision,
            "scan_busy": bool(source.get("scan_busy", False)),
            "scan_request_id": _clean(source.get("scan_request_id"))[:128],
            "thumbnail_request": _normalize_thumbnail_request(
                source.get("thumbnail_request")
            ),
            "thumbnail_result": _normalize_thumbnail_result(
                source.get("thumbnail_result")
            ),
            "thumbnail_revision": _non_negative_int(
                source.get("thumbnail_revision")
            ),
            "thumbnail_busy": bool(source.get("thumbnail_busy", False)),
            "asset_registration_request": _normalize_asset_registration_request(
                source.get("asset_registration_request")
            ),
            "asset_registration_result": _normalize_asset_registration_result(
                source.get("asset_registration_result")
            ),
            "disconnect_import_uid": _normalize_disconnect_import_uid(
                source.get("disconnect_import_uid")
            ),
            "warnings": [_clean(item) for item in warnings if _clean(item)][:100],
            "error": _clean(source.get("error")),
            "status": {
                "asset_count": len(assets),
                "selected_count": sum(
                    1 for asset in assets if bool(asset.get("selected"))
                ),
                "project_asset_count": sum(
                    1 for asset in assets if asset.get("source_kind") == "project"
                ),
                "user_asset_count": sum(
                    1 for asset in assets if asset.get("source_kind") == "user"
                ),
                "registered_asset_count": sum(
                    1
                    for asset in assets
                    if asset.get("source_kind") == "project"
                    and bool(asset.get("registered"))
                ),
                "unregistered_asset_count": sum(
                    1
                    for asset in assets
                    if asset.get("source_kind") == "project"
                    and not bool(asset.get("registered"))
                ),
            },
        }
    )
    return state


_IMAGE_ASSET_RESET_DURABLE_FIELDS = (
    "catalog_root",
    "projects",
    "project_root",
    "project_id",
    "project_uid",
    "project_cache_uid",
    "manifest_signature",
    "folder_signature",
    "folders",
    "assets",
)


def _reset_image_asset_state_preserving_shot_media(value: Any) -> Dict[str, Any]:
    """Reset transient UI/work state while retaining the Shot image library.

    Griptape implements Reset Node by constructing a temporary replacement and
    retiring the old object.  The replacement must start with no scan, request,
    registration, error, filter, or layout draft, but the selected asset rows
    and their per-Shot membership are workflow data rather than authoring
    scratch state.  Preserve those fields as one normalized snapshot so order,
    selection and active Shot cannot drift during the replacement transaction.
    """

    source = _normalize_state(value)
    reset = _default_state()
    for field in _IMAGE_ASSET_RESET_DURABLE_FIELDS:
        reset[field] = copy.deepcopy(source.get(field))
    ordered_selected_source_uids = [
        _clean(asset.get("source_uid"))
        for asset in sorted(
            (
                asset
                for asset in source.get("assets", [])
                if isinstance(asset, dict) and bool(asset.get("selected"))
            ),
            key=lambda asset: _non_negative_int(
                asset.get("selection_order")
            ),
        )
        if _clean(asset.get("source_uid"))
    ]
    source_routing = source.get("shot_routing")
    source_routing = source_routing if isinstance(source_routing, dict) else {}
    source_shots = [
        item
        for item in source_routing.get("shots", [])
        if isinstance(item, dict)
    ][:MAX_SHOTS]
    source_active_uuid = _uuid_text(source_routing.get("active_shot_uuid"))
    replacement_shots: List[Dict[str, Any]] = []
    for index, shot in enumerate(source_shots, start=1):
        replacement_shots.append(
            {
                # Channel and Shot UUIDs are durable workflow addresses used
                # by downstream Shot participants. Reset changes the publisher
                # runtime, not the content address of an existing Shot.
                "shot_uuid": _uuid_text(shot.get("shot_uuid")),
                "number": index,
                "name": _clean(shot.get("name"))[:128] or f"Shot {index}",
                "name_is_custom": bool(shot.get("name_is_custom")),
                "revision": _non_negative_int(shot.get("revision")) + 1,
                "selected_source_uids": copy.deepcopy(
                    shot.get("selected_source_uids")
                    if isinstance(shot.get("selected_source_uids"), list)
                    else []
                ),
                # Media hashes are derived again by the new publisher runtime;
                # no previous process cache is authority after Reset.
                "media_count": 0,
                "metadata_sha256": "",
                "media_sha256": "",
            }
        )
    replacement_routing = {
        "publisher_instance_uuid": _new_uuid_text(),
        "channel_uuid": _uuid_text(source_routing.get("channel_uuid")),
        "generation": 1,
        "active_shot_uuid": source_active_uuid,
        "expanded": False,
        "shots": replacement_shots,
    }
    reset["shot_routing"] = _normalize_shot_routing(
        replacement_routing,
        ordered_selected_source_uids,
    )
    # Monotonic revisions reject any browser echo queued for the retired
    # object without treating Reset itself as a filesystem refresh request.
    reset["scan_revision"] = _non_negative_int(source.get("scan_revision")) + 1
    reset["refresh_revision"] = _non_negative_int(
        source.get("refresh_revision")
    )
    reset[UI_EDIT_REVISION_KEY] = min(
        MAX_UI_EDIT_REVISION,
        _non_negative_int(source.get(UI_EDIT_REVISION_KEY)) + 1,
    )
    return _normalize_state(reset)


def _merge_scan_with_state(
    scan: Dict[str, Any],
    previous_state: Dict[str, Any],
) -> Dict[str, Any]:
    scan_cache_uid = _clean(scan.get("project_cache_uid"))
    previous_cache_uid = _clean(previous_state.get("project_cache_uid"))
    same_project = bool(
        scan_cache_uid
        and previous_cache_uid
        and scan_cache_uid == previous_cache_uid
    )
    if not previous_cache_uid:
        same_project = bool(
            _clean(scan.get("project_uid"))
            and _clean(scan.get("project_uid"))
            == _clean(previous_state.get("project_uid"))
            and _clean(scan.get("project_root")).replace("\\", "/").casefold()
            == _clean(previous_state.get("project_root"))
            .replace("\\", "/")
            .casefold()
        )
    previous_assets = {
        _clean(asset.get("asset_library_id")): asset
        for asset in previous_state.get("assets", [])
        if same_project
        and isinstance(asset, dict)
        and _clean(asset.get("asset_library_id"))
    }
    assets: List[Dict[str, Any]] = []
    for scanned in scan.get("assets", []):
        asset = dict(scanned)
        previous = previous_assets.get(asset["asset_library_id"])
        if previous is not None:
            asset["selected"] = bool(previous.get("selected")) and (
                asset.get("source_kind") == "user"
                or bool(asset.get("registered"))
            )
            asset["selection_order"] = _non_negative_int(
                previous.get("selection_order")
            )
            if (
                _clean(asset.get("media_signature"))
                and _clean(asset.get("media_signature"))
                == _clean(previous.get("media_signature"))
                and _thumbnail_url_is_live(
                    previous.get("media_signature"),
                    previous.get("thumbnail_url"),
                )
            ):
                # A metadata refresh keeps already hydrated thumbnails only
                # while path+size+mtime still identify the same file.
                asset["thumbnail_url"] = _clean(previous.get("thumbnail_url"))
        assets.append(asset)
    assets.extend(
        dict(asset)
        for asset in previous_state.get("assets", [])
        if isinstance(asset, dict)
        and _clean(asset.get("source_kind")) == "user"
        and _non_negative_int(asset.get("import_index")) > 0
    )
    state = dict(previous_state)
    state.update(
        {
            "project_root": scan.get("project_root", ""),
            "project_id": scan.get("project_id", ""),
            "project_uid": scan.get("project_uid", ""),
            "project_cache_uid": scan.get("project_cache_uid", ""),
            "manifest_signature": scan.get("manifest_signature", ""),
            "folder_signature": scan.get("folder_signature", ""),
            "folders": scan.get("folders", []),
            "assets": assets,
            "warnings": scan.get("warnings", []),
            "error": "",
            "scan_revision": int(previous_state.get("scan_revision") or 0) + 1,
        }
    )
    return _normalize_state(state)


_ASYNC_SCAN_LIVE_STATE_FIELDS = (
    "root_edit_enabled",
    "selected_folder_path",
    "expanded_folders",
    "selected_main_type",
    "selected_sub_type",
    "selected_source_view",
    "search",
    "language",
    "asset_view_mode",
    UI_EDIT_REVISION_KEY,
    "refresh_revision",
    "thumbnail_request",
    "thumbnail_result",
    "thumbnail_revision",
    "thumbnail_busy",
    "shot_routing",
    "asset_registration_request",
    "asset_registration_result",
    "disconnect_import_uid",
)

_ASYNC_SCAN_USER_ASSET_FIELDS = (
    "asset_id",
    "image_name",
    "registered",
    "image_main_type",
    "image_sub_type",
    "source_type",
    "custom_source_type",
    "scope_candidate",
    "color_pick_candidates",
)


def _async_scan_asset_key(asset: Any) -> str:
    if not isinstance(asset, dict):
        return ""
    library_id = _clean(asset.get("asset_library_id"))
    if library_id:
        return f"library:{library_id}"
    source_uid = _clean(asset.get("source_uid"))
    return f"source:{source_uid}" if source_uid else ""


def _merge_async_scan_result_with_live_state(
    scan_result: Dict[str, Any],
    scan_base: Dict[str, Any],
    live_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge filesystem authority without rolling back in-flight UI edits.

    A scan owns catalog/project/filesystem facts.  Language, filters, Shot
    membership, selection, and explicit registration edits remain live while
    that scan is running, so its older captured snapshot cannot overwrite
    them when the generation completes.
    """

    scanned = _normalize_state(scan_result)
    base = _normalize_state(scan_base)
    live = _normalize_state(live_state)
    merged = dict(scanned)
    for field in _ASYNC_SCAN_LIVE_STATE_FIELDS:
        value = live.get(field)
        if isinstance(value, dict):
            merged[field] = dict(value)
        elif isinstance(value, list):
            merged[field] = list(value)
        else:
            merged[field] = value

    base_assets = {
        _async_scan_asset_key(asset): asset
        for asset in base.get("assets", [])
        if _async_scan_asset_key(asset)
    }
    live_assets = {
        _async_scan_asset_key(asset): asset
        for asset in live.get("assets", [])
        if _async_scan_asset_key(asset)
    }
    assets: List[Dict[str, Any]] = []
    scanned_keys: set[str] = set()
    for raw_asset in scanned.get("assets", []):
        asset = dict(raw_asset)
        if (
            _clean(asset.get("source_kind")) == "user"
            and _non_negative_int(asset.get("import_index")) > 0
        ):
            # Worker state contains the IMAGE_IMPORT_IN snapshot captured when
            # the scan started. Rebuild that portion only from current live
            # state below so a disconnect cannot be resurrected.
            continue
        key = _async_scan_asset_key(asset)
        if key:
            scanned_keys.add(key)
        current = live_assets.get(key)
        baseline = base_assets.get(key)
        if current is not None:
            # Selection and Shot membership are interactive state, not
            # filesystem authority.  Always take their latest committed form.
            asset["selected"] = bool(current.get("selected"))
            asset["selection_order"] = _non_negative_int(
                current.get("selection_order")
            )
            # Registration can complete during a reload. Preserve only fields
            # that actually diverged from the scan's starting snapshot; an
            # unchanged field still accepts a newer manifest value.
            for field in _ASYNC_SCAN_USER_ASSET_FIELDS:
                if baseline is None or current.get(field) != baseline.get(field):
                    value = current.get(field)
                    asset[field] = list(value) if isinstance(value, list) else value
            if (
                _clean(asset.get("media_signature"))
                and _clean(asset.get("media_signature"))
                == _clean(current.get("media_signature"))
                and _thumbnail_url_is_live(
                    current.get("media_signature"),
                    current.get("thumbnail_url"),
                )
            ):
                # A thumbnail worker may finish while this catalog generation
                # is walking the project. Keep that newer presentation-only
                # field when the filesystem identity is still exact.
                asset["thumbnail_url"] = _clean(current.get("thumbnail_url"))
        assets.append(asset)

    # IMAGE_IMPORT_IN can change while a slow UNC scan is blocked.  Its latest
    # live rows are authoritative and never come from project filesystem walk.
    assets.extend(
        dict(asset)
        for asset in live.get("assets", [])
        if _clean(asset.get("source_kind")) == "user"
        and _non_negative_int(asset.get("import_index")) > 0
    )
    merged["assets"] = assets
    merged["scan_revision"] = max(
        _non_negative_int(scanned.get("scan_revision")),
        _non_negative_int(live.get("scan_revision")),
    )
    merged[UI_EDIT_REVISION_KEY] = max(
        _non_negative_int(scanned.get(UI_EDIT_REVISION_KEY)),
        _non_negative_int(live.get(UI_EDIT_REVISION_KEY)),
    )
    return _normalize_state(merged)


def _merge_async_registration_result_with_live_state(
    registration_result: Dict[str, Any],
    registration_base: Dict[str, Any],
    live_state: Dict[str, Any],
    request_value: Any,
) -> Dict[str, Any]:
    """Apply one durable registration without rolling back later UI edits.

    Registration owns the manifest-backed passport fields and, for an imported
    image, the exact source-row replacement.  Filters, Shot membership and any
    selection edits made while the filesystem worker was running remain live.
    A failed worker owns only its error/result acknowledgement and therefore
    leaves the previously usable asset snapshot intact.
    """

    scanned = _normalize_state(registration_result)
    live = _normalize_state(live_state)
    request = _normalize_asset_registration_request(request_value)
    merged = _merge_async_scan_result_with_live_state(
        scanned,
        registration_base,
        live,
    )
    merged["thumbnail_revision"] = max(
        _non_negative_int(scanned.get("thumbnail_revision")),
        _non_negative_int(live.get("thumbnail_revision")),
    )

    result = _normalize_asset_registration_result(
        scanned.get("asset_registration_result")
    )
    if not result and _clean(scanned.get("error")):
        result = {
            "request_id": _clean(request.get("request_id")),
            "ok": False,
            "asset_library_id": _clean(request.get("asset_library_id")),
            "message": _clean(scanned.get("error")),
        }
    merged["asset_registration_result"] = result
    if result and not bool(result.get("ok")):
        message = _clean(result.get("message"))
        merged["error"] = f"Asset registration: {message}" if message else (
            "Asset registration failed."
        )
        return _normalize_state(merged)

    if not result or not bool(result.get("ok")):
        return _normalize_state(merged)

    # A project registration retains the same stable library key, so the
    # generic merger above already combines its newly verified passport with
    # the latest selection.  A copied IMAGE_IMPORT_IN source changes identity;
    # transfer only that source's latest selection to the durable project row
    # and retire only that exact live import.
    if _clean(request.get("source_kind")).casefold() == "user":
        source_uid = _clean(request.get("source_uid"))
        latest_source = next(
            (
                asset
                for asset in live.get("assets", [])
                if _clean(asset.get("source_kind")) == "user"
                and _clean(asset.get("source_uid")) == source_uid
            ),
            None,
        )
        target_library_id = _clean(result.get("asset_library_id"))
        assets = [
            dict(asset)
            for asset in merged.get("assets", [])
            if not (
                _clean(asset.get("source_kind")) == "user"
                and _clean(asset.get("source_uid")) == source_uid
            )
        ]
        target = next(
            (
                asset
                for asset in assets
                if _clean(asset.get("source_kind")) == "project"
                and _clean(asset.get("asset_library_id")) == target_library_id
            ),
            None,
        )
        if target is not None:
            if latest_source is not None:
                target["selected"] = bool(latest_source.get("selected"))
                target["selection_order"] = (
                    _non_negative_int(latest_source.get("selection_order"))
                    if target["selected"]
                    else 0
                )
            else:
                # A disconnect committed while Add was copying is live UI/graph
                # authority. Keep the durable new project row, but never revive
                # the retired import's captured selection or Shot membership.
                target["selected"] = False
                target["selection_order"] = 0
        merged["assets"] = assets
        if latest_source is not None:
            _remap_shot_routing_source_uid(
                merged,
                source_uid,
                target.get("source_uid") if target is not None else "",
            )

    merged["error"] = ""
    return _normalize_state(merged)


def _shared_catalog_cache_key(state: Dict[str, Any]) -> tuple[str, str, str] | None:
    uid = _clean(state.get("project_cache_uid"))
    manifest_signature = _clean(state.get("manifest_signature"))
    folder_signature = _clean(state.get("folder_signature"))
    if not uid or not manifest_signature or not folder_signature:
        return None
    return uid, manifest_signature, folder_signature


def _shared_catalog_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    """Copy project catalog authority without copying any Shot/UI selection."""

    normalized = _normalize_state(state)
    assets: List[Dict[str, Any]] = []
    for raw_asset in normalized["assets"]:
        if _clean(raw_asset.get("source_kind")).casefold() != "project":
            continue
        asset = dict(raw_asset)
        asset["selected"] = False
        asset["selection_order"] = 0
        if not _thumbnail_url_is_live(
            asset.get("media_signature"), asset.get("thumbnail_url")
        ):
            asset["thumbnail_url"] = ""
        assets.append(asset)
    return {
        "catalog_root": normalized["catalog_root"],
        "projects": [dict(item) for item in normalized["projects"]],
        "project_root": normalized["project_root"],
        "project_id": normalized["project_id"],
        "project_uid": normalized["project_uid"],
        "project_cache_uid": normalized["project_cache_uid"],
        "manifest_signature": normalized["manifest_signature"],
        "folder_signature": normalized["folder_signature"],
        "folders": list(normalized["folders"]),
        "assets": assets,
        "warnings": list(normalized["warnings"]),
    }


def _store_shared_catalog_snapshot(
    state: Dict[str, Any],
    *,
    normalized: bool = False,
) -> None:
    normalized_state = state if normalized else _normalize_state(state)
    key = _shared_catalog_cache_key(normalized_state)
    if key is None or _clean(normalized_state.get("error")):
        return
    snapshot = _shared_catalog_snapshot(normalized_state)
    root_key = _clean(snapshot.get("project_root")).replace("\\", "/").casefold()
    with _SHARED_CATALOG_CACHE_LOCK:
        _SHARED_CATALOG_CACHE[key] = snapshot
        _SHARED_CATALOG_CACHE.move_to_end(key)
        if root_key:
            _SHARED_CATALOG_ROOT_BINDINGS[root_key] = key
            _SHARED_CATALOG_ROOT_BINDINGS.move_to_end(root_key)
        while len(_SHARED_CATALOG_CACHE) > _SHARED_CATALOG_CACHE_LIMIT:
            retired_key, _retired = _SHARED_CATALOG_CACHE.popitem(last=False)
            stale_roots = [
                item_root
                for item_root, item_key in _SHARED_CATALOG_ROOT_BINDINGS.items()
                if item_key == retired_key
            ]
            for item_root in stale_roots:
                _SHARED_CATALOG_ROOT_BINDINGS.pop(item_root, None)
        while len(_SHARED_CATALOG_ROOT_BINDINGS) > _SHARED_CATALOG_CACHE_LIMIT * 4:
            _SHARED_CATALOG_ROOT_BINDINGS.popitem(last=False)


def _rebind_shared_catalog_snapshot(
    snapshot: Dict[str, Any],
    project_record: Dict[str, Any],
    catalog: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Bind cached relative identities to the currently selected drive alias."""

    project_root_text = _clean(project_record.get("path"))
    project_id = _clean(project_record.get("project_id"))
    project_uid = _clean(project_record.get("project_uid"))
    project_cache_uid = _clean(project_record.get("project_cache_uid"))
    if not project_cache_uid and project_root_text:
        try:
            project_cache_uid = _project_cache_uid(Path(project_root_text))
        except Exception:
            project_cache_uid = ""
    if not project_root_text or not project_id or not project_uid or not project_cache_uid:
        return None
    try:
        root = Path(project_root_text).resolve()
        if not root.is_dir() or _is_reparse_point(root):
            return None
        if _clean(snapshot.get("project_uid")) != project_uid:
            return None
        if _clean(snapshot.get("project_cache_uid")) != project_cache_uid:
            return None
        if _clean(snapshot.get("manifest_signature")) != _asset_manifest_signature(root):
            return None
        if _clean(snapshot.get("folder_signature")) != _project_folder_metadata_signature(root):
            return None
        assets: List[Dict[str, Any]] = []
        for raw_asset in snapshot.get("assets", []):
            if not isinstance(raw_asset, dict):
                return None
            asset = dict(raw_asset)
            relative_text = _clean(asset.get("relative_path")).replace("\\", "/")
            relative = Path(relative_text)
            if (
                not relative_text
                or relative.is_absolute()
                or bool(relative.drive)
                or ".." in relative.parts
                or _clean(asset.get("asset_library_id"))
                != _asset_library_id(project_id, relative.as_posix())
            ):
                return None
            rebound = (root / relative).resolve()
            rebound.relative_to(root)
            asset["path"] = str(rebound).replace("\\", "/")
            asset["asset_project_uid"] = project_uid
            if not _thumbnail_url_is_live(
                asset.get("media_signature"), asset.get("thumbnail_url")
            ):
                asset["thumbnail_url"] = ""
            assets.append(asset)
        rebound_snapshot = dict(snapshot)
        rebound_snapshot.update(
            {
                "catalog_root": catalog["catalog_root"],
                "projects": [dict(item) for item in catalog["projects"]],
                "project_root": str(root).replace("\\", "/"),
                "project_id": project_id,
                "project_uid": project_uid,
                "project_cache_uid": project_cache_uid,
                "assets": assets,
            }
        )
        return rebound_snapshot
    except Exception:
        return None


def _adopt_shared_catalog_snapshot(
    catalog: Dict[str, Any],
    project_record: Dict[str, Any],
    previous_state: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Adopt a process snapshot after cheap identity/version validation."""

    project_root = _clean(project_record.get("path"))
    project_uid = _clean(project_record.get("project_uid"))
    try:
        project_cache_uid = _project_cache_uid(Path(project_root)) if project_root else ""
    except Exception:
        project_cache_uid = ""
    if not project_root or not project_uid or not project_cache_uid:
        return None
    try:
        manifest_signature = _asset_manifest_signature(Path(project_root))
    except Exception:
        return None
    root_key = project_root.replace("\\", "/").casefold()
    with _SHARED_CATALOG_CACHE_LOCK:
        exact_key = _SHARED_CATALOG_ROOT_BINDINGS.get(root_key)
        candidates: List[tuple[tuple[str, str, str], Dict[str, Any]]] = []
        if exact_key is not None:
            snapshot = _SHARED_CATALOG_CACHE.get(exact_key)
            if snapshot is not None:
                candidates.append((exact_key, dict(snapshot)))
        for key, snapshot in reversed(_SHARED_CATALOG_CACHE.items()):
            if key == exact_key:
                continue
            if key[0] == project_cache_uid and key[1] == manifest_signature:
                candidates.append((key, dict(snapshot)))
    candidates = [
        item
        for item in candidates
        if item[0][0] == project_cache_uid and item[0][1] == manifest_signature
    ]
    if not candidates:
        return None
    # Same-name projects can share a derived UID. An exact root is sufficient;
    # cross-drive aliases additionally require the current folder fingerprint
    # to match exactly before a cached catalog may cross that boundary.
    if candidates[0][0] != exact_key:
        try:
            current_folder_signature = _project_folder_metadata_signature(project_root)
        except Exception:
            return None
        candidates = [item for item in candidates if item[0][2] == current_folder_signature]
        if not candidates:
            return None
    selected_key, snapshot = candidates[0]
    rebound = _rebind_shared_catalog_snapshot(snapshot, project_record, catalog)
    if rebound is None:
        return None
    merged = _merge_scan_with_state(rebound, previous_state)
    merged["scan_revision"] = _non_negative_int(previous_state.get("scan_revision"))
    merged["catalog_root"] = catalog["catalog_root"]
    merged["projects"] = catalog["projects"]
    _store_shared_catalog_snapshot(merged)
    with _SHARED_CATALOG_CACHE_LOCK:
        _SHARED_CATALOG_ROOT_BINDINGS[root_key] = selected_key
        _SHARED_CATALOG_ROOT_BINDINGS.move_to_end(root_key)
    return _normalize_state(merged)


def _load_project_catalog(
    projects_root: Any,
    previous_state: Dict[str, Any],
    *,
    use_shared_cache: bool = True,
) -> Dict[str, Any]:
    catalog = _discover_project_catalog(projects_root)
    state = dict(previous_state)
    state["catalog_root"] = catalog["catalog_root"]
    state["projects"] = catalog["projects"]
    selected = _match_catalog_project(
        catalog["projects"],
        previous_path=previous_state.get("project_root"),
        previous_uid=previous_state.get("project_uid"),
        previous_project_id=previous_state.get("project_id"),
    )
    selected_path = _clean(selected.get("path")) if selected else ""
    if not selected_path and len(catalog["projects"]) == 1:
        only_project = catalog["projects"][0]
        if _clean(only_project.get("path")).casefold() == _clean(
            catalog["catalog_root"]
        ).casefold():
            selected_path = _clean(only_project.get("path"))
    if selected_path:
        cached = (
            _adopt_shared_catalog_snapshot(catalog, selected, state)
            if use_shared_cache and selected is not None
            else None
        )
        state = cached or _merge_scan_with_state(
            _scan_project_assets(selected_path), state
        )
        state["catalog_root"] = catalog["catalog_root"]
        state["projects"] = catalog["projects"]
    else:
        state.update(
            {
                "project_root": "",
                "project_id": "",
                "project_uid": "",
                "project_cache_uid": "",
                "manifest_signature": "",
                "folder_signature": "",
                "folders": [],
                "assets": [
                    dict(asset)
                    for asset in previous_state.get("assets", [])
                    if isinstance(asset, dict)
                    and _clean(asset.get("source_kind")) == "user"
                    and _non_negative_int(asset.get("import_index")) > 0
                ],
            }
        )
    if catalog.get("warning"):
        state["warnings"] = [
            *(
                state.get("warnings")
                if isinstance(state.get("warnings"), list)
                else []
            ),
            catalog["warning"],
        ]
    return _normalize_state(state)


def _catalog_index_path(project_root: Any) -> Path:
    root_text = _project_root_text(project_root)
    identity = _project_cache_uid(Path(root_text)) if root_text else ""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return Path(_ASSET_CATALOG_INDEX_ROOT) / f"{digest}.json"


def _catalog_index_projection(
    state: Dict[str, Any],
    *,
    normalized: bool = False,
) -> Dict[str, Any]:
    """Return catalog facts only; UI selection and transient URLs stay in state."""

    normalized_state = state if normalized else _normalize_state(state)
    assets: List[Dict[str, Any]] = []
    for raw_asset in normalized_state["assets"]:
        if _clean(raw_asset.get("source_kind")).casefold() != "project":
            continue
        asset = dict(raw_asset)
        asset["selected"] = False
        asset["selection_order"] = 0
        asset["thumbnail_url"] = ""
        assets.append(asset)
    return {
        "schema": _ASSET_CATALOG_INDEX_SCHEMA,
        "version": _ASSET_CATALOG_INDEX_VERSION,
        "catalog_root": normalized_state["catalog_root"],
        "projects": normalized_state["projects"],
        "project_root": normalized_state["project_root"],
        "project_id": normalized_state["project_id"],
        "project_uid": normalized_state["project_uid"],
        "project_cache_uid": normalized_state["project_cache_uid"],
        "manifest_signature": normalized_state["manifest_signature"],
        "folder_signature": normalized_state["folder_signature"],
        "folders": normalized_state["folders"],
        "assets": assets,
    }


def _write_catalog_index(
    state: Dict[str, Any],
    *,
    normalized: bool = False,
) -> None:
    """Atomically persist one bounded, non-authoritative local scan snapshot."""

    project_root = _clean(state.get("project_root"))
    if not project_root:
        return
    try:
        projection = _catalog_index_projection(state, normalized=normalized)
        payload = _json_text(projection).encode("utf-8")
        if len(payload) > _ASSET_CATALOG_INDEX_MAX_BYTES:
            return
        index_path = _catalog_index_path(project_root)
        with _ASSET_CATALOG_INDEX_LOCK:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = index_path.parent / f".{index_path.name}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_bytes(payload)
                os.replace(temporary, index_path)
            finally:
                temporary.unlink(missing_ok=True)
    except Exception as exc:
        _diagnostic_warning("Local catalog index write failed", exc)


def _read_catalog_index(
    project_root: Any,
    previous_state: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Adopt a local index only when project identity and manifest still match."""

    root_text = _clean(project_root)
    if not root_text:
        return None
    try:
        index_path = _catalog_index_path(root_text)
        if (
            not index_path.is_file()
            or _is_reparse_point(index_path)
            or index_path.stat().st_size > _ASSET_CATALOG_INDEX_MAX_BYTES
        ):
            return None
        raw = json.loads(index_path.read_text(encoding="utf-8"))
        expected_catalog_root = _project_root_text(
            previous_state.get("catalog_root")
        ).replace("\\", "/")
        if (
            not isinstance(raw, dict)
            or raw.get("schema") != _ASSET_CATALOG_INDEX_SCHEMA
            or raw.get("version") != _ASSET_CATALOG_INDEX_VERSION
            or _project_uid(Path(_clean(raw.get("project_root"))))
            != _clean(raw.get("project_uid"))
            or not expected_catalog_root
        ):
            return None
        catalog = _discover_project_catalog(expected_catalog_root)
        selected = _match_catalog_project(
            catalog["projects"],
            previous_path=root_text,
            previous_uid=raw.get("project_uid"),
            previous_project_id=raw.get("project_id"),
        )
        if selected is None:
            return None
        resolved_root = Path(_clean(selected.get("path"))).resolve()
        if (
            _clean(raw.get("project_id")) != _project_id(resolved_root)
            or _clean(raw.get("project_uid")) != _project_uid(resolved_root)
            or _clean(raw.get("project_cache_uid"))
            != _project_cache_uid(resolved_root)
            or _clean(raw.get("manifest_signature"))
            != _asset_manifest_signature(resolved_root)
        ):
            return None
        if _clean(raw.get("folder_signature")) != _project_folder_metadata_signature(
            resolved_root
        ):
            return None
        assets = raw.get("assets")
        if not isinstance(assets, list) or len(assets) > MAX_ASSETS:
            return None
        for asset in assets:
            if not isinstance(asset, dict):
                return None
            relative_text = _clean(asset.get("relative_path")).replace("\\", "/")
            relative = Path(relative_text)
            if (
                not relative_text
                or relative.is_absolute()
                or bool(relative.drive)
                or ".." in relative.parts
                or relative.suffix.casefold() not in IMAGE_EXTENSIONS
                or _clean(asset.get("asset_library_id"))
                != _asset_library_id(_project_id(resolved_root), relative.as_posix())
            ):
                return None
            resolved_asset = (resolved_root / relative).resolve()
            try:
                resolved_asset.relative_to(resolved_root)
            except Exception:
                return None
            asset["path"] = str(resolved_asset).replace("\\", "/")
            asset["thumbnail_url"] = ""
        indexed = dict(previous_state)
        indexed.update(raw)
        indexed["catalog_root"] = catalog["catalog_root"]
        indexed["projects"] = catalog["projects"]
        indexed["project_root"] = str(resolved_root).replace("\\", "/")
        indexed["catalog_root"] = catalog["catalog_root"]
        merged = _merge_scan_with_state(indexed, previous_state)
        merged["scan_revision"] = _non_negative_int(
            previous_state.get("scan_revision")
        )
        return merged
    except Exception:
        return None


def _state_catalog_is_current(state: Dict[str, Any]) -> bool:
    """Cheap SWR guard: validate the managed manifest without walking assets."""

    project_root = _clean(state.get("project_root"))
    signature = _clean(state.get("manifest_signature"))
    if not project_root or not signature:
        return False
    try:
        root = Path(project_root).resolve()
        return (
            root.is_dir()
            and not _is_reparse_point(root)
            and _clean(state.get("project_id")) == _project_id(root)
            and _clean(state.get("project_uid")) == _project_uid(root)
            and _clean(state.get("project_cache_uid")) == _project_cache_uid(root)
            and signature == _asset_manifest_signature(root)
        )
    except Exception:
        return False


def _state_project_belongs_to_catalog(
    state: Dict[str, Any],
    catalog_root: Any,
) -> bool:
    """Reject a valid old project after PROJECT_ROOT switches catalogs."""

    project_text = _clean(state.get("project_root"))
    catalog_text = _project_root_text(catalog_root)
    if not project_text or not catalog_text:
        return False
    try:
        project = Path(project_text).resolve()
        catalog = Path(catalog_text).resolve()
        # Discovery treats the chosen root either as one direct project or as
        # a container whose immediate child directories are projects.
        return project == catalog or project.parent == catalog
    except Exception:
        return False


def _select_catalog_project(
    state: Dict[str, Any],
    project_path: Any,
) -> Dict[str, Any]:
    normalized = _normalize_state(state)
    requested = _clean(project_path).replace("\\", "/")
    selected = next(
        (
            item
            for item in normalized["projects"]
            if _clean(item.get("path")).casefold() == requested.casefold()
        ),
        None,
    )
    if selected is None:
        raise ValueError("Selected project is outside the enumerated project catalog.")
    catalog = {
        "catalog_root": normalized["catalog_root"],
        "projects": normalized["projects"],
    }
    merged = _adopt_shared_catalog_snapshot(catalog, selected, normalized)
    if merged is None:
        merged = _merge_scan_with_state(
            _scan_project_assets(selected["path"]),
            normalized,
        )
    merged["catalog_root"] = normalized["catalog_root"]
    merged["projects"] = normalized["projects"]
    merged["selected_main_type"] = ""
    merged["selected_sub_type"] = ""
    merged["selected_source_view"] = "project"
    merged["selected_folder_path"] = ""
    merged["expanded_folders"] = ["$root"]
    return _normalize_state(merged)


def _registration_identifier(value: Any, label: str) -> str:
    text = _clean(value)
    if not text:
        raise ValueError(f"{label} is required.")
    if len(text) > 256:
        raise ValueError(f"{label} exceeds 256 characters.")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError(f"{label} contains unsupported control characters.")
    return text


def _registration_record(
    request: Dict[str, str],
    scanned_asset: Dict[str, Any],
) -> Dict[str, Any]:
    image_name = _registration_identifier(request.get("image_name"), "Image Name")
    asset_id = _registration_identifier(request.get("asset_id"), "Asset ID")
    requested_main_type = _clean(request.get("image_main_type"))
    requested_sub_type = _clean(request.get("image_sub_type"))
    taxonomy = _normalize_image_taxonomy_fields({
        "image_main_type": requested_main_type,
        "image_sub_type": requested_sub_type,
        "custom_source_type": request.get("custom_source_type"),
    })
    if requested_main_type and taxonomy["image_main_type"] == IMAGE_MAIN_TYPE_UNCLASSIFIED:
        raise ValueError("Select a valid Image Main Type and Sub Type pair.")
    custom_source_type = taxonomy["custom_source_type"]
    if len(custom_source_type) > 256:
        raise ValueError("Custom Main Type exceeds 256 characters.")
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in custom_source_type
    ):
        raise ValueError("Custom Main Type contains unsupported control characters.")
    relative_text = _clean(scanned_asset.get("relative_path")).replace("\\", "/")
    return {
        "path": relative_text,
        "asset_id": asset_id,
        "image_name": image_name,
        "image_main_type": taxonomy["image_main_type"],
        "image_sub_type": taxonomy["image_sub_type"],
        "source_type": taxonomy["source_type"],
        "custom_source_type": custom_source_type,
        "scope": taxonomy["scope_candidate"],
    }


def _registration_folder_path(project_root: Path, folder_value: Any) -> Path:
    """Resolve one existing project folder without creating or following redirects."""
    folder_text = _clean(folder_value).replace("\\", "/").strip("/")
    parts = [part for part in folder_text.split("/") if part]
    if not parts:
        raise ValueError(
            "Select an existing Asset Folder below the project root before registering."
        )
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Project Folder contains an unsafe path segment.")
    if Path(folder_text).is_absolute() or re.match(r"^[A-Za-z]:", folder_text):
        raise ValueError("Project Folder must be relative to the selected project.")
    resolved_root = project_root.resolve()
    destination = resolved_root.joinpath(*parts)
    try:
        resolved_destination = destination.resolve()
        resolved_destination.relative_to(resolved_root)
    except Exception as exc:
        raise ValueError("Project Folder resolves outside the selected project.") from exc
    if not resolved_destination.is_dir():
        raise ValueError("Select an existing Project Folder before registering.")
    current = resolved_destination
    while current != resolved_root:
        if _is_reparse_point(current):
            raise ValueError("Project Folder cannot be a symlink or reparse point.")
        current = current.parent
    return resolved_destination


def _resolve_import_file_reference(value: str) -> Path | None:
    """Resolve a server-local path, including Griptape project macros."""
    text = _decode_file_uri(value)
    if re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", text):
        try:
            from griptape_nodes.files.file import File  # type: ignore

            text = File(text).resolve()
        except Exception:
            return None
    try:
        return Path(text).expanduser().resolve()
    except Exception:
        return None


def _local_import_source(asset: Dict[str, Any], media_value: Any) -> Path | None:
    artifact_value = _artifact_field(media_value, "value")
    candidates = [
        asset.get("path"),
        media_value if isinstance(media_value, (str, Path)) else "",
        artifact_value if isinstance(artifact_value, (str, Path)) else "",
    ]
    for raw in candidates:
        text = _clean(raw)
        if not text or text.startswith(("data:image/", "http://", "https://", "blob:")):
            continue
        resolved = _resolve_import_file_reference(text)
        if resolved is None:
            continue
        if (
            resolved.is_file()
            and resolved.suffix.casefold() in IMAGE_EXTENSIONS
            and not _is_reparse_point(resolved)
        ):
            try:
                if resolved.stat().st_size > MAX_IMPORT_BYTES:
                    raise ValueError(
                        f"Imported image exceeds the {MAX_IMPORT_BYTES // (1024 * 1024)} MiB limit."
                    )
            except OSError as exc:
                raise ValueError(f"Unable to read imported image: {exc}") from exc
            return resolved
    return None


def _import_media_bytes(media_value: Any) -> bytes | None:
    artifact_value = _artifact_field(media_value, "value")
    if isinstance(media_value, (bytes, bytearray)):
        payload = bytes(media_value)
    elif isinstance(artifact_value, (bytes, bytearray)):
        payload = bytes(artifact_value)
    else:
        embedded = _artifact_field(media_value, "base64")
        if callable(embedded):
            try:
                embedded = embedded()
            except Exception as exc:
                raise ValueError(f"Unable to read imported image payload: {exc}") from exc
        if not isinstance(embedded, str) and isinstance(media_value, str):
            embedded = media_value if media_value.startswith("data:image/") else None
        if not isinstance(embedded, str) or not embedded.strip():
            return None
        encoded = embedded.split(",", 1)[1] if embedded.startswith("data:") and "," in embedded else embedded
        encoded = re.sub(r"\s+", "", encoded)
        if len(encoded) > MAX_IMPORT_BASE64_CHARS:
            raise ValueError(
                f"Imported image exceeds the {MAX_IMPORT_BYTES // (1024 * 1024)} MiB limit."
            )
        try:
            payload = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Imported image payload is not valid base64 data.") from exc
    if not payload:
        return None
    if len(payload) > MAX_IMPORT_BYTES:
        raise ValueError(
            f"Imported image exceeds the {MAX_IMPORT_BYTES // (1024 * 1024)} MiB limit."
        )
    return payload


def _safe_import_filename(
    asset: Dict[str, Any],
    media_value: Any,
    local_source: Path | None,
) -> str:
    artifact_name = _clean(
        _artifact_field(media_value, "name")
        or _artifact_field(media_value, "filename")
    )
    extension = (
        local_source.suffix.casefold()
        if local_source is not None
        else Path(artifact_name).suffix.casefold()
        if artifact_name
        else _clean(asset.get("extension")).casefold()
    )
    if extension not in IMAGE_EXTENSIONS:
        extension = ".png"
    original_name = (
        local_source.name
        if local_source is not None
        else Path(artifact_name).name
        if artifact_name
        else f"{_clean(asset.get('image_name')) or 'Imported Image'}{extension}"
    )
    stem = Path(original_name).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" .")
    if not stem:
        stem = "Imported_Image"
    if stem.casefold() in {
        "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5",
        "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4",
        "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }:
        stem = f"_{stem}"
    return f"{stem[:180]}{extension}"


def _copy_import_to_project(
    asset: Dict[str, Any],
    media_value: Any,
    project_root: Path,
    target_folder: Any,
) -> Path:
    target_parent = _registration_folder_path(project_root, target_folder)
    local_source = _local_import_source(asset, media_value)
    payload = None if local_source is not None else _import_media_bytes(media_value)
    if local_source is None and payload is None:
        raise ValueError(
            "This external image has no readable local or embedded payload to copy."
        )
    if local_source is not None:
        _verified_image_dimensions(local_source)
    else:
        _verified_image_dimensions(BytesIO(payload or b""))
    try:
        resolved_root = project_root.resolve()
        resolved_folder = target_parent.resolve()
        resolved_folder.relative_to(resolved_root)
    except Exception as exc:
        raise ValueError("Selected Asset Folder resolves outside the project.") from exc
    if not resolved_folder.is_dir() or _is_reparse_point(resolved_folder):
        raise ValueError(
            "Selected Asset Folder must be a regular directory inside the project."
        )
    filename = _safe_import_filename(asset, media_value, local_source)
    stem = Path(filename).stem
    extension = Path(filename).suffix.casefold()
    for number in range(1, 10001):
        candidate_name = filename if number == 1 else f"{stem}_{number}{extension}"
        destination = resolved_folder / candidate_name
        try:
            with destination.open("xb") as output:
                if local_source is not None:
                    with local_source.open("rb") as source:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                else:
                    output.write(payload or b"")
                output.flush()
                os.fsync(output.fileno())
            _verified_image_dimensions(destination)
            return destination
        except FileExistsError:
            continue
        except Exception as exc:
            cleanup_error: Exception | None = None
            try:
                destination.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                cleanup_error = cleanup_exc
            if cleanup_error is not None:
                raise RuntimeError(
                    "Image copy failed and the incomplete destination could not be "
                    f"removed: {cleanup_error}"
                ) from exc
            raise
    raise ValueError("Unable to choose a unique filename in the selected Asset Folder.")


def _resolve_project_asset_file(
    project_root: Path,
    project_id: str,
    relative_value: Any,
    expected_library_id: Any = "",
    *,
    allow_user_import_path: bool = True,
) -> tuple[Path, str, str]:
    """Resolve one exact image row without walking the surrounding project."""

    relative_text = _clean(relative_value).replace("\\", "/").strip("/")
    relative_path = Path(relative_text)
    parts = [part for part in relative_path.parts if part]
    if (
        not parts
        or relative_path.is_absolute()
        or re.match(r"^[A-Za-z]:", relative_text)
        or any(part in {".", ".."} or part.startswith(".") for part in parts)
    ):
        raise ValueError("The image path is not a safe project-relative file.")
    if relative_path.suffix.casefold() not in IMAGE_EXTENSIONS:
        raise ValueError("The selected project file is not a supported image.")
    if not allow_user_import_path and _is_user_import_relative_path(relative_text):
        raise ValueError("External or User Import images cannot be registered in place.")
    resolved_root = project_root.resolve()
    try:
        resolved = resolved_root.joinpath(*parts).resolve()
        canonical_relative = resolved.relative_to(resolved_root).as_posix()
    except Exception as exc:
        raise ValueError("The image resolves outside the selected project.") from exc
    if canonical_relative.casefold() != relative_text.casefold():
        raise ValueError("The image path changed while the operation was pending.")
    if not resolved.is_file() or _is_reparse_point(resolved):
        raise ValueError("The image file changed or is no longer available.")
    current = resolved.parent
    while current != resolved_root:
        if _is_reparse_point(current):
            raise ValueError("Image paths cannot traverse a symlink or reparse point.")
        current = current.parent
    library_id = _asset_library_id(project_id, canonical_relative)
    expected_id = _clean(expected_library_id)
    if expected_id and library_id != expected_id:
        raise ValueError("The image identity changed while the operation was pending.")
    _resolved, _size, _mtime_ns, media_signature = _asset_file_facts(
        resolved,
        project_uid=_project_cache_uid(resolved_root),
        relative_path=canonical_relative,
    )
    return resolved, canonical_relative, media_signature


def _registered_project_asset_row(
    *,
    project_root: Path,
    project_id: str,
    project_cache_uid: str,
    relative_text: str,
    manifest_record: Dict[str, Any],
    previous_asset: Dict[str, Any] | None = None,
    selected: bool = False,
    selection_order: int = 0,
    verified_dimensions: tuple[int, int] | None = None,
    hydrate_thumbnail: bool = False,
) -> Dict[str, Any]:
    """Build the authoritative row for one committed manifest record."""

    # ``asset_project_uid`` remains the logical routing identity used by Shot
    # contracts.  ``project_cache_uid`` is deliberately separate and exists
    # only to isolate/reuse catalog and thumbnail caches safely.
    project_uid = _project_uid(project_root)
    path, canonical_relative, media_signature = _resolve_project_asset_file(
        project_root,
        project_id,
        relative_text,
        allow_user_import_path=False,
    )
    taxonomy = _normalize_image_taxonomy_fields(manifest_record)
    previous = previous_asset if isinstance(previous_asset, dict) else {}
    width, height = (
        verified_dimensions
        if verified_dimensions is not None
        else _asset_dimensions(path)
    )
    library_id = _asset_library_id(project_id, canonical_relative)
    thumbnail_url = (
        _asset_thumbnail_url_for_media(path, library_id, media_signature)
        if hydrate_thumbnail
        else _clean(previous.get("thumbnail_url"))
        if (
            _clean(previous.get("media_signature")) == media_signature
            and _thumbnail_url_is_live(
                previous.get("media_signature"),
                previous.get("thumbnail_url"),
            )
        )
        else ""
    )
    if thumbnail_url:
        try:
            _resolved, _size, _mtime_ns, hydrated_signature = _asset_file_facts(
                path,
                project_uid=project_cache_uid,
                relative_path=canonical_relative,
            )
            if hydrated_signature != media_signature:
                thumbnail_url = ""
        except Exception:
            thumbnail_url = ""
    return {
        "asset_library_id": library_id,
        "source_uid": f"project:{library_id}",
        "source_kind": "project",
        "import_source_uid": _clean(manifest_record.get("import_source_uid")),
        "asset_project_uid": project_uid,
        "asset_id": _clean(manifest_record.get("asset_id")) or path.stem,
        "image_name": _clean(
            manifest_record.get("image_name") or manifest_record.get("name")
        )
        or path.stem,
        "path": str(path).replace("\\", "/"),
        "thumbnail_url": thumbnail_url,
        "media_signature": media_signature,
        "relative_path": canonical_relative,
        "extension": path.suffix.casefold(),
        "width": max(0, int(width)),
        "height": max(0, int(height)),
        "image_main_type": taxonomy["image_main_type"],
        "image_sub_type": taxonomy["image_sub_type"],
        "source_type": taxonomy["source_type"],
        "custom_source_type": taxonomy["custom_source_type"],
        "scope_candidate": taxonomy["scope_candidate"],
        "color_pick_candidates": taxonomy["color_pick_candidates"],
        "registered": True,
        "selected": bool(selected),
        "selection_order": (
            _non_negative_int(selection_order) if bool(selected) else 0
        ),
        "import_index": 0,
        "media_ref_kind": "path",
        "connected": True,
    }


def _remap_shot_routing_source_uid(
    state: Dict[str, Any],
    old_source_uid: Any,
    new_source_uid: Any,
) -> None:
    """Replace one Add source identity in-place across every Shot."""

    old_uid = _clean(old_source_uid)
    new_uid = _clean(new_source_uid)
    if not old_uid or not new_uid or old_uid == new_uid:
        return
    routing = copy.deepcopy(state.get("shot_routing"))
    if not isinstance(routing, dict):
        return
    changed_any = False
    raw_shots = routing.get("shots")
    if not isinstance(raw_shots, list):
        return
    for shot in raw_shots:
        if not isinstance(shot, dict):
            continue
        raw_uids = shot.get("selected_source_uids")
        if not isinstance(raw_uids, list) or old_uid not in {
            _clean(item) for item in raw_uids
        }:
            continue
        remapped: List[str] = []
        for raw_uid in raw_uids:
            uid = _clean(raw_uid)
            if not uid:
                continue
            if uid == new_uid:
                # If both identities somehow exist, the old row's exact slot
                # owns the durable replacement and this duplicate is retired.
                continue
            candidate = new_uid if uid == old_uid else uid
            if candidate not in remapped:
                remapped.append(candidate)
            if len(remapped) >= MAX_SHOT_IMAGES:
                break
        shot["selected_source_uids"] = remapped
        shot["revision"] = _non_negative_int(shot.get("revision")) + 1
        shot["media_count"] = min(
            len(remapped),
            _non_negative_int(shot.get("media_count")),
        )
        shot["metadata_sha256"] = ""
        shot["media_sha256"] = ""
        changed_any = True
    if changed_any:
        routing["generation"] = max(
            1,
            _non_negative_int(routing.get("generation")) + 1,
        )
        state["shot_routing"] = routing


def _apply_asset_registration(
    state: Dict[str, Any],
    request_value: Any,
    import_media_by_uid: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Commit and hydrate exactly one Add without rescanning the project."""
    normalized = _normalize_state(state)
    request = _normalize_asset_registration_request(request_value)
    if not request:
        raise ValueError("Asset registration request is incomplete.")
    project_root_text = _clean(normalized.get("project_root")).replace("\\", "/")
    project_uid = _clean(normalized.get("project_uid"))
    if not project_root_text or not project_uid:
        raise ValueError("Select a project before registering an image asset.")
    if request.get("project_uid") != project_uid:
        raise ValueError("The asset registration request belongs to a stale project.")

    catalog = _discover_project_catalog(normalized.get("catalog_root"))
    selected_project = next(
        (
            item
            for item in catalog["projects"]
            if _clean(item.get("path")).casefold() == project_root_text.casefold()
            and _clean(item.get("project_uid")) == project_uid
        ),
        None,
    )
    if selected_project is None:
        raise ValueError("The selected project is outside the active project catalog.")

    request_source_kind = request.get("source_kind", "project")
    selected_root = Path(selected_project["path"]).resolve()
    registered_library_id = request["asset_library_id"]
    registration_message = ""
    source_selection = False
    source_selection_order = 0
    copied_destination: Path | None = None
    registered_row: Dict[str, Any]
    source_index = -1

    if request_source_kind == "project":
        matches = [
            (index, asset)
            for index, asset in enumerate(normalized["assets"])
            if _clean(asset.get("asset_library_id"))
            == request.get("asset_library_id")
            and _clean(asset.get("source_kind")) == "project"
            and _non_negative_int(asset.get("import_index")) == 0
        ]
        if len(matches) > 1:
            raise ValueError("The image file changed or no longer belongs to this project.")
        if matches:
            source_index, source_asset = matches[0]
        else:
            # A file may appear after the last metadata refresh. Its stable
            # project-relative identity is sufficient to validate this exact
            # Add without falling back to a whole-project walk.
            source_index = len(normalized["assets"])
            source_asset = {
                "asset_library_id": request["asset_library_id"],
                "source_uid": f"project:{request['asset_library_id']}",
                "source_kind": "project",
                "relative_path": request.get("relative_path"),
                "registered": False,
                "selected": False,
                "selection_order": 0,
            }
        if bool(source_asset.get("registered")):
            raise ValueError(
                "This image asset is already registered and cannot be edited. "
                "Only unregistered assets can be added."
            )
        relative_text = _clean(source_asset.get("relative_path")).replace("\\", "/")
        if relative_text.casefold() != request.get("relative_path", "").casefold():
            raise ValueError("The image path changed while the registration window was open.")
        source_path, relative_text, _media_signature = _resolve_project_asset_file(
            selected_root,
            _clean(selected_project.get("project_id")),
            relative_text,
            request.get("asset_library_id"),
            allow_user_import_path=False,
        )
        manifest_records = _read_asset_manifest(selected_root)
        if relative_text.casefold() in manifest_records:
            raise ValueError(
                "This image asset is already registered and cannot be edited. "
                "Only unregistered assets can be added."
            )
        verified_dimensions = _verified_image_dimensions(source_path)
        record = _registration_record(
            request,
            {"relative_path": relative_text},
        )
        registered_row = _registered_project_asset_row(
            project_root=selected_root,
            project_id=_clean(selected_project.get("project_id")),
            project_cache_uid=_clean(normalized.get("project_cache_uid"))
            or _project_cache_uid(selected_root),
            relative_text=relative_text,
            manifest_record=record,
            previous_asset=source_asset,
            selected=bool(source_asset.get("selected")),
            selection_order=_non_negative_int(source_asset.get("selection_order")),
            verified_dimensions=verified_dimensions,
            hydrate_thumbnail=True,
        )
        manifest_path = _write_asset_manifest_record(selected_root, record)
        registration_message = f"Registered in {manifest_path.name}."
    else:
        source_matches = [
            (index, asset)
            for index, asset in enumerate(normalized["assets"])
            if _clean(asset.get("asset_library_id")) == request["asset_library_id"]
            and _clean(asset.get("source_uid")) == request["source_uid"]
            and _clean(asset.get("source_kind")) == "user"
            and _non_negative_int(asset.get("import_index")) > 0
        ]
        if len(source_matches) != 1:
            raise ValueError("The external IMAGE_IMPORT_IN source changed or is unavailable.")
        source_index, source_asset = source_matches[0]
        requested_folder = _clean(request.get("target_folder")).replace("\\", "/").strip("/")
        available_folders = {
            _clean(folder).casefold(): _clean(folder)
            for folder in normalized.get("folders", [])
            if _clean(folder)
            and not _is_user_import_relative_path(f"{_clean(folder)}/asset.png")
        }
        if not requested_folder:
            raise ValueError(
                "Select an existing Asset Folder below the project root before registering."
            )
        if requested_folder.casefold() not in available_folders:
            raise ValueError("The selected Project Folder is no longer available.")
        target_folder = available_folders[requested_folder.casefold()]
        media_lookup = import_media_by_uid or {}
        if request["source_uid"] not in media_lookup:
            raise ValueError("The external IMAGE_IMPORT_IN payload is no longer available.")
        media_value = media_lookup[request["source_uid"]]
        authoritative_import = _import_record(
            media_value,
            _non_negative_int(source_asset.get("import_index")) or 1,
        )
        if (
            authoritative_import is None
            or _clean(authoritative_import[0].get("source_uid"))
            != request["source_uid"]
        ):
            raise ValueError("The external IMAGE_IMPORT_IN identity changed.")
        copy_source_asset = dict(source_asset)
        for field in ("path", "extension", "media_ref_kind"):
            copy_source_asset[field] = authoritative_import[0].get(field)
        record = _registration_record(request, {"relative_path": ""})
        copied_destination = _copy_import_to_project(
            copy_source_asset,
            media_value,
            selected_root,
            target_folder,
        )
        relative_text = copied_destination.relative_to(selected_root).as_posix()
        record["path"] = relative_text
        record["import_source_uid"] = request["source_uid"]
        registered_library_id = _asset_library_id(
            _clean(selected_project.get("project_id")),
            relative_text,
        )
        source_selection = bool(source_asset.get("selected"))
        source_selection_order = _non_negative_int(source_asset.get("selection_order"))
        try:
            registered_row = _registered_project_asset_row(
                project_root=selected_root,
                project_id=_clean(selected_project.get("project_id")),
                project_cache_uid=_clean(normalized.get("project_cache_uid"))
                or _project_cache_uid(selected_root),
                relative_text=relative_text,
                manifest_record=record,
                selected=source_selection,
                selection_order=source_selection_order,
                verified_dimensions=_asset_dimensions(copied_destination),
                hydrate_thumbnail=True,
            )
            manifest_path = _write_asset_manifest_record(selected_root, record)
        except Exception as exc:
            cleanup_error: Exception | None = None
            try:
                copied_destination.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                cleanup_error = cleanup_exc
            if cleanup_error is not None:
                raise RuntimeError(
                    "Manifest update failed and the copied image could not be rolled "
                    f"back: {cleanup_error}"
                ) from exc
            raise
        registration_message = (
            f"Copied to {relative_text} and registered in {manifest_path.name}."
        )

    refreshed = dict(normalized)
    assets = [dict(asset) for asset in normalized["assets"]]
    if source_index < 0 or source_index > len(assets):
        raise RuntimeError("The registered asset row is no longer available.")
    if source_index == len(assets):
        assets.append(registered_row)
    else:
        assets[source_index] = registered_row
    refreshed["assets"] = assets
    refreshed["catalog_root"] = catalog["catalog_root"]
    refreshed["projects"] = catalog["projects"]
    try:
        refreshed["manifest_signature"] = _asset_manifest_signature(selected_root)
    except Exception as exc:
        # The manifest is already durable. Keep the prior signature so the
        # ordinary poll detects and reconciles it instead of reporting Add as
        # failed after commit because a share became briefly unavailable.
        _diagnostic_warning("Post-registration manifest signature refresh", exc)
    try:
        refreshed["folder_signature"] = _project_folder_metadata_signature(
            selected_root
        )
    except Exception as exc:
        _diagnostic_warning("Post-registration folder signature refresh", exc)
    refreshed["scan_revision"] = _non_negative_int(
        normalized.get("scan_revision")
    ) + 1
    if _clean(registered_row.get("thumbnail_url")):
        refreshed["thumbnail_revision"] = _non_negative_int(
            normalized.get("thumbnail_revision")
        ) + 1
    if request_source_kind == "user":
        _remap_shot_routing_source_uid(
            refreshed,
            request.get("source_uid"),
            registered_row.get("source_uid"),
        )
    refreshed["asset_registration_request"] = {}
    refreshed["asset_registration_result"] = {
        "request_id": request["request_id"],
        "ok": True,
        "asset_library_id": registered_library_id,
        "message": registration_message,
    }
    refreshed["error"] = ""
    return _normalize_state(refreshed)


def _hydrate_asset_thumbnails(
    state: Dict[str, Any],
    request_value: Any,
    *,
    normalized: bool = False,
    request_normalized: bool = False,
) -> Dict[str, Any]:
    """Hydrate a bounded selected/visible batch without changing media facts."""

    normalized_state = state if normalized else _normalize_state(state)
    request = (
        dict(request_value)
        if request_normalized and isinstance(request_value, dict)
        else _normalize_thumbnail_request(request_value)
    )
    if not request:
        return normalized_state
    requested_ids = list(request["asset_library_ids"])
    completed: List[str] = []
    failed: List[str] = []
    hydrated = dict(normalized_state)
    hydrated["thumbnail_request"] = {}

    context_matches = (
        request.get("project_uid") == _clean(normalized_state.get("project_uid"))
        and (
            not _clean(request.get("project_cache_uid"))
            or request.get("project_cache_uid")
            == _clean(normalized_state.get("project_cache_uid"))
        )
        and request.get("manifest_signature")
        == _clean(normalized_state.get("manifest_signature"))
        and _non_negative_int(request.get("scan_revision"))
        == _non_negative_int(normalized_state.get("scan_revision"))
    )
    project_root_text = _clean(normalized_state.get("project_root"))
    project_id = _clean(normalized_state.get("project_id"))
    if context_matches and project_root_text and project_id:
        try:
            context_matches = (
                _asset_manifest_signature(Path(project_root_text))
                == request.get("manifest_signature")
            )
        except Exception:
            context_matches = False

    assets = [dict(asset) for asset in normalized_state["assets"]]
    by_library_id = {
        _clean(asset.get("asset_library_id")): (index, asset)
        for index, asset in enumerate(assets)
        if _clean(asset.get("asset_library_id"))
    }
    shot_selected_uids = {
        _clean(source_uid)
        for shot in normalized_state.get("shot_routing", {}).get("shots", [])
        if isinstance(shot, dict)
        for source_uid in (
            shot.get("selected_source_uids")
            if isinstance(shot.get("selected_source_uids"), list)
            else []
        )
        if _clean(source_uid)
    }
    request_order = {library_id: index for index, library_id in enumerate(requested_ids)}
    requested_ids.sort(
        key=lambda library_id: (
            0
            if (
                library_id in by_library_id
                and (
                    bool(by_library_id[library_id][1].get("selected"))
                    or _clean(by_library_id[library_id][1].get("source_uid"))
                    in shot_selected_uids
                )
            )
            else 1,
            request_order[library_id],
        )
    )

    if context_matches:
        project_root = Path(project_root_text)
        global _ASSET_THUMBNAIL_CACHE_DEFER_COUNT
        with _ASSET_THUMBNAIL_LOCK:
            _ASSET_THUMBNAIL_CACHE_DEFER_COUNT += 1
        try:
            for library_id in requested_ids:
                match = by_library_id.get(library_id)
                if match is None:
                    failed.append(library_id)
                    continue
                index, asset = match
                if (
                    _non_negative_int(asset.get("import_index")) > 0
                    or not _clean(asset.get("relative_path"))
                ):
                    failed.append(library_id)
                    continue
                try:
                    path, _relative_text, media_signature = _resolve_project_asset_file(
                        project_root,
                        project_id,
                        asset.get("relative_path"),
                        library_id,
                        allow_user_import_path=True,
                    )
                    expected_signature = _clean(asset.get("media_signature"))
                    if expected_signature and media_signature != expected_signature:
                        failed.append(library_id)
                        continue
                    thumbnail_url = _asset_thumbnail_url_for_media(
                        path,
                        library_id,
                        media_signature,
                    )
                    if not thumbnail_url:
                        failed.append(library_id)
                        continue
                    _resolved, _size, _mtime_ns, hydrated_signature = (
                        _asset_file_facts(
                            path,
                            project_uid=normalized_state.get("project_cache_uid"),
                            relative_path=asset.get("relative_path"),
                        )
                    )
                    if hydrated_signature != media_signature:
                        failed.append(library_id)
                        continue
                    asset["thumbnail_url"] = thumbnail_url
                    asset["media_signature"] = media_signature
                    assets[index] = asset
                    completed.append(library_id)
                except Exception as exc:
                    failed.append(library_id)
                    _diagnostic_warning(
                        f"Thumbnail hydration failed for {library_id}",
                        exc,
                    )
        finally:
            with _ASSET_THUMBNAIL_LOCK:
                _ASSET_THUMBNAIL_CACHE_DEFER_COUNT = max(
                    0,
                    _ASSET_THUMBNAIL_CACHE_DEFER_COUNT - 1,
                )
                should_prune = _ASSET_THUMBNAIL_CACHE_DEFER_COUNT == 0
            if should_prune:
                _flush_persistent_thumbnail_cache_prune()
    else:
        failed.extend(requested_ids)

    hydrated["assets"] = assets
    hydrated["thumbnail_busy"] = False
    hydrated["thumbnail_revision"] = _non_negative_int(
        normalized_state.get("thumbnail_revision")
    ) + 1
    hydrated["thumbnail_result"] = {
        "request_id": request["request_id"],
        "project_uid": request["project_uid"],
        "project_cache_uid": _clean(
            request.get("project_cache_uid")
            or normalized_state.get("project_cache_uid")
        ),
        "manifest_signature": request["manifest_signature"],
        "scan_revision": request["scan_revision"],
        "completed_asset_library_ids": completed,
        "failed_asset_library_ids": failed,
    }
    return hydrated if normalized else _normalize_state(hydrated)


def _merge_async_thumbnail_result_with_live_state(
    hydration_result: Dict[str, Any],
    hydration_base: Dict[str, Any],
    live_state: Dict[str, Any],
    request_value: Any,
    *,
    inputs_normalized: bool = False,
    request_normalized: bool = False,
) -> Dict[str, Any]:
    """Patch thumbnail_url only when worker and live filesystem identities agree."""

    hydrated = (
        hydration_result
        if inputs_normalized
        else _normalize_state(hydration_result)
    )
    base = hydration_base if inputs_normalized else _normalize_state(hydration_base)
    live = live_state if inputs_normalized else _normalize_state(live_state)
    request = (
        dict(request_value)
        if request_normalized and isinstance(request_value, dict)
        else _normalize_thumbnail_request(request_value)
    )
    result = _normalize_thumbnail_result(hydrated.get("thumbnail_result"))
    result_matches_request = bool(request) and bool(result) and (
        result.get("request_id") == request.get("request_id")
        and result.get("project_uid") == request.get("project_uid")
        and (
            not _clean(request.get("project_cache_uid"))
            or result.get("project_cache_uid") == request.get("project_cache_uid")
        )
        and result.get("manifest_signature") == request.get("manifest_signature")
        and _non_negative_int(result.get("scan_revision"))
        == _non_negative_int(request.get("scan_revision"))
        and _clean(hydrated.get("project_uid")) == request.get("project_uid")
        and (
            not _clean(request.get("project_cache_uid"))
            or _clean(hydrated.get("project_cache_uid"))
            == request.get("project_cache_uid")
        )
        and _clean(hydrated.get("manifest_signature"))
        == request.get("manifest_signature")
        and _non_negative_int(hydrated.get("scan_revision"))
        == _non_negative_int(request.get("scan_revision"))
        and _clean(base.get("project_uid")) == request.get("project_uid")
        and (
            not _clean(request.get("project_cache_uid"))
            or _clean(base.get("project_cache_uid"))
            == request.get("project_cache_uid")
        )
        and _clean(base.get("manifest_signature"))
        == request.get("manifest_signature")
        and _non_negative_int(base.get("scan_revision"))
        == _non_negative_int(request.get("scan_revision"))
    )
    if not result_matches_request:
        return live
    merged = dict(live)
    # Any request received during this single-flight batch was deliberately
    # rejected; completion clears the intent and the browser recomputes the
    # next bounded missing-ID batch from this authoritative result.
    merged["thumbnail_request"] = {}
    context_matches = (
        request.get("project_uid") == _clean(live.get("project_uid"))
        and (
            not _clean(request.get("project_cache_uid"))
            or request.get("project_cache_uid")
            == _clean(live.get("project_cache_uid"))
        )
        and request.get("manifest_signature") == _clean(live.get("manifest_signature"))
        and _non_negative_int(request.get("scan_revision"))
        == _non_negative_int(live.get("scan_revision"))
    )
    completed_ids = set(result.get("completed_asset_library_ids", []))
    hydrated_assets = {
        _clean(asset.get("asset_library_id")): asset
        for asset in hydrated.get("assets", [])
        if _clean(asset.get("asset_library_id")) in completed_ids
    }
    assets: List[Dict[str, Any]] = []
    actually_completed: List[str] = []
    for raw_asset in live.get("assets", []):
        asset = dict(raw_asset)
        library_id = _clean(asset.get("asset_library_id"))
        worker_asset = hydrated_assets.get(library_id) if context_matches else None
        if (
            worker_asset is not None
            and _clean(worker_asset.get("media_signature"))
            and _clean(worker_asset.get("media_signature"))
            == _clean(asset.get("media_signature"))
            and _clean(worker_asset.get("thumbnail_url"))
        ):
            asset["thumbnail_url"] = _clean(worker_asset.get("thumbnail_url"))
            actually_completed.append(library_id)
        assets.append(asset)
    failed_ids = list(result.get("failed_asset_library_ids", []))
    for library_id in result.get("completed_asset_library_ids", []):
        if library_id not in actually_completed and library_id not in failed_ids:
            failed_ids.append(library_id)
    merged["assets"] = assets
    merged["thumbnail_busy"] = False
    merged["thumbnail_revision"] = max(
        _non_negative_int(live.get("thumbnail_revision")),
        _non_negative_int(hydrated.get("thumbnail_revision")),
    )
    if result:
        merged["thumbnail_result"] = {
            **result,
            "completed_asset_library_ids": actually_completed,
            "failed_asset_library_ids": failed_ids,
        }
    return merged if inputs_normalized else _normalize_state(merged)


def _merge_import_input(
    state: Dict[str, Any],
    value: Any,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    normalized = _normalize_state(state)
    if not _flatten_import_values(value):
        return normalized, {}
    imports, media_by_uid = _normalize_import_input(
        value,
        normalized["assets"],
    )
    # IMAGE_IMPORT_IN is an authoritative ParameterList snapshot.  Preserve
    # verified project assets, but rebuild live external rows from the current
    # aggregate so disconnecting one edge removes only that source and never
    # leaves stale imports behind.
    assets = [
        dict(asset)
        for asset in normalized["assets"]
        if not (
            _clean(asset.get("source_kind")) == "user"
            and _non_negative_int(asset.get("import_index")) > 0
        )
    ]
    by_library_id = {
        _clean(asset.get("asset_library_id")): index
        for index, asset in enumerate(assets)
    }
    by_source_uid = {
        _clean(asset.get("source_uid")): index
        for index, asset in enumerate(assets)
    }
    existing_asset_ids = {
        _clean(asset.get("asset_id")): _clean(asset.get("source_uid"))
        for asset in assets
        if _clean(asset.get("asset_id"))
    }
    registered_import_uids = {
        _clean(asset.get("import_source_uid"))
        for asset in assets
        if _clean(asset.get("source_kind")) == "project"
        and bool(asset.get("registered"))
        and _clean(asset.get("import_source_uid"))
    }
    for imported in imports:
        imported["asset_project_uid"] = ""
        uid = _clean(imported.get("source_uid"))
        if uid in registered_import_uids:
            continue
        library_id = _clean(imported.get("asset_library_id"))
        match_index = by_source_uid.get(uid)
        if match_index is None:
            match_index = by_library_id.get(library_id)
        if match_index is not None:
            previous = assets[match_index]
            for field in (
                "asset_id",
                "image_name",
                "selected",
                "selection_order",
            ):
                if field in previous:
                    imported[field] = previous[field]
            assets[match_index] = imported
            continue
        asset_id = _clean(imported.get("asset_id"))
        if asset_id in existing_asset_ids and existing_asset_ids[asset_id] != uid:
            imported["asset_id"] = f"{asset_id}_{uid[-6:]}"
        assets.append(imported)
        by_library_id[library_id] = len(assets) - 1
        by_source_uid[uid] = len(assets) - 1
        existing_asset_ids[_clean(imported.get("asset_id"))] = uid
    normalized["assets"] = assets
    normalized["scan_revision"] = _non_negative_int(
        normalized.get("scan_revision")
    ) + 1
    return _normalize_state(normalized), media_by_uid


def _remove_live_imports(state: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_state(state)
    normalized["assets"] = [
        dict(asset)
        for asset in normalized["assets"]
        if not (
            _clean(asset.get("source_kind")) == "user"
            and _non_negative_int(asset.get("import_index")) > 0
        )
    ]
    normalized["scan_revision"] = _non_negative_int(
        normalized.get("scan_revision")
    ) + 1
    return _normalize_state(normalized)


def _source_parameter_output_value(
    source_node: Any,
    parameter_name: str,
) -> tuple[bool, Any]:
    """Read one connected output without guessing when the host hides it."""
    for attribute_name in ("parameter_output_values", "parameter_values"):
        values = getattr(source_node, attribute_name, None)
        if isinstance(values, dict) and parameter_name in values:
            return True, values[parameter_name]
    getter = getattr(source_node, "get_parameter_value", None)
    if callable(getter):
        try:
            return True, getter(parameter_name)
        except Exception:
            pass
    parameter = _get_parameter_obj(source_node, parameter_name)
    if parameter is not None and hasattr(parameter, "default_value"):
        return True, getattr(parameter, "default_value")
    return False, None


def _is_image_import_parameter(parameter: Any) -> bool:
    return (
        _clean(getattr(parameter, "name", "")) == IMAGE_IMPORT_PARAMETER
        or _clean(getattr(parameter, "parent_container_name", ""))
        == IMAGE_IMPORT_PARAMETER
    )


def _image_import_target_parameter_names(node: Any) -> set[str]:
    names = {IMAGE_IMPORT_PARAMETER}
    parameter_list = _get_parameter_obj(node, IMAGE_IMPORT_PARAMETER)
    if parameter_list is None:
        return names
    getter = getattr(parameter_list, "get_child_parameters", None)
    try:
        children = getter() if callable(getter) else []
    except Exception:
        children = []
    for child in children:
        name = _clean(getattr(child, "name", ""))
        if name:
            names.add(name)
    return names


def _single_import_connection_for_uid(
    node_manager: Any,
    incoming_connections: Sequence[Any],
    source_uid: str,
    target_parameter_names: Sequence[str] | None = None,
) -> Any:
    """Resolve exactly one single-image IMAGE_IMPORT_IN edge for a card X."""
    requested_uid = _normalize_disconnect_import_uid(source_uid)
    if not requested_uid:
        raise ValueError("The external image identity is invalid.")

    allowed_targets = {
        _clean(name)
        for name in (target_parameter_names or (IMAGE_IMPORT_PARAMETER,))
        if _clean(name)
    }
    matches: List[tuple[Any, set[str]]] = []
    unresolved: List[str] = []
    for connection in incoming_connections:
        if _clean(getattr(connection, "target_parameter_name", "")) not in allowed_targets:
            continue
        source_node_name = _clean(getattr(connection, "source_node_name", ""))
        source_parameter_name = _clean(
            getattr(connection, "source_parameter_name", "")
        )
        if not source_node_name or not source_parameter_name:
            unresolved.append(source_node_name or "unknown source")
            continue
        try:
            source_node = node_manager.get_node_by_name(source_node_name)
            readable, source_value = _source_parameter_output_value(
                source_node,
                source_parameter_name,
            )
            if not readable:
                unresolved.append(source_node_name)
                continue
            imports, _media_by_uid = _normalize_import_input(source_value, [])
        except Exception:
            unresolved.append(source_node_name)
            continue
        connected_uids = {
            _clean(item.get("source_uid"))
            for item in imports
            if _clean(item.get("source_uid"))
        }
        if requested_uid in connected_uids:
            matches.append((connection, connected_uids))

    if unresolved:
        raise RuntimeError(
            "Not every IMAGE_IMPORT_IN source could be inspected safely; "
            "disconnect the wire at the input port."
        )
    if not matches:
        raise RuntimeError(
            "No IMAGE_IMPORT_IN edge uniquely matches this external image; "
            "disconnect the wire at the input port."
        )
    if len(matches) != 1:
        raise RuntimeError(
            "More than one IMAGE_IMPORT_IN edge matches this external image; "
            "disconnect the intended wire at the input port."
        )
    connection, connected_uids = matches[0]
    if connected_uids != {requested_uid}:
        raise RuntimeError(
            "This IMAGE_IMPORT_IN edge carries multiple images and cannot be "
            "removed from a single card; disconnect the wire at the input port."
        )
    return connection


def _disconnect_import_connection(node: Any, source_uid: str) -> None:
    """Delete one proven single-image incoming edge through retained mode."""
    try:
        from griptape_nodes.retained_mode.events.connection_events import (  # type: ignore
            DeleteConnectionRequest,
            DeleteConnectionResultSuccess,
            ListConnectionsForNodeRequest,
            ListConnectionsForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import (  # type: ignore
            GriptapeNodes,
        )
    except Exception as exc:
        raise RuntimeError(
            "Graph disconnection is unavailable in this host; disconnect the "
            "wire at IMAGE_IMPORT_IN."
        ) from exc

    node_name = _clean(getattr(node, "name", ""))
    if not node_name:
        raise RuntimeError("The Image Asset node has no graph identity.")
    result = GriptapeNodes.handle_request(
        ListConnectionsForNodeRequest(node_name=node_name)
    )
    if not isinstance(result, ListConnectionsForNodeResultSuccess):
        details = _clean(getattr(result, "result_details", ""))
        raise RuntimeError(
            details or "IMAGE_IMPORT_IN connections could not be inspected safely."
        )
    connection = _single_import_connection_for_uid(
        GriptapeNodes.NodeManager(),
        result.incoming_connections,
        source_uid,
        _image_import_target_parameter_names(node),
    )
    delete_result = GriptapeNodes.handle_request(
        DeleteConnectionRequest(
            source_node_name=connection.source_node_name,
            source_parameter_name=connection.source_parameter_name,
            target_node_name=node_name,
            target_parameter_name=connection.target_parameter_name,
        )
    )
    if not isinstance(delete_result, DeleteConnectionResultSuccess):
        details = _clean(getattr(delete_result, "result_details", ""))
        raise RuntimeError(
            details or "Griptape could not disconnect the selected external image."
        )


def _resolved_media_value(media_value: Any) -> str:
    """Return the exact string accepted by a generator media-list input."""
    if isinstance(media_value, str) and media_value.strip():
        return media_value.strip()
    artifact_value = _artifact_field(media_value, "value")
    if isinstance(artifact_value, str) and artifact_value.strip():
        return artifact_value.strip()
    raw_bytes = (
        bytes(artifact_value)
        if isinstance(artifact_value, (bytes, bytearray))
        else bytes(media_value)
        if isinstance(media_value, (bytes, bytearray))
        else b""
    )
    if raw_bytes:
        return (
            "data:image/png;base64,"
            + base64.b64encode(raw_bytes).decode("ascii")
        )
    embedded = _artifact_field(media_value, "base64")
    if callable(embedded):
        try:
            embedded = embedded()
        except Exception:
            embedded = None
    if isinstance(embedded, str) and embedded:
        if embedded.startswith("data:image/"):
            return embedded
        image_format = _clean(
            _artifact_field(media_value, "format")
        ).casefold() or "png"
        return f"data:image/{image_format};base64,{embedded}"
    return ""


_PROJECT_RESOLUTION_KEY_FIELDS = (
    "asset_library_id",
    "source_uid",
    "source_kind",
    "asset_project_uid",
    "asset_id",
    "image_name",
    "path",
    "relative_path",
    "extension",
    "image_main_type",
    "image_sub_type",
    "source_type",
    "custom_source_type",
    "scope_candidate",
    "registered",
    "media_ref_kind",
    "connected",
)


def _media_resolution_identity(value: Any, import_revision: int) -> Dict[str, Any]:
    """Describe imported media without decoding or copying its payload.

    IMAGE_IMPORT_IN updates advance ``import_revision``.  Object identity is
    therefore sufficient for opaque host artifacts, while immutable textual
    references use a bounded digest so a large data URI never becomes a cache
    key itself.
    """
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        encoded = value.encode("utf-8", errors="surrogatepass")
        return {
            "kind": "str",
            "length": len(encoded),
            "digest": hashlib.sha256(encoded).hexdigest(),
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "kind": type(value).__name__,
            "length": len(value),
            "object_id": id(value),
            "import_revision": _non_negative_int(import_revision),
        }
    return {
        "kind": type(value).__name__,
        "object_id": id(value),
        "import_revision": _non_negative_int(import_revision),
    }


def _asset_resolution_cache_key(
    asset: Dict[str, Any],
    state: Dict[str, Any],
    import_revision: int,
) -> str:
    source_kind = _clean(asset.get("source_kind")).casefold()
    if source_kind == "project":
        payload: Dict[str, Any] = {
            "kind": "project",
            "project_root": _clean(state.get("project_root")),
            "project_id": _clean(state.get("project_id")),
            "project_uid": _clean(state.get("project_uid")),
            "project_cache_uid": _clean(state.get("project_cache_uid")),
            "manifest_signature": _clean(state.get("manifest_signature")),
            "scan_revision": _non_negative_int(state.get("scan_revision")),
            "asset": {
                field: asset.get(field)
                for field in _PROJECT_RESOLUTION_KEY_FIELDS
            },
        }
    else:
        source_uid = _clean(asset.get("source_uid"))
        payload = {
            "kind": "user",
            "source_uid": source_uid,
            "asset_library_id": _clean(asset.get("asset_library_id")),
            "path": _clean(asset.get("path")),
            "media_ref_kind": _clean(asset.get("media_ref_kind")),
            "connected": bool(asset.get("connected", True)),
            "import_revision": _non_negative_int(import_revision),
        }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolution_cache_get(
    cache: OrderedDict[str, Dict[str, Any]] | None,
    key: str,
) -> Dict[str, Any] | None:
    if not isinstance(cache, OrderedDict) or not key:
        return None
    cached = cache.get(key)
    if not isinstance(cached, dict):
        return None
    cache.move_to_end(key)
    return cached


def _resolution_cache_put(
    cache: OrderedDict[str, Dict[str, Any]] | None,
    key: str,
    value: Dict[str, Any],
) -> None:
    if not isinstance(cache, OrderedDict) or not key:
        return
    cache[key] = dict(value)
    cache.move_to_end(key)
    while len(cache) > _ASSET_RESOLUTION_CACHE_LIMIT:
        cache.popitem(last=False)


def _import_media_map_identity(media_by_uid: Dict[str, Any]) -> str:
    payload = [
        (
            _clean(source_uid),
            _media_resolution_identity(media_value, 0),
        )
        for source_uid, media_value in sorted(
            (media_by_uid or {}).items(),
            key=lambda item: _clean(item[0]),
        )
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolution_cache_state_identity(state: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "catalog_root": _clean(state.get("catalog_root")),
            "project_root": _clean(state.get("project_root")),
            "project_id": _clean(state.get("project_id")),
            "project_uid": _clean(state.get("project_uid")),
            "project_cache_uid": _clean(state.get("project_cache_uid")),
            "manifest_signature": _clean(state.get("manifest_signature")),
            "scan_revision": _non_negative_int(state.get("scan_revision")),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_selected_assets(
    state: Dict[str, Any],
    media_by_uid: Dict[str, Any] | None = None,
    *,
    resolution_cache: OrderedDict[str, Dict[str, Any]] | None = None,
    import_revision: int = 0,
    force: bool = False,
    normalized: bool = False,
) -> Dict[str, Any]:
    """Resolve one authoritative selection for metadata and generator media.

    Selection order in widget state is the requested order.  Only rows with
    concrete media enter the published order; omitted rows retain their
    requested order and source identity in diagnostics so a missing image can
    never shift ``@imageN`` onto a different fan-out item silently.
    """
    normalized_state = state if normalized else _normalize_state(state)
    normalized = normalized_state
    media_lookup = media_by_uid if isinstance(media_by_uid, dict) else {}
    ordered = sorted(
        [
            asset
            for asset in normalized["assets"]
            if bool(asset.get("selected"))
        ],
        key=lambda asset: _non_negative_int(asset.get("selection_order")),
    )[:MAX_SELECTED_IMAGES]
    manifest_records: Dict[str, Dict[str, Any]] | None = None
    manifest_loaded = False
    resolved: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    for asset in ordered:
        requested_order = _non_negative_int(asset.get("selection_order"))
        source_uid = _clean(asset.get("source_uid"))
        image_name = _clean(asset.get("image_name"))
        source_kind = _clean(asset.get("source_kind")).casefold()
        cache_key = _asset_resolution_cache_key(
            asset,
            normalized,
            import_revision,
        )
        cached = (
            None
            if force
            else _resolution_cache_get(resolution_cache, cache_key)
        )
        if cached is None:
            relative_path = ""
            media_value = ""
            reason = ""
            if source_kind == "project":
                if not manifest_loaded:
                    manifest_loaded = True
                    try:
                        project_root = _clean(normalized.get("project_root"))
                        manifest_records = (
                            _read_asset_manifest(Path(project_root))
                            if project_root
                            else {}
                        )
                    except Exception:
                        # One failed shared-manifest read invalidates all project
                        # selections in this immutable resolution snapshot.
                        manifest_records = {}
                relative_path = _verified_project_relative_path(
                    asset,
                    normalized,
                    manifest_records,
                )
                if relative_path:
                    media_value = _resolved_media_value(asset.get("path"))
                else:
                    reason = "project_asset_verification_failed"
            else:
                media_value = _resolved_media_value(asset.get("path"))
                if not media_value:
                    media_value = _resolved_media_value(media_lookup.get(source_uid))
                if not media_value:
                    reason = "external_media_unavailable"
            cached = {
                "relative_path": relative_path,
                "media": media_value,
                "reason": reason,
            }
            _resolution_cache_put(resolution_cache, cache_key, cached)
        relative_path = _clean(cached.get("relative_path"))
        media_value = _clean(cached.get("media"))
        reason = _clean(cached.get("reason"))
        if not media_value:
            unresolved.append(
                {
                    "source_uid": source_uid,
                    "image_name": image_name,
                    "requested_selection_order": requested_order,
                    "reason": reason or "media_unavailable",
                }
            )
            continue
        resolved.append(
            {
                "asset": asset,
                "media": media_value,
                "source_uid": source_uid,
                "requested_selection_order": requested_order,
                "selection_order": len(resolved) + 1,
                "relative_path": relative_path,
            }
        )
    warnings = [
        (
            f'Selected image #{item["requested_selection_order"]} '
            f'"{item["image_name"]}" ({item["source_uid"] or "missing source_uid"}) '
            "has no resolvable media and was omitted from both ASSET_OUT and "
            "Video Generation Out."
        )
        for item in unresolved
    ]
    return {
        "state": normalized,
        "selected_count": len(ordered),
        "resolved": resolved,
        "unresolved": unresolved,
        "warnings": warnings,
    }


def _selected_media_values(
    state: Dict[str, Any],
    media_by_uid: Dict[str, Any],
) -> List[str]:
    selection = _resolve_selected_assets(state, media_by_uid)
    return [item["media"] for item in selection["resolved"]]


def _selection_id(
    state: Dict[str, Any],
    resolved_selection: Dict[str, Any] | None = None,
) -> str:
    if isinstance(resolved_selection, dict):
        selected_assets = [
            item
            for item in resolved_selection.get("resolved", [])
            if isinstance(item, dict) and isinstance(item.get("asset"), dict)
        ]
    else:
        ordered_assets = sorted(
            [
                asset
                for asset in state.get("assets", [])
                if isinstance(asset, dict) and bool(asset.get("selected"))
            ],
            key=lambda asset: _non_negative_int(asset.get("selection_order")),
        )
        manifest_records: Dict[str, Dict[str, Any]] | None = None
        if any(
            _clean(asset.get("source_kind")).casefold() == "project"
            and bool(asset.get("registered"))
            for asset in ordered_assets
        ):
            try:
                project_root = _clean(state.get("project_root"))
                manifest_records = (
                    _read_asset_manifest(Path(project_root)) if project_root else {}
                )
            except Exception:
                manifest_records = {}
        selected_assets = [
            {
                "asset": asset,
                "selection_order": _non_negative_int(
                    asset.get("selection_order")
                ),
                "relative_path": _verified_project_relative_path(
                    asset,
                    state,
                    manifest_records,
                ),
            }
            for asset in ordered_assets
        ]
    selected: List[Dict[str, Any]] = []
    for resolved_item in selected_assets:
        asset = resolved_item["asset"]
        selection_order = _non_negative_int(
            resolved_item.get("selection_order")
        )
        relative_path = _clean(resolved_item.get("relative_path"))
        if relative_path:
            selected.append(
                {
                    "order_key": asset["source_uid"],
                    "verified_asset": True,
                    "asset_library_id": asset["asset_library_id"],
                    "asset_id": asset["asset_id"],
                    "image_name": asset["image_name"],
                    "relative_path": relative_path,
                    "image_main_type": asset["image_main_type"],
                    "image_sub_type": asset["image_sub_type"],
                    "source_type": asset["source_type"],
                    "scope_candidate": asset["scope_candidate"],
                    "selection_order": selection_order,
                }
            )
        elif _clean(asset.get("source_kind")).casefold() == "user":
            selected.append(
                {
                    "order_key": asset["source_uid"],
                    "image_name": asset["image_name"],
                    "selection_order": selection_order,
                }
            )
    canonical = json.dumps(
        {
            "project_id": state.get("project_id", ""),
            "selected": selected,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_output_payload(
    state: Dict[str, Any],
    media_by_uid: Dict[str, Any] | None = None,
    resolved_selection: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    selection = (
        resolved_selection
        if isinstance(resolved_selection, dict)
        else _resolve_selected_assets(state, media_by_uid)
    )
    normalized = selection["state"]
    ordered_images: List[Dict[str, Any]] = []
    verified_assets: List[Dict[str, Any]] = []
    imported_images: List[Dict[str, Any]] = []
    for resolved_item in selection["resolved"]:
        asset = resolved_item["asset"]
        relative_path = _clean(resolved_item.get("relative_path"))
        output_index = _non_negative_int(resolved_item.get("selection_order"))
        descriptor = {
            "order_key": asset["source_uid"],
            "image_name": asset["image_name"],
            "selection_order": output_index,
        }
        ordered_images.append(descriptor)
        if not relative_path:
            imported_images.append(dict(descriptor))
            continue
        verified_assets.append(
            {
                "selected": True,
                "verified_asset": True,
                "binding_mode": "verified_asset",
                "order_key": asset["source_uid"],
                "source_uid": asset["source_uid"],
                "source_kind": "project",
                "asset_library_id": asset["asset_library_id"],
                "asset_id": asset["asset_id"],
                "image_name": asset["image_name"],
                "path": asset["path"],
                "relative_path": relative_path,
                "width": asset["width"],
                "height": asset["height"],
                "image_main_type": asset["image_main_type"],
                "image_sub_type": asset["image_sub_type"],
                "source_type": asset["source_type"],
                "custom_source_type": asset["custom_source_type"],
                "scope_candidate": asset["scope_candidate"],
                "color_pick_candidates": list(asset["color_pick_candidates"]),
                "selection_order": output_index,
                "binding_capabilities": {
                    "schema": IMAGE_BINDING_CAPABILITY_SCHEMA,
                    "version": IMAGE_BINDING_CAPABILITY_VERSION,
                    "image_source_frame_range": True,
                },
            }
        )
    return {
        "schema": OUTPUT_SCHEMA,
        "version": OUTPUT_VERSION,
        "mode": "image_asset",
        "project_id": normalized["project_id"],
        "project_uid": normalized["project_uid"],
        "project_root": normalized["project_root"],
        "selection_id": _selection_id(normalized, selection),
        "ordered_images": ordered_images,
        "verified_assets": verified_assets,
        "selected_assets": verified_assets,
        "imported_images": imported_images,
        "binding_contract": {
            "schema": IMAGE_BINDING_CAPABILITY_SCHEMA,
            "version": IMAGE_BINDING_CAPABILITY_VERSION,
            "source_identity_fields": ["source_uid", "order_key"],
            "image_source_frame_range": {
                "supported": True,
                "enabled_by_default": False,
            },
        },
        "media_resolution": {
            "selected_count": selection["selected_count"],
            "resolved_count": len(selection["resolved"]),
            "unresolved_count": len(selection["unresolved"]),
            "status": "partial" if selection["unresolved"] else "complete",
            "resolved": [
                {
                    "source_uid": item["source_uid"],
                    "requested_selection_order": item["requested_selection_order"],
                    "selection_order": item["selection_order"],
                }
                for item in selection["resolved"]
            ],
            "unresolved": [dict(item) for item in selection["unresolved"]],
        },
        "warnings": list(selection["warnings"]),
        "authority_scope": {
            "schema": IMAGE_AUTHORITY_SCOPE_SCHEMA,
            "version": IMAGE_AUTHORITY_SCOPE_VERSION,
            "verified_metadata_fields": [
                "project_uid",
                "image_main_type",
                "image_sub_type",
                "source_type",
                "asset_id",
                "image_name",
                "scope_candidate",
                "color_pick_candidates",
            ],
            "external_metadata_fields": [
                "source_uid",
                "image_name",
                "selection_order",
            ],
            "downstream_binding_fields": [
                "target",
                "color_pick",
                "image_source_frame_range",
            ],
        },
    }


def _build_synchronized_outputs(
    state: Dict[str, Any],
    media_by_uid: Dict[str, Any],
    *,
    resolution_cache: OrderedDict[str, Dict[str, Any]] | None = None,
    import_revision: int = 0,
    force: bool = False,
    normalized: bool = False,
) -> tuple[Dict[str, Any], List[str]]:
    """Build both public outputs from one immutable resolution snapshot."""
    selection = _resolve_selected_assets(
        state,
        media_by_uid,
        resolution_cache=resolution_cache,
        import_revision=import_revision,
        force=force,
        normalized=normalized,
    )
    return (
        _build_output_payload(
            selection["state"],
            media_by_uid,
            resolved_selection=selection,
        ),
        [item["media"] for item in selection["resolved"]],
    )


def _shot_asset_metadata(
    resolved_item: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the rich per-image ASSET_OUT record used by remote consumers."""
    asset = resolved_item["asset"]
    source_uid = _clean(resolved_item.get("source_uid"))
    selection_order = _non_negative_int(resolved_item.get("selection_order"))
    relative_path = _clean(resolved_item.get("relative_path"))
    verified = bool(relative_path)
    metadata = {
        "selected": True,
        "verified_asset": verified,
        "binding_mode": "verified_asset" if verified else "external_image",
        "order_key": source_uid,
        "source_uid": source_uid,
        "source_kind": _clean(asset.get("source_kind")),
        "asset_project_uid": _clean(asset.get("asset_project_uid")),
        "asset_library_id": _clean(asset.get("asset_library_id")),
        "asset_id": _clean(asset.get("asset_id")),
        "image_name": _clean(asset.get("image_name")),
        "label": _clean(asset.get("image_name")),
        "width": _non_negative_int(asset.get("width")),
        "height": _non_negative_int(asset.get("height")),
        "image_main_type": _clean(asset.get("image_main_type")),
        "image_sub_type": _clean(asset.get("image_sub_type")),
        "source_type": _clean(asset.get("source_type")),
        "custom_source_type": _clean(asset.get("custom_source_type")),
        "scope_candidate": _clean(asset.get("scope_candidate")),
        "color_pick_candidates": [
            _clean(item)
            for item in (asset.get("color_pick_candidates") or [])
            if _clean(item)
        ],
        "selection_order": selection_order,
        "identity": {
            "asset_id": _clean(asset.get("asset_id")),
            "asset_library_id": _clean(asset.get("asset_library_id")),
            "source_uid": source_uid,
            "project_uid": _clean(asset.get("asset_project_uid")),
            "selection_order": selection_order,
            "source_kind": _clean(asset.get("source_kind")),
            "verified": verified,
        },
        "binding_capabilities": {
            "schema": IMAGE_BINDING_CAPABILITY_SCHEMA,
            "version": IMAGE_BINDING_CAPABILITY_VERSION,
            "image_source_frame_range": True,
        },
    }
    return metadata


def _shot_media_descriptors(
    ordered_source_uids: Sequence[str],
    media_by_source_uid: Dict[str, str],
) -> List[Dict[str, str]]:
    return [
        {
            "source_uid": source_uid,
            "media_value_sha256": hashlib.sha256(
                media_by_source_uid[source_uid].encode("utf-8")
            ).hexdigest(),
        }
        for source_uid in ordered_source_uids
        if source_uid in media_by_source_uid
    ]


def _build_shot_routing_snapshot(
    state: Dict[str, Any],
    media_by_uid: Dict[str, Any] | None = None,
    *,
    resolution_cache: OrderedDict[str, Dict[str, Any]] | None = None,
    import_revision: int = 0,
    force: bool = False,
    generation: int | None = None,
    normalized: bool = False,
) -> Dict[str, Any]:
    """Resolve one immutable metadata/media pair for every configured shot."""
    selection = _resolve_selected_assets(
        state,
        media_by_uid,
        resolution_cache=resolution_cache,
        import_revision=import_revision,
        force=force,
        normalized=normalized,
    )
    normalized = selection["state"]
    routing = normalized["shot_routing"]
    ordered_assets: List[Dict[str, Any]] = []
    media_by_source_uid: Dict[str, str] = {}
    seen_source_uids: set[str] = set()
    for item in selection["resolved"]:
        source_uid = _clean(item.get("source_uid"))
        media_value = _clean(item.get("media"))
        if not source_uid or not media_value or source_uid in seen_source_uids:
            continue
        seen_source_uids.add(source_uid)
        ordered_assets.append(
            {
                "source_uid": source_uid,
                "metadata": _shot_asset_metadata(item),
            }
        )
        media_by_source_uid[source_uid] = media_value
    resolved_uids = [item["source_uid"] for item in ordered_assets]
    resolved_set = set(resolved_uids)
    shots = [
        {
            "shot_uuid": shot["shot_uuid"],
            "number": shot["number"],
            "name": shot["name"],
            "revision": shot["revision"],
            "selected_source_uids": [
                uid
                for uid in shot["selected_source_uids"]
                if uid in resolved_set
            ],
        }
        for shot in routing["shots"]
    ]
    resolved_generation = max(
        1,
        _non_negative_int(
            routing.get("generation") if generation is None else generation
        ),
    )
    metadata_document = {
        "channel_uuid": routing["channel_uuid"],
        "generation": resolved_generation,
        "shots": shots,
        "ordered_assets": ordered_assets,
    }
    media_document = {
        "media_descriptors": _shot_media_descriptors(
            resolved_uids,
            media_by_source_uid,
        )
    }
    return {
        "schema": SHOT_ROUTING_SNAPSHOT_SCHEMA,
        "version": SHOT_ROUTING_SNAPSHOT_VERSION,
        "publisher_instance_uuid": routing["publisher_instance_uuid"],
        "channel_uuid": routing["channel_uuid"],
        "generation": resolved_generation,
        "metadata_sha256": _sha256_canonical(metadata_document),
        "media_sha256": _sha256_canonical(media_document),
        "shots": shots,
        "ordered_assets": ordered_assets,
        "media_by_source_uid": media_by_source_uid,
    }


def _apply_shot_routing_state_facts(
    state: Dict[str, Any],
    snapshot: Dict[str, Any],
) -> None:
    """Copy only compact counts/hashes from a private runtime snapshot."""
    routing_state = state.get("shot_routing")
    if not isinstance(routing_state, dict):
        return
    generation = _non_negative_int(snapshot.get("generation"))
    routing_state["generation"] = max(1, generation)
    snapshot_shots = {
        item["shot_uuid"]: item
        for item in snapshot.get("shots", [])
        if isinstance(item, dict) and _clean(item.get("shot_uuid"))
    }
    assets_by_uid = {
        item["source_uid"]: item
        for item in snapshot.get("ordered_assets", [])
        if isinstance(item, dict) and _clean(item.get("source_uid"))
    }
    snapshot_media = snapshot.get("media_by_source_uid")
    if not isinstance(snapshot_media, dict):
        snapshot_media = {}
    for shot in routing_state.get("shots", []):
        if not isinstance(shot, dict):
            continue
        resolved_shot = snapshot_shots.get(_clean(shot.get("shot_uuid")))
        selected_uids = (
            list(resolved_shot.get("selected_source_uids", []))
            if isinstance(resolved_shot, dict)
            else []
        )
        selected_assets = [
            assets_by_uid[uid]
            for uid in selected_uids
            if uid in assets_by_uid
        ]
        selected_media = {
            uid: snapshot_media[uid]
            for uid in selected_uids
            if uid in snapshot_media
        }
        shot["media_count"] = len(selected_media)
        shot["metadata_sha256"] = _sha256_canonical(
            {
                "channel_uuid": snapshot.get("channel_uuid", ""),
                "generation": max(1, generation),
                "shot": resolved_shot or {},
                "ordered_assets": selected_assets,
            }
        )
        shot["media_sha256"] = _sha256_canonical(
            {
                "media_descriptors": _shot_media_descriptors(
                    selected_uids,
                    selected_media,
                )
            }
        )


_OUTPUT_FINGERPRINT_ASSET_FIELDS = (
    "asset_library_id",
    "source_uid",
    "source_kind",
    "asset_project_uid",
    "asset_id",
    "image_name",
    "path",
    "relative_path",
    "width",
    "height",
    "image_main_type",
    "image_sub_type",
    "source_type",
    "custom_source_type",
    "scope_candidate",
    "registered",
    "selection_order",
    "media_ref_kind",
    "connected",
)


def _project_output_fingerprint(
    state: Dict[str, Any],
    media_by_uid: Dict[str, Any] | None = None,
    import_revision: int = 0,
) -> str:
    """Fingerprint an in-memory output-resolution snapshot.

    UI fields are intentionally excluded so a search, language, or panel click
    does not touch the filesystem. Manifest polling advances the state signature
    for normal UI updates, while ``process()`` forces a fresh filesystem-backed
    resolution before execution.
    """
    selected = sorted(
        [
            asset
            for asset in state.get("assets", [])
            if isinstance(asset, dict) and bool(asset.get("selected"))
        ],
        key=lambda asset: _non_negative_int(asset.get("selection_order")),
    )[:MAX_SELECTED_IMAGES]
    selected_payload: List[Dict[str, Any]] = []
    for asset in selected:
        item = {
            field: asset.get(field)
            for field in _OUTPUT_FINGERPRINT_ASSET_FIELDS
        }
        item["color_pick_candidates"] = list(
            asset.get("color_pick_candidates") or []
        )
        if _clean(asset.get("source_kind")).casefold() != "project":
            item["import_revision"] = _non_negative_int(import_revision)
        selected_payload.append(item)

    canonical = json.dumps(
        {
            "project_root": _clean(state.get("project_root")),
            "project_id": _clean(state.get("project_id")),
            "project_uid": _clean(state.get("project_uid")),
            "project_cache_uid": _clean(state.get("project_cache_uid")),
            "manifest_signature": _clean(state.get("manifest_signature")),
            "scan_revision": _non_negative_int(state.get("scan_revision")),
            "selected": selected_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _repair_output_port(
    node: Any,
    parameter_name: str,
    display_name: str,
) -> None:
    parameter = _get_parameter_obj(node, parameter_name)
    if parameter is None:
        return
    try:
        parameter.hide = True
    except Exception as exc:
        _diagnostic_exception(
            f"{parameter_name} hide repair failed",
            exc,
        )
    try:
        parameter.hide_property = True
    except Exception as exc:
        _diagnostic_exception(
            f"{parameter_name} hide-property repair failed",
            exc,
        )
    try:
        current_ui = (
            getattr(parameter, "ui_options", None)
            or getattr(parameter, "_ui_options", None)
            or {}
        )
        if not isinstance(current_ui, dict):
            current_ui = {}
        current_ui.update(
            {
                "display_name": "",
                "compact": True,
                "height": 1,
                "min_height": 0,
                "max_height": 1,
                "is_full_width": True,
                "expandable": False,
                "hide": True,
                "hide_property": True,
                "hide_label": True,
                "hide_handles": True,
            }
        )
        parameter.ui_options = current_ui
    except Exception as exc:
        _diagnostic_exception(
            f"{parameter_name} UI repair failed",
            exc,
        )


def _add_output(node: Any) -> None:
    if parameter_exists(node, OUTPUT_PARAMETER):
        _repair_output_port(node, OUTPUT_PARAMETER, OUTPUT_DISPLAY_NAME)
        return
    kwargs: Dict[str, Any] = {
        "name": OUTPUT_PARAMETER,
        "tooltip": (
            "ASSET_OUT optionally shares selected images and available project, name, "
            "order, and taxonomy metadata with any downstream node. A verified "
            "registration is immutable in this library. HMBPromptLibrary may still "
            "select an effective per-shot Look Sub Type where its own taxonomy permits "
            "it, without making Prompt a prerequisite."
        ),
        "default_value": "",
        "type": "str",
        "output_type": "str",
        "input_types": [],
        "allow_input": False,
        "allow_output": True,
        "allow_property": False,
        "hide_property": True,
        "settable": False,
        "ui_options": {
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "is_full_width": True,
            "expandable": False,
            "hide": True,
            "hide_property": True,
            "hide_label": True,
            "hide_handles": True,
        },
    }
    modes = _mode_set("OUTPUT")
    if modes is not None:
        kwargs["allowed_modes"] = modes
    try:
        _safe_add_parameter(node, **kwargs)
    finally:
        _repair_output_port(node, OUTPUT_PARAMETER, OUTPUT_DISPLAY_NAME)


def _add_media_output(node: Any) -> None:
    if parameter_exists(node, MEDIA_OUTPUT_PARAMETER):
        _repair_output_port(
            node,
            MEDIA_OUTPUT_PARAMETER,
            MEDIA_OUTPUT_DISPLAY_NAME,
        )
        return
    kwargs: Dict[str, Any] = {
        "name": MEDIA_OUTPUT_PARAMETER,
        "tooltip": (
            "Ordered selected image media list. Connect this output to a "
            "generator multi-image input; its order exactly matches "
            "ordered_images in IMAGE_ASSET_OUT and Prompt @image1 through "
            "@image50."
        ),
        "default_value": [],
        "type": "list[str]",
        "output_type": "list[str]",
        "input_types": [],
        "allow_input": False,
        "allow_output": True,
        "allow_property": False,
        "hide_property": True,
        "settable": False,
        "ui_options": {
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "is_full_width": True,
            "expandable": False,
            "hide": True,
            "hide_property": True,
            "hide_label": True,
            "hide_handles": True,
        },
    }
    modes = _mode_set("OUTPUT")
    if modes is not None:
        kwargs["allowed_modes"] = modes
    try:
        _safe_add_parameter(node, **kwargs)
    finally:
        _repair_output_port(
            node,
            MEDIA_OUTPUT_PARAMETER,
            MEDIA_OUTPUT_DISPLAY_NAME,
        )


def _add_shot_asset_output(node: Any) -> None:
    """Add the tiny dependency token used by cable-free Shot routing.

    The token is deliberately not a second metadata payload.  Prompt resolves
    the exact registered source node behind this edge and reads one private,
    atomically paired metadata/media snapshot from it.
    """

    if parameter_exists(node, SHOT_ASSET_OUTPUT_PARAMETER):
        parameter = _get_parameter_obj(node, SHOT_ASSET_OUTPUT_PARAMETER)
    else:
        kwargs: Dict[str, Any] = {
            "name": SHOT_ASSET_OUTPUT_PARAMETER,
            "tooltip": "Hidden compact Shot dependency token; no media is stored here.",
            "default_value": "",
            "type": "str",
            "output_type": "str",
            "input_types": [],
            "allow_input": False,
            "allow_output": True,
            "allow_property": False,
            "hide_property": True,
            "settable": False,
            "ui_options": {
                "display_name": "",
                "hide": True,
                "hide_property": True,
                "hide_label": True,
                "hide_handles": True,
                "height": 1,
                "min_height": 0,
                "max_height": 1,
                "compact": True,
                "is_full_width": True,
                "expandable": False,
            },
        }
        modes = _mode_set("OUTPUT")
        if modes is not None:
            kwargs["allowed_modes"] = modes
        _safe_add_parameter(node, **kwargs)
        parameter = _get_parameter_obj(node, SHOT_ASSET_OUTPUT_PARAMETER)
    if parameter is None:
        return
    try:
        parameter.hide = True
        parameter.hide_property = True
        options = dict(getattr(parameter, "ui_options", {}) or {})
        options.update(
            {
                "display_name": "",
                "hide": True,
                "hide_property": True,
                "hide_label": True,
                "hide_handles": True,
                "height": 1,
                "min_height": 0,
                "max_height": 1,
                "compact": True,
                "is_full_width": True,
                "expandable": False,
            }
        )
        parameter.ui_options = options
    except Exception:
        pass


def _add_image_import_input(node: Any) -> None:
    if parameter_exists(node, IMAGE_IMPORT_PARAMETER):
        return
    tooltip = (
        "Optional external images appended to IMAGE_OUT with their readable content "
        "and available name/order metadata. Project verification fields remain "
        "unspecified until registered, but their absence never restricts creative use. "
        "Accepts ImageArtifact, ImageUrlArtifact, local paths, and image lists. "
        f"At most {MAX_SELECTED_IMAGES} images are published."
    )
    modes = _mode_set("INPUT")
    if ParameterList is not None:
        kwargs: Dict[str, Any] = {
            "name": IMAGE_IMPORT_PARAMETER,
            "input_types": [
                "ImageUrlArtifact",
                "ImageArtifact",
                "str",
            ],
            "default_value": [],
            "tooltip": tooltip,
            "max_items": MAX_SELECTED_IMAGES,
            "collapsed": True,
            "grid": False,
            "ui_options": {
                "display_name": "IMAGE_IMPORT_IN",
                "expander": True,
                "collapsed": True,
                "hide_property": True,
            },
        }
        if modes is not None:
            kwargs["allowed_modes"] = modes
        try:
            node.add_parameter(ParameterList(**kwargs))
            return
        except Exception as exc:
            _diagnostic_exception("IMAGE_IMPORT_IN ParameterList setup failed", exc)
    kwargs = {
        "name": IMAGE_IMPORT_PARAMETER,
        "default_value": [],
        "type": "list",
        "input_types": [
            "ImageUrlArtifact",
            "ImageArtifact",
            "str",
            "list",
        ],
        "allow_input": True,
        "allow_output": False,
        "allow_property": False,
        "tooltip": tooltip,
        "ui_options": {
            "display_name": "IMAGE_IMPORT_IN",
            "compact": True,
            "hide_property": True,
        },
    }
    if modes is not None:
        kwargs["allowed_modes"] = modes
    _safe_add_parameter(node, **kwargs)


def _add_project_root(node: Any) -> None:
    if parameter_exists(node, PROJECT_ROOT_PARAMETER):
        return
    tooltip = (
        "Select a projects catalog. Each direct child "
        "folder is one project; a direct project folder is also accepted. Optional "
        "hmb_image_assets.json records may override inferred Asset ID, Image "
        "Name, Main Type, registered Sub Type, and default selection. Registered "
        "records are read-only; only unregistered project media can use Add."
    )
    trait = None
    if FileSystemPicker is not None:
        for trait_kwargs in (
            {
                "allow_files": False,
                "allow_directories": True,
                "multiple": False,
            },
            {"allow_directories": True},
        ):
            try:
                trait = FileSystemPicker(**trait_kwargs)
                break
            except Exception:
                continue
    if ParameterString is not None:
        parameter = ParameterString(
            name=PROJECT_ROOT_PARAMETER,
            default_value=str(DEFAULT_PROJECTS_ROOT),
            tooltip=tooltip,
            placeholder_text=str(DEFAULT_PROJECTS_ROOT),
        )
        if trait is not None:
            try:
                parameter.add_trait(trait)
            except Exception:
                pass
        try:
            parameter.allowed_modes = _mode_set("PROPERTY")
        except Exception:
            pass
        try:
            options = dict(getattr(parameter, "ui_options", {}) or {})
            options.update(
                {
                    "display_name": "PROJECT_ROOT",
                    "placeholder_text": str(DEFAULT_PROJECTS_ROOT),
                    "is_full_width": True,
                }
            )
            parameter.ui_options = options
        except Exception:
            pass
        node.add_parameter(parameter)
        return
    kwargs: Dict[str, Any] = {
        "name": PROJECT_ROOT_PARAMETER,
        "default_value": str(DEFAULT_PROJECTS_ROOT),
        "type": "str",
        "tooltip": tooltip,
        "allow_input": False,
        "allow_output": False,
        "allow_property": True,
        "ui_options": {
            "display_name": "PROJECT_ROOT",
            "placeholder_text": str(DEFAULT_PROJECTS_ROOT),
            "is_full_width": True,
        },
    }
    modes = _mode_set("PROPERTY")
    if modes is not None:
        kwargs["allowed_modes"] = modes
        kwargs["allow_input"] = False
    if trait is not None:
        kwargs["traits"] = {trait}
    _safe_add_parameter(node, **kwargs)


def _add_widget_state(node: Any) -> None:
    if parameter_exists(node, WIDGET_STATE_PARAMETER):
        return
    kwargs: Dict[str, Any] = {
        "name": WIDGET_STATE_PARAMETER,
        "default_value": _json_text(_default_state()),
        "type": "str",
        "input_types": [],
        "allow_input": False,
        "allow_output": False,
        "allow_property": True,
        "ui_options": {
            "display_name": "HMBImageAssetLibrary",
            "is_full_width": True,
            "height": ASSET_NODE_HEIGHT,
            "min_height": 560,
            "width": ASSET_NODE_WIDTH,
            "min_width": 760,
            "resizable": True,
        },
    }
    modes = _mode_set("PROPERTY")
    if modes is not None:
        kwargs["allowed_modes"] = modes
    parameter = None
    last: Exception | None = None
    for attempt in _parameter_attempts(kwargs):
        if Widget is not None:
            try:
                parameter = Parameter(
                    **{
                        **attempt,
                        "traits": {
                            Widget(
                                name=WIDGET_NAME,
                                library=WIDGET_LIBRARY_NAME,
                            )
                        },
                    }
                )
                break
            except Exception as exc:
                last = exc
        try:
            parameter = Parameter(**attempt)
            break
        except Exception as exc:
            last = exc
    if parameter is None:
        raise last or RuntimeError("Unable to add HMB image asset widget state.")
    if Widget is not None:
        try:
            find = getattr(parameter, "find_elements_by_type", None)
            existing = list(find(Widget, True)) if callable(find) else []
            if not existing:
                parameter.add_trait(
                    Widget(name=WIDGET_NAME, library=WIDGET_LIBRARY_NAME)
                )
        except Exception:
            pass
    node.add_parameter(parameter)


def _add_thumbnail_patch_bridge(node: Any) -> None:
    runtime_id = ""
    try:
        runtime_id = _normalize_state(
            _get_parameter_raw(node, WIDGET_STATE_PARAMETER)
        )["shot_routing"]["publisher_instance_uuid"]
    except Exception:
        runtime_id = ""
    if parameter_exists(node, THUMBNAIL_PATCH_PARAMETER):
        parameter = _get_parameter_obj(node, THUMBNAIL_PATCH_PARAMETER)
    else:
        kwargs: Dict[str, Any] = {
            "name": THUMBNAIL_PATCH_PARAMETER,
            "default_value": _default_thumbnail_bridge(runtime_id),
            "type": "dict",
            "input_types": ["dict"],
            "allow_input": False,
            "allow_output": False,
            "allow_property": True,
            "settable": True,
            "ui_options": {
                "display_name": "",
                "is_full_width": True,
                "height": 0,
                "min_height": 0,
                "max_height": 0,
                "expandable": False,
                "compact": True,
                "resizable": False,
                "hide_label": True,
                "hide_handles": True,
                "hide": True,
                # The row is invisible, but the property must stay mounted so
                # the dedicated bridge widget can exchange compact patches.
                "hide_property": False,
            },
        }
        modes = _mode_set("PROPERTY")
        if modes is not None:
            kwargs["allowed_modes"] = modes
        parameter = None
        last: Exception | None = None
        for attempt in _parameter_attempts(kwargs):
            try:
                parameter = Parameter(**attempt)
                break
            except Exception as exc:
                last = exc
        if parameter is None:
            raise last or RuntimeError(
                "Unable to add HMB image thumbnail patch bridge."
            )
        if Widget is not None:
            try:
                parameter.add_trait(
                    Widget(
                        name=THUMBNAIL_BRIDGE_WIDGET_NAME,
                        library=WIDGET_LIBRARY_NAME,
                    )
                )
            except Exception:
                pass
        node.add_parameter(parameter)
    for attribute, setting in (
        ("type", "dict"),
        ("input_types", ["dict"]),
        ("settable", True),
        ("hide", True),
        ("hide_property", False),
        ("serializable", True),
    ):
        try:
            setattr(parameter, attribute, setting)
        except Exception:
            pass
    if Widget is not None:
        try:
            finder = getattr(parameter, "find_elements_by_type", None)
            existing = list(finder(Widget, True)) if callable(finder) else []
            if not existing:
                parameter.add_trait(
                    Widget(
                        name=THUMBNAIL_BRIDGE_WIDGET_NAME,
                        library=WIDGET_LIBRARY_NAME,
                    )
                )
        except Exception:
            pass
    try:
        options = dict(getattr(parameter, "ui_options", {}) or {})
        options.update(
            {
                "display_name": "",
                "height": 0,
                "min_height": 0,
                "max_height": 0,
                "expandable": False,
                "compact": True,
                "resizable": False,
                "hide_label": True,
                "hide_handles": True,
                "hide": True,
                "hide_property": False,
            }
        )
        parameter.ui_options = options
    except Exception:
        pass


def _image_output_side_effect_local(node: Any) -> Any:
    local = getattr(node, "_hmb_output_side_effect_local", None)
    if local is None:
        local = threading.local()
        setattr(node, "_hmb_output_side_effect_local", local)
    return local


def _is_image_output_side_effect_callback(node: Any) -> bool:
    return int(
        getattr(_image_output_side_effect_local(node), "depth", 0) or 0
    ) > 0


def _begin_image_output_side_effect_callback(node: Any) -> None:
    local = _image_output_side_effect_local(node)
    local.depth = int(getattr(local, "depth", 0) or 0) + 1


def _end_image_output_side_effect_callback(node: Any) -> None:
    local = _image_output_side_effect_local(node)
    local.depth = max(0, int(getattr(local, "depth", 0) or 0) - 1)


def _propagate_image_output_to_connections(
    node: Any,
    name: str,
    value: Any,
    *,
    owner_pending: Any = None,
) -> None:
    """Forward one late compact output through real retained-mode edges."""

    def still_owned() -> bool:
        if owner_pending is None:
            return True
        pending = getattr(node, "_hmb_pending_output_notifications", None)
        return isinstance(pending, dict) and pending.get(name) is owner_pending

    try:
        from griptape_nodes.retained_mode.events.connection_events import (  # type: ignore
            ListConnectionsForNodeRequest,
            ListConnectionsForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.events.parameter_events import (  # type: ignore
            SetParameterValueRequest,
            SetParameterValueResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import (  # type: ignore
            GriptapeNodes,
        )
    except Exception:
        return

    node_name = _clean(getattr(node, "name", ""))
    if not node_name or not still_owned():
        return
    try:
        registered = GriptapeNodes.NodeManager().get_node_by_name(node_name)
    except Exception:
        return
    if registered is not node or not still_owned():
        return
    result = GriptapeNodes.handle_request(
        ListConnectionsForNodeRequest(
            node_name=node_name,
            broadcast_result=False,
            failure_log_level=logging.DEBUG,
        )
    )
    if not isinstance(result, ListConnectionsForNodeResultSuccess):
        details = _clean(getattr(result, "result_details", ""))
        raise RuntimeError(
            details or f"Griptape could not inspect outgoing {name} connections."
        )
    source_parameter = _get_parameter_obj(node, name)
    data_type = _clean(getattr(source_parameter, "output_type", "")) or _clean(
        getattr(source_parameter, "type", "")
    )
    for connection in result.outgoing_connections:
        if not still_owned():
            return
        if _clean(getattr(connection, "source_parameter_name", "")) != name:
            continue
        target_node_name = _clean(getattr(connection, "target_node_name", ""))
        target_parameter_name = _clean(
            getattr(connection, "target_parameter_name", "")
        )
        if not target_node_name or not target_parameter_name:
            continue
        try:
            target_node = GriptapeNodes.NodeManager().get_node_by_name(
                target_node_name
            )
        except Exception:
            target_node = None
        if bool(getattr(target_node, "lock", False)):
            continue
        set_result = GriptapeNodes.handle_request(
            SetParameterValueRequest(
                node_name=target_node_name,
                parameter_name=target_parameter_name,
                value=value,
                data_type=data_type or None,
                incoming_connection_source_node_name=node_name,
                incoming_connection_source_parameter_name=name,
            )
        )
        if not still_owned():
            return
        if not isinstance(set_result, SetParameterValueResultSuccess):
            details = _clean(getattr(set_result, "result_details", ""))
            raise RuntimeError(
                details
                or (
                    f"Griptape rejected {node_name}.{name} propagation to "
                    f"{target_node_name}.{target_parameter_name}."
                )
            )


def _stage_and_notify_image_output_pair(
    node: Any,
    asset_output: Any,
    media_output: Any,
    shot_asset_output: Any | None = None,
    *,
    stage_outputs: bool = True,
    replace_pending: bool = True,
) -> None:
    """Stage both sibling caches, then independently notify live connections."""
    output_values = getattr(node, "parameter_output_values", None)
    synchronized_outputs: tuple[tuple[str, Any], ...] = (
        (OUTPUT_PARAMETER, asset_output),
        (MEDIA_OUTPUT_PARAMETER, media_output),
    )
    current_shot_output = (
        output_values.get(SHOT_ASSET_OUTPUT_PARAMETER)
        if isinstance(output_values, dict)
        else getattr(node, SHOT_ASSET_OUTPUT_PARAMETER, None)
    )
    shot_output_changed = bool(
        shot_asset_output is not None
        and current_shot_output != shot_asset_output
    )
    if shot_output_changed:
        synchronized_outputs += ((SHOT_ASSET_OUTPUT_PARAMETER, shot_asset_output),)
    # A synchronous subscriber to the first notification can read the sibling
    # port immediately, so both retained-mode caches must already be current.
    if stage_outputs:
        staged_outputs = synchronized_outputs
        if shot_asset_output is not None and not shot_output_changed:
            staged_outputs += ((SHOT_ASSET_OUTPUT_PARAMETER, shot_asset_output),)
        for name, value in staged_outputs:
            set_output(node, name, value)

    if replace_pending:
        generation = (
            int(getattr(node, "_hmb_output_notification_generation", 0)) + 1
        )
        node._hmb_output_notification_generation = generation
        node._hmb_pending_output_notifications = {
            name: (generation, value)
            for name, value in synchronized_outputs
        }

    publisher = getattr(node, "publish_update_to_parameter", None)
    if not callable(publisher):
        node._hmb_pending_output_notifications = {}
        return
    pending = getattr(node, "_hmb_pending_output_notifications", {})
    if not isinstance(pending, dict) or not pending:
        return
    notification_errors: List[tuple[str, Exception]] = []
    for name, pending_item in list(pending.items()):
        if (
            not isinstance(pending_item, tuple)
            or len(pending_item) != 2
        ):
            continue
        owner_generation, value = pending_item
        current_pending = getattr(
            node,
            "_hmb_pending_output_notifications",
            {},
        )
        current_item = (
            current_pending.get(name)
            if isinstance(current_pending, dict)
            else None
        )
        if (
            not isinstance(current_item, tuple)
            or len(current_item) != 2
            or current_item[0] != owner_generation
            or current_item is not pending_item
        ):
            continue
        try:
            publisher(name, value)
        except Exception as error:
            current_pending = getattr(
                node,
                "_hmb_pending_output_notifications",
                {},
            )
            current_item = (
                current_pending.get(name)
                if isinstance(current_pending, dict)
                else None
            )
            if (
                isinstance(current_item, tuple)
                and len(current_item) == 2
                and current_item[0] == owner_generation
                and current_item is pending_item
            ):
                notification_errors.append((name, error))
        else:
            current_pending = getattr(
                node,
                "_hmb_pending_output_notifications",
                {},
            )
            current_item = (
                current_pending.get(name)
                if isinstance(current_pending, dict)
                else None
            )
            if (
                isinstance(current_item, tuple)
                and len(current_item) == 2
                and current_item[0] == owner_generation
                and current_item is pending_item
            ):
                try:
                    if (
                        name == SHOT_ASSET_OUTPUT_PARAMETER
                        and not _is_image_output_side_effect_callback(node)
                    ):
                        _propagate_image_output_to_connections(
                            node,
                            name,
                            value,
                            owner_pending=pending_item,
                        )
                except Exception as error:
                    current_pending = getattr(
                        node,
                        "_hmb_pending_output_notifications",
                        {},
                    )
                    if (
                        isinstance(current_pending, dict)
                        and current_pending.get(name) is pending_item
                    ):
                        notification_errors.append((f"{name} graph", error))
                else:
                    current_pending = getattr(
                        node,
                        "_hmb_pending_output_notifications",
                        {},
                    )
                    if (
                        isinstance(current_pending, dict)
                        and current_pending.get(name) is pending_item
                    ):
                        current_pending.pop(name, None)
    if notification_errors:
        failed_ports = ", ".join(
            f"{name} ({type(error).__name__})"
            for name, error in notification_errors
        )
        raise RuntimeError(
            "Synchronized image output notification failed after both output "
            f"caches were staged: {failed_ports}."
        ) from notification_errors[0][1]


class HMBImageAssetLibrary(DataNode):
    """Independent project image library and optional metadata source.

    The node owns project discovery plus the selected images and their available
    Asset ID / Image Name / taxonomy metadata. All readable image content and
    user metadata remain directly usable under the current goal. ASSET_OUT may
    optionally share them with a downstream Prompt. A verified registered Sub
    Type remains bound there while Target and Color Pick stay freely editable.
    """

    def __init__(self, **kwargs: Any):
        # Widget callbacks can be delivered after a later click has already
        # committed. Keep the latest canonical local transaction so an older
        # callback cannot roll back selection/filter/dropdown state.
        self._hmb_last_accepted_widget_state: str | None = None
        self._hmb_last_accepted_widget_revisions = (0, 0)
        self._hmb_last_accepted_thumbnail_revision = 0
        self._hmb_restoring_widget_state = False
        serialized_metadata = kwargs.get("metadata")
        restored_size = (
            dict(serialized_metadata.get("size") or {})
            if isinstance(serialized_metadata, dict)
            and isinstance(serialized_metadata.get("size"), dict)
            else {}
        )
        super().__init__(**kwargs)
        if restored_size:
            current_metadata = dict(getattr(self, "metadata", {}) or {})
            current_metadata["size"] = restored_size
            self.metadata = current_metadata
        self.category = "HMB_GP_Production"
        self.description = (
            "Independent project image asset tree with optional Main Type/Sub Type "
            "metadata and additive downstream binding output."
        )
        self._hmb_state_syncing = False
        self._hmb_thumbnail_bridge_syncing = False
        self._hmb_root_syncing = False
        self._hmb_refresh_revision = 0
        self._hmb_manifest_poll_received = False
        self._hmb_manifest_poll_pending = False
        self._hmb_last_manifest_poll_nonce = ""
        self._hmb_last_manifest_poll_error = ""
        self._hmb_scan_lock = threading.RLock()
        self._hmb_scan_generation = 0
        self._hmb_scan_pending_key = ""
        self._hmb_scan_thread: threading.Thread | None = None
        self._hmb_scan_pending_result: tuple[int, str, str, Dict[str, Any]] | None = None
        self._hmb_thumbnail_lock = threading.RLock()
        self._hmb_thumbnail_generation = 0
        self._hmb_thumbnail_pending_key = ""
        self._hmb_thumbnail_thread: threading.Thread | None = None
        self._hmb_thumbnail_pending_result: tuple[
            int,
            str,
            Dict[str, Any],
        ] | None = None
        self._hmb_catalog_probe_lock = threading.RLock()
        self._hmb_catalog_probe_generation = 0
        self._hmb_catalog_probe_pending_key = ""
        self._hmb_catalog_probe_thread: threading.Thread | None = None
        self._hmb_catalog_probe_pending_result: tuple[
            int,
            str,
            Dict[str, Any],
        ] | None = None
        self._hmb_catalog_probe_last_manifest_at = 0.0
        self._hmb_catalog_probe_last_folder_at = 0.0
        self._hmb_catalog_probe_pending_folder_signature = ""
        self._hmb_catalog_probe_pending_folder_since = 0.0
        self._hmb_node_deleted = False
        self._hmb_initial_catalog_scan_pending = True
        # A newly registered ImageAsset may appear after Prompt. Its first
        # exact catalog result must advertise once, but a subsequently hydrated
        # saved workflow must never let this constructor-default scan win.
        self._hmb_fresh_registration_scan_key = ""
        self._hmb_initial_catalog_root = str(DEFAULT_PROJECTS_ROOT)
        # Constructor/default catalog scans are not serialized workflow
        # authority. The host initial_setup lifecycle or an explicit user
        # action adopts the aggregate before any whole-flow reconciliation.
        self._hmb_hydration_adopted = False
        try:
            # Griptape's outer React Flow node reads its first-render size from
            # metadata["size"].  Only fill a missing size so a restored node's
            # user-resized dimensions remain authoritative.
            metadata = dict(getattr(self, "metadata", {}) or {})
            saved_size = metadata.get("size")
            try:
                has_saved_size = (
                    isinstance(saved_size, dict)
                    and float(saved_size.get("width") or 0) > 0
                    and float(saved_size.get("height") or 0) > 0
                )
            except (TypeError, ValueError):
                has_saved_size = False
            initial_size_setter = getattr(self, "set_initial_node_size", None)
            if not has_saved_size and callable(initial_size_setter):
                initial_size_setter(width=ASSET_NODE_WIDTH, height=ASSET_NODE_HEIGHT)
            elif not has_saved_size:
                metadata.setdefault(
                    "size",
                    {"width": ASSET_NODE_WIDTH, "height": ASSET_NODE_HEIGHT},
                )
                self.metadata = metadata
            self.ui_options = {
                "width": ASSET_NODE_WIDTH,
                "height": ASSET_NODE_HEIGHT,
                "default_width": ASSET_NODE_WIDTH,
                "default_height": ASSET_NODE_HEIGHT,
                "preferred_width": ASSET_NODE_WIDTH,
                "preferred_height": ASSET_NODE_HEIGHT,
                "initial_width": ASSET_NODE_WIDTH,
                "initial_height": ASSET_NODE_HEIGHT,
                "min_width": 760,
                "min_height": 560,
                "resizable": True,
            }
            self.width = saved_size.get("width") if has_saved_size else ASSET_NODE_WIDTH
            self.height = saved_size.get("height") if has_saved_size else ASSET_NODE_HEIGHT
        except Exception as exc:
            _diagnostic_exception("Image asset node UI sizing failed", exc)

        self._hmb_import_media_by_uid: Dict[str, Any] = {}
        self._hmb_import_revision = 0
        self._hmb_import_media_identity = _import_media_map_identity({})
        self._hmb_last_applied_import_identity = _canonical_import_input_identity(None)
        self._hmb_resolution_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hmb_resolution_cache_identity = ""
        self._hmb_last_resolution_warning = ""
        self._hmb_last_output_fingerprint = ""
        self._hmb_last_output_pair: tuple[Any, Any] | None = None
        self._hmb_output_notification_generation = 0
        self._hmb_pending_output_notifications: Dict[str, tuple[int, Any]] = {}
        self._hmb_output_side_effect_local = threading.local()
        self._hmb_shot_routing_cache: Dict[str, Any] | None = None
        self._hmb_shot_routing_input_identity = ""
        self._hmb_shot_routing_identity = ""
        self._hmb_shot_routing_generation = 0
        self._hmb_last_reconciled_shot_catalog_identity = ""
        self._hmb_reserved_shot_catalog_identity = ""
        self._ensure_parameters()
        self._accept_widget_state_baseline(
            _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        )
        root_value = _project_root_text(
            _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
        )
        # The constructor is a retained-mode/UI callback and may run while the
        # default catalog points at an unavailable UNC share.  Keep the
        # parameter's already-normalized snapshot paintable immediately; exact
        # registration below owns the first filesystem discovery generation.
        self._hmb_initial_catalog_root = root_value or str(DEFAULT_PROJECTS_ROOT)
        scheduler = getattr(
            _hmb_shot_routing, "schedule_post_registration_reconcile", None
        )
        if callable(scheduler):
            scheduler(self)

    def _ensure_parameters(self) -> None:
        _add_output(self)
        _add_media_output(self)
        _add_shot_asset_output(self)
        _add_image_import_input(self)
        _add_project_root(self)
        _add_widget_state(self)
        _add_thumbnail_patch_bridge(self)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Adopt serialized hydration as a fresh instance-local baseline."""

        parent_setter = getattr(super(), "set_parameter_value")
        if (
            ParameterMode is None
            and param_name == WIDGET_STATE_PARAMETER
            and not emit_change
            and skip_before_value_set
        ):
            values = getattr(self, "parameter_values", None)
            if isinstance(values, dict):
                values[WIDGET_STATE_PARAMETER] = value
            parameter = _get_parameter_obj(self, WIDGET_STATE_PARAMETER)
            if parameter is not None:
                parameter.default_value = value
            return
        if initial_setup and param_name in {
            WIDGET_STATE_PARAMETER,
            PROJECT_ROOT_PARAMETER,
            IMAGE_IMPORT_PARAMETER,
            THUMBNAIL_PATCH_PARAMETER,
        }:
            self._hmb_fresh_registration_scan_key = ""
        if initial_setup and param_name == WIDGET_STATE_PARAMETER:
            self._accept_widget_state_baseline(value)
        if (
            ParameterMode is None
            and param_name in {WIDGET_STATE_PARAMETER, THUMBNAIL_PATCH_PARAMETER}
            and not initial_setup
        ):
            if param_name == WIDGET_STATE_PARAMETER and not self._hmb_state_syncing and not getattr(
                self, "_hmb_restoring_widget_state", False
            ):
                self._hmb_hydration_adopted = True
            parameter = _get_parameter_obj(self, param_name)
            final_value = (
                value
                if skip_before_value_set
                else self.before_value_set(parameter, value)
            )
            parent_setter(param_name, final_value)
            self.after_value_set(parameter, final_value)
            return
        if ParameterMode is None:
            parent_setter(param_name, value)
            if initial_setup and param_name == WIDGET_STATE_PARAMETER:
                self._hmb_hydration_adopted = True
                self._schedule_post_hydration_shot_reconcile()
            return
        parent_setter(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )
        if initial_setup and param_name == WIDGET_STATE_PARAMETER:
            self._hmb_hydration_adopted = True
            self._schedule_post_hydration_shot_reconcile()

    def _schedule_post_hydration_shot_reconcile(self) -> bool:
        """Re-advertise the restored Shot catalog after host hydration."""

        if not bool(getattr(self, "_hmb_hydration_adopted", False)):
            return False
        identity = _shot_routing_catalog_identity(
            self._current_state()
        )
        self._reconcile_hmb_shot_routing(identity)
        return bool(
            identity
            and (
                _clean(
                    getattr(
                        self,
                        "_hmb_reserved_shot_catalog_identity",
                        "",
                    )
                ) == identity
                or _clean(
                    getattr(
                        self,
                        "_hmb_last_reconciled_shot_catalog_identity",
                        "",
                    )
                ) == identity
            )
        )

    def _hmb_post_registration_shot_discovery(self) -> None:
        """Start the first catalog scan only after exact host registration.

        Constructor state is the immutable last-known snapshot.  Registration
        may race workflow hydration or an explicit root edit, so any newer scan
        generation remains authoritative and suppresses this default request.
        """

        self._ensure_scan_runtime_state()
        self._ensure_thumbnail_runtime_state()
        self._ensure_catalog_probe_runtime_state()
        with self._hmb_scan_lock:
            if not bool(getattr(self, "_hmb_initial_catalog_scan_pending", False)):
                return
            self._hmb_initial_catalog_scan_pending = False
            if self._hmb_scan_pending_key or bool(
                getattr(self, "_hmb_node_deleted", False)
            ):
                return
            registration_generation = self._hmb_scan_generation

        snapshot = self._current_state()
        requested_root = (
            _project_root_text(snapshot.get("catalog_root"))
            or _project_root_text(
                _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
            )
            or _project_root_text(
                getattr(self, "_hmb_initial_catalog_root", "")
            )
            or str(DEFAULT_PROJECTS_ROOT)
        ).replace("\\", "/")
        candidate = dict(snapshot)
        candidate["catalog_root"] = requested_root
        candidate["error"] = ""
        captured_import_value = _get_parameter_raw(
            self,
            IMAGE_IMPORT_PARAMETER,
        )
        request_key = f"initial:{requested_root.casefold()}"
        with self._hmb_scan_lock:
            # Snapshot/root resolution happens outside the lock. An explicit
            # root edit or hydrated workflow can complete its own scan during
            # that interval, including quickly enough to leave no pending key.
            # Generation is therefore the authority, not pending-key presence
            # alone. Keep the final reservation and schedule atomic under the
            # RLock so the constructor-default scan can never supersede newer
            # user or hydration state.
            if (
                registration_generation != self._hmb_scan_generation
                or self._hmb_scan_pending_key
                or bool(getattr(self, "_hmb_node_deleted", False))
            ):
                return
            self._hmb_fresh_registration_scan_key = request_key
            self._schedule_catalog_scan(
                request_key,
                candidate,
                lambda: self._merge_captured_imports_into_scan(
                    _load_project_catalog(requested_root, snapshot),
                    captured_import_value,
                ),
                failure_state=snapshot,
            )

    def _current_state(self) -> Dict[str, Any]:
        return _normalize_state(
            _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        )

    def _cache_shot_routing_snapshot(
        self,
        state: Dict[str, Any],
        *,
        force: bool = False,
        normalized: bool = False,
    ) -> Dict[str, Any]:
        import_media = getattr(self, "_hmb_import_media_by_uid", {})
        if not isinstance(import_media, dict):
            import_media = {}
        resolution_cache = getattr(self, "_hmb_resolution_cache", None)
        if not isinstance(resolution_cache, OrderedDict):
            resolution_cache = OrderedDict()
            self._hmb_resolution_cache = resolution_cache
        import_revision = _non_negative_int(
            getattr(self, "_hmb_import_revision", 0)
        )
        normalized_state = state if normalized else _normalize_state(state)
        routing = normalized_state["shot_routing"]
        routing_contract = {
            "publisher_instance_uuid": routing["publisher_instance_uuid"],
            "channel_uuid": routing["channel_uuid"],
            "shots": [
                {
                    "shot_uuid": shot["shot_uuid"],
                    "number": shot["number"],
                    "name": shot["name"],
                    "revision": shot["revision"],
                    "selected_source_uids": list(shot["selected_source_uids"]),
                }
                for shot in routing["shots"]
            ],
        }
        input_identity = _sha256_canonical(
            {
                "routing": routing_contract,
                "selected_assets": _project_output_fingerprint(
                    normalized_state,
                    import_media,
                    import_revision,
                ),
            }
        )
        cached_snapshot = getattr(self, "_hmb_shot_routing_cache", None)
        if (
            not force
            and input_identity
            and input_identity
            == getattr(self, "_hmb_shot_routing_input_identity", "")
            and isinstance(cached_snapshot, dict)
        ):
            _apply_shot_routing_state_facts(state, cached_snapshot)
            return cached_snapshot
        probe = _build_shot_routing_snapshot(
            normalized_state,
            import_media,
            resolution_cache=resolution_cache,
            import_revision=import_revision,
            generation=1,
            normalized=True,
        )
        media_descriptors = _shot_media_descriptors(
            [item["source_uid"] for item in probe["ordered_assets"]],
            probe["media_by_source_uid"],
        )
        identity = _sha256_canonical(
            {
                "publisher_instance_uuid": probe["publisher_instance_uuid"],
                "channel_uuid": probe["channel_uuid"],
                "shots": probe["shots"],
                "ordered_assets": probe["ordered_assets"],
                "media_descriptors": media_descriptors,
            }
        )
        configured_generation = _non_negative_int(
            normalized_state["shot_routing"].get("generation")
        )
        previous_generation = _non_negative_int(
            getattr(self, "_hmb_shot_routing_generation", 0)
        )
        previous_identity = _clean(
            getattr(self, "_hmb_shot_routing_identity", "")
        )
        if previous_identity and identity != previous_identity:
            generation = max(1, configured_generation, previous_generation + 1)
        else:
            generation = max(1, configured_generation, previous_generation)
        snapshot = _build_shot_routing_snapshot(
            normalized_state,
            import_media,
            resolution_cache=resolution_cache,
            import_revision=import_revision,
            generation=generation,
            normalized=True,
        )
        self._hmb_shot_routing_identity = identity
        self._hmb_shot_routing_input_identity = input_identity
        self._hmb_shot_routing_generation = generation
        self._hmb_shot_routing_cache = snapshot
        _apply_shot_routing_state_facts(state, snapshot)
        return snapshot

    @staticmethod
    def _shot_asset_dependency_token(snapshot: Dict[str, Any]) -> str:
        """Return one bounded routing identity with no source or media data."""

        return _json_text(
            {
                "schema": "hmb-shot-asset-dependency",
                "version": 1,
                "publisher_instance_uuid": _clean(
                    snapshot.get("publisher_instance_uuid")
                ),
                "channel_uuid": _clean(snapshot.get("channel_uuid")),
                "generation": _non_negative_int(snapshot.get("generation")),
                "metadata_sha256": _clean(snapshot.get("metadata_sha256")),
                "media_sha256": _clean(snapshot.get("media_sha256")),
                "shot_count": len(snapshot.get("shots") or []),
            }
        )

    def _hmb_shot_routing_snapshot(
        self,
        expected_channel_uuid: str = "",
    ) -> Dict[str, Any]:
        """Return a private atomic shot metadata/media snapshot."""
        snapshot = self._cache_shot_routing_snapshot(self._current_state())
        expected = _clean(expected_channel_uuid)
        if expected and expected != snapshot["channel_uuid"]:
            raise ValueError(
                "HMB shot routing channel mismatch: expected "
                f"{expected!r}, publisher has {snapshot['channel_uuid']!r}."
            )
        return {
            "schema": snapshot["schema"],
            "version": snapshot["version"],
            "publisher_instance_uuid": snapshot["publisher_instance_uuid"],
            "channel_uuid": snapshot["channel_uuid"],
            "generation": snapshot["generation"],
            "metadata_sha256": snapshot["metadata_sha256"],
            "media_sha256": snapshot["media_sha256"],
            "shots": [
                {
                    "shot_uuid": item["shot_uuid"],
                    "number": item["number"],
                    "name": item["name"],
                    "revision": item["revision"],
                    "selected_source_uids": list(item["selected_source_uids"]),
                }
                for item in snapshot["shots"]
            ],
            "ordered_assets": [
                {
                    "source_uid": item["source_uid"],
                    "metadata": dict(item["metadata"]),
                }
                for item in snapshot["ordered_assets"]
            ],
            "media_by_source_uid": dict(snapshot["media_by_source_uid"]),
        }

    def _hmb_shot_routing_catalog(self) -> Dict[str, Any]:
        """Return the bounded, media-free Shot catalog used by same-flow peers."""

        snapshot = self._cache_shot_routing_snapshot(self._current_state())
        shots = [
            {
                "shot_uuid": item["shot_uuid"],
                "number": item["number"],
                "name": item["name"],
                "revision": item["revision"],
            }
            for item in snapshot["shots"]
        ]
        catalog_document = {
            "channel_uuid": snapshot["channel_uuid"],
            "generation": snapshot["generation"],
            "shots": shots,
        }
        return {
            "schema": SHOT_ROUTING_CATALOG_SCHEMA,
            "version": SHOT_ROUTING_CATALOG_VERSION,
            "publisher_instance_uuid": snapshot["publisher_instance_uuid"],
            "channel_uuid": snapshot["channel_uuid"],
            "generation": snapshot["generation"],
            "metadata_sha256": _sha256_canonical(catalog_document),
            "shots": shots,
        }

    def _hmb_shot_channel_subscription(self) -> Dict[str, Any]:
        routing = self._current_state()["shot_routing"]
        active = next(
            (
                item
                for item in routing["shots"]
                if item["shot_uuid"] == routing["active_shot_uuid"]
            ),
            routing["shots"][0],
        )
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": "image_asset",
            "enabled": True,
            "channel_uuid": routing["channel_uuid"],
            "shot_uuid": active["shot_uuid"],
            "shot_number": active["number"],
            "shot_name": active["name"],
        }

    def _hmb_export_reset_handoff(self) -> Dict[str, Any]:
        """Export only durable image/Shot state for an in-flow node reset."""

        self._ensure_scan_runtime_state()
        self._ensure_thumbnail_runtime_state()
        self._ensure_catalog_probe_runtime_state()
        with self._hmb_scan_lock:
            state = _normalize_state(self._current_state())
            import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
            import_media = dict(
                getattr(self, "_hmb_import_media_by_uid", {}) or {}
            )
        try:
            import_value = copy.deepcopy(import_value)
        except Exception:
            # Artifact/media wrappers may deliberately be non-copyable. The
            # handoff is synchronous and in-process, so retaining that exact
            # immutable host value is safer than dropping the imported image.
            pass
        return {
            "schema": RESET_HANDOFF_SCHEMA,
            "version": RESET_HANDOFF_VERSION,
            "identity_contract": RESET_HANDOFF_IDENTITY_CONTRACT,
            "participant_kind": "image_asset",
            "state": state,
            "project_root": _project_root_text(state.get("catalog_root")),
            "import_value": import_value,
            "import_media_by_uid": import_media,
        }

    def _hmb_adopt_reset_handoff(self, value: Any) -> bool:
        """Adopt a predecessor's Shot images without restoring its UI/error state."""

        payload = value if isinstance(value, dict) else {}
        if (
            payload.get("schema") != RESET_HANDOFF_SCHEMA
            or payload.get("version") != RESET_HANDOFF_VERSION
            or payload.get("identity_contract")
            != RESET_HANDOFF_IDENTITY_CONTRACT
            or _clean(payload.get("participant_kind")) != "image_asset"
            or bool(getattr(self, "_hmb_node_deleted", False))
        ):
            return False
        state = _reset_image_asset_state_preserving_shot_media(
            payload.get("state")
        )
        project_root = (
            _project_root_text(payload.get("project_root"))
            or _project_root_text(state.get("catalog_root"))
            or str(DEFAULT_PROJECTS_ROOT)
        )
        import_value = payload.get("import_value")
        import_media = payload.get("import_media_by_uid")
        if not isinstance(import_media, dict):
            return False

        self._ensure_scan_runtime_state()
        self._ensure_thumbnail_runtime_state()
        self._ensure_catalog_probe_runtime_state()
        with self._hmb_scan_lock:
            self._hmb_scan_generation += 1
            self._hmb_scan_pending_key = ""
            self._hmb_scan_pending_result = None
            self._hmb_scan_thread = None
            self._hmb_initial_catalog_scan_pending = False
        with self._hmb_thumbnail_lock:
            self._hmb_thumbnail_generation += 1
            self._hmb_thumbnail_pending_key = ""
            self._hmb_thumbnail_pending_result = None
            self._hmb_thumbnail_thread = None
            self._hmb_thumbnail_queued_bridge_request = None
        with self._hmb_catalog_probe_lock:
            self._hmb_catalog_probe_generation += 1
            self._hmb_catalog_probe_pending_key = ""
            self._hmb_catalog_probe_pending_result = None
            self._hmb_catalog_probe_thread = None
        self._replace_import_media(dict(import_media))
        self._hmb_last_applied_import_identity = (
            _canonical_import_input_identity(import_value)
        )

        # Store reconstructed connection aggregates through the ordinary host
        # lifecycle, but keep their callbacks inert until the one coherent
        # durable snapshot is published below.
        self._hmb_root_syncing = True
        self._hmb_state_syncing = True
        try:
            self.set_parameter_value(
                PROJECT_ROOT_PARAMETER,
                project_root,
                initial_setup=True,
                emit_change=False,
                skip_before_value_set=True,
            )
            self.set_parameter_value(
                IMAGE_IMPORT_PARAMETER,
                import_value,
                initial_setup=True,
                emit_change=False,
                skip_before_value_set=True,
            )
        finally:
            self._hmb_state_syncing = False
            self._hmb_root_syncing = False

        state["catalog_root"] = project_root.replace("\\", "/")
        self._hmb_hydration_adopted = False
        adopted = self._publish_state(state)
        self._hmb_hydration_adopted = True
        self._hmb_initial_catalog_root = project_root
        return bool(
            adopted.get("assets") == state.get("assets")
            and adopted.get("shot_routing") == state.get("shot_routing")
        )

    def _reconcile_hmb_shot_routing(
        self,
        catalog_identity: str = "",
    ) -> None:
        if not bool(getattr(self, "_hmb_hydration_adopted", False)):
            return
        scheduler = getattr(
            _hmb_shot_routing, "schedule_post_hydration_reconcile", None
        )
        if not callable(scheduler):
            return
        identity = (
            _clean(catalog_identity)
            or _shot_routing_catalog_identity(self._current_state())
        )
        if not identity or identity == _clean(
            getattr(self, "_hmb_last_reconciled_shot_catalog_identity", "")
        ):
            return
        # Reservation and completion are deliberately separate.  The router
        # snapshots this token into its queued generation and acknowledges it
        # only after a registered, exact-flow ``ready`` pass.  Repeated state
        # setters may still call the scheduler so a changed subscription
        # fingerprint supersedes an older pending callback safely.
        self._hmb_reserved_shot_catalog_identity = identity
        try:
            scheduled = bool(scheduler(self))
            if (
                not scheduled
                and _clean(
                    getattr(
                        self,
                        "_hmb_reserved_shot_catalog_identity",
                        "",
                    )
                ) == identity
            ):
                self._hmb_reserved_shot_catalog_identity = ""
        except Exception as exc:
            if _clean(
                getattr(
                    self,
                    "_hmb_reserved_shot_catalog_identity",
                    "",
                )
            ) == identity:
                self._hmb_reserved_shot_catalog_identity = ""
            _diagnostic_exception("Shot routing reconciliation failed", exc)

    def _hmb_shot_routing_reconcile_finished(
        self,
        acknowledgement: Any,
    ) -> None:
        """Commit one catalog identity only after the router really finished."""

        if (
            bool(getattr(self, "_hmb_node_deleted", False))
            or not isinstance(acknowledgement, dict)
            or acknowledgement.get("schema")
            != "hmb-shot-routing-reconcile-ack"
            or acknowledgement.get("version") != 1
            or acknowledgement.get("phase") != "hydrated"
        ):
            return
        token = _clean(acknowledgement.get("owner_token"))
        if not token or token != _clean(
            getattr(self, "_hmb_reserved_shot_catalog_identity", "")
        ):
            return
        self._hmb_reserved_shot_catalog_identity = ""
        if (
            acknowledgement.get("completed") is not True
            or _clean(acknowledgement.get("code")) != "ready"
        ):
            return
        current_identity = _shot_routing_catalog_identity(
            self._current_state()
        )
        if current_identity == token:
            self._hmb_last_reconciled_shot_catalog_identity = token

    def _publish_completed_catalog_scan(
        self,
        state: Dict[str, Any],
        request_key: Any,
    ) -> Dict[str, Any]:
        """Publish one worker result and adopt only a fresh registered scan.

        The request has already passed generation, key, deletion, and exact
        NodeManager identity checks at both call sites.  Clearing the key here
        makes the late-discovery advertisement exactly once.
        """

        key = _clean(request_key)[:512]
        with self._hmb_scan_lock:
            fresh_registration = bool(
                key
                and key
                == _clean(
                    getattr(self, "_hmb_fresh_registration_scan_key", "")
                )[:512]
                and not bool(getattr(self, "_hmb_node_deleted", False))
            )
            if fresh_registration:
                self._hmb_fresh_registration_scan_key = ""
        if fresh_registration:
            self._hmb_hydration_adopted = True
        normalized_state = _normalize_state(state)
        if not _clean(normalized_state.get("error")) and _clean(
            normalized_state.get("project_root")
        ):
            _store_shared_catalog_snapshot(normalized_state, normalized=True)
            _write_catalog_index(normalized_state, normalized=True)
        try:
            return self._publish_state(normalized_state, normalized=True)
        except TypeError as exc:
            # Compatibility for legacy monkey-patched publication stubs.
            if "normalized" not in str(exc):
                raise
            return self._publish_state(normalized_state)

    @staticmethod
    def _widget_revision_pair(value: Any) -> tuple[int, int] | None:
        raw = _parse_mapping(value)
        if not raw:
            return None
        scan_revision = _non_negative_int(raw.get("scan_revision"))
        try:
            ui_revision = int(raw.get(UI_EDIT_REVISION_KEY) or 0)
        except Exception:
            ui_revision = 0
        return (
            scan_revision,
            max(0, min(MAX_UI_EDIT_REVISION, ui_revision)),
        )

    def _accept_widget_state_baseline(self, value: Any) -> None:
        raw = _parse_mapping(value)
        if not raw:
            return
        normalized_state = _normalize_state(raw)
        self._accept_normalized_widget_state_baseline(normalized_state)

    def _accept_normalized_widget_state_baseline(
        self,
        normalized_state: Dict[str, Any],
        serialized: str = "",
    ) -> None:
        self._hmb_last_accepted_widget_state = serialized or _json_text(normalized_state)
        self._hmb_last_accepted_widget_revisions = (
            _non_negative_int(normalized_state.get("scan_revision")),
            _non_negative_int(normalized_state.get(UI_EDIT_REVISION_KEY)),
        )
        self._hmb_last_accepted_thumbnail_revision = _non_negative_int(
            normalized_state.get("thumbnail_revision")
        )

    def _widget_state_is_stale(self, value: Any) -> bool:
        incoming = self._widget_revision_pair(value)
        if (
            incoming is None
            or self._hmb_last_accepted_widget_state is None
        ):
            return False
        accepted_scan, accepted_ui = self._hmb_last_accepted_widget_revisions
        incoming_scan, incoming_ui = incoming
        if incoming_scan != accepted_scan:
            return incoming_scan < accepted_scan
        if incoming_ui != accepted_ui:
            return incoming_ui < accepted_ui
        raw = _parse_mapping(value)
        return _non_negative_int(raw.get("thumbnail_revision")) < max(
            0,
            _non_negative_int(
                getattr(self, "_hmb_last_accepted_thumbnail_revision", 0)
            ),
        )

    def _preserve_newer_thumbnail_baseline(self, value: Any) -> Dict[str, Any]:
        """Keep a completed thumbnail when a newer UI edit carries an old echo."""

        raw = dict(_parse_mapping(value))
        cached_raw = _parse_mapping(self._hmb_last_accepted_widget_state)
        if not raw or not cached_raw:
            return raw
        incoming_thumbnail_revision = _non_negative_int(
            raw.get("thumbnail_revision")
        )
        cached_thumbnail_revision = _non_negative_int(
            cached_raw.get("thumbnail_revision")
        )
        if (
            incoming_thumbnail_revision >= cached_thumbnail_revision
            or _non_negative_int(raw.get("scan_revision"))
            != _non_negative_int(cached_raw.get("scan_revision"))
            or _clean(raw.get("project_uid")) != _clean(cached_raw.get("project_uid"))
            or _clean(raw.get("project_cache_uid"))
            != _clean(cached_raw.get("project_cache_uid"))
            or _clean(raw.get("manifest_signature"))
            != _clean(cached_raw.get("manifest_signature"))
        ):
            return raw
        cached_assets = {
            _clean(asset.get("asset_library_id")): asset
            for asset in cached_raw.get("assets", [])
            if isinstance(asset, dict) and _clean(asset.get("asset_library_id"))
        }
        merged_assets: List[Any] = []
        for raw_asset in raw.get("assets", []):
            if not isinstance(raw_asset, dict):
                merged_assets.append(raw_asset)
                continue
            asset = dict(raw_asset)
            cached_asset = cached_assets.get(_clean(asset.get("asset_library_id")))
            if (
                cached_asset is not None
                and _clean(asset.get("media_signature"))
                and _clean(asset.get("media_signature"))
                == _clean(cached_asset.get("media_signature"))
                and _clean(cached_asset.get("thumbnail_url"))
            ):
                asset["thumbnail_url"] = _clean(cached_asset.get("thumbnail_url"))
            merged_assets.append(asset)
        raw["assets"] = merged_assets
        raw["thumbnail_revision"] = cached_thumbnail_revision
        raw["thumbnail_result"] = cached_raw.get("thumbnail_result", {})
        raw["thumbnail_busy"] = bool(cached_raw.get("thumbnail_busy", False))
        return raw

    def _restore_accepted_widget_state(self) -> None:
        cached = self._hmb_last_accepted_widget_state
        if cached is None:
            return
        parent_setter = getattr(super(), "set_parameter_value", None)
        if not callable(parent_setter):
            return
        try:
            self._hmb_restoring_widget_state = True
            if ParameterMode is None:
                parent_setter(WIDGET_STATE_PARAMETER, cached)
            else:
                parent_setter(
                    WIDGET_STATE_PARAMETER,
                    cached,
                    initial_setup=False,
                    emit_change=False,
                    skip_before_value_set=True,
                )
        finally:
            self._hmb_restoring_widget_state = False

    def _replace_import_media(self, media_by_uid: Dict[str, Any] | None) -> None:
        """Install one authoritative import snapshot and retire stale resolutions."""
        normalized_media = (
            dict(media_by_uid) if isinstance(media_by_uid, dict) else {}
        )
        identity = _import_media_map_identity(normalized_media)
        if identity != getattr(self, "_hmb_import_media_identity", ""):
            self._hmb_import_revision = (
                _non_negative_int(getattr(self, "_hmb_import_revision", 0)) + 1
            )
            cache = getattr(self, "_hmb_resolution_cache", None)
            if isinstance(cache, OrderedDict):
                cache.clear()
            self._hmb_resolution_cache_identity = ""
            # Keep the last pair staged until its replacement is complete, but
            # never treat it as current after IMAGE_IMPORT_IN changed.
            self._hmb_last_output_fingerprint = ""
            self._hmb_import_media_identity = identity
        self._hmb_import_media_by_uid = normalized_media

    def _sync_output(
        self,
        state: Dict[str, Any],
        *,
        force: bool = False,
        normalized: bool = False,
    ) -> Dict[str, Any]:
        normalized_state = state if normalized else _normalize_state(state)
        normalized = normalized_state
        resolution_cache = getattr(self, "_hmb_resolution_cache", None)
        if not isinstance(resolution_cache, OrderedDict):
            resolution_cache = OrderedDict()
            self._hmb_resolution_cache = resolution_cache
        resolution_identity = _resolution_cache_state_identity(normalized)
        if resolution_identity != getattr(
            self,
            "_hmb_resolution_cache_identity",
            "",
        ):
            resolution_cache.clear()
            self._hmb_resolution_cache_identity = resolution_identity
        import_media = getattr(self, "_hmb_import_media_by_uid", {})
        if not isinstance(import_media, dict):
            import_media = {}
        import_revision = _non_negative_int(
            getattr(self, "_hmb_import_revision", 0)
        )
        output_fingerprint = _project_output_fingerprint(
            normalized,
            import_media,
            import_revision,
        )
        cached_pair = getattr(self, "_hmb_last_output_pair", None)
        if (
            not force
            and
            output_fingerprint
            and output_fingerprint
            == getattr(self, "_hmb_last_output_fingerprint", "")
            and isinstance(cached_pair, tuple)
            and len(cached_pair) == 2
        ):
            output_values = getattr(self, "parameter_output_values", {})
            output_getter = getattr(output_values, "get", None)
            current_asset_output = (
                output_getter(OUTPUT_PARAMETER)
                if callable(output_getter)
                else None
            )
            current_media_output = (
                output_getter(MEDIA_OUTPUT_PARAMETER)
                if callable(output_getter)
                else None
            )
            cached_asset_output, cached_media_output = cached_pair
            shot_snapshot = self._cache_shot_routing_snapshot(
                normalized,
                normalized=True,
            )
            shot_token = self._shot_asset_dependency_token(shot_snapshot)
            current_shot_output = (
                output_getter(SHOT_ASSET_OUTPUT_PARAMETER)
                if callable(output_getter)
                else None
            )
            if (
                current_asset_output != cached_asset_output
                or current_media_output != cached_media_output
                or current_shot_output != shot_token
            ):
                # Treat the metadata/media branches as one synchronized pair.
                # If either host port was cleared or replaced, republish both
                # last-good values without touching the filesystem.
                _stage_and_notify_image_output_pair(
                    self,
                    cached_asset_output,
                    (
                        list(cached_media_output)
                        if isinstance(cached_media_output, list)
                        else cached_media_output
                    ),
                    shot_token,
                )
            elif getattr(self, "_hmb_pending_output_notifications", None):
                _stage_and_notify_image_output_pair(
                    self,
                    cached_asset_output,
                    cached_media_output,
                    shot_token,
                    stage_outputs=False,
                    replace_pending=False,
                )
            return normalized
        output_payload, media_values = _build_synchronized_outputs(
            normalized,
            import_media,
            resolution_cache=resolution_cache,
            import_revision=import_revision,
            force=force,
            normalized=True,
        )
        asset_output_value = _json_text(output_payload)
        media_output_value = (
            list(media_values) if isinstance(media_values, list) else media_values
        )
        warning_signature = "\n".join(output_payload.get("warnings", []))
        if warning_signature and warning_signature != self._hmb_last_resolution_warning:
            _diagnostic_warning("Selected media resolution", warning_signature)
        self._hmb_last_resolution_warning = warning_signature
        resolution = output_payload.get("media_resolution")
        cacheable_fingerprint = (
            output_fingerprint
            if output_fingerprint
            and not warning_signature
            and isinstance(resolution, dict)
            and _non_negative_int(resolution.get("unresolved_count")) == 0
            else ""
        )
        self._hmb_last_output_fingerprint = cacheable_fingerprint
        self._hmb_last_output_pair = (
            (
                asset_output_value,
                list(media_output_value)
                if isinstance(media_output_value, list)
                else media_output_value,
            )
            if cacheable_fingerprint
            else None
        )
        shot_snapshot = self._cache_shot_routing_snapshot(
            normalized, force=force, normalized=True
        )
        _stage_and_notify_image_output_pair(
            self,
            asset_output_value,
            media_output_value,
            self._shot_asset_dependency_token(shot_snapshot),
        )
        return normalized

    @staticmethod
    def _thumbnail_runtime_id(state: Dict[str, Any]) -> str:
        return _clean(
            state.get("shot_routing", {}).get("publisher_instance_uuid")
            if isinstance(state.get("shot_routing"), dict)
            else ""
        )

    def _set_thumbnail_bridge_value(self, value: Dict[str, Any]) -> None:
        normalized = _normalize_thumbnail_bridge(value)
        self._hmb_thumbnail_bridge_syncing = True
        try:
            publisher = getattr(self, "publish_update_to_parameter", None)
            if callable(publisher):
                # Stage the hidden property without emitting the full node
                # state, then publish exactly the compact bridge envelope.
                # Unlike the generic compatibility helper, this path must not
                # silently fall back to changing only Parameter.default_value:
                # doing so produces no lifecycle event and leaves the browser
                # loader waiting forever.
                try:
                    self.set_parameter_value(
                        THUMBNAIL_PATCH_PARAMETER,
                        normalized,
                        emit_change=False,
                        skip_before_value_set=True,
                    )
                except TypeError:
                    self.set_parameter_value(
                        THUMBNAIL_PATCH_PARAMETER,
                        normalized,
                    )
                publisher(THUMBNAIL_PATCH_PARAMETER, normalized)
            else:
                # Legacy/unit hosts have no explicit compact publisher. Keep
                # their ordinary setter semantics so existing tests and saved
                # workflows remain operable.
                _set_parameter_value(
                    self,
                    THUMBNAIL_PATCH_PARAMETER,
                    normalized,
                )
        finally:
            self._hmb_thumbnail_bridge_syncing = False

    def _sync_thumbnail_bridge_identity(self, state: Dict[str, Any]) -> None:
        runtime_id = self._thumbnail_runtime_id(state)
        current = _normalize_thumbnail_bridge(
            _get_parameter_raw(self, THUMBNAIL_PATCH_PARAMETER)
        )
        if _clean(current.get("runtime_instance_id")) != runtime_id:
            self._set_thumbnail_bridge_value(
                _default_thumbnail_bridge(runtime_id)
            )

    def _store_thumbnail_state_silently(
        self,
        state: Dict[str, Any],
        *,
        normalized: bool = False,
    ) -> Dict[str, Any]:
        normalized_state = state if normalized else _normalize_state(state)
        _store_shared_catalog_snapshot(normalized_state, normalized=True)
        serialized = _json_text(normalized_state)
        self._accept_normalized_widget_state_baseline(normalized_state, serialized)
        self._hmb_state_syncing = True
        try:
            self.set_parameter_value(
                WIDGET_STATE_PARAMETER,
                serialized,
                emit_change=False,
                skip_before_value_set=True,
            )
        finally:
            self._hmb_state_syncing = False
        return normalized_state

    def _publish_thumbnail_bridge_result(
        self,
        state: Dict[str, Any],
        request: Dict[str, Any],
    ) -> None:
        result = state.get("thumbnail_result")
        result = result if isinstance(result, dict) else {}
        completed_ids = {
            _clean(item)
            for item in result.get("completed_asset_library_ids", [])
            if _clean(item)
        }
        entries = [
            {
                "asset_library_id": _clean(asset.get("asset_library_id")),
                "source_uid": _clean(asset.get("source_uid")),
                "media_signature": _clean(asset.get("media_signature")),
                "thumbnail_url": _clean(asset.get("thumbnail_url")),
            }
            for asset in state.get("assets", [])
            if isinstance(asset, dict)
            and _clean(asset.get("asset_library_id")) in completed_ids
            and _clean(asset.get("thumbnail_url"))
        ]
        self._set_thumbnail_bridge_value(
            {
                "schema": THUMBNAIL_BRIDGE_SCHEMA,
                "version": THUMBNAIL_BRIDGE_VERSION,
                "runtime_instance_id": self._thumbnail_runtime_id(state),
                "operation": "hydrate",
                "phase": "result",
                "request_id": request.get("request_id"),
                "project_uid": state.get("project_uid"),
                "project_cache_uid": state.get("project_cache_uid"),
                "manifest_signature": state.get("manifest_signature"),
                "scan_revision": state.get("scan_revision"),
                "thumbnail_revision": state.get("thumbnail_revision"),
                "completed_assets": entries,
                "failed_asset_library_ids": result.get(
                    "failed_asset_library_ids", []
                ),
            }
        )

    def _publish_state(
        self,
        state: Dict[str, Any],
        *,
        normalized: bool = False,
    ) -> Dict[str, Any]:
        state = dict(state)
        state["asset_registration_request"] = {}
        state["disconnect_import_uid"] = ""
        normalized_state = state if normalized else _normalize_state(state)
        normalized = normalized_state
        pending_only = bool(
            normalized.get("scan_busy") or normalized.get("thumbnail_busy")
        )
        if not pending_only:
            # Resolve the compact shot facts before serialization.  The private
            # cache retains media while widget state receives hashes/counts only.
            # A busy acknowledgement deliberately keeps the last staged outputs:
            # it must be paintable without touching a manifest, image, or share.
            self._cache_shot_routing_snapshot(normalized, normalized=True)
        catalog_root = _project_root_text(normalized.get("catalog_root"))
        current_root = _project_root_text(
            _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
        )
        if (
            catalog_root
            and not normalized.get("error")
            and catalog_root.casefold() != current_root.casefold()
        ):
            self._hmb_root_syncing = True
            try:
                _set_parameter_value(
                    self,
                    PROJECT_ROOT_PARAMETER,
                    catalog_root,
                )
            finally:
                self._hmb_root_syncing = False
        serialized = _json_text(normalized)
        self._accept_normalized_widget_state_baseline(
            normalized,
            serialized,
        )
        self._hmb_state_syncing = True
        try:
            _set_parameter_value(
                self,
                WIDGET_STATE_PARAMETER,
                serialized,
            )
        finally:
            self._hmb_state_syncing = False
        self._hmb_refresh_revision = _non_negative_int(
            normalized.get("refresh_revision")
        )
        if not pending_only:
            normalized = self._sync_output(normalized, normalized=True)
            self._reconcile_hmb_shot_routing(
                _shot_routing_catalog_identity(normalized, normalized=True)
            )
        self._sync_thumbnail_bridge_identity(normalized)
        return normalized

    def _scan_owner_is_current(self) -> bool:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return False
        try:
            from griptape_nodes.retained_mode.engine import has_current_engine  # type: ignore
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

            # Unit/legacy hosts may expose the package without an active Engine.
            # Identity cannot be stale before registration exists, and probing
            # GriptapeNodes here would synchronously construct the whole Engine.
            if not has_current_engine():
                return True
            node_name = _clean(getattr(self, "name", ""))
            if node_name:
                registered = GriptapeNodes.NodeManager().get_node_by_name(node_name)
                return registered is self
        except ImportError:
            return True
        except Exception:
            # When the host exists but identity cannot be proven, never let an
            # old same-name worker publish into a replacement node.
            return False
        return True

    def _ensure_scan_runtime_state(self) -> None:
        if not hasattr(self, "_hmb_scan_lock"):
            self._hmb_scan_lock = threading.RLock()
        if not hasattr(self, "_hmb_scan_generation"):
            self._hmb_scan_generation = 0
        if not hasattr(self, "_hmb_scan_pending_key"):
            self._hmb_scan_pending_key = ""
        if not hasattr(self, "_hmb_scan_thread"):
            self._hmb_scan_thread = None
        if not hasattr(self, "_hmb_scan_pending_result"):
            self._hmb_scan_pending_result = None
        if not hasattr(self, "_hmb_node_deleted"):
            self._hmb_node_deleted = False

    def _ensure_thumbnail_runtime_state(self) -> None:
        if not hasattr(self, "_hmb_thumbnail_lock"):
            self._hmb_thumbnail_lock = threading.RLock()
        if not hasattr(self, "_hmb_thumbnail_generation"):
            self._hmb_thumbnail_generation = 0
        if not hasattr(self, "_hmb_thumbnail_pending_key"):
            self._hmb_thumbnail_pending_key = ""
        if not hasattr(self, "_hmb_thumbnail_thread"):
            self._hmb_thumbnail_thread = None
        if not hasattr(self, "_hmb_thumbnail_pending_result"):
            self._hmb_thumbnail_pending_result = None
        if not hasattr(self, "_hmb_thumbnail_queued_bridge_request"):
            self._hmb_thumbnail_queued_bridge_request = None
        if not hasattr(self, "_hmb_node_deleted"):
            self._hmb_node_deleted = False

    def _ensure_catalog_probe_runtime_state(self) -> None:
        if not hasattr(self, "_hmb_catalog_probe_lock"):
            self._hmb_catalog_probe_lock = threading.RLock()
        if not hasattr(self, "_hmb_catalog_probe_generation"):
            self._hmb_catalog_probe_generation = 0
        if not hasattr(self, "_hmb_catalog_probe_pending_key"):
            self._hmb_catalog_probe_pending_key = ""
        if not hasattr(self, "_hmb_catalog_probe_thread"):
            self._hmb_catalog_probe_thread = None
        if not hasattr(self, "_hmb_catalog_probe_pending_result"):
            self._hmb_catalog_probe_pending_result = None
        if not hasattr(self, "_hmb_catalog_probe_last_manifest_at"):
            self._hmb_catalog_probe_last_manifest_at = 0.0
        if not hasattr(self, "_hmb_catalog_probe_last_folder_at"):
            self._hmb_catalog_probe_last_folder_at = 0.0
        if not hasattr(self, "_hmb_catalog_probe_pending_folder_signature"):
            self._hmb_catalog_probe_pending_folder_signature = ""
        if not hasattr(self, "_hmb_catalog_probe_pending_folder_since"):
            self._hmb_catalog_probe_pending_folder_since = 0.0
        if not hasattr(self, "_hmb_node_deleted"):
            self._hmb_node_deleted = False

    def _catalog_probe_result_envelope(
        self,
        request: Dict[str, Any],
        outcome: str,
        state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        current = state if isinstance(state, dict) else self._current_state()
        return {
            "schema": THUMBNAIL_BRIDGE_SCHEMA,
            "version": THUMBNAIL_BRIDGE_VERSION,
            "operation": CATALOG_PROBE_OPERATION,
            "phase": "result",
            "request_id": _clean(request.get("request_id")),
            "runtime_instance_id": _clean(request.get("runtime_instance_id")),
            "project_uid": _clean(current.get("project_uid")),
            "project_cache_uid": _clean(current.get("project_cache_uid")),
            "project_root": _clean(current.get("project_root")),
            "manifest_signature": _clean(current.get("manifest_signature")),
            "folder_signature": _clean(current.get("folder_signature")),
            "scan_revision": _non_negative_int(current.get("scan_revision")),
            "probe_kind": (
                "folder"
                if _clean(request.get("probe_kind")).casefold() == "folder"
                else "manifest"
            ),
            "outcome": outcome,
        }

    def _compute_catalog_probe(
        self,
        state: Dict[str, Any],
        request: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any] | None]:
        """Probe metadata only; return a full state solely after a real change."""

        project_root_text = _clean(state.get("project_root"))
        if not project_root_text:
            return "no_change", None
        now = time.monotonic()
        probe_kind = _clean(request.get("probe_kind")).casefold()
        if probe_kind == "folder":
            pending_signature = _clean(
                self._hmb_catalog_probe_pending_folder_signature
            )
            if (
                not pending_signature
                and now - self._hmb_catalog_probe_last_folder_at
                < CATALOG_PROBE_FOLDER_SECONDS
            ):
                return "deferred", None
            signature = _project_folder_metadata_signature(project_root_text)
            self._hmb_catalog_probe_last_folder_at = now
            current_signature = _clean(state.get("folder_signature"))
            if not current_signature:
                state = dict(state)
                state["folder_signature"] = signature
                return "changed", _normalize_state(state)
            if signature == current_signature:
                self._hmb_catalog_probe_pending_folder_signature = ""
                self._hmb_catalog_probe_pending_folder_since = 0.0
                return "no_change", None
            if pending_signature != signature:
                self._hmb_catalog_probe_pending_folder_signature = signature
                self._hmb_catalog_probe_pending_folder_since = now
                # Confirm a raw copy/replace once inside this background worker.
                # This preserves the one-second stable-write guard without
                # making the browser wait for the next 10-second folder poll.
                time.sleep(CATALOG_PROBE_STABLE_WRITE_SECONDS + 0.05)
                confirmed_signature = _project_folder_metadata_signature(
                    project_root_text
                )
                confirmed_at = time.monotonic()
                self._hmb_catalog_probe_last_folder_at = confirmed_at
                if confirmed_signature != signature:
                    self._hmb_catalog_probe_pending_folder_signature = (
                        confirmed_signature
                    )
                    self._hmb_catalog_probe_pending_folder_since = confirmed_at
                    return "deferred", None
                signature = confirmed_signature
                now = confirmed_at
            if (
                now - self._hmb_catalog_probe_pending_folder_since
                < CATALOG_PROBE_STABLE_WRITE_SECONDS
            ):
                return "deferred", None
        else:
            if (
                now - self._hmb_catalog_probe_last_manifest_at
                < CATALOG_PROBE_MANIFEST_SECONDS
            ):
                return "deferred", None
            self._hmb_catalog_probe_last_manifest_at = now
            signature = _asset_manifest_signature(Path(project_root_text))
            if signature == _clean(state.get("manifest_signature")):
                return "no_change", None

        refreshed_scan = _scan_project_assets(project_root_text)
        refreshed = _merge_scan_with_state(refreshed_scan, state)
        refreshed["catalog_root"] = state["catalog_root"]
        refreshed["projects"] = state["projects"]
        self._hmb_catalog_probe_pending_folder_signature = ""
        self._hmb_catalog_probe_pending_folder_since = 0.0
        return "changed", refreshed

    def _consume_pending_catalog_probe_result(self) -> bool:
        self._ensure_catalog_probe_runtime_state()
        with self._hmb_catalog_probe_lock:
            pending = self._hmb_catalog_probe_pending_result
            if pending is None:
                return False
            generation, key, payload = pending
            if (
                generation != self._hmb_catalog_probe_generation
                or key != self._hmb_catalog_probe_pending_key
                or not self._scan_owner_is_current()
            ):
                self._hmb_catalog_probe_pending_result = None
                self._hmb_catalog_probe_pending_key = ""
                self._hmb_catalog_probe_thread = None
                return False
            self._hmb_catalog_probe_pending_result = None
            self._hmb_catalog_probe_pending_key = ""
            self._hmb_catalog_probe_thread = None
        request = dict(payload.get("request") or {})
        outcome = _clean(payload.get("outcome")) or "deferred"
        result_state = payload.get("state")
        live = self._current_state()
        base = payload.get("base") if isinstance(payload.get("base"), dict) else {}
        if any(
            _clean(base.get(field)).replace("\\", "/").casefold()
            != _clean(live.get(field)).replace("\\", "/").casefold()
            for field in (
                "catalog_root",
                "project_root",
                "project_cache_uid",
                "manifest_signature",
            )
        ) or _non_negative_int(base.get("scan_revision")) != _non_negative_int(
            live.get("scan_revision")
        ):
            return False
        if outcome == "changed" and isinstance(result_state, dict):
            result_state = _merge_async_scan_result_with_live_state(
                result_state,
                base or live,
                live,
            )
            result_state["scan_busy"] = False
            result_state = self._publish_completed_catalog_scan(
                result_state,
                f"probe:{key}",
            )
        else:
            result_state = self._current_state()
        self._set_thumbnail_bridge_value(
            self._catalog_probe_result_envelope(request, outcome, result_state)
        )
        return True

    def _schedule_catalog_probe(
        self,
        request: Dict[str, Any],
        state: Dict[str, Any],
    ) -> None:
        """Run one bounded compact probe; never publish unchanged full state."""

        self._ensure_catalog_probe_runtime_state()
        key = _clean(request.get("request_id"))[:128]
        with self._hmb_catalog_probe_lock:
            if self._hmb_catalog_probe_pending_key:
                self._set_thumbnail_bridge_value(
                    self._catalog_probe_result_envelope(request, "deferred", state)
                )
                return
            self._hmb_catalog_probe_generation += 1
            generation = self._hmb_catalog_probe_generation
            self._hmb_catalog_probe_pending_key = key
            self._hmb_catalog_probe_pending_result = None
        base = _normalize_state(state)
        node_ref = weakref.ref(self)

        def worker() -> None:
            owner = node_ref()
            if owner is None:
                return
            try:
                outcome, result_state = owner._compute_catalog_probe(base, request)
            except Exception as exc:
                outcome, result_state = "offline", None
                message = _clean(exc)
                if message != getattr(owner, "_hmb_last_manifest_poll_error", ""):
                    _diagnostic_warning("Shared catalog probe retained last snapshot", exc)
                    owner._hmb_last_manifest_poll_error = message
            owner = node_ref()
            if owner is None:
                return
            with owner._hmb_catalog_probe_lock:
                if (
                    generation != owner._hmb_catalog_probe_generation
                    or key != owner._hmb_catalog_probe_pending_key
                    or bool(getattr(owner, "_hmb_node_deleted", False))
                ):
                    return
                owner._hmb_catalog_probe_pending_result = (
                    generation,
                    key,
                    {
                        "request": dict(request),
                        "outcome": outcome,
                        "state": result_state,
                        "base": base,
                    },
                )

        thread = threading.Thread(
            target=worker,
            name=f"HMBImageAssetCatalogProbe-{generation}",
            daemon=True,
        )
        with self._hmb_catalog_probe_lock:
            self._hmb_catalog_probe_thread = thread
        thread.start()

    def _drain_queued_thumbnail_bridge_request(self) -> bool:
        """Start the latest compact request deferred by thumbnail single-flight."""

        self._ensure_thumbnail_runtime_state()
        with self._hmb_thumbnail_lock:
            if self._hmb_thumbnail_pending_key:
                return False
            queued = self._hmb_thumbnail_queued_bridge_request
            self._hmb_thumbnail_queued_bridge_request = None
        if not isinstance(queued, dict):
            return False
        current = self._current_state()
        if (
            _clean(queued.get("runtime_instance_id"))
            != self._thumbnail_runtime_id(current)
            or _clean(queued.get("project_uid"))
            != _clean(current.get("project_uid"))
            or _clean(queued.get("manifest_signature"))
            != _clean(current.get("manifest_signature"))
            or _non_negative_int(queued.get("scan_revision"))
            != _non_negative_int(current.get("scan_revision"))
        ):
            return False
        self._schedule_thumbnail_hydration(
            current,
            queued,
            compact_bridge=True,
            candidate_normalized=True,
            request_normalized=True,
        )
        return True

    def _schedule_thumbnail_hydration(
        self,
        candidate_state: Dict[str, Any],
        request_value: Any,
        *,
        compact_bridge: bool = False,
        candidate_normalized: bool = False,
        request_normalized: bool = False,
    ) -> Dict[str, Any]:
        """Hydrate one bounded batch off-thread with its own stale generation."""

        request = (
            dict(request_value)
            if request_normalized and isinstance(request_value, dict)
            else _normalize_thumbnail_request(request_value)
        )
        if not request:
            return _normalize_state(candidate_state)
        self._ensure_thumbnail_runtime_state()
        key = _clean(request.get("request_id"))[:128]
        active_request = False
        with self._hmb_thumbnail_lock:
            if self._hmb_thumbnail_pending_key:
                # True single-flight: a different request cannot spawn another
                # decoder thread. The browser recomputes remaining missing IDs
                # after this active bounded batch completes.
                active_request = True
                generation = self._hmb_thumbnail_generation
                if (
                    compact_bridge
                    and key != self._hmb_thumbnail_pending_key
                ):
                    # A remount may replace the browser's pending request while
                    # the previous decoder batch is still active. Retain only
                    # the latest compact intent and start it after completion;
                    # otherwise the old result is rejected by the new request
                    # ID and the loader can wait forever.
                    self._hmb_thumbnail_queued_bridge_request = dict(request)
            else:
                self._hmb_thumbnail_generation += 1
                generation = self._hmb_thumbnail_generation
                self._hmb_thumbnail_pending_key = key
                self._hmb_thumbnail_pending_result = None
                # A queued request from an older completed flight must never
                # run after this newer flight. This closes the small interval
                # between completion and deferred-queue draining.
                self._hmb_thumbnail_queued_bridge_request = None
        if active_request:
            current = dict(self._current_state())
            current["thumbnail_request"] = {}
            if not compact_bridge:
                current["thumbnail_busy"] = True
            return current

        hydration_base = (
            candidate_state
            if candidate_normalized
            else _normalize_state(candidate_state)
        )
        hydration_base["thumbnail_request"] = {}
        busy = dict(hydration_base)
        busy["thumbnail_busy"] = True
        busy["thumbnail_result"] = {}
        node_ref = weakref.ref(self)
        def resolve_host_event_loop(preferred: Any = None) -> Any:
            """Return only a live engine loop without constructing an Engine.

            Retained-mode value callbacks can be dispatched from a synchronous
            request thread, so ``asyncio.get_running_loop()`` alone is not a
            sufficient host contract.  EventManager owns the engine loop and
            exposes it specifically for cross-thread scheduling.
            """

            candidates: List[Any] = []
            if preferred is not None:
                candidates.append(preferred)
            try:
                candidates.append(asyncio.get_running_loop())
            except RuntimeError:
                pass
            except Exception as exc:
                _diagnostic_exception("Thumbnail hydration event-loop lookup", exc)
            try:
                from griptape_nodes.retained_mode.engine import has_current_engine  # type: ignore
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

                if has_current_engine():
                    candidates.append(GriptapeNodes.EventManager().event_loop)
            except ImportError:
                pass
            except Exception as exc:
                _diagnostic_exception(
                    "Active thumbnail hydration event-loop lookup",
                    exc,
                )
            seen: set[int] = set()
            for candidate in candidates:
                if candidate is None or id(candidate) in seen:
                    continue
                seen.add(id(candidate))
                try:
                    if candidate.is_running() and not candidate.is_closed():
                        return candidate
                except Exception:
                    continue
            return None

        event_loop = resolve_host_event_loop()
        host_context = contextvars.copy_context()

        def apply_result(result: Dict[str, Any]) -> None:
            owner = node_ref()
            if owner is None:
                return
            with owner._hmb_thumbnail_lock:
                generation_matches = (
                    generation == owner._hmb_thumbnail_generation
                    and key == owner._hmb_thumbnail_pending_key
                )
                if not generation_matches:
                    return
                if not owner._scan_owner_is_current():
                    # A deleted/replaced same-name node must not retain a dead
                    # single-flight slot that can later drain into a new node.
                    owner._hmb_thumbnail_pending_key = ""
                    owner._hmb_thumbnail_pending_result = None
                    owner._hmb_thumbnail_thread = None
                    owner._hmb_thumbnail_queued_bridge_request = None
                    return
            try:
                merged = _merge_async_thumbnail_result_with_live_state(
                    result,
                    hydration_base,
                    owner._current_state(),
                    request,
                    inputs_normalized=True,
                    request_normalized=True,
                )
                _store_shared_catalog_snapshot(merged, normalized=True)
                if compact_bridge:
                    merged = owner._store_thumbnail_state_silently(
                        merged,
                        normalized=True,
                    )
                    owner._publish_thumbnail_bridge_result(merged, request)
                else:
                    owner._publish_state(merged, normalized=True)
            except Exception as exc:
                # Keep the immutable worker result retrievable.  The next
                # retained-mode callback (including the browser watchdog's
                # idempotent same-request probe) can safely drain it on the
                # engine thread instead of leaving the UI permanently busy.
                _diagnostic_exception(
                    "Thumbnail completion publication failed",
                    exc,
                )
                with owner._hmb_thumbnail_lock:
                    if (
                        generation == owner._hmb_thumbnail_generation
                        and key == owner._hmb_thumbnail_pending_key
                        and not bool(getattr(owner, "_hmb_node_deleted", False))
                    ):
                        owner._hmb_thumbnail_pending_result = (
                            generation,
                            key,
                            {
                                "state": result,
                                "base": hydration_base,
                                "request": request,
                                "compact_bridge": compact_bridge,
                            },
                        )
                return
            with owner._hmb_thumbnail_lock:
                if (
                    generation != owner._hmb_thumbnail_generation
                    or key != owner._hmb_thumbnail_pending_key
                ):
                    return
                owner._hmb_thumbnail_pending_key = ""
                owner._hmb_thumbnail_thread = None
                owner._hmb_thumbnail_pending_result = None
            owner._drain_queued_thumbnail_bridge_request()

        def worker() -> None:
            owner = node_ref()
            if owner is None:
                return
            try:
                result = _hydrate_asset_thumbnails(
                    hydration_base,
                    request,
                    normalized=True,
                    request_normalized=True,
                )
            except Exception as exc:
                result = dict(hydration_base)
                result["thumbnail_busy"] = False
                result["thumbnail_revision"] = _non_negative_int(
                    hydration_base.get("thumbnail_revision")
                ) + 1
                result["thumbnail_result"] = {
                    "request_id": request["request_id"],
                    "project_uid": request["project_uid"],
                    "project_cache_uid": _clean(
                        request.get("project_cache_uid")
                        or hydration_base.get("project_cache_uid")
                    ),
                    "manifest_signature": request["manifest_signature"],
                    "scan_revision": request["scan_revision"],
                    "completed_asset_library_ids": [],
                    "failed_asset_library_ids": list(
                        request["asset_library_ids"]
                    ),
                }
                _diagnostic_exception("Background thumbnail hydration failed", exc)
            owner = node_ref()
            if owner is None:
                return
            with owner._hmb_thumbnail_lock:
                is_current = (
                    generation == owner._hmb_thumbnail_generation
                    and key == owner._hmb_thumbnail_pending_key
                    and not bool(getattr(owner, "_hmb_node_deleted", False))
                )
            if not is_current:
                return
            # Store the immutable completion before queueing it to the host.
            # ``call_soon_threadsafe`` may accept a callback immediately before
            # its loop is stopped/replaced; retaining this copy lets the next
            # official value callback/watchdog probe finish the same request.
            with owner._hmb_thumbnail_lock:
                if (
                    generation == owner._hmb_thumbnail_generation
                    and key == owner._hmb_thumbnail_pending_key
                    and not bool(getattr(owner, "_hmb_node_deleted", False))
                ):
                    owner._hmb_thumbnail_pending_result = (
                        generation,
                        key,
                        {
                            "state": result,
                            "base": hydration_base,
                            "request": request,
                            "compact_bridge": compact_bridge,
                        },
                    )
            # Resolve the manager-owned loop again after decoding.  Some hosts
            # deliver the request during a short bootstrap/remount interval in
            # which the loop was not yet observable at scheduling time.
            for retry_delay in (0.0, 0.02, 0.08, 0.20):
                if retry_delay:
                    time.sleep(retry_delay)
                completion_loop = host_context.copy().run(
                    resolve_host_event_loop,
                    event_loop,
                )
                if completion_loop is None:
                    continue
                try:
                    try:
                        completion_loop.call_soon_threadsafe(
                            apply_result,
                            result,
                            context=host_context.copy(),
                        )
                    except TypeError:
                        # Python/legacy loop compatibility; current bundled
                        # hosts support the explicit context argument. Keep
                        # the captured host identity on older loops as well.
                        completion_loop.call_soon_threadsafe(
                            host_context.copy().run,
                            apply_result,
                            result,
                        )
                    return
                except Exception as exc:
                    _diagnostic_exception(
                        "Background thumbnail result queue unavailable",
                        exc,
                    )
            # No loop accepted the callback. The pre-stored result remains
            # available to the next retained-mode callback.

        with self._hmb_thumbnail_lock:
            if (
                generation != self._hmb_thumbnail_generation
                or key != self._hmb_thumbnail_pending_key
                or bool(getattr(self, "_hmb_node_deleted", False))
            ):
                return busy
            thread = threading.Thread(
                target=worker,
                name=f"HMBImageAssetThumbnail-{generation}",
                daemon=True,
            )
            self._hmb_thumbnail_thread = thread
        thread.start()
        return busy

    def _consume_pending_thumbnail_result(self) -> bool:
        self._ensure_thumbnail_runtime_state()
        with self._hmb_thumbnail_lock:
            pending = self._hmb_thumbnail_pending_result
            if pending is None:
                return False
            generation, key, payload = pending
            generation_matches = (
                generation == self._hmb_thumbnail_generation
                and key == self._hmb_thumbnail_pending_key
            )
            if not generation_matches:
                self._hmb_thumbnail_pending_result = None
                return False
            if not self._scan_owner_is_current():
                self._hmb_thumbnail_pending_result = None
                self._hmb_thumbnail_pending_key = ""
                self._hmb_thumbnail_thread = None
                self._hmb_thumbnail_queued_bridge_request = None
                return False
        try:
            merged = _merge_async_thumbnail_result_with_live_state(
                payload.get("state"),
                payload.get("base"),
                self._current_state(),
                payload.get("request"),
                inputs_normalized=True,
                request_normalized=True,
            )
            _store_shared_catalog_snapshot(merged, normalized=True)
            if bool(payload.get("compact_bridge")):
                merged = self._store_thumbnail_state_silently(
                    merged,
                    normalized=True,
                )
                self._publish_thumbnail_bridge_result(
                    merged,
                    payload.get("request") or {},
                )
            else:
                self._publish_state(merged, normalized=True)
        except Exception as exc:
            # Leave the immutable completion retrievable for the next official
            # retained-mode callback instead of losing its terminal event.
            _diagnostic_exception("Pending thumbnail publication failed", exc)
            return False
        with self._hmb_thumbnail_lock:
            if (
                generation != self._hmb_thumbnail_generation
                or key != self._hmb_thumbnail_pending_key
            ):
                return False
            self._hmb_thumbnail_pending_result = None
            self._hmb_thumbnail_pending_key = ""
            self._hmb_thumbnail_thread = None
        self._drain_queued_thumbnail_bridge_request()
        return True

    def _schedule_catalog_scan(
        self,
        request_key: str,
        candidate_state: Dict[str, Any],
        scan: Callable[[], Any],
        failure_state: Dict[str, Any] | None = None,
        result_merger: Callable[
            [Dict[str, Any], Dict[str, Any], Dict[str, Any]],
            Dict[str, Any],
        ]
        | None = None,
    ) -> Dict[str, Any]:
        """Publish a busy snapshot and run filesystem work off the UI thread.

        Identical reloads coalesce. A newer request, node deletion, or same-name
        replacement invalidates the older worker before it can publish.
        """

        self._ensure_scan_runtime_state()
        key = _clean(request_key)[:512] or "catalog-scan"
        with self._hmb_scan_lock:
            if self._hmb_scan_pending_key == key:
                current = self._current_state()
                current["scan_busy"] = True
                return current
            if (
                getattr(self, "_hmb_fresh_registration_scan_key", "")
                and self._hmb_fresh_registration_scan_key != key
            ):
                self._hmb_fresh_registration_scan_key = ""
            self._hmb_scan_generation += 1
            generation = self._hmb_scan_generation
            request_id = f"scan-{generation}-{uuid.uuid4().hex[:12]}"
            self._hmb_scan_pending_key = key
            # A result stored by a host without a running event loop belongs
            # to the prior generation and must not be retained after a newer
            # user request supersedes it.
            self._hmb_scan_pending_result = None

        scan_base = _normalize_state(candidate_state)
        scan_import_revision = _non_negative_int(
            getattr(self, "_hmb_import_revision", 0)
        )
        busy = dict(scan_base)
        busy["scan_busy"] = True
        busy["scan_request_id"] = request_id
        busy["error"] = ""
        busy = self._publish_state(busy)
        node_ref = weakref.ref(self)
        # Never instantiate/resolve Griptape's Engine from this UI callback.
        # In actual-host tests a cold EventManager lookup can take seconds.  A
        # running callback loop is sufficient for thread-safe publication; a
        # synchronous/legacy host uses the existing retained-mode consumption
        # fallback instead.
        event_loop = None
        try:
            event_loop = asyncio.get_running_loop()
        except RuntimeError:
            event_loop = None
        except Exception as exc:
            _diagnostic_exception("Background project scan event-loop lookup", exc)
        if event_loop is None:
            try:
                from griptape_nodes.retained_mode.engine import has_current_engine  # type: ignore
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

                # This guard is the important boundary: never let a catalog UI
                # callback lazily construct an Engine just to locate its loop.
                if has_current_engine():
                    event_loop = GriptapeNodes.EventManager().event_loop
            except ImportError:
                event_loop = None
            except Exception as exc:
                _diagnostic_exception(
                    "Active background project scan event-loop lookup",
                    exc,
                )
        host_context = contextvars.copy_context()

        def resolve_scan_event_loop(preferred: Any = None) -> Any:
            """Re-resolve the official host loop without constructing Engine."""

            candidates: List[Any] = []
            if preferred is not None:
                candidates.append(preferred)
            try:
                candidates.append(asyncio.get_running_loop())
            except RuntimeError:
                pass
            except Exception as exc:
                _diagnostic_exception(
                    "Background project scan event-loop refresh",
                    exc,
                )
            try:
                from griptape_nodes.retained_mode.engine import has_current_engine  # type: ignore
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

                if has_current_engine():
                    candidates.append(GriptapeNodes.EventManager().event_loop)
            except ImportError:
                pass
            except Exception as exc:
                _diagnostic_exception(
                    "Active background project scan event-loop refresh",
                    exc,
                )
            seen: set[int] = set()
            for candidate in candidates:
                if candidate is None or id(candidate) in seen:
                    continue
                seen.add(id(candidate))
                try:
                    if candidate.is_running() and not candidate.is_closed():
                        return candidate
                except Exception:
                    continue
            return None

        def apply_result(
            result: Dict[str, Any],
            media_by_uid: Dict[str, Any] | None,
        ) -> None:
            owner = node_ref()
            if owner is None:
                return
            with owner._hmb_scan_lock:
                generation_matches = (
                    generation == owner._hmb_scan_generation
                    and key == owner._hmb_scan_pending_key
                )
                if not generation_matches:
                    return
                if not owner._scan_owner_is_current():
                    owner._hmb_scan_pending_key = ""
                    owner._hmb_scan_thread = None
                    owner._hmb_scan_pending_result = None
                    return
            worker_result = result
            try:
                live_state = owner._current_state()
                merger = result_merger or _merge_async_scan_result_with_live_state
                result = merger(worker_result, scan_base, live_state)
                if (
                    media_by_uid is not None
                    and _non_negative_int(
                        getattr(owner, "_hmb_import_revision", 0)
                    ) == scan_import_revision
                ):
                    owner._replace_import_media(media_by_uid)
                result["scan_busy"] = False
                result["scan_request_id"] = request_id
                owner._publish_completed_catalog_scan(result, key)
            except Exception as exc:
                _diagnostic_exception("Catalog completion publication failed", exc)
                with owner._hmb_scan_lock:
                    if (
                        generation == owner._hmb_scan_generation
                        and key == owner._hmb_scan_pending_key
                        and not bool(getattr(owner, "_hmb_node_deleted", False))
                    ):
                        owner._hmb_scan_pending_result = (
                            generation,
                            key,
                            request_id,
                            {
                                "state": worker_result,
                                "media_by_uid": media_by_uid,
                                "scan_base": scan_base,
                                "scan_import_revision": scan_import_revision,
                                "result_merger": result_merger,
                            },
                        )
                return
            with owner._hmb_scan_lock:
                if (
                    generation != owner._hmb_scan_generation
                    or key != owner._hmb_scan_pending_key
                ):
                    return
                owner._hmb_scan_pending_key = ""
                owner._hmb_scan_thread = None
                owner._hmb_scan_pending_result = None

        def worker() -> None:
            owner = node_ref()
            if owner is None:
                return
            try:
                scanned = scan()
                if (
                    isinstance(scanned, tuple)
                    and len(scanned) == 2
                    and isinstance(scanned[0], dict)
                ):
                    scanned_state, scanned_media = scanned
                    media_by_uid = (
                        dict(scanned_media)
                        if isinstance(scanned_media, dict)
                        else None
                    )
                else:
                    scanned_state = scanned
                    media_by_uid = None
                result = _normalize_state(scanned_state)
                result["error"] = ""
            except Exception as exc:
                result = _normalize_state(failure_state or candidate_state)
                media_by_uid = None
                result["error"] = str(exc)
                _diagnostic_exception("Background project scan failed", exc)
            owner = node_ref()
            if owner is None:
                return
            with owner._hmb_scan_lock:
                is_current = (
                    generation == owner._hmb_scan_generation
                    and key == owner._hmb_scan_pending_key
                    and not bool(getattr(owner, "_hmb_node_deleted", False))
                )
                if not is_current:
                    return
                # Retain before enqueue for the same loop-stop race handled by
                # thumbnail hydration. A later retained callback and the
                # scheduled callback race on generation/key; only one can win.
                owner._hmb_scan_pending_result = (
                    generation,
                    key,
                    request_id,
                    {
                        "state": result,
                        "media_by_uid": media_by_uid,
                        "scan_base": scan_base,
                        "scan_import_revision": scan_import_revision,
                        "result_merger": result_merger,
                    },
                )
            # The host loop can become observable shortly after a remount. Use
            # the captured host ContextVar identity while re-resolving it, then
            # marshal the completion exactly once onto that loop.
            for retry_delay in (0.0, 0.02, 0.08, 0.20):
                if retry_delay:
                    time.sleep(retry_delay)
                completion_loop = host_context.copy().run(
                    resolve_scan_event_loop,
                    event_loop,
                )
                if completion_loop is None:
                    continue
                try:
                    try:
                        completion_loop.call_soon_threadsafe(
                            apply_result,
                            result,
                            media_by_uid,
                            context=host_context.copy(),
                        )
                    except TypeError:
                        completion_loop.call_soon_threadsafe(
                            host_context.copy().run,
                            apply_result,
                            result,
                            media_by_uid,
                        )
                    return
                except Exception as exc:
                    _diagnostic_exception(
                        "Background scan result queue unavailable",
                        exc,
                    )
            # Never call retained-mode host APIs from the worker.
            # A host without a running event loop consumes this result on its
            # next retained-mode callback or explicit process().
            # No loop accepted the callback. The pre-stored result remains
            # available to the next retained-mode callback/process().

        def launch() -> None:
            owner = node_ref()
            if owner is None:
                return
            with owner._hmb_scan_lock:
                if (
                    generation != owner._hmb_scan_generation
                    or key != owner._hmb_scan_pending_key
                    or bool(getattr(owner, "_hmb_node_deleted", False))
                ):
                    return
                thread = threading.Thread(
                    target=worker,
                    name=f"HMBImageAssetScan-{generation}",
                    daemon=True,
                )
                owner._hmb_scan_thread = thread
            thread.start()

        # Starting a daemon thread is bounded and does not require any retained-
        # mode manager.  Only the completed result is marshalled back to the
        # captured UI loop.
        launch()
        return busy

    def _consume_pending_catalog_scan_result(self) -> bool:
        """Apply a worker result only from a retained-mode/UI callback."""

        self._ensure_scan_runtime_state()
        with self._hmb_scan_lock:
            pending = self._hmb_scan_pending_result
            if pending is None:
                return False
            generation, key, request_id, payload = pending
            generation_matches = (
                generation == self._hmb_scan_generation
                and key == self._hmb_scan_pending_key
            )
            if not generation_matches:
                self._hmb_scan_pending_result = None
                return False
            if not self._scan_owner_is_current():
                self._hmb_scan_pending_result = None
                self._hmb_scan_pending_key = ""
                self._hmb_scan_thread = None
                return False
        try:
            live_state = self._current_state()
            merger = payload.get("result_merger")
            if not callable(merger):
                merger = _merge_async_scan_result_with_live_state
            result = merger(
                payload.get("state"),
                payload.get("scan_base"),
                live_state,
            )
            media_by_uid = payload.get("media_by_uid")
            if (
                isinstance(media_by_uid, dict)
                and _non_negative_int(
                    getattr(self, "_hmb_import_revision", 0)
                ) == _non_negative_int(payload.get("scan_import_revision"))
            ):
                self._replace_import_media(media_by_uid)
            result["scan_busy"] = False
            result["scan_request_id"] = request_id
            self._publish_completed_catalog_scan(result, key)
        except Exception as exc:
            _diagnostic_exception("Pending catalog publication failed", exc)
            return False
        with self._hmb_scan_lock:
            if (
                generation != self._hmb_scan_generation
                or key != self._hmb_scan_pending_key
            ):
                return False
            self._hmb_scan_pending_result = None
            self._hmb_scan_pending_key = ""
            self._hmb_scan_thread = None
        return True

    def _load_catalog(self, root_value: Any) -> Dict[str, Any]:
        previous = self._current_state()
        try:
            state = _load_project_catalog(
                root_value or str(DEFAULT_PROJECTS_ROOT),
                previous,
            )
        except Exception as exc:
            state = dict(previous)
            state.update(
                {
                    "catalog_root": _project_root_text(root_value).replace("\\", "/"),
                    "error": str(exc),
                    "scan_revision": _non_negative_int(
                        previous.get("scan_revision")
                    )
                    + 1,
                }
            )
            state = _normalize_state(state)
            _diagnostic_exception("Project catalog scan failed", exc)
        return self._publish_state(state)

    def _schedule_catalog_root_change(self, root_value: Any) -> Dict[str, Any]:
        """Acknowledge a picker edit immediately and discover it off-thread."""

        self._hmb_initial_catalog_scan_pending = False
        self._ensure_catalog_probe_runtime_state()
        with self._hmb_catalog_probe_lock:
            # A probe belongs to the project snapshot captured when it started.
            # Retire it before publishing a new catalog root so an old scan can
            # never merge back over the user's new root selection.
            self._hmb_catalog_probe_generation += 1
            self._hmb_catalog_probe_pending_key = ""
            self._hmb_catalog_probe_pending_result = None
            self._hmb_catalog_probe_thread = None
            self._hmb_catalog_probe_pending_folder_signature = ""
            self._hmb_catalog_probe_pending_folder_since = 0.0
        requested_root = (
            _project_root_text(root_value) or str(DEFAULT_PROJECTS_ROOT)
        ).replace("\\", "/")
        previous = self._current_state()
        candidate = dict(previous)
        candidate["catalog_root"] = requested_root
        candidate["error"] = ""
        captured_import_value = _get_parameter_raw(
            self,
            IMAGE_IMPORT_PARAMETER,
        )
        return self._schedule_catalog_scan(
            f"root-parameter:{requested_root.casefold()}",
            candidate,
            lambda: self._merge_captured_imports_into_scan(
                _load_project_catalog(requested_root, previous),
                captured_import_value,
            ),
            failure_state=previous,
        )

    def _apply_import_value(self, value: Any) -> Dict[str, Any]:
        state = self._current_state()
        input_identity = _canonical_import_input_identity(value)
        last_identity = getattr(self, "_hmb_last_applied_import_identity", None)
        if input_identity == last_identity:
            # A fresh empty node is already authoritative. A hydrated state with
            # stale live rows is the sole empty-input exception and must still
            # execute once to remove them.
            if _flatten_import_values(value) or not _state_has_live_imports(state):
                return state
        if not _flatten_import_values(value):
            self._replace_import_media({})
            published = self._publish_state(_remove_live_imports(state))
            self._hmb_last_applied_import_identity = input_identity
            return published
        try:
            state, media_by_uid = _merge_import_input(state, value)
            self._replace_import_media(media_by_uid)
            published = self._publish_state(state)
            # A non-empty aggregate that normalized to no concrete media is an
            # incomplete/unsupported host snapshot. Never latch it as success.
            if media_by_uid:
                self._hmb_last_applied_import_identity = input_identity
            else:
                self._hmb_last_applied_import_identity = None
            return published
        except Exception as exc:
            self._hmb_last_applied_import_identity = None
            state = dict(state)
            state["error"] = f"IMAGE_IMPORT_IN: {exc}"
            _diagnostic_exception("Image import failed", exc)
            return self._publish_state(state)

    @staticmethod
    def _merge_captured_imports_into_scan(
        state: Dict[str, Any],
        import_value: Any,
    ) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
        if not _flatten_import_values(import_value):
            return state, None
        merged, media_by_uid = _merge_import_input(state, import_value)
        return merged, media_by_uid

    def _compute_manifest_poll(
        self,
        state: Dict[str, Any],
        import_value: Any = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
        """Compute a shared-manifest refresh without publishing from a worker."""
        normalized = _normalize_state(state)
        if not normalized.get("project_root"):
            return normalized, None
        catalog = _discover_project_catalog(normalized.get("catalog_root"))
        selected = _match_catalog_project(
            catalog["projects"],
            previous_path=normalized.get("project_root"),
            previous_uid=normalized.get("project_uid"),
            previous_project_id=normalized.get("project_id"),
        )
        if selected is None:
            raise ValueError(
                "The selected project is no longer available in the active project catalog."
            )
        current_signature = _asset_manifest_signature(Path(selected["path"]))
        if current_signature == _clean(normalized.get("manifest_signature")):
            self._hmb_last_manifest_poll_error = ""
            return normalized, None

        refreshed_scan = _scan_project_assets(selected["path"])
        refreshed = _merge_scan_with_state(refreshed_scan, normalized)
        refreshed["catalog_root"] = catalog["catalog_root"]
        refreshed["projects"] = catalog["projects"]
        if _flatten_import_values(import_value):
            refreshed, media_by_uid = _merge_import_input(
                refreshed,
                import_value,
            )
        else:
            media_by_uid = None
        self._hmb_last_manifest_poll_error = ""
        return refreshed, media_by_uid

    def _apply_manifest_poll(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility entry point; interactive polls use the worker path."""
        normalized = _normalize_state(state)
        try:
            refreshed, media_by_uid = self._compute_manifest_poll(
                normalized,
                _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER),
            )
            if refreshed == normalized:
                return normalized
            if media_by_uid is not None:
                self._replace_import_media(media_by_uid)
            return self._publish_state(refreshed)
        except Exception as exc:
            message = _clean(exc)
            if message != self._hmb_last_manifest_poll_error:
                _diagnostic_exception("Shared manifest auto-sync failed", exc)
                self._hmb_last_manifest_poll_error = message
            # Keep the last verified snapshot and outputs intact while a share
            # is offline or another client is midway through a bad write.
            return normalized

    def _apply_widget_state(self, value: Any) -> Dict[str, Any]:
        state = _normalize_state(value)
        thumbnail_request = dict(state.get("thumbnail_request") or {})
        state["thumbnail_request"] = {}
        manifest_poll_received = bool(self._hmb_manifest_poll_received)
        self._hmb_manifest_poll_received = False
        manifest_poll_requested = bool(self._hmb_manifest_poll_pending)
        self._hmb_manifest_poll_pending = False
        disconnect_import_uid = _normalize_disconnect_import_uid(
            state.get("disconnect_import_uid")
        )
        state["disconnect_import_uid"] = ""
        if disconnect_import_uid:
            try:
                authoritative_matches = [
                    asset
                    for asset in state.get("assets", [])
                    if _clean(asset.get("source_uid")) == disconnect_import_uid
                    and _clean(asset.get("source_kind")) == "user"
                    and _non_negative_int(asset.get("import_index")) > 0
                ]
                if (
                    len(authoritative_matches) != 1
                    or disconnect_import_uid not in self._hmb_import_media_by_uid
                ):
                    raise RuntimeError(
                        "The requested external image is no longer an active "
                        "IMAGE_IMPORT_IN source."
                    )
                _disconnect_import_connection(self, disconnect_import_uid)

                # DeleteConnectionRequest is authoritative.  Its removal hook
                # normally refreshes the ParameterList synchronously; this
                # exact-UID filter also prevents a successful graph deletion
                # from briefly repainting the stale card during host updates.
                state = self._current_state()
                state["disconnect_import_uid"] = ""
                state["assets"] = [
                    dict(asset)
                    for asset in state.get("assets", [])
                    if not (
                        _clean(asset.get("source_kind")) == "user"
                        and _clean(asset.get("source_uid"))
                        == disconnect_import_uid
                    )
                ]
                remaining_media = dict(self._hmb_import_media_by_uid)
                remaining_media.pop(disconnect_import_uid, None)
                self._replace_import_media(remaining_media)
                state["scan_revision"] = _non_negative_int(
                    state.get("scan_revision")
                ) + 1
                state["error"] = ""
                return self._publish_state(state)
            except Exception as exc:
                state["error"] = f"IMAGE_IMPORT_IN disconnect: {exc}"
                _diagnostic_warning("External image disconnect rejected", exc)
                return self._publish_state(state)
        registration_request = dict(state.get("asset_registration_request") or {})
        state["asset_registration_request"] = {}
        if registration_request:
            request_snapshot = _normalize_asset_registration_request(
                registration_request
            )
            if not request_snapshot:
                state["asset_registration_result"] = {
                    "request_id": _clean(registration_request.get("request_id")),
                    "ok": False,
                    "asset_library_id": _clean(
                        registration_request.get("asset_library_id")
                    ),
                    "message": "Asset registration request is incomplete.",
                }
                state["error"] = (
                    "Asset registration: Asset registration request is incomplete."
                )
                return self._publish_state(state)

            # The request itself is only an intent.  Keep the last verified
            # catalog and outputs visible while copy/fsync/manifest locking and
            # the authoritative single-row patch are owned by this worker.
            state["asset_registration_result"] = {}
            captured_import_value = _get_parameter_raw(
                self,
                IMAGE_IMPORT_PARAMETER,
            )
            captured_import_media = dict(self._hmb_import_media_by_uid)

            def register_and_patch() -> Any:
                registered = _apply_asset_registration(
                    state,
                    request_snapshot,
                    captured_import_media,
                )
                if not _flatten_import_values(captured_import_value):
                    return registered
                return _merge_import_input(registered, captured_import_value)

            return self._schedule_catalog_scan(
                (
                    f"registration:{_clean(request_snapshot.get('project_uid'))}:"
                    f"{_clean(request_snapshot.get('request_id'))}"
                ),
                state,
                register_and_patch,
                failure_state=state,
                result_merger=lambda result, base, live: (
                    _merge_async_registration_result_with_live_state(
                        result,
                        base,
                        live,
                        request_snapshot,
                    )
                ),
            )
        refresh_requested = _non_negative_int(
            state.get("refresh_revision")
        ) > _non_negative_int(self._hmb_refresh_revision)
        requested_catalog = (
            _project_root_text(state.get("catalog_root"))
            or str(DEFAULT_PROJECTS_ROOT)
        )
        current_catalog = (
            _project_root_text(
                _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
            )
            or str(DEFAULT_PROJECTS_ROOT)
        )
        captured_import_value = _get_parameter_raw(
            self,
            IMAGE_IMPORT_PARAMETER,
        )
        if requested_catalog.casefold() != current_catalog.casefold():
            return self._schedule_catalog_scan(
                f"catalog:{requested_catalog.casefold()}",
                state,
                lambda: self._merge_captured_imports_into_scan(
                    _load_project_catalog(requested_catalog, state),
                    captured_import_value,
                ),
                failure_state={
                    **state,
                    "catalog_root": current_catalog.replace("\\", "/"),
                },
            )
        if refresh_requested:
            return self._schedule_catalog_scan(
                f"refresh:{requested_catalog.casefold()}:{_non_negative_int(state.get('refresh_revision'))}",
                state,
                lambda: self._merge_captured_imports_into_scan(
                    _load_project_catalog(
                        requested_catalog,
                        state,
                        use_shared_cache=False,
                    ),
                    captured_import_value,
                ),
            )
        requested_path = _clean(state.get("project_root")).replace("\\", "/")
        selected_record = next(
            (
                item
                for item in state["projects"]
                if _clean(item.get("path")).casefold()
                == requested_path.casefold()
            ),
            None,
        )
        expected_uid = (
            _clean(selected_record.get("project_uid"))
            if isinstance(selected_record, dict)
            else ""
        )
        if (
            requested_path
            and selected_record is not None
            and _clean(state.get("project_uid")) != expected_uid
        ):
            return self._schedule_catalog_scan(
                f"project:{requested_path.casefold()}:{expected_uid}",
                state,
                lambda: self._merge_captured_imports_into_scan(
                    _select_catalog_project(state, requested_path),
                    captured_import_value,
                ),
            )
        if manifest_poll_received:
            if not manifest_poll_requested:
                return state
            return self._schedule_catalog_scan(
                f"manifest:{requested_path.casefold()}:{_clean(state.get('manifest_signature'))}",
                state,
                lambda: self._compute_manifest_poll(
                    state,
                    captured_import_value,
                ),
            )
        if thumbnail_request:
            self._ensure_thumbnail_runtime_state()
            with self._hmb_thumbnail_lock:
                thumbnail_worker_active = bool(
                    self._hmb_thumbnail_pending_key
                )
            if not thumbnail_worker_active:
                return self._schedule_thumbnail_hydration(
                    state,
                    thumbnail_request,
                    candidate_normalized=True,
                    request_normalized=True,
                )
            # A repeated presentation request may ride along with a newer
            # selection/order edit while the single worker is active. Ignore
            # only the thumbnail intent; semantic output/reconcile below must
            # still observe that live edit immediately.
        normalized = self._sync_output(state)
        # Search, language, folder, and display edits must not scan the flow.
        # Advertise only when the bounded catalog visible to peers changed;
        # lifecycle reloads and process() retain their force-style paths.
        catalog_identity = _shot_routing_catalog_identity(normalized)
        if catalog_identity != getattr(
            self, "_hmb_last_reconciled_shot_catalog_identity", ""
        ):
            self._reconcile_hmb_shot_routing(catalog_identity)
        return normalized

    def _apply_thumbnail_bridge_request(self, value: Any) -> None:
        self._consume_pending_catalog_probe_result()
        bridge = _normalize_thumbnail_bridge(value)
        if (
            bridge.get("operation") == CATALOG_PROBE_OPERATION
            and bridge.get("phase") == "request"
            and _clean(bridge.get("request_id"))
        ):
            current = self._current_state()
            runtime_id = self._thumbnail_runtime_id(current)
            if _clean(bridge.get("runtime_instance_id")) != runtime_id:
                return
            if (
                _clean(bridge.get("project_uid"))
                != _clean(current.get("project_uid"))
                or (
                    _clean(bridge.get("project_cache_uid"))
                    and _clean(bridge.get("project_cache_uid"))
                    != _clean(current.get("project_cache_uid"))
                )
                or _clean(bridge.get("project_root")).replace("\\", "/").casefold()
                != _clean(current.get("project_root")).replace("\\", "/").casefold()
                or _clean(bridge.get("manifest_signature"))
                != _clean(current.get("manifest_signature"))
                or (
                    _clean(bridge.get("folder_signature"))
                    and _clean(bridge.get("folder_signature"))
                    != _clean(current.get("folder_signature"))
                )
                or _non_negative_int(bridge.get("scan_revision"))
                != _non_negative_int(current.get("scan_revision"))
            ):
                return
            self._schedule_catalog_probe(bridge, current)
            return
        if (
            bridge.get("operation") != "hydrate"
            or bridge.get("phase") != "request"
            or not _clean(bridge.get("request_id"))
        ):
            return
        current = self._current_state()
        runtime_id = self._thumbnail_runtime_id(current)
        if _clean(bridge.get("runtime_instance_id")) != runtime_id:
            return
        if (
            _clean(bridge.get("project_uid")) != _clean(current.get("project_uid"))
            or (
                _clean(bridge.get("project_cache_uid"))
                and _clean(bridge.get("project_cache_uid"))
                != _clean(current.get("project_cache_uid"))
            )
            or _clean(bridge.get("manifest_signature"))
            != _clean(current.get("manifest_signature"))
            or _non_negative_int(bridge.get("scan_revision"))
            != _non_negative_int(current.get("scan_revision"))
        ):
            return
        canonical_ids = {
            _clean(asset.get("asset_library_id"))
            for asset in current.get("assets", [])
            if isinstance(asset, dict)
            and _clean(asset.get("source_kind")).casefold() == "project"
            and _clean(asset.get("asset_library_id"))
        }
        requested_ids = list(bridge.get("asset_library_ids", []))
        if not requested_ids or any(item not in canonical_ids for item in requested_ids):
            return
        request = {
            "runtime_instance_id": runtime_id,
            "request_id": bridge["request_id"],
            "project_uid": current["project_uid"],
            "project_cache_uid": current["project_cache_uid"],
            "manifest_signature": current["manifest_signature"],
            "scan_revision": current["scan_revision"],
            "asset_library_ids": requested_ids,
        }
        current_result = _normalize_thumbnail_result(
            current.get("thumbnail_result")
        )
        if (
            not bool(current.get("thumbnail_busy"))
            and current_result.get("request_id") == request["request_id"]
            and current_result.get("project_uid") == request["project_uid"]
            and current_result.get("project_cache_uid")
            == request["project_cache_uid"]
            and current_result.get("manifest_signature")
            == request["manifest_signature"]
            and _non_negative_int(current_result.get("scan_revision"))
            == _non_negative_int(request["scan_revision"])
        ):
            # Idempotent result retrieval. The browser watchdog may repeat the
            # exact compact request if its first response was lost during a
            # mount/update race. Re-publish the already completed envelope;
            # never decode again or create a duplicate hydration worker.
            self._publish_thumbnail_bridge_result(current, request)
            return
        self._schedule_thumbnail_hydration(
            current,
            request,
            compact_bridge=True,
            candidate_normalized=True,
            request_normalized=True,
        )

    def before_value_set(self, parameter: Any, value: Any) -> Any:
        if not bool(getattr(self, "_hmb_state_syncing", False)) and not bool(
            getattr(self, "_hmb_restoring_widget_state", False)
        ):
            self._consume_pending_catalog_scan_result()
            self._consume_pending_thumbnail_result()
            self._consume_pending_catalog_probe_result()
        name = _clean(getattr(parameter, "name", ""))
        if name == WIDGET_STATE_PARAMETER:
            raw_state = dict(_parse_mapping(value))
            poll_nonce = _clean(raw_state.pop("__hmb_manifest_poll_nonce", ""))[:128]
            # Poll flags describe this exact value-set only.  In particular,
            # never leave a pending flag behind when an unchanged canonical
            # value is suppressed by the host and no post-set hook follows.
            self._hmb_manifest_poll_received = False
            self._hmb_manifest_poll_pending = False
            if not poll_nonce:
                if self._widget_state_is_stale(raw_state):
                    return self._hmb_last_accepted_widget_state
                raw_state = self._preserve_newer_thumbnail_baseline(raw_state)
                normalized = _normalize_state(raw_state)
                self._accept_widget_state_baseline(normalized)
                return _json_text(normalized)

            current_raw = dict(
                _parse_mapping(
                    _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
                )
            )
            # Older tests/hosts may not expose the pre-set value.  A full
            # legacy poll payload remains a valid fallback, while lightweight
            # polls merge only their identity fields into this authoritative
            # current snapshot and never normalize a client-sent catalog.
            candidate = _normalize_state(current_raw or raw_state)
            if poll_nonce == getattr(self, "_hmb_last_manifest_poll_nonce", ""):
                return _json_text(candidate)
            self._hmb_last_manifest_poll_nonce = poll_nonce

            identity_matches = True
            for field in (
                "catalog_root",
                "project_root",
                "project_id",
                "project_uid",
                "manifest_signature",
            ):
                supplied = _clean(raw_state.get(field))
                if not supplied:
                    continue
                authoritative = _clean(candidate.get(field))
                if field in {"catalog_root", "project_root"}:
                    supplied = _project_root_text(supplied).replace("\\", "/").casefold()
                    authoritative = (
                        _project_root_text(authoritative)
                        .replace("\\", "/")
                        .casefold()
                    )
                if supplied != authoritative:
                    identity_matches = False
                    break
            if not identity_matches:
                return _json_text(candidate)

            # Filesystem probes can block for seconds on an unavailable UNC
            # share. Always force a lightweight value change here; the exact
            # signature/discovery/scan work is generation-owned by the worker.
            if _clean(candidate.get("project_root")):
                candidate["scan_revision"] = (
                    _non_negative_int(candidate.get("scan_revision")) + 1
                )
                self._hmb_manifest_poll_received = True
                self._hmb_manifest_poll_pending = True
            return _json_text(_normalize_state(candidate))
        if name == PROJECT_ROOT_PARAMETER:
            return _project_root_text(value)
        if name == THUMBNAIL_PATCH_PARAMETER:
            return _normalize_thumbnail_bridge(value)
        return value

    def after_value_set(self, parameter: Any, value: Any) -> Any:
        result = None
        try:
            parent = getattr(super(), "after_value_set", None)
            if callable(parent):
                result = parent(parameter, value)
        except Exception as exc:
            _diagnostic_exception("Parent after_value_set failed", exc)
        if self._hmb_state_syncing or self._hmb_thumbnail_bridge_syncing:
            return result
        name = _clean(getattr(parameter, "name", ""))
        if name in {
            PROJECT_ROOT_PARAMETER,
            IMAGE_IMPORT_PARAMETER,
            WIDGET_STATE_PARAMETER,
        }:
            self._hmb_hydration_adopted = True
        _begin_image_output_side_effect_callback(self)
        try:
            if name == PROJECT_ROOT_PARAMETER and not self._hmb_root_syncing:
                self._schedule_catalog_root_change(value)
            elif name == IMAGE_IMPORT_PARAMETER:
                self._apply_import_value(value)
            elif name == WIDGET_STATE_PARAMETER:
                if (
                    not self._hmb_state_syncing
                    and not self._hmb_restoring_widget_state
                    and self._widget_state_is_stale(value)
                ):
                    # A host may assign the raw Parameter and call this hook with
                    # skip_before_value_set=True. Restore the accepted B snapshot
                    # before any output or filesystem side effect can observe A.
                    self._restore_accepted_widget_state()
                    return result
                if not self._hmb_state_syncing and not self._hmb_restoring_widget_state:
                    self._accept_widget_state_baseline(value)
                self._apply_widget_state(value)
            elif name == THUMBNAIL_PATCH_PARAMETER:
                self._apply_thumbnail_bridge_request(value)
        finally:
            _end_image_output_side_effect_callback(self)
        return result

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        result = None
        try:
            result = super().after_incoming_connection(
                source_node,
                source_parameter,
                target_parameter,
            )
        except Exception:
            result = None
        try:
            if _is_image_import_parameter(target_parameter):
                self._hmb_hydration_adopted = True
                # ParameterList owns the authoritative aggregate.  Read it
                # after the framework has installed the new edge instead of
                # replacing the whole list with only the newly connected
                # source value.
                value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
                if not _flatten_import_values(value):
                    # Local-validation/older-host fallback for a first
                    # connection whose aggregate has not been exposed yet.
                    source_name = _clean(getattr(source_parameter, "name", ""))
                    sentinel = object()
                    source_value: Any = sentinel
                    outputs = getattr(source_node, "parameter_output_values", {})
                    if source_name and source_name in outputs:
                        source_value = outputs[source_name]
                    elif source_name:
                        values = getattr(source_node, "parameter_values", {})
                        if source_name in values:
                            source_value = values[source_name]
                        else:
                            try:
                                source_value = source_node.get_parameter_value(source_name)
                            except Exception:
                                source_value = sentinel
                    if source_value is not sentinel:
                        value = source_value
                self._apply_import_value(value)
        except Exception as exc:
            _diagnostic_exception("Incoming image import synchronization failed", exc)
        return result

    def after_incoming_connection_removed(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        result = None
        try:
            result = super().after_incoming_connection_removed(
                source_node,
                source_parameter,
                target_parameter,
            )
        except Exception:
            result = None
        try:
            if _is_image_import_parameter(target_parameter):
                # One ParameterList edge was removed.  The framework has
                # already rebuilt the aggregate value, so preserve every
                # remaining source and remove only the media no longer present.
                self._apply_import_value(
                    _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
                )
        except Exception as exc:
            _diagnostic_exception("Image import disconnect synchronization failed", exc)
        return result

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            parent = getattr(super(), "after_deserialize", None)
            if callable(parent):
                result = parent(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent after_deserialize failed", exc)
        # Deserialization may replace both widget state and ParameterList values
        # without replaying their normal hooks. Force the hydrated aggregate to
        # establish a fresh per-instance identity on its first event.
        self._hmb_last_applied_import_identity = None
        self._ensure_parameters()
        self._ensure_scan_runtime_state()
        self._ensure_thumbnail_runtime_state()
        self._ensure_catalog_probe_runtime_state()
        with self._hmb_scan_lock:
            # Constructor/initial-scan workers belong to the pre-hydration
            # snapshot and must not overwrite the saved workflow or index.
            self._hmb_scan_generation += 1
            self._hmb_scan_pending_key = ""
            self._hmb_scan_pending_result = None
            self._hmb_scan_thread = None
        with self._hmb_thumbnail_lock:
            self._hmb_thumbnail_generation += 1
            self._hmb_thumbnail_pending_key = ""
            self._hmb_thumbnail_pending_result = None
            self._hmb_thumbnail_thread = None
            self._hmb_thumbnail_queued_bridge_request = None
        with self._hmb_catalog_probe_lock:
            self._hmb_catalog_probe_generation += 1
            self._hmb_catalog_probe_pending_key = ""
            self._hmb_catalog_probe_pending_result = None
            self._hmb_catalog_probe_thread = None
        self._hmb_initial_catalog_scan_pending = False
        self._hmb_fresh_registration_scan_key = ""
        saved_state = dict(self._current_state())
        saved_assets: List[Dict[str, Any]] = []
        retired_thumbnail_url = False
        for raw_asset in saved_state.get("assets", []):
            asset = dict(raw_asset)
            if (
                _clean(asset.get("thumbnail_url"))
                and not _thumbnail_url_is_live(
                    asset.get("media_signature"),
                    asset.get("thumbnail_url"),
                )
            ):
                asset["thumbnail_url"] = ""
                retired_thumbnail_url = True
            saved_assets.append(asset)
        saved_state["assets"] = saved_assets
        if retired_thumbnail_url:
            saved_state["thumbnail_revision"] = _non_negative_int(
                saved_state.get("thumbnail_revision")
            ) + 1
        # A serialized busy/request/result belongs to a worker that no longer
        # exists after restart. Never let that transient snapshot permanently
        # block the new process's visible-window scheduler.
        saved_state["thumbnail_busy"] = False
        saved_state["thumbnail_request"] = {}
        saved_state["thumbnail_result"] = {}
        saved_root = _project_root_text(saved_state.get("catalog_root"))
        parameter_root = _project_root_text(
            _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
        )
        # Deserialization is a retained-mode/UI callback.  Pick the saved
        # candidate without probing it here; discovery and asset walking run
        # in the generation-owned worker below.
        root_value = saved_root or parameter_root or str(DEFAULT_PROJECTS_ROOT)
        if root_value:
            self._hmb_root_syncing = True
            try:
                _set_parameter_value(self, PROJECT_ROOT_PARAMETER, root_value)
            finally:
                self._hmb_root_syncing = False
        import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
        candidate_state = dict(saved_state)
        candidate_state["catalog_root"] = root_value.replace("\\", "/")
        indexed_state = _read_catalog_index(
            saved_state.get("project_root"),
            saved_state,
        )
        if indexed_state is not None:
            indexed_state["catalog_root"] = root_value.replace("\\", "/")
            indexed_state, indexed_media = self._merge_captured_imports_into_scan(
                indexed_state,
                import_value,
            )
            if isinstance(indexed_media, dict):
                self._replace_import_media(indexed_media)
            self._publish_state(indexed_state)
        else:
            self._schedule_catalog_scan(
                (
                    f"deserialize:{root_value.casefold()}:"
                    f"{_non_negative_int(saved_state.get('scan_revision'))}"
                ),
                candidate_state,
                lambda: self._merge_captured_imports_into_scan(
                    _load_project_catalog(root_value, saved_state),
                    import_value,
                ),
                failure_state=candidate_state,
            )
        self._hmb_hydration_adopted = True
        self._schedule_post_hydration_shot_reconcile()
        return result

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        """Reconcile surviving Shot participants exactly once on deletion."""

        prepare = getattr(
            _hmb_shot_routing,
            "prepare_node_deletion",
            None,
        )
        if callable(prepare) and not bool(
            getattr(self, "_hmb_node_deleted", False)
        ):
            try:
                prepare(self)
            except Exception as exc:
                _diagnostic_exception(
                    "ImageAsset reset handoff preparation failed",
                    exc,
                )
        self._ensure_scan_runtime_state()
        self._ensure_thumbnail_runtime_state()
        first_delete = not bool(getattr(self, "_hmb_node_deleted", False))
        if first_delete:
            self._hmb_node_deleted = True
            self._hmb_reserved_shot_catalog_identity = ""
            self._hmb_fresh_registration_scan_key = ""
            release = getattr(
                _hmb_shot_routing,
                "release_node_lifecycle",
                None,
            )
            if callable(release):
                try:
                    release(self)
                except Exception as exc:
                    _diagnostic_exception(
                        "ImageAsset lifecycle release failed",
                        exc,
                    )
            with self._hmb_scan_lock:
                self._hmb_scan_generation += 1
                self._hmb_scan_pending_key = ""
                self._hmb_scan_pending_result = None
                self._hmb_scan_thread = None
            with self._hmb_thumbnail_lock:
                self._hmb_thumbnail_generation += 1
                self._hmb_thumbnail_pending_key = ""
                self._hmb_thumbnail_pending_result = None
                self._hmb_thumbnail_thread = None
                self._hmb_thumbnail_queued_bridge_request = None
            with self._hmb_catalog_probe_lock:
                self._hmb_catalog_probe_generation += 1
                self._hmb_catalog_probe_pending_key = ""
                self._hmb_catalog_probe_pending_result = None
                self._hmb_catalog_probe_thread = None
        if first_delete and not bool(
            getattr(self, "_hmb_deletion_reconcile_called", False)
        ):
            self._hmb_deletion_reconcile_called = True
            try:
                scheduler = getattr(
                    _hmb_shot_routing,
                    "schedule_post_deletion_reconcile",
                    None,
                )
                if callable(scheduler):
                    scheduler(self)
            except Exception as exc:
                _diagnostic_exception(
                    "Post-deletion Shot routing schedule failed", exc
                )
        if bool(getattr(self, "_hmb_delete_parent_called", False)):
            return None
        self._hmb_delete_parent_called = True
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None

    def process(self) -> None:
        self._hmb_hydration_adopted = True
        self._consume_pending_catalog_scan_result()
        self._consume_pending_thumbnail_result()
        probe_consumer = getattr(self, "_consume_pending_catalog_probe_result", None)
        if callable(probe_consumer):
            probe_consumer()
        self._ensure_parameters()
        root_value = (
            _project_root_text(
                _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
            )
            or str(DEFAULT_PROJECTS_ROOT)
        )
        current = self._current_state()
        requested_catalog_identity = root_value.replace("\\", "/").rstrip("/").casefold()
        current_catalog_identity = (
            _project_root_text(current.get("catalog_root"))
            .replace("\\", "/")
            .rstrip("/")
            .casefold()
        )
        catalog_root_matches = bool(
            requested_catalog_identity
            and requested_catalog_identity == current_catalog_identity
        )
        project_belongs_to_catalog = _state_project_belongs_to_catalog(
            current,
            root_value,
        )
        if (
            catalog_root_matches
            and project_belongs_to_catalog
            and _state_catalog_is_current(current)
        ):
            state = current
        elif catalog_root_matches and project_belongs_to_catalog:
            indexed = _read_catalog_index(current.get("project_root"), current)
            if indexed is not None:
                state = self._publish_state(indexed)
            else:
                state = self._load_catalog(root_value)
        else:
            # PROJECT_ROOT is the process-time authority.  A programmatic host
            # update may arrive without the retained widget callback, so an
            # otherwise-current snapshot/index from the previous root must not
            # be adopted here.
            state = self._load_catalog(root_value)
        import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
        if _flatten_import_values(import_value):
            self._apply_import_value(import_value)
        synchronized = self._sync_output(self._current_state(), force=True)
        self._reconcile_hmb_shot_routing(
            _shot_routing_catalog_identity(synchronized)
        )
        return None
