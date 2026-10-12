"""Deterministic import/optional-poster barriers, with no external services."""
from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import sys
import threading
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker


def make_node():
    node = picker.HMBVideoPickerLibrary(name=f"Import bottleneck regression {uuid.uuid4().hex}")
    try:
        from griptape_nodes.exe_types.flow import ControlFlow
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    except ImportError:
        pass  # The hostless fallback intentionally has no Engine registry.
    else:
        manager = GriptapeNodes.EventManager()
        manager.initialize_queue()
        options = {"name": f"ImportFixtureFlow_{uuid.uuid4().hex}"}
        if "engine" in inspect.signature(ControlFlow).parameters:
            options["engine"] = manager.engine
        flow = ControlFlow(**options)
        flow.add_node(node)
        GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)
        GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
        GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name
    node._schedule_video_removal_output_sync = lambda: None
    return node, node._picker_state()["active_picker_shot_uuid"]


def fake_import(state, path, *, picker_shot_uuid, **_kwargs):
    return picker._append_video_asset(state, {
        "video_path": path, "label": Path(path).name, "import_source_path": path,
    }, picker_shot_uuid=picker_shot_uuid, defer_thumbnail=True)


def wait_posters(node):
    worker = node._hmb_video_import_poster_worker
    if worker is not None:
        worker.join(5)
        assert not worker.is_alive(), "Optional poster worker did not finish"


metrics = {}

# Metadata is optional and local-only: no automatic executable provisioning,
# no guessed 24 fps, and a short subprocess timeout instead of 30 s per file.
with patch.object(picker, "_video_thumbnail_ffmpeg", return_value=None), \
        patch.object(picker, "_find_ffprobe", return_value=None), \
        patch.object(picker.subprocess, "run", side_effect=AssertionError("Probe with no installed tool")):
    assert picker._local_video_player_metadata(Path("C:/source.mp4")) == {}
metadata_json = json.dumps({"streams": [{"width": 1920, "height": 1080, "codec_name": "h264",
    "avg_frame_rate": "30000/1001", "r_frame_rate": "30/1"}],
    "format": {"duration": "5.005", "size": "1048576", "format_name": "mov,mp4"}}).encode()
with patch.object(picker, "_video_thumbnail_ffmpeg", return_value=Path("C:/installed/ffmpeg.exe")), \
        patch.object(picker, "_find_ffprobe", return_value=Path("C:/installed/ffprobe.exe")), \
        patch.object(picker.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=metadata_json)) as run:
    metadata = picker._local_video_player_metadata(Path("C:/source.mp4"))
    assert abs(metadata["frame_rate"] - 30000 / 1001) < 1e-9
    assert metadata["duration_seconds"] == 5.005 and metadata["width"] == 1920
    assert run.call_args.kwargs["timeout"] == 3.0
with patch.object(picker, "_video_thumbnail_ffmpeg", return_value=Path("C:/installed/ffmpeg.exe")), \
        patch.object(picker, "_find_ffprobe", return_value=Path("C:/installed/ffprobe.exe")), \
        patch.object(picker.subprocess, "run", side_effect=TimeoutError("fixture probe timeout")), \
        patch.object(picker, "_diagnostic_exception"):
    assert picker._local_video_player_metadata(Path("C:/source.mp4")) == {}

# Import provenance comparisons are used inside the catalog commit lock.
# Stored paths have already been resolved by the real import worker. These
# comparisons must never resolve/stat an offline share a second time.
started = time.perf_counter()
with patch.object(Path, "resolve", side_effect=AssertionError("Filesystem lookup in catalog comparison")):
    first = picker._video_import_source_key(r"\\server\share\folder\..\clip.mp4")
    second = picker._video_import_source_key(r"\\server\share\clip.mp4")
    assert first == second, (first, second)
    for _ in range(1000):
        assert picker._video_import_source_key(r"\\server\share\clip.mp4") == second
metrics["1000_catalog_source_comparisons_ms"] = round((time.perf_counter() - started) * 1000, 2)

# Hold the FIRST optional thumbnail indefinitely. Both playable cards and the
# whole copy batch must still finish; a second import batch must also complete.
node, shot = make_node()
poster_started, release_poster, batch_finished = (threading.Event() for _ in range(3))
errors = []
poster_threads = set()


def readable(item):
    assert not node._hmb_catalog_commit_lock._is_owned(), "Media probe held catalog lock"
    assert not node._hmb_state_write_lock._is_owned(), "Media probe held UI state lock"
    return Path(item["video_path"])


def poster(path, uid):
    poster_threads.add(threading.get_ident())
    if path.name == "first.mp4":
        poster_started.set()
        assert release_poster.wait(5)
    return f"poster://{uid}", path.stem


def run_batch():
    try:
        node._commit_video_import_sources(
            [{"source_path": "C:/first.mp4"}, {"source_path": "C:/second.mp4"}],
            captured_picker_shot_uuid=shot, action_id="blocked-poster-batch",
        )
    except Exception as exc:
        errors.append(str(exc))
    finally:
        batch_finished.set()


with patch.object(node, "_import_video_asset", side_effect=fake_import), \
        patch.object(picker, "_resolved_video_asset_path", side_effect=readable), \
        patch.object(picker, "_video_thumbnail_signature", side_effect=lambda path: path.stem), \
        patch.object(picker, "_video_asset_thumbnail_url", side_effect=poster):
    started = time.perf_counter()
    worker = threading.Thread(target=run_batch)
    worker.start()
    try:
        assert poster_started.wait(3)
        assert batch_finished.wait(1), "Optional poster blocked the following source copy"
        metrics["two_ready_cards_while_first_poster_blocked_ms"] = round((time.perf_counter() - started) * 1000, 2)
        assert [v["label"] for v in node._picker_state()["videos"]] == ["first.mp4", "second.mp4"]
        assert not node._picker_state().get("video_imports")
        node._commit_video_import_sources([{"source_path": "C:/third.mp4"}],
            captured_picker_shot_uuid=shot, action_id="second-batch")
        state = node._picker_state()
        assert len(state["videos"]) == 3
        assert len(poster_threads) == 1, "Import posters should share one worker"
        # Cancel crossing the ready-card echo removes exactly that imported UID;
        # its still-running poster must never restore it.
        first_import = state["videos"][0]["import_request_id"]
        node._handle_picker_command({
            "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
            "runtime_instance_id": node._hmb_runtime_instance_id,
            "action": "cancel_video_import", "action_id": "cancel-ready",
            "payload": {"import_id": first_import},
        })
    finally:
        release_poster.set()
        worker.join(5)
        wait_posters(node)
assert not errors, errors
ready = node._picker_state()["videos"]
assert [v["label"] for v in ready] == ["second.mp4", "third.mp4"]
assert all(v.get("thumbnail_url") for v in ready)

# Optional decode errors remain isolated and do not prevent a later poster.
node, shot = make_node()
calls = []


def failure_then_success(path, uid):
    calls.append(path.name)
    if path.name == "bad-poster.mp4":
        raise RuntimeError("fixture poster decoder unavailable")
    return f"poster://{uid}", path.stem


with patch.object(node, "_import_video_asset", side_effect=fake_import), \
        patch.object(picker, "_resolved_video_asset_path", side_effect=lambda item: Path(item["video_path"])), \
        patch.object(picker, "_video_thumbnail_signature", side_effect=lambda path: path.stem), \
        patch.object(picker, "_video_asset_thumbnail_url", side_effect=failure_then_success), \
        patch.object(picker, "_diagnostic_exception"):
    node._commit_video_import_sources([{"source_path": "C:/bad-poster.mp4"}, {"source_path": "C:/good-poster.mp4"}],
        captured_picker_shot_uuid=shot, action_id="poster-errors")
    wait_posters(node)
state = node._picker_state()
assert state["status"] == "VIDEO_READY"
assert len(state["videos"]) == 2 and not state.get("video_imports")
assert state["videos"][1]["thumbnail_url"]
assert calls == ["bad-poster.mp4", "good-poster.mp4"]

# A native dialog failure is a local import result, not a FAILED Maya/Picker
# state that disables previously selected usable media.
before = copy.deepcopy(state["videos"])
with patch.object(picker, "_choose_video_asset_files", side_effect=TimeoutError("fixture native dialog failed")):
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "browse_video_asset", "action_id": "failed-dialog",
        "payload": {"picker_shot_uuid": shot},
    })
after = node._picker_state()
assert after["status"] == "VIDEO_READY" and after["videos"] == before
assert after["backend_ack_action_id"] == "failed-dialog" and not after["pending_action"]

# Delayed native-dialog startup and rapid clicking still open just one dialog.
opened, close_dialog = threading.Event(), threading.Event()
dialog_calls = []


def slow_dialog(_path):
    dialog_calls.append(True)
    opened.set()
    assert close_dialog.wait(5)
    return []


def browse(action):
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "browse_video_asset", "action_id": action,
        "payload": {"picker_shot_uuid": shot},
    })


with patch.object(picker, "_choose_video_asset_files", side_effect=slow_dialog):
    first_dialog = threading.Thread(target=browse, args=("slow-dialog",))
    first_dialog.start()
    try:
        assert opened.wait(3)
        browse("repeated-dialog-click")
        assert len(dialog_calls) == 1
        assert node._picker_state()["videos"] == before
    finally:
        close_dialog.set()
        first_dialog.join(5)
assert not node._hmb_video_browse_lock.locked(), "Cancel must allow a new dialog"

# Restored-card backfill uses the same filesystem/commit separation. A slow
# source check cannot make the Load button wait for the state lock.
with patch.object(picker, "_resolved_video_asset_path", side_effect=readable), \
        patch.object(picker, "_video_thumbnail_signature", side_effect=lambda path: path.stem), \
        patch.object(picker, "_video_asset_thumbnail_url", side_effect=lambda path, uid: (f"poster://{uid}", path.stem)):
    node._recover_missing_video_thumbnails(node._hmb_lifecycle_generation)
assert all(v.get("thumbnail_url") for v in node._picker_state()["videos"])

# A source replaced during extraction retains its new state and rejects the
# previous source's poster. The card itself stays usable.
snapshot = node._picker_state()["videos"][0]


def replace_source(path, uid):
    latest = node._picker_state()
    current = next(v for v in latest["videos"] if v["video_uid"] == uid)
    current["video_path"] = "C:/changed.mp4"
    current["thumbnail_url"] = ""
    node._write_state(latest)
    return "poster://obsolete", path.stem


with patch.object(picker, "_resolved_video_asset_path", side_effect=readable), \
        patch.object(picker, "_video_thumbnail_signature", side_effect=lambda path: path.stem), \
        patch.object(picker, "_video_asset_thumbnail_url", side_effect=replace_source):
    node._publish_video_import_posters([snapshot])
current = node._picker_state()["videos"][0]
assert current["video_path"] == "C:/changed.mp4" and not current["thumbnail_url"]

# A retained publication failure after a ready card cannot abandon another
# import that joined the same optional worker while that batch was in flight.
node, _shot = make_node()
failed_batch_started = threading.Event()
release_failed_batch = threading.Event()
surviving_batch_done = threading.Event()
batch_uids = []


def interrupted_publication(batch, **_kwargs):
    batch_uids.extend(item["video_uid"] for item in batch)
    if batch[0]["video_uid"] == "interrupted-batch":
        failed_batch_started.set()
        assert release_failed_batch.wait(5)
        raise RuntimeError("fixture retained publication interrupted")
    surviving_batch_done.set()


with patch.object(node, "_publish_video_import_posters", side_effect=interrupted_publication):
    node._schedule_video_import_posters([{"video_uid": "interrupted-batch"}])
    assert failed_batch_started.wait(3)
    first_worker = node._hmb_video_import_poster_worker
    node._schedule_video_import_posters([{"video_uid": "later-ready-card"}])
    assert node._hmb_video_import_poster_worker is first_worker
    release_failed_batch.set()
    assert surviving_batch_done.wait(3), "Publication failure stranded a later ready card"
    first_worker.join(5)
    assert not first_worker.is_alive()
assert batch_uids == ["interrupted-batch", "later-ready-card"]
assert not node._hmb_video_import_posters and node._hmb_video_import_poster_worker is None

metrics["checks"] = ["UNC comparisons are lexical", "poster never blocks later imports",
    "one coalesced poster worker", "file probes outside catalog lock", "ready-card cancellation",
    "optional decoder failure isolation", "native dialog failure preserves usable media",
    "one dialog during rapid clicks", "restored poster checks outside locks", "changed source rejects stale poster",
    "local-only bounded metadata", "unknown metadata remains unknown",
    "publication failure drains later ready cards"]
print("HMB_PICKER_IMPORT_BOTTLENECK=PASS " + json.dumps(metrics, ensure_ascii=False))
