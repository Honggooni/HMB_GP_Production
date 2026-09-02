from __future__ import annotations

from pathlib import Path
import base64
import copy
import hashlib
import importlib.util
import inspect
import json
import logging
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from contextlib import contextmanager, suppress
from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote, unquote, urlparse

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import _hmb_screen_space as _screen_space
import _hmb_shot_routing as _shot_routing


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
set_output = _hmb.set_output
parameter_exists = getattr(_hmb, "parameter_exists", lambda node, name: name in getattr(node, "parameters", {}))

try:
    from griptape_nodes.traits.file_system_picker import FileSystemPicker  # type: ignore
except Exception:
    FileSystemPicker = None  # type: ignore

try:
    from griptape_nodes.exe_types.param_types.parameter_string import ParameterString  # type: ignore
except Exception:
    ParameterString = None  # type: ignore

try:
    from griptape_nodes.traits.widget import Widget  # type: ignore
except Exception:
    Widget = None  # type: ignore

try:
    from griptape.artifacts import VideoUrlArtifact  # type: ignore
except Exception:
    VideoUrlArtifact = None  # type: ignore


MAYA_RUNNER = _THIS_DIR / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
MARKER_CATALOG_PATH = _THIS_DIR / "resources" / "picker" / "HMB_Marker_Catalog.json"
WIDGET_NAME = "HMBVideoPickerLibraryWidget"
WIDGET_LIBRARY_NAME = "HMB_GP_Production"
WIDGET_STATE_PARAMETER = "HMB_PICKER_STATE"
WIDGET_COMMAND_PARAMETER = "HMB_PICKER_COMMAND"
WIDGET_STATE_EMBEDDED_COMMAND_FIELD = "__hmb_picker_command__"
COMMAND_WIDGET_NAME = "HMBVideoPickerCommandBridgeWidget"
COMMAND_SCHEMA = "hmb-picker-command"
COMMAND_VERSION = 1
RESET_HANDOFF_SCHEMA = "hmb-video-picker-reset-handoff"
RESET_HANDOFF_VERSION = 1
RESET_HANDOFF_IDENTITY_CONTRACT = (
    "preserve-loader-channel-shot-new-picker-runtime-v1"
)
PICKER_WORKSPACE_SENSITIVE_ACTIONS = frozenset({
    "read_scene",
    "run_video",
    "render_snapshot",
    "delete_snapshot",
    "render_original_preview",
    "hide_original_preview",
    "browse_maya_scene",
    "browse_video_asset",
    "import_video_asset",
    "import_video_assets",
    "import_video",
})
OUTPUT_FPS = 24.0
OUTPUT_WIDTH = 1280
OUTPUT_HEIGHT = 720
PROXY_ENCODING_PROFILE = "hmb_hq_bt709_crf6_v1"
PROXY_ENCODER_PRESET = "slow"
PROXY_ENCODER_CRF = 6
PROXY_H264_PROFILE = "high"
PROXY_H264_LEVEL = "4.2"
FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE = "hmb_full_smooth_geometry_v2"
ORIGINAL_VIEWPORT_QUALITY_PROFILE = FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
ORIGINAL_MATERIAL_OVERRIDE_PROFILE = (
    "per_source_material_lambert_plugin_fallback_v4"
)
ORIGINAL_LAMBERT_ASSIGNMENT_MODE = (
    "original_per_source_material_lambert_plugin_fallback"
)
MOUTH_CARD_INNER_PATCH_POLICY = "temporary_mouth_alpha_inner_patch_v1"
SCREEN_SPACE_PATTERN_PROFILE = "hmb_screen_space_pattern_post_v2"
SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR = 3
MAYA_WORLD_PATTERN_PROFILE = "hmb_maya_world_root_projection_v1"
WORLD_PATTERN_BASE_CELL_WORLD_UNITS = 15.0
WORLD_PATTERN_DENSITY_MULTIPLIER = 3.0
WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS = (
    WORLD_PATTERN_BASE_CELL_WORLD_UNITS / WORLD_PATTERN_DENSITY_MULTIPLIER
)
MAYA_WORLD_PATTERN_PROJECTIONS = {
    "floor_grid": ("Planar", "XZ"),
    "direction_checker": ("TriPlanar", "XYZ"),
    "position_pattern": ("TriPlanar", "XYZ"),
    "sky_grid": ("TriPlanar", "XYZ"),
}
DEPTH_PLAYBLAST_PROFILE = "hmb_camera_space_depth_v7"
LEGACY_DEPTH_PLAYBLAST_PROFILES = frozenset({
    "hmb_camera_space_depth_v1",
    "hmb_camera_space_depth_v2",
    "hmb_camera_space_depth_v3",
    "hmb_camera_space_depth_v4",
    "hmb_camera_space_depth_v5",
    "hmb_camera_space_depth_v6",
})
DEPTH_MEDIA_KIND = "maya_depth_playblast"
DEPTH_SOURCE_TYPE = "Depth / Spatial Reference"
DEPTH_CONTROL_ROLE = "Spatial Alignment Verification Only"
DEPTH_NEAR_COLOR = 0.9
DEPTH_FAR_COLOR = 0.0
DEPTH_CAMERA_NEAR_SAFETY_MARGIN = 0.1
DEPTH_CONTRAST_EXPONENT = 1.0
DEPTH_FOREGROUND_NEAR_PERCENTILE = 0.01
DEPTH_FOREGROUND_FAR_PERCENTILE = 0.99
DEPTH_GENERIC_FAR_PERCENTILE = 0.95
DEPTH_GENERIC_PERCENTILE_MIN_SHAPES = 20
DEPTH_SCREEN_VERTEX_SAMPLE_LIMIT = 128
DEPTH_SCREEN_POLYGON_CENTER_SAMPLE_LIMIT = 64
DEPTH_REJECTION_ACCOUNTING_POLICY = "disjoint_normalization_outcomes"
DEPTH_QUALITY_SAMPLE_FRAMES = 7
DEPTH_GRAYSCALE_CHANNEL_TOLERANCE = 2
DEPTH_QUALITY_MIN_MEANINGFUL_LEVELS = 48
DEPTH_QUALITY_MIN_NORMALIZED_ENTROPY = 0.50
DEPTH_QUALITY_MAX_WHITE_SATURATION = 0.20
DEPTH_QUALITY_MIN_SMOOTH_NEIGHBORS = 0.03
DEPTH_QUALITY_MAX_LARGE_JUMPS = 0.10
DEPTH_QUALITY_MIN_PASS_FRACTION = 2.0 / 3.0
DEPTH_QUALITY_MIN_DIAGNOSTIC_FOREGROUND_PIXELS = 32
MOTION_GUIDE_PROFILE = "hmb_target_neutral_motion_guide_v5"
LEGACY_MOTION_GUIDE_PROFILES = frozenset({
    "hmb_target_neutral_motion_guide_v4",
})
MOTION_GUIDE_COMPATIBLE_PROFILES = frozenset({
    MOTION_GUIDE_PROFILE,
})
MOTION_GUIDE_RUNNER_SCHEMA_VERSION = 2
MOTION_GUIDE_SIDECAR_SCHEMA_VERSION = 2
MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES = 6
MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE = 32
MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE = 64
MOTION_GUIDE_FACE_BROW_RGB = (176, 96, 255)
MOTION_GUIDE_FACE_EYELID_RGB = (48, 196, 255)
MOTION_GUIDE_FACE_MOUTH_RGB = (255, 72, 180)
MOTION_GUIDE_FACE_JAW_RGB = (255, 176, 64)
MOTION_GUIDE_MEDIA_KIND = "maya_motion_guide"
MOTION_GUIDE_SOURCE_TYPE = "Motion Guide / Retargeting Reference"
MOTION_GUIDE_CONTROL_ROLE = "Derived Motion Decoding Only"
ORIGINAL_MEDIA_KIND = "maya_original_playblast"
MASK_MEDIA_KIND = "maya_color_assignment_mask"
PRIMARY_COLOR_VIDEO_SLOT = 1
MAX_SELECTED_VIDEOS = 10
# Selection/output order remains bounded to ten within the active Shot. Durable
# catalog ownership is partitioned separately across five 10-asset Shot rows.
MAX_REPRESENTATIVE_VIDEOS = MAX_SELECTED_VIDEOS
MAX_VIDEO_IMPORT_BATCH = 100
MAX_SNAPSHOT_HISTORY = 10
# ``MAX_VIDEO_SLOTS`` remains as a compatibility name for the Maya staging and
# legacy widget command code.  Public media is no longer represented by fixed
# output ports: selected catalog records receive transient @video1..@video10
# positions only when state/output snapshots are normalized.
MAX_VIDEO_SLOTS = MAX_SELECTED_VIDEOS
# These numbers are private runner compatibility tags for the one-pass Maya
# Mask/Depth/Motion bundle. They are never public catalog identities, never
# become output ports, and cannot limit or reorder the catalog selection.
AUXILIARY_VIDEO_SLOTS = (2, 3, 4, 5)
VIDEO_OUTPUT_PARAMETER = "VIDEO_OUT"
SHOT_PICKER_OUTPUT_PARAMETER = "SHOT_PICKER_OUT"
SHOT_ROUTING_SNAPSHOT_SCHEMA = "hmb-picker-shot-routing-snapshot"
SHOT_ROUTING_SNAPSHOT_VERSION = 1
SHOT_ROUTING_MAX_SHOTS = 5
MAX_VIDEO_ASSETS_PER_PICKER_SHOT = 10
MAX_PICKER_VIDEO_ASSETS = (
    SHOT_ROUTING_MAX_SHOTS * MAX_VIDEO_ASSETS_PER_PICKER_SHOT
)
VIDEO_THUMBNAIL_WIDTH = 320
VIDEO_THUMBNAIL_HEIGHT = 180
VIDEO_THUMBNAIL_TIMEOUT_SECONDS = 20.0
# StaticFilesManager URLs belong to one Python/static-server lifetime.  The
# token is serialized beside each URL so a workflow reopened by a later engine
# can discard only that process-local URL while retaining all durable media and
# Shot ownership fields.
_VIDEO_THUMBNAIL_RUNTIME_ID = uuid.uuid4().hex
_VIDEO_THUMBNAIL_LOCK = threading.RLock()
_VIDEO_THUMBNAIL_URLS: Dict[str, str] = {}
_VIDEO_THUMBNAIL_ATTEMPTED: set[str] = set()
_VIDEO_THUMBNAIL_FFMPEG: Optional[Path] = None
_VIDEO_THUMBNAIL_FFMPEG_RESOLVED = False
PICKER_DEFAULT_WORKSPACE_UUID = "00000000-0000-4000-8000-000000000001"
VIDEO_REFERENCE_CAPABILITY_SCHEMA = "hmb-video-reference-capabilities"
VIDEO_REFERENCE_CAPABILITY_VERSION = 1
VIDEO_FRAME_DOMAIN_SCHEMA = "hmb-video-frame-domain"
VIDEO_FRAME_DOMAIN_VERSION = 1
VIDEO_TIMING_CUE_SCHEMA = "hmb-video-emitter-timing-cue"
VIDEO_TIMING_CUE_VERSION = 1
MAX_VIDEO_TIMING_CUES = 256
ORIGINAL_DEPENDENCY_MANIFEST_SCHEMA = "hmb-maya-scene-dependencies-v1"
ORIGINAL_DEPENDENCY_MANIFEST_VERSION = 1
PLAYBLAST_RESOLUTIONS = (
    (OUTPUT_WIDTH, OUTPUT_HEIGHT),
    (1920, 1080),
)
PICKER_START_WIDTH = 1400
# Expanded mode keeps the established production canvas, but the native cold
# mount is the compact Loader.  Advertising the expanded 1200px shell before
# the compact body is measured leaves the host's trailing allocation visible as
# a black panel and can re-fit the workspace during workflow hydration.
PICKER_START_HEIGHT = 1200
PICKER_NATIVE_SIZE_VERSION = 7
PICKER_EXPANDED_SIZE_METADATA_KEY = "hmb_picker_expanded_size"
PICKER_WIDGET_MIN_WIDTH = 760
# The compact outer node minimum covers Griptape's title/Flow chrome plus the
# populated one-Shot Loader row. JavaScript grows the exact node beyond this
# floor for every additional Shot; it never caps the list with an inner scroll.
PICKER_COMPACT_NATIVE_HEIGHT = 360
PICKER_COMPACT_NATIVE_MIN_HEIGHT = PICKER_COMPACT_NATIVE_HEIGHT
# Keep the established expanded resize floor separate from the compact native
# bootstrap. Existing workflows may legitimately contain a manually resized
# 1151px expanded node; v6 stores that geometry independently.
PICKER_WIDGET_MIN_HEIGHT = 1151
# Compact Loader rows reserve the full, populated one-Shot card height even
# before media arrives. Additional Shots grow the widget deterministically in
# the browser (180px row + 6px gap each) instead of switching between an empty
# and populated height or introducing an internal scroll cap.
PICKER_WIDGET_COMPACT_MOUNT_HEIGHT = 252
# This is the authored parameter-row height, not the React Flow outer height.
PICKER_WIDGET_START_HEIGHT = PICKER_WIDGET_COMPACT_MOUNT_HEIGHT
READ_OVERALL_TIMEOUT_SECONDS = 900
READ_STALL_TIMEOUT_SECONDS = 180
PLAYBLAST_OVERALL_TIMEOUT_SECONDS = 7200
PLAYBLAST_STALL_TIMEOUT_SECONDS = 600
PROCESS_OUTPUT_ACTIVITY_SCAN_INTERVAL_SECONDS = 30.0
PROCESS_OUTPUT_ACTIVITY_QUIET_FRACTION = 0.5
DEPENDENCY_SCAN_DEFAULT_MAX_FILES = 50000
DEPENDENCY_SCAN_DEFAULT_SECONDS = 5.0
READ_STDOUT_QUEUE_MAX_LINES = 4096
_ORIGINAL_PUBLISH_LOCK_GUARD = threading.Lock()
_ORIGINAL_PUBLISH_LOCKS: Dict[str, threading.Lock] = {}
_PLAYBLAST_PUBLISH_LOCK_GUARD = threading.Lock()
_PLAYBLAST_PUBLISH_LOCKS: Dict[str, threading.Lock] = {}


@contextmanager
def _original_publish_guard(scene_path: Path):
    """Serialize the final Original video/sidecar pair across nodes/processes."""
    key = _scene_path_key(scene_path)
    with _ORIGINAL_PUBLISH_LOCK_GUARD:
        thread_lock = _ORIGINAL_PUBLISH_LOCKS.setdefault(key, threading.Lock())
    if not thread_lock.acquire(timeout=60.0):
        raise TimeoutError(
            "Another Picker node is publishing Original Playblast for this scene."
        )

    handle = None
    platform_lock = None
    output_folder = _ensure_scene_output_folder(scene_path)
    lock_path = (
        output_folder
        / ".hmb_video_picker"
        / f"{_safe_scene_name(scene_path.stem)}.original.publish.lock"
    )
    try:
        _ensure_private_job_folder(lock_path.parent, output_folder)
        handle = lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + 60.0
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    platform_lock = ("nt", msvcrt)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Another Griptape process is publishing Original "
                            "Playblast for this scene."
                        )
                    time.sleep(0.05)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    platform_lock = ("posix", fcntl)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Another Griptape process is publishing Original "
                            "Playblast for this scene."
                        )
                    time.sleep(0.05)
        yield
    finally:
        if handle is not None and platform_lock is not None:
            try:
                if platform_lock[0] == "nt":
                    handle.seek(0)
                    platform_lock[1].locking(handle.fileno(), platform_lock[1].LK_UNLCK, 1)
                else:
                    platform_lock[1].flock(handle.fileno(), platform_lock[1].LOCK_UN)
            except Exception:
                pass
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        # Keep the inode in place. Removing a platform-lock file after unlock
        # permits a waiter to retain the old inode while a third publisher
        # creates and locks a new inode at the same path.
        thread_lock.release()


@contextmanager
def _playblast_publish_guard(scene_path: Path):
    """Serialize final Color/Depth publication across Picker nodes/processes."""
    key = _scene_path_key(scene_path)
    with _PLAYBLAST_PUBLISH_LOCK_GUARD:
        thread_lock = _PLAYBLAST_PUBLISH_LOCKS.setdefault(key, threading.Lock())
    if not thread_lock.acquire(timeout=60.0):
        raise TimeoutError(
            "Another Picker node is publishing a playblast bundle for this scene."
        )

    handle = None
    platform_lock = None
    output_folder = _ensure_scene_output_folder(scene_path)
    lock_path = (
        output_folder
        / ".hmb_video_picker"
        / f"{_safe_scene_name(scene_path.stem)}.playblast.publish.lock"
    )
    try:
        _ensure_private_job_folder(lock_path.parent, output_folder)
        handle = lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + 60.0
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    platform_lock = ("nt", msvcrt)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Another Griptape process is publishing a playblast "
                            "bundle for this scene."
                        )
                    time.sleep(0.05)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    platform_lock = ("posix", fcntl)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Another Griptape process is publishing a playblast "
                            "bundle for this scene."
                        )
                    time.sleep(0.05)
        yield
    finally:
        if handle is not None and platform_lock is not None:
            try:
                if platform_lock[0] == "nt":
                    handle.seek(0)
                    platform_lock[1].locking(
                        handle.fileno(),
                        platform_lock[1].LK_UNLCK,
                        1,
                    )
                else:
                    platform_lock[1].flock(
                        handle.fileno(),
                        platform_lock[1].LOCK_UN,
                    )
            except Exception:
                pass
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        # The stable lock inode is intentionally persistent; see the Original
        # guard above. It is a zero-byte coordination artifact, not a job file.
        thread_lock.release()


def _playblast_resolution(value: Any) -> tuple[int, int]:
    source = value if isinstance(value, dict) else {}
    try:
        selected = (
            int(float(source.get("output_width") or OUTPUT_WIDTH)),
            int(float(source.get("output_height") or OUTPUT_HEIGHT)),
        )
    except Exception:
        selected = (OUTPUT_WIDTH, OUTPUT_HEIGHT)
    if selected not in PLAYBLAST_RESOLUTIONS:
        return OUTPUT_WIDTH, OUTPUT_HEIGHT
    return selected


def _validate_full_smooth_confirmation(
    result: Dict[str, Any],
    sidecar: Optional[Dict[str, Any]] = None,
    *,
    label: str,
) -> Dict[str, Any]:
    sidecar_payload = sidecar if isinstance(sidecar, dict) else {}
    profile = _clean(
        result.get("viewport_quality_profile")
        or sidecar_payload.get("viewport_quality_profile")
    )
    report_value = (
        result.get("viewport_quality_report")
        if isinstance(result.get("viewport_quality_report"), dict)
        else sidecar_payload.get("viewport_quality_report")
    )
    report = dict(report_value) if isinstance(report_value, dict) else {}
    errors: List[str] = []
    if profile != FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE:
        errors.append("quality profile")
    if _clean(report.get("profile")) != FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE:
        errors.append("quality report profile")
    if int(report.get("smooth_mesh_preview_mode") or 0) != 3:
        errors.append("Smooth Preview 3 mode")
    if int(report.get("smooth_mesh_shape_count") or 0) <= 0:
        errors.append("smoothed polygon mesh count")
    if int(report.get("remaining_bounding_box_count") or 0) != 0:
        errors.append("remaining Bounding Box")
    if list(report.get("unsupported_proxy_shapes") or []):
        errors.append("proxy/cache/stand-in geometry")
    if list(report.get("technical_dummy_shapes") or []):
        errors.append("dummy/check geometry")
    # Smooth Preview and proxy-detail confirmation improve image quality, but
    # they must never decide whether the tool may publish otherwise valid
    # media.  Keep the diagnostics in metadata and continue with the scene's
    # authored-visible representation.
    report["best_effort_issues"] = list(errors)
    report["best_effort_complete"] = not bool(errors)
    if errors:
        report["best_effort_warning"] = (
            f"{label} used the authored-visible viewport representation because "
            f"these optional quality checks were unavailable: {', '.join(errors)}."
        )
    return report


def _validate_world_pattern_runner_confirmation(
    result: Dict[str, Any],
    sidecar: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fail closed unless Maya confirms root-projected, UV-free patterns."""
    sidecar_payload = sidecar if isinstance(sidecar, dict) else {}
    profile = _clean(
        result.get("world_pattern_profile")
        or sidecar_payload.get("world_pattern_profile")
    )
    report_value = (
        result.get("world_pattern_report")
        if isinstance(result.get("world_pattern_report"), dict)
        else sidecar_payload.get("world_pattern_report")
    )
    report = dict(report_value) if isinstance(report_value, dict) else {}
    options_value = (
        result.get("world_pattern_render_options")
        if isinstance(result.get("world_pattern_render_options"), dict)
        else sidecar_payload.get("world_pattern_render_options")
    )
    options = dict(options_value) if isinstance(options_value, dict) else {}
    errors: List[str] = []
    if profile != MAYA_WORLD_PATTERN_PROFILE:
        errors.append("profile")
    if _clean(report.get("profile")) != MAYA_WORLD_PATTERN_PROFILE:
        errors.append("report profile")
    if _clean(report.get("coordinate_space")) != "background_root":
        errors.append("background-root coordinate space")
    if report.get("camera_anchored") is not False:
        errors.append("camera independence")
    if report.get("uv_dependent") is not False:
        errors.append("UV independence")
    if report.get("root_scale_followed") is not True:
        errors.append("background-root scale follow")
    if report.get("world_cell_scale_compensated") is not True:
        errors.append("world-cell scale compensation")
    if not math.isclose(
        float(report.get("base_cell_world_units") or 0.0),
        WORLD_PATTERN_BASE_CELL_WORLD_UNITS,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        errors.append("15-unit base cell")
    if not math.isclose(
        float(report.get("density_multiplier") or 0.0),
        WORLD_PATTERN_DENSITY_MULTIPLIER,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        errors.append("3x density")
    if not math.isclose(
        float(report.get("cell_size_world_units") or 0.0),
        WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        errors.append("5-unit effective cell")
    try:
        reference_frame = float(report.get("reference_frame"))
    except (TypeError, ValueError):
        reference_frame = float("nan")
    if not math.isfinite(reference_frame):
        errors.append("reference frame")
    pattern_rows = report.get("patterns")
    if not isinstance(pattern_rows, list):
        pattern_rows = []
        errors.append("pattern rows")
    for row in pattern_rows:
        if not isinstance(row, dict):
            errors.append("pattern row schema")
            continue
        pattern = _clean(row.get("pattern"))
        expected = MAYA_WORLD_PATTERN_PROJECTIONS.get(pattern)
        actual = (
            _clean(row.get("projection_type")),
            _clean(row.get("projection_axis")),
        )
        if expected is None or actual != expected:
            errors.append(f"{pattern or '<blank>'} projection mapping")
        if row.get("camera_anchored") is not False:
            errors.append(f"{pattern or '<blank>'} camera independence")
        if row.get("uv_dependent") is not False:
            errors.append(f"{pattern or '<blank>'} UV independence")
        if row.get("root_scale_followed") is not True:
            errors.append(f"{pattern or '<blank>'} root scale follow")
        if row.get("world_cell_scale_compensated") is not True:
            errors.append(f"{pattern or '<blank>'} scale compensation")
        try:
            row_reference_frame = float(row.get("reference_frame"))
        except (TypeError, ValueError):
            row_reference_frame = float("nan")
        if not math.isclose(
            row_reference_frame,
            reference_frame,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            errors.append(f"{pattern or '<blank>'} reference frame")
        for node_field in (
            "projection_node",
            "projector_node",
            "anchor_node",
            "constraint_node",
            "scale_constraint_node",
            "scale_compensator_node",
        ):
            if not _clean(row.get(node_field)):
                errors.append(f"{pattern or '<blank>'} {node_field}")
    pattern_count = len(pattern_rows)
    if int(report.get("pattern_binding_count") or 0) != pattern_count:
        errors.append("pattern binding count")
    if int(report.get("projection_node_count") or 0) != pattern_count:
        errors.append("projection node count")
    if int(report.get("projector_node_count") or 0) != pattern_count:
        errors.append("projector node count")
    for field in (
        "output_transform_disabled",
        "multisample_disabled",
        "line_aa_disabled",
        "ssao_disabled",
        "motion_blur_disabled",
    ):
        if options.get(field) is not True:
            errors.append(field)
    if errors:
        raise RuntimeError(
            "Maya did not confirm the production world-pattern contract "
            f"({', '.join(dict.fromkeys(errors))})."
        )
    return report


def _load_marker_catalog() -> Dict[str, Any]:
    with MARKER_CATALOG_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema") != "hmb-marker-catalog":
        raise RuntimeError(f"Invalid HMB marker catalog: {MARKER_CATALOG_PATH}")
    actor = [dict(item) for item in payload.get("character", []) if isinstance(item, dict)]
    object_items = [dict(item) for item in payload.get("background", []) if isinstance(item, dict)]
    names = [_clean_catalog_name(item.get("name")) for item in actor + object_items]
    if len(actor) != 7 or len(object_items) != 7 or len(names) != len(set(names)) or any(not name for name in names):
        raise RuntimeError("HMB marker catalog must contain seven unique Actor choices and seven unique Object choices.")
    pattern_ids = []
    for item in object_items:
        if _clean_catalog_name(item.get("kind")).lower() != "pattern":
            continue
        raw_id = item.get("screen_space_id_rgb")
        if (
            not isinstance(raw_id, list)
            or len(raw_id) != 3
            or any(
                isinstance(channel, bool)
                or not isinstance(channel, (int, float))
                or int(channel) != channel
                or not 0 <= int(channel) <= 255
                for channel in raw_id
            )
        ):
            raise RuntimeError(
                "Every HMB pattern marker requires a three-channel "
                "screen_space_id_rgb value."
            )
        pattern_ids.append(tuple(int(channel) for channel in raw_id))
    if len(pattern_ids) != 4 or len(set(pattern_ids)) != 4:
        raise RuntimeError(
            "The four HMB pattern markers require four unique screen-space IDs."
        )
    return {
        "schema": "hmb-marker-catalog",
        "version": int(payload.get("version") or 1),
        "character": actor,
        "background": object_items,
        "options": names,
    }


def _clean_catalog_name(value: Any) -> str:
    return str(value or "").strip()


MARKER_CATALOG = _load_marker_catalog()
MARKER_ORDER = list(MARKER_CATALOG["options"])
ACTOR_MARKERS = frozenset(
    _clean_catalog_name(item.get("name"))
    for item in MARKER_CATALOG["character"]
)
BACKGROUND_MARKERS = frozenset(
    _clean_catalog_name(item.get("name"))
    for item in MARKER_CATALOG["background"]
)
# Multiple Maya roots may form one logical background mask. Actor colors remain
# unique because each actor color is one appearance-authority address.
REPEATABLE_MARKERS = BACKGROUND_MARKERS


def _screen_space_preflight(bindings: Sequence[Dict[str, Any]]) -> tuple[str, ...]:
    active = _screen_space.active_patterns_from_bindings(
        bindings,
        MARKER_CATALOG,
    )
    if active:
        _screen_space.preflight_pillow()
    return active


def _world_pattern_preflight(
    bindings: Sequence[Dict[str, Any]],
) -> tuple[str, ...]:
    active = _screen_space.active_patterns_from_bindings(
        bindings,
        MARKER_CATALOG,
    )
    unsupported = sorted(set(active).difference(MAYA_WORLD_PATTERN_PROJECTIONS))
    if unsupported:
        raise RuntimeError(
            "Unsupported Maya world pattern(s): " + ", ".join(unsupported)
        )
    return active


def _postprocess_screen_space_frames(
    frame_paths: Sequence[Path],
    *,
    bindings: Sequence[Dict[str, Any]],
    width: int,
    height: int,
) -> Dict[str, Any]:
    report = _screen_space.postprocess_marker_frames(
        frame_paths,
        catalog=MARKER_CATALOG,
        bindings=bindings,
        expected_size=(int(width), int(height)),
    )
    if _clean(report.get("profile")) != SCREEN_SPACE_PATTERN_PROFILE:
        raise RuntimeError(
            "Screen-space compositor returned an unsupported profile."
        )
    if (
        int(report.get("pattern_linear_scale_divisor") or 0)
        != SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR
    ):
        raise RuntimeError(
            "Screen-space compositor returned an unsupported pattern scale."
        )
    if bool(report.get("uv_dependent")):
        raise RuntimeError(
            "Screen-space compositor unexpectedly reported UV dependence."
        )
    if _clean(report.get("phase")) != "frame_top_left":
        raise RuntimeError(
            "Screen-space compositor did not preserve the fixed frame origin."
        )
    return report


def _validate_depth_companion_inputs(
    *,
    result: Dict[str, Any],
    color_sidecar: Dict[str, Any],
    depth_sidecar: Dict[str, Any],
    color_frame_paths: Sequence[Path],
    depth_frame_paths: Sequence[Path],
    expected_frame_count: int,
    expected_fps: float,
    expected_start_frame: float,
    expected_end_frame: float,
    expected_width: int,
    expected_height: int,
) -> Dict[str, Any]:
    """Validate paired Maya shader Depth and diagnose its visible tone detail.

    Raster-content heuristics are deliberately non-blocking. A valid generic
    camera-space Depth pass can be entirely black, contain a very small object,
    or show one fronto-parallel surface at a constant depth. Those cases cannot
    be distinguished safely from an empty or mask-like raster using pixels
    alone. Schema, shader semantics, timing, dimensions, and grayscale remain
    fail-closed; tonal-detail measurements are reported for diagnostics.
    """

    def required_number(value: Any, label: str) -> float:
        try:
            number = float(value)
        except Exception as exc:
            raise RuntimeError(f"Depth companion {label} is not numeric.") from exc
        if number != number or abs(number) == float("inf"):
            raise RuntimeError(f"Depth companion {label} is not finite.")
        return number

    def required_nonnegative_integer(value: Any, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError(
                f"Depth companion {label} must be an integer."
            )
        if value < 0:
            raise RuntimeError(
                f"Depth companion {label} must not be negative."
            )
        return value

    def required_path_list(value: Any, label: str) -> List[str]:
        if not isinstance(value, list):
            raise RuntimeError(f"Depth companion {label} must be a list.")
        if any(not isinstance(item, str) for item in value):
            raise RuntimeError(
                f"Depth companion {label} must contain string DAG paths."
            )
        paths = [_clean(item) for item in value]
        if any(not path for path in paths):
            raise RuntimeError(
                f"Depth companion {label} contains an empty DAG path."
            )
        if len(set(paths)) != len(paths):
            raise RuntimeError(
                f"Depth companion {label} contains duplicate DAG paths."
            )
        return paths

    def assert_close(value: Any, expected: float, label: str) -> None:
        number = required_number(value, label)
        if abs(number - float(expected)) > 1e-6:
            raise RuntimeError(
                f"Depth companion {label} does not match Color "
                f"({number!r} != {float(expected)!r})."
            )

    def assert_uniform_color(value: Any, expected: float, label: str) -> None:
        channels = (
            list(value)
            if isinstance(value, (list, tuple))
            else [value]
        )
        if len(channels) not in {1, 3}:
            raise RuntimeError(f"Depth companion {label} has an invalid shape.")
        for channel in channels:
            assert_close(channel, expected, label)

    def frame_signature(
        payload: Dict[str, Any],
        label: str,
    ) -> List[tuple[int, float]]:
        raw_map = payload.get("frame_map")
        if not isinstance(raw_map, list) or len(raw_map) != expected_frame_count:
            raise RuntimeError(
                f"{label} frame_map must contain exactly "
                f"{expected_frame_count} entries."
            )
        signature: List[tuple[int, float]] = []
        for expected_index, raw in enumerate(raw_map):
            if not isinstance(raw, dict):
                raise RuntimeError(
                    f"{label} frame_map entry {expected_index} is invalid."
                )
            try:
                sequence_index = int(raw.get("sequence_index"))
            except Exception as exc:
                raise RuntimeError(
                    f"{label} frame_map entry {expected_index} has no valid "
                    "sequence_index."
                ) from exc
            if sequence_index != expected_index:
                raise RuntimeError(
                    f"{label} frame_map sequence is not contiguous at "
                    f"{expected_index}."
                )
            signature.append(
                (
                    sequence_index,
                    required_number(
                        raw.get("maya_frame"),
                        f"{label} frame_map[{expected_index}].maya_frame",
                    ),
                )
            )
        if signature:
            if abs(signature[0][1] - expected_start_frame) > 1e-6:
                raise RuntimeError(f"{label} frame_map start frame does not match Color.")
            if abs(signature[-1][1] - expected_end_frame) > 1e-6:
                raise RuntimeError(f"{label} frame_map end frame does not match Color.")
        return signature

    if _clean(depth_sidecar.get("schema")) != "hmb-maya-depth-playblast":
        raise RuntimeError("Depth runner sidecar schema is unsupported.")
    if int(depth_sidecar.get("schema_version") or 0) != 1:
        raise RuntimeError("Depth runner sidecar schema version is unsupported.")
    if _clean(depth_sidecar.get("profile")) != DEPTH_PLAYBLAST_PROFILE:
        raise RuntimeError("Depth runner sidecar profile is unsupported.")
    if _clean(result.get("depth_profile")) != DEPTH_PLAYBLAST_PROFILE:
        raise RuntimeError("Depth runner result profile is unsupported.")
    if int(result.get("depth_frame_count") or 0) != expected_frame_count:
        raise RuntimeError("Depth runner result frame count does not match Color.")

    for label, payload in (
        ("Color", color_sidecar),
        ("Depth", depth_sidecar),
    ):
        if int(payload.get("frame_count") or 0) != expected_frame_count:
            raise RuntimeError(f"{label} frame count does not match the paired run.")
        assert_close(payload.get("fps"), expected_fps, f"{label} FPS")
        assert_close(
            payload.get("start_frame"),
            expected_start_frame,
            f"{label} start frame",
        )
        assert_close(
            payload.get("end_frame"),
            expected_end_frame,
            f"{label} end frame",
        )
        resolution = (
            payload.get("resolution")
            if isinstance(payload.get("resolution"), dict)
            else {}
        )
        if (
            int(resolution.get("width") or 0) != int(expected_width)
            or int(resolution.get("height") or 0) != int(expected_height)
        ):
            raise RuntimeError(
                f"{label} sidecar resolution does not match "
                f"{expected_width}x{expected_height}."
            )

    color_camera = _clean(color_sidecar.get("camera"))
    depth_camera = _clean(depth_sidecar.get("camera"))
    if not color_camera or depth_camera != color_camera:
        raise RuntimeError("Depth camera does not exactly match the Color camera.")

    color_signature = frame_signature(color_sidecar, "Color")
    depth_signature = frame_signature(depth_sidecar, "Depth")
    if depth_signature != color_signature:
        raise RuntimeError("Depth frame_map does not exactly match Color.")
    result_depth_map = result.get("depth_frame_map")
    if not isinstance(result_depth_map, list):
        raise RuntimeError("Depth runner result did not return a frame_map.")
    result_signature = frame_signature(
        {"frame_map": result_depth_map},
        "Depth result",
    )
    if result_signature != depth_signature:
        raise RuntimeError("Depth result frame_map does not match its sidecar.")

    range_report = depth_sidecar.get("depth_range_report")
    result_range_report = result.get("depth_range_report")
    if not isinstance(range_report, dict) or not isinstance(result_range_report, dict):
        raise RuntimeError("Depth range report is missing.")
    if range_report != result_range_report:
        raise RuntimeError("Depth range report differs between result and sidecar.")
    required_semantics = {
        "profile": DEPTH_PLAYBLAST_PROFILE,
        "space": "camera",
        "source": "object_bbox_camera_depth",
        "assignment_mode": "color_picker_style_shared_gray_material_buckets",
        "depth_update_scope": "per_shape_path_per_output_frame",
        "representative_depth": (
            "median_positive_camera_depth_of_world_bbox_corners"
        ),
        "shader_model": "surfaceShader",
        "direction": "near_white_far_black",
        "background": "pure_black",
        "temporal_normalization": "fixed_for_complete_sequence",
        "encoding_curve": "normalized_power",
    }
    for field, expected in required_semantics.items():
        if _clean(range_report.get(field)) != expected:
            raise RuntimeError(
                f"Depth range report has unsupported {field}: "
                f"{range_report.get(field)!r}."
            )
    if _clean(range_report.get("range_evaluation_scope")) != (
        "complete_requested_sequence"
    ):
        raise RuntimeError(
            "Depth range was not evaluated across the complete requested sequence."
        )
    try:
        range_frame_count = int(range_report.get("range_evaluated_frame_count"))
    except Exception as exc:
        raise RuntimeError("Depth range evaluated frame count is invalid.") from exc
    if range_frame_count != expected_frame_count:
        raise RuntimeError(
            "Depth range evaluated frame count does not match the paired sequence."
        )
    shot_range_sample = range_report.get("shot_range_sample")
    if not isinstance(shot_range_sample, dict):
        raise RuntimeError("Depth complete-sequence range evidence is missing.")
    if _clean(shot_range_sample.get("evaluation_scope")) != (
        "complete_requested_sequence"
    ):
        raise RuntimeError("Depth range evidence is not complete-sequence evidence.")
    try:
        sampled_frame_count = int(shot_range_sample.get("evaluated_frame_count"))
    except Exception as exc:
        raise RuntimeError("Depth range evidence frame count is invalid.") from exc
    if sampled_frame_count != expected_frame_count:
        raise RuntimeError(
            "Depth range evidence frame count does not match the paired sequence."
        )
    evaluated_frames = shot_range_sample.get("evaluated_frames")
    if not isinstance(evaluated_frames, list) or len(evaluated_frames) != (
        expected_frame_count
    ):
        raise RuntimeError("Depth range evidence frame list is incomplete.")
    expected_maya_frames = [item[1] for item in depth_signature]
    actual_maya_frames = [
        required_number(value, f"range evaluated frame {index}")
        for index, value in enumerate(evaluated_frames)
    ]
    if any(
        abs(actual - expected) > 1e-6
        for actual, expected in zip(actual_maya_frames, expected_maya_frames)
    ):
        raise RuntimeError("Depth range evidence does not match the Depth frame_map.")
    normalization_policy = _clean(range_report.get("normalization_policy"))
    if normalization_policy not in {
        "screen_valid_foreground_percentile_bounds",
        "screen_valid_shape_robust_fallback_bounds",
        "screen_valid_shape_extrema_fallback_bounds",
        "camera_clip_planes_fallback",
        "fixed_shot_range_clamped_to_camera",
    }:
        raise RuntimeError("Depth range report has no fixed shot normalization policy.")
    assert_close(
        range_report.get("camera_origin_distance"),
        0.0,
        "camera origin distance",
    )
    if range_report.get("camera_clip_is_hard_safety_boundary") is not True:
        raise RuntimeError("Depth camera clip safety boundary evidence is missing.")
    foreground_samples = required_nonnegative_integer(
        shot_range_sample.get("foreground_representative_sample_count"),
        "foreground representative sample count",
    )
    context_samples = required_nonnegative_integer(
        shot_range_sample.get("context_representative_sample_count"),
        "context representative sample count",
    )
    representative_samples = required_nonnegative_integer(
        shot_range_sample.get("representative_sample_count"),
        "representative sample count",
    )
    screen_rejected_samples = required_nonnegative_integer(
        shot_range_sample.get("screen_rejected_representative_sample_count"),
        "screen-rejected representative sample count",
    )
    role_excluded_samples = required_nonnegative_integer(
        shot_range_sample.get("role_excluded_representative_sample_count"),
        "role-excluded representative sample count",
    )
    if (
        foreground_samples
        + context_samples
        + screen_rejected_samples
        + role_excluded_samples
        != representative_samples
    ):
        raise RuntimeError(
            "Depth disjoint foreground/context/rejection sample evidence is "
            "inconsistent."
        )
    if _clean(shot_range_sample.get("rejection_accounting_policy")) != (
        DEPTH_REJECTION_ACCOUNTING_POLICY
    ):
        raise RuntimeError("Depth rejection accounting policy is unsupported.")
    candidate_shape_count = required_nonnegative_integer(
        shot_range_sample.get("normalization_candidate_shape_path_count"),
        "normalization candidate shape-path count",
    )
    screen_tested_count = required_nonnegative_integer(
        shot_range_sample.get("screen_sample_tested_bbox_count"),
        "screen-sample tested bbox count",
    )
    screen_visible_count = required_nonnegative_integer(
        shot_range_sample.get("screen_sample_visible_bbox_count"),
        "screen-sample visible bbox count",
    )
    screen_rejected_count = required_nonnegative_integer(
        shot_range_sample.get("screen_sample_rejected_bbox_count"),
        "screen-sample rejected bbox count",
    )
    bbox_fallback_count = required_nonnegative_integer(
        shot_range_sample.get("bbox_fallback_candidate_count"),
        "bbox fallback candidate count",
    )
    if screen_tested_count != screen_visible_count + screen_rejected_count:
        raise RuntimeError("Depth screen-sample bbox evidence is inconsistent.")
    if screen_rejected_samples != screen_rejected_count:
        raise RuntimeError("Depth screen-rejected sample evidence is inconsistent.")
    if foreground_samples + context_samples != (
        screen_visible_count + bbox_fallback_count
    ):
        raise RuntimeError("Depth normalization candidate evidence is inconsistent.")
    if candidate_shape_count > foreground_samples + context_samples:
        raise RuntimeError("Depth normalization candidate shape count is invalid.")
    assert_close(
        shot_range_sample.get("foreground_near_percentile"),
        DEPTH_FOREGROUND_NEAR_PERCENTILE,
        "foreground near percentile",
    )
    assert_close(
        shot_range_sample.get("foreground_far_percentile"),
        DEPTH_FOREGROUND_FAR_PERCENTILE,
        "foreground far percentile",
    )
    assert_close(
        shot_range_sample.get("generic_far_percentile"),
        DEPTH_GENERIC_FAR_PERCENTILE,
        "generic far percentile",
    )
    generic_min_shapes = required_nonnegative_integer(
        shot_range_sample.get("generic_percentile_min_shapes"),
        "generic percentile minimum shape count",
    )
    if generic_min_shapes != DEPTH_GENERIC_PERCENTILE_MIN_SHAPES:
        raise RuntimeError("Depth generic percentile threshold is unsupported.")
    if _clean(shot_range_sample.get("screen_sample_policy")) != (
        "deterministic_api_mesh_vertices_and_polygon_centers;"
        "bbox_fallback_when_sampling_unavailable"
    ):
        raise RuntimeError("Depth screen-sample policy evidence is missing.")
    if required_nonnegative_integer(
        shot_range_sample.get("screen_vertex_sample_limit"),
        "screen vertex sample limit",
    ) != DEPTH_SCREEN_VERTEX_SAMPLE_LIMIT:
        raise RuntimeError("Depth screen vertex sample limit is unsupported.")
    if required_nonnegative_integer(
        shot_range_sample.get("screen_polygon_center_sample_limit"),
        "screen polygon-center sample limit",
    ) != DEPTH_SCREEN_POLYGON_CENTER_SAMPLE_LIMIT:
        raise RuntimeError("Depth screen polygon-center sample limit is unsupported.")
    range_candidate_scope = _clean(
        shot_range_sample.get("range_candidate_scope")
    )
    range_basis = _clean(shot_range_sample.get("range_basis"))
    near_anchor = _clean(shot_range_sample.get("near_anchor"))
    extrema_sources = shot_range_sample.get("range_extrema_sources")
    if not isinstance(extrema_sources, dict):
        raise RuntimeError("Depth effective range extrema evidence is missing.")
    binding_range_reports = shot_range_sample.get("binding_range_reports")
    if not isinstance(binding_range_reports, list):
        raise RuntimeError("Depth binding range evidence is missing.")
    if representative_samples and not binding_range_reports:
        raise RuntimeError("Depth binding range evidence must not be empty.")

    binding_representative_total = 0
    binding_candidate_total = 0
    binding_screen_rejected_total = 0
    binding_role_excluded_total = 0
    selected_bindings = []
    for binding_index, binding_report in enumerate(binding_range_reports):
        if not isinstance(binding_report, dict):
            raise RuntimeError("Depth binding range evidence entry is invalid.")
        role = _clean(binding_report.get("role"))
        if role not in {"foreground", "context"}:
            raise RuntimeError("Depth binding range evidence role is invalid.")
        representative_count = required_nonnegative_integer(
            binding_report.get("representative_sample_count"),
            f"binding range[{binding_index}] representative sample count",
        )
        candidate_count = required_nonnegative_integer(
            binding_report.get("normalization_candidate_sample_count"),
            f"binding range[{binding_index}] candidate sample count",
        )
        if candidate_count > representative_count:
            raise RuntimeError("Depth binding candidate count is invalid.")
        binding_representative_total += representative_count
        binding_candidate_total += candidate_count
        for field in (
            "screen_tested_shape_path_count",
            "screen_visible_shape_path_count",
            "screen_rejected_shape_path_count",
            "bbox_fallback_shape_path_count",
            "role_excluded_shape_path_count",
            "screen_sample_count",
            "screen_visible_sample_count",
        ):
            required_nonnegative_integer(
                binding_report.get(field),
                f"binding range[{binding_index}] {field}",
            )
        policy_counts = binding_report.get("screen_sample_policy_counts")
        if not isinstance(policy_counts, dict) or any(
            not _clean(key)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for key, value in policy_counts.items()
        ):
            raise RuntimeError("Depth binding screen policy evidence is invalid.")
        if sum(policy_counts.values()) != representative_count:
            raise RuntimeError("Depth binding screen policy counts are inconsistent.")
        rejected_policy_count = int(policy_counts.get(
            "api_mesh_vertex_polygon_center_screen_rejected",
            0,
        ))
        role_excluded_policy_count = int(policy_counts.get(
            "context_not_sampled_foreground_priority",
            0,
        ))
        candidate_policy_count = (
            representative_count
            - rejected_policy_count
            - role_excluded_policy_count
        )
        if candidate_policy_count != candidate_count:
            raise RuntimeError(
                "Depth binding normalization outcome accounting is inconsistent."
            )
        binding_screen_rejected_total += rejected_policy_count
        binding_role_excluded_total += role_excluded_policy_count
        if binding_report.get("selected_for_normalization") is True:
            if not candidate_count:
                raise RuntimeError("Depth selected binding has no candidates.")
            selected_bindings.append(binding_report)
        elif binding_report.get("selected_for_normalization") is not False:
            raise RuntimeError("Depth binding selection evidence is invalid.")
    if binding_representative_total != representative_samples:
        raise RuntimeError("Depth binding representative evidence is inconsistent.")
    if binding_candidate_total != foreground_samples + context_samples:
        raise RuntimeError("Depth binding candidate evidence is inconsistent.")
    if binding_screen_rejected_total != screen_rejected_samples:
        raise RuntimeError("Depth binding screen-rejected evidence is inconsistent.")
    if binding_role_excluded_total != role_excluded_samples:
        raise RuntimeError("Depth binding role-excluded evidence is inconsistent.")

    policy_contracts = {
        "screen_valid_foreground_percentile_bounds": (
            "screen_valid_foreground_actor_shapes",
            "complete_sequence_screen_valid_foreground_representative_percentiles",
            "effective_screen_valid_foreground_near",
        ),
        "screen_valid_shape_robust_fallback_bounds": (
            "screen_valid_shapes_generic_robust_fallback",
            "complete_sequence_screen_valid_shape_temporal_extrema_percentiles",
            "effective_screen_valid_shape_near",
        ),
        "screen_valid_shape_extrema_fallback_bounds": (
            "screen_valid_shapes_small_scene_fallback",
            "complete_sequence_screen_valid_shape_representative_extrema_fallback",
            "effective_screen_valid_shape_near",
        ),
    }
    if normalization_policy in policy_contracts:
        expected_scope, expected_basis, expected_anchor = policy_contracts[
            normalization_policy
        ]
        if (
            range_candidate_scope != expected_scope
            or range_basis != expected_basis
            or near_anchor != expected_anchor
        ):
            raise RuntimeError("Depth normalization policy evidence is inconsistent.")
        if set(extrema_sources) != {"near", "far"}:
            raise RuntimeError("Depth range extrema evidence must contain near and far.")
        for label in ("near", "far"):
            source = extrema_sources[label]
            if not isinstance(source, dict) or not _clean(source.get("shape")):
                raise RuntimeError(f"Depth {label} extrema source is invalid.")
            if _clean(source.get("role")) not in {"foreground", "context"}:
                raise RuntimeError(f"Depth {label} extrema role is invalid.")
            required_number(
                source.get("representative_depth"),
                f"{label} extrema representative depth",
            )
            if not _clean(source.get("screen_sample_policy")):
                raise RuntimeError(f"Depth {label} screen evidence is missing.")
            if not isinstance(source.get("used_bbox_fallback"), bool):
                raise RuntimeError(f"Depth {label} bbox fallback evidence is invalid.")
            required_nonnegative_integer(
                source.get("screen_inside_sample_count"),
                f"{label} screen-inside sample count",
            )
        if not selected_bindings:
            raise RuntimeError("Depth normalization has no selected binding evidence.")
    if normalization_policy == "screen_valid_foreground_percentile_bounds":
        if not foreground_samples or context_samples or any(
            _clean(item.get("role")) != "foreground"
            for item in selected_bindings
        ):
            raise RuntimeError("Depth foreground normalization evidence is invalid.")
        if shot_range_sample.get("fallback_percentile") is not None:
            raise RuntimeError("Depth foreground policy must not claim a fallback percentile.")
    elif normalization_policy == "screen_valid_shape_robust_fallback_bounds":
        if foreground_samples or candidate_shape_count < generic_min_shapes:
            raise RuntimeError("Depth robust fallback evidence is invalid.")
        assert_close(
            shot_range_sample.get("fallback_percentile"),
            DEPTH_GENERIC_FAR_PERCENTILE,
            "generic fallback percentile",
        )
    elif normalization_policy == "screen_valid_shape_extrema_fallback_bounds":
        if foreground_samples or candidate_shape_count >= generic_min_shapes:
            raise RuntimeError("Depth small-scene fallback evidence is invalid.")
        if shot_range_sample.get("fallback_percentile") is not None:
            raise RuntimeError("Depth small-scene fallback percentile is invalid.")
    near_value = required_number(range_report.get("near"), "near distance")
    far_value = required_number(range_report.get("far"), "far distance")
    if near_value <= 0.0 or far_value <= near_value:
        raise RuntimeError("Depth near/far range is invalid.")
    camera_near = required_number(
        range_report.get("camera_near_clip"),
        "camera near clip",
    )
    camera_near_min = required_number(
        range_report.get("camera_near_clip_min"),
        "camera near clip minimum",
    )
    camera_far = required_number(
        range_report.get("camera_far_clip"),
        "camera far clip",
    )
    camera_near_max = required_number(
        range_report.get("camera_near_clip_max"),
        "camera near clip maximum",
    )
    camera_far_min = required_number(
        range_report.get("camera_far_clip_min"),
        "camera far clip minimum",
    )
    camera_far_max = required_number(
        range_report.get("camera_far_clip_max"),
        "camera far clip maximum",
    )
    if (
        camera_near <= 0.0
        or camera_far <= camera_near
        or abs(camera_near_min - camera_near) > 1e-6
        or camera_near_max < camera_near
        or camera_far_min <= camera_near
        or abs(camera_far_max - camera_far) > 1e-6
        or camera_far < camera_far_min
        or near_value < camera_near - 1e-6
        or far_value > camera_far + 1e-6
    ):
        raise RuntimeError("Depth range is outside the validated camera clip range.")
    assert_uniform_color(
        range_report.get("near_color"),
        DEPTH_NEAR_COLOR,
        "near color",
    )
    assert_uniform_color(
        range_report.get("far_color"),
        DEPTH_FAR_COLOR,
        "far color",
    )
    output_value_range = range_report.get("output_value_range")
    reserved_value_range = range_report.get("reserved_output_value_range")
    if (
        not isinstance(output_value_range, (list, tuple))
        or len(output_value_range) != 2
        or not isinstance(reserved_value_range, (list, tuple))
        or len(reserved_value_range) != 2
    ):
        raise RuntimeError("Depth safe output-range evidence is missing.")
    assert_close(
        output_value_range[0], DEPTH_FAR_COLOR, "output value minimum"
    )
    assert_close(
        output_value_range[1], DEPTH_NEAR_COLOR, "output value maximum"
    )
    assert_close(
        reserved_value_range[0],
        DEPTH_NEAR_COLOR,
        "reserved value minimum",
    )
    assert_close(reserved_value_range[1], 1.0, "reserved value maximum")
    assert_close(
        range_report.get("camera_near_safety_margin"),
        DEPTH_CAMERA_NEAR_SAFETY_MARGIN,
        "camera near safety margin",
    )
    assert_close(
        range_report.get("contrast_exponent"),
        DEPTH_CONTRAST_EXPONENT,
        "contrast exponent",
    )
    grayscale_bucket_count = required_nonnegative_integer(
        range_report.get("grayscale_bucket_count"),
        "grayscale bucket count",
    )
    if grayscale_bucket_count != 256:
        raise RuntimeError("Depth must provide exactly 256 grayscale buckets.")
    if list(range_report.get("standard_nodes") or []) != ["surfaceShader"]:
        raise RuntimeError(
            "Depth shader graph must use only the Color Picker surfaceShader path."
        )

    cutout_transparency = range_report.get("cutout_transparency")
    if not isinstance(cutout_transparency, dict):
        raise RuntimeError(
            "Depth authored cutout-transparency evidence is missing."
        )
    if _clean(cutout_transparency.get("policy")) != (
        "preserve_authored_material_out_transparency_v1"
    ):
        raise RuntimeError(
            "Depth authored cutout-transparency policy is unsupported."
        )
    cutout_counts = {
        field: required_nonnegative_integer(
            cutout_transparency.get(field),
            f"cutout transparency {field}",
        )
        for field in (
            "captured_shape_path_count",
            "alpha_driven_shape_path_count",
            "source_plug_count",
            "verified_shape_path_count",
            "ambiguous_shape_path_count",
            "unsupported_shape_path_count",
        )
    }
    if (
        cutout_counts["alpha_driven_shape_path_count"]
        > cutout_counts["captured_shape_path_count"]
        or cutout_counts["source_plug_count"]
        > cutout_counts["alpha_driven_shape_path_count"]
        or cutout_counts["verified_shape_path_count"]
        != cutout_counts["alpha_driven_shape_path_count"]
        or cutout_counts["ambiguous_shape_path_count"] != 0
        or cutout_counts["unsupported_shape_path_count"] != 0
    ):
        raise RuntimeError(
            "Depth authored cutout-transparency evidence is inconsistent."
        )

    proxy_recovery = range_report.get("proxy_preview_recovery")
    if not isinstance(proxy_recovery, dict):
        raise RuntimeError("Depth proxy preview recovery evidence is missing.")
    proxy_counts = {
        field: required_nonnegative_integer(
            proxy_recovery.get(field),
            f"proxy preview recovery {field}",
        )
        for field in (
            "candidate_shape_count",
            "candidate_path_count",
            "recovered_shape_count",
            "recovered_path_count",
        )
    }
    recovered_paths = required_path_list(
        proxy_recovery.get("recovered_paths"),
        "proxy preview recovery recovered_paths",
    )
    source_paths = required_path_list(
        proxy_recovery.get("source_paths"),
        "proxy preview recovery source_paths",
    )
    if (
        proxy_counts["candidate_shape_count"]
        != proxy_counts["recovered_shape_count"]
        or proxy_counts["candidate_path_count"]
        != proxy_counts["recovered_path_count"]
    ):
        raise RuntimeError("Depth proxy preview recovery is incomplete.")
    if (
        proxy_counts["candidate_path_count"]
        < proxy_counts["candidate_shape_count"]
        or len(recovered_paths) != proxy_counts["recovered_path_count"]
        or (
            proxy_counts["recovered_shape_count"] > 0
            and not source_paths
        )
        or (
            proxy_counts["recovered_shape_count"] == 0
            and source_paths
        )
    ):
        raise RuntimeError(
            "Depth proxy preview recovery evidence is inconsistent."
        )

    assignment_verification = range_report.get("assignment_verification")
    if not isinstance(assignment_verification, dict):
        raise RuntimeError(
            "Depth shader assignment verification evidence is missing."
        )
    assignment_counts = {
        field: required_nonnegative_integer(
            assignment_verification.get(field),
            f"shader assignment verification {field}",
        )
        for field in (
            "shape_path_count",
            "mesh_path_count",
            "nurbs_surface_path_count",
            "verified_shape_path_count",
            "verified_mesh_face_count",
            "rendered_frame_count",
            "expected_frame_assignment_count",
            "verified_frame_assignment_count",
        )
    }
    assignment_counts["verified_proxy_placeholder_path_count"] = (
        required_nonnegative_integer(
            assignment_verification.get(
                "verified_proxy_placeholder_path_count",
                0,
            ),
            "shader assignment verification verified_proxy_placeholder_path_count",
        )
    )
    renderable_shape_count = required_nonnegative_integer(
        range_report.get("renderable_shape_count"),
        "renderable shape count",
    )
    mesh_shape_count = required_nonnegative_integer(
        range_report.get("mesh_shape_count"),
        "mesh shape count",
    )
    nurbs_surface_shape_count = required_nonnegative_integer(
        range_report.get("nurbs_surface_shape_count"),
        "NURBS surface shape count",
    )
    if cutout_counts["captured_shape_path_count"] != renderable_shape_count:
        raise RuntimeError(
            "Depth authored cutout-transparency evidence does not cover every "
            "renderable shape path."
        )
    if (
        renderable_shape_count != mesh_shape_count + nurbs_surface_shape_count
        or proxy_counts["recovered_path_count"] > renderable_shape_count
        or proxy_counts["recovered_shape_count"] > mesh_shape_count
        or assignment_counts["shape_path_count"] != renderable_shape_count
        or assignment_counts["mesh_path_count"] != mesh_shape_count
        or assignment_counts["nurbs_surface_path_count"]
        != nurbs_surface_shape_count
        or assignment_counts["verified_shape_path_count"]
        != renderable_shape_count
        or assignment_counts["verified_proxy_placeholder_path_count"]
        > mesh_shape_count
        or assignment_counts["rendered_frame_count"] != expected_frame_count
        or assignment_counts["expected_frame_assignment_count"]
        != expected_frame_count * renderable_shape_count
        or assignment_counts["verified_frame_assignment_count"]
        != assignment_counts["expected_frame_assignment_count"]
        or (
            mesh_shape_count > 0
            and assignment_counts["verified_mesh_face_count"]
            < mesh_shape_count
        )
        or (
            mesh_shape_count == 0
            and assignment_counts["verified_mesh_face_count"] != 0
        )
    ):
        raise RuntimeError("Depth shader assignment verification is inconsistent.")

    render_options = range_report.get("render_options")
    if not isinstance(render_options, dict):
        raise RuntimeError("Depth raw-render option evidence is missing.")
    required_disabled_options = (
        "output_transform_disabled",
        "multisample_disabled",
        "line_aa_disabled",
        "ssao_disabled",
        "motion_blur_disabled",
        "depth_of_field_disabled",
        "fog_disabled",
    )
    missing_disabled_options = [
        field for field in required_disabled_options
        if render_options.get(field) is not True
    ]
    if missing_disabled_options:
        raise RuntimeError(
            "Depth raw-render options were not verified: "
            + ", ".join(missing_disabled_options)
            + "."
        )

    if (
        len(color_frame_paths) != expected_frame_count
        or len(depth_frame_paths) != expected_frame_count
    ):
        raise RuntimeError("Color/Depth frame path counts do not match the paired run.")
    Image, ImageChops, _draw, UnidentifiedImageError, pillow_version = (
        _screen_space._require_pillow()
    )
    expected_size = (int(expected_width), int(expected_height))
    for label, paths in (
        ("Color", color_frame_paths),
        ("Depth", depth_frame_paths),
    ):
        for index, frame_path in enumerate(paths):
            path = Path(frame_path)
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(
                    f"{label} frame {index} is missing or empty: {path}"
                )
            try:
                with Image.open(path) as image:
                    if tuple(image.size) != expected_size:
                        raise RuntimeError(
                            f"{label} frame {index} raster size "
                            f"{tuple(image.size)!r} does not match {expected_size!r}."
                        )
                    image.verify()
            except UnidentifiedImageError as exc:
                raise RuntimeError(
                    f"{label} frame {index} is not a valid image: {path}"
                ) from exc

    # Maya Viewport 2.0 can quantize otherwise neutral shader output one least
    # significant bit differently per RGB channel on some GPU/driver pairs.
    # Inspect every full-resolution Depth frame before changing any source. A
    # bounded two-LSB spread is normalized to an exact gray8 PNG; larger chroma
    # remains a fail-closed shader/render error.
    grayscale_source_max_channel_spread = 0
    grayscale_source_drift_pixel_count = 0
    grayscale_source_drift_frame_indices: List[int] = []
    for index, frame_path in enumerate(depth_frame_paths):
        path = Path(frame_path)
        with Image.open(path) as image:
            rgb_image = image.convert("RGB")
            red_channel, green_channel, blue_channel = rgb_image.split()
            low_red_green = ImageChops.darker(red_channel, green_channel)
            high_red_green = ImageChops.lighter(red_channel, green_channel)
            minimum_channel = ImageChops.darker(low_red_green, blue_channel)
            maximum_channel = ImageChops.lighter(high_red_green, blue_channel)
            channel_spread = ImageChops.difference(
                maximum_channel,
                minimum_channel,
            )
            spread_histogram = channel_spread.histogram()
            max_channel_spread = next(
                (
                    value
                    for value in range(255, -1, -1)
                    if spread_histogram[value]
                ),
                0,
            )
            drift_pixel_count = sum(spread_histogram[1:])
            excessive_pixel_count = sum(
                spread_histogram[DEPTH_GRAYSCALE_CHANNEL_TOLERANCE + 1:]
            )
            grayscale_source_max_channel_spread = max(
                grayscale_source_max_channel_spread,
                max_channel_spread,
            )
            grayscale_source_drift_pixel_count += drift_pixel_count
            if drift_pixel_count:
                grayscale_source_drift_frame_indices.append(index)
            if excessive_pixel_count:
                excessive_mask = channel_spread.point(
                    lambda value: (
                        255
                        if value > DEPTH_GRAYSCALE_CHANNEL_TOLERANCE
                        else 0
                    )
                )
                bounds = excessive_mask.getbbox()
                if bounds is None:
                    sample_coordinate = (0, 0)
                else:
                    sample_y = int(bounds[1])
                    row_bounds = excessive_mask.crop(
                        (0, sample_y, excessive_mask.width, sample_y + 1)
                    ).getbbox()
                    sample_coordinate = (
                        int(row_bounds[0]) if row_bounds is not None else 0,
                        sample_y,
                    )
                sample_rgb = tuple(
                    int(value) for value in rgb_image.getpixel(sample_coordinate)
                )
                raise RuntimeError(
                    "Depth shader raster must contain grayscale only; "
                    f"frame {index} ({path}) has {excessive_pixel_count} "
                    "pixel(s) above the allowed RGB channel spread "
                    f"{DEPTH_GRAYSCALE_CHANNEL_TOLERANCE}, with maximum "
                    f"spread {max_channel_spread} and sample RGB "
                    f"{sample_rgb} at {sample_coordinate}."
                )

    grayscale_normalized = bool(grayscale_source_drift_frame_indices)
    if grayscale_normalized:
        staged_grayscale_frames: List[tuple[Path, Path]] = []
        try:
            for index, frame_path in enumerate(depth_frame_paths):
                path = Path(frame_path)
                staged_path = path.with_name(
                    f".{path.name}.{uuid.uuid4().hex}.hmb-gray.png"
                )
                staged_grayscale_frames.append((staged_path, path))
                with Image.open(path) as image:
                    rgb_image = image.convert("RGB")
                    red_channel, green_channel, blue_channel = rgb_image.split()
                    low_red_green = ImageChops.darker(
                        red_channel,
                        green_channel,
                    )
                    high_red_green = ImageChops.lighter(
                        red_channel,
                        green_channel,
                    )
                    median_channel = ImageChops.lighter(
                        low_red_green,
                        ImageChops.darker(high_red_green, blue_channel),
                    )
                    median_channel.save(staged_path, format="PNG")
                with Image.open(staged_path) as staged_image:
                    if (
                        staged_image.mode != "L"
                        or tuple(staged_image.size) != expected_size
                    ):
                        raise RuntimeError(
                            "Depth grayscale normalization produced an invalid "
                            f"frame {index}: {staged_path}"
                        )
                    staged_image.verify()
            for staged_path, path in staged_grayscale_frames:
                os.replace(staged_path, path)
        finally:
            for staged_path, _path in staged_grayscale_frames:
                try:
                    staged_path.unlink(missing_ok=True)
                except OSError:
                    pass

    sample_count = min(DEPTH_QUALITY_SAMPLE_FRAMES, expected_frame_count)
    sample_indices = (
        [0]
        if sample_count <= 1
        else sorted({
            int(round(index * (expected_frame_count - 1) / (sample_count - 1)))
            for index in range(sample_count)
        })
    )
    grayscale_min = 255
    grayscale_max = 0
    frame_quality: List[Dict[str, Any]] = []
    for index in sample_indices:
        try:
            with Image.open(Path(depth_frame_paths[index])) as image:
                rgb_sample = image.convert("RGB")
                rgb_sample.thumbnail((256, 256))
                rgb_pixels = list(rgb_sample.getdata())
        except UnidentifiedImageError as exc:
            raise RuntimeError(
                f"Depth sample frame {index} is not a valid image."
            ) from exc
        if not rgb_pixels:
            raise RuntimeError(f"Depth sample frame {index} contains no pixels.")
        for red, green, blue in rgb_pixels:
            if red != green or green != blue:
                raise RuntimeError(
                    "Depth shader raster must contain grayscale only."
                )
        values = [pixel[0] for pixel in rgb_pixels]
        grayscale_min = min(grayscale_min, min(values))
        grayscale_max = max(grayscale_max, max(values))
        total = len(values)
        black_pixel_count = sum(value == 0 for value in values)
        foreground_values = [value for value in values if value > 0]
        foreground_count = len(foreground_values)
        foreground_coverage = foreground_count / total
        black_background_ratio = black_pixel_count / total
        histogram = [0] * 256
        for value in foreground_values:
            histogram[value] += 1
        meaningful_floor = max(1, int(round(foreground_count * 0.00005)))
        meaningful_levels = sum(
            1 for count in histogram if count >= meaningful_floor
        )
        entropy_bits = 0.0
        for count in histogram:
            if count and foreground_count:
                probability = count / foreground_count
                entropy_bits -= probability * math.log2(probability)
        normalized_entropy = entropy_bits / 8.0
        near_ceiling_start = max(
            1,
            int(round(DEPTH_NEAR_COLOR * 255.0)) - 3,
        )
        white_saturation = (
            sum(histogram[near_ceiling_start:]) / foreground_count
            if foreground_count
            else 0.0
        )

        width, height = rgb_sample.size
        smooth_neighbors = 0
        large_jumps = 0
        neighbor_count = 0
        for row in range(height):
            offset = row * width
            for column in range(width - 1):
                left = values[offset + column]
                right = values[offset + column + 1]
                if left <= 0 or right <= 0:
                    continue
                difference = abs(right - left)
                smooth_neighbors += int(1 <= difference <= 12)
                large_jumps += int(difference >= 64)
                neighbor_count += 1
        for row in range(height - 1):
            offset = row * width
            next_offset = offset + width
            for column in range(width):
                upper = values[offset + column]
                lower = values[next_offset + column]
                if upper <= 0 or lower <= 0:
                    continue
                difference = abs(lower - upper)
                smooth_neighbors += int(1 <= difference <= 12)
                large_jumps += int(difference >= 64)
                neighbor_count += 1
        smooth_ratio = smooth_neighbors / max(1, neighbor_count)
        large_jump_ratio = large_jumps / max(1, neighbor_count)
        foreground_min = min(foreground_values) if foreground_values else None
        foreground_max = max(foreground_values) if foreground_values else None
        value_span = (
            foreground_max - foreground_min
            if foreground_min is not None and foreground_max is not None
            else 0
        )

        diagnostic_warning = ""
        diagnostic_rated = True
        if not foreground_count:
            diagnostic_status = "no_visible_depth"
            diagnostic_rated = False
        elif foreground_count < DEPTH_QUALITY_MIN_DIAGNOSTIC_FOREGROUND_PIXELS:
            diagnostic_status = "sparse_unrated"
            diagnostic_rated = False
        elif meaningful_levels == 1 and white_saturation >= 0.95:
            diagnostic_status = "mask_like_candidate"
            diagnostic_warning = (
                "Visible Depth is a single near-white tone; this may be a valid "
                "flat/clipped surface or a mask-like result."
            )
        elif meaningful_levels == 1:
            diagnostic_status = "flat_depth"
        elif meaningful_levels <= 4:
            diagnostic_status = "posterized_candidate"
            diagnostic_warning = (
                "Visible Depth contains only a few discrete foreground tones."
            )
        elif large_jump_ratio > DEPTH_QUALITY_MAX_LARGE_JUMPS:
            diagnostic_status = "irregular_candidate"
            diagnostic_warning = (
                "Visible Depth contains unusually many large foreground jumps."
            )
        elif (
            value_span >= 128
            and meaningful_levels >= DEPTH_QUALITY_MIN_MEANINGFUL_LEVELS
            and normalized_entropy >= DEPTH_QUALITY_MIN_NORMALIZED_ENTROPY
            and white_saturation <= DEPTH_QUALITY_MAX_WHITE_SATURATION
            and smooth_ratio >= DEPTH_QUALITY_MIN_SMOOTH_NEIGHBORS
        ):
            diagnostic_status = "continuous_detail"
        else:
            diagnostic_status = "low_detail_candidate"
            diagnostic_warning = (
                "Visible Depth has limited foreground tonal detail; this may be "
                "valid for a flat or low-relief scene."
            )
        passed = diagnostic_status in {
            "continuous_detail",
            "flat_depth",
            "no_visible_depth",
            "sparse_unrated",
        }
        frame_quality.append({
            "frame_index": index,
            "passed": passed,
            "diagnostic_status": diagnostic_status,
            "diagnostic_rated": diagnostic_rated,
            "diagnostic_warning": diagnostic_warning,
            "value_min": min(values),
            "value_max": max(values),
            "value_span": value_span,
            "foreground_value_min": foreground_min,
            "foreground_value_max": foreground_max,
            "foreground_pixel_count": foreground_count,
            "foreground_coverage_ratio": round(foreground_coverage, 6),
            "black_background_ratio": round(black_background_ratio, 6),
            "foreground_neighbor_count": neighbor_count,
            "meaningful_levels": meaningful_levels,
            "entropy_bits": round(entropy_bits, 6),
            "normalized_entropy": round(normalized_entropy, 6),
            "white_saturation_ratio": round(white_saturation, 6),
            "smooth_neighbor_ratio": round(smooth_ratio, 6),
            "large_jump_ratio": round(large_jump_ratio, 6),
        })

    passing_frames = sum(int(item["passed"]) for item in frame_quality)
    required_passing_frames = max(
        1,
        int(math.ceil(len(frame_quality) * DEPTH_QUALITY_MIN_PASS_FRACTION)),
    )

    diagnostic_priority = (
        "irregular_candidate",
        "mask_like_candidate",
        "posterized_candidate",
        "low_detail_candidate",
    )
    diagnostic_statuses = [item["diagnostic_status"] for item in frame_quality]
    sequence_diagnostic_status = next(
        (
            status
            for status in diagnostic_priority
            if status in diagnostic_statuses
        ),
        (
            "continuous_detail"
            if "continuous_detail" in diagnostic_statuses
            else (
                "flat_depth"
                if "flat_depth" in diagnostic_statuses
                else (
                    "sparse_unrated"
                    if "sparse_unrated" in diagnostic_statuses
                    else "no_visible_depth"
                )
            )
        ),
    )
    diagnostic_warnings = [
        {
            "frame_index": item["frame_index"],
            "status": item["diagnostic_status"],
            "message": item["diagnostic_warning"],
        }
        for item in frame_quality
        if item["diagnostic_warning"]
    ]

    def median_metric(name: str) -> float:
        numbers = sorted(float(item[name]) for item in frame_quality)
        middle = len(numbers) // 2
        if len(numbers) % 2:
            return numbers[middle]
        return (numbers[middle - 1] + numbers[middle]) / 2.0

    return {
        "profile": DEPTH_PLAYBLAST_PROFILE,
        "validated": True,
        "frame_count": expected_frame_count,
        "fps": float(expected_fps),
        "start_frame": float(expected_start_frame),
        "end_frame": float(expected_end_frame),
        "resolution": {
            "width": int(expected_width),
            "height": int(expected_height),
        },
        "camera": color_camera,
        "frame_map_match": True,
        "cutout_transparency": dict(cutout_transparency),
        "grayscale_sampled_frame_indices": sample_indices,
        "grayscale_min": grayscale_min,
        "grayscale_max": grayscale_max,
        "grayscale_channel_tolerance": DEPTH_GRAYSCALE_CHANNEL_TOLERANCE,
        "grayscale_source_max_channel_spread": (
            grayscale_source_max_channel_spread
        ),
        "grayscale_source_drift_pixel_count": (
            grayscale_source_drift_pixel_count
        ),
        "grayscale_source_drift_frame_indices": (
            grayscale_source_drift_frame_indices
        ),
        "grayscale_normalized": grayscale_normalized,
        "quality_passed_frames": passing_frames,
        "quality_required_frames": required_passing_frames,
        "quality_frame_reports": frame_quality,
        "diagnostic_status": sequence_diagnostic_status,
        "diagnostic_warnings": diagnostic_warnings,
        "content_heuristics_blocking": False,
        "quality_medians": {
            "foreground_coverage_ratio": median_metric(
                "foreground_coverage_ratio"
            ),
            "black_background_ratio": median_metric(
                "black_background_ratio"
            ),
            "meaningful_levels": median_metric("meaningful_levels"),
            "normalized_entropy": median_metric("normalized_entropy"),
            "white_saturation_ratio": median_metric("white_saturation_ratio"),
            "smooth_neighbor_ratio": median_metric("smooth_neighbor_ratio"),
            "large_jump_ratio": median_metric("large_jump_ratio"),
        },
        "quality_thresholds": {
            "minimum_meaningful_levels": DEPTH_QUALITY_MIN_MEANINGFUL_LEVELS,
            "minimum_normalized_entropy": DEPTH_QUALITY_MIN_NORMALIZED_ENTROPY,
            "maximum_white_saturation_ratio": DEPTH_QUALITY_MAX_WHITE_SATURATION,
            "minimum_smooth_neighbor_ratio": DEPTH_QUALITY_MIN_SMOOTH_NEIGHBORS,
            "maximum_large_jump_ratio": DEPTH_QUALITY_MAX_LARGE_JUMPS,
            "minimum_pass_fraction": DEPTH_QUALITY_MIN_PASS_FRACTION,
            "minimum_diagnostic_foreground_pixels": (
                DEPTH_QUALITY_MIN_DIAGNOSTIC_FOREGROUND_PIXELS
            ),
            "measurement_scope": "nonzero_foreground_only",
            "blocking": False,
        },
        "background_contract": "pure_black",
        "pillow_version": pillow_version,
    }


def _validate_motion_face_semantics(
    report: Dict[str, Any],
    frame_signature: Sequence[tuple[int, float]],
) -> Dict[str, Any]:
    """Validate semantic face samples without granting them appearance authority."""

    def finite(value: Any, label: str) -> float:
        try:
            number = float(value)
        except Exception as exc:
            raise RuntimeError(
                f"Motion Guide face {label} is not numeric."
            ) from exc
        if not math.isfinite(number):
            raise RuntimeError(f"Motion Guide face {label} is not finite.")
        return number

    def count(payload: Dict[str, Any], field: str) -> int:
        value = payload.get(field)
        if isinstance(value, bool):
            raise RuntimeError(
                f"Motion Guide face {field} must be a non-negative integer."
            )
        try:
            integer = int(value)
        except Exception as exc:
            raise RuntimeError(
                f"Motion Guide face {field} must be a non-negative integer."
            ) from exc
        try:
            if float(value) != float(integer):
                raise ValueError
        except Exception as exc:
            raise RuntimeError(
                f"Motion Guide face {field} must be a non-negative integer."
            ) from exc
        if integer < 0:
            raise RuntimeError(
                f"Motion Guide face {field} must be a non-negative integer."
            )
        return integer

    face = report.get("face_semantics")
    if not isinstance(face, dict):
        raise RuntimeError("Motion Guide face_semantics report is missing.")
    required_face_contract = {
        "schema": "hmb-maya-face-semantics",
        "channel_source_policy": (
            "final_evaluated_blendshape_weight_raw_value"
        ),
        "controller_policy": (
            "connected_numeric_nurbs_curve_controller_plug_raw_value_provenance_only"
        ),
        "localization_policy": (
            "read_only_blendshape_target_delta_heatmap_then_bounded_fail_closed_surface_completion"
        ),
        "raster_policy": (
            "surface_pinned_brow_eyelid_mouth_jaw_landmarks_only;"
            "raw_nurbs_curve_geometry_never_rendered"
        ),
        "visibility_policy": (
            "front_facing_vertex_normal_plus_camera_ray_first_hit_visible_only"
        ),
        "partial_contour_policy": (
            "defined_face_edge_both_endpoints_front_facing_first_hit_visible"
        ),
        "visibility_opportunity_policy": (
            "target_visible_defined_face_edge_both_endpoints_front_facing_"
            "first_hit_visible_and_minimum_screen_span"
        ),
        "ray_scope": "authored_visible_character_target_meshes",
        "unknown_alias_policy": (
            "raw_alias_and_value_preserved_sidecar_only_no_raster_guess"
        ),
    }
    for field, expected in required_face_contract.items():
        if _clean(face.get(field)) != expected:
            raise RuntimeError(
                f"Motion Guide face_semantics has unsupported {field}: "
                f"{face.get(field)!r}."
            )
    if int(face.get("schema_version") or 0) != 2:
        raise RuntimeError(
            "Motion Guide face_semantics schema version is unsupported."
        )
    if face.get("curve_geometry_rendered") is not False:
        raise RuntimeError(
            "Motion Guide must never rasterize raw NURBS controller geometry."
        )

    declared_counts = {
        field: count(face, field)
        for field in (
            "target_count",
            "channel_count",
            "driver_count",
            "landmark_count",
            "channel_sample_count",
            "driver_sample_count",
            "rasterized_sample_count",
            "visibility_opportunity_count",
            "hidden_or_occluded_sample_count",
        )
    }
    raw_targets = report.get("targets")
    if not isinstance(raw_targets, list):
        raise RuntimeError("Motion Guide targets must be a list.")
    allowed_groups = {"brow", "eyelid", "mouth", "jaw", "unknown"}
    allowed_sides = {"left", "right", "center"}
    targets: Dict[int, Dict[str, Any]] = {}
    channel_groups: set[str] = set()
    computed_target_count = 0
    computed_channel_count = 0
    computed_driver_count = 0
    computed_landmark_count = 0

    for raw_target in raw_targets:
        if not isinstance(raw_target, dict):
            raise RuntimeError("Motion Guide target descriptor is invalid.")
        try:
            target_index = int(raw_target.get("target_index"))
        except Exception as exc:
            raise RuntimeError(
                "Motion Guide target descriptor has no valid target_index."
            ) from exc
        if target_index <= 0 or target_index in targets:
            raise RuntimeError(
                "Motion Guide face target indices must be positive and unique."
            )

        joint_selection = raw_target.get("joint_selection")
        if joint_selection is not None:
            if not isinstance(joint_selection, dict):
                raise RuntimeError(
                    "Motion Guide target joint_selection must be an object."
                )
            joint_count = count(raw_target, "joint_count")
            joint_ids = raw_target.get("joint_ids")
            joint_labels = raw_target.get("joint_labels")
            if (
                not isinstance(joint_ids, list)
                or not isinstance(joint_labels, list)
                or len(joint_ids) != joint_count
                or len(joint_labels) != joint_count
                or len(set(_clean(item) for item in joint_ids)) != joint_count
                or any(not _clean(item) for item in joint_ids + joint_labels)
            ):
                raise RuntimeError(
                    "Motion Guide target joint identity evidence is inconsistent."
                )
            selection_counts = {
                field: count(joint_selection, field)
                for field in (
                    "raw_joint_count",
                    "selected_joint_count",
                    "excluded_joint_count",
                    "skin_cluster_count",
                    "truncated_joint_count",
                    "connected_edge_count",
                    "semantic_root_count",
                )
            }
            if selection_counts["selected_joint_count"] != joint_count:
                raise RuntimeError(
                    "Motion Guide selected joint count differs from its target."
                )
            if (
                joint_count > selection_counts["raw_joint_count"]
                or selection_counts["connected_edge_count"]
                > max(0, joint_count - 1)
                or selection_counts["semantic_root_count"] > joint_count
                or (joint_count > 1 and not selection_counts["connected_edge_count"])
            ):
                raise RuntimeError(
                    "Motion Guide target joint structure is disconnected or inconsistent."
                )
            excluded_by_reason = joint_selection.get("excluded_by_reason")
            if not isinstance(excluded_by_reason, dict) or any(
                not _clean(reason)
                or count({"value": value}, "value") < 0
                for reason, value in excluded_by_reason.items()
            ):
                raise RuntimeError(
                    "Motion Guide target joint exclusion evidence is invalid."
                )
            if sum(int(value) for value in excluded_by_reason.values()) != (
                selection_counts["excluded_joint_count"]
            ):
                raise RuntimeError(
                    "Motion Guide target excluded joint count is inconsistent."
                )
            selection_source = _clean(joint_selection.get("source"))
            if selection_source not in {
                "background_marker_rigid_transform",
                "weighted_skin_cluster_influences",
                "direct_descendant_joint_fallback",
                "character_reference_joint_fallback",
                "character_reference_structural_fallback",
            }:
                raise RuntimeError(
                    "Motion Guide target joint selection source is unsupported."
                )
            fallback_reasons = joint_selection.get(
                "structural_fallback_reasons"
            )
            if (
                not isinstance(fallback_reasons, list)
                or any(not _clean(item) for item in fallback_reasons)
                or len(set(_clean(item) for item in fallback_reasons))
                != len(fallback_reasons)
            ):
                raise RuntimeError(
                    "Motion Guide target structural fallback evidence is invalid."
                )
            if joint_count:
                for field in (
                    "pre_fallback_selected_joint_count",
                    "pre_fallback_connected_edge_count",
                    "pre_fallback_semantic_root_count",
                ):
                    count(joint_selection, field)
            root_source = _clean(raw_target.get("root_source"))
            root_joint_id = _clean(raw_target.get("root_joint_id"))
            if root_source == "semantic_joint":
                if (
                    not root_joint_id
                    or not selection_counts["semantic_root_count"]
                    or root_joint_id not in set(_clean(item) for item in joint_ids)
                ):
                    raise RuntimeError(
                        "Motion Guide semantic root lacks matching joint evidence."
                    )
            elif root_source == "target_transform":
                if root_joint_id:
                    raise RuntimeError(
                        "Motion Guide target-transform root must not claim a joint."
                    )
            else:
                raise RuntimeError(
                    "Motion Guide target root source is unsupported."
                )
            expected_mode = "joint_hierarchy" if joint_count else "rigid_transform"
            if _clean(raw_target.get("mode")) != expected_mode:
                raise RuntimeError(
                    "Motion Guide target mode differs from its joint evidence."
                )

        channels = raw_target.get("face_channels")
        drivers = raw_target.get("face_drivers")
        landmarks = raw_target.get("face_landmarks")
        edges = raw_target.get("face_edges")
        for label, value in (
            ("face_channels", channels),
            ("face_drivers", drivers),
            ("face_landmarks", landmarks),
            ("face_edges", edges),
        ):
            if not isinstance(value, list):
                raise RuntimeError(
                    f"Motion Guide target {target_index} {label} must be a list."
                )
        if int(raw_target.get("face_channel_count") or 0) != len(channels):
            raise RuntimeError("Motion Guide face channel count is inconsistent.")
        if int(raw_target.get("face_driver_count") or 0) != len(drivers):
            raise RuntimeError("Motion Guide face driver count is inconsistent.")
        if int(raw_target.get("face_landmark_count") or 0) != len(landmarks):
            raise RuntimeError("Motion Guide face landmark count is inconsistent.")

        channel_ids: set[str] = set()
        controller_plugs: set[str] = set()
        for channel in channels:
            if not isinstance(channel, dict):
                raise RuntimeError("Motion Guide face channel descriptor is invalid.")
            channel_id = _clean(channel.get("id"))
            alias = _clean(channel.get("alias"))
            weight_plug = _clean(channel.get("weight_plug"))
            group = _clean(channel.get("group"))
            side = _clean(channel.get("side"))
            try:
                weight_index = int(channel.get("weight_index"))
            except Exception as exc:
                raise RuntimeError(
                    "Motion Guide face channel weight_index is invalid."
                ) from exc
            if (
                not channel_id
                or channel_id in channel_ids
                or not alias
                or not weight_plug
                or weight_index < 0
            ):
                raise RuntimeError(
                    "Motion Guide face channel identity is incomplete or duplicated."
                )
            if group not in allowed_groups or side not in allowed_sides:
                raise RuntimeError(
                    "Motion Guide face channel semantic group or side is unsupported."
                )
            if not isinstance(channel.get("raster_eligible"), bool):
                raise RuntimeError(
                    "Motion Guide face raster_eligible must be boolean."
                )
            if group == "unknown" and channel.get("raster_eligible"):
                raise RuntimeError(
                    "Unknown face aliases may be preserved only in the sidecar."
                )
            raw_controller_plugs = channel.get("controller_plugs")
            if not isinstance(raw_controller_plugs, list) or any(
                not _clean(item) for item in raw_controller_plugs
            ):
                raise RuntimeError(
                    "Motion Guide face controller plug provenance is invalid."
                )
            raw_affected_shapes = channel.get("affected_shapes")
            if not isinstance(raw_affected_shapes, list):
                raise RuntimeError(
                    "Motion Guide face affected_shapes provenance is invalid."
                )
            channel_ids.add(channel_id)
            controller_plugs.update(_clean(item) for item in raw_controller_plugs)
            if group != "unknown":
                channel_groups.add(group)

        driver_ids: set[str] = set()
        driver_plugs: set[str] = set()
        keyed_semantic_driver_count = 0
        for driver in drivers:
            if not isinstance(driver, dict):
                raise RuntimeError("Motion Guide face driver descriptor is invalid.")
            driver_id = _clean(driver.get("id"))
            driver_plug = _clean(driver.get("plug"))
            if (
                not driver_id
                or driver_id in driver_ids
                or not driver_plug
                or driver_plug in driver_plugs
            ):
                raise RuntimeError(
                    "Motion Guide face driver identity is incomplete or duplicated."
                )
            driver_ids.add(driver_id)
            driver_plugs.add(driver_plug)
            provenance = _clean(driver.get("provenance"))
            if provenance:
                if provenance != "target_local_keyed_semantic_controller":
                    raise RuntimeError(
                        "Motion Guide face driver provenance is unsupported."
                    )
                if (
                    _clean(driver.get("group"))
                    not in (allowed_groups - {"unknown"})
                    or _clean(driver.get("side")) not in allowed_sides
                    or not _clean(driver.get("action"))
                    or not _clean(driver.get("node"))
                    or not _clean(driver.get("node_id"))
                    or not _clean(driver.get("label"))
                    or driver.get("curve_geometry_rendered") is not False
                ):
                    raise RuntimeError(
                        "Motion Guide keyed semantic driver evidence is incomplete."
                    )
                animation_evidence = driver.get("animation_evidence")
                if not isinstance(animation_evidence, dict):
                    raise RuntimeError(
                        "Motion Guide keyed semantic driver animation evidence is missing."
                    )
                animation_source = _clean(animation_evidence.get("source"))
                key_count = count(animation_evidence, "key_count")
                animation_nodes = animation_evidence.get("animation_nodes")
                if (
                    animation_source not in {
                        "direct_keyframes",
                        "upstream_anim_curve",
                    }
                    or not isinstance(animation_nodes, list)
                    or any(not _clean(item) for item in animation_nodes)
                    or (
                        animation_source == "direct_keyframes"
                        and key_count <= 0
                    )
                    or (
                        animation_source == "upstream_anim_curve"
                        and (key_count != 0 or not animation_nodes)
                    )
                ):
                    raise RuntimeError(
                        "Motion Guide keyed semantic driver animation evidence is invalid."
                    )
                keyed_semantic_driver_count += 1
        if not controller_plugs.issubset(driver_plugs):
            raise RuntimeError(
                "Motion Guide face channel references an undeclared controller plug."
            )

        face_discovery = raw_target.get("face_discovery")
        if keyed_semantic_driver_count:
            if not isinstance(face_discovery, dict):
                raise RuntimeError(
                    "Motion Guide keyed semantic driver audit is missing."
                )
            keyed_audit = face_discovery.get("keyed_semantic_driver_audit")
            if not isinstance(keyed_audit, dict):
                raise RuntimeError(
                    "Motion Guide keyed semantic driver audit is missing."
                )
            if _clean(keyed_audit.get("policy")) != (
                "target_scope_semantic_curve_control_keyed_numeric_plugs_only"
            ) or keyed_audit.get("curve_geometry_rendered") is not False:
                raise RuntimeError(
                    "Motion Guide keyed semantic driver policy is unsupported."
                )
            keyed_counts = {
                field: count(keyed_audit, field)
                for field in (
                    "keyed_semantic_controller_count",
                    "keyed_semantic_candidate_plug_count",
                    "keyed_semantic_driver_count",
                    "keyed_semantic_rejected_nonanimated_count",
                )
            }
            if (
                keyed_counts["keyed_semantic_driver_count"]
                != keyed_semantic_driver_count
                or keyed_counts["keyed_semantic_driver_count"]
                > keyed_counts["keyed_semantic_candidate_plug_count"]
                or keyed_counts["keyed_semantic_rejected_nonanimated_count"]
                > keyed_counts["keyed_semantic_candidate_plug_count"]
            ):
                raise RuntimeError(
                    "Motion Guide keyed semantic driver counts are inconsistent."
                )

        landmark_ids: set[str] = set()
        semantic_mesh_landmark_ids: set[str] = set()
        visible_landmark_contract: Dict[str, Dict[str, Any]] = {}
        for landmark in landmarks:
            if not isinstance(landmark, dict):
                raise RuntimeError("Motion Guide face landmark descriptor is invalid.")
            landmark_id = _clean(landmark.get("id"))
            region = _clean(landmark.get("region"))
            side = _clean(landmark.get("side"))
            try:
                vertex_index = int(landmark.get("vertex_index"))
            except Exception as exc:
                raise RuntimeError(
                    "Motion Guide face landmark vertex index is invalid."
                ) from exc
            raw_channel_ids = landmark.get("channel_ids")
            if (
                not landmark_id
                or landmark_id in landmark_ids
                or region not in (allowed_groups - {"unknown"})
                or side not in allowed_sides
                or vertex_index < 0
                or not isinstance(raw_channel_ids, list)
                or not raw_channel_ids
                or not set(_clean(item) for item in raw_channel_ids).issubset(
                    channel_ids
                )
            ):
                raise RuntimeError(
                    "Motion Guide face landmark identity or channel reference is invalid."
                )
            finite(
                landmark.get("surface_snap_distance"),
                f"landmark {landmark_id} surface_snap_distance",
            )
            anchor_method = _clean(landmark.get("anchor_method"))
            if anchor_method not in {
                "blendshape_target_delta_heatmap",
                "bounded_bilateral_surface_offset_fallback",
                "semantic_face_axis_lower_surface_inference",
                "semantic_bilateral_jaw_midpoint_surface_inference",
                "semantic_face_axis_center_surface_fallback",
                "semantic_bilateral_jaw_surface_profile_inference",
                "render_scope_semantic_mesh_vertex",
                "rotate_pivot",
                "curve_cv_centroid",
            }:
                raise RuntimeError(
                    "Motion Guide face landmark anchor method is unsupported."
                )
            if anchor_method == "render_scope_semantic_mesh_vertex":
                surface_vertex_distance = finite(
                    landmark.get("surface_vertex_distance"),
                    f"landmark {landmark_id} surface_vertex_distance",
                )
                if (
                    region != "eyelid"
                    or _clean(landmark.get("anchor_source"))
                    != "render_scope_semantic_mesh_vertex"
                    or not _clean(landmark.get("mesh"))
                    or not _clean(landmark.get("mesh_id"))
                    or _clean(landmark.get("controller_id"))
                    or _clean(landmark.get("controller_label"))
                    or abs(float(landmark.get("surface_snap_distance"))) > 1e-9
                    or abs(surface_vertex_distance) > 1e-9
                    or count(landmark, "anchor_sample_count") <= 0
                ):
                    raise RuntimeError(
                        "Motion Guide semantic mesh landmark evidence is incomplete."
                    )
                semantic_mesh_landmark_ids.add(landmark_id)
            anchor_confidence = finite(
                landmark.get("anchor_confidence"),
                f"landmark {landmark_id} anchor_confidence",
            )
            if not 0.0 <= anchor_confidence <= 1.0:
                raise RuntimeError(
                    "Motion Guide face landmark confidence is outside 0.0..1.0."
                )
            landmark_ids.add(landmark_id)
            visible_landmark_contract[landmark_id] = landmark

        edge_pairs: set[tuple[str, str]] = set()
        for edge in edges:
            if not isinstance(edge, dict):
                raise RuntimeError("Motion Guide face edge descriptor is invalid.")
            start = _clean(edge.get("from"))
            end = _clean(edge.get("to"))
            region = _clean(edge.get("region"))
            if (
                not start
                or not end
                or start == end
                or start not in landmark_ids
                or end not in landmark_ids
                or region not in (allowed_groups - {"unknown"})
                or (start, end) in edge_pairs
            ):
                raise RuntimeError(
                    "Motion Guide face edge reference is invalid or duplicated."
                )
            edge_pairs.add((start, end))

        landmark_audit = raw_target.get("face_landmark_audit")
        if landmark_audit is not None:
            if not isinstance(landmark_audit, dict):
                raise RuntimeError(
                    "Motion Guide face landmark audit must be an object."
                )
            completion_audit = landmark_audit.get("surface_completion")
            if completion_audit is not None:
                if not isinstance(completion_audit, dict):
                    raise RuntimeError(
                        "Motion Guide face surface completion audit is invalid."
                    )
                center_candidates = completion_audit.get(
                    "jaw_center_candidate_evidence"
                )
                if not isinstance(center_candidates, list):
                    raise RuntimeError(
                        "Motion Guide jaw center candidate audit must be a list."
                    )
                for candidate_audit in center_candidates:
                    if not isinstance(candidate_audit, dict):
                        raise RuntimeError(
                            "Motion Guide jaw center candidate evidence is invalid."
                        )
                    status = _clean(candidate_audit.get("status"))
                    stage = _clean(candidate_audit.get("stage"))
                    rejection = _clean(candidate_audit.get("rejection"))
                    if (
                        status not in {"accepted", "rejected"}
                        or not stage
                        or (status == "rejected" and not rejection)
                        or (status == "accepted" and rejection)
                    ):
                        raise RuntimeError(
                            "Motion Guide jaw center candidate decision is invalid."
                        )
                    for metric in (
                        "downward_progress_fraction",
                        "jaw_midpoint_lateral_drift_fraction",
                        "mouth_center_lateral_drift_fraction",
                        "mouth_center_lateral_offset_fraction",
                        "maximum_center_drift_fraction",
                        "bilateral_span_position",
                        "bilateral_jaw_span_fraction",
                        "surface_snap_fraction",
                    ):
                        if metric in candidate_audit:
                            finite(
                                candidate_audit.get(metric),
                                "jaw center candidate {0}".format(metric),
                            )
                    nearest_scanned_metrics = candidate_audit.get(
                        "nearest_scanned_metrics"
                    )
                    if nearest_scanned_metrics is not None:
                        if not isinstance(nearest_scanned_metrics, dict):
                            raise RuntimeError(
                                "Motion Guide nearest scanned jaw metrics are invalid."
                            )
                        for metric in (
                            "downward_progress_fraction",
                            "jaw_midpoint_lateral_drift_fraction",
                            "mouth_center_lateral_drift_fraction",
                            "mouth_center_lateral_offset_fraction",
                            "maximum_center_drift_fraction",
                            "bilateral_span_position",
                            "surface_snap_fraction",
                        ):
                            if metric not in nearest_scanned_metrics:
                                raise RuntimeError(
                                    "Motion Guide nearest scanned jaw evidence "
                                    "is incomplete."
                                )
                            finite(
                                nearest_scanned_metrics.get(metric),
                                "nearest scanned jaw {0}".format(metric),
                            )
                    declared_candidate_counts = {}
                    for field in (
                        "surface_vertex_count",
                        "scanned_candidate_count",
                        "eligible_candidate_count",
                    ):
                        if field in candidate_audit:
                            declared_candidate_counts[field] = count(
                                candidate_audit,
                                field,
                            )
                    if (
                        "scanned_candidate_count" in declared_candidate_counts
                        and "eligible_candidate_count" in declared_candidate_counts
                        and declared_candidate_counts[
                            "eligible_candidate_count"
                        ] > declared_candidate_counts[
                            "scanned_candidate_count"
                        ]
                    ):
                        raise RuntimeError(
                            "Motion Guide jaw center eligible count exceeds "
                            "its scanned snap-sphere count."
                        )
                    score_policy = candidate_audit.get(
                        "selection_score_policy"
                    )
                    if score_policy is not None and _clean(score_policy) != (
                        "surface_distance_then_vertex_index"
                    ):
                        raise RuntimeError(
                            "Motion Guide jaw center candidate score policy "
                            "is unsupported."
                        )
                    selected_score = candidate_audit.get("selected_score")
                    if selected_score is not None:
                        if (
                            not isinstance(selected_score, list)
                            or len(selected_score) != 2
                        ):
                            raise RuntimeError(
                                "Motion Guide jaw center selected score is invalid."
                            )
                        selected_distance = finite(
                            selected_score[0],
                            "jaw center selected surface distance",
                        )
                        if selected_distance < 0.0:
                            raise RuntimeError(
                                "Motion Guide jaw center selected distance is invalid."
                            )
                        count(
                            {"selected_vertex": selected_score[1]},
                            "selected_vertex",
                        )
                    if status == "accepted" and stage == (
                        "bilateral_jaw_surface_profile"
                    ):
                        if (
                            declared_candidate_counts.get(
                                "eligible_candidate_count",
                                0,
                            ) <= 0
                            or selected_score is None
                        ):
                            raise RuntimeError(
                                "Motion Guide accepted jaw profile has no "
                                "eligible deterministic selection evidence."
                            )

        if semantic_mesh_landmark_ids:
            if not isinstance(landmark_audit, dict):
                raise RuntimeError(
                    "Motion Guide semantic mesh landmark audit is missing."
                )
            semantic_audit = raw_target.get("face_semantic_surface_audit")
            nested_semantic_audit = landmark_audit.get(
                "semantic_mesh_fallback"
            )
            if (
                not isinstance(semantic_audit, dict)
                or semantic_audit != nested_semantic_audit
            ):
                raise RuntimeError(
                    "Motion Guide semantic mesh audits are missing or differ."
                )
            if (
                _clean(semantic_audit.get("policy"))
                != "render_scope_nonintermediate_deformed_visible_semantic_mesh_edges"
                or _clean(semantic_audit.get("appearance_authority")) != "zero"
                or semantic_audit.get("curve_geometry_rendered") is not False
            ):
                raise RuntimeError(
                    "Motion Guide semantic mesh policy is unsupported."
                )
            semantic_counts = {
                field: count(semantic_audit, field)
                for field in (
                    "candidate_count",
                    "accepted_surface_count",
                    "truncated_surface_count",
                    "surface_limit",
                    "landmark_limit_per_surface",
                    "edge_limit_per_surface",
                    "landmark_count",
                    "edge_count",
                )
            }
            if (
                semantic_counts["surface_limit"]
                != MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES
                or semantic_counts["landmark_limit_per_surface"]
                != MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE
                or semantic_counts["edge_limit_per_surface"]
                != MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE
                or semantic_counts["accepted_surface_count"]
                > semantic_counts["candidate_count"]
                or semantic_counts["accepted_surface_count"]
                > semantic_counts["surface_limit"]
                or semantic_counts["landmark_count"]
                != len(semantic_mesh_landmark_ids)
                or semantic_counts["edge_count"]
                != sum(
                    1
                    for start, end in edge_pairs
                    if start in semantic_mesh_landmark_ids
                    and end in semantic_mesh_landmark_ids
                )
                or semantic_counts["truncated_surface_count"]
                > semantic_counts["candidate_count"]
            ):
                raise RuntimeError(
                    "Motion Guide semantic mesh counts are inconsistent."
                )
            if semantic_audit.get("regions") != ["eyelid"]:
                raise RuntimeError(
                    "Motion Guide semantic mesh regions are unsupported."
                )
            surfaces = semantic_audit.get("surfaces")
            rejections = semantic_audit.get("rejections")
            if (
                not isinstance(surfaces, list)
                or len(surfaces) != semantic_counts["accepted_surface_count"]
                or not isinstance(rejections, list)
            ):
                raise RuntimeError(
                    "Motion Guide semantic mesh surface decisions are invalid."
                )
            semantic_landmark_shapes = {
                _clean(visible_landmark_contract[item].get("mesh"))
                for item in semantic_mesh_landmark_ids
            }
            accepted_shapes: set[str] = set()
            surface_landmark_total = 0
            surface_edge_total = 0
            for surface in surfaces:
                if not isinstance(surface, dict):
                    raise RuntimeError(
                        "Motion Guide semantic mesh surface evidence is invalid."
                    )
                shape = _clean(surface.get("shape"))
                shape_id = _clean(surface.get("shape_id"))
                surface_landmarks = count(surface, "landmark_count")
                surface_edges = count(surface, "edge_count")
                topology = surface.get("topology")
                visibility = surface.get("visibility_evidence")
                deformation = surface.get("deformation_evidence")
                if (
                    not shape
                    or shape in accepted_shapes
                    or not shape_id
                    or _clean(surface.get("region")) != "eyelid"
                    or _clean(surface.get("side")) not in allowed_sides
                    or not _clean(surface.get("name_evidence"))
                    or surface.get("render_scope_verified") is not True
                    or surface.get("intermediate") is not False
                    or finite(
                        surface.get("surface_diagonal"),
                        "semantic surface diagonal",
                    ) <= 0.0
                    or surface_landmarks <= 0
                    or surface_landmarks
                    > MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE
                    or surface_edges <= 0
                    or surface_edges
                    > MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE
                    or not isinstance(topology, dict)
                    or not isinstance(visibility, dict)
                    or visibility.get("eligible") is not True
                    or not isinstance(deformation, dict)
                    or deformation.get("eligible") is not True
                ):
                    raise RuntimeError(
                        "Motion Guide accepted semantic surface lacks final-mesh evidence."
                    )
                topology_counts = {
                    field: count(topology, field)
                    for field in (
                        "topology_edge_count",
                        "boundary_edge_count",
                        "selected_edge_count",
                        "selection_limit",
                    )
                }
                if (
                    topology_counts["selection_limit"]
                    != MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE
                    or topology_counts["selected_edge_count"] != surface_edges
                    or topology_counts["selected_edge_count"]
                    > topology_counts["topology_edge_count"]
                    or topology_counts["boundary_edge_count"]
                    > topology_counts["topology_edge_count"]
                    or _clean(topology.get("selection_source"))
                    not in {"boundary_edges", "bounded_all_edges"}
                ):
                    raise RuntimeError(
                        "Motion Guide semantic topology evidence is inconsistent."
                    )
                deformation_lists = (
                    deformation.get("deformers"),
                    deformation.get("driven_transform_nodes"),
                    deformation.get("driven_transform_plugs"),
                    deformation.get("driven_visibility_nodes"),
                )
                if any(not isinstance(items, list) for items in deformation_lists) or not any(
                    items for items in deformation_lists
                ):
                    raise RuntimeError(
                        "Motion Guide semantic surface has no deformation evidence."
                    )
                if any(
                    _clean(visible_landmark_contract[item].get("mesh")) == shape
                    and _clean(visible_landmark_contract[item].get("mesh_id"))
                    != shape_id
                    for item in semantic_mesh_landmark_ids
                ):
                    raise RuntimeError(
                        "Motion Guide semantic landmark mesh identity is inconsistent."
                    )
                accepted_shapes.add(shape)
                surface_landmark_total += surface_landmarks
                surface_edge_total += surface_edges
            if (
                accepted_shapes != semantic_landmark_shapes
                or surface_landmark_total != semantic_counts["landmark_count"]
                or surface_edge_total != semantic_counts["edge_count"]
            ):
                raise RuntimeError(
                    "Motion Guide semantic surface totals differ from its landmarks."
                )
            for rejection_record in rejections:
                if (
                    not isinstance(rejection_record, dict)
                    or not _clean(rejection_record.get("reason"))
                ):
                    raise RuntimeError(
                        "Motion Guide semantic surface rejection is invalid."
                    )
                if _clean(rejection_record.get("reason")) == (
                    "alpha_driven_card_excluded"
                ) and any(
                    not _clean(rejection_record.get(field))
                    for field in (
                        "shape",
                        "source_plug",
                        "source_material",
                        "evidence_kind",
                        "shading_group",
                    )
                ):
                    raise RuntimeError(
                        "Motion Guide alpha-card rejection evidence is incomplete."
                    )

        targets[target_index] = {
            "descriptor": raw_target,
            "channel_count": len(channels),
            "driver_count": len(drivers),
            "channel_ids": channel_ids,
            "driver_ids": driver_ids,
            "landmarks": visible_landmark_contract,
            "edges": edge_pairs,
        }
        if channels:
            computed_target_count += 1
        computed_channel_count += len(channels)
        computed_driver_count += len(drivers)
        computed_landmark_count += len(landmarks)

    expected_descriptor_counts = {
        "target_count": computed_target_count,
        "channel_count": computed_channel_count,
        "driver_count": computed_driver_count,
        "landmark_count": computed_landmark_count,
    }
    for field, expected in expected_descriptor_counts.items():
        if declared_counts[field] != expected:
            raise RuntimeError(
                f"Motion Guide face {field} does not match target descriptors."
            )

    motion_frames = report.get("motion_frames")
    if not isinstance(motion_frames, list) or len(motion_frames) != len(
        frame_signature
    ):
        raise RuntimeError(
            "Motion Guide face frame samples do not match the Color frame count."
        )
    channel_sample_count = 0
    driver_sample_count = 0
    rasterized_sample_count = 0
    visibility_opportunity_count = 0
    hidden_or_occluded_sample_count = 0
    rasterized_frame_indices: set[int] = set()
    expected_target_indices = set(targets)
    for frame_index, (frame, signature) in enumerate(
        zip(motion_frames, frame_signature)
    ):
        if not isinstance(frame, dict):
            raise RuntimeError("Motion Guide face frame descriptor is invalid.")
        if int(frame.get("sequence_index") or 0) != signature[0]:
            raise RuntimeError("Motion Guide face frame sequence is inconsistent.")
        if abs(
            finite(frame.get("maya_frame"), f"frame {frame_index} maya_frame")
            - float(signature[1])
        ) > 1e-6:
            raise RuntimeError("Motion Guide face frame time is inconsistent.")
        frame_targets = frame.get("targets")
        if not isinstance(frame_targets, list):
            raise RuntimeError("Motion Guide face frame targets must be a list.")
        seen_frame_targets: set[int] = set()
        for frame_target in frame_targets:
            if not isinstance(frame_target, dict):
                raise RuntimeError("Motion Guide face frame target is invalid.")
            try:
                target_index = int(frame_target.get("target_index"))
            except Exception as exc:
                raise RuntimeError(
                    "Motion Guide face frame target_index is invalid."
                ) from exc
            if target_index not in targets or target_index in seen_frame_targets:
                raise RuntimeError(
                    "Motion Guide face frame target reference is unknown or duplicated."
                )
            seen_frame_targets.add(target_index)
            contract = targets[target_index]
            face_frame = frame_target.get("face")
            if not isinstance(face_frame, dict):
                raise RuntimeError("Motion Guide face frame sample is missing.")
            channel_values = face_frame.get("channel_values")
            driver_values = face_frame.get("driver_values")
            landmarks = face_frame.get("landmarks")
            guide_points = face_frame.get("guide_points")
            guide_segments = face_frame.get("guide_segments")
            for label, value in (
                ("channel_values", channel_values),
                ("driver_values", driver_values),
                ("landmarks", landmarks),
                ("guide_points", guide_points),
                ("guide_segments", guide_segments),
            ):
                if not isinstance(value, list):
                    raise RuntimeError(
                        f"Motion Guide face frame {label} must be a list."
                    )
            if len(channel_values) != contract["channel_count"]:
                raise RuntimeError(
                    "Motion Guide face channel sample count is inconsistent."
                )
            if len(driver_values) != contract["driver_count"]:
                raise RuntimeError(
                    "Motion Guide face driver sample count is inconsistent."
                )
            for value_index, value in enumerate(channel_values):
                finite(value, f"channel sample {frame_index}:{target_index}:{value_index}")
            for value_index, value in enumerate(driver_values):
                finite(value, f"driver sample {frame_index}:{target_index}:{value_index}")
            channel_sample_count += len(channel_values)
            driver_sample_count += len(driver_values)
            available = face_frame.get("available")
            raster_ready = face_frame.get("raster_ready")
            rasterized = face_frame.get("rasterized")
            visibility_opportunity = face_frame.get(
                "visibility_opportunity"
            )
            if not all(
                isinstance(value, bool)
                for value in (
                    available,
                    raster_ready,
                    rasterized,
                    visibility_opportunity,
                )
            ):
                raise RuntimeError(
                    "Motion Guide face availability/raster/opportunity flags "
                    "must be boolean."
                )
            if available != bool(contract["channel_count"]):
                raise RuntimeError(
                    "Motion Guide face availability disagrees with its channels."
                )

            sampled_landmarks: Dict[str, Dict[str, Any]] = {}
            for landmark in landmarks:
                if not isinstance(landmark, dict):
                    raise RuntimeError("Motion Guide face landmark sample is invalid.")
                landmark_id = _clean(landmark.get("id"))
                if (
                    landmark_id not in contract["landmarks"]
                    or landmark_id in sampled_landmarks
                ):
                    raise RuntimeError(
                        "Motion Guide face landmark sample has an unknown or duplicate ID."
                    )
                descriptor = contract["landmarks"][landmark_id]
                if (
                    _clean(landmark.get("region"))
                    != _clean(descriptor.get("region"))
                    or _clean(landmark.get("side"))
                    != _clean(descriptor.get("side"))
                ):
                    raise RuntimeError(
                        "Motion Guide face landmark semantic identity changed by frame."
                    )
                for field in ("x", "y", "camera_depth", "normal_view_dot"):
                    finite(
                        landmark.get(field),
                        f"landmark sample {landmark_id} {field}",
                    )
                for field in (
                    "in_frame", "front_facing", "camera_ray_visible", "visible"
                ):
                    if not isinstance(landmark.get(field), bool):
                        raise RuntimeError(
                            "Motion Guide face landmark visibility flags must be boolean."
                        )
                if landmark.get("visible") and not (
                    landmark.get("in_frame")
                    and landmark.get("front_facing")
                    and landmark.get("camera_ray_visible")
                ):
                    raise RuntimeError(
                        "Motion Guide face landmark visibility is internally inconsistent."
                    )
                sampled_landmarks[landmark_id] = landmark

            guide_ids: set[str] = set()
            for point in guide_points:
                if not isinstance(point, dict):
                    raise RuntimeError("Motion Guide face guide point is invalid.")
                point_id = _clean(point.get("id"))
                sampled = sampled_landmarks.get(point_id)
                descriptor = contract["landmarks"].get(point_id)
                if (
                    not point_id
                    or point_id in guide_ids
                    or sampled is None
                    or descriptor is None
                    or not sampled.get("visible")
                    or _clean(point.get("region"))
                    != _clean(descriptor.get("region"))
                    or _clean(point.get("side"))
                    != _clean(descriptor.get("side"))
                ):
                    raise RuntimeError(
                        "Motion Guide face guide point is not backed by a visible landmark."
                    )
                x = finite(point.get("x"), f"guide point {point_id} x")
                y = finite(point.get("y"), f"guide point {point_id} y")
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise RuntimeError(
                        "Motion Guide face guide point lies outside the raster."
                    )
                guide_ids.add(point_id)
            for segment in guide_segments:
                if not isinstance(segment, dict):
                    raise RuntimeError("Motion Guide face guide segment is invalid.")
                start = _clean(segment.get("from"))
                end = _clean(segment.get("to"))
                if (
                    start not in guide_ids
                    or end not in guide_ids
                    or (start, end) not in contract["edges"]
                ):
                    raise RuntimeError(
                        "Motion Guide face guide segment has an invalid reference."
                    )

            if visibility_opportunity:
                if (
                    not available
                    or not raster_ready
                    or frame_target.get("visible") is not True
                    or len(guide_ids) < 2
                    or not guide_segments
                    or _clean(face_frame.get("visibility_reason"))
                    != "front_facing_camera_ray_visible_face_surface"
                ):
                    raise RuntimeError(
                        "Motion Guide face visibility opportunity violates its "
                        "defined-edge visibility contract."
                    )
                visibility_opportunity_count += 1
                if rasterized is not True:
                    raise RuntimeError(
                        "Motion Guide found a visible face-edge opportunity but "
                        "did not rasterize it."
                    )

            if rasterized:
                if (
                    not available
                    or not raster_ready
                    or frame_target.get("visible") is not True
                    or visibility_opportunity is not True
                    or len(guide_ids) < 2
                    or not guide_segments
                    or _clean(face_frame.get("visibility_reason"))
                    != "front_facing_camera_ray_visible_face_surface"
                ):
                    raise RuntimeError(
                        "Motion Guide face rasterization violates its visibility contract."
                    )
                rasterized_sample_count += 1
                rasterized_frame_indices.add(frame_index)
            else:
                if guide_points or guide_segments:
                    raise RuntimeError(
                        "Hidden or occluded face samples must not publish raster guides."
                    )
                if available:
                    hidden_or_occluded_sample_count += 1
        if seen_frame_targets != expected_target_indices:
            raise RuntimeError(
                "Motion Guide face frame does not contain every declared target exactly once."
            )

    computed_sample_counts = {
        "channel_sample_count": channel_sample_count,
        "driver_sample_count": driver_sample_count,
        "rasterized_sample_count": rasterized_sample_count,
        "visibility_opportunity_count": visibility_opportunity_count,
        "hidden_or_occluded_sample_count": hidden_or_occluded_sample_count,
    }
    for field, expected in computed_sample_counts.items():
        if declared_counts[field] != expected:
            raise RuntimeError(
                f"Motion Guide face {field} does not match frame samples."
            )
    if visibility_opportunity_count > 0 and rasterized_sample_count == 0:
        raise RuntimeError(
            "Motion Guide found visible face-edge opportunities but rasterized "
            "no face guide samples."
        )

    palette = report.get("palette")
    if not isinstance(palette, dict):
        raise RuntimeError("Motion Guide palette report is missing.")
    required_face_palette = {
        "face_brow": list(MOTION_GUIDE_FACE_BROW_RGB),
        "face_eyelid": list(MOTION_GUIDE_FACE_EYELID_RGB),
        "face_mouth": list(MOTION_GUIDE_FACE_MOUTH_RGB),
        "face_jaw": list(MOTION_GUIDE_FACE_JAW_RGB),
    }
    for field, expected in required_face_palette.items():
        if palette.get(field) != expected:
            raise RuntimeError(
                f"Motion Guide face palette {field} is unsupported."
            )
    return {
        **declared_counts,
        "semantic_groups": sorted(channel_groups),
        "rasterized_frame_indices": sorted(rasterized_frame_indices),
        "curve_geometry_rendered": False,
    }


def _validate_motion_guide_inputs(
    *,
    result: Dict[str, Any],
    color_sidecar: Dict[str, Any],
    motion_sidecar: Dict[str, Any],
    motion_frame_paths: Sequence[Path],
    expected_frame_count: int,
    expected_fps: float,
    expected_start_frame: float,
    expected_end_frame: float,
    expected_width: int,
    expected_height: int,
) -> Dict[str, Any]:
    """Fail closed unless the typed auxiliary is an exact @video1 Motion Guide."""

    def number(value: Any, label: str) -> float:
        try:
            result_value = float(value)
        except Exception as exc:
            raise RuntimeError(
                f"Motion Guide {label} is not numeric."
            ) from exc
        if not math.isfinite(result_value):
            raise RuntimeError(f"Motion Guide {label} is not finite.")
        return result_value

    def close(value: Any, expected: float, label: str) -> None:
        actual = number(value, label)
        if abs(actual - float(expected)) > 1e-6:
            raise RuntimeError(
                f"Motion Guide {label} does not match @video1 "
                f"({actual!r} != {float(expected)!r})."
            )

    def frame_signature(payload: Dict[str, Any], label: str) -> List[tuple[int, float]]:
        raw_map = payload.get("frame_map")
        if not isinstance(raw_map, list) or len(raw_map) != expected_frame_count:
            raise RuntimeError(
                f"{label} frame_map must contain exactly "
                f"{expected_frame_count} entries."
            )
        signature: List[tuple[int, float]] = []
        for expected_index, raw in enumerate(raw_map):
            if not isinstance(raw, dict):
                raise RuntimeError(
                    f"{label} frame_map entry {expected_index} is invalid."
                )
            try:
                sequence_index = int(raw.get("sequence_index"))
            except Exception as exc:
                raise RuntimeError(
                    f"{label} frame_map entry {expected_index} has no valid "
                    "sequence_index."
                ) from exc
            if sequence_index != expected_index:
                raise RuntimeError(
                    f"{label} frame_map sequence is not contiguous at "
                    f"{expected_index}."
                )
            signature.append((
                sequence_index,
                number(
                    raw.get("maya_frame"),
                    f"{label} frame_map[{expected_index}].maya_frame",
                ),
            ))
        if signature and (
            abs(signature[0][1] - expected_start_frame) > 1e-6
            or abs(signature[-1][1] - expected_end_frame) > 1e-6
        ):
            raise RuntimeError(
                f"{label} frame_map range does not match @video1."
            )
        return signature

    if _clean(motion_sidecar.get("schema")) != "hmb-maya-motion-guide":
        raise RuntimeError("Motion Guide runner sidecar schema is unsupported.")
    if (
        int(motion_sidecar.get("schema_version") or 0)
        != MOTION_GUIDE_RUNNER_SCHEMA_VERSION
    ):
        raise RuntimeError(
            "Motion Guide runner sidecar schema version is unsupported."
        )
    if _clean(motion_sidecar.get("profile")) != MOTION_GUIDE_PROFILE:
        raise RuntimeError("Motion Guide runner sidecar profile is unsupported.")
    if _clean(result.get("motion_guide_profile")) != MOTION_GUIDE_PROFILE:
        raise RuntimeError("Motion Guide runner result profile is unsupported.")
    if int(result.get("motion_guide_frame_count") or 0) != expected_frame_count:
        raise RuntimeError(
            "Motion Guide runner result frame count does not match @video1."
        )
    if int(motion_sidecar.get("frame_count") or 0) != expected_frame_count:
        raise RuntimeError("Motion Guide sidecar frame count does not match @video1.")
    for label, payload in (
        ("@video1", color_sidecar),
        ("Motion Guide", motion_sidecar),
    ):
        close(payload.get("fps"), expected_fps, f"{label} FPS")
        close(
            payload.get("start_frame"),
            expected_start_frame,
            f"{label} start frame",
        )
        close(
            payload.get("end_frame"),
            expected_end_frame,
            f"{label} end frame",
        )
        resolution = (
            payload.get("resolution")
            if isinstance(payload.get("resolution"), dict)
            else {}
        )
        if (
            int(resolution.get("width") or 0) != int(expected_width)
            or int(resolution.get("height") or 0) != int(expected_height)
        ):
            raise RuntimeError(
                f"{label} raster does not match "
                f"{expected_width}x{expected_height}."
            )
    color_camera = _clean(color_sidecar.get("camera"))
    if (
        not color_camera
        or _clean(motion_sidecar.get("camera")) != color_camera
    ):
        raise RuntimeError(
            "Motion Guide camera does not exactly match @video1."
        )
    color_signature = frame_signature(color_sidecar, "@video1")
    motion_signature = frame_signature(motion_sidecar, "Motion Guide")
    result_signature = frame_signature(
        {"frame_map": result.get("motion_guide_frame_map")},
        "Motion Guide result",
    )
    if (
        motion_signature != color_signature
        or result_signature != motion_signature
    ):
        raise RuntimeError(
            "Motion Guide time mapping does not exactly match @video1."
        )

    color_hidden_paths = sorted(
        _scene_path_key(item)
        for item in color_sidecar.get("hidden_paths", [])
        if _clean(item)
    )
    motion_hidden_paths = sorted(
        _scene_path_key(item)
        for item in motion_sidecar.get("hidden_paths", [])
        if _clean(item)
    )
    if motion_hidden_paths != color_hidden_paths:
        raise RuntimeError(
            "Motion Guide visibility does not exactly inherit @video1."
        )

    report = motion_sidecar.get("motion_guide_report")
    result_report = result.get("motion_guide_report")
    if not isinstance(report, dict) or report != result_report:
        raise RuntimeError(
            "Motion Guide report is missing or differs between result and sidecar."
        )
    required_report = {
        "profile": MOTION_GUIDE_PROFILE,
        "space": "camera_screen_normalized",
        "representation": (
            "target_neutral_core_motion_plus_visible_face_semantic_rgb"
        ),
        "source": (
            "maya_skin_influence_transform_blendshape_and_curve_driver_evaluation"
        ),
        "appearance_authority": "zero",
        "camera_authority": "zero_independent_authority",
        "motion_authority": "derived_decoder_of_video1_only",
        "visibility_policy": (
            "shared_hidden_paths_plus_target_shape_animated_dag_layer_visibility"
        ),
        "joint_selection_policy": (
            "weighted_skin_influences_then_direct_or_character_reference_core_fallback"
        ),
        "occlusion_policy": (
            "micro_face_rig_helper_and_duplicate_skeleton_points_excluded;"
            "core_body_motion_intent_preserved_through_self_occlusion;"
            "face_surface_front_facing_and_character_mesh_first_hit_only"
        ),
    }
    for field, expected in required_report.items():
        if _clean(report.get(field)) != expected:
            raise RuntimeError(
                f"Motion Guide report has unsupported {field}: "
                f"{report.get(field)!r}."
            )
    if int(report.get("target_count") or 0) <= 0:
        raise RuntimeError("Motion Guide contains no selected target.")
    if int(report.get("total_point_samples") or 0) <= 0:
        raise RuntimeError("Motion Guide contains no usable motion samples.")
    report_hidden_paths = sorted(
        _scene_path_key(item)
        for item in report.get("hidden_paths", [])
        if _clean(item)
    )
    if report_hidden_paths != color_hidden_paths:
        raise RuntimeError(
            "Motion Guide report visibility differs from @video1."
        )
    face_validation = _validate_motion_face_semantics(
        report,
        motion_signature,
    )

    if len(motion_frame_paths) != expected_frame_count:
        raise RuntimeError(
            "Motion Guide frame path count does not match @video1."
        )
    Image, _chops, _draw, UnidentifiedImageError, pillow_version = (
        _screen_space._require_pillow()
    )
    expected_size = (int(expected_width), int(expected_height))
    allowed_palette = {
        (0, 0, 0),
        (245, 245, 245),
        (0, 224, 230),
        (255, 224, 0),
        (240, 0, 210),
        (0, 235, 92),
        (255, 132, 0),
        (255, 48, 48),
        (48, 235, 80),
        (64, 112, 255),
        (70, 70, 70),
        MOTION_GUIDE_FACE_BROW_RGB,
        MOTION_GUIDE_FACE_EYELID_RGB,
        MOTION_GUIDE_FACE_MOUTH_RGB,
        MOTION_GUIDE_FACE_JAW_RGB,
    }
    face_palette = {
        MOTION_GUIDE_FACE_BROW_RGB,
        MOTION_GUIDE_FACE_EYELID_RGB,
        MOTION_GUIDE_FACE_MOUTH_RGB,
        MOTION_GUIDE_FACE_JAW_RGB,
    }
    face_rasterized_indices = set(
        face_validation["rasterized_frame_indices"]
    )
    sample_indices = sorted({
        0,
        max(0, expected_frame_count // 2),
        max(0, expected_frame_count - 1),
    })
    black_pixel_observed = False
    guide_pixel_observed = False
    face_pixel_observed = False
    sampled_colors: set[tuple[int, int, int]] = set()
    for index, frame_path in enumerate(motion_frame_paths):
        path = Path(frame_path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(
                f"Motion Guide frame {index} is missing or empty: {path}"
            )
        try:
            with Image.open(path) as image:
                if tuple(image.size) != expected_size:
                    raise RuntimeError(
                        f"Motion Guide frame {index} raster "
                        f"{tuple(image.size)!r} does not match {expected_size!r}."
                    )
                rgb_image = image.convert("RGB")
                color_counts = rgb_image.getcolors(
                    maxcolors=len(allowed_palette) + 1
                )
                if color_counts is None:
                    raise RuntimeError(
                        f"Motion Guide frame {index} contains colors outside "
                        "the target-neutral guide palette."
                    )
                pixels = {color for _count, color in color_counts}
                unexpected_colors = pixels - allowed_palette
                if unexpected_colors:
                    raise RuntimeError(
                        f"Motion Guide frame {index} contains unsupported RGB "
                        f"values: {sorted(unexpected_colors)!r}."
                    )
                has_face_pixels = bool(pixels.intersection(face_palette))
                if index in face_rasterized_indices and not has_face_pixels:
                    raise RuntimeError(
                        f"Motion Guide frame {index} declares a visible face "
                        "raster but contains no semantic face pixels."
                    )
                if index not in face_rasterized_indices and has_face_pixels:
                    raise RuntimeError(
                        f"Motion Guide frame {index} contains semantic face "
                        "pixels without a visible face raster declaration."
                    )
                face_pixel_observed = face_pixel_observed or has_face_pixels
                if index in sample_indices:
                    sampled_colors.update(pixels)
                    black_pixel_observed = (
                        black_pixel_observed or (0, 0, 0) in pixels
                    )
                    guide_pixel_observed = guide_pixel_observed or bool(
                        pixels.intersection(
                            allowed_palette - {(0, 0, 0), (70, 70, 70)}
                        )
                    )
        except UnidentifiedImageError as exc:
            raise RuntimeError(
                f"Motion Guide frame {index} is not a valid image."
            ) from exc
    if not black_pixel_observed or not guide_pixel_observed:
        raise RuntimeError(
            "Motion Guide samples must contain pure black background and "
            "at least one target-neutral guide primitive."
        )
    return {
        "profile": MOTION_GUIDE_PROFILE,
        "validated": True,
        "frame_count": expected_frame_count,
        "fps": float(expected_fps),
        "start_frame": float(expected_start_frame),
        "end_frame": float(expected_end_frame),
        "resolution": {
            "width": int(expected_width),
            "height": int(expected_height),
        },
        "camera": color_camera,
        "frame_map_match": True,
        "visibility_match": True,
        "target_count": int(report.get("target_count") or 0),
        "joint_target_count": int(report.get("joint_target_count") or 0),
        "rigid_target_count": int(report.get("rigid_target_count") or 0),
        "total_point_samples": int(report.get("total_point_samples") or 0),
        "sampled_frame_indices": sample_indices,
        "sampled_color_count": len(sampled_colors),
        "black_pixel_observed": black_pixel_observed,
        "guide_pixel_observed": guide_pixel_observed,
        "face_pixel_observed": face_pixel_observed,
        "face_semantics": {
            key: value
            for key, value in face_validation.items()
            if key != "rasterized_frame_indices"
        },
        "appearance_authority": "zero",
        "motion_authority": "derived_decoder_of_video1_only",
        "pillow_version": pillow_version,
    }


_DIAGNOSTIC_PREFIX = "[HMB_GP_Production][HMBVideoPickerLibrary]"
_LOGGER = logging.getLogger("griptape_nodes")


def _diagnostic(message: str) -> None:
    try:
        _LOGGER.info("%s %s", _DIAGNOSTIC_PREFIX, message)
    except Exception as logger_exc:
        try:
            print(f"{_DIAGNOSTIC_PREFIX} logger failure: {logger_exc}; {message}", file=sys.stderr)
        except (OSError, ValueError):
            return


def _diagnostic_exception(context: str, exc: BaseException) -> None:
    try:
        _LOGGER.error(
            "%s %s: %s",
            _DIAGNOSTIC_PREFIX,
            context,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    except Exception as logger_exc:
        try:
            print(f"{_DIAGNOSTIC_PREFIX} logger failure: {logger_exc}; {context}: {exc}", file=sys.stderr)
        except (OSError, ValueError):
            return


def _mode_set(*names: str):
    if ParameterMode is None:
        return None
    result = set()
    for name in names:
        try:
            result.add(getattr(ParameterMode, name))
        except Exception as exc:
            _diagnostic_exception(f"ParameterMode lookup failed for {name}", exc)
    return result or None


def _safe_add_parameter(node: Any, attempts: Sequence[Dict[str, Any]]) -> None:
    last: Optional[Exception] = None
    for kwargs in attempts:
        try:
            node.add_parameter(Parameter(**kwargs))
            return
        except Exception as exc:
            last = exc
    raise last or RuntimeError("Parameter creation failed")


def _get_parameter_obj(node: Any, name: str) -> Any:
    try:
        getter = getattr(node, "get_parameter_by_name", None)
        if callable(getter):
            parameter = getter(name)
            if parameter is not None:
                return parameter
    except Exception as exc:
        _diagnostic_exception(f"Parameter lookup failed for {name}", exc)
    try:
        return getattr(node, "parameters", {}).get(name)
    except Exception:
        return None


def _configure_compact_output(
    parameter: Any,
    name: str,
    output_type: str,
    display_name: str,
    *,
    hidden: bool = False,
) -> None:
    """Keep a data output connectable while hiding its read-only value editor."""
    if parameter is None:
        return
    attributes = [
        ("type", output_type),
        ("output_type", output_type),
        ("input_types", []),
        ("hide_property", True),
        ("settable", False),
    ]
    if hidden:
        attributes.append(("hide", True))
    mode = _mode_set("OUTPUT")
    if mode is not None:
        attributes.append(("allowed_modes", mode))
    else:
        attributes.extend((
            ("allow_input", False),
            ("allow_output", True),
            ("allow_property", False),
        ))
    for attribute, value in attributes:
        try:
            setattr(parameter, attribute, value)
        except Exception as exc:
            _diagnostic_exception(f"Output {name} attribute configuration failed for {attribute}", exc)
    try:
        options = dict(getattr(parameter, "ui_options", {}) or {})
        if hidden:
            options.update({
                "display_name": "",
                "compact": True,
                "height": 1,
                "min_height": 0,
                "max_height": 1,
                "is_full_width": True,
                "hide": True,
                "hide_property": True,
                "hide_label": True,
                "hide_handles": True,
            })
        else:
            options.update({
                "display_name": display_name,
                "compact": True,
                "height": 24,
                "is_full_width": False,
                "hide_property": True,
            })
            options.pop("hide", None)
            options.pop("hide_handles", None)
            options.pop("hide_label", None)
        setattr(parameter, "ui_options", options)
    except Exception as exc:
        _diagnostic_exception(f"Output {name} UI option configuration failed", exc)


def _add_output(
    node: Any,
    name: str,
    output_type: str,
    default_value: Any,
    tooltip: str,
    *,
    display_name: str | None = None,
    hidden: bool = False,
) -> None:
    clean_display_name = str(display_name or name)
    if parameter_exists(node, name):
        _configure_compact_output(
            _get_parameter_obj(node, name),
            name,
            output_type,
            clean_display_name,
            hidden=hidden,
        )
        return
    base: Dict[str, Any] = {
        "name": name,
        "default_value": default_value,
        "type": output_type,
        "output_type": output_type,
        "input_types": [],
        "settable": False,
        "hide_property": True,
        "tooltip": tooltip,
        "ui_options": {
            "display_name": "" if hidden else clean_display_name,
            "compact": True,
            "height": 1 if hidden else 24,
            "min_height": 0 if hidden else 24,
            "max_height": 1 if hidden else 24,
            "is_full_width": bool(hidden),
            "hide": bool(hidden),
            "hide_property": True,
            "hide_label": bool(hidden),
            "hide_handles": bool(hidden),
        },
    }
    mode = _mode_set("OUTPUT")
    if mode is not None:
        base["allowed_modes"] = mode
    attempts = [base]
    without_settable = dict(base)
    without_settable.pop("settable", None)
    attempts.append(without_settable)
    legacy = {
        "name": name,
        "default_value": default_value,
        "type": output_type,
        "output_type": output_type,
        "input_types": [],
        "allow_input": False,
        "allow_output": True,
        "allow_property": False,
        "settable": False,
        "hide_property": True,
        "tooltip": tooltip,
        "ui_options": {
            "display_name": "" if hidden else clean_display_name,
            "compact": True,
            "height": 1 if hidden else 24,
            "min_height": 0 if hidden else 24,
            "max_height": 1 if hidden else 24,
            "is_full_width": bool(hidden),
            "hide": bool(hidden),
            "hide_property": True,
            "hide_label": bool(hidden),
            "hide_handles": bool(hidden),
        },
    }
    attempts.append(legacy)
    legacy_without_settable = dict(legacy)
    legacy_without_settable.pop("settable", None)
    attempts.append(legacy_without_settable)
    _safe_add_parameter(node, attempts)
    _configure_compact_output(
        _get_parameter_obj(node, name),
        name,
        output_type,
        clean_display_name,
        hidden=hidden,
    )




def _add_picker_output(node: Any) -> None:
    _add_output(
        node,
        "PICKER_OUT",
        "str",
        "",
        "Maya HMB binding report for HMBPromptLibrary PICKER_IN.",
        display_name="PICKER OUT",
        hidden=True,
    )


def _add_video_output(node: Any) -> None:
    """Register the sole ordered media-list output for the generator."""
    _add_output(
        node,
        VIDEO_OUTPUT_PARAMETER,
        "list[str]",
        [],
        (
            "Ordered selected video media list. Its order exactly matches the "
            "selected videos in PICKER_OUT and transient @video1 through @video10."
        ),
        display_name="VIDEO OUT",
        hidden=True,
    )


def _add_shot_picker_output(node: Any) -> None:
    """Register the hidden compact dependency used by automatic Shot routing."""
    _add_output(
        node,
        SHOT_PICKER_OUTPUT_PARAMETER,
        "dict",
        {},
        "Compact Shot catalog dependency. Media is resolved through the private atomic snapshot API.",
        display_name="SHOT PICKER OUT",
        hidden=True,
    )
    parameter = _get_parameter_obj(node, SHOT_PICKER_OUTPUT_PARAMETER)
    if parameter is not None:
        for attribute in ("hide", "hide_property"):
            try:
                setattr(parameter, attribute, True)
            except Exception:
                pass
        options = getattr(parameter, "ui_options", None)
        if isinstance(options, dict):
            options.update({
                "display_name": "",
                "height": 1,
                "min_height": 0,
                "max_height": 1,
                "is_full_width": True,
                "hide": True,
                "hide_property": True,
                "hide_label": True,
                "hide_handles": True,
            })
            try:
                parameter.ui_options = options
            except Exception:
                pass


def _add_maya_scene_picker(node: Any) -> None:
    """Register MAYA_SCENE using the current official Parameter + FileSystemPicker pattern.

    Avoid the legacy allow_input/allow_output/allow_property flags here. On recent
    Griptape Nodes builds those fields can coexist with allowed_modes but produce a
    property that renders correctly while its value-change lifecycle is not forwarded.
    """
    if parameter_exists(node, "MAYA_SCENE"):
        _configure_hidden_maya_scene_parameter(
            _get_parameter_obj(node, "MAYA_SCENE")
        )
        return
    tooltip = (
        "Select one Maya .mb or .ma scene. READ loads cameras, exact frame range, "
        "FPS, and Outliner metadata with the highest installed Maya; it does not render video."
    )
    trait = None
    if FileSystemPicker is not None:
        # Keep every compatibility attempt extension-constrained.  The former
        # unfiltered fallback could succeed on newer Griptape builds and turn
        # this Maya picker into the same generic/video browser used by Preview.
        for trait_kwargs in (
            {"allow_files": True, "allow_directories": False, "multiple": False, "file_types": [".mb", ".ma"]},
            {"allow_files": True, "file_types": [".mb", ".ma"]},
        ):
            try:
                trait = FileSystemPicker(**trait_kwargs)
                break
            except Exception:
                continue

    if ParameterString is not None:
        parameter = ParameterString(
            name="MAYA_SCENE",
            default_value="",
            tooltip=tooltip,
            placeholder_text=r"C:\path\shot.mb",
        )
        add_trait = getattr(parameter, "add_trait", None)
        if trait is not None and callable(add_trait):
            add_trait(trait)
        ui_options = getattr(parameter, "ui_options", None)
        if isinstance(ui_options, dict):
            ui_options.update({
                "display_name": "MAYA_SCENE",
                "placeholder_text": r"C:\path\shot.mb",
                "is_full_width": True,
            })
    else:
        kwargs: Dict[str, Any] = {
            "name": "MAYA_SCENE",
            "default_value": "",
            "type": "str",
            "tooltip": tooltip,
            "ui_options": {
                "display_name": "MAYA_SCENE",
                "placeholder_text": r"C:\path\shot.mb",
                "is_full_width": True,
            },
        }
        mode = _mode_set("INPUT", "PROPERTY")
        if mode is not None:
            kwargs["allowed_modes"] = mode
        if trait is not None:
            kwargs["traits"] = {trait}
        parameter = Parameter(**kwargs)
    node.add_parameter(parameter)
    _configure_hidden_maya_scene_parameter(parameter)


def _configure_hidden_maya_scene_parameter(parameter: Any) -> None:
    """Keep the durable Maya path without consuming an adaptive host row.

    The expanded Picker dashboard owns Browse/READ.  Rendering the native
    FileSystemPicker as a second visible row lets Griptape hide MAYA, COMMAND,
    and STATE together before the saved dashboard can mount.
    """

    if parameter is None:
        return
    for attribute, setting in (
        ("hide", True),
        ("hide_property", True),
        ("serializable", True),
    ):
        try:
            setattr(parameter, attribute, setting)
        except Exception:
            pass
    try:
        options = dict(getattr(parameter, "ui_options", {}) or {})
        options.update({
            "display_name": "",
            "height": 0,
            "min_height": 0,
            "max_height": 0,
            "hide": True,
            "hide_property": True,
            "hide_label": True,
            "hide_handles": True,
            "is_full_width": True,
            "expandable": False,
            "resizable": False,
        })
        parameter.ui_options = options
    except Exception as exc:
        _diagnostic_exception("Maya scene transport row configuration failed", exc)


def _remove_parameter(node: Any, name: str) -> None:
    """Remove a retired parameter through the runtime API and local stubs."""
    parameter = _get_parameter_obj(node, name)
    if parameter is not None:
        removed = False
        for method_name in (
            "remove_parameter_element",
            "remove_parameter_element_by_name",
            "remove_parameter",
            "delete_parameter",
            "remove_parameter_by_name",
        ):
            method = getattr(node, method_name, None)
            if not callable(method):
                continue
            for argument in (parameter, name):
                try:
                    method(argument)
                    removed = True
                    break
                except TypeError:
                    continue
                except Exception:
                    continue
            if removed:
                break
    for attr_name in (
        "parameters",
        "parameter_values",
        "parameter_input_values",
        "parameter_output_values",
    ):
        mapping = getattr(node, attr_name, None)
        if isinstance(mapping, dict):
            mapping.pop(name, None)
    root = getattr(node, "root_ui_element", None)
    children = getattr(root, "children", None) if root is not None else None
    if children is None and root is not None:
        children = getattr(root, "_children", None)
    if isinstance(children, list):
        children[:] = [
            child for child in children if getattr(child, "name", None) != name
        ]


def _retire_legacy_video_slot_outputs(node: Any) -> None:
    """Remove the former VIDEO1_OUT..VIDEO10_OUT fixed-port contract."""
    for slot in range(1, MAX_SELECTED_VIDEOS + 1):
        _remove_parameter(node, f"VIDEO{slot}_OUT")


def _reorder_video_picker_parameters(node: Any, active_count: int = 0) -> None:
    """Keep the two public outputs above the Picker dashboard."""
    del active_count
    preferred = [
        "PICKER_OUT",
        VIDEO_OUTPUT_PARAMETER,
        SHOT_PICKER_OUTPUT_PARAMETER,
        "MAYA_SCENE",
        WIDGET_COMMAND_PARAMETER,
        WIDGET_STATE_PARAMETER,
    ]
    try:
        root = getattr(node, "root_ui_element", None)
        children = getattr(root, "children", None) if root is not None else None
        if children is None and root is not None:
            children = getattr(root, "_children", None)
        if isinstance(children, list):
            current_names = [getattr(child, "name", None) for child in children]
            current_names = [name for name in current_names if isinstance(name, str) and name]
            preferred_names = [name for name in preferred if name in current_names]
            preferred_set = set(preferred_names)
            desired_names = preferred_names + [name for name in current_names if name not in preferred_set]
            if desired_names != current_names:
                reorder = getattr(node, "reorder_elements", None)
                if callable(reorder):
                    reorder(desired_names)
                else:
                    by_name = {getattr(child, "name", None): child for child in children}
                    ordered = [by_name[name] for name in desired_names if name in by_name]
                    ordered_ids = {id(child) for child in ordered}
                    ordered.extend(child for child in children if id(child) not in ordered_ids)
                    children[:] = ordered
    except Exception as exc:
        _diagnostic_exception("VideoPicker UI element reorder failed", exc)
    try:
        parameters = getattr(node, "parameters", None)
        if isinstance(parameters, dict):
            ordered_items = [(name, parameters[name]) for name in preferred if name in parameters]
            used = {name for name, _value in ordered_items}
            ordered_items.extend((name, value) for name, value in parameters.items() if name not in used)
            parameters.clear()
            parameters.update(ordered_items)
    except Exception as exc:
        _diagnostic_exception("VideoPicker parameter-map reorder failed", exc)


def _default_widget_state() -> Dict[str, Any]:
    picker_workspace_uuid = PICKER_DEFAULT_WORKSPACE_UUID
    return {
        "schema": "maya-video-picker-state",
        "state_revision": 0,
        "state_writer": "",
        "writer_runtime_instance_id": "",
        "writer_lifecycle_generation": 0,
        "state_published_at_ms": 0,
        "frontend_seen_revision": 0,
        "scene_stage": "EMPTY",
        "scene_draft_path": "",
        "marker_catalog": MARKER_CATALOG,
        "marker_catalog_version": int(MARKER_CATALOG["version"]),
        "scene_request_path": "",
        "mode": "maya",
        "status": "READY",
        "message": "Browse to a Maya scene, then press READ.",
        "video_path": "",
        "video_url": "",
        "original_video_path": "",
        "original_video_url": "",
        "original_metadata": {},
        # Generation choices are inert state.  Maya/FFmpeg starts only from the
        # explicit Generate Playblast command; toggling a checkbox never runs it.
        "original_enabled": False,
        "mask_enabled": True,
        "mask_authoring_slot": PRIMARY_COLOR_VIDEO_SLOT,
        "original_preview_enabled": False,
        "depth_enabled": False,
        "motion_guide_enabled": False,
        "depth_video_slot": 0,
        "motion_guide_video_slot": 0,
        "snapshot_active": False,
        "snapshot_frame": 0.0,
        "snapshot_video_slot": 0,
        "snapshot_data_uri": "",
        "snapshot_path": "",
        "snapshot_url": "",
        "snapshot_sha256": "",
        "active_snapshot_uid": "",
        "viewport_mode": "video",
        "snapshot_request_video_uid": "",
        "snapshots": [],
        "scene_path": "",
        "native_read_ready": False,
        "native_read_mode": "",
        "native_source_version": "",
        "native_metadata": {},
        "camera": "",
        "source_fps": 0.0,
        "output_fps": OUTPUT_FPS,
        "output_width": OUTPUT_WIDTH,
        "output_height": OUTPUT_HEIGHT,
        "source_frame_count": 0,
        "output_frame_count": 0,
        "decoded_frame_count": 0,
        "source_duration_seconds": 0.0,
        "output_duration_seconds": 0.0,
        "frame_metadata": {},
        "start_frame": 0.0,
        "end_frame": 0.0,
        "current_frame": 0.0,
        "has_maya_frame_range": False,
        "markers": [],
        "warnings": [],
        "activity_log": [],
        "activity_log_text": "",
        "activity_log_text_user_edited": False,
        "activity_log_cleared": False,
        "maya_executable": "",
        "maya_version": "",
        "maya_available": False,
        "active_process_pid": 0,
        "active_process_kind": "",
        "last_log_path": "",
        "log_folder": "",
        "operation_kind": "",
        "operation_video_slot": 0,
        "operation_started_at_ms": 0,
        "operation_finished_at_ms": 0,
        "last_operation_seconds": 0.0,
        "run_id": "",
        "operation_id": "",
        "operation_input_digest": "",
        "operation_scene_fingerprint": "",
        "operation_invalidated": False,
        "operation_invalidation_reason": "",
        "python_core_loaded": False,
        "python_core_path": "",
        "runtime_instance_id": "",
        "scene_request_id": "",
        "scene_request_source": "",
        "scene_request_status": "",
        "selected_video_slot": 1,
        "active_slot_count": 1,
        "selected_video_count": 0,
        "max_selected_videos": MAX_REPRESENTATIVE_VIDEOS,
        "selection_id": "",
        "preview_video_uid": "",
        "selected_video_uid": "",
        "selected_video_path": "",
        "video_library_version": 1,
        "pending_action": "",
        "pending_action_id": "",
        "backend_ack_action_id": "",
        "lower_panel_ratio": 0.34,
        "main_split_ratio": 0.64,
        "right_split_ratio": 0.42,
        "node_width": 0,
        "node_height": 0,
        # Python mirrors the independently retained metadata geometry so a
        # compact cold mount can restore the saved expanded height on demand.
        "expanded_node_size": {
            "width": PICKER_START_WIDTH,
            "height": PICKER_START_HEIGHT,
        },
        "outliner_panel_height": 0,
        "viewport_panel_height": 0,
        "right_section_heights": {
            "settings": 217,
            "color": 628,
            "log": 208,
        },
        "ui_layout_version": 6,
        "ui_theme": "P",
        "workspace_view": "outliner",
        "selected_outliner_path": "",
        "selected_outliner_name": "",
        "selected_outliner_uuid": "",
        "selected_color": "",
        "outliner_nodes": [],
        "outliner_expanded": [],
        "cameras": [],
        "selected_camera": "",
        "language": "ko",
        "outliner_search": "",
        "videos": [],
        "slot_assignments": [{"video_slot": 1, "bindings": []}],
        "slot_visibility": [{"video_slot": 1, "hidden_paths": []}],
        "slot_recovery_fallbacks": [],
        "shot_publisher_instance_uuid": "",
        "channel_uuid": "",
        "shot_uuid": "",
        "shot_number": 0,
        "shot_name": "",
        "shot_selections": [],
        # Last validated ImageAsset catalog authority. These fields survive
        # reload/publisher loss so the first callback in a new runtime cannot
        # replay an older catalog or authorize destructive Shot removal.
        "accepted_shot_catalog_publisher_instance_uuid": "",
        "accepted_shot_catalog_channel_uuid": "",
        "accepted_shot_catalog_generation": 0,
        "accepted_shot_catalog_metadata_sha256": "",
        # ImageAsset owns Shot existence.  A standalone/new Picker starts with
        # exactly one local 01 workspace; a validated ImageAsset catalog later
        # expands this list to its actual 1..5 Shot count.
        "picker_shots": [{
            "workspace_uuid": picker_workspace_uuid,
            "number": 1,
            "name": "Shot 1",
            "custom_name": False,
            "revision": 0,
            "bound_shot_uuid": "",
            "video_asset_uids": [],
            "selected_video_uids": [],
            "preview_video_uid": "",
            "scene_draft_path": "",
            "current_frame": 0.0,
            "viewport_mode": "video",
            "active_snapshot_uid": "",
            "selected_video_slot": 1,
            "authoring_context": {
                "version": 1,
                "scene_stage": "EMPTY",
                "scene_draft_path": "",
                "scene_request_path": "",
                "scene_path": "",
                "native_read_ready": False,
                "native_metadata": {},
                "selected_camera": "",
                "cameras": [],
                "selected_outliner_path": "",
                "selected_outliner_name": "",
                "selected_outliner_uuid": "",
                "selected_color": "",
                "outliner_nodes": [],
                "outliner_expanded": [],
                "outliner_search": "",
                "slot_assignments": [{"video_slot": 1, "bindings": []}],
                "slot_visibility": [{"video_slot": 1, "hidden_paths": []}],
            },
        }],
        "active_picker_shot_uuid": picker_workspace_uuid,
        "picker_legacy_membership_fallbacks": {},
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sha256_canonical(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _uuid_text(value: Any) -> str:
    try:
        return str(uuid.UUID(_clean(value)))
    except (ValueError, TypeError, AttributeError):
        return ""


def _normalize_shot_selection_fields(state: Dict[str, Any]) -> None:
    """Normalize only durable subscriber identity and per-shot video membership."""
    state["shot_publisher_instance_uuid"] = _uuid_text(
        state.get("shot_publisher_instance_uuid")
    )
    state["channel_uuid"] = _uuid_text(state.get("channel_uuid"))
    state["shot_uuid"] = _uuid_text(state.get("shot_uuid"))
    try:
        shot_number = int(state.get("shot_number") or 0)
    except (TypeError, ValueError, OverflowError):
        shot_number = 0
    state["shot_number"] = shot_number if 1 <= shot_number <= SHOT_ROUTING_MAX_SHOTS else 0
    state["shot_name"] = _clean(state.get("shot_name"))[:128]

    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    raw_rows = state.get("shot_selections")
    for raw in raw_rows[:SHOT_ROUTING_MAX_SHOTS] if isinstance(raw_rows, list) else []:
        if not isinstance(raw, dict):
            continue
        shot_uuid = _uuid_text(raw.get("shot_uuid"))
        if not shot_uuid or shot_uuid in seen:
            continue
        seen.add(shot_uuid)
        try:
            number = int(raw.get("number") or len(rows) + 1)
        except (TypeError, ValueError, OverflowError):
            number = len(rows) + 1
        number = max(1, min(SHOT_ROUTING_MAX_SHOTS, number))
        try:
            revision = max(0, int(raw.get("revision") or 0))
        except (TypeError, ValueError, OverflowError):
            revision = 0
        selected_uids: List[str] = []
        for value in (
            raw.get("selected_video_uids")
            if isinstance(raw.get("selected_video_uids"), list)
            else []
        ):
            uid = _clean(value)
            if uid and uid not in selected_uids:
                selected_uids.append(uid)
            if len(selected_uids) >= MAX_SELECTED_VIDEOS:
                break
        rows.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": _clean(raw.get("name"))[:128] or f"Shot {number}",
                "revision": revision,
                "selected_video_uids": selected_uids,
            }
        )
    if state["shot_uuid"] and state["shot_uuid"] not in seen:
        number = state["shot_number"] or min(len(rows) + 1, SHOT_ROUTING_MAX_SHOTS)
        rows.append(
            {
                "shot_uuid": state["shot_uuid"],
                "number": number,
                "name": state["shot_name"] or f"Shot {number}",
                "revision": 0,
                "selected_video_uids": [],
            }
        )
        rows = rows[:SHOT_ROUTING_MAX_SHOTS]
    # A compact catalog is an option source, not an activation signal.  A
    # blank durable Shot identity is the independent ``Only`` mode and must
    # stay blank until the user explicitly chooses one of the advertised
    # rows.
    if not state["shot_uuid"]:
        state["shot_number"] = 0
        state["shot_name"] = ""
    state["shot_selections"] = rows


def _normalize_shot_catalog_watermark_fields(state: Dict[str, Any]) -> None:
    """Normalize the durable last-accepted ImageAsset catalog watermark."""

    publisher = _uuid_text(
        state.get("accepted_shot_catalog_publisher_instance_uuid")
    )
    channel = _uuid_text(state.get("accepted_shot_catalog_channel_uuid"))
    try:
        generation = max(
            0,
            int(state.get("accepted_shot_catalog_generation") or 0),
        )
    except (TypeError, ValueError, OverflowError):
        generation = 0
    metadata_sha256 = _clean(
        state.get("accepted_shot_catalog_metadata_sha256")
    ).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", metadata_sha256):
        metadata_sha256 = ""
    if not (publisher and channel and generation > 0 and metadata_sha256):
        publisher = ""
        channel = ""
        generation = 0
        metadata_sha256 = ""
    state.update({
        "accepted_shot_catalog_publisher_instance_uuid": publisher,
        "accepted_shot_catalog_channel_uuid": channel,
        "accepted_shot_catalog_generation": generation,
        "accepted_shot_catalog_metadata_sha256": metadata_sha256,
    })


def _shot_catalog_deletion_watermark_matches(
    state: Dict[str, Any],
    remote_rows: Sequence[Dict[str, Any]],
) -> bool:
    """Return whether rows exactly match the durable validated catalog."""

    publisher = _uuid_text(state.get("shot_publisher_instance_uuid"))
    channel = _uuid_text(state.get("channel_uuid"))
    watermark_publisher = _uuid_text(
        state.get("accepted_shot_catalog_publisher_instance_uuid")
    )
    watermark_channel = _uuid_text(
        state.get("accepted_shot_catalog_channel_uuid")
    )
    try:
        generation = int(
            state.get("accepted_shot_catalog_generation") or 0
        )
    except (TypeError, ValueError, OverflowError):
        return False
    metadata_sha256 = _clean(
        state.get("accepted_shot_catalog_metadata_sha256")
    ).casefold()
    if not (
        publisher
        and channel
        and publisher == watermark_publisher
        and channel == watermark_channel
        and generation > 0
        and re.fullmatch(r"[0-9a-f]{64}", metadata_sha256)
        and remote_rows
    ):
        return False
    shots = [
        {
            "shot_uuid": _uuid_text(row.get("shot_uuid")),
            "number": int(row.get("number") or 0),
            "name": _clean(row.get("name"))[:128],
            "revision": max(0, int(row.get("revision") or 0)),
        }
        for row in remote_rows
    ]
    return metadata_sha256 == _sha256_canonical({
        "channel_uuid": channel,
        "generation": generation,
        "shots": shots,
    })


def _picker_selected_video_uids(state: Dict[str, Any]) -> List[str]:
    selected = [
        item
        for item in state.get("videos", [])
        if isinstance(item, dict) and bool(item.get("selected"))
    ]
    selected.sort(key=lambda item: _positive_int(item.get("selection_order")))
    result: List[str] = []
    for item in selected:
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        if uid and uid not in result:
            result.append(uid)
        if len(result) >= MAX_SELECTED_VIDEOS:
            break
    return result


def _picker_representative_video_uids(
    values: Any,
    preview_video_uid: Any = "",
    known_video_uids: Optional[set[str]] = None,
) -> List[str]:
    """Return the bounded durable Shot order; preview remains a separate cursor."""

    candidates: List[str] = []
    for raw_uid in values if isinstance(values, (list, tuple)) else []:
        uid = _clean(raw_uid)
        if (
            uid
            and (known_video_uids is None or uid in known_video_uids)
            and uid not in candidates
        ):
            candidates.append(uid)
        if len(candidates) >= MAX_REPRESENTATIVE_VIDEOS:
            break
    return candidates


def _picker_workspace_uuid_for_number(number: int) -> str:
    """Return one stable local identity for a legacy positional workspace."""
    normalized_number = max(1, min(SHOT_ROUTING_MAX_SHOTS, int(number or 1)))
    if normalized_number == 1:
        return PICKER_DEFAULT_WORKSPACE_UUID
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"hmb-video-picker-workspace:{normalized_number}",
    ))


def _picker_workspace_uuid_for_bound_shot(shot_uuid: Any) -> str:
    """Return a stable workspace identity for a newly discovered Image Shot."""

    normalized = _uuid_text(shot_uuid)
    if not normalized:
        return ""
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"hmb-video-picker-image-shot:{normalized}",
    ))


PICKER_AUTHORING_CONTEXT_VERSION = 1
_PICKER_AUTHORING_CONTEXT_FIELDS = (
    "scene_stage", "scene_draft_path", "scene_request_path", "scene_path",
    "scene_request_id", "scene_request_source", "scene_request_status",
    "native_read_ready", "native_read_mode", "native_source_version",
    "native_metadata", "camera", "selected_camera", "cameras",
    "source_fps", "output_fps", "output_width", "output_height",
    "source_frame_count", "output_frame_count", "decoded_frame_count",
    "source_duration_seconds", "output_duration_seconds", "frame_metadata",
    "start_frame", "end_frame", "current_frame", "has_maya_frame_range",
    "workspace_view", "selected_outliner_path", "selected_outliner_name",
    "selected_outliner_uuid", "selected_color", "outliner_nodes",
    "outliner_expanded", "outliner_search", "slot_assignments",
    "slot_visibility", "markers", "original_video_path",
    "original_video_url", "original_metadata", "original_preview_enabled",
    "status", "message",
)


def _empty_picker_authoring_context() -> Dict[str, Any]:
    return {
        "version": PICKER_AUTHORING_CONTEXT_VERSION,
        "scene_stage": "EMPTY",
        "scene_draft_path": "",
        "scene_request_path": "",
        "scene_path": "",
        "scene_request_id": "",
        "scene_request_source": "",
        "scene_request_status": "",
        "native_read_ready": False,
        "native_read_mode": "",
        "native_source_version": "",
        "native_metadata": {},
        "camera": "",
        "selected_camera": "",
        "cameras": [],
        "source_fps": 0.0,
        "output_fps": OUTPUT_FPS,
        "output_width": OUTPUT_WIDTH,
        "output_height": OUTPUT_HEIGHT,
        "source_frame_count": 0,
        "output_frame_count": 0,
        "decoded_frame_count": 0,
        "source_duration_seconds": 0.0,
        "output_duration_seconds": 0.0,
        "frame_metadata": {},
        "start_frame": 0.0,
        "end_frame": 0.0,
        "current_frame": 0.0,
        "has_maya_frame_range": False,
        "workspace_view": "outliner",
        "selected_outliner_path": "",
        "selected_outliner_name": "",
        "selected_outliner_uuid": "",
        "selected_color": "",
        "outliner_nodes": [],
        "outliner_expanded": [],
        "outliner_search": "",
        "slot_assignments": [{"video_slot": 1, "bindings": []}],
        "slot_visibility": [{"video_slot": 1, "hidden_paths": []}],
        "markers": [],
        "original_video_path": "",
        "original_video_url": "",
        "original_metadata": {},
        "original_preview_enabled": False,
        "status": "READY",
        "message": "Browse to a Maya scene, then press READ.",
    }


def _normalize_picker_authoring_context(value: Any) -> Dict[str, Any]:
    defaults = _empty_picker_authoring_context()
    source = value if isinstance(value, dict) else {}
    context = copy.deepcopy(defaults)
    for key in _PICKER_AUTHORING_CONTEXT_FIELDS:
        if key in source:
            context[key] = copy.deepcopy(source[key])
    context["version"] = PICKER_AUTHORING_CONTEXT_VERSION
    for key in (
        "scene_stage", "scene_request_id", "scene_request_source",
        "scene_request_status", "native_read_mode", "native_source_version",
        "camera", "selected_camera", "workspace_view",
        "selected_outliner_path", "selected_outliner_name",
        "selected_outliner_uuid", "selected_color", "outliner_search",
        "original_video_path", "original_video_url", "status", "message",
    ):
        context[key] = _clean(context.get(key))
    for key in ("scene_draft_path", "scene_request_path", "scene_path"):
        context[key] = _maya_scene_path_text(context.get(key))
    for key in ("native_read_ready", "has_maya_frame_range", "original_preview_enabled"):
        context[key] = bool(context.get(key))
    for key in (
        "source_fps", "output_fps", "output_width", "output_height",
        "source_frame_count", "output_frame_count", "decoded_frame_count",
        "source_duration_seconds", "output_duration_seconds", "start_frame",
        "end_frame", "current_frame",
    ):
        try:
            numeric = float(context.get(key) or 0.0)
            context[key] = numeric if math.isfinite(numeric) else defaults[key]
        except Exception:
            context[key] = defaults[key]
    for key in ("native_metadata", "frame_metadata", "original_metadata"):
        context[key] = (
            copy.deepcopy(context.get(key))
            if isinstance(context.get(key), dict)
            else {}
        )
    for key in (
        "cameras", "outliner_nodes", "outliner_expanded", "slot_assignments",
        "slot_visibility", "markers",
    ):
        context[key] = (
            copy.deepcopy(context.get(key))
            if isinstance(context.get(key), list)
            else []
        )
    return context


def _picker_authoring_context_from_state(state: Any) -> Dict[str, Any]:
    source = state if isinstance(state, dict) else {}
    context = _empty_picker_authoring_context()
    for key in _PICKER_AUTHORING_CONTEXT_FIELDS:
        if key in source:
            context[key] = copy.deepcopy(source[key])
    return _normalize_picker_authoring_context(context)


def _apply_picker_authoring_context(
    state: Dict[str, Any],
    value: Any,
) -> None:
    context = _normalize_picker_authoring_context(value)
    for key in _PICKER_AUTHORING_CONTEXT_FIELDS:
        state[key] = copy.deepcopy(context[key])


def _restore_picker_workspace_projection(
    state: Dict[str, Any],
    workspace: Any,
) -> bool:
    """Restore one durable workspace before global compatibility projection.

    ``_normalize_picker_workspace_fields`` intentionally mirrors the active
    workspace through legacy top-level controls.  When the previous active
    Shot was just deleted, those controls still belong to the removed row and
    must be replaced before normalization selects a surviving fallback.
    """

    if not isinstance(state, dict) or not isinstance(workspace, dict):
        return False
    workspace_uuid = _uuid_text(workspace.get("workspace_uuid"))
    if not workspace_uuid:
        return False
    try:
        current_frame = float(workspace.get("current_frame") or 0.0)
        if not math.isfinite(current_frame):
            current_frame = 0.0
    except Exception:
        current_frame = 0.0
    try:
        selected_video_slot = max(
            1,
            int(workspace.get("selected_video_slot") or 1),
        )
    except Exception:
        selected_video_slot = 1
    preview_video_uid = _clean(workspace.get("preview_video_uid"))
    selected_order = {
        _clean(uid): index
        for index, uid in enumerate(
            workspace.get("selected_video_uids", []),
            start=1,
        )
        if _clean(uid)
    }
    projected_videos: List[Dict[str, Any]] = []
    for raw in state.get("videos", []):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        order = selected_order.get(uid, 0)
        item["selected"] = bool(order)
        item["selection_order"] = order
        item["video_slot"] = order
        if isinstance(item.get("frame_metadata"), dict):
            item["frame_metadata"] = dict(item["frame_metadata"])
            item["frame_metadata"]["video_slot"] = (
                f"@video{order}" if order else ""
            )
        projected_videos.append(item)
    state.update({
        "active_picker_shot_uuid": workspace_uuid,
        "videos": projected_videos,
        "active_slot_count": max(1, len(selected_order)),
        "selected_video_count": len(selected_order),
        "preview_video_uid": preview_video_uid,
        "selected_video_uid": preview_video_uid,
        "scene_draft_path": _maya_scene_path_text(
            workspace.get("scene_draft_path")
        ),
        "current_frame": current_frame,
        "viewport_mode": (
            "snapshot"
            if _clean(workspace.get("viewport_mode")).lower() == "snapshot"
            else "video"
        ),
        "active_snapshot_uid": _clean(
            workspace.get("active_snapshot_uid")
        ),
        "selected_video_slot": selected_video_slot,
    })
    _apply_picker_authoring_context(
        state,
        workspace.get("authoring_context"),
    )
    return True


def _new_picker_workspace_row(
    number: int,
    *,
    bound_shot_uuid: str = "",
    video_asset_uids: Optional[Sequence[str]] = None,
    selected_video_uids: Optional[Sequence[str]] = None,
    preview_video_uid: str = "",
    state: Optional[Dict[str, Any]] = None,
    workspace_uuid: str = "",
) -> Dict[str, Any]:
    source = state if isinstance(state, dict) else {}
    try:
        normalized_number = max(
            1,
            min(SHOT_ROUTING_MAX_SHOTS, int(number or 1)),
        )
    except Exception:
        normalized_number = 1
    try:
        current_frame = float(source.get("current_frame") or 0.0)
        if not math.isfinite(current_frame):
            current_frame = 0.0
    except Exception:
        current_frame = 0.0
    try:
        selected_video_slot = max(
            1,
            int(source.get("selected_video_slot") or 1),
        )
    except Exception:
        selected_video_slot = 1
    representative_uids = _picker_representative_video_uids(
        list(selected_video_uids or []),
        preview_video_uid,
    )
    asset_uids = _picker_representative_video_uids(
        list(video_asset_uids or selected_video_uids or []),
    )
    representative_uids = [
        uid for uid in representative_uids if uid in set(asset_uids)
    ]
    requested_preview_uid = _clean(preview_video_uid)
    # Output membership and the Loader preview cursor are independent. Keep a
    # valid owned preview even when that card is not selected as an @video
    # representative; name-click selection must never stop viewport playback.
    representative_uid = (
        requested_preview_uid
        if requested_preview_uid in asset_uids
        else (representative_uids[0] if representative_uids else "")
    )
    return {
        "workspace_uuid": (
            _uuid_text(workspace_uuid)
            or _picker_workspace_uuid_for_number(normalized_number)
        ),
        "number": normalized_number,
        "name": f"Shot {normalized_number}",
        "custom_name": False,
        "revision": 0,
        "bound_shot_uuid": _uuid_text(bound_shot_uuid),
        "video_asset_uids": asset_uids,
        "selected_video_uids": representative_uids,
        "preview_video_uid": representative_uid,
        "scene_draft_path": _maya_scene_path_text(source.get("scene_draft_path")),
        "current_frame": current_frame,
        "viewport_mode": (
            "snapshot"
            if _clean(source.get("viewport_mode")).lower() == "snapshot"
            else "video"
        ),
        "active_snapshot_uid": _clean(source.get("active_snapshot_uid")),
        "selected_video_slot": selected_video_slot,
        "authoring_context": _picker_authoring_context_from_state(source),
    }


def _normalize_picker_workspace_fields(
    state: Dict[str, Any],
    raw_picker_shots: Any,
    *,
    picker_shots_present: bool,
) -> None:
    """Normalize ImageAsset-sized, independently owned video workspaces.

    ``video_asset_uids`` is the durable ownership list for a row and
    ``selected_video_uids`` is only its ordered output subset. Legacy one-page
    states migrate to Shot 1 only. A validated ImageAsset catalog owns visible
    Shot existence; rows are matched by ``bound_shot_uuid`` so renumbering never
    moves media to another Shot. Merely losing a publisher is not an
    authoritative deletion, so last-known non-empty/bound rows remain durable.
    """

    catalog = [
        dict(item)
        for item in state.get("videos", [])
        if isinstance(item, dict)
        and _clean(item.get("video_uid") or item.get("source_uid"))
    ]
    remote_rows = [
        row
        for row in state.get("shot_selections", [])
        if isinstance(row, dict) and _uuid_text(row.get("shot_uuid"))
    ]
    catalog_present = bool(
        state.get("shot_publisher_instance_uuid")
        and state.get("channel_uuid")
        and remote_rows
    )
    # The remote rows may shape a fresh/unbound view, but only a catalog whose
    # exact generation+metadata hash matches the durable accepted watermark may
    # delete an existing bound workspace or any media it owns.
    catalog_authoritative = bool(
        catalog_present
        and _shot_catalog_deletion_watermark_matches(state, remote_rows)
    )
    remote_rows.sort(key=lambda row: int(row.get("number") or 0))
    remote_by_uuid = {
        _uuid_text(row.get("shot_uuid")): row for row in remote_rows
    }
    source_rows = (
        raw_picker_shots
        if picker_shots_present and isinstance(raw_picker_shots, list)
        else []
    )
    valid_source_rows = [
        raw for raw in source_rows[:SHOT_ROUTING_MAX_SHOTS]
        if isinstance(raw, dict)
    ]
    legacy_one_page = not picker_shots_present or (
        len(valid_source_rows) == 1
        and not _uuid_text(valid_source_rows[0].get("bound_shot_uuid"))
    )

    target_rows: List[tuple[int, Optional[Dict[str, Any]], Dict[str, Any]]] = []
    retained_source_ids: set[int] = set()
    preserve_bound_shape = bool(
        catalog_present
        and not catalog_authoritative
        and any(
            _uuid_text(raw.get("bound_shot_uuid"))
            for raw in valid_source_rows
        )
    )
    if preserve_bound_shape:
        # A stale/unwatermarked five-row callback must not consume the row cap
        # before a last-known bound owner can be retained. Preserve the entire
        # existing shape until reconciliation has accepted and persisted the
        # callback watermark; otherwise an omitted row's media can be orphaned
        # and silently reassigned to a different Shot.
        for index, raw in enumerate(valid_source_rows, start=1):
            try:
                raw_number = max(
                    1,
                    min(
                        SHOT_ROUTING_MAX_SHOTS,
                        int(raw.get("number") or index),
                    ),
                )
            except Exception:
                raw_number = index
            retained_source_ids.add(id(raw))
            target_rows.append((
                raw_number,
                {
                    "shot_uuid": _uuid_text(raw.get("bound_shot_uuid")),
                    "name": _clean(raw.get("name"))[:128],
                },
                raw,
            ))
    elif catalog_present:
        bound_sources = {
            _uuid_text(raw.get("bound_shot_uuid")): raw
            for raw in valid_source_rows
            if _uuid_text(raw.get("bound_shot_uuid"))
        }
        unbound_by_number: Dict[int, Dict[str, Any]] = {}
        for raw in valid_source_rows:
            if _uuid_text(raw.get("bound_shot_uuid")):
                continue
            try:
                raw_number = int(raw.get("number") or 0)
            except Exception:
                raw_number = 0
            if 1 <= raw_number <= SHOT_ROUTING_MAX_SHOTS:
                unbound_by_number.setdefault(raw_number, raw)
        for index, remote in enumerate(remote_rows[:SHOT_ROUTING_MAX_SHOTS], start=1):
            remote_uuid = _uuid_text(remote.get("shot_uuid"))
            try:
                remote_number = max(
                    1,
                    min(SHOT_ROUTING_MAX_SHOTS, int(remote.get("number") or index)),
                )
            except Exception:
                remote_number = index
            raw = bound_sources.get(remote_uuid)
            if raw is None:
                raw = unbound_by_number.get(remote_number, {})
            if raw:
                retained_source_ids.add(id(raw))
            target_rows.append((remote_number, remote, raw or {}))
        if not catalog_authoritative:
            # A catalog without a matching durable watermark is not deletion
            # authority (for example the first stale callback after reload).
            # It may add/update visible options, but every last-known bound row
            # remains until a validated newer watermark is committed.
            for raw in valid_source_rows:
                if (
                    id(raw) in retained_source_ids
                    or len(target_rows) >= SHOT_ROUTING_MAX_SHOTS
                ):
                    continue
                try:
                    raw_number = max(
                        1,
                        min(
                            SHOT_ROUTING_MAX_SHOTS,
                            int(raw.get("number") or len(target_rows) + 1),
                        ),
                    )
                except Exception:
                    raw_number = min(
                        SHOT_ROUTING_MAX_SHOTS,
                        len(target_rows) + 1,
                    )
                retained_source_ids.add(id(raw))
                target_rows.append((raw_number, None, raw))
    else:
        # A never-configured Picker is exactly 01. Preserve additional rows only
        # when they contain authored media or a last-known ImageAsset identity;
        # publisher absence alone must not destroy durable Picker history.
        last_meaningful_index = 0
        for index, raw in enumerate(valid_source_rows, start=1):
            meaningful = bool(
                _uuid_text(raw.get("bound_shot_uuid"))
                or raw.get("video_asset_uids")
                or raw.get("selected_video_uids")
                or _clean(raw.get("preview_video_uid"))
            )
            if meaningful:
                last_meaningful_index = index
        retained_count = max(1, last_meaningful_index)
        retained_sources = valid_source_rows[:retained_count]
        if not retained_sources:
            retained_sources = [{}]
        for index, raw in enumerate(retained_sources, start=1):
            if raw:
                retained_source_ids.add(id(raw))
            target_rows.append((index, None, raw))

    # A valid newer ImageAsset catalog is the sole authority allowed to delete
    # a Shot. Remove only the media owned by a bound row that disappeared from
    # that catalog; do not reallocate it as an orphan to another Shot.
    removed_workspace_uuids: set[str] = set()
    removed_video_uids: set[str] = set()
    retained_claims: set[str] = set()
    for raw in valid_source_rows:
        if id(raw) in retained_source_ids:
            retained_claims.update(
                _clean(uid)
                for uid in (
                    raw.get("video_asset_uids")
                    if isinstance(raw.get("video_asset_uids"), list)
                    else []
                )
                if _clean(uid)
            )
            continue
        bound_uuid = _uuid_text(raw.get("bound_shot_uuid"))
        if not catalog_authoritative or not bound_uuid or bound_uuid in remote_by_uuid:
            continue
        workspace_uuid = _uuid_text(raw.get("workspace_uuid"))
        if workspace_uuid:
            removed_workspace_uuids.add(workspace_uuid)
        removed_video_uids.update(
            _clean(uid)
            for uid in (
                raw.get("video_asset_uids")
                if isinstance(raw.get("video_asset_uids"), list)
                else []
            )
            if _clean(uid)
        )
    removed_video_uids.difference_update(retained_claims)
    if removed_workspace_uuids or removed_video_uids:
        catalog = [
            item for item in catalog
            if _clean(item.get("video_uid") or item.get("source_uid"))
            not in removed_video_uids
            and _uuid_text(item.get("picker_shot_uuid"))
            not in removed_workspace_uuids
        ]
        state["videos"] = catalog

    catalog_uids = [
        _clean(item.get("video_uid") or item.get("source_uid"))
        for item in catalog
    ]
    known_video_uids = set(catalog_uids)
    global_selected = _picker_selected_video_uids(state)
    global_preview = _clean(
        state.get("preview_video_uid") or state.get("selected_video_uid")
    )
    snapshot_uids = {
        _clean(item.get("snapshot_uid"))
        for item in state.get("snapshots", [])
        if isinstance(item, dict) and _clean(item.get("snapshot_uid"))
    }

    rows: List[Dict[str, Any]] = []
    source_by_workspace: Dict[str, Dict[str, Any]] = {}
    seen_workspace_uuids: set[str] = set()
    for number, remote, raw in target_rows:
        raw_name = _clean(raw.get("name"))[:128]
        custom_name = (
            bool(raw.get("custom_name"))
            if "custom_name" in raw
            else bool(raw.get("name_is_custom"))
            if "name_is_custom" in raw
            else bool(raw_name and raw_name != f"Shot {number}")
        )
        workspace_uuid = _uuid_text(raw.get("workspace_uuid"))
        if not workspace_uuid or workspace_uuid in seen_workspace_uuids:
            workspace_uuid = (
                _picker_workspace_uuid_for_bound_shot(
                    remote.get("shot_uuid") if remote else ""
                )
                or _picker_workspace_uuid_for_number(number)
            )
            if workspace_uuid in seen_workspace_uuids:
                workspace_uuid = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"hmb-video-picker-workspace:{number}:{len(rows)}:duplicate",
                ))
        seen_workspace_uuids.add(workspace_uuid)

        bound_shot_uuid = _uuid_text(
            remote.get("shot_uuid") if remote else raw.get("bound_shot_uuid")
        )
        remote_name = _clean(remote.get("name"))[:128] if remote else ""

        active_snapshot_uid = _clean(raw.get("active_snapshot_uid"))
        if active_snapshot_uid not in snapshot_uids:
            active_snapshot_uid = ""
        try:
            current_frame = float(raw.get("current_frame") or 0.0)
            if not math.isfinite(current_frame):
                current_frame = 0.0
        except Exception:
            current_frame = 0.0
        try:
            revision = max(0, int(raw.get("revision") or 0))
        except Exception:
            revision = 0
        try:
            selected_video_slot = max(1, int(raw.get("selected_video_slot") or 1))
        except Exception:
            selected_video_slot = 1
        row = {
            "workspace_uuid": workspace_uuid,
            "number": number,
            "name": (
                raw_name if custom_name and raw_name
                else remote_name or f"Shot {number}"
            ),
            "custom_name": custom_name,
            "revision": revision,
            "bound_shot_uuid": bound_shot_uuid,
            "video_asset_uids": [],
            "selected_video_uids": [],
            "preview_video_uid": "",
            "scene_draft_path": _maya_scene_path_text(raw.get("scene_draft_path")),
            "current_frame": current_frame,
            "viewport_mode": (
                "snapshot"
                if _clean(raw.get("viewport_mode")).lower() == "snapshot"
                and active_snapshot_uid
                else "video"
            ),
            "active_snapshot_uid": active_snapshot_uid,
            "selected_video_slot": selected_video_slot,
            "authoring_context": _normalize_picker_authoring_context(
                raw.get("authoring_context")
            ),
        }
        rows.append(row)
        source_by_workspace[workspace_uuid] = raw

    requested_active_uuid = (
        _uuid_text(state.get("active_picker_shot_uuid"))
        if picker_shots_present else ""
    )
    if legacy_one_page:
        # The pre-workspace Picker was one page, regardless of the transient
        # remote selector that happened to be active when it was saved. Keep
        # that page and its media together as the deterministic 01 migration.
        active_row = rows[0]
    else:
        active_row = next(
            (row for row in rows if row["workspace_uuid"] == requested_active_uuid),
            next(
                (
                    row for row in rows
                    if row["bound_shot_uuid"] == _uuid_text(state.get("shot_uuid"))
                ),
                rows[0],
            ),
        )
    state["active_picker_shot_uuid"] = active_row["workspace_uuid"]

    owned_uids: set[str] = set()
    if legacy_one_page:
        # A legacy catalog represented one page, not five. Never silently
        # spread its overflow into additional user-visible Shots.
        rows[0]["video_asset_uids"] = catalog_uids[
            :MAX_VIDEO_ASSETS_PER_PICKER_SHOT
        ]
        owned_uids.update(rows[0]["video_asset_uids"])
    else:
        # Explicit ownership is authoritative. Numeric row order deterministically
        # resolves corrupt duplicate claims.
        for row in rows:
            raw = source_by_workspace.get(row["workspace_uuid"], {})
            if "video_asset_uids" not in raw:
                continue
            assets = _picker_representative_video_uids(
                raw.get("video_asset_uids"),
                "",
                known_video_uids,
            )
            for uid in assets:
                if uid not in owned_uids:
                    row["video_asset_uids"].append(uid)
                    owned_uids.add(uid)

        # Selected-only experimental rows predate ownership. Their membership
        # claims are migrated before any shared-catalog orphan is allocated.
        for row in rows:
            raw = source_by_workspace.get(row["workspace_uuid"], {})
            if "video_asset_uids" in raw:
                continue
            selected_claims = _picker_representative_video_uids(
                raw.get("selected_video_uids"),
                raw.get("preview_video_uid"),
                known_video_uids,
            )
            for uid in selected_claims:
                if (
                    uid not in owned_uids
                    and len(row["video_asset_uids"])
                    < MAX_VIDEO_ASSETS_PER_PICKER_SHOT
                ):
                    row["video_asset_uids"].append(uid)
                    owned_uids.add(uid)

        # Per-record owner tags are a recovery mirror, not the primary model.
        # Honor them only for still-unclaimed records and currently retained
        # ImageAsset/local rows.
        row_by_workspace = {
            row["workspace_uuid"]: row for row in rows
        }
        for item in catalog:
            uid = _clean(item.get("video_uid") or item.get("source_uid"))
            tagged_row = row_by_workspace.get(
                _uuid_text(item.get("picker_shot_uuid"))
            )
            if (
                uid in owned_uids
                or tagged_row is None
                or len(tagged_row["video_asset_uids"])
                >= MAX_VIDEO_ASSETS_PER_PICKER_SHOT
            ):
                continue
            tagged_row["video_asset_uids"].append(uid)
            owned_uids.add(uid)

        allocation_rows = [active_row] + [
            row for row in rows if row is not active_row
        ]
        for uid in catalog_uids:
            if uid in owned_uids or len(owned_uids) >= MAX_PICKER_VIDEO_ASSETS:
                continue
            target_row = next(
                (
                    row
                    for row in allocation_rows
                    if len(row["video_asset_uids"])
                    < MAX_VIDEO_ASSETS_PER_PICKER_SHOT
                ),
                None,
            )
            if target_row is None:
                break
            target_row["video_asset_uids"].append(uid)
            owned_uids.add(uid)

    # A selected UID is always a subset of ownership. Legacy selection is
    # retained on Shot 1; newer rows retain their own independent subset/order.
    for row in rows:
        raw = source_by_workspace.get(row["workspace_uuid"], {})
        asset_set = set(row["video_asset_uids"])
        if legacy_one_page and row["number"] == 1:
            raw_selected = raw.get("selected_video_uids")
            requested_selected = (
                raw_selected
                if isinstance(raw_selected, (list, tuple)) and raw_selected
                else global_selected
            )
            requested_preview = (
                raw.get("preview_video_uid") or global_preview
            )
        elif legacy_one_page:
            requested_selected = []
            requested_preview = ""
        else:
            requested_selected = raw.get("selected_video_uids", [])
            requested_preview = raw.get("preview_video_uid")
            # States assembled by older Python integrations may carry the
            # current global selection beside newly introduced empty ownership
            # rows. Once their orphan records are assigned to the active Shot,
            # retain that active subset instead of silently deselecting it.
            if row is active_row and not requested_selected:
                projected_global_selection = [
                    uid for uid in global_selected if uid in asset_set
                ]
                if projected_global_selection:
                    requested_selected = projected_global_selection
        selected = _picker_representative_video_uids(
            requested_selected,
            requested_preview,
            asset_set,
        )
        row["selected_video_uids"] = selected
        preview_uid = _clean(requested_preview)
        if row is active_row and global_preview in asset_set:
            preview_uid = global_preview
        if preview_uid not in asset_set:
            preview_uid = selected[0] if selected else (
                row["video_asset_uids"][0] if row["video_asset_uids"] else ""
            )
        row["preview_video_uid"] = preview_uid
        row["selected_video_slot"] = max(
            1,
            min(max(1, len(selected)), int(row.get("selected_video_slot") or 1)),
        )

    # Keep the active row's non-media viewport projection compatible with the
    # existing widget transport while ownership/selection remains row-local.
    active_snapshot_uid = _clean(state.get("active_snapshot_uid"))
    if active_snapshot_uid not in snapshot_uids:
        active_snapshot_uid = ""
    try:
        active_current_frame = float(state.get("current_frame") or 0.0)
        if not math.isfinite(active_current_frame):
            active_current_frame = 0.0
    except Exception:
        active_current_frame = 0.0
    active_row.update({
        "scene_draft_path": _maya_scene_path_text(state.get("scene_draft_path")),
        "current_frame": active_current_frame,
        "viewport_mode": (
            "snapshot"
            if _clean(state.get("viewport_mode")).lower() == "snapshot"
            and active_snapshot_uid
            else "video"
        ),
        "active_snapshot_uid": active_snapshot_uid,
        "authoring_context": _picker_authoring_context_from_state(state),
    })

    retained_catalog: List[Dict[str, Any]] = []
    owner_by_uid = {
        uid: row["workspace_uuid"]
        for row in rows
        for uid in row["video_asset_uids"]
    }
    for item in catalog:
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        owner_uuid = owner_by_uid.get(uid)
        if not owner_uuid:
            continue
        item["picker_shot_uuid"] = owner_uuid
        retained_catalog.append(item)
    omitted_count = len(catalog) - len(retained_catalog)
    if omitted_count:
        scope = (
            "legacy Shot 1"
            if legacy_one_page
            else f"{len(rows)} Picker Shot(s)"
        )
        warning = (
            f"Video ownership overflow: retained {len(retained_catalog)} of "
            f"{len(catalog)} assets in {scope}; omitted {omitted_count} beyond "
            f"the {MAX_VIDEO_ASSETS_PER_PICKER_SHOT}-per-Shot capacity."
        )
        warnings = _normalize_ui_warnings(state.get("warnings"))
        if warning not in warnings:
            warnings.append(warning)
        state["warnings"] = warnings[-20:]
    state["videos"] = retained_catalog

    # Once a remote Shot has a fixed local owner, legacy remote membership must
    # not be resurrected if that publisher later disappears.
    legacy_membership_fallbacks = (
        dict(state.get("picker_legacy_membership_fallbacks"))
        if isinstance(state.get("picker_legacy_membership_fallbacks"), dict)
        else {}
    )
    for row in rows:
        legacy_membership_fallbacks.pop(row["bound_shot_uuid"], None)
    state["picker_legacy_membership_fallbacks"] = legacy_membership_fallbacks

    remote_row = remote_by_uuid.get(active_row["bound_shot_uuid"])
    if remote_row is None:
        state["shot_uuid"] = ""
        state["shot_number"] = 0
        state["shot_name"] = ""
    else:
        state["shot_uuid"] = _uuid_text(remote_row.get("shot_uuid"))
        state["shot_number"] = int(remote_row.get("number") or 0)
        state["shot_name"] = _clean(remote_row.get("name"))[:128]

    active_selected_uids = list(active_row["selected_video_uids"])
    active_order_by_uid = {
        uid: index + 1 for index, uid in enumerate(active_selected_uids)
    }
    catalog_by_uid: Dict[str, Dict[str, Any]] = {}
    for item in state["videos"]:
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        catalog_by_uid[uid] = item
        selection_order = active_order_by_uid.get(uid, 0)
        item["selected"] = bool(selection_order)
        item["selection_order"] = selection_order
        item["video_slot"] = selection_order
        if isinstance(item.get("frame_metadata"), dict):
            item["frame_metadata"]["video_slot"] = (
                f"@video{selection_order}" if selection_order else ""
            )

    active_preview_uid = _clean(active_row.get("preview_video_uid"))
    if active_preview_uid not in set(active_row["video_asset_uids"]):
        active_preview_uid = (
            active_selected_uids[0] if active_selected_uids
            else active_row["video_asset_uids"][0]
            if active_row["video_asset_uids"] else ""
        )
    active_row["preview_video_uid"] = active_preview_uid
    active_slot = active_order_by_uid.get(active_preview_uid)
    if not active_slot:
        active_slot = max(
            1,
            min(
                max(1, len(active_selected_uids)),
                int(active_row.get("selected_video_slot") or 1),
            ),
        )
    active_row["selected_video_slot"] = active_slot
    state["preview_video_uid"] = active_preview_uid
    state["selected_video_uid"] = active_preview_uid
    state["selected_video_slot"] = active_slot
    state["selected_video_count"] = len(active_selected_uids)
    state["max_selected_videos"] = MAX_SELECTED_VIDEOS
    state["active_slot_count"] = max(1, len(active_selected_uids))
    preview_item = catalog_by_uid.get(active_preview_uid, {})
    state["selected_video_path"] = _clean(
        preview_item.get("project_video_path")
        or preview_item.get("video_path")
        or preview_item.get("video_url")
    )
    selection_identity = [
        {
            "video_uid": uid,
            "selection_order": order,
            "media": _clean(
                catalog_by_uid.get(uid, {}).get("project_video_path")
                or catalog_by_uid.get(uid, {}).get("video_path")
                or catalog_by_uid.get(uid, {}).get("video_url")
            ),
        }
        for uid, order in active_order_by_uid.items()
    ]
    state["selection_id"] = hashlib.sha256(
        json.dumps(
            selection_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    state["picker_shots"] = rows
    # ``picker_shots`` is the durable media owner. Keep the compact routing
    # rows synchronized from that authority on every save/reload. Older saved
    # files could contain full Shot membership here while ``shot_selections``
    # remained empty, causing Prompt hydration to observe an empty Picker even
    # though every video card was still serialized.
    workspaces_by_bound_uuid = {
        _uuid_text(row.get("bound_shot_uuid")): row
        for row in rows
        if _uuid_text(row.get("bound_shot_uuid"))
    }
    synchronized_shot_selections: List[Dict[str, Any]] = []
    for raw_selection in state.get("shot_selections", []):
        if not isinstance(raw_selection, dict):
            continue
        selection = dict(raw_selection)
        workspace = workspaces_by_bound_uuid.get(
            _uuid_text(selection.get("shot_uuid"))
        )
        if workspace is not None:
            selection["selected_video_uids"] = list(
                workspace.get("selected_video_uids") or []
            )[:MAX_SELECTED_VIDEOS]
        synchronized_shot_selections.append(selection)
    state["shot_selections"] = synchronized_shot_selections


def _activate_picker_workspace_projection(
    state: Dict[str, Any],
    workspace_uuid: Any,
) -> Optional[Dict[str, Any]]:
    """Project one validated local workspace onto legacy global controls.

    Command transport and widget state transport are independent. A command
    can therefore reach Python before the state echo from a rapid local Shot
    switch. The command's captured workspace UUID is authoritative for that
    one action, while an invalid/missing row returns ``None`` without mutation.
    """

    normalized = _parse_state(state)
    requested_uuid = _uuid_text(workspace_uuid)
    if not requested_uuid:
        return None
    target = next(
        (
            row
            for row in normalized.get("picker_shots", [])
            if isinstance(row, dict)
            and _uuid_text(row.get("workspace_uuid")) == requested_uuid
        ),
        None,
    )
    if target is None:
        return None

    selected_order = {
        _clean(uid): index
        for index, uid in enumerate(
            target.get("selected_video_uids", []),
            start=1,
        )
        if _clean(uid)
    }
    projected = dict(normalized)
    projected["videos"] = []
    for raw in normalized.get("videos", []):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        order = selected_order.get(uid, 0)
        item["selected"] = bool(order)
        item["selection_order"] = order
        item["video_slot"] = order
        projected["videos"].append(item)
    projected.update({
        "active_picker_shot_uuid": requested_uuid,
        "preview_video_uid": _clean(target.get("preview_video_uid")),
        "selected_video_uid": _clean(target.get("preview_video_uid")),
        "scene_draft_path": _maya_scene_path_text(target.get("scene_draft_path")),
        "current_frame": float(target.get("current_frame") or 0.0),
        "viewport_mode": (
            "snapshot"
            if _clean(target.get("viewport_mode")).lower() == "snapshot"
            else "video"
        ),
        "active_snapshot_uid": _clean(target.get("active_snapshot_uid")),
        "selected_video_slot": max(1, int(target.get("selected_video_slot") or 1)),
    })
    _apply_picker_authoring_context(
        projected,
        target.get("authoring_context"),
    )
    bound_shot_uuid = _uuid_text(target.get("bound_shot_uuid"))
    bound_remote = next(
        (
            row
            for row in normalized.get("shot_selections", [])
            if isinstance(row, dict)
            and _uuid_text(row.get("shot_uuid")) == bound_shot_uuid
        ),
        None,
    )
    if bound_remote is None:
        projected.update({"shot_uuid": "", "shot_number": 0, "shot_name": ""})
    else:
        projected.update({
            "shot_uuid": bound_shot_uuid,
            "shot_number": int(bound_remote.get("number") or 0),
            "shot_name": _clean(bound_remote.get("name"))[:128],
        })
    return _parse_state(projected)


def _readable_video_slot(value: Any) -> int:
    """Return one readable @video slot without coercing it into another slot."""
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(float(value))
    except Exception:
        match = re.fullmatch(r"(?:@?video)?\s*(\d+)", _clean(value), flags=re.IGNORECASE)
        parsed = int(match.group(1)) if match else 0
    return parsed if 1 <= parsed <= MAX_VIDEO_SLOTS else 0


def _normalized_video_slot(value: Any, fallback: int = 1) -> int:
    readable = _readable_video_slot(value)
    if readable:
        return readable
    try:
        parsed = int(float(value))
    except Exception:
        parsed = int(fallback or 1)
    return max(1, min(MAX_VIDEO_SLOTS, parsed))


def _observed_state_slot_count(value: Any) -> int:
    """Recover the largest readable slot represented by serialized UI state."""
    source = value if isinstance(value, dict) else {}
    observed = 0
    for scalar_name in (
        "selected_video_slot",
        "snapshot_video_slot",
        "depth_video_slot",
        "motion_guide_video_slot",
    ):
        observed = max(
            observed,
            _readable_video_slot(source.get(scalar_name)),
        )
    for collection_name in (
        "videos",
        "slot_assignments",
        "slot_visibility",
        "snapshots",
    ):
        collection = source.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            observed = max(
                observed,
                _readable_video_slot(item.get("video_slot")),
            )
    return observed


def _positive_int(value: Any) -> int:
    try:
        parsed = int(round(float(value)))
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def _finite_float(value: Any) -> float:
    try:
        parsed = float(value)
    except Exception:
        return 0.0
    return parsed if parsed == parsed and abs(parsed) != float("inf") else 0.0


def _fps_timebase(value: Any) -> str:
    fps = _finite_float(value)
    if fps <= 0:
        return ""
    known_rates = (
        (23.976, "24000/1001"),
        (29.97, "30000/1001"),
        (47.952, "48000/1001"),
        (59.94, "60000/1001"),
    )
    for known, timebase in known_rates:
        if abs(fps - known) < 0.001:
            return timebase
    fraction = Fraction(str(round(fps, 9))).limit_denominator(100000)
    return f"{fraction.numerator}/{fraction.denominator}"


def _maya_sequence_frame_count(start_frame: Any, end_frame: Any) -> int:
    """Mirror the Maya runner's exact fractional-endpoint sampling contract."""
    start_value = float(start_frame)
    end_value = float(end_frame)
    if not math.isfinite(start_value) or not math.isfinite(end_value):
        return 0
    if end_value < start_value:
        return 0
    whole_steps = int(math.floor((end_value - start_value) + 1e-9))
    count = whole_steps + 1
    if abs((start_value + whole_steps) - end_value) > 1e-6:
        count += 1
    return count


def _video_track_timescale(value: Any) -> int:
    """Choose a >=10 kHz MP4 timescale with an integer tick per source frame."""
    rate_text = _fps_timebase(value)
    if not rate_text:
        return 0
    numerator_text, _, denominator_text = rate_text.partition("/")
    numerator = max(1, int(numerator_text))
    denominator = max(1, int(denominator_text or "1"))
    multiplier = max(1, (10000 + numerator - 1) // numerator)
    timescale = numerator * multiplier
    if timescale * denominator // numerator <= 0:
        return 0
    return timescale


def _video_frame_metadata(item: Dict[str, Any], slot: int) -> Dict[str, Any]:
    """Resolve one stable display-frame contract without hiding source conflicts.

    Generated/decoded frame count is authoritative for media length. Maya's
    playback range remains authoritative for the frame numbers shown to users.
    A disagreement is reported instead of shifting either side automatically.
    """
    source = item if isinstance(item, dict) else {}
    warnings: List[str] = []

    decoded_frame_count = next(
        (
            value
            for value in (
                _positive_int(source.get("decoded_frame_count")),
                _positive_int(source.get("actual_decoded_frame_count")),
                _positive_int(source.get("output_frame_count")),
                _positive_int(source.get("source_frame_count")),
            )
            if value > 0
        ),
        0,
    )

    maya_start_value = source.get("maya_start_frame")
    if maya_start_value in (None, ""):
        maya_start_value = source.get("start_frame")
    maya_end_value = source.get("maya_end_frame")
    if maya_end_value in (None, ""):
        maya_end_value = source.get("end_frame")
    maya_start = _finite_float(maya_start_value)
    maya_end = _finite_float(maya_end_value)
    explicit_maya_range = source.get("has_maya_frame_range")
    if explicit_maya_range is None:
        explicit_maya_range = (
            "maya_start_frame" in source
            or "maya_end_frame" in source
            or (
                "start_frame" in source
                and "end_frame" in source
                and (maya_start != 0 or maya_end != 0)
            )
        )
    has_maya_range = bool(explicit_maya_range) and maya_end >= maya_start
    maya_start_frame = int(round(maya_start)) if has_maya_range else 0
    maya_end_frame = int(round(maya_end)) if has_maya_range else 0
    maya_frame_count = (
        max(1, maya_end_frame - maya_start_frame + 1)
        if has_maya_range
        else 0
    )

    fps = next(
        (
            value
            for value in (
                _finite_float(source.get("decoded_fps")),
                _finite_float(source.get("actual_output_fps")),
                _finite_float(source.get("output_fps")),
                _finite_float(source.get("fps")),
                _finite_float(source.get("source_fps")),
                _finite_float(source.get("manual_fps")),
            )
            if value > 0
        ),
        0.0,
    )
    stored_duration = next(
        (
            value
            for value in (
                _finite_float(source.get("output_duration_seconds")),
                _finite_float(source.get("duration_seconds")),
                _finite_float(source.get("source_duration_seconds")),
                _finite_float(source.get("manual_duration_seconds")),
            )
            if value > 0
        ),
        0.0,
    )
    resolution = (
        source.get("resolution")
        if isinstance(source.get("resolution"), dict)
        else {}
    )
    raster_width = next(
        (
            value
            for value in (
                _positive_int(source.get("output_width")),
                _positive_int(source.get("source_width")),
                _positive_int(source.get("width")),
                _positive_int(resolution.get("width")),
            )
            if value > 0
        ),
        0,
    )
    raster_height = next(
        (
            value
            for value in (
                _positive_int(source.get("output_height")),
                _positive_int(source.get("source_height")),
                _positive_int(source.get("height")),
                _positive_int(resolution.get("height")),
            )
            if value > 0
        ),
        0,
    )
    derived_frame_count = (
        max(1, int(round(fps * stored_duration)))
        if fps > 0 and stored_duration > 0
        else 0
    )
    manual_frame_count = _positive_int(source.get("manual_frame_count"))
    frame_count = (
        decoded_frame_count
        or maya_frame_count
        or derived_frame_count
        or manual_frame_count
    )

    if has_maya_range:
        start_frame = maya_start_frame
        end_frame = maya_end_frame
    else:
        manual_start = _positive_int(source.get("manual_start_frame"))
        start_frame = manual_start or 1
        manual_end = _positive_int(source.get("manual_end_frame"))
        if frame_count > 0:
            end_frame = start_frame + frame_count - 1
        elif manual_end >= start_frame:
            end_frame = manual_end
            frame_count = end_frame - start_frame + 1
        else:
            end_frame = start_frame - 1

    conflict = False
    if decoded_frame_count > 0 and maya_frame_count > 0 and decoded_frame_count != maya_frame_count:
        conflict = True
        warnings.append(
            "Decoded video frame count "
            f"({decoded_frame_count}) does not match the Maya display range "
            f"{maya_start_frame}–{maya_end_frame} ({maya_frame_count} frames)."
        )
    if frame_count <= 0:
        warnings.append("Frame count is unavailable.")
    if fps <= 0:
        warnings.append("FPS is unavailable.")
    if end_frame < start_frame:
        warnings.append("Display frame range is unavailable.")

    duration_seconds = frame_count / fps if frame_count > 0 and fps > 0 else stored_duration
    markers = _normalize_markers(source.get("markers"), slot)
    available_color_picks: List[str] = []
    for marker in markers:
        color = _clean(marker.get("color"))
        if color and color not in available_color_picks:
            available_color_picks.append(color)

    return {
        "video_slot": f"@video{slot}",
        "fps": fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_count": frame_count,
        "decoded_frame_count": decoded_frame_count,
        "maya_start_frame": maya_start_frame if has_maya_range else None,
        "maya_end_frame": maya_end_frame if has_maya_range else None,
        "duration_seconds": duration_seconds,
        "timebase": _fps_timebase(fps),
        "width": raster_width,
        "height": raster_height,
        "resolution": {"width": raster_width, "height": raster_height},
        "frame_index_start": 0 if frame_count > 0 else None,
        "frame_index_end": frame_count - 1 if frame_count > 0 else None,
        "available_color_picks": available_color_picks,
        "origin": (
            "decoded_video+maya"
            if decoded_frame_count > 0 and has_maya_range
            else "decoded_video"
            if decoded_frame_count > 0
            else "maya"
            if has_maya_range
            else "fps_duration"
            if derived_frame_count > 0
            else "manual"
        ),
        "conflict": conflict,
        "valid": bool(
            frame_count > 0
            and fps > 0
            and end_frame >= start_frame
            and not conflict
        ),
        "warnings": warnings,
    }


def _video_frame_domain(frame_metadata: Any) -> Dict[str, Any]:
    """Return the bounded frame-addressing contract used by typed bindings."""

    metadata = frame_metadata if isinstance(frame_metadata, dict) else {}
    try:
        start_frame = int(metadata.get("start_frame"))
        end_frame = int(metadata.get("end_frame"))
        frame_count = max(0, int(metadata.get("frame_count") or 0))
    except (TypeError, ValueError, OverflowError):
        start_frame = 1
        end_frame = 0
        frame_count = 0
    valid = bool(
        frame_count > 0
        and end_frame >= start_frame
        and not bool(metadata.get("conflict"))
    )
    return {
        "schema": VIDEO_FRAME_DOMAIN_SCHEMA,
        "version": VIDEO_FRAME_DOMAIN_VERSION,
        "timebase": _clean(metadata.get("timebase")),
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_count": frame_count,
        "range_addressable": valid,
    }


def _emitter_identity_from_cue(
    value: Any,
    markers: Sequence[Dict[str, Any]],
) -> Dict[str, str]:
    """Resolve one cue emitter without promoting unrelated metadata to intent."""

    source = value if isinstance(value, dict) else {}
    marker_color = _clean(source.get("marker_color") or source.get("color"))
    maya_uuid = _clean(source.get("maya_uuid"))
    subject_root = _clean(
        source.get("subject_root") or source.get("full_dag_path")
    )
    asset_id = _clean(source.get("asset_id"))

    matched: Optional[Dict[str, Any]] = None
    for marker in markers:
        if not isinstance(marker, dict):
            continue
        if maya_uuid and _clean(marker.get("maya_uuid")).casefold() == maya_uuid.casefold():
            matched = marker
            break
        if (
            subject_root
            and _clean(
                marker.get("subject_root") or marker.get("full_dag_path")
            ).casefold()
            == subject_root.casefold()
        ):
            matched = marker
            break
        if (
            asset_id
            and marker_color
            and _clean(marker.get("asset_id")).casefold() == asset_id.casefold()
            and _clean(marker.get("color")).casefold() == marker_color.casefold()
        ):
            matched = marker
            break

    if matched is None and marker_color and not asset_id:
        color_matches = [
            marker
            for marker in markers
            if isinstance(marker, dict)
            and _clean(marker.get("color")).casefold() == marker_color.casefold()
        ]
        if len(color_matches) == 1:
            matched = color_matches[0]

    if matched is None:
        return {}

    marker_color = _clean(matched.get("color"))
    maya_uuid = _clean(matched.get("maya_uuid"))
    subject_root = _clean(
        matched.get("subject_root") or matched.get("full_dag_path")
    )
    asset_id = _clean(matched.get("asset_id"))
    if not marker_color and not maya_uuid and not subject_root:
        return {}
    if marker_color and marker_color not in MARKER_ORDER:
        return {}
    return {
        "marker_color": marker_color,
        "asset_id": asset_id,
        "subject_root": subject_root,
        "maya_uuid": maya_uuid,
    }


def _normalize_emitter_local_point(value: Any) -> Dict[str, Any]:
    """Validate one explicit emitter-local spatial point."""

    if not isinstance(value, dict):
        return {}
    kind = _clean(value.get("kind")).casefold()
    if kind == "locator":
        locator_id = _clean(value.get("locator_id") or value.get("maya_uuid"))[:256]
        locator_path = _clean(
            value.get("locator_path")
            or value.get("full_dag_path")
            or value.get("path")
        )[:512]
        if not locator_id and not locator_path:
            return {}
        if any(
            ord(character) < 32 or ord(character) == 127
            for character in f"{locator_id}{locator_path}"
        ):
            return {}
        return {
            "kind": "locator",
            "locator_id": locator_id,
            "locator_path": locator_path,
        }

    if kind != "coordinates":
        return {}
    space = _clean(value.get("space")).casefold()
    if space not in {"local", "object"}:
        return {}
    unit_aliases = {
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
    unit = unit_aliases.get(_clean(value.get("unit")).casefold(), "")
    if not unit:
        return {}
    raw_xyz = value.get("xyz")
    if isinstance(raw_xyz, (list, tuple)) and len(raw_xyz) == 3:
        candidates = list(raw_xyz)
    elif all(axis in value for axis in ("x", "y", "z")):
        candidates = [value.get("x"), value.get("y"), value.get("z")]
    else:
        return {}
    coordinates: List[float] = []
    for candidate in candidates:
        if isinstance(candidate, bool):
            return {}
        try:
            coordinate = float(candidate)
        except (TypeError, ValueError, OverflowError):
            return {}
        if not math.isfinite(coordinate):
            return {}
        coordinates.append(coordinate)
    return {
        "kind": "coordinates",
        "space": space,
        "unit": unit,
        "xyz": coordinates,
    }


def _normalize_timing_cues(
    value: Any,
    markers: Sequence[Dict[str, Any]],
    frame_domain: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Validate exact emitter/frame cues carried by a Picker video record."""

    if not isinstance(value, list):
        return []
    if not bool(frame_domain.get("range_addressable")):
        return []
    start_frame = int(frame_domain["start_frame"])
    end_frame = int(frame_domain["end_frame"])
    cues: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for raw in value[:MAX_VIDEO_TIMING_CUES]:
        if not isinstance(raw, dict):
            continue
        raw_frame = raw.get("frame")
        if raw_frame in (None, ""):
            raw_frame = raw.get("maya_frame")
        try:
            frame_value = float(raw_frame)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(frame_value) or not (
            start_frame <= frame_value <= end_frame
        ):
            continue
        rounded_frame = round(frame_value)
        if abs(frame_value - rounded_frame) > 1e-6:
            continue

        emitter_source = (
            raw.get("emitter")
            if isinstance(raw.get("emitter"), dict)
            else raw
        )
        emitter = _emitter_identity_from_cue(emitter_source, markers)
        if not emitter:
            continue
        local_point = _normalize_emitter_local_point(raw.get("local_point"))
        if not local_point:
            continue
        cue_phase = _clean(
            raw.get("cue_phase") or raw.get("phase") or "point"
        ).casefold()
        if cue_phase not in {"point", "onset", "peak", "falloff", "end"}:
            continue
        normalized_frame = int(rounded_frame)
        signature = (
            normalized_frame,
            cue_phase,
            emitter["marker_color"].casefold(),
            emitter["maya_uuid"].casefold(),
            emitter["subject_root"].casefold(),
            json.dumps(
                local_point,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        if signature in seen:
            continue
        seen.add(signature)
        cue_id = _clean(raw.get("cue_id"))[:128]
        if not cue_id:
            digest = hashlib.sha256(
                json.dumps(
                    signature,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:20]
            cue_id = f"emitter-cue-{digest}"
        cue: Dict[str, Any] = {
            "schema": VIDEO_TIMING_CUE_SCHEMA,
            "version": VIDEO_TIMING_CUE_VERSION,
            "cue_id": cue_id,
            "cue_type": "emitter_point",
            "cue_phase": cue_phase,
            "frame": normalized_frame,
            "emitter": emitter,
            "local_point": local_point,
        }
        description = _clean(raw.get("description"))[:512]
        if description:
            cue["description"] = description
        cues.append(cue)

    # Distinct cues may arrive with the same external cue_id. Canonicalize all
    # members of that collision by content so IDs are unique and independent of
    # Picker row order while remaining within the producer's 128-char bound.
    cue_id_counts: Dict[str, int] = {}
    for cue in cues:
        cue_id = _clean(cue.get("cue_id"))
        cue_id_counts[cue_id] = cue_id_counts.get(cue_id, 0) + 1
    for cue in cues:
        cue_id = _clean(cue.get("cue_id"))
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
        prefix = cue_id[: 128 - len(digest) - 1]
        cue["cue_id"] = f"{prefix}-{digest}"
    return cues


def _video_reference_capabilities(
    frame_domain: Dict[str, Any],
    timing_cues: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Describe typed support without choosing an interpretation role."""

    frame_addressable = bool(frame_domain.get("range_addressable"))
    return {
        "schema": VIDEO_REFERENCE_CAPABILITY_SCHEMA,
        "version": VIDEO_REFERENCE_CAPABILITY_VERSION,
        "frame_addressable": frame_addressable,
        "exact_emitter_cues": bool(timing_cues),
        "image_source_frame_ranges": frame_addressable,
        "marker_instance_identity_fields": [
            "maya_uuid",
            "full_dag_path",
        ],
    }


def _parameter_name(parameter: Any) -> str:
    if isinstance(parameter, str):
        return _clean(parameter)
    if isinstance(parameter, dict):
        return _clean(parameter.get("name") or parameter.get("parameter_name"))
    return _clean(getattr(parameter, "name", "") or getattr(parameter, "parameter_name", ""))


def _scene_path_text(value: Any) -> str:
    """Resolve the path shape produced by different FileSystemPicker builds."""
    if value is None:
        return ""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return _decode_maya_text(value)
    if isinstance(value, dict):
        for key in ("path", "file_path", "filepath", "value", "uri", "url", "filename"):
            resolved = _scene_path_text(value.get(key))
            if resolved:
                return resolved
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            resolved = _scene_path_text(item)
            if resolved:
                return resolved
        return ""
    if not isinstance(value, str):
        for attribute in ("path", "file_path", "filepath", "value", "uri", "url", "filename"):
            try:
                resolved = _scene_path_text(getattr(value, attribute, None))
            except Exception:
                resolved = ""
            if resolved:
                return resolved
    text = _clean(value).strip('"').strip("'")
    if text[:1] in {"[", "{"}:
        try:
            resolved = _scene_path_text(json.loads(text))
            if resolved:
                return resolved
        except Exception as exc:
            _diagnostic_exception("JSON-shaped Maya scene path parsing failed; preserving literal text", exc)
    return text


def _maya_scene_path_text(value: Any) -> str:
    """Return exactly one lexical absolute Maya scene path.

    This boundary is intentionally filesystem-independent: a saved workflow
    may point at a portable/non-mounted scene and READ owns the later existence
    check.  It nevertheless rejects native-control aggregate text, multiple
    selections/roots, relative paths, and log/status suffixes before any such
    value can become retained node state.
    """

    def one_candidate(candidate: Any) -> str:
        if candidate is None:
            return ""
        if isinstance(candidate, dict):
            resolved = []
            for key in (
                "path", "file_path", "filepath", "value", "uri", "url",
                "filename",
            ):
                if key not in candidate:
                    continue
                item = one_candidate(candidate.get(key))
                if item and item not in resolved:
                    resolved.append(item)
            return resolved[0] if len(resolved) == 1 else ""
        if isinstance(candidate, (list, tuple, set)):
            resolved = [one_candidate(item) for item in candidate]
            resolved = [item for item in resolved if item]
            return resolved[0] if len(resolved) == 1 else ""
        if not isinstance(candidate, (str, bytes, Path)):
            resolved = []
            for attribute in (
                "path", "file_path", "filepath", "value", "uri", "url",
                "filename",
            ):
                try:
                    item = one_candidate(getattr(candidate, attribute, None))
                except Exception:
                    item = ""
                if item and item not in resolved:
                    resolved.append(item)
            return resolved[0] if len(resolved) == 1 else ""
        if isinstance(candidate, bytes):
            candidate = _decode_maya_text(candidate)
        text_value = str(candidate or "").strip().strip('"').strip("'")
        if text_value[:1] in {"[", "{"}:
            try:
                decoded = json.loads(text_value)
            except Exception:
                return text_value
            return one_candidate(decoded)
        return text_value

    text = one_candidate(value)
    if not text or len(text) > 4096:
        return ""
    if any(ord(character) < 32 for character in text):
        return ""
    if any(character in text for character in '<>"|?*'):
        return ""
    if re.search(r"\[\d{1,2}:\d{2}(?::\d{2})?\]", text):
        return ""
    if re.search(
        r"(?i)\.(?:py|js|log|txt)\s*(?:\[[^\]]+\]\s*)?"
        r"(?:SUCCESS|ERROR|WARNING|INFO)\b",
        text,
    ):
        return ""
    if re.search(r"(?i)\s(?:SUCCESS|ERROR|WARNING|INFO)(?:\s|$)", text):
        return ""

    lexical = text.replace("\\", "/")
    drive_roots = re.findall(r"(?i)(?<![A-Za-z0-9_])[A-Z]:/", lexical)
    whitespace_roots = re.findall(r"\s/(?!/)", lexical)
    is_drive = bool(re.fullmatch(r"(?is)[A-Z]:/(?!/).+", lexical))
    is_unc = lexical.startswith("//") and not lexical.startswith("///")
    is_posix = lexical.startswith("/") and not lexical.startswith("//")

    if is_drive:
        if len(drive_roots) != 1 or whitespace_roots:
            return ""
        if ":" in lexical[2:]:
            return ""
        components = lexical[3:].split("/")
    elif is_unc:
        if drive_roots or "//" in lexical[2:] or whitespace_roots:
            return ""
        components = lexical[2:].split("/")
        # server, share, and at least one path component are required.
        if len(components) < 3:
            return ""
    elif is_posix:
        if drive_roots or whitespace_roots:
            return ""
        components = lexical[1:].split("/")
    else:
        return ""

    if not components or any(not component for component in components):
        return ""
    if Path(components[-1]).suffix.casefold() not in {".ma", ".mb"}:
        return ""
    return text


_UI_WARNING_MESSAGE_LIMIT = 480
_UI_ACTIVITY_MESSAGE_LIMIT = 1600


def _compact_ui_diagnostic(value: Any, max_chars: int) -> str:
    """Return one bounded, single-line UI diagnostic.

    Maya errors can contain hundreds of full DAG paths.  Retained widget state
    is transported on every update, so copying those path lists into warnings
    or activity entries can turn one useful error into a multi-megabyte node
    payload.  Full output stays in the operation log/sidecar; the widget keeps
    only the leading diagnosis and bounded count evidence.
    """
    text = re.sub(r"\s+", " ", _clean(value).replace("\x00", " ")).strip()
    limit = max(160, int(max_chars or 0))
    if len(text) <= limit:
        return text

    failed_count = ""
    failed_match = re.search(
        r"failed\s+for\s+([0-9]+)\s+of\s+([0-9]+)",
        text,
        flags=re.IGNORECASE,
    )
    if failed_match:
        failed_count = (
            f" Failed paths: {failed_match.group(1)}/{failed_match.group(2)}."
        )

    # Preserve the actionable clause before the first expanded path list.
    path_start = re.search(r"(?:^|[,:;]\s+)(?:\|[^\s,;:]+)", text)
    useful_end = path_start.start() if path_start else min(len(text), limit // 2)
    head = text[:useful_end].rstrip(" ,:;|")
    if len(head) > limit // 2:
        head = head[: limit // 2].rsplit(" ", 1)[0].rstrip(" ,:;|")
    if not head:
        head = text[: limit // 2].rsplit(" ", 1)[0].rstrip(" ,:;|")
    suffix = (
        f"{failed_count} Detailed DAG paths were omitted from UI state; "
        "see the diagnostic log/sidecar."
    )
    compact = f"{head}. {suffix}" if head else suffix
    if len(compact) > limit:
        compact = compact[: limit - 1].rstrip() + "…"
    return compact


def _normalize_ui_warnings(value: Any) -> List[str]:
    source = value if isinstance(value, list) else []
    result: List[str] = []
    for item in source:
        warning = _compact_ui_diagnostic(item, _UI_WARNING_MESSAGE_LIMIT)
        if warning and warning not in result:
            result.append(warning)
    depth_summary_present = any(
        warning.startswith(("Depth failed:", "Depth 실패:"))
        for warning in result
    )
    motion_summary_present = any(
        warning.startswith(("Motion Guide failed:", "Motion Guide 실패:"))
        for warning in result
    )
    if depth_summary_present:
        result = [
            warning for warning in result
            if not (
                "optional depth artifact failed" in warning.lower()
                or "optional @video" in warning.lower()
                and " depth " in f" {warning.lower()} "
                and "artifact was not published" in warning.lower()
            )
            or warning.startswith(("Depth failed:", "Depth 실패:"))
        ]
    if motion_summary_present:
        result = [
            warning for warning in result
            if not (
                "optional motion guide artifact failed" in warning.lower()
                or "optional @video" in warning.lower()
                and "motion guide" in warning.lower()
                and "artifact was not published" in warning.lower()
            )
            or warning.startswith((
                "Motion Guide failed:",
                "Motion Guide 실패:",
            ))
        ]
    return result[-20:]


def _compact_motion_guide_report_for_state(value: Any) -> Dict[str, Any]:
    """Build a bounded typed summary for transported widget state.

    The complete, already validated report remains in the `.hmb.json` sidecar.
    Per-frame samples plus per-target channel/driver/landmark descriptors are
    sidecar-only; together they can exceed four megabytes for one character.
    PromptLibrary needs only the signed policy/count fields and semantic groups
    to classify the companion, so retain exactly that bounded authority.
    """
    if not isinstance(value, dict):
        return {}
    compaction_profile = "hmb_motion_guide_ui_summary_v1"

    def has_heavy_key(item: Any) -> bool:
        if isinstance(item, dict):
            if set(item).intersection({
                "motion_frames",
                "face_channels",
                "face_drivers",
                "face_landmarks",
                "face_edges",
                "detailed_vertex_paths",
            }):
                return True
            return any(has_heavy_key(nested) for nested in item.values())
        if isinstance(item, list):
            return any(has_heavy_key(nested) for nested in item)
        return False

    if (
        _clean(value.get("state_compaction_profile")) == compaction_profile
        and "motion_frames" not in value
        and not has_heavy_key(value)
        and len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ) < 65536
    ):
        return copy.deepcopy(value)

    report: Dict[str, Any] = {}
    # Preserve top-level scalar policy/count evidence. Long path collections,
    # palette maps, audits, and frame/target payloads stay in the sidecar.
    top_level_scalar_fields = {
        "schema", "schema_version", "profile", "space", "representation",
        "source", "appearance_authority", "camera_authority",
        "motion_authority", "visibility_policy", "joint_selection_policy",
        "occlusion_policy", "target_count", "joint_target_count",
        "rigid_target_count", "total_point_samples", "frame_count",
        "sample_count", "hidden_path_count",
    }
    for key in top_level_scalar_fields:
        item = value.get(key)
        if isinstance(item, bool) or item is None or isinstance(item, (int, float)):
            report[key] = item
        elif isinstance(item, str):
            report[key] = item[:512]

    face_source = (
        value.get("face_semantics")
        if isinstance(value.get("face_semantics"), dict)
        else {}
    )
    face_summary: Dict[str, Any] = {}
    face_scalar_fields = {
        "schema", "schema_version", "channel_source_policy",
        "controller_policy", "localization_policy", "raster_policy",
        "visibility_policy", "partial_contour_policy",
        "visibility_opportunity_policy", "ray_scope",
        "unknown_alias_policy", "curve_geometry_rendered", "target_count",
        "channel_count", "driver_count", "landmark_count",
        "channel_sample_count", "driver_sample_count",
        "rasterized_sample_count", "visibility_opportunity_count",
        "hidden_or_occluded_sample_count",
    }
    for key in face_scalar_fields:
        item = face_source.get(key)
        if isinstance(item, bool) or item is None or isinstance(item, (int, float)):
            face_summary[key] = item
        elif isinstance(item, str):
            face_summary[key] = item[:512]
    report["face_semantics"] = face_summary

    allowed_groups = {"brow", "eyelid", "mouth", "jaw"}
    report_groups = {
        _clean(item)
        for item in (
            value.get("semantic_groups")
            if isinstance(value.get("semantic_groups"), list)
            else []
        )
        if _clean(item) in allowed_groups
    }
    target_summaries: List[Dict[str, Any]] = []
    raw_targets = value.get("targets")
    if isinstance(raw_targets, list):
        for raw_target in raw_targets[:64]:
            if not isinstance(raw_target, dict):
                continue
            target_summary: Dict[str, Any] = {}
            for key in (
                "target_index", "label", "mode", "source_root",
                "target_type", "joint_count", "edge_count",
                "face_channel_count", "face_driver_count",
                "face_landmark_count", "face_edge_count",
            ):
                item = raw_target.get(key)
                if isinstance(item, bool) or item is None or isinstance(item, (int, float)):
                    target_summary[key] = item
                elif isinstance(item, str):
                    target_summary[key] = item[:128]
            groups = {
                _clean(item)
                for item in (
                    raw_target.get("semantic_groups")
                    if isinstance(raw_target.get("semantic_groups"), list)
                    else []
                )
                if _clean(item) in allowed_groups
            }
            for channel in (
                raw_target.get("face_channels")
                if isinstance(raw_target.get("face_channels"), list)
                else []
            ):
                group = (
                    _clean(channel.get("group"))
                    if isinstance(channel, dict)
                    else ""
                )
                if group in allowed_groups:
                    groups.add(group)
            report_groups.update(groups)
            target_summary["semantic_groups"] = sorted(groups)
            for field, count_field in (
                ("face_channels", "face_channel_count"),
                ("face_drivers", "face_driver_count"),
                ("face_landmarks", "face_landmark_count"),
                ("face_edges", "face_edge_count"),
                ("joints", "joint_count"),
                ("edges", "edge_count"),
            ):
                source_list = raw_target.get(field)
                if isinstance(source_list, list):
                    target_summary[count_field] = len(source_list)
                elif count_field in raw_target:
                    try:
                        target_summary[count_field] = max(
                            0,
                            int(raw_target.get(count_field) or 0),
                        )
                    except Exception:
                        target_summary[count_field] = 0
            target_summaries.append(target_summary)
    report["targets"] = target_summaries
    report["semantic_groups"] = sorted(report_groups)

    motion_frames = value.get("motion_frames")
    if isinstance(motion_frames, list):
        report["motion_frame_count"] = len(motion_frames)
    else:
        try:
            report["motion_frame_count"] = max(
                0,
                int(value.get("motion_frame_count") or 0),
            )
        except Exception:
            report["motion_frame_count"] = 0
    try:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        report["full_report_sha256"] = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
    except Exception:
        report["full_report_sha256"] = ""
    report["motion_frames_in_sidecar"] = True
    report["target_details_in_sidecar"] = True
    report["state_compaction_profile"] = compaction_profile
    report_size = len(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    if report_size >= 65536:
        # The known schema remains far below this guard. If a future Maya
        # version adds unusually many targets, retain aggregate authority and
        # semantic groups rather than publishing an oversized node payload.
        report["targets"] = []
        report["targets_omitted_from_state"] = True
        report_size = len(
            json.dumps(
                report,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    report["state_report_bytes"] = report_size
    return report


def _compact_video_payload_for_state(value: Any) -> Dict[str, Any]:
    payload = dict(value) if isinstance(value, dict) else {}
    if isinstance(payload.get("motion_guide_report"), dict):
        payload["motion_guide_report"] = (
            _compact_motion_guide_report_for_state(
                payload.get("motion_guide_report")
            )
        )
    return payload


# Shot routing publishes media only through ``media_by_source_uid``.  Its
# sibling metadata is semantic-only, so runtime/project paths must not cross
# this private snapshot boundary when new Picker fields are added later.
_SHOT_VIDEO_METADATA_FIELDS = frozenset({
    "video_uid", "source_uid", "label", "generation_role", "media_kind",
    "video_role", "source_type_hint", "control_role_hint", "camera",
    "run_id", "pair_run_id", "bundle_run_id", "created_at_ms",
    "catalog_order", "source_fps", "output_fps", "fps", "start_frame",
    "end_frame", "frame_count", "source_frame_count", "output_frame_count",
    "decoded_frame_count", "source_duration_seconds", "output_duration_seconds",
    "duration_seconds", "timebase", "width", "height", "output_width",
    "output_height", "resolution", "available_color_picks", "markers",
    "frame_metadata", "frame_domain", "timing_cues", "reference_capabilities",
    "companion_video_uid", "source_video_uid", "companion_of_video_uid",
    "companion_of_video_slot", "source_video_slot", "depth_profile",
    "motion_guide_profile", "depth_range_report", "motion_guide_report",
})
_SHOT_VIDEO_METADATA_MEDIA_KEYS = frozenset({
    "path", "asset_path", "video_path", "project_video_path", "video_url",
    "media", "media_value", "data", "data_uri", "base64", "blob", "bytes",
    "binary", "url", "reference_file", "maya_executable", "relative_path",
})
_SHOT_VIDEO_METADATA_PRIVATE_KEY_TOKENS = (
    "sidecar",
    "thumbnail",
    "thumb",
    "cache",
)
_SHOT_VIDEO_METADATA_IDENTITY_PATH_KEYS = frozenset({
    # Maya DAG identities are not filesystem/media paths.
    "full_dag_path",
})
_SHOT_VIDEO_METADATA_OMIT = object()


def _is_maya_full_dag_path(value: Any) -> bool:
    """Accept a Maya full DAG identity, never a filesystem/media path."""

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


def _semantic_shot_video_metadata_value(value: Any, key: str = "") -> Any:
    """Return a semantic copy, omitting local/project/private media fields."""

    normalized_key = _clean(key).casefold()
    if normalized_key == "full_dag_path":
        return value if _is_maya_full_dag_path(value) else _SHOT_VIDEO_METADATA_OMIT
    if normalized_key:
        path_like = (
            normalized_key.endswith("_path")
            or normalized_key.endswith("_url")
            or normalized_key.endswith("_folder")
            or normalized_key.endswith("_directory")
            or normalized_key.endswith("_file")
        )
        if (
            normalized_key in _SHOT_VIDEO_METADATA_MEDIA_KEYS
            or "base64" in normalized_key
            or any(
                token in normalized_key
                for token in _SHOT_VIDEO_METADATA_PRIVATE_KEY_TOKENS
            )
            or (
                path_like
                and normalized_key not in _SHOT_VIDEO_METADATA_IDENTITY_PATH_KEYS
            )
        ):
            return _SHOT_VIDEO_METADATA_OMIT
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            field = _clean(raw_key)
            if not field:
                continue
            semantic = _semantic_shot_video_metadata_value(raw_value, field)
            if semantic is not _SHOT_VIDEO_METADATA_OMIT:
                result[field] = semantic
        return result
    if isinstance(value, (list, tuple)):
        result_list: List[Any] = []
        for item in value:
            semantic = _semantic_shot_video_metadata_value(item)
            if semantic is not _SHOT_VIDEO_METADATA_OMIT:
                result_list.append(semantic)
        return result_list
    if _looks_like_private_media_string(value):
        return _SHOT_VIDEO_METADATA_OMIT
    return copy.deepcopy(value)


def _compact_slot_recovery_fallback(value: Any) -> Dict[str, Any]:
    item = dict(value) if isinstance(value, dict) else {}
    if isinstance(item.get("payload"), dict):
        item["payload"] = _compact_video_payload_for_state(item["payload"])
    return item


def _compact_auxiliary_failure_warning(
    label: Any,
    detail: Any,
    *,
    language: str = "ko",
) -> str:
    """Summarize an optional artifact failure without publishing path dumps."""
    label_text = _clean(label)
    detail_text = _clean(detail)
    role = (
        "Depth"
        if "depth" in label_text.lower()
        else "Motion Guide"
        if "motion" in label_text.lower()
        else label_text or "Auxiliary output"
    )
    count_match = re.search(
        r"failed\s+for\s+([0-9]+)\s+of\s+([0-9]+)",
        detail_text,
        flags=re.IGNORECASE,
    )
    unsupported_controls = bool(
        re.search(
            r"unsupported\s+depth\s+shape\s+type|nurbsCurve|locator",
            detail_text,
            flags=re.IGNORECASE,
        )
    )
    if _clean(language).lower() == "ko":
        if count_match:
            if role == "Depth" and unsupported_controls:
                return (
                    "Depth 실패: 지원되지 않는 컨트롤 "
                    f"{count_match.group(1)}개"
                )
            return (
                f"{role} 실패: 처리하지 못한 경로 {count_match.group(1)}개/"
                f"전체 {count_match.group(2)}개. 자세한 내용은 로그를 확인하세요."
            )
        return f"{role} 실패: 자세한 원인은 로그를 확인하세요."
    if count_match:
        if role == "Depth" and unsupported_controls:
            return (
                "Depth failed: "
                f"{count_match.group(1)} unsupported controls."
            )
        return (
            f"{role} failed: {count_match.group(1)} of "
            f"{count_match.group(2)} paths could not be processed. See the log."
        )
    compact_detail = _compact_ui_diagnostic(
        detail_text,
        _UI_WARNING_MESSAGE_LIMIT - len(role) - 48,
    )
    return _compact_ui_diagnostic(
        f"{role} failed: {compact_detail or 'see the diagnostic log.'}",
        _UI_WARNING_MESSAGE_LIMIT,
    )


def _append_full_diagnostic_log(path: Any, label: Any, detail: Any) -> None:
    """Best-effort append of full diagnostics that are intentionally not UI state."""
    try:
        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(
                "\n[{0}] {1}\n{2}\n".format(
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    _clean(label) or "HMB DIAGNOSTIC",
                    _clean(detail),
                )
            )
    except Exception as exc:
        _diagnostic_exception("full diagnostic log append failed", exc)


def _normalize_activity_log(value: Any) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    if not isinstance(value, list):
        return entries
    for raw in value:
        if isinstance(raw, str):
            message = _compact_ui_diagnostic(
                raw,
                _UI_ACTIVITY_MESSAGE_LIMIT,
            )
            if message:
                entries.append({"time": "", "level": "INFO", "message": message})
            continue
        if not isinstance(raw, dict):
            continue
        message = _compact_ui_diagnostic(
            raw.get("message"),
            _UI_ACTIVITY_MESSAGE_LIMIT,
        )
        if not message:
            continue
        entries.append({
            "time": _clean(raw.get("time")),
            "level": (_clean(raw.get("level")) or "INFO").upper(),
            "message": message,
        })
    return entries[-80:]


def _format_activity_log_entry(entry: Dict[str, Any]) -> str:
    message = _clean(entry.get("message"))
    if not message:
        return ""
    timestamp = _clean(entry.get("time")) or "--:--:--"
    level = (_clean(entry.get("level")) or "INFO").upper()
    return f"[{timestamp}] {level}  {message}"


def _structured_activity_log_text(value: Any) -> str:
    return "\n".join(
        line for line in (_format_activity_log_entry(entry) for entry in _normalize_activity_log(value)) if line
    )


def _editable_activity_log_text(state: Dict[str, Any]) -> str:
    explicit = str(state.get("activity_log_text") or "")
    if explicit or bool(state.get("activity_log_text_user_edited")) or bool(state.get("activity_log_cleared")):
        return explicit
    return _structured_activity_log_text(state.get("activity_log"))


def _append_activity_log(state: Dict[str, Any], level: str, message: str) -> Dict[str, Any]:
    text = _compact_ui_diagnostic(message, _UI_ACTIVITY_MESSAGE_LIMIT)
    if not text:
        return state
    entry = {
        "time": time.strftime("%H:%M:%S"),
        "level": (_clean(level) or "INFO").upper(),
        "message": text,
    }
    existing_text = _editable_activity_log_text(state).rstrip()
    entries = _normalize_activity_log(state.get("activity_log"))
    entries.append(entry)
    state["activity_log"] = entries[-80:]
    line = _format_activity_log_entry(entry)
    combined_text = f"{existing_text}\n{line}" if existing_text else line
    state["activity_log_text"] = combined_text[-32000:]
    state["activity_log_cleared"] = False
    return state


def _merge_activity_logs(primary: Any, secondary: Any) -> List[Dict[str, str]]:
    """Preserve native entries when an older widget callback arrives late."""
    merged: List[Dict[str, str]] = []
    seen = set()
    for entry in _normalize_activity_log(primary) + _normalize_activity_log(secondary):
        key = (_clean(entry.get("time")), _clean(entry.get("level")), _clean(entry.get("message")))
        if not key[2] or key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return merged[-80:]


def _normalize_markers(value: Any, video_slot: Optional[int] = None) -> List[Dict[str, Any]]:
    markers: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return markers
    seen_colors = set()
    seen_instances: set[tuple[str, ...]] = set()
    fallback_slot = max(1, min(MAX_VIDEO_SLOTS, int(video_slot or 1)))
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            continue
        color = _clean(raw.get("color"))
        asset_id = _clean(raw.get("asset_id"))
        if color not in MARKER_ORDER or not asset_id:
            continue
        maya_uuid = _clean(raw.get("maya_uuid"))
        full_dag_path = _clean(
            raw.get("full_dag_path") or raw.get("subject_root")
        )
        reference_node = _clean(raw.get("reference_node"))
        instance_identity = (
            ("uuid", maya_uuid.casefold())
            if maya_uuid
            else ("dag", full_dag_path.replace("\\", "/").casefold())
            if full_dag_path
            else (
                "legacy_asset",
                reference_node.casefold(),
                asset_id.casefold(),
            )
        )
        if instance_identity in seen_instances:
            continue
        if color in seen_colors and color not in REPEATABLE_MARKERS:
            continue
        seen_colors.add(color)
        seen_instances.add(instance_identity)
        try:
            marker_slot = max(1, min(MAX_VIDEO_SLOTS, int(raw.get("video_slot") or fallback_slot)))
        except Exception:
            marker_slot = fallback_slot
        try:
            picker_order = max(1, int(raw.get("picker_order") or index))
        except Exception:
            picker_order = index
        markers.append({
            "color": color,
            "asset_id": asset_id,
            "subject_root": full_dag_path,
            "group_name": _clean(raw.get("group_name")) or asset_id,
            "full_dag_path": full_dag_path,
            "maya_uuid": maya_uuid,
            "reference_node": reference_node,
            "reference_file": _clean(raw.get("reference_file")),
            "proxy_manager": _clean(raw.get("proxy_manager")),
            "proxy_tag": _clean(raw.get("proxy_tag")),
            "shader_model": _clean(raw.get("shader_model")),
            "visual_profile": _clean(raw.get("visual_profile")),
            "out_rim": _clean(raw.get("out_rim")),
            "shading_profile": (
                dict(raw.get("shading_profile"))
                if isinstance(raw.get("shading_profile"), dict)
                else {}
            ),
            "video_slot": marker_slot,
            "picker_order": picker_order,
        })
    return markers


def _normalize_assignment_bindings(value: Any, video_slot: Optional[int] = None) -> List[Dict[str, Any]]:
    bindings: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return bindings
    fallback_slot = max(1, min(MAX_VIDEO_SLOTS, int(video_slot or 1)))
    seen_objects: set[tuple[str, str]] = set()
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            continue
        full_dag_path = _clean(raw.get("full_dag_path") or raw.get("subject_root"))
        group_name = _clean(raw.get("group_name") or raw.get("display_name") or full_dag_path)
        maya_uuid = _clean(raw.get("maya_uuid"))
        # A catalog-selection collapse or an older widget echo could merge the
        # same editable Mask row into @video1 more than once.  Color edits then
        # replaced only the first copy and left the stale shader assignment in
        # the Maya job.  Maya UUID is the authoritative identity; exact DAG path
        # is the compatibility fallback for legacy rows without UUID metadata.
        object_identity = (
            ("uuid", maya_uuid.lower())
            if maya_uuid
            else ("path", full_dag_path.replace("\\", "/").lower())
            if full_dag_path
            else ("", "")
        )
        if object_identity[0] and object_identity in seen_objects:
            continue
        if object_identity[0]:
            seen_objects.add(object_identity)
        reference_node = _clean(raw.get("reference_node"))
        reference_file = _clean(raw.get("reference_file"))
        proxy_manager = _clean(raw.get("proxy_manager"))
        proxy_tag = _clean(raw.get("proxy_tag"))
        color = _clean(raw.get("color"))
        try:
            binding_slot = max(1, min(MAX_VIDEO_SLOTS, int(raw.get("video_slot") or fallback_slot)))
        except Exception:
            binding_slot = fallback_slot
        try:
            picker_order = max(1, int(raw.get("picker_order") or index))
        except Exception:
            picker_order = index
        bindings.append({
            "group_name": group_name,
            "full_dag_path": full_dag_path,
            "maya_uuid": maya_uuid,
            "reference_node": reference_node,
            "reference_file": reference_file,
            "proxy_manager": proxy_manager,
            "proxy_tag": proxy_tag,
            "color": color,
            "enabled": bool(raw.get("enabled", True)),
            "video_slot": binding_slot,
            "picker_order": picker_order,
        })
    bindings.sort(key=lambda item: int(item.get("picker_order") or 0))
    return bindings


def _normalize_slot_assignments(
    value: Any,
    active_count: int,
    videos: Optional[List[Dict[str, Any]]] = None,
    diagnostics: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    by_slot: Dict[int, List[Dict[str, Any]]] = {}
    if isinstance(value, list):
        for row_index, raw in enumerate(value, start=1):
            if not isinstance(raw, dict):
                continue
            requested_slot = _readable_video_slot(raw.get("video_slot"))
            slot = requested_slot or _normalized_video_slot(raw.get("video_slot"), 1)
            slot = max(1, min(active_count, slot))
            bindings = _normalize_assignment_bindings(raw.get("bindings"), slot)
            if slot in by_slot and bindings and diagnostics is not None:
                diagnostics.append(
                    f"Merged duplicate readable assignment row {row_index} into @video{slot} "
                    "instead of overwriting the earlier bindings."
                )
            by_slot.setdefault(slot, []).extend(bindings)
    if videos:
        for item in videos:
            if not isinstance(item, dict):
                continue
            slot = max(
                1,
                min(
                    active_count,
                    _normalized_video_slot(item.get("video_slot"), 1),
                ),
            )
            if by_slot.get(slot):
                continue
            inferred: List[Dict[str, Any]] = []
            for index, marker in enumerate(_normalize_markers(item.get("markers"), slot), start=1):
                inferred.append({
                    "group_name": _clean(marker.get("asset_id")) or _clean(marker.get("subject_root")).split("|")[-1],
                    "full_dag_path": _clean(marker.get("subject_root")),
                    "maya_uuid": _clean(marker.get("maya_uuid")),
                    "reference_node": _clean(marker.get("reference_node")),
                    "reference_file": _clean(marker.get("reference_file")),
                    "proxy_manager": _clean(marker.get("proxy_manager")),
                    "proxy_tag": _clean(marker.get("proxy_tag")),
                    "color": _clean(marker.get("color")),
                    "enabled": True,
                    "video_slot": slot,
                    "picker_order": max(1, int(marker.get("picker_order") or index)),
                })
            by_slot[slot] = inferred
    return [
        {
            "video_slot": slot,
            "bindings": _normalize_assignment_bindings(
                by_slot.get(slot, []),
                slot,
            ),
        }
        for slot in range(1, active_count + 1)
    ]


def _outliner_selection_after_read(
    outliner_nodes: Any,
    slot_assignments: Any,
    selected_video_slot: Any,
    previous_path: Any = "",
    previous_uuid: Any = "",
) -> Dict[str, str]:
    """Choose a usable Color Pick target immediately after a Maya READ.

    Maya UUID is preferred when a re-read changes a DAG path. A new scene has
    no previous target, so its first root (or first readable node) becomes the
    explicit selection instead of leaving every Color Pick button disabled.
    The displayed color is restored only from the currently edited video slot.
    """
    nodes = (
        [dict(item) for item in outliner_nodes if isinstance(item, dict)]
        if isinstance(outliner_nodes, list)
        else []
    )
    readable_nodes = [item for item in nodes if _clean(item.get("full_path"))]
    if not readable_nodes:
        return {"path": "", "name": "", "uuid": "", "color": ""}

    requested_uuid = _clean(previous_uuid)
    requested_path = _clean(previous_path)
    selected = None
    if requested_uuid:
        selected = next(
            (
                item for item in readable_nodes
                if _clean(item.get("maya_uuid")).casefold() == requested_uuid.casefold()
            ),
            None,
        )
    if selected is None and requested_path:
        selected = next(
            (item for item in readable_nodes if _clean(item.get("full_path")) == requested_path),
            None,
        )
    if selected is None:
        selected = next(
            (item for item in readable_nodes if not _clean(item.get("parent_path"))),
            readable_nodes[0],
        )

    selected_path = _clean(selected.get("full_path"))
    selected_uuid = _clean(selected.get("maya_uuid"))
    selected_name = (
        _clean(selected.get("name") or selected.get("display_name"))
        or selected_path.rsplit("|", 1)[-1]
        or selected_path
    )
    try:
        active_slot = max(1, min(MAX_VIDEO_SLOTS, int(selected_video_slot or 1)))
    except (TypeError, ValueError):
        active_slot = 1
    selected_color = ""
    for slot_item in slot_assignments if isinstance(slot_assignments, list) else []:
        if not isinstance(slot_item, dict) or int(slot_item.get("video_slot") or 0) != active_slot:
            continue
        bindings = slot_item.get("bindings") if isinstance(slot_item.get("bindings"), list) else []
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            binding_uuid = _clean(binding.get("maya_uuid"))
            binding_path = _clean(binding.get("full_dag_path") or binding.get("subject_root"))
            same_target = bool(
                (selected_uuid and binding_uuid and selected_uuid.casefold() == binding_uuid.casefold())
                or (selected_path and binding_path and selected_path == binding_path)
            )
            if same_target:
                color = _clean(binding.get("color"))
                selected_color = color if color in MARKER_ORDER else ""
                break
        break
    return {
        "path": selected_path,
        "name": selected_name,
        "uuid": selected_uuid,
        "color": selected_color,
    }


def _slot_assignment_bindings(state: Dict[str, Any], slot: int) -> List[Dict[str, Any]]:
    for item in state.get("slot_assignments", []):
        if isinstance(item, dict) and int(item.get("video_slot") or 0) == slot:
            return _normalize_assignment_bindings(item.get("bindings"), slot)
    return []


def _normalize_video_items(
    value: Any,
    active_count: int,
    diagnostics: Optional[List[str]] = None,
    fallbacks: Optional[List[Dict[str, Any]]] = None,
    reserved_slots: Optional[set[int]] = None,
) -> List[Dict[str, Any]]:
    """Normalize incoming catalog records before 5x10 ownership compaction.

    ``video_slot`` is no longer catalog identity.  It is rebuilt from
    ``selection_order`` for the at-most-ten selected records.  Legacy states
    without selection fields are migrated by their prior slot order, while
    every retained record receives a stable ``video_uid`` that survives later
    reorder. ``_normalize_picker_workspace_fields`` then enforces 50 total.
    """
    if not isinstance(value, list):
        return []
    del active_count, fallbacks, reserved_slots
    raw_rows = [raw for raw in value if isinstance(raw, dict)]
    has_catalog_selection = any(
        "selected" in raw
        or _positive_int(raw.get("selection_order")) > 0
        for raw in raw_rows
    )
    used_uids: set[str] = set()
    records: List[Dict[str, Any]] = []
    for row_index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            continue
        legacy_slot = _readable_video_slot(raw.get("video_slot"))
        marker_slot = legacy_slot or 1
        item = dict(raw)
        had_stable_uid = bool(
            _clean(raw.get("video_uid") or raw.get("source_uid"))
        )
        uid = _clean(raw.get("video_uid") or raw.get("source_uid"))
        if not uid or uid in used_uids:
            identity = {
                "scene_path": _clean(raw.get("scene_path")),
                "video_path": _clean(raw.get("video_path")),
                "project_video_path": _clean(raw.get("project_video_path")),
                "video_url": _clean(raw.get("video_url")),
                "media_kind": _clean(raw.get("media_kind")),
                "generation_role": _clean(raw.get("generation_role")),
                "run_id": _clean(raw.get("run_id")),
                "pair_run_id": _clean(raw.get("pair_run_id")),
                "bundle_run_id": _clean(raw.get("bundle_run_id")),
                "legacy_video_slot": legacy_slot,
                "legacy_row": row_index,
            }
            digest = hashlib.sha256(
                json.dumps(
                    identity,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:24]
            uid = f"video-{digest}"
            collision_index = 1
            while uid in used_uids:
                collision_index += 1
                uid = f"video-{digest}-{collision_index}"
        used_uids.add(uid)
        item["video_uid"] = uid
        # ``source_uid`` is an intentional alias shared with Image Asset and
        # lets Prompt retain one stable-identity implementation for both media.
        item["source_uid"] = uid
        item["catalog_order"] = max(
            1,
            _positive_int(raw.get("catalog_order")) or row_index,
        )
        if (
            legacy_slot
            and not had_stable_uid
            and not _positive_int(item.get("legacy_video_slot"))
        ):
            item["legacy_video_slot"] = legacy_slot
        item["video_path"] = _clean(raw.get("video_path"))
        item["project_video_path"] = _clean(raw.get("project_video_path"))
        item["video_url"] = _clean(raw.get("video_url"))
        item["thumbnail_url"] = _clean(raw.get("thumbnail_url"))
        item["thumbnail_runtime_id"] = _clean(
            raw.get("thumbnail_runtime_id")
        )
        item["thumbnail_source_signature"] = _clean(
            raw.get("thumbnail_source_signature")
        )
        item["camera"] = _clean(raw.get("camera"))
        item["markers"] = _normalize_markers(raw.get("markers"), marker_slot)
        if isinstance(raw.get("motion_guide_report"), dict):
            item["motion_guide_report"] = (
                _compact_motion_guide_report_for_state(
                    raw.get("motion_guide_report")
                )
            )
        nested_metadata = (
            raw.get("frame_metadata")
            if isinstance(raw.get("frame_metadata"), dict)
            else {}
        )
        metadata_fallbacks = {
            "source_fps": nested_metadata.get("fps"),
            "source_frame_count": nested_metadata.get("frame_count"),
            "decoded_frame_count": nested_metadata.get("decoded_frame_count") or nested_metadata.get("frame_count"),
            "source_duration_seconds": nested_metadata.get("duration_seconds"),
            "output_width": nested_metadata.get("width"),
            "output_height": nested_metadata.get("height"),
            "start_frame": nested_metadata.get("start_frame"),
            "end_frame": nested_metadata.get("end_frame"),
        }
        for key, fallback in metadata_fallbacks.items():
            if raw.get(key) in (None, "") and fallback not in (None, ""):
                item[key] = fallback
        for key in (
            "source_fps", "output_fps", "source_duration_seconds", "output_duration_seconds"
        ):
            try:
                item[key] = float(item.get(key) or 0.0)
            except Exception:
                item[key] = 0.0
        for key in (
            "output_width", "output_height", "source_frame_count", "output_frame_count",
            "decoded_frame_count",
        ):
            try:
                item[key] = int(item.get(key) or 0)
            except Exception:
                item[key] = 0
        for key in ("start_frame", "end_frame"):
            try:
                item[key] = float(item.get(key) or 0.0)
            except Exception:
                item[key] = 0.0
        item["has_maya_frame_range"] = bool(
            raw.get("has_maya_frame_range")
            or "maya_start_frame" in raw
            or "maya_end_frame" in raw
            or (
                "start_frame" in raw
                and "end_frame" in raw
                and (
                    _finite_float(raw.get("start_frame")) != 0
                    or _finite_float(raw.get("end_frame")) != 0
                )
            )
        )
        item["frame_metadata"] = _video_frame_metadata(item, marker_slot)
        frame_domain = _video_frame_domain(item["frame_metadata"])
        item["timing_cues"] = _normalize_timing_cues(
            raw.get("timing_cues"),
            item["markers"],
            frame_domain,
        )
        raw_selection_order = _positive_int(raw.get("selection_order"))
        if has_catalog_selection:
            item["selected"] = bool(
                raw.get("selected")
                if "selected" in raw
                else raw_selection_order > 0
            )
        else:
            # Every readable legacy VIDEO slot was an active output, so migrate
            # it into the initial catalog selection in its previous order.
            item["selected"] = True
        item["selection_order"] = raw_selection_order
        item["_legacy_catalog_row"] = row_index
        item["_legacy_selection_slot"] = legacy_slot
        records.append(item)

    selected = [item for item in records if bool(item.get("selected"))]
    selected.sort(
        key=lambda item: (
            _positive_int(item.get("selection_order")) or 10**9,
            _positive_int(item.get("_legacy_selection_slot")) or 10**9,
            _positive_int(item.get("_legacy_catalog_row")) or 10**9,
        )
    )
    selected_uids = {
        _clean(item.get("video_uid"))
        for item in selected[:MAX_SELECTED_VIDEOS]
    }
    if len(selected) > MAX_SELECTED_VIDEOS and diagnostics is not None:
        diagnostics.append(
            f"Retained {len(selected)} catalog videos but limited the active "
            f"selection to {MAX_SELECTED_VIDEOS}."
        )
    ordered_selected = [
        item for item in selected if _clean(item.get("video_uid")) in selected_uids
    ][:MAX_SELECTED_VIDEOS]
    order_by_uid = {
        _clean(item.get("video_uid")): order
        for order, item in enumerate(ordered_selected, start=1)
    }
    for item in records:
        uid = _clean(item.get("video_uid"))
        order = order_by_uid.get(uid, 0)
        item["selected"] = bool(order)
        item["selection_order"] = order
        # A catalog item never owns a permanent slot.  This compatibility field
        # mirrors only the current selected order and is zero while unselected.
        item["video_slot"] = order
        item.pop("_legacy_catalog_row", None)
        item.pop("_legacy_selection_slot", None)
        item["frame_metadata"] = _video_frame_metadata(
            item,
            order or _positive_int(item.get("legacy_video_slot")) or 1,
        )
        frame_domain = _video_frame_domain(item["frame_metadata"])
        item["timing_cues"] = _normalize_timing_cues(
            item.get("timing_cues"),
            item.get("markers") if isinstance(item.get("markers"), list) else [],
            frame_domain,
        )
    return records


def _assert_picker_workspace_capacity(
    state: Dict[str, Any],
    picker_shot_uuid: Any = "",
    required_assets: int = 1,
) -> tuple[Dict[str, Any], str]:
    """Return normalized state and a captured row after strict capacity checks."""
    normalized = _parse_state(state)
    requested_workspace_uuid = _uuid_text(picker_shot_uuid) or _uuid_text(
        normalized.get("active_picker_shot_uuid")
    )
    target_row = next(
        (
            row
            for row in normalized.get("picker_shots", [])
            if isinstance(row, dict)
            and _uuid_text(row.get("workspace_uuid")) == requested_workspace_uuid
        ),
        None,
    )
    if target_row is None:
        raise ValueError("The captured Picker Shot no longer exists.")
    try:
        required = max(0, int(required_assets or 0))
    except Exception:
        required = 0
    owned_count = len(
        _picker_representative_video_uids(target_row.get("video_asset_uids"))
    )
    if owned_count + required > MAX_VIDEO_ASSETS_PER_PICKER_SHOT:
        raise RuntimeError(
            f"Shot {int(target_row.get('number') or 1)} already owns "
            f"{owned_count} video asset(s); at most "
            f"{MAX_VIDEO_ASSETS_PER_PICKER_SHOT} are allowed."
        )
    catalog_count = len(
        [item for item in normalized.get("videos", []) if isinstance(item, dict)]
    )
    picker_row_count = max(
        1,
        min(
            SHOT_ROUTING_MAX_SHOTS,
            len([
                row for row in normalized.get("picker_shots", [])
                if isinstance(row, dict)
            ]),
        ),
    )
    active_catalog_capacity = min(
        MAX_PICKER_VIDEO_ASSETS,
        picker_row_count * MAX_VIDEO_ASSETS_PER_PICKER_SHOT,
    )
    if catalog_count + required > active_catalog_capacity:
        raise RuntimeError(
            f"The {picker_row_count} active Picker Shot(s) already own "
            f"{catalog_count} video asset(s); the current catalog capacity is "
            f"{active_catalog_capacity}."
        )
    return normalized, requested_workspace_uuid


def _video_import_source_key(value: Any) -> str:
    """Return a stable same-file key for user-imported MP4 provenance."""

    text = _clean(value)
    if not text:
        return ""
    try:
        text = str(Path(text).expanduser().resolve(strict=False))
    except Exception:
        pass
    return os.path.normcase(os.path.normpath(text)).replace("\\", "/")


def _picker_workspace_imported_asset(
    state: Dict[str, Any],
    picker_shot_uuid: Any,
    source_path: Any,
) -> Optional[Dict[str, Any]]:
    """Find the same imported source only inside its captured Picker Shot."""

    normalized = _parse_state(state)
    workspace_uuid = _uuid_text(picker_shot_uuid) or _uuid_text(
        normalized.get("active_picker_shot_uuid")
    )
    source_key = _video_import_source_key(source_path)
    if not workspace_uuid or not source_key:
        return None
    row = next(
        (
            item
            for item in normalized.get("picker_shots", [])
            if isinstance(item, dict)
            and _uuid_text(item.get("workspace_uuid")) == workspace_uuid
        ),
        None,
    )
    if not isinstance(row, dict):
        return None
    owned_uids = {
        _clean(value)
        for value in row.get("video_asset_uids", [])
        if _clean(value)
    }
    for item in normalized.get("videos", []):
        if not isinstance(item, dict):
            continue
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        if uid not in owned_uids:
            continue
        if _video_import_source_key(item.get("import_source_path")) == source_key:
            return dict(item)
    return None


def _reuse_picker_imported_asset(
    state: Dict[str, Any],
    picker_shot_uuid: Any,
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """Reuse/reselect an existing imported card instead of duplicating it."""

    normalized = _parse_state(state)
    workspace_uuid = _uuid_text(picker_shot_uuid) or _uuid_text(
        normalized.get("active_picker_shot_uuid")
    )
    uid = _clean(record.get("video_uid") or record.get("source_uid"))
    rows = [
        dict(item)
        for item in normalized.get("picker_shots", [])
        if isinstance(item, dict)
    ]
    target = next(
        (
            row
            for row in rows
            if _uuid_text(row.get("workspace_uuid")) == workspace_uuid
        ),
        None,
    )
    if not isinstance(target, dict) or not uid:
        return normalized
    owned = _picker_representative_video_uids(
        target.get("video_asset_uids"), "", {
            _clean(item.get("video_uid") or item.get("source_uid"))
            for item in normalized.get("videos", [])
            if isinstance(item, dict)
        }
    )
    selected = _picker_representative_video_uids(
        target.get("selected_video_uids"),
        target.get("preview_video_uid"),
        set(owned),
    )
    changed = False
    if uid in owned and uid not in selected and len(selected) < MAX_VIDEO_SLOTS:
        selected.append(uid)
        changed = True
    if uid in owned and _clean(target.get("preview_video_uid")) != uid:
        target["preview_video_uid"] = uid
        target["selected_video_slot"] = max(1, selected.index(uid) + 1) if uid in selected else 1
        changed = True
    if changed:
        target["selected_video_uids"] = selected
        target["revision"] = max(0, int(target.get("revision") or 0)) + 1
    result = dict(normalized)
    result["picker_shots"] = rows
    return _parse_state(result)


def _append_video_asset(
    state: Dict[str, Any],
    item: Dict[str, Any],
    *,
    picker_shot_uuid: Any = "",
) -> Dict[str, Any]:
    """Append and auto-select one asset in its captured local workspace."""
    try:
        normalized, requested_workspace_uuid = _assert_picker_workspace_capacity(
            state,
            picker_shot_uuid,
            1,
        )
    except RuntimeError as exc:
        # Direct compatibility callers historically received a state result.
        # Reject overflow as an idempotent no-op while import/generation paths
        # call the strict capacity helper before creating any external asset.
        normalized = _parse_state(state)
        warning = _clean(exc) or "Picker Shot video capacity was reached."
        warnings = _normalize_ui_warnings(normalized.get("warnings"))
        if warning not in warnings:
            warnings.append(warning)
        normalized["warnings"] = warnings[-20:]
        return normalized
    catalog = [
        dict(raw) for raw in normalized.get("videos", []) if isinstance(raw, dict)
    ]
    picker_rows = [
        dict(raw)
        for raw in normalized.get("picker_shots", [])
        if isinstance(raw, dict)
    ]
    target_row = next(
        row
        for row in picker_rows
        if _uuid_text(row.get("workspace_uuid")) == requested_workspace_uuid
    )
    record = _compact_video_payload_for_state(item)
    existing_uids = {
        _clean(raw.get("video_uid") or raw.get("source_uid"))
        for raw in catalog
        if _clean(raw.get("video_uid") or raw.get("source_uid"))
    }
    uid = _clean(record.get("video_uid") or record.get("source_uid"))
    if not uid or uid in existing_uids:
        uid = f"video-{uuid.uuid4().hex}"
    thumbnail_url = (
        _clean(record.get("thumbnail_url"))
        if _clean(record.get("thumbnail_runtime_id"))
        == _VIDEO_THUMBNAIL_RUNTIME_ID
        else ""
    )
    if not thumbnail_url:
        local_video = _resolved_video_asset_path(record)
        if local_video is not None:
            thumbnail_url, thumbnail_signature = _video_asset_thumbnail_url(
                local_video,
                uid,
            )
            if thumbnail_signature:
                record["thumbnail_source_signature"] = thumbnail_signature
    if thumbnail_url:
        record["thumbnail_url"] = thumbnail_url
        record["thumbnail_runtime_id"] = _VIDEO_THUMBNAIL_RUNTIME_ID
    record.update({
        "video_uid": uid,
        "source_uid": uid,
        "picker_shot_uuid": requested_workspace_uuid,
        "catalog_order": len(catalog) + 1,
        "selected": False,
        "selection_order": 0,
        "video_slot": 0,
    })
    owned_uids = _picker_representative_video_uids(
        target_row.get("video_asset_uids"),
        "",
        existing_uids,
    )
    selected_uids = _picker_representative_video_uids(
        target_row.get("selected_video_uids"),
        target_row.get("preview_video_uid"),
        set(owned_uids),
    )
    owned_uids.append(uid)
    selected_uids.append(uid)
    target_row.update({
        "video_asset_uids": owned_uids,
        "selected_video_uids": selected_uids,
        "preview_video_uid": uid,
        "selected_video_slot": len(selected_uids),
        "revision": max(0, int(target_row.get("revision") or 0)) + 1,
    })
    catalog.append(record)
    result = dict(normalized)
    result["videos"] = catalog
    result["picker_shots"] = picker_rows
    return _parse_state(result)


def _remove_video_asset_uids(
    state: Dict[str, Any],
    video_uids: Sequence[Any],
) -> Dict[str, Any]:
    """Remove catalog records and every durable workspace reference to them."""

    normalized = _parse_state(state)
    removed = {
        _clean(value) for value in video_uids if _clean(value)
    }
    if not removed:
        return normalized
    normalized["videos"] = [
        dict(item)
        for item in normalized.get("videos", [])
        if isinstance(item, dict)
        and _clean(item.get("video_uid") or item.get("source_uid"))
        not in removed
    ]
    cleaned_rows: List[Dict[str, Any]] = []
    for raw_row in normalized.get("picker_shots", []):
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        changed = False
        for membership_key in ("video_asset_uids", "selected_video_uids"):
            membership = [
                _clean(uid)
                for uid in row.get(membership_key, [])
                if _clean(uid) and _clean(uid) not in removed
            ]
            if membership != row.get(membership_key, []):
                changed = True
            row[membership_key] = membership
        if _clean(row.get("preview_video_uid")) in removed:
            row["preview_video_uid"] = (
                row["selected_video_uids"][0]
                if row["selected_video_uids"]
                else row["video_asset_uids"][0]
                if row["video_asset_uids"]
                else ""
            )
            changed = True
        if changed:
            row["revision"] = max(0, int(row.get("revision") or 0)) + 1
        cleaned_rows.append(row)
    normalized["picker_shots"] = cleaned_rows
    if _clean(normalized.get("preview_video_uid")) in removed:
        normalized["preview_video_uid"] = ""
    if _clean(normalized.get("selected_video_uid")) in removed:
        normalized["selected_video_uid"] = ""
    return _parse_state(normalized)


def _is_generated_depth_video_item(value: Any) -> bool:
    """Recognize current and legacy Picker-generated Depth catalog records.

    Legacy camera-space outputs remain disposable generated companions, but
    only ``DEPTH_PLAYBLAST_PROFILE`` is valid downstream Depth authority.
    """
    if not isinstance(value, dict):
        return False
    if (
        _clean(value.get("generation_role")) == "depth"
        and _clean(value.get("media_kind")) == DEPTH_MEDIA_KIND
    ):
        return True
    try:
        slot = int(value.get("video_slot") or 0)
        source_slot = int(
            value.get("source_video_slot")
            or value.get("companion_of_video_slot")
            or 0
        )
    except Exception:
        return False
    return (
        slot in AUXILIARY_VIDEO_SLOTS
        and source_slot == PRIMARY_COLOR_VIDEO_SLOT
        and _clean(value.get("media_kind")) == DEPTH_MEDIA_KIND
        and _clean(value.get("video_role")) == "maya_depth_companion"
        and _clean(value.get("depth_profile"))
        in ({DEPTH_PLAYBLAST_PROFILE} | LEGACY_DEPTH_PLAYBLAST_PROFILES)
    )


def _is_generated_motion_guide_video_item(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if (
        _clean(value.get("generation_role")) == "motion_guide"
        and _clean(value.get("media_kind")) == MOTION_GUIDE_MEDIA_KIND
    ):
        return True
    try:
        slot = int(value.get("video_slot") or 0)
        source_slot = int(
            value.get("source_video_slot")
            or value.get("companion_of_video_slot")
            or 0
        )
    except Exception:
        return False
    return (
        slot in AUXILIARY_VIDEO_SLOTS
        and source_slot == PRIMARY_COLOR_VIDEO_SLOT
        and _clean(value.get("media_kind"))
        == MOTION_GUIDE_MEDIA_KIND
        and _clean(value.get("video_role"))
        == "maya_motion_guide_companion"
        and _clean(value.get("motion_guide_profile"))
        in MOTION_GUIDE_COMPATIBLE_PROFILES
    )


def _is_generated_mask_video_item(
    value: Any,
    owner_state: Optional[Dict[str, Any]] = None,
) -> bool:
    """Recognize typed Mask outputs and strongly owned legacy Color output.

    A user video can legitimately have a ``*_playblast_1.mp4`` filename and a
    run identifier, so that legacy shape alone is not ownership evidence.  A
    legacy item is disposable only when the containing state identifies the
    same run *and* its current top-level video path points to that exact item.
    New outputs use explicit role/kind metadata and do not need this migration
    check.
    """

    if not isinstance(value, dict):
        return False
    if (
        _clean(value.get("generation_role")) == "mask"
        or _clean(value.get("media_kind")) == MASK_MEDIA_KIND
        or _clean(value.get("video_role")) == "maya_color_assignment_mask"
    ):
        return True
    try:
        slot = int(value.get("video_slot") or 0)
    except Exception:
        return False
    path_text = _clean(
        value.get("video_path") or value.get("project_video_path")
    ).replace("\\", "/").lower()
    has_legacy_shape = bool(
        1 <= slot <= MAX_VIDEO_SLOTS
        and value.get("run_id")
        and re.search(r"_playblast_1\.mp4$", path_text)
    )
    if not has_legacy_shape or not isinstance(owner_state, dict):
        return False
    item_run_id = _clean(value.get("run_id"))
    state_run_id = _clean(owner_state.get("run_id"))
    if not item_run_id or item_run_id != state_run_id:
        return False
    item_paths = {
        _clean(value.get(field)).replace("\\", "/").lower()
        for field in ("video_path", "project_video_path")
        if _clean(value.get(field))
    }
    state_paths = {
        _clean(owner_state.get(field)).replace("\\", "/").lower()
        for field in ("video_path", "project_video_path")
        if _clean(owner_state.get(field))
    }
    return bool(item_paths.intersection(state_paths))


def _generation_choice_roles(state: Dict[str, Any]) -> List[str]:
    """Return the only public generation/output order for the four switches."""

    return [
        role
        for role, enabled in (
            ("original", bool(state.get("original_enabled"))),
            ("mask", bool(state.get("mask_enabled"))),
            ("depth", bool(state.get("depth_enabled"))),
            ("motion_guide", bool(state.get("motion_guide_enabled"))),
        )
        if enabled
    ]


def _mask_authoring_slot(state: Dict[str, Any]) -> int:
    """Return the cut-authoring staging slot, independent of asset order."""
    del state
    return PRIMARY_COLOR_VIDEO_SLOT


def _original_video_item_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    metadata = (
        dict(state.get("original_metadata"))
        if isinstance(state.get("original_metadata"), dict)
        else {}
    )
    resolution = (
        dict(metadata.get("resolution"))
        if isinstance(metadata.get("resolution"), dict)
        else {}
    )
    fps = float(metadata.get("fps") or 0.0)
    frame_count = int(metadata.get("frame_count") or 0)
    duration = frame_count / fps if fps > 0.0 else 0.0
    return {
        "video_slot": 1,
        "video_path": _clean(state.get("original_video_path")),
        "project_video_path": "",
        "video_url": _clean(state.get("original_video_url")),
        "camera": _clean(metadata.get("camera")),
        "markers": [],
        "source_fps": fps,
        "output_fps": fps,
        "output_width": int(resolution.get("width") or 0),
        "output_height": int(resolution.get("height") or 0),
        "source_frame_count": frame_count,
        "output_frame_count": frame_count,
        "decoded_frame_count": frame_count,
        "source_duration_seconds": duration,
        "output_duration_seconds": duration,
        "start_frame": float(metadata.get("start_frame") or 0.0),
        "end_frame": float(metadata.get("end_frame") or 0.0),
        "has_maya_frame_range": bool(frame_count),
        "generation_role": "original",
        "media_kind": ORIGINAL_MEDIA_KIND,
        "video_role": "maya_original_playblast",
        "source_type_hint": "Original Maya Viewport Reference",
        "control_role_hint": "Original Appearance and Motion Reference",
        "label": "Original Playblast",
    }


def _append_selected_generation_videos(
    state: Dict[str, Any],
    generated_by_role: Dict[str, Dict[str, Any]],
    manual_source_state: Optional[Dict[str, Any]] = None,
    *,
    selected_roles: Optional[Sequence[str]] = None,
    picker_shot_uuid: Any = "",
) -> Dict[str, Any]:
    """Compatibility entry point that now appends generation assets.

    No prior catalog record is replaced or packed. The complete validated
    bundle is capacity-checked before the first record is appended, so a
    generation can never leave an unowned partial overflow record.
    """
    # The inner Maya pass temporarily publishes validated Mask/Depth/Motion
    # rows so they can be inspected. Remove only those exact provisional UIDs
    # from the newest state before appending the finalized operation delta.
    # Replacing ``videos`` from the pre-generation snapshot would discard any
    # import, deletion, or selection committed while Maya was running.
    provisional_uids = [
        _clean(source.get("video_uid") or source.get("source_uid"))
        for source in generated_by_role.values()
        if isinstance(source, dict)
        and _clean(source.get("video_uid") or source.get("source_uid"))
    ]
    if isinstance(manual_source_state, dict):
        parsed_staging = _parse_state(state)
        for role, source in generated_by_role.items():
            if not isinstance(source, dict) or _clean(
                source.get("video_uid") or source.get("source_uid")
            ):
                continue
            source_paths = {
                _clean(source.get(field))
                for field in ("video_path", "project_video_path", "video_url")
                if _clean(source.get(field))
            }
            for item in parsed_staging.get("videos", []):
                if not isinstance(item, dict):
                    continue
                item_paths = {
                    _clean(item.get(field))
                    for field in (
                        "video_path",
                        "project_video_path",
                        "video_url",
                    )
                    if _clean(item.get(field))
                }
                uid = _clean(item.get("video_uid") or item.get("source_uid"))
                role_matches = (
                    _clean(item.get("generation_role")) == _clean(role)
                    or (
                        role == "mask"
                        and _is_generated_mask_video_item(
                            item,
                            parsed_staging,
                        )
                    )
                    or (role == "depth" and _is_generated_depth_video_item(item))
                    or (
                        role == "motion_guide"
                        and _is_generated_motion_guide_video_item(item)
                    )
                )
                if (
                    uid
                    and role_matches
                    and source_paths
                    and source_paths.intersection(item_paths)
                ):
                    provisional_uids.append(uid)
    result = _remove_video_asset_uids(state, provisional_uids)
    if isinstance(manual_source_state, dict):
        # Compatibility callers may still provide a legacy pre-generation page
        # after a staging state replaced it. Merge only missing records here.
        # The live Generate worker no longer passes this snapshot, so a user
        # deletion made during generation can never be resurrected by it.
        manual = _parse_state(manual_source_state)
        existing_uids = {
            _clean(item.get("video_uid") or item.get("source_uid"))
            for item in result.get("videos", [])
            if isinstance(item, dict)
        }
        owner_by_uid = {
            _clean(uid): _uuid_text(row.get("workspace_uuid"))
            for row in manual.get("picker_shots", [])
            if isinstance(row, dict)
            for uid in row.get("video_asset_uids", [])
            if _clean(uid)
        }
        for manual_item in manual.get("videos", []):
            if not isinstance(manual_item, dict):
                continue
            manual_uid = _clean(
                manual_item.get("video_uid") or manual_item.get("source_uid")
            )
            if not manual_uid or manual_uid in existing_uids:
                continue
            target_uuid = owner_by_uid.get(manual_uid) or _uuid_text(
                result.get("active_picker_shot_uuid")
            )
            result = _append_video_asset(
                result,
                manual_item,
                picker_shot_uuid=target_uuid,
            )
            existing_uids.add(manual_uid)
    captured_picker_shot_uuid = _uuid_text(picker_shot_uuid) or _uuid_text(
        manual_source_state.get("active_picker_shot_uuid")
        if isinstance(manual_source_state, dict)
        else state.get("active_picker_shot_uuid")
    )
    warnings = [
        _clean(item) for item in state.get("warnings", []) if _clean(item)
    ]
    requested_roles = (
        tuple(_clean(role) for role in selected_roles)
        if selected_roles is not None
        else tuple(_generation_choice_roles(state))
    )
    requested_role_set = set(requested_roles)
    ordered_roles = tuple(
        role
        for role in ("original", "mask", "depth", "motion_guide")
        if role in requested_role_set
    )
    appendable_roles = [
        role
        for role in ordered_roles
        if isinstance(generated_by_role.get(role), dict)
        and any(
            _clean(generated_by_role[role].get(field))
            for field in ("video_path", "project_video_path", "video_url")
        )
    ]
    if appendable_roles:
        result, captured_picker_shot_uuid = _assert_picker_workspace_capacity(
            result,
            captured_picker_shot_uuid,
            len(appendable_roles),
        )
    mask_uid = ""
    for role in ordered_roles:
        source = generated_by_role.get(role)
        if not isinstance(source, dict) or not any(
            _clean(source.get(field))
            for field in ("video_path", "project_video_path", "video_url")
        ):
            warning = (
                f"Selected {role.replace('_', ' ').title()} did not produce a "
                "validated video and was not added to the catalog."
            )
            if warning not in warnings:
                warnings.append(warning)
            continue
        item = _compact_video_payload_for_state(source)
        item.pop("video_uid", None)
        item.pop("source_uid", None)
        item["selected"] = False
        item["selection_order"] = 0
        item["video_slot"] = 0
        item["generation_role"] = role
        if role == "original":
            item.update({
                "media_kind": ORIGINAL_MEDIA_KIND,
                "video_role": "maya_original_playblast",
                "markers": [],
                "label": "Original Playblast",
            })
        elif role == "mask":
            item.update({
                "media_kind": MASK_MEDIA_KIND,
                "video_role": "maya_color_assignment_mask",
                "source_type_hint": "Color Assignment Mask / Segmentation Reference",
                "control_role_hint": "Object and Character Region Guidance",
                "label": "Mask",
            })
        elif role in {"depth", "motion_guide"}:
            item["companion_video_uid"] = mask_uid
            item["source_video_uid"] = mask_uid
        result = _append_video_asset(
            result,
            item,
            picker_shot_uuid=captured_picker_shot_uuid,
        )
        appended = result.get("videos", [])[-1] if result.get("videos") else {}
        if role == "mask" and isinstance(appended, dict):
            mask_uid = _clean(appended.get("video_uid"))
    result["warnings"] = warnings[-20:]
    result["selected_video_count"] = len(
        [
            item
            for item in result.get("videos", [])
            if isinstance(item, dict) and bool(item.get("selected"))
        ]
    )
    result["active_slot_count"] = max(1, result["selected_video_count"])
    result["selected_video_slot"] = max(
        1,
        min(
            result["active_slot_count"],
            result["selected_video_count"] or 1,
        ),
    )
    return _parse_state(result)



# Older serialized Python-side integrations may still resolve the former
# helper name. It now points to append-only semantics and performs no packing.
_pack_selected_generation_videos = _append_selected_generation_videos


def _resolve_generated_companion_slots(
    state: Dict[str, Any],
    *,
    depth_enabled: bool,
    motion_guide_enabled: bool,
) -> tuple[int, int]:
    """Return private Maya staging positions, independent of catalog capacity."""
    del state
    return (
        2 if depth_enabled else 0,
        (3 if depth_enabled else 2) if motion_guide_enabled else 0,
    )



def _clear_slot_ui_state(state: Dict[str, Any], slot: int) -> Dict[str, Any]:
    """Compatibility no-op: generated media never erases authored slot UI."""
    del slot
    return state


def _snapshot_created_at_ms(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except Exception:
        return 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_content_sha256(raw: Dict[str, Any]) -> str:
    supplied = _clean(raw.get("sha256") or raw.get("content_sha256")).lower()
    if re.fullmatch(r"[0-9a-f]{64}", supplied):
        return supplied
    legacy_data_uri = _clean(raw.get("data_uri") or raw.get("snapshot_data_uri"))
    if legacy_data_uri.startswith("data:image/") and "," in legacy_data_uri:
        try:
            payload = base64.b64decode(legacy_data_uri.split(",", 1)[1], validate=True)
            return hashlib.sha256(payload).hexdigest()
        except Exception:
            return hashlib.sha256(legacy_data_uri.encode("utf-8")).hexdigest()
    path_text = _clean(raw.get("path") or raw.get("snapshot_path"))
    if path_text:
        try:
            path = Path(path_text)
            if path.is_file():
                return _sha256_file(path)
        except Exception:
            pass
    return hashlib.sha256(path_text.encode("utf-8")).hexdigest() if path_text else ""


def _snapshot_media_url(raw: Dict[str, Any], path_text: str) -> str:
    supplied = _clean(raw.get("url") or raw.get("media_url") or raw.get("snapshot_url"))
    if supplied and not supplied.startswith("data:"):
        return supplied
    if not path_text:
        return ""
    try:
        return _external_media_url(Path(path_text))
    except Exception:
        return Path(path_text).as_posix()


def _snapshot_catalog_uid_by_slot(videos: Any) -> Dict[int, str]:
    """Best-effort migration map for legacy slot-only snapshot records."""
    candidates: Dict[int, List[str]] = {}
    for item in videos if isinstance(videos, list) else []:
        if not isinstance(item, dict):
            continue
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        if not uid:
            continue
        slot = _readable_video_slot(
            item.get("selection_order") or item.get("video_slot")
        )
        if slot:
            candidates.setdefault(slot, []).append(uid)
    return {
        slot: uids[0]
        for slot, uids in candidates.items()
        if len(set(uids)) == 1
    }


def _snapshot_record_signature(item: Dict[str, Any]) -> str:
    payload = {
        "video_uid": _clean(item.get("video_uid")),
        "render_video_slot": _normalized_video_slot(
            item.get("render_video_slot") or item.get("video_slot"),
            PRIMARY_COLOR_VIDEO_SLOT,
        ),
        "frame": float(item.get("frame") or item.get("snapshot_frame") or 0.0),
        "path": _clean(item.get("path") or item.get("snapshot_path")),
        "created_at_ms": _snapshot_created_at_ms(item.get("created_at_ms")),
        "sha256": _snapshot_content_sha256(item),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _normalized_snapshot_record(
    raw: Any,
    catalog_uid_by_slot: Dict[int, str],
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    path_text = _clean(raw.get("path") or raw.get("snapshot_path"))
    media_url = _snapshot_media_url(raw, path_text)
    legacy_data_uri = _clean(raw.get("data_uri") or raw.get("snapshot_data_uri"))
    content_sha256 = _snapshot_content_sha256(raw)
    # Old workflows embedded Snapshot PNGs directly in widget state.  Modern
    # state intentionally drops the heavyweight inline bytes, but the history
    # record (frame, content hash and stable UID) must survive migration even
    # when no external cache path was recorded.
    if (
        not path_text
        and not media_url
        and not legacy_data_uri.startswith("data:image/")
        and not re.fullmatch(r"[0-9a-f]{64}", content_sha256)
    ):
        return None
    render_slot = _normalized_video_slot(
        raw.get("render_video_slot") or raw.get("video_slot"),
        PRIMARY_COLOR_VIDEO_SLOT,
    )
    try:
        frame = float(raw.get("frame") or raw.get("snapshot_frame") or 0.0)
    except Exception:
        frame = 0.0
    supplied_snapshot_uid = _clean(raw.get("snapshot_uid"))
    supplied_video_uid = _clean(raw.get("video_uid"))
    # Only records from the retired slot-only schema may infer a catalog UID.
    # A modern record with an intentionally empty video_uid is an orphan and
    # must never attach itself to a different card that later occupies slot 1.
    migrated_video_uid = (
        _clean(catalog_uid_by_slot.get(render_slot))
        if not supplied_snapshot_uid and not supplied_video_uid
        else ""
    )
    record = {
        "snapshot_uid": supplied_snapshot_uid,
        "video_uid": supplied_video_uid or migrated_video_uid,
        "render_video_slot": render_slot,
        # Keep the readable compatibility name, but never use its mutable
        # selection order as the snapshot's identity.
        "video_slot": render_slot,
        "frame": frame,
        "path": path_text,
        "url": media_url,
        "sha256": content_sha256,
        "created_at_ms": _snapshot_created_at_ms(raw.get("created_at_ms")),
    }
    if not record["snapshot_uid"]:
        record["snapshot_uid"] = (
            "snapshot-legacy-" + _snapshot_record_signature(record)[:24]
        )
    return record


def _apply_active_snapshot_projection(
    state: Dict[str, Any],
    *,
    active_snapshot_uid: Any = None,
    viewport_mode: Any = None,
) -> Dict[str, Any]:
    """Project the active UID record onto the legacy scalar snapshot fields."""
    history = [
        dict(item)
        for item in state.get("snapshots", [])
        if isinstance(item, dict) and _clean(item.get("snapshot_uid"))
    ]
    by_uid = {
        _clean(item.get("snapshot_uid")): item
        for item in history
    }
    requested_uid = _clean(
        state.get("active_snapshot_uid")
        if active_snapshot_uid is None
        else active_snapshot_uid
    )
    requested_mode = _clean(
        state.get("viewport_mode") if viewport_mode is None else viewport_mode
    ).lower()
    mode = "snapshot" if requested_mode == "snapshot" else "video"
    if requested_uid not in by_uid:
        requested_uid = ""
    if mode == "snapshot" and not requested_uid and history:
        requested_uid = _clean(history[-1].get("snapshot_uid"))
    active = by_uid.get(requested_uid)
    state["snapshots"] = history
    state["active_snapshot_uid"] = requested_uid if active else ""
    state["viewport_mode"] = "snapshot" if active and mode == "snapshot" else "video"
    if active:
        state.update({
            # ``viewport_mode`` is the authoritative display selector.  Keep
            # the active record projected while Video is visible so switching
            # back to Snapshot does not discard the user's navigation point.
            "snapshot_active": mode == "snapshot",
            "snapshot_frame": float(active.get("frame") or 0.0),
            "snapshot_video_slot": _normalized_video_slot(
                active.get("render_video_slot") or active.get("video_slot"),
                PRIMARY_COLOR_VIDEO_SLOT,
            ),
            "snapshot_data_uri": "",
            "snapshot_path": _clean(active.get("path")),
            "snapshot_url": _clean(active.get("url")),
            "snapshot_sha256": _clean(active.get("sha256")),
        })
    else:
        state.update({
            "snapshot_active": False,
            "snapshot_video_slot": 0,
            "snapshot_data_uri": "",
            "snapshot_path": "",
            "snapshot_url": "",
            "snapshot_sha256": "",
        })
    return state


def _normalize_snapshot_history(
    state: Dict[str, Any],
    source: Dict[str, Any],
    recovery_diagnostics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        state["snapshot_frame"] = float(state.get("snapshot_frame") or 0.0)
    except Exception:
        state["snapshot_frame"] = 0.0
    catalog_uid_by_slot = _snapshot_catalog_uid_by_slot(state.get("videos"))
    history: List[Dict[str, Any]] = []
    history_by_uid: Dict[str, Dict[str, Any]] = {}

    def append_record(raw: Any) -> Optional[Dict[str, Any]]:
        record = _normalized_snapshot_record(raw, catalog_uid_by_slot)
        if record is None:
            return None
        uid = _clean(record.get("snapshot_uid"))
        existing = history_by_uid.get(uid)
        if existing is not None:
            if _snapshot_record_signature(existing) == _snapshot_record_signature(record):
                return existing
            conflict_base = f"{uid}-conflict-{_snapshot_record_signature(record)[:12]}"
            conflict_uid = conflict_base
            suffix = 2
            while conflict_uid in history_by_uid:
                conflict_uid = f"{conflict_base}-{suffix}"
                suffix += 1
            record["snapshot_uid"] = conflict_uid
            uid = conflict_uid
            if recovery_diagnostics is not None:
                recovery_diagnostics.append(
                    "Preserved conflicting Snapshot records by assigning a new stable UID."
                )
        history.append(record)
        history_by_uid[uid] = record
        return record

    for raw in (
        state.get("snapshots", [])
        if isinstance(state.get("snapshots"), list)
        else []
    ):
        append_record(raw)

    compatibility_record: Optional[Dict[str, Any]] = None
    compatibility_data_uri = _clean(state.get("snapshot_data_uri"))
    compatibility_uid = _clean(state.get("active_snapshot_uid"))
    if compatibility_uid in history_by_uid:
        # Modern scalar fields are a projection of this exact record. Never
        # reinterpret that lossy projection as another history entry.
        compatibility_record = history_by_uid[compatibility_uid]
    elif bool(state.get("snapshot_active")) and (
        compatibility_data_uri.startswith("data:image/")
        or _clean(state.get("snapshot_path"))
        or _clean(state.get("snapshot_url"))
    ):
        compatibility_candidate = _normalized_snapshot_record({
            "snapshot_uid": _clean(state.get("active_snapshot_uid")),
            "video_uid": _clean(state.get("snapshot_video_uid")),
            "render_video_slot": state.get("snapshot_video_slot"),
            "video_slot": state.get("snapshot_video_slot"),
            "frame": state.get("snapshot_frame"),
            "data_uri": compatibility_data_uri,
            "path": state.get("snapshot_path"),
            "url": state.get("snapshot_url"),
            "sha256": state.get("snapshot_sha256"),
            "created_at_ms": state.get("snapshot_created_at_ms"),
        }, catalog_uid_by_slot)
        if compatibility_candidate is not None:
            candidate_signature = _snapshot_record_signature(compatibility_candidate)
            compatibility_record = next(
                (
                    item for item in history
                    if _snapshot_record_signature(item) == candidate_signature
                ),
                None,
            )
            if compatibility_record is None:
                compatibility_record = append_record(compatibility_candidate)

    requested_uid = _clean(source.get("active_snapshot_uid"))
    if requested_uid not in history_by_uid:
        requested_uid = _clean(
            compatibility_record.get("snapshot_uid")
            if compatibility_record is not None
            else ""
        )
    source_mode = _clean(source.get("viewport_mode")).lower()
    if source_mode not in {"snapshot", "video"}:
        source_mode = "snapshot" if requested_uid else "video"
    state["snapshots"] = history
    if len(history) > MAX_SNAPSHOT_HISTORY:
        history = history[-MAX_SNAPSHOT_HISTORY:]
        history_by_uid = {
            _clean(item.get("snapshot_uid")): item
            for item in history
        }
        if recovery_diagnostics is not None:
            recovery_diagnostics.append(
                f"Snapshot history was limited to the newest {MAX_SNAPSHOT_HISTORY} records."
            )
        state["snapshots"] = history
    state["active_snapshot_uid"] = requested_uid
    state["viewport_mode"] = source_mode
    state["snapshot_request_video_uid"] = _clean(
        state.get("snapshot_request_video_uid")
    )
    return _apply_active_snapshot_projection(state)


def _append_snapshot_history_record(
    state: Dict[str, Any],
    record: Dict[str, Any],
    *,
    scene_path: Any = None,
) -> Dict[str, Any]:
    result = _parse_state(state)
    normalized_record = _normalized_snapshot_record(
        record,
        _snapshot_catalog_uid_by_slot(result.get("videos")),
    )
    snapshot_uid = _clean(
        normalized_record.get("snapshot_uid") if normalized_record else ""
    )
    if not snapshot_uid or normalized_record is None:
        raise ValueError("Appending Snapshot history requires snapshot_uid.")
    existing = next(
        (
            dict(item)
            for item in result.get("snapshots", [])
            if isinstance(item, dict)
            and _clean(item.get("snapshot_uid")) == snapshot_uid
        ),
        None,
    )
    if existing is not None:
        if _snapshot_record_signature(existing) != _snapshot_record_signature(
            normalized_record
        ):
            raise ValueError(
                f"Snapshot UID already identifies a different record: {snapshot_uid}"
            )
    else:
        result["snapshots"] = [
            dict(item)
            for item in result.get("snapshots", [])
            if isinstance(item, dict)
        ] + [normalized_record]
    removed = result["snapshots"][:-MAX_SNAPSHOT_HISTORY]
    if removed:
        result["snapshots"] = result["snapshots"][-MAX_SNAPSHOT_HISTORY:]
        if scene_path:
            for stale_record in removed:
                _safe_delete_snapshot_cache_file(
                    _norm_path(scene_path),
                    stale_record.get("path"),
                )
    result["active_snapshot_uid"] = snapshot_uid
    result["viewport_mode"] = "snapshot"
    return _parse_state(result)


def _parse_state(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        source = value
    else:
        try:
            source = json.loads(str(value or ""))
        except Exception:
            source = {}
    state = _default_widget_state()
    if isinstance(source, dict):
        state.update(source)
    _normalize_shot_selection_fields(state)
    _normalize_shot_catalog_watermark_fields(state)
    recovery_diagnostics: List[str] = []
    recovery_fallbacks = [
        _compact_slot_recovery_fallback(item)
        for item in (
            state.get("slot_recovery_fallbacks")
            if isinstance(state.get("slot_recovery_fallbacks"), list)
            else []
        )
        if isinstance(item, dict)
    ]
    # The packaged catalog is authoritative. Saved graphs cannot reintroduce
    # legacy colors or mutate the Maya/Prompt binding vocabulary.
    state["marker_catalog"] = MARKER_CATALOG
    state["marker_catalog_version"] = int(MARKER_CATALOG["version"])
    state["output_width"], state["output_height"] = _playblast_resolution(state)
    for key in (
        "state_revision", "writer_lifecycle_generation",
        "state_published_at_ms", "frontend_seen_revision",
    ):
        try:
            state[key] = max(0, int(float(state.get(key) or 0)))
        except Exception:
            state[key] = 0
    state["state_writer"] = _clean(state.get("state_writer"))
    state["writer_runtime_instance_id"] = _clean(
        state.get("writer_runtime_instance_id")
    )
    state["scene_stage"] = _clean(state.get("scene_stage"))
    raw_scene_fields = {
        key: state.get(key)
        for key in ("scene_path", "scene_draft_path", "scene_request_path")
    }
    strict_scene_fields = {
        key: _maya_scene_path_text(raw_value)
        for key, raw_value in raw_scene_fields.items()
    }
    invalid_scene_value = any(
        bool(_scene_path_text(raw_value)) and not strict_scene_fields[key]
        for key, raw_value in raw_scene_fields.items()
    )
    if invalid_scene_value:
        state.update({
            "scene_path": "",
            "scene_draft_path": "",
            "scene_request_path": "",
            "native_read_ready": False,
            "scene_stage": "EMPTY",
            "scene_request_status": "IDLE",
            "status": "READY",
            "message": "Select a Maya .mb or .ma scene.",
        })
    else:
        state.update(strict_scene_fields)
    try:
        active_slot_count = int(float(state.get("active_slot_count") or 1))
    except Exception:
        active_slot_count = 1
    observed_slot_count = _observed_state_slot_count(source)
    state["active_slot_count"] = max(
        1,
        min(
            MAX_VIDEO_SLOTS,
            max(active_slot_count, observed_slot_count),
        ),
    )
    # Fixed output-slot expansion notices belonged to the retired VIDEO*_OUT
    # contract. Catalog normalization below derives active count solely from
    # the current selected snapshot.
    try:
        selected_video_slot = int(float(state.get("selected_video_slot") or 1))
    except Exception:
        selected_video_slot = 1
    state["selected_video_slot"] = max(1, min(state["active_slot_count"], selected_video_slot))
    state["pending_action"] = _clean(state.get("pending_action"))
    state["pending_action_id"] = _clean(state.get("pending_action_id"))
    state["backend_ack_action_id"] = _clean(state.get("backend_ack_action_id"))
    state["maya_available"] = bool(state.get("maya_available") and _clean(state.get("maya_executable")))
    try:
        state["active_process_pid"] = max(0, int(float(state.get("active_process_pid") or 0)))
    except Exception:
        state["active_process_pid"] = 0
    state["active_process_kind"] = _clean(state.get("active_process_kind"))
    state["operation_id"] = _clean(state.get("operation_id"))
    state["operation_input_digest"] = _clean(state.get("operation_input_digest"))
    state["operation_scene_fingerprint"] = _clean(state.get("operation_scene_fingerprint"))
    state["operation_invalidated"] = bool(state.get("operation_invalidated"))
    state["operation_invalidation_reason"] = _clean(state.get("operation_invalidation_reason"))
    expanded_node_size = _normalized_picker_native_size(
        state.get("expanded_node_size"),
        minimum_height=PICKER_WIDGET_MIN_HEIGHT,
    ) or {
        "width": PICKER_START_WIDTH,
        "height": PICKER_START_HEIGHT,
    }
    state["expanded_node_size"] = {
        "width": max(
            PICKER_WIDGET_MIN_WIDTH,
            min(6000, int(round(float(expanded_node_size["width"])))),
        ),
        "height": max(
            PICKER_WIDGET_MIN_HEIGHT,
            min(6000, int(round(float(expanded_node_size["height"])))),
        ),
    }
    try:
        state["lower_panel_ratio"] = max(0.20, min(0.62, float(state.get("lower_panel_ratio") or 0.34)))
    except Exception:
        state["lower_panel_ratio"] = 0.34
    try:
        state["main_split_ratio"] = max(0.30, min(0.80, float(state.get("main_split_ratio") or 0.64)))
    except Exception:
        state["main_split_ratio"] = 0.64
    try:
        state["right_split_ratio"] = max(0.22, min(0.72, float(state.get("right_split_ratio") or 0.42)))
    except Exception:
        state["right_split_ratio"] = 0.42
    for key, minimum in (
        ("node_width", PICKER_WIDGET_MIN_WIDTH),
        ("node_height", PICKER_WIDGET_MIN_HEIGHT),
    ):
        try:
            value = int(round(float(state.get(key) or 0)))
        except Exception:
            value = 0
        state[key] = max(minimum, min(6000, value)) if value > 0 else 0
    for key, minimum in (("outliner_panel_height", 480), ("viewport_panel_height", 636)):
        try:
            value = int(round(float(state.get(key) or 0)))
        except Exception:
            value = 0
        state[key] = max(minimum, min(6000, value)) if value > 0 else 0
    right_section_defaults = {"settings": 217, "color": 628, "log": 208}
    try:
        source_layout_version = max(1, int(float(source.get("ui_layout_version") or 1)))
    except Exception:
        source_layout_version = 1
    if source_layout_version < 4:
        # Release stale outer height from the former available-space
        # fitting mode. Panel heights and all functional state are preserved.
        state["node_height"] = 0
    if source_layout_version < 2:
        legacy_defaults = {"settings": 190, "color": 412, "log": 208}
        legacy_heights = (
            source.get("right_section_heights")
            if isinstance(source.get("right_section_heights"), dict)
            else {}
        )
        raw_right_section_heights = dict(legacy_defaults)
        raw_right_section_heights.update(legacy_heights)
        try:
            legacy_color = int(round(float(raw_right_section_heights.get("color", 412))))
        except Exception:
            legacy_color = 412
        try:
            legacy_log = int(round(float(raw_right_section_heights.get("log", 208))))
        except Exception:
            legacy_log = 208
        raw_right_section_heights["color"] = legacy_color + legacy_log + 8
        try:
            legacy_viewport_height = int(round(float(source.get("viewport_panel_height") or 0)))
        except Exception:
            legacy_viewport_height = 0
        if legacy_viewport_height > 0:
            state["viewport_panel_height"] = max(636, min(6000, legacy_viewport_height - legacy_log - 8))
    else:
        raw_right_section_heights = (
            state.get("right_section_heights")
            if isinstance(state.get("right_section_heights"), dict)
            else {}
        )
    normalized_right_section_heights: Dict[str, int] = {}
    for key, default in right_section_defaults.items():
        try:
            value = int(round(float(raw_right_section_heights.get(key, default))))
        except Exception:
            value = default
        normalized_right_section_heights[key] = max(96, min(900, value))
    if source_layout_version == 5:
        normalized_right_section_heights["settings"] = max(
            96,
            min(
                900,
                normalized_right_section_heights["settings"] - 68,
            ),
        )
    state["right_section_heights"] = normalized_right_section_heights
    state["ui_layout_version"] = 6
    state["ui_theme"] = "T" if _clean(state.get("ui_theme")).upper() == "T" else "P"
    reserved_video_control_slots: set[int] = set()
    for raw in (
        state.get("slot_assignments")
        if isinstance(state.get("slot_assignments"), list)
        else []
    ):
        if (
            isinstance(raw, dict)
            and isinstance(raw.get("bindings"), list)
            and any(isinstance(binding, dict) for binding in raw["bindings"])
        ):
            slot = _readable_video_slot(raw.get("video_slot"))
            if slot:
                reserved_video_control_slots.add(slot)
    for raw in (
        state.get("slot_visibility")
        if isinstance(state.get("slot_visibility"), list)
        else []
    ):
        if isinstance(raw, dict) and raw.get("hidden_paths"):
            slot = _readable_video_slot(raw.get("video_slot"))
            if slot:
                reserved_video_control_slots.add(slot)
    for raw in (
        state.get("snapshots")
        if isinstance(state.get("snapshots"), list)
        else []
    ):
        if isinstance(raw, dict) and _clean(raw.get("data_uri")).startswith("data:image/"):
            slot = _readable_video_slot(raw.get("video_slot"))
            if slot:
                reserved_video_control_slots.add(slot)
    state["videos"] = _normalize_video_items(
        state.get("videos"),
        state["active_slot_count"],
        recovery_diagnostics,
        recovery_fallbacks,
        reserved_video_control_slots,
    )
    # Normalize the active Shot's ordered selection before computing derived
    # slot/count/hash fields.  Up to ten selected videos remain durable.
    preselected_uids = _picker_selected_video_uids(state)
    prerepresentative = _picker_representative_video_uids(
        preselected_uids,
        state.get("preview_video_uid") or state.get("selected_video_uid"),
        {
            _clean(item.get("video_uid") or item.get("source_uid"))
            for item in state["videos"]
            if isinstance(item, dict)
        },
    )
    selected_order_by_uid = {
        uid: index + 1 for index, uid in enumerate(prerepresentative)
    }
    for item in state["videos"]:
        if not isinstance(item, dict):
            continue
        uid = _clean(item.get("video_uid") or item.get("source_uid"))
        selection_order = selected_order_by_uid.get(uid, 0)
        selected = bool(selection_order)
        item["selected"] = selected
        item["selection_order"] = selection_order
        item["video_slot"] = selection_order
        if isinstance(item.get("frame_metadata"), dict):
            item["frame_metadata"]["video_slot"] = (
                f"@video{selection_order}" if selected else ""
            )
    selected_video_count = len(
        [
            item
            for item in state["videos"]
            if isinstance(item, dict) and bool(item.get("selected"))
        ]
    )
    state["selected_video_count"] = min(
        MAX_REPRESENTATIVE_VIDEOS,
        selected_video_count,
    )
    state["max_selected_videos"] = MAX_REPRESENTATIVE_VIDEOS
    selection_identity = [
        {
            "video_uid": _clean(item.get("video_uid")),
            "selection_order": _positive_int(item.get("selection_order")),
            "media": _clean(
                item.get("project_video_path")
                or item.get("video_path")
                or item.get("video_url")
            ),
        }
        for item in state["videos"]
        if isinstance(item, dict) and bool(item.get("selected"))
    ]
    selection_identity.sort(key=lambda item: int(item["selection_order"]))
    state["selection_id"] = hashlib.sha256(
        json.dumps(
            selection_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    # Keep one empty authoring row for legacy Maya controls. Public media count
    # is carried separately and may correctly be zero.
    state["active_slot_count"] = max(1, state["selected_video_count"])
    state["selected_video_slot"] = max(
        1,
        min(
            state["active_slot_count"],
            int(state.get("selected_video_slot") or 1),
        ),
    )
    requested_preview_uid = _clean(
        state.get("preview_video_uid") or state.get("selected_video_uid")
    )
    catalog_by_uid = {
        _clean(item.get("video_uid")): item
        for item in state["videos"]
        if isinstance(item, dict) and _clean(item.get("video_uid"))
    }
    if requested_preview_uid not in catalog_by_uid:
        requested_preview_uid = next(
            (
                _clean(item.get("video_uid"))
                for item in state["videos"]
                if isinstance(item, dict) and bool(item.get("selected"))
            ),
            "",
        )
    preview_item = catalog_by_uid.get(requested_preview_uid, {})
    preview_order = _positive_int(preview_item.get("selection_order"))
    if preview_order:
        state["selected_video_slot"] = preview_order
    state["preview_video_uid"] = requested_preview_uid
    state["selected_video_uid"] = requested_preview_uid
    state["selected_video_path"] = _clean(
        preview_item.get("project_video_path")
        or preview_item.get("video_path")
        or preview_item.get("video_url")
    )
    state["video_library_version"] = 1
    state["markers"] = _normalize_markers(state.get("markers"), state["selected_video_slot"])
    state["slot_assignments"] = _normalize_slot_assignments(
        state.get("slot_assignments"),
        state["active_slot_count"],
        [
            item
            for item in state.get("videos", [])
            if isinstance(item, dict) and bool(item.get("selected"))
        ],
        recovery_diagnostics,
    )
    visibility_by_slot: Dict[int, List[str]] = {}
    for row_index, raw in enumerate(
        state.get("slot_visibility", [])
        if isinstance(state.get("slot_visibility"), list)
        else [],
        start=1,
    ):
        if not isinstance(raw, dict):
            continue
        slot = max(
            1,
            min(
                state["active_slot_count"],
                _normalized_video_slot(raw.get("video_slot"), 1),
            ),
        )
        hidden_paths = []
        for path_value in raw.get("hidden_paths", []) if isinstance(raw.get("hidden_paths"), list) else []:
            path_text = _clean(path_value)
            if path_text and path_text not in hidden_paths:
                hidden_paths.append(path_text)
        if slot in visibility_by_slot and hidden_paths:
            recovery_diagnostics.append(
                f"Merged duplicate readable visibility row {row_index} into "
                f"@video{slot} instead of overwriting earlier eye exclusions."
            )
        retained_paths = visibility_by_slot.setdefault(slot, [])
        for path_text in hidden_paths:
            if path_text not in retained_paths:
                retained_paths.append(path_text)
    state["slot_visibility"] = [
        {"video_slot": slot, "hidden_paths": visibility_by_slot.get(slot, [])}
        for slot in range(1, state["active_slot_count"] + 1)
    ]
    state["workspace_view"] = "playblast" if _clean(state.get("workspace_view")).lower() == "playblast" else "outliner"
    state["selected_outliner_path"] = _clean(state.get("selected_outliner_path"))
    state["selected_outliner_name"] = _clean(state.get("selected_outliner_name"))
    state["selected_outliner_uuid"] = _clean(state.get("selected_outliner_uuid"))
    state["selected_color"] = _clean(state.get("selected_color"))
    state["selected_camera"] = _clean(state.get("selected_camera"))
    state["video_url"] = _clean(state.get("video_url"))
    state["original_video_path"] = _clean(state.get("original_video_path"))
    state["original_video_url"] = _clean(state.get("original_video_url"))
    state["original_metadata"] = (
        dict(state.get("original_metadata"))
        if isinstance(state.get("original_metadata"), dict)
        else {}
    )
    state["original_enabled"] = bool(state.get("original_enabled"))
    # Saved states predate the Mask switch and therefore retain the historical
    # Generate behaviour (Color Assignment/Mask enabled) on first migration.
    state["mask_enabled"] = bool(
        state.get("mask_enabled", True)
    )
    try:
        state["mask_authoring_slot"] = max(
            1,
            min(
                MAX_VIDEO_SLOTS,
                int(state.get("mask_authoring_slot") or PRIMARY_COLOR_VIDEO_SLOT),
            ),
        )
    except Exception:
        state["mask_authoring_slot"] = PRIMARY_COLOR_VIDEO_SLOT
    state["original_preview_enabled"] = bool(
        state.get("original_preview_enabled")
        and (state["original_video_path"] or state["original_video_url"])
    )
    state["depth_enabled"] = bool(state.get("depth_enabled"))
    state["motion_guide_enabled"] = bool(
        state.get("motion_guide_enabled")
    )
    for key in ("depth_video_slot", "motion_guide_video_slot"):
        try:
            typed_slot = int(state.get(key) or 0)
        except Exception:
            typed_slot = 0
        state[key] = typed_slot if typed_slot in AUXILIARY_VIDEO_SLOTS else 0
    state = _normalize_snapshot_history(
        state,
        source,
        recovery_diagnostics,
    )
    try:
        state["operation_video_slot"] = max(
            0,
            min(MAX_VIDEO_SLOTS, int(state.get("operation_video_slot") or 0)),
        )
    except Exception:
        state["operation_video_slot"] = 0
    state["native_read_ready"] = bool(state.get("native_read_ready"))
    state["native_read_mode"] = _clean(state.get("native_read_mode"))
    state["native_source_version"] = _clean(state.get("native_source_version"))
    state["native_metadata"] = dict(state.get("native_metadata")) if isinstance(state.get("native_metadata"), dict) else {}
    for key in ("start_frame", "end_frame", "current_frame"):
        try:
            state[key] = float(state.get(key) or 0.0)
        except Exception:
            state[key] = 0.0
    state["language"] = "en" if _clean(state.get("language")).lower() == "en" else "ko"
    state["outliner_search"] = _clean(state.get("outliner_search"))
    outliner_nodes = state.get("outliner_nodes") if isinstance(state.get("outliner_nodes"), list) else []
    cameras = state.get("cameras") if isinstance(state.get("cameras"), list) else []
    state["outliner_nodes"] = [dict(item) for item in outliner_nodes if isinstance(item, dict)]
    state["cameras"] = [dict(item) for item in cameras if isinstance(item, dict)]
    state["outliner_expanded"] = [_clean(item) for item in state.get("outliner_expanded", []) if _clean(item)] if isinstance(state.get("outliner_expanded"), list) else []
    state["warnings"] = _normalize_ui_warnings(state.get("warnings"))
    for diagnostic in recovery_diagnostics:
        compact_diagnostic = _compact_ui_diagnostic(
            diagnostic,
            _UI_WARNING_MESSAGE_LIMIT,
        )
        if compact_diagnostic and compact_diagnostic not in state["warnings"]:
            state["warnings"].append(compact_diagnostic)
    state["warnings"] = state["warnings"][-20:]
    state["slot_recovery_fallbacks"] = recovery_fallbacks
    state["activity_log"] = _normalize_activity_log(state.get("activity_log"))
    state["activity_log_text"] = str(state.get("activity_log_text") or "")[-32000:]
    state["activity_log_text_user_edited"] = bool(state.get("activity_log_text_user_edited"))
    state["activity_log_cleared"] = bool(state.get("activity_log_cleared"))
    for key in (
        "maya_executable", "maya_version", "last_log_path", "log_folder", "operation_kind",
        "python_core_path", "runtime_instance_id", "scene_request_id", "scene_request_source",
        "scene_request_status",
    ):
        state[key] = _clean(state.get(key))
    state["python_core_loaded"] = bool(state.get("python_core_loaded"))
    for key in ("operation_started_at_ms", "operation_finished_at_ms"):
        try:
            state[key] = max(0, int(float(state.get(key) or 0)))
        except Exception:
            state[key] = 0
    try:
        state["last_operation_seconds"] = max(0.0, float(state.get("last_operation_seconds") or 0.0))
    except Exception:
        state["last_operation_seconds"] = 0.0
    _normalize_picker_workspace_fields(
        state,
        source.get("picker_shots") if isinstance(source, dict) else None,
        picker_shots_present=isinstance(source, dict) and "picker_shots" in source,
    )
    return state


_PICKER_RESET_DURABLE_FIELDS = (
    "videos",
    "shot_publisher_instance_uuid",
    "channel_uuid",
    "shot_uuid",
    "shot_number",
    "shot_name",
    "shot_selections",
    "accepted_shot_catalog_publisher_instance_uuid",
    "accepted_shot_catalog_channel_uuid",
    "accepted_shot_catalog_generation",
    "accepted_shot_catalog_metadata_sha256",
    "active_picker_shot_uuid",
    "picker_legacy_membership_fallbacks",
)


def _reset_picker_state_preserving_loader_media(value: Any) -> Dict[str, Any]:
    """Return fresh authoring/runtime state with the durable Loader intact."""

    source = _parse_state(value)
    reset = _default_widget_state()
    for field in _PICKER_RESET_DURABLE_FIELDS:
        reset[field] = copy.deepcopy(source.get(field))

    reset_rows: List[Dict[str, Any]] = []
    for raw_row in source.get("picker_shots", []):
        if not isinstance(raw_row, dict):
            continue
        row = {
            "workspace_uuid": _uuid_text(raw_row.get("workspace_uuid")),
            "number": int(raw_row.get("number") or len(reset_rows) + 1),
            "name": _clean(raw_row.get("name"))[:128],
            "custom_name": bool(raw_row.get("custom_name")),
            # A Reset is a newer row transaction even though its Loader
            # membership is unchanged. This prevents a queued authoring echo
            # from restoring the retired scene context on the new instance.
            "revision": max(0, int(raw_row.get("revision") or 0)) + 1,
            "bound_shot_uuid": _uuid_text(
                raw_row.get("bound_shot_uuid")
            ),
            "video_asset_uids": copy.deepcopy(
                raw_row.get("video_asset_uids")
                if isinstance(raw_row.get("video_asset_uids"), list)
                else []
            ),
            "selected_video_uids": copy.deepcopy(
                raw_row.get("selected_video_uids")
                if isinstance(raw_row.get("selected_video_uids"), list)
                else []
            ),
            "preview_video_uid": _clean(
                raw_row.get("preview_video_uid")
            ),
            "scene_draft_path": "",
            "current_frame": 0.0,
            "viewport_mode": "video",
            "active_snapshot_uid": "",
            "selected_video_slot": max(
                1,
                int(raw_row.get("selected_video_slot") or 1),
            ),
            "authoring_context": _empty_picker_authoring_context(),
        }
        reset_rows.append(row)
    if reset_rows:
        reset["picker_shots"] = reset_rows
        active_workspace_uuid = _uuid_text(
            source.get("active_picker_shot_uuid")
        )
        active_row = next(
            (
                row
                for row in reset_rows
                if _uuid_text(row.get("workspace_uuid"))
                == active_workspace_uuid
            ),
            reset_rows[0],
        )
        # The top-level fields are the retained widget projection of the
        # active Loader row.  Supplying the projection before normalization is
        # essential: otherwise the parser legitimately falls back to the first
        # catalog item and Reset silently moves a user's preview cursor even
        # though the row-local selection/order survived.
        active_preview_uid = _clean(active_row.get("preview_video_uid"))
        active_selected_uids = list(
            active_row.get("selected_video_uids") or []
        )
        reset["preview_video_uid"] = active_preview_uid
        reset["selected_video_uid"] = active_preview_uid
        reset["selected_video_slot"] = max(
            1,
            int(active_row.get("selected_video_slot") or 1),
        )
        reset["active_slot_count"] = max(1, len(active_selected_uids))

    reset["state_revision"] = max(
        0,
        int(source.get("state_revision") or 0),
    ) + 1
    normalized = _parse_state(reset)
    # Parsing projects the active Loader selection, but Reset deliberately
    # leaves every Maya/Snapshot/log/error field at the new-instance default.
    normalized["status"] = "READY"
    normalized["scene_stage"] = "EMPTY"
    normalized["message"] = "Browse to a Maya scene, then press READ."
    normalized["warnings"] = []
    normalized["activity_log"] = []
    normalized["activity_log_text"] = ""
    return _parse_state(normalized)


def _picker_library_marker(
    marker: Dict[str, Any],
    slot: int,
    order: int,
    video_uid: str,
) -> Dict[str, Any]:
    return {
        "asset_id": _clean(marker.get("asset_id")),
        "color": _clean(marker.get("color")),
        "subject_root": _clean(
            marker.get("subject_root") or marker.get("full_dag_path")
        ),
        "group_name": _clean(marker.get("group_name"))
        or _clean(marker.get("asset_id")),
        "full_dag_path": _clean(
            marker.get("full_dag_path") or marker.get("subject_root")
        ),
        "maya_uuid": _clean(marker.get("maya_uuid")),
        "reference_node": _clean(marker.get("reference_node")),
        "reference_file": _clean(marker.get("reference_file")),
        "proxy_manager": _clean(marker.get("proxy_manager")),
        "proxy_tag": _clean(marker.get("proxy_tag")),
        "video_uid": video_uid,
        "source_uid": video_uid,
        "video_slot": slot,
        "picker_order": max(1, int(marker.get("picker_order") or order)),
    }


def _is_remote_video_reference(value: Any) -> bool:
    """Return whether a reference can be consumed without a local file."""

    text = _clean(value)
    if not text:
        return False
    parsed = urlparse(text)
    scheme = parsed.scheme.lower()
    if scheme in {"http", "https"}:
        return bool(parsed.netloc)
    if scheme == "asset":
        return bool(parsed.netloc or parsed.path)
    return False


def _probe_readable_video_reference(value: Any) -> Optional[Path]:
    """Resolve and probe one reference without transaction-level caching."""

    text = _clean(value)
    if not text or _is_remote_video_reference(text):
        return None
    parsed = urlparse(text)
    is_explicit_path = bool(
        parsed.scheme.lower() == "file"
        or Path(text).is_absolute()
        or re.match(r"^[A-Za-z]:[\\/]", text)
        or text.startswith(("\\\\", "//"))
    )
    if is_explicit_path:
        # Absolute local and UNC paths are already authoritative. Sending them
        # through Griptape's project File resolver can reinterpret a server
        # share as a project-relative path and incorrectly report it missing.
        try:
            resolved = _norm_path(text)
        except Exception:
            return None
    else:
        try:
            from griptape_nodes.files.file import File  # type: ignore

            resolved = Path(File(text).resolve())
        except Exception:
            # Relative project paths must never fall back to the process working
            # directory. Griptape's File resolver is the active-project authority.
            return None
    try:
        if not resolved.is_file() or resolved.stat().st_size <= 0:
            return None
        with resolved.open("rb") as handle:
            if not handle.read(1):
                return None
    except OSError:
        return None
    return resolved


def _resolve_readable_video_reference(
    value: Any,
    *,
    probe_cache: Optional[Dict[str, Optional[Path]]] = None,
) -> Optional[Path]:
    """Resolve one readable reference, sharing probes inside one state revision.

    Building public output and up to five per-Shot snapshots used to open and
    stat the same selected file repeatedly.  Callers now pass one short-lived
    cache for a coherent state synchronization; the cache is never retained
    across revisions, so an external file removal is still observed on the next
    publication.
    """

    key = _clean(value)
    if probe_cache is not None and key in probe_cache:
        return probe_cache[key]
    resolved = _probe_readable_video_reference(value)
    if probe_cache is not None and key:
        probe_cache[key] = resolved
    return resolved


def _selected_video_label(item: Dict[str, Any]) -> str:
    label = _clean(item.get("label"))
    if label:
        return label
    reference = _clean(
        item.get("project_video_path")
        or item.get("video_path")
        or item.get("video_url")
    )
    if reference:
        parsed = urlparse(reference)
        name_source = unquote(parsed.path) if parsed.scheme else reference
        stem = Path(name_source).stem
        if stem:
            return stem
    return _clean(item.get("video_uid")) or "selected video"


def _select_synchronized_video_media(
    item: Dict[str, Any],
    *,
    enforce_media_availability: bool,
    probe_cache: Optional[Dict[str, Optional[Path]]] = None,
) -> str:
    """Choose one output reference, validating local candidates when required."""

    if not enforce_media_availability:
        return _clean(
            item.get("project_video_path")
            or item.get("video_path")
            or item.get("video_url")
        )

    project_reference = _clean(item.get("project_video_path"))
    local_reference = _clean(item.get("video_path"))
    had_local_candidate = bool(project_reference or local_reference)

    for field, reference in (
        ("project_video_path", project_reference),
        ("video_path", local_reference),
    ):
        if not reference:
            continue
        if _is_remote_video_reference(reference):
            if field == "video_path":
                item["project_video_path"] = ""
            return reference
        resolved_reference = (
            _resolve_readable_video_reference(reference)
            if probe_cache is None
            else _resolve_readable_video_reference(
                reference,
                probe_cache=probe_cache,
            )
        )
        if resolved_reference is not None:
            if field == "video_path":
                # The project copy is stale, so it must not remain authoritative
                # in PICKER_OUT after the verified local-source fallback.
                item["project_video_path"] = ""
            return reference
        item[field] = ""

    # Picker-generated video_url values point at its local preview server. If a
    # local-origin item has disappeared, passing that preview URL would only
    # defer the same failure to the upload/generation node.
    if had_local_candidate:
        return ""

    remote_reference = _clean(item.get("video_url"))
    return remote_reference if _is_remote_video_reference(remote_reference) else ""


def _build_synchronized_video_outputs(
    state: Dict[str, Any],
    *,
    enforce_media_availability: bool = False,
    probe_cache: Optional[Dict[str, Optional[Path]]] = None,
) -> tuple[Dict[str, Any], List[str]]:
    """Build Prompt metadata and generator media from one selected snapshot."""
    normalized = _parse_state(state)
    selected = [
        dict(item)
        for item in normalized.get("videos", [])
        if isinstance(item, dict) and bool(item.get("selected"))
    ]
    selected.sort(key=lambda item: _positive_int(item.get("selection_order")))

    resolved: List[tuple[Dict[str, Any], str]] = []
    omitted_uids: List[str] = []
    unavailable_videos: List[Dict[str, str]] = []
    for item in selected[:MAX_SELECTED_VIDEOS]:
        media = _select_synchronized_video_media(
            item,
            enforce_media_availability=enforce_media_availability,
            probe_cache=probe_cache,
        )
        if media:
            resolved.append((item, media))
        else:
            uid = _clean(item.get("video_uid"))
            omitted_uids.append(uid)
            if enforce_media_availability:
                unavailable_videos.append(
                    {
                        "video_uid": uid,
                        "label": _selected_video_label(item),
                        "reason": "local_reference_missing_or_unreadable",
                    }
                )

    media_blocked = bool(enforce_media_availability and unavailable_videos)
    if media_blocked:
        # Never renumber or partially forward the remaining valid selection.
        # An incomplete reference set can materially change a generation.
        resolved = []

    transient_slot_by_uid = {
        _clean(item.get("video_uid")): slot
        for slot, (item, _media) in enumerate(resolved, start=1)
    }
    mask_uid_by_bundle: Dict[str, str] = {}
    for item, _media in resolved:
        if _clean(item.get("generation_role")) != "mask" and _clean(
            item.get("media_kind")
        ) != MASK_MEDIA_KIND:
            continue
        bundle_id = _clean(item.get("bundle_run_id") or item.get("pair_run_id"))
        if bundle_id:
            mask_uid_by_bundle[bundle_id] = _clean(item.get("video_uid"))

    videos_payload: List[Dict[str, Any]] = []
    aggregate_markers: List[Dict[str, Any]] = []
    frame_metadata_payload: List[Dict[str, Any]] = []
    media_values: List[str] = []
    for slot, (item, media) in enumerate(resolved, start=1):
        uid = _clean(item.get("video_uid"))
        markers = [
            _picker_library_marker(marker, slot, marker_order, uid)
            for marker_order, marker in enumerate(
                _normalize_markers(item.get("markers"), slot),
                start=1,
            )
        ]
        aggregate_markers.extend(markers)
        frame_metadata = _video_frame_metadata(
            {**item, "video_slot": slot, "markers": markers},
            slot,
        )
        frame_metadata["video_uid"] = uid
        frame_metadata["source_uid"] = uid
        frame_metadata["selection_order"] = slot
        frame_metadata_payload.append(frame_metadata)
        frame_domain = _video_frame_domain(frame_metadata)
        timing_cues = _normalize_timing_cues(
            item.get("timing_cues"),
            markers,
            frame_domain,
        )
        reference_capabilities = _video_reference_capabilities(
            frame_domain,
            timing_cues,
        )
        local_video_path = _clean(item.get("video_path"))
        project_video_path = _clean(item.get("project_video_path"))
        video_payload: Dict[str, Any] = {
            "video_uid": uid,
            "source_uid": uid,
            "order_key": uid,
            "selected": True,
            "selection_order": slot,
            "video_slot": slot,
            # This is the exact string in VIDEO_OUT, so Prompt metadata and the
            # generator can never describe different selected media.
            "video_path": media,
            "camera": _clean(item.get("camera")),
            "markers": markers,
            "fps": frame_metadata["fps"],
            "start_frame": frame_metadata["start_frame"],
            "end_frame": frame_metadata["end_frame"],
            "frame_count": frame_metadata["frame_count"],
            "duration_seconds": frame_metadata["duration_seconds"],
            "timebase": frame_metadata["timebase"],
            "width": frame_metadata["width"],
            "height": frame_metadata["height"],
            "available_color_picks": frame_metadata["available_color_picks"],
            "frame_metadata": frame_metadata,
            "frame_domain": frame_domain,
            "timing_cues": timing_cues,
            "reference_capabilities": reference_capabilities,
        }
        if local_video_path and local_video_path != media:
            video_payload["local_video_path"] = local_video_path
        if project_video_path:
            video_payload["project_video_path"] = project_video_path
        for identity_field in ("run_id", "pair_run_id", "bundle_run_id"):
            identity_value = _clean(item.get(identity_field))
            if identity_value:
                video_payload[identity_field] = identity_value
        for field in (
            "generation_role",
            "media_kind",
            "video_role",
            "source_type_hint",
            "control_role_hint",
            "depth_profile",
            "motion_guide_profile",
            "label",
        ):
            field_value = _clean(item.get(field))
            if field_value:
                video_payload[field] = field_value

        companion_uid = _clean(
            item.get("companion_video_uid") or item.get("source_video_uid")
        )
        if not companion_uid and _clean(item.get("generation_role")) in {
            "depth",
            "motion_guide",
        }:
            bundle_id = _clean(
                item.get("bundle_run_id") or item.get("pair_run_id")
            )
            companion_uid = mask_uid_by_bundle.get(bundle_id, "")
        companion_slot = transient_slot_by_uid.get(companion_uid, 0)
        if companion_uid or _clean(item.get("generation_role")) in {
            "depth",
            "motion_guide",
        }:
            video_payload["companion_video_uid"] = companion_uid
            video_payload["source_video_uid"] = companion_uid
            video_payload["companion_of_video_slot"] = companion_slot
            video_payload["source_video_slot"] = companion_slot
        if isinstance(item.get("depth_range_report"), dict):
            video_payload["depth_range_report"] = dict(
                item["depth_range_report"]
            )
        if isinstance(item.get("motion_guide_report"), dict):
            video_payload["motion_guide_report"] = (
                _compact_motion_guide_report_for_state(
                    item["motion_guide_report"]
                )
            )
        videos_payload.append(video_payload)
        media_values.append(media)

    selection_identity = [
        {
            "video_uid": item["video_uid"],
            "selection_order": item["selection_order"],
            "media": media,
        }
        for item, media in zip(videos_payload, media_values)
    ]
    selection_id = hashlib.sha256(
        json.dumps(
            selection_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    semantic: Dict[str, Any] = {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "scene_path": _clean(normalized.get("scene_path")),
        "scene_fingerprint": _scene_fingerprint(normalized.get("scene_path")),
        "marker_catalog_version": int(MARKER_CATALOG["version"]),
        "media_ready": bool(videos_payload),
        "active_slot_count": len(videos_payload),
        "selected_video_count": len(videos_payload),
        "max_selected_videos": MAX_REPRESENTATIVE_VIDEOS,
        "selection_id": selection_id,
        "ordered_video_uids": [
            _clean(item.get("video_uid")) for item in videos_payload
        ],
        "catalog_video_count": len(
            [
                item
                for item in normalized.get("videos", [])
                if isinstance(item, dict)
            ]
        ),
        "videos": videos_payload,
        "markers": aggregate_markers,
        "frame_metadata": frame_metadata_payload,
        "frame_metadata_schema_version": 1,
        "reference_capability_schema": VIDEO_REFERENCE_CAPABILITY_SCHEMA,
        "reference_capability_schema_version": (
            VIDEO_REFERENCE_CAPABILITY_VERSION
        ),
        "timing_cue_schema": VIDEO_TIMING_CUE_SCHEMA,
        "timing_cue_schema_version": VIDEO_TIMING_CUE_VERSION,
    }
    if media_blocked:
        unavailable_labels = ", ".join(
            item["label"] for item in unavailable_videos
        )
        blocking_error = (
            "Selected reference video is unavailable in the active Griptape "
            f"project: {unavailable_labels}. Re-import the MP4 or regenerate "
            "its Playblast in HMBVideoPickerLibrary, then retry."
        )
        semantic.update(
            {
                "media_blocked": True,
                "blocking_error_code": "LOCAL_REFERENCE_MISSING",
                "blocking_error": blocking_error,
                "requested_selected_video_count": len(
                    selected[:MAX_SELECTED_VIDEOS]
                ),
                "unavailable_video_uids": omitted_uids,
                "unavailable_videos": unavailable_videos,
                "warnings": [blocking_error],
            }
        )
    elif omitted_uids:
        semantic["warnings"] = [
            "Selected catalog records without media references were omitted from "
            "both PICKER_OUT and VIDEO_OUT: " + ", ".join(omitted_uids)
        ]
    canonical = json.dumps(
        semantic,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        {
            "run_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            **semantic,
        },
        media_values,
    )


def _recover_orphaned_runtime_state(value: Any) -> tuple[Dict[str, Any], bool]:
    """Remove one-shot commands and impossible busy states from an old runtime."""
    state = _parse_state(value)
    pending_action = _clean(state.get("pending_action"))
    pending_action_id = _clean(state.get("pending_action_id"))
    status = _clean(state.get("status")).upper()
    scene_stage = _clean(state.get("scene_stage")).upper()
    operation_kind = _clean(state.get("operation_kind"))
    busy_statuses = {
        "READ_PENDING", "RUN_PENDING", "SCANNING_SCENE", "READING_SCENE",
        "RUNNING", "GENERATING_VIDEO", "SNAPSHOT_PENDING", "SNAPSHOT_RENDERING",
        "GENERATING_ORIGINAL",
        "CANCELLING",
    }
    busy_stages = {
        "UI_COMMAND_PENDING", "PYTHON_COMMAND_RECEIVED", "MAYA_READING",
        "GENERATING_ORIGINAL", "CANCELLING",
    }
    orphaned_busy = bool(
        status in busy_statuses
        or scene_stage in busy_stages
        or operation_kind in {
            "read_scene", "run_video", "render_snapshot", "render_original_preview",
        }
    )
    if not pending_action and not orphaned_busy:
        return state, False

    state["pending_action"] = ""
    state["pending_action_id"] = ""
    if pending_action_id:
        state["backend_ack_action_id"] = pending_action_id

    if orphaned_busy:
        state["operation_kind"] = ""
        state["operation_id"] = ""
        state["operation_started_at_ms"] = 0
        state["operation_finished_at_ms"] = int(time.time() * 1000)
        state["last_operation_seconds"] = 0.0
        scene_text = next(
            (
                candidate
                for candidate in (
                    _maya_scene_path_text(state.get("scene_draft_path")),
                    _maya_scene_path_text(state.get("scene_request_path")),
                    _maya_scene_path_text(state.get("scene_path")),
                )
                if candidate
            ),
            "",
        )
        if not scene_text:
            state.update({
                "scene_path": "",
                "scene_draft_path": "",
                "scene_request_path": "",
                "native_read_ready": False,
            })
        valid_scene = bool(scene_text)
        if state.get("native_read_ready"):
            ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
            state["status"] = ready_stage
            state["scene_stage"] = ready_stage
            state["scene_request_status"] = "COMPLETE"
            state["message"] = "Recovered the completed Maya snapshot after the Python runtime restarted."
        elif valid_scene:
            state["status"] = "READY"
            state["scene_stage"] = "LOAD_READY"
            state["scene_request_status"] = "COMPLETE"
            state["message"] = "Recovered the selected Maya scene after restart. Press READ to scan it."
        else:
            state["status"] = "EMPTY"
            state["scene_stage"] = "EMPTY"
            state["scene_request_status"] = "IDLE"
            state["message"] = "Select a Maya .mb or .ma file."
        _append_activity_log(
            state,
            "WARNING",
            "Recovered an unfinished command from a previous Python runtime; no stale action was replayed.",
        )
    return _parse_state(state), True



def _default_picker_command(runtime_instance_id: str = "") -> Dict[str, Any]:
    return {
        "schema": COMMAND_SCHEMA,
        "version": COMMAND_VERSION,
        "runtime_instance_id": _clean(runtime_instance_id),
        "action": "",
        "action_id": "",
        "issued_at_ms": 0,
        "payload": {},
    }


def _parse_picker_command(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        source = dict(value)
    else:
        try:
            parsed = json.loads(str(value or ""))
            source = dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            source = {}
    command = _default_picker_command(source.get("runtime_instance_id"))
    command["schema"] = COMMAND_SCHEMA
    command["version"] = COMMAND_VERSION
    command["action"] = _clean(source.get("action"))
    command["action_id"] = _clean(source.get("action_id"))
    try:
        command["issued_at_ms"] = max(0, int(float(source.get("issued_at_ms") or 0)))
    except Exception:
        command["issued_at_ms"] = 0
    command["payload"] = dict(source.get("payload")) if isinstance(source.get("payload"), dict) else {}
    return command


def _configure_picker_command_parameter(parameter: Any) -> None:
    if parameter is None:
        return
    attributes = [
        ("type", "dict"),
        ("input_types", ["dict"]),
        ("settable", True),
        ("hide", True),
        ("hide_property", True),
        # SaveWorkflow serializes parameter_values. Keep the full Shot/media
        # catalog durable instead of treating this widget value as ephemeral.
        ("serializable", True),
    ]
    mode = _mode_set("PROPERTY")
    if mode is not None:
        attributes.append(("allowed_modes", mode))
    else:
        attributes.extend((("allow_input", False), ("allow_output", False), ("allow_property", True)))
    for attribute, value in attributes:
        try:
            setattr(parameter, attribute, value)
        except Exception as exc:
            _diagnostic_exception(f"Command parameter attribute {attribute} setup failed", exc)
    try:
        setattr(parameter, "default_value", _parse_picker_command(getattr(parameter, "default_value", None)))
    except Exception as exc:
        _diagnostic_exception("Command parameter default normalization failed", exc)
    try:
        options = dict(getattr(parameter, "ui_options", {}) or {})
        options.update({
            "display_name": "",
            "is_full_width": True,
            "height": 0,
            "min_height": 0,
            "max_height": 0,
            # Griptape classifies every custom widget as an expandable row
            # unless this flag is explicitly false. This invisible command
            # bridge must remain mounted, but must never share the node's free
            # height with the visible picker dashboard.
            "expandable": False,
            "compact": True,
            "resizable": False,
            "hide_label": True,
            "hide_handles": True,
            "hide": True,
            "hide_property": True,
        })
        setattr(parameter, "ui_options", options)
    except Exception as exc:
        _diagnostic_exception("Command parameter UI configuration failed", exc)


def _add_picker_command_bridge(node: Any) -> None:
    if parameter_exists(node, WIDGET_COMMAND_PARAMETER):
        _configure_picker_command_parameter(_get_parameter_obj(node, WIDGET_COMMAND_PARAMETER))
        return
    kwargs: Dict[str, Any] = {
        "name": WIDGET_COMMAND_PARAMETER,
        "default_value": _default_picker_command(getattr(node, "_hmb_runtime_instance_id", "")),
        "type": "dict",
        "input_types": ["dict"],
        "tooltip": "Ephemeral minimal JSON command transport for HMBVideoPickerLibrary.",
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
        },
    }
    mode = _mode_set("PROPERTY")
    if mode is not None:
        kwargs["allowed_modes"] = mode
    else:
        kwargs.update({"allow_input": False, "allow_output": False, "allow_property": True})
    parameter = Parameter(**kwargs)
    node.add_parameter(parameter)
    _configure_picker_command_parameter(parameter)

def _configure_picker_widget_parameter(parameter: Any) -> None:
    """Use Griptape's native structured-value custom-widget contract."""
    if parameter is None:
        return
    attributes = [
        ("type", "dict"),
        ("input_types", ["dict"]),
        ("settable", True),
        # Explicitly clear a stale host allocator latch. Older Picker builds
        # could leave this serializable state row hidden as Collapsed (3),
        # preventing the saved media catalog from ever reaching the widget.
        ("hide", False),
        ("hide_property", False),
        ("serializable", True),
    ]
    mode = _mode_set("PROPERTY")
    if mode is not None:
        attributes.append(("allowed_modes", mode))
    else:
        attributes.extend((
            ("allow_input", False),
            ("allow_output", False),
            ("allow_property", True),
        ))
    for attribute, value in attributes:
        try:
            setattr(parameter, attribute, value)
        except Exception as exc:
            _diagnostic_exception(f"Picker state parameter attribute configuration failed for {attribute}", exc)
    if Widget is not None:
        has_widget = False
        try:
            finder = getattr(parameter, "find_elements_by_type", None)
            if callable(finder):
                has_widget = bool(finder(Widget, find_recursively=True))
        except Exception:
            has_widget = False
        if not has_widget:
            try:
                parameter.add_trait(Widget(name=WIDGET_NAME, library=WIDGET_LIBRARY_NAME))
            except Exception as exc:
                _diagnostic_exception("Picker state widget compatibility trait registration failed", exc)
    try:
        current = getattr(parameter, "default_value", None)
        setattr(parameter, "default_value", _parse_state(current))
    except Exception as exc:
        _diagnostic_exception("Picker state default normalization failed", exc)
    try:
        options = dict(getattr(parameter, "ui_options", {}) or {})
        options.update({
            "display_name": "HMBVideoPickerLibrary",
            "is_full_width": True,
            "height": PICKER_WIDGET_START_HEIGHT,
            "min_height": PICKER_WIDGET_COMPACT_MOUNT_HEIGHT,
            "widget_height": PICKER_WIDGET_START_HEIGHT,
            "width": PICKER_START_WIDTH,
            "min_width": PICKER_WIDGET_MIN_WIDTH,
            "preferred_width": PICKER_START_WIDTH,
            "preferred_height": PICKER_WIDGET_START_HEIGHT,
            "default_width": PICKER_START_WIDTH,
            "default_height": PICKER_WIDGET_START_HEIGHT,
            "initial_width": PICKER_START_WIDTH,
            "initial_height": PICKER_WIDGET_START_HEIGHT,
            "node_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            "default_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            "initial_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            # This is the only visible Picker row. It remains expandable so
            # Griptape's first 40px allocator pass cannot collapse the row,
            # while the compact controller reclaims the trailing spacer and
            # locks the exact Shot-derived height after mounting.
            "expandable": True,
            "resizable": True,
            "compact": False,
            "hide": False,
            "hide_property": False,
        })
        setattr(parameter, "ui_options", options)
    except Exception as exc:
        _diagnostic_exception("Picker state UI option configuration failed", exc)


def _migrate_picker_widget_value(node: Any, parameter: Any) -> None:
    """Normalize legacy JSON-string state to Griptape's native dict contract."""
    try:
        raw_value = node.get_parameter_value(WIDGET_STATE_PARAMETER)
    except Exception:
        raw_value = getattr(parameter, "default_value", None)
    migrated = _parse_state(raw_value)
    if isinstance(raw_value, dict) and _parse_state(raw_value) == migrated:
        return
    _begin_state_sync(node)
    try:
        setter = getattr(node, "set_parameter_value", None)
        if callable(setter):
            setter(WIDGET_STATE_PARAMETER, migrated)
        else:
            setattr(parameter, "default_value", migrated)
    except Exception as exc:
        _diagnostic_exception("Widget-state JSON migration failed", exc)
        try:
            setattr(parameter, "default_value", migrated)
        except Exception as fallback_exc:
            _diagnostic_exception("Widget-state migration fallback write failed", fallback_exc)
    finally:
        _end_state_sync(node)


def _add_picker_widget(node: Any) -> None:
    if parameter_exists(node, WIDGET_STATE_PARAMETER):
        parameter = _get_parameter_obj(node, WIDGET_STATE_PARAMETER)
        _configure_picker_widget_parameter(parameter)
        _migrate_picker_widget_value(node, parameter)
        return
    kwargs: Dict[str, Any] = {
        "name": WIDGET_STATE_PARAMETER,
        "default_value": _default_widget_state(),
        "type": "dict",
        "input_types": ["dict"],
        "serializable": True,
        "tooltip": "Maya Outliner reader, per-video Color Pick assignment editor, and temporary-shader Playblast generator.",
        "ui_options": {
            "display_name": "HMBVideoPickerLibrary",
            "is_full_width": True,
            "height": PICKER_WIDGET_START_HEIGHT,
            "min_height": PICKER_WIDGET_COMPACT_MOUNT_HEIGHT,
            "widget_height": PICKER_WIDGET_START_HEIGHT,
            "width": PICKER_START_WIDTH,
            "min_width": PICKER_WIDGET_MIN_WIDTH,
            "preferred_width": PICKER_START_WIDTH,
            "preferred_height": PICKER_WIDGET_START_HEIGHT,
            "default_width": PICKER_START_WIDTH,
            "default_height": PICKER_WIDGET_START_HEIGHT,
            "initial_width": PICKER_START_WIDTH,
            "initial_height": PICKER_WIDGET_START_HEIGHT,
            "node_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            "default_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            "initial_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            # The visible state row participates in the host's first allocator
            # pass, then the compact controller locks the exact Loader height.
            # Hidden transport rows remain non-expandable.
            "expandable": True,
            "resizable": True,
            "compact": False,
            "hide": False,
            "hide_property": False,
        },
    }
    mode = _mode_set("PROPERTY")
    if mode is not None:
        kwargs["allowed_modes"] = mode
    else:
        kwargs.update({
            "allow_input": False,
            "allow_output": False,
            "allow_property": True,
        })
    try:
        if Widget is not None:
            parameter = Parameter(**{**kwargs, "traits": {Widget(name=WIDGET_NAME, library=WIDGET_LIBRARY_NAME)}})
        else:
            parameter = Parameter(**kwargs)
    except Exception:
        parameter = Parameter(**kwargs)
        if Widget is not None:
            try:
                parameter.add_trait(Widget(name=WIDGET_NAME, library=WIDGET_LIBRARY_NAME))
            except Exception as exc:
                _diagnostic_exception("Picker state fallback widget registration failed", exc)
    node.add_parameter(parameter)
    _configure_picker_widget_parameter(parameter)
    _migrate_picker_widget_value(node, parameter)

def _raw_parameter_value(node: Any, name: str) -> Any:
    try:
        return node.get_parameter_value(name)
    except Exception:
        parameter = getattr(node, "parameters", {}).get(name)
        return getattr(parameter, "default_value", None)


def _set_parameter_value(node: Any, name: str, value: Any) -> None:
    setter = getattr(node, "set_parameter_value", None)
    if not callable(setter):
        raise RuntimeError(f"The runtime does not expose set_parameter_value for {name}.")
    setter(name, value)


def _state_sync_local(node: Any) -> Any:
    local = getattr(node, "_hmb_state_sync_local", None)
    if local is None:
        local = threading.local()
        setattr(node, "_hmb_state_sync_local", local)
    return local


def _is_state_syncing(node: Any) -> bool:
    return int(getattr(_state_sync_local(node), "depth", 0) or 0) > 0


def _is_output_side_effect_callback(node: Any) -> bool:
    """Return whether output changes are inside a host value-set transaction.

    Griptape's NodeManager snapshots output values around ``after_value_set``
    and propagates changes itself.  Late worker publications happen outside
    that transaction and must explicitly forward their values to connected
    inputs.  Keeping this marker thread-local prevents a worker publication
    from being mistaken for a simultaneous host callback on another thread.
    """

    return int(
        getattr(_state_sync_local(node), "output_side_effect_depth", 0) or 0
    ) > 0


def _begin_output_side_effect_callback(node: Any) -> None:
    local = _state_sync_local(node)
    local.output_side_effect_depth = int(
        getattr(local, "output_side_effect_depth", 0) or 0
    ) + 1


def _end_output_side_effect_callback(node: Any) -> None:
    local = _state_sync_local(node)
    local.output_side_effect_depth = max(
        0,
        int(getattr(local, "output_side_effect_depth", 0) or 0) - 1,
    )


def _begin_state_sync(node: Any) -> None:
    local = _state_sync_local(node)
    local.depth = int(getattr(local, "depth", 0) or 0) + 1


def _end_state_sync(node: Any) -> None:
    local = _state_sync_local(node)
    local.depth = max(0, int(getattr(local, "depth", 0) or 0) - 1)


def _request_parameter_value(
    node: Any,
    name: str,
    value: Any,
    data_type: str,
) -> bool:
    """Publish a value through Griptape's retained-mode request bus when available."""
    try:
        from griptape_nodes.retained_mode.events.parameter_events import (  # type: ignore
            SetParameterValueRequest,
            SetParameterValueResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore
    except Exception:
        return False

    node_name = _clean(getattr(node, "name", ""))
    if not node_name:
        return False
    result = GriptapeNodes.handle_request(
        SetParameterValueRequest(
            node_name=node_name,
            parameter_name=name,
            value=value,
            data_type=data_type,
        )
    )
    if isinstance(result, SetParameterValueResultSuccess):
        return True
    details = _clean(getattr(result, "result_details", ""))
    raise RuntimeError(details or f"Griptape rejected the {name} state publication.")


def _notify_parameter_update(node: Any, name: str, value: Any) -> None:
    """Notify existing connections after the caller has staged output caches."""
    publisher = getattr(node, "publish_update_to_parameter", None)
    if callable(publisher):
        publisher(name, value)


def _propagate_parameter_update_to_connections(
    node: Any,
    name: str,
    value: Any,
) -> None:
    """Forward one late output value through real retained-mode graph edges.

    ``BaseNode.publish_update_to_parameter`` emits a display/execution event,
    but it does not issue the ``SetParameterValueRequest`` that updates a
    connected input.  Picker workers finish after the initiating host request
    has returned, so NodeManager's synchronous output-side-effect propagation
    cannot see those changes.  Use only public connection/result payloads and
    preserve the upstream identity fields required for connected INPUT+PROPERTY
    targets.
    """

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
    if not node_name:
        return
    try:
        registered_node = GriptapeNodes.NodeManager().get_node_by_name(
            node_name
        )
    except Exception:
        # Unit probes and constructor-time synchronization legitimately run
        # before the node belongs to a retained-mode graph.  There cannot be
        # an outgoing edge to forward in that state.
        return
    if registered_node is not node:
        return
    connections_result = GriptapeNodes.handle_request(
        ListConnectionsForNodeRequest(
            node_name=node_name,
            broadcast_result=False,
            failure_log_level=logging.DEBUG,
        )
    )
    if not isinstance(connections_result, ListConnectionsForNodeResultSuccess):
        details = _clean(getattr(connections_result, "result_details", ""))
        raise RuntimeError(
            details or f"Griptape could not inspect outgoing {name} connections."
        )

    source_parameter = _get_parameter_obj(node, name)
    data_type = _clean(getattr(source_parameter, "output_type", "")) or _clean(
        getattr(source_parameter, "type", "")
    )
    for connection in connections_result.outgoing_connections:
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
        if not isinstance(set_result, SetParameterValueResultSuccess):
            details = _clean(getattr(set_result, "result_details", ""))
            raise RuntimeError(
                details
                or (
                    f"Griptape rejected {node_name}.{name} propagation to "
                    f"{target_node_name}.{target_parameter_name}."
                )
            )


def _publish_parameter_update(node: Any, name: str, value: Any) -> None:
    """Set one output and propagate late async results across existing connections."""
    set_output(node, name, value)
    _notify_parameter_update(node, name, value)
    if not _is_output_side_effect_callback(node):
        _propagate_parameter_update_to_connections(node, name, value)


def _norm_path(value: Any) -> Path:
    text = _scene_path_text(value)
    parsed = urlparse(text)
    if parsed.scheme.lower() == "file":
        path_text = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", path_text):
            path_text = path_text[1:]
        text = path_text
    return Path(os.path.expandvars(os.path.expanduser(text))).resolve()


def _scene_path_key(value: Any) -> str:
    text = _scene_path_text(value)
    if not text:
        return ""
    try:
        text = str(_norm_path(text))
    except Exception as exc:
        _diagnostic_exception("Path normalization failed; using cleaned literal path", exc)
    text = text.replace("\\", "/")
    return text.lower() if os.name == "nt" else text


def _validated_runner_result_path(
    result: Dict[str, Any],
    field_name: str,
    expected_path: Path,
) -> Path:
    """Accept only the exact normalized staged path requested from Maya."""
    returned_text = _clean(result.get(field_name))
    if not returned_text:
        raise RuntimeError(
            f"Maya result omitted required staged path '{field_name}'."
        )
    returned_path = _norm_path(returned_text)
    expected_path = _norm_path(expected_path)
    if _scene_path_key(returned_path) != _scene_path_key(expected_path):
        raise RuntimeError(
            "Maya result returned an unexpected staged path for "
            f"'{field_name}': {returned_path}"
        )
    return expected_path


def _safe_scene_name(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]+', "_", _clean(value))
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text or "scene"


def _is_reparse_or_symlink(path: Path) -> bool:
    """Return True for symlinks and Windows junction/reparse entries."""
    try:
        stat_result = path.lstat()
    except (FileNotFoundError, OSError):
        return False
    attributes = int(getattr(stat_result, "st_file_attributes", 0) or 0)
    return path.is_symlink() or bool(attributes & 0x400)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _scene_output_folder(scene_path: Path) -> Path:
    """Return the user-facing playblast folder beside the Maya scene."""
    scene_parent = scene_path.parent.resolve(strict=False)
    candidate = scene_parent / scene_path.stem
    if candidate.exists() and _is_reparse_or_symlink(candidate):
        raise RuntimeError(
            "The scene playblast folder is a symlink or Windows junction. "
            f"Choose a normal folder before generating media: {candidate}"
        )
    if candidate.exists() and candidate.resolve(strict=True) != candidate.absolute():
        raise RuntimeError(
            "The scene playblast folder resolves outside its authored location: "
            f"{candidate}"
        )
    return candidate


def _ensure_scene_output_folder(scene_path: Path) -> Path:
    output_folder = _scene_output_folder(scene_path)
    output_folder.mkdir(parents=True, exist_ok=True)
    # Re-check after mkdir to close the common pre-check/create race.
    return _scene_output_folder(scene_path)


def _ensure_private_job_folder(job_folder: Path, output_folder: Path) -> Path:
    """Create a Picker-private job folder without traversing link-like entries."""
    output_folder = output_folder.resolve(strict=True)
    lexical_job = job_folder.absolute()
    try:
        relative = lexical_job.relative_to(output_folder.absolute())
    except ValueError as exc:
        raise RuntimeError(
            f"Picker job folder is outside the scene output folder: {job_folder}"
        ) from exc
    current = output_folder
    for part in relative.parts:
        current = current / part
        current.mkdir(exist_ok=True)
        if _is_reparse_or_symlink(current):
            raise RuntimeError(
                "Picker private work folders cannot be symlinks or Windows "
                f"junctions: {current}"
            )
    if not _path_is_within(current, output_folder):
        raise RuntimeError(
            f"Picker private work folder escaped the scene output folder: {current}"
        )
    return current


def _private_work_root(path: Path) -> Optional[Path]:
    for candidate in (path, *path.parents):
        if candidate.name == ".hmb_video_picker":
            return candidate
    return None


def _assert_safe_private_path(path: Path) -> Path:
    root = _private_work_root(path)
    if root is None or not _path_is_within(path, root):
        raise RuntimeError(f"Refusing cleanup outside .hmb_video_picker: {path}")
    for candidate in (root, *reversed(path.absolute().parents), path.absolute()):
        if candidate == root or _path_is_within(candidate, root):
            if (candidate.exists() or candidate.is_symlink()) and _is_reparse_or_symlink(candidate):
                raise RuntimeError(
                    "Refusing cleanup through a symlink or Windows junction: "
                    f"{candidate}"
                )
    return path


def _safe_delete_snapshot_cache_file(scene_path: Path, value: Any) -> bool:
    """Delete only a PNG inside this scene's Picker-private cache root."""
    text = _clean(value)
    if not text:
        return False
    try:
        candidate = _norm_path(text)
        private_root = (
            _scene_output_folder(scene_path) / ".hmb_video_picker"
        ).resolve(strict=False)
        if candidate.suffix.lower() != ".png":
            raise RuntimeError(
                f"Refusing Snapshot cleanup for a non-PNG path: {candidate}"
            )
        if not _path_is_within(candidate, private_root):
            raise RuntimeError(
                "Refusing Snapshot cleanup outside this scene's private "
                f"cache: {candidate}"
            )
        _assert_safe_private_path(candidate).unlink(missing_ok=True)
        return True
    except Exception as exc:
        _diagnostic(
            "snapshot cache cleanup refused or failed: "
            f"{_clean(exc) or exc.__class__.__name__}"
        )
        return False


def _safe_remove_private_tree(path: Path) -> None:
    safe_path = _assert_safe_private_path(path)
    if safe_path.is_dir():
        shutil.rmtree(safe_path)


def _external_media_url(path: Path) -> str:
    """Return the Griptape static-server URL used by browser video elements."""
    resolved = path.resolve()
    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore

        base_url = _clean(GriptapeNodes.StaticFilesManager().static_server_base_url).rstrip("/")
        if base_url:
            resolved_text = str(resolved)
            if os.name == "nt" and resolved_text.startswith("\\\\"):
                # Griptape 0.95.1 reconstructs ``/external/{file_path}`` with
                # ``Path(file_path)``.  Preserve a Windows UNC authority as
                # percent-encoded backslashes so the decoded route parameter
                # remains ``\\server\share\...`` and is absolute. Converting it
                # to slashes and stripping the prefix turns it into the local
                # rooted path ``\server\share\...`` and produces a 404.
                external_path = resolved_text
            else:
                external_path = resolved_text.replace("\\", "/").lstrip("/")
            cache_key = resolved.stat().st_mtime_ns if resolved.is_file() else time.time_ns()
            return f"{base_url}/external/{quote(external_path, safe='/:')}?v={cache_key}"
    except Exception as exc:
        _diagnostic(f"Griptape external-file URL unavailable; using file URI fallback: {_clean(exc)}")
    try:
        return resolved.as_uri()
    except Exception:
        return str(resolved).replace("\\", "/")


def _resolved_video_asset_path(value: Any) -> Optional[Path]:
    """Return the first durable, readable local source for one catalog card."""

    item = value if isinstance(value, dict) else {}
    probe_cache: Dict[str, Optional[Path]] = {}
    for field in (
        "project_video_path",
        "video_path",
        "import_source_path",
    ):
        reference = _clean(item.get(field))
        if not reference:
            continue
        try:
            resolved = _resolve_readable_video_reference(
                reference,
                probe_cache=probe_cache,
            )
        except Exception as exc:
            _diagnostic_exception("Video thumbnail source probe failed", exc)
            resolved = None
        if resolved is not None:
            return resolved
    return None


def _video_thumbnail_signature(path: Path) -> str:
    """Return a durable source signature without retaining the local path."""

    try:
        resolved = path.resolve()
        details = resolved.stat()
        signature_text = "|".join((
            str(resolved).replace("\\", "/").casefold(),
            str(int(details.st_size)),
            str(int(details.st_mtime_ns)),
        ))
    except Exception:
        return ""
    return hashlib.sha256(signature_text.encode("utf-8")).hexdigest()[:24]


def _video_thumbnail_ffmpeg() -> Optional[Path]:
    """Resolve the package-managed FFmpeg binary once per engine process."""

    global _VIDEO_THUMBNAIL_FFMPEG, _VIDEO_THUMBNAIL_FFMPEG_RESOLVED
    with _VIDEO_THUMBNAIL_LOCK:
        if not _VIDEO_THUMBNAIL_FFMPEG_RESOLVED:
            # Reuse the same trusted discovery policy as playblast encoding,
            # including an application-local binary beside mayabatch.
            _VIDEO_THUMBNAIL_FFMPEG = _find_ffmpeg(_find_mayabatch())
            _VIDEO_THUMBNAIL_FFMPEG_RESOLVED = True
        return _VIDEO_THUMBNAIL_FFMPEG


def _video_asset_thumbnail_url(
    path: Path,
    video_uid: Any,
) -> tuple[str, str]:
    """Decode and publish one cached 320x180 PNG poster for a local video.

    Cache identity follows file path, size, and mtime.  The lock intentionally
    covers extraction and publication: simultaneous append/recovery workers for
    the same source therefore invoke FFmpeg and ``save_static_file`` only once.
    Failures are non-fatal because the video card and playback URL remain the
    durable authority.
    """

    try:
        resolved = path.resolve()
    except Exception:
        return "", ""
    signature = _video_thumbnail_signature(resolved)
    if not signature:
        return "", ""

    with _VIDEO_THUMBNAIL_LOCK:
        cached = _clean(_VIDEO_THUMBNAIL_URLS.get(signature))
        if cached:
            return cached, signature
        if signature in _VIDEO_THUMBNAIL_ATTEMPTED:
            return "", signature
        if len(_VIDEO_THUMBNAIL_ATTEMPTED) >= MAX_PICKER_VIDEO_ASSETS * 4:
            try:
                _VIDEO_THUMBNAIL_ATTEMPTED.pop()
            except KeyError:
                pass
        _VIDEO_THUMBNAIL_ATTEMPTED.add(signature)
        try:
            ffmpeg = _video_thumbnail_ffmpeg()
        except Exception as exc:
            _diagnostic_exception("Video thumbnail FFmpeg lookup failed", exc)
            return "", signature
        if ffmpeg is None:
            return "", signature
        command = [
            str(ffmpeg),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(resolved),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-vf",
            (
                f"scale={VIDEO_THUMBNAIL_WIDTH}:{VIDEO_THUMBNAIL_HEIGHT}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={VIDEO_THUMBNAIL_WIDTH}:{VIDEO_THUMBNAIL_HEIGHT}:"
                "(ow-iw)/2:(oh-ih)/2:color=black"
            ),
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=VIDEO_THUMBNAIL_TIMEOUT_SECONDS,
                check=False,
                creationflags=_creation_flags(),
            )
            png_bytes = bytes(completed.stdout or b"")
            if (
                completed.returncode != 0
                or not png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                or len(png_bytes) > 8 * 1024 * 1024
            ):
                return "", signature
            from griptape_nodes.retained_mode.griptape_nodes import (  # type: ignore
                GriptapeNodes,
            )

            safe_uid = re.sub(
                r"[^0-9A-Za-z_-]+",
                "_",
                _clean(video_uid),
            )[:32] or "video"
            filename = f"hmb_video_thumb_{safe_uid}_{signature}.png"
            url = _clean(
                GriptapeNodes.StaticFilesManager().save_static_file(
                    png_bytes,
                    filename,
                )
            )
        except Exception as exc:
            _diagnostic_exception("Video thumbnail publication failed", exc)
            url = ""
        if url:
            if len(_VIDEO_THUMBNAIL_URLS) >= MAX_PICKER_VIDEO_ASSETS * 2:
                try:
                    _VIDEO_THUMBNAIL_URLS.pop(
                        next(iter(_VIDEO_THUMBNAIL_URLS))
                    )
                except (KeyError, StopIteration):
                    pass
            _VIDEO_THUMBNAIL_URLS[signature] = url
        return url, signature


def _refresh_saved_video_media_urls(
    value: Any,
    *,
    clear_process_thumbnail_urls: bool = True,
) -> tuple[Dict[str, Any], bool]:
    """Rebind saved video cards to this engine's static-media server.

    Workflow files persist durable project/absolute paths. ``video_url`` is
    process-local because Griptape chooses a static-server origin per launch.
    Missing files remain assigned to their Shot and are reported rather than
    being silently removed from the user's saved ordering and selection.
    """

    state = _parse_state(value)
    videos = [
        dict(item)
        for item in state.get("videos", [])
        if isinstance(item, dict)
    ]
    warnings = _normalize_ui_warnings(state.get("warnings"))
    changed = False
    restored_count = 0

    for item in videos:
        # ``thumbnail_url`` is served by the current process' static manager,
        # just like ``video_url``.  Clear stale saved URLs synchronously, but do
        # not decode any frame here; a daemon recovery worker performs that
        # bounded work after hydration.
        thumbnail_url = _clean(item.get("thumbnail_url"))
        thumbnail_runtime_id = _clean(item.get("thumbnail_runtime_id"))
        if thumbnail_url and (
            clear_process_thumbnail_urls
            or thumbnail_runtime_id != _VIDEO_THUMBNAIL_RUNTIME_ID
        ):
            item["thumbnail_url"] = ""
            item["thumbnail_runtime_id"] = ""
            changed = True
        references: List[str] = []
        for field in (
            "project_video_path",
            "video_path",
            "import_source_path",
        ):
            reference = _clean(item.get(field))
            if reference and reference not in references:
                references.append(reference)
        resolved = next(
            (
                candidate
                for candidate in (
                    _resolve_readable_video_reference(reference)
                    for reference in references
                )
                if candidate is not None
            ),
            None,
        )
        if resolved is not None:
            restored_count += 1
            refreshed_url = _external_media_url(resolved)
            if refreshed_url and refreshed_url != _clean(item.get("video_url")):
                item["video_url"] = refreshed_url
                changed = True
            continue

        if references:
            label = _selected_video_label(item)
            warning = (
                f"Saved video is unavailable: {label}. The Shot assignment "
                "and card were preserved; restore the file and reload."
            )
            if warning not in warnings:
                warnings.append(warning)
                changed = True

    # Original Preview is retained outside the catalog until it is explicitly
    # appended as an output asset. Its static-server origin is just as
    # process-local as each card URL, so rebind it during saved-workflow
    # hydration too. This is required for Maya scenes and generated previews on
    # UNC shares, where a stale localhost port cannot be reused after restart.
    original_reference = _clean(state.get("original_video_path"))
    if original_reference:
        original_resolved = _resolve_readable_video_reference(
            original_reference
        )
        if original_resolved is not None:
            refreshed_original_url = _external_media_url(original_resolved)
            if refreshed_original_url and refreshed_original_url != _clean(
                state.get("original_video_url")
            ):
                state["original_video_url"] = refreshed_original_url
                changed = True
        else:
            warning = (
                "Saved original preview is unavailable. Restore the file and "
                "reload before using Original Preview."
            )
            if warning not in warnings:
                warnings.append(warning)
                changed = True

    previous_count = int(state.get("saved_video_restore_count") or 0)
    if previous_count != restored_count:
        changed = True
    state["videos"] = videos
    state["warnings"] = warnings[-20:]
    state["saved_video_restore_count"] = restored_count
    return _parse_state(state), changed


def _decode_maya_text(value: bytes) -> str:
    raw = bytes(value or b"").rstrip(b"\0")
    for encoding in ("utf-8", "cp949", "latin-1"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()


def _inspect_maya_scene_file(path: Path) -> Dict[str, Any]:
    # OPEN is intentionally limited to filesystem metadata. Maya owns every
    # camera, timeline, node, plug-in, and scene-version decision during READ.
    return {
        "size_mb": round(path.stat().st_size / (1024.0 * 1024.0), 1),
        "source_version": "",
        "plugin_hints": [],
    }


def _maya_major_from_path(path: Path) -> int:
    text = str(path).replace("\\", "/")
    matches = re.findall(r"(?i)(?:maya|autodesk[/\\]maya)[^0-9]*([0-9]{4})", text)
    if matches:
        try:
            return max(int(value) for value in matches)
        except Exception as exc:
            _diagnostic_exception("Maya version parsing failed", exc)
    return 0


def _mayabatch_candidates() -> List[Path]:
    candidates: List[Path] = []
    env_location = _clean(os.environ.get("MAYA_LOCATION"))
    if env_location:
        root = Path(os.path.expandvars(os.path.expanduser(env_location)))
        candidates.extend([root / "bin" / "mayabatch.exe", root / "bin" / "mayabatch"])

    windows_roots: List[Path] = []
    for env_name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base_text = _clean(os.environ.get(env_name))
        if base_text:
            windows_roots.append(Path(base_text))
    if os.name == "nt":
        windows_roots.extend([Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")])
    seen_windows_roots = set()
    for base_path in windows_roots:
        root_key = str(base_path).replace("\\", "/").lower()
        if root_key in seen_windows_roots:
            continue
        seen_windows_roots.add(root_key)
        autodesk_root = base_path / "Autodesk"
        try:
            for maya_root in autodesk_root.glob("Maya*"):
                candidates.extend([maya_root / "bin" / "mayabatch.exe", maya_root / "bin" / "mayabatch"])
        except OSError:
            pass

    # Common Linux and macOS install locations.
    for pattern in ("/usr/autodesk/maya*/bin/mayabatch", "/Applications/Autodesk/maya*/Maya.app/Contents/bin/mayabatch"):
        try:
            candidates.extend(Path(item) for item in __import__("glob").glob(pattern))
        except Exception as exc:
            _diagnostic_exception(f"Maya executable glob failed for {pattern}", exc)

    for executable in ("mayabatch.exe", "mayabatch"):
        resolved = shutil.which(executable)
        if resolved:
            candidates.append(Path(resolved))

    unique: Dict[str, Path] = {}
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.is_file():
                unique[str(resolved).lower()] = resolved
        except OSError:
            continue
    return list(unique.values())


def _find_mayabatch() -> Optional[Path]:
    candidates = _mayabatch_candidates()
    if not candidates:
        return None
    # Highest installed Maya major wins. Unknown-version PATH entries remain a
    # fallback and never override a detected numbered installation.
    candidates.sort(key=lambda item: (_maya_major_from_path(item), str(item).lower()), reverse=True)
    return candidates[0]


def _maya_display_version(mayabatch: Path) -> str:
    major = _maya_major_from_path(mayabatch)
    return str(major) if major > 0 else "Detected"

def _find_ffmpeg(mayabatch: Optional[Path] = None) -> Optional[Path]:
    candidates: List[Path] = []
    # An explicit operator override wins. Otherwise use only package-managed
    # or application-local binaries. Ambient PATH entries are intentionally
    # excluded because another application can silently shadow them.
    env_path = os.environ.get("FFMPEG_PATH", "")
    if env_path:
        candidates.append(_norm_path(env_path))
    try:
        import imageio_ffmpeg  # type: ignore

        bundled_ffmpeg = _clean(imageio_ffmpeg.get_ffmpeg_exe())
        if bundled_ffmpeg:
            candidates.append(_norm_path(bundled_ffmpeg))
    except (ImportError, OSError, RuntimeError):
        pass
    try:
        import static_ffmpeg  # type: ignore

        static_root = Path(static_ffmpeg.__file__).resolve().parent
        platform_folders = ("win32", "win64") if os.name == "nt" else ("linux", "darwin")
        executable_names = ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg",)
        for platform_folder in platform_folders:
            for executable_name in executable_names:
                candidates.append(static_root / "bin" / platform_folder / executable_name)
    except (ImportError, OSError, RuntimeError, TypeError):
        pass
    if mayabatch is not None:
        candidates.extend([mayabatch.parent / "ffmpeg.exe", mayabatch.parent / "ffmpeg"])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _find_ffprobe(ffmpeg: Optional[Path] = None) -> Optional[Path]:
    candidates: List[Path] = []
    env_path = os.environ.get("FFPROBE_PATH", "")
    if env_path:
        candidates.append(_norm_path(env_path))
    if ffmpeg is not None:
        candidates.extend([
            ffmpeg.with_name("ffprobe.exe"),
            ffmpeg.with_name("ffprobe"),
        ])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _find_maya_project(scene_path: Path) -> Optional[Path]:
    for folder in [scene_path.parent, *scene_path.parents]:
        try:
            if (folder / "workspace.mel").is_file():
                return folder.resolve()
        except OSError:
            continue
    return None


def _maya_subprocess_environment(job_path: Path) -> Dict[str, str]:
    """Build one deterministic environment for every Maya background operation."""
    env = os.environ.copy()
    job_path = job_path.resolve(strict=True)
    runner_path = MAYA_RUNNER.resolve(strict=True)
    env["HMB_VIDEO_PICKER_JOB"] = str(job_path)
    env["HMB_VIDEO_PICKER_JOB_SHA256"] = hashlib.sha256(
        job_path.read_bytes()
    ).hexdigest()
    env["HMB_VIDEO_PICKER_RUNNER"] = str(runner_path)
    env["HMB_VIDEO_PICKER_RUNNER_SHA256"] = hashlib.sha256(
        runner_path.read_bytes()
    ).hexdigest()
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MAYA_DISABLE_CIP"] = "1"
    env["MAYA_DISABLE_CER"] = "1"
    env["MAYA_DISABLE_ADP"] = "1"

    # The production crash report showed Maya 2027 failing inside
    # nvoglv64.dll while ogsRender presented the first OpenGL frame. Autodesk
    # supports selecting the VP2 device before both interactive and batch
    # startup. Prefer DirectX 11 on Windows unless the host has explicitly
    # selected a device through either environment variable.
    requested_device = _clean(env.get("HMB_MAYA_VP2_DEVICE_OVERRIDE"))
    if requested_device:
        env["MAYA_VP2_DEVICE_OVERRIDE"] = requested_device
    elif os.name == "nt" and not _clean(env.get("MAYA_VP2_DEVICE_OVERRIDE")):
        env["MAYA_VP2_DEVICE_OVERRIDE"] = "VirtualDeviceDx11"
    return env


def _maya_runner_command() -> str:
    """Load the verified runner by absolute path, never by ambient sys.path."""
    code = (
        "import hashlib,importlib.util,os,sys;sys.dont_write_bytecode=True;"
        "p=os.path.abspath(os.environ['HMB_VIDEO_PICKER_RUNNER']);"
        "e=os.environ['HMB_VIDEO_PICKER_RUNNER_SHA256'].lower();"
        "a=hashlib.sha256(__import__('pathlib').Path(p).read_bytes()).hexdigest().lower();"
        "(a==e)or(_ for _ in()).throw(RuntimeError('HMB Maya runner integrity check failed'));"
        "s=importlib.util.spec_from_file_location('_hmb_verified_maya_runner',p);"
        "(s is not None and s.loader is not None)or(_ for _ in()).throw(RuntimeError('HMB Maya runner load failed'));"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.run_from_env()"
    )
    return "python(" + json.dumps(code) + ")"


def _open_path_in_file_browser(path: Path) -> None:
    target = path if path.is_dir() else path.parent
    if not target.exists():
        raise FileNotFoundError(f"Log folder not found: {target}")
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    command = ["open", str(target)] if sys.platform == "darwin" else ["xdg-open", str(target)]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _choose_maya_scene_file(initial_value: Any = "") -> str:
    """Open an OS-native Maya scene dialog and return its absolute path."""
    test_selection = _clean(os.environ.get("HMB_MAYA_SCENE_TEST_SELECTION"))
    if test_selection:
        return str(_norm_path(test_selection))
    initial_path = _norm_path(initial_value) if _clean(initial_value) else None
    initial_dir = initial_path.parent if initial_path and initial_path.suffix else initial_path
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception as exc:
            _diagnostic_exception("Native file dialog topmost configuration failed", exc)
        try:
            selected = filedialog.askopenfilename(
                parent=root,
                title="Open Maya Scene",
                initialdir=str(initial_dir) if initial_dir and initial_dir.is_dir() else None,
                filetypes=[
                    ("Maya Scene", "*.mb *.ma"),
                    ("Maya Binary", "*.mb"),
                    ("Maya ASCII", "*.ma"),
                ],
            )
        finally:
            root.destroy()
    except Exception as tkinter_exc:
        if os.name != "nt":
            raise RuntimeError(
                f"The native Maya scene browser could not be opened: {tkinter_exc}"
            ) from tkinter_exc
        initial_directory = str(initial_dir) if initial_dir and initial_dir.is_dir() else ""
        escaped_initial = initial_directory.replace("'", "''")
        script = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d=New-Object System.Windows.Forms.OpenFileDialog; "
            "$d.Title='Open Maya Scene'; "
            "$d.Filter='Maya Scene (*.mb;*.ma)|*.mb;*.ma|Maya Binary (*.mb)|*.mb|Maya ASCII (*.ma)|*.ma'; "
            "$d.Multiselect=$false; "
            f"$d.InitialDirectory='{escaped_initial}'; "
            "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){[Console]::Out.Write($d.FileName)}"
        )
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
                capture_output=True,
                text=False,
                timeout=600,
                creationflags=_creation_flags(),
                check=False,
            )
            selected = _decode_maya_text(bytes(completed.stdout or b""))
            if completed.returncode != 0:
                raise RuntimeError(
                    _decode_maya_text(bytes(completed.stderr or b""))
                    or "PowerShell file dialog failed."
                )
        except Exception as powershell_exc:
            raise RuntimeError(
                "The native Maya scene browser could not be opened with Tk or Windows Forms: "
                f"{powershell_exc}"
            ) from powershell_exc
    return str(_norm_path(selected)) if _clean(selected) else ""


def _choose_video_asset_files(initial_value: Any = "") -> List[str]:
    """Open one OS-native multi-select MP4 dialog in deterministic order."""
    test_selections = _clean(
        os.environ.get("HMB_VIDEO_ASSET_TEST_SELECTIONS")
    )
    if test_selections:
        try:
            decoded = json.loads(test_selections)
        except Exception as exc:
            raise ValueError(
                "HMB_VIDEO_ASSET_TEST_SELECTIONS must be a JSON list."
            ) from exc
        if not isinstance(decoded, list):
            raise ValueError(
                "HMB_VIDEO_ASSET_TEST_SELECTIONS must be a JSON list."
            )
        return [
            str(_norm_path(item))
            for item in decoded[:MAX_VIDEO_IMPORT_BATCH]
            if _clean(item)
        ]
    test_selection = _clean(os.environ.get("HMB_VIDEO_ASSET_TEST_SELECTION"))
    if test_selection:
        return [str(_norm_path(test_selection))]
    initial_path = _norm_path(initial_value) if _clean(initial_value) else None
    initial_dir = initial_path.parent if initial_path and initial_path.suffix else initial_path
    if os.name == "nt":
        # The Picker command runs on a worker. Tk may silently hang when it is
        # created from that thread, so Windows uses an independent STA WinForms
        # dialog. Wrap the actual foreground Griptape HWND as IWin32Window: an
        # invisible topmost owner can leave the common dialog behind Electron
        # or on another monitor even though the command was delivered.
        initial_directory = (
            str(initial_dir) if initial_dir and initial_dir.is_dir() else ""
        )
        escaped_initial = initial_directory.replace("'", "''")
        script = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; using System.Windows.Forms; public sealed class HmbPickerOwner : IWin32Window { public HmbPickerOwner(IntPtr handle) { Handle = handle; } public IntPtr Handle { get; private set; } } public static class HmbPickerNative { [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); }'; "
            "$foreground=[HmbPickerNative]::GetForegroundWindow(); "
            "$owner=if($foreground -ne [IntPtr]::Zero){[HmbPickerOwner]::new($foreground)}else{$null}; "
            "$d=New-Object System.Windows.Forms.OpenFileDialog; "
            "$d.Title='Import MP4 Videos'; "
            "$d.Filter='MP4 Video (*.mp4)|*.mp4'; "
            "$d.Multiselect=$true; $d.CheckFileExists=$true; $d.RestoreDirectory=$true; "
            f"$d.InitialDirectory='{escaped_initial}'; "
            "$result=if($owner){$d.ShowDialog($owner)}else{$d.ShowDialog()}; "
            "if($result -eq [System.Windows.Forms.DialogResult]::OK){$d.FileNames | ForEach-Object {[Console]::Out.WriteLine($_)}}; "
            "$d.Dispose()"
        )
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-STA",
                "-Command",
                script,
            ],
            capture_output=True,
            text=False,
            timeout=600,
            creationflags=_creation_flags(),
            check=False,
        )
        stdout_text = _decode_maya_text(bytes(completed.stdout or b""))
        selected = [
            line.strip()
            for line in stdout_text.splitlines()
            if line.strip()
        ]
        if completed.returncode != 0:
            raise RuntimeError(
                _decode_maya_text(bytes(completed.stderr or b""))
                or "The Windows MP4 file dialog failed."
            )
    else:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception as exc:
                _diagnostic_exception(
                    "Native video dialog topmost configuration failed",
                    exc,
                )
            try:
                selected = filedialog.askopenfilenames(
                    parent=root,
                    title="Import MP4 Videos",
                    initialdir=(
                        str(initial_dir)
                        if initial_dir and initial_dir.is_dir()
                        else None
                    ),
                    filetypes=[("MP4 Video", "*.mp4")],
                )
            finally:
                root.destroy()
        except Exception as tkinter_exc:
            raise RuntimeError(
                f"The native MP4 browser could not be opened: {tkinter_exc}"
            ) from tkinter_exc
    if isinstance(selected, (str, Path)):
        selected = [selected] if _clean(selected) else []
    return [
        str(_norm_path(item))
        for item in list(selected or [])[:MAX_VIDEO_IMPORT_BATCH]
        if _clean(item)
    ]


def _choose_video_asset_file(initial_value: Any = "") -> str:
    """Compatibility wrapper returning the first selected MP4, if any."""
    selected = _choose_video_asset_files(initial_value)
    return selected[0] if selected else ""


def _command_text(command: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creation_flags(),
                check=False,
                timeout=20,
            )
        except Exception as exc:
            _diagnostic_exception(f"Windows process-tree termination failed for PID {getattr(process, 'pid', 0)}", exc)
    try:
        process.kill()
    except Exception as exc:
        _diagnostic_exception(f"Direct process termination failed for PID {getattr(process, 'pid', 0)}", exc)
    try:
        process.wait(timeout=20)
    except Exception as exc:
        _diagnostic_exception(f"Process wait after termination failed for PID {getattr(process, 'pid', 0)}", exc)


def _progress_signature(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)
    except Exception:
        return repr(payload)


def _filesystem_activity_snapshot(paths: Sequence[Path]) -> tuple[str, int, int]:
    """Summarize completed files directly beneath operation output folders.

    Maya moves every completed frame into the top-level frames folder. Direct
    child names/counts/sizes/mtimes are reliable on Windows even when the parent
    directory mtime is not. The watchdog calls this fallback only after primary
    JSON/console progress has been quiet for a substantial part of the stall
    window, so the normal per-frame JSON path never repeatedly scans a growing
    image sequence.
    """
    records: List[tuple[str, str, int, int]] = []
    file_count = 0
    total_size = 0
    for raw_path in paths:
        path = Path(raw_path)
        try:
            is_file = path.is_file()
            is_directory = path.is_dir()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if is_file:
            try:
                stat = path.stat()
            except (FileNotFoundError, PermissionError, OSError):
                continue
            records.append((
                str(path).replace("\\", "/").casefold(),
                "file",
                int(stat.st_size),
                int(stat.st_mtime_ns),
            ))
            file_count += 1
            total_size += int(stat.st_size)
            continue
        if not is_directory:
            continue
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        entry_stat = entry.stat(follow_symlinks=False)
                    except (FileNotFoundError, PermissionError, OSError):
                        continue
                    size = int(entry_stat.st_size)
                    records.append((
                        (
                            str(path / entry.name)
                            .replace("\\", "/")
                            .casefold()
                        ),
                        "file",
                        size,
                        int(entry_stat.st_mtime_ns),
                    ))
                    file_count += 1
                    total_size += size
        except (FileNotFoundError, PermissionError, OSError):
            continue
    if not records:
        return "", 0, 0
    records.sort()
    encoded = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    return (
        hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        file_count,
        total_size,
    )


def _scene_fingerprint(value: Any) -> str:
    """Fingerprint a scene without reading Maya file contents."""
    text = _maya_scene_path_text(value)
    if not text:
        return ""
    try:
        path = _norm_path(text)
        stat = path.stat()
        payload = {
            "path": str(path).replace("\\", "/").casefold(),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }
    except Exception:
        payload = {"path": text.replace("\\", "/").casefold(), "size": -1, "mtime_ns": -1}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scene_dependency_manifest_path(scene_path: Path) -> Path:
    return (
        _scene_output_folder(scene_path)
        / ".hmb_video_picker"
        / f"{_safe_scene_name(scene_path.stem)}.dependencies.json"
    )


def _dependency_paths_summary(paths: Sequence[Any]) -> Dict[str, Any]:
    records: List[tuple[Any, ...]] = []
    file_count = 0
    missing_count = 0
    total_size = 0
    scan_started = time.monotonic()
    try:
        max_files = max(
            1000,
            int(
                os.environ.get(
                    "HMB_DEPENDENCY_SCAN_MAX_FILES",
                    DEPENDENCY_SCAN_DEFAULT_MAX_FILES,
                )
            ),
        )
    except (TypeError, ValueError):
        max_files = DEPENDENCY_SCAN_DEFAULT_MAX_FILES
    try:
        max_seconds = max(
            0.5,
            float(
                os.environ.get(
                    "HMB_DEPENDENCY_SCAN_SECONDS",
                    DEPENDENCY_SCAN_DEFAULT_SECONDS,
                )
            ),
        )
    except (TypeError, ValueError):
        max_seconds = DEPENDENCY_SCAN_DEFAULT_SECONDS
    deadline = scan_started + max_seconds
    scan_truncated = False
    seen_paths = set()
    sequence_token = re.compile(r"(<udim>|<uvtile>|<f\d*>|#+|%0?\d*d)", re.IGNORECASE)
    for raw_value in paths:
        text = os.path.expandvars(os.path.expanduser(_clean(raw_value)))
        if not text:
            continue
        path = Path(text)
        key = str(path).replace("\\", "/").casefold()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        try:
            if path.is_file():
                stat = path.stat()
                records.append((key, "file", int(stat.st_size), int(stat.st_mtime_ns)))
                file_count += 1
                total_size += int(stat.st_size)
                continue
            if path.is_dir():
                directory = path
                record_kind = "directory"
            elif sequence_token.search(path.name):
                directory = path.parent
                record_kind = "sequence_directory"
                records.append((key, "pattern"))
            else:
                records.append((key, "missing"))
                missing_count += 1
                continue
        except (FileNotFoundError, PermissionError, OSError):
            records.append((key, "unreadable"))
            missing_count += 1
            continue

        child_count = 0
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if file_count >= max_files or time.monotonic() >= deadline:
                        scan_truncated = True
                        break
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        entry_stat = entry.stat(follow_symlinks=False)
                    except (FileNotFoundError, PermissionError, OSError):
                        continue
                    child_key = str(Path(directory) / entry.name).replace("\\", "/").casefold()
                    size = int(entry_stat.st_size)
                    records.append((
                        child_key,
                        record_kind,
                        size,
                        int(entry_stat.st_mtime_ns),
                    ))
                    child_count += 1
                    file_count += 1
                    total_size += size
        except (FileNotFoundError, PermissionError, OSError):
            records.append((key, "unreadable_directory"))
            missing_count += 1
        if child_count == 0:
            records.append((key, record_kind, 0, 0))
        if scan_truncated:
            try:
                directory_stat = directory.stat()
                records.append(
                    (
                        key,
                        "bounded_directory_fallback",
                        int(directory_stat.st_mtime_ns),
                    )
                )
            except (FileNotFoundError, PermissionError, OSError):
                records.append((key, "bounded_directory_unreadable"))
            break

    records.sort()
    if scan_truncated:
        records.append(
            (
                "scan_truncated",
                int(max_files),
                round(max_seconds, 3),
                int(file_count),
            )
        )
    encoded = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    return {
        "fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "path_count": len(seen_paths),
        "file_count": file_count,
        "missing_count": missing_count,
        "total_size": total_size,
        "scan_truncated": scan_truncated,
        "scan_limit_files": max_files,
        "scan_limit_seconds": max_seconds,
    }


def _current_scene_dependency_summary(
    scene_path: Path,
    native_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    manifest_value = _clean(native_metadata.get("dependency_manifest_path"))
    manifest_path = (
        Path(manifest_value)
        if manifest_value
        else _scene_dependency_manifest_path(scene_path)
    )
    result = {
        "complete": False,
        "manifest_path": str(manifest_path).replace("\\", "/"),
        "fingerprint": "",
        "path_count": 0,
        "file_count": 0,
        "missing_count": 0,
        "total_size": 0,
    }
    try:
        manifest = _read_json(manifest_path)
        if _clean(manifest.get("schema")) != ORIGINAL_DEPENDENCY_MANIFEST_SCHEMA:
            return result
        if _scene_path_key(manifest.get("scene_path")) != _scene_path_key(scene_path):
            return result
        paths = [
            _clean(item)
            for item in manifest.get("paths", [])
            if _clean(item)
        ]
        if not paths:
            return result
        result.update(_dependency_paths_summary(paths))
        result["complete"] = True
        return result
    except Exception:
        return result


def _is_structurally_valid_mp4(path: Path) -> bool:
    try:
        file_size = int(path.stat().st_size)
        if file_size < 24:
            return False
        box_types = set()
        position = 0
        with path.open("rb") as handle:
            while position + 8 <= file_size:
                handle.seek(position)
                header = handle.read(8)
                if len(header) != 8:
                    return False
                box_size = int.from_bytes(header[:4], "big")
                box_type = header[4:8]
                header_size = 8
                if box_size == 1:
                    extended = handle.read(8)
                    if len(extended) != 8:
                        return False
                    box_size = int.from_bytes(extended, "big")
                    header_size = 16
                elif box_size == 0:
                    box_size = file_size - position
                if box_size < header_size or position + box_size > file_size:
                    return False
                box_types.add(box_type)
                position += box_size
        return position == file_size and {b"ftyp", b"mdat", b"moov"}.issubset(box_types)
    except (FileNotFoundError, PermissionError, OSError, ValueError):
        return False


def _validate_encoded_playblast_with_ffmpeg(
    path: Path,
    *,
    ffmpeg: Path,
    expected_fps: float,
    expected_frame_count: int,
    expected_width: int,
    expected_height: int,
    label: str,
) -> Dict[str, Any]:
    """Portable validation fallback for imageio-ffmpeg-only installations."""
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "info",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-vf",
        "showinfo",
        "-f",
        "null",
        os.devnull,
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
            creationflags=_creation_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"FFmpeg decode verification timed out for {label}."
        ) from exc
    diagnostic = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(
            f"FFmpeg could not decode-verify {label}: "
            f"{_clean(completed.stderr)[-1000:] or 'unknown error'}"
        )

    rate_match = re.search(
        r"config in time_base:.*?\bframe_rate:\s*(\d+)\s*/\s*(\d+)",
        diagnostic,
    )
    actual_fps = 0.0
    if rate_match and int(rate_match.group(2)) != 0:
        actual_fps = int(rate_match.group(1)) / int(rate_match.group(2))
    frame_rows = re.findall(
        r"\bn:\s*(\d+)\b.*?\bfmt:(\S+).*?\bs:(\d+)x(\d+)\b",
        diagnostic,
    )
    frame_indices = [int(row[0]) for row in frame_rows]
    errors: List[str] = []
    if len(frame_indices) != expected_frame_count:
        errors.append("frame count")
    elif frame_indices != list(range(expected_frame_count)):
        errors.append("frame sequence")
    if abs(actual_fps - float(expected_fps)) > 1e-6:
        errors.append("frame rate")
    if any(row[1].lower() != "yuv420p" for row in frame_rows):
        errors.append("pixel format")
    if any(
        int(row[2]) != int(expected_width)
        or int(row[3]) != int(expected_height)
        for row in frame_rows
    ):
        errors.append("raster")
    stream_contract = re.search(
        r"Video:\s*h264\b.*?yuv420p\(tv,\s*bt709.*?\).*?"
        + re.escape(f"{int(expected_width)}x{int(expected_height)}"),
        diagnostic,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if stream_contract is None:
        errors.append("H.264/BT.709 stream")
    if errors:
        raise RuntimeError(
            f"Encoded {label} failed FFmpeg decode verification "
            f"({', '.join(errors)})."
        )
    return {
        "validated": True,
        "probe_backend": "ffmpeg_showinfo_decode",
        "ffmpeg": str(ffmpeg).replace("\\", "/"),
        "codec": "h264",
        "pixel_format": "yuv420p",
        "width": int(expected_width),
        "height": int(expected_height),
        "fps": actual_fps,
        "frame_count": len(frame_indices),
        "duration_seconds": (
            float(expected_frame_count) / float(expected_fps)
            if expected_fps > 0
            else 0.0
        ),
        "color_range": "tv",
        "color_space": "bt709",
        "color_transfer": "bt709",
        "color_primaries": "bt709",
    }


def _validate_encoded_playblast(
    path: Path,
    *,
    ffmpeg: Path,
    expected_fps: float,
    expected_frame_count: int,
    expected_width: int,
    expected_height: int,
    label: str,
) -> Dict[str, Any]:
    """Verify the final stream; prefer FFprobe and fall back to FFmpeg decode."""
    ffprobe = _find_ffprobe(ffmpeg)
    if ffprobe is None:
        return _validate_encoded_playblast_with_ffmpeg(
            path,
            ffmpeg=ffmpeg,
            expected_fps=expected_fps,
            expected_frame_count=expected_frame_count,
            expected_width=expected_width,
            expected_height=expected_height,
            label=label,
        )
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-count_packets",
        "-show_entries",
        (
            "stream=codec_name,pix_fmt,width,height,r_frame_rate,"
            "avg_frame_rate,nb_frames,nb_read_packets,color_range,"
            "color_space,color_transfer,color_primaries,duration"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            creationflags=_creation_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"FFprobe timed out while validating {label}.") from exc
    if completed.returncode != 0:
        detail = _clean(completed.stderr)[-1000:]
        raise RuntimeError(
            f"FFprobe could not validate {label}: {detail or 'unknown error'}"
        )
    try:
        payload = json.loads(completed.stdout)
        streams = payload.get("streams") if isinstance(payload, dict) else None
        stream = streams[0] if isinstance(streams, list) and streams else None
    except Exception as exc:
        raise RuntimeError(f"FFprobe returned invalid JSON for {label}.") from exc
    if not isinstance(stream, dict):
        raise RuntimeError(f"FFprobe found no video stream for {label}.")

    errors: List[str] = []
    if _clean(stream.get("codec_name")).lower() != "h264":
        errors.append("codec")
    if _clean(stream.get("pix_fmt")).lower() != "yuv420p":
        errors.append("pixel format")
    if int(stream.get("width") or 0) != int(expected_width):
        errors.append("width")
    if int(stream.get("height") or 0) != int(expected_height):
        errors.append("height")
    packet_count = int(
        stream.get("nb_read_packets")
        or stream.get("nb_frames")
        or 0
    )
    if packet_count != int(expected_frame_count):
        errors.append("frame count")
    rate_text = _clean(
        stream.get("avg_frame_rate")
        or stream.get("r_frame_rate")
    )
    try:
        actual_fps = float(Fraction(rate_text))
    except Exception:
        actual_fps = 0.0
    if abs(actual_fps - float(expected_fps)) > 1e-6:
        errors.append("frame rate")
    expected_duration = (
        float(expected_frame_count) / float(expected_fps)
        if expected_fps > 0
        else 0.0
    )
    try:
        actual_duration = float(stream.get("duration") or 0.0)
    except Exception:
        actual_duration = 0.0
    duration_tolerance = max(1e-4, 0.5 / max(float(expected_fps), 1.0))
    if abs(actual_duration - expected_duration) > duration_tolerance:
        errors.append("duration")
    expected_color_fields = {
        "color_range": "tv",
        "color_space": "bt709",
        "color_transfer": "bt709",
        "color_primaries": "bt709",
    }
    for field, expected in expected_color_fields.items():
        if _clean(stream.get(field)).lower() != expected:
            errors.append(field.replace("_", " "))
    if errors:
        raise RuntimeError(
            f"Encoded {label} failed final stream verification "
            f"({', '.join(errors)})."
        )
    return {
        "validated": True,
        "ffprobe": str(ffprobe).replace("\\", "/"),
        "codec": "h264",
        "pixel_format": "yuv420p",
        "width": int(expected_width),
        "height": int(expected_height),
        "fps": actual_fps,
        "frame_count": packet_count,
        "duration_seconds": actual_duration,
        **expected_color_fields,
    }


def _original_preview_paths(scene_path: Path) -> tuple[Path, Path]:
    output_folder = _scene_output_folder(scene_path)
    return (
        output_folder / f"{scene_path.stem}_Orignal.mp4",
        output_folder / f"{scene_path.stem}_Orignal.hmb.json",
    )


def _snapshot_original_preview_asset(
    scene_path: Path,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """Copy the mutable Original cache into one immutable catalog artifact."""
    source_video = Path(_clean(state.get("original_video_path")))
    if not source_video.is_file():
        raise FileNotFoundError(
            "The validated Original preview is unavailable for catalog publication."
        )
    source_sidecar = source_video.with_suffix(".hmb.json")
    if not source_sidecar.is_file():
        _canonical_video, canonical_sidecar = _original_preview_paths(scene_path)
        source_sidecar = canonical_sidecar
    if not source_sidecar.is_file():
        raise FileNotFoundError(
            "The validated Original preview sidecar is unavailable for catalog publication."
        )
    output_folder = _ensure_scene_output_folder(scene_path)
    token = hashlib.sha1(
        f"original-catalog|{scene_path}|{time.time_ns()}|{uuid.uuid4().hex}".encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    target_video = output_folder / f"{scene_path.stem}_Orignal_{token}.mp4"
    target_sidecar = output_folder / f"{scene_path.stem}_Orignal_{token}.hmb.json"
    if target_video.exists() or target_sidecar.exists():
        raise FileExistsError("Unique Original catalog target unexpectedly exists.")
    shutil.copy2(source_video, target_video)
    try:
        metadata = _read_json(source_sidecar)
        metadata["video"] = target_video.name
        metadata["video_path"] = str(target_video).replace("\\", "/")
        metadata["catalog_snapshot"] = True
        _write_json(target_sidecar, metadata)
    except Exception:
        target_video.unlink(missing_ok=True)
        target_sidecar.unlink(missing_ok=True)
        raise
    result = dict(state)
    result["original_video_path"] = str(target_video).replace("\\", "/")
    result["original_video_url"] = _external_media_url(target_video)
    result["original_metadata"] = _original_view_metadata(metadata)
    return result


def _original_preview_cache_fields(scene_path: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    output_width, output_height = _playblast_resolution(state)
    native_metadata = (
        dict(state.get("native_metadata"))
        if isinstance(state.get("native_metadata"), dict)
        else {}
    )
    dependency_summary = _current_scene_dependency_summary(scene_path, native_metadata)
    return {
        "scene_path": str(scene_path).replace("\\", "/"),
        "scene_fingerprint": _scene_fingerprint(scene_path),
        "camera": _clean(state.get("selected_camera") or state.get("camera")),
        "start_frame": float(native_metadata.get("start_frame", state.get("start_frame")) or 0.0),
        "end_frame": float(native_metadata.get("end_frame", state.get("end_frame")) or 0.0),
        "fps": float(native_metadata.get("fps", state.get("source_fps")) or 0.0),
        "resolution": {"width": output_width, "height": output_height},
        "encoding_profile": PROXY_ENCODING_PROFILE,
        "viewport_quality_profile": ORIGINAL_VIEWPORT_QUALITY_PROFILE,
        "original_material_override_profile": ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
        "mouth_card_inner_patch_policy": MOUTH_CARD_INNER_PATCH_POLICY,
        "dependency_manifest_version": ORIGINAL_DEPENDENCY_MANIFEST_VERSION,
        "scene_dependency_complete": bool(dependency_summary["complete"]),
        "scene_dependency_fingerprint": _clean(dependency_summary["fingerprint"]),
        "scene_dependency_path_count": int(dependency_summary["path_count"]),
        "scene_dependency_file_count": int(dependency_summary["file_count"]),
        "scene_dependency_missing_count": int(dependency_summary["missing_count"]),
    }


def _original_material_report_is_valid(report: Any) -> bool:
    source = report if isinstance(report, dict) else {}
    count_keys = (
        "inspected_shading_engine_count",
        "source_material_count",
        "temporary_lambert_count",
        "existing_lambert_count",
        "texture_connection_count",
        "numeric_color_count",
        "loaded_plugin_passthrough_count",
        "plugin_fallback_count",
        "plugin_fallback_material_count",
        "plugin_fallback_node_count",
        "unsupported_color_fallback_count",
        "required_texture_dependency_count",
        "missing_texture_dependency_count",
        "swapped_shading_engine_count",
    )
    if any(
        isinstance(source.get(key), bool)
        or not isinstance(source.get(key), int)
        for key in count_keys
    ):
        return False
    try:
        counts = {
            key: int(source[key])
            for key in count_keys
        }
    except (TypeError, ValueError):
        return False
    fallback_records = source.get("plugin_fallback_records")
    unsupported_materials = source.get("unsupported_color_fallback_materials")
    loaded_plugin_nodes = source.get("loaded_plugin_nodes")
    warnings = source.get("warnings")
    if not isinstance(fallback_records, list):
        return False
    if not isinstance(unsupported_materials, list):
        return False
    if not isinstance(loaded_plugin_nodes, list):
        return False
    if not isinstance(warnings, list):
        return False
    fallback_count = counts["plugin_fallback_count"]
    fallback_material_count = counts["plugin_fallback_material_count"]
    fallback_node_count = counts["plugin_fallback_node_count"]
    unsupported_count = counts["unsupported_color_fallback_count"]
    loaded_plugin_count = counts["loaded_plugin_passthrough_count"]
    return bool(
        _clean(source.get("profile"))
        == ORIGINAL_MATERIAL_OVERRIDE_PROFILE
        and source.get("requested") is True
        and _clean(source.get("status")) == "restored"
        and source.get("restore_ok") is True
        and source.get("shading_group_membership_preserved") is True
        and source.get("one_lambert_per_source_material") is True
        and source.get("default_lighting_verified") is True
        and source.get("textured_render_mode_verified") is True
        and not bool(
            source.get("temporary_nodes_retained_on_restore_failure")
        )
        and min(counts.values()) >= 0
        and counts["inspected_shading_engine_count"]
        >= counts["swapped_shading_engine_count"]
        and counts["source_material_count"]
        == counts["temporary_lambert_count"]
        + counts["existing_lambert_count"]
        and counts["temporary_lambert_count"]
        <= counts["swapped_shading_engine_count"]
        and counts["texture_connection_count"]
        + counts["numeric_color_count"]
        == counts["temporary_lambert_count"]
        and source.get("texture_dependency_preflight_passed") is True
        and counts["missing_texture_dependency_count"] == 0
        and isinstance(source.get("missing_texture_dependencies"), list)
        and not source.get("missing_texture_dependencies")
        and fallback_material_count <= counts["temporary_lambert_count"]
        and fallback_material_count <= fallback_count
        and unsupported_count <= counts["temporary_lambert_count"]
        and (fallback_count == 0 and unsupported_count == 0) == bool(
            source.get("texture_identity_preserved")
        )
        and len(fallback_records) == min(fallback_count, 32)
        and len(unsupported_materials) == min(unsupported_count, 32)
        and len(set(unsupported_materials)) == len(unsupported_materials)
        and all(
            isinstance(material, str) and bool(material.strip())
            for material in unsupported_materials
        )
        and len(loaded_plugin_nodes) == min(loaded_plugin_count, 32)
        and (fallback_count == 0 or fallback_node_count > 0)
        and (
            fallback_count == 0 and unsupported_count == 0
            or bool(warnings)
        )
    )


def _original_preview_cache_is_valid(
    scene_path: Path,
    state: Dict[str, Any],
    video_path: Optional[Path] = None,
    sidecar_path: Optional[Path] = None,
) -> bool:
    expected_video, expected_sidecar = _original_preview_paths(scene_path)
    video_path = video_path or expected_video
    sidecar_path = sidecar_path or expected_sidecar
    try:
        if not video_path.is_file() or not sidecar_path.is_file():
            return False
        if not _is_structurally_valid_mp4(video_path):
            return False
        metadata = _read_json(sidecar_path)
        expected = _original_preview_cache_fields(scene_path, state)
        resolution = metadata.get("resolution") if isinstance(metadata.get("resolution"), dict) else {}
        if not expected["scene_dependency_complete"]:
            return False
        if _clean(metadata.get("schema")) != "hmb-original-playblast":
            return False
        if _scene_path_key(metadata.get("scene_path")) != _scene_path_key(expected["scene_path"]):
            return False
        if _clean(metadata.get("scene_fingerprint")) != expected["scene_fingerprint"]:
            return False
        if _clean(metadata.get("camera")) != expected["camera"]:
            return False
        if _clean(metadata.get("encoding_profile")) != expected["encoding_profile"]:
            return False
        if _clean(metadata.get("viewport_quality_profile")) != expected["viewport_quality_profile"]:
            return False
        if (
            _clean(metadata.get("original_material_override_profile"))
            != expected["original_material_override_profile"]
        ):
            return False
        if (
            _clean(metadata.get("assignment_mode"))
            != ORIGINAL_LAMBERT_ASSIGNMENT_MODE
        ):
            return False
        material_report = (
            dict(metadata.get("original_material_override_report"))
            if isinstance(metadata.get("original_material_override_report"), dict)
            else {}
        )
        if not _original_material_report_is_valid(material_report):
            return False
        if (
            _clean(metadata.get("mouth_card_inner_patch_policy"))
            != expected["mouth_card_inner_patch_policy"]
        ):
            return False
        if int(metadata.get("dependency_manifest_version") or 0) != expected["dependency_manifest_version"]:
            return False
        if not bool(metadata.get("scene_dependency_complete")):
            return False
        if (
            _clean(metadata.get("accepted_read_dependency_fingerprint"))
            != expected["scene_dependency_fingerprint"]
        ):
            return False
        dependency_paths = [
            _clean(item)
            for item in metadata.get("scene_dependency_paths", [])
            if _clean(item)
        ]
        if not dependency_paths:
            return False
        dependency_summary = _dependency_paths_summary(dependency_paths)
        if (
            _clean(metadata.get("scene_dependency_fingerprint"))
            != dependency_summary["fingerprint"]
        ):
            return False
        if int(metadata.get("scene_dependency_path_count") or 0) != dependency_summary["path_count"]:
            return False
        if int(metadata.get("scene_dependency_file_count") or 0) != dependency_summary["file_count"]:
            return False
        if int(metadata.get("scene_dependency_missing_count") or 0) != dependency_summary["missing_count"]:
            return False
        if int(metadata.get("video_size_bytes") or 0) != int(video_path.stat().st_size):
            return False
        if int(resolution.get("width") or 0) != expected["resolution"]["width"]:
            return False
        if int(resolution.get("height") or 0) != expected["resolution"]["height"]:
            return False
        for key in ("start_frame", "end_frame", "fps"):
            if abs(float(metadata.get(key)) - float(expected[key])) > 1e-6:
                return False
        return bool(expected["camera"] and expected["fps"] > 0.0 and expected["end_frame"] >= expected["start_frame"])
    except Exception:
        return False


def _original_view_metadata(metadata: Any) -> Dict[str, Any]:
    source = metadata if isinstance(metadata, dict) else {}
    resolution = (
        dict(source.get("resolution"))
        if isinstance(source.get("resolution"), dict)
        else {}
    )
    return {
        "camera": _clean(source.get("camera")),
        "start_frame": source.get("start_frame"),
        "end_frame": source.get("end_frame"),
        "fps": source.get("fps"),
        "frame_count": source.get("frame_count"),
        "resolution": {
            "width": int(resolution.get("width") or 0),
            "height": int(resolution.get("height") or 0),
        },
        "viewport_quality_profile": _clean(
            source.get("viewport_quality_profile")
        ),
        "original_material_override_profile": _clean(
            source.get("original_material_override_profile")
        ),
        "original_material_override_report": (
            dict(source.get("original_material_override_report"))
            if isinstance(source.get("original_material_override_report"), dict)
            else {}
        ),
    }


def _operation_input_digest(kind: str, scene_text: Any, state: Dict[str, Any], slot: Optional[int] = None) -> str:
    normalized = _parse_state(state)
    selected_slot = max(
        1,
        min(
            int(normalized.get("active_slot_count") or 1),
            int(slot or normalized.get("selected_video_slot") or 1),
        ),
    )
    payload: Dict[str, Any] = {
        "kind": _clean(kind),
        "scene_fingerprint": _scene_fingerprint(scene_text),
        "marker_catalog_version": int(MARKER_CATALOG["version"]),
    }
    kind_text = _clean(kind)
    if kind_text == "render_snapshot":
        selected_slot = PRIMARY_COLOR_VIDEO_SLOT
    if kind_text == "render_original_preview":
        # Original preview identity is deliberately independent of marker/color
        # bindings and their catalog version. It represents the unmodified scene.
        payload.pop("marker_catalog_version", None)
        original_fields = _original_preview_cache_fields(_norm_path(scene_text), normalized)
        payload.update({
            "camera": original_fields["camera"],
            "start_frame": original_fields["start_frame"],
            "end_frame": original_fields["end_frame"],
            "fps": original_fields["fps"],
            "width": original_fields["resolution"]["width"],
            "height": original_fields["resolution"]["height"],
            "encoding_profile": original_fields["encoding_profile"],
            "viewport_quality_profile": original_fields["viewport_quality_profile"],
            "original_material_override_profile": original_fields[
                "original_material_override_profile"
            ],
            "mouth_card_inner_patch_policy": original_fields[
                "mouth_card_inner_patch_policy"
            ],
            "scene_dependency_complete": original_fields["scene_dependency_complete"],
            "scene_dependency_fingerprint": original_fields["scene_dependency_fingerprint"],
        })
    elif kind_text != "read_scene":
        depth_enabled = bool(
            kind_text == "run_video"
            and normalized.get("depth_enabled")
        )
        motion_guide_enabled = bool(
            kind_text == "run_video"
            and normalized.get("motion_guide_enabled")
        )
        depth_video_slot = 0
        motion_guide_video_slot = 0
        binding_slot = selected_slot
        if kind_text == "run_video":
            selected_slot = PRIMARY_COLOR_VIDEO_SLOT
            binding_slot = _mask_authoring_slot(normalized)
        if depth_enabled or motion_guide_enabled:
            (
                depth_video_slot,
                motion_guide_video_slot,
            ) = _resolve_generated_companion_slots(
                normalized,
                depth_enabled=depth_enabled,
                motion_guide_enabled=motion_guide_enabled,
            )
        bindings = _slot_assignment_bindings(normalized, binding_slot)
        hidden_paths = sorted({
            _clean(path)
            for item in normalized.get("slot_visibility", [])
            if (
                isinstance(item, dict)
                and int(item.get("video_slot") or 0) == binding_slot
            )
            for path in (
                item.get("hidden_paths", [])
                if isinstance(item.get("hidden_paths"), list)
                else []
            )
            if _clean(path)
        })
        output_width, output_height = _playblast_resolution(normalized)
        payload.update({
            "video_slot": selected_slot,
            "mask_authoring_slot": binding_slot,
            "camera": _clean(normalized.get("selected_camera")),
            "bindings": [
                {
                    "full_dag_path": _clean(item.get("full_dag_path")),
                    "maya_uuid": _clean(item.get("maya_uuid")),
                    "group_name": _clean(item.get("group_name")),
                    "color": _clean(item.get("color")),
                    "enabled": bool(item.get("enabled", True)),
                    "picker_order": int(item.get("picker_order") or 0),
                }
                for item in bindings
            ],
            "hidden_paths": hidden_paths,
            "width": output_width,
            "height": output_height,
            "output_fps": OUTPUT_FPS,
        })
        if kind_text == "run_video":
            payload.update({
                "active_picker_shot_uuid": _uuid_text(
                    normalized.get("active_picker_shot_uuid")
                ),
                "original_enabled": bool(normalized.get("original_enabled")),
                "mask_enabled": bool(normalized.get("mask_enabled")),
                "depth_enabled": depth_enabled,
                "depth_video_slot": depth_video_slot,
                "depth_profile": DEPTH_PLAYBLAST_PROFILE if depth_enabled else "",
                "mouth_card_inner_patch_policy": (
                    MOUTH_CARD_INNER_PATCH_POLICY
                    if depth_enabled or normalized.get("original_enabled")
                    else ""
                ),
                "motion_guide_enabled": motion_guide_enabled,
                "motion_guide_video_slot": motion_guide_video_slot,
                "motion_guide_profile": (
                    MOTION_GUIDE_PROFILE if motion_guide_enabled else ""
                ),
            })
            if depth_enabled:
                previous_depth_target = next(
                    (
                        item
                        for item in normalized.get("videos", [])
                        if isinstance(item, dict)
                        and int(item.get("video_slot") or 0)
                        == depth_video_slot
                    ),
                    {},
                )
                payload["depth_target_previous"] = {
                    "video_path": _clean(previous_depth_target.get("video_path")),
                    "project_video_path": _clean(
                        previous_depth_target.get("project_video_path")
                    ),
                    "run_id": _clean(previous_depth_target.get("run_id")),
                    "media_kind": _clean(previous_depth_target.get("media_kind")),
                }
            if motion_guide_enabled:
                previous_motion_target = next(
                    (
                        item
                        for item in normalized.get("videos", [])
                        if isinstance(item, dict)
                        and int(item.get("video_slot") or 0)
                        == motion_guide_video_slot
                    ),
                    {},
                )
                payload["motion_guide_target_previous"] = {
                    "video_path": _clean(previous_motion_target.get("video_path")),
                    "project_video_path": _clean(
                        previous_motion_target.get("project_video_path")
                    ),
                    "run_id": _clean(previous_motion_target.get("run_id")),
                    "media_kind": _clean(previous_motion_target.get("media_kind")),
                }
        if kind_text == "render_snapshot":
            payload["snapshot_frame"] = float(normalized.get("snapshot_frame") or 0.0)
            payload["snapshot_video_uid"] = _clean(
                normalized.get("snapshot_request_video_uid")
                or normalized.get("preview_video_uid")
                or normalized.get("selected_video_uid")
            )
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _OperationContext:
    operation_id: str
    kind: str
    scene_path: str
    scene_fingerprint: str
    input_digest: str
    video_slot: int
    snapshot_video_uid: str
    mask_authoring_slot: int
    depth_video_slot: int
    motion_guide_video_slot: int
    selected_roles: tuple[str, ...]
    picker_shot_uuid: str
    accepted_state_revision: int


class _StaleOperationError(RuntimeError):
    pass


def _build_ffmpeg_encode_command(
    ffmpeg: Path,
    frame_pattern: Path,
    output_path: Path,
    source_fps: float,
    frame_count: int,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> List[str]:
    if source_fps <= 0 or frame_count <= 0:
        raise ValueError("FFmpeg source FPS and frame count must be greater than zero.")
    source_rate = _fps_timebase(source_fps)
    track_timescale = _video_track_timescale(source_fps)
    if not source_rate or track_timescale <= 0:
        raise ValueError("FFmpeg source FPS could not be represented as an exact rational timebase.")
    gop_frames = max(1, int(round(source_fps)))
    scale_filter = (
        f"scale={int(width)}:{int(height)}:"
        "flags=lanczos+accurate_rnd+full_chroma_int:"
        "in_range=full:out_range=tv:out_color_matrix=bt709,"
        "setsar=1,format=yuv420p"
    )
    return [
        str(ffmpeg), "-y",
        "-framerate", source_rate,
        "-start_number", "0",
        "-i", str(frame_pattern),
        "-vf", scale_filter,
        "-frames:v", str(int(frame_count)),
        "-fps_mode", "passthrough",
        "-an",
        "-c:v", "libx264",
        "-preset", PROXY_ENCODER_PRESET,
        "-crf", str(PROXY_ENCODER_CRF),
        "-profile:v", PROXY_H264_PROFILE,
        "-level:v", PROXY_H264_LEVEL,
        "-g", str(gop_frames),
        "-keyint_min", str(gop_frames),
        "-sc_threshold", "0",
        "-bf", "1",
        "-refs", "2",
        "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:fullrange=off",
        "-pix_fmt", "yuv420p",
        "-color_range", "tv",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-video_track_timescale", str(track_timescale),
        "-movflags", "+faststart",
        str(output_path),
    ]


def _video_artifact_value(value: str, meta: Optional[Dict[str, Any]] = None) -> Any:
    if VideoUrlArtifact is not None:
        try:
            return VideoUrlArtifact(value=value, meta=dict(meta or {}))
        except Exception as exc:
            _diagnostic_exception("VideoUrlArtifact construction failed; using raw URL value", exc)
    return value


def _video_artifact(path: Path) -> Any:
    return _video_artifact_value(str(path.resolve()))


def _snapshot_publish_target(
    target: Path,
    backup_folder: Path,
    label: str,
) -> tuple[Path, Path, bool]:
    """Capture one file before a transaction may replace or create it."""
    target = target.resolve()
    if target.exists() and not target.is_file():
        raise RuntimeError(
            f"Project publication target is not a regular file: {target}"
        )
    backup_folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(
        _scene_path_key(target).encode("utf-8")
    ).hexdigest()[:12]
    backup = backup_folder / f"{_safe_scene_name(label)}-{digest}.previous"
    existed = target.is_file()
    if existed:
        shutil.copy2(target, backup)
    return target, backup, existed


def _created_publish_target_record(
    target: Path,
    backup_folder: Path,
    label: str,
) -> tuple[Path, Path, bool]:
    """Record a CREATE_NEW destination without copying its new payload."""
    target = target.resolve()
    backup_folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(
        _scene_path_key(target).encode("utf-8")
    ).hexdigest()[:12]
    backup = backup_folder / f"{_safe_scene_name(label)}-{digest}.previous"
    return target, backup, False


def _is_allowed_project_create_new_path(
    planned_target: Path,
    actual_target: Path,
) -> bool:
    """Restrict CREATE_NEW results to the planned project directory/family."""
    planned_target = planned_target.resolve()
    actual_target = actual_target.resolve()
    if (
        _scene_path_key(actual_target.parent)
        != _scene_path_key(planned_target.parent)
        or actual_target.suffix.casefold()
        != planned_target.suffix.casefold()
    ):
        return False

    flags = re.IGNORECASE if os.name == "nt" else 0
    actual_stem = actual_target.stem
    planned_stem = planned_target.stem
    if re.fullmatch(
        re.escape(planned_stem) + r"_0*[1-9][0-9]*",
        actual_stem,
        flags=flags,
    ):
        return True

    planned_index = re.fullmatch(r"(.*?)([0-9]+)", planned_stem)
    actual_index = re.fullmatch(r"(.*?)([0-9]+)", actual_stem)
    if planned_index is None or actual_index is None:
        return False
    planned_prefix, planned_digits = planned_index.groups()
    actual_prefix, actual_digits = actual_index.groups()
    prefix_equal = (
        actual_prefix.casefold() == planned_prefix.casefold()
        if os.name == "nt"
        else actual_prefix == planned_prefix
    )
    return (
        prefix_equal
        and len(actual_digits) == len(planned_digits)
        and int(actual_digits) > int(planned_digits)
    )


def _paths_match_bytes(left: Path, right: Path) -> bool:
    """Compare two files without loading either complete payload into memory."""
    try:
        if not left.is_file() or not right.is_file():
            return False
        if left.stat().st_size != right.stat().st_size:
            return False
        digests = []
        for candidate in (left, right):
            file_digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    file_digest.update(chunk)
            digests.append(file_digest.digest())
        return digests[0] == digests[1]
    except OSError:
        return False


def _copy_video_to_griptape_project(
    node: Any,
    path: Path,
    slot: int,
    *,
    transaction_records: Optional[List[tuple[Path, Path, bool]]] = None,
    backup_folder: Optional[Path] = None,
) -> tuple[Any, str]:
    """Return a project artifact and optionally enroll its files in rollback."""
    try:
        from griptape_nodes_library.utils import ffmpeg_utils  # type: ignore
        from griptape_nodes_library.utils.macro_path_utils import (  # type: ignore
            resolve_to_macro_path,
        )
    except Exception:
        value = str(path.resolve())
        return _video_artifact_value(value), value

    metadata = ffmpeg_utils.extract_video_player_metadata(str(path.resolve()))
    resolved = resolve_to_macro_path(str(path.resolve()))
    if not resolved.is_external:
        return _video_artifact_value(resolved.resolved_path, metadata), resolved.resolved_path
    if VideoUrlArtifact is None:
        value = str(path.resolve())
        return value, value

    node_name = _clean(getattr(node, "name", "")) or "HMBVideoPickerLibrary"
    parameter_name = VIDEO_OUTPUT_PARAMETER
    pending_records: List[tuple[Path, Path, bool]] = []
    planned_target: Optional[Path] = None
    if transaction_records is None or backup_folder is None:
        raise ValueError(
            "External Griptape project copies require a rollback transaction."
        )
    try:
        from griptape_nodes.files.file import FileDestination  # type: ignore
        from griptape_nodes.files.project_file import (  # type: ignore
            ProjectFileDestination,
        )
        from griptape_nodes.retained_mode.events.os_events import (  # type: ignore
            ExistingFilePolicy,
        )
        from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import (  # type: ignore
            _resolve_sidecar_path,
            write_sidecar,
        )
    except Exception as exc:
        raise RuntimeError(
            "Griptape project artifact rollback support is unavailable."
        ) from exc

    project_destination = ProjectFileDestination.from_situation(
        filename=path.name,
        situation="copy_external_file",
        node_name=node_name,
        parameter_name=parameter_name,
    )
    planned_target = Path(project_destination.resolve()).resolve()
    pending_records.append(
        _snapshot_publish_target(
            planned_target,
            backup_folder,
            f"video{slot}-media",
        )
    )
    destination_policy = getattr(
        project_destination,
        "_existing_file_policy",
        None,
    )
    destination_file = getattr(project_destination, "_file", None)
    metadata_builder = getattr(
        destination_file,
        "_build_file_metadata",
        None,
    )
    if not callable(metadata_builder):
        raise RuntimeError(
            "Griptape project destination cannot expose transactional metadata."
        )
    sidecar_content = metadata_builder()
    try:
        # The engine normally writes its metadata sidecar inside write_bytes().
        # Suppress that one internal call so the actual CREATE_NEW path can be
        # enrolled first and the sidecar's prior bytes can be snapshotted.
        had_builder_override = "_build_file_metadata" in vars(destination_file)
        previous_builder_override = vars(destination_file).get(
            "_build_file_metadata"
        )
        setattr(destination_file, "_build_file_metadata", lambda: None)
        try:
            # Griptape 0.93 dispatches binary writes only for an actual bytes
            # instance. Buffer-protocol objects such as mmap are treated as
            # text and fail with ``write() argument must be str``.
            source_bytes = path.read_bytes()
            saved_file = FileDestination.write_bytes(
                project_destination,
                source_bytes,
            )
        finally:
            if had_builder_override:
                setattr(
                    destination_file,
                    "_build_file_metadata",
                    previous_builder_override,
                )
            else:
                delattr(destination_file, "_build_file_metadata")

        # Register the exact base-write result before macro, metadata, or
        # artifact post-processing can raise.
        actual_target = Path(saved_file.resolve()).resolve()
        if _scene_path_key(actual_target) != _scene_path_key(planned_target):
            if (
                destination_policy != ExistingFilePolicy.CREATE_NEW
                or not _is_allowed_project_create_new_path(
                    planned_target,
                    actual_target,
                )
            ):
                raise RuntimeError(
                    "Griptape returned an unsafe project copy destination "
                    f"outside the approved CREATE_NEW path family: {actual_target}"
                )
            pending_records.append(
                _created_publish_target_record(
                    actual_target,
                    backup_folder,
                    f"video{slot}-created-media",
                )
            )
            if not _paths_match_bytes(actual_target, path):
                raise RuntimeError(
                    "Griptape CREATE_NEW result does not match the requested video."
                )
        elif not _paths_match_bytes(actual_target, path):
            raise RuntimeError(
                "Griptape project copy result does not match the requested video."
            )

        actual_metadata = Path(
            _resolve_sidecar_path(actual_target)
        ).resolve()
        if _scene_path_key(actual_metadata) == _scene_path_key(actual_target):
            raise RuntimeError(
                "Griptape metadata resolver returned the media file itself."
            )
        pending_records.append(
            _snapshot_publish_target(
                actual_metadata,
                backup_folder,
                f"video{slot}-metadata",
            )
        )
        if actual_metadata.exists():
            actual_metadata.unlink()
        write_sidecar(actual_target, sidecar_content)
        if not actual_metadata.is_file():
            raise RuntimeError(
                "Griptape project metadata sidecar was not created."
            )
        try:
            _read_json(actual_metadata)
        except Exception as exc:
            raise RuntimeError(
                "Griptape project metadata sidecar is not a valid JSON object."
            ) from exc

        macro_result = resolve_to_macro_path(str(actual_target))
        if macro_result.is_external:
            raise RuntimeError(
                "Griptape could not map its project copy back to a project macro."
            )
        macro_path = macro_result.resolved_path
        transaction_records.extend(pending_records)
    except Exception:
        if pending_records:
            HMBVideoPickerLibrary._restore_playblast_bundle(pending_records)
        raise
    return _video_artifact_value(macro_path, metadata), macro_path


def _normalized_picker_native_dimension(value: Any) -> Optional[Any]:
    """Return one finite positive JSON dimension without accepting booleans."""
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric) or numeric <= 0:
        return None
    if isinstance(value, (int, float)):
        return value
    return int(numeric) if numeric.is_integer() else numeric


def _normalized_picker_native_size(
    value: Any,
    *,
    minimum_height: int,
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    width = _normalized_picker_native_dimension(value.get("width"))
    height = _normalized_picker_native_dimension(value.get("height"))
    if width is None or height is None:
        return {}
    if float(width) < PICKER_WIDGET_MIN_WIDTH or float(height) < minimum_height:
        return {}
    return {"width": width, "height": height}


def _normalized_picker_expanded_size(value: Any) -> Dict[str, int]:
    """Validate and bound one durable expanded-node geometry."""

    normalized = _normalized_picker_native_size(
        value,
        minimum_height=PICKER_WIDGET_MIN_HEIGHT,
    )
    if not normalized:
        return {}
    return {
        "width": max(
            PICKER_WIDGET_MIN_WIDTH,
            min(6000, int(round(float(normalized["width"])))),
        ),
        "height": max(
            PICKER_WIDGET_MIN_HEIGHT,
            min(6000, int(round(float(normalized["height"])))),
        ),
    }


def _saved_picker_expanded_state_size(metadata: Any) -> Dict[str, int]:
    source = metadata if isinstance(metadata, dict) else {}
    normalized = _normalized_picker_expanded_size(
        source.get(PICKER_EXPANDED_SIZE_METADATA_KEY)
    ) or {
        "width": PICKER_START_WIDTH,
        "height": PICKER_START_HEIGHT,
    }
    return dict(normalized)


def _reconciled_picker_expanded_state_size(
    serialized_state: Any,
    metadata: Any,
) -> Dict[str, int]:
    """Choose one compatible expanded size when old snapshots disagree.

    Widget state and node metadata are written together in current workflows.
    Older workflows may contain only one side of that contract: native node
    resize persisted metadata while the Python widget-state merge discarded
    ``expanded_node_size``. A non-default valid value therefore wins over the
    other side's default; if both are custom, the serializable widget state is
    the newest explicit resize transaction and takes precedence.
    """

    if isinstance(serialized_state, dict):
        source = serialized_state
    else:
        try:
            decoded_state = json.loads(str(serialized_state or ""))
        except Exception:
            decoded_state = {}
        source = decoded_state if isinstance(decoded_state, dict) else {}
    state_size = _normalized_picker_expanded_size(
        source.get("expanded_node_size")
    )
    metadata_size = _saved_picker_expanded_state_size(metadata)
    default_size = {
        "width": PICKER_START_WIDTH,
        "height": PICKER_START_HEIGHT,
    }
    if state_size and state_size != default_size:
        return state_size
    if metadata_size != default_size:
        return metadata_size
    return state_size or metadata_size


def _restored_picker_native_geometry(
    serialized_metadata: Any,
) -> tuple[Dict[str, Any], Dict[str, Any], bool]:
    """Split compact cold-mount geometry from saved expanded geometry.

    v6 advertised the expanded 1200px node before the compact Loader could
    claim its 252px parameter row.  On Editor hosts with an adaptive trailing
    spacer, the unmatched outer allocation remained visible as a black panel.
    v7 always hydrates at the stable 1400x360 compact size. A valid serialized
    expanded resize is retained independently for the explicit header toggle;
    widget/media state remains owned by the serializable dict parameter.
    """
    metadata = serialized_metadata if isinstance(serialized_metadata, dict) else {}
    raw_size = metadata.get("size")
    saved_expanded_size = _normalized_picker_native_size(
        metadata.get(PICKER_EXPANDED_SIZE_METADATA_KEY),
        minimum_height=PICKER_WIDGET_MIN_HEIGHT,
    )
    raw_expanded_size = _normalized_picker_native_size(
        raw_size,
        minimum_height=PICKER_WIDGET_MIN_HEIGHT,
    )
    # A workflow saved while the full dashboard was visible has the latest
    # user resize in metadata.size. It takes precedence over the prior saved
    # expanded snapshot; compact or corrupt raw sizes never erase that snapshot.
    expanded_size = raw_expanded_size or saved_expanded_size or {
        "width": PICKER_START_WIDTH,
        "height": PICKER_START_HEIGHT,
    }
    compact_size = {
        "width": PICKER_START_WIDTH,
        "height": PICKER_COMPACT_NATIVE_HEIGHT,
    }
    try:
        native_size_version = max(
            0,
            int(float(metadata.get("hmb_picker_native_size_version") or 0)),
        )
    except (TypeError, ValueError, OverflowError):
        native_size_version = 0
    current_compact_size = _normalized_picker_native_size(
        raw_size,
        minimum_height=PICKER_COMPACT_NATIVE_MIN_HEIGHT,
    )
    canonical = (
        native_size_version == PICKER_NATIVE_SIZE_VERSION
        and current_compact_size == compact_size
        and saved_expanded_size == expanded_size
    )
    return compact_size, expanded_size, not canonical


def _restored_picker_native_size(
    serialized_metadata: Any,
) -> tuple[Dict[str, Any], bool]:
    """Compatibility wrapper returning the v7 compact cold-mount geometry."""
    compact_size, _expanded_size, migrated = _restored_picker_native_geometry(
        serialized_metadata
    )
    return compact_size, migrated


class HMBVideoPickerLibrary(DataNode):
    """One UI facade over two deliberately separated responsibilities.

    ``picker_shots`` plus the global ``videos`` catalog form the durable,
    per-Shot loader. Maya READ/Outliner/Color Pick data lives in each row's
    ``authoring_context`` and may only append a validated artifact to the
    workspace UUID captured when the operation starts. Switching scenes or
    Shots may reset/restore Maya authoring state; it must never replace or
    delete the loader catalog owned by another Shot.
    """

    def __init__(self, **kwargs: Any):
        serialized_metadata = kwargs.get("metadata")
        compact_size, expanded_size, _size_migrated = _restored_picker_native_geometry(
            serialized_metadata
        )
        # Prepare v7 metadata before DataNode/React Flow sees it. Passing a
        # serialized expanded size through ``super`` even briefly recreates the
        # load-time black-tail/viewport reflow this migration removes.
        prepared_metadata = (
            dict(serialized_metadata) if isinstance(serialized_metadata, dict) else {}
        )
        prepared_metadata["size"] = dict(compact_size)
        prepared_metadata[PICKER_EXPANDED_SIZE_METADATA_KEY] = dict(expanded_size)
        prepared_metadata["hmb_picker_native_size_version"] = PICKER_NATIVE_SIZE_VERSION
        prepared_kwargs = dict(kwargs)
        prepared_kwargs["metadata"] = prepared_metadata
        super().__init__(**prepared_kwargs)
        current_metadata = dict(getattr(self, "metadata", {}) or {})
        current_metadata.update(prepared_metadata)
        self.metadata = current_metadata
        self.category = "HMB_GP_Production"
        self.description = (
            "Per-Shot video loader with durable order/selection, plus a Maya "
            "Picker that appends validated Color/Depth/Motion playblasts to "
            "the captured Shot without replacing its loader history."
        )
        # Node ui_options describe only the cold/reload compact shell. Expanded
        # geometry stays separate and is restored only by the widget toggle.
        self.ui_options = {
            "width": PICKER_START_WIDTH,
            "height": PICKER_COMPACT_NATIVE_HEIGHT,
            "default_width": PICKER_START_WIDTH,
            "default_height": PICKER_COMPACT_NATIVE_HEIGHT,
            "preferred_width": PICKER_START_WIDTH,
            "preferred_height": PICKER_COMPACT_NATIVE_HEIGHT,
            "initial_width": PICKER_START_WIDTH,
            "initial_height": PICKER_COMPACT_NATIVE_HEIGHT,
            "node_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            "default_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            "initial_size": {"width": PICKER_START_WIDTH, "height": PICKER_COMPACT_NATIVE_HEIGHT},
            "min_width": PICKER_WIDGET_MIN_WIDTH,
            "min_height": PICKER_COMPACT_NATIVE_MIN_HEIGHT,
            "resizable": True,
        }
        self.width = compact_size["width"]
        self.height = compact_size["height"]
        self._hmb_video_output: Any = None
        self._hmb_node_deleted = False
        self._hmb_lifecycle_generation = 1
        self._hmb_delete_parent_called = False
        self._hmb_deletion_reconcile_called = False
        self._hmb_process_lock = threading.Lock()
        self._hmb_active_process: Optional[subprocess.Popen[Any]] = None
        self._hmb_worker_thread: Optional[threading.Thread] = None
        self._hmb_cancel_requested = threading.Event()
        self._hmb_operation_control_lock = threading.RLock()
        self._hmb_pending_operation_id = ""
        self._hmb_cleanup_files: List[Path] = []
        self._hmb_cleanup_dirs: List[Path] = []
        self._hmb_state_sync_local = threading.local()
        self._hmb_state_write_lock = threading.RLock()
        self._hmb_command_lock = threading.RLock()
        self._hmb_embedded_command_queue: List[Dict[str, Any]] = []
        # Serializes catalog authority changes and MP4 import commits. File
        # browsers may run concurrently, but no stale whole-state import may
        # overwrite another import or resurrect an ImageAsset-deleted Shot.
        self._hmb_catalog_commit_lock = threading.RLock()
        self._hmb_shot_snapshot_lock = threading.RLock()
        self._hmb_thumbnail_worker_lock = threading.Lock()
        self._hmb_thumbnail_worker: Optional[threading.Thread] = None
        self._hmb_thumbnail_recovery_generation = 0
        self._hmb_thumbnail_serialized_adoption_complete = False
        self._hmb_latest_widget_state: Optional[Dict[str, Any]] = None
        self._hmb_authoritative_state: Optional[Dict[str, Any]] = None
        self._hmb_state_revision = 0
        self._hmb_runtime_instance_id = f"{id(self):x}-{time.time_ns():x}"
        self._hmb_serialized_maya_scene_path = ""
        self._hmb_picker_publisher_uuid = str(uuid.uuid4())
        self._hmb_processed_action_ids: set[str] = set()
        self._hmb_active_operation: Optional[_OperationContext] = None
        self._hmb_pending_scene_selection: Optional[tuple[str, str]] = None
        self._hmb_last_public_output_fingerprint = ""
        self._hmb_last_shot_output_fingerprint = ""
        self._hmb_shot_catalog_snapshot: Optional[Dict[str, Any]] = None
        self._hmb_shot_catalog_refresh_count = 0
        self._hmb_shot_snapshot_identity = ""
        self._hmb_shot_snapshot_generation = 0
        self._hmb_standalone_catalog_identity = ""
        self._hmb_standalone_catalog_generation = 0
        self._hmb_shot_route_status: Dict[str, Any] = {}
        self._hmb_shared_routing_in_progress = False

        _add_picker_output(self)
        _add_video_output(self)
        _add_shot_picker_output(self)
        _retire_legacy_video_slot_outputs(self)
        _add_maya_scene_picker(self)
        _add_picker_command_bridge(self)
        _add_picker_widget(self)
        self._initialize_fresh_instance_state()
        _reorder_video_picker_parameters(self, 1)
        set_output(self, "PICKER_OUT", "")
        set_output(self, VIDEO_OUTPUT_PARAMETER, [])
        set_output(self, SHOT_PICKER_OUTPUT_PARAMETER, {})
        self._seed_python_runtime_state()
        _shot_routing.schedule_post_registration_reconcile(self)

    def _initialize_fresh_instance_state(self) -> None:
        """Seal a newly constructed node to instance-local empty defaults.

        Griptape restores a workflow only *after* constructing the node, via
        ``set_parameter_value(..., initial_setup=True)`` and the deserialize
        hooks below.  Constructor-time parameter values therefore never carry
        saved-workflow authority.  Replacing them here prevents a retained
        native FileSystemPicker/widget bridge (or a reused parameter template)
        from donating the previous node's Maya path to a newly added node.

        This is intentionally a direct initial-value store: no value-set hook,
        native browser, Maya validation, or output publication may run while a
        fresh node is still being registered.  Explicit serialized hydration,
        Browse, and READ all happen later and remain authoritative.
        """

        fresh_values = {
            "MAYA_SCENE": "",
            WIDGET_STATE_PARAMETER: _default_widget_state(),
            WIDGET_COMMAND_PARAMETER: _default_picker_command(
                self._hmb_runtime_instance_id
            ),
        }
        for name, value in fresh_values.items():
            self._store_initial_parameter_value(name, value)

    def _store_initial_parameter_value(self, name: str, value: Any) -> None:
        """Store one construction/deserialize value without lifecycle echoes."""

        stored_value = copy.deepcopy(value)
        parameter_values = getattr(self, "parameter_values", None)
        if isinstance(parameter_values, dict):
            parameter_values[name] = stored_value
            return
        parameter = _get_parameter_obj(self, name)
        if parameter is not None:
            setattr(parameter, "default_value", stored_value)

    def _seed_python_runtime_state(self) -> None:
        """Publish a boot handshake before the widget mounts.

        This is deliberately outside any value-set callback. If this entry is not
        visible, the running engine loaded a different/cached Python module.
        """
        state = _parse_state(_raw_parameter_value(self, WIDGET_STATE_PARAMETER))
        expanded_node_size = _saved_picker_expanded_state_size(
            getattr(self, "metadata", {})
        )
        expanded_geometry_changed = (
            state.get("expanded_node_size") != expanded_node_size
        )
        state["expanded_node_size"] = expanded_node_size
        if (
            state.get("python_core_loaded")
            and _clean(state.get("python_core_path")) == str(Path(__file__).resolve())
            and _clean(state.get("runtime_instance_id")) == self._hmb_runtime_instance_id
            and not expanded_geometry_changed
        ):
            return
        state, recovered_runtime_state = _recover_orphaned_runtime_state(state)
        state["python_core_loaded"] = True
        state["python_core_path"] = str(Path(__file__).resolve()).replace("\\", "/")
        state["runtime_instance_id"] = self._hmb_runtime_instance_id
        if not recovered_runtime_state:
            state["scene_request_status"] = "IDLE"
        state["state_revision"] = max(
            int(getattr(self, "_hmb_state_revision", 0) or 0),
            int(state.get("state_revision") or 0),
        ) + 1
        state["state_writer"] = "python"
        state["state_published_at_ms"] = int(time.time() * 1000)
        _append_activity_log(state, "INFO", f"Python core loaded: {state['python_core_path']}")
        if recovered_runtime_state:
            _append_activity_log(
                state,
                "SUCCESS",
                "Previous runtime state was normalized without replaying its one-shot command.",
            )
        mayabatch = _find_mayabatch()
        if mayabatch is not None:
            state["maya_executable"] = str(mayabatch).replace("\\", "/")
            state["maya_version"] = _maya_display_version(mayabatch)
            state["maya_available"] = True
            _append_activity_log(
                state,
                "SUCCESS",
                f"Maya {state['maya_version']} mayabatch detected: {state['maya_executable']}",
            )
        else:
            state["maya_executable"] = ""
            state["maya_version"] = ""
            state["maya_available"] = False
            _append_activity_log(
                state,
                "WARNING",
                "No mayabatch was detected at node startup. READ remains disabled until Maya is available.",
            )
        _append_activity_log(state, "SUCCESS", "Runtime mode: Shared / Orchestrator. Isolated Worker mode is disabled for HMB_GP_Production.")
        parameter = _get_parameter_obj(self, WIDGET_STATE_PARAMETER)
        widget_settable = bool(getattr(parameter, "settable", True)) if parameter is not None else False
        widget_property = bool(getattr(parameter, "allow_property", True)) if parameter is not None else False
        widget_type = _clean(getattr(parameter, "type", "")) if parameter is not None else ""
        contract_level = "SUCCESS" if parameter is not None and widget_settable and widget_property and widget_type == "dict" else "ERROR"
        _append_activity_log(
            state,
            contract_level,
            f"Primary widget state transport: parameter={WIDGET_STATE_PARAMETER}, type={widget_type or '<unknown>'}, settable={str(widget_settable).lower()}, property={str(widget_property).lower()}.",
        )
        _append_activity_log(
            state,
            "SUCCESS",
            f"Action transport: execution and language commands use the independent {WIDGET_COMMAND_PARAMETER} minimal JSON path; {WIDGET_STATE_PARAMETER} carries dashboard state only.",
        )
        _append_activity_log(state, "INFO", "Waiting for a Maya .mb or .ma file.")
        _begin_state_sync(self)
        try:
            setter = getattr(self, "set_parameter_value", None)
            if callable(setter):
                setter(WIDGET_STATE_PARAMETER, _parse_state(state))
            elif parameter is not None:
                setattr(parameter, "default_value", _parse_state(state))
        except Exception as exc:
            _diagnostic_exception("Python boot handshake publish failed", exc)
            if parameter is not None:
                try:
                    setattr(parameter, "default_value", _parse_state(state))
                except Exception as exc:
                    _diagnostic_exception("Boot-state compatibility fallback write failed", exc)
        finally:
            _end_state_sync(self)
        self._hmb_state_revision = int(state.get("state_revision") or 0)
        self._hmb_authoritative_state = dict(state)
        self._hmb_latest_widget_state = dict(state)
        command_parameter = _get_parameter_obj(self, WIDGET_COMMAND_PARAMETER)
        command_value = _default_picker_command(self._hmb_runtime_instance_id)
        _begin_state_sync(self)
        try:
            setter = getattr(self, "set_parameter_value", None)
            if callable(setter):
                setter(WIDGET_COMMAND_PARAMETER, command_value)
            elif command_parameter is not None:
                setattr(command_parameter, "default_value", command_value)
        except Exception as exc:
            _diagnostic_exception("Command bridge boot handshake publish failed", exc)
            if command_parameter is not None:
                try:
                    setattr(command_parameter, "default_value", command_value)
                except Exception as fallback_exc:
                    _diagnostic_exception("Command bridge boot fallback failed", fallback_exc)
        finally:
            _end_state_sync(self)

    def _ensure_parameters(self) -> None:
        _add_picker_output(self)
        _add_video_output(self)
        _add_shot_picker_output(self)
        _retire_legacy_video_slot_outputs(self)
        _add_maya_scene_picker(self)
        _add_picker_command_bridge(self)
        _add_picker_widget(self)
        _reorder_video_picker_parameters(self)

    def _picker_state(self) -> Dict[str, Any]:
        """Return the newest committed state without reviving stale widget caches."""
        raw_state = _parse_state(_raw_parameter_value(self, WIDGET_STATE_PARAMETER))
        authoritative = getattr(self, "_hmb_authoritative_state", None)
        if isinstance(authoritative, dict):
            authoritative_state = _parse_state(authoritative)
            if int(authoritative_state.get("state_revision") or 0) >= int(raw_state.get("state_revision") or 0):
                return authoritative_state
        self._hmb_authoritative_state = dict(raw_state)
        self._hmb_state_revision = max(
            int(getattr(self, "_hmb_state_revision", 0) or 0),
            int(raw_state.get("state_revision") or 0),
        )
        return raw_state

    def _synchronize_picker_expanded_geometry_metadata(
        self,
        state: Dict[str, Any],
    ) -> bool:
        """Commit state/metadata expanded geometry as one validated value.

        ``metadata.size`` remains the host-owned live shell size. The dedicated
        metadata key is the durable expanded geometry used after the next
        compact cold mount, and must always match the serializable widget state.
        """

        expanded_size = _normalized_picker_expanded_size(
            state.get("expanded_node_size")
        ) or _saved_picker_expanded_state_size(getattr(self, "metadata", {}))
        state["expanded_node_size"] = dict(expanded_size)
        previous_metadata = dict(getattr(self, "metadata", {}) or {})
        synchronized_metadata = dict(previous_metadata)
        synchronized_metadata[PICKER_EXPANDED_SIZE_METADATA_KEY] = dict(
            expanded_size
        )
        synchronized_metadata["hmb_picker_native_size_version"] = (
            PICKER_NATIVE_SIZE_VERSION
        )
        if synchronized_metadata == previous_metadata:
            return False
        self.metadata = synchronized_metadata
        return True

    @contextmanager
    def _hmb_catalog_state_commit(self):
        """Serialize catalog RMW transactions in one invariant lock order."""

        catalog_lock = getattr(self, "_hmb_catalog_commit_lock", None)
        state_lock = getattr(self, "_hmb_state_write_lock", None)
        if catalog_lock is None:
            if state_lock is None:
                yield
                return
            with state_lock:
                yield
                return
        with catalog_lock:
            if state_lock is None:
                yield
                return
            with state_lock:
                yield

    def _write_state(self, state: Dict[str, Any]) -> None:
        """Publish one serialized state snapshot.

        Worker-originated updates use Griptape's retained-mode request bus so the
        orchestrator publishes a distinct external widget update. A direct setter
        remains only as the local-validation fallback.
        """
        if getattr(self, "_hmb_node_deleted", False):
            return
        with self._hmb_state_write_lock:
            if getattr(self, "_hmb_node_deleted", False):
                return
            owner_generation = int(
                getattr(self, "_hmb_lifecycle_generation", 0) or 0
            )
            normalized = _parse_state(state)
            logged_messages = {
                _clean(entry.get("message"))
                for entry in _normalize_activity_log(
                    normalized.get("activity_log")
                )
                if _clean(entry.get("message"))
            }
            # ``warnings`` remains a compact compatibility field, but every
            # notice is also represented in the sole visible notification
            # surface: the activity log. Existing ERROR entries keep their red
            # severity; ordinary notices migrate as WARNING without duplicates.
            for warning in normalized.get("warnings", []):
                compact_warning = _compact_ui_diagnostic(
                    warning,
                    _UI_WARNING_MESSAGE_LIMIT,
                )
                if compact_warning and compact_warning not in logged_messages:
                    _append_activity_log(
                        normalized,
                        "WARNING",
                        compact_warning,
                    )
                    logged_messages.add(compact_warning)
            current_revision = max(
                int(getattr(self, "_hmb_state_revision", 0) or 0),
                int(normalized.get("state_revision") or 0),
            )
            normalized["state_revision"] = current_revision + 1
            normalized["state_writer"] = "python"
            normalized["writer_runtime_instance_id"] = (
                self._hmb_runtime_instance_id
            )
            normalized["writer_lifecycle_generation"] = owner_generation
            normalized["state_published_at_ms"] = int(time.time() * 1000)
            previous_metadata = copy.deepcopy(
                dict(getattr(self, "metadata", {}) or {})
            )
            self._synchronize_picker_expanded_geometry_metadata(normalized)
            # SaveWorkflow reads ``node.parameter_values`` directly. Stage the
            # completed import/reorder snapshot there before broadcasting it to
            # the retained UI, so an immediate Ctrl+S cannot serialize the
            # previous video catalog while the browser notification is pending.
            parameter_values = getattr(self, "parameter_values", None)
            had_serialized_value = (
                isinstance(parameter_values, dict)
                and WIDGET_STATE_PARAMETER in parameter_values
            )
            previous_serialized_value = copy.deepcopy(
                _raw_parameter_value(self, WIDGET_STATE_PARAMETER)
            )
            self._store_initial_parameter_value(
                WIDGET_STATE_PARAMETER,
                normalized,
            )
            _begin_state_sync(self)
            try:
                if not _request_parameter_value(
                    self,
                    WIDGET_STATE_PARAMETER,
                    normalized,
                    "dict",
                ):
                    _set_parameter_value(self, WIDGET_STATE_PARAMETER, normalized)
            except Exception:
                self.metadata = previous_metadata
                if isinstance(parameter_values, dict):
                    if had_serialized_value:
                        parameter_values[WIDGET_STATE_PARAMETER] = (
                            previous_serialized_value
                        )
                    else:
                        parameter_values.pop(WIDGET_STATE_PARAMETER, None)
                else:
                    self._store_initial_parameter_value(
                        WIDGET_STATE_PARAMETER,
                        previous_serialized_value,
                    )
                raise
            finally:
                _end_state_sync(self)
            if (
                getattr(self, "_hmb_node_deleted", False)
                or owner_generation
                != int(getattr(self, "_hmb_lifecycle_generation", 0) or 0)
            ):
                return
            self._hmb_state_revision = normalized["state_revision"]
            self._hmb_authoritative_state = dict(normalized)
            self._hmb_latest_widget_state = dict(normalized)

    @staticmethod
    def _merge_widget_state(authoritative: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(_parse_state(authoritative))
        # Preserve the raw UUID-scoped UI delta before normalization. A stale
        # browser echo may carry an incomplete catalog/ownership list; parsing
        # that echo first would discard an otherwise valid selection before it
        # can be filtered against the authoritative workspace membership.
        raw_incoming = dict(incoming) if isinstance(incoming, dict) else {}
        raw_incoming_rows = (
            list(raw_incoming.get("picker_shots") or [])
            if isinstance(raw_incoming.get("picker_shots"), list)
            else []
        )
        raw_incoming_active_uuid = _uuid_text(
            raw_incoming.get("active_picker_shot_uuid")
        )
        incoming = _parse_state(incoming)
        authoritative_revision = int(merged.get("state_revision") or 0)
        incoming_revision = int(incoming.get("state_revision") or 0)
        stale_picker_echo = incoming_revision < authoritative_revision
        widget_layout_fields = {
            "lower_panel_ratio", "main_split_ratio", "right_split_ratio", "node_width", "node_height",
            "outliner_panel_height", "viewport_panel_height", "right_section_heights",
            "ui_layout_version", "ui_theme",
            "activity_log_text", "activity_log_text_user_edited", "activity_log_cleared",
        }
        widget_authoring_fields = {
            "workspace_view", "selected_outliner_path", "selected_outliner_name", "selected_outliner_uuid",
            "selected_color", "outliner_expanded", "outliner_search", "selected_camera",
            "slot_assignments", "slot_visibility", "snapshot_frame", "snapshot_video_slot",
            "scene_draft_path", "scene_request_path",
            "output_width", "output_height",
            "original_enabled", "mask_enabled",
            "depth_enabled", "motion_guide_enabled",
            "depth_video_slot", "motion_guide_video_slot",
        }
        for key in widget_layout_fields:
            if key in incoming:
                merged[key] = incoming[key]
        if not stale_picker_echo:
            # Native resize finalization is a widget-owned layout transaction.
            # Accept only a complete, finite expanded geometry from a current
            # revision; parsing an absent/malformed field to the default must
            # never erase the last valid saved resize.
            incoming_expanded_size = _normalized_picker_expanded_size(
                raw_incoming.get("expanded_node_size")
            )
            if incoming_expanded_size:
                merged["expanded_node_size"] = incoming_expanded_size
            # A READ result is backend authority. Delayed browser props from
            # before READ must never erase its Outliner, selected Maya object,
            # or color bindings. Current UI edits still merge normally.
            for key in widget_authoring_fields:
                if key in incoming:
                    merged[key] = incoming[key]
            # Catalog rows and media are Python/ImageAsset authority even when
            # a browser echo has the same revision. Apply only workspace-UUID
            # scoped UI deltas; never accept row creation/removal, ownership,
            # binding, route metadata, or a replacement video catalog.
            incoming_rows_by_uuid = {
                _uuid_text(row.get("workspace_uuid")): row
                for row in raw_incoming_rows
                if isinstance(row, dict)
                and _uuid_text(row.get("workspace_uuid"))
            }
            accepted_workspace_delta = False
            merged_rows: List[Dict[str, Any]] = []
            for raw_row in merged.get("picker_shots", []):
                if not isinstance(raw_row, dict):
                    continue
                row = dict(raw_row)
                workspace_uuid = _uuid_text(row.get("workspace_uuid"))
                incoming_row = incoming_rows_by_uuid.get(workspace_uuid)
                try:
                    row_revision = max(0, int(row.get("revision") or 0))
                except (TypeError, ValueError, OverflowError):
                    row_revision = 0
                try:
                    incoming_row_revision = max(
                        0,
                        int(incoming_row.get("revision") or 0),
                    ) if isinstance(incoming_row, dict) else -1
                except (TypeError, ValueError, OverflowError):
                    incoming_row_revision = -1
                # Global state_revision identifies the last Python snapshot,
                # not the ordering of rapid per-Shot UI edits made from that
                # snapshot.  Every real workspace mutation increments its row
                # revision in the widget.  Require that monotonic token here so
                # a delayed same-global-revision echo cannot restore an older
                # selection/order/preview after a newer Shot edit was already
                # committed. Equal row revisions are an acknowledgement only;
                # the Python-owned selection/order/preview remains authoritative.
                if (
                    isinstance(incoming_row, dict)
                    and incoming_row_revision > row_revision
                ):
                    accepted_workspace_delta = True
                    owned_uids = _picker_representative_video_uids(
                        row.get("video_asset_uids")
                    )
                    owned_set = set(owned_uids)
                    selected_uids = _picker_representative_video_uids(
                        incoming_row.get("selected_video_uids"),
                        "",
                        owned_set,
                    )
                    preview_uid = _clean(
                        incoming_row.get("preview_video_uid")
                    )
                    if preview_uid not in owned_set:
                        preview_uid = (
                            selected_uids[0]
                            if selected_uids
                            else _clean(row.get("preview_video_uid"))
                        )
                    row.update({
                        "name": _clean(incoming_row.get("name"))[:128]
                        or _clean(row.get("name"))[:128],
                        "custom_name": bool(
                            incoming_row.get("custom_name")
                        ),
                        "selected_video_uids": selected_uids,
                        "preview_video_uid": preview_uid,
                        "scene_draft_path": _maya_scene_path_text(
                            incoming_row.get("scene_draft_path")
                        ),
                        "current_frame": incoming_row.get(
                            "current_frame",
                            row.get("current_frame", 0.0),
                        ),
                        "viewport_mode": incoming_row.get(
                            "viewport_mode",
                            row.get("viewport_mode", "video"),
                        ),
                        "active_snapshot_uid": _clean(
                            incoming_row.get("active_snapshot_uid")
                        ),
                        "selected_video_slot": incoming_row.get(
                            "selected_video_slot",
                            row.get("selected_video_slot", 1),
                        ),
                        "authoring_context": _normalize_picker_authoring_context(
                            incoming_row.get("authoring_context")
                            if "authoring_context" in incoming_row
                            else row.get("authoring_context")
                        ),
                        "revision": max(
                            row_revision,
                            incoming_row_revision,
                        ),
                    })
                merged_rows.append(row)
            merged["picker_shots"] = merged_rows
            requested_active_uuid = raw_incoming_active_uuid
            if requested_active_uuid in {
                _uuid_text(row.get("workspace_uuid"))
                for row in merged_rows
            }:
                merged["active_picker_shot_uuid"] = requested_active_uuid

            if accepted_workspace_delta:
                # ``videos[*].selected`` is the legacy global projection of
                # the active Picker Shot.  A current row edit can legitimately
                # make its selected list empty while an unselected card keeps
                # playing in the Loader preview.  Project the accepted row
                # before the final parse so the legacy catalog flags cannot
                # resurrect the just-deselected card as a fallback selection.
                active_workspace_uuid = _uuid_text(
                    merged.get("active_picker_shot_uuid")
                )
                active_workspace = next(
                    (
                        row for row in merged_rows
                        if _uuid_text(row.get("workspace_uuid"))
                        == active_workspace_uuid
                    ),
                    None,
                )
                if isinstance(active_workspace, dict):
                    owned_uids = _picker_representative_video_uids(
                        active_workspace.get("video_asset_uids")
                    )
                    owned_set = set(owned_uids)
                    selected_uids = _picker_representative_video_uids(
                        active_workspace.get("selected_video_uids"),
                        "",
                        owned_set,
                    )
                    selection_order_by_uid = {
                        uid: index + 1
                        for index, uid in enumerate(selected_uids)
                    }
                    active_workspace["selected_video_uids"] = selected_uids
                    preview_uid = _clean(
                        active_workspace.get("preview_video_uid")
                    )
                    if preview_uid not in owned_set:
                        preview_uid = (
                            selected_uids[0]
                            if selected_uids
                            else owned_uids[0]
                            if owned_uids else ""
                        )
                    active_workspace["preview_video_uid"] = preview_uid
                    for item in merged.get("videos", []):
                        if not isinstance(item, dict):
                            continue
                        uid = _clean(
                            item.get("video_uid") or item.get("source_uid")
                        )
                        order = selection_order_by_uid.get(uid, 0)
                        item["selected"] = bool(order)
                        item["selection_order"] = order
                        item["video_slot"] = order
                        if isinstance(item.get("frame_metadata"), dict):
                            item["frame_metadata"]["video_slot"] = (
                                f"@video{order}" if order else ""
                            )
                    merged["preview_video_uid"] = preview_uid
                    merged["selected_video_uid"] = preview_uid
                    resolved_preview_slot = (
                        selection_order_by_uid.get(preview_uid)
                        or max(
                            1,
                            min(
                                max(1, len(selected_uids)),
                                _positive_int(
                                    active_workspace.get(
                                        "selected_video_slot"
                                    )
                                ) or 1,
                            ),
                        )
                    )
                    active_workspace["selected_video_slot"] = (
                        resolved_preview_slot
                    )
                    merged["selected_video_slot"] = resolved_preview_slot
        # Snapshot media/history is backend authoritative. A current widget may
        # move only the active pointer/view mode, and an older browser echo may
        # not roll either pointer back after Python has published new history.
        if int(incoming.get("state_revision") or 0) >= int(
            merged.get("state_revision") or 0
        ):
            merged["active_snapshot_uid"] = _clean(
                incoming.get("active_snapshot_uid")
            )
            merged["viewport_mode"] = (
                "snapshot"
                if _clean(incoming.get("viewport_mode")).lower() == "snapshot"
                else "video"
            )
        merged["activity_log"] = _merge_activity_logs(merged.get("activity_log"), incoming.get("activity_log"))
        merged["state_revision"] = max(
            int(merged.get("state_revision") or 0),
            int(incoming.get("state_revision") or 0),
        )
        merged["state_published_at_ms"] = max(
            int(merged.get("state_published_at_ms") or 0),
            int(incoming.get("state_published_at_ms") or 0),
        )
        merged["pending_action"] = ""
        merged["pending_action_id"] = ""
        merged["frontend_seen_revision"] = max(
            int(merged.get("frontend_seen_revision") or 0),
            int(incoming.get("frontend_seen_revision") or 0),
            int(incoming.get("state_revision") or 0),
        )
        return _parse_state(merged)

    @staticmethod
    def _video_item_for_slot(state: Dict[str, Any], slot: int) -> Optional[Dict[str, Any]]:
        for item in state.get("videos", []):
            if isinstance(item, dict) and int(item.get("video_slot") or 0) == slot:
                return item
        return None

    @staticmethod
    def _slot_assignment_item_for_slot(state: Dict[str, Any], slot: int) -> Optional[Dict[str, Any]]:
        for item in state.get("slot_assignments", []):
            if isinstance(item, dict) and int(item.get("video_slot") or 0) == slot:
                return item
        return None

    @staticmethod
    def _editable_assignments_for_slot(state: Dict[str, Any], slot: int) -> List[Dict[str, Any]]:
        item = HMBVideoPickerLibrary._slot_assignment_item_for_slot(state, slot)
        return _normalize_assignment_bindings(item.get("bindings") if item else [], slot)

    @staticmethod
    def _derive_asset_id(group_name: str) -> str:
        text = _clean(group_name).replace('\\', '/')
        if not text:
            return ''
        leaf = text.split('|')[-1] if '|' in text else text.split('/')[-1]
        leaf = leaf or text
        return _clean(leaf)

    def _selected_slot_job_bindings(self, state: Dict[str, Any], slot: int) -> List[Dict[str, Any]]:
        bindings = self._editable_assignments_for_slot(state, slot)
        normalized: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_colors = set()
        seen_groups = set()
        seen_instances: set[tuple[str, str]] = set()
        enabled_rows = [item for item in bindings if bool(item.get("enabled", True))]
        if not enabled_rows:
            return []
        if not any(_clean(item.get("group_name")) or _clean(item.get("color")) for item in enabled_rows):
            return []
        for index, binding in enumerate(enabled_rows, start=1):
            group_name = _clean(binding.get("group_name"))
            full_dag_path = _clean(binding.get("full_dag_path"))
            maya_uuid = _clean(binding.get("maya_uuid"))
            reference_node = _clean(binding.get("reference_node"))
            reference_file = _clean(binding.get("reference_file"))
            proxy_manager = _clean(binding.get("proxy_manager"))
            proxy_tag = _clean(binding.get("proxy_tag"))
            color = _clean(binding.get("color"))
            if not group_name and not full_dag_path and not color:
                continue
            if not full_dag_path and not group_name:
                errors.append(f"Assignment row {index} is missing a Maya Outliner group.")
                continue
            if not color:
                # A readable group row without a Color Pick is simply outside
                # the requested render scope. It must not turn an optional
                # Color Pick into a generation prerequisite.
                continue
            if color not in MARKER_ORDER:
                errors.append(f"Assignment row {index} uses unsupported Color Pick: {color}")
            if color in seen_colors and color not in REPEATABLE_MARKERS:
                errors.append(f"Duplicate Color Pick in @video{slot}: {color}")
            seen_colors.add(color)
            group_key = full_dag_path or group_name
            if group_key in seen_groups:
                errors.append(f"Duplicate Maya group in @video{slot}: {group_key}")
            seen_groups.add(group_key)
            asset_id = self._derive_asset_id(group_name or full_dag_path)
            if not asset_id:
                errors.append(f"Assignment row {index} could not derive Asset ID from Group Name: {group_name}")
            instance_identity = (
                ("uuid", maya_uuid.casefold())
                if maya_uuid
                else ("dag", full_dag_path.replace("\\", "/").casefold())
                if full_dag_path
                else ("group", group_name.casefold())
            )
            if instance_identity in seen_instances:
                errors.append(
                    f"Duplicate Maya instance in @video{slot}: "
                    f"{full_dag_path or group_name}"
                )
            seen_instances.add(instance_identity)
            normalized.append({
                "group_name": group_name or self._derive_asset_id(full_dag_path),
                "full_dag_path": full_dag_path,
                "maya_uuid": maya_uuid,
                "reference_node": reference_node,
                "reference_file": reference_file,
                "proxy_manager": proxy_manager,
                "proxy_tag": proxy_tag,
                "subject_root": full_dag_path,
                "color": color,
                "asset_id": asset_id,
                "enabled": True,
                "video_slot": slot,
                "picker_order": max(1, int(binding.get("picker_order") or index)),
            })
        if errors:
            raise RuntimeError(' | '.join(errors))
        return normalized

    @staticmethod
    def _selected_slot_hidden_paths(state: Dict[str, Any], slot: int) -> List[str]:
        for item in state.get("slot_visibility", []):
            if isinstance(item, dict) and int(item.get("video_slot") or 0) == int(slot):
                return [_clean(path) for path in item.get("hidden_paths", []) if _clean(path)]
        return []

    def _apply_selected_view_fields(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state = _parse_state(state)
        slot = int(state.get("selected_video_slot") or 1)
        item = self._video_item_for_slot(state, slot)
        if bool(state.get("original_preview_enabled")):
            metadata = (
                dict(state.get("original_metadata"))
                if isinstance(state.get("original_metadata"), dict)
                else {}
            )
            resolution = (
                dict(metadata.get("resolution"))
                if isinstance(metadata.get("resolution"), dict)
                else {}
            )
            fps = float(metadata.get("fps") or state.get("source_fps") or 0.0)
            start_frame = float(
                metadata.get("start_frame", state.get("start_frame")) or 0.0
            )
            end_frame = float(
                metadata.get("end_frame", state.get("end_frame")) or 0.0
            )
            frame_count = max(
                0,
                int(
                    metadata.get("frame_count")
                    or (
                        _maya_sequence_frame_count(start_frame, end_frame)
                        if end_frame >= start_frame
                        else 0
                    )
                ),
            )
            duration = frame_count / fps if frame_count > 0 and fps > 0 else 0.0
            frame_metadata = _video_frame_metadata(
                {
                    "source_fps": fps,
                    "output_fps": fps,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "has_maya_frame_range": end_frame >= start_frame,
                    "decoded_frame_count": frame_count,
                    "source_frame_count": frame_count,
                    "source_duration_seconds": duration,
                    "output_width": int(resolution.get("width") or state.get("output_width") or OUTPUT_WIDTH),
                    "output_height": int(resolution.get("height") or state.get("output_height") or OUTPUT_HEIGHT),
                    "markers": [],
                },
                slot,
            )
            state.update({
                "video_path": _clean(state.get("original_video_path")),
                "video_url": _clean(state.get("original_video_url")),
                "camera": _clean(metadata.get("camera") or state.get("selected_camera")),
                "source_fps": fps,
                "output_fps": fps,
                "output_width": int(resolution.get("width") or state.get("output_width") or OUTPUT_WIDTH),
                "output_height": int(resolution.get("height") or state.get("output_height") or OUTPUT_HEIGHT),
                "source_frame_count": frame_count,
                "output_frame_count": frame_count,
                "decoded_frame_count": frame_count,
                "source_duration_seconds": duration,
                "output_duration_seconds": duration,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "has_maya_frame_range": end_frame >= start_frame,
                "frame_metadata": frame_metadata,
                "markers": [],
            })
            return state
        if item is None:
            state.update({
                "video_path": "",
                "video_url": "",
                "markers": [],
            })
            return state
        for key in (
            "video_path", "video_url", "camera", "source_fps", "output_fps",
            "output_width", "output_height", "source_frame_count", "output_frame_count",
            "decoded_frame_count", "source_duration_seconds", "output_duration_seconds",
            "start_frame", "end_frame", "has_maya_frame_range", "frame_metadata", "markers",
        ):
            state[key] = item.get(key, state.get(key))
        return state

    def _build_picker_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return _build_synchronized_video_outputs(state)[0]

    @staticmethod
    def _validate_image_shot_catalog_snapshot(
        value: Any,
        *,
        expected_channel_uuid: str = "",
    ) -> Dict[str, Any]:
        required = {
            "schema", "version", "publisher_instance_uuid", "channel_uuid",
            "generation", "metadata_sha256", "shots",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("ImageAsset Shot catalog has unknown or missing fields.")
        if value.get("schema") != "hmb-shot-routing-catalog" or value.get("version") != 1:
            raise ValueError("ImageAsset Shot catalog schema is invalid.")
        publisher = _uuid_text(value.get("publisher_instance_uuid"))
        channel = _uuid_text(value.get("channel_uuid"))
        expected = _uuid_text(expected_channel_uuid)
        if not publisher or not channel or (expected and channel != expected):
            raise ValueError("ImageAsset Shot catalog publisher/channel mismatch.")
        generation = value.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0:
            raise ValueError("ImageAsset Shot catalog generation is invalid.")
        raw_shots = value.get("shots")
        if (
            not isinstance(raw_shots, list)
            or not 1 <= len(raw_shots) <= SHOT_ROUTING_MAX_SHOTS
        ):
            raise ValueError("ImageAsset Shot catalog collections are invalid.")
        shots: List[Dict[str, Any]] = []
        shot_ids: set[str] = set()
        shot_numbers: set[int] = set()
        for raw in raw_shots:
            if not isinstance(raw, dict) or set(raw) != {
                "shot_uuid", "number", "name", "revision",
            }:
                raise ValueError("ImageAsset Shot record is invalid.")
            shot_uuid = _uuid_text(raw.get("shot_uuid"))
            number = raw.get("number")
            revision = raw.get("revision")
            name = _clean(raw.get("name"))[:128]
            if (
                not shot_uuid or shot_uuid in shot_ids or not name
                or not isinstance(raw.get("name"), str)
                or raw.get("name") != name
                or len(name) > 128
                or not isinstance(number, int) or isinstance(number, bool)
                or number in shot_numbers or not 1 <= number <= SHOT_ROUTING_MAX_SHOTS
                or not isinstance(revision, int) or isinstance(revision, bool) or revision < 0
            ):
                raise ValueError("ImageAsset Shot identity/revision is invalid.")
            shot_ids.add(shot_uuid)
            shot_numbers.add(number)
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
        metadata_hash = _clean(value.get("metadata_sha256")).casefold()
        if metadata_hash != _sha256_canonical(metadata_document):
            raise ValueError("ImageAsset Shot metadata hash does not match.")
        return {
            **copy.deepcopy(value),
            "publisher_instance_uuid": publisher,
            "channel_uuid": channel,
            "shots": shots,
            "metadata_sha256": metadata_hash,
        }

    def _hmb_shot_channel_subscription(self) -> Dict[str, Any]:
        state = self._picker_state()
        channel_uuid = _uuid_text(state.get("channel_uuid"))
        shot_uuid = _uuid_text(state.get("shot_uuid"))
        if not channel_uuid:
            # A standalone Picker still owns one bounded local Shot catalog for
            # downstream video-conditioned generation. ImageAsset remains the
            # authority whenever it exists; its catalog replaces this private
            # fallback without changing the Picker's durable video ownership.
            catalog = self._hmb_standalone_shot_routing_catalog()
            rows = [
                item for item in state.get("picker_shots", [])
                if isinstance(item, dict) and _uuid_text(item.get("workspace_uuid"))
            ]
            active_workspace = _uuid_text(state.get("active_picker_shot_uuid"))
            active = next(
                (
                    item for item in rows
                    if _uuid_text(item.get("workspace_uuid")) == active_workspace
                ),
                rows[0] if rows else {},
            )
            fallback_shot_uuid = _uuid_text(active.get("workspace_uuid"))
            fallback_number = max(
                1,
                min(SHOT_ROUTING_MAX_SHOTS, int(active.get("number") or 1)),
            )
            fallback_name = _clean(active.get("name"))[:128] or f"Shot {fallback_number}"
            return {
                "schema": "hmb-shot-channel-subscription",
                "version": 1,
                "participant_kind": "video_picker",
                "enabled": bool(catalog and fallback_shot_uuid),
                "channel_uuid": _uuid_text(catalog.get("channel_uuid")),
                "shot_uuid": fallback_shot_uuid,
                "shot_number": fallback_number,
                "shot_name": fallback_name,
            }
        # VideoPicker is a flow-level Shot publisher.  Once it has accepted the
        # ImageAsset channel it can publish the complete per-Shot snapshot even
        # while its local workspace selector displays ``Only``.  Requiring an
        # active workspace UUID here detached PICKER_OUT from every Prompt until
        # the user made an otherwise unnecessary UI selection.  The central
        # router deliberately exempts ImageAsset/VideoPicker from the per-Shot
        # UUID requirement for this reason.
        enabled = bool(channel_uuid)
        selected = bool(channel_uuid and shot_uuid)
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": "video_picker",
            "enabled": enabled,
            # Retain the accepted channel while Only is selected so the
            # backend-supplied options remain visible.  ``enabled`` is the
            # sole remote-routing gate and additionally requires Shot UUID.
            "channel_uuid": channel_uuid,
            "shot_uuid": shot_uuid if selected else "",
            "shot_number": int(state.get("shot_number") or 1) if selected else 1,
            "shot_name": (_clean(state.get("shot_name")) or "Shot 1") if selected else "Only",
        }

    def _hmb_export_reset_handoff(self) -> Dict[str, Any]:
        """Export only the Loader catalog and Shot membership for Reset."""

        # Deletion is dispatched on the retained-mode thread. Never wait for a
        # worker-held catalog/state lock here; `_picker_state()` already returns
        # the last atomically committed authoritative snapshot.
        state = _parse_state(self._picker_state())
        return {
            "schema": RESET_HANDOFF_SCHEMA,
            "version": RESET_HANDOFF_VERSION,
            "identity_contract": RESET_HANDOFF_IDENTITY_CONTRACT,
            "participant_kind": "video_picker",
            "state": state,
        }

    def _hmb_adopt_reset_handoff(self, value: Any) -> bool:
        """Adopt Loader media while retaining this new runtime's identity."""

        payload = value if isinstance(value, dict) else {}
        if (
            payload.get("schema") != RESET_HANDOFF_SCHEMA
            or payload.get("version") != RESET_HANDOFF_VERSION
            or payload.get("identity_contract")
            != RESET_HANDOFF_IDENTITY_CONTRACT
            or _clean(payload.get("participant_kind")) != "video_picker"
            or bool(getattr(self, "_hmb_node_deleted", False))
        ):
            return False
        source_state = payload.get("state")
        if not isinstance(source_state, dict):
            return False
        fresh_runtime = _parse_state(self._picker_state())
        adopted = _reset_picker_state_preserving_loader_media(source_state)
        for field in (
            "python_core_loaded",
            "python_core_path",
            "runtime_instance_id",
            "maya_executable",
            "maya_version",
            "maya_available",
            "expanded_node_size",
            "activity_log",
        ):
            adopted[field] = copy.deepcopy(fresh_runtime.get(field))
        adopted["state_revision"] = max(
            int(adopted.get("state_revision") or 0),
            int(fresh_runtime.get("state_revision") or 0),
        ) + 1
        adopted["writer_runtime_instance_id"] = self._hmb_runtime_instance_id
        adopted["writer_lifecycle_generation"] = int(
            getattr(self, "_hmb_lifecycle_generation", 1) or 1
        )
        adopted["state_writer"] = "python"
        adopted["scene_request_status"] = "IDLE"
        adopted = self._apply_selected_view_fields(_parse_state(adopted))

        # Native Maya/FileSystemPicker state belongs to the retired authoring
        # instance. The Loader records carry their own verified media paths.
        self._store_initial_parameter_value("MAYA_SCENE", "")
        self._hmb_serialized_maya_scene_path = ""
        self._hmb_shot_catalog_snapshot = None
        self._hmb_shot_catalog_refresh_count = 0
        self._write_state(adopted)
        committed = self._apply_selected_view_fields(self._picker_state())
        self._sync_outputs_from_state(committed)
        expected_uids = [
            _clean(item.get("video_uid") or item.get("source_uid"))
            for item in adopted.get("videos", [])
            if isinstance(item, dict)
        ]
        committed_uids = [
            _clean(item.get("video_uid") or item.get("source_uid"))
            for item in committed.get("videos", [])
            if isinstance(item, dict)
        ]
        return bool(
            committed_uids == expected_uids
            and committed.get("picker_shots") == adopted.get("picker_shots")
            and _clean(committed.get("runtime_instance_id"))
            == self._hmb_runtime_instance_id
        )

    def _hmb_standalone_shot_routing_catalog(self) -> Dict[str, Any]:
        """Publish a media-free local catalog when no ImageAsset exists.

        This fallback is intentionally private to optional downstream media
        routing. Prompt and Agent keep ImageAsset as their Shot authority.
        """

        lock = getattr(self, "_hmb_shot_snapshot_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._hmb_shot_snapshot_lock = lock
        with lock:
            return self._hmb_standalone_shot_routing_catalog_locked(
                self._picker_state()
            )

    def _hmb_standalone_shot_routing_catalog_locked(
        self,
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        if _uuid_text(state.get("channel_uuid")):
            return {}
        publisher = _uuid_text(getattr(self, "_hmb_picker_publisher_uuid", ""))
        if not publisher:
            publisher = str(uuid.uuid4())
            self._hmb_picker_publisher_uuid = publisher
        shots: List[Dict[str, Any]] = []
        numbers: set[int] = set()
        for row in state.get("picker_shots", []):
            if not isinstance(row, dict):
                continue
            shot_uuid = _uuid_text(row.get("workspace_uuid"))
            try:
                number = int(row.get("number") or 0)
            except (TypeError, ValueError, OverflowError):
                continue
            if (
                not shot_uuid
                or not 1 <= number <= SHOT_ROUTING_MAX_SHOTS
                or number in numbers
            ):
                continue
            name = _clean(row.get("name"))[:128] or f"Shot {number}"
            try:
                revision = max(0, int(row.get("revision") or 0))
            except (TypeError, ValueError, OverflowError):
                revision = 0
            numbers.add(number)
            shots.append({
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
            })
        shots.sort(key=lambda item: (item["number"], item["shot_uuid"]))
        if not shots:
            return {}
        identity = _sha256_canonical({
            "channel_uuid": publisher,
            "shots": shots,
        })
        previous_identity = str(
            getattr(self, "_hmb_standalone_catalog_identity", "") or ""
        )
        generation = max(
            1,
            int(getattr(self, "_hmb_standalone_catalog_generation", 0) or 0),
        )
        if previous_identity and previous_identity != identity:
            generation += 1
        self._hmb_standalone_catalog_identity = identity
        self._hmb_standalone_catalog_generation = generation
        metadata_document = {
            "channel_uuid": publisher,
            "generation": generation,
            "shots": shots,
        }
        return {
            "schema": "hmb-shot-routing-catalog",
            "version": 1,
            "publisher_instance_uuid": publisher,
            "channel_uuid": publisher,
            "generation": generation,
            "metadata_sha256": _sha256_canonical(metadata_document),
            "shots": shots,
        }

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if isinstance(value, dict):
            self._hmb_shot_route_status = copy.deepcopy(value)

    def _hmb_reconcile_shot_routing(
        self,
        routing_snapshot: Any = None,
    ) -> Dict[str, Any]:
        """Atomically accept one ImageAsset catalog and commit its delta."""

        with self._hmb_catalog_state_commit():
            return self._hmb_reconcile_shot_routing_commit(routing_snapshot)

    def _hmb_reconcile_replacement_shot_routing(
        self,
        routing_snapshot: Any = None,
    ) -> Dict[str, Any]:
        """Adopt the sole replacement ImageAsset after its predecessor left.

        The shared router calls this narrow path only when the Picker's saved
        channel has no live ImageAsset owner and the flow contains exactly one
        replacement publisher.  Clearing the stale quartet first prevents an
        old publisher UUID from permanently rejecting the new catalog.
        """

        snapshot = self._validate_image_shot_catalog_snapshot(routing_snapshot)
        with self._hmb_catalog_state_commit():
            current = self._picker_state()
            current_channel = (
                _uuid_text(current.get("channel_uuid"))
                or _uuid_text(
                    current.get("accepted_shot_catalog_channel_uuid")
                )
            )
            current_publisher = _uuid_text(
                current.get("shot_publisher_instance_uuid")
            ) or _uuid_text(
                current.get("accepted_shot_catalog_publisher_instance_uuid")
            )
            replacing = bool(
                current_channel
                and (
                    current_channel != snapshot["channel_uuid"]
                    or (
                        current_publisher
                        and current_publisher
                        != snapshot["publisher_instance_uuid"]
                    )
                )
            )
            if not replacing:
                return self._hmb_reconcile_shot_routing_commit(snapshot)

            # This callback is reached only after the central router proves that
            # the previous publisher is absent and exactly one authoritative
            # replacement exists.  That explicit lifecycle event is the sole
            # place where display order may bridge newly generated Shot UUIDs.
            # Ordinary catalog updates remain UUID-only.
            old_rows = [
                copy.deepcopy(row)
                for row in current.get("picker_shots", [])
                if isinstance(row, dict)
                and _uuid_text(row.get("workspace_uuid"))
                and _uuid_text(row.get("bound_shot_uuid"))
            ]
            old_rows.sort(
                key=lambda row: (
                    int(row.get("number") or 0),
                    _uuid_text(row.get("workspace_uuid")),
                )
            )
            new_shots = sorted(
                (dict(item) for item in snapshot["shots"]),
                key=lambda item: (int(item["number"]), item["shot_uuid"]),
            )
            old_numbers = [int(row.get("number") or 0) for row in old_rows]
            new_numbers = [int(item["number"]) for item in new_shots]
            unambiguous = bool(
                old_rows
                and len(old_rows) == len(new_shots)
                and old_numbers == new_numbers
                and len({_uuid_text(row.get("workspace_uuid")) for row in old_rows})
                == len(old_rows)
                and len({_uuid_text(row.get("bound_shot_uuid")) for row in old_rows})
                == len(old_rows)
            )
            if not unambiguous:
                # Preserve every authored workspace/media record as an orphan;
                # never delete it or guess a different target when the old/new
                # shapes cannot be paired exactly.  Clearing only the remote
                # quartet makes the ambiguity visible and retry-safe.
                self._hmb_clear_shot_routing_catalog_commit(
                    "replacement_shape_ambiguous_media_preserved"
                )
                self._hmb_shot_route_status = {
                    "schema": "hmb-shot-routing-status",
                    "version": 1,
                    "ok": False,
                    "code": "replacement_ambiguous",
                    "details": (
                        "ImageAsset replacement Shot shape differs; Picker media "
                        "was preserved without automatic rebinding."
                    ),
                }
                raise ValueError(
                    "ImageAsset replacement Shot shape is ambiguous; Picker media was preserved."
                )

            active_workspace_uuid = _uuid_text(
                current.get("active_picker_shot_uuid")
            )
            migrated_rows: List[Dict[str, Any]] = []
            shot_selections: List[Dict[str, Any]] = []
            selected_catalog_row: Optional[Dict[str, Any]] = None
            for old_row, new_shot in zip(old_rows, new_shots):
                migrated = copy.deepcopy(old_row)
                migrated["bound_shot_uuid"] = new_shot["shot_uuid"]
                migrated["number"] = new_shot["number"]
                if not bool(migrated.get("custom_name")):
                    migrated["name"] = new_shot["name"]
                migrated_rows.append(migrated)
                shot_selections.append({
                    "shot_uuid": new_shot["shot_uuid"],
                    "number": new_shot["number"],
                    "name": new_shot["name"],
                    "revision": max(0, int(new_shot.get("revision") or 0)),
                    "selected_video_uids": list(
                        migrated.get("selected_video_uids") or []
                    )[:MAX_SELECTED_VIDEOS],
                })
                if _uuid_text(migrated.get("workspace_uuid")) == active_workspace_uuid:
                    selected_catalog_row = new_shot
            if selected_catalog_row is None:
                selected_catalog_row = new_shots[0]
                active_workspace_uuid = _uuid_text(
                    migrated_rows[0].get("workspace_uuid")
                )

            migrated_state = copy.deepcopy(current)
            migrated_state.update({
                "picker_shots": migrated_rows,
                "active_picker_shot_uuid": active_workspace_uuid,
                "shot_publisher_instance_uuid": snapshot[
                    "publisher_instance_uuid"
                ],
                "channel_uuid": snapshot["channel_uuid"],
                "shot_uuid": selected_catalog_row["shot_uuid"],
                "shot_number": selected_catalog_row["number"],
                "shot_name": selected_catalog_row["name"],
                "shot_selections": shot_selections,
                "accepted_shot_catalog_publisher_instance_uuid": snapshot[
                    "publisher_instance_uuid"
                ],
                "accepted_shot_catalog_channel_uuid": snapshot["channel_uuid"],
                "accepted_shot_catalog_generation": snapshot["generation"],
                "accepted_shot_catalog_metadata_sha256": snapshot[
                    "metadata_sha256"
                ],
            })
            normalized = self._apply_selected_view_fields(
                _parse_state(migrated_state)
            )
            self._hmb_shot_catalog_snapshot = copy.deepcopy(snapshot)
            self._hmb_shot_catalog_refresh_count = max(
                0,
                int(getattr(self, "_hmb_shot_catalog_refresh_count", 0) or 0),
            ) + 1
            self._hmb_shot_route_status = {
                "schema": "hmb-shot-routing-status",
                "version": 1,
                "ok": True,
                "code": "ready",
                "details": "ImageAsset replacement adopted; Picker workspaces preserved.",
            }
            if normalized != current:
                self._write_state(normalized)
                self._sync_outputs_from_state(normalized)
            return self._hmb_shot_channel_subscription()

    def _hmb_reconcile_shot_routing_commit(
        self,
        routing_snapshot: Any = None,
    ) -> Dict[str, Any]:
        current = self._picker_state()
        expected_channel = _uuid_text(current.get("channel_uuid"))
        expected_publisher = _uuid_text(
            current.get("shot_publisher_instance_uuid")
        )
        snapshot = self._validate_image_shot_catalog_snapshot(
            routing_snapshot,
            expected_channel_uuid=expected_channel,
        )
        if (
            expected_publisher
            and snapshot["publisher_instance_uuid"] != expected_publisher
        ):
            raise ValueError("ImageAsset Shot catalog publisher does not match.")
        watermark_scope_matches = bool(
            _uuid_text(
                current.get("accepted_shot_catalog_publisher_instance_uuid")
            ) == snapshot["publisher_instance_uuid"]
            and _uuid_text(current.get("accepted_shot_catalog_channel_uuid"))
            == snapshot["channel_uuid"]
        )
        if watermark_scope_matches:
            accepted_generation = int(
                current.get("accepted_shot_catalog_generation") or 0
            )
            accepted_hash = _clean(
                current.get("accepted_shot_catalog_metadata_sha256")
            ).casefold()
            if snapshot["generation"] < accepted_generation:
                raise ValueError(
                    "ImageAsset Shot catalog generation moved backwards."
                )
            if (
                snapshot["generation"] == accepted_generation
                and accepted_hash
                and snapshot["metadata_sha256"] != accepted_hash
            ):
                raise ValueError(
                    "ImageAsset Shot catalog changed without a generation revision."
                )
        previous = getattr(self, "_hmb_shot_catalog_snapshot", None)
        if (
            isinstance(previous, dict)
            and previous.get("publisher_instance_uuid")
            == snapshot["publisher_instance_uuid"]
            and previous.get("channel_uuid") == snapshot["channel_uuid"]
        ):
            previous_generation = int(previous.get("generation") or 0)
            if snapshot["generation"] < previous_generation:
                raise ValueError("ImageAsset Shot catalog generation moved backwards.")
            if snapshot["generation"] == previous_generation and (
                snapshot["metadata_sha256"] != previous.get("metadata_sha256")
            ):
                raise ValueError("ImageAsset Shot catalog changed without a generation revision.")

        rows_by_uuid = {
            _uuid_text(row.get("shot_uuid")): dict(row)
            for row in current.get("shot_selections", [])
            if isinstance(row, dict) and _uuid_text(row.get("shot_uuid"))
        }
        workspaces_by_bound_uuid = {
            _uuid_text(row.get("bound_shot_uuid")): dict(row)
            for row in current.get("picker_shots", [])
            if isinstance(row, dict)
            and _uuid_text(row.get("bound_shot_uuid"))
        }
        workspaces_by_uuid = {
            _uuid_text(row.get("workspace_uuid")): dict(row)
            for row in current.get("picker_shots", [])
            if isinstance(row, dict)
            and _uuid_text(row.get("workspace_uuid"))
        }
        selected_shot_uuid = _uuid_text(current.get("shot_uuid"))
        catalog_ids = {item["shot_uuid"] for item in snapshot["shots"]}
        selected_shot_deleted = bool(
            selected_shot_uuid and selected_shot_uuid not in catalog_ids
        )
        requested_active_workspace_uuid = _uuid_text(
            current.get("active_picker_shot_uuid")
        )
        requested_active_workspace = workspaces_by_uuid.get(
            requested_active_workspace_uuid
        )
        requested_active_bound_uuid = _uuid_text(
            requested_active_workspace.get("bound_shot_uuid")
            if isinstance(requested_active_workspace, dict)
            else ""
        )
        active_workspace_deleted = bool(
            requested_active_bound_uuid
            and requested_active_bound_uuid not in catalog_ids
        )
        active_workspace_missing = bool(
            requested_active_workspace_uuid
            and requested_active_workspace is None
        )
        previous_workspace_order = [
            row
            for row in sorted(
                workspaces_by_uuid.values(),
                key=lambda item: (
                    max(1, int(item.get("number") or 1)),
                    _uuid_text(item.get("workspace_uuid")),
                ),
            )
            if _uuid_text(row.get("bound_shot_uuid"))
        ]
        removed_workspace_index = next(
            (
                index
                for index, row in enumerate(previous_workspace_order)
                if _uuid_text(row.get("bound_shot_uuid"))
                == requested_active_bound_uuid
            ),
            -1,
        )
        durable_active_workspace: Optional[Dict[str, Any]] = (
            requested_active_workspace
            if isinstance(requested_active_workspace, dict)
            and not active_workspace_deleted
            else None
        )
        if selected_shot_deleted:
            # A validated newer ImageAsset catalog is authoritative deletion.
            # Normalization below removes that bound workspace and its owned
            # media, then applies ImageAsset's positional survivor fallback.
            selected_shot_uuid = ""

        if (
            selected_shot_deleted
            or active_workspace_deleted
            or active_workspace_missing
        ):
            # The legacy top-level controls still project the removed active
            # workspace. Restore the same surviving row that normalization
            # will choose before parsing, otherwise its Maya camera/FPS/frame
            # metadata and slot state are overwritten by the deleted Shot.
            if durable_active_workspace is None:
                fallback_index = (
                    min(removed_workspace_index, len(snapshot["shots"]) - 1)
                    if removed_workspace_index >= 0
                    else 0
                )
                first_shot = snapshot["shots"][fallback_index]
                durable_active_workspace = workspaces_by_bound_uuid.get(
                    first_shot["shot_uuid"]
                )
                if durable_active_workspace is None:
                    durable_active_workspace = _new_picker_workspace_row(
                        first_shot["number"],
                        bound_shot_uuid=first_shot["shot_uuid"],
                        state={},
                        workspace_uuid=(
                            _picker_workspace_uuid_for_bound_shot(
                                first_shot["shot_uuid"]
                            )
                        ),
                    )
            _restore_picker_workspace_projection(
                current,
                durable_active_workspace,
            )

        normalized_rows: List[Dict[str, Any]] = []
        for catalog_shot in snapshot["shots"]:
            row = rows_by_uuid.get(catalog_shot["shot_uuid"], {})
            workspace = workspaces_by_bound_uuid.get(
                catalog_shot["shot_uuid"], {}
            )
            membership = list(
                workspace.get("selected_video_uids")
                or row.get("selected_video_uids")
                or []
            )
            normalized_rows.append({
                "shot_uuid": catalog_shot["shot_uuid"],
                "number": catalog_shot["number"],
                "name": catalog_shot["name"],
                "revision": max(0, int(catalog_shot.get("revision") or 0)),
                "selected_video_uids": membership[:MAX_SELECTED_VIDEOS],
            })
        selected_row = next(
            (item for item in normalized_rows if item["shot_uuid"] == selected_shot_uuid),
            None,
        )
        current.update({
            "shot_publisher_instance_uuid": snapshot["publisher_instance_uuid"],
            "channel_uuid": snapshot["channel_uuid"],
            "shot_uuid": selected_row["shot_uuid"] if selected_row else "",
            "shot_number": selected_row["number"] if selected_row else 0,
            "shot_name": selected_row["name"] if selected_row else "",
            "shot_selections": normalized_rows,
            "accepted_shot_catalog_publisher_instance_uuid": snapshot[
                "publisher_instance_uuid"
            ],
            "accepted_shot_catalog_channel_uuid": snapshot["channel_uuid"],
            "accepted_shot_catalog_generation": snapshot["generation"],
            "accepted_shot_catalog_metadata_sha256": snapshot[
                "metadata_sha256"
            ],
        })
        normalized = self._apply_selected_view_fields(_parse_state(current))
        if durable_active_workspace is not None:
            # Keep the existing selected-video viewport projection, but restore
            # the survivor's independent Maya authoring state before it is
            # serialized. Without this second projection, selected-video
            # metadata is persisted back over that workspace's camera/FPS/
            # frame/Mask state on the next parse after any catalog mutation.
            _restore_picker_workspace_projection(
                normalized,
                durable_active_workspace,
            )
            normalized = _parse_state(normalized)
        self._hmb_shot_catalog_snapshot = copy.deepcopy(snapshot)
        self._hmb_shot_catalog_refresh_count = max(
            0,
            int(getattr(self, "_hmb_shot_catalog_refresh_count", 0) or 0),
        ) + 1
        self._hmb_shot_route_status = {
            "schema": "hmb-shot-routing-status",
            "version": 1,
            "ok": True,
            "code": "ready",
            "details": "",
        }
        if normalized != self._picker_state():
            self._write_state(normalized)
            self._sync_outputs_from_state(normalized)
        return self._hmb_shot_channel_subscription()

    def _hmb_clear_shot_routing_catalog(
        self,
        reason: str = "publisher_unavailable",
    ) -> Dict[str, Any]:
        with self._hmb_catalog_state_commit():
            return self._hmb_clear_shot_routing_catalog_commit(reason)

    def _hmb_clear_shot_routing_catalog_commit(
        self,
        reason: str = "publisher_unavailable",
    ) -> Dict[str, Any]:
        """Return to independent Only mode without clearing authored media."""

        current = self._picker_state()
        cleared = dict(current)
        cleared.update({
            "shot_publisher_instance_uuid": "",
            "channel_uuid": "",
            "shot_uuid": "",
            "shot_number": 0,
            "shot_name": "",
            "shot_selections": [],
        })
        normalized = self._apply_selected_view_fields(_parse_state(cleared))
        self._hmb_shot_catalog_snapshot = None
        self._hmb_shot_catalog_refresh_count = 0
        self._hmb_shot_route_status = {
            "schema": "hmb-shot-routing-status",
            "version": 1,
            "ok": True,
            "code": "only",
            "details": _clean(reason)[:128],
        }
        if normalized != current:
            self._write_state(normalized)
            self._sync_outputs_from_state(normalized)
        return self._hmb_shot_channel_subscription()

    def _reconcile_shared_shot_routing(self) -> Dict[str, Any]:
        if self._hmb_shared_routing_in_progress:
            return {"ok": True, "code": "reentrant", "changed": 0}
        initially_enabled = bool(self._hmb_shot_channel_subscription()["enabled"])
        self._hmb_shared_routing_in_progress = True
        try:
            result = _shot_routing.reconcile_shot_routing(self)
            if not initially_enabled and self._hmb_shot_channel_subscription()["enabled"]:
                result = _shot_routing.reconcile_shot_routing(self)
            # An unchanged valid catalog does not invoke the recipient callback
            # on every retained-mode pass. Treating that normal cache hit as a
            # missing publisher changed a ready Picker into a false failure and
            # made Prompt/Agent video snapshots stop at the next stage. The
            # central router already owns every real invalidation: it clears an
            # orphaned catalog, rejects stale/conflicting generations, and
            # publishes a precise failure status. Preserve the last accepted
            # ready status when this pass simply has nothing new to commit.
            return result
        finally:
            self._hmb_shared_routing_in_progress = False

    def _hmb_post_registration_shot_discovery(self) -> None:
        """Adopt the live ImageAsset catalog when this Picker is newly added."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        self._reconcile_shared_shot_routing()

    @staticmethod
    def _shot_video_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
        compact = _compact_video_payload_for_state(item)
        metadata: Dict[str, Any] = {}
        for field in _SHOT_VIDEO_METADATA_FIELDS:
            if field not in compact:
                continue
            semantic = _semantic_shot_video_metadata_value(
                compact.get(field),
                field,
            )
            if semantic is not _SHOT_VIDEO_METADATA_OMIT:
                metadata[field] = semantic
        source_uid = _clean(item.get("video_uid") or item.get("source_uid"))
        metadata["source_uid"] = source_uid
        metadata["video_uid"] = source_uid
        return metadata

    def _hmb_allocate_shot_snapshot_generation(self, identity: str) -> int:
        """Return one monotonic generation for a serialized snapshot identity."""

        lock = getattr(self, "_hmb_shot_snapshot_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._hmb_shot_snapshot_lock = lock
        with lock:
            previous_identity = getattr(
                self,
                "_hmb_shot_snapshot_identity",
                "",
            )
            generation = max(
                1,
                int(
                    getattr(
                        self,
                        "_hmb_shot_snapshot_generation",
                        0,
                    )
                    or 0
                ),
            )
            if identity != previous_identity:
                generation += int(bool(previous_identity))
            self._hmb_shot_snapshot_identity = identity
            self._hmb_shot_snapshot_generation = generation
            return generation

    def _hmb_shot_routing_snapshot(
        self,
        expected_channel_uuid: str = "",
        *,
        state_snapshot: Optional[Dict[str, Any]] = None,
        probe_cache: Optional[Dict[str, Optional[Path]]] = None,
    ) -> Dict[str, Any]:
        lock = getattr(self, "_hmb_shot_snapshot_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._hmb_shot_snapshot_lock = lock
        if not isinstance(probe_cache, dict):
            probe_cache = getattr(
                _state_sync_local(self),
                "media_probe_cache",
                None,
            )
            if not isinstance(probe_cache, dict):
                probe_cache = {}
        with lock:
            return self._hmb_shot_routing_snapshot_locked(
                expected_channel_uuid,
                state_snapshot=state_snapshot,
                probe_cache=probe_cache,
            )

    def _hmb_shot_routing_snapshot_locked(
        self,
        expected_channel_uuid: str = "",
        *,
        state_snapshot: Optional[Dict[str, Any]] = None,
        probe_cache: Optional[Dict[str, Optional[Path]]] = None,
    ) -> Dict[str, Any]:
        # Output publication supplies its exact immutable state revision here.
        # Falling back to ``_picker_state`` remains the public read contract,
        # while the explicit snapshot prevents PICKER_OUT/VIDEO_OUT from being
        # built from one revision and SHOT_PICKER_OUT from a newer callback.
        state = (
            _parse_state(state_snapshot)
            if isinstance(state_snapshot, dict)
            else self._picker_state()
        )
        channel = _uuid_text(state.get("channel_uuid"))
        standalone = not bool(channel)
        if standalone:
            catalog = self._hmb_standalone_shot_routing_catalog_locked(state)
            channel = _uuid_text(catalog.get("channel_uuid"))
        else:
            catalog = getattr(self, "_hmb_shot_catalog_snapshot", None)
        expected = _uuid_text(expected_channel_uuid)
        if not channel or (expected and expected != channel):
            raise ValueError("VideoPicker Shot channel is unavailable or does not match.")
        accepted_publisher = _uuid_text(
            state.get("shot_publisher_instance_uuid")
        )
        if not standalone and (
            not isinstance(catalog, dict)
            or catalog.get("channel_uuid") != channel
            or not accepted_publisher
            or catalog.get("publisher_instance_uuid") != accepted_publisher
        ):
            raise ValueError("VideoPicker has no validated ImageAsset Shot catalog.")
        status = getattr(self, "_hmb_shot_route_status", {})
        if (
            not standalone
            and isinstance(status, dict)
            and status
            and not bool(status.get("ok", True))
        ):
            raise ValueError("VideoPicker automatic Shot route is incomplete.")

        source_items: Dict[str, Dict[str, Any]] = {}
        source_media_by_uid: Dict[str, str] = {}
        for raw in state.get("videos", []):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            uid = _clean(item.get("video_uid") or item.get("source_uid"))
            media = _select_synchronized_video_media(
                item,
                enforce_media_availability=True,
                probe_cache=probe_cache,
            )
            if not uid or not media or uid in source_items:
                continue
            source_items[uid] = item
            source_media_by_uid[uid] = media
        local_rows_by_bound: Dict[str, Dict[str, Any]] = {}
        for row in state.get("picker_shots", []):
            if not isinstance(row, dict):
                continue
            bound_shot_uuid = _uuid_text(
                row.get("workspace_uuid")
                if standalone
                else row.get("bound_shot_uuid")
            )
            if not bound_shot_uuid:
                continue
            if bound_shot_uuid in local_rows_by_bound:
                raise ValueError("Duplicate local VideoPicker Shot binding is invalid.")
            local_rows_by_bound[bound_shot_uuid] = row
        legacy_membership_fallbacks = (
            state.get("picker_legacy_membership_fallbacks")
            if isinstance(state.get("picker_legacy_membership_fallbacks"), dict)
            else {}
        )
        shots: List[Dict[str, Any]] = []
        for catalog_shot in catalog["shots"]:
            # A bound local workspace is exact authority.  The dedicated
            # one-way overflow map is only a lossless migration fallback for
            # an unbound remote row (Only + five historical remote buckets do
            # not fit into the strict five-local-workspace cap).
            row = local_rows_by_bound.get(catalog_shot["shot_uuid"])
            if row is None:
                row = legacy_membership_fallbacks.get(catalog_shot["shot_uuid"])
            # Preserve the exact durable intent before consulting media
            # availability. Filtering through ``source_items`` first turns a
            # deleted/moved selected file into an indistinguishable empty Shot.
            selected_uids = _picker_representative_video_uids(
                row.get("selected_video_uids", []) if isinstance(row, dict) else [],
                row.get("preview_video_uid", "") if isinstance(row, dict) else "",
            )
            unavailable_uids = [
                uid for uid in selected_uids if uid not in source_items
            ]
            if unavailable_uids:
                raise ValueError(
                    "A selected Shot video is unavailable: "
                    + ", ".join(unavailable_uids)
                )
            selected_order = {uid: index for index, uid in enumerate(selected_uids, start=1)}
            shot_state = dict(state)
            shot_state["shot_uuid"] = catalog_shot["shot_uuid"]
            shot_state["shot_number"] = catalog_shot["number"]
            shot_state["shot_name"] = catalog_shot["name"]
            if isinstance(row, dict) and _uuid_text(row.get("workspace_uuid")):
                # Output normalization is intentionally active-Shot-local.
                # Project the bound local owner before building this remote
                # Shot snapshot instead of relying on transient global flags.
                shot_state["active_picker_shot_uuid"] = _uuid_text(
                    row.get("workspace_uuid")
                )
            shot_state["videos"] = []
            for raw in state.get("videos", []):
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                uid = _clean(item.get("video_uid") or item.get("source_uid"))
                order = selected_order.get(uid, 0)
                item["selected"] = bool(order)
                item["selection_order"] = order
                item["video_slot"] = order
                shot_state["videos"].append(item)
            picker_payload, shot_media = _build_synchronized_video_outputs(
                shot_state,
                enforce_media_availability=True,
                probe_cache=probe_cache,
            )
            if shot_media != [source_media_by_uid[uid] for uid in selected_uids]:
                raise ValueError("VideoPicker Shot media order changed during snapshot.")
            shots.append({
                "shot_uuid": catalog_shot["shot_uuid"],
                "number": catalog_shot["number"],
                "name": catalog_shot["name"],
                "revision": max(0, int(row.get("revision") or 0)) if row else 0,
                "selected_source_uids": selected_uids,
                "picker_payload": picker_payload,
            })
        # The routing snapshot is a generation dependency, not the Picker's
        # reusable catalog. Publish only representatives referenced by Shots;
        # unselected history remains local and cannot inflate remote payloads.
        ordered_source_uids: List[str] = []
        for shot in shots:
            for uid in shot.get("selected_source_uids", []):
                if uid and uid not in ordered_source_uids:
                    ordered_source_uids.append(uid)
        ordered_videos = [
            {"source_uid": uid, "metadata": self._shot_video_metadata(source_items[uid])}
            for uid in ordered_source_uids
        ]
        media_by_source_uid = {
            uid: source_media_by_uid[uid]
            for uid in ordered_source_uids
        }
        semantic_identity = {
            "channel_uuid": channel,
            "shots": shots,
            "ordered_videos": ordered_videos,
        }
        media_descriptors = [
            {
                "source_uid": item["source_uid"],
                "media_value_sha256": hashlib.sha256(
                    media_by_source_uid[item["source_uid"]].encode("utf-8")
                ).hexdigest(),
            }
            for item in ordered_videos
        ]
        identity = _sha256_canonical({
            "semantic": semantic_identity,
            "media_descriptors": media_descriptors,
        })
        generation = self._hmb_allocate_shot_snapshot_generation(identity)
        metadata_document = {
            "channel_uuid": channel,
            "generation": generation,
            "shots": shots,
            "ordered_videos": ordered_videos,
        }
        return {
            "schema": SHOT_ROUTING_SNAPSHOT_SCHEMA,
            "version": SHOT_ROUTING_SNAPSHOT_VERSION,
            "publisher_instance_uuid": self._hmb_picker_publisher_uuid,
            "channel_uuid": channel,
            "generation": generation,
            "metadata_sha256": _sha256_canonical(metadata_document),
            "media_sha256": _sha256_canonical({"media_descriptors": media_descriptors}),
            "shots": shots,
            "ordered_videos": ordered_videos,
            "media_by_source_uid": media_by_source_uid,
        }

    def _shot_picker_dependency_envelope(
        self,
        *,
        state_snapshot: Optional[Dict[str, Any]] = None,
        probe_cache: Optional[Dict[str, Optional[Path]]] = None,
    ) -> Dict[str, Any]:
        try:
            snapshot = self._hmb_shot_routing_snapshot(
                state_snapshot=state_snapshot,
                probe_cache=probe_cache,
            )
        except Exception:
            state = (
                _parse_state(state_snapshot)
                if isinstance(state_snapshot, dict)
                else self._picker_state()
            )
            return {
                "schema": "hmb-picker-shot-routing-catalog",
                "version": 1,
                "channel_uuid": _uuid_text(state.get("channel_uuid")),
                "generation": 0,
                "metadata_sha256": "",
                "media_sha256": "",
                "shot_count": len(state.get("shot_selections", [])),
            }
        return {
            "schema": "hmb-picker-shot-routing-catalog",
            "version": 1,
            "channel_uuid": snapshot["channel_uuid"],
            "generation": snapshot["generation"],
            "metadata_sha256": snapshot["metadata_sha256"],
            "media_sha256": snapshot["media_sha256"],
            "shot_count": len(snapshot["shots"]),
        }

    def _sync_outputs_from_state(
        self,
        state: Dict[str, Any],
        *,
        enforce_media_availability: bool = True,
        propagate_connections: bool | None = None,
    ) -> str:
        if getattr(self, "_hmb_node_deleted", False):
            return ""
        # Serialize sibling output staging/notification. Lifecycle invalidation
        # never waits for this lock; generation checks make deletion win.
        with self._hmb_state_write_lock:
            if getattr(self, "_hmb_node_deleted", False):
                return ""
            owner_generation = int(
                getattr(self, "_hmb_lifecycle_generation", 0) or 0
            )

            def still_owned() -> bool:
                return (
                    not bool(getattr(self, "_hmb_node_deleted", False))
                    and owner_generation
                    == int(
                        getattr(self, "_hmb_lifecycle_generation", 0) or 0
                    )
                )

            probe_cache: Dict[str, Optional[Path]] = {}
            sync_local = _state_sync_local(self)
            previous_probe_cache = getattr(sync_local, "media_probe_cache", None)
            sync_local.media_probe_cache = probe_cache
            try:
                payload, media_values = _build_synchronized_video_outputs(
                    state,
                    enforce_media_availability=enforce_media_availability,
                    probe_cache=probe_cache,
                )
                # Resolve the hidden Shot dependency from the same state object
                # and the same local-file probe cache as both public outputs.
                # This is one publication revision even if a widget or routing
                # callback commits a newer state immediately afterward.
                shot_envelope = self._shot_picker_dependency_envelope(
                    state_snapshot=state,
                    probe_cache=probe_cache,
                )
            finally:
                if previous_probe_cache is None:
                    try:
                        delattr(sync_local, "media_probe_cache")
                    except AttributeError:
                        pass
                else:
                    sync_local.media_probe_cache = previous_probe_cache
            if not still_owned():
                return ""
            text = _json_text(payload)
            public_fingerprint = _sha256_canonical({
                "picker": payload,
                "videos": media_values,
            })
            synchronized_outputs: tuple[tuple[str, Any], ...] = ()
            public_changed = public_fingerprint != getattr(self, "_hmb_last_public_output_fingerprint", "")
            if public_changed:
                synchronized_outputs = (
                    (VIDEO_OUTPUT_PARAMETER, media_values),
                    ("PICKER_OUT", text),
                )
            if not still_owned():
                return ""
            shot_fingerprint = _sha256_canonical(shot_envelope)
            shot_changed = shot_fingerprint != getattr(self, "_hmb_last_shot_output_fingerprint", "")
            if shot_changed:
                synchronized_outputs += ((SHOT_PICKER_OUTPUT_PARAMETER, shot_envelope),)
            # A synchronous connection callback may read either sibling output.
            # Stage both caches first so every observer sees one coherent snapshot,
            # then notify each port independently because the host has no atomic
            # multi-parameter publication API.
            for name, value in synchronized_outputs:
                if not still_owned():
                    return ""
                set_output(self, name, value)
            notification_errors: List[tuple[str, Exception]] = []
            for name, value in synchronized_outputs:
                if not still_owned():
                    return ""
                try:
                    _notify_parameter_update(self, name, value)
                except Exception as error:
                    notification_errors.append((name, error))
            should_propagate_connections = (
                not _is_output_side_effect_callback(self)
                if propagate_connections is None
                else bool(propagate_connections)
            )
            if should_propagate_connections:
                for name, value in synchronized_outputs:
                    if not still_owned():
                        return ""
                    try:
                        _propagate_parameter_update_to_connections(
                            self,
                            name,
                            value,
                        )
                    except Exception as error:
                        notification_errors.append((f"{name} graph", error))
            if not still_owned():
                return ""
            _retire_legacy_video_slot_outputs(self)
            _reorder_video_picker_parameters(self)
            if notification_errors:
                failed_ports = ", ".join(
                    f"{name} ({type(error).__name__})"
                    for name, error in notification_errors
                )
                raise RuntimeError(
                    "Synchronized picker output notification failed after both "
                    f"output caches were staged: {failed_ports}."
                ) from notification_errors[0][1]
            if public_changed:
                self._hmb_last_public_output_fingerprint = public_fingerprint
            if shot_changed:
                self._hmb_last_shot_output_fingerprint = shot_fingerprint
            if payload.get("media_blocked"):
                raise RuntimeError(
                    _clean(payload.get("blocking_error"))
                    or "Selected reference video is unavailable."
                )
            return text

    @staticmethod
    def _operation_elapsed_seconds(state: Dict[str, Any]) -> float:
        try:
            started = int(state.get("operation_started_at_ms") or 0)
        except Exception:
            started = 0
        if started <= 0:
            return 0.0
        return max(0.0, (time.time() * 1000.0 - started) / 1000.0)

    def _mark_operation_started(self, state: Dict[str, Any], kind: str) -> Dict[str, Any]:
        state["operation_kind"] = _clean(kind)
        state["operation_video_slot"] = max(
            0,
            min(MAX_VIDEO_SLOTS, int(state.get("selected_video_slot") or 0)),
        )
        state["operation_started_at_ms"] = int(time.time() * 1000)
        state["operation_finished_at_ms"] = 0
        state["last_operation_seconds"] = 0.0
        state["operation_invalidated"] = False
        state["operation_invalidation_reason"] = ""
        return state

    def _mark_operation_finished(self, state: Dict[str, Any]) -> Dict[str, Any]:
        elapsed = self._operation_elapsed_seconds(state)
        state["operation_finished_at_ms"] = int(time.time() * 1000)
        state["last_operation_seconds"] = round(elapsed, 3)
        state["operation_kind"] = ""
        state["operation_video_slot"] = 0
        state["operation_id"] = ""
        state["operation_input_digest"] = ""
        state["operation_scene_fingerprint"] = ""
        return state

    def _current_scene_text(self, fallback: Any = "") -> str:
        return next(
            (
                candidate
                for candidate in (
                    _maya_scene_path_text(
                        _raw_parameter_value(self, "MAYA_SCENE")
                    ),
                    _maya_scene_path_text(fallback),
                    _maya_scene_path_text(
                        self._picker_state().get("scene_request_path")
                    ),
                    _maya_scene_path_text(
                        self._picker_state().get("scene_path")
                    ),
                )
                if candidate
            ),
            "",
        )

    def _create_operation_context(
        self,
        kind: str,
        scene_text: Any,
        state: Dict[str, Any],
        video_slot: Optional[int] = None,
    ) -> _OperationContext:
        strict_scene_text = _maya_scene_path_text(scene_text)
        if not strict_scene_text:
            raise ValueError("A single absolute Maya .mb or .ma scene is required.")
        normalized_scene = str(_norm_path(strict_scene_text)).replace("\\", "/")
        kind_text = _clean(kind)
        slot = max(
            1,
            min(
                int(state.get("active_slot_count") or 1),
                int(video_slot or state.get("selected_video_slot") or 1),
            ),
        )
        depth_video_slot = 0
        motion_guide_video_slot = 0
        selected_roles: tuple[str, ...] = ()
        snapshot_video_uid = ""
        mask_authoring_slot = _mask_authoring_slot(state)
        picker_shot_uuid = _uuid_text(state.get("active_picker_shot_uuid"))
        if kind_text == "run_video":
            selected_roles = tuple(_generation_choice_roles(state))
            if not selected_roles:
                raise ValueError(
                    "Generate Playblast requires at least one checked output: "
                    "Original, Mask, Depth, or Motion Guide."
                )
            _normalized_capacity_state, picker_shot_uuid = (
                _assert_picker_workspace_capacity(
                    state,
                    picker_shot_uuid,
                    len(selected_roles),
                )
            )
            slot = PRIMARY_COLOR_VIDEO_SLOT
            depth_enabled = bool(state.get("depth_enabled"))
            motion_guide_enabled = bool(state.get("motion_guide_enabled"))
            if depth_enabled or motion_guide_enabled:
                (
                    depth_video_slot,
                    motion_guide_video_slot,
                ) = _resolve_generated_companion_slots(
                    state,
                    depth_enabled=depth_enabled,
                    motion_guide_enabled=motion_guide_enabled,
                )
        elif kind_text == "render_snapshot":
            # Snapshot authoring always uses the one Maya Color staging slot.
            # ``snapshot_video_uid`` freezes the catalog identity separately;
            # later card reorder cannot change what the image belongs to.
            slot = PRIMARY_COLOR_VIDEO_SLOT
            snapshot_video_uid = _clean(
                state.get("snapshot_request_video_uid")
                or state.get("preview_video_uid")
                or state.get("selected_video_uid")
            )
        return _OperationContext(
            operation_id=f"{_clean(kind)}-{uuid.uuid4().hex}",
            kind=kind_text,
            scene_path=normalized_scene,
            scene_fingerprint=_scene_fingerprint(normalized_scene),
            input_digest=_operation_input_digest(kind, normalized_scene, state, slot),
            video_slot=slot,
            snapshot_video_uid=snapshot_video_uid,
            mask_authoring_slot=mask_authoring_slot,
            depth_video_slot=depth_video_slot,
            motion_guide_video_slot=motion_guide_video_slot,
            selected_roles=selected_roles,
            picker_shot_uuid=picker_shot_uuid,
            accepted_state_revision=int(state.get("state_revision") or 0),
        )

    def _operation_is_current(self, context: Optional[_OperationContext]) -> bool:
        if context is None:
            return True
        active = self._hmb_active_operation
        if active is None or active.operation_id != context.operation_id:
            return False
        if self._hmb_cancel_requested.is_set():
            return False
        current_scene = self._current_scene_text(context.scene_path)
        if _scene_fingerprint(current_scene) != context.scene_fingerprint:
            return False
        current_state = self._picker_state()
        if bool(current_state.get("operation_invalidated")):
            return False
        return _operation_input_digest(context.kind, current_scene, current_state, context.video_slot) == context.input_digest

    def _assert_operation_current(self, context: Optional[_OperationContext], stage: str) -> None:
        if not self._operation_is_current(context):
            raise _StaleOperationError(
                f"Discarded stale {context.kind if context else 'picker'} result at {stage}; "
                "the scene, camera, slot, frame, or Color Pick assignment changed while it was running."
            )

    def _invalidate_active_operation(self, reason: str, terminate: bool = True) -> None:
        context = self._hmb_active_operation
        if context is None:
            return
        self._hmb_cancel_requested.set()
        state = self._picker_state()
        state["operation_invalidated"] = True
        state["operation_invalidation_reason"] = _clean(reason)
        state["status"] = "CANCELLING"
        state["scene_stage"] = "STALE_RESULT_DISCARD"
        state["message"] = _clean(reason) or "Active result invalidated."
        _append_activity_log(state, "WARNING", state["message"])
        self._write_state(state)
        if terminate:
            active_process = self._hmb_active_process
            if active_process is not None and active_process.poll() is None:
                _terminate_process(active_process)

    def _set_cancelled_state(self) -> None:
        state = self._picker_state()
        operation_kind = _clean(state.get("operation_kind"))
        korean = _clean(state.get("language")).lower() == "ko"
        state = self._mark_operation_finished(state)
        if operation_kind == "render_original_preview":
            ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
            state.update({
                "status": ready_stage,
                "scene_stage": ready_stage,
                "scene_request_status": "COMPLETE",
                "message": "Original preview generation was stopped. The completed READ metadata and existing outputs were preserved.",
                "original_preview_enabled": False,
                "pending_action": "",
                "pending_action_id": "",
                "active_process_pid": 0,
                "active_process_kind": "",
            })
            state = self._apply_selected_view_fields(state)
            _append_activity_log(
                state,
                "WARNING",
                f"Original preview generation stopped after {state.get('last_operation_seconds', 0.0):.1f} seconds; existing outputs were preserved.",
            )
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return
        if operation_kind in {"run_video", "render_snapshot"} and bool(
            state.get("native_read_ready")
        ):
            ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
            state.update({
                "status": ready_stage,
                "scene_stage": ready_stage,
                "scene_request_status": "COMPLETE",
                "message": (
                    "The current generation was stopped. Completed READ metadata, "
                    "Color Pick assignments, and existing outputs were preserved."
                ),
                "pending_action": "",
                "pending_action_id": "",
                "active_process_pid": 0,
                "active_process_kind": "",
            })
            _append_activity_log(
                state,
                "WARNING",
                f"Generation stopped after {state.get('last_operation_seconds', 0.0):.1f} seconds; authoring state remains ready for retry.",
            )
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return
        if operation_kind == "read_scene":
            message = "사용자가 읽기 작업을 정지했습니다." if korean else "READ stopped by the user."
            log_message = (
                f"정지 완료. 읽기 작업이 {state.get('last_operation_seconds', 0.0):.1f}초 후 중지되었습니다."
                if korean
                else f"STOP completed. READ was stopped after {state.get('last_operation_seconds', 0.0):.1f} seconds."
            )
        else:
            message = "사용자가 현재 Maya/FFmpeg 작업을 정지했습니다." if korean else "The current Maya/FFmpeg operation was stopped by the user."
            log_message = (
                f"정지 완료. {state.get('last_operation_seconds', 0.0):.1f}초가 소요되었습니다."
                if korean
                else f"STOP completed after {state.get('last_operation_seconds', 0.0):.1f} seconds."
            )
        state.update({
            "status": "CANCELLED",
            "scene_stage": "CANCELLED",
            "message": message,
            "warnings": [],
            "pending_action": "",
            "pending_action_id": "",
            "active_process_pid": 0,
            "active_process_kind": "",
        })
        _append_activity_log(state, "WARNING", log_message)
        self._write_state(state)
        self._sync_outputs_from_state(state)

    def _set_stale_discarded_state(self, context: _OperationContext, reason: str) -> None:
        active = self._hmb_active_operation
        if active is None or active.operation_id != context.operation_id:
            return
        state = self._picker_state()
        state = self._mark_operation_finished(state)
        if context.kind == "render_original_preview":
            ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
            state.update({
                "status": ready_stage,
                "scene_stage": ready_stage,
                "scene_request_status": "COMPLETE",
                "message": _clean(reason) or "The original preview result was discarded because its inputs changed.",
                "original_preview_enabled": False,
                "operation_invalidated": False,
                "operation_invalidation_reason": "",
                "pending_action": "",
                "pending_action_id": "",
                "active_process_pid": 0,
                "active_process_kind": "",
            })
            state = self._apply_selected_view_fields(state)
            _append_activity_log(
                state,
                "WARNING",
                "Stale original preview result discarded; completed READ metadata, bindings, videos, and successful artifacts were preserved.",
            )
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return
        if context.kind in {"run_video", "render_snapshot"} and bool(
            state.get("native_read_ready")
        ):
            ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
            state.update({
                "status": ready_stage,
                "scene_stage": ready_stage,
                "scene_request_status": "COMPLETE",
                "message": (
                    _clean(reason)
                    or "The stale generation result was discarded; authoring state remains ready for retry."
                ),
                "operation_invalidated": False,
                "operation_invalidation_reason": "",
                "pending_action": "",
                "pending_action_id": "",
                "active_process_pid": 0,
                "active_process_kind": "",
            })
            _append_activity_log(
                state,
                "WARNING",
                "Stale generation result discarded; existing Color Pick assignments and outputs remain ready for retry.",
            )
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return
        state.update({
            "status": "CANCELLED",
            "scene_stage": "STALE_RESULT_DISCARDED",
            "message": _clean(reason) or "The completed result was discarded because its inputs changed.",
            "operation_invalidated": False,
            "operation_invalidation_reason": "",
            "pending_action": "",
            "pending_action_id": "",
        })
        _append_activity_log(
            state,
            "WARNING",
            f"Stale result discarded for {context.operation_id}. Existing successful VIDEO output and PICKER_OUT were preserved.",
        )
        self._write_state(state)
        self._sync_outputs_from_state(state)

    def _commit_generate_terminal_state(
        self,
        terminal_state: Dict[str, Any],
        context: _OperationContext,
        generation_records: Sequence[Dict[str, Any]],
        provisional_video_uids: Sequence[Any],
    ) -> Dict[str, Any]:
        """Rebase one completed Generate delta onto the newest catalog."""

        with self._hmb_catalog_state_commit():
            latest = self._picker_state()
            if (
                self._hmb_active_operation is not context
                or _clean(latest.get("operation_id")) != context.operation_id
                or bool(latest.get("operation_invalidated"))
                or self._hmb_cancel_requested.is_set()
            ):
                raise _StaleOperationError(
                    "Generate terminal ownership changed before publication."
                )

            latest_rows = {
                _uuid_text(row.get("workspace_uuid")): dict(row)
                for row in latest.get("picker_shots", [])
                if isinstance(row, dict)
                and _uuid_text(row.get("workspace_uuid"))
            }
            latest_videos = [
                dict(item)
                for item in latest.get("videos", [])
                if isinstance(item, dict)
            ]
            provisional_role_by_uid = {
                _clean(item.get("video_uid") or item.get("source_uid")):
                _clean(item.get("generation_role"))
                for item in latest_videos
                if _clean(item.get("video_uid") or item.get("source_uid"))
                in {
                    _clean(value)
                    for value in provisional_video_uids
                    if _clean(value)
                }
            }
            cleaned_latest = _remove_video_asset_uids(
                latest,
                provisional_video_uids,
            )

            # Retain terminal Maya/backend fields and the newest harmless
            # widget edits, then explicitly restore newest catalog authority.
            rebased = self._merge_widget_state(terminal_state, cleaned_latest)
            catalog_fields = (
                "videos",
                "picker_shots",
                "active_picker_shot_uuid",
                "preview_video_uid",
                "selected_video_uid",
                "selected_video_path",
                "selected_video_slot",
                "active_slot_count",
                "video_library_version",
                "shot_publisher_instance_uuid",
                "channel_uuid",
                "shot_uuid",
                "shot_number",
                "shot_name",
                "shot_selections",
                "accepted_shot_catalog_publisher_instance_uuid",
                "accepted_shot_catalog_channel_uuid",
                "accepted_shot_catalog_generation",
                "accepted_shot_catalog_metadata_sha256",
                "picker_legacy_membership_fallbacks",
            )
            for field in catalog_fields:
                rebased[field] = copy.deepcopy(cleaned_latest.get(field))

            rebased, captured_workspace_uuid = _assert_picker_workspace_capacity(
                rebased,
                context.picker_shot_uuid,
                len(generation_records),
            )
            actual_uid_by_role: Dict[str, str] = {}
            for raw_record in generation_records:
                record = dict(raw_record)
                role = _clean(record.get("generation_role"))
                if role in {"depth", "motion_guide"} and actual_uid_by_role.get(
                    "mask"
                ):
                    record["companion_video_uid"] = actual_uid_by_role["mask"]
                    record["source_video_uid"] = actual_uid_by_role["mask"]
                rebased = _append_video_asset(
                    rebased,
                    record,
                    picker_shot_uuid=captured_workspace_uuid,
                )
                appended = (
                    rebased.get("videos", [])[-1]
                    if rebased.get("videos")
                    else {}
                )
                actual_uid = _clean(
                    appended.get("video_uid") or appended.get("source_uid")
                )
                if role and actual_uid:
                    actual_uid_by_role[role] = actual_uid

            # Preserve the latest user selection. Provisional generated cards
            # that were selected are replaced by their finalized counterpart;
            # deselected/new records remain merely available in the history.
            final_rows: List[Dict[str, Any]] = []
            for raw_row in rebased.get("picker_shots", []):
                if not isinstance(raw_row, dict):
                    continue
                row = dict(raw_row)
                workspace_uuid = _uuid_text(row.get("workspace_uuid"))
                latest_row = latest_rows.get(workspace_uuid, {})
                owned_uids = _picker_representative_video_uids(
                    row.get("video_asset_uids")
                )
                owned_set = set(owned_uids)

                def finalized_uid(value: Any) -> str:
                    uid = _clean(value)
                    role = provisional_role_by_uid.get(uid)
                    return actual_uid_by_role.get(role, uid)

                selected_uids: List[str] = []
                for value in latest_row.get("selected_video_uids", []):
                    uid = finalized_uid(value)
                    if uid in owned_set and uid not in selected_uids:
                        selected_uids.append(uid)
                    if len(selected_uids) >= MAX_SELECTED_VIDEOS:
                        break
                preview_uid = finalized_uid(
                    latest_row.get("preview_video_uid")
                )
                if preview_uid not in owned_set:
                    preview_uid = (
                        selected_uids[0]
                        if selected_uids
                        else owned_uids[0]
                        if owned_uids
                        else ""
                    )
                row["selected_video_uids"] = selected_uids
                row["preview_video_uid"] = preview_uid
                row["selected_video_slot"] = max(
                    1,
                    min(
                        len(selected_uids) or 1,
                        int(latest_row.get("selected_video_slot") or 1),
                    ),
                )
                final_rows.append(row)
            rebased["picker_shots"] = final_rows
            active_workspace_uuid = _uuid_text(
                rebased.get("active_picker_shot_uuid")
            )
            active_final_row = next(
                (
                    row
                    for row in final_rows
                    if _uuid_text(row.get("workspace_uuid"))
                    == active_workspace_uuid
                ),
                final_rows[0] if final_rows else None,
            )
            if active_final_row is not None:
                # Workspace rows are the selection/preview authority. Project
                # the finalized active cursor before parsing; otherwise the
                # stale pre-generation global preview can overwrite this row
                # during workspace normalization.
                active_preview_uid = _clean(
                    active_final_row.get("preview_video_uid")
                )
                active_selected_uids = _picker_representative_video_uids(
                    active_final_row.get("selected_video_uids")
                )
                rebased["active_picker_shot_uuid"] = _uuid_text(
                    active_final_row.get("workspace_uuid")
                )
                rebased["preview_video_uid"] = active_preview_uid
                rebased["selected_video_uid"] = active_preview_uid
                rebased["selected_video_slot"] = (
                    active_selected_uids.index(active_preview_uid) + 1
                    if active_preview_uid in active_selected_uids
                    else max(
                        1,
                        int(active_final_row.get("selected_video_slot") or 1),
                    )
                )
            rebased = self._apply_selected_view_fields(_parse_state(rebased))
            self._write_state(rebased)
            return rebased

    def _start_ui_operation(self, action: str, incoming: Dict[str, Any]) -> None:
        """Run one accepted operation inside the worker started by after_value_set."""
        action_id = _clean(
            incoming.get("backend_ack_action_id")
            or incoming.get("pending_action_id")
        )
        if not self._hmb_process_lock.acquire(blocking=False):
            with self._hmb_operation_control_lock:
                if self._hmb_pending_operation_id == action_id:
                    self._hmb_pending_operation_id = ""
            state = self._picker_state()
            state["pending_action"] = ""
            state["message"] = (
                "HMBVideoPickerLibrary가 이미 실행 중입니다. 현재 작업을 정지하거나 완료될 때까지 기다리세요."
                if _clean(state.get("language")).lower() == "ko"
                else "HMBVideoPickerLibrary is already running. Stop it or wait for it to finish."
            )
            _append_activity_log(state, "WARNING", state["message"])
            self._write_state(state)
            return
        with self._hmb_operation_control_lock:
            cancelled_before_start = self._hmb_cancel_requested.is_set()
        if cancelled_before_start:
            state = _parse_state(incoming)
            state["operation_kind"] = action
            state["operation_started_at_ms"] = int(state.get("operation_started_at_ms") or int(time.time() * 1000))
            state = self._mark_operation_finished(state)
            if action == "render_original_preview":
                ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
                state.update({
                    "status": ready_stage,
                    "scene_stage": ready_stage,
                    "scene_request_status": "COMPLETE",
                    "message": "Original preview generation stopped before Maya started; existing outputs were preserved.",
                    "original_preview_enabled": False,
                    "pending_action": "",
                    "pending_action_id": "",
                    "active_process_pid": 0,
                    "active_process_kind": "",
                })
                state = self._apply_selected_view_fields(state)
            else:
                state.update({
                    "status": "CANCELLED",
                    "scene_stage": "CANCELLED",
                    "message": "READ stopped before Maya started." if action == "read_scene" else "The operation stopped before Maya started.",
                    "pending_action": "",
                    "pending_action_id": "",
                    "warnings": [],
                })
            _append_activity_log(
                state,
                "WARNING",
                "STOP completed before the pending Maya worker started.",
            )
            self._write_state(state)
            self._sync_outputs_from_state(state)
            with self._hmb_operation_control_lock:
                if self._hmb_pending_operation_id == action_id:
                    self._hmb_pending_operation_id = ""
                if self._hmb_worker_thread is threading.current_thread():
                    self._hmb_worker_thread = None
            self._hmb_process_lock.release()
            return
        incoming["pending_action"] = ""
        scene_text = next(
            (
                candidate
                for candidate in (
                    _maya_scene_path_text(incoming.get("scene_request_path")),
                    _maya_scene_path_text(incoming.get("scene_path")),
                    self._current_scene_text(),
                )
                if candidate
            ),
            "",
        )
        try:
            scene_path = _norm_path(scene_text)
            if scene_path.suffix.lower() not in {".ma", ".mb"} or not scene_path.is_file():
                raise FileNotFoundError(f"Select an existing Maya .mb or .ma scene before {action}.")
            slot = max(
                1,
                min(
                    int(incoming.get("active_slot_count") or 1),
                    int(incoming.get("selected_video_slot") or 1),
                ),
            )
            context = self._create_operation_context(action, scene_path, incoming, slot)
        except Exception:
            if action == "render_original_preview":
                # Let the common failure handler recognize this as an optional
                # Original failure even when scene/context preflight failed.
                failed_preflight_state = _parse_state(incoming)
                failed_preflight_state["operation_kind"] = action
                failed_preflight_state["operation_started_at_ms"] = int(time.time() * 1000)
                self._write_state(failed_preflight_state)
            with self._hmb_operation_control_lock:
                if self._hmb_pending_operation_id == action_id:
                    self._hmb_pending_operation_id = ""
                if self._hmb_worker_thread is threading.current_thread():
                    self._hmb_worker_thread = None
            self._hmb_process_lock.release()
            raise
        self._hmb_active_operation = context
        incoming = self._mark_operation_started(incoming, action)
        incoming.update({
            "operation_id": context.operation_id,
            "operation_input_digest": context.input_digest,
            "operation_scene_fingerprint": context.scene_fingerprint,
            "operation_video_slot": context.video_slot,
            "scene_path": context.scene_path,
            "scene_request_path": context.scene_path,
        })
        if action == "read_scene":
            korean = _clean(incoming.get("language")).lower() == "ko"
            incoming.update({
                "status": "READING_SCENE",
                "scene_stage": "MAYA_READING",
                "message": "읽기가 시작되었습니다. 설치된 Maya mayabatch를 확인합니다." if korean else "READ started. Detecting the highest installed Maya mayabatch.",
            })
            _append_activity_log(
                incoming,
                "INFO",
                "읽기 시작. 백그라운드 Maya 아웃라이너 스캔이 실행 중입니다." if korean else "READ started. The background Maya Outliner scan is active.",
            )
            _append_activity_log(incoming, "INFO", "Stage 1/5: Python command accepted and worker lock acquired.")
            _append_activity_log(incoming, "INFO", "Stage 2/5: Starting background worker thread.")
            _diagnostic("READ started.")
        elif action == "render_snapshot":
            slot = context.video_slot
            frame = float(incoming.get("snapshot_frame") or incoming.get("current_frame") or 0.0)
            incoming.update({
                "status": "SNAPSHOT_RENDERING",
                "scene_stage": "SNAPSHOT_RENDERING",
                "message": f"Rendering the colored snapshot for @video{slot} at Maya frame {frame:g}.",
            })
            _append_activity_log(
                incoming,
                "INFO",
                f"Snapshot request received for @video{slot} at Maya frame {frame:g}.",
            )
        elif action == "render_original_preview":
            incoming.update({
                "status": "GENERATING_ORIGINAL",
                "scene_stage": "GENERATING_ORIGINAL",
                "message": "Preparing the on-demand original Maya playblast.",
                "original_preview_enabled": False,
            })
            _append_activity_log(
                incoming,
                "INFO",
                "Original preview requested. Existing READ metadata, bindings, videos, and successful artifacts remain active until publish.",
            )
        else:
            accepted_generation_flags = {
                "original_enabled": "original" in context.selected_roles,
                "mask_enabled": "mask" in context.selected_roles,
                "depth_enabled": "depth" in context.selected_roles,
                "motion_guide_enabled": "motion_guide" in context.selected_roles,
            }
            incoming.update(accepted_generation_flags)
            depth_enabled = bool(incoming.get("depth_enabled"))
            motion_guide_enabled = bool(
                incoming.get("motion_guide_enabled")
            )
            selected_roles = list(context.selected_roles)
            slot = PRIMARY_COLOR_VIDEO_SLOT
            depth_video_slot = context.depth_video_slot
            motion_guide_video_slot = context.motion_guide_video_slot
            incoming.update({
                "selected_video_slot": slot,
                "depth_video_slot": depth_video_slot,
                "motion_guide_video_slot": motion_guide_video_slot,
            })
            selected_labels = [
                "Motion Guide" if role == "motion_guide" else role.title()
                for role in selected_roles
            ]
            message = (
                "Preparing checked Generate Playblast outputs ("
                + ", ".join(selected_labels)
                + "). Detecting the highest installed Maya mayabatch."
            )
            log_message = (
                "Generate request received. Successful results will be appended "
                "to the video history: "
                + ", ".join(selected_labels)
                + "."
            )
            incoming.update({"status": "RUNNING", "message": message})
            _append_activity_log(incoming, "INFO", log_message)
        worker_name = threading.current_thread().name
        _append_activity_log(incoming, "INFO", f"Background worker thread started: {worker_name}.")
        terminal_success_state: Optional[Dict[str, Any]] = None
        terminal_generation_records: List[Dict[str, Any]] = []
        terminal_provisional_uids: List[str] = []
        terminal_publication_error: Optional[Exception] = None
        pending_selection_to_schedule: Optional[tuple[str, str]] = None
        try:
            self._write_state(incoming)
            self._cleanup_transient_paths()
            self._assert_operation_current(context, "worker start")
            scene_text = context.scene_path
            if action == "read_scene":
                self._read_scene_mode(scene_text, context=context)
            elif action == "render_snapshot":
                self._snapshot_mode(
                    scene_text,
                    context.video_slot,
                    context=context,
                    video_uid=context.snapshot_video_uid,
                )
            elif action == "render_original_preview":
                self._render_original_preview_mode(scene_text, context=context)
            else:
                selected_roles = list(context.selected_roles)
                accepted_generation_flags = {
                    "original_enabled": "original" in context.selected_roles,
                    "mask_enabled": "mask" in context.selected_roles,
                    "depth_enabled": "depth" in context.selected_roles,
                    "motion_guide_enabled": "motion_guide" in context.selected_roles,
                }
                generated_by_role: Dict[str, Dict[str, Any]] = {}
                original_cache_state: Dict[str, Any] = {}
                generation_warnings: List[str] = []
                if "original" in selected_roles:
                    try:
                        self._render_original_preview_mode(
                            scene_text,
                            context=context,
                            publish_public=False,
                        )
                        original_state = self._picker_state()
                        original_state = _snapshot_original_preview_asset(
                            _norm_path(scene_text),
                            original_state,
                        )
                        original_cache_state = {
                            "original_video_path": _clean(
                                original_state.get("original_video_path")
                            ),
                            "original_video_url": _clean(
                                original_state.get("original_video_url")
                            ),
                            "original_metadata": dict(
                                original_state.get("original_metadata") or {}
                            ),
                        }
                        generated_by_role["original"] = (
                            _original_video_item_from_state(original_state)
                        )
                    except _StaleOperationError:
                        raise
                    except Exception as exc:
                        detail = _clean(exc) or exc.__class__.__name__
                        raise RuntimeError(
                            "Selected Original failed, so Generate Playblast did "
                            "not publish a partial Mask/Depth/Motion result. "
                            f"{detail}"
                        ) from exc
                if any(
                    role in selected_roles
                    for role in ("mask", "depth", "motion_guide")
                ):
                    accepted_stage_state = self._picker_state()
                    accepted_stage_state.update(accepted_generation_flags)
                    self._write_state(accepted_stage_state)
                    core_generation_succeeded = False
                    core_result: Dict[str, Any] = {}
                    try:
                        self._prepare_run_state(
                            scene_text,
                            context.video_slot,
                            context=context,
                            publish_public=False,
                        )
                        core_result = self._maya_mode(
                            scene_text,
                            context.video_slot,
                            context=context,
                            publish_public=False,
                        )
                        core_generation_succeeded = True
                    except _StaleOperationError:
                        raise
                    except Exception as exc:
                        if not generated_by_role or self._hmb_cancel_requested.is_set():
                            raise
                        partial_state = self._picker_state()
                        warning = (
                            "Mask/Depth/Motion generation failed; preserving the "
                            f"validated Original output. {_clean(exc) or exc.__class__.__name__}"
                        )
                        merged_warnings = [
                            _clean(item)
                            for item in partial_state.get("warnings", [])
                            if _clean(item)
                        ]
                        if warning not in merged_warnings:
                            merged_warnings.append(warning)
                        if warning not in generation_warnings:
                            generation_warnings.append(warning)
                        partial_state["warnings"] = merged_warnings[-20:]
                        _append_activity_log(partial_state, "WARNING", warning)
                        self._write_state(partial_state)
                    generated_state = self._picker_state()
                    mask_item = next(
                        (
                            dict(item)
                            for item in reversed(generated_state.get("videos", []))
                            if isinstance(item, dict)
                            and _clean(item.get("generation_role")) == "mask"
                        ),
                        {},
                    )
                    if core_generation_succeeded and mask_item:
                        generated_by_role["mask"] = mask_item
                    depth_item = next(
                        (
                            dict(item)
                            for item in reversed(generated_state.get("videos", []))
                            if isinstance(item, dict)
                            and _is_generated_depth_video_item(item)
                        ),
                        {},
                    )
                    if (
                        core_generation_succeeded
                        and bool(core_result.get("depth_succeeded"))
                        and depth_item
                    ):
                        generated_by_role["depth"] = depth_item
                    motion_item = next(
                        (
                            dict(item)
                            for item in reversed(generated_state.get("videos", []))
                            if isinstance(item, dict)
                            and _is_generated_motion_guide_video_item(item)
                        ),
                        {},
                    )
                    if (
                        core_generation_succeeded
                        and bool(core_result.get("motion_guide_succeeded"))
                        and motion_item
                    ):
                        generated_by_role["motion_guide"] = motion_item

                final_base_state = self._picker_state()
                final_base_state.update(accepted_generation_flags)
                if original_cache_state:
                    final_base_state.update(original_cache_state)
                final_base_warnings = [
                    _clean(item)
                    for item in final_base_state.get("warnings", [])
                    if _clean(item)
                ]
                for warning in generation_warnings:
                    if warning not in final_base_warnings:
                        final_base_warnings.append(warning)
                final_base_state["warnings"] = final_base_warnings[-20:]
                terminal_provisional_uids = [
                    _clean(source.get("video_uid") or source.get("source_uid"))
                    for source in generated_by_role.values()
                    if isinstance(source, dict)
                    and _clean(
                        source.get("video_uid") or source.get("source_uid")
                    )
                ]
                generation_base_state = _remove_video_asset_uids(
                    final_base_state,
                    terminal_provisional_uids,
                )
                generation_base_uids = {
                    _clean(item.get("video_uid") or item.get("source_uid"))
                    for item in generation_base_state.get("videos", [])
                    if isinstance(item, dict)
                    and _clean(
                        item.get("video_uid") or item.get("source_uid")
                    )
                }
                final_state = _append_selected_generation_videos(
                    final_base_state,
                    generated_by_role,
                    selected_roles=context.selected_roles,
                    picker_shot_uuid=context.picker_shot_uuid,
                )
                # Appended Generate results use the catalog viewer. The legacy
                # preview flag would otherwise force Original over the selected
                # Mask/Depth/Motion history card.
                final_state["original_preview_enabled"] = False
                new_generation_items = [
                    item
                    for item in final_state.get("videos", [])
                    if isinstance(item, dict)
                    and _clean(
                        item.get("video_uid") or item.get("source_uid")
                    ) not in generation_base_uids
                    and _clean(item.get("generation_role"))
                    in set(context.selected_roles)
                ]
                terminal_generation_records = [
                    copy.deepcopy(item) for item in new_generation_items
                ]
                actual_roles = [
                    _clean(item.get("generation_role"))
                    for item in new_generation_items
                ]
                final_state["generation_output_roles"] = actual_roles
                final_state["status"] = (
                    "VIDEO_READY" if final_state.get("videos") else "OUTLINER_READY"
                )
                final_state["scene_stage"] = final_state["status"]
                if new_generation_items:
                    final_state["message"] = (
                        "Generate Playblast appended to video history: "
                        + ", ".join(
                            _clean(item.get("generation_role"))
                            .replace("_", " ")
                            .title()
                            for item in new_generation_items
                        )
                        + "."
                    )
                else:
                    final_state["message"] = (
                        "Generate Playblast completed without a validated video. "
                        "See Activity Log."
                    )
                final_state["snapshot_request_video_uid"] = ""
                final_state = _apply_active_snapshot_projection(
                    final_state,
                    viewport_mode="video",
                )
                final_state = self._mark_operation_finished(final_state)
                final_state = self._apply_selected_view_fields(final_state)
                # Keep the widget visibly busy until process cleanup and all
                # in-memory operation reservations have been retired. Without
                # this terminal boundary, an immediate post-success recolor can
                # be mistaken for a mutation of the already-finished run.
                terminal_success_state = final_state
        except _StaleOperationError as exc:
            if bool(self._picker_state().get("operation_invalidated")):
                self._set_stale_discarded_state(context, str(exc))
            else:
                self._set_cancelled_state()
        except Exception as exc:
            if self._hmb_cancel_requested.is_set():
                if bool(self._picker_state().get("operation_invalidated")):
                    self._set_stale_discarded_state(context, _clean(self._picker_state().get("operation_invalidation_reason")) or str(exc))
                else:
                    self._set_cancelled_state()
            else:
                self._set_failed_state(exc)
        finally:
            active = self._hmb_active_process
            if active is not None and active.poll() is None:
                _terminate_process(active)
            self._clear_active_process(active)
            self._cleanup_transient_paths()
            terminal_commit_context = None
            terminal_committed_state: Optional[Dict[str, Any]] = None
            if terminal_success_state is not None:
                terminal_commit_context = self._hmb_catalog_state_commit()
                terminal_commit_context.__enter__()
                try:
                    terminal_committed_state = self._commit_generate_terminal_state(
                        terminal_success_state,
                        context,
                        terminal_generation_records,
                        terminal_provisional_uids,
                    )
                except Exception as exc:
                    terminal_publication_error = (
                        exc
                        if isinstance(exc, Exception)
                        else RuntimeError(str(exc))
                    )
            if self._hmb_active_operation and self._hmb_active_operation.operation_id == context.operation_id:
                self._hmb_active_operation = None
            with self._hmb_operation_control_lock:
                if self._hmb_worker_thread is threading.current_thread():
                    self._hmb_worker_thread = None
            if self._hmb_process_lock.locked():
                self._hmb_process_lock.release()
            try:
                if terminal_committed_state is not None:
                    self._sync_outputs_from_state(terminal_committed_state)
            except Exception as exc:
                if terminal_publication_error is None:
                    terminal_publication_error = (
                        exc
                        if isinstance(exc, Exception)
                        else RuntimeError(str(exc))
                    )
            finally:
                # Keep the operation reservation and catalog commit through
                # terminal publication, but never leak either if an output
                # callback rejects the newly committed state.
                with self._hmb_operation_control_lock:
                    if self._hmb_pending_operation_id == action_id:
                        self._hmb_pending_operation_id = ""
                if terminal_commit_context is not None:
                    terminal_commit_context.__exit__(None, None, None)
            pending_selection = self._hmb_pending_scene_selection
            self._hmb_pending_scene_selection = None
            if pending_selection:
                pending_selection_to_schedule = pending_selection
        try:
            if terminal_publication_error is not None:
                self._set_failed_state(terminal_publication_error)
        finally:
            # A Maya scene selected during generation must start after the old
            # operation's terminal state is published, otherwise that terminal
            # echo can overwrite the newly scheduled READ state.
            if pending_selection_to_schedule:
                pending_path, pending_source = pending_selection_to_schedule
                try:
                    self._schedule_scene_selection(pending_path, pending_source)
                except Exception as exc:
                    _diagnostic_exception("pending Maya scene selection failed", exc)

    def _prepare_run_state(
        self,
        scene_text: str,
        video_slot: int,
        *,
        context: Optional[_OperationContext] = None,
        publish_public: bool = True,
    ) -> None:
        strict_scene_text = _maya_scene_path_text(scene_text)
        if not strict_scene_text:
            raise ValueError("A single absolute Maya .mb or .ma scene is required.")
        state = self._picker_state()
        depth_enabled = bool(state.get("depth_enabled"))
        motion_guide_enabled = bool(state.get("motion_guide_enabled"))
        video_slot = PRIMARY_COLOR_VIDEO_SLOT
        if context is not None:
            depth_video_slot = context.depth_video_slot
            motion_guide_video_slot = context.motion_guide_video_slot
        elif depth_enabled or motion_guide_enabled:
            (
                depth_video_slot,
                motion_guide_video_slot,
            ) = _resolve_generated_companion_slots(
                state,
                depth_enabled=depth_enabled,
                motion_guide_enabled=motion_guide_enabled,
            )
        else:
            depth_video_slot = 0
            motion_guide_video_slot = 0
        message = (
            "Maya is generating Mask, shader Depth, and Motion Guide from one "
            "scene load. Existing delivery remains "
            "active until all three results succeed."
            if depth_enabled and motion_guide_enabled
            else
            "Maya is generating paired Mask and shader Depth "
            "from one scene load. Existing library delivery remains active until both results succeed."
            if depth_enabled
            else
            "Maya is generating Mask and Motion Guide from one "
            "scene load. Existing library delivery remains active until both "
            "results succeed."
            if motion_guide_enabled
            else
            "Maya is generating a Mask from the current Group Name + Color Pick "
            "assignments. Existing library delivery remains active until the new "
            "result succeeds."
        )
        state.update({
            "mode": "maya",
            "status": "RUNNING",
            "message": message,
            "scene_path": strict_scene_text,
            "warnings": [],
            "selected_video_slot": video_slot,
            "depth_video_slot": depth_video_slot,
            "motion_guide_video_slot": motion_guide_video_slot,
        })
        _append_activity_log(
            state,
            "INFO",
            (
                "Preparing the typed Mask/Depth/Motion Guide bundle: validating "
                "assignments, shared visibility, the detected Maya installation and FFmpeg."
                if depth_enabled and motion_guide_enabled
                else
                "Preparing the paired Mask/Depth bundle: validating assignments, "
                "the detected Maya installation and FFmpeg."
                if depth_enabled
                else
                "Preparing the Mask/Motion Guide bundle: validating assignments, "
                "shared visibility, the detected Maya installation and FFmpeg."
                if motion_guide_enabled
                else
                "Preparing the Mask playblast: validating assignments, the "
                "detected Maya installation and FFmpeg."
            ),
        )
        self._write_state(state)
        if publish_public:
            self._sync_outputs_from_state(state)

    def _build_native_scene_selection_state(
        self,
        scene_text: Any,
        base_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Prepare Maya authoring state without clearing the Picker library.

        A Maya scene is an interchangeable authoring input.  Video catalog,
        per-Shot ownership/selection and preview identity are durable Picker
        state and therefore survive selecting a different scene. Scene-derived
        Outliner/camera/assignment/Snapshot state is still reset below.
        """
        state = _parse_state(base_state if isinstance(base_state, dict) else self._picker_state())
        previous_state = dict(state)
        active_slot_count = max(1, min(MAX_VIDEO_SLOTS, int(state.get("active_slot_count") or 1)))
        selected_video_slot = max(1, min(active_slot_count, int(state.get("selected_video_slot") or 1)))
        scene_text = _maya_scene_path_text(scene_text)
        same_scene_request = bool(
            scene_text
            and _scene_path_key(previous_state.get("scene_path") or previous_state.get("scene_request_path"))
            == _scene_path_key(scene_text)
        )
        state.update({
            "scene_stage": "EMPTY",
            "scene_path": "",
            "scene_draft_path": scene_text,
            "scene_request_path": scene_text,
            "native_read_ready": False,
            "native_read_mode": "maya-batch-atomic",
            "native_source_version": "",
            "native_metadata": {},
            "camera": "",
            "selected_camera": "",
            "cameras": [],
            "start_frame": 0.0,
            "end_frame": 0.0,
            "current_frame": 0.0,
            "source_fps": 0.0,
            "source_frame_count": 0,
            "output_frame_count": 0,
            "source_duration_seconds": 0.0,
            "output_duration_seconds": 0.0,
            "outliner_nodes": [],
            "outliner_expanded": [],
            "selected_outliner_path": "",
            "selected_outliner_name": "",
            "selected_outliner_uuid": "",
            "selected_color": "",
            "video_path": "",
            "video_url": "",
            "original_video_path": "",
            "original_video_url": "",
            "original_preview_enabled": False,
            "snapshot_active": False,
            "snapshot_frame": 0.0,
            "snapshot_video_slot": 0,
            "snapshot_data_uri": "",
            "snapshot_path": "",
            "snapshot_url": "",
            "snapshot_sha256": "",
            "active_snapshot_uid": "",
            "viewport_mode": "video",
            "snapshot_request_video_uid": "",
            "snapshots": [],
            "markers": [],
            "warnings": [],
            "pending_action": "",
            "workspace_view": "outliner",
            "slot_assignments": [
                {"video_slot": slot, "bindings": []}
                for slot in range(1, active_slot_count + 1)
            ],
            "selected_video_slot": selected_video_slot,
            "active_slot_count": active_slot_count,
            "static_frame_range_valid": False,
            "static_camera_metadata_valid": False,
            "static_metadata_complete": False,
        })
        if same_scene_request:
            for key in (
                "camera", "selected_camera", "cameras", "start_frame", "end_frame", "current_frame",
                "source_fps", "source_frame_count", "output_frame_count", "source_duration_seconds",
                "output_duration_seconds", "outliner_nodes", "outliner_expanded", "selected_outliner_path",
                "selected_outliner_name", "selected_outliner_uuid", "selected_color",
                "video_path", "video_url", "original_video_path", "original_video_url",
                "snapshot_active", "snapshot_frame",
                "snapshot_video_slot", "snapshot_data_uri", "snapshot_path",
                "snapshot_url", "snapshot_sha256",
                "active_snapshot_uid", "viewport_mode", "snapshots",
                "markers", "workspace_view", "videos", "slot_assignments",
                "outliner_search",
                "static_frame_range_valid", "static_camera_metadata_valid", "static_metadata_complete",
            ):
                if key in previous_state:
                    state[key] = previous_state[key]
        _append_activity_log(state, "INFO", f"LOAD received: {scene_text or '<empty>'}")
        if not scene_text:
            state.update({
                "status": "READY",
                "message": "Select a Maya .mb or .ma scene.",
            })
            return _parse_state(state)
        try:
            scene_path = _norm_path(scene_text)
            if scene_path.suffix.lower() not in {".mb", ".ma"}:
                raise ValueError(f"MAYA_SCENE must be .mb or .ma: {scene_path}")
            if not scene_path.is_file():
                raise FileNotFoundError(f"Maya scene does not exist: {scene_path}")
            mayabatch = _find_mayabatch()
            if mayabatch is None:
                raise FileNotFoundError("No mayabatch installation was found. Install Maya or set MAYA_LOCATION/PATH.")
            maya_version = _maya_display_version(mayabatch)
            normalized_path = str(scene_path).replace("\\", "/")
            state.update({
                "status": "SCANNING_SCENE",
                "scene_stage": "MAYA_READING",
                "message": (
                    f"Maya {maya_version} is opening the selected scene to read cameras, frame range, "
                    "FPS, and Outliner metadata without rendering video."
                ),
                "scene_path": normalized_path,
                "scene_draft_path": normalized_path,
                "scene_request_path": normalized_path,
                "native_read_ready": False,
                "native_read_mode": "maya-batch-atomic",
                "maya_executable": str(mayabatch).replace("\\", "/"),
                "maya_version": maya_version,
                "maya_available": True,
            })
            _append_activity_log(state, "SUCCESS", f"Maya scene selected: {normalized_path}")
            _append_activity_log(state, "SUCCESS", f"Maya {maya_version} is available: {mayabatch}")
            _append_activity_log(
                state,
                "INFO",
                "Step 1 started. One mayabatch process will read cameras, exact playback timing, FPS, and Outliner metadata only.",
            )
        except Exception as exc:
            error_text = _clean(exc) or exc.__class__.__name__
            detected_maya = _find_mayabatch()
            state.update({
                "status": "FAILED",
                "scene_stage": "LOAD_FAILED",
                "message": error_text,
                "warnings": [error_text],
                "scene_path": scene_text,
                "native_read_ready": False,
                "maya_executable": str(detected_maya).replace("\\", "/") if detected_maya else "",
                "maya_version": _maya_display_version(detected_maya) if detected_maya else "",
                "maya_available": detected_maya is not None,
            })
            _append_activity_log(state, "ERROR", error_text)
            _diagnostic_exception("Maya LOAD validation failed", exc)
        return _parse_state(state)

    def _schedule_scene_selection(self, scene_text: Any, source: str) -> None:
        """Validate the native picker selection and publish READ-ready state."""
        resolved_text = _maya_scene_path_text(scene_text)
        if _scene_path_text(scene_text) and not resolved_text:
            self._store_initial_parameter_value("MAYA_SCENE", "")
        base = self._picker_state()
        busy_status = _clean(base.get("status")).upper() in {
            "READ_PENDING", "READING_SCENE", "RUN_PENDING", "RUNNING", "GENERATING_VIDEO",
            "SNAPSHOT_PENDING", "SNAPSHOT_RENDERING", "CANCELLING"
        }
        if busy_status or _clean(base.get("operation_kind")) or self._hmb_process_lock.locked():
            self._hmb_pending_scene_selection = (resolved_text, _clean(source))
            self._invalidate_active_operation(
                "MAYA_SCENE changed while an operation was running. The old result will be discarded and the new LOAD path will be prepared.",
                terminate=True,
            )
            _diagnostic(f"scene selection queued while the previous operation is stopping: {source}")
            return
        base["scene_request_source"] = _clean(source)
        base["scene_request_status"] = "PROCESSING"
        prepared = self._build_native_scene_selection_state(resolved_text, base_state=base)
        prepared["scene_request_source"] = _clean(source)
        selection_valid = bool(resolved_text and _clean(prepared.get("status")).upper() == "SCANNING_SCENE")
        if selection_valid:
            prepared.update({
                "status": "READY",
                "scene_stage": "LOAD_READY",
                "scene_request_status": "COMPLETE",
                "native_read_ready": False,
                "message": "Maya scene selected. Press READ to load cameras, frame range, FPS, and Outliner metadata without rendering video.",
            })
            _append_activity_log(prepared, "SUCCESS", f"LOAD ready: {resolved_text}")
            _append_activity_log(prepared, "INFO", "Press READ to start the Maya scene scan.")
        else:
            prepared["scene_request_status"] = "IDLE" if not resolved_text else "FAILED"
        prepared["pending_action"] = ""
        self._write_state(prepared)
        self._sync_outputs_from_state(prepared)

    def _register_active_process(self, process: subprocess.Popen[Any], kind: str) -> None:
        if getattr(self, "_hmb_node_deleted", False):
            with suppress(Exception):
                process.kill()
            threading.Thread(
                target=_terminate_process,
                args=(process,),
                name="HMBVideoPicker-deleted-process-cleanup",
                daemon=True,
            ).start()
            raise RuntimeError("VideoPicker node was deleted before process registration.")
        self._hmb_active_process = process
        state = self._picker_state()
        state["active_process_pid"] = max(0, int(getattr(process, "pid", 0) or 0))
        state["active_process_kind"] = _clean(kind)
        _append_activity_log(
            state,
            "SUCCESS",
            f"{state['active_process_kind'] or 'External'} process launched with PID {state['active_process_pid']}. STOP can now terminate that process.",
        )
        self._write_state(state)

    def _clear_active_process(self, process: Optional[subprocess.Popen[Any]] = None) -> None:
        if process is not None and self._hmb_active_process is not process:
            return
        self._hmb_active_process = None
        state = self._picker_state()
        if int(state.get("active_process_pid") or 0) or _clean(state.get("active_process_kind")):
            state["active_process_pid"] = 0
            state["active_process_kind"] = ""
            self._write_state(state)

    def _handle_cancel_action(self, incoming: Dict[str, Any]) -> None:
        state = _parse_state(incoming)
        state["pending_action"] = ""
        state["pending_action_id"] = ""
        self._hmb_cancel_requested.set()
        with self._hmb_operation_control_lock:
            pending_operation = bool(self._hmb_pending_operation_id)
            worker = self._hmb_worker_thread
            worker_active = bool(worker is not None and worker.is_alive())
        active_process = self._hmb_active_process
        process_active = bool(active_process is not None and active_process.poll() is None)
        if process_active and active_process is not None:
            process_kind = _clean(state.get("active_process_kind")) or "external"
            process_pid = int(getattr(active_process, "pid", 0) or state.get("active_process_pid") or 0)
            state.update({
                "status": "CANCELLING",
                "scene_stage": "CANCELLING",
                "message": f"Stopping the active {process_kind} process (PID {process_pid})...",
                "active_process_pid": process_pid,
                "active_process_kind": process_kind,
            })
            _append_activity_log(
                state,
                "WARNING",
                f"STOP requested termination of the active {process_kind} process with PID {process_pid}.",
            )
            self._write_state(state)
            _terminate_process(active_process)
            return
        if pending_operation or worker_active or self._hmb_process_lock.locked():
            state.update({
                "status": "CANCELLING",
                "scene_stage": "CANCELLING",
                "message": "Cancelled the pending operation before an external process started.",
                "active_process_pid": 0,
                "active_process_kind": "",
            })
            _append_activity_log(
                state,
                "WARNING",
                "Pending operation cancellation requested before any Maya or FFmpeg PID existed.",
            )
            self._write_state(state)
            return
        state.update({
            "status": "READY",
            "message": "No active or pending operation to stop.",
            "active_process_pid": 0,
            "active_process_kind": "",
        })
        _append_activity_log(state, "INFO", "STOP ignored because no operation is running or pending.")
        self._write_state(state)

    def _handle_open_log_folder_action(self, incoming: Dict[str, Any]) -> None:
        state = _parse_state(incoming)
        state["pending_action"] = ""
        try:
            target_text = _clean(state.get("last_log_path") or state.get("log_folder"))
            if not target_text:
                scene_text = _maya_scene_path_text(
                    _raw_parameter_value(self, "MAYA_SCENE")
                )
                if scene_text:
                    target_text = str(_norm_path(scene_text).parent / "HMBVideoPicker")
            if not target_text:
                raise FileNotFoundError("No log folder is available yet.")
            _open_path_in_file_browser(_norm_path(target_text))
            state["message"] = "Opened the HMBVideoPicker log folder."
            _append_activity_log(state, "SUCCESS", f"Opened log folder: {target_text}")
        except Exception as exc:
            state["message"] = _clean(exc) or "Unable to open the log folder."
            _append_activity_log(state, "ERROR", state["message"])
        self._write_state(state)

    def before_value_set(
        self,
        parameter: Any,
        value: Any,
    ) -> Any:
        """Return one authoritative value for the current parameter transaction.

        The custom widget submits a complete dict for every small UI edit. A
        browser can therefore resend an older READ_PENDING snapshot after Python
        has already published OUTLINER_READY. Merge widget-owned fields here,
        before Griptape stores the value, so stale browser snapshots cannot
        replace backend-owned Maya results.
        """
        name = _parameter_name(parameter)
        if (
            name == WIDGET_STATE_PARAMETER
            and isinstance(value, dict)
            and isinstance(value.get(WIDGET_STATE_EMBEDDED_COMMAND_FIELD), dict)
        ):
            command = _parse_picker_command(
                value.get(WIDGET_STATE_EMBEDDED_COMMAND_FIELD)
            )
            if (
                _clean(command.get("runtime_instance_id"))
                == self._hmb_runtime_instance_id
                and _clean(command.get("action"))
                and _clean(command.get("action_id"))
            ):
                with self._hmb_command_lock:
                    self._hmb_embedded_command_queue.append(command)
        final_value = value
        if bool(getattr(self, "_hmb_node_deleted", False)):
            # A request already dispatched before deletion may arrive after a
            # same-name replacement exists. Never let the retired instance
            # normalize or adopt that transaction as live state.
            return _raw_parameter_value(self, name)
        try:
            if name == "MAYA_SCENE":
                # Native FileSystemPicker DOM/control aggregates are untrusted
                # input. Normalize before Griptape stores the property so an
                # invalid path can never survive in parameter_values even for
                # the ordinary (non-initial_setup) setter lifecycle.
                final_value = _maya_scene_path_text(value)
            elif name == WIDGET_STATE_PARAMETER:
                final_value = _parse_state(value)
            elif name == WIDGET_COMMAND_PARAMETER:
                final_value = _parse_picker_command(value)
        except Exception as exc:
            _diagnostic_exception("before_value_set normalization failed", exc)

        try:
            parent_hook = getattr(super(), "before_value_set", None)
            if callable(parent_hook):
                parent_value = parent_hook(parameter, final_value)
                if parent_value is not None:
                    final_value = parent_value
        except Exception as parent_exc:
            _diagnostic_exception("parent before_value_set failed", parent_exc)

        if name == "MAYA_SCENE":
            return _maya_scene_path_text(final_value)
        if name == WIDGET_STATE_PARAMETER:
            incoming = _parse_state(final_value)
            writer = _clean(incoming.get("state_writer")).lower()
            # Do not decide whether a foreign Python runtime is a saved
            # workflow or a late worker publication here. Griptape invokes
            # this hook *before* ``set_parameter_value`` even for
            # ``initial_setup=True`` workflow replay, but the hook receives no
            # initial-setup flag. Treating every previous-runtime writer as a
            # retired worker therefore replaced a valid serialized media
            # catalog with the constructor's empty default. The setter below
            # has the real lifecycle flag and performs that discrimination.
            if writer != "python" and not _is_state_syncing(self):
                with self._hmb_catalog_state_commit():
                    authoritative = _parse_state(
                        getattr(self, "_hmb_authoritative_state", None) or {}
                    )
                    if authoritative:
                        incoming = self._merge_widget_state(authoritative, incoming)

                    action_id = _clean(incoming.get("pending_action_id"))
                    if action_id and action_id in self._hmb_processed_action_ids:
                        incoming["backend_ack_action_id"] = action_id
                        incoming["pending_action"] = ""
                        incoming["pending_action_id"] = ""
                        _diagnostic(
                            f"discarded duplicate stale widget action before storage: {action_id}"
                        )
            incoming["pending_action"] = ""
            incoming["pending_action_id"] = ""
            return _parse_state(incoming)
        if name == WIDGET_COMMAND_PARAMETER:
            return _parse_picker_command(final_value)
        return final_value

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> Any:
        """Restore dynamic VIDEO outputs after Griptape's initial value write.

        Serialized workflows set ``HMB_PICKER_STATE`` with
        ``initial_setup=True``.  Griptape stores that value without invoking
        ``after_value_set()``, so the constructor's one-slot visibility would
        otherwise survive even when the saved state contains VIDEO2_OUT or
        VIDEO3_OUT connections.  Apply the saved snapshot only after the base
        setter has stored it, while leaving every normal transaction on the
        existing before/store/after path.
        """
        if (
            initial_setup
            and param_name == WIDGET_STATE_PARAMETER
            and hasattr(self, "_hmb_runtime_instance_id")
        ):
            # A new serialized snapshot (including loading another workflow in
            # the same engine process) must rebind every process-local poster.
            self._hmb_thumbnail_serialized_adoption_complete = False
            self._hmb_thumbnail_recovery_generation = 0
        parent_setter = super().set_parameter_value
        if (
            not initial_setup
            and param_name == WIDGET_STATE_PARAMETER
            and hasattr(self, "_hmb_runtime_instance_id")
            and not _is_state_syncing(self)
        ):
            candidate = _parse_state(value)
            writer_runtime_id = _clean(
                candidate.get("writer_runtime_instance_id")
            )
            if (
                _clean(candidate.get("state_writer")).lower() == "python"
                and writer_runtime_id
                and writer_runtime_id != self._hmb_runtime_instance_id
            ):
                # Normal live publications from a deleted/replaced Picker must
                # not be allowed to overwrite the replacement. Unlike
                # before_value_set(), this method receives ``initial_setup``
                # and can reject only the live stale-worker case without
                # rejecting a legitimate saved-workflow snapshot.
                value = _parse_state(
                    getattr(self, "_hmb_authoritative_state", None)
                    or _raw_parameter_value(self, WIDGET_STATE_PARAMETER)
                )
        lifecycle_values = {
            "initial_setup": initial_setup,
            "emit_change": emit_change,
            "skip_before_value_set": skip_before_value_set,
        }
        try:
            parent_parameters = inspect.signature(parent_setter).parameters
            accepts_keywords = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parent_parameters.values()
            )
            lifecycle_kwargs = {
                name: lifecycle_value
                for name, lifecycle_value in lifecycle_values.items()
                if accepts_keywords or name in parent_parameters
            }
        except (TypeError, ValueError):
            # Python methods are inspectable in supported Griptape releases;
            # keep the full modern contract for an opaque compatibility shim.
            lifecycle_kwargs = lifecycle_values
        result = parent_setter(param_name, value, **lifecycle_kwargs)

        if (
            initial_setup
            and param_name == "MAYA_SCENE"
            and hasattr(self, "_hmb_runtime_instance_id")
        ):
            # Only the host's explicit serialized-value lifecycle can grant a
            # pre-existing native picker value authority in this new runtime.
            # Ordinary constructor/native-template values are cleared above;
            # normal Browse/value-set callbacks use the live state path instead.
            self._hmb_serialized_maya_scene_path = _maya_scene_path_text(value)
        if (
            initial_setup
            and param_name == WIDGET_STATE_PARAMETER
            and hasattr(self, "_hmb_runtime_instance_id")
        ):
            self._restore_dynamic_state(adopt_serialized=True)
            self._schedule_post_hydration_shot_reconcile()
        return result

    def _schedule_post_hydration_shot_reconcile(self) -> bool:
        """Re-run same-flow discovery after serialized state becomes authoritative."""

        scheduler = getattr(
            _shot_routing, "schedule_post_hydration_reconcile", None
        )
        return bool(callable(scheduler) and scheduler(self))

    def _schedule_action_worker(
        self,
        action: str,
        action_id: str,
        target: Any,
    ) -> None:
        """Start one worker after the current retained-mode request has completed."""

        def launch() -> None:
            if getattr(self, "_hmb_node_deleted", False):
                return
            thread = threading.Thread(
                target=target,
                name=f"HMBVideoPicker-{action}",
                daemon=True,
            )
            if action in {
                "read_scene", "run_video", "render_snapshot", "render_original_preview",
            }:
                self._hmb_worker_thread = thread
            _diagnostic(f"starting widget action worker: {thread.name} {action_id}")
            thread.start()

        if action in {"cancel_pending", "cancel_operation", "stop_read"}:
            launch()
            return

        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore
        except ImportError:
            launch()
            return
        try:
            event_loop = GriptapeNodes.EventManager().event_loop
            if event_loop is not None and event_loop.is_running():
                event_loop.call_soon_threadsafe(launch)
                _diagnostic(f"widget action scheduled after current request: {action} {action_id}")
                return
        except Exception as exc:
            _diagnostic_exception("event-loop action scheduling unavailable", exc)
        launch()

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        """Invalidate queued work and terminate external tools without joining."""

        if not bool(getattr(self, "_hmb_node_deleted", False)):
            try:
                _shot_routing.prepare_node_deletion(self)
            except Exception as exc:
                _diagnostic_exception(
                    "VideoPicker reset handoff preparation failed",
                    exc,
                )
        if bool(getattr(self, "_hmb_node_deleted", False)):
            if bool(getattr(self, "_hmb_delete_parent_called", False)):
                return None
        else:
            # Invalidate immediately. Waiting for a worker-owned state lock can
            # deadlock when that worker is blocked on the retained-mode request
            # currently dispatching this deletion callback.
            self._hmb_node_deleted = True
            self._hmb_lifecycle_generation = (
                int(getattr(self, "_hmb_lifecycle_generation", 0) or 0) + 1
            )
            try:
                _shot_routing.release_node_lifecycle(self)
            except Exception as exc:
                _diagnostic_exception(
                    "VideoPicker lifecycle release failed",
                    exc,
                )
        self._hmb_cancel_requested.set()
        with self._hmb_operation_control_lock:
            self._hmb_pending_operation_id = ""
            self._hmb_active_operation = None
            self._hmb_pending_scene_selection = None
        process = self._hmb_active_process
        self._hmb_active_process = None
        if process is not None and process.poll() is None:
            # Kill immediately, then let the existing tree-cleanup routine run
            # off-thread.  The host delete lifecycle must never wait/join.
            with suppress(Exception):
                process.kill()
            with suppress(Exception):
                threading.Thread(
                    target=_terminate_process,
                    args=(process,),
                    name="HMBVideoPicker-delete-process-cleanup",
                    daemon=True,
                ).start()
        if not bool(getattr(self, "_hmb_deletion_reconcile_called", False)):
            self._hmb_deletion_reconcile_called = True
            try:
                _shot_routing.schedule_post_deletion_reconcile(self)
            except Exception as exc:
                _diagnostic_exception(
                    "Post-deletion Shot routing schedule failed", exc
                )
        if bool(getattr(self, "_hmb_delete_parent_called", False)):
            return None
        self._hmb_delete_parent_called = True
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None

    def _import_video_asset(
        self,
        state: Dict[str, Any],
        source_path: Any,
        *,
        label: Any = "",
        picker_shot_uuid: Any = "",
    ) -> Dict[str, Any]:
        """Import one MP4 once per Shot, reusing an existing source card."""
        source = _norm_path(source_path)
        if source.suffix.lower() != ".mp4":
            raise ValueError(f"Only MP4 video assets can be imported: {source}")
        if not source.is_file():
            raise FileNotFoundError(f"Imported MP4 does not exist: {source}")
        if not _is_structurally_valid_mp4(source):
            raise ValueError(f"Imported MP4 is not structurally readable: {source}")

        state, captured_picker_shot_uuid = _assert_picker_workspace_capacity(
            state,
            picker_shot_uuid,
            0,
        )
        existing_import = _picker_workspace_imported_asset(
            state,
            captured_picker_shot_uuid,
            source,
        )
        if existing_import is not None:
            result = _reuse_picker_imported_asset(
                state,
                captured_picker_shot_uuid,
                existing_import,
            )
            result.update({
                "status": "VIDEO_READY",
                "scene_stage": "VIDEO_READY",
                "workspace_view": "playblast",
                "message": (
                    "This MP4 is already loaded in the active Shot; "
                    "the existing card was reused."
                ),
            })
            _append_activity_log(result, "INFO", result["message"])
            return _parse_state(result)
        state, captured_picker_shot_uuid = _assert_picker_workspace_capacity(
            state,
            captured_picker_shot_uuid,
            1,
        )

        scene_text = next(
            (
                candidate
                for candidate in (
                    _maya_scene_path_text(state.get("scene_path")),
                    _maya_scene_path_text(state.get("scene_request_path")),
                )
                if candidate
            ),
            "",
        )
        local_video = source
        project_video_path = ""
        preview_video = source
        video_metadata: Dict[str, Any] = {}
        import_warning = ""
        token = hashlib.sha1(
            f"import|{source}|{time.time_ns()}|{uuid.uuid4().hex}".encode(
                "utf-8"
            )
        ).hexdigest()[:12]
        output_folder: Optional[Path] = None
        if scene_text:
            scene_path = _norm_path(scene_text)
            if scene_path.is_file() and scene_path.suffix.lower() in {".ma", ".mb"}:
                output_folder = _ensure_scene_output_folder(scene_path)
                target = output_folder / (
                    f"{_safe_scene_name(source.stem)}_import_{token}.mp4"
                )
                if target.exists():
                    raise FileExistsError(
                        "Unique imported-video target unexpectedly exists."
                    )
                shutil.copy2(source, target)
                local_video = target

        # Browser media elements cannot reliably play a UNC/file URL selected
        # from a server search. Always publish an active-project copy, even when
        # no Maya scene is open, and serve that verified local copy instead.
        backup_folder = (
            output_folder / ".hmb_video_picker" / f"import_video_{token}"
            if output_folder is not None
            else Path(tempfile.gettempdir()).resolve()
            / ".hmb_video_picker"
            / f"import_video_{token}"
        )
        _assert_safe_private_path(backup_folder)
        project_records: List[tuple[Path, Path, bool]] = []
        try:
            project_artifact, project_video_path = _copy_video_to_griptape_project(
                self,
                local_video,
                1,
                transaction_records=project_records,
                backup_folder=backup_folder,
            )
            video_metadata = dict(getattr(project_artifact, "meta", {}) or {})
            resolved_project_video = _resolve_readable_video_reference(
                project_video_path
            )
            if resolved_project_video is None:
                raise RuntimeError(
                    "The active-project video copy could not be read after publication."
                )
            preview_video = resolved_project_video
        except Exception as exc:
            # Preserve the immutable source/shot-local asset for recovery and
            # downstream absolute-path use, but report that browser playback is
            # unavailable until a project copy can be created.
            if project_records:
                HMBVideoPickerLibrary._restore_playblast_bundle(project_records)
            project_video_path = ""
            preview_video = local_video
            import_warning = (
                "Imported MP4 was retained at its source location because the "
                "active Griptape project copy failed; browser playback may be "
                "unavailable: "
                f"{_clean(exc) or exc.__class__.__name__}"
            )
        finally:
            try:
                if backup_folder.is_dir():
                    _safe_remove_private_tree(backup_folder)
            except Exception as exc:
                _diagnostic_exception(
                    "Imported-video transaction cleanup failed",
                    exc,
                )

        item = {
            "video_path": str(local_video.resolve()).replace("\\", "/"),
            "project_video_path": project_video_path,
            "video_metadata": video_metadata,
            "video_url": _external_media_url(preview_video),
            "scene_path": scene_text,
            "markers": [],
            "generation_role": "imported",
            "media_kind": "imported_mp4_reference",
            "video_role": "user_imported_reference",
            "source_type_hint": "User Imported Cut Reference",
            "control_role_hint": "User Selected Video Reference",
            "label": _clean(label) or source.stem,
            "import_source_path": str(source.resolve()).replace("\\", "/"),
            "imported_at_ms": int(time.time() * 1000),
        }
        result = _append_video_asset(
            state,
            item,
            picker_shot_uuid=captured_picker_shot_uuid,
        )
        appended = result.get("videos", [])[-1] if result.get("videos") else {}
        result.update({
            "status": "VIDEO_READY",
            "scene_stage": "VIDEO_READY",
            "workspace_view": "playblast",
            "message": (
                f"Imported MP4 added to the cut history: "
                f"{_clean(appended.get('label')) or source.stem}."
            ),
        })
        _append_activity_log(result, "SUCCESS", result["message"])
        if import_warning:
            warnings = [
                _clean(value)
                for value in result.get("warnings", [])
                if _clean(value)
            ]
            if import_warning not in warnings:
                warnings.append(import_warning)
            result["warnings"] = warnings[-20:]
            _append_activity_log(result, "WARNING", import_warning)
        return _parse_state(result)

    def _commit_video_import_sources(
        self,
        sources: Sequence[Dict[str, str]],
        *,
        captured_picker_shot_uuid: Any,
        action_id: str,
    ) -> Dict[str, Any]:
        """Serialize one import delta against the newest committed catalog.

        File dialogs may finish in any order. The commit mutex also covers
        ImageAsset reconcile/clear, so the latest state is read only after all
        earlier imports or authoritative Shot deletion have committed. This
        prevents last-writer-wins loss and makes a deleted captured workspace a
        hard failure instead of resurrecting its stale snapshot.
        """

        # Expensive validation/copying is intentionally outside catalog/state
        # locks. Only the final durable delta commit is serialized.
        staging_state, captured_workspace_uuid = _assert_picker_workspace_capacity(
            self._picker_state(),
            captured_picker_shot_uuid,
            0,
        )
        baseline_warning_set = {
            _clean(value)
            for value in staging_state.get("warnings", [])
            if _clean(value)
        }
        imported_records: List[Dict[str, Any]] = []
        import_failures: List[str] = []
        duplicate_sources: List[Dict[str, str]] = []
        for source in sources:
            source_path = source["source_path"]
            try:
                if _picker_workspace_imported_asset(
                    staging_state,
                    captured_workspace_uuid,
                    source_path,
                ) is not None:
                    duplicate_sources.append(dict(source))
                    continue
                before_uids = {
                    _clean(item.get("video_uid") or item.get("source_uid"))
                    for item in staging_state.get("videos", [])
                    if isinstance(item, dict)
                }
                staged_result = self._import_video_asset(
                    staging_state,
                    source_path,
                    label=source.get("label"),
                    picker_shot_uuid=captured_workspace_uuid,
                )
                appended = [
                    dict(item)
                    for item in staged_result.get("videos", [])
                    if isinstance(item, dict)
                    and _clean(
                        item.get("video_uid") or item.get("source_uid")
                    ) not in before_uids
                ]
                if not appended:
                    raise RuntimeError(
                        "Imported MP4 produced no durable video asset."
                    )
                imported_records.append(appended[-1])
                staging_state = staged_result
            except Exception as exc:
                source_label = _clean(source.get("label")) or Path(
                    source_path
                ).name
                import_failures.append(
                    f"{source_label or 'MP4'}: "
                    f"{_clean(exc) or exc.__class__.__name__}"
                )
        if not imported_records and not duplicate_sources:
            raise RuntimeError(
                "No selected MP4 could be imported. "
                + " | ".join(import_failures[:5])
            )

        # Re-read immediately before the durable write. Merge only the imported
        # records into that newest state and revalidate the captured workspace.
        with self._hmb_catalog_state_commit():
            state, captured_workspace_uuid = _assert_picker_workspace_capacity(
                self._picker_state(),
                captured_workspace_uuid,
                0,
            )
            pending_records: List[Dict[str, Any]] = []
            for imported_record in imported_records:
                import_source_path = imported_record.get("import_source_path")
                existing = _picker_workspace_imported_asset(
                    state,
                    captured_workspace_uuid,
                    import_source_path,
                )
                if existing is not None:
                    state = _reuse_picker_imported_asset(
                        state,
                        captured_workspace_uuid,
                        existing,
                    )
                    duplicate_sources.append({
                        "source_path": _clean(import_source_path),
                        "label": _clean(imported_record.get("label")),
                    })
                    continue
                pending_records.append(imported_record)
            state, captured_workspace_uuid = _assert_picker_workspace_capacity(
                state,
                captured_workspace_uuid,
                len(pending_records),
            )
            for duplicate_source in duplicate_sources:
                existing = _picker_workspace_imported_asset(
                    state,
                    captured_workspace_uuid,
                    duplicate_source.get("source_path"),
                )
                if existing is not None:
                    state = _reuse_picker_imported_asset(
                        state,
                        captured_workspace_uuid,
                        existing,
                    )
            for imported_record in pending_records:
                state = _append_video_asset(
                    state,
                    imported_record,
                    picker_shot_uuid=captured_workspace_uuid,
                )
            state["backend_ack_action_id"] = action_id
            state["pending_action"] = ""
            state["pending_action_id"] = ""
            state["status"] = "VIDEO_READY"
            state["scene_stage"] = "VIDEO_READY"
            state["workspace_view"] = "playblast"
            imported_count = len(pending_records)
            duplicate_count = len(duplicate_sources)
            if imported_count:
                state["message"] = (
                    f"Imported {imported_count} MP4 file(s) into the cut history."
                )
                _append_activity_log(state, "SUCCESS", state["message"])
            else:
                state["message"] = (
                    f"Skipped {duplicate_count} duplicate MP4 file(s); "
                    "the existing Shot card was reused."
                )
                _append_activity_log(state, "INFO", state["message"])
            if duplicate_count and imported_count:
                _append_activity_log(
                    state,
                    "INFO",
                    f"Skipped {duplicate_count} duplicate MP4 file(s) already loaded in this Shot.",
                )
            new_import_warnings = [
                _clean(value)
                for value in staging_state.get("warnings", [])
                if _clean(value) and _clean(value) not in baseline_warning_set
            ]
            if new_import_warnings:
                warnings = [
                    _clean(item)
                    for item in state.get("warnings", [])
                    if _clean(item)
                ]
                for warning in new_import_warnings:
                    if warning not in warnings:
                        warnings.append(warning)
                        _append_activity_log(state, "WARNING", warning)
                state["warnings"] = warnings[-20:]
            if import_failures:
                warning = (
                    f"Skipped {len(import_failures)} MP4 file(s): "
                    + " | ".join(import_failures[:5])
                )
                warnings = [
                    _clean(item)
                    for item in state.get("warnings", [])
                    if _clean(item)
                ]
                if warning not in warnings:
                    warnings.append(warning)
                state["warnings"] = warnings[-20:]
                _append_activity_log(state, "WARNING", warning)
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return state

    def _acknowledge_video_import_failure(
        self,
        action_id: str,
        error: Any,
    ) -> Dict[str, Any]:
        """Finish a failed file action without destabilizing durable media."""

        detail = _clean(error) or error.__class__.__name__
        with self._hmb_catalog_state_commit():
            state = self._picker_state()
            state["backend_ack_action_id"] = action_id
            state["pending_action"] = ""
            state["pending_action_id"] = ""
            state["message"] = f"MP4 import did not change the library: {detail}"
            _append_activity_log(state, "WARNING", state["message"])
            self._write_state(state)
        return state

    def _handle_picker_command(self, command: Dict[str, Any]) -> None:
        command = _parse_picker_command(command)
        action = _clean(command.get("action"))
        action_id = _clean(command.get("action_id"))
        runtime_instance_id = _clean(command.get("runtime_instance_id"))
        payload = dict(command.get("payload") or {})
        operation_actions = {
            "read_scene", "run_video", "render_snapshot", "render_original_preview",
        }
        if not action or not action_id:
            return
        if runtime_instance_id != self._hmb_runtime_instance_id:
            _diagnostic(
                f"ignored stale command {action_id}: runtime {runtime_instance_id or '<blank>'} != {self._hmb_runtime_instance_id}"
            )
            return
        with self._hmb_command_lock:
            duplicate_action = action_id in self._hmb_processed_action_ids
            if not duplicate_action:
                self._hmb_processed_action_ids.add(action_id)
                if len(self._hmb_processed_action_ids) > 256:
                    self._hmb_processed_action_ids = set(
                        list(self._hmb_processed_action_ids)[-128:]
                    )
        if duplicate_action:
            duplicate_state = self._picker_state()
            duplicate_state["backend_ack_action_id"] = action_id
            self._write_state(duplicate_state)
            return
        state = self._picker_state()
        workspace_projection_applied = False
        workspace_uuid_supplied = any(
            key in payload for key in ("picker_shot_uuid", "workspace_uuid")
        )
        if action in PICKER_WORKSPACE_SENSITIVE_ACTIONS and workspace_uuid_supplied:
            requested_workspace_uuid = payload.get(
                "picker_shot_uuid",
                payload.get("workspace_uuid"),
            )
            projected_state = _activate_picker_workspace_projection(
                state,
                requested_workspace_uuid,
            )
            if projected_state is None:
                # A LOAD/Browse command may arrive just after ImageAsset
                # authoritatively deleted its captured Shot. Acknowledge the
                # stale command so the button guard unlocks immediately; never
                # leave the UI waiting for its transport timeout.
                state["backend_ack_action_id"] = action_id
                state["pending_action"] = ""
                state["pending_action_id"] = ""
                state["message"] = (
                    "The captured Picker Shot no longer exists. "
                    "The file action was cancelled without changing media."
                )
                _append_activity_log(state, "WARNING", state["message"])
                self._write_state(state)
                _diagnostic(
                    f"ignored command {action_id}: local Picker Shot workspace "
                    f"{_clean(requested_workspace_uuid) or '<blank>'} is unavailable"
                )
                return
            state = projected_state
            workspace_projection_applied = True
            workspace_scene_draft = _maya_scene_path_text(
                state.get("scene_draft_path")
            )
            if workspace_scene_draft and action in {
                "read_scene",
                "run_video",
                "render_snapshot",
                "delete_snapshot",
                "render_original_preview",
                "browse_maya_scene",
            }:
                state["scene_request_path"] = workspace_scene_draft

        state["backend_ack_action_id"] = action_id
        state["pending_action"] = ""
        state["pending_action_id"] = ""
        if action == "browse_maya_scene" or (
            workspace_projection_applied
            and action in {
                "browse_video_asset",
                "import_video_asset",
                "import_video_assets",
                "import_video",
            }
        ):
            # Publish the acknowledgement before an OS browser or file import
            # can yield. Maya browse is valid without a workspace UUID, while
            # video imports additionally persist their captured projection.
            self._write_state(state)
        if action == "run_video" and isinstance(
            payload.get("authoring_state"),
            dict,
        ):
            authoring_state = dict(payload["authoring_state"])
            # WIDGET_STATE and HMB_PICKER_COMMAND are independent transports.
            # Freeze the exact authoring snapshot visible when Generate was
            # clicked so a just-applied color/visibility edit cannot arrive
            # behind the command and invalidate or misconfigure this run.
            for field in (
                "selected_camera",
                "slot_assignments",
                "slot_visibility",
                "original_enabled",
                "mask_enabled",
                "depth_enabled",
                "motion_guide_enabled",
                "output_width",
                "output_height",
            ):
                if field in authoring_state:
                    state[field] = copy.deepcopy(authoring_state[field])
            state = _parse_state(state)
            state["backend_ack_action_id"] = action_id
            state["pending_action"] = ""
            state["pending_action_id"] = ""
        # Only Maya/FFmpeg work owns the transient busy stage. Metadata and UI
        # commands (notably catalog deletion) must retain the last stable stage;
        # otherwise the widget interprets their terminal echo as a permanently
        # running operation and disables the entire Picker.
        if action in operation_actions:
            state["scene_stage"] = "PYTHON_COMMAND_RECEIVED"

        scene_path = _maya_scene_path_text(payload.get("scene_path"))
        raw_scene_path_supplied = any(
            key in payload and payload.get(key) not in (None, "")
            for key in ("scene_path", "scene_request_path", "scene_draft_path")
        )
        if not scene_path:
            scene_path = next(
                (
                    candidate
                    for candidate in (
                        _maya_scene_path_text(payload.get("scene_request_path")),
                        _maya_scene_path_text(payload.get("scene_draft_path")),
                    )
                    if candidate
                ),
                "",
            )
        if scene_path:
            state["scene_draft_path"] = scene_path
            state["scene_request_path"] = scene_path
            state["scene_path"] = scene_path
            self._store_initial_parameter_value("MAYA_SCENE", scene_path)
        elif raw_scene_path_supplied:
            # A command carrying malformed scene text is an explicit invalid
            # selection, never permission to fall back to a previous scene.
            state.update({
                "scene_path": "",
                "scene_draft_path": "",
                "scene_request_path": "",
                "native_read_ready": False,
                "scene_stage": "EMPTY",
                "scene_request_status": "IDLE",
                "status": "READY",
                "message": "Select a Maya .mb or .ma scene.",
            })
            self._store_initial_parameter_value("MAYA_SCENE", "")
            _append_activity_log(
                state,
                "WARNING",
                "Rejected a malformed or non-absolute Maya scene path.",
            )
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return
        try:
            selected_slot = int(float(payload.get("selected_video_slot") or state.get("selected_video_slot") or 1))
        except Exception:
            selected_slot = int(state.get("selected_video_slot") or 1)
        state["selected_video_slot"] = max(1, min(int(state.get("active_slot_count") or 1), selected_slot))
        if action == "run_video":
            if "include_original" in payload:
                state["original_enabled"] = bool(payload.get("include_original"))
            if "include_mask" in payload:
                state["mask_enabled"] = bool(payload.get("include_mask"))
            if "include_depth" in payload:
                state["depth_enabled"] = bool(payload.get("include_depth"))
            if "include_motion_guide" in payload:
                state["motion_guide_enabled"] = bool(
                    payload.get("include_motion_guide")
                )
            if not _generation_choice_roles(state):
                raise ValueError(
                    "Generate Playblast requires at least one checked output: "
                    "Original, Mask, Depth, or Motion Guide."
                )
            # Rendering still uses one private Color staging position. Public
            # Original/Mask/Depth/Motion results append to history after success.
            state["selected_video_slot"] = PRIMARY_COLOR_VIDEO_SLOT
        if "output_width" in payload or "output_height" in payload:
            state["output_width"], state["output_height"] = _playblast_resolution({
                "output_width": payload.get("output_width"),
                "output_height": payload.get("output_height"),
            })
        if "snapshot_frame" in payload:
            try:
                state["snapshot_frame"] = float(payload.get("snapshot_frame") or 0.0)
            except Exception:
                state["snapshot_frame"] = float(state.get("current_frame") or 0.0)
            state["snapshot_video_slot"] = state["selected_video_slot"]
        if action == "render_snapshot":
            state["selected_video_slot"] = PRIMARY_COLOR_VIDEO_SLOT
            state["snapshot_video_slot"] = PRIMARY_COLOR_VIDEO_SLOT
            state["snapshot_request_video_uid"] = _clean(
                payload.get("video_uid")
                or payload.get("source_uid")
                or state.get("preview_video_uid")
                or state.get("selected_video_uid")
            )

        if action == "set_language":
            language = _clean(payload.get("language")).lower()
            if language not in {"en", "ko"}:
                raise ValueError("Language command must be 'en' or 'ko'.")
            state["language"] = language
            state["scene_stage"] = _clean(self._picker_state().get("scene_stage")) or "EMPTY"
            state["message"] = "한국어로 전환했습니다." if language == "ko" else "Language changed to English."
            _append_activity_log(state, "INFO", state["message"])
            self._write_state(state)
            return

        if action == "clear_log":
            state["activity_log"] = []
            state["activity_log_text"] = ""
            state["activity_log_text_user_edited"] = True
            state["activity_log_cleared"] = True
            state["message"] = "Activity log cleared."
            self._write_state(state)
            return

        if action == "hide_original_preview":
            active_operation = self._hmb_active_operation
            if (
                active_operation is not None
                and active_operation.kind == "render_original_preview"
            ):
                self._invalidate_active_operation(
                    "Original preview hidden while generation was running.",
                    terminate=True,
                )
                # _invalidate_active_operation writes the canonical state. Refresh
                # it, then retain the acknowledgement for this immediate command.
                state = self._picker_state()
                state["backend_ack_action_id"] = action_id
                state["pending_action"] = ""
                state["pending_action_id"] = ""
            ready_stage = (
                "VIDEO_READY"
                if state.get("videos")
                else "OUTLINER_READY" if state.get("native_read_ready") else "LOAD_READY"
            )
            state.update({
                "status": ready_stage,
                "scene_stage": ready_stage,
                "scene_request_status": "COMPLETE",
                "message": "Original preview hidden. The cached file was preserved.",
                "original_preview_enabled": False,
            })
            state = self._apply_selected_view_fields(state)
            _append_activity_log(state, "INFO", "Original preview hidden without deleting its cached artifact.")
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return

        if action == "render_original_preview":
            if not state.get("native_read_ready"):
                raise RuntimeError("Complete READ before requesting the original preview.")
            scene_path = _norm_path(
                scene_path or state.get("scene_request_path") or state.get("scene_path")
            )
            video_path, sidecar_path = _original_preview_paths(scene_path)
            if _original_preview_cache_is_valid(
                scene_path,
                state,
                video_path=video_path,
                sidecar_path=sidecar_path,
            ):
                ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
                state.update({
                    "status": ready_stage,
                    "scene_stage": ready_stage,
                    "scene_request_status": "COMPLETE",
                    "message": "Original preview loaded from the validated cache.",
                    "original_video_path": str(video_path).replace("\\", "/"),
                    "original_video_url": _external_media_url(video_path),
                    "original_metadata": _original_view_metadata(
                        _read_json(sidecar_path)
                    ),
                    "original_preview_enabled": True,
                    "workspace_view": "playblast",
                })
                state = self._apply_selected_view_fields(state)
                _append_activity_log(
                    state,
                    "SUCCESS",
                    f"Original preview cache validated and loaded without Maya or FFmpeg: {video_path}",
                )
                self._write_state(state)
                self._sync_outputs_from_state(state)
                return
            state.update({
                "original_preview_enabled": False,
                "original_video_path": "",
                "original_video_url": "",
            })
            requested_output_width, requested_output_height = _playblast_resolution(state)
            state = self._apply_selected_view_fields(state)
            # Showing the selected slot while Original is off must not replace
            # the resolution explicitly submitted for this Original request.
            state["output_width"] = requested_output_width
            state["output_height"] = requested_output_height

        if action in operation_actions:
            reserved = False
            with self._hmb_operation_control_lock:
                if not self._hmb_pending_operation_id and not self._hmb_process_lock.locked():
                    self._hmb_cancel_requested.clear()
                    self._hmb_pending_operation_id = action_id
                    reserved = True
            if not reserved:
                busy_state = self._picker_state()
                busy_state["backend_ack_action_id"] = action_id
                busy_state["pending_action"] = ""
                busy_state["pending_action_id"] = ""
                busy_state["message"] = (
                    "Another Picker operation is already reserved or running. "
                    "This duplicate request was not started."
                )
                _append_activity_log(
                    busy_state,
                    "WARNING",
                    busy_state["message"],
                )
                self._write_state(busy_state)
                return
            self._start_ui_operation(action, state)
            return
        if action == "delete_snapshot":
            self._handle_delete_snapshot_action(
                state,
                snapshot_uid=payload.get("snapshot_uid"),
                video_uid=payload.get("video_uid") or payload.get("source_uid"),
            )
            return
        if action in {"cancel_pending", "stop_read", "cancel_operation"}:
            self._hmb_cancel_requested.set()
            self._handle_cancel_action(state)
            return
        if action == "open_log_folder":
            self._handle_open_log_folder_action(state)
            return
        if action in {
            "browse_video_asset",
            "import_video_asset",
            "import_video_assets",
            "import_video",
        }:
            captured_picker_shot_uuid = _uuid_text(
                payload.get("picker_shot_uuid")
                or payload.get("workspace_uuid")
                or state.get("active_picker_shot_uuid")
            )
            sources: List[Dict[str, str]] = []
            if action == "browse_video_asset":
                initial_path = _clean(
                    payload.get("source_path")
                    or payload.get("file_path")
                    or payload.get("path")
                )
                sources = [
                    {"source_path": source_path, "label": ""}
                    for source_path in _choose_video_asset_files(initial_path)
                ]
            elif isinstance(payload.get("sources"), list):
                for raw_source in payload["sources"][:MAX_VIDEO_IMPORT_BATCH]:
                    if isinstance(raw_source, dict):
                        source_path = _clean(
                            raw_source.get("source_path")
                            or raw_source.get("file_path")
                            or raw_source.get("path")
                        )
                        label = _clean(
                            raw_source.get("label") or raw_source.get("name")
                        )
                    else:
                        source_path = _clean(raw_source)
                        label = ""
                    if source_path:
                        sources.append({
                            "source_path": source_path,
                            "label": label,
                        })
            else:
                source_path = _clean(
                    payload.get("source_path")
                    or payload.get("file_path")
                    or payload.get("path")
                )
                if source_path:
                    sources = [{
                        "source_path": source_path,
                        "label": _clean(
                            payload.get("label") or payload.get("name")
                        ),
                    }]
            if not sources:
                with self._hmb_catalog_state_commit():
                    state = self._picker_state()
                    state["backend_ack_action_id"] = action_id
                    state["pending_action"] = ""
                    state["pending_action_id"] = ""
                    state["message"] = "MP4 import was cancelled."
                    self._write_state(state)
                return
            try:
                self._commit_video_import_sources(
                    sources,
                    captured_picker_shot_uuid=captured_picker_shot_uuid,
                    action_id=action_id,
                )
            except Exception as exc:
                self._acknowledge_video_import_failure(action_id, exc)
            return
        if action in {"delete_video_asset", "remove_video_asset", "delete_video"}:
            video_uid = _clean(
                payload.get("video_uid") or payload.get("source_uid")
            )
            if not video_uid:
                raise ValueError("Deleting a video asset requires video_uid.")
            with self._hmb_catalog_state_commit():
                state = self._picker_state()
                state["backend_ack_action_id"] = action_id
                state["pending_action"] = ""
                state["pending_action_id"] = ""
                # The UI disables catalog mutation while a Maya/FFmpeg
                # operation is reserved or running. Recheck only after the
                # latest state is captured inside the shared catalog commit.
                with self._hmb_operation_control_lock:
                    operation_active = bool(
                        self._hmb_pending_operation_id
                        or self._hmb_active_operation is not None
                        or self._hmb_process_lock.locked()
                    )
                if operation_active:
                    state["message"] = (
                        "Video removal was ignored while a Picker operation is "
                        "running. Wait for it to finish, then remove the "
                        "history asset."
                    )
                    _append_activity_log(state, "WARNING", state["message"])
                elif not any(
                    isinstance(item, dict)
                    and _clean(
                        item.get("video_uid") or item.get("source_uid")
                    ) == video_uid
                    for item in state.get("videos", [])
                ):
                    # Repeated/stale delete is an idempotent acknowledgement.
                    state["message"] = (
                        "Video asset was already absent from the cut history; "
                        "no media file was changed."
                    )
                    _append_activity_log(state, "INFO", state["message"])
                else:
                    # Metadata-only deletion; external MP4 files remain
                    # recoverable and can be imported again.
                    state = _remove_video_asset_uids(state, [video_uid])
                    state["backend_ack_action_id"] = action_id
                    state["pending_action"] = ""
                    state["pending_action_id"] = ""
                    state["message"] = "Video asset removed from the cut history."
                    _append_activity_log(state, "INFO", state["message"])
                self._write_state(state)
            self._sync_outputs_from_state(state)
            return
        if action == "browse_maya_scene":
            selected = _choose_maya_scene_file(
                scene_path or state.get("scene_request_path") or state.get("scene_path")
            )
            if not selected:
                state.update({
                    "status": "READY",
                    "scene_stage": "LOAD_READY" if self._current_scene_text() else "EMPTY",
                    "message": "Maya scene selection was cancelled.",
                })
                self._write_state(state)
                return
            selected_path = _norm_path(selected)
            if selected_path.suffix.lower() not in {".ma", ".mb"}:
                raise ValueError(f"Select a Maya .ma or .mb scene: {selected_path}")
            if not selected_path.is_file():
                raise FileNotFoundError(f"Maya scene does not exist: {selected_path}")
            normalized_selected = str(selected_path).replace("\\", "/")
            _begin_state_sync(self)
            try:
                if not _request_parameter_value(self, "MAYA_SCENE", normalized_selected, "str"):
                    _set_parameter_value(self, "MAYA_SCENE", normalized_selected)
            finally:
                _end_state_sync(self)
            self._schedule_scene_selection(normalized_selected, "widget native OS browser")
            return
        raise ValueError(f"Unsupported HMB picker command: {action}")

    def after_value_set(
        self,
        parameter: Any,
        value: Any,
    ) -> None:
        """Process state and one-shot commands only after the current transaction."""
        output_side_effect_callback_started = False
        catalog_state_context = None
        try:
            if _is_state_syncing(self):
                return
            _begin_output_side_effect_callback(self)
            output_side_effect_callback_started = True
            name = _parameter_name(parameter)
            _diagnostic(f"after_value_set entered: {name or '<unknown>'}")

            if name == "MAYA_SCENE":
                scene_text = _maya_scene_path_text(value)
                if value is None:
                    scene_text = _maya_scene_path_text(
                        _raw_parameter_value(self, "MAYA_SCENE")
                    )
                scene_key = _scene_path_key(scene_text)
                current = self._picker_state()
                current_key = _scene_path_key(current.get("scene_request_path") or current.get("scene_path"))
                current_stage = _clean(current.get("scene_stage")).upper()
                if scene_key == current_key and current_stage not in {"", "EMPTY", "LOAD_FAILED", "FAILED"}:
                    return
                self._schedule_scene_selection(scene_text, "MAYA_SCENE.after_value_set")
                return

            if name == WIDGET_COMMAND_PARAMETER:
                command = _parse_picker_command(value)
                action = _clean(command.get("action")) or "command"
                action_id = _clean(command.get("action_id")) or f"{action}-{time.time_ns()}"

                def handle_command() -> None:
                    try:
                        self._handle_picker_command(command)
                    except Exception as action_exc:
                        _diagnostic_exception("picker command worker failed", action_exc)
                        self._set_failed_state(
                            action_exc if isinstance(action_exc, Exception) else RuntimeError(str(action_exc))
                        )

                self._schedule_action_worker(action, action_id, handle_command)
                return

            if name != WIDGET_STATE_PARAMETER:
                return

            embedded_command: Optional[Dict[str, Any]] = None
            with self._hmb_command_lock:
                if self._hmb_embedded_command_queue:
                    embedded_command = self._hmb_embedded_command_queue.pop(0)
            if embedded_command is not None:
                action = _clean(embedded_command.get("action")) or "command"
                action_id = _clean(embedded_command.get("action_id"))

                def handle_embedded_command() -> None:
                    try:
                        self._handle_picker_command(embedded_command)
                    except Exception as action_exc:
                        _diagnostic_exception(
                            "embedded picker command worker failed", action_exc
                        )
                        self._set_failed_state(action_exc)

                self._schedule_action_worker(
                    action,
                    action_id,
                    handle_embedded_command,
                )
                return

            catalog_state_context = self._hmb_catalog_state_commit()
            catalog_state_context.__enter__()

            incoming = _parse_state(value)
            incoming["pending_action"] = ""
            incoming["pending_action_id"] = ""
            previous_state = _parse_state(getattr(self, "_hmb_authoritative_state", None) or {})
            restored_revision = int(getattr(self, "_hmb_restored_state_pending_revision", -1) or -1)
            if restored_revision == int(incoming.get("state_revision") or 0):
                restored = self._apply_selected_view_fields(incoming)
                self._synchronize_picker_expanded_geometry_metadata(restored)
                self._hmb_authoritative_state = dict(restored)
                self._hmb_latest_widget_state = dict(restored)
                self._hmb_state_revision = int(restored.get("state_revision") or 0)
                self._hmb_restored_state_pending_revision = -1
                self._ensure_parameters()
                self._sync_outputs_from_state(restored)
                return

            merged = self._merge_widget_state(previous_state, incoming)
            merged = self._apply_selected_view_fields(merged)
            self._synchronize_picker_expanded_geometry_metadata(merged)
            self._hmb_latest_widget_state = dict(merged)
            self._hmb_authoritative_state = dict(merged)
            self._hmb_state_revision = max(
                int(getattr(self, "_hmb_state_revision", 0) or 0),
                int(merged.get("state_revision") or 0),
            )
            active_context = self._hmb_active_operation
            active_context_still_owned = bool(
                active_context is not None
                and _clean(previous_state.get("operation_id"))
                == active_context.operation_id
                and _clean(previous_state.get("operation_kind"))
                == active_context.kind
            )
            if active_context_still_owned and active_context is not None:
                current_scene = self._current_scene_text(active_context.scene_path)
                current_digest = _operation_input_digest(
                    active_context.kind,
                    current_scene,
                    merged,
                    active_context.video_slot,
                )
                if current_digest != active_context.input_digest:
                    self._invalidate_active_operation(
                        "A camera, frame, Color Pick, or scene input changed during execution. The old result will be discarded.",
                        terminate=True,
                    )
            previous_output_signature = _json_text({
                "active_slot_count": int(previous_state.get("active_slot_count") or 1),
                "videos": previous_state.get("videos") or [],
            })
            merged_output_signature = _json_text({
                "active_slot_count": int(merged.get("active_slot_count") or 1),
                "videos": merged.get("videos") or [],
            })
            previous_route_signature = _json_text({
                "shot_publisher_instance_uuid": previous_state.get("shot_publisher_instance_uuid"),
                "channel_uuid": previous_state.get("channel_uuid"),
                "shot_uuid": previous_state.get("shot_uuid"),
                "shot_number": previous_state.get("shot_number"),
                "shot_name": previous_state.get("shot_name"),
                "shot_selections": previous_state.get("shot_selections") or [],
                "picker_shots": previous_state.get("picker_shots") or [],
                "active_picker_shot_uuid": previous_state.get("active_picker_shot_uuid"),
                "picker_legacy_membership_fallbacks": previous_state.get("picker_legacy_membership_fallbacks") or {},
            })
            merged_route_signature = _json_text({
                "shot_publisher_instance_uuid": merged.get("shot_publisher_instance_uuid"),
                "channel_uuid": merged.get("channel_uuid"),
                "shot_uuid": merged.get("shot_uuid"),
                "shot_number": merged.get("shot_number"),
                "shot_name": merged.get("shot_name"),
                "shot_selections": merged.get("shot_selections") or [],
                "picker_shots": merged.get("picker_shots") or [],
                "active_picker_shot_uuid": merged.get("active_picker_shot_uuid"),
                "picker_legacy_membership_fallbacks": merged.get("picker_legacy_membership_fallbacks") or {},
            })
            if merged_route_signature != previous_route_signature:
                self._reconcile_shared_shot_routing()
                merged = self._picker_state()
            if merged_output_signature != previous_output_signature:
                self._sync_outputs_from_state(dict(merged))
            elif merged_route_signature != previous_route_signature:
                self._sync_outputs_from_state(dict(merged))
        except Exception as exc:
            _diagnostic_exception("after_value_set failed", exc)
            try:
                self._set_failed_state(exc if isinstance(exc, Exception) else RuntimeError(str(exc)))
            except Exception as nested:
                _diagnostic_exception("failed to publish after_value_set error", nested)
        finally:
            if catalog_state_context is not None:
                catalog_state_context.__exit__(None, None, None)
            if output_side_effect_callback_started:
                _end_output_side_effect_callback(self)
            try:
                parent_hook = getattr(super(), "after_value_set", None)
                if callable(parent_hook):
                    parent_hook(parameter, value)
            except Exception as parent_exc:
                _diagnostic_exception("parent after_value_set failed", parent_exc)

    def _set_failed_state(self, exc: Exception) -> None:
        state = self._picker_state()
        operation_kind = _clean(state.get("operation_kind"))
        message = _clean(exc) or exc.__class__.__name__
        last_log_path = _clean(state.get("last_log_path"))
        if last_log_path:
            try:
                failure_log = Path(last_log_path)
                failure_log.parent.mkdir(parents=True, exist_ok=True)
                with failure_log.open("a", encoding="utf-8", errors="replace") as log_handle:
                    log_handle.write(
                        f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                        f"HMB OPERATION ERROR: {message}\n"
                    )
            except Exception as log_exc:
                _diagnostic_exception("failed to append operation error log", log_exc)
        if operation_kind == "render_original_preview":
            state = self._mark_operation_finished(state)
            ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
            state.update({
                "status": ready_stage,
                "scene_stage": ready_stage,
                "scene_request_status": "COMPLETE",
                "message": (
                    "Original preview generation failed; completed READ metadata and "
                    f"existing outputs were preserved. {message}"
                ),
                "original_preview_enabled": False,
                "pending_action": "",
                "pending_action_id": "",
                "operation_invalidated": False,
                "operation_invalidation_reason": "",
                "active_process_pid": 0,
                "active_process_kind": "",
            })
            state = self._apply_selected_view_fields(state)
            warnings = [_clean(item) for item in state.get("warnings", []) if _clean(item)]
            if message and message not in warnings:
                warnings.append(message)
            state["warnings"] = warnings[-20:]
            _append_activity_log(state, "ERROR", message)
            _append_activity_log(
                state,
                "INFO",
                "The optional original preview stopped after an error. READ metadata, bindings, videos, and successful artifacts remain available.",
            )
            self._write_state(state)
            self._sync_outputs_from_state(state)
            return
        state.update({
            "status": "FAILED",
            "scene_stage": "FAILED",
            "operation_kind": "",
            "pending_action": "",
            "pending_action_id": "",
            "message": message,
            "native_read_ready": bool(state.get("native_read_ready")),
            "scene_request_status": "FAILED",
            "operation_invalidated": False,
            "operation_invalidation_reason": "",
            "active_process_pid": 0,
            "active_process_kind": "",
        })
        state = self._mark_operation_finished(state)
        warnings = [_clean(item) for item in state.get("warnings", []) if _clean(item)]
        if message and message not in warnings:
            warnings.append(message)
        state["warnings"] = warnings[-20:]
        _append_activity_log(state, "ERROR", message)
        operation_label = {
            "read_scene": "Maya scene READ",
            "render_snapshot": "Maya snapshot",
            "render_original_preview": "original preview",
            "run_video": "Maya playblast",
        }.get(operation_kind, "Maya/FFmpeg")
        _append_activity_log(
            state,
            "INFO",
            f"The {operation_label} operation stopped after an error. Review the diagnostic log and retry.",
        )
        self._write_state(state)

    def _recover_missing_video_thumbnails(
        self,
        owner_generation: int,
    ) -> None:
        """Backfill restored card posters and publish one UID-scoped merge."""

        published: Dict[str, tuple[str, str]] = {}
        try:
            if (
                getattr(self, "_hmb_node_deleted", False)
                or owner_generation
                != int(getattr(self, "_hmb_lifecycle_generation", 0) or 0)
            ):
                return
            snapshot = self._picker_state()
            for raw_item in snapshot.get("videos", []):
                if (
                    getattr(self, "_hmb_node_deleted", False)
                    or owner_generation
                    != int(
                        getattr(self, "_hmb_lifecycle_generation", 0) or 0
                    )
                ):
                    return
                if not isinstance(raw_item, dict):
                    continue
                if (
                    _clean(raw_item.get("thumbnail_url"))
                    and _clean(raw_item.get("thumbnail_runtime_id"))
                    == _VIDEO_THUMBNAIL_RUNTIME_ID
                ):
                    continue
                uid = _clean(
                    raw_item.get("video_uid") or raw_item.get("source_uid")
                )
                if not uid:
                    continue
                local_video = _resolved_video_asset_path(raw_item)
                if local_video is None:
                    continue
                url, signature = _video_asset_thumbnail_url(local_video, uid)
                if url and signature:
                    published[uid] = (url, signature)
            if not published:
                return

            with self._hmb_catalog_state_commit():
                if (
                    getattr(self, "_hmb_node_deleted", False)
                    or owner_generation
                    != int(
                        getattr(self, "_hmb_lifecycle_generation", 0) or 0
                    )
                ):
                    return
                latest = self._picker_state()
                videos = [
                    dict(item)
                    for item in latest.get("videos", [])
                    if isinstance(item, dict)
                ]
                changed = False
                for item in videos:
                    uid = _clean(
                        item.get("video_uid") or item.get("source_uid")
                    )
                    result = published.get(uid)
                    if result is None:
                        continue
                    if (
                        _clean(item.get("thumbnail_url"))
                        and _clean(item.get("thumbnail_runtime_id"))
                        == _VIDEO_THUMBNAIL_RUNTIME_ID
                    ):
                        continue
                    local_video = _resolved_video_asset_path(item)
                    if local_video is None:
                        continue
                    url, source_signature = result
                    if _video_thumbnail_signature(local_video) != source_signature:
                        # The card's source changed while FFmpeg was decoding;
                        # never attach the previous source's frame to that UID.
                        continue
                    item.update({
                        "thumbnail_url": url,
                        "thumbnail_runtime_id": _VIDEO_THUMBNAIL_RUNTIME_ID,
                        "thumbnail_source_signature": source_signature,
                    })
                    changed = True
                if changed:
                    latest["videos"] = videos
                    # _write_state normalizes against the newest catalog and
                    # increments one global revision. Selection/order and all
                    # expanded playback fields are left byte-for-byte intact.
                    self._write_state(latest)
        except Exception as exc:
            _diagnostic_exception("Video thumbnail recovery failed", exc)
        finally:
            worker_lock = getattr(self, "_hmb_thumbnail_worker_lock", None)
            if worker_lock is not None:
                with worker_lock:
                    if getattr(self, "_hmb_thumbnail_worker", None) is (
                        threading.current_thread()
                    ):
                        self._hmb_thumbnail_worker = None

    def _schedule_missing_video_thumbnail_recovery(self) -> bool:
        """Start at most one daemon backfill for this node lifecycle."""

        worker_lock = getattr(self, "_hmb_thumbnail_worker_lock", None)
        if worker_lock is None or getattr(self, "_hmb_node_deleted", False):
            return False
        current = getattr(self, "_hmb_authoritative_state", None)
        if not isinstance(current, dict):
            return False
        has_missing_thumbnail = any(
            isinstance(item, dict)
            and not (
                _clean(item.get("thumbnail_url"))
                and _clean(item.get("thumbnail_runtime_id"))
                == _VIDEO_THUMBNAIL_RUNTIME_ID
            )
            and any(
                _clean(item.get(field))
                for field in (
                    "project_video_path",
                    "video_path",
                    "import_source_path",
                )
            )
            for item in current.get("videos", [])
        )
        if not has_missing_thumbnail:
            # Do not consume this lifecycle's one backfill when an early host
            # hook fires before the serialized media catalog is installed.
            return False
        owner_generation = int(
            getattr(self, "_hmb_lifecycle_generation", 0) or 0
        )
        if owner_generation <= 0:
            return False
        with worker_lock:
            existing = getattr(self, "_hmb_thumbnail_worker", None)
            if existing is not None and existing.is_alive():
                return False
            if int(
                getattr(self, "_hmb_thumbnail_recovery_generation", 0) or 0
            ) == owner_generation:
                return False
            self._hmb_thumbnail_recovery_generation = owner_generation
            worker = threading.Thread(
                target=self._recover_missing_video_thumbnails,
                args=(owner_generation,),
                name="HMBVideoPicker-thumbnail-recovery",
                daemon=True,
            )
            self._hmb_thumbnail_worker = worker
            worker.start()
        return True

    def _restore_dynamic_state(self, *, adopt_serialized: bool = False) -> None:
        """Restore only the saved state; never auto-reset it during reconnect."""
        try:
            if adopt_serialized:
                serialized_state = _raw_parameter_value(
                    self,
                    WIDGET_STATE_PARAMETER,
                )
                raw_state = _parse_state(serialized_state)
                clear_process_thumbnail_urls = not bool(
                    getattr(
                        self,
                        "_hmb_thumbnail_serialized_adoption_complete",
                        False,
                    )
                )
                raw_state, media_urls_refreshed = _refresh_saved_video_media_urls(
                    raw_state,
                    clear_process_thumbnail_urls=clear_process_thumbnail_urls,
                )
                expanded_node_size = _reconciled_picker_expanded_state_size(
                    serialized_state,
                    getattr(self, "metadata", {})
                )
                expanded_geometry_refreshed = (
                    raw_state.get("expanded_node_size") != expanded_node_size
                )
                raw_state["expanded_node_size"] = expanded_node_size
                expanded_geometry_refreshed = (
                    self._synchronize_picker_expanded_geometry_metadata(raw_state)
                    or expanded_geometry_refreshed
                )
                serialized_state_paths = {
                    field: _maya_scene_path_text(raw_state.get(field))
                    for field in (
                        "scene_draft_path",
                        "scene_request_path",
                        "scene_path",
                    )
                }
                # Drop malformed aggregate control/log text at the backend
                # boundary even when it arrived inside serialized widget state.
                # Keep each valid saved field intact because a saved draft may
                # legitimately differ from the last completed READ scene.
                raw_state.update(serialized_state_paths)
                state_scene_path = next(
                    (
                        serialized_state_paths[field]
                        for field in (
                            "scene_draft_path",
                            "scene_request_path",
                            "scene_path",
                        )
                        if serialized_state_paths[field]
                    ),
                    "",
                )
                serialized_parameter_path = _maya_scene_path_text(
                    getattr(self, "_hmb_serialized_maya_scene_path", "")
                )
                restored_scene_path = state_scene_path or serialized_parameter_path
                if restored_scene_path:
                    # A saved widget snapshot is authoritative when present.
                    # Older workflows that serialized only MAYA_SCENE receive
                    # the same non-executing LOAD-ready draft on migration.
                    if not state_scene_path:
                        raw_state.update({
                            "scene_draft_path": restored_scene_path,
                            "scene_request_path": restored_scene_path,
                            "scene_stage": "LOAD_READY",
                            "scene_request_status": "COMPLETE",
                            "status": "READY",
                            "message": (
                                "Restored the saved Maya scene selection. "
                                "Press READ to load it."
                            ),
                        })
                    self._store_initial_parameter_value(
                        "MAYA_SCENE", restored_scene_path
                    )
                else:
                    # Never consult or retain an unproven native/global bridge
                    # value while adopting a path-free serialized workflow.
                    self._store_initial_parameter_value("MAYA_SCENE", "")
                previous_runtime_id = _clean(raw_state.get("runtime_instance_id"))
                raw_state, recovered = _recover_orphaned_runtime_state(raw_state)
                needs_publication = (
                    recovered
                    or media_urls_refreshed
                    or expanded_geometry_refreshed
                    or previous_runtime_id != self._hmb_runtime_instance_id
                )
                if needs_publication:
                    raw_state["python_core_loaded"] = True
                    raw_state["python_core_path"] = str(Path(__file__).resolve()).replace("\\", "/")
                    raw_state["runtime_instance_id"] = self._hmb_runtime_instance_id
                    raw_state["state_writer"] = "python"
                    raw_state["state_published_at_ms"] = int(time.time() * 1000)
                self._hmb_authoritative_state = dict(raw_state)
                self._hmb_latest_widget_state = dict(raw_state)
                self._hmb_state_revision = int(raw_state.get("state_revision") or 0)
                # initial_setup bypasses after_value_set(), so no deferred
                # restored-state revision may remain after this direct adopt.
                self._hmb_restored_state_pending_revision = -1
                self._hmb_thumbnail_serialized_adoption_complete = True
                if needs_publication:
                    self._write_state(raw_state)
            self._ensure_parameters()
            state = self._apply_selected_view_fields(self._picker_state())
            self._sync_outputs_from_state(state)
            if adopt_serialized:
                # Never decode up to 50 restored videos on the retained-mode
                # hydration path. The daemon performs a single batched state
                # merge after the saved state is visible and interactive.
                self._schedule_missing_video_thumbnail_recovery()
        except Exception as exc:
            _diagnostic_exception("Dynamic state restore failed", exc)

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            parent_hook = getattr(super(), "after_deserialize", None)
            if callable(parent_hook):
                result = parent_hook(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent after_deserialize hook failed", exc)
        self._restore_dynamic_state(adopt_serialized=True)
        self._schedule_post_hydration_shot_reconcile()
        return result

    def after_load(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            parent_hook = getattr(super(), "after_load", None)
            if callable(parent_hook):
                result = parent_hook(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent after_load hook failed", exc)
        self._restore_dynamic_state(adopt_serialized=True)
        self._schedule_post_hydration_shot_reconcile()
        return result

    def on_loaded(self, *args: Any, **kwargs: Any) -> Any:
        result = None
        try:
            parent_hook = getattr(super(), "on_loaded", None)
            if callable(parent_hook):
                result = parent_hook(*args, **kwargs)
        except Exception as exc:
            _diagnostic_exception("Parent on_loaded hook failed", exc)
        self._restore_dynamic_state(adopt_serialized=True)
        self._schedule_post_hydration_shot_reconcile()
        return result

    def _register_cleanup_file(self, path: Path) -> None:
        if path not in self._hmb_cleanup_files:
            self._hmb_cleanup_files.append(path)

    def _register_cleanup_dir(self, path: Path) -> None:
        if path not in self._hmb_cleanup_dirs:
            self._hmb_cleanup_dirs.append(path)

    def _cleanup_transient_paths(self) -> None:
        private_work_roots = {
            parent
            for path in (*self._hmb_cleanup_files, *self._hmb_cleanup_dirs)
            for parent in (path, *path.parents)
            if parent.name == ".hmb_video_picker"
        }
        for path in reversed(self._hmb_cleanup_files):
            try:
                _assert_safe_private_path(path).unlink(missing_ok=True)
            except Exception as exc:
                _diagnostic_exception(f"Transient file cleanup failed for {path}", exc)
        for path in sorted(self._hmb_cleanup_dirs, key=lambda item: len(item.parts), reverse=True):
            try:
                if path.is_dir():
                    _safe_remove_private_tree(path)
            except Exception as exc:
                _diagnostic_exception(f"Transient directory cleanup failed for {path}", exc)
        # Job folders are transient.  Remove their private parent only when it
        # is empty; persistent snapshots/dependency manifests and concurrent
        # Picker jobs therefore remain untouched.
        for path in sorted(private_work_roots, key=lambda item: len(item.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass
        self._hmb_cleanup_files.clear()
        self._hmb_cleanup_dirs.clear()

    def _publish_outputs(
        self,
        state: Dict[str, Any],
        video_slot: int,
        *,
        publish_public: bool = True,
        picker_shot_uuid: Any = "",
    ) -> str:
        run_id = str(time.time_ns())
        markers = _normalize_markers(state.get("markers"), video_slot)
        selected_slot = max(
            1,
            min(
                int(state.get("active_slot_count") or 1),
                int(state.get("selected_video_slot") or video_slot),
            ),
        )
        state["run_id"] = run_id
        state["markers"] = markers
        new_video = {
            "video_slot": video_slot,
            "video_path": _clean(state.get("video_path")),
            "project_video_path": _clean(state.get("project_video_path")),
            "video_metadata": dict(state.get("video_metadata") or {}),
            "video_url": _clean(state.get("video_url")),
            "camera": _clean(state.get("camera")),
            "markers": markers,
            "source_fps": float(state.get("source_fps") or 0.0),
            "output_fps": float(state.get("output_fps") or OUTPUT_FPS),
            "output_width": int(state.get("output_width") or OUTPUT_WIDTH),
            "output_height": int(state.get("output_height") or OUTPUT_HEIGHT),
            "source_frame_count": int(state.get("source_frame_count") or 0),
            "output_frame_count": int(state.get("output_frame_count") or 0),
            "decoded_frame_count": int(
                state.get("decoded_frame_count")
                or state.get("output_frame_count")
                or state.get("source_frame_count")
                or 0
            ),
            "source_duration_seconds": float(state.get("source_duration_seconds") or 0.0),
            "output_duration_seconds": float(state.get("output_duration_seconds") or 0.0),
            "start_frame": float(state.get("start_frame") or 0.0),
            "end_frame": float(state.get("end_frame") or 0.0),
            "has_maya_frame_range": bool(
                state.get("has_maya_frame_range")
                or state.get("native_read_ready")
            ),
            "run_id": run_id,
            "pair_run_id": _clean(state.get("pair_run_id")),
            "bundle_run_id": _clean(state.get("bundle_run_id")),
            "generation_role": "mask",
            "media_kind": MASK_MEDIA_KIND,
            "video_role": "maya_color_assignment_mask",
            "source_type_hint": "Color Assignment Mask / Segmentation Reference",
            "control_role_hint": "Object and Character Region Guidance",
            "label": "Mask",
        }
        state = _append_video_asset(
            state,
            new_video,
            picker_shot_uuid=picker_shot_uuid,
        )
        videos = [
            item for item in state.get("videos", []) if isinstance(item, dict)
        ]
        frame_warnings: List[str] = []
        for item in videos:
            slot = max(1, min(MAX_VIDEO_SLOTS, int(item.get("video_slot") or 1)))
            metadata = _video_frame_metadata(item, slot)
            item["frame_metadata"] = metadata
            frame_warnings.extend(
                f"[FRAME METADATA @video{slot}] {warning}"
                for warning in metadata.get("warnings", [])
            )
        existing_warnings = [
            _clean(item)
            for item in state.get("warnings", [])
            if _clean(item) and not _clean(item).startswith("[FRAME METADATA @video")
        ]
        state["warnings"] = existing_warnings + frame_warnings
        state["selected_video_slot"] = selected_slot
        state = self._apply_selected_view_fields(state)
        self._write_state(state)
        if publish_public:
            return self._sync_outputs_from_state(state)
        return ""

    @staticmethod
    def _maya_console_level(line: str) -> str:
        lowered = _clean(line).lower()
        if any(token in lowered for token in ("traceback", "fatal", "error:", "[error]", "exception")):
            return "ERROR"
        if any(token in lowered for token in ("warning", "// warning", "[warn]")):
            return "WARNING"
        return "INFO"

    @staticmethod
    def _clean_console_line(line: Any) -> str:
        text = str(line or "").replace("\r", "").rstrip("\n")
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        text = "".join(character for character in text if character == "\t" or ord(character) >= 32)
        return text[-6000:]

    def _wait_for_process_with_progress(
        self,
        process: subprocess.Popen[Any],
        progress_path: Path,
        overall_timeout: float,
        stall_timeout: float,
        operation_label: str,
        output_queue: Optional[Any] = None,
        output_log_handle: Any = None,
        output_reader: Optional[threading.Thread] = None,
        activity_paths: Optional[Sequence[Path]] = None,
        process_name: str = "Maya",
    ) -> int:
        """Wait while streaming an external process and progress into the UI."""
        process_label = _clean(process_name) or "External"
        started = time.monotonic()
        last_progress_at = started
        last_signature = ""
        last_stage = f"{process_label} startup"
        last_heartbeat_at = started
        stream_eof = False
        last_ui_publish_at = 0.0
        pending_ui_lines: List[tuple[str, str]] = []
        watched_activity_paths = tuple(Path(path) for path in (activity_paths or ()))
        activity_signature, _activity_count, _activity_size = _filesystem_activity_snapshot(
            watched_activity_paths
        )
        last_activity_scan_at = started
        activity_quiet_seconds = max(
            0.0,
            float(stall_timeout) * PROCESS_OUTPUT_ACTIVITY_QUIET_FRACTION,
        )
        activity_scan_interval = min(
            PROCESS_OUTPUT_ACTIVITY_SCAN_INTERVAL_SECONDS,
            max(0.05, float(stall_timeout) * 0.1),
        )

        def publish_runtime_ui(message: str = "", force: bool = False) -> None:
            nonlocal last_ui_publish_at, pending_ui_lines
            now = time.monotonic()
            if not force and now - last_ui_publish_at < 4.0:
                return
            if not pending_ui_lines and not message:
                return
            state = self._picker_state()
            if message:
                state["message"] = message
            for level, text in pending_ui_lines[-24:]:
                _append_activity_log(state, level, text)
            pending_ui_lines = []
            self._write_state(state)
            last_ui_publish_at = now

        def drain_console() -> bool:
            nonlocal last_progress_at, last_stage, stream_eof
            if output_queue is None:
                return False
            lines: List[str] = []
            while len(lines) < 120:
                try:
                    raw = output_queue.get_nowait()
                except queue.Empty:
                    break
                if raw is None:
                    stream_eof = True
                    continue
                text = self._clean_console_line(raw)
                if text:
                    lines.append(text)
            if not lines:
                return False
            now = time.monotonic()
            last_progress_at = now
            last_stage = lines[-1]
            for text in lines:
                if output_log_handle is not None:
                    try:
                        output_log_handle.write(text + "\n")
                    except Exception as exc:
                        _diagnostic_exception(
                            f"{process_label} console log write failed",
                            exc,
                        )
                pending_ui_lines.append((
                    self._maya_console_level(text),
                    f"{process_label.upper()} | {text}",
                ))
            if output_log_handle is not None:
                try:
                    output_log_handle.flush()
                except Exception as exc:
                    _diagnostic_exception(f"{process_label} console log flush failed", exc)
            publish_runtime_ui(lines[-1])
            return True

        def completed_return_code() -> Optional[int]:
            return_code = process.poll()
            if return_code is None:
                return None
            if output_reader is not None:
                try:
                    output_reader.join(timeout=1.5)
                except Exception as exc:
                    _diagnostic_exception(f"{process_label} console reader join failed", exc)
            for _index in range(20):
                changed = drain_console()
                if stream_eof or not changed:
                    break
                time.sleep(0.02)
            publish_runtime_ui(last_stage, force=True)
            return int(return_code)

        while True:
            if self._hmb_cancel_requested.is_set():
                _terminate_process(process)
                raise RuntimeError(f"{operation_label} cancelled by user.")
            console_changed = drain_console()
            now = time.monotonic()
            try:
                payload = _read_json(progress_path)
                signature = _progress_signature(payload)
                if signature != last_signature:
                    last_signature = signature
                    last_progress_at = now
                    stage = _clean(payload.get("stage")) or "external_progress"
                    message = _clean(payload.get("message")) or stage
                    last_stage = message
                    pending_ui_lines.append((
                        "INFO",
                        f"{process_label.upper()} PROGRESS [{stage}] | {message}",
                    ))
                    publish_runtime_ui(message)
            except (FileNotFoundError, PermissionError, json.JSONDecodeError, ValueError):
                pass
            except Exception as exc:
                _diagnostic_exception(f"{process_label} progress read failed", exc)
            if (
                watched_activity_paths
                and now - last_progress_at >= activity_quiet_seconds
                and now - last_activity_scan_at >= activity_scan_interval
            ):
                last_activity_scan_at = now
                next_signature, activity_file_count, activity_size = _filesystem_activity_snapshot(
                    watched_activity_paths
                )
                if next_signature != activity_signature:
                    activity_signature = next_signature
                    last_progress_at = now
                    last_stage = (
                        f"{process_label} output activity detected "
                        f"({activity_file_count} completed file(s), {activity_size} byte(s))"
                    )
                    pending_ui_lines.append((
                        "INFO",
                        f"{process_label.upper()} OUTPUT | {last_stage}",
                    ))
                    publish_runtime_ui(last_stage)
            if self._hmb_cancel_requested.is_set():
                _terminate_process(process)
                raise RuntimeError(f"{operation_label} cancelled by user.")
            return_code = completed_return_code()
            if return_code is not None:
                return return_code
            if now - last_heartbeat_at >= 10.0:
                last_heartbeat_at = now
                elapsed = now - started
                pending_ui_lines.append((
                    "INFO",
                    f"{process_label.upper()} | [heartbeat] process running for "
                    f"{elapsed:.1f}s; last activity: {last_stage}",
                ))
                publish_runtime_ui(last_stage, force=True)
            if now - started > overall_timeout:
                return_code = completed_return_code()
                if return_code is not None:
                    return return_code
                _terminate_process(process)
                raise TimeoutError(f"{operation_label} exceeded {int(overall_timeout)} seconds. Last stage: {last_stage}")
            if now - last_progress_at > stall_timeout:
                return_code = completed_return_code()
                if return_code is not None:
                    return return_code
                _terminate_process(process)
                raise TimeoutError(f"{operation_label} made no progress for {int(stall_timeout)} seconds. Last stage: {last_stage}")
            if not console_changed:
                time.sleep(0.1)

    def _read_scene_mode(
        self,
        scene_text: str,
        context: Optional[_OperationContext] = None,
    ) -> Dict[str, Any]:
        self._assert_operation_current(context, "READ preflight")
        if self._hmb_cancel_requested.is_set():
            raise RuntimeError("Maya Outliner READ cancelled by user.")
        strict_scene_text = _maya_scene_path_text(scene_text)
        if not strict_scene_text:
            raise ValueError("MAYA_SCENE is required before READ.")
        scene_path = _norm_path(strict_scene_text)
        if not scene_path.is_file():
            raise FileNotFoundError(f"Maya scene not found: {scene_path}")
        if scene_path.suffix.lower() not in {".ma", ".mb"}:
            raise ValueError(f"MAYA_SCENE must be .mb or .ma: {scene_path}")
        if not MAYA_RUNNER.is_file():
            raise FileNotFoundError(f"Maya runner not found: {MAYA_RUNNER}")
        mayabatch = _find_mayabatch()
        if mayabatch is None:
            raise FileNotFoundError("No mayabatch installation was found. Install Maya or set MAYA_LOCATION/PATH.")
        maya_version = _maya_display_version(mayabatch)
        if self._hmb_cancel_requested.is_set():
            raise RuntimeError("Maya Outliner READ cancelled by user.")

        state = self._picker_state()
        output_width, output_height = _playblast_resolution(state)
        _append_activity_log(state, "INFO", f"Stage 3/5: Validating scene file, Maya runner, and Maya {maya_version} installation.")
        _append_activity_log(state, "SUCCESS", f"Preflight passed: {scene_path.name}. Selected Maya {maya_version}: {mayabatch}")
        state.update({
            "status": "READING_SCENE",
            "scene_stage": "MAYA_READING",
            "message": f"Maya {maya_version} is starting the Outliner scan.",
            "maya_executable": str(mayabatch).replace("\\", "/"),
            "maya_version": maya_version,
            "pending_action": "",
            "scene_path": str(scene_path).replace("\\", "/"),
            "workspace_view": "outliner",
            "warnings": [],
        })
        # The accepted READ state was already published by _start_ui_operation.

        output_folder = _ensure_scene_output_folder(scene_path)
        token = hashlib.sha1(f"scan|{scene_path}|{time.time_ns()}".encode("utf-8")).hexdigest()[:12]
        job_folder = output_folder / ".hmb_video_picker" / f"read_{token}"
        job_path = job_folder / "read.job.json"
        result_path = job_folder / "read.result.json"
        progress_path = job_folder / "read.progress.json"
        log_path = output_folder / f"Read_{_safe_scene_name(scene_path.stem)}.log"
        self._register_cleanup_dir(job_folder)
        self._register_cleanup_file(job_path)
        self._register_cleanup_file(result_path)
        self._register_cleanup_file(progress_path)
        self._register_cleanup_file(Path(str(progress_path) + ".tmp"))
        _ensure_private_job_folder(job_folder, output_folder)
        _write_json(job_path, {
            "operation": "scan",
            "scene_path": str(scene_path),
            "result_path": str(result_path),
            "progress_path": str(progress_path),
            "generate_original_video": False,
            "camera": _clean(state.get("selected_camera")),
            "expected_maya_major": maya_version if maya_version.isdigit() else "",
        })

        command: List[str] = [str(mayabatch)]
        maya_project = _find_maya_project(scene_path)
        if maya_project is not None:
            command.extend(["-proj", str(maya_project)])
        command.extend([
            "-command", _maya_runner_command(),
        ])

        state = self._picker_state()
        state.update({
            "status": "READING_SCENE",
            "scene_stage": "MAYA_READING",
            "message": f"Maya {maya_version} is reading scene metadata, cameras, frame range, and the Outliner.",
            "pending_action": "",
            "scene_path": str(scene_path).replace("\\", "/"),
            "workspace_view": "outliner",
            "warnings": [],
            "maya_executable": str(mayabatch).replace("\\", "/"),
            "maya_version": maya_version,
            "last_log_path": str(log_path).replace("\\", "/"),
            "log_folder": str(output_folder).replace("\\", "/"),
        })
        scene_info = _inspect_maya_scene_file(scene_path)
        _append_activity_log(state, "INFO", f"Scene preflight: {scene_info.get('size_mb', 0):.1f} MB" + (f", saved by Maya {scene_info.get('source_version')}" if scene_info.get("source_version") else ""))
        plugin_hints = list(scene_info.get("plugin_hints") or [])
        if plugin_hints:
            _append_activity_log(state, "INFO", "Scene contains plugin node hints: " + ", ".join(plugin_hints) + ". Script nodes are disabled during READ.")
        _append_activity_log(state, "INFO", f"Stage 4/5: Launching Maya {maya_version} mayabatch and opening the scene safely.")
        _append_activity_log(
            state,
            "INFO",
            f"Maya {maya_version} metadata-only Outliner scan started. Diagnostic log: {log_path}",
        )
        self._write_state(state)

        env = _maya_subprocess_environment(job_path)
        if self._hmb_cancel_requested.is_set():
            raise RuntimeError("Maya Outliner READ cancelled by user.")
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            command_text = _command_text(command)
            log_handle.write("MAYA READ COMMAND\n" + command_text + "\n\n")
            log_handle.write(
                "MAYA VP2 DEVICE OVERRIDE\n"
                + (_clean(env.get("MAYA_VP2_DEVICE_OVERRIDE")) or "user preference")
                + "\n\n"
            )
            log_handle.flush()
            state = self._picker_state()
            _append_activity_log(state, "INFO", f"MAYA CMD | working directory: {job_path.parent}")
            _append_activity_log(state, "INFO", f"MAYA CMD | executable: {mayabatch}")
            _append_activity_log(state, "INFO", f"MAYA CMD | command: {command_text}")
            _append_activity_log(state, "INFO", f"MAYA CMD | job: {job_path}")
            _append_activity_log(
                state,
                "INFO",
                "MAYA CMD | VP2 device override: "
                + (_clean(env.get("MAYA_VP2_DEVICE_OVERRIDE")) or "user preference"),
            )
            _append_activity_log(state, "INFO", "MAYA CMD | stdout and stderr streaming started.")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(job_path.parent),
                creationflags=_creation_flags(),
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self._register_active_process(process, "Maya")
            output_queue: Any = queue.Queue(maxsize=READ_STDOUT_QUEUE_MAX_LINES)

            def enqueue_output(value: Any) -> None:
                try:
                    output_queue.put_nowait(value)
                    return
                except queue.Full:
                    # Retain recent diagnostics without ever blocking Maya's
                    # stdout pipe on an unusually noisy plug-in.
                    try:
                        output_queue.get_nowait()
                    except queue.Empty:
                        pass
                try:
                    output_queue.put_nowait(value)
                except queue.Full:
                    pass

            def pump_maya_output() -> None:
                try:
                    stream = process.stdout
                    if stream is not None:
                        for line in iter(stream.readline, ""):
                            enqueue_output(line)
                except Exception as exc:
                    enqueue_output(f"[HMB STREAM ERROR] {exc}\n")
                finally:
                    enqueue_output(None)

            output_reader = threading.Thread(
                target=pump_maya_output,
                name="HMBVideoPicker-maya-cmd-stream",
                daemon=True,
            )
            output_reader.start()
            state = self._picker_state()
            _append_activity_log(state, "SUCCESS", f"Maya process launched with PID {process.pid}. STOP is active.")
            try:
                return_code = self._wait_for_process_with_progress(
                    process,
                    progress_path,
                    READ_OVERALL_TIMEOUT_SECONDS,
                    READ_STALL_TIMEOUT_SECONDS,
                    "Maya Outliner READ",
                    output_queue=output_queue,
                    output_log_handle=log_handle,
                    output_reader=output_reader,
                )
                log_handle.write(f"\nHMB MAYA PROCESS EXIT CODE: {return_code}\n")
                log_handle.flush()
            except Exception as wait_exc:
                log_handle.write(f"\nHMB MAYA WAIT ERROR: {_clean(wait_exc) or wait_exc.__class__.__name__}\n")
                log_handle.flush()
                raise
            finally:
                self._clear_active_process(process)
                try:
                    if process.stdout is not None:
                        process.stdout.close()
                except Exception as exc:
                    _diagnostic_exception("Maya process stdout close failed", exc)

        self._assert_operation_current(context, "READ Maya completion")
        state = self._picker_state()
        _append_activity_log(state, "INFO", f"Maya Outliner process finished with exit code {return_code}.")
        _append_activity_log(
            state,
            "INFO",
            "Stage 5/5: Validating Maya result JSON, Outliner groups, cameras, frames, and FPS.",
        )
        # Final result validation is published atomically below.

        if not result_path.is_file():
            raise RuntimeError(f"Maya did not write the Outliner result. Exit code={return_code}. See {log_path}")
        result = _read_json(result_path)
        if not result.get("ok"):
            raise RuntimeError(f"{_clean(result.get('error')) or 'Maya Outliner read failed.'} See {log_path}")
        if return_code not in (0, None):
            raise RuntimeError(f"Maya exited with code {return_code}. See {log_path}")

        self._assert_operation_current(context, "READ result validation")
        outliner_nodes = [dict(item) for item in result.get("outliner_nodes", []) if isinstance(item, dict)]
        cameras = [dict(item) for item in result.get("cameras", []) if isinstance(item, dict)]
        read_warnings = [_clean(item) for item in result.get("warnings", []) if _clean(item)]
        try:
            start_frame = float(result["start_frame"])
            end_frame = float(result["end_frame"])
            current_frame = float(result.get("current_frame", start_frame))
            source_fps = float(result["fps"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Maya returned incomplete frame/FPS data. See {log_path}") from exc
        if end_frame < start_frame:
            raise RuntimeError(f"Maya returned an invalid playback range: {start_frame:g} to {end_frame:g}. See {log_path}")
        if source_fps <= 0:
            raise RuntimeError(f"Maya returned an invalid FPS value: {source_fps:g}. See {log_path}")
        actual_maya_version = _clean(result.get("maya_version")) or maya_version
        source_frame_count = _maya_sequence_frame_count(start_frame, end_frame)
        source_duration = source_frame_count / source_fps
        dependency_paths = [
            _clean(item)
            for item in result.get("scene_dependency_paths", [])
            if _clean(item)
        ]
        scene_path_text = str(scene_path).replace("\\", "/")
        if _scene_path_key(scene_path_text) not in {
            _scene_path_key(item) for item in dependency_paths
        }:
            dependency_paths.append(scene_path_text)
        dependency_paths = sorted(
            set(dependency_paths),
            key=lambda item: item.casefold(),
        )
        dependency_summary = _dependency_paths_summary(dependency_paths)
        dependency_manifest_path = _scene_dependency_manifest_path(scene_path)
        _ensure_private_job_folder(dependency_manifest_path.parent, output_folder)
        _write_json(dependency_manifest_path, {
            "schema": ORIGINAL_DEPENDENCY_MANIFEST_SCHEMA,
            "version": ORIGINAL_DEPENDENCY_MANIFEST_VERSION,
            "scene_path": scene_path_text,
            "scene_fingerprint": _scene_fingerprint(scene_path),
            "paths": dependency_paths,
            **dependency_summary,
        })
        script_node_report = (
            dict(result.get("script_node_report"))
            if isinstance(result.get("script_node_report"), dict)
            else {}
        )
        native_metadata = {
            "schema": "hmb-maya-scene-read",
            "read_mode": "maya-batch-atomic",
            "scene_path": str(scene_path).replace("\\", "/"),
            "source_version": actual_maya_version,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "current_frame": current_frame,
            "fps": source_fps,
            "cameras": cameras,
            "camera_count": len(cameras),
            "outliner_group_count": len(outliner_nodes),
            "original_video_path": "",
            "preview_frame_count": 0,
            "dependency_manifest_path": str(dependency_manifest_path).replace("\\", "/"),
            "scene_dependency_fingerprint": dependency_summary["fingerprint"],
            "scene_dependency_path_count": dependency_summary["path_count"],
            "scene_dependency_file_count": dependency_summary["file_count"],
            "scene_dependency_missing_count": dependency_summary["missing_count"],
            "script_node_report": script_node_report,
        }
        root_paths = [
            _clean(item.get("full_path")) for item in outliner_nodes
            if not _clean(item.get("parent_path")) and _clean(item.get("full_path"))
        ]
        previous_state = self._picker_state()
        active_slot_count = max(1, min(MAX_VIDEO_SLOTS, int(previous_state.get("active_slot_count") or 1)))
        selected_video_slot = max(1, min(active_slot_count, int(previous_state.get("selected_video_slot") or 1)))
        valid_paths = {_clean(item.get("full_path")) for item in outliner_nodes if _clean(item.get("full_path"))}
        valid_uuids = {_clean(item.get("maya_uuid")) for item in outliner_nodes if _clean(item.get("maya_uuid"))}
        preserved_assignments: List[Dict[str, Any]] = []
        for slot_item in _normalize_slot_assignments(
            previous_state.get("slot_assignments"), active_slot_count, previous_state.get("videos")
        ):
            bindings = []
            for binding in slot_item.get("bindings", []):
                full_path = _clean(binding.get("full_dag_path"))
                maya_uuid = _clean(binding.get("maya_uuid"))
                if (full_path and full_path in valid_paths) or (maya_uuid and maya_uuid in valid_uuids):
                    bindings.append(dict(binding))
            preserved_assignments.append({"video_slot": int(slot_item.get("video_slot") or 1), "bindings": bindings})
        outliner_selection = _outliner_selection_after_read(
            outliner_nodes,
            preserved_assignments,
            selected_video_slot,
            previous_state.get("selected_outliner_path"),
            previous_state.get("selected_outliner_uuid"),
        )
        state = {
            **previous_state,
            "mode": "maya",
            "status": "OUTLINER_READY",
            "scene_stage": "OUTLINER_READY",
            "message": (
                f"Maya Outliner loaded with {len(outliner_nodes)} selectable asset roots. "
                "Enable Original Playblast when an unmodified viewport preview is needed."
            ),
            "scene_path": str(scene_path).replace("\\", "/"),
            "scene_draft_path": str(scene_path).replace("\\", "/"),
            "scene_request_path": str(scene_path).replace("\\", "/"),
            "scene_request_status": "COMPLETE",
            "native_read_ready": True,
            "native_read_mode": "maya-batch-atomic",
            "native_source_version": actual_maya_version,
            "native_metadata": native_metadata,
            "maya_executable": str(mayabatch).replace("\\", "/"),
            "maya_version": actual_maya_version,
            "last_log_path": str(log_path).replace("\\", "/"),
            "log_folder": str(output_folder).replace("\\", "/"),
            "camera": _clean(result.get("selected_camera")),
            "selected_camera": _clean(result.get("selected_camera")),
            "cameras": cameras,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "current_frame": current_frame,
            "has_maya_frame_range": True,
            "source_fps": source_fps,
            "output_fps": source_fps,
            "output_width": output_width,
            "output_height": output_height,
            "source_frame_count": source_frame_count,
            "source_duration_seconds": source_duration,
            "outliner_nodes": outliner_nodes,
            "outliner_expanded": root_paths,
            "selected_outliner_path": outliner_selection["path"],
            "selected_outliner_name": outliner_selection["name"],
            "selected_outliner_uuid": outliner_selection["uuid"],
            "selected_color": outliner_selection["color"],
            "workspace_view": "outliner",
            "active_slot_count": active_slot_count,
            "selected_video_slot": selected_video_slot,
            "videos": [dict(item) for item in previous_state.get("videos", []) if isinstance(item, dict)],
            "slot_assignments": preserved_assignments,
            "original_video_path": "",
            "original_video_url": "",
            "original_metadata": {},
            "original_preview_enabled": False,
            "video_path": "",
            "video_url": "",
            "snapshot_active": False,
            "snapshot_frame": current_frame,
            "snapshot_video_slot": 0,
            "snapshot_data_uri": "",
            "snapshot_path": "",
            "snapshot_url": "",
            "snapshot_sha256": "",
            "markers": [],
            "warnings": read_warnings,
            "pending_action": "",
            "outliner_search": "",
            "static_frame_range_valid": True,
            "static_camera_metadata_valid": bool(cameras),
            "static_metadata_complete": True,
        }
        state = self._mark_operation_finished(state)
        actual_camera_names = [
            _clean(item.get("name") or item.get("full_path"))
            for item in cameras
            if _clean(item.get("name") or item.get("full_path"))
        ]
        _append_activity_log(
            state,
            "INFO",
            f"Actual Maya frames: start {state['start_frame']:g}, current {state['current_frame']:g}, end {state['end_frame']:g}, FPS {state['source_fps']:g}.",
        )
        _append_activity_log(
            state,
            "INFO",
            f"Actual user cameras ({len(cameras)}): {', '.join(actual_camera_names) if actual_camera_names else 'none'}.",
        )
        _append_activity_log(
            state,
            "SUCCESS",
            f"READ completed with Maya {actual_maya_version}: {len(outliner_nodes)} asset roots, "
            f"{len(cameras)} user camera(s), {source_frame_count} timeline frame(s), "
            f"{active_slot_count} selected video(s) in {state.get('last_operation_seconds', 0.0):.1f} seconds.",
        )
        _append_activity_log(
            state,
            "INFO",
            "READ completed without rendering an original playblast. Original preview remains off until requested.",
        )
        _append_activity_log(state, "INFO", f"Diagnostic log saved: {log_path}")
        self._assert_operation_current(context, "READ atomic publish")
        self._write_state(state)
        self._sync_outputs_from_state(state)
        self._ensure_parameters()
        return {
            "mode": "scan",
            "scene": str(scene_path),
            "group_count": len(outliner_nodes),
            "camera_count": len(cameras),
            "original_video": "",
        }

    @staticmethod
    def _publish_original_preview_artifacts(
        staged_video_path: Path,
        staged_sidecar_path: Path,
        video_path: Path,
        sidecar_path: Path,
        job_folder: Path,
    ) -> tuple[bool, bool]:
        """Publish the validated pair and restore the prior pair on any failure."""
        previous_video = job_folder / "previous-original.mp4"
        previous_sidecar = job_folder / "previous-original.hmb.json"
        had_video = video_path.is_file()
        had_sidecar = sidecar_path.is_file()
        if had_video:
            shutil.copy2(video_path, previous_video)
        if had_sidecar:
            shutil.copy2(sidecar_path, previous_sidecar)
        try:
            os.replace(staged_video_path, video_path)
            os.replace(staged_sidecar_path, sidecar_path)
        except Exception:
            try:
                if had_video and previous_video.is_file():
                    os.replace(previous_video, video_path)
                elif video_path.exists():
                    video_path.unlink()
            except Exception as restore_exc:
                _diagnostic_exception("original preview video rollback failed", restore_exc)
            try:
                if had_sidecar and previous_sidecar.is_file():
                    os.replace(previous_sidecar, sidecar_path)
                elif sidecar_path.exists():
                    sidecar_path.unlink()
            except Exception as restore_exc:
                _diagnostic_exception("original preview sidecar rollback failed", restore_exc)
            raise
        return had_video, had_sidecar

    @staticmethod
    def _restore_original_preview_artifacts(
        video_path: Path,
        sidecar_path: Path,
        job_folder: Path,
        had_video: bool,
        had_sidecar: bool,
    ) -> None:
        """Restore the pair that existed before a successful atomic publish."""
        previous_video = job_folder / "previous-original.mp4"
        previous_sidecar = job_folder / "previous-original.hmb.json"
        restore_errors: List[str] = []
        try:
            if had_video and previous_video.is_file():
                os.replace(previous_video, video_path)
            elif video_path.exists():
                video_path.unlink()
        except Exception as exc:
            restore_errors.append(f"video: {exc}")
        try:
            if had_sidecar and previous_sidecar.is_file():
                os.replace(previous_sidecar, sidecar_path)
            elif sidecar_path.exists():
                sidecar_path.unlink()
        except Exception as exc:
            restore_errors.append(f"sidecar: {exc}")
        if restore_errors:
            raise RuntimeError(
                "Original preview rollback could not restore the previous artifact pair ("
                + "; ".join(restore_errors)
                + ")."
            )

    @staticmethod
    def _publish_playblast_bundle(
        staged_targets: Sequence[tuple[Path, Path]],
        backup_folder: Path,
    ) -> List[tuple[Path, Path, bool]]:
        """Atomically expose one validated artifact pair with rollback data."""
        backup_folder.mkdir(parents=True, exist_ok=True)
        records: List[tuple[Path, Path, bool]] = []
        for index, (_staged, target) in enumerate(staged_targets):
            backup = backup_folder / f"{index:02d}-{target.name}.previous"
            existed = target.is_file()
            if existed:
                shutil.copy2(target, backup)
            records.append((target, backup, existed))
        try:
            for staged, target in staged_targets:
                os.replace(staged, target)
        except Exception:
            HMBVideoPickerLibrary._restore_playblast_bundle(records)
            raise
        return records

    @staticmethod
    def _restore_playblast_bundle(
        records: Sequence[tuple[Path, Path, bool]],
    ) -> None:
        """Restore all previously published files, including absent targets."""
        restore_errors: List[str] = []
        for target, backup, existed in reversed(list(records)):
            try:
                if existed and backup.is_file():
                    os.replace(backup, target)
                elif target.exists():
                    target.unlink()
            except Exception as exc:
                restore_errors.append(f"{target.name}: {exc}")
        if restore_errors:
            raise RuntimeError(
                "Playblast bundle rollback could not restore every prior artifact ("
                + "; ".join(restore_errors)
                + ")."
            )

    @staticmethod
    def _publish_validated_playblast_artifact(
        *,
        staged_video: Path,
        staged_sidecar: Path,
        target_video: Path,
        target_sidecar: Path,
        backup_folder: Path,
        label: str,
    ) -> List[tuple[Path, Path, bool]]:
        """Publish one media/sidecar pair without coupling sibling artifacts."""
        if not _is_structurally_valid_mp4(staged_video):
            raise RuntimeError(f"The staged {label} MP4 failed structural validation.")
        if not staged_sidecar.is_file():
            raise RuntimeError(f"The staged {label} sidecar is missing.")
        records = HMBVideoPickerLibrary._publish_playblast_bundle(
            [
                (staged_video, target_video),
                (staged_sidecar, target_sidecar),
            ],
            backup_folder,
        )
        try:
            if (
                not _is_structurally_valid_mp4(target_video)
                or not target_sidecar.is_file()
            ):
                raise RuntimeError(f"Published {label} failed final validation.")
        except Exception:
            HMBVideoPickerLibrary._restore_playblast_bundle(records)
            raise
        return records

    def _render_original_preview_mode(
        self,
        scene_text: str,
        context: Optional[_OperationContext] = None,
        *,
        publish_public: bool = True,
    ) -> Dict[str, Any]:
        self._assert_operation_current(context, "ORIGINAL PREVIEW preflight")
        strict_scene_text = _maya_scene_path_text(scene_text)
        if not strict_scene_text:
            raise ValueError(
                "A single absolute Maya .mb or .ma scene is required before Original Preview."
            )
        scene_path = _norm_path(strict_scene_text)
        if not scene_path.is_file() or scene_path.suffix.lower() not in {".ma", ".mb"}:
            raise FileNotFoundError(f"Select an existing Maya .mb or .ma scene before Original Preview: {scene_path}")
        if not MAYA_RUNNER.is_file():
            raise FileNotFoundError(f"Maya runner not found: {MAYA_RUNNER}")

        state = self._picker_state()
        if not state.get("native_read_ready"):
            raise RuntimeError("Complete READ before generating the original preview.")
        native_metadata = (
            dict(state.get("native_metadata"))
            if isinstance(state.get("native_metadata"), dict)
            else {}
        )
        native_scene_text = _maya_scene_path_text(
            native_metadata.get("scene_path")
        )
        if (
            native_scene_text
            and _scene_path_key(native_scene_text) != _scene_path_key(scene_path)
        ):
            raise RuntimeError(
                "The completed READ metadata belongs to a different Maya scene. "
                "Run READ for the selected scene before generating Original."
        )
        cache_fields = _original_preview_cache_fields(scene_path, state)
        if not cache_fields.get("scene_dependency_complete"):
            raise RuntimeError(
                "Original Playblast requires the current dependency manifest. "
                "Run READ again for this Maya scene before enabling Original."
            )
        camera = _clean(cache_fields.get("camera"))
        start_frame = float(cache_fields.get("start_frame") or 0.0)
        end_frame = float(cache_fields.get("end_frame") or 0.0)
        source_fps = float(cache_fields.get("fps") or 0.0)
        output_width = int(cache_fields["resolution"]["width"])
        output_height = int(cache_fields["resolution"]["height"])
        if not camera:
            raise RuntimeError("A selected Maya camera is required for the original preview.")
        if end_frame < start_frame or source_fps <= 0.0:
            raise RuntimeError("READ metadata does not contain a valid frame range and FPS.")

        output_folder = _ensure_scene_output_folder(scene_path)
        video_path, sidecar_path = _original_preview_paths(scene_path)
        if _original_preview_cache_is_valid(scene_path, state, video_path, sidecar_path):
            state.update({
                "status": "VIDEO_READY" if state.get("videos") else "OUTLINER_READY",
                "scene_stage": "VIDEO_READY" if state.get("videos") else "OUTLINER_READY",
                "scene_request_status": "COMPLETE",
                "message": "Original preview loaded from the validated cache.",
                "original_video_path": str(video_path).replace("\\", "/"),
                "original_video_url": _external_media_url(video_path),
                "original_metadata": _original_view_metadata(
                    _read_json(sidecar_path)
                ),
                "original_preview_enabled": True,
                "workspace_view": "playblast",
            })
            if publish_public:
                state = self._mark_operation_finished(state)
            state = self._apply_selected_view_fields(state)
            _append_activity_log(
                state,
                "SUCCESS",
                f"Original preview cache became available before Maya launch and was loaded without a process: {video_path}",
            )
            self._write_state(state)
            if publish_public:
                self._sync_outputs_from_state(state)
            return {"mode": "original_preview_cache", "video": str(video_path), "cached": True}

        mayabatch = _find_mayabatch()
        if mayabatch is None:
            raise FileNotFoundError("No mayabatch installation was found. Install Maya or set MAYA_LOCATION/PATH.")
        maya_version = _maya_display_version(mayabatch)
        ffmpeg = _find_ffmpeg(mayabatch)
        if ffmpeg is None:
            raise FileNotFoundError(
                "FFmpeg was not found. Install imageio-ffmpeg, set FFMPEG_PATH explicitly, or place it beside mayabatch."
            )

        output_name = f"{_safe_scene_name(scene_path.stem)}_Orignal"
        token = hashlib.sha1(
            f"original|{scene_path}|{camera}|{time.time_ns()}".encode("utf-8")
        ).hexdigest()[:12]
        job_folder = output_folder / ".hmb_video_picker" / f"original_{token}"
        frames_folder = job_folder / "frames"
        job_path = job_folder / "original.job.json"
        result_path = job_folder / "original.result.json"
        progress_path = job_folder / "original.progress.json"
        staged_video_path = job_folder / "original.partial.mp4"
        staged_sidecar_path = job_folder / "original.partial.hmb.json"
        log_path = output_folder / f"{_safe_scene_name(scene_path.stem)}_Orignal.log"
        for transient in (
            job_folder,
            frames_folder,
        ):
            self._register_cleanup_dir(transient)
        for transient in (
            job_path,
            result_path,
            progress_path,
            Path(str(progress_path) + ".tmp"),
            staged_video_path,
            staged_sidecar_path,
            job_folder / "previous-original.mp4",
            job_folder / "previous-original.hmb.json",
        ):
            self._register_cleanup_file(transient)
        _ensure_private_job_folder(job_folder, output_folder)
        _write_json(job_path, {
            "operation": "render",
            "scene_path": str(scene_path),
            "output_name": output_name,
            "frames_folder": str(frames_folder),
            "sidecar_path": str(staged_sidecar_path),
            "result_path": str(result_path),
            "progress_path": str(progress_path),
            "camera": camera,
            "width": output_width,
            "height": output_height,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "fps": source_fps,
            "apply_marker_shaders": False,
            "apply_original_lambert_override": True,
            "original_material_override_profile": (
                ORIGINAL_MATERIAL_OVERRIDE_PROFILE
            ),
            "force_high_quality_viewport": True,
            "viewport_quality_profile": ORIGINAL_VIEWPORT_QUALITY_PROFILE,
            "mouth_card_inner_patch_policy": MOUTH_CARD_INNER_PATCH_POLICY,
            "require_full_smooth_geometry": True,
            "expected_maya_major": maya_version if maya_version.isdigit() else "",
            "video_container": "MPEG-4",
            "video_codec": "H.264",
            "ffmpeg_encoder": "libx264",
            "output_fps": source_fps,
        })

        command: List[str] = [str(mayabatch)]
        maya_project = _find_maya_project(scene_path)
        if maya_project is not None:
            command.extend(["-proj", str(maya_project)])
        command.extend([
            "-command", _maya_runner_command(),
        ])
        state.update({
            "status": "GENERATING_ORIGINAL",
            "scene_stage": "GENERATING_ORIGINAL",
            "message": f"Maya {maya_version} is rendering the on-demand original preview.",
            "original_preview_enabled": False,
            "maya_executable": str(mayabatch).replace("\\", "/"),
            "maya_version": maya_version,
            "last_log_path": str(log_path).replace("\\", "/"),
            "log_folder": str(output_folder).replace("\\", "/"),
        })
        state = self._apply_selected_view_fields(state)
        # _apply_selected_view_fields also projects a selected slot's media
        # metadata. Keep the accepted Original render resolution authoritative
        # while the unmodified preview is being generated.
        state["output_width"] = output_width
        state["output_height"] = output_height
        _append_activity_log(
            state,
            "INFO",
            (
                f"Original preview Maya render started with camera {camera}, frames "
                f"{start_frame:g}-{end_frame:g}, {source_fps:g} FPS, and forced "
                f"full-detail viewport profile {ORIGINAL_VIEWPORT_QUALITY_PROFILE} "
                "with a per-source-material Maya Lambert compatibility pass."
            ),
        )
        self._write_state(state)

        env = _maya_subprocess_environment(job_path)
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            log_handle.write("MAYA ORIGINAL PREVIEW COMMAND\n" + _command_text(command) + "\n\n")
            log_handle.write(
                "MAYA VP2 DEVICE OVERRIDE\n"
                + (_clean(env.get("MAYA_VP2_DEVICE_OVERRIDE")) or "user preference")
                + "\n\n"
            )
            log_handle.flush()
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(job_path.parent),
                creationflags=_creation_flags(),
            )
            self._register_active_process(process, "Maya")
            try:
                return_code = self._wait_for_process_with_progress(
                    process,
                    progress_path,
                    PLAYBLAST_OVERALL_TIMEOUT_SECONDS,
                    PLAYBLAST_STALL_TIMEOUT_SECONDS,
                    "Maya Original Preview",
                    activity_paths=(frames_folder,),
                )
            finally:
                self._clear_active_process(process)

        self._assert_operation_current(context, "ORIGINAL PREVIEW Maya completion")
        if not result_path.is_file():
            raise RuntimeError(f"Maya did not write the original preview result. Exit code={return_code}. See {log_path}")
        result = _read_json(result_path)
        if not result.get("ok") or return_code not in (0, None):
            raise RuntimeError(
                f"{_clean(result.get('error')) or f'Maya exited with code {return_code}.'} See {log_path}"
            )
        actual_frames_folder = Path(_clean(result.get("frames_folder")) or frames_folder)
        actual_sidecar_path = Path(_clean(result.get("sidecar_path")) or staged_sidecar_path)
        if _scene_path_key(actual_frames_folder) != _scene_path_key(frames_folder):
            raise RuntimeError(
                f"Maya returned an unexpected original preview frames folder. See {log_path}"
            )
        if _scene_path_key(actual_sidecar_path) != _scene_path_key(staged_sidecar_path):
            raise RuntimeError(
                f"Maya returned an unexpected original preview sidecar path. See {log_path}"
            )
        self._register_cleanup_dir(actual_frames_folder)
        result_fps = float(result.get("fps") or 0.0)
        frame_count = int(result.get("frame_count") or 0)
        if result_fps <= 0.0 or frame_count <= 0:
            raise RuntimeError(f"Maya did not provide valid original preview frames or FPS. See {log_path}")
        if abs(result_fps - source_fps) > 1e-6:
            raise RuntimeError(
                f"Maya returned {result_fps:g} FPS for an original preview requested at {source_fps:g} FPS. See {log_path}"
            )
        if not actual_sidecar_path.is_file():
            raise RuntimeError(f"Maya did not create the original preview sidecar. See {log_path}")
        runner_sidecar = _read_json(actual_sidecar_path)
        _validate_full_smooth_confirmation(
            result,
            runner_sidecar,
            label="Original Playblast",
        )
        expected_frame_count = _maya_sequence_frame_count(start_frame, end_frame)
        runner_resolution = (
            dict(runner_sidecar.get("resolution"))
            if isinstance(runner_sidecar.get("resolution"), dict)
            else {}
        )
        runner_dependency_paths = [
            _clean(item)
            for item in runner_sidecar.get("scene_dependency_paths", [])
            if _clean(item)
        ]
        runner_dependency_summary = _dependency_paths_summary(runner_dependency_paths)
        runner_script_report = (
            dict(runner_sidecar.get("script_node_report"))
            if isinstance(runner_sidecar.get("script_node_report"), dict)
            else {}
        )
        validation_errors = []
        if _scene_path_key(runner_sidecar.get("scene_path")) != _scene_path_key(scene_path):
            validation_errors.append("scene path")
        if _clean(runner_sidecar.get("camera")) != camera:
            validation_errors.append("camera")
        for label, actual, expected in (
            ("start frame", runner_sidecar.get("start_frame"), start_frame),
            ("end frame", runner_sidecar.get("end_frame"), end_frame),
            ("FPS", runner_sidecar.get("fps"), source_fps),
        ):
            try:
                if abs(float(actual) - float(expected)) > 1e-6:
                    validation_errors.append(label)
            except (TypeError, ValueError):
                validation_errors.append(label)
        if frame_count != expected_frame_count:
            validation_errors.append("result frame count")
        if int(runner_sidecar.get("frame_count") or 0) != expected_frame_count:
            validation_errors.append("sidecar frame count")
        if int(runner_resolution.get("width") or 0) != output_width:
            validation_errors.append("width")
        if int(runner_resolution.get("height") or 0) != output_height:
            validation_errors.append("height")
        if (
            _clean(runner_sidecar.get("assignment_mode"))
            != ORIGINAL_LAMBERT_ASSIGNMENT_MODE
        ):
            validation_errors.append("assignment mode")
        if (
            _clean(runner_sidecar.get("original_material_override_profile"))
            != ORIGINAL_MATERIAL_OVERRIDE_PROFILE
        ):
            validation_errors.append("Original Lambert material profile")
        runner_material_report = (
            dict(runner_sidecar.get("original_material_override_report"))
            if isinstance(
                runner_sidecar.get("original_material_override_report"), dict
            )
            else {}
        )
        if not _original_material_report_is_valid(runner_material_report):
            validation_errors.append("Original Lambert restoration report")
        if list(runner_sidecar.get("markers") or []):
            validation_errors.append("marker isolation")
        if not runner_dependency_paths:
            validation_errors.append("dependency manifest")
        fresh_read_dependency = _current_scene_dependency_summary(
            scene_path,
            native_metadata,
        )
        if (
            not fresh_read_dependency["complete"]
            or fresh_read_dependency["fingerprint"]
            != cache_fields["scene_dependency_fingerprint"]
        ):
            validation_errors.append("accepted READ dependency fingerprint")
        if not runner_script_report:
            validation_errors.append("script-node safety report")
        elif int(runner_script_report.get("disabled_count") or 0) != int(
            runner_script_report.get("script_node_count") or 0
        ):
            validation_errors.append("script-node neutralization")
        if validation_errors:
            raise RuntimeError(
                "Maya Original output did not match the accepted READ request "
                f"({', '.join(validation_errors)}). Run READ again. See {log_path}"
            )

        self._assert_operation_current(context, "ORIGINAL PREVIEW frame validation")
        ffmpeg_command = _build_ffmpeg_encode_command(
            ffmpeg=ffmpeg,
            frame_pattern=actual_frames_folder / f"{output_name}.%06d.png",
            output_path=staged_video_path,
            source_fps=source_fps,
            frame_count=frame_count,
            width=output_width,
            height=output_height,
        )
        state = self._picker_state()
        _append_activity_log(
            state,
            "INFO",
            (
                "Encoding the on-demand original preview with the high-quality "
                f"BT.709 H.264 profile at the exact Maya rate {source_fps:g} FPS."
            ),
        )
        self._write_state(state)
        with log_path.open("a", encoding="utf-8", errors="replace") as log_handle:
            log_handle.write("\nFFMPEG ORIGINAL PREVIEW COMMAND\n" + _command_text(ffmpeg_command) + "\n\n")
            log_handle.flush()
            ffmpeg_process = subprocess.Popen(
                ffmpeg_command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                cwd=str(output_folder),
                creationflags=_creation_flags(),
            )
            self._register_active_process(ffmpeg_process, "FFmpeg")
            try:
                ffmpeg_return_code = ffmpeg_process.wait(timeout=PLAYBLAST_OVERALL_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                _terminate_process(ffmpeg_process)
                raise TimeoutError(f"Original preview FFmpeg encoding exceeded {PLAYBLAST_OVERALL_TIMEOUT_SECONDS} seconds. See {log_path}")
            finally:
                self._clear_active_process(ffmpeg_process)
        if (
            ffmpeg_return_code != 0
            or not staged_video_path.is_file()
            or not _is_structurally_valid_mp4(staged_video_path)
        ):
            raise RuntimeError(f"Original preview H.264 encoding failed. See {log_path}")

        warnings = [_clean(item) for item in runner_sidecar.get("warnings", []) if _clean(item)]
        viewport_quality_report = (
            dict(runner_sidecar.get("viewport_quality_report"))
            if isinstance(runner_sidecar.get("viewport_quality_report"), dict)
            else {}
        )
        original_metadata = {
            "schema": "hmb-original-playblast",
            **cache_fields,
            "video": video_path.name,
            "video_path": str(video_path).replace("\\", "/"),
            "video_size_bytes": int(staged_video_path.stat().st_size),
            "accepted_read_dependency_fingerprint": cache_fields[
                "scene_dependency_fingerprint"
            ],
            "scene_dependency_complete": True,
            "scene_dependency_fingerprint": runner_dependency_summary["fingerprint"],
            "scene_dependency_path_count": runner_dependency_summary["path_count"],
            "scene_dependency_file_count": runner_dependency_summary["file_count"],
            "scene_dependency_missing_count": runner_dependency_summary["missing_count"],
            "scene_dependency_paths": runner_dependency_paths,
            "maya_version": maya_version,
            "frame_count": frame_count,
            "source_duration_seconds": frame_count / source_fps,
            "marker_shaders": False,
            "assignment_mode": ORIGINAL_LAMBERT_ASSIGNMENT_MODE,
            "original_material_override_report": runner_material_report,
            "render_method": _clean(runner_sidecar.get("render_method")) or "Viewport 2.0 OGS",
            "viewport_quality_report": viewport_quality_report,
            "duration_policy": "exact_source_timing",
            "warnings": warnings,
            "video_format": {
                "container": "MPEG-4",
                "codec": "H.264",
                "encoder": "libx264",
                "pixel_format": "yuv420p",
                "profile": PROXY_H264_PROFILE,
                "level": PROXY_H264_LEVEL,
                "preset": PROXY_ENCODER_PRESET,
                "crf": PROXY_ENCODER_CRF,
                "color_range": "tv",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
                "frame_rate": _fps_timebase(source_fps),
                "track_timescale": _video_track_timescale(source_fps),
                "gop_frames": max(1, int(round(source_fps))),
                "fps_mode": "passthrough",
            },
        }
        _write_json(actual_sidecar_path, original_metadata)

        self._assert_operation_current(context, "ORIGINAL PREVIEW atomic publish")
        if not _original_preview_cache_is_valid(
            scene_path,
            state,
            staged_video_path,
            actual_sidecar_path,
        ):
            raise RuntimeError(
                "The staged original preview failed cache validation before publish."
            )
        with _original_publish_guard(scene_path):
            if _original_preview_cache_is_valid(
                scene_path,
                state,
                video_path,
                sidecar_path,
            ):
                # A concurrent Picker finished the exact same accepted request.
                # Reuse its validated pair instead of replacing it.
                self._assert_operation_current(
                    context,
                    "ORIGINAL PREVIEW concurrent-cache validation",
                )
                original_metadata = _read_json(sidecar_path)
                warnings = [
                    _clean(item)
                    for item in original_metadata.get("warnings", [])
                    if _clean(item)
                ]
            else:
                had_video, had_sidecar = self._publish_original_preview_artifacts(
                    staged_video_path,
                    actual_sidecar_path,
                    video_path,
                    sidecar_path,
                    job_folder,
                )
                try:
                    # Validate against the immutable READ metadata used to render,
                    # then reject a result whose live inputs changed before it can
                    # become active.
                    if not _original_preview_cache_is_valid(
                        scene_path,
                        state,
                        video_path,
                        sidecar_path,
                    ):
                        raise RuntimeError(
                            "Published original preview failed its final cache validation."
                        )
                    self._assert_operation_current(
                        context,
                        "ORIGINAL PREVIEW post-publish validation",
                    )
                except Exception:
                    self._restore_original_preview_artifacts(
                        video_path,
                        sidecar_path,
                        job_folder,
                        had_video,
                        had_sidecar,
                    )
                    raise

        state = self._picker_state()
        ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
        merged_warnings = [_clean(item) for item in state.get("warnings", []) if _clean(item)]
        for warning in warnings:
            if warning not in merged_warnings:
                merged_warnings.append(warning)
        state.update({
            "status": ready_stage,
            "scene_stage": ready_stage,
            "scene_request_status": "COMPLETE",
            "message": f"Original preview ready: {frame_count} frames at {source_fps:g} FPS.",
            "original_video_path": str(video_path).replace("\\", "/"),
            "original_video_url": _external_media_url(video_path),
            "original_metadata": _original_view_metadata(original_metadata),
            "original_preview_enabled": True,
            "workspace_view": "playblast",
            "warnings": merged_warnings[-20:],
        })
        if publish_public:
            state = self._mark_operation_finished(state)
        state = self._apply_selected_view_fields(state)
        _append_activity_log(
            state,
            "SUCCESS",
            f"Original preview published atomically with {frame_count} frame(s) in {state.get('last_operation_seconds', 0.0):.1f} seconds: {video_path}",
        )
        self._write_state(state)
        if publish_public:
            self._sync_outputs_from_state(state)
        return {
            "mode": "original_preview",
            "video": str(video_path),
            "json": str(sidecar_path),
            "cached": False,
            "frame_count": frame_count,
            "fps": source_fps,
        }

    @staticmethod
    def _snapshot_cache_root(scene_path: Path) -> Path:
        output_folder = _ensure_scene_output_folder(scene_path)
        return _ensure_private_job_folder(
            output_folder / ".hmb_video_picker",
            output_folder,
        )

    @staticmethod
    def _snapshot_cache_path(scene_path: Path, snapshot_uid: Any) -> Path:
        uid = _clean(snapshot_uid)
        if not uid:
            raise ValueError("Snapshot cache creation requires snapshot_uid.")
        private_root = HMBVideoPickerLibrary._snapshot_cache_root(scene_path)
        readable_uid = re.sub(r"[^A-Za-z0-9_-]+", "_", uid).strip("_-")
        readable_uid = (readable_uid or "snapshot")[:48]
        uid_digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()[:12]
        return private_root / f"snapshot_{readable_uid}_{uid_digest}.png"

    @staticmethod
    def _legacy_snapshot_cache_path(scene_path: Path, video_slot: int) -> Path:
        slot = max(1, min(MAX_VIDEO_SLOTS, int(video_slot)))
        return (
            _scene_output_folder(scene_path)
            / ".hmb_video_picker"
            / f"snapshot_video{slot}.png"
        )

    def _clear_snapshot_cache(
        self,
        state: Dict[str, Any],
        scene_path: Optional[Path],
        video_slot: int = PRIMARY_COLOR_VIDEO_SLOT,
        *,
        snapshot_uid: Any = "",
        delete_all_for_slot: bool = True,
    ) -> Dict[str, Any]:
        state = _parse_state(state)
        slot = max(1, min(MAX_VIDEO_SLOTS, int(video_slot)))
        history = [
            dict(item)
            for item in state.get("snapshots", [])
            if isinstance(item, dict) and _clean(item.get("snapshot_uid"))
        ]
        requested_uid = _clean(snapshot_uid)
        target_indexes: List[int] = []
        if requested_uid:
            target_indexes = [
                index
                for index, item in enumerate(history)
                if _clean(item.get("snapshot_uid")) == requested_uid
            ]
        else:
            slot_indexes = [
                index
                for index, item in enumerate(history)
                if _normalized_video_slot(
                    item.get("render_video_slot") or item.get("video_slot"),
                    PRIMARY_COLOR_VIDEO_SLOT,
                ) == slot
            ]
            if delete_all_for_slot:
                target_indexes = slot_indexes
            elif slot_indexes:
                active_uid = _clean(state.get("active_snapshot_uid"))
                active_index = next(
                    (
                        index for index in slot_indexes
                        if _clean(history[index].get("snapshot_uid")) == active_uid
                    ),
                    None,
                )
                target_indexes = [
                    active_index if active_index is not None else slot_indexes[-1]
                ]
        if not target_indexes:
            return _apply_active_snapshot_projection(state)

        deleted_uids = {
            _clean(history[index].get("snapshot_uid"))
            for index in target_indexes
        }
        active_uid = _clean(state.get("active_snapshot_uid"))
        active_index = next(
            (
                index for index, item in enumerate(history)
                if _clean(item.get("snapshot_uid")) == active_uid
            ),
            -1,
        )
        if scene_path is not None:
            for index in target_indexes:
                _safe_delete_snapshot_cache_file(
                    scene_path,
                    history[index].get("path"),
                )
            if not requested_uid and delete_all_for_slot:
                _safe_delete_snapshot_cache_file(
                    scene_path,
                    self._legacy_snapshot_cache_path(scene_path, slot),
                )

        remaining = [
            item
            for item in history
            if _clean(item.get("snapshot_uid")) not in deleted_uids
        ]
        state["snapshots"] = remaining
        if active_uid in deleted_uids:
            if remaining:
                neighbor_index = min(max(0, active_index), len(remaining) - 1)
                state["active_snapshot_uid"] = _clean(
                    remaining[neighbor_index].get("snapshot_uid")
                )
                state["viewport_mode"] = "snapshot"
            else:
                state["active_snapshot_uid"] = ""
                state["viewport_mode"] = "video"
        return _apply_active_snapshot_projection(state)

    def _handle_delete_snapshot_action(
        self,
        incoming: Dict[str, Any],
        *,
        snapshot_uid: Any = "",
        video_uid: Any = "",
    ) -> None:
        with self._hmb_operation_control_lock:
            operation_active = bool(
                self._hmb_pending_operation_id
                or self._hmb_active_operation is not None
                or self._hmb_process_lock.locked()
            )
        if operation_active:
            acknowledgement = _clean(incoming.get("backend_ack_action_id"))
            state = self._picker_state()
            state["backend_ack_action_id"] = acknowledgement
            state["pending_action"] = ""
            state["pending_action_id"] = ""
            state["message"] = (
                "Snapshot deletion was ignored while a Picker operation is "
                "running. Wait for it to finish, then delete the Snapshot."
            )
            _append_activity_log(state, "WARNING", state["message"])
            self._write_state(state)
            return

        state = self._merge_widget_state(self._picker_state(), incoming)
        scene_text = next(
            (
                candidate
                for candidate in (
                    _maya_scene_path_text(state.get("scene_request_path")),
                    _maya_scene_path_text(state.get("scene_path")),
                    self._current_scene_text(),
                )
                if candidate
            ),
            "",
        )
        history = [
            dict(item)
            for item in state.get("snapshots", [])
            if isinstance(item, dict) and _clean(item.get("snapshot_uid"))
        ]
        requested_uid = _clean(snapshot_uid)
        requested_video_uid = _clean(video_uid)
        target = next(
            (
                item for item in history
                if requested_uid
                and _clean(item.get("snapshot_uid")) == requested_uid
            ),
            None,
        )
        if target is None and not requested_uid:
            active_uid = _clean(state.get("active_snapshot_uid"))
            target = next(
                (
                    item for item in history
                    if _clean(item.get("snapshot_uid")) == active_uid
                    and (
                        not requested_video_uid
                        or _clean(item.get("video_uid")) == requested_video_uid
                    )
                ),
                None,
            )
        if target is None and not requested_uid and requested_video_uid:
            target = next(
                (
                    item for item in reversed(history)
                    if _clean(item.get("video_uid")) == requested_video_uid
                ),
                None,
            )
        if target is None and not requested_uid and not requested_video_uid:
            legacy_slot = _normalized_video_slot(
                state.get("snapshot_video_slot")
                or state.get("selected_video_slot"),
                PRIMARY_COLOR_VIDEO_SLOT,
            )
            target = next(
                (
                    item for item in reversed(history)
                    if _normalized_video_slot(
                        item.get("render_video_slot") or item.get("video_slot"),
                        PRIMARY_COLOR_VIDEO_SLOT,
                    ) == legacy_slot
                ),
                None,
            )
        target_uid = _clean(target.get("snapshot_uid")) if target else ""
        if target_uid:
            state = self._clear_snapshot_cache(
                state,
                _norm_path(scene_text) if scene_text else None,
                _normalized_video_slot(
                    target.get("render_video_slot") or target.get("video_slot"),
                    PRIMARY_COLOR_VIDEO_SLOT,
                ),
                snapshot_uid=target_uid,
                delete_all_for_slot=False,
            )
        ready_stage = (
            "VIDEO_READY"
            if state.get("videos")
            else "OUTLINER_READY" if state.get("native_read_ready") else "LOAD_READY"
        )
        deleted_frame = float(target.get("frame") or 0.0) if target else 0.0
        state.update({
            "status": ready_stage,
            "scene_stage": ready_stage,
            "message": (
                f"Snapshot deleted: {target_uid} (Maya frame {deleted_frame:g})."
                if target_uid
                else "Snapshot was already absent; no cache file was changed."
            ),
            "pending_action": "",
            "pending_action_id": "",
        })
        _append_activity_log(state, "INFO", state["message"])
        self._write_state(state)

    def _snapshot_mode(
        self,
        scene_text: str,
        video_slot: int,
        context: Optional[_OperationContext] = None,
        *,
        video_uid: Any = "",
    ) -> Dict[str, Any]:
        self._assert_operation_current(context, "SNAPSHOT preflight")
        video_slot = PRIMARY_COLOR_VIDEO_SLOT
        strict_scene_text = _maya_scene_path_text(scene_text)
        if not strict_scene_text:
            raise ValueError(
                "A single absolute Maya .mb or .ma scene is required before SNAPSHOT."
            )
        scene_path = _norm_path(strict_scene_text)
        if not scene_path.is_file() or scene_path.suffix.lower() not in {".ma", ".mb"}:
            raise FileNotFoundError(f"Select an existing Maya .mb or .ma scene before SNAPSHOT: {scene_path}")
        if not MAYA_RUNNER.is_file():
            raise FileNotFoundError(f"Maya runner not found: {MAYA_RUNNER}")
        mayabatch = _find_mayabatch()
        if mayabatch is None:
            raise FileNotFoundError("No mayabatch installation was found.")
        maya_version = _maya_display_version(mayabatch)

        state = self._picker_state()
        output_width, output_height = _playblast_resolution(state)
        bindings = self._selected_slot_job_bindings(state, video_slot)
        _world_pattern_preflight(bindings)
        start_frame = float(state.get("start_frame") or 0.0)
        end_frame = float(state.get("end_frame") or start_frame)
        frame = max(start_frame, min(end_frame, float(state.get("snapshot_frame") or start_frame)))
        output_folder = _ensure_scene_output_folder(scene_path)
        snapshot_uid = f"snapshot-{uuid.uuid4().hex}"
        created_at_ms = int(time.time() * 1000)
        associated_video_uid = _clean(
            video_uid
            or state.get("snapshot_request_video_uid")
            or state.get("preview_video_uid")
            or state.get("selected_video_uid")
        )
        cache_path = self._snapshot_cache_path(scene_path, snapshot_uid)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        token = hashlib.sha1(
            f"snapshot|{scene_path}|{snapshot_uid}|{frame}|{time.time_ns()}".encode("utf-8")
        ).hexdigest()[:12]
        job_folder = output_folder / ".hmb_video_picker" / f"snapshot_{token}"
        frames_folder = job_folder / "frames"
        output_name = f"snapshot_video{video_slot}"
        job_path = job_folder / "snapshot.job.json"
        result_path = job_folder / "snapshot.result.json"
        progress_path = job_folder / "snapshot.progress.json"
        sidecar_path = job_folder / "snapshot.hmb.json"
        staged_cache_path = job_folder / "snapshot.partial.png"
        log_path = output_folder / f"Snapshot_{_safe_scene_name(scene_path.stem)}_Video{video_slot}.log"
        self._register_cleanup_dir(job_folder)
        self._register_cleanup_dir(frames_folder)
        for transient in (
            job_path, result_path, progress_path, Path(str(progress_path) + ".tmp"),
            sidecar_path, staged_cache_path,
        ):
            self._register_cleanup_file(transient)
        _ensure_private_job_folder(job_folder, output_folder)
        _write_json(job_path, {
            "operation": "snapshot",
            "scene_path": str(scene_path),
            "output_name": output_name,
            "frames_folder": str(frames_folder),
            "sidecar_path": str(sidecar_path),
            "result_path": str(result_path),
            "progress_path": str(progress_path),
            "camera": _clean(state.get("selected_camera")),
            "width": output_width,
            "height": output_height,
            "start_frame": frame,
            "end_frame": frame,
            "fps": float(state.get("source_fps") or 0.0) or None,
            "apply_marker_shaders": True,
            "character_outline_mode": "native_lambert",
            "force_high_quality_viewport": True,
            "viewport_quality_profile": FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
            "mouth_card_inner_patch_policy": MOUTH_CARD_INNER_PATCH_POLICY,
            "require_full_smooth_geometry": True,
            "world_space_patterns": True,
            "world_pattern_profile": MAYA_WORLD_PATTERN_PROFILE,
            "world_pattern_cell_units": WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS,
            "world_pattern_density_multiplier": WORLD_PATTERN_DENSITY_MULTIPLIER,
            "screen_space_patterns": False,
            "expected_maya_major": maya_version if maya_version.isdigit() else "",
            "marker_catalog_path": str(MARKER_CATALOG_PATH),
            "marker_catalog_version": int(MARKER_CATALOG["version"]),
            "video_slot": video_slot,
            "bindings": bindings,
            "hidden_paths": self._selected_slot_hidden_paths(state, video_slot),
        })

        command: List[str] = [str(mayabatch)]
        maya_project = _find_maya_project(scene_path)
        if maya_project is not None:
            command.extend(["-proj", str(maya_project)])
        command.extend([
            "-command", _maya_runner_command(),
        ])
        state.update({
            "status": "SNAPSHOT_RENDERING",
            "scene_stage": "SNAPSHOT_RENDERING",
            "message": f"Maya {maya_version} is rendering @video{video_slot} frame {frame:g}.",
            "snapshot_frame": frame,
            "snapshot_video_slot": video_slot,
            "last_log_path": str(log_path).replace("\\", "/"),
            "log_folder": str(output_folder).replace("\\", "/"),
        })
        _append_activity_log(
            state,
            "INFO",
            f"Maya {maya_version} snapshot started for @video{video_slot}, frame {frame:g}.",
        )
        self._write_state(state)

        env = _maya_subprocess_environment(job_path)
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            log_handle.write("MAYA SNAPSHOT COMMAND\n" + _command_text(command) + "\n\n")
            log_handle.write(
                "MAYA VP2 DEVICE OVERRIDE\n"
                + (_clean(env.get("MAYA_VP2_DEVICE_OVERRIDE")) or "user preference")
                + "\n\n"
            )
            log_handle.flush()
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(job_path.parent),
                creationflags=_creation_flags(),
            )
            self._register_active_process(process, "Maya")
            try:
                return_code = self._wait_for_process_with_progress(
                    process,
                    progress_path,
                    PLAYBLAST_OVERALL_TIMEOUT_SECONDS,
                    PLAYBLAST_STALL_TIMEOUT_SECONDS,
                    f"Maya @video{video_slot} Snapshot",
                    activity_paths=(frames_folder,),
                )
            finally:
                self._clear_active_process(process)

        self._assert_operation_current(context, "SNAPSHOT Maya completion")
        if not result_path.is_file():
            raise RuntimeError(f"Maya did not write a snapshot result. See {log_path}")
        result = _read_json(result_path)
        if not result.get("ok") or return_code not in (0, None):
            raise RuntimeError(
                f"{_clean(result.get('error')) or f'Maya exited with code {return_code}.'} See {log_path}"
            )
        runner_sidecar = (
            _read_json(sidecar_path)
            if sidecar_path.is_file()
            else {}
        )
        _validate_full_smooth_confirmation(
            result,
            runner_sidecar,
            label=f"@video{video_slot} Snapshot",
        )
        _validate_world_pattern_runner_confirmation(
            result,
            runner_sidecar,
        )
        rendered_folder = Path(_clean(result.get("frames_folder")) or frames_folder)
        rendered_path = rendered_folder / f"{output_name}.000000.png"
        if not rendered_path.is_file() or rendered_path.stat().st_size <= 0:
            raise RuntimeError(f"Maya did not create the requested snapshot frame. See {log_path}")
        shutil.copy2(rendered_path, staged_cache_path)
        self._assert_operation_current(context, "SNAPSHOT atomic publish")
        os.replace(staged_cache_path, cache_path)

        state = _append_snapshot_history_record(
            self._picker_state(),
            {
            "snapshot_uid": snapshot_uid,
            "video_uid": associated_video_uid,
            "render_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
            "video_slot": video_slot,
            "frame": frame,
            "path": str(cache_path).replace("\\", "/"),
            "url": _external_media_url(cache_path),
            "sha256": _sha256_file(cache_path),
            "created_at_ms": created_at_ms,
            },
            scene_path=scene_path,
        )
        ready_stage = "VIDEO_READY" if state.get("videos") else "OUTLINER_READY"
        state.update({
            "status": ready_stage,
            "scene_stage": ready_stage,
            "message": f"Snapshot ready at Maya frame {frame:g}.",
            "snapshot_request_video_uid": "",
            "workspace_view": "playblast",
            "warnings": [_clean(item) for item in result.get("warnings", []) if _clean(item)],
        })
        state = self._mark_operation_finished(state)
        _append_activity_log(
            state,
            "SUCCESS",
            f"Snapshot {snapshot_uid} completed at Maya frame {frame:g}.",
        )
        self._write_state(state)
        return {
            "mode": "snapshot",
            "snapshot_uid": snapshot_uid,
            "video_uid": associated_video_uid,
            "video_slot": video_slot,
            "frame": frame,
            "snapshot": str(cache_path),
        }

    def _encode_playblast_sequence(
        self,
        *,
        ffmpeg: Path,
        frame_pattern: Path,
        staged_video_path: Path,
        source_fps: float,
        frame_count: int,
        width: int,
        height: int,
        log_path: Path,
        output_folder: Path,
        label: str,
    ) -> None:
        command = _build_ffmpeg_encode_command(
            ffmpeg=ffmpeg,
            frame_pattern=frame_pattern,
            output_path=staged_video_path,
            source_fps=source_fps,
            frame_count=frame_count,
            width=width,
            height=height,
        )
        state = self._picker_state()
        _append_activity_log(
            state,
            "INFO",
            (
                f"Encoding {label} with the high-quality BT.709 H.264 profile "
                f"at the exact Maya rate {source_fps:g} FPS."
            ),
        )
        self._write_state(state)
        with log_path.open("a", encoding="utf-8", errors="replace") as log_handle:
            log_handle.write(
                f"\nFFMPEG COMMAND ({label})\n"
                + _command_text(command)
                + "\n\n"
            )
            log_handle.flush()
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                cwd=str(output_folder),
                creationflags=_creation_flags(),
            )
            self._register_active_process(process, "FFmpeg")
            try:
                return_code = process.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                _terminate_process(process)
                raise TimeoutError(
                    f"FFmpeg encoding for {label} exceeded 7200 seconds. See {log_path}"
                )
            finally:
                self._clear_active_process(process)
        if (
            return_code != 0
            or not staged_video_path.is_file()
            or staged_video_path.stat().st_size <= 0
        ):
            raise RuntimeError(f"H.264 encoding for {label} failed. See {log_path}")

    def _maya_mode(
        self,
        scene_text: str,
        video_slot: int,
        context: Optional[_OperationContext] = None,
        *,
        publish_public: bool = True,
    ) -> Dict[str, Any]:
        self._assert_operation_current(context, "PLAYBLAST preflight")
        state = self._picker_state()
        depth_enabled = bool(state.get("depth_enabled"))
        motion_guide_enabled = bool(state.get("motion_guide_enabled"))
        video_slot = PRIMARY_COLOR_VIDEO_SLOT
        if context is not None:
            depth_video_slot = context.depth_video_slot
            motion_guide_video_slot = context.motion_guide_video_slot
        elif depth_enabled or motion_guide_enabled:
            (
                depth_video_slot,
                motion_guide_video_slot,
            ) = _resolve_generated_companion_slots(
                state,
                depth_enabled=depth_enabled,
                motion_guide_enabled=motion_guide_enabled,
            )
        else:
            depth_video_slot = 0
            motion_guide_video_slot = 0
        if depth_enabled != bool(depth_video_slot):
            raise RuntimeError("The frozen Depth slot plan no longer matches the request.")
        if motion_guide_enabled != bool(motion_guide_video_slot):
            raise RuntimeError("The frozen Motion Guide slot plan no longer matches the request.")
        strict_scene_text = _maya_scene_path_text(scene_text)
        if not strict_scene_text:
            raise ValueError("MAYA_SCENE is required.")
        scene_path = _norm_path(strict_scene_text)
        if not scene_path.is_file():
            raise FileNotFoundError(f"Maya scene not found: {scene_path}")
        if scene_path.suffix.lower() not in {".ma", ".mb"}:
            raise ValueError(f"MAYA_SCENE must be .mb or .ma: {scene_path}")
        if not MAYA_RUNNER.is_file():
            raise FileNotFoundError(f"Maya runner not found: {MAYA_RUNNER}")

        mayabatch = _find_mayabatch()
        if mayabatch is None:
            raise FileNotFoundError("No mayabatch installation was found. Install Maya or set MAYA_LOCATION/PATH.")
        maya_version = _maya_display_version(mayabatch)
        ffmpeg = _find_ffmpeg(mayabatch)
        if ffmpeg is None:
            raise FileNotFoundError("FFmpeg was not found. Install imageio-ffmpeg, set FFMPEG_PATH explicitly, or place it beside mayabatch.")
        output_folder = _ensure_scene_output_folder(scene_path)
        token = hashlib.sha1(
            f"{scene_path}|{time.time_ns()}|{uuid.uuid4().hex}".encode("utf-8")
        ).hexdigest()[:12]
        output_name = f"{_safe_scene_name(scene_path.stem)}_playblast_{token}"
        depth_output_name = (
            f"{_safe_scene_name(scene_path.stem)}_depth_playblast_{token}"
        )
        motion_guide_output_name = (
            f"{_safe_scene_name(scene_path.stem)}_motion_guide_"
            f"{token}"
        )
        job_folder = (
            output_folder
            / ".hmb_video_picker"
            / (
                f"video{video_slot}_bundle_{token}"
                if depth_enabled or motion_guide_enabled
                else f"video{video_slot}_{token}"
            )
        )
        frames_folder = job_folder / "frames"
        depth_frames_folder = job_folder / "depth_frames"
        motion_guide_frames_folder = job_folder / "motion_guide_frames"
        job_path = job_folder / "render.job.json"
        result_path = job_folder / "render.result.json"
        progress_path = job_folder / "render.progress.json"
        log_path = output_folder / f"{output_name}.log"
        video_path = output_folder / f"{scene_path.stem}_playblast_{token}.mp4"
        sidecar_path = output_folder / f"{scene_path.stem}_playblast_{token}.hmb.json"
        depth_video_path = (
            output_folder
            / f"{scene_path.stem}_depth_playblast_{token}.mp4"
        )
        depth_sidecar_path = (
            output_folder
            / f"{scene_path.stem}_depth_playblast_{token}.hmb.json"
        )
        motion_guide_video_path = (
            output_folder
            / f"{scene_path.stem}_motion_guide_{token}.mp4"
        )
        motion_guide_sidecar_path = (
            output_folder
            / f"{scene_path.stem}_motion_guide_{token}.hmb.json"
        )
        staged_video_path = job_folder / "video.partial.mp4"
        staged_sidecar_path = job_folder / "video.partial.hmb.json"
        staged_depth_video_path = job_folder / "depth.partial.mp4"
        staged_depth_sidecar_path = job_folder / "depth.partial.hmb.json"
        staged_motion_guide_video_path = (
            job_folder / "motion-guide.partial.mp4"
        )
        staged_motion_guide_sidecar_path = (
            job_folder / "motion-guide.partial.hmb.json"
        )

        self._register_cleanup_dir(frames_folder)
        self._register_cleanup_dir(job_folder)
        self._register_cleanup_file(job_path)
        self._register_cleanup_file(result_path)
        self._register_cleanup_file(progress_path)
        self._register_cleanup_file(Path(str(progress_path) + ".tmp"))
        self._register_cleanup_file(staged_video_path)
        self._register_cleanup_file(staged_sidecar_path)
        if depth_enabled:
            self._register_cleanup_dir(depth_frames_folder)
            self._register_cleanup_file(staged_depth_video_path)
            self._register_cleanup_file(staged_depth_sidecar_path)
        if motion_guide_enabled:
            self._register_cleanup_dir(motion_guide_frames_folder)
            self._register_cleanup_file(staged_motion_guide_video_path)
            self._register_cleanup_file(staged_motion_guide_sidecar_path)
        _ensure_private_job_folder(job_folder, output_folder)
        if frames_folder.exists():
            _safe_remove_private_tree(frames_folder)
        if depth_enabled and depth_frames_folder.exists():
            _safe_remove_private_tree(depth_frames_folder)
        if (
            motion_guide_enabled
            and motion_guide_frames_folder.exists()
        ):
            _safe_remove_private_tree(motion_guide_frames_folder)

        # Generate switches the shared viewport back to Video but keeps the
        # append-only Snapshot history and its private cache files available.
        state = _apply_active_snapshot_projection(state, viewport_mode="video")
        output_width, output_height = _playblast_resolution(state)
        mask_authoring_slot = (
            context.mask_authoring_slot
            if context is not None
            else _mask_authoring_slot(state)
        )
        job_bindings = self._selected_slot_job_bindings(
            state,
            mask_authoring_slot,
        )
        _world_pattern_preflight(job_bindings)

        _write_json(job_path, {
            "operation": "render",
            "scene_path": str(scene_path),
            "output_folder": str(output_folder),
            "output_name": output_name,
            "frames_folder": str(frames_folder),
            "sidecar_path": str(staged_sidecar_path),
            "result_path": str(result_path),
            "progress_path": str(progress_path),
            "camera": _clean(state.get("selected_camera")),
            "width": output_width,
            "height": output_height,
            "start_frame": None,
            "end_frame": None,
            "fps": None,
            "apply_marker_shaders": True,
            "character_outline_mode": "native_lambert",
            "force_high_quality_viewport": True,
            "viewport_quality_profile": FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
            "mouth_card_inner_patch_policy": MOUTH_CARD_INNER_PATCH_POLICY,
            "require_full_smooth_geometry": True,
            "world_space_patterns": True,
            "world_pattern_profile": MAYA_WORLD_PATTERN_PROFILE,
            "world_pattern_cell_units": WORLD_PATTERN_DEFAULT_CELL_WORLD_UNITS,
            "world_pattern_density_multiplier": WORLD_PATTERN_DENSITY_MULTIPLIER,
            "screen_space_patterns": False,
            "expected_maya_major": maya_version if maya_version.isdigit() else "",
            "video_container": "MPEG-4",
            "video_codec": "H.264",
            "ffmpeg_encoder": "libx264",
            "output_fps": OUTPUT_FPS,
            "marker_catalog_path": str(MARKER_CATALOG_PATH),
            "marker_catalog_version": int(MARKER_CATALOG["version"]),
            "video_slot": video_slot,
            "bindings": job_bindings,
            "hidden_paths": self._selected_slot_hidden_paths(
                state,
                mask_authoring_slot,
            ),
            "generate_depth_playblast": depth_enabled,
            "depth_video_slot": depth_video_slot,
            "depth_output_name": depth_output_name if depth_enabled else "",
            "depth_frames_folder": (
                str(depth_frames_folder) if depth_enabled else ""
            ),
            "depth_sidecar_path": (
                str(staged_depth_sidecar_path) if depth_enabled else ""
            ),
            "depth_profile": (
                DEPTH_PLAYBLAST_PROFILE if depth_enabled else ""
            ),
            "generate_motion_guide": motion_guide_enabled,
            "motion_guide_video_slot": motion_guide_video_slot,
            "motion_guide_output_name": (
                motion_guide_output_name if motion_guide_enabled else ""
            ),
            "motion_guide_frames_folder": (
                str(motion_guide_frames_folder)
                if motion_guide_enabled
                else ""
            ),
            "motion_guide_sidecar_path": (
                str(staged_motion_guide_sidecar_path)
                if motion_guide_enabled
                else ""
            ),
            "motion_guide_profile": (
                MOTION_GUIDE_PROFILE if motion_guide_enabled else ""
            ),
        })

        command: List[str] = [str(mayabatch)]
        maya_project = _find_maya_project(scene_path)
        if maya_project is not None:
            command.extend(["-proj", str(maya_project)])
        command.extend([
            "-command", _maya_runner_command(),
        ])

        state.update({
            "status": "GENERATING_VIDEO",
            "message": (
                f"Maya {maya_version} is rendering Mask, shader Depth, and Motion "
                "Guide from one scene load."
                if depth_enabled and motion_guide_enabled
                else
                f"Maya {maya_version} is rendering paired Mask and shader Depth "
                "from one scene load."
                if depth_enabled
                else
                f"Maya {maya_version} is rendering Mask and "
                "Motion Guide from one scene load."
                if motion_guide_enabled
                else
                f"Maya {maya_version} is applying temporary marker shaders and rendering the playblast."
            ),
            "scene_path": str(scene_path).replace("\\", "/"),
            "selected_video_slot": video_slot,
            "depth_video_slot": depth_video_slot,
            "motion_guide_video_slot": motion_guide_video_slot,
            "maya_executable": str(mayabatch).replace("\\", "/"),
            "maya_version": maya_version,
            "last_log_path": str(log_path).replace("\\", "/"),
            "log_folder": str(output_folder).replace("\\", "/"),
        })
        _append_activity_log(
            state,
            "INFO",
            (
                f"Maya {maya_version} Mask/Depth/Motion Guide bundle started. "
                f"Diagnostic log: {log_path}"
                if depth_enabled and motion_guide_enabled
                else
                f"Maya {maya_version} paired Mask/shader-Depth playblast started. "
                f"Diagnostic log: {log_path}"
                if depth_enabled
                else
                f"Maya {maya_version} Mask/Motion Guide bundle started. "
                f"Diagnostic log: {log_path}"
                if motion_guide_enabled
                else
                f"Maya {maya_version} Mask playblast started. Diagnostic log: {log_path}"
            ),
        )
        if depth_enabled or motion_guide_enabled:
            _append_activity_log(
                state,
                "INFO",
                "Each independently validated auxiliary result will append a new "
                "video-history record; existing records and files remain unchanged.",
            )
        self._write_state(state)

        env = _maya_subprocess_environment(job_path)
        _ensure_private_job_folder(job_folder, output_folder)

        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            log_handle.write("MAYA COMMAND\n" + _command_text(command) + "\n\n")
            log_handle.write(
                "MAYA VP2 DEVICE OVERRIDE\n"
                + (_clean(env.get("MAYA_VP2_DEVICE_OVERRIDE")) or "user preference")
                + "\n\n"
            )
            log_handle.flush()
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(job_path.parent),
                creationflags=_creation_flags(),
            )
            self._register_active_process(process, "Maya")
            try:
                return_code = self._wait_for_process_with_progress(
                    process,
                    progress_path,
                    PLAYBLAST_OVERALL_TIMEOUT_SECONDS,
                    PLAYBLAST_STALL_TIMEOUT_SECONDS,
                    (
                        f"Maya Mask + @video{depth_video_slot} shader Depth + "
                        f"@video{motion_guide_video_slot} Motion Guide bundle"
                        if depth_enabled and motion_guide_enabled
                        else
                        f"Maya Mask + @video{depth_video_slot} shader Depth Playblast"
                        if depth_enabled
                        else
                        f"Maya Mask + @video{motion_guide_video_slot} Motion Guide bundle"
                        if motion_guide_enabled
                        else f"Maya @video{video_slot} Playblast"
                    ),
                    activity_paths=(
                        tuple(
                            [
                                frames_folder,
                                *(
                                    [depth_frames_folder]
                                    if depth_enabled else []
                                ),
                                *(
                                    [motion_guide_frames_folder]
                                    if motion_guide_enabled else []
                                ),
                            ]
                        )
                    ),
                )
            finally:
                self._clear_active_process(process)

        self._assert_operation_current(context, "PLAYBLAST Maya completion")
        state = self._picker_state()
        _append_activity_log(
            state,
            "INFO",
            f"Maya playblast process finished with exit code {return_code}.",
        )
        self._write_state(state)

        if not result_path.is_file():
            raise RuntimeError(f"Maya did not write a result file. Exit code={return_code}. See {log_path}")
        result = _read_json(result_path)
        if not result.get("ok"):
            raise RuntimeError(f"{_clean(result.get('error')) or 'Maya background preview failed.'} See {log_path}")
        if return_code not in (0, None):
            raise RuntimeError(f"Maya exited with code {return_code}. See {log_path}")

        runner_artifacts = (
            dict(result.get("artifacts"))
            if isinstance(result.get("artifacts"), dict)
            else {}
        )
        depth_succeeded = bool(
            depth_enabled
            and (
                bool((runner_artifacts.get("depth") or {}).get("ok"))
                if runner_artifacts
                else True
            )
        )
        motion_guide_succeeded = bool(
            motion_guide_enabled
            and (
                bool((runner_artifacts.get("motion_guide") or {}).get("ok"))
                if runner_artifacts
                else True
            )
        )
        auxiliary_failure_warnings: List[str] = []
        auxiliary_failure_details: List[Dict[str, str]] = []

        def record_auxiliary_failure(label: str, error: Any) -> None:
            detail = _clean(error) or error.__class__.__name__
            full_warning = (
                f"Optional {label} artifact was not published: {detail}"
            )
            warning = _compact_auxiliary_failure_warning(
                label,
                detail,
                language=_clean(state.get("language")) or "ko",
            )
            if warning not in auxiliary_failure_warnings:
                auxiliary_failure_warnings.append(warning)
            detail_record = {
                "label": _clean(label),
                "error": detail,
            }
            if detail_record not in auxiliary_failure_details:
                auxiliary_failure_details.append(detail_record)
            _append_full_diagnostic_log(
                log_path,
                "HMB OPTIONAL ARTIFACT ERROR",
                full_warning,
            )

        if depth_enabled and not depth_succeeded:
            record_auxiliary_failure(
                f"@video{depth_video_slot} Depth",
                _clean((runner_artifacts.get("depth") or {}).get("error"))
                or "Maya did not produce a valid Depth frame sequence",
            )
        if motion_guide_enabled and not motion_guide_succeeded:
            record_auxiliary_failure(
                f"@video{motion_guide_video_slot} Motion Guide",
                _clean(
                    (runner_artifacts.get("motion_guide") or {}).get("error")
                )
                or "Maya did not produce a valid Motion Guide frame sequence",
            )

        actual_frames_folder = _validated_runner_result_path(
            result,
            "frames_folder",
            frames_folder,
        )
        actual_sidecar = _validated_runner_result_path(
            result,
            "sidecar_path",
            staged_sidecar_path,
        )
        actual_depth_frames_folder = depth_frames_folder
        actual_depth_sidecar = staged_depth_sidecar_path
        actual_motion_guide_frames_folder = motion_guide_frames_folder
        actual_motion_guide_sidecar = staged_motion_guide_sidecar_path
        if depth_succeeded:
            try:
                actual_depth_frames_folder = _validated_runner_result_path(
                    result,
                    "depth_frames_folder",
                    depth_frames_folder,
                )
                actual_depth_sidecar = _validated_runner_result_path(
                    result,
                    "depth_sidecar_path",
                    staged_depth_sidecar_path,
                )
            except Exception as exc:
                depth_succeeded = False
                record_auxiliary_failure(
                    f"@video{depth_video_slot} Depth path validation",
                    exc,
                )
        if motion_guide_succeeded:
            try:
                actual_motion_guide_frames_folder = (
                    _validated_runner_result_path(
                        result,
                        "motion_guide_frames_folder",
                        motion_guide_frames_folder,
                    )
                )
                actual_motion_guide_sidecar = _validated_runner_result_path(
                    result,
                    "motion_guide_sidecar_path",
                    staged_motion_guide_sidecar_path,
                )
            except Exception as exc:
                motion_guide_succeeded = False
                record_auxiliary_failure(
                    f"@video{motion_guide_video_slot} Motion Guide path validation",
                    exc,
                )

        # Only validated requested paths may enter cleanup or downstream I/O.
        self._register_cleanup_dir(actual_frames_folder)
        if depth_succeeded:
            self._register_cleanup_dir(actual_depth_frames_folder)
            self._register_cleanup_file(actual_depth_sidecar)
        if motion_guide_succeeded:
            self._register_cleanup_dir(actual_motion_guide_frames_folder)
            self._register_cleanup_file(actual_motion_guide_sidecar)
        source_fps = float(result.get("fps") or 0.0)
        source_frame_count = int(result.get("frame_count") or 0)
        if source_fps <= 0 or source_frame_count <= 0:
            raise RuntimeError(f"Maya did not provide valid timing or preview frames. See {log_path}")
        source_duration = source_frame_count / source_fps
        # Preserve Maya's exact frame/time relationship. Converting an arbitrary
        # source rate to fixed 24 fps cannot represent every duration exactly.
        # The Picker therefore encodes the inspected source rate and leaves any
        # explicit delivery-rate conversion to a downstream delivery stage.
        output_fps = source_fps
        output_frame_count = source_frame_count
        output_duration = source_duration
        if output_frame_count <= 0:
            raise RuntimeError("Duration validation failed.")

        if not actual_sidecar.is_file():
            raise RuntimeError(f"HMB sidecar JSON was not created. See {log_path}")
        runner_sidecar = _read_json(actual_sidecar)
        _validate_full_smooth_confirmation(
            result,
            runner_sidecar,
            label="Mask / legacy Color Assignment Playblast",
        )
        _validate_world_pattern_runner_confirmation(
            result,
            runner_sidecar,
        )
        depth_runner_sidecar: Dict[str, Any] = {}
        depth_range_report: Dict[str, Any] = {}
        depth_validation_report: Dict[str, Any] = {}
        motion_guide_runner_sidecar: Dict[str, Any] = {}
        motion_guide_validation_report: Dict[str, Any] = {}
        if depth_succeeded:
            try:
                if not actual_depth_sidecar.is_file():
                    raise RuntimeError(
                        f"Depth sidecar JSON was not created for @video{depth_video_slot}. "
                        f"See {log_path}"
                    )
                depth_runner_sidecar = _read_json(actual_depth_sidecar)
            except Exception as exc:
                depth_succeeded = False
                record_auxiliary_failure(
                    f"@video{depth_video_slot} Depth metadata",
                    exc,
                )
        if motion_guide_succeeded:
            try:
                if not actual_motion_guide_sidecar.is_file():
                    raise RuntimeError(
                        f"Motion Guide sidecar JSON was not created for @video{motion_guide_video_slot}. "
                        f"See {log_path}"
                    )
                motion_guide_runner_sidecar = _read_json(
                    actual_motion_guide_sidecar
                )
            except Exception as exc:
                motion_guide_succeeded = False
                record_auxiliary_failure(
                    f"@video{motion_guide_video_slot} Motion Guide metadata",
                    exc,
                )
        expected_frame_paths = [
            actual_frames_folder / f"{output_name}.{index:06d}.png"
            for index in range(output_frame_count)
        ]
        if depth_succeeded:
            try:
                expected_depth_frame_paths = [
                    actual_depth_frames_folder
                    / f"{depth_output_name}.{index:06d}.png"
                    for index in range(output_frame_count)
                ]
                missing_depth_frames = [
                    path.name
                    for path in expected_depth_frame_paths
                    if not path.is_file() or path.stat().st_size <= 0
                ]
                if missing_depth_frames:
                    raise RuntimeError(
                        "Depth frame sequence is incomplete; first missing/empty "
                        f"frame: {missing_depth_frames[0]}. See {log_path}"
                    )
                depth_validation_report = _validate_depth_companion_inputs(
                    result=result,
                    color_sidecar=runner_sidecar,
                    depth_sidecar=depth_runner_sidecar,
                    color_frame_paths=expected_frame_paths,
                    depth_frame_paths=expected_depth_frame_paths,
                    expected_frame_count=output_frame_count,
                    expected_fps=output_fps,
                    expected_start_frame=float(
                        runner_sidecar.get("start_frame") or 0.0
                    ),
                    expected_end_frame=float(
                        runner_sidecar.get("end_frame") or 0.0
                    ),
                    expected_width=output_width,
                    expected_height=output_height,
                )
                depth_range_report = dict(
                    depth_runner_sidecar["depth_range_report"]
                )
            except Exception as exc:
                depth_succeeded = False
                record_auxiliary_failure(
                    f"@video{depth_video_slot} Depth frame validation",
                    exc,
                )
        if motion_guide_succeeded:
            try:
                expected_motion_guide_frame_paths = [
                    actual_motion_guide_frames_folder
                    / f"{motion_guide_output_name}.{index:06d}.png"
                    for index in range(output_frame_count)
                ]
                missing_motion_frames = [
                    path.name
                    for path in expected_motion_guide_frame_paths
                    if not path.is_file() or path.stat().st_size <= 0
                ]
                if missing_motion_frames:
                    raise RuntimeError(
                        "Motion Guide frame sequence is incomplete; first "
                        f"missing/empty frame: {missing_motion_frames[0]}. "
                        f"See {log_path}"
                    )
                motion_guide_validation_report = (
                    _validate_motion_guide_inputs(
                        result=result,
                        color_sidecar=runner_sidecar,
                        motion_sidecar=motion_guide_runner_sidecar,
                        motion_frame_paths=expected_motion_guide_frame_paths,
                        expected_frame_count=output_frame_count,
                        expected_fps=output_fps,
                        expected_start_frame=float(
                            runner_sidecar.get("start_frame") or 0.0
                        ),
                        expected_end_frame=float(
                            runner_sidecar.get("end_frame") or 0.0
                        ),
                        expected_width=output_width,
                        expected_height=output_height,
                    )
                )
            except Exception as exc:
                motion_guide_succeeded = False
                record_auxiliary_failure(
                    f"@video{motion_guide_video_slot} Motion Guide frame validation",
                    exc,
                )

        self._assert_operation_current(context, "PLAYBLAST frame validation")
        self._encode_playblast_sequence(
            ffmpeg=ffmpeg,
            frame_pattern=actual_frames_folder / f"{output_name}.%06d.png",
            staged_video_path=staged_video_path,
            source_fps=output_fps,
            frame_count=output_frame_count,
            width=output_width,
            height=output_height,
            log_path=log_path,
            output_folder=output_folder,
            label=f"@video{video_slot} Color",
        )
        if depth_succeeded:
            try:
                self._assert_operation_current(
                    context,
                    "DEPTH PLAYBLAST color encode completion",
                )
                self._encode_playblast_sequence(
                    ffmpeg=ffmpeg,
                    frame_pattern=(
                        actual_depth_frames_folder
                        / f"{depth_output_name}.%06d.png"
                    ),
                    staged_video_path=staged_depth_video_path,
                    source_fps=output_fps,
                    frame_count=output_frame_count,
                    width=output_width,
                    height=output_height,
                    log_path=log_path,
                    output_folder=output_folder,
                    label=f"@video{depth_video_slot} Depth",
                )
            except _StaleOperationError:
                raise
            except Exception as exc:
                depth_succeeded = False
                record_auxiliary_failure(
                    f"@video{depth_video_slot} Depth encoding",
                    exc,
                )
        if motion_guide_succeeded:
            try:
                self._assert_operation_current(
                    context,
                    "MOTION GUIDE color encode completion",
                )
                self._encode_playblast_sequence(
                    ffmpeg=ffmpeg,
                    frame_pattern=(
                        actual_motion_guide_frames_folder
                        / f"{motion_guide_output_name}.%06d.png"
                    ),
                    staged_video_path=staged_motion_guide_video_path,
                    source_fps=output_fps,
                    frame_count=output_frame_count,
                    width=output_width,
                    height=output_height,
                    log_path=log_path,
                    output_folder=output_folder,
                    label=f"@video{motion_guide_video_slot} Motion Guide",
                )
            except _StaleOperationError:
                raise
            except Exception as exc:
                motion_guide_succeeded = False
                record_auxiliary_failure(
                    f"@video{motion_guide_video_slot} Motion Guide encoding",
                    exc,
                )

        color_stream_validation = _validate_encoded_playblast(
            staged_video_path,
            ffmpeg=ffmpeg,
            expected_fps=output_fps,
            expected_frame_count=output_frame_count,
            expected_width=output_width,
            expected_height=output_height,
            label=f"@video{video_slot} Color",
        )
        depth_stream_validation: Dict[str, Any] = {}
        if depth_succeeded:
            try:
                depth_stream_validation = _validate_encoded_playblast(
                    staged_depth_video_path,
                    ffmpeg=ffmpeg,
                    expected_fps=output_fps,
                    expected_frame_count=output_frame_count,
                    expected_width=output_width,
                    expected_height=output_height,
                    label=f"@video{depth_video_slot} Depth",
                )
            except Exception as exc:
                depth_succeeded = False
                record_auxiliary_failure(
                    f"@video{depth_video_slot} Depth media validation",
                    exc,
                )
        motion_guide_stream_validation: Dict[str, Any] = {}
        if motion_guide_succeeded:
            try:
                motion_guide_stream_validation = _validate_encoded_playblast(
                    staged_motion_guide_video_path,
                    ffmpeg=ffmpeg,
                    expected_fps=output_fps,
                    expected_frame_count=output_frame_count,
                    expected_width=output_width,
                    expected_height=output_height,
                    label=f"@video{motion_guide_video_slot} Motion Guide",
                )
            except Exception as exc:
                motion_guide_succeeded = False
                record_auxiliary_failure(
                    f"@video{motion_guide_video_slot} Motion Guide media validation",
                    exc,
                )
        if not actual_sidecar.is_file():
            raise RuntimeError(f"HMB sidecar JSON was not created. See {log_path}")
        self._assert_operation_current(context, "PLAYBLAST encode completion")
        sidecar = _read_json(actual_sidecar)
        markers = [{**marker, "video_slot": video_slot} for marker in _normalize_markers(sidecar.get("markers"))]

        bundle_run_id = (
            uuid.uuid4().hex
            if depth_succeeded or motion_guide_succeeded
            else ""
        )
        pair_run_id = bundle_run_id if depth_succeeded else ""
        warnings = [_clean(item) for item in sidecar.get("warnings", []) if _clean(item)]
        for warning in auxiliary_failure_warnings:
            if warning not in warnings:
                warnings.append(warning)
        sidecar.pop("frame_pattern", None)
        sidecar.update({
            "mode": "maya",
            "video": video_path.name,
            "video_path": str(video_path).replace("\\", "/"),
            "pair_run_id": pair_run_id,
            "bundle_run_id": bundle_run_id,
            "paired_depth_video_slot": depth_video_slot if depth_succeeded else 0,
            "paired_motion_guide_video_slot": (
                motion_guide_video_slot if motion_guide_succeeded else 0
            ),
            "frame_sequence_transient": True,
            "encoded_stream_validation": color_stream_validation,
            "fps": output_fps,
            "frame_count": output_frame_count,
            "source_fps": source_fps,
            "source_frame_count": source_frame_count,
            "source_duration_seconds": source_duration,
            "output_duration_seconds": output_duration,
            "output_fps": output_fps,
            "resolution": {"width": output_width, "height": output_height},
            "markers": markers,
            "warnings": warnings,
            "auxiliary_failure_details": list(
                auxiliary_failure_details
            ),
            "duration_policy": "exact_source_timing",
            "marker_catalog_version": int(MARKER_CATALOG["version"]),
            "video_format": {
                "container": "MPEG-4",
                "codec": "H.264",
                "encoder": "libx264",
                "pixel_format": "yuv420p",
                "profile": PROXY_H264_PROFILE,
                "level": PROXY_H264_LEVEL,
                "preset": PROXY_ENCODER_PRESET,
                "crf": PROXY_ENCODER_CRF,
                "color_range": "tv",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
                "frame_rate": _fps_timebase(output_fps),
                "track_timescale": _video_track_timescale(output_fps),
                "gop_frames": max(1, int(round(output_fps))),
                "fps_mode": "passthrough",
            },
        })
        _write_json(actual_sidecar, sidecar)

        depth_sidecar: Dict[str, Any] = {}
        depth_warnings: List[str] = []
        if depth_succeeded:
            depth_warnings = [
                _clean(item)
                for item in depth_runner_sidecar.get("warnings", [])
                if _clean(item)
            ]
            depth_runner_sidecar.pop("frame_pattern", None)
            depth_sidecar = {
                **depth_runner_sidecar,
                "schema": "hmb-depth-playblast",
                "schema_version": 1,
                "mode": "maya_depth",
                "media_kind": DEPTH_MEDIA_KIND,
                "video_role": "maya_depth_companion",
                "source_type_hint": DEPTH_SOURCE_TYPE,
                "control_role_hint": DEPTH_CONTROL_ROLE,
                "companion_of_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                "source_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                "pair_run_id": pair_run_id,
                "bundle_run_id": bundle_run_id,
                "video_slot": depth_video_slot,
                "video": depth_video_path.name,
                "video_path": str(depth_video_path).replace("\\", "/"),
                "camera": _clean(
                    depth_runner_sidecar.get("camera")
                    or sidecar.get("camera")
                ),
                "fps": output_fps,
                "frame_count": output_frame_count,
                "source_fps": source_fps,
                "source_frame_count": source_frame_count,
                "source_duration_seconds": source_duration,
                "output_duration_seconds": output_duration,
                "output_fps": output_fps,
                "start_frame": float(
                    depth_runner_sidecar.get(
                        "start_frame",
                        sidecar.get("start_frame", state.get("start_frame", 0.0)),
                    )
                    or 0.0
                ),
                "end_frame": float(
                    depth_runner_sidecar.get(
                        "end_frame",
                        sidecar.get("end_frame", state.get("end_frame", 0.0)),
                    )
                    or 0.0
                ),
                "resolution": {
                    "width": output_width,
                    "height": output_height,
                },
                "markers": [],
                "available_color_picks": [],
                "warnings": depth_warnings,
                "duration_policy": "exact_source_timing",
                "depth_profile": DEPTH_PLAYBLAST_PROFILE,
                "depth_range_report": depth_range_report,
                "depth_validation_report": depth_validation_report,
                "encoded_stream_validation": depth_stream_validation,
                "background_value": 0.0,
                "depth_semantics": "camera_space_near_white_far_black",
                "normalization_scope": "fixed_full_shot",
                "frame_sequence_transient": True,
                "video_format": dict(sidecar.get("video_format") or {}),
            }
            _write_json(actual_depth_sidecar, depth_sidecar)

        motion_guide_sidecar: Dict[str, Any] = {}
        motion_guide_warnings: List[str] = []
        if motion_guide_succeeded:
            motion_guide_warnings = [
                _clean(item)
                for item in motion_guide_runner_sidecar.get("warnings", [])
                if _clean(item)
            ]
            motion_guide_runner_sidecar.pop("frame_pattern", None)
            motion_guide_sidecar = {
                **motion_guide_runner_sidecar,
                "schema": "hmb-motion-guide",
                "schema_version": MOTION_GUIDE_SIDECAR_SCHEMA_VERSION,
                "mode": "maya_motion_guide",
                "media_kind": MOTION_GUIDE_MEDIA_KIND,
                "video_role": "maya_motion_guide_companion",
                "source_type_hint": MOTION_GUIDE_SOURCE_TYPE,
                "control_role_hint": MOTION_GUIDE_CONTROL_ROLE,
                "companion_of_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                "source_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                "bundle_run_id": bundle_run_id,
                "video_slot": motion_guide_video_slot,
                "video": motion_guide_video_path.name,
                "video_path": str(motion_guide_video_path).replace("\\", "/"),
                "camera": _clean(
                    motion_guide_runner_sidecar.get("camera")
                    or sidecar.get("camera")
                ),
                "fps": output_fps,
                "frame_count": output_frame_count,
                "source_fps": source_fps,
                "source_frame_count": source_frame_count,
                "source_duration_seconds": source_duration,
                "output_duration_seconds": output_duration,
                "output_fps": output_fps,
                "start_frame": float(
                    motion_guide_runner_sidecar.get(
                        "start_frame",
                        sidecar.get(
                            "start_frame",
                            state.get("start_frame", 0.0),
                        ),
                    )
                    or 0.0
                ),
                "end_frame": float(
                    motion_guide_runner_sidecar.get(
                        "end_frame",
                        sidecar.get(
                            "end_frame",
                            state.get("end_frame", 0.0),
                        ),
                    )
                    or 0.0
                ),
                "resolution": {
                    "width": output_width,
                    "height": output_height,
                },
                "markers": [],
                "available_color_picks": [],
                "warnings": motion_guide_warnings,
                "duration_policy": "exact_source_timing",
                "motion_guide_profile": MOTION_GUIDE_PROFILE,
                "motion_guide_report": dict(
                    motion_guide_runner_sidecar.get(
                        "motion_guide_report"
                    )
                    or {}
                ),
                "motion_guide_validation_report": (
                    motion_guide_validation_report
                ),
                "encoded_stream_validation": (
                    motion_guide_stream_validation
                ),
                "background_rgb": [0, 0, 0],
                "appearance_authority": "zero",
                "motion_authority": "derived_decoder_of_video1_only",
                "frame_sequence_transient": True,
                "video_format": dict(sidecar.get("video_format") or {}),
            }
            _write_json(
                actual_motion_guide_sidecar,
                motion_guide_sidecar,
            )

        # Publish Color first, then each optional artifact in its own atomic
        # media/sidecar + project-copy transaction. An optional failure restores
        # only that optional pair and cannot undo Color or its successful sibling.
        self._assert_operation_current(context, "PLAYBLAST per-artifact publish")
        previous_picker_state = self._picker_state()
        publish_records: List[tuple[Path, Path, bool]] = []
        project_publish_records: List[tuple[Path, Path, bool]] = []
        project_video_artifact: Any = None
        project_video_path = ""
        project_depth_artifact: Any = None
        project_depth_path = ""
        project_motion_guide_artifact: Any = None
        project_motion_guide_path = ""
        with _playblast_publish_guard(scene_path):
            try:
                color_records = self._publish_validated_playblast_artifact(
                    staged_video=staged_video_path,
                    staged_sidecar=actual_sidecar,
                    target_video=video_path,
                    target_sidecar=sidecar_path,
                    backup_folder=job_folder / "publish-backup" / "color",
                    label=f"@video{video_slot} Color",
                )
                publish_records.extend(color_records)
                try:
                    color_project_records: List[tuple[Path, Path, bool]] = []
                    project_video_artifact, project_video_path = (
                        _copy_video_to_griptape_project(
                            self,
                            video_path,
                            video_slot,
                            transaction_records=color_project_records,
                            backup_folder=(
                                job_folder / "project-publish-backup" / "color"
                            ),
                        )
                    )
                    project_publish_records.extend(color_project_records)
                except Exception as exc:
                    # A valid scene-local Color artifact remains usable even if
                    # the host project-copy service is unavailable.
                    project_video_artifact = _video_artifact(video_path)
                    project_video_path = str(video_path.resolve())
                    warning = (
                        "Color was published scene-locally because the optional "
                        f"Griptape project copy failed: {_clean(exc) or exc.__class__.__name__}"
                    )
                    if warning not in warnings:
                        warnings.append(warning)

                if depth_succeeded:
                    depth_records: List[tuple[Path, Path, bool]] = []
                    depth_project_records: List[tuple[Path, Path, bool]] = []
                    try:
                        depth_records = self._publish_validated_playblast_artifact(
                            staged_video=staged_depth_video_path,
                            staged_sidecar=actual_depth_sidecar,
                            target_video=depth_video_path,
                            target_sidecar=depth_sidecar_path,
                            backup_folder=job_folder / "publish-backup" / "depth",
                            label=f"@video{depth_video_slot} Depth",
                        )
                        project_depth_artifact, project_depth_path = (
                            _copy_video_to_griptape_project(
                                self,
                                depth_video_path,
                                depth_video_slot,
                                transaction_records=depth_project_records,
                                backup_folder=(
                                    job_folder / "project-publish-backup" / "depth"
                                ),
                            )
                        )
                    except Exception as exc:
                        if depth_project_records:
                            self._restore_playblast_bundle(depth_project_records)
                        if depth_records:
                            self._restore_playblast_bundle(depth_records)
                        depth_succeeded = False
                        project_depth_artifact = None
                        project_depth_path = ""
                        record_auxiliary_failure(
                            f"@video{depth_video_slot} Depth publication",
                            exc,
                        )
                    else:
                        publish_records.extend(depth_records)
                        project_publish_records.extend(depth_project_records)

                if motion_guide_succeeded:
                    motion_records: List[tuple[Path, Path, bool]] = []
                    motion_project_records: List[tuple[Path, Path, bool]] = []
                    try:
                        motion_records = self._publish_validated_playblast_artifact(
                            staged_video=staged_motion_guide_video_path,
                            staged_sidecar=actual_motion_guide_sidecar,
                            target_video=motion_guide_video_path,
                            target_sidecar=motion_guide_sidecar_path,
                            backup_folder=job_folder / "publish-backup" / "motion",
                            label=f"@video{motion_guide_video_slot} Motion Guide",
                        )
                        (
                            project_motion_guide_artifact,
                            project_motion_guide_path,
                        ) = _copy_video_to_griptape_project(
                            self,
                            motion_guide_video_path,
                            motion_guide_video_slot,
                            transaction_records=motion_project_records,
                            backup_folder=(
                                job_folder / "project-publish-backup" / "motion"
                            ),
                        )
                    except Exception as exc:
                        if motion_project_records:
                            self._restore_playblast_bundle(motion_project_records)
                        if motion_records:
                            self._restore_playblast_bundle(motion_records)
                        motion_guide_succeeded = False
                        project_motion_guide_artifact = None
                        project_motion_guide_path = ""
                        record_auxiliary_failure(
                            f"@video{motion_guide_video_slot} Motion Guide publication",
                            exc,
                        )
                    else:
                        publish_records.extend(motion_records)
                        project_publish_records.extend(motion_project_records)

                # Final matched-bundle metadata reflects only artifacts that
                # actually committed. Updating JSON is atomic and never touches
                # the already validated Color MP4.
                bundle_run_id = (
                    bundle_run_id
                    if depth_succeeded or motion_guide_succeeded
                    else ""
                )
                pair_run_id = bundle_run_id if depth_succeeded else ""
                for warning in auxiliary_failure_warnings:
                    if warning not in warnings:
                        warnings.append(warning)
                sidecar.update({
                    "pair_run_id": pair_run_id,
                    "bundle_run_id": bundle_run_id,
                    "paired_depth_video_slot": (
                        depth_video_slot if depth_succeeded else 0
                    ),
                    "paired_motion_guide_video_slot": (
                        motion_guide_video_slot if motion_guide_succeeded else 0
                    ),
                    "warnings": warnings,
                    "auxiliary_failure_details": list(
                        auxiliary_failure_details
                    ),
                })
                _write_json(sidecar_path, sidecar)
                self._assert_operation_current(
                    context,
                    "PLAYBLAST per-artifact copy completion",
                )

                state = {
                    **self._picker_state(),
                    "mode": "maya",
                    "status": "VIDEO_READY",
                    "scene_stage": "VIDEO_READY",
                    "message": (
                        "Mask playblast validated for video-history append with "
                        f"{len(markers)} Group Name + Color Pick bindings."
                    ),
                    "video_path": str(video_path).replace("\\", "/"),
                    "project_video_path": project_video_path,
                    "video_metadata": dict(
                        getattr(project_video_artifact, "meta", {}) or {}
                    ),
                    "video_url": _external_media_url(video_path),
                    "scene_path": str(scene_path).replace("\\", "/"),
                    "camera": _clean(sidecar.get("camera")),
                    "source_fps": source_fps,
                    "output_fps": output_fps,
                    "output_width": output_width,
                    "output_height": output_height,
                    "source_frame_count": source_frame_count,
                    "output_frame_count": output_frame_count,
                    "decoded_frame_count": output_frame_count,
                    "source_duration_seconds": source_duration,
                    "output_duration_seconds": output_duration,
                    "has_maya_frame_range": True,
                    "markers": markers,
                    "warnings": warnings,
                    "original_preview_enabled": False,
                    "snapshot_active": False,
                    "snapshot_video_slot": 0,
                    "snapshot_data_uri": "",
                    "snapshot_path": "",
                    "snapshot_url": "",
                    "snapshot_sha256": "",
                    "viewport_mode": "video",
                    "snapshot_request_video_uid": "",
                    "workspace_view": "playblast",
                    "pair_run_id": pair_run_id,
                    "bundle_run_id": bundle_run_id,
                    "depth_video_slot": depth_video_slot if depth_succeeded else 0,
                    "motion_guide_video_slot": (
                        motion_guide_video_slot if motion_guide_succeeded else 0
                    ),
                }
                if depth_succeeded:
                    mask_item = next(
                        (
                            item
                            for item in reversed(state.get("videos", []))
                            if isinstance(item, dict)
                            and _clean(item.get("run_id")) == _clean(state.get("run_id"))
                            and _clean(item.get("generation_role")) == "mask"
                        ),
                        {},
                    )
                    mask_uid = _clean(mask_item.get("video_uid"))
                    state = _append_video_asset(state, {
                        "video_slot": depth_video_slot,
                        "video_path": str(depth_video_path).replace("\\", "/"),
                        "project_video_path": project_depth_path,
                        "video_metadata": dict(
                            getattr(project_depth_artifact, "meta", {}) or {}
                        ),
                        "video_url": _external_media_url(depth_video_path),
                        "camera": _clean(depth_sidecar.get("camera")),
                        "markers": [],
                        "source_fps": source_fps,
                        "output_fps": output_fps,
                        "output_width": output_width,
                        "output_height": output_height,
                        "source_frame_count": source_frame_count,
                        "output_frame_count": output_frame_count,
                        "decoded_frame_count": output_frame_count,
                        "source_duration_seconds": source_duration,
                        "output_duration_seconds": output_duration,
                        "start_frame": float(
                            depth_sidecar.get("start_frame") or 0.0
                        ),
                        "end_frame": float(
                            depth_sidecar.get("end_frame") or 0.0
                        ),
                        "has_maya_frame_range": True,
                        "media_kind": DEPTH_MEDIA_KIND,
                        "video_role": "maya_depth_companion",
                        "source_type_hint": DEPTH_SOURCE_TYPE,
                        "control_role_hint": DEPTH_CONTROL_ROLE,
                        "companion_of_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                        "source_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                        "pair_run_id": pair_run_id,
                        "bundle_run_id": bundle_run_id,
                        "depth_profile": DEPTH_PLAYBLAST_PROFILE,
                        "depth_range_report": depth_range_report,
                        "generation_role": "depth",
                        "companion_video_uid": mask_uid,
                        "source_video_uid": mask_uid,
                        "label": "Depth",
                    }, picker_shot_uuid=(
                        context.picker_shot_uuid if context is not None else ""
                    ))
                    state["message"] = (
                        "Mask and Depth were validated for video-history append with "
                        f"{len(markers)} Group Name + Color Pick bindings."
                    )
                    merged_warnings = list(warnings)
                    for warning in depth_warnings:
                        if warning not in merged_warnings:
                            merged_warnings.append(warning)
                    state["warnings"] = merged_warnings[-20:]
                if motion_guide_succeeded:
                    mask_item = next(
                        (
                            item
                            for item in reversed(state.get("videos", []))
                            if isinstance(item, dict)
                            and _clean(item.get("run_id")) == _clean(state.get("run_id"))
                            and _clean(item.get("generation_role")) == "mask"
                        ),
                        {},
                    )
                    mask_uid = _clean(mask_item.get("video_uid"))
                    state = _append_video_asset(state, {
                        "video_slot": motion_guide_video_slot,
                        "video_path": str(
                            motion_guide_video_path
                        ).replace("\\", "/"),
                        "project_video_path": project_motion_guide_path,
                        "video_metadata": dict(
                            getattr(
                                project_motion_guide_artifact,
                                "meta",
                                {},
                            )
                            or {}
                        ),
                        "video_url": _external_media_url(
                            motion_guide_video_path
                        ),
                        "camera": _clean(
                            motion_guide_sidecar.get("camera")
                        ),
                        "markers": [],
                        "source_fps": source_fps,
                        "output_fps": output_fps,
                        "output_width": output_width,
                        "output_height": output_height,
                        "source_frame_count": source_frame_count,
                        "output_frame_count": output_frame_count,
                        "decoded_frame_count": output_frame_count,
                        "source_duration_seconds": source_duration,
                        "output_duration_seconds": output_duration,
                        "start_frame": float(
                            motion_guide_sidecar.get("start_frame") or 0.0
                        ),
                        "end_frame": float(
                            motion_guide_sidecar.get("end_frame") or 0.0
                        ),
                        "has_maya_frame_range": True,
                        "media_kind": MOTION_GUIDE_MEDIA_KIND,
                        "video_role": "maya_motion_guide_companion",
                        "source_type_hint": MOTION_GUIDE_SOURCE_TYPE,
                        "control_role_hint": MOTION_GUIDE_CONTROL_ROLE,
                        "companion_of_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                        "source_video_slot": PRIMARY_COLOR_VIDEO_SLOT,
                        "bundle_run_id": bundle_run_id,
                        "motion_guide_profile": MOTION_GUIDE_PROFILE,
                        "motion_guide_sidecar_path": str(
                            motion_guide_sidecar_path
                        ).replace("\\", "/"),
                        "motion_guide_report": (
                            _compact_motion_guide_report_for_state(
                                motion_guide_sidecar.get(
                                    "motion_guide_report"
                                )
                            )
                        ),
                        "generation_role": "motion_guide",
                        "companion_video_uid": mask_uid,
                        "source_video_uid": mask_uid,
                        "label": "Motion Guide",
                    }, picker_shot_uuid=(
                        context.picker_shot_uuid if context is not None else ""
                    ))
                    if depth_succeeded:
                        state["message"] = (
                            "Mask, Depth, and Motion Guide were validated for "
                            f"video-history append with {len(markers)} Group Name "
                            "+ Color Pick bindings."
                        )
                    else:
                        state["message"] = (
                            "Mask and Motion Guide were validated for video-history "
                            f"append with {len(markers)} Group Name + Color Pick "
                            "bindings."
                        )
                    merged_warnings = list(state.get("warnings") or [])
                    for warning in motion_guide_warnings:
                        if warning not in merged_warnings:
                            merged_warnings.append(warning)
                    state["warnings"] = merged_warnings[-20:]
                if publish_public:
                    state = self._mark_operation_finished(state)
                for failure_warning in auxiliary_failure_warnings:
                    _append_activity_log(
                        state,
                        "ERROR",
                        failure_warning,
                    )
                _append_activity_log(
                    state,
                    "SUCCESS",
                    (
                        "Mask, Depth, and Motion Guide completed as independently "
                        "validated append-only artifacts "
                        f"with Maya {maya_version}: {len(markers)} marker "
                        f"binding(s), {output_frame_count} frame(s) each, "
                        f"{output_fps:g} FPS in "
                        f"{state.get('last_operation_seconds', 0.0):.1f} seconds."
                        if depth_succeeded and motion_guide_succeeded
                        else
                        "Mask and Depth completed as independently validated "
                        "append-only artifacts "
                        f"with Maya {maya_version}: {len(markers)} marker "
                        f"binding(s), {output_frame_count} frame(s) each, "
                        f"{output_fps:g} FPS in "
                        f"{state.get('last_operation_seconds', 0.0):.1f} seconds."
                        if depth_succeeded
                        else
                        "Mask and Motion Guide completed as independently validated "
                        f"append-only artifacts in Maya {maya_version}: {len(markers)} "
                        f"marker binding(s), {output_frame_count} frame(s) "
                        f"each, {output_fps:g} FPS in "
                        f"{state.get('last_operation_seconds', 0.0):.1f} "
                        "seconds."
                        if motion_guide_succeeded
                        else
                        f"Mask completed as an append-only artifact with Maya {maya_version}: "
                        f"{len(markers)} marker binding(s), "
                        f"{output_frame_count} frame(s), {output_fps:g} FPS in "
                        f"{state.get('last_operation_seconds', 0.0):.1f} seconds."
                    ),
                )
                self._hmb_video_output = project_video_artifact
                self._assert_operation_current(
                    context,
                    "PLAYBLAST state publication",
                )
                picker_text = self._publish_outputs(
                    state,
                    video_slot,
                    publish_public=publish_public,
                    picker_shot_uuid=(
                        context.picker_shot_uuid if context is not None else ""
                    ),
                )
            except Exception as publish_exc:
                rollback_errors: List[str] = []
                try:
                    self._restore_playblast_bundle(
                        project_publish_records
                    )
                except Exception as restore_exc:
                    rollback_errors.append(
                        f"Griptape project artifacts: {restore_exc}"
                    )
                try:
                    self._restore_playblast_bundle(publish_records)
                except Exception as restore_exc:
                    rollback_errors.append(
                        f"scene bundle: {restore_exc}"
                    )
                try:
                    self._write_state(previous_picker_state)
                    if publish_public:
                        self._sync_outputs_from_state(previous_picker_state)
                except Exception as restore_exc:
                    rollback_errors.append(
                        f"Picker state/output metadata: {restore_exc}"
                    )
                    _diagnostic_exception(
                        "Picker state rollback failed after paired publish error",
                        restore_exc,
                    )
                if rollback_errors:
                    raise RuntimeError(
                        "Playblast publication failed and rollback was "
                        "incomplete ("
                        + "; ".join(rollback_errors)
                        + ")."
                    ) from publish_exc
                raise
        return {
            "mode": "maya",
            "video_slot": video_slot,
            "video": str(video_path),
            "json": str(sidecar_path),
            "source_fps": source_fps,
            "output_fps": output_fps,
            "output_width": output_width,
            "output_height": output_height,
            "source_frame_count": source_frame_count,
            "output_frame_count": output_frame_count,
            "source_duration_seconds": source_duration,
            "output_duration_seconds": output_duration,
            "marker_count": len(markers),
            "picker": picker_text,
            "depth_enabled": depth_enabled,
            "depth_succeeded": depth_succeeded,
            "depth_video_slot": depth_video_slot,
            "depth_video": str(depth_video_path) if depth_succeeded else "",
            "depth_json": str(depth_sidecar_path) if depth_succeeded else "",
            "depth_profile": DEPTH_PLAYBLAST_PROFILE if depth_succeeded else "",
            "motion_guide_enabled": motion_guide_enabled,
            "motion_guide_succeeded": motion_guide_succeeded,
            "motion_guide_video_slot": motion_guide_video_slot,
            "motion_guide_video": (
                str(motion_guide_video_path)
                if motion_guide_succeeded
                else ""
            ),
            "motion_guide_json": (
                str(motion_guide_sidecar_path)
                if motion_guide_succeeded
                else ""
            ),
            "motion_guide_profile": (
                MOTION_GUIDE_PROFILE if motion_guide_succeeded else ""
            ),
        }

    def process(self) -> None:
        """Refresh Picker/Video outputs without starting Maya or FFmpeg.

        Playblast is an explicit dashboard-button action.  A downstream graph run
        may execute this node repeatedly, so process() must remain a cheap,
        side-effect-free synchronization step just like HMBPromptLibrary.process().
        """
        self._ensure_parameters()
        self._reconcile_shared_shot_routing()
        state = self._apply_selected_view_fields(self._picker_state())
        # The workflow executor propagates process outputs through the graph.
        # Explicit late-worker forwarding here would deliver every value twice.
        self._sync_outputs_from_state(state, propagate_connections=False)
        return None
