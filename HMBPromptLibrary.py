from __future__ import annotations

import copy
from pathlib import Path
import hashlib
import importlib.util
import json
import logging
import math
import re
import sys
import threading
from typing import Any, Dict, List, Sequence

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _load_hmb_common():
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


# Legacy/manual Prompt authoring retains its established fifty-image capacity.
# Remote Shot routing is a narrower projection: each Shot publishes at most
# thirty ordered image addresses. Generator-specific limits remain downstream.
MAX_IMAGES = 50
MAX_SHOT_IMAGES = 30
MAX_VIDEOS = 10
PROMPT_POLICY_SOURCE_VERSION = "2026-08-12.agent-shot-quality.v4.2"
PROMPT_POLICY_SOURCE_CONTRACT_SHA256 = (
    "7a40ddf71c115ddef29b3bc428ccd9024649d9fac5af607b96173c1cf77b2199"
)
PROMPT_POLICY_CANDIDATE_VERSION = "2026-08-12.agent-shot-quality.v4.2"
PROMPT_POLICY_CANDIDATE_CONTRACT_SHA256 = (
    "7a40ddf71c115ddef29b3bc428ccd9024649d9fac5af607b96173c1cf77b2199"
)
PROMPT_POLICY_CANDIDATE_STATUS = "active"
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
VIDEO_WIDE_RANGE_MARKER = "Video-wide"
VIDEO_REFERENCE_CAPABILITIES_SCHEMA = "hmb-video-reference-capabilities"
VIDEO_REFERENCE_CAPABILITIES_VERSION = 1
VIDEO_FRAME_DOMAIN_SCHEMA = "hmb-video-frame-domain"
VIDEO_FRAME_DOMAIN_VERSION = 1
FX_TIMING_CONTRACT_SCHEMA = "hmb-fx-timing-source-facts"
FX_TIMING_CONTRACT_VERSION = 3
FX_TIMING_CONTRACT_HEADER = "FX/TIMING SOURCE DATA (JSON):"
PUBLIC_JOB_CONTRACT_SCHEMA = "hmb-public-job-data"
PUBLIC_JOB_CONTRACT_VERSION = 1
PUBLIC_JOB_CONTRACT_HEADER = "HMB JOB DATA (JSON):"
USER_DESCRIPTION_DATA_HEADER = "USER DESCRIPTION DATA (JSON):"
MAX_PUBLIC_PROMPT_FIELD_CHARS = 512
MAX_PUBLIC_PROMPT_LINE_CHARS = 4096
_PUBLIC_PROMPT_SECTION_HEADERS = (
    "TARGET GENERATOR:",
    "IMAGE SOURCE:",
    "IMAGE ROLE MAP:",
    "REPLACEMENT BINDING:",
    "VIDEO SOURCE:",
)
_PUBLIC_WINDOWS_PATH_PATTERN = re.compile(
    r"(?i)(?<![A-Z0-9_])(?:[A-Z]:[\\/]|\\\\)[^|;]*?(?=\s+/\s+|\s+\|\s+|;|$)"
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
SHOT_ASSET_INPUT_PARAMETER_NAME = "SHOT_ASSET_IN"
SHOT_IMAGE_OUTPUT_PARAMETER_NAME = "SHOT_IMAGE_OUT"
SHOT_PICKER_INPUT_PARAMETER_NAME = "SHOT_PICKER_IN"
SHOT_VIDEO_OUTPUT_PARAMETER_NAME = "SHOT_VIDEO_OUT"
SHOT_ROUTING_SNAPSHOT_SCHEMA = "hmb-shot-routing-snapshot"
SHOT_ROUTING_SNAPSHOT_VERSION = 1
SHOT_ROUTING_CATALOG_SCHEMA = "hmb-shot-routing-catalog"
SHOT_ROUTING_CATALOG_VERSION = 1
PICKER_SHOT_ROUTING_SNAPSHOT_SCHEMA = "hmb-picker-shot-routing-snapshot"
PICKER_SHOT_ROUTING_SNAPSHOT_VERSION = 1
SHOT_SELECTION_SCHEMA = "hmb-shot-selection"
SHOT_SELECTION_VERSION = 1
MAX_SHOTS = 5
WIDGET_NAME = "HMBPromptLibraryScopedBindingWidget"
WIDGET_LIBRARY_NAME = "HMB_GP_Production"
STATE_SCHEMA = "prompt-library-state"
MODE_NAME = "prompt_only_role_dashboard"
SOURCE_SYNC_REVISION_KEY = "source_sync_revision"
UI_EDIT_REVISION_KEY = "ui_edit_revision"
MANUAL_VIDEO_CONTEXT_KEY = "manual_video_context"
MAX_SOURCE_SYNC_REVISION = (1 << 53) - 1
UI_RESIZE_MODE = "stacked_outer_1000"
UI_HEADER_LAYOUT_VERSION = 2
LEGACY_IMAGE_SOURCES_DEFAULT_HEIGHT = 542
GROUP_START_HEIGHTS = {
    # Match VideoPicker's 68px header without changing the established
    # 1800x1193 outer size. Only the fresh/default image editor absorbs the
    # 10px delta; persisted user group heights remain authoritative.
    "imageSources": 514,
    "imageText": 200,
    "videoSources": 200,
    "videoText": 150,
}
GROUP_MIN_HEIGHTS = {
    # Keep the established 1193px minimum while reserving VideoPicker chrome.
    "imageSources": 514,
    "imageText": 200,
    "videoSources": 200,
    "videoText": 150,
}
GROUP_START_TOTAL_HEIGHT = sum(GROUP_START_HEIGHTS.values())
PROMPT_DASHBOARD_FIXED_HEIGHT = 129
# Native compatibility/dependency ports are retained on the graph but rendered
# as hidden rows. The custom dashboard therefore owns the full node.
PROMPT_NATIVE_ASSET_INPUT_ROW_HEIGHT = 0
PROMPT_START_HEIGHT = GROUP_START_TOTAL_HEIGHT + PROMPT_DASHBOARD_FIXED_HEIGHT
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
        "Local Motion Detail Only", "Secondary Motion Only",
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


def _public_single_line(value: Any, max_chars: int = MAX_PUBLIC_PROMPT_FIELD_CHARS) -> str:
    """Normalize untrusted public Prompt text to one bounded, control-free line."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()

    def replace_local_path(match: re.Match[str]) -> str:
        raw = match.group(0).strip().replace("\\", "/").rstrip("/")
        filename = raw.rsplit("/", 1)[-1].strip(" \t\"'")
        return filename or "[local path]"

    text = _PUBLIC_WINDOWS_PATH_PATTERN.sub(replace_local_path, text)
    return text[: max(0, int(max_chars))].rstrip()


def _public_path_basename(value: Any, fallback: str, *, strip_extension: bool) -> str:
    """Return a safe display label without publishing a local or remote path."""
    text = _public_single_line(value, MAX_PUBLIC_PROMPT_FIELD_CHARS)
    if not text:
        text = _public_single_line(fallback, MAX_PUBLIC_PROMPT_FIELD_CHARS)
    clean_path = text.split("?", 1)[0].split("#", 1)[0].replace("\\", "/").rstrip("/")
    filename = clean_path.rsplit("/", 1)[-1] or _public_single_line(
        fallback,
        MAX_PUBLIC_PROMPT_FIELD_CHARS,
    )
    if strip_extension:
        filename = Path(filename).stem or filename
    return _public_single_line(filename, MAX_PUBLIC_PROMPT_FIELD_CHARS)


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


def _connected_source_fingerprint(payload: Any, connected: bool) -> str:
    """Identify one authoritative Picker/Image input generation.

    Prompt widget edits round-trip through the frontend without the Picker-only
    transport fields stored on video rows.  Reapplying an unchanged connected
    payload restores those fields, but that enrichment is not a new upstream
    generation and must not advance ``source_sync_revision``.  The connection
    bit is part of the identity so a real disconnect remains authoritative.
    """

    source = payload if connected and isinstance(payload, dict) else {}
    try:
        canonical = json.dumps(
            {"connected": bool(connected), "payload": source},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except Exception:
        canonical = repr((bool(connected), source))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_UNSTRUCTURED_INPUT_KEY = "__hmb_unstructured_input__"
_SOURCE_INTENT_FALLBACKS_KEY = "source_intent_fallbacks"
_SOURCE_PARSE_DIAGNOSTIC_KIND = "parse_diagnostic"
_SOURCE_PARSE_DIAGNOSTIC_REASON = "invalid JSON connected input"
_SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE = "invalid_json"
_LEGACY_SOURCE_PARSE_FAILURE_REASON = "readable non-JSON connected input"
_HMB_CONNECTED_SIGNATURE_PREFIX_CHARS = 4096
_HMB_CONNECTED_SIGNATURES = {
    PICKER_INPUT_PARAMETER_NAME: {
        "schema": frozenset({"hmb-prompt-library-picker-binding"}),
        "mode": frozenset({"maya"}),
    },
    IMAGE_ASSET_INPUT_PARAMETER_NAME: {
        "schema": frozenset({"hmb-image-asset-library-binding"}),
        "mode": frozenset({"image_asset"}),
    },
}
_JSON_STRING_FIELD_PATTERN = re.compile(
    r'(?:\A|[,{])\s*"(?P<key>schema|mode)"\s*:\s*"(?P<value>[^"\\]*)"'
)
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
    "asset_project_uid",
    "image_name",
    "label",
    "path",
    "asset_path",
    "relative_path",
    "width",
    "height",
    "project_uid",
    "source_type",
    "custom_source_type",
    "scope_candidate",
    "scope",
    "sub_type",
    "color_pick_candidates",
    "selection_order",
    "slot",
    "identity",
    "binding_capabilities",
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
    "reference_capabilities",
    "frame_domain",
    "timing_cues",
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


def _machine_port_hmb_signature(source: Any, value: Any) -> bool:
    """Recognize an HMB machine payload without parsing or retaining its body."""

    source_name = _clean_string(source)
    allowed = _HMB_CONNECTED_SIGNATURES.get(source_name)
    text = value if isinstance(value, str) else ""
    prefix = text[:_HMB_CONNECTED_SIGNATURE_PREFIX_CHARS]
    if not allowed or not prefix.startswith("{"):
        return False
    matched: set[str] = set()
    for match in _JSON_STRING_FIELD_PATTERN.finditer(prefix):
        key = match.group("key")
        if match.group("value") in allowed.get(key, frozenset()):
            matched.add(key)
    return matched == set(allowed)


def _known_hmb_connected_payload(source: Any, payload: Any) -> bool:
    source_name = _clean_string(source)
    allowed = _HMB_CONNECTED_SIGNATURES.get(source_name)
    if not allowed or not isinstance(payload, dict):
        return False
    return all(
        _clean_string(payload.get(key)) in values
        for key, values in allowed.items()
    )


def _json_error_offset(value: str) -> int:
    try:
        json.loads(value)
    except json.JSONDecodeError as exc:
        return max(-1, int(exc.pos))
    except Exception:
        return -1
    return -1


def _source_parse_diagnostic(
    source: Any,
    value: Any,
    *,
    error_offset: Any = None,
    require_hmb_signature: bool = True,
) -> Dict[str, Any] | None:
    text = value if isinstance(value, str) else _readable_original(value)
    source_name = _clean_string(source)
    if (
        not text
        or source_name not in _HMB_CONNECTED_SIGNATURES
        or (
            require_hmb_signature
            and not _machine_port_hmb_signature(source_name, text)
        )
    ):
        return None
    try:
        offset = int(error_offset)
    except Exception:
        offset = _json_error_offset(text)
    raw = text.encode("utf-8")
    return {
        "kind": _SOURCE_PARSE_DIAGNOSTIC_KIND,
        "source": source_name,
        "reason": _SOURCE_PARSE_DIAGNOSTIC_REASON,
        "error_code": _SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE,
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "error_offset": max(-1, offset),
    }


def _normalize_source_parse_diagnostic(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    source = _clean_string(value.get("source"))
    if (
        value.get("kind") != _SOURCE_PARSE_DIAGNOSTIC_KIND
        or source not in _HMB_CONNECTED_SIGNATURES
        or _clean_string(value.get("error_code"))
        != _SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE
    ):
        return None
    try:
        byte_length = max(0, int(value.get("byte_length")))
        error_offset = max(-1, int(value.get("error_offset")))
    except Exception:
        return None
    sha256 = _clean_string(value.get("sha256")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        return None
    return {
        "kind": _SOURCE_PARSE_DIAGNOSTIC_KIND,
        "source": source,
        "reason": _SOURCE_PARSE_DIAGNOSTIC_REASON,
        "error_code": _SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE,
        "byte_length": byte_length,
        "sha256": sha256,
        "error_offset": error_offset,
    }


def _source_intent_entry(source: Any, reason: Any, value: Any) -> Dict[str, str] | None:
    # Connected operator prose is ordinary user data, not a transport budget.
    # Preserve string bytes exactly; use trimming only to reject blank values.
    text = value if isinstance(value, str) else _readable_original(value)
    if not text or not text.strip():
        return None
    return {
        "source": _clean_string(source) or "CONNECTED_SOURCE",
        "reason": _clean_string(reason) or "readable unstructured input",
        "text": text,
    }


def _normalize_source_intent_fallbacks(value: Any) -> List[Dict[str, Any]]:
    raw_entries = value if isinstance(value, (list, tuple)) else [value]
    out: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    diagnostic_positions: Dict[str, int] = {}
    for raw in raw_entries:
        if isinstance(raw, dict):
            diagnostic = _normalize_source_parse_diagnostic(raw)
            if (
                diagnostic is None
                and raw.get("kind") == _SOURCE_PARSE_DIAGNOSTIC_KIND
            ):
                diagnostic = _source_parse_diagnostic(
                    raw.get("source"),
                    raw.get("text"),
                    error_offset=raw.get("error_offset"),
                )
                if diagnostic is None:
                    entry = _source_intent_entry(
                        raw.get("source"),
                        raw.get("reason"),
                        raw.get("text"),
                    )
                    if entry is not None:
                        signature = (
                            entry["source"],
                            entry["reason"],
                            entry["text"],
                        )
                        if signature not in seen:
                            seen.add(signature)
                            out.append(entry)
                    continue
            if diagnostic is None and (
                _clean_string(raw.get("reason"))
                == _LEGACY_SOURCE_PARSE_FAILURE_REASON
            ):
                diagnostic = _source_parse_diagnostic(
                    raw.get("source"),
                    raw.get("text"),
                )
            if diagnostic is not None:
                source = diagnostic["source"]
                position = diagnostic_positions.get(source)
                if position is None:
                    diagnostic_positions[source] = len(out)
                    out.append(diagnostic)
                else:
                    out[position] = diagnostic
                continue
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


def _prune_source_parse_diagnostic(state: Dict[str, Any], source: Any) -> None:
    source_name = _clean_string(source)
    state[_SOURCE_INTENT_FALLBACKS_KEY] = [
        entry
        for entry in _normalize_source_intent_fallbacks(
            state.get(_SOURCE_INTENT_FALLBACKS_KEY)
        )
        if not (
            entry.get("kind") == _SOURCE_PARSE_DIAGNOSTIC_KIND
            and entry.get("source") == source_name
        )
    ]


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


def _append_source_parse_diagnostic(
    state: Dict[str, Any], diagnostic: Any
) -> None:
    entry = _normalize_source_parse_diagnostic(diagnostic)
    if entry is None:
        return
    state[_SOURCE_INTENT_FALLBACKS_KEY] = _normalize_source_intent_fallbacks(
        [
            *_normalize_source_intent_fallbacks(
                state.get(_SOURCE_INTENT_FALLBACKS_KEY)
            ),
            entry,
        ]
    )


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


def _unstructured_payload_entries(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return _normalize_source_intent_fallbacks(payload.get(_UNSTRUCTURED_INPUT_KEY))


_TIMING_CUE_PHASES = frozenset({"point", "onset", "peak", "falloff", "end"})
_LOCAL_POINT_UNITS = frozenset({
    "scene_unit", "millimeter", "centimeter", "meter", "inch", "foot"
})
_LOCAL_POINT_UNIT_ALIASES = {
    "scene_unit": "scene_unit",
    "scene unit": "scene_unit",
    "mm": "millimeter",
    "millimeter": "millimeter",
    "millimeters": "millimeter",
    "cm": "centimeter",
    "centimeter": "centimeter",
    "centimeters": "centimeter",
    "m": "meter",
    "meter": "meter",
    "meters": "meter",
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "ft": "foot",
    "foot": "foot",
    "feet": "foot",
}
_MAX_TIMING_CUES_PER_VIDEO = 256


def _strict_int(value: Any) -> int | None:
    """Return an exact integer without coercing arbitrary transport text."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _normalize_video_reference_capabilities(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}
    version = _strict_int(value.get("version"))
    identity_fields = value.get("marker_instance_identity_fields")
    return {
        "schema": _clean_string(value.get("schema")),
        "version": version,
        "frame_addressable": value.get("frame_addressable")
        if isinstance(value.get("frame_addressable"), bool)
        else None,
        "exact_emitter_cues": value.get("exact_emitter_cues")
        if isinstance(value.get("exact_emitter_cues"), bool)
        else None,
        "image_source_frame_ranges": value.get("image_source_frame_ranges")
        if isinstance(value.get("image_source_frame_ranges"), bool)
        else None,
        "marker_instance_identity_fields": [
            _clean_string(field)
            for field in identity_fields
            if _clean_string(field)
        ][:4]
        if isinstance(identity_fields, (list, tuple))
        else [],
    }


def _normalize_video_frame_domain(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}
    return {
        "schema": _clean_string(value.get("schema")),
        "version": _strict_int(value.get("version")),
        "timebase": _clean_string(value.get("timebase")),
        "start_frame": _strict_int(value.get("start_frame")),
        "end_frame": _strict_int(value.get("end_frame")),
        "frame_count": _strict_int(value.get("frame_count")),
        "range_addressable": value.get("range_addressable")
        if isinstance(value.get("range_addressable"), bool)
        else None,
    }


def _normalize_emitter(value: Any) -> Dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        key: _clean_string(raw.get(key))
        for key in (
            "marker_color", "asset_id", "subject_root", "maya_uuid", "full_dag_path"
        )
        if _clean_string(raw.get(key))
    }


def _normalize_local_point(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    kind = _clean_string(value.get("kind")).casefold()
    if kind == "locator":
        locator_id = _clean_string(value.get("locator_id"))[:MAX_IDENTIFIER_CHARS]
        locator_path = _clean_string(value.get("locator_path"))[:MAX_DESCRIPTION_CHARS]
        if not locator_id and not locator_path:
            return {}
        return {
            "kind": "locator",
            "locator_id": locator_id,
            "locator_path": locator_path,
        }
    if kind == "coordinates":
        space = _clean_string(value.get("space")).casefold()
        raw_unit = _clean_string(value.get("unit")).casefold()
        unit = _LOCAL_POINT_UNIT_ALIASES.get(raw_unit, "")
        xyz = value.get("xyz")
        if (
            space not in {"local", "object"}
            or unit not in _LOCAL_POINT_UNITS
            or not isinstance(xyz, (list, tuple))
            or len(xyz) != 3
            or any(
                isinstance(component, bool)
                or not isinstance(component, (int, float))
                or not math.isfinite(float(component))
                for component in xyz
            )
        ):
            return {}
        return {
            "kind": "coordinates",
            "space": space,
            "unit": unit,
            "xyz": [float(component) for component in xyz],
        }
    return {}


def _normalize_video_timing_cues(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value[:_MAX_TIMING_CUES_PER_VIDEO]:
        if not isinstance(raw, dict):
            continue
        emitter = _normalize_emitter(raw.get("emitter"))
        local_point = _normalize_local_point(raw.get("local_point"))
        cue = {
            "schema": _clean_string(raw.get("schema")),
            "version": _strict_int(raw.get("version")),
            "cue_id": _clean_string(raw.get("cue_id"))[:MAX_IDENTIFIER_CHARS],
            "cue_type": _clean_string(raw.get("cue_type")),
            "cue_phase": _clean_string(raw.get("cue_phase")).casefold(),
            "frame": _strict_int(raw.get("frame")),
            "emitter": emitter,
            "local_point": local_point,
        }
        description = _clean_string(raw.get("description"))
        if description:
            cue["description"] = description[:MAX_DESCRIPTION_CHARS]
        signature = json.dumps(
            cue,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if signature in seen:
            continue
        seen.add(signature)
        out.append(cue)

    # Picker-authored IDs identify a cue only when they are unique.  If two
    # distinct valid cues reuse one supplied ID, suffix every member with its
    # content signature.  The result is stable across Picker row reordering and
    # stays within the same 256-character public identifier bound.
    cue_id_counts: Dict[str, int] = {}
    for cue in out:
        cue_id = _clean_string(cue.get("cue_id"))
        cue_id_counts[cue_id] = cue_id_counts.get(cue_id, 0) + 1
    for cue in out:
        cue_id = _clean_string(cue.get("cue_id"))
        if not cue_id or cue_id_counts.get(cue_id, 0) < 2:
            continue
        content = {
            key: nested
            for key, nested in cue.items()
            if key != "cue_id"
        }
        digest = hashlib.sha256(
            json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        prefix = cue_id[: MAX_IDENTIFIER_CHARS - len(digest) - 1]
        cue["cue_id"] = f"{prefix}-{digest}"
    return out


def _video_reference_transport_errors(item: Dict[str, Any]) -> List[str]:
    """Validate Picker transport fields without treating them as creative text."""

    errors: List[str] = []
    capabilities = item.get("reference_capabilities")
    if capabilities not in (None, "", {}) and not isinstance(capabilities, dict):
        errors.append("reference_capabilities must be an object")
    elif isinstance(capabilities, dict) and capabilities:
        if (
            capabilities.get("schema") != VIDEO_REFERENCE_CAPABILITIES_SCHEMA
            or capabilities.get("version") != VIDEO_REFERENCE_CAPABILITIES_VERSION
        ):
            errors.append("reference_capabilities schema/version is invalid")
        for key in (
            "frame_addressable",
            "exact_emitter_cues",
            "image_source_frame_ranges",
        ):
            if not isinstance(capabilities.get(key), bool):
                errors.append(f"reference_capabilities.{key} must be boolean")
        identity_fields = capabilities.get("marker_instance_identity_fields")
        allowed_identity_fields = {
            "marker_color", "asset_id", "subject_root", "maya_uuid", "full_dag_path"
        }
        if not isinstance(identity_fields, list) or any(
            field not in allowed_identity_fields for field in identity_fields
        ):
            errors.append(
                "reference_capabilities.marker_instance_identity_fields is invalid"
            )

    frame_domain = item.get("frame_domain")
    if frame_domain not in (None, "", {}) and not isinstance(frame_domain, dict):
        errors.append("frame_domain must be an object")
    elif isinstance(frame_domain, dict) and frame_domain:
        if (
            frame_domain.get("schema") != "hmb-video-frame-domain"
            or frame_domain.get("version") != 1
        ):
            errors.append("frame_domain schema/version is invalid")
        start = frame_domain.get("start_frame")
        end = frame_domain.get("end_frame")
        count = frame_domain.get("frame_count")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (start, end, count)):
            errors.append("frame_domain requires integer start/end/count")
        elif start > end or count != end - start + 1:
            errors.append("frame_domain start/end/count do not agree")
        if not isinstance(frame_domain.get("range_addressable"), bool):
            errors.append("frame_domain.range_addressable must be boolean")

    cues = item.get("timing_cues")
    if cues not in (None, "", []) and not isinstance(cues, list):
        errors.append("timing_cues must be a list")
    elif isinstance(cues, list):
        for index, cue in enumerate(cues, start=1):
            prefix = f"timing_cues[{index}]"
            if (
                not isinstance(cue, dict)
                or cue.get("schema") != "hmb-video-emitter-timing-cue"
                or cue.get("version") != 1
            ):
                errors.append(f"{prefix} schema/version is invalid")
                continue
            if not _clean_string(cue.get("cue_id")):
                errors.append(f"{prefix}.cue_id is required")
            if cue.get("cue_type") != "emitter_point":
                errors.append(f"{prefix}.cue_type must be emitter_point")
            if cue.get("cue_phase") not in _TIMING_CUE_PHASES:
                errors.append(f"{prefix}.cue_phase is invalid")
            frame = cue.get("frame")
            if not isinstance(frame, int) or isinstance(frame, bool):
                errors.append(f"{prefix}.frame must be an integer")
            emitter = cue.get("emitter")
            if (
                not isinstance(emitter, dict)
                or not _clean_string(emitter.get("marker_color"))
                or not any(
                    _clean_string(emitter.get(key))
                    for key in (
                        "asset_id", "subject_root", "maya_uuid", "full_dag_path"
                    )
                )
            ):
                errors.append(f"{prefix}.emitter requires an exact address")
            if not _normalize_local_point(cue.get("local_point")):
                errors.append(f"{prefix}.local_point requires an exact locator or coordinates")
            if (
                isinstance(frame, int)
                and isinstance(frame_domain, dict)
                and isinstance(frame_domain.get("start_frame"), int)
                and isinstance(frame_domain.get("end_frame"), int)
                and not (
                    int(frame_domain["start_frame"])
                    <= frame
                    <= int(frame_domain["end_frame"])
                )
            ):
                errors.append(f"{prefix}.frame is outside frame_domain")
    return list(dict.fromkeys(errors))



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
        "actor_color_pick_choices": image_color_pick_choices_for_source_type(
            "Character Appearance"
        ),
        "object_color_pick_choices": image_color_pick_choices_for_source_type(
            "Prop / Accessory"
        ),
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
        # Picker-authored transport facts. They do not change any dashboard
        # control; they make FX/Timing frame addresses machine-verifiable.
        "reference_capabilities": {},
        "frame_domain": {},
        "timing_cues": [],
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
        SOURCE_SYNC_REVISION_KEY: 0,
        UI_EDIT_REVISION_KEY: 0,
        "image_taxonomy": _image_taxonomy_payload(),
        # This is the only durable Prompt-side shot selection.  The upstream
        # catalog and its media stay on the graph-connected Image Asset node.
        "shot": {
            "shot_uuid": "",
            "channel_uuid": "",
            "name": "Only",
            "number": 1,
            "selected_source_uids": [],
        },
        "images": [_default_image_item(slot) for slot in range(1, 5)],
        "videos": [_default_video_item(1)],
        "text": dict(TEXT_FIELD_DEFAULTS),
        _SOURCE_INTENT_FALLBACKS_KEY: [],
        "ui": {
            "group_heights": {},
            "textarea_heights": {},
            "resize_mode": UI_RESIZE_MODE,
            "header_layout_version": UI_HEADER_LAYOUT_VERSION,
            "language": "ko",
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
            MANUAL_VIDEO_CONTEXT_KEY: {},
            "slot_suppressions": {},
            "scene": "",
            "video_path": "",
            "camera": "",
            "markers": [],
            "frame_metadata": [],
            "matched_images": 0,
            "shot_catalog": [],
            "shot_routing": {},
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
            # Read-only transport projection used to render the five remote
            # shot choices. It is rebuilt from the connected source snapshot;
            # no media is serialized into HMB_UI_STATE.
            "shot_catalog": [],
            "shot_catalog_routing": {},
            "shot_routing": {},
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
        normalized_binding = {
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
        if "enabled" in raw or "enabled" in previous:
            normalized_binding["enabled"] = (
                raw.get("enabled") is True
                if "enabled" in raw
                else previous.get("enabled") is True
            )
        out[key] = normalized_binding
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
    # Range ON by itself is not an authored video-wide instruction.  The
    # widget stores an explicit ``@videoN::`` binding as soon as the user edits
    # the markerless external-video domain; only that concrete blank-address
    # record may enter the video-wide validation path.
    if not color:
        return None
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


def _video_wide_frame_range_allowed(
    state: Dict[str, Any], video_slot: Any, color_pick: Any
) -> bool:
    """Allow a markerless range only for a connected markerless Picker slot.

    An externally imported video has no Maya Color Pick catalog.  Its range is
    therefore a video-wide temporal address rather than an image-replacement
    marker address.  A normal Picker slot with one or more marker colors keeps
    the existing exact-Color-Pick requirement.
    """

    if _clean_string(color_pick):
        return False
    picker = state.get("picker") if isinstance(state.get("picker"), dict) else {}
    if not bool(picker.get("enabled") and not picker.get("awaiting_data")):
        return False
    slot = _video_slot_number(video_slot, MAX_VIDEOS)
    marker_colors = {
        _clean_string(marker.get("color"))
        for marker in (
            picker.get("markers") if isinstance(picker.get("markers"), list) else []
        )
        if isinstance(marker, dict)
        and _video_slot_number(marker.get("video_slot"), MAX_VIDEOS) == slot
        and _clean_string(marker.get("color"))
    }
    metadata = next(
        (
            entry
            for entry in _normalize_frame_metadata(picker.get("frame_metadata"))
            if _video_slot_number(entry.get("video_slot"), MAX_VIDEOS) == slot
        ),
        None,
    )
    if isinstance(metadata, dict):
        colors = metadata.get("available_color_picks")
        return isinstance(colors, list) and not colors and not marker_colors
    return not marker_colors


def _public_frame_range_marker(
    state: Dict[str, Any], video_slot: Any, color_pick: Any
) -> str:
    color = _clean_string(color_pick)
    if color:
        return color
    return (
        VIDEO_WIDE_RANGE_MARKER
        if _video_wide_frame_range_allowed(state, video_slot, color)
        else ""
    )


def _active_frame_range_bindings(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return current Range ON plus explicitly enabled additional bindings."""

    if not bool(item.get("frame_range_enabled")):
        return []
    current = _current_frame_range_binding(item)
    bindings = _normalize_frame_range_bindings(
        item.get("frame_range_bindings"),
        item.get("frame_range_binding"),
    )
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(current, dict):
        key = _frame_binding_key(
            current.get("video_slot"), current.get("color_pick")
        )
        seen.add(key)
        out.append(dict(current))
    for binding in bindings.values():
        if not isinstance(binding, dict) or binding.get("enabled") is not True:
            continue
        key = _frame_binding_key(
            binding.get("video_slot"), binding.get("color_pick")
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(binding))
    return out



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


def _effective_image_source_type(item: Dict[str, Any]) -> str:
    source_type = _clean_string(item.get("source_type"))
    if source_type == "Role Required / Select Source Type":
        source_type = ""
    if source_type == "Custom":
        return _clean_string(item.get("custom_source_type")) or "Unspecified custom image role"
    return source_type or "Unspecified image role"


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

def _color_pick_text(
    item: Dict[str, Any],
    include_video: bool = True,
    active_video_slots: set[int] | None = None,
) -> str:
    parts: List[str] = []
    for entry in _image_binding_entries(item):
        marker_video = int(entry.get("marker_video") or 1)
        if (
            active_video_slots is not None
            and marker_video not in active_video_slots
        ):
            continue
        color = entry["color"]
        if not color:
            continue
        marker = f"@video{marker_video} / {color}" if include_video else color
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
    try:
        header_layout_version = max(0, int(float(ui.get("header_layout_version") or 0)))
    except Exception:
        header_layout_version = 0
    try:
        legacy_image_height = int(round(float(source_heights.get("imageSources"))))
    except Exception:
        legacy_image_height = -1
    legacy_companion_defaults = True
    for key in ("imageText", "videoSources", "videoText"):
        if key not in source_heights:
            continue
        try:
            if int(round(float(source_heights.get(key)))) != GROUP_START_HEIGHTS[key]:
                legacy_companion_defaults = False
        except Exception:
            legacy_companion_defaults = False
    legacy_default_layout = bool(
        compatible
        and header_layout_version < UI_HEADER_LAYOUT_VERSION
        and legacy_image_height == LEGACY_IMAGE_SOURCES_DEFAULT_HEIGHT
        and legacy_companion_defaults
    )
    group_heights: Dict[str, int] = {}
    for key, min_height in GROUP_MIN_HEIGHTS.items():
        try:
            value = (
                GROUP_START_HEIGHTS["imageSources"]
                if key == "imageSources" and legacy_default_layout
                else int(round(float(source_heights.get(key))))
            )
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
    language = "en" if language == "en" else "ko"
    return {
        "group_heights": group_heights,
        "textarea_heights": textarea_heights,
        "resize_mode": UI_RESIZE_MODE,
        "header_layout_version": UI_HEADER_LAYOUT_VERSION,
        "language": language,
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
    out["reference_capabilities"] = _normalize_video_reference_capabilities(
        item.get("reference_capabilities")
    )
    out["frame_domain"] = _normalize_video_frame_domain(
        item.get("frame_domain")
    )
    out["timing_cues"] = _normalize_video_timing_cues(
        item.get("timing_cues")
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
            out["control_role"] = ""
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
    # Keep the factual Maya preview type but remove the stale combined
    # authority. Primary is valid only when the user explicitly selects the
    # distinct Unified Shot-Control Video main type.
    if (
        out.get("source_type") == "Maya Preview / Playblast"
        and out.get("control_role") == "Primary Unified Shot Control"
    ):
        out["control_role"] = ""
        out["custom_control_role"] = ""
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


_MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS = (
    "color_picks",
    "binding_scopes",
    "binding_custom_scopes",
    "binding_video_slots",
    "marker_video",
    "preview_marker",
    "picker_auto_video",
    "picker_auto_color",
    "picker_auto_source",
    "frame_range_enabled",
    "frame_range_color_index",
    "frame_range_bindings",
    "frame_range_binding",
    "frame_range_selected_index",
)


def _manual_video_context_image_identity(
    item: Dict[str, Any],
    index: int,
) -> str:
    source_uid = _clean_string(
        item.get("asset_source_uid") or item.get("source_uid")
    )
    if source_uid:
        return f"uid:{source_uid}"
    asset_id = _clean_string(item.get("asset_id"))
    if asset_id:
        return f"asset:{asset_id}"
    return f"slot:{index + 1}"


def _manual_video_context_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    """Capture only fields that video-slot remapping may mutate."""

    text_source = state.get("text") if isinstance(state.get("text"), dict) else {}
    text = {
        key: copy.deepcopy(text_source.get(key, ""))
        for key in TEXT_FIELD_DEFAULTS
        if key != "PRESERVED_TEXT"
    }
    images: List[Dict[str, Any]] = []
    for index, item in enumerate(
        state.get("images", []) if isinstance(state.get("images"), list) else []
    ):
        if not isinstance(item, dict) or index >= MAX_IMAGES:
            continue
        images.append({
            "identity": _manual_video_context_image_identity(item, index),
            "index": index,
            "fields": {
                field: copy.deepcopy(item.get(field))
                for field in _MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS
            },
        })
    ui = state.get("ui") if isinstance(state.get("ui"), dict) else {}
    textarea_heights = (
        ui.get("textarea_heights")
        if isinstance(ui.get("textarea_heights"), dict)
        else {}
    )
    return {
        "text": text,
        "images": images,
        "textarea_heights": copy.deepcopy(textarea_heights),
    }


def _normalize_manual_video_context_snapshot(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    text_source = value.get("text") if isinstance(value.get("text"), dict) else {}
    text = {
        key: _clean_string(text_source.get(key))[:MAX_PROMPT_CHARS]
        for key in TEXT_FIELD_DEFAULTS
        if key != "PRESERVED_TEXT"
    }
    images: List[Dict[str, Any]] = []
    raw_images = value.get("images") if isinstance(value.get("images"), list) else []
    for fallback_index, raw in enumerate(raw_images[:MAX_IMAGES]):
        if not isinstance(raw, dict):
            continue
        try:
            index = max(0, min(MAX_IMAGES - 1, int(raw.get("index", fallback_index))))
        except Exception:
            index = fallback_index
        fields_source = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
        normalized_item = _migrate_old_image_item(fields_source, index + 1)
        images.append({
            "identity": _clean_string(raw.get("identity")) or f"slot:{index + 1}",
            "index": index,
            "fields": {
                field: copy.deepcopy(normalized_item.get(field))
                for field in _MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS
            },
        })
    textarea_source = (
        value.get("textarea_heights")
        if isinstance(value.get("textarea_heights"), dict)
        else {}
    )
    textarea_heights = _normalize_ui({
        "ui": {
            "textarea_heights": textarea_source,
            "resize_mode": UI_RESIZE_MODE,
        },
    }).get("textarea_heights", {})
    return {
        "text": text,
        "images": images,
        "textarea_heights": textarea_heights,
    }


def _normalize_manual_video_context(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    version = value.get("version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != 1
        or not isinstance(value.get("before"), dict)
        or not isinstance(
        value.get("after"), dict
        )
    ):
        return {}
    return {
        "version": 1,
        "before": _normalize_manual_video_context_snapshot(value.get("before")),
        "after": _normalize_manual_video_context_snapshot(value.get("after")),
    }


def _mapping_entry_matches(
    left: Dict[str, Any],
    right: Dict[str, Any],
    key: str,
) -> bool:
    return (key in left) == (key in right) and left.get(key) == right.get(key)


def _replace_mapping_entry(
    target: Dict[str, Any],
    source: Dict[str, Any],
    key: str,
) -> None:
    if key in source:
        target[key] = copy.deepcopy(source[key])
    else:
        target.pop(key, None)


def _manual_video_context_image_records(
    snapshot: Dict[str, Any],
) -> Dict[tuple[str, Any], Dict[str, Any]]:
    raw_records = [
        record
        for record in snapshot.get("images", [])
        if isinstance(record, dict)
    ]
    stable_identity_counts: Dict[str, int] = {}
    for record in raw_records:
        identity = _clean_string(record.get("identity"))
        if identity.startswith(("uid:", "asset:")):
            stable_identity_counts[identity] = (
                stable_identity_counts.get(identity, 0) + 1
            )

    records: Dict[tuple[str, Any], Dict[str, Any]] = {}
    for fallback_index, record in enumerate(raw_records):
        if not isinstance(record, dict):
            continue
        try:
            index = int(record.get("index", fallback_index))
        except Exception:
            index = fallback_index
        identity = _clean_string(record.get("identity")) or f"slot:{index + 1}"
        # Asset/source identity survives ImageAsset reorder.  Index is only a
        # fallback for anonymous or duplicate rows where identity cannot pick
        # one record unambiguously.
        key: tuple[str, Any] = (
            ("identity", identity)
            if identity.startswith(("uid:", "asset:"))
            and stable_identity_counts.get(identity) == 1
            else ("index", index)
        )
        records[key] = record
    return records


def _advance_manual_video_context(
    current_context: Any,
    before_sync: Dict[str, Any],
    after_sync: Dict[str, Any],
) -> Dict[str, Any]:
    """Advance automatic baselines without claiming user-authored edits."""

    normalized = _normalize_manual_video_context(current_context)
    if not normalized:
        return {
            "version": 1,
            "before": copy.deepcopy(before_sync),
            "after": copy.deepcopy(after_sync),
        }
    old_after = normalized["after"]
    next_after = copy.deepcopy(old_after)
    old_text = old_after.get("text", {})
    before_text = before_sync.get("text", {})
    after_text = after_sync.get("text", {})
    next_text = next_after.setdefault("text", {})
    for key in set(old_text) | set(before_text) | set(after_text):
        if _mapping_entry_matches(before_text, old_text, key):
            _replace_mapping_entry(next_text, after_text, key)

    old_images = _manual_video_context_image_records(old_after)
    before_images = _manual_video_context_image_records(before_sync)
    after_images = _manual_video_context_image_records(after_sync)
    next_images = _manual_video_context_image_records(next_after)
    for record_key, old_record in old_images.items():
        before_record = before_images.get(record_key)
        after_record = after_images.get(record_key)
        next_record = next_images.get(record_key)
        if not before_record or not after_record or not next_record:
            continue
        old_fields = old_record.get("fields", {})
        before_fields = before_record.get("fields", {})
        after_fields = after_record.get("fields", {})
        next_fields = next_record.setdefault("fields", {})
        for field in _MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS:
            if _mapping_entry_matches(before_fields, old_fields, field):
                _replace_mapping_entry(next_fields, after_fields, field)

    old_heights = old_after.get("textarea_heights", {})
    before_heights = before_sync.get("textarea_heights", {})
    after_heights = after_sync.get("textarea_heights", {})
    next_heights = next_after.setdefault("textarea_heights", {})
    for key in set(old_heights) | set(before_heights) | set(after_heights):
        if _mapping_entry_matches(before_heights, old_heights, key):
            _replace_mapping_entry(next_heights, after_heights, key)
    return {
        "version": 1,
        "before": normalized["before"],
        "after": next_after,
    }


def _restore_manual_video_context(
    state: Dict[str, Any],
    context: Any,
) -> None:
    """Three-way restore automatic remaps while preserving later user edits."""

    normalized = _normalize_manual_video_context(context)
    if not normalized:
        return
    original = normalized["before"]
    automatic = normalized["after"]
    current = _manual_video_context_snapshot(state)

    state_text = state.get("text") if isinstance(state.get("text"), dict) else {}
    state["text"] = state_text
    original_text = original.get("text", {})
    automatic_text = automatic.get("text", {})
    current_text = current.get("text", {})
    for key in set(original_text) | set(automatic_text):
        if _mapping_entry_matches(current_text, automatic_text, key):
            _replace_mapping_entry(state_text, original_text, key)

    original_images = _manual_video_context_image_records(original)
    automatic_images = _manual_video_context_image_records(automatic)
    current_images = _manual_video_context_image_records(current)
    state_images = state.get("images") if isinstance(state.get("images"), list) else []
    for record_key, automatic_record in automatic_images.items():
        original_record = original_images.get(record_key)
        current_record = current_images.get(record_key)
        if not original_record or not current_record:
            continue
        try:
            index = int(current_record.get("index", -1))
        except Exception:
            continue
        if index < 0 or index >= len(state_images) or not isinstance(state_images[index], dict):
            continue
        automatic_fields = automatic_record.get("fields", {})
        original_fields = original_record.get("fields", {})
        current_fields = current_record.get("fields", {})
        for field in _MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS:
            if _mapping_entry_matches(current_fields, automatic_fields, field):
                _replace_mapping_entry(state_images[index], original_fields, field)

    ui = state.get("ui") if isinstance(state.get("ui"), dict) else {}
    state["ui"] = ui
    state_heights = (
        ui.get("textarea_heights")
        if isinstance(ui.get("textarea_heights"), dict)
        else {}
    )
    ui["textarea_heights"] = state_heights
    original_heights = original.get("textarea_heights", {})
    automatic_heights = automatic.get("textarea_heights", {})
    current_heights = current.get("textarea_heights", {})
    for key in set(original_heights) | set(automatic_heights):
        if _mapping_entry_matches(current_heights, automatic_heights, key):
            _replace_mapping_entry(state_heights, original_heights, key)


def _normalize_shot_selection(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    shot_uuid = _clean_string(source.get("shot_uuid"))[:128]
    channel_uuid = _clean_string(source.get("channel_uuid"))[:128]
    bound = bool(shot_uuid and channel_uuid)
    try:
        number = int(source.get("number") or 1) if bound else 1
    except Exception:
        number = 1
    number = max(1, min(MAX_SHOTS, number))
    selected_source_uids: List[str] = []
    seen: set[str] = set()
    raw_uids = source.get("selected_source_uids") if bound else []
    if isinstance(raw_uids, (list, tuple)):
        for raw_uid in raw_uids:
            uid = _clean_string(raw_uid)[:MAX_IDENTIFIER_CHARS]
            if not uid or uid in seen:
                continue
            seen.add(uid)
            selected_source_uids.append(uid)
            if len(selected_source_uids) >= MAX_SHOT_IMAGES:
                break
    name = (
        _clean_string(source.get("name"))[:128] or f"Shot {number}"
        if bound
        else "Only"
    )
    return {
        "shot_uuid": shot_uuid if bound else "",
        "channel_uuid": channel_uuid if bound else "",
        "name": name,
        "number": number,
        "selected_source_uids": selected_source_uids,
    }


def _normalize_shot_catalog(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: List[Dict[str, Any]] = []
    seen_uuids: set[str] = set()
    seen_numbers: set[int] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        shot = _normalize_shot_selection(raw)
        shot_uuid = shot["shot_uuid"]
        number = shot["number"]
        if not shot_uuid or shot_uuid in seen_uuids or number in seen_numbers:
            continue
        seen_uuids.add(shot_uuid)
        seen_numbers.add(number)
        result.append(shot)
        if len(result) >= MAX_SHOTS:
            break
    return sorted(result, key=lambda item: (int(item["number"]), item["shot_uuid"]))


def _normalize_shot_routing(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    try:
        generation = int(source.get("generation") or 0)
    except Exception:
        generation = 0
    generation = max(0, min(MAX_SOURCE_SYNC_REVISION, generation))
    try:
        media_count = max(0, int(source.get("media_count") or 0))
    except Exception:
        media_count = 0
    result = {
        "publisher_instance_uuid": _clean_string(
            source.get("publisher_instance_uuid")
        ),
        "channel_uuid": _clean_string(source.get("channel_uuid")),
        "generation": generation,
        "metadata_sha256": _clean_string(source.get("metadata_sha256")),
        "media_sha256": _clean_string(source.get("media_sha256")),
        "media_count": media_count,
        "media_order_sha256": _clean_string(
            source.get("media_order_sha256")
        ),
    }
    return result if any(result.values()) else {}


def _normalize_shot_catalog_routing(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    try:
        generation = int(source.get("generation") or 0)
    except Exception:
        generation = 0
    generation = max(0, min(MAX_SOURCE_SYNC_REVISION, generation))
    result = {
        "publisher_instance_uuid": _clean_string(
            source.get("publisher_instance_uuid")
        )[:128],
        "channel_uuid": _clean_string(source.get("channel_uuid"))[:128],
        "generation": generation,
        "metadata_sha256": _clean_string(source.get("metadata_sha256")),
    }
    return result if any(result.values()) else {}


class _ShotRoutingContractError(RuntimeError):
    """The graph-connected shot publisher failed its closed snapshot contract."""


_SHOT_METADATA_PRIVATE_MEDIA_KEYS = frozenset({
    "path",
    "asset_path",
    "video_path",
    "project_video_path",
    "video_url",
    "media",
    "media_value",
    "data",
    "data_uri",
    "base64",
    "blob",
    "bytes",
    "binary",
    "url",
    "relative_path",
})
_SHOT_METADATA_PRIVATE_KEY_TOKENS = (
    "sidecar",
    "thumbnail",
    "thumb",
    "cache",
)
_SHOT_METADATA_IDENTITY_PATH_KEYS = frozenset({
    # Maya DAG identities are semantic scene addresses, not local media paths.
    "full_dag_path",
})


def _is_maya_full_dag_path(value: Any) -> bool:
    """Recognize a Maya DAG identity without accepting disguised file paths."""

    if not isinstance(value, str) or value != value.strip():
        return False
    if not value.startswith("|") or len(value) > 4096:
        return False
    if "/" in value or "\\" in value:
        return False
    parts = value[1:].split("|")
    return bool(parts) and all(
        part and not any(ord(character) < 32 for character in part)
        for part in parts
    )


def _looks_like_private_media_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    lowered = text.casefold()
    return bool(
        lowered.startswith(("data:", "file:", "http://", "https://"))
        or re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE)
        or re.match(r"^[a-z]:[\\/]", text, re.IGNORECASE)
        or text.startswith(("\\\\", "//", "/", "~/", "~\\"))
    )


def _metadata_contains_private_media(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = _clean_string(key).casefold()
            if (
                normalized_key in _SHOT_METADATA_PRIVATE_MEDIA_KEYS
                or "base64" in normalized_key
                or any(
                    token in normalized_key
                    for token in _SHOT_METADATA_PRIVATE_KEY_TOKENS
                )
                or (
                    normalized_key not in _SHOT_METADATA_IDENTITY_PATH_KEYS
                    and (
                        normalized_key.endswith("_path")
                        or normalized_key.endswith("_url")
                        or normalized_key.endswith("_file")
                        or normalized_key.endswith("_folder")
                        or normalized_key.endswith("_directory")
                    )
                )
                or (
                    normalized_key == "full_dag_path"
                    and not _is_maya_full_dag_path(item)
                )
            ):
                return True
            if _metadata_contains_private_media(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_metadata_contains_private_media(item) for item in value)
    return _looks_like_private_media_string(value)


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception as exc:
        raise _ShotRoutingContractError(
            "Shot routing snapshot contains non-serializable metadata."
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _validate_shot_routing_catalog(
    value: Any,
    *,
    expected_channel_uuid: str = "",
) -> Dict[str, Any]:
    """Validate compact selector identity without accepting any media facts."""

    if not isinstance(value, dict) or set(value) != {
        "schema",
        "version",
        "publisher_instance_uuid",
        "channel_uuid",
        "generation",
        "metadata_sha256",
        "shots",
    }:
        raise _ShotRoutingContractError("Shot routing catalog is malformed.")
    if (
        value.get("schema") != SHOT_ROUTING_CATALOG_SCHEMA
        or value.get("version") != SHOT_ROUTING_CATALOG_VERSION
    ):
        raise _ShotRoutingContractError("Shot routing catalog schema is invalid.")
    publisher = _clean_string(value.get("publisher_instance_uuid"))
    channel = _clean_string(value.get("channel_uuid"))
    generation = value.get("generation")
    if (
        not publisher
        or len(publisher) > 128
        or not channel
        or len(channel) > 128
        or (expected_channel_uuid and channel != _clean_string(expected_channel_uuid))
        or not isinstance(generation, int)
        or isinstance(generation, bool)
        or not 0 <= generation <= MAX_SOURCE_SYNC_REVISION
    ):
        raise _ShotRoutingContractError(
            "Shot routing catalog publisher/channel/generation is invalid."
        )
    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list) or not 1 <= len(raw_shots) <= MAX_SHOTS:
        raise _ShotRoutingContractError(
            "Shot routing catalog must contain one to five shots."
        )
    shots: List[Dict[str, Any]] = []
    shot_uuids: set[str] = set()
    shot_numbers: set[int] = set()
    for raw in raw_shots:
        if not isinstance(raw, dict) or set(raw) != {
            "shot_uuid", "number", "name", "revision"
        }:
            raise _ShotRoutingContractError(
                "A shot routing catalog record is invalid."
            )
        shot_uuid = _clean_string(raw.get("shot_uuid"))
        name = _clean_string(raw.get("name"))
        number = raw.get("number")
        revision = raw.get("revision")
        if (
            not shot_uuid
            or len(shot_uuid) > 128
            or shot_uuid in shot_uuids
            or not name
            or len(name) > 128
            or not isinstance(number, int)
            or isinstance(number, bool)
            or not 1 <= number <= MAX_SHOTS
            or number in shot_numbers
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or not 0 <= revision <= MAX_SOURCE_SYNC_REVISION
        ):
            raise _ShotRoutingContractError(
                "A shot routing catalog value is invalid or duplicated."
            )
        shot_uuids.add(shot_uuid)
        shot_numbers.add(number)
        shots.append({
            "shot_uuid": shot_uuid,
            "number": number,
            "name": name,
            "revision": revision,
        })
    contract = {
        "channel_uuid": channel,
        "generation": generation,
        "shots": shots,
    }
    metadata_sha256 = _clean_string(value.get("metadata_sha256"))
    if metadata_sha256 != _canonical_sha256(contract):
        raise _ShotRoutingContractError("Shot routing catalog hash is invalid.")
    return {
        "schema": SHOT_ROUTING_CATALOG_SCHEMA,
        "version": SHOT_ROUTING_CATALOG_VERSION,
        "publisher_instance_uuid": publisher,
        **contract,
        "metadata_sha256": metadata_sha256,
    }


def _validate_shot_routing_snapshot(
    value: Any,
    *,
    expected_channel_uuid: str = "",
    max_selected_sources: int = MAX_SHOT_IMAGES,
) -> Dict[str, Any]:
    """Validate one exact metadata/media generation from an upstream node.

    The two hashes deliberately cover both halves of the source publication.
    Prompt never joins a target-side JSON cache with media from another source
    generation; an address, order, duplicate publisher, or hash mismatch fails
    before PROMPT_OUT or either shot-media output can be published.
    """

    if not isinstance(value, dict):
        raise _ShotRoutingContractError("Shot routing snapshot is unavailable.")
    required = {
        "schema",
        "version",
        "publisher_instance_uuid",
        "channel_uuid",
        "generation",
        "metadata_sha256",
        "media_sha256",
        "shots",
        "ordered_assets",
        "media_by_source_uid",
    }
    if set(value) != required:
        raise _ShotRoutingContractError(
            "Shot routing snapshot has an unknown or missing field."
        )
    if (
        value.get("schema") != SHOT_ROUTING_SNAPSHOT_SCHEMA
        or value.get("version") != SHOT_ROUTING_SNAPSHOT_VERSION
    ):
        raise _ShotRoutingContractError("Shot routing snapshot schema is invalid.")
    publisher_instance_uuid = _clean_string(
        value.get("publisher_instance_uuid")
    )
    channel_uuid = _clean_string(value.get("channel_uuid"))
    if (
        not publisher_instance_uuid
        or not channel_uuid
        or len(publisher_instance_uuid) > 128
        or len(channel_uuid) > 128
    ):
        raise _ShotRoutingContractError(
            "Shot routing publisher or channel identity is missing."
        )
    expected_channel_uuid = _clean_string(expected_channel_uuid)
    if expected_channel_uuid and channel_uuid != expected_channel_uuid:
        raise _ShotRoutingContractError(
            "Shot routing channel does not match the Prompt subscription."
        )
    generation = value.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 0
        or generation > MAX_SOURCE_SYNC_REVISION
    ):
        raise _ShotRoutingContractError("Shot routing generation is invalid.")

    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list) or not 1 <= len(raw_shots) <= MAX_SHOTS:
        raise _ShotRoutingContractError("Shot routing must contain one to five shots.")
    shots: List[Dict[str, Any]] = []
    shot_uuids: set[str] = set()
    shot_numbers: set[int] = set()
    for raw_shot in raw_shots:
        if not isinstance(raw_shot, dict) or set(raw_shot) != {
            "shot_uuid",
            "number",
            "name",
            "revision",
            "selected_source_uids",
        }:
            raise _ShotRoutingContractError("A shot routing record is invalid.")
        shot_uuid = _clean_string(raw_shot.get("shot_uuid"))
        name = _clean_string(raw_shot.get("name"))
        number = raw_shot.get("number")
        revision = raw_shot.get("revision")
        raw_uids = raw_shot.get("selected_source_uids")
        if (
            not shot_uuid
            or len(shot_uuid) > 128
            or not name
            or len(name) > 128
            or not isinstance(number, int)
            or isinstance(number, bool)
            or not 1 <= number <= MAX_SHOTS
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 0
            or revision > MAX_SOURCE_SYNC_REVISION
            or not isinstance(raw_uids, list)
            or len(raw_uids) > max_selected_sources
        ):
            raise _ShotRoutingContractError("A shot routing value is invalid.")
        uids = [_clean_string(uid) for uid in raw_uids]
        if (
            any(not uid or len(uid) > MAX_IDENTIFIER_CHARS for uid in uids)
            or len(set(uids)) != len(uids)
        ):
            raise _ShotRoutingContractError(
                "A shot contains an empty or duplicate source address."
            )
        if shot_uuid in shot_uuids or number in shot_numbers:
            raise _ShotRoutingContractError("Shot identity is duplicated.")
        shot_uuids.add(shot_uuid)
        shot_numbers.add(number)
        shots.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
                "selected_source_uids": uids,
            }
        )

    raw_assets = value.get("ordered_assets")
    raw_media = value.get("media_by_source_uid")
    if not isinstance(raw_assets, list) or not isinstance(raw_media, dict):
        raise _ShotRoutingContractError("Shot routing source arrays are invalid.")
    ordered_assets: List[Dict[str, Any]] = []
    ordered_uids: List[str] = []
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, dict) or set(raw_asset) != {
            "source_uid",
            "metadata",
        }:
            raise _ShotRoutingContractError("A routed source record is invalid.")
        source_uid = _clean_string(raw_asset.get("source_uid"))
        metadata = raw_asset.get("metadata")
        if (
            not source_uid
            or len(source_uid) > MAX_IDENTIFIER_CHARS
            or source_uid in ordered_uids
            or not isinstance(metadata, dict)
            or _metadata_contains_private_media(metadata)
        ):
            raise _ShotRoutingContractError(
                "A routed source address is empty/duplicated or exposes media."
            )
        ordered_uids.append(source_uid)
        ordered_assets.append(
            {"source_uid": source_uid, "metadata": copy.deepcopy(metadata)}
        )
    if set(raw_media) != set(ordered_uids):
        raise _ShotRoutingContractError(
            "Shot routing metadata and media addresses do not match."
        )
    media_by_source_uid: Dict[str, str] = {}
    for source_uid in ordered_uids:
        media = raw_media.get(source_uid)
        if not isinstance(media, str) or not media:
            raise _ShotRoutingContractError("A routed source has no media value.")
        media_by_source_uid[source_uid] = media
    known = set(ordered_uids)
    if any(uid not in known for shot in shots for uid in shot["selected_source_uids"]):
        raise _ShotRoutingContractError(
            "A shot addresses media outside the published source generation."
        )

    metadata_contract = {
        "channel_uuid": channel_uuid,
        "generation": generation,
        "shots": shots,
        "ordered_assets": ordered_assets,
    }
    if _clean_string(value.get("metadata_sha256")) != _canonical_sha256(
        metadata_contract
    ):
        raise _ShotRoutingContractError("Shot metadata hash does not match.")
    media_descriptors = [
        {
            "source_uid": uid,
            "media_value_sha256": hashlib.sha256(
                media_by_source_uid[uid].encode("utf-8")
            ).hexdigest(),
        }
        for uid in ordered_uids
    ]
    if _clean_string(value.get("media_sha256")) != _canonical_sha256(
        {"media_descriptors": media_descriptors}
    ):
        raise _ShotRoutingContractError("Shot media hash does not match.")
    return {
        "schema": SHOT_ROUTING_SNAPSHOT_SCHEMA,
        "version": SHOT_ROUTING_SNAPSHOT_VERSION,
        "publisher_instance_uuid": publisher_instance_uuid,
        "channel_uuid": channel_uuid,
        "generation": generation,
        "metadata_sha256": _clean_string(value.get("metadata_sha256")),
        "media_sha256": _clean_string(value.get("media_sha256")),
        "shots": shots,
        "ordered_assets": ordered_assets,
        "media_by_source_uid": media_by_source_uid,
    }


def _validate_picker_shot_routing_snapshot(
    value: Any,
    *,
    expected_channel_uuid: str,
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise _ShotRoutingContractError("Picker shot routing snapshot is unavailable.")
    required = {
        "schema",
        "version",
        "publisher_instance_uuid",
        "channel_uuid",
        "generation",
        "metadata_sha256",
        "media_sha256",
        "shots",
        "ordered_videos",
        "media_by_source_uid",
    }
    if set(value) != required:
        raise _ShotRoutingContractError(
            "Picker shot routing snapshot has an unknown or missing field."
        )
    if (
        value.get("schema") != PICKER_SHOT_ROUTING_SNAPSHOT_SCHEMA
        or value.get("version") != PICKER_SHOT_ROUTING_SNAPSHOT_VERSION
    ):
        raise _ShotRoutingContractError(
            "Picker shot routing snapshot schema is invalid."
        )
    publisher = _clean_string(value.get("publisher_instance_uuid"))
    channel = _clean_string(value.get("channel_uuid"))
    if (
        not publisher
        or len(publisher) > 128
        or not channel
        or len(channel) > 128
        or channel != _clean_string(expected_channel_uuid)
    ):
        raise _ShotRoutingContractError(
            "Picker routing publisher/channel does not match Prompt."
        )
    generation = value.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or not 0 <= generation <= MAX_SOURCE_SYNC_REVISION
    ):
        raise _ShotRoutingContractError("Picker routing generation is invalid.")
    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list) or not 1 <= len(raw_shots) <= MAX_SHOTS:
        raise _ShotRoutingContractError(
            "Picker routing must contain one to five shots."
        )
    shots: List[Dict[str, Any]] = []
    shot_ids: set[str] = set()
    shot_numbers: set[int] = set()
    for raw in raw_shots:
        if not isinstance(raw, dict) or set(raw) != {
            "shot_uuid",
            "number",
            "name",
            "revision",
            "selected_source_uids",
            "picker_payload",
        }:
            raise _ShotRoutingContractError("A Picker shot record is invalid.")
        shot_uuid = _clean_string(raw.get("shot_uuid"))
        name = _clean_string(raw.get("name"))
        number = raw.get("number")
        revision = raw.get("revision")
        selected = raw.get("selected_source_uids")
        picker_payload = raw.get("picker_payload")
        if (
            not shot_uuid
            or len(shot_uuid) > 128
            or not name
            or len(name) > 128
            or not isinstance(number, int)
            or isinstance(number, bool)
            or not 1 <= number <= MAX_SHOTS
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or not 0 <= revision <= MAX_SOURCE_SYNC_REVISION
            or not isinstance(selected, list)
            or len(selected) > MAX_VIDEOS
            or not isinstance(picker_payload, dict)
        ):
            raise _ShotRoutingContractError("A Picker shot value is invalid.")
        uids = [_clean_string(uid) for uid in selected]
        if (
            any(not uid or len(uid) > MAX_IDENTIFIER_CHARS for uid in uids)
            or len(set(uids)) != len(uids)
            or shot_uuid in shot_ids
            or number in shot_numbers
        ):
            raise _ShotRoutingContractError(
                "Picker shot identity or source address is duplicated."
            )
        shot_ids.add(shot_uuid)
        shot_numbers.add(number)
        shots.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
                "selected_source_uids": uids,
                "picker_payload": copy.deepcopy(picker_payload),
            }
        )
    raw_videos = value.get("ordered_videos")
    raw_media = value.get("media_by_source_uid")
    if not isinstance(raw_videos, list) or not isinstance(raw_media, dict):
        raise _ShotRoutingContractError("Picker routing source arrays are invalid.")
    videos: List[Dict[str, Any]] = []
    ordered_uids: List[str] = []
    for raw in raw_videos:
        if not isinstance(raw, dict) or set(raw) != {"source_uid", "metadata"}:
            raise _ShotRoutingContractError("A routed video record is invalid.")
        uid = _clean_string(raw.get("source_uid"))
        metadata = raw.get("metadata")
        if (
            not uid
            or len(uid) > MAX_IDENTIFIER_CHARS
            or uid in ordered_uids
            or not isinstance(metadata, dict)
            or _metadata_contains_private_media(metadata)
        ):
            raise _ShotRoutingContractError(
                "A routed video address is empty/duplicated or exposes media."
            )
        ordered_uids.append(uid)
        videos.append({"source_uid": uid, "metadata": copy.deepcopy(metadata)})
    if set(raw_media) != set(ordered_uids):
        raise _ShotRoutingContractError(
            "Picker routing metadata and media addresses do not match."
        )
    media: Dict[str, str] = {}
    for uid in ordered_uids:
        value_at_uid = raw_media.get(uid)
        if not isinstance(value_at_uid, str) or not value_at_uid:
            raise _ShotRoutingContractError("A routed video has no media value.")
        media[uid] = value_at_uid
    known = set(ordered_uids)
    if any(uid not in known for shot in shots for uid in shot["selected_source_uids"]):
        raise _ShotRoutingContractError(
            "A Picker shot addresses unpublished video media."
        )
    if _clean_string(value.get("metadata_sha256")) != _canonical_sha256(
        {
            "channel_uuid": channel,
            "generation": generation,
            "shots": shots,
            "ordered_videos": videos,
        }
    ):
        raise _ShotRoutingContractError("Picker routing metadata hash does not match.")
    descriptors = [
        {
            "source_uid": uid,
            "media_value_sha256": hashlib.sha256(
                media[uid].encode("utf-8")
            ).hexdigest(),
        }
        for uid in ordered_uids
    ]
    if _clean_string(value.get("media_sha256")) != _canonical_sha256(
        {"media_descriptors": descriptors}
    ):
        raise _ShotRoutingContractError("Picker routing media hash does not match.")
    return {
        "schema": PICKER_SHOT_ROUTING_SNAPSHOT_SCHEMA,
        "version": PICKER_SHOT_ROUTING_SNAPSHOT_VERSION,
        "publisher_instance_uuid": publisher,
        "channel_uuid": channel,
        "generation": generation,
        "metadata_sha256": _clean_string(value.get("metadata_sha256")),
        "media_sha256": _clean_string(value.get("media_sha256")),
        "shots": shots,
        "ordered_videos": videos,
        "media_by_source_uid": media,
    }


def _select_routed_shot(
    snapshot: Dict[str, Any],
    current_shot: Any,
) -> Dict[str, Any]:
    current = _normalize_shot_selection(current_shot)
    shots = snapshot["shots"]
    selected: Dict[str, Any] | None = None
    if current["shot_uuid"]:
        selected = next(
            (
                shot
                for shot in shots
                if shot["shot_uuid"] == current["shot_uuid"]
            ),
            None,
        )
        if selected is None:
            raise _ShotRoutingContractError(
                "The selected shot is not present in the connected channel."
            )
    else:
        selected = next(
            (
                shot
                for shot in shots
                if int(shot["number"]) == int(current["number"])
            ),
            shots[0],
        )
    return {
        "shot_uuid": selected["shot_uuid"],
        "channel_uuid": snapshot["channel_uuid"],
        "name": selected["name"],
        "number": selected["number"],
        "selected_source_uids": list(selected["selected_source_uids"]),
    }


def _shot_catalog_from_snapshot(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "shot_uuid": shot["shot_uuid"],
            "channel_uuid": snapshot["channel_uuid"],
            "name": shot["name"],
            "number": shot["number"],
            "selected_source_uids": list(shot["selected_source_uids"]),
        }
        for shot in snapshot["shots"]
    ]


def _compact_catalog_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    shots = [
        {
            "shot_uuid": shot["shot_uuid"],
            "number": shot["number"],
            "name": shot["name"],
            "revision": shot["revision"],
        }
        for shot in snapshot["shots"]
    ]
    contract = {
        "channel_uuid": snapshot["channel_uuid"],
        "generation": snapshot["generation"],
        "shots": shots,
    }
    return {
        "schema": SHOT_ROUTING_CATALOG_SCHEMA,
        "version": SHOT_ROUTING_CATALOG_VERSION,
        "publisher_instance_uuid": snapshot["publisher_instance_uuid"],
        **contract,
        "metadata_sha256": _canonical_sha256(contract),
    }


def _catalog_routing_projection(catalog: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "publisher_instance_uuid": catalog["publisher_instance_uuid"],
        "channel_uuid": catalog["channel_uuid"],
        "generation": catalog["generation"],
        "metadata_sha256": catalog["metadata_sha256"],
    }


def _assert_monotonic_shot_catalog(
    previous: Any,
    catalog: Dict[str, Any],
) -> None:
    current = _normalize_shot_catalog_routing(previous)
    if not current:
        return
    if current["channel_uuid"] and current["channel_uuid"] != catalog["channel_uuid"]:
        raise _ShotRoutingContractError(
            "ImageAsset shot catalog channel changed unexpectedly."
        )
    if (
        current["publisher_instance_uuid"]
        and current["publisher_instance_uuid"] != catalog["publisher_instance_uuid"]
    ):
        raise _ShotRoutingContractError(
            "ImageAsset shot catalog duplicate/replaced publisher was rejected."
        )
    previous_generation = int(current["generation"])
    generation = int(catalog["generation"])
    if generation < previous_generation:
        raise _ShotRoutingContractError("ImageAsset shot catalog generation is stale.")
    if (
        generation == previous_generation
        and previous_generation
        and current.get("metadata_sha256")
        and current["metadata_sha256"] != catalog["metadata_sha256"]
    ):
        raise _ShotRoutingContractError(
            "ImageAsset shot catalog reused one generation with different data."
        )


def _routing_projection(
    snapshot: Dict[str, Any],
    selected_source_uids: List[str],
) -> Dict[str, Any]:
    return {
        "publisher_instance_uuid": snapshot["publisher_instance_uuid"],
        "channel_uuid": snapshot["channel_uuid"],
        "generation": snapshot["generation"],
        "metadata_sha256": snapshot["metadata_sha256"],
        "media_sha256": snapshot["media_sha256"],
        "media_count": len(selected_source_uids),
        "media_order_sha256": _canonical_sha256(
            {"selected_source_uids": selected_source_uids}
        ),
    }


def _assert_monotonic_shot_route(
    previous: Any,
    snapshot: Dict[str, Any],
    *,
    label: str,
) -> None:
    current = _normalize_shot_routing(previous)
    if not current:
        return
    publisher = snapshot["publisher_instance_uuid"]
    channel = snapshot["channel_uuid"]
    if current["channel_uuid"] and current["channel_uuid"] != channel:
        raise _ShotRoutingContractError(f"{label} channel changed unexpectedly.")
    if (
        current["publisher_instance_uuid"]
        and current["publisher_instance_uuid"] != publisher
    ):
        raise _ShotRoutingContractError(
            f"{label} duplicate/replaced publisher was rejected."
        )
    previous_generation = int(current["generation"])
    generation = int(snapshot["generation"])
    if generation < previous_generation:
        raise _ShotRoutingContractError(f"{label} generation is stale.")
    if generation == previous_generation and previous_generation:
        for key in ("metadata_sha256", "media_sha256"):
            previous_hash = current.get(key)
            if previous_hash and previous_hash != snapshot[key]:
                raise _ShotRoutingContractError(
                    f"{label} reused one generation with different data."
                )


def _shot_image_payload_from_snapshot(
    snapshot: Dict[str, Any],
    shot: Dict[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    by_uid = {
        item["source_uid"]: item for item in snapshot["ordered_assets"]
    }
    ordered_images: List[Dict[str, Any]] = []
    verified_assets: List[Dict[str, Any]] = []
    imported_images: List[Dict[str, Any]] = []
    media: List[str] = []
    for selection_order, source_uid in enumerate(
        shot["selected_source_uids"], start=1
    ):
        source = by_uid[source_uid]
        metadata = copy.deepcopy(source["metadata"])
        metadata["source_uid"] = source_uid
        metadata["order_key"] = source_uid
        metadata["selection_order"] = selection_order
        ordered_images.append(copy.deepcopy(metadata))
        if (
            metadata.get("verified_asset") is True
            and _clean_string(metadata.get("source_kind")).casefold()
            == "project"
        ):
            verified_assets.append(copy.deepcopy(metadata))
        else:
            imported_images.append(copy.deepcopy(metadata))
        media.append(snapshot["media_by_source_uid"][source_uid])
    first_metadata = (
        ordered_images[0] if ordered_images else {}
    )
    payload = {
        "schema": "hmb-image-asset-library-binding",
        "version": 2,
        "mode": "image_asset",
        "project_id": _clean_string(first_metadata.get("project_id")),
        "project_uid": _clean_string(
            first_metadata.get("project_uid")
            or first_metadata.get("asset_project_uid")
        ),
        "project_root": "",
        "selection_id": _canonical_sha256(
            {
                "channel_uuid": snapshot["channel_uuid"],
                "generation": snapshot["generation"],
                "shot_uuid": shot["shot_uuid"],
                "selected_source_uids": shot["selected_source_uids"],
            }
        ),
        "ordered_images": ordered_images,
        "verified_assets": verified_assets,
        "selected_assets": verified_assets,
        "imported_images": imported_images,
    }
    return payload, media


def _shot_selection_contract(state: Dict[str, Any]) -> Dict[str, Any]:
    shot = _normalize_shot_selection(state.get("shot"))
    image_asset = (
        state.get("image_asset")
        if isinstance(state.get("image_asset"), dict)
        else {}
    )
    picker = state.get("picker") if isinstance(state.get("picker"), dict) else {}
    result: Dict[str, Any] = {
        "schema": SHOT_SELECTION_SCHEMA,
        "version": SHOT_SELECTION_VERSION,
        **shot,
    }
    image_routing = _normalize_shot_routing(image_asset.get("shot_routing"))
    video_routing = _normalize_shot_routing(picker.get("shot_routing"))
    if image_routing:
        result["image_routing"] = image_routing
    if video_routing:
        result["video_routing"] = video_routing
    return result


def _normalize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        source_sync_revision = int(state.get(SOURCE_SYNC_REVISION_KEY) or 0)
    except Exception:
        source_sync_revision = 0
    source_sync_revision = max(
        0,
        min(MAX_SOURCE_SYNC_REVISION, source_sync_revision),
    )
    try:
        ui_edit_revision = int(state.get(UI_EDIT_REVISION_KEY) or 0)
    except Exception:
        ui_edit_revision = 0
    ui_edit_revision = max(
        0,
        min(MAX_SOURCE_SYNC_REVISION, ui_edit_revision),
    )
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
        MANUAL_VIDEO_CONTEXT_KEY: _normalize_manual_video_context(
            picker_source.get(MANUAL_VIDEO_CONTEXT_KEY)
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
        "shot_catalog": _normalize_shot_catalog(
            picker_source.get("shot_catalog")
        ),
        "shot_routing": _normalize_shot_routing(
            picker_source.get("shot_routing")
        ),
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
        "shot_catalog": _normalize_shot_catalog(
            image_asset_source.get("shot_catalog")
        ),
        "shot_catalog_routing": _normalize_shot_catalog_routing(
            image_asset_source.get("shot_catalog_routing")
        ),
        "shot_routing": _normalize_shot_routing(
            image_asset_source.get("shot_routing")
        ),
    }

    return {
        "schema": STATE_SCHEMA,
        "mode": MODE_NAME,
        SOURCE_SYNC_REVISION_KEY: source_sync_revision,
        UI_EDIT_REVISION_KEY: ui_edit_revision,
        "image_taxonomy": _image_taxonomy_payload(),
        "shot": _normalize_shot_selection(state.get("shot")),
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
    parts = [part for part in parts if part]
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
    if scope not in {
        "Handheld prop",
        "Attached accessory",
        "Interactive scene prop",
    }:
        return ""
    return f" / Target function = {_target_function(scope)}"


def _image_role_line(item: Dict[str, Any], seq: int) -> str:
    """Render one user-readable image role without transport metadata."""

    token = f"@image{seq}"
    source_type_choice = _public_single_line(item.get("source_type"))
    source_type = _public_single_line(_effective_image_source_type(item))
    owner = _public_single_line(_effective_target(item, f"image {seq}"))
    scopes = [
        _public_single_line(scope)
        for scope in (_non_empty_binding_scopes(item) or [""])
    ]

    def line_for(scope: str) -> str:
        suffix = _detail_suffix(scope)
        if source_type_choice == "Character Appearance":
            return (
                f"{owner} / Approved final appearance source = {token}{suffix} / "
                "Authority = intrinsic identity, color, pattern, and material character; "
                "white backdrop, studio lighting, baked highlight/shadow, matte spill, "
                "and halo are not scene-light authority"
            )
        if source_type_choice == "Partial Character Detail":
            return f"{owner} / Partial character detail source = {token}{suffix}"
        if source_type_choice == "Prop / Accessory":
            return (
                f"{owner} prop / accessory source = {token}{suffix}"
                f"{_target_function_suffix(scope)} / Authority = intrinsic prop appearance "
                "only; reference lighting is not inherited"
            )
        if source_type_choice == "Costume / Clothing":
            return f"{owner} costume / clothing source = {token}{suffix}"
        if source_type_choice == "Environment / Background":
            return (
                f"{owner} / Environment / background source = {token}{suffix} / "
                "Authority = continuous environment appearance and target lighting context, "
                "including dummy regions"
            )
        if source_type_choice == "Sky / Exterior Background":
            return f"{owner} / Sky / exterior background source = {token}{suffix}"
        if source_type_choice == "Set / Structure":
            return f"{owner} / Set / structure source = {token}{suffix}"
        if source_type_choice == "Foreground / Ground":
            return f"{owner} / Foreground / ground source = {token}{suffix}"
        if source_type_choice == "Color / Look Reference":
            return f"{owner} / Color / look reference = {token}{suffix}"
        if source_type_choice == "Color + Look + Lighting Mood Reference":
            return f"{owner} / Color / look / lighting reference = {token}{suffix}"
        if source_type_choice == "Lighting / Atmosphere Reference":
            return f"{owner} / Lighting / atmosphere source = {token}{suffix}"
        if source_type_choice == "Scale / Composition Reference":
            return f"{owner} / Scale / composition reference = {token}{suffix}"
        if source_type_choice == "Custom":
            return f"{owner} / {source_type} = {token}{suffix}"
        return f"{owner} / Unspecified image role = {token}{suffix}"

    lines: List[str] = []
    for scope in scopes:
        line = line_for(scope)
        if line not in lines:
            lines.append(line)
    return "\n".join(lines)


def _clean_replacement_marker(marker: Any, image_seq: int) -> str:
    marker_text = _clean_string(marker)
    if not marker_text:
        return ""
    if "=" in marker_text:
        marker_text = marker_text.split("=", 1)[1].strip()
    token_pattern = r"\s*/\s*@image\d+\b\s*"
    previous = None
    while previous != marker_text:
        previous = marker_text
        marker_text = re.sub(token_pattern + r"$", "", marker_text).strip()
    return re.sub(r"\s+", " ", marker_text).strip(" /\t")


def _image_replacement_line(
    item: Dict[str, Any],
    seq: int,
    active_video_slots: set[int] | None = None,
) -> str | None:
    """Render only explicit marker bindings; blank marker addresses stay omitted."""

    explicit_marker = _clean_replacement_marker(item.get("preview_marker"), seq)
    explicit_video_match = re.search(
        r"@video(10|[1-9])\b",
        explicit_marker,
        re.IGNORECASE,
    )
    if (
        explicit_video_match is not None
        and active_video_slots is not None
        and int(explicit_video_match.group(1)) not in active_video_slots
    ):
        explicit_marker = ""
    source_type = _public_single_line(item.get("source_type"))
    owner = _public_single_line(_effective_target(item, f"image {seq}"))

    def format_line(marker: str, scope: str) -> str:
        if source_type == "Character Appearance":
            label = f"{owner} / {scope}" if scope else owner
            return f"{label} replaces = {marker} / @image{seq}"
        if source_type == "Partial Character Detail":
            return (
                f"{owner} partial detail guides = {marker} / @image{seq} / "
                f"{scope or 'specified detail only'}"
            )
        if source_type in ("Prop / Accessory", "Costume / Clothing"):
            label = scope or (
                "prop / accessory"
                if source_type == "Prop / Accessory"
                else "costume / clothing detail"
            )
            target_suffix = (
                _target_function_suffix(scope)
                if source_type == "Prop / Accessory"
                else ""
            )
            return f"{owner} {label} replaces = {marker} / @image{seq}{target_suffix}"
        if source_type == "Environment / Background":
            return (
                f"{owner} environment / background replaces = {marker} / @image{seq}"
                f"{_detail_suffix(scope)}"
            )
        if source_type == "Sky / Exterior Background":
            return (
                f"{owner} sky / exterior background replaces = {marker} / @image{seq}"
                f"{_detail_suffix(scope)}"
            )
        if source_type == "Set / Structure":
            return (
                f"{owner} set / structure replaces = {marker} / @image{seq}"
                f"{_detail_suffix(scope)}"
            )
        if source_type == "Foreground / Ground":
            return (
                f"{owner} foreground / ground replaces = {marker} / @image{seq}"
                f"{_detail_suffix(scope)}"
            )
        if source_type in {
            "Color / Look Reference",
            "Color + Look + Lighting Mood Reference",
            "Lighting / Atmosphere Reference",
            "Scale / Composition Reference",
        }:
            return (
                f"{source_type} applies to = {marker} / @image{seq}"
                f"{_detail_suffix(scope)}"
            )
        if source_type == "Custom":
            return (
                f"{_public_single_line(_effective_image_source_type(item))} "
                f"applies to {owner} = {marker} / "
                f"@image{seq}{_detail_suffix(scope)}"
            )
        return (
            f"Unclassified image marker association = {marker} / @image{seq}"
            f"{_detail_suffix(scope)}"
        )

    lines: List[str] = []
    if explicit_marker:
        first_scope = _public_single_line(next(
            (
                entry["scope"]
                for entry in _image_binding_entries(item)
                if entry["scope"]
            ),
            "",
        ))
        lines.append(format_line(explicit_marker, first_scope))
    for entry in _image_binding_entries(item):
        marker_video = int(entry.get("marker_video") or 1)
        if (
            active_video_slots is not None
            and marker_video not in active_video_slots
        ):
            continue
        color = _public_single_line(entry["color"])
        scope = _public_single_line(entry["scope"])
        if not color:
            continue
        marker = (
            f"Color Pick marker: @video{marker_video} / {color}"
        )
        line = format_line(marker, scope)
        if line not in lines:
            lines.append(line)
    return "\n".join(lines) if lines else None




def _picker_input_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "name": PICKER_INPUT_PARAMETER_NAME,
        "tooltip": "Connect HMBVideoPickerLibrary PICKER_OUT to synchronize available video slots, source labels, and Asset ID-to-Image Name Color Pick relationships used by the public source and replacement sections. Decoded metadata, diagnostics, descriptive control data, and unknown connected values remain local dashboard state and are not serialized into PROMPT_OUT. Missing companions, slots, metadata, Color Picks, or local bindings are optional and never block Prompt output.",
        "default_value": "",
        "type": "str",
        "input_types": ["any"],
        "allow_input": True,
        "allow_output": False,
        "allow_property": False,
        "hide_property": True,
        "ui_options": {
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "expandable": False,
            "is_full_width": True,
            "hide_property": True,
            "hide_label": True,
            "hide": True,
            "hide_handles": True,
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
            "Recognized source, role, Color Pick, and replacement fields compile into the public Prompt sections. "
            "Other connected or descriptive values remain local dashboard state and are not serialized into PROMPT_OUT."
        ),
        "default_value": "",
        "type": "str",
        "input_types": ["any"],
        "allow_input": True,
        "allow_output": False,
        "allow_property": False,
        "hide_property": True,
        "ui_options": {
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "expandable": False,
            "is_full_width": True,
            "hide_property": True,
            "hide_label": True,
            "hide": True,
            "hide_handles": True,
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
        parameter.hide = True
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


def _shot_asset_input_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "name": SHOT_ASSET_INPUT_PARAMETER_NAME,
        "tooltip": (
            "Hidden compact dependency for the active shot's ImageAsset "
            "snapshot. The raw string is never used as routing authority."
        ),
        "default_value": "",
        "type": "str",
        "input_types": ["any"],
        "allow_input": True,
        "allow_output": False,
        "allow_property": False,
        "hide_property": True,
        "ui_options": {
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "expandable": False,
            "is_full_width": True,
            "hide_property": True,
            "hide_label": True,
            "hide": True,
            "hide_handles": True,
        },
    }
    if ParameterMode is not None:
        kwargs["allowed_modes"] = {ParameterMode.INPUT}
    return kwargs


def _add_shot_asset_input(node: Any) -> None:
    kwargs = _shot_asset_input_kwargs()
    if parameter_exists(node, SHOT_ASSET_INPUT_PARAMETER_NAME):
        _repair_source_input_parameter(
            node, SHOT_ASSET_INPUT_PARAMETER_NAME, kwargs
        )
        return
    try:
        _safe_add_parameter(node, **kwargs)
    finally:
        _repair_source_input_parameter(
            node, SHOT_ASSET_INPUT_PARAMETER_NAME, kwargs
        )


def _shot_picker_input_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "name": SHOT_PICKER_INPUT_PARAMETER_NAME,
        "tooltip": (
            "Hidden exact-source dependency for the active shot's VideoPicker "
            "snapshot. The raw string is never used as routing authority."
        ),
        "default_value": "",
        "type": "str",
        "input_types": ["any"],
        "allow_input": True,
        "allow_output": False,
        "allow_property": False,
        "hide_property": True,
        "ui_options": {
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "expandable": False,
            "is_full_width": True,
            "hide_property": True,
            "hide_label": True,
            "hide": True,
            "hide_handles": True,
        },
    }
    if ParameterMode is not None:
        kwargs["allowed_modes"] = {ParameterMode.INPUT}
    return kwargs


def _add_shot_picker_input(node: Any) -> None:
    kwargs = _shot_picker_input_kwargs()
    if parameter_exists(node, SHOT_PICKER_INPUT_PARAMETER_NAME):
        _repair_source_input_parameter(
            node, SHOT_PICKER_INPUT_PARAMETER_NAME, kwargs
        )
        return
    try:
        _safe_add_parameter(node, **kwargs)
    finally:
        _repair_source_input_parameter(
            node, SHOT_PICKER_INPUT_PARAMETER_NAME, kwargs
        )


def _parse_connected_payload(value: Any, source_name: str) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = value if isinstance(value, str) else _readable_original(value)
    if not text or not text.strip():
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        diagnostic = _source_parse_diagnostic(
            source_name,
            text,
            error_offset=exc.pos,
        )
        if diagnostic is not None:
            return {_UNSTRUCTURED_INPUT_KEY: [diagnostic]}
        entry = _source_intent_entry(
            source_name,
            _LEGACY_SOURCE_PARSE_FAILURE_REASON,
            value,
        )
        return {_UNSTRUCTURED_INPUT_KEY: [entry] if entry else []}
    except Exception:
        diagnostic = _source_parse_diagnostic(source_name, text)
        if diagnostic is not None:
            return {_UNSTRUCTURED_INPUT_KEY: [diagnostic]}
        entry = _source_intent_entry(
            source_name,
            _LEGACY_SOURCE_PARSE_FAILURE_REASON,
            value,
        )
        return {_UNSTRUCTURED_INPUT_KEY: [entry] if entry else []}
    if isinstance(payload, dict):
        return payload
    entry = _source_intent_entry(
        source_name,
        "readable non-object connected input",
        text,
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
        if entry.get("kind") == _SOURCE_PARSE_DIAGNOSTIC_KIND:
            _append_source_parse_diagnostic(state, entry)
        else:
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
    if _known_hmb_connected_payload(IMAGE_ASSET_INPUT_PARAMETER_NAME, payload):
        _prune_source_parse_diagnostic(
            normalized,
            IMAGE_ASSET_INPUT_PARAMETER_NAME,
        )
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


def _source_identity_already_applied(
    state: Dict[str, Any],
    source_name: str,
    payload: Dict[str, Any],
    connected: bool,
) -> bool:
    """Return whether a persisted dashboard already represents one input.

    Source fingerprints intentionally live only for the lifetime of a node.
    Consequently, a restored workflow first observes both inputs as the
    disconnected fingerprint even when its serialized dashboard already
    contains the exact Picker/Image selection.  Frontend serialization also
    omits transport-only helper fields, so reapplying that same source can make
    the normalized JSON differ without representing a new upstream selection.

    This check is used only while establishing a disconnected in-memory
    fingerprint baseline.  Once a connected fingerprint has been observed,
    the full payload fingerprint remains authoritative, including metadata
    changes that retain the same run/selection identifiers.
    """

    if source_name == PICKER_INPUT_PARAMETER_NAME:
        applied = state.get("picker")
        if not isinstance(applied, dict):
            return False
        if bool(applied.get("enabled")) != bool(connected):
            return False
        if not connected:
            return True
        if not payload:
            return True
        if _clean_string(applied.get("run_id")) != _picker_payload_id(payload):
            return False
        if _clean_string(applied.get("selection_id")) != _clean_string(
            payload.get("selection_id")
        ):
            return False

        raw_videos = (
            payload.get("videos")
            if isinstance(payload.get("videos"), list)
            else []
        )
        canonical_videos, uid_managed = _canonical_uid_picker_video_rows(
            raw_videos
        )
        if uid_managed:
            expected_uids = [
                _picker_video_uid(item)
                for item in canonical_videos
                if isinstance(item, dict)
                and item.get("selected") is not False
                and _picker_video_uid(item)
            ][:MAX_VIDEOS]
            if list(applied.get("ordered_video_uids") or []) != expected_uids:
                return False
        return True

    if source_name == IMAGE_ASSET_INPUT_PARAMETER_NAME:
        applied = state.get("image_asset")
        if not isinstance(applied, dict):
            return False
        if bool(applied.get("enabled")) != bool(connected):
            return False
        if not connected:
            return True
        if not payload:
            return True
        if _clean_string(applied.get("selection_id")) != (
            _image_asset_selection_id(payload)
        ):
            return False
        if _clean_string(applied.get("project_uid")) != _clean_string(
            payload.get("project_uid")
        ):
            return False
        if _clean_string(applied.get("project_id")) != _clean_string(
            payload.get("project_id")
        ):
            return False
        return True

    return False


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
    try:
        previous_selection_order = int(
            item.get("selection_order") or item.get("slot") or 0
        )
    except Exception:
        previous_selection_order = 0
    row["selection_order"] = max(
        0,
        min(MAX_VIDEOS, previous_selection_order),
    )
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
) -> tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    Dict[str, Any],
]:
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
    manual_context = _normalize_manual_video_context(
        picker.get(MANUAL_VIDEO_CONTEXT_KEY)
    )
    candidates_by_uid: Dict[str, Dict[str, Any]] = {}
    for item in [*dormant, *old_rows]:
        uid = _picker_video_uid(item)
        if uid:
            candidates_by_uid[uid] = item

    previously_uid_managed = bool(picker.get("order_managed"))
    generated_empty_placeholder = bool(
        int(picker.get("selected_video_count") or 0) == 0
        and len(old_rows) == 1
        and _migrate_old_video_item(old_rows[0], 1)
        == _migrate_old_video_item(_default_video_item(1), 1)
    )
    if not previously_uid_managed:
        # Snapshot every native row before positional Picker adoption assigns a
        # UID to it.  The old implementation cached only rows outside the new
        # selected count, so @video1 could never return on disconnect.
        manual_cache = (
            []
            if generated_empty_placeholder
            else _normalize_dormant_video_rows(
                old_rows,
                managed=False,
            )[:MAX_VIDEOS]
        )
        entry_snapshot = _manual_video_context_snapshot(state)
        manual_context = {
            "version": 1,
            "before": copy.deepcopy(entry_snapshot),
            "after": copy.deepcopy(entry_snapshot),
        }
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
        # While UID order is managed, Prompt's add/delete controls are locked.
        # Any UID-less visible row is a transient placeholder, never a new
        # manual asset to append to the immutable pre-connection snapshot.

    new_slot_by_uid = {
        _picker_video_uid(item): slot
        for slot, item in enumerate(selected_rows, start=1)
    }
    previous_picker_slot_by_uid: Dict[str, int] = {}
    for item in [*dormant, *old_rows]:
        uid = _picker_video_uid(item)
        if not uid:
            continue
        try:
            previous_slot = int(
                item.get("selection_order") or item.get("slot") or 0
            )
        except Exception:
            previous_slot = 0
        if previous_slot > 0:
            previous_picker_slot_by_uid[uid] = previous_slot
    picker_row_slot_map = {
        previous_slot: new_slot_by_uid.get(uid, 0)
        for uid, previous_slot in previous_picker_slot_by_uid.items()
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
        context_before_sync = _manual_video_context_snapshot(state)
        _remap_video_source_references_in_state(state, slot_map)
        for item in selected_rows:
            item["keep_out"] = _remap_video_source_references(
                item.get("keep_out"),
                picker_row_slot_map or slot_map,
            )
        manual_context = _advance_manual_video_context(
            manual_context,
            context_before_sync,
            _manual_video_context_snapshot(state),
        )
    return selected_rows, dormant_out, manual_cache[:MAX_VIDEOS], manual_context


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
    normalized_bundle_run_id = _clean_string(bundle_run_id)
    same_generation = bool(
        normalized_bundle_run_id
        and previous_auto.get("bundle_run_id") == normalized_bundle_run_id
    )
    previous_fields = previous_auto.get("fields", {})
    next_fields: Dict[str, Dict[str, Any]] = {}
    for field, raw_assigned in assigned_values.items():
        if field not in _PICKER_AUTO_DEPTH_FIELDS:
            continue
        current = _picker_auto_depth_field_value(field, item.get(field))
        assigned = _picker_auto_depth_field_value(field, raw_assigned)
        previous_entry = previous_fields.get(field)
        previous_assigned = (
            _picker_auto_depth_field_value(
                field,
                previous_entry.get("assigned"),
            )
            if isinstance(previous_entry, dict)
            else None
        )
        if (
            same_generation
            and isinstance(previous_entry, dict)
            and current != previous_assigned
        ):
            # The same Picker generation has already assigned this field. A
            # different current value is a later Prompt edit, not stale source
            # data. Keep the override and retain the old automation fingerprint
            # so disconnect/invalid provenance will not roll it back.
            next_fields[field] = dict(previous_entry)
            continue
        if (
            isinstance(previous_entry, dict)
            and current == previous_assigned
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
        "bundle_run_id": normalized_bundle_run_id,
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
    normalized_pair_run_id = _clean_string(pair_run_id)
    same_generation = bool(
        normalized_pair_run_id
        and previous_auto.get("pair_run_id") == normalized_pair_run_id
    )
    previous_fields = previous_auto.get("fields", {})
    next_fields: Dict[str, Dict[str, Any]] = {}
    for field, raw_assigned in assigned_values.items():
        if field not in _PICKER_AUTO_DEPTH_FIELDS:
            continue
        current = _picker_auto_depth_field_value(field, item.get(field))
        assigned = _picker_auto_depth_field_value(field, raw_assigned)
        previous_entry = previous_fields.get(field)
        previous_assigned = (
            _picker_auto_depth_field_value(
                field,
                previous_entry.get("assigned"),
            )
            if isinstance(previous_entry, dict)
            else None
        )
        if (
            same_generation
            and isinstance(previous_entry, dict)
            and current != previous_assigned
        ):
            # Preserve a Prompt-authored override while the exact generated
            # Depth source is merely being re-applied during a local UI commit.
            next_fields[field] = dict(previous_entry)
            continue
        if (
            isinstance(previous_entry, dict)
            and current == previous_assigned
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
        "pair_run_id": normalized_pair_run_id,
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


def _release_picker_video_row_provenance(
    item: Dict[str, Any],
    slot: int,
) -> Dict[str, Any]:
    """Convert one connected Picker row back into an ordinary Prompt row."""

    row = _migrate_old_video_item(item, slot)
    _invalidate_picker_generated_depth(row)
    _invalidate_picker_generated_motion_guide(row)
    row.update({
        "slot": slot,
        "token": f"@video{slot}",
        "name": _slot_name("VIDEO", slot),
        "video_uid": "",
        "source_uid": "",
        "selection_order": 0,
        "order_key": "",
        "picker_managed": False,
        "picker_companion_kind": "",
        "picker_companion_source_slot": -1,
        "picker_companion_source_uid": "",
        "picker_companion_validated": False,
        "manual": True,
    })
    return row


def _renumber_video_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        _release_picker_video_row_provenance(item, slot)
        if bool(item.get("picker_managed") or _picker_video_uid(item))
        else {
            **_migrate_old_video_item(item, slot),
            "slot": slot,
            "token": f"@video{slot}",
            "name": _slot_name("VIDEO", slot),
            "manual": True,
        }
        for slot, item in enumerate(rows[:MAX_VIDEOS], start=1)
        if isinstance(item, dict)
    ]


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
        (
            _,
            dormant_video_rows,
            dormant_manual_rows,
            manual_video_context,
        ) = (
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
            MANUAL_VIDEO_CONTEXT_KEY: manual_video_context,
            "slot_suppressions": {},
            "scene": _clean_string(payload.get("scene") or payload.get("scene_path")),
            "video_path": "",
            "camera": _clean_string(payload.get("camera")),
            "markers": [],
            "frame_metadata": [],
            "contract_errors": list(dict.fromkeys(rejected_video_contract_errors)),
            "matched_images": 0,
        }
        if _known_hmb_connected_payload(PICKER_INPUT_PARAMETER_NAME, payload):
            _prune_source_parse_diagnostic(
                normalized,
                PICKER_INPUT_PARAMETER_NAME,
            )
        return _normalize_state(normalized)
    if not picker_has_media:
        if has_readable_unstructured_video_rows:
            if isinstance(previous_picker, dict):
                previous_picker["enabled"] = bool(
                    connected or previous_picker.get("enabled")
                )
            return _normalize_state(normalized)
        previous_enabled = bool(previous_picker.get("enabled"))
        previous_order_managed = bool(previous_picker.get("order_managed"))
        dormant_video_rows = _normalize_dormant_video_rows(
            previous_picker.get("dormant_video_rows"),
            managed=True,
        )
        dormant_manual_rows = _normalize_dormant_video_rows(
            previous_picker.get("dormant_manual_rows"),
            managed=False,
        )
        manual_video_context = _normalize_manual_video_context(
            previous_picker.get(MANUAL_VIDEO_CONTEXT_KEY)
        )
        has_manual_restore_snapshot = bool(manual_video_context)
        if (
            not connected
            and previous_enabled
            and (previous_order_managed or has_manual_restore_snapshot)
        ):
            selected_picker_rows = [
                item
                for item in normalized.get("videos", [])
                if isinstance(item, dict)
                and bool(item.get("picker_managed") or _picker_video_uid(item))
            ]
            for item in selected_picker_rows:
                _upsert_dormant_video_row(dormant_video_rows, item)
            if manual_video_context:
                # New states carry a complete pre-connection snapshot,
                # including rows that were positionally adopted by Picker.
                restored_rows = dormant_manual_rows
            else:
                # Backward-compatible recovery for workflows saved before the
                # complete snapshot existed: adopted rows were not in the old
                # manual cache, so release them ahead of the cached tail.
                restored_rows = [
                    _release_picker_video_row_provenance(item, slot)
                    for slot, item in enumerate(selected_picker_rows, start=1)
                ]
                restored_rows.extend(dormant_manual_rows)
            normalized["videos"] = (
                _renumber_video_rows(restored_rows)
                or [_default_video_item(1)]
            )
            _restore_manual_video_context(normalized, manual_video_context)
            manual_video_context = {}

        # Release only fields previously auto-authored by Picker companion
        # provenance. A connected semantic payload containing only empty UI
        # placeholders remains awaiting data; only a true edge disconnect takes
        # the restoration branch above.
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
            "order_managed": bool(connected and previous_order_managed),
            "dormant_video_rows": dormant_video_rows,
            "dormant_manual_rows": dormant_manual_rows,
            MANUAL_VIDEO_CONTEXT_KEY: manual_video_context,
            "slot_suppressions": (
                _normalize_picker_slot_suppressions(
                    previous_picker.get("slot_suppressions")
                )
                if connected
                else {}
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
    manual_video_context = previous_picker.get(MANUAL_VIDEO_CONTEXT_KEY, {})
    if (
        not uid_order_managed
        and not _normalize_manual_video_context(manual_video_context)
    ):
        # Legacy Picker payloads have no stable video UID/order contract, but
        # disconnect must still be lossless. Snapshot their pre-connection
        # manual rows and every remap-affected Prompt field before applying the
        # first connected payload.
        dormant_manual_rows = _normalize_dormant_video_rows(
            normalized.get("videos"),
            managed=False,
        )[:MAX_VIDEOS]
        legacy_entry_snapshot = _manual_video_context_snapshot(normalized)
        manual_video_context = {
            "version": 1,
            "before": copy.deepcopy(legacy_entry_snapshot),
            "after": copy.deepcopy(legacy_entry_snapshot),
        }
    if uid_order_managed:
        (
            selected_rows,
            dormant_video_rows,
            dormant_manual_rows,
            manual_video_context,
        ) = (
            _prepare_uid_managed_video_rows(normalized, payload_videos)
        )
        normalized["videos"] = selected_rows or [_default_video_item(1)]
    picker_automatic_context_before = (
        _manual_video_context_snapshot(normalized)
        if _normalize_manual_video_context(manual_video_context)
        else None
    )

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
            video_item["reference_capabilities"] = {}
            video_item["frame_domain"] = {}
            video_item["timing_cues"] = []
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
        video_item["reference_capabilities"] = (
            _normalize_video_reference_capabilities(
                raw_video.get("reference_capabilities")
            )
        )
        video_item["frame_domain"] = _normalize_video_frame_domain(
            raw_video.get("frame_domain")
        )
        video_item["timing_cues"] = _normalize_video_timing_cues(
            raw_video.get("timing_cues")
        )
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
        # Connected Picker media may adopt a pre-existing manual row.  Preserve
        # its label, Keep Out, and all other authoring, but remove the one
        # taxonomy pair that would claim two incompatible authority domains.
        if (
            video_item.get("source_type") == "Maya Preview / Playblast"
            and video_item.get("control_role")
            == "Primary Unified Shot Control"
        ):
            video_item["control_role"] = ""
            video_item["custom_control_role"] = ""
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

    if picker_automatic_context_before is not None:
        manual_video_context = _advance_manual_video_context(
            manual_video_context,
            picker_automatic_context_before,
            _manual_video_context_snapshot(normalized),
        )

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
        MANUAL_VIDEO_CONTEXT_KEY: manual_video_context,
        "slot_suppressions": slot_suppressions,
        "scene": _clean_string(payload.get("scene") or payload.get("scene_path")),
        "video_path": video_path,
        "camera": _clean_string(payload.get("camera")),
        "markers": markers,
        "frame_metadata": frame_metadata,
        "contract_errors": list(dict.fromkeys(picker_contract_errors)),
        "matched_images": matched_images,
    }
    if _known_hmb_connected_payload(PICKER_INPUT_PARAMETER_NAME, payload):
        _prune_source_parse_diagnostic(
            normalized,
            PICKER_INPUT_PARAMETER_NAME,
        )
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
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "expandable": False,
            "is_full_width": True,
            "hide_property": True,
            "hide_label": True,
            "hide": True,
            "hide_handles": True,
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


def _shot_media_output_kwargs(name: str) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "name": name,
        "tooltip": (
            "Hidden ordered media output for the exact active Prompt shot. "
            "Its order is generation-paired with PROMPT_OUT."
        ),
        "default_value": [],
        "type": "list[str]",
        "output_type": "list[str]",
        "input_types": [],
        "allow_input": False,
        "allow_output": True,
        "allow_property": False,
        "settable": False,
        "hide_property": True,
        "ui_options": {
            "display_name": "",
            "compact": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "expandable": False,
            "is_full_width": True,
            "hide_property": True,
            "hide_label": True,
            "hide": True,
            "hide_handles": True,
        },
    }
    mode = _mode_output()
    if mode is not None:
        kwargs["allowed_modes"] = mode
    return kwargs


def _repair_shot_media_output(node: Any, name: str) -> None:
    parameter = _get_parameter_obj(node, name)
    if parameter is None:
        return
    kwargs = _shot_media_output_kwargs(name)
    for key, value in kwargs.items():
        if key == "ui_options":
            continue
        if kwargs.get("allowed_modes") is not None and key in {
            "allow_input",
            "allow_output",
            "allow_property",
        }:
            continue
        try:
            setattr(parameter, key, value)
        except Exception as exc:
            _diagnostic_exception(f"{name} attribute repair failed", exc)
    try:
        current_ui = dict(
            getattr(parameter, "ui_options", None)
            or getattr(parameter, "_ui_options", None)
            or {}
        )
        current_ui.update(kwargs["ui_options"])
        parameter.ui_options = current_ui
    except Exception as exc:
        _diagnostic_exception(f"{name} UI repair failed", exc)


def _add_shot_media_output(node: Any, name: str) -> None:
    if parameter_exists(node, name):
        _repair_shot_media_output(node, name)
        return
    try:
        _safe_add_parameter(node, **_shot_media_output_kwargs(name))
    finally:
        _repair_shot_media_output(node, name)


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
    binding_override: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None, List[str]]:
    errors: List[str] = []
    if not bool(item.get("frame_range_enabled")):
        return None, None, errors

    binding = (
        dict(binding_override)
        if isinstance(binding_override, dict)
        else _current_frame_range_binding(item)
    )
    if not binding:
        errors.append(
            "Optional frame-range instruction ignored: select a Video and Color Pick to define it."
        )
        return None, None, errors

    slot = _video_slot_number(binding.get("video_slot"), MAX_VIDEOS)
    color = _clean_string(binding.get("color_pick"))
    video_wide = _video_wide_frame_range_allowed(state, slot, color)
    if active_video_slots is not None and slot not in active_video_slots:
        errors.append(f"@video{slot} does not exist as an active video source.")
    if not color and not video_wide:
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

    # Picker frame metadata is identity and optional UI suggestion data only.
    # A re-probe, source swap, or conflict must never replace or bound the
    # user's canonical manual start/end/segments.  Marker catalogs retain their
    # independent exact-address security role.
    if picker_metadata is not None:
        available_colors = picker_metadata.get("available_color_picks")
        # An empty catalog means the imported video declared no Picker marker
        # authority. A non-empty catalog remains an exact allow-list.
        if (
            isinstance(available_colors, list)
            and available_colors
            and color not in available_colors
        ):
            errors.append(f"{color} is not available in @video{slot} Picker metadata.")

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
    valid_ranges: List[Dict[str, int]] = []
    for frame_range in ranges:
        start = int(frame_range.get("start") or 0)
        end = int(frame_range.get("end") or 0)
        if start > end:
            errors.append(f"Invalid frame range {start}–{end}.")
        elif start < minimum or end > maximum:
            errors.append(
                f"Frame range {start}–{end} is outside @video{slot} Frames {minimum}–{maximum}."
            )
        else:
            valid_ranges.append({"start": start, "end": end})
    binding = {
        **binding,
        "video_slot": f"@video{slot}",
        "color_pick": color,
        "ranges": valid_ranges,
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
        for active_binding in _active_frame_range_bindings(item):
            binding, metadata, errors = _frame_range_binding_validation(
                state,
                item,
                active_video_slots,
                active_binding,
            )
            error_codes = set(_frame_range_error_codes(errors))
            segment_only_errors = {
                "segment_order_invalid", "segment_out_of_domain"
            }
            if (
                binding is not None
                and metadata is not None
                and bool(binding.get("ranges"))
                and error_codes.issubset(segment_only_errors)
            ):
                out.append((item, binding, metadata))
    return out


def _control_binding_timing_cues(
    entries: List[Dict[str, Any]], video_slot: int
) -> List[Dict[str, Any]]:
    """Translate an exact manual emitter binding into the typed cue shape."""

    cues: List[Dict[str, Any]] = []
    for entry in entries:
        if int(entry.get("video") or 0) != int(video_slot):
            continue
        if "emitter" not in _clean_string(entry.get("function")).casefold():
            continue
        boundary = _clean_string(entry.get("boundary"))
        frame_match = re.search(
            r"\b(?:frame|f)\s*[:=#@-]?\s*([0-9]+)\b",
            boundary,
            re.IGNORECASE,
        )
        if frame_match is None:
            continue
        local_point: Dict[str, Any] = {}
        locator_match = re.search(
            r"\bLocator(?:\s+(?:ID|Path))?\s*=\s*([^,;]+)",
            boundary,
            re.IGNORECASE,
        )
        if locator_match is not None:
            locator_value = _clean_string(locator_match.group(1))
            local_point = _normalize_local_point({
                "kind": "locator",
                (
                    "locator_path"
                    if "|" in locator_value or "/" in locator_value
                    else "locator_id"
                ): locator_value,
            })
        if not local_point:
            number = r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
            coordinate_match = re.search(
                rf"\b(Local|Object)\s+XYZ\s*=\s*({number})\s*,\s*({number})\s*,\s*({number})\s+([A-Za-z_ ]+?)(?=\s*,\s*Frame\b|\s*;|$)",
                boundary,
                re.IGNORECASE,
            )
            if coordinate_match is not None:
                local_point = _normalize_local_point({
                    "kind": "coordinates",
                    "space": coordinate_match.group(1),
                    "unit": coordinate_match.group(5),
                    "xyz": [
                        float(coordinate_match.group(axis)) for axis in (2, 3, 4)
                    ],
                })
        # A prose phrase such as "exact local point" is not a resolvable point.
        if not local_point:
            continue
        marker_color = _clean_string(entry.get("marker"))
        target_id = _clean_string(entry.get("target"))
        if not marker_color or not target_id:
            continue
        emitter = {
            key: value
            for key, value in {
                "marker_color": marker_color,
                "subject_root": target_id,
            }.items()
            if value
        }
        if not emitter:
            continue
        cues.append({
            "schema": "hmb-video-emitter-timing-cue",
            "version": 1,
            "cue_id": (
                f"manual-{_clean_string(entry.get('field')).casefold()}-"
                f"{int(entry.get('line') or 0)}"
            ),
            "cue_type": "emitter_point",
            "cue_phase": "point",
            "frame": int(frame_match.group(1)),
            "emitter": emitter,
            "local_point": local_point,
            "description": boundary,
        })
    return _normalize_video_timing_cues(cues)


def _fx_timing_range_segments(
    valid_bindings: List[tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]],
    video_slot: int,
) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for item, binding, _metadata in valid_bindings:
        if _video_slot_number(binding.get("video_slot"), MAX_VIDEOS) != video_slot:
            continue
        image_slot = int(item.get("slot") or 1)
        marker_color = (
            _clean_string(binding.get("color_pick"))
            or VIDEO_WIDE_RANGE_MARKER
        )
        image_source_uid = _clean_string(
            item.get("asset_source_uid") or item.get("source_uid")
        )
        image_asset_id = _clean_string(item.get("asset_id"))
        target_id = _clean_string(item.get("owner"))
        binding_entry = next(
            (
                entry
                for entry in _image_binding_entries(item)
                if int(entry.get("marker_video") or 0) == video_slot
                and (
                    _clean_string(entry.get("color"))
                    or VIDEO_WIDE_RANGE_MARKER
                ).casefold() == marker_color.casefold()
            ),
            {},
        )
        target_scope = _clean_string(binding_entry.get("scope"))
        binding_signature = hashlib.sha256(
            json.dumps(
                {
                    "marker_color": marker_color.casefold(),
                    "target_scope": target_scope,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        ranges = (
            binding.get("ranges")
            if isinstance(binding.get("ranges"), list)
            else []
        )
        for range_index, frame_range in enumerate(ranges, start=1):
            start = _strict_int(frame_range.get("start"))
            end = _strict_int(frame_range.get("end"))
            if start is None or end is None or start > end:
                continue
            segment: Dict[str, Any] = {
                "segment_id": (
                    f"image{image_slot}-video{video_slot}-"
                    f"{binding_signature}-{range_index}"
                ),
                "image": f"@image{image_slot}",
                "video": f"@video{video_slot}",
                "marker_color": marker_color,
                "target_id": target_id,
                "target_scope": target_scope,
                "start_frame": start,
                "end_frame": end,
            }
            if image_source_uid:
                segment["image_source_uid"] = image_source_uid
            if image_asset_id:
                segment["image_asset_id"] = image_asset_id
            segments.append(segment)
    return segments


def _build_fx_timing_source_contract(
    state: Dict[str, Any],
    active_images: List[Dict[str, Any]],
    active_videos: List[Dict[str, Any]],
    control_only_bindings: List[Dict[str, Any]],
    valid_frame_bindings: List[
        tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]
    ],
) -> Dict[str, Any]:
    """Compile typed FX/Timing source facts without policy interpretation.

    The package carries source identity, user selections, validated ranges, and
    exact emitter cues. Behavior authority and preservation rules remain solely
    in the signed Agent policy and are never serialized into ``PROMPT_OUT``.
    """

    sources: List[Dict[str, Any]] = []
    active_video_slots = {
        int(item.get("slot") or 1) for item in active_videos
    }
    for item in active_videos:
        source_type = _clean_string(item.get("source_type"))
        if source_type not in {"FX Reference", "Timing / Edit Reference"}:
            continue
        slot = int(item.get("slot") or 1)
        token = f"@video{slot}"
        # Serialize the selected UI value exactly as data.  Main-Type policy
        # meaning (including whether this role can narrow it) belongs to the
        # signed Agent runtime, not to the Prompt compiler.
        selected_role = _clean_string(item.get("control_role"))
        role_selected = bool(selected_role)
        validation_codes: List[str] = []

        relevant_range_enabled = False
        range_errors_for_source: List[str] = []
        for image in active_images:
            for binding in _active_frame_range_bindings(image):
                if _video_slot_number(binding.get("video_slot"), MAX_VIDEOS) != slot:
                    continue
                relevant_range_enabled = True
                _binding, _metadata, range_errors = _frame_range_binding_validation(
                    state,
                    image,
                    active_video_slots,
                    binding,
                )
                range_errors_for_source.extend(
                    f"{token} image-range binding: {error}" for error in range_errors
                )

        segments = _fx_timing_range_segments(valid_frame_bindings, slot)
        if relevant_range_enabled and not segments:
            range_errors_for_source.append(
                f"{token} Range ON has no valid image-source segment"
            )

        capabilities = (
            item.get("reference_capabilities")
            if isinstance(item.get("reference_capabilities"), dict)
            else {}
        )
        transport_errors = _video_reference_transport_errors(item)
        if transport_errors:
            validation_codes.append("transport")
        if capabilities:
            if segments and capabilities.get("frame_addressable") is not True:
                range_errors_for_source.append(
                    f"{token} is not frame-addressable for Range ON"
                )
            if (
                segments
                and capabilities.get("image_source_frame_ranges") is not True
            ):
                range_errors_for_source.append(
                    f"{token} does not support image-source frame ranges"
                )

        raw_timing_cues = _normalize_video_timing_cues(item.get("timing_cues"))
        manual_timing_cues = _control_binding_timing_cues(
            control_only_bindings, slot
        )
        emitter_binding_declared = bool(raw_timing_cues) or any(
            int(entry.get("video") or 0) == slot
            and "emitter" in _clean_string(entry.get("function")).casefold()
            for entry in control_only_bindings
        )
        timing_cues = _normalize_video_timing_cues([
            *raw_timing_cues,
            *manual_timing_cues,
        ])
        timing_cues = [
            cue
            for cue in timing_cues
            if not _video_reference_transport_errors({
                "timing_cues": [cue],
                "frame_domain": item.get("frame_domain"),
            })
        ]
        if emitter_binding_declared and not timing_cues:
            validation_codes.append("emitter_cue")
        if (
            emitter_binding_declared
            and capabilities
            and capabilities.get("exact_emitter_cues") is not True
        ):
            validation_codes.append("emitter_cue")

        if range_errors_for_source:
            validation_codes.append("range")
        validation_codes = list(dict.fromkeys(validation_codes))

        source: Dict[str, Any] = {
            "video": token,
            "source_type": source_type,
            "selected_role": selected_role,
            "role_selected": role_selected,
            "validation_codes": validation_codes,
            "range_on": relevant_range_enabled,
            "range_segments": segments,
            "emitter_binding_declared": emitter_binding_declared,
            "timing_cues": timing_cues,
        }
        video_uid = _clean_string(item.get("video_uid") or item.get("source_uid"))
        if video_uid:
            source["video_uid"] = video_uid
        sources.append(source)

    error_records: List[Dict[str, str]] = []
    seen_error_records: set[tuple[str, str]] = set()
    for source in sources:
        video = _clean_string(source.get("video"))
        for code in source.get("validation_codes", []):
            signature = (video, _clean_string(code))
            if not all(signature) or signature in seen_error_records:
                continue
            seen_error_records.add(signature)
            error_records.append({"video": signature[0], "code": signature[1]})
    return {
        "schema": FX_TIMING_CONTRACT_SCHEMA,
        "version": FX_TIMING_CONTRACT_VERSION,
        "valid": not error_records,
        "errors": error_records,
        "sources": sources,
    }


def _frame_range_error_codes(errors: List[str]) -> List[str]:
    """Map internal diagnostics to stable data-only codes."""

    codes: List[str] = []
    for raw in errors:
        error = _clean_string(raw).casefold()
        if "does not exist as an active video source" in error:
            code = "video_inactive"
        elif "color pick is not selected" in error:
            code = "marker_missing"
        elif "conflicting or incomplete" in error:
            code = "frame_domain_invalid"
        elif "is not available" in error and "picker metadata" in error:
            code = "marker_unavailable"
        elif "start frame is not supplied" in error:
            code = "domain_start_missing"
        elif "end frame is not supplied" in error:
            code = "domain_end_missing"
        elif "start after end" in error:
            code = "domain_order_invalid"
        elif "no range is selected" in error:
            code = "segment_missing"
        elif "invalid frame range" in error:
            code = "segment_order_invalid"
        elif " is outside " in error:
            code = "segment_out_of_domain"
        elif "select a video and color pick" in error:
            code = "binding_address_missing"
        else:
            code = "binding_invalid"
        if code not in codes:
            codes.append(code)
    return codes


def _nonempty_identity(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value not in (None, "", [], {})
    }


def _valid_public_frame_domain_for_prompt(value: Any) -> bool:
    """Return whether an optional frame domain is safe to publish to Agent."""

    if not isinstance(value, dict) or set(value) != {
        "schema",
        "version",
        "timebase",
        "start_frame",
        "end_frame",
        "frame_count",
        "range_addressable",
    }:
        return False
    start = value.get("start_frame")
    end = value.get("end_frame")
    count = value.get("frame_count")
    return bool(
        value.get("schema") == VIDEO_FRAME_DOMAIN_SCHEMA
        and value.get("version") == VIDEO_FRAME_DOMAIN_VERSION
        and isinstance(value.get("timebase"), str)
        and all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in (start, end, count)
        )
        and start <= end
        and count == end - start + 1
        and isinstance(value.get("range_addressable"), bool)
    )


def _public_job_data_contract(
    state: Dict[str, Any],
    active_images: List[Dict[str, Any]],
    active_videos: List[Dict[str, Any]],
    control_only_bindings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build source, role, target, and range addresses without policy prose."""

    active_video_slots = {
        int(item.get("slot") or 1) for item in active_videos
    }
    images: List[Dict[str, Any]] = []
    for item in active_images:
        slot = int(item.get("slot") or 1)
        video_wide_range_slots = {
            _video_slot_number(binding.get("video_slot"), MAX_VIDEOS)
            for binding in _active_frame_range_bindings(item)
            if _video_wide_frame_range_allowed(
                state,
                binding.get("video_slot"),
                binding.get("color_pick"),
            )
        }
        bindings = [
            {
                "video": f"@video{int(entry.get('marker_video') or 1)}",
                "marker_color": (
                    _clean_string(entry.get("color"))
                    or (
                        VIDEO_WIDE_RANGE_MARKER
                        if int(entry.get("marker_video") or 1)
                        in video_wide_range_slots
                        else ""
                    )
                ),
                "target_scope": _clean_string(entry.get("scope")),
            }
            for entry in _image_binding_entries(item)
            if int(entry.get("marker_video") or 1) in active_video_slots
            and (
                _clean_string(entry.get("color"))
                or _clean_string(entry.get("scope"))
                or int(entry.get("marker_video") or 1) in video_wide_range_slots
            )
        ]
        images.append({
            "image": f"@image{slot}",
            "label": _clean_string(item.get("label")),
            "source_type": _clean_string(item.get("source_type")),
            "custom_source_type": _clean_string(item.get("custom_source_type")),
            "target_id": _clean_string(item.get("owner")),
            # Legacy relationship targets are retained in widget state for
            # round-trip compatibility, but remain dormant until a dedicated
            # active binding contract exists.
            "relationship_targets": [],
            "bindings": bindings,
            "identity": _nonempty_identity({
                "asset_id": _clean_string(item.get("asset_id")),
                "asset_library_id": _clean_string(item.get("asset_library_id")),
                "source_uid": _clean_string(
                    item.get("asset_source_uid") or item.get("source_uid")
                ),
                "project_uid": _clean_string(item.get("asset_project_uid")),
                "selection_order": int(item.get("asset_selection_order") or 0),
                "source_kind": _clean_string(item.get("asset_source_kind")),
                "verified": bool(item.get("asset_verified")),
            }),
        })

    videos: List[Dict[str, Any]] = []
    for item in active_videos:
        slot = int(item.get("slot") or 1)
        source_type = _clean_string(item.get("source_type"))
        selected_role = _clean_string(item.get("control_role"))
        record: Dict[str, Any] = {
            "video": f"@video{slot}",
            "label": _clean_string(item.get("label")),
            "source_type": source_type,
            "custom_source_type": _clean_string(item.get("custom_source_type")),
            "control_role": selected_role,
            "custom_control_role": _clean_string(item.get("custom_control_role")),
            "control_role_explicit": bool(selected_role),
            "keep_out": _clean_string(item.get("keep_out")),
            "identity": _nonempty_identity({
                "video_uid": _clean_string(item.get("video_uid")),
                "source_uid": _clean_string(item.get("source_uid")),
                "order_key": _clean_string(item.get("order_key")),
                "selection_order": int(item.get("selection_order") or 0),
            }),
        }
        capabilities = _normalize_video_reference_capabilities(
            item.get("reference_capabilities")
        )
        frame_domain = _normalize_video_frame_domain(item.get("frame_domain"))
        if capabilities:
            record["reference_capabilities"] = capabilities
        # Picker uses 1..0/count=0 as an internal "not addressable" sentinel.
        # The Agent's optional public field is a real domain only, so omit that
        # sentinel instead of turning one unavailable source into a global gate.
        if _valid_public_frame_domain_for_prompt(frame_domain):
            record["frame_domain"] = frame_domain
        if bool(item.get("picker_companion_validated")):
            record["companion"] = _nonempty_identity({
                "kind": _clean_string(item.get("picker_companion_kind")),
                "source_slot": int(item.get("picker_companion_source_slot") or 0),
                "source_uid": _clean_string(item.get("picker_companion_source_uid")),
                "validated": True,
            })
        videos.append(record)

    frame_ranges: List[Dict[str, Any]] = []
    for item in active_images:
        image_token = f"@image{int(item.get('slot') or 1)}"
        for active_binding in _active_frame_range_bindings(item):
            binding, metadata, errors = _frame_range_binding_validation(
                state,
                item,
                active_video_slots,
                active_binding,
            )
            selected = binding if isinstance(binding, dict) else active_binding
            slot = _video_slot_number(selected.get("video_slot"), MAX_VIDEOS)
            if slot not in active_video_slots:
                continue
            valid_ranges = _normalize_frame_ranges(selected.get("ranges"))
            submitted_ranges = _normalize_frame_ranges(active_binding.get("ranges"))
            error_codes = _frame_range_error_codes(errors)
            segment_error_codes = {
                "segment_order_invalid", "segment_out_of_domain"
            }
            usable = bool(
                binding is not None
                and metadata is not None
                and valid_ranges
                and set(error_codes).issubset(segment_error_codes)
            )
            domain: Dict[str, Any] = {}
            if isinstance(metadata, dict):
                domain = _nonempty_identity({
                    "start_frame": _strict_int(metadata.get("start_frame")),
                    "end_frame": _strict_int(metadata.get("end_frame")),
                    "frame_count": _strict_int(metadata.get("frame_count")),
                    "timebase": _clean_string(metadata.get("timebase")),
                    "fps": float(metadata.get("fps") or 0.0),
                })
            else:
                domain = _nonempty_identity({
                    "start_frame": _strict_int(selected.get("start_frame")),
                    "end_frame": _strict_int(selected.get("end_frame")),
                })
            minimum = _strict_int(domain.get("start_frame"))
            maximum = _strict_int(domain.get("end_frame"))
            unresolved_segments: List[Dict[str, Any]] = []
            for frame_range in submitted_ranges:
                start = int(frame_range.get("start") or 0)
                end = int(frame_range.get("end") or 0)
                error_code = ""
                if start > end:
                    error_code = "segment_order_invalid"
                elif (
                    minimum is not None
                    and maximum is not None
                    and (start < minimum or end > maximum)
                ):
                    error_code = "segment_out_of_domain"
                if error_code:
                    unresolved_segments.append({
                        "start_frame": start,
                        "end_frame": end,
                        "error_code": error_code,
                    })
            # An invalid ON range remains a local unresolved instruction. Keep
            # its machine record internally self-consistent so Agent can ignore
            # only this binding instead of turning optional Range metadata into
            # a generation-wide contract failure. Validation may return early
            # for a bad manual domain, so segment diagnostics are completed here
            # from the submitted ranges that the public record actually carries.
            for unresolved_segment in unresolved_segments:
                unresolved_code = _clean_string(
                    unresolved_segment.get("error_code")
                )
                if unresolved_code and unresolved_code not in error_codes:
                    error_codes.append(unresolved_code)
            frame_ranges.append({
                "image": image_token,
                "video": f"@video{slot}",
                "marker_color": _public_frame_range_marker(
                    state,
                    slot,
                    selected.get("color_pick"),
                ),
                "enabled": True,
                "origin": _clean_string(selected.get("origin")) or "manual",
                "domain": domain,
                "segments": [
                    {
                        "start_frame": int(frame_range.get("start") or 0),
                        "end_frame": int(frame_range.get("end") or 0),
                    }
                    for frame_range in valid_ranges
                ] if usable else [],
                "unresolved_segments": [
                    dict(segment) for segment in unresolved_segments
                ],
                "valid": usable,
                "error_codes": error_codes,
            })

    controls = [
        {
            "source_field": _clean_string(entry.get("field")),
            "line": int(entry.get("line") or 0),
            "video": f"@video{int(entry.get('video') or 1)}",
            "target_id": _clean_string(entry.get("target")),
            "function": _clean_string(entry.get("function")),
            "marker_color": _clean_string(entry.get("marker")),
            "boundary": _clean_string(entry.get("boundary")),
        }
        for entry in control_only_bindings
        if int(entry.get("video") or 1) in active_video_slots
    ]
    return {
        "schema": PUBLIC_JOB_CONTRACT_SCHEMA,
        "version": PUBLIC_JOB_CONTRACT_VERSION,
        "images": images,
        "videos": videos,
        "control_only_bindings": controls,
        "frame_ranges": frame_ranges,
        "connections": {
            "image_asset": _image_asset_connection_enabled(state),
            "picker": bool(
                isinstance(state.get("picker"), dict)
                and state["picker"].get("enabled")
            ),
        },
    }


def _public_user_description_data(
    state: Dict[str, Any], text: Dict[str, Any]
) -> Dict[str, Any]:
    """Return user-authored text verbatim after ordinary field normalization."""

    payload: Dict[str, Any] = {}
    for key in TEXT_FIELD_NAMES:
        value = _clean_string(text.get(key))
        if value:
            payload[key] = value
    return payload


def _build_data_only_prompt_package(state: Dict[str, Any]) -> str:
    state = _normalize_state(state)
    text = state["text"]
    active_images = _active_image_rows_for_state(state["images"], state)
    active_videos = [item for item in state["videos"] if _is_active_video(item)]
    control_only_bindings = _parse_control_only_bindings(text)[0]
    valid_frame_bindings = _valid_frame_range_bindings(
        state, active_images, active_videos
    )
    job_data = _public_job_data_contract(
        state, active_images, active_videos, control_only_bindings
    )
    fx_timing_contract = _build_fx_timing_source_contract(
        state,
        active_images,
        active_videos,
        control_only_bindings,
        valid_frame_bindings,
    )
    user_data = _public_user_description_data(state, text)
    return "\n".join([
        "HMB_GP_Production",
        PUBLIC_JOB_CONTRACT_HEADER,
        json.dumps(job_data, ensure_ascii=False, separators=(",", ":")),
        FX_TIMING_CONTRACT_HEADER,
        json.dumps(fx_timing_contract, ensure_ascii=False, separators=(",", ":")),
        USER_DESCRIPTION_DATA_HEADER,
        json.dumps(user_data, ensure_ascii=False, separators=(",", ":")),
        "",
    ])


def _compile_prompt_with_budget(lines: List[str]) -> str:
    """Compile the bounded user-readable view without machine metadata."""

    safe_lines = [
        _public_single_line(line, MAX_PUBLIC_PROMPT_LINE_CHARS)
        for line in lines
    ]
    compiled = "\n".join(safe_lines).strip() + "\n"
    if len(compiled) <= MAX_PROMPT_CHARS:
        return compiled

    notice = "[Additional source lines omitted from the display view.]"
    kept: List[str] = []
    used = len(notice) + 2
    for line in safe_lines:
        added = len(line) + 1
        if used + added > MAX_PROMPT_CHARS:
            break
        kept.append(line)
        used += added
    while kept and not kept[-1]:
        kept.pop()
    kept.extend(["", notice])
    return "\n".join(kept).strip() + "\n"


def _build_user_readable_prompt_package(state: Dict[str, Any]) -> str:
    """Render the documented source map shown on the public PROMPT_OUT port."""

    state = _normalize_state(state)
    active_images = _active_image_rows_for_state(state["images"], state)
    active_videos = [item for item in state["videos"] if _is_active_video(item)]
    active_video_slots = {
        int(item.get("slot") or 1) for item in active_videos
    }
    lines: List[str] = ["HMB_GP_Production", ""]

    lines.extend([
        "TARGET GENERATOR:",
        "This prompt is written for the active downstream target generator or execution system.",
        "",
        "IMAGE SOURCE:",
    ])
    if active_images:
        for item in active_images:
            seq = int(item.get("slot") or 1)
            label = _public_path_basename(
                item.get("label"),
                f"image source {seq}",
                strip_extension=False,
            )
            asset_id = _public_path_basename(
                item.get("asset_id"),
                "",
                strip_extension=False,
            )
            asset_suffix = f" / Asset ID: {asset_id}" if asset_id else ""
            color_text = _public_single_line(
                _color_pick_text(
                    item,
                    active_video_slots=active_video_slots,
                )
            )
            color_suffix = f" / Color Pick: {color_text}" if color_text else ""
            lines.append(f"@image{seq} = {label}{asset_suffix}{color_suffix}")
        lines.append(
            "Color Pick values = target, mask, and reference-routing addresses; "
            "not final intrinsic color, material, lighting, or background appearance authority"
        )
    else:
        lines.append("No image source assigned in HMBPromptLibrary.")
    lines.append("")

    if active_images:
        lines.append("IMAGE ROLE MAP:")
        for item in active_images:
            seq = int(item.get("slot") or 1)
            for role_line in _image_role_line(item, seq).splitlines():
                if _clean_string(role_line):
                    lines.append(role_line)
        lines.append("")

        replacement_lines: List[str] = []
        for item in active_images:
            seq = int(item.get("slot") or 1)
            replacement = _image_replacement_line(
                item,
                seq,
                active_video_slots=active_video_slots,
            )
            if not replacement:
                continue
            for replacement_line in replacement.splitlines():
                if replacement_line and replacement_line not in replacement_lines:
                    replacement_lines.append(replacement_line)
        if replacement_lines:
            lines.append("REPLACEMENT BINDING:")
            lines.extend(replacement_lines)
            lines.append("")

    lines.append("VIDEO SOURCE:")
    if active_videos:
        lines.append(
            "Active video slots = "
            + ", ".join(
                f"@video{int(item.get('slot') or 1)}" for item in active_videos
            )
        )
        for item in active_videos:
            seq = int(item.get("slot") or 1)
            label = _public_path_basename(
                item.get("label"),
                f"video source {seq}",
                strip_extension=bool(_clean_string(item.get("picker_auto_label"))),
            )
            lines.append(f"@video{seq} = {label}")
    else:
        lines.append("No video source assigned in HMBPromptLibrary.")
    lines.append("")
    return _compile_prompt_with_budget(lines)


def _build_prompt_package(state: Dict[str, Any]) -> str:
    # PROMPT_OUT is the concise, user-verifiable source map. The exact typed
    # machine envelope is paired privately by HMBPromptLibrary and consumed only
    # by the directly connected HMBAgentLibrary.
    return _build_user_readable_prompt_package(state)

def _prompt_semantic_fingerprint(
    state: Dict[str, Any],
    public_prompt: str | None = None,
    machine_prompt: str | None = None,
) -> str:
    """Identify the atomic visible/machine pair, excluding irrelevant UI state."""

    visible = public_prompt
    if visible is None:
        visible = _build_user_readable_prompt_package(state)
    machine = machine_prompt
    if machine is None:
        machine = _build_data_only_prompt_package(state)
    # Shot identity and upstream media hashes are private pairing facts. They
    # must advance the Prompt generation even when the concise document and
    # machine job JSON happen to remain textually identical (for example, a
    # source file was replaced in place without changing its label).
    shot_pairing = _canonical_sha256(_shot_selection_contract(state))
    return hashlib.sha256(
        (str(visible) + "\0" + str(machine) + "\0" + shot_pairing).encode(
            "utf-8"
        )
    ).hexdigest()


def _media_list_sha256(values: List[str]) -> str:
    if not isinstance(values, list) or any(
        not isinstance(value, str) for value in values
    ):
        raise _ShotRoutingContractError("Shot media output is not list[str].")
    return _canonical_sha256({"media": values})


def _agent_shot_context(
    state: Dict[str, Any],
    *,
    prompt_generation: int,
    visible_prompt: str,
    image_media: List[str],
    video_media: List[str],
) -> Dict[str, Any]:
    shot = _normalize_shot_selection(state.get("shot"))
    if not shot["channel_uuid"] or not shot["shot_uuid"]:
        raise _ShotRoutingContractError("Active Prompt shot identity is unavailable.")
    return {
        "schema": "hmb-agent-shot-context",
        "version": 1,
        "channel_uuid": shot["channel_uuid"],
        "shot_uuid": shot["shot_uuid"],
        "shot_number": shot["number"],
        "shot_name": shot["name"],
        "prompt_generation": int(prompt_generation),
        "visible_prompt_sha256": hashlib.sha256(
            visible_prompt.rstrip("\r\n").encode("utf-8")
        ).hexdigest(),
        "image_media_sha256": _media_list_sha256(image_media),
        "video_media_sha256": _media_list_sha256(video_media),
    }


def _prompt_output_side_effect_local(node: Any) -> Any:
    local = getattr(node, "_hmb_output_side_effect_local", None)
    if local is None:
        local = threading.local()
        setattr(node, "_hmb_output_side_effect_local", local)
    return local


def _is_prompt_output_side_effect_callback(node: Any) -> bool:
    return int(
        getattr(_prompt_output_side_effect_local(node), "depth", 0) or 0
    ) > 0


def _begin_prompt_output_side_effect_callback(node: Any) -> None:
    local = _prompt_output_side_effect_local(node)
    local.depth = int(getattr(local, "depth", 0) or 0) + 1


def _end_prompt_output_side_effect_callback(node: Any) -> None:
    local = _prompt_output_side_effect_local(node)
    local.depth = max(0, int(getattr(local, "depth", 0) or 0) - 1)


def _propagate_prompt_output_to_connections(
    node: Any,
    value: Any,
    *,
    owner_pending: Any = None,
    output_name: str = "PROMPT_OUT",
    pending_attribute: str = "_hmb_pending_prompt_notification",
) -> None:
    """Forward one late Prompt output through retained-mode edges."""

    def still_owned() -> bool:
        if bool(getattr(node, "_hmb_node_deleted", False)):
            return False
        if owner_pending is None:
            return True
        current = getattr(node, pending_attribute, None)
        if isinstance(current, dict):
            return current.get(output_name) is owner_pending
        return current is owner_pending

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

    node_name = _clean_string(getattr(node, "name", ""))
    if not node_name:
        return
    try:
        registered_node = GriptapeNodes.NodeManager().get_node_by_name(
            node_name
        )
    except Exception:
        return
    if registered_node is not node:
        return
    if not still_owned():
        return

    connections_result = GriptapeNodes.handle_request(
        ListConnectionsForNodeRequest(
            node_name=node_name,
            broadcast_result=False,
            failure_log_level=logging.DEBUG,
        )
    )
    if not isinstance(connections_result, ListConnectionsForNodeResultSuccess):
        details = _clean_string(
            getattr(connections_result, "result_details", "")
        )
        raise RuntimeError(
            details or f"Griptape could not inspect outgoing {output_name} connections."
        )

    source_parameter = _get_parameter_obj(node, output_name)
    data_type = _clean_string(
        getattr(source_parameter, "output_type", "")
    ) or _clean_string(getattr(source_parameter, "type", ""))
    for connection in connections_result.outgoing_connections:
        if not still_owned():
            return
        if _clean_string(
            getattr(connection, "source_parameter_name", "")
        ) != output_name:
            continue
        target_node_name = _clean_string(
            getattr(connection, "target_node_name", "")
        )
        target_parameter_name = _clean_string(
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
                incoming_connection_source_parameter_name=output_name,
            )
        )
        if not still_owned():
            return
        if not isinstance(set_result, SetParameterValueResultSuccess):
            details = _clean_string(getattr(set_result, "result_details", ""))
            raise RuntimeError(
                details
                or (
                    f"Griptape rejected {node_name}.{output_name} propagation to "
                    f"{target_node_name}.{target_parameter_name}."
                )
            )


def _notify_prompt_shot_media_outputs(
    node: Any,
    synchronized_outputs: Sequence[tuple[str, List[str]]],
) -> None:
    """Publish changed Shot media after both caches are atomically staged."""

    if bool(getattr(node, "_hmb_node_deleted", False)) or not synchronized_outputs:
        return
    generation = int(
        getattr(node, "_hmb_shot_media_notification_generation", 0) or 0
    ) + 1
    node._hmb_shot_media_notification_generation = generation
    node._hmb_pending_shot_media_notifications = {
        name: (generation, list(value))
        for name, value in synchronized_outputs
    }
    publisher = getattr(node, "publish_update_to_parameter", None)
    pending = getattr(node, "_hmb_pending_shot_media_notifications", {})
    if not isinstance(pending, dict):
        return
    for name, pending_item in list(pending.items()):
        if bool(getattr(node, "_hmb_node_deleted", False)):
            return
        current = getattr(node, "_hmb_pending_shot_media_notifications", {})
        if not isinstance(current, dict) or current.get(name) is not pending_item:
            continue
        owner_generation, value = pending_item
        try:
            if callable(publisher):
                publisher(name, value)
            if bool(getattr(node, "_hmb_node_deleted", False)):
                return
            current = getattr(node, "_hmb_pending_shot_media_notifications", {})
            if (
                not isinstance(current, dict)
                or current.get(name) is not pending_item
                or pending_item[0] != owner_generation
            ):
                continue
            if not _is_prompt_output_side_effect_callback(node):
                _propagate_prompt_output_to_connections(
                    node,
                    value,
                    owner_pending=pending_item,
                    output_name=name,
                    pending_attribute="_hmb_pending_shot_media_notifications",
                )
        except Exception:
            current = getattr(node, "_hmb_pending_shot_media_notifications", {})
            if isinstance(current, dict) and current.get(name) is pending_item:
                raise
            continue
        current = getattr(node, "_hmb_pending_shot_media_notifications", {})
        if isinstance(current, dict) and current.get(name) is pending_item:
            current.pop(name, None)


def _stage_and_notify_prompt_output(
    node: Any,
    value: Any,
    *,
    stage_output: bool = True,
    replace_pending: bool = True,
) -> None:
    """Stage PROMPT_OUT before notifying an already-connected downstream node."""
    if bool(getattr(node, "_hmb_node_deleted", False)):
        return
    if stage_output:
        set_output(node, "PROMPT_OUT", value)
    if replace_pending:
        generation = (
            int(getattr(node, "_hmb_prompt_notification_generation", 0)) + 1
        )
        node._hmb_prompt_notification_generation = generation
        node._hmb_pending_prompt_notification = (generation, value)
    publisher = getattr(node, "publish_update_to_parameter", None)
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
        if callable(publisher):
            publisher("PROMPT_OUT", pending_value)
        if bool(getattr(node, "_hmb_node_deleted", False)):
            return
        current_pending = getattr(
            node,
            "_hmb_pending_prompt_notification",
            None,
        )
        if (
            not isinstance(current_pending, tuple)
            or len(current_pending) != 2
            or current_pending[0] != owner_generation
            or current_pending is not pending
        ):
            # A synchronous subscriber published a newer paired generation.
            # The superseded callback may never forward its older visible text
            # after the newer generation has reached downstream nodes.
            return
        if not _is_prompt_output_side_effect_callback(node):
            _propagate_prompt_output_to_connections(
                node,
                pending_value,
                owner_pending=pending,
            )
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
        self._hmb_node_deleted = False
        self._hmb_delete_parent_called = False
        self._hmb_deletion_reconcile_called = False
        # The host may deliver widget value callbacks after a later UI edit has
        # already been accepted.  Keep a per-node canonical baseline so an old
        # callback cannot replace the newer dashboard before deferred prompt
        # synchronization gets a chance to read it.
        self._hmb_last_accepted_widget_state: str | None = None
        self._hmb_last_accepted_widget_revisions = (0, 0)
        self._hmb_widget_write_in_progress = False
        self._hmb_restoring_widget_state = False
        # Publisher instance UUIDs and routing generations are intentionally
        # process-local. A saved Flow therefore contains valid media ownership
        # together with watermarks that cannot match the newly constructed
        # ImageAsset/VideoPicker instances. Arm one narrowly scoped rebase when
        # the host hydrates such a saved dashboard. The first successful exact
        # graph-source projection consumes it; all later live updates continue
        # to use strict monotonic validation.
        self._hmb_routing_hydration_rebase_pending = False
        self._hmb_routing_hydration_epoch_started = False
        # A newly dragged Prompt should immediately adopt the ImageAsset's
        # active Shot and exact Picker snapshot. Serialized workflows disable
        # this one-shot path as soon as their initial widget state arrives, so
        # an intentionally saved Only selection remains Only after reload.
        self._hmb_initial_shot_autoclaim_pending = True
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_initial_shot_exact_refresh_pending = False
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
        self._hmb_connected_source_nodes: Dict[str, Any] = {}
        self._hmb_current_shot_images: List[str] = []
        self._hmb_current_shot_videos: List[str] = []
        self._hmb_last_shot_context: Dict[str, Any] = {}
        self._hmb_last_agent_context_pair: Dict[str, Any] = {}
        self._hmb_agent_pair_local = threading.local()
        self._hmb_shot_route_status: Dict[str, Any] = {}
        self._hmb_shared_routing_in_progress = False
        self._hmb_compact_route_syncing = False
        self._hmb_sync_lock = threading.RLock()
        self._hmb_output_side_effect_local = threading.local()
        self._hmb_sync_generation = 0
        self._hmb_last_prompt_semantic_fingerprint = ""
        self._hmb_last_prompt_output = None
        self._hmb_last_machine_prompt_output = None
        self._hmb_prompt_snapshot_generation = 0
        self._hmb_prompt_notification_generation = 0
        self._hmb_pending_prompt_notification = None
        self._hmb_shot_media_notification_generation = 0
        self._hmb_pending_shot_media_notifications: Dict[
            str, tuple[int, List[str]]
        ] = {}
        self._hmb_source_input_fingerprints = {
            PICKER_INPUT_PARAMETER_NAME: _connected_source_fingerprint({}, False),
            IMAGE_ASSET_INPUT_PARAMETER_NAME: _connected_source_fingerprint(
                {}, False
            ),
        }
        try:
            self.ui_options = {"width": 1800, "height": PROMPT_START_HEIGHT, "default_width": 1800, "default_height": PROMPT_START_HEIGHT, "preferred_width": 1800, "preferred_height": PROMPT_START_HEIGHT, "initial_width": 1800, "initial_height": PROMPT_START_HEIGHT, "node_size": {"width": 1800, "height": PROMPT_START_HEIGHT}, "default_size": {"width": 1800, "height": PROMPT_START_HEIGHT}, "initial_size": {"width": 1800, "height": PROMPT_START_HEIGHT}, "min_width": 760, "min_height": PROMPT_MIN_HEIGHT, "resizable": True}
            self.width = 1800
            self.height = PROMPT_START_HEIGHT
        except Exception as exc:
            _diagnostic_exception("Prompt node UI sizing failed", exc)

        _add_image_asset_input(self)
        _add_picker_input(self)
        _add_shot_asset_input(self)
        _add_shot_picker_input(self)
        self._ensure_prompt_output()
        add_group(self, "A_HMB_PROMPT_LIBRARY_DASHBOARD", "HMB_GP_Production", collapsed=False)
        _add_widget_state_parameter(self)
        self._accept_widget_state_baseline(
            _get_parameter_raw(self, WIDGET_PARAMETER_NAME)
        )
        self._ensure_prompt_output()
        try:
            self._sync_prompt_output_from_state()
        except Exception as exc:
            _diagnostic_exception("Initial PROMPT_OUT synchronization failed", exc)
        try:
            from _hmb_shot_routing import schedule_post_registration_reconcile

            schedule_post_registration_reconcile(self)
        except Exception as exc:
            _diagnostic_exception("Initial Shot routing schedule failed", exc)

    @staticmethod
    def _state_has_persisted_shot_routing(value: Any) -> bool:
        state = value if isinstance(value, dict) else _parse_state(value)
        if not isinstance(state, dict) or not state:
            return False
        image_asset = state.get("image_asset")
        picker = state.get("picker")
        return bool(
            isinstance(image_asset, dict)
            and (
                _normalize_shot_catalog_routing(
                    image_asset.get("shot_catalog_routing")
                )
                or _normalize_shot_routing(image_asset.get("shot_routing"))
            )
            or isinstance(picker, dict)
            and _normalize_shot_routing(picker.get("shot_routing"))
        )

    def _arm_routing_hydration_rebase(self, value: Any) -> None:
        if bool(getattr(self, "_hmb_routing_hydration_epoch_started", False)):
            return
        if not self._state_has_persisted_shot_routing(value):
            return
        self._hmb_routing_hydration_epoch_started = True
        self._hmb_routing_hydration_rebase_pending = True

    def _routing_watermark_for_validation(self, value: Any) -> Any:
        if bool(getattr(self, "_hmb_routing_hydration_rebase_pending", False)):
            return {}
        return value

    def _consume_routing_hydration_rebase(self) -> None:
        self._hmb_routing_hydration_rebase_pending = False

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
            _add_shot_asset_input(self)
        except Exception as exc:
            _diagnostic_exception("SHOT_ASSET_IN parameter setup failed", exc)
        try:
            _add_shot_picker_input(self)
        except Exception as exc:
            _diagnostic_exception("SHOT_PICKER_IN parameter setup failed", exc)
        try:
            _add_prompt_output(self)
        except Exception as exc:
            _diagnostic_exception("PROMPT_OUT parameter setup failed", exc)
        for name in (
            SHOT_IMAGE_OUTPUT_PARAMETER_NAME,
            SHOT_VIDEO_OUTPUT_PARAMETER_NAME,
        ):
            try:
                _add_shot_media_output(self, name)
            except Exception as exc:
                _diagnostic_exception(f"{name} parameter setup failed", exc)

    def _reconcile_connected_source_inputs_from_graph(self) -> bool:
        """Refresh source inputs from their actual connected output caches.

        Saved workflows create edges before hydrating output values, and
        ``initial_setup`` deliberately skips normal value propagation.  The
        separately serialized target input may therefore be stale.  Inspecting
        the real incoming edges at the end of Prompt state hydration makes the
        connected source authoritative without accepting or repairing a stale
        target-side payload.
        """

        try:
            from griptape_nodes.retained_mode.events.connection_events import (  # type: ignore
                ListConnectionsForNodeRequest,
                ListConnectionsForNodeResultSuccess,
            )
            from griptape_nodes.retained_mode.griptape_nodes import (  # type: ignore
                GriptapeNodes,
            )
        except Exception:
            return False

        node_name = _clean_string(getattr(self, "name", ""))
        if not node_name:
            return False
        try:
            registered_node = GriptapeNodes.NodeManager().get_node_by_name(
                node_name
            )
        except Exception:
            return False
        if registered_node is not self:
            return False
        request_handler = getattr(GriptapeNodes, "handle_request", None)
        if not callable(request_handler):
            return False
        try:
            result = request_handler(
                ListConnectionsForNodeRequest(
                    node_name=node_name,
                    broadcast_result=False,
                    failure_log_level=logging.DEBUG,
                )
            )
        except Exception:
            return False
        if not isinstance(result, ListConnectionsForNodeResultSuccess):
            return False

        source_targets = {
            PICKER_INPUT_PARAMETER_NAME,
            IMAGE_ASSET_INPUT_PARAMETER_NAME,
            SHOT_ASSET_INPUT_PARAMETER_NAME,
            SHOT_PICKER_INPUT_PARAMETER_NAME,
        }
        incoming_groups: Dict[str, List[Any]] = {
            name: [] for name in source_targets
        }
        for connection in result.incoming_connections:
            target_name = _clean_string(
                getattr(connection, "target_parameter_name", "")
            )
            if target_name in incoming_groups:
                incoming_groups[target_name].append(connection)
        duplicated = [
            name for name, connections in incoming_groups.items()
            if len(connections) > 1
        ]
        if duplicated:
            raise _ShotRoutingContractError(
                "Duplicate shot/source publisher connection: "
                + ", ".join(sorted(duplicated))
            )
        incoming_by_target = {
            name: connections[0]
            for name, connections in incoming_groups.items()
            if connections
        }
        self._hmb_picker_connected = PICKER_INPUT_PARAMETER_NAME in incoming_by_target
        self._hmb_image_asset_connected = (
            IMAGE_ASSET_INPUT_PARAMETER_NAME in incoming_by_target
            or SHOT_ASSET_INPUT_PARAMETER_NAME in incoming_by_target
        )
        self._hmb_connected_source_nodes = {}
        sentinel = object()
        parent_setter = getattr(super(), "set_parameter_value", None)
        if not callable(parent_setter):
            return True
        # Once graph inspection succeeds, a missing edge is authoritative too.
        # Saved target-side input values are merely connection transport caches;
        # retaining one after its edge is absent can make ``or payload`` below
        # resurrect a disconnected Picker/ImageAsset during hydration.
        for target_name in source_targets - incoming_by_target.keys():
            if ParameterMode is None:
                parent_setter(target_name, "")
            else:
                parent_setter(target_name, "", initial_setup=True)
        for target_name, connection in incoming_by_target.items():
            source_node_name = _clean_string(
                getattr(connection, "source_node_name", "")
            )
            source_parameter_name = _clean_string(
                getattr(connection, "source_parameter_name", "")
            )
            if not source_node_name or not source_parameter_name:
                continue
            try:
                source_node = GriptapeNodes.NodeManager().get_node_by_name(
                    source_node_name
                )
            except Exception:
                continue
            self._hmb_connected_source_nodes[target_name] = source_node
            value: Any = sentinel
            output_values = getattr(source_node, "parameter_output_values", {})
            if source_parameter_name in output_values:
                value = output_values[source_parameter_name]
            else:
                parameter_values = getattr(source_node, "parameter_values", {})
                if source_parameter_name in parameter_values:
                    value = parameter_values[source_parameter_name]
                else:
                    try:
                        value = source_node.get_parameter_value(
                            source_parameter_name
                        )
                    except Exception:
                        value = sentinel
            if value is sentinel:
                continue
            if ParameterMode is None:
                parent_setter(target_name, value)
            else:
                # Bypass this class's hydration reconciliation and all normal
                # before/after hooks while retaining parameter conversion.
                parent_setter(target_name, value, initial_setup=True)
        return True

    def _apply_exact_shot_routes(
        self,
        state: Dict[str, Any],
        *,
        image_source_node: Any = None,
        picker_source_node: Any = None,
    ) -> tuple[Dict[str, Any], List[str], List[str], bool, bool]:
        """Project one graph-owned shot generation onto Prompt state/media."""

        normalized = _normalize_state(state)
        sources = getattr(self, "_hmb_connected_source_nodes", {})
        legacy_image_source_selected = False
        if image_source_node is None and isinstance(sources, dict):
            compact_image_source = sources.get(SHOT_ASSET_INPUT_PARAMETER_NAME)
            legacy_image_source = sources.get(IMAGE_ASSET_INPUT_PARAMETER_NAME)
            if (
                compact_image_source is not None
                and legacy_image_source is not None
                and compact_image_source is not legacy_image_source
            ):
                raise _ShotRoutingContractError(
                    "Duplicate ImageAsset shot publishers are connected."
                )
            # New automatic routing uses only the compact dependency. A saved
            # legacy IMAGE_ASSET_IN edge remains a supported exact-source
            # fallback, but its serialized rich payload is never preferred.
            image_source_node = compact_image_source or legacy_image_source
            legacy_image_source_selected = bool(
                compact_image_source is None and legacy_image_source is not None
            )
        if picker_source_node is None and isinstance(sources, dict):
            picker_source_node = sources.get(SHOT_PICKER_INPUT_PARAMETER_NAME)

        current_shot = _normalize_shot_selection(normalized.get("shot"))
        # IMAGE_ASSET_IN predates Shot routing and intentionally accepts any
        # third-party source.  Keep that legacy wildcard contract while Shot
        # mode is disabled; only a compact SHOT_ASSET_IN edge or an explicitly
        # persisted Shot identity may require the private exact-snapshot API.
        if legacy_image_source_selected and not (
            current_shot["channel_uuid"] and current_shot["shot_uuid"]
        ):
            image_source_node = None
        expected_channel = current_shot["channel_uuid"]
        image_media: List[str] = []
        video_media: List[str] = []
        image_exact = False
        picker_exact = False

        image_api = getattr(
            image_source_node, "_hmb_shot_routing_snapshot", None
        )
        if image_source_node is not None and not callable(image_api):
            raise _ShotRoutingContractError(
                "Connected ImageAsset publisher has no exact Shot snapshot API."
            )
        if callable(image_api):
            image_exact = True
            raw_snapshot = image_api(expected_channel_uuid=expected_channel)
            image_snapshot = _validate_shot_routing_snapshot(
                raw_snapshot,
                expected_channel_uuid=expected_channel,
                max_selected_sources=MAX_SHOT_IMAGES,
            )
            _assert_monotonic_shot_route(
                self._routing_watermark_for_validation(
                    normalized.get("image_asset", {}).get("shot_routing")
                    if isinstance(normalized.get("image_asset"), dict)
                    else {}
                ),
                image_snapshot,
                label="ImageAsset shot routing",
            )
            compact_catalog = _compact_catalog_from_snapshot(image_snapshot)
            selected_uuid_exists = any(
                item["shot_uuid"] == current_shot["shot_uuid"]
                for item in image_snapshot["shots"]
            )
            if not (
                current_shot["channel_uuid"]
                and current_shot["shot_uuid"]
                and selected_uuid_exists
            ):
                # A verified publisher supplies choices, not an activation.
                # Restore the independent rows and keep Only selected until the
                # user explicitly chooses one of those backend-owned UUIDs.
                normalized = _apply_image_asset_payload(
                    normalized, {}, connected=False
                )
                normalized["shot"] = _normalize_shot_selection({})
                image_asset = (
                    normalized.get("image_asset")
                    if isinstance(normalized.get("image_asset"), dict)
                    else {}
                )
                image_asset["shot_catalog"] = (
                    self._hmb_available_prompt_shot_catalog(
                        _shot_catalog_from_snapshot(image_snapshot),
                        current_shot,
                    )
                )
                image_asset["shot_catalog_routing"] = (
                    _catalog_routing_projection(compact_catalog)
                )
                image_asset["shot_routing"] = {}
                normalized["image_asset"] = image_asset
                current_shot = _normalize_shot_selection({})
                expected_channel = ""
            else:
                selected_shot = _select_routed_shot(
                    image_snapshot, current_shot
                )
                payload, image_media = _shot_image_payload_from_snapshot(
                    image_snapshot, selected_shot
                )
                normalized["shot"] = selected_shot
                normalized = _apply_image_asset_payload(
                    normalized, payload, connected=True
                )
                projected_image_uids = [
                    _clean_string(
                        item.get("asset_source_uid") or item.get("source_uid")
                    )
                    for item in normalized.get("images", [])
                    if isinstance(item, dict)
                    and bool(item.get("asset_managed"))
                ]
                if projected_image_uids != selected_shot["selected_source_uids"]:
                    raise _ShotRoutingContractError(
                        "Prompt image rows do not match the active Shot media order."
                    )
                normalized["shot"] = selected_shot
                image_asset = (
                    normalized.get("image_asset")
                    if isinstance(normalized.get("image_asset"), dict)
                    else {}
                )
                image_asset["shot_catalog"] = (
                    self._hmb_available_prompt_shot_catalog(
                        _shot_catalog_from_snapshot(image_snapshot),
                        current_shot,
                    )
                )
                image_asset["shot_catalog_routing"] = (
                    _catalog_routing_projection(compact_catalog)
                )
                image_asset["shot_routing"] = _routing_projection(
                    image_snapshot, selected_shot["selected_source_uids"]
                )
                normalized["image_asset"] = image_asset
                current_shot = selected_shot
                expected_channel = selected_shot["channel_uuid"]

        picker_api = getattr(
            picker_source_node, "_hmb_shot_routing_snapshot", None
        )
        if picker_source_node is not None and not callable(picker_api):
            raise _ShotRoutingContractError(
                "Connected VideoPicker publisher has no exact Shot snapshot API."
            )
        picker_subscription_api = getattr(
            picker_source_node, "_hmb_shot_channel_subscription", None
        )
        if callable(picker_api) and callable(picker_subscription_api):
            picker_subscription = picker_subscription_api()
            if (
                isinstance(picker_subscription, dict)
                and picker_subscription.get("participant_kind") == "video_picker"
                and not bool(picker_subscription.get("enabled"))
            ):
                # VideoPicker's independent Only mode is valid even while this
                # Prompt uses an ImageAsset Shot. A managed edge can survive
                # for one retained-mode callback during hydration/deletion;
                # do not ask that disabled Picker for remote Shot authority.
                picker_exact = True
                normalized = _apply_picker_payload(
                    normalized, {}, connected=False
                )
                picker_api = None
        if callable(picker_api):
            if not expected_channel or not current_shot["shot_uuid"]:
                # Picker may remain connected while Prompt runs independently.
                # It is another remote choice consumer and must not force Shot 1.
                picker_exact = True
                normalized = _apply_picker_payload(
                    normalized, {}, connected=False
                )
                normalized["shot"] = _normalize_shot_selection({})
                normalized = _normalize_state(normalized)
                return (
                    normalized,
                    image_media,
                    video_media,
                    image_exact,
                    picker_exact,
                )
            picker_exact = True
            picker_snapshot = _validate_picker_shot_routing_snapshot(
                picker_api(expected_channel_uuid=expected_channel),
                expected_channel_uuid=expected_channel,
            )
            _assert_monotonic_shot_route(
                self._routing_watermark_for_validation(
                    normalized.get("picker", {}).get("shot_routing")
                    if isinstance(normalized.get("picker"), dict)
                    else {}
                ),
                picker_snapshot,
                label="VideoPicker shot routing",
            )
            picker_shot = next(
                (
                    item
                    for item in picker_snapshot["shots"]
                    if item["shot_uuid"] == current_shot["shot_uuid"]
                ),
                None,
            )
            if picker_shot is None:
                raise _ShotRoutingContractError(
                    "Picker routing does not contain the active Prompt shot."
                )
            if (
                int(picker_shot["number"]) != int(current_shot["number"])
                or picker_shot["name"] != current_shot["name"]
            ):
                raise _ShotRoutingContractError(
                    "Picker and ImageAsset shot metadata do not match."
                )
            normalized = _apply_picker_payload(
                normalized,
                copy.deepcopy(picker_shot["picker_payload"]),
                connected=True,
            )
            projected_video_uids = [
                _clean_string(uid)
                for uid in (
                    normalized.get("picker", {}).get("ordered_video_uids", [])
                    if isinstance(normalized.get("picker"), dict)
                    else []
                )
            ]
            if projected_video_uids != picker_shot["selected_source_uids"]:
                raise _ShotRoutingContractError(
                    "Prompt video rows do not match the active Shot media order."
                )
            normalized["shot"] = current_shot
            picker_state = (
                normalized.get("picker")
                if isinstance(normalized.get("picker"), dict)
                else {}
            )
            picker_state["shot_catalog"] = _shot_catalog_from_snapshot(
                picker_snapshot
            )
            picker_state["shot_routing"] = _routing_projection(
                picker_snapshot, picker_shot["selected_source_uids"]
            )
            normalized["picker"] = picker_state
            video_media = [
                picker_snapshot["media_by_source_uid"][uid]
                for uid in picker_shot["selected_source_uids"]
            ]

        normalized = _normalize_state(normalized)
        return (
            normalized,
            image_media,
            video_media,
            image_exact,
            picker_exact,
        )

    def _hmb_shot_channel_subscription(self) -> Dict[str, Any]:
        """Return the durable selector identity used by the edge helper."""

        shot = _normalize_shot_selection(self._current_state().get("shot"))
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": "prompt",
            "enabled": bool(shot["channel_uuid"] and shot["shot_uuid"]),
            "channel_uuid": shot["channel_uuid"],
            "shot_uuid": shot["shot_uuid"],
            "shot_number": shot["number"],
            "shot_name": shot["name"],
        }

    def _hmb_available_prompt_shot_catalog(
        self,
        catalog: Any,
        current_shot: Any = None,
    ) -> List[Dict[str, Any]]:
        """Hide Shot UUIDs already assigned to another Prompt in this flow."""

        normalized_catalog = _normalize_shot_catalog(catalog)
        if not normalized_catalog:
            return []
        current = _normalize_shot_selection(
            current_shot
            if isinstance(current_shot, dict)
            else self._current_state().get("shot")
        )
        channel_uuid = _clean_string(
            normalized_catalog[0].get("channel_uuid")
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
                isinstance(subscription, dict)
                and subscription.get("participant_kind") == "prompt"
                and subscription.get("enabled")
                and subscription.get("channel_uuid") == channel_uuid
                and subscription.get("shot_uuid")
            ):
                claimed.add(_clean_string(subscription["shot_uuid"]))
        current_uuid = (
            current["shot_uuid"]
            if current["channel_uuid"] == channel_uuid
            else ""
        )
        return [
            copy.deepcopy(item)
            for item in normalized_catalog
            if item["shot_uuid"] not in claimed
            or item["shot_uuid"] == current_uuid
        ]

    def _hmb_filter_prompt_widget_write(self, value: Any) -> Any:
        """Reject stale/browser attempts to claim another Prompt's Shot."""

        incoming = value if isinstance(value, dict) else _parse_state(value)
        if not isinstance(incoming, dict) or not incoming:
            return value
        state = _normalize_state(copy.deepcopy(incoming))
        current = _normalize_shot_selection(self._current_state().get("shot"))
        image_asset = (
            state.get("image_asset")
            if isinstance(state.get("image_asset"), dict)
            else {}
        )
        source_catalog = _normalize_shot_catalog(
            image_asset.get("shot_catalog")
        )
        if not source_catalog:
            return value
        available_catalog = self._hmb_available_prompt_shot_catalog(
            source_catalog,
            current,
        )
        available_uuids = {
            item["shot_uuid"] for item in available_catalog
        }
        requested = _normalize_shot_selection(state.get("shot"))
        if requested["shot_uuid"] and requested["shot_uuid"] not in available_uuids:
            state["shot"] = (
                current
                if current["shot_uuid"] in available_uuids
                else _normalize_shot_selection({})
            )
        image_asset["shot_catalog"] = available_catalog
        state["image_asset"] = image_asset
        picker = (
            state.get("picker")
            if isinstance(state.get("picker"), dict)
            else {}
        )
        picker["shot_catalog"] = [
            item
            for item in _normalize_shot_catalog(picker.get("shot_catalog"))
            if item["shot_uuid"] in available_uuids
        ]
        state["picker"] = picker
        return _json_dumps(_normalize_state(state))

    def _hmb_post_registration_shot_discovery(self) -> None:
        """Discover already-running Shot publishers for a newly dragged node."""

        if not bool(getattr(self, "_hmb_initial_shot_autoclaim_pending", False)):
            return
        self._reconcile_shared_shot_edges()

    def _hmb_prepare_initial_shot_selection(self, shot_uuid: Any = "") -> None:
        """Capture ImageAsset's active UUID before accepting its first catalog."""

        if not bool(getattr(self, "_hmb_initial_shot_autoclaim_pending", False)):
            return
        current = _normalize_shot_selection(self._current_state().get("shot"))
        if current["channel_uuid"] or current["shot_uuid"]:
            self._hmb_initial_shot_autoclaim_pending = False
            return
        self._hmb_initial_shot_preferred_uuid = _clean_string(shot_uuid)

    def _hmb_finalize_initial_shot_discovery(self) -> None:
        """Read exact ImageAsset/VideoPicker outputs after managed edges exist."""

        if not bool(
            getattr(self, "_hmb_initial_shot_exact_refresh_pending", False)
        ):
            return
        self._hmb_initial_shot_exact_refresh_pending = False
        try:
            self._hmb_reconcile_shot_routing()
        except Exception:
            self._hmb_initial_shot_exact_refresh_pending = True
            raise

    def _hmb_reject_duplicate_shot_selection(
        self, reason: str = "duplicate_prompt_shot"
    ) -> Dict[str, Any]:
        """Return only this Prompt selector to Only after a 1:1 collision.

        Remote catalog choices and all manual Prompt rows remain durable.  The
        graph coordinator performs the subsequent edge reconciliation, so this
        narrow callback deliberately does not compile or publish PROMPT_OUT.
        """

        with self._hmb_sync_lock:
            current = self._current_state()
            current_image_asset = (
                current.get("image_asset")
                if isinstance(current.get("image_asset"), dict)
                else {}
            )
            current_picker = (
                current.get("picker")
                if isinstance(current.get("picker"), dict)
                else {}
            )
            image_catalog = self._hmb_available_prompt_shot_catalog(
                current_image_asset.get("shot_catalog", []),
                {},
            )
            image_catalog_routing = copy.deepcopy(
                current_image_asset.get("shot_catalog_routing", {})
            )
            available_uuids = {
                item["shot_uuid"] for item in image_catalog
            }
            picker_catalog = [
                item
                for item in _normalize_shot_catalog(
                    current_picker.get("shot_catalog", [])
                )
                if item["shot_uuid"] in available_uuids
            ]
            # Release exact upstream authority through the standard no-loss
            # disconnect paths. Selected remote rows may remain as ordinary
            # native content, while dormant manual rows are restored exactly.
            state = _apply_image_asset_payload(
                copy.deepcopy(current), {}, connected=False
            )
            state = _apply_picker_payload(state, {}, connected=False)
            state["shot"] = _normalize_shot_selection({})
            image_asset = (
                state.get("image_asset")
                if isinstance(state.get("image_asset"), dict)
                else {}
            )
            image_asset["shot_catalog"] = image_catalog
            image_asset["shot_catalog_routing"] = image_catalog_routing
            image_asset["shot_routing"] = {}
            state["image_asset"] = image_asset
            picker = (
                state.get("picker")
                if isinstance(state.get("picker"), dict)
                else {}
            )
            picker["shot_catalog"] = picker_catalog
            picker["shot_routing"] = {}
            state["picker"] = picker
            normalized = _normalize_state(state)
            self._hmb_current_shot_images = []
            self._hmb_current_shot_videos = []
            self._hmb_last_shot_context = {}
            self._hmb_last_agent_context_pair = {}
            self._hmb_shot_route_status = {
                "ok": False,
                "code": _clean_string(reason)[:128] or "duplicate_prompt_shot",
            }
            if normalized != current:
                self._hmb_compact_route_syncing = True
                try:
                    _set_parameter_value(
                        self, WIDGET_PARAMETER_NAME, _json_dumps(normalized)
                    )
                finally:
                    self._hmb_compact_route_syncing = False
            return self._hmb_shot_channel_subscription()

    def _hmb_clear_shot_routing_catalog(
        self, reason: str = "publisher_unavailable"
    ) -> Dict[str, Any]:
        """Drop remote Shot authority without deleting independent content.

        The graph helper calls this when the ImageAsset publisher disappears or
        becomes ambiguous.  Restore dormant manual rows and immediately publish
        the resulting local-only Prompt/media generation so downstream nodes can
        never retain the removed publisher's Shot outputs.
        """

        with self._hmb_sync_lock:
            current = self._current_state()
            state = _apply_image_asset_payload(current, {}, connected=False)
            state = _apply_picker_payload(state, {}, connected=False)
            state["shot"] = _normalize_shot_selection({})
            image_asset = (
                state.get("image_asset")
                if isinstance(state.get("image_asset"), dict)
                else {}
            )
            image_asset["shot_catalog"] = []
            image_asset["shot_catalog_routing"] = {}
            image_asset["shot_routing"] = {}
            state["image_asset"] = image_asset
            picker = (
                state.get("picker")
                if isinstance(state.get("picker"), dict)
                else {}
            )
            picker["shot_catalog"] = []
            picker["shot_routing"] = {}
            state["picker"] = picker
            normalized = _normalize_state(state)
            if normalized != current:
                try:
                    previous_source_revision = max(
                        0,
                        int(current.get(SOURCE_SYNC_REVISION_KEY) or 0),
                    )
                except Exception:
                    previous_source_revision = 0
                normalized[SOURCE_SYNC_REVISION_KEY] = min(
                    MAX_SOURCE_SYNC_REVISION,
                    previous_source_revision + 1,
                )
                normalized = _normalize_state(normalized)
            self._hmb_current_shot_images = []
            self._hmb_current_shot_videos = []
            self._hmb_last_shot_context = {}
            self._hmb_last_agent_context_pair = {}
            self._hmb_shot_route_status = {
                "ok": False,
                "code": _clean_string(reason)[:128] or "publisher_unavailable",
            }
            if normalized != current:
                self._hmb_compact_route_syncing = True
                try:
                    _set_parameter_value(
                        self, WIDGET_PARAMETER_NAME, _json_dumps(normalized)
                    )
                finally:
                    self._hmb_compact_route_syncing = False
            # The widget setter above is deliberately non-recursive. Compile
            # the restored local/Only state explicitly and publish both media
            # caches before PROMPT_OUT as one paired Prompt generation. Empty
            # video ownership remains the valid [] no-video contract.
            self._sync_prompt_output_from_state(publish_shot_media=True)
            return self._hmb_shot_channel_subscription()

    def _hmb_reconcile_shot_routing(
        self,
        routing_snapshot: Any = None,
        image_source_node: Any = None,
        picker_source_node: Any = None,
    ) -> Dict[str, Any]:
        """Helper hook for atomic auto-edge setup/reconciliation."""

        with self._hmb_sync_lock:
            if routing_snapshot is not None:
                state = self._current_state()
                current = _normalize_shot_selection(state.get("shot"))
                catalog = _validate_shot_routing_catalog(
                    routing_snapshot,
                    expected_channel_uuid=current["channel_uuid"],
                )
                image_asset = (
                    state.get("image_asset")
                    if isinstance(state.get("image_asset"), dict)
                    else {}
                )
                _assert_monotonic_shot_catalog(
                    self._routing_watermark_for_validation(
                        image_asset.get("shot_catalog_routing")
                    ),
                    catalog,
                )
                previous_catalog = _normalize_shot_catalog(
                    image_asset.get("shot_catalog")
                )
                selected_by_uuid = {
                    item["shot_uuid"]: list(item["selected_source_uids"])
                    for item in previous_catalog
                }
                if current["shot_uuid"]:
                    selected_by_uuid[current["shot_uuid"]] = list(
                        current["selected_source_uids"]
                    )
                full_compact_shots = [
                    {
                        "shot_uuid": item["shot_uuid"],
                        "channel_uuid": catalog["channel_uuid"],
                        "name": item["name"],
                        "number": item["number"],
                        # A compact callback may preserve a selection that was
                        # already proven by a full exact-source compile, but it
                        # can never introduce a source address itself.
                        "selected_source_uids": selected_by_uuid.get(
                            item["shot_uuid"], []
                        ),
                    }
                    for item in catalog["shots"]
                ]
                compact_shots = self._hmb_available_prompt_shot_catalog(
                    full_compact_shots,
                    current,
                )
                selected = next(
                    (
                        item for item in compact_shots
                        if item["shot_uuid"] == current["shot_uuid"]
                    ),
                    None,
                )
                initial_autoclaim = bool(
                    selected is None
                    and not current["channel_uuid"]
                    and not current["shot_uuid"]
                    and getattr(
                        self,
                        "_hmb_initial_shot_autoclaim_pending",
                        False,
                    )
                    and compact_shots
                )
                if initial_autoclaim:
                    preferred_uuid = _clean_string(
                        getattr(
                            self,
                            "_hmb_initial_shot_preferred_uuid",
                            "",
                        )
                    )
                    selected = next(
                        (
                            item for item in compact_shots
                            if item["shot_uuid"] == preferred_uuid
                        ),
                        compact_shots[0],
                    )
                if selected is None:
                    # Blank recipients remain independently usable. The same
                    # fallback also handles deletion of the active UUID; the
                    # renumbered catalog stays available for a new explicit pick.
                    state["shot"] = _normalize_shot_selection({})
                else:
                    state["shot"] = selected
                if initial_autoclaim:
                    self._hmb_initial_shot_autoclaim_pending = False
                    self._hmb_initial_shot_preferred_uuid = ""
                    self._hmb_initial_shot_exact_refresh_pending = True
                image_asset["shot_catalog"] = compact_shots
                image_asset["shot_catalog_routing"] = (
                    _catalog_routing_projection(catalog)
                )
                state["image_asset"] = image_asset
                normalized = _normalize_state(state)
                persisted = self._current_state()
                if normalized != persisted:
                    # A compact Shot catalog is backend source authority, not a
                    # local dashboard edit.  Without advancing the source
                    # revision, a retained-mode props echo can be rejected by
                    # the widget whenever a more recent local UI revision is
                    # present, leaving add/rename/delete options visibly stale.
                    # Keep the UI revision untouched and advance only the
                    # source watermark once for this accepted catalog
                    # generation.
                    try:
                        previous_source_revision = max(
                            0,
                            int(
                                persisted.get(SOURCE_SYNC_REVISION_KEY)
                                or 0
                            ),
                        )
                    except Exception:
                        previous_source_revision = 0
                    normalized[SOURCE_SYNC_REVISION_KEY] = min(
                        MAX_SOURCE_SYNC_REVISION,
                        previous_source_revision + 1,
                    )
                    normalized = _normalize_state(normalized)
                    # One compact callback is only a change signal/catalog
                    # refresh. Resolve the exact connected source snapshot and
                    # publish PROMPT_OUT/Shot media in this same transaction;
                    # otherwise a live ImageAsset membership/name edit can
                    # leave already connected Prompt outputs stale until the
                    # user touches or runs the Prompt node again.
                    self._hmb_compact_route_syncing = True
                    try:
                        _set_parameter_value(
                            self,
                            WIDGET_PARAMETER_NAME,
                            _json_dumps(normalized),
                        )
                    finally:
                        self._hmb_compact_route_syncing = False
                    # Active UUID deletion is also an authoritative change.
                    # Compile it immediately so the Prompt returns to Only and
                    # publishes empty Shot media instead of retaining the
                    # deleted Shot until the next unrelated edit. A Prompt that
                    # was already in Only receives choices only; asking it for
                    # exact source data before managed edges exist would erase
                    # the just-accepted catalog. The exact picker empty-
                    # selection path remains valid and produces
                    # SHOT_VIDEO_OUT=[] without an error.
                    if (
                        not initial_autoclaim
                        and (selected is not None or current["shot_uuid"])
                    ):
                        self._sync_prompt_output_from_state(
                            publish_shot_media=True,
                        )
                return self._hmb_shot_channel_subscription()
            if image_source_node is None and picker_source_node is None:
                self._reconcile_connected_source_inputs_from_graph()
            state, images, videos, _image_exact, _picker_exact = (
                self._apply_exact_shot_routes(
                    self._current_state(),
                    image_source_node=image_source_node,
                    picker_source_node=picker_source_node,
                )
            )
            self._hmb_current_shot_images = list(images)
            self._hmb_current_shot_videos = list(videos)
            _set_parameter_value(self, WIDGET_PARAMETER_NAME, _json_dumps(state))
            if _image_exact or _picker_exact:
                self._consume_routing_hydration_rebase()
            self._sync_prompt_output_from_state(publish_shot_media=True)
            return self._hmb_shot_channel_subscription()

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if isinstance(value, dict):
            self._hmb_shot_route_status = copy.deepcopy(value)

    def _reconcile_shared_shot_edges(self) -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)) or self._hmb_shared_routing_in_progress:
            return
        try:
            from _hmb_shot_routing import reconcile_shot_routing
        except Exception:
            return
        try:
            self._hmb_shared_routing_in_progress = True
            result = reconcile_shot_routing(self)
        finally:
            self._hmb_shared_routing_in_progress = False
        if not isinstance(result, dict) or bool(result.get("ok", True)):
            return
        node_prefix = _clean_string(getattr(self, "name", "")) + ":"
        failures = result.get("failures")
        own_failures = [
            _clean_string(item)
            for item in (failures if isinstance(failures, (list, tuple)) else [])
            if _clean_string(item).startswith(node_prefix)
        ]
        if own_failures:
            raise _ShotRoutingContractError("; ".join(own_failures))

    def _schedule_post_hydration_shot_reconcile(self) -> bool:
        """Re-run same-flow routing after the serialized selector is restored."""

        try:
            from _hmb_shot_routing import schedule_post_hydration_reconcile
        except Exception:
            return False
        return bool(schedule_post_hydration_reconcile(self))

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Reconcile real source caches after initial Prompt hydration writes."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return

        parent_setter = getattr(super(), "set_parameter_value")
        is_widget_write = param_name == WIDGET_PARAMETER_NAME
        if is_widget_write and initial_setup:
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            self._hmb_initial_shot_exact_refresh_pending = False
            self._arm_routing_hydration_rebase(value)
        guarded_widget_write = bool(
            is_widget_write
            and not initial_setup
            and not getattr(self, "_hmb_ui_syncing", False)
            and not getattr(self, "_hmb_restoring_widget_state", False)
        )
        if guarded_widget_write and self._widget_state_write_is_stale(value):
            # A stale request can arrive either before or after the host has
            # assigned its raw parameter value. Restore the accepted canonical
            # baseline in both cases and never compile the older selection.
            self._restore_accepted_widget_state()
            return
        if guarded_widget_write:
            value = self._hmb_filter_prompt_widget_write(value)

        previous_widget_state = getattr(
            self, "_hmb_last_accepted_widget_state", None
        )
        previous_widget_revisions = getattr(
            self, "_hmb_last_accepted_widget_revisions", (0, 0)
        )
        if is_widget_write:
            self._accept_widget_state_baseline(value)
            self._hmb_widget_write_in_progress = True
        try:
            if ParameterMode is None:
                parent_setter(param_name, value)
            else:
                parent_setter(
                    param_name,
                    value,
                    initial_setup=initial_setup,
                    emit_change=emit_change,
                    skip_before_value_set=skip_before_value_set,
                )
        except Exception:
            if is_widget_write:
                self._hmb_last_accepted_widget_state = previous_widget_state
                self._hmb_last_accepted_widget_revisions = (
                    previous_widget_revisions
                )
            raise
        finally:
            if is_widget_write:
                self._hmb_widget_write_in_progress = False
        if (
            not initial_setup
            or param_name
            not in {
                WIDGET_PARAMETER_NAME,
                PICKER_INPUT_PARAMETER_NAME,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                SHOT_ASSET_INPUT_PARAMETER_NAME,
                SHOT_PICKER_INPUT_PARAMETER_NAME,
            }
            or getattr(self, "_hmb_hydration_reconciling", False)
            or not hasattr(self, "_hmb_sync_lock")
        ):
            return
        try:
            self._hmb_hydration_reconciling = True
            if self._reconcile_connected_source_inputs_from_graph():
                self._sync_prompt_output_now()
        except Exception as exc:
            _diagnostic_exception(
                "Initial connected source hydration reconciliation failed",
                exc,
            )
        finally:
            self._hmb_hydration_reconciling = False
            self._schedule_post_hydration_shot_reconcile()

    def _current_state(self) -> Dict[str, Any]:
        self._ensure_prompt_output()
        state = _parse_state(_get_parameter_raw(self, WIDGET_PARAMETER_NAME))
        if not state:
            state = _default_widget_state()
        return state

    @staticmethod
    def _widget_revision_pair(value: Any) -> tuple[int, int] | None:
        state = value if isinstance(value, dict) else _parse_state(value)
        if not isinstance(state, dict) or not state:
            return None

        def bounded_revision(key: str) -> int:
            try:
                revision = int(state.get(key) or 0)
            except Exception:
                revision = 0
            return max(0, min(MAX_SOURCE_SYNC_REVISION, revision))

        return (
            bounded_revision(SOURCE_SYNC_REVISION_KEY),
            bounded_revision(UI_EDIT_REVISION_KEY),
        )

    def _accept_widget_state_baseline(self, value: Any) -> None:
        state = value if isinstance(value, dict) else _parse_state(value)
        if not isinstance(state, dict) or not state:
            return
        normalized = _normalize_state(state)
        self._hmb_last_accepted_widget_state = _json_dumps(normalized)
        self._hmb_last_accepted_widget_revisions = (
            int(normalized.get(SOURCE_SYNC_REVISION_KEY) or 0),
            int(normalized.get(UI_EDIT_REVISION_KEY) or 0),
        )
        self._seed_source_fingerprint_baseline_from_state(normalized)

    def _seed_source_fingerprint_baseline_from_state(
        self,
        state: Dict[str, Any],
    ) -> None:
        """Seed restored source identities before host setter hooks can sync.

        The real Griptape setter invokes ``after_value_set`` synchronously.
        During workflow hydration, HMB_UI_STATE is commonly assigned before the
        corresponding connected input cache.  Record only a private identity
        sentinel here; once that raw source arrives, `_write_dashboard_state`
        verifies it against the persisted run/selection and consumes it without
        creating a false source revision.
        """

        fingerprints = getattr(self, "_hmb_source_input_fingerprints", None)
        if not isinstance(fingerprints, dict):
            return
        disconnected_fingerprint = _connected_source_fingerprint({}, False)
        picker = state.get("picker")
        if (
            isinstance(picker, dict)
            and bool(picker.get("enabled"))
            and fingerprints.get(PICKER_INPUT_PARAMETER_NAME)
            == disconnected_fingerprint
        ):
            fingerprints[PICKER_INPUT_PARAMETER_NAME] = (
                "persisted-picker:"
                + _clean_string(picker.get("run_id"))
                + ":"
                + _clean_string(picker.get("selection_id"))
            )
        image_asset = state.get("image_asset")
        if (
            isinstance(image_asset, dict)
            and bool(image_asset.get("enabled"))
            and fingerprints.get(IMAGE_ASSET_INPUT_PARAMETER_NAME)
            == disconnected_fingerprint
        ):
            fingerprints[IMAGE_ASSET_INPUT_PARAMETER_NAME] = (
                "persisted-image-asset:"
                + _clean_string(image_asset.get("selection_id"))
                + ":"
                + _clean_string(image_asset.get("project_uid"))
                + ":"
                + _clean_string(image_asset.get("project_id"))
            )

    def _widget_state_write_is_stale(self, value: Any) -> bool:
        incoming = self._widget_revision_pair(value)
        if incoming is None or self._hmb_last_accepted_widget_state is None:
            return False
        accepted_source, accepted_ui = self._hmb_last_accepted_widget_revisions
        incoming_source, incoming_ui = incoming
        if incoming_source < accepted_source:
            return True
        return incoming_source == accepted_source and incoming_ui < accepted_ui

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
                parent_setter(WIDGET_PARAMETER_NAME, cached)
            else:
                parent_setter(
                    WIDGET_PARAMETER_NAME,
                    cached,
                    initial_setup=False,
                    emit_change=False,
                    skip_before_value_set=True,
                )
        finally:
            self._hmb_restoring_widget_state = False

    def _write_dashboard_state(self) -> Dict[str, Any]:
        if getattr(self, "_hmb_ui_syncing", False):
            return self._current_state()
        try:
            self._hmb_ui_syncing = True
            graph_sources_authoritative = (
                self._reconcile_connected_source_inputs_from_graph()
            )
            raw_widget_value = _get_parameter_raw(self, WIDGET_PARAMETER_NAME)
            current_state = self._current_state()
            state = _normalize_state(current_state)
            source_sync_revision = int(state.get(SOURCE_SYNC_REVISION_KEY) or 0)
            source_state_before_sync = state
            state_before_source_sync = _json_dumps(source_state_before_sync)
            previous_source_fingerprints = getattr(
                self,
                "_hmb_source_input_fingerprints",
                {},
            )
            (
                state,
                shot_images,
                shot_videos,
                image_exact,
                picker_exact,
            ) = self._apply_exact_shot_routes(state)
            self._hmb_current_shot_images = list(shot_images)
            self._hmb_current_shot_videos = list(shot_videos)
            image_asset_payload = _parse_image_asset_payload(
                _get_parameter_raw(self, IMAGE_ASSET_INPUT_PARAMETER_NAME)
            )
            image_asset_connected = bool(
                getattr(self, "_hmb_image_asset_connected", False)
                or image_asset_payload
            )
            pending_image_asset_hydration = bool(
                not graph_sources_authoritative
                and not image_asset_connected
                and not image_asset_payload
                and str(
                    previous_source_fingerprints.get(
                        IMAGE_ASSET_INPUT_PARAMETER_NAME,
                        "",
                    )
                ).startswith("persisted-image-asset:")
            )
            if not pending_image_asset_hydration and not image_exact:
                state = _apply_image_asset_payload(
                    state,
                    image_asset_payload,
                    connected=image_asset_connected,
                )
            picker_payload = _parse_picker_payload(_get_parameter_raw(self, PICKER_INPUT_PARAMETER_NAME))
            picker_connected = bool(getattr(self, "_hmb_picker_connected", False) or picker_payload)
            pending_picker_hydration = bool(
                not graph_sources_authoritative
                and not picker_connected
                and not picker_payload
                and str(
                    previous_source_fingerprints.get(
                        PICKER_INPUT_PARAMETER_NAME,
                        "",
                    )
                ).startswith("persisted-picker:")
            )
            image_fingerprint_payload = (
                {"shot_routing": state["image_asset"].get("shot_routing", {})}
                if image_exact
                else image_asset_payload
            )
            picker_fingerprint_payload = (
                {"shot_routing": state["picker"].get("shot_routing", {})}
                if picker_exact
                else picker_payload
            )
            image_fingerprint_connected = image_exact or image_asset_connected
            picker_fingerprint_connected = picker_exact or picker_connected
            source_input_fingerprints = {
                IMAGE_ASSET_INPUT_PARAMETER_NAME: (
                    previous_source_fingerprints.get(
                        IMAGE_ASSET_INPUT_PARAMETER_NAME,
                        _connected_source_fingerprint({}, False),
                    )
                    if pending_image_asset_hydration
                    else _connected_source_fingerprint(
                        image_fingerprint_payload,
                        image_fingerprint_connected,
                    )
                ),
                PICKER_INPUT_PARAMETER_NAME: (
                    previous_source_fingerprints.get(
                        PICKER_INPUT_PARAMETER_NAME,
                        _connected_source_fingerprint({}, False),
                    )
                    if pending_picker_hydration
                    else _connected_source_fingerprint(
                        picker_fingerprint_payload,
                        picker_fingerprint_connected,
                    )
                ),
            }
            source_payloads = {
                IMAGE_ASSET_INPUT_PARAMETER_NAME: image_fingerprint_payload,
                PICKER_INPUT_PARAMETER_NAME: picker_fingerprint_payload,
            }
            source_connections = {
                IMAGE_ASSET_INPUT_PARAMETER_NAME: image_fingerprint_connected,
                PICKER_INPUT_PARAMETER_NAME: picker_fingerprint_connected,
            }
            upstream_source_changed = False
            for name, fingerprint in source_input_fingerprints.items():
                previous_fingerprint = previous_source_fingerprints.get(name)
                if previous_fingerprint == fingerprint:
                    continue
                disconnected_fingerprint = _connected_source_fingerprint(
                    {}, False
                )
                establishes_hydrated_baseline = bool(
                    (
                        previous_fingerprint == disconnected_fingerprint
                        or str(previous_fingerprint or "").startswith(
                            "persisted-"
                        )
                    )
                    and _source_identity_already_applied(
                        source_state_before_sync,
                        name,
                        source_payloads[name],
                        source_connections[name],
                    )
                )
                if not establishes_hydrated_baseline:
                    upstream_source_changed = True
            if not pending_picker_hydration and not picker_exact:
                state = _apply_picker_payload(
                    state,
                    picker_payload,
                    connected=picker_connected,
                )
            source_application_changed_state = (
                _json_dumps(state) != state_before_source_sync
            )
            if upstream_source_changed and source_application_changed_state:
                state[SOURCE_SYNC_REVISION_KEY] = min(
                    MAX_SOURCE_SYNC_REVISION,
                    source_sync_revision + 1,
                )
            # A widget edit has already stored its complete canonical state before
            # this deferred synchronization runs. Writing the same value back
            # produces a second frontend props update and can remount the full
            # dashboard after a local select/Range change. Keep canonicalization
            # and Picker synchronization authoritative, but publish the widget
            # parameter only when either operation actually changed its value.
            if state != current_state or not isinstance(raw_widget_value, str):
                _set_parameter_value(self, WIDGET_PARAMETER_NAME, _json_dumps(state))
            if image_exact or picker_exact:
                self._consume_routing_hydration_rebase()
            self._hmb_source_input_fingerprints = source_input_fingerprints
            return state
        finally:
            self._hmb_ui_syncing = False

    def _sync_prompt_output_from_state(
        self,
        *,
        publish_shot_media: bool = False,
    ) -> Dict[str, Any]:
        """Commit the latest widget state and refresh PROMPT_OUT immediately.

        The paid Agent may be run directly after editing the dashboard.  PROMPT_OUT
        must therefore never depend on a separate HMBPromptLibrary run or on the
        editor losing focus first.
        """
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return {}
        state, prompt, machine_prompt, fingerprint = (
            self._compile_current_prompt_pair()
        )
        output_values = getattr(self, "parameter_output_values", {})
        output_getter = getattr(output_values, "get", None)
        current_output = output_getter("PROMPT_OUT") if callable(output_getter) else None
        shot_images = list(getattr(self, "_hmb_current_shot_images", []))
        shot_videos = list(getattr(self, "_hmb_current_shot_videos", []))
        current_images = (
            output_getter(SHOT_IMAGE_OUTPUT_PARAMETER_NAME)
            if callable(output_getter)
            else None
        )
        current_videos = (
            output_getter(SHOT_VIDEO_OUTPUT_PARAMETER_NAME)
            if callable(output_getter)
            else None
        )
        cached_output = getattr(self, "_hmb_last_prompt_output", None)
        cached_machine = getattr(self, "_hmb_last_machine_prompt_output", None)
        changed_shot_outputs: List[tuple[str, List[str]]] = []
        if current_images != shot_images:
            changed_shot_outputs.append(
                (SHOT_IMAGE_OUTPUT_PARAMETER_NAME, list(shot_images))
            )
        if current_videos != shot_videos:
            changed_shot_outputs.append(
                (SHOT_VIDEO_OUTPUT_PARAMETER_NAME, list(shot_videos))
            )
        if (
            fingerprint
            == getattr(self, "_hmb_last_prompt_semantic_fingerprint", "")
            and cached_output is not None
            and cached_machine is not None
        ):
            if current_images != shot_images:
                set_output(self, SHOT_IMAGE_OUTPUT_PARAMETER_NAME, shot_images)
            if current_videos != shot_videos:
                set_output(self, SHOT_VIDEO_OUTPUT_PARAMETER_NAME, shot_videos)
            if publish_shot_media:
                _notify_prompt_shot_media_outputs(self, changed_shot_outputs)
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

        # Pair both representations before publishing PROMPT_OUT. Publication can
        # synchronously re-enter the connected Agent, which must never observe a
        # new visible document with an older machine envelope.
        self._hmb_prompt_snapshot_generation = (
            int(getattr(self, "_hmb_prompt_snapshot_generation", 0)) + 1
        )
        self._hmb_last_prompt_semantic_fingerprint = fingerprint
        self._hmb_last_prompt_output = prompt
        self._hmb_last_machine_prompt_output = machine_prompt
        self._hmb_last_shot_images = list(shot_images)
        self._hmb_last_shot_videos = list(shot_videos)
        try:
            self._hmb_last_shot_context = _agent_shot_context(
                state,
                prompt_generation=self._hmb_prompt_snapshot_generation,
                visible_prompt=prompt,
                image_media=shot_images,
                video_media=shot_videos,
            )
        except _ShotRoutingContractError:
            self._hmb_last_shot_context = {}
        # Stage both ordered media halves before PROMPT_OUT wakes an Agent.
        set_output(self, SHOT_IMAGE_OUTPUT_PARAMETER_NAME, shot_images)
        set_output(self, SHOT_VIDEO_OUTPUT_PARAMETER_NAME, shot_videos)
        if publish_shot_media:
            _notify_prompt_shot_media_outputs(self, changed_shot_outputs)
        if current_output != prompt:
            _stage_and_notify_prompt_output(self, prompt)
        else:
            # Machine-only changes (for example USER DESCRIPTION or a validated
            # Range fact) keep the same concise display but must still wake the
            # directly connected Agent with the newly paired generation.
            _stage_and_notify_prompt_output(
                self,
                prompt,
                stage_output=False,
            )
        return state

    def _compile_current_prompt_pair(
        self,
    ) -> tuple[Dict[str, Any], str, str, str]:
        """Compile both Prompt representations from one current-state snapshot.

        Griptape hydrates persisted parameter values after constructing a node.
        This pure publication-free compiler lets the Agent recover the private
        pair from those hydrated values without parsing the human document or
        publishing a second output during Agent resolution.
        """

        self._reconcile_shared_shot_edges()
        state = self._write_dashboard_state()
        prompt = _build_prompt_package(state)
        machine_prompt = _build_data_only_prompt_package(state)
        fingerprint = _prompt_semantic_fingerprint(
            state,
            public_prompt=prompt,
            machine_prompt=machine_prompt,
        )
        return state, prompt, machine_prompt, fingerprint

    def _cache_prompt_pair(
        self,
        prompt: str,
        machine_prompt: str,
        fingerprint: str,
    ) -> int:
        """Atomically retain one compiled human/machine generation."""

        changed = bool(
            prompt != getattr(self, "_hmb_last_prompt_output", None)
            or machine_prompt
            != getattr(self, "_hmb_last_machine_prompt_output", None)
            or fingerprint
            != getattr(self, "_hmb_last_prompt_semantic_fingerprint", "")
            or int(getattr(self, "_hmb_prompt_snapshot_generation", 0) or 0) < 1
        )
        if changed:
            self._hmb_prompt_snapshot_generation = (
                int(getattr(self, "_hmb_prompt_snapshot_generation", 0) or 0)
                + 1
            )
        self._hmb_last_prompt_semantic_fingerprint = fingerprint
        self._hmb_last_prompt_output = prompt
        self._hmb_last_machine_prompt_output = machine_prompt
        return int(self._hmb_prompt_snapshot_generation)

    def _hmb_agent_prompt_snapshot(self, expected_visible: Any) -> Dict[str, Any]:
        """Return the exact private envelope paired with one visible PROMPT_OUT."""

        incoming = getattr(expected_visible, "value", expected_visible)
        incoming_text = str(incoming or "")
        with self._hmb_sync_lock:
            # Parameter hydration bypasses after_value_set and the host does not
            # call this library's deserialize/load hooks. Recompile on every
            # Agent snapshot request so a constructor-time default cache can
            # never be paired with later hydrated state. This also catches a
            # machine-only state change whose concise visible text is unchanged.
            (
                _state,
                visible,
                machine,
                fingerprint,
            ) = self._compile_current_prompt_pair()
            # Griptape's execution hydration removes terminal line separators
            # from a string output. Treat that transport-only normalization as
            # equivalent while keeping every document character before it
            # exact; embedded line breaks and section text remain protected.
            if incoming_text.rstrip("\r\n") != visible.rstrip("\r\n"):
                raise RuntimeError("HMB Prompt paired snapshot is unavailable.")
            generation = self._cache_prompt_pair(
                visible,
                machine,
                fingerprint,
            )
            try:
                paired_shot_context = _agent_shot_context(
                    _state,
                    prompt_generation=generation,
                    visible_prompt=incoming_text,
                    image_media=list(self._hmb_current_shot_images),
                    video_media=list(self._hmb_current_shot_videos),
                )
            except _ShotRoutingContractError:
                paired_shot_context = {}
            self._hmb_last_agent_context_pair = {
                "visible_prompt": incoming_text.rstrip("\r\n"),
                "context": copy.deepcopy(paired_shot_context),
            }
            self._hmb_agent_pair_local.pair = copy.deepcopy(
                self._hmb_last_agent_context_pair
            )
            return {
                "schema": "hmb-prompt-paired-snapshot",
                "version": 1,
                "generation": generation,
                "visible_sha256": hashlib.sha256(
                    incoming_text.encode("utf-8")
                ).hexdigest(),
                "machine_sha256": hashlib.sha256(
                    machine.encode("utf-8")
                ).hexdigest(),
                "machine_prompt": machine,
            }

    def _hmb_agent_shot_context(
        self, expected_visible_prompt: Any
    ) -> Dict[str, Any]:
        """Return the shot/media hashes paired with one exact visible prompt."""

        incoming = getattr(
            expected_visible_prompt, "value", expected_visible_prompt
        )
        incoming_text = str(incoming or "")
        with self._hmb_sync_lock:
            paired = getattr(self._hmb_agent_pair_local, "pair", None)
            if (
                isinstance(paired, dict)
                and paired.get("visible_prompt") == incoming_text.rstrip("\r\n")
                and isinstance(paired.get("context"), dict)
            ):
                context = copy.deepcopy(paired["context"])
                self._hmb_last_agent_context_pair = {}
                self._hmb_agent_pair_local.pair = None
                return context
            state, visible, machine, fingerprint = (
                self._compile_current_prompt_pair()
            )
            if incoming_text.rstrip("\r\n") != visible.rstrip("\r\n"):
                raise RuntimeError("HMB Prompt shot context is unavailable.")
            generation = self._cache_prompt_pair(
                visible, machine, fingerprint
            )
            try:
                context = _agent_shot_context(
                    state,
                    prompt_generation=generation,
                    visible_prompt=incoming_text,
                    image_media=list(self._hmb_current_shot_images),
                    video_media=list(self._hmb_current_shot_videos),
                )
            except _ShotRoutingContractError:
                if self._hmb_shot_channel_subscription().get("enabled"):
                    raise
                context = {}
            self._hmb_last_shot_context = copy.deepcopy(context)
            self._hmb_last_shot_images = list(self._hmb_current_shot_images)
            self._hmb_last_shot_videos = list(self._hmb_current_shot_videos)
            self._hmb_last_agent_context_pair = {
                "visible_prompt": incoming_text.rstrip("\r\n"),
                "context": copy.deepcopy(context),
            }
            self._hmb_agent_pair_local.pair = None
            return context

    def _hmb_generator_shot_snapshot(
        self,
        expected_images: Any,
        expected_videos: Any,
    ) -> Dict[str, Any]:
        """Validate both hidden media edges against one current Prompt pair."""

        raw_images = getattr(expected_images, "value", expected_images)
        raw_videos = getattr(expected_videos, "value", expected_videos)
        if not isinstance(raw_images, list) or not isinstance(raw_videos, list):
            raise RuntimeError("HMB Prompt shot media inputs are invalid.")
        if any(not isinstance(value, str) for value in raw_images + raw_videos):
            raise RuntimeError("HMB Prompt shot media inputs are invalid.")
        with self._hmb_sync_lock:
            state, visible, machine, fingerprint = (
                self._compile_current_prompt_pair()
            )
            current_images = list(self._hmb_current_shot_images)
            current_videos = list(self._hmb_current_shot_videos)
            if raw_images != current_images or raw_videos != current_videos:
                raise RuntimeError(
                    "HMB Prompt shot media generation does not match."
                )
            generation = self._cache_prompt_pair(
                visible, machine, fingerprint
            )
            context = _agent_shot_context(
                state,
                prompt_generation=generation,
                visible_prompt=visible,
                image_media=current_images,
                video_media=current_videos,
            )
            return {
                **context,
                "schema": "hmb-prompt-generator-shot-snapshot",
                "version": 1,
                "image_media": current_images,
                "video_media": current_videos,
            }

    def _sync_prompt_output_now(self) -> Dict[str, Any]:
        """Invalidate queued callbacks and commit one authoritative snapshot."""
        with self._hmb_sync_lock:
            if bool(getattr(self, "_hmb_node_deleted", False)):
                return {}
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
            if bool(getattr(self, "_hmb_node_deleted", False)):
                return
            self._hmb_sync_generation += 1
            generation = self._hmb_sync_generation

        def run_sync() -> None:
            try:
                with self._hmb_sync_lock:
                    if (
                        bool(getattr(self, "_hmb_node_deleted", False))
                        or generation != self._hmb_sync_generation
                    ):
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
        _begin_prompt_output_side_effect_callback(self)
        try:
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
                if (
                    name == WIDGET_PARAMETER_NAME
                    and not getattr(self, "_hmb_ui_syncing", False)
                    and not getattr(self, "_hmb_restoring_widget_state", False)
                    and not getattr(self, "_hmb_widget_write_in_progress", False)
                ):
                    # Some host paths assign the Parameter first and invoke only
                    # this hook, bypassing this class's set_parameter_value
                    # override. Compare against the instance baseline before
                    # any prompt compile can consume that raw rollback.
                    if self._widget_state_write_is_stale(value):
                        self._restore_accepted_widget_state()
                        self._schedule_prompt_sync()
                        return result
                    self._accept_widget_state_baseline(value)
                if name == PICKER_INPUT_PARAMETER_NAME and _clean_string(value):
                    self._hmb_picker_connected = True
                if name == IMAGE_ASSET_INPUT_PARAMETER_NAME and _clean_string(value):
                    self._hmb_image_asset_connected = True
                if name in {
                    WIDGET_PARAMETER_NAME,
                    PICKER_INPUT_PARAMETER_NAME,
                    IMAGE_ASSET_INPUT_PARAMETER_NAME,
                    SHOT_ASSET_INPUT_PARAMETER_NAME,
                    SHOT_PICKER_INPUT_PARAMETER_NAME,
                } and not getattr(self, "_hmb_ui_syncing", False) and not getattr(
                    self, "_hmb_compact_route_syncing", False
                ):
                    self._schedule_prompt_sync()
            except Exception as exc:
                _diagnostic_exception("after_value_set scheduling failed", exc)
            return result
        finally:
            _end_prompt_output_side_effect_callback(self)

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        try:
            target_name = getattr(target_parameter, "name", "")
            if target_name in {
                PICKER_INPUT_PARAMETER_NAME,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                SHOT_ASSET_INPUT_PARAMETER_NAME,
                SHOT_PICKER_INPUT_PARAMETER_NAME,
            }:
                if target_name == PICKER_INPUT_PARAMETER_NAME:
                    self._hmb_picker_connected = True
                elif target_name in {
                    IMAGE_ASSET_INPUT_PARAMETER_NAME,
                    SHOT_ASSET_INPUT_PARAMETER_NAME,
                }:
                    self._hmb_image_asset_connected = True
                self._hmb_connected_source_nodes[target_name] = source_node
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
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        try:
            target_name = getattr(target_parameter, "name", "")
            if target_name in {
                PICKER_INPUT_PARAMETER_NAME,
                IMAGE_ASSET_INPUT_PARAMETER_NAME,
                SHOT_ASSET_INPUT_PARAMETER_NAME,
                SHOT_PICKER_INPUT_PARAMETER_NAME,
            }:
                if target_name == PICKER_INPUT_PARAMETER_NAME:
                    self._hmb_picker_connected = False
                elif target_name in {
                    IMAGE_ASSET_INPUT_PARAMETER_NAME,
                    SHOT_ASSET_INPUT_PARAMETER_NAME,
                }:
                    self._hmb_image_asset_connected = False
                self._hmb_connected_source_nodes.pop(target_name, None)
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

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        """Invalidate every deferred Prompt write before the host tears us down."""

        def invalidate() -> None:
            self._hmb_node_deleted = True
            self._hmb_sync_generation = (
                int(getattr(self, "_hmb_sync_generation", 0) or 0) + 1
            )
            self._hmb_prompt_notification_generation = (
                int(
                    getattr(
                        self, "_hmb_prompt_notification_generation", 0
                    )
                    or 0
                )
                + 1
            )
            self._hmb_pending_prompt_notification = None
            self._hmb_shot_media_notification_generation = (
                int(
                    getattr(
                        self,
                        "_hmb_shot_media_notification_generation",
                        0,
                    )
                    or 0
                )
                + 1
            )
            self._hmb_pending_shot_media_notifications = {}

        first_delete = not bool(getattr(self, "_hmb_node_deleted", False))
        if first_delete:
            # Do not wait for _hmb_sync_lock here. A worker can hold it while a
            # retained-mode request waits for this very deletion callback,
            # creating a host freeze. Flag/generation invalidation is immediate;
            # every deferred commit re-checks ownership before publication.
            invalidate()
        if first_delete and not bool(
            getattr(self, "_hmb_deletion_reconcile_called", False)
        ):
            self._hmb_deletion_reconcile_called = True
            try:
                from _hmb_shot_routing import schedule_post_deletion_reconcile

                schedule_post_deletion_reconcile(self)
            except Exception as exc:
                _diagnostic_exception(
                    "Post-deletion Shot routing schedule failed", exc
                )
        if bool(getattr(self, "_hmb_delete_parent_called", False)):
            return None
        self._hmb_delete_parent_called = True
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None

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
        self._hmb_initial_shot_autoclaim_pending = False
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_initial_shot_exact_refresh_pending = False
        self._arm_routing_hydration_rebase(
            _get_parameter_raw(self, WIDGET_PARAMETER_NAME)
        )
        self._ensure_prompt_output()
        self._restore_picker_connection_state()
        self._schedule_post_hydration_shot_reconcile()
        return result

    def after_load(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            result = super().after_load(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent after_load hook failed", exc)
        self._hmb_initial_shot_autoclaim_pending = False
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_initial_shot_exact_refresh_pending = False
        self._arm_routing_hydration_rebase(
            _get_parameter_raw(self, WIDGET_PARAMETER_NAME)
        )
        self._ensure_prompt_output()
        self._restore_picker_connection_state()
        self._schedule_post_hydration_shot_reconcile()
        return result

    def on_loaded(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            result = super().on_loaded(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent on_loaded hook failed", exc)
        self._hmb_initial_shot_autoclaim_pending = False
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_initial_shot_exact_refresh_pending = False
        self._arm_routing_hydration_rebase(
            _get_parameter_raw(self, WIDGET_PARAMETER_NAME)
        )
        self._ensure_prompt_output()
        self._restore_picker_connection_state()
        self._schedule_post_hydration_shot_reconcile()
        return result

    def process(self) -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        self._ensure_prompt_output()
        # The workflow executor owns normal process-output propagation.
        _begin_prompt_output_side_effect_callback(self)
        try:
            self._sync_prompt_output_now()
        finally:
            _end_prompt_output_side_effect_callback(self)
        return None
