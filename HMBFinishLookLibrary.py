from __future__ import annotations

import copy
import hashlib
import hmac
import importlib.util
import json
import logging
import math
import re
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4


_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from _hmb_deletion_guard import hmb_binding_mutation


def _load_hmb_common() -> Any:
    module_path = _THIS_DIR / "_hmb_common.py"
    module_name = "_hmb_gp_production_common"
    existing = sys.modules.get(module_name)
    if existing is not None and Path(getattr(existing, "__file__", "")).resolve() == module_path.resolve():
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
add_group = _hmb.add_group
set_output = _hmb.set_output
parameter_exists = _hmb.parameter_exists

try:
    from griptape_nodes.traits.widget import Widget  # type: ignore
except Exception:
    Widget = None  # type: ignore


LOGGER = logging.getLogger("griptape_nodes")
EPSILON = 1e-6
SCHEMA_VERSION = 2
WIDGET_NAME = "HMBFinishLookLibraryWidget"
WIDGET_LIBRARY_NAME = "HMB_GP_Production"
WIDGET_PARAMETER_NAME = "HMB_FINISH_LOOK_UI_STATE"
REMOTE_INPUT_PARAMETER_NAME = "FINISH_LOOK_REMOTE_IN"
SHOT_STORE_PARAMETER_NAME = "HMB_FINISH_LOOK_SHOT_STATES"
SHOT_STORE_SCHEMA = "hmb-finish-look-shot-store"
UI_TRANSPORT_KEY = "ui_transport"
UI_TRANSPORT_SCHEMA = "hmb-finish-ui-transport"
MAX_UI_CLIENTS = 64

FINISH_LOOK_OUTPUT_PARAMETER_NAME = "FINISH_LOOK_OUT"
SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME = "SHOT_FINISH_LOOK_OUT"
FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME = "HMB_FINISH_LOOK_STATE"
REMOTE_STATUS_OUTPUT_PARAMETER_NAME = "HMB_FINISH_LOOK_REMOTE_STATUS"

REMOTE_SCHEMA = "hmb-finish-look-remote-patch"
MAX_REQUEST_ID_LENGTH = 128
MAX_REMOTE_HISTORY = 256
SHOT_ROUTING_CATALOG_SCHEMA = "hmb-shot-routing-catalog"
SHOT_ROUTING_CATALOG_VERSION = 1
SHOT_SUBSCRIPTION_SCHEMA = "hmb-shot-channel-subscription"
SHOT_SUBSCRIPTION_VERSION = 1
FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA = "hmb-finish-look-shot-snapshot"
FINISH_LOOK_SHOT_SNAPSHOT_VERSION = 2
MAX_SHOTS = 5
FINISH_LOOK_NODE_WIDTH = 980
FINISH_LOOK_SHOT_TAB_HEIGHT = 51
# Beauty controls, five fixed Shot tabs and the status footer fit without the
# old empty tail. Native Flow rows/frame add 76 px around the visible widget.
FINISH_LOOK_WIDGET_HEIGHT = 737 + FINISH_LOOK_SHOT_TAB_HEIGHT
FINISH_LOOK_NODE_HEIGHT = FINISH_LOOK_WIDGET_HEIGHT + 76
FINISH_LOOK_NODE_MIN_WIDTH = 700
FINISH_LOOK_NODE_MIN_HEIGHT = 620
FINISH_LOOK_WIDGET_MIN_HEIGHT = 180


class FinishLookValidationError(ValueError):
    """A state or remote request violates the public Finish Look contract."""


DEFAULT_FINISH_LOOK_STATE: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "beauty": {
        "enabled": False,
        "soften_shadows": 0.11,
        "shadow_threshold": 0.27,
        "saturation": 1.0,
        "brightness": 1.0,
        "glow_brightness": 0.0,
        "glow_threshold": 0.2,
        "glow_width": 16.0,
        "soft_focus": 0.0,
        "blur_amount": 0.0,
        "pore_size": 0.0,
        "reduce_shine": 0.0,
    },
}

DEFAULT_REMOTE_STATUS: dict[str, Any] = {
    "schema_version": 1,
    "status": "idle",
    "code": "idle",
    "message": "",
    "request_id": "",
    "revision": 0,
}

def default_finish_look_state() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_FINISH_LOOK_STATE)


def _shot_only() -> dict[str, Any]:
    return {
        "channel_uuid": "",
        "shot_uuid": "",
        "number": 1,
        "name": "Only",
    }


def _normalize_shot_catalog(
    value: Any,
    *,
    strict: bool = False,
    allow_sparse: bool = False,
) -> dict[str, Any]:
    """Normalize the compact ImageAsset-owned Shot catalog.

    Finish Look never persists media in its selector state.  The catalog is
    only a bounded UUID/name option list supplied by the same-flow router.
    """

    if not value:
        return {}
    if not isinstance(value, Mapping):
        if strict:
            raise FinishLookValidationError("Shot catalog must be an object.")
        return {}
    required = {
        "schema",
        "version",
        "publisher_instance_uuid",
        "channel_uuid",
        "generation",
        "metadata_sha256",
        "shots",
    }
    if set(value) != required:
        if strict:
            raise FinishLookValidationError("Shot catalog shape is invalid.")
        return {}
    publisher = str(value.get("publisher_instance_uuid") or "")
    channel = str(value.get("channel_uuid") or "")
    metadata_sha256 = str(value.get("metadata_sha256") or "").casefold()
    generation = value.get("generation")
    shots_value = value.get("shots")
    if (
        value.get("schema") != SHOT_ROUTING_CATALOG_SCHEMA
        or value.get("version") != SHOT_ROUTING_CATALOG_VERSION
        or not publisher
        or publisher != publisher.strip()
        or len(publisher) > 128
        or not channel
        or channel != channel.strip()
        or len(channel) > 128
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or not 1 <= generation <= (1 << 53) - 1
        or re.fullmatch(r"[0-9a-f]{64}", metadata_sha256) is None
        or not isinstance(shots_value, list)
        or not 1 <= len(shots_value) <= MAX_SHOTS
    ):
        if strict:
            raise FinishLookValidationError("Shot catalog metadata is invalid.")
        return {}
    shots: list[dict[str, Any]] = []
    shot_ids: set[str] = set()
    shot_numbers: set[int] = set()
    for raw in shots_value:
        if not isinstance(raw, Mapping) or set(raw) != {
            "shot_uuid",
            "number",
            "name",
            "revision",
        }:
            if strict:
                raise FinishLookValidationError("Shot catalog row is invalid.")
            return {}
        shot_uuid = str(raw.get("shot_uuid") or "")
        name = " ".join(str(raw.get("name") or "").split())
        number = raw.get("number")
        revision = raw.get("revision")
        if (
            not shot_uuid
            or shot_uuid != shot_uuid.strip()
            or len(shot_uuid) > 128
            or shot_uuid in shot_ids
            or isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= MAX_SHOTS
            or number in shot_numbers
            or not name
            or len(name) > 128
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or not 0 <= revision <= (1 << 53) - 1
        ):
            if strict:
                raise FinishLookValidationError("Shot catalog row value is invalid.")
            return {}
        shot_ids.add(shot_uuid)
        shot_numbers.add(number)
        shots.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
            }
        )
    shots.sort(key=lambda item: (item["number"], item["shot_uuid"]))
    if (
        not allow_sparse
        and [item["number"] for item in shots] != list(range(1, len(shots) + 1))
    ):
        if strict:
            raise FinishLookValidationError("Shot catalog numbering is invalid.")
        return {}
    document = {
        "channel_uuid": channel,
        "generation": generation,
        "shots": shots,
    }
    expected_sha256 = hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(metadata_sha256, expected_sha256):
        if strict:
            raise FinishLookValidationError("Shot catalog hash does not match.")
        return {}
    return {
        "schema": SHOT_ROUTING_CATALOG_SCHEMA,
        "version": SHOT_ROUTING_CATALOG_VERSION,
        "publisher_instance_uuid": publisher,
        "channel_uuid": channel,
        "generation": generation,
        "metadata_sha256": metadata_sha256,
        "shots": shots,
    }


def _normalize_shot_selection(value: Any, catalog: Any = None) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    channel = str(source.get("channel_uuid") or "").strip()[:128]
    shot_uuid = str(source.get("shot_uuid") or "").strip()[:128]
    if not channel or not shot_uuid:
        return _shot_only()
    normalized_catalog = _normalize_shot_catalog(catalog, allow_sparse=True)
    if normalized_catalog and normalized_catalog.get("channel_uuid") != channel:
        return _shot_only()
    selected = next(
        (
            item
            for item in normalized_catalog.get("shots", [])
            if item.get("shot_uuid") == shot_uuid
        ),
        None,
    )
    if normalized_catalog and selected is None:
        return _shot_only()
    try:
        number = max(1, min(MAX_SHOTS, int(source.get("number") or 1)))
    except (TypeError, ValueError, OverflowError):
        number = 1
    if selected is not None:
        number = int(selected["number"])
        name = str(selected["name"])
    else:
        name = " ".join(str(source.get("name") or f"Shot {number}").split())[:128]
    return {
        "channel_uuid": channel,
        "shot_uuid": shot_uuid,
        "number": number,
        "name": name or f"Shot {number}",
    }


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise FinishLookValidationError(f"{field} must contain valid JSON.") from exc
    if not isinstance(value, Mapping):
        raise FinishLookValidationError(f"{field} must be an object.")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise FinishLookValidationError(f"{field} is missing: {', '.join(missing)}.")
    if unknown:
        raise FinishLookValidationError(f"{field} contains unsupported keys: {', '.join(unknown)}.")


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise FinishLookValidationError(f"{field} must be boolean.")
    return value


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FinishLookValidationError(f"{field} must be numeric.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise FinishLookValidationError(f"{field} must be finite.") from exc
    if not math.isfinite(result):
        raise FinishLookValidationError(f"{field} must be finite.")
    if minimum is not None and result < minimum:
        raise FinishLookValidationError(f"{field} must be at least {format_number(minimum)}.")
    if maximum is not None and result > maximum:
        raise FinishLookValidationError(f"{field} must be at most {format_number(maximum)}.")
    return result


def _choice(value: Any, choices: Sequence[str], field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise FinishLookValidationError(f"{field} must be one of: {', '.join(choices)}.")
    return value


def validate_finish_look_state(value: Any) -> dict[str, Any]:
    state = _mapping(value, "Finish Look state")
    version = state.get("schema_version")
    if type(version) is not int or version not in (1, SCHEMA_VERSION):
        raise FinishLookValidationError("schema_version must be integer 1 or 2.")
    # Old workflows migrate Beauty settings, never their retired film instructions.
    expected = {"schema_version", "beauty"}
    if version == 1 and "film" in state:
        expected.add("film")
    _exact_keys(state, expected, "Finish Look state")

    beauty = _mapping(state["beauty"], "beauty")
    beauty_keys = {
        "enabled",
        "soften_shadows",
        "shadow_threshold",
        "saturation",
        "brightness",
        "glow_brightness",
        "glow_threshold",
        "glow_width",
        "soft_focus",
        "blur_amount",
        "pore_size",
        "reduce_shine",
    }
    _exact_keys(beauty, beauty_keys, "beauty")
    normalized_beauty = {
        "enabled": _boolean(beauty["enabled"], "beauty.enabled"),
        "soften_shadows": _number(beauty["soften_shadows"], "beauty.soften_shadows", minimum=-1, maximum=1),
        "shadow_threshold": _number(beauty["shadow_threshold"], "beauty.shadow_threshold", minimum=0, maximum=1),
        "saturation": _number(beauty["saturation"], "beauty.saturation", minimum=-2, maximum=8),
        "brightness": _number(beauty["brightness"], "beauty.brightness", minimum=0),
        "glow_brightness": _number(beauty["glow_brightness"], "beauty.glow_brightness", minimum=0),
        "glow_threshold": _number(beauty["glow_threshold"], "beauty.glow_threshold", minimum=0),
        "glow_width": _number(beauty["glow_width"], "beauty.glow_width", minimum=0),
        "soft_focus": _number(beauty["soft_focus"], "beauty.soft_focus", minimum=0),
        "blur_amount": _number(beauty["blur_amount"], "beauty.blur_amount", minimum=0),
        "pore_size": _number(beauty["pore_size"], "beauty.pore_size", minimum=0),
        "reduce_shine": _number(beauty["reduce_shine"], "beauty.reduce_shine", minimum=0, maximum=1),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "beauty": normalized_beauty,
    }


parse_finish_look_state = validate_finish_look_state


def format_number(value: float) -> str:
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def is_zero(value: float) -> bool:
    return abs(float(value)) <= EPSILON


def join_sentences(parts: Sequence[str]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _common_strength(value: float) -> str:
    magnitude = abs(float(value))
    if magnitude <= EPSILON:
        return ""
    if magnitude <= 0.05:
        return "nearly imperceptible"
    if magnitude <= 0.12:
        return "very subtle"
    if magnitude <= 0.25:
        return "subtle"
    if magnitude <= 0.5:
        return "moderate"
    return "pronounced"


def _beauty_shadow_phrase(value: float) -> str:
    if value <= -0.21:
        return "pronounced shadow enhancement"
    if value <= -0.06:
        return "moderately strengthened shadow definition"
    if value <= 0.05:
        return "no meaningful shadow softening"
    if value <= 0.12:
        return "gently softened shadow transitions"
    if value <= 0.25:
        return "moderately softened shadow transitions"
    return "pronounced shadow softening"


def _beauty_threshold_phrase(value: float) -> str:
    if value <= 0.14:
        return "at a low shadow threshold"
    if value <= 0.39:
        return "at a moderate threshold"
    return "across a broad shadow range"


def _beauty_saturation_clause(value: float) -> str:
    if value <= -1.01:
        return "Use a strongly amplified inverted-chroma response on character surfaces"
    if value <= -0.51:
        return "Use a clear inverted-chroma response on character surfaces"
    if value < -EPSILON:
        return "Use a restrained inverted-chroma response on character surfaces"
    if abs(value) <= EPSILON:
        return "Use a monochrome character-surface color response"
    if value <= 0.89:
        return "Use visibly reduced character-surface saturation"
    if value <= 0.97:
        return "Use slightly reduced character-surface saturation"
    if value <= 1.02:
        return "Keep character-surface saturation neutral at full strength"
    if value <= 1.10:
        return "Use subtly increased character-surface saturation"
    return "Use increased character-surface saturation"


def _beauty_brightness_clause(value: float) -> str:
    if 0.98 <= value <= 1.02:
        return "maintain neutral character-surface brightness"
    direction = "reduce" if value < 0.98 else "increase"
    return f"{direction} character-surface brightness to value {format_number(value)}"


def compile_beauty_glow_prompt(beauty: Mapping[str, Any]) -> str:
    value = float(beauty["glow_brightness"])
    if value <= EPSILON:
        return ""
    threshold = float(beauty["glow_threshold"])
    threshold_clause = (
        "across all non-black character face, skin, and material regions"
        if threshold <= EPSILON
        else (
            "only in character face, skin, and material regions brighter than threshold "
            f"{format_number(threshold)}"
        )
    )
    return (
        f"Add a {_common_strength(value)} character beauty glow {threshold_clause}, "
        f"with a configured glow width of {format_number(float(beauty['glow_width']))}."
    )


def compile_beauty_prompt(state: Mapping[str, Any]) -> str:
    beauty = state.get("beauty") if isinstance(state.get("beauty"), Mapping) else state
    if not bool(beauty.get("enabled", False)):
        return ""
    shadow_phrase = _beauty_shadow_phrase(float(beauty["soften_shadows"]))
    if not is_zero(float(beauty["soften_shadows"])):
        shadow_phrase += " " + _beauty_threshold_phrase(float(beauty["shadow_threshold"]))
    parts = [
        (
            "Apply Character Beauty exclusively inside each visible character's matte and silhouette, "
            "including only character-owned face, eyes, teeth, skin when present, hair, clothing, "
            "accessories, and intrinsic material surfaces. Treat every character matte as a hard "
            "processing boundary."
        ),
        (
            "Exclude the background and environment completely, including sets, terrain, architecture, "
            "vegetation, sky, atmosphere, and environment-only objects; Character Beauty must not alter "
            "their pixels, lighting, color, contrast, detail, or material response."
        ),
        (
            "Within that character-only scope, apply restrained beauty processing with "
            f"{shadow_phrase}, while preserving "
            "clean character edges, material definition, and natural character-surface texture."
        ),
        (
            f"{_beauty_saturation_clause(float(beauty['saturation']))} and "
            f"{_beauty_brightness_clause(float(beauty['brightness']))}."
        ),
        compile_beauty_glow_prompt(beauty),
    ]
    advanced = (
        ("soft_focus", "character-surface soft-focus diffusion"),
        ("blur_amount", "edge-aware character-surface blur"),
    )
    for key, label in advanced:
        value = float(beauty[key])
        if value > EPSILON:
            parts.append(
                f"Apply {_common_strength(value)} {label} at value {format_number(value)}."
            )
    pore_size = float(beauty["pore_size"])
    if pore_size > EPSILON:
        parts.append(
            "Preserve character texture features smaller than the pore-size threshold "
            f"{format_number(pore_size)}."
        )
    reduce_shine = float(beauty["reduce_shine"])
    if reduce_shine > EPSILON:
        parts.append(
            f"Apply {_common_strength(reduce_shine)} reduction of bright character-surface shine at value "
            f"{format_number(reduce_shine)} while preserving local color."
        )
    if all(float(beauty[key]) <= EPSILON for key in ("soft_focus", "blur_amount", "pore_size", "reduce_shine")):
        parts.append(
            "Do not add character soft-focus diffusion, skin blur, pore removal, shine reduction, "
            "or any airbrushed or plasticky character smoothing."
        )
    parts.append(
        "Preserve a clean, natural, polished character appearance with stable color fidelity and intact "
        "local detail under the authored color and brightness adjustments. Retain facial structure, "
        "feature placement, proportions, silhouette, material boundaries, markings, and asymmetries "
        "through the resolved expression, deformation, perspective, and occlusion. Keep subject "
        "animation and camera movement on their resolved timing; character-surface soft-focus "
        "diffusion changes optical treatment only. Every Character Beauty control in this block is character-only and must not spill, "
        "feather, or propagate beyond the character matte into the background or environment."
    )
    return "CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE\n" + join_sentences(parts)


def compile_finish_look_prompt(state: Mapping[str, Any]) -> str:
    normalized = validate_finish_look_state(state)
    return compile_beauty_prompt(normalized["beauty"]) if normalized["beauty"]["enabled"] else ""


# New nodes are opt-in and do not alter the project's approved look.
EXPECTED_DEFAULT_FINISH_LOOK_OUT = ""


def _deep_patch(base: dict[str, Any], changes: Mapping[str, Any], path: str = "state") -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in changes.items():
        if key not in result:
            raise FinishLookValidationError(f"{path}.{key} is not a supported field.")
        if isinstance(result[key], dict):
            if not isinstance(value, Mapping):
                raise FinishLookValidationError(f"{path}.{key} must be an object.")
            result[key] = _deep_patch(result[key], value, f"{path}.{key}")
        else:
            result[key] = copy.deepcopy(value)
    return result


def normalize_remote_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FinishLookValidationError("remote request must be a dict object.")
    request = _mapping(value, "remote request")
    required = {"schema", "version", "request_id", "base_revision", "changes"}
    _exact_keys(request, required, "remote request")
    if request["schema"] != REMOTE_SCHEMA or type(request["version"]) is not int or request["version"] != 1:
        raise FinishLookValidationError("Unsupported remote request schema or version.")
    request_id = request["request_id"]
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > MAX_REQUEST_ID_LENGTH:
        raise FinishLookValidationError("remote request_id must be a non-empty bounded string.")
    revision = request["base_revision"]
    if type(revision) is not int or revision < 0:
        raise FinishLookValidationError("remote base_revision must be a non-negative integer.")
    if not isinstance(request["changes"], Mapping):
        raise FinishLookValidationError("remote changes must be a dict object.")
    changes = request["changes"]
    if not changes or any(key != "beauty" for key in changes):
        raise FinishLookValidationError("remote changes must contain only beauty.")
    return {
        "schema": REMOTE_SCHEMA,
        "version": 1,
        "request_id": request_id.strip(),
        "base_revision": revision,
        "changes": copy.deepcopy(dict(changes)),
    }


def apply_finish_look_remote_request(
    current_state: Mapping[str, Any],
    request: Any,
    *,
    current_revision: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical = validate_finish_look_state(current_state)
    normalized = normalize_remote_request(request)
    request_id = normalized["request_id"]
    if normalized["base_revision"] != current_revision:
        return canonical, {
            "schema_version": 1,
            "status": "rejected",
            "code": "stale_revision",
            "message": f"Expected base_revision {current_revision}.",
            "request_id": request_id,
            "revision": current_revision,
        }
    patched = _deep_patch(canonical, normalized["changes"])
    validated = validate_finish_look_state(patched)
    return validated, {
        "schema_version": 1,
        "status": "accepted",
        "code": "ok",
        "message": "Finish Look state updated.",
        "request_id": request_id,
        "revision": current_revision + 1,
    }


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def default_widget_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "language": "ko",
        "remote_connected": False,
        "shot_catalog": {},
        "shot": _shot_only(),
        "finish_look": default_finish_look_state(),
        "shot_manager": True,
        "shot_editor_expanded": True,
        "shot_documents": {},
    }


def validate_widget_state(value: Any) -> dict[str, Any]:
    state = _mapping(value, "widget state")
    required = {
        "schema_version",
        "language",
        "remote_connected",
        "finish_look",
    }
    allowed = required | {
        "catalog",  # Discard the obsolete catalog during legacy hydration.
        "shot_catalog",
        "shot",
        "shot_manager", "shot_editor_expanded", "shot_documents", UI_TRANSPORT_KEY,
    }
    missing = sorted(required - set(state))
    unknown = sorted(set(state) - allowed)
    if missing:
        raise FinishLookValidationError(
            f"widget state is missing: {', '.join(missing)}."
        )
    if unknown:
        raise FinishLookValidationError(
            f"widget state contains unsupported keys: {', '.join(unknown)}."
        )
    if type(state["schema_version"]) is not int or state["schema_version"] != 1:
        raise FinishLookValidationError("widget schema_version must be integer 1.")
    language = _choice(state["language"], ("ko", "en"), "widget language")
    shot_catalog = _normalize_shot_catalog(
        state.get("shot_catalog"), allow_sparse=True
    )
    shot = _normalize_shot_selection(state.get("shot"), shot_catalog)
    return {
        "schema_version": 1,
        "language": language,
        "remote_connected": _boolean(state["remote_connected"], "widget remote_connected"),
        "shot_catalog": shot_catalog,
        "shot": shot,
        "finish_look": validate_finish_look_state(state["finish_look"]),
        "shot_manager": True,
        "shot_editor_expanded": state.get("shot_editor_expanded", True) is not False,
        "shot_documents": copy.deepcopy(state.get("shot_documents") or {}),
    }


def _mode(name: str) -> Any:
    if ParameterMode is None:
        return None
    return {getattr(ParameterMode, name)}


def _parameter_attempts(kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    modern = dict(kwargs)
    if modern.get("allowed_modes") is not None:
        for key in ("allow_input", "allow_output", "allow_property"):
            modern.pop(key, None)
    legacy = dict(kwargs)
    legacy.pop("allowed_modes", None)
    attempts: list[dict[str, Any]] = []
    for candidate in (modern, legacy):
        attempts.append(candidate)
        without_type = dict(candidate)
        without_type.pop("type", None)
        if without_type != candidate:
            attempts.append(without_type)
    return attempts


def _add_parameter(node: Any, **kwargs: Any) -> Any:
    if parameter_exists(node, str(kwargs.get("name") or "")):
        return getattr(node, "parameters", {}).get(kwargs["name"])
    last_error: Exception | None = None
    for attempt in _parameter_attempts(kwargs):
        try:
            parameter = Parameter(**attempt)
            node.add_parameter(parameter)
            return parameter
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError(f"Unable to add parameter {kwargs.get('name')}.")


def _parameter_object(node: Any, name: str) -> Any:
    for getter_name in ("get_parameter_by_name", "get_parameter"):
        getter = getattr(node, getter_name, None)
        if callable(getter):
            try:
                parameter = getter(name)
                if parameter is not None:
                    return parameter
            except Exception:
                pass
    parameters = getattr(node, "parameters", None)
    if isinstance(parameters, dict):
        return parameters.get(name)
    if isinstance(parameters, (list, tuple)):
        return next(
            (
                parameter
                for parameter in parameters
                if getattr(parameter, "name", None) == name
            ),
            None,
        )
    return None


def _add_widget_parameter(node: Any, *, widget_name: str, **kwargs: Any) -> Any:
    """Attach the Widget trait before Griptape performs its first row layout."""

    name = str(kwargs.get("name") or "")
    if parameter_exists(node, name):
        parameter = _parameter_object(node, name)
    else:
        parameter = None
        last_error: Exception | None = None
        for attempt in _parameter_attempts(kwargs):
            if Widget is not None:
                try:
                    parameter = Parameter(
                        **{
                            **attempt,
                            "traits": {
                                Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                            },
                        }
                    )
                    break
                except Exception as exc:
                    last_error = exc
            try:
                parameter = Parameter(**attempt)
                if Widget is not None:
                    parameter.add_trait(
                        Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                    )
                break
            except Exception as exc:
                parameter = None
                last_error = exc
        if parameter is None:
            raise last_error or RuntimeError(f"Unable to add widget parameter {name}.")
        # Adding the trait after add_parameter() leaves the host's first layout
        # cached as a compact native dict row (about 40-48 px).
        node.add_parameter(parameter)

    if Widget is not None and parameter is not None:
        has_widget = False
        try:
            finder = getattr(parameter, "find_elements_by_type", None)
            if callable(finder):
                has_widget = bool(finder(Widget, find_recursively=True))
        except Exception:
            has_widget = False
        if not has_widget:
            try:
                parameter.add_trait(
                    Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                )
            except Exception:
                pass
    return parameter


def _apply_parameter_ui_options(parameter: Any, options: Mapping[str, Any]) -> None:
    if parameter is None:
        return
    try:
        current = dict(getattr(parameter, "ui_options", {}) or {})
        current.update(dict(options))
        parameter.ui_options = current
    except Exception:
        return
    updater = getattr(parameter, "update_ui_options_key", None)
    if callable(updater):
        for key, value in options.items():
            try:
                updater(key, value)
            except Exception:
                pass


def _hidden_transport_ui_options() -> dict[str, Any]:
    return {
        "display_name": "",
        "hide": True,
        "hide_property": True,
        "hide_label": True,
        "hide_handles": True,
        "height": 1,
        "min_height": 0,
        "max_height": 1,
        "is_full_width": True,
        "expandable": False,
        "compact": True,
    }


def _hide_transport_parameter(parameter: Any) -> None:
    if parameter is None:
        return
    for attribute in ("hide", "hide_property", "hide_label"):
        try:
            setattr(parameter, attribute, True)
        except Exception:
            pass
    _apply_parameter_ui_options(parameter, _hidden_transport_ui_options())


def _raw_parameter(node: Any, name: str) -> Any:
    try:
        return node.get_parameter_value(name)
    except Exception:
        parameter = getattr(node, "parameters", {}).get(name)
        return getattr(parameter, "default_value", None)


def _set_parameter_silently(node: Any, name: str, value: Any) -> None:
    parent_setter = getattr(super(type(node), node), "set_parameter_value", None)
    if callable(parent_setter):
        try:
            if ParameterMode is None:
                parent_setter(name, copy.deepcopy(value))
            else:
                parent_setter(
                    name,
                    copy.deepcopy(value),
                    initial_setup=False,
                    emit_change=False,
                    skip_before_value_set=True,
                )
            return
        except (AttributeError, TypeError):
            try:
                parent_setter(name, copy.deepcopy(value))
                return
            except Exception:
                pass
        except Exception:
            pass
    parameter = getattr(node, "parameters", {}).get(name)
    if parameter is not None:
        try:
            parameter.default_value = copy.deepcopy(value)
        except Exception:
            pass


class HMBFinishLookLibrary(DataNode):
    """Opt-in, character-matte-only Beauty instruction compiler."""

    def __init__(self, **kwargs: Any) -> None:
        serialized_metadata = kwargs.get("metadata")
        restored_size = (
            dict(serialized_metadata.get("size") or {})
            if isinstance(serialized_metadata, dict)
            and isinstance(serialized_metadata.get("size"), dict)
            else {}
        )
        super().__init__(**kwargs)
        if restored_size:
            try:
                current_metadata = dict(getattr(self, "metadata", {}) or {})
                current_metadata["size"] = restored_size
                self.metadata = current_metadata
            except Exception:
                pass
        try:
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
                initial_size_setter(
                    width=FINISH_LOOK_NODE_WIDTH,
                    height=FINISH_LOOK_NODE_HEIGHT,
                )
            elif not has_saved_size:
                metadata.setdefault(
                    "size",
                    {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                )
                self.metadata = metadata
            self.ui_options = {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
                "default_width": FINISH_LOOK_NODE_WIDTH,
                "default_height": FINISH_LOOK_NODE_HEIGHT,
                "preferred_width": FINISH_LOOK_NODE_WIDTH,
                "preferred_height": FINISH_LOOK_NODE_HEIGHT,
                "initial_width": FINISH_LOOK_NODE_WIDTH,
                "initial_height": FINISH_LOOK_NODE_HEIGHT,
                "node_size": {
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "height": FINISH_LOOK_NODE_HEIGHT,
                },
                "default_size": {
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "height": FINISH_LOOK_NODE_HEIGHT,
                },
                "initial_size": {
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "height": FINISH_LOOK_NODE_HEIGHT,
                },
                "min_width": FINISH_LOOK_NODE_MIN_WIDTH,
                "min_height": FINISH_LOOK_NODE_MIN_HEIGHT,
                "resizable": True,
            }
            self.width = (
                saved_size.get("width") if has_saved_size else FINISH_LOOK_NODE_WIDTH
            )
            self.height = (
                saved_size.get("height") if has_saved_size else FINISH_LOOK_NODE_HEIGHT
            )
        except Exception:
            pass
        self.category = "HMB_GP_Production"
        self.description = (
            "Compiles opt-in character-matte-only Character Beauty values "
            "into deterministic English production prose."
        )
        self._state_lock = threading.RLock()
        self._last_valid_state = default_finish_look_state()
        self._widget_state = default_widget_state()
        self._remote_revision = 0
        self._remote_connected = False
        self._seen_remote_requests: list[str] = []
        self._remote_status = copy.deepcopy(DEFAULT_REMOTE_STATUS)
        self._node_deleted = False
        # Shared Shot routing excludes a node as soon as this flag is set,
        # including the short interval before retained mode removes it from
        # the flow registry.
        self._hmb_node_deleted = False
        self._delete_parent_called = False
        self._syncing_widget = False
        self._hmb_shot_catalog_snapshot: dict[str, Any] = {}
        self._hmb_shot_route_status: dict[str, Any] = {}
        self._hmb_shot_catalog_syncing = False
        self._hmb_initial_shot_autoclaim_pending = True
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_finish_snapshot_generation = 0
        self._hmb_finish_snapshot_fingerprint = ""
        self._hmb_finish_snapshot_live_fingerprint = ""
        self._hmb_finish_live_values: dict[str, Any] = {}
        self._hmb_finish_live_publication_owner = 0
        # A hidden Shot snapshot may publish only after the router has attached
        # the exact same-UUID Seedance edge.  Keep this false across
        # construction, hydration, and Shot changes so a stale edge can never
        # receive the next Shot's finishing instruction.
        self._hmb_finish_route_ready = False
        self._hmb_finish_snapshot: dict[str, Any] = {}
        self._hmb_finish_documents: dict[str, Any] = {}
        self._hmb_finish_archives: dict[str, Any] = {}
        self._hmb_finish_remote_owners: dict[str, str] = {}
        self._hmb_finish_active_key = "__standalone__"
        self._hmb_finish_store_syncing = False
        self._hmb_finish_hydrating = False
        self._hmb_finish_loaded_store = False
        self._setup_parameters()
        self._repair_ui_contract()
        self._publish_all(live=False)
        self._restore_widget_parameter(live=False)
        try:
            from _hmb_shot_routing import schedule_post_registration_reconcile

            schedule_post_registration_reconcile(self)
        except Exception:
            pass
        LOGGER.info("[HMB][FINISH] Finish Look initialized with schema version 1.")

    def _setup_parameters(self) -> None:
        add_group(self, "A_HMB_FINISH_LOOK", "HMB Finish Look", collapsed=False)
        widget_ui_options = {
            "display_name": "HMB Finish Look",
            "is_full_width": True,
            "height": FINISH_LOOK_WIDGET_HEIGHT,
            "min_height": FINISH_LOOK_WIDGET_MIN_HEIGHT,
            "widget_height": FINISH_LOOK_WIDGET_HEIGHT,
            "width": FINISH_LOOK_NODE_WIDTH,
            "min_width": FINISH_LOOK_NODE_MIN_WIDTH,
            "preferred_width": FINISH_LOOK_NODE_WIDTH,
            "preferred_height": FINISH_LOOK_WIDGET_HEIGHT,
            "default_width": FINISH_LOOK_NODE_WIDTH,
            "default_height": FINISH_LOOK_WIDGET_HEIGHT,
            "initial_width": FINISH_LOOK_NODE_WIDTH,
            "initial_height": FINISH_LOOK_WIDGET_HEIGHT,
            "node_size": {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
            },
            "default_size": {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
            },
            "initial_size": {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
            },
            # This is the sole visible Finish Look row. Keeping it expandable
            # prevents Griptape's first 40 px allocator pass from clipping the
            # dashboard to its header.
            "expandable": True,
            "resizable": True,
            "compact": False,
            "hide": False,
            "hide_property": False,
        }
        widget_parameter = _add_widget_parameter(
            self,
            widget_name=WIDGET_NAME,
            name=WIDGET_PARAMETER_NAME,
            default_value=default_widget_state(),
            type="dict",
            input_types=["dict"],
            allow_input=False,
            allow_output=False,
            allow_property=True,
            allowed_modes=_mode("PROPERTY"),
            tooltip=(
                "HMB Finish Look dashboard state. Character Beauty has one direct Enable switch, no value "
                "bundle selector, and applies only inside character mattes."
            ),
            ui_options=widget_ui_options,
        )
        for attribute, value in (
            ("hide", False),
            ("hide_property", False),
            ("serializable", True),
            ("settable", True),
        ):
            try:
                setattr(widget_parameter, attribute, value)
            except Exception:
                pass
        _apply_parameter_ui_options(widget_parameter, widget_ui_options)

        parameter = _add_parameter(
            self, name=REMOTE_INPUT_PARAMETER_NAME, default_value={}, type="dict",
            input_types=["dict"], allow_input=True, allow_output=False,
            allow_property=False, allowed_modes=_mode("INPUT"), hide_property=True,
            serializable=False, tooltip="Validated same-flow Finish Look remote patch input.",
            ui_options=_hidden_transport_ui_options(),
        )
        _hide_transport_parameter(parameter)
        _add_parameter(self, name=SHOT_STORE_PARAMETER_NAME, default_value={}, type="dict",
            allowed_modes=_mode("PROPERTY"), hide=True, hide_property=True, serializable=True,
            ui_options=_hidden_transport_ui_options())
        outputs = (
            (
                FINISH_LOOK_OUTPUT_PARAMETER_NAME,
                "",
                "str",
                "Deterministic English character-matte-only Beauty prose; empty when disabled.",
            ),
            (
                SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
                {},
                "dict",
                "Hidden same-Shot Finish Look dependency for HMBSeedanceGeneration.",
            ),
            (FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME, default_finish_look_state(), "dict", "Canonical schema_version 2 Beauty-only state."),
            (REMOTE_STATUS_OUTPUT_PARAMETER_NAME, copy.deepcopy(DEFAULT_REMOTE_STATUS), "dict", "Latest strict remote patch result."),
        )
        for name, default, type_name, tooltip in outputs:
            parameter = _add_parameter(
                self,
                name=name,
                default_value=default,
                type=type_name,
                output_type=type_name,
                input_types=[],
                allow_input=False,
                allow_output=True,
                allow_property=False,
                allowed_modes=_mode("OUTPUT"),
                settable=False,
                hide_property=True,
                tooltip=tooltip,
                ui_options=_hidden_transport_ui_options(),
            )
            _hide_transport_parameter(parameter)

    def _repair_ui_contract(self) -> None:
        """Reapply the host surface contract after saved-workflow hydration."""

        widget_parameter = _parameter_object(self, WIDGET_PARAMETER_NAME)
        if widget_parameter is not None:
            for attribute, value in (
                ("hide", False),
                ("hide_property", False),
                ("serializable", True),
                ("settable", True),
            ):
                try:
                    setattr(widget_parameter, attribute, value)
                except Exception:
                    pass
            _apply_parameter_ui_options(
                widget_parameter,
                {
                    "display_name": "HMB Finish Look",
                    "is_full_width": True,
                    "height": FINISH_LOOK_WIDGET_HEIGHT,
                    "min_height": FINISH_LOOK_WIDGET_MIN_HEIGHT,
                    "widget_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "min_width": FINISH_LOOK_NODE_MIN_WIDTH,
                    "preferred_width": FINISH_LOOK_NODE_WIDTH,
                    "preferred_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "default_width": FINISH_LOOK_NODE_WIDTH,
                    "default_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "initial_width": FINISH_LOOK_NODE_WIDTH,
                    "initial_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "node_size": {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                    "default_size": {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                    "initial_size": {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                    "expandable": True,
                    "resizable": True,
                    "compact": False,
                    "hide": False,
                    "hide_property": False,
                },
            )
        for name in (
            REMOTE_INPUT_PARAMETER_NAME,
            FINISH_LOOK_OUTPUT_PARAMETER_NAME,
            SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
            FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME,
            REMOTE_STATUS_OUTPUT_PARAMETER_NAME,
        ):
            _hide_transport_parameter(_parameter_object(self, name))

    def _publish_parameter(
        self, name: str, value: Any, *, live: bool, stage_output: bool = True
    ) -> bool:
        if stage_output:
            set_output(self, name, copy.deepcopy(value))
        if not live:
            return True
        publisher = getattr(self, "publish_update_to_parameter", None)
        if not callable(publisher):
            return False
        try:
            publisher(name, copy.deepcopy(value))
        except Exception:
            return False
        return True

    def _update_finish_snapshot_locked(
        self,
        prompt: str,
        state: Mapping[str, Any],
    ) -> bool:
        subscription = self._hmb_shot_channel_subscription()
        if not subscription.get("enabled"):
            changed = bool(self._hmb_finish_snapshot)
            self._hmb_finish_snapshot = {}
            self._hmb_finish_snapshot_fingerprint = ""
            return changed
        identity = {
            "channel_uuid": subscription.get("channel_uuid", ""),
            "shot_uuid": subscription.get("shot_uuid", ""),
            "shot_number": subscription.get("shot_number", 1),
            "shot_name": subscription.get("shot_name", "Only"),
        }
        state_sha256 = hashlib.sha256(
            json.dumps(
                state,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    **identity,
                    "state_sha256": state_sha256,
                    "instruction_sha256": prompt_sha256,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        changed = fingerprint != self._hmb_finish_snapshot_fingerprint
        if changed:
            self._hmb_finish_snapshot_generation += 1
            self._hmb_finish_snapshot_fingerprint = fingerprint
        self._hmb_finish_snapshot = {
            "schema": FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA,
            "version": FINISH_LOOK_SHOT_SNAPSHOT_VERSION,
            **identity,
            "generation": max(1, self._hmb_finish_snapshot_generation),
            "finish_look_sha256": prompt_sha256,
            "state_sha256": state_sha256,
            "finish_look_out": prompt,
            "finish_look_state": copy.deepcopy(dict(state)),
        }
        return changed

    def _publish_all(self, *, live: bool) -> None:
        with self._state_lock:
            state = copy.deepcopy(self._last_valid_state)
            prompt = compile_finish_look_prompt(state)
            self._update_finish_snapshot_locked(prompt, state)
            self._hmb_finish_persist_store()
            shot_snapshot = copy.deepcopy(self._hmb_finish_snapshot)
            shot_fingerprint = self._hmb_finish_snapshot_fingerprint
            publish_shot_snapshot = (
                self._hmb_finish_route_ready
                and bool(shot_snapshot)
                and shot_fingerprint != self._hmb_finish_snapshot_live_fingerprint
            )
            remote_status = copy.deepcopy(self._remote_status)
            self._hmb_finish_live_publication_owner += 1
            owner = self._hmb_finish_live_publication_owner
            # Stage every changed sibling under the same owner before any live
            # publication can wake a consumer. A reentrant newer publication
            # invalidates this owner's remaining work.
            values = (
                (FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME, state),
                (FINISH_LOOK_OUTPUT_PARAMETER_NAME, prompt),
                (SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME, shot_snapshot),
                (REMOTE_STATUS_OUTPUT_PARAMETER_NAME, remote_status),
            )
            staged = getattr(self, "parameter_output_values", {})
            for name, value in values:
                if owner != self._hmb_finish_live_publication_owner:
                    return
                if (
                    not isinstance(staged, Mapping)
                    or name not in staged
                    or staged[name] != value
                ):
                    set_output(self, name, copy.deepcopy(value))
        if live:
            for name, value in values:
                with self._state_lock:
                    if owner != self._hmb_finish_live_publication_owner:
                        break
                if name == SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME:
                    if publish_shot_snapshot:
                        if self._publish_parameter(
                            name, value, live=True, stage_output=False
                        ):
                            with self._state_lock:
                                if owner == self._hmb_finish_live_publication_owner:
                                    self._hmb_finish_snapshot_live_fingerprint = shot_fingerprint
                    continue
                with self._state_lock:
                    already_live = (
                        name in self._hmb_finish_live_values
                        and self._hmb_finish_live_values[name] == value
                    )
                if already_live:
                    continue
                if self._publish_parameter(name, value, live=True, stage_output=False):
                    with self._state_lock:
                        if owner == self._hmb_finish_live_publication_owner:
                            self._hmb_finish_live_values[name] = copy.deepcopy(value)

    @staticmethod
    def _hmb_finish_key(channel_uuid="", shot_uuid=""):
        return str(channel_uuid) + "\x1f" + str(shot_uuid) if channel_uuid and shot_uuid else "__standalone__"

    def _hmb_finish_ensure_manager_state(self):
        defaults = {"_hmb_finish_documents": {}, "_hmb_finish_archives": {}, "_hmb_finish_remote_owners": {},
            "_hmb_finish_active_key": "__standalone__", "_hmb_finish_store_syncing": False,
            "_hmb_finish_hydrating": False, "_hmb_finish_loaded_store": False, "_hmb_finish_loaded_store_value": None}
        for name, value in defaults.items():
            if not hasattr(self, name):
                setattr(self, name, copy.deepcopy(value))

    def _hmb_finish_ui_clock(self):
        """Instance-local UI transport, never part of creative state or snapshots."""
        if not hasattr(self, "_hmb_finish_ui_session"):
            self._hmb_finish_ui_session = uuid4().hex
            self._hmb_finish_ui_revision = 0
            self._hmb_finish_ui_fingerprint = ""
            self._hmb_finish_ui_target_fingerprints = {}
            self._hmb_finish_ui_target_revisions = {}
            self._hmb_finish_ui_clients = {}
            self._hmb_finish_ui_ack = {}
        documents = dict(self._hmb_finish_documents)
        documents[self._hmb_finish_active_key] = self._hmb_finish_current_document()
        catalog = self._widget_state.get("shot_catalog") or {}
        identities = {self._hmb_finish_key(catalog.get("channel_uuid"), row["shot_uuid"]): row
            for row in catalog.get("shots", [])}
        identities["__standalone__"] = _shot_only()
        targets = {key: _canonical_sha256({"finish_look": (documents.get(key) or {}).get("finish_look", default_finish_look_state()),
            "remote_revision": (documents.get(key) or {}).get("remote_revision", 0),
            "identity": identity, "remote_connected": self._remote_connected}) for key, identity in identities.items()}
        fingerprint = _canonical_sha256({"widget": self._widget_state, "targets": targets})
        if fingerprint != self._hmb_finish_ui_fingerprint:
            self._hmb_finish_ui_revision += 1
            self._hmb_finish_ui_fingerprint = fingerprint
            self._hmb_finish_ui_target_revisions = {key: self._hmb_finish_ui_target_revisions.get(key, 0)
                if self._hmb_finish_ui_target_fingerprints.get(key) == value else self._hmb_finish_ui_revision
                for key, value in targets.items()}
            self._hmb_finish_ui_target_fingerprints = targets
            self._hmb_finish_ui_ack = {}
        return {"schema": UI_TRANSPORT_SCHEMA, "version": 1, "session_id": self._hmb_finish_ui_session,
            "revision": self._hmb_finish_ui_revision, "target_revisions": dict(self._hmb_finish_ui_target_revisions),
            "status": "state", "client_id": "", "client_epoch": "", "request_id": "", "sequence": 0, **self._hmb_finish_ui_ack}

    def _hmb_finish_ui_reply(self, command, status):
        self._restore_widget_parameter(live=False)
        self._hmb_finish_ui_ack = {"status": status,
            **{key: command.get(key, "" if key != "sequence" else 0) for key in ("client_id", "request_id", "sequence")}}
        client = self._hmb_finish_ui_clients.get(command.get("client_id"), {})
        self._hmb_finish_ui_ack["client_epoch"] = client.get("client_epoch", "")
        self._restore_widget_parameter(live=True)

    def _hmb_finish_apply_ui_command(self, normalized, command):
        """CAS/dedup for UI requests. Refresh and selection never apply Beauty."""
        if self._node_deleted or getattr(self, "_hmb_node_deleted", False):
            return
        with self._state_lock:
            clock = self._hmb_finish_ui_clock()
            required = {"schema", "version", "operation", "session_id", "base_revision", "base_target_revision", "client_id", "client_epoch", "request_id", "sequence"}
            valid = isinstance(command, Mapping) and set(command) == required and command.get("schema") == UI_TRANSPORT_SCHEMA and type(command.get("version")) is int and command.get("version") == 1
            valid = valid and command.get("operation") in {"refresh", "select", "edit"}
            valid = valid and all(isinstance(command.get(key), str) and 0 < len(command[key]) <= 128 for key in ("client_id", "request_id"))
            valid = valid and isinstance(command.get("session_id"), str) and len(command["session_id"]) <= 128
            valid = valid and isinstance(command.get("client_epoch"), str) and len(command["client_epoch"]) <= 128
            valid = valid and all(type(command.get(key)) is int and 0 <= command[key] <= 9007199254740991 for key in ("sequence", "base_revision", "base_target_revision")) and command.get("sequence", 0) > 0
            if not valid:
                self._hmb_finish_ui_reply({}, "invalid_command");return
            operation = command["operation"]
            if operation != "refresh" and command["session_id"] != clock["session_id"]:
                self._hmb_finish_ui_reply(command, "stale_session");return
            previous = self._hmb_finish_ui_clients.get(command["client_id"], {})
            if operation == "refresh" and not previous:
                previous = {"sequence": 0, "request_id": "", "client_epoch": uuid4().hex}
                self._hmb_finish_ui_clients[command["client_id"]] = previous
                while len(self._hmb_finish_ui_clients) > MAX_UI_CLIENTS:
                    self._hmb_finish_ui_clients.pop(next(iter(self._hmb_finish_ui_clients)))
            elif not previous or (command["client_epoch"] != previous.get("client_epoch") and not (
                operation == "refresh" and command["request_id"] == previous.get("request_id") and command["sequence"] == previous.get("sequence"))):
                self._hmb_finish_ui_reply(command, "stale_client");return
            if command["sequence"] <= previous.get("sequence", 0):
                duplicate = command["sequence"] == previous.get("sequence") and command["request_id"] == previous.get("request_id")
                self._hmb_finish_ui_reply(command, "duplicate" if duplicate else "stale_sequence");return
            self._hmb_finish_ui_clients.pop(command["client_id"], None)
            self._hmb_finish_ui_clients[command["client_id"]] = {**{key: command[key] for key in ("sequence", "request_id")}, "client_epoch": previous["client_epoch"]}
            if operation == "refresh":
                self._hmb_finish_ui_reply(command, "refreshed");return
            catalog = self._hmb_available_finish_shot_catalog(self._hmb_shot_catalog_snapshot, self._widget_state.get("shot")) or self._widget_state.get("shot_catalog") or {}
            requested = _normalize_shot_selection(normalized.get("shot"), catalog)
            key = self._hmb_finish_key(requested["channel_uuid"], requested["shot_uuid"])
            if key not in clock["target_revisions"] or (catalog.get("shots") and not requested["shot_uuid"]):
                self._hmb_finish_ui_reply(command, "target_unavailable");return
            if operation == "select":
                selection = copy.deepcopy(self._widget_state)
                selection["shot"] = requested
                self._apply_widget_value(selection)
                self._hmb_finish_ui_reply(command, "accepted");return
            active = key == self._hmb_finish_active_key
            document = self._hmb_finish_current_document() if active else copy.deepcopy(self._hmb_finish_documents.get(key) or {})
            requested_state = copy.deepcopy(normalized["finish_look"])
            changed = requested_state != document.get("finish_look", default_finish_look_state())
            if changed and (command["base_revision"] > clock["revision"] or command["base_target_revision"] != clock["target_revisions"][key]):
                self._hmb_finish_ui_reply(command, "conflict");return
            if changed and self._remote_connected:
                self._hmb_finish_ui_reply(command, "remote_locked");return
            if changed:
                document["finish_look"] = requested_state
                document["remote_revision"] = int(document.get("remote_revision") or 0) + 1
                document["remote_status"] = {"schema_version": 1, "status": "local_update", "code": "ok",
                    "message": "Finish Look state updated locally.", "request_id": "", "revision": document["remote_revision"]}
                if active:
                    self._last_valid_state = requested_state
                    self._remote_revision = document["remote_revision"]
                    self._remote_status = document["remote_status"]
                else:
                    document["snapshot_generation"] = int(document.get("snapshot_generation") or 0) + 1
                    document["snapshot_fingerprint"] = "";document["snapshot"] = {}
                    self._hmb_finish_documents[key] = document
            self._widget_state["language"] = normalized["language"]
            if changed and active:
                self._publish_all(live=True)
            elif changed:
                self._hmb_finish_persist_store()
            self._hmb_finish_ui_reply(command, "accepted")

    def _hmb_shot_manager_enabled(self):
        return not bool(getattr(self, "_hmb_finish_legacy_mode", False))

    def _hmb_shot_manager_subscriptions(self):
        if not self._hmb_shot_manager_enabled():
            value = self._hmb_shot_channel_subscription()
            return [value] if value.get("enabled") else []
        catalog = getattr(self, "_hmb_shot_catalog_snapshot", {})
        return [{"schema": SHOT_SUBSCRIPTION_SCHEMA, "version": 1, "participant_kind": "finish_look",
            "enabled": True, "channel_uuid": catalog["channel_uuid"], "shot_uuid": row["shot_uuid"],
            "shot_number": row["number"], "shot_name": row["name"]} for row in catalog.get("shots", [])]

    _hmb_finish_look_shot_subscriptions = _hmb_shot_manager_subscriptions

    def _hmb_finish_current_document(self):
        return {"finish_look": copy.deepcopy(self._last_valid_state), "remote_revision": self._remote_revision,
            "seen_remote_requests": list(self._seen_remote_requests), "remote_status": copy.deepcopy(self._remote_status),
            "snapshot_generation": self._hmb_finish_snapshot_generation,
            "snapshot_fingerprint": self._hmb_finish_snapshot_fingerprint, "snapshot": copy.deepcopy(self._hmb_finish_snapshot)}

    def _hmb_finish_capture(self):
        self._hmb_finish_documents[self._hmb_finish_active_key] = self._hmb_finish_current_document()

    def _hmb_finish_activate(self, key):
        if key == self._hmb_finish_active_key:
            return
        self._hmb_finish_capture()
        document = copy.deepcopy(self._hmb_finish_documents.get(key) or {})
        self._last_valid_state = validate_finish_look_state(document.get("finish_look", default_finish_look_state()))
        self._remote_revision = int(document.get("remote_revision") or 0)
        self._seen_remote_requests = list(document.get("seen_remote_requests") or [])
        self._remote_status = copy.deepcopy(document.get("remote_status") or DEFAULT_REMOTE_STATUS)
        self._hmb_finish_snapshot_generation = int(document.get("snapshot_generation") or 0)
        self._hmb_finish_snapshot_fingerprint = str(document.get("snapshot_fingerprint") or "")
        self._hmb_finish_snapshot = copy.deepcopy(document.get("snapshot") or {})
        self._hmb_finish_active_key = key

    def _hmb_finish_persist_store(self):
        self._hmb_finish_ensure_manager_state()
        if self._hmb_finish_store_syncing or self._node_deleted:
            return
        self._hmb_finish_capture()
        value = {"schema": SHOT_STORE_SCHEMA, "version": 1, "documents": copy.deepcopy(self._hmb_finish_documents),
            "archives": copy.deepcopy(self._hmb_finish_archives), "remote_owners": dict(self._hmb_finish_remote_owners),
            "active": self._hmb_finish_active_key}
        if _raw_parameter(self, SHOT_STORE_PARAMETER_NAME) != value:
            self._hmb_finish_store_syncing = True
            try:
                _set_parameter_silently(self, SHOT_STORE_PARAMETER_NAME, value)
            finally:
                self._hmb_finish_store_syncing = False

    def _hmb_finish_restore_store(self, value):
        if not isinstance(value, Mapping) or value.get("schema") != SHOT_STORE_SCHEMA or value.get("version") != 1:
            return False
        documents = value.get("documents")
        if not isinstance(documents, dict):
            raise FinishLookValidationError("Finish Look Shot store is invalid.")
        for document in documents.values():
            validate_finish_look_state(document.get("finish_look"))
        self._hmb_finish_documents = copy.deepcopy(documents)
        self._hmb_finish_archives = copy.deepcopy(value.get("archives") or {})
        self._hmb_finish_remote_owners = dict(value.get("remote_owners") or {})
        key = str(value.get("active") or "__standalone__")
        self._hmb_finish_active_key = "__restore_pending__"
        self._hmb_finish_activate(key)
        self._hmb_finish_documents.pop("__restore_pending__", None)
        self._hmb_finish_loaded_store = True
        self._hmb_finish_legacy_mode = False
        return True

    def _hmb_capture_saved_parameter_value(self, name, value, *, is_output=False):
        if is_output or not isinstance(value, dict):
            return
        if name == WIDGET_PARAMETER_NAME and value.get("shot_manager") is not True:
            self._hmb_finish_legacy_widget = copy.deepcopy(value)
            self._hmb_finish_legacy_mode = True
        elif name == SHOT_STORE_PARAMETER_NAME and value.get("schema") == SHOT_STORE_SCHEMA:
            self._hmb_finish_loaded_store = True
            self._hmb_finish_loaded_store_value = copy.deepcopy(value)

    def _hmb_finish_look_shot_snapshot_for(self, *, channel_uuid, shot_uuid, expected_output=None):
        self._hmb_finish_ensure_manager_state()
        with self._state_lock:
            matches = [row for row in self._hmb_shot_manager_subscriptions()
                if row["channel_uuid"] == channel_uuid and row["shot_uuid"] == shot_uuid]
            if len(matches) != 1:
                raise RuntimeError("Finish Look target Shot is unavailable.")
            key = self._hmb_finish_key(channel_uuid, shot_uuid)
            document = self._hmb_finish_current_document() if key == self._hmb_finish_active_key else copy.deepcopy(self._hmb_finish_documents.get(key) or {})
            state = validate_finish_look_state(document.get("finish_look", default_finish_look_state()))
            prompt = compile_finish_look_prompt(state)
            row = matches[0]
            snapshot = {"schema": FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA, "version": FINISH_LOOK_SHOT_SNAPSHOT_VERSION,
                "channel_uuid": channel_uuid, "shot_uuid": shot_uuid, "shot_number": row["shot_number"], "shot_name": row["shot_name"],
                "generation": max(1, int(document.get("snapshot_generation") or 1)),
                "finish_look_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "state_sha256": _canonical_sha256(state), "finish_look_out": prompt, "finish_look_state": state}
        if expected_output is not None and expected_output != snapshot:
            raise RuntimeError("Finish Look target snapshot does not match its exact source.")
        return copy.deepcopy(snapshot)

    def _hmb_finish_merge_snapshot(self):
        self._hmb_finish_ensure_manager_state()
        with self._state_lock:
            subscription = self._hmb_shot_channel_subscription()
            legacy = copy.deepcopy(getattr(self, "_hmb_finish_legacy_widget", None))
            if isinstance(legacy, dict):
                shot = legacy.get("shot") or {}
                subscription = {**subscription, "channel_uuid": str(shot.get("channel_uuid") or ""),
                    "shot_uuid": str(shot.get("shot_uuid") or ""), "shot_number": int(shot.get("number") or 1), "shot_name": str(shot.get("name") or "Only")}
                subscription["enabled"] = bool(subscription["channel_uuid"] and subscription["shot_uuid"])
            current = self._hmb_finish_current_document()
            documents = copy.deepcopy(self._hmb_finish_documents) if not legacy or self._hmb_finish_loaded_store else {}
            key = self._hmb_finish_key(subscription["channel_uuid"], subscription["shot_uuid"])
            documents[key] = copy.deepcopy(current)
            cache = {"documents": copy.deepcopy(self._hmb_finish_documents), "archives": copy.deepcopy(self._hmb_finish_archives),
                "remote_owners": dict(self._hmb_finish_remote_owners), "active": self._hmb_finish_active_key,
                "widget": copy.deepcopy(self._widget_state), "current": current, "legacy_widget": legacy,
                "loaded_store": self._hmb_finish_loaded_store,
                "loaded_store_value": copy.deepcopy(getattr(self, "_hmb_finish_loaded_store_value", None)),
                "legacy_mode": bool(getattr(self, "_hmb_finish_legacy_mode", False))}
            data = {"schema": "hmb-finish-authoring-export", "version": 1, "source_node": str(self.name),
                "active_subscription": subscription, "documents": documents,
                "standalone": copy.deepcopy(documents.get("__standalone__")), "current_widget": copy.deepcopy(self._widget_state),
                "private_cache": cache, "legacy_widget": legacy}
            data["digest"] = _canonical_sha256(data)
            return data

    def _hmb_finish_authoring_state_sha256(self):
        return self._hmb_finish_merge_snapshot()["digest"]

    def _hmb_import_finish_documents(self, exports, *, expected_state_sha256):
        with self._state_lock:
            if not hmac.compare_digest(str(expected_state_sha256), self._hmb_finish_authoring_state_sha256()):
                raise RuntimeError("Finish Look migration changed before commit.")
            documents = copy.deepcopy(self._hmb_finish_documents)
            archives = copy.deepcopy(self._hmb_finish_archives)
            # Only the original authoring records are merge authority. Discard
            # load-time default projections when this is a legacy survivor.
            if getattr(self, "_hmb_finish_legacy_widget", None) and not self._hmb_finish_loaded_store:
                documents = {}
            for exported in exports:
                data = copy.deepcopy(exported);digest = str(data.pop("digest", ""))
                if data.get("schema") != "hmb-finish-authoring-export" or data.get("version") != 1 or not hmac.compare_digest(digest, _canonical_sha256(data)):
                    raise RuntimeError("Finish Look migration document is invalid.")
                for key, document in data["documents"].items():
                    validate_finish_look_state(document["finish_look"])
                    if key == "__standalone__":
                        previous = archives.get(data["source_node"])
                        if previous is not None and previous != document:
                            raise RuntimeError("Finish Look standalone archive conflicts.")
                        archives[data["source_node"]] = copy.deepcopy(document)
                    else:
                        if key in documents and documents[key] != document:
                            raise RuntimeError("Finish Look contains conflicting settings for the same Shot.")
                        documents[key] = copy.deepcopy(document)
            before = self._hmb_finish_merge_snapshot()
            before_store = copy.deepcopy(_raw_parameter(self, SHOT_STORE_PARAMETER_NAME))
            subscription = before["active_subscription"]
            active_key = self._hmb_finish_key(subscription["channel_uuid"], subscription["shot_uuid"])
            try:
                self._hmb_finish_documents = documents;self._hmb_finish_archives = archives
                self._hmb_finish_active_key = active_key
                self._hmb_finish_legacy_widget = None;self._hmb_finish_legacy_mode = False
                for key, document in documents.items():
                    for identifier in document.get("seen_remote_requests", []):
                        previous = self._hmb_finish_remote_owners.get(identifier)
                        self._hmb_finish_remote_owners[identifier] = key if previous in {None,key} else "__multiple_original_targets__"
                self._hmb_finish_persist_store()
                self._hmb_finish_loaded_store = True
            except Exception:
                self._hmb_restore_finish_merge_snapshot(before)
                _set_parameter_silently(self, SHOT_STORE_PARAMETER_NAME, before_store)
                raise
            return {"schema": "hmb-finish-authoring-import", "version": 1, "imported_count": len(exports),
                "parameter_aliases": {}, "state_sha256": self._hmb_finish_authoring_state_sha256()}

    @hmb_binding_mutation
    def _hmb_restore_finish_merge_snapshot(self, exported, *, expected_state_sha256=None):
        with self._state_lock:
            if expected_state_sha256 is not None and not hmac.compare_digest(str(expected_state_sha256), self._hmb_finish_authoring_state_sha256()):
                raise RuntimeError("Finish Look rollback state changed.")
            data = copy.deepcopy(exported);digest = str(data.pop("digest", ""))
            if data.get("schema") != "hmb-finish-authoring-export" or data.get("version") != 1 or not hmac.compare_digest(digest, _canonical_sha256(data)):
                raise RuntimeError("Finish Look rollback document is invalid.")
            cache=data["private_cache"];current=cache["current"]
            self._hmb_finish_documents=cache["documents"];self._hmb_finish_archives=cache["archives"]
            self._hmb_finish_remote_owners=cache["remote_owners"];self._hmb_finish_active_key=cache["active"]
            self._widget_state=cache["widget"];self._last_valid_state=current["finish_look"]
            self._remote_revision=current["remote_revision"];self._seen_remote_requests=current["seen_remote_requests"]
            self._remote_status=current["remote_status"];self._hmb_finish_snapshot_generation=current["snapshot_generation"]
            self._hmb_finish_snapshot_fingerprint=current["snapshot_fingerprint"];self._hmb_finish_snapshot=current["snapshot"]
            self._hmb_finish_legacy_widget=cache["legacy_widget"];self._hmb_finish_loaded_store=cache["loaded_store"]
            self._hmb_finish_loaded_store_value=cache.get("loaded_store_value")
            self._hmb_finish_legacy_mode=cache["legacy_mode"]
            return True

    def _restore_widget_parameter(self, *, live: bool = False) -> None:
        self._hmb_finish_ensure_manager_state()
        shot_catalog = _normalize_shot_catalog(
            self._widget_state.get("shot_catalog"), allow_sparse=True
        )
        shot = _normalize_shot_selection(
            self._widget_state.get("shot"), shot_catalog
        )
        self._widget_state = {
            "schema_version": 1,
            "language": self._widget_state.get("language", "ko"),
            "remote_connected": self._remote_connected,
            "shot_catalog": shot_catalog,
            "shot": shot,
            "finish_look": copy.deepcopy(self._last_valid_state),
            "shot_manager": self._hmb_shot_manager_enabled(),
            "shot_editor_expanded": self._widget_state.get("shot_editor_expanded", True) is not False,
            "shot_documents": {self._hmb_finish_key(shot_catalog.get("channel_uuid"), row["shot_uuid"]):
                copy.deepcopy(self._hmb_finish_documents.get(self._hmb_finish_key(shot_catalog.get("channel_uuid"), row["shot_uuid"]), {}).get("finish_look", default_finish_look_state()))
                for row in shot_catalog.get("shots", [])},
            }
        wire_value = {**copy.deepcopy(self._widget_state), UI_TRANSPORT_KEY: self._hmb_finish_ui_clock()}
        try:
            self._syncing_widget = True
            changed = _raw_parameter(self, WIDGET_PARAMETER_NAME) != wire_value
            if changed:
                _set_parameter_silently(self, WIDGET_PARAMETER_NAME, wire_value)
            if live and changed:
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    publisher(WIDGET_PARAMETER_NAME, copy.deepcopy(wire_value))
        except Exception:
            pass
        finally:
            self._syncing_widget = False

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        """Return the exact Shot identity owned by this Finish Look node."""

        shot = (
            self._widget_state.get("shot", {})
            if isinstance(self._widget_state, Mapping)
            else {}
        )
        normalized = _normalize_shot_selection(
            shot,
            self._widget_state.get("shot_catalog", {})
            if isinstance(self._widget_state, Mapping)
            else {},
        )
        deleted = bool(
            getattr(self, "_hmb_node_deleted", False)
            or getattr(self, "_node_deleted", False)
        )
        enabled = bool(
            not deleted
            and normalized["channel_uuid"]
            and normalized["shot_uuid"]
        )
        return {
            "schema": SHOT_SUBSCRIPTION_SCHEMA,
            "version": SHOT_SUBSCRIPTION_VERSION,
            "participant_kind": "finish_look",
            "enabled": enabled,
            "channel_uuid": normalized["channel_uuid"] if enabled else "",
            "shot_uuid": normalized["shot_uuid"] if enabled else "",
            "shot_number": normalized["number"] if enabled else 1,
            "shot_name": normalized["name"] if enabled else "Only",
        }

    def _hmb_prepare_initial_shot_selection(self, shot_uuid: Any = "") -> None:
        """Remember one router-proven, unclaimed Shot for initial adoption."""

        if not bool(getattr(self, "_hmb_initial_shot_autoclaim_pending", False)):
            return
        if self._hmb_shot_channel_subscription().get("enabled"):
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            return
        self._hmb_initial_shot_preferred_uuid = str(shot_uuid or "").strip()[:128]

    def _hmb_available_finish_shot_catalog(
        self,
        snapshot: Any,
        current_shot: Any = None,
    ) -> dict[str, Any]:
        """Hide Shots already owned by another live Finish Look node."""

        normalized = _normalize_shot_catalog(snapshot)
        if not normalized:
            return {}
        if self._hmb_shot_manager_enabled():
            return normalized
        current = (
            current_shot
            if isinstance(current_shot, Mapping)
            else self._hmb_shot_channel_subscription()
        )
        current_uuid = (
            str(current.get("shot_uuid") or "")
            if current.get("channel_uuid") == normalized["channel_uuid"]
            else ""
        )
        claimed: set[str] = set()
        try:
            from _hmb_shot_routing import _same_flow_nodes

            _flow_name, nodes = _same_flow_nodes(self)
        except Exception:
            nodes = []
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
                isinstance(subscription, Mapping)
                and subscription.get("participant_kind") == "finish_look"
                and subscription.get("enabled") is True
                and subscription.get("channel_uuid") == normalized["channel_uuid"]
                and subscription.get("shot_uuid")
            ):
                claimed.add(str(subscription["shot_uuid"]))
        shots = [
            dict(item)
            for item in normalized["shots"]
            if item["shot_uuid"] not in claimed or item["shot_uuid"] == current_uuid
        ]
        if not shots:
            return {}
        metadata_sha256 = hashlib.sha256(
            json.dumps(
                {
                    "channel_uuid": normalized["channel_uuid"],
                    "generation": normalized["generation"],
                    "shots": shots,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        # This is a bounded node-local selector projection. The original
        # authenticated catalog remains in _hmb_shot_catalog_snapshot.
        return {**normalized, "metadata_sha256": metadata_sha256, "shots": shots}

    @hmb_binding_mutation
    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        """Adopt one UUID-backed Shot without changing authored look values."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        self._hmb_finish_ensure_manager_state()
        normalized = _normalize_shot_catalog(snapshot, strict=True)
        previous = self._hmb_shot_catalog_snapshot
        if (
            isinstance(previous, Mapping)
            and previous.get("channel_uuid") == normalized["channel_uuid"]
        ):
            previous_generation = int(previous.get("generation") or 0)
            if normalized["generation"] < previous_generation:
                raise FinishLookValidationError("Shot catalog generation moved backwards.")
            if (
                normalized["generation"] == previous_generation
                and normalized["metadata_sha256"] != previous.get("metadata_sha256")
            ):
                raise FinishLookValidationError(
                    "Shot catalog changed without a new generation."
                )
        self._hmb_shot_catalog_snapshot = copy.deepcopy(normalized)
        current = self._hmb_shot_channel_subscription()
        available = self._hmb_available_finish_shot_catalog(normalized, current)
        available_shots = available.get("shots", []) if available else []
        selected = next(
            (
                item
                for item in available_shots
                if item["shot_uuid"] == current.get("shot_uuid")
            ),
            None,
        )
        if selected is None and self._hmb_shot_manager_enabled() and available_shots:
            selected = available_shots[0]
        initial_autoclaim = bool(
            selected is None
            and not current.get("enabled")
            and getattr(self, "_hmb_initial_shot_autoclaim_pending", False)
            and getattr(self, "_hmb_initial_shot_preferred_uuid", "")
        )
        if initial_autoclaim:
            preferred_uuid = str(self._hmb_initial_shot_preferred_uuid)
            selected = next(
                (item for item in available_shots if item["shot_uuid"] == preferred_uuid),
                None,
            )
        shot = (
            {
                "channel_uuid": normalized["channel_uuid"],
                "shot_uuid": selected["shot_uuid"],
                "number": selected["number"],
                "name": selected["name"],
            }
            if isinstance(selected, Mapping)
            else _shot_only()
        )
        current_identity = {
            "channel_uuid": str(current.get("channel_uuid") or ""),
            "shot_uuid": str(current.get("shot_uuid") or ""),
            "number": int(current.get("shot_number") or 1),
            "name": str(current.get("shot_name") or "Only"),
        }
        shot_route_changed = (
            str(shot.get("channel_uuid") or ""),
            str(shot.get("shot_uuid") or ""),
        ) != (
            str(current_identity.get("channel_uuid") or ""),
            str(current_identity.get("shot_uuid") or ""),
        )
        if shot != current_identity:
            # The previous retained edge may still exist until this routing
            # transaction completes. Stage the new identity without waking
            # that edge with a cross-Shot finishing instruction.
            self._hmb_finish_route_ready = False
        if initial_autoclaim:
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
        with self._state_lock:
            self._hmb_shot_catalog_syncing = True
            try:
                if self._hmb_shot_manager_enabled():
                    self._hmb_finish_activate(self._hmb_finish_key(shot["channel_uuid"], shot["shot_uuid"]))
                self._widget_state["shot_catalog"] = copy.deepcopy(available)
                self._widget_state["shot"] = shot
                self._restore_widget_parameter(live=True)
            finally:
                self._hmb_shot_catalog_syncing = False
        # Catalog delivery precedes retained-edge mutation. Stage the new
        # snapshot without waking the previously connected Shot; the router
        # will attach the staged value to the new exact UUID owner.
        self._publish_all(live=False)
        self._hmb_shot_route_status = {
            "ok": True,
            "code": "catalog_ready" if shot["shot_uuid"] else "only",
        }

    @hmb_binding_mutation
    def _hmb_clear_shot_routing_catalog(
        self,
        reason: str = "publisher_unavailable",
    ) -> dict[str, Any]:
        """Return to Only while retaining authored Character Beauty values."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()
        with self._state_lock:
            self._hmb_shot_catalog_snapshot = {}
            self._hmb_finish_route_ready = False
            self._widget_state["shot_catalog"] = {}
            self._widget_state["shot"] = _shot_only()
            if self._hmb_shot_manager_enabled():
                self._hmb_finish_activate("__standalone__")
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            self._restore_widget_parameter(live=True)
        self._publish_all(live=False)
        self._hmb_shot_route_status = {
            "ok": False,
            "code": str(reason or "publisher_unavailable")[:128],
        }
        return self._hmb_shot_channel_subscription()

    def _hmb_reject_duplicate_shot_selection(
        self,
        reason: str = "duplicate_finish_look_shot",
    ) -> dict[str, Any]:
        """Release a duplicate Shot claim but retain available selector choices."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()
        available = self._hmb_available_finish_shot_catalog(
            self._hmb_shot_catalog_snapshot,
            {},
        )
        with self._state_lock:
            self._hmb_finish_route_ready = False
            self._widget_state["shot_catalog"] = copy.deepcopy(available)
            self._widget_state["shot"] = _shot_only()
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            self._restore_widget_parameter(live=True)
        self._publish_all(live=False)
        self._hmb_shot_route_status = {
            "ok": False,
            "code": str(reason or "duplicate_finish_look_shot")[:128],
        }
        return self._hmb_shot_channel_subscription()

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if not bool(getattr(self, "_hmb_node_deleted", False)) and isinstance(value, Mapping):
            self._hmb_shot_route_status = dict(value)

    def _reconcile_shared_shot_routing(self, *, strict: bool = False) -> dict[str, Any]:
        try:
            from _hmb_shot_routing import reconcile_shot_routing

            result = reconcile_shot_routing(self)
        except Exception:
            if strict and self._hmb_shot_channel_subscription().get("enabled"):
                raise RuntimeError("Finish Look Shot routing is unavailable.") from None
            return {"ok": False, "code": "unavailable", "changed": 0}
        if strict and self._hmb_shot_channel_subscription().get("enabled"):
            prefix = str(getattr(self, "name", "") or "") + ":"
            failures = result.get("failures", ()) if isinstance(result, Mapping) else ()
            if any(str(item).startswith(prefix) for item in failures):
                raise RuntimeError("Finish Look Shot routing is incomplete or ambiguous.")
        return dict(result) if isinstance(result, Mapping) else {
            "ok": False,
            "code": "invalid_result",
            "changed": 0,
        }

    def _hmb_post_registration_shot_discovery(self) -> None:
        if not bool(getattr(self, "_hmb_node_deleted", False)):
            self._reconcile_shared_shot_routing()

    def _hmb_finish_look_shot_snapshot(self, expected_output: Any = None) -> dict[str, Any]:
        """Return a validated atomic Finish Look snapshot for Seedance."""

        with self._state_lock:
            state = validate_finish_look_state(self._last_valid_state)
            prompt = compile_finish_look_prompt(state)
            self._update_finish_snapshot_locked(prompt, state)
            snapshot = copy.deepcopy(self._hmb_finish_snapshot)
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
        if not snapshot or set(snapshot) != required:
            raise RuntimeError("Finish Look Shot snapshot is unavailable.")
        if (
            snapshot["schema"] != FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA
            or type(snapshot["version"]) is not int
            or snapshot["version"] != FINISH_LOOK_SHOT_SNAPSHOT_VERSION
            or snapshot["finish_look_state"] != state
            or not isinstance(snapshot["state_sha256"], str)
            or not hmac.compare_digest(snapshot["state_sha256"], _canonical_sha256(state))
        ):
            raise RuntimeError("Finish Look state hash does not match its canonical Beauty state.")
        if (
            not isinstance(snapshot["finish_look_sha256"], str)
            or snapshot["finish_look_out"] != prompt
            or not hmac.compare_digest(
                snapshot["finish_look_sha256"],
                hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            )
        ):
            raise RuntimeError("Finish Look instruction hash does not match.")
        if expected_output is not None and expected_output != snapshot:
            # During legacy workflow hydration the connected input may restore
            # its old v1 value after this source has migrated and published v2.
            # Only that well-formed, same-Shot stale transport is replaceable.
            # Its prose/state hash never supplies settings: the current source's
            # canonical Beauty state above remains the sole execution authority.
            legacy = expected_output if isinstance(expected_output, dict) else {}
            legacy_prompt = legacy.get("finish_look_out")
            legacy_prompt_hash = legacy.get("finish_look_sha256")
            legacy_state_hash = legacy.get("state_sha256")
            legacy_generation = legacy.get("generation")
            legacy_matches_source = (
                set(legacy) == required - {"finish_look_state"}
                and legacy.get("schema") == FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA
                and type(legacy.get("version")) is int
                and legacy["version"] == 1
                and all(
                    legacy.get(key) == snapshot[key]
                    for key in ("channel_uuid", "shot_uuid", "shot_number", "shot_name")
                )
                and type(legacy_generation) is int
                and 1 <= legacy_generation <= (1 << 53) - 1
                and isinstance(legacy_prompt, str)
                and isinstance(legacy_prompt_hash, str)
                and re.fullmatch(r"[0-9a-f]{64}", legacy_prompt_hash) is not None
                and isinstance(legacy_state_hash, str)
                and re.fullmatch(r"[0-9a-f]{64}", legacy_state_hash) is not None
                and hmac.compare_digest(
                    legacy_prompt_hash,
                    hashlib.sha256(legacy_prompt.encode("utf-8")).hexdigest(),
                )
            )
            if not legacy_matches_source:
                raise RuntimeError("Finish Look hidden output does not match its atomic snapshot.")
            if self._hmb_publish_routed_finish_snapshot(force=True) is not True:
                raise RuntimeError("Finish Look could not republish its migrated Character Beauty snapshot.")
        return snapshot

    @hmb_binding_mutation
    def _hmb_publish_routed_finish_snapshot(self, *, force: bool = False) -> bool:
        """Publish once after the router has attached the exact Seedance edge."""

        if not self._hmb_shot_channel_subscription().get("enabled"):
            with self._state_lock:
                self._hmb_finish_route_ready = False
            return False
        with self._state_lock:
            prompt = compile_finish_look_prompt(self._last_valid_state)
            self._update_finish_snapshot_locked(prompt, self._last_valid_state)
            snapshot = copy.deepcopy(self._hmb_finish_snapshot)
            fingerprint = self._hmb_finish_snapshot_fingerprint
            needs_publication = bool(
                force
                or not self._hmb_finish_route_ready
                or fingerprint != self._hmb_finish_snapshot_live_fingerprint
            )
        set_output(self, SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME, snapshot)
        if needs_publication:
            published = self._publish_parameter(
                SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
                snapshot,
                live=True,
            )
            if not published:
                with self._state_lock:
                    self._hmb_finish_route_ready = False
                return False
        with self._state_lock:
            self._hmb_finish_snapshot_live_fingerprint = fingerprint
            self._hmb_finish_route_ready = True
        return True

    def _record_bounded(self, target: list[str], identifier: str) -> None:
        target.append(identifier)
        if len(target) > MAX_REMOTE_HISTORY:
            del target[: len(target) - MAX_REMOTE_HISTORY]

    def _apply_widget_value(self, value: Any) -> None:
        self._hmb_finish_ensure_manager_state()
        if self._node_deleted:
            return
        try:
            normalized = validate_widget_state(value)
        except FinishLookValidationError as exc:
            with self._state_lock:
                self._remote_status = {
                    "schema_version": 1,
                    "status": "rejected",
                    "code": "invalid_ui_state",
                    "message": str(exc),
                    "request_id": "",
                    "revision": self._remote_revision,
                }
                self._restore_widget_parameter(live=True)
            self._publish_all(live=True)
            return
        raw = _mapping(value, "widget state")
        if UI_TRANSPORT_KEY in raw and not self._hmb_finish_hydrating:
            self._hmb_finish_apply_ui_command(normalized, raw[UI_TRANSPORT_KEY])
            return
        if normalized == self._widget_state:
            return
        remote_locked_rejected = False
        shot_changed = False
        with self._state_lock:
            previous_shot = _normalize_shot_selection(
                self._widget_state.get("shot"),
                self._widget_state.get("shot_catalog"),
            )
            authoritative_catalog = self._hmb_available_finish_shot_catalog(
                self._hmb_shot_catalog_snapshot,
                previous_shot,
            )
            # Before the first live catalog arrives, retain a serialized
            # catalog long enough for UUID-based hydration. Once routing owns
            # a catalog, browser state can never replace it.
            effective_catalog = authoritative_catalog or normalized["shot_catalog"]
            requested_shot = _normalize_shot_selection(
                normalized.get("shot"),
                effective_catalog,
            )
            shot_changed = requested_shot != previous_shot
            saved_initial_authoring = self._hmb_finish_hydrating and not self._hmb_finish_loaded_store
            if shot_changed and self._hmb_shot_manager_enabled() and not saved_initial_authoring:
                self._hmb_finish_activate(self._hmb_finish_key(requested_shot["channel_uuid"], requested_shot["shot_uuid"]))
            requested_state = copy.deepcopy(normalized["finish_look"])
            if self._hmb_shot_manager_enabled() and (shot_changed and not saved_initial_authoring or self._hmb_finish_hydrating and self._hmb_finish_loaded_store):
                requested_state = copy.deepcopy(self._last_valid_state)
            state_changed = requested_state != self._last_valid_state
            if self._remote_connected and state_changed:
                remote_locked_rejected = True
                requested_state = copy.deepcopy(self._last_valid_state)
                self._remote_status = {
                    "schema_version": 1,
                    "status": "rejected",
                    "code": "remote_locked",
                    "message": "Finish Look controls are locked while REMOTE is connected.",
                    "request_id": "",
                    "revision": self._remote_revision,
                }
            elif state_changed:
                self._remote_revision += 1
                self._remote_status = {
                    "schema_version": 1,
                    "status": "local_update",
                    "code": "ok",
                    "message": "Finish Look state updated locally.",
                    "request_id": "",
                    "revision": self._remote_revision,
                }
            self._last_valid_state = requested_state
            if saved_initial_authoring:
                self._hmb_finish_active_key = self._hmb_finish_key(requested_shot["channel_uuid"], requested_shot["shot_uuid"])
            self._widget_state = copy.deepcopy(normalized)
            self._widget_state["shot_catalog"] = copy.deepcopy(effective_catalog)
            self._widget_state["shot"] = requested_shot
            if shot_changed:
                if not self._hmb_shot_manager_enabled():
                    self._hmb_finish_route_ready = False
                self._hmb_initial_shot_autoclaim_pending = False
                self._hmb_initial_shot_preferred_uuid = ""
            self._hmb_finish_capture()
            self._restore_widget_parameter(live=remote_locked_rejected)
        if not shot_changed and not state_changed and not remote_locked_rejected:
            return
        if shot_changed and self._hmb_shot_manager_enabled():
            # Tabs choose one authoring view. Exact Generator snapshots come
            # from UUID documents, so selecting an editor neither compiles nor
            # broadcasts its state into the other connected Generator inputs.
            self._hmb_finish_persist_store()
            return
        if shot_changed and not self._hmb_shot_catalog_syncing and not self._hmb_shot_manager_enabled():
            self._publish_all(live=False)
            self._reconcile_shared_shot_routing()
            self._publish_all(live=True)
        else:
            self._publish_all(live=True)

    def _apply_remote_value(self, value: Any, *, report_duplicate: bool = True) -> None:
        self._hmb_finish_ensure_manager_state()
        if not value:
            return
        request_id = ""
        try:
            normalized_request = normalize_remote_request(value)
            request_id = normalized_request["request_id"]
            with self._state_lock:
                owner = self._hmb_finish_remote_owners.get(request_id)
                if owner is not None and owner != self._hmb_finish_active_key:
                    # A retained v1 input replay belongs to its first target.
                    # Selecting another editor must never apply it again there.
                    return
                self._hmb_finish_remote_owners[request_id] = self._hmb_finish_active_key
                if len(self._hmb_finish_remote_owners) > MAX_REMOTE_HISTORY:
                    del self._hmb_finish_remote_owners[next(iter(self._hmb_finish_remote_owners))]
                if request_id in self._seen_remote_requests:
                    if report_duplicate:
                        self._remote_status = {
                            "schema_version": 1,
                            "status": "duplicate",
                            "code": "duplicate_request",
                            "message": "Remote request was already applied.",
                            "request_id": request_id,
                            "revision": self._remote_revision,
                        }
                    else:
                        return
                else:
                    next_state, status = apply_finish_look_remote_request(
                        self._last_valid_state,
                        normalized_request,
                        current_revision=self._remote_revision,
                    )
                    self._remote_status = status
                    self._record_bounded(self._seen_remote_requests, request_id)
                    if status["status"] == "accepted":
                        self._last_valid_state = next_state
                        self._remote_revision = int(status["revision"])
                        self._restore_widget_parameter(live=True)
        except FinishLookValidationError as exc:
            with self._state_lock:
                self._remote_status = {
                    "schema_version": 1,
                    "status": "rejected",
                    "code": "invalid_request",
                    "message": str(exc),
                    "request_id": request_id,
                    "revision": self._remote_revision,
                }
        self._publish_all(live=True)

    def _hmb_apply_finish_remote_for(self, *, channel_uuid, shot_uuid, request):
        """Apply a canonical targeted patch without changing the visible editor."""
        with self._state_lock:
            self._hmb_finish_look_shot_snapshot_for(channel_uuid=channel_uuid, shot_uuid=shot_uuid)
            key = self._hmb_finish_key(channel_uuid, shot_uuid)
            if key == self._hmb_finish_active_key:
                self._apply_remote_value(request)
                return copy.deepcopy(self._remote_status)
            normalized = normalize_remote_request(request)
            document = copy.deepcopy(self._hmb_finish_documents.get(key) or {
                "finish_look": default_finish_look_state(), "remote_revision": 0, "seen_remote_requests": [],
                "remote_status": copy.deepcopy(DEFAULT_REMOTE_STATUS), "snapshot_generation": 0,
                "snapshot_fingerprint": "", "snapshot": {}})
            if normalized["request_id"] in document["seen_remote_requests"]:
                return {**copy.deepcopy(document["remote_status"]), "status": "duplicate", "code": "duplicate_request"}
            state, status = apply_finish_look_remote_request(document["finish_look"], normalized,
                current_revision=document["remote_revision"])
            document["remote_status"] = status
            self._record_bounded(document["seen_remote_requests"], normalized["request_id"])
            if status["status"] == "accepted":
                document["finish_look"] = state;document["remote_revision"] = int(status["revision"])
                document["snapshot_generation"] = max(1, int(document["snapshot_generation"]) + 1)
            self._hmb_finish_documents[key] = document
            previous_owner = self._hmb_finish_remote_owners.get(normalized["request_id"])
            self._hmb_finish_remote_owners[normalized["request_id"]] = key if previous_owner in {None,key} else "__multiple_original_targets__"
            self._hmb_finish_persist_store()
            return copy.deepcopy(status)

    @hmb_binding_mutation
    def after_value_set(self, parameter: Any, value: Any) -> Any:
        parent = getattr(super(), "after_value_set", None)
        result = parent(parameter, value) if callable(parent) else None
        if self._node_deleted:
            return result
        name = str(getattr(parameter, "name", "") or "")
        # A new explicit command may arrive while a previous UI reply is being
        # published. Suppress only our response mirrors, never a user's command.
        explicit_ui_command = isinstance(value, Mapping) and isinstance(value.get(UI_TRANSPORT_KEY), Mapping) and value[UI_TRANSPORT_KEY].get("operation") in {"refresh", "select", "edit"}
        if name == WIDGET_PARAMETER_NAME and (not self._syncing_widget or explicit_ui_command):
            self._apply_widget_value(value)
        elif name == REMOTE_INPUT_PARAMETER_NAME:
            self._apply_remote_value(value)
        elif name == SHOT_STORE_PARAMETER_NAME and not self._hmb_finish_store_syncing:
            self._hmb_finish_restore_store(value)
        return result

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        parent = getattr(super(), "after_incoming_connection", None)
        result = (
            parent(source_node, source_parameter, target_parameter)
            if callable(parent)
            else None
        )
        if str(getattr(target_parameter, "name", "") or "") == REMOTE_INPUT_PARAMETER_NAME:
            with self._state_lock:
                self._remote_connected = True
                self._restore_widget_parameter(live=True)
            self._publish_all(live=True)
        return result

    def after_incoming_connection_removed(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        parent = getattr(super(), "after_incoming_connection_removed", None)
        result = (
            parent(source_node, source_parameter, target_parameter)
            if callable(parent)
            else None
        )
        if str(getattr(target_parameter, "name", "") or "") == REMOTE_INPUT_PARAMETER_NAME:
            with self._state_lock:
                self._remote_connected = False
                self._restore_widget_parameter(live=True)
            self._publish_all(live=True)
        return result

    def before_value_set(self, parameter: Any, value: Any) -> Any:
        name = str(getattr(parameter, "name", "") or "")
        normalized = value
        if name == WIDGET_PARAMETER_NAME:
            try:
                normalized = validate_widget_state(value)
                raw = _mapping(value, "widget state")
                if UI_TRANSPORT_KEY in raw:
                    normalized[UI_TRANSPORT_KEY] = copy.deepcopy(raw[UI_TRANSPORT_KEY])
            except FinishLookValidationError as exc:
                with self._state_lock:
                    self._remote_status = {
                        "schema_version": 1,
                        "status": "rejected",
                        "code": "invalid_ui_state",
                        "message": str(exc),
                        "request_id": "",
                        "revision": self._remote_revision,
                    }
                    normalized = copy.deepcopy(self._widget_state)
        # Remote patch envelopes are deliberately validated in
        # the post-set handlers. This lets malformed input publish a rejected
        # status without throwing out of the host's value-set lifecycle.
        parent = getattr(super(), "before_value_set", None)
        if callable(parent):
            parent_value = parent(parameter, normalized)
            if parent_value is not None:
                normalized = parent_value
        return normalized

    @hmb_binding_mutation
    def set_parameter_value(self, name, value, *args, **kwargs):
        saved = kwargs.get("initial_setup") and not getattr(self, "_hmb_finish_store_syncing", False) and not getattr(self, "_syncing_widget", False)
        if saved:
            self._hmb_capture_saved_parameter_value(name, value)
        result = super().set_parameter_value(name, value, *args, **kwargs)
        if saved and name == SHOT_STORE_PARAMETER_NAME:
            self._hmb_finish_ensure_manager_state()
            self._hmb_finish_restore_store(getattr(self, "_hmb_finish_loaded_store_value", None) or value)
        elif saved and name == WIDGET_PARAMETER_NAME:
            # The SDK's official DeserializeFlow hydrates initial values without
            # calling a node-specific after_deserialize hook. Restore only
            # private authoring mirrors here; never publish, route or execute.
            self._hmb_finish_ensure_manager_state()
            normalized = validate_widget_state(value)
            self._widget_state = copy.deepcopy(normalized)
            shot = normalized["shot"]
            key = self._hmb_finish_key(shot["channel_uuid"], shot["shot_uuid"])
            if self._hmb_finish_loaded_store and key in self._hmb_finish_documents:
                self._hmb_finish_activate(key)
            else:
                self._last_valid_state = copy.deepcopy(normalized["finish_look"])
                self._hmb_finish_active_key = key
                self._hmb_finish_capture()
        if saved and name in {WIDGET_PARAMETER_NAME, SHOT_STORE_PARAMETER_NAME}:
            # Generated workflow builds replay properties with initial_setup
            # and do not call after_deserialize. Publish only the durable local
            # subscription's hydration signal; the live ImageAsset publisher
            # still has to validate and supply the remote catalog. Without this
            # signal the flow-wide authority barrier waits on Finish forever.
            try:
                from _hmb_shot_routing import schedule_post_hydration_reconcile

                schedule_post_hydration_reconcile(self)
            except Exception:
                pass
        return result

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        self._hmb_finish_ensure_manager_state()
        parent = getattr(super(), "after_deserialize", None)
        result = parent(*args, **kwargs) if callable(parent) else None
        self._repair_ui_contract()
        if self._hmb_finish_loaded_store:
            self._hmb_finish_restore_store(getattr(self, "_hmb_finish_loaded_store_value", None) or _raw_parameter(self, SHOT_STORE_PARAMETER_NAME))
        value = _raw_parameter(self, WIDGET_PARAMETER_NAME)
        persisted = value if isinstance(value, Mapping) else {}
        if not self._hmb_finish_loaded_store and isinstance(persisted.get("finish_look"), Mapping) and persisted["finish_look"].get("schema_version") == 1:
            self._hmb_finish_legacy_mode = True
            self._hmb_finish_legacy_widget = copy.deepcopy(dict(persisted))
        persisted_shot = persisted.get("shot") if isinstance(persisted, Mapping) else {}
        if isinstance(persisted_shot, Mapping) and persisted_shot.get("shot_uuid"):
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
        # Hydration starts a new host output epoch even when the saved Beauty
        # values match those last sent by this Python instance.
        with self._state_lock:
            self._hmb_finish_live_publication_owner = int(
                getattr(self, "_hmb_finish_live_publication_owner", 0) or 0
            ) + 1
            self._hmb_finish_live_values = {}
            self._hmb_finish_route_ready = False
            self._hmb_finish_snapshot_live_fingerprint = ""
        self._hmb_finish_hydrating = True
        try:
            self._apply_widget_value(value)
        finally:
            self._hmb_finish_hydrating = False
        try:
            from _hmb_shot_routing import schedule_post_hydration_reconcile

            schedule_post_hydration_reconcile(self)
        except Exception:
            pass
        return result

    def process(self) -> None:
        if self._node_deleted:
            return None
        remote_value = _raw_parameter(self, REMOTE_INPUT_PARAMETER_NAME)
        if remote_value:
            self._apply_remote_value(remote_value, report_duplicate=False)
        self._publish_all(live=False)
        LOGGER.info("[HMB][FINISH] FINISH_LOOK_OUT compiled.")
        return None

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        if self._delete_parent_called:
            return None
        self._node_deleted = True
        self._hmb_node_deleted = True
        self._hmb_finish_route_ready = False
        try:
            from _hmb_shot_routing import (
                prepare_node_deletion,
                release_node_lifecycle,
                schedule_post_deletion_reconcile,
            )

            prepare_node_deletion(self)
            release_node_lifecycle(self)
            schedule_post_deletion_reconcile(self)
        except Exception:
            pass
        self._delete_parent_called = True
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None


__all__ = [
    "DEFAULT_FINISH_LOOK_STATE",
    "EPSILON",
    "EXPECTED_DEFAULT_FINISH_LOOK_OUT",
    "FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA",
    "FINISH_LOOK_SHOT_SNAPSHOT_VERSION",
    "SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME",
    "HMBFinishLookLibrary",
    "apply_finish_look_remote_request",
    "compile_beauty_glow_prompt",
    "compile_beauty_prompt",
    "compile_finish_look_prompt",
    "default_finish_look_state",
    "default_widget_state",
    "format_number",
    "is_zero",
    "join_sentences",
    "normalize_remote_request",
    "parse_finish_look_state",
    "validate_finish_look_state",
    "validate_widget_state",
]
