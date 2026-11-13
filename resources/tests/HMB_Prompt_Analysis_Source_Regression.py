"""Verify the exact-shot analysis catalog and ignore retired widget commands."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from HMBPromptLibrary import (
    HMBPromptLibrary, WIDGET_PARAMETER_NAME, _build_data_only_prompt_package,
    _build_user_readable_prompt_package, _normalize_state,
    _normal_prompt_visual_rows, _public_job_data_contract,
    _build_fx_timing_source_contract, _merge_analysis_generated_text,
)


CHANNEL = "11111111-1111-4111-8111-111111111111"
SHOT = "22222222-2222-4222-8222-000000000001"
OTHER = "22222222-2222-4222-8222-000000000002"
STATE = {
    "shot": {"channel_uuid": CHANNEL, "shot_uuid": SHOT, "selected_source_uids": ["i-1", "i-2", "i-ordinary"]},
    "images": [{"asset_source_uid": "i-1", "label": "Still one", "image_sub_type": "Analysis"},
        {"asset_source_uid": "i-2", "label": "Still two", "image_sub_type": "Analysis"},
        {"asset_source_uid": "i-ordinary", "label": "Ordinary still", "image_sub_type": "Color Mood"}],
    "videos": [{"video_uid": "v-1", "label": "Motion", "video_sub_type": "Analysis"},
        {"video_uid": "v-ordinary", "label": "Ordinary motion", "video_sub_type": "Local Motion"},
        {"video_uid": "v-unavailable", "label": "HTTP", "video_sub_type": "Analysis"}],
    "picker": {"ordered_video_uids": ["v-1", "v-ordinary", "v-unavailable"], "frame_metadata": [{"video_slot": "@video1", "duration_seconds": 7.5}]},
    "sound_sources": [
        {"instance_id": "sound-1", "audio_sub_type": "Analysis", "enabled": False},
        {"instance_id": "sound-2", "audio_sub_type": "Analysis", "enabled": False},
        {"instance_id": "sound-off", "audio_sub_type": "Ignore", "enabled": False},
        {"instance_id": "sound-ordinary", "audio_sub_type": "Apply", "enabled": True},
    ],
    "text": {"VIDEO_VFX": "Authored Prompt"},
}
IMAGE_PATHS = ["C:/fixture/reference.png", "data:image/png;base64,MTIz", "C:/fixture/ordinary.png"]
VIDEO_PATHS = ["C:/fixture/reference.mov", "C:/fixture/ordinary.mov", "https://host.invalid/reference.mov"]
SOUND = {"tracks": [
    {"channel_uuid": CHANNEL, "shot_uuid": shot_uuid, "instance_id": instance, "path": f"C:/fixture/{instance}.wav",
        "name": "Sound cue", "duration_seconds": 8, "in_seconds": 1.5, "out_seconds": 6, "enabled": enabled}
    for shot_uuid, instance, enabled in [(SHOT, "sound-1", False), (OTHER, "sound-2", False),
        (SHOT, "sound-off", False), (SHOT, "sound-ordinary", True)]
]}


def main() -> None:
    records = HMBPromptLibrary._hmb_project_analysis_sources(STATE, IMAGE_PATHS, VIDEO_PATHS, SOUND)
    assert [item["kind"] for item in records] == ["image", "image", "video", "audio"]
    assert records[2]["duration_seconds"] == 7.5
    assert (records[3]["start_seconds"], records[3]["end_seconds"]) == (1.5, 6)
    assert records[3]["selector"] == "sound-1"
    assert {item["selector"] for item in records} == {"i-1", "i-2", "v-1", "sound-1"}
    assert [item["shot_reference"] for item in records[:3]] == ["@image1", "@image2", "@video1"]
    upstream = HMBPromptLibrary._hmb_project_analysis_sources(
        STATE, IMAGE_PATHS, VIDEO_PATHS, SOUND, include_unmarked=True)
    by_selector = {item["selector"]: item for item in upstream}
    assert {"i-ordinary", "v-ordinary", "sound-ordinary"} <= by_selector.keys()
    assert not {"v-unavailable", "sound-2"}.intersection(by_selector)
    assert [by_selector[item["selector"]] for item in records] == records
    ordinary_state = _normalize_state({
        "images": [
            {"label": "analysis-image-only", "image_main_type": "Character",
             "image_sub_type": "Analysis", "owner": "Analysis Target"},
            {"label": "ordinary-image", "image_sub_type": "Color Mood"},
        ],
        "videos": [
            {"label": "analysis-video-only", "video_main_type": "Motion Reference",
             "video_sub_type": "Analysis", "control_role": "Camera"},
            {"label": "ordinary-video", "video_sub_type": "Local Motion"},
        ],
    })
    visible = _build_user_readable_prompt_package(ordinary_state)
    machine = _build_data_only_prompt_package(ordinary_state)
    assert "analysis-image-only" not in visible + machine
    assert "analysis-video-only" not in visible + machine
    assert "@image1" not in visible + machine
    assert "@video1" not in visible + machine
    assert "@image2" in visible + machine and "@video2" in visible + machine
    images, videos, excluded_slots = _normal_prompt_visual_rows(ordinary_state)
    assert excluded_slots == {1}
    authored_controls = [{"video": 1, "raw": "analysis video control"},
                         {"video": 2, "raw": "ordinary video control"}]
    job = _public_job_data_contract(ordinary_state, images, videos, authored_controls, excluded_slots)
    fx = _build_fx_timing_source_contract(ordinary_state, images, videos, authored_controls, excluded_slots)
    assert [item["image"] for item in job["images"]] == ["@image2"]
    assert [item["video"] for item in job["videos"]] == ["@video2"]
    assert [item["video"] for item in job["control_only_bindings"]] == ["@video2"]
    assert [item["video"] for item in fx["sources"]] == ["@video2"]
    assert [item["video"] for item in fx["control_bindings"]] == [2]
    excluded = HMBPromptLibrary._hmb_analysis_excluded_media(STATE, IMAGE_PATHS, VIDEO_PATHS)
    assert excluded == {"images": IMAGE_PATHS[:2], "videos": [VIDEO_PATHS[0], VIDEO_PATHS[2]]}
    assert HMBPromptLibrary._hmb_analysis_excluded_media(STATE,
        [*IMAGE_PATHS[:2], IMAGE_PATHS[0]], VIDEO_PATHS)["images"] == IMAGE_PATHS[1:2]
    if sys.platform == "win32":
        assert HMBPromptLibrary._hmb_analysis_excluded_media(STATE,
            [*IMAGE_PATHS[:2], "file:///C:/fixture/REFERENCE.png"], VIDEO_PATHS)["images"] == IMAGE_PATHS[1:2]

    reordered = copy.deepcopy(STATE)
    reordered["shot"]["selected_source_uids"].reverse()
    image_rows = HMBPromptLibrary._hmb_project_analysis_sources(reordered, IMAGE_PATHS[::-1], [], {})
    assert [row["source_id"] for row in image_rows] == [records[1]["source_id"], records[0]["source_id"]]

    node = object.__new__(HMBPromptLibrary)
    from threading import RLock
    node._hmb_sync_lock = RLock()
    node._hmb_prompt_selector_state = lambda: STATE
    def exact_document(*, channel_uuid, shot_uuid, _analysis_sources_only, _analysis_upstream=False):
        matching = _analysis_sources_only and channel_uuid == CHANNEL and shot_uuid == SHOT
        return {"analysis_sources": (upstream if _analysis_upstream else records) if matching else []}

    node._hmb_prompt_shot_document = exact_document
    public = node._hmb_analysis_sources_for(channel_uuid=CHANNEL, shot_uuid=SHOT)
    assert all(set(row).isdisjoint({"path", "selector", "visible_prompt", "machine_prompt"}) for row in public)
    source = node._hmb_analysis_reference_for(channel_uuid=CHANNEL, shot_uuid=SHOT, kind="image", source_id=records[0]["source_id"])
    assert source["path"] == IMAGE_PATHS[0]
    assert not node._hmb_analysis_reference_for(channel_uuid=CHANNEL, shot_uuid=OTHER, kind="image", source_id=records[0]["source_id"])
    assert not node._hmb_analysis_reference_for(channel_uuid=CHANNEL, shot_uuid=SHOT, kind="video", source_id=records[0]["source_id"])
    assert not node._hmb_analysis_reference_for(channel_uuid=CHANNEL, shot_uuid=SHOT, kind="image",
        source_id=by_selector["i-ordinary"]["source_id"])
    assert node._hmb_analysis_upstream_reference_for(channel_uuid=CHANNEL, shot_uuid=SHOT, kind="image",
        source_id=by_selector["i-ordinary"]["source_id"])["path"] == IMAGE_PATHS[-1]
    assert not node._hmb_analysis_upstream_reference_for(channel_uuid=CHANNEL, shot_uuid=OTHER, kind="image",
        source_id=by_selector["i-ordinary"]["source_id"])
    assert all(set(row).isdisjoint({"path", "selector"}) for row in
        node._hmb_analysis_upstream_sources_for(channel_uuid=CHANNEL, shot_uuid=SHOT))

    document = _normalize_state({"text": {"VIDEO_VFX": "Artist's note", "PRESERVED_TEXT": "  [Dialogue] Original  "}})
    assert _merge_analysis_generated_text(document, {"VIDEO_VFX": "First", "PRESERVED_TEXT": ""})
    assert document["text"]["VIDEO_VFX"] == "Artist's note\n\nFirst"
    assert document["text"]["PRESERVED_TEXT"] == "  [Dialogue] Original  "
    assert not _merge_analysis_generated_text(document, {"VIDEO_VFX": "First"})
    assert _merge_analysis_generated_text(document, {"VIDEO_VFX": "Replacement"})
    assert document["text"]["VIDEO_VFX"] == "Artist's note\n\nReplacement"
    document["text"]["VIDEO_VFX"] += " edited"
    assert not _merge_analysis_generated_text(document, {"VIDEO_VFX": "Next"})
    assert document["text"]["VIDEO_VFX"] == "Artist's note\n\nReplacement edited"

    restore_calls = []
    node._restore_accepted_widget_state = lambda: restore_calls.append(True)
    old_request = {"schema": "hmb-prompt-analysis-pick", "version": 1, "kind": "image",
        "channel_uuid": CHANNEL, "shot_uuid": SHOT, "selector": "i-1", "guidance": "Read the effect."}
    assert not hasattr(node, "_hmb_dispatch_analysis_pick")
    assert node.set_parameter_value(WIDGET_PARAMETER_NAME, json.dumps(old_request)) is None
    assert node.set_parameter_value(WIDGET_PARAMETER_NAME, old_request, initial_setup=True) is None
    assert node.after_value_set(SimpleNamespace(name=WIDGET_PARAMETER_NAME), old_request) is None
    assert restore_calls == [True]
    print("Prompt analysis catalog: PASS (exact upstream/downstream media, reorder, authored text, retired commands)")


if __name__ == "__main__":
    main()
