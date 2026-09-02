from __future__ import annotations

from copy import deepcopy
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]


def load(filename: str, alias: str):
    path = ROOT / f"{filename}.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def apply_widget_state_and_wait(node, state):
    """Exercise the non-blocking scan path, then consume its exact result."""

    result = node._apply_widget_state(state)
    if not result.get("scan_busy"):
        return result
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        thread = getattr(node, "_hmb_scan_thread", None)
        if thread is not None:
            thread.join(timeout=0.1)
        if node._consume_pending_catalog_scan_result():
            final = node._current_state()
            assert final.get("scan_busy") is False
            return final
        if not getattr(node, "_hmb_scan_pending_key", ""):
            final = node._current_state()
            assert final.get("scan_busy") is False
            return final
        time.sleep(0.01)
    raise AssertionError("Background image-asset scan did not complete in 10 seconds.")


asset_library = load(
    "HMBImageAssetLibrary",
    "hmb_image_asset_import_order_asset",
)
prompt_library = load(
    "HMBPromptLibrary",
    "hmb_image_asset_import_order_prompt",
)
try:
    from griptape.artifacts import ImageArtifact, ImageUrlArtifact
except Exception:
    ImageArtifact = None
    ImageUrlArtifact = None


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
)

if ImageArtifact is not None and ImageUrlArtifact is not None:
    real_image_artifact = ImageArtifact(
        PNG_1X1,
        name="Actual_Artifact.png",
        format="png",
        width=1,
        height=1,
    )
    actual_record = asset_library._import_record(real_image_artifact, 1)
    assert actual_record is not None
    assert actual_record[0]["image_name"] == "Actual_Artifact"
    assert actual_record[0]["width"] == 1
    assert actual_record[0]["height"] == 1
    actual_state, actual_media_map = asset_library._merge_import_input(
        asset_library._default_state(),
        [real_image_artifact],
    )
    actual_media = asset_library._selected_media_values(
        actual_state,
        actual_media_map,
    )
    assert len(actual_media) == 1
    assert actual_media[0].startswith("data:image/")
    real_url_artifact = ImageUrlArtifact(
        "https://example.com/Actual_Url.png",
        name="Actual_Url.png",
    )
    url_record = asset_library._import_record(real_url_artifact, 1)
    assert url_record is not None
    assert url_record[0]["media_ref_kind"] == "url"


def payload_row(name: str, order: int) -> dict:
    return {
        "selected": True,
        "source_uid": f"source:{name}",
        "source_kind": "project",
        "asset_project_uid": "sw12:test",
        "asset_library_id": f"library:{name}",
        "asset_id": f"Asset_{name}",
        "image_name": name,
        "path": f"C:/Project/sw12/Custom/{name}.png",
        "image_main_type": "Custom / Context",
        "image_sub_type": "Custom",
        "source_type": "Custom",
        "custom_source_type": f"Type_{name}",
        "scope_candidate": "Custom scope",
        "color_pick_candidates": ["Red", "Green", "Blue"],
        "selection_order": order,
        "slot": order,
        "token": f"@image{order}",
    }


def payload(order: list[str]) -> dict:
    rows = [payload_row(name, index) for index, name in enumerate(order, start=1)]
    return {
        "schema": "hmb-image-asset-library-binding",
        "version": 2,
        "mode": "image_asset",
        "project_id": "sw12",
        "project_uid": "sw12:test",
        "project_root": "C:/Project/sw12",
        "selection_id": "-".join(order),
        "selected_assets": rows,
        "ordered_images": rows,
    }


def look_payload(sub_type: str = "Color Mood") -> dict:
    row = {
        "selected": True,
        "source_uid": "source:MasterLook",
        "source_kind": "project",
        "asset_project_uid": "sw12:test",
        "asset_library_id": "library:MasterLook",
        "asset_id": "Asset_MasterLook",
        "image_name": "Master Look",
        "path": "C:/Project/sw12/Look/MasterLook.png",
        "image_main_type": "Look Reference",
        "image_sub_type": sub_type,
        "selection_order": 1,
    }
    return {
        "schema": "hmb-image-asset-library-binding",
        "version": 2,
        "mode": "image_asset",
        "project_id": "sw12",
        "project_uid": "sw12:test",
        "project_root": "C:/Project/sw12",
        "selection_id": f"look-{sub_type}",
        "selected_assets": [row],
        "ordered_images": [row],
    }


def character_payload(image_name: str) -> dict:
    row = {
        "selected": True,
        "source_uid": "source:HeroCharacter",
        "source_kind": "project",
        "asset_project_uid": "sw12:test",
        "asset_library_id": "library:HeroCharacter",
        "asset_id": "Asset_HeroCharacter",
        "image_name": image_name,
        "path": f"C:/Project/sw12/Character/{image_name}.png",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "selection_order": 1,
    }
    return {
        "schema": "hmb-image-asset-library-binding",
        "version": 2,
        "mode": "image_asset",
        "project_id": "sw12",
        "project_uid": "sw12:test",
        "project_root": "C:/Project/sw12",
        "selection_id": f"character-{image_name}",
        "selected_assets": [row],
        "ordered_images": [row],
    }


# The temporary production catalog requested for this workstation must expose
# each direct child folder as one independently selectable project.
real_catalog_root = Path(r"C:\Project")
if real_catalog_root.is_dir():
    real_catalog = asset_library._discover_project_catalog(real_catalog_root)
    real_names = {item["name"] for item in real_catalog["projects"]}
    if {"ds4", "ka8", "sw12"}.issubset(real_names):
        for name in ("ds4", "ka8", "sw12"):
            selected = next(
                item for item in real_catalog["projects"] if item["name"] == name
            )
            scan = asset_library._scan_project_assets(selected["path"])
            assert scan["project_id"] == name
        direct_sw12 = asset_library._discover_project_catalog(
            real_catalog_root / "sw12"
        )
        assert [item["name"] for item in direct_sw12["projects"]] == ["sw12"]


tmp_parent = ROOT / ".tmp"
tmp_parent.mkdir(parents=True, exist_ok=True)
catalog_root = Path(
    tempfile.mkdtemp(prefix="hmb_project_catalog_", dir=tmp_parent)
)
try:
    sw12 = catalog_root / "sw12"
    ka8 = catalog_root / "ka8"
    (sw12 / "Custom").mkdir(parents=True)
    (sw12 / "Only Existing" / "Nested").mkdir(parents=True)
    ka8.mkdir(parents=True)
    project_a = sw12 / "Custom" / "Project_A.png"
    project_a.write_bytes(PNG_1X1)
    (sw12 / "hmb_image_assets.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "path": "Custom/Project_A.png",
                        "asset_id": "Project_A",
                        "image_name": "Project_A",
                        "image_main_type": "Custom / Context",
                        "image_sub_type": "Custom",
                        "source_type": "Custom",
                        "custom_source_type": "Regression fixture",
                        "scope": "Custom scope",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert [
        item["name"]
        for item in asset_library._discover_project_catalog(sw12)["projects"]
    ] == ["sw12"]

    catalog_state = asset_library._load_project_catalog(
        catalog_root,
        asset_library._default_state(),
    )
    assert [item["name"] for item in catalog_state["projects"]] == ["ka8", "sw12"]
    assert catalog_state["project_id"] == ""

    sw12_state = asset_library._select_catalog_project(catalog_state, sw12)
    assert sw12_state["project_id"] == "sw12"
    assert len(sw12_state["assets"]) == 1
    assert sw12_state["assets"][0]["registered"] is True
    assert {
        "Custom",
        "Only Existing",
        "Only Existing/Nested",
    }.issubset(set(sw12_state["folders"]))
    assert all(
        node.get("folder_path") != "Character Appearance"
        for node in sw12_state["tree"]["children"]
    )
    sw12_state["expanded_folders"] = ["$root", "Custom", "Only Existing"]
    sw12_state["selected_folder_path"] = "Only Existing"
    sw12_state = asset_library._normalize_state(sw12_state)
    assert sw12_state["expanded_folders"] == [
        "$root",
        "Custom",
        "Only Existing",
    ]
    assert sw12_state["selected_folder_path"] == "Only Existing"
    collapsed_state = deepcopy(sw12_state)
    collapsed_state["expanded_folders"] = []
    assert asset_library._normalize_state(collapsed_state)["expanded_folders"] == []

    class FakeImageArtifact:
        def __init__(self, value: bytes, name: str):
            self.value = value
            self.name = name

    imported_value = FakeImageArtifact(PNG_1X1, "External_User.png")
    imported_state, media_by_uid = asset_library._merge_import_input(
        sw12_state,
        [imported_value],
    )
    imported = next(
        item
        for item in imported_state["assets"]
        if item["source_kind"] == "user"
    )
    assert imported["asset_project_uid"] == ""
    assert imported["relative_path"] == ""
    assert imported["path"] == ""
    assert imported["image_main_type"] == "Select Image Main Type"
    assert imported["image_sub_type"] == ""
    assert imported["source_type"] == "Role Required / Select Source Type"
    assert imported["custom_source_type"] == ""
    assert imported["scope_candidate"] == ""
    assert imported["color_pick_candidates"] == []
    assert imported["selected"] is True
    assert not (sw12 / "Custom" / "User Imports").exists()

    project_asset = next(
        item
        for item in imported_state["assets"]
        if item["source_kind"] == "project"
    )
    project_asset["selected"] = True
    project_asset["selection_order"] = 1
    imported["selection_order"] = 2
    imported_state = asset_library._normalize_state(imported_state)

    output = asset_library._build_output_payload(imported_state, media_by_uid)
    assert output["version"] == asset_library.OUTPUT_VERSION == 4
    assert [item["image_name"] for item in output["ordered_images"]] == [
        project_asset["image_name"],
        imported["image_name"],
    ]
    assert [item["selection_order"] for item in output["ordered_images"]] == [1, 2]
    assert all(
        set(item) == {"order_key", "image_name", "selection_order"}
        for item in output["ordered_images"]
    )
    assert len(output["verified_assets"]) == 1
    assert output["selected_assets"] == output["verified_assets"]
    verified = output["verified_assets"][0]
    assert verified["verified_asset"] is True
    assert verified["source_kind"] == "project"
    assert verified["asset_id"] == project_asset["asset_id"]
    assert verified["selection_order"] == 1
    assert output["imported_images"] == [output["ordered_images"][1]]
    forbidden_import_fields = {
        "asset_id",
        "asset_library_id",
        "asset_project_uid",
        "path",
        "relative_path",
        "source_type",
        "custom_source_type",
        "scope_candidate",
        "color_pick_candidates",
    }
    assert not (
        forbidden_import_fields & set(output["imported_images"][0])
    )
    media = asset_library._selected_media_values(imported_state, media_by_uid)
    assert len(media) == 2
    assert Path(str(media[0])).resolve() == project_a.resolve()
    assert media[1].startswith("data:image/")

    mixed_prompt = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        output,
        connected=True,
    )
    verified_row, imported_row = mixed_prompt["images"][:2]
    assert verified_row["asset_managed"] is True
    assert verified_row["asset_verified"] is True
    assert verified_row["asset_source_kind"] == "project"
    assert verified_row["asset_id"] == project_asset["asset_id"]
    assert verified_row["source_type"] == project_asset["source_type"]
    assert imported_row["asset_managed"] is True
    assert imported_row["asset_verified"] is False
    assert imported_row["asset_source_kind"] == "user"
    assert imported_row["label"] == imported["image_name"]
    assert imported_row["asset_id"] == ""
    assert imported_row["asset_path"] == ""
    assert imported_row["asset_library_id"] == ""
    assert imported_row["source_type"] == "Role Required / Select Source Type"
    assert imported_row["custom_source_type"] == ""
    assert imported_row["asset_scope_candidate"] == ""
    assert imported_row["asset_color_pick_candidates"] == []
    assert mixed_prompt["image_asset"]["selected_assets"] == 2
    assert mixed_prompt["image_asset"]["verified_assets"] == 1
    assert mixed_prompt["image_asset"]["imported_images"] == 1

    # External rows behave like native Prompt rows for identity/taxonomy
    # editing while their physical generator order remains upstream-managed.
    imported_row["label"] = "Editable external name"
    imported_row["image_main_type"] = "Character Prop"
    imported_row["image_sub_type"] = "Handheld Prop"
    reapplied_mixed = prompt_library._apply_image_asset_payload(
        mixed_prompt,
        output,
        connected=True,
    )
    reapplied_import = next(
        item
        for item in reapplied_mixed["images"]
        if item["asset_source_kind"] == "user"
    )
    assert reapplied_import["label"] == "Editable external name"
    assert reapplied_import["image_main_type"] == "Character Prop"
    assert reapplied_import["image_sub_type"] == "Handheld Prop"
    assert reapplied_import["source_type"] == "Prop / Accessory"
    assert reapplied_import["asset_id"] == ""
    assert prompt_library._picker_match_candidates(
        reapplied_mixed["images"],
        {"asset_id": "Editable external name"},
        set(),
    ) == []

    forged_unknown = payload_row("Forged", 1)
    forged_unknown.pop("source_kind")
    forged_prompt = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        {
            "schema": "hmb-image-asset-library-binding",
            "version": 3,
            "mode": "image_asset",
            "project_id": "sw12",
            "project_uid": "sw12:test",
            "project_root": "C:/Project/sw12",
            "ordered_images": [forged_unknown],
        },
        connected=True,
    )
    forged_row = forged_prompt["images"][0]
    assert forged_row["label"] == "Forged"
    assert forged_row["asset_managed"] is True
    assert forged_row["asset_verified"] is False
    assert forged_row["asset_id"] == ""
    assert forged_row["source_type"] == "Role Required / Select Source Type"
    assert forged_row["custom_source_type"] == ""

    # Unknown legacy classification remains authored context instead of being
    # discarded by taxonomy normalization.
    future_type_payload = payload(["FutureType"])
    future_type_payload["ordered_images"][0].pop("image_main_type", None)
    future_type_payload["ordered_images"][0].pop("image_sub_type", None)
    future_type_payload["ordered_images"][0]["source_type"] = "Future Asset Type"
    future_type_payload["ordered_images"][0]["custom_source_type"] = "Future Asset Type"
    future_type_prompt = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        future_type_payload,
        connected=True,
    )
    future_type_row = future_type_prompt["images"][0]
    assert future_type_row["image_main_type"] == ""
    assert future_type_row["image_sub_type"] == ""
    assert future_type_row["source_type"] == "Role Required / Select Source Type"
    assert future_type_row["custom_source_type"] == "Future Asset Type"

    cleared_import_state = asset_library._remove_live_imports(imported_state)
    assert not any(
        item["source_kind"] == "user" and item["import_index"] > 0
        for item in cleared_import_state["assets"]
    )
    cleared_output = asset_library._build_output_payload(cleared_import_state)
    assert [item["image_name"] for item in cleared_output["ordered_images"]] == [
        project_asset["image_name"],
    ]
    assert cleared_output["imported_images"] == []

    # External imports are ordinary connected media, independent of which
    # verified Project catalog entry is active.
    ka8_state = asset_library._select_catalog_project(imported_state, ka8)
    assert ka8_state["project_id"] == "ka8"
    assert not any(
        item["source_kind"] == "project"
        for item in ka8_state["assets"]
    )
    ka8_import = next(
        item
        for item in ka8_state["assets"]
        if item["source_kind"] == "user"
    )
    assert ka8_import["source_uid"] == imported["source_uid"]
    assert ka8_import["asset_project_uid"] == ""

    # Selection compaction enforces the library's 50-reference limit.
    limit_state = asset_library._default_state()
    limit_state["assets"] = [
        {
            **payload_row(f"L{index:02d}", index),
            "source_kind": "project",
            "registered": True,
            "image_name": f"L{index:02d}",
            "selected": True,
        }
        for index in range(1, 54)
    ]
    limit_state = asset_library._normalize_state(limit_state)
    assert sum(bool(item["selected"]) for item in limit_state["assets"]) == 50
    assert [
        item["selection_order"]
        for item in limit_state["assets"]
        if item["selected"]
    ] == list(range(1, 51))

    # Establish three managed rows, author freely editable Target/Color fields,
    # then reorder upstream. Registered Sub Type remains authoritative while the
    # complete rows move and textual @image references remap simultaneously.
    prompt_state = prompt_library._default_widget_state()
    normalized_before_asset = prompt_library._normalize_state(prompt_state)
    inactive_videos_before_asset = deepcopy(normalized_before_asset["videos"])
    picker_before_asset = deepcopy(normalized_before_asset["picker"])
    prompt_state = prompt_library._apply_image_asset_payload(
        prompt_state,
        payload(["A", "B", "C"]),
        connected=True,
    )
    # ASSET_IN owns verified image identity/order/taxonomy. Connecting it while
    # @video1 is inactive must not activate Video Picker state or synthesize a
    # video row.
    assert prompt_state["videos"] == inactive_videos_before_asset
    assert prompt_state["picker"] == picker_before_asset
    prompt_state["videos"][0].update(
        {
            "present": True,
            "label": "shot_playblast",
            "source_type": "Maya Preview / Playblast",
            "control_role": "Primary Unified Shot Control",
        }
    )
    expected_final = {}
    scopes = ["Head / face only", "Handheld prop", "Main background"]
    colors = ["Red", "Green", "Blue"]
    for index, row in enumerate(prompt_state["images"][:3]):
        row["owner"] = row["label"]
        row["binding_scopes"] = [scopes[index]]
        row["scope"] = scopes[index]
        row["color_picks"] = [colors[index]]
        expected_final[row["label"]] = {
            "owner": row["owner"],
            "binding_scopes": [scopes[index]],
            "color_picks": list(row["color_picks"]),
        }
    prompt_state["text"]["SCENE_CONTEXT"] = "Use @image1 with @image3."
    prompt_state["text"]["PRESERVED_TEXT"] = "[On-screen Text] literal @image1 and @image3"
    prompt_state["videos"][0]["keep_out"] = "Do not copy @image2 artifacts."

    reordered = prompt_library._apply_image_asset_payload(
        prompt_state,
        payload(["C", "A", "B"]),
        connected=True,
    )
    assert [item["label"] for item in reordered["images"][:3]] == ["C", "A", "B"]
    for row in reordered["images"][:3]:
        assert {
            "owner": row["owner"],
            "binding_scopes": row["binding_scopes"],
            "color_picks": row["color_picks"],
        } == expected_final[row["label"]], (
            row["label"],
            {
                "owner": row["owner"],
                "binding_scopes": row["binding_scopes"],
                "color_picks": row["color_picks"],
            },
            expected_final[row["label"]],
        )
    assert reordered["text"]["SCENE_CONTEXT"] == "Use @image2 with @image1."
    assert reordered["text"]["PRESERVED_TEXT"] == "[On-screen Text] literal @image1 and @image3"
    assert reordered["videos"][0]["keep_out"] == "Do not copy @image3 artifacts."
    assert reordered["image_asset"]["order_managed"] is True
    assert reordered["image_asset"]["ordered_source_uids"] == [
        "source:C",
        "source:A",
        "source:B",
    ]

    # Reapplying the same selection is idempotent.
    repeated = prompt_library._apply_image_asset_payload(
        reordered,
        payload(["C", "A", "B"]),
        connected=True,
    )
    assert repeated == reordered

    # Registered Look provenance remains source-owned. Retired pre-v2 Sub Type
    # text is released; refresh restores only the registered current Sub Type.
    look_state = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        look_payload(),
        connected=True,
    )
    assert look_state["images"][0]["image_sub_type"] == "Color Mood"
    assert look_state["images"][0]["owner"] == "Master Look"
    assert look_state["images"][0]["asset_default_target"] == "Master Look"

    render_style_state = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        look_payload("Render Style"),
        connected=True,
    )
    assert render_style_state["images"][0]["owner"] == "Master Look"
    assert render_style_state["images"][0]["asset_default_target"] == "Master Look"

    camera_state = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        look_payload("Camera / Composition"),
        connected=True,
    )
    assert camera_state["images"][0]["owner"] == "Global Look"
    assert camera_state["images"][0]["asset_default_target"] == "Global Look"

    subtypeless_state = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        look_payload(""),
        connected=True,
    )
    assert subtypeless_state["images"][0]["owner"] == ""
    assert subtypeless_state["images"][0]["asset_default_target"] == ""

    look_state["images"][0]["image_sub_type"] = "Scale"
    look_state["images"][0]["owner"] = "Director Camera"
    prompt_library._normalize_image_binding_fields(look_state["images"][0])
    refreshed_look = prompt_library._apply_image_asset_payload(
        look_state,
        look_payload(),
        connected=True,
    )
    refreshed_look_row = refreshed_look["images"][0]
    assert refreshed_look_row["asset_image_sub_type_candidate"] == "Color Mood"
    assert refreshed_look_row["image_sub_type"] == "Scale"
    assert refreshed_look_row["source_type"] == "Role Required / Select Source Type"
    assert refreshed_look_row["scope"] == ""
    assert refreshed_look_row["owner"] == "Director Camera"

    changed_registered_look = prompt_library._apply_image_asset_payload(
        refreshed_look,
        look_payload("Render Style"),
        connected=True,
    )
    assert changed_registered_look["images"][0][
        "asset_image_sub_type_candidate"
    ] == "Render Style"
    assert changed_registered_look["images"][0]["image_sub_type"] == "Scale"
    assert changed_registered_look["images"][0]["owner"] == "Director Camera"

    dormant_look = prompt_library._apply_image_asset_payload(
        changed_registered_look,
        {
            "schema": "hmb-image-asset-library-binding",
            "version": 2,
            "mode": "image_asset",
            "project_id": "sw12",
            "project_uid": "sw12:test",
            "project_root": "C:/Project/sw12",
            "selection_id": "look-empty",
            "selected_assets": [],
            "ordered_images": [],
        },
        connected=True,
    )
    cached_look = next(
        item
        for item in dormant_look["image_asset"]["dormant_asset_rows"]
        if item["asset_source_uid"] == "source:MasterLook"
    )
    assert cached_look["image_sub_type"] == "Scale"
    assert cached_look["owner"] == "Director Camera"
    restored_look = prompt_library._apply_image_asset_payload(
        dormant_look,
        look_payload("Render Style"),
        connected=True,
    )
    assert restored_look["images"][0]["image_sub_type"] == "Scale"
    assert restored_look["images"][0]["owner"] == "Director Camera"

    # Lighting-bearing Look rows default to Global Look and expose Custom as a
    # reserved shared-scope mode. The authored instruction must survive source
    # refresh, deselection into the dormant cache, and exact-UID reconnect.
    lighting_state = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        look_payload("Lighting / Atmosphere"),
        connected=True,
    )
    assert lighting_state["images"][0]["owner"] == "Global Look"
    lighting_state["images"][0]["owner"] = "Custom"
    lighting_state["images"][0]["look_custom_instruction"] = (
        "Use dawn lighting globally, with a readable foreground."
    )
    prompt_library._normalize_image_binding_fields(lighting_state["images"][0])
    refreshed_lighting = prompt_library._apply_image_asset_payload(
        lighting_state,
        look_payload("Lighting / Atmosphere"),
        connected=True,
    )
    assert refreshed_lighting["images"][0]["owner"] == "Custom"
    assert refreshed_lighting["images"][0]["look_custom_instruction"] == (
        "Use dawn lighting globally, with a readable foreground."
    )
    dormant_lighting = prompt_library._apply_image_asset_payload(
        refreshed_lighting,
        {
            "schema": "hmb-image-asset-library-binding",
            "version": 2,
            "mode": "image_asset",
            "project_id": "sw12",
            "project_uid": "sw12:test",
            "project_root": "C:/Project/sw12",
            "selection_id": "look-lighting-empty",
            "selected_assets": [],
            "ordered_images": [],
        },
        connected=True,
    )
    cached_lighting = next(
        item
        for item in dormant_lighting["image_asset"]["dormant_asset_rows"]
        if item["asset_source_uid"] == "source:MasterLook"
    )
    assert cached_lighting["owner"] == "Custom"
    assert cached_lighting["look_custom_instruction"] == (
        "Use dawn lighting globally, with a readable foreground."
    )
    restored_lighting = prompt_library._apply_image_asset_payload(
        dormant_lighting,
        look_payload("Lighting / Atmosphere"),
        connected=True,
    )
    assert restored_lighting["images"][0]["owner"] == "Custom"
    assert restored_lighting["images"][0]["look_custom_instruction"] == (
        "Use dawn lighting globally, with a readable foreground."
    )

    # Returning from a retired Scale label to a general Look preserves the
    # authored Target through source refresh, dormant cache, and restore.
    returned_general = deepcopy(restored_look)
    returned_general["images"][0]["image_sub_type"] = "Color Mood"
    prompt_library._normalize_image_binding_fields(returned_general["images"][0])
    assert returned_general["images"][0]["owner"] == "Director Camera"
    assert returned_general["images"][0]["asset_default_target"] == ""
    refreshed_general = prompt_library._apply_image_asset_payload(
        returned_general,
        look_payload("Render Style"),
        connected=True,
    )
    assert refreshed_general["images"][0]["image_sub_type"] == "Color Mood"
    assert refreshed_general["images"][0]["owner"] == "Director Camera"
    assert refreshed_general["images"][0]["asset_default_target"] == "Master Look"
    dormant_general = prompt_library._apply_image_asset_payload(
        refreshed_general,
        {
            "schema": "hmb-image-asset-library-binding",
            "version": 2,
            "mode": "image_asset",
            "project_id": "sw12",
            "project_uid": "sw12:test",
            "project_root": "C:/Project/sw12",
            "selection_id": "look-general-empty",
            "selected_assets": [],
            "ordered_images": [],
        },
        connected=True,
    )
    cached_general = next(
        item
        for item in dormant_general["image_asset"]["dormant_asset_rows"]
        if item["asset_source_uid"] == "source:MasterLook"
    )
    assert cached_general["image_sub_type"] == "Color Mood"
    assert cached_general["owner"] == "Director Camera"
    restored_general = prompt_library._apply_image_asset_payload(
        dormant_general,
        look_payload("Render Style"),
        connected=True,
    )
    assert restored_general["images"][0]["image_sub_type"] == "Color Mood"
    assert restored_general["images"][0]["owner"] == "Director Camera"

    # Target is Prompt-owned for every verified Main Type. A source rename
    # updates only the suggested default and never overwrites the authored value.
    character_state = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        character_payload("Hero Old"),
        connected=True,
    )
    assert character_state["images"][0]["owner"] == "Hero Old"
    renamed_character = prompt_library._apply_image_asset_payload(
        character_state,
        character_payload("Hero New"),
        connected=True,
    )
    assert renamed_character["images"][0]["owner"] == "Hero Old"
    assert renamed_character["images"][0]["asset_default_target"] == "Hero New"
    renamed_character["images"][0]["owner"] = "Hero Custom Target"
    authored_character = prompt_library._apply_image_asset_payload(
        renamed_character,
        character_payload("Hero Final"),
        connected=True,
    )
    assert authored_character["images"][0]["owner"] == "Hero Custom Target"
    assert authored_character["images"][0]["asset_default_target"] == "Hero Final"

    # A shorter connected selection removes the deselected managed row. Tokens
    # that pointed to it become tombstones instead of silently rebinding.
    deselected_b = prompt_library._apply_image_asset_payload(
        reordered,
        payload(["C", "A"]),
        connected=True,
    )
    assert [item["label"] for item in deselected_b["images"][:2]] == ["C", "A"]
    assert "B" not in [
        item["label"] for item in deselected_b["images"] if item["asset_managed"]
    ]
    assert "B" not in [item["label"] for item in deselected_b["images"]]
    assert "@image3" not in deselected_b["videos"][0]["keep_out"]
    assert "[deselected image source #3]" in deselected_b["videos"][0]["keep_out"]
    assert deselected_b["text"]["PRESERVED_TEXT"] == "[On-screen Text] literal @image1 and @image3"
    cached_b = next(
        item
        for item in deselected_b["image_asset"]["dormant_asset_rows"]
        if item["asset_source_uid"] == "source:B"
    )
    assert {
        "owner": cached_b["owner"],
        "binding_scopes": cached_b["binding_scopes"],
        "color_picks": cached_b["color_picks"],
    } == expected_final["B"]
    reselected_b = prompt_library._apply_image_asset_payload(
        deselected_b,
        payload(["C", "A", "B"]),
        connected=True,
    )
    restored_b = next(
        item for item in reselected_b["images"] if item["label"] == "B"
    )
    assert {
        "owner": restored_b["owner"],
        "binding_scopes": restored_b["binding_scopes"],
        "color_picks": restored_b["color_picks"],
    } == expected_final["B"]

    # A readable-name collision may never override stable source identity.
    collision_old = prompt_library._apply_image_asset_payload(
        prompt_library._default_widget_state(),
        payload(["Collision"]),
        connected=True,
    )
    collision_old["images"][0]["owner"] = "old-source-only target"
    collision_new_payload = deepcopy(payload(["Collision"]))
    for row in collision_new_payload["ordered_images"]:
        row["source_uid"] = "source:Collision-new"
        row["asset_library_id"] = "library:Collision-new"
        row["asset_id"] = "Asset_Collision_new"
    for row in collision_new_payload["selected_assets"]:
        row["source_uid"] = "source:Collision-new"
        row["asset_library_id"] = "library:Collision-new"
        row["asset_id"] = "Asset_Collision_new"
    collision_new = prompt_library._apply_image_asset_payload(
        collision_old,
        collision_new_payload,
        connected=True,
    )
    assert collision_new["images"][0]["asset_source_uid"] == "source:Collision-new"
    assert collision_new["images"][0]["owner"] != "old-source-only target"
    assert next(
        item
        for item in collision_new["image_asset"]["dormant_asset_rows"]
        if item["asset_source_uid"] == "source:Collision"
    )["owner"] == "old-source-only target"

    # Strict upstream ownership must never capture a manual row merely because
    # its label matches, or because its label is blank while other authored
    # fields give the row meaning.
    manual_state = prompt_library._default_widget_state()
    manual_named = prompt_library._default_image_item(1)
    manual_named.update(
        {
            "present": True,
            "label": "Hero",
            "owner": "manual named target",
            "image_main_type": "Character",
            "image_sub_type": "Full Appearance",
            "source_type": "Character Appearance",
        }
    )
    manual_blank_label = prompt_library._default_image_item(2)
    manual_blank_label.update(
        {
            "present": True,
            "owner": "manual owner-only target",
            "image_main_type": "Custom / Context",
            "image_sub_type": "Custom",
            "source_type": "Custom",
            "custom_source_type": "Unnamed manual concept",
        }
    )
    manual_state["images"] = [manual_named, manual_blank_label]
    selected_hero = prompt_library._apply_image_asset_payload(
        manual_state,
        payload(["Hero"]),
        connected=True,
    )
    assert sum(bool(item["asset_managed"]) for item in selected_hero["images"]) == 1
    assert selected_hero["images"][0]["owner"] == "manual named target"
    assert {
        item["owner"]
        for item in selected_hero["image_asset"]["dormant_manual_rows"]
        if item["owner"]
    } == {"manual owner-only target"}
    # PROMPT_OUT is now the concise operator-facing source map.  Assert the
    # exact structured contract through the private Agent-paired envelope.
    selected_prompt = prompt_library._build_data_only_prompt_package(selected_hero)
    selected_lines = selected_prompt.splitlines()
    assert len(selected_lines) == 7
    selected_job = json.loads(
        selected_lines[selected_lines.index("HMB JOB DATA (JSON):") + 1]
    )
    assert [(item["image"], item["label"]) for item in selected_job["images"]] == [
        ("@image1", "Hero"),
    ]
    assert selected_job["images"][0]["target_id"] == "manual named target"
    assert all(
        item.get("target_id") != "manual owner-only target"
        for item in selected_job["images"]
    )

    # A stale or forced frontend value cannot create a visible manual row while
    # ASSET_IN is connected. Preserve it only in the dormant cache so disconnect
    # remains lossless.
    forged_connected = deepcopy(selected_hero)
    forged_manual = prompt_library._default_image_item(2)
    forged_manual.update(
        {
            "present": True,
            "manual": True,
            "label": "FORGED_MANUAL",
            "owner": "forced click target",
            "image_main_type": "Custom / Context",
            "image_sub_type": "Custom",
            "source_type": "Custom",
            "custom_source_type": "Forced stale UI row",
        }
    )
    forged_connected["images"].append(forged_manual)
    forged_sanitized = prompt_library._apply_image_asset_payload(
        forged_connected,
        payload(["Hero"]),
        connected=True,
    )
    assert "FORGED_MANUAL" not in [
        item["label"] for item in forged_sanitized["images"]
    ]
    assert "FORGED_MANUAL" in [
        item["label"]
        for item in forged_sanitized["image_asset"]["dormant_manual_rows"]
    ]
    forged_released = prompt_library._apply_image_asset_payload(
        forged_sanitized,
        {},
        connected=False,
    )
    assert forged_released["image_asset"]["enabled"] is False
    assert "FORGED_MANUAL" in [
        item["label"] for item in forged_released["images"]
    ]

    deselected_hero = prompt_library._apply_image_asset_payload(
        selected_hero,
        payload([]),
        connected=True,
    )
    assert not any(item["asset_managed"] for item in deselected_hero["images"])
    assert {
        item["owner"]
        for item in deselected_hero["image_asset"]["dormant_manual_rows"]
        if item["owner"]
    } == {"manual owner-only target"}
    cached_hero = next(
        item
        for item in deselected_hero["image_asset"]["dormant_asset_rows"]
        if item["asset_source_uid"] == "source:Hero"
    )
    assert cached_hero["owner"] == "manual named target"

    # On initial connection, two explicit but different Asset IDs override a
    # same-label fallback and keep the manual row dormant.
    id_collision_state = prompt_library._default_widget_state()
    id_collision_state["images"] = [{
        **prompt_library._default_image_item(1),
        "present": True,
        "label": "Hero",
        "asset_id": "Manual_Hero_ID",
        "owner": "manual ID target",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "source_type": "Character Appearance",
    }]
    id_collision = prompt_library._apply_image_asset_payload(
        id_collision_state,
        payload(["Hero"]),
        connected=True,
    )
    assert id_collision["images"][0]["asset_id"] == "Asset_Hero"
    assert id_collision["images"][0]["owner"] != "manual ID target"
    assert id_collision["image_asset"]["dormant_manual_rows"][0]["owner"] == "manual ID target"

    # Disconnected inputs preserve current rows, final Prompt choices, text,
    # and video state, while returning their rows to native/manual control.
    before_disconnect = deepcopy(deselected_b)
    disconnected = prompt_library._apply_image_asset_payload(
        deselected_b,
        {},
        connected=False,
    )
    assert [
        item["label"] for item in disconnected["images"] if item["label"]
    ] == [
        item["label"] for item in before_disconnect["images"] if item["label"]
    ]
    assert disconnected["videos"] == before_disconnect["videos"]
    assert disconnected["image_asset"]["enabled"] is False
    assert not any(item["asset_managed"] for item in disconnected["images"])

    native_state = prompt_library._normalize_state(
        prompt_library._default_widget_state()
    )
    native_images = deepcopy(native_state["images"])
    native_videos = deepcopy(native_state["videos"])
    native_text = deepcopy(native_state["text"])
    no_asset_input = prompt_library._apply_image_asset_payload(
        native_state,
        {},
        connected=False,
    )
    assert no_asset_input["images"] == native_images
    assert no_asset_input["videos"] == native_videos
    assert no_asset_input["text"] == native_text

    no_picker_input = prompt_library._apply_picker_payload(
        native_state,
        {},
        connected=False,
    )
    assert no_picker_input["images"] == native_images
    assert no_picker_input["videos"] == native_videos
    assert no_picker_input["text"] == native_text

    node = asset_library.HMBImageAssetLibrary(
        name="image_asset_import_contract",
    )
    # This unit node is intentionally not registered with a retained-mode
    # NodeManager. An installed host may already own an Engine singleton, so
    # make the fixture's identity explicit while exercising its async scanner.
    node._scan_owner_is_current = lambda: True
    for parameter_name in (
        asset_library.IMAGE_IMPORT_PARAMETER,
        asset_library.OUTPUT_PARAMETER,
        asset_library.MEDIA_OUTPUT_PARAMETER,
        asset_library.PROJECT_ROOT_PARAMETER,
    ):
        assert asset_library.parameter_exists(node, parameter_name)
    assert asset_library.MEDIA_OUTPUT_PARAMETER == "IMAGE_OUT"
    assert not asset_library.parameter_exists(node, "IMAGE_MEDIA_OUT")
    expected_projects_root = os.environ.get(
        "HMB_IMAGE_PROJECTS_ROOT",
        r"\\fin-rcomp1\Composite_Team\projects_AI",
    )
    assert str(asset_library.DEFAULT_PROJECTS_ROOT) == expected_projects_root
    assert asset_library._default_state()["catalog_root"] == expected_projects_root.replace(
        "\\", "/"
    )
    custom_catalog_root = "//artist-server/custom-projects"
    assert (
        asset_library._normalize_state({"catalog_root": custom_catalog_root})[
            "catalog_root"
        ]
        == custom_catalog_root
    )
    assert asset_library.ASSET_NODE_WIDTH == 1400
    assert asset_library.ASSET_NODE_HEIGHT == 1200
    assert node.width == 1400
    assert node.height == 1200
    assert node.metadata["size"] == {"width": 1400, "height": 1200}
    resized_node = asset_library.HMBImageAssetLibrary(
        name="image_asset_manual_size_restore",
        metadata={"size": {"width": 1120, "height": 880}},
    )
    assert resized_node.metadata["size"] == {"width": 1120, "height": 880}
    widget_state_parameter = asset_library._get_parameter_obj(
        node,
        asset_library.WIDGET_STATE_PARAMETER,
    )
    assert widget_state_parameter.ui_options["width"] == 1400
    assert widget_state_parameter.ui_options["height"] == 1200
    asset_output_parameter = asset_library._get_parameter_obj(
        node,
        asset_library.OUTPUT_PARAMETER,
    )
    # Cable-free Shot routing keeps legacy metadata/media ports callable while
    # removing their visible handles from the node chrome.
    assert asset_output_parameter.ui_options.get("display_name") == ""
    assert asset_output_parameter.ui_options.get("hide_property") is True
    assert asset_output_parameter.ui_options.get("hide") is True
    assert asset_output_parameter.ui_options.get("hide_handles") is True
    assert asset_output_parameter.ui_options.get("is_full_width") is True
    media_parameter = asset_library._get_parameter_obj(
        node,
        asset_library.MEDIA_OUTPUT_PARAMETER
    )
    assert media_parameter.output_type == "list[str]"
    assert media_parameter.ui_options.get("display_name") == ""
    assert media_parameter.ui_options.get("hide_property") is True
    assert media_parameter.ui_options.get("hide") is True
    assert media_parameter.ui_options.get("hide_handles") is True
    image_asset_input = prompt_library._image_asset_input_kwargs()
    assert image_asset_input["name"] == "IMAGE_ASSET_IN"
    assert image_asset_input["ui_options"]["display_name"] == ""
    assert image_asset_input["ui_options"]["hide_property"] is True
    assert image_asset_input["ui_options"]["hide"] is True
    assert image_asset_input["ui_options"]["hide_handles"] is True
    asset_output_parameter.hide_property = False
    asset_output_parameter.ui_options["display_name"] = "IMAGE_ASSET_OUT"
    asset_output_parameter.ui_options["hide_property"] = False
    media_parameter.hide_property = False
    media_parameter.ui_options["display_name"] = "IMAGE_OUT"
    media_parameter.ui_options["hide_property"] = False
    node._ensure_parameters()
    assert asset_output_parameter.hide_property is True
    assert asset_output_parameter.ui_options["display_name"] == ""
    assert asset_output_parameter.ui_options["hide_property"] is True
    assert asset_output_parameter.ui_options["hide"] is True
    assert asset_output_parameter.ui_options["hide_handles"] is True
    assert media_parameter.hide_property is True
    assert media_parameter.ui_options["display_name"] == ""
    assert media_parameter.ui_options["hide"] is True
    assert media_parameter.ui_options["hide_handles"] is True
    prompt_node = prompt_library.HMBPromptLibrary(
        name="prompt_asset_port_contract",
    )
    prompt_asset_input_parameter = prompt_library._get_parameter_obj(
        prompt_node,
        prompt_library.IMAGE_ASSET_INPUT_PARAMETER_NAME,
    )
    prompt_asset_input_parameter.hide_property = False
    prompt_asset_input_parameter.ui_options["display_name"] = "IMAGE_ASSET_IN"
    prompt_asset_input_parameter.ui_options["hide_property"] = False
    prompt_node._ensure_prompt_output()
    assert prompt_asset_input_parameter.hide_property is True
    assert prompt_asset_input_parameter.ui_options["display_name"] == ""
    assert prompt_asset_input_parameter.ui_options["hide_property"] is True
    assert prompt_asset_input_parameter.ui_options["hide"] is True
    assert prompt_asset_input_parameter.ui_options["hide_handles"] is True
    if asset_library.ParameterList is not None:
        import_parameter = asset_library._get_parameter_obj(
            node,
            asset_library.IMAGE_IMPORT_PARAMETER
        )
        expected_import_types = [
            "list[ImageUrlArtifact]",
            "list[ImageArtifact]",
            "list[str]",
        ]
        # Griptape 0.98 additionally advertises the ParameterList aggregate as
        # generic ``list``; older/current clean-CI doubles expose only the three
        # typed aggregates. Both surfaces preserve the same accepted media.
        assert import_parameter.input_types in (
            expected_import_types,
            [*expected_import_types, "list"],
        )
        assert getattr(import_parameter, "_collapsed", None) is True
        assert getattr(import_parameter, "_max_items", None) == 50
        assert import_parameter.ui_options.get("collapsed") is True
    if real_catalog_root.is_dir():
        node_state = node._load_catalog(real_catalog_root)
        assert isinstance(node_state["projects"], list)
        node_output = json.loads(
            node.parameter_output_values[asset_library.OUTPUT_PARAMETER]
        )
        assert node_output["selected_assets"] == []
        assert node.parameter_output_values[asset_library.MEDIA_OUTPUT_PARAMETER] == []

    # ParameterList disconnects remove one edge at a time.  The post-removal
    # hook must rebuild imports from the framework's remaining aggregate rather
    # than clearing every connected image.
    import_a = FakeImageArtifact(PNG_1X1 + b"A", "Disconnect_A.png")
    import_b = FakeImageArtifact(PNG_1X1 + b"B", "Disconnect_B.png")
    node._apply_import_value([import_a, import_b])
    assert [
        item["image_name"]
        for item in node._current_state()["assets"]
        if item["source_kind"] == "user"
    ] == ["Disconnect_A", "Disconnect_B"]
    target_parameter = SimpleNamespace(name=asset_library.IMAGE_IMPORT_PARAMETER)
    # A real registered ParameterList exposes the post-removal aggregate from
    # its root.  This isolated unit node is intentionally not registered with
    # the retained-mode engine, so emulate only that root read while allowing
    # every other state/parameter read to use the real helper.
    original_get_parameter_raw = asset_library._get_parameter_raw
    simulated_import_aggregate = [import_b]

    def simulated_get_parameter_raw(candidate_node, parameter_name):
        if (
            candidate_node is node
            and parameter_name == asset_library.IMAGE_IMPORT_PARAMETER
        ):
            return simulated_import_aggregate
        return original_get_parameter_raw(candidate_node, parameter_name)

    asset_library._get_parameter_raw = simulated_get_parameter_raw
    try:
        node.after_incoming_connection_removed(
            SimpleNamespace(),
            SimpleNamespace(name="IMAGE_OUT"),
            target_parameter,
        )
        remaining_imports = [
            item
            for item in node._current_state()["assets"]
            if item["source_kind"] == "user"
        ]
        assert [item["image_name"] for item in remaining_imports] == ["Disconnect_B"]
        assert len(node.parameter_output_values[asset_library.MEDIA_OUTPUT_PARAMETER]) == 1
        remaining_payload = json.loads(
            node.parameter_output_values[asset_library.OUTPUT_PARAMETER]
        )
        assert [
            item["image_name"] for item in remaining_payload["imported_images"]
        ] == ["Disconnect_B"]

        simulated_import_aggregate = []
        node.after_incoming_connection_removed(
            SimpleNamespace(),
            SimpleNamespace(name="IMAGE_OUT"),
            target_parameter,
        )
    finally:
        asset_library._get_parameter_raw = original_get_parameter_raw
    assert not any(
        item["source_kind"] == "user"
        for item in node._current_state()["assets"]
    )
    assert node.parameter_output_values[asset_library.MEDIA_OUTPUT_PARAMETER] == []
    assert asset_library._project_root_text(
        {"value": "file:///C:/Project"}
    ).replace("\\", "/") == "C:/Project"

    asset_library._set_parameter_value(
        node,
        asset_library.PROJECT_ROOT_PARAMETER,
        str(catalog_root),
    )
    valid_state = node._load_catalog(catalog_root)
    assert valid_state["asset_view_mode"] == "image"
    selected_state = deepcopy(valid_state)
    selected_state["project_root"] = str(sw12).replace("\\", "/")
    selected_state["project_uid"] = ""
    selected_state["root_edit_enabled"] = False
    selected_state["language"] = "ko"
    selected_state["asset_view_mode"] = "detail"
    folders_before_selection = sorted(
        path.relative_to(sw12).as_posix()
        for path in sw12.rglob("*")
        if path.is_dir()
    )
    selected_state = apply_widget_state_and_wait(node, selected_state)
    assert selected_state["project_id"] == "sw12"
    assert selected_state["language"] == "ko"
    assert selected_state["asset_view_mode"] == "detail"
    assert sorted(
        path.relative_to(sw12).as_posix()
        for path in sw12.rglob("*")
        if path.is_dir()
    ) == folders_before_selection, "Project selection must not create taxonomy folders."
    added_after_load = sw12 / "Custom" / "Added_After_Load.png"
    added_after_load.write_bytes(PNG_1X1)
    refresh_state = deepcopy(selected_state)
    refresh_state["refresh_revision"] += 1
    refreshed = apply_widget_state_and_wait(node, refresh_state)
    assert refreshed["asset_view_mode"] == "detail"
    assert "Added_After_Load" in {
        item["image_name"] for item in refreshed["assets"]
    }
    assert refreshed["root_edit_enabled"] is False
    assert Path(
        asset_library._get_parameter_raw(
            node,
            asset_library.PROJECT_ROOT_PARAMETER,
        )
    ).resolve() == catalog_root.resolve()
    node.after_deserialize()
    restored = node._current_state()
    assert Path(restored["catalog_root"]).resolve() == catalog_root.resolve()
    assert restored["root_edit_enabled"] is False
    assert restored["project_id"] == "sw12"
    assert restored["language"] == "ko"
    assert restored["asset_view_mode"] == "detail"
    workflow_only_state = deepcopy(restored)
    workflow_only_state["project_root"] = str(ka8).replace("\\", "/")
    workflow_only_state["project_uid"] = ""
    workflow_only_state = apply_widget_state_and_wait(node, workflow_only_state)
    assert workflow_only_state["project_id"] == "ka8"
    assert workflow_only_state["asset_view_mode"] == "detail"
    node.after_deserialize()
    assert node._current_state()["project_id"] == "ka8"
    assert not (catalog_root / "HMBImageAssetLibrary.project-set.json").exists()
    invalid_state = deepcopy(valid_state)
    invalid_state["catalog_root"] = str(catalog_root / "missing-root")
    rejected = apply_widget_state_and_wait(node, invalid_state)
    assert Path(rejected["catalog_root"]).resolve() == catalog_root.resolve()
    assert "does not exist" in rejected["error"]
finally:
    shutil.rmtree(catalog_root, ignore_errors=True)


# Host aggregates may contain self-references or excessively deep wrapper values.
# They must terminate deterministically instead of exhausting Python recursion.
cyclic_import = []
cyclic_import.append(cyclic_import)
assert asset_library._flatten_import_values(cyclic_import) == []
cyclic_root = {}
cyclic_root["value"] = cyclic_root
assert asset_library._project_root_text(cyclic_root) == ""
deep_root = "C:/deep/project"
for _index in range(asset_library.MAX_INPUT_NESTING + 100):
    deep_root = {"value": deep_root}
assert asset_library._project_root_text(deep_root) == ""

previous_total_budget = asset_library.MAX_IMPORT_TOTAL_BYTES
asset_library.MAX_IMPORT_TOTAL_BYTES = 8
try:
    try:
        asset_library._normalize_import_input([b"12345", b"67890"], [])
    except ValueError as exc:
        assert "Combined IMAGE_IMPORT_IN" in str(exc)
    else:
        raise AssertionError("Combined import media must honor the configurable safety budget.")
finally:
    asset_library.MAX_IMPORT_TOTAL_BYTES = previous_total_budget

exr_header = (
    b"\x76\x2f\x31\x01\x02\x00\x00\x00"
    + b"dataWindow\0box2i\0"
    + (16).to_bytes(4, "little")
    + (0).to_bytes(4, "little", signed=True)
    + (0).to_bytes(4, "little", signed=True)
    + (1919).to_bytes(4, "little", signed=True)
    + (1079).to_bytes(4, "little", signed=True)
    + b"\0"
)
assert asset_library._exr_header_dimensions(exr_header) == (1920, 1080)


print(
    "HMB Project Root catalog + IMAGE_IMPORT_IN + ordered IMAGE_OUT + "
    "Prompt @image synchronization/no-input preservation regression: PASS"
)
