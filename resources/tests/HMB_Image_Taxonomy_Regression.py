from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("_hmb_image_taxonomy_common", "_hmb_common.py")
prompt = load("_hmb_image_taxonomy_prompt", "HMBPromptLibrary.py")
image_asset = load("_hmb_image_taxonomy_asset", "HMBImageAssetLibrary.py")
agent = load("_hmb_image_taxonomy_agent", "HMBAgentLibrary.py")

assert prompt.IMAGE_MAIN_TYPE_CHOICES == [
    "Select Image Main Type",
    "Character",
    "Character Prop",
    "Environment / Background",
    "Background Prop",
    "Look Reference",
    "Custom / Context",
]
assert "Scene / Look Reference" not in prompt.IMAGE_MAIN_TYPE_CHOICES
assert "Character Appearance" not in prompt.IMAGE_MAIN_TYPE_CHOICES
assert len(prompt.IMAGE_TAXONOMY_WIRE_MAP) == 26

# Old Main/Sub/Target/Color state is intentionally released, while the image
# identity and media remain available for the user to classify again.
legacy = prompt._default_widget_state()
legacy["images"][0].update({
    "present": True,
    "label": "legacy.png",
    "asset_id": "legacy",
    "source_type": "Character Appearance",
    "scope": "Full body / full appearance",
    "binding_scopes": ["Full body / full appearance"],
    "owner": "hero",
    "color_picks": ["Red"],
})
released = prompt._normalize_state(legacy)["images"][0]
assert released["image_main_type"] == "Select Image Main Type"
assert released["image_sub_type"] == ""
assert released["source_type"] == "Role Required / Select Source Type"
assert released["scope"] == ""
assert released["owner"] == ""
assert released["color_picks"] == [""]
assert released["label"] == "legacy.png"
assert released["asset_id"] == "legacy"

for (main_type, sub_type), wire_pair in prompt.IMAGE_TAXONOMY_WIRE_MAP.items():
    item = prompt._default_image_item(1)
    item.update({
        "present": True,
        "label": f"{main_type}-{sub_type}.png",
        "image_main_type": main_type,
        "image_sub_type": sub_type,
    })
    normalized = prompt._normalize_image_binding_fields(item)
    assert (normalized["source_type"], normalized["scope"]) == wire_pair
    state = prompt._default_widget_state()
    state["images"] = [normalized]
    package = prompt._build_data_only_prompt_package(state)
    validated = agent._assert_public_job_data_contract(package)
    assert validated["images"][0]["source_type"] == wire_pair[0]

character_prop = prompt._default_image_item(1)
character_prop.update({
    "image_main_type": "Character Prop",
    "image_sub_type": "Handheld Prop",
    "color_picks": ["Red", "Sky Blue"],
})
prompt._normalize_image_binding_fields(character_prop)
assert character_prop["color_picks"] == ["Red"]

background_prop = prompt._default_image_item(1)
background_prop.update({
    "image_main_type": "Background Prop",
    "image_sub_type": "Set / Structure",
    "color_picks": ["Mint", "Green"],
})
prompt._normalize_image_binding_fields(background_prop)
assert background_prop["color_picks"] == ["Mint"]

look = prompt._default_image_item(1)
look.update({
    "present": True,
    "label": "look.png",
    "image_main_type": "Look Reference",
    "image_sub_type": "Render Look",
    "owner": "Former Character Target",
    "color_picks": ["Red", "Sky Blue"],
})
prompt._normalize_image_binding_fields(look)
assert look["color_picks"] == [""]
assert look["owner"] == "Global Look"
assert look["interaction_targets"] == [""]
assert prompt._image_binding_entries(look) == []
assert common.image_color_pick_choices_for_taxonomy("Look Reference", "Render Look") == []

# Server records use only the new authoring fields. Legacy record values are
# never treated as migration input.
server_legacy = image_asset._normalize_image_taxonomy_fields({
    "source_type": "Character Appearance",
    "scope": "Full body / full appearance",
})
assert server_legacy["image_main_type"] == "Select Image Main Type"
assert server_legacy["image_sub_type"] == ""

server_look = image_asset._normalize_image_taxonomy_fields({
    "image_main_type": "Look Reference",
    "image_sub_type": "Color Mood",
    "source_type": "Character Appearance",
    "scope": "Full body / full appearance",
})
assert server_look["source_type"] == "Color / Look Reference"
assert server_look["scope_candidate"] == "Color mood only"
assert server_look["color_pick_candidates"] == []

print(
    "HMB image taxonomy regression: PASS "
    "(legacy release, 26 Agent projections, Look Reference has no Color Pick)"
)
