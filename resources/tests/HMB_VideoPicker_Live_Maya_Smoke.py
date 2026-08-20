from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker

try:
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
except Exception:
    ControlFlow = None
    GriptapeNodes = None


def compact_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": state.get("status"),
        "scene_stage": state.get("scene_stage"),
        "operation_kind": state.get("operation_kind"),
        "message": state.get("message"),
        "native_read_ready": bool(state.get("native_read_ready")),
        "scene_path": state.get("scene_path"),
        "maya_version": state.get("maya_version"),
        "camera": state.get("camera"),
        "selected_camera": state.get("selected_camera"),
        "camera_count": len(state.get("cameras") or []),
        "start_frame": state.get("start_frame"),
        "current_frame": state.get("current_frame"),
        "end_frame": state.get("end_frame"),
        "source_fps": state.get("source_fps"),
        "outliner_count": len(state.get("outliner_nodes") or []),
        "video_path": state.get("video_path"),
        "video_url": state.get("video_url"),
        "original_video_path": state.get("original_video_path"),
        "original_video_url": state.get("original_video_url"),
        "original_preview_enabled": bool(state.get("original_preview_enabled")),
        "snapshot_active": bool(state.get("snapshot_active")),
        "snapshot_frame": state.get("snapshot_frame"),
        "snapshot_path": state.get("snapshot_path"),
        "last_log_path": state.get("last_log_path"),
        "warnings": state.get("warnings") or [],
        "depth_video_slot": int(state.get("depth_video_slot") or 0),
        "motion_guide_video_slot": int(state.get("motion_guide_video_slot") or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HMBVideoPicker against a real Maya mayabatch.")
    parser.add_argument("scene", type=Path)
    parser.add_argument(
        "--original-preview",
        action="store_true",
        help="After metadata-only READ, render Original once and verify the second request is a cache hit.",
    )
    parser.add_argument("--playblast", action="store_true")
    parser.add_argument(
        "--depth",
        action="store_true",
        help="With --playblast, generate and validate typed auxiliary Depth.",
    )
    parser.add_argument(
        "--motion-guide",
        action="store_true",
        help="With --playblast, generate and validate typed auxiliary Motion Guide.",
    )
    parser.add_argument(
        "--no-assignment",
        action="store_true",
        help=(
            "With --playblast, leave Color Assignment empty and exercise the "
            "authored-visible auxiliary fallback scope."
        ),
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    source_scene = args.scene.resolve()
    if not source_scene.is_file() or source_scene.suffix.lower() not in {".ma", ".mb"}:
        raise FileNotFoundError(f"A Maya .ma or .mb scene is required: {source_scene}")

    test_root = Path(tempfile.mkdtemp(prefix="HMBVideoPicker_Live_"))
    scene_copy = test_root / source_scene.name
    shutil.copy2(source_scene, scene_copy)
    transitions: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {
        "ok": False,
        "source_scene": str(source_scene),
        "test_root": str(test_root),
        "scene_copy": str(scene_copy),
        "mayabatch": str(picker._find_mayabatch() or ""),
        "ffmpeg": str(picker._find_ffmpeg(picker._find_mayabatch()) or ""),
        "original_preview_requested": bool(args.original_preview),
        "playblast_requested": bool(args.playblast),
        "depth_requested": bool(args.depth),
        "motion_guide_requested": bool(args.motion_guide),
        "no_assignment_requested": bool(args.no_assignment),
    }
    if args.depth and not args.playblast:
        raise ValueError("--depth requires --playblast.")
    if args.motion_guide and not args.playblast:
        raise ValueError("--motion-guide requires --playblast.")

    node = picker.HMBVideoPickerLibrary(name=f"HMBVideoPickerLive_{time.time_ns()}")
    if GriptapeNodes is not None and ControlFlow is not None:
        GriptapeNodes.EventManager().initialize_queue()
        flow = ControlFlow(name=f"HMBVideoPickerLiveFlow_{time.time_ns()}")
        flow.add_node(node)
        GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)
        GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
        GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name
    original_write_state = node._write_state

    def traced_write_state(state: Dict[str, Any]) -> None:
        transitions.append({
            "time": time.strftime("%H:%M:%S"),
            **compact_state(copy.deepcopy(state)),
        })
        original_write_state(state)

    node._write_state = traced_write_state

    try:
        node._schedule_scene_selection(str(scene_copy), "live_maya_smoke")
        selected_state = node._picker_state()
        if selected_state.get("scene_stage") != "LOAD_READY":
            raise RuntimeError(f"Maya selection did not become READ-ready: {selected_state.get('message')}")

        selected_state.update({
            "scene_draft_path": str(scene_copy),
            "scene_request_path": str(scene_copy),
            "scene_path": str(scene_copy),
            "backend_ack_action_id": "live-read",
            "pending_action": "",
            "pending_action_id": "",
        })
        node._hmb_cancel_requested.clear()
        node._start_ui_operation("read_scene", selected_state)
        read_state = node._picker_state()
        result["read"] = compact_state(read_state)
        if not read_state.get("native_read_ready"):
            raise RuntimeError(f"Live READ did not publish native_read_ready: {read_state.get('message')}")
        if not read_state.get("outliner_nodes"):
            raise RuntimeError("Live READ returned no selectable Outliner nodes.")
        if not read_state.get("cameras"):
            raise RuntimeError("Live READ returned no user camera.")
        if float(read_state.get("source_fps") or 0.0) <= 0:
            raise RuntimeError("Live READ returned invalid FPS.")
        expected_original = scene_copy.parent / scene_copy.stem / f"{scene_copy.stem}_Orignal.mp4"
        expected_original_sidecar = (
            scene_copy.parent / scene_copy.stem / f"{scene_copy.stem}_Orignal.hmb.json"
        )
        if read_state.get("original_preview_enabled"):
            raise RuntimeError("Metadata-only live READ unexpectedly enabled Original preview.")
        for field in (
            "original_video_path",
            "original_video_url",
            "video_path",
            "video_url",
        ):
            if str(read_state.get(field) or ""):
                raise RuntimeError(f"Metadata-only live READ unexpectedly populated {field}.")
        native_metadata = (
            read_state.get("native_metadata")
            if isinstance(read_state.get("native_metadata"), dict)
            else {}
        )
        if str(native_metadata.get("original_video_path") or ""):
            raise RuntimeError("Metadata-only live READ published an Original path in native metadata.")
        if int(native_metadata.get("preview_frame_count") or 0) != 0:
            raise RuntimeError("Metadata-only live READ reported rendered preview frames.")
        if expected_original.exists() or expected_original_sidecar.exists():
            raise RuntimeError("Metadata-only live READ created an Original preview artifact.")
        if any(key in read_state for key in ("preview_frames", "preview_data_uri", "preview_frame_index")):
            raise RuntimeError("Live READ retained retired static preview state.")

        if args.original_preview:
            original_request_state = copy.deepcopy(read_state)
            original_request_state.update({
                "backend_ack_action_id": "live-original-preview-miss",
                "pending_action": "",
                "pending_action_id": "",
            })
            node._hmb_cancel_requested.clear()
            node._start_ui_operation("render_original_preview", original_request_state)
            original_state = node._picker_state()
            result["original_preview_miss"] = compact_state(original_state)
            original_video_path = Path(str(original_state.get("original_video_path") or ""))
            original_sidecar_path = expected_original_sidecar
            if not original_state.get("original_preview_enabled"):
                raise RuntimeError(
                    f"Live Original preview did not become active: {original_state.get('message')}"
                )
            if original_video_path != expected_original:
                raise RuntimeError(
                    f"Live Original preview used the wrong output name: {original_video_path}"
                )
            if not expected_original.is_file() or expected_original.stat().st_size <= 0:
                raise RuntimeError(
                    f"Live Original preview did not create a video: {expected_original}"
                )
            if not original_sidecar_path.is_file() or original_sidecar_path.stat().st_size <= 0:
                raise RuntimeError(
                    f"Live Original preview did not create its cache sidecar: {original_sidecar_path}"
                )
            original_metadata = json.loads(original_sidecar_path.read_text(encoding="utf-8"))
            if original_metadata.get("encoding_profile") != picker.PROXY_ENCODING_PROFILE:
                raise RuntimeError("Live Original preview used an obsolete encoding profile.")
            if (
                original_metadata.get("viewport_quality_profile")
                != picker.ORIGINAL_VIEWPORT_QUALITY_PROFILE
            ):
                raise RuntimeError(
                    "Live Original preview did not confirm the full-detail viewport profile."
                )
            if not isinstance(original_metadata.get("viewport_quality_report"), dict):
                raise RuntimeError(
                    "Live Original preview did not publish its full-detail quality report."
                )
            if (original_metadata.get("video_format") or {}).get("crf") != picker.PROXY_ENCODER_CRF:
                raise RuntimeError("Live Original preview did not use the high-quality CRF profile.")
            if not str(original_state.get("original_video_url") or ""):
                raise RuntimeError("Live Original preview did not publish its media URL.")
            if Path(str(original_state.get("video_path") or "")) != expected_original:
                raise RuntimeError("Live Original preview was not projected into the active viewport.")
            result["original_preview_miss"]["original_video_size"] = expected_original.stat().st_size
            result["original_preview_miss"]["sidecar_size"] = original_sidecar_path.stat().st_size

            # Repeating the same explicit request must validate and reuse the
            # published pair without modifying either artifact.
            original_stat = (
                expected_original.stat().st_size,
                expected_original.stat().st_mtime_ns,
            )
            sidecar_stat = (
                original_sidecar_path.stat().st_size,
                original_sidecar_path.stat().st_mtime_ns,
            )
            cache_request_state = copy.deepcopy(original_state)
            cache_request_state.update({
                "backend_ack_action_id": "live-original-preview-hit",
                "pending_action": "",
                "pending_action_id": "",
            })
            node._hmb_cancel_requested.clear()
            node._start_ui_operation("render_original_preview", cache_request_state)
            cache_state = node._picker_state()
            result["original_preview_hit"] = compact_state(cache_state)
            if not cache_state.get("original_preview_enabled"):
                raise RuntimeError("Validated Original cache hit did not remain active.")
            if "cache" not in str(cache_state.get("message") or "").lower():
                raise RuntimeError(
                    f"Repeated Original request did not report a cache hit: {cache_state.get('message')}"
                )
            if (
                expected_original.stat().st_size,
                expected_original.stat().st_mtime_ns,
            ) != original_stat:
                raise RuntimeError("Original cache hit rewrote the video artifact.")
            if (
                original_sidecar_path.stat().st_size,
                original_sidecar_path.stat().st_mtime_ns,
            ) != sidecar_stat:
                raise RuntimeError("Original cache hit rewrote the sidecar artifact.")

        if args.playblast:
            first_group = next(
                (
                    item for item in read_state.get("outliner_nodes", [])
                    if item.get("scene_visible")
                    and item.get("full_path")
                    and not item.get("proxy_manager")
                ),
                next(
                    (
                        item
                        for item in read_state.get("outliner_nodes", [])
                        if item.get("scene_visible") and item.get("full_path")
                    ),
                    read_state["outliner_nodes"][0],
                ),
            )
            selected_camera = (
                str(read_state.get("selected_camera") or read_state.get("camera") or "")
                or str(read_state["cameras"][0].get("full_path") or "")
            )
            slot_assignments = [] if args.no_assignment else [{
                "video_slot": 1,
                "bindings": [{
                    "group_name": first_group.get("name") or first_group.get("full_path"),
                    "full_dag_path": first_group.get("full_path"),
                    "maya_uuid": first_group.get("maya_uuid") or "",
                    "reference_node": first_group.get("reference_node") or "",
                    "reference_file": first_group.get("reference_file") or "",
                    "proxy_manager": first_group.get("proxy_manager") or "",
                    "proxy_tag": first_group.get("proxy_tag") or "",
                    "color": "Red",
                    "enabled": True,
                    "video_slot": 1,
                    "picker_order": 1,
                }],
            }]
            run_state = copy.deepcopy(node._picker_state())
            run_state.update({
                "selected_video_slot": 1,
                "selected_camera": selected_camera,
                "camera": selected_camera,
                "slot_assignments": slot_assignments,
                "backend_ack_action_id": "live-playblast",
                "pending_action": "",
                "pending_action_id": "",
                "depth_enabled": bool(args.depth),
                "motion_guide_enabled": bool(args.motion_guide),
            })
            node._write_state(run_state)

            snapshot_state = copy.deepcopy(node._picker_state())
            snapshot_state.update({
                "snapshot_frame": float(read_state.get("current_frame") or read_state.get("start_frame") or 0.0),
                "snapshot_video_slot": 1,
                "backend_ack_action_id": "live-snapshot",
                "pending_action": "",
                "pending_action_id": "",
            })
            node._hmb_cancel_requested.clear()
            node._start_ui_operation("render_snapshot", snapshot_state)
            rendered_snapshot_state = node._picker_state()
            result["snapshot"] = compact_state(rendered_snapshot_state)
            snapshot_path = Path(str(rendered_snapshot_state.get("snapshot_path") or ""))
            if (
                not rendered_snapshot_state.get("snapshot_active")
                or not snapshot_path.is_file()
                or snapshot_path.stat().st_size <= 0
            ):
                raise RuntimeError(f"Live SNAPSHOT did not create a still frame: {snapshot_path}")
            result["snapshot"]["snapshot_size"] = snapshot_path.stat().st_size

            node._hmb_cancel_requested.clear()
            node._start_ui_operation("run_video", node._picker_state())
            playblast_state = node._picker_state()
            result["playblast"] = compact_state(playblast_state)
            result["playblast"]["serialized_state_bytes"] = len(
                json.dumps(
                    playblast_state,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if args.no_assignment and playblast_state.get("markers"):
                raise RuntimeError(
                    "No-assignment live PLAYBLAST unexpectedly published Color markers."
                )
            for warning in playblast_state.get("warnings") or []:
                if len(str(warning)) > picker._UI_WARNING_MESSAGE_LIMIT:
                    raise RuntimeError(
                        "Live PLAYBLAST retained an oversized UI warning."
                    )
            video_path = Path(str(playblast_state.get("video_path") or ""))
            expected_playblast = scene_copy.parent / scene_copy.stem / f"{scene_copy.stem}_playblast_1.mp4"
            expected_playblast_sidecar = (
                scene_copy.parent
                / scene_copy.stem
                / f"{scene_copy.stem}_playblast_1.hmb.json"
            )
            if str(playblast_state.get("status") or "").upper() != "VIDEO_READY":
                raise RuntimeError(
                    f"Live PLAYBLAST did not retain VIDEO_READY: {playblast_state.get('message')}"
                )
            if video_path != expected_playblast:
                raise RuntimeError(f"Live PLAYBLAST used the wrong output name: {video_path}")
            if not video_path.is_file() or video_path.stat().st_size <= 0:
                raise RuntimeError(f"Live PLAYBLAST did not create a video: {video_path}")
            if not expected_playblast_sidecar.is_file():
                raise RuntimeError(
                    f"Live PLAYBLAST did not create its sidecar: {expected_playblast_sidecar}"
                )
            playblast_metadata = json.loads(
                expected_playblast_sidecar.read_text(encoding="utf-8")
            )
            quality_report = playblast_metadata.get("viewport_quality_report") or {}
            if (
                playblast_metadata.get("viewport_quality_profile")
                != picker.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE
                or int(quality_report.get("smooth_mesh_preview_mode") or 0) != 3
                or int(quality_report.get("smooth_mesh_shape_count") or 0) <= 0
                or int(quality_report.get("remaining_bounding_box_count") or 0) != 0
            ):
                raise RuntimeError(
                    "Live PLAYBLAST did not verify full-detail Smooth Preview 3."
                )
            screen_report = playblast_metadata.get("screen_space_postprocess") or {}
            if (
                screen_report.get("profile")
                != picker.SCREEN_SPACE_PATTERN_PROFILE
                or bool(screen_report.get("uv_dependent"))
                or screen_report.get("phase") != "frame_top_left"
            ):
                raise RuntimeError(
                    "Live PLAYBLAST did not publish the screen-space pattern contract."
                )
            if (playblast_metadata.get("video_format") or {}).get("crf") != picker.PROXY_ENCODER_CRF:
                raise RuntimeError("Live PLAYBLAST did not use the high-quality CRF profile.")
            if int(playblast_metadata.get("frame_count") or 0) != int(
                playblast_state.get("output_frame_count") or 0
            ):
                raise RuntimeError("Live PLAYBLAST sidecar frame count disagrees with Picker state.")
            if playblast_state.get("snapshot_active") or snapshot_path.exists():
                raise RuntimeError("Live PLAYBLAST did not clear the snapshot cache.")
            result["playblast"]["video_size"] = video_path.stat().st_size
            if args.depth:
                depth_slot = int(playblast_state.get("depth_video_slot") or 0)
                if depth_slot != 2:
                    raise RuntimeError(
                        "Live Depth did not publish to canonical @video2: "
                        f"{depth_slot}"
                    )
                expected_depth = (
                    scene_copy.parent
                    / scene_copy.stem
                    / f"{scene_copy.stem}_depth_playblast_{depth_slot}.mp4"
                )
                expected_depth_sidecar = (
                    scene_copy.parent
                    / scene_copy.stem
                    / f"{scene_copy.stem}_depth_playblast_{depth_slot}.hmb.json"
                )
                if not expected_depth.is_file() or expected_depth.stat().st_size <= 0:
                    raise RuntimeError(
                        f"Live Depth did not create @video{depth_slot}: {expected_depth}"
                    )
                if not expected_depth_sidecar.is_file():
                    raise RuntimeError(
                        f"Live Depth did not create the @video{depth_slot} sidecar: "
                        f"{expected_depth_sidecar}"
                    )
                depth_metadata = json.loads(
                    expected_depth_sidecar.read_text(encoding="utf-8")
                )
                auxiliary_scope = depth_metadata.get("auxiliary_render_scope") or {}
                if args.no_assignment and sorted(
                    auxiliary_scope.get("supported_surface_types") or []
                ) != ["mesh", "nurbsSurface"]:
                    raise RuntimeError(
                        "No-assignment Depth did not confirm the exact mesh/NURBS surface scope."
                    )
                if depth_metadata.get("media_kind") != picker.DEPTH_MEDIA_KIND:
                    raise RuntimeError(f"Live @video{depth_slot} is missing generated Depth media metadata.")
                if depth_metadata.get("markers") != []:
                    raise RuntimeError(f"Live @video{depth_slot} Depth must remain marker-free.")
                for field in (
                    "camera",
                    "fps",
                    "frame_count",
                    "start_frame",
                    "end_frame",
                    "resolution",
                ):
                    if depth_metadata.get(field) != playblast_metadata.get(field):
                        raise RuntimeError(
                            f"Live @video{depth_slot} Depth {field} does not match @video1."
                        )
                if (
                    (depth_metadata.get("depth_range_report") or {}).get(
                        "temporal_normalization"
                    )
                    != "fixed_for_complete_sequence"
                ):
                    raise RuntimeError(
                        f"Live @video{depth_slot} Depth did not use one fixed shot range."
                    )
                depth_item = next(
                    (
                        item
                        for item in playblast_state.get("videos", [])
                        if int(item.get("video_slot") or 0) == depth_slot
                    ),
                    None,
                )
                if (
                    not depth_item
                    or depth_item.get("media_kind") != picker.DEPTH_MEDIA_KIND
                    or depth_item.get("markers") != []
                ):
                    raise RuntimeError(
                        f"Live Picker state did not activate marker-free @video{depth_slot} Depth."
                    )
                picker_payload = node._build_picker_payload(playblast_state)
                depth_payload = next(
                    (
                        item
                        for item in picker_payload.get("videos", [])
                        if int(item.get("video_slot") or 0) == depth_slot
                    ),
                    None,
                )
                if (
                    picker_payload.get("schema_version") != 4
                    or not depth_payload
                    or depth_payload.get("source_type_hint")
                    != picker.DEPTH_SOURCE_TYPE
                    or depth_payload.get("control_role_hint")
                    != picker.DEPTH_CONTROL_ROLE
                ):
                    raise RuntimeError(
                        f"Live PICKER_OUT did not carry the generated @video{depth_slot} Depth contract."
                    )
                result["depth"] = {
                    "video_path": str(expected_depth),
                    "video_size": expected_depth.stat().st_size,
                    "sidecar_path": str(expected_depth_sidecar),
                    "profile": depth_metadata.get("depth_profile"),
                    "range": depth_metadata.get("depth_range_report"),
                    "auxiliary_scope": auxiliary_scope,
                    "video_slot": depth_slot,
                }
            if args.motion_guide:
                motion_slot = int(
                    playblast_state.get("motion_guide_video_slot") or 0
                )
                expected_motion_slot = 3 if args.depth else 2
                if motion_slot != expected_motion_slot:
                    raise RuntimeError(
                        "Live Motion Guide did not publish to its canonical packed "
                        f"slot @{expected_motion_slot}: {motion_slot}"
                    )
                depth_slot = int(playblast_state.get("depth_video_slot") or 0)
                if args.depth and motion_slot == depth_slot:
                    raise RuntimeError(
                        "Live Motion Guide and Depth occupied the same auxiliary slot."
                    )
                expected_motion = (
                    scene_copy.parent
                    / scene_copy.stem
                    / f"{scene_copy.stem}_motion_guide_{motion_slot}.mp4"
                )
                expected_motion_sidecar = (
                    scene_copy.parent
                    / scene_copy.stem
                    / f"{scene_copy.stem}_motion_guide_{motion_slot}.hmb.json"
                )
                if (
                    not expected_motion.is_file()
                    or expected_motion.stat().st_size <= 0
                ):
                    raise RuntimeError(
                        f"Live Motion Guide did not create @video{motion_slot}: "
                        f"{expected_motion}"
                    )
                if not expected_motion_sidecar.is_file():
                    raise RuntimeError(
                        f"Live Motion Guide did not create the @video{motion_slot} "
                        f"sidecar: {expected_motion_sidecar}"
                    )
                motion_metadata = json.loads(
                    expected_motion_sidecar.read_text(encoding="utf-8")
                )
                if (
                    motion_metadata.get("media_kind")
                    != picker.MOTION_GUIDE_MEDIA_KIND
                    or motion_metadata.get("motion_guide_profile")
                    != picker.MOTION_GUIDE_PROFILE
                    or motion_metadata.get("appearance_authority") != "zero"
                    or motion_metadata.get("motion_authority")
                    != "derived_decoder_of_video1_only"
                    or int(motion_metadata.get("source_video_slot") or 0) != 1
                ):
                    raise RuntimeError(
                        f"Live @video{motion_slot} is missing strict Motion Guide provenance."
                    )
                if motion_metadata.get("markers") != []:
                    raise RuntimeError(
                        f"Live @video{motion_slot} Motion Guide must remain marker-free."
                    )
                for field in (
                    "camera",
                    "fps",
                    "frame_count",
                    "start_frame",
                    "end_frame",
                    "resolution",
                ):
                    if motion_metadata.get(field) != playblast_metadata.get(field):
                        raise RuntimeError(
                            f"Live @video{motion_slot} Motion Guide {field} does not match @video1."
                        )
                motion_item = next(
                    (
                        item
                        for item in playblast_state.get("videos", [])
                        if int(item.get("video_slot") or 0) == motion_slot
                    ),
                    None,
                )
                if (
                    not motion_item
                    or motion_item.get("media_kind")
                    != picker.MOTION_GUIDE_MEDIA_KIND
                    or motion_item.get("markers") != []
                ):
                    raise RuntimeError(
                        f"Live Picker state did not activate marker-free @video{motion_slot} Motion Guide."
                    )
                compact_motion_report = motion_item.get("motion_guide_report") or {}
                if "motion_frames" in compact_motion_report:
                    raise RuntimeError(
                        "Live Picker state retained Motion Guide frame details."
                    )
                if len(json.dumps(
                    compact_motion_report,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")) >= 65536:
                    raise RuntimeError(
                        "Live Picker state retained an oversized Motion Guide report."
                    )
                full_motion_report = motion_metadata.get("motion_guide_report") or {}
                if len(full_motion_report.get("motion_frames") or []) != int(
                    motion_metadata.get("frame_count") or 0
                ):
                    raise RuntimeError(
                        "Motion Guide sidecar did not retain one full detail row per frame."
                    )
                picker_payload = node._build_picker_payload(playblast_state)
                motion_payload = next(
                    (
                        item
                        for item in picker_payload.get("videos", [])
                        if int(item.get("video_slot") or 0) == motion_slot
                    ),
                    None,
                )
                if (
                    picker_payload.get("schema_version") != 4
                    or not motion_payload
                    or motion_payload.get("source_type_hint")
                    != picker.MOTION_GUIDE_SOURCE_TYPE
                    or motion_payload.get("control_role_hint")
                    != picker.MOTION_GUIDE_CONTROL_ROLE
                ):
                    raise RuntimeError(
                        f"Live PICKER_OUT did not carry the generated @video{motion_slot} Motion Guide contract."
                    )
                result["motion_guide"] = {
                    "video_path": str(expected_motion),
                    "video_size": expected_motion.stat().st_size,
                    "sidecar_path": str(expected_motion_sidecar),
                    "profile": motion_metadata.get("motion_guide_profile"),
                    "state_report_bytes": len(json.dumps(
                        compact_motion_report,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")),
                    "sidecar_motion_frame_count": len(
                        full_motion_report.get("motion_frames") or []
                    ),
                    "video_slot": motion_slot,
                }

        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{exc.__class__.__name__}: {exc}"
        result["terminal_state"] = compact_state(node._picker_state())
    finally:
        result["transitions"] = transitions
        summary_path = test_root / "live_maya_smoke_summary.json"
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HMB_LIVE_SMOKE_SUMMARY={summary_path}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.keep:
            shutil.rmtree(test_root, ignore_errors=True)

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
