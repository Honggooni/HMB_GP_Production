from __future__ import annotations

from pathlib import Path
import hashlib
import importlib.util
import json
import logging
import re
import sys
import threading
from typing import Any, Dict, List

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _load_hmb_common():
    module_path = _THIS_DIR / "_hmb_common.py"
    module_key = f"{module_path.resolve()}:{module_path.stat().st_mtime_ns}"
    module_name = "_hmb_gp_production_common_" + hashlib.sha1(module_key.encode("utf-8")).hexdigest()[:12]
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
parameter_exists = getattr(_hmb, "parameter_exists", lambda node, name: name in getattr(node, "parameters", {}))
_LOGGER = logging.getLogger("griptape_nodes")
_DIAGNOSTIC_PREFIX = "[HMB_GP_Production][HMBPromptLibrary]"


def _diagnostic(message: str) -> None:
    try:
        _LOGGER.info("%s %s", _DIAGNOSTIC_PREFIX, message)
    except Exception:
        return


def _diagnostic_exception(context: str, exc: BaseException) -> None:
    try:
        _LOGGER.exception("%s %s: %s", _DIAGNOSTIC_PREFIX, context, exc)
    except Exception:
        return


try:
    from griptape_nodes.traits.widget import Widget  # type: ignore
except Exception:
    Widget = None  # type: ignore


MAX_IMAGES = 50
MAX_VIDEOS = 10
PROMPT_POLICY_SOURCE_VERSION = "2026-08-06.animation-look-continuity.v3"
PROMPT_POLICY_SOURCE_CONTRACT_SHA256 = (
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
)
PICKER_DEPTH_PROFILE = "hmb_camera_space_depth_v7"
PICKER_MOTION_GUIDE_PROFILE = "hmb_target_neutral_motion_guide_v5"
PICKER_LEGACY_MOTION_GUIDE_PROFILES = frozenset({
    "hmb_target_neutral_motion_guide_v4",
})
PICKER_MOTION_GUIDE_PROFILES = frozenset({
    PICKER_MOTION_GUIDE_PROFILE,
})
MAX_COLOR_PICKS = 3
MAX_IDENTIFIER_CHARS = 256
MAX_DESCRIPTION_CHARS = 6000
MAX_VIDEO_VFX_CHARS = 20000
MAX_KEEP_OUT_CHARS = 4000
MAX_PROMPT_CHARS = 55000
MAX_FRAME_RANGES_PER_BINDING = 100
MAX_MANUAL_FRAME_NUMBER = 9999
_OPTIONAL_PROMPT_SECTION_PRIORITY = (
    "SOURCE INTERPRETATION NOTES:",
    "SELF-SCOPED REFERENCE ALIGNMENT:",
    "ADDITIVE MULTI-VIDEO BINDING SCHEMA:",
    "SOURCE DATA WARNINGS:",
)
IMAGE_SOURCE_TYPE_CHOICES = _hmb.IMAGE_SOURCE_TYPE_CHOICES
IMAGE_SCOPE_CHOICES = _hmb.IMAGE_SCOPE_CHOICES
IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE = _hmb.IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE
IMAGE_SYSTEM_TARGETS = _hmb.IMAGE_SYSTEM_TARGETS
IMAGE_OWNER_CHOICES = _hmb.IMAGE_OWNER_CHOICES
ACTOR_COLOR_PICK_CHOICES = _hmb.ACTOR_COLOR_PICK_CHOICES
OBJECT_COLOR_PICK_CHOICES = _hmb.OBJECT_COLOR_PICK_CHOICES
COLOR_PICK_CHOICES = _hmb.COLOR_PICK_CHOICES
ACTOR_COLOR_PICK_SOURCE_TYPES = _hmb.ACTOR_COLOR_PICK_SOURCE_TYPES
OBJECT_COLOR_PICK_SOURCE_TYPES = _hmb.OBJECT_COLOR_PICK_SOURCE_TYPES
image_scope_choices_for_source_type = _hmb.image_scope_choices_for_source_type
image_color_pick_choices_for_source_type = _hmb.image_color_pick_choices_for_source_type
WIDGET_PARAMETER_NAME = "HMB_UI_STATE"
PICKER_INPUT_PARAMETER_NAME = "PICKER_IN"
IMAGE_ASSET_INPUT_PARAMETER_NAME = "IMAGE_ASSET_IN"
IMAGE_ASSET_INPUT_DISPLAY_NAME = "ASSET_IN"
WIDGET_NAME = "HMBPromptLibraryScopedBindingWidget"
WIDGET_LIBRARY_NAME = "HMB_GP_Production"
STATE_SCHEMA = "prompt-library-state"
MODE_NAME = "prompt_only_role_dashboard"
UI_RESIZE_MODE = "stacked_outer_1000"
GROUP_START_HEIGHTS = {
    "imageSources": 500,
    "imageText": 200,
    "videoSources": 200,
    "videoText": 150,
}
GROUP_MIN_HEIGHTS = GROUP_START_HEIGHTS
GROUP_START_TOTAL_HEIGHT = sum(GROUP_START_HEIGHTS.values())
PROMPT_DASHBOARD_FIXED_HEIGHT = 101
# IMAGE_ASSET_IN adds one native connector row above the custom dashboard.
# Reserve the measured native-row height so the existing dashboard area is not
# clipped at the bottom when a Prompt node is first created.
PROMPT_NATIVE_ASSET_INPUT_ROW_HEIGHT = 42
PROMPT_START_HEIGHT = (
    GROUP_START_TOTAL_HEIGHT
    + PROMPT_DASHBOARD_FIXED_HEIGHT
    + PROMPT_NATIVE_ASSET_INPUT_ROW_HEIGHT
)
PROMPT_MIN_HEIGHT = PROMPT_START_HEIGHT
GROUP_MAX_HEIGHT = 6000
KEEP_OUT_TEXTAREA_MIN_HEIGHT = 34
KEEP_OUT_TEXTAREA_MAX_HEIGHT = 1200

# Target is the dashboard's compact relationship field. Saved/custom Targets
# and additional relationship Targets remain ordinary user intent; suggestions
# never limit how the current goal may use them.
VIDEO_SOURCE_TYPE_CHOICES = [
    "Role Required / Select Video Type",
    "Ignore / Unused",
    "Maya Preview / Playblast",
    "Unified Shot-Control Video",
    "Motion Reference",
    "Camera / Layout Reference",
    "Depth / Spatial Reference",
    "Motion Guide / Retargeting Reference",
    "FX Reference",
    "Timing / Edit Reference",
    "Lighting / Look Reference",
    "Simulation Reference",
    "Mask / Control Reference",
    "Custom",
]

VIDEO_CONTROL_ROLE_CHOICES = [
    "",
    "Primary Unified Shot Control",
    "Timing Only",
    "Local Motion Detail Only",
    "Secondary Motion Only",
    "Spatial Alignment Verification Only",
    "Derived Motion Decoding Only",
    "FX Behavior Only",
    "Lighting / Look Only",
    "Local Composition Check Only",
    "Mask / Guide Only",
    "Context Only",
    "Custom Role",
]

VIDEO_ROLE_COMPATIBILITY = {
    "Maya Preview / Playblast": {
        "Primary Unified Shot Control", "Local Motion Detail Only", "Secondary Motion Only",
        "Spatial Alignment Verification Only", "Timing Only", "Mask / Guide Only", "Context Only",
    },
    "Unified Shot-Control Video": {"Primary Unified Shot Control"},
    "Motion Reference": {"Local Motion Detail Only", "Secondary Motion Only", "Context Only"},
    "Camera / Layout Reference": {"Spatial Alignment Verification Only", "Local Composition Check Only", "Context Only"},
    "Depth / Spatial Reference": {"Spatial Alignment Verification Only", "Mask / Guide Only", "Context Only"},
    "Motion Guide / Retargeting Reference": {"Derived Motion Decoding Only"},
    "FX Reference": {"FX Behavior Only", "Timing Only", "Context Only"},
    "Timing / Edit Reference": {"Timing Only", "Context Only"},
    "Lighting / Look Reference": {"Lighting / Look Only", "Context Only"},
    "Simulation Reference": {"Secondary Motion Only", "FX Behavior Only", "Context Only"},
    "Mask / Control Reference": {"Mask / Guide Only", "Context Only"},
    "Custom": {"Custom Role", "Context Only"},
}

SELF_SCOPED_AUXILIARY_REFERENCE_SPECS = {
    ("Maya Preview / Playblast", "Spatial Alignment Verification Only"): {
        "authority_domain": "playblast_spatial_verification",
        "fields": "protected animator-authored acting, motion, pose, timing, trajectory, contact, camera, framing, visibility, occlusion, relative depth, and spatial arrangement; the selected role emphasizes spatial verification without narrowing that shot state",
        "time_mapping": "source-local timing as supplied; cross-source alignment applies only to an explicitly declared Picker companion bundle",
        "authority": "the role label is an interpretation emphasis, not a cross-attribute override; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
    },
    ("Camera / Layout Reference", "Spatial Alignment Verification Only"): {
        "authority_domain": "camera_layout_verification",
        "fields": "default interpretation: camera, layout, framing, composition, screen position, and spatial alignment",
        "time_mapping": "source-local timing as supplied; cross-source alignment applies only to an explicitly declared Picker companion bundle",
        "authority": "default camera/layout-verification interpretation; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
    },
    ("Depth / Spatial Reference", "Spatial Alignment Verification Only"): {
        "authority_domain": "depth_spatial_verification",
        "fields": "default interpretation: relative depth, occlusion, and spatial ordering",
        "time_mapping": "source-local timing as supplied; cross-source alignment applies only to an explicitly declared Picker companion bundle",
        "authority": "default depth/spatial interpretation; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
    },
    ("Motion Guide / Retargeting Reference", "Derived Motion Decoding Only"): {
        "authority_domain": "derived_motion_decoding",
        "fields": "default interpretation: target-neutral root, joint, contact, trajectory, and rigid-transform decoding of supplied source motion",
        "time_mapping": "source-local timing as supplied; exact bundle correspondence applies only when Picker provenance explicitly declares a companion source",
        "authority": "default motion-decoding/retargeting interpretation; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
    },
    ("Maya Preview / Playblast", "Timing Only"): {
        "authority_domain": "playblast_timing_verification",
        "fields": "protected animator-authored acting, motion, pose, timing, trajectory, contact, camera, framing, visibility, occlusion, relative depth, and spatial arrangement; the selected role emphasizes timing verification without narrowing that shot state",
        "time_mapping": "source-local timing as supplied; cross-source alignment applies only to an explicitly declared Picker companion bundle",
        "authority": "the role label is an interpretation emphasis, not a cross-attribute override; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
    },
    ("Timing / Edit Reference", "Timing Only"): {
        "authority_domain": "timing_edit_verification",
        "fields": "default interpretation: full-shot edit cadence, cut position, source-time alignment, and timing cues",
        "time_mapping": "source-local timing as supplied; cross-source alignment applies only to an explicitly declared Picker companion bundle",
        "authority": "default timing/edit interpretation; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
    },
    ("Lighting / Look Reference", "Lighting / Look Only"): {
        "authority_domain": "integration_lighting_look_reference",
        "fields": "default interpretation: full-shot integration lighting and atmosphere consistency",
        "time_mapping": "source-local timing as supplied; cross-source alignment applies only to an explicitly declared Picker companion bundle",
        "authority": "default lighting/look-reference interpretation; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
    },
}

TEXT_FIELD_NAMES = [
    "PROJECT_STYLE_LOOK",
    "SCENE_CONTEXT",
    "EMOTION_INTENT",
    "VIDEO_VFX",
    "PRESERVED_TEXT",
]
TEXT_FIELD_DEFAULTS = {name: "" for name in TEXT_FIELD_NAMES}


PRESERVED_TEXT_TYPES = {
    "Proper Noun",
    "Dialogue",
    "Lip-sync Speech",
    "Lyrics",
    "Chant",
    "On-screen Text",
}
_PRESERVED_TEXT_LINE_RE = re.compile(r"^\s*\[([^]\r\n]+)\]\s*(.+?)\s*$")

def _parse_preserved_text(value: Any) -> tuple[List[Dict[str, str]], List[str]]:
    entries: List[Dict[str, str]] = []
    errors: List[str] = []
    seen: set[tuple[str, str]] = set()
    for line_number, raw_line in enumerate(str(value or "").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        match = _PRESERVED_TEXT_LINE_RE.match(line)
        if not match:
            errors.append(f"PRESERVED_TEXT line {line_number} must use [Type] exact text.")
            continue
        item_type = match.group(1).strip()
        literal = match.group(2).strip()
        if item_type not in PRESERVED_TEXT_TYPES:
            errors.append(f"PRESERVED_TEXT line {line_number} uses unsupported type: {item_type}.")
            continue
        if not literal:
            errors.append(f"PRESERVED_TEXT line {line_number} has no exact text.")
            continue
        key=(item_type,literal)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"type": item_type, "value": literal})
    return entries, errors


def _unverified_preserved_text_lines(value: Any) -> List[str]:
    """Keep malformed exact-text rows as ordinary descriptive user intent.

    A malformed or unknown tag cannot receive exact-literal authority, but that
    technical limitation must never erase the words the user supplied.
    """
    out: List[str] = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _PRESERVED_TEXT_LINE_RE.match(line)
        if not match:
            out.append(line)
            continue
        item_type = match.group(1).strip()
        literal = match.group(2).strip()
        if item_type not in PRESERVED_TEXT_TYPES or not literal:
            out.append(line)
    return list(dict.fromkeys(out))

VIDEO_ROLE_ALIASES = {
    "Strongest Unified Shot-Control": "Primary Unified Shot Control",
    "Motion Only": "Local Motion Detail Only",
    "Camera / Layout / Depth Only": "Spatial Alignment Verification Only",
    "Composition Reference Only": "Local Composition Check Only",
}
# Compatibility export retained for saved states and downstream integrations.
# Prompt no longer assigns special authority to a slot number: every declared
# video type may be used independently in any visible slot.
PRIMARY_VIDEO_SOURCE_TYPES = {
    value
    for value in VIDEO_SOURCE_TYPE_CHOICES
    if value not in {"", "Role Required / Select Video Type", "Ignore / Unused"}
}

def _canonical_video_role(value: Any) -> str:
    role = _clean_string(value) if "_clean_string" in globals() else str(value or "").strip()
    return VIDEO_ROLE_ALIASES.get(role, role)


def _mode_output():
    if ParameterMode is None:
        return None
    return {ParameterMode.OUTPUT}


def _mode_property():
    if ParameterMode is None:
        return None
    return {ParameterMode.PROPERTY}


def _parameter_attempts(kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
    modern = dict(kwargs)
    if modern.get("allowed_modes") is not None:
        for key in ("allow_input", "allow_output", "allow_property"):
            modern.pop(key, None)

    legacy = dict(kwargs)
    legacy.pop("allowed_modes", None)

    attempts: List[Dict[str, Any]] = []
    for candidate in (modern, legacy):
        attempts.append(candidate)
        no_type = dict(candidate)
        no_type.pop("type", None)
        if no_type != candidate:
            attempts.append(no_type)
    return attempts


def _safe_add_parameter(node: Any, **kwargs: Any) -> None:
    last: Exception | None = None
    for attempt in _parameter_attempts(dict(kwargs)):
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
            obj = getter(name)
            if obj is not None:
                return obj
    except Exception as exc:
        _diagnostic_exception(f"Parameter lookup failed for {name}", exc)
    return getattr(node, "parameters", {}).get(name)


def _get_parameter_raw(node: Any, name: str) -> Any:
    try:
        return node.get_parameter_value(name)
    except Exception:
        parameter = _get_parameter_obj(node, name)
        return getattr(parameter, "default_value", None)


def _set_parameter_value(node: Any, name: str, value: Any) -> None:
    try:
        setter = getattr(node, "set_parameter_value", None)
        if callable(setter):
            setter(name, value)
            return
    except Exception as exc:
        _diagnostic_exception(f"Runtime parameter write failed for {name}; using compatibility fallback", exc)
    parameter = _get_parameter_obj(node, name)
    if parameter is None:
        return
    for attr in ("default_value", "value"):
        try:
            setattr(parameter, attr, value)
        except Exception as exc:
            _diagnostic_exception(f"Compatibility parameter write failed for {name}.{attr}", exc)


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _video_file_stem(value: Any) -> str:
    """Return only a video's file name without its path or final extension."""
    text = _clean_string(value)
    if not text:
        return ""
    clean_path = text.split("?", 1)[0].split("#", 1)[0].replace("\\", "/").rstrip("/")
    filename = clean_path.rsplit("/", 1)[-1]
    if not filename:
        return text
    stem = Path(filename).stem
    return stem or filename


def _color_pick_choices_for_source_type(source_type: Any) -> List[str]:
    return image_color_pick_choices_for_source_type(source_type)


def _merge_unique_notes(*values: Any) -> str:
    parts: List[str] = []
    for value in values:
        cleaned = _clean_string(value)
        if not cleaned:
            continue
        for line in cleaned.splitlines():
            note = _clean_string(line)
            if note and note not in parts:
                parts.append(note)
    return "\n".join(parts)


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


_UNSTRUCTURED_INPUT_KEY = "__hmb_unstructured_input__"
_SOURCE_INTENT_FALLBACKS_KEY = "source_intent_fallbacks"
_IMAGE_ASSET_PAYLOAD_KEYS = frozenset({
    "schema",
    "version",
    "mode",
    "project_id",
    "project_uid",
    "project_root",
    "selection_id",
    "ordered_images",
    "verified_assets",
    "selected_assets",
    "imported_images",
    "assets",
    "authority",
    # HMBImageAssetLibrary publishes these diagnostics alongside the resolved
    # ordered_images list.  They are transport metadata, not prompt intent.
    "media_resolution",
    "warnings",
})
_IMAGE_ASSET_IDENTITY_KEYS = frozenset({
    "project_id",
    "project_uid",
    "project_root",
    "selection_id",
    "ordered_images",
    "verified_assets",
    "selected_assets",
    "imported_images",
    "assets",
})
_IMAGE_ASSET_ROW_KEYS = frozenset({
    "selected",
    "verified_asset",
    "binding_mode",
    "order_key",
    "source_uid",
    "source_kind",
    "asset_library_id",
    "asset_key",
    "asset_id",
    "image_name",
    "label",
    "path",
    "asset_path",
    "project_uid",
    "source_type",
    "custom_source_type",
    "scope_candidate",
    "scope",
    "sub_type",
    "color_pick_candidates",
    "selection_order",
    "slot",
})
_PICKER_PAYLOAD_KEYS = frozenset({
    "schema",
    "schema_version",
    "mode",
    "run_id",
    "scene_path",
    "scene_fingerprint",
    "marker_catalog_version",
    "media_ready",
    "active_slot_count",
    "selected_video_count",
    "max_selected_videos",
    "selection_id",
    "ordered_video_uids",
    "catalog_video_count",
    "warnings",
    "videos",
    "video",
    "video_path",
    "video_slot",
    "camera",
    "markers",
    "frame_metadata",
    "frame_metadata_schema_version",
})
_PICKER_IDENTITY_KEYS = frozenset({
    "run_id",
    "scene_path",
    "scene_fingerprint",
    "media_ready",
    "active_slot_count",
    "selected_video_count",
    "max_selected_videos",
    "selection_id",
    "ordered_video_uids",
    "videos",
    "video",
    "video_path",
    "video_slot",
    "camera",
    "markers",
    "frame_metadata",
})
_PICKER_VIDEO_ROW_KEYS = frozenset({
    "video_uid",
    "source_uid",
    "selection_order",
    "order_key",
    "selected",
    "video_slot",
    "video_path",
    "local_video_path",
    "project_video_path",
    "camera",
    "markers",
    "fps",
    "start_frame",
    "end_frame",
    "frame_count",
    "duration_seconds",
    "timebase",
    "width",
    "height",
    "resolution",
    "available_color_picks",
    "frame_metadata",
    "run_id",
    "pair_run_id",
    "bundle_run_id",
    "media_kind",
    "generation_role",
    "video_role",
    "label",
    "source_type_hint",
    "control_role_hint",
    "depth_profile",
    "motion_guide_profile",
    "companion_of_video_slot",
    "source_video_slot",
    "companion_of_video_uid",
    "source_video_uid",
    "companion_video_uid",
    "depth_range_report",
    "motion_guide_report",
    "conflict",
    "valid",
    "warnings",
})
_PICKER_MARKER_CONSUMED_KEYS = frozenset({
    "color",
    "asset_id",
    "subject_root",
    "video_slot",
    "video_uid",
    "source_uid",
    "selection_order",
    "order_key",
    "picker_order",
})
_PICKER_FRAME_METADATA_KEYS = frozenset({
    "video_slot",
    "video_uid",
    "source_uid",
    "selection_order",
    "order_key",
    "fps",
    "start_frame",
    "end_frame",
    "frame_count",
    "duration_seconds",
    "timebase",
    "width",
    "height",
    "resolution",
    "available_color_picks",
    "conflict",
    "valid",
    "warnings",
})


def _readable_original(value: Any) -> str:
    """Return a stable readable representation without inventing structure."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        try:
            return str(value).strip()
        except Exception:
            return ""


def _source_intent_entry(source: Any, reason: Any, value: Any) -> Dict[str, str] | None:
    text = _readable_original(value)
    if not text:
        return None
    return {
        "source": _clean_string(source) or "CONNECTED_SOURCE",
        "reason": _clean_string(reason) or "readable unstructured input",
        "text": text,
    }


def _normalize_source_intent_fallbacks(value: Any) -> List[Dict[str, str]]:
    raw_entries = value if isinstance(value, (list, tuple)) else [value]
    out: List[Dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_entries:
        if isinstance(raw, dict):
            entry = _source_intent_entry(
                raw.get("source"),
                raw.get("reason"),
                raw.get("text"),
            )
        else:
            entry = _source_intent_entry("CONNECTED_SOURCE", "readable unstructured input", raw)
        if entry is None:
            continue
        signature = (entry["source"], entry["reason"], entry["text"])
        if signature in seen:
            continue
        seen.add(signature)
        out.append(entry)
    return out


def _append_source_intent(
    state: Dict[str, Any],
    source: Any,
    reason: Any,
    value: Any,
) -> None:
    entries = _normalize_source_intent_fallbacks(
        state.get(_SOURCE_INTENT_FALLBACKS_KEY)
    )
    entry = _source_intent_entry(source, reason, value)
    if entry is not None:
        entries = _normalize_source_intent_fallbacks([*entries, entry])
    state[_SOURCE_INTENT_FALLBACKS_KEY] = entries


def _append_unconsumed_connected_fields(
    state: Dict[str, Any],
    source: str,
    payload: Dict[str, Any],
    consumed_keys: frozenset[str],
) -> None:
    """Preserve every readable field that a known HMB schema does not consume."""

    extras = {
        key: value
        for key, value in payload.items()
        if key not in consumed_keys and key != _UNSTRUCTURED_INPUT_KEY
    }
    if extras:
        _append_source_intent(
            state,
            source,
            "additional connected fields retained as ordinary user intent",
            extras,
        )


def _append_unconsumed_connected_rows(
    state: Dict[str, Any],
    source: str,
    rows: Any,
    consumed_keys: frozenset[str],
    row_label: str,
    limit: int,
) -> None:
    """Preserve readable extension fields nested inside structured rows."""

    if not isinstance(rows, (list, tuple)):
        return
    for index, row in enumerate(rows[: max(0, int(limit))], start=1):
        if not isinstance(row, dict):
            continue
        extras = {
            key: value
            for key, value in row.items()
            if key not in consumed_keys
        }
        if extras:
            _append_source_intent(
                state,
                source,
                f"{row_label} {index} additional fields retained as ordinary user intent",
                extras,
            )


def _unstructured_payload_entries(payload: Any) -> List[Dict[str, str]]:
    if not isinstance(payload, dict):
        return []
    return _normalize_source_intent_fallbacks(payload.get(_UNSTRUCTURED_INPUT_KEY))


def _parse_state(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value) if value.strip() else {}
            if isinstance(parsed, dict):
                return parsed
            entry = _source_intent_entry(
                WIDGET_PARAMETER_NAME,
                "readable non-object dashboard state",
                parsed,
            )
            return {_SOURCE_INTENT_FALLBACKS_KEY: [entry] if entry else []}
        except Exception:
            entry = _source_intent_entry(
                WIDGET_PARAMETER_NAME,
                "readable non-JSON dashboard state",
                value,
            )
            return {_SOURCE_INTENT_FALLBACKS_KEY: [entry] if entry else []}
    entry = _source_intent_entry(
        WIDGET_PARAMETER_NAME,
        "readable non-object dashboard state",
        value,
    )
    return {_SOURCE_INTENT_FALLBACKS_KEY: [entry] if entry else []}


def _slot_name(prefix: str, index: int) -> str:
    return f"{prefix}_{index:02d}"


def _image_taxonomy_payload() -> Dict[str, Any]:
    return {
        "source_type_choices": list(IMAGE_SOURCE_TYPE_CHOICES),
        "scope_choices": list(IMAGE_SCOPE_CHOICES),
        "scope_choices_by_source_type": {
            key: list(values)
            for key, values in IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE.items()
        },
        "actor_color_pick_choices": list(ACTOR_COLOR_PICK_CHOICES),
        "object_color_pick_choices": list(OBJECT_COLOR_PICK_CHOICES),
        "actor_color_pick_source_types": sorted(ACTOR_COLOR_PICK_SOURCE_TYPES),
        "object_color_pick_source_types": sorted(OBJECT_COLOR_PICK_SOURCE_TYPES),
    }


def _default_image_item(slot: int) -> Dict[str, Any]:
    return {
        "slot": slot,
        "token": f"@image{slot}",
        "name": _slot_name("IMAGE", slot),
        "present": False,
        "label": "",
        "asset_id": "",
        "asset_path": "",
        "asset_library_id": "",
        "asset_source_uid": "",
        "asset_project_uid": "",
        "asset_selection_order": 0,
        "asset_source_type_candidate": "",
        "asset_scope_candidate": "",
        "asset_color_pick_candidates": [],
        "asset_default_target": "",
        "asset_managed": False,
        "asset_verified": False,
        "asset_source_kind": "",
        "source_type": "Role Required / Select Source Type",
        "custom_source_type": "",
        "owner": "",
        "legacy_relationship_targets": [],
        "scope": "",
        "binding_scopes": [""],
        "binding_custom_scopes": [""],
        "binding_video_slots": [1],
        "color_picks": [""],
        "marker_video": 1,
        "preview_marker": "",
        "picker_auto_color": "",
        "picker_auto_video": 0,
        "picker_auto_source": "",
        "frame_range_enabled": False,
        "frame_range_color_index": 0,
        "frame_range_bindings": {},
        "frame_range_binding": None,
        "frame_range_selected_index": -1,
        "manual": True,
        "source_type_choices": IMAGE_SOURCE_TYPE_CHOICES,
        "owner_choices": IMAGE_OWNER_CHOICES,
        "scope_choices": IMAGE_SCOPE_CHOICES,
    }


def _default_video_item(slot: int) -> Dict[str, Any]:
    return {
        "slot": slot,
        "token": f"@video{slot}",
        "name": _slot_name("VIDEO", slot),
        # ``video_uid`` is the durable Picker-library identity. ``slot`` and
        # ``token`` are deliberately transient generator addresses derived
        # from the current selection order.
        "video_uid": "",
        "source_uid": "",
        "selection_order": 0,
        "order_key": "",
        "picker_managed": False,
        "present": False,
        "label": "",
        "source_type": "Role Required / Select Video Type",
        "custom_source_type": "",
        "control_role": "",
        "custom_control_role": "",
        "keep_out": "",
        "picker_auto_label": "",
        "picker_auto_depth": {},
        "picker_auto_motion_guide": {},
        "picker_motion_guide_summary": {},
        # Stable companion provenance.  These fields describe the Picker
        # relationship; ``slot`` remains only the current transient address.
        "picker_companion_kind": "",
        "picker_companion_source_slot": -1,
        "picker_companion_source_uid": "",
        "picker_companion_validated": False,
        "manual": slot == 1,
        "source_type_choices": VIDEO_SOURCE_TYPE_CHOICES,
        "control_role_choices": VIDEO_CONTROL_ROLE_CHOICES,
    }


def _default_widget_state() -> Dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "mode": MODE_NAME,
        "image_taxonomy": _image_taxonomy_payload(),
        "images": [_default_image_item(slot) for slot in range(1, 5)],
        "videos": [_default_video_item(1)],
        "text": dict(TEXT_FIELD_DEFAULTS),
        _SOURCE_INTENT_FALLBACKS_KEY: [],
        "ui": {
            "group_heights": {},
            "textarea_heights": {},
            "resize_mode": UI_RESIZE_MODE,
            "language": "en",
            "theme": "P",
        },
        "picker": {
            "enabled": False,
            "awaiting_data": False,
            "run_id": "",
            "selection_id": "",
            "selected_video_count": 0,
            "ordered_video_uids": [],
            "order_managed": False,
            "dormant_video_rows": [],
            "dormant_manual_rows": [],
            "slot_suppressions": {},
            "scene": "",
            "video_path": "",
            "camera": "",
            "markers": [],
            "frame_metadata": [],
            "matched_images": 0,
        },
        "image_asset": {
            "enabled": False,
            "project_id": "",
            "project_uid": "",
            "project_root": "",
            "selection_id": "",
            "selected_assets": 0,
            "verified_assets": 0,
            "imported_images": 0,
            "ordered_source_uids": [],
            "order_managed": False,
            # IMAGE_ASSET_IN temporarily owns the visible @image slots.  Keep
            # native rows outside that slot namespace so they can return
            # byte-for-byte (apart from slot numbering) when the edge is
            # removed.  Upstream-owned rows use a separate source_uid cache so
            # deselect/reselect restores Target, Role, Color Pick, and Range.
            "dormant_manual_rows": [],
            "dormant_asset_rows": [],
        },
        "status": {
            "active_images": 0,
            "active_videos": 0,
            "visible_image_slots": 4,
            "visible_video_slots": 1,
            "max_images": MAX_IMAGES,
            "max_videos": MAX_VIDEOS,
        },
    }


def _normalize_color_picks(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = []
        for item in value[:MAX_COLOR_PICKS]:
            if isinstance(item, dict):
                raw.append(item.get("color") or item.get("value") or item.get("name") or "")
            else:
                raw.append(item)
    elif isinstance(value, str):
        raw = re.split(r"[,+/]", value)[:MAX_COLOR_PICKS]
    else:
        raw = []
    out: List[str] = []
    for item in raw:
        color = _clean_string(item)
        # Known colors drive the standard picker UI, but a readable custom
        # marker is still user intent and remains directly usable.
        out.append(color)
    if not out:
        out.append("")
    return out[:MAX_COLOR_PICKS]


def _normalize_binding_scopes(value: Any, fallback_scope: Any = "", count: int = 1) -> List[str]:
    if isinstance(value, list):
        raw = list(value[:MAX_COLOR_PICKS])
    elif isinstance(value, tuple):
        raw = list(value[:MAX_COLOR_PICKS])
    elif isinstance(value, str) and value.strip():
        raw = [value]
    else:
        raw = []

    fallback = _clean_string(fallback_scope)
    target_count = max(1, min(MAX_COLOR_PICKS, int(count or len(raw) or 1)))
    if not raw and fallback:
        raw = [fallback]

    out: List[str] = []
    for item in raw[:target_count]:
        scope = _clean_string(item)
        out.append(scope)
    while len(out) < target_count:
        out.append("")
    return out[:MAX_COLOR_PICKS]


def _normalize_parallel_text_list(value: Any, count: int, max_count: int) -> List[str]:
    if isinstance(value, list):
        raw = list(value[:max_count])
    elif isinstance(value, tuple):
        raw = list(value[:max_count])
    elif isinstance(value, str) and value.strip():
        raw = [value]
    else:
        raw = []
    target_count = max(1, min(max_count, int(count or len(raw) or 1)))
    out = [_clean_string(item) for item in raw[:target_count]]
    while len(out) < target_count:
        out.append("")
    return out[:max_count]


def _normalize_binding_video_slots(value: Any, fallback: Any, count: int, video_count: int = MAX_VIDEOS) -> List[int]:
    if isinstance(value, list):
        raw = list(value[:MAX_COLOR_PICKS])
    elif isinstance(value, tuple):
        raw = list(value[:MAX_COLOR_PICKS])
    elif value not in (None, ""):
        raw = [value]
    else:
        raw = []
    target_count = max(1, min(MAX_COLOR_PICKS, int(count or len(raw) or 1)))
    fallback_slot = _normalize_marker_video(fallback, video_count)
    out = [_normalize_marker_video(item, video_count) for item in raw[:target_count]]
    while len(out) < target_count:
        out.append(out[-1] if out else fallback_slot)
    return out[:MAX_COLOR_PICKS]


def _video_slot_number(value: Any, video_count: int = MAX_VIDEOS) -> int:
    text = _clean_string(value)
    match = re.search(r"(?:@?video)?\s*(\d+)", text, re.IGNORECASE)
    return _normalize_marker_video(match.group(1) if match else value, video_count)


def _frame_binding_key(video_slot: Any, color_pick: Any) -> str:
    slot = _video_slot_number(video_slot, MAX_VIDEOS)
    color = _clean_string(color_pick)
    return f"@video{slot}::{color}"


def _normalize_frame_ranges(value: Any) -> List[Dict[str, int]]:
    raw_ranges = value if isinstance(value, list) else []
    ranges: List[Dict[str, int]] = []
    for raw in raw_ranges[:MAX_FRAME_RANGES_PER_BINDING]:
        if not isinstance(raw, dict):
            continue
        try:
            start = int(round(float(raw.get("start"))))
            end = int(round(float(raw.get("end"))))
        except Exception:
            continue
        ranges.append({"start": start, "end": end})
    ranges.sort(key=lambda item: (item["start"], item["end"]))

    merged: List[Dict[str, int]] = []
    for current in ranges:
        if current["start"] > current["end"]:
            merged.append(current)
            continue
        if (
            merged
            and merged[-1]["start"] <= merged[-1]["end"]
            and current["start"] <= merged[-1]["end"] + 1
        ):
            merged[-1]["end"] = max(merged[-1]["end"], current["end"])
        else:
            merged.append(dict(current))
    return merged[:MAX_FRAME_RANGES_PER_BINDING]


def _optional_frame_number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(0, min(MAX_MANUAL_FRAME_NUMBER, int(round(float(value)))))
    except Exception:
        return None


def _normalize_frame_range_bindings(value: Any, legacy_binding: Any = None) -> Dict[str, Dict[str, Any]]:
    raw_map = value if isinstance(value, dict) else {}
    candidates: List[tuple[Any, Any]] = []
    if isinstance(legacy_binding, dict):
        candidates.append(("", legacy_binding))
    candidates.extend(raw_map.items())
    out: Dict[str, Dict[str, Any]] = {}
    for raw_key, raw in candidates:
        if not isinstance(raw, dict):
            continue
        slot = _video_slot_number(
            raw.get("video_slot")
            or raw.get("video")
            or str(raw_key).split("::", 1)[0],
            MAX_VIDEOS,
        )
        color = _clean_string(
            raw.get("color_pick")
            or raw.get("color")
            or (
                str(raw_key).split("::", 1)[1]
                if "::" in str(raw_key)
                else ""
            )
        )
        key = _frame_binding_key(slot, color)
        previous = out.get(key) if isinstance(out.get(key), dict) else {}
        has_start = "start_frame" in raw or "manual_start_frame" in raw
        has_end = "end_frame" in raw or "manual_end_frame" in raw
        out[key] = {
            "video_slot": f"@video{slot}",
            "color_pick": color,
            "origin": _clean_string(raw.get("origin")) or "manual",
            "start_frame": (
                _optional_frame_number(
                    raw.get("start_frame")
                    if "start_frame" in raw
                    else raw.get("manual_start_frame")
                )
                if has_start
                else _optional_frame_number(previous.get("start_frame"))
            ),
            "end_frame": (
                _optional_frame_number(
                    raw.get("end_frame")
                    if "end_frame" in raw
                    else raw.get("manual_end_frame")
                )
                if has_end
                else _optional_frame_number(previous.get("end_frame"))
            ),
            "ranges": _normalize_frame_ranges(raw.get("ranges")),
        }
    return out


def _release_picker_auto_frame_binding(
    item: Dict[str, Any], video_slot: Any, color_pick: Any
) -> bool:
    """Release a Picker-authored range while retaining every manual range."""
    bindings = _normalize_frame_range_bindings(
        item.get("frame_range_bindings"),
        item.get("frame_range_binding"),
    )
    key = _frame_binding_key(video_slot, color_pick)
    binding = bindings.get(key)
    origin = _clean_string(binding.get("origin")).casefold() if isinstance(binding, dict) else ""
    if origin not in {"picker", "picker_auto", "picker-authored"}:
        return False
    bindings.pop(key, None)
    item["frame_range_bindings"] = bindings
    current = item.get("frame_range_binding")
    if isinstance(current, dict):
        current_key = _frame_binding_key(
            current.get("video_slot") or current.get("video"),
            current.get("color_pick") or current.get("color"),
        )
        if current_key == key:
            item["frame_range_binding"] = None
    if not bindings:
        item["frame_range_enabled"] = False
        item["frame_range_selected_index"] = -1
    return True


def _normalize_frame_metadata(value: Any) -> List[Dict[str, Any]]:
    raw_items = value if isinstance(value, list) else []
    by_slot: Dict[int, Dict[str, Any]] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        slot = _video_slot_number(raw.get("video_slot") or raw.get("video"), MAX_VIDEOS)
        try:
            fps = float(raw.get("fps") or 0.0)
        except Exception:
            fps = 0.0
        try:
            start_frame = int(round(float(raw.get("start_frame"))))
            end_frame = int(round(float(raw.get("end_frame"))))
            frame_count = int(round(float(raw.get("frame_count") or 0)))
        except Exception:
            start_frame = 0
            end_frame = -1
            frame_count = 0
        try:
            duration_seconds = float(raw.get("duration_seconds") or 0.0)
        except Exception:
            duration_seconds = 0.0
        resolution = (
            raw.get("resolution")
            if isinstance(raw.get("resolution"), dict)
            else {}
        )
        try:
            width = max(
                0,
                int(round(float(raw.get("width") or resolution.get("width") or 0))),
            )
        except Exception:
            width = 0
        try:
            height = max(
                0,
                int(round(float(raw.get("height") or resolution.get("height") or 0))),
            )
        except Exception:
            height = 0
        warnings = [
            _clean_string(item)
            for item in raw.get("warnings", [])
            if _clean_string(item)
        ] if isinstance(raw.get("warnings"), list) else []
        colors: List[str] = []
        for color_value in raw.get("available_color_picks", []) if isinstance(raw.get("available_color_picks"), list) else []:
            color = _clean_string(color_value)
            if color and color not in colors:
                colors.append(color)
        range_count = end_frame - start_frame + 1 if end_frame >= start_frame else 0
        conflict = bool(raw.get("conflict")) or bool(
            frame_count > 0 and range_count > 0 and frame_count != range_count
        )
        if conflict and not warnings:
            warnings.append(
                f"Frame count {frame_count} does not match display range "
                f"{start_frame}–{end_frame} ({range_count} frames)."
            )
        structurally_valid = (
            fps > 0
            and frame_count > 0
            and end_frame >= start_frame
        )
        declared_valid = raw.get("valid")
        metadata_valid = (
            structurally_valid
            if declared_valid in (None, "")
            else bool(declared_valid)
        )
        by_slot[slot] = {
            "video_slot": f"@video{slot}",
            "video_uid": _clean_string(raw.get("video_uid") or raw.get("source_uid")),
            "source_uid": _clean_string(raw.get("video_uid") or raw.get("source_uid")),
            "selection_order": slot,
            "order_key": _clean_string(raw.get("order_key"))
            or _clean_string(raw.get("video_uid") or raw.get("source_uid")),
            "fps": fps,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "frame_count": frame_count,
            "duration_seconds": duration_seconds,
            "timebase": _clean_string(raw.get("timebase")),
            "width": width,
            "height": height,
            "resolution": {"width": width, "height": height},
            "available_color_picks": colors,
            "origin": _clean_string(raw.get("origin")),
            "conflict": conflict,
            "valid": metadata_valid and structurally_valid and not conflict,
            "warnings": warnings,
        }
    return [by_slot[slot] for slot in sorted(by_slot)]


def _current_frame_range_binding(item: Dict[str, Any]) -> Dict[str, Any] | None:
    picks = _normalize_color_picks(item.get("color_picks"))
    try:
        selected_index = int(item.get("frame_range_color_index") or 0)
    except Exception:
        selected_index = 0
    selected_index = max(0, min(len(picks) - 1, selected_index))
    if not _clean_string(picks[selected_index]):
        selected_index = next(
            (index for index, color in enumerate(picks) if _clean_string(color)),
            selected_index,
        )
    color = _clean_string(picks[selected_index] if picks else "")
    if not color:
        return None
    video_slots = _normalize_binding_video_slots(
        item.get("binding_video_slots"),
        item.get("marker_video") or 1,
        len(picks),
        MAX_VIDEOS,
    )
    slot = video_slots[selected_index]
    bindings = _normalize_frame_range_bindings(
        item.get("frame_range_bindings"),
        item.get("frame_range_binding"),
    )
    binding = bindings.get(_frame_binding_key(slot, color))
    if binding is not None:
        return dict(binding)
    if bool(item.get("frame_range_enabled")):
        return {
            "video_slot": f"@video{slot}",
            "color_pick": color,
            "origin": "manual",
            "start_frame": None,
            "end_frame": None,
            "ranges": [],
        }
    return None


def _legacy_relationship_targets(item: Dict[str, Any]) -> List[str]:
    """Preserve every readable Target from older multi-target dashboard states."""
    out: List[str] = []
    preserved_value = item.get("legacy_relationship_targets")
    if isinstance(preserved_value, (list, tuple)):
        preserved = list(preserved_value)
    elif isinstance(preserved_value, str) and preserved_value.strip():
        preserved = [preserved_value]
    else:
        preserved = []
    for value in preserved:
        target = _clean_string(value)
        if target and target not in out:
            out.append(target)

    raw_value = item.get("interaction_targets") or item.get("interaction_target") or item.get("interactionTarget")
    if isinstance(raw_value, (list, tuple)):
        raw = list(raw_value)
    elif isinstance(raw_value, str) and raw_value.strip():
        raw = [raw_value]
    else:
        raw = []
    custom_value = item.get("interaction_custom_targets")
    if isinstance(custom_value, (list, tuple)):
        customs = [_clean_string(value) for value in custom_value]
    elif isinstance(custom_value, str) and custom_value.strip():
        customs = [_clean_string(custom_value)]
    else:
        customs = []
    for index, value in enumerate(raw):
        target = _clean_string(customs[index] if _clean_string(value) == "Custom" and index < len(customs) else value)
        if target and target not in out:
            out.append(target)
    return out


def _migrate_target_authority(item: Dict[str, Any], scopes: List[str]) -> str:
    """Migrate one unambiguous legacy Target without merging distinct meanings."""
    owner = _clean_string(item.get("owner"))
    if owner == "Custom":
        owner = _clean_string(item.get("custom_owner") or item.get("custom_target"))
    relationship_scopes = {"Handheld prop", "Attached accessory", "Interactive scene prop"}
    if not owner and any(scope in relationship_scopes for scope in scopes):
        legacy_targets = _legacy_relationship_targets(item)
        if len(legacy_targets) == 1:
            owner = legacy_targets[0]
    return owner


def _relationship_scopes(item: Dict[str, Any]) -> List[str]:
    return [
        entry.get("scope_choice", "")
        for entry in _image_binding_entries(item)
        if entry.get("scope_choice") in {"Handheld prop", "Attached accessory", "Interactive scene prop"}
    ]


def _effective_image_source_type(item: Dict[str, Any]) -> str:
    source_type = _clean_string(item.get("source_type"))
    if source_type == "Role Required / Select Source Type":
        source_type = ""
    if source_type == "Custom":
        return _clean_string(item.get("custom_source_type")) or "Unspecified custom image role"
    return source_type or "Unspecified image role"


def _effective_video_source_type(item: Dict[str, Any]) -> str:
    source_type = _clean_string(item.get("source_type"))
    if source_type == "Role Required / Select Video Type":
        source_type = ""
    if source_type == "Custom":
        return _clean_string(item.get("custom_source_type")) or "Unspecified custom video type"
    return source_type or "Unspecified video type"


def _effective_video_role(item: Dict[str, Any]) -> str:
    role = _clean_string(item.get("control_role"))
    if role == "Custom Role":
        return _clean_string(item.get("custom_control_role")) or "Unspecified custom video role"
    return role



def _effective_target(item: Dict[str, Any], default: str) -> str:
    return _target_text(_clean_string(item.get("owner")), default)


def _default_image_target_for_main_type(
    source_type: Any,
    image_name: Any = "",
    asset_id: Any = "",
) -> str:
    """Return the editable initial Target implied by a verified Main Type."""
    main_type = _clean_string(source_type)
    if main_type == "Ignore / Unused":
        return "None"
    if main_type in {
        "Environment / Background",
        "Sky / Exterior Background",
        "Set / Structure",
        "Foreground / Ground",
    }:
        return "Scene / Environment"
    if main_type == "Scale / Composition Reference":
        return "Camera / Composition"
    if main_type in {
        "Color / Look Reference",
        "Color + Look + Lighting Mood Reference",
        "Lighting / Atmosphere Reference",
    }:
        return "Global Look"
    if main_type in {
        "Character Appearance",
        "Partial Character Detail",
        "Prop / Accessory",
        "Costume / Clothing",
    }:
        return _clean_string(image_name) or _clean_string(asset_id)
    return ""


def _verified_registered_subtype(item: Dict[str, Any]) -> str:
    if (
        not bool(item.get("asset_verified"))
        or _clean_string(item.get("asset_source_kind")).casefold() != "project"
    ):
        return ""
    subtype = _clean_string(item.get("asset_scope_candidate"))
    if subtype and subtype in image_scope_choices_for_source_type(
        item.get("source_type")
    ):
        return subtype
    return ""


def _normalize_image_binding_fields(item: Dict[str, Any], video_count: int = MAX_VIDEOS) -> Dict[str, Any]:
    picks = _normalize_color_picks(item.get("color_picks"))
    raw_scopes = item.get("binding_scopes")
    if raw_scopes is None:
        raw_scopes = item.get("sub_types")
    if raw_scopes is None:
        raw_scopes = item.get("subtypes")
    scopes = _normalize_binding_scopes(raw_scopes, item.get("scope"), len(picks))
    count = max(1, min(MAX_COLOR_PICKS, max(len(picks), len(scopes))))
    while len(picks) < count:
        picks.append("")
    while len(scopes) < count:
        scopes.append("")
    custom_scopes = _normalize_parallel_text_list(item.get("binding_custom_scopes"), count, MAX_COLOR_PICKS)
    registered_subtype = _verified_registered_subtype(item)
    # Sub Type is image-level authority. Color/video bindings remain independent,
    # but legacy per-binding subtype overrides are intentionally collapsed.
    first_authored_scope_index = next(
        (index for index, scope in enumerate(scopes) if _clean_string(scope)),
        -1,
    )
    primary_scope_index = (
        first_authored_scope_index
        if (
            not registered_subtype
            and not _clean_string(scopes[0] if scopes else "")
            and not _clean_string(item.get("scope"))
            and first_authored_scope_index >= 0
        )
        else 0
    )
    primary_scope = (
        registered_subtype
        or (
            scopes[primary_scope_index]
            if 0 <= primary_scope_index < len(scopes)
            else ""
        )
        or _clean_string(item.get("scope"))
    )
    primary_scope = _clean_string(primary_scope)
    primary_custom_scope = ""
    if not registered_subtype and primary_scope == "Custom scope":
        primary_custom_scope = _clean_string(
            (
                custom_scopes[primary_scope_index]
                if 0 <= primary_scope_index < len(custom_scopes)
                else ""
            )
            or (
                next(
                    (
                        scope
                        for scope in custom_scopes
                        if _clean_string(scope)
                    ),
                    "",
                )
            )
        )
    scopes = [primary_scope] * count
    custom_scopes = [primary_custom_scope] * count
    legacy_video_slots = _normalize_binding_video_slots(
        item.get("binding_video_slots"),
        item.get("marker_video") or item.get("color_video") or item.get("video_slot") or 1,
        count,
        MAX_VIDEOS,
    )
    item["color_picks"] = picks[:count]
    item["binding_scopes"] = scopes[:count]
    item["binding_custom_scopes"] = custom_scopes[:count]
    item["binding_video_slots"] = legacy_video_slots[:count]
    item["marker_video"] = item["binding_video_slots"][0]
    item["scope"] = item["binding_scopes"][0] if item["binding_scopes"] else ""
    item["frame_range_enabled"] = bool(item.get("frame_range_enabled"))
    try:
        frame_color_index = int(item.get("frame_range_color_index") or 0)
    except Exception:
        frame_color_index = 0
    item["frame_range_color_index"] = max(0, min(count - 1, frame_color_index))
    if not _clean_string(item["color_picks"][item["frame_range_color_index"]]):
        item["frame_range_color_index"] = next(
            (
                index
                for index, color in enumerate(item["color_picks"])
                if _clean_string(color)
            ),
            item["frame_range_color_index"],
        )
    # Range intent is canonical user state, not connection state.  Keep every
    # dormant/manual binding when Range is off or its video/color address is not
    # currently available; execution validation may describe the missing
    # context, but normalization must never erase the user's work.
    item["frame_range_bindings"] = _normalize_frame_range_bindings(
        item.get("frame_range_bindings"),
        item.get("frame_range_binding"),
    )
    try:
        selected_range_index = int(item.get("frame_range_selected_index"))
    except Exception:
        selected_range_index = -1
    item["frame_range_selected_index"] = (
        max(-1, selected_range_index)
        if item["frame_range_enabled"]
        else -1
    )
    item["frame_range_binding"] = _current_frame_range_binding(item)
    return item

def _image_binding_entries(item: Dict[str, Any], video_count: int = MAX_VIDEOS) -> List[Dict[str, Any]]:
    normalized = _normalize_image_binding_fields(dict(item), video_count)
    entries: List[Dict[str, Any]] = []
    scopes = normalized.get("binding_scopes", [""])
    custom_scopes = normalized.get("binding_custom_scopes", [""])
    colors = normalized.get("color_picks", [""])
    video_slots = normalized.get("binding_video_slots", [1])
    count = max(len(scopes), len(custom_scopes), len(colors), len(video_slots), 1)
    for index in range(count):
        scope_choice = _clean_string(scopes[index] if index < len(scopes) else "")
        custom_scope = _clean_string(custom_scopes[index] if index < len(custom_scopes) else "")
        if scope_choice == "Custom scope":
            effective_scope = custom_scope
            if (
                not effective_scope
                and _verified_registered_subtype(normalized) == scope_choice
            ):
                effective_scope = scope_choice
        else:
            effective_scope = scope_choice
        entries.append({
            "index": index,
            "scope": effective_scope,
            "scope_choice": scope_choice,
            "custom_scope": custom_scope,
            "color": _clean_string(colors[index] if index < len(colors) else ""),
            "marker_video": _normalize_marker_video(video_slots[index] if index < len(video_slots) else 1, video_count),
        })
    return entries

def _non_empty_binding_scopes(item: Dict[str, Any]) -> List[str]:
    scopes: List[str] = []
    for entry in _image_binding_entries(item):
        scope = entry["scope"]
        if scope and scope not in scopes:
            scopes.append(scope)
    return scopes


def _normalize_marker_video(value: Any, video_count: int = 1) -> int:
    max_video = max(1, min(MAX_VIDEOS, int(video_count or 1)))
    try:
        parsed = int(round(float(value)))
    except Exception:
        return 1
    return max(1, min(max_video, parsed))


def _enforce_color_pick_uniqueness_by_video(images: List[Dict[str, Any]], video_count: int = 1) -> List[Dict[str, Any]]:
    """Normalize Color Pick values without silently deleting duplicates.

    The dashboard prevents a color already used by the selected video from being
    offered again. Legacy or externally edited duplicate state is preserved so
    deterministic validation can report the conflict instead of losing data.
    """
    for item in images:
        _normalize_image_binding_fields(item, MAX_VIDEOS)
        cleaned: List[str] = []
        for color in item.get("color_picks", [""]):
            value = _clean_string(color)
            cleaned.append(value)
        item["color_picks"] = cleaned or [""]
        _normalize_image_binding_fields(item, MAX_VIDEOS)
    return images


def _reset_image_video_binding_to_primary(item: Dict[str, Any], video_count: int = MAX_VIDEOS) -> Dict[str, Any]:
    _normalize_image_binding_fields(item, video_count)
    item["marker_video"] = 1
    item["binding_video_slots"] = [1 for _ in item.get("color_picks", [""])]
    item["color_picks"] = ["" for _ in item.get("color_picks", [""])] or [""]
    item["picker_auto_color"] = ""
    item["picker_auto_video"] = 0
    item["picker_auto_source"] = ""
    _normalize_image_binding_fields(item, video_count)
    return item


def _reset_images_bound_to_inactive_videos(
    images: List[Dict[str, Any]], videos: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], bool]:
    """Preserve bindings whose video is temporarily absent.

    A temporarily absent address never erases or demotes user intent. The
    current goal may use the stored relationship immediately and may resolve the
    concrete source whenever that slot is supplied.
    """
    for item in images:
        _normalize_image_binding_fields(item, MAX_VIDEOS)
    return images, False

def _color_pick_text(item: Dict[str, Any], include_video: bool = True) -> str:
    parts: List[str] = []
    for entry in _image_binding_entries(item):
        color = entry["color"]
        if not color:
            continue
        marker = f"@video{entry['marker_video']} / {color}" if include_video else color
        scope = entry["scope"]
        parts.append(f"{scope} = {marker}" if scope else marker)
    return "; ".join(parts)

_CONTROL_ONLY_BINDING_PREFIX_RE = re.compile(
    r"^\s*(?:CONTROL_ONLY_BINDING|VFX_CONTROL_BINDING)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
def _control_binding_value(payload: str, key: str) -> str:
    key_pattern = r"(?:Marker|Color\s*Pick)" if key == "Marker" else re.escape(key)
    next_keys = r"Target|Function|Marker|Color\s*Pick|Boundary"
    match = re.search(
        rf"(?:^|[|;]\s*|/\s*)(?:{key_pattern})\s*=\s*(.+?)(?=\s*(?:[|;]|/\s*(?:{next_keys})\s*=)|$)",
        payload,
        re.IGNORECASE,
    )
    return _clean_string(match.group(1)) if match else ""


def _parse_control_only_bindings(descriptive_fields: Dict[str, Any] | None) -> tuple[List[Dict[str, Any]], List[str]]:
    """Parse optional structured control-only bindings without adding UI fields.

    Supported line syntax inside SCENE_CONTEXT or VIDEO_VFX:
    CONTROL_ONLY_BINDING: @video2 | Target = ExactName | Function = emitter | Marker = Blue | Boundary = exact local point
    """
    fields = descriptive_fields if isinstance(descriptive_fields, dict) else {}
    entries: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen: set[tuple] = set()
    for field_name in ("SCENE_CONTEXT", "VIDEO_VFX"):
        for line_number, raw_line in enumerate(str(fields.get(field_name, "") or "").splitlines(), 1):
            match = _CONTROL_ONLY_BINDING_PREFIX_RE.match(raw_line)
            if not match:
                continue
            payload = match.group(1).strip()
            video_match = re.search(r"@video(10|[1-9])\b", payload, re.IGNORECASE)
            if not video_match:
                errors.append(
                    f"{field_name} control-only binding line {line_number} has no "
                    f"@video1 through @video{MAX_VIDEOS} reference."
                )
                continue
            entry = {
                "field": field_name,
                "line": line_number,
                "video": int(video_match.group(1)),
                "target": _control_binding_value(payload, "Target"),
                "function": _control_binding_value(payload, "Function"),
                "marker": _control_binding_value(payload, "Marker"),
                "boundary": _control_binding_value(payload, "Boundary"),
            }
            missing = [key.lower() for key in ("target", "function", "boundary") if not entry[key]]
            if missing:
                errors.append(
                    f"{field_name} control-only binding line {line_number} is missing {', '.join(missing)}."
                )
                continue
            signature = (
                entry["video"],
                entry["target"],
                entry["function"],
                entry["marker"],
                entry["boundary"],
            )
            if signature in seen:
                continue
            seen.add(signature)
            entries.append(entry)
    return entries, errors


def _strip_control_only_binding_lines(value: Any) -> str:
    preserved: List[str] = []
    for line in str(value or "").splitlines():
        match = _CONTROL_ONLY_BINDING_PREFIX_RE.match(line)
        if not match:
            preserved.append(line)
            continue
        payload = match.group(1).strip()
        video_match = re.search(r"@video(10|[1-9])\b", payload, re.IGNORECASE)
        has_structured_fields = all(
            _control_binding_value(payload, key)
            for key in ("Target", "Function", "Boundary")
        )
        # Only a fully structured line is extracted into CONTROL-ONLY BINDING.
        # Malformed lines stay verbatim as ordinary user intent. A formatting
        # convention never becomes a prerequisite or warning by itself.
        if not video_match or not has_structured_fields:
            preserved.append(line)
    return "\n".join(preserved).strip()


def _control_bindings_for_video(entries: List[Dict[str, Any]], video_slot: int) -> List[Dict[str, Any]]:
    return [entry for entry in entries if int(entry.get("video") or 0) == int(video_slot)]


def _format_control_only_binding(entry: Dict[str, Any]) -> str:
    marker = f" / Marker = {entry['marker']}" if _clean_string(entry.get("marker")) else ""
    return (
        f"@video{int(entry['video'])} / Target = {entry['target']} / Function = {entry['function']}"
        f"{marker} / Control Boundary = {entry['boundary']} / Default interpretation = control cue; "
        "an explicit scoped instruction may use a named visible or supplied property only for its "
        "named Target and declared Control Boundary; if no separate temporal subset is stated or "
        "clearly implied, it applies to the whole shot, otherwise only to that subset; it does not expand into "
        "unrelated identity, material, lighting, motion, camera, or final-look attributes"
    )


def _normalize_text(state: Dict[str, Any]) -> Dict[str, str]:
    text = state.get("text") if isinstance(state.get("text"), dict) else {}
    out = {name: _clean_string(text.get(name, "")) for name in TEXT_FIELD_NAMES}

    legacy_parts: List[str] = []

    def add_part(label: str, value: Any) -> None:
        cleaned = _clean_string(value)
        if not cleaned:
            return
        line = f"{label}: {cleaned}" if label else cleaned
        if line not in legacy_parts:
            legacy_parts.append(line)

    add_part("", text.get("VIDEO_VFX", ""))
    add_part("Shot VFX note", text.get("FX_ADDITIONAL_INSTRUCTION", ""))
    missing = _clean_string(text.get("FALLBACK_MISSING_FUNCTION", ""))
    instruction = _clean_string(text.get("FALLBACK_INSTRUCTION", ""))
    if missing or instruction:
        fallback = " / ".join(part for part in [f"Missing function = {missing}" if missing else "", f"Instruction = {instruction}" if instruction else ""] if part)
        add_part("Fallback only if source is missing", fallback)
    if legacy_parts:
        out["VIDEO_VFX"] = "\n".join(legacy_parts)
    return out


def _normalize_ui(state: Dict[str, Any]) -> Dict[str, Any]:
    ui = state.get("ui") if isinstance(state.get("ui"), dict) else {}
    compatible = _clean_string(ui.get("resize_mode")) == UI_RESIZE_MODE
    source_heights = ui.get("group_heights") if compatible and isinstance(ui.get("group_heights"), dict) else {}
    group_heights: Dict[str, int] = {}
    for key, min_height in GROUP_MIN_HEIGHTS.items():
        try:
            value = int(round(float(source_heights.get(key))))
        except Exception:
            continue
        if min_height <= value <= GROUP_MAX_HEIGHT:
            group_heights[key] = value

    source_textarea_heights = ui.get("textarea_heights") if compatible and isinstance(ui.get("textarea_heights"), dict) else {}
    textarea_heights: Dict[str, int] = {}
    for key, raw_value in source_textarea_heights.items():
        normalized_key = _clean_string(key)
        if not re.fullmatch(r"video:(?:10|[1-9]):keep_out", normalized_key):
            continue
        try:
            value = int(round(float(raw_value)))
        except Exception:
            continue
        if KEEP_OUT_TEXTAREA_MIN_HEIGHT <= value <= KEEP_OUT_TEXTAREA_MAX_HEIGHT:
            textarea_heights[normalized_key] = value

    language = _clean_string(ui.get("language")).lower()
    if language not in ("en", "ko"):
        language = "en"
    theme = "T" if _clean_string(ui.get("theme")).upper() == "T" else "P"
    return {
        "group_heights": group_heights,
        "textarea_heights": textarea_heights,
        "resize_mode": UI_RESIZE_MODE,
        "language": language,
        "theme": theme,
    }


def _migrate_old_image_item(item: Dict[str, Any], slot: int) -> Dict[str, Any]:
    out = _default_image_item(slot)
    out["label"] = _clean_string(item.get("label") or item.get("name_override") or item.get("description"))
    out["present"] = bool(item.get("present")) or bool(out["label"])
    out["asset_id"] = _clean_string(item.get("asset_id"))
    out["asset_path"] = _clean_string(item.get("asset_path"))
    out["asset_library_id"] = _clean_string(item.get("asset_library_id"))
    out["asset_source_uid"] = _clean_string(
        item.get("asset_source_uid") or item.get("source_uid")
    )
    out["asset_project_uid"] = _clean_string(item.get("asset_project_uid"))
    try:
        out["asset_selection_order"] = max(
            0,
            int(item.get("asset_selection_order") or item.get("selection_order") or 0),
        )
    except Exception:
        out["asset_selection_order"] = 0
    out["asset_source_type_candidate"] = _clean_string(
        item.get("asset_source_type_candidate")
    )
    out["asset_scope_candidate"] = _clean_string(item.get("asset_scope_candidate"))
    raw_asset_colors = item.get("asset_color_pick_candidates")
    if isinstance(raw_asset_colors, (list, tuple)):
        out["asset_color_pick_candidates"] = [
            _clean_string(value)
            for value in raw_asset_colors
            if _clean_string(value)
        ]
    out["asset_default_target"] = _clean_string(item.get("asset_default_target"))
    out["asset_managed"] = bool(item.get("asset_managed"))
    asset_source_kind = _clean_string(item.get("asset_source_kind")).casefold()
    if asset_source_kind not in {"project", "user"}:
        asset_source_kind = ""
    out["asset_source_kind"] = asset_source_kind
    out["asset_verified"] = bool(
        item.get("asset_verified")
        and asset_source_kind == "project"
    )
    out["source_type"] = _clean_string(item.get("source_type")) or out["source_type"]
    out["custom_source_type"] = _clean_string(item.get("custom_source_type") or item.get("custom_main_type"))
    out["scope"] = _clean_string(item.get("scope"))
    out["color_picks"] = _normalize_color_picks(item.get("color_picks") or item.get("colorPick") or item.get("color_pick") or item.get("color") or item.get("preview_color"))
    out["binding_custom_scopes"] = _normalize_parallel_text_list(item.get("binding_custom_scopes") or item.get("custom_scopes"), len(out["color_picks"]), MAX_COLOR_PICKS)
    legacy_video_slots = _normalize_binding_video_slots(item.get("binding_video_slots"), item.get("marker_video") or item.get("color_video") or item.get("video_slot") or item.get("video_number") or item.get("video_pick"), len(out["color_picks"]), MAX_VIDEOS)
    out["binding_video_slots"] = legacy_video_slots
    out["marker_video"] = legacy_video_slots[0]
    raw_binding_scopes = item.get("binding_scopes")
    if raw_binding_scopes is None:
        raw_binding_scopes = item.get("sub_types")
    if raw_binding_scopes is None:
        raw_binding_scopes = item.get("subtypes")
    migration_scopes = _normalize_binding_scopes(raw_binding_scopes, out["scope"], len(out["color_picks"]))
    migration_primary_scope = (
        _verified_registered_subtype(out)
        or (migration_scopes[0] if migration_scopes else "")
        or out["scope"]
        or next(
            (
                scope
                for scope in migration_scopes
                if _clean_string(scope)
            ),
            "",
        )
    )
    out["owner"] = _migrate_target_authority(item, [migration_primary_scope])
    out["legacy_relationship_targets"] = _legacy_relationship_targets(item)
    out["preview_marker"] = _clean_string(item.get("preview_marker") or item.get("target_marker") or item.get("replacement_target"))
    out["picker_auto_color"] = _clean_string(item.get("picker_auto_color"))
    try:
        out["picker_auto_video"] = int(item.get("picker_auto_video") or 0)
    except Exception:
        out["picker_auto_video"] = 0
    out["picker_auto_source"] = _clean_string(item.get("picker_auto_source"))
    out["frame_range_enabled"] = bool(item.get("frame_range_enabled"))
    try:
        out["frame_range_color_index"] = int(item.get("frame_range_color_index") or 0)
    except Exception:
        out["frame_range_color_index"] = 0
    out["frame_range_bindings"] = _normalize_frame_range_bindings(
        item.get("frame_range_bindings"),
        item.get("frame_range_binding"),
    )
    try:
        out["frame_range_selected_index"] = int(item.get("frame_range_selected_index"))
    except Exception:
        out["frame_range_selected_index"] = -1
    out["manual"] = bool(item.get("manual", True))

    old_role = _clean_string(item.get("role"))
    if old_role and not item.get("source_type"):
        m = re.match(r"^Subject\s+(\d+)\s+Appearance$", old_role)
        if m:
            out["source_type"] = "Character Appearance"
            out["owner"] = f"Subject {int(m.group(1))}"
            out["scope"] = "Full body / full appearance"
        elif old_role == "Environment / Background":
            out["source_type"] = "Environment / Background"
            out["owner"] = "Scene / Environment"
            out["scope"] = "Main background"
        elif old_role == "Lighting / Atmosphere":
            out["source_type"] = "Lighting / Atmosphere Reference"
            out["owner"] = "Global Look"
            out["scope"] = "Lighting mood only"
        elif old_role == "Scene Scale / Composition":
            out["source_type"] = "Scale / Composition Reference"
            out["owner"] = "Camera / Composition"
            out["scope"] = "Composition only"
        elif old_role == "Prop / Set Reference":
            out["source_type"] = "Prop / Accessory"
            out["scope"] = "Custom scope"
        elif old_role == "Color / Look Reference":
            out["source_type"] = "Color / Look Reference"
            out["owner"] = "Global Look"
            out["scope"] = "Render look only"
        elif old_role == "Environment + Lighting + Color":
            out["source_type"] = "Environment / Background"
            out["owner"] = "Scene / Environment"
        elif old_role == "Ignore / Unused":
            out["source_type"] = "Ignore / Unused"
    if out["source_type"] not in IMAGE_SOURCE_TYPE_CHOICES:
        unknown_source_type = out["source_type"]
        existing_custom = _clean_string(out.get("custom_source_type"))
        out["source_type"] = "Custom"
        out["custom_source_type"] = " | ".join(dict.fromkeys(
            value
            for value in (unknown_source_type, existing_custom)
            if value
        ))
    subject_num = _subject_number(out["owner"])
    if subject_num:
        out["owner"] = f"image {subject_num}"
    out["binding_scopes"] = _normalize_binding_scopes(raw_binding_scopes, out["scope"], len(out["color_picks"]))
    _normalize_image_binding_fields(out, MAX_VIDEOS)
    return out

def _migrate_old_video_item(item: Dict[str, Any], slot: int) -> Dict[str, Any]:
    out = _default_video_item(slot)
    video_uid = _clean_string(item.get("video_uid") or item.get("source_uid"))
    out["video_uid"] = video_uid
    out["source_uid"] = video_uid
    try:
        out["selection_order"] = max(
            0,
            int(item.get("selection_order") or item.get("video_selection_order") or 0),
        )
    except Exception:
        out["selection_order"] = 0
    out["order_key"] = _clean_string(item.get("order_key")) or video_uid
    out["picker_managed"] = bool(item.get("picker_managed") or video_uid)
    out["label"] = _clean_string(item.get("label") or item.get("name_override") or item.get("description"))
    out["present"] = bool(item.get("present")) or bool(out["label"])
    out["source_type"] = _clean_string(item.get("source_type")) or out["source_type"]
    out["custom_source_type"] = _clean_string(item.get("custom_source_type") or item.get("custom_video_type"))
    out["control_role"] = _canonical_video_role(item.get("control_role"))
    out["custom_control_role"] = _clean_string(item.get("custom_control_role") or item.get("custom_video_role"))
    out["keep_out"] = _merge_unique_notes(
        item.get("keep_out"),
        item.get("keepOut"),
        item.get("exclusion_note"),
        item.get("negative_prompt"),
        item.get("video_marker"),
        item.get("marker"),
        item.get("description"),
    )
    out["picker_auto_label"] = _clean_string(item.get("picker_auto_label"))
    out["picker_auto_depth"] = _normalize_picker_auto_depth(
        item.get("picker_auto_depth")
    )
    out["picker_auto_motion_guide"] = (
        _normalize_picker_auto_motion_guide(
            item.get("picker_auto_motion_guide")
        )
    )
    out["picker_motion_guide_summary"] = (
        _normalize_picker_motion_guide_summary(
            item.get("picker_motion_guide_summary")
        )
    )
    companion_kind = _clean_string(item.get("picker_companion_kind")).casefold()
    if companion_kind not in {"depth", "motion_guide"}:
        media_kind = re.sub(
            r"[^a-z0-9]+",
            "_",
            _clean_string(item.get("media_kind")).casefold(),
        ).strip("_")
        if media_kind == "maya_depth_playblast" or out["picker_auto_depth"]:
            companion_kind = "depth"
        elif media_kind == "maya_motion_guide" or out["picker_auto_motion_guide"]:
            companion_kind = "motion_guide"
    out["picker_companion_kind"] = (
        companion_kind if companion_kind in {"depth", "motion_guide"} else ""
    )
    raw_companion_source_slot = (
        item.get("picker_companion_source_slot")
        if item.get("picker_companion_source_slot") not in (None, "")
        else item.get("source_video_slot")
        if item.get("source_video_slot") not in (None, "")
        else item.get("companion_of_video_slot")
    )
    try:
        source_slot_text = _clean_string(raw_companion_source_slot)
        source_slot_match = re.fullmatch(
            r"(?:@?video)?\s*(-?[0-9]+)",
            source_slot_text,
            re.IGNORECASE,
        )
        companion_source_slot = int(
            source_slot_match.group(1)
            if source_slot_match is not None
            else raw_companion_source_slot
        )
    except Exception:
        companion_source_slot = -1
    out["picker_companion_source_slot"] = (
        companion_source_slot
        if companion_source_slot in range(0, MAX_VIDEOS + 1)
        else -1
    )
    out["picker_companion_source_uid"] = _clean_string(
        item.get("picker_companion_source_uid")
        or item.get("source_video_uid")
        or item.get("companion_of_video_uid")
        or item.get("companion_video_uid")
    )
    out["picker_companion_validated"] = bool(
        item.get("picker_companion_validated")
        or out["picker_auto_depth"]
        or out["picker_auto_motion_guide"]
    )
    out["manual"] = bool(item.get("manual")) or slot == 1

    old_role = _clean_string(item.get("role"))
    if old_role and not item.get("source_type"):
        if old_role == "Maya Preview / Strongest Unified Shot-Control Source":
            out["source_type"] = "Maya Preview / Playblast"
            out["control_role"] = "Primary Unified Shot Control"
        elif old_role == "Motion / Timing Reference":
            out["source_type"] = "Motion Reference"
            out["control_role"] = "Local Motion Detail Only"
        elif old_role == "Camera / Layout / Depth Reference":
            out["source_type"] = "Camera / Layout Reference"
            out["control_role"] = "Spatial Alignment Verification Only"
        elif old_role == "Performance Reference":
            out["source_type"] = "Motion Reference"
            out["control_role"] = "Local Motion Detail Only"
        elif old_role == "Reference Video Only":
            out["source_type"] = "Custom"
            out["control_role"] = "Context Only"
        elif old_role == "Ignore / Unused":
            out["source_type"] = "Ignore / Unused"
    if out["source_type"] not in VIDEO_SOURCE_TYPE_CHOICES:
        unknown_source_type = out["source_type"]
        existing_custom = _clean_string(out.get("custom_source_type"))
        out["source_type"] = "Custom"
        out["custom_source_type"] = " | ".join(dict.fromkeys(
            value
            for value in (unknown_source_type, existing_custom)
            if value
        ))
    if out["control_role"] not in VIDEO_CONTROL_ROLE_CHOICES:
        unknown_control_role = out["control_role"]
        existing_custom_role = _clean_string(out.get("custom_control_role"))
        out["control_role"] = "Custom Role"
        out["custom_control_role"] = " | ".join(dict.fromkeys(
            value
            for value in (unknown_control_role, existing_custom_role)
            if value
        ))
    return out


def _has_image_meaning(item: Dict[str, Any]) -> bool:
    return bool(
        item.get("present")
        or _clean_string(item.get("label"))
        or _clean_string(item.get("asset_id"))
        or _clean_string(item.get("asset_path"))
        or _clean_string(item.get("asset_source_uid"))
        or _clean_string(item.get("asset_library_id"))
        or item.get("asset_managed")
        or item.get("asset_verified")
        or item.get("source_type")
        not in ("", "Role Required / Select Source Type")
        or _clean_string(item.get("custom_source_type"))
        or _clean_string(item.get("owner"))
        or any(_clean_string(value) for value in item.get("legacy_relationship_targets", []))
        or any(_clean_string(value) for value in item.get("binding_scopes", []))
        or any(_clean_string(value) for value in item.get("binding_custom_scopes", []))
        or any(_clean_string(value) for value in item.get("color_picks", []))
        or _clean_string(item.get("preview_marker"))
        or item.get("frame_range_enabled")
    )


def _has_video_meaning(item: Dict[str, Any]) -> bool:
    return (
        bool(item.get("present"))
        or bool(_clean_string(item.get("video_uid") or item.get("source_uid")))
        or bool(_clean_string(item.get("label")))
        or bool(_clean_string(item.get("keep_out")))
        or item.get("source_type") not in ("", "Role Required / Select Video Type")
        or bool(item.get("control_role"))
        or bool(_clean_string(item.get("custom_source_type")))
        or bool(_clean_string(item.get("custom_control_role")))
    )


def _normalize_items(state: Dict[str, Any], key: str, max_count: int) -> List[Dict[str, Any]]:
    source = state.get(key) if isinstance(state.get(key), list) else []
    migrated: List[Dict[str, Any]] = []
    for slot, item in enumerate(source[:max_count], start=1):
        if not isinstance(item, dict):
            migrated.append(_default_image_item(slot) if key == "images" else _default_video_item(slot))
            continue
        migrated.append(_migrate_old_image_item(item, slot) if key == "images" else _migrate_old_video_item(item, slot))
    if not migrated:
        if key == "images":
            migrated = [_default_image_item(slot) for slot in range(1, 5)]
        else:
            migrated = [_default_video_item(1)]

    if key == "videos":
        last_visible = 0
        for idx, item in enumerate(migrated):
            if idx == 0 or item.get("manual") or _has_video_meaning(item):
                last_visible = idx
        visible_count = max(1, min(max_count, last_visible + 1))
        result: List[Dict[str, Any]] = []
        for idx in range(1, visible_count + 1):
            prev = migrated[idx - 1] if idx <= len(migrated) else {}
            row = _migrate_old_video_item(prev, idx)
            row["slot"] = idx
            row["token"] = f"@video{idx}"
            row["name"] = _slot_name("VIDEO", idx)
            row["present"] = _has_video_meaning(row)
            row["manual"] = bool(row.get("manual")) or idx == 1
            result.append(row)
        return result

    # Image rows are explicitly managed by the user. A new library starts with
    # four rows, but users may remove rows down to one. Editing a name or any
    # other field never creates another image row automatically.
    visible_count = max(1, min(max_count, len(migrated)))
    result: List[Dict[str, Any]] = []
    for idx in range(1, visible_count + 1):
        prev = migrated[idx - 1] if idx <= len(migrated) else {}
        row = _migrate_old_image_item(prev, idx)
        row["slot"] = idx
        row["token"] = f"@image{idx}"
        row["name"] = _slot_name("IMAGE", idx)
        row["present"] = _has_image_meaning(row)
        row["manual"] = True
        result.append(row)
    return result


def _is_active_image(item: Dict[str, Any]) -> bool:
    return _has_image_meaning(item) and item.get("source_type") != "Ignore / Unused"


def _image_asset_connection_enabled(state: Dict[str, Any]) -> bool:
    image_asset = state.get("image_asset")
    return bool(
        isinstance(image_asset, dict)
        and image_asset.get("enabled")
    )


def _active_image_rows_for_state(
    images: List[Dict[str, Any]],
    state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return the only rows that may own active ``@imageN`` tokens.

    With no ASSET_IN edge this is the historical/manual policy.  While the
    edge is present, however, generator media contains only the selected
    upstream assets, so a native/manual row must remain dormant and cannot
    claim an extra Prompt token.
    """
    connection_owned = _image_asset_connection_enabled(state)
    return [
        item
        for item in images
        if _is_active_image(item)
        and (not connection_owned or bool(item.get("asset_managed")))
    ]


def _normalize_dormant_image_rows(
    value: Any,
    *,
    asset_rows: bool,
) -> List[Dict[str, Any]]:
    """Normalize hidden image rows without inventing visible placeholder rows."""
    if not isinstance(value, (list, tuple)):
        return []
    limit = MAX_IMAGES * 4 if asset_rows else MAX_IMAGES
    out: List[Dict[str, Any]] = []
    for raw in value[:limit]:
        if not isinstance(raw, dict):
            continue
        row = _migrate_old_image_item(raw, len(out) + 1)
        row["manual"] = True
        if asset_rows:
            if not _clean_string(
                row.get("asset_source_uid") or row.get("asset_library_id")
            ):
                continue
            row["asset_managed"] = True
        else:
            row["asset_managed"] = False
            row["asset_verified"] = False
            row["asset_source_kind"] = ""
            row["asset_selection_order"] = 0
        out.append(row)
    return out


def _image_target_choices_for_row(item: Dict[str, Any], images: List[Dict[str, Any]]) -> List[str]:
    dynamic_targets = [
        _clean_string(row.get("label"))
        for row in images
        if _is_active_image(row) and _clean_string(row.get("label"))
    ]
    source_type = _clean_string(item.get("source_type"))
    choices = ["", *dynamic_targets]
    if source_type == "Ignore / Unused":
        choices = ["", "None"]
    elif source_type in {"Environment / Background", "Sky / Exterior Background", "Set / Structure", "Foreground / Ground"}:
        choices = ["", *dynamic_targets, "Scene / Environment"]
    elif source_type == "Scale / Composition Reference":
        choices = ["", *dynamic_targets, "Camera / Composition"]
    elif source_type in {"Color / Look Reference", "Color + Look + Lighting Mood Reference", "Lighting / Atmosphere Reference"}:
        choices = ["", *dynamic_targets, "Global Look"]
    elif source_type == "Custom":
        choices = ["", *dynamic_targets, "Scene / Environment", "Camera / Composition", "Global Look"]
    current_target = _clean_string(item.get("owner"))
    if current_target:
        choices.append(current_target)
    return list(dict.fromkeys(choices))


def _is_active_video(item: Dict[str, Any]) -> bool:
    return _has_video_meaning(item) and item.get("source_type") != "Ignore / Unused"


def _enforce_single_active_video_unified(videos: List[Dict[str, Any]]) -> None:
    """Legacy normalization hook that now preserves independent video roles.

    Picker payloads still author their own explicit Color/Depth/Motion roles,
    but Prompt must not infer a primary source or mutate manual rows by slot.
    """
    return


def _normalize_picker_slot_suppressions(value: Any) -> Dict[str, str]:
    """Keep same-run Picker deletions local to their exact video slot."""
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, str] = {}
    for raw_slot, raw_payload_id in value.items():
        try:
            slot = int(raw_slot)
        except (TypeError, ValueError):
            continue
        payload_id = _clean_string(raw_payload_id)
        if 1 <= slot <= MAX_VIDEOS and payload_id:
            normalized[str(slot)] = payload_id
    return normalized


def _normalize_dormant_video_rows(
    value: Any,
    *,
    managed: bool,
) -> List[Dict[str, Any]]:
    """Normalize hidden video rows without assigning active ``@videoN`` tokens."""
    if not isinstance(value, (list, tuple)):
        return []
    normalized: List[Dict[str, Any]] = []
    seen_uids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        row = _migrate_old_video_item(raw, len(normalized) + 1)
        uid = _clean_string(row.get("video_uid") or row.get("source_uid"))
        if managed:
            if not uid or uid in seen_uids:
                continue
            seen_uids.add(uid)
            row["video_uid"] = uid
            row["source_uid"] = uid
            row["picker_managed"] = True
        else:
            if uid or bool(row.get("picker_managed")):
                continue
            row["picker_managed"] = False
            row["selection_order"] = 0
            row["order_key"] = ""
        row["slot"] = 0
        row["token"] = ""
        row["name"] = ""
        normalized.append(row)
    return normalized


def _normalize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    source_intent_fallbacks = _normalize_source_intent_fallbacks(
        state.get(_SOURCE_INTENT_FALLBACKS_KEY)
    )
    for row_group in ("images", "videos"):
        raw_rows = state.get(row_group)
        if not isinstance(raw_rows, list):
            if raw_rows not in (None, ""):
                entry = _source_intent_entry(
                    WIDGET_PARAMETER_NAME,
                    f"readable non-list {row_group} value",
                    raw_rows,
                )
                if entry is not None:
                    source_intent_fallbacks.append(entry)
            continue
        for row_index, raw_row in enumerate(raw_rows, start=1):
            if isinstance(raw_row, dict) or raw_row in (None, ""):
                continue
            entry = _source_intent_entry(
                WIDGET_PARAMETER_NAME,
                f"readable non-object {row_group} row {row_index}",
                raw_row,
            )
            if entry is not None:
                source_intent_fallbacks.append(entry)
    source_intent_fallbacks = _normalize_source_intent_fallbacks(
        source_intent_fallbacks
    )
    videos = _normalize_items(state, "videos", MAX_VIDEOS)

    # Legacy dashboard states may still contain old global video-control
    # text. That function now belongs to the fourth video field, Keep Out. When no
    # explicit per-video destination exists, preserve the note on @video1 so it is
    # not incorrectly emitted as VIDEO VFX.
    text_source = state.get("text") if isinstance(state.get("text"), dict) else {}
    legacy_keep_out = _merge_unique_notes(
        text_source.get("VIDEO_CONTEXT"),
        text_source.get("VIDEO_MARKER"),
        text_source.get("VIDEO_DESCRIPTION"),
    )
    if legacy_keep_out and videos:
        videos[0]["keep_out"] = _merge_unique_notes(videos[0].get("keep_out"), legacy_keep_out)

    _enforce_single_active_video_unified(videos)
    images = _normalize_items(state, "images", MAX_IMAGES)
    images, _ = _reset_images_bound_to_inactive_videos(images, videos)
    images = _enforce_color_pick_uniqueness_by_video(images, len(videos))
    active_images = len(_active_image_rows_for_state(images, state))
    active_videos = sum(1 for item in videos if _is_active_video(item))

    picker_source = state.get("picker") if isinstance(state.get("picker"), dict) else {}
    try:
        matched_images = max(0, int(float(picker_source.get("matched_images") or 0)))
    except Exception:
        matched_images = 0
    picker_markers = picker_source.get("markers") if isinstance(picker_source.get("markers"), list) else []
    picker_frame_metadata = _normalize_frame_metadata(picker_source.get("frame_metadata"))
    picker_contract_errors = [
        _clean_string(item)
        for item in picker_source.get("contract_errors", [])
        if _clean_string(item)
    ] if isinstance(picker_source.get("contract_errors"), list) else []
    try:
        selected_video_count = max(
            0,
            min(
                MAX_VIDEOS,
                int(picker_source.get("selected_video_count") or 0),
            ),
        )
    except Exception:
        selected_video_count = 0
    picker = {
        "enabled": bool(picker_source.get("enabled")),
        "awaiting_data": bool(picker_source.get("awaiting_data")),
        "run_id": _clean_string(picker_source.get("run_id")),
        "selection_id": _clean_string(picker_source.get("selection_id")),
        "selected_video_count": selected_video_count,
        "ordered_video_uids": [
            _clean_string(value)
            for value in (
                picker_source.get("ordered_video_uids")
                if isinstance(picker_source.get("ordered_video_uids"), (list, tuple))
                else []
            )
            if _clean_string(value)
        ][:MAX_VIDEOS],
        "order_managed": bool(picker_source.get("order_managed")),
        "dormant_video_rows": _normalize_dormant_video_rows(
            picker_source.get("dormant_video_rows"),
            managed=True,
        ),
        "dormant_manual_rows": _normalize_dormant_video_rows(
            picker_source.get("dormant_manual_rows"),
            managed=False,
        ),
        "slot_suppressions": _normalize_picker_slot_suppressions(
            picker_source.get("slot_suppressions")
        ),
        "scene": _clean_string(picker_source.get("scene")),
        "video_path": _clean_string(picker_source.get("video_path")),
        "camera": _clean_string(picker_source.get("camera")),
        "markers": [item for item in picker_markers if isinstance(item, dict)],
        "frame_metadata": picker_frame_metadata,
        "contract_errors": picker_contract_errors,
        "matched_images": matched_images,
    }
    image_asset_source = (
        state.get("image_asset")
        if isinstance(state.get("image_asset"), dict)
        else {}
    )
    try:
        selected_asset_count = max(
            0,
            int(float(image_asset_source.get("selected_assets") or 0)),
        )
    except Exception:
        selected_asset_count = 0
    try:
        verified_asset_count = max(
            0,
            int(float(image_asset_source.get("verified_assets") or 0)),
        )
    except Exception:
        verified_asset_count = 0
    try:
        imported_image_count = max(
            0,
            int(float(image_asset_source.get("imported_images") or 0)),
        )
    except Exception:
        imported_image_count = 0
    image_asset = {
        "enabled": bool(image_asset_source.get("enabled")),
        "project_id": _clean_string(image_asset_source.get("project_id")),
        "project_uid": _clean_string(image_asset_source.get("project_uid")),
        "project_root": _clean_string(image_asset_source.get("project_root")),
        "selection_id": _clean_string(image_asset_source.get("selection_id")),
        "selected_assets": selected_asset_count,
        "verified_assets": verified_asset_count,
        "imported_images": imported_image_count,
        "ordered_source_uids": [
            _clean_string(value)
            for value in (
                image_asset_source.get("ordered_source_uids")
                if isinstance(
                    image_asset_source.get("ordered_source_uids"),
                    (list, tuple),
                )
                else []
            )
            if _clean_string(value)
        ][:MAX_IMAGES],
        "order_managed": bool(image_asset_source.get("order_managed")),
        "dormant_manual_rows": _normalize_dormant_image_rows(
            image_asset_source.get("dormant_manual_rows"),
            asset_rows=False,
        ),
        "dormant_asset_rows": _normalize_dormant_image_rows(
            image_asset_source.get("dormant_asset_rows"),
            asset_rows=True,
        ),
    }

    return {
        "schema": STATE_SCHEMA,
        "mode": MODE_NAME,
        "theme": "dark-neon",
        "image_taxonomy": _image_taxonomy_payload(),
        "images": images,
        "videos": videos,
        "text": _normalize_text(state),
        _SOURCE_INTENT_FALLBACKS_KEY: source_intent_fallbacks,
        "ui": _normalize_ui(state),
        "picker": picker,
        "image_asset": image_asset,
        "status": {
            "active_images": active_images,
            "active_videos": active_videos,
            "visible_image_slots": len(images),
            "visible_video_slots": len(videos),
            "max_images": MAX_IMAGES,
            "max_videos": MAX_VIDEOS,
        },
    }


def _subject_number(owner: str) -> int | None:
    m = re.match(r"^Subject\s+(\d+)$", owner or "")
    return int(m.group(1)) if m else None


def _target_text(owner: str, default: str) -> str:
    owner = _clean_string(owner)
    if _subject_number(owner):
        return f"image {_subject_number(owner)}"
    return owner or default


def _detail_suffix(scope: str, extra_detail: str = "") -> str:
    parts = [_clean_string(scope), _clean_string(extra_detail)]
    parts = [p for p in parts if p]
    return " / " + " / ".join(parts) if parts else ""


def _target_function(scope: str) -> str:
    if scope == "Handheld prop":
        return "holder"
    if scope == "Attached accessory":
        return "attachment subject"
    if scope == "Interactive scene prop":
        return "interaction subject"
    return "production subject"


def _target_function_suffix(scope: str) -> str:
    if scope not in {"Handheld prop", "Attached accessory", "Interactive scene prop"}:
        return ""
    return f" / Target function = {_target_function(scope)}"


def _image_target_function_lines(item: Dict[str, Any], seq: int) -> List[str]:
    if _clean_string(item.get("source_type")) != "Prop / Accessory":
        return []
    targets = list(dict.fromkeys(
        value
        for value in [
            _effective_target(item, f"image {seq}"),
            *_legacy_relationship_targets(item),
        ]
        if _clean_string(value)
    ))
    lines: List[str] = []
    for scope in _relationship_scopes(item):
        matching_video_slots = list(dict.fromkeys(
            int(entry.get("marker_video") or 1)
            for entry in _image_binding_entries(item, MAX_VIDEOS)
            if _clean_string(entry.get("color"))
            and (entry.get("scope_choice") == scope or entry.get("scope") == scope)
        ))
        binding_note = (
            " / Supplied video bindings = "
            + ", ".join(f"@video{slot}" for slot in matching_video_slots)
            if matching_video_slots
            else ""
        )
        for target in targets:
            line = (
                f"@image{seq} / Target = {target} / Image Sub Type = {scope} / "
                f"Target defines the {_target_function(scope)}; contact, grip, release, attachment, "
                "deformation, visibility, occlusion, and separation follow the current user goal"
                f"{binding_note}"
            )
            if line not in lines:
                lines.append(line)
    return lines


def _image_role_line(item: Dict[str, Any], seq: int) -> str:
    token = f"@image{seq}"
    st_choice = _clean_string(item.get("source_type"))
    st = _effective_image_source_type(item)
    owner = _effective_target(item, f"image {seq}")
    scopes = _non_empty_binding_scopes(item) or [""]

    def line_for(scope: str) -> str:
        suffix = _detail_suffix(scope)
        if st_choice == "Character Appearance":
            return (
                f"{owner} / Approved final appearance source = {token}{suffix} / "
                "Authority = intrinsic identity, color, pattern, and material character; white backdrop, "
                "studio lighting, baked highlight/shadow, matte spill, and halo are not scene-light authority"
            )
        if st_choice == "Partial Character Detail":
            return f"{owner} / Partial character detail source = {token}{suffix}"
        if st_choice == "Prop / Accessory":
            return (
                f"{owner} prop / accessory source = {token}{suffix}{_target_function_suffix(scope)} / "
                "Authority = intrinsic prop appearance only; reference lighting is not inherited"
            )
        if st_choice == "Costume / Clothing":
            return f"{owner} costume / clothing source = {token}{suffix}"
        if st_choice == "Environment / Background":
            return (
                f"{owner} / Environment / background source = {token}{suffix} / "
                "Authority = continuous environment appearance and target lighting context, including dummy regions"
            )
        if st_choice == "Sky / Exterior Background":
            return f"{owner} / Sky / exterior background source = {token}{suffix}"
        if st_choice == "Set / Structure":
            return f"{owner} / Set / structure source = {token}{suffix}"
        if st_choice == "Foreground / Ground":
            return f"{owner} / Foreground / ground source = {token}{suffix}"
        if st_choice == "Color / Look Reference":
            return f"{owner} / Color / look reference = {token}{suffix}"
        if st_choice == "Color + Look + Lighting Mood Reference":
            return f"{owner} / Color / look / lighting reference = {token}{suffix}"
        if st_choice == "Lighting / Atmosphere Reference":
            return (
                f"{owner} / Lighting / atmosphere source = {token}{suffix} / "
                "Default = implementation evidence for the approved background or sequence look unless explicitly approved as lighting authority"
            )
        if st_choice == "Scale / Composition Reference":
            return f"{owner} / Scale / composition reference = {token}{suffix}"
        if st_choice == "Custom":
            return f"{owner} / {st} = {token}{suffix}"
        return (
            f"Unclassified image idea reference = {token} / No missing role is inferred / "
            "Use every attribute supported by readable evidence or an explicit scoped exception; "
            "do not infer unrelated identity, material, lighting, motion, camera, or final-look authority"
        )

    lines: List[str] = []
    for scope in scopes:
        for line in line_for(scope).splitlines():
            if line not in lines:
                lines.append(line)
    return "\n".join(lines)

def _clean_replacement_marker(marker: str, image_seq: int) -> str:
    marker = _clean_string(marker)
    if not marker:
        return ""
    if "=" in marker:
        marker = marker.split("=", 1)[1].strip()
    token_pattern = r"\s*/\s*@image\d+\b\s*"
    previous = None
    while previous != marker:
        previous = marker
        marker = re.sub(token_pattern + r"$", "", marker).strip()
    marker = re.sub(r"\s+", " ", marker).strip(" /\t")
    return marker


def _image_replacement_line(item: Dict[str, Any], seq: int) -> str | None:
    explicit_marker = _clean_replacement_marker(item.get("preview_marker"), seq)
    st = _clean_string(item.get("source_type"))
    owner = _effective_target(item, f"image {seq}")

    def format_line(marker: str, scope: str) -> str:
        if st == "Character Appearance":
            label = f"{owner} / {scope}" if scope else owner
            return f"{label} replaces = {marker} / @image{seq}"
        if st == "Partial Character Detail":
            return f"{owner} partial detail guides = {marker} / @image{seq} / {scope or 'specified detail only'}"
        if st in ("Prop / Accessory", "Costume / Clothing"):
            label = scope or ("prop / accessory" if st == "Prop / Accessory" else "costume / clothing detail")
            target_function_suffix = _target_function_suffix(scope) if st == "Prop / Accessory" else ""
            return f"{owner} {label} replaces = {marker} / @image{seq}{target_function_suffix}"
        if st == "Environment / Background":
            return f"{owner} environment / background replaces = {marker} / @image{seq}{_detail_suffix(scope)}"
        if st == "Sky / Exterior Background":
            return f"{owner} sky / exterior background replaces = {marker} / @image{seq}{_detail_suffix(scope)}"
        if st == "Set / Structure":
            return f"{owner} set / structure replaces = {marker} / @image{seq}{_detail_suffix(scope)}"
        if st == "Foreground / Ground":
            return f"{owner} foreground / ground replaces = {marker} / @image{seq}{_detail_suffix(scope)}"
        if st in ("Color / Look Reference", "Color + Look + Lighting Mood Reference", "Lighting / Atmosphere Reference", "Scale / Composition Reference"):
            return f"{st} applies to = {marker} / @image{seq}{_detail_suffix(scope)}"
        if st == "Custom":
            return f"{_effective_image_source_type(item)} applies to {owner} = {marker} / @image{seq}{_detail_suffix(scope)}"
        return (
            f"Unclassified image marker association = {marker} / @image{seq}"
            f"{_detail_suffix(scope)} / No missing role is inferred / "
            "Use the supplied association according to the current user goal"
        )

    lines: List[str] = []
    if explicit_marker:
        first_scope = next((entry["scope"] for entry in _image_binding_entries(item) if entry["scope"]), "")
        lines.append(format_line(explicit_marker, first_scope))
    for entry in _image_binding_entries(item):
        if not entry["color"]:
            continue
        marker = f"Color Pick marker: @video{entry['marker_video']} / {entry['color']}"
        line = format_line(marker, entry["scope"])
        if line not in lines:
            lines.append(line)
    return "\n".join(lines) if lines else None

def _video_reverse_binding_entries(active_images: List[Dict[str, Any]], video_slot: int) -> List[Dict[str, str]]:
    bindings: List[Dict[str, str]] = []
    for item in active_images:
        image_slot = int(item.get("slot") or 1)
        target = _effective_target(item, f"image {image_slot}")
        for entry in _image_binding_entries(item, MAX_VIDEOS):
            if entry["marker_video"] != video_slot or not entry["color"]:
                continue
            bindings.append({
                "image": f"@image{image_slot}",
                "target": target,
                "scope": entry["scope"] or "Unspecified Sub Type",
                "color": entry["color"],
            })
    return bindings


def _video_reverse_bindings(active_images: List[Dict[str, Any]], video_slot: int) -> List[str]:
    return [
        f"{entry['image']} / Target = {entry['target']} / Image Sub Type = {entry['scope']} / Color Pick = {entry['color']}"
        for entry in _video_reverse_binding_entries(active_images, video_slot)
    ]


def _self_scoped_auxiliary_reference(item: Dict[str, Any], seq: int) -> Dict[str, str] | None:
    source_type = _clean_string(item.get("source_type"))
    role = _clean_string(item.get("control_role"))
    if role == "Context Only" and role in VIDEO_ROLE_COMPATIBILITY.get(source_type, set()):
        return {
            "authority_domain": "descriptive_context",
            "fields": "default interpretation: descriptive shot context",
            "time_mapping": "source-local timing as supplied; no cross-source mapping is inferred",
            "authority": "default context interpretation; an explicit scoped instruction may change only its named property for a named target or clearly scene-wide scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset",
        }
    spec = SELF_SCOPED_AUXILIARY_REFERENCE_SPECS.get((source_type, role))
    return dict(spec) if isinstance(spec, dict) else None


def _self_scoped_alignment_evaluation(
    active_images: List[Dict[str, Any]],
    active_videos: List[Dict[str, Any]],
    control_only_bindings: List[Dict[str, Any]],
    frame_metadata: Any,
) -> tuple[List[str], List[str]]:
    """Evaluate source-local and explicitly declared Picker companion contracts.

    Video numbers are transient selection addresses. A Depth or Motion Guide
    may therefore appear in any slot, including ``@video1``. Matched-bundle
    authority follows only its stable source UID and/or its explicitly remapped
    source slot; it never falls back to an unrelated ``@video1``.
    """
    normalized_metadata = _normalize_frame_metadata(frame_metadata)
    metadata_by_slot = {
        _video_slot_number(item.get("video_slot"), MAX_VIDEOS): item
        for item in normalized_metadata
    }
    metadata_by_uid = {
        _clean_string(item.get("video_uid") or item.get("source_uid")): item
        for item in normalized_metadata
        if _clean_string(item.get("video_uid") or item.get("source_uid"))
    }
    active_video_slots = {
        int(item.get("slot") or 1)
        for item in active_videos
    }
    active_slot_by_uid = {
        _clean_string(item.get("video_uid") or item.get("source_uid")): int(
            item.get("slot") or 1
        )
        for item in active_videos
        if _clean_string(item.get("video_uid") or item.get("source_uid"))
    }
    reports: List[str] = []
    conflicts: List[str] = []

    def contract(
        item: Dict[str, Any] | None,
    ) -> tuple[Dict[str, Any] | None, str, str]:
        if not isinstance(item, dict):
            return None, "absent", "metadata is not connected"
        try:
            fps = float(item.get("fps") or 0.0)
            frame_count = int(item.get("frame_count") or 0)
            duration = float(item.get("duration_seconds") or 0.0)
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
        except Exception:
            return None, "invalid", "metadata contains non-numeric values"
        if not bool(item.get("valid")):
            return None, "invalid", "metadata is marked invalid or internally conflicting"
        if duration <= 0 and fps > 0 and frame_count > 0:
            duration = frame_count / fps
        if fps <= 0 or frame_count <= 0 or duration <= 0:
            return None, "incomplete", "frame count, FPS, or duration is unavailable"
        expected_duration = frame_count / fps
        if abs(duration - expected_duration) > 0.001:
            return (
                None,
                "invalid",
                f"duration {duration:.6f}s is inconsistent with "
                f"{frame_count} frames / {fps:g} FPS ({expected_duration:.6f}s)",
            )
        if width <= 0 or height <= 0:
            return None, "incomplete", "decoded width or height is unavailable"
        return (
            {
                "fps": fps,
                "frame_count": frame_count,
                "duration_seconds": duration,
                "width": width,
                "height": height,
            },
            "complete",
            "",
        )

    def metadata_for(item: Dict[str, Any], slot: int) -> Dict[str, Any] | None:
        uid = _clean_string(item.get("video_uid") or item.get("source_uid"))
        return metadata_by_uid.get(uid) if uid in metadata_by_uid else metadata_by_slot.get(slot)

    def companion_provenance(
        item: Dict[str, Any],
        seq: int,
    ) -> tuple[str, bool, int, str, bool]:
        depth_auto = _normalize_picker_auto_depth(item.get("picker_auto_depth"))
        motion_auto = _normalize_picker_auto_motion_guide(
            item.get("picker_auto_motion_guide")
        )
        kind = _clean_string(item.get("picker_companion_kind")).casefold()
        if kind not in {"depth", "motion_guide"}:
            if depth_auto and not motion_auto:
                kind = "depth"
            elif motion_auto and not depth_auto:
                kind = "motion_guide"
            else:
                kind = ""
        validated = bool(
            item.get("picker_companion_validated")
            or depth_auto
            or motion_auto
        )
        source_uid = _clean_string(
            item.get("picker_companion_source_uid")
            or item.get("source_video_uid")
            or item.get("companion_of_video_uid")
            or item.get("companion_video_uid")
        )
        try:
            source_slot = int(
                item.get("picker_companion_source_slot")
                if item.get("picker_companion_source_slot") not in (None, "")
                else _picker_companion_source_slot(item)
            )
        except Exception:
            source_slot = -1

        legacy_primary = False
        if source_uid:
            resolved_uid_slot = active_slot_by_uid.get(source_uid, -1)
            if resolved_uid_slot < 1:
                source_slot = -1
            elif source_slot > 0 and source_slot != resolved_uid_slot:
                # Stable UID is authoritative when a serialized transient slot
                # still reflects the previous drag order.
                source_slot = resolved_uid_slot
            elif source_slot == 0:
                # Standalone provenance cannot simultaneously name a source.
                source_slot = -1
            else:
                source_slot = resolved_uid_slot
        elif source_slot not in range(0, MAX_VIDEOS + 1):
            source_slot = -1

        # Legacy states did not persist a source address. Their auto-provenance
        # was produced only after validating the historical @video1 bundle.
        # Permit that narrow shape only for rows with no stable UID and never
        # for a companion already occupying @video1.
        item_uid = _clean_string(item.get("video_uid") or item.get("source_uid"))
        if (
            kind
            and validated
            and source_slot < 0
            and not source_uid
            and not item_uid
            and seq > 1
        ):
            source_slot = 1
            legacy_primary = True
        return kind, validated, source_slot, source_uid, legacy_primary

    for item in active_videos:
        seq = int(item.get("slot") or 1)
        self_scoped = _self_scoped_auxiliary_reference(item, seq)
        if not self_scoped or self_scoped["authority_domain"] == "descriptive_context":
            continue

        token = f"@video{seq}"
        auxiliary_contract, auxiliary_status, auxiliary_detail = contract(
            metadata_for(item, seq)
        )
        (
            companion_kind,
            companion_validated,
            source_slot,
            source_uid,
            legacy_primary,
        ) = companion_provenance(item, seq)
        explicit_picker_companion = bool(companion_kind)
        if not explicit_picker_companion and _video_reverse_binding_entries(
            active_images, seq
        ):
            continue
        if not explicit_picker_companion and _control_bindings_for_video(
            control_only_bindings, seq
        ):
            continue

        if not explicit_picker_companion:
            if auxiliary_status == "invalid":
                conflicts.append(
                    f"{token} has invalid declared source metadata: "
                    f"{auxiliary_detail}. Metadata-derived authority is ignored; "
                    "the source remains independently usable."
                )
                reports.append(
                    f"{token} source metadata = UNVERIFIED / {auxiliary_detail} / "
                    "source-local use remains available"
                )
            elif auxiliary_contract is None:
                reports.append(
                    f"{token} source metadata = OPTIONAL / "
                    "use the connected source as supplied without requiring another video slot"
                )
            else:
                reports.append(
                    f"{token} source-local contract = "
                    f"{auxiliary_contract['frame_count']} decoded frames / "
                    f"{auxiliary_contract['fps']:g} FPS / "
                    f"{auxiliary_contract['duration_seconds']:.6f} seconds / "
                    f"{auxiliary_contract['width']}x{auxiliary_contract['height']} / "
                    "no cross-source correspondence inferred"
                )
            continue

        companion_label = "Depth" if companion_kind == "depth" else "Motion Guide"
        if source_slot == 0:
            if auxiliary_contract is None:
                if auxiliary_status == "invalid":
                    conflicts.append(
                        f"{token} standalone {companion_label} has invalid metadata: "
                        f"{auxiliary_detail}. Matched-bundle authority is not claimed."
                    )
                reports.append(
                    f"{token} standalone Picker companion contract = INCOMPLETE / "
                    f"{auxiliary_detail or 'decoded metadata is unavailable'} / "
                    "no matched source is required"
                )
            elif companion_validated:
                reports.append(
                    f"{token} standalone Picker companion contract = VALIDATED / "
                    f"{auxiliary_contract['frame_count']} decoded frames / "
                    f"{auxiliary_contract['fps']:g} FPS / "
                    f"{auxiliary_contract['duration_seconds']:.6f} seconds / "
                    f"{auxiliary_contract['width']}x{auxiliary_contract['height']} / "
                    "no matched source is required"
                )
            else:
                reports.append(
                    f"{token} standalone Picker companion contract = UNVERIFIED / "
                    "source-local use remains available"
                )
            continue

        if source_slot < 1:
            source_detail = (
                f"source UID {source_uid} is not selected"
                if source_uid
                else "the declared source is missing or no longer selected"
            )
            reports.append(
                f"{token} explicit Picker companion contract = INCOMPLETE / "
                f"{source_detail} / matched-bundle authority is disabled / "
                "independent source use remains available"
            )
            continue

        source_token = f"@video{source_slot}"
        if source_slot == seq or source_slot not in active_video_slots:
            reports.append(
                f"{token} explicit Picker companion contract = INCOMPLETE / "
                f"declared source {source_token} is not an independent active source / "
                "matched-bundle authority is disabled"
            )
            continue
        source_item = next(
            (
                source
                for source in active_videos
                if int(source.get("slot") or 1) == source_slot
            ),
            None,
        )
        source_contract, source_status, source_detail = contract(
            metadata_for(source_item, source_slot)
            if isinstance(source_item, dict)
            else None
        )
        if not companion_validated:
            reports.append(
                f"{token} declared {companion_label} companion against {source_token} = "
                "UNVERIFIED / matched-bundle authority is disabled / "
                "independent source use remains available"
            )
            continue
        if source_contract is None:
            if source_status == "invalid":
                conflicts.append(
                    f"{token} loses declared {source_token} matched-bundle authority because "
                    f"{source_detail}. Both sources remain independently usable."
                )
                reports.append(
                    f"{token} alignment = UNVERIFIED / {source_token} {source_detail} / "
                    "independent source use remains available"
                )
            else:
                reports.append(
                    f"{token} explicit Picker companion contract = INCOMPLETE / "
                    f"the declared bundle source metadata for {source_token} is unavailable"
                )
            continue
        if auxiliary_contract is None:
            if auxiliary_status == "invalid":
                conflicts.append(
                    f"{token} has invalid declared alignment metadata: {auxiliary_detail}. "
                    "Matched-bundle authority is ignored; the source remains independently usable."
                )
                reports.append(
                    f"{token} alignment = UNVERIFIED / {auxiliary_detail} / "
                    "independent source use remains available"
                )
            else:
                reports.append(
                    f"{token} explicit Picker companion contract = INCOMPLETE / "
                    "this companion's decoded metadata is unavailable"
                )
            continue

        mismatches: List[str] = []
        if auxiliary_contract["frame_count"] != source_contract["frame_count"]:
            mismatches.append(
                f"frame count {auxiliary_contract['frame_count']} != {source_contract['frame_count']}"
            )
        if abs(auxiliary_contract["fps"] - source_contract["fps"]) > 0.001:
            mismatches.append(
                f"FPS {auxiliary_contract['fps']:g} != {source_contract['fps']:g}"
            )
        if (
            abs(
                auxiliary_contract["duration_seconds"]
                - source_contract["duration_seconds"]
            )
            > 0.001
        ):
            mismatches.append(
                "duration "
                f"{auxiliary_contract['duration_seconds']:.6f}s != "
                f"{source_contract['duration_seconds']:.6f}s"
            )
        if (
            auxiliary_contract["width"] != source_contract["width"]
            or auxiliary_contract["height"] != source_contract["height"]
        ):
            mismatches.append(
                "raster "
                f"{auxiliary_contract['width']}x{auxiliary_contract['height']} != "
                f"{source_contract['width']}x{source_contract['height']}"
            )

        if mismatches:
            conflicts.append(
                f"{token} self-scoped alignment does not match {source_token}: "
                + "; ".join(mismatches)
                + ". Matched-bundle authority is disabled; the source remains independently usable."
            )
            reports.append(
                f"{token} alignment = NOT MATCHED / "
                + "; ".join(mismatches)
                + " / independent source use remains available"
            )
            continue

        reports.append(
            f"{token} Picker slot contract = MATCHED against {source_token} / "
            f"{auxiliary_contract['frame_count']} decoded frames / "
            f"{auxiliary_contract['fps']:g} FPS / "
            f"{auxiliary_contract['duration_seconds']:.6f} seconds / "
            f"{auxiliary_contract['width']}x{auxiliary_contract['height']} / "
            f"source indices 0-{auxiliary_contract['frame_count'] - 1} / "
            + ("legacy explicit bundle provenance / " if legacy_primary else "")
            + "this contract records the verified match; a changed downstream file remains "
            "independently usable but loses matched-bundle authority"
        )
    return reports, conflicts


def _video_role_line(
    item: Dict[str, Any],
    seq: int,
    active_images: List[Dict[str, Any]] | None = None,
    control_only_bindings: List[Dict[str, Any]] | None = None,
) -> str:
    token = f"@video{seq}"
    st = _effective_video_source_type(item)
    role = _effective_video_role(item)
    image_links = _video_reverse_bindings(active_images or [], seq)
    control_links = [
        _format_control_only_binding(entry)
        for entry in _control_bindings_for_video(control_only_bindings or [], seq)
    ]
    self_scoped = (
        _self_scoped_auxiliary_reference(item, seq)
        if not image_links and not control_links
        else None
    )
    if self_scoped:
        lines = [
            f"{token} = {st} / {role or 'Unspecified optional role'} / Binding Mode = Recognized self-scoped full-shot reference",
            f"{token} self-scoped reference = Reference Domain = Current shot / Boundary = Full shot / "
            f"Fields = {self_scoped['fields']} / Time Mapping = {self_scoped['time_mapping']} / "
            f"Authority = {self_scoped['authority']}",
            f"{token} default role interpretation is advisory; an explicit scoped instruction may change "
            "only its named property for a named target or clearly scene-wide scope; if no temporal "
            "subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset.",
        ]
    elif role == "Primary Unified Shot Control":
        lines = [
            f"{token} = {st} / {role} / Target = Current shot / "
            "Control Boundary = Full shot / Authority comes from the explicitly supplied role"
        ]
    else:
        lines = [
            f"{token} = {st} / {role or 'Unspecified optional role'} / "
            "Exact local bindings add Target + Control Boundary when supplied; their absence does not "
            "invalidate readable source attributes or create a connection gate"
        ]
    if st == "Maya Preview / Playblast":
        lines.append(
            f"{token} Color Playblast scope = animator-authored acting, motion, pose, timing, trajectory, "
            "contact, camera, framing, visibility, occlusion, relative depth, and spatial arrangement are "
            "protected shot state by default; a role label alone does not narrow them / Proxy marker colors, "
            "Color Pick markers, temporary Maya materials, dummy shading, and temporary lighting = routing "
            "or tracking controls, not final identity, material, lighting, or look authority / An explicit "
            "scoped instruction may change only its named property for a named Target or clearly scene-wide "
            "scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset / "
            "Image bindings and PROJECT_STYLE_LOOK add their declared authority only when supplied; "
            "their absence creates no dependency"
        )
    if image_links:
        lines.append(f"{token} image-derived control bindings = " + "; ".join(image_links))
    if control_links:
        lines.append(f"{token} control-only bindings = " + "; ".join(control_links))
    if (
        not image_links
        and not control_links
        and not self_scoped
        and role != "Primary Unified Shot Control"
    ):
        lines.append(
            f"{token} local control binding = not supplied; use the supplied source for the user goal "
            "without inventing a Target, boundary, or missing semantic field"
        )
    return "\n".join(lines)


def _motion_guide_semantic_summary_line(
    item: Dict[str, Any],
    seq: int,
) -> str:
    summary = _normalize_picker_motion_guide_summary(
        item.get("picker_motion_guide_summary")
    )
    if not summary:
        return ""
    if not summary["semantic_face"]:
        return (
            f"@video{seq} verified Motion Guide profile = "
            f"{summary['profile']} / semantic face data = unavailable / "
            "the motion source remains independently usable"
        )
    groups = ", ".join(summary["semantic_groups"]) or "none"
    return (
        f"@video{seq} verified semantic face summary = "
        f"{summary['target_count']} target(s) / "
        f"{summary['channel_count']} final Blend Shape channel(s) / "
        f"{summary['driver_count']} connected numeric curve driver(s) / "
        f"{summary['landmark_count']} surface-pinned landmark(s) / "
        f"groups {groups} / "
        f"{summary['rasterized_sample_count']} visible raster sample(s) / "
        f"{summary['hidden_or_occluded_sample_count']} sidecar-only hidden or "
        "occluded sample(s) / raw NURBS curve geometry is never rendered"
    )

def _authority_scope(value: Any, fallback: str) -> str:
    return _clean_string(value) or fallback


def _canonical_authority_domain(source_type: str, scope: str) -> tuple[str, int, str, str]:
    """Return canonical function, rank, label, and comparison scope.

    Equivalent functions reached through different Main Type paths must land in
    the same domain. Broad combined references use a lower rank than dedicated
    single-function sources for the same exact Target.
    """
    source_type = _clean_string(source_type)
    scope = _clean_string(scope)

    exact_scope_map = {
        "Full body / full appearance": ("character_appearance", 300, "approved final character appearance", "full body / full appearance"),
        "Head / face only": ("head_face", 400 if source_type == "Partial Character Detail" else 300, "head / face", "head / face"),
        "Eye / expression detail": ("eye_expression", 400, "eye / expression detail", "eye / expression detail"),
        "Eyes / iris / pupil detail": ("eyes_iris_pupil", 400, "eyes / iris / pupil detail", "eyes / iris / pupil detail"),
        "Hand / foot / body part detail": ("body_part_detail", 400, "hand / foot / body part detail", "hand / foot / body part detail"),
        "Hair / fur detail": ("hair_fur_detail", 400, "hair / fur detail", "hair / fur detail"),
        "Costume detail": ("costume_detail", 400, "costume detail", "costume detail"),
        "Full outfit / complete costume": ("complete_costume", 300, "full outfit / complete costume", "full outfit / complete costume"),
        "Handheld prop": ("handheld_prop", 300, "handheld prop", "handheld prop"),
        "Attached accessory": ("attached_accessory", 300, "attached accessory", "attached accessory"),
        "Interactive scene prop": ("interactive_scene_prop", 300, "interactive scene prop", "interactive scene prop"),
        "Independent scene prop": ("independent_scene_prop", 300, "independent scene prop", "independent scene prop"),
        "Main background": ("environment_background", 300, "main environment / background", "main background"),
        "Sky / exterior area": ("sky_exterior", 300, "sky / exterior background", "sky / exterior area"),
        "Set geometry / structure only": ("set_structure", 300, "set geometry / structure", "set geometry / structure"),
        "Ground / floor": ("ground_floor", 300, "ground / floor", "ground / floor"),
        "Foreground element": ("foreground_element", 300, "foreground element", "foreground element"),
        "Color mood only": ("color_mood", 300, "color mood", "assigned target function"),
        "Lighting mood only": ("lighting_mood", 300, "lighting mood", "assigned target function"),
        "Render look only": ("render_look", 300, "render look", "assigned target function"),
        "Scale only": ("scale", 300, "scale", "assigned target function"),
        "Composition only": ("composition", 300, "composition", "assigned target function"),
    }
    if scope in exact_scope_map:
        return exact_scope_map[scope]

    if scope == "All color + look + lighting functions":
        return ("combined_look", 200, "combined color / look / lighting", "assigned target function")
    if scope == "Scale + composition":
        return ("scale_composition", 200, "scale + composition", "assigned target function")

    if scope and scope != "unspecified scope":
        key = re.sub(r"\s+", " ", scope.casefold()).strip()
        return (f"custom_scope:{key}", 300, scope, scope)

    mapping = {
        "Character Appearance": ("character_appearance", 300, "approved final character appearance", "unspecified character appearance"),
        "Partial Character Detail": ("character_detail", 400, "partial character detail", "unspecified character detail"),
        "Prop / Accessory": ("prop_accessory", 300, "prop / accessory design", "unspecified prop / accessory"),
        "Costume / Clothing": ("costume_clothing", 300, "costume / clothing", "unspecified costume"),
        "Environment / Background": ("environment_background", 300, "environment / background", "unspecified environment"),
        "Sky / Exterior Background": ("sky_exterior", 300, "sky / exterior background", "unspecified sky / exterior"),
        "Set / Structure": ("set_structure", 300, "set / structure", "unspecified set / structure"),
        "Foreground / Ground": ("foreground_ground", 300, "foreground / ground", "unspecified foreground / ground"),
        "Color / Look Reference": ("color_look", 300, "color / look", "assigned target function"),
        "Color + Look + Lighting Mood Reference": ("combined_look", 200, "combined color / look / lighting", "assigned target function"),
        "Lighting / Atmosphere Reference": ("lighting_mood", 300, "lighting / atmosphere", "assigned target function"),
        "Scale / Composition Reference": ("scale_composition", 300, "scale / composition", "assigned target function"),
        "Custom": ("custom_image_role", 300, "custom image role", "unspecified custom scope"),
    }
    return mapping.get(source_type, ("unspecified_image_role", 0, "unspecified image role", "unspecified scope"))


def _image_authority_entries(item: Dict[str, Any], seq: int) -> List[tuple]:
    token = f"@image{seq}"
    source_type_choice = _clean_string(item.get("source_type"))
    target = _effective_target(item, f"image {seq}")
    entries: List[tuple] = []
    for binding in _image_binding_entries(item):
        scope = _authority_scope(binding["scope"], "unspecified scope")
        domain, rank, label, comparison_scope = _canonical_authority_domain(source_type_choice, scope)
        if source_type_choice == "Custom":
            custom_main = re.sub(r"\s+", " ", _effective_image_source_type(item).casefold()).strip()
            custom_scope = re.sub(r"\s+", " ", scope.casefold()).strip()
            domain = f"custom_main_type:{custom_main}"
            comparison_scope = f"custom_scope:{custom_scope}"
            label = _effective_image_source_type(item)
        if scope == "All color + look + lighting functions":
            for sub_domain, sub_label in (("color_mood", "color mood"), ("render_look", "render look"), ("lighting_mood", "lighting mood")):
                entries.append((sub_domain, target, comparison_scope, 200, token, sub_label))
        elif scope == "Scale + composition":
            for sub_domain, sub_label in (("scale", "scale"), ("composition", "composition")):
                entries.append((sub_domain, target, comparison_scope, 200, token, sub_label))
        else:
            entries.append((domain, target, comparison_scope, rank, token, label))
    return entries

def _description_source_reference_conflicts(
    label: str,
    value: Any,
    active_image_slots: set[int],
    active_video_slots: set[int],
) -> List[str]:
    conflicts: List[str] = []
    for prefix, number in re.findall(r"@(image|video)(\d+)", _clean_string(value), flags=re.IGNORECASE):
        slot = int(number)
        if prefix.lower() == "image" and slot not in active_image_slots:
            conflicts.append(
                f"{label} references currently unsupplied @image{slot}; retain the address as immediately "
                "usable user intent, with the current goal governing how it is resolved."
            )
        elif prefix.lower() == "video" and slot not in active_video_slots:
            conflicts.append(
                f"{label} references currently unsupplied @video{slot}; retain the address as immediately "
                "usable user intent, with the current goal governing how it is resolved."
            )
    return conflicts


def _find_source_authority_conflicts(
    active_images: List[Dict[str, Any]],
    active_videos: List[Dict[str, Any]],
    descriptive_fields: Dict[str, Any] | None = None,
    frame_metadata: Any = None,
) -> List[str]:
    groups: Dict[tuple, List[tuple]] = {}
    conflicts: List[str] = []
    descriptive_fields = descriptive_fields if isinstance(descriptive_fields, dict) else {}
    active_image_slots = {int(item.get("slot") or 1) for item in active_images}
    active_video_slots = {int(item.get("slot") or 1) for item in active_videos}
    active_names = [_clean_string(item.get("label")) for item in active_images if _clean_string(item.get("label"))]
    control_only_bindings, _control_binding_notes = _parse_control_only_bindings(descriptive_fields)
    allowed_control_targets = set(active_names) | set(IMAGE_SYSTEM_TARGETS)
    for entry in control_only_bindings:
        token = f"{entry['field']} control-only binding line {entry['line']}"
        if int(entry["video"]) not in active_video_slots:
            conflicts.append(
                f"{token} references currently unsupplied @video{entry['video']}; the tuple remains "
                "immediately usable under the current user goal without a slot prerequisite."
            )
        if entry["target"] not in allowed_control_targets:
            conflicts.append(
                f"{token} uses a user-defined Target outside the current suggestions; preserve it exactly "
                "and apply it according to the current user goal."
            )
        for key in ("target", "function", "marker", "boundary"):
            if len(_clean_string(entry.get(key))) > MAX_IDENTIFIER_CHARS:
                conflicts.append(f"{token} {key} exceeds {MAX_IDENTIFIER_CHARS} characters.")
    duplicate_names = sorted({name for name in active_names if active_names.count(name) > 1})
    for name in duplicate_names:
        conflicts.append(
            f"Image Name {name!r} appears in multiple slots; each source remains distinct by its @image token."
        )

    full_appearance_targets: set[str] = set()
    for item in active_images:
        if _clean_string(item.get("source_type")) != "Character Appearance":
            continue
        scopes = {_clean_string(entry.get("scope")) for entry in _image_binding_entries(item)}
        if "Full body / full appearance" in scopes:
            full_appearance_targets.add(_effective_target(item, ""))

    for item in active_images:
        seq = int(item.get("slot") or 1)
        token = f"@image{seq}"
        source_type = _clean_string(item.get("source_type"))
        name = _clean_string(item.get("label"))
        owner_choice = _clean_string(item.get("owner"))
        effective_target = _effective_target(item, "")

        if len(name) > MAX_IDENTIFIER_CHARS:
            conflicts.append(f"{token} Name exceeds {MAX_IDENTIFIER_CHARS} characters.")
        if len(_clean_string(item.get("custom_source_type"))) > MAX_IDENTIFIER_CHARS:
            conflicts.append(f"{token} Custom Main Type exceeds {MAX_IDENTIFIER_CHARS} characters.")
        if owner_choice and owner_choice not in _image_target_choices_for_row(item, active_images):
            conflicts.append(
                f"{token} Target is outside the current suggestions; preserve the supplied Target and let "
                "the user goal govern its interpretation."
            )
        if len(owner_choice) > MAX_IDENTIFIER_CHARS:
            conflicts.append(f"{token} Target exceeds {MAX_IDENTIFIER_CHARS} characters.")

        for entry in _image_binding_entries(item):
            if len(_clean_string(entry.get("custom_scope"))) > MAX_IDENTIFIER_CHARS:
                conflicts.append(f"{token} binding {entry['index'] + 1} Custom scope exceeds {MAX_IDENTIFIER_CHARS} characters.")
            if entry["color"] and entry["marker_video"] not in active_video_slots:
                conflicts.append(
                    f"{token} binding {entry['index'] + 1} names currently unsupplied "
                    f"@video{entry['marker_video']} / {entry['color']}; retain it as immediately usable "
                    "user intent without a slot prerequisite."
                )
            allowed_colors = _color_pick_choices_for_source_type(source_type)
            if entry["color"] and entry["color"] not in allowed_colors:
                conflicts.append(
                    f"{token} binding {entry['index'] + 1} uses {entry['color']} outside the current "
                    f"suggested palette for {source_type or 'an unselected Main Type'}; preserve the marker "
                    "as supplied."
                )

        for domain, target, scope, rank, authority_token, label in _image_authority_entries(item, seq):
            groups.setdefault((domain, target, scope), []).append((rank, authority_token, label))

    auxiliary_groups: Dict[tuple[str, str, str], List[str]] = {}
    for item in active_videos:
        seq = int(item.get("slot") or 1)
        token = f"@video{seq}"
        source_type = _clean_string(item.get("source_type"))
        role = _clean_string(item.get("control_role"))
        name = _clean_string(item.get("label"))

        if len(name) > MAX_IDENTIFIER_CHARS:
            conflicts.append(f"{token} Name exceeds {MAX_IDENTIFIER_CHARS} characters.")
        if len(_clean_string(item.get("custom_source_type"))) > MAX_IDENTIFIER_CHARS:
            conflicts.append(f"{token} Custom Main Type exceeds {MAX_IDENTIFIER_CHARS} characters.")
        if len(_clean_string(item.get("custom_control_role"))) > MAX_IDENTIFIER_CHARS:
            conflicts.append(f"{token} Custom Role exceeds {MAX_IDENTIFIER_CHARS} characters.")
        if source_type in VIDEO_ROLE_COMPATIBILITY and role and role not in VIDEO_ROLE_COMPATIBILITY[source_type]:
            conflicts.append(
                f"{token} uses an uncommon video Main Type / Video Sub Type pair: {source_type} / {role}; "
                "preserve both values and let the user goal govern their combined use."
            )
        reverse_bindings = _video_reverse_binding_entries(active_images, seq)
        control_bindings = _control_bindings_for_video(control_only_bindings, seq)
        self_scoped = (
            _self_scoped_auxiliary_reference(item, seq)
            if not reverse_bindings and not control_bindings
            else None
        )
        # Exact local/reverse bindings retain their historical auxiliary-slot
        # treatment. Self-scoped full-shot roles are slot-agnostic because a
        # selected Depth or Motion Guide can legitimately be @video1.
        if seq > 1:
            for binding in reverse_bindings:
                auxiliary_groups.setdefault(
                    (_effective_video_role(item), binding["target"], binding["scope"]),
                    [],
                ).append(token)
            for binding in control_bindings:
                auxiliary_groups.setdefault(
                    (_effective_video_role(item), binding["target"], binding["boundary"]),
                    [],
                ).append(token)
        if self_scoped and self_scoped["authority_domain"] != "descriptive_context":
            auxiliary_groups.setdefault(
                (self_scoped["authority_domain"], "Current shot", "Full shot"),
                [],
            ).append(token)
        if len(_clean_string(item.get("keep_out"))) > MAX_KEEP_OUT_CHARS:
            conflicts.append(f"{token} Keep Out exceeds {MAX_KEEP_OUT_CHARS} characters.")

    for (role, target, scope), tokens in auxiliary_groups.items():
        unique_tokens = list(dict.fromkeys(tokens))
        if len(unique_tokens) > 1:
            conflicts.append(
                f"{', '.join(unique_tokens)} describe overlapping auxiliary authority for {target} / "
                f"{scope} / {role}; preserve all supplied sources and let the user goal govern the combination."
            )

    _alignment_reports, alignment_conflicts = _self_scoped_alignment_evaluation(
        active_images,
        active_videos,
        control_only_bindings,
        frame_metadata,
    )
    conflicts.extend(alignment_conflicts)

    used_markers: Dict[tuple[int, str], str] = {}
    for item in active_images:
        seq = int(item.get("slot") or 1)
        for entry in _image_binding_entries(item):
            color = _clean_string(entry.get("color"))
            if not color:
                continue
            key = (int(entry.get("marker_video") or 1), color)
            token = f"@image{seq} binding {int(entry.get('index') or 0) + 1}"
            if key in used_markers:
                conflicts.append(f"{token} duplicates {used_markers[key]} at @video{key[0]} / {color}.")
            else:
                used_markers[key] = token

    for entry in control_only_bindings:
        marker = _clean_string(entry.get("marker"))
        if not marker:
            continue
        key = (int(entry.get("video") or 1), marker)
        token = f"{entry['field']} control-only binding line {entry['line']}"
        if key in used_markers:
            conflicts.append(
                f"{token} overlaps {used_markers[key]} at @video{key[0]} / {marker}; preserve both supplied "
                "bindings and let the user goal govern their combination."
            )
        else:
            used_markers[key] = token

    for field_name in TEXT_FIELD_NAMES:
        value = _clean_string(descriptive_fields.get(field_name))
        field_limit = MAX_VIDEO_VFX_CHARS if field_name == "VIDEO_VFX" else MAX_DESCRIPTION_CHARS
        if len(value) > field_limit:
            conflicts.append(f"{field_name} exceeds {field_limit} characters.")
        conflicts.extend(_description_source_reference_conflicts(field_name, value, active_image_slots, active_video_slots))
    for item in active_videos:
        seq = int(item.get("slot") or 1)
        conflicts.extend(_description_source_reference_conflicts(f"@video{seq} Keep Out", item.get("keep_out"), active_image_slots, active_video_slots))

    seen = set()
    for (domain, target, scope), entries in groups.items():
        max_rank = max(rank for rank, _token, _label in entries)
        highest = [(token, label) for rank, token, label in entries if rank == max_rank]
        unique_tokens = list(dict.fromkeys(token for token, _label in highest))
        labels = list(dict.fromkeys(label for _token, label in highest))
        if len(unique_tokens) < 2:
            continue
        signature = (tuple(unique_tokens), target, scope, tuple(labels))
        if signature in seen:
            continue
        seen.add(signature)
        conflicts.append(
            f"{', '.join(unique_tokens)} describe overlapping image authority for {target} / "
            f"{' / '.join(labels)} / {scope}; preserve all supplied sources and let the user goal govern "
            "their combination."
        )
    return list(dict.fromkeys(conflicts))

def _picker_input_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "name": PICKER_INPUT_PARAMETER_NAME,
        "tooltip": "Connect HMBVideoPickerLibrary PICKER_OUT to add available video slots, decoded metadata, generated paths, and Asset ID-to-Image Name Color Pick relationships. Other readable connected values are retained as ordinary prompt intent. Every source and every user Target remains independently usable. Missing companions, slots, metadata, Color Picks, or local bindings are optional and never block Prompt output. Explicit Picker companion provenance alone activates cross-file bundle integrity checks.",
        "default_value": "",
        "type": "str",
        "input_types": ["any"],
        "allow_input": True,
        "allow_output": False,
        "allow_property": False,
        "hide_property": True,
        "ui_options": {
            "display_name": "PICKER_IN",
            "compact": True,
            "height": 24,
            "is_full_width": False,
            "hide_property": True,
        },
    }
    if ParameterMode is not None:
        kwargs["allowed_modes"] = {ParameterMode.INPUT}
    return kwargs


def _image_asset_input_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "name": IMAGE_ASSET_INPUT_PARAMETER_NAME,
        "tooltip": (
            "Connect HMBImageAssetLibrary ASSET_OUT. Verified Project "
            "assets provide Main Type, Asset ID, Image Name, a registered Sub Type, "
            "and Color Pick candidates. The registered Sub Type stays bound to the "
            "asset; Target receives a Main-Type default and remains editable. "
            "IMAGE_IMPORT_IN sources provide only Image Name and generator order. "
            "Color Pick and custom ideas remain editable and available to the current goal. "
            "Other readable connected values are retained as ordinary prompt intent."
        ),
        "default_value": "",
        "type": "str",
        "input_types": ["any"],
        "allow_input": True,
        "allow_output": False,
        "allow_property": False,
        "hide_property": True,
        "ui_options": {
            "display_name": IMAGE_ASSET_INPUT_DISPLAY_NAME,
            "compact": True,
            "height": 24,
            "is_full_width": False,
            "hide_property": True,
        },
    }
    if ParameterMode is not None:
        kwargs["allowed_modes"] = {ParameterMode.INPUT}
    return kwargs


def _repair_source_input_parameter(
    node: Any,
    parameter_name: str,
    kwargs: Dict[str, Any],
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
        parameter.type = kwargs["type"]
        parameter.input_types = list(kwargs["input_types"])
    except Exception as exc:
        _diagnostic_exception(f"{parameter_name} input-type repair failed", exc)
    try:
        current_ui = (
            getattr(parameter, "ui_options", None)
            or getattr(parameter, "_ui_options", None)
            or {}
        )
        if not isinstance(current_ui, dict):
            current_ui = {}
        current_ui.update(kwargs["ui_options"])
        current_ui.pop("hide", None)
        current_ui.pop("hide_handles", None)
        parameter.ui_options = current_ui
    except Exception as exc:
        _diagnostic_exception(f"{parameter_name} UI repair failed", exc)


def _repair_picker_input_parameter(node: Any) -> None:
    _repair_source_input_parameter(
        node,
        PICKER_INPUT_PARAMETER_NAME,
        _picker_input_kwargs(),
    )


def _repair_image_asset_input_parameter(node: Any) -> None:
    _repair_source_input_parameter(
        node,
        IMAGE_ASSET_INPUT_PARAMETER_NAME,
        _image_asset_input_kwargs(),
    )


def _add_picker_input(node: Any) -> None:
    if parameter_exists(node, PICKER_INPUT_PARAMETER_NAME):
        _repair_picker_input_parameter(node)
        return
    try:
        _safe_add_parameter(node, **_picker_input_kwargs())
    finally:
        _repair_picker_input_parameter(node)


def _add_image_asset_input(node: Any) -> None:
    if parameter_exists(node, IMAGE_ASSET_INPUT_PARAMETER_NAME):
        _repair_image_asset_input_parameter(node)
        return
    try:
        _safe_add_parameter(node, **_image_asset_input_kwargs())
    finally:
        _repair_image_asset_input_parameter(node)


def _parse_connected_payload(value: Any, source_name: str) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = value.strip() if isinstance(value, str) else _readable_original(value)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        entry = _source_intent_entry(
            source_name,
            "readable non-JSON connected input",
            value,
        )
        return {_UNSTRUCTURED_INPUT_KEY: [entry] if entry else []}
    if isinstance(payload, dict):
        return payload
    entry = _source_intent_entry(
        source_name,
        "readable non-object connected input",
        payload,
    )
    return {_UNSTRUCTURED_INPUT_KEY: [entry] if entry else []}


def _parse_picker_payload(value: Any) -> Dict[str, Any]:
    return _parse_connected_payload(value, PICKER_INPUT_PARAMETER_NAME)


def _parse_image_asset_payload(value: Any) -> Dict[str, Any]:
    return _parse_connected_payload(value, IMAGE_ASSET_INPUT_PARAMETER_NAME)


def _image_asset_selection_id(payload: Dict[str, Any]) -> str:
    selection_id = _clean_string(payload.get("selection_id"))
    if selection_id:
        return selection_id
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except Exception:
        canonical = str(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _image_asset_row_uid(item: Dict[str, Any]) -> str:
    return _clean_string(
        item.get("asset_source_uid")
        or item.get("source_uid")
        or item.get("asset_library_id")
    )


def _has_image_asset_provenance(item: Dict[str, Any]) -> bool:
    try:
        selection_order = int(item.get("asset_selection_order") or 0)
    except Exception:
        selection_order = 0
    return bool(
        item.get("asset_managed")
        or item.get("asset_verified")
        or _clean_string(item.get("asset_source_uid"))
        or _clean_string(item.get("asset_library_id"))
        or _clean_string(item.get("asset_project_uid"))
        or selection_order > 0
    )


def _asset_cache_key(item: Dict[str, Any]) -> str:
    source_uid = _clean_string(
        item.get("asset_source_uid") or item.get("source_uid")
    )
    if source_uid:
        return f"uid:{source_uid}"
    library_id = _clean_string(item.get("asset_library_id"))
    return f"library:{library_id}" if library_id else ""


def _upsert_dormant_asset_row(
    rows: List[Dict[str, Any]],
    item: Dict[str, Any],
) -> None:
    """Store the latest authored row by stable upstream identity."""
    normalized_rows = _normalize_dormant_image_rows([item], asset_rows=True)
    if not normalized_rows:
        return
    row = normalized_rows[0]
    key = _asset_cache_key(row)
    if not key:
        return
    for index, existing in enumerate(rows):
        if _asset_cache_key(existing) == key:
            rows[index] = row
            return
    rows.append(row)
    if len(rows) > MAX_IMAGES * 4:
        del rows[: len(rows) - (MAX_IMAGES * 4)]


def _pop_dormant_asset_row(
    rows: List[Dict[str, Any]],
    source_uid: str,
    library_id: str = "",
) -> Dict[str, Any] | None:
    keys = {f"uid:{source_uid}"} if source_uid else set()
    if library_id:
        keys.add(f"library:{library_id}")
    for index, item in enumerate(rows):
        if _asset_cache_key(item) in keys:
            return rows.pop(index)
    return None


def _manual_cache_rows_from_visible(
    images: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return _normalize_dormant_image_rows(
        [
            item
            for item in images
            if isinstance(item, dict)
            and not bool(item.get("asset_managed"))
            and not _has_image_asset_provenance(item)
        ],
        asset_rows=False,
    )


def _image_asset_order_value(item: Any) -> int:
    if not isinstance(item, dict):
        return MAX_IMAGES + 1
    try:
        order = int(item.get("selection_order") or item.get("slot") or 0)
    except Exception:
        order = 0
    return order if order > 0 else MAX_IMAGES + 1


def _remap_image_source_references(value: Any, slot_map: Dict[int, int]) -> str:
    source = "" if value is None else str(value)
    if not source or not slot_map:
        return source

    def replace(match: re.Match[str]) -> str:
        slot = int(match.group(1))
        if slot not in slot_map:
            return match.group(0)
        next_slot = int(slot_map.get(slot) or 0)
        # A removed row cannot keep its old token: a later row may be promoted
        # into that slot. Preserve the reference as a non-token tombstone so it
        # cannot silently bind to a different source.
        return f"@image{next_slot}" if next_slot > 0 else f"[deselected image source #{slot}]"

    return re.sub(r"@image(\d+)(?!\d)", replace, source, flags=re.IGNORECASE)


def _remap_image_source_references_in_state(
    state: Dict[str, Any],
    slot_map: Dict[int, int],
) -> None:
    if not slot_map:
        return
    text = state.get("text")
    if isinstance(text, dict):
        for key, value in list(text.items()):
            if key == "PRESERVED_TEXT":
                continue
            text[key] = _remap_image_source_references(value, slot_map)
    videos = state.get("videos")
    if isinstance(videos, list):
        for item in videos:
            if isinstance(item, dict):
                item["keep_out"] = _remap_image_source_references(
                    item.get("keep_out"),
                    slot_map,
                )


def _renumber_image_rows(images: Sequence[Dict[str, Any]]) -> None:
    for index, item in enumerate(images, start=1):
        item["slot"] = index
        item["token"] = f"@image{index}"
        item["name"] = _slot_name("IMAGE", index)


def _merge_unstructured_payload_intent(
    state: Dict[str, Any], payload: Any
) -> bool:
    entries = _unstructured_payload_entries(payload)
    for entry in entries:
        _append_source_intent(
            state,
            entry.get("source"),
            entry.get("reason"),
            entry.get("text"),
        )
    return bool(entries)


def _release_image_asset_row_provenance(item: Dict[str, Any]) -> None:
    """Release connection authority while retaining a resumable native row.

    The stable addresses are deliberately kept.  They do not make a row
    upstream-managed while ASSET_IN is absent, but let a later reconnect merge
    edits back into the correct source_uid cache instead of matching by label.
    """
    item["asset_managed"] = False
    item["asset_verified"] = False
    item["asset_source_kind"] = ""
    item["asset_selection_order"] = 0


def _apply_image_asset_payload(
    state: Dict[str, Any],
    payload: Dict[str, Any],
    connected: bool = False,
) -> Dict[str, Any]:
    """Import selected image assets with verified taxonomy authority.

    HMBImageAssetLibrary establishes Project metadata only for verified project
    assets. External IMAGE_IMPORT_IN rows carry Image Name and generator order
    only and otherwise behave like native Prompt rows. A verified registered Sub
    Type is authoritative for its Prompt bindings. Target receives a Main-Type
    default only when it has not been authored and remains freely editable.
    Neither mode writes final Color Pick, video slot, or frame range.
    """
    normalized = _normalize_state(state)
    has_unstructured_input = _merge_unstructured_payload_intent(
        normalized,
        payload,
    )
    if has_unstructured_input and set(payload).issubset({_UNSTRUCTURED_INPUT_KEY}):
        previous = normalized.get("image_asset")
        if isinstance(previous, dict):
            previous["enabled"] = bool(connected or previous.get("enabled"))
        return _normalize_state(normalized)
    mode = (
        _clean_string(payload.get("mode")).lower()
        if isinstance(payload, dict)
        else ""
    )
    schema = (
        _clean_string(payload.get("schema"))
        if isinstance(payload, dict)
        else ""
    )
    payload_has_foreign_identity = bool(
        payload
        and (
            mode not in {"", "image_asset"}
            or schema not in {"", "hmb-image-asset-library-binding"}
        )
    )
    payload_has_asset_identity = bool(
        payload
        and (
            mode == "image_asset"
            or schema == "hmb-image-asset-library-binding"
            or any(key in payload for key in _IMAGE_ASSET_IDENTITY_KEYS)
        )
    )
    if payload and (payload_has_foreign_identity or not payload_has_asset_identity):
        _append_source_intent(
            normalized,
            IMAGE_ASSET_INPUT_PARAMETER_NAME,
            (
                "foreign mode or schema retained as ordinary user intent"
                if payload_has_foreign_identity
                else "readable connected object retained as ordinary user intent"
            ),
            {
                key: value
                for key, value in payload.items()
                if key != _UNSTRUCTURED_INPUT_KEY
            },
        )
        previous = normalized.get("image_asset")
        if isinstance(previous, dict):
            previous["enabled"] = bool(connected or previous.get("enabled"))
        return _normalize_state(normalized)

    if payload_has_asset_identity:
        _append_unconsumed_connected_fields(
            normalized,
            IMAGE_ASSET_INPUT_PARAMETER_NAME,
            payload,
            _IMAGE_ASSET_PAYLOAD_KEYS,
        )

    if not payload:
        previous = (
            normalized.get("image_asset")
            if isinstance(normalized.get("image_asset"), dict)
            else {}
        )
        previous_enabled = bool(previous.get("enabled"))
        images = [
            item
            for item in normalized.get("images", [])
            if isinstance(item, dict)
        ]
        old_rows = list(images)
        manual_cache = _normalize_dormant_image_rows(
            previous.get("dormant_manual_rows"),
            asset_rows=False,
        )
        asset_cache = _normalize_dormant_image_rows(
            previous.get("dormant_asset_rows"),
            asset_rows=True,
        )

        if connected:
            # An edge with no selected payload owns zero active image slots.
            # Snapshot native rows only on the transition into connection mode;
            # the blank row normalized for an empty connected UI is not a new
            # manual row on every refresh.
            visible_manual = _manual_cache_rows_from_visible(images)
            if not previous_enabled or (not manual_cache and visible_manual):
                manual_cache = visible_manual
            for item in images:
                if _has_image_asset_provenance(item):
                    _upsert_dormant_asset_row(asset_cache, item)
            if old_rows:
                _remap_image_source_references_in_state(
                    normalized,
                    {slot: 0 for slot in range(1, len(old_rows) + 1)},
                )
            normalized["images"] = [_default_image_item(1)]
        elif previous_enabled:
            # Restore pre-connection native rows first.  Only assets that were
            # selected at disconnect become native rows; already-deselected
            # upstream rows remain in the source_uid cache for a later reselect.
            selected_rows = [
                item for item in images if bool(item.get("asset_managed"))
            ]
            for item in selected_rows:
                _upsert_dormant_asset_row(asset_cache, item)
            restored = _normalize_dormant_image_rows(
                manual_cache,
                asset_rows=False,
            )
            restored_by_uid: Dict[str, int] = {}
            for item in selected_rows:
                released_rows = _normalize_dormant_image_rows(
                    [item],
                    asset_rows=True,
                )
                if not released_rows:
                    continue
                released = released_rows[0]
                _release_image_asset_row_provenance(released)
                if len(restored) >= MAX_IMAGES:
                    break
                restored.append(released)
                key = _asset_cache_key(item)
                if key:
                    restored_by_uid[key] = len(restored)
            if not restored:
                # Foreign/unstructured connected values never moved the user's
                # rows into the managed cache; preserve those rows verbatim.
                restored = _normalize_dormant_image_rows(
                    images,
                    asset_rows=False,
                )
            slot_map: Dict[int, int] = {}
            for old_slot, item in enumerate(old_rows, start=1):
                key = _asset_cache_key(item)
                slot_map[old_slot] = restored_by_uid.get(key, 0) if key else 0
            if any(
                old_slot != new_slot
                for old_slot, new_slot in slot_map.items()
            ):
                _remap_image_source_references_in_state(normalized, slot_map)
            _renumber_image_rows(restored)
            normalized["images"] = restored or [_default_image_item(1)]
        else:
            # Historical independent mode: no ASSET_IN edge means no row is
            # removed, hidden, reordered, or activated by this synchronization.
            for item in images:
                if bool(item.get("asset_managed")):
                    _upsert_dormant_asset_row(asset_cache, item)
                    _release_image_asset_row_provenance(item)
        normalized["image_asset"] = {
            "enabled": bool(connected),
            "project_id": _clean_string(previous.get("project_id")),
            "project_uid": _clean_string(previous.get("project_uid")),
            "project_root": _clean_string(previous.get("project_root")),
            "selection_id": (
                _clean_string(previous.get("selection_id"))
                if connected
                else ""
            ),
            "selected_assets": 0,
            "verified_assets": 0,
            "imported_images": 0,
            "ordered_source_uids": [],
            "order_managed": bool(connected),
            "dormant_manual_rows": manual_cache,
            "dormant_asset_rows": asset_cache,
        }
        return _normalize_state(normalized)

    raw_assets = (
        payload.get("ordered_images")
        if isinstance(payload.get("ordered_images"), list)
        else payload.get("selected_assets")
        if isinstance(payload.get("selected_assets"), list)
        else payload.get("assets")
        if isinstance(payload.get("assets"), list)
        else []
    )
    if (
        not isinstance(payload.get("ordered_images"), list)
        and isinstance(raw_assets, list)
    ):
        raw_assets = sorted(
            raw_assets,
            key=_image_asset_order_value,
        )
    split_verified_records = (
        payload.get("verified_assets")
        if isinstance(payload.get("verified_assets"), list)
        else None
    )
    for overflow_index, overflow_row in enumerate(
        raw_assets[MAX_IMAGES:],
        start=MAX_IMAGES + 1,
    ):
        _append_source_intent(
            normalized,
            IMAGE_ASSET_INPUT_PARAMETER_NAME,
            (
                f"image row {overflow_index} exceeds the structured "
                f"@image1 through @image{MAX_IMAGES} capacity and remains ordinary intent"
            ),
            overflow_row,
        )
    if split_verified_records is not None:
        for overflow_index, overflow_row in enumerate(
            split_verified_records[MAX_IMAGES:],
            start=MAX_IMAGES + 1,
        ):
            _append_source_intent(
                normalized,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                (
                    f"verified asset row {overflow_index} exceeds the structured "
                    f"@image1 through @image{MAX_IMAGES} capacity and remains ordinary intent"
                ),
                overflow_row,
            )
    _append_unconsumed_connected_rows(
        normalized,
        IMAGE_ASSET_INPUT_PARAMETER_NAME,
        raw_assets,
        _IMAGE_ASSET_ROW_KEYS,
        "image row",
        MAX_IMAGES,
    )
    if split_verified_records is not None:
        _append_unconsumed_connected_rows(
            normalized,
            IMAGE_ASSET_INPUT_PARAMETER_NAME,
            split_verified_records,
            _IMAGE_ASSET_ROW_KEYS,
            "image row",
            MAX_IMAGES,
        )
    verified_by_order_key: Dict[str, Dict[str, Any]] = {}
    verified_by_selection_order: Dict[int, Dict[str, Any]] = {}
    if split_verified_records is not None:
        for verified_index, raw_verified in enumerate(
            split_verified_records[:MAX_IMAGES],
            start=1,
        ):
            if not isinstance(raw_verified, dict):
                _append_source_intent(
                    normalized,
                    IMAGE_ASSET_INPUT_PARAMETER_NAME,
                    f"readable non-object verified asset row {verified_index}",
                    raw_verified,
                )
                continue
            order_key = _clean_string(
                raw_verified.get("order_key")
                or raw_verified.get("source_uid")
            )
            if order_key:
                verified_by_order_key[order_key] = raw_verified
            order = _image_asset_order_value(raw_verified)
            if order <= MAX_IMAGES:
                verified_by_selection_order[order] = raw_verified

    selected_assets: List[Dict[str, Any]] = []
    seen_source_uids: set[str] = set()
    seen_library_ids: set[str] = set()
    project_uid = _clean_string(payload.get("project_uid"))
    for selection_order, raw in enumerate(raw_assets[:MAX_IMAGES], start=1):
        if not isinstance(raw, dict):
            _append_source_intent(
                normalized,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                f"readable non-object image row {selection_order}",
                raw,
            )
            continue
        if raw.get("selected") is False:
            continue
        order_key = _clean_string(
            raw.get("order_key")
            or raw.get("source_uid")
            or raw.get("asset_library_id")
        )
        verified_raw: Dict[str, Any] | None = None
        if split_verified_records is not None:
            verified_raw = (
                verified_by_order_key.get(order_key)
                if order_key
                else None
            )
            if verified_raw is None:
                verified_raw = verified_by_selection_order.get(selection_order)
        else:
            verified_raw = raw

        verified_source_kind = (
            _clean_string(verified_raw.get("source_kind")).casefold()
            if isinstance(verified_raw, dict)
            else ""
        )
        if split_verified_records is not None:
            project_verified = bool(
                isinstance(verified_raw, dict)
                and verified_raw.get("verified_asset") is True
                and verified_source_kind == "project"
                and _clean_string(
                    verified_raw.get("binding_mode") or "verified_asset"
                ).casefold()
                == "verified_asset"
            )
        else:
            # Legacy rich records are accepted only when they explicitly
            # declare project provenance. Missing/unknown kinds fail closed.
            project_verified = bool(
                isinstance(verified_raw, dict)
                and verified_source_kind == "project"
            )

        metadata = verified_raw if project_verified else {}
        asset_path = _clean_string(
            metadata.get("path") or metadata.get("asset_path")
        )
        image_name = _clean_string(
            raw.get("image_name")
            or raw.get("label")
            or metadata.get("image_name")
            or metadata.get("label")
            or (Path(asset_path).stem if asset_path else "")
        )
        asset_id = (
            _clean_string(metadata.get("asset_id"))
            if project_verified
            else ""
        )
        library_id = (
            _clean_string(
                metadata.get("asset_library_id")
                or metadata.get("asset_key")
            )
            if project_verified
            else ""
        )
        if project_verified and (not asset_id or not library_id):
            project_verified = False
            metadata = {}
            asset_id = ""
            library_id = ""
            asset_path = ""
        source_uid = (
            order_key
            or _clean_string(metadata.get("source_uid"))
            or (
                "external:"
                + hashlib.sha256(
                    f"{selection_order}\n{image_name}".encode("utf-8")
                ).hexdigest()[:24]
            )
        )
        if not image_name or not source_uid:
            _append_source_intent(
                normalized,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                f"image row {selection_order} lacks a structured address but remains ordinary intent",
                raw,
            )
            continue
        if (
            source_uid in seen_source_uids
            or (library_id and library_id in seen_library_ids)
        ):
            _append_source_intent(
                normalized,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                f"duplicate image row {selection_order} retained as ordinary intent",
                raw,
            )
            continue
        seen_source_uids.add(source_uid)
        if library_id:
            seen_library_ids.add(library_id)
        source_type = (
            _clean_string(metadata.get("source_type"))
            if project_verified
            else "Role Required / Select Source Type"
        )
        custom_source_type = (
            _clean_string(metadata.get("custom_source_type"))
            if project_verified
            else ""
        )
        if project_verified and source_type and source_type not in IMAGE_SOURCE_TYPE_CHOICES:
            custom_source_type = " | ".join(dict.fromkeys(
                value for value in (source_type, custom_source_type) if value
            ))
            source_type = "Custom"
        elif not project_verified or not source_type:
            source_type = "Role Required / Select Source Type"
        scope_candidate = _clean_string(
            metadata.get("scope_candidate")
            or metadata.get("scope")
            or metadata.get("sub_type")
        )
        allowed_scopes = image_scope_choices_for_source_type(source_type)
        if scope_candidate and scope_candidate not in allowed_scopes:
            _append_source_intent(
                normalized,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                f"custom scope candidate for {image_name}",
                scope_candidate,
            )
        raw_colors = metadata.get("color_pick_candidates")
        if not isinstance(raw_colors, (list, tuple)):
            raw_colors = (
                image_color_pick_choices_for_source_type(source_type)
                if project_verified
                else []
            )
        allowed_colors = image_color_pick_choices_for_source_type(source_type)
        color_candidates = [
            _clean_string(value)
            for value in raw_colors
            if _clean_string(value)
        ]
        for custom_color in color_candidates:
            if custom_color not in allowed_colors:
                _append_source_intent(
                    normalized,
                    IMAGE_ASSET_INPUT_PARAMETER_NAME,
                    f"custom Color Pick candidate for {image_name}",
                    custom_color,
                )
        selected_assets.append(
            {
                "source_uid": source_uid,
                "asset_library_id": library_id,
                "asset_project_uid": (
                    _clean_string(metadata.get("asset_project_uid"))
                    or project_uid
                    if project_verified
                    else ""
                ),
                "asset_id": asset_id,
                "image_name": image_name,
                "asset_path": asset_path,
                "source_type": source_type,
                "custom_source_type": custom_source_type,
                "scope_candidate": scope_candidate,
                "color_pick_candidates": list(dict.fromkeys(color_candidates)),
                "selection_order": selection_order,
                "source_kind": "project" if project_verified else "user",
                "verified": project_verified,
            }
        )

    images = (
        normalized.get("images")
        if isinstance(normalized.get("images"), list)
        else []
    )
    old_rows = list(images)
    previous_asset_state = (
        normalized.get("image_asset")
        if isinstance(normalized.get("image_asset"), dict)
        else {}
    )
    previous_enabled = bool(previous_asset_state.get("enabled"))
    manual_cache = _normalize_dormant_image_rows(
        previous_asset_state.get("dormant_manual_rows"),
        asset_rows=False,
    )
    asset_cache = _normalize_dormant_image_rows(
        previous_asset_state.get("dormant_asset_rows"),
        asset_rows=True,
    )

    visible_manual = _manual_cache_rows_from_visible(images)
    if not previous_enabled:
        # The visible independent rows are canonical on connection entry.  A
        # full cache means even 50 manual rows can sleep while all selected
        # upstream rows receive the generator-aligned token namespace.
        manual_cache = visible_manual
    elif any(_has_image_meaning(item) for item in visible_manual):
        # Migration path for states saved by versions that retained manual rows
        # after the managed rows.  Do not mistake the one normalized blank
        # placeholder of a zero-selection connected state for user content.
        if not manual_cache:
            manual_cache = visible_manual
        else:
            existing_serialized = {
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                for item in manual_cache
            }
            for item in visible_manual:
                serialized = json.dumps(item, ensure_ascii=False, sort_keys=True)
                if serialized not in existing_serialized and len(manual_cache) < MAX_IMAGES:
                    manual_cache.append(item)
                    existing_serialized.add(serialized)

    # Exact source provenance is eligible for upstream reuse.  Native/manual
    # rows are never candidates, including same-label and blank-label rows.
    candidates = [
        item
        for item in images
        if isinstance(item, dict) and _has_image_asset_provenance(item)
    ]
    initial_manual_seeds = [
        item
        for item in images
        if isinstance(item, dict)
        and not _has_image_asset_provenance(item)
        and _has_image_meaning(item)
    ] if not previous_enabled else []
    used_initial_manual_seed_ids: set[int] = set()
    assigned: set[int] = set()
    ordered_managed_rows: List[Dict[str, Any]] = []
    for asset in selected_assets:
        match_index: int | None = None
        for index, item in enumerate(candidates):
            if index in assigned or not isinstance(item, dict):
                continue
            if (
                _image_asset_row_uid(item) == asset["source_uid"]
                or (
                    bool(asset["asset_library_id"])
                    and _clean_string(item.get("asset_library_id"))
                    == asset["asset_library_id"]
                )
            ):
                match_index = index
                break
        if match_index is None:
            for index, item in enumerate(candidates):
                if index in assigned or not isinstance(item, dict):
                    continue
                if not _has_image_asset_provenance(item):
                    continue
                # A stable address belongs to exactly one upstream source.
                # Never relink an addressed dormant/current row by a readable
                # label or Asset ID when a different source_uid arrives.
                if (
                    _image_asset_row_uid(item)
                    or _clean_string(item.get("asset_library_id"))
                ):
                    continue
                row_asset_id = _clean_string(item.get("asset_id"))
                row_label = _clean_string(item.get("label"))
                row_project_uid = _clean_string(item.get("asset_project_uid"))
                same_project = (
                    not project_uid
                    or not row_project_uid
                    or row_project_uid == project_uid
                )
                if (
                    asset["verified"]
                    and same_project
                    and (
                        (
                            bool(asset["asset_id"])
                            and row_asset_id == asset["asset_id"]
                        )
                        or (
                            not row_asset_id
                            and row_label == asset["image_name"]
                        )
                    )
                ):
                    match_index = index
                    break
                if (
                    not asset["verified"]
                    and not bool(item.get("asset_verified"))
                    and row_label == asset["image_name"]
                ):
                    match_index = index
                    break
        if match_index is None:
            cached = _pop_dormant_asset_row(
                asset_cache,
                asset["source_uid"],
                asset["asset_library_id"],
            )
            if cached is not None:
                candidates.append(cached)
                match_index = len(candidates) - 1
        if match_index is None:
            # First connection only: a unique exact native identity may seed
            # the newly managed row, preserving already-authored Role/Target/
            # Color fields.  Later updates never use labels and must resume by
            # source_uid, preventing accidental rebinding after deselection.
            exact_manual_matches = [
                item
                for item in initial_manual_seeds
                if id(item) not in used_initial_manual_seed_ids
                and (
                    _clean_string(item.get("asset_id")) == asset["asset_id"]
                    if _clean_string(item.get("asset_id")) and asset["asset_id"]
                    else _clean_string(item.get("label")) == asset["image_name"]
                )
            ]
            if len(exact_manual_matches) == 1:
                seed = exact_manual_matches[0]
                used_initial_manual_seed_ids.add(id(seed))
                candidates.append(seed)
                match_index = len(candidates) - 1
                normalized_seed_rows = _normalize_dormant_image_rows(
                    [seed],
                    asset_rows=False,
                )
                if normalized_seed_rows:
                    seed_json = json.dumps(
                        normalized_seed_rows[0],
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    for cache_index, cached_manual in enumerate(manual_cache):
                        if json.dumps(
                            cached_manual,
                            ensure_ascii=False,
                            sort_keys=True,
                        ) == seed_json:
                            manual_cache.pop(cache_index)
                            break
        if match_index is None:
            cached = _default_image_item(len(candidates) + 1)
            candidates.append(cached)
            match_index = len(candidates) - 1

        item = candidates[match_index]
        previous_asset_default_target = _clean_string(
            item.get("asset_default_target")
        )
        assigned.add(match_index)
        # Remove an older cached snapshot when the visible/resumable row won.
        _pop_dormant_asset_row(
            asset_cache,
            asset["source_uid"],
            asset["asset_library_id"],
        )
        ordered_managed_rows.append(item)
        item["present"] = True
        if not _clean_string(item.get("label")):
            item["label"] = asset["image_name"]
        item["asset_source_uid"] = asset["source_uid"]
        item["asset_selection_order"] = asset["selection_order"]
        item["asset_managed"] = True
        item["asset_verified"] = bool(asset["verified"])
        item["asset_source_kind"] = asset["source_kind"]
        if asset["verified"]:
            item["asset_id"] = asset["asset_id"]
            item["asset_path"] = asset["asset_path"]
            item["asset_library_id"] = asset["asset_library_id"]
            item["asset_project_uid"] = asset["asset_project_uid"]
            item["asset_source_type_candidate"] = asset["source_type"]
            item["asset_scope_candidate"] = asset["scope_candidate"]
            item["asset_color_pick_candidates"] = asset["color_pick_candidates"]
            item["source_type"] = asset["source_type"]
            item["custom_source_type"] = asset["custom_source_type"]
            default_target = _default_image_target_for_main_type(
                item.get("source_type"),
                asset.get("image_name"),
                asset.get("asset_id"),
            )
            current_target = _clean_string(item.get("owner"))
            if (
                (not current_target and not previous_asset_default_target)
                or (
                    previous_asset_default_target
                    and current_target == previous_asset_default_target
                )
            ):
                item["owner"] = default_target
            item["asset_default_target"] = default_target
            _normalize_image_binding_fields(item, MAX_VIDEOS)
        else:
            # External/imported selection contributes its readable name/order.
            # It never erases an existing Asset ID/path note, candidate, or user
            # role merely because project verification is not supplied.
            pass

    # Deselecting does not destroy authored fields.  It moves the complete row
    # out of the active token namespace and indexes it by source_uid for a later
    # reselect.  While connected, *only* the ordered selected rows stay visible
    # and active, so Prompt @imageN is identical to generator fan-out order.
    for index, item in enumerate(candidates):
        if index not in assigned:
            _upsert_dormant_asset_row(asset_cache, item)
    images = ordered_managed_rows[:MAX_IMAGES]
    if not images:
        images = [_default_image_item(1)]

    new_slots_by_object = {
        id(item): index
        for index, item in enumerate(images, start=1)
    }
    slot_map = {
        old_slot: new_slots_by_object.get(id(item), 0)
        for old_slot, item in enumerate(old_rows, start=1)
    }
    if any(old_slot != new_slot for old_slot, new_slot in slot_map.items()):
        _remap_image_source_references_in_state(normalized, slot_map)
    _renumber_image_rows(images)
    normalized["images"] = images
    normalized["image_asset"] = {
        "enabled": bool(connected),
        "project_id": _clean_string(payload.get("project_id")),
        "project_uid": project_uid,
        "project_root": _clean_string(payload.get("project_root")),
        "selection_id": _image_asset_selection_id(payload),
        "selected_assets": len(selected_assets),
        "verified_assets": sum(
            1 for asset in selected_assets if asset["verified"]
        ),
        "imported_images": sum(
            1 for asset in selected_assets if not asset["verified"]
        ),
        "ordered_source_uids": [
            asset["source_uid"] for asset in selected_assets
        ],
        "order_managed": True,
        "dormant_manual_rows": manual_cache,
        "dormant_asset_rows": asset_cache,
    }
    return _normalize_state(normalized)


def _picker_payload_id(payload: Dict[str, Any]) -> str:
    run_id = _clean_string(payload.get("run_id"))
    if run_id:
        return run_id
    try:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        canonical = str(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _picker_video_uid(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return _clean_string(item.get("video_uid") or item.get("source_uid"))


def _picker_video_order_value(item: Any, fallback: int) -> int:
    if not isinstance(item, dict):
        return fallback
    try:
        value = int(item.get("selection_order") or item.get("video_slot") or fallback)
    except Exception:
        value = fallback
    return value if value > 0 else fallback


def _canonical_uid_picker_video_rows(value: Any) -> tuple[List[Any], bool]:
    """Derive transient slots from stable-UID selection order.

    A legacy payload with no UID is returned byte-for-byte in its original row
    order. Once any selected row carries a UID, all UID rows are sorted by
    ``selection_order`` (with input order as the stable tie breaker) and receive
    the contiguous ``@video1..N`` addresses consumed by Prompt and Generator.
    """
    raw_rows = list(value) if isinstance(value, list) else []
    uid_managed = any(_picker_video_uid(row) for row in raw_rows)
    if not uid_managed:
        return raw_rows, False
    object_rows = [
        (index, row)
        for index, row in enumerate(raw_rows, start=1)
        if isinstance(row, dict)
    ]
    object_rows.sort(
        key=lambda entry: (
            _picker_video_order_value(entry[1], entry[0]),
            entry[0],
        )
    )
    original_uid_by_slot: Dict[int, str] = {}
    for fallback, (_, raw) in enumerate(object_rows, start=1):
        uid = _picker_video_uid(raw)
        if not uid:
            continue
        try:
            original_slot = int(raw.get("video_slot") or fallback)
        except Exception:
            original_slot = fallback
        if original_slot > 0:
            original_uid_by_slot[original_slot] = uid
    transient_slot_by_uid = {
        _picker_video_uid(raw): slot
        for slot, (_, raw) in enumerate(object_rows, start=1)
        if _picker_video_uid(raw)
    }
    ordered: List[Any] = []
    for transient_slot, (_, raw) in enumerate(object_rows, start=1):
        row = dict(raw)
        uid = _picker_video_uid(row)
        if uid:
            row["video_uid"] = uid
            row["source_uid"] = uid
            row["selection_order"] = transient_slot
            row["order_key"] = _clean_string(row.get("order_key")) or uid
            row["video_slot"] = transient_slot
            source_uid = _clean_string(
                row.get("source_video_uid")
                or row.get("companion_of_video_uid")
                or row.get("companion_video_uid")
            )
            explicit_source_fields = [
                key
                for key in ("source_video_slot", "companion_of_video_slot")
                if key in row and row.get(key) not in (None, "")
            ]
            declared_source_slot = 0
            if not source_uid:
                for source_slot_key in explicit_source_fields:
                    try:
                        old_source_slot = int(row.get(source_slot_key))
                    except Exception:
                        continue
                    declared_source_slot = old_source_slot
                    source_uid = original_uid_by_slot.get(old_source_slot, "")
                    if source_uid:
                        break
            if source_uid and source_uid in transient_slot_by_uid:
                source_slot = transient_slot_by_uid[source_uid]
                row["source_video_uid"] = source_uid
                row["companion_of_video_uid"] = source_uid
                if "source_video_slot" in row:
                    row["source_video_slot"] = source_slot
                if "companion_of_video_slot" in row:
                    row["companion_of_video_slot"] = source_slot
            elif source_uid or declared_source_slot > 0:
                # A companion source outside the selected list must not retain
                # a stale number that can now identify a different video.
                for source_slot_key in explicit_source_fields:
                    row[source_slot_key] = -1
        ordered.append(row)
    ordered.extend(row for row in raw_rows if not isinstance(row, dict))
    return ordered, True


def _remap_video_source_references(value: Any, slot_map: Dict[int, int]) -> str:
    source = "" if value is None else str(value)
    if not source or not slot_map:
        return source

    def replace(match: re.Match[str]) -> str:
        slot = int(match.group(1))
        if slot not in slot_map:
            return match.group(0)
        next_slot = int(slot_map.get(slot) or 0)
        return (
            f"@video{next_slot}"
            if next_slot > 0
            else f"[deselected video source #{slot}]"
        )

    return re.sub(r"@video(\d+)(?!\d)", replace, source, flags=re.IGNORECASE)


def _remap_video_slots_in_image(item: Dict[str, Any], slot_map: Dict[int, int]) -> None:
    if not slot_map:
        return
    _normalize_image_binding_fields(item, MAX_VIDEOS)
    picks = list(item.get("color_picks", [""]))
    scopes = list(item.get("binding_scopes", [""]))
    custom_scopes = list(item.get("binding_custom_scopes", [""]))
    slots = list(item.get("binding_video_slots", [1]))
    for index, old_slot in enumerate(slots):
        if old_slot not in slot_map:
            continue
        next_slot = int(slot_map.get(old_slot) or 0)
        if next_slot > 0:
            slots[index] = next_slot
        else:
            # A deselected source cannot leave an address that silently binds
            # the Color Pick to a different video promoted into that slot.
            picks[index] = ""
            slots[index] = 1
    item["color_picks"] = picks
    item["binding_scopes"] = scopes
    item["binding_custom_scopes"] = custom_scopes
    item["binding_video_slots"] = slots
    item["marker_video"] = slots[0] if slots else 1
    item["preview_marker"] = _remap_video_source_references(
        item.get("preview_marker"),
        slot_map,
    )
    try:
        old_auto_slot = int(item.get("picker_auto_video") or 0)
    except Exception:
        old_auto_slot = 0
    if old_auto_slot in slot_map:
        next_auto_slot = int(slot_map.get(old_auto_slot) or 0)
        item["picker_auto_video"] = next_auto_slot
        if next_auto_slot <= 0:
            item["picker_auto_color"] = ""
            item["picker_auto_source"] = ""

    bindings = _normalize_frame_range_bindings(
        item.get("frame_range_bindings"),
        item.get("frame_range_binding"),
    )
    remapped_bindings: Dict[str, Dict[str, Any]] = {}
    for binding in bindings.values():
        old_slot = _video_slot_number(binding.get("video_slot"), MAX_VIDEOS)
        next_slot = int(slot_map.get(old_slot, old_slot) or 0)
        if next_slot <= 0:
            continue
        next_binding = dict(binding)
        next_binding["video_slot"] = f"@video{next_slot}"
        color = _clean_string(next_binding.get("color_pick"))
        remapped_bindings[_frame_binding_key(next_slot, color)] = next_binding
    item["frame_range_bindings"] = remapped_bindings
    item["frame_range_binding"] = None
    if not remapped_bindings:
        item["frame_range_enabled"] = False
        item["frame_range_selected_index"] = -1


def _remap_video_source_references_in_state(
    state: Dict[str, Any],
    slot_map: Dict[int, int],
) -> None:
    if not slot_map:
        return
    text = state.get("text")
    if isinstance(text, dict):
        for key, value in list(text.items()):
            if key == "PRESERVED_TEXT":
                continue
            text[key] = _remap_video_source_references(value, slot_map)
    videos = state.get("videos")
    if isinstance(videos, list):
        for item in videos:
            if isinstance(item, dict):
                item["keep_out"] = _remap_video_source_references(
                    item.get("keep_out"),
                    slot_map,
                )
    images = state.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict):
                _remap_video_slots_in_image(item, slot_map)
    ui = state.get("ui")
    textarea_heights = ui.get("textarea_heights") if isinstance(ui, dict) else None
    if isinstance(textarea_heights, dict):
        remapped_heights: Dict[str, Any] = {}
        for key, height in textarea_heights.items():
            match = re.fullmatch(r"video:(\d+):keep_out", _clean_string(key))
            if match is None:
                remapped_heights[key] = height
                continue
            old_slot = int(match.group(1))
            next_slot = int(slot_map.get(old_slot, old_slot) or 0)
            if next_slot > 0:
                remapped_heights[f"video:{next_slot}:keep_out"] = height
        ui["textarea_heights"] = remapped_heights


def _upsert_dormant_video_row(
    rows: List[Dict[str, Any]],
    item: Dict[str, Any],
) -> None:
    uid = _picker_video_uid(item)
    if not uid:
        return
    row = _migrate_old_video_item(item, len(rows) + 1)
    row["video_uid"] = uid
    row["source_uid"] = uid
    row["selection_order"] = 0
    row["order_key"] = uid
    row["picker_managed"] = True
    row["slot"] = 0
    row["token"] = ""
    row["name"] = ""
    for index, existing in enumerate(rows):
        if _picker_video_uid(existing) == uid:
            rows[index] = row
            return
    rows.append(row)


def _prepare_uid_managed_video_rows(
    state: Dict[str, Any],
    payload_videos: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Merge selected Picker rows by UID and derive their transient slots."""
    picker = state.get("picker") if isinstance(state.get("picker"), dict) else {}
    old_rows = [
        item
        for item in state.get("videos", [])
        if isinstance(item, dict)
    ] if isinstance(state.get("videos"), list) else []
    dormant = _normalize_dormant_video_rows(
        picker.get("dormant_video_rows"),
        managed=True,
    )
    manual_cache = _normalize_dormant_video_rows(
        picker.get("dormant_manual_rows"),
        managed=False,
    )
    candidates_by_uid: Dict[str, Dict[str, Any]] = {}
    for item in [*dormant, *old_rows]:
        uid = _picker_video_uid(item)
        if uid:
            candidates_by_uid[uid] = item

    previously_uid_managed = bool(picker.get("order_managed"))
    used_old_row_ids: set[int] = set()
    new_slot_by_old_row_id: Dict[int, int] = {}
    selected_rows: List[Dict[str, Any]] = []
    for slot, payload_row in enumerate(payload_videos, start=1):
        uid = _picker_video_uid(payload_row)
        if not uid:
            continue
        previous = candidates_by_uid.pop(uid, None)
        if previous is None and not previously_uid_managed and slot <= len(old_rows):
            positional = old_rows[slot - 1]
            if not _picker_video_uid(positional):
                previous = positional
        if previous is None:
            row = _default_video_item(slot)
        else:
            used_old_row_ids.add(id(previous))
            new_slot_by_old_row_id[id(previous)] = slot
            row = _migrate_old_video_item(previous, slot)
        row["slot"] = slot
        row["token"] = f"@video{slot}"
        row["name"] = _slot_name("VIDEO", slot)
        row["video_uid"] = uid
        row["source_uid"] = uid
        row["selection_order"] = slot
        row["order_key"] = _clean_string(payload_row.get("order_key")) or uid
        row["picker_managed"] = True
        row["manual"] = True
        selected_rows.append(row)

    selected_uids = {_picker_video_uid(item) for item in selected_rows}
    dormant_out: List[Dict[str, Any]] = []
    for item in [*dormant, *old_rows]:
        uid = _picker_video_uid(item)
        if uid and uid not in selected_uids:
            _upsert_dormant_video_row(dormant_out, item)
        elif not uid and id(item) not in used_old_row_ids:
            manual_cache.append(_migrate_old_video_item(item, len(manual_cache) + 1))

    new_slot_by_uid = {
        _picker_video_uid(item): slot
        for slot, item in enumerate(selected_rows, start=1)
    }
    slot_map: Dict[int, int] = {}
    for old_slot, item in enumerate(old_rows, start=1):
        uid = _picker_video_uid(item)
        if uid:
            slot_map[old_slot] = new_slot_by_uid.get(uid, 0)
        elif id(item) in used_old_row_ids:
            slot_map[old_slot] = new_slot_by_old_row_id.get(id(item), old_slot)
        else:
            slot_map[old_slot] = 0
    if any(old != new for old, new in slot_map.items()):
        _remap_video_source_references_in_state(state, slot_map)
        for item in selected_rows:
            item["keep_out"] = _remap_video_source_references(
                item.get("keep_out"),
                slot_map,
            )
    return selected_rows, dormant_out, manual_cache


_PICKER_AUTO_DEPTH_FIELDS = (
    "label",
    "present",
    "source_type",
    "custom_source_type",
    "control_role",
    "custom_control_role",
    "picker_auto_label",
)


def _picker_auto_depth_field_value(field: str, value: Any) -> Any:
    if field == "present":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return _clean_string(value).casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }
    return _clean_string(value)


def _normalize_picker_auto_depth(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    raw_fields = value.get("fields")
    if not isinstance(raw_fields, dict):
        return {}
    fields: Dict[str, Dict[str, Any]] = {}
    for field in _PICKER_AUTO_DEPTH_FIELDS:
        entry = raw_fields.get(field)
        if not isinstance(entry, dict) or "assigned" not in entry or "previous" not in entry:
            continue
        fields[field] = {
            "assigned": _picker_auto_depth_field_value(
                field,
                entry.get("assigned"),
            ),
            "previous": _picker_auto_depth_field_value(
                field,
                entry.get("previous"),
            ),
        }
    if not fields:
        return {}
    return {
        "pair_run_id": _clean_string(value.get("pair_run_id")),
        "fields": fields,
    }


def _picker_video_claims_generated_depth(item: Any, slot: int) -> bool:
    if not isinstance(item, dict) or int(slot or 0) not in range(1, MAX_VIDEOS + 1):
        return False
    media_kind = re.sub(
        r"[^a-z0-9]+",
        "_",
        _clean_string(item.get("media_kind")).casefold(),
    ).strip("_")
    if media_kind == "maya_depth_playblast":
        return True
    source_type_hint = _clean_string(item.get("source_type_hint"))
    control_role_hint = _canonical_video_role(item.get("control_role_hint"))
    source_slot_value = (
        item.get("source_video_slot")
        if item.get("source_video_slot") not in (None, "")
        else item.get("companion_of_video_slot")
    )
    if source_slot_value in (None, ""):
        return False
    return (
        source_type_hint == "Depth / Spatial Reference"
        and control_role_hint == "Spatial Alignment Verification Only"
        and _picker_companion_source_slot(item) in range(1, MAX_VIDEOS + 1)
    )


def _picker_companion_source_slot(item: Any) -> int:
    """Return a Picker companion source slot without coercing zero to one.

    Prompt's ordinary video-slot normalizer deliberately maps an empty/zero
    address to ``@video1``. Packed Picker provenance uses an explicit zero to
    mean that a selected Depth or Motion Guide was published without a Mask.
    A missing source field is incomplete provenance, so companion validation
    needs a lossless source address instead.
    """

    if not isinstance(item, dict):
        return -1
    source_is_explicit = (
        "source_video_slot" in item
        and item.get("source_video_slot") not in (None, "")
    )
    companion_is_explicit = (
        "companion_of_video_slot" in item
        and item.get("companion_of_video_slot") not in (None, "")
    )
    if not source_is_explicit and not companion_is_explicit:
        return -1

    def parse_slot(value: Any) -> int:
        text = _clean_string(value)
        match = re.fullmatch(
            r"(?:@?video)?\s*([0-9]+)",
            text,
            re.IGNORECASE,
        )
        try:
            parsed = int(match.group(1) if match is not None else value)
        except Exception:
            return -1
        return parsed if parsed in range(0, MAX_VIDEOS + 1) else -1

    source_slot = (
        parse_slot(item.get("source_video_slot"))
        if source_is_explicit
        else -1
    )
    companion_slot = (
        parse_slot(item.get("companion_of_video_slot"))
        if companion_is_explicit
        else -1
    )
    if source_is_explicit and companion_is_explicit:
        return source_slot if source_slot == companion_slot else -1
    return source_slot if source_is_explicit else companion_slot


def _picker_video_is_generated_depth(
    item: Any,
    slot: int,
    source_pair_run_id: str = "",
) -> bool:
    """Recognize a validated Picker relative-depth output.

    A companion linked to a Mask must carry the Mask source's non-empty
    pair/bundle identity.  A packed standalone Depth row uses source slot zero
    and is authoritative from its own non-empty identity.  The caller resolves
    whether a non-zero source is an actual Mask; retaining the string argument
    keeps the legacy ``@video1`` Color bundle API compatible.
    ``media_kind`` is the primary discriminator.  The exact source/role hints
    plus a source-slot link are accepted as a compatibility shape.  The
    declared media type is honored in whichever valid Prompt video slot the
    Picker supplies; Prompt does not reserve a slot for a creative role.
    """
    if not _picker_video_claims_generated_depth(item, slot):
        return False
    source_slot = _picker_companion_source_slot(item)
    depth_pair_run_id = _clean_string(
        item.get("bundle_run_id") or item.get("pair_run_id")
    )
    expected_pair_run_id = _clean_string(source_pair_run_id)
    if source_slot < 0 or not depth_pair_run_id:
        return False
    if source_slot > 0 and (
        not expected_pair_run_id
        or depth_pair_run_id != expected_pair_run_id
    ):
        return False
    return bool(
        _clean_string(item.get("media_kind")) == "maya_depth_playblast"
        and _clean_string(item.get("video_role")) == "maya_depth_companion"
        and _clean_string(item.get("depth_profile"))
        == PICKER_DEPTH_PROFILE
    )


def _normalize_picker_auto_motion_guide(value: Any) -> Dict[str, Any]:
    normalized = _normalize_picker_auto_depth(value)
    if not normalized:
        return {}
    return {
        "bundle_run_id": _clean_string(
            value.get("bundle_run_id") or value.get("pair_run_id")
        ),
        "fields": normalized["fields"],
    }


def _normalize_picker_motion_guide_summary(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    profile = _clean_string(value.get("profile"))
    if profile not in PICKER_MOTION_GUIDE_PROFILES:
        return {}

    def bounded_count(field: str) -> int:
        try:
            return max(0, int(value.get(field) or 0))
        except Exception:
            return 0

    groups = sorted({
        _clean_string(item)
        for item in value.get("semantic_groups", [])
        if _clean_string(item) in {"brow", "eyelid", "mouth", "jaw"}
    }) if isinstance(value.get("semantic_groups"), list) else []
    return {
        "profile": profile,
        "semantic_face": bool(value.get("semantic_face")),
        "target_count": bounded_count("target_count"),
        "channel_count": bounded_count("channel_count"),
        "driver_count": bounded_count("driver_count"),
        "landmark_count": bounded_count("landmark_count"),
        "rasterized_sample_count": bounded_count("rasterized_sample_count"),
        "hidden_or_occluded_sample_count": bounded_count(
            "hidden_or_occluded_sample_count"
        ),
        "semantic_groups": groups,
        "final_blendshape_values_in_sidecar": bool(
            value.get("final_blendshape_values_in_sidecar")
        ),
        "raw_curve_geometry_rendered": False,
    }


def _picker_motion_guide_summary(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    profile = _clean_string(item.get("motion_guide_profile"))
    if profile not in PICKER_MOTION_GUIDE_PROFILES:
        return {}
    report = (
        item.get("motion_guide_report")
        if isinstance(item.get("motion_guide_report"), dict)
        else {}
    )
    face = (
        report.get("face_semantics")
        if isinstance(report.get("face_semantics"), dict)
        else {}
    )

    def safe_count(field: str) -> int:
        try:
            return max(0, int(face.get(field) or 0))
        except Exception:
            return 0

    allowed_groups = {"brow", "eyelid", "mouth", "jaw"}
    groups = {
        _clean_string(group)
        for group in (
            report.get("semantic_groups")
            if isinstance(report.get("semantic_groups"), list)
            else []
        )
        if _clean_string(group) in allowed_groups
    }
    targets = report.get("targets")
    if isinstance(targets, list):
        for target in targets:
            if isinstance(target, dict):
                groups.update(
                    _clean_string(group)
                    for group in (
                        target.get("semantic_groups")
                        if isinstance(target.get("semantic_groups"), list)
                        else []
                    )
                    if _clean_string(group) in allowed_groups
                )
            channels = (
                target.get("face_channels")
                if isinstance(target, dict)
                and isinstance(target.get("face_channels"), list)
                else []
            )
            for channel in channels:
                group = (
                    _clean_string(channel.get("group"))
                    if isinstance(channel, dict)
                    else ""
                )
                if group in allowed_groups:
                    groups.add(group)
    try:
        face_schema_version = int(face.get("schema_version") or 0)
    except Exception:
        face_schema_version = 0
    semantic_face = bool(
        profile == PICKER_MOTION_GUIDE_PROFILE
        and _clean_string(face.get("schema")) == "hmb-maya-face-semantics"
        and face_schema_version == 2
        and _clean_string(face.get("channel_source_policy"))
        == "final_evaluated_blendshape_weight_raw_value"
        and _clean_string(face.get("controller_policy"))
        == "connected_numeric_nurbs_curve_controller_plug_raw_value_provenance_only"
        and _clean_string(face.get("raster_policy"))
        == (
            "surface_pinned_brow_eyelid_mouth_jaw_landmarks_only;"
            "raw_nurbs_curve_geometry_never_rendered"
        )
        and _clean_string(face.get("visibility_policy"))
        == "front_facing_vertex_normal_plus_camera_ray_first_hit_visible_only"
        and face.get("curve_geometry_rendered") is False
    )
    return _normalize_picker_motion_guide_summary({
        "profile": profile,
        "semantic_face": semantic_face,
        "target_count": safe_count("target_count"),
        "channel_count": safe_count("channel_count"),
        "driver_count": safe_count("driver_count"),
        "landmark_count": safe_count("landmark_count"),
        "rasterized_sample_count": safe_count("rasterized_sample_count"),
        "hidden_or_occluded_sample_count": safe_count(
            "hidden_or_occluded_sample_count"
        ),
        "semantic_groups": sorted(groups),
        "final_blendshape_values_in_sidecar": semantic_face,
        "raw_curve_geometry_rendered": False,
    })


def _picker_video_claims_generated_motion_guide(
    item: Any,
    slot: int,
) -> bool:
    if not isinstance(item, dict) or int(slot or 0) not in range(1, MAX_VIDEOS + 1):
        return False
    media_kind = re.sub(
        r"[^a-z0-9]+",
        "_",
        _clean_string(item.get("media_kind")).casefold(),
    ).strip("_")
    if media_kind == "maya_motion_guide":
        return True
    source_slot_value = (
        item.get("source_video_slot")
        if item.get("source_video_slot") not in (None, "")
        else item.get("companion_of_video_slot")
    )
    return (
        _clean_string(item.get("source_type_hint"))
        == "Motion Guide / Retargeting Reference"
        and _canonical_video_role(item.get("control_role_hint"))
        == "Derived Motion Decoding Only"
        and _picker_companion_source_slot(item) in range(1, MAX_VIDEOS + 1)
    )


def _picker_video_is_generated_motion_guide(
    item: Any,
    slot: int,
    source_bundle_run_id: str = "",
) -> bool:
    if not _picker_video_claims_generated_motion_guide(item, slot):
        return False
    source_slot = _picker_companion_source_slot(item)
    item_bundle_run_id = _clean_string(item.get("bundle_run_id"))
    expected_bundle_run_id = _clean_string(source_bundle_run_id)
    return bool(
        source_slot >= 0
        and item_bundle_run_id
        and (
            source_slot == 0
            or (
                expected_bundle_run_id
                and item_bundle_run_id == expected_bundle_run_id
            )
        )
        and _clean_string(item.get("media_kind")) == "maya_motion_guide"
        and _clean_string(item.get("video_role"))
        == "maya_motion_guide_companion"
        and _clean_string(item.get("motion_guide_profile"))
        in PICKER_MOTION_GUIDE_PROFILES
    )


def _assign_picker_generated_motion_guide(
    item: Dict[str, Any],
    bundle_run_id: str,
    assigned_values: Dict[str, Any],
) -> None:
    previous_auto = _normalize_picker_auto_motion_guide(
        item.get("picker_auto_motion_guide")
    )
    previous_fields = previous_auto.get("fields", {})
    next_fields: Dict[str, Dict[str, Any]] = {}
    for field, raw_assigned in assigned_values.items():
        if field not in _PICKER_AUTO_DEPTH_FIELDS:
            continue
        current = _picker_auto_depth_field_value(field, item.get(field))
        assigned = _picker_auto_depth_field_value(field, raw_assigned)
        previous_entry = previous_fields.get(field)
        if (
            isinstance(previous_entry, dict)
            and current
            == _picker_auto_depth_field_value(
                field,
                previous_entry.get("assigned"),
            )
        ):
            previous = _picker_auto_depth_field_value(
                field,
                previous_entry.get("previous"),
            )
        else:
            previous = current
        item[field] = assigned
        next_fields[field] = {
            "assigned": assigned,
            "previous": previous,
        }
    item["picker_auto_motion_guide"] = {
        "bundle_run_id": _clean_string(bundle_run_id),
        "fields": next_fields,
    }


def _release_picker_generated_motion_guide(
    item: Dict[str, Any],
) -> bool:
    had_summary = bool(
        _normalize_picker_motion_guide_summary(
            item.get("picker_motion_guide_summary")
        )
    )
    previous_auto = _normalize_picker_auto_motion_guide(
        item.get("picker_auto_motion_guide")
    )
    if not previous_auto:
        item["picker_auto_motion_guide"] = {}
        item["picker_motion_guide_summary"] = {}
        return had_summary
    for field, entry in previous_auto.get("fields", {}).items():
        current = _picker_auto_depth_field_value(field, item.get(field))
        assigned = _picker_auto_depth_field_value(
            field,
            entry.get("assigned"),
        )
        if current == assigned:
            item[field] = _picker_auto_depth_field_value(
                field,
                entry.get("previous"),
            )
    item["picker_auto_motion_guide"] = {}
    item["picker_motion_guide_summary"] = {}
    return True


def _invalidate_picker_generated_motion_guide(
    item: Dict[str, Any],
) -> bool:
    if _release_picker_generated_motion_guide(item):
        return True
    auto_label = _clean_string(item.get("picker_auto_label"))
    if (
        auto_label
        and _clean_string(item.get("label")) == auto_label
        and _clean_string(item.get("source_type"))
        == "Motion Guide / Retargeting Reference"
        and _canonical_video_role(item.get("control_role"))
        == "Derived Motion Decoding Only"
        and not _clean_string(item.get("custom_source_type"))
        and not _clean_string(item.get("custom_control_role"))
    ):
        item["label"] = ""
        item["present"] = False
        item["source_type"] = "Role Required / Select Video Type"
        item["custom_source_type"] = ""
        item["control_role"] = ""
        item["custom_control_role"] = ""
        item["picker_auto_label"] = ""
        return True
    return False


def _assign_picker_generated_depth(
    item: Dict[str, Any],
    pair_run_id: str,
    assigned_values: Dict[str, Any],
) -> None:
    previous_auto = _normalize_picker_auto_depth(
        item.get("picker_auto_depth")
    )
    previous_fields = previous_auto.get("fields", {})
    next_fields: Dict[str, Dict[str, Any]] = {}
    for field, raw_assigned in assigned_values.items():
        if field not in _PICKER_AUTO_DEPTH_FIELDS:
            continue
        current = _picker_auto_depth_field_value(field, item.get(field))
        assigned = _picker_auto_depth_field_value(field, raw_assigned)
        previous_entry = previous_fields.get(field)
        if (
            isinstance(previous_entry, dict)
            and current
            == _picker_auto_depth_field_value(
                field,
                previous_entry.get("assigned"),
            )
        ):
            previous = _picker_auto_depth_field_value(
                field,
                previous_entry.get("previous"),
            )
        else:
            previous = current
        item[field] = assigned
        next_fields[field] = {
            "assigned": assigned,
            "previous": previous,
        }
    item["picker_auto_depth"] = {
        "pair_run_id": _clean_string(pair_run_id),
        "fields": next_fields,
    }


def _release_picker_generated_depth(item: Dict[str, Any]) -> bool:
    previous_auto = _normalize_picker_auto_depth(
        item.get("picker_auto_depth")
    )
    if not previous_auto:
        item["picker_auto_depth"] = {}
        return False
    for field, entry in previous_auto.get("fields", {}).items():
        current = _picker_auto_depth_field_value(field, item.get(field))
        assigned = _picker_auto_depth_field_value(
            field,
            entry.get("assigned"),
        )
        if current == assigned:
            item[field] = _picker_auto_depth_field_value(
                field,
                entry.get("previous"),
            )
    item["picker_auto_depth"] = {}
    return True


def _invalidate_picker_generated_depth(item: Dict[str, Any]) -> bool:
    """Release tracked Depth automation or deactivate an untracked legacy row."""
    if _release_picker_generated_depth(item):
        return True
    auto_label = _clean_string(item.get("picker_auto_label"))
    if (
        auto_label
        and _clean_string(item.get("label")) == auto_label
        and _clean_string(item.get("source_type"))
        == "Depth / Spatial Reference"
        and _canonical_video_role(item.get("control_role"))
        == "Spatial Alignment Verification Only"
        and not _clean_string(item.get("custom_source_type"))
        and not _clean_string(item.get("custom_control_role"))
    ):
        item["label"] = ""
        item["present"] = False
        item["source_type"] = "Role Required / Select Video Type"
        item["custom_source_type"] = ""
        item["control_role"] = ""
        item["custom_control_role"] = ""
        item["picker_auto_label"] = ""
        return True
    return False


def _clear_image_bindings_for_generated_depth(
    images: List[Dict[str, Any]],
    depth_slots: set[int],
    video_count: int,
) -> None:
    """Compatibility hook that preserves every user-authored image binding.

    A generated typed source may change how a binding is interpreted, but a
    connection is additive and cannot erase Color Picks, local bindings, or
    optional frame ranges. Invalid or unsuitable bindings are reported as
    non-blocking notes by Prompt compilation and remain editable by the user.
    """
    return


def _picker_match_candidates(images: List[Dict[str, Any]], marker: Dict[str, Any], assigned: set[int]) -> List[int]:
    asset_id = _clean_string(marker.get("asset_id"))
    if not asset_id:
        return []
    return [
        index
        for index, item in enumerate(images)
        if (
            index not in assigned
            and (
                _clean_string(item.get("asset_id")) == asset_id
                or (
                    not _clean_string(item.get("asset_id"))
                    and not _clean_string(item.get("asset_source_uid"))
                    and not bool(item.get("asset_managed"))
                    and _clean_string(item.get("label")) == asset_id
                )
            )
        )
    ]


def _picker_video_has_media(value: Any) -> bool:
    """Return whether a PICKER_OUT video row names concrete media.

    Picker UI slot rows can exist before Maya/FFmpeg has produced anything.
    Those rows are configuration placeholders and must never activate Prompt
    @video slots.
    """
    return bool(
        isinstance(value, dict)
        and _clean_string(value.get("video_path") or value.get("video"))
    )


def _picker_video_is_mask_bundle_source(item: Any, slot: int) -> bool:
    """Recognize a packed Mask or the untyped legacy @video1 Color source."""

    if not isinstance(item, dict):
        return False
    media_kind = re.sub(
        r"[^a-z0-9]+",
        "_",
        _clean_string(item.get("media_kind")).casefold(),
    ).strip("_")
    video_role = re.sub(
        r"[^a-z0-9]+",
        "_",
        _clean_string(item.get("video_role")).casefold(),
    ).strip("_")
    if (
        media_kind == "maya_color_assignment_mask"
        or video_role == "maya_color_assignment_mask"
    ):
        return True
    # Pre-packed Picker payloads authored the Color bundle at @video1 without
    # a media_kind/video_role discriminator.  Do not let a typed Original (or
    # another typed row) inherit that compatibility authority merely because
    # packing placed it first.
    return bool(int(slot or 0) == 1 and not media_kind and not video_role)


def _picker_companion_expected_run_id(
    item: Dict[str, Any],
    slot: int,
    videos_by_slot: Dict[int, Dict[str, Any]],
) -> str | None:
    """Resolve the actual Mask identity for a typed Picker output.

    ``""`` is the valid standalone sentinel (source slot zero); ``None`` means
    a non-zero source is missing, is not a Mask, or has no bundle identity.
    """

    source_slot = _picker_companion_source_slot(item)
    if source_slot < 0:
        return None
    if source_slot == 0:
        return ""
    source = videos_by_slot.get(source_slot)
    if not isinstance(source, dict):
        return None
    # Preserve the historical typed-@video1 shape, where the companion row
    # itself also carried the old implicit Color bundle identity.
    if source is item and source_slot == int(slot or 0) == 1:
        return _clean_string(
            item.get("bundle_run_id") or item.get("pair_run_id")
        ) or None
    if not _picker_video_is_mask_bundle_source(source, source_slot):
        return None
    return _clean_string(
        source.get("bundle_run_id") or source.get("pair_run_id")
    ) or None


def _apply_picker_payload(state: Dict[str, Any], payload: Dict[str, Any], connected: bool = False) -> Dict[str, Any]:
    """Apply Maya binding data while preserving manual Color Pick edits.

    A marker is assigned only when its exact Asset ID equals the image row's
    Asset ID, or its Image Name for native legacy rows with no upstream
    provenance. External IMAGE_IMPORT_IN rows never enter this fallback.
    Picker data never authors image Main Type, Target, Image Sub Type,
    ordinary-video roles, Keep Out, or VFX. Valid generated Maya media adds its
    declared type/role and provenance without deleting user Color Picks, local
    bindings, or optional frame ranges. Invalid companion provenance keeps the
    connected file as an independent ordinary source while dropping only its
    matched-bundle authority. Row order, normalized text, visual similarity,
    and fallback assignment never create a binding.
    """
    normalized = _normalize_state(state)
    previous_picker = normalized.get("picker") if isinstance(normalized.get("picker"), dict) else {}
    has_unstructured_input = _merge_unstructured_payload_intent(
        normalized,
        payload,
    )
    if has_unstructured_input and set(payload).issubset({_UNSTRUCTURED_INPUT_KEY}):
        if isinstance(previous_picker, dict):
            previous_picker["enabled"] = bool(
                connected or previous_picker.get("enabled")
            )
        return _normalize_state(normalized)
    payload_mode = _clean_string(payload.get("mode")).lower() if isinstance(payload, dict) else ""
    payload_schema = _clean_string(payload.get("schema")) if isinstance(payload, dict) else ""
    payload_has_foreign_identity = bool(
        payload
        and (
            payload_mode not in {"", "maya"}
            or payload_schema not in {"", "hmb-prompt-library-picker-binding"}
        )
    )
    payload_has_picker_identity = bool(
        payload
        and (
            payload_mode == "maya"
            or payload_schema == "hmb-prompt-library-picker-binding"
            or any(key in payload for key in _PICKER_IDENTITY_KEYS)
        )
    )
    if payload and (payload_has_foreign_identity or not payload_has_picker_identity):
        _append_source_intent(
            normalized,
            PICKER_INPUT_PARAMETER_NAME,
            (
                "foreign mode or schema retained as ordinary user intent"
                if payload_has_foreign_identity
                else "readable connected object retained as ordinary user intent"
            ),
            {
                key: value
                for key, value in payload.items()
                if key != _UNSTRUCTURED_INPUT_KEY
            },
        )
        if isinstance(previous_picker, dict):
            previous_picker["enabled"] = bool(
                connected or previous_picker.get("enabled")
            )
        return _normalize_state(normalized)
    if payload_has_picker_identity:
        _append_unconsumed_connected_fields(
            normalized,
            PICKER_INPUT_PARAMETER_NAME,
            payload,
            _PICKER_PAYLOAD_KEYS,
        )
    raw_payload_videos_source = (
        payload.get("videos")
        if isinstance(payload, dict) and isinstance(payload.get("videos"), list)
        else []
    )
    raw_payload_videos, uid_order_managed = _canonical_uid_picker_video_rows(
        raw_payload_videos_source
    )
    _append_unconsumed_connected_rows(
        normalized,
        PICKER_INPUT_PARAMETER_NAME,
        raw_payload_videos,
        _PICKER_VIDEO_ROW_KEYS,
        "video row",
        len(raw_payload_videos),
    )
    for video_index, raw_video in enumerate(raw_payload_videos, start=1):
        if not isinstance(raw_video, dict):
            continue
        _append_unconsumed_connected_rows(
            normalized,
            PICKER_INPUT_PARAMETER_NAME,
            raw_video.get("markers"),
            _PICKER_MARKER_CONSUMED_KEYS,
            f"video row {video_index} marker",
            MAX_COLOR_PICKS,
        )
        nested_frame_metadata = raw_video.get("frame_metadata")
        if isinstance(nested_frame_metadata, dict):
            _append_unconsumed_connected_rows(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                [nested_frame_metadata],
                _PICKER_FRAME_METADATA_KEYS,
                f"video row {video_index} frame metadata",
                1,
            )
    payload_videos: List[Dict[str, Any]] = []
    accepted_payload_slots: set[int] = set()
    accepted_payload_uids: set[str] = set()
    rejected_video_contract_errors: List[str] = []
    has_readable_unstructured_video_rows = False
    for video_index, item in enumerate(raw_payload_videos, start=1):
        if not isinstance(item, dict):
            has_readable_unstructured_video_rows = True
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"readable non-object video row {video_index}",
                item,
            )
            continue
        item_uid = _picker_video_uid(item)
        if uid_order_managed and item.get("selected") is False:
            error = (
                f"PICKER_OUT UID-managed video row {video_index} is not selected; "
                "the row remains ordinary intent."
            )
            rejected_video_contract_errors.append(error)
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                error,
                item,
            )
            continue
        if uid_order_managed and not item_uid:
            has_readable_unstructured_video_rows = True
            error = (
                f"PICKER_OUT UID-managed video row {video_index} has no video_uid; "
                "the row remains ordinary intent."
            )
            rejected_video_contract_errors.append(error)
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                error,
                item,
            )
            continue
        if item_uid and item_uid in accepted_payload_uids:
            error = (
                f"PICKER_OUT contains an additional row for video_uid {item_uid}; "
                "the first valid row remains structured and this row remains ordinary intent."
            )
            rejected_video_contract_errors.append(error)
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                error,
                item,
            )
            continue
        if _picker_video_has_media(item):
            try:
                raw_slot = int(item.get("video_slot") or 1)
            except Exception:
                has_readable_unstructured_video_rows = True
                error = (
                    f"PICKER_OUT video row {video_index} has an invalid video_slot; "
                    "the row remains ordinary intent."
                )
                rejected_video_contract_errors.append(error)
                _append_source_intent(
                    normalized,
                    PICKER_INPUT_PARAMETER_NAME,
                    error,
                    item,
                )
                continue
            if raw_slot < 1 or raw_slot > MAX_VIDEOS:
                has_readable_unstructured_video_rows = True
                error = (
                    f"PICKER_OUT video_slot {raw_slot} is outside @video1 through "
                    f"@video{MAX_VIDEOS}; the row remains ordinary intent."
                )
                rejected_video_contract_errors.append(error)
                _append_source_intent(
                    normalized,
                    PICKER_INPUT_PARAMETER_NAME,
                    error,
                    item,
                )
                continue
            if raw_slot in accepted_payload_slots:
                error = (
                    f"PICKER_OUT contains an additional row for @video{raw_slot}; "
                    "the first valid row remains structured and this row remains ordinary intent."
                )
                rejected_video_contract_errors.append(error)
                _append_source_intent(
                    normalized,
                    PICKER_INPUT_PARAMETER_NAME,
                    error,
                    item,
                )
                continue
            accepted_payload_slots.add(raw_slot)
            if item_uid:
                accepted_payload_uids.add(item_uid)
            payload_videos.append(item)
        elif any(_clean_string(value) for value in item.values()):
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"video row {video_index} without concrete media retained as ordinary intent",
                item,
            )
    if uid_order_managed:
        # Contract-invalid or unreadable rows may have been rejected above.
        # Re-derive a contiguous transient namespace from the accepted media so
        # no gap can make Prompt and the generator list disagree.
        canonical_payload_videos, _ = _canonical_uid_picker_video_rows(
            payload_videos
        )
        payload_videos = [
            item for item in canonical_payload_videos if isinstance(item, dict)
        ]
        accepted_payload_slots = {
            int(item.get("video_slot") or 1) for item in payload_videos
        }
    legacy_video_path = (
        _clean_string(payload.get("video_path") or payload.get("video"))
        if isinstance(payload, dict)
        else ""
    )
    payload_declares_not_ready = bool(
        isinstance(payload, dict)
        and "media_ready" in payload
        and payload.get("media_ready") is not True
    )
    picker_has_media = bool(
        payload
        and not payload_declares_not_ready
        and (payload_videos or legacy_video_path)
    )
    try:
        declared_selected_video_count = int(
            payload.get("selected_video_count")
            if isinstance(payload, dict)
            and payload.get("selected_video_count") not in (None, "")
            else len(payload_videos)
        )
    except Exception:
        declared_selected_video_count = len(payload_videos)
    uid_selection_contract = bool(
        uid_order_managed
        or (
            isinstance(payload, dict)
            and any(
                key in payload
                for key in (
                    "selection_id",
                    "selected_video_count",
                    "max_selected_videos",
                )
            )
        )
    )
    authoritative_empty_uid_selection = bool(
        uid_selection_contract
        and declared_selected_video_count <= 0
        and not payload_videos
        and not legacy_video_path
    )
    if authoritative_empty_uid_selection:
        _, dormant_video_rows, dormant_manual_rows = (
            _prepare_uid_managed_video_rows(normalized, [])
        )
        normalized["videos"] = [_default_video_item(1)]
        normalized["picker"] = {
            "enabled": bool(connected),
            "awaiting_data": False,
            "run_id": _picker_payload_id(payload),
            "selection_id": _clean_string(payload.get("selection_id")),
            "selected_video_count": 0,
            "ordered_video_uids": [],
            "order_managed": True,
            "dormant_video_rows": dormant_video_rows,
            "dormant_manual_rows": dormant_manual_rows,
            "slot_suppressions": {},
            "scene": _clean_string(payload.get("scene") or payload.get("scene_path")),
            "video_path": "",
            "camera": _clean_string(payload.get("camera")),
            "markers": [],
            "frame_metadata": [],
            "contract_errors": list(dict.fromkeys(rejected_video_contract_errors)),
            "matched_images": 0,
        }
        return _normalize_state(normalized)
    if not picker_has_media:
        if has_readable_unstructured_video_rows:
            if isinstance(previous_picker, dict):
                previous_picker["enabled"] = bool(
                    connected or previous_picker.get("enabled")
                )
            return _normalize_state(normalized)
        # Release only fields previously auto-authored by Picker companion
        # provenance. Native/manual rows are untouched, so a workflow with no
        # Picker input retains its original Prompt state.  A connected semantic
        # payload containing only empty UI slot placeholders follows this same
        # path: it is awaiting data, not authoritative media lifecycle data.
        for video_item in normalized.get("videos", []):
            if isinstance(video_item, dict):
                _invalidate_picker_generated_depth(video_item)
                _invalidate_picker_generated_motion_guide(video_item)
                video_item["picker_companion_kind"] = ""
                video_item["picker_companion_source_slot"] = -1
                video_item["picker_companion_source_uid"] = ""
                video_item["picker_companion_validated"] = False
        normalized["picker"] = {
            "enabled": bool(connected),
            "awaiting_data": bool(connected),
            "run_id": "",
            "selection_id": "",
            "selected_video_count": 0,
            "ordered_video_uids": [],
            "order_managed": bool(previous_picker.get("order_managed")),
            "dormant_video_rows": previous_picker.get("dormant_video_rows", []),
            "dormant_manual_rows": previous_picker.get("dormant_manual_rows", []),
            "slot_suppressions": _normalize_picker_slot_suppressions(
                previous_picker.get("slot_suppressions")
            ),
            "scene": "",
            "video_path": "",
            "camera": "",
            "markers": [],
            "frame_metadata": [],
            "matched_images": 0,
        }
        return _normalize_state(normalized)

    if not payload_videos and legacy_video_path:
        payload_videos = [{
            "video_slot": payload.get("video_slot") or 1,
            "video_path": legacy_video_path,
            "camera": payload.get("camera") or "",
        }]

    payload_id = _picker_payload_id(payload)
    slot_suppressions = {} if uid_order_managed else {
        slot: suppressed_payload_id
        for slot, suppressed_payload_id in _normalize_picker_slot_suppressions(
            previous_picker.get("slot_suppressions")
        ).items()
        if suppressed_payload_id == payload_id
    }
    suppressed_payload_slots = {int(slot) for slot in slot_suppressions}

    dormant_video_rows = previous_picker.get("dormant_video_rows", [])
    dormant_manual_rows = previous_picker.get("dormant_manual_rows", [])
    if uid_order_managed:
        selected_rows, dormant_video_rows, dormant_manual_rows = (
            _prepare_uid_managed_video_rows(normalized, payload_videos)
        )
        normalized["videos"] = selected_rows or [_default_video_item(1)]

    payload_videos_by_slot: Dict[int, Dict[str, Any]] = {}
    for raw_video in payload_videos:
        if not isinstance(raw_video, dict):
            continue
        try:
            candidate_slot = int(raw_video.get("video_slot") or 1)
        except Exception:
            candidate_slot = 1
        if candidate_slot in range(1, MAX_VIDEOS + 1):
            payload_videos_by_slot[candidate_slot] = raw_video
    payload_slot_by_uid = {
        _picker_video_uid(raw_video): slot
        for slot, raw_video in payload_videos_by_slot.items()
        if _picker_video_uid(raw_video)
    }
    claimed_depth_slots: set[int] = set()
    generated_depth_slots: set[int] = set()
    generated_depth_run_ids: Dict[int, str] = {}
    claimed_motion_guide_slots: set[int] = set()
    generated_motion_guide_slots: set[int] = set()
    generated_motion_guide_run_ids: Dict[int, str] = {}
    picker_contract_errors: List[str] = list(rejected_video_contract_errors)
    raw_slot_counts: Dict[int, int] = {}
    for raw_video in payload_videos:
        if not isinstance(raw_video, dict):
            continue
        try:
            raw_slot = int(raw_video.get("video_slot") or 1)
        except Exception:
            raw_slot = 1
        if raw_slot < 1 or raw_slot > MAX_VIDEOS:
            picker_contract_errors.append(
                f"PICKER_OUT video_slot {raw_slot} is outside @video1 through @video{MAX_VIDEOS}."
            )
        candidate_slot = max(1, min(MAX_VIDEOS, raw_slot))
        raw_slot_counts[candidate_slot] = raw_slot_counts.get(candidate_slot, 0) + 1
        if _picker_video_claims_generated_depth(
            raw_video,
            candidate_slot,
        ):
            claimed_depth_slots.add(candidate_slot)
        expected_run_id = _picker_companion_expected_run_id(
            raw_video,
            candidate_slot,
            payload_videos_by_slot,
        )
        if (
            expected_run_id is not None
            and _picker_video_is_generated_depth(
                raw_video,
                candidate_slot,
                expected_run_id,
            )
        ):
            generated_depth_slots.add(candidate_slot)
            generated_depth_run_ids[candidate_slot] = _clean_string(
                raw_video.get("bundle_run_id")
                or raw_video.get("pair_run_id")
            )
        if _picker_video_claims_generated_motion_guide(
            raw_video,
            candidate_slot,
        ):
            claimed_motion_guide_slots.add(candidate_slot)
        if (
            expected_run_id is not None
            and _picker_video_is_generated_motion_guide(
                raw_video,
                candidate_slot,
                expected_run_id,
            )
        ):
            generated_motion_guide_slots.add(candidate_slot)
            generated_motion_guide_run_ids[candidate_slot] = _clean_string(
                raw_video.get("bundle_run_id")
            )
    for duplicate_slot, count in sorted(raw_slot_counts.items()):
        if count > 1:
            picker_contract_errors.append(
                f"PICKER_OUT contains {count} rows for @video{duplicate_slot}; each slot must be unique."
            )
    conflicting_typed_slots = claimed_depth_slots & claimed_motion_guide_slots
    for conflicting_slot in sorted(conflicting_typed_slots):
        picker_contract_errors.append(
            f"@video{conflicting_slot} cannot claim both Depth and Motion Guide."
        )
    if not uid_order_managed and len(claimed_depth_slots) > 1:
        picker_contract_errors.append(
            "Only one generated Depth companion may be active across the Picker video slots."
        )
    if not uid_order_managed and len(claimed_motion_guide_slots) > 1:
        picker_contract_errors.append(
            "Only one generated Motion Guide companion may be active across the Picker video slots."
        )
    for invalid_slot in sorted(claimed_depth_slots - generated_depth_slots):
        picker_contract_errors.append(
            f"@video{invalid_slot} has incomplete or mismatched generated Depth provenance."
        )
    for invalid_slot in sorted(
        claimed_motion_guide_slots - generated_motion_guide_slots
    ):
        picker_contract_errors.append(
            f"@video{invalid_slot} has incomplete or mismatched generated Motion Guide provenance."
        )
    claimed_companion_slots = (
        claimed_depth_slots | claimed_motion_guide_slots
    )
    generated_companion_slots = (
        generated_depth_slots | generated_motion_guide_slots
    )

    raw_markers = payload.get("markers") if isinstance(payload.get("markers"), list) else []
    _append_unconsumed_connected_rows(
        normalized,
        PICKER_INPUT_PARAMETER_NAME,
        raw_markers,
        _PICKER_MARKER_CONSUMED_KEYS,
        "marker row",
        len(raw_markers),
    )
    markers: List[Dict[str, Any]] = []
    for order_index, raw in enumerate(raw_markers, start=1):
        if not isinstance(raw, dict):
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"readable non-object marker row {order_index}",
                raw,
            )
            continue
        color = _clean_string(raw.get("color"))
        if not color:
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"marker row {order_index} without a structured color retained as ordinary intent",
                raw,
            )
            continue
        try:
            marker_uid = _clean_string(raw.get("video_uid") or raw.get("source_uid"))
            video_slot = int(
                payload_slot_by_uid.get(marker_uid)
                or raw.get("video_slot")
                or payload.get("video_slot")
                or 1
            )
        except Exception:
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"marker row {order_index} has an invalid video_slot and remains ordinary intent",
                raw,
            )
            continue
        if video_slot < 1 or video_slot > MAX_VIDEOS:
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                (
                    f"marker row {order_index} targets @video{video_slot}, outside "
                    f"@video1 through @video{MAX_VIDEOS}, and remains ordinary intent"
                ),
                raw,
            )
            continue
        if video_slot in generated_companion_slots:
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"marker row {order_index} associated with a companion slot",
                raw,
            )
            continue
        try:
            picker_order = int(raw.get("picker_order") or order_index)
        except Exception:
            picker_order = order_index
        markers.append({
            "color": color,
            "asset_id": _clean_string(raw.get("asset_id")),
            "subject_root": _clean_string(raw.get("subject_root")),
            "video_slot": video_slot,
            "video_uid": _clean_string(
                raw.get("video_uid")
                or raw.get("source_uid")
                or _picker_video_uid(payload_videos_by_slot.get(video_slot))
            ),
            "picker_order": picker_order,
        })
    markers.sort(key=lambda item: (int(item.get("video_slot") or 1), int(item.get("picker_order") or 0)))

    video_path = _clean_string(payload.get("video_path") or payload.get("video"))
    previous_video_path = _clean_string(previous_picker.get("video_path"))
    videos = normalized.get("videos") if isinstance(normalized.get("videos"), list) else []
    if not videos:
        videos = [_default_video_item(1)]
        normalized["videos"] = videos

    top_level_frame_metadata = (
        payload.get("frame_metadata")
        if isinstance(payload.get("frame_metadata"), list)
        else []
    )
    _append_unconsumed_connected_rows(
        normalized,
        PICKER_INPUT_PARAMETER_NAME,
        top_level_frame_metadata,
        _PICKER_FRAME_METADATA_KEYS,
        "frame metadata row",
        len(top_level_frame_metadata),
    )
    raw_frame_metadata = list(top_level_frame_metadata)
    if not raw_frame_metadata:
        raw_frame_metadata = []
        for raw_video in payload_videos:
            if not isinstance(raw_video, dict):
                continue
            nested = raw_video.get("frame_metadata")
            if isinstance(nested, dict):
                raw_frame_metadata.append(nested)
            elif any(
                key in raw_video
                for key in ("fps", "start_frame", "end_frame", "frame_count")
            ):
                raw_frame_metadata.append({
                    "video_slot": raw_video.get("video_slot"),
                    "video_uid": raw_video.get("video_uid") or raw_video.get("source_uid"),
                    "source_uid": raw_video.get("video_uid") or raw_video.get("source_uid"),
                    "selection_order": raw_video.get("selection_order"),
                    "order_key": raw_video.get("order_key"),
                    "fps": raw_video.get("fps"),
                    "start_frame": raw_video.get("start_frame"),
                    "end_frame": raw_video.get("end_frame"),
                    "frame_count": raw_video.get("frame_count"),
                    "duration_seconds": raw_video.get("duration_seconds"),
                    "timebase": raw_video.get("timebase"),
                    "width": raw_video.get("width"),
                    "height": raw_video.get("height"),
                    "resolution": raw_video.get("resolution"),
                    "available_color_picks": raw_video.get("available_color_picks"),
                    "conflict": raw_video.get("conflict"),
                    "valid": raw_video.get("valid"),
                    "warnings": raw_video.get("warnings"),
                })
    structured_frame_metadata: List[Dict[str, Any]] = []
    seen_frame_metadata_slots: set[int] = set()
    for metadata_index, raw_metadata in enumerate(raw_frame_metadata, start=1):
        if not isinstance(raw_metadata, dict):
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"readable non-object frame metadata row {metadata_index}",
                raw_metadata,
            )
            continue
        try:
            metadata_uid = _clean_string(
                raw_metadata.get("video_uid") or raw_metadata.get("source_uid")
            )
            raw_metadata_slot = (
                payload_slot_by_uid.get(metadata_uid)
                or raw_metadata.get("video_slot")
                or raw_metadata.get("video")
                or 1
            )
            metadata_slot_token = _clean_string(raw_metadata_slot)
            metadata_slot_match = re.fullmatch(
                r"@video([0-9]+)",
                metadata_slot_token,
                re.IGNORECASE,
            )
            metadata_slot = int(
                metadata_slot_match.group(1)
                if metadata_slot_match is not None
                else raw_metadata_slot
            )
        except Exception:
            error = (
                f"frame metadata row {metadata_index} has an invalid video_slot and "
                "remains ordinary intent"
            )
            picker_contract_errors.append(error)
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                error,
                raw_metadata,
            )
            continue
        if metadata_slot < 1 or metadata_slot > MAX_VIDEOS:
            error = (
                f"frame metadata row {metadata_index} targets @video{metadata_slot}, outside "
                f"@video1 through @video{MAX_VIDEOS}, and remains ordinary intent"
            )
            picker_contract_errors.append(error)
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                error,
                raw_metadata,
            )
            continue
        if metadata_slot in seen_frame_metadata_slots:
            error = (
                f"frame metadata row {metadata_index} duplicates @video{metadata_slot}; "
                "the first valid row remains structured and this row remains ordinary intent"
            )
            picker_contract_errors.append(error)
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                error,
                raw_metadata,
            )
            continue
        seen_frame_metadata_slots.add(metadata_slot)
        structured_metadata = dict(raw_metadata)
        structured_metadata["video_slot"] = metadata_slot
        if metadata_uid:
            structured_metadata["video_uid"] = metadata_uid
            structured_metadata["source_uid"] = metadata_uid
            structured_metadata["selection_order"] = metadata_slot
            structured_metadata["order_key"] = (
                _clean_string(raw_metadata.get("order_key")) or metadata_uid
            )
        structured_frame_metadata.append(structured_metadata)
    frame_metadata = _normalize_frame_metadata(structured_frame_metadata)
    try:
        picker_slot_count = max(1, min(MAX_VIDEOS, int(payload.get("active_slot_count") or len(payload_videos) or 1)))
    except Exception:
        picker_slot_count = max(1, min(MAX_VIDEOS, len(payload_videos) or 1))
    payload_slots = {
        max(1, min(MAX_VIDEOS, int(item.get("video_slot") or 1)))
        for item in payload_videos if isinstance(item, dict)
    }
    effective_payload_slots = payload_slots - suppressed_payload_slots
    highest_payload_slot = max(effective_payload_slots, default=1)
    effective_picker_slot_count = (
        picker_slot_count
        if not suppressed_payload_slots
        else highest_payload_slot
    )
    merged_slot_count = max(
        1,
        min(
            MAX_VIDEOS,
            max(len(videos), effective_picker_slot_count, highest_payload_slot),
        ),
    )
    # PICKER_OUT contributes rows but does not own Prompt's slot lifecycle.
    # Existing manual/user-edited rows survive a shorter Picker payload. Only
    # unchanged fields that Prompt can identify as Picker-authored are released.
    videos = videos[:MAX_VIDEOS]
    while len(videos) < merged_slot_count:
        videos.append(_default_video_item(len(videos) + 1))
    for slot in range(1, merged_slot_count + 1):
        if slot not in payload_slots:
            video_item = videos[slot - 1]
            depth_auto_released = _release_picker_generated_depth(video_item)
            motion_auto_released = (
                _release_picker_generated_motion_guide(video_item)
            )
            if not depth_auto_released and not motion_auto_released:
                auto_label = _clean_string(video_item.get("picker_auto_label"))
                current_label = _clean_string(video_item.get("label"))
                if auto_label and current_label == auto_label:
                    video_item["label"] = ""
                    video_item["picker_auto_label"] = ""
                    video_item["present"] = False
                    if (
                        video_item.get("source_type") == "Maya Preview / Playblast"
                        and not _clean_string(video_item.get("control_role"))
                        and not _clean_string(video_item.get("keep_out"))
                    ):
                        video_item["source_type"] = "Role Required / Select Video Type"
            video_item["picker_companion_kind"] = ""
            video_item["picker_companion_source_slot"] = -1
            video_item["picker_companion_source_uid"] = ""
            video_item["picker_companion_validated"] = False
            video_item["manual"] = True
    for slot in payload_slots:
        if (
            slot <= len(videos)
            and slot not in suppressed_payload_slots
            and slot not in generated_companion_slots
        ):
            _invalidate_picker_generated_depth(videos[slot - 1])
            _invalidate_picker_generated_motion_guide(videos[slot - 1])
    for raw_video in payload_videos:
        if not isinstance(raw_video, dict):
            continue
        try:
            slot = max(1, min(MAX_VIDEOS, int(raw_video.get("video_slot") or 1)))
        except Exception:
            slot = 1
        if slot in suppressed_payload_slots:
            continue
        while len(videos) < slot:
            videos.append(_default_video_item(len(videos) + 1))
        video_item = videos[slot - 1]
        if _clean_string(video_item.get("source_type")) == "Ignore / Unused":
            continue
        row_uid = _picker_video_uid(raw_video)
        if row_uid:
            video_item["video_uid"] = row_uid
            video_item["source_uid"] = row_uid
            video_item["selection_order"] = slot
            video_item["order_key"] = (
                _clean_string(raw_video.get("order_key")) or row_uid
            )
            video_item["picker_managed"] = True
        slot_path = _clean_string(raw_video.get("video_path") or raw_video.get("video"))
        current_label = _clean_string(video_item.get("label"))
        previous_auto_label = _clean_string(video_item.get("picker_auto_label"))
        generated_depth = slot in generated_depth_slots
        generated_motion_guide = slot in generated_motion_guide_slots
        declared_depth = slot in claimed_depth_slots
        declared_motion_guide = slot in claimed_motion_guide_slots
        if declared_depth or declared_motion_guide:
            companion_source_slot = _picker_companion_source_slot(raw_video)
            companion_source_uid = _clean_string(
                raw_video.get("source_video_uid")
                or raw_video.get("companion_of_video_uid")
                or raw_video.get("companion_video_uid")
            )
            video_item["picker_companion_kind"] = (
                "depth" if declared_depth else "motion_guide"
            )
            video_item["picker_companion_source_slot"] = companion_source_slot
            video_item["picker_companion_source_uid"] = companion_source_uid
            video_item["picker_companion_validated"] = bool(
                generated_depth or generated_motion_guide
            )
        else:
            video_item["picker_companion_kind"] = ""
            video_item["picker_companion_source_slot"] = -1
            video_item["picker_companion_source_uid"] = ""
            video_item["picker_companion_validated"] = False
        if generated_depth:
            assigned_depth_values: Dict[str, Any] = {
                "source_type": "Depth / Spatial Reference",
                "custom_source_type": "",
                "control_role": "Spatial Alignment Verification Only",
                "custom_control_role": "",
            }
            if slot_path:
                depth_label = _video_file_stem(slot_path)
                assigned_depth_values.update({
                    "label": depth_label,
                    "present": True,
                    "picker_auto_label": depth_label,
                })
            _assign_picker_generated_depth(
                video_item,
                generated_depth_run_ids.get(slot, ""),
                assigned_depth_values,
            )
        elif generated_motion_guide:
            assigned_motion_values: Dict[str, Any] = {
                "source_type": "Motion Guide / Retargeting Reference",
                "custom_source_type": "",
                "control_role": "Derived Motion Decoding Only",
                "custom_control_role": "",
            }
            if slot_path:
                motion_label = _video_file_stem(slot_path)
                assigned_motion_values.update({
                    "label": motion_label,
                    "present": True,
                    "picker_auto_label": motion_label,
                })
            _assign_picker_generated_motion_guide(
                video_item,
                generated_motion_guide_run_ids.get(slot, ""),
                assigned_motion_values,
            )
            video_item["picker_motion_guide_summary"] = (
                _picker_motion_guide_summary(raw_video)
            )
        elif declared_depth or declared_motion_guide:
            declared_type = _clean_string(raw_video.get("source_type_hint")) or (
                "Depth / Spatial Reference"
                if declared_depth
                else "Motion Guide / Retargeting Reference"
            )
            declared_role = _canonical_video_role(
                raw_video.get("control_role_hint")
            ) or (
                "Spatial Alignment Verification Only"
                if declared_depth
                else "Derived Motion Decoding Only"
            )
            if video_item.get("source_type") in (
                "",
                "Role Required / Select Video Type",
            ):
                video_item["source_type"] = declared_type
            if not _clean_string(video_item.get("control_role")):
                video_item["control_role"] = declared_role
            if slot_path and (
                not current_label
                or current_label == previous_auto_label
                or current_label == previous_video_path
                or current_label == _video_file_stem(previous_video_path)
                or current_label
                == _clean_string(previous_picker.get(f"video{slot}_path"))
            ):
                video_item["label"] = _video_file_stem(slot_path)
                video_item["picker_auto_label"] = video_item["label"]
                video_item["present"] = True
        elif slot_path and (
            not current_label
            or current_label == previous_auto_label
            or current_label == previous_video_path
            or current_label == _video_file_stem(previous_video_path)
            or current_label == _clean_string(previous_picker.get(f"video{slot}_path"))
        ):
            video_item["label"] = _video_file_stem(slot_path)
            video_item["picker_auto_label"] = video_item["label"]
            video_item["present"] = True
        if (
            not generated_depth
            and not generated_motion_guide
            and video_item.get("source_type")
            in ("", "Role Required / Select Video Type")
        ):
            video_item["source_type"] = "Maya Preview / Playblast"
        video_item["manual"] = True
    normalized["videos"] = videos

    images = normalized.get("images") if isinstance(normalized.get("images"), list) else []
    _clear_image_bindings_for_generated_depth(
        images,
        generated_companion_slots,
        len(videos),
    )
    picker_source = _clean_string(payload.get("scene_path") or payload.get("video_path") or payload.get("video") or payload.get("mode") or "picker")

    # Clear only unchanged values that were previously assigned by Picker. A
    # user-edited Color Pick is never removed or overwritten.
    auto_replacement_indices: Dict[int, int] = {}
    for item in images:
        _normalize_image_binding_fields(item, max(1, len(videos)))
        auto_color = _clean_string(item.get("picker_auto_color"))
        try:
            auto_video = int(item.get("picker_auto_video") or 0)
        except Exception:
            auto_video = 0
        picks = list(item.get("color_picks", [""]))
        slots = list(item.get("binding_video_slots", [1]))
        auto_index = next(
            (
                index
                for index, color in enumerate(picks)
                if _clean_string(color) == auto_color
                and index < len(slots)
                and slots[index] == auto_video
            ),
            -1,
        )
        if auto_color and auto_index >= 0:
            _release_picker_auto_frame_binding(item, auto_video, auto_color)
            picks[auto_index] = ""
            item["color_picks"] = picks
            item["marker_video"] = slots[0] if slots else 1
            item["picker_auto_color"] = ""
            item["picker_auto_video"] = 0
            item["picker_auto_source"] = ""
            auto_replacement_indices[id(item)] = auto_index

    matched_images = 0
    assigned_image_ids: set[int] = set()
    assigned_marker_ids: set[int] = set()
    assigned_marker_addresses: set[tuple[int, str]] = set()

    def apply_marker(item: Dict[str, Any], marker: Dict[str, Any]) -> bool:
        nonlocal matched_images
        video_count = max(1, len(videos))
        _normalize_image_binding_fields(item, video_count)
        picks = list(item.get("color_picks", [""]))
        slots = list(item.get("binding_video_slots", [1]))
        replacement_index = auto_replacement_indices.get(id(item))
        current_colors = [value for value in picks if _clean_string(value)]
        if current_colors and replacement_index is None:
            return False
        slot = max(1, min(MAX_VIDEOS, int(marker.get("video_slot") or 1)))
        if replacement_index is None:
            replacement_index = next(
                (index for index, color in enumerate(picks) if not _clean_string(color)),
                -1,
            )
        if replacement_index < 0 and len(picks) < MAX_COLOR_PICKS:
            picks.append("")
            slots.append(slots[-1] if slots else slot)
            primary_scope = _clean_string(item.get("scope"))
            primary_custom_scope = (
                _clean_string((item.get("binding_custom_scopes") or [""])[0])
                if primary_scope == "Custom scope"
                else ""
            )
            item["binding_scopes"] = [primary_scope] * len(picks)
            item["binding_custom_scopes"] = [primary_custom_scope] * len(picks)
            replacement_index = len(picks) - 1
        if replacement_index < 0 or replacement_index >= len(picks):
            return False
        if any(
            index != replacement_index
            and index < len(slots)
            and slots[index] == slot
            and _clean_string(color) == marker["color"]
            for index, color in enumerate(picks)
        ):
            return False
        picks[replacement_index] = marker["color"]
        slots[replacement_index] = slot
        item["color_picks"] = picks
        item["binding_video_slots"] = slots
        item["marker_video"] = slots[0]
        item["picker_auto_color"] = marker["color"]
        item["picker_auto_video"] = slot
        item["picker_auto_source"] = picker_source
        _normalize_image_binding_fields(item, video_count)
        matched_images += 1
        return True

    # Exact Asset ID binding only. One Maya Asset ID must equal one active image Name.
    for marker_index, marker in enumerate(markers):
        if not marker.get("asset_id") and not marker.get("name"):
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"marker row {marker_index + 1} without an exact Asset ID",
                marker,
            )
            continue
        marker_address = (
            max(1, min(MAX_VIDEOS, int(marker.get("video_slot") or 1))),
            _clean_string(marker.get("color")),
        )
        # Keep the Picker marker catalog for inspection and future runs, but a
        # locally suppressed video slot cannot continue authoring an active
        # image/Color Pick binding. Other slots remain independent.
        if marker_address[0] in suppressed_payload_slots:
            continue
        # Several Maya roots may share one background marker, but one
        # @video/color address still owns exactly one appearance binding.
        if marker_address in assigned_marker_addresses:
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                f"additional marker at @video{marker_address[0]} / {marker_address[1]}",
                marker,
            )
            continue
        candidates = _picker_match_candidates(images, marker, assigned_image_ids)
        if len(candidates) != 1:
            _append_source_intent(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
                (
                    f"marker row {marker_index + 1} with "
                    f"{len(candidates)} exact image matches"
                ),
                marker,
            )
            continue
        image_index = candidates[0]
        item = images[image_index]
        if apply_marker(item, marker):
            assigned_image_ids.add(image_index)
            assigned_marker_ids.add(marker_index)
            assigned_marker_addresses.add(marker_address)

    normalized["picker"] = {
        "enabled": True,
        "awaiting_data": False,
        "run_id": payload_id,
        "selection_id": _clean_string(payload.get("selection_id")),
        "selected_video_count": len(payload_videos),
        "ordered_video_uids": [
            uid
            for uid in (_picker_video_uid(item) for item in payload_videos)
            if uid
        ],
        "order_managed": uid_order_managed,
        "dormant_video_rows": dormant_video_rows,
        "dormant_manual_rows": dormant_manual_rows,
        "slot_suppressions": slot_suppressions,
        "scene": _clean_string(payload.get("scene") or payload.get("scene_path")),
        "video_path": video_path,
        "camera": _clean_string(payload.get("camera")),
        "markers": markers,
        "frame_metadata": frame_metadata,
        "contract_errors": list(dict.fromkeys(picker_contract_errors)),
        "matched_images": matched_images,
    }
    return _normalize_state(normalized)

def _prompt_output_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "name": "PROMPT_OUT",
        "tooltip": "Prompt output for HMBAgentLibrary. When direct media conditioning is desired, external loaders may also connect those media files to the agent/generator.",
        "default_value": "",
        "type": "str",
        "output_type": "str",
        "input_types": [],
        "allow_input": False,
        "allow_output": True,
        "allow_property": False,
        "settable": False,
        "hide_property": True,
        "ui_options": {
            "display_name": "PROMPT OUT",
            "compact": True,
            "height": 24,
            "is_full_width": False,
            "hide_property": True,
        },
    }
    mode = _mode_output()
    if mode is not None:
        kwargs["allowed_modes"] = mode
    return kwargs


def _repair_prompt_output_parameter(node: Any) -> None:
    parameter = _get_parameter_obj(node, "PROMPT_OUT")
    if parameter is None:
        return
    kwargs = _prompt_output_kwargs()
    modern_modes = kwargs.get("allowed_modes") is not None
    for key, value in kwargs.items():
        if key == "ui_options":
            continue
        if modern_modes and key in ("allow_input", "allow_output", "allow_property"):
            continue
        try:
            setattr(parameter, key, value)
        except Exception as exc:
            _diagnostic_exception(f"PROMPT_OUT attribute repair failed for {key}", exc)
    try:
        current_ui = getattr(parameter, "ui_options", None) or getattr(parameter, "_ui_options", None) or {}
        if not isinstance(current_ui, dict):
            current_ui = {}
        current_ui.update(kwargs["ui_options"])
        current_ui.pop("port_only", None)
        current_ui.pop("hide", None)
        current_ui.pop("hide_handles", None)
        current_ui.pop("hide_label", None)
        parameter.ui_options = current_ui
    except Exception as exc:
        _diagnostic_exception("PROMPT_OUT UI option repair failed", exc)


def _add_prompt_output(node: Any) -> None:
    if parameter_exists(node, "PROMPT_OUT"):
        _repair_prompt_output_parameter(node)
        return
    kwargs = _prompt_output_kwargs()
    try:
        _safe_add_parameter(node, **kwargs)
    finally:
        _repair_prompt_output_parameter(node)


def _add_widget_state_parameter(node: Any) -> None:
    if parameter_exists(node, WIDGET_PARAMETER_NAME):
        return
    kwargs: Dict[str, Any] = {
        "name": WIDGET_PARAMETER_NAME,
        "tooltip": "HMB_GP_Production additive source-binding dashboard. Supplied Image Target, Sub Type, video role, Color Pick, and optional local bindings add authority without making another source or slot mandatory. Missing semantic fields remain unspecified. Explicit Picker companion provenance alone activates cross-file bundle integrity checks.",
        "default_value": _json_dumps(_default_widget_state()),
        "type": "str",
        "input_types": [],
        "allow_input": False,
        "allow_output": False,
        "allow_property": True,
        "ui_options": {
            "display_name": "HMB_GP_Production",
            "is_full_width": True,
            "height": PROMPT_START_HEIGHT,
            "min_height": PROMPT_MIN_HEIGHT,
            "widget_height": PROMPT_START_HEIGHT,
            "width": 1800,
            "min_width": 760,
            "preferred_width": 1800,
            "preferred_height": PROMPT_START_HEIGHT,
            "default_width": 1800,
            "default_height": PROMPT_START_HEIGHT,
            "initial_width": 1800,
            "initial_height": PROMPT_START_HEIGHT,
            "node_size": {"width": 1800, "height": PROMPT_START_HEIGHT},
            "default_size": {"width": 1800, "height": PROMPT_START_HEIGHT},
            "initial_size": {"width": 1800, "height": PROMPT_START_HEIGHT},
            "resizable": True,
            "compact": False,
        },
    }
    mode = _mode_property()
    if mode is not None:
        kwargs["allowed_modes"] = mode
    param = None
    trait_attached = False
    last: Exception | None = None
    for attempt in _parameter_attempts(kwargs):
        if Widget is not None:
            try:
                param = Parameter(**{**attempt, "traits": {Widget(name=WIDGET_NAME, library=WIDGET_LIBRARY_NAME)}})
                trait_attached = True
                break
            except Exception as exc:
                last = exc
        try:
            if param is None:
                param = Parameter(**attempt)
            break
        except Exception as exc:
            last = exc
    if param is None:
        raise last or RuntimeError(f"Unable to add parameter {WIDGET_PARAMETER_NAME}")
    if Widget is not None and not trait_attached:
        try:
            param.add_trait(Widget(name=WIDGET_NAME, library=WIDGET_LIBRARY_NAME))
        except Exception as exc:
            _diagnostic_exception("Prompt widget compatibility trait registration failed", exc)
    node.add_parameter(param)


def _frame_range_binding_validation(
    state: Dict[str, Any],
    item: Dict[str, Any],
    active_video_slots: set[int] | None = None,
) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None, List[str]]:
    errors: List[str] = []
    if not bool(item.get("frame_range_enabled")):
        return None, None, errors

    binding = _current_frame_range_binding(item)
    if not binding:
        errors.append(
            "Optional frame-range instruction ignored: select a Video and Color Pick to define it."
        )
        return None, None, errors

    slot = _video_slot_number(binding.get("video_slot"), MAX_VIDEOS)
    color = _clean_string(binding.get("color_pick"))
    if active_video_slots is not None and slot not in active_video_slots:
        errors.append(f"@video{slot} does not exist as an active video source.")
    if not color:
        errors.append("Color Pick is not selected.")

    picker = state.get("picker") if isinstance(state.get("picker"), dict) else {}
    picker_ready = bool(
        picker.get("enabled")
        and not picker.get("awaiting_data")
    )
    picker_metadata = next(
        (
            entry
            for entry in _normalize_frame_metadata(picker.get("frame_metadata"))
            if _video_slot_number(entry.get("video_slot"), MAX_VIDEOS) == slot
        ),
        None,
    ) if picker_ready else None

    if picker_metadata is not None:
        metadata = picker_metadata
        if bool(metadata.get("conflict")) or not bool(metadata.get("valid")):
            errors.append(f"Frame metadata for @video{slot} is conflicting or incomplete.")
        available_colors = metadata.get("available_color_picks")
        if isinstance(available_colors, list) and color not in available_colors:
            errors.append(f"{color} is not available in @video{slot} Picker metadata.")
    else:
        manual_start = _optional_frame_number(binding.get("start_frame"))
        manual_end = _optional_frame_number(binding.get("end_frame"))
        if manual_start is None:
            errors.append(
                "Optional frame-range instruction ignored: manual START frame is not supplied."
            )
        if manual_end is None:
            errors.append(
                "Optional frame-range instruction ignored: manual END frame is not supplied."
            )
        if manual_start is not None and manual_end is not None and manual_start > manual_end:
            errors.append(
                f"Manual frame domain {manual_start}-{manual_end} has START after END."
            )
        if manual_start is None or manual_end is None or manual_start > manual_end:
            return binding, None, errors
        metadata = {
            "video_slot": f"@video{slot}",
            "fps": 0.0,
            "start_frame": manual_start,
            "end_frame": manual_end,
            "frame_count": manual_end - manual_start + 1,
            "duration_seconds": 0.0,
            "timebase": "",
            "available_color_picks": [color] if color else [],
            "origin": "manual",
            "conflict": False,
            "valid": True,
            "warnings": [],
        }

    ranges = _normalize_frame_ranges(binding.get("ranges"))
    if not ranges:
        errors.append(
            "Optional frame-range instruction ignored: no range is selected; full-shot source use remains available."
        )
    minimum = int(metadata.get("start_frame"))
    maximum = int(metadata.get("end_frame"))
    for frame_range in ranges:
        start = int(frame_range.get("start") or 0)
        end = int(frame_range.get("end") or 0)
        if start > end:
            errors.append(f"Invalid frame range {start}–{end}.")
        elif start < minimum or end > maximum:
            errors.append(
                f"Frame range {start}–{end} is outside @video{slot} Frames {minimum}–{maximum}."
            )
    binding = {
        **binding,
        "video_slot": f"@video{slot}",
        "color_pick": color,
        "ranges": ranges,
    }
    return binding, metadata, errors


def _valid_frame_range_bindings(
    state: Dict[str, Any],
    active_images: List[Dict[str, Any]],
    active_videos: List[Dict[str, Any]],
) -> List[tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    active_video_slots = {
        int(item.get("slot") or 1)
        for item in active_videos
    }
    out: List[tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
    for item in active_images:
        binding, metadata, errors = _frame_range_binding_validation(
            state,
            item,
            active_video_slots,
        )
        if binding is not None and metadata is not None and not errors:
            out.append((item, binding, metadata))
    return out


def _prompt_section_end(lines: List[str], start: int) -> int:
    """Return the first following production section header or EOF."""
    for index in range(start + 1, len(lines)):
        text = _clean_string(lines[index])
        if text and text.endswith(":") and re.fullmatch(r"[A-Z0-9][A-Z0-9 /_+()@.-]*:", text):
            return index
    return len(lines)


def _compile_prompt_with_budget(lines: List[str]) -> str:
    """Compact generated diagnostics without truncating canonical user intent.

    The dashboard state and USER DESCRIPTION DATA remain untouched.  When the
    protected user-authored payload itself exceeds the advisory budget, the
    prompt remains over budget rather than silently deleting the user's goal.
    """
    working = list(lines)
    compacted: List[str] = []
    for header in _OPTIONAL_PROMPT_SECTION_PRIORITY:
        prompt = "\n".join(working).strip() + "\n"
        if len(prompt) <= MAX_PROMPT_CHARS:
            return prompt
        try:
            start = working.index(header)
        except ValueError:
            continue
        end = _prompt_section_end(working, start)
        detail_count = sum(1 for line in working[start + 1 : end] if _clean_string(line))
        replacement = [
            header,
            f"- {detail_count} generated diagnostic line(s) compacted for transport; canonical dashboard state is retained.",
            "",
        ]
        working[start:end] = replacement
        compacted.append(header[:-1])

    prompt = "\n".join(working).strip() + "\n"
    if compacted and len(prompt) <= MAX_PROMPT_CHARS:
        return prompt
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt += (
            "\nPROMPT BUDGET NOTICE:\n"
            f"- The protected user-authored payload exceeds {MAX_PROMPT_CHARS} characters. "
            "It was preserved without truncation; generated optional diagnostics were compacted first.\n"
        )
    return prompt


def _build_prompt_package(state: Dict[str, Any]) -> str:
    state = _normalize_state(state)
    text = state["text"]
    active_images = _active_image_rows_for_state(state["images"], state)
    active_videos = [item for item in state["videos"] if _is_active_video(item)]
    control_only_bindings = _parse_control_only_bindings(text)[0]
    picker_state = state.get("picker") if isinstance(state.get("picker"), dict) else {}
    frame_metadata = picker_state.get("frame_metadata", [])

    lines: List[str] = ["HMB_GP_Production", ""]

    lines.append("TARGET GENERATOR:")
    lines.append("This prompt is written for the active downstream target generator or execution system.")
    lines.append("")

    lines.append("IMAGE SOURCE:")
    if active_images:
        for item in active_images:
            seq = int(item.get("slot") or 1)
            label = _clean_string(item.get("label")) or f"image source {seq}"
            asset_id = _clean_string(item.get("asset_id"))
            asset_id_suffix = f" / Asset ID: {asset_id}" if asset_id else ""
            color_text = _color_pick_text(item)
            color_suffix = f" / Color Pick: {color_text}" if color_text else ""
            lines.append(
                f"@image{seq} = {label}{asset_id_suffix}{color_suffix}"
            )
        lines.append(
            "Color Pick values = target, mask, and reference-routing addresses; not final intrinsic "
            "color, material, lighting, or background appearance authority"
        )
    else:
        lines.append("No image source assigned in HMBPromptLibrary.")
    lines.append("")

    if active_images:
        lines.append("IMAGE ROLE MAP:")
        for item in active_images:
            seq = int(item.get("slot") or 1)
            lines.append(_image_role_line(item, seq))
        lines.append("")

        repl = [line for item in active_images for line in [_image_replacement_line(item, int(item.get("slot") or 1))] if line]
        if repl:
            lines.append("REPLACEMENT BINDING:")
            lines.extend(repl)
            lines.append("")

        target_function_bindings = [
            line
            for item in active_images
            for line in _image_target_function_lines(item, int(item.get("slot") or 1))
        ]
        if target_function_bindings:
            lines.append("TARGET FUNCTION BINDING:")
            lines.extend(target_function_bindings)
            lines.append("")

    if control_only_bindings:
        lines.append("CONTROL-ONLY BINDING:")
        lines.extend(_format_control_only_binding(entry) for entry in control_only_bindings)
        lines.append("")

    lines.append("VIDEO SOURCE:")
    if active_videos:
        active_slots_text = ", ".join(f"@video{int(item.get('slot') or 1)}" for item in active_videos)
        lines.append(f"Active video slots = {active_slots_text}")
        for item in active_videos:
            seq = int(item.get("slot") or 1)
            label = _clean_string(item.get("label")) or f"video source {seq}"
            if _clean_string(item.get("picker_auto_label")):
                label = _video_file_stem(label)
            lines.append(f"@video{seq} = {label}")
        lines.append("")
        lines.append("VIDEO ROLE MAP:")
        for item in active_videos:
            seq = int(item.get("slot") or 1)
            lines.append(_video_role_line(item, seq, active_images, control_only_bindings))
            semantic_summary = _motion_guide_semantic_summary_line(item, seq)
            if semantic_summary:
                lines.append(semantic_summary)
        lines.append("")
        alignment_lines, _alignment_conflicts = _self_scoped_alignment_evaluation(
            active_images,
            active_videos,
            control_only_bindings,
            frame_metadata,
        )
        if alignment_lines:
            lines.append("SELF-SCOPED REFERENCE ALIGNMENT:")
            lines.extend(alignment_lines)
            lines.append("")
        if any(int(item.get("slot") or 1) > 1 for item in active_videos):
            lines.append("ADDITIVE MULTI-VIDEO BINDING SCHEMA:")
            lines.append("Every active video slot is independent; no slot, companion, Color Pick, image source, or local binding is required merely because another video is present.")
            lines.append("Explicit reciprocal image or structured control-only bindings add exact local Targets and boundaries when supplied.")
            lines.append(
                "Recognized self-scoped role tuples provide a default attribute interpretation; an explicit "
                "scoped instruction may change only its named property for a named target or clearly scene-wide "
                "scope; if no temporal subset is stated or clearly implied, it applies to the whole shot, otherwise only to that subset."
            )
            lines.append("Decoded metadata is validated for internal file/schema integrity. Cross-source alignment is enforced only when explicit Picker companion provenance declares those files as one bundle.")
            lines.append("Missing optional metadata or bindings never invents data and never blocks use of the sources that are present.")
            lines.append("")
    else:
        lines.append("No video source assigned in HMBPromptLibrary.")
    lines.append("")

    valid_frame_bindings = _valid_frame_range_bindings(
        state,
        active_images,
        active_videos,
    )
    if valid_frame_bindings:
        lines.append("FRAME RANGE BINDING:")
        emitted_timebases: set[int] = set()
        for _item, binding, metadata in valid_frame_bindings:
            slot = _video_slot_number(binding.get("video_slot"), MAX_VIDEOS)
            if slot in emitted_timebases:
                continue
            emitted_timebases.add(slot)
            fps = float(metadata.get("fps") or 0.0)
            start_frame = int(metadata.get("start_frame"))
            end_frame = int(metadata.get("end_frame"))
            if fps > 0:
                lines.append(
                    f"Timebase = @video{slot} / {fps:g} FPS / "
                    f"Frames {start_frame}–{end_frame}"
                )
            else:
                lines.append(
                    f"Frame domain = @video{slot} / Manual / "
                    f"Frames {start_frame}–{end_frame}"
                )
        for item, binding, _metadata in valid_frame_bindings:
            image_slot = int(item.get("slot") or 1)
            slot = _video_slot_number(binding.get("video_slot"), MAX_VIDEOS)
            color = _clean_string(binding.get("color_pick"))
            ranges = binding.get("ranges") if isinstance(binding.get("ranges"), list) else []
            range_text = " and ".join(
                f"{int(frame_range.get('start') or 0)}–{int(frame_range.get('end') or 0)}"
                for frame_range in ranges
            )
            lines.append(
                f"@image{image_slot} replaces the @video{slot} {color} marker "
                f"during Frames {range_text} only."
            )
        lines.append("")

    preserved_entries, preserved_errors = _parse_preserved_text(text.get("PRESERVED_TEXT"))
    unverified_preserved_text = _unverified_preserved_text_lines(text.get("PRESERVED_TEXT"))
    authority_diagnostics = _find_source_authority_conflicts(
        active_images,
        active_videos,
        text,
        frame_metadata,
    )
    _control_bindings, control_binding_errors = _parse_control_only_bindings(text)
    _alignment_reports, alignment_errors = _self_scoped_alignment_evaluation(
        active_images,
        active_videos,
        _control_bindings,
        frame_metadata,
    )
    active_video_slots = {
        int(item.get("slot") or 1)
        for item in active_videos
    }
    frame_range_warnings: List[str] = []
    for item in active_images:
        _binding, _metadata, range_errors = _frame_range_binding_validation(
            state,
            item,
            active_video_slots,
        )
        token = f"@image{int(item.get('slot') or 1)}"
        frame_range_warnings.extend(
            f"{token} {error}"
            for error in range_errors
        )
    picker_state = state.get("picker") if isinstance(state.get("picker"), dict) else {}
    technical_frame_errors = [
        error
        for error in frame_range_warnings
        if any(
            marker in error
            for marker in (
                "conflicting or incomplete",
                "START after END",
                "Invalid frame range",
                " is outside ",
            )
        )
    ]
    technical_errors = [*alignment_errors, *technical_frame_errors]
    technical_errors.extend(
        _clean_string(item)
        for item in picker_state.get("contract_errors", [])
        if _clean_string(item)
    )
    technical_errors.extend(
        diagnostic
        for diagnostic in authority_diagnostics
        if " exceeds " in diagnostic
    )
    technical_errors = list(dict.fromkeys(technical_errors))
    interpretation_notes = [
        diagnostic
        for diagnostic in authority_diagnostics
        if diagnostic not in technical_errors
    ]
    if interpretation_notes:
        lines.append("SOURCE INTERPRETATION NOTES:")
        for note in interpretation_notes:
            lines.append(f"- {note}")
        lines.append(
            "These notes describe ambiguity without deleting supplied ideas; every source remains available "
            "within the attributes its readable evidence supports or an explicit scoped exception."
        )
        lines.append("")
    if technical_errors:
        lines.append("SOURCE DATA WARNINGS:")
        for conflict in technical_errors:
            lines.append(f"- {conflict}")
        lines.append(
            "Exact schema, provenance, or matched-authority interpretation is withheld only where it cannot "
            "be verified. Every supplied source and the user goal remain independently usable."
        )
        lines.append("")

    description_payload: Dict[str, Any] = {}
    for key in TEXT_FIELD_NAMES:
        if key == "PRESERVED_TEXT":
            continue
        value = _clean_string(text.get(key))
        if key in ("SCENE_CONTEXT", "VIDEO_VFX"):
            value = _strip_control_only_binding_lines(value)
        if value:
            description_payload[key] = value
    if preserved_entries:
        description_payload["PRESERVED_TEXT"] = preserved_entries
    connected_source_fallbacks = [
        f"[{entry['source']} / {entry['reason']}] {entry['text']}"
        for entry in _normalize_source_intent_fallbacks(
            state.get(_SOURCE_INTENT_FALLBACKS_KEY)
        )
    ]
    descriptive_fallbacks = list(dict.fromkeys([
        *unverified_preserved_text,
        *connected_source_fallbacks,
    ]))
    if descriptive_fallbacks:
        description_payload["PRESERVED_TEXT_DESCRIPTIVE_FALLBACK"] = descriptive_fallbacks
        description_payload["CONNECTED_SOURCE_INTENT_POLICY"] = (
            "Every readable fallback is ordinary user intent available to the current goal immediately; "
            "it is not a prerequisite, lower-priority idea, or reason to block output."
        )
    frame_range_intent = {
        f"@image{int(item.get('slot') or 1)}": {
            "selected_color_index": int(item.get("frame_range_color_index") or 0),
            "bindings": _normalize_frame_range_bindings(
                item.get("frame_range_bindings"),
                item.get("frame_range_binding"),
            ),
        }
        for item in active_images
        if bool(item.get("frame_range_enabled"))
    }
    if frame_range_intent:
        description_payload["FRAME_RANGE_INTENT"] = {
            "policy": (
                "Every readable range remains available to the current goal immediately; inactive addresses or "
                "missing metadata do not erase or demote it."
            ),
            "sources": frame_range_intent,
        }
    legacy_relationship_payload = {
        f"@image{int(item.get('slot') or 1)}": [
            _clean_string(value)
            for value in item.get("legacy_relationship_targets", [])
            if _clean_string(value)
        ]
        for item in active_images
        if any(
            _clean_string(value)
            for value in item.get("legacy_relationship_targets", [])
        )
    }
    if legacy_relationship_payload:
        description_payload["RELATIONSHIP_TARGETS"] = {
            "interpretation": (
                "Every supplied Target is available to the current user goal immediately. The first Target is "
                "the dashboard selection, while additional Targets remain equally usable relationship intent."
            ),
            "sources": legacy_relationship_payload,
        }
    keep_out_payload = {
        f"@video{int(item.get('slot') or 1)}": _clean_string(item.get("keep_out"))
        for item in active_videos
        if _clean_string(item.get("keep_out"))
    }
    if keep_out_payload:
        description_payload["KEEP_OUT"] = keep_out_payload
    if description_payload:
        lines.append("USER DESCRIPTION DATA (JSON):")
        lines.append(json.dumps(description_payload, ensure_ascii=False, separators=(",", ":")))
        lines.append("")

    return _compile_prompt_with_budget(lines)


def _prompt_semantic_fingerprint(state: Dict[str, Any]) -> str:
    """Return a stable identity for fields that can affect PROMPT_OUT.

    ``ui`` is persisted workflow geometry/presentation and ``status`` is fully
    derived by normalization. Neither is read by the prompt compiler, so those
    updates must not rebuild or propagate an identical paid-Agent input.
    """
    normalized = _normalize_state(state)
    semantic_state = {
        key: value
        for key, value in normalized.items()
        if key not in {"ui", "status"}
    }
    canonical = json.dumps(
        semantic_state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stage_and_notify_prompt_output(
    node: Any,
    value: Any,
    *,
    stage_output: bool = True,
    replace_pending: bool = True,
) -> None:
    """Stage PROMPT_OUT before notifying an already-connected downstream node."""
    if stage_output:
        set_output(node, "PROMPT_OUT", value)
    if replace_pending:
        generation = (
            int(getattr(node, "_hmb_prompt_notification_generation", 0)) + 1
        )
        node._hmb_prompt_notification_generation = generation
        node._hmb_pending_prompt_notification = (generation, value)
    publisher = getattr(node, "publish_update_to_parameter", None)
    if not callable(publisher):
        node._hmb_pending_prompt_notification = None
        return
    pending = getattr(node, "_hmb_pending_prompt_notification", None)
    if not isinstance(pending, tuple) or len(pending) != 2:
        return
    owner_generation, pending_value = pending
    current_pending = getattr(node, "_hmb_pending_prompt_notification", None)
    if (
        not isinstance(current_pending, tuple)
        or len(current_pending) != 2
        or current_pending[0] != owner_generation
        or current_pending is not pending
    ):
        return
    try:
        publisher("PROMPT_OUT", pending_value)
    except Exception:
        # A synchronous subscriber may re-enter this node and publish a newer
        # generation before the older callback returns (or throws).  Only the
        # still-owned generation may remain pending or surface its failure.
        current_pending = getattr(
            node,
            "_hmb_pending_prompt_notification",
            None,
        )
        if (
            isinstance(current_pending, tuple)
            and len(current_pending) == 2
            and current_pending[0] == owner_generation
            and current_pending is pending
        ):
            raise
        return
    current_pending = getattr(node, "_hmb_pending_prompt_notification", None)
    if (
        isinstance(current_pending, tuple)
        and len(current_pending) == 2
        and current_pending[0] == owner_generation
        and current_pending is pending
    ):
        node._hmb_pending_prompt_notification = None


class HMBPromptLibrary(DataNode):
    """HMBPromptLibrary.

    Independent source-binding and prompt-authoring dashboard with four equal
    production modes: Prompt only, Prompt + IMAGE_ASSET_IN, Prompt + PICKER_IN,
    and Prompt + both inputs. IMAGE_ASSET_IN and PICKER_IN are optional in all
    modes; neither input is a prerequisite.
    PROMPT_OUT is available in every mode and is the canonical parent edge for
    HMBAgentLibrary automation.
    Verified Project Asset data establishes Project, Asset ID, Image Name, Main
    Type, and the registered Image Sub Type. Target starts from a Main-Type
    default but remains freely editable. External IMAGE_IMPORT_IN rows establish
    Image Name and generator order only. Prompt keeps Target, Color Pick, and
    custom user intent editable.
    Picker data synchronizes video-slot lifecycle, generated video paths, and exact Asset ID-to-Image Name appearance-replacement Color Pick bindings.
    Native image rows may bind one or many supplied Targets, Image Sub Types, video addresses, and appearance markers. Verified Asset rows keep their one registered Sub Type across every local binding while Target remains editable.
    Every video row is independently usable in any slot. Video Sub Type, Keep Out, image-derived boundaries, and structured CONTROL_ONLY_BINDING lines add meaning when supplied; omitted fields remain optional and never require another source or companion.
    Media remains connected through external loaders.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.category = "HMB_GP_Production"
        self.description = (
            "Independent HMB prompt authoring with four valid modes: Prompt "
            "only, +Image Asset, +Video Picker, or +both; PROMPT_OUT is always "
            "available as the canonical HMBAgentLibrary input"
        )
        self._hmb_ui_syncing = False
        self._hmb_picker_connected = False
        self._hmb_image_asset_connected = False
        self._hmb_sync_lock = threading.RLock()
        self._hmb_sync_generation = 0
        self._hmb_last_prompt_semantic_fingerprint = ""
        self._hmb_last_prompt_output = None
        self._hmb_prompt_notification_generation = 0
        self._hmb_pending_prompt_notification = None
        try:
            self.ui_options = {"width": 1800, "height": PROMPT_START_HEIGHT, "default_width": 1800, "default_height": PROMPT_START_HEIGHT, "preferred_width": 1800, "preferred_height": PROMPT_START_HEIGHT, "initial_width": 1800, "initial_height": PROMPT_START_HEIGHT, "node_size": {"width": 1800, "height": PROMPT_START_HEIGHT}, "default_size": {"width": 1800, "height": PROMPT_START_HEIGHT}, "initial_size": {"width": 1800, "height": PROMPT_START_HEIGHT}, "min_width": 760, "min_height": PROMPT_MIN_HEIGHT, "resizable": True}
            self.width = 1800
            self.height = PROMPT_START_HEIGHT
        except Exception as exc:
            _diagnostic_exception("Prompt node UI sizing failed", exc)

        _add_image_asset_input(self)
        _add_picker_input(self)
        self._ensure_prompt_output()
        add_group(self, "A_HMB_PROMPT_LIBRARY_DASHBOARD", "HMB_GP_Production", collapsed=False)
        _add_widget_state_parameter(self)
        self._ensure_prompt_output()
        try:
            self._sync_prompt_output_from_state()
        except Exception as exc:
            _diagnostic_exception("Initial PROMPT_OUT synchronization failed", exc)

    def _ensure_prompt_output(self) -> None:
        try:
            _add_image_asset_input(self)
        except Exception as exc:
            _diagnostic_exception("IMAGE_ASSET_IN parameter setup failed", exc)
        try:
            _add_picker_input(self)
        except Exception as exc:
            _diagnostic_exception("PICKER_IN parameter setup failed", exc)
        try:
            _add_prompt_output(self)
        except Exception as exc:
            _diagnostic_exception("PROMPT_OUT parameter setup failed", exc)

    def _current_state(self) -> Dict[str, Any]:
        self._ensure_prompt_output()
        state = _parse_state(_get_parameter_raw(self, WIDGET_PARAMETER_NAME))
        if not state:
            state = _default_widget_state()
        return state

    def _write_dashboard_state(self) -> Dict[str, Any]:
        if getattr(self, "_hmb_ui_syncing", False):
            return self._current_state()
        try:
            self._hmb_ui_syncing = True
            raw_widget_value = _get_parameter_raw(self, WIDGET_PARAMETER_NAME)
            current_state = self._current_state()
            state = _normalize_state(current_state)
            image_asset_payload = _parse_image_asset_payload(
                _get_parameter_raw(self, IMAGE_ASSET_INPUT_PARAMETER_NAME)
            )
            image_asset_connected = bool(
                getattr(self, "_hmb_image_asset_connected", False)
                or image_asset_payload
            )
            state = _apply_image_asset_payload(
                state,
                image_asset_payload,
                connected=image_asset_connected,
            )
            picker_payload = _parse_picker_payload(_get_parameter_raw(self, PICKER_INPUT_PARAMETER_NAME))
            picker_connected = bool(getattr(self, "_hmb_picker_connected", False) or picker_payload)
            state = _apply_picker_payload(state, picker_payload, connected=picker_connected)
            # A widget edit has already stored its complete canonical state before
            # this deferred synchronization runs. Writing the same value back
            # produces a second frontend props update and can remount the full
            # dashboard after a local select/Range change. Keep canonicalization
            # and Picker synchronization authoritative, but publish the widget
            # parameter only when either operation actually changed its value.
            if state != current_state or not isinstance(raw_widget_value, str):
                _set_parameter_value(self, WIDGET_PARAMETER_NAME, _json_dumps(state))
            return state
        finally:
            self._hmb_ui_syncing = False

    def _sync_prompt_output_from_state(self) -> Dict[str, Any]:
        """Commit the latest widget state and refresh PROMPT_OUT immediately.

        The paid Agent may be run directly after editing the dashboard.  PROMPT_OUT
        must therefore never depend on a separate HMBPromptLibrary run or on the
        editor losing focus first.
        """
        state = self._write_dashboard_state()
        fingerprint = _prompt_semantic_fingerprint(state)
        output_values = getattr(self, "parameter_output_values", {})
        output_getter = getattr(output_values, "get", None)
        current_output = output_getter("PROMPT_OUT") if callable(output_getter) else None
        cached_output = getattr(self, "_hmb_last_prompt_output", None)
        if (
            fingerprint
            == getattr(self, "_hmb_last_prompt_semantic_fingerprint", "")
            and cached_output is not None
        ):
            if current_output != cached_output:
                _stage_and_notify_prompt_output(self, cached_output)
            elif getattr(self, "_hmb_pending_prompt_notification", None):
                _stage_and_notify_prompt_output(
                    self,
                    cached_output,
                    stage_output=False,
                    replace_pending=False,
                )
            return state

        prompt = _build_prompt_package(state)
        self._hmb_last_prompt_semantic_fingerprint = fingerprint
        self._hmb_last_prompt_output = prompt
        if current_output != prompt:
            _stage_and_notify_prompt_output(self, prompt)
        elif getattr(self, "_hmb_pending_prompt_notification", None):
            _stage_and_notify_prompt_output(
                self,
                prompt,
                stage_output=False,
                replace_pending=False,
            )
        return state

    def _sync_prompt_output_now(self) -> Dict[str, Any]:
        """Invalidate queued callbacks and commit one authoritative snapshot."""
        with self._hmb_sync_lock:
            self._hmb_sync_generation += 1
            return self._sync_prompt_output_from_state()

    def _schedule_prompt_sync(self) -> None:
        """Schedule on the host loop, or synchronize on the current host thread.

        Griptape node/parameter APIs are host-thread state.  A raw
        ``threading.Timer`` fallback could call them concurrently with the
        editor transaction, so environments without a running host loop use a
        guarded synchronous commit instead.
        """
        with self._hmb_sync_lock:
            self._hmb_sync_generation += 1
            generation = self._hmb_sync_generation

        def run_sync() -> None:
            try:
                with self._hmb_sync_lock:
                    if generation != self._hmb_sync_generation:
                        return
                    self._sync_prompt_output_from_state()
            except Exception as exc:
                _diagnostic_exception("Deferred PROMPT_OUT synchronization failed", exc)

        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore
            event_loop = GriptapeNodes.EventManager().event_loop
            if event_loop is not None and event_loop.is_running():
                event_loop.call_soon_threadsafe(run_sync)
                return
        except ImportError:
            pass
        except Exception as exc:
            _diagnostic_exception("Event-loop deferred sync scheduling failed", exc)
        run_sync()

    def after_value_set(self, parameter: Any, value: Any) -> Any:
        result = None
        try:
            parent_hook = getattr(super(), "after_value_set", None)
            if callable(parent_hook):
                result = parent_hook(parameter, value)
        except AttributeError:
            result = None
        except Exception as exc:
            _diagnostic_exception("Parent after_value_set failed", exc)
        try:
            name = getattr(parameter, "name", "") or ""
            if name == PICKER_INPUT_PARAMETER_NAME and _clean_string(value):
                self._hmb_picker_connected = True
            if name == IMAGE_ASSET_INPUT_PARAMETER_NAME and _clean_string(value):
                self._hmb_image_asset_connected = True
            if name in {
                WIDGET_PARAMETER_NAME,
                PICKER_INPUT_PARAMETER_NAME,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
            } and not getattr(self, "_hmb_ui_syncing", False):
                self._schedule_prompt_sync()
        except Exception as exc:
            _diagnostic_exception("after_value_set scheduling failed", exc)
        return result

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        try:
            target_name = getattr(target_parameter, "name", "")
            if target_name in {
                PICKER_INPUT_PARAMETER_NAME,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
            }:
                if target_name == PICKER_INPUT_PARAMETER_NAME:
                    self._hmb_picker_connected = True
                else:
                    self._hmb_image_asset_connected = True
                source_name = getattr(source_parameter, "name", "")
                sentinel = object()
                value: Any = sentinel
                outputs = getattr(source_node, "parameter_output_values", {})
                if source_name and source_name in outputs:
                    value = outputs[source_name]
                elif source_name:
                    values = getattr(source_node, "parameter_values", {})
                    if source_name in values:
                        value = values[source_name]
                    else:
                        try:
                            value = source_node.get_parameter_value(source_name)
                        except Exception:
                            value = sentinel
                if value is not sentinel:
                    _set_parameter_value(self, target_name, value)
                self._sync_prompt_output_now()
        except Exception as exc:
            _diagnostic_exception("Incoming source connection synchronization failed", exc)
        try:
            return super().after_incoming_connection(source_node, source_parameter, target_parameter)
        except Exception as exc:
            _diagnostic_exception("Parent incoming connection hook failed", exc)
            return None

    def after_incoming_connection_removed(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        try:
            target_name = getattr(target_parameter, "name", "")
            if target_name in {
                PICKER_INPUT_PARAMETER_NAME,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
            }:
                if target_name == PICKER_INPUT_PARAMETER_NAME:
                    self._hmb_picker_connected = False
                else:
                    self._hmb_image_asset_connected = False
                try:
                    _set_parameter_value(self, target_name, "")
                except Exception as exc:
                    _diagnostic_exception("Source input clear failed", exc)
                self._sync_prompt_output_now()
        except Exception as exc:
            _diagnostic_exception("Picker disconnect synchronization failed", exc)
        try:
            return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)
        except Exception as exc:
            _diagnostic_exception("Parent incoming connection removal hook failed", exc)
            return None

    def _restore_picker_connection_state(self) -> None:
        try:
            image_asset_payload = _parse_image_asset_payload(
                _get_parameter_raw(self, IMAGE_ASSET_INPUT_PARAMETER_NAME)
            )
            if image_asset_payload:
                self._hmb_image_asset_connected = True
            payload = _parse_picker_payload(_get_parameter_raw(self, PICKER_INPUT_PARAMETER_NAME))
            if payload:
                self._hmb_picker_connected = True
            self._sync_prompt_output_now()
        except Exception as exc:
            _diagnostic_exception("Picker connection state restore failed", exc)

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            result = super().after_deserialize(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent after_deserialize hook failed", exc)
        self._ensure_prompt_output()
        self._restore_picker_connection_state()
        return result

    def after_load(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            result = super().after_load(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent after_load hook failed", exc)
        self._ensure_prompt_output()
        self._restore_picker_connection_state()
        return result

    def on_loaded(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            result = super().on_loaded(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent on_loaded hook failed", exc)
        self._ensure_prompt_output()
        self._restore_picker_connection_state()
        return result

    def process(self) -> None:
        self._ensure_prompt_output()
        self._sync_prompt_output_now()
        return None
