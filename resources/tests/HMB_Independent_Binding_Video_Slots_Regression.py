from __future__ import annotations

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
agent = load("HMBAgentLibrary")


def active_video(slot: int, label: str, source_type: str, control_role: str):
    item = prompt._default_video_item(slot)
    item.update(
        {
            "present": True,
            "label": label,
            "source_type": source_type,
            "control_role": control_role,
            "manual": True,
        }
    )
    return item


# One image may bind independent Color Pick rows to different videos, but Sub
# Type is image-level authority. Repeated normalization must preserve the slot
# array while collapsing legacy per-binding subtype overrides to the first one;
# marker_video remains only the backwards-compatible alias of the first binding.
state = prompt._default_widget_state()
state["images"] = [prompt._default_image_item(1)]
state["images"][0].update(
    {
        "present": True,
        "label": "Hero",
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
    "Full body / full appearance",
]
assert prompt._normalize_state(copy.deepcopy(normalized)) == normalized

custom_scope_image = prompt._default_image_item(1)
custom_scope_image.update(
    {
        "color_picks": ["Red", "Green"],
        "binding_scopes": ["Custom scope", "Head / face only"],
        "binding_custom_scopes": ["Hero silhouette", "Face detail"],
        "binding_video_slots": [1, 3],
    }
)
prompt._normalize_image_binding_fields(custom_scope_image)
assert custom_scope_image["binding_scopes"] == ["Custom scope", "Custom scope"]
assert custom_scope_image["binding_custom_scopes"] == [
    "Hero silhouette",
    "Hero silhouette",
]

legacy_owner_state = prompt._default_widget_state()
legacy_owner_state["images"] = [
    {
        "slot": 1,
        "present": True,
        "label": "Hero",
        "source_type": "Character Appearance",
        "owner": "",
        "color_picks": ["Red", "Green"],
        "binding_scopes": [
            "Full body / full appearance",
            "Handheld prop",
        ],
        "interaction_targets": ["Dog"],
    }
]
legacy_owner_image = prompt._normalize_state(legacy_owner_state)["images"][0]
assert legacy_owner_image["binding_scopes"] == [
    "Full body / full appearance",
    "Full body / full appearance",
]
assert legacy_owner_image["owner"] == ""

entries = prompt._image_binding_entries(image)
assert [
    (entry["marker_video"], entry["color"], entry["scope"])
    for entry in entries
] == [
    (1, "Red", "Full body / full appearance"),
    (3, "Green", "Full body / full appearance"),
]

compiled = prompt._build_prompt_package(normalized)
assert "Color Pick marker: @video1 / Red" in compiled
assert "Color Pick marker: @video3 / Green" in compiled
assert "SOURCE AUTHORITY CONFLICTS:" not in compiled
assert "Final prompt generation is blocked" not in compiled
assert "requires one validated Motion Guide" not in compiled
assert agent._is_hmb_prompt_library_payload(compiled)


# The selected Color Pick index owns the Range address. Index 1 must resolve to
# binding_video_slots[1] (@video3), not to the compatibility marker_video value.
range_state = copy.deepcopy(normalized)
range_image = range_state["images"][0]
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

validated_binding, metadata, errors = prompt._frame_range_binding_validation(
    range_state,
    range_image,
    {1, 3},
)
assert errors == []
assert validated_binding is not None
assert validated_binding["video_slot"] == "@video3"
assert metadata is not None
assert metadata["video_slot"] == "@video3"
range_compiled = prompt._build_prompt_package(range_state)
assert "FRAME RANGE BINDING:" not in range_compiled
assert "Color Pick marker: @video3 / Green" in range_compiled
assert "during Frames" not in range_compiled


# Deactivating @video3 makes its binding dormant without deleting user intent.
# The @video1 binding, shared scope, and optional frame instruction remain intact
# so the independent @video3 source can return later.
inactive_state = copy.deepcopy(normalized)
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
    "Full body / full appearance",
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
    "Full body / full appearance",
]
assert picker_image["picker_auto_color"] == "Green"
assert picker_image["picker_auto_video"] == 2


print("HMB independent binding_video_slots Python regression: PASS")
