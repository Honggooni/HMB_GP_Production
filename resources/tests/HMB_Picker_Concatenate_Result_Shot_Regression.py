"""First-card Shot capture remains immutable through render and Add Result."""
from __future__ import annotations

import copy
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


def send(node, operation, settings=None, wait=True):
    state = node._picker_state()
    node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "video_tools", "action_id": f"result-route-{len(node._hmb_processed_action_ids)}",
        "payload": {"op": operation, "picker_shot_uuid": state["active_picker_shot_uuid"], "settings": settings or {}}})
    job = node._hmb_video_tools_job
    if wait and job:
        job["thread"].join(20)
        assert not job["thread"].is_alive()
    return node._picker_state()


with patch.object(picker, "_request_parameter_value", return_value=False), \
     patch.object(picker, "_external_media_url", side_effect=lambda path: Path(path).as_uri()), \
     patch.object(picker, "_video_asset_thumbnail_url", return_value=("", "")), \
     tempfile.TemporaryDirectory(prefix="hmb-concat-result-shot-") as temporary:
    # Match the canonical paths returned by the media service on Windows CI.
    folder = Path(temporary).resolve()
    source = folder / "source.mp4"
    subprocess.run([media._find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
        "color=c=red:s=96x64:r=24:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True, timeout=20)
    original_bytes = source.read_bytes()
    node = picker.HMBVideoPickerLibrary(name="First concatenate card result Shot")
    state = node._picker_state()
    shots = [f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 6)]
    rows = []
    for number, uid in enumerate(shots, 1):
        row = copy.deepcopy(state["picker_shots"][0])
        row.update(workspace_uuid=uid, bound_shot_uuid=f"10000000-0000-4000-8000-{number:012d}", number=number, name=f"Shot {number}")
        rows.append(row)
    state.update(picker_shots=rows, active_picker_shot_uuid=shots[3])
    for number in (1, 2, 4):
        state = picker._append_video_asset(state, {
            "video_uid": f"source-{number}", "video_path": str(source), "label": f"Source {number}", "markers": []},
            picker_shot_uuid=shots[number - 1])
    state = picker._activate_picker_workspace_projection(state, shots[3])
    node._write_state(state)
    work_preview = node._picker_state()["preview_video_uid"]
    work_selection = picker._picker_selected_video_uids(node._picker_state())
    concat = {**media.default_picker_tools_state()["concatenate"], "inputs": [str(source), str(source)],
              "input_uids": ["source-2", "source-4"], "manual_output_enabled": True,
              "output_path": str(folder / "from-shot-2.mp4")}

    # The render captures destination before a newer queue order reaches state.
    entered, release = threading.Event(), threading.Event()
    RealService = media.VideoMediaService
    class DelayedService(RealService):
        def concatenate(self, settings, **kwargs):
            entered.set()
            assert release.wait(10)
            return super().concatenate(settings, **kwargs)
    with patch.object(media, "VideoMediaService", DelayedService):
        send(node, "concatenate", concat, wait=False)
        assert entered.wait(5)
        job = node._hmb_video_tools_job
        assert job["result_picker_shot_uuid"] == shots[1]
        reordered = node._picker_state()
        reordered["video_tools_by_shot"][shots[3]]["concatenate"].update({**concat, "input_uids": ["source-4", "source-2"]})
        reordered["video_tools_by_shot"][shots[3]]["revision"] += 1
        node._write_state(reordered)
        release.set()
        job["thread"].join(20)
        assert not job["thread"].is_alive()
    complete = node._picker_state()
    assert complete["video_tools_status"]["status"] == "succeeded", complete["video_tools_status"]
    assert complete["video_tools_status"]["picker_shot_uuid"] == shots[3]
    assert complete["video_tools_status"]["result_picker_shot_uuid"] == shots[1]
    assert complete["video_tools_status"]["result_source_uid"] == "source-2"
    target_before = next(row for row in complete["picker_shots"] if row["workspace_uuid"] == shots[1])
    added = send(node, "add_result")
    output_card = next(card for card in added["videos"] if card.get("video_path") == str(folder / "from-shot-2.mp4").replace("\\", "/"))
    assert output_card["picker_shot_uuid"] == shots[1]
    assert added["active_picker_shot_uuid"] == shots[3]
    assert added["preview_video_uid"] == work_preview
    assert picker._picker_selected_video_uids(added) == work_selection
    target_after = next(row for row in added["picker_shots"] if row["workspace_uuid"] == shots[1])
    assert target_after["selected_video_uids"] == target_before["selected_video_uids"]
    assert target_after["preview_video_uid"] == target_before["preview_video_uid"]
    assert len(send(node, "add_result")["videos"]) == len(added["videos"])

    # A new render after reordering captures the newly first card, Shot 4.
    complete = send(node, "concatenate", {**concat, "input_uids": ["source-4", "source-2"],
                       "output_path": str(folder / "from-shot-4.mp4")})
    assert complete["video_tools_status"]["result_picker_shot_uuid"] == shots[3]
    added = send(node, "add_result")
    assert any(card["picker_shot_uuid"] == shots[3] and card.get("video_path", "").endswith("from-shot-4.mp4") for card in added["videos"])

    # Deleting the captured destination never redirects the completed output.
    complete = send(node, "concatenate", {**concat, "input_uids": ["source-1", "source-4"],
                       "output_path": str(folder / "from-deleted-shot.mp4")})
    missing_target = copy.deepcopy(complete)
    missing_target["picker_shots"] = [row for row in missing_target["picker_shots"] if row["workspace_uuid"] != shots[0]]
    try:
        node._add_picker_video_tool_result(missing_target, shots[3])
    except media.VideoToolError as exc:
        assert "captured result Shot" in str(exc) and "deleted" in str(exc)
    else:
        raise AssertionError("A deleted result destination was silently replaced")
    assert (folder / "from-deleted-shot.mp4").is_file()

    # Missing UID/standalone old external references can render a file, but
    # have no first-card Shot and therefore cannot be silently added elsewhere.
    complete = send(node, "concatenate", {**concat, "input_uids": ["", "source-4"],
                       "output_path": str(folder / "unowned.mp4")})
    assert complete["video_tools_status"]["status"] == "succeeded"
    assert not complete["video_tools_status"]["result_picker_shot_uuid"]
    try:
        node._add_picker_video_tool_result(complete, shots[3])
    except media.VideoToolError as exc:
        assert "no captured Shot owner" in str(exc)
    else:
        raise AssertionError("Unowned input fell back to the work Shot")
    unowned = copy.deepcopy(complete)
    unowned["video_tools_by_shot"][shots[3]]["external_sources"] = [{"source_uid": "external-only", "local_path": str(source)}]
    assert picker._picker_concatenate_result_workspace(unowned, {"input_uids": ["external-only"]}) == ""

    # Crop retains its previous work-Shot destination contract.
    crop = {**media.default_picker_tools_state()["crop"], "input": str(source), "source_uid": "source-2",
            "manual_output_enabled": True, "output_path": str(folder / "crop-work-shot.mp4"),
            "crop_position": "Custom", "custom_width": 48, "custom_height": 32}
    complete = send(node, "crop", crop)
    assert complete["video_tools_status"]["result_picker_shot_uuid"] == shots[3]
    added = send(node, "add_result")
    assert any(card["picker_shot_uuid"] == shots[3] and card.get("video_path", "").endswith("crop-work-shot.mp4") for card in added["videos"])
    assert source.read_bytes() == original_bytes

print("Concatenate result Shot: exact first-card owner, immutable Run capture, pre/post render reorder, explicit Add, duplicate protection, missing/deleted destination diagnostics, work preview preservation and unchanged Crop passed.")
