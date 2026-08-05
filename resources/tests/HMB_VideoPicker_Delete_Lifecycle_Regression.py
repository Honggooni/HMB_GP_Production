from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_delete_lifecycle_regression",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


def asset(uid: str, order: int) -> dict:
    return {
        "video_uid": uid,
        "source_uid": uid,
        "video_path": f"C:/shot/catalog/{uid}.mp4",
        "label": uid,
        "generation_role": "imported",
        "media_kind": "imported_mp4_reference",
        "selected": True,
        "selection_order": order,
        "source_fps": 24.0,
        "decoded_frame_count": 24,
        "start_frame": 101.0,
        "end_frame": 124.0,
        "has_maya_frame_range": True,
    }


def command(node, action: str, action_id: str, payload: dict | None = None) -> None:
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA,
        "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": action,
        "action_id": action_id,
        "payload": payload or {},
    })


node = picker.HMBVideoPickerLibrary(name="Video Delete Lifecycle Contract")
state_store = {
    "value": picker._parse_state({
        **picker._default_widget_state(),
        "status": "VIDEO_READY",
        "scene_stage": "VIDEO_READY",
        "native_read_ready": True,
        "scene_request_status": "COMPLETE",
        "videos": [asset("preview-a", 1), asset("preview-b", 2)],
        "preview_video_uid": "preview-a",
        "selected_video_uid": "preview-a",
    })
}
published_outputs: list[dict] = []
node._picker_state = lambda: deepcopy(state_store["value"])
node._write_state = lambda value: state_store.__setitem__("value", deepcopy(value))
node._sync_outputs_from_state = lambda value: published_outputs.append(deepcopy(value))


# Deleting the active preview is an immediate metadata command. It must return
# to the same stable stage, acknowledge the command, and select a valid next
# preview without touching the process-cancellation event.
node._hmb_cancel_requested.clear()
command(
    node,
    "delete_video_asset",
    "delete-current-preview",
    {"video_uid": "preview-a"},
)
deleted_state = state_store["value"]
assert deleted_state["backend_ack_action_id"] == "delete-current-preview"
assert deleted_state["status"] == "VIDEO_READY"
assert deleted_state["scene_stage"] == "VIDEO_READY"
assert deleted_state["operation_kind"] == ""
assert deleted_state["pending_action"] == ""
assert deleted_state["pending_action_id"] == ""
assert [item["video_uid"] for item in deleted_state["videos"]] == ["preview-b"]
assert deleted_state["preview_video_uid"] == "preview-b"
assert deleted_state["selected_video_uid"] == "preview-b"
assert deleted_state["selected_video_path"].endswith("/preview-b.mp4")
assert not node._hmb_cancel_requested.is_set()
assert published_outputs[-1]["preview_video_uid"] == "preview-b"


# A duplicate/stale UI command is idempotent instead of escalating a harmless
# missing card into the node-wide FAILED state.
command(
    node,
    "delete_video_asset",
    "delete-current-preview-again",
    {"video_uid": "preview-a"},
)
duplicate_state = state_store["value"]
assert duplicate_state["backend_ack_action_id"] == "delete-current-preview-again"
assert duplicate_state["status"] == "VIDEO_READY"
assert duplicate_state["scene_stage"] == "VIDEO_READY"
assert [item["video_uid"] for item in duplicate_state["videos"]] == ["preview-b"]
assert "already absent" in duplicate_state["message"]


# Other immediate commands also retain a terminal stage. In particular,
# clearing the log used to leave the same PYTHON_COMMAND_RECEIVED lock behind.
command(node, "clear_log", "clear-log-stable")
cleared_state = state_store["value"]
assert cleared_state["backend_ack_action_id"] == "clear-log-stable"
assert cleared_state["status"] == "VIDEO_READY"
assert cleared_state["scene_stage"] == "VIDEO_READY"


# Import remains terminal and must not inherit the transient operation stage.
tmp_parent = ROOT / ".tmp"
tmp_parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(
    prefix="hmb_delete_lifecycle_",
    dir=tmp_parent,
) as temporary:
    source_mp4 = Path(temporary) / "import_after_delete.mp4"
    source_mp4.write_bytes(
        b"\x00\x00\x00\x08ftyp"
        b"\x00\x00\x00\x08mdat"
        b"\x00\x00\x00\x08moov"
    )
    command(
        node,
        "import_video_asset",
        "import-stable",
        {"source_path": str(source_mp4), "label": "Imported after delete"},
    )
    imported_state = state_store["value"]
    assert imported_state["backend_ack_action_id"] == "import-stable"
    assert imported_state["status"] == "VIDEO_READY"
    assert imported_state["scene_stage"] == "VIDEO_READY"
    assert len(imported_state["videos"]) == 2


# A delayed delete command received while an operation is genuinely reserved
# must not mutate the catalog, set cancellation, or replace the running stage.
running_state = deepcopy(state_store["value"])
running_state.update({
    "status": "RUNNING",
    "scene_stage": "MAYA_READING",
    "operation_kind": "run_video",
})
state_store["value"] = picker._parse_state(running_state)
before_running_delete = deepcopy(state_store["value"]["videos"])
node._hmb_pending_operation_id = "active-run"
node._hmb_cancel_requested.clear()
try:
    command(
        node,
        "delete_video_asset",
        "delete-during-run",
        {"video_uid": before_running_delete[0]["video_uid"]},
    )
finally:
    node._hmb_pending_operation_id = ""
blocked_state = state_store["value"]
assert blocked_state["backend_ack_action_id"] == "delete-during-run"
assert blocked_state["videos"] == before_running_delete
assert blocked_state["status"] == "RUNNING"
assert blocked_state["scene_stage"] == "MAYA_READING"
assert blocked_state["operation_kind"] == "run_video"
assert not node._hmb_cancel_requested.is_set()
assert "ignored while a Picker operation is running" in blocked_state["message"]


print(
    "HMB VideoPicker delete lifecycle regression: PASS "
    "(stable immediate stage, preview fallback, no operation cancellation)"
)
