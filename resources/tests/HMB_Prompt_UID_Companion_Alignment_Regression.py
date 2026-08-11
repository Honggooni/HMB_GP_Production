from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_prompt_uid_companion_alignment_regression",
    ROOT / "HMBPromptLibrary.py",
)
assert SPEC is not None and SPEC.loader is not None
prompt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prompt
SPEC.loader.exec_module(prompt)


def frame_metadata(uid: str, slot: int) -> dict:
    return {
        "video_uid": uid,
        "source_uid": uid,
        "video_slot": slot,
        "selection_order": slot,
        "order_key": uid,
        "fps": 24,
        "start_frame": 101,
        "end_frame": 124,
        "frame_count": 24,
        "duration_seconds": 1,
        "timebase": "24/1",
        "width": 1280,
        "height": 720,
        "available_color_picks": [],
        "valid": True,
        "conflict": False,
    }


def picker_payload(
    order: list[str],
    *,
    standalone: bool = False,
    missing_source: bool = False,
) -> dict:
    bundle_id = "uid-companion-bundle"
    slot_by_uid = {uid: slot for slot, uid in enumerate(order, start=1)}
    videos = []
    for slot, uid in enumerate(order, start=1):
        row = {
            "video_uid": uid,
            "source_uid": uid,
            "selection_order": slot,
            "order_key": uid,
            "video_slot": slot,
            "selected": True,
            "video_path": f"C:/shots/{uid}.mp4",
        }
        if uid == "mask":
            row.update(
                {
                    "media_kind": "maya_color_assignment_mask",
                    "video_role": "maya_color_assignment_mask",
                    "pair_run_id": bundle_id,
                    "bundle_run_id": bundle_id,
                }
            )
        elif uid == "depth":
            source_slot = (
                0
                if standalone
                else -1
                if missing_source
                else slot_by_uid["mask"]
            )
            row.update(
                {
                    "media_kind": "maya_depth_playblast",
                    "video_role": "maya_depth_companion",
                    "depth_profile": prompt.PICKER_DEPTH_PROFILE,
                    "pair_run_id": bundle_id,
                    "bundle_run_id": bundle_id,
                    "source_video_slot": source_slot,
                    "companion_of_video_slot": source_slot,
                }
            )
            if not standalone:
                row["source_video_uid"] = "mask"
                row["companion_of_video_uid"] = "mask"
        videos.append(row)
    metadata = [
        frame_metadata(uid, slot)
        for slot, uid in enumerate(order, start=1)
    ]
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "media_ready": bool(videos),
        "selection_id": "selection-" + "-".join(order),
        "selected_video_count": len(videos),
        "max_selected_videos": 10,
        "active_slot_count": len(videos),
        "videos": videos,
        "markers": [],
        "frame_metadata": metadata,
    }


# Drag order: Depth is now @video1, while its declared Mask source is @video3.
reordered = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    picker_payload(["depth", "original", "mask"]),
    connected=True,
)
depth = reordered["videos"][0]
assert depth["video_uid"] == "depth"
assert depth["picker_companion_kind"] == "depth"
assert depth["picker_companion_source_uid"] == "mask"
assert depth["picker_companion_source_slot"] == 3
assert depth["picker_companion_validated"] is True
compiled = prompt._build_prompt_package(reordered)
assert "@video1 = depth" in compiled
assert "@video2 = original" in compiled
assert "@video3 = mask" in compiled
assert "Picker slot contract" not in compiled

# Stable UID wins over a stale serialized transient source slot.
uid_authoritative = copy.deepcopy(reordered)
uid_authoritative["videos"][0]["picker_companion_source_slot"] = 1
uid_authoritative_prompt = prompt._build_prompt_package(uid_authoritative)
assert uid_authoritative_prompt == compiled


# The compiled conflict path also names the declared source, never a positional
# primary fallback.
mismatch_contract = picker_payload(["depth", "original", "mask"])
mismatch_contract["frame_metadata"][0].update(
    {"end_frame": 112, "frame_count": 12, "duration_seconds": 0.5}
)
mismatched = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    mismatch_contract,
    connected=True,
)
mismatch_prompt = prompt._build_prompt_package(mismatched)
assert mismatch_prompt == compiled
assert "self-scoped alignment" not in mismatch_prompt


# Motion Guide uses the same UID/source resolution and may also occupy slot 1.
motion_contract = picker_payload(["depth", "original", "mask"])
motion_row = motion_contract["videos"][0]
motion_row["video_uid"] = "motion"
motion_row["source_uid"] = "motion"
motion_row["order_key"] = "motion"
motion_row["video_path"] = "C:/shots/motion.mp4"
motion_row["media_kind"] = "maya_motion_guide"
motion_row["video_role"] = "maya_motion_guide_companion"
motion_row["motion_guide_profile"] = prompt.PICKER_MOTION_GUIDE_PROFILE
motion_row.pop("depth_profile", None)
motion_contract["frame_metadata"][0].update(
    {"video_uid": "motion", "source_uid": "motion", "order_key": "motion"}
)
motion = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    motion_contract,
    connected=True,
)
motion_prompt = prompt._build_prompt_package(motion)
assert motion["videos"][0]["picker_companion_kind"] == "motion_guide"
assert motion["videos"][0]["picker_companion_source_slot"] == 3
assert "@video1 = motion" in motion_prompt
assert "Picker slot contract" not in motion_prompt


# A standalone Depth may itself be @video1 and requires no matched Mask.
standalone = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    picker_payload(["depth"], standalone=True),
    connected=True,
)
standalone_prompt = prompt._build_prompt_package(standalone)
assert standalone["videos"][0]["picker_companion_source_slot"] == 0
assert "@video1 = depth" in standalone_prompt
assert "Picker companion contract" not in standalone_prompt


# A deselected source is represented by -1 and cannot silently rebind to the
# video promoted into @video1.
missing = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    picker_payload(["depth"], missing_source=True),
    connected=True,
)
missing_prompt = prompt._build_prompt_package(missing)
assert missing["videos"][0]["picker_companion_source_slot"] == -1
assert missing["videos"][0]["picker_companion_source_uid"] == "mask"
assert "@video1 = depth" in missing_prompt
assert "source UID mask is not selected" not in missing_prompt


# Prompt settings follow the stable Depth UID while both source and companion
# receive new transient addresses on a later drag reorder.
reordered["videos"][0]["keep_out"] = "Preserve the authored Depth exclusion."
reordered_again = prompt._apply_picker_payload(
    reordered,
    picker_payload(["mask", "original", "depth"]),
    connected=True,
)
depth_after = next(
    item for item in reordered_again["videos"] if item["video_uid"] == "depth"
)
assert depth_after["slot"] == 3
assert depth_after["keep_out"] == "Preserve the authored Depth exclusion."
assert depth_after["picker_companion_source_uid"] == "mask"
assert depth_after["picker_companion_source_slot"] == 1
compiled_again = prompt._build_prompt_package(reordered_again)
assert "@video1 = mask" in compiled_again
assert "@video2 = original" in compiled_again
assert "@video3 = depth" in compiled_again
assert "Picker slot contract" not in compiled_again


print("HMB Prompt UID companion alignment regression: PASS")
