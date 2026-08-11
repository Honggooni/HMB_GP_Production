from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_prompt_no_loss_regression",
    ROOT / "HMBPromptLibrary.py",
)
assert SPEC is not None and SPEC.loader is not None
prompt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prompt)


def prompt_json_section(payload: str, header: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert len(lines) == 7
    return json.loads(lines[lines.index(header) + 1])


def fallback_texts(state):
    return [
        str(entry.get("text") or "")
        for entry in state.get("source_intent_fallbacks", [])
        if isinstance(entry, dict)
    ]


# Structured connectors do not have verified user-authored text provenance.
# Malformed/non-object values therefore cannot enter USER DESCRIPTION.
raw_asset = "Use the brass key as the hero's emotional anchor"
parsed_asset = prompt._parse_image_asset_payload(raw_asset)
assert parsed_asset == {}
asset_state = prompt._apply_image_asset_payload(
    prompt._default_widget_state(),
    parsed_asset,
    connected=True,
)
assert raw_asset not in fallback_texts(asset_state)
assert asset_state["image_asset"]["enabled"] is True

raw_picker = '["slow orbit", {"mood":"hesitant"}]'
parsed_picker = prompt._parse_picker_payload(raw_picker)
assert parsed_picker == {}
picker_state = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    parsed_picker,
    connected=True,
)
assert "slow orbit" not in "\n".join(fallback_texts(picker_state))
assert picker_state["picker"]["enabled"] is True


# Foreign contracts are preserved and cannot erase existing connected state.
existing = prompt._default_widget_state()
existing["videos"] = [{
    **prompt._default_video_item(1),
    "present": True,
    "label": "manual_color",
    "source_type": "Custom",
    "custom_source_type": "User-directed dream motion",
    "control_role": "Custom Role",
    "custom_control_role": "Drive the final goal",
}]
existing["picker"] = {
    **existing["picker"],
    "enabled": True,
    "run_id": "keep-run",
    "video_path": "C:/keep/manual_color.mp4",
}
foreign_picker = {
    "schema": "future-picker-contract",
    "mode": "experimental-user-mode",
    "instruction": "Use every reflection as choreography",
}
foreign_result = prompt._apply_picker_payload(existing, foreign_picker, connected=True)
assert foreign_result["videos"][0]["label"] == "manual_color"
assert foreign_result["picker"]["run_id"] == "keep-run"
assert "Use every reflection" not in "\n".join(fallback_texts(foreign_result))
foreign_user = prompt_json_section(
    prompt._build_prompt_package(foreign_result),
    "USER DESCRIPTION DATA (JSON):",
)
assert foreign_user == {}


# A shorter connected Asset selection removes only the deselected upstream-owned
# row. Non-row malformed intent remains preserved separately.
state = prompt._default_widget_state()
row_a = {
    **prompt._default_image_item(1),
    "present": True,
    "label": "HeroA",
    "asset_source_uid": "uid-a",
    "asset_managed": True,
    "source_type": "Character Appearance",
    "owner": "Hero A custom target",
    "binding_scopes": ["Full body / full appearance"],
    "color_picks": ["Red"],
}
row_b = {
    **prompt._default_image_item(2),
    "present": True,
    "label": "HeroB user rename",
    "asset_id": "HeroB",
    "asset_path": "P:/ideas/HeroB.png",
    "asset_library_id": "library-b",
    "asset_source_uid": "uid-b",
    "asset_project_uid": "project-b",
    "asset_selection_order": 2,
    "asset_managed": True,
    "asset_verified": True,
    "asset_source_kind": "project",
    "source_type": "Custom",
    "custom_source_type": "Memory apparition",
    "owner": "Any user-defined relationship target",
    "legacy_relationship_targets": ["Second simultaneous target"],
    "binding_scopes": ["Impossible custom scope"],
    "color_picks": ["Ultraviolet user tone"],
    "binding_video_slots": [5],
}
state["images"] = [row_a, row_b]
short_asset_payload = {
    "schema": "hmb-image-asset-library-binding",
    "mode": "image_asset",
    "ordered_images": [
        {"source_uid": "uid-a", "image_name": "Upstream Hero A"},
        "a handwritten third image idea",
    ],
}
short_result = prompt._apply_image_asset_payload(
    state,
    short_asset_payload,
    connected=True,
)
assert not any(
    item["label"] == "HeroB user rename"
    for item in short_result["images"]
)
assert short_result["images"][0]["asset_source_uid"] == "uid-a"
assert "a handwritten third image idea" not in fallback_texts(short_result)


# Unknown upstream scope/Color candidates stay readable and available.
custom_asset_payload = {
    "schema": "hmb-image-asset-library-binding",
    "mode": "image_asset",
    "project_uid": "p",
    "ordered_images": [{
        "order_key": "custom-1",
        "source_uid": "custom-1",
        "image_name": "CustomAsset",
    }],
    "verified_assets": [{
        "order_key": "custom-1",
        "source_uid": "custom-1",
        "selection_order": 1,
        "verified_asset": True,
        "source_kind": "project",
        "binding_mode": "verified_asset",
        "asset_id": "CustomAsset",
        "asset_library_id": "lib-custom",
        "source_type": "Character Appearance",
        "scope_candidate": "Invented cinematic scope",
        "color_pick_candidates": ["Red", "Infrared dream marker"],
    }],
}
custom_result = prompt._apply_image_asset_payload(
    prompt._default_widget_state(),
    custom_asset_payload,
    connected=True,
)
custom_row = custom_result["images"][0]
assert custom_row["asset_scope_candidate"] == "Invented cinematic scope"
assert custom_row["asset_color_pick_candidates"] == ["Red", "Infrared dream marker"]
fallback_blob = "\n".join(fallback_texts(custom_result))
assert "Invented cinematic scope" not in fallback_blob
assert "Infrared dream marker" not in fallback_blob


# Picker refresh may replace only its auto marker, never the user's frame range.
range_state = prompt._default_widget_state()
range_image = {
    **prompt._default_image_item(1),
    "present": True,
    "label": "Hero",
    "asset_id": "Hero",
    "source_type": "Character Appearance",
    "binding_scopes": ["Full body / full appearance"],
    "color_picks": ["Red"],
    "binding_video_slots": [1],
    "picker_auto_color": "Red",
    "picker_auto_video": 1,
    "picker_auto_source": "old-picker",
    "frame_range_enabled": True,
    "frame_range_bindings": {
        "@video1::Red": {
            "video_slot": "@video1",
            "color_pick": "Red",
            "origin": "manual",
            "start_frame": 101,
            "end_frame": 140,
            "ranges": [{"start": 110, "end": 120}],
        },
    },
}
range_state["images"] = [range_image]
picker_payload = {
    "schema": "hmb-prompt-library-picker-binding",
    "mode": "maya",
    "media_ready": True,
    "scene_path": "P:/shot.ma",
    "videos": [{"video_slot": 1, "video_path": "P:/color.mp4"}],
    "markers": [{"video_slot": 1, "asset_id": "Hero", "color": "Red"}],
}
range_result = prompt._apply_picker_payload(range_state, picker_payload, connected=True)
assert range_result["images"][0]["frame_range_bindings"]["@video1::Red"]["origin"] == "manual"
assert range_result["images"][0]["frame_range_bindings"]["@video1::Red"]["ranges"] == [{"start": 110, "end": 120}]

auto_range_state = copy.deepcopy(range_state)
auto_range_state["images"][0]["frame_range_bindings"]["@video1::Red"]["origin"] = "picker_auto"
auto_range_result = prompt._apply_picker_payload(auto_range_state, picker_payload, connected=True)
assert "@video1::Red" not in auto_range_result["images"][0]["frame_range_bindings"]


# Unknown Picker markers remain usable rather than being normalized to blank.
unknown_payload = copy.deepcopy(picker_payload)
unknown_payload["markers"][0]["color"] = "Infrared dream marker"
unknown_state = prompt._default_widget_state()
unknown_state["images"] = [{
    **prompt._default_image_item(1),
    "present": True,
    "label": "Hero",
    "asset_id": "Hero",
    "source_type": "Character Appearance",
}]
unknown_result = prompt._apply_picker_payload(unknown_state, unknown_payload, connected=True)
assert unknown_result["images"][0]["color_picks"] == ["Infrared dream marker"]


# Dormant addresses and every Target are expressly available now; Prop does not
# hardcode @video1 when the user bound a different source.
goal_state = prompt._default_widget_state()
goal_state["images"] = [{
    **prompt._default_image_item(1),
    "present": True,
    "label": "Key",
    "source_type": "Prop / Accessory",
    "owner": "Hero hand",
    "legacy_relationship_targets": ["Door lock", "Memory echo"],
    "binding_scopes": ["Handheld prop"],
    "color_picks": ["Custom brass marker"],
    "binding_video_slots": [3],
}]
goal_state["text"]["SCENE_CONTEXT"] = "Resolve @video5 as a dream-memory rhythm"
goal_prompt = prompt._build_prompt_package(goal_state)
goal_job = prompt_json_section(goal_prompt, "HMB JOB DATA (JSON):")
goal_image = goal_job["images"][0]
assert goal_image["target_id"] == "Hero hand"
assert goal_image["relationship_targets"] == ["Door lock", "Memory echo"]
assert goal_image["bindings"] == [{
    "video": "@video3",
    "marker_color": "Custom brass marker",
    "target_scope": "Handheld prop",
}]
goal_user = prompt_json_section(goal_prompt, "USER DESCRIPTION DATA (JSON):")
assert goal_user == {"SCENE_CONTEXT": "Resolve @video5 as a dream-memory rhythm"}

malformed_text_state = prompt._default_widget_state()
malformed_text_state["text"]["PRESERVED_TEXT"] = "free readable words\n[Future Tag] exact future phrase"
malformed_prompt = prompt._build_prompt_package(malformed_text_state)
assert prompt_json_section(
    malformed_prompt,
    "USER DESCRIPTION DATA (JSON):",
) == {
    "PRESERVED_TEXT": "free readable words\n[Future Tag] exact future phrase",
}

source = (ROOT / "HMBPromptLibrary.py").read_text(encoding="utf-8")
for forbidden in (
    "Target remains the sole",
    "retains exclusive",
    "secondary Target fields are forbidden",
    "follow @video1 when present",
    "until that slot is available",
):
    assert forbidden not in source

print("HMB Prompt connection data-boundary regression: PASS")
