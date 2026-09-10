from __future__ import annotations

import copy
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


prompt = load("_hmb_video_taxonomy_prompt", "HMBPromptLibrary.py")
agent = load("_hmb_video_taxonomy_agent", "HMBAgentLibrary.py")


def prompt_records(machine_prompt: str) -> tuple[dict, dict]:
    lines = machine_prompt.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert lines[1] == prompt.PUBLIC_JOB_CONTRACT_HEADER
    assert lines[3] == prompt.FX_TIMING_CONTRACT_HEADER
    assert lines[5] == prompt.USER_DESCRIPTION_DATA_HEADER
    job = json.loads(lines[2])
    fx = json.loads(lines[4])
    assert isinstance(job, dict) and isinstance(fx, dict)
    return job, fx


layout_pair = ("Motion Reference", "Layout Reference")
layout_role = "Camera / Layout Preserved; Free Character Motion"
expected = {
    ("Maya Preview / Playblast", "Original Preview"): ("Unified Shot-Control Video", "Primary Unified Shot Control"),
    ("Maya Preview / Playblast", "Mask"): ("Maya Preview / Playblast", "Mask / Guide Only"),
    ("Maya Preview / Playblast", "Depth"): ("Depth / Spatial Reference", "Spatial Alignment Verification Only"),
    ("Maya Preview / Playblast", "Motion Guide"): ("Motion Guide / Retargeting Reference", "Derived Motion Decoding Only"),
    ("Maya Preview / Playblast", "Timing / Edit"): ("Timing / Edit Reference", "Timing Only"),
    ("Motion Reference", "Local Motion"): ("Motion Reference", "Local Motion Detail Only"),
    ("Motion Reference", "Secondary Motion"): ("Motion Reference", "Secondary Motion Only"),
    layout_pair: ("Motion Reference", layout_role),
    ("Scene / Look Reference", "Camera / Layout"): ("Camera / Layout Reference", "Spatial Alignment Verification Only"),
    ("Scene / Look Reference", "Lighting / Look"): ("Lighting / Look Reference", "Lighting / Look Only"),
    ("Scene / Look Reference", "Composition"): ("Camera / Layout Reference", "Local Composition Check Only"),
    ("FX Reference", "FX Effect Only"): ("FX Reference", "FX Effect Only"),
    ("Custom / Context", "Context"): ("Custom", "Context Only"),
    ("Custom / Context", "Custom"): ("Custom", "Custom Role"),
}
assert prompt.VIDEO_TAXONOMY_WIRE_MAP == expected
assert layout_role in prompt.VIDEO_CONTROL_ROLE_CHOICES
assert len(prompt.VIDEO_MAIN_TYPE_CHOICES) == 6
assert sum(len(values) for values in prompt.VIDEO_SUB_TYPE_CHOICES.values()) == 14
assert prompt.VIDEO_SUB_TYPE_CHOICES["Maya Preview / Playblast"] == [
    "Original Preview", "Mask", "Depth", "Motion Guide", "Timing / Edit",
]
assert prompt.VIDEO_SUB_TYPE_CHOICES["Motion Reference"] == [
    "Local Motion", "Secondary Motion", "Layout Reference",
]
assert prompt.VIDEO_SUB_TYPE_CHOICES["FX Reference"] == ["FX Effect Only"]
assert "Unified Shot-Control Video" not in prompt.VIDEO_MAIN_TYPE_CHOICES
assert "Timing / Edit Reference" not in prompt.VIDEO_MAIN_TYPE_CHOICES


expected_migrations = {
    ("Scene / Look Reference", "Depth / Spatial"): (
        "Maya Preview / Playblast", "Depth",
    ),
    ("Motion Reference", "Retargeting Guide"): (
        "Maya Preview / Playblast", "Motion Guide",
    ),
    ("Depth", "Depth / Spatial"): ("Maya Preview / Playblast", "Depth"),
    ("Motion Guide", "Retargeting Guide"): (
        "Maya Preview / Playblast", "Motion Guide",
    ),
    ("FX / Simulation Reference", "Explosion"): (
        "FX Reference", "FX Effect Only",
    ),
    ("FX / Simulation Reference", "Dust"): (
        "FX Reference", "FX Effect Only",
    ),
    ("FX / Simulation Reference", "Particle"): (
        "FX Reference", "FX Effect Only",
    ),
    ("FX / Simulation Reference", "FX Effect Only"): (
        "FX Reference", "FX Effect Only",
    ),
    ("FX Reference", "Explosion"): ("FX Reference", "FX Effect Only"),
    ("FX Reference", "Dust"): ("FX Reference", "FX Effect Only"),
    ("FX Reference", "Particle"): ("FX Reference", "FX Effect Only"),
}
assert not hasattr(prompt, "VIDEO_TAXONOMY_PAIR_MIGRATIONS")
assert not hasattr(prompt, "VIDEO_ROLE_ALIASES")
for old_pair, canonical_pair in expected_migrations.items():
    assert prompt._migrate_video_taxonomy_pair(*old_pair) == old_pair
    state = prompt._default_widget_state()
    state["videos"][0].update({
        "present": True,
        "label": "migrated.mp4",
        "video_main_type": old_pair[0],
        "video_sub_type": old_pair[1],
        "picker_auto_video_main_type": old_pair[0],
        "picker_auto_video_sub_type": old_pair[1],
    })
    migrated = prompt._normalize_state(state)["videos"][0]
    assert (migrated["video_main_type"], migrated["video_sub_type"]) == old_pair
    assert (migrated["source_type"], migrated["control_role"]) == (
        "Role Required / Select Video Type", "",
    )


# Prompt owns the canonical UI pair and exact machine JSON projection.
sample_machine = ""
sample_visible = ""
for index, ((main_type, sub_type), wire_pair) in enumerate(expected.items(), 1):
    state = prompt._default_widget_state()
    state["videos"][0].update({
        "present": True,
        "label": f"taxonomy-{index}.mp4",
        "video_main_type": main_type,
        "video_sub_type": sub_type,
    })
    normalized = prompt._normalize_state(state)
    video = normalized["videos"][0]
    assert (video["source_type"], video["control_role"]) == wire_pair
    machine = prompt._build_data_only_prompt_package(normalized)
    job, _fx = prompt_records(machine)
    assert job["videos"][0]["source_type"] == wire_pair[0]
    assert job["videos"][0]["control_role"] == wire_pair[1]
    assert _fx["sources"][0]["role"] == wire_pair[1]
    assert ("reference_scope" in job["videos"][0]) == ((main_type, sub_type) == layout_pair)
    sample_machine = machine
    sample_visible = prompt._build_prompt_package(normalized)


# Layout Reference is an explicit camera/layout assignment, not Original's
# frame-locked acting and not just interpolation of the source key poses.
layout_state = prompt._default_widget_state()
layout_state["videos"][0].update({
    "present": True,
    "label": "blocking-with-dialogue.mp4",
    "video_main_type": layout_pair[0],
    "video_sub_type": layout_pair[1],
    "custom_control_role": "Keep my authored note",
    "keep_out": "  no added props\nno added props\n",
})
layout_state["text"]["PRESERVED_TEXT"] = "[Dialogue] 안녕, 반가워!"
layout_state = prompt._normalize_state(layout_state)
for _ in range(25):
    restored = prompt._normalize_state(json.loads(json.dumps(layout_state)))
    assert restored == layout_state
    layout_state = restored
layout_machine = prompt._build_data_only_prompt_package(layout_state)
layout_visible = prompt._build_prompt_package(layout_state)
layout_job, layout_fx = prompt_records(layout_machine)
layout_scope = layout_job["videos"][0]["reference_scope"]
assert "camera movement and camera timing" in layout_scope["camera"]
assert "relative scale and spatial staging" in layout_scope["layout"]
assert "full reinterpretation" in layout_scope["character_motion"]
assert "not limited to interpolation" in layout_scope["character_motion"]
assert "speech audio or dialogue" in layout_scope["lip_sync"]
assert "preserve the supplied words" in layout_scope["lip_sync"]
assert "no invented speech" in layout_scope["lip_sync"]
assert layout_scope["frame_by_frame_motion_matching"] is False
assert "assigned image and look-reference" in layout_scope["appearance"]
assert layout_job["videos"][0]["custom_control_role"] == "Keep my authored note"
assert layout_job["videos"][0]["keep_out"] == "  no added props\nno added props\n"
assert json.loads(layout_machine.splitlines()[6])["PRESERVED_TEXT"] == "[Dialogue] 안녕, 반가워!"
assert "Primary Unified Shot Control" not in layout_machine
assert f"Reference Scope: {layout_role}" in layout_visible
assert "Full Motion Reinterpretation and Lip Sync" in layout_visible

# Deriving scope at publication prevents stale data from authorizing free
# motion after any other subtype (including Original Preview) is selected.
for next_pair in [*expected, ("Motion Reference", "")]:
    changed = copy.deepcopy(layout_state)
    changed["videos"][0].update({
        "video_main_type": next_pair[0],
        "video_sub_type": next_pair[1],
        "reference_scope": copy.deepcopy(layout_scope),
    })
    changed_job, _ = prompt_records(prompt._build_data_only_prompt_package(changed))
    changed_record = changed_job["videos"][0]
    assert ("reference_scope" in changed_record) == (next_pair == layout_pair)
    if next_pair in expected:
        assert changed_record["control_role"] == expected[next_pair][1]
    if next_pair != layout_pair:
        assert "Full Motion Reinterpretation and Lip Sync" not in prompt._build_prompt_package(changed)

# Picker reordering/reconnect must keep the author-selected subtype attached
# to its UID, not to the old slot, without changing the other video's role.
def layout_picker_payload(uids):
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "media_ready": True,
        "active_slot_count": len(uids),
        "selected_video_count": len(uids),
        "selection_id": "layout-test-" + "-".join(uids),
        "ordered_video_uids": list(uids),
        "videos": [{
            "video_uid": uid, "source_uid": uid, "order_key": uid,
            "selected": True, "selection_order": slot, "video_slot": slot,
            "video_path": f"https://example.test/{uid}.mp4",
        } for slot, uid in enumerate(uids, 1)],
        "markers": [],
    }


picker_state = prompt._apply_picker_payload(
    prompt._default_widget_state(), layout_picker_payload(("blocking", "other")), connected=True,
)
picker_state["videos"][0].update({
    "video_main_type": layout_pair[0], "video_sub_type": layout_pair[1], "manual": True,
})
picker_state["videos"][1].update({
    "video_main_type": "Motion Reference", "video_sub_type": "Secondary Motion", "manual": True,
})
for order in (("other", "blocking"), ("blocking", "other")):
    picker_state = prompt._apply_picker_payload(picker_state, layout_picker_payload(order), connected=True)
    picker_state = prompt._normalize_state(json.loads(json.dumps(picker_state)))
    by_uid = {row["video_uid"]: row for row in picker_state["videos"]}
    assert by_uid["blocking"]["video_sub_type"] == "Layout Reference"
    assert by_uid["other"]["video_sub_type"] == "Secondary Motion"
disconnected = prompt._apply_picker_payload(picker_state, {}, connected=False)
reconnected = prompt._apply_picker_payload(
    disconnected, layout_picker_payload(("blocking", "other")), connected=True,
)
assert reconnected["videos"][0]["video_sub_type"] == "Layout Reference"


# Main Type alone is broad authored metadata. It remains present in the public
# job even when no exact wire role can be projected from an optional Sub Type.
main_only = prompt._default_widget_state()
main_only["videos"][0].update({
    "present": True,
    "label": "main-only-motion.mp4",
    "video_main_type": "Motion Reference",
    "video_sub_type": "",
    "custom_source_type": "authored broad motion context",
})
normalized_main_only = prompt._normalize_state(main_only)
main_only_video = normalized_main_only["videos"][0]
assert main_only_video["video_main_type"] == "Motion Reference"
assert main_only_video["video_sub_type"] == ""
assert main_only_video["custom_source_type"] == "authored broad motion context"
main_only_job, _main_only_fx = prompt_records(
    prompt._build_data_only_prompt_package(normalized_main_only)
)
assert main_only_job["videos"][0]["video_main_type"] == "Motion Reference"
assert main_only_job["videos"][0]["video_sub_type"] == ""
assert main_only_job["videos"][0]["source_type"] == ""


# Multiple Original Preview rows are ordinary authored inputs. Prompt neither
# rejects them nor silently demotes either role before Agent publication.
multi_primary = prompt._default_widget_state()
multi_primary["videos"] = []
for slot in (1, 2):
    row = prompt._default_video_item(slot)
    row.update({
        "present": True,
        "label": f"original-{slot}.mp4",
        "video_main_type": "Maya Preview / Playblast",
        "video_sub_type": "Original Preview",
    })
    multi_primary["videos"].append(row)
normalized_primary = prompt._normalize_state(multi_primary)
primary_job, _primary_fx = prompt_records(
    prompt._build_data_only_prompt_package(normalized_primary)
)
assert [row["video"] for row in primary_job["videos"]] == [
    "@video1", "@video2",
]
assert [row["label"] for row in primary_job["videos"]] == [
    "original-1.mp4", "original-2.mp4",
]
assert [row["control_role"] for row in primary_job["videos"]] == [
    "Primary Unified Shot Control", "Primary Unified Shot Control",
]
assert [row["control_role"] for row in normalized_primary["videos"]] == [
    "Primary Unified Shot Control", "Primary Unified Shot Control",
]


# Legacy FX labels remain authored values; no migration is imposed.
legacy_fx = prompt._default_widget_state()
legacy_fx["videos"][0].update({
    "present": True,
    "label": "legacy-fx.mp4",
    "video_main_type": "FX / Simulation Reference",
    "video_sub_type": "Explosion",
    "control_role": "FX Behavior Only",
})
canonical_fx = prompt._normalize_state(legacy_fx)
assert canonical_fx["videos"][0]["video_main_type"] == "FX / Simulation Reference"
assert canonical_fx["videos"][0]["video_sub_type"] == "Explosion"
assert canonical_fx["videos"][0]["control_role"] == ""
job, fx = prompt_records(prompt._build_data_only_prompt_package(canonical_fx))
assert job["videos"][0]["control_role"] == ""
assert fx["sources"][0]["role"] == ""


# Retired one-field role labels are not semantic migration input. Only the
# current authored Main/Sub pair may derive source/control wire metadata.
retired_role = prompt._default_widget_state()
retired_role["videos"][0].update({
    "present": True,
    "label": "retired-role.mp4",
    "role": "Motion / Timing Reference",
    "source_type": "Future Wire Source",
    "control_role": "Future Wire Role",
    "custom_source_type": "Authored custom source",
    "custom_control_role": "Authored custom role",
    "custom_video_type": "Retired custom source alias",
    "custom_video_role": "Retired custom role alias",
})
normalized_retired_role = prompt._normalize_state(retired_role)["videos"][0]
assert normalized_retired_role["video_main_type"] == "Select Video Main Type"
assert normalized_retired_role["video_sub_type"] == ""
assert normalized_retired_role["source_type"] == "Role Required / Select Video Type"
assert normalized_retired_role["control_role"] == ""
assert normalized_retired_role["custom_source_type"] == "Authored custom source"
assert normalized_retired_role["custom_control_role"] == "Authored custom role"


# Agent transports the exact paired Prompt bytes and does not pin a policy
# revision or revalidate video counts, roles, FX ranges, or provider limits.
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

# The new scope and lip-sync intent reach Agent as the exact paired data;
# no model call, new validator, or policy override is introduced here.
layout_snapshot = {
    **snapshot,
    "visible_sha256": hashlib.sha256(layout_visible.encode("utf-8")).hexdigest(),
    "machine_sha256": hashlib.sha256(layout_machine.encode("utf-8")).hexdigest(),
    "machine_prompt": layout_machine,
}
layout_source = SimpleNamespace(_hmb_agent_prompt_snapshot=lambda _: dict(layout_snapshot))
assert agent._paired_machine_prompt(
    SimpleNamespace(_hmb_verified_prompt_source_node=layout_source), layout_visible,
) == layout_machine

print("HMB video taxonomy Prompt-authority / opaque Agent boundary: PASS")
