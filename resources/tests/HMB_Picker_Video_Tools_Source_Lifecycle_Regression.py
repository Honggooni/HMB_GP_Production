"""Independent edit sources, exact UID deletion, output paths and UI-lock safety.

FFmpeg/probe are real. The desktop publication boundary, native file selection,
and project-directory resolver are isolated where explicitly patched below.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker
import _hmb_video_tools as media


def make_node():
    node = picker.HMBVideoPickerLibrary(name="Independent edit lifecycle")
    state = node._picker_state()
    rows = []
    for number in range(1, 6):
        row = copy.deepcopy(state["picker_shots"][0])
        row.update(workspace_uuid=f"00000000-0000-4000-8000-{number:012d}",
                   bound_shot_uuid=f"10000000-0000-4000-8000-{number:012d}",
                   number=number, name=f"Shot {number}")
        rows.append(row)
    state.update(picker_shots=rows, active_picker_shot_uuid=rows[3]["workspace_uuid"])
    node._write_state(state)
    return node, [row["workspace_uuid"] for row in rows]


def send(node, operation, settings=None, workspace=None, action_id=None, wait=True):
    uid = workspace or node._picker_state()["active_picker_shot_uuid"]
    identifier = action_id or f"tool-{len(node._hmb_processed_action_ids)}"
    node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "video_tools", "action_id": identifier,
        "payload": {"op": operation, "picker_shot_uuid": uid, "settings": settings or {}}})
    job = node._hmb_video_tools_job
    if wait and job and job.get("thread"):
        job["thread"].join(20)
        assert not job["thread"].is_alive()
    return node._picker_state()


def delete(node, uid, action_id):
    node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "delete_video_asset", "action_id": action_id, "payload": {"video_uid": uid}})
    return node._picker_state()


def add(state, source, uid, workspace):
    return picker._append_video_asset(state, {"video_uid": uid, "video_path": str(source),
        "video_url": source.as_uri(), "import_source_path": str(source),
        "generation_role": "imported", "media_kind": "imported_mp4_reference",
        "label": uid, "markers": []}, picker_shot_uuid=workspace)


with patch.object(picker, "_request_parameter_value", return_value=False), \
     patch.object(picker, "_external_media_url", side_effect=lambda p: Path(p).as_uri()), \
     patch.object(picker, "_video_asset_thumbnail_url", return_value=("", "")), \
     tempfile.TemporaryDirectory(prefix="hmb-tools-lifecycle-") as temporary:
    folder = Path(temporary)
    paths = []
    for index, color in enumerate(("red", "green", "blue")):
        source = folder / f"source-{index}.mp4"
        subprocess.run([media._find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
            f"color=c={color}:s=96x64:r=24:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
            check=True, timeout=20)
        paths.append(source)
    original = [p.read_bytes() for p in paths]

    # Invalid/blank paths are removed together with their paired identities.
    paired = media.normalize_picker_tools_state({"concatenate": {
        "inputs": [str(paths[0]), "", str(paths[1]), str(paths[0])],
        "input_uids": [None, "discard", "B", "A"]}})["concatenate"]
    assert paired["inputs"] == [str(paths[0]), str(paths[1]), str(paths[0])]
    assert paired["input_uids"] == ["", "B", "A"]
    if picker.os.name == "nt":
        dialog_result = types.SimpleNamespace(returncode=0, stdout=(str(paths[0]) + "\n" + str(paths[1])).encode(), stderr=b"")
        with patch.dict(picker.os.environ, {"HMB_VIDEO_ASSET_TEST_SELECTIONS": "", "HMB_VIDEO_ASSET_TEST_SELECTION": ""}), \
             patch.object(picker.subprocess, "run", return_value=dialog_result) as dialog:
            assert picker._choose_video_asset_files("", multiple=False) == [str(paths[0])]
            assert "$d.Multiselect=$false" in dialog.call_args.args[0][-1]
            assert picker._choose_video_asset_files("") == [str(paths[0]), str(paths[1])]
            assert "$d.Multiselect=$true" in dialog.call_args.args[0][-1]

    # An independently authored, unbound tools workspace is meaningful even
    # before any external source card is dragged into an edit queue.
    standalone = picker._default_widget_state()
    standalone["picker_shots"] = [{"workspace_uuid": f"50000000-0000-4000-8000-{i:012d}", "number": i} for i in range(1, 4)]
    standalone["active_picker_shot_uuid"] = standalone["picker_shots"][0]["workspace_uuid"]
    standalone["video_tools_by_shot"] = {standalone["picker_shots"][2]["workspace_uuid"]: {
        "external_sources": [{"source_uid": "standalone-external", "local_path": str(paths[0])}]}}
    assert len(picker._parse_state(standalone)["picker_shots"]) == 3

    # All-Shot sources compose into Shot 4 without transferring ownership.
    node, shots = make_node()
    state = node._picker_state()
    for index, path in enumerate(paths):
        state = add(state, path, f"source-{index}", shots[index])
    state = picker._activate_picker_workspace_projection(state, shots[3])
    node._write_state(state)
    ownership = [(r["workspace_uuid"], list(r["video_asset_uids"]), list(r["selected_video_uids"])) for r in node._picker_state()["picker_shots"]]
    settings = dict(media.default_picker_tools_state()["concatenate"], inputs=[str(p) for p in paths],
        input_uids=[f"source-{i}" for i in range(3)], manual_output_enabled=True, output_path=str(folder / "shot4.mp4"))
    state = send(node, "concatenate", settings)
    assert state["video_tools_status"]["status"] == "succeeded", state["video_tools_status"]
    assert abs(media.probe_video(state["video_tools_output"])["duration"] - 1.5) < .1
    assert [(r["workspace_uuid"], r["video_asset_uids"], r["selected_video_uids"]) for r in state["picker_shots"]] == ownership
    state = send(node, "add_result")
    assert len(next(r for r in state["picker_shots"] if r["workspace_uuid"] == shots[0])["video_asset_uids"]) == 2
    assert len(next(r for r in state["picker_shots"] if r["workspace_uuid"] == shots[3])["video_asset_uids"]) == 0
    assert state["active_picker_shot_uuid"] == shots[3]
    assert not picker._picker_selected_video_uids(state)

    # No Maya: direct loading and automatic output use the first source folder,
    # never an unchecked old custom-path draft.
    external, external_shots = make_node()
    state = send(external, "browse_sources", {"tool": "concatenate", "paths": [str(p) for p in paths]})
    ext_workspace = external_shots[3]
    sources = state["video_tools_by_shot"][ext_workspace]["external_sources"]
    assert len(sources) == 3 and not state["videos"]
    assert state["video_tools_by_shot"][ext_workspace]["concatenate"]["inputs"] == [str(p) for p in paths]
    assert not state["video_tools_by_shot"][ext_workspace]["crop"]["input"]
    assert sources[0]["width"] == 96 and sources[0]["frame_count"] == 12
    state = send(external, "browse_sources", {"tool": "concatenate", "paths": [str(paths[0])]})
    assert len(state["video_tools_by_shot"][ext_workspace]["external_sources"]) == 3
    auto_path = folder / "must-not-exist.mp4"
    state = send(external, "concatenate", {**settings, "output_path": str(auto_path), "manual_output_enabled": False})
    assert state["video_tools_status"]["status"] == "succeeded", state["video_tools_status"]
    assert Path(state["video_tools_output"]).parent == paths[0].parent
    assert not auto_path.exists()
    external_settings = {**settings, "output_path": str(folder / "external.mp4"), "input_uids": [s["source_uid"] for s in sources]}
    state = send(external, "concatenate", external_settings)
    assert state["video_tools_status"]["status"] == "succeeded", state["video_tools_status"]
    crop = dict(media.default_picker_tools_state()["crop"], input=str(paths[0]), source_uid=sources[0]["source_uid"],
        output_path=str(folder / "external-crop.mp4"), manual_output_enabled=True,
        crop_position="Custom", custom_width=48, custom_height=32)
    state = send(external, "crop", crop)
    assert state["video_tools_status"]["status"] == "succeeded"
    assert not state["videos"], "Independent tool sources were registered into the Picker"
    concat_before_crop = copy.deepcopy(state["video_tools_by_shot"][ext_workspace]["concatenate"])
    with patch.object(picker, "_choose_video_asset_files", return_value=[str(paths[0]), str(paths[1])]) as chooser:
        state = send(external, "browse_sources", {"tool": "crop"})
    chooser.assert_called_once_with("", multiple=False)
    entry = state["video_tools_by_shot"][ext_workspace]
    assert entry["crop"]["input"] == str(paths[0])
    assert entry["crop"]["source_uid"] == sources[0]["source_uid"]
    assert entry["concatenate"] == concat_before_crop
    assert len(entry["external_sources"]) == 3
    widget = copy.deepcopy(state)
    widget_entry = widget["video_tools_by_shot"][ext_workspace]
    widget_entry["revision"] += 1
    widget_entry["concatenate"]["inputs"].pop(0)
    widget_entry["concatenate"]["input_uids"].pop(0)
    deleted_concat = external._merge_widget_state(state, widget)
    assert deleted_concat["video_tools_by_shot"][ext_workspace]["crop"] == entry["crop"]
    assert len(deleted_concat["video_tools_by_shot"][ext_workspace]["concatenate"]["inputs"]) == len(concat_before_crop["inputs"]) - 1
    # Top-card deletion is a scoped authored delta; it cannot delete metadata
    # still referenced by the other tool, original Picker cards or actual files.
    before_remove = copy.deepcopy(state)
    widget = copy.deepcopy(state)
    widget["video_tools_by_shot"][ext_workspace]["revision"] += 1
    widget["video_tools_by_shot"][ext_workspace]["crop"].update(input="", source_uid="")
    state = external._merge_widget_state(state, widget)
    external._write_state(state)
    state = external._picker_state()
    assert state["video_tools_by_shot"][ext_workspace]["concatenate"] == concat_before_crop
    assert len(state["video_tools_by_shot"][ext_workspace]["external_sources"]) == 3
    merged = external._merge_widget_state(state, before_remove)
    assert not merged["video_tools_by_shot"][ext_workspace]["crop"]["input"]

    # Loading a Maya scene cannot redirect independently selected tool outputs.
    state = external._picker_state()
    state.update(scene_path=str(folder / "scene.ma"), scene_request_path=str(folder / "scene.ma"))
    external._write_state(state)
    state = send(external, "concatenate", {**external_settings, "manual_output_enabled": False, "output_path": str(auto_path)})
    assert state["video_tools_status"]["status"] == "succeeded", state["video_tools_status"]
    assert Path(state["video_tools_output"]).parent == paths[0].parent
    assert not auto_path.exists()

    # One deleted UID removes all queued occurrences and crop history in every
    # Shot, preserving an independently registered UID at the same path.
    state = node._picker_state()
    state = add(state, paths[0], "same-path-other-owner", shots[4])
    state = picker._activate_picker_workspace_projection(state, shots[3])
    for shot in shots:
        entry = state["video_tools_by_shot"][shot]
        entry["concatenate"].update(inputs=[str(paths[0])] * 4,
            input_uids=["source-0", "same-path-other-owner", "source-0", "external-independent"])
        entry["crop"].update(input=str(paths[0]), source_uid="source-0")
        entry["crop_by_source"] = {"source-0": copy.deepcopy(entry["crop"])}
    state["video_tools_by_shot"][shots[3]]["external_sources"] = [{"source_uid": "external-independent", "local_path": str(paths[0])}]
    node._write_state(state)
    before_delete = copy.deepcopy(node._picker_state())
    state = delete(node, "source-0", "delete-source-zero")
    assert state["video_delete_results"]["delete-source-zero"]["status"] == "removed"
    for entry in state["video_tools_by_shot"].values():
        assert entry["concatenate"]["input_uids"] == ["same-path-other-owner", "external-independent"]
        assert not entry["crop"]["source_uid"] and "source-0" not in entry["crop_by_source"]
    stale = copy.deepcopy(before_delete)
    for entry in stale["video_tools_by_shot"].values():
        entry["revision"] += 100
    merged = node._merge_widget_state(state, stale)
    for entry in merged["video_tools_by_shot"].values():
        assert "source-0" not in entry["concatenate"]["input_uids"]
    assert not any(item["video_uid"] == "source-0" for item in merged["videos"])
    assert picker._parse_state(json.dumps(merged))["video_tools_deleted_sources_by_shot"]
    if getattr(node, "_hmb_video_removal_sync_thread", None):
        node._hmb_video_removal_sync_thread.join(10)

    # Slow media resolution is not inside catalog/state locks. A second delete
    # is acknowledged before the probe is released; only latest state publishes.
    entered, release = threading.Event(), threading.Event()
    built = picker._build_synchronized_video_outputs
    captured = []
    def slow_build(state, **kwargs):
        entered.set()
        assert release.wait(10)
        return built(state, **kwargs)
    def publish(state, **kwargs):
        captured.append([v["video_uid"] for v in state["videos"]])
        assert "_prepared_publication" in kwargs
    with patch.object(picker, "_build_synchronized_video_outputs", side_effect=slow_build), patch.object(node, "_sync_outputs_from_state", side_effect=publish):
        state = delete(node, "source-1", "rapid-first")
        assert entered.wait(5)
        assert node._hmb_state_write_lock.acquire(timeout=1)
        node._hmb_state_write_lock.release()
        state = delete(node, "source-2", "rapid-second")
        assert state["video_delete_results"]["rapid-second"]["status"] == "removed"
        release.set()
        node._hmb_video_removal_sync_thread.join(10)
        assert not node._hmb_video_removal_sync_thread.is_alive()
    assert len(captured) == 1 and "source-1" not in captured[0] and "source-2" not in captured[0], captured

    # External browse is equally non-blocking, commits to the captured Shot
    # after navigation, and never restores a deleted target workspace.
    browse_node, browse_shots = make_node()
    actual_probe = media.probe_video
    entered, release = threading.Event(), threading.Event()
    def slow_probe(path):
        entered.set()
        assert release.wait(10)
        return actual_probe(path)
    with patch.object(media, "probe_video", side_effect=slow_probe):
        thread = threading.Thread(target=send, args=(browse_node, "browse_sources", {"tool": "concatenate", "paths": [str(paths[0])]}, browse_shots[3]))
        thread.start()
        assert entered.wait(5)
        with browse_node._hmb_catalog_state_commit():
            changed = picker._activate_picker_workspace_projection(browse_node._picker_state(), browse_shots[0])
            changed["video_tools_by_shot"][browse_shots[3]]["active_tool"] = "crop"
            changed["video_tools_by_shot"][browse_shots[3]]["crop"].update(input=str(paths[2]), source_uid="independent-crop")
            browse_node._write_state(changed)
        release.set()
        thread.join(10)
    state = browse_node._picker_state()
    assert state["active_picker_shot_uuid"] == browse_shots[0]
    assert len(state["video_tools_by_shot"][browse_shots[3]]["external_sources"]) == 1
    assert state["video_tools_by_shot"][browse_shots[3]]["active_tool"] == "crop"
    assert state["video_tools_by_shot"][browse_shots[3]]["concatenate"]["inputs"] == [str(paths[0])]
    assert state["video_tools_by_shot"][browse_shots[3]]["crop"]["input"] == str(paths[2])
    assert not state["video_tools_by_shot"][browse_shots[0]]["external_sources"]

    entered, release = threading.Event(), threading.Event()
    with patch.object(media, "probe_video", side_effect=slow_probe):
        thread = threading.Thread(target=send, args=(browse_node, "browse_sources", {"tool": "crop", "paths": [str(paths[1])]}, browse_shots[3]))
        thread.start()
        assert entered.wait(5)
        with browse_node._hmb_catalog_state_commit():
            changed = browse_node._picker_state()
            changed["picker_shots"] = [r for r in changed["picker_shots"] if r["workspace_uuid"] != browse_shots[3]]
            changed["video_tools_by_shot"].pop(browse_shots[3], None)
            browse_node._write_state(changed)
        release.set()
        thread.join(10)
    assert browse_shots[3] not in browse_node._picker_state()["video_tools_by_shot"]

    # Crop browsing must not overwrite a later drop/clear, including a return
    # to the original empty input. Exercise the real before/after widget route.
    def crop_widget_update(node, update):
        value = node._picker_state()
        tools = value["video_tools_by_shot"][value["active_picker_shot_uuid"]]
        update(tools)
        tools["revision"] += 1
        value["state_writer"] = "widget"
        parameter = picker._get_parameter_obj(node, picker.WIDGET_STATE_PARAMETER)
        prepared = node.before_value_set(parameter, value)
        node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, prepared, skip_before_value_set=True, emit_change=False)
        node.after_value_set(parameter, prepared)

    for scenario in ("replace", "clear", "empty-roundtrip", "other-tool-output", "newer-browse"):
        guarded, guarded_shots = make_node()
        guarded._sync_outputs_from_state = lambda *_args, **_kwargs: ""
        state = guarded._picker_state()
        if scenario != "empty-roundtrip":
            state["video_tools_by_shot"][guarded_shots[3]]["crop"].update(input=str(paths[0]), source_uid="initial-crop")
        guarded._write_state(state)
        entered, release = threading.Event(), threading.Event()
        def delayed_crop_probe(path):
            if Path(path) == paths[1]:
                entered.set()
                assert release.wait(10)
            return actual_probe(path)
        with patch.object(media, "probe_video", side_effect=delayed_crop_probe):
            pending = threading.Thread(target=send, args=(guarded, "browse_sources", {"tool": "crop", "paths": [str(paths[1])]}),
                                       kwargs={"action_id": "older-crop-browse"})
            pending.start()
            assert entered.wait(5)
            if scenario in ("replace", "empty-roundtrip"):
                crop_widget_update(guarded, lambda tools: tools["crop"].update(input=str(paths[2]), source_uid="newer-drop"))
            if scenario in ("clear", "empty-roundtrip"):
                crop_widget_update(guarded, lambda tools: tools["crop"].update(input="", source_uid=""))
            if scenario == "other-tool-output":
                def other_tool_edit(tools):
                    tools["active_tool"] = "concatenate"
                    tools["concatenate"]["inputs"].append(str(paths[2]))
                    tools["concatenate"]["input_uids"].append("independent-concat")
                    tools["crop"].update(output_path=str(folder / "newer-output.mp4"), manual_output_enabled=True)
                crop_widget_update(guarded, other_tool_edit)
            if scenario == "newer-browse":
                send(guarded, "browse_sources", {"tool": "crop", "paths": [str(paths[2])]}, action_id="newer-crop-browse")
            release.set()
            pending.join(10)
            assert not pending.is_alive()
        tools = guarded._picker_state()["video_tools_by_shot"][guarded_shots[3]]
        if scenario in ("clear", "empty-roundtrip"):
            assert not tools["crop"]["input"], scenario
        elif scenario == "other-tool-output":
            assert tools["crop"]["input"] == str(paths[1]), tools
            assert tools["crop"]["output_path"] == str(folder / "newer-output.mp4")
            assert tools["crop"]["manual_output_enabled"] is True
            assert tools["active_tool"] == "concatenate"
            assert tools["concatenate"]["input_uids"] == ["independent-concat"]
        else:
            assert tools["crop"]["input"] == str(paths[2]), scenario

    # A running edit owns an immutable FFmpeg input snapshot. Removing its
    # source card only edits future queues, not the original file/current job.
    running, running_shots = make_node()
    state = add(running._picker_state(), paths[0], "running-source", running_shots[3])
    node_entry = state["video_tools_by_shot"][running_shots[3]]
    node_entry["concatenate"].update(inputs=[str(paths[0]), str(paths[1])], input_uids=["running-source", ""])
    running._write_state(state)
    entered, release = threading.Event(), threading.Event()
    class FrozenService:
        def cancel(self):
            raise AssertionError("Catalog deletion cancelled an independent media job")
        def concatenate(self, settings, cancel_event=None):
            entered.set()
            assert release.wait(10)
            assert settings["inputs"] == [str(paths[0]), str(paths[1])]
            assert not cancel_event.is_set()
            return {"path": str(folder / "shot4.mp4"), "width": 96, "height": 64, "duration": 1.5}
    with patch.object(media, "VideoMediaService", FrozenService):
        send(running, "concatenate", {"manual_output_enabled": True, "output_path": str(folder / "unused.mp4")}, wait=False)
        assert entered.wait(5)
        job = running._hmb_video_tools_job
        state = delete(running, "running-source", "remove-during-edit")
        assert state["video_delete_results"]["remove-during-edit"]["status"] == "removed"
        assert not job["cancel"].is_set()
        assert state["video_tools_by_shot"][running_shots[3]]["concatenate"]["inputs"] == [str(paths[1])]
        release.set()
        job["thread"].join(10)
    assert running._picker_state()["video_tools_status"]["status"] == "succeeded"
    running._hmb_video_removal_sync_thread.join(10)

    # Duplicate-source staging is not proof the card still exists at commit.
    importing, import_shots = make_node()
    state = add(importing._picker_state(), paths[0], "old-import", import_shots[3])
    importing._write_state(state)
    entered, release = threading.Event(), threading.Event()
    def staged_import(state, source_path, *, picker_shot_uuid, **_kwargs):
        entered.set()
        assert release.wait(10)
        return add(state, Path(source_path), "new-import", picker_shot_uuid)
    with patch.object(importing, "_import_video_asset", side_effect=staged_import), patch.object(importing, "_sync_outputs_from_state", return_value=""):
        thread = threading.Thread(target=importing._commit_video_import_sources,
            args=([{"source_path": str(paths[0])}, {"source_path": str(paths[1])}],),
            kwargs={"captured_picker_shot_uuid": import_shots[3], "action_id": "import-race"})
        thread.start()
        assert entered.wait(5)
        delete(importing, "old-import", "delete-during-import")
        release.set()
        thread.join(10)
        importing._hmb_video_removal_sync_thread.join(10)
    state = importing._picker_state()
    assert [item["video_uid"] for item in state["videos"]] == ["new-import"]
    assert not state["video_tools_by_shot"][import_shots[3]]["concatenate"]["inputs"]
    assert not state["video_tools_by_shot"][import_shots[3]]["crop"]["input"]
    serialized = json.dumps(state)
    assert "no deleted card was restored" in serialized
    assert "existing Shot card was reused" not in serialized
    assert [p.read_bytes() for p in paths] == original

print("Video Tools source lifecycle: all-Shot real concat, external real concat/crop, manual/automatic destinations, UID tombstones, stale echoes and non-blocking coalesced deletion passed.")
