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
        "video_main_type": "FX / Simulation Reference",
        "video_sub_type": "Explosion",
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
assert merged["videos"][0]["video_main_type"] == "FX / Simulation Reference"
assert merged["videos"][0]["video_sub_type"] == "Explosion"
assert merged["videos"][0]["keep_out"] == "Ignore proxy sparks."
assert merged["videos"][0]["label"] == "Source Video"

# Only is a real Prompt-owned selection too. A simultaneous source callback
# must not resurrect the previously selected Shot.
only_ui = copy.deepcopy(ui)
only_ui["shot"] = prompt._normalize_shot_selection({})
only_merged = prompt._merge_prompt_revision_axes(source, only_ui)
assert only_merged["shot"] == prompt._normalize_shot_selection({})

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


print(
    "HMB Prompt revision-axis regression: PASS "
    "(stable identity / equal echo / crossed clocks / saved reload)"
)
