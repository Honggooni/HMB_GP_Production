from __future__ import annotations

import argparse
import asyncio
import copy
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
    SetParameterValueResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


def compact_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": state.get("status"),
        "scene_stage": state.get("scene_stage"),
        "state_writer": state.get("state_writer"),
        "state_revision": state.get("state_revision"),
        "backend_ack_action_id": state.get("backend_ack_action_id"),
        "pending_action": state.get("pending_action"),
        "operation_kind": state.get("operation_kind"),
        "native_read_ready": bool(state.get("native_read_ready")),
        "camera_count": len(state.get("cameras") or []),
        "outliner_count": len(state.get("outliner_nodes") or []),
        "start_frame": state.get("start_frame"),
        "current_frame": state.get("current_frame"),
        "end_frame": state.get("end_frame"),
        "source_fps": state.get("source_fps"),
        "video_path": state.get("video_path"),
        "original_video_path": state.get("original_video_path"),
        "original_video_url": state.get("original_video_url"),
        "original_preview_enabled": bool(state.get("original_preview_enabled")),
        "video_url": state.get("video_url"),
        "message": state.get("message"),
        "last_log_path": state.get("last_log_path"),
    }


async def run(scene: Path, timeout_seconds: float, keep: bool) -> dict[str, Any]:
    source_scene = scene.resolve()
    if not source_scene.is_file() or source_scene.suffix.lower() not in {".mb", ".ma"}:
        raise FileNotFoundError(f"A Maya .mb or .ma scene is required: {source_scene}")

    test_root = Path(tempfile.mkdtemp(prefix="HMB_Griptape_Transport_"))
    scene_copy = test_root / source_scene.name
    shutil.copy2(source_scene, scene_copy)
    action_id = f"integration-read-{time.time_ns()}"
    result: dict[str, Any] = {
        "ok": False,
        "source_scene": str(source_scene),
        "scene_copy": str(scene_copy),
        "action_id": action_id,
        "transitions": [],
    }

    GriptapeNodes.EventManager().initialize_queue()
    node = picker.HMBVideoPickerLibrary(name=f"HMBVideoPickerTransport_{time.time_ns()}")
    flow = ControlFlow(name=f"HMBTransportFlow_{time.time_ns()}")
    flow.add_node(node)
    GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)
    GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name

    try:
        # Match the production UI contract: LOAD is a separate parameter
        # transaction, then READ is submitted through the independent minimal
        # HMB_PICKER_COMMAND dict parameter.
        load_result = GriptapeNodes.handle_request(
            SetParameterValueRequest(
                node_name=node.name,
                parameter_name="MAYA_SCENE",
                value=str(scene_copy),
                data_type="str",
            )
        )
        result["load_request_result"] = type(load_result).__name__
        result["load_request_details"] = str(getattr(load_result, "result_details", ""))
        if not isinstance(load_result, SetParameterValueResultSuccess):
            raise RuntimeError(result["load_request_details"] or result["load_request_result"])

        load_state = copy.deepcopy(node._picker_state())
        if str(load_state.get("scene_stage") or "").upper() not in {"LOAD_READY", "MAYA_READING"}:
            raise RuntimeError(str(load_state.get("message") or "LOAD did not become READ-ready."))

        command = picker._default_picker_command(node._hmb_runtime_instance_id)
        command.update(
            {
                "action": "read_scene",
                "action_id": action_id,
                "issued_at_ms": int(time.time() * 1000),
                "payload": {
                    "scene_path": str(scene_copy),
                    "selected_video_slot": 1,
                },
            }
        )
        request_result = GriptapeNodes.handle_request(
            SetParameterValueRequest(
                node_name=node.name,
                parameter_name=picker.WIDGET_COMMAND_PARAMETER,
                value=command,
                data_type="dict",
            )
        )
        result["request_result"] = type(request_result).__name__
        result["request_details"] = str(getattr(request_result, "result_details", ""))
        if not isinstance(request_result, SetParameterValueResultSuccess):
            raise RuntimeError(result["request_details"] or result["request_result"])

        deadline = time.monotonic() + timeout_seconds
        previous_signature: tuple[Any, ...] | None = None
        while time.monotonic() < deadline:
            current = copy.deepcopy(node._picker_state())
            snapshot = compact_state(current)
            signature = (
                snapshot["status"],
                snapshot["scene_stage"],
                snapshot["state_revision"],
                snapshot["backend_ack_action_id"],
                snapshot["native_read_ready"],
            )
            if signature != previous_signature:
                result["transitions"].append(snapshot)
                previous_signature = signature
            terminal = str(current.get("status") or "").upper()
            if terminal in {"OUTLINER_READY", "FAILED", "CANCELLED"}:
                break
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError(f"Widget READ did not finish within {timeout_seconds:.1f} seconds.")

        final_state = copy.deepcopy(node._picker_state())
        result["final_state"] = compact_state(final_state)
        if final_state.get("backend_ack_action_id") != action_id:
            raise RuntimeError("Python did not publish the matching backend action acknowledgement.")
        if str(final_state.get("status") or "").upper() != "OUTLINER_READY":
            raise RuntimeError(str(final_state.get("message") or "READ did not reach OUTLINER_READY."))
        if not final_state.get("native_read_ready"):
            raise RuntimeError("READ completed without native_read_ready.")
        if not final_state.get("cameras"):
            raise RuntimeError("READ completed without a user camera.")
        if not final_state.get("outliner_nodes"):
            raise RuntimeError("READ completed without Outliner groups.")
        # READ is metadata-only. It must not render frames, invoke FFmpeg, or
        # publish/activate an Original preview through the real Griptape
        # HMB_PICKER_COMMAND transport.
        if final_state.get("original_preview_enabled"):
            raise RuntimeError("Metadata-only READ unexpectedly enabled Original preview.")
        for field in (
            "original_video_path",
            "original_video_url",
            "video_path",
            "video_url",
        ):
            if str(final_state.get(field) or ""):
                raise RuntimeError(f"Metadata-only READ unexpectedly populated {field}.")
        native_metadata = (
            final_state.get("native_metadata")
            if isinstance(final_state.get("native_metadata"), dict)
            else {}
        )
        if str(native_metadata.get("original_video_path") or ""):
            raise RuntimeError("Metadata-only READ published an Original path in native metadata.")
        if int(native_metadata.get("preview_frame_count") or 0) != 0:
            raise RuntimeError("Metadata-only READ reported rendered preview frames.")
        expected_output_folder = scene_copy.parent / scene_copy.stem
        expected_original = expected_output_folder / f"{scene_copy.stem}_Orignal.mp4"
        expected_sidecar = expected_output_folder / f"{scene_copy.stem}_Orignal.hmb.json"
        if expected_original.exists() or expected_sidecar.exists():
            raise RuntimeError("Metadata-only READ created an Original preview artifact.")
        if any(key in final_state for key in ("preview_frames", "preview_data_uri", "preview_frame_index")):
            raise RuntimeError("READ completed with retired static preview state.")
        result["ok"] = True
        return result
    finally:
        if not result.get("ok"):
            result["final_state"] = compact_state(copy.deepcopy(node._picker_state()))
        result["test_root"] = str(test_root)
        if not keep:
            shutil.rmtree(test_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exercise VideoPicker LOAD plus independent HMB_PICKER_COMMAND through Griptape's real SetParameterValueRequest transport."
    )
    parser.add_argument("scene", type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.scene, max(10.0, args.timeout), args.keep))
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
