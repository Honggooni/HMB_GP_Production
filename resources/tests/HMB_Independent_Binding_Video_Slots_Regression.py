from __future__ import annotations

import copy
import importlib.util
import json
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
agent = load("HMBAgentLibrary")


def prompt_json_section(payload: str, header: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert header in lines
    return json.loads(lines[lines.index(header) + 1])


def active_video(slot: int, label: str, source_type: str, control_role: str):
    item = prompt._default_video_item(slot)
    item.update(
        {
            "present": True,
            "label": label,
            "source_type": source_type,
            "control_role": control_role,
            "video_main_type": (
                "Maya Preview / Playblast"
                if source_type == "Maya Preview / Playblast"
                else "Motion Reference"
            ),
            "video_sub_type": (
                "Original Preview"
                if source_type == "Maya Preview / Playblast"
                else "Local Motion"
            ),
            "manual": True,
        }
    )
    return item


# One image may bind independent Color Pick rows to different videos. Repeated
# normalization preserves every authored scope/custom scope and slot; the
# image-level Main/Sub pair does not rewrite those relationship fields.
state = prompt._default_widget_state()
state["images"] = [prompt._default_image_item(1)]
state["images"][0].update(
    {
        "present": True,
        "label": "Hero",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "source_type": "Character Appearance",
        "owner": "Hero",
        "binding_scopes": [
            "Full body / full appearance",
            "Head / face only",
        ],
        "binding_custom_scopes": ["", ""],
        "binding_video_slots": [1, 3],
        "marker_video": 1,
        "color_picks": ["Red", "Green"],
    }
)
state["videos"] = [
    active_video(
        1,
        "primary",
        "Maya Preview / Playblast",
        "Primary Unified Shot Control",
    ),
    prompt._default_video_item(2),
    active_video(3, "head-guide", "Motion Reference", "Context Only"),
]

normalized = prompt._normalize_state(state)
image = normalized["images"][0]
assert image["binding_video_slots"] == [1, 3]
assert image["marker_video"] == 1
assert image["binding_scopes"] == [
    "Full body / full appearance",
    "Head / face only",
]
assert prompt._normalize_state(copy.deepcopy(normalized)) == normalized

custom_scope_image = prompt._default_image_item(1)
custom_scope_image.update(
    {
        "image_main_type": "Custom / Context",
        "image_sub_type": "Custom",
        "custom_source_type": "Hero custom binding",
        "color_picks": ["Red", "Green"],
        "binding_scopes": ["Custom scope", "Head / face only"],
        "binding_custom_scopes": ["Hero silhouette", "Face detail"],
        "binding_video_slots": [1, 3],
    }
)
prompt._normalize_image_binding_fields(custom_scope_image)
assert custom_scope_image["binding_scopes"] == ["Custom scope", "Head / face only"]
assert custom_scope_image["binding_custom_scopes"] == [
    "Hero silhouette",
    "Face detail",
]

legacy_owner_state = prompt._default_widget_state()
legacy_owner_state["images"] = [
    {
        "slot": 1,
        "present": True,
        "label": "Hero",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "source_type": "Character Appearance",
        "owner": "",
        "color_picks": ["Red", "Green"],
        "binding_scopes": [
            "Full body / full appearance",
            "Handheld prop",
        ],
    }
]
legacy_owner_image = prompt._normalize_state(legacy_owner_state)["images"][0]
assert legacy_owner_image["binding_scopes"] == [
    "Full body / full appearance",
    "Handheld prop",
]
assert legacy_owner_image["owner"] == ""

entries = prompt._image_binding_entries(image)
assert [
    (entry["marker_video"], entry["color"], entry["scope"])
    for entry in entries
] == [
    (1, "Red", "Full body / full appearance"),
    (3, "Green", "Head / face only"),
]

compiled = prompt._build_data_only_prompt_package(normalized)
compiled_job = prompt_json_section(compiled, "HMB JOB DATA (JSON):")
assert compiled_job["images"][0]["bindings"] == [
    {
        "video": "@video1",
        "marker_color": "Red",
        "target_scope": "Full body / full appearance",
    },
    {
        "video": "@video3",
        "marker_color": "Green",
        "target_scope": "Head / face only",
    },
]
assert compiled_job["images"][0]["image_main_type"] == "Character"
assert compiled_job["images"][0]["image_sub_type"] == "Full Appearance"


# The selected Color Pick index owns the Range address. Index 1 must resolve to
# binding_video_slots[1] (@video3), not to the compatibility marker_video value.
range_state = copy.deepcopy(normalized)
range_image = range_state["images"][0]
range_image["frame_range_intent"] = {
    "version": 1,
    "enabled": True,
    "start_frame": 1,
    "end_frame": 24,
    "ranges": [{"start": 5, "end": 12}],
    "selected_index": 0,
}
range_image["frame_range_enabled"] = True
range_image["frame_range_color_index"] = 1
range_image["frame_range_bindings"] = {
    "@video3::Green": {
        "video_slot": "@video3",
        "color_pick": "Green",
        "origin": "manual",
        "ranges": [{"start": 5, "end": 12}],
    }
}
range_state["picker"] = {
    "enabled": True,
    "awaiting_data": False,
    "suppressed": False,
    "run_id": "independent-binding-video-range",
    "scene": "C:/shots/independent_binding.mb",
    "video_path": "",
    "camera": "|shotCam",
    "markers": [],
    "matched_images": 0,
    "frame_metadata": [
        {
            "video_slot": "@video3",
            "fps": 24,
            "start_frame": 1,
            "end_frame": 24,
            "frame_count": 24,
            "duration_seconds": 1,
            "timebase": "24/1",
            "available_color_picks": ["Green"],
            "origin": "maya",
            "conflict": False,
            "valid": True,
            "warnings": [],
        }
    ],
}
range_state = prompt._normalize_state(range_state)
range_image = range_state["images"][0]
current_binding = prompt._current_frame_range_binding(range_image)
assert current_binding is not None
assert current_binding["video_slot"] == "@video3"
assert current_binding["color_pick"] == "Green"
assert current_binding["ranges"] == [{"start": 5, "end": 12}]

range_compiled = prompt._build_data_only_prompt_package(range_state)
assert prompt_json_section(
    range_compiled,
    "HMB JOB DATA (JSON):",
)["frame_ranges"] == [{
    "image": "@image1",
    "video": "@video3",
    "marker_color": "Green",
    "enabled": True,
    "origin": "manual",
    "domain": {"start_frame": 1, "end_frame": 24},
    "segments": [{"start_frame": 5, "end_frame": 12}],
}]


# Deactivating @video3 makes its binding dormant without deleting user intent.
# The @video1 binding, shared scope, and optional frame instruction remain intact
# so the independent @video3 source can return later.
inactive_state = copy.deepcopy(normalized)
inactive_state["images"][0]["frame_range_intent"] = {
    "version": 1,
    "enabled": True,
    "start_frame": 1,
    "end_frame": 24,
    "ranges": [{"start": 5, "end": 12}],
    "selected_index": 0,
}
inactive_state["images"][0]["frame_range_enabled"] = True
inactive_state["images"][0]["frame_range_color_index"] = 1
inactive_state["images"][0]["frame_range_bindings"] = {
    "@video3::Green": {
        "video_slot": "@video3",
        "color_pick": "Green",
        "origin": "manual",
        "ranges": [{"start": 5, "end": 12}],
    }
}
inactive_state["videos"][2].update(
    {
        "present": False,
        "label": "",
        "source_type": "Ignore / Unused",
        "control_role": "",
    }
)
inactive = prompt._normalize_state(inactive_state)["images"][0]
assert inactive["binding_video_slots"] == [1, 3]
assert inactive["color_picks"] == ["Red", "Green"]
assert "@video3::Green" in inactive["frame_range_bindings"]
assert inactive["frame_range_color_index"] == 1
assert inactive["binding_scopes"] == [
    "Full body / full appearance",
    "Head / face only",
]
assert inactive["marker_video"] == 1


# Picker re-sync replaces only its exact automatic binding and preserves a
# user-added binding with its independent video number and shared image subtype.
def picker_payload(color: str, run_id: str):
    return {
        "mode": "maya",
        "run_id": run_id,
        "active_slot_count": 3,
        "videos": [
            {"video_slot": 1, "video_path": "C:/shots/primary.mp4"},
            {"video_slot": 2, "video_path": "C:/shots/mask.mp4"},
            {"video_slot": 3, "video_path": "C:/shots/detail.mp4"},
        ],
        "markers": [
            {
                "asset_id": "Hero",
                "color": color,
                "video_slot": 2,
                "picker_order": 1,
            }
        ],
    }


picker_state = prompt._default_widget_state()
picker_state["images"][0].update(
    {
        "present": True,
        "label": "Hero",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "source_type": "Character Appearance",
        "owner": "Hero",
        "binding_scopes": ["Full body / full appearance"],
        "binding_custom_scopes": [""],
    }
)
picker_state = prompt._apply_picker_payload(
    picker_state,
    picker_payload("Red", "independent-auto-1"),
    connected=True,
)
picker_image = picker_state["images"][0]
picker_image["color_picks"] = ["Red", "Yellow"]
picker_image["binding_video_slots"] = [2, 3]
picker_image["binding_scopes"] = [
    "Full body / full appearance",
    "Head / face only",
]
picker_image["binding_custom_scopes"] = ["", ""]
picker_image["marker_video"] = 2

picker_state = prompt._apply_picker_payload(
    picker_state,
    picker_payload("Green", "independent-auto-2"),
    connected=True,
)
picker_image = picker_state["images"][0]
assert picker_image["color_picks"] == ["Green", "Yellow"]
assert picker_image["binding_video_slots"] == [2, 3]
assert picker_image["binding_scopes"] == [
    "Full body / full appearance",
    "Head / face only",
]
assert picker_image["picker_auto_color"] == "Green"
assert picker_image["picker_auto_video"] == 2


print("HMB independent binding_video_slots Python regression: PASS")
