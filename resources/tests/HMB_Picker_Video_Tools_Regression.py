from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker
import _hmb_video_tools as media


def command(node, op, settings=None):
    state = node._picker_state()
    node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "video_tools", "action_id": f"{op}-{threading.get_ident()}-{len(node._hmb_processed_action_ids)}",
        "payload": {"op": op, "picker_shot_uuid": state["active_picker_shot_uuid"], "settings": settings or {}}})
    job = node._hmb_video_tools_job
    if job and job.get("thread"):
        job["thread"].join(30)
        assert not job["thread"].is_alive()
    return node._picker_state()


node = picker.HMBVideoPickerLibrary(name="Picker Video Tools Regression")
# This isolated node is not registered in the desktop's live flow. Exercise
# the real node class/state machinery with local parameter publication; a live
# retained-bus mount is covered separately by the browser/install checks.
local_publication = patch.object(picker, "_request_parameter_value", return_value=False)
local_publication.start()
state = node._picker_state()
workspace = state["active_picker_shot_uuid"]
draft = state["video_tools_by_shot"][workspace]
draft.update(revision=7, active_tool="crop")
draft["crop"].update(source_uid="source-one", custom_width=32, zoom=2)
draft["crop_by_source"] = {"source-one": copy.deepcopy(draft["crop"])}
node._write_state(state)
saved = json.loads(json.dumps(node._picker_state()))
restored = picker._parse_state(saved)
assert restored["video_tools_by_shot"][workspace] == draft
assert picker._reset_picker_state_preserving_loader_media(saved)["video_tools_by_shot"][workspace] == draft
stale = copy.deepcopy(saved)
stale["video_tools_by_shot"][workspace]["revision"] = 6
stale["video_tools_by_shot"][workspace]["crop"]["custom_width"] = 80
assert node._merge_widget_state(saved, stale)["video_tools_by_shot"][workspace] == draft

with tempfile.TemporaryDirectory(prefix="hmb_picker_tools_") as directory:
    folder = Path(directory)
    sources = []
    for index, color in enumerate(("red", "blue")):
        source = folder / f"source-{index}.mp4"
        subprocess.run([media._find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                        f"color=c={color}:s=96x64:r=24:d=0.5", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(source)], check=True, timeout=30)
        sources.append(source)
    original_bytes = [path.read_bytes() for path in sources]
    with patch.object(picker, "_external_media_url", side_effect=lambda path: Path(path).as_uri()):
        state = node._picker_state()
        for index, path in enumerate(sources):
            state = picker._append_video_asset(state, {
                "video_uid": f"loaded-{index}", "video_path": str(path), "label": f"Loaded {index}", "markers": [],
            }, picker_shot_uuid=workspace)
        node._write_state(state)
        selected_before = picker._picker_selected_video_uids(node._picker_state())
        concat = media.default_picker_tools_state()["concatenate"]
        concat.update(inputs=[str(path) for path in sources], input_uids=["loaded-0", "loaded-1"],
                      output_path=str(folder / "joined.mp4"), manual_output_enabled=True)
        completed = command(node, "concatenate", concat)
        assert completed["video_tools_status"]["status"] == "succeeded", completed["video_tools_status"]
        joined = Path(completed["video_tools_output"])
        assert joined.is_file()
        assert abs(media.probe_video(joined)["duration"] - 1.0) < 0.1
        assert picker._picker_selected_video_uids(completed) == selected_before
        added = command(node, "add_result")
        assert len(added["videos"]) == 3
        assert picker._picker_selected_video_uids(added) == selected_before, added["picker_shots"]
        again = command(node, "add_result")
        assert len(again["videos"]) == 3
        crop = media.default_picker_tools_state()["crop"]
        crop.update(input=str(joined), output_path=str(folder / "crop.mp4"), manual_output_enabled=True,
                    crop_position="Custom", custom_width=48, custom_height=32, custom_left=16, custom_top=8)
        cropped = command(node, "crop", crop)
        assert cropped["video_tools_status"]["status"] == "succeeded", cropped["video_tools_status"]
        probe = media.probe_video(cropped["video_tools_output"])
        assert (probe["width"], probe["height"]) == (48, 32)
        assert [path.read_bytes() for path in sources] == original_bytes
        overwrite = command(node, "crop", {**crop, "output_path": str(sources[0])})
        assert overwrite["video_tools_status"]["status"] == "failed"
        assert sources[0].read_bytes() == original_bytes[0]

    # A late completion cannot leak across workspace/binding identity changes.
    entered = threading.Event()
    release = threading.Event()
    class DelayedService:
        def cancel(self):
            pass
        def concatenate(self, settings, cancel_event=None):
            entered.set()
            assert release.wait(10)
            return {"path": str(joined), "duration": 1, "width": 96, "height": 64}
    with patch.object(media, "VideoMediaService", DelayedService):
        state = node._picker_state()
        node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
            "action": "video_tools", "action_id": "late-job", "payload": {"op": "concatenate",
            "picker_shot_uuid": workspace, "settings": concat}})
        assert entered.wait(5)
        job = node._hmb_video_tools_job
        changed = node._picker_state()
        changed["channel_uuid"] = "22222222-2222-4222-8222-222222222222"
        node._reconcile_video_tools_state(changed)
        assert job["cancel"].is_set()
        assert node._hmb_video_tools_job is None
        release.set()
        job["thread"].join(5)
        assert node._hmb_video_tools_results[workspace]["status"] == "cancelled"

    cancellation = threading.Event()
    cancellation.set()
    cancelled_settings = {**concat, "output_path": str(folder / "cancelled.mp4")}
    try:
        media.VideoMediaService().concatenate(cancelled_settings, cancel_event=cancellation)
    except media.VideoToolError as exc:
        assert "cancel" in str(exc).lower()
    else:
        raise AssertionError("Cancelled edit succeeded")
    assert not (folder / "cancelled.mp4").exists()

embedded_node = picker.HMBVideoPickerLibrary(name="Picker Embedded Video Tools Regression")
embedded_parameter = picker._get_parameter_obj(embedded_node, picker.WIDGET_STATE_PARAMETER)
captured_embedded_jobs = []
embedded_job_ready = threading.Event()

def capture_embedded_job(job):
    captured_embedded_jobs.append(copy.deepcopy(job["settings"]))
    embedded_node._hmb_video_tools_job = None
    embedded_job_ready.set()

def embedded_transaction(value):
    prepared = embedded_node.before_value_set(embedded_parameter, value)
    embedded_node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, prepared, skip_before_value_set=True, emit_change=False)
    embedded_node.after_value_set(embedded_parameter, prepared)

with patch.object(embedded_node, "_schedule_action_worker", side_effect=lambda _action, _identifier, callback: callback()), patch.object(embedded_node, "_run_picker_video_tool", side_effect=capture_embedded_job):
    embedded_value = embedded_node._picker_state()
    embedded_workspace = embedded_value["active_picker_shot_uuid"]
    embedded_draft = embedded_value["video_tools_by_shot"][embedded_workspace]
    embedded_draft["revision"] += 1
    embedded_draft["concatenate"]["inputs"] = ["C:/media/draft-one.mp4", "C:/media/draft-two.mp4"]
    embedded_value["state_writer"] = "widget"
    embedded_value[picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD] = {
        "runtime_instance_id": embedded_node._hmb_runtime_instance_id,
        "action": "video_tools", "action_id": "embedded-video-tools-once",
        "payload": {"op": "concatenate", "picker_shot_uuid": embedded_workspace},
    }
    embedded_transaction(embedded_value)
    assert embedded_job_ready.wait(5)
    assert captured_embedded_jobs and captured_embedded_jobs[0]["inputs"] == embedded_draft["concatenate"]["inputs"], captured_embedded_jobs
    assert embedded_node._picker_state()["video_tools_by_shot"][embedded_workspace]["concatenate"]["inputs"] == embedded_draft["concatenate"]["inputs"]
    echo = embedded_node._picker_state()
    assert picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD not in echo
    embedded_transaction(echo)
    embedded_transaction(embedded_value)
    assert len(captured_embedded_jobs) == 1, "Embedded command replayed during a normal or duplicate echo."

print("Picker Video Tools: persistence, stale draft, real concat/crop, source preservation, non-selected add, binding cancellation and one-shot embedded command passed.")
local_publication.stop()
