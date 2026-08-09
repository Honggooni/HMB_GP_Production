from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_POLICY_VERSION = "2026-08-06.animation-look-continuity.v3"
EXPECTED_CONTRACT_SHA256 = "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
EXPECTED_POLICY_SHA256 = "6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619"


def load(filename: str, alias: str):
    path = ROOT / f"{filename}.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


common = load("_hmb_common", "hmb_four_flow_common")
asset_library = load("HMBImageAssetLibrary", "hmb_four_flow_image_asset")
prompt_library = load("HMBPromptLibrary", "hmb_four_flow_prompt")
agent_library = load("HMBAgentLibrary", "hmb_four_flow_agent")


# Prompt and Image Asset bind the exact same common taxonomy objects. No copied
# Python literal is allowed to become a second source of truth.
assert (
    prompt_library.IMAGE_SOURCE_TYPE_CHOICES
    is prompt_library._hmb.IMAGE_SOURCE_TYPE_CHOICES
)
assert (
    asset_library.IMAGE_SOURCE_TYPE_CHOICES
    is asset_library._hmb.IMAGE_SOURCE_TYPE_CHOICES
)
assert asset_library._hmb is prompt_library._hmb
assert agent_library._hmb is prompt_library._hmb
assert prompt_library.IMAGE_SOURCE_TYPE_CHOICES == common.IMAGE_SOURCE_TYPE_CHOICES
assert prompt_library.IMAGE_SCOPE_CHOICES == common.IMAGE_SCOPE_CHOICES


png_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)
tmp_parent = ROOT / ".tmp"
tmp_parent.mkdir(parents=True, exist_ok=True)
project_root = Path(
    tempfile.mkdtemp(prefix="hmb_image_asset_regression_", dir=tmp_parent)
)
try:
    hero_path = (
        project_root
        / "Character Appearance"
        / "Full body - full appearance"
        / "hero_beauty.png"
    )
    background_path = (
        project_root
        / "Environment"
        / "Background"
        / "Main background"
        / "night_city.png"
    )
    hero_path.parent.mkdir(parents=True)
    background_path.parent.mkdir(parents=True)
    hero_path.write_bytes(png_1x1)
    background_path.write_bytes(png_1x1)
    (project_root / "hmb_image_assets.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "path": hero_path.relative_to(project_root).as_posix(),
                        "asset_id": "HeroRig",
                        "image_name": "Hero Beauty",
                        "source_type": "Character Appearance",
                        "scope": "Full body / full appearance",
                        "selected": True,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    scan = asset_library._scan_project_assets(project_root)
    assert len(scan["assets"]) == 2
    hero = next(asset for asset in scan["assets"] if asset["asset_id"] == "HeroRig")
    background = next(
        asset for asset in scan["assets"] if asset["image_name"] == "night_city"
    )
    assert hero["source_type"] == "Character Appearance"
    assert hero["scope_candidate"] == "Full body / full appearance"
    assert hero["color_pick_candidates"] == (
        common.image_color_pick_choices_for_source_type("Character Appearance")
    )
    assert hero["registered"] is True
    assert background["source_type"] == "Environment / Background"
    assert background["scope_candidate"] == "Main background"
    assert background["registered"] is False
    assert background["selected"] is False

    image_node = asset_library.HMBImageAssetLibrary(name="four_library_image_asset")
    image_state = asset_library._merge_scan_with_state(
        scan,
        image_node._current_state(),
    )
    image_node._publish_state(image_state)
    output_payload = json.loads(
        image_node.parameter_output_values[asset_library.OUTPUT_PARAMETER]
    )
    assert output_payload["schema"] == "hmb-image-asset-library-binding"
    assert output_payload["mode"] == "image_asset"
    assert output_payload["version"] == asset_library.OUTPUT_VERSION == 4
    assert [item["asset_id"] for item in output_payload["selected_assets"]] == [
        "HeroRig"
    ]
    assert output_payload["selected_assets"] == output_payload["verified_assets"]
    assert output_payload["verified_assets"][0]["verified_asset"] is True
    assert output_payload["ordered_images"] == [
        {
            "order_key": hero["source_uid"],
            "image_name": "Hero Beauty",
            "selection_order": 1,
        }
    ]
    assert "final creative authority" in output_payload["authority"][
        "current_user_goal"
    ].casefold()
    assert output_payload["authority"]["optional_downstream_refinement"] == [
        "Target",
        "Color Pick",
    ]
    assert "registered main type and image sub type" in output_payload["authority"][
        "connection_policy"
    ].casefold()
    assert "prompt_final" not in output_payload["authority"]

    tree = image_state["tree"]
    assert tree["kind"] == "root"
    character_node = next(
        node
        for node in tree["children"]
        if node["folder_path"] == "Character Appearance"
    )
    full_body_node = next(
        node
        for node in character_node["children"]
        if node["folder_path"] == "Character Appearance/Full body - full appearance"
    )
    assert full_body_node["children"][0]["asset_id"] == "HeroRig"
    assert all(
        node.get("folder_path") != "Prop / Accessory"
        for node in tree["children"]
    )

    # A fresh verified row receives a Main-Type Target default and the registered
    # Sub Type as its actual Prompt binding.
    default_bound_state = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        output_payload,
        connected=True,
    )
    default_bound_row = default_bound_state["images"][0]
    assert default_bound_row["owner"] == "Hero Beauty"
    assert default_bound_row["asset_default_target"] == "Hero Beauty"
    assert default_bound_row["binding_scopes"] == ["Full body / full appearance"]
    assert default_bound_row["scope"] == "Full body / full appearance"
    default_bound_prompt = prompt_library._build_prompt_package(default_bound_state)
    assert (
        "Hero Beauty / Approved final appearance source = @image1 / "
        "Full body / full appearance"
    ) in default_bound_prompt
    default_bound_row["owner"] = ""
    default_bound_row["color_picks"] = ["Red", "Green"]
    cleared_target_state = prompt_library._apply_image_asset_payload(
        default_bound_state,
        output_payload,
        connected=True,
    )
    assert cleared_target_state["images"][0]["owner"] == ""
    assert cleared_target_state["images"][0]["binding_scopes"] == [
        "Full body / full appearance",
        "Full body / full appearance",
    ]
    assert prompt_library._default_image_target_for_main_type(
        "Environment / Background", "Night City"
    ) == "Scene / Environment"
    assert prompt_library._default_image_target_for_main_type(
        "Scale / Composition Reference", "Wide Shot"
    ) == "Camera / Composition"
    assert prompt_library._default_image_target_for_main_type(
        "Lighting / Atmosphere Reference", "Blue Hour"
    ) == "Global Look"

    # Prompt may already hold a freely authored Target and Color Pick. Applying
    # Asset Library metadata preserves those fields but replaces the Prompt Sub
    # Type with the registered authoritative value.
    prompt_state = prompt_library._default_widget_state()
    prompt_state["images"][0].update(
        {
            "present": True,
            "label": "Hero Beauty",
            "source_type": "Character Appearance",
            "owner": "Hero Custom Target",
            "binding_scopes": ["Head / face only"],
            "scope": "Head / face only",
            "color_picks": ["Blue"],
        }
    )
    prompt_state["videos"][0].update(
        {
            "present": True,
            "label": "shot_playblast",
            "source_type": "Maya Preview / Playblast",
            "control_role": "Primary Unified Shot Control",
        }
    )
    prompt_state = prompt_library._apply_image_asset_payload(
        prompt_state,
        output_payload,
        connected=True,
    )
    prompt_row = prompt_state["images"][0]
    assert prompt_row["asset_verified"] is True
    assert prompt_row["asset_source_kind"] == "project"
    assert prompt_row["asset_id"] == "HeroRig"
    assert prompt_row["label"] == "Hero Beauty"
    assert prompt_row["owner"] == "Hero Custom Target"
    assert prompt_row["binding_scopes"] == ["Full body / full appearance"]
    assert prompt_row["scope"] == "Full body / full appearance"
    assert prompt_row["color_picks"] == ["Blue"]
    assert prompt_row["asset_scope_candidate"] == "Full body / full appearance"
    assert prompt_row["asset_color_pick_candidates"] == (
        common.image_color_pick_choices_for_source_type("Character Appearance")
    )

    # Video Picker markers bind against the exact Asset ID even when Image Name
    # differs; legacy rows still fall back to Image Name.
    assert prompt_library._picker_match_candidates(
        prompt_state["images"],
        {"asset_id": "HeroRig"},
        set(),
    ) == [0]
    assert not prompt_library._picker_match_candidates(
        prompt_state["images"],
        {"asset_id": "Hero Beauty"},
        set(),
    )
    compiled_prompt = prompt_library._build_prompt_package(prompt_state)
    assert "@image1 = Hero Beauty / Asset ID: HeroRig" in compiled_prompt
    assert (
        "Hero Custom Target / Approved final appearance source = @image1 / "
        "Full body / full appearance"
    ) in compiled_prompt

    # The fourth stage receives its rules only through the signed Agent payload.
    policy = agent_library.get_internal_policy_rules()
    policy_identity = common.get_internal_policy_identity()
    assert policy
    assert policy_identity == {
        "version": EXPECTED_POLICY_VERSION,
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
    }
    bundled_policy_path = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
    assert bundled_policy_path.is_file()
    bundled_policy = bundled_policy_path.read_bytes()
    assert hashlib.sha256(bundled_policy).hexdigest() == EXPECTED_POLICY_SHA256
    assert policy.encode("utf-8") not in bundled_policy
finally:
    shutil.rmtree(project_root, ignore_errors=True)


print(
    "HMB ImageAsset -> VideoPicker identity -> Prompt authority -> Agent policy "
    "four-library flow regression: PASS"
)
