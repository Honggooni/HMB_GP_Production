import copy
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt = load("HMBPromptLibrary")


def picker_payload(run_id: str, bundle_run_id: str):
    frame_metadata = []
    for slot in range(1, 4):
        frame_metadata.append(
            {
                "video_slot": slot,
                "fps": 24,
                "start_frame": 101,
                "end_frame": 124,
                "frame_count": 24,
                "duration_seconds": 1,
                "timebase": "24/1",
                "width": 1280,
                "height": 720,
                "available_color_picks": ["Red"] if slot == 1 else [],
                "valid": True,
                "conflict": False,
            }
        )
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "mode": "maya",
        "run_id": run_id,
        "active_slot_count": 3,
        "scene_path": "C:/shots/slot_local.mb",
        "camera": "|shotCam",
        "videos": [
            {
                "video_slot": 1,
                "video_path": "C:/shots/color.mp4",
                "bundle_run_id": bundle_run_id,
                "pair_run_id": bundle_run_id,
            },
            {
                "video_slot": 2,
                "video_path": "C:/shots/depth.mp4",
                "bundle_run_id": bundle_run_id,
                "pair_run_id": bundle_run_id,
                "source_video_slot": 1,
                "media_kind": "maya_depth_playblast",
                "video_role": "maya_depth_companion",
                "depth_profile": prompt.PICKER_DEPTH_PROFILE,
            },
            {
                "video_slot": 3,
                "video_path": "C:/shots/motion.mp4",
                "bundle_run_id": bundle_run_id,
                "source_video_slot": 1,
                "media_kind": "maya_motion_guide",
                "video_role": "maya_motion_guide_companion",
                "motion_guide_profile": "hmb_target_neutral_motion_guide_v5",
            },
        ],
        "markers": [
            {
                "asset_id": "Hero",
                "subject_root": "|Hero_GRP",
                "color": "Red",
                "video_slot": 1,
                "picker_order": 1,
            }
        ],
        "frame_metadata": frame_metadata,
    }


state = prompt._default_widget_state()
state["images"][0].update(
    {
        "present": True,
        "label": "Hero",
        "asset_id": "Hero",
        "source_type": "Character Appearance",
        "owner": "Hero",
    }
)
payload_a = picker_payload("slot-local-run-a", "slot-local-bundle-a")
applied = prompt._apply_picker_payload(state, payload_a, connected=True)

assert len(applied["videos"]) == 3
assert applied["videos"][1]["picker_auto_depth"]
assert applied["videos"][2]["picker_auto_motion_guide"]
assert len(applied["picker"]["markers"]) == 1
assert len(applied["picker"]["frame_metadata"]) == 3


# Ignoring @video1 is a slot-local user choice. Reapplying the still-connected
# Picker payload must not clear or disable @video2/@video3 and their provenance.
ignored = copy.deepcopy(applied)
ignored["videos"][0]["source_type"] = "Ignore / Unused"
ignored["picker"]["slot_suppressions"] = {"1": "slot-local-run-a"}
ignored = prompt._apply_picker_payload(ignored, payload_a, connected=True)

assert ignored["videos"][0]["source_type"] == "Ignore / Unused"
assert ignored["videos"][1]["picker_auto_depth"]
assert ignored["videos"][2]["picker_auto_motion_guide"]
assert len(ignored["picker"]["markers"]) == 1
assert len(ignored["picker"]["frame_metadata"]) == 3
assert ignored["picker"]["matched_images"] == 0
assert ignored["picker"]["run_id"] == "slot-local-run-a"
assert ignored["images"][0]["picker_auto_color"] == ""
assert ignored["images"][0]["picker_auto_video"] == 0
assert not any(ignored["images"][0]["color_picks"])
assert "suppressed" not in ignored["picker"]
assert "suppressed_run_id" not in ignored["picker"]


# X on the Depth row records only @video2. The same connected payload cannot
# immediately recreate it, while the Motion Guide and Picker metadata survive.
deleted_depth = copy.deepcopy(ignored)
deleted_depth["videos"][1] = prompt._default_video_item(2)
deleted_depth["videos"][1]["manual"] = True
deleted_depth["picker"]["slot_suppressions"]["2"] = "slot-local-run-a"
deleted_depth = prompt._apply_picker_payload(
    deleted_depth,
    payload_a,
    connected=True,
)

assert not prompt._is_active_video(deleted_depth["videos"][1])
assert deleted_depth["videos"][1]["picker_auto_depth"] == {}
assert deleted_depth["videos"][2]["picker_auto_motion_guide"]
assert len(deleted_depth["picker"]["markers"]) == 1
assert len(deleted_depth["picker"]["frame_metadata"]) == 3


# A genuinely new Picker run may populate a deleted slot again. Stale
# same-run tombstones are discarded automatically, while explicit Ignore
# remains a user-owned role until the user changes it.
payload_b = picker_payload("slot-local-run-b", "slot-local-bundle-b")
next_run = prompt._apply_picker_payload(
    deleted_depth,
    payload_b,
    connected=True,
)

assert next_run["videos"][0]["source_type"] == "Ignore / Unused"
assert next_run["videos"][1]["picker_auto_depth"]
assert next_run["videos"][2]["picker_auto_motion_guide"]
assert next_run["picker"]["slot_suppressions"] == {}


print("HMB Prompt Picker slot-local suppression regression: PASS")
