"""Exact-card source recovery, first-input destinations and custom Run snapshots.

Media operations use real FFmpeg. Desktop publication/native UI are isolated;
the macro branch substitutes only the active-project File boundary.
"""
from __future__ import annotations

import copy
import json
import shutil
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


def send(node, operation, settings):
    state = node._picker_state()
    uid = state["active_picker_shot_uuid"]
    node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "video_tools", "action_id": f"run-{len(node._hmb_processed_action_ids)}",
        "payload": {"op": operation, "picker_shot_uuid": uid, "settings": settings}})
    job = node._hmb_video_tools_job
    if job:
        job["thread"].join(20)
        assert not job["thread"].is_alive()
    return node._picker_state()


with patch.object(picker, "_request_parameter_value", return_value=False), \
     patch.object(picker, "_external_media_url", side_effect=lambda path: Path(path).as_uri()), \
     patch.object(picker, "_video_asset_thumbnail_url", return_value=("", "")), \
     tempfile.TemporaryDirectory(prefix="hmb-picker-destinations-") as temporary:
    # Match the canonical paths returned by the media service on Windows CI.
    folder = Path(temporary).resolve()
    source_dirs = [folder / "first imported", folder / "other shot"]
    project = folder / "project copies"
    custom = folder / "custom output"
    for directory in [*source_dirs, project, custom]:
        directory.mkdir()
    originals, copies = [], []
    for index, directory in enumerate(source_dirs):
        original = directory / f"source-{index}.mp4"
        subprocess.run([media._find_ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
            f"color=c={'red' if index == 0 else 'blue'}:s=96x64:r=24:d=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(original)], check=True, timeout=20)
        target = project / f"source-{index}_import_token.mp4"
        shutil.copy2(original, target)
        originals.append(original)
        copies.append(target)
    source_bytes = [path.read_bytes() for path in originals]
    node = picker.HMBVideoPickerLibrary(name="Picker destination regression")
    assert picker._get_parameter_obj(node, "VIDEO_TOOL_OUT") is None
    state = node._picker_state()
    workspace = state["active_picker_shot_uuid"]
    for index in range(2):
        state = picker._append_video_asset(state, {
            "video_uid": f"source-{index}", "video_path": str(copies[index]),
            "project_video_path": f"{{inputs}}/source-{index}_import_token.mp4",
            "import_source_path": str(originals[index]), "label": f"Card {index}",
            "generation_role": "imported", "markers": []}, picker_shot_uuid=workspace)
    state["video_tools_by_shot"][workspace].update(active_tool="concatenate", panel_height=567)
    node._write_state(state)
    assert picker._parse_state(json.dumps(node._picker_state()))["video_tools_by_shot"][workspace]["panel_height"] == 567
    assert media.normalize_picker_tools_state({"panel_height": 10000})["panel_height"] == 900
    assert media.normalize_picker_tools_state({"panel_height": -1})["panel_height"] == 160

    # Old drafts may contain cwd-prefixed macros. Exact UID aliases recover the
    # known file, never a same-name directory scan, even without an engine.
    bad = [str(folder / "appdata" / "Griptape Nodes" / "tmp" / "{inputs}" / f"source-{index}_import_token.mp4") for index in range(2)]
    concat = {**media.default_picker_tools_state()["concatenate"], "inputs": bad,
              "input_uids": ["source-0", "source-1"], "manual_output_enabled": True,
              "output_path": str(custom / "manual.mp4")}
    assert node._picker_state()["video_tools_by_shot"][workspace]["concatenate"]["manual_output_enabled"] is False
    completed = send(node, "concatenate", concat)
    assert completed["video_tools_status"]["status"] == "succeeded", completed["video_tools_status"]
    assert Path(completed["video_tools_output"]) == custom / "manual.mp4"
    assert abs(media.probe_video(completed["video_tools_output"])["duration"] - 1.0) < .1

    # Unchecked remembered custom destinations never override the first current
    # card's original import directory; reordering changes that directory.
    remembered = custom / "unchecked.mp4"
    for order in ([0, 1], [1, 0]):
        settings = {**concat, "inputs": [bad[index] for index in order],
                    "input_uids": [f"source-{index}" for index in order],
                    "manual_output_enabled": False, "output_path": str(remembered)}
        completed = send(node, "concatenate", settings)
        assert completed["video_tools_status"]["status"] == "succeeded", completed["video_tools_status"]
        assert Path(completed["video_tools_output"]).parent == source_dirs[order[0]]
    assert not remembered.exists()
    # The asynchronous directory hint exposes its exact source context so an
    # optimistic UI reorder cannot present a previous card's resolved folder.
    state = node._picker_state()
    state["video_tools_by_shot"][workspace]["revision"] += 1
    state["video_tools_by_shot"][workspace]["concatenate"].update(concat)
    with patch.object(node, "_schedule_action_worker", return_value=None):
        node._write_state(state)
    captured = picker._picker_tools_source_snapshots(state, "concatenate", concat)[0]
    node._refresh_video_tools_output_directory(node._hmb_video_tools_directory_context, captured)
    hinted = node._picker_state()
    assert hinted["video_tools_default_output_directory"] == str(source_dirs[0])
    assert hinted["video_tools_default_output_context"] == {
        "picker_shot_uuid": workspace, "tool": "concatenate",
        "source_uid": "source-0", "reference": bad[0]}
    crop = {**media.default_picker_tools_state()["crop"], "input": bad[1], "source_uid": "source-1",
            "crop_position": "Custom", "custom_width": 48, "custom_height": 32}
    completed = send(node, "crop", crop)
    assert completed["video_tools_status"]["status"] == "succeeded", completed["video_tools_status"]
    assert Path(completed["video_tools_output"]).parent == source_dirs[1]
    assert (media.probe_video(completed["video_tools_output"])["width"], media.probe_video(completed["video_tools_output"])["height"]) == (48, 32)

    # The result remains a local card/Shot flow after removing the public port.
    before = len(completed["videos"])
    added = send(node, "add_result", {})
    assert len(added["videos"]) == before + 1
    assert picker._get_parameter_obj(node, "VIDEO_TOOL_OUT") is None

    # A genuine project macro delegates exactly once to the real engine API
    # boundary; a stale prefixed tmp path does not become a filesystem literal.
    macro_calls = []
    class File:
        def __init__(self, reference):
            macro_calls.append(reference)
        def resolve(self):
            return copies[0]
    with patch.dict(picker.os.environ, {"APPDATA": str(folder / "appdata")}), \
         patch.dict(sys.modules, {"griptape_nodes.files.file": types.SimpleNamespace(File=File)}):
        resolved, origin = picker._picker_tools_resolve_source({"reference": bad[0]})
    assert resolved == copies[0] and origin == copies[0]
    assert macro_calls == ["{inputs}/source-0_import_token.mp4"]
    literal = project / "literal-{inputs}.mp4"
    shutil.copy2(copies[0], literal)
    with patch.dict(sys.modules, {"griptape_nodes.files.file": types.SimpleNamespace(File=File)}):
        assert picker._picker_tools_reference_path(str(literal)) == literal
        assert picker._picker_tools_reference_path(literal.as_uri()) == literal
        assert len(macro_calls) == 1, "A literal brace filename was treated as a macro"
        assert picker._picker_tools_reference_path("relative-prefix/{inputs}/movie.mp4") == copies[0]
        assert macro_calls[-1] == "relative-prefix/{inputs}/movie.mp4"
        unknown = str(folder / "unrelated prefix" / "{inputs}" / "movie.mp4")
        assert picker._picker_tools_reference_path(unknown) is None
        assert len(macro_calls) == 2, "An unrelated absolute prefix was discarded"

    # Source errors identify the source; valid sources with bad destinations
    # identify the output. Neither creates a partial destination.
    missing = str(folder / "actually missing.mp4")
    failed = send(node, "crop", {**crop, "input": missing, "source_uid": "not-in-catalog",
                  "manual_output_enabled": True, "output_path": str(custom / "must-not-exist.mp4")})
    assert failed["video_tools_status"]["status"] == "failed"
    assert "Source video is missing" in failed["video_tools_status"]["error"]
    assert not (custom / "must-not-exist.mp4").exists()
    failed = send(node, "crop", {**crop, "manual_output_enabled": True,
                  "output_path": str(folder / "absent output parent" / "crop.mp4")})
    assert "Output directory does not exist" in failed["video_tools_status"]["error"]
    failed = send(node, "crop", {**crop, "manual_output_enabled": True, "output_path": ""})
    assert "Enter an output file path" in failed["video_tools_status"]["error"]
    failed = send(node, "crop", {**crop, "manual_output_enabled": True, "output_path": str(originals[0])})
    assert "Output already exists" in failed["video_tools_status"]["error"]

    # A delayed directory hint from an old tool/source cannot replace current
    # context. Resolution is outside the catalog lock.
    entered, release = threading.Event(), threading.Event()
    original_resolver = picker._picker_tools_resolve_source
    def slow_source(source):
        entered.set()
        assert release.wait(5)
        return original_resolver(source)
    node._hmb_video_tools_directory_context = ("old",)
    with patch.object(picker, "_picker_tools_resolve_source", side_effect=slow_source):
        worker = threading.Thread(target=node._refresh_video_tools_output_directory,
            args=(("old",), {"reference": str(copies[0])}))
        worker.start()
        assert entered.wait(5)
        assert node._hmb_state_write_lock.acquire(timeout=1)
        node._hmb_state_write_lock.release()
        node._hmb_video_tools_directory_context = ("new",)
        node._hmb_video_tools_default_directory = str(source_dirs[1])
        release.set()
        worker.join(5)
    assert node._hmb_video_tools_default_directory == str(source_dirs[1])
    assert [path.read_bytes() for path in originals] == source_bytes

    # The ordinary Loader can import into a browsed source Shot while an edit
    # remains owned by its original destination Shot.
    browsing = node._picker_state()
    source_workspace = "00000000-0000-4000-8000-000000000002"
    second = copy.deepcopy(browsing["picker_shots"][0])
    second.update(workspace_uuid=source_workspace, number=2, name="Shot 2", bound_shot_uuid="",
                  video_asset_uids=[], selected_video_uids=[], preview_video_uid="")
    browsing["picker_shots"].append(second)
    browsing["video_tools_by_shot"][source_workspace] = {
        **media.default_picker_tools_state(), "external_sources": [
            {"source_uid": "source-browser-owned", "local_path": str(copies[0])}]}
    node._write_state(browsing)
    received = []
    def capture_import(sources, **kwargs):
        received.append((node._picker_state()["active_picker_shot_uuid"], kwargs["captured_picker_shot_uuid"]))
        return node._picker_state()
    with patch.object(node, "_commit_video_import_sources", side_effect=capture_import):
        node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
            "action": "import_video_assets", "action_id": "browse-source-import",
            "payload": {"picker_shot_uuid": source_workspace, "preserve_edit_workspace": True,
                        "sources": [{"source_path": str(copies[0])}]}})
    assert received == [(workspace, source_workspace)], (received, node._picker_state()["message"])
    assert node._picker_state()["active_picker_shot_uuid"] == workspace
    browsing = picker._append_video_asset(node._picker_state(), {
        "video_uid": "source-browser-delete", "video_path": str(copies[0]),
        "label": "source-browser-delete", "markers": []}, picker_shot_uuid=source_workspace)
    node._write_state(browsing)
    with patch.object(node, "_schedule_video_removal_output_sync", return_value=None):
        node._handle_picker_command({"runtime_instance_id": node._hmb_runtime_instance_id,
            "action": "delete_video_asset", "action_id": "source-browser-delete",
            "payload": {"picker_shot_uuid": source_workspace, "video_uid": "source-browser-delete",
                        "preserve_edit_workspace": True}})
    assert node._picker_state()["active_picker_shot_uuid"] == workspace
    assert all(item["video_uid"] != "source-browser-delete" for item in node._picker_state()["videos"])

print("Picker output paths: exact UID/macro recovery, real custom/default concat/crop, reordered source origins, missing-source/output distinction, protected inputs, stale directory isolation and retired public port passed.")
