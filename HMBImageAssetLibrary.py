from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
import base64
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
from typing import Any, Dict, List, Sequence
import unicodedata
from urllib.parse import unquote, urlparse
import uuid


_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _load_hmb_common():
    module_path = _THIS_DIR / "_hmb_common.py"
    module_key = f"{module_path.resolve()}:{module_path.stat().st_mtime_ns}"
    module_name = (
        "_hmb_gp_production_common_"
        + hashlib.sha1(module_key.encode("utf-8")).hexdigest()[:12]
    )
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
IMAGE_SOURCE_TYPE_UNCLASSIFIED = getattr(
    _hmb,
    "IMAGE_SOURCE_TYPE_UNCLASSIFIED",
    "Select Source Type",
)
IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED = getattr(
    _hmb,
    "IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED",
    "Role Required / Select Source Type",
)
IMAGE_SCOPE_CHOICES = _hmb.IMAGE_SCOPE_CHOICES
IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE = _hmb.IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE
ACTOR_COLOR_PICK_CHOICES = _hmb.ACTOR_COLOR_PICK_CHOICES
OBJECT_COLOR_PICK_CHOICES = _hmb.OBJECT_COLOR_PICK_CHOICES
COLOR_PICK_CHOICES = _hmb.COLOR_PICK_CHOICES
image_scope_choices_for_source_type = _hmb.image_scope_choices_for_source_type
image_color_pick_choices_for_source_type = (
    _hmb.image_color_pick_choices_for_source_type
)

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
PROJECT_ROOT_PARAMETER = "PROJECT_ROOT"
IMAGE_IMPORT_PARAMETER = "IMAGE_IMPORT_IN"
OUTPUT_PARAMETER = "IMAGE_ASSET_OUT"
MEDIA_OUTPUT_PARAMETER = "IMAGE_OUT"
OUTPUT_DISPLAY_NAME = "ASSET_OUT"
MEDIA_OUTPUT_DISPLAY_NAME = "Video Generation Out"
STATE_SCHEMA = "hmb-image-asset-library-state"
OUTPUT_SCHEMA = "hmb-image-asset-library-binding"
STATE_VERSION = 4
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
_ASSET_THUMBNAIL_URLS: Dict[str, str] = {}


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
    return {
        "source_type_choices": list(IMAGE_SOURCE_TYPE_CHOICES),
        "scope_choices": list(IMAGE_SCOPE_CHOICES),
        "scope_choices_by_source_type": {
            key: list(values)
            for key, values in IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE.items()
        },
        "actor_color_pick_choices": list(ACTOR_COLOR_PICK_CHOICES),
        "object_color_pick_choices": list(OBJECT_COLOR_PICK_CHOICES),
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


def _match_taxonomy_prefix(
    parts: Sequence[str],
    choices: Sequence[str],
) -> tuple[str, int]:
    best_value = ""
    best_count = 0
    keyed = {
        _taxonomy_key(choice): choice
        for choice in choices
        if _taxonomy_key(choice)
    }
    for count in range(1, min(4, len(parts)) + 1):
        candidates = (
            " / ".join(parts[:count]),
            " ".join(parts[:count]),
            "_".join(parts[:count]),
            "-".join(parts[:count]),
        )
        for candidate in candidates:
            match = keyed.get(_taxonomy_key(candidate))
            if match and count >= best_count:
                best_value = match
                best_count = count
    return best_value, best_count


def _infer_asset_taxonomy(relative_path: Path) -> Dict[str, str]:
    directories = list(relative_path.parts[:-1])
    source_type, consumed = _match_taxonomy_prefix(
        directories,
        [
            value
            for value in _selectable_source_types()
            if value != "Custom"
        ],
    )
    custom_source_type = ""
    if not source_type:
        source_type = "Custom"
        custom_source_type = directories[0] if directories else ""
        consumed = 1 if directories else 0

    scope_choices = [
        value
        for value in image_scope_choices_for_source_type(source_type)
        if value and value != "Custom scope"
    ]
    scope, _scope_consumed = _match_taxonomy_prefix(
        directories[consumed:],
        scope_choices,
    )
    if not scope and directories[consumed:]:
        scope = "Custom scope"
    return {
        "source_type": source_type,
        "custom_source_type": custom_source_type,
        "scope_candidate": scope,
    }


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


def _asset_thumbnail_url(path: Path, asset_library_id: str) -> str:
    """Publish a small browser-safe thumbnail instead of exposing a UNC path."""
    try:
        resolved = path.resolve()
        details = resolved.stat()
        signature_text = "|".join(
            (
                str(resolved).replace("\\", "/").casefold(),
                str(details.st_size),
                str(details.st_mtime_ns),
            )
        )
        signature = hashlib.sha256(signature_text.encode("utf-8")).hexdigest()[:24]
    except Exception:
        return ""

    with _ASSET_THUMBNAIL_LOCK:
        cached = _ASSET_THUMBNAIL_URLS.get(signature)
    if cached:
        return cached

    try:
        from PIL import Image
        from griptape_nodes.retained_mode.griptape_nodes import (  # type: ignore
            GriptapeNodes,
        )

        with Image.open(resolved) as image:
            image.seek(0)
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
        safe_asset_id = re.sub(r"[^0-9A-Za-z_-]+", "_", asset_library_id)[:32]
        filename = f"hmb_asset_thumb_{safe_asset_id}_{signature}.{extension}"
        url = _clean(
            GriptapeNodes.StaticFilesManager().save_static_file(
                output.getvalue(),
                filename,
            )
        )
    except Exception:
        url = ""

    if url:
        with _ASSET_THUMBNAIL_LOCK:
            if len(_ASSET_THUMBNAIL_URLS) >= MAX_ASSETS * 2:
                try:
                    _ASSET_THUMBNAIL_URLS.pop(next(iter(_ASSET_THUMBNAIL_URLS)))
                except (KeyError, StopIteration):
                    pass
            _ASSET_THUMBNAIL_URLS[signature] = url
    return url


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


def _import_payload_size(value: Any) -> int:
    """Return a conservative byte estimate without decoding embedded media."""
    artifact_value = _artifact_field(value, "value")
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    if isinstance(artifact_value, (bytes, bytearray)):
        return len(artifact_value)
    embedded = _artifact_field(value, "base64")
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


def _import_record(value: Any, index: int) -> tuple[Dict[str, Any], Any] | None:
    media_value = value
    reference = ""
    media_ref_kind = "artifact"
    embedded = _artifact_field(value, "base64")
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
    if callable(embedded):
        try:
            embedded = embedded()
        except Exception:
            embedded = None
    if isinstance(value, Path):
        reference = str(value)
    elif isinstance(value, str):
        reference = value.strip()
    elif isinstance(artifact_value, str):
        reference = artifact_value.strip()
    elif isinstance(embedded, str) and embedded.strip():
        reference = embedded.strip()
        media_ref_kind = "embedded"
    elif artifact_bytes:
        reference = "bytes:" + hashlib.sha256(artifact_bytes).hexdigest()
        media_ref_kind = "bytes"
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
        # Creative classification is optional.  External media starts as an
        # unclassified Custom source instead of carrying the legacy
        # "Role Required" sentinel into output payloads.
        "source_type": "Custom",
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
        item_bytes = _import_payload_size(raw)
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
        imported = _import_record(raw, index)
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
    authoritative_fields = (
        ("asset_id", _clean(manifest_record.get("asset_id"))),
        (
            "image_name",
            _clean(manifest_record.get("image_name") or manifest_record.get("name")),
        ),
        ("source_type", _clean(manifest_record.get("source_type"))),
        ("custom_source_type", _clean(manifest_record.get("custom_source_type"))),
        (
            "scope_candidate",
            _clean(
                manifest_record.get("scope")
                or manifest_record.get("scope_candidate")
            ),
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
    """Atomically upsert one validated project-relative asset record."""
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
        existing = records[matching_indices[0]]
        updated = dict(existing) if isinstance(existing, dict) else {}
        updated.update(record)
        updated_records[matching_indices[0]] = updated
    else:
        updated_records.append(dict(record))

    if isinstance(payload, dict):
        output_payload: Any = dict(payload)
        output_payload["assets"] = updated_records
    else:
        output_payload = updated_records
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
            "manifest_signature": "",
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

    stem_counts: Dict[str, int] = {}
    for path in paths:
        stem_key = path.stem.casefold()
        stem_counts[stem_key] = stem_counts.get(stem_key, 0) + 1

    assets: List[Dict[str, Any]] = []
    for path in paths:
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        inferred = _infer_asset_taxonomy(relative)
        override = manifest_overrides.get(relative_text.casefold())
        registered = override is not None
        override_values = override or {}
        source_type = (
            _clean(override_values.get("source_type")) or inferred["source_type"]
        )
        if source_type in {
            IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
            IMAGE_SOURCE_TYPE_UNCLASSIFIED,
        }:
            source_type = "Custom"
        if source_type not in IMAGE_SOURCE_TYPE_CHOICES:
            warnings.append(
                f"{relative_text}: unknown Main Type {source_type!r}; classified as Custom."
            )
            source_type = "Custom"
        custom_source_type = (
            _clean(override_values.get("custom_source_type"))
            if "custom_source_type" in override_values
            else inferred["custom_source_type"]
        )
        scope_candidate = (
            _clean(
                override_values.get("scope")
                if "scope" in override_values
                else override_values.get("scope_candidate")
            )
            if "scope" in override_values or "scope_candidate" in override_values
            else inferred["scope_candidate"]
        )
        if (
            scope_candidate
            and scope_candidate
            not in image_scope_choices_for_source_type(source_type)
        ):
            warnings.append(
                f"{relative_text}: Sub Type candidate {scope_candidate!r} is not "
                f"valid for {source_type!r}; candidate cleared."
            )
            scope_candidate = ""

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
        thumbnail_url = _asset_thumbnail_url(path, library_id)
        color_candidates = image_color_pick_choices_for_source_type(source_type)
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
                "thumbnail_url": thumbnail_url,
                "relative_path": relative_text,
                "extension": path.suffix.casefold(),
                "width": width,
                "height": height,
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
        "manifest_signature": manifest_signature,
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
    source_type = _clean(raw.get("source_type"))
    if source_type in {
        IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
        IMAGE_SOURCE_TYPE_UNCLASSIFIED,
    }:
        source_type = "Custom"
    if source_type not in IMAGE_SOURCE_TYPE_CHOICES:
        source_type = "Custom"
    scope_candidate = _clean(
        raw.get("scope_candidate") or raw.get("scope") or raw.get("sub_type")
    )
    if (
        scope_candidate
        and scope_candidate not in image_scope_choices_for_source_type(source_type)
    ):
        scope_candidate = ""
    allowed_colors = image_color_pick_choices_for_source_type(source_type)
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
        "relative_path": _clean(raw.get("relative_path")).replace("\\", "/"),
        "extension": _clean(raw.get("extension")).casefold(),
        "width": width,
        "height": height,
        "source_type": source_type,
        "custom_source_type": _clean(raw.get("custom_source_type")),
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
        "source_type": _clean(value.get("source_type"))[:256],
        "custom_source_type": _clean(value.get("custom_source_type"))[:256],
        "scope_candidate": _clean(
            value.get("scope_candidate") or value.get("scope")
        )[:256],
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


def _normalize_disconnect_import_uid(value: Any) -> str:
    source_uid = _clean(value)[:512]
    return source_uid if source_uid.startswith("import:") else ""


def _default_state() -> Dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "version": STATE_VERSION,
        "catalog_root": str(DEFAULT_PROJECTS_ROOT).replace("\\", "/"),
        "projects": [],
        "project_root": "",
        "project_id": "",
        "project_uid": "",
        "manifest_signature": "",
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
        "language": "en",
        "asset_view_mode": "image",
        UI_EDIT_REVISION_KEY: 0,
        "scan_revision": 0,
        "refresh_revision": 0,
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
    if selected_main_type in {
        IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
        IMAGE_SOURCE_TYPE_UNCLASSIFIED,
    }:
        selected_main_type = ""
    if selected_main_type not in IMAGE_SOURCE_TYPE_CHOICES:
        selected_main_type = ""
    selected_sub_type = _clean(source.get("selected_sub_type"))
    if (
        selected_sub_type
        and selected_sub_type
        not in image_scope_choices_for_source_type(selected_main_type)
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
            "manifest_signature": _clean(source.get("manifest_signature"))[:128],
            "folders": folders,
            "assets": assets,
            "tree": _build_asset_tree(project_root, project_id, folders, assets),
            "root_edit_enabled": bool(source.get("root_edit_enabled", False)),
            "selected_folder_path": selected_folder_path,
            "expanded_folders": expanded_folders,
            "selected_main_type": selected_main_type,
            "selected_sub_type": selected_sub_type,
            "selected_source_view": selected_source_view,
            "search": _clean(source.get("search"))[:256],
            "language": (
                "ko"
                if _clean(source.get("language")).casefold() == "ko"
                else "en"
            ),
            "asset_view_mode": (
                "detail"
                if _clean(source.get("asset_view_mode")).casefold() == "detail"
                else "image"
            ),
            UI_EDIT_REVISION_KEY: ui_edit_revision,
            "scan_revision": scan_revision,
            "refresh_revision": refresh_revision,
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


def _merge_scan_with_state(
    scan: Dict[str, Any],
    previous_state: Dict[str, Any],
) -> Dict[str, Any]:
    previous_assets = {
        _clean(asset.get("asset_library_id")): asset
        for asset in previous_state.get("assets", [])
        if isinstance(asset, dict) and _clean(asset.get("asset_library_id"))
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
            "manifest_signature": scan.get("manifest_signature", ""),
            "folders": scan.get("folders", []),
            "assets": assets,
            "warnings": scan.get("warnings", []),
            "error": "",
            "scan_revision": int(previous_state.get("scan_revision") or 0) + 1,
        }
    )
    return _normalize_state(state)


def _load_project_catalog(
    projects_root: Any,
    previous_state: Dict[str, Any],
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
        state = _merge_scan_with_state(
            _scan_project_assets(selected_path),
            state,
        )
        state["catalog_root"] = catalog["catalog_root"]
        state["projects"] = catalog["projects"]
    else:
        state.update(
            {
                "project_root": "",
                "project_id": "",
                "project_uid": "",
                "manifest_signature": "",
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
    requested_source_type = _clean(request.get("source_type"))
    source_type = requested_source_type
    if source_type in {
        "",
        IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
        IMAGE_SOURCE_TYPE_UNCLASSIFIED,
    }:
        source_type = "Custom"
    custom_source_type = _clean(request.get("custom_source_type"))
    if source_type not in _selectable_source_types():
        # Preserve an unknown future/user role as ordinary Custom metadata.  A
        # role is creative context, not a registration prerequisite.
        custom_source_type = custom_source_type or requested_source_type
        source_type = "Custom"
    if source_type == "Custom":
        if len(custom_source_type) > 256:
            raise ValueError("Custom Main Type exceeds 256 characters.")
        if any(
            ord(character) < 32 or ord(character) == 127
            for character in custom_source_type
        ):
            raise ValueError("Custom Main Type contains unsupported control characters.")
    else:
        custom_source_type = ""
    scope_candidate = _clean(request.get("scope_candidate"))
    if len(scope_candidate) > 256:
        raise ValueError("Sub Type exceeds 256 characters.")
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in scope_candidate
    ):
        raise ValueError("Sub Type contains unsupported control characters.")
    if (
        scope_candidate
        and scope_candidate not in image_scope_choices_for_source_type(source_type)
    ):
        raise ValueError(
            f"Sub Type {scope_candidate!r} is not valid for Main Type "
            f"{source_type!r}."
        )
    relative_text = _clean(scanned_asset.get("relative_path")).replace("\\", "/")
    return {
        "path": relative_text,
        "asset_id": asset_id,
        "image_name": image_name,
        "source_type": source_type,
        "custom_source_type": custom_source_type,
        "scope": scope_candidate,
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


def _apply_asset_registration(
    state: Dict[str, Any],
    request_value: Any,
    import_media_by_uid: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Validate one UI Add request, persist it, then return a fresh scan."""
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
    refresh_base = normalized
    source_selection = False
    source_selection_order = 0
    copied_destination: Path | None = None

    if request_source_kind == "project":
        scan = _scan_project_assets(selected_project["path"])
        matches = [
            asset
            for asset in scan["assets"]
            if _clean(asset.get("asset_library_id"))
            == request.get("asset_library_id")
        ]
        if len(matches) != 1:
            raise ValueError("The image file changed or no longer belongs to this project.")
        scanned_asset = matches[0]
        relative_text = _clean(scanned_asset.get("relative_path")).replace("\\", "/")
        if relative_text.casefold() != request.get("relative_path", "").casefold():
            raise ValueError("The image path changed while the registration window was open.")
        if (
            scanned_asset.get("source_kind") != "project"
            or _is_user_import_relative_path(relative_text)
        ):
            raise ValueError("External or User Import images cannot be registered in place.")
        _verified_image_dimensions(selected_root / Path(relative_text))
        record = _registration_record(request, scanned_asset)
        manifest_path = _write_asset_manifest_record(selected_root, record)
        registration_message = f"Registered in {manifest_path.name}."
    else:
        source_matches = [
            asset
            for asset in normalized["assets"]
            if _clean(asset.get("asset_library_id")) == request["asset_library_id"]
            and _clean(asset.get("source_uid")) == request["source_uid"]
            and _clean(asset.get("source_kind")) == "user"
            and _non_negative_int(asset.get("import_index")) > 0
        ]
        if len(source_matches) != 1:
            raise ValueError("The external IMAGE_IMPORT_IN source changed or is unavailable.")
        source_asset = source_matches[0]
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
        try:
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
        registered_library_id = _asset_library_id(
            _clean(selected_project.get("project_id")),
            relative_text,
        )
        source_selection = bool(source_asset.get("selected"))
        source_selection_order = _non_negative_int(source_asset.get("selection_order"))
        refresh_base = dict(normalized)
        refresh_base["assets"] = [
            dict(asset)
            for asset in normalized["assets"]
            if not (
                _clean(asset.get("source_kind")) == "user"
                and _clean(asset.get("source_uid")) == request["source_uid"]
            )
        ]
        registration_message = (
            f"Copied to {relative_text} and registered in {manifest_path.name}."
        )

    refreshed_scan = _scan_project_assets(selected_project["path"])
    refreshed = _merge_scan_with_state(refreshed_scan, refresh_base)
    refreshed["catalog_root"] = catalog["catalog_root"]
    refreshed["projects"] = catalog["projects"]
    if request_source_kind == "user":
        for asset in refreshed["assets"]:
            if _clean(asset.get("asset_library_id")) != registered_library_id:
                continue
            asset["selected"] = source_selection
            asset["selection_order"] = source_selection_order if source_selection else 0
            break
    refreshed["asset_registration_request"] = {}
    refreshed["asset_registration_result"] = {
        "request_id": request["request_id"],
        "ok": True,
        "asset_library_id": registered_library_id,
        "message": registration_message,
    }
    refreshed["error"] = ""
    return _normalize_state(refreshed)


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
) -> Dict[str, Any]:
    """Resolve one authoritative selection for metadata and generator media.

    Selection order in widget state is the requested order.  Only rows with
    concrete media enter the published order; omitted rows retain their
    requested order and source identity in diagnostics so a missing image can
    never shift ``@imageN`` onto a different fan-out item silently.
    """
    normalized = _normalize_state(state)
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
) -> tuple[Dict[str, Any], List[str]]:
    """Build both public outputs from one immutable resolution snapshot."""
    selection = _resolve_selected_assets(
        state,
        media_by_uid,
        resolution_cache=resolution_cache,
        import_revision=import_revision,
        force=force,
    )
    return (
        _build_output_payload(
            selection["state"],
            media_by_uid,
            resolved_selection=selection,
        ),
        [item["media"] for item in selection["resolved"]],
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
                "display_name": display_name,
                "compact": True,
                "height": 24,
                "is_full_width": False,
                "hide_property": True,
            }
        )
        current_ui.pop("hide", None)
        current_ui.pop("hide_handles", None)
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
            "registered Sub Type remains bound in HMBPromptLibrary while Target and "
            "Color Pick remain editable without making Prompt a prerequisite."
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
            "display_name": OUTPUT_DISPLAY_NAME,
            "compact": True,
            "height": 24,
            "is_full_width": False,
            "hide_property": True,
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
            "display_name": MEDIA_OUTPUT_DISPLAY_NAME,
            "compact": True,
            "height": 24,
            "is_full_width": False,
            "hide_property": True,
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
        "Name, Main Type, registered Sub Type, and default selection."
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


def _stage_and_notify_image_output_pair(
    node: Any,
    asset_output: Any,
    media_output: Any,
    *,
    stage_outputs: bool = True,
    replace_pending: bool = True,
) -> None:
    """Stage both sibling caches, then independently notify live connections."""
    synchronized_outputs = (
        (OUTPUT_PARAMETER, asset_output),
        (MEDIA_OUTPUT_PARAMETER, media_output),
    )
    # A synchronous subscriber to the first notification can read the sibling
    # port immediately, so both retained-mode caches must already be current.
    if stage_outputs:
        for name, value in synchronized_outputs:
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
        self._hmb_root_syncing = False
        self._hmb_refresh_revision = 0
        self._hmb_manifest_poll_received = False
        self._hmb_manifest_poll_pending = False
        self._hmb_last_manifest_poll_nonce = ""
        self._hmb_last_manifest_poll_error = ""
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
        self._hmb_resolution_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hmb_resolution_cache_identity = ""
        self._hmb_last_resolution_warning = ""
        self._hmb_last_output_fingerprint = ""
        self._hmb_last_output_pair: tuple[Any, Any] | None = None
        self._hmb_output_notification_generation = 0
        self._hmb_pending_output_notifications: Dict[str, tuple[int, Any]] = {}
        self._ensure_parameters()
        self._accept_widget_state_baseline(
            _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        )
        root_value = _project_root_text(
            _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
        )
        self._load_catalog(root_value or str(DEFAULT_PROJECTS_ROOT))

    def _ensure_parameters(self) -> None:
        _add_output(self)
        _add_media_output(self)
        _add_image_import_input(self)
        _add_project_root(self)
        _add_widget_state(self)

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
        if initial_setup and param_name == WIDGET_STATE_PARAMETER:
            self._accept_widget_state_baseline(value)
        if (
            ParameterMode is None
            and param_name == WIDGET_STATE_PARAMETER
            and not initial_setup
        ):
            parameter = _get_parameter_obj(self, WIDGET_STATE_PARAMETER)
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
            return
        parent_setter(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

    def _current_state(self) -> Dict[str, Any]:
        return _normalize_state(
            _get_parameter_raw(self, WIDGET_STATE_PARAMETER)
        )

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
        normalized = _normalize_state(raw)
        self._hmb_last_accepted_widget_state = _json_text(normalized)
        self._hmb_last_accepted_widget_revisions = (
            _non_negative_int(normalized.get("scan_revision")),
            _non_negative_int(normalized.get(UI_EDIT_REVISION_KEY)),
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
        return incoming_ui < accepted_ui

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
    ) -> Dict[str, Any]:
        normalized = _normalize_state(state)
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
            if (
                current_asset_output != cached_asset_output
                or current_media_output != cached_media_output
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
                )
            elif getattr(self, "_hmb_pending_output_notifications", None):
                _stage_and_notify_image_output_pair(
                    self,
                    cached_asset_output,
                    cached_media_output,
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
        _stage_and_notify_image_output_pair(
            self,
            asset_output_value,
            media_output_value,
        )
        return normalized

    def _publish_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state = dict(state)
        state["asset_registration_request"] = {}
        state["disconnect_import_uid"] = ""
        normalized = _normalize_state(state)
        self._accept_widget_state_baseline(normalized)
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
        self._hmb_state_syncing = True
        try:
            _set_parameter_value(
                self,
                WIDGET_STATE_PARAMETER,
                _json_text(normalized),
            )
        finally:
            self._hmb_state_syncing = False
        self._hmb_refresh_revision = _non_negative_int(
            normalized.get("refresh_revision")
        )
        normalized = self._sync_output(normalized)
        return normalized

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

    def _apply_import_value(self, value: Any) -> Dict[str, Any]:
        state = self._current_state()
        if not _flatten_import_values(value):
            self._replace_import_media({})
            return self._publish_state(_remove_live_imports(state))
        try:
            state, media_by_uid = _merge_import_input(state, value)
            self._replace_import_media(media_by_uid)
            return self._publish_state(state)
        except Exception as exc:
            state = dict(state)
            state["error"] = f"IMAGE_IMPORT_IN: {exc}"
            _diagnostic_exception("Image import failed", exc)
            return self._publish_state(state)

    def _apply_manifest_poll(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Refresh only when another client changed the shared manifest."""
        normalized = _normalize_state(state)
        if not normalized.get("project_root"):
            return normalized
        try:
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
                return normalized

            refreshed_scan = _scan_project_assets(selected["path"])
            refreshed = _merge_scan_with_state(refreshed_scan, normalized)
            refreshed["catalog_root"] = catalog["catalog_root"]
            refreshed["projects"] = catalog["projects"]
            import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
            if _flatten_import_values(import_value):
                refreshed, media_by_uid = _merge_import_input(
                    refreshed,
                    import_value,
                )
                self._replace_import_media(media_by_uid)
            self._hmb_last_manifest_poll_error = ""
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
            try:
                state = _apply_asset_registration(
                    state,
                    registration_request,
                    self._hmb_import_media_by_uid,
                )
                import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
                if _flatten_import_values(import_value):
                    state, media_by_uid = _merge_import_input(
                        state,
                        import_value,
                    )
                    self._replace_import_media(media_by_uid)
                return self._publish_state(state)
            except Exception as exc:
                state["asset_registration_result"] = {
                    "request_id": _clean(registration_request.get("request_id")),
                    "ok": False,
                    "asset_library_id": _clean(
                        registration_request.get("asset_library_id")
                    ),
                    "message": str(exc),
                }
                state["error"] = f"Asset registration: {exc}"
                _diagnostic_exception("Asset registration failed", exc)
                return self._publish_state(state)
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
        if requested_catalog.casefold() != current_catalog.casefold():
            try:
                state = _load_project_catalog(
                    requested_catalog,
                    state,
                )
                self._hmb_root_syncing = True
                try:
                    _set_parameter_value(
                        self,
                        PROJECT_ROOT_PARAMETER,
                        requested_catalog,
                    )
                finally:
                    self._hmb_root_syncing = False
                import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
                if _flatten_import_values(import_value):
                    state, media_by_uid = _merge_import_input(
                        state,
                        import_value,
                    )
                    self._replace_import_media(media_by_uid)
                return self._publish_state(state)
            except Exception as exc:
                state["catalog_root"] = current_catalog.replace("\\", "/")
                state["error"] = str(exc)
                _diagnostic_exception("Project Root update failed", exc)
                return self._publish_state(state)
        if refresh_requested:
            try:
                state = _load_project_catalog(
                    requested_catalog,
                    state,
                )
                import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
                if _flatten_import_values(import_value):
                    state, media_by_uid = _merge_import_input(
                        state,
                        import_value,
                    )
                    self._replace_import_media(media_by_uid)
                return self._publish_state(state)
            except Exception as exc:
                state["error"] = str(exc)
                _diagnostic_exception("Project refresh failed", exc)
                return self._publish_state(state)
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
            try:
                state = _select_catalog_project(
                    state,
                    requested_path,
                )
                import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
                if _flatten_import_values(import_value):
                    state, media_by_uid = _merge_import_input(
                        state,
                        import_value,
                    )
                    self._replace_import_media(media_by_uid)
                return self._publish_state(state)
            except Exception as exc:
                state["error"] = str(exc)
                _diagnostic_exception("Project selection failed", exc)
                return self._publish_state(state)
        if manifest_poll_received:
            return (
                self._apply_manifest_poll(state)
                if manifest_poll_requested
                else state
            )
        return self._sync_output(state)

    def before_value_set(self, parameter: Any, value: Any) -> Any:
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

            try:
                project_root = _clean(candidate.get("project_root"))
                if project_root:
                    signature = _asset_manifest_signature(Path(project_root))
                    if signature != _clean(candidate.get("manifest_signature")):
                        # Guarantee a real parameter-value change so hosts
                        # that suppress identical values still invoke the
                        # post-set refresh hook.
                        candidate["scan_revision"] = (
                            _non_negative_int(candidate.get("scan_revision")) + 1
                        )
                        self._hmb_manifest_poll_received = True
                        self._hmb_manifest_poll_pending = True
                self._hmb_last_manifest_poll_error = ""
            except Exception as exc:
                message = _clean(exc)
                if message != self._hmb_last_manifest_poll_error:
                    _diagnostic_exception("Shared manifest probe failed", exc)
                    self._hmb_last_manifest_poll_error = message
            return _json_text(_normalize_state(candidate))
        if name == PROJECT_ROOT_PARAMETER:
            return _project_root_text(value)
        return value

    def after_value_set(self, parameter: Any, value: Any) -> Any:
        result = None
        try:
            parent = getattr(super(), "after_value_set", None)
            if callable(parent):
                result = parent(parameter, value)
        except Exception as exc:
            _diagnostic_exception("Parent after_value_set failed", exc)
        if self._hmb_state_syncing:
            return result
        name = _clean(getattr(parameter, "name", ""))
        if name == PROJECT_ROOT_PARAMETER and not self._hmb_root_syncing:
            self._load_catalog(value)
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
        self._ensure_parameters()
        saved_state = self._current_state()
        root_value = _project_root_text(
            _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
        )
        saved_root = _project_root_text(saved_state.get("catalog_root"))
        root_candidates = [
            saved_root,
            root_value,
            str(DEFAULT_PROJECTS_ROOT),
        ]
        root_value = ""
        for candidate in root_candidates:
            candidate = _project_root_text(candidate)
            if not candidate:
                continue
            try:
                _discover_project_catalog(candidate)
                root_value = candidate
                break
            except Exception:
                continue
        root_value = root_value or str(DEFAULT_PROJECTS_ROOT)
        if root_value:
            self._hmb_root_syncing = True
            try:
                _set_parameter_value(self, PROJECT_ROOT_PARAMETER, root_value)
            finally:
                self._hmb_root_syncing = False
        self._load_catalog(root_value or str(DEFAULT_PROJECTS_ROOT))
        import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
        if _flatten_import_values(import_value):
            self._apply_import_value(import_value)
        return result

    def process(self) -> None:
        self._ensure_parameters()
        root_value = _project_root_text(
            _get_parameter_raw(self, PROJECT_ROOT_PARAMETER)
        )
        state = self._load_catalog(root_value or str(DEFAULT_PROJECTS_ROOT))
        import_value = _get_parameter_raw(self, IMAGE_IMPORT_PARAMETER)
        if _flatten_import_values(import_value):
            self._apply_import_value(import_value)
        self._sync_output(self._current_state(), force=True)
        return None
