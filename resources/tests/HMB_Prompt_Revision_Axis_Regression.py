from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def load_prompt():
    path = ROOT / "HMBPromptLibrary.py"
    name = "_hmb_prompt_revision_axis_regression"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt = load_prompt()


def range_intent(start: int, end: int):
    return {
        "version": 1,
        "enabled": True,
        "start_frame": start,
        "end_frame": end,
        "ranges": [{"start": start, "end": end}],
        "selected_index": 0,
    }


# Two independent writer clocks may cross. Source structure wins its axis, but
# Prompt selections follow stable media identity rather than transient row slot.
ui = prompt._default_widget_state()
ui[prompt.SOURCE_SYNC_REVISION_KEY] = 20
ui[prompt.UI_EDIT_REVISION_KEY] = 7
ui["image_asset"]["shot_catalog_routing"] = {
    "publisher_instance_uuid": "publisher-alpha",
    "channel_uuid": "channel-alpha",
    "generation": 20,
    "metadata_sha256": "a" * 64,
}
ui["image_asset"]["shot_catalog"] = [
    {
        "shot_uuid": "shot-alpha",
        "channel_uuid": "channel-alpha",
        "name": "Shot 1",
        "number": 1,
        "selected_source_uids": ["image-alpha"],
    },
    {
        "shot_uuid": "shot-beta",
        "channel_uuid": "channel-alpha",
        "name": "Shot 2",
        "number": 2,
        "selected_source_uids": ["image-beta"],
    },
]
ui["shot"] = copy.deepcopy(ui["image_asset"]["shot_catalog"][1])
ui["ui"]["language"] = "en"
ui["ui"]["textarea_heights"] = {"video:1:keep_out": 333}
ui["source_intent_fallbacks"] = [
    {
        "source": "PICKER_IN",
        "reason": "older source callback",
        "text": "do not restore this stale connected intent",
    }
]
ui["images"][0].update(
    {
        "asset_source_uid": "image-alpha",
        "asset_managed": True,
        "label": "UI Alpha",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "owner": "image 1",
        "color_picks": ["Red"],
        "binding_video_slots": [1],
        "frame_range_intent": range_intent(101, 120),
    }
)
ui["images"][1].update(
    {
        "asset_source_uid": "image-beta",
        "asset_managed": True,
        "label": "UI Beta",
        "image_main_type": "Character",
        "image_sub_type": "Head / Face",
        "owner": "image 2",
        "color_picks": ["Green"],
        "binding_video_slots": [1],
        "frame_range_intent": range_intent(201, 208),
    }
)
ui["videos"][0].update(
    {
        "video_uid": "video-alpha",
        "source_uid": "video-alpha",
        "picker_managed": True,
        "label": "UI Video",
        "video_main_type": "FX Reference",
        "video_sub_type": "FX Effect Only",
        "keep_out": "Ignore proxy sparks.",
    }
)
ui = prompt._normalize_state(ui)
ui["text"]["SCENE_CONTEXT"] = "latest UI context"

source = copy.deepcopy(ui)
source[prompt.SOURCE_SYNC_REVISION_KEY] = 21
source["picker"]["run_id"] = "source-generation-21"
source["text"]["SCENE_CONTEXT"] = "stale source context"
source["shot"] = copy.deepcopy(source["image_asset"]["shot_catalog"][0])
source["ui"]["language"] = "ko"
source["ui"]["textarea_heights"] = {"video:1:keep_out": 100}
source["source_intent_fallbacks"] = [
    {
        "source": "PICKER_IN",
        "reason": "newest source callback",
        "text": "retain this newest connected intent",
    }
]
source["images"] = list(reversed(source["images"]))
for item in source["images"]:
    if item.get("asset_source_uid"):
        item["label"] = f"Source {item['asset_source_uid']}"
    item.update(
        {
            "image_main_type": prompt.IMAGE_MAIN_TYPE_UNCLASSIFIED,
            "image_sub_type": "",
            "owner": "",
            "color_picks": [""],
            "frame_range_intent": {
                "version": 1,
                "enabled": False,
                "start_frame": None,
                "end_frame": None,
                "ranges": [],
                "selected_index": -1,
            },
        }
    )
source["videos"][0].update(
    {
        "label": "Source Video",
        "video_main_type": "Select Video Main Type",
        "video_sub_type": "",
        "keep_out": "",
    }
)

merged = prompt._merge_prompt_revision_axes(source, ui)
assert merged[prompt.SOURCE_SYNC_REVISION_KEY] == 21
assert merged[prompt.UI_EDIT_REVISION_KEY] == 7
assert merged["picker"]["run_id"] == "source-generation-21"
assert merged["text"]["SCENE_CONTEXT"] == "latest UI context"
assert merged["shot"]["shot_uuid"] == "shot-beta"
assert merged["shot"]["selected_source_uids"] == ["image-beta"]
assert merged["ui"]["language"] == "en"
assert merged["ui"]["textarea_heights"]["video:1:keep_out"] == 333
assert merged["source_intent_fallbacks"] == source["source_intent_fallbacks"]
by_image_uid = {item["asset_source_uid"]: item for item in merged["images"]}
assert by_image_uid["image-alpha"]["label"] == "Source image-alpha"
assert by_image_uid["image-alpha"]["image_main_type"] == "Character"
assert by_image_uid["image-alpha"]["image_sub_type"] == "Full Appearance"
assert by_image_uid["image-alpha"]["color_picks"] == ["Red"]
assert by_image_uid["image-alpha"]["frame_range_intent"] == range_intent(101, 120)
assert by_image_uid["image-beta"]["image_sub_type"] == "Head / Face"
assert by_image_uid["image-beta"]["color_picks"] == ["Green"]
assert by_image_uid["image-beta"]["frame_range_intent"] == range_intent(201, 208)
assert merged["videos"][0]["video_main_type"] == "FX Reference"
assert merged["videos"][0]["video_sub_type"] == "FX Effect Only"
assert merged["videos"][0]["keep_out"] == "Ignore proxy sparks."
assert merged["videos"][0]["label"] == "Source Video"

# A verified asset keeps source-owned Main provenance while Prompt-owned Sub
# and Target survive crossed revision axes verbatim.
look_source = prompt._default_widget_state()
look_source["images"][0].update(
    {
        "present": True,
        "label": "Registered Look",
        "asset_managed": True,
        "asset_verified": True,
        "asset_source_kind": "project",
        "asset_source_uid": "verified-look-axis",
        "asset_image_main_type_candidate": "Look Reference",
        "asset_image_sub_type_candidate": "Render Style",
        "image_main_type": "Look Reference",
        "image_sub_type": "Render Style",
        "owner": "Global Look",
    }
)
look_ui = copy.deepcopy(look_source)
look_ui["images"][0]["asset_image_sub_type_candidate"] = "Color Mood"
look_ui["images"][0]["image_sub_type"] = "Scale"
look_ui["images"][0]["owner"] = "Director Camera"
look_merged = prompt._merge_prompt_revision_axes(look_source, look_ui)
look_row = look_merged["images"][0]
assert look_row["asset_image_sub_type_candidate"] == "Render Style"
assert look_row["image_main_type"] == "Look Reference"
assert look_row["image_sub_type"] == "Scale"
assert look_row["source_type"] == "Role Required / Select Source Type"
assert look_row["scope"] == ""
assert look_row["owner"] == "Director Camera"
assert look_row["color_picks"] == [""]

# A stale registered default is not an override. A newer global registration
# therefore remains authoritative when the UI had never chosen another Sub.
look_default_ui = copy.deepcopy(look_source)
look_default_ui["images"][0]["asset_image_sub_type_candidate"] = "Color Mood"
look_default_ui["images"][0]["image_sub_type"] = "Color Mood"
look_default_ui["images"][0]["owner"] = "Jett_08"
look_default_merged = prompt._merge_prompt_revision_axes(
    look_source,
    look_default_ui,
)
assert look_default_merged["images"][0]["image_sub_type"] == "Color Mood"
assert look_default_merged["images"][0]["owner"] == "Jett_08"

# Only is a real Prompt-owned selection too. A simultaneous source callback
# must not resurrect the previously selected Shot.
only_ui = copy.deepcopy(ui)
only_ui["shot"] = prompt._normalize_shot_selection({})
only_merged = prompt._merge_prompt_revision_axes(source, only_ui)
assert only_merged["shot"] == prompt._normalize_shot_selection({})

# A Prompt created first has only the default catalog-less Only placeholder.
# Text entered before ImageAsset arrives remains Prompt-owned, while the first
# backend-proven Shot must be accepted instead of being overwritten to Only.
prompt_first_ui = prompt._default_widget_state()
prompt_first_ui["text"]["SCENE_CONTEXT"] = "typed before ImageAsset"
prompt_first_ui[prompt.UI_EDIT_REVISION_KEY] = 1
prompt_first_source = copy.deepcopy(source)
prompt_first_source["text"]["SCENE_CONTEXT"] = "older source text"
prompt_first_merged = prompt._merge_prompt_revision_axes(
    prompt_first_source,
    prompt_first_ui,
)
assert prompt_first_merged["text"]["SCENE_CONTEXT"] == "typed before ImageAsset"
assert prompt_first_merged["shot"]["shot_uuid"] == "shot-alpha"

# An Only selection from another/older publisher has no authority to suppress
# the first Shot of a replacement ImageAsset publisher.
old_publisher_only = copy.deepcopy(only_ui)
replacement_source = copy.deepcopy(source)
replacement_source["image_asset"]["shot_catalog_routing"].update({
    "publisher_instance_uuid": "publisher-replacement",
    "channel_uuid": "channel-replacement",
    "generation": 1,
    "metadata_sha256": "b" * 64,
})
for item in replacement_source["image_asset"]["shot_catalog"]:
    item["channel_uuid"] = "channel-replacement"
replacement_source["shot"] = copy.deepcopy(
    replacement_source["image_asset"]["shot_catalog"][0]
)
replacement_merged = prompt._merge_prompt_revision_axes(
    replacement_source,
    old_publisher_only,
)
assert replacement_merged["shot"]["shot_uuid"] == "shot-alpha"

manual_ui = prompt._default_widget_state()
manual_ui[prompt.SOURCE_SYNC_REVISION_KEY] = 2
manual_ui[prompt.UI_EDIT_REVISION_KEY] = 3
manual_ui["images"][0]["label"] = "Manual Image UI"
manual_ui["videos"][0]["label"] = "Manual Video UI"
manual_ui = prompt._normalize_state(manual_ui)
manual_source = copy.deepcopy(manual_ui)
manual_source[prompt.SOURCE_SYNC_REVISION_KEY] = 3
manual_source["images"][0]["label"] = "Stale Manual Image"
manual_source["videos"][0]["label"] = "Stale Manual Video"
manual_merged = prompt._merge_prompt_revision_axes(manual_source, manual_ui)
assert manual_merged["images"][0]["label"] == "Manual Image UI"
assert manual_merged["videos"][0]["label"] == "Manual Video UI"


# Both source axes can advance between two Prompt writes. A slot in the
# older UI still refers to the same UID when that edit reaches the new order.
before = prompt._default_widget_state()
before["shot"] = copy.deepcopy(ui["shot"])
before["picker"]["order_managed"] = before["image_asset"]["order_managed"] = True
before["text"].update(SCENE_CONTEXT="@image1, @image2, @video1, @video2", PRESERVED_TEXT="@image1 @video1")
before["analysis_generated_text"] = {"SCENE_CONTEXT": before["text"]["SCENE_CONTEXT"], "PRESERVED_TEXT": "@image1 @video1"}
before["sound_overlays"] = {"dialog": {"speaker_binding": {"kind": "video", "source_id": "original", "color": "Red"}}}
before["images"] = [dict(prompt._default_image_item(n), asset_source_uid=uid, asset_managed=True,
    present=True, label=uid, binding_video_slots=[1], color_picks=["Red"], frame_range_intent=range_intent(2, 8),
    preview_marker="@video1") for n, uid in enumerate(("left", "retired", "right"), 1)]
before["videos"] = [dict(prompt._default_video_item(n), video_uid=uid, source_uid=uid, present=True,
    label=uid, picker_managed=True, keep_out="@image1 @video1") for n, uid in enumerate(("original", "mask"), 1)]
before["ui"]["textarea_heights"] = {"video:1:keep_out": 333}
before[prompt.SOURCE_SYNC_REVISION_KEY] = 1
before = prompt._normalize_state(before)
latest = copy.deepcopy(before)
latest[prompt.SOURCE_SYNC_REVISION_KEY] = 2
latest["images"] = [latest["images"][2], latest["images"][0]]
latest["videos"].reverse()
result = prompt._merge_prompt_revision_axes(latest, before)
assert [item["binding_video_slots"] for item in result["images"]] == [[2], [2]]
assert result["images"][0]["marker_video"] == 2 and result["images"][0]["color_picks"] == ["Red"]
assert result["images"][0]["frame_range_intent"] == range_intent(2, 8)
assert result["text"]["SCENE_CONTEXT"] == "@image2, [deselected image source #2], @video2, @video1"
assert result["text"]["PRESERVED_TEXT"] == "@image1 @video1"
assert result["analysis_generated_text"]["SCENE_CONTEXT"] == result["text"]["SCENE_CONTEXT"]
assert result["analysis_generated_text"]["PRESERVED_TEXT"] == before["analysis_generated_text"]["PRESERVED_TEXT"]
assert result["sound_overlays"] == before["sound_overlays"]
reanalyzed = copy.deepcopy(result)
assert prompt._merge_analysis_generated_text(reanalyzed, {"SCENE_CONTEXT": "New analysis of @video2"})
assert reanalyzed["text"]["SCENE_CONTEXT"] == "New analysis of @video2"
assert result["videos"][0]["keep_out"] == "@image2 @video2"
assert result["ui"]["textarea_heights"] == {"video:2:keep_out": 333}
assert prompt._merge_prompt_revision_axes(result, result) == result

concurrent_ui = copy.deepcopy(before)
concurrent_ui[prompt.UI_EDIT_REVISION_KEY] += 1
concurrent_ui["images"][0]["binding_video_slots"] = [2]
concurrent_ui["text"]["SCENE_CONTEXT"] = "Follow the mask @video2."
concurrent = prompt._merge_prompt_revision_axes(latest, concurrent_ui)
assert concurrent["images"][1]["binding_video_slots"] == [1]
assert concurrent["text"]["SCENE_CONTEXT"] == "Follow the mask @video1."
removed = copy.deepcopy(latest)
removed["videos"] = removed["videos"][:1]
result = prompt._merge_prompt_revision_axes(removed, before)
assert result["images"][0]["color_picks"] == [""] and result["images"][0]["binding_video_slots"] == [1]
assert "[deselected video source #1]" in result["text"]["SCENE_CONTEXT"]
assert result["sound_overlays"]["dialog"]["speaker_binding"]["source_id"] == "original"


# Equal clocks are acknowledgements only. An exact echo is accepted, while a
# same-clock payload with older selections/Range is rejected by both setter and
# the host's assign-before-after_value_set callback path.
node = prompt.HMBPromptLibrary(name="prompt_equal_revision_guard")
node.set_parameter_value(prompt.WIDGET_PARAMETER_NAME, prompt._json_dumps(merged))
accepted = prompt._normalize_state(node._current_state())
assert node._widget_state_write_is_stale(prompt._json_dumps(accepted)) is False

divergent = copy.deepcopy(accepted)
divergent["images"][0]["color_picks"] = [""]
divergent["images"][0]["frame_range_intent"] = {
    "version": 1,
    "enabled": False,
    "start_frame": None,
    "end_frame": None,
    "ranges": [],
    "selected_index": -1,
}
divergent["videos"][0]["video_main_type"] = "Select Video Main Type"
divergent["videos"][0]["video_sub_type"] = ""
assert node._widget_state_write_is_stale(prompt._json_dumps(divergent)) is True
node.set_parameter_value(prompt.WIDGET_PARAMETER_NAME, prompt._json_dumps(divergent))
assert prompt._normalize_state(node._current_state()) == accepted

node._schedule_prompt_sync = lambda: None
parameter = prompt._get_parameter_obj(node, prompt.WIDGET_PARAMETER_NAME)
parameter.default_value = prompt._json_dumps(divergent)
node.after_value_set(parameter, prompt._json_dumps(divergent))
assert prompt._normalize_state(node._current_state()) == accepted


# Saved state is intentionally a fresh baseline even if its clocks are lower.
# After reload, the same equal-clock rollback guard remains active.
saved = copy.deepcopy(accepted)
saved[prompt.SOURCE_SYNC_REVISION_KEY] = 4
saved[prompt.UI_EDIT_REVISION_KEY] = 3
restored_node = prompt.HMBPromptLibrary(name="prompt_revision_saved_reload")
restored_node.set_parameter_value(
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(saved),
    initial_setup=True,
)
restored = prompt._normalize_state(restored_node._current_state())
assert restored[prompt.SOURCE_SYNC_REVISION_KEY] == 4
assert restored[prompt.UI_EDIT_REVISION_KEY] == 3
saved_rollback = copy.deepcopy(restored)
saved_rollback["images"][0]["frame_range_intent"] = {
    "version": 1,
    "enabled": False,
    "start_frame": None,
    "end_frame": None,
    "ranges": [],
    "selected_index": -1,
}
restored_node.set_parameter_value(
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(saved_rollback),
)
assert prompt._normalize_state(restored_node._current_state()) == restored


# A source notification can update the exact selection before its compact
# catalog catches up. A crossed Prompt edit owns authoring only.
for multishot in (False, True):
    earlier = copy.deepcopy(ui)
    earlier["multi_shot_enabled"] = multishot
    for selected_uids in (["image-beta", "image-alpha"], ["image-alpha"], []):
        latest = copy.deepcopy(earlier)
        latest["shot"]["selected_source_uids"] = selected_uids
        latest[prompt.SOURCE_SYNC_REVISION_KEY] += 1
        earlier[prompt.UI_EDIT_REVISION_KEY] += 1
        result = prompt._merge_prompt_revision_axes(latest, earlier)
        assert result["shot"]["selected_source_uids"] == selected_uids

print(
    "HMB Prompt revision-axis regression: PASS "
    "(stable identity / equal echo / crossed clocks / saved reload)"
)
