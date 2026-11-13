"""First-card Shot capture remains immutable through render and Add Result."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import threading
from importlib.util import find_spec
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker
import HMBPromptLibrary as prompt
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
    ffmpeg = media._find_ffmpeg()
    sources = {}
    colors = {1: "red", 2: "lime", 3: "blue", 4: "yellow", 5: "magenta"}
    for number, color in colors.items():
        source_dir = folder / f"shot-{number}"
        source_dir.mkdir()
        source = source_dir / "source.mp4"
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
            f"color=c={color}:s=96x64:r=24:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True, timeout=20)
        sources[number] = source
    original_bytes = {number: source.read_bytes() for number, source in sources.items()}

    def concat_settings(order, filename):
        return {**media.default_picker_tools_state()["concatenate"],
                "inputs": [str(sources[number]) for number in order],
                "input_uids": [f"source-{number}" for number in order],
                "manual_output_enabled": True, "output_path": str(folder / filename)}

    def verify_frames(filename, order):
        decoded = subprocess.check_output([ffmpeg, "-v", "error", "-i", str(folder / filename),
            "-vf", "scale=1:1,format=rgb24", "-threads", "1", "-f", "rawvideo", "-"], timeout=20)
        rgb_on = {1: (True, False, False), 2: (False, True, False), 3: (False, False, True),
                  4: (True, True, False), 5: (True, False, True)}
        assert len(decoded) == len(order) * 12 * 3, f"Expected 12 frames per source, got {len(decoded) // 3} frames"
        for index, number in enumerate(order):
            clip = decoded[index * 36:(index + 1) * 36]
            assert all((channel > 200 if rgb_on[number][component % 3] else channel < 25)
                       for component, channel in enumerate(clip)), f"Decoded segment {index + 1} must be {colors[number]} from Shot {number}"
        duration = media.probe_video(folder / filename)["duration"]
        assert abs(duration - 0.5 * len(order)) < 0.02, duration
        return duration

    node = picker.HMBVideoPickerLibrary(name="First concatenate card result Shot")
    state = node._picker_state()
    shots = [f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 6)]
    rows = []
    for number, uid in enumerate(shots, 1):
        row = copy.deepcopy(state["picker_shots"][0])
        row.update(workspace_uuid=uid, bound_shot_uuid=f"10000000-0000-4000-8000-{number:012d}", number=number, name=f"Shot {number}")
        rows.append(row)
    state.update(picker_shots=rows, active_picker_shot_uuid=shots[3])
    for number in colors:
        state = picker._append_video_asset(state, {
            "video_uid": f"source-{number}", "video_path": str(sources[number]), "label": f"Source {number}",
            "source_fps": 24, "source_frame_count": 12, "duration_seconds": 0.5, "markers": []},
            picker_shot_uuid=shots[number - 1])
    first_order = [2, 5, 3, 1, 4]
    reversed_order = list(reversed(first_order))
    concat = concat_settings(first_order, "from-shot-2.mp4")
    drafts = {}
    for index, workspace in enumerate(shots):
        order = first_order[index:] + first_order[:index]
        settings = concat if workspace == shots[3] else concat_settings(order, f"draft-{index + 1}.mp4")
        drafts[workspace] = {**media.default_picker_tools_state(), "active_tool": "concatenate", "concatenate": settings}
    state["video_tools_by_shot"] = copy.deepcopy(drafts)
    state = picker._activate_picker_workspace_projection(state, shots[3])
    node._write_state(state)
    saved_state = node.get_parameter_value(picker.WIDGET_STATE_PARAMETER)
    saved_file = folder / "picker-widget-state.json"
    saved_file.write_text(json.dumps(saved_state), encoding="utf-8")
    restore_started = perf_counter()
    reopened = picker.HMBVideoPickerLibrary(name="Reopen cross-Shot concatenate drafts")
    reopened._schedule_post_hydration_shot_reconcile = lambda: False
    state_parameter = picker._get_parameter_obj(reopened, picker.WIDGET_STATE_PARAMETER)
    serialized = json.loads(saved_file.read_text(encoding="utf-8"))
    hydrated = reopened.before_value_set(state_parameter, serialized)
    reopened.set_parameter_value(picker.WIDGET_STATE_PARAMETER, hydrated, initial_setup=True, skip_before_value_set=True)
    reopened.after_deserialize()
    reopened.after_load()
    reopened.on_loaded()
    restore_ms = (perf_counter() - restore_started) * 1000
    assert reopened._picker_state()["active_picker_shot_uuid"] == shots[3]
    expected_owners = {f"source-{number}": workspace for number, workspace in enumerate(shots, 1)}
    saved_rows = {row["workspace_uuid"]: row for row in saved_state["picker_shots"]}
    for workspace in (*shots, shots[3]):
        reopened._write_state(picker._activate_picker_workspace_projection(reopened._picker_state(), workspace))
        state = reopened._picker_state()
        assert state["active_picker_shot_uuid"] == workspace
        assert state["video_tools_by_shot"][workspace]["concatenate"] == drafts[workspace]["concatenate"]
        assert {item["video_uid"]: item["picker_shot_uuid"] for item in state["videos"]} == expected_owners
        assert picker._picker_selected_video_uids(state) == saved_rows[workspace]["selected_video_uids"]
        assert state["preview_video_uid"] == saved_rows[workspace]["preview_video_uid"]
    node = reopened
    work_preview = node._picker_state()["preview_video_uid"]
    work_selection = picker._picker_selected_video_uids(node._picker_state())

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
        reordered["video_tools_by_shot"][shots[3]]["concatenate"].update(concat_settings(reversed_order, "from-shot-4.mp4"))
        reordered["video_tools_by_shot"][shots[3]]["revision"] += 1
        node._write_state(reordered)
        render_started = perf_counter()
        release.set()
        job["thread"].join(20)
        assert not job["thread"].is_alive()
        first_render_ms = (perf_counter() - render_started) * 1000
    complete = node._picker_state()
    assert complete["video_tools_status"]["status"] == "succeeded", complete["video_tools_status"]
    assert complete["video_tools_status"]["picker_shot_uuid"] == shots[3]
    assert complete["video_tools_status"]["result_picker_shot_uuid"] == shots[1]
    assert complete["video_tools_status"]["result_source_uid"] == "source-2"
    first_duration = verify_frames("from-shot-2.mp4", first_order)
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
    render_started = perf_counter()
    complete = send(node, "concatenate")
    second_render_ms = (perf_counter() - render_started) * 1000
    assert complete["video_tools_status"]["result_picker_shot_uuid"] == shots[3]
    second_duration = verify_frames("from-shot-4.mp4", reversed_order)
    added = send(node, "add_result")
    assert any(card["picker_shot_uuid"] == shots[3] and card.get("video_path", "").endswith("from-shot-4.mp4") for card in added["videos"])

    # Deleting the captured destination never redirects the completed output.
    complete = send(node, "concatenate", concat_settings([1, 4], "from-deleted-shot.mp4"))
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
    complete = send(node, "concatenate", {**concat_settings([2, 4], "unowned.mp4"), "input_uids": ["", "source-4"]})
    assert complete["video_tools_status"]["status"] == "succeeded"
    assert not complete["video_tools_status"]["result_picker_shot_uuid"]
    try:
        node._add_picker_video_tool_result(complete, shots[3])
    except media.VideoToolError as exc:
        assert "no captured Shot owner" in str(exc)
    else:
        raise AssertionError("Unowned input fell back to the work Shot")
    unowned = copy.deepcopy(complete)
    unowned["video_tools_by_shot"][shots[3]]["external_sources"] = [{"source_uid": "external-only", "local_path": str(sources[1])}]
    assert picker._picker_concatenate_result_workspace(unowned, {"input_uids": ["external-only"]}) == ""

    # Crop retains its previous work-Shot destination contract.
    crop = {**media.default_picker_tools_state()["crop"], "input": str(sources[2]), "source_uid": "source-2",
            "manual_output_enabled": True, "output_path": str(folder / "crop-work-shot.mp4"),
            "crop_position": "Custom", "custom_width": 48, "custom_height": 32}
    complete = send(node, "crop", crop)
    assert complete["video_tools_status"]["result_picker_shot_uuid"] == shots[3]
    added = send(node, "add_result")
    owned = {Path(card["video_path"]).name: card for card in added["videos"] if card["picker_shot_uuid"] == shots[3]}
    ordered_names = ["source.mp4", "from-shot-4.mp4", "crop-work-shot.mp4"]
    ordered_uids = [owned[name]["video_uid"] for name in ordered_names]
    shot_row = next(row for row in added["picker_shots"] if row["workspace_uuid"] == shots[3])
    assert shot_row["selected_video_uids"] == ["source-4"]
    shot_row["selected_video_uids"] = ordered_uids
    shot_row["revision"] += 1
    node._write_state(picker._activate_picker_workspace_projection(added, shots[3]))
    catalog = node._hmb_standalone_shot_routing_catalog()
    channel = catalog["channel_uuid"]
    snapshot = prompt._validate_picker_shot_routing_snapshot(
        node._hmb_shot_routing_snapshot_for(channel_uuid=channel, shot_uuid=shots[3]), expected_channel_uuid=channel)
    exact_shot = snapshot["shots"][0]
    assert exact_shot["selected_source_uids"] == ordered_uids
    assert exact_shot["shot_uuid"] == shots[3]
    prompt_state = prompt._apply_picker_payload(prompt._default_widget_state(), exact_shot["picker_payload"], connected=True)
    assert prompt_state["picker"]["ordered_video_uids"] == ordered_uids
    assert [(entry["fps"], entry["frame_count"]) for entry in prompt_state["picker"]["frame_metadata"]] == [(24, 12), (24, 60), (24, 12)]
    if find_spec("HMBAnalysisAgent") is not None:
        from HMBAnalysisAgent import HMBAnalysisAgent

        prompt_state["shot"].update(channel_uuid=channel, shot_uuid=shots[3])
        for row in prompt_state["videos"]:
            row["video_sub_type"] = "Analysis"
        routed_files = [snapshot["media_by_source_uid"][uid] for uid in ordered_uids]
        analysis_sources = prompt.HMBPromptLibrary._hmb_project_analysis_sources(prompt_state, [], routed_files, {})
        assert [entry["shot_reference"] for entry in analysis_sources] == ["@video1", "@video2", "@video3"]
        assert [Path(entry["path"]).name for entry in analysis_sources] == ordered_names
        assert [entry["duration_seconds"] for entry in analysis_sources] == [0.5, 2.5, 0.5]

        prompt_node = object.__new__(prompt.HMBPromptLibrary)
        # Supply the validated Picker route while exercising the Analysis owner's normal APIs.
        prompt_node._hmb_prompt_shot_document = lambda **query: {"analysis_sources": analysis_sources
            if (query["channel_uuid"], query["shot_uuid"]) == (channel, shots[3]) else []}
        analysis = object.__new__(HMBAnalysisAgent)
        for role in ("before", "after"):
            analysis._role = role
            for entry, filename in zip(analysis_sources, ordered_names):
                selection = {"origin": "prompt", "kind": "video", "source_id": entry["source_id"]}
                resolved = analysis._resolve_source(prompt_node, channel, shots[3], selection)
                assert Path(resolved["path"]).resolve() == Path(owned[filename]["video_path"]).resolve()
                assert analysis._resolve_source(prompt_node, channel, shots[2], selection) == {}
        print("Local Analysis: all three exact-Shot references resolved in both roles.")
    assert {number: source.read_bytes() for number, source in sources.items()} == original_bytes

print("Cross-Shot concatenate: five SDK-restored drafts; two five-source renders; 60 frames each; decoded order, first-card owner, immutable Run capture, explicit Add, original bytes, and original/concatenated/cropped exact-Shot Prompt references passed.")
print(f"SDK reopen {restore_ms:.1f}ms | 2→5→3→1→4 {first_duration:.2f}s encoded in {first_render_ms:.1f}ms | "
      f"4→1→3→5→2 {second_duration:.2f}s encoded in {second_render_ms:.1f}ms")
