from __future__ import annotations

import copy
import importlib.util
import json
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


def expect_rejected(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("invalid image taxonomy authority was accepted")


def replace_job(package: str, job: dict) -> str:
    lines = package.splitlines()
    assert lines[1] == prompt.PUBLIC_JOB_CONTRACT_HEADER
    lines[2] = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
    return "\n".join(lines)

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

exact_taxonomy_records: set[tuple[str, str, str, str, str]] = set()
visible_documents: set[str] = set()
semantic_fingerprints: set[str] = set()
packages_by_taxonomy: dict[tuple[str, str], tuple[str, dict]] = {}

for (main_type, sub_type), wire_pair in prompt.IMAGE_TAXONOMY_WIRE_MAP.items():
    item = prompt._default_image_item(1)
    item.update({
        "present": True,
        # Keep every non-taxonomy input identical so uniqueness cannot be
        # accidentally supplied by a changing file name.
        "label": "shared-taxonomy-reference.png",
        "image_main_type": main_type,
        "image_sub_type": sub_type,
    })
    normalized = prompt._normalize_image_binding_fields(item)
    assert (normalized["source_type"], normalized["scope"]) == wire_pair
    state = prompt._default_widget_state()
    state["images"] = [normalized]
    package = prompt._build_data_only_prompt_package(state)
    validated = agent._assert_public_job_data_contract(package)
    record = validated["images"][0]
    assert record["image_main_type"] == main_type
    assert record["image_sub_type"] == sub_type
    assert (record["source_type"], record["source_scope"]) == wire_pair
    exact_taxonomy_records.add((
        record["image_main_type"],
        record["image_sub_type"],
        record["source_type"],
        record["source_scope"],
        record["target_id"],
    ))
    visible_documents.add(prompt._build_prompt_package(state))
    semantic_fingerprints.add(prompt._prompt_semantic_fingerprint(state))
    packages_by_taxonomy[(main_type, sub_type)] = (package, validated)

assert len(exact_taxonomy_records) == len(prompt.IMAGE_TAXONOMY_WIRE_MAP) == 26
assert len(visible_documents) == 26
assert len(semantic_fingerprints) == 26

# The two authoring choices formerly collapsed to an identical no-video job.
color_mood_package, color_mood_job = packages_by_taxonomy[
    ("Look Reference", "Color Mood")
]
render_look_package, render_look_job = packages_by_taxonomy[
    ("Look Reference", "Render Look")
]
assert color_mood_package != render_look_package
assert color_mood_job["images"][0]["source_scope"] == "Color mood only"
assert render_look_job["images"][0]["source_scope"] == "Render look only"

# Agent fail-closes exact taxonomy and Look-only relationship/binding authority,
# while Target remains an independent Prompt-authored address. Blank, named,
# global, and camera/composition targets are all valid typed Look targets.
full_look_package, full_look_job = packages_by_taxonomy[
    ("Look Reference", "Color / Look / Lighting")
]
full_look_record = full_look_job["images"][0]
assert full_look_record["target_id"] == ""
assert full_look_record["bindings"] == []
assert full_look_record["relationship_targets"] == []

wrong_scope_job = copy.deepcopy(full_look_job)
wrong_scope_job["images"][0]["source_scope"] = "Rendering look only"
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(full_look_package, wrong_scope_job)
    )
)

for authored_target in ("", "Hero_A", "Global Look", "Camera / Composition"):
    targeted_job = copy.deepcopy(full_look_job)
    targeted_job["images"][0]["target_id"] = authored_target
    validated_targeted_job = agent._assert_public_job_data_contract(
        replace_job(full_look_package, targeted_job)
    )
    assert validated_targeted_job["images"][0]["target_id"] == authored_target

wrong_relationship_job = copy.deepcopy(full_look_job)
wrong_relationship_job["images"][0]["relationship_targets"] = ["Hero_A"]
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(full_look_package, wrong_relationship_job)
    )
)

wrong_binding_job = copy.deepcopy(full_look_job)
wrong_binding_job["images"][0]["bindings"] = [{
    "video": "@video1",
    "marker_color": "",
    "target_scope": "All color + look + lighting functions",
}]
wrong_binding_job["videos"] = [{
    "video": "@video1",
    "label": "valid-motion-reference.mp4",
    "source_type": "Motion Reference",
    "custom_source_type": "",
    "control_role": "Local Motion Detail Only",
    "custom_control_role": "",
    "control_role_explicit": True,
    "keep_out": "",
    "identity": {},
}]
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_job(full_look_package, wrong_binding_job)
    )
)

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

# Empty marker values are pending UI binding slots, not invalid taxonomy.
# They must survive until the user fills all three Video / Color selectors.
pending_three = prompt._default_image_item(1)
pending_three.update({
    "image_main_type": "Character",
    "image_sub_type": "Full Appearance",
    "color_picks": ["", "", ""],
    "binding_video_slots": [1, 2, 3],
})
prompt._normalize_image_binding_fields(pending_three)
assert pending_three["color_picks"] == ["", "", ""]
assert pending_three["binding_video_slots"] == [1, 2, 3]

filled_three = prompt._default_image_item(1)
filled_three.update({
    "image_main_type": "Character",
    "image_sub_type": "Full Appearance",
    "color_picks": ["Red", "Green", "Blue", "Yellow"],
    "binding_video_slots": [1, 2, 3, 4],
})
prompt._normalize_image_binding_fields(filled_three)
assert filled_three["color_picks"] == ["Red", "Green", "Blue"]
assert filled_three["binding_video_slots"] == [1, 2, 3]

# Environment Main/Sub already owns scene authority. Migrate only the former
# generated target; a genuinely authored named target remains intact.
legacy_environment_target = prompt._default_image_item(1)
legacy_environment_target.update({
    "image_main_type": "Environment / Background",
    "image_sub_type": "Main Background",
    "owner": "Scene / Environment",
})
prompt._normalize_image_binding_fields(legacy_environment_target)
assert legacy_environment_target["owner"] == ""
assert prompt._default_image_target_for_main_type("Environment / Background") == ""
assert "Scene / Environment" not in common.IMAGE_SYSTEM_TARGETS
assert "Scene / Environment" not in common.IMAGE_OWNER_CHOICES

named_environment_target = prompt._default_image_item(1)
named_environment_target.update({
    "image_main_type": "Environment / Background",
    "image_sub_type": "Main Background",
    "owner": "Forest_Set_A",
})
prompt._normalize_image_binding_fields(named_environment_target)
assert named_environment_target["owner"] == "Forest_Set_A"

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
assert look["owner"] == "Former Character Target"
assert look["interaction_targets"] == [""]
assert prompt._image_binding_entries(look) == []
assert common.image_color_pick_choices_for_taxonomy("Look Reference", "Render Look") == []

# A Target survives repeated normalization and Render -> Lighting -> Composition
# changes. Only the canonical wire source/scope changes with the Sub Type.
transitioning_look = prompt._default_image_item(1)
transitioning_look.update({
    "present": True,
    "label": "jett-look-reference.png",
    "image_main_type": "Look Reference",
    "owner": "Jett_11",
})
for look_subtype in ("Render Look", "Lighting / Atmosphere", "Composition"):
    transitioning_look["image_sub_type"] = look_subtype
    prompt._normalize_image_binding_fields(transitioning_look)
    assert transitioning_look["owner"] == "Jett_11"
    assert (
        transitioning_look["source_type"],
        transitioning_look["scope"],
    ) == prompt.IMAGE_TAXONOMY_WIRE_MAP[("Look Reference", look_subtype)]

# Multiple Look rows may address different subjects with independent look,
# lighting, scale, and composition decisions in the same public Agent job.
targeted_look_state = prompt._default_widget_state()
targeted_look_state["images"] = []
targeted_look_subtypes = prompt.image_sub_type_choices_for_main_type(
    "Look Reference"
)
expected_target_ids = []
for index, look_subtype in enumerate(targeted_look_subtypes, start=1):
    target_id = f"Look_Target_{index}"
    targeted_item = prompt._default_image_item(index)
    targeted_item.update({
        "present": True,
        "label": f"targeted-look-{index}.png",
        "image_main_type": "Look Reference",
        "image_sub_type": look_subtype,
        "owner": target_id,
    })
    targeted_look_state["images"].append(
        prompt._normalize_image_binding_fields(targeted_item)
    )
    expected_target_ids.append(target_id)

targeted_look_visible = prompt._build_prompt_package(targeted_look_state)
targeted_look_job = agent._assert_public_job_data_contract(
    prompt._build_data_only_prompt_package(targeted_look_state)
)
assert [record["target_id"] for record in targeted_look_job["images"]] == (
    expected_target_ids
)
assert all(record["bindings"] == [] for record in targeted_look_job["images"])
assert "across every visible" not in targeted_look_visible
assert "scene-wide" not in targeted_look_visible
assert "only on the selected target" in targeted_look_visible
assert "scene/background content" in targeted_look_visible

# Registration candidates are internal provenance. The public job and Agent
# contract must receive only the effective Prompt Look taxonomy.
verified_look_override = prompt._default_image_item(1)
verified_look_override.update(
    {
        "present": True,
        "label": "registered-master-look.png",
        "asset_managed": True,
        "asset_verified": True,
        "asset_source_kind": "project",
        "asset_source_uid": "verified-look-taxonomy",
        "asset_project_uid": "project-look-taxonomy",
        "asset_library_id": "library-look-taxonomy",
        "asset_id": "MasterLook",
        "asset_image_main_type_candidate": "Look Reference",
        "asset_image_sub_type_candidate": "Color Mood",
        "image_main_type": "Look Reference",
        "image_sub_type": "Scale",
        "owner": "Jett_11",
    }
)
prompt._normalize_image_binding_fields(verified_look_override)
verified_look_state = prompt._default_widget_state()
verified_look_state["images"] = [verified_look_override]
verified_look_job = agent._assert_public_job_data_contract(
    prompt._build_data_only_prompt_package(verified_look_state)
)
verified_look_record = verified_look_job["images"][0]
assert verified_look_record["image_main_type"] == "Look Reference"
assert verified_look_record["image_sub_type"] == "Scale"
assert verified_look_record["source_type"] == "Scale / Composition Reference"
assert verified_look_record["source_scope"] == "Scale only"
assert verified_look_record["target_id"] == "Jett_11"
assert verified_look_record["bindings"] == []
assert "asset_image_sub_type_candidate" not in verified_look_record

# Five-image, no-control-video production example. Image 5 owns the shared
# scene lighting/look while the first four sources retain intrinsic identity.
example_state = prompt._default_widget_state()
example_state["images"] = []
for slot, label, main_type, sub_type, owner in (
    (1, "Character_A.png", "Character", "Full Appearance", "Character_A"),
    (2, "Character_B.png", "Character", "Full Appearance", "Character_B"),
    (3, "Main_Background.png", "Environment / Background", "Main Background", "Main Background"),
    (4, "Sky.png", "Environment / Background", "Sky / Exterior", "Sky"),
    (5, "Master_Look.png", "Look Reference", "Color / Look / Lighting", "Global Look"),
):
    example_item = prompt._default_image_item(slot)
    example_item.update({
        "present": True,
        "label": label,
        "image_main_type": main_type,
        "image_sub_type": sub_type,
        "owner": owner,
    })
    example_state["images"].append(
        prompt._normalize_image_binding_fields(example_item)
    )

example_visible = prompt._build_prompt_package(example_state)
example_job = agent._assert_public_job_data_contract(
    prompt._build_data_only_prompt_package(example_state)
)
assert len(example_job["images"]) == 5
assert example_job["images"][4]["image_main_type"] == "Look Reference"
assert example_job["images"][4]["image_sub_type"] == "Color / Look / Lighting"
assert example_job["images"][4]["source_scope"] == (
    "All color + look + lighting functions"
)
assert example_job["images"][4]["target_id"] == "Global Look"
assert "scene-wide" in example_visible
assert "across every visible" not in example_visible
assert "preserve intrinsic identity, color, pattern, and material" in example_visible

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
    "(26 exact Agent projections, editable Look targets, five-image relight)"
)
