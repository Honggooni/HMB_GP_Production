from __future__ import annotations

from contextlib import suppress
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_thumbnail_backfill_regression",
    TARGET,
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


module_names = (
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.griptape_nodes",
)
saved_modules = {name: sys.modules.get(name) for name in module_names}
saved_run = picker.subprocess.run
saved_find_ffmpeg = picker._find_ffmpeg
saved_external_media_url = picker._external_media_url

published_static_files: list[tuple[bytes, str]] = []


class FakeStaticFilesManager:
    def save_static_file(self, value, filename):
        published_static_files.append((bytes(value), str(filename)))
        return f"http://127.0.0.1:9888/workspace/static_files/{filename}"


class FakeGriptapeNodes:
    StaticFilesManager = FakeStaticFilesManager


package = ModuleType(module_names[0])
package.__path__ = []
retained = ModuleType(module_names[1])
retained.__path__ = []
leaf = ModuleType(module_names[2])
leaf.GriptapeNodes = FakeGriptapeNodes


def install_fake_static_manager() -> None:
    sys.modules[module_names[0]] = package
    sys.modules[module_names[1]] = retained
    sys.modules[module_names[2]] = leaf


def reset_thumbnail_cache() -> None:
    picker._VIDEO_THUMBNAIL_URLS.clear()
    picker._VIDEO_THUMBNAIL_ATTEMPTED.clear()
    picker._VIDEO_THUMBNAIL_FFMPEG = None
    picker._VIDEO_THUMBNAIL_FFMPEG_RESOLVED = False
    published_static_files.clear()


def fake_node(state_store: dict, writes: list[dict]):
    node = object.__new__(picker.HMBVideoPickerLibrary)
    node._hmb_node_deleted = False
    node._hmb_lifecycle_generation = 1
    node._hmb_thumbnail_worker_lock = threading.Lock()
    node._hmb_thumbnail_worker = None
    node._hmb_thumbnail_recovery_generation = 0
    node._hmb_catalog_commit_lock = threading.RLock()
    node._hmb_state_write_lock = threading.RLock()
    node._hmb_authoritative_state = copy.deepcopy(state_store["value"])
    node._picker_state = lambda: copy.deepcopy(state_store["value"])

    def write_state(value):
        writes.append(copy.deepcopy(value))
        state_store["value"] = copy.deepcopy(value)
        node._hmb_authoritative_state = copy.deepcopy(value)

    node._write_state = write_state
    return node


def fifty_video_state(media_path: Path) -> dict:
    state = picker._default_widget_state()
    videos = []
    rows = []
    for shot_index in range(5):
        workspace_uuid = str(uuid.UUID(int=shot_index + 100))
        uids = []
        for card_index in range(10):
            uid = f"shot-{shot_index + 1}-video-{card_index + 1}"
            uids.append(uid)
            videos.append({
                "video_uid": uid,
                "source_uid": uid,
                "picker_shot_uuid": workspace_uuid,
                "catalog_order": len(videos) + 1,
                "video_path": str(media_path.resolve()),
                "project_video_path": str(media_path.resolve()),
                "video_url": "http://127.0.0.1:7000/stale-video.mp4",
                "thumbnail_url": "http://127.0.0.1:7000/stale-thumb.png",
                "thumbnail_runtime_id": "previous-engine-process",
                "label": uid,
                "generation_role": "imported",
                "selected": card_index == 0,
                "selection_order": 1 if card_index == 0 else 0,
            })
        row = copy.deepcopy(state["picker_shots"][0])
        row.update({
            "workspace_uuid": workspace_uuid,
            "number": shot_index + 1,
            "name": f"Shot {shot_index + 1}",
            "video_asset_uids": list(uids),
            "selected_video_uids": [uids[0]],
            "preview_video_uid": uids[0],
        })
        rows.append(row)
    state.update({
        "videos": videos,
        "picker_shots": rows,
        "active_picker_shot_uuid": rows[0]["workspace_uuid"],
        "preview_video_uid": rows[0]["preview_video_uid"],
        "selected_video_uid": rows[0]["preview_video_uid"],
    })
    parsed = picker._parse_state(state)
    assert len(parsed["videos"]) == picker.MAX_PICKER_VIDEO_ASSETS == 50
    return parsed


try:
    install_fake_static_manager()
    picker._find_ffmpeg = lambda *_args, **_kwargs: Path("C:/fake/ffmpeg.exe")
    picker._external_media_url = (
        lambda path: f"http://127.0.0.1:9888/external/{Path(path).name}"
    )

    with tempfile.TemporaryDirectory(
        prefix="hmb-video-thumbnail-",
        dir=ROOT / ".tmp",
    ) as temporary:
        media_path = Path(temporary) / "source.mp4"
        media_path.write_bytes(b"local-video-source")

        immediate_calls: list[list[str]] = []

        def immediate_run(command, **_kwargs):
            immediate_calls.append([str(value) for value in command])
            return SimpleNamespace(
                returncode=0,
                stdout=b"\x89PNG\r\n\x1a\nposter",
                stderr=b"",
            )

        picker.subprocess.run = immediate_run
        reset_thumbnail_cache()
        state = picker._append_video_asset(
            picker._default_widget_state(),
            {
                "video_uid": "poster-a",
                "source_uid": "poster-a",
                "video_path": str(media_path),
                "label": "Poster A",
            },
        )
        state = picker._append_video_asset(
            state,
            {
                "video_uid": "poster-b",
                "source_uid": "poster-b",
                "video_path": str(media_path),
                "label": "Poster B",
            },
        )
        assert len(immediate_calls) == 1
        assert len(published_static_files) == 1
        assert "scale=320:180" in " ".join(immediate_calls[0])
        assert "pad=320:180" in " ".join(immediate_calls[0])
        first, second = state["videos"]
        assert first["thumbnail_url"] == second["thumbnail_url"]
        assert first["thumbnail_runtime_id"] == (
            picker._VIDEO_THUMBNAIL_RUNTIME_ID
        )
        assert picker._parse_state(state)["videos"][0]["thumbnail_url"] == (
            first["thumbnail_url"]
        )

        # Fifty stale cards must hydrate without invoking FFmpeg. Only the
        # process-local poster URL is cleared; ownership and ordering survive.
        saved_fifty = fifty_video_state(media_path)
        before_rows = copy.deepcopy(saved_fifty["picker_shots"])
        before_catalog_order = [
            item["video_uid"] for item in saved_fifty["videos"]
        ]
        run_count_before_restore = len(immediate_calls)
        restore_started = time.perf_counter()
        restored, changed = picker._refresh_saved_video_media_urls(saved_fifty)
        restore_seconds = time.perf_counter() - restore_started
        assert changed is True
        assert len(immediate_calls) == run_count_before_restore
        assert restore_seconds < 2.0
        assert len(restored["videos"]) == 50
        assert [
            (
                row["workspace_uuid"],
                row["video_asset_uids"],
                row["selected_video_uids"],
                row["preview_video_uid"],
            )
            for row in restored["picker_shots"]
        ] == [
            (
                row["workspace_uuid"],
                row["video_asset_uids"],
                row["selected_video_uids"],
                row["preview_video_uid"],
            )
            for row in before_rows
        ]
        assert [item["video_uid"] for item in restored["videos"]] == (
            before_catalog_order
        )
        assert all(not item["thumbnail_url"] for item in restored["videos"])

        # Recovery is daemonized. While its one decode is blocked, mutate the
        # newest state. The final single write must merge posters by UID without
        # reverting that concurrent label/selection edit.
        reset_thumbnail_cache()
        worker_started = threading.Event()
        worker_release = threading.Event()
        worker_calls: list[list[str]] = []

        def blocking_run(command, **_kwargs):
            worker_calls.append([str(value) for value in command])
            worker_started.set()
            assert worker_release.wait(timeout=5.0)
            return SimpleNamespace(
                returncode=0,
                stdout=b"\x89PNG\r\n\x1a\nbackground-poster",
                stderr=b"",
            )

        picker.subprocess.run = blocking_run
        store = {"value": copy.deepcopy(restored)}
        writes: list[dict] = []
        node = fake_node(store, writes)
        schedule_started = time.perf_counter()
        assert node._schedule_missing_video_thumbnail_recovery() is True
        schedule_seconds = time.perf_counter() - schedule_started
        worker = node._hmb_thumbnail_worker
        assert worker is not None and worker.daemon is True
        assert schedule_seconds < 1.0
        assert worker_started.wait(timeout=5.0)
        assert not store["value"]["videos"][0]["thumbnail_url"]
        store["value"]["videos"][0]["label"] = "newest-label"
        store["value"]["picker_shots"][0]["selected_video_uids"] = [
            store["value"]["picker_shots"][0]["video_asset_uids"][1]
        ]
        worker_release.set()
        worker.join(timeout=10.0)
        assert worker.is_alive() is False
        assert len(worker_calls) == 1
        assert len(published_static_files) == 1
        assert len(writes) == 1
        assert store["value"]["videos"][0]["label"] == "newest-label"
        assert store["value"]["picker_shots"][0]["selected_video_uids"] == [
            store["value"]["picker_shots"][0]["video_asset_uids"][1]
        ]
        assert all(item["thumbnail_url"] for item in store["value"]["videos"])
        assert all(
            item["thumbnail_runtime_id"]
            == picker._VIDEO_THUMBNAIL_RUNTIME_ID
            for item in store["value"]["videos"]
        )

        # A deleted/replaced lifecycle may finish FFmpeg, but it may never write
        # its result into the retired node state.
        reset_thumbnail_cache()
        worker_started.clear()
        worker_release.clear()
        retired_store = {"value": copy.deepcopy(restored)}
        retired_writes: list[dict] = []
        retired = fake_node(retired_store, retired_writes)
        assert retired._schedule_missing_video_thumbnail_recovery() is True
        retired_worker = retired._hmb_thumbnail_worker
        assert retired_worker is not None
        assert worker_started.wait(timeout=5.0)
        retired._hmb_node_deleted = True
        retired._hmb_lifecycle_generation += 1
        worker_release.set()
        retired_worker.join(timeout=10.0)
        assert retired_worker.is_alive() is False
        assert retired_writes == []
        assert all(
            not item["thumbnail_url"]
            for item in retired_store["value"]["videos"]
        )
finally:
    picker.subprocess.run = saved_run
    picker._find_ffmpeg = saved_find_ffmpeg
    picker._external_media_url = saved_external_media_url
    for name, saved in saved_modules.items():
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved
    with suppress(Exception):
        picker._VIDEO_THUMBNAIL_URLS.clear()
        picker._VIDEO_THUMBNAIL_ATTEMPTED.clear()


print(
    "HMB VideoPicker 320x180 poster cache + nonblocking 50-card backfill + "
    "latest-state/lifecycle merge regression: PASS"
)
