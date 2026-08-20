from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_snapshot_history_regression",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


def video(uid: str, order: int) -> dict:
    return {
        "video_uid": uid,
        "source_uid": uid,
        "video_path": f"C:/shot/catalog/{uid}.mp4",
        "label": uid,
        "selected": True,
        "selection_order": order,
        "video_slot": order,
        "source_fps": 24.0,
        "decoded_frame_count": 24,
    }


def snapshot(
    uid: str,
    frame: float,
    *,
    video_uid: str = "video-a",
    path: str = "",
    created_at_ms: int = 0,
) -> dict:
    return {
        "snapshot_uid": uid,
        "video_uid": video_uid,
        "render_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "frame": frame,
        "data_uri": f"data:image/png;base64,{uid.encode().hex()}",
        "path": path,
        "created_at_ms": created_at_ms,
    }


node = picker.HMBVideoPickerLibrary(name="Snapshot History Contract")
base = picker._parse_state({
    **picker._default_widget_state(),
    "active_slot_count": 2,
    "videos": [video("video-a", 1), video("video-b", 2)],
    "preview_video_uid": "video-a",
    "selected_video_uid": "video-a",
})


# Snapshot creation appends records instead of replacing the previous frame.
first = snapshot("snapshot-a", 101.0, created_at_ms=1001)
second = snapshot("snapshot-b", 109.0, created_at_ms=1002)
history_state = picker._append_snapshot_history_record(base, first)
history_state = picker._append_snapshot_history_record(history_state, second)
assert [item["snapshot_uid"] for item in history_state["snapshots"]] == [
    "snapshot-a",
    "snapshot-b",
]
assert history_state["active_snapshot_uid"] == "snapshot-b"
assert history_state["viewport_mode"] == "snapshot"
assert history_state["snapshot_active"] is True
assert history_state["snapshot_frame"] == 109.0


# Navigation changes only the pointer/projection. Every record and its content
# hash survives while heavyweight legacy inline PNG bytes stay excluded.
navigation = deepcopy(history_state)
navigation["active_snapshot_uid"] = "snapshot-a"
navigation["viewport_mode"] = "snapshot"
navigation = picker._parse_state(navigation)
assert navigation["snapshot_frame"] == 101.0
assert navigation["snapshots"] == history_state["snapshots"]
video_mode = picker._apply_active_snapshot_projection(
    deepcopy(navigation),
    viewport_mode="video",
)
assert video_mode["viewport_mode"] == "video"
assert video_mode["snapshot_active"] is False
assert video_mode["active_snapshot_uid"] == "snapshot-a"
assert video_mode["snapshots"] == history_state["snapshots"]


# Maya authoring always stays on private render slot 1, while the stable video
# UID is frozen separately in the operation context.
context_state = deepcopy(history_state)
context_state["selected_video_slot"] = 2
context_state["preview_video_uid"] = "video-b"
context_state["selected_video_uid"] = "video-b"
context_state["snapshot_request_video_uid"] = "video-b"
context = node._create_operation_context(
    "render_snapshot",
    "C:/shot/scene.ma",
    context_state,
    video_slot=2,
)
assert context.video_slot == picker.PRIMARY_COLOR_VIDEO_SLOT
assert context.snapshot_video_uid == "video-b"


# Slot-only saved states migrate once to deterministic snapshot/video UIDs.
legacy_source = {
    "videos": [video("legacy-video", 1)],
    "snapshots": [{
        "video_slot": 1,
        "frame": 117.0,
        "data_uri": "data:image/png;base64,TEVHQUNZ",
        "path": "C:/legacy/snapshot_video1.png",
    }],
    "snapshot_active": True,
    "snapshot_video_slot": 1,
    "snapshot_frame": 117.0,
    "snapshot_data_uri": "data:image/png;base64,TEVHQUNZ",
    "snapshot_path": "C:/legacy/snapshot_video1.png",
}
legacy = picker._parse_state(legacy_source)
assert len(legacy["snapshots"]) == 1
legacy_record = legacy["snapshots"][0]
assert legacy_record["snapshot_uid"].startswith("snapshot-legacy-")
assert legacy_record["video_uid"] == "legacy-video"
assert legacy_record["render_video_slot"] == 1
assert legacy["active_snapshot_uid"] == legacy_record["snapshot_uid"]
assert legacy["viewport_mode"] == "snapshot"
assert picker._parse_state(legacy)["snapshots"][0]["snapshot_uid"] == legacy_record[
    "snapshot_uid"
]


# Once associated, deleting/reordering video cards never relinks an orphaned
# Snapshot to a new card occupying the readable slot.
orphan = picker._parse_state({
    **history_state,
    "videos": [video("replacement-video", 1)],
})
assert [item["video_uid"] for item in orphan["snapshots"]] == [
    "video-a",
    "video-a",
]


# A stale browser echo cannot replace the backend-authoritative history.
authoritative = deepcopy(history_state)
authoritative["state_revision"] = 10
stale_widget = picker._parse_state({
    **picker._default_widget_state(),
    "state_revision": 9,
    "snapshots": [snapshot("stale-widget", 1.0)],
    "active_snapshot_uid": "stale-widget",
    "viewport_mode": "snapshot",
})
merged = node._merge_widget_state(authoritative, stale_widget)
assert [item["snapshot_uid"] for item in merged["snapshots"]] == [
    "snapshot-a",
    "snapshot-b",
]
assert merged["active_snapshot_uid"] == "snapshot-b"


tmp_parent = ROOT / ".tmp"
tmp_parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(
    prefix="hmb_snapshot_history_",
    dir=tmp_parent,
) as temporary:
    temporary_root = Path(temporary)
    scene_path = temporary_root / "shot.ma"
    scene_path.write_text("// snapshot history regression\n", encoding="utf-8")

    first_path = node._snapshot_cache_path(scene_path, "delete-a")
    second_path = node._snapshot_cache_path(scene_path, "delete-b")
    first_path.write_bytes(b"PNG-A")
    second_path.write_bytes(b"PNG-B")
    delete_state = picker._parse_state({
        **base,
        "scene_path": str(scene_path),
        "scene_request_path": str(scene_path),
        "native_read_ready": True,
    })
    delete_state = picker._append_snapshot_history_record(
        delete_state,
        snapshot("delete-a", 201.0, path=str(first_path), created_at_ms=2001),
        scene_path=scene_path,
    )
    delete_state = picker._append_snapshot_history_record(
        delete_state,
        snapshot("delete-b", 202.0, path=str(second_path), created_at_ms=2002),
        scene_path=scene_path,
    )
    state_store = {"value": deepcopy(delete_state)}
    node._picker_state = lambda: deepcopy(state_store["value"])
    node._write_state = lambda value: state_store.__setitem__(
        "value", deepcopy(value)
    )

    # Exact UID removal deletes only its validated private PNG and selects the
    # nearest surviving history record.
    node._handle_delete_snapshot_action(
        deepcopy(delete_state),
        snapshot_uid="delete-b",
    )
    after_second_delete = state_store["value"]
    assert not second_path.exists()
    assert first_path.exists()
    assert [item["snapshot_uid"] for item in after_second_delete["snapshots"]] == [
        "delete-a"
    ]
    assert after_second_delete["active_snapshot_uid"] == "delete-a"
    assert after_second_delete["viewport_mode"] == "snapshot"

    # Untrusted paths are removed from metadata but never deleted from disk.
    outside_path = temporary_root / "outside.png"
    outside_path.write_bytes(b"DO-NOT-DELETE")
    unsafe_state = picker._append_snapshot_history_record(
        after_second_delete,
        snapshot("unsafe-path", 203.0, path=str(outside_path), created_at_ms=2003),
        scene_path=scene_path,
    )
    state_store["value"] = deepcopy(unsafe_state)
    node._handle_delete_snapshot_action(
        deepcopy(unsafe_state),
        snapshot_uid="unsafe-path",
    )
    assert outside_path.exists()
    assert [item["snapshot_uid"] for item in state_store["value"]["snapshots"]] == [
        "delete-a"
    ]

    node._handle_delete_snapshot_action(
        deepcopy(state_store["value"]),
        snapshot_uid="delete-a",
    )
    empty_history = state_store["value"]
    assert not first_path.exists()
    assert empty_history["snapshots"] == []
    assert empty_history["active_snapshot_uid"] == ""
    assert empty_history["viewport_mode"] == "video"
    assert empty_history["snapshot_active"] is False

    # The eleventh append evicts the oldest record and only its safe private
    # PNG. The remaining history stays ordered and bounded at ten.
    capped = picker._parse_state({
        **base,
        "scene_path": str(scene_path),
        "scene_request_path": str(scene_path),
    })
    cache_paths: list[Path] = []
    for index in range(11):
        uid = f"cap-{index}"
        cache_path = node._snapshot_cache_path(scene_path, uid)
        cache_path.write_bytes(f"PNG-{index}".encode())
        cache_paths.append(cache_path)
        capped = picker._append_snapshot_history_record(
            capped,
            snapshot(
                uid,
                300.0 + index,
                path=str(cache_path),
                created_at_ms=3000 + index,
            ),
            scene_path=scene_path,
        )
    assert len(capped["snapshots"]) == picker.MAX_SNAPSHOT_HISTORY
    assert [item["snapshot_uid"] for item in capped["snapshots"]] == [
        f"cap-{index}" for index in range(1, 11)
    ]
    assert not cache_paths[0].exists()
    assert all(path.exists() for path in cache_paths[1:])

    # Generate's new viewport transition preserves both history and cache.
    generated_view = picker._apply_active_snapshot_projection(
        deepcopy(capped),
        viewport_mode="video",
    )
    assert generated_view["viewport_mode"] == "video"
    assert generated_view["snapshots"] == capped["snapshots"]
    assert all(path.exists() for path in cache_paths[1:])

    # Same-scene LOAD/READ preparation retains history. Selecting another
    # scene clears all Snapshot state so records cannot leak across scenes.
    same_scene = node._build_native_scene_selection_state(
        str(scene_path),
        capped,
    )
    assert same_scene["snapshots"] == capped["snapshots"]
    other_scene_path = temporary_root / "other.ma"
    other_scene_path.write_text("// another scene\n", encoding="utf-8")
    other_scene = node._build_native_scene_selection_state(
        str(other_scene_path),
        capped,
    )
    assert other_scene["snapshots"] == []
    assert other_scene["active_snapshot_uid"] == ""
    assert other_scene["viewport_mode"] == "video"

    # Deletion is blocked while Maya/FFmpeg work is reserved, just like video
    # catalog deletion. History and files remain untouched.
    state_store["value"] = deepcopy(capped)
    node._hmb_pending_operation_id = "active-snapshot-operation"
    try:
        node._handle_delete_snapshot_action(
            deepcopy(capped),
            snapshot_uid="cap-10",
        )
    finally:
        node._hmb_pending_operation_id = ""
    assert len(state_store["value"]["snapshots"]) == picker.MAX_SNAPSHOT_HISTORY
    assert cache_paths[10].exists()
    assert "ignored while a Picker operation is running" in state_store["value"][
        "message"
    ]


print(
    "HMB VideoPicker Snapshot history regression: PASS "
    "(append/navigation/UID delete/fallback/migration/merge/cap/safety)"
)
