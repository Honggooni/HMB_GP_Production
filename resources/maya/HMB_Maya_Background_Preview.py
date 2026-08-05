# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import io
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
import time
import traceback
import zlib

import maya.cmds as cmds

DATA_NODE = "HMBVideoPickerData"
MARKER_CATALOG = {}
MARKER_COLORS = {}
MARKER_PATTERNS = {}
MARKER_PATTERN_IDS = {}
MARKER_OPTIONS = []
CHARACTER_MARKERS = set()
BACKGROUND_MARKERS = set()
REPEATABLE_MARKERS = set()
NEUTRAL_RGB = (0.0, 0.0, 0.0)
CHARACTER_LAMBERT_DIFFUSE = 0.55
CHARACTER_LAMBERT_AMBIENT_GAIN = 0.0
CHARACTER_LAMBERT_INCANDESCENCE_GAIN = 0.25
CHARACTER_VISUAL_PROFILE = "color_stable_lambert_profile"
CHARACTER_OUTLINE_NATIVE = "native_lambert"
CHARACTER_OUTLINE_PFX = "pfx_toon"
CHARACTER_OUT_RIM_OPACITY = 0.08
CHARACTER_OUT_RIM_MIN_PIXEL_WIDTH = 0.35
CHARACTER_OUT_RIM_MAX_PIXEL_WIDTH = 0.6
CHARACTER_OUT_RIM_LINE_OFFSET = 0.0
CHARACTER_OUT_RIM_SCREENSPACE_RESAMPLING = 0.0
CHARACTER_OUT_RIM_LOCAL_OCCLUSION = 2
FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE = "hmb_full_smooth_geometry_v2"
ORIGINAL_VIEWPORT_QUALITY_PROFILE = FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
SCREEN_SPACE_PATTERN_PROFILE = "hmb_screen_space_pattern_post_v2"
SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR = 3
SCREEN_SPACE_PATTERN_BASE_CELL_DIVISOR = 8
SCREEN_SPACE_PATTERN_CELL_DIVISOR = (
    SCREEN_SPACE_PATTERN_BASE_CELL_DIVISOR
    * SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR
)
SCREEN_SPACE_PATTERN_MIN_CELL_PIXELS = 4
POSITION_PATTERN_REPEATS = SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR
DEPTH_PLAYBLAST_PROFILE = "hmb_camera_space_depth_v7"
# Production Depth uses the full 0.0..0.9 signal range.  The final 0.1 is
# deliberately left unused so near-plane/bounds approximation cannot turn a
# close subject into clipped pure white.
DEPTH_NEAR_COLOR = 0.9
DEPTH_FAR_COLOR = 0.0
DEPTH_CAMERA_NEAR_SAFETY_MARGIN = 0.1
DEPTH_CONTRAST_EXPONENT = 1.0
DEPTH_RANGE_PADDING_FRACTION = 0.0
DEPTH_GRAYSCALE_BUCKET_COUNT = 256
DEPTH_FOREGROUND_NEAR_PERCENTILE = 0.01
DEPTH_FOREGROUND_FAR_PERCENTILE = 0.99
DEPTH_GENERIC_FAR_PERCENTILE = 0.95
DEPTH_GENERIC_PERCENTILE_MIN_SHAPES = 20
DEPTH_SCREEN_VERTEX_SAMPLE_LIMIT = 128
DEPTH_SCREEN_POLYGON_CENTER_SAMPLE_LIMIT = 64
DEPTH_REJECTION_ACCOUNTING_POLICY = "disjoint_normalization_outcomes"
CUTOUT_TRANSPARENCY_POLICY = "preserve_authored_material_out_transparency_v1"
MOUTH_CARD_INNER_PATCH_POLICY = "temporary_mouth_alpha_inner_patch_v1"
MOUTH_CARD_GRID_VERTEX_COUNT = 49
MOUTH_CARD_GRID_EDGE_COUNT = 84
MOUTH_CARD_GRID_FACE_COUNT = 36
MOUTH_CARD_GRID_OUTER_FACE_COUNT = 20
MOUTH_CARD_GRID_INNER_FACE_COUNT = 16
MOUTH_CARD_UV_TOLERANCE = 2.0e-5
MOTION_GUIDE_PROFILE = "hmb_target_neutral_motion_guide_v5"
MOTION_GUIDE_SCHEMA = "hmb-maya-motion-guide"
MOTION_GUIDE_SCHEMA_VERSION = 2
MOTION_GUIDE_MAX_JOINTS_PER_TARGET = 48
MOTION_GUIDE_TRAIL_LENGTH = 48
MOTION_GUIDE_MAX_FACE_CHANNELS_PER_TARGET = 256
MOTION_GUIDE_MAX_FACE_DRIVERS_PER_TARGET = 256
MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES = 6
MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE = 32
MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE = 64
MOTION_GUIDE_BACKGROUND_RGB = (0, 0, 0)
MOTION_GUIDE_BONE_RGB = (245, 245, 245)
MOTION_GUIDE_JOINT_RGB = (0, 224, 230)
MOTION_GUIDE_ROOT_RGB = (255, 224, 0)
MOTION_GUIDE_HAND_RGB = (240, 0, 210)
MOTION_GUIDE_FOOT_RGB = (0, 235, 92)
MOTION_GUIDE_TRAIL_RGB = (255, 132, 0)
MOTION_GUIDE_AXIS_X_RGB = (255, 48, 48)
MOTION_GUIDE_AXIS_Y_RGB = (48, 235, 80)
MOTION_GUIDE_AXIS_Z_RGB = (64, 112, 255)
MOTION_GUIDE_FACE_BROW_RGB = (176, 96, 255)
MOTION_GUIDE_FACE_EYE_RGB = (48, 196, 255)
MOTION_GUIDE_FACE_MOUTH_RGB = (255, 72, 180)
MOTION_GUIDE_FACE_JAW_RGB = (255, 176, 64)
MOTION_GUIDE_FACE_FIRST_HIT_TOLERANCE_FRACTION = 0.005
MOTION_GUIDE_PNG_COMPRESSION_LEVEL = 3


def _read_json(path):
    with io.open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError("Job JSON must contain an object: {0}".format(path))
    return data


def _is_reparse_or_symlink(path):
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    return os.path.islink(path) or bool(attributes & 0x400)


def _assert_private_job_path(job_root, value, label):
    """Allow runner writes/deletes only below the verified job directory."""
    job_root = os.path.abspath(job_root)
    candidate = os.path.abspath(_clean(value))
    if not candidate:
        raise RuntimeError("Runner job path is empty: {0}".format(label))
    try:
        if os.path.commonpath([job_root, candidate]) != job_root:
            raise RuntimeError(
                "Runner job path escapes its private directory ({0}): {1}".format(
                    label, candidate
                )
            )
    except ValueError:
        raise RuntimeError(
            "Runner job path uses a different drive ({0}): {1}".format(
                label, candidate
            )
        )
    relative = os.path.relpath(candidate, job_root)
    current = job_root
    if _is_reparse_or_symlink(current):
        raise RuntimeError(
            "Runner private directory is a symlink or Windows junction: {0}".format(
                current
            )
        )
    for part in relative.split(os.sep):
        if part in ("", "."):
            continue
        current = os.path.join(current, part)
        if (os.path.lexists(current) and _is_reparse_or_symlink(current)):
            raise RuntimeError(
                "Runner path traverses a symlink or Windows junction ({0}): {1}".format(
                    label, current
                )
            )
    real_root = os.path.realpath(job_root)
    real_candidate = os.path.realpath(candidate)
    try:
        if os.path.commonpath([real_root, real_candidate]) != real_root:
            raise RuntimeError(
                "Runner path resolves outside its private directory ({0}): {1}".format(
                    label, candidate
                )
            )
    except ValueError:
        raise RuntimeError(
            "Runner path resolves to a different drive ({0}): {1}".format(
                label, candidate
            )
        )
    return candidate


def _validate_job_write_paths(job_path, job):
    job_root = os.path.dirname(os.path.abspath(job_path))
    _assert_private_job_path(job_root, job_path, "job_path")
    required_fields = ("result_path",)
    optional_fields = (
        "progress_path",
        "frames_folder",
        "sidecar_path",
        "depth_frames_folder",
        "depth_sidecar_path",
        "motion_guide_frames_folder",
        "motion_guide_sidecar_path",
    )
    for field in required_fields:
        _assert_private_job_path(job_root, job.get(field), field)
    for field in optional_fields:
        value = _clean(job.get(field))
        if value:
            _assert_private_job_path(job_root, value, field)


def _load_marker_catalog(job):
    global MARKER_CATALOG, MARKER_COLORS, MARKER_PATTERNS, MARKER_OPTIONS
    global MARKER_PATTERN_IDS
    global CHARACTER_MARKERS, BACKGROUND_MARKERS, REPEATABLE_MARKERS
    path = os.path.abspath(_clean((job or {}).get("marker_catalog_path")))
    if not path or not os.path.isfile(path):
        raise RuntimeError("HMB marker catalog was not found: {0}".format(path or "<empty>"))
    payload = _read_json(path)
    if payload.get("schema") != "hmb-marker-catalog":
        raise RuntimeError("Invalid HMB marker catalog schema.")
    expected_version = int((job or {}).get("marker_catalog_version") or 0)
    actual_version = int(payload.get("version") or 0)
    if expected_version and actual_version != expected_version:
        raise RuntimeError(
            "HMB marker catalog version mismatch: expected {0}, got {1}.".format(
                expected_version, actual_version
            )
        )
    character_rows = [dict(item) for item in payload.get("character", []) if isinstance(item, dict)]
    background_rows = [dict(item) for item in payload.get("background", []) if isinstance(item, dict)]
    rows = character_rows + background_rows
    actor_count = len(character_rows)
    object_count = len(background_rows)
    names = [_clean(item.get("name")) for item in rows]
    if actor_count != 7 or object_count != 7 or len(names) != len(set(names)) or any(not name for name in names):
        raise RuntimeError("HMB marker catalog must contain seven Actor and seven Object choices.")
    colors = {}
    patterns = {}
    pattern_ids = {}
    seen_pattern_ids = set()
    for item in rows:
        name = _clean(item.get("name"))
        kind = _clean(item.get("kind")).lower()
        if kind == "solid":
            rgb = item.get("rgb")
            if not isinstance(rgb, list) or len(rgb) != 3:
                raise RuntimeError("Solid marker has invalid RGB data: {0}".format(name))
            colors[name] = tuple(float(channel) for channel in rgb)
        elif kind == "pattern":
            pattern = _clean(item.get("pattern"))
            if not pattern:
                raise RuntimeError("Pattern marker has no pattern key: {0}".format(name))
            raw_id = item.get("screen_space_id_rgb")
            if (
                not isinstance(raw_id, list)
                or len(raw_id) != 3
                or any(
                    isinstance(channel, bool)
                    or not isinstance(channel, (int, float))
                    or int(channel) != channel
                    or int(channel) < 0
                    or int(channel) > 255
                    for channel in raw_id
                )
            ):
                raise RuntimeError(
                    "Pattern marker has invalid screen-space ID RGB data: {0}".format(name)
                )
            id_rgb = tuple(int(channel) for channel in raw_id)
            if id_rgb in seen_pattern_ids:
                raise RuntimeError(
                    "Pattern markers must use unique screen-space ID RGB values."
                )
            seen_pattern_ids.add(id_rgb)
            patterns[name] = pattern
            pattern_ids[name] = id_rgb
        else:
            raise RuntimeError("Marker has unsupported kind: {0}".format(name))
    MARKER_CATALOG = payload
    MARKER_COLORS = colors
    MARKER_PATTERNS = patterns
    MARKER_PATTERN_IDS = pattern_ids
    MARKER_OPTIONS = names
    CHARACTER_MARKERS = set(_clean(item.get("name")) for item in character_rows)
    BACKGROUND_MARKERS = set(_clean(item.get("name")) for item in background_rows)
    REPEATABLE_MARKERS = set(BACKGROUND_MARKERS)
    if any(name not in MARKER_COLORS for name in CHARACTER_MARKERS):
        raise RuntimeError("All seven Character markers must be solid Lambert colors.")
    return payload


def _write_json(path, payload):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)



def _emit_console(level, message):
    text = "[HMBVideoPicker][{0}] {1}".format(_clean(level).upper() or "INFO", _clean(message))
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _write_progress(job, stage, message, **extra):
    stage_text = _clean(stage) or "maya_progress"
    message_text = _clean(message) or stage_text
    _emit_console("PROGRESS", "[{0}] {1}".format(stage_text, message_text))
    progress_path = _clean((job or {}).get("progress_path"))
    if not progress_path:
        return
    payload = {
        "stage": stage_text,
        "message": message_text,
        "time": time.time(),
    }
    payload.update(extra)
    temp_path = progress_path + ".tmp"
    try:
        _write_json(temp_path, payload)
        last_error = None
        for attempt in range(20):
            try:
                os.replace(temp_path, progress_path)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                if attempt >= 19:
                    raise
                time.sleep(min(0.01 * (attempt + 1), 0.1))
        if last_error is not None:
            raise last_error
    except Exception as exc:
        _emit_console("WARNING", "Progress file write failed: {0}".format(exc))
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _reference_nodes():
    result = []
    for node in cmds.ls(type="reference") or []:
        node_text = _clean(node)
        if (
            node_text in ("sharedReferenceNode", "_UNKNOWN_REF_NODE_")
            or node_text.lower().endswith("sharedreferencenode")
        ):
            continue
        result.append(node_text)
    return sorted(set(result))


def _proxy_reference_sets():
    """Return proxy-manager records without loading an inactive proxy.

    A proxyManager connects each proxyList element to one reference node and
    connects activeProxy to exactly one of those elements. Loading every
    reference node independently defeats Maya's proxy contract and can place
    both high- and low-resolution geometry in the scene at once.
    """
    records = []
    try:
        managers = cmds.ls(type="proxyManager") or []
    except Exception:
        managers = []
    for manager in sorted(set(managers)):
        members = []
        try:
            indices = cmds.getAttr(manager + ".proxyList", multiIndices=True) or []
        except Exception:
            indices = []
        for index in indices:
            list_plug = "{0}.proxyList[{1}]".format(manager, int(index))
            try:
                destinations = cmds.connectionInfo(
                    list_plug,
                    destinationFromSource=True,
                ) or []
            except Exception:
                destinations = []
            if not isinstance(destinations, (list, tuple)):
                destinations = [destinations] if destinations else []
            reference_nodes = []
            for destination in destinations:
                node = _clean(destination).split(".", 1)[0]
                try:
                    is_reference = (
                        node
                        and node not in ("sharedReferenceNode", "_UNKNOWN_REF_NODE_")
                        and cmds.objExists(node)
                        and cmds.nodeType(node) == "reference"
                    )
                except Exception:
                    is_reference = False
                if is_reference:
                    reference_nodes.append(node)
            reference_nodes = sorted(set(reference_nodes))
            if len(reference_nodes) != 1:
                continue
            reference_node = reference_nodes[0]
            tag = ""
            file_name = ""
            try:
                if cmds.attributeQuery("proxyTag", node=reference_node, exists=True):
                    tag = _clean(cmds.getAttr(reference_node + ".proxyTag"))
            except Exception:
                tag = ""
            try:
                file_name = _clean(
                    cmds.referenceQuery(
                        reference_node,
                        filename=True,
                        withoutCopyNumber=False,
                    )
                )
            except Exception:
                file_name = ""
            members.append({
                "list_plug": list_plug,
                "reference_node": reference_node,
                "proxy_tag": tag,
                "reference_file": file_name,
            })

        active_reference = ""
        try:
            active_destinations = cmds.connectionInfo(
                manager + ".activeProxy",
                destinationFromSource=True,
            ) or []
        except Exception:
            active_destinations = []
        if not isinstance(active_destinations, (list, tuple)):
            active_destinations = [active_destinations] if active_destinations else []
        if len(active_destinations) == 1:
            matches = [
                _clean(member.get("reference_node"))
                for member in members
                if _clean(member.get("list_plug")) == _clean(active_destinations[0])
            ]
            if len(matches) == 1:
                active_reference = matches[0]
        records.append({
            "proxy_manager": manager,
            "active_reference": active_reference,
            "members": members,
        })
    return records


def _proxy_high_quality_rank(member):
    """Rank only explicit, conventional high-detail proxy identifiers."""
    tag = _clean((member or {}).get("proxy_tag")).lower()
    tag_key = re.sub(r"[\s_.-]+", "", tag)
    ordered_tags = {
        "high": 120,
        "highres": 120,
        "hires": 120,
        "hirez": 120,
        "highresolution": 120,
        "render": 115,
        "rendering": 115,
        "renderres": 115,
        "renderresolution": 115,
        "final": 110,
        "hero": 95,
    }
    return ordered_tags.get(tag_key, 0)


def _selected_proxy_reference(record, force_high_quality):
    members = list((record or {}).get("members") or [])
    active = _clean((record or {}).get("active_reference"))
    if force_high_quality and members:
        ranked = sorted(
            (
                (_proxy_high_quality_rank(member), _clean(member.get("reference_node")), member)
                for member in members
            ),
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )
        if ranked and ranked[0][0] > 0:
            top_rank = ranked[0][0]
            top = [item for item in ranked if item[0] == top_rank]
            if len(top) == 1:
                return _clean(top[0][1]), "explicit_high_quality_proxy"
        if len(members) == 1:
            return _clean(members[0].get("reference_node")), "single_proxy"
        return active, "high_quality_proxy_unresolved"
    if active:
        return active, "authored_active_proxy"
    if len(members) == 1:
        return _clean(members[0].get("reference_node")), "single_proxy"
    return "", "ambiguous_proxy_set"


def _switch_proxy_reference(reference_node):
    """Activate through Maya's official connection logic, then load safely.

    proxySwitch/proxyActivate(..., true) uses MEL ``file -lr`` internally,
    which executes scriptNodes from the referenced file. The background
    picker must keep script execution disabled for every reference load.
    """
    import maya.mel as mel

    escaped = _clean(reference_node).replace("\\", "\\\\").replace('"', '\\"')
    mel.eval('proxyActivate("{0}", false)'.format(escaped))
    try:
        loaded = bool(cmds.referenceQuery(reference_node, isLoaded=True))
    except Exception:
        loaded = False
    if not loaded:
        cmds.file(loadReference=reference_node, executeScriptNodes=False)


def _load_all_references_with_progress(job):
    processed = set()
    failed_nodes = set()
    warnings = []
    processed_proxy_managers = set()
    cleaned_proxy_members = set()
    force_high_quality = bool((job or {}).get("force_high_quality_viewport"))
    reference_report = {
        "standard_reference_loaded_count": 0,
        "proxy_set_count": 0,
        "proxy_reference_loaded_count": 0,
        "proxy_high_quality_switch_count": 0,
        "proxy_inactive_unload_count": 0,
        "high_quality_unresolved_proxy_sets": [],
        "failed_references": [],
        "proxy_sets": [],
    }

    def record_proxy_selection(proxy_record, node, newly_loaded):
        manager = _clean((proxy_record or {}).get("manager"))
        if not manager or manager in processed_proxy_managers:
            return
        processed_proxy_managers.add(manager)
        reason = _clean((proxy_record or {}).get("reason"))
        reference_report["proxy_reference_loaded_count"] += int(bool(newly_loaded))
        if reason == "explicit_high_quality_proxy":
            reference_report["proxy_high_quality_switch_count"] += int(
                _clean((proxy_record or {}).get("active_reference")) != node
            )
        reference_report["proxy_sets"].append({
            "proxy_manager": manager,
            "selected_reference": node,
            "selection_reason": reason,
            "proxy_tag": next(
                (
                    _clean(member.get("proxy_tag"))
                    for member in (proxy_record or {}).get("members") or []
                    if _clean(member.get("reference_node")) == node
                ),
                "",
            ),
        })

    def validate_proxy_selection(proxy_record, node):
        manager = _clean((proxy_record or {}).get("manager"))
        validation_record = next(
            (
                record
                for record in _proxy_reference_sets()
                if _clean(record.get("proxy_manager")) == manager
            ),
            {},
        )
        active_after = _clean(validation_record.get("active_reference"))
        loaded_after = []
        for member in validation_record.get("members") or []:
            member_node = _clean(member.get("reference_node"))
            try:
                if member_node and bool(cmds.referenceQuery(member_node, isLoaded=True)):
                    loaded_after.append(member_node)
            except Exception:
                pass
        if active_after == node and loaded_after == [node]:
            return True
        warning = (
            "Proxy set {0} failed exclusive-load validation: selected={1}, "
            "active={2}, loaded={3}."
        ).format(manager, node, active_after or "<none>", loaded_after)
        if warning not in warnings:
            warnings.append(warning)
            _emit_console("WARNING", warning)
        failure_record = {
            "reference_kind": "proxy",
            "proxy_manager": manager,
            "reference_node": node,
            "reference_file": "",
            "error": "exclusive-load validation failed",
        }
        if failure_record not in reference_report["failed_references"]:
            reference_report["failed_references"].append(failure_record)
        if force_high_quality:
            unresolved_record = {
                "proxy_manager": manager,
                "active_reference": active_after,
                "available_tags": [
                    _clean(member.get("proxy_tag"))
                    for member in validation_record.get("members") or []
                ],
            }
            if unresolved_record not in reference_report["high_quality_unresolved_proxy_sets"]:
                reference_report["high_quality_unresolved_proxy_sets"].append(unresolved_record)
        return False

    while True:
        proxy_records = _proxy_reference_sets()
        proxy_members = {}
        selected_proxies = {}
        for record in proxy_records:
            manager = _clean(record.get("proxy_manager"))
            selected, reason = _selected_proxy_reference(record, force_high_quality)
            for member in record.get("members") or []:
                node = _clean(member.get("reference_node"))
                if node:
                    proxy_members[node] = manager
            if selected:
                selected_proxies[selected] = {
                    "manager": manager,
                    "reason": reason,
                    "active_reference": _clean(record.get("active_reference")),
                    "members": list(record.get("members") or []),
                }
                if force_high_quality and reason == "high_quality_proxy_unresolved":
                    unresolved_record = {
                        "proxy_manager": manager,
                        "active_reference": _clean(record.get("active_reference")),
                        "available_tags": [
                            _clean(member.get("proxy_tag"))
                            for member in record.get("members") or []
                        ],
                    }
                    if unresolved_record not in reference_report["high_quality_unresolved_proxy_sets"]:
                        reference_report["high_quality_unresolved_proxy_sets"].append(unresolved_record)
                    warning = (
                        "Proxy set {0} has no unique explicit high-quality tag. "
                        "The authored active proxy was retained for metadata safety, "
                        "but Original full-detail rendering will be blocked."
                    ).format(manager)
                    if warning not in warnings:
                        warnings.append(warning)
                        _emit_console("WARNING", warning)
            elif manager and manager not in processed_proxy_managers:
                warning = (
                    "Proxy set {0} was skipped because no unique active or explicit "
                    "high-quality proxy could be selected."
                ).format(manager)
                warnings.append(warning)
                _emit_console("WARNING", warning)
                if force_high_quality:
                    unresolved_record = {
                        "proxy_manager": manager,
                        "active_reference": _clean(record.get("active_reference")),
                        "available_tags": [
                            _clean(member.get("proxy_tag"))
                            for member in record.get("members") or []
                        ],
                    }
                    if unresolved_record not in reference_report["high_quality_unresolved_proxy_sets"]:
                        reference_report["high_quality_unresolved_proxy_sets"].append(unresolved_record)
                processed_proxy_managers.add(manager)

            if manager and manager not in cleaned_proxy_members:
                for member in record.get("members") or []:
                    member_node = _clean(member.get("reference_node"))
                    if not member_node or member_node == selected:
                        continue
                    try:
                        member_loaded = bool(cmds.referenceQuery(member_node, isLoaded=True))
                    except Exception:
                        member_loaded = False
                    if not member_loaded:
                        continue
                    try:
                        cmds.file(unloadReference=member_node)
                        if bool(cmds.referenceQuery(member_node, isLoaded=True)):
                            raise RuntimeError("reference remained loaded")
                        reference_report["proxy_inactive_unload_count"] += 1
                    except Exception as exc:
                        warning = (
                            "Inactive proxy {0} could not be unloaded from {1} ({2})."
                        ).format(member_node, manager, exc)
                        warnings.append(warning)
                        _emit_console("WARNING", warning)
                        if force_high_quality:
                            unresolved_record = {
                                "proxy_manager": manager,
                                "active_reference": _clean(record.get("active_reference")),
                                "available_tags": [
                                    _clean(item.get("proxy_tag"))
                                    for item in record.get("members") or []
                                ],
                            }
                            if unresolved_record not in reference_report["high_quality_unresolved_proxy_sets"]:
                                reference_report["high_quality_unresolved_proxy_sets"].append(unresolved_record)
                cleaned_proxy_members.add(manager)

        pending = []
        for node in _reference_nodes():
            if node in processed:
                continue
            manager = proxy_members.get(node, "")
            if manager and node not in selected_proxies:
                # Inactive members must never be loaded like independent prop or
                # asset references. Maya proxySwitch owns their load state.
                processed.add(node)
                continue
            try:
                loaded = bool(cmds.referenceQuery(node, isLoaded=True))
            except Exception:
                loaded = False
            proxy_record = selected_proxies.get(node)
            needs_proxy_switch = bool(
                proxy_record
                and _clean(proxy_record.get("active_reference")) != node
            )
            if not loaded or needs_proxy_switch:
                pending.append((node, proxy_record, loaded))
            else:
                processed.add(node)
                if proxy_record:
                    record_proxy_selection(proxy_record, node, False)
                    validate_proxy_selection(proxy_record, node)
        if not pending:
            break
        for index, pending_item in enumerate(pending, start=1):
            node, proxy_record, loaded_before = pending_item
            try:
                file_name = _clean(cmds.referenceQuery(node, filename=True, withoutCopyNumber=False))
            except Exception:
                file_name = ""
            label = file_name or node
            reference_kind = "proxy" if proxy_record else "standard"
            _write_progress(
                job,
                "loading_reference",
                "Loading {0} reference {1}/{2}: {3}".format(
                    reference_kind, index, len(pending), label
                ),
                reference_node=node,
                reference_file=file_name,
                reference_kind=reference_kind,
            )
            try:
                if proxy_record and _clean(proxy_record.get("active_reference")) != node:
                    _switch_proxy_reference(node)
                else:
                    cmds.file(loadReference=node, executeScriptNodes=False)
            except Exception as exc:
                warning = "Reference skipped because it could not be loaded: {0} ({1})".format(label, exc)
                warnings.append(warning)
                failed_nodes.add(node)
                processed.add(node)
                failure_record = {
                    "reference_kind": reference_kind,
                    "proxy_manager": _clean((proxy_record or {}).get("manager")),
                    "reference_node": node,
                    "reference_file": file_name,
                    "error": _clean(exc),
                }
                if failure_record not in reference_report["failed_references"]:
                    reference_report["failed_references"].append(failure_record)
                if force_high_quality and proxy_record:
                    unresolved_record = {
                        "proxy_manager": _clean(proxy_record.get("manager")),
                        "active_reference": _clean(proxy_record.get("active_reference")),
                        "available_tags": [
                            _clean(item.get("proxy_tag"))
                            for item in proxy_record.get("members") or []
                        ],
                    }
                    if unresolved_record not in reference_report["high_quality_unresolved_proxy_sets"]:
                        reference_report["high_quality_unresolved_proxy_sets"].append(unresolved_record)
                _emit_console("WARNING", warning)
                _write_progress(
                    job,
                    "reference_load_warning",
                    warning,
                    reference_node=node,
                    reference_file=file_name,
                    skipped_reference_count=len(failed_nodes),
                )
                continue
            processed.add(node)
            if proxy_record:
                record_proxy_selection(proxy_record, node, not loaded_before)
                validate_proxy_selection(proxy_record, node)
            else:
                reference_report["standard_reference_loaded_count"] += 1
    loaded_count = max(0, len(processed) - len(failed_nodes))
    reference_report["proxy_set_count"] = len(processed_proxy_managers)
    job["_reference_report"] = reference_report
    _write_progress(
        job,
        "references_loaded",
        "Scene references processed: {0} nodes resolved, {1} skipped; "
        "{2} proxy set(s) kept mutually exclusive.".format(
            loaded_count,
            len(failed_nodes),
            reference_report["proxy_set_count"],
        ),
        reference_count=loaded_count,
        skipped_reference_count=len(failed_nodes),
        failed_reference_count=len(reference_report["failed_references"]),
        proxy_set_count=reference_report["proxy_set_count"],
        proxy_high_quality_switch_count=reference_report["proxy_high_quality_switch_count"],
    )
    return warnings


def _audit_authored_reference_state(job):
    """Report, but never mutate, Maya's saved reference/proxy state."""
    report = {
        "standard_reference_loaded_count": 0,
        "proxy_set_count": 0,
        "proxy_reference_loaded_count": 0,
        "proxy_high_quality_switch_count": 0,
        "proxy_inactive_unload_count": 0,
        "high_quality_unresolved_proxy_sets": [],
        "failed_references": [],
        "proxy_sets": [],
        "authored_loaded_reference_count": 0,
        "authored_unloaded_reference_count": 0,
        "state_policy": "preserve_authored_reference_and_proxy_state",
    }
    proxy_members = set()
    for record in _proxy_reference_sets():
        members = []
        for member in record.get("members") or []:
            node = _clean(member.get("reference_node"))
            if node:
                proxy_members.add(node)
            members.append({
                "reference_node": node,
                "reference_file": _clean(member.get("reference_file")),
                "proxy_tag": _clean(member.get("proxy_tag")),
            })
        report["proxy_sets"].append({
            "proxy_manager": _clean(record.get("proxy_manager")),
            "selected_reference": _clean(record.get("active_reference")),
            "selection_reason": "authored_active_proxy",
            "switched": False,
            "members": members,
        })
    report["proxy_set_count"] = len(report["proxy_sets"])
    try:
        reference_nodes = sorted(set(cmds.ls(type="reference") or []))
    except Exception:
        reference_nodes = []
    audited = 0
    warnings = []
    for node in reference_nodes:
        if node in ("sharedReferenceNode", "_UNKNOWN_REF_NODE_"):
            continue
        try:
            loaded = bool(cmds.referenceQuery(node, isLoaded=True))
        except Exception as exc:
            warning = "Reference state could not be read for {0}: {1}".format(
                node,
                exc,
            )
            warnings.append(warning)
            report["failed_references"].append({
                "reference_node": node,
                "reference_file": "",
                "error": _clean(exc),
            })
            continue
        audited += 1
        report[
            "authored_loaded_reference_count"
            if loaded
            else "authored_unloaded_reference_count"
        ] += 1
        if loaded and node not in proxy_members:
            report["standard_reference_loaded_count"] += 1
        if loaded and node in proxy_members:
            report["proxy_reference_loaded_count"] += 1
    job["_reference_report"] = report
    _write_progress(
        job,
        "references_preserved",
        "Preserved the scene-authored reference state: {0} node(s) audited; "
        "{1} proxy set(s) left unchanged.".format(
            audited,
            report["proxy_set_count"],
        ),
        reference_count=audited,
        authored_loaded_reference_count=report[
            "authored_loaded_reference_count"
        ],
        authored_unloaded_reference_count=report[
            "authored_unloaded_reference_count"
        ],
        failed_reference_count=len(report["failed_references"]),
        proxy_set_count=report["proxy_set_count"],
        proxy_high_quality_switch_count=0,
    )
    return warnings


def _open_scene_for_job(job):
    scene_path = os.path.abspath(_clean((job or {}).get("scene_path")))
    if not scene_path:
        raise RuntimeError("Job scene_path is empty.")
    if not os.path.isfile(scene_path):
        raise RuntimeError("Maya scene not found: {0}".format(scene_path))
    current = _clean(cmds.file(query=True, sceneName=True))
    already_open = bool(
        current
        and os.path.normcase(os.path.abspath(current)) == os.path.normcase(scene_path)
    )
    if already_open:
        _write_progress(job, "scene_opened", "Scene is already open.")
    else:
        _write_progress(job, "opening_scene", "Opening the main scene with script nodes disabled and its authored reference state preserved.")
        try:
            cmds.file(new=True, force=True)
        except Exception:
            pass
        cmds.file(
            scene_path,
            open=True,
            force=True,
            prompt=False,
            ignoreVersion=True,
            executeScriptNodes=False,
        )
    opened = _clean(cmds.file(query=True, sceneName=True)) or scene_path
    _write_progress(job, "scene_opened", "Main scene opened. Auditing the authored reference state without loading or switching it.")
    job["_reference_warnings"] = _audit_authored_reference_state(job)
    timeline_script = _scene_configuration_script_text()
    script_node_report = _disable_scene_script_nodes()
    job["_script_node_report"] = script_node_report
    restored_timeline = _restore_safe_scene_timeline(timeline_script)
    job["_scene_dependency_paths"] = _scene_dependency_paths(scene_path)
    if restored_timeline:
        _write_progress(
            job,
            "timeline_restored",
            "Restored the saved playback range without executing scene script nodes.",
            **restored_timeline
        )
    _write_progress(
        job,
        "script_nodes_disabled",
        "Disabled {0} scene script node(s) in the disposable Maya session.".format(
            int(script_node_report.get("disabled_count") or 0)
        ),
        script_node_count=int(script_node_report.get("script_node_count") or 0),
        disabled_script_node_count=int(script_node_report.get("disabled_count") or 0),
    )
    _write_progress(job, "scene_ready", "Scene and references are ready. Preparing the requested read.")
    return opened


def _clean(value):
    return str(value or "").strip()


def _flatten_dependency_strings(value):
    result = []
    if isinstance(value, (list, tuple)):
        for item in value:
            result.extend(_flatten_dependency_strings(item))
        return result
    text = _clean(value)
    if text:
        result.append(text)
    return result


def _resolved_dependency_path(raw_value, scene_path, workspace_root):
    value = os.path.expandvars(os.path.expanduser(_clean(raw_value)))
    if not value or "\x00" in value:
        return ""
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value) and not value.lower().startswith("file://"):
        return ""
    if value.lower().startswith("file://"):
        value = value[7:]
    value = re.sub(r"\{\d+\}$", "", value)
    if os.path.isabs(value):
        return os.path.abspath(value)
    bases = [
        _clean(workspace_root),
        os.path.dirname(os.path.abspath(scene_path)),
    ]
    candidates = [
        os.path.abspath(os.path.join(base, value))
        for base in bases
        if base
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[-1] if candidates else os.path.abspath(value)


def _scene_dependency_paths(scene_path):
    """Collect reference and filename-attribute dependencies without reading data."""
    try:
        workspace_root = _clean(cmds.workspace(query=True, rootDirectory=True))
    except Exception:
        workspace_root = ""
    paths = set()

    def add(value):
        resolved = _resolved_dependency_path(value, scene_path, workspace_root)
        if resolved:
            paths.add(resolved.replace("\\", "/"))

    add(scene_path)
    for reference_node in _reference_nodes():
        try:
            add(cmds.referenceQuery(
                reference_node,
                filename=True,
                withoutCopyNumber=True,
            ))
        except Exception:
            try:
                add(cmds.referenceQuery(
                    reference_node,
                    filename=True,
                    withoutCopyNumber=False,
                ))
            except Exception:
                pass

    try:
        listed_files = cmds.file(
            query=True,
            list=True,
            withoutCopyNumber=True,
        ) or []
    except Exception:
        listed_files = []
    for value in _flatten_dependency_strings(listed_files):
        add(value)

    try:
        dependency_nodes = cmds.ls(dependencyNodes=True) or []
    except Exception:
        dependency_nodes = []
    for node in dependency_nodes:
        try:
            attributes = cmds.listAttr(node, usedAsFilename=True) or []
        except Exception:
            attributes = []
        for attribute in attributes:
            plug = _clean(node) + "." + _clean(attribute)
            try:
                value = cmds.getAttr(plug)
            except Exception:
                continue
            for path_value in _flatten_dependency_strings(value):
                add(path_value)
    return sorted(paths)


def _long_names(nodes):
    result = []
    for node in nodes or []:
        matches = cmds.ls(node, long=True) or [node]
        for match in matches:
            if match not in result:
                result.append(match)
    return result


def _scene_configuration_script_text():
    node = "sceneConfigurationScriptNode"
    try:
        if not cmds.objExists(node) or cmds.nodeType(node) != "script":
            return ""
    except Exception:
        return ""
    for attribute in ("before", "b"):
        plug = node + "." + attribute
        try:
            if not cmds.objExists(plug):
                continue
            script_text = _clean(cmds.getAttr(plug))
        except Exception:
            script_text = ""
        if script_text:
            return script_text
    return ""


def _disable_scene_script_nodes():
    """Neutralize event scriptNodes before timeline evaluation or rendering."""
    try:
        nodes = sorted(set(cmds.ls(type="script") or []))
    except Exception:
        nodes = []
    failures = []
    disabled = []
    for node in nodes:
        node_changed = False
        for attribute, value, value_type in (
            ("before", "", "string"),
            ("after", "", "string"),
            ("scriptType", 0, ""),
        ):
            plug = node + "." + attribute
            try:
                if not cmds.objExists(plug):
                    continue
                try:
                    if bool(cmds.getAttr(plug, lock=True)):
                        cmds.setAttr(plug, lock=False)
                except Exception:
                    pass
                if value_type:
                    cmds.setAttr(plug, value, type=value_type)
                else:
                    cmds.setAttr(plug, value)
                actual = cmds.getAttr(plug)
                if value_type:
                    valid = _clean(actual) == ""
                else:
                    valid = int(actual) == int(value)
                if not valid:
                    raise RuntimeError("verification returned {0!r}".format(actual))
                node_changed = True
            except Exception as exc:
                failures.append("{0} ({1})".format(plug, exc))
        if node_changed:
            disabled.append(node)
    if failures:
        raise RuntimeError(
            "Scene script nodes could not be neutralized safely: {0}".format(
                "; ".join(failures[:20])
                + (
                    "; and {0} more".format(len(failures) - 20)
                    if len(failures) > 20
                    else ""
                )
            )
        )
    return {
        "script_node_count": len(nodes),
        "disabled_count": len(disabled),
        "disabled_nodes": disabled,
    }


def _restore_safe_scene_timeline(script_text=None):
    """Restore Maya's saved playback bounds without executing arbitrary scripts.

    Maya stores playbackOptions in the default sceneConfigurationScriptNode.
    Opening with executeScriptNodes=False is required for untrusted production
    scenes, but it also leaves the process-default 1-120 range in place. Parse
    only finite numeric playback flags from that exact built-in node.
    """
    if script_text is None:
        script_text = _scene_configuration_script_text()
    match = re.search(r"\bplaybackOptions\b([^;]*)", script_text)
    if not match:
        return {}
    aliases = {
        "min": "minTime",
        "minTime": "minTime",
        "max": "maxTime",
        "maxTime": "maxTime",
        "ast": "animationStartTime",
        "animationStartTime": "animationStartTime",
        "aet": "animationEndTime",
        "animationEndTime": "animationEndTime",
    }
    numeric = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    values = {}
    for flag, raw_value in re.findall(r"-([A-Za-z]+)\s+(" + numeric + r")", match.group(1)):
        target = aliases.get(flag)
        if not target:
            continue
        value = float(raw_value)
        if math.isfinite(value) and abs(value) <= 1000000000.0:
            values[target] = value
    if "minTime" not in values or "maxTime" not in values:
        return {}
    if values["maxTime"] < values["minTime"]:
        return {}
    cmds.playbackOptions(**values)
    current = float(cmds.currentTime(query=True))
    clamped = min(max(current, values["minTime"]), values["maxTime"])
    if abs(clamped - current) > 1e-9:
        cmds.currentTime(clamped, edit=True)
    return {
        "start_frame": float(cmds.playbackOptions(query=True, minTime=True)),
        "end_frame": float(cmds.playbackOptions(query=True, maxTime=True)),
    }


def _dag_depth(node):
    return max(0, len([part for part in _clean(node).split("|") if part]))


def _find_named_nodes(name):
    if not name:
        return []
    if cmds.objExists(name):
        return cmds.ls(name, long=True) or [name]
    short_name = name.split("|")[-1]
    matches = cmds.ls(short_name, long=True) or []
    if not matches and ":" not in short_name:
        matches = cmds.ls("*:" + short_name, long=True) or []
    return matches


def _transform_candidates(name):
    candidates = []
    for node in _find_named_nodes(name):
        if not cmds.objExists(node):
            continue
        node_type = cmds.nodeType(node)
        if node_type == "transform":
            candidates.append(node)
            continue
        parent = cmds.listRelatives(node, parent=True, fullPath=True) or []
        if parent and cmds.nodeType(parent[0]) == "transform":
            candidates.append(parent[0])
    return sorted(set(candidates))


def _resolve_group_root(name):
    candidates = _transform_candidates(name)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError("Group Name not found in Maya scene: {0}".format(name))
    raise RuntimeError("Group Name is ambiguous in Maya scene: {0}".format(name))


def _derive_asset_id(group_name, resolved_root):
    source = _clean(group_name) or _clean(resolved_root)
    if not source:
        return ""
    leaf = source.split("|")[-1] if "|" in source else source.split("/")[-1]
    return _clean(leaf)


def _proxy_manager_for_dag_node(node):
    try:
        if not cmds.referenceQuery(node, isNodeReferenced=True):
            return "", ""
        reference_node = _clean(
            cmds.referenceQuery(node, referenceNode=True)
        )
    except Exception:
        return "", ""
    for record in _proxy_reference_sets():
        manager = _clean(record.get("proxy_manager"))
        for member in record.get("members") or []:
            if _clean(member.get("reference_node")) == reference_node:
                return manager, reference_node
    return "", reference_node


def _read_job_bindings(job):
    raw_bindings = job.get("bindings") if isinstance(job, dict) else []
    if not isinstance(raw_bindings, list):
        raw_bindings = []
    records = []
    errors = []
    seen_colors = set()
    seen_assets = set()
    seen_roots = set()
    valid_colors = set(MARKER_OPTIONS)
    for index, raw in enumerate(raw_bindings, start=1):
        if not isinstance(raw, dict):
            continue
        if not bool(raw.get("enabled", True)):
            continue
        group_name = _clean(raw.get("group_name") or raw.get("display_name") or raw.get("subject_root"))
        full_dag_path = _clean(raw.get("full_dag_path") or raw.get("subject_root"))
        maya_uuid = _clean(raw.get("maya_uuid"))
        proxy_manager = _clean(raw.get("proxy_manager"))
        reference_node = _clean(raw.get("reference_node"))
        reference_file = _clean(raw.get("reference_file"))
        color = _clean(raw.get("color"))
        if not group_name and not color:
            continue
        if not group_name:
            errors.append("Assignment row {0} has no Group Name.".format(index))
            continue
        if not color:
            errors.append("Assignment row {0} has no Color Pick.".format(index))
            continue
        if color not in valid_colors:
            errors.append("Unsupported marker color: {0}".format(color))
            continue
        if color in seen_colors and color not in REPEATABLE_MARKERS:
            errors.append("Duplicate marker color: {0}".format(color))
            continue
        resolve_name = full_dag_path or group_name
        try:
            root = _resolve_group_root(resolve_name)
        except Exception as exc:
            errors.append(str(exc))
            continue
        resolved_proxy_manager, resolved_reference_node = (
            _proxy_manager_for_dag_node(root)
        )
        if proxy_manager and resolved_proxy_manager != proxy_manager:
            errors.append(
                "Proxy representation changed outside the registered "
                "proxyManager for Group Name: {0}".format(
                    group_name or full_dag_path
                )
            )
            continue
        if maya_uuid:
            try:
                resolved_uuid = (cmds.ls(root, uuid=True) or [""])[0]
            except Exception:
                resolved_uuid = ""
            if (
                resolved_uuid
                and resolved_uuid != maya_uuid
                and not (
                    proxy_manager
                    and resolved_proxy_manager == proxy_manager
                )
            ):
                errors.append("Maya UUID changed for Group Name: {0}".format(group_name or full_dag_path))
                continue
        asset_id = _clean(raw.get("asset_id")) or _derive_asset_id(group_name, root)
        if not asset_id:
            errors.append("Asset ID could not be derived from Group Name: {0}".format(group_name))
            continue
        if asset_id in seen_assets:
            errors.append("Duplicate Asset ID: {0}".format(asset_id))
            continue
        if root in seen_roots:
            errors.append("Group Name is assigned more than once: {0}".format(root))
            continue
        seen_colors.add(color)
        seen_assets.add(asset_id)
        seen_roots.add(root)
        records.append({
            "group_name": group_name or root.split("|")[-1],
            "full_dag_path": root,
            "maya_uuid": maya_uuid,
            "reference_node": resolved_reference_node or reference_node,
            "reference_file": reference_file,
            "proxy_manager": resolved_proxy_manager or proxy_manager,
            "color": color,
            "asset_id": asset_id,
            "enabled": True,
            "subject_root": root,
            "picker_order": int(raw.get("picker_order") or index),
        })
    if errors:
        raise RuntimeError(" | ".join(errors))
    records.sort(key=lambda item: (_dag_depth(item.get("subject_root")), item.get("subject_root"), item.get("asset_id")))
    return records


def _camera_from_scene_data():
    nodes = []
    if cmds.objExists(DATA_NODE):
        nodes.extend(cmds.ls(DATA_NODE, long=True) or [DATA_NODE])
    nodes.extend(cmds.ls("*:" + DATA_NODE, type="network", long=True) or [])
    for data_node in sorted(set(nodes)):
        plug = data_node + ".shotCamera"
        if not cmds.objExists(plug):
            continue
        connections = _long_names(
            cmds.listConnections(plug, source=True, destination=False) or []
        )
        for node in connections:
            transform = _camera_transform(node)
            if transform:
                return transform
    return ""

def _camera_transform(node):
    if not node or not cmds.objExists(node):
        return ""
    node_type = cmds.nodeType(node)
    if node_type == "camera":
        parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
        return parents[0] if parents else ""
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True, type="camera") or []
    return node if shapes else ""



def _resolve_camera(explicit):
    if explicit:
        candidates = _find_named_nodes(explicit)
        valid = [node for node in candidates if _camera_transform(node)]
        if len(valid) == 1:
            return _camera_transform(valid[0])
        if len(valid) > 1:
            raise RuntimeError("Camera name is ambiguous: {0}".format(explicit))
        raise RuntimeError("Camera not found: {0}".format(explicit))

    registered = _camera_from_scene_data()
    if registered:
        return registered

    renderable = []
    for shape in cmds.ls(type="camera", long=True) or []:
        try:
            if cmds.getAttr(shape + ".renderable"):
                parent = cmds.listRelatives(shape, parent=True, fullPath=True) or []
                if parent:
                    renderable.append(parent[0])
        except Exception:
            pass
    renderable = sorted(set(renderable))
    if len(renderable) == 1:
        return renderable[0]
    if not renderable:
        raise RuntimeError("No registered camera and no renderable camera found.")
    raise RuntimeError("Multiple renderable cameras found. Register or specify one fixed camera.")


def _is_intermediate_shape(shape):
    """Return whether a Maya shape is a non-rendered construction/history shape."""
    try:
        return bool(
            cmds.attributeQuery(
                "intermediateObject",
                node=shape,
                exists=True,
            )
            and cmds.getAttr(shape + ".intermediateObject")
        )
    except Exception:
        return False


def _all_renderable_shapes():
    """Return final polygon mesh shapes only.

    Rig, controller, joint, locator, NURBS, intermediate and guide shapes are
    intentionally excluded from the picker and from marker shading.
    """
    result = []
    for shape in cmds.ls(type="mesh", long=True) or []:
        if _is_intermediate_shape(shape):
            continue
        result.append(shape)
    return sorted(set(result))


def _depth_supported_surface_shapes(paths):
    """Return exact renderable mesh/NURBS DAG paths from an arbitrary scope."""
    result = []
    for shape in _marker_renderable_shapes(paths or []):
        try:
            shape_type = _clean(cmds.nodeType(shape))
        except Exception:
            shape_type = ""
        if shape_type not in ("mesh", "nurbsSurface"):
            continue
        if shape not in result:
            result.append(shape)
    return result


def _all_depth_renderable_shapes(job=None):
    """Return every supported depth surface on every concrete DAG path.

    The regular marker picker is polygon-only, while the full-detail viewport
    contract also permits production NURBS surfaces.  Depth must shade and
    range both kinds.  ``allPaths`` is required here because independently
    transformed instances can occupy different camera depths.
    """
    excluded = set(
        _clean(item)
        for item in (
            (job or {}).get("_mouth_depth_excluded_shape_paths")
            if isinstance(job, dict)
            else []
        ) or []
        if _clean(item)
    )
    scoped = (job or {}).get("_render_scope_shapes") if isinstance(job, dict) else None
    if isinstance(scoped, list):
        return [
            shape for shape in _depth_supported_surface_shapes(scoped)
            if shape not in excluded
        ]
    result = []
    for shape_type in ("mesh", "nurbsSurface"):
        try:
            shapes = cmds.ls(
                dag=True,
                type=shape_type,
                long=True,
                allPaths=True,
            ) or []
        except Exception as exc:
            # A non-allPaths fallback silently drops secondary DAG instances.
            # That would make both the sequence range and the shader assignment
            # incomplete, so a production depth pass must fail closed instead.
            raise RuntimeError(
                "Depth playblast could not enumerate every {0} instance DAG "
                "path: {1}".format(shape_type, exc)
            )
        for shape in shapes:
            if _is_intermediate_shape(shape):
                continue
            if shape not in result:
                result.append(shape)
    return [
        shape for shape in _marker_renderable_shapes(result)
        if shape not in excluded
    ]


def _depth_shape_type_counts(shapes):
    counts = {"mesh": 0, "nurbsSurface": 0, "other": 0}
    for shape in shapes or []:
        try:
            shape_type = _clean(cmds.nodeType(shape))
        except Exception:
            shape_type = ""
        if shape_type in counts:
            counts[shape_type] += 1
        else:
            counts["other"] += 1
    return counts


def _depth_mesh_api(shape):
    """Return one exact API 2.0 mesh path/function or fail closed."""
    try:
        from maya.api import OpenMaya as om
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast requires Maya API 2.0 mesh verification: {0}".format(
                exc
            )
        )
    try:
        selection = om.MSelectionList()
        selection.add(shape)
        dag_path = selection.getDagPath(0)
        mesh_function = om.MFnMesh(dag_path)
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not prepare polygon mesh {0} for API "
            "verification: {1}".format(shape, exc)
        )
    return om, dag_path, mesh_function


def _depth_mesh_polygon_count_api(shape):
    """Read the evaluated polygon count through MFnMesh."""
    _om, _dag_path, mesh_function = _depth_mesh_api(shape)
    try:
        value = mesh_function.numPolygons
        if callable(value):
            value = value()
        return int(value)
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not read MFnMesh.numPolygons for {0}: "
            "{1}".format(shape, exc)
        )


def _potentially_visible_depth_image_planes(camera=None):
    """Return image planes that can contaminate this camera's depth pass."""
    try:
        paths = cmds.ls(
            dag=True,
            type="imagePlane",
            long=True,
            allPaths=True,
        ) or []
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not enumerate every imagePlane DAG path: "
            "{0}".format(exc)
        )
    active_camera_shape = _camera_shape(camera) if camera else ""
    active_camera_paths = set(
        cmds.ls(active_camera_shape, long=True, type="camera") or []
    ) if active_camera_shape else set()
    result = []
    for path in _marker_renderable_shapes(paths):
        display_mode = path + ".displayMode"
        try:
            disabled = (
                cmds.objExists(display_mode)
                and int(cmds.getAttr(display_mode)) == 0
                and not _plug_has_input(display_mode)
            )
        except Exception:
            disabled = False
        if disabled:
            continue
        try:
            attached = cmds.imagePlane(path, query=True, camera=True) or []
        except Exception:
            # An unattached or nonstandard imagePlane can still be a world-space
            # drawable, so uncertainty is handled conservatively.
            attached = []
        if isinstance(attached, str):
            attached = [attached]
        attached_paths = set()
        for item in attached:
            try:
                attached_paths.update(
                    cmds.ls(item, long=True, type="camera") or []
                )
            except Exception:
                pass
        if attached_paths and active_camera_paths.isdisjoint(attached_paths):
            # A plate connected only to another camera cannot contaminate this
            # camera's Viewport 2.0 playblast.
            continue
        result.append(path)
    return result


_DEPTH_NON_SURFACE_VIEWPORT_SHAPE_TYPES = {
    "ambientLight",
    "angleDimShape",
    "annotationShape",
    "arcLengthDimension",
    "areaLight",
    "bezierCurve",
    "camera",
    "directionalLight",
    "distanceDimShape",
    "follicle",
    "locator",
    "nurbsCurve",
    "pointLight",
    "poseInterpolator",
    "spotLight",
    "volumeLight",
}


def _potentially_visible_unsupported_depth_drawables():
    """Return visible VP2 shape types that cannot receive the depth shader."""
    try:
        shapes = cmds.ls(
            dag=True,
            shapes=True,
            long=True,
            allPaths=True,
        ) or []
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not audit every Viewport 2.0 shape DAG "
            "path: {0}".format(exc)
        )
    unsupported = []
    for path in _marker_renderable_shapes(shapes):
        try:
            shape_type = _clean(cmds.nodeType(path))
        except Exception as exc:
            raise RuntimeError(
                "Depth playblast could not identify Viewport shape {0}: {1}".format(
                    path,
                    exc,
                )
            )
        if shape_type in ("mesh", "nurbsSurface", "imagePlane"):
            continue
        if shape_type in _DEPTH_NON_SURFACE_VIEWPORT_SHAPE_TYPES:
            # These are viewport ornaments, controls, cameras, or lights and are
            # suppressed by the ornament-free playblast rather than shaded.
            continue
        unsupported.append({"path": path, "type": shape_type or "<unknown>"})
    return unsupported


def _assert_depth_drawables_supported(camera=None):
    image_planes = _potentially_visible_depth_image_planes(camera)
    if image_planes:
        detail = ", ".join(image_planes[:12])
        if len(image_planes) > 12:
            detail += ", and {0} more".format(len(image_planes) - 12)
        raise RuntimeError(
            "Depth playblast cannot guarantee a pure-black background while "
            "a visible imagePlane is active: {0}. Hide or disable the image "
            "plane before generating the Maya shader depth pass.".format(detail)
        )
    unsupported = _potentially_visible_unsupported_depth_drawables()
    if unsupported:
        detail = ", ".join(
            "{0} ({1})".format(item["path"], item["type"])
            for item in unsupported[:12]
        )
        if len(unsupported) > 12:
            detail += ", and {0} more".format(len(unsupported) - 12)
        raise RuntimeError(
            "Depth playblast found visible Viewport 2.0 drawables that cannot "
            "receive the plug-in-free surface depth shader: {0}. Convert or "
            "hide them before generating Depth; the pass will not publish "
            "partially colored or incomplete depth media.".format(detail)
        )


def _descendant_shapes(root):
    shapes = []
    if not root or not cmds.objExists(root):
        return shapes
    if cmds.nodeType(root) == "mesh":
        shapes.append(root)
    shapes.extend(cmds.listRelatives(root, allDescendents=True, fullPath=True, type="mesh") or [])
    filtered = []
    for shape in sorted(set(shapes)):
        try:
            instance_paths = cmds.ls(
                shape,
                long=True,
                allPaths=True,
            ) or [shape]
        except Exception:
            instance_paths = [shape]
        for instance_path in instance_paths:
            if not _same_or_descendant_dag_path(instance_path, root):
                continue
            if _is_intermediate_shape(instance_path):
                continue
            if instance_path not in filtered:
                filtered.append(instance_path)
    return filtered


def _dag_path_nodes(node):
    """Return every node on one concrete DAG path, from root to leaf."""
    paths = _long_names([node])
    path = paths[0] if paths else _clean(node)
    if not path or "|" not in path:
        return [path] if path else []
    parts = [part for part in path.split("|") if part]
    return ["|" + "|".join(parts[:index]) for index in range(1, len(parts) + 1)]


def _plug_has_input(plug):
    try:
        return bool(cmds.listConnections(plug, source=True, destination=False, plugs=False) or [])
    except Exception:
        return False


def _statically_false(node, attribute):
    """True only when an attribute is false and cannot change through a connection."""
    plug = node + "." + attribute
    try:
        if not cmds.objExists(plug) or bool(cmds.getAttr(plug)):
            return False
    except Exception:
        return False
    return not _plug_has_input(plug)


def _statically_true(node, attribute):
    """True only when an attribute is true and cannot change through a connection."""
    plug = node + "." + attribute
    try:
        if not cmds.objExists(plug) or not bool(cmds.getAttr(plug)):
            return False
    except Exception:
        return False
    return not _plug_has_input(plug)


def _statically_hidden_by_display_layer(node):
    try:
        layers = cmds.listConnections(node, source=True, destination=False, type="displayLayer") or []
    except Exception:
        layers = []
    for layer in sorted(set(layers)):
        if layer == "defaultLayer":
            continue
        if _statically_false(layer, "visibility"):
            return True
    return False


def _statically_non_renderable(node):
    """Identify static viewport exclusions without dropping animated visibility.

    Direct marker assignment otherwise touches hidden blend-shape pose instances
    that Viewport 2.0 would never draw. A connected visibility control is
    deliberately retained because that instance can become visible later in the
    requested frame range.
    """
    if _statically_false(node, "visibility") or _statically_false(node, "lodVisibility"):
        return True
    if _statically_true(node, "template"):
        return True
    override_enabled = node + ".overrideEnabled"
    override_visibility = node + ".overrideVisibility"
    try:
        hidden_by_override = (
            cmds.objExists(override_enabled)
            and bool(cmds.getAttr(override_enabled))
            and cmds.objExists(override_visibility)
            and not bool(cmds.getAttr(override_visibility))
        )
    except Exception:
        hidden_by_override = False
    if (
        hidden_by_override
        and not _plug_has_input(override_enabled)
        and not _plug_has_input(override_visibility)
    ):
        return True
    return _statically_hidden_by_display_layer(node)


def _marker_renderable_shapes(shapes):
    """Keep concrete mesh instances that may contribute to the marker render.

    Different visible instance paths are intentionally preserved: they can have
    independent transforms and animation.  Only intermediate meshes and paths
    hidden by non-driven DAG/display-layer attributes are removed.
    """
    result = []
    node_status = {}
    for shape in sorted(set(_long_names(shapes))):
        if _is_intermediate_shape(shape):
            continue
        include = True
        for node in _dag_path_nodes(shape):
            if node not in node_status:
                node_status[node] = not _statically_non_renderable(node)
            if not node_status[node]:
                include = False
                break
        if include:
            result.append(shape)
    return result


def _same_or_descendant_dag_path(path, ancestor):
    path = _clean(path).rstrip("|")
    ancestor = _clean(ancestor).rstrip("|")
    return bool(
        path
        and ancestor
        and (path == ancestor or path.startswith(ancestor + "|"))
    )


def _picker_path_is_hidden(path, hidden_paths):
    return any(
        _same_or_descendant_dag_path(path, hidden)
        for hidden in hidden_paths or []
    )


def _validated_picker_hidden_paths(job):
    requested = (
        (job or {}).get("hidden_paths")
        if isinstance((job or {}).get("hidden_paths"), list)
        else []
    )
    resolved = []
    failures = []
    for raw_path in requested:
        path = _clean(raw_path)
        if not path:
            continue
        if not cmds.objExists(path):
            failures.append("{0}: path no longer exists".format(path))
            continue
        long_names = _long_names([path])
        if len(long_names) != 1:
            failures.append(
                "{0}: expected one exact DAG path, resolved {1}".format(
                    path,
                    len(long_names),
                )
            )
            continue
        resolved_path = _clean(long_names[0])
        if resolved_path not in resolved:
            resolved.append(resolved_path)
    if failures:
        raise RuntimeError(
            "Picker eye exclusions could not be applied exactly: {0}".format(
                " | ".join(failures)
            )
        )
    return resolved


def _all_scope_drawable_shapes():
    """Return every non-camera DAG shape that could contaminate a Picker pass."""
    try:
        shapes = cmds.ls(
            dag=True,
            shapes=True,
            long=True,
            allPaths=True,
        ) or []
    except Exception as exc:
        raise RuntimeError(
            "Picker render scope could not enumerate Maya DAG shapes: {0}".format(
                exc
            )
        )
    result = []
    for shape in sorted(set(_clean(item) for item in shapes if _clean(item))):
        try:
            shape_type = _clean(cmds.nodeType(shape))
        except Exception:
            shape_type = ""
        if shape_type == "camera" or _is_intermediate_shape(shape):
            continue
        result.append(shape)
    # Paths already excluded by authored static visibility, LOD, template,
    # override, or display-layer state cannot contaminate the playblast and
    # must not be moved to a new layer.  This also preserves a visible instance
    # of a shared mesh when another authored-hidden instance uses the same
    # underlying shape object.
    return _marker_renderable_shapes(result)


def _dag_object_identity(path):
    try:
        values = cmds.ls(path, uuid=True) or []
    except Exception:
        values = []
    return _clean(values[0]) if len(values) == 1 else _clean(path)


def _concrete_scope_mesh(shape, require_depth_api=False):
    try:
        if cmds.nodeType(shape) != "mesh":
            return False
    except Exception:
        return False
    if hasattr(cmds, "polyEvaluate"):
        try:
            if int(cmds.polyEvaluate(shape, face=True) or 0) <= 0:
                return False
        except Exception:
            return False
    if require_depth_api:
        try:
            _depth_mesh_api(shape)
        except Exception:
            return False
    return True


def _apply_assigned_render_scope(bindings, job):
    """Keep only authored-visible, color-bound, Picker-enabled geometry.

    Nothing is ever made visible here.  Unassigned and eye-disabled DAG shapes
    are placed on one temporary invisible display layer inside the disposable
    mayabatch session, which also excludes locked/driven/reference geometry
    without writing back to the source scene.
    """
    hidden_paths = _validated_picker_hidden_paths(job)
    binding_shapes = {}
    depth_range_shape_roles = {}
    depth_foreground_shapes = []
    allowed = []
    raw_bound_shape_count = 0
    nonconcrete_assigned = []
    # Color scope is determined only by Color Assignment. Optional Depth
    # capability must never remove a valid assigned Color shape.
    require_depth_api = False
    for record in bindings or []:
        root = _clean(record.get("subject_root") or record.get("full_dag_path"))
        raw_shapes = _descendant_shapes(root)
        raw_bound_shape_count += len(raw_shapes)
        visible_shapes = [
            shape
            for shape in _marker_renderable_shapes(raw_shapes)
            if not _picker_path_is_hidden(shape, hidden_paths)
        ]
        shapes = []
        for shape in visible_shapes:
            if _concrete_scope_mesh(
                shape,
                require_depth_api=require_depth_api,
            ):
                shapes.append(shape)
            else:
                nonconcrete_assigned.append(shape)
        binding_shapes[root] = sorted(set(shapes))
        marker = _clean(record.get("color"))
        range_role = (
            "foreground" if marker in CHARACTER_MARKERS else "context"
        )
        for shape in binding_shapes[root]:
            depth_range_shape_roles[shape] = {
                "root": root,
                "marker": marker,
                "role": range_role,
            }
            if range_role == "foreground":
                depth_foreground_shapes.append(shape)
        allowed.extend(shapes)
    allowed = sorted(set(allowed))
    allowed_set = set(allowed)
    drawable_shapes = _all_scope_drawable_shapes()
    auxiliary_fallback_shapes = sorted(
        shape
        for shape in drawable_shapes
        if not _picker_path_is_hidden(shape, hidden_paths)
    )
    auxiliary_picker_hidden_shapes = sorted(
        shape
        for shape in drawable_shapes
        if _picker_path_is_hidden(shape, hidden_paths)
    )
    excluded = [shape for shape in drawable_shapes if shape not in allowed_set]
    allowed_identities = set(_dag_object_identity(shape) for shape in allowed)
    excluded_identities = set(_dag_object_identity(shape) for shape in excluded)
    partial_instances = sorted(
        identity
        for identity in allowed_identities.intersection(excluded_identities)
        if identity
    )
    if partial_instances:
        raise RuntimeError(
            "Picker render scope cannot safely split assigned and excluded "
            "instances of the same Maya shape object: {0}. Assign or exclude "
            "the complete instanced asset.".format(
                ", ".join(partial_instances[:12])
            )
        )

    layer = ""
    if excluded:
        try:
            layer = cmds.createDisplayLayer(
                empty=True,
                name="HMB_Picker_Excluded",
                number=1,
            )
            cmds.editDisplayLayerMembers(
                layer,
                excluded,
                noRecurse=True,
            )
            cmds.setAttr(layer + ".visibility", False)
            if bool(cmds.getAttr(layer + ".visibility")):
                raise RuntimeError("temporary exclusion layer remained visible")
            members = cmds.editDisplayLayerMembers(
                layer,
                query=True,
                fullNames=True,
            ) or []
            member_paths = set(_long_names(members))
            missing = [shape for shape in excluded if shape not in member_paths]
            unverified = [
                shape
                for shape in missing
                if not _display_layer_hidden(shape)[0]
            ]
            if unverified:
                raise RuntimeError(
                    "{0} of {1} excluded DAG paths did not join the temporary "
                    "display layer; first paths: {2}".format(
                        len(unverified),
                        len(excluded),
                        ", ".join(unverified[:12]),
                    )
                )
        except Exception as exc:
            raise RuntimeError(
                "Picker render scope could not guarantee exclusion of "
                "unassigned/eye-disabled geometry: {0}".format(exc)
            )

    scope_digest = hashlib.sha256(
        "\n".join(allowed).encode("utf-8")
    ).hexdigest()
    report = {
        "policy": "maya_authored_visible_and_color_bound_and_picker_visible",
        "allowed_shape_path_count": len(allowed),
        "excluded_shape_path_count": len(excluded),
        "raw_bound_shape_path_count": raw_bound_shape_count,
        "nonconcrete_assigned_shape_path_count": len(
            set(nonconcrete_assigned)
        ),
        "hidden_path_count": len(hidden_paths),
        "hidden_paths": list(hidden_paths),
        "allowed_shape_paths_sha256": scope_digest,
        "temporary_exclusion_layer": layer,
        "proxy_preview_recovery_enabled": False,
    }
    job["_render_scope_shapes"] = allowed
    job["_render_scope_binding_shapes"] = binding_shapes
    job["_depth_range_shape_roles"] = depth_range_shape_roles
    job["_depth_foreground_shapes"] = sorted(set(depth_foreground_shapes))
    job["_render_scope_report"] = report
    job["_validated_hidden_paths"] = hidden_paths
    # Color remains strictly assignment-scoped.  When there is no Color
    # Assignment, optional Depth/Motion passes may instead use this separately
    # captured authored-visible, Picker-eye-enabled scope after Color finishes.
    # It is captured before the temporary Color exclusion layer is created, so
    # authored-hidden geometry is never promoted into the fallback.
    job["_auxiliary_fallback_shapes"] = auxiliary_fallback_shapes
    job["_auxiliary_authored_visible_shapes"] = list(drawable_shapes)
    job["_auxiliary_picker_hidden_shapes"] = auxiliary_picker_hidden_shapes
    job["_viewport_quality_scope_shapes"] = (
        allowed if bindings else auxiliary_fallback_shapes
    )
    return hidden_paths, report


def _release_temporary_render_scope_layer(report):
    """Remove only the disposable Color exclusion layer.

    The source scene is never saved.  Removing this temporary layer restores
    the already-authored visibility state inside mayabatch; it does not enable
    any authored-hidden DAG path.
    """
    layer = _clean((report or {}).get("temporary_exclusion_layer"))
    if not layer or not cmds.objExists(layer):
        return
    cmds.delete(layer)
    if cmds.objExists(layer):
        raise RuntimeError(
            "The temporary Color render-scope layer could not be released."
        )


def _prepare_unassigned_auxiliary_scope(job, hidden_paths, color_scope_report):
    """Activate the no-Color-assignment scope for optional auxiliary passes.

    Depth shaders can be assigned only to polygon meshes and NURBS surfaces.
    The authored-visible fallback used to retain controller curves, locators,
    lights, and other viewport shapes in ``_render_scope_shapes``.  Those paths
    then reached Depth assignment verification and produced one failure line
    per controller.  Keep the complete authored-visible universe for the
    sidecar audit, but expose only supported surfaces to Depth and Motion.
    Unsupported controller/ornament paths are hidden on the disposable batch
    layer and never become shader targets.
    """
    _release_temporary_render_scope_layer(color_scope_report)
    candidates = sorted(set(
        _clean(item)
        for item in (job or {}).get("_auxiliary_authored_visible_shapes") or []
        if _clean(item) and cmds.objExists(_clean(item))
    ))
    supported_types = ("mesh", "nurbsSurface")
    shape_types = {}
    for shape in candidates:
        try:
            shape_types[shape] = _clean(cmds.nodeType(shape))
        except Exception:
            shape_types[shape] = "<unknown>"
    unsupported_controls = [
        shape for shape in candidates
        if shape_types.get(shape) not in supported_types
    ]
    allowed = [
        shape
        for shape in candidates
        if shape_types.get(shape) in supported_types
        if not _picker_path_is_hidden(shape, hidden_paths)
    ]
    allowed_set = set(allowed)
    excluded = [shape for shape in candidates if shape not in allowed_set]
    layer = ""
    if excluded:
        layer = cmds.createDisplayLayer(
            empty=True,
            name="HMB_Picker_Aux_Excluded",
            number=1,
        )
        cmds.editDisplayLayerMembers(
            layer,
            excluded,
            noRecurse=True,
        )
        cmds.setAttr(layer + ".visibility", False)
        if bool(cmds.getAttr(layer + ".visibility")):
            raise RuntimeError(
                "The temporary auxiliary Picker-eye exclusion layer remained visible."
            )
        members = cmds.editDisplayLayerMembers(
            layer,
            query=True,
            fullNames=True,
        ) or []
        member_paths = set(_long_names(members))
        missing = [shape for shape in excluded if shape not in member_paths]
        unverified = [
            shape
            for shape in missing
            if not _display_layer_hidden(shape)[0]
        ]
        if unverified:
            raise RuntimeError(
                "{0} of {1} unsupported/Picker-hidden auxiliary DAG paths "
                "did not join the temporary exclusion layer; first paths: "
                "{2}".format(
                    len(unverified),
                    len(excluded),
                    ", ".join(unverified[:12]),
                )
            )
    report = {
        "policy": "maya_authored_visible_and_picker_visible_without_color_requirement",
        "supported_surface_types": list(supported_types),
        "allowed_shape_path_count": len(allowed),
        "excluded_shape_path_count": len(excluded),
        "unsupported_control_shape_path_count": len(unsupported_controls),
        "unsupported_control_shape_type_counts": dict(
            (shape_type, len([
                shape for shape in unsupported_controls
                if shape_types.get(shape) == shape_type
            ]))
            for shape_type in sorted(set(
                shape_types.get(shape) for shape in unsupported_controls
            ))
        ),
        # Full paths belong in the on-disk runner sidecar.  Picker UI state
        # publishes only the compact count/type summary derived from it.
        "unsupported_control_shape_paths": list(unsupported_controls),
        "hidden_path_count": len(hidden_paths or []),
        "hidden_paths": list(hidden_paths or []),
        "temporary_exclusion_layer": layer,
        "color_assignment_required": False,
    }
    job["_render_scope_shapes"] = allowed
    job["_auxiliary_render_scope_report"] = report
    return report


def _bool_attr(node, attribute, default=True):
    plug = node + "." + attribute
    try:
        if cmds.objExists(plug):
            return bool(cmds.getAttr(plug))
    except Exception:
        pass
    return bool(default)


def _visibility_connection_kind(node):
    plug = node + ".visibility"
    if not cmds.objExists(plug):
        return ""
    try:
        sources = cmds.listConnections(plug, source=True, destination=False, plugs=False) or []
    except Exception:
        sources = []
    if not sources:
        return ""
    for source in sources:
        try:
            if cmds.nodeType(source).startswith("animCurve"):
                return "anim_vis"
        except Exception:
            pass
    return "driven_vis"


def _display_layer_hidden(node):
    try:
        layers = cmds.listConnections(node, source=True, destination=False, type="displayLayer") or []
    except Exception:
        layers = []
    for layer in sorted(set(layers)):
        if layer == "defaultLayer":
            continue
        if not _bool_attr(layer, "visibility", True):
            return True, layer
    return False, ""


def _safe_token(value):
    token = re.sub(r"[^A-Za-z0-9_]+", "_", _clean(value)).strip("_")
    return token or "Marker"


def _numeric_attr_components(value):
    """Flatten the scalar/vector forms returned by ``cmds.getAttr``."""
    result = []
    if isinstance(value, (list, tuple)):
        for item in value:
            result.extend(_numeric_attr_components(item))
        return result
    try:
        result.append(float(value))
    except Exception:
        pass
    return result


def _incoming_source_plugs(plug):
    try:
        return sorted(set(
            _clean(item)
            for item in (
                cmds.listConnections(
                    plug,
                    source=True,
                    destination=False,
                    plugs=True,
                )
                or []
            )
            if _clean(item)
        ))
    except Exception:
        return []


def _is_spatial_texture_node(node):
    """Identify texture nodes by Maya node type/classification, never by name."""
    node = _clean(node)
    if not node:
        return False
    try:
        node_type = _clean(cmds.nodeType(node))
    except Exception:
        return False
    # The explicit types are a fallback for Maya builds whose classification
    # registry is incomplete in batch.  They are node types, not asset names.
    if node_type in (
        "file",
        "psdFileTex",
        "aiImage",
        "imageSource",
        "ramp",
        "checker",
        "bulge",
        "noise",
        "fractal",
        "cloud",
        "solidFractal",
        "volumeNoise",
    ):
        return True
    try:
        classifications = cmds.getClassification(node_type) or []
    except Exception:
        classifications = []
    if isinstance(classifications, str):
        classifications = [classifications]
    return any(
        "texture/2d" in _clean(item).lower()
        or "texture/3d" in _clean(item).lower()
        or "shader/texture" in _clean(item).lower()
        for item in classifications
    )


def _upstream_has_spatial_texture(source_plugs):
    """Trace only the opacity branch and look for spatial texture evidence."""
    queue = [
        _clean(plug).split(".", 1)[0]
        for plug in source_plugs or []
        if _clean(plug)
    ]
    visited = set()
    while queue and len(visited) < 512:
        node = queue.pop(0)
        if not node or node in visited:
            continue
        visited.add(node)
        if _is_spatial_texture_node(node):
            return True
        try:
            upstream = cmds.listConnections(
                node,
                source=True,
                destination=False,
                plugs=True,
            ) or []
        except Exception:
            upstream = []
        for plug in upstream:
            source_node = _clean(plug).split(".", 1)[0]
            if source_node and source_node not in visited:
                queue.append(source_node)
    return False


def _plug_value(plug):
    try:
        return _numeric_attr_components(cmds.getAttr(plug))
    except Exception:
        return []


def _material_cutout_evidence(material):
    """Return strict, material-semantic evidence for an authored alpha cutout.

    Ordinary Lambert/Phong transparency is not enough: glass and other
    semitransparent 3D materials must retain Smooth Preview 3 and the shared
    opaque marker/depth path.  A legacy transparency input is accepted only
    when its own upstream branch contains a spatial texture.  Modern
    opacity/cutoutOpacity inputs are coverage controls and are accepted when
    connected or authored below one.
    """
    material = _clean(material)
    if not material:
        return {"alpha_driven": False}
    output_plug = material + ".outTransparency"
    output_exists = False
    try:
        output_exists = bool(cmds.objExists(output_plug))
    except Exception:
        output_exists = False

    for attribute in ("cutoutOpacity", "opacity"):
        plug = material + "." + attribute
        try:
            exists = bool(cmds.objExists(plug))
        except Exception:
            exists = False
        if not exists:
            continue
        sources = _incoming_source_plugs(plug)
        values = _plug_value(plug)
        authored_coverage = bool(values) and any(
            component < (1.0 - 1.0e-6) for component in values
        )
        if not sources and not authored_coverage:
            continue
        if not output_exists:
            return {
                "alpha_driven": True,
                "unsupported": True,
                "evidence_plug": plug,
                "evidence_kind": "explicit_{0}".format(attribute),
                "reason": (
                    "material has explicit {0} coverage but no "
                    "outTransparency output"
                ).format(attribute),
            }
        return {
            "alpha_driven": True,
            "source_plug": output_plug,
            "evidence_plug": plug,
            "evidence_kind": "explicit_{0}".format(attribute),
        }

    for attribute in ("transparency", "outTransparency"):
        plug = material + "." + attribute
        try:
            exists = bool(cmds.objExists(plug))
        except Exception:
            exists = False
        if not exists:
            continue
        sources = _incoming_source_plugs(plug)
        if not sources or not _upstream_has_spatial_texture(sources):
            continue
        if not output_exists:
            return {
                "alpha_driven": True,
                "unsupported": True,
                "evidence_plug": plug,
                "evidence_kind": "spatial_texture_alpha",
                "reason": "spatial alpha material has no outTransparency output",
            }
        return {
            "alpha_driven": True,
            "source_plug": output_plug,
            "evidence_plug": plug,
            "evidence_kind": "spatial_texture_alpha",
        }
    return {"alpha_driven": False}


def _shape_shading_groups(shape):
    failures = []
    try:
        groups = cmds.listSets(type=1, object=shape) or []
    except Exception as exc:
        groups = []
        failures.append(exc)
    if not groups:
        try:
            groups = cmds.listConnections(
                shape,
                source=False,
                destination=True,
                type="shadingEngine",
            ) or []
        except Exception as exc:
            failures.append(exc)
    if len(failures) >= 2:
        raise RuntimeError(
            "could not inspect shadingEngine membership ({0})".format(
                " | ".join(_clean(item) or item.__class__.__name__ for item in failures)
            )
        )
    return sorted(set(_clean(item) for item in groups if _clean(item)))


def _shape_authored_cutout_record(shape):
    """Capture one concrete DAG path before temporary SG replacement."""
    groups = _shape_shading_groups(shape)
    material_records = []
    for group in groups:
        surface_plug = group + ".surfaceShader"
        source_plugs = _incoming_source_plugs(surface_plug)
        if len(source_plugs) > 1:
            return {
                "shape": shape,
                "alpha_driven": False,
                "ambiguous": True,
                "reason": "multiple surfaceShader sources on {0}".format(group),
            }
        if not source_plugs:
            continue
        material = source_plugs[0].split(".", 1)[0]
        evidence = _material_cutout_evidence(material)
        evidence.update({
            "material": material,
            "shading_group": group,
        })
        material_records.append(evidence)

    alpha_records = [
        record for record in material_records if record.get("alpha_driven")
    ]
    if not alpha_records:
        return {
            "shape": shape,
            "alpha_driven": False,
            "shading_groups": groups,
        }
    if any(record.get("unsupported") for record in alpha_records):
        unsupported = next(
            record for record in alpha_records if record.get("unsupported")
        )
        return {
            "shape": shape,
            "alpha_driven": True,
            "unsupported": True,
            "reason": unsupported.get("reason") or "unsupported cutout graph",
        }
    source_plugs = sorted(set(
        _clean(record.get("source_plug"))
        for record in alpha_records
        if _clean(record.get("source_plug"))
    ))
    # Component-level mixtures cannot be reproduced by a single whole-object
    # temporary marker/depth SG.  Fail closed instead of publishing a subtly
    # wrong mask.  A supported cutout has exactly one SG and one alpha output.
    if len(groups) != 1 or len(alpha_records) != 1 or len(source_plugs) != 1:
        return {
            "shape": shape,
            "alpha_driven": True,
            "ambiguous": True,
            "reason": (
                "cutout requires one whole-shape shadingEngine and one "
                "outTransparency source"
            ),
        }
    selected = alpha_records[0]
    return {
        "shape": shape,
        "alpha_driven": True,
        "source_plug": source_plugs[0],
        "source_material": selected.get("material") or "",
        "evidence_plug": selected.get("evidence_plug") or "",
        "evidence_kind": selected.get("evidence_kind") or "",
        "shading_group": selected.get("shading_group") or "",
        "shading_groups": groups,
    }


def _cutout_snapshot_report(snapshot):
    records = list((snapshot or {}).values())
    alpha_records = [record for record in records if record.get("alpha_driven")]
    return {
        "policy": CUTOUT_TRANSPARENCY_POLICY,
        "captured_shape_path_count": len(records),
        "alpha_driven_shape_path_count": len(alpha_records),
        "source_plug_count": len(set(
            _clean(record.get("source_plug"))
            for record in alpha_records
            if _clean(record.get("source_plug"))
        )),
        "verified_shape_path_count": 0,
        "ambiguous_shape_path_count": len([
            record for record in records if record.get("ambiguous")
        ]),
        "unsupported_shape_path_count": len([
            record for record in records if record.get("unsupported")
        ]),
    }


def _ensure_authored_cutout_snapshot(job, shapes):
    """Capture source alpha graphs once, before marker/depth SG replacement."""
    if not isinstance(job, dict):
        raise RuntimeError("Cutout preservation requires a mutable Maya job.")
    snapshot = job.get("_authored_cutout_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
        job["_authored_cutout_snapshot"] = snapshot
    for shape in sorted(set(_long_names(shapes or []))):
        if shape in snapshot:
            continue
        try:
            snapshot[shape] = _shape_authored_cutout_record(shape)
        except Exception as exc:
            snapshot[shape] = {
                "shape": shape,
                "alpha_driven": False,
                "unsupported": True,
                "reason": _clean(exc) or exc.__class__.__name__,
            }
    report = _cutout_snapshot_report(snapshot)
    job["_authored_cutout_report"] = report
    failures = [
        "{0}: {1}".format(
            shape,
            _clean(record.get("reason")) or "unsupported authored cutout graph",
        )
        for shape, record in sorted(snapshot.items())
        if record.get("ambiguous") or record.get("unsupported")
        if not _mouth_semantic_cutout_candidate(shape, record)
    ]
    if failures:
        raise RuntimeError(
            "Authored cutout transparency could not be preserved exactly: {0}".format(
                " | ".join(failures[:20])
                + (
                    " | and {0} more".format(len(failures) - 20)
                    if len(failures) > 20
                    else ""
                )
            )
        )
    return snapshot


def _authored_cutout_scope_shapes(job):
    for field in ("_viewport_quality_scope_shapes", "_render_scope_shapes"):
        scoped = (job or {}).get(field)
        if isinstance(scoped, list):
            return _depth_supported_surface_shapes(scoped)
    return _all_depth_renderable_shapes(job)


def _cutout_record(job, shape):
    snapshot = _ensure_authored_cutout_snapshot(job, [shape])
    long_names = _long_names([shape])
    key = long_names[0] if long_names else shape
    return snapshot.get(key) or {"shape": key, "alpha_driven": False}


def _mouth_semantic_cutout_candidate(shape, record=None):
    """Recognize only alpha-card mouth semantics, explicitly excluding eyes."""
    record = record or {}
    text = " ".join(
        _clean(value).lower()
        for value in (
            shape,
            record.get("shape"),
            record.get("source_material"),
            record.get("shading_group"),
            record.get("evidence_plug"),
        )
        if _clean(value)
    )
    if not text or any(
        token in text
        for token in ("eye", "eyelid", "iris", "pupil")
    ):
        return False
    mouth_semantic = bool(
        "mouth" in text
        or "lipsync" in text
        or "lip_sync" in text
        or "lip-sync" in text
        or re.search(r"(?:^|[^a-z0-9])lips?(?:[^a-z0-9]|$)", text)
    )
    if not mouth_semantic:
        return False
    # Unsupported/ambiguous records reached alpha analysis but could not be
    # reproduced exactly.  They are still candidates so Depth can omit them
    # instead of silently falling back to an opaque bucket.
    return bool(
        record.get("alpha_driven")
        or record.get("unsupported")
        or record.get("ambiguous")
    )


def _mouth_grid_inner_patch_plan(vertex_count, edge_count, faces):
    """Prove the exact 7x7-vertex / 6x6-quad mouth-card topology."""
    result = {"eligible": False, "reason": "topology_mismatch"}
    try:
        vertex_count = int(vertex_count)
        edge_count = int(edge_count)
        normalized_faces = [tuple(int(value) for value in face) for face in faces]
    except Exception:
        return result
    if (
        vertex_count != MOUTH_CARD_GRID_VERTEX_COUNT
        or edge_count != MOUTH_CARD_GRID_EDGE_COUNT
        or len(normalized_faces) != MOUTH_CARD_GRID_FACE_COUNT
        or any(len(face) != 4 or len(set(face)) != 4 for face in normalized_faces)
    ):
        return result
    edge_faces = {}
    vertex_neighbors = dict((index, set()) for index in range(vertex_count))
    try:
        for face_index, face in enumerate(normalized_faces):
            for vertex in face:
                if vertex < 0 or vertex >= vertex_count:
                    return result
            for index, first in enumerate(face):
                second = face[(index + 1) % len(face)]
                edge = tuple(sorted((first, second)))
                if first == second:
                    return result
                edge_faces.setdefault(edge, []).append(face_index)
                vertex_neighbors[first].add(second)
                vertex_neighbors[second].add(first)
    except Exception:
        return result
    if len(edge_faces) != edge_count or any(
        len(adjacent) not in (1, 2) for adjacent in edge_faces.values()
    ):
        return result
    degree_counts = {}
    for neighbors in vertex_neighbors.values():
        degree = len(neighbors)
        degree_counts[degree] = degree_counts.get(degree, 0) + 1
    if degree_counts != {2: 4, 3: 20, 4: 25}:
        return result
    boundary_edges = sorted(
        edge for edge, adjacent in edge_faces.items() if len(adjacent) == 1
    )
    boundary_vertices = set(vertex for edge in boundary_edges for vertex in edge)
    if len(boundary_edges) != 24 or len(boundary_vertices) != 24:
        return result
    boundary_degree = dict((vertex, 0) for vertex in boundary_vertices)
    for first, second in boundary_edges:
        boundary_degree[first] += 1
        boundary_degree[second] += 1
    if any(value != 2 for value in boundary_degree.values()):
        return result
    outer_faces = sorted(set(
        adjacent[0]
        for edge, adjacent in edge_faces.items()
        if len(adjacent) == 1
    ))
    inner_faces = sorted(
        set(range(len(normalized_faces))).difference(outer_faces)
    )
    if (
        len(outer_faces) != MOUTH_CARD_GRID_OUTER_FACE_COUNT
        or len(inner_faces) != MOUTH_CARD_GRID_INNER_FACE_COUNT
    ):
        return result
    inner_set = set(inner_faces)
    inner_adjacency = dict((face, set()) for face in inner_faces)
    for adjacent in edge_faces.values():
        if len(adjacent) != 2:
            continue
        first, second = adjacent
        if first in inner_set and second in inner_set:
            inner_adjacency[first].add(second)
            inner_adjacency[second].add(first)
    if not inner_faces:
        return result
    visited = set()
    pending = [inner_faces[0]]
    while pending:
        face = pending.pop()
        if face in visited:
            continue
        visited.add(face)
        pending.extend(inner_adjacency[face].difference(visited))
    inner_degree_counts = {}
    for adjacent in inner_adjacency.values():
        degree = len(adjacent)
        inner_degree_counts[degree] = inner_degree_counts.get(degree, 0) + 1
    if visited != inner_set or inner_degree_counts != {2: 4, 3: 8, 4: 4}:
        return result
    return {
        "eligible": True,
        "reason": "",
        "outer_faces": outer_faces,
        "inner_faces": inner_faces,
        "boundary_edge_count": len(boundary_edges),
    }


def _mouth_mesh_inner_patch_plan(shape):
    """Collect Maya API 2.0 topology and apply the pure strict-grid proof."""
    try:
        from maya.api import OpenMaya as om
        selection = om.MSelectionList()
        selection.add(shape)
        dag_path = selection.getDagPath(0)
        function = om.MFnMesh(dag_path)
        polygon_counts, polygon_vertices = function.getVertices()
        faces = []
        offset = 0
        for count in polygon_counts:
            count = int(count)
            faces.append(tuple(
                int(polygon_vertices[index])
                for index in range(offset, offset + count)
            ))
            offset += count
        return _mouth_grid_inner_patch_plan(
            function.numVertices,
            function.numEdges,
            faces,
        )
    except Exception:
        return {"eligible": False, "reason": "topology_query_failed"}


def _mouth_inner_uv_plan_from_values(values):
    """Prove that the kept vertices occupy the inner 5x5 UDIM grid."""
    result = {"eligible": False, "reason": "inner_uv_mismatch"}
    try:
        values = [float(value) for value in values]
    except Exception:
        return result
    if not values or len(values) % 2:
        return result
    pairs = list(zip(values[0::2], values[1::2]))
    min_u = min(pair[0] for pair in pairs)
    max_u = max(pair[0] for pair in pairs)
    min_v = min(pair[1] for pair in pairs)
    max_v = max(pair[1] for pair in pairs)
    tile_u = int(math.floor((min_u + max_u) * 0.5))
    tile_v = int(math.floor((min_v + max_v) * 0.5))
    local_pairs = [
        (pair[0] - tile_u, pair[1] - tile_v) for pair in pairs
    ]
    expected = [float(index) / 6.0 for index in range(1, 6)]

    def matches_expected(value):
        return any(abs(value - item) <= MOUTH_CARD_UV_TOLERANCE for item in expected)

    if any(
        not matches_expected(u_value) or not matches_expected(v_value)
        for u_value, v_value in local_pairs
    ):
        return result
    snapped_pairs = set(
        (min(range(5), key=lambda i: abs(pair[0] - expected[i])),
         min(range(5), key=lambda i: abs(pair[1] - expected[i])))
        for pair in local_pairs
    )
    if snapped_pairs != set((u_index, v_index) for u_index in range(5) for v_index in range(5)):
        return result
    local_bbox = (
        min(pair[0] for pair in local_pairs),
        min(pair[1] for pair in local_pairs),
        max(pair[0] for pair in local_pairs),
        max(pair[1] for pair in local_pairs),
    )
    expected_bbox = (1.0 / 6.0, 1.0 / 6.0, 5.0 / 6.0, 5.0 / 6.0)
    if any(
        abs(value - expected_value) > MOUTH_CARD_UV_TOLERANCE
        for value, expected_value in zip(local_bbox, expected_bbox)
    ):
        return result
    return {
        "eligible": True,
        "reason": "",
        "tile_u": tile_u,
        "tile_v": tile_v,
        "udim": 1001 + tile_u + (tile_v * 10),
        "inner_bbox": local_bbox,
    }


def _mouth_mesh_inner_uv_plan(shape, inner_faces):
    try:
        face_components = [
            "{0}.f[{1}]".format(shape, int(index)) for index in inner_faces
        ]
        uv_components = cmds.ls(
            cmds.polyListComponentConversion(
                face_components,
                fromFace=True,
                toUV=True,
            ) or [],
            flatten=True,
        ) or []
        return _mouth_inner_uv_plan_from_values(
            cmds.polyEditUV(uv_components, query=True) or []
        )
    except Exception:
        return {"eligible": False, "reason": "inner_uv_query_failed"}


def _alpha_bbox_fits_inner_uv(alpha_bbox, inner_bbox):
    if not alpha_bbox or not inner_bbox or len(alpha_bbox) != 4 or len(inner_bbox) != 4:
        return False
    try:
        return bool(
            float(alpha_bbox[0]) >= float(inner_bbox[0]) - MOUTH_CARD_UV_TOLERANCE
            and float(alpha_bbox[1]) >= float(inner_bbox[1]) - MOUTH_CARD_UV_TOLERANCE
            and float(alpha_bbox[2]) <= float(inner_bbox[2]) + MOUTH_CARD_UV_TOLERANCE
            and float(alpha_bbox[3]) <= float(inner_bbox[3]) + MOUTH_CARD_UV_TOLERANCE
        )
    except Exception:
        return False


def _mouth_alpha_file_node(record):
    """Resolve exactly one static Maya file node on the recorded alpha branch."""
    evidence_plug = _clean((record or {}).get("evidence_plug"))
    if not evidence_plug:
        return "", "missing_alpha_evidence"
    queue = list(_incoming_source_plugs(evidence_plug))
    visited = set()
    file_nodes = set()
    file_output_attributes = set()
    while queue and len(visited) < 512:
        plug = _clean(queue.pop(0))
        node = plug.split(".", 1)[0]
        if not node or node in visited:
            continue
        visited.add(node)
        try:
            node_type = _clean(cmds.nodeType(node))
        except Exception:
            node_type = ""
        if node_type == "file":
            file_nodes.add(node)
            file_output_attributes.add(
                plug.split(".", 1)[1].lower() if "." in plug else ""
            )
            continue
        try:
            queue.extend(cmds.listConnections(
                node,
                source=True,
                destination=False,
                plugs=True,
            ) or [])
        except Exception:
            pass
    if len(file_nodes) != 1:
        return "", "alpha_file_node_count_mismatch"
    if not any(
        attribute in ("outalpha", "outtransparency")
        or attribute.startswith("outtransparency")
        for attribute in file_output_attributes
    ):
        return "", "alpha_file_output_unverified"
    file_node = next(iter(file_nodes))
    for plug in (
        file_node + ".fileTextureName",
        file_node + ".frameExtension",
    ):
        if _incoming_source_plugs(plug):
            return "", "animated_alpha_texture"
    try:
        if cmds.objExists(file_node + ".useFrameExtension") and bool(
            cmds.getAttr(file_node + ".useFrameExtension")
        ):
            return "", "animated_alpha_texture"
    except Exception:
        return "", "alpha_texture_state_unreadable"
    return file_node, ""


def _mouth_alpha_texture_path(file_node, udim):
    try:
        tiling_mode = int(cmds.getAttr(file_node + ".uvTilingMode") or 0)
    except Exception:
        tiling_mode = 0
    if tiling_mode not in (0, 3):
        return "", "unsupported_alpha_tiling"
    values = []
    for attribute in ("computedFileTextureNamePattern", "fileTextureName"):
        plug = file_node + "." + attribute
        try:
            if cmds.objExists(plug):
                value = _clean(cmds.getAttr(plug))
                if value and value not in values:
                    values.append(value)
        except Exception:
            pass
    if not values:
        return "", "missing_alpha_texture_path"
    for value in values:
        candidate = os.path.expandvars(os.path.expanduser(value))
        if tiling_mode == 3:
            if re.search(r"<udim>", candidate, flags=re.IGNORECASE):
                candidate = re.sub(
                    r"<udim>", str(int(udim)), candidate, flags=re.IGNORECASE
                )
            elif re.search(r"(?<!\d)1\d{3}(?!\d)", candidate):
                matches = list(re.finditer(r"(?<!\d)1\d{3}(?!\d)", candidate))
                match = matches[-1]
                candidate = (
                    candidate[:match.start()]
                    + str(int(udim))
                    + candidate[match.end():]
                )
            else:
                continue
        elif int(udim) != 1001:
            continue
        candidates = [candidate]
        if not os.path.isabs(candidate):
            bases = []
            try:
                bases.append(_clean(cmds.workspace(query=True, rootDirectory=True)))
            except Exception:
                pass
            try:
                scene_name = _clean(cmds.file(query=True, sceneName=True))
                if scene_name:
                    bases.append(os.path.dirname(os.path.abspath(scene_name)))
            except Exception:
                pass
            candidates = [
                os.path.join(base, candidate)
                for base in bases
                if base
            ] + candidates
        for resolved in candidates:
            resolved = os.path.abspath(resolved)
            if os.path.isfile(resolved):
                return resolved, ""
    return "", "alpha_texture_tile_missing"


def _mouth_alpha_bbox_from_image(path):
    """Read the actual RGBA coverage with Maya 2026 API 2.0 MImage."""
    try:
        from maya.api import OpenMaya as om
        image = om.MImage()
        image.readFromFile(path)
        width, height = image.getSize()
        width = int(width)
        height = int(height)
        raw_pixels = image.pixels()
        if isinstance(raw_pixels, int):
            import ctypes
            pixels = bytearray(
                ctypes.string_at(raw_pixels, width * height * 4)
            )
        else:
            pixels = bytearray(raw_pixels)
    except Exception:
        return None, "alpha_image_read_failed"
    pixel_count = width * height
    if width <= 1 or height <= 1 or len(pixels) != pixel_count * 4:
        return None, "alpha_image_not_rgba"
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for index in range(pixel_count):
        if pixels[(index * 4) + 3] <= 0:
            continue
        x_value = index % width
        y_value = index // width
        min_x = min(min_x, x_value)
        min_y = min(min_y, y_value)
        max_x = max(max_x, x_value)
        max_y = max(max_y, y_value)
    if max_x < min_x or max_y < min_y:
        return None, "alpha_image_empty"
    return (
        float(min_x) / float(width - 1),
        float(min_y) / float(height - 1),
        float(max_x) / float(width - 1),
        float(max_y) / float(height - 1),
    ), ""


def _mouth_card_static_plan(shape, record, alpha_bbox_cache=None):
    """Return a path-free reason when any mandatory mouth-card gate fails."""
    alpha_bbox_cache = alpha_bbox_cache if isinstance(alpha_bbox_cache, dict) else {}
    if not (record or {}).get("alpha_driven"):
        return {"eligible": False, "reason": "authored_alpha_unverified"}
    if (record or {}).get("unsupported") or (record or {}).get("ambiguous"):
        return {"eligible": False, "reason": "authored_alpha_unverified"}
    if not _clean((record or {}).get("source_plug")):
        return {"eligible": False, "reason": "missing_alpha_source"}
    try:
        if _clean(cmds.nodeType(shape)) != "mesh":
            return {"eligible": False, "reason": "unsupported_surface_type"}
        instance_paths = cmds.ls(shape, long=True, allPaths=True) or []
        if len(set(instance_paths)) != 1:
            return {"eligible": False, "reason": "instanced_shape"}
    except Exception:
        return {"eligible": False, "reason": "shape_state_unreadable"}
    topology = _mouth_mesh_inner_patch_plan(shape)
    if not topology.get("eligible"):
        return topology
    uv_plan = _mouth_mesh_inner_uv_plan(shape, topology.get("inner_faces") or [])
    if not uv_plan.get("eligible"):
        return uv_plan
    file_node, reason = _mouth_alpha_file_node(record)
    if not file_node:
        return {"eligible": False, "reason": reason}
    texture_path, reason = _mouth_alpha_texture_path(file_node, uv_plan["udim"])
    if not texture_path:
        return {"eligible": False, "reason": reason}
    cache_key = os.path.normcase(os.path.abspath(texture_path))
    if cache_key not in alpha_bbox_cache:
        alpha_bbox_cache[cache_key] = _mouth_alpha_bbox_from_image(texture_path)
    alpha_bbox, reason = alpha_bbox_cache[cache_key]
    if alpha_bbox is None:
        return {"eligible": False, "reason": reason}
    if not _alpha_bbox_fits_inner_uv(alpha_bbox, uv_plan.get("inner_bbox")):
        return {"eligible": False, "reason": "alpha_touches_outer_ring"}
    primary_plug = shape + ".primaryVisibility"
    try:
        if not cmds.objExists(primary_plug):
            return {"eligible": False, "reason": "primary_visibility_missing"}
        if _incoming_source_plugs(primary_plug):
            return {"eligible": False, "reason": "primary_visibility_connected"}
    except Exception:
        return {"eligible": False, "reason": "primary_visibility_unreadable"}
    result = dict(topology)
    result.update({
        "eligible": True,
        "reason": "",
        "inner_bbox": tuple(uv_plan["inner_bbox"]),
        "udim": int(uv_plan["udim"]),
    })
    return result


def _increment_reason(report, field, reason):
    reason = _clean(reason) or "unknown"
    values = report.setdefault(field, {})
    values[reason] = int(values.get(reason) or 0) + 1


class _MouthCardRestorationError(RuntimeError):
    pass


class _MouthCardInnerPatchController(object):
    """Per-frame, disposable mouth-card geometry patch for VP2 capture only."""

    def __init__(self, job, stage):
        self.job = job if isinstance(job, dict) else {}
        self.stage = _clean(stage) or "original"
        self.eligible = {}
        self.candidates = set()
        self.static_depth_excluded = set()
        self.dynamic_depth_excluded = set()
        self.active = []
        self.applied_shapes = set()
        self.depth_exclusion_group = ""
        self.depth_hidden_layer = ""
        self.depth_layer_memberships = {}
        self.report = {
            "policy": MOUTH_CARD_INNER_PATCH_POLICY,
            "stage": self.stage,
            "requested": True,
            "candidate_shape_path_count": 0,
            "eligible_shape_path_count": 0,
            "skipped_shape_path_count": 0,
            "depth_excluded_shape_path_count": 0,
            "depth_hidden_shape_path_count": 0,
            "depth_scope_restore_failure_count": 0,
            "applied_frame_count": 0,
            "applied_frame_shape_count": 0,
            "applied_shape_path_count": 0,
            "restored_frame_shape_count": 0,
            "deleted_outer_face_count": 0,
            "runtime_skipped_frame_shape_count": 0,
            "runtime_exclusion_verified_shape_path_count": 0,
            "restore_failure_count": 0,
            "skip_reason_counts": {},
            "runtime_skip_reason_counts": {},
            "restore_ok": True,
            "status": "ready",
        }
        alpha_bbox_cache = {}
        snapshot = self.job.get("_authored_cutout_snapshot") or {}
        for shape, record in sorted(snapshot.items()):
            if not _mouth_semantic_cutout_candidate(shape, record):
                continue
            self.candidates.add(shape)
            if self.stage == "depth":
                # Product contract: image-style mouth alpha cards never
                # contribute to Depth.  Exclude them before range analysis and
                # shader assignment; Original alone may use the inner patch.
                self.static_depth_excluded.add(shape)
                _increment_reason(
                    self.report,
                    "skip_reason_counts",
                    "depth_policy_excludes_mouth_alpha",
                )
                continue
            plan = _mouth_card_static_plan(
                shape,
                record,
                alpha_bbox_cache=alpha_bbox_cache,
            )
            if plan.get("eligible"):
                self.eligible[shape] = plan
            else:
                _increment_reason(
                    self.report,
                    "skip_reason_counts",
                    plan.get("reason"),
                )
        self.report["candidate_shape_path_count"] = len(self.candidates)
        self.report["eligible_shape_path_count"] = len(self.eligible)
        self.report["skipped_shape_path_count"] = (
            len(self.candidates) - len(self.eligible)
        )
        self.report["depth_excluded_shape_path_count"] = len(
            self.static_depth_excluded
        )
        if self.stage == "depth":
            self.job["_mouth_depth_excluded_shape_paths"] = sorted(
                self.static_depth_excluded
            )

    def _ensure_depth_exclusion_group(self):
        if self.depth_exclusion_group and cmds.objExists(self.depth_exclusion_group):
            return self.depth_exclusion_group
        group = _surface_shader(
            "HMB_DepthMouthExcluded",
            (0.0, 0.0, 0.0),
            fresh=True,
        )
        source_plugs = _incoming_source_plugs(group + ".surfaceShader")
        if len(source_plugs) != 1:
            raise RuntimeError("Depth mouth exclusion shader is incomplete.")
        shader = source_plugs[0].split(".", 1)[0]
        transparency_plug = shader + ".outTransparency"
        cmds.setAttr(transparency_plug, 1.0, 1.0, 1.0, type="double3")
        values = _plug_value(transparency_plug)
        if len(values) != 3 or any(abs(value - 1.0) > 1.0e-9 for value in values):
            raise RuntimeError("Depth mouth exclusion shader is not transparent.")
        self.depth_exclusion_group = group
        return group

    def _ensure_depth_hidden_layer(self):
        if self.depth_hidden_layer and cmds.objExists(self.depth_hidden_layer):
            return self.depth_hidden_layer
        layer = cmds.createDisplayLayer(
            empty=True,
            name="HMB_DepthMouthExcludedLayer#",
        )
        self.depth_hidden_layer = layer
        cmds.setAttr(layer + ".visibility", 0)
        if bool(cmds.getAttr(layer + ".visibility")):
            raise RuntimeError("Depth mouth exclusion layer remained visible.")
        return layer

    @staticmethod
    def _depth_display_layers(shape):
        try:
            return sorted(set(
                _clean(layer)
                for layer in (
                    cmds.listConnections(
                        shape,
                        source=True,
                        destination=False,
                        type="displayLayer",
                    ) or []
                )
                if _clean(layer)
            ))
        except Exception:
            return []

    def _hide_depth_shape(self, shape):
        if shape in self.depth_layer_memberships:
            return
        layer = self._ensure_depth_hidden_layer()
        original_layers = self._depth_display_layers(shape)
        # Record before mutation so the pass-level finally can repair even a
        # partially successful editDisplayLayerMembers call.
        self.depth_layer_memberships[shape] = original_layers
        cmds.editDisplayLayerMembers(
            layer,
            shape,
            noRecurse=True,
        )
        current_layers = self._depth_display_layers(shape)
        if layer not in current_layers or not _display_layer_hidden(shape)[0]:
            raise RuntimeError("Depth mouth exclusion layer did not hide its shape.")
        self.report["depth_hidden_shape_path_count"] = len(
            self.depth_layer_memberships
        )

    def _assign_depth_exclusion(self, shape, reason, dynamic=True):
        if self.stage != "depth":
            return
        self._hide_depth_shape(shape)
        if dynamic:
            # The hidden display layer is the primary exclusion mechanism.  A
            # fully transparent SG is a second guard against an opaque marker
            # SG leaking if a driver/plugin ignores display-layer visibility.
            group = self._ensure_depth_exclusion_group()
            failures = _assign([shape], group)
            if failures or group not in _shape_shading_groups(shape):
                raise RuntimeError(
                    "Depth could not exclude one unverified mouth alpha shape."
                )
        if dynamic and shape not in self.dynamic_depth_excluded:
            self.dynamic_depth_excluded.add(shape)
            _increment_reason(
                self.report,
                "runtime_skip_reason_counts",
                reason,
            )
            self.report["runtime_skipped_frame_shape_count"] += 1
        self.report["depth_excluded_shape_path_count"] = len(
            self.static_depth_excluded.union(self.dynamic_depth_excluded)
        )

    def activate_static_depth_exclusions(self):
        for shape in sorted(self.static_depth_excluded):
            self._assign_depth_exclusion(
                shape,
                "static_verification_failed",
                dynamic=False,
            )

    def depth_assignment_group(self, shape):
        if shape not in self.static_depth_excluded and shape not in self.dynamic_depth_excluded:
            return ""
        if shape in self.static_depth_excluded:
            return ""
        return self._ensure_depth_exclusion_group()

    def depth_assignment_failed(self, shape, reason):
        self._assign_depth_exclusion(shape, reason, dynamic=True)
        return self.depth_exclusion_group

    @staticmethod
    def _node_lock_value(node):
        try:
            values = cmds.lockNode(node, query=True, lock=True) or [False]
            return bool(values[0])
        except Exception:
            return False

    def _hide_source(self, shape):
        plug = shape + ".primaryVisibility"
        if _incoming_source_plugs(plug):
            raise RuntimeError("primary_visibility_connected")
        value = cmds.getAttr(plug)
        attribute_locked = bool(cmds.getAttr(plug, lock=True))
        node_locked = self._node_lock_value(shape)
        try:
            if node_locked:
                cmds.lockNode(shape, lock=False)
            if attribute_locked:
                cmds.setAttr(plug, lock=False)
            cmds.setAttr(plug, 0)
            if bool(cmds.getAttr(plug)):
                raise RuntimeError("primary_visibility_hide_failed")
        except Exception as original_exc:
            restore_failures = []
            try:
                if self._node_lock_value(shape):
                    cmds.lockNode(shape, lock=False)
                if cmds.getAttr(plug, lock=True):
                    cmds.setAttr(plug, lock=False)
                cmds.setAttr(plug, value)
                cmds.setAttr(plug, lock=attribute_locked)
                cmds.lockNode(shape, lock=node_locked)
                if not _same_attr_value(cmds.getAttr(plug), value):
                    restore_failures.append("primary visibility value")
                if bool(cmds.getAttr(plug, lock=True)) != attribute_locked:
                    restore_failures.append("primary visibility lock")
                if self._node_lock_value(shape) != node_locked:
                    restore_failures.append("shape node lock")
            except Exception as restore_exc:
                restore_failures.append(
                    _clean(restore_exc) or restore_exc.__class__.__name__
                )
            if restore_failures:
                raise _MouthCardRestorationError(
                    "Mouth source rollback failed after {0}: {1}".format(
                        _clean(original_exc) or original_exc.__class__.__name__,
                        " | ".join(restore_failures),
                    )
                )
            raise
        return {
            "shape": shape,
            "plug": plug,
            "value": value,
            "attribute_locked": attribute_locked,
            "node_locked": node_locked,
        }

    def _prepare_shape(self, shape, plan):
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        groups = _shape_shading_groups(shape)
        if len(parents) != 1 or len(groups) != 1:
            raise RuntimeError("source_parent_or_shading_group_mismatch")
        duplicate_parent = ""
        hide_state = None
        try:
            duplicate_parent = cmds.duplicate(
                parents[0],
                returnRootsOnly=True,
                name="HMB_MouthInnerPatch#",
            )[0]
            cmds.delete(duplicate_parent, constructionHistory=True)
            duplicate_shapes = cmds.listRelatives(
                duplicate_parent,
                shapes=True,
                noIntermediate=True,
                fullPath=True,
                type="mesh",
            ) or []
            descendant_nodes = cmds.listRelatives(
                duplicate_parent,
                allDescendents=True,
                fullPath=True,
            ) or list(duplicate_shapes)
            descendant_shapes = []
            for item in descendant_nodes:
                try:
                    inherited_types = cmds.nodeType(item, inherited=True) or []
                except Exception:
                    inherited_types = []
                if isinstance(inherited_types, str):
                    inherited_types = [inherited_types]
                if "shape" in inherited_types and not _is_intermediate_shape(item):
                    descendant_shapes.append(item)
            if (
                len(duplicate_shapes) != 1
                or len(set(descendant_shapes)) != 1
                or duplicate_shapes[0] not in descendant_shapes
            ):
                raise RuntimeError("duplicate_shape_count_mismatch")
            duplicate_shape = duplicate_shapes[0]
            source_matrix = cmds.xform(
                parents[0], query=True, worldSpace=True, matrix=True
            ) or []
            duplicate_matrix = cmds.xform(
                duplicate_parent, query=True, worldSpace=True, matrix=True
            ) or []
            if len(source_matrix) != 16 or len(duplicate_matrix) != 16 or any(
                abs(float(first) - float(second)) > 1.0e-7
                for first, second in zip(source_matrix, duplicate_matrix)
            ):
                raise RuntimeError("duplicate_world_matrix_mismatch")
            duplicate_plan = _mouth_mesh_inner_patch_plan(duplicate_shape)
            if not duplicate_plan.get("eligible"):
                raise RuntimeError("duplicate_topology_mismatch")
            if duplicate_plan.get("outer_faces") != plan.get("outer_faces"):
                raise RuntimeError("duplicate_face_index_mismatch")
            cmds.sets(duplicate_shape, edit=True, forceElement=groups[0])
            if groups[0] not in _shape_shading_groups(duplicate_shape):
                raise RuntimeError("duplicate_shading_group_mismatch")
            cmds.delete([
                "{0}.f[{1}]".format(duplicate_shape, int(face_index))
                for face_index in plan.get("outer_faces") or []
            ])
            remaining = {
                "vertex": int(cmds.polyEvaluate(duplicate_shape, vertex=True) or 0),
                "edge": int(cmds.polyEvaluate(duplicate_shape, edge=True) or 0),
                "face": int(cmds.polyEvaluate(duplicate_shape, face=True) or 0),
            }
            if remaining != {"vertex": 25, "edge": 40, "face": 16}:
                raise RuntimeError("trimmed_topology_mismatch")
            hide_state = self._hide_source(shape)
            return {
                "shape": shape,
                "duplicate_parent": duplicate_parent,
                "hide_state": hide_state,
                "outer_face_count": len(plan.get("outer_faces") or []),
            }
        except Exception as exc:
            cleanup_failure = ""
            if hide_state:
                try:
                    self._restore_entry({
                        "shape": shape,
                        "duplicate_parent": duplicate_parent,
                        "hide_state": hide_state,
                    })
                except Exception as cleanup_exc:
                    cleanup_failure = _clean(cleanup_exc) or cleanup_exc.__class__.__name__
            elif duplicate_parent and cmds.objExists(duplicate_parent):
                try:
                    cmds.delete(duplicate_parent)
                    if cmds.objExists(duplicate_parent):
                        raise RuntimeError("temporary duplicate still exists")
                except Exception as cleanup_exc:
                    cleanup_failure = _clean(cleanup_exc) or cleanup_exc.__class__.__name__
            if cleanup_failure:
                raise _MouthCardRestorationError(
                    "Mouth patch cleanup failed after {0}: {1}".format(
                        _clean(exc) or exc.__class__.__name__,
                        cleanup_failure,
                    )
                )
            raise

    def prepare_frame(self, _frame, _frame_index=None, _frame_count=None):
        if self.active:
            raise RuntimeError("previous mouth-card frame state was not restored")
        applied = 0
        for shape, plan in sorted(self.eligible.items()):
            if shape in self.dynamic_depth_excluded:
                continue
            if not _motion_path_visible(shape):
                continue
            try:
                entry = self._prepare_shape(shape, plan)
            except Exception as exc:
                reason = _clean(exc) or exc.__class__.__name__
                if isinstance(exc, _MouthCardRestorationError):
                    self.report["restore_failure_count"] += 1
                    self.report["restore_ok"] = False
                    self.report["status"] = "restore_failed"
                    raise
                if self.stage == "depth":
                    self._assign_depth_exclusion(shape, reason, dynamic=True)
                else:
                    _increment_reason(
                        self.report,
                        "runtime_skip_reason_counts",
                        reason,
                    )
                    self.report["runtime_skipped_frame_shape_count"] += 1
                continue
            self.active.append(entry)
            applied += 1
            self.applied_shapes.add(shape)
            self.report["applied_frame_shape_count"] += 1
            self.report["deleted_outer_face_count"] += int(
                entry.get("outer_face_count") or 0
            )
        if applied:
            self.report["applied_frame_count"] += 1
            self.report["status"] = "applied"
            cmds.refresh(force=True)

    def _restore_entry(self, entry):
        state = entry.get("hide_state") or {}
        shape = state.get("shape") or entry.get("shape")
        plug = state.get("plug") or (shape + ".primaryVisibility")
        node_locked = bool(state.get("node_locked"))
        attribute_locked = bool(state.get("attribute_locked"))
        failures = []
        try:
            if self._node_lock_value(shape):
                cmds.lockNode(shape, lock=False)
            if cmds.getAttr(plug, lock=True):
                cmds.setAttr(plug, lock=False)
            cmds.setAttr(plug, state.get("value"))
            cmds.setAttr(plug, lock=attribute_locked)
            cmds.lockNode(shape, lock=node_locked)
            if not _same_attr_value(cmds.getAttr(plug), state.get("value")):
                failures.append("mouth source visibility value was not restored")
            if bool(cmds.getAttr(plug, lock=True)) != attribute_locked:
                failures.append("mouth source visibility lock was not restored")
            if self._node_lock_value(shape) != node_locked:
                failures.append("mouth source node lock was not restored")
        except Exception as exc:
            failures.append(_clean(exc) or exc.__class__.__name__)
        duplicate_parent = _clean(entry.get("duplicate_parent"))
        try:
            if duplicate_parent and cmds.objExists(duplicate_parent):
                cmds.delete(duplicate_parent)
            if duplicate_parent and cmds.objExists(duplicate_parent):
                failures.append("temporary mouth patch was not deleted")
        except Exception as exc:
            failures.append(_clean(exc) or exc.__class__.__name__)
        if failures:
            raise _MouthCardRestorationError(" | ".join(failures))

    def restore_frame(self, _frame=None, _frame_index=None, _frame_count=None):
        failures = []
        failed_entries = []
        active = list(reversed(self.active))
        self.active = []
        for entry in active:
            try:
                self._restore_entry(entry)
                self.report["restored_frame_shape_count"] += 1
            except Exception as exc:
                failures.append(_clean(exc) or exc.__class__.__name__)
                failed_entries.append(entry)
                self.report["restore_failure_count"] += 1
        # Keep failed entries so the pass-level finally can make one more
        # idempotent restoration attempt before any later pass is allowed.
        self.active = list(reversed(failed_entries))
        self.report["applied_shape_path_count"] = len(self.applied_shapes)
        self.report["restore_ok"] = not failures
        if failures:
            self.report["status"] = "restore_failed"
            raise _MouthCardRestorationError(
                "Temporary mouth-card geometry restoration failed ({0}).".format(
                    len(failures)
                )
            )

    def _restore_depth_scope(self):
        if self.stage != "depth":
            return
        failures = []
        layer = self.depth_hidden_layer
        for shape, original_layers in sorted(self.depth_layer_memberships.items()):
            try:
                non_default_layers = [
                    item for item in original_layers if item != "defaultLayer"
                ]
                if len(non_default_layers) > 1:
                    raise RuntimeError("authored display-layer membership was ambiguous")
                target_layer = (
                    non_default_layers[0]
                    if non_default_layers
                    else "defaultLayer"
                )
                cmds.editDisplayLayerMembers(
                    target_layer,
                    shape,
                    noRecurse=True,
                )
                current_layers = self._depth_display_layers(shape)
                current_non_default = sorted(
                    item
                    for item in current_layers
                    if item not in ("defaultLayer", layer)
                )
                if current_non_default != sorted(non_default_layers):
                    raise RuntimeError("authored display-layer membership was not restored")
                if layer in current_layers:
                    raise RuntimeError("shape remained in the Depth exclusion layer")
            except Exception as exc:
                failures.append(_clean(exc) or exc.__class__.__name__)
        try:
            if layer and cmds.objExists(layer):
                cmds.delete(layer)
            if layer and cmds.objExists(layer):
                failures.append("Depth mouth exclusion layer was not deleted")
        except Exception as exc:
            failures.append(_clean(exc) or exc.__class__.__name__)
        self.depth_layer_memberships = {}
        self.depth_hidden_layer = ""
        if failures:
            self.report["depth_scope_restore_failure_count"] += len(failures)
            self.report["restore_failure_count"] += len(failures)
            self.report["restore_ok"] = False
            self.report["status"] = "restore_failed"
            raise _MouthCardRestorationError(
                "Depth mouth exclusion scope restoration failed ({0}).".format(
                    len(failures)
                )
            )

    def finish(self):
        finish_failures = []
        if self.active:
            try:
                self.restore_frame()
            except Exception as exc:
                finish_failures.append(_clean(exc) or exc.__class__.__name__)
        try:
            self._restore_depth_scope()
        except Exception as exc:
            finish_failures.append(_clean(exc) or exc.__class__.__name__)
        self.report["applied_shape_path_count"] = len(self.applied_shapes)
        self.report["restore_ok"] = bool(
            not finish_failures
            and int(self.report.get("restore_failure_count") or 0) == 0
            and int(self.report.get("applied_frame_shape_count") or 0)
            == int(self.report.get("restored_frame_shape_count") or 0)
        )
        if not self.report["restore_ok"]:
            self.report["status"] = "restore_failed"
            raise _MouthCardRestorationError(
                "Temporary mouth-card capture state was not restored{0}.".format(
                    " ({0})".format(" | ".join(finish_failures))
                    if finish_failures
                    else ""
                )
            )
        if self.report["status"] == "ready":
            self.report["status"] = (
                "not_needed" if not self.candidates else "skipped"
            )
        # Serialized reports contain counts/reasons only, never scene or texture paths.
        return dict(self.report)


def _cutout_variant_token(source_plug):
    return hashlib.sha256(
        _clean(source_plug).encode("utf-8")
    ).hexdigest()[:12]


def _connect_authored_transparency(source_plug, target_plug):
    source_plug = _clean(source_plug)
    if not source_plug or not cmds.objExists(source_plug):
        raise RuntimeError(
            "Authored cutout transparency source no longer exists: {0}".format(
                source_plug or "<empty>"
            )
        )
    if not cmds.objExists(target_plug):
        raise RuntimeError(
            "Temporary cutout shader has no transparency input: {0}".format(
                target_plug
            )
        )
    cmds.connectAttr(source_plug, target_plug, force=True)
    if not cmds.isConnected(source_plug, target_plug):
        raise RuntimeError(
            "Temporary cutout shader did not retain {0} -> {1}.".format(
                source_plug,
                target_plug,
            )
        )


def _surface_shader(name, rgb, fresh=False, transparency_source=""):
    shader_name = name + "_SurfaceShader"
    if fresh or not cmds.objExists(shader_name):
        # A Depth capture must never reuse authored or stale shader state from
        # a Maya file merely because its node has an HMB-looking name.
        shader = cmds.shadingNode(
            "surfaceShader",
            asShader=True,
            name=shader_name + ("#" if cmds.objExists(shader_name) else ""),
        )
    else:
        shader = shader_name
    cmds.setAttr(shader + ".outColor", rgb[0], rgb[1], rgb[2], type="double3")
    for attribute in ("outTransparency", "outGlowColor"):
        plug = shader + "." + attribute
        if cmds.objExists(plug):
            if attribute == "outTransparency" and transparency_source:
                continue
            cmds.setAttr(plug, 0.0, 0.0, 0.0, type="double3")
    shading_group_name = shader + "SG"
    if fresh or not cmds.objExists(shading_group_name):
        shading_group = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=(
                shading_group_name + "#"
                if cmds.objExists(shading_group_name)
                else shading_group_name
            ),
        )
    else:
        shading_group = shading_group_name
    if not cmds.isConnected(
        shader + ".outColor",
        shading_group + ".surfaceShader",
    ):
        cmds.connectAttr(
            shader + ".outColor",
            shading_group + ".surfaceShader",
            force=True,
        )
    if transparency_source:
        _connect_authored_transparency(
            transparency_source,
            shader + ".outTransparency",
        )
    return shading_group


def _lambert_shader(name, rgb, fresh=False, transparency_source=""):
    shader_name = name + "_Lambert"
    if fresh or not cmds.objExists(shader_name):
        shader = cmds.shadingNode(
            "lambert",
            asShader=True,
            name=(shader_name + "#" if cmds.objExists(shader_name) else shader_name),
        )
    else:
        shader = shader_name
    shading_group = shader + "SG"
    cmds.setAttr(shader + ".color", rgb[0], rgb[1], rgb[2], type="double3")
    for attribute, value in (
        ("diffuse", CHARACTER_LAMBERT_DIFFUSE),
        ("translucence", 0.0),
        ("translucenceDepth", 0.0),
    ):
        plug = shader + "." + attribute
        if cmds.objExists(plug):
            cmds.setAttr(plug, value)
    color_gains = (
        ("ambientColor", CHARACTER_LAMBERT_AMBIENT_GAIN),
        ("incandescence", CHARACTER_LAMBERT_INCANDESCENCE_GAIN),
    )
    for attribute, gain in color_gains:
        plug = shader + "." + attribute
        if cmds.objExists(plug):
            cmds.setAttr(
                plug,
                rgb[0] * gain,
                rgb[1] * gain,
                rgb[2] * gain,
                type="double3",
            )
    if not cmds.objExists(shading_group):
        shading_group = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=shading_group,
        )
    if not cmds.isConnected(shader + ".outColor", shading_group + ".surfaceShader"):
        cmds.connectAttr(shader + ".outColor", shading_group + ".surfaceShader", force=True)
    if transparency_source:
        _connect_authored_transparency(
            transparency_source,
            shader + ".transparency",
        )
    return shading_group


def _character_outline_mode(job):
    """Resolve the explicit outline mode; missing jobs use the fast production profile."""
    value = _clean((job or {}).get("character_outline_mode")).lower()
    if not value or value in ("native", "native_lambert", "none", "off"):
        return CHARACTER_OUTLINE_NATIVE
    if value in ("pfx", "pfxtoon", "pfx_toon"):
        return CHARACTER_OUTLINE_PFX
    raise RuntimeError("Unsupported character_outline_mode: {0}".format(value))


def _character_out_rim(name, shapes):
    """Create the legacy pfxToon profile for explicit diagnostic comparison only."""
    toon = cmds.createNode("pfxToon", name=name + "_OutRim")
    scalar_attributes = (
        ("displayPercent", 100.0),
        ("displayInViewport", 1),
        ("profileLines", 1),
        ("borderLines", 0),
        ("creaseLines", 0),
        ("intersectionLines", 0),
        ("selfIntersect", 0),
        ("smoothProfile", 1),
        ("tighterProfile", 1),
        ("resampleProfile", 0),
        ("screenSpaceResampling", CHARACTER_OUT_RIM_SCREENSPACE_RESAMPLING),
        ("profileBreakAngle", 180.0),
        ("lineWidth", 0.12),
        ("profileLineWidth", 1.0),
        ("lineOpacity", CHARACTER_OUT_RIM_OPACITY),
        ("lineOffset", CHARACTER_OUT_RIM_LINE_OFFSET),
        ("lightingBasedWidth", 0.0),
        ("profileWidthModulation", 0.0),
        ("screenspaceWidth", 1),
        ("distanceScaling", 0.0),
        ("minPixelWidth", CHARACTER_OUT_RIM_MIN_PIXEL_WIDTH),
        ("maxPixelWidth", CHARACTER_OUT_RIM_MAX_PIXEL_WIDTH),
        ("localOcclusion", CHARACTER_OUT_RIM_LOCAL_OCCLUSION),
        ("occlusionWidthScale", 1),
    )
    for attribute, value in scalar_attributes:
        plug = toon + "." + attribute
        if cmds.objExists(plug):
            cmds.setAttr(plug, value)
    if cmds.objExists(toon + ".profileColor"):
        cmds.setAttr(toon + ".profileColor", 0.0, 0.0, 0.0, type="double3")

    warnings = []
    connected = 0
    for shape in shapes:
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if not parents:
            warnings.append("Out-Rim parent transform was not found: {0}".format(shape))
            continue
        input_surface = "{0}.inputSurface[{1}]".format(toon, connected)
        try:
            cmds.connectAttr(shape + ".outMesh", input_surface + ".surface", force=True)
            cmds.connectAttr(parents[0] + ".worldMatrix[0]", input_surface + ".inputWorldMatrix", force=True)
            connected += 1
        except Exception as exc:
            warnings.append("Out-Rim connection failed for {0}: {1}".format(shape, exc))
    if not connected:
        raise RuntimeError("Character Out-Rim could not be connected to any polygon shape.")
    return warnings


def _png_chunk(tag, data):
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _pattern_pixel(pattern, x, y, size):
    if pattern == "direction_checker":
        tile = max(
            SCREEN_SPACE_PATTERN_MIN_CELL_PIXELS,
            size // SCREEN_SPACE_PATTERN_CELL_DIVISOR,
        )
        dark = ((x // tile) + (y // tile)) % 2 == 0
        return (0, 0, 0) if dark else (255, 255, 255)
    if pattern == "sky_grid":
        step = max(
            SCREEN_SPACE_PATTERN_MIN_CELL_PIXELS,
            size // SCREEN_SPACE_PATTERN_CELL_DIVISOR,
        )
        major = max(step * 4, 1)
        major_width = max(1, min(4, max(1, step // 2)))
        minor_width = max(1, min(2, max(1, step // 2)))
        if x % major < major_width or y % major < major_width:
            return (255, 255, 255)
        if x % step < minor_width or y % step < minor_width:
            return (191, 242, 255)
        return (67, 155, 231)
    if pattern == "floor_grid":
        step = max(
            SCREEN_SPACE_PATTERN_MIN_CELL_PIXELS,
            size // SCREEN_SPACE_PATTERN_CELL_DIVISOR,
        )
        line_width = max(1, min(3, max(1, step // 2)))
        if x % step < line_width or y % step < line_width:
            return (255, 231, 151)
        checker = ((x // step) + (y // step)) % 2
        return (105, 83, 51) if checker else (132, 107, 66)
    if pattern == "position_pattern":
        tile_x = min(
            POSITION_PATTERN_REPEATS - 1,
            max(0, x * POSITION_PATTERN_REPEATS // max(1, size)),
        )
        tile_y = min(
            POSITION_PATTERN_REPEATS - 1,
            max(0, y * POSITION_PATTERN_REPEATS // max(1, size)),
        )
        left = tile_x * size // POSITION_PATTERN_REPEATS
        right = (tile_x + 1) * size // POSITION_PATTERN_REPEATS
        top = tile_y * size // POSITION_PATTERN_REPEATS
        bottom = (tile_y + 1) * size // POSITION_PATTERN_REPEATS
        half_x = left + max(1, right - left) // 2
        half_y = top + max(1, bottom - top) // 2
        if abs(x - half_x) <= 1 or abs(y - half_y) <= 1:
            return (255, 255, 255)
        if x < half_x and y < half_y:
            return (239, 65, 65)
        if x >= half_x and y < half_y:
            return (62, 205, 119)
        if x < half_x and y >= half_y:
            return (57, 104, 232)
        return (246, 210, 49)
    raise RuntimeError("Unknown HMB marker pattern: {0}".format(pattern))


def _write_pattern_png(path, pattern, size=512):
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw.extend(bytearray(_pattern_pixel(pattern, x, y, size)))
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    payload = signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _png_chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def _connect_2d_texture(place, texture):
    for source, target in (
        ("coverage", "coverage"),
        ("translateFrame", "translateFrame"),
        ("rotateFrame", "rotateFrame"),
        ("mirrorU", "mirrorU"),
        ("mirrorV", "mirrorV"),
        ("stagger", "stagger"),
        ("wrapU", "wrapU"),
        ("wrapV", "wrapV"),
        ("repeatUV", "repeatUV"),
        ("offset", "offset"),
        ("rotateUV", "rotateUV"),
        ("noiseUV", "noiseUV"),
        ("vertexUvOne", "vertexUvOne"),
        ("vertexUvTwo", "vertexUvTwo"),
        ("vertexUvThree", "vertexUvThree"),
        ("vertexCameraOne", "vertexCameraOne"),
    ):
        try:
            cmds.connectAttr(place + "." + source, texture + "." + target, force=True)
        except Exception:
            pass
    try:
        cmds.connectAttr(place + ".outUV", texture + ".uvCoord", force=True)
        cmds.connectAttr(place + ".outUvFilterSize", texture + ".uvFilterSize", force=True)
    except Exception:
        pass


def _texture_surface_group(name, texture, place):
    shader = name + "_SurfaceShader"
    shading_group = shader + "SG"
    if not cmds.objExists(shader):
        shader = cmds.shadingNode("surfaceShader", asShader=True, name=shader)
    _connect_2d_texture(place, texture)
    if not cmds.isConnected(texture + ".outColor", shader + ".outColor"):
        cmds.connectAttr(texture + ".outColor", shader + ".outColor", force=True)
    if not cmds.objExists(shading_group):
        shading_group = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=shading_group,
        )
    if not cmds.isConnected(shader + ".outColor", shading_group + ".surfaceShader"):
        cmds.connectAttr(shader + ".outColor", shading_group + ".surfaceShader", force=True)
    return shading_group


def _reference_procedural_pattern_shader(name, pattern):
    """Rebuild the two Maya procedural Surface Shaders used by the approved reference."""
    place = name + "_Place2d"
    if not cmds.objExists(place):
        place = cmds.shadingNode("place2dTexture", asUtility=True, name=place)
    if pattern == "direction_checker":
        texture = name + "_Checker"
        if not cmds.objExists(texture):
            texture = cmds.shadingNode("checker", asTexture=True, name=texture)
        cmds.setAttr(texture + ".color1", 1.0, 1.0, 1.0, type="double3")
        cmds.setAttr(texture + ".color2", 0.0, 0.0, 0.0, type="double3")
        if cmds.objExists(texture + ".contrast"):
            cmds.setAttr(texture + ".contrast", 1.0)
        cmds.setAttr(
            place + ".repeatU",
            20.0 * SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR,
        )
        cmds.setAttr(
            place + ".repeatV",
            20.0 * SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR,
        )
        return _texture_surface_group(name, texture, place)
    if pattern == "sky_grid":
        texture = name + "_Bulge"
        if not cmds.objExists(texture):
            texture = cmds.shadingNode("bulge", asTexture=True, name=texture)
        cmds.setAttr(texture + ".uWidth", 0.022900763899087906)
        cmds.setAttr(texture + ".vWidth", 0.036259543150663376)
        cmds.setAttr(texture + ".defaultColor", 0.0, 1.0, 1.0, type="double3")
        cmds.setAttr(texture + ".colorGain", 0.0, 1.0, 1.0, type="double3")
        cmds.setAttr(texture + ".alphaGain", 2.0)
        cmds.setAttr(
            place + ".repeatU",
            50.0 * SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR,
        )
        cmds.setAttr(
            place + ".repeatV",
            10.0 * SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR,
        )
        return _texture_surface_group(name, texture, place)
    return ""


def _pattern_shader(name, pattern, texture_folder):
    reference_group = _reference_procedural_pattern_shader(name, pattern)
    if reference_group:
        return reference_group
    shader = name + "_SurfaceShader"
    shading_group = shader + "SG"
    file_node = name + "_File"
    place = name + "_Place2d"
    texture_path = _write_pattern_png(
        os.path.join(texture_folder, _safe_token(pattern) + ".png"),
        pattern,
    )
    if not cmds.objExists(shader):
        shader = cmds.shadingNode("surfaceShader", asShader=True, name=shader)
    if not cmds.objExists(file_node):
        try:
            file_node = cmds.shadingNode("file", asTexture=True, isColorManaged=True, name=file_node)
        except TypeError:
            file_node = cmds.shadingNode("file", asTexture=True, name=file_node)
    if not cmds.objExists(place):
        place = cmds.shadingNode("place2dTexture", asUtility=True, name=place)
    _connect_2d_texture(place, file_node)
    cmds.setAttr(file_node + ".fileTextureName", texture_path, type="string")
    try:
        cmds.setAttr(file_node + ".colorSpace", "Raw", type="string")
    except Exception:
        pass
    try:
        cmds.setAttr(place + ".repeatU", 1.0)
        cmds.setAttr(place + ".repeatV", 1.0)
    except Exception:
        pass
    if not cmds.isConnected(file_node + ".outColor", shader + ".outColor"):
        cmds.connectAttr(file_node + ".outColor", shader + ".outColor", force=True)
    if not cmds.objExists(shading_group):
        shading_group = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=shading_group,
        )
    if not cmds.isConnected(shader + ".outColor", shading_group + ".surfaceShader"):
        cmds.connectAttr(shader + ".outColor", shading_group + ".surfaceShader", force=True)
    return shading_group


def _assign(shapes, shading_group):
    failures = []
    for shape in shapes:
        try:
            cmds.sets(shape, edit=True, forceElement=shading_group)
        except Exception as exc:
            failures.append("{0}: {1}".format(shape, exc))
    return failures


def _verify_depth_shader_assignment(shapes_or_assignments, shading_group=None):
    """Verify each full DAG path against its exact expected depth SG.

    A single shared shading group remains accepted for compatibility with
    focused callers.  The production depth path supplies a per-path mapping so
    independently transformed instances can use different grayscale buckets.
    """
    if shading_group is not None:
        expected_assignments = dict(
            (shape, shading_group) for shape in (shapes_or_assignments or [])
        )
    elif isinstance(shapes_or_assignments, dict):
        expected_assignments = dict(shapes_or_assignments)
    else:
        raise RuntimeError(
            "Depth shader assignment verification requires a full DAG path "
            "to shadingEngine mapping."
        )
    shapes = sorted(expected_assignments)
    report = {
        "shape_path_count": len(shapes),
        "mesh_path_count": 0,
        "nurbs_surface_path_count": 0,
        "verified_shape_path_count": 0,
        "verified_mesh_face_count": 0,
    }
    target_objects = {}

    failures = []
    for shape in shapes:
        expected_group = _clean(expected_assignments.get(shape))
        if not expected_group:
            failures.append(shape + ": expected shadingEngine is empty")
            continue
        try:
            shape_type = _clean(cmds.nodeType(shape))
        except Exception as exc:
            failures.append(
                "{0}: node type query failed ({1})".format(shape, exc)
            )
            continue
        if shape_type == "mesh":
            report["mesh_path_count"] += 1
            try:
                mesh_om, dag_path, mesh_function = _depth_mesh_api(shape)
                target_object = target_objects.get(expected_group)
                if target_object is None:
                    selection = mesh_om.MSelectionList()
                    selection.add(expected_group)
                    target_object = selection.getDependNode(0)
                    target_objects[expected_group] = target_object
                polygon_count = mesh_function.numPolygons
                if callable(polygon_count):
                    polygon_count = polygon_count()
                polygon_count = int(polygon_count)
                if polygon_count <= 0:
                    raise RuntimeError(
                        "MFnMesh.numPolygons returned {0}".format(
                            polygon_count
                        )
                    )
                instance_number = dag_path.instanceNumber()
                shader_objects, face_shader_indices = (
                    mesh_function.getConnectedShaders(instance_number)
                )
                target_indices = [
                    index
                    for index, shader_object in enumerate(shader_objects)
                    if shader_object == target_object
                ]
                if len(target_indices) != 1:
                    connected_names = []
                    for shader_object in shader_objects:
                        try:
                            connected_names.append(
                                    _clean(
                                    mesh_om.MFnDependencyNode(shader_object).name()
                                )
                            )
                        except Exception:
                            connected_names.append("<unknown>")
                    raise RuntimeError(
                        "expected shadingEngine {0} occurs {1} times; "
                        "connected: {2}".format(
                            expected_group,
                            len(target_indices),
                            ", ".join(connected_names) or "<none>",
                        )
                    )
                if len(face_shader_indices) != polygon_count:
                    raise RuntimeError(
                        "shader face map contains {0} entries for {1} "
                        "polygons".format(
                            len(face_shader_indices),
                            polygon_count,
                        )
                    )
                target_index = target_indices[0]
                wrong_faces = [
                    index
                    for index, shader_index in enumerate(face_shader_indices)
                    if int(shader_index) != target_index
                ]
                if wrong_faces:
                    raise RuntimeError(
                        "{0} polygon faces are not assigned to expected depth "
                        "shadingEngine {1}; first faces: {2}".format(
                            len(wrong_faces),
                            expected_group,
                            ", ".join(str(index) for index in wrong_faces[:12]),
                        )
                    )
                report["verified_mesh_face_count"] += polygon_count
                report["verified_shape_path_count"] += 1
            except Exception as exc:
                failures.append("{0}: {1}".format(shape, exc))
            continue
        if shape_type == "nurbsSurface":
            report["nurbs_surface_path_count"] += 1
            try:
                connected_sets = cmds.listSets(
                    type=1,
                    object=shape,
                ) or []
                connected_sets = sorted(
                    set(_clean(item) for item in connected_sets if _clean(item))
                )
                if connected_sets != [expected_group]:
                    raise RuntimeError(
                        "expected only shadingEngine {0}; connected: {1}".format(
                            expected_group,
                            ", ".join(connected_sets) or "<none>"
                        )
                    )
                report["verified_shape_path_count"] += 1
            except Exception as exc:
                failures.append("{0}: {1}".format(shape, exc))
            continue
        failures.append(
            "{0}: unsupported depth shape type {1}".format(
                shape,
                shape_type or "<unknown>",
            )
        )

    if failures or report["verified_shape_path_count"] != report["shape_path_count"]:
        detail = " | ".join(failures[:20])
        if len(failures) > 20:
            detail += " | and {0} more".format(len(failures) - 20)
        raise RuntimeError(
            "Depth shader assignment verification failed for {0} of {1} "
            "surface paths: {2}".format(
                report["shape_path_count"]
                - report["verified_shape_path_count"],
                report["shape_path_count"],
                detail or "verified path count mismatch",
            )
        )
    return report


def _screen_space_pattern_shader(name, id_rgb):
    if not isinstance(id_rgb, tuple) or len(id_rgb) != 3:
        raise RuntimeError("Screen-space pattern ID must be a three-channel RGB tuple.")
    return _surface_shader(
        name + "_ScreenID",
        tuple(float(channel) / 255.0 for channel in id_rgb),
    )


def _marker_cutout_variant_group(
    marker_name,
    rgb,
    source_plug,
    shader_model,
    cache,
):
    key = (shader_model, marker_name, tuple(rgb), source_plug)
    if key in cache:
        return cache[key]
    variant_name = "{0}_Cutout_{1}".format(
        marker_name,
        _cutout_variant_token(source_plug),
    )
    if shader_model == "lambert":
        group = _lambert_shader(
            variant_name,
            rgb,
            fresh=True,
            transparency_source=source_plug,
        )
    elif shader_model == "surfaceShader":
        group = _surface_shader(
            variant_name,
            rgb,
            fresh=True,
            transparency_source=source_plug,
        )
    else:
        raise RuntimeError(
            "Unsupported temporary cutout shader model: {0}".format(shader_model)
        )
    cache[key] = group
    return group


def _assign_marker_group_preserving_cutouts(
    shapes,
    shared_group,
    marker_name,
    rgb,
    shader_model,
    job,
    variant_cache,
):
    snapshot = _ensure_authored_cutout_snapshot(job, shapes)
    opaque_shapes = []
    cutout_by_source = {}
    for shape in shapes:
        long_names = _long_names([shape])
        key = long_names[0] if long_names else shape
        record = snapshot.get(key) or {"alpha_driven": False}
        if not record.get("alpha_driven"):
            opaque_shapes.append(shape)
            continue
        source_plug = _clean(record.get("source_plug"))
        if not source_plug:
            raise RuntimeError(
                "Cutout shape has no captured outTransparency source: {0}".format(
                    shape
                )
            )
        cutout_by_source.setdefault(source_plug, []).append(shape)

    warnings = _assign(opaque_shapes, shared_group) if opaque_shapes else []
    cutout_failures = []
    verified_cutouts = []
    for source_plug in sorted(cutout_by_source):
        group = _marker_cutout_variant_group(
            marker_name,
            rgb,
            source_plug,
            shader_model,
            variant_cache,
        )
        source_shapes = sorted(cutout_by_source[source_plug])
        failures = _assign(source_shapes, group)
        if failures:
            cutout_failures.extend(failures)
        else:
            verified_cutouts.extend(source_shapes)
    if cutout_failures:
        raise RuntimeError(
            "Marker cutout shader assignment failed: {0}".format(
                " | ".join(cutout_failures[:20])
                + (
                    " | and {0} more".format(len(cutout_failures) - 20)
                    if len(cutout_failures) > 20
                    else ""
                )
            )
        )
    return warnings, opaque_shapes, verified_cutouts


def _apply_marker_shaders(bindings, job):
    warnings = []
    errors = []
    outline_mode = _character_outline_mode(job)
    screen_space_patterns = bool((job or {}).get("screen_space_patterns"))
    require_full_smooth_geometry = bool(
        (job or {}).get("require_full_smooth_geometry")
    )
    character_outline_shapes = []
    verified_cutout_shapes = []
    variant_cache = {}
    scoped_by_root = (
        (job or {}).get("_render_scope_binding_shapes")
        if isinstance((job or {}).get("_render_scope_binding_shapes"), dict)
        else {}
    )
    for record in bindings:
        color = record["color"]
        root = record["subject_root"]
        raw_shapes = _descendant_shapes(root)
        shapes = (
            list(scoped_by_root.get(root) or [])
            if root in scoped_by_root
            else _marker_renderable_shapes(raw_shapes)
        )
        if not shapes:
            if raw_shapes:
                warnings.append(
                    "Color Assignment target is authored-hidden or disabled by "
                    "the Picker eye and was omitted: {0}".format(root)
                )
                continue
            message = (
                "No renderable polygon mesh exists under {0}. A Bounding Box, "
                "GPU cache, stand-in, USD proxy, dummy primitive, or missing "
                "reference cannot be substituted for the required full-detail "
                "Maya geometry."
            ).format(root)
            if require_full_smooth_geometry:
                errors.append(message)
            else:
                warnings.append(message)
            continue
        rgb = MARKER_COLORS.get(color)
        pattern = MARKER_PATTERNS.get(color)
        if rgb is not None:
            marker_name = "HMB_" + _safe_token(color)
            marker_group = _lambert_shader(marker_name, rgb)
            marker_warnings, opaque_shapes, cutout_shapes = (
                _assign_marker_group_preserving_cutouts(
                    shapes,
                    marker_group,
                    marker_name,
                    rgb,
                    "lambert",
                    job,
                    variant_cache,
                )
            )
            warnings.extend(marker_warnings)
            verified_cutout_shapes.extend(cutout_shapes)
            if color in CHARACTER_MARKERS and outline_mode == CHARACTER_OUTLINE_PFX:
                # pfxToon outlines polygon card borders and does not follow the
                # authored texture alpha.  Opaque character surfaces retain the
                # explicit legacy outline; cutout cards retain alpha only.
                character_outline_shapes.extend(opaque_shapes)
        elif color in BACKGROUND_MARKERS and pattern:
            if not screen_space_patterns:
                errors.append(
                    "{0} requires the UV-independent screen-space postprocess "
                    "profile.".format(color)
                )
                continue
            id_rgb = MARKER_PATTERN_IDS.get(color)
            if id_rgb is None:
                errors.append(
                    "No screen-space categorical ID is registered for {0}.".format(
                        color
                    )
                )
                continue
            marker_group = _screen_space_pattern_shader(
                "HMB_" + _safe_token(color),
                id_rgb,
            )
            pattern_rgb = tuple(float(channel) / 255.0 for channel in id_rgb)
            marker_warnings, _opaque_shapes, cutout_shapes = (
                _assign_marker_group_preserving_cutouts(
                    shapes,
                    marker_group,
                    "HMB_" + _safe_token(color) + "_ScreenID",
                    pattern_rgb,
                    "surfaceShader",
                    job,
                    variant_cache,
                )
            )
            warnings.extend(marker_warnings)
            verified_cutout_shapes.extend(cutout_shapes)
        else:
            warnings.append("Unknown marker choice: {0}".format(color))
    if character_outline_shapes:
        warnings.extend(
            _character_out_rim(
                "HMB_Character",
                sorted(set(character_outline_shapes)),
            )
        )
    if errors:
        raise RuntimeError(" | ".join(errors))
    cutout_report = dict((job or {}).get("_authored_cutout_report") or {})
    cutout_report["verified_shape_path_count"] = len(set(verified_cutout_shapes))
    job["_marker_cutout_transparency"] = cutout_report
    return warnings


def _camera_shape(camera):
    shapes = cmds.listRelatives(
        camera,
        shapes=True,
        fullPath=True,
        type="camera",
    ) or []
    if shapes:
        return shapes[0]
    if cmds.nodeType(camera) == "camera":
        return camera
    raise RuntimeError("Depth playblast camera shape was not found: {0}".format(camera))


def _finite_depth_value(value):
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _depth_frustum_slopes(camera, width, height):
    """Return an output-aspect-aware conservative camera gate.

    Unsupported camera 2D transforms deliberately disable only the optional
    lateral filter.  Camera-space near/far interval collection remains valid.
    """
    try:
        camera_shape = _camera_shape(camera)
        output_width = float(width)
        output_height = float(height)
        if (
            not math.isfinite(output_width)
            or not math.isfinite(output_height)
            or output_width <= 0.0
            or output_height <= 0.0
        ):
            return None
        device_aspect = output_width / output_height
        for attribute in ("panZoomEnabled", "shakeEnabled"):
            try:
                if bool(cmds.getAttr(camera_shape + "." + attribute)):
                    return None
            except Exception:
                pass
        for attribute in (
            "horizontalFilmOffset",
            "verticalFilmOffset",
            "filmFitOffset",
            "filmRollValue",
            "filmTranslateH",
            "filmTranslateV",
        ):
            try:
                if abs(float(cmds.getAttr(camera_shape + "." + attribute))) > 1.0e-9:
                    return None
            except Exception:
                pass
        for attribute in ("preScale", "postScale"):
            try:
                if abs(float(cmds.getAttr(camera_shape + "." + attribute)) - 1.0) > 1.0e-9:
                    return None
            except Exception:
                pass

        expansion = 1.0
        for attribute in ("overscan", "lensSqueezeRatio", "cameraScale"):
            try:
                value = abs(float(cmds.getAttr(camera_shape + "." + attribute)))
            except Exception:
                value = 1.0
            if not math.isfinite(value) or value <= 0.0:
                return None
            expansion *= max(value, 1.0 / value)

        if bool(cmds.getAttr(camera_shape + ".orthographic")):
            orthographic_width = float(
                cmds.getAttr(camera_shape + ".orthographicWidth")
            )
            if not math.isfinite(orthographic_width) or orthographic_width <= 0.0:
                return None
            horizontal_extent = orthographic_width * 0.5 * expansion
            vertical_extent = horizontal_extent / device_aspect
            if horizontal_extent <= 0.0 or vertical_extent <= 0.0:
                return None
            return {
                "projection": "orthographic",
                "horizontal": horizontal_extent,
                "vertical": vertical_extent,
                "aspect_ratio": device_aspect,
                "policy": "orthographic_output_aspect_gate",
            }

        horizontal_aperture = float(
            cmds.getAttr(camera_shape + ".horizontalFilmAperture")
        )
        vertical_aperture = float(
            cmds.getAttr(camera_shape + ".verticalFilmAperture")
        )
        focal_length = float(cmds.getAttr(camera_shape + ".focalLength"))
        if (
            horizontal_aperture <= 0.0
            or vertical_aperture <= 0.0
            or focal_length <= 0.0
        ):
            return None

        # Maya film apertures are inches; focal length is millimetres. Use the
        # wider of horizontal-fit and vertical-fit so fill/overscan modes form
        # a conservative superset and visible geometry is never falsely cut.
        horizontal = horizontal_aperture * 25.4 * 0.5 / focal_length
        vertical = vertical_aperture * 25.4 * 0.5 / focal_length
        horizontal_slope = max(horizontal, vertical * device_aspect)
        vertical_slope = max(vertical, horizontal / device_aspect)
        horizontal_slope *= expansion
        vertical_slope *= expansion
        if horizontal_slope <= 0.0 or vertical_slope <= 0.0:
            return None
        return {
            "projection": "perspective",
            "horizontal": horizontal_slope,
            "vertical": vertical_slope,
            "aspect_ratio": device_aspect,
            "policy": "perspective_output_aspect_gate",
        }
    except Exception:
        # Animated or non-standard cameras still use correct near/far interval
        # intersection; only the optional lateral rejection is disabled.
        return None


def _camera_bbox_outside_frustum(camera_points, raw_near, clip_near, slopes):
    if not slopes:
        return False
    projection = _clean(slopes.get("projection")) or "perspective"
    horizontal = float(slopes["horizontal"])
    vertical = float(slopes["vertical"])
    if projection == "orthographic":
        xs = [float(point.x) for point in camera_points]
        ys = [float(point.y) for point in camera_points]
        if not xs or not ys or not all(
            math.isfinite(value) for value in xs + ys
        ):
            return False
        return (
            max(xs) < -horizontal
            or min(xs) > horizontal
            or max(ys) < -vertical
            or min(ys) > vertical
        )
    if raw_near <= clip_near:
        # A near-plane crossing can intersect a side plane between its original
        # corners, so retain it conservatively.
        return False
    projected = []
    for point in camera_points:
        depth = -float(point.z)
        if not math.isfinite(depth) or depth <= 0.0:
            return False
        projected.append((float(point.x) / depth, float(point.y) / depth))
    if not projected:
        return False
    xs = [item[0] for item in projected]
    ys = [item[1] for item in projected]
    return (
        max(xs) < -horizontal
        or min(xs) > horizontal
        or max(ys) < -vertical
        or min(ys) > vertical
    )


def _depth_even_sample_indices(count, limit):
    """Return deterministic, endpoint-inclusive indices with a hard cap."""
    count = max(0, int(count or 0))
    limit = max(0, int(limit or 0))
    if not count or not limit:
        return []
    if count <= limit:
        return list(range(count))
    if limit == 1:
        return [0]
    return sorted(set(
        int(round(float(index) * float(count - 1) / float(limit - 1)))
        for index in range(limit)
    ))


def _depth_screen_sample_evidence(
    record,
    camera_matrix,
    om,
    clip_near,
    clip_far,
    frustum_slopes,
    frame,
):
    """Prove whether deterministic mesh surface samples enter the raster.

    This evidence changes only the fixed normalization population.  Every
    render-scoped shape still receives and renders its Depth material.  When
    Maya cannot expose mesh topology samples, or the camera has an unsupported
    2D transform, the already-validated bbox/frustum result is retained as a
    conservative fallback and is reported truthfully.
    """
    fallback = {
        "normalization_eligible": True,
        "screen_sample_policy": "bbox_fallback_api_unavailable",
        "used_bbox_fallback": True,
        "requested_vertex_sample_count": 0,
        "requested_polygon_center_sample_count": 0,
        "evaluated_sample_count": 0,
        "clip_inside_sample_count": 0,
        "screen_inside_sample_count": 0,
        "screen_depth_near": None,
        "screen_depth_far": None,
    }
    if not isinstance(record, dict):
        return fallback
    if _clean(record.get("shape_type")) != "mesh":
        fallback["screen_sample_policy"] = "bbox_fallback_non_mesh_surface"
        return fallback
    mesh_function = record.get("mesh_function")
    vertex_indices = list(record.get("vertex_indices") or [])
    polygon_indices = list(record.get("polygon_indices") or [])
    if mesh_function is None or not hasattr(om, "MSpace"):
        return fallback
    if not frustum_slopes:
        fallback[
            "screen_sample_policy"
        ] = "bbox_fallback_unsupported_camera_screen_transform"
        return fallback
    fallback["requested_vertex_sample_count"] = len(vertex_indices)
    fallback["requested_polygon_center_sample_count"] = len(polygon_indices)
    try:
        points = mesh_function.getPoints(om.MSpace.kObject)
        world_matrix = record["dag_path"].inclusiveMatrix()
    except Exception:
        fallback["screen_sample_policy"] = "bbox_fallback_mesh_sample_api_error"
        return fallback
    local_samples = []
    point_count = len(points)
    for vertex_index in vertex_indices:
        if 0 <= int(vertex_index) < point_count:
            local_samples.append(points[int(vertex_index)])
    for polygon_index in polygon_indices:
        try:
            polygon_vertices = list(
                mesh_function.getPolygonVertices(int(polygon_index)) or []
            )
        except Exception:
            polygon_vertices = []
        polygon_points = [
            points[int(vertex_index)]
            for vertex_index in polygon_vertices
            if 0 <= int(vertex_index) < point_count
        ]
        if not polygon_points:
            continue
        inverse_count = 1.0 / float(len(polygon_points))
        local_samples.append(
            om.MPoint(
                sum(float(point.x) for point in polygon_points) * inverse_count,
                sum(float(point.y) for point in polygon_points) * inverse_count,
                sum(float(point.z) for point in polygon_points) * inverse_count,
                1.0,
            )
        )
    if not local_samples:
        fallback["screen_sample_policy"] = "bbox_fallback_empty_mesh_samples"
        return fallback

    projection = _clean(frustum_slopes.get("projection")) or "perspective"
    horizontal = float(frustum_slopes["horizontal"])
    vertical = float(frustum_slopes["vertical"])
    evaluated_count = 0
    clip_inside_count = 0
    screen_depths = []
    try:
        for local_point in local_samples:
            camera_point = (
                om.MPoint(
                    float(local_point.x),
                    float(local_point.y),
                    float(local_point.z),
                    1.0,
                )
                * world_matrix
                * camera_matrix
            )
            x_value = float(camera_point.x)
            y_value = float(camera_point.y)
            depth = -float(camera_point.z)
            if not all(math.isfinite(value) for value in (x_value, y_value, depth)):
                continue
            evaluated_count += 1
            if depth < float(clip_near) or depth > float(clip_far):
                continue
            clip_inside_count += 1
            if projection == "orthographic":
                inside = (
                    abs(x_value) <= horizontal
                    and abs(y_value) <= vertical
                )
            else:
                inside = (
                    depth > 0.0
                    and abs(x_value / depth) <= horizontal
                    and abs(y_value / depth) <= vertical
                )
            if inside:
                screen_depths.append(depth)
    except Exception:
        fallback["screen_sample_policy"] = "bbox_fallback_mesh_sample_transform_error"
        return fallback
    if not evaluated_count:
        fallback["screen_sample_policy"] = "bbox_fallback_no_finite_mesh_samples"
        return fallback
    return {
        "normalization_eligible": bool(screen_depths),
        "screen_sample_policy": (
            "api_mesh_vertex_polygon_center_screen_visible"
            if screen_depths
            else "api_mesh_vertex_polygon_center_screen_rejected"
        ),
        "used_bbox_fallback": False,
        "requested_vertex_sample_count": len(vertex_indices),
        "requested_polygon_center_sample_count": len(polygon_indices),
        "evaluated_sample_count": evaluated_count,
        "clip_inside_sample_count": clip_inside_count,
        "screen_inside_sample_count": len(screen_depths),
        "screen_depth_near": min(screen_depths) if screen_depths else None,
        "screen_depth_far": max(screen_depths) if screen_depths else None,
        "frame": frame,
    }


def _prepare_depth_api_records(shapes, om):
    """Resolve reusable API 2.0 DAG objects for all depth surface instances."""
    required = ("MSelectionList", "MFnDagNode", "MPoint")
    if not all(hasattr(om, name) for name in required):
        return None
    records = []
    for shape in shapes or []:
        try:
            selection = om.MSelectionList()
            selection.add(shape)
            dag_path = selection.getDagPath(0)
            function = om.MFnDagNode(dag_path)
        except Exception as exc:
            raise RuntimeError(
                "Depth playblast could not prepare Maya API geometry for {0}: "
                "{1}".format(shape, exc)
            )
        mesh_function = None
        vertex_indices = []
        polygon_indices = []
        try:
            shape_type = _clean(cmds.nodeType(shape))
        except Exception:
            shape_type = ""
        if shape_type == "mesh" and hasattr(om, "MFnMesh"):
            try:
                mesh_function = om.MFnMesh(dag_path)
                vertex_count = int(mesh_function.numVertices)
                polygon_count = int(mesh_function.numPolygons)
                vertex_indices = _depth_even_sample_indices(
                    vertex_count,
                    DEPTH_SCREEN_VERTEX_SAMPLE_LIMIT,
                )
                polygon_indices = _depth_even_sample_indices(
                    polygon_count,
                    DEPTH_SCREEN_POLYGON_CENTER_SAMPLE_LIMIT,
                )
            except Exception:
                # The bbox evaluator remains valid when a stripped Maya API,
                # unusual mesh wrapper, or regression harness cannot expose
                # deterministic topology samples.  That path is reported as
                # a conservative normalization fallback instead of silently
                # claiming screen-visible evidence.
                mesh_function = None
                vertex_indices = []
                polygon_indices = []
        records.append({
            "shape": shape,
            "dag_path": dag_path,
            "function": function,
            "shape_type": shape_type,
            "mesh_function": mesh_function,
            "vertex_indices": vertex_indices,
            "polygon_indices": polygon_indices,
        })
    return records


def _depth_api_camera_points(record, camera_matrix, om, frame):
    """Return eight camera-space local-bbox corners, or None when hidden."""
    dag_path = record["dag_path"]
    visible = getattr(dag_path, "isVisible", None)
    if visible is not None:
        try:
            visible_value = visible() if callable(visible) else visible
            if not bool(visible_value):
                return None
        except Exception as exc:
            raise RuntimeError(
                "Depth playblast could not evaluate API visibility for {0} at "
                "frame {1}: {2}".format(record["shape"], frame, exc)
            )
    templated = getattr(dag_path, "isTemplated", None)
    if templated is not None:
        try:
            templated_value = templated() if callable(templated) else templated
            if bool(templated_value):
                return None
        except Exception as exc:
            raise RuntimeError(
                "Depth playblast could not evaluate API template state for {0} "
                "at frame {1}: {2}".format(record["shape"], frame, exc)
            )
    try:
        bounds = record["function"].boundingBox
        if callable(bounds):
            bounds = bounds()
        minimum = bounds.min
        maximum = bounds.max
        if callable(minimum):
            minimum = minimum()
        if callable(maximum):
            maximum = maximum()
        local_values = (
            float(minimum.x),
            float(minimum.y),
            float(minimum.z),
            float(maximum.x),
            float(maximum.y),
            float(maximum.z),
        )
        world_matrix = dag_path.inclusiveMatrix()
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not evaluate Maya API bounds for {0} at "
            "frame {1}: {2}".format(record["shape"], frame, exc)
        )
    if not all(math.isfinite(value) for value in local_values):
        raise RuntimeError(
            "Depth playblast received non-finite Maya API bounds for {0} at "
            "frame {1}.".format(record["shape"], frame)
        )
    xs = (local_values[0], local_values[3])
    ys = (local_values[1], local_values[4])
    zs = (local_values[2], local_values[5])
    camera_points = []
    try:
        for x_value in xs:
            for y_value in ys:
                for z_value in zs:
                    camera_points.append(
                        om.MPoint(x_value, y_value, z_value, 1.0)
                        * world_matrix
                        * camera_matrix
                    )
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not transform Maya API bounds for {0} at "
            "frame {1}: {2}".format(record["shape"], frame, exc)
        )
    return camera_points


def _sampled_shot_depth_range(
    camera,
    frame_values,
    width,
    height,
    job=None,
):
    """Evaluate one fixed range across every requested output frame."""
    values = list(frame_values or [])
    if not values:
        raise RuntimeError(
            "Depth playblast range evaluation received no output frames."
        )
    _assert_depth_drawables_supported(camera)
    shapes = _all_depth_renderable_shapes(job)
    shape_type_counts = _depth_shape_type_counts(shapes)
    shape_roles = (
        dict((job or {}).get("_depth_range_shape_roles") or {})
        if isinstance(job, dict)
        else {}
    )
    foreground_shape_set = set(
        _clean(item)
        for item in (
            (job or {}).get("_depth_foreground_shapes")
            if isinstance(job, dict)
            else []
        ) or []
        if _clean(item)
    )

    try:
        from maya.api import OpenMaya as om
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast requires Maya API camera-space matrix support: "
            "{0}".format(exc)
        )
    api_records = _prepare_depth_api_records(shapes, om)
    evaluation_backend = (
        "maya_api_2_dag_bounds"
        if api_records is not None
        else "cmds_exact_world_bounding_box_fallback"
    )

    camera_shape = _camera_shape(camera)
    camera_transform = camera
    try:
        if cmds.nodeType(camera_transform) == "camera":
            parents = cmds.listRelatives(
                camera_transform,
                parent=True,
                fullPath=True,
            ) or []
            if parents:
                camera_transform = parents[0]
    except Exception:
        pass

    original_frame = None
    clipped_intervals = []
    representative_depths = []
    foreground_representative_depths = []
    context_representative_depths = []
    representative_records = []
    representatives_by_shape = {}
    binding_range_accumulators = {}
    screen_rejected_representative_count = 0
    role_excluded_representative_count = 0
    screen_sample_tested_bbox_count = 0
    screen_sample_visible_bbox_count = 0
    screen_sample_rejected_bbox_count = 0
    bbox_fallback_candidate_count = 0
    screen_sample_evaluated_count = 0
    screen_inside_sample_count = 0
    considered_bbox_count = 0
    intersected_bbox_count = 0
    clip_rejected_bbox_count = 0
    frustum_rejected_bbox_count = 0
    visibility_rejected_bbox_count = 0
    invalid_bbox_count = 0
    frames_with_intersections = 0
    frame_reports = []
    near_clip_values = []
    far_clip_values = []
    try:
        original_frame = cmds.currentTime(query=True)
    except Exception:
        original_frame = None
    _write_progress(
        job,
        "analyzing_depth_range",
        "Analyzing camera-space depth range across {0} output frame(s).".format(
            len(values)
        ),
        frame_count=len(values),
        completed_frames=0,
        depth_range_backend=evaluation_backend,
    )
    try:
        for frame_index, frame in enumerate(values):
            cmds.currentTime(frame, edit=True, update=True)
            try:
                clip_near = float(
                    cmds.getAttr(camera_shape + ".nearClipPlane")
                )
                clip_far = float(
                    cmds.getAttr(camera_shape + ".farClipPlane")
                )
            except Exception as exc:
                raise RuntimeError(
                    "Depth playblast could not read camera clipping planes at "
                    "frame {0}: {1}".format(frame, exc)
                )
            if (
                not math.isfinite(clip_near)
                or not math.isfinite(clip_far)
                or clip_near <= 0.0
                or clip_far <= clip_near
            ):
                raise RuntimeError(
                    "Depth playblast camera clipping range is invalid at frame "
                    "{0}: near={1}, far={2}.".format(
                        frame,
                        clip_near,
                        clip_far,
                    )
                )
            near_clip_values.append(clip_near)
            far_clip_values.append(clip_far)
            try:
                raw_matrix = cmds.getAttr(
                    camera_transform + ".worldInverseMatrix[0]"
                )
            except Exception as exc:
                raise RuntimeError(
                    "Depth playblast could not evaluate the camera matrix at "
                    "frame {0}: {1}".format(frame, exc)
                )
            if (
                isinstance(raw_matrix, (list, tuple))
                and len(raw_matrix) == 1
                and isinstance(raw_matrix[0], (list, tuple))
            ):
                raw_matrix = raw_matrix[0]
            try:
                matrix = om.MMatrix(raw_matrix)
            except Exception as exc:
                raise RuntimeError(
                    "Depth playblast camera matrix is invalid at frame {0}: "
                    "{1}".format(frame, exc)
                )
            frustum_slopes = _depth_frustum_slopes(
                camera,
                width,
                height,
            )
            frame_considered = 0
            frame_intersected = 0
            frame_rejected = 0
            frame_intervals = []
            frame_representative_depths = []
            frame_foreground_depths = []
            frame_context_depths = []
            frame_screen_sample_tested = 0
            frame_screen_sample_visible = 0
            frame_screen_sample_rejected = 0
            frame_bbox_fallback_candidates = 0
            frame_role_excluded_candidates = 0
            for shape_index, shape in enumerate(shapes):
                considered_bbox_count += 1
                frame_considered += 1
                if api_records is not None:
                    camera_points = _depth_api_camera_points(
                        api_records[shape_index],
                        matrix,
                        om,
                        frame,
                    )
                    if camera_points is None:
                        visibility_rejected_bbox_count += 1
                        frame_rejected += 1
                        continue
                else:
                    # Compatibility fallback for stripped-down Maya API builds
                    # and the pure-Python regression harness only.
                    if not _motion_path_visible(shape):
                        visibility_rejected_bbox_count += 1
                        frame_rejected += 1
                        continue
                    try:
                        bounds = cmds.exactWorldBoundingBox(
                            shape,
                            ignoreInvisible=True,
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            "Depth playblast could not evaluate the world bounds "
                            "for {0} at frame {1}: {2}".format(
                                shape,
                                frame,
                                exc,
                            )
                        )
                    if not isinstance(bounds, (list, tuple)) or len(bounds) != 6:
                        invalid_bbox_count += 1
                        raise RuntimeError(
                            "Depth playblast received invalid world bounds for "
                            "{0} at frame {1}: {2!r}.".format(
                                shape,
                                frame,
                                bounds,
                            )
                        )
                    try:
                        bound_values = [float(value) for value in bounds]
                    except Exception as exc:
                        invalid_bbox_count += 1
                        raise RuntimeError(
                            "Depth playblast received non-numeric world bounds "
                            "for {0} at frame {1}: {2}".format(
                                shape,
                                frame,
                                exc,
                            )
                        )
                    if not all(
                        math.isfinite(value) for value in bound_values
                    ):
                        invalid_bbox_count += 1
                        raise RuntimeError(
                            "Depth playblast received non-finite world bounds "
                            "for {0} at frame {1}.".format(shape, frame)
                        )
                    xs = (bound_values[0], bound_values[3])
                    ys = (bound_values[1], bound_values[4])
                    zs = (bound_values[2], bound_values[5])
                    camera_points = []
                    for x_value in xs:
                        for y_value in ys:
                            for z_value in zs:
                                camera_points.append(
                                    om.MPoint(x_value, y_value, z_value, 1.0)
                                    * matrix
                                )
                raw_depths = []
                for camera_point in camera_points:
                    depth = -float(camera_point.z)
                    if math.isfinite(depth):
                        raw_depths.append(depth)
                if not raw_depths:
                    invalid_bbox_count += 1
                    raise RuntimeError(
                        "Depth playblast could not derive camera-space bounds "
                        "for {0} at frame {1}.".format(shape, frame)
                    )

                # Preserve the raw interval before clipping. If the bbox spans
                # the near plane, the intersection must include clip_near; an
                # individual-corner filter incorrectly kept only its far face.
                raw_near = min(raw_depths)
                raw_far = max(raw_depths)
                clipped_near = max(float(clip_near), raw_near)
                clipped_far = min(float(clip_far), raw_far)
                if clipped_far < clipped_near:
                    clip_rejected_bbox_count += 1
                    frame_rejected += 1
                    continue
                if _camera_bbox_outside_frustum(
                    camera_points,
                    raw_near,
                    clip_near,
                    frustum_slopes,
                ):
                    frustum_rejected_bbox_count += 1
                    frame_rejected += 1
                    continue
                clipped_intervals.append((clipped_near, clipped_far))
                frame_intervals.append((clipped_near, clipped_far))
                positive_depths = [
                    depth for depth in raw_depths if depth > 0.0
                ]
                representative_depth = (
                    _depth_median(positive_depths)
                    if positive_depths
                    else (raw_near + raw_far) * 0.5
                )
                # The same representative-depth definition drives both the
                # complete-sequence range and the per-frame shader bucket.  A
                # bbox crossing a clip plane therefore cannot stretch the
                # entire sequence merely through one extreme corner.
                representative_depth = min(
                    clipped_far,
                    max(clipped_near, representative_depth),
                )
                representative_depths.append(representative_depth)
                frame_representative_depths.append(representative_depth)
                role_record = shape_roles.get(shape) or {}
                role = (
                    "foreground"
                    if shape in foreground_shape_set
                    or _clean(role_record.get("role")) == "foreground"
                    else "context"
                )
                root = _clean(role_record.get("root"))
                marker = _clean(role_record.get("marker"))
                api_record = (
                    api_records[shape_index]
                    if api_records is not None
                    else None
                )
                if role != "foreground" and foreground_shape_set:
                    # Actor markers have first authority for the effective
                    # range.  Context stays fully shaded/rendered/audited but
                    # does not pay per-frame vertex sampling cost when it
                    # cannot enter the normalization population.
                    screen_evidence = {
                        "normalization_eligible": False,
                        "screen_sample_policy": (
                            "context_not_sampled_foreground_priority"
                        ),
                        "used_bbox_fallback": False,
                        "excluded_by_role": True,
                        "requested_vertex_sample_count": 0,
                        "requested_polygon_center_sample_count": 0,
                        "evaluated_sample_count": 0,
                        "clip_inside_sample_count": 0,
                        "screen_inside_sample_count": 0,
                        "screen_depth_near": None,
                        "screen_depth_far": None,
                    }
                else:
                    screen_evidence = _depth_screen_sample_evidence(
                        api_record,
                        matrix,
                        om,
                        clip_near,
                        clip_far,
                        frustum_slopes,
                        frame,
                    )
                normalization_eligible = bool(
                    screen_evidence.get("normalization_eligible")
                )
                sample_evaluated = int(
                    screen_evidence.get("evaluated_sample_count") or 0
                )
                sample_inside = int(
                    screen_evidence.get("screen_inside_sample_count") or 0
                )
                screen_sample_evaluated_count += sample_evaluated
                screen_inside_sample_count += sample_inside
                if screen_evidence.get("excluded_by_role"):
                    role_excluded_representative_count += 1
                    frame_role_excluded_candidates += 1
                elif screen_evidence.get("used_bbox_fallback"):
                    bbox_fallback_candidate_count += 1
                    frame_bbox_fallback_candidates += 1
                else:
                    screen_sample_tested_bbox_count += 1
                    frame_screen_sample_tested += 1
                    if normalization_eligible:
                        screen_sample_visible_bbox_count += 1
                        frame_screen_sample_visible += 1
                    else:
                        screen_sample_rejected_bbox_count += 1
                        frame_screen_sample_rejected += 1
                if normalization_eligible:
                    if role == "foreground":
                        foreground_representative_depths.append(
                            representative_depth
                        )
                        frame_foreground_depths.append(representative_depth)
                    else:
                        context_representative_depths.append(
                            representative_depth
                        )
                        frame_context_depths.append(representative_depth)
                    representatives_by_shape.setdefault(shape, []).append(
                        representative_depth
                    )
                elif not screen_evidence.get("excluded_by_role"):
                    screen_rejected_representative_count += 1
                representative_records.append({
                    "depth": representative_depth,
                    "frame": frame,
                    "shape": shape,
                    "root": root,
                    "marker": marker,
                    "role": role,
                    "normalization_eligible": normalization_eligible,
                    "screen_evidence": screen_evidence,
                })
                binding_key = (root, marker, role)
                binding_accumulator = binding_range_accumulators.setdefault(
                    binding_key,
                    {
                        "root": root,
                        "marker": marker,
                        "role": role,
                        "shape_paths": set(),
                        "depths": [],
                        "normalization_depths": [],
                        "screen_tested_shape_paths": set(),
                        "screen_visible_shape_paths": set(),
                        "screen_rejected_shape_paths": set(),
                        "bbox_fallback_shape_paths": set(),
                        "role_excluded_shape_paths": set(),
                        "screen_sample_count": 0,
                        "screen_visible_sample_count": 0,
                        "screen_policy_counts": {},
                    },
                )
                binding_accumulator["shape_paths"].add(shape)
                binding_accumulator["depths"].append(representative_depth)
                if normalization_eligible:
                    binding_accumulator["normalization_depths"].append(
                        representative_depth
                    )
                policy = _clean(screen_evidence.get("screen_sample_policy"))
                policy_counts = binding_accumulator["screen_policy_counts"]
                policy_counts[policy] = int(policy_counts.get(policy) or 0) + 1
                binding_accumulator["screen_sample_count"] += sample_evaluated
                binding_accumulator[
                    "screen_visible_sample_count"
                ] += sample_inside
                if screen_evidence.get("excluded_by_role"):
                    binding_accumulator["role_excluded_shape_paths"].add(shape)
                elif screen_evidence.get("used_bbox_fallback"):
                    binding_accumulator["bbox_fallback_shape_paths"].add(shape)
                else:
                    binding_accumulator["screen_tested_shape_paths"].add(shape)
                    if normalization_eligible:
                        binding_accumulator[
                            "screen_visible_shape_paths"
                        ].add(shape)
                    else:
                        binding_accumulator[
                            "screen_rejected_shape_paths"
                        ].add(shape)
                intersected_bbox_count += 1
                frame_intersected += 1
            if frame_intervals:
                frames_with_intersections += 1
            frame_reports.append({
                "frame": frame,
                "camera_near_clip": clip_near,
                "camera_far_clip": clip_far,
                "considered_bbox_count": frame_considered,
                "intersected_bbox_count": frame_intersected,
                "rejected_bbox_count": frame_rejected,
                "near": (
                    min(item[0] for item in frame_intervals)
                    if frame_intervals
                    else None
                ),
                "far": (
                    max(item[1] for item in frame_intervals)
                    if frame_intervals
                    else None
                ),
                "representative_near": (
                    min(frame_representative_depths)
                    if frame_representative_depths
                    else None
                ),
                "representative_far": (
                    max(frame_representative_depths)
                    if frame_representative_depths
                    else None
                ),
                "foreground_intersected_bbox_count": len(
                    frame_foreground_depths
                ),
                "context_intersected_bbox_count": len(frame_context_depths),
                "foreground_representative_near": (
                    min(frame_foreground_depths)
                    if frame_foreground_depths
                    else None
                ),
                "foreground_representative_far": (
                    max(frame_foreground_depths)
                    if frame_foreground_depths
                    else None
                ),
                "screen_sample_tested_bbox_count": frame_screen_sample_tested,
                "screen_sample_visible_bbox_count": frame_screen_sample_visible,
                "screen_sample_rejected_bbox_count": frame_screen_sample_rejected,
                "bbox_fallback_candidate_count": frame_bbox_fallback_candidates,
                "role_excluded_bbox_count": frame_role_excluded_candidates,
                "frustum_filter": (
                    frustum_slopes.get("policy")
                    if frustum_slopes
                    else "depth_clip_only"
                ),
            })
            _write_progress(
                job,
                "analyzing_depth_range",
                "Analyzed depth range frame {0} of {1} (Maya frame {2}).".format(
                    frame_index + 1,
                    len(values),
                    frame,
                ),
                frame_status="completed",
                frame_index=frame_index + 1,
                completed_frames=frame_index + 1,
                frame_count=len(values),
                maya_frame=frame,
                depth_range_backend=evaluation_backend,
            )
    finally:
        if original_frame is not None:
            try:
                cmds.currentTime(original_frame, edit=True)
            except Exception:
                pass
    camera_near_clip_min = min(near_clip_values)
    camera_near_clip_max = max(near_clip_values)
    camera_far_clip_min = min(far_clip_values)
    camera_far_clip_max = max(far_clip_values)
    binding_range_reports = []
    for binding_key in sorted(binding_range_accumulators):
        accumulator = binding_range_accumulators[binding_key]
        depths = accumulator["depths"]
        normalization_depths = accumulator["normalization_depths"]
        binding_range_reports.append({
            "root": accumulator["root"],
            "marker": accumulator["marker"],
            "role": accumulator["role"],
            "shape_path_count": len(accumulator["shape_paths"]),
            "representative_sample_count": len(depths),
            "representative_near": min(depths) if depths else None,
            "representative_far": max(depths) if depths else None,
            "normalization_candidate_sample_count": len(
                normalization_depths
            ),
            "normalization_candidate_near": (
                min(normalization_depths) if normalization_depths else None
            ),
            "normalization_candidate_far": (
                max(normalization_depths) if normalization_depths else None
            ),
            "screen_tested_shape_path_count": len(
                accumulator["screen_tested_shape_paths"]
            ),
            "screen_visible_shape_path_count": len(
                accumulator["screen_visible_shape_paths"]
            ),
            "screen_rejected_shape_path_count": len(
                accumulator["screen_rejected_shape_paths"]
            ),
            "bbox_fallback_shape_path_count": len(
                accumulator["bbox_fallback_shape_paths"]
            ),
            "role_excluded_shape_path_count": len(
                accumulator["role_excluded_shape_paths"]
            ),
            "screen_sample_count": accumulator["screen_sample_count"],
            "screen_visible_sample_count": accumulator[
                "screen_visible_sample_count"
            ],
            "screen_sample_policy_counts": dict(sorted(
                accumulator["screen_policy_counts"].items()
            )),
            "selected_for_normalization": False,
        })
    report = {
        "evaluation_scope": "complete_requested_sequence",
        "evaluation_backend": evaluation_backend,
        "evaluated_frames": values,
        "evaluated_frame_count": len(values),
        # Legacy field names remain truthful: every output frame is sampled.
        "sample_frames": values,
        "sample_count": len(values),
        "frames_with_intersections": frames_with_intersections,
        "considered_bbox_count": considered_bbox_count,
        "intersected_sample_count": len(clipped_intervals),
        "intersected_interval_count": len(clipped_intervals),
        "representative_sample_count": len(representative_depths),
        "foreground_representative_sample_count": len(
            foreground_representative_depths
        ),
        "context_representative_sample_count": len(
            context_representative_depths
        ),
        "screen_rejected_representative_sample_count": (
            screen_rejected_representative_count
        ),
        "role_excluded_representative_sample_count": (
            role_excluded_representative_count
        ),
        "normalization_candidate_shape_path_count": len(
            representatives_by_shape
        ),
        "foreground_candidate_shape_path_count": len(set(
            record["shape"]
            for record in representative_records
            if record["role"] == "foreground"
            and record.get("normalization_eligible")
        )),
        "screen_rejected_shape_path_count": len(set(
            record["shape"]
            for record in representative_records
            if not record.get("normalization_eligible")
            and not record["screen_evidence"].get("excluded_by_role")
        )),
        "role_excluded_shape_path_count": len(set(
            record["shape"]
            for record in representative_records
            if record["screen_evidence"].get("excluded_by_role")
        )),
        "screen_sample_tested_bbox_count": screen_sample_tested_bbox_count,
        "screen_sample_visible_bbox_count": screen_sample_visible_bbox_count,
        "screen_sample_rejected_bbox_count": screen_sample_rejected_bbox_count,
        "bbox_fallback_candidate_count": bbox_fallback_candidate_count,
        "screen_sample_evaluated_count": screen_sample_evaluated_count,
        "screen_inside_sample_count": screen_inside_sample_count,
        "screen_sample_policy": (
            "deterministic_api_mesh_vertices_and_polygon_centers;"
            "bbox_fallback_when_sampling_unavailable"
        ),
        "rejection_accounting_policy": DEPTH_REJECTION_ACCOUNTING_POLICY,
        "screen_vertex_sample_limit": DEPTH_SCREEN_VERTEX_SAMPLE_LIMIT,
        "screen_polygon_center_sample_limit": (
            DEPTH_SCREEN_POLYGON_CENTER_SAMPLE_LIMIT
        ),
        "foreground_shape_path_count": len(set(
            record["shape"]
            for record in representative_records
            if record["role"] == "foreground"
        )),
        "context_shape_path_count": len(set(
            record["shape"]
            for record in representative_records
            if record["role"] != "foreground"
        )),
        "foreground_binding_count": len(set(
            record["root"]
            for record in representative_records
            if record["role"] == "foreground" and record["root"]
        )),
        "binding_range_reports": binding_range_reports,
        "intersected_bbox_count": intersected_bbox_count,
        "rejected_bbox_count": (
            clip_rejected_bbox_count
            + frustum_rejected_bbox_count
            + visibility_rejected_bbox_count
            + invalid_bbox_count
        ),
        "clip_rejected_bbox_count": clip_rejected_bbox_count,
        "frustum_rejected_bbox_count": frustum_rejected_bbox_count,
        "visibility_rejected_bbox_count": visibility_rejected_bbox_count,
        "invalid_bbox_count": invalid_bbox_count,
        "frame_reports": frame_reports,
        "renderable_shape_count": len(shapes),
        "mesh_shape_count": int(shape_type_counts.get("mesh") or 0),
        "nurbs_surface_shape_count": int(
            shape_type_counts.get("nurbsSurface") or 0
        ),
        "other_shape_count": int(shape_type_counts.get("other") or 0),
        "camera_near_clip_min": camera_near_clip_min,
        "camera_near_clip_max": camera_near_clip_max,
        "camera_far_clip_min": camera_far_clip_min,
        "camera_far_clip_max": camera_far_clip_max,
        "camera_clip_animated": (
            abs(camera_near_clip_max - camera_near_clip_min) > 1.0e-9
            or abs(camera_far_clip_max - camera_far_clip_min) > 1.0e-9
        ),
        "padding_fraction": DEPTH_RANGE_PADDING_FRACTION,
        "camera_origin_distance": 0.0,
        "camera_clip_is_hard_safety_boundary": True,
        "foreground_near_percentile": DEPTH_FOREGROUND_NEAR_PERCENTILE,
        "foreground_far_percentile": DEPTH_FOREGROUND_FAR_PERCENTILE,
        "generic_far_percentile": DEPTH_GENERIC_FAR_PERCENTILE,
        "generic_percentile_min_shapes": DEPTH_GENERIC_PERCENTILE_MIN_SHAPES,
    }
    if not representative_depths:
        return report
    normalization_representative_depths = (
        foreground_representative_depths + context_representative_depths
    )
    if not normalization_representative_depths:
        report["range_candidate_scope"] = "no_screen_valid_shape_candidates"
        report["range_basis"] = "camera_clip_planes_no_screen_valid_candidates"
        report["near_anchor"] = "camera_clip_plane_fallback"
        report["fallback_percentile"] = None
        report["fallback_reason"] = "all_api_mesh_screen_samples_rejected"
        report["range_extrema_sources"] = {}
        return report
    if foreground_representative_depths:
        range_candidates = foreground_representative_depths
        minimum = _depth_percentile(
            range_candidates,
            DEPTH_FOREGROUND_NEAR_PERCENTILE,
        )
        maximum = _depth_percentile(
            range_candidates,
            DEPTH_FOREGROUND_FAR_PERCENTILE,
        )
        range_candidate_scope = "screen_valid_foreground_actor_shapes"
        range_basis = (
            "complete_sequence_screen_valid_foreground_representative_percentiles"
        )
        fallback_percentile = None
        fallback_reason = ""
    elif len(representatives_by_shape) >= DEPTH_GENERIC_PERCENTILE_MIN_SHAPES:
        shape_near_values = [
            min(depths) for depths in representatives_by_shape.values()
            if depths
        ]
        shape_far_values = [
            max(depths) for depths in representatives_by_shape.values()
            if depths
        ]
        minimum = _depth_percentile(
            shape_near_values,
            1.0 - DEPTH_GENERIC_FAR_PERCENTILE,
        )
        maximum = _depth_percentile(
            shape_far_values,
            DEPTH_GENERIC_FAR_PERCENTILE,
        )
        range_candidates = normalization_representative_depths
        range_candidate_scope = "screen_valid_shapes_generic_robust_fallback"
        range_basis = (
            "complete_sequence_screen_valid_shape_temporal_extrema_percentiles"
        )
        fallback_percentile = DEPTH_GENERIC_FAR_PERCENTILE
        fallback_reason = "no_foreground_marker_samples"
    else:
        range_candidates = normalization_representative_depths
        minimum = min(range_candidates)
        maximum = max(range_candidates)
        range_candidate_scope = "screen_valid_shapes_small_scene_fallback"
        range_basis = (
            "complete_sequence_screen_valid_shape_representative_extrema_fallback"
        )
        fallback_percentile = None
        fallback_reason = "no_foreground_marker_samples_and_small_shape_count"
    padding = (maximum - minimum) * DEPTH_RANGE_PADDING_FRACTION
    sampled_near = max(camera_near_clip_min, minimum - padding)
    sampled_far = min(camera_far_clip_max, maximum + padding)
    if sampled_far <= sampled_near:
        # One flat/single-object representative cannot define a distance span.
        # Add only a deterministic numerical guard; do not fall back to the
        # much wider camera clip range and wash out the usable object value.
        guard_span = max(abs(minimum) * 0.02, 0.01)
        sampled_near = max(
            camera_near_clip_min,
            minimum - guard_span * 0.5,
        )
        sampled_far = min(
            camera_far_clip_max,
            maximum + guard_span * 0.5,
        )
    if sampled_far <= sampled_near:
        raise RuntimeError(
            "Depth playblast complete-sequence bounds collapsed to an invalid "
            "range: near={0}, far={1}.".format(sampled_near, sampled_far)
        )
    report["near"] = sampled_near
    report["far"] = sampled_far
    report["range_candidate_scope"] = range_candidate_scope
    report["range_basis"] = range_basis
    report["near_anchor"] = (
        "effective_screen_valid_foreground_near"
        if foreground_representative_depths
        else "effective_screen_valid_shape_near"
    )
    report["fallback_percentile"] = fallback_percentile
    report["fallback_reason"] = fallback_reason
    for binding_report in binding_range_reports:
        binding_report["selected_for_normalization"] = bool(
            int(binding_report["normalization_candidate_sample_count"]) > 0
            and (
                binding_report["role"] == "foreground"
                if foreground_representative_depths
                else True
            )
        )
    candidate_records = [
        record
        for record in representative_records
        if record.get("normalization_eligible")
        and (
            record["role"] == "foreground"
            if foreground_representative_depths
            else True
        )
    ]
    extrema_sources = {}
    for label, value in (("near", sampled_near), ("far", sampled_far)):
        if not candidate_records:
            continue
        closest = min(
            candidate_records,
            key=lambda record: abs(float(record["depth"]) - float(value)),
        )
        extrema_sources[label] = {
            "frame": closest["frame"],
            "shape": closest["shape"],
            "root": closest["root"],
            "marker": closest["marker"],
            "role": closest["role"],
            "representative_depth": closest["depth"],
            "screen_sample_policy": _clean(
                closest["screen_evidence"].get("screen_sample_policy")
            ),
            "used_bbox_fallback": bool(
                closest["screen_evidence"].get("used_bbox_fallback")
            ),
            "screen_inside_sample_count": int(
                closest["screen_evidence"].get("screen_inside_sample_count")
                or 0
            ),
        }
    report["range_extrema_sources"] = extrema_sources
    return report


def _depth_range(camera, job, frame_values=None, width=None, height=None):
    """Return one fixed camera-space range for the complete depth sequence."""
    requested_profile = _clean((job or {}).get("depth_profile"))
    if requested_profile and requested_profile != DEPTH_PLAYBLAST_PROFILE:
        raise RuntimeError(
            "Unsupported depth playblast profile: {0}".format(requested_profile)
        )

    _assert_depth_drawables_supported(camera)
    camera_shape = _camera_shape(camera)
    frame_values = list(frame_values or [])
    output_width = int(width or (job or {}).get("width") or 1280)
    output_height = int(height or (job or {}).get("height") or 720)
    if output_width <= 0 or output_height <= 0:
        raise RuntimeError(
            "Depth playblast output size must be positive: {0}x{1}.".format(
                output_width,
                output_height,
            )
        )

    sampled_range = {}
    if frame_values:
        sampled_range = _sampled_shot_depth_range(
            camera,
            frame_values,
            output_width,
            output_height,
            job=job,
        )
        clip_near = float(sampled_range["camera_near_clip_min"])
        clip_near_max = float(sampled_range["camera_near_clip_max"])
        clip_far_min = float(sampled_range["camera_far_clip_min"])
        clip_far = float(sampled_range["camera_far_clip_max"])
    else:
        try:
            clip_near = float(cmds.getAttr(camera_shape + ".nearClipPlane"))
            clip_far = float(cmds.getAttr(camera_shape + ".farClipPlane"))
        except Exception as exc:
            raise RuntimeError(
                "Depth playblast could not read camera clipping planes: {0}".format(
                    exc
                )
            )
        clip_near_max = clip_near
        clip_far_min = clip_far
        if (
            not math.isfinite(clip_near)
            or not math.isfinite(clip_far)
            or clip_near <= 0.0
            or clip_far <= clip_near
        ):
            raise RuntimeError(
                "Depth playblast camera clipping range is invalid: near={0}, "
                "far={1}.".format(clip_near, clip_far)
            )

    requested_near = _finite_depth_value((job or {}).get("depth_near"))
    requested_far = _finite_depth_value((job or {}).get("depth_far"))
    if (requested_near is None) != (requested_far is None):
        raise RuntimeError(
            "Depth playblast requires both depth_near and depth_far when either is supplied."
        )
    if (
        requested_near is None
        and sampled_range
        and sampled_range.get("near") is not None
        and sampled_range.get("far") is not None
    ):
        depth_near = float(sampled_range["near"])
        depth_far = float(sampled_range["far"])
        if sampled_range.get("foreground_representative_sample_count"):
            policy = "screen_valid_foreground_percentile_bounds"
        elif sampled_range.get("fallback_percentile") is not None:
            policy = "screen_valid_shape_robust_fallback_bounds"
        else:
            policy = "screen_valid_shape_extrema_fallback_bounds"
    elif requested_near is None:
        depth_near = clip_near
        depth_far = clip_far
        policy = "camera_clip_planes_fallback"
    else:
        depth_near = max(clip_near, requested_near)
        depth_far = min(clip_far, requested_far)
        policy = "fixed_shot_range_clamped_to_camera"
        if requested_near <= 0.0 or requested_far <= requested_near:
            raise RuntimeError(
                "Depth playblast fixed range is invalid: near={0}, far={1}.".format(
                    requested_near,
                    requested_far,
                )
            )
    if depth_far <= depth_near:
        raise RuntimeError(
            "Depth playblast range does not overlap the camera clipping range."
        )
    report = {
        "profile": DEPTH_PLAYBLAST_PROFILE,
        "space": "camera",
        "source": "object_bbox_camera_depth",
        "normalization_policy": policy,
        "near": depth_near,
        "far": depth_far,
        # Compatibility fields expose the complete animated clip envelope.
        "camera_near_clip": clip_near,
        "camera_far_clip": clip_far,
        "camera_near_clip_min": clip_near,
        "camera_near_clip_max": clip_near_max,
        "camera_far_clip_min": clip_far_min,
        "camera_far_clip_max": clip_far,
        "camera_clip_animated": (
            abs(clip_near_max - clip_near) > 1.0e-9
            or abs(clip_far - clip_far_min) > 1.0e-9
        ),
        "range_evaluation_scope": (
            "complete_requested_sequence" if frame_values else "current_frame"
        ),
        "range_evaluated_frame_count": len(frame_values) if frame_values else 1,
        "range_evaluation_backend": (
            _clean(sampled_range.get("evaluation_backend"))
            if sampled_range
            else "current_frame_camera_clip"
        ),
        "output_aspect_ratio": float(output_width) / float(output_height),
        "near_color": DEPTH_NEAR_COLOR,
        "far_color": DEPTH_FAR_COLOR,
        "output_value_range": [DEPTH_FAR_COLOR, DEPTH_NEAR_COLOR],
        "camera_near_safety_margin": DEPTH_CAMERA_NEAR_SAFETY_MARGIN,
        "camera_origin_distance": 0.0,
        "camera_clip_is_hard_safety_boundary": True,
        "reserved_output_value_range": [DEPTH_NEAR_COLOR, 1.0],
        "direction": "near_white_far_black",
        "background": "pure_black",
        "temporal_normalization": "fixed_for_complete_sequence",
        "encoding_curve": "normalized_power",
        "contrast_exponent": DEPTH_CONTRAST_EXPONENT,
    }
    if sampled_range:
        report["shot_range_sample"] = sampled_range
    return report


def _depth_camera_world_inverse_matrix(camera):
    """Return API 2.0 and this frame's camera world-inverse matrix."""
    try:
        from maya.api import OpenMaya as om
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast requires Maya API camera-space matrix support: "
            "{0}".format(exc)
        )
    camera_transform = camera
    try:
        if cmds.nodeType(camera_transform) == "camera":
            parents = cmds.listRelatives(
                camera_transform,
                parent=True,
                fullPath=True,
            ) or []
            if len(parents) != 1:
                raise RuntimeError(
                    "camera shape expected one transform parent, got {0}".format(
                        len(parents)
                    )
                )
            camera_transform = parents[0]
        raw_matrix = cmds.getAttr(
            camera_transform + ".worldInverseMatrix[0]"
        )
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not evaluate the camera matrix: {0}".format(
                exc
            )
        )
    if (
        isinstance(raw_matrix, (list, tuple))
        and len(raw_matrix) == 1
        and isinstance(raw_matrix[0], (list, tuple))
    ):
        raw_matrix = raw_matrix[0]
    try:
        return om, om.MMatrix(raw_matrix)
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast camera matrix is invalid: {0}".format(exc)
        )


def _depth_median(values):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise RuntimeError("Depth median requires at least one value.")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) * 0.5


def _depth_percentile(values, fraction):
    """Return a deterministic linearly interpolated percentile."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise RuntimeError("Depth percentile requires at least one value.")
    fraction = float(fraction)
    if not math.isfinite(fraction) or fraction < 0.0 or fraction > 1.0:
        raise RuntimeError(
            "Depth percentile fraction must be within 0.0..1.0."
        )
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * float(len(ordered) - 1)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - float(lower_index)
    return (
        ordered[lower_index] * (1.0 - weight)
        + ordered[upper_index] * weight
    )


def _depth_shape_representative_camera_depth(
    shape,
    camera_matrix,
    om,
    frame=None,
):
    """Return median positive camera depth of the exact world bbox corners.

    Bounds are queried with ``ignoreInvisible=False`` because an animated path
    can be hidden on one output frame and visible on another.  It must retain a
    valid material assignment on every frame even while it does not draw.
    """
    try:
        bounds = cmds.exactWorldBoundingBox(
            shape,
            ignoreInvisible=False,
        )
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not evaluate the world bounds for {0} at "
            "frame {1}: {2}".format(shape, frame, exc)
        )
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 6:
        raise RuntimeError(
            "Depth playblast received invalid world bounds for {0} at frame "
            "{1}: {2!r}.".format(shape, frame, bounds)
        )
    try:
        values = [float(value) for value in bounds]
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast received non-numeric world bounds for {0} at "
            "frame {1}: {2}".format(shape, frame, exc)
        )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError(
            "Depth playblast received non-finite world bounds for {0} at "
            "frame {1}.".format(shape, frame)
        )

    xs = (values[0], values[3])
    ys = (values[1], values[4])
    zs = (values[2], values[5])
    positive_depths = []
    try:
        for x_value in xs:
            for y_value in ys:
                for z_value in zs:
                    point = (
                        om.MPoint(x_value, y_value, z_value, 1.0)
                        * camera_matrix
                    )
                    depth = -float(point.z)
                    if math.isfinite(depth) and depth > 0.0:
                        positive_depths.append(depth)
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not transform world bounds for {0} at "
            "frame {1}: {2}".format(shape, frame, exc)
        )
    if positive_depths:
        return _depth_median(positive_depths)

    try:
        center = om.MPoint(
            (values[0] + values[3]) * 0.5,
            (values[1] + values[4]) * 0.5,
            (values[2] + values[5]) * 0.5,
            1.0,
        ) * camera_matrix
        center_depth = -float(center.z)
    except Exception as exc:
        raise RuntimeError(
            "Depth playblast could not transform the world-bounds center for "
            "{0} at frame {1}: {2}".format(shape, frame, exc)
        )
    if not math.isfinite(center_depth):
        raise RuntimeError(
            "Depth playblast received a non-finite bbox-center depth for {0} "
            "at frame {1}.".format(shape, frame)
        )
    return center_depth


def _depth_grayscale_bucket_index(depth, near, far):
    """Quantize fixed-range depth across all 256 palette indices."""
    depth = float(depth)
    near = float(near)
    far = float(far)
    if not all(math.isfinite(value) for value in (depth, near, far)):
        raise RuntimeError("Depth bucket inputs must be finite.")
    if far <= near:
        raise RuntimeError(
            "Depth bucket range is invalid: near={0}, far={1}.".format(
                near,
                far,
            )
        )
    normalized = min(1.0, max(0.0, (depth - near) / (far - near)))
    gray = 1.0 - math.pow(normalized, DEPTH_CONTRAST_EXPONENT)
    return int(math.floor(gray * 255.0 + 0.5))


def _depth_grayscale_value(bucket_index):
    bucket_index = int(bucket_index)
    if bucket_index < 0 or bucket_index >= DEPTH_GRAYSCALE_BUCKET_COUNT:
        raise RuntimeError(
            "Depth grayscale bucket index is out of range: {0}".format(
                bucket_index
            )
        )
    normalized = float(bucket_index) / float(
        DEPTH_GRAYSCALE_BUCKET_COUNT - 1
    )
    return DEPTH_FAR_COLOR + (
        (DEPTH_NEAR_COLOR - DEPTH_FAR_COLOR) * normalized
    )


def _create_depth_grayscale_buckets():
    """Create 256 constant materials spanning only the safe 0.0..0.9 range."""
    groups = []
    for bucket_index in range(DEPTH_GRAYSCALE_BUCKET_COUNT):
        gray = _depth_grayscale_value(bucket_index)
        groups.append(
            _surface_shader(
                "HMB_DepthGray_{0:03d}".format(bucket_index),
                (gray, gray, gray),
                fresh=True,
            )
        )
    if len(groups) != DEPTH_GRAYSCALE_BUCKET_COUNT or len(set(groups)) != len(groups):
        raise RuntimeError(
            "Depth playblast could not create 256 unique grayscale shading "
            "groups."
        )
    return groups


def _depth_cutout_surface_group(bucket_index, source_plug, cache):
    key = (int(bucket_index), _clean(source_plug))
    if key in cache:
        return cache[key]
    gray = _depth_grayscale_value(bucket_index)
    group = _surface_shader(
        "HMB_DepthGray_{0:03d}_Cutout_{1}".format(
            int(bucket_index),
            _cutout_variant_token(source_plug),
        ),
        (gray, gray, gray),
        fresh=True,
        transparency_source=source_plug,
    )
    cache[key] = group
    return group


def _apply_depth_shader(
    camera,
    job,
    frame_values=None,
    width=None,
    height=None,
):
    """Prepare shared grayscale buckets and a verified per-frame assigner."""
    mouth_controller = (
        (job or {}).get("_mouth_inner_patch_depth_controller")
        if isinstance(job, dict)
        else None
    )
    recovery_report = dict(
        (job or {}).get("_proxy_preview_recovery")
        or _empty_proxy_preview_recovery_report()
    )
    if (
        int(recovery_report.get("candidate_shape_count") or 0)
        != int(recovery_report.get("recovered_shape_count") or 0)
        or int(recovery_report.get("candidate_path_count") or 0)
        != int(recovery_report.get("recovered_path_count") or 0)
    ):
        raise RuntimeError(
            "Depth playblast proxy preview recovery was incomplete: {0} "
            "of {1} shapes and {2} of {3} instance paths recovered.".format(
                int(recovery_report.get("recovered_shape_count") or 0),
                int(recovery_report.get("candidate_shape_count") or 0),
                int(recovery_report.get("recovered_path_count") or 0),
                int(recovery_report.get("candidate_path_count") or 0),
            )
        )
    range_report = _depth_range(
        camera,
        job,
        frame_values=frame_values,
        width=width,
        height=height,
    )
    shapes = _all_depth_renderable_shapes(job)
    if not shapes:
        raise RuntimeError(
            "Depth playblast found no visible polygon mesh or NURBS surface "
            "shapes to shade."
        )
    cutout_snapshot = _ensure_authored_cutout_snapshot(job, shapes)
    cutout_records = {}
    for shape in shapes:
        long_names = _long_names([shape])
        key = long_names[0] if long_names else shape
        cutout_records[shape] = cutout_snapshot.get(key) or {
            "shape": key,
            "alpha_driven": False,
        }
    alpha_cutout_shapes = sorted(
        shape
        for shape, record in cutout_records.items()
        if record.get("alpha_driven")
    )
    mouth_alpha_shapes = set(
        shape
        for shape, record in cutout_records.items()
        if _mouth_semantic_cutout_candidate(shape, record)
    )
    cutout_source_plugs = sorted(set(
        _clean(cutout_records[shape].get("source_plug"))
        for shape in alpha_cutout_shapes
        if _clean(cutout_records[shape].get("source_plug"))
    ))
    if any(
        not _clean(cutout_records[shape].get("source_plug"))
        for shape in alpha_cutout_shapes
    ):
        raise RuntimeError(
            "Depth playblast found a cutout shape without a captured "
            "outTransparency source."
        )
    buckets = _create_depth_grayscale_buckets()
    cutout_bucket_cache = {}
    shape_type_counts = _depth_shape_type_counts(shapes)
    assignment_verification = {
        "shape_path_count": len(shapes),
        "mesh_path_count": int(shape_type_counts.get("mesh") or 0),
        "nurbs_surface_path_count": int(
            shape_type_counts.get("nurbsSurface") or 0
        ),
        "verified_shape_path_count": 0,
        "verified_mesh_face_count": 0,
        "rendered_frame_count": 0,
        "expected_frame_assignment_count": 0,
        "verified_frame_assignment_count": 0,
    }
    range_report["renderable_shape_count"] = len(shapes)
    range_report["mesh_shape_count"] = int(shape_type_counts.get("mesh") or 0)
    range_report["nurbs_surface_shape_count"] = int(
        shape_type_counts.get("nurbsSurface") or 0
    )
    range_report["source"] = "object_bbox_camera_depth"
    range_report[
        "assignment_mode"
    ] = "color_picker_style_shared_gray_material_buckets"
    range_report["depth_update_scope"] = "per_shape_path_per_output_frame"
    range_report[
        "representative_depth"
    ] = "median_positive_camera_depth_of_world_bbox_corners"
    range_report["shader_model"] = "surfaceShader"
    range_report["grayscale_bucket_count"] = DEPTH_GRAYSCALE_BUCKET_COUNT
    range_report["proxy_preview_recovery"] = recovery_report
    range_report["assignment_verification"] = assignment_verification
    range_report["standard_nodes"] = ["surfaceShader"]
    range_report["cutout_transparency"] = {
        "policy": CUTOUT_TRANSPARENCY_POLICY,
        "captured_shape_path_count": len(shapes),
        "alpha_driven_shape_path_count": len(alpha_cutout_shapes),
        "source_plug_count": len(cutout_source_plugs),
        "verified_shape_path_count": 0,
        "ambiguous_shape_path_count": 0,
        "unsupported_shape_path_count": 0,
    }
    previous_assignments = {}

    def assign_depth_frame(frame, _frame_index=None, _frame_count=None):
        om, camera_matrix = _depth_camera_world_inverse_matrix(camera)
        expected_assignments = {}
        assignments_by_group = {}
        for shape in shapes:
            representative_depth = _depth_shape_representative_camera_depth(
                shape,
                camera_matrix,
                om,
                frame=frame,
            )
            bucket_index = _depth_grayscale_bucket_index(
                representative_depth,
                range_report["near"],
                range_report["far"],
            )
            cutout_record = cutout_records.get(shape) or {}
            source_plug = _clean(cutout_record.get("source_plug"))
            forced_exclusion_group = (
                mouth_controller.depth_assignment_group(shape)
                if mouth_controller is not None
                else ""
            )
            if forced_exclusion_group:
                shading_group = forced_exclusion_group
            elif cutout_record.get("alpha_driven"):
                try:
                    shading_group = _depth_cutout_surface_group(
                        bucket_index,
                        source_plug,
                        cutout_bucket_cache,
                    )
                except Exception:
                    if shape not in mouth_alpha_shapes or mouth_controller is None:
                        raise
                    shading_group = mouth_controller.depth_assignment_failed(
                        shape,
                        "authored_alpha_connection_failed",
                    )
            else:
                if shape in mouth_alpha_shapes:
                    if mouth_controller is None:
                        raise RuntimeError(
                            "Depth mouth alpha requires verified authored transparency."
                        )
                    shading_group = mouth_controller.depth_assignment_failed(
                        shape,
                        "authored_alpha_unverified",
                    )
                else:
                    shading_group = buckets[bucket_index]
            if shape in mouth_alpha_shapes and shading_group in buckets:
                raise RuntimeError(
                    "Depth refused an opaque fallback for a mouth alpha card."
                )
            expected_assignments[shape] = shading_group
            if (
                previous_assignments.get(shape) != shading_group
                or shape in mouth_alpha_shapes
            ):
                assignments_by_group.setdefault(shading_group, []).append(shape)

        failures = []
        for shading_group in sorted(assignments_by_group):
            failures.extend(
                _assign(
                    sorted(assignments_by_group[shading_group]),
                    shading_group,
                )
            )
        if failures:
            raise RuntimeError(
                "Depth shader assignment failed at frame {0}: {1}".format(
                    frame,
                    " | ".join(failures[:20])
                    + (
                        " | and {0} more".format(len(failures) - 20)
                        if len(failures) > 20
                        else ""
                    ),
                )
            )

        frame_index = int(_frame_index or 0)
        frame_count = max(1, int(_frame_count or 1))
        full_verification = frame_index == 0 or frame_index == frame_count - 1
        verification_assignments = (
            expected_assignments
            if full_verification
            else dict(
                (shape, expected_assignments[shape])
                for group_shapes in assignments_by_group.values()
                for shape in group_shapes
            )
        )
        verified = None
        if verification_assignments:
            verified = _verify_depth_shader_assignment(
                verification_assignments
            )
            if int(verified.get("verified_shape_path_count") or 0) != len(
                verification_assignments
            ):
                raise RuntimeError(
                    "Depth assignment verification was incomplete at frame "
                    "{0}: expected {1}, got {2}.".format(
                        frame,
                        len(verification_assignments),
                        int(verified.get("verified_shape_path_count") or 0),
                    )
                )
            if full_verification:
                for key in (
                    "shape_path_count",
                    "mesh_path_count",
                    "nurbs_surface_path_count",
                ):
                    if int(verified.get(key) or 0) != int(
                        assignment_verification.get(key) or 0
                    ):
                        raise RuntimeError(
                            "Depth assignment verification changed {0} at "
                            "frame {1}: expected {2}, got {3}.".format(
                                key,
                                frame,
                                assignment_verification.get(key),
                                verified.get(key),
                            )
                        )
                assignment_verification["verified_shape_path_count"] = max(
                    int(assignment_verification["verified_shape_path_count"]),
                    int(verified.get("verified_shape_path_count") or 0),
                )
                active_alpha_cutout_shapes = [
                    shape
                    for shape in alpha_cutout_shapes
                    if not (
                        mouth_controller is not None
                        and mouth_controller.depth_assignment_group(shape)
                    )
                ]
                verified_cutout_shapes = [
                    shape
                    for shape in active_alpha_cutout_shapes
                    if shape in verification_assignments
                    and expected_assignments.get(shape) not in buckets
                ]
                if len(verified_cutout_shapes) != len(active_alpha_cutout_shapes):
                    raise RuntimeError(
                        "Depth cutout transparency verification was incomplete "
                        "at frame {0}: expected {1}, got {2}.".format(
                            frame,
                            len(active_alpha_cutout_shapes),
                            len(verified_cutout_shapes),
                        )
                    )
                range_report["cutout_transparency"][
                    "verified_shape_path_count"
                ] = len(verified_cutout_shapes)
            assignment_verification["verified_mesh_face_count"] += int(
                verified.get("verified_mesh_face_count") or 0
            )
        assignment_verification["rendered_frame_count"] += 1
        assignment_verification[
            "expected_frame_assignment_count"
        ] += len(expected_assignments)
        # Unchanged SG assignments were fully verified at the first frame and
        # are immutable Maya connections. Middle frames re-verify only paths
        # whose depth bucket changed; the final frame performs one full audit.
        assignment_verification[
            "verified_frame_assignment_count"
        ] += len(expected_assignments)
        previous_assignments.clear()
        previous_assignments.update(expected_assignments)

    def finalize_cutout_report():
        excluded = (
            set(mouth_controller.dynamic_depth_excluded)
            if mouth_controller is not None
            else set()
        )
        active_alpha_shapes = [
            shape for shape in alpha_cutout_shapes if shape not in excluded
        ]
        active_source_plugs = set(
            _clean((cutout_records.get(shape) or {}).get("source_plug"))
            for shape in active_alpha_shapes
            if _clean((cutout_records.get(shape) or {}).get("source_plug"))
        )
        cutout_report = range_report["cutout_transparency"]
        cutout_report["alpha_driven_shape_path_count"] = len(
            active_alpha_shapes
        )
        cutout_report["source_plug_count"] = len(active_source_plugs)
        cutout_report["verified_shape_path_count"] = (
            len(active_alpha_shapes)
            if int(assignment_verification.get("rendered_frame_count") or 0) > 0
            else 0
        )

    assign_depth_frame.finalize_cutout_report = finalize_cutout_report
    return range_report, assign_depth_frame


def _scene_fps():
    unit = cmds.currentUnit(query=True, time=True)
    mapping = {
        "game": 15.0,
        "film": 24.0,
        "pal": 25.0,
        "ntsc": 30.0,
        "show": 48.0,
        "palf": 50.0,
        "ntscf": 60.0,
    }
    if unit in mapping:
        return mapping[unit]
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)fps$", unit)
    if match:
        return float(match.group(1))
    raise RuntimeError("Unsupported Maya time unit: {0}".format(unit))


def _frame_values(start_frame, end_frame):
    start_value = float(start_frame)
    end_value = float(end_frame)
    if end_value < start_value:
        raise RuntimeError("End frame is before start frame.")
    # Maya can legitimately expose fractional playback bounds after a scene's
    # time unit is converted (for example film to PAL). Sample every frame from
    # the exact start and include the exact endpoint when it is not on that grid.
    # This preserves Maya's published range instead of rejecting a valid scene.
    span = end_value - start_value
    whole_steps = int(span + 1e-9)
    try:
        max_frames = max(
            1,
            int(os.environ.get("HMB_MAX_PLAYBLAST_FRAMES", "1000001")),
        )
    except (TypeError, ValueError):
        max_frames = 1000001
    endpoint_extra = int(abs((start_value + whole_steps) - end_value) > 1e-6)
    requested_count = whole_steps + 1 + endpoint_extra
    if requested_count > max_frames:
        raise RuntimeError(
            "Playback range requests {0} frames; the technical safety budget "
            "is {1}. Set HMB_MAX_PLAYBLAST_FRAMES explicitly for this "
            "workstation to continue.".format(requested_count, max_frames)
        )
    frames = [start_value + index for index in range(whole_steps + 1)]
    if not frames or abs(frames[-1] - end_value) > 1e-6:
        frames.append(end_value)
    return frames


def _validate_render_storage_budget(job, frames, width, height):
    """Fail before render only when the local filesystem cannot hold staging."""
    width = int(width)
    height = int(height)
    try:
        max_dimension = max(
            1,
            int(os.environ.get("HMB_MAX_PLAYBLAST_DIMENSION", "8192")),
        )
    except (TypeError, ValueError):
        max_dimension = 8192
    if width <= 0 or height <= 0 or width > max_dimension or height > max_dimension:
        raise RuntimeError(
            "Render resolution {0}x{1} is outside the workstation safety "
            "budget (maximum dimension {2}). Set "
            "HMB_MAX_PLAYBLAST_DIMENSION explicitly to continue.".format(
                width, height, max_dimension
            )
        )
    pass_count = 1
    if bool(job.get("generate_depth_playblast")):
        pass_count += 1
    if bool(job.get("generate_motion_guide")):
        pass_count += 1
    # Four bytes/pixel is a conservative staging estimate for PNG plus a 10%
    # transaction margin. This is a capacity check, not a creative limit.
    estimated_bytes = int(
        len(frames) * width * height * 4 * pass_count * 1.10
    )
    job_root = os.path.dirname(os.path.abspath(job.get("result_path") or "."))
    free_bytes = int(shutil.disk_usage(job_root).free)
    reserve_bytes = max(512 * 1024 * 1024, int(estimated_bytes * 0.10))
    allow_low_disk = _clean(os.environ.get("HMB_ALLOW_LOW_DISK", "")).lower() in (
        "1", "true", "yes", "on"
    )
    if estimated_bytes + reserve_bytes > free_bytes and not allow_low_disk:
        raise RuntimeError(
            "Estimated frame staging needs {0:.1f} GiB plus reserve, but only "
            "{1:.1f} GiB is free. Free disk space or set HMB_ALLOW_LOW_DISK=1 "
            "to accept the risk for this workstation.".format(
                estimated_bytes / float(1024 ** 3),
                free_bytes / float(1024 ** 3),
            )
        )
    return {
        "frame_count": len(frames),
        "pass_count": pass_count,
        "width": width,
        "height": height,
        "estimated_staging_bytes": estimated_bytes,
        "free_bytes": free_bytes,
        "operator_low_disk_override": allow_low_disk,
    }


def _same_attr_value(left, right):
    try:
        return abs(float(left) - float(right)) <= 1e-9
    except Exception:
        return left == right


def _set_attr_with_restore(restore_state, plug, value, failures, required=True):
    """Set one temporary Maya value and remember its exact authored value."""
    try:
        if not cmds.objExists(plug):
            return False
        original = cmds.getAttr(plug)
    except Exception as exc:
        if required:
            failures.append("{0} could not be read ({1})".format(plug, exc))
        return False
    if _same_attr_value(original, value):
        return False
    try:
        try:
            settable = bool(cmds.getAttr(plug, settable=True))
        except Exception:
            settable = True
        if not settable:
            raise RuntimeError("attribute is locked or connected")
        cmds.setAttr(plug, value)
        actual = cmds.getAttr(plug)
        if not _same_attr_value(actual, value):
            raise RuntimeError("verification returned {0!r}".format(actual))
    except Exception as exc:
        if required:
            failures.append("{0} could not be set to {1!r} ({2})".format(plug, value, exc))
        return False
    restore_state["attributes"].append((plug, original))
    return True


def _enum_entries(node, attribute):
    try:
        raw = cmds.attributeQuery(attribute, node=node, listEnum=True) or []
    except Exception:
        return []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    if not raw:
        return []
    entries = []
    next_index = 0
    for token in _clean(raw[0]).split(":"):
        label = token
        index = next_index
        if "=" in token:
            maybe_label, maybe_index = token.rsplit("=", 1)
            try:
                index = int(maybe_index)
                label = maybe_label
            except Exception:
                pass
        entries.append((index, _clean(label)))
        next_index = index + 1
    return entries


def _full_detail_proxy_enum_index(node, attribute):
    entries = _enum_entries(node, attribute)
    normalized = [
        (index, re.sub(r"[^a-z0-9]+", "", label.lower()))
        for index, label in entries
    ]
    if not any(("boundingbox" in label or label == "bbox") for _index, label in normalized):
        return None
    priorities = (
        "previewmesh",
        "fulldetail",
        "fullresolution",
        "highresolution",
        "highres",
        "polygons",
        "polygon",
        "mesh",
        "full",
    )
    for desired in priorities:
        for index, label in normalized:
            if "boundingbox" in label or label == "bbox":
                continue
            if label == desired or desired in label:
                if "linkedmesh" in label:
                    continue
                return index
    return None


def _proxy_preview_candidates():
    try:
        nodes = cmds.ls(dependencyNodes=True) or []
    except Exception:
        try:
            nodes = cmds.ls() or []
        except Exception:
            nodes = []
    result = []
    for node in sorted(set(_clean(item) for item in nodes if _clean(item))):
        try:
            node_type = _clean(cmds.nodeType(node))
        except Exception:
            node_type = ""
        descriptor = (node + " " + node_type).lower()
        if any(token in descriptor for token in ("proxy", "standin", "stand_in", "procedural")):
            result.append((node, node_type))
    return result


def _unresolved_proxy_plugins():
    unresolved = []
    try:
        unknown_nodes = cmds.ls(type="unknown") or []
    except Exception:
        unknown_nodes = []
    for node in sorted(set(unknown_nodes)):
        try:
            real_class = _clean(cmds.unknownNode(node, query=True, realClassName=True))
        except Exception:
            real_class = ""
        descriptor = (node + " " + real_class).lower()
        if not any(token in descriptor for token in ("proxy", "standin", "stand_in", "procedural")):
            continue
        try:
            plugin = _clean(cmds.unknownNode(node, query=True, plugin=True))
        except Exception:
            plugin = ""
        unresolved.append({
            "node": _clean(node),
            "real_class": real_class,
            "plugin": plugin,
        })
    return unresolved


def _empty_proxy_preview_recovery_report():
    return {
        "candidate_shape_count": 0,
        "candidate_path_count": 0,
        "recovered_shape_count": 0,
        "recovered_path_count": 0,
        "recovered_paths": [],
        "source_paths": [],
    }


def _depth_node_uuid(path):
    try:
        values = cmds.ls(path, uuid=True) or []
    except Exception as exc:
        raise RuntimeError(
            "Depth proxy preview could not identify {0}: {1}".format(
                path,
                exc,
            )
        )
    values = sorted(set(_clean(value) for value in values if _clean(value)))
    if len(values) != 1:
        raise RuntimeError(
            "Depth proxy preview expected one Maya UUID for {0}, got {1}.".format(
                path,
                len(values),
            )
        )
    return values[0]


def _looks_like_proxy_placeholder_output(shape):
    """Identify an unevaluated proxy output without requiring its plug-in."""
    descriptor_parts = [_clean(shape)]
    try:
        source_plugs = cmds.listConnections(
            shape + ".inMesh",
            source=True,
            destination=False,
            plugs=True,
        ) or []
    except Exception:
        source_plugs = []
    for source_plug in source_plugs:
        source_node = _clean(source_plug).split(".", 1)[0]
        if not source_node:
            continue
        descriptor_parts.append(source_node)
        try:
            node_type = _clean(cmds.nodeType(source_node))
        except Exception:
            node_type = ""
        descriptor_parts.append(node_type)
        if node_type.lower() == "unknown":
            for query_flag in ("realClassName", "plugin"):
                try:
                    descriptor_parts.append(
                        _clean(
                            cmds.unknownNode(
                                source_node,
                                query=True,
                                **{query_flag: True}
                            )
                        )
                    )
                except Exception:
                    pass
    descriptor = " ".join(descriptor_parts).lower()
    return any(
        token in descriptor
        for token in (
            "proxy",
            "standin",
            "stand_in",
            "procedural",
        )
    )


def _recover_scene_saved_proxy_previews(restore_state, failures):
    """Expose cached native proxy previews without touching invalid inMesh.

    Missing renderer plug-ins leave their visible output mesh at zero faces,
    while Maya can retain a populated intermediate sibling under the same
    transform.  Driving that invalid output from the cached mesh can crash VP2
    during Poly smoothMeshDataRef evaluation.  The safe disposable-session
    contract is therefore to expose the existing native sibling and hide the
    empty output.  Both authored attributes are recorded for restoration.
    """
    report = _empty_proxy_preview_recovery_report()
    try:
        mesh_paths = cmds.ls(
            dag=True,
            type="mesh",
            long=True,
            allPaths=True,
        ) or []
    except Exception as exc:
        failures.append(
            "Scene-saved proxy preview recovery could not enumerate every "
            "mesh instance DAG path ({0})".format(exc)
        )
        return report

    visible_outputs = _marker_renderable_shapes(
        [path for path in mesh_paths if not _is_intermediate_shape(path)]
    )
    candidate_paths = []
    for path in visible_outputs:
        try:
            face_count = int(cmds.polyEvaluate(path, face=True) or 0)
        except Exception as exc:
            failures.append(
                "Scene-saved proxy preview could not inspect {0} ({1})".format(
                    path,
                    exc,
                )
            )
            continue
        if face_count == 0 and _looks_like_proxy_placeholder_output(path):
            candidate_paths.append(path)

    candidate_paths = sorted(set(candidate_paths))
    candidate_ids = {}
    for path in candidate_paths:
        try:
            candidate_ids.setdefault(_depth_node_uuid(path), []).append(path)
        except Exception as exc:
            failures.append(str(exc))
    report["candidate_shape_count"] = len(candidate_ids)
    report["candidate_path_count"] = len(candidate_paths)
    if not candidate_paths:
        return report

    mappings = []
    planning_failures = []
    for output_path in candidate_paths:
        try:
            parents = cmds.listRelatives(
                output_path,
                parent=True,
                fullPath=True,
            ) or []
        except Exception as exc:
            parents = []
            planning_failures.append(
                "{0} parent query failed ({1})".format(output_path, exc)
            )
        if len(parents) != 1:
            planning_failures.append(
                "{0} expected one concrete parent path, got {1}".format(
                    output_path,
                    len(parents),
                )
            )
            continue
        parent = parents[0]
        try:
            siblings = cmds.listRelatives(
                parent,
                shapes=True,
                fullPath=True,
                type="mesh",
            ) or []
        except Exception as exc:
            planning_failures.append(
                "{0} sibling query failed ({1})".format(output_path, exc)
            )
            continue
        sources = []
        for sibling in siblings:
            if not _is_intermediate_shape(sibling):
                continue
            try:
                sibling_faces = int(
                    cmds.polyEvaluate(sibling, face=True) or 0
                )
            except Exception as exc:
                planning_failures.append(
                    "{0} cached sibling {1} could not be inspected ({2})".format(
                        output_path,
                        sibling,
                        exc,
                    )
                )
                continue
            if sibling_faces > 0:
                sources.append(sibling)
        sources = sorted(set(sources))
        if len(sources) != 1:
            planning_failures.append(
                "{0} requires exactly one populated intermediate mesh under "
                "{1}; found {2}: {3}".format(
                    output_path,
                    parent,
                    len(sources),
                    ", ".join(sources) or "<none>",
                )
            )
            continue
        try:
            output_uuid = _depth_node_uuid(output_path)
            source_uuid = _depth_node_uuid(sources[0])
        except Exception as exc:
            planning_failures.append(str(exc))
            continue
        mappings.append({
            "output_path": output_path,
            "output_uuid": output_uuid,
            "source_path": sources[0],
            "source_uuid": source_uuid,
        })

    grouped = {}
    for mapping in mappings:
        record = grouped.setdefault(
            mapping["output_uuid"],
            {
                "output_paths": [],
                "source_paths": [],
                "source_uuids": set(),
            },
        )
        record["output_paths"].append(mapping["output_path"])
        record["source_paths"].append(mapping["source_path"])
        record["source_uuids"].add(mapping["source_uuid"])
    for output_uuid, record in grouped.items():
        if len(record["source_uuids"]) != 1:
            planning_failures.append(
                "Proxy output {0} maps to multiple cached mesh nodes across "
                "its instances: {1}".format(
                    output_uuid,
                    ", ".join(sorted(set(record["source_paths"]))),
                )
            )
    if len(mappings) != len(candidate_paths):
        planning_failures.append(
            "Only {0} of {1} proxy placeholder paths had a valid cached "
            "native mesh mapping.".format(len(mappings), len(candidate_paths))
        )
    if len(grouped) != len(candidate_ids):
        planning_failures.append(
            "Only {0} of {1} unique proxy placeholder shapes had a valid "
            "cached native mesh mapping.".format(len(grouped), len(candidate_ids))
        )
    if planning_failures:
        failures.extend(
            "Scene-saved proxy preview recovery failed: " + item
            for item in planning_failures
        )
        return report

    recovered_outputs = []
    recovered_sources = []
    for output_uuid in sorted(grouped):
        record = grouped[output_uuid]
        output_path = sorted(set(record["output_paths"]))[0]
        source_path = sorted(set(record["source_paths"]))[0]
        mutation_failures = []
        _set_attr_with_restore(
            restore_state,
            source_path + ".intermediateObject",
            False,
            mutation_failures,
            required=True,
        )
        _set_attr_with_restore(
            restore_state,
            output_path + ".visibility",
            False,
            mutation_failures,
            required=True,
        )
        try:
            if _is_intermediate_shape(source_path):
                mutation_failures.append(
                    source_path + " remained an intermediate mesh"
                )
            if bool(cmds.getAttr(output_path + ".visibility")):
                mutation_failures.append(
                    output_path + " remained visible"
                )
        except Exception as exc:
            mutation_failures.append(
                "visibility/intermediate verification failed ({0})".format(exc)
            )
        if mutation_failures:
            failures.extend(
                "Scene-saved proxy preview recovery failed for {0}: {1}".format(
                    output_path,
                    item,
                )
                for item in mutation_failures
            )
            continue
        recovered_outputs.extend(sorted(set(record["output_paths"])))
        recovered_sources.append(source_path)

    try:
        cmds.refresh(force=True)
    except Exception:
        pass

    verified_source_uuids = set()
    for source_path in sorted(set(recovered_sources)):
        try:
            source_uuid = _depth_node_uuid(source_path)
            polygon_count = _depth_mesh_polygon_count_api(source_path)
            if polygon_count <= 0:
                raise RuntimeError(
                    "MFnMesh.numPolygons returned {0}".format(polygon_count)
                )
            verified_source_uuids.add(source_uuid)
        except Exception as exc:
            failures.append(
                "Scene-saved proxy preview API verification failed for {0}: "
                "{1}".format(source_path, exc)
            )

    recovered_ids = set(
        mapping["output_uuid"]
        for mapping in mappings
        if mapping["output_path"] in recovered_outputs
    )
    expected_source_uuids = set(
        mapping["source_uuid"]
        for mapping in mappings
        if mapping["output_path"] in recovered_outputs
    )
    if verified_source_uuids != expected_source_uuids:
        failures.append(
            "Scene-saved proxy preview verified {0} of {1} cached mesh nodes "
            "for {2} recovered output nodes.".format(
                len(verified_source_uuids),
                len(expected_source_uuids),
                len(recovered_ids),
            )
        )
    report.update({
        "recovered_shape_count": len(recovered_ids),
        "recovered_path_count": len(set(recovered_outputs)),
        "recovered_paths": sorted(set(recovered_outputs)),
        "source_paths": sorted(set(recovered_sources)),
    })
    return report


def _first_display_smoothness_value(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _query_display_smoothness_int(shape, flag):
    value = _first_display_smoothness_value(
        cmds.displaySmoothness(
            shape,
            query=True,
            **{flag: True}
        )
    )
    if value is None:
        raise RuntimeError(
            "{0} displaySmoothness query returned no {1} value".format(
                shape,
                flag,
            )
        )
    return int(value)


def _visible_unsupported_proxy_geometry():
    """Find viewport drawables that cannot satisfy polygon Smooth Preview 3."""
    unsupported_types = {
        "aistandin",
        "assemblydefinition",
        "assemblyreference",
        "gpucache",
        "mayausdproxyshape",
        "pxrusdproxyshape",
        "usdproxyshape",
    }
    try:
        dag_nodes = cmds.ls(dag=True, long=True) or []
    except Exception:
        dag_nodes = []
    unsupported = []
    for node in sorted(set(dag_nodes)):
        try:
            node_type = _clean(cmds.nodeType(node)).lower()
        except Exception:
            node_type = ""
        normalized_type = re.sub(r"[^a-z0-9]+", "", node_type)
        if normalized_type not in unsupported_types:
            continue
        if _marker_renderable_shapes([node]):
            unsupported.append("{0} ({1})".format(node, node_type or "unknown"))
    return unsupported


def _visible_technical_dummy_meshes():
    try:
        mesh_shapes = cmds.ls(type="mesh", long=True) or []
    except Exception:
        mesh_shapes = []
    result = []
    for shape in _marker_renderable_shapes(mesh_shapes):
        if any(
            _technical_asset_branch_name(node)
            for node in _dag_path_nodes(shape)[:-1]
        ):
            result.append(shape)
    return sorted(set(result))


def _apply_full_smooth_viewport(job):
    """Force full-detail Smooth Preview 3 without saving the source scene."""
    requested_profile = _clean((job or {}).get("viewport_quality_profile"))
    if (
        requested_profile
        and requested_profile != FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
    ):
        raise RuntimeError(
            "Unsupported full-smooth viewport quality profile: {0}".format(
                requested_profile
            )
        )

    restore_state = {
        "attributes": [],
        "global_distance_lod": None,
        "mesh_smoothness": [],
        "nurbs_smoothness": [],
    }
    report = {
        "profile": FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
        "global_distance_lod_disabled": False,
        "dag_full_detail_count": 0,
        "display_layer_full_detail_count": 0,
        "proxy_preview_mesh_count": 0,
        "proxy_preview_percent_count": 0,
        "smooth_mesh_preview_mode": 3,
        "smooth_mesh_shape_count": 0,
        "alpha_cutout_smooth_preserved_count": 0,
        "cutout_transparency": {},
        "smooth_nurbs_shape_count": 0,
        "remaining_bounding_box_count": 0,
        "unsupported_proxy_shapes": [],
        "technical_dummy_shapes": [],
        "viewport_render_mode_forced": False,
        "unresolved_proxy_nodes": [],
        "unresolved_proxy_plugin_pass_through": False,
        "proxy_preview_recovery": _empty_proxy_preview_recovery_report(),
        "warnings": [],
        "reference_loading": dict((job or {}).get("_reference_report") or {}),
    }
    failures = []
    # Authored hidden/intermediate proxy caches are never promoted to visible
    # geometry.  The Picker uses only the scene's already loaded, already
    # drawable mesh representation.
    report["proxy_preview_recovery"] = _empty_proxy_preview_recovery_report()
    if bool((job or {}).get("require_full_smooth_geometry")):
        unsupported_proxy_shapes = _visible_unsupported_proxy_geometry()
        technical_dummy_shapes = _visible_technical_dummy_meshes()
        report["unsupported_proxy_shapes"] = unsupported_proxy_shapes
        report["technical_dummy_shapes"] = technical_dummy_shapes
        if unsupported_proxy_shapes:
            failures.append(
                "Viewport proxy/cache/stand-in geometry cannot be used for the "
                "required polygon Smooth Preview 3 playblast: {0}. Supply the "
                "full-detail Maya mesh/reference instead.".format(
                    ", ".join(unsupported_proxy_shapes[:20])
                )
            )
        if technical_dummy_shapes:
            failures.append(
                "Visible dummy/check geometry is forbidden in the full-smooth "
                "playblast: {0}. Supply the production Maya geometry instead.".format(
                    ", ".join(technical_dummy_shapes[:20])
                )
            )

    unresolved_sets = (
        report["reference_loading"].get("high_quality_unresolved_proxy_sets")
        if isinstance(report["reference_loading"], dict)
        else []
    ) or []
    if unresolved_sets:
        failures.append(
            "High-quality Maya proxy references were not uniquely identified for: {0}. "
            "Use an exact proxy tag such as high, hires, highres, highresolution, "
            "render, rendering, final, or hero."
            .format(
                ", ".join(
                    _clean(item.get("proxy_manager")) or "<unknown>"
                    for item in unresolved_sets
                )
            )
        )

    failed_references = (
        report["reference_loading"].get("failed_references")
        if isinstance(report["reference_loading"], dict)
        else []
    ) or []
    if failed_references:
        failures.append(
            "Some authored proxy, prop, or asset references were unavailable; "
            "the playblast will continue with the loaded authored-visible scene: {0}"
            .format(
                ", ".join(
                    "{0} ({1})".format(
                        _clean(item.get("reference_file"))
                        or _clean(item.get("reference_node"))
                        or "<unknown>",
                        _clean(item.get("error")) or "load failed",
                    )
                    for item in failed_references[:12]
                )
                + (
                    ", and {0} more".format(len(failed_references) - 12)
                    if len(failed_references) > 12
                    else ""
                )
            )
        )

    unresolved = _unresolved_proxy_plugins()
    if unresolved:
        report["unresolved_proxy_nodes"] = unresolved
        names = ", ".join(
            "{0} ({1})".format(
                item.get("node") or "<unknown>",
                item.get("plugin") or item.get("real_class") or "missing plug-in",
            )
            for item in unresolved[:12]
        )
        if len(unresolved) > 12:
            names += ", and {0} more".format(len(unresolved) - 12)
        warning = (
            "Proxy plug-in unavailable for unresolved nodes: {0}. The authored "
            "reference, proxy, and visibility state is preserved; cached proxy "
            "recovery is not attempted."
            .format(names)
        )
        report["unresolved_proxy_plugin_pass_through"] = True
        report["warnings"].append(warning)
        _emit_console("WARNING", warning)

    try:
        original_lod = bool(cmds.displayLevelOfDetail(query=True, levelOfDetail=True))
        restore_state["global_distance_lod"] = original_lod
        if original_lod:
            cmds.displayLevelOfDetail(levelOfDetail=False)
            if bool(cmds.displayLevelOfDetail(query=True, levelOfDetail=True)):
                failures.append("Maya distance-based Level of Detail remained enabled.")
            else:
                report["global_distance_lod_disabled"] = True
    except Exception:
        # Batch and mocked Maya builds can omit this UI preference command. DAG
        # and display-layer full-detail validation below remains authoritative.
        restore_state["global_distance_lod"] = None

    quality_scope = (job or {}).get("_viewport_quality_scope_shapes")
    if not isinstance(quality_scope, list):
        quality_scope = (job or {}).get("_render_scope_shapes")
    scoped_shapes = (
        list(quality_scope or [])
        if isinstance(quality_scope, list)
        else None
    )
    if scoped_shapes is not None:
        dag_nodes = sorted(set(
            node
            for shape in scoped_shapes
            for node in _dag_path_nodes(shape)
        ))
    else:
        try:
            dag_nodes = cmds.ls(dag=True, long=True) or []
        except Exception:
            dag_nodes = []
    for node in sorted(set(dag_nodes)):
        enabled_plug = node + ".overrideEnabled"
        lod_plug = node + ".overrideLevelOfDetail"
        try:
            enabled = bool(cmds.getAttr(enabled_plug)) if cmds.objExists(enabled_plug) else False
            lod_value = int(cmds.getAttr(lod_plug)) if cmds.objExists(lod_plug) else 0
        except Exception:
            continue
        if enabled and lod_value == 1:
            if _set_attr_with_restore(
                restore_state,
                lod_plug,
                0,
                failures,
                required=True,
            ):
                report["dag_full_detail_count"] += 1

    if scoped_shapes is not None:
        display_layers = []
        for shape in scoped_shapes:
            try:
                display_layers.extend(
                    cmds.listConnections(
                        shape,
                        source=True,
                        destination=False,
                        type="displayLayer",
                    ) or []
                )
            except Exception:
                pass
        display_layers = sorted(set(display_layers))
    else:
        try:
            display_layers = cmds.ls(type="displayLayer") or []
        except Exception:
            display_layers = []
    for layer in sorted(set(display_layers)):
        if layer == "defaultLayer":
            continue
        plug = layer + ".levelOfDetail"
        try:
            is_bbox = cmds.objExists(plug) and int(cmds.getAttr(plug)) == 1
        except Exception:
            is_bbox = False
        if is_bbox and _set_attr_with_restore(
            restore_state,
            plug,
            0,
            failures,
            required=True,
        ):
            report["display_layer_full_detail_count"] += 1

    if scoped_shapes is not None:
        mesh_shapes = []
        for shape in scoped_shapes:
            try:
                if cmds.nodeType(shape) == "mesh":
                    mesh_shapes.append(shape)
            except Exception:
                pass
    else:
        try:
            mesh_shapes = cmds.ls(type="mesh", long=True) or []
        except Exception:
            mesh_shapes = []
    cutout_snapshot = _ensure_authored_cutout_snapshot(job, mesh_shapes)
    report["cutout_transparency"] = dict(
        (job or {}).get("_authored_cutout_report") or {}
    )
    for shape in sorted(set(mesh_shapes)):
        if _is_intermediate_shape(shape):
            continue
        long_names = _long_names([shape])
        snapshot_key = long_names[0] if long_names else shape
        cutout_record = cutout_snapshot.get(snapshot_key) or {}
        if bool(cutout_record.get("alpha_driven")) or (
            _mouth_semantic_cutout_candidate(snapshot_key, cutout_record)
            and (
                cutout_record.get("unsupported")
                or cutout_record.get("ambiguous")
            )
        ):
            # Polygon Smooth Preview can introduce interpolation/edge artifacts
            # on texture-alpha cards.  Preserve their authored display mode;
            # every solid mesh still takes the shared Smooth Preview 3 path.
            report["alpha_cutout_smooth_preserved_count"] += 1
            continue
        try:
            original_mode = _first_display_smoothness_value(
                cmds.displaySmoothness(
                    shape,
                    query=True,
                    polygonObject=True,
                )
            )
            if original_mode is None:
                raise RuntimeError("query returned no polygonObject value")
            restore_state["mesh_smoothness"].append(
                (shape, int(original_mode))
            )
            cmds.displaySmoothness(
                shape,
                divisionsU=3,
                divisionsV=3,
                pointsWire=16,
                pointsShaded=4,
                polygonObject=3,
            )
            actual_mode = _first_display_smoothness_value(
                cmds.displaySmoothness(
                    shape,
                    query=True,
                    polygonObject=True,
                )
            )
            if int(actual_mode) != 3:
                raise RuntimeError(
                    "verification returned polygonObject={0!r}".format(
                        actual_mode
                    )
                )
            report["smooth_mesh_shape_count"] += 1
        except Exception as exc:
            failures.append(
                "{0} could not enter Maya Smooth Preview 3 ({1})".format(
                    shape,
                    exc,
                )
            )

    if scoped_shapes is not None:
        nurbs_shapes = []
        for shape in scoped_shapes:
            try:
                if cmds.nodeType(shape) == "nurbsSurface":
                    nurbs_shapes.append(shape)
            except Exception:
                pass
    else:
        try:
            nurbs_shapes = cmds.ls(type="nurbsSurface", long=True) or []
        except Exception:
            nurbs_shapes = []
    for shape in sorted(set(nurbs_shapes)):
        # ShapeOrig/history NURBS are construction inputs, are not drawn by
        # Viewport 2.0, and commonly return None for displaySmoothness queries.
        # They must not block validation of the visible production geometry.
        if _is_intermediate_shape(shape):
            continue
        try:
            original_values = tuple(
                _query_display_smoothness_int(shape, flag)
                for flag in (
                    "divisionsU",
                    "divisionsV",
                    "pointsWire",
                    "pointsShaded",
                )
            )
            restore_state["nurbs_smoothness"].append(
                (shape, original_values)
            )
            target_values = (3, 3, 16, 4)
            cmds.displaySmoothness(
                shape,
                divisionsU=target_values[0],
                divisionsV=target_values[1],
                pointsWire=target_values[2],
                pointsShaded=target_values[3],
            )
            actual_values = tuple(
                _query_display_smoothness_int(shape, flag)
                for flag in (
                    "divisionsU",
                    "divisionsV",
                    "pointsWire",
                    "pointsShaded",
                )
            )
            if actual_values != target_values:
                raise RuntimeError(
                    "verification returned {0!r}".format(actual_values)
                )
            report["smooth_nurbs_shape_count"] += 1
        except Exception as exc:
            failures.append(
                "{0} could not enter high-quality NURBS smooth display ({1})".format(
                    shape,
                    exc,
                )
            )

    if bool((job or {}).get("require_full_smooth_geometry")):
        if (
            not report["smooth_mesh_shape_count"]
            and not report["alpha_cutout_smooth_preserved_count"]
        ):
            failures.append(
                "No polygon mesh was available for the required Smooth Preview "
                "3 playblast. Bounding boxes, stand-ins, caches, and dummy "
                "primitives are not accepted."
            )

    if _set_attr_with_restore(
        restore_state,
        "hardwareRenderingGlobals.renderMode",
        4,
        failures,
        required=True,
    ):
        report["viewport_render_mode_forced"] = True

    remaining = []
    for node in sorted(set(dag_nodes)):
        try:
            if (
                cmds.objExists(node + ".overrideEnabled")
                and bool(cmds.getAttr(node + ".overrideEnabled"))
                and cmds.objExists(node + ".overrideLevelOfDetail")
                and int(cmds.getAttr(node + ".overrideLevelOfDetail")) == 1
            ):
                remaining.append(node)
        except Exception:
            pass
    for layer in sorted(set(display_layers)):
        try:
            if (
                layer != "defaultLayer"
                and cmds.objExists(layer + ".levelOfDetail")
                and int(cmds.getAttr(layer + ".levelOfDetail")) == 1
            ):
                remaining.append(layer)
        except Exception:
            pass
    report["remaining_bounding_box_count"] = len(remaining)
    if remaining:
        failures.append(
            "Bounding Box display remained active on: {0}".format(
                ", ".join(remaining[:20])
            )
        )

    # Full-detail preparation is a best-effort quality improvement, never a
    # tool-availability policy.  Preserve every successful temporary change,
    # report the rest, and continue with the authored-visible representation.
    for detail in failures:
        warning = "Best-effort viewport quality warning: {0}".format(detail)
        if warning not in report["warnings"]:
            report["warnings"].append(warning)
            _emit_console("WARNING", warning)

    try:
        cmds.refresh(force=True)
    except Exception:
        pass
    return restore_state, report


def _restore_full_smooth_viewport(restore_state):
    warnings = []
    source = restore_state if isinstance(restore_state, dict) else {}
    for shape, values in reversed(source.get("nurbs_smoothness") or []):
        try:
            cmds.displaySmoothness(
                shape,
                divisionsU=int(values[0]),
                divisionsV=int(values[1]),
                pointsWire=int(values[2]),
                pointsShaded=int(values[3]),
            )
        except Exception as exc:
            warnings.append(
                "{0} NURBS smoothness restore failed ({1})".format(shape, exc)
            )
    for shape, mode in reversed(source.get("mesh_smoothness") or []):
        try:
            cmds.displaySmoothness(shape, polygonObject=int(mode))
        except Exception as exc:
            warnings.append(
                "{0} polygon smoothness restore failed ({1})".format(shape, exc)
            )
    for plug, value in reversed(source.get("attributes") or []):
        try:
            if cmds.objExists(plug):
                cmds.setAttr(plug, value)
        except Exception as exc:
            warnings.append("{0} restore failed ({1})".format(plug, exc))
    original_lod = source.get("global_distance_lod")
    if original_lod is not None:
        try:
            cmds.displayLevelOfDetail(levelOfDetail=bool(original_lod))
        except Exception as exc:
            warnings.append("Global Level of Detail restore failed ({0})".format(exc))
    return warnings


def _set_viewport_render_options(
    marker_mode=False,
    preserve_authored_look=False,
    screen_space_patterns=False,
    depth_mode=False,
):
    report = {
        "output_transform_disabled": False,
        "multisample_disabled": False,
        "line_aa_disabled": False,
        "ssao_disabled": False,
        "motion_blur_disabled": False,
        "depth_of_field_disabled": False,
        "fog_disabled": False,
    }
    if not preserve_authored_look:
        try:
            cmds.displayRGBColor("background", NEUTRAL_RGB[0], NEUTRAL_RGB[1], NEUTRAL_RGB[2])
            cmds.displayRGBColor("backgroundTop", NEUTRAL_RGB[0], NEUTRAL_RGB[1], NEUTRAL_RGB[2])
            cmds.displayRGBColor("backgroundBottom", NEUTRAL_RGB[0], NEUTRAL_RGB[1], NEUTRAL_RGB[2])
        except Exception:
            pass
        for attr, value in (
            ("hardwareRenderingGlobals.multiSampleEnable", 0),
            ("hardwareRenderingGlobals.lineAAEnable", 0),
            ("hardwareRenderingGlobals.ssaoEnable", 0),
            ("hardwareRenderingGlobals.motionBlurEnable", 0),
        ):
            try:
                if cmds.objExists(attr):
                    cmds.setAttr(attr, value)
                    actual = cmds.getAttr(attr)
                    if int(actual) == int(value):
                        report_key = {
                            "hardwareRenderingGlobals.multiSampleEnable": "multisample_disabled",
                            "hardwareRenderingGlobals.lineAAEnable": "line_aa_disabled",
                            "hardwareRenderingGlobals.ssaoEnable": "ssao_disabled",
                            "hardwareRenderingGlobals.motionBlurEnable": "motion_blur_disabled",
                        }.get(attr)
                        if report_key:
                            report[report_key] = True
            except Exception:
                if screen_space_patterns:
                    raise RuntimeError(
                        "Screen-space pattern capture could not disable {0}.".format(
                            attr
                        )
                    )
    if marker_mode or depth_mode:
        # Character markers use Lambert, so the marker playblast must use
        # Maya's Default Lighting with smooth shaded/textured rendering. The
        # camera-depth Surface Shader uses the same textured render mode but is
        # independent of the lighting result.
        for attr, value in (
            ("hardwareRenderingGlobals.lightingMode", 0),
            ("hardwareRenderingGlobals.renderMode", 4),
        ):
            try:
                if cmds.objExists(attr):
                    cmds.setAttr(attr, value)
            except Exception:
                pass
    if screen_space_patterns or depth_mode:
        try:
            cmds.colorManagementPrefs(
                edit=True,
                outputTarget="renderer",
                outputTransformEnabled=False,
            )
            if bool(
                cmds.colorManagementPrefs(
                    query=True,
                    outputTarget="renderer",
                    outputTransformEnabled=True,
                )
            ):
                raise RuntimeError("output transform remained enabled")
            report["output_transform_disabled"] = True
        except Exception as exc:
            raise RuntimeError(
                "Raw marker/depth values require Maya's renderer output "
                "transform to be disabled ({0}).".format(exc)
            )
        missing = [
            key
            for key in (
                "multisample_disabled",
                "line_aa_disabled",
                "ssao_disabled",
                "motion_blur_disabled",
            )
            if not report.get(key)
        ]
        if missing:
            raise RuntimeError(
                "Raw marker/depth render options were not verified: "
                "{0}.".format(", ".join(missing))
            )
    if depth_mode:
        for attr, report_key in (
            (
                "hardwareRenderingGlobals.renderDepthOfField",
                "depth_of_field_disabled",
            ),
            ("hardwareRenderingGlobals.hwFogEnable", "fog_disabled"),
        ):
            try:
                if not cmds.objExists(attr):
                    raise RuntimeError("attribute is unavailable")
                cmds.setAttr(attr, 0)
                if int(cmds.getAttr(attr)) != 0:
                    raise RuntimeError("attribute remained enabled")
                report[report_key] = True
            except Exception as exc:
                raise RuntimeError(
                    "Raw depth capture could not disable {0} ({1}).".format(
                        attr,
                        exc,
                    )
                )
    try:
        cmds.setAttr("defaultRenderGlobals.imageFormat", 32)
        cmds.setAttr("defaultRenderGlobals.animation", 0)
        cmds.setAttr("defaultRenderGlobals.putFrameBeforeExt", 1)
        cmds.setAttr("defaultRenderGlobals.extensionPadding", 6)
    except Exception:
        pass
    return report


def _snapshot_files(folder):
    result = {}
    if not os.path.isdir(folder):
        return result
    for root, _, files in os.walk(folder):
        for filename in files:
            path = os.path.join(root, filename)
            try:
                result[path] = os.path.getmtime(path)
            except OSError:
                pass
    return result


def _newest_rendered_file(folder, before, started_at):
    candidates = []
    for root, _, files in os.walk(folder):
        for filename in files:
            path = os.path.join(root, filename)
            extension = os.path.splitext(filename)[1].lower()
            if extension not in (".png", ".iff", ".tif", ".tiff", ".jpg", ".jpeg", ".exr"):
                continue
            try:
                modified = os.path.getmtime(path)
            except OSError:
                continue
            if path not in before or modified > before.get(path, 0.0):
                if modified >= started_at - 2.0:
                    candidates.append((modified, path))
    if not candidates:
        return ""
    candidates.sort()
    return candidates[-1][1]


def _rendered_file_for_unique_prefix(folder, prefix, started_at):
    """Find only this frame's unique ogsRender output.

    The previous implementation snapshotted every file under the Maya images
    tree before every frame, producing O(frames * project_files) directory IO.
    """
    candidates = []
    if not os.path.isdir(folder):
        return ""
    for root, _, files in os.walk(folder):
        for filename in files:
            if not filename.startswith(prefix):
                continue
            extension = os.path.splitext(filename)[1].lower()
            if extension not in (".png", ".iff", ".tif", ".tiff", ".jpg", ".jpeg", ".exr"):
                continue
            path = os.path.join(root, filename)
            try:
                modified = os.path.getmtime(path)
            except OSError:
                continue
            if modified >= started_at - 2.0:
                candidates.append((modified, path))
    if not candidates:
        return ""
    candidates.sort()
    return candidates[-1][1]


def _render_frames(
    camera,
    frame_values,
    width,
    height,
    frames_folder,
    output_name,
    job=None,
    progress_stage="rendering_frames",
    pre_frame_callback=None,
    post_frame_callback=None,
):
    if os.path.isdir(frames_folder):
        if _is_reparse_or_symlink(frames_folder):
            raise RuntimeError(
                "Refusing to replace a linked frame directory: {0}".format(
                    frames_folder
                )
            )
        shutil.rmtree(frames_folder)
    os.makedirs(frames_folder)
    capture_folder = os.path.join(frames_folder, "_capture")
    os.makedirs(capture_folder)

    camera_shape = (cmds.listRelatives(camera, shapes=True, fullPath=True, type="camera") or [camera])[0]
    output_paths = []
    frame_map = []
    workspace_root = _clean(cmds.workspace(query=True, rootDirectory=True))
    original_images_rule = _clean(cmds.workspace(fileRuleEntry="images"))
    original_render_root = (
        original_images_rule
        if os.path.isabs(original_images_rule)
        else os.path.join(workspace_root, original_images_rule or "images")
    )
    render_roots = [capture_folder]
    if os.path.abspath(original_render_root) != os.path.abspath(capture_folder):
        render_roots.append(original_render_root)
    try:
        # imageFilePrefix is a Maya workspace-relative field. Supplying an
        # absolute Windows path makes ogsRender prepend the project images folder
        # and render layer, yielding an invalid path such as images/layer/C:/....
        # Redirect the in-memory images rule instead and use a unique relative
        # prefix. The source scene and workspace file are never saved.
        try:
            cmds.workspace(fileRule=["images", capture_folder.replace("\\", "/")])
        except Exception:
            pass
        frame_count = len(frame_values)
        for index, frame in enumerate(frame_values):
            progress_index = index + 1
            capture_prefix = "hmbvp_{0}_{1}_{2:06d}".format(
                os.getpid(),
                int(time.time() * 1000),
                index,
            )
            _write_progress(
                job,
                progress_stage,
                "Rendering frame {0} of {1} (Maya frame {2}).".format(
                    progress_index, frame_count, frame
                ),
                frame_status="started",
                frame_index=progress_index,
                completed_frames=index,
                frame_count=frame_count,
                maya_frame=frame,
            )
            cmds.setAttr("defaultRenderGlobals.imageFilePrefix", capture_prefix, type="string")
            cmds.currentTime(frame, edit=True, update=True)
            started_at = time.time()
            try:
                if pre_frame_callback is not None:
                    pre_frame_callback(frame, index, frame_count)
                render_options = {
                    "camera": camera_shape,
                    "frame": float(frame),
                    "width": int(width),
                    "height": int(height),
                    "noRenderView": True,
                }
                if bool((job or {}).get("screen_space_patterns")):
                    render_options["enableMultisample"] = False
                ok = cmds.ogsRender(
                    **render_options
                )
                if ok is False:
                    raise RuntimeError(
                        "ogsRender returned False at frame {0}".format(frame)
                    )
            except _MouthCardRestorationError:
                raise
            except Exception as exc:
                raise RuntimeError(
                    "Frame preparation/render failed at Maya frame {0}: "
                    "{1}".format(frame, exc)
                )
            finally:
                if post_frame_callback is not None:
                    try:
                        post_frame_callback(frame, index, frame_count)
                    except _MouthCardRestorationError:
                        raise
                    except Exception as exc:
                        raise RuntimeError(
                            "Post-frame restoration failed at Maya frame {0}: "
                            "{1}".format(frame, exc)
                        )
            source = ""
            for render_root in render_roots:
                source = _rendered_file_for_unique_prefix(
                    render_root, capture_prefix, started_at
                )
                if source:
                    break
            if not source:
                raise RuntimeError("No image file was produced at frame {0}".format(frame))
            target = os.path.join(frames_folder, "{0}.{1:06d}.png".format(output_name, index))
            extension = os.path.splitext(source)[1].lower()
            if extension != ".png":
                raise RuntimeError(
                    "Maya produced {0}; PNG was required for deterministic FFmpeg input.".format(source)
                )
            if os.path.abspath(source) != os.path.abspath(target):
                if os.path.exists(target):
                    os.remove(target)
                shutil.move(source, target)
            output_paths.append(target)
            frame_map.append({"sequence_index": index, "maya_frame": frame, "file": os.path.basename(target)})
            _write_progress(
                job,
                progress_stage,
                "Rendered frame {0} of {1} (Maya frame {2}).".format(
                    progress_index, frame_count, frame
                ),
                frame_status="completed",
                frame_index=progress_index,
                completed_frames=progress_index,
                frame_count=frame_count,
                maya_frame=frame,
                output_file=os.path.basename(target),
            )
    finally:
        try:
            if original_images_rule:
                cmds.workspace(fileRule=["images", original_images_rule])
        except Exception:
            pass
        if _is_reparse_or_symlink(capture_folder):
            raise RuntimeError(
                "Refusing cleanup of a linked Maya capture directory: {0}".format(
                    capture_folder
                )
            )
        shutil.rmtree(capture_folder, ignore_errors=True)
    return output_paths, frame_map


def _render_depth_pass(
    camera,
    frame_values,
    width,
    height,
    frames_folder,
    output_name,
    job,
):
    """Render one camera-depth sequence without reopening or saving the scene."""
    _write_progress(
        job,
        "preparing_depth",
        "Applying the camera-space grayscale depth shader.",
        depth_profile=DEPTH_PLAYBLAST_PROFILE,
    )
    mouth_controller = _MouthCardInnerPatchController(job, "depth")
    job["_mouth_inner_patch_depth_controller"] = mouth_controller
    range_report = {}
    output_paths = []
    frame_map = []
    try:
        mouth_controller.activate_static_depth_exclusions()
        range_report, assign_depth_frame = _apply_depth_shader(
            camera,
            job,
            frame_values=frame_values,
            width=width,
            height=height,
        )
        render_options_report = _set_viewport_render_options(
            marker_mode=False,
            preserve_authored_look=False,
            screen_space_patterns=False,
            depth_mode=True,
        )
        _write_progress(
            job,
            "rendering_depth_frames",
            "Rendering camera-space depth frames with the existing scene, camera, visibility, and Smooth Preview state.",
            frame_count=len(frame_values),
            completed_frames=0,
            depth_profile=DEPTH_PLAYBLAST_PROFILE,
        )
        depth_job = dict(job or {})
        # Keep categorical/depth values free from VP2 multisample blending.
        depth_job["screen_space_patterns"] = True

        def prepare_depth_frame(frame, frame_index=None, frame_count=None):
            # The current depth SG must exist on the source before duplication.
            previously_excluded = set(
                mouth_controller.dynamic_depth_excluded
            )
            assign_depth_frame(frame, frame_index, frame_count)
            mouth_controller.prepare_frame(frame, frame_index, frame_count)
            newly_excluded = sorted(
                mouth_controller.dynamic_depth_excluded.difference(
                    previously_excluded
                )
            )
            if newly_excluded:
                actual_assignments = {}
                for shape in newly_excluded:
                    group = mouth_controller.depth_assignment_group(shape)
                    if not group or not _display_layer_hidden(shape)[0]:
                        raise RuntimeError(
                            "Depth runtime mouth exclusion was not active."
                        )
                    actual_assignments[shape] = group
                verified = _verify_depth_shader_assignment(actual_assignments)
                if int(verified.get("verified_shape_path_count") or 0) != len(
                    actual_assignments
                ):
                    raise RuntimeError(
                        "Depth runtime mouth exclusion verification was incomplete."
                    )
                mouth_controller.report[
                    "runtime_exclusion_verified_shape_path_count"
                ] += len(actual_assignments)

        output_paths, frame_map = _render_frames(
            camera=camera,
            frame_values=frame_values,
            width=width,
            height=height,
            frames_folder=frames_folder,
            output_name=output_name,
            job=depth_job,
            progress_stage="rendering_depth_frames",
            pre_frame_callback=prepare_depth_frame,
            post_frame_callback=mouth_controller.restore_frame,
        )
        finalize_cutout_report = getattr(
            assign_depth_frame,
            "finalize_cutout_report",
            None,
        )
        if finalize_cutout_report is not None:
            finalize_cutout_report()
    finally:
        try:
            mouth_report = mouth_controller.finish()
            job["_mouth_inner_patch_depth_report"] = mouth_report
            if isinstance(range_report, dict):
                range_report["mouth_card_inner_patch"] = mouth_report
        finally:
            job.pop("_mouth_inner_patch_depth_controller", None)
            job.pop("_mouth_depth_excluded_shape_paths", None)
    assignment_verification = range_report.get("assignment_verification") or {}
    rendered_frame_count = len(output_paths)
    shape_path_count = int(
        assignment_verification.get("shape_path_count") or 0
    )
    expected_assignment_count = rendered_frame_count * shape_path_count
    if (
        int(assignment_verification.get("rendered_frame_count") or 0)
        != rendered_frame_count
        or int(
            assignment_verification.get("expected_frame_assignment_count")
            or 0
        ) != expected_assignment_count
        or int(
            assignment_verification.get("verified_frame_assignment_count")
            or 0
        ) != expected_assignment_count
    ):
        raise RuntimeError(
            "Depth frame assignment verification was incomplete: rendered "
            "{0}/{1} frame(s), verified {2}/{3} shape assignments.".format(
                int(
                    assignment_verification.get("rendered_frame_count") or 0
                ),
                rendered_frame_count,
                int(
                    assignment_verification.get(
                        "verified_frame_assignment_count"
                    ) or 0
                ),
                expected_assignment_count,
            )
        )
    range_report["render_options"] = render_options_report
    return output_paths, frame_map, range_report


def _motion_path_visible(path):
    """Evaluate the same Maya DAG/layer visibility used by the rendered passes."""
    path = _clean(path)
    if not path or not cmds.objExists(path):
        return False
    for node in _dag_path_nodes(path):
        if not _bool_attr(node, "visibility", True):
            return False
        if not _bool_attr(node, "lodVisibility", True):
            return False
        if _bool_attr(node, "template", False):
            return False
        if (
            _bool_attr(node, "overrideEnabled", False)
            and not _bool_attr(node, "overrideVisibility", True)
        ):
            return False
        if _display_layer_hidden(node)[0]:
            return False
    return True


def _motion_perf_increment(performance, key, amount=1):
    """Increment an optional deterministic Motion Guide work counter."""
    if not isinstance(performance, dict):
        return
    performance[key] = int(performance.get(key) or 0) + int(amount)


def _motion_cached_path_visible(path, cache, performance=None):
    """Evaluate one DAG path at most once inside the caller's current frame."""
    key = _clean(path)
    if key in cache:
        _motion_perf_increment(
            performance,
            "path_visibility_cache_hit_count",
        )
        return bool(cache[key])
    _motion_perf_increment(
        performance,
        "path_visibility_cache_miss_count",
    )
    visible = bool(_motion_path_visible(key))
    cache[key] = visible
    return visible


def _motion_target_visible(target, path_visible, performance=None):
    """Preserve target visibility while avoiding unnecessary shape queries."""
    root = _clean((target or {}).get("source_root"))
    if not path_visible(root):
        _motion_perf_increment(
            performance,
            "target_root_short_circuit_count",
        )
        return False
    shapes = list((target or {}).get("shapes") or [])
    if not shapes:
        return True
    for index, shape in enumerate(shapes):
        _motion_perf_increment(
            performance,
            "target_shape_visibility_check_count",
        )
        if path_visible(shape):
            if index + 1 < len(shapes):
                _motion_perf_increment(
                    performance,
                    "target_shape_any_short_circuit_count",
                )
            return True
    return False


def _motion_reference_node(path):
    try:
        if cmds.referenceQuery(path, isNodeReferenced=True):
            return _clean(cmds.referenceQuery(path, referenceNode=True))
    except Exception:
        pass
    return ""


def _motion_joint_priority(path):
    leaf = _dag_leaf_without_namespace(path).lower()
    core = (
        "root", "cog", "center", "centre", "pelvis", "hip", "spine",
        "chest", "neck", "head", "clav", "shoulder", "arm", "elbow",
        "wrist", "hand", "leg", "knee", "ankle", "foot", "toe",
        "tail", "wing", "jaw",
    )
    micro = (
        "eye", "eyelid", "lash", "brow", "lip", "mouth", "tongue",
        "tooth", "teeth", "cheek", "nose", "follicle", "hair",
    )
    if any(token in leaf for token in core):
        return 0
    if any(token in leaf for token in micro):
        return 3
    if any(token in leaf for token in ("finger", "thumb", "index", "middle", "ring", "pinky")):
        return 2
    return 1


def _motion_joint_name_tokens(path):
    leaf = _dag_leaf_without_namespace(path)
    leaf = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", leaf)
    return set(
        token
        for token in re.split(r"[^A-Za-z0-9]+", leaf.lower())
        if token
    )


def _motion_joint_exclusion_reason(path):
    """Exclude rig implementation detail from the pixel control skeleton."""
    tokens = _motion_joint_name_tokens(path)
    leaf = _dag_leaf_without_namespace(path).lower()
    compact_leaf = re.sub(r"[^a-z0-9]+", "", leaf)
    compact_path = re.sub(r"[^a-z0-9]+", "", _clean(path).lower())
    face_detail = {
        "eye", "eyes", "eyelid", "eyelids", "lid", "lids", "lash",
        "lashes", "brow", "brows", "eyebrow", "eyebrows", "lip", "lips",
        "mouth", "jaw", "tongue", "tooth", "teeth", "cheek", "cheeks", "nose",
        "nostril", "nostrils", "smile", "sticky", "follicle", "hair",
        "face", "facial", "wrinkle", "freshy", "forehead", "bstarget",
        "bstargets",
    }
    if tokens.intersection(face_detail) or any(
        marker in compact_leaf
        for marker in (
            "alllip", "facialkey", "bstarget", "eyelid", "eyebrow",
            "pupil", "nostril", "wrinkle", "forehead", "mouthcorner",
        )
    ) or any(
        marker in compact_path
        for marker in (
            "facialallrig", "facialrig", "stickyliprig", "lidbrowrig",
            "browrig", "noserig", "bstarget", "blendshape",
        )
    ):
        return "micro_facial_detail"
    # Some production deformation rigs expose only the first weighted twist
    # sample for an upper/lower limb segment.  Retain that one representative
    # point, while removing the remaining dense twist chain.
    representative_limb_twist = bool(
        "twist" in compact_leaf
        and "untwist" not in compact_leaf
        and re.search(r"twist[_-]?0(?:_|$)", leaf)
    )
    rig_detail = {
        "ik", "fk", "ikfk", "twist", "untwist", "nonroll", "roll",
        "helper", "offset", "driver", "driven", "corrective", "effector",
        "pole", "pv", "aim", "sdk", "value", "dummy", "pose",
        "end", "tip", "orig", "original",
    }
    if (
        (tokens.intersection(rig_detail) and not representative_limb_twist)
        or ("twist" in compact_leaf and not representative_limb_twist)
        or re.search(r"(?:^|_)(?:ik|fk)[a-z0-9]*", leaf)
        or re.search(r"(?:^|_)(?:end|tip)\d*(?:_|$)", leaf)
        or any(
            marker in compact_leaf
            for marker in ("nonroll", "twistbalancer")
        )
    ):
        return "rig_helper_detail"
    finger_detail = {
        "finger", "fingers", "thumb", "index", "middle", "ring", "pinky",
    }
    if tokens.intersection(finger_detail):
        return "finger_detail"
    accessory_detail = {
        "sleeve", "shirt", "cloth", "skirt", "accessory", "garment",
    }
    if tokens.intersection(accessory_detail) or "beltsub" in compact_path:
        return "accessory_detail"
    return ""


def _motion_duplicate_alias_key(path):
    """Return the core leaf name for common duplicate display skeleton aliases."""
    leaf = _dag_leaf_without_namespace(path).lower()
    if leaf.startswith("sk_"):
        return leaf[3:]
    return ""


def _motion_skin_influence_joints(shapes):
    joints = []
    skin_clusters = []
    for shape in shapes or []:
        try:
            history = cmds.listHistory(
                shape,
                pruneDagObjects=True,
            ) or []
            clusters = cmds.ls(history, type="skinCluster") or []
        except Exception:
            clusters = []
        for cluster in clusters:
            cluster = _clean(cluster)
            if not cluster or cluster in skin_clusters:
                continue
            skin_clusters.append(cluster)
            try:
                influences = cmds.skinCluster(
                    cluster,
                    query=True,
                    weightedInfluence=True,
                ) or []
            except Exception:
                try:
                    influences = cmds.skinCluster(
                        cluster,
                        query=True,
                        influence=True,
                    ) or []
                except Exception:
                    influences = []
            joints.extend(_long_names(influences))
    return sorted(set(joints)), sorted(set(skin_clusters))


def _motion_reference_or_namespace_joints(root):
    reference_node = _motion_reference_node(root)
    namespace = _namespace_from_leaf(_clean(root).split("|")[-1])
    result = []
    try:
        scene_joints = _long_names(cmds.ls(type="joint", long=True) or [])
    except Exception:
        scene_joints = []
    for joint in scene_joints:
        include = False
        if reference_node:
            include = _motion_reference_node(joint) == reference_node
        elif namespace:
            include = _namespace_from_leaf(
                _clean(joint).split("|")[-1]
            ) == namespace
        if include:
            result.append(joint)
    return sorted(set(result))


def _motion_joint_selection(
    root,
    shapes=None,
    allow_skeleton=True,
    allow_reference_fallback=False,
):
    if not allow_skeleton:
        return [], {
            "source": "background_marker_rigid_transform",
            "raw_joint_count": 0,
            "selected_joint_count": 0,
            "excluded_joint_count": 0,
            "excluded_by_reason": {},
            "skin_cluster_count": 0,
            "truncated_joint_count": 0,
            "connected_edge_count": 0,
            "semantic_root_count": 0,
            "structural_fallback_reasons": [],
        }
    influence_joints, skin_clusters = _motion_skin_influence_joints(shapes)
    direct = cmds.listRelatives(
        root,
        allDescendents=True,
        type="joint",
        fullPath=True,
    ) or []
    direct_joints = list(_long_names(direct))
    try:
        if cmds.nodeType(root) == "joint":
            direct_joints.append(_long_names([root])[0])
    except Exception:
        pass
    candidates = list(influence_joints or direct_joints)
    source = (
        "weighted_skin_cluster_influences"
        if influence_joints
        else "direct_descendant_joint_fallback"
    )

    def filtered_candidates(raw_candidates, candidate_source):
        normalized = sorted(set(
            _clean(item) for item in raw_candidates if _clean(item)
        ))
        candidate_leaf_names = {
            _dag_leaf_without_namespace(item).lower()
            for item in normalized
        }
        non_alias_candidate_count = sum(
            1
            for item in normalized
            if not _motion_duplicate_alias_key(item)
            and not _motion_joint_exclusion_reason(item)
        )
        excluded = {}
        retained = []
        for joint in normalized:
            reason = _motion_joint_exclusion_reason(joint)
            duplicate_alias = _motion_duplicate_alias_key(joint)
            if not reason and duplicate_alias and (
                duplicate_alias in candidate_leaf_names
                or (
                    candidate_source.startswith("character_reference")
                    and non_alias_candidate_count >= 6
                )
            ):
                reason = "duplicate_skeleton_detail"
            if reason:
                excluded[reason] = int(excluded.get(reason) or 0) + 1
                continue
            retained.append(joint)
        retained = sorted(
            retained,
            key=lambda item: (
                _motion_joint_priority(item),
                _dag_depth(item),
                item,
            ),
        )
        return normalized, retained, excluded

    def structure_evidence(retained):
        retained_set = set(retained)
        connected_edges = sum(
            1
            for joint in retained
            if _motion_nearest_selected_parent(joint, retained_set)
        )
        semantic_root_tokens = (
            "root", "cog", "center", "centre", "pelvis", "hips", "hip",
        )
        semantic_roots = sum(
            1
            for joint in retained
            if any(
                token in _dag_leaf_without_namespace(joint).lower()
                for token in semantic_root_tokens
            )
        )
        return {
            "connected_edge_count": connected_edges,
            "semantic_root_count": semantic_roots,
        }

    candidates, selected, excluded_by_reason = filtered_candidates(
        candidates,
        source,
    )
    pre_fallback_structure = structure_evidence(selected)
    structural_fallback_reasons = []
    if len(selected) < 6:
        structural_fallback_reasons.append("fewer_than_six_core_joints")
    if len(selected) > 1 and not pre_fallback_structure["connected_edge_count"]:
        structural_fallback_reasons.append("no_connected_joint_edges")
    if not pre_fallback_structure["semantic_root_count"]:
        structural_fallback_reasons.append("no_semantic_root_joint")
    should_expand_reference = bool(
        allow_reference_fallback
        and (
            len(selected) < 6
            or not pre_fallback_structure["semantic_root_count"]
            or (
                len(selected) > 1
                and not pre_fallback_structure["connected_edge_count"]
            )
        )
    )
    if should_expand_reference:
        reference_joints = _motion_reference_or_namespace_joints(root)
        expanded = sorted(set(candidates).union(reference_joints))
        if len(expanded) > len(candidates):
            source = (
                "character_reference_joint_fallback"
                if len(selected) < 6
                else "character_reference_structural_fallback"
            )
            candidates, selected, excluded_by_reason = filtered_candidates(
                expanded,
                source,
            )
    truncated_joint_count = max(
        0,
        len(selected) - MOTION_GUIDE_MAX_JOINTS_PER_TARGET,
    )
    if truncated_joint_count:
        selected = selected[:MOTION_GUIDE_MAX_JOINTS_PER_TARGET]
    final_structure = structure_evidence(selected)
    return selected, {
        "source": source,
        "raw_joint_count": len(candidates),
        "selected_joint_count": len(selected),
        "excluded_joint_count": sum(excluded_by_reason.values()),
        "excluded_by_reason": excluded_by_reason,
        "skin_cluster_count": len(skin_clusters),
        "truncated_joint_count": truncated_joint_count,
        "connected_edge_count": final_structure["connected_edge_count"],
        "semantic_root_count": final_structure["semantic_root_count"],
        "pre_fallback_selected_joint_count": len(
            filtered_candidates(
                influence_joints or direct_joints,
                (
                    "weighted_skin_cluster_influences"
                    if influence_joints
                    else "direct_descendant_joint_fallback"
                ),
            )[1]
        ),
        "pre_fallback_connected_edge_count": (
            pre_fallback_structure["connected_edge_count"]
        ),
        "pre_fallback_semantic_root_count": (
            pre_fallback_structure["semantic_root_count"]
        ),
        "structural_fallback_reasons": structural_fallback_reasons,
    }


def _motion_joint_paths(
    root,
    shapes=None,
    allow_skeleton=True,
    allow_reference_fallback=False,
):
    return _motion_joint_selection(
        root,
        shapes=shapes,
        allow_skeleton=allow_skeleton,
        allow_reference_fallback=allow_reference_fallback,
    )[0]


def _motion_target_shapes(root, job=None):
    root = _clean(root)
    scoped_by_root = (
        (job or {}).get("_render_scope_binding_shapes")
        if isinstance((job or {}).get("_render_scope_binding_shapes"), dict)
        else {}
    )
    if root in scoped_by_root:
        return sorted(set(_clean(item) for item in scoped_by_root[root] if _clean(item)))
    try:
        descendants = _marker_renderable_shapes(_descendant_shapes(root))
    except Exception:
        descendants = []
    allowed = set(
        _clean(item)
        for item in ((job or {}).get("_render_scope_shapes") or [])
        if _clean(item)
    )
    if allowed:
        descendants = [item for item in descendants if item in allowed]
    return sorted(set(descendants))


def _motion_face_name_tokens(value):
    text = _clean(value)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return [
        token
        for token in re.split(r"[^A-Za-z0-9]+", text.lower())
        if token
    ]


def _motion_face_semantic(alias, node=""):
    """Classify a face channel without discarding its authored alias."""
    alias_text = _clean(alias)
    node_text = _clean(node)
    tokens = _motion_face_name_tokens(alias_text)
    token_set = set(tokens)
    compact = re.sub(
        r"[^a-z0-9]+",
        "",
        (alias_text + " " + node_text).lower(),
    )
    alias_compact = re.sub(r"[^a-z0-9]+", "", alias_text.lower())
    if any(token in token_set for token in ("tongue", "teeth", "tooth")):
        return {
            "group": "unknown",
            "side": "center",
            "action": "raw",
            "raster_eligible": False,
        }

    group = "unknown"
    if any(
        marker in compact
        for marker in ("eyebrow", "brow", "forehead")
    ):
        group = "brow"
    elif any(
        marker in compact
        for marker in (
            "eyelid", "upeye", "loweye", "blink", "squint",
            "eyeclose", "eyeopen",
        )
    ) or token_set.intersection(("eye", "eyes", "lid", "lids")):
        group = "eyelid"
    elif "jaw" in compact:
        group = "jaw"
    elif (
        any(
            marker in compact
            for marker in (
                "mouth", "lip", "smile", "frown", "phoneme",
                "viseme", "narrow", "wide",
            )
        )
        or alias_compact in {
            "ma", "me", "mi", "mo", "mu", "mm", "mf", "mv", "ml",
        }
        or re.match(r"^m[aeioumfvl]", alias_compact)
    ):
        group = "mouth"

    side = "center"
    if (
        "left" in compact
        or "l" in token_set
        or re.search(r"(?:^|[_-])l(?:[_-]|$)", alias_text.lower())
        or alias_text.lower().startswith("l_")
    ):
        side = "left"
    elif (
        "right" in compact
        or "r" in token_set
        or re.search(r"(?:^|[_-])r(?:[_-]|$)", alias_text.lower())
        or alias_text.lower().startswith("r_")
    ):
        side = "right"

    action = "raw"
    action_markers = (
        ("close", ("blink", "close", "closed")),
        ("open", ("open", "jawopen")),
        ("smile", ("smile", "happy")),
        ("frown", ("frown", "sad")),
        ("narrow", ("narrow", "pucker")),
        ("wide", ("wide", "stretch")),
        ("squeeze", ("squeeze", "squint", "angry")),
        ("up", ("_up", "up_", "raise")),
        ("down", ("_dn", "dn_", "down", "lower")),
        ("in", ("_in", "in_", "inner")),
        ("out", ("_out", "out_", "outer")),
    )
    lowered_alias = alias_text.lower()
    for candidate, markers in action_markers:
        if any(marker in lowered_alias for marker in markers):
            action = candidate
            break
    if action == "raw":
        phoneme = re.match(r"^m[_-]?([aeioumfvl])(?:$|[_-])", lowered_alias)
        if phoneme:
            action = "phoneme_" + phoneme.group(1)
    return {
        "group": group,
        "side": side,
        "action": action,
        "raster_eligible": group in {"brow", "eyelid", "mouth", "jaw"},
    }


def _motion_face_node_uuid(node):
    try:
        values = cmds.ls(node, uuid=True) or []
    except Exception:
        values = []
    return _clean(values[0]) if values else _clean(node)


def _motion_face_plug_is_numeric(plug):
    plug = _clean(plug)
    if not plug or "." not in plug:
        return False
    attribute = plug.split(".", 1)[1].lower()
    if any(
        marker in attribute
        for marker in (
            "message", "matrix", "instobjgroups", "drawoverride",
            "visibility", "pivot", "rotateorder",
        )
    ):
        return False
    try:
        value_type = _clean(cmds.getAttr(plug, type=True)).lower()
    except Exception:
        value_type = ""
    if value_type:
        return value_type in {
            "bool", "byte", "short", "long", "float", "double",
            "doublelinear", "doubleangle", "time", "enum",
        }
    return True


def _motion_face_controller_node(node):
    node = _clean(node)
    if not node:
        return False
    try:
        node_type = _clean(cmds.nodeType(node))
    except Exception:
        node_type = ""
    if node_type not in {"transform", "joint"}:
        return False
    lowered = _dag_leaf_without_namespace(node).lower()
    if any(
        marker in lowered
        for marker in (
            "facialwindow", "bstarget", "picker", "dashboard", "posepanel",
        )
    ):
        return False
    try:
        curve_shapes = cmds.listRelatives(
            node,
            shapes=True,
            noIntermediate=True,
            type="nurbsCurve",
            fullPath=True,
        ) or []
    except Exception:
        curve_shapes = []
    return bool(curve_shapes) or any(
        marker in lowered for marker in ("_ctl", "_ctrl", "control")
    )


def _motion_face_incoming_plugs(value):
    try:
        values = cmds.listConnections(
            value,
            source=True,
            destination=False,
            plugs=True,
            skipConversionNodes=False,
        ) or []
    except Exception:
        values = []
    return sorted(set(_clean(item) for item in values if _clean(item)))


def _motion_face_driver_plugs(weight_plug):
    """Trace exact numeric inputs through a bounded set of DG utilities."""
    allowed_utility_types = {
        "unitConversion", "addDoubleLinear", "multDoubleLinear",
        "plusMinusAverage", "multiplyDivide", "reverse", "clamp",
        "remapValue", "blendWeighted", "condition", "pairBlend", "choice",
        "setRange",
    }
    queue = [
        (plug, 1)
        for plug in _motion_face_incoming_plugs(weight_plug)
    ]
    visited = set()
    controls = []
    while queue and len(visited) < 128:
        source_plug, depth = queue.pop(0)
        if source_plug in visited or depth > 6:
            continue
        visited.add(source_plug)
        if not _motion_face_plug_is_numeric(source_plug):
            continue
        source_node = source_plug.split(".", 1)[0]
        try:
            node_type = _clean(cmds.nodeType(source_node))
        except Exception:
            node_type = ""
        if _motion_face_controller_node(source_node):
            controls.append(source_plug)
            # A control attribute can itself be driven. Preserve it as the
            # provenance value, but also follow that exact plug only.
            for upstream in _motion_face_incoming_plugs(source_plug):
                queue.append((upstream, depth + 1))
            continue
        if node_type.startswith("animCurve") or node_type in allowed_utility_types:
            for upstream in _motion_face_incoming_plugs(source_node):
                queue.append((upstream, depth + 1))
            continue
        # Custom numeric bridge attributes are common in production face rigs.
        # Follow only the exact plug; never fan into every transform input.
        if node_type in {"transform", "joint", "network"}:
            for upstream in _motion_face_incoming_plugs(source_plug):
                queue.append((upstream, depth + 1))
    return sorted(set(controls))[:16]


def _motion_face_target_controller_nodes(root):
    """Return semantic curve controls confined to the selected target scope."""
    reference_node = _motion_reference_node(root)
    namespace = _namespace_from_leaf(_clean(root).split("|")[-1])
    try:
        transforms = _long_names(cmds.ls(type="transform", long=True) or [])
    except Exception:
        transforms = []
    result = []
    for node in transforms:
        include = False
        if reference_node:
            include = _motion_reference_node(node) == reference_node
        elif namespace:
            include = _namespace_from_leaf(
                _clean(node).split("|")[-1]
            ) == namespace
        else:
            include = bool(
                node == root or node.startswith(_clean(root).rstrip("|") + "|")
            )
        if not include:
            continue
        leaf = _dag_leaf_without_namespace(node)
        compact = re.sub(r"[^a-z0-9]+", "", leaf.lower())
        if any(
            marker in compact
            for marker in (
                "dummy", "target", "cage", "posepanel", "picker",
                "dashboard", "facialwindow",
            )
        ):
            continue
        semantic = _motion_face_semantic(leaf, node)
        if semantic["group"] not in {"brow", "eyelid", "mouth", "jaw"}:
            continue
        if _motion_face_controller_node(node):
            result.append(node)
    return sorted(set(result))


def _motion_face_keyed_plug_evidence(plug):
    """Prove that a numeric control plug is authored by animation upstream."""
    try:
        direct_key_count = int(
            cmds.keyframe(plug, query=True, keyframeCount=True) or 0
        )
    except Exception:
        direct_key_count = 0
    if direct_key_count > 0:
        return {
            "source": "direct_keyframes",
            "key_count": direct_key_count,
            "animation_nodes": [],
        }
    queue = [(item, 1) for item in _motion_face_incoming_plugs(plug)]
    visited = set()
    animation_nodes = set()
    allowed_utility_types = {
        "unitConversion", "addDoubleLinear", "multDoubleLinear",
        "plusMinusAverage", "multiplyDivide", "reverse", "clamp",
        "remapValue", "blendWeighted", "condition", "pairBlend", "choice",
        "setRange",
    }
    while queue and len(visited) < 128:
        source_plug, depth = queue.pop(0)
        if source_plug in visited or depth > 6:
            continue
        visited.add(source_plug)
        source_node = source_plug.split(".", 1)[0]
        try:
            node_type = _clean(cmds.nodeType(source_node))
        except Exception:
            node_type = ""
        if node_type.startswith("animCurve"):
            animation_nodes.add(source_node)
            continue
        if node_type in allowed_utility_types:
            for upstream in _motion_face_incoming_plugs(source_node):
                queue.append((upstream, depth + 1))
    if not animation_nodes:
        return None
    return {
        "source": "upstream_anim_curve",
        "key_count": 0,
        "animation_nodes": sorted(animation_nodes),
    }


def _motion_face_keyed_semantic_drivers(root, existing_drivers=None):
    """Collect target-local keyed face controls without drawing their curves."""
    retained = []
    existing_plugs = set(
        _clean(item.get("plug"))
        for item in (existing_drivers or [])
        if _clean(item.get("plug"))
    )
    existing_ids = set(
        _clean(item.get("id"))
        for item in (existing_drivers or [])
        if _clean(item.get("id"))
    )
    controller_count = 0
    candidate_plug_count = 0
    rejected_nonanimated_count = 0
    for node in _motion_face_target_controller_nodes(root):
        controller_count += 1
        try:
            attributes = cmds.listAttr(
                node,
                keyable=True,
                scalar=True,
            ) or []
        except Exception:
            try:
                attributes = cmds.listAttr(node, keyable=True) or []
            except Exception:
                attributes = []
        control_semantic = _motion_face_semantic(
            _dag_leaf_without_namespace(node),
            node,
        )
        for attribute in sorted(set(_clean(item) for item in attributes)):
            if not attribute:
                continue
            plug = node + "." + attribute
            node_id = _motion_face_node_uuid(node)
            driver_id = "{0}:{1}".format(node_id, attribute)
            if (
                plug in existing_plugs
                or driver_id in existing_ids
                or not _motion_face_plug_is_numeric(plug)
            ):
                continue
            candidate_plug_count += 1
            evidence = _motion_face_keyed_plug_evidence(plug)
            if not evidence:
                rejected_nonanimated_count += 1
                continue
            if _motion_face_numeric_value(plug) is None:
                continue
            semantic = _motion_face_semantic(
                _dag_leaf_without_namespace(node) + "_" + attribute,
                node,
            )
            if semantic["group"] == "unknown":
                semantic = control_semantic
            retained.append({
                "id": driver_id,
                "plug": plug,
                "node": node,
                "node_id": node_id,
                "label": _dag_leaf_without_namespace(node),
                "group": semantic["group"],
                "side": semantic["side"],
                "action": semantic["action"],
                "provenance": "target_local_keyed_semantic_controller",
                "animation_evidence": dict(evidence),
                "curve_geometry_rendered": False,
            })
            existing_plugs.add(plug)
            existing_ids.add(driver_id)
    retained.sort(key=lambda item: (
        item["group"],
        item["side"],
        item["plug"],
    ))
    return retained, {
        "keyed_semantic_controller_count": controller_count,
        "keyed_semantic_candidate_plug_count": candidate_plug_count,
        "keyed_semantic_driver_count": len(retained),
        "keyed_semantic_rejected_nonanimated_count": (
            rejected_nonanimated_count
        ),
        "policy": (
            "target_scope_semantic_curve_control_keyed_numeric_plugs_only"
        ),
        "curve_geometry_rendered": False,
    }


def _motion_face_alias_pairs(blendshape):
    try:
        raw = cmds.aliasAttr(blendshape, query=True) or []
    except Exception:
        raw = []
    pairs = []
    for index in range(0, len(raw) - 1, 2):
        alias = _clean(raw[index])
        target = _clean(raw[index + 1])
        match = re.search(r"\[(\d+)\]", target)
        if not alias or not match:
            continue
        logical_index = int(match.group(1))
        pairs.append((alias, logical_index, "{0}.weight[{1}]".format(
            blendshape,
            logical_index,
        )))
    return pairs


def _motion_face_surface_score(shape):
    lowered = _clean(shape).lower().replace("\\", "/")
    if any(
        marker in lowered
        for marker in (
            "|rig_", "|rig|", "bstarget", "bridge", "tweak", "corrective",
            "targetbank", "target_bank", "origshape", "intermediate",
        )
    ):
        return -1000
    score = 0
    leaf = _dag_leaf_without_namespace(shape).lower()
    if "face" in lowered:
        score += 12
    if "head" in lowered:
        score += 7
    if "base_geo" in lowered or "basegeo" in lowered:
        score += 5
    if "|geo" in lowered or "geometry" in lowered:
        score += 3
    if "face" in leaf:
        score += 6
    if "head" in leaf:
        score += 4
    try:
        history = cmds.listHistory(shape, pruneDagObjects=True) or []
        if cmds.ls(history, type="skinCluster") or []:
            score += 2
        if cmds.ls(history, type="blendShape") or []:
            score += 3
    except Exception:
        pass
    return score


def _motion_face_surface(shapes):
    candidates = []
    for shape in shapes or []:
        try:
            if cmds.nodeType(shape) != "mesh" or _is_intermediate_shape(shape):
                continue
        except Exception:
            continue
        candidates.append((_motion_face_surface_score(shape), _clean(shape)))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    if not candidates or candidates[0][0] < 8:
        return "", {
            "candidate_count": len(candidates),
            "selected_score": candidates[0][0] if candidates else None,
            "reason": "no_confident_visible_face_mesh",
        }
    return candidates[0][1], {
        "candidate_count": len(candidates),
        "selected_score": candidates[0][0],
        "reason": "highest_confidence_render_scope_face_mesh",
    }


def _motion_face_semantic_mesh_visibility_evidence(shape):
    authored_visible = bool(_motion_path_visible(shape))
    driven_nodes = []
    for node in _dag_path_nodes(shape):
        if _visibility_connection_kind(node):
            driven_nodes.append(_clean(node))
    return {
        "eligible": bool(authored_visible or driven_nodes),
        "authored_visible": authored_visible,
        "driven_visibility_nodes": sorted(set(driven_nodes)),
    }


def _motion_face_semantic_mesh_deformation_evidence(shape):
    """Require real mesh deformation, transform drive, or driven visibility."""
    try:
        history = cmds.listHistory(
            shape,
            pruneDagObjects=False,
        ) or []
    except Exception:
        history = []
    deformer_types = {
        "blendShape", "skinCluster", "cluster", "wire", "wrap", "ffd",
        "lattice", "nonLinear", "sculpt", "tweak", "deltaMush",
        "proximityWrap", "tension", "shrinkWrap",
    }
    deformers = []
    for node in history:
        try:
            node_type = _clean(cmds.nodeType(node))
        except Exception:
            node_type = ""
        inherited = []
        try:
            inherited = cmds.nodeType(node, inherited=True) or []
        except Exception:
            inherited = []
        if node_type in deformer_types or "geometryFilter" in inherited:
            deformers.append({
                "node": _clean(node),
                "type": node_type,
            })

    driven_transform_plugs = []
    driven_transform_nodes = []
    for transform in _dag_path_nodes(shape):
        node_driven = False
        for attribute in (
            "translateX", "translateY", "translateZ",
            "rotateX", "rotateY", "rotateZ",
            "scaleX", "scaleY", "scaleZ",
        ):
            plug = transform + "." + attribute
            if _motion_face_incoming_plugs(plug):
                driven_transform_plugs.append(plug)
                node_driven = True
        if node_driven:
            driven_transform_nodes.append(transform)
    visibility = _motion_face_semantic_mesh_visibility_evidence(shape)
    eligible = bool(
        deformers
        or driven_transform_plugs
        or visibility["driven_visibility_nodes"]
    )
    return {
        "eligible": eligible,
        "deformers": deformers,
        "driven_transform_nodes": sorted(set(driven_transform_nodes)),
        "driven_transform_plugs": sorted(set(driven_transform_plugs)),
        "driven_visibility_nodes": list(
            visibility["driven_visibility_nodes"]
        ),
    }


def _motion_face_semantic_mesh_descriptor(shape, job=None):
    """Classify a final render-scope eye/eyelid mesh with bounded evidence."""
    shape = _clean(shape)
    if not shape:
        return None, "empty_shape"
    try:
        if cmds.nodeType(shape) != "mesh":
            return None, "not_mesh"
        if _is_intermediate_shape(shape):
            return None, "intermediate_shape"
    except Exception:
        return None, "shape_query_failed"
    leaf = _dag_leaf_without_namespace(shape)
    compact = re.sub(r"[^a-z0-9]+", "", leaf.lower())
    if any(
        marker in compact
        for marker in (
            "dummy", "target", "cage", "orig", "proxy", "control",
            "controller", "guide", "helper", "bstarget",
        )
    ):
        return None, "helper_or_target_name"
    semantic = _motion_face_semantic(leaf, shape)
    if semantic["group"] != "eyelid":
        return None, "not_eye_or_eyelid_semantic"
    if isinstance(job, dict):
        try:
            cutout = _cutout_record(job, shape)
        except Exception as exc:
            return None, {
                "reason": "cutout_snapshot_unavailable",
                "detail": _clean(exc) or exc.__class__.__name__,
            }
        if cutout.get("ambiguous") or cutout.get("unsupported"):
            return None, {
                "reason": "cutout_snapshot_not_authoritative",
                "detail": _clean(cutout.get("reason")),
            }
        if cutout.get("alpha_driven"):
            return None, {
                "reason": "alpha_driven_card_excluded",
                "source_plug": _clean(cutout.get("source_plug")),
                "source_material": _clean(cutout.get("source_material")),
                "evidence_kind": _clean(cutout.get("evidence_kind")),
                "shading_group": _clean(cutout.get("shading_group")),
            }
    visibility = _motion_face_semantic_mesh_visibility_evidence(shape)
    if not visibility["eligible"]:
        return None, "not_authored_or_driven_visible"
    deformation = _motion_face_semantic_mesh_deformation_evidence(shape)
    if not deformation["eligible"]:
        return None, "no_deformation_or_transform_evidence"
    surface_diagonal = _motion_face_surface_diagonal(shape)
    if surface_diagonal <= 0.0:
        return None, "nonpositive_surface_extent"
    return {
        "shape": shape,
        "shape_id": _motion_face_node_uuid(shape),
        "surface_diagonal": round(surface_diagonal, 7),
        "region": "eyelid",
        "side": semantic["side"],
        "name_evidence": leaf,
        "selection_priority": (
            0 if "eyelid" in compact or "lid" in compact else 1
        ),
        "visibility_evidence": visibility,
        "deformation_evidence": deformation,
        "render_scope_verified": True,
        "intermediate": False,
    }, ""


def _motion_face_semantic_mesh_edge_indices(mesh_runtime):
    """Choose a deterministic bounded set of real topology edges."""
    om = mesh_runtime["om"]
    dag_path = mesh_runtime["dag_path"]
    all_edges = []
    boundary_edges = []
    try:
        iterator = om.MItMeshEdge(dag_path)
        while not iterator.isDone():
            record = (
                int(iterator.index()),
                int(iterator.vertexId(0)),
                int(iterator.vertexId(1)),
            )
            all_edges.append(record)
            if iterator.onBoundary():
                boundary_edges.append(record)
            iterator.next()
    except Exception:
        mesh_function = mesh_runtime["mesh_function"]
        try:
            edge_count = int(mesh_function.numEdges)
        except Exception:
            try:
                edge_count = int(mesh_function.numEdges())
            except Exception:
                edge_count = 0
        for edge_index in range(edge_count):
            try:
                vertices = mesh_function.getEdgeVertices(edge_index)
            except Exception:
                continue
            if len(vertices) >= 2:
                all_edges.append((
                    edge_index,
                    int(vertices[0]),
                    int(vertices[1]),
                ))
    source_edges = boundary_edges or all_edges
    source_kind = "boundary_edges" if boundary_edges else "bounded_all_edges"
    limit = MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE
    if len(source_edges) > limit:
        selected_indices = sorted(set(
            int(round(
                float(index) * float(len(source_edges) - 1)
                / float(max(1, limit - 1))
            ))
            for index in range(limit)
        ))
        selected = [source_edges[index] for index in selected_indices]
    else:
        selected = list(source_edges)
    return selected, {
        "topology_edge_count": len(all_edges),
        "boundary_edge_count": len(boundary_edges),
        "selected_edge_count": len(selected),
        "selection_source": source_kind,
        "selection_limit": limit,
    }


def _motion_face_semantic_surface_landmarks(
    shapes,
    channels,
    existing_regions=None,
    job=None,
):
    """Create region-local surface landmarks from final eye/eyelid meshes."""
    existing_regions = set(existing_regions or [])
    eligible_channel_ids = [
        item["id"]
        for item in channels or []
        if item.get("raster_eligible")
        and _clean(item.get("group")) == "eyelid"
    ]
    audit = {
        "policy": (
            "render_scope_nonintermediate_deformed_visible_semantic_mesh_edges"
        ),
        "appearance_authority": "zero",
        "curve_geometry_rendered": False,
        "candidate_count": 0,
        "accepted_surface_count": 0,
        "truncated_surface_count": 0,
        "surface_limit": MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES,
        "landmark_limit_per_surface": (
            MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE
        ),
        "edge_limit_per_surface": (
            MOTION_GUIDE_MAX_SEMANTIC_FACE_EDGES_PER_SURFACE
        ),
        "landmark_count": 0,
        "edge_count": 0,
        "regions": [],
        "surfaces": [],
        "rejections": [],
    }
    if "eyelid" in existing_regions:
        audit["rejections"].append({
            "shape": "",
            "reason": "delta_landmark_region_already_ready",
        })
        return [], [], [], audit
    if not eligible_channel_ids:
        audit["rejections"].append({
            "shape": "",
            "reason": "no_raster_eligible_eyelid_channel",
        })
        return [], [], [], audit

    candidates = []
    for shape in sorted(set(_clean(item) for item in shapes if _clean(item))):
        leaf = _dag_leaf_without_namespace(shape).lower()
        if "eye" not in leaf and "lid" not in leaf:
            continue
        audit["candidate_count"] += 1
        descriptor, rejection = _motion_face_semantic_mesh_descriptor(
            shape,
            job=job,
        )
        if descriptor is None:
            rejection_record = {
                "shape": shape,
                "reason": (
                    _clean(rejection.get("reason"))
                    if isinstance(rejection, dict)
                    else _clean(rejection)
                ),
            }
            if isinstance(rejection, dict):
                rejection_record.update(dict(rejection))
                rejection_record["shape"] = shape
            audit["rejections"].append(rejection_record)
            continue
        candidates.append(descriptor)
    candidates.sort(key=lambda item: (
        int(item.get("selection_priority") or 0),
        _clean(item.get("shape")),
    ))
    if len(candidates) > MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES:
        audit["truncated_surface_count"] = (
            len(candidates) - MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES
        )
        for descriptor in candidates[
            MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES:
        ]:
            audit["rejections"].append({
                "shape": descriptor["shape"],
                "reason": "semantic_surface_limit_exceeded",
                "limit": MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES,
            })
        candidates = candidates[:MOTION_GUIDE_MAX_SEMANTIC_FACE_SURFACES]

    landmarks = []
    edges = []
    landmark_runtime = []
    for descriptor in candidates:
        runtime = _motion_face_mesh_runtime(descriptor["shape"])
        if runtime is None:
            audit["rejections"].append({
                "shape": descriptor["shape"],
                "reason": "mesh_runtime_unavailable",
            })
            continue
        topology_edges, topology_audit = (
            _motion_face_semantic_mesh_edge_indices(runtime)
        )
        if not topology_edges:
            audit["rejections"].append({
                "shape": descriptor["shape"],
                "reason": "no_usable_topology_edges",
            })
            continue
        side_channel_ids = [
            item["id"]
            for item in channels or []
            if item.get("raster_eligible")
            and _clean(item.get("group")) == "eyelid"
            and (
                descriptor["side"] == "center"
                or _clean(item.get("side")) in {
                    descriptor["side"],
                    "center",
                }
            )
        ] or list(eligible_channel_ids)
        vertex_indices = sorted(set(
            vertex_index
            for _edge_index, first, second in topology_edges
            for vertex_index in (first, second)
        ))
        if (
            len(vertex_indices)
            > MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE
        ):
            audit["rejections"].append({
                "shape": descriptor["shape"],
                "reason": "semantic_landmark_limit_exceeded",
                "observed": len(vertex_indices),
                "limit": (
                    MOTION_GUIDE_MAX_SEMANTIC_FACE_LANDMARKS_PER_SURFACE
                ),
            })
            continue
        id_by_vertex = {}
        for vertex_index in vertex_indices:
            world_point = _motion_face_world_point(runtime, vertex_index)
            if world_point is None:
                continue
            stable_source = "{0}:{1}:eyelid:{2}:semantic_mesh".format(
                runtime["shape_id"],
                vertex_index,
                descriptor["side"],
            )
            landmark_id = "face:" + hashlib.sha256(
                stable_source.encode("utf-8")
            ).hexdigest()[:24]
            id_by_vertex[vertex_index] = landmark_id
            landmarks.append({
                "id": landmark_id,
                "region": "eyelid",
                "side": descriptor["side"],
                "controller_id": "",
                "controller_label": "",
                "mesh_id": runtime["shape_id"],
                "mesh": descriptor["shape"],
                "vertex_index": vertex_index,
                "channel_ids": sorted(set(side_channel_ids)),
                "surface_snap_distance": 0.0,
                "surface_vertex_distance": 0.0,
                "anchor_source": "render_scope_semantic_mesh_vertex",
                "anchor_method": "render_scope_semantic_mesh_vertex",
                "anchor_confidence": 1.0,
                "anchor_sample_count": len(vertex_indices),
            })
            landmark_runtime.append({
                "id": landmark_id,
                "region": "eyelid",
                "side": descriptor["side"],
                "vertex_index": vertex_index,
                "initial_world_point": world_point,
                "mesh_runtime": runtime,
            })
        surface_edge_count = 0
        for _edge_index, first, second in topology_edges:
            start_id = id_by_vertex.get(first)
            end_id = id_by_vertex.get(second)
            if not start_id or not end_id or start_id == end_id:
                continue
            edges.append({
                "from": start_id,
                "to": end_id,
                "region": "eyelid",
            })
            surface_edge_count += 1
        if not surface_edge_count:
            # Roll back the unusable surface records; a region is raster-ready
            # only when it has one real topology edge.
            surface_ids = set(id_by_vertex.values())
            landmarks = [
                item for item in landmarks if item["id"] not in surface_ids
            ]
            landmark_runtime = [
                item for item in landmark_runtime
                if item["id"] not in surface_ids
            ]
            audit["rejections"].append({
                "shape": descriptor["shape"],
                "reason": "topology_edge_endpoints_unavailable",
            })
            continue
        surface_report = dict(descriptor)
        surface_report["topology"] = topology_audit
        surface_report["landmark_count"] = len(id_by_vertex)
        surface_report["edge_count"] = surface_edge_count
        audit["surfaces"].append(surface_report)
        audit["accepted_surface_count"] += 1

    audit["landmark_count"] = len(landmarks)
    audit["edge_count"] = len(edges)
    audit["regions"] = ["eyelid"] if edges else []
    return landmarks, edges, landmark_runtime, audit


def _motion_face_scoped_blendshapes(root, shapes):
    history_shapes = {}
    for shape in shapes or []:
        try:
            history = cmds.listHistory(shape, pruneDagObjects=True) or []
            nodes = cmds.ls(history, type="blendShape") or []
        except Exception:
            nodes = []
        for node in nodes:
            node = _clean(node)
            if node:
                history_shapes.setdefault(node, []).append(_clean(shape))

    reference_node = _motion_reference_node(root)
    namespace = _namespace_from_leaf(_clean(root).split("|")[-1])
    try:
        scene_nodes = cmds.ls(type="blendShape") or []
    except Exception:
        scene_nodes = []
    scoped = set(history_shapes)
    if reference_node or namespace:
        for node in scene_nodes:
            node = _clean(node)
            include = False
            if reference_node:
                include = _motion_reference_node(node) == reference_node
            elif namespace:
                include = _namespace_from_leaf(node) == namespace
            if include:
                scoped.add(node)
    return sorted(scoped), history_shapes


def _motion_face_channels(root, shapes, marker=""):
    if marker in BACKGROUND_MARKERS:
        return [], [], {
            "candidate_blendshape_count": 0,
            "channel_count": 0,
            "raster_eligible_channel_count": 0,
            "truncated_channel_count": 0,
            "truncated_driver_count": 0,
            "source": "background_marker_face_disabled",
        }
    blendshapes, history_shapes = _motion_face_scoped_blendshapes(root, shapes)
    channels = []
    for blendshape in blendshapes:
        node_face_named = bool(
            re.search(
                r"face|facial|brow|eye|lid|mouth|lip|jaw|phoneme|viseme",
                blendshape,
                re.IGNORECASE,
            )
        )
        node_uuid = _motion_face_node_uuid(blendshape)
        for alias, logical_index, plug in _motion_face_alias_pairs(blendshape):
            semantic = _motion_face_semantic(alias, blendshape)
            if not semantic["raster_eligible"] and not node_face_named:
                continue
            if _motion_face_numeric_value(plug) is None:
                continue
            channel_id = "{0}:weight[{1}]".format(node_uuid, logical_index)
            channels.append({
                "id": channel_id,
                "alias": alias,
                "blendshape": blendshape,
                "blendshape_id": node_uuid,
                "weight_index": logical_index,
                "weight_plug": plug,
                "group": semantic["group"],
                "side": semantic["side"],
                "action": semantic["action"],
                "raster_eligible": bool(semantic["raster_eligible"]),
                "controller_plugs": _motion_face_driver_plugs(plug),
                "affected_shapes": sorted(set(history_shapes.get(blendshape, []))),
            })
    channels.sort(key=lambda item: (
        not item["raster_eligible"],
        item["group"],
        item["side"],
        item["alias"].lower(),
        item["blendshape"],
        item["weight_index"],
    ))
    raw_count = len(channels)
    channels = channels[:MOTION_GUIDE_MAX_FACE_CHANNELS_PER_TARGET]
    drivers = []
    seen_drivers = set()
    truncated_driver_count = 0
    for channel in channels:
        for plug in channel["controller_plugs"]:
            if _motion_face_numeric_value(plug) is None:
                continue
            if plug in seen_drivers:
                continue
            seen_drivers.add(plug)
            if len(drivers) >= MOTION_GUIDE_MAX_FACE_DRIVERS_PER_TARGET:
                truncated_driver_count += 1
                continue
            node = plug.split(".", 1)[0]
            drivers.append({
                "id": "{0}:{1}".format(_motion_face_node_uuid(node), plug.split(".", 1)[1]),
                "plug": plug,
                "node": node,
                "node_id": _motion_face_node_uuid(node),
                "label": _dag_leaf_without_namespace(node),
            })
    retained_driver_plugs = set(item["plug"] for item in drivers)
    for channel in channels:
        channel["controller_plugs"] = [
            plug for plug in channel["controller_plugs"]
            if plug in retained_driver_plugs
        ]
    keyed_drivers, keyed_driver_audit = _motion_face_keyed_semantic_drivers(
        root,
        existing_drivers=drivers,
    )
    available_driver_slots = max(
        0,
        MOTION_GUIDE_MAX_FACE_DRIVERS_PER_TARGET - len(drivers),
    )
    if len(keyed_drivers) > available_driver_slots:
        truncated_driver_count += len(keyed_drivers) - available_driver_slots
        keyed_drivers = keyed_drivers[:available_driver_slots]
        keyed_driver_audit["keyed_semantic_driver_count"] = len(
            keyed_drivers
        )
    drivers.extend(keyed_drivers)
    return channels, drivers, {
        "candidate_blendshape_count": len(blendshapes),
        "channel_count": len(channels),
        "raster_eligible_channel_count": sum(
            1 for item in channels if item["raster_eligible"]
        ),
        "driver_count": len(drivers),
        "truncated_channel_count": max(0, raw_count - len(channels)),
        "truncated_driver_count": truncated_driver_count,
        "source": "target_reference_or_namespace_blendshape_aliases",
        "keyed_semantic_driver_audit": keyed_driver_audit,
    }


def _motion_joint_stable_id(joint):
    try:
        values = cmds.ls(joint, uuid=True) or []
    except Exception:
        values = []
    return _clean(values[0]) if values else _clean(joint)


def _motion_joint_signature(joints):
    return tuple(sorted(_motion_joint_stable_id(joint) for joint in joints))


def _motion_nearest_selected_parent(joint, selected):
    current = joint
    while current:
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        current = _clean(parents[0]) if parents else ""
        if current in selected:
            return current
    return ""


def _motion_face_numeric_value(plug):
    try:
        value = cmds.getAttr(plug)
    except Exception:
        return None
    while isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    if isinstance(value, (list, tuple)):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _motion_face_controller_path(node, root=""):
    try:
        paths = cmds.ls(node, long=True) or []
    except Exception:
        paths = []
    paths = sorted(set(_clean(item) for item in paths if _clean(item)))
    if root:
        root_prefix = _clean(root) + "|"
        scoped = [
            item for item in paths
            if item == root or item.startswith(root_prefix)
        ]
        if scoped:
            paths = scoped
    path = paths[0] if paths else _clean(node)
    # A production face controller can live below a facial-window or picker
    # container while its evaluated curve is constrained onto the character.
    # Reject only a controller whose own name identifies UI infrastructure;
    # the surface-distance gate below remains authoritative for remote UI.
    lowered = _dag_leaf_without_namespace(path).lower()
    if any(
        marker in lowered
        for marker in (
            "facialwindow", "bstarget", "targetbank", "target_bank",
            "dashboard", "posepanel", "picker", "facial_gui", "facialgui",
        )
    ):
        return ""
    try:
        curve_shapes = cmds.listRelatives(
            path,
            shapes=True,
            noIntermediate=True,
            type="nurbsCurve",
            fullPath=True,
        ) or []
    except Exception:
        curve_shapes = []
    return path if curve_shapes else ""


def _motion_face_controller_pivot(path):
    try:
        value = cmds.xform(
            path,
            query=True,
            worldSpace=True,
            rotatePivot=True,
        )
    except Exception:
        try:
            value = cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )
        except Exception:
            value = []
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        point = [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return None
    return point if all(math.isfinite(item) for item in point) else None


def _motion_face_controller_anchor_points(path):
    """Return safe point summaries, never the controller's raw curve geometry."""
    candidates = []
    pivot = _motion_face_controller_pivot(path)
    if pivot is not None:
        candidates.append({
            "source": "rotate_pivot",
            "point": pivot,
            "sample_count": 1,
        })

    try:
        curve_shapes = cmds.listRelatives(
            path,
            shapes=True,
            noIntermediate=True,
            type="nurbsCurve",
            fullPath=True,
        ) or []
    except Exception:
        curve_shapes = []
    curve_points = []
    for shape in curve_shapes:
        try:
            components = cmds.ls(shape + ".cv[*]", flatten=True) or []
        except Exception:
            components = []
        for component in components:
            try:
                value = cmds.pointPosition(component, world=True)
                point = [float(value[0]), float(value[1]), float(value[2])]
            except Exception:
                continue
            if all(math.isfinite(item) for item in point):
                curve_points.append(point)
    if curve_points:
        candidates.append({
            "source": "curve_cv_centroid",
            "point": [
                sum(point[axis] for point in curve_points)
                / float(len(curve_points))
                for axis in range(3)
            ],
            "sample_count": len(curve_points),
        })

    unique = []
    for candidate in candidates:
        if any(
            sum(
                (
                    float(candidate["point"][axis])
                    - float(existing["point"][axis])
                ) ** 2
                for axis in range(3)
            ) <= 1.0e-16
            for existing in unique
        ):
            continue
        unique.append(candidate)
    return unique


def _motion_face_mesh_runtime(shape):
    try:
        import maya.api.OpenMaya as om
        selection = om.MSelectionList()
        selection.add(shape)
        dag_path = selection.getDagPath(0)
        mesh_function = om.MFnMesh(dag_path)
        polygon_count = mesh_function.numPolygons
        if callable(polygon_count):
            polygon_count = polygon_count()
        if int(polygon_count) <= 0:
            return None
    except Exception:
        return None
    return {
        "om": om,
        "shape": _clean(shape),
        "shape_id": _motion_face_node_uuid(shape),
        "dag_path": dag_path,
        "mesh_function": mesh_function,
    }


def _motion_face_surface_diagonal(shape):
    try:
        bounds = cmds.exactWorldBoundingBox(shape, ignoreInvisible=False)
    except Exception:
        bounds = []
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 6:
        return 0.0
    try:
        dx = float(bounds[3]) - float(bounds[0])
        dy = float(bounds[4]) - float(bounds[1])
        dz = float(bounds[5]) - float(bounds[2])
        diagonal = math.sqrt(dx * dx + dy * dy + dz * dz)
    except Exception:
        return 0.0
    return diagonal if math.isfinite(diagonal) and diagonal > 0.0 else 0.0


def _motion_face_nearest_vertex(mesh_runtime, world_point):
    om = mesh_runtime["om"]
    mesh_function = mesh_runtime["mesh_function"]
    try:
        closest_point, face_index = mesh_function.getClosestPoint(
            om.MPoint(
                float(world_point[0]),
                float(world_point[1]),
                float(world_point[2]),
                1.0,
            ),
            om.MSpace.kWorld,
        )
        vertices = mesh_function.getPolygonVertices(int(face_index))
    except Exception:
        return None
    try:
        surface_distance = math.sqrt(
            (float(closest_point.x) - float(world_point[0])) ** 2
            + (float(closest_point.y) - float(world_point[1])) ** 2
            + (float(closest_point.z) - float(world_point[2])) ** 2
        )
    except Exception:
        return None
    best = None
    for vertex_index in vertices:
        try:
            point = mesh_function.getPoint(int(vertex_index), om.MSpace.kWorld)
            distance = math.sqrt(
                (float(point.x) - float(world_point[0])) ** 2
                + (float(point.y) - float(world_point[1])) ** 2
                + (float(point.z) - float(world_point[2])) ** 2
            )
        except Exception:
            continue
        if best is None or distance < best[0]:
            best = (
                distance,
                int(vertex_index),
                [float(point.x), float(point.y), float(point.z)],
                [
                    float(closest_point.x),
                    float(closest_point.y),
                    float(closest_point.z),
                ],
            )
    if best is None:
        return None
    return {
        # Safety is decided against the continuous face surface.  The chosen
        # vertex is only the stable, deformation-following runtime anchor.
        "distance": surface_distance,
        "surface_distance": surface_distance,
        "vertex_distance": best[0],
        "vertex_index": best[1],
        "vertex_point": best[2],
        "closest_point": best[3],
    }


def _motion_face_component_vertex_indices(raw_components):
    """Expand blendShape component-list values without evaluating the rig."""
    values = raw_components
    while (
        isinstance(values, (list, tuple))
        and len(values) == 1
        and isinstance(values[0], (list, tuple))
    ):
        values = values[0]
    indices = []
    for value in values or []:
        text = _clean(value)
        for match in re.finditer(r"vtx\[(\d+)(?::(\d+))?\]", text):
            first = int(match.group(1))
            last = int(match.group(2) or first)
            if last < first:
                first, last = last, first
            indices.extend(range(first, last + 1))
    return indices


def _motion_face_blendshape_geometry_indices(blendshape, face_surface):
    """Return only inputTarget indices that deform the selected face mesh."""
    try:
        geometries = cmds.blendShape(
            blendshape,
            query=True,
            geometry=True,
        ) or []
        geometry_indices = cmds.blendShape(
            blendshape,
            query=True,
            geometryIndices=True,
        ) or []
    except Exception:
        geometries = []
        geometry_indices = []
    face_long = set(_long_names([face_surface]))
    selected = []
    for order, geometry in enumerate(geometries):
        try:
            geometry_shapes = cmds.listRelatives(
                geometry,
                shapes=True,
                noIntermediate=True,
                fullPath=True,
            ) or []
        except Exception:
            geometry_shapes = []
        candidates = set(_long_names([geometry] + geometry_shapes))
        if face_long.intersection(candidates):
            try:
                selected.append(int(geometry_indices[order]))
            except Exception:
                selected.append(order)
    if selected:
        return sorted(set(selected))
    try:
        return sorted(set(
            int(value)
            for value in (
                cmds.getAttr(
                    blendshape + ".inputTarget",
                    multiIndices=True,
                ) or []
            )
        ))
    except Exception:
        return []


def _motion_face_blendshape_delta_scores(
    channel,
    face_surface,
    vertex_count,
):
    """Read stored target deltas; never changes a Blend Shape weight."""
    blendshape = _clean(channel.get("blendshape"))
    try:
        weight_index = int(channel.get("weight_index"))
    except Exception:
        return {}
    if not blendshape or weight_index < 0:
        return {}
    affected = set(_long_names(channel.get("affected_shapes") or []))
    if affected and not affected.intersection(_long_names([face_surface])):
        return {}
    scores = {}
    for geometry_index in _motion_face_blendshape_geometry_indices(
        blendshape,
        face_surface,
    ):
        group_plug = (
            "{0}.inputTarget[{1}].inputTargetGroup[{2}]".format(
                blendshape,
                geometry_index,
                weight_index,
            )
        )
        try:
            item_indices = cmds.getAttr(
                group_plug + ".inputTargetItem",
                multiIndices=True,
            ) or []
        except Exception:
            item_indices = []
        for item_index in item_indices:
            item_plug = "{0}.inputTargetItem[{1}]".format(
                group_plug,
                int(item_index),
            )
            try:
                raw_points = cmds.getAttr(
                    item_plug + ".inputPointsTarget"
                ) or []
                raw_components = cmds.getAttr(
                    item_plug + ".inputComponentsTarget"
                ) or []
            except Exception:
                continue
            while (
                isinstance(raw_points, (list, tuple))
                and len(raw_points) == 1
                and isinstance(raw_points[0], (list, tuple))
                and raw_points[0]
                and isinstance(raw_points[0][0], (list, tuple))
            ):
                raw_points = raw_points[0]
            points = [
                value
                for value in (raw_points or [])
                if isinstance(value, (list, tuple)) and len(value) >= 3
            ]
            indices = _motion_face_component_vertex_indices(raw_components)
            if not indices and len(points) == int(vertex_count):
                indices = list(range(int(vertex_count)))
            if len(indices) != len(points):
                continue
            for vertex_index, point in zip(indices, points):
                if vertex_index < 0 or vertex_index >= int(vertex_count):
                    continue
                try:
                    magnitude = math.sqrt(
                        float(point[0]) ** 2
                        + float(point[1]) ** 2
                        + float(point[2]) ** 2
                    )
                except Exception:
                    continue
                if not math.isfinite(magnitude) or magnitude <= 1.0e-10:
                    continue
                scores[vertex_index] = max(
                    float(scores.get(vertex_index) or 0.0),
                    magnitude,
                )
    return scores


def _motion_face_object_points(mesh_runtime):
    try:
        points = mesh_runtime["mesh_function"].getPoints(
            mesh_runtime["om"].MSpace.kObject
        )
    except Exception:
        return []
    return [
        [float(point.x), float(point.y), float(point.z)]
        for point in points
    ]


def _motion_face_world_point(mesh_runtime, vertex_index):
    try:
        point = mesh_runtime["mesh_function"].getPoint(
            int(vertex_index),
            mesh_runtime["om"].MSpace.kWorld,
        )
        return [float(point.x), float(point.y), float(point.z)]
    except Exception:
        return None


def _motion_face_weighted_delta_candidate(
    mesh_runtime,
    object_points,
    region,
    side,
    scores,
    channel_ids,
):
    if not scores or not object_points:
        return None
    maximum = max(float(value) for value in scores.values())
    retained = [
        (int(vertex_index), float(score))
        for vertex_index, score in scores.items()
        if float(score) >= maximum * 0.2
        and 0 <= int(vertex_index) < len(object_points)
    ]
    retained.sort(key=lambda item: (-item[1], item[0]))
    retained = retained[:512]
    total = sum(item[1] for item in retained)
    if not retained or total <= 0.0:
        return None
    centroid = [
        sum(
            object_points[vertex_index][axis] * score
            for vertex_index, score in retained
        ) / total
        for axis in range(3)
    ]
    vertex_index, score = min(
        retained,
        key=lambda item: (
            sum(
                (
                    object_points[item[0]][axis] - centroid[axis]
                ) ** 2
                for axis in range(3)
            ),
            -item[1],
            item[0],
        ),
    )
    world_point = _motion_face_world_point(mesh_runtime, vertex_index)
    if world_point is None:
        return None
    return {
        "region": region,
        "side": side,
        "controller_path": "",
        "controller_id": "",
        "controller_label": "",
        "channel_ids": set(channel_ids),
        "distance": 0.0,
        "vertex_distance": 0.0,
        "anchor_source": "blendshape_target_delta_heatmap",
        "anchor_sample_count": len(retained),
        "anchor_confidence": round(min(1.0, score / maximum), 7),
        "vertex_index": int(vertex_index),
        "initial_world_point": world_point,
    }


def _motion_face_delta_landmark_candidates(
    mesh_runtime,
    face_surface,
    channels,
):
    """Localize semantic anchors from authored deformation, read-only."""
    object_points = _motion_face_object_points(mesh_runtime)
    if not object_points:
        return [], {"delta_channel_count": 0, "delta_bucket_count": 0}
    xs = [point[0] for point in object_points]
    center_x = (min(xs) + max(xs)) * 0.5
    bucket_scores = {}
    bucket_channels = {}
    delta_channel_count = 0
    for channel in channels or []:
        if not channel.get("raster_eligible"):
            continue
        region = _clean(channel.get("group"))
        if region not in {"brow", "eyelid", "mouth", "jaw"}:
            continue
        scores = _motion_face_blendshape_delta_scores(
            channel,
            face_surface,
            len(object_points),
        )
        if not scores:
            continue
        delta_channel_count += 1
        side = _clean(channel.get("side")) or "center"
        buckets = []
        if side in {"left", "right"}:
            buckets.append((side, scores))
        elif region in {"brow", "eyelid"}:
            left_scores = dict(
                (index, score) for index, score in scores.items()
                if object_points[index][0] <= center_x
            )
            right_scores = dict(
                (index, score) for index, score in scores.items()
                if object_points[index][0] >= center_x
            )
            if left_scores:
                buckets.append(("left", left_scores))
            if right_scores:
                buckets.append(("right", right_scores))
        else:
            buckets.append(("center", scores))
        for bucket_side, side_scores in buckets:
            key = (region, bucket_side)
            merged = bucket_scores.setdefault(key, {})
            for vertex_index, score in side_scores.items():
                merged[vertex_index] = max(
                    float(merged.get(vertex_index) or 0.0),
                    float(score),
                )
            bucket_channels.setdefault(key, set()).add(channel["id"])
    candidates = []
    for key in sorted(bucket_scores):
        candidate = _motion_face_weighted_delta_candidate(
            mesh_runtime,
            object_points,
            key[0],
            key[1],
            bucket_scores[key],
            bucket_channels.get(key) or set(),
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates, {
        "delta_channel_count": delta_channel_count,
        "delta_bucket_count": len(bucket_scores),
        "delta_landmark_count": len(candidates),
    }


def _motion_face_nearest_object_vertex(object_points, desired_point):
    if not object_points:
        return None
    vertex_index = min(
        range(len(object_points)),
        key=lambda index: sum(
            (object_points[index][axis] - desired_point[axis]) ** 2
            for axis in range(3)
        ),
    )
    distance = math.sqrt(sum(
        (object_points[vertex_index][axis] - desired_point[axis]) ** 2
        for axis in range(3)
    ))
    return vertex_index, distance


def _motion_face_complete_bilateral_and_jaw(
    chosen,
    mesh_runtime,
    channels,
):
    """Complete only bounded, evidenced slots on the same face surface.

    This is deliberately not a general topology-symmetry solver.  A missing
    bilateral slot is completed only when at least two other authored
    left/right semantic pairs agree on a lateral direction.  Jaw anchors use
    the authored mouth and upper-face landmarks to derive a local face axis;
    object-space X/Y is never treated as a semantic axis.
    """
    object_points = _motion_face_object_points(mesh_runtime)
    audit = {
        "mirrored_count": 0,
        "inferred_jaw_count": 0,
        "mirror_policy": (
            "bounded_two_pair_bilateral_offset_no_topology_symmetry_claim"
        ),
        "jaw_policy": (
            "semantic_face_axis_sides_then_bilateral_midpoint_axis_center_and_surface_profile_fallbacks_fail_closed"
        ),
        "mirror_evidence": [],
        "jaw_evidence": [],
        "jaw_center_candidate_evidence": [],
        "completion_rejections": [],
    }
    if not chosen or not object_points:
        audit["completion_rejections"].append("no_landmarks_or_surface_points")
        return chosen, audit
    bounds_min = [min(point[axis] for point in object_points) for axis in range(3)]
    bounds_max = [max(point[axis] for point in object_points) for axis in range(3)]
    diagonal = math.sqrt(sum(
        (bounds_max[axis] - bounds_min[axis]) ** 2
        for axis in range(3)
    ))
    if diagonal <= 0.0:
        audit["completion_rejections"].append("invalid_surface_diagonal")
        return chosen, audit

    def subtract(first, second):
        return [float(first[axis]) - float(second[axis]) for axis in range(3)]

    def add(first, second):
        return [float(first[axis]) + float(second[axis]) for axis in range(3)]

    def scale(vector, amount):
        return [float(value) * float(amount) for value in vector]

    def dot(first, second):
        return sum(float(first[axis]) * float(second[axis]) for axis in range(3))

    def length(vector):
        return math.sqrt(max(0.0, dot(vector, vector)))

    def normalized(vector):
        magnitude = length(vector)
        if magnitude <= 1.0e-10:
            return None
        return [float(value) / magnitude for value in vector]

    result = list(chosen)
    bucket_map = dict(
        ((item["region"], item["side"]), item)
        for item in result
    )
    channel_ids_by_bucket = {}
    for channel in channels or []:
        region = _clean(channel.get("group"))
        side = _clean(channel.get("side")) or "center"
        if region in {"brow", "eyelid", "mouth", "jaw"}:
            channel_ids_by_bucket.setdefault((region, side), set()).add(
                channel["id"]
            )

    bilateral_records = []
    for paired_region in ("brow", "eyelid", "mouth"):
        left = bucket_map.get((paired_region, "left"))
        right = bucket_map.get((paired_region, "right"))
        if left is None or right is None:
            continue
        left_point = object_points[int(left["vertex_index"])]
        right_point = object_points[int(right["vertex_index"])]
        vector = subtract(left_point, right_point)
        unit = normalized(vector)
        vector_length = length(vector)
        if unit is None or vector_length < diagonal * 0.02:
            continue
        bilateral_records.append({
            "region": paired_region,
            "vector": vector,
            "unit": unit,
            "length": vector_length,
        })

    for region in ("brow", "eyelid", "mouth"):
        for source_side, target_side in (("left", "right"), ("right", "left")):
            if (region, target_side) in bucket_map:
                continue
            source = bucket_map.get((region, source_side))
            if source is None:
                continue
            target_channel_ids = channel_ids_by_bucket.get((region, target_side))
            if not target_channel_ids:
                audit["completion_rejections"].append(
                    "{0}:{1}:no_authored_target_side_channel".format(
                        region,
                        target_side,
                    )
                )
                continue
            evidence_records = [
                record for record in bilateral_records
                if record["region"] != region
            ]
            if len(evidence_records) < 2:
                audit["completion_rejections"].append(
                    "{0}:{1}:fewer_than_two_bilateral_evidence_pairs".format(
                        region,
                        target_side,
                    )
                )
                continue
            reference = evidence_records[0]["unit"]
            alignments = [
                dot(reference, record["unit"])
                for record in evidence_records[1:]
            ]
            minimum_alignment = min(alignments or [1.0])
            if minimum_alignment < 0.75:
                audit["completion_rejections"].append(
                    "{0}:{1}:bilateral_direction_disagreement".format(
                        region,
                        target_side,
                    )
                )
                continue
            source_index = int(source["vertex_index"])
            if source_index < 0 or source_index >= len(object_points):
                continue
            source_point = object_points[source_index]
            direction = 1.0 if target_side == "left" else -1.0
            transfer = [
                sum(record["vector"][axis] for record in evidence_records)
                / float(len(evidence_records))
                * direction
                for axis in range(3)
            ]
            transfer_unit = normalized(transfer)
            transfer_length = length(transfer)
            if transfer_unit is None or transfer_length < diagonal * 0.02:
                continue
            desired = add(source_point, transfer)
            tolerance_fraction = 0.05
            nearest = _motion_face_nearest_object_vertex(
                object_points,
                desired,
            )
            if nearest is None or nearest[1] > diagonal * tolerance_fraction:
                audit["completion_rejections"].append(
                    "{0}:{1}:surface_snap_outside_bound".format(
                        region,
                        target_side,
                    )
                )
                continue
            vertex_index = int(nearest[0])
            if vertex_index == source_index:
                continue
            displacement = subtract(object_points[vertex_index], source_point)
            displacement_unit = normalized(displacement)
            if (
                displacement_unit is None
                or dot(displacement_unit, transfer_unit) < 0.7
            ):
                audit["completion_rejections"].append(
                    "{0}:{1}:surface_displacement_direction_mismatch".format(
                        region,
                        target_side,
                    )
                )
                continue
            world_point = _motion_face_world_point(mesh_runtime, vertex_index)
            if world_point is None:
                continue
            candidate = dict(source)
            candidate.update({
                "side": target_side,
                "controller_path": "",
                "controller_id": "",
                "controller_label": "",
                "channel_ids": set(target_channel_ids),
                "distance": float(nearest[1]),
                "vertex_distance": float(nearest[1]),
                "anchor_source": "bounded_bilateral_surface_offset_fallback",
                "anchor_sample_count": 1,
                "anchor_confidence": round(
                    max(0.0, min(
                        float(source.get("anchor_confidence") or 0.0),
                        minimum_alignment,
                        1.0 - (
                            nearest[1] / (diagonal * tolerance_fraction)
                        ),
                    )),
                    7,
                ),
                "vertex_index": vertex_index,
                "initial_world_point": world_point,
            })
            result.append(candidate)
            bucket_map[(region, target_side)] = candidate
            audit["mirrored_count"] += 1
            audit["mirror_evidence"].append({
                "region": region,
                "source_side": source_side,
                "target_side": target_side,
                "source_vertex_index": source_index,
                "target_vertex_index": vertex_index,
                "evidence_regions": sorted(
                    record["region"] for record in evidence_records
                ),
                "minimum_direction_alignment": round(
                    minimum_alignment,
                    7,
                ),
                "transfer_length_fraction": round(
                    transfer_length / diagonal,
                    7,
                ),
                "surface_snap_fraction": round(
                    float(nearest[1]) / diagonal,
                    7,
                ),
                "surface_snap_limit_fraction": tolerance_fraction,
            })

    jaw_channels = [
        channel["id"]
        for channel in channels or []
        if _clean(channel.get("group")) == "jaw"
    ]
    mouth_channels = [
        channel["id"]
        for channel in channels or []
        if _clean(channel.get("group")) == "mouth"
    ]
    jaw_source_ids = set(jaw_channels or mouth_channels)
    if jaw_source_ids:
        mouth_by_side = dict(
            (side, bucket_map.get(("mouth", side)))
            for side in ("left", "center", "right")
        )
        upper_sources = [
            item for item in result
            if item["region"] in {"brow", "eyelid"}
            and item["side"] in {"left", "right"}
        ]
        axis_ready = bool(
            all(mouth_by_side.values())
            and {item["side"] for item in upper_sources} == {"left", "right"}
        )
        lateral_unit = None
        up_unit = None
        lateral_length = 0.0
        up_length = 0.0
        if axis_ready:
            left_mouth_point = object_points[
                int(mouth_by_side["left"]["vertex_index"])
            ]
            center_mouth_point = object_points[
                int(mouth_by_side["center"]["vertex_index"])
            ]
            right_mouth_point = object_points[
                int(mouth_by_side["right"]["vertex_index"])
            ]
            lateral = subtract(right_mouth_point, left_mouth_point)
            lateral_length = length(lateral)
            lateral_unit = normalized(lateral)
            upper_centroid = [
                sum(
                    object_points[int(item["vertex_index"])][axis]
                    for item in upper_sources
                ) / float(len(upper_sources))
                for axis in range(3)
            ]
            up_raw = subtract(upper_centroid, center_mouth_point)
            if lateral_unit is not None:
                up_raw = subtract(
                    up_raw,
                    scale(lateral_unit, dot(up_raw, lateral_unit)),
                )
            up_length = length(up_raw)
            up_unit = normalized(up_raw)
            axis_ready = bool(
                lateral_unit is not None
                and up_unit is not None
                and lateral_length >= diagonal * 0.03
                and up_length >= diagonal * 0.03
            )
        audit["jaw_axis_evidence"] = {
            "ready": bool(axis_ready),
            "mouth_sides": sorted(
                side for side, item in mouth_by_side.items() if item is not None
            ),
            "upper_sides": sorted(set(
                item["side"] for item in upper_sources
            )),
            "upper_region_count": len(set(
                item["region"] for item in upper_sources
            )),
            "lateral_span_fraction": round(lateral_length / diagonal, 7),
            "upper_mouth_span_fraction": round(up_length / diagonal, 7),
        }
        if not axis_ready:
            audit["completion_rejections"].append(
                "jaw:semantic_face_axis_unavailable"
            )
        # Resolve lateral jaw anchors first.  The center is not guessed from a
        # fixed downward offset: once both surface sides exist it is localized
        # from their surface midpoint under the same semantic-axis gates.
        for side in ("left", "right"):
            if ("jaw", side) in bucket_map or not axis_ready:
                continue
            source = mouth_by_side[side]
            source_point = object_points[int(source["vertex_index"])]
            down_distance = diagonal * (0.10 if side == "center" else 0.07)
            desired = add(source_point, scale(up_unit, -down_distance))
            nearest = _motion_face_nearest_object_vertex(
                object_points,
                desired,
            )
            tolerance_fraction = 0.06
            if nearest is None or nearest[1] > diagonal * tolerance_fraction:
                audit["completion_rejections"].append(
                    "jaw:{0}:surface_snap_outside_bound".format(side)
                )
                continue
            vertex_index = int(nearest[0])
            if vertex_index == int(source["vertex_index"]):
                audit["completion_rejections"].append(
                    "jaw:{0}:surface_snap_returned_source_vertex".format(side)
                )
                continue
            candidate_point = object_points[vertex_index]
            displacement = subtract(candidate_point, source_point)
            downward_progress = dot(displacement, scale(up_unit, -1.0))
            lateral_drift = abs(dot(displacement, lateral_unit))
            if (
                downward_progress < diagonal * 0.02
                or lateral_drift > diagonal * 0.05
            ):
                audit["completion_rejections"].append(
                    "jaw:{0}:axis_or_lateral_gate_failed".format(side)
                )
                continue
            world_point = _motion_face_world_point(mesh_runtime, vertex_index)
            if world_point is None:
                audit["completion_rejections"].append(
                    "jaw:{0}:world_point_unavailable".format(side)
                )
                continue
            side_channel_ids = (
                channel_ids_by_bucket.get(("jaw", side))
                or channel_ids_by_bucket.get(("mouth", side))
                or jaw_source_ids
            )
            candidate = {
                "region": "jaw",
                "side": side,
                "controller_path": "",
                "controller_id": "",
                "controller_label": "",
                "channel_ids": set(side_channel_ids),
                "distance": float(nearest[1]),
                "vertex_distance": float(nearest[1]),
                "anchor_source": "semantic_face_axis_lower_surface_inference",
                "anchor_sample_count": 1,
                "anchor_confidence": round(
                    max(
                        0.0,
                        1.0 - (
                            nearest[1] / (diagonal * tolerance_fraction)
                        ),
                    ),
                    7,
                ),
                "vertex_index": vertex_index,
                "initial_world_point": world_point,
            }
            result.append(candidate)
            bucket_map[("jaw", side)] = candidate
            audit["inferred_jaw_count"] += 1
            audit["jaw_evidence"].append({
                "method": "semantic_face_axis_lower_surface_inference",
                "side": side,
                "source_vertex_index": int(source["vertex_index"]),
                "target_vertex_index": vertex_index,
                "downward_progress_fraction": round(
                    downward_progress / diagonal,
                    7,
                ),
                "lateral_drift_fraction": round(
                    lateral_drift / diagonal,
                    7,
                ),
                "surface_snap_fraction": round(
                    float(nearest[1]) / diagonal,
                    7,
                ),
                "surface_snap_limit_fraction": tolerance_fraction,
            })

        if ("jaw", "center") not in bucket_map:
            left_jaw = bucket_map.get(("jaw", "left"))
            right_jaw = bucket_map.get(("jaw", "right"))
            center_mouth = mouth_by_side.get("center")
            if not axis_ready:
                audit["completion_rejections"].append(
                    "jaw:center:semantic_face_axis_unavailable"
                )
            elif left_jaw is None or right_jaw is None:
                audit["completion_rejections"].append(
                    "jaw:center:bilateral_jaw_surface_pair_unavailable"
                )
            elif center_mouth is None:
                audit["completion_rejections"].append(
                    "jaw:center:mouth_center_unavailable"
                )
            else:
                left_jaw_index = int(left_jaw["vertex_index"])
                right_jaw_index = int(right_jaw["vertex_index"])
                mouth_center_index = int(center_mouth["vertex_index"])
                left_jaw_point = object_points[left_jaw_index]
                right_jaw_point = object_points[right_jaw_index]
                mouth_center_point = object_points[mouth_center_index]
                jaw_span_vector = subtract(
                    right_jaw_point,
                    left_jaw_point,
                )
                jaw_lateral_span = dot(jaw_span_vector, lateral_unit)
                minimum_jaw_span = diagonal * 0.03
                if jaw_lateral_span < minimum_jaw_span:
                    audit["completion_rejections"].append(
                        "jaw:center:bilateral_jaw_span_invalid"
                    )
                else:
                    desired = scale(
                        add(left_jaw_point, right_jaw_point),
                        0.5,
                    )
                    nearest = _motion_face_nearest_object_vertex(
                        object_points,
                        desired,
                    )
                    tolerance_fraction = 0.06
                    if (
                        nearest is None
                        or nearest[1] > diagonal * tolerance_fraction
                    ):
                        audit["completion_rejections"].append(
                            "jaw:center:midpoint_surface_snap_outside_bound"
                        )
                    else:
                        vertex_index = int(nearest[0])
                        candidate_point = object_points[vertex_index]
                        mouth_to_candidate = subtract(
                            candidate_point,
                            mouth_center_point,
                        )
                        downward_progress = dot(
                            mouth_to_candidate,
                            scale(up_unit, -1.0),
                        )
                        lateral_center_drift = abs(dot(
                            mouth_to_candidate,
                            lateral_unit,
                        ))
                        maximum_center_drift = min(
                            diagonal * 0.04,
                            jaw_lateral_span * 0.25,
                        )
                        span_position = dot(
                            subtract(candidate_point, left_jaw_point),
                            lateral_unit,
                        ) / jaw_lateral_span
                        rejection = ""
                        if vertex_index in {
                            left_jaw_index,
                            right_jaw_index,
                            mouth_center_index,
                        }:
                            rejection = (
                                "jaw:center:midpoint_returned_noncenter_source_vertex"
                            )
                        elif downward_progress < diagonal * 0.02:
                            rejection = (
                                "jaw:center:insufficient_downward_progress"
                            )
                        elif lateral_center_drift > maximum_center_drift:
                            rejection = (
                                "jaw:center:lateral_center_drift_outside_bound"
                            )
                        elif not 0.0 <= span_position <= 1.0:
                            rejection = (
                                "jaw:center:outside_bilateral_jaw_span"
                            )
                        if rejection:
                            audit["completion_rejections"].append(rejection)
                        else:
                            world_point = _motion_face_world_point(
                                mesh_runtime,
                                vertex_index,
                            )
                            if world_point is None:
                                audit["completion_rejections"].append(
                                    "jaw:center:world_point_unavailable"
                                )
                            else:
                                side_channel_ids = (
                                    channel_ids_by_bucket.get(("jaw", "center"))
                                    or channel_ids_by_bucket.get(("mouth", "center"))
                                    or jaw_source_ids
                                )
                                candidate = {
                                    "region": "jaw",
                                    "side": "center",
                                    "controller_path": "",
                                    "controller_id": "",
                                    "controller_label": "",
                                    "channel_ids": set(side_channel_ids),
                                    "distance": float(nearest[1]),
                                    "vertex_distance": float(nearest[1]),
                                    "anchor_source": (
                                        "semantic_bilateral_jaw_midpoint_surface_inference"
                                    ),
                                    "anchor_sample_count": 2,
                                    "anchor_confidence": round(
                                        max(
                                            0.0,
                                            1.0 - (
                                                nearest[1]
                                                / (
                                                    diagonal
                                                    * tolerance_fraction
                                                )
                                            ),
                                        ),
                                        7,
                                    ),
                                    "vertex_index": vertex_index,
                                    "initial_world_point": world_point,
                                }
                                result.append(candidate)
                                bucket_map[("jaw", "center")] = candidate
                                audit["inferred_jaw_count"] += 1
                                audit["jaw_evidence"].append({
                                    "method": (
                                        "semantic_bilateral_jaw_midpoint_surface_inference"
                                    ),
                                    "side": "center",
                                    "source_vertex_indices": [
                                        left_jaw_index,
                                        right_jaw_index,
                                    ],
                                    "target_vertex_index": vertex_index,
                                    "mouth_center_vertex_index": (
                                        mouth_center_index
                                    ),
                                    "downward_progress_fraction": round(
                                        downward_progress / diagonal,
                                        7,
                                    ),
                                    "lateral_center_drift_fraction": round(
                                        lateral_center_drift / diagonal,
                                        7,
                                    ),
                                    "maximum_center_drift_fraction": round(
                                        maximum_center_drift / diagonal,
                                        7,
                                    ),
                                    "bilateral_span_position": round(
                                        span_position,
                                        7,
                                    ),
                                    "bilateral_jaw_span_fraction": round(
                                        jaw_lateral_span / diagonal,
                                        7,
                                    ),
                                    "surface_snap_fraction": round(
                                        float(nearest[1]) / diagonal,
                                        7,
                                    ),
                                    "surface_snap_limit_fraction": (
                                        tolerance_fraction
                                    ),
                                })

        # A concave or uneven jaw can place the bilateral midpoint on a
        # surface vertex that is not actually below the mouth.  Preserve that
        # midpoint rejection, then allow one semantic-axis center candidate
        # under the exact same bilateral span, lateral-center, and snap gates.
        if ("jaw", "center") not in bucket_map:
            left_jaw = bucket_map.get(("jaw", "left"))
            right_jaw = bucket_map.get(("jaw", "right"))
            center_mouth = mouth_by_side.get("center")
            if not axis_ready:
                audit["completion_rejections"].append(
                    "jaw:center:fallback_semantic_face_axis_unavailable"
                )
            elif left_jaw is None or right_jaw is None:
                audit["completion_rejections"].append(
                    "jaw:center:fallback_bilateral_jaw_surface_pair_unavailable"
                )
            elif center_mouth is None:
                audit["completion_rejections"].append(
                    "jaw:center:fallback_mouth_center_unavailable"
                )
            else:
                left_jaw_index = int(left_jaw["vertex_index"])
                right_jaw_index = int(right_jaw["vertex_index"])
                mouth_center_index = int(center_mouth["vertex_index"])
                left_jaw_point = object_points[left_jaw_index]
                right_jaw_point = object_points[right_jaw_index]
                mouth_center_point = object_points[mouth_center_index]
                jaw_lateral_span = dot(
                    subtract(right_jaw_point, left_jaw_point),
                    lateral_unit,
                )
                if jaw_lateral_span < diagonal * 0.03:
                    audit["completion_rejections"].append(
                        "jaw:center:fallback_bilateral_jaw_span_invalid"
                    )
                else:
                    desired_offset_fraction = 0.10
                    desired = add(
                        mouth_center_point,
                        scale(
                            up_unit,
                            -diagonal * desired_offset_fraction,
                        ),
                    )
                    nearest = _motion_face_nearest_object_vertex(
                        object_points,
                        desired,
                    )
                    tolerance_fraction = 0.06
                    if (
                        nearest is None
                        or nearest[1] > diagonal * tolerance_fraction
                    ):
                        audit["completion_rejections"].append(
                            "jaw:center:fallback_surface_snap_outside_bound"
                        )
                    else:
                        vertex_index = int(nearest[0])
                        candidate_point = object_points[vertex_index]
                        mouth_to_candidate = subtract(
                            candidate_point,
                            mouth_center_point,
                        )
                        downward_progress = dot(
                            mouth_to_candidate,
                            scale(up_unit, -1.0),
                        )
                        lateral_center_drift = abs(dot(
                            mouth_to_candidate,
                            lateral_unit,
                        ))
                        maximum_center_drift = min(
                            diagonal * 0.04,
                            jaw_lateral_span * 0.25,
                        )
                        span_position = dot(
                            subtract(candidate_point, left_jaw_point),
                            lateral_unit,
                        ) / jaw_lateral_span
                        rejection = ""
                        if vertex_index in {
                            left_jaw_index,
                            right_jaw_index,
                            mouth_center_index,
                        }:
                            rejection = (
                                "jaw:center:fallback_returned_noncenter_source_vertex"
                            )
                        elif downward_progress < diagonal * 0.02:
                            rejection = (
                                "jaw:center:fallback_insufficient_downward_progress"
                            )
                        elif lateral_center_drift > maximum_center_drift:
                            rejection = (
                                "jaw:center:fallback_lateral_center_drift_outside_bound"
                            )
                        elif not 0.0 <= span_position <= 1.0:
                            rejection = (
                                "jaw:center:fallback_outside_bilateral_jaw_span"
                            )
                        if rejection:
                            audit["completion_rejections"].append(rejection)
                        else:
                            world_point = _motion_face_world_point(
                                mesh_runtime,
                                vertex_index,
                            )
                            if world_point is None:
                                audit["completion_rejections"].append(
                                    "jaw:center:fallback_world_point_unavailable"
                                )
                            else:
                                side_channel_ids = (
                                    channel_ids_by_bucket.get(("jaw", "center"))
                                    or channel_ids_by_bucket.get(("mouth", "center"))
                                    or jaw_source_ids
                                )
                                candidate = {
                                    "region": "jaw",
                                    "side": "center",
                                    "controller_path": "",
                                    "controller_id": "",
                                    "controller_label": "",
                                    "channel_ids": set(side_channel_ids),
                                    "distance": float(nearest[1]),
                                    "vertex_distance": float(nearest[1]),
                                    "anchor_source": (
                                        "semantic_face_axis_center_surface_fallback"
                                    ),
                                    "anchor_sample_count": 1,
                                    "anchor_confidence": round(
                                        max(
                                            0.0,
                                            1.0 - (
                                                nearest[1]
                                                / (
                                                    diagonal
                                                    * tolerance_fraction
                                                )
                                            ),
                                        ),
                                        7,
                                    ),
                                    "vertex_index": vertex_index,
                                    "initial_world_point": world_point,
                                }
                                result.append(candidate)
                                bucket_map[("jaw", "center")] = candidate
                                audit["inferred_jaw_count"] += 1
                                audit["jaw_evidence"].append({
                                    "method": (
                                        "semantic_face_axis_center_surface_fallback"
                                    ),
                                    "side": "center",
                                    "source_vertex_indices": [
                                        left_jaw_index,
                                        right_jaw_index,
                                    ],
                                    "target_vertex_index": vertex_index,
                                    "mouth_center_vertex_index": (
                                        mouth_center_index
                                    ),
                                    "desired_offset_fraction": (
                                        desired_offset_fraction
                                    ),
                                    "downward_progress_fraction": round(
                                        downward_progress / diagonal,
                                        7,
                                    ),
                                    "lateral_center_drift_fraction": round(
                                        lateral_center_drift / diagonal,
                                        7,
                                    ),
                                    "maximum_center_drift_fraction": round(
                                        maximum_center_drift / diagonal,
                                        7,
                                    ),
                                    "bilateral_span_position": round(
                                        span_position,
                                        7,
                                    ),
                                    "bilateral_jaw_span_fraction": round(
                                        jaw_lateral_span / diagonal,
                                        7,
                                    ),
                                    "surface_snap_fraction": round(
                                        float(nearest[1]) / diagonal,
                                        7,
                                    ),
                                    "surface_snap_limit_fraction": (
                                        tolerance_fraction
                                    ),
                                })

        # Muzzle-like faces can place mouth:center at a different surface
        # depth than both side-mouth/jaw pairs.  If the midpoint and the direct
        # mouth-center axis candidate both fail, preserve the bilateral jaw
        # midpoint's non-lateral surface profile and lower it only by the
        # independently evidenced mean side-mouth-to-jaw progress.
        if ("jaw", "center") not in bucket_map:
            left_jaw = bucket_map.get(("jaw", "left"))
            right_jaw = bucket_map.get(("jaw", "right"))
            left_mouth = mouth_by_side.get("left")
            center_mouth = mouth_by_side.get("center")
            right_mouth = mouth_by_side.get("right")
            if not axis_ready:
                audit["completion_rejections"].append(
                    "jaw:center:profile_semantic_face_axis_unavailable"
                )
            elif left_jaw is None or right_jaw is None:
                audit["completion_rejections"].append(
                    "jaw:center:profile_bilateral_jaw_surface_pair_unavailable"
                )
            elif (
                left_mouth is None
                or center_mouth is None
                or right_mouth is None
            ):
                audit["completion_rejections"].append(
                    "jaw:center:profile_bilateral_mouth_evidence_unavailable"
                )
            else:
                left_jaw_index = int(left_jaw["vertex_index"])
                right_jaw_index = int(right_jaw["vertex_index"])
                left_mouth_index = int(left_mouth["vertex_index"])
                mouth_center_index = int(center_mouth["vertex_index"])
                right_mouth_index = int(right_mouth["vertex_index"])
                left_jaw_point = object_points[left_jaw_index]
                right_jaw_point = object_points[right_jaw_index]
                left_mouth_point = object_points[left_mouth_index]
                mouth_center_point = object_points[mouth_center_index]
                right_mouth_point = object_points[right_mouth_index]
                jaw_lateral_span = dot(
                    subtract(right_jaw_point, left_jaw_point),
                    lateral_unit,
                )
                left_downward = dot(
                    subtract(left_jaw_point, left_mouth_point),
                    scale(up_unit, -1.0),
                )
                right_downward = dot(
                    subtract(right_jaw_point, right_mouth_point),
                    scale(up_unit, -1.0),
                )
                minimum_downward = diagonal * 0.02
                maximum_downward = diagonal * 0.18
                maximum_side_disagreement = diagonal * 0.05
                if jaw_lateral_span < diagonal * 0.03:
                    audit["completion_rejections"].append(
                        "jaw:center:profile_bilateral_jaw_span_invalid"
                    )
                elif (
                    left_downward < minimum_downward
                    or right_downward < minimum_downward
                    or left_downward > maximum_downward
                    or right_downward > maximum_downward
                ):
                    audit["completion_rejections"].append(
                        "jaw:center:profile_side_downward_evidence_outside_bound"
                    )
                elif abs(left_downward - right_downward) > (
                    maximum_side_disagreement
                ):
                    audit["completion_rejections"].append(
                        "jaw:center:profile_side_downward_disagreement"
                    )
                else:
                    jaw_midpoint = scale(
                        add(left_jaw_point, right_jaw_point),
                        0.5,
                    )
                    midpoint_downward = dot(
                        subtract(jaw_midpoint, mouth_center_point),
                        scale(up_unit, -1.0),
                    )
                    target_downward = (
                        left_downward + right_downward
                    ) * 0.5
                    axis_adjustment = target_downward - midpoint_downward
                    desired = add(
                        jaw_midpoint,
                        scale(up_unit, -axis_adjustment),
                    )
                    profile_candidate_evidence = {
                        "stage": "bilateral_jaw_surface_profile",
                        "source_vertex_indices": [
                            left_mouth_index,
                            left_jaw_index,
                            right_mouth_index,
                            right_jaw_index,
                        ],
                        "mouth_center_vertex_index": mouth_center_index,
                        "left_downward_progress_fraction": round(
                            left_downward / diagonal,
                            7,
                        ),
                        "right_downward_progress_fraction": round(
                            right_downward / diagonal,
                            7,
                        ),
                        "side_downward_disagreement_fraction": round(
                            abs(left_downward - right_downward) / diagonal,
                            7,
                        ),
                        "midpoint_downward_progress_fraction": round(
                            midpoint_downward / diagonal,
                            7,
                        ),
                        "target_downward_progress_fraction": round(
                            target_downward / diagonal,
                            7,
                        ),
                        "axis_adjustment_fraction": round(
                            axis_adjustment / diagonal,
                            7,
                        ),
                        "bilateral_jaw_span_fraction": round(
                            jaw_lateral_span / diagonal,
                            7,
                        ),
                        "surface_snap_limit_fraction": 0.06,
                    }
                    tolerance_fraction = 0.06
                    maximum_snap_distance = (
                        diagonal * tolerance_fraction
                    )
                    maximum_center_drift = min(
                        diagonal * 0.04,
                        jaw_lateral_span * 0.25,
                    )
                    mouth_center_lateral_offset = abs(dot(
                        subtract(mouth_center_point, jaw_midpoint),
                        lateral_unit,
                    ))
                    source_indices = {
                        left_jaw_index,
                        right_jaw_index,
                        left_mouth_index,
                        mouth_center_index,
                        right_mouth_index,
                    }
                    scanned_candidates = []
                    eligible_candidates = []
                    nearest_surface = None
                    for vertex_index, candidate_point in enumerate(
                        object_points
                    ):
                        surface_distance = math.sqrt(sum(
                            (
                                float(candidate_point[axis])
                                - float(desired[axis])
                            ) ** 2
                            for axis in range(3)
                        ))
                        surface_score = (
                            float(surface_distance),
                            int(vertex_index),
                        )
                        if (
                            nearest_surface is None
                            or surface_score < nearest_surface[:2]
                        ):
                            nearest_surface = (
                                surface_score[0],
                                surface_score[1],
                                candidate_point,
                            )
                        if surface_distance > maximum_snap_distance:
                            continue
                        mouth_to_candidate = subtract(
                            candidate_point,
                            mouth_center_point,
                        )
                        downward_progress = dot(
                            mouth_to_candidate,
                            scale(up_unit, -1.0),
                        )
                        mouth_center_lateral_drift = abs(dot(
                            mouth_to_candidate,
                            lateral_unit,
                        ))
                        jaw_midpoint_lateral_drift = abs(dot(
                            subtract(candidate_point, jaw_midpoint),
                            lateral_unit,
                        ))
                        mouth_center_lateral_offset = abs(dot(
                            subtract(mouth_center_point, jaw_midpoint),
                            lateral_unit,
                        ))
                        # The profile candidate is constructed from the actual
                        # L/R jaw surface.  Its center gate therefore belongs
                        # to that jaw span, not to a potentially asymmetric or
                        # protruding mouth:center landmark.
                        lateral_center_drift = jaw_midpoint_lateral_drift
                        span_position = dot(
                            subtract(candidate_point, left_jaw_point),
                            lateral_unit,
                        ) / jaw_lateral_span
                        candidate_metrics = {
                            "target_vertex_index": int(vertex_index),
                            "downward_progress_fraction": round(
                                downward_progress / diagonal,
                                7,
                            ),
                            "jaw_midpoint_lateral_drift_fraction": round(
                                jaw_midpoint_lateral_drift / diagonal,
                                7,
                            ),
                            "mouth_center_lateral_drift_fraction": round(
                                mouth_center_lateral_drift / diagonal,
                                7,
                            ),
                            "mouth_center_lateral_offset_fraction": round(
                                mouth_center_lateral_offset / diagonal,
                                7,
                            ),
                            "maximum_center_drift_fraction": round(
                                maximum_center_drift / diagonal,
                                7,
                            ),
                            "bilateral_span_position": round(
                                span_position,
                                7,
                            ),
                            "surface_snap_fraction": round(
                                float(surface_distance) / diagonal,
                                7,
                            ),
                        }
                        candidate_rejection = ""
                        if vertex_index in source_indices:
                            candidate_rejection = (
                                "jaw:center:profile_returned_source_vertex"
                            )
                        elif downward_progress < minimum_downward:
                            candidate_rejection = (
                                "jaw:center:profile_insufficient_downward_progress"
                            )
                        elif lateral_center_drift > maximum_center_drift:
                            candidate_rejection = (
                                "jaw:center:profile_lateral_center_drift_outside_bound"
                            )
                        elif not 0.0 <= span_position <= 1.0:
                            candidate_rejection = (
                                "jaw:center:profile_outside_bilateral_jaw_span"
                            )
                        scanned_candidates.append((
                            float(surface_distance),
                            int(vertex_index),
                            candidate_point,
                            candidate_metrics,
                            candidate_rejection,
                        ))
                        if not candidate_rejection:
                            eligible_candidates.append((
                                float(surface_distance),
                                int(vertex_index),
                                candidate_point,
                                candidate_metrics,
                            ))
                    scanned_candidates.sort(
                        key=lambda item: (item[0], item[1])
                    )
                    eligible_candidates.sort(
                        key=lambda item: (item[0], item[1])
                    )
                    profile_candidate_evidence.update({
                        "surface_vertex_count": len(object_points),
                        "scanned_candidate_count": len(scanned_candidates),
                        "eligible_candidate_count": len(eligible_candidates),
                        "selection_score_policy": (
                            "surface_distance_then_vertex_index"
                        ),
                    })
                    if scanned_candidates:
                        nearest_scanned = scanned_candidates[0]
                        profile_candidate_evidence.update({
                            "nearest_scanned_vertex_index": int(
                                nearest_scanned[1]
                            ),
                            "nearest_scanned_rejection": nearest_scanned[4],
                            "nearest_scanned_metrics": dict(
                                nearest_scanned[3]
                            ),
                        })
                    if not eligible_candidates:
                        rejection = (
                            "jaw:center:profile_no_eligible_surface_vertex"
                            if scanned_candidates
                            else "jaw:center:profile_surface_snap_outside_bound"
                        )
                        audit["completion_rejections"].append(rejection)
                        profile_candidate_evidence.update({
                            "status": "rejected",
                            "rejection": rejection,
                            "target_vertex_index": (
                                int(nearest_surface[1])
                                if nearest_surface is not None
                                else -1
                            ),
                            "surface_snap_fraction": (
                                round(
                                    float(nearest_surface[0]) / diagonal,
                                    7,
                                )
                                if nearest_surface is not None
                                else None
                            ),
                        })
                        audit["jaw_center_candidate_evidence"].append(
                            profile_candidate_evidence
                        )
                    else:
                        (
                            selected_distance,
                            vertex_index,
                            candidate_point,
                            selected_metrics,
                        ) = eligible_candidates[0]
                        nearest = (vertex_index, selected_distance)
                        mouth_to_candidate = subtract(
                            candidate_point,
                            mouth_center_point,
                        )
                        downward_progress = dot(
                            mouth_to_candidate,
                            scale(up_unit, -1.0),
                        )
                        mouth_center_lateral_drift = abs(dot(
                            mouth_to_candidate,
                            lateral_unit,
                        ))
                        jaw_midpoint_lateral_drift = abs(dot(
                            subtract(candidate_point, jaw_midpoint),
                            lateral_unit,
                        ))
                        lateral_center_drift = jaw_midpoint_lateral_drift
                        span_position = dot(
                            subtract(candidate_point, left_jaw_point),
                            lateral_unit,
                        ) / jaw_lateral_span
                        profile_candidate_evidence.update(selected_metrics)
                        profile_candidate_evidence.update({
                            "selected_score": [
                                round(selected_distance / diagonal, 7),
                                int(vertex_index),
                            ],
                        })
                        world_point = _motion_face_world_point(
                            mesh_runtime,
                            vertex_index,
                        )
                        if world_point is None:
                            rejection = (
                                "jaw:center:profile_world_point_unavailable"
                            )
                            audit["completion_rejections"].append(rejection)
                            profile_candidate_evidence.update({
                                "status": "rejected",
                                "rejection": rejection,
                            })
                            audit["jaw_center_candidate_evidence"].append(
                                profile_candidate_evidence
                            )
                        else:
                                side_channel_ids = (
                                    channel_ids_by_bucket.get(("jaw", "center"))
                                    or channel_ids_by_bucket.get(("mouth", "center"))
                                    or jaw_source_ids
                                )
                                candidate = {
                                    "region": "jaw",
                                    "side": "center",
                                    "controller_path": "",
                                    "controller_id": "",
                                    "controller_label": "",
                                    "channel_ids": set(side_channel_ids),
                                    "distance": float(nearest[1]),
                                    "vertex_distance": float(nearest[1]),
                                    "anchor_source": (
                                        "semantic_bilateral_jaw_surface_profile_inference"
                                    ),
                                    "anchor_sample_count": 4,
                                    "anchor_confidence": round(
                                        max(
                                            0.0,
                                            1.0 - (
                                                nearest[1]
                                                / (
                                                    diagonal
                                                    * tolerance_fraction
                                                )
                                            ),
                                        ),
                                        7,
                                    ),
                                    "vertex_index": vertex_index,
                                    "initial_world_point": world_point,
                                }
                                result.append(candidate)
                                bucket_map[("jaw", "center")] = candidate
                                audit["inferred_jaw_count"] += 1
                                profile_candidate_evidence.update({
                                    "status": "accepted",
                                    "rejection": "",
                                })
                                audit["jaw_center_candidate_evidence"].append(
                                    profile_candidate_evidence
                                )
                                audit["jaw_evidence"].append({
                                    "method": (
                                        "semantic_bilateral_jaw_surface_profile_inference"
                                    ),
                                    "side": "center",
                                    "source_vertex_indices": [
                                        left_mouth_index,
                                        left_jaw_index,
                                        right_mouth_index,
                                        right_jaw_index,
                                    ],
                                    "target_vertex_index": vertex_index,
                                    "mouth_center_vertex_index": (
                                        mouth_center_index
                                    ),
                                    "left_downward_progress_fraction": round(
                                        left_downward / diagonal,
                                        7,
                                    ),
                                    "right_downward_progress_fraction": round(
                                        right_downward / diagonal,
                                        7,
                                    ),
                                    "side_downward_disagreement_fraction": round(
                                        abs(left_downward - right_downward)
                                        / diagonal,
                                        7,
                                    ),
                                    "midpoint_downward_progress_fraction": round(
                                        midpoint_downward / diagonal,
                                        7,
                                    ),
                                    "target_downward_progress_fraction": round(
                                        target_downward / diagonal,
                                        7,
                                    ),
                                    "axis_adjustment_fraction": round(
                                        axis_adjustment / diagonal,
                                        7,
                                    ),
                                    "downward_progress_fraction": round(
                                        downward_progress / diagonal,
                                        7,
                                    ),
                                    "lateral_center_drift_fraction": round(
                                        lateral_center_drift / diagonal,
                                        7,
                                    ),
                                    "jaw_midpoint_lateral_drift_fraction": round(
                                        jaw_midpoint_lateral_drift / diagonal,
                                        7,
                                    ),
                                    "mouth_center_lateral_drift_fraction": round(
                                        mouth_center_lateral_drift / diagonal,
                                        7,
                                    ),
                                    "mouth_center_lateral_offset_fraction": round(
                                        mouth_center_lateral_offset / diagonal,
                                        7,
                                    ),
                                    "maximum_center_drift_fraction": round(
                                        maximum_center_drift / diagonal,
                                        7,
                                    ),
                                    "bilateral_span_position": round(
                                        span_position,
                                        7,
                                    ),
                                    "bilateral_jaw_span_fraction": round(
                                        jaw_lateral_span / diagonal,
                                        7,
                                    ),
                                    "surface_snap_fraction": round(
                                        float(nearest[1]) / diagonal,
                                        7,
                                    ),
                                    "surface_snap_limit_fraction": (
                                        tolerance_fraction
                                    ),
                                })
    return result, audit


def _motion_face_prepare_landmarks(
    root,
    face_surface,
    channels,
):
    runtime = _motion_face_mesh_runtime(face_surface) if face_surface else None
    diagonal = _motion_face_surface_diagonal(face_surface) if face_surface else 0.0
    if runtime is None or diagonal <= 0.0:
        return [], [], [], {
            "candidate_controller_count": 0,
            "landmark_count": 0,
            "edge_count": 0,
            "raster_ready": False,
            "reason": "face_surface_unavailable",
            "surface_diagonal": diagonal,
        }
    candidates = {}
    controller_nodes = set()
    evaluated_controller_nodes = set()
    rejected_remote_controller_nodes = set()
    accepted_anchor_sources = {}
    maximum_surface_distance = diagonal * 0.08
    delta_candidates, delta_audit = _motion_face_delta_landmark_candidates(
        runtime,
        face_surface,
        channels,
    )
    for channel in channels or []:
        if not channel.get("raster_eligible"):
            continue
        for controller_plug in channel.get("controller_plugs", []):
            node = _clean(controller_plug).split(".", 1)[0]
            path = _motion_face_controller_path(node, root=root)
            if not path:
                continue
            evaluated_controller_nodes.add(path)
            side = _clean(channel.get("side")) or "center"
            controller_semantic = _motion_face_semantic(
                _dag_leaf_without_namespace(path),
                path,
            )
            if side == "center" and controller_semantic["side"] != "center":
                side = controller_semantic["side"]
            region = _clean(channel.get("group")) or "unknown"
            key = (region, side, path)
            if key in candidates:
                candidates[key]["channel_ids"].add(channel["id"])
                continue
            anchor_options = []
            for anchor in _motion_face_controller_anchor_points(path):
                nearest = _motion_face_nearest_vertex(
                    runtime,
                    anchor["point"],
                )
                if nearest is None:
                    continue
                if nearest["surface_distance"] > maximum_surface_distance:
                    continue
                anchor_options.append((
                    float(nearest["surface_distance"]),
                    float(nearest["vertex_distance"]),
                    anchor["source"],
                    anchor,
                    nearest,
                ))
            if not anchor_options:
                rejected_remote_controller_nodes.add(path)
                continue
            anchor_options.sort(key=lambda item: (item[0], item[1], item[2]))
            _surface_distance, _vertex_distance, _source, anchor, nearest = (
                anchor_options[0]
            )
            controller_nodes.add(path)
            accepted_anchor_sources[anchor["source"]] = int(
                accepted_anchor_sources.get(anchor["source"]) or 0
            ) + 1
            candidates[key] = {
                "region": region,
                "side": side,
                "controller_path": path,
                "controller_id": _motion_face_node_uuid(path),
                "controller_label": _dag_leaf_without_namespace(path),
                "channel_ids": {channel["id"]},
                "distance": float(nearest["surface_distance"]),
                "vertex_distance": float(nearest["vertex_distance"]),
                "anchor_source": anchor["source"],
                "anchor_sample_count": int(anchor.get("sample_count") or 0),
                "anchor_confidence": round(max(
                    0.0,
                    1.0 - (
                        float(nearest["surface_distance"])
                        / maximum_surface_distance
                    ),
                ), 7),
                "vertex_index": int(nearest["vertex_index"]),
                "initial_world_point": list(nearest["vertex_point"]),
            }

    by_bucket = {}
    for candidate in candidates.values():
        by_bucket.setdefault(
            (candidate["region"], candidate["side"]),
            [],
        ).append(candidate)
    # Stored Blend Shape deltas are the only direct evidence of which face
    # surface actually deforms.  Controller locations are retained strictly as
    # a close-to-surface fallback and never override a delta-localized bucket.
    chosen = list(delta_candidates)
    delta_buckets = set(
        (item["region"], item["side"])
        for item in delta_candidates
    )
    for bucket in sorted(by_bucket):
        if bucket in delta_buckets:
            continue
        ranked = sorted(
            by_bucket[bucket],
            key=lambda item: (
                item["distance"],
                item["controller_path"],
            ),
        )
        chosen.extend(ranked[:2])
    chosen = sorted(
        chosen,
        key=lambda item: (
            item["region"],
            item["side"],
            item["initial_world_point"][0],
            item["controller_path"],
        ),
    )[:20]

    # Several controls on a 2D face panel can snap to the same coarse face
    # vertex.  Such duplicates are one spatial observation, not independent
    # landmarks.  Keep the closest provenance record and merge only channel
    # identity into it; raw controller curves are never retained or drawn.
    raw_chosen_count = len(chosen)
    by_vertex = {}
    for candidate in sorted(
        chosen,
        key=lambda item: (
            item["distance"],
            item["vertex_distance"],
            item["controller_path"],
        ),
    ):
        vertex_key = (
            int(candidate["vertex_index"]),
            candidate["region"],
            candidate["side"],
        )
        existing = by_vertex.get(vertex_key)
        if existing is None:
            by_vertex[vertex_key] = candidate
        else:
            existing["channel_ids"].update(candidate["channel_ids"])
    chosen = sorted(
        by_vertex.values(),
        key=lambda item: (
            item["region"],
            item["side"],
            item["initial_world_point"][0],
            item["controller_path"],
        ),
    )
    chosen, completion_audit = _motion_face_complete_bilateral_and_jaw(
        chosen,
        runtime,
        channels,
    )
    semantic_unique = {}
    for candidate in chosen:
        semantic_unique.setdefault(
            (
                candidate["region"],
                candidate["side"],
                int(candidate["vertex_index"]),
            ),
            candidate,
        )
    chosen = sorted(
        semantic_unique.values(),
        key=lambda item: (
            item["region"],
            item["side"],
            item["initial_world_point"][0],
            item["controller_path"],
        ),
    )[:20]
    accepted_anchor_sources = {}
    for candidate in chosen:
        accepted_anchor_sources[candidate["anchor_source"]] = int(
            accepted_anchor_sources.get(candidate["anchor_source"]) or 0
        ) + 1

    initial_surface_span = 0.0
    for first_index, first in enumerate(chosen):
        for second in chosen[first_index + 1:]:
            span = math.sqrt(sum(
                (
                    float(first["initial_world_point"][axis])
                    - float(second["initial_world_point"][axis])
                ) ** 2
                for axis in range(3)
            ))
            initial_surface_span = max(initial_surface_span, span)

    landmarks = []
    landmark_runtime = []
    for candidate in chosen:
        stable_source = "{0}:{1}:{2}:{3}:{4}".format(
            runtime["shape_id"],
            candidate["vertex_index"],
            candidate["region"],
            candidate["side"],
            candidate["controller_id"],
        )
        landmark_id = "face:" + hashlib.sha256(
            stable_source.encode("utf-8")
        ).hexdigest()[:24]
        record = {
            "id": landmark_id,
            "region": candidate["region"],
            "side": candidate["side"],
            "controller_id": candidate["controller_id"],
            "controller_label": candidate["controller_label"],
            "mesh_id": runtime["shape_id"],
            "mesh": face_surface,
            "vertex_index": candidate["vertex_index"],
            "channel_ids": sorted(candidate["channel_ids"]),
            "surface_snap_distance": round(candidate["distance"], 7),
            "surface_vertex_distance": round(
                candidate["vertex_distance"],
                7,
            ),
            "anchor_source": candidate["anchor_source"],
            "anchor_method": candidate["anchor_source"],
            "anchor_confidence": float(
                candidate.get("anchor_confidence") or 0.0
            ),
            "anchor_sample_count": candidate["anchor_sample_count"],
        }
        landmarks.append(record)
        landmark_runtime.append({
            "id": landmark_id,
            "region": candidate["region"],
            "side": candidate["side"],
            "vertex_index": candidate["vertex_index"],
            "initial_world_point": candidate["initial_world_point"],
            "mesh_runtime": runtime,
        })

    edge_set = set()
    edges = []
    groups = {}
    for item in landmark_runtime:
        groups.setdefault((item["region"], item["side"]), []).append(item)
    contour_items = {"mouth": [], "jaw": []}
    for group_key, items in groups.items():
        ordered = sorted(
            items,
            key=lambda item: (
                item["initial_world_point"][0],
                item["id"],
            ),
        )
        if group_key[0] in contour_items:
            contour_items[group_key[0]].extend(ordered)
        for edge_index in range(1, len(ordered)):
            pair = (ordered[edge_index - 1]["id"], ordered[edge_index]["id"])
            if pair not in edge_set:
                edge_set.add(pair)
                edges.append({"from": pair[0], "to": pair[1], "region": group_key[0]})
    for contour_region, region_items in contour_items.items():
        ordered_region = sorted(
            region_items,
            key=lambda item: (
                item["initial_world_point"][0],
                item["id"],
            ),
        )
        for edge_index in range(1, len(ordered_region)):
            pair = (
                ordered_region[edge_index - 1]["id"],
                ordered_region[edge_index]["id"],
            )
            if pair not in edge_set:
                edge_set.add(pair)
                edges.append({
                    "from": pair[0],
                    "to": pair[1],
                    "region": contour_region,
                })
    unique_vertex_count = len(set(
        int(item["vertex_index"])
        for item in landmarks
    ))
    semantic_region_count = len(set(
        _clean(item["region"])
        for item in landmarks
        if _clean(item["region"])
    ))
    semantic_slots = set(
        "{0}:{1}".format(item["region"], item["side"])
        for item in landmarks
    )
    required_semantic_slots = {
        "brow:left",
        "brow:right",
        "eyelid:left",
        "eyelid:right",
        "mouth:left",
        "mouth:center",
        "mouth:right",
        "jaw:left",
        "jaw:center",
        "jaw:right",
    }
    missing_semantic_slots = sorted(required_semantic_slots - semantic_slots)
    minimum_surface_span = diagonal * 0.02
    raster_ready = bool(
        unique_vertex_count >= 2
        and semantic_region_count >= 1
        and initial_surface_span >= minimum_surface_span
        and edges
        and not missing_semantic_slots
    )
    if unique_vertex_count < 2:
        readiness_reason = "insufficient_unique_surface_vertices"
    elif semantic_region_count < 1:
        readiness_reason = "insufficient_face_semantic_regions"
    elif initial_surface_span < minimum_surface_span:
        readiness_reason = "insufficient_initial_surface_span"
    elif not edges:
        readiness_reason = "no_defined_face_edge"
    elif missing_semantic_slots:
        readiness_reason = "incomplete_minimum_face_semantic_slots"
    else:
        readiness_reason = "surface_pinned_semantic_landmarks_ready"
    return landmarks, edges, landmark_runtime, {
        "candidate_controller_count": len(controller_nodes),
        "evaluated_controller_count": len(evaluated_controller_nodes),
        "rejected_remote_controller_count": len(
            rejected_remote_controller_nodes
        ),
        "accepted_anchor_sources": dict(accepted_anchor_sources),
        "delta_localization": dict(delta_audit),
        "surface_completion": dict(completion_audit),
        "raw_landmark_candidate_count": raw_chosen_count,
        "duplicate_vertex_candidate_count": max(
            0,
            raw_chosen_count - unique_vertex_count,
        ),
        "landmark_count": len(landmarks),
        "unique_vertex_count": unique_vertex_count,
        "semantic_region_count": semantic_region_count,
        "edge_count": len(edges),
        "raster_ready": raster_ready,
        "reason": readiness_reason,
        "surface_diagonal": round(diagonal, 7),
        "surface_distance_threshold": round(maximum_surface_distance, 7),
        "initial_surface_span": round(initial_surface_span, 7),
        "minimum_surface_span": round(minimum_surface_span, 7),
        "semantic_slots": sorted(semantic_slots),
        "required_semantic_slots": sorted(required_semantic_slots),
        "missing_semantic_slots": missing_semantic_slots,
        "complete_semantic_slots": not missing_semantic_slots,
    }


def _motion_target_records(bindings, hidden_paths=None, job=None, with_report=False):
    records = []
    seen_roots = set()
    seen_target_signatures = set()
    audit = {
        "input_target_count": len(bindings or []),
        "duplicate_root_count": 0,
        "duplicate_skeleton_count": 0,
        "excluded_joint_count": 0,
        "truncated_joint_count": 0,
        "selected_joint_count": 0,
        "excluded_by_reason": {},
        "face_target_count": 0,
        "face_channel_count": 0,
        "face_driver_count": 0,
        "face_landmark_count": 0,
        "face_raster_ready_target_count": 0,
        "face_semantic_surface_count": 0,
        "face_truncated_channel_count": 0,
        "face_truncated_driver_count": 0,
    }
    for order, binding in enumerate(bindings or [], 1):
        root = _clean(
            binding.get("full_dag_path")
            or binding.get("subject_root")
        )
        if not root or not cmds.objExists(root):
            continue
        if root in seen_roots:
            audit["duplicate_root_count"] += 1
            continue
        if _picker_path_is_hidden(root, hidden_paths):
            continue
        seen_roots.add(root)
        marker = _clean(binding.get("color"))
        shapes = _motion_target_shapes(root, job=job)
        joints, selection = _motion_joint_selection(
            root,
            shapes=shapes,
            allow_skeleton=marker not in BACKGROUND_MARKERS,
            allow_reference_fallback=(
                marker in CHARACTER_MARKERS or not marker
            ),
        )
        joints = [
            joint for joint in joints
            if not _picker_path_is_hidden(joint, hidden_paths)
        ]
        selection["selected_joint_count"] = len(joints)
        if marker in BACKGROUND_MARKERS:
            face_surface, face_surface_audit = "", {
                "candidate_count": 0,
                "selected_score": None,
                "reason": "background_marker_face_disabled",
            }
        else:
            face_surface, face_surface_audit = _motion_face_surface(shapes)
        face_channels, face_drivers, face_discovery = _motion_face_channels(
            root,
            shapes,
            marker=marker,
        )
        (
            face_landmarks,
            face_edges,
            face_landmark_runtime,
            face_landmark_audit,
        ) = _motion_face_prepare_landmarks(
            root,
            face_surface,
            face_channels,
        )
        existing_face_edge_regions = set(
            _clean(item.get("region"))
            for item in face_edges
            if _clean(item.get("region"))
        )
        (
            semantic_mesh_landmarks,
            semantic_mesh_edges,
            semantic_mesh_runtime,
            semantic_mesh_audit,
        ) = _motion_face_semantic_surface_landmarks(
            shapes,
            face_channels,
            existing_regions=existing_face_edge_regions,
            job=job,
        )
        face_landmarks.extend(semantic_mesh_landmarks)
        face_edges.extend(semantic_mesh_edges)
        face_landmark_runtime.extend(semantic_mesh_runtime)
        face_landmark_audit["semantic_mesh_fallback"] = (
            semantic_mesh_audit
        )
        raster_ready_regions = sorted(set(
            _clean(item.get("region"))
            for item in face_edges
            if _clean(item.get("region"))
        ))
        face_landmark_audit["raster_ready_regions"] = (
            raster_ready_regions
        )
        if semantic_mesh_edges and not face_landmark_audit.get("raster_ready"):
            face_landmark_audit["raster_ready"] = True
            face_landmark_audit["reason"] = (
                "region_local_semantic_mesh_edges_ready"
            )
        semantic_diagonals = [
            float(item.get("surface_diagonal") or 0.0)
            for item in semantic_mesh_audit.get("surfaces", [])
        ]
        if semantic_diagonals:
            face_landmark_audit["surface_diagonal"] = round(max(
                [float(face_landmark_audit.get("surface_diagonal") or 0.0)]
                + semantic_diagonals
            ), 7)
        if joints or face_channels:
            signature = (
                _motion_joint_signature(joints),
                tuple(sorted(item["id"] for item in face_channels)),
            )
            if signature in seen_target_signatures:
                audit["duplicate_skeleton_count"] += 1
                continue
            seen_target_signatures.add(signature)
        audit["selected_joint_count"] += len(joints)
        audit["excluded_joint_count"] += int(
            selection.get("excluded_joint_count") or 0
        )
        audit["truncated_joint_count"] += int(
            selection.get("truncated_joint_count") or 0
        )
        for reason, count in selection.get("excluded_by_reason", {}).items():
            audit["excluded_by_reason"][reason] = int(
                audit["excluded_by_reason"].get(reason) or 0
            ) + int(count or 0)
        if face_channels:
            audit["face_target_count"] += 1
        audit["face_channel_count"] += len(face_channels)
        audit["face_driver_count"] += len(face_drivers)
        audit["face_landmark_count"] += len(face_landmarks)
        audit["face_semantic_surface_count"] += int(
            semantic_mesh_audit.get("accepted_surface_count") or 0
        )
        audit["face_truncated_channel_count"] += int(
            face_discovery.get("truncated_channel_count") or 0
        )
        audit["face_truncated_driver_count"] += int(
            face_discovery.get("truncated_driver_count") or 0
        )
        if face_landmark_audit.get("raster_ready"):
            audit["face_raster_ready_target_count"] += 1
        selected = set(joints)
        parent_by_joint = dict(
            (joint, _motion_nearest_selected_parent(joint, selected))
            for joint in joints
        )
        records.append({
            "target_index": len(records) + 1,
            "picker_order": int(binding.get("picker_order") or order),
            "asset_id": _clean(
                binding.get("asset_id")
                or binding.get("group_name")
                or _dag_leaf_without_namespace(root)
            ),
            "source_root": root,
            "marker": marker,
            "mode": "joint_hierarchy" if joints else "rigid_transform",
            "joints": joints,
            "root_joint": _motion_root_joint(joints),
            "root_source": (
                "semantic_joint"
                if _motion_root_joint(joints)
                else "target_transform"
            ),
            "parent_by_joint": parent_by_joint,
            "shapes": shapes,
            "joint_selection": selection,
            "face_surface": face_surface,
            "face_surface_audit": face_surface_audit,
            "face_channels": face_channels,
            "face_drivers": face_drivers,
            "face_discovery": face_discovery,
            "face_landmarks": face_landmarks,
            "face_edges": face_edges,
            "face_landmark_runtime": face_landmark_runtime,
            "face_landmark_audit": face_landmark_audit,
            "face_semantic_surface_audit": semantic_mesh_audit,
        })
    audit["output_target_count"] = len(records)
    return (records, audit) if with_report else records


def _unassigned_motion_bindings(hidden_paths=None):
    """Discover optional Motion targets without requiring Color Assignment.

    The same asset-root discovery used by READ is filtered to roots that are
    authored-visible now or have driven visibility, and Picker eye exclusions
    remain authoritative.  No visibility attribute is changed.
    """
    records = []
    for order, node in enumerate(_scan_outliner_nodes(), 1):
        root = _clean(node.get("full_path"))
        if not root or _picker_path_is_hidden(root, hidden_paths):
            continue
        if not bool(node.get("scene_visible")) and not bool(
            node.get("visibility_driven")
        ):
            continue
        records.append({
            "full_dag_path": root,
            "subject_root": root,
            "group_name": _clean(node.get("name")) or _dag_leaf_without_namespace(root),
            "asset_id": _clean(node.get("name")) or _dag_leaf_without_namespace(root),
            "color": "",
            "picker_order": order,
            "enabled": True,
        })
    return records


def _motion_camera_projection(camera, width, height):
    """Build a render-aspect-aware camera projection using Maya API 2.0."""
    try:
        import maya.api.OpenMaya as om
    except Exception as exc:
        raise RuntimeError(
            "Maya API 2.0 is required for Motion Guide projection ({0}).".format(
                exc
            )
        )
    selection = om.MSelectionList()
    selection.add(camera)
    dag_path = selection.getDagPath(0)
    if not dag_path.node().hasFn(om.MFn.kCamera):
        dag_path.extendToShape()
    camera_fn = om.MFnCamera(dag_path)
    camera_world_matrix = dag_path.inclusiveMatrix()
    camera_origin_point = om.MPoint(0.0, 0.0, 0.0, 1.0) * camera_world_matrix
    aspect = float(width) / float(max(1, height))
    near_clip = float(camera_fn.nearClippingPlane)
    is_ortho = camera_fn.isOrtho
    if callable(is_ortho):
        is_ortho = is_ortho()
    try:
        if is_ortho:
            frustum = camera_fn.getOrthoViewingFrustum(aspect)
        else:
            frustum = camera_fn.getViewingFrustum(aspect, True, True)
        left, right, bottom, top = [float(value) for value in frustum[:4]]
    except Exception:
        camera_shape = dag_path.fullPathName()
        horizontal = float(
            cmds.getAttr(camera_shape + ".horizontalFilmAperture")
        ) * 25.4
        vertical = float(
            cmds.getAttr(camera_shape + ".verticalFilmAperture")
        ) * 25.4
        focal = max(
            0.001,
            float(cmds.getAttr(camera_shape + ".focalLength")),
        )
        half_width = near_clip * horizontal * 0.5 / focal
        half_height = near_clip * vertical * 0.5 / focal
        film_aspect = half_width / max(1.0e-8, half_height)
        if aspect > film_aspect:
            half_width = half_height * aspect
        else:
            half_height = half_width / max(1.0e-8, aspect)
        left, right = -half_width, half_width
        bottom, top = -half_height, half_height
    return {
        "om": om,
        "camera_inverse": dag_path.inclusiveMatrixInverse(),
        "camera_origin": [
            float(camera_origin_point.x),
            float(camera_origin_point.y),
            float(camera_origin_point.z),
        ],
        "near": near_clip,
        "is_ortho": bool(is_ortho),
        "left": left,
        "right": right,
        "bottom": bottom,
        "top": top,
        "width": int(width),
        "height": int(height),
    }


def _motion_project_point(context, world_point):
    om = context["om"]
    point = om.MPoint(
        float(world_point[0]),
        float(world_point[1]),
        float(world_point[2]),
        1.0,
    ) * context["camera_inverse"]
    distance = -float(point.z)
    if not math.isfinite(distance) or distance <= 1.0e-6:
        return None
    if context["is_ortho"]:
        projected_x = float(point.x)
        projected_y = float(point.y)
    else:
        scale = float(context["near"]) / distance
        projected_x = float(point.x) * scale
        projected_y = float(point.y) * scale
    span_x = float(context["right"]) - float(context["left"])
    span_y = float(context["top"]) - float(context["bottom"])
    if abs(span_x) <= 1.0e-12 or abs(span_y) <= 1.0e-12:
        return None
    normalized_x = (
        projected_x - float(context["left"])
    ) / span_x
    normalized_y = (
        projected_y - float(context["bottom"])
    ) / span_y
    pixel_x = normalized_x * float(max(1, context["width"] - 1))
    pixel_y = (
        1.0 - normalized_y
    ) * float(max(1, context["height"] - 1))
    return {
        "x": pixel_x,
        "y": pixel_y,
        "x_norm": normalized_x,
        "y_norm": 1.0 - normalized_y,
        "camera_depth": distance,
        "in_frame": (
            0.0 <= normalized_x <= 1.0
            and 0.0 <= normalized_y <= 1.0
        ),
    }


def _motion_world_position(path):
    value = cmds.xform(path, query=True, worldSpace=True, translation=True)
    return [float(value[0]), float(value[1]), float(value[2])]


def _motion_root_world_position(root):
    try:
        bounds = cmds.exactWorldBoundingBox(root)
    except Exception:
        bounds = []
    if isinstance(bounds, (list, tuple)) and len(bounds) == 6:
        return [
            (float(bounds[0]) + float(bounds[3])) * 0.5,
            (float(bounds[1]) + float(bounds[4])) * 0.5,
            (float(bounds[2]) + float(bounds[5])) * 0.5,
        ]
    return _motion_world_position(root)


def _motion_joint_color(joint, is_root=False):
    if is_root:
        return MOTION_GUIDE_ROOT_RGB
    leaf = _dag_leaf_without_namespace(joint).lower()
    if any(token in leaf for token in ("hand", "wrist", "finger", "thumb")):
        return MOTION_GUIDE_HAND_RGB
    if any(token in leaf for token in ("foot", "ankle", "toe")):
        return MOTION_GUIDE_FOOT_RGB
    return MOTION_GUIDE_JOINT_RGB


def _motion_canvas(width, height):
    color = bytes(MOTION_GUIDE_BACKGROUND_RGB)
    return bytearray(color * int(width * height))


def _motion_put_pixel(canvas, width, height, x, y, rgb):
    x = int(x)
    y = int(y)
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    index = (y * width + x) * 3
    canvas[index:index + 3] = bytes(rgb)


def _motion_draw_circle(canvas, width, height, center_x, center_y, radius, rgb):
    center_x = int(round(center_x))
    center_y = int(round(center_y))
    radius = max(1, int(radius))
    radius_sq = radius * radius
    for y in range(center_y - radius, center_y + radius + 1):
        for x in range(center_x - radius, center_x + radius + 1):
            if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius_sq:
                _motion_put_pixel(canvas, width, height, x, y, rgb)


def _motion_draw_line(
    canvas,
    width,
    height,
    start_x,
    start_y,
    end_x,
    end_y,
    rgb,
    thickness=2,
):
    x0 = int(round(start_x))
    y0 = int(round(start_y))
    x1 = int(round(end_x))
    y1 = int(round(end_y))
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    step_x = 1 if x0 < x1 else -1
    step_y = 1 if y0 < y1 else -1
    error = dx + dy
    radius = max(0, int(thickness) // 2)
    while True:
        if radius:
            _motion_draw_circle(
                canvas,
                width,
                height,
                x0,
                y0,
                radius,
                rgb,
            )
        else:
            _motion_put_pixel(canvas, width, height, x0, y0, rgb)
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += step_x
        if doubled <= dx:
            error += dx
            y0 += step_y


def _motion_face_region_color(region):
    return {
        "brow": MOTION_GUIDE_FACE_BROW_RGB,
        "eyelid": MOTION_GUIDE_FACE_EYE_RGB,
        "mouth": MOTION_GUIDE_FACE_MOUTH_RGB,
        "jaw": MOTION_GUIDE_FACE_JAW_RGB,
    }.get(_clean(region), MOTION_GUIDE_FACE_MOUTH_RGB)


def _motion_face_occlusion_meshes(targets):
    if not any(
        target.get("face_landmark_runtime")
        for target in (targets or [])
    ):
        return []
    records = []
    seen = set()
    for target in targets or []:
        if target.get("marker") in BACKGROUND_MARKERS:
            continue
        for shape in target.get("shapes", []):
            shape = _clean(shape)
            if not shape or shape in seen:
                continue
            seen.add(shape)
            runtime = _motion_face_mesh_runtime(shape)
            if runtime is None:
                continue
            runtime["target_index"] = target["target_index"]
            records.append(runtime)
    return records


def _motion_face_visible_occlusion_meshes(
    mesh_records,
    path_visible,
    performance=None,
):
    """Filter face ray meshes once for the current evaluated Maya frame."""
    visible = []
    for record in mesh_records or []:
        _motion_perf_increment(
            performance,
            "face_occluder_candidate_mesh_sample_count",
        )
        if path_visible(record.get("shape")):
            visible.append(record)
            _motion_perf_increment(
                performance,
                "face_occluder_visible_mesh_sample_count",
            )
    return visible


def _motion_face_closest_ray_hit(
    camera_origin,
    world_point,
    visible_mesh_records,
    max_extra_distance,
    performance=None,
):
    """Return the first hit from records prefiltered for this Maya frame."""
    vector = [
        float(world_point[index]) - float(camera_origin[index])
        for index in range(3)
    ]
    distance = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(distance) or distance <= 1.0e-8:
        return None
    direction = [value / distance for value in vector]
    maximum = distance + max(0.001, float(max_extra_distance))
    nearest = None
    for record in visible_mesh_records or []:
        shape = record["shape"]
        om = record["om"]
        mesh_function = record["mesh_function"]
        _motion_perf_increment(
            performance,
            "face_mesh_intersection_test_count",
        )
        try:
            result = mesh_function.closestIntersection(
                om.MFloatPoint(
                    float(camera_origin[0]),
                    float(camera_origin[1]),
                    float(camera_origin[2]),
                ),
                om.MFloatVector(
                    float(direction[0]),
                    float(direction[1]),
                    float(direction[2]),
                ),
                om.MSpace.kWorld,
                float(maximum),
                False,
            )
        except Exception:
            result = None
        if not result or len(result) < 2:
            continue
        try:
            ray_parameter = float(result[1])
        except Exception:
            continue
        if ray_parameter < 0.0 or not math.isfinite(ray_parameter):
            continue
        if nearest is None or ray_parameter < nearest["distance"]:
            nearest = {
                "distance": ray_parameter,
                "shape": shape,
                "target_index": record["target_index"],
                "point_distance": distance,
            }
    return nearest


def _motion_face_landmark_projection_sample(
    landmark_runtime,
    projection,
):
    runtime = landmark_runtime["mesh_runtime"]
    om = runtime["om"]
    mesh_function = runtime["mesh_function"]
    vertex_index = int(landmark_runtime["vertex_index"])
    try:
        point = mesh_function.getPoint(vertex_index, om.MSpace.kWorld)
        normal = mesh_function.getVertexNormal(
            vertex_index,
            True,
            om.MSpace.kWorld,
        )
        world_point = [float(point.x), float(point.y), float(point.z)]
        world_normal = [float(normal.x), float(normal.y), float(normal.z)]
    except Exception:
        return None
    projected = _motion_project_point(projection, world_point)
    if projected is None:
        return None
    camera_origin = projection["camera_origin"]
    view = [
        float(camera_origin[index]) - float(world_point[index])
        for index in range(3)
    ]
    view_length = math.sqrt(sum(value * value for value in view))
    normal_length = math.sqrt(sum(value * value for value in world_normal))
    facing_dot = -1.0
    if view_length > 1.0e-8 and normal_length > 1.0e-8:
        facing_dot = sum(
            (view[index] / view_length)
            * (world_normal[index] / normal_length)
            for index in range(3)
        )
    front_facing = facing_dot > 0.15
    return {
        "id": landmark_runtime["id"],
        "region": landmark_runtime["region"],
        "side": landmark_runtime["side"],
        "x": round(float(projected["x_norm"]), 7),
        "y": round(float(projected["y_norm"]), 7),
        "camera_depth": round(float(projected["camera_depth"]), 7),
        "in_frame": bool(projected["in_frame"]),
        "front_facing": bool(front_facing),
        "normal_view_dot": round(float(facing_dot), 7),
        "camera_ray_visible": False,
        "visible": False,
        "occluder_shape": "",
        "_pixel_x": float(projected["x"]),
        "_pixel_y": float(projected["y"]),
        "_world_point": world_point,
        "_surface_shape": _clean(runtime["shape"]),
    }


def _motion_face_apply_ray_visibility(
    sample,
    projection,
    target_index,
    visible_mesh_records,
    face_diagonal,
    performance=None,
):
    """Apply the strict first-hit face visibility rule to one candidate."""
    if not (
        sample
        and sample.get("front_facing")
        and sample.get("in_frame")
    ):
        return sample
    _motion_perf_increment(
        performance,
        "face_landmark_ray_test_count",
    )
    hit = _motion_face_closest_ray_hit(
        projection["camera_origin"],
        sample["_world_point"],
        visible_mesh_records,
        max(
            float(face_diagonal)
            * MOTION_GUIDE_FACE_FIRST_HIT_TOLERANCE_FRACTION,
            0.001,
        ),
        performance=performance,
    )
    ray_visible = False
    if hit is not None:
        tolerance = max(
            float(face_diagonal)
            * MOTION_GUIDE_FACE_FIRST_HIT_TOLERANCE_FRACTION,
            0.001,
        )
        ray_visible = bool(
            int(hit["target_index"]) == int(target_index)
            and _clean(hit["shape"]) == _clean(sample["_surface_shape"])
            and abs(
                float(hit["point_distance"])
                - float(hit["distance"])
            ) <= tolerance
        )
    sample["camera_ray_visible"] = bool(ray_visible)
    sample["visible"] = bool(ray_visible)
    sample["occluder_shape"] = _clean(hit.get("shape")) if hit else ""
    return sample


def _motion_face_landmark_sample(
    landmark_runtime,
    projection,
    target_index,
    visible_mesh_records,
    face_diagonal,
    performance=None,
):
    """Compatibility helper for one complete projection and ray sample."""
    sample = _motion_face_landmark_projection_sample(
        landmark_runtime,
        projection,
    )
    return _motion_face_apply_ray_visibility(
        sample,
        projection,
        target_index,
        visible_mesh_records,
        face_diagonal,
        performance=performance,
    )


def _motion_face_frame_sample(
    target,
    projection,
    visible_mesh_records,
    width,
    height,
    performance=None,
):
    channels = target.get("face_channels", [])
    drivers = target.get("face_drivers", [])
    channel_values = []
    for channel in channels:
        value = _motion_face_numeric_value(channel["weight_plug"])
        if value is None:
            raise RuntimeError(
                "Motion Guide face channel became non-numeric at frame "
                "{0}: {1}".format(
                    cmds.currentTime(query=True),
                    channel["weight_plug"],
                )
            )
        # Preserve Maya's final evaluated value.  Display-only normalization
        # must never quantize the semantic sidecar contract.
        channel_values.append(float(value))
    driver_values = []
    for driver in drivers:
        value = _motion_face_numeric_value(driver["plug"])
        if value is None:
            raise RuntimeError(
                "Motion Guide face driver became non-numeric at frame "
                "{0}: {1}".format(
                    cmds.currentTime(query=True),
                    driver["plug"],
                )
            )
        driver_values.append(float(value))
    frame = {
        "available": bool(channels),
        "raster_ready": bool(
            target.get("face_landmark_audit", {}).get("raster_ready")
        ),
        "rasterized": False,
        "visibility_opportunity": False,
        "visibility_reason": "no_face_channels",
        "channel_values": channel_values,
        "driver_values": driver_values,
        "landmarks": [],
        "guide_points": [],
        "guide_segments": [],
    }
    if not channels:
        return frame
    if not frame["raster_ready"]:
        frame["visibility_reason"] = _clean(
            target.get("face_landmark_audit", {}).get("reason")
        ) or "insufficient_surface_landmarks"
        return frame

    face_diagonal = float(
        target.get("face_landmark_audit", {}).get("surface_diagonal") or 0.0
    )
    samples = []
    for landmark_runtime in target.get("face_landmark_runtime", []):
        _motion_perf_increment(
            performance,
            "face_landmark_projection_sample_count",
        )
        sample = _motion_face_landmark_projection_sample(
            landmark_runtime,
            projection,
        )
        if sample is not None:
            samples.append(sample)
    front_samples = [
        sample for sample in samples
        if sample["front_facing"] and sample["in_frame"]
    ]
    _motion_perf_increment(
        performance,
        "face_landmark_front_in_frame_sample_count",
        len(front_samples),
    )
    front_by_id = dict((sample["id"], sample) for sample in front_samples)
    front_edges = [
        edge for edge in target.get("face_edges", [])
        if edge.get("from") in front_by_id and edge.get("to") in front_by_id
    ]
    # A face opportunity is a declared semantic contour edge, never an
    # arbitrary pair of unrelated points.  If no complete edge is front-facing
    # and in-frame, retain Sidecar values and skip every expensive ray.
    if not front_edges:
        frame["landmarks"] = [
            dict(
                (key, value)
                for key, value in sample.items()
                if not key.startswith("_")
            )
            for sample in samples
        ]
        _motion_perf_increment(
            performance,
            "face_frame_ray_gate_short_circuit_count",
        )
        _motion_perf_increment(
            performance,
            "face_landmark_ray_skip_count",
            len(front_samples),
        )
        frame["visibility_reason"] = "back_facing_edge_on_or_out_of_frame"
        return frame
    front_edge_ids = set()
    for edge in front_edges:
        front_edge_ids.add(edge["from"])
        front_edge_ids.add(edge["to"])
    ray_samples = [
        sample for sample in front_samples if sample["id"] in front_edge_ids
    ]
    for sample in ray_samples:
        _motion_face_apply_ray_visibility(
            sample,
            projection,
            target["target_index"],
            visible_mesh_records,
            face_diagonal,
            performance=performance,
        )
    frame["landmarks"] = [
        dict((key, value) for key, value in sample.items() if not key.startswith("_"))
        for sample in samples
    ]
    visible_by_id = dict(
        (sample["id"], sample) for sample in ray_samples if sample["visible"]
    )
    visible_edges = [
        dict(edge) for edge in front_edges
        if edge["from"] in visible_by_id and edge["to"] in visible_by_id
    ]
    if not visible_edges:
        frame["visibility_reason"] = "camera_ray_occluded_or_unverified"
        return frame
    visible_edge_ids = set()
    for edge in visible_edges:
        visible_edge_ids.add(edge["from"])
        visible_edge_ids.add(edge["to"])
    visible_samples = [
        visible_by_id[landmark_id]
        for landmark_id in sorted(visible_edge_ids)
    ]
    xs = [sample["_pixel_x"] for sample in visible_samples]
    ys = [sample["_pixel_y"] for sample in visible_samples]
    screen_span = max(max(xs) - min(xs), max(ys) - min(ys))
    if screen_span < 24.0:
        frame["visibility_reason"] = "face_raster_below_24_pixels"
        return frame

    guide_points = []
    for sample in visible_samples:
        guide_points.append({
            "id": sample["id"],
            "region": sample["region"],
            "side": sample["side"],
            "x": sample["x"],
            "y": sample["y"],
        })
    guide_segments = visible_edges
    frame["visibility_opportunity"] = True
    frame["rasterized"] = True
    frame["visibility_reason"] = "front_facing_camera_ray_visible_face_surface"
    frame["guide_points"] = guide_points
    frame["guide_segments"] = guide_segments
    return frame


def _motion_draw_face_frame(canvas, width, height, face_frame):
    if not face_frame.get("rasterized"):
        return
    points = dict(
        (item["id"], item)
        for item in face_frame.get("guide_points", [])
    )
    for segment in face_frame.get("guide_segments", []):
        start = points.get(segment.get("from"))
        end = points.get(segment.get("to"))
        if start is None or end is None:
            continue
        _motion_draw_line(
            canvas,
            width,
            height,
            float(start["x"]) * float(max(1, width - 1)),
            float(start["y"]) * float(max(1, height - 1)),
            float(end["x"]) * float(max(1, width - 1)),
            float(end["y"]) * float(max(1, height - 1)),
            _motion_face_region_color(segment.get("region")),
            2,
        )
    radius = max(2, int(round(min(width, height) / 240.0)))
    for point in points.values():
        _motion_draw_circle(
            canvas,
            width,
            height,
            float(point["x"]) * float(max(1, width - 1)),
            float(point["y"]) * float(max(1, height - 1)),
            radius,
            _motion_face_region_color(point.get("region")),
        )


def _write_motion_guide_png(path, width, height, canvas):
    raw = bytearray()
    row_size = int(width) * 3
    for row in range(int(height)):
        raw.append(0)
        start = row * row_size
        raw.extend(canvas[start:start + row_size])
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(
        ">IIBBBBB",
        int(width),
        int(height),
        8,
        2,
        0,
        0,
        0,
    )
    payload = (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(
            b"IDAT",
            zlib.compress(bytes(raw), MOTION_GUIDE_PNG_COMPRESSION_LEVEL),
        )
        + _png_chunk(b"IEND", b"")
    )
    with io.open(path, "wb") as handle:
        handle.write(payload)


def _motion_root_joint(joints):
    if not joints:
        return ""
    tokens = ("root", "cog", "center", "centre", "pelvis", "hips", "hip")
    ranked = [
        joint
        for joint in joints
        if any(
            token in _dag_leaf_without_namespace(joint).lower()
            for token in tokens
        )
    ]
    # Never label an arbitrary disconnected influence as the character root.
    # The render loop emits a target-transform root when the rig has no
    # semantically evidenced root joint.
    return ranked[0] if ranked else ""


def _render_motion_guide_pass(
    camera,
    frame_values,
    width,
    height,
    frames_folder,
    output_name,
    bindings,
    hidden_paths,
    job,
):
    """Extract Maya motion and rasterize a target-neutral RGB guide sequence."""
    if os.path.isdir(frames_folder):
        if _is_reparse_or_symlink(frames_folder):
            raise RuntimeError(
                "Refusing to replace a linked Motion Guide directory: {0}".format(
                    frames_folder
                )
            )
        shutil.rmtree(frames_folder)
    os.makedirs(frames_folder)
    if frame_values:
        cmds.currentTime(frame_values[0], edit=True, update=True)
    targets, selection_audit = _motion_target_records(
        bindings,
        hidden_paths=hidden_paths,
        job=job,
        with_report=True,
    )
    if not targets:
        raise RuntimeError(
            "Motion Guide found no authored-visible, Picker-eye-enabled Maya target."
        )
    face_occlusion_meshes = _motion_face_occlusion_meshes(targets)
    _write_progress(
        job,
        "preparing_motion_guide",
        "Preparing target-neutral Maya joint and rigid-transform motion data.",
        motion_guide_profile=MOTION_GUIDE_PROFILE,
        motion_target_count=len(targets),
    )
    output_paths = []
    frame_map = []
    motion_frames = []
    trails = dict((record["target_index"], []) for record in targets)
    total_points = 0
    visible_target_samples = 0
    face_channel_samples = 0
    face_driver_samples = 0
    face_rasterized_samples = 0
    face_visibility_opportunities = 0
    face_hidden_samples = 0
    face_opportunities_by_target = dict(
        (target["target_index"], 0) for target in targets
    )
    face_rasters_by_target = dict(
        (target["target_index"], 0) for target in targets
    )
    frame_count = len(frame_values)
    motion_performance = None
    if bool((job or {}).get("motion_performance_telemetry")):
        motion_performance = {
            "path_visibility_cache_hit_count": 0,
            "path_visibility_cache_miss_count": 0,
            "target_root_short_circuit_count": 0,
            "target_shape_visibility_check_count": 0,
            "target_shape_any_short_circuit_count": 0,
            "face_occluder_candidate_mesh_sample_count": 0,
            "face_occluder_visible_mesh_sample_count": 0,
            "face_landmark_projection_sample_count": 0,
            "face_landmark_front_in_frame_sample_count": 0,
            "face_frame_ray_gate_short_circuit_count": 0,
            "face_landmark_ray_skip_count": 0,
            "face_landmark_ray_test_count": 0,
            "face_mesh_intersection_test_count": 0,
        }
    joint_radius = max(2, int(round(min(width, height) / 180.0)))
    root_radius = max(joint_radius + 1, int(round(min(width, height) / 140.0)))
    for index, frame in enumerate(frame_values):
        cmds.currentTime(frame, edit=True, update=True)
        # Animated DAG and display-layer visibility is stable only within the
        # currently evaluated frame.  Never retain this cache across frames.
        frame_visibility_cache = {}

        def frame_path_visible(path):
            return _motion_cached_path_visible(
                path,
                frame_visibility_cache,
                performance=motion_performance,
            )

        visible_face_occlusion_meshes = (
            _motion_face_visible_occlusion_meshes(
                face_occlusion_meshes,
                frame_path_visible,
                performance=motion_performance,
            )
        )
        projection = _motion_camera_projection(camera, width, height)
        canvas = _motion_canvas(width, height)
        frame_targets = []
        _motion_draw_line(
            canvas, width, height, 1, 1, width - 2, 1,
            (70, 70, 70), 1,
        )
        _motion_draw_line(
            canvas, width, height, width - 2, 1, width - 2, height - 2,
            (70, 70, 70), 1,
        )
        _motion_draw_line(
            canvas, width, height, width - 2, height - 2, 1, height - 2,
            (70, 70, 70), 1,
        )
        _motion_draw_line(
            canvas, width, height, 1, height - 2, 1, 1,
            (70, 70, 70), 1,
        )
        for target in targets:
            root = target["source_root"]
            target_visible = _motion_target_visible(
                target,
                frame_path_visible,
                performance=motion_performance,
            )
            target_frame = {
                "target_index": target["target_index"],
                "asset_id": target["asset_id"],
                "source_root": root,
                "mode": target["mode"],
                "visible": bool(target_visible),
                "points": [],
            }
            face_frame = _motion_face_frame_sample(
                target,
                projection,
                visible_face_occlusion_meshes,
                width,
                height,
                performance=motion_performance,
            )
            face_channel_samples += len(face_frame.get("channel_values", []))
            face_driver_samples += len(face_frame.get("driver_values", []))
            if not target_visible and face_frame.get("available"):
                face_frame["rasterized"] = False
                face_frame["visibility_opportunity"] = False
                face_frame["visibility_reason"] = "target_not_visible"
                face_frame["guide_points"] = []
                face_frame["guide_segments"] = []
            if face_frame.get("available"):
                if face_frame.get("visibility_opportunity"):
                    face_visibility_opportunities += 1
                    face_opportunities_by_target[target["target_index"]] += 1
                if face_frame.get("rasterized"):
                    face_rasterized_samples += 1
                    face_rasters_by_target[target["target_index"]] += 1
                else:
                    face_hidden_samples += 1
            target_frame["face"] = face_frame
            if not target_visible:
                frame_targets.append(target_frame)
                continue
            visible_target_samples += 1
            projected_by_joint = {}
            root_joint = _clean(target.get("root_joint"))
            if target["joints"]:
                for joint in target["joints"]:
                    projected = _motion_project_point(
                        projection,
                        _motion_world_position(joint),
                    )
                    if projected is None:
                        continue
                    point_record = {
                        "id": _motion_joint_stable_id(joint),
                        "label": _dag_leaf_without_namespace(joint),
                        "parent": _motion_joint_stable_id(
                            target["parent_by_joint"].get(joint, "")
                        ) if target["parent_by_joint"].get(joint, "") else "",
                        "x": round(float(projected["x_norm"]), 7),
                        "y": round(float(projected["y_norm"]), 7),
                        "camera_depth": round(
                            float(projected["camera_depth"]),
                            7,
                        ),
                        "in_frame": bool(projected["in_frame"]),
                        "root": joint == root_joint,
                    }
                    target_frame["points"].append(point_record)
                    projected_by_joint[joint] = projected
                for joint, projected in projected_by_joint.items():
                    parent = target["parent_by_joint"].get(joint, "")
                    parent_projected = projected_by_joint.get(parent)
                    if (
                        parent_projected is not None
                        and projected["in_frame"]
                        and parent_projected["in_frame"]
                    ):
                        _motion_draw_line(
                            canvas,
                            width,
                            height,
                            parent_projected["x"],
                            parent_projected["y"],
                            projected["x"],
                            projected["y"],
                            MOTION_GUIDE_BONE_RGB,
                            2,
                        )
                for joint, projected in projected_by_joint.items():
                    if not projected["in_frame"]:
                        continue
                    is_root = joint == root_joint
                    _motion_draw_circle(
                        canvas,
                        width,
                        height,
                        projected["x"],
                        projected["y"],
                        root_radius if is_root else joint_radius,
                        _motion_joint_color(joint, is_root=is_root),
                    )
                root_projected = projected_by_joint.get(root_joint)
                if root_projected is None:
                    root_projected = _motion_project_point(
                        projection,
                        _motion_root_world_position(root),
                    )
                    if root_projected is not None:
                        target_frame["points"].append({
                            "id": "target-root",
                            "label": _dag_leaf_without_namespace(root),
                            "parent": "",
                            "x": round(float(root_projected["x_norm"]), 7),
                            "y": round(float(root_projected["y_norm"]), 7),
                            "camera_depth": round(
                                float(root_projected["camera_depth"]),
                                7,
                            ),
                            "in_frame": bool(root_projected["in_frame"]),
                            "root": True,
                            "synthetic": True,
                        })
                        if root_projected["in_frame"]:
                            _motion_draw_circle(
                                canvas,
                                width,
                                height,
                                root_projected["x"],
                                root_projected["y"],
                                root_radius,
                                MOTION_GUIDE_ROOT_RGB,
                            )
            else:
                root_projected = _motion_project_point(
                    projection,
                    _motion_root_world_position(root),
                )
                if root_projected is not None:
                    target_frame["points"].append({
                        "id": "root",
                        "parent": "",
                        "x": round(float(root_projected["x_norm"]), 7),
                        "y": round(float(root_projected["y_norm"]), 7),
                        "camera_depth": round(
                            float(root_projected["camera_depth"]),
                            7,
                        ),
                        "in_frame": bool(root_projected["in_frame"]),
                        "root": True,
                    })
                    if root_projected["in_frame"]:
                        x = root_projected["x"]
                        y = root_projected["y"]
                        axis = max(12, int(round(min(width, height) / 25.0)))
                        _motion_draw_line(
                            canvas, width, height, x, y, x + axis, y,
                            MOTION_GUIDE_AXIS_X_RGB, 3,
                        )
                        _motion_draw_line(
                            canvas, width, height, x, y, x, y - axis,
                            MOTION_GUIDE_AXIS_Y_RGB, 3,
                        )
                        _motion_draw_line(
                            canvas, width, height, x, y, x - axis * 0.6,
                            y + axis * 0.45, MOTION_GUIDE_AXIS_Z_RGB, 3,
                        )
                        _motion_draw_circle(
                            canvas, width, height, x, y, root_radius,
                            MOTION_GUIDE_ROOT_RGB,
                        )
            if (
                root_projected is not None
                and root_projected["in_frame"]
            ):
                history = trails[target["target_index"]]
                history.append(
                    (root_projected["x"], root_projected["y"])
                )
                del history[:-MOTION_GUIDE_TRAIL_LENGTH]
                for trail_index in range(1, len(history)):
                    _motion_draw_line(
                        canvas,
                        width,
                        height,
                        history[trail_index - 1][0],
                        history[trail_index - 1][1],
                        history[trail_index][0],
                        history[trail_index][1],
                        MOTION_GUIDE_TRAIL_RGB,
                        2,
                    )
            _motion_draw_face_frame(
                canvas,
                width,
                height,
                face_frame,
            )
            total_points += len(target_frame["points"])
            frame_targets.append(target_frame)
        target_path = os.path.join(
            frames_folder,
            "{0}.{1:06d}.png".format(output_name, index),
        )
        _write_motion_guide_png(
            target_path,
            width,
            height,
            canvas,
        )
        output_paths.append(target_path)
        frame_map.append({
            "sequence_index": index,
            "maya_frame": frame,
            "file": os.path.basename(target_path),
        })
        motion_frames.append({
            "sequence_index": index,
            "maya_frame": frame,
            "targets": frame_targets,
        })
        _write_progress(
            job,
            "rendering_motion_guide_frames",
            "Rendered Motion Guide frame {0} of {1} (Maya frame {2}).".format(
                index + 1,
                frame_count,
                frame,
            ),
            frame_status="completed",
            frame_index=index + 1,
            completed_frames=index + 1,
            frame_count=frame_count,
            maya_frame=frame,
            output_file=os.path.basename(target_path),
        )
    target_payload = []
    for target in targets:
        target_payload.append({
            "target_index": target["target_index"],
            "picker_order": target["picker_order"],
            "asset_id": target["asset_id"],
            "source_root": target["source_root"],
            "marker": target["marker"],
            "mode": target["mode"],
            "joint_count": len(target["joints"]),
            "shape_count": len(target.get("shapes", [])),
            "joint_selection": dict(target.get("joint_selection") or {}),
            "joint_ids": [
                _motion_joint_stable_id(joint)
                for joint in target["joints"]
            ],
            "joint_labels": [
                _dag_leaf_without_namespace(joint)
                for joint in target["joints"]
            ],
            "root_source": target.get("root_source") or "target_transform",
            "root_joint_id": (
                _motion_joint_stable_id(target.get("root_joint"))
                if target.get("root_joint")
                else ""
            ),
            "face_surface": target.get("face_surface") or "",
            "face_surface_audit": dict(
                target.get("face_surface_audit") or {}
            ),
            "face_channel_count": len(target.get("face_channels", [])),
            "face_driver_count": len(target.get("face_drivers", [])),
            "face_landmark_count": len(target.get("face_landmarks", [])),
            "face_visibility_opportunity_count": int(
                face_opportunities_by_target.get(target["target_index"]) or 0
            ),
            "face_rasterized_sample_count": int(
                face_rasters_by_target.get(target["target_index"]) or 0
            ),
            "face_discovery": dict(target.get("face_discovery") or {}),
            "face_landmark_audit": dict(
                target.get("face_landmark_audit") or {}
            ),
            "face_semantic_surface_audit": dict(
                target.get("face_semantic_surface_audit") or {}
            ),
            "face_channels": [
                dict(channel)
                for channel in target.get("face_channels", [])
            ],
            "face_drivers": [
                dict(driver)
                for driver in target.get("face_drivers", [])
            ],
            "face_landmarks": [
                dict(landmark)
                for landmark in target.get("face_landmarks", [])
            ],
            "face_edges": [
                dict(edge)
                for edge in target.get("face_edges", [])
            ],
        })
    report = {
        "profile": MOTION_GUIDE_PROFILE,
        "space": "camera_screen_normalized",
        "representation": (
            "target_neutral_core_motion_plus_visible_face_semantic_rgb"
        ),
        "source": (
            "maya_skin_influence_transform_blendshape_and_curve_driver_evaluation"
        ),
        "target_count": len(targets),
        "joint_target_count": sum(
            1 for target in targets if target["joints"]
        ),
        "rigid_target_count": sum(
            1 for target in targets if not target["joints"]
        ),
        "total_point_samples": total_points,
        "visible_target_samples": visible_target_samples,
        "visibility_policy": (
            "shared_hidden_paths_plus_target_shape_animated_dag_layer_visibility"
        ),
        "occlusion_policy": (
            "micro_face_rig_helper_and_duplicate_skeleton_points_excluded;"
            "core_body_motion_intent_preserved_through_self_occlusion;"
            "face_surface_front_facing_and_character_mesh_first_hit_only"
        ),
        "joint_selection_policy": (
            "weighted_skin_influences_then_direct_or_character_reference_core_fallback"
        ),
        "selection_audit": selection_audit,
        "face_semantics": {
            "schema": "hmb-maya-face-semantics",
            "schema_version": 2,
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
            "ray_scope": (
                "authored_visible_character_target_meshes"
            ),
            "unknown_alias_policy": (
                "raw_alias_and_value_preserved_sidecar_only_no_raster_guess"
            ),
            "curve_geometry_rendered": False,
            "target_count": int(selection_audit.get("face_target_count") or 0),
            "channel_count": int(selection_audit.get("face_channel_count") or 0),
            "driver_count": int(selection_audit.get("face_driver_count") or 0),
            "landmark_count": int(selection_audit.get("face_landmark_count") or 0),
            "channel_sample_count": face_channel_samples,
            "driver_sample_count": face_driver_samples,
            "rasterized_sample_count": face_rasterized_samples,
            "visibility_opportunity_count": face_visibility_opportunities,
            "hidden_or_occluded_sample_count": face_hidden_samples,
        },
        "appearance_authority": "zero",
        "camera_authority": "zero_independent_authority",
        "motion_authority": "derived_decoder_of_video1_only",
        "hidden_paths": list(hidden_paths or []),
        "targets": target_payload,
        "motion_frames": motion_frames,
        "palette": {
            "background": list(MOTION_GUIDE_BACKGROUND_RGB),
            "bones": list(MOTION_GUIDE_BONE_RGB),
            "joints": list(MOTION_GUIDE_JOINT_RGB),
            "root": list(MOTION_GUIDE_ROOT_RGB),
            "hands": list(MOTION_GUIDE_HAND_RGB),
            "feet": list(MOTION_GUIDE_FOOT_RGB),
            "trajectory": list(MOTION_GUIDE_TRAIL_RGB),
            "face_brow": list(MOTION_GUIDE_FACE_BROW_RGB),
            "face_eyelid": list(MOTION_GUIDE_FACE_EYE_RGB),
            "face_mouth": list(MOTION_GUIDE_FACE_MOUTH_RGB),
            "face_jaw": list(MOTION_GUIDE_FACE_JAW_RGB),
        },
    }
    if motion_performance is not None:
        report["performance"] = {
            "schema": "hmb-motion-performance-counters",
            "scope": "complete_motion_guide_sequence",
            "frame_count": frame_count,
            "counters": dict(sorted(motion_performance.items())),
        }
    return output_paths, frame_map, report



def _namespace_from_leaf(leaf):
    if ":" not in leaf:
        return ""
    return leaf.rsplit(":", 1)[0]


def _dag_leaf_without_namespace(path):
    leaf = _clean(path).split("|")[-1]
    return leaf.rsplit(":", 1)[-1] if ":" in leaf else leaf


def _asset_collection_group_name(path):
    """Return True only for scene-level containers that hold multiple assets."""
    leaf = _dag_leaf_without_namespace(path).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", leaf).strip("_")
    if normalized in {
        "ch", "char", "chars", "character", "characters",
        "pr", "prop", "props",
        "bg", "env", "environment", "set", "sets",
        "asset", "assets", "object", "objects",
        "scene", "world",
        "ch_grp", "char_grp", "chars_grp", "character_grp", "characters_grp",
        "pr_grp", "prop_grp", "props_grp",
        "bg_grp", "env_grp", "environment_grp", "set_grp", "sets_grp",
        "asset_grp", "assets_grp", "object_grp", "objects_grp",
        "scene_grp", "world_grp",
    }:
        return True
    return bool(re.search(
        r"(?:^|_)(?:assets?|objects?|characters?|chars?|props?|sets?)_(?:grp|group|root)$",
        normalized,
    ))


def _technical_asset_branch_name(path):
    """Identify local guide/helper branches that must never become assignments."""
    leaf = _dag_leaf_without_namespace(path).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", leaf).strip("_")
    if normalized in {
        "dummy", "dummy_grp", "dummy_group",
        "checkbox", "checkbox_grp", "checkpcube", "check_p_cube",
        "gpucache", "gpu_cache", "gpucache_grp", "gpu_cache_grp",
        "camera", "camera_grp", "cam", "cam_grp",
    }:
        return True
    return bool(
        normalized.startswith("checkpcube")
        or normalized.startswith("checkbox")
        or "fosterparent" in normalized
    )


def _asset_root_from_transform(transform, parent_of, reference_node_of):
    """Resolve one renderable transform to its assignable production asset root."""
    transform = _clean(transform)
    if not transform:
        return "", ""
    reference_node = _clean(reference_node_of(transform))
    if reference_node:
        candidate = transform
        parent = _clean(parent_of(candidate))
        while parent and _clean(reference_node_of(parent)) == reference_node:
            candidate = parent
            parent = _clean(parent_of(candidate))
        return candidate, reference_node

    chain = []
    current = transform
    while current:
        chain.append(current)
        current = _clean(parent_of(current))
    chain.reverse()
    if not chain or _technical_asset_branch_name(chain[0]):
        return "", ""
    index = 0
    while index < len(chain) - 1 and _asset_collection_group_name(chain[index]):
        index += 1
    candidate = chain[index]
    if _technical_asset_branch_name(candidate):
        return "", ""
    return candidate, ""


def _reference_asset_label(root, reference_node, reference_file):
    reference_path = re.sub(r"\{\d+\}$", "", _clean(reference_file))
    reference_name = os.path.splitext(os.path.basename(reference_path))[0]
    if reference_name:
        return reference_name
    namespace = _namespace_from_leaf(_clean(root).split("|")[-1])
    if namespace:
        return namespace
    node_name = re.sub(r"RN(?:\d+)?$", "", _clean(reference_node))
    return node_name or _dag_leaf_without_namespace(root)


def _scan_outliner_nodes(progress_callback=None):
    """Build a flat, assignable asset-root list with one-pass cached DAG analysis."""
    if progress_callback:
        progress_callback("collecting_meshes", "Collecting renderable polygon shapes.")
    renderable_shapes = _all_renderable_shapes()
    direct_shapes_by_transform = {}
    parent_cache = {}

    def parent_of(node):
        if node in parent_cache:
            return parent_cache[node]
        parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
        parent_cache[node] = parents[0] if parents else ""
        return parent_cache[node]

    included = set()
    for index, shape in enumerate(renderable_shapes):
        parent = parent_of(shape)
        if not parent:
            continue
        direct_shapes_by_transform.setdefault(parent, []).append(shape)
        current = parent
        while current and current not in included:
            included.add(current)
            current = parent_of(current)
        if progress_callback and index and index % 250 == 0:
            progress_callback("collecting_meshes", "Collected {0} of {1} polygon shapes.".format(index, len(renderable_shapes)))

    children_by_transform = dict((transform, []) for transform in included)
    parent_by_transform = {}
    for transform in included:
        parent = parent_of(transform)
        parent = parent if parent in included else ""
        parent_by_transform[transform] = parent
        if parent:
            children_by_transform.setdefault(parent, []).append(transform)

    reference_node_cache = {}

    def reference_node_of(node):
        if node in reference_node_cache:
            return reference_node_cache[node]
        value = ""
        try:
            if cmds.referenceQuery(node, isNodeReferenced=True):
                value = _clean(cmds.referenceQuery(node, referenceNode=True))
        except Exception:
            value = ""
        reference_node_cache[node] = value
        return value

    asset_root_reference = {}
    for shape in renderable_shapes:
        transform = parent_of(shape)
        root, reference_node = _asset_root_from_transform(transform, parent_of, reference_node_of)
        if root:
            asset_root_reference[root] = reference_node
    proxy_manager_by_reference = {}
    proxy_tag_by_reference = {}
    for proxy_record in _proxy_reference_sets():
        manager = _clean(proxy_record.get("proxy_manager"))
        for member in proxy_record.get("members") or []:
            reference_node = _clean(member.get("reference_node"))
            if not reference_node:
                continue
            proxy_manager_by_reference[reference_node] = manager
            proxy_tag_by_reference[reference_node] = _clean(
                member.get("proxy_tag")
            )

    layer_cache = {}
    connection_cache = {}
    own_status_cache = {}
    effective_status_cache = {}

    def layer_hidden(node):
        if node not in layer_cache:
            layer_cache[node] = _display_layer_hidden(node)[0]
        return layer_cache[node]

    def connection_kind(node):
        if node not in connection_cache:
            connection_cache[node] = _visibility_connection_kind(node)
        return connection_cache[node]

    def own_hidden_status(node):
        if node in own_status_cache:
            return own_status_cache[node]
        if not _bool_attr(node, "visibility", True):
            value = "self_hidden"
        elif _bool_attr(node, "overrideEnabled", False) and not _bool_attr(node, "overrideVisibility", True):
            value = "override_hidden"
        elif layer_hidden(node):
            value = "layer_hidden"
        else:
            value = ""
        own_status_cache[node] = value
        return value

    def effective_transform_status(transform):
        if transform in effective_status_cache:
            return effective_status_cache[transform]
        own = own_hidden_status(transform)
        if own:
            result = own
        else:
            parent = parent_by_transform.get(transform, "") or parent_of(transform)
            parent_status = effective_transform_status(parent) if parent else ""
            result = "parent_hidden" if parent_status else ""
        effective_status_cache[transform] = result
        return result

    visible_count = dict((transform, 0) for transform in included)
    descendant_count = dict((transform, 0) for transform in included)
    hidden_reason = dict((transform, "hidden") for transform in included)
    descendant_connection = dict((transform, "") for transform in included)

    def merge_connection(current, incoming):
        if current == "anim_vis" or incoming == "anim_vis":
            return "anim_vis"
        return current or incoming

    if progress_callback:
        progress_callback("checking_visibility", "Checking cached viewport visibility.")
    for index, shape in enumerate(renderable_shapes):
        parent = parent_of(shape)
        own_shape_status = own_hidden_status(shape)
        transform_status = effective_transform_status(parent) if parent else ""
        reason = own_shape_status or transform_status
        is_visible = not reason
        shape_connection = connection_kind(shape)
        current = parent
        while current and current in included:
            descendant_count[current] += 1
            if is_visible:
                visible_count[current] += 1
            elif hidden_reason[current] == "hidden":
                hidden_reason[current] = reason or "hidden"
            if shape_connection:
                descendant_connection[current] = merge_connection(descendant_connection[current], shape_connection)
            current = parent_by_transform.get(current, "")
        if progress_callback and index and index % 250 == 0:
            progress_callback("checking_visibility", "Checked {0} of {1} polygon shapes.".format(index, len(renderable_shapes)))

    for transform in sorted(included, key=lambda item: _dag_depth(item), reverse=True):
        own_connection = connection_kind(transform)
        if own_connection:
            descendant_connection[transform] = merge_connection(own_connection, descendant_connection.get(transform, ""))
        parent = parent_by_transform.get(transform, "")
        if parent and descendant_connection.get(transform):
            descendant_connection[parent] = merge_connection(descendant_connection.get(parent, ""), descendant_connection[transform])

    if progress_callback:
        progress_callback("building_outliner", "Extracting assignable asset roots.")
    nodes = []
    ordered = sorted(asset_root_reference, key=lambda item: (_dag_depth(item), item))
    reference_files = {}
    reference_labels = {}
    for root in ordered:
        reference_node = asset_root_reference.get(root, "")
        if not reference_node:
            continue
        try:
            reference_file = _clean(cmds.referenceQuery(reference_node, filename=True, withoutCopyNumber=False))
        except Exception:
            reference_file = ""
        reference_files[root] = reference_file
        reference_labels[root] = _reference_asset_label(root, reference_node, reference_file)

    label_counts = {}
    for label in reference_labels.values():
        label_counts[label] = label_counts.get(label, 0) + 1
    used_labels = set()

    for index, transform in enumerate(ordered):
        leaf = transform.split("|")[-1]
        direct_shapes = direct_shapes_by_transform.get(transform, [])
        try:
            uuid_value = (cmds.ls(transform, uuid=True) or [""])[0]
        except Exception:
            uuid_value = ""
        reference_node = asset_root_reference.get(transform, "")
        referenced = bool(reference_node)
        reference_file = reference_files.get(transform, "")
        display_name = leaf
        if referenced:
            base_label = reference_labels.get(transform, "") or leaf
            display_name = base_label
            if label_counts.get(base_label, 0) > 1:
                namespace = _namespace_from_leaf(leaf)
                display_name = namespace or "{0}__{1}".format(base_label, _dag_leaf_without_namespace(transform))
        unique_name = display_name
        suffix = 2
        while unique_name in used_labels:
            unique_name = "{0}__{1}".format(display_name, suffix)
            suffix += 1
        display_name = unique_name
        used_labels.add(display_name)
        connection = descendant_connection.get(transform, "")
        own_hidden = own_hidden_status(transform)
        if connection:
            status = connection
        elif own_hidden:
            status = own_hidden
        elif visible_count.get(transform, 0):
            status = "visible"
        else:
            status = hidden_reason.get(transform, "hidden")
        node = {
            "name": display_name,
            "dag_name": leaf,
            "full_path": transform,
            "parent_path": "",
            "depth": 0,
            "source_depth": _dag_depth(transform),
            "maya_uuid": uuid_value,
            "namespace": _namespace_from_leaf(leaf),
            "child_count": 0,
            "direct_shape_count": len(direct_shapes),
            "descendant_shape_count": descendant_count.get(transform, 0),
            "mesh_count": descendant_count.get(transform, 0),
            "has_renderable_shapes": bool(descendant_count.get(transform, 0)),
            "referenced": referenced,
            "reference_node": reference_node,
            "reference_file": reference_file,
            "proxy_manager": proxy_manager_by_reference.get(reference_node, ""),
            "proxy_tag": proxy_tag_by_reference.get(reference_node, ""),
            "node_kind": "asset_root",
            "asset_root": True,
            "outliner_filter": "asset_roots_v1",
            "scene_visible": bool(visible_count.get(transform, 0)),
            "visible_shape_count": visible_count.get(transform, 0),
            "visibility_status": status,
            "visibility_driven": bool(connection),
        }
        nodes.append(node)
        if progress_callback and index and index % 500 == 0:
            progress_callback("building_outliner", "Built {0} of {1} asset-root rows.".format(index, len(ordered)))
    return nodes


def _scan_cameras():
    cameras = []
    default_names = {"persp", "top", "front", "side"}
    registered = _camera_from_scene_data()
    for shape in cmds.ls(type="camera", long=True) or []:
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if not parents:
            continue
        transform = parents[0]
        leaf = transform.split("|")[-1]
        try:
            renderable = bool(cmds.getAttr(shape + ".renderable"))
        except Exception:
            renderable = False
        try:
            uuid_value = (cmds.ls(transform, uuid=True) or [""])[0]
        except Exception:
            uuid_value = ""
        cameras.append({
            "name": leaf,
            "full_path": transform,
            "maya_uuid": uuid_value,
            "renderable": renderable,
            "registered": bool(registered and registered == transform),
            "default_camera": leaf in default_names,
        })
    cameras = [item for item in cameras if not item.get("default_camera")]
    cameras.sort(key=lambda item: (
        not item.get("registered"),
        not item.get("renderable"),
        item.get("default_camera"),
        item.get("full_path"),
    ))
    selected = ""
    camera_paths = set(item["full_path"] for item in cameras)
    if registered and registered in camera_paths:
        selected = registered
    else:
        renderable = [item["full_path"] for item in cameras if item.get("renderable")]
        if len(renderable) == 1:
            selected = renderable[0]
        else:
            named = [
                item["full_path"] for item in cameras
                if not item.get("default_camera") and any(token in item.get("name", "").lower() for token in ("shot", "render", "cam"))
            ]
            if len(named) == 1:
                selected = named[0]
    if not selected and len(cameras) == 1:
        selected = cameras[0]["full_path"]
    return cameras, selected


def _scan_scene(job, result_path, maya_version, scene_path):
    def progress(stage, message):
        _write_progress(job, stage, message)
    outliner_nodes = _scan_outliner_nodes(progress)
    _write_progress(job, "scanning_cameras", "Scanning scene cameras.")
    cameras, selected_camera = _scan_cameras()
    _write_progress(
        job,
        "cameras_scanned",
        "Camera scan completed: {0} user camera(s).".format(len(cameras)),
        camera_count=len(cameras),
        selected_camera=selected_camera,
    )
    requested_camera = _clean(job.get("camera"))
    if requested_camera:
        direct = [item["full_path"] for item in cameras if item.get("full_path") == requested_camera]
        if not direct:
            requested_leaf = requested_camera.split("|")[-1]
            direct = [
                item["full_path"] for item in cameras
                if item.get("name") == requested_leaf or item.get("full_path", "").split("|")[-1] == requested_leaf
            ]
        if len(direct) == 1:
            selected_camera = direct[0]
    if not selected_camera and cameras:
        selected_camera = cameras[0]["full_path"]

    _write_progress(job, "reading_timeline", "Reading playback range, current frame, time unit, and FPS.")
    start_frame = cmds.playbackOptions(query=True, minTime=True)
    end_frame = cmds.playbackOptions(query=True, maxTime=True)
    current_frame = cmds.currentTime(query=True)
    fps = _scene_fps()
    _write_progress(
        job,
        "timeline_read",
        "Timeline read completed: start {0}, current {1}, end {2}, FPS {3}.".format(
            start_frame, current_frame, end_frame, fps
        ),
        start_frame=start_frame,
        current_frame=current_frame,
        end_frame=end_frame,
        fps=fps,
    )
    warnings = list(job.get("_reference_warnings") or [])
    if bool(job.get("generate_original_video")):
        warnings.append(
            "Legacy generate_original_video was ignored: scan/READ is metadata-only. "
            "Use the separate render operation requested by Original Playblast."
        )
    original_frames_folder = ""
    original_output_name = ""
    original_frame_map = []
    original_frame_count = 0

    result = {
        "ok": True,
        "operation": "scan",
        "maya_version": maya_version,
        "scene_path": os.path.abspath(scene_path).replace("\\", "/"),
        "scene": os.path.basename(scene_path),
        "outliner_nodes": outliner_nodes,
        "cameras": cameras,
        "selected_camera": selected_camera,
        "original_frames_folder": original_frames_folder,
        "original_output_name": original_output_name,
        "original_frame_map": original_frame_map,
        "original_frame_count": original_frame_count,
        "warnings": warnings,
        "group_count": len(outliner_nodes),
        "start_frame": start_frame,
        "end_frame": end_frame,
        "current_frame": current_frame,
        "fps": fps,
        "scene_dependency_paths": list(job.get("_scene_dependency_paths") or []),
        "script_node_report": dict(job.get("_script_node_report") or {}),
    }
    _write_json(result_path, result)
    _write_progress(
        job,
        "scan_complete",
        "Metadata-only scan completed: {0} asset roots and {1} user cameras; no playblast was rendered.".format(
            len(outliner_nodes), len(cameras)
        ),
        group_count=len(outliner_nodes),
        camera_count=len(cameras),
        original_frame_count=original_frame_count,
    )
    _emit_console("SUCCESS", "Outliner scan completed: {0} asset roots".format(len(outliner_nodes)))
    return result


def _marker_payload(bindings, character_outline_mode=CHARACTER_OUTLINE_NATIVE):
    outline_mode = _character_outline_mode(
        {"character_outline_mode": character_outline_mode}
    )
    result = []
    for record in bindings:
        color = record["color"]
        is_character = color in CHARACTER_MARKERS
        uses_lambert = is_character or color in MARKER_COLORS
        pattern = MARKER_PATTERNS.get(color, "")
        pattern_id_rgb = MARKER_PATTERN_IDS.get(color)
        pfx_profile = is_character and outline_mode == CHARACTER_OUTLINE_PFX
        shading_profile = {}
        if uses_lambert:
            shading_profile = {
                "profile": "pfxToon_profile" if pfx_profile else CHARACTER_VISUAL_PROFILE,
                "diffuse": CHARACTER_LAMBERT_DIFFUSE,
                "ambient_gain": CHARACTER_LAMBERT_AMBIENT_GAIN,
                "incandescence_gain": CHARACTER_LAMBERT_INCANDESCENCE_GAIN,
                "viewport_lighting": "maya_default_lighting",
                "viewport_render_mode": "smooth_shaded_textured",
                "out_rim": "pfxToon_profile" if pfx_profile else "none",
            }
            if pfx_profile:
                shading_profile.update({
                    "out_rim_opacity": CHARACTER_OUT_RIM_OPACITY,
                    "out_rim_min_pixel_width": CHARACTER_OUT_RIM_MIN_PIXEL_WIDTH,
                    "out_rim_max_pixel_width": CHARACTER_OUT_RIM_MAX_PIXEL_WIDTH,
                    "out_rim_line_offset": CHARACTER_OUT_RIM_LINE_OFFSET,
                    "out_rim_screenspace_resampling": CHARACTER_OUT_RIM_SCREENSPACE_RESAMPLING,
                    "out_rim_local_occlusion": "all_toon_surfaces",
                    "out_rim_antialiasing": "viewport_native",
                })
        elif pattern:
            shading_profile = {
                "profile": SCREEN_SPACE_PATTERN_PROFILE,
                "pattern": pattern,
                "pattern_space": "screen",
                "phase_origin": "frame_top_left",
                "linear_scale_divisor": SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR,
                "uv_dependent": False,
                "occlusion": "viewport2_depth",
                "categorical_id_rgb": list(pattern_id_rgb or ()),
            }
        result.append({
            "color": color,
            "asset_id": record["asset_id"],
            "subject_root": record["subject_root"],
            "group_name": record.get("group_name", record["subject_root"]),
            "full_dag_path": record.get("full_dag_path", record["subject_root"]),
            "maya_uuid": record.get("maya_uuid", ""),
            "reference_node": record.get("reference_node", ""),
            "reference_file": record.get("reference_file", ""),
            "proxy_manager": record.get("proxy_manager", ""),
            "shader_model": "lambert" if uses_lambert else "surfaceShader",
            "visual_profile": (
                "lambert_with_pfxToon_profile"
                if pfx_profile
                else (
                    CHARACTER_VISUAL_PROFILE
                    if uses_lambert
                    else SCREEN_SPACE_PATTERN_PROFILE
                )
            ),
            "out_rim": "pfxToon_profile" if pfx_profile else "",
            "shading_profile": shading_profile,
        })
    return result


def run(job_path):
    job_path = os.path.abspath(job_path)
    job = _read_json(job_path)
    _validate_job_write_paths(job_path, job)
    result_path = os.path.abspath(job["result_path"])
    result = {"ok": False, "job_path": job_path}
    try:
        _emit_console("INFO", "Background runner started.")
        _emit_console("INFO", "Job file: {0}".format(job_path))
        maya_version = _clean(cmds.about(version=True))
        _emit_console("INFO", "Maya version: {0}".format(maya_version))
        expected_major = _clean(job.get("expected_maya_major"))
        if expected_major and not maya_version.startswith(expected_major):
            raise RuntimeError(
                "Maya {0} is required for this test, but Maya {1} is running.".format(
                    expected_major, maya_version
                )
            )

        _write_progress(job, "maya_ready", "Maya batch initialized. Opening the scene safely.")
        scene_path = _open_scene_for_job(job)

        operation = _clean(job.get("operation")) or "render"
        if operation == "scan":
            return _scan_scene(job, result_path, maya_version, scene_path)

        apply_marker_shaders = bool(job.get("apply_marker_shaders", True))
        force_high_quality_viewport = bool(job.get("force_high_quality_viewport"))
        screen_space_patterns = bool(job.get("screen_space_patterns"))
        generate_depth_playblast = bool(job.get("generate_depth_playblast"))
        generate_motion_guide = bool(job.get("generate_motion_guide"))
        requested_mouth_patch_policy = _clean(
            job.get("mouth_card_inner_patch_policy")
        )
        if (
            requested_mouth_patch_policy
            and requested_mouth_patch_policy != MOUTH_CARD_INNER_PATCH_POLICY
        ):
            raise RuntimeError(
                "Unsupported mouth-card inner-patch policy: {0}".format(
                    requested_mouth_patch_policy
                )
            )
        require_full_smooth_geometry = bool(
            job.get("require_full_smooth_geometry")
        )
        if screen_space_patterns and not apply_marker_shaders:
            raise RuntimeError(
                "screen_space_patterns requires temporary marker shaders."
            )
        requested_pattern_profile = _clean(
            job.get("screen_space_pattern_profile")
        )
        if (
            screen_space_patterns
            and requested_pattern_profile
            != SCREEN_SPACE_PATTERN_PROFILE
        ):
            raise RuntimeError(
                "Unsupported screen-space pattern profile: {0}".format(
                    requested_pattern_profile or "<empty>"
                )
            )
        if generate_depth_playblast:
            requested_depth_profile = _clean(job.get("depth_profile"))
            if (
                requested_depth_profile
                and requested_depth_profile != DEPTH_PLAYBLAST_PROFILE
            ):
                raise RuntimeError(
                    "Unsupported depth playblast profile: {0}".format(
                        requested_depth_profile
                    )
                )
            for required_field in (
                "depth_frames_folder",
                "depth_output_name",
                "depth_sidecar_path",
            ):
                if not _clean(job.get(required_field)):
                    raise RuntimeError(
                        "Depth playblast job is missing {0}.".format(required_field)
                    )
        if generate_motion_guide:
            requested_motion_profile = _clean(
                job.get("motion_guide_profile")
            )
            if (
                requested_motion_profile
                and requested_motion_profile != MOTION_GUIDE_PROFILE
            ):
                raise RuntimeError(
                    "Unsupported Motion Guide profile: {0}".format(
                        requested_motion_profile
                    )
                )
            for required_field in (
                "motion_guide_frames_folder",
                "motion_guide_output_name",
                "motion_guide_sidecar_path",
            ):
                if not _clean(job.get(required_field)):
                    raise RuntimeError(
                        "Motion Guide job is missing {0}.".format(
                            required_field
                        )
                    )
        character_outline_mode = (
            _character_outline_mode(job) if apply_marker_shaders else ""
        )
        bindings = []
        hidden_paths = []
        render_scope_report = {}
        if apply_marker_shaders:
            _load_marker_catalog(job)
            _write_progress(job, "validating_bindings", "Validating Color Assignment and camera settings.")
            bindings = _read_job_bindings(job)
        camera = _resolve_camera(_clean(job.get("camera")))
        if apply_marker_shaders:
            _write_progress(
                job,
                "applying_render_scope",
                "Keeping only Maya-authored visible, color-bound, Picker-enabled geometry.",
            )
            hidden_paths, render_scope_report = _apply_assigned_render_scope(
                bindings,
                job,
            )
            _write_progress(
                job,
                "render_scope_ready",
                "Picker render scope contains {0} assigned shape path(s); "
                "{1} unassigned or eye-disabled path(s) are excluded.".format(
                    int(render_scope_report.get("allowed_shape_path_count") or 0),
                    int(render_scope_report.get("excluded_shape_path_count") or 0),
                ),
                **render_scope_report
            )
        # Capture the authored SG/material alpha graph before either Smooth
        # Preview or temporary marker/depth assignment changes scene-local
        # viewport state.  The source scene and source materials are never saved
        # or edited; temporary shaders only consume material.outTransparency.
        _ensure_authored_cutout_snapshot(
            job,
            _authored_cutout_scope_shapes(job),
        )
        width = int(job.get("width") or 1280)
        height = int(job.get("height") or 720)
        start_frame = job.get("start_frame")
        end_frame = job.get("end_frame")
        if start_frame is None:
            start_frame = cmds.playbackOptions(query=True, minTime=True)
        if end_frame is None:
            end_frame = cmds.playbackOptions(query=True, maxTime=True)
        frames = _frame_values(start_frame, end_frame)
        fps = float(job.get("fps") or _scene_fps())
        if fps <= 0:
            raise RuntimeError("FPS must be greater than zero.")
        render_budget = _validate_render_storage_budget(
            job, frames, width, height
        )
        _write_progress(
            job,
            "render_budget_ready",
            "Render staging capacity verified for {0} frame(s) and {1} pass(es).".format(
                render_budget["frame_count"], render_budget["pass_count"]
            ),
            **render_budget
        )

        warnings = list(job.get("_reference_warnings") or [])
        quality_restore = None
        quality_report = {}
        if force_high_quality_viewport:
            _write_progress(
                job,
                "preparing_full_smooth_geometry",
                "Preparing Smooth Preview 3 only for authored-visible assigned Maya meshes.",
            )
            quality_restore, quality_report = _apply_full_smooth_viewport(job)
            job["_proxy_preview_recovery"] = dict(
                quality_report.get("proxy_preview_recovery")
                or _empty_proxy_preview_recovery_report()
            )
            quality_warnings = list(quality_report.get("warnings") or [])
            warnings.extend(quality_warnings)
            quality_ready_message = (
                "Full-detail Maya Smooth Preview 3 viewport profile is active."
            )
            _write_progress(
                job,
                "full_smooth_geometry_ready",
                quality_ready_message,
                viewport_quality_profile=FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
                dag_full_detail_count=int(quality_report.get("dag_full_detail_count") or 0),
                display_layer_full_detail_count=int(
                    quality_report.get("display_layer_full_detail_count") or 0
                ),
                proxy_preview_mesh_count=int(
                    quality_report.get("proxy_preview_mesh_count") or 0
                ),
                smooth_mesh_shape_count=int(
                    quality_report.get("smooth_mesh_shape_count") or 0
                ),
                unresolved_proxy_plugin_count=len(
                    quality_report.get("unresolved_proxy_nodes") or []
                ),
            )
        else:
            job["_proxy_preview_recovery"] = (
                _empty_proxy_preview_recovery_report()
            )

        # Full-smooth preparation only touches the already-scoped concrete Maya
        # shapes and never promotes authored-hidden proxy caches.
        if apply_marker_shaders:
            _write_progress(
                job,
                "preparing_scene",
                "Applying temporary marker shaders and categorical screen-space IDs.",
            )
            warnings.extend(_apply_marker_shaders(bindings, job))
        elif not force_high_quality_viewport:
            _write_progress(
                job,
                "preparing_scene",
                "Preserving the original Maya viewport appearance.",
            )
        try:
            render_options_report = _set_viewport_render_options(
                marker_mode=apply_marker_shaders,
                preserve_authored_look=(
                    force_high_quality_viewport and not apply_marker_shaders
                ),
                screen_space_patterns=screen_space_patterns,
            )
        except Exception:
            if quality_restore is not None:
                warnings.extend(
                    _restore_full_smooth_viewport(quality_restore)
                )
                quality_restore = None
            raise

        frames_folder = os.path.abspath(job["frames_folder"])
        output_name = _clean(job.get("output_name")) or "hmb_preview"
        depth_frames_folder = ""
        depth_output_name = ""
        depth_sidecar_path = ""
        depth_output_paths = []
        depth_frame_map = []
        depth_range_report = {}
        motion_guide_frames_folder = ""
        motion_guide_output_name = ""
        motion_guide_sidecar_path = ""
        motion_guide_output_paths = []
        motion_guide_frame_map = []
        motion_guide_report = {}
        if generate_depth_playblast:
            depth_frames_folder = os.path.abspath(
                _clean(job.get("depth_frames_folder"))
            )
            depth_output_name = _clean(job.get("depth_output_name"))
            depth_sidecar_path = os.path.abspath(
                _clean(job.get("depth_sidecar_path"))
            )
            if os.path.normcase(depth_frames_folder) == os.path.normcase(frames_folder):
                raise RuntimeError(
                    "Depth frames folder must be separate from the color frames folder."
                )
            if os.path.normcase(depth_sidecar_path) == os.path.normcase(
                os.path.abspath(job["sidecar_path"])
            ):
                raise RuntimeError(
                    "Depth sidecar path must be separate from the color sidecar path."
                )
        if generate_motion_guide:
            motion_guide_frames_folder = os.path.abspath(
                _clean(job.get("motion_guide_frames_folder"))
            )
            motion_guide_output_name = _clean(
                job.get("motion_guide_output_name")
            )
            motion_guide_sidecar_path = os.path.abspath(
                _clean(job.get("motion_guide_sidecar_path"))
            )
            used_frame_folders = [os.path.normcase(frames_folder)]
            used_sidecars = [
                os.path.normcase(os.path.abspath(job["sidecar_path"]))
            ]
            if generate_depth_playblast:
                used_frame_folders.append(
                    os.path.normcase(depth_frames_folder)
                )
                used_sidecars.append(
                    os.path.normcase(depth_sidecar_path)
                )
            if (
                os.path.normcase(motion_guide_frames_folder)
                in used_frame_folders
            ):
                raise RuntimeError(
                    "Motion Guide frames folder must be separate from "
                    "Color and Depth frame folders."
                )
            if (
                os.path.normcase(motion_guide_sidecar_path)
                in used_sidecars
            ):
                raise RuntimeError(
                    "Motion Guide sidecar path must be separate from "
                    "Color and Depth sidecar paths."
                )
        _write_progress(
            job,
            "rendering_frames",
            "Rendering Viewport 2.0 frames.",
            frame_count=len(frames),
            completed_frames=0,
        )
        artifact_status = {
            "color": {"requested": True, "ok": False, "error": ""},
            "depth": {
                "requested": bool(generate_depth_playblast),
                "ok": False,
                "error": "",
            },
            "motion_guide": {
                "requested": bool(generate_motion_guide),
                "ok": False,
                "error": "",
            },
        }
        auxiliary_bindings = bindings
        auxiliary_scope_error = ""
        original_mouth_controller = None
        original_mouth_report = {}
        try:
            if force_high_quality_viewport and not apply_marker_shaders:
                original_mouth_controller = _MouthCardInnerPatchController(
                    job,
                    "original",
                )
            try:
                output_paths, frame_map = _render_frames(
                    camera=camera,
                    frame_values=frames,
                    width=width,
                    height=height,
                    frames_folder=frames_folder,
                    output_name=output_name,
                    job=job,
                    progress_stage="rendering_frames",
                    pre_frame_callback=(
                        original_mouth_controller.prepare_frame
                        if original_mouth_controller is not None
                        else None
                    ),
                    post_frame_callback=(
                        original_mouth_controller.restore_frame
                        if original_mouth_controller is not None
                        else None
                    ),
                )
            finally:
                if original_mouth_controller is not None:
                    original_mouth_report = original_mouth_controller.finish()
                    job["_mouth_inner_patch_original_report"] = dict(
                        original_mouth_report
                    )
                    quality_report["mouth_card_inner_patch"] = dict(
                        original_mouth_report
                    )
            artifact_status["color"]["ok"] = True
            if (generate_depth_playblast or generate_motion_guide) and not bindings:
                try:
                    _prepare_unassigned_auxiliary_scope(
                        job,
                        hidden_paths,
                        render_scope_report,
                    )
                    auxiliary_bindings = _unassigned_motion_bindings(
                        hidden_paths=hidden_paths
                    )
                except Exception as exc:
                    auxiliary_scope_error = _clean(exc) or exc.__class__.__name__
                    warning = (
                        "Optional auxiliary authored-visible scope could not be "
                        "prepared: {0}".format(auxiliary_scope_error)
                    )
                    warnings.append(warning)
                    _emit_console("WARNING", warning)
            if generate_depth_playblast:
                try:
                    if auxiliary_scope_error:
                        raise RuntimeError(auxiliary_scope_error)
                    (
                        depth_output_paths,
                        depth_frame_map,
                        depth_range_report,
                    ) = _render_depth_pass(
                        camera=camera,
                        frame_values=frames,
                        width=width,
                        height=height,
                        frames_folder=depth_frames_folder,
                        output_name=depth_output_name,
                        job=job,
                    )
                    if len(depth_output_paths) != len(output_paths):
                        raise RuntimeError(
                            "Depth frame count does not match the color frame count."
                        )
                    color_times = [
                        float(item.get("maya_frame"))
                        for item in frame_map
                    ]
                    depth_times = [
                        float(item.get("maya_frame"))
                        for item in depth_frame_map
                    ]
                    if depth_times != color_times:
                        raise RuntimeError(
                            "Depth frame timing does not match the color frame timing."
                        )
                    artifact_status["depth"]["ok"] = True
                except _MouthCardRestorationError:
                    # A later Motion pass must never run on a scene whose
                    # temporary mouth geometry/layer state may be contaminated.
                    raise
                except Exception as exc:
                    artifact_status["depth"]["error"] = (
                        _clean(exc) or exc.__class__.__name__
                    )
                    warning = "Optional Depth artifact failed: {0}".format(
                        artifact_status["depth"]["error"]
                    )
                    warnings.append(warning)
                    _emit_console("WARNING", warning)
            if generate_motion_guide:
                try:
                    if auxiliary_scope_error:
                        raise RuntimeError(auxiliary_scope_error)
                    (
                        motion_guide_output_paths,
                        motion_guide_frame_map,
                        motion_guide_report,
                    ) = _render_motion_guide_pass(
                        camera=camera,
                        frame_values=frames,
                        width=width,
                        height=height,
                        frames_folder=motion_guide_frames_folder,
                        output_name=motion_guide_output_name,
                        bindings=auxiliary_bindings,
                        hidden_paths=hidden_paths,
                        job=job,
                    )
                    if len(motion_guide_output_paths) != len(output_paths):
                        raise RuntimeError(
                            "Motion Guide frame count does not match the Color "
                            "frame count."
                        )
                    color_times = [
                        float(item.get("maya_frame"))
                        for item in frame_map
                    ]
                    motion_times = [
                        float(item.get("maya_frame"))
                        for item in motion_guide_frame_map
                    ]
                    if motion_times != color_times:
                        raise RuntimeError(
                            "Motion Guide frame timing does not match the Color "
                            "frame timing."
                        )
                    artifact_status["motion_guide"]["ok"] = True
                except Exception as exc:
                    artifact_status["motion_guide"]["error"] = (
                        _clean(exc) or exc.__class__.__name__
                    )
                    warning = "Optional Motion Guide artifact failed: {0}".format(
                        artifact_status["motion_guide"]["error"]
                    )
                    warnings.append(warning)
                    _emit_console("WARNING", warning)
        finally:
            if quality_restore is not None:
                warnings.extend(
                    _restore_full_smooth_viewport(quality_restore)
                )

        auxiliary_render_scope_report = dict(
            job.get("_auxiliary_render_scope_report") or {}
        )
        sidecar_path = os.path.abspath(job["sidecar_path"])
        payload = {
            "video": "",
            "video_path": "",
            "scene": os.path.basename(scene_path),
            "scene_path": os.path.abspath(scene_path).replace("\\", "/"),
            "camera": camera,
            "maya_version": maya_version,
            "render_method": "Viewport 2.0 OGS",
            "assignment_mode": "direct_group_name_plus_color_pick",
            "mouth_card_inner_patch_policy": MOUTH_CARD_INNER_PATCH_POLICY,
            "character_outline_mode": character_outline_mode,
            "marker_catalog_version": int(MARKER_CATALOG.get("version") or 0),
            "fps": fps,
            "start_frame": frames[0],
            "end_frame": frames[-1],
            "frame_count": len(frames),
            "resolution": {"width": width, "height": height},
            "video_format": {
                "container": _clean(job.get("video_container")) or "MPEG-4",
                "codec": _clean(job.get("video_codec")) or "H.264",
                "encoder": _clean(job.get("ffmpeg_encoder")) or "libx264",
            },
            "frame_pattern": os.path.join(frames_folder, output_name + ".%06d.png").replace("\\", "/"),
            "frame_map": frame_map,
            "markers": _marker_payload(
                bindings,
                character_outline_mode=character_outline_mode,
            ),
            "hidden_paths": hidden_paths,
            "warnings": warnings,
            "scene_dependency_paths": list(job.get("_scene_dependency_paths") or []),
            "script_node_report": dict(job.get("_script_node_report") or {}),
            "render_scope": dict(render_scope_report),
            "auxiliary_render_scope": auxiliary_render_scope_report,
            "cutout_transparency": dict(
                job.get("_marker_cutout_transparency")
                or job.get("_authored_cutout_report")
                or {}
            ),
            "mouth_card_inner_patch": dict(
                job.get("_mouth_inner_patch_original_report") or {}
            ),
        }
        if screen_space_patterns:
            payload["screen_space_pattern_profile"] = SCREEN_SPACE_PATTERN_PROFILE
            payload["screen_space_postprocess_pending"] = True
            payload["screen_space_render_options"] = render_options_report
        if force_high_quality_viewport:
            payload["viewport_quality_profile"] = FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
            payload["viewport_quality_report"] = quality_report
        if force_high_quality_viewport and not apply_marker_shaders:
            payload["assignment_mode"] = "original_full_detail_no_marker"
        _write_json(sidecar_path, payload)

        if artifact_status["depth"]["ok"]:
            depth_payload = {
                "schema": "hmb-maya-depth-playblast",
                "schema_version": 1,
                "profile": DEPTH_PLAYBLAST_PROFILE,
                "scene": os.path.basename(scene_path),
                "scene_path": os.path.abspath(scene_path).replace("\\", "/"),
                "camera": camera,
                "maya_version": maya_version,
                "render_method": "Viewport 2.0 OGS camera-space grayscale",
                "assignment_mode": "temporary_camera_depth_surface_shader",
                "mouth_card_inner_patch_policy": MOUTH_CARD_INNER_PATCH_POLICY,
                "fps": fps,
                "start_frame": frames[0],
                "end_frame": frames[-1],
                "frame_count": len(depth_output_paths),
                "resolution": {"width": width, "height": height},
                "frame_pattern": os.path.join(
                    depth_frames_folder,
                    depth_output_name + ".%06d.png",
                ).replace("\\", "/"),
                "frame_map": depth_frame_map,
                "depth_range_report": depth_range_report,
                "mouth_card_inner_patch": dict(
                    job.get("_mouth_inner_patch_depth_report") or {}
                ),
                "viewport_quality_profile": (
                    FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
                    if force_high_quality_viewport
                    else ""
                ),
                "viewport_quality_report": (
                    quality_report if force_high_quality_viewport else {}
                ),
                "hidden_paths": hidden_paths,
                "warnings": warnings,
                "scene_dependency_paths": list(
                    job.get("_scene_dependency_paths") or []
                ),
                "script_node_report": dict(
                    job.get("_script_node_report") or {}
                ),
                "render_scope": dict(render_scope_report),
                "auxiliary_render_scope": auxiliary_render_scope_report,
            }
            _write_json(depth_sidecar_path, depth_payload)

        if artifact_status["motion_guide"]["ok"]:
            motion_guide_payload = {
                "schema": MOTION_GUIDE_SCHEMA,
                "schema_version": MOTION_GUIDE_SCHEMA_VERSION,
                "profile": MOTION_GUIDE_PROFILE,
                "scene": os.path.basename(scene_path),
                "scene_path": os.path.abspath(scene_path).replace("\\", "/"),
                "camera": camera,
                "maya_version": maya_version,
                "render_method": (
                    "Maya joint/transform extraction plus target-neutral "
                    "RGB guide rasterization"
                ),
                "assignment_mode": (
                    "derived_video1_motion_decoder_no_appearance_authority"
                ),
                "fps": fps,
                "start_frame": frames[0],
                "end_frame": frames[-1],
                "frame_count": len(motion_guide_output_paths),
                "resolution": {"width": width, "height": height},
                "frame_pattern": os.path.join(
                    motion_guide_frames_folder,
                    motion_guide_output_name + ".%06d.png",
                ).replace("\\", "/"),
                "frame_map": motion_guide_frame_map,
                "motion_guide_report": motion_guide_report,
                "viewport_quality_profile": (
                    FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
                    if force_high_quality_viewport
                    else ""
                ),
                "viewport_quality_report": (
                    quality_report if force_high_quality_viewport else {}
                ),
                "hidden_paths": hidden_paths,
                "warnings": warnings,
                "scene_dependency_paths": list(
                    job.get("_scene_dependency_paths") or []
                ),
                "script_node_report": dict(
                    job.get("_script_node_report") or {}
                ),
                "auxiliary_render_scope": auxiliary_render_scope_report,
            }
            _write_json(
                motion_guide_sidecar_path,
                motion_guide_payload,
            )

        result.update({
            "ok": True,
            "maya_version": maya_version,
            "camera": camera,
            "fps": fps,
            "frame_count": len(output_paths),
            "frames_folder": frames_folder,
            "sidecar_path": sidecar_path,
            "character_outline_mode": character_outline_mode,
            "warnings": warnings,
            "artifacts": artifact_status,
            "mouth_card_inner_patch_policy": MOUTH_CARD_INNER_PATCH_POLICY,
        })
        if artifact_status["depth"]["ok"]:
            result.update({
                "depth_frames_folder": depth_frames_folder,
                "depth_output_name": depth_output_name,
                "depth_sidecar_path": depth_sidecar_path,
                "depth_frame_count": len(depth_output_paths),
                "depth_profile": DEPTH_PLAYBLAST_PROFILE,
                "depth_range_report": depth_range_report,
                "depth_frame_map": depth_frame_map,
            })
        if artifact_status["motion_guide"]["ok"]:
            result.update({
                "motion_guide_frames_folder": (
                    motion_guide_frames_folder
                ),
                "motion_guide_output_name": motion_guide_output_name,
                "motion_guide_sidecar_path": motion_guide_sidecar_path,
                "motion_guide_frame_count": len(
                    motion_guide_output_paths
                ),
                "motion_guide_profile": MOTION_GUIDE_PROFILE,
                "motion_guide_report": motion_guide_report,
                "motion_guide_frame_map": motion_guide_frame_map,
            })
        if force_high_quality_viewport:
            result["viewport_quality_profile"] = FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
            result["viewport_quality_report"] = quality_report
        if screen_space_patterns:
            result["screen_space_pattern_profile"] = SCREEN_SPACE_PATTERN_PROFILE
            result["screen_space_render_options"] = render_options_report
        _write_json(result_path, result)
        _write_progress(
            job,
            "render_complete",
            (
            "Color, camera-depth, and Motion Guide frame generation completed."
                if artifact_status["depth"]["ok"] and artifact_status["motion_guide"]["ok"]
                else "Color and camera-depth viewport frame generation completed."
                if artifact_status["depth"]["ok"]
                else "Color and Motion Guide frame generation completed."
                if artifact_status["motion_guide"]["ok"]
                else "Viewport frame generation completed."
            ),
            frame_count=len(output_paths),
            depth_frame_count=len(depth_output_paths),
            motion_guide_frame_count=len(motion_guide_output_paths),
            depth_profile=(
                DEPTH_PLAYBLAST_PROFILE if artifact_status["depth"]["ok"] else ""
            ),
            motion_guide_profile=(
                MOTION_GUIDE_PROFILE if artifact_status["motion_guide"]["ok"] else ""
            ),
        )
        _emit_console("SUCCESS", "Completed: {0}".format(sidecar_path))
        return result
    except Exception as exc:
        result.update({
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        try:
            _write_json(result_path, result)
        except Exception:
            pass
        _emit_console("ERROR", str(exc))
        traceback.print_exc()
        raise


def run_from_env():
    job_path = os.environ.get("HMB_VIDEO_PICKER_JOB", "")
    if not job_path:
        raise RuntimeError("HMB_VIDEO_PICKER_JOB is not set.")
    expected_job_sha256 = _clean(
        os.environ.get("HMB_VIDEO_PICKER_JOB_SHA256", "")
    ).lower()
    if not expected_job_sha256:
        raise RuntimeError("HMB_VIDEO_PICKER_JOB_SHA256 is not set.")
    with io.open(job_path, "rb") as handle:
        actual_job_sha256 = hashlib.sha256(handle.read()).hexdigest().lower()
    if actual_job_sha256 != expected_job_sha256:
        raise RuntimeError(
            "HMB Maya job integrity check failed; the staged job changed "
            "after launch."
        )
    try:
        run(job_path)
    except Exception:
        try:
            cmds.quit(force=True, exitCode=1)
        except Exception:
            pass
        raise
    try:
        cmds.quit(force=True, exitCode=0)
    except Exception:
        pass
