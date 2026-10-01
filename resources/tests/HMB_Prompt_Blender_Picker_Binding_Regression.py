"""Blender Picker media must retain shot/order identity without inheriting Maya roles."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_prompt_blender_picker_binding_regression", ROOT / "HMBPromptLibrary.py"
)
assert SPEC is not None and SPEC.loader is not None
prompt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prompt
SPEC.loader.exec_module(prompt)


def payload(mode: str = "blender") -> dict:
    # Deliberately place both companions before their source mask. The Picker
    # selection order, not source role or filename, owns the @video slots.
    kinds = ["depth", "motion", "mask", "original"]
    rows = []
    metadata = []
    for slot, uid in enumerate(kinds, 1):
        row = {
            "video_uid": uid,
            "source_uid": uid,
            "selection_order": slot,
            "order_key": uid,
            "video_slot": slot,
            "selected": True,
            "video_path": f"C:/shot-04/{uid}.mp4",
        }
        if uid == "depth":
            row.update({
                "generation_role": "depth",
                "media_kind": "blender_depth_render",
                "video_role": "blender_depth_companion",
                "depth_profile": prompt.BLENDER_DEPTH_PROFILE,
                "bundle_run_id": "run-04",
                "source_video_slot": 3,
                "companion_of_video_slot": 3,
                "source_video_uid": "mask",
            })
        elif uid == "motion":
            row.update({
                "generation_role": "motion_guide",
                "media_kind": "blender_motion_guide",
                "video_role": "blender_motion_guide_companion",
                "motion_guide_profile": prompt.BLENDER_MOTION_GUIDE_PROFILE,
                "bundle_run_id": "run-04",
                "source_video_slot": 3,
                "companion_of_video_slot": 3,
                "source_video_uid": "mask",
            })
        elif uid == "mask":
            row.update({
                "generation_role": "mask",
                "media_kind": "blender_color_assignment_mask",
                "video_role": "blender_color_assignment_mask",
                "bundle_run_id": "run-04",
            })
        else:
            row.update({
                "generation_role": "original",
                "media_kind": "blender_original_render",
                "video_role": "blender_original_render",
            })
        rows.append(row)
        metadata.append({
            "video_uid": uid,
            "source_uid": uid,
            "video_slot": slot,
            "selection_order": slot,
            "order_key": uid,
            "fps": 24,
            "start_frame": 1,
            "end_frame": 24,
            "frame_count": 24,
            "duration_seconds": 1,
            "timebase": "24/1",
            "width": 1280,
            "height": 720,
            "valid": True,
            "conflict": False,
        })
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": mode,
        "scene_engine": "blender" if mode == "blender" else "maya",
        "scene_path": "C:/shot-04/scene.blend",
        "media_ready": True,
        "selection_id": "shot-04-selection",
        "selected_video_count": 4,
        "active_slot_count": 4,
        "videos": rows,
        "frame_metadata": metadata,
        "markers": [],
    }


def apply(data: dict) -> dict:
    return prompt._apply_picker_payload(
        prompt._default_widget_state(), data, connected=True
    )


def job(state: dict) -> dict:
    package = prompt._build_data_only_prompt_package(state)
    lines = package.splitlines()
    assert lines[0] == "HMB_GP_Production"
    return json.loads(lines[lines.index("HMB JOB DATA (JSON):") + 1])


blender = apply(payload())
videos = blender["videos"][:4]
assert [item["video_uid"] for item in videos] == ["depth", "motion", "mask", "original"]
assert [item["selection_order"] for item in videos] == [1, 2, 3, 4]
assert [item["video_main_type"] for item in videos] == [
    "Blender Preview / Render"
] * 4
assert [item["video_sub_type"] for item in videos] == [
    "Depth", "Motion Guide", "Mask", "Original Preview"
]
assert videos[0]["picker_companion_validated"] is True
assert videos[1]["picker_companion_validated"] is True
assert videos[0]["picker_companion_source_uid"] == "mask"
assert videos[1]["picker_companion_source_uid"] == "mask"
assert videos[0]["picker_companion_source_slot"] == 3
assert videos[1]["picker_companion_source_slot"] == 3
assert [item["video_uid"] for item in blender["picker"]["frame_metadata"]] == [
    "depth", "motion", "mask", "original"
]
blender_job = job(blender)
assert [row["video"] for row in blender_job["videos"][:4]] == [
    "@video1", "@video2", "@video3", "@video4"
]
assert [row["video_main_type"] for row in blender_job["videos"][:4]] == [
    "Blender Preview / Render"
] * 4
assert blender_job["videos"][0]["companion"]["source_uid"] == "mask"
assert blender_job["videos"][1]["companion"]["source_uid"] == "mask"
assert "Maya Preview / Playblast" not in json.dumps(blender_job)

spoofed_face = {
    "profile": prompt.BLENDER_MOTION_GUIDE_PROFILE,
    "semantic_face": True,
    "target_count": 7,
    "channel_count": 21,
    "driver_count": 8,
    "landmark_count": 32,
    "rasterized_sample_count": 16,
    "hidden_or_occluded_sample_count": 4,
    "semantic_groups": ["brow", "eyelid", "mouth", "jaw"],
    "final_blendshape_values_in_sidecar": True,
}
blender["videos"][1]["picker_motion_guide_summary"] = spoofed_face
normalized_blender = prompt._normalize_state(blender)
blender_summary = normalized_blender["videos"][1]["picker_motion_guide_summary"]
assert blender_summary["profile"] == prompt.BLENDER_MOTION_GUIDE_PROFILE
assert blender_summary["semantic_face"] is False
assert blender_summary["semantic_groups"] == []
assert blender_summary["final_blendshape_values_in_sidecar"] is False
for face_count in (
    "target_count", "channel_count", "driver_count", "landmark_count",
    "rasterized_sample_count", "hidden_or_occluded_sample_count",
):
    assert blender_summary[face_count] == 0

# Marker Asset ID still binds to the image row at its selected Mask slot.
image_state = prompt._default_widget_state()
image_state["images"][0].update({
    "present": True,
    "label": "Hero",
    "asset_id": "Hero",
    "image_main_type": "Character",
    "image_sub_type": "Full Appearance",
    "source_type": "Character Appearance",
    "owner": "Hero",
})
marked_payload = payload()
marked_payload["markers"] = [{
    "asset_id": "Hero", "subject_root": "Hero", "color": "Red",
    "video_slot": 3, "picker_order": 1,
}]
marked = prompt._apply_picker_payload(image_state, marked_payload, connected=True)
assert marked["images"][0]["color_picks"][0] == "Red"
assert marked["images"][0]["binding_video_slots"][0] == 3

# A Blender Depth/Motion declaration with Maya profile is not granted
# generated-companion authority, even if the bundle ID and source align.
wrong_profile = payload()
wrong_profile["videos"][0]["depth_profile"] = prompt.PICKER_DEPTH_PROFILE
wrong_profile["videos"][1]["motion_guide_profile"] = prompt.PICKER_MOTION_GUIDE_PROFILE
rejected = apply(wrong_profile)
assert rejected["videos"][0]["picker_companion_validated"] is False
assert rejected["videos"][1]["picker_companion_validated"] is False
assert rejected["videos"][0]["video_main_type"] != "Maya Preview / Playblast"
assert rejected["videos"][1]["video_main_type"] != "Maya Preview / Playblast"

# A self-contained companion uses explicit source slot zero, never silently
# links to whichever video happens to be first in the current Shot.
standalone_payload = payload()
for row in standalone_payload["videos"][:2]:
    row["source_video_slot"] = 0
    row["companion_of_video_slot"] = 0
    row.pop("source_video_uid", None)
standalone = apply(standalone_payload)
assert standalone["videos"][0]["picker_companion_validated"] is True
assert standalone["videos"][1]["picker_companion_validated"] is True
assert standalone["videos"][0]["picker_companion_source_slot"] == 0
assert standalone["videos"][1]["picker_companion_source_slot"] == 0

# The linked source must be a true Blender mask, not a Maya mask in the same
# numbered slot or a Blender original render with a forged bundle ID.
foreign_source = payload()
foreign_source["videos"][2]["media_kind"] = "maya_color_assignment_mask"
foreign_source["videos"][2]["video_role"] = "maya_color_assignment_mask"
foreign = apply(foreign_source)
assert foreign["videos"][0]["picker_companion_validated"] is False
assert foreign["videos"][1]["picker_companion_validated"] is False

not_a_mask = payload()
not_a_mask["videos"][2]["media_kind"] = "blender_original_render"
not_a_mask["videos"][2]["video_role"] = "blender_original_render"
not_mask = apply(not_a_mask)
assert not_mask["videos"][0]["picker_companion_validated"] is False
assert not_mask["videos"][1]["picker_companion_validated"] is False

invalid_pair = payload()
invalid_pair["videos"][3]["video_role"] = "maya_original_playblast"
invalid = apply(invalid_pair)
assert all(row["video_uid"] != "original" for row in invalid["videos"])
assert any("exact Blender media kind/role" in error for error in invalid["picker"]["contract_errors"])

# A machine-signed Maya selection continues to classify as Maya.
maya = payload(mode="maya")
for row in maya["videos"]:
    row["media_kind"] = row["media_kind"].replace("blender_", "maya_")
    row["video_role"] = row["video_role"].replace("blender_", "maya_")
maya["videos"][0]["media_kind"] = "maya_depth_playblast"
maya["videos"][0]["depth_profile"] = prompt.PICKER_DEPTH_PROFILE
maya["videos"][1]["motion_guide_profile"] = prompt.PICKER_MOTION_GUIDE_PROFILE
maya_state = apply(maya)
assert maya_state["videos"][0]["video_main_type"] == "Maya Preview / Playblast"
assert maya_state["videos"][0]["picker_companion_validated"] is True
assert maya_state["videos"][1]["picker_companion_validated"] is True

print("HMB Prompt Blender Picker binding regression: PASS")
