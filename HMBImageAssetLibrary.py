from __future__ import annotations

from collections import OrderedDict
from array import array
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

from _hmb_deletion_guard import hmb_binding_mutation


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
IMAGE_BASH_IMAGES_OUTPUT_PARAMETER = "IMAGE_BASH_IMAGES_OUT"
IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER = "IMAGE_BASH_CONTEXT_OUT"
IMAGE_BASH_CONTEXT_SCHEMA = "hmb-image-bash-inputs-v1"
IMAGE_BASH_WORKSPACE_REQUEST_SCHEMA = "hmb-image-bash-workspace-edit-v1"
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
IMAGE_ASSET_EDIT_SCHEMA = "hmb-image-asset-edit-v1"
IMAGE_ASSET_EDIT_FIELDS = (
    "root_edit_enabled", "selected_folder_path", "expanded_folders",
    "selected_main_type", "selected_sub_type", "selected_source_view",
    "search", "language", "asset_view_mode", "refresh_revision",
    "thumbnail_request", "asset_registration_request", "asset_cleanup_request",
    "disconnect_import_uid", "shot_routing", "shot_hierarchy", "shot_hierarchy_request",
    "image_bash_workspace", "image_bash_active", "image_bash_workspace_request",
)
MAX_UI_EDIT_REVISION = (1 << 53) - 1
OUTPUT_VERSION = 4
IMAGE_BINDING_CAPABILITY_SCHEMA = "hmb-image-source-binding-capabilities"
IMAGE_BINDING_CAPABILITY_VERSION = 1
MAX_ASSETS = 5000
MAX_FOLDERS = 5000
MAX_PROJECTS = 500
MAX_SELECTED_IMAGES = 50
MAX_SHOTS = 5
MAX_SHOT_IMAGES = MAX_SELECTED_IMAGES
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
PRODUCTION_PROJECTS_ROOT = "//192.168.200.19/v/projects"
_RETIRED_PROJECTS_ROOT = "//fin-rcomp1/Composite_Team/projects_AI"


def _relocate_image_project_path(value: Any) -> str:
    """Replace retired saved addresses in memory; never read the old storage."""
    text = str(value or "").strip()
    path = text.replace("\\", "/")
    prefix = _RETIRED_PROJECTS_ROOT
    if path.casefold() == prefix.casefold() or path.casefold().startswith(prefix.casefold() + "/"):
        parts = path[len(prefix):].strip("/").split("/")
        if not parts[0]:
            return PRODUCTION_PROJECTS_ROOT
        if any(part in (".", "..") for part in parts):
            return text
        return "/".join((PRODUCTION_PROJECTS_ROOT, parts[0], "Ai_Ct_image", *parts[1:]))
    if "://" in path or any(part in (".", "..") for part in path.split("/")):
        return text
    flat = re.fullmatch(r"(.*?/projects)/ai_ct_image(?:/([^/]+)(/.*)?)?/?", path, re.IGNORECASE)
    if flat:
        base, show, suffix = flat.groups()
        return base if not show else base + "/" + show + "/Ai_Ct_image" + (suffix or "")
    nested = re.fullmatch(r"(.*?/projects/([^/]+)/ai_ct_image)/([^/]+)(/.*)?", path, re.IGNORECASE)
    if nested and nested[2].casefold() == nested[3].casefold():
        return nested[1] + (nested[4] or "")
    return text


DEFAULT_PROJECTS_ROOT = Path(
    _relocate_image_project_path(os.environ.get(
        "HMB_IMAGE_PROJECTS_ROOT",
        PRODUCTION_PROJECTS_ROOT,
    ))
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
            return _relocate_image_project_path(current)
        if isinstance(current, bytes):
            return _relocate_image_project_path(current.decode("utf-8", errors="replace"))
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
        return _relocate_image_project_path(os.path.expandvars(text))
    return ""


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class _ImageCatalogSearchIndex:
    """Immutable, background-built substring index; no files or SDK access."""

    def __init__(self, assets: Sequence[Dict[str, Any]], cancelled: Callable[[], bool] = lambda: False):
        fields = ("asset_id", "image_name", "relative_path", "image_main_type", "image_sub_type", "source_kind", "asset_library_id")
        self.assets = tuple({key: _clean(asset.get(key)) for key in fields} for asset in assets)
        self.texts: List[str] = []
        self.postings: Dict[str, Any] = {}
        self.folder_counts: Dict[str, int] = {}
        self.stats = {"records": len(assets), "queries": 0, "candidate_checks": 0}
        for number, asset in enumerate(self.assets):
            if number % 256 == 0 and cancelled():
                raise InterruptedError("Catalog index retired")
            text = "\n".join(_clean(asset.get(key)).lower() for key in
                ("asset_id", "image_name", "relative_path", "image_main_type", "image_sub_type"))
            self.texts.append(text)
            for gram in set(text[pos:pos + 3] for pos in range(max(0, len(text) - 2))):
                self.postings.setdefault(gram, array("I")).append(number)
            if asset.get("source_kind") == "project":
                parts = _clean(asset.get("relative_path")).replace("\\", "/").split("/")[:-1]
                for depth in range(len(parts) + 1):
                    folder = "/".join(parts[:depth])
                    self.folder_counts[folder] = self.folder_counts.get(folder, 0) + 1

    def query(self, request: Dict[str, Any], cancelled: Callable[[], bool] = lambda: False) -> Dict[str, Any]:
        needle = str(request.get("query") or "").strip().lower()
        folder = _clean(request.get("folder")).replace("\\", "/").strip("/").lower()
        source = "user" if request.get("source_view") == "user" else "project"
        candidates: Any = range(len(self.assets))
        if len(needle) >= 3:
            grams = {needle[pos:pos + 3] for pos in range(len(needle) - 2)}
            candidates = min((self.postings.get(gram, ()) for gram in grams), key=len)
        matches = []
        for position, number in enumerate(candidates):
            if position % 256 == 0 and cancelled():
                raise InterruptedError("Catalog query retired")
            asset = self.assets[number]
            relative = _clean(asset.get("relative_path")).replace("\\", "/").lower()
            if asset.get("source_kind") != source or (source == "project" and folder
                    and not (relative == folder or relative.startswith(folder + "/"))):
                continue
            self.stats["candidate_checks"] += 1
            if not needle or needle in self.texts[number]:
                matches.append(number)
        self.stats["queries"] += 1
        limit = min(80, max(1, _non_negative_int(request.get("limit")) or 80))
        offset = min(_non_negative_int(request.get("offset")), ((len(matches) - 1) // limit) * limit if matches else 0)
        return {"total": len(matches), "offset": offset, "limit": limit,
            "asset_library_ids": [_clean(self.assets[number].get("asset_library_id")) for number in matches[offset:offset + limit]]}


def _default_thumbnail_bridge(runtime_instance_id: Any = "") -> Dict[str, Any]:
    return {
        "schema": THUMBNAIL_BRIDGE_SCHEMA,
        "version": THUMBNAIL_BRIDGE_VERSION,
        "runtime_instance_id": _clean(runtime_instance_id),
        "operation": "idle",
        "phase": "idle",
        "request_id": "",
        "catalog_page_version": 1,
    }


def _normalize_thumbnail_bridge(value: Any) -> Dict[str, Any]:
    raw = _parse_mapping(value)
    bridge = _default_thumbnail_bridge(raw.get("runtime_instance_id"))
    operation = _clean(raw.get("operation")).casefold()
    phase = _clean(raw.get("phase")).casefold()
    if operation in {"cgt_catalog", "cgt_confirm", "cgt_cancel"} and phase in {"request", "result"}:
        bridge.update(operation=operation, phase=phase)
        for key in ("request_id", "session_id", "project_identity"):
            bridge[key] = str(raw.get(key) or "")[:4096 if key == "project_identity" else 128]
        bridge["cgt_project_id"] = _clean(raw.get("cgt_project_id"))[:128]
        if operation == "cgt_confirm" and phase == "request":
            command = raw.get("hierarchy_request")
            if isinstance(command, dict) and len(_json_text(command)) <= 32768:
                bridge["hierarchy_request"] = command
        if phase == "result":
            bridge["outcome"] = _clean(raw.get("outcome"))[:40]
            bridge["state"] = raw.get("state") if isinstance(raw.get("state"), dict) else {}
        return bridge
    if operation == "catalog_page" and phase in {"request", "result"}:
        for field in ("request_id", "session_id", "project_uid", "project_cache_uid", "manifest_signature", "folder_signature"):
            bridge[field] = _clean(raw.get(field))[:256]
        bridge.update(operation=operation, phase=phase,
            scan_revision=_non_negative_int(raw.get("scan_revision")),
            import_revision=_non_negative_int(raw.get("import_revision")),
            sequence=_non_negative_int(raw.get("sequence")),
            query=str(raw.get("query") or "")[:256],
            folder=_clean(raw.get("folder")).replace("\\", "/").strip("/")[:4096],
            source_view="user" if raw.get("source_view") == "user" else "project",
            offset=_non_negative_int(raw.get("offset")), limit=min(80, max(1, _non_negative_int(raw.get("limit")) or 80)))
        if phase == "result":
            bridge["state"] = raw.get("state") if isinstance(raw.get("state"), dict) else {}
            bridge["outcome"] = _clean(raw.get("outcome"))[:32]
        return bridge
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
    """Preserve authored taxonomy and derive a wire pair only when exact."""
    source = raw if isinstance(raw, dict) else {}
    main_type = _clean(source.get("image_main_type"))
    sub_type = _clean(source.get("image_sub_type"))
    wire_pair = image_taxonomy_wire_pair(main_type, sub_type)
    source_type, scope_candidate = (
        wire_pair
        if wire_pair is not None
        else (IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED, "")
    )
    custom_source_type = _clean(source.get("custom_source_type"))
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


def _image_project_child(root: Path, name: str) -> Path | None:
    """Find one regular child directory, without following a project redirect."""
    candidate = root / name
    try:
        if candidate.is_dir() and not _is_reparse_point(candidate):
            candidate.resolve().relative_to(root.resolve())
            return candidate.resolve()
        # Windows shares are case insensitive. Keep that contract in portable
        # tests and on case-sensitive project mounts as well.
        for child in root.iterdir():
            if child.name.casefold() != name.casefold():
                continue
            if child.is_dir() and not _is_reparse_point(child):
                child.resolve().relative_to(root.resolve())
                return child.resolve()
    except (FileNotFoundError, NotADirectoryError, ValueError):
        return None
    return None


def _nested_image_project_root(show: Path) -> Path | None:
    """A show's own Ai_Ct_image is its image boundary, never its pipelines."""
    return _image_project_child(show, "Ai_Ct_image")


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
    own_nested_root = None if root.name.casefold() == "projects" else _nested_image_project_root(root)
    if own_nested_root is not None:
        project_paths = [own_nested_root]
    elif root.name.casefold() == "ai_ct_image" or (root.name.casefold() != "projects" and _looks_like_direct_project(root)):
        project_paths = [root]
    else:
        project_paths = []
        try:
            candidates = list(root.iterdir())
        except Exception as exc:
            raise ValueError(f"Unable to enumerate projects in {root}: {exc}") from exc
        nested_paths: Dict[str, Path] = {}
        for candidate in candidates:
            if len(nested_paths) >= MAX_PROJECTS:
                break
            # The retired global catalog is not a project and is never probed.
            if candidate.name.casefold() == "ai_ct_image":
                continue
            try:
                if not candidate.is_dir() or _is_reparse_point(candidate):
                    continue
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except (FileNotFoundError, NotADirectoryError, ValueError):
                continue
            nested = _nested_image_project_root(resolved)
            if nested is not None:
                nested_paths[_project_identity_key(_project_id(nested))] = nested
        project_paths.extend(nested_paths.values())
        # Preserve unrelated explicit flat catalogs. Official projects catalogs
        # only discover <show>/Ai_Ct_image; old global storage is never scanned.
        flat_candidates = candidates if not nested_paths and root.name.casefold() != "projects" else []
        for candidate in flat_candidates:
            if len(project_paths) >= MAX_PROJECTS:
                break
            try:
                if (not candidate.is_dir() or candidate.name.startswith(".")
                        or _is_reparse_point(candidate)):
                    continue
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except (FileNotFoundError, NotADirectoryError, ValueError):
                continue
            if _project_identity_key(_project_id(resolved)) not in nested_paths:
                project_paths.append(resolved)
        project_paths.sort(key=lambda value: _natural_key(_project_id(value)))

    projects = [
        {
            "project_id": _project_id(path),
            "project_uid": _project_uid(path),
            "name": _project_id(path),
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
    *,
    defer_thumbnail: bool = False,
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
    elif reference.lower().startswith(("http://", "https://", "blob:")):
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
        # File identity must not depend on a transient SMB/mapped-drive outage.
        # Keep the same canonical path/UID even while thumbnail I/O is unavailable.
        if resolved.suffix.casefold() in IMAGE_EXTENSIONS and _canonical_import_path(reference):
            media_ref_kind = "path"
            display_reference = str(resolved).replace("\\", "/")
            identity_material = display_reference.casefold()
            image_name = resolved.stem
            extension = resolved.suffix.casefold()
            media_value = display_reference
            try:
                if resolved.is_file():
                    width, height = _asset_dimensions(resolved)
                    thumbnail_path = resolved
            except OSError:
                pass
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
        if thumbnail_path is not None and not defer_thumbnail
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


def _canonical_import_path(value: Any) -> str:
    text = _clean(value)
    if not text or "{" in text:
        return ""
    if (re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", text)
        and not re.match(r"^[a-zA-Z]:[\\/]", text)
        and not text.lower().startswith("file:")):
        return ""
    try:
        return os.path.normpath(os.path.abspath(os.path.expanduser(
            _decode_file_uri(text)
        ))).replace("\\", "/").casefold()
    except (OSError, ValueError):
        return ""


def _normalize_import_input(
    value: Any,
    previous_assets: Sequence[Dict[str, Any]],
    *,
    defer_thumbnail: bool = False,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    previous = {
        _clean(asset.get("source_uid") or asset.get("asset_library_id")): asset
        for asset in previous_assets
        if isinstance(asset, dict)
        and _clean(asset.get("source_kind")) == "user"
    }
    previous_paths = {
        _canonical_import_path(asset.get("path")): asset
        for asset in previous.values()
        if _canonical_import_path(asset.get("path"))
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
        imported = _import_record(
            raw,
            index,
            resolved_embedded,
            defer_thumbnail=defer_thumbnail,
        )
        if imported is None:
            continue
        record, media_value = imported
        # Saved workflows may contain the old availability-dependent URL UID.
        # Keep that exact addressed image stable; do not relink by file name.
        prior_path = previous_paths.get(_canonical_import_path(record.get("path")))
        if prior_path is not None and record.get("media_ref_kind") == "path":
            record["source_uid"] = _clean(prior_path.get("source_uid")) or record["source_uid"]
            record["asset_library_id"] = record["source_uid"]
            if defer_thumbnail and _thumbnail_url_is_live(
                prior_path.get("media_signature"),
                prior_path.get("thumbnail_url"),
            ):
                # Keep a loaded card painted while the new input snapshot is
                # validated in the background. A failed recheck clears it.
                record["media_signature"] = _clean(prior_path.get("media_signature"))
                record["thumbnail_url"] = _clean(prior_path.get("thumbnail_url"))
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
    return root.parent.name if root.name.casefold() == "ai_ct_image" else root.name


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


def _manifest_asset_relative_path(root: Path, record: Dict[str, Any]) -> str:
    """Read moved registrations against the new media root without rewriting JSON."""
    roots = [root.as_posix()]
    # The production mapped drive and canonical UNC denote the same share.
    # Do not infer aliases for arbitrary user drives or for other projects.
    production_share = "//192.168.200.19/v"
    for value in tuple(roots):
        if value.casefold().startswith(production_share.casefold() + "/"):
            roots.append("P:" + value[len(production_share):])
        elif value.casefold().startswith("p:/projects/"):
            roots.append(production_share + value[2:])
    for field in ("path", "relative_path"):
        text = _relocate_image_project_path(record.get(field)).replace("\\", "/")
        if not text:
            continue
        if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
            match = next((prefix for prefix in roots
                          if text.casefold().startswith(prefix.rstrip("/").casefold() + "/")), None)
            if match is None:
                continue
            text = text[len(match.rstrip("/")) + 1:]
        parts = text.split("/")
        if (not text or any(not part or part in (".", "..") for part in parts)
                or ":" in text or text.startswith("/")):
            continue
        return text
    return ""


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
                # An old registration file is a read-only source during a
                # move; include its actual location in cache invalidation.
                (manifest_path.relative_to(root).as_posix()
                 if manifest_path.is_relative_to(root)
                 else "legacy:" + manifest_path.as_posix()).casefold(),
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
            if current == root and root.name.casefold() == "ai_ct_image" and name.casefold() == root.parent.name.casefold():
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
    # A subsequent explicit Add writes only the new project's canonical JSON.
    # Carry old absolute-path registrations as project-relative copies so the
    # old read-only file is neither changed nor duplicated as unregistered media.
    records = [
        {**record, "path": relative}
        if isinstance(record, dict)
        and (relative := _manifest_asset_relative_path(root.resolve(), record))
        else record
        for record in records
    ]
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
            relative_text = _manifest_asset_relative_path(resolved_root, raw)
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


def _refresh_manifest_regular_stat(path: Path) -> os.stat_result:
    """Unlike a best-effort catalog probe, never hide inaccessible/reparse paths."""
    facts = path.lstat()
    if stat.S_ISLNK(facts.st_mode) or int(
        getattr(facts, "st_file_attributes", 0)
    ) & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        raise ValueError(f"Refresh cannot verify a symlink or reparse point: {path}")
    return facts


def _refresh_manifest_document(
    root: Path,
) -> tuple[Path | None, bytes, Any, List[Any]]:
    """Read without creating metadata or silently ignoring a permissions error."""
    metadata = root / ASSET_METADATA_DIRECTORY_NAME
    try:
        metadata_facts = _refresh_manifest_regular_stat(metadata)
    except FileNotFoundError:
        metadata_exists = False
    else:
        metadata_exists = True
        if not stat.S_ISDIR(metadata_facts.st_mode):
            raise ValueError("Refresh requires .json to be a regular directory.")
    candidates = (
        [metadata / name for name in MANIFEST_NAMES] if metadata_exists else []
    ) + [root / name for name in MANIFEST_NAMES]
    inherited = _existing_asset_manifest_path(root)
    if inherited is not None and inherited not in candidates:
        candidates.append(inherited)
    for candidate in candidates:
        try:
            facts = _refresh_manifest_regular_stat(candidate)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(facts.st_mode):
            raise ValueError(f"Refresh manifest is not a regular file: {candidate}")
        if facts.st_size > 2 * 1024 * 1024:
            raise ValueError("Refresh manifest exceeds 2 MiB.")
        original = candidate.read_bytes()
        if len(original) > 2 * 1024 * 1024:
            raise ValueError("Refresh manifest exceeds 2 MiB.")
        payload = json.loads(original.decode("utf-8-sig"))
        records = payload.get("assets") if isinstance(payload, dict) else payload
        if not isinstance(records, list) or len(records) > MAX_ASSETS:
            raise ValueError("Refresh requires a complete, bounded assets list.")
        records = [
            {**record, "path": relative}
            if isinstance(record, dict)
            and (relative := _manifest_asset_relative_path(root, record))
            else record
            for record in records
        ]
        return candidate, original, payload, records
    return None, b"", None, []


def _refresh_manifest_relative_path(record: Any) -> str:
    if not isinstance(record, dict):
        raise ValueError("Refresh cannot clean a malformed manifest record.")
    raw = record.get("path") or record.get("relative_path")
    if not isinstance(raw, str):
        raise ValueError("Refresh manifest record has no relative image path.")
    relative = raw.replace("\\", "/")
    parts = relative.split("/")
    if (
        not relative
        or relative.startswith("/")
        or ":" in relative
        or any(
            not part or part.startswith(".") or part.endswith((".", " "))
            for part in parts
        )
        or Path(relative).suffix.casefold() not in IMAGE_EXTENSIONS
    ):
        raise ValueError(f"Refresh cannot verify this manifest image path: {relative}")
    return relative


def _audit_project_manifest_refresh(root: Path) -> Dict[str, Any]:
    """Explicit Refresh only: compare a stable, fully accessible image inventory.

    Ordinary polling deliberately remains best effort. This separate audit is
    fail-closed because a missing inventory row alone never authorizes deletion.
    It does not create folders, rewrite JSON, or read image pixels.
    """
    review: Dict[str, Any] = {
        "project_root": str(root).replace("\\", "/"),
        "manifest_path": "",
        "manifest_digest": "",
        "inventory_digest": "",
        "missing_records": [],
        "missing_paths": [],
        "unregistered_paths": [],
        "registered_count": 0,
        "file_count": 0,
        "missing_count": 0,
        "unregistered_count": 0,
        "safe_to_clean": False,
        "error": "",
    }
    try:
        root = Path(_project_root_text(root)).expanduser()
        root_facts = _refresh_manifest_regular_stat(root)
        if not stat.S_ISDIR(root_facts.st_mode):
            raise ValueError("Refresh project root is not a regular directory.")
        root = root.resolve(strict=True)
        review["project_root"] = root.as_posix()
        source_path, original, _payload, records = _refresh_manifest_document(root)
        review["manifest_path"] = source_path.as_posix() if source_path else ""
        review["manifest_digest"] = hashlib.sha256(original).hexdigest()
        review["registered_count"] = len(records)
        registered: Dict[str, tuple[str, Dict[str, Any]]] = {}
        for record in records:
            relative = _refresh_manifest_relative_path(record)
            key = relative.casefold()
            if key in registered:
                raise ValueError(f"Refresh found duplicate registration paths: {relative}")
            registered[key] = (relative, record)

        def directory_identity(facts: os.stat_result) -> tuple[int, int, int, int]:
            return (facts.st_dev, facts.st_ino, facts.st_mtime_ns, facts.st_ctime_ns)

        directories: Dict[Path, tuple[int, int, int, int]] = {}
        inventory: Dict[str, tuple[str, int, int, int, int]] = {}
        pending = [root]
        while pending:
            directory = pending.pop()
            facts = _refresh_manifest_regular_stat(directory)
            if not stat.S_ISDIR(facts.st_mode):
                raise ValueError(f"Refresh folder changed during inspection: {directory}")
            directories[directory] = directory_identity(facts)
            if len(directories) - 1 > MAX_FOLDERS:
                raise ValueError("Refresh exceeded the complete-folder inspection limit.")
            with os.scandir(directory) as entries:
                for entry in entries:
                    if directory == root and root.name.casefold() == "ai_ct_image" and entry.name.casefold() == root.parent.name.casefold():
                        continue
                    path = Path(entry.path)
                    entry_facts = _refresh_manifest_regular_stat(path)
                    # Match the normal catalog's intentional hidden-file scope.
                    # Registered hidden paths were rejected above, not deleted.
                    if entry.name.startswith("."):
                        continue
                    if stat.S_ISDIR(entry_facts.st_mode):
                        pending.append(path)
                        if len(directories) + len(pending) - 1 > MAX_FOLDERS:
                            raise ValueError("Refresh exceeded the complete-folder inspection limit.")
                    elif path.suffix.casefold() in IMAGE_EXTENSIONS:
                        if not stat.S_ISREG(entry_facts.st_mode):
                            raise ValueError(f"Refresh image is not a regular file: {path}")
                        relative = path.relative_to(root).as_posix()
                        key = relative.casefold()
                        if key in inventory:
                            raise ValueError(f"Refresh found case-colliding image paths: {relative}")
                        inventory[key] = (
                            relative,
                            entry_facts.st_size,
                            entry_facts.st_mtime_ns,
                            entry_facts.st_dev,
                            entry_facts.st_ino,
                        )
                        if len(inventory) > MAX_ASSETS:
                            raise ValueError("Refresh exceeded the complete-image inspection limit.")
        review["file_count"] = len(inventory)
        missing_records: List[Dict[str, Any]] = []
        missing_paths: List[str] = []
        for key, (relative, record) in registered.items():
            if key in inventory:
                continue
            # A full successful walk must agree with a direct lookup. A
            # permission/network error, changed folder, or restored file aborts.
            try:
                _refresh_manifest_regular_stat(root.joinpath(*relative.split("/")))
            except FileNotFoundError:
                missing_records.append(copy.deepcopy(record))
                missing_paths.append(relative)
            else:
                raise ValueError(f"Refresh image changed during inspection: {relative}")
        for directory, before in directories.items():
            after = _refresh_manifest_regular_stat(directory)
            if not stat.S_ISDIR(after.st_mode) or directory_identity(after) != before:
                raise ValueError("Project folders changed during Refresh; please refresh again.")
        after_path, after_bytes, _after_payload, _after_records = _refresh_manifest_document(root)
        if after_path != source_path or after_bytes != original:
            raise ValueError("Registration JSON changed during Refresh; please refresh again.")
        # Final enumeration confirms that the share/root did not disappear
        # while ENOENT candidates were being checked.
        with os.scandir(root) as entries:
            for _entry in entries:
                pass
        unregistered = sorted(
            (row[0] for key, row in inventory.items() if key not in registered),
            key=str.casefold,
        )
        inventory_payload = {
            "files": [inventory[key] for key in sorted(inventory)],
            "folders": sorted(
                directory.relative_to(root).as_posix() for directory in directories
            ),
        }
        review.update({
            "inventory_digest": hashlib.sha256(
                json.dumps(inventory_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "missing_records": missing_records,
            "missing_paths": missing_paths,
            "unregistered_paths": unregistered,
            "missing_count": len(missing_paths),
            "unregistered_count": len(unregistered),
            "safe_to_clean": source_path is None or source_path.is_relative_to(root),
        })
    except Exception as exc:
        review["safe_to_clean"] = False
        review["error"] = str(exc) or type(exc).__name__
    return review


def _clean_project_manifest_refresh(
    review: Dict[str, Any],
    is_current: Callable[[], bool],
) -> Dict[str, Any]:
    """Remove only confirmed missing registrations; never delete media files."""
    if not isinstance(review, dict) or review.get("safe_to_clean") is not True:
        raise ValueError("Refresh inspection is incomplete; no registrations were removed.")
    root = Path(_clean(review.get("project_root")))
    if not root.is_absolute() or not _clean(review.get("manifest_path")):
        raise ValueError("No verified registration JSON is available for cleanup.")
    if not is_current():
        raise ValueError("Refresh confirmation expired; please refresh again.")
    with _asset_manifest_lock(root):
        with _asset_manifest_process_lock(root):
            if not is_current():
                raise ValueError("Refresh confirmation expired while waiting for the project lock.")
            current = _audit_project_manifest_refresh(root)
            if current.get("safe_to_clean") is not True:
                raise ValueError(current.get("error") or "Project inspection could not be completed.")
            for field in (
                "project_root", "manifest_path", "manifest_digest", "inventory_digest",
                "missing_paths", "missing_records",
            ):
                if current.get(field) != review.get(field):
                    raise ValueError("Project files or registration JSON changed; please refresh and confirm again.")
            missing_keys = {
                _refresh_manifest_relative_path(record).casefold()
                for record in current["missing_records"]
            }
            if not missing_keys:
                return {**current, "cleaned_count": 0, "backup_path": ""}
            manifest_path, original, payload, records = _refresh_manifest_document(root)
            if (
                manifest_path is None
                or manifest_path.as_posix() != current["manifest_path"]
                or hashlib.sha256(original).hexdigest() != current["manifest_digest"]
            ):
                raise ValueError("Registration JSON changed; please refresh again.")
            remaining = [
                record for record in records
                if _refresh_manifest_relative_path(record).casefold() not in missing_keys
            ]
            if isinstance(payload, dict):
                updated: Any = dict(payload)
                updated["assets"] = remaining
            else:
                updated = remaining
            encoded = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if len(encoded) > 2 * 1024 * 1024:
                raise ValueError("Updated registration JSON would exceed 2 MiB.")
            metadata = _asset_metadata_directory(root, create=True)
            backup = metadata / f"hmb_image_assets.refresh-{time.time_ns()}-{uuid.uuid4().hex}.json.bak"
            temporary = manifest_path.with_name(f".{manifest_path.name}.refresh-{uuid.uuid4().hex}.tmp")
            replace_attempted = False
            try:
                if not is_current():
                    raise ValueError("Refresh confirmation expired before cleanup.")
                with backup.open("xb") as handle:
                    handle.write(original)
                    handle.flush()
                    os.fsync(handle.fileno())
                with temporary.open("xb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                latest_path, latest_bytes, _latest_payload, _latest_records = _refresh_manifest_document(root)
                if latest_path != manifest_path or latest_bytes != original:
                    raise ValueError("Registration JSON changed before cleanup; please refresh again.")
                for relative in current["missing_paths"]:
                    try:
                        _refresh_manifest_regular_stat(root.joinpath(*relative.split("/")))
                    except FileNotFoundError:
                        pass
                    else:
                        raise ValueError("An image was restored before cleanup; please refresh again.")
                with os.scandir(root) as entries:
                    for _entry in entries:
                        pass
                if not is_current():
                    raise ValueError("Refresh confirmation expired before saving; nothing was removed.")
                replace_attempted = True
                os.replace(temporary, manifest_path)
            except Exception as exc:
                # SMB may commit a rename before its acknowledgement is lost.
                # Retain rollback bytes whenever the commit outcome is unknown.
                for staged in ((temporary,) if replace_attempted else (temporary, backup)):
                    try:
                        staged.unlink(missing_ok=True)
                    except OSError:
                        pass
                if replace_attempted:
                    raise RuntimeError(
                        f"Registration cleanup save could not be confirmed. Refresh to verify the current JSON; backup retained: {backup}. {exc}"
                    ) from exc
                raise
            _invalidate_asset_manifest_cache(root)
            _invalidate_project_cache_uid(root)
            # Rotate only this feature's own regular backups, never arbitrary
            # user backup files or legacy manifests. A completed write remains
            # successful even if a later network outage delays backup pruning.
            backup_warning = ""
            try:
                backups = []
                with os.scandir(metadata) as entries:
                    for entry in entries:
                        if re.fullmatch(r"hmb_image_assets\.refresh-\d+-[0-9a-f]{32}\.json\.bak", entry.name):
                            candidate = Path(entry.path)
                            facts = _refresh_manifest_regular_stat(candidate)
                            if not stat.S_ISREG(facts.st_mode):
                                raise ValueError("Refresh backup is not a regular file.")
                            backups.append(candidate)
                for obsolete in sorted(backups, key=lambda path: path.name, reverse=True)[3:]:
                    obsolete.unlink()
            except Exception as exc:
                backup_warning = f"Registration cleanup completed; older backup pruning was deferred: {exc}"
            result = _audit_project_manifest_refresh(root)
            result.update({
                "cleaned_count": len(missing_keys),
                "backup_path": backup.as_posix(),
                "backup_warning": backup_warning,
            })
            return result


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
            if current == root and root.name.casefold() == "ai_ct_image" and name.casefold() == root.parent.name.casefold():
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
    path = _relocate_image_project_path(raw.get("path") or raw.get("asset_path")).replace("\\", "/")
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
    raw_colors = raw.get("color_pick_candidates")
    if not isinstance(raw_colors, (list, tuple)):
        raw_colors = taxonomy["color_pick_candidates"]
    colors = [
        _clean(value)
        for value in raw_colors
        if _clean(value)
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
        "thumbnail_url": _relocate_image_project_path(raw.get("thumbnail_url")),
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
        "label": (project_id or Path(project_root).name) if project_root else "Select Project",
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
        path = _relocate_image_project_path(raw.get("path")).replace("\\", "/")
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


def _normalize_image_bash_workspace(value: Any, channel_uuid: str) -> Dict[str, Any]:
    if not value:
        return {}
    raw = value if isinstance(value, dict) else {}
    identity = _uuid_text(raw.get("workspace_id"))
    if not identity:
        raise ValueError("Image Bash 작업 공간에는 고유한 ID가 필요합니다.")
    instances: List[Dict[str, str]] = []
    seen: set[str] = set()
    for row in raw.get("instances", []) if isinstance(raw.get("instances"), list) else []:
        if not isinstance(row, dict) or set(row) != {"instance_id", "source_uid"}:
            raise ValueError("Image Bash 이미지 인스턴스 구성이 올바르지 않습니다.")
        instance, source = _uuid_text(row.get("instance_id")), _clean(row.get("source_uid"))
        if not instance or not source or len(source) > 512 or instance in seen:
            raise ValueError("Image Bash 이미지마다 고유한 인스턴스 ID가 필요합니다.")
        instances.append({"instance_id": instance, "source_uid": source})
        seen.add(instance)
    if len(instances) > MAX_SELECTED_IMAGES:
        raise ValueError(f"Image Bash에는 최대 {MAX_SELECTED_IMAGES}개 이미지를 배치할 수 있습니다.")
    return {"workspace_id": identity, "revision": min(MAX_UI_EDIT_REVISION, _non_negative_int(raw.get("revision"))),
            "instances": instances}


def _normalize_image_bash_workspace_request(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    fields = {"schema", "version", "operation", "request_id", "workspace_id", "expected_revision"}
    if (not isinstance(value, dict) or set(value) != fields
            or value.get("schema") != IMAGE_BASH_WORKSPACE_REQUEST_SCHEMA or type(value.get("version")) is not int
            or value["version"] != 1 or value.get("operation") != "create"
            or not _uuid_text(value.get("request_id")) or not _uuid_text(value.get("workspace_id"))
            or type(value.get("expected_revision")) is not int or not 0 <= value["expected_revision"] <= MAX_UI_EDIT_REVISION):
        raise ValueError("Image Bash 추가 요청이 올바르지 않습니다.")
    return copy.deepcopy(value)


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


def _normalize_asset_refresh_review(value: Any) -> Dict[str, Any]:
    """Presentation only: cleanup authority is never restored from widget JSON."""
    source = _parse_mapping(value)
    token = _clean(source.get("request_id"))[:128]
    if not token:
        return {}
    result = {
        "request_id": token,
        "project_root": _clean(source.get("project_root")).replace("\\", "/"),
        "project_id": _clean(source.get("project_id"))[:256],
        "status": _clean(source.get("status")) if source.get("status") in (
            "review", "cleaned", "error"
        ) else "review",
        "safe_to_clean": source.get("safe_to_clean") is True,
        "error": _clean(source.get("error"))[:4096],
        "backup_path": _clean(source.get("backup_path"))[:4096],
    }
    for key in ("registered_count", "file_count", "missing_count",
                "unregistered_count", "cleaned_count"):
        result[key] = _non_negative_int(source.get(key))
    for key in ("missing_paths", "unregistered_paths"):
        values = source.get(key)
        result[key] = [
            _clean(item)[:4096] for item in values if isinstance(item, str) and _clean(item)
        ][:MAX_ASSETS] if isinstance(values, list) else []
    return result


def _normalize_cgt_work_start_notice(value: Any) -> Dict[str, Any]:
    source = _parse_mapping(value)
    if (source.get("schema") != "hmb-cgt-work-start-notice-v1"
            or source.get("status") not in {"queued", "running", "completed", "partial", "failed", "unknown"}
            or re.fullmatch(r"[a-zA-Z0-9_.:-]{1,128}", _clean(source.get("request_id"))) is None):
        return {}
    result = {"schema": "hmb-cgt-work-start-notice-v1", "status": source["status"],
              "request_id": source["request_id"]}
    for name in ("updated_count", "already_work_count", "skipped_count", "failed_count"):
        result[name] = min(5, _non_negative_int(source.get(name)))
    return result


def _default_state() -> Dict[str, Any]:
    state = {
        "schema": STATE_SCHEMA,
        "version": STATE_VERSION,
        "edit_transport_schema": IMAGE_ASSET_EDIT_SCHEMA,
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
        "asset_refresh_review": {},
        "cgt_work_start_notice": {},
        "asset_cleanup_request": {},
        "disconnect_import_uid": "",
        "warnings": [],
        "error": "",
        "status": {
            "asset_count": 0,
            "selected_count": 0,
        },
    }
    state["shot_routing"] = _normalize_shot_routing({}, [])
    state["shot_hierarchy"] = {}
    state["image_bash_workspace"] = {}
    state["image_bash_active"] = False
    state["image_bash_workspace_request"] = {}
    return state


def _normalize_state(value: Any) -> Dict[str, Any]:
    source = _parse_mapping(value)
    state = _default_state()
    catalog_root = (
        _relocate_image_project_path(source.get("catalog_root")).replace("\\", "/")
        or str(DEFAULT_PROJECTS_ROOT).replace("\\", "/")
    )
    projects = _normalize_project_catalog(source.get("projects"))
    project_root = _relocate_image_project_path(source.get("project_root")).replace("\\", "/")
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
            "asset_refresh_review": _normalize_asset_refresh_review(
                source.get("asset_refresh_review")
            ),
            "asset_cleanup_request": {
                "request_id": _clean(
                    _parse_mapping(source.get("asset_cleanup_request")).get("request_id")
                )[:128]
            } if _clean(_parse_mapping(source.get("asset_cleanup_request")).get("request_id")) else {},
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
    state["shot_hierarchy"] = _hmb_shot_routing.validate_shot_hierarchy_routing(
        source.get("shot_hierarchy"), state["shot_routing"]
    )
    state["cgt_work_start_notice"] = _normalize_cgt_work_start_notice(source.get("cgt_work_start_notice"))
    state["image_bash_workspace"] = _normalize_image_bash_workspace(source.get("image_bash_workspace"),
        state["shot_routing"]["channel_uuid"])
    state["image_bash_active"] = source.get("image_bash_active") is True
    state["image_bash_workspace_request"] = _normalize_image_bash_workspace_request(source.get("image_bash_workspace_request"))
    binding = state["shot_hierarchy"]
    if binding and binding["project_identity"]:
        previous_identity = binding["project_identity"]
        previous_key = _hmb_shot_routing.hierarchy_project_key({"project_root": previous_identity})
        canonical_identity = _relocate_image_project_path(previous_identity).replace("\\", "/").rstrip("/").lower()
        if (canonical_identity != previous_key
                and canonical_identity == _hmb_shot_routing.hierarchy_project_key(state)):
            # A retired address of this same project is metadata, not a new
            # binding. Preserve its IDs, revision, CGT scope and membership.
            binding["project_identity"] = canonical_identity
    if (binding and not binding["project_identity"]
            and _hmb_shot_routing.hierarchy_project_key(state)
            and all(row["origin"] == "manual" for row in binding["members"])):
        # Locally named Shots may be added before selecting a project. Adopt
        # only that previously empty scope on the first project selection;
        # never relabel an authenticated CGT or another project's binding.
        # Slot UUIDs, selected media, authored names and downstream results
        # remain untouched by this metadata-only transition.
        binding["project_identity"] = _hmb_shot_routing.hierarchy_project_key(state)
        binding["revision"] = min((1 << 53) - 1, binding["revision"] + 1)
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
    "shot_hierarchy",
    "image_bash_workspace",
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
    "image_bash_workspace",
    "image_bash_active",
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
    "shot_hierarchy",
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
    previous_state = _normalize_state(previous_state)
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
    previous_catalog = _project_root_text(previous_state.get("catalog_root")).replace("\\", "/").rstrip("/").casefold()
    discovered_catalog = _project_root_text(catalog.get("catalog_root")).replace("\\", "/").rstrip("/").casefold()
    if (not selected_path and previous_catalog and previous_catalog == discovered_catalog
            and _clean(previous_state.get("project_root"))):
        raise ValueError("The selected ImageAsset project is no longer available in this catalog. Reconnect the project and retry.")
    if not selected_path and len(catalog["projects"]) == 1:
        only_project = catalog["projects"][0]
        direct_root = Path(catalog["catalog_root"])
        nested_root = None if direct_root.name.casefold() == "projects" else _nested_image_project_root(direct_root)
        if (_clean(only_project.get("path")).casefold() == _clean(
            catalog["catalog_root"]
        ).casefold() or (nested_root is not None
                        and _clean(only_project.get("path")).casefold() == nested_root.as_posix().casefold())):
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


def _catalog_index_path_for_verified_uid(project_cache_uid: Any) -> Path:
    """Compute a local write path without revisiting the project filesystem."""

    identity = _valid_project_cache_uid(project_cache_uid)
    if not identity:
        raise ValueError("A verified project cache identity is required.")
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
        # Runtime writes follow worker-side identity verification.  In
        # particular, calculating this local filename must not stat/resolve an
        # unavailable UNC project again on a retained completion callback.
        index_path = _catalog_index_path_for_verified_uid(
            projection.get("project_cache_uid")
        )
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


def _prepare_catalog_scan_index(
    state: Dict[str, Any],
    *,
    normalized: bool = False,
) -> None:
    """Verify and persist scan facts on the filesystem worker, never the host loop.

    The identity supplied by a live widget edit is not write authority.  Confirm
    it against the actual project here; the read path independently verifies
    the catalog, project, manifest, folder signature and contained asset paths.
    A replaced project gets a different local filename, so a late old worker
    cannot overwrite that replacement's index.
    """

    normalized_state = state if normalized else _normalize_state(state)
    root_text = _clean(normalized_state.get("project_root"))
    identity = _valid_project_cache_uid(normalized_state.get("project_cache_uid"))
    if not root_text or not identity or _clean(normalized_state.get("error")):
        return
    try:
        if _project_cache_uid(Path(root_text)) != identity:
            return
        _write_catalog_index(normalized_state, normalized=True)
    except Exception as exc:
        # A local cache failure must not turn a successful catalog into an
        # offline/error result or delay the host loop with a retry.
        _diagnostic_warning("Local catalog index preparation failed", exc)


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
        project = Path(_project_root_text(project_text)).resolve()
        catalog = Path(catalog_text).resolve()
        if project == catalog or project.parent == catalog:
            return True
        try:
            parts = project.relative_to(catalog).parts
        except ValueError:
            return False
        keys = tuple(part.casefold() for part in parts)
        # One direct show/Ai_Ct_image boundary. Retired saved addresses are
        # replaced before this check; unrelated descendants stay out of scope.
        return bool(
            (len(keys) == 2 and keys[1] == "ai_ct_image")
            or (len(keys) == 1 and keys[0] == "ai_ct_image"
                and _project_id(project).casefold() == catalog.name.casefold())
        )
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
    workspace = copy.deepcopy(state.get("image_bash_workspace") or {})
    if workspace and any(row["source_uid"] == old_uid for row in workspace.get("instances", [])):
        for row in workspace["instances"]:
            if row["source_uid"] == old_uid:
                row["source_uid"] = new_uid
        workspace["revision"] = min(MAX_UI_EDIT_REVISION, _non_negative_int(workspace.get("revision")) + 1)
        state["image_bash_workspace"] = workspace
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
        authoritative_rows, _ = _normalize_import_input([media_value], [source_asset])
        authoritative_import = (authoritative_rows[0], media_value) if len(authoritative_rows) == 1 else None
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
    *,
    defer_thumbnail: bool = False,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    normalized = _normalize_state(state)
    if not _flatten_import_values(value):
        return normalized, {}
    imports, media_by_uid = _normalize_import_input(
        value,
        normalized["assets"],
        defer_thumbnail=defer_thumbnail,
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


def _hydrate_live_import_thumbnails(
    rows: Sequence[tuple[str, str]],
    is_current: Callable[[], bool],
) -> Dict[str, tuple[str, str, str]]:
    """Decode path previews off-thread; never use these as media validation."""

    results: Dict[str, tuple[str, str, str]] = {}
    for uid, path_text in rows:
        if not is_current():
            break
        signature = ""
        url = ""
        try:
            path, _size, _mtime_ns, signature = _asset_file_facts(
                Path(path_text)
            )
            url = _asset_thumbnail_url_for_media(path, uid, signature)
            if url:
                _resolved, _size, _mtime_ns, current_signature = (
                    _asset_file_facts(path)
                )
            else:
                current_signature = ""
            if current_signature != signature:
                signature = ""
                url = ""
        except Exception:
            signature = ""
            url = ""
        results[uid] = (path_text, signature, url)
    return results


def _merge_live_import_thumbnail_result(
    live_state: Dict[str, Any],
    results: Dict[str, tuple[str, str, str]],
) -> Dict[str, Any] | None:
    """Patch presentation only for the same still-connected input path."""

    merged = dict(live_state)
    assets: List[Dict[str, Any]] = []
    changed = False
    for raw_asset in live_state.get("assets", []):
        asset = dict(raw_asset)
        uid = _clean(asset.get("source_uid"))
        update = results.get(uid)
        if (
            update is not None
            and _clean(asset.get("source_kind")) == "user"
            and _non_negative_int(asset.get("import_index")) > 0
            and _clean(asset.get("media_ref_kind")) == "path"
            and _clean(asset.get("path")) == update[0]
        ):
            _path, signature, url = update
            if (
                _clean(asset.get("media_signature")) != signature
                or _clean(asset.get("thumbnail_url")) != url
            ):
                asset["media_signature"] = signature
                asset["thumbnail_url"] = url
                changed = True
        assets.append(asset)
    if not changed:
        return None
    merged["assets"] = assets
    merged["thumbnail_revision"] = (
        _non_negative_int(live_state.get("thumbnail_revision")) + 1
    )
    return _normalize_state(merged)


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
    previous_assets: Sequence[Dict[str, Any]] = (),
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
            imports, _media_by_uid = _normalize_import_input(source_value, previous_assets)
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
        node._current_state().get("assets", []),
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


def _import_connection_snapshot(node: Any) -> Any:
    from griptape_nodes.retained_mode.events.connection_events import (
        ListConnectionsForNodeRequest, ListConnectionsForNodeResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    node_name = _clean(getattr(node, "name", ""))
    if not node_name:
        raise RuntimeError("The Image Asset node has no graph identity.")
    result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=node_name))
    if not isinstance(result, ListConnectionsForNodeResultSuccess):
        raise RuntimeError("IMAGE_IMPORT_IN connections could not be inspected safely.")
    return result


def _ensure_import_child_removal_observers(node: Any) -> Dict[str, Any]:
    """Observe native removals before their nested disconnect callbacks run.

    A next-loop callback is not an operation-completion barrier: the native
    RemoveParameter handler may still be disconnecting its child on a worker.
    Only proven, successfully removed UUID children are idempotent here.
    """
    state = getattr(node, "_hmb_import_child_removal_state", None)
    if not isinstance(state, dict):
        state = {"lock": threading.RLock(), "active": {}, "retired": {}, "pending": {}, "generations": {}}
        node._hmb_import_child_removal_state = state
    state.setdefault("generations", {})
    try:
        from griptape_nodes.retained_mode.events.parameter_events import (
            RemoveParameterFromNodeRequest, RemoveParameterFromNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        manager = GriptapeNodes.EventManager()
        if state.get("manager") is manager:
            return state
        if not all(callable(getattr(manager, name, None)) for name in (
            "add_pre_dispatch_hook", "remove_pre_dispatch_hook",
            "add_post_dispatch_hook", "remove_post_dispatch_hook",
        )):
            return state
        owner_ref = weakref.ref(node)
        observer_owner = object()

        def before_remove(request: Any, _context: Any) -> Any:
            # Observer exceptions must never prevent unrelated host operations.
            try:
                if state.get("observer_owner") is not observer_owner:
                    return None
                owner = owner_ref()
                if (owner is None or not isinstance(request, RemoveParameterFromNodeRequest)
                    or _clean(getattr(request, "node_name", "")) != _clean(owner.name)
                    or not owner._scan_owner_is_current() or bool(getattr(owner, "lock", False))):
                    return None
                name = _clean(getattr(request, "parameter_name", ""))
                if not name or name == IMAGE_IMPORT_PARAMETER:
                    return None
                child = _get_parameter_obj(owner, name)
                with state["lock"]:
                    generation = state["generations"].get(name)
                    if child is None and generation is not None and (
                        state["retired"].get(name) is generation[1] or any(
                            entry[1] == name and entry[3] is generation[1]
                            for entry in state["active"].values()
                        )
                    ):
                        return RemoveParameterFromNodeResultSuccess(
                            result_details="The image input was already removed."
                        )
                    if child is not None and _is_image_import_parameter(child):
                        if generation is None or generation[0]() is not child:
                            generation = (weakref.ref(child), object())
                            state["generations"][name] = generation
                            state["retired"].pop(name, None)
                        state["active"][id(request)] = (request, name, generation[0], generation[1])
                    elif child is not None:
                        state["retired"].pop(name, None)
                        state["generations"].pop(name, None)
                    while len(state["generations"]) > MAX_SELECTED_IMAGES * 8:
                        oldest = next(iter(state["generations"]))
                        state["generations"].pop(oldest)
                        state["retired"].pop(oldest, None)
                return None
            except Exception:
                return None

        def after_remove(request: Any, result: Any) -> None:
            try:
                if state.get("observer_owner") is not observer_owner:
                    return
                with state["lock"]:
                    entry = state["active"].pop(id(request), None)
                    if entry is None or entry[0] is not request:
                        return
                    owner = owner_ref()
                    name = entry[1]
                    generation = state["generations"].get(name)
                    if (owner is not None and isinstance(result, RemoveParameterFromNodeResultSuccess)
                        and generation is not None and generation[1] is entry[3]
                        and _get_parameter_obj(owner, name) is None):
                        state["retired"][name] = entry[3]
                        while len(state["retired"]) > MAX_SELECTED_IMAGES * 8:
                            state["retired"].pop(next(iter(state["retired"])))
            except Exception:
                return

        manager.add_pre_dispatch_hook(before_remove)
        try:
            manager.add_post_dispatch_hook(RemoveParameterFromNodeRequest, after_remove)
        except Exception:
            manager.remove_pre_dispatch_hook(before_remove)
            return state

        def unregister() -> None:
            for remove, args in (
                (manager.remove_pre_dispatch_hook, (before_remove,)),
                (manager.remove_post_dispatch_hook, (RemoveParameterFromNodeRequest, after_remove)),
            ):
                try:
                    remove(*args)
                except Exception:
                    pass

        def finalize_unregister() -> None:
            # GC can run while the SDK snapshots hooks under its non-reentrant
            # pre/post-dispatch locks. Removing hooks on this thread deadlocks
            # the request that triggered collection. This short-lived worker
            # owns only callbacks/manager (the node is weak), requires no engine
            # loop, and may acquire the locks after the finalizer has returned.
            try:
                threading.Thread(target=unregister, name="HMBImageImportHookCleanup", daemon=True).start()
            except (RuntimeError, OSError):
                # Interpreter shutdown may refuse new threads. Weak-owner and
                # registration-token guards keep any remaining callback inert.
                pass

        previous_finalizer = state.get("finalizer")
        if callable(previous_finalizer):
            previous_finalizer()
        state["manager"] = manager
        state["observer_owner"] = observer_owner
        state["unregister"] = unregister
        state["finalizer"] = weakref.finalize(node, finalize_unregister)
    except Exception:
        # Older hosts retain explicit registration cleanup, but must not race a
        # native minus operation through an unobserved asynchronous callback.
        pass
    return state


def _release_import_child_removal_observers(node: Any) -> None:
    state = getattr(node, "_hmb_import_child_removal_state", None)
    if not isinstance(state, dict):
        return
    finalizer = state.get("finalizer")
    # Normal node deletion runs outside the dispatch-hook locks. Keep that
    # explicit cleanup synchronous, and detach the GC-only deferred fallback.
    state["observer_owner"] = None
    detach = getattr(finalizer, "detach", None)
    if callable(detach):
        detach()
    unregister = state.pop("unregister", None)
    if callable(unregister):
        unregister()
    elif callable(finalizer):
        finalizer()
    with state["lock"]:
        for key in ("active", "retired", "pending", "generations"):
            state[key].clear()
        state["manager"] = None


def _remove_import_child_parameter(node: Any, parameter_name: str) -> bool:
    """Remove only an empty, disconnected child; never its aggregate parent."""
    from griptape_nodes.retained_mode.events.parameter_events import (
        RemoveParameterFromNodeRequest, RemoveParameterFromNodeResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    name = _clean(parameter_name)
    if not name or name == IMAGE_IMPORT_PARAMETER:
        raise RuntimeError("The IMAGE_IMPORT_IN aggregate must not be removed.")
    if name not in _image_import_target_parameter_names(node):
        if _get_parameter_obj(node, name) is None:
            return False  # Already removed by the host's minus-button request.
        raise RuntimeError("The input is not an IMAGE_IMPORT_IN child.")
    child = _get_parameter_obj(node, name)
    if child is None or not _is_image_import_parameter(child):
        raise RuntimeError("The input no longer belongs to IMAGE_IMPORT_IN.")
    removal_state = _ensure_import_child_removal_observers(node)
    with removal_state["lock"]:
        if any(entry[1] == name for entry in removal_state["active"].values()):
            return False
    snapshot = _import_connection_snapshot(node)
    # Listing connections dispatches another host request. Its callbacks may
    # remove or replace this exact child before control returns here.
    if _get_parameter_obj(node, name) is not child:
        return False
    with removal_state["lock"]:
        if any(entry[1] == name for entry in removal_state["active"].values()):
            return False
    if any(_clean(getattr(edge, "target_parameter_name", "")) == name
           for edge in snapshot.incoming_connections) or any(
        _clean(getattr(edge, "source_parameter_name", "")) == name
        for edge in getattr(snapshot, "outgoing_connections", [])
    ):
        raise RuntimeError("The input is still connected; it was not removed.")
    if _flatten_import_values(_get_parameter_raw(node, name)):
        raise RuntimeError("The input still contains media; it was not removed.")
    previous_guard = bool(getattr(node, "_hmb_import_cleanup_active", False))
    node._hmb_import_cleanup_active = True
    try:
        result = GriptapeNodes.handle_request(RemoveParameterFromNodeRequest(
            node_name=_clean(getattr(node, "name", "")), parameter_name=name,
        ))
    finally:
        node._hmb_import_cleanup_active = previous_guard
    if not isinstance(result, RemoveParameterFromNodeResultSuccess):
        if _get_parameter_obj(node, name) is None:
            return False
        raise RuntimeError("Griptape could not remove the empty image input.")
    if name in _image_import_target_parameter_names(node):
        raise RuntimeError("The empty image input is still present.")
    return True


def _retire_registered_import_connection(
    node: Any, source_uid: str, target_parameter_name: str | None = None,
    *, previous_assets: Sequence[Dict[str, Any]] = (),
) -> bool:
    """Disconnect one proven image, verify it, then remove its exact UUID child."""
    from griptape_nodes.retained_mode.events.connection_events import (
        DeleteConnectionRequest, DeleteConnectionResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    targets = _image_import_target_parameter_names(node)
    if target_parameter_name:
        targets &= {_clean(target_parameter_name)}
    connection = _single_import_connection_for_uid(
        GriptapeNodes.NodeManager(), _import_connection_snapshot(node).incoming_connections,
        source_uid, targets, previous_assets,
    )
    name = _clean(connection.target_parameter_name)
    if name == IMAGE_IMPORT_PARAMETER:
        raise RuntimeError("A list-level image connection cannot be removed as one image input.")
    previous_guard = bool(getattr(node, "_hmb_import_cleanup_active", False))
    node._hmb_import_cleanup_active = True
    try:
        result = GriptapeNodes.handle_request(DeleteConnectionRequest(
            source_node_name=connection.source_node_name,
            source_parameter_name=connection.source_parameter_name,
            target_node_name=_clean(getattr(node, "name", "")),
            target_parameter_name=name,
        ))
        if not isinstance(result, DeleteConnectionResultSuccess):
            raise RuntimeError("Griptape could not disconnect the registered image.")
        return _remove_import_child_parameter(node, name)
    finally:
        node._hmb_import_cleanup_active = previous_guard


def _capture_import_registration_edges(node: Any, source_uid: str) -> List[tuple[Any, str, str]]:
    """Capture exact source objects and UUID slots, not mutable display numbers."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    captured = []
    targets = _image_import_target_parameter_names(node) - {IMAGE_IMPORT_PARAMETER}
    snapshot = _import_connection_snapshot(node)
    for edge in snapshot.incoming_connections:
        name = _clean(getattr(edge, "target_parameter_name", ""))
        if name not in targets:
            continue
        try:
            match = _single_import_connection_for_uid(
                GriptapeNodes.NodeManager(), [edge], source_uid, {name},
                node._current_state().get("assets", []),
            )
        except RuntimeError:
            # Multi-image edges must keep their other unregistered inputs.
            continue
        captured.append((
            GriptapeNodes.NodeManager().get_node_by_name(match.source_node_name),
            _clean(match.source_parameter_name), name,
        ))
    return captured


def _defer_empty_import_child_cleanup(node: Any, parameter_name: str) -> None:
    """Wait for a native minus request to finish before pruning a detached slot."""
    name = _clean(parameter_name)
    state = _ensure_import_child_removal_observers(node)
    if state.get("manager") is None:
        return
    child = _get_parameter_obj(node, name)
    if child is None:
        return
    child_ref = weakref.ref(child)
    with state["lock"]:
        if name in state["pending"] or any(entry[1] == name for entry in state["active"].values()):
            return
        state["pending"][name] = child_ref
    node_ref = weakref.ref(node)
    host_context = contextvars.copy_context()

    def cleanup() -> None:
        try:
            owner = node_ref()
            expected_child = child_ref()
            with state["lock"]:
                if state["pending"].get(name) is not child_ref:
                    return
            if (owner is None or not owner._scan_owner_is_current()
                or expected_child is None or _get_parameter_obj(owner, name) is not expected_child):
                return
            _remove_import_child_parameter(owner, name)
        except Exception as exc:
            _diagnostic_warning("Empty image input cleanup deferred", exc)
        finally:
            with state["lock"]:
                if state["pending"].get(name) is child_ref:
                    state["pending"].pop(name, None)

    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        loop = GriptapeNodes.EventManager().event_loop
        if loop is not None and loop.is_running() and not loop.is_closed():
            loop.call_soon_threadsafe(host_context.run, cleanup)
            return
    except Exception as exc:
        # No worker-thread graph mutation or nested parameter deletion fallback.
        _diagnostic_warning("Empty image input cleanup unavailable", exc)
    with state["lock"]:
        if state["pending"].get(name) is child_ref:
            state["pending"].pop(name, None)


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
                # Only a manifest-backed registration may carry an identity
                # handover. A frontend-edited alias cannot claim a Prompt row.
                "import_source_uid": _clean(
                    (manifest_records or {}).get(relative_path.casefold(), {}).get("import_source_uid")
                ) if relative_path else "",
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
                "import_source_uid": _clean(cached.get("import_source_uid")),
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
                "import_source_uid": _clean(resolved_item.get("import_source_uid")),
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
        "import_source_uid": _clean(resolved_item.get("import_source_uid")) if verified else "",
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
        "project_id": _clean(normalized.get("project_id")),
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
        "project_id": metadata_document["project_id"],
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
    "import_source_uid",
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


def _add_image_bash_outputs(node: Any) -> None:
    for name, kind, default in ((IMAGE_BASH_IMAGES_OUTPUT_PARAMETER, "list[ImageUrlArtifact]", []),
                                (IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER, "dict", {})):
        if not parameter_exists(node, name):
            kwargs = {"name": name, "type": kind, "output_type": kind, "default_value": default,
                "input_types": [], "allow_input": False, "allow_output": True, "allow_property": False,
                "settable": False, "ui_options": {"hide": True, "hide_property": True, "hide_handles": True,
                    "height": 1, "min_height": 0, "max_height": 1}}
            modes = _mode_set("OUTPUT")
            if modes is not None:
                kwargs["allowed_modes"] = modes
            _safe_add_parameter(node, **kwargs)


def _build_image_bash_outputs(state: Dict[str, Any], media_by_uid: Dict[str, Any] | None = None,
                              *, resolution_cache: Any = None, import_revision: int = 0,
                              force: bool = False) -> tuple[list[Any], Dict[str, Any]] | None:
    """Resolve a separate workspace; never modify the five Shot selections.

    Missing inputs retain the last good pair instead of silently deleting
    canvas layers. Duplicate catalog assets remain distinct input instances.
    """
    workspace = state["image_bash_workspace"]
    if not workspace:
        return [], {}
    instances = workspace["instances"]
    scoped = _image_bash_selection_state(state)
    selection = _resolve_selected_assets(scoped, media_by_uid, resolution_cache=resolution_cache,
        import_revision=import_revision, force=force, normalized=True)
    resolved = {row["source_uid"]: row for row in selection["resolved"]}
    if any(row["source_uid"] not in resolved for row in instances):
        return None
    if instances:
        from griptape.artifacts.image_url_artifact import ImageUrlArtifact
    records, images = [], []
    for instance in instances:
        item = resolved[instance["source_uid"]]
        asset, url = item["asset"], item["media"]
        record = {"source_uid": instance["instance_id"], "catalog_uid": instance["source_uid"],
                  "url": url, "name": _clean(asset.get("image_name")) or "Image"}
        if asset.get("media_signature"):
            record["media_signature"] = _clean(asset["media_signature"])
        records.append(record)
        images.append(ImageUrlArtifact(value=url, name=record["name"]))
    return images, {"schema": IMAGE_BASH_CONTEXT_SCHEMA, "workspace_id": workspace["workspace_id"],
                    "revision": workspace["revision"], "ready": True, "records": records}


def _image_bash_selection_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Select workspace assets without changing any authored Shot selection."""
    instances = state.get("image_bash_workspace", {}).get("instances", [])
    order = {row["source_uid"]: index + 1 for index, row in enumerate(instances)}
    return dict(state, assets=[dict(asset, selected=asset["source_uid"] in order,
        selection_order=order.get(asset["source_uid"], 0)) for asset in state["assets"]])


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
    _ensure_import_child_removal_observers(node)
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
        "Name, optional Main/Sub metadata, and default selection. Registered "
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
                # Native hide=True excludes the property from the editor's
                # allocator entirely, so no transport widget would mount.
                # The dedicated inert widget hides itself without removing
                # its supported PROPERTY/onChange transport lifecycle.
                "hide": False,
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
        ("hide", False),
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
                "hide": False,
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
    pending_attribute: str = "_hmb_pending_output_notifications",
) -> None:
    """Forward one late compact output through real retained-mode edges."""

    def still_owned() -> bool:
        if owner_pending is None:
            return True
        pending = getattr(node, pending_attribute, None)
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
    notify_unchanged_shot: bool = False,
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
    # Exact media readiness can change while a restored Shot token stays equal.
    # Only its validated completion callback requests this one extra wake.
    shot_output_changed = bool(
        shot_asset_output is not None
        and (current_shot_output != shot_asset_output or notify_unchanged_shot)
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


class _ImageAssetSelectionPreparing(ValueError):
    hmb_image_asset_selection_preparing = True


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
        self._hmb_refresh_authority = None
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
        self._hmb_import_thumbnail_lock = threading.RLock()
        self._hmb_import_thumbnail_generation = 0
        self._hmb_import_thumbnail_processing_generation = 0
        self._hmb_import_thumbnail_active_workers = 0
        self._hmb_import_thumbnail_queued_task: tuple[int, Callable[[], None]] | None = None
        self._hmb_import_thumbnail_thread: threading.Thread | None = None
        self._hmb_import_thumbnail_pending_result: tuple[
            int,
            Dict[str, tuple[str, str, str]],
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
        _add_image_bash_outputs(self)
        _add_image_import_input(self)
        _add_project_root(self)
        _add_widget_state(self)
        _add_thumbnail_patch_bridge(self)

    @hmb_binding_mutation
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
        if initial_setup and param_name == THUMBNAIL_PATCH_PARAMETER:
            saved_request = _normalize_thumbnail_bridge(value)
            if saved_request.get("operation") in {"cgt_catalog", "cgt_confirm", "cgt_cancel"} and saved_request.get("phase") == "request":
                # A saved dialog command is not a fresh user confirmation.
                # Retire it before even the native hydration callbacks see it.
                value = _default_thumbnail_bridge(saved_request.get("runtime_instance_id", ""))
        if initial_setup and param_name in {WIDGET_STATE_PARAMETER, THUMBNAIL_PATCH_PARAMETER}:
            # Native cold restore applies saved AlterParameterDetails after
            # construction and does not invoke our legacy after_deserialize
            # helper. Repair only the inert transport's UI contract when the
            # supported initial-setup value hydration reaches this node.
            _add_thumbnail_patch_bridge(self)
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
            self._hmb_publication_cursor_restore_pending = True
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
        state = _normalize_state(
            _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        )
        authority = getattr(self, "_hmb_cgt_work_notice", None)
        if authority and authority[0] == _hmb_shot_routing.hierarchy_project_key(state):
            state["cgt_work_start_notice"] = dict(authority[1])
        notice = state.get("cgt_work_start_notice") or {}
        if (notice.get("status") in {"queued", "running"}
                and notice.get("request_id") not in getattr(self, "_hmb_cgt_work_seen", set())):
            # A saved in-flight notice is never a command to resume a write.
            state["cgt_work_start_notice"] = {**notice, "status": "unknown"}
        return state

    def _hmb_project_identity(self) -> Dict[str, str]:
        """Read the selected project without scanning, publishing, or changing UI."""
        from _hmb_project import project_from_asset_payload

        return project_from_asset_payload(self._current_state(), default_legacy=False)

    @hmb_binding_mutation
    def _cache_shot_routing_snapshot(
        self,
        state: Dict[str, Any],
        *,
        force: bool = False,
        normalized: bool = False,
        cached_only: bool = False,
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
        if cached_only:
            # Readiness must never resolve a network project on the engine
            # event loop. Normal source publication refreshes this cache.
            raise _ImageAssetSelectionPreparing("ImageAsset Shot publication is still preparing.")
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
                "project_id": probe["project_id"],
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
        *,
        cached_only: bool = False,
    ) -> Dict[str, Any]:
        """Return a private atomic shot metadata/media snapshot."""
        state = self._current_state()
        if not cached_only:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and self._defer_project_selection_resolution(state):
                raise _ImageAssetSelectionPreparing("ImageAsset Shot publication is still preparing.")
        snapshot = self._cache_shot_routing_snapshot(state, cached_only=cached_only)
        expected = _clean(expected_channel_uuid)
        if expected and expected != snapshot["channel_uuid"]:
            raise ValueError(
                "HMB shot routing channel mismatch: expected "
                f"{expected!r}, publisher has {snapshot['channel_uuid']!r}."
            )
        result = {
            "schema": snapshot["schema"],
            "version": snapshot["version"],
            "publisher_instance_uuid": snapshot["publisher_instance_uuid"],
            "channel_uuid": snapshot["channel_uuid"],
            "generation": snapshot["generation"],
            "project_id": snapshot["project_id"],
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
        return self._hmb_image_shot_snapshot_view(result)

    def _hmb_image_shot_snapshot_view(self, snapshot: Dict[str, Any], *, scoped: bool = False) -> Dict[str, Any]:
        """Give full/scoped reads one monotonic private snapshot hash clock.

        The reusable catalog, serialized widget and output dependency caches
        keep their own publication generation. Only this returned immutable
        view changes: alternating exact Shots cannot reuse one generation for
        different hashes or invalidate an older full-read document on upgrade.
        """
        identity = _sha256_canonical({key: snapshot[key] for key in (
            "publisher_instance_uuid", "channel_uuid", "project_id", "shots",
            "ordered_assets", "media_sha256")})
        lock = getattr(self, "_hmb_scan_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._hmb_scan_lock = lock
        with lock:
            previous = getattr(self, "_hmb_image_snapshot_view_identity", "")
            previous_generation = _non_negative_int(getattr(self, "_hmb_image_snapshot_view_generation", 0))
            floor = max(1, _non_negative_int(snapshot["generation"]),
                        _non_negative_int(getattr(self, "_hmb_shot_routing_generation", 0)))
            generation = max(floor, previous_generation)
            if identity != previous:
                # A saved older workflow may already contain the full hash at
                # floor before this private view clock has been created.
                generation = max(generation, previous_generation + 1, floor + int(scoped))
            self._hmb_image_snapshot_view_identity = identity
            self._hmb_image_snapshot_view_generation = generation
        result = dict(snapshot, generation=generation)
        result["metadata_sha256"] = _sha256_canonical({key: result[key] for key in (
            "channel_uuid", "generation", "project_id", "shots", "ordered_assets")})
        return result

    def _hmb_shot_routing_snapshot_for(
        self,
        *,
        channel_uuid: str,
        shot_uuid: str,
        cached_only: bool = False,
    ) -> Dict[str, Any]:
        """Resolve only one exact Shot and reject every missing owned source.

        Another Shot's unavailable share/file must not erase or block this
        Shot's references. Authored empty [] remains valid; selected missing
        media is an error, never a successful empty/partial publication.
        """
        state = self._current_state()
        routing = state["shot_routing"]
        channel, target = _uuid_text(channel_uuid), _uuid_text(shot_uuid)
        if not channel or not target or channel != routing["channel_uuid"]:
            raise ValueError("ImageAsset exact Shot channel or identity is unavailable.")
        selected = next((row for row in routing["shots"] if row["shot_uuid"] == target), None)
        if selected is None:
            raise ValueError("ImageAsset exact Shot is no longer in the current catalog.")
        requested = list(selected["selected_source_uids"])
        by_uid = {_clean(row.get("source_uid")): row for row in state["assets"]
                  if row.get("selected")}
        if any(uid not in by_uid for uid in requested):
            raise ValueError("ImageAsset exact Shot addresses an unavailable selected image.")
        scoped = dict(state)
        scoped["assets"] = [dict(by_uid[uid], selected=True, selection_order=index)
                            for index, uid in enumerate(requested, 1)]
        scoped["shot_routing"] = dict(routing, shots=[dict(selected, selected_source_uids=requested)],
                                       active_shot_uuid=target)
        self._consume_selection_resolution()
        cache = self._resolution_cache_for_state(scoped)
        revision = _non_negative_int(getattr(self, "_hmb_import_revision", 0))
        if cached_only:
            if any(_asset_resolution_cache_key(row, scoped, revision) not in cache for row in scoped["assets"]):
                raise _ImageAssetSelectionPreparing("ImageAsset exact Shot media cache is still preparing.")
        else:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and self._defer_project_selection_resolution(scoped):
                raise _ImageAssetSelectionPreparing("ImageAsset exact Shot media is still preparing.")
        snapshot = _build_shot_routing_snapshot(scoped,
            getattr(self, "_hmb_import_media_by_uid", {}), resolution_cache=cache,
            import_revision=revision, generation=max(1, _non_negative_int(routing["generation"])), normalized=True)
        actual = snapshot["shots"][0]["selected_source_uids"]
        if actual != requested:
            missing = [uid for uid in requested if uid not in snapshot["media_by_source_uid"]]
            raise ValueError("ImageAsset exact Shot selected image media is unavailable: " + ", ".join(missing))
        return self._hmb_image_shot_snapshot_view(snapshot, scoped=True)

    def _hmb_shot_routing_catalog(self) -> Dict[str, Any]:
        """Return the bounded, media-free Shot catalog used by same-flow peers."""

        state = self._current_state()
        try:
            snapshot = self._cache_shot_routing_snapshot(state, cached_only=True)
        except ValueError:
            # Discovery needs only authored Shot names/IDs. Resolving images
            # here would put UNC IO back on the event loop while a selection
            # worker is preparing that separate media snapshot.
            snapshot = dict(state["shot_routing"])
            snapshot["generation"] = max(
                1, _non_negative_int(snapshot.get("generation")),
                _non_negative_int(getattr(self, "_hmb_shot_routing_generation", 0)),
            )
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
        # The accepted canonical native value owns this bounded scalar view.
        # A pending setter/hydration with a different raw value must follow the
        # original normalizer; never reuse another generation by names/count.
        baseline = getattr(self, "_hmb_shot_subscription_baseline", None)
        raw = _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        if (isinstance(baseline, tuple) and len(baseline) == 2
                and isinstance(baseline[0], str)
                and isinstance(raw, str) and raw == baseline[0]):
            return dict(baseline[1])
        return self._hmb_shot_subscription_value(self._current_state()["shot_routing"])

    def _hmb_shot_hierarchy_snapshot(self, channel_uuid: str, shot_uuid: str) -> Dict[str, Any]:
        state = self._current_state()
        binding = _hmb_shot_routing.validate_shot_hierarchy_routing(
            state.get("shot_hierarchy"), state["shot_routing"]
        )
        if (not binding or binding["channel_uuid"] != channel_uuid
                or binding["project_identity"] != _hmb_shot_routing.hierarchy_project_key(state)
                or not any(row["gp_shot_uuid"] == shot_uuid for row in binding["members"])):
            return {}
        return copy.deepcopy(binding)

    @staticmethod
    def _hmb_shot_subscription_value(routing: Dict[str, Any]) -> Dict[str, Any]:
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
        self._hmb_refresh_authority = None
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
        # Publishing assigns the replacement's own publisher identity and
        # recomputes media summaries; neither changes durable Shot membership.
        expected_routing = copy.deepcopy(state.get("shot_routing") or {})
        actual_routing = copy.deepcopy(adopted.get("shot_routing") or {})
        expected_routing.pop("publisher_instance_uuid", None)
        publisher = actual_routing.pop("publisher_instance_uuid", "")
        for routing in (expected_routing, actual_routing):
            for shot in routing.get("shots", []):
                for key in ("media_count", "metadata_sha256", "media_sha256"):
                    shot.pop(key, None)
        return bool(
            _uuid_text(publisher)
            and adopted.get("assets") == state.get("assets")
            and actual_routing == expected_routing
            and adopted.get("image_bash_workspace") == state.get("image_bash_workspace")
            and adopted.get("image_bash_active") == state.get("image_bash_active")
            and _canonical_import_input_identity(_get_parameter_raw(self, IMAGE_IMPORT_PARAMETER))
                == _canonical_import_input_identity(import_value)
            and dict(getattr(self, "_hmb_import_media_by_uid", {}) or {}) == import_media
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
        NodeManager identity checks at every call site.  Clearing the key here
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
        if key.startswith("project:") and not normalized_state.get("scan_busy"):
            live = self._current_state()
            if (live.get("scan_busy")
                and _project_root_text(live.get("project_root")).casefold()
                == _project_root_text(normalized_state.get("project_root")).casefold()):
                # A cache hit preserves the source snapshot's scan clock.
                # Completion must still supersede its empty/busy ACK, which
                # the editor can deliver after these terminal catalog facts.
                normalized_state["scan_revision"] = max(
                    _non_negative_int(normalized_state.get("scan_revision")),
                    _non_negative_int(live.get("scan_revision")) + 1,
                )
        if not _clean(normalized_state.get("error")) and _clean(
            normalized_state.get("project_root")
        ):
            _store_shared_catalog_snapshot(normalized_state, normalized=True)
            # Durable cache IO was completed on the scan/probe worker.  This
            # retained callback also handles pending results and cache hits;
            # none of those routes may revisit a project path or write a file.
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
        raw = self._expand_widget_edit(value)
        if not raw:
            return
        normalized_state = _normalize_state(raw)
        self._accept_normalized_widget_state_baseline(normalized_state)

    def _expand_widget_edit(self, value: Any) -> Dict[str, Any]:
        """Expand a catalog-free edit against this node's accepted authority.

        A client can edit selection/presentation and send existing explicit
        commands; it cannot supply catalog rows, source paths or media facts.
        Legacy full snapshots keep their existing hydration/scan contract.
        """
        raw = dict(_parse_mapping(value))
        if raw.get("schema") == STATE_SCHEMA and raw.get("shot_hierarchy_request"):
            return self._prepare_shot_hierarchy_edit(raw, raw["shot_hierarchy_request"])
        if raw.get("schema") == STATE_SCHEMA and isinstance(raw.get("catalog_page"), dict):
            # Display pages never replace the full canonical persisted catalog.
            base = _parse_mapping(getattr(self, "_hmb_last_accepted_widget_state", ""))
            if not base or base.get("schema") != STATE_SCHEMA:
                raise ValueError("A display page requires an accepted ImageAsset catalog.")
            raw.pop("catalog_page", None)
            raw["assets"] = base.get("assets", [])
            raw["folders"] = base.get("folders", [])
        if raw.get("schema") != IMAGE_ASSET_EDIT_SCHEMA:
            return raw
        revision = raw.get(UI_EDIT_REVISION_KEY)
        if (raw.get("version") != 1 or isinstance(raw.get("version"), bool)
                or not isinstance(revision, int) or isinstance(revision, bool)
                or not 0 <= revision <= MAX_UI_EDIT_REVISION):
            raise ValueError("Image asset edit has an invalid protocol/revision.")
        base = dict(_parse_mapping(self._hmb_last_accepted_widget_state))
        if not base or base.get("schema") != STATE_SCHEMA:
            raise ValueError("Image asset edit requires an accepted catalog; refresh and retry.")
        identity = raw.get("catalog_identity")
        if not isinstance(identity, dict):
            raise ValueError("Image asset edit is missing its catalog identity.")
        for field in ("catalog_root", "project_root", "project_uid", "project_cache_uid",
                      "manifest_signature", "folder_signature", "scan_revision"):
            supplied, current = identity.get(field), base.get(field)
            if field == "scan_revision":
                matches = isinstance(supplied, int) and not isinstance(supplied, bool) and supplied == _non_negative_int(current)
            elif field in {"catalog_root", "project_root"}:
                matches = isinstance(supplied, str) and _project_root_text(supplied).replace("\\", "/").casefold() == _project_root_text(current).replace("\\", "/").casefold()
            else:
                matches = isinstance(supplied, str) and supplied == _clean(current)
            if not matches:
                raise ValueError("Image asset catalog changed; refresh and retry this edit.")
        clock = dict(raw, scan_revision=identity["scan_revision"],
                     thumbnail_revision=base.get("thumbnail_revision", 0))
        if self._widget_state_is_stale(clock):
            raise ValueError("Image asset edit is older than the accepted state.")
        edits = raw.get("edits")
        selected = raw.get("selected_source_uids")
        if not isinstance(edits, dict) or set(edits) - set(IMAGE_ASSET_EDIT_FIELDS):
            raise ValueError("Image asset edit contains unsupported fields.")
        if edits.get("shot_hierarchy_request"):
            return self._prepare_shot_hierarchy_edit(raw, edits["shot_hierarchy_request"])
        if edits.get("shot_hierarchy", base.get("shot_hierarchy", {})) != base.get("shot_hierarchy", {}):
            raise ValueError("샷 구성은 연필 창에서 확정해야 합니다.")
        if (not isinstance(selected, list) or len(selected) > MAX_SELECTED_IMAGES
                or any(not isinstance(uid, str) or not uid for uid in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError("Image asset edit has invalid source identities.")
        known = {_clean(item.get("source_uid")) for item in base.get("assets", [])}
        if any(uid not in known for uid in selected):
            raise ValueError("Image asset source changed; refresh and retry this edit.")
        routing = edits.get("shot_routing")
        current_routing = base.get("shot_routing") or {}
        if not isinstance(routing, dict) or not isinstance(routing.get("shots"), list):
            raise ValueError("Image asset edit is missing Shot ownership.")
        for field in ("publisher_instance_uuid", "channel_uuid"):
            if routing.get(field) != current_routing.get(field):
                raise ValueError("Image asset edit belongs to a different Shot publisher.")
        rows = routing["shots"]
        if (not 1 <= len(rows) <= MAX_SHOTS
                or any(not isinstance(row, dict) or not _uuid_text(row.get("shot_uuid")) for row in rows)
                or len({row["shot_uuid"] for row in rows}) != len(rows)):
            raise ValueError("Image asset edit has invalid Shot identities.")
        old_rows = {row["shot_uuid"]: row for row in current_routing.get("shots", [])}
        new_generation = _non_negative_int(routing.get("generation"))
        old_generation = _non_negative_int(current_routing.get("generation"))
        if new_generation < old_generation:
            raise ValueError("Image asset Shot structure changed; refresh and retry.")
        if ([row["shot_uuid"] for row in current_routing.get("shots", [])]
                != [row["shot_uuid"] for row in rows] and new_generation <= old_generation):
            raise ValueError("Image asset Shot structure requires a newer structure revision.")
        for row in rows:
            previous = old_rows.get(row["shot_uuid"])
            if previous is not None and _non_negative_int(row.get("revision")) < _non_negative_int(previous.get("revision")):
                raise ValueError("Image asset Shot edit is older than the accepted Shot.")
            members = row.get("selected_source_uids")
            if (not isinstance(members, list) or len(members) > MAX_SHOT_IMAGES
                    or any(uid not in selected for uid in members) or len(set(members)) != len(members)):
                raise ValueError("Image asset Shot contains an unselected source identity.")
            if (previous is not None and _non_negative_int(row.get("revision")) == _non_negative_int(previous.get("revision"))
                    and any(row.get(field) != previous.get(field)
                            for field in ("name", "name_is_custom", "selected_source_uids"))):
                raise ValueError("Image asset Shot membership/name requires a newer Shot revision.")
        if routing.get("active_shot_uuid") not in {row["shot_uuid"] for row in rows}:
            raise ValueError("Image asset active Shot is no longer present.")
        if "image_bash_active" in edits and type(edits["image_bash_active"]) is not bool:
            raise ValueError("Image Bash 화면 선택이 올바르지 않습니다.")
        if "image_bash_workspace" in edits:
            old_workspace = base["image_bash_workspace"]
            workspace = _normalize_image_bash_workspace(edits["image_bash_workspace"], current_routing["channel_uuid"])
            changed = workspace.get("instances", []) != old_workspace.get("instances", [])
            if ((not workspace and bool(old_workspace))
                    or (workspace and ((old_workspace and workspace["workspace_id"] != old_workspace["workspace_id"])
                    or workspace["revision"] != (old_workspace["revision"] + int(changed) if old_workspace else 0)))):
                raise ValueError("Image Bash 작업 공간이 변경되었습니다. 다시 선택하세요.")
            old_instances = {row["instance_id"]: row["source_uid"] for row in old_workspace.get("instances", [])}
            known_sources = {_clean(row.get("source_uid")) for row in base.get("assets", [])}
            if any((row["instance_id"] in old_instances and old_instances[row["instance_id"]] != row["source_uid"])
                   or (row["instance_id"] not in old_instances and row["source_uid"] not in known_sources)
                   for row in workspace.get("instances", [])):
                raise ValueError("Image Bash 이미지 원본이 변경되었습니다. 새 인스턴스로 추가하세요.")
            edits["image_bash_workspace"] = workspace
        if edits.get("image_bash_workspace_request"):
            command = _normalize_image_bash_workspace_request(edits["image_bash_workspace_request"])
            workspace = edits.get("image_bash_workspace", base["image_bash_workspace"])
            if not workspace or command["workspace_id"] != workspace["workspace_id"] or command["expected_revision"] != workspace["revision"]:
                raise ValueError("Image Bash 추가 요청의 작업 공간이 변경되었습니다.")
        base.update(edits)
        base[UI_EDIT_REVISION_KEY] = raw.get(UI_EDIT_REVISION_KEY)
        order = {uid: index + 1 for index, uid in enumerate(selected)}
        base["assets"] = [dict(item, selected=_clean(item.get("source_uid")) in order,
                               selection_order=order.get(_clean(item.get("source_uid")), 0))
                          for item in base.get("assets", [])]
        return base

    def _prepare_shot_hierarchy_edit(self, raw: Dict[str, Any], request: Any) -> Dict[str, Any]:
        base = dict(_parse_mapping(getattr(self, "_hmb_last_accepted_widget_state", "")))
        if not base or base.get("schema") != STATE_SCHEMA or self._widget_state_is_stale(raw):
            raise ValueError("샷 라이브러리를 새로 확인한 뒤 다시 구성하세요.")
        prepared = _hmb_shot_routing.apply_shot_hierarchy_edit(base, request)
        edited = prepared.get("shot_hierarchy", {})
        if any(row.get("origin") == "cgt" for row in edited.get("members", [])):
            # Renaming a locally authored member does not change a CGT
            # selection. Allow that narrow transaction without contacting CGT;
            # all authenticated rows, grouping, scope and native identities
            # must remain byte-for-byte equivalent to accepted authority.
            prior = base.get("shot_hierarchy", {})
            old_rows, new_rows = prior.get("members", []), edited.get("members", [])
            ignored = {"revision", "members"}
            manual_name_only = bool(prior) and len(old_rows) == len(new_rows) and (
                {key: value for key, value in prior.items() if key not in ignored}
                == {key: value for key, value in edited.items() if key not in ignored})
            name_changed = False
            for old, new in zip(old_rows, new_rows):
                if old.get("origin") == new.get("origin") == "manual":
                    names = {"source_name", "canonical_name"}
                    manual_name_only = manual_name_only and (
                        {key: value for key, value in old.items() if key not in names}
                        == {key: value for key, value in new.items() if key not in names})
                    name_changed = name_changed or any(old.get(key) != new.get(key) for key in names)
                elif old != new:
                    manual_name_only = False
            if not manual_name_only or not name_changed:
                raise ValueError("CGT 샷은 본인 작업을 다시 검증한 뒤 확정해야 합니다.")
        prepared[UI_EDIT_REVISION_KEY] = raw.get(UI_EDIT_REVISION_KEY, base.get(UI_EDIT_REVISION_KEY, 0))
        return prepared

    def _accept_normalized_widget_state_baseline(
        self,
        normalized_state: Dict[str, Any],
        serialized: str = "",
    ) -> None:
        # A detached scalar search projection owns index invalidation. Selection
        # and thumbnail edits do not rebuild it; same-count metadata edits do.
        fields = ("asset_id", "image_name", "relative_path", "image_main_type",
                  "image_sub_type", "source_kind", "asset_library_id", "source_uid")
        projection = tuple(tuple(_clean(asset.get(key)) for key in fields)
                           for asset in normalized_state.get("assets", []))
        if projection != getattr(self, "_hmb_catalog_search_projection", None):
            self._hmb_catalog_search_projection = projection
            self._hmb_catalog_search_catalog_revision = (
                getattr(self, "_hmb_catalog_search_catalog_revision", 0) + 1)
        # Owner-local accepted read view; never authority supplied by a page.
        self._hmb_catalog_search_authority = normalized_state
        self._hmb_catalog_search_assets = {
            _clean(asset.get("asset_library_id")): asset for asset in normalized_state.get("assets", [])}
        self._hmb_catalog_search_selected = tuple(
            asset for asset in normalized_state.get("assets", []) if asset.get("selected"))
        self._hmb_last_accepted_widget_state = serialized or _json_text(normalized_state)
        self._hmb_durable_shot_generation = (
            self._hmb_last_accepted_widget_state,
            normalized_state["shot_routing"]["generation"],
        )
        workspace = normalized_state.get("image_bash_workspace", {})
        routing = normalized_state["shot_routing"]
        self._hmb_image_bash_catalog_baseline = (self._hmb_last_accepted_widget_state,
            {"schema": "hmb-image-bash-workspace-catalog-v1", "source_node": self.name,
             "channel_uuid": routing["channel_uuid"], "publisher_instance_uuid": routing["publisher_instance_uuid"],
             "workspaces": ([{"workspace_id": workspace["workspace_id"], "name": "HMBImageBash",
                 "revision": workspace["revision"], "count": len(workspace["instances"])}] if workspace else [])})
        self._hmb_shot_subscription_baseline = (
            self._hmb_last_accepted_widget_state,
            self._hmb_shot_subscription_value(normalized_state["shot_routing"]),
        )
        self._hmb_last_accepted_widget_revisions = (
            _non_negative_int(normalized_state.get("scan_revision")),
            _non_negative_int(normalized_state.get(UI_EDIT_REVISION_KEY)),
        )
        self._hmb_last_accepted_thumbnail_revision = _non_negative_int(
            normalized_state.get("thumbnail_revision")
        )

    @staticmethod
    def _rebase_fresh_project_selection(
        value: Any, previous: Dict[str, Any], latest: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        """Carry only a fresh selection intent across an older scan completion."""
        raw = _parse_mapping(value)
        revision = raw.get(UI_EDIT_REVISION_KEY)
        target = _clean(raw.get("project_root")).replace("\\", "/")
        catalog = _project_root_text(raw.get("catalog_root")).replace("\\", "/").casefold()
        if (raw.get("schema") != STATE_SCHEMA or not target
                or _non_negative_int(raw.get("scan_revision")) != _non_negative_int(previous.get("scan_revision"))
                or _non_negative_int(latest.get("scan_revision")) <= _non_negative_int(previous.get("scan_revision"))
                or not isinstance(revision, int) or isinstance(revision, bool)
                or not 0 <= revision <= MAX_UI_EDIT_REVISION
                or revision <= max(_non_negative_int(previous.get(UI_EDIT_REVISION_KEY)),
                                   _non_negative_int(latest.get(UI_EDIT_REVISION_KEY)))
                or target.casefold() == _clean(previous.get("project_root")).replace("\\", "/").casefold()
                or any(_clean(raw.get(key)) for key in ("project_id", "project_uid", "project_cache_uid"))
                or not catalog or any(catalog != _project_root_text(state.get("catalog_root")).replace("\\", "/").casefold()
                                      for state in (previous, latest))):
            return None
        selected = next((row for row in latest.get("projects", [])
                         if _clean(row.get("path")).replace("\\", "/").casefold() == target.casefold()), None)
        if selected is None or _clean(latest.get("error")):
            return None
        rebased = dict(latest)
        rebased.update(project_root=selected["path"], project_id="", project_uid="", project_cache_uid="",
                       folder_signature="", selected_folder_path="", expanded_folders=["$root"],
                       selected_main_type="", selected_sub_type="", selected_source_view="project")
        rebased[UI_EDIT_REVISION_KEY] = revision
        return rebased

    def _take_pending_project_selection(self, value: Any, previous: Dict[str, Any]) -> Dict[str, Any] | None:
        """Retire a pure ready scan without emitting its old selection first."""
        if (bool(getattr(self, "_hmb_catalog_completion_active", False))
                or getattr(self, "_hmb_scan_pending_result", None) is None):
            return None
        with self._hmb_scan_lock:
            pending = self._hmb_scan_pending_result
            if pending is None or not self._scan_owner_is_current():
                return None
            generation, key, _request_id, payload = pending
            if (generation != self._hmb_scan_generation or key != self._hmb_scan_pending_key
                    or payload.get("result_merger") is not None or payload.get("on_published") is not None
                    or payload.get("media_by_uid") or getattr(self, "_hmb_import_media_by_uid", {})):
                return None  # Mutations/import handoffs keep their normal completion callbacks.
            latest = _merge_async_scan_result_with_live_state(payload.get("state"), payload.get("scan_base"), self._current_state())
            rebased = HMBImageAssetLibrary._rebase_fresh_project_selection(value, previous, latest)
            if rebased is None:
                return None
            self._hmb_scan_generation += 1  # Invalidate the already queued completion callback too.
            self._hmb_scan_pending_result = None
            self._hmb_scan_pending_key = ""
            self._hmb_scan_thread = None
            if key == getattr(self, "_hmb_fresh_registration_scan_key", ""):
                self._hmb_fresh_registration_scan_key = ""
                self._hmb_hydration_adopted = True
            return rebased

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

    def _resolution_cache_for_state(self, state: Dict[str, Any]) -> OrderedDict:
        cache = getattr(self, "_hmb_resolution_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._hmb_resolution_cache = cache
        identity = _resolution_cache_state_identity(state)
        if identity != getattr(self, "_hmb_resolution_cache_identity", ""):
            cache.clear()
            self._hmb_resolution_cache_identity = identity
        return cache

    def _consume_selection_resolution(self, *, publish: bool = False) -> bool:
        work = getattr(self, "_hmb_selection_resolution_work", None)
        if not isinstance(work, dict):
            return False
        with work["lock"]:
            ready = work.get("ready")
            # A snapshot reader may warm the cache before the queued host
            # callback runs. Only that publishing callback may consume its
            # notification; otherwise the ready Prompt/Agent wake is lost.
            if publish:
                work["ready"] = None
        if ready is None or not self._scan_owner_is_current():
            return False
        identity, epoch, entries = ready
        live = self._current_state()
        if (identity != _resolution_cache_state_identity(live)
            or epoch != work["epoch"]):
            return False
        cache = self._resolution_cache_for_state(live)
        for key, entry in entries.items():
            _resolution_cache_put(cache, key, entry)
        if publish and not live.get("scan_busy"):
            # Only the current selection owns publication. A late completion
            # can warm its exact project cache, never restore a previous click.
            self._sync_output(live, normalized=True, selection_ready=True)
            self._reconcile_hmb_shot_routing(
                _shot_routing_catalog_identity(live, normalized=True)
            )
        return True

    def _defer_project_selection_resolution(self, state: Dict[str, Any]) -> bool:
        """Keep first-selection UNC verification off the retained event loop."""
        self._consume_selection_resolution()
        cache = self._resolution_cache_for_state(state)
        revision = _non_negative_int(getattr(self, "_hmb_import_revision", 0))
        # Workspace-only project sources need the same asynchronous share
        # verification as Shot selections. Resolve the two independently so
        # each selection retains its own 50-image limit.
        selections = [state]
        if state.get("image_bash_workspace"):
            selections.append(_image_bash_selection_state(state))
        missing = [
            _asset_resolution_cache_key(asset, state, revision)
            for selection in selections
            for asset in selection.get("assets", [])
            if asset.get("selected")
            and _clean(asset.get("source_kind")).casefold() == "project"
            and _asset_resolution_cache_key(asset, state, revision) not in cache
        ]
        if not missing:
            return False
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if loop is None:
            try:
                from griptape_nodes.retained_mode.engine import has_current_engine
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                if has_current_engine():
                    loop = GriptapeNodes.EventManager().event_loop
            except ImportError:
                pass
        if loop is None or not loop.is_running() or loop.is_closed():
            # Synchronous legacy hosts and process(force=True) retain their
            # existing verification contract; never construct an Engine here.
            return False
        work = getattr(self, "_hmb_selection_resolution_work", None)
        if not isinstance(work, dict):
            work = {"lock": threading.RLock(), "active": False,
                    "key": "", "queued": None, "ready": None, "epoch": 0}
            self._hmb_selection_resolution_work = work
        identity = _resolution_cache_state_identity(state)
        key = _sha256_canonical([identity, sorted(missing), work["epoch"]])
        task = (key, identity, work["epoch"], copy.deepcopy(selections),
                dict(getattr(self, "_hmb_import_media_by_uid", {}) or {}), revision)
        with work["lock"]:
            if key == work["key"]:
                work["queued"] = None
                return True
            if work["queued"] and work["queued"][0] == key:
                return True
            if work["active"]:
                # Bound a stalled share to one worker and retain only the
                # newest pending selection instead of spawning on every click.
                work["queued"] = task
                return True
            work["active"] = True
            work["key"] = key
        node_ref = weakref.ref(self)
        host_context = contextvars.copy_context()

        def publish_ready() -> None:
            owner = node_ref()
            if owner is not None:
                owner._consume_selection_resolution(publish=True)

        def worker() -> None:
            current_task = task
            try:
                while current_task is not None:
                    _, project_identity, epoch, snapshots, imports, import_revision = current_task
                    resolved_cache: OrderedDict = OrderedDict()
                    try:
                        for snapshot in snapshots:
                            _resolve_selected_assets(
                                snapshot, imports, resolution_cache=resolved_cache,
                                import_revision=import_revision, normalized=True,
                            )
                    except Exception as exc:
                        # A failed task must release its slot and still drain a
                        # newer queued selection. Never publish a partial cache.
                        _diagnostic_exception("Selected project image verification failed", exc)
                    else:
                        with work["lock"]:
                            if epoch == work["epoch"]:
                                work["ready"] = (project_identity, epoch, resolved_cache)
                        try:
                            loop.call_soon_threadsafe(host_context.copy().run, publish_ready)
                        except RuntimeError:
                            # A retained callback will consume the ready cache if
                            # the host loop stopped between lookup and handoff.
                            pass
                    with work["lock"]:
                        current_task = work["queued"]
                        work["queued"] = None
                        work["key"] = current_task[0] if current_task else ""
                        if current_task is None:
                            work["active"] = False
                            return
            finally:
                with work["lock"]:
                    if current_task is not None and work["key"] == current_task[0]:
                        work["active"] = False
                        work["key"] = ""

        thread = threading.Thread(target=worker, name="HMBImageAssetSelection", daemon=True)
        try:
            thread.start()
        except Exception:
            with work["lock"]:
                work["active"] = False
                work["key"] = ""
            raise
        return True

    def _sync_image_bash_output(self, state: Dict[str, Any], *, force: bool = False,
                                pending: bool = False) -> None:
        workspace = state["image_bash_workspace"]
        if workspace:
            wanted = {row["source_uid"] for row in workspace["instances"]}
            scoped = dict(state, assets=[dict(row, selected=row["source_uid"] in wanted)
                                        for row in state["assets"]])
            # scan_revision also advances for unrelated imported images. Keep
            # the previous usable context while only those rows are changing;
            # workspace/project/source facts still invalidate immediately.
            semantic = _sha256_canonical([workspace, _project_output_fingerprint(
                dict(scoped, scan_revision=0), getattr(self, "_hmb_import_media_by_uid", {}),
                getattr(self, "_hmb_import_revision", 0)),
                [(row["source_uid"], row.get("media_signature")) for row in state["assets"] if row["source_uid"] in wanted]])
            fingerprint = _sha256_canonical([workspace, _project_output_fingerprint(scoped,
                getattr(self, "_hmb_import_media_by_uid", {}), getattr(self, "_hmb_import_revision", 0)),
                [(row["source_uid"], row.get("media_signature")) for row in state["assets"] if row["source_uid"] in wanted]])
        else:
            semantic = "empty-workspace"
            fingerprint = "empty-workspace"
        pair = getattr(self, "_hmb_last_image_bash_pair", None)
        if pending and workspace:
            if (bool(getattr(self, "_hmb_unrelated_import_publication", False))
                    and semantic == getattr(self, "_hmb_last_image_bash_semantic", "")
                    and isinstance(pair, tuple) and pair[1].get("ready") is True):
                return
            # The saved scene is retained, but an old Apply cannot be mistaken
            # for the newly requested revision while the share is checked.
            previous = pair if isinstance(pair, tuple) else ([], {})
            same_workspace = previous[1].get("workspace_id") == workspace.get("workspace_id")
            pair = (previous[0] if same_workspace else [], {"schema": IMAGE_BASH_CONTEXT_SCHEMA,
                "workspace_id": workspace.get("workspace_id", ""), "revision": workspace.get("revision", 0),
                "ready": False, "records": copy.deepcopy(previous[1].get("records", [])) if same_workspace else [],
                "error": "Image Bash 이미지 원본을 확인하는 중입니다."})
        elif force or fingerprint != getattr(self, "_hmb_last_image_bash_fingerprint", "") or pair is None:
            pair = _build_image_bash_outputs(state, getattr(self, "_hmb_import_media_by_uid", {}),
                resolution_cache=self._resolution_cache_for_state(state),
                import_revision=getattr(self, "_hmb_import_revision", 0), force=force)
            if pair is None:
                # A temporarily missing share/image must not delete edited
                # layers. The new request still invalidates the last Apply:
                # hold its image bytes but mark this context non-runnable.
                self._hmb_last_image_bash_fingerprint = ""
                previous = getattr(self, "_hmb_last_image_bash_pair", None)
                previous = previous if isinstance(previous, tuple) else ([], {})
                same_workspace = previous[1].get("workspace_id") == workspace.get("workspace_id")
                pair = (previous[0] if same_workspace else [], {"schema": IMAGE_BASH_CONTEXT_SCHEMA,
                    "workspace_id": workspace.get("workspace_id", ""), "revision": workspace.get("revision", 0),
                    "ready": False, "records": copy.deepcopy(previous[1].get("records", [])) if same_workspace else [],
                    "error": "Image Bash에서 선택한 이미지 원본을 확인할 수 없습니다. 원본 연결을 복구하세요."})
            else:
                self._hmb_last_image_bash_pair = pair
                self._hmb_last_image_bash_fingerprint = fingerprint
                self._hmb_last_image_bash_semantic = semantic
        outputs = ((IMAGE_BASH_IMAGES_OUTPUT_PARAMETER, pair[0]), (IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER, pair[1]))
        changed = force or any(getattr(self, "parameter_output_values", {}).get(name) != value for name, value in outputs)
        if changed:
            generation = getattr(self, "_hmb_image_bash_output_generation", 0) + 1
            self._hmb_image_bash_output_generation = generation
            # Stage both siblings before either subscriber may read them.
            for name, value in outputs:
                set_output(self, name, value)
            self._hmb_image_bash_pending_notifications = {
                name: (generation, value) for name, value in outputs
            }
        pending = getattr(self, "_hmb_image_bash_pending_notifications", {})
        if not isinstance(pending, dict):
            return
        for name, item in list(pending.items()):
            if getattr(self, "_hmb_image_bash_pending_notifications", {}).get(name) is not item:
                continue
            _, value = item
            try:
                self.publish_update_to_parameter(name, value)
                if getattr(self, "_hmb_image_bash_pending_notifications", {}).get(name) is not item:
                    continue
                _propagate_image_output_to_connections(self, name, value, owner_pending=item,
                    pending_attribute="_hmb_image_bash_pending_notifications")
            except Exception as exc:
                _diagnostic_exception("Image Bash output notification deferred", exc)
            else:
                current = getattr(self, "_hmb_image_bash_pending_notifications", {})
                if current.get(name) is item:
                    current.pop(name, None)

    def _hmb_image_bash_catalog(self) -> Dict[str, Any]:
        """Media-free workspace discovery, separate from the five Shot rows."""
        flow_name, _ = _hmb_shot_routing._same_flow_nodes(self)
        if not flow_name or bool(getattr(self, "_hmb_node_deleted", False)):
            return {}
        baseline = getattr(self, "_hmb_image_bash_catalog_baseline", None)
        raw = _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        if (isinstance(baseline, tuple) and len(baseline) == 2 and raw != baseline[0]
                and not getattr(self, "_hmb_hydration_adopted", False)):
            # A fresh SDK node's default JSON may differ from its normalized
            # authority in derived status fields. Adopt only exact semantic
            # equivalence; never rebase a hydrated or edited selection here.
            normalized = _normalize_state(raw)
            if normalized == getattr(self, "_hmb_catalog_search_authority", None):
                self._accept_normalized_widget_state_baseline(normalized, raw)
                baseline = self._hmb_image_bash_catalog_baseline
        if not isinstance(baseline, tuple) or len(baseline) != 2 or raw != baseline[0]:
            return {}
        return copy.deepcopy(baseline[1])

    def _hmb_image_bash_snapshot(self, workspace_id: str, cached_only: bool = True) -> tuple[Any, Dict[str, Any]]:
        """Read the exact current pair; a catalog/selector never resolves files."""
        catalog = self._hmb_image_bash_catalog()
        workspace = next((row for row in catalog.get("workspaces", []) if row["workspace_id"] == _uuid_text(workspace_id)), None)
        if workspace is None:
            raise ValueError("Image Bash 작업 공간이 변경되었습니다. 다시 선택하세요.")
        if not cached_only:
            self._sync_image_bash_output(self._current_state())
        generation = getattr(self, "_hmb_image_bash_output_generation", 0)
        values = getattr(self, "parameter_output_values", {})
        images, context = values.get(IMAGE_BASH_IMAGES_OUTPUT_PARAMETER), values.get(IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER)
        if (not isinstance(images, list) or not isinstance(context, dict)
                or context.get("schema") != IMAGE_BASH_CONTEXT_SCHEMA
                or context.get("workspace_id") != workspace["workspace_id"]
                or context.get("revision") != workspace["revision"]
                or generation != getattr(self, "_hmb_image_bash_output_generation", 0)):
            raise _ImageAssetSelectionPreparing("Image Bash 이미지 작업 공간을 동기화하는 중입니다.")
        return list(images), copy.deepcopy(context)

    def _hmb_prepare_image_bash_workspace(self, target: Any) -> str:
        """Explicitly prepare one workspace for an already registered Bash node."""
        if not hasattr(self, "_hmb_image_bash_binding_lock"):
            self._hmb_image_bash_binding_lock = threading.RLock()
        with self._hmb_image_bash_binding_lock:
            flow, nodes = _hmb_shot_routing._same_flow_nodes(self)
            if not flow or type(target).__name__ != "HMBImageBash" or not any(n is target for n in nodes):
                raise ValueError("같은 워크플로의 Image Bash만 연결할 수 있습니다.")
            state = self._current_state()
            if _get_parameter_raw(self, WIDGET_STATE_PARAMETER) != getattr(self, "_hmb_last_accepted_widget_state", None):
                raise ValueError("이미지 라이브러리 변경을 적용 중입니다. 다시 시도하세요.")
            workspace = state.get("image_bash_workspace") or {}
            created = not bool(workspace)
            if created:
                workspace = {"workspace_id": str(uuid.uuid4()), "revision": 0, "instances": []}
                state["image_bash_workspace"] = workspace
                self._publish_state(state, preserve_outputs=True)
            try:
                self._hmb_bind_image_bash_workspace(target, workspace["workspace_id"])
            except Exception:
                if created:
                    try:
                        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                        from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeRequest
                        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=target.name, broadcast_result=False))
                        current = self._current_state()
                        if (result.succeeded() and not any(edge.source_node_name == self.name for edge in result.incoming_connections)
                                and current.get("image_bash_workspace") == workspace):
                            current["image_bash_workspace"] = {}
                            current["image_bash_active"] = False
                            self._publish_state(current, preserve_outputs=True)
                    except Exception as exc:
                        _diagnostic_exception("Image Bash preparation rollback requires review", exc)
                raise
            return workspace["workspace_id"]

    def _image_bash_binding_state(self, target: Any, workspace_id: str, expected: Any = None) -> tuple[Any, ...]:
        for node in (self, target):
            resolution = getattr(node, "state", None)
            if (bool(getattr(node, "lock", False)) or bool(getattr(node, "_hmb_node_deleted", False))
                    or _clean(getattr(resolution, "value", resolution)).casefold() == "resolving"
                    or _clean(getattr(resolution, "name", "")).casefold() == "resolving"):
                raise ValueError("ImageAsset와 Image Bash의 실행을 마치고 편집 잠금을 해제하세요.")
        flow_name, nodes = _hmb_shot_routing._same_flow_nodes(self)
        if (not flow_name or type(target).__name__ != "HMBImageBash"
                or not any(node is target for node in nodes)):
            raise ValueError("같은 워크플로에 등록된 Image Bash만 연결할 수 있습니다.")
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        manager = GriptapeNodes.NodeManager()
        if (manager.get_node_by_name(target.name) is not target
                or manager.get_node_parent_flow_by_name(target.name) != flow_name):
            raise ValueError("Image Bash 노드가 교체되었습니다. 다시 선택하세요.")
        state = getattr(self, "_hmb_catalog_search_authority", None)
        if (not isinstance(state, dict) or _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
                != getattr(self, "_hmb_last_accepted_widget_state", None)):
            raise ValueError("ImageAsset 변경을 적용하는 중입니다. 다시 연결하세요.")
        workspace, routing = state["image_bash_workspace"], state["shot_routing"]
        if not workspace or _uuid_text(workspace_id) != workspace["workspace_id"]:
            raise ValueError("Image Bash 작업 공간이 변경되었습니다. 다시 선택하세요.")
        identity = (flow_name, workspace["workspace_id"], workspace["revision"], routing["channel_uuid"], routing["publisher_instance_uuid"])
        if expected is not None and identity != expected:
            raise ValueError("Image Bash 연결 중 작업 공간이 변경되었습니다. 다시 선택하세요.")
        return identity, state, nodes

    def _hmb_bind_image_bash_workspace(self, target_node: Any, workspace_id: str, enabled: bool = True) -> None:
        """Bind exactly two native ports, or release only this source's pair."""
        if type(enabled) is not bool:
            raise ValueError("Image Bash 연결 요청이 올바르지 않습니다.")
        if not hasattr(self, "_hmb_image_bash_binding_lock"):
            self._hmb_image_bash_binding_lock = threading.RLock()
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.events.connection_events import (
            CreateConnectionRequest, DeleteConnectionRequest, ListConnectionsForNodeRequest)
        from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
        target = target_node
        ports = ((IMAGE_BASH_IMAGES_OUTPUT_PARAMETER, "input_images"),
                 (IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER, "image_bash_context"))
        relevant_names = {item[1] for item in ports}
        with self._hmb_image_bash_binding_lock:
            identity, state, nodes = self._image_bash_binding_state(target, workspace_id)
            def check() -> None:
                self._image_bash_binding_state(target, workspace_id, identity)
            def inspect(node: Any) -> Any:
                result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=node.name))
                check()
                if not result.succeeded():
                    raise ValueError("Image Bash 연결 상태를 확인할 수 없습니다.")
                return result
            def relevant(edge: Any) -> bool:
                return edge.target_parameter_name in relevant_names or edge.target_parameter_name.startswith("input_images_")
            incoming = [edge for edge in inspect(target).incoming_connections if relevant(edge)]
            if any(edge.source_node_name != self.name or
                    (edge.source_parameter_name, edge.target_parameter_name) not in ports for edge in incoming):
                raise ValueError("Image Bash에 다른 이미지 원본이 연결되어 있습니다. 기존 연결을 먼저 해제하세요.")
            if (not enabled and not incoming and not (
                    target.metadata.get("hmb_image_bash_workspace_id") == identity[1]
                    and target.metadata.get("hmb_image_bash_channel_uuid") == identity[3])):
                raise ValueError("이 이미지 라이브러리가 소유한 Image Bash 연결이 없습니다.")
            if enabled:
                occupied = [node for node in nodes if node is not target and type(node).__name__ == "HMBImageBash"
                    and node.metadata.get("hmb_image_bash_workspace_id") == identity[1]
                    and node.metadata.get("hmb_image_bash_channel_uuid") == identity[3]]
                outgoing = inspect(self).outgoing_connections
                names = {node.name for node in nodes if node is not target and type(node).__name__ == "HMBImageBash"}
                if occupied or any(edge.target_node_name in names and (edge.source_parameter_name, edge.target_parameter_name) in ports
                                   for edge in outgoing):
                    raise ValueError("이 Image Bash 작업 공간은 다른 노드에 연결되어 있습니다. 먼저 연결을 해제하세요.")
            old_values = {name: copy.deepcopy(target.get_parameter_value(name)) for _, name in ports}
            input_list = target.get_parameter_by_name("input_images")
            old_children = {child.name: child for child in input_list.get_child_parameters()}
            old_child_values = {name: copy.deepcopy(target.get_parameter_value(name)) for name in old_children}
            keys = ("hmb_image_bash_workspace_id", "hmb_image_bash_channel_uuid")
            old_metadata = {key: copy.deepcopy(target.metadata[key]) for key in keys if key in target.metadata}
            created, removed = [], []
            was_syncing = bool(getattr(target, "_hmb_syncing", False))
            target._hmb_syncing = True
            def set_transport(name: str, value: Any, *, restore: bool = False) -> None:
                result = GriptapeNodes.handle_request(SetParameterValueRequest(node_name=target.name,
                    parameter_name=name, value=value, initial_setup=restore,
                    **({"incoming_connection_source_node_name": self.name,
                        "incoming_connection_source_parameter_name": dict((item[1], item[0]) for item in ports)[name]}
                       if enabled and not restore else {})))
                if not result.succeeded():
                    raise ValueError("Image Bash 입력을 갱신할 수 없습니다.")
                if not restore:
                    check()
            try:
                if enabled:
                    # No source publication/target callback occurs until all
                    # lock, ownership, foreign-edge and occupancy checks pass.
                    self._sync_image_bash_output(state)
                    check()
                    for output, input_name in ports:
                        if not any(edge.source_parameter_name == output and edge.target_parameter_name == input_name for edge in incoming):
                            result = GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=self.name,
                                source_parameter_name=output, target_node_name=target.name, target_parameter_name=input_name))
                            if not result.succeeded():
                                raise ValueError("Image Bash 입력 연결을 완료하지 못했습니다. 다시 연결하세요.")
                            created.append((output, input_name))
                            check()
                    actual = [edge for edge in inspect(target).incoming_connections if relevant(edge)]
                    if len(actual) != 2 or {(edge.source_node_name, edge.source_parameter_name, edge.target_parameter_name)
                            for edge in actual} != {(self.name, output, name) for output, name in ports}:
                        raise ValueError("Image Bash의 두 입력 연결을 다시 확인하세요.")
                    images, context = self._hmb_image_bash_snapshot(workspace_id, cached_only=True)
                    for name, value in (("input_images", images), ("image_bash_context", context)):
                        set_transport(name, value)
                    target.metadata.update({keys[0]: identity[1], keys[1]: identity[3]})
                else:
                    for edge in reversed(incoming):
                        result = GriptapeNodes.handle_request(DeleteConnectionRequest(source_node_name=self.name,
                            source_parameter_name=edge.source_parameter_name, target_node_name=target.name,
                            target_parameter_name=edge.target_parameter_name))
                        if not result.succeeded():
                            raise ValueError("Image Bash 연결을 해제할 수 없습니다.")
                        removed.append((edge.source_parameter_name, edge.target_parameter_name))
                        check()
                    set_transport("input_images", [])
                    set_transport("image_bash_context", {})
                    # Without a whole-list wire the SDK aggregates the list's
                    # scalar children again. Retire those local transport
                    # values too; keep their parameters and the Bash scene.
                    for name in old_child_values:
                        current_child = _get_parameter_obj(target, name)
                        if current_child is None:
                            # Some hosts remove list children when the parent
                            # is cleared; there is nothing left to clear.
                            continue
                        if current_child is not old_children[name]:
                            raise ValueError("Image Bash 입력이 연결 해제 중 변경되었습니다.")
                        set_transport(name, None, restore=True)
                        check()
                    for key in keys:
                        target.metadata.pop(key, None)
                check()
            except Exception as binding_error:
                # Roll back only edges changed by this invocation. An older
                # partial pair survives and can be completed by a later bind.
                try:
                    registered = GriptapeNodes.NodeManager().get_node_by_name(target.name) is target
                    if registered:
                        live_children = list(input_list.get_child_parameters())
                        if any(old_children.get(child.name) is not child for child in live_children):
                            raise RuntimeError("Image Bash 입력 목록이 변경되어 자동 복원을 중단했습니다.")
                        for name, child in old_children.items():
                            current = _get_parameter_obj(target, name)
                            if current is not None and current is not child:
                                raise RuntimeError("Image Bash 입력이 교체되어 자동 복원을 중단했습니다.")
                        for output, name in reversed(created):
                            result = GriptapeNodes.handle_request(DeleteConnectionRequest(source_node_name=self.name,
                                source_parameter_name=output, target_node_name=target.name, target_parameter_name=name))
                            if not result.succeeded():
                                raise RuntimeError("Image Bash 연결 복원에 실패했습니다.")
                        for output, name in reversed(removed):
                            result = GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=self.name,
                                source_parameter_name=output, target_node_name=target.name, target_parameter_name=name))
                            if not result.succeeded():
                                raise RuntimeError("Image Bash 연결 복원에 실패했습니다.")
                        for name, value in old_values.items():
                            set_transport(name, value, restore=True)
                        # A parent-list reset can remove the original scalar
                        # child objects on newer hosts. Restore only this
                        # transaction's exact children; never overwrite or
                        # move a child introduced by another owner.
                        live_children = list(input_list.get_child_parameters())
                        if any(old_children.get(child.name) is not child for child in live_children):
                            raise RuntimeError("Image Bash 입력 목록이 변경되어 자동 복원을 중단했습니다.")
                        for index, (name, child) in enumerate(old_children.items()):
                            current = _get_parameter_obj(target, name)
                            if current is None:
                                if getattr(child, "_parent", None) is not None:
                                    raise RuntimeError("Image Bash 입력이 다른 곳으로 이동하여 자동 복원을 중단했습니다.")
                                input_list.add_child(child)
                            elif current is not child:
                                raise RuntimeError("Image Bash 입력이 교체되어 자동 복원을 중단했습니다.")
                            children = list(input_list.get_child_parameters())
                            position = children.index(child)
                            if position != index:
                                input_list.move_child(position, index)
                        for name, value in old_child_values.items():
                            set_transport(name, value, restore=True)
                        for key in keys:
                            if key in old_metadata:
                                target.metadata[key] = old_metadata[key]
                            else:
                                target.metadata.pop(key, None)
                except Exception as rollback_error:
                    _diagnostic_exception("Image Bash binding rollback incomplete", rollback_error)
                    raise ValueError("Image Bash 연결 복원이 완료되지 않았습니다. 입력과 연결 상태를 확인하세요.") from binding_error
                raise
            finally:
                target._hmb_syncing = was_syncing
            if enabled and not was_syncing:
                target._sync_metadata_with_input_images()
            elif not enabled and not was_syncing:
                target._clear_output()
                target._status("REMOTE 연결 해제 · 편집 내용은 유지됩니다")
            publish_header = getattr(target, "_publish_header", None)
            if callable(publish_header) and not was_syncing:
                publish_header()

    def _create_image_bash_workspace_node(self, command: Any) -> str:
        command = _normalize_image_bash_workspace_request(command)
        if not command:
            return ""
        if bool(getattr(self, "lock", False)) or bool(getattr(self, "_hmb_node_deleted", False)) or str(getattr(self, "state", "")).casefold() == "resolving":
            raise ValueError("라이브러리 편집 잠금을 해제한 뒤 Image Bash를 추가하세요.")
        state = self._current_state()
        workspace = state["image_bash_workspace"]
        if not workspace or command["workspace_id"] != workspace["workspace_id"] or command["expected_revision"] != workspace["revision"]:
            raise ValueError("Image Bash 작업 공간이 변경되었습니다. 다시 추가하세요.")
        flow_name, nodes = _hmb_shot_routing._same_flow_nodes(self)
        if not flow_name:
            raise ValueError("현재 라이브러리의 워크플로 등록이 끝난 뒤 Image Bash를 추가하세요.")
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
        from griptape_nodes.node_library.library_registry import LibraryRegistry
        bash_library = LibraryRegistry.get_library_for_node_type("HMBImageBash", WIDGET_LIBRARY_NAME)
        bash_class = bash_library.get_node_class("HMBImageBash")
        # Palette creation and this explicit command share one retained Bash.
        # An unbound node still owns its authored canvas/output; its old lease
        # metadata must not cause a second editor to be created beside it.
        candidates = [node for node in nodes if type(node) is bash_class
            and not bool(getattr(node, "_hmb_node_deleted", False))
            and isinstance(getattr(node, "metadata", None), dict)
            and node.metadata.get("library") == WIDGET_LIBRARY_NAME
            and node.metadata.get("node_type") == "HMBImageBash"]
        if len(candidates) > 1:
            raise ValueError("같은 Image Bash 작업 공간 노드가 여러 개 있습니다. 연결을 확인하세요.")
        if candidates:
            target = candidates[0]
        else:
            position = self.metadata.get("position", {})
            result = GriptapeNodes.handle_request(CreateNodeRequest(node_type="HMBImageBash", specific_library_name=WIDGET_LIBRARY_NAME,
                node_name="HMBImageBash", override_parent_flow_name=flow_name, set_as_new_context=False,
                create_error_proxy_on_failure=False, parent_group_name=getattr(getattr(self, "parent_group", None), "name", None),
                metadata={"hmb_image_bash_workspace_id": workspace["workspace_id"],
                    "hmb_image_bash_channel_uuid": state["shot_routing"]["channel_uuid"],
                    "position": {"x": float(position.get("x", 0)) + ASSET_NODE_WIDTH + 120, "y": float(position.get("y", 0))}}))
            if not result.succeeded():
                raise ValueError("HMB Image Bash 노드를 만들 수 없습니다. 라이브러리 등록 상태를 확인하세요.")
            target = GriptapeNodes.NodeManager().get_node_by_name(result.node_name)
        self._hmb_bind_image_bash_workspace(target, workspace["workspace_id"])
        return target.name

    def _hmb_restore_publication_cursor(self) -> None:
        """Repair an older saved cursor only after live hydration is complete."""
        if bool(getattr(self, "_hmb_restoring_publication_cursor", False)):
            return
        state = self._current_state()
        routing = state["shot_routing"]
        own = max(1, _non_negative_int(routing["generation"]),
                  _non_negative_int(getattr(self, "_hmb_shot_routing_generation", 0)))
        floor = _hmb_shot_routing.restored_shot_catalog_generation_floor(
            self, publisher_instance_uuid=routing["publisher_instance_uuid"],
            channel_uuid=routing["channel_uuid"], current_generation=own,
        )
        if floor <= own:
            self._hmb_publication_cursor_restore_pending = False
            return
        if floor >= 9007199254740991:
            raise ValueError("ImageAsset restored Shot generation exceeds the safe publication range.")
        routing["generation"] = floor + 1
        self._hmb_restoring_publication_cursor = True
        self._hmb_publication_cursor_restore_pending = False
        try:
            self._hmb_shot_routing_input_identity = ""
            self._publish_state(state, normalized=True)
        except Exception:
            self._hmb_publication_cursor_restore_pending = True
            raise
        finally:
            self._hmb_restoring_publication_cursor = False

    def _persist_shot_routing_facts(self, state: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
        """Save the live publication cursor before any peer can accept it.

        UI edits and async selection completion can publish without going through
        _publish_state. Persist only derived routing facts on the matching live
        authored state, never a saved output token or another worker's document.
        """
        raw = _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        baseline = getattr(self, "_hmb_durable_shot_generation", None)
        if (isinstance(baseline, tuple) and len(baseline) == 2
                and raw == baseline[0] and baseline[1] == snapshot.get("generation")):
            return
        current = self._current_state()
        current_routing = current["shot_routing"]
        if current_routing.get("generation") == snapshot.get("generation"):
            return

        def authored_routing(value: Dict[str, Any]) -> tuple:
            routing = value["shot_routing"]
            return (routing["publisher_instance_uuid"], routing["channel_uuid"],
                    tuple((row["shot_uuid"], row["number"], row["name"], row["revision"],
                           tuple(row["selected_source_uids"])) for row in routing["shots"]))

        if authored_routing(current) != authored_routing(state):
            return
        media = getattr(self, "_hmb_import_media_by_uid", {})
        revision = _non_negative_int(getattr(self, "_hmb_import_revision", 0))
        if (_project_output_fingerprint(current, media, revision)
                != _project_output_fingerprint(state, media, revision)):
            return
        if _non_negative_int(current_routing.get("generation")) > _non_negative_int(snapshot.get("generation")):
            return
        _apply_shot_routing_state_facts(current, snapshot)
        serialized = _json_text(current)
        previous_syncing = bool(getattr(self, "_hmb_state_syncing", False))
        self._hmb_state_syncing = True
        try:
            _set_parameter_value(self, WIDGET_STATE_PARAMETER, serialized)
            if _get_parameter_raw(self, WIDGET_STATE_PARAMETER) != serialized:
                raise ValueError("ImageAsset Shot publication could not persist its current routing cursor.")
            self._accept_normalized_widget_state_baseline(current, serialized)
        finally:
            self._hmb_state_syncing = previous_syncing

    def _sync_output(
        self,
        state: Dict[str, Any],
        *,
        force: bool = False,
        normalized: bool = False,
        selection_ready: bool = False,
    ) -> Dict[str, Any]:
        normalized_state = state if normalized else _normalize_state(state)
        work_notice = getattr(self, "_hmb_cgt_work_notice", None)
        if (isinstance(work_notice, tuple) and len(work_notice) == 2
                and work_notice[0] == _hmb_shot_routing.hierarchy_project_key(normalized_state)):
            normalized_state["cgt_work_start_notice"] = dict(work_notice[1])
        normalized = normalized_state
        resolution_cache = self._resolution_cache_for_state(normalized)
        if force:
            work = getattr(self, "_hmb_selection_resolution_work", None)
            if isinstance(work, dict):
                with work["lock"]:
                    work["epoch"] += 1
                    work["queued"] = None
                    work["ready"] = None
        elif self._defer_project_selection_resolution(normalized):
            if normalized.get("image_bash_workspace"):
                self._sync_image_bash_output(normalized, pending=True)
            return normalized
        if normalized.get("image_bash_workspace") or getattr(self, "_hmb_last_image_bash_pair", None) is not None:
            self._sync_image_bash_output(normalized, force=force)
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
            self._persist_shot_routing_facts(normalized, shot_snapshot)
            shot_token = self._shot_asset_dependency_token(shot_snapshot)
            current_shot_output = (
                output_getter(SHOT_ASSET_OUTPUT_PARAMETER)
                if callable(output_getter)
                else None
            )
            if (
                selection_ready
                or current_asset_output != cached_asset_output
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
                    notify_unchanged_shot=selection_ready,
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
        self._persist_shot_routing_facts(normalized, shot_snapshot)
        _stage_and_notify_image_output_pair(
            self,
            asset_output_value,
            media_output_value,
            self._shot_asset_dependency_token(shot_snapshot),
            notify_unchanged_shot=selection_ready,
        )
        return normalized

    @staticmethod
    def _thumbnail_runtime_id(state: Dict[str, Any]) -> str:
        return _clean(
            state.get("shot_routing", {}).get("publisher_instance_uuid")
            if isinstance(state.get("shot_routing"), dict)
            else ""
        )

    def _catalog_search_epoch(self, state: Dict[str, Any]) -> tuple:
        return tuple(_clean(state.get(key)) for key in
            ("project_uid", "project_cache_uid", "project_root", "manifest_signature", "folder_signature")) + (
            self._thumbnail_runtime_id(state), _non_negative_int(state.get("scan_revision")),
            _non_negative_int(getattr(self, "_hmb_import_revision", 0)),
            _non_negative_int(getattr(self, "_hmb_catalog_search_catalog_revision", 0)),
            len(state.get("assets", [])))

    def _catalog_page_projection(self, state: Dict[str, Any], page: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Presentation only. The raw property and routing outputs stay full."""
        page = dict(page or getattr(self, "_hmb_catalog_search_page", {}) or {})
        epoch = self._catalog_search_epoch(state)
        if page.get("epoch") != epoch:
            ids = [_clean(asset.get("asset_library_id")) for asset in state.get("assets", [])
                   if asset.get("source_kind") == "project"][:80]
            page = {"query": "", "folder": "", "source_view": "project", "offset": 0,
                "limit": 80, "total": state.get("status", {}).get("project_asset_count", len(state.get("assets", []))),
                "asset_library_ids": ids, "epoch": epoch}
        wanted = set(page.get("asset_library_ids", []))
        if state is getattr(self, "_hmb_catalog_search_authority", None):
            by_id = self._hmb_catalog_search_assets
            assets = list(self._hmb_catalog_search_selected)
            selected = {_clean(asset.get("asset_library_id")) for asset in assets}
            assets.extend(by_id[key] for key in page.get("asset_library_ids", [])
                          if key in by_id and key not in selected)
        else:
            assets = [asset for asset in state.get("assets", [])
                      if asset.get("selected") or _clean(asset.get("asset_library_id")) in wanted]
        retained = {row["source_uid"] for row in state.get("image_bash_workspace", {}).get("instances", [])}
        existing = {_clean(row.get("source_uid")) for row in assets}
        assets.extend(row for row in state.get("assets", [])
                      if row.get("source_uid") in retained and row.get("source_uid") not in existing)
        # The retained tree repeats every asset ID. The widget derives its
        # folder tree from folders/counts, so never copy that full export here.
        dto = {key: value for key, value in state.items() if key not in {"assets", "catalog_page", "tree"}}
        dto["assets"] = assets
        dto["catalog_page"] = {key: value for key, value in page.items() if key != "epoch"}
        dto["catalog_page"].update(version=1,
            import_revision=_non_negative_int(getattr(self, "_hmb_import_revision", 0)),
            catalog_revision=_non_negative_int(getattr(self, "_hmb_catalog_search_catalog_revision", 0)),
            runtime_instance_id=self._thumbnail_runtime_id(state),
            project_uid=state.get("project_uid", ""), project_cache_uid=state.get("project_cache_uid", ""),
            manifest_signature=state.get("manifest_signature", ""), scan_revision=state.get("scan_revision", 0))
        return dto

    def _consume_catalog_search_result(self) -> bool:
        lock = getattr(self, "_hmb_catalog_search_lock", None)
        if lock is None:
            return False
        with lock:
            ready = list(getattr(self, "_hmb_catalog_search_results", {}).values())
            self._hmb_catalog_search_results = OrderedDict()
        if not ready or not self._scan_owner_is_current():
            return False
        for generation, request, page in ready:
            state = getattr(self, "_hmb_catalog_search_authority", None)
            if (not isinstance(state, dict) or generation != self._hmb_catalog_search_generations.get(request["session_id"])
                    or page["epoch"] != self._catalog_search_epoch(state)):
                continue
            self._hmb_catalog_search_page = page
            self._set_thumbnail_bridge_value({**request, "phase": "result", "outcome": "ready",
                "state": self._catalog_page_projection(state, page)})
        return True

    def _request_catalog_search(self, request: Dict[str, Any]) -> None:
        state = getattr(self, "_hmb_catalog_search_authority", None)
        if not isinstance(state, dict):
            state = self._current_state()
        if (request.get("runtime_instance_id") != self._thumbnail_runtime_id(state)
                or not request.get("session_id") or not request.get("request_id")
                or any(_clean(request.get(key)) != _clean(state.get(key)) for key in
                    ("project_uid", "project_cache_uid", "manifest_signature", "folder_signature"))
                or _non_negative_int(request.get("scan_revision")) != _non_negative_int(state.get("scan_revision"))):
            return
        if not hasattr(self, "_hmb_catalog_search_lock"):
            self._hmb_catalog_search_lock = threading.RLock()
            self._hmb_catalog_search_generation = 0
            self._hmb_catalog_search_generations = {}
            self._hmb_catalog_search_sequences = OrderedDict()
            self._hmb_catalog_search_pending = OrderedDict()
            self._hmb_catalog_search_results = OrderedDict()
            self._hmb_catalog_search_index = None
            self._hmb_catalog_search_index_epoch = None
            self._hmb_catalog_search_thread = None
            self._hmb_catalog_search_builds = 0
        epoch = self._catalog_search_epoch(state)
        with self._hmb_catalog_search_lock:
            session = request["session_id"]
            previous_sequence = self._hmb_catalog_search_sequences.get(session, -1)
            if request["sequence"] <= previous_sequence:
                return
            self._hmb_catalog_search_sequences[session] = request["sequence"]
            self._hmb_catalog_search_sequences.move_to_end(session)
            while len(self._hmb_catalog_search_sequences) > 16:
                retired, _ = self._hmb_catalog_search_sequences.popitem(last=False)
                self._hmb_catalog_search_generations.pop(retired, None)
                self._hmb_catalog_search_pending.pop(retired, None)
                self._hmb_catalog_search_results.pop(retired, None)
            self._hmb_catalog_search_generation += 1
            generation = self._hmb_catalog_search_generation
            self._hmb_catalog_search_generations[session] = generation
            self._hmb_catalog_search_pending[session] = (
                generation, dict(request), epoch,
                getattr(self, "_hmb_catalog_search_projection", ()))
            if self._hmb_catalog_search_thread is not None:
                return
            host_context = contextvars.copy_context()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                try:
                    from griptape_nodes.retained_mode.engine import has_current_engine
                    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                    if has_current_engine():
                        loop = GriptapeNodes.EventManager().event_loop
                except (ImportError, AttributeError):
                    pass
            node_ref = weakref.ref(self)

            def worker() -> None:
                owner = node_ref()
                if owner is None:
                    return
                while True:
                    with owner._hmb_catalog_search_lock:
                        if not owner._hmb_catalog_search_pending:
                            owner._hmb_catalog_search_thread = None
                            return
                        _, job = owner._hmb_catalog_search_pending.popitem(last=False)
                    current_generation, intent, identity, projection = job
                    def epoch_retired() -> bool:
                        live = getattr(owner, "_hmb_catalog_search_authority", {})
                        return bool(getattr(owner, "_hmb_node_deleted", False)) or identity != owner._catalog_search_epoch(live)
                    try:
                        if owner._hmb_catalog_search_index_epoch != identity:
                            fields = ("asset_id", "image_name", "relative_path", "image_main_type",
                                      "image_sub_type", "source_kind", "asset_library_id", "source_uid")
                            index = _ImageCatalogSearchIndex(
                                [dict(zip(fields, row)) for row in projection], epoch_retired)
                            if epoch_retired():
                                continue
                            owner._hmb_catalog_search_index = index
                            owner._hmb_catalog_search_index_epoch = identity
                            owner._hmb_catalog_search_builds += 1
                        index = owner._hmb_catalog_search_index
                        if index is None or epoch_retired():
                            continue
                        page = index.query(intent, lambda: epoch_retired() or current_generation != owner._hmb_catalog_search_generations.get(intent["session_id"]))
                        if epoch_retired():
                            continue
                        page.update({key: intent[key] for key in ("query", "folder", "source_view", "session_id", "sequence")})
                        page.update(epoch=identity, folder_counts=index.folder_counts,
                            index_builds=owner._hmb_catalog_search_builds)
                        with owner._hmb_catalog_search_lock:
                            if current_generation != owner._hmb_catalog_search_generations.get(intent["session_id"]):
                                continue
                            owner._hmb_catalog_search_results[intent["session_id"]] = (current_generation, intent, page)
                        if loop is not None and loop.is_running():
                            loop.call_soon_threadsafe(host_context.copy().run, owner._consume_catalog_search_result)
                    except InterruptedError:
                        continue
                    except Exception as exc:
                        _diagnostic_exception("ImageAsset catalog page preparation failed", exc)

            thread = threading.Thread(target=worker, name="HMB-image-catalog-search", daemon=True)
            self._hmb_catalog_search_thread = thread
            thread.start()

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

    @hmb_binding_mutation
    def _publish_state(
        self,
        state: Dict[str, Any],
        *,
        normalized: bool = False,
        preserve_outputs: bool = False,
    ) -> Dict[str, Any]:
        state = dict(state)
        state["asset_registration_request"] = {}
        state["asset_cleanup_request"] = {}
        state["disconnect_import_uid"] = ""
        state["image_bash_workspace_request"] = {}
        normalized_state = state if normalized else _normalize_state(state)
        normalized = normalized_state
        pending_only = preserve_outputs or bool(
            normalized.get("scan_busy") or normalized.get("thumbnail_busy")
        )
        resolution_pending = False
        if not pending_only:
            resolution_pending = self._defer_project_selection_resolution(normalized)
            pending_only = resolution_pending
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
        elif resolution_pending and normalized.get("image_bash_workspace"):
            self._sync_image_bash_output(normalized, pending=True)
        self._sync_thumbnail_bridge_identity(normalized)
        # Optional finishing UI only; no catalog scan, selection or output change.
        try:
            _hmb_shot_routing.notify_color_lut_project_change(self, normalized)
        except Exception:
            pass
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

    def _ensure_import_thumbnail_runtime_state(self) -> None:
        if not hasattr(self, "_hmb_import_thumbnail_lock"):
            self._hmb_import_thumbnail_lock = threading.RLock()
        if not hasattr(self, "_hmb_import_thumbnail_generation"):
            self._hmb_import_thumbnail_generation = 0
        if not hasattr(self, "_hmb_import_thumbnail_processing_generation"):
            self._hmb_import_thumbnail_processing_generation = 0
        if not hasattr(self, "_hmb_import_thumbnail_active_workers"):
            self._hmb_import_thumbnail_active_workers = 0
        if not hasattr(self, "_hmb_import_thumbnail_queued_task"):
            self._hmb_import_thumbnail_queued_task = None
        if not hasattr(self, "_hmb_import_thumbnail_thread"):
            self._hmb_import_thumbnail_thread = None
        if not hasattr(self, "_hmb_import_thumbnail_pending_result"):
            self._hmb_import_thumbnail_pending_result = None

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
            if outcome == "changed" and isinstance(result_state, dict):
                _prepare_catalog_scan_index(result_state)
            with owner._hmb_catalog_probe_lock:
                # Never hold the node lock during filesystem IO.  A newer
                # request/deletion can proceed while cache preparation waits.
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
        on_published: Callable[[Dict[str, Any]], None] | None = None,
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
                published = owner._publish_completed_catalog_scan(result, key)
                if on_published is not None:
                    owner._run_catalog_publication_callback(on_published, published)
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
                                "on_published": on_published,
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
            _prepare_catalog_scan_index(result, normalized=True)
            with owner._hmb_scan_lock:
                if (
                    generation != owner._hmb_scan_generation
                    or key != owner._hmb_scan_pending_key
                    or bool(getattr(owner, "_hmb_node_deleted", False))
                ):
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
                        "on_published": on_published,
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

    def _run_catalog_publication_callback(
        self, callback: Callable[[Dict[str, Any]], None], published: Dict[str, Any],
    ) -> None:
        previous = bool(getattr(self, "_hmb_catalog_completion_active", False))
        self._hmb_catalog_completion_active = True
        try:
            callback(published)
        finally:
            self._hmb_catalog_completion_active = previous

    def _consume_pending_catalog_scan_result(self) -> bool:
        """Apply a worker result only from a retained-mode/UI callback."""

        self._ensure_scan_runtime_state()
        if bool(getattr(self, "_hmb_catalog_completion_active", False)):
            return False
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
            published = self._publish_completed_catalog_scan(result, key)
            on_published = payload.get("on_published")
            if callable(on_published):
                self._run_catalog_publication_callback(on_published, published)
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
        preserve_outputs = False
        try:
            state = _load_project_catalog(
                root_value or str(DEFAULT_PROJECTS_ROOT),
                previous,
            )
        except Exception as exc:
            # Preserve the last verified pair when an owned project becomes
            # unavailable. Publishing an error must not publish stale media as
            # a fresh successful result.
            preserve_outputs = bool(_clean(previous.get("project_root")))
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
        return self._publish_state(state, preserve_outputs=True) if preserve_outputs else self._publish_state(state)

    def _schedule_catalog_root_change(self, root_value: Any) -> Dict[str, Any]:
        """Acknowledge a picker edit immediately and discover it off-thread."""

        self._hmb_initial_catalog_scan_pending = False
        self._hmb_refresh_authority = None
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
        previous["asset_refresh_review"] = {}
        previous["asset_cleanup_request"] = {}
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

    def _consume_pending_import_thumbnail_result(self) -> bool:
        """Apply a path preview only from the retained-mode callback thread."""

        self._ensure_import_thumbnail_runtime_state()
        with self._hmb_import_thumbnail_lock:
            pending = self._hmb_import_thumbnail_pending_result
            if pending is None:
                return False
            generation, results = pending
            if generation != self._hmb_import_thumbnail_generation:
                self._hmb_import_thumbnail_pending_result = None
                return False
            if self._hmb_import_thumbnail_processing_generation == generation:
                return False
            if not self._scan_owner_is_current():
                self._hmb_import_thumbnail_pending_result = None
                self._hmb_import_thumbnail_thread = None
                return False
            self._hmb_import_thumbnail_processing_generation = generation
        completed = False
        try:
            merged = _merge_live_import_thumbnail_result(
                self._current_state(), results,
            )
            with self._hmb_import_thumbnail_lock:
                if (
                    generation != self._hmb_import_thumbnail_generation
                    or not self._scan_owner_is_current()
                ):
                    return False
            if merged is not None:
                self._publish_state(merged, normalized=True)
            completed = True
            return True
        except Exception as exc:
            _diagnostic_exception(
                "Imported image preview publication failed", exc,
            )
            return False
        finally:
            with self._hmb_import_thumbnail_lock:
                if self._hmb_import_thumbnail_processing_generation == generation:
                    self._hmb_import_thumbnail_processing_generation = 0
                if completed and generation == self._hmb_import_thumbnail_generation:
                    self._hmb_import_thumbnail_pending_result = None
                    self._hmb_import_thumbnail_thread = None

    def _schedule_live_import_thumbnail_hydration(
        self, state: Dict[str, Any],
    ) -> None:
        """Keep validated media immediate while decoding path previews later."""

        self._ensure_import_thumbnail_runtime_state()
        rows = [
            (_clean(asset.get("source_uid")), _clean(asset.get("path")))
            for asset in state.get("assets", [])
            if isinstance(asset, dict)
            and _clean(asset.get("source_kind")) == "user"
            and _non_negative_int(asset.get("import_index")) > 0
            and _clean(asset.get("media_ref_kind")) == "path"
            and _clean(asset.get("source_uid"))
            and _clean(asset.get("path"))
        ]
        with self._hmb_import_thumbnail_lock:
            self._hmb_import_thumbnail_generation += 1
            self._hmb_import_thumbnail_processing_generation = 0
            generation = self._hmb_import_thumbnail_generation
            self._hmb_import_thumbnail_pending_result = None
            self._hmb_import_thumbnail_queued_task = None
        if not rows:
            return
        node_ref = weakref.ref(self)
        host_context = contextvars.copy_context()

        def active_loop() -> Any:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running() and not loop.is_closed():
                    return loop
            except RuntimeError:
                pass
            except Exception:
                pass
            try:
                from griptape_nodes.retained_mode.engine import has_current_engine  # type: ignore
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

                if has_current_engine():
                    loop = GriptapeNodes.EventManager().event_loop
                    if loop.is_running() and not loop.is_closed():
                        return loop
            except Exception:
                pass
            return None

        event_loop = active_loop()

        def is_current() -> bool:
            owner = node_ref()
            if owner is None:
                return False
            with owner._hmb_import_thumbnail_lock:
                return (
                    generation == owner._hmb_import_thumbnail_generation
                    and owner._scan_owner_is_current()
                )

        def run_once() -> None:
            results = _hydrate_live_import_thumbnails(rows, is_current)
            owner = node_ref()
            if owner is None or not is_current():
                return
            with owner._hmb_import_thumbnail_lock:
                if generation != owner._hmb_import_thumbnail_generation:
                    return
                owner._hmb_import_thumbnail_pending_result = (
                    generation, results,
                )
            loop = host_context.copy().run(active_loop) or event_loop
            if loop is not None:
                try:
                    try:
                        loop.call_soon_threadsafe(
                            owner._consume_pending_import_thumbnail_result,
                            context=host_context.copy(),
                        )
                    except TypeError:
                        loop.call_soon_threadsafe(
                            host_context.copy().run,
                            owner._consume_pending_import_thumbnail_result,
                        )
                except Exception as exc:
                    _diagnostic_warning(
                        "Imported image preview callback queue unavailable", exc,
                    )
            # With no running host loop, the next retained-mode callback or
            # process() consumes the saved completion on its own thread.

        def worker() -> None:
            task: Callable[[], None] | None = run_once
            released = False
            try:
                while task is not None:
                    try:
                        task()
                    except Exception as exc:
                        _diagnostic_exception(
                            "Imported image preview worker failed", exc,
                        )
                    owner = node_ref()
                    if owner is None:
                        return
                    with owner._hmb_import_thumbnail_lock:
                        queued = owner._hmb_import_thumbnail_queued_task
                        if queued and queued[0] == owner._hmb_import_thumbnail_generation:
                            task = queued[1]
                            owner._hmb_import_thumbnail_queued_task = None
                        else:
                            owner._hmb_import_thumbnail_active_workers = max(
                                0, owner._hmb_import_thumbnail_active_workers - 1,
                            )
                            released = True
                            return
            finally:
                owner = node_ref()
                if owner is not None and not released:
                    with owner._hmb_import_thumbnail_lock:
                        owner._hmb_import_thumbnail_active_workers = max(
                            0, owner._hmb_import_thumbnail_active_workers - 1,
                        )

        thread = threading.Thread(
            target=worker,
            name=f"HMBImageImportPreview-{generation}",
            daemon=True,
        )
        with self._hmb_import_thumbnail_lock:
            if generation != self._hmb_import_thumbnail_generation:
                return
            if self._hmb_import_thumbnail_active_workers >= 2:
                # Keep only the newest pending input. An older blocked decoder
                # must not create an unbounded thread for every rapid edit.
                self._hmb_import_thumbnail_queued_task = (generation, run_once)
                return
            self._hmb_import_thumbnail_active_workers += 1
            self._hmb_import_thumbnail_thread = thread
            try:
                thread.start()
            except Exception as exc:
                self._hmb_import_thumbnail_active_workers = max(
                    0, self._hmb_import_thumbnail_active_workers - 1,
                )
                if generation == self._hmb_import_thumbnail_generation:
                    self._hmb_import_thumbnail_thread = None
                _diagnostic_warning("Imported image preview worker unavailable", exc)

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
            self._schedule_live_import_thumbnail_hydration(published)
            self._hmb_last_applied_import_identity = input_identity
            return published
        try:
            previous_imports = {_clean(row.get("source_uid")) for row in state.get("assets", [])}
            feedback_uids = set()
            workspace = state.get("image_bash_workspace") or {}
            if workspace:
                try:
                    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                    for edge in _import_connection_snapshot(self).incoming_connections:
                        if (_clean(getattr(edge, "source_parameter_name", "")) != "output_image"
                                or not _clean(getattr(edge, "target_parameter_name", "")).startswith(IMAGE_IMPORT_PARAMETER)):
                            continue
                        owner = GriptapeNodes.NodeManager().get_node_by_name(edge.source_node_name)
                        metadata = getattr(owner, "metadata", {})
                        if (type(owner).__name__ != "HMBImageBash"
                                or metadata.get("hmb_image_bash_workspace_id") != workspace.get("workspace_id")
                                or metadata.get("hmb_image_bash_channel_uuid") != state["shot_routing"]["channel_uuid"]):
                            continue
                        output = getattr(owner, "parameter_output_values", {}).get("output_image")
                        for item in _flatten_import_values(output):
                            record = _import_record(item, 1, defer_thumbnail=True)
                            if record:
                                feedback_uids.add(record[0]["source_uid"])
                except Exception as exc:
                    _diagnostic_warning("Image Bash feedback classification unavailable", exc)
            state, media_by_uid = _merge_import_input(
                state, value, defer_thumbnail=True,
            )
            if feedback_uids:
                for row in state.get("assets", []):
                    if row.get("source_uid") in feedback_uids and row.get("source_uid") not in previous_imports:
                        row["selected"] = False
                        row["selection_order"] = 0
                state = _normalize_state(state)
            self._replace_import_media(media_by_uid)
            previous_import_publication = bool(getattr(self, "_hmb_unrelated_import_publication", False))
            self._hmb_unrelated_import_publication = True
            try:
                published = self._publish_state(state)
            finally:
                self._hmb_unrelated_import_publication = previous_import_publication
            self._schedule_live_import_thumbnail_hydration(published)
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
        *,
        defer_thumbnail: bool = False,
    ) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
        if not _flatten_import_values(import_value):
            return state, None
        merged, media_by_uid = _merge_import_input(
            state, import_value, defer_thumbnail=defer_thumbnail,
        )
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
        if (current_signature == _clean(normalized.get("manifest_signature"))
                and _project_root_text(selected["path"]).casefold()
                == _project_root_text(normalized.get("project_root")).casefold()
                and _project_root_text(catalog["catalog_root"]).casefold()
                == _project_root_text(normalized.get("catalog_root")).casefold()):
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

    def _schedule_project_manifest_refresh(
        self, state: Dict[str, Any], catalog_root: str, import_value: Any
    ) -> Dict[str, Any]:
        """Explicit Refresh only: audit in the worker, never prune implicitly."""
        self._hmb_refresh_authority = None
        state = dict(state)
        state["asset_refresh_review"] = {}
        token = uuid.uuid4().hex
        project_root = _project_root_text(state.get("project_root"))
        effective_project_root = project_root
        report: Dict[str, Any] = {}

        def refresh() -> Any:
            nonlocal effective_project_root
            if project_root:
                effective_project_root = _project_root_text(project_root)
                audit = _audit_project_manifest_refresh(Path(effective_project_root))
                report.update(audit)
                report.update({
                    "request_id": token,
                    "project_uid": _clean(state.get("project_uid")),
                    "project_id": _clean(state.get("project_id")),
                    "status": "error" if audit.get("error") else "review",
                })
                if audit.get("error"):
                    # Do not replace a verified catalog with a partial share walk.
                    return state
            loaded = _load_project_catalog(catalog_root, state, use_shared_cache=False)
            if project_root and (
                _project_root_text(loaded.get("project_root")).casefold() != effective_project_root.casefold()
                or _clean(loaded.get("project_uid")) != _clean(state.get("project_uid"))
            ):
                raise ValueError("The selected project is no longer available; the previous catalog was retained.")
            return self._merge_captured_imports_into_scan(loaded, import_value)

        def merge(result: Dict[str, Any], base: Dict[str, Any], live: Dict[str, Any]) -> Dict[str, Any]:
            merged = _merge_async_scan_result_with_live_state(result, base, live)
            if not project_root:
                return merged
            if result.get("error"):
                report.update({"request_id": token, "project_root": effective_project_root,
                               "status": "error", "safe_to_clean": False,
                               "error": _clean(result.get("error"))})
            same_project = (
                _project_root_text(merged.get("project_root")).casefold() == effective_project_root.casefold()
                and _clean(merged.get("project_uid")) == _clean(state.get("project_uid"))
            )
            if same_project:
                merged["asset_refresh_review"] = _normalize_asset_refresh_review(report)
                if report.get("error"):
                    merged["error"] = _clean(report["error"])
                if report.get("safe_to_clean") and not report.get("error"):
                    # Assigned only after the scheduler's owner/generation guard.
                    self._hmb_refresh_authority = copy.deepcopy(report)
            return _normalize_state(merged)

        return self._schedule_catalog_scan(
            f"refresh:{catalog_root.casefold()}:{_non_negative_int(state.get('refresh_revision'))}",
            state, refresh, failure_state=state, result_merger=merge,
        )

    def _schedule_project_manifest_cleanup(
        self, state: Dict[str, Any], request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Consume one locally issued review token, then revalidate under lock."""
        self._ensure_scan_runtime_state()
        token = _clean(request.get("request_id"))
        key = f"refresh-cleanup:{token}"
        if self._hmb_scan_pending_key == key:
            return self._current_state()
        authority = getattr(self, "_hmb_refresh_authority", None)
        valid = (
            isinstance(authority, dict)
            and token and token == authority.get("request_id")
            and authority.get("safe_to_clean") is True
            and _project_root_text(authority.get("project_root")).casefold()
            == _project_root_text(state.get("project_root")).casefold()
            and _clean(authority.get("project_uid")) == _clean(state.get("project_uid"))
            and self._scan_owner_is_current()
        )
        if not valid:
            failed = dict(state)
            message = "Refresh this project again before confirming registration cleanup."
            failed["asset_refresh_review"] = {
                **dict(state.get("asset_refresh_review") or {}),
                "request_id": token or uuid.uuid4().hex,
                "project_root": _clean(state.get("project_root")),
                "status": "error", "safe_to_clean": False, "error": message,
            }
            failed["error"] = message
            return self._publish_state(failed)
        confirmed = copy.deepcopy(authority)
        self._hmb_refresh_authority = None  # Single use; even failure needs a new review.
        expected_generation = self._hmb_scan_generation + 1
        report: Dict[str, Any] = dict(confirmed)
        report["safe_to_clean"] = False
        captured_import = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)

        def is_current() -> bool:
            if (bool(getattr(self, "_hmb_node_deleted", False))
                or self._hmb_scan_generation != expected_generation
                or self._hmb_scan_pending_key != key):
                return False
            current = self._current_state()
            return (
                _project_root_text(current.get("project_root")).casefold()
                == _project_root_text(confirmed.get("project_root")).casefold()
                and _clean(current.get("project_uid")) == _clean(confirmed.get("project_uid"))
            )

        def cleanup() -> Any:
            cleaned = _clean_project_manifest_refresh(confirmed, is_current)
            report.update(cleaned)
            report.update({"request_id": token, "status": "cleaned", "safe_to_clean": False})
            if cleaned.get("backup_warning"):
                report["error"] = "\n".join(filter(None, (
                    _clean(report.get("error")), _clean(cleaned["backup_warning"])
                )))
            if cleaned.get("error"):
                # The manifest commit succeeded; retain the last usable catalog
                # if the share became unavailable during post-write verification.
                return state
            loaded = _load_project_catalog(
                state["catalog_root"], state, use_shared_cache=False
            )
            if (
                _project_root_text(loaded.get("project_root")).casefold()
                != _project_root_text(confirmed.get("project_root")).casefold()
                or _clean(loaded.get("project_uid")) != _clean(confirmed.get("project_uid"))
            ):
                raise ValueError("Registration cleanup completed, but the project became unavailable; the previous catalog was retained.")
            return self._merge_captured_imports_into_scan(loaded, captured_import)

        def merge(result: Dict[str, Any], base: Dict[str, Any], live: Dict[str, Any]) -> Dict[str, Any]:
            merged = _merge_async_scan_result_with_live_state(result, base, live)
            if result.get("error"):
                report.update({"status": "cleaned" if report.get("cleaned_count") else "error", "safe_to_clean": False,
                               "error": _clean(result["error"])})
            merged["asset_refresh_review"] = _normalize_asset_refresh_review(report)
            if report.get("error"):
                merged["error"] = _clean(report["error"])
            return _normalize_state(merged)

        return self._schedule_catalog_scan(
            key, state, cleanup, failure_state=state, result_merger=merge
        )

    @hmb_binding_mutation
    def _apply_widget_state(self, value: Any) -> Dict[str, Any]:
        state = _normalize_state(self._expand_widget_edit(value))
        cleanup_request = dict(state.get("asset_cleanup_request") or {})
        state["asset_cleanup_request"] = {}
        # A displayed report is not a durable permission to modify a project.
        # Switching projects invalidates both the report and its private token.
        authority = getattr(self, "_hmb_refresh_authority", None)
        if isinstance(authority, dict) and (
            _project_root_text(authority.get("project_root")).casefold()
            != _project_root_text(state.get("project_root")).casefold()
            or _clean(authority.get("project_uid")) != _clean(state.get("project_uid"))
        ):
            self._hmb_refresh_authority = None
        review = state.get("asset_refresh_review") or {}
        if review and _project_root_text(review.get("project_root")).casefold() != _project_root_text(state.get("project_root")).casefold():
            state["asset_refresh_review"] = {}
        if cleanup_request:
            return self._schedule_project_manifest_cleanup(state, cleanup_request)
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
            cleanup_edges: List[tuple[Any, str, str]] = []
            cleanup_capture_error = ""
            if _clean(request_snapshot.get("source_kind")) == "user":
                try:
                    cleanup_edges = _capture_import_registration_edges(
                        self, _clean(request_snapshot.get("source_uid")),
                    )
                except Exception as exc:
                    cleanup_capture_error = str(exc)

            def register_and_patch() -> Any:
                registered = _apply_asset_registration(
                    state,
                    request_snapshot,
                    captured_import_media,
                )
                if not _flatten_import_values(captured_import_value):
                    return registered
                return _merge_import_input(registered, captured_import_value)

            cleanup_finished = False

            def finish_registration(published: Dict[str, Any]) -> None:
                nonlocal cleanup_finished
                if cleanup_finished:
                    return
                cleanup_finished = True
                result = dict(published.get("asset_registration_result") or {})
                if (not result.get("ok")
                    or _clean(result.get("request_id")) != _clean(request_snapshot.get("request_id"))
                    or _clean(request_snapshot.get("source_kind")) != "user"
                    or not self._scan_owner_is_current()):
                    return
                # Publication above transfers every Shot and its authored Prompt
                # row before any connection callback can retire the live import.
                warnings = []
                if cleanup_capture_error:
                    warnings.append("The registered image is saved; input cleanup was unavailable.")
                try:
                    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                    for source_node, source_parameter, target_name in cleanup_edges:
                        try:
                            # A changed/replaced connection during a slow Add is
                            # newer user intent; never delete it by display index.
                            snapshot = _import_connection_snapshot(self)
                            current = [edge for edge in snapshot.incoming_connections
                                       if _clean(getattr(edge, "target_parameter_name", "")) == target_name]
                            if not current:
                                _remove_import_child_parameter(self, target_name)
                                continue
                            if (len(current) != 1
                                or GriptapeNodes.NodeManager().get_node_by_name(current[0].source_node_name) is not source_node
                                or _clean(current[0].source_parameter_name) != source_parameter):
                                warnings.append("An input changed during Add and was left connected.")
                                continue
                            _retire_registered_import_connection(
                                self, _clean(request_snapshot.get("source_uid")), target_name,
                                previous_assets=state.get("assets", []),
                            )
                        except Exception as exc:
                            warnings.append(f"Registered image saved; input cleanup: {exc}")
                    if not cleanup_edges and not cleanup_capture_error and _flatten_import_values(
                        _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
                    ):
                        warnings.append("A shared/multi-image input was retained to preserve its other images.")
                except Exception as exc:
                    warnings.append(f"Registered image saved; input cleanup: {exc}")
                if warnings:
                    state_now = dict(self._current_state())
                    result["message"] = " ".join(filter(None, (
                        _clean(result.get("message")), *dict.fromkeys(warnings),
                    )))
                    state_now["asset_registration_result"] = result
                    self._publish_state(state_now)

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
                on_published=finish_registration,
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
            self._hmb_refresh_authority = None
            state["asset_refresh_review"] = {}
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
            return self._schedule_project_manifest_refresh(
                state, requested_catalog, captured_import_value
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

    def _queue_cgt_work_start(self, request: Dict[str, Any], previous: Dict[str, Any], committed: Dict[str, Any]) -> None:
        """Notify a successful explicit commit, independently of dialog reads.

        The CGT child owns its durable single-write claim. This queue is never
        populated by Run, catalog/preview, serialization, or workflow restore.
        """
        before = copy.deepcopy(previous.get("shot_hierarchy") or {})
        binding = copy.deepcopy(committed.get("shot_hierarchy") or {})
        candidates = [m for m in binding.get("members", []) if m.get("origin") == "cgt"]
        if not any(member.get("status") == "Wait" for member in candidates):
            return
        identity = _hmb_shot_routing.hierarchy_project_key(committed)
        operation = "cgt-" + _sha256_canonical({"session": request["session_id"], "request": request["request_id"],
            "project": identity, "members": sorted(m["cgt_task_id"] for m in candidates)})
        if not hasattr(self, "_hmb_cgt_work_lock"):
            self._hmb_cgt_work_lock = threading.RLock()
            self._hmb_cgt_work_seen = set()
            self._hmb_cgt_work_pending = []
            self._hmb_cgt_work_ready = []
            self._hmb_cgt_work_thread = None
        with self._hmb_cgt_work_lock:
            if operation in self._hmb_cgt_work_seen:
                return
            if len(self._hmb_cgt_work_pending) >= 8 or len(self._hmb_cgt_work_seen) >= 256:
                raise RuntimeError("CGT start notification queue is full")
            self._hmb_cgt_work_seen.add(operation)
            notice = _normalize_cgt_work_start_notice({"schema": "hmb-cgt-work-start-notice-v1",
                "request_id": operation, "status": "queued"})
            self._hmb_cgt_work_notice = (identity, notice)
            self._publish_state({**committed, "cgt_work_start_notice": notice}, preserve_outputs=True)
            self._hmb_cgt_work_pending.append({"operation": operation, "identity": identity,
                "project_id": _clean(committed.get("project_id")), "previous": before, "binding": binding,
                "cgt_project_id": (binding.get("cgt_scope") or {}).get("project_id")})
            if self._hmb_cgt_work_thread is not None:
                return
            context = contextvars.copy_context()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                try:
                    from griptape_nodes.retained_mode.engine import has_current_engine
                    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                    if has_current_engine():
                        loop = GriptapeNodes.EventManager().event_loop
                except (ImportError, AttributeError):
                    pass
            owner = self

            def worker() -> None:
                import _hmb_cgt
                while True:
                    with owner._hmb_cgt_work_lock:
                        if not owner._hmb_cgt_work_pending:
                            owner._hmb_cgt_work_thread = None
                            return
                        job = owner._hmb_cgt_work_pending.pop(0)
                    try:
                        result = _hmb_cgt.start_own_wait_after_commit(job["project_id"],
                            previous_binding=job["previous"], committed_binding=job["binding"],
                            commit_request_id=job["operation"], cgt_project_id=job["cgt_project_id"], include_bound_wait=True)
                    except Exception:
                        result = {"schema": "hmb-cgt-work-start-result-v1", "status": "unknown", "failed_count": 1}
                    with owner._hmb_cgt_work_lock:
                        owner._hmb_cgt_work_ready.append((job, result))
                    if loop is not None and loop.is_running():
                        loop.call_soon_threadsafe(context.copy().run, owner._consume_cgt_work_results)

            self._hmb_cgt_work_thread = threading.Thread(target=worker, name="HMB-CGT-work-start", daemon=True)
            self._hmb_cgt_work_thread.start()

    @hmb_binding_mutation
    def _consume_cgt_work_results(self) -> None:
        lock = getattr(self, "_hmb_cgt_work_lock", None)
        if lock is None:
            return
        with lock:
            ready, self._hmb_cgt_work_ready = self._hmb_cgt_work_ready, []
        for job, result in ready:
            if bool(getattr(self, "_hmb_node_deleted", False)) or not self._scan_owner_is_current():
                continue
            current = self._current_state()
            if _hmb_shot_routing.hierarchy_project_key(current) != job["identity"]:
                continue
            binding = current.get("shot_hierarchy") or {}
            if binding.get("cgt_scope") != job["binding"].get("cgt_scope"):
                continue
            # Rebase only authenticated factual status, never names, grouping,
            # Shot UUIDs, inputs, or media. A newer status wins over this reply.
            old = {m.get("cgt_task_id"): m for m in job["binding"].get("members", []) if m.get("origin") == "cgt"}
            observed = {m.get("task_id"): m for m in result.get("observed_tasks", []) if isinstance(m, dict)}
            changed = False
            for member in binding.get("members", []):
                prior, fact = old.get(member.get("cgt_task_id")), observed.get(member.get("cgt_task_id"))
                if (member.get("origin") != "cgt" or not prior or not fact
                        or any(member.get(k) != prior.get(k) for k in ("cgt_identity", "source_name", "artist", "status"))
                        or member.get("cgt_identity") != fact.get("identity")
                        or member.get("source_name") != fact.get("source_name") or member.get("artist") != fact.get("artist")):
                    continue
                status = fact.get("status")
                if (isinstance(status, str) and status and len(status) <= 256
                        and all(ord(char) >= 32 for char in status) and status != member.get("status")):
                    member["status"] = status
                    changed = True
            if changed:
                binding["revision"] = min((1 << 53) - 1, _non_negative_int(binding.get("revision")) + 1)
                current["shot_hierarchy"] = binding
            active = getattr(self, "_hmb_cgt_work_notice", None)
            if active and active[1].get("request_id") == job["operation"]:
                status = result.get("status") if result.get("schema") == "hmb-cgt-work-start-result-v1" else "unknown"
                notice = _normalize_cgt_work_start_notice({**result, "schema": "hmb-cgt-work-start-notice-v1",
                    "status": status if status in {"completed", "partial", "failed", "unknown"} else "unknown",
                    "request_id": job["operation"]})
                self._hmb_cgt_work_notice = (job["identity"], notice)
                current["cgt_work_start_notice"] = notice
            self._publish_state(current, preserve_outputs=True)

    def _request_cgt_read(self, request: Dict[str, Any]) -> None:
        """One bounded worker, newest pending intent, host-loop-only publication."""
        current = self._current_state()
        if (request.get("runtime_instance_id") != self._thumbnail_runtime_id(current)
                or request.get("project_identity") != _hmb_shot_routing.hierarchy_project_key(current)
                or not request.get("session_id") or not request.get("request_id")):
            return
        if not hasattr(self, "_hmb_cgt_lock"):
            self._hmb_cgt_lock = threading.RLock()
            self._hmb_cgt_generation = 0
            self._hmb_cgt_pending = None
            self._hmb_cgt_ready = None
            self._hmb_cgt_thread = None
        with self._hmb_cgt_lock:
            self._hmb_cgt_generation += 1
            generation = self._hmb_cgt_generation
            if request["operation"] == "cgt_cancel":
                self._hmb_cgt_pending = None
                self._hmb_cgt_ready = None
                return
            command = request.get("hierarchy_request")
            if request["operation"] == "cgt_confirm":
                if bool(getattr(self, "lock", False)) or str(getattr(self, "state", "")).casefold() == "resolving":
                    return
                # Validate the complete transaction before any network request.
                _hmb_shot_routing.apply_shot_hierarchy_edit(current, command)
                scope_id = ((command.get("binding") or {}).get("cgt_scope") or {}).get("project_id")
                if (request.get("cgt_project_id") and scope_id
                        and request["cgt_project_id"].lower() != scope_id.lower()):
                    raise ValueError("확정할 CGT 프로젝트가 선택한 샷 범위와 다릅니다.")
                request = dict(request, cgt_project_id=scope_id or request.get("cgt_project_id", ""))
            self._hmb_cgt_pending = (generation, copy.deepcopy(request), _clean(current.get("project_id")))
            if self._hmb_cgt_thread is not None:
                return
            host_context = contextvars.copy_context()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                try:
                    from griptape_nodes.retained_mode.engine import has_current_engine
                    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
                    if has_current_engine():
                        loop = GriptapeNodes.EventManager().event_loop
                except (ImportError, AttributeError):
                    pass
            node_ref = weakref.ref(self)

            def worker() -> None:
                import _hmb_cgt
                owner = node_ref()
                if owner is None:
                    return
                while True:
                    with owner._hmb_cgt_lock:
                        job = owner._hmb_cgt_pending
                        owner._hmb_cgt_pending = None
                        if job is None:
                            owner._hmb_cgt_thread = None
                            return
                    serial, intent, project_id = job
                    command = intent.get("hierarchy_request") or {}
                    binding = command.get("binding") if intent["operation"] == "cgt_confirm" else None
                    try:
                        result = _hmb_cgt.catalog(project_id, binding=binding,
                            cgt_project_id=intent.get("cgt_project_id") or None)
                    except Exception:
                        result = {"status": "SDK_UNAVAILABLE", "tasks": [], "projects": []}
                    with owner._hmb_cgt_lock:
                        if serial != owner._hmb_cgt_generation or bool(getattr(owner, "_hmb_node_deleted", False)):
                            continue
                        owner._hmb_cgt_ready = (serial, intent, project_id, result)
                    if loop is not None and loop.is_running():
                        loop.call_soon_threadsafe(host_context.copy().run, owner._consume_cgt_result)

            self._hmb_cgt_thread = threading.Thread(target=worker, name="HMB-CGT-own-tasks", daemon=True)
            self._hmb_cgt_thread.start()

    def _consume_cgt_result(self) -> None:
        lock = getattr(self, "_hmb_cgt_lock", None)
        if lock is None:
            return
        with lock:
            ready = self._hmb_cgt_ready
            self._hmb_cgt_ready = None
            if not ready or ready[0] != self._hmb_cgt_generation or bool(getattr(self, "_hmb_node_deleted", False)):
                return
        serial, request, project_id, result = ready
        current = self._current_state()
        if (request["runtime_instance_id"] != self._thumbnail_runtime_id(current)
                or request["project_identity"] != _hmb_shot_routing.hierarchy_project_key(current)
                or project_id != _clean(current.get("project_id"))):
            result = {"status": "SOURCE_CHANGED", "tasks": [], "projects": []}
        outcome = "ready" if result.get("status") == "ready" else "rejected"
        if request["operation"] == "cgt_confirm" and outcome == "ready":
            try:
                import _hmb_cgt
                command = request["hierarchy_request"]
                if bool(getattr(self, "lock", False)) or str(getattr(self, "state", "")).casefold() == "resolving":
                    raise ValueError("Griptape 편집 잠금")
                _hmb_cgt.verify_binding(command["binding"], project_id, result)
                prepared = _hmb_shot_routing.apply_shot_hierarchy_edit(current, command)
                try:
                    self._publish_state(prepared)
                except Exception:
                    # A local publication failure must not strand a partially
                    # accepted name/binding snapshot or trigger another CGT read.
                    self._publish_state(current)
                    raise
                outcome = "committed"
                try:
                    self._queue_cgt_work_start(request, current, prepared)
                except Exception:
                    # The accepted Shot commit is not rolled back because its
                    # optional CGT start notification could not be queued.
                    notice = _normalize_cgt_work_start_notice({"schema": "hmb-cgt-work-start-notice-v1",
                        "request_id": "cgt-" + _sha256_canonical(request["request_id"]), "status": "failed", "failed_count": 1})
                    self._hmb_cgt_work_notice = (_hmb_shot_routing.hierarchy_project_key(prepared), notice)
                    try:
                        self._publish_state({**prepared, "cgt_work_start_notice": notice}, preserve_outputs=True)
                    except Exception:
                        _LOGGER.warning("CGT start notice could not be published; the accepted Shot commit is retained.")
                # The live list belongs to this dialog, not to persistent native
                # media/Prompt/Agent state. Save only the confirmed binding.
                result = {"status": "committed"}
            except Exception:
                outcome = "rejected"
                result = {"status": "SOURCE_CHANGED", "tasks": [], "projects": []}
        response = {key: request[key] for key in ("schema", "version", "runtime_instance_id", "session_id", "request_id", "project_identity", "operation")}
        response["cgt_project_id"] = request.get("cgt_project_id", "")
        response.update(phase="result", outcome=outcome, state=result)
        self._set_thumbnail_bridge_value(response)

    def _apply_thumbnail_bridge_request(self, value: Any) -> None:
        self._consume_cgt_work_results()
        early = _normalize_thumbnail_bridge(value)
        if early.get("operation") == "cgt_cancel" and early.get("phase") == "request":
            self._request_cgt_read(early)
            return
        self._consume_cgt_result()
        self._consume_catalog_search_result()
        self._consume_pending_catalog_probe_result()
        bridge = _normalize_thumbnail_bridge(value)
        if bridge.get("operation") in {"cgt_catalog", "cgt_confirm", "cgt_cancel"} and bridge.get("phase") == "request":
            self._request_cgt_read(bridge)
            return
        if bridge.get("operation") == "catalog_page" and bridge.get("phase") == "request":
            self._request_catalog_search(bridge)
            return
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
        name = _clean(getattr(parameter, "name", ""))
        previous: Dict[str, Any] = {}
        external_state = name == WIDGET_STATE_PARAMETER and not (
            bool(getattr(self, "_hmb_state_syncing", False)) or bool(getattr(self, "_hmb_restoring_widget_state", False))
        )
        if external_state:
            value = dict(_parse_mapping(value))
            if (value.get("schema") == STATE_SCHEMA and _clean(value.get("project_root"))
                    and not any(_clean(value.get(key)) for key in ("project_id", "project_uid", "project_cache_uid"))):
                previous = dict(_parse_mapping(getattr(self, "_hmb_last_accepted_widget_state", None)))
        original_value = value
        taken_selection = None
        if not bool(getattr(self, "_hmb_state_syncing", False)) and not bool(
            getattr(self, "_hmb_restoring_widget_state", False)
        ):
            if previous:
                rebased = HMBImageAssetLibrary._take_pending_project_selection(self, value, previous)
                if rebased is not None:
                    taken_selection = rebased
                    value = rebased
            self._consume_pending_catalog_scan_result()
            self._consume_pending_thumbnail_result()
            self._consume_pending_catalog_probe_result()
            if taken_selection is not None:
                latest = dict(_parse_mapping(self._hmb_last_accepted_widget_state))
                if latest != previous:
                    # A later probe/thumbnail completion owns these facts, even
                    # when it used the same scan clock. Preserve the ready
                    # scan's proven clock, but never overwrite newer facts.
                    latest["scan_revision"] = max(_non_negative_int(latest.get("scan_revision")),
                                                  _non_negative_int(taken_selection.get("scan_revision")))
                    rebased = HMBImageAssetLibrary._rebase_fresh_project_selection(original_value, previous, latest)
                    if rebased is None or not self._scan_owner_is_current():
                        return self._hmb_last_accepted_widget_state
                    value = rebased
        if name == WIDGET_STATE_PARAMETER:
            raw_state = self._expand_widget_edit(value)
            if not bool(getattr(self, "_hmb_restoring_widget_state", False)):
                authority = getattr(self, "_hmb_cgt_work_notice", None)
                accepted = _parse_mapping(getattr(self, "_hmb_last_accepted_widget_state", {}))
                retained_notice = (authority[1] if authority and authority[0] == _hmb_shot_routing.hierarchy_project_key(raw_state)
                    else accepted.get("cgt_work_start_notice") if _hmb_shot_routing.hierarchy_project_key(accepted) == _hmb_shot_routing.hierarchy_project_key(raw_state) else {})
                raw_state["cgt_work_start_notice"] = _normalize_cgt_work_start_notice(retained_notice)
            poll_nonce = _clean(raw_state.pop("__hmb_manifest_poll_nonce", ""))[:128]
            # Poll flags describe this exact value-set only.  In particular,
            # never leave a pending flag behind when an unchanged canonical
            # value is suppressed by the host and no post-set hook follows.
            self._hmb_manifest_poll_received = False
            self._hmb_manifest_poll_pending = False
            if not poll_nonce:
                if self._widget_state_is_stale(raw_state):
                    latest = dict(_parse_mapping(self._hmb_last_accepted_widget_state))
                    rebased = HMBImageAssetLibrary._rebase_fresh_project_selection(original_value, previous, latest) if previous else None
                    if rebased is None or not self._scan_owner_is_current():
                        return self._hmb_last_accepted_widget_state
                    raw_state = rebased
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

    @hmb_binding_mutation
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
        self._consume_pending_import_thumbnail_result()
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
                if _parse_mapping(value).get("schema") == IMAGE_ASSET_EDIT_SCHEMA:
                    try:
                        value = _json_text(self._expand_widget_edit(value))
                    except ValueError:
                        self._restore_accepted_widget_state()
                        raise
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
                command = _parse_mapping(value).get("image_bash_workspace_request")
                if command:
                    # A presentation-only edit can leave all normal Shot
                    # outputs unchanged, so _apply_widget_state need not
                    # publish. Consume explicit intent even on that path (or
                    # on a partial wiring failure) before performing it.
                    self._publish_state(self._current_state())
                    self._create_image_bash_workspace_node(command)
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
                if (not bool(getattr(self, "_hmb_import_cleanup_active", False))
                    and _clean(getattr(target_parameter, "name", "")) != IMAGE_IMPORT_PARAMETER):
                    # A manually severed wire retires its empty UUID slot too.
                    # The native list reindexes labels without renaming survivors.
                    _defer_empty_import_child_cleanup(self, target_parameter.name)
        except Exception as exc:
            _diagnostic_exception("Image import disconnect synchronization failed", exc)
        return result

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        self._hmb_publication_cursor_restore_pending = True
        self._hmb_refresh_authority = None
        removal_state = getattr(self, "_hmb_import_child_removal_state", None)
        if isinstance(removal_state, dict):
            with removal_state["lock"]:
                for key in ("retired", "generations", "pending"):
                    removal_state[key].clear()
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
        self._ensure_import_thumbnail_runtime_state()
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
        with self._hmb_import_thumbnail_lock:
            self._hmb_import_thumbnail_generation += 1
            self._hmb_import_thumbnail_processing_generation = 0
            self._hmb_import_thumbnail_queued_task = None
            self._hmb_import_thumbnail_pending_result = None
            self._hmb_import_thumbnail_thread = None
        with self._hmb_catalog_probe_lock:
            self._hmb_catalog_probe_generation += 1
            self._hmb_catalog_probe_pending_key = ""
            self._hmb_catalog_probe_pending_result = None
            self._hmb_catalog_probe_thread = None
        self._hmb_initial_catalog_scan_pending = False
        self._hmb_fresh_registration_scan_key = ""
        saved_state = dict(self._current_state())
        saved_state["asset_refresh_review"] = {}
        saved_state["asset_cleanup_request"] = {}
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
                defer_thumbnail=True,
            )
            if isinstance(indexed_media, dict):
                self._replace_import_media(indexed_media)
            indexed_state = self._publish_state(indexed_state)
            self._schedule_live_import_thumbnail_hydration(indexed_state)
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
        self._ensure_import_thumbnail_runtime_state()
        first_delete = not bool(getattr(self, "_hmb_node_deleted", False))
        if first_delete:
            self._hmb_node_deleted = True
            search_lock = getattr(self, "_hmb_catalog_search_lock", None)
            if search_lock is not None:
                with search_lock:
                    self._hmb_catalog_search_pending.clear()
                    self._hmb_catalog_search_results.clear()
                    self._hmb_catalog_search_generations.clear()
                    self._hmb_catalog_search_index = None
                    self._hmb_catalog_search_index_epoch = None
            _release_import_child_removal_observers(self)
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
            with self._hmb_import_thumbnail_lock:
                self._hmb_import_thumbnail_generation += 1
                self._hmb_import_thumbnail_processing_generation = 0
                self._hmb_import_thumbnail_queued_task = None
                self._hmb_import_thumbnail_pending_result = None
                self._hmb_import_thumbnail_thread = None
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

    def _execution_preparation_identity(self) -> str:
        state = self._current_state()
        imports = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
        return _sha256_canonical({
            "root": _project_root_text(_get_parameter_raw(self, PROJECT_ROOT_PARAMETER)),
            "selection": _project_output_fingerprint(
                state, getattr(self, "_hmb_import_media_by_uid", {}),
                _non_negative_int(getattr(self, "_hmb_import_revision", 0)),
            ),
            "imports": _canonical_import_input_identity(imports),
            "import_revision": _non_negative_int(getattr(self, "_hmb_import_revision", 0)),
            "routing": _shot_routing_catalog_identity(state, normalized=True),
            "shot_membership": [list(shot["selected_source_uids"])
                                for shot in state["shot_routing"]["shots"]],
        })

    @staticmethod
    def _prepare_execution_files(
        current: Dict[str, Any], root_value: str, import_value: Any,
        import_media: Dict[str, Any], import_revision: int,
    ) -> tuple[Dict[str, Any], Dict[str, Any], int, OrderedDict]:
        """Detached filesystem preparation: no node, ports, or graph mutation."""
        requested = root_value.replace("\\", "/").rstrip("/").casefold()
        current_root = _project_root_text(current.get("catalog_root")).rstrip("/").casefold()
        root_matches = bool(requested and requested == current_root)
        belongs = _state_project_belongs_to_catalog(current, root_value)
        if root_matches and belongs and _state_catalog_is_current(current):
            state = current
        elif root_matches and belongs:
            state = _read_catalog_index(current.get("project_root"), current)
            if state is None:
                state = _load_project_catalog(root_value, current)
        else:
            state = _load_project_catalog(root_value, current)
        media = import_media
        revision = import_revision
        if _flatten_import_values(import_value):
            state, media = _merge_import_input(state, import_value, defer_thumbnail=True)
            if _import_media_map_identity(media) != _import_media_map_identity(import_media):
                revision += 1
        state = _normalize_state(state)
        cache: OrderedDict = OrderedDict()
        _resolve_selected_assets(
            state, media, resolution_cache=cache, import_revision=revision,
            force=True, normalized=True,
        )
        return state, media, revision, cache

    async def aprocess(self) -> None:
        """Verify shared files off-loop, then publish one current pair on-loop."""
        self._hmb_hydration_adopted = True
        self._consume_pending_catalog_scan_result()
        self._consume_pending_thumbnail_result()
        self._consume_pending_import_thumbnail_result()
        self._consume_pending_catalog_probe_result()
        self._ensure_parameters()
        generation = _non_negative_int(getattr(self, "_hmb_execution_prepare_generation", 0)) + 1
        self._hmb_execution_prepare_generation = generation
        work = getattr(self, "_hmb_selection_resolution_work", None)
        if isinstance(work, dict):
            with work["lock"]:
                work["epoch"] += 1
                work["queued"] = None
                work["ready"] = None
        if bool(getattr(self, "is_cancellation_requested", False)):
            raise asyncio.CancelledError()
        base = self._current_state()
        if base.get("scan_busy"):
            raise _ImageAssetSelectionPreparing("ImageAsset project catalog is still preparing.")
        identity = self._execution_preparation_identity()
        root_value = _project_root_text(_get_parameter_raw(self, PROJECT_ROOT_PARAMETER)) or str(DEFAULT_PROJECTS_ROOT)
        import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
        media = dict(getattr(self, "_hmb_import_media_by_uid", {}) or {})
        revision = _non_negative_int(getattr(self, "_hmb_import_revision", 0))
        prepared, prepared_media, prepared_revision, cache = await asyncio.to_thread(
            self._prepare_execution_files, base, root_value, import_value, media, revision,
        )
        if bool(getattr(self, "is_cancellation_requested", False)):
            raise asyncio.CancelledError()
        if (generation != getattr(self, "_hmb_execution_prepare_generation", 0)
            or not self._scan_owner_is_current()
            or self._current_state().get("scan_busy")
            or identity != self._execution_preparation_identity()):
            raise ValueError("ImageAsset inputs changed while preparing execution; run again with the current selection.")
        live = self._current_state()
        worker_state = prepared
        prepared = _merge_async_scan_result_with_live_state(prepared, base, live)
        if _flatten_import_values(import_value):
            # Unlike a background catalog scan, execution already proved that
            # IMAGE_IMPORT_IN is unchanged. Preserve its freshly prepared rows
            # even when a legacy/programmatic write skipped the input callback.
            prepared["assets"] = [row for row in prepared["assets"] if not (
                _clean(row.get("source_kind")) == "user"
                and _non_negative_int(row.get("import_index")) > 0
            )] + [dict(row) for row in worker_state["assets"] if (
                _clean(row.get("source_kind")) == "user"
                and _non_negative_int(row.get("import_index")) > 0
            )]
            prepared["shot_routing"] = copy.deepcopy(worker_state["shot_routing"])
            prepared["shot_routing"]["expanded"] = live["shot_routing"]["expanded"]
            prepared = _normalize_state(prepared)
        # The merge may retain newer presentation facts, but every selected
        # project row must still have the exact worker-verified cache key.
        if any(
            row.get("selected") and _clean(row.get("source_kind")).casefold() == "project"
            and _asset_resolution_cache_key(row, prepared, prepared_revision) not in cache
            for row in prepared.get("assets", [])
        ):
            raise ValueError("ImageAsset selection changed during verification; run again.")
        if _flatten_import_values(import_value):
            self._replace_import_media(prepared_media)
            if self._hmb_import_revision != prepared_revision:
                raise ValueError("ImageAsset imports changed during verification; run again.")
            self._hmb_last_applied_import_identity = _canonical_import_input_identity(import_value)
        self._hmb_resolution_cache = cache
        self._hmb_resolution_cache_identity = _resolution_cache_state_identity(prepared)
        self._hmb_last_output_fingerprint = ""
        self._hmb_shot_routing_input_identity = ""
        published = self._publish_state(prepared, normalized=True)
        # Thumbnail hydration is presentation work and may still be busy.
        # _publish_state intentionally preserves old outputs for a busy UI
        # acknowledgement; execution must stage the verified pair regardless.
        synchronized = self._sync_output(published, normalized=True)
        self._reconcile_hmb_shot_routing(_shot_routing_catalog_identity(synchronized, normalized=True))
        if _flatten_import_values(import_value):
            self._schedule_live_import_thumbnail_hydration(published)

    def process(self) -> None:
        self._hmb_hydration_adopted = True
        self._consume_pending_catalog_scan_result()
        self._consume_pending_thumbnail_result()
        import_thumbnail_consumer = getattr(
            self, "_consume_pending_import_thumbnail_result", None,
        )
        if callable(import_thumbnail_consumer):
            import_thumbnail_consumer()
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
        loaded_catalog = False
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
                loaded_catalog = True
        else:
            # PROJECT_ROOT is the process-time authority.  A programmatic host
            # update may arrive without the retained widget callback, so an
            # otherwise-current snapshot/index from the previous root must not
            # be adopted here.
            state = self._load_catalog(root_value)
            loaded_catalog = True
        if loaded_catalog and _clean(current.get("project_root")) and _clean(state.get("error")):
            raise ValueError("ImageAsset project catalog could not be read; the previous selection and outputs were retained. " + _clean(state.get("error")))
        import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
        if _flatten_import_values(import_value):
            self._apply_import_value(import_value)
        synchronized = self._sync_output(self._current_state(), force=True)
        self._reconcile_hmb_shot_routing(
            _shot_routing_catalog_identity(synchronized)
        )
        return None
