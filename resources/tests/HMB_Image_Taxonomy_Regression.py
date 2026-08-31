from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
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


def prompt_job(machine_prompt: str) -> dict:
    lines = machine_prompt.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert lines[1] == prompt.PUBLIC_JOB_CONTRACT_HEADER
    assert lines[3] == prompt.FX_TIMING_CONTRACT_HEADER
    assert lines[5] == prompt.USER_DESCRIPTION_DATA_HEADER
    value = json.loads(lines[2])
    assert isinstance(value, dict)
    return value


assert prompt.IMAGE_MAIN_TYPE_CHOICES == [
    "Select Image Main Type",
    "Character",
    "Character Prop",
    "Environment / Background",
    "Background Prop",
    "Look Reference",
    "Custom / Context",
]
taxonomy_payload = common.image_taxonomy_payload()
assert prompt._image_taxonomy_payload() == taxonomy_payload
assert image_asset._taxonomy_payload() == taxonomy_payload
assert taxonomy_payload["schema"] == "hmb-image-taxonomy"
assert taxonomy_payload["version"] == 2
assert taxonomy_payload["main_type_count"] == 6
assert taxonomy_payload["sub_type_count"] == 26
assert taxonomy_payload["pair_count"] == 26
assert len(common.IMAGE_TAXONOMY_WIRE_MAP) == 26


# A stale/omitted Sub Type no longer erases the valid Main Type, Target, or media.
for retired_subtype in ("Scale", "Composition", "Scale / Composition"):
    item = prompt._default_image_item(1)
    item.update({
        "present": True,
        "label": "retired-scale-sheet.png",
        "image_main_type": "Look Reference",
        "image_sub_type": retired_subtype,
        "owner": "Camera / Composition",
    })
    prompt._normalize_image_binding_fields(item)
    assert item["image_main_type"] == "Look Reference"
    assert item["image_sub_type"] == retired_subtype
    assert item["owner"] == "Camera / Composition"
    assert item["source_type"] == "Role Required / Select Source Type"
    asset_fields = image_asset._normalize_image_taxonomy_fields({
        "image_main_type": "Look Reference",
        "image_sub_type": retired_subtype,
    })
    assert asset_fields["image_main_type"] == "Look Reference"
    assert asset_fields["image_sub_type"] == retired_subtype


legacy = prompt._default_widget_state()
legacy["images"][0].update({
    "present": True,
    "label": "legacy.png",
    "asset_id": "legacy",
    "source_type": "Character Appearance",
    "scope": "Full body / full appearance",
    "owner": "hero",
    "color_picks": ["Red"],
})
released = prompt._normalize_state(legacy)["images"][0]
assert released["image_main_type"] == "Select Image Main Type"
assert released["image_sub_type"] == ""
assert released["source_type"] == "Role Required / Select Source Type"
assert released["scope"] == ""
assert released["owner"] == "hero"
assert released["label"] == "legacy.png"
assert released["asset_id"] == "legacy"


# Main Type alone is broad, publishable metadata rather than an execution gate.
main_only = prompt._default_widget_state()
main_only["images"][0].update({
    "present": True,
    "label": "broad-character.png",
    "image_main_type": "Character",
    "image_sub_type": "",
    "owner": "hero",
    "color_picks": ["Red"],
    "binding_scopes": ["authored broad relationship"],
    "binding_video_slots": [1],
})
main_only["videos"][0].update({
    "present": True,
    "label": "broad-motion.mp4",
    "video_main_type": "Motion Reference",
    "video_sub_type": "",
})
main_only_job = prompt_job(prompt._build_data_only_prompt_package(main_only))
assert main_only_job["images"][0]["image_main_type"] == "Character"
assert main_only_job["images"][0]["image_sub_type"] == ""
assert main_only_job["images"][0]["source_type"] == ""
assert main_only_job["images"][0]["target_id"] == "hero"
assert main_only_job["images"][0]["bindings"] == [{
    "video": "@video1",
    "marker_color": "Red",
    "target_scope": "authored broad relationship",
}]


# Prompt owns taxonomy normalization and the exact machine JSON projection.
records: set[tuple[str, str, str, str, str]] = set()
visible_documents: set[str] = set()
fingerprints: set[str] = set()
sample_machine = ""
sample_visible = ""
for (main_type, sub_type), wire_pair in common.IMAGE_TAXONOMY_WIRE_MAP.items():
    item = prompt._default_image_item(1)
    item.update({
        "present": True,
        "label": "shared-taxonomy-reference.png",
        "image_main_type": main_type,
        "image_sub_type": sub_type,
    })
    if main_type == "Look Reference":
        if sub_type in common.IMAGE_GENERAL_LOOK_REFERENCE_SUB_TYPES:
            item["owner"] = common.IMAGE_GLOBAL_LOOK_TARGET
        elif sub_type in common.IMAGE_SCALE_REFERENCE_SUB_TYPES:
            item["owner"] = common.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS[sub_type]
    normalized = prompt._normalize_image_binding_fields(item)
    assert (normalized["source_type"], normalized["scope"]) == wire_pair
    state = prompt._default_widget_state()
    state["images"] = [normalized]
    machine = prompt._build_data_only_prompt_package(state)
    record = prompt_job(machine)["images"][0]
    assert record["image_main_type"] == main_type
    assert record["image_sub_type"] == sub_type
    assert (record["source_type"], record["source_scope"]) == wire_pair
    records.add((
        record["image_main_type"], record["image_sub_type"],
        record["source_type"], record["source_scope"], record["target_id"],
    ))
    visible = prompt._build_prompt_package(state)
    visible_documents.add(visible)
    fingerprints.add(prompt._prompt_semantic_fingerprint(state))
    sample_machine, sample_visible = machine, visible

assert len(records) == len(common.IMAGE_TAXONOMY_WIRE_MAP) == 26
assert len(visible_documents) == 26
assert len(fingerprints) == 26


# Target is optional authored data and is never inferred or re-policed by Agent.
for sub_type, expected_target in common.IMAGE_SCALE_REFERENCE_DEFAULT_TARGETS.items():
    item = prompt._default_image_item(1)
    item.update({
        "present": True,
        "label": "scale-sheet.png",
        "image_main_type": "Look Reference",
        "image_sub_type": sub_type,
    })
    normalized = prompt._normalize_image_binding_fields(item)
    assert normalized["owner"] == ""
    normalized["owner"] = expected_target
    assert prompt._normalize_image_binding_fields(normalized)["owner"] == expected_target

look = prompt._default_image_item(1)
look.update({
    "present": True,
    "label": "look.png",
    "image_main_type": "Look Reference",
    "image_sub_type": "Color Mood",
    "owner": "Global Look",
})
look_state = prompt._default_widget_state()
look_state["images"] = [prompt._normalize_image_binding_fields(look)]
assert prompt_job(prompt._build_data_only_prompt_package(look_state))["images"][0][
    "target_id"
] == "Global Look"


# The two broad Look subtypes serialize the authored scope exactly; a named or
# blank Target must never be rewritten into scene-wide authority.
for authored_target in ("Global Look", "Custom", "hero", ""):
    scoped_look = prompt._default_image_item(1)
    scoped_look.update({
        "present": True,
        "label": "lighting-look.png",
        "image_main_type": "Look Reference",
        "image_sub_type": "Lighting / Atmosphere",
        "owner": authored_target,
        "look_custom_instruction": "Hero lighting only",
    })
    scoped_state = prompt._default_widget_state()
    scoped_state["images"] = [scoped_look]
    scoped_record = prompt_job(
        prompt._build_data_only_prompt_package(scoped_state)
    )["images"][0]
    assert "target_scope_mode" not in scoped_record
    assert scoped_record["target_id"] == authored_target
    assert scoped_record["custom_look_instruction"] == "Hero lighting only"


# Agent transports the paired machine bytes unchanged. It does not rebuild
# taxonomy, pin one policy revision, or append a semantic manifest.
snapshot = {
    "schema": "hmb-prompt-paired-snapshot",
    "version": 1,
    "generation": 1,
    "visible_sha256": hashlib.sha256(sample_visible.encode("utf-8")).hexdigest(),
    "machine_sha256": hashlib.sha256(sample_machine.encode("utf-8")).hexdigest(),
    "machine_prompt": sample_machine,
}
source = SimpleNamespace(
    _hmb_agent_prompt_snapshot=lambda _visible: dict(snapshot)
)
assert agent._paired_machine_prompt(
    SimpleNamespace(_hmb_verified_prompt_source_node=source), sample_visible
) == sample_machine

print("HMB image taxonomy Prompt-authority / opaque Agent boundary: PASS")
