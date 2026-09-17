"""Deterministic I/O barriers; no Maya, broker, or source-media writes."""
from __future__ import annotations

import copy
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBVideoPickerLibrary as picker


def node_state():
    node = picker.HMBVideoPickerLibrary(name="Staged import regression")
    state = node._picker_state()
    first = state["active_picker_shot_uuid"]
    state["picker_shots"][0]["bound_shot_uuid"] = "10000000-0000-4000-8000-000000000001"
    second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    row = copy.deepcopy(state["picker_shots"][0])
    row.update(workspace_uuid=second, bound_shot_uuid="10000000-0000-4000-8000-000000000002", number=2, name="Shot 2", video_asset_uids=[], selected_video_uids=[])
    state["picker_shots"].append(row)
    state = picker._parse_state(state)
    node._write_state(state)
    node._schedule_video_removal_output_sync = lambda: None
    return node, first, second


def cancel(node, import_id):
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "cancel_video_import", "action_id": f"cancel-{import_id}",
        "payload": {"import_id": import_id},
    })


def record(state, path, *, picker_shot_uuid, **_kwargs):
    return picker._append_video_asset(state, {
        "video_path": path, "label": Path(path).name, "import_source_path": path,
        "video_metadata": {"frame_rate": 24, "duration_seconds": 2},
    }, picker_shot_uuid=picker_shot_uuid, defer_thumbnail=True)


# Native selection must NOT resolve/stat UNC paths before loading cards exist.
unc_source = r"\\server\share\영상\clip.mp4"
with patch.dict(os.environ, {"HMB_VIDEO_ASSET_TEST_SELECTIONS": "", "HMB_VIDEO_ASSET_TEST_SELECTION": ""}), \
        patch.object(picker.os, "name", "nt"), \
        patch.object(picker.subprocess, "run", return_value=SimpleNamespace(
            stdout=(unc_source + "\r\n").encode("utf-8"), stderr=b"", returncode=0)), \
        patch.object(picker, "_norm_path", side_effect=AssertionError("UNC lookup before loading cards")):
    assert picker._choose_video_asset_files() == [unc_source]

# Exercise the actual command entry point, not only the synchronous helper.
# The dialog/command transaction must finish with reservations published and
# with no source I/O started. The copy worker then retains the original Shot.
target, first, second = node_state()
scheduled = []
with patch.object(target, "_schedule_action_worker", side_effect=lambda *args: scheduled.append(args)), \
        patch.object(picker, "_choose_video_asset_files", return_value=[unc_source]), \
        patch.object(target, "_import_video_asset", side_effect=AssertionError("Copy started in dialog worker")):
    target._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA, "version": picker.COMMAND_VERSION,
        "runtime_instance_id": target._hmb_runtime_instance_id,
        "action": "browse_video_asset", "action_id": "native-stage",
        "payload": {"picker_shot_uuid": first},
    })
assert len(scheduled) == 1 and scheduled[0][0] == "video_import_copy"
assert len(target._picker_state()["video_imports"]) == 1
assert not target._picker_state()["videos"]
target._write_state(picker._activate_picker_workspace_projection(target._picker_state(), second))
with patch.object(target, "_import_video_asset", side_effect=record), \
        patch.object(picker, "_resolved_video_asset_path", return_value=None):
    scheduled[0][2]()
assert target._picker_state()["active_picker_shot_uuid"] == second
assert target._picker_state()["videos"][0]["picker_shot_uuid"] == first
assert not target._picker_state().get("video_imports")


node, shot1, shot2 = node_state()
entered1, release1, entered2, release2 = (threading.Event() for _ in range(4))
calls, errors = [], []


def staged(state, path, **kwargs):
    calls.append(path)
    if path.endswith("a.mp4"):
        entered1.set()
        assert release1.wait(10)
    elif path.endswith("b.mp4"):
        entered2.set()
        assert release2.wait(10)
    return record(state, path, **kwargs)


def run_import(target, paths, shot, action):
    try:
        target._commit_video_import_sources([{"source_path": path} for path in paths],
            captured_picker_shot_uuid=shot, action_id=action)
    except Exception as exc:
        errors.append(exc)


with patch.object(node, "_import_video_asset", side_effect=staged), patch.object(picker, "_resolved_video_asset_path", return_value=None):
    worker = threading.Thread(target=run_import, args=(node, ["C:/a.mp4", "C:/b.mp4", "C:/c.mp4"], shot1, "batch"))
    worker.start()
    try:
        assert entered1.wait(5)
        pending = node._picker_state()
        assert len(pending["video_imports"]) == 3, "All cards must publish before the first blocked copy completes."
        assert not pending["videos"], "Pending cards must never be published as playable media."
        lock_free = threading.Event()
        def inspect_lock():
            with node._hmb_catalog_state_commit():
                lock_free.set()
        probe = threading.Thread(target=inspect_lock)
        probe.start()
        assert lock_free.wait(1), "Slow copying cannot own the catalog/UI lock."
        probe.join(2)
        cancelled = pending["video_imports"][2]["import_id"]
        cancel(node, cancelled)
        assert len(node._picker_state()["video_imports"]) == 2
        switched = picker._activate_picker_workspace_projection(node._picker_state(), shot2)
        node._write_state(switched)
        release1.set()
        assert entered2.wait(5)
        partial = node._picker_state()
        assert len(partial["videos"]) == 1, "The first ready file must appear before the second copy finishes."
        assert partial["videos"][0]["picker_shot_uuid"] == shot1
        assert partial["active_picker_shot_uuid"] == shot2, "Completion must not navigate back to the captured Shot."
        # A late cancel from a still-visible placeholder crosses the ready echo.
        ready_request = partial["videos"][0]["import_request_id"]
        cancel(node, ready_request)
        assert not node._picker_state()["videos"]
    finally:
        release1.set(); release2.set(); worker.join(10)
    assert not worker.is_alive()
assert not errors, errors
final = node._picker_state()
assert calls == ["C:/a.mp4", "C:/b.mp4"]
assert [item["label"] for item in final["videos"]] == ["b.mp4"]
assert not final.get("video_imports")

# A failed card is terminal, not an endless spinner; retry reuses its capacity.
with patch.object(node, "_import_video_asset", side_effect=ValueError("Unreadable MP4")):
    run_import(node, ["C:/bad.mp4"], shot1, "failed")
failed = node._picker_state()["video_imports"]
assert len(failed) == 1 and failed[0]["status"] == "failed"
assert "Unreadable MP4" in failed[0]["error"]
with patch.object(node, "_import_video_asset", side_effect=record), patch.object(picker, "_resolved_video_asset_path", return_value=None):
    run_import(node, ["C:/bad.mp4"], shot1, "retry")
assert not node._picker_state().get("video_imports")
assert len(node._picker_state()["videos"]) == 2

# Deleting a Shot or node while I/O is outstanding discards the late result.
for scope in ("shot", "node", "channel"):
    target, first, second = node_state()
    started, finish = threading.Event(), threading.Event()
    def delayed(state, path, **kwargs):
        started.set(); assert finish.wait(10)
        return record(state, path, **kwargs)
    with patch.object(target, "_import_video_asset", side_effect=delayed), patch.object(picker, "_resolved_video_asset_path", return_value=None):
        worker = threading.Thread(target=run_import, args=(target, ["C:/late.mp4"], first, scope))
        worker.start()
        try:
            assert started.wait(5)
            if scope == "node":
                target._hmb_node_deleted = True
            elif scope == "channel":
                state = target._picker_state()
                state["channel_uuid"] = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
                target._write_state(state)
            else:
                state = target._picker_state()
                state["picker_shots"] = [row for row in state["picker_shots"] if row["workspace_uuid"] != first]
                state["active_picker_shot_uuid"] = second
                target._write_state(state)
        finally:
            finish.set(); worker.join(10)
        assert not worker.is_alive()
        assert not target._picker_state()["videos"], scope

# Runtime-owned reservations cannot come back from saved/stale widget state.
fresh, first, _ = node_state()
stale = fresh._picker_state()
stale["video_imports"] = failed
fresh._write_state(stale)
assert "video_imports" not in fresh._picker_state()
assert not errors, errors
print("PASS: staged imports paint before blocked I/O, publish incrementally, release UI locks, preserve Shot identity, cancel queued/ready entries, isolate failures/retry and discard deleted Shot/node results.")
