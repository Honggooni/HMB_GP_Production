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


expected = dict(prompt.VIDEO_TAXONOMY_WIRE_MAP)
assert len(prompt.VIDEO_MAIN_TYPE_CHOICES) == 6
assert sum(len(values) for values in prompt.VIDEO_SUB_TYPE_CHOICES.values()) == 13
assert prompt.VIDEO_SUB_TYPE_CHOICES["Maya Preview / Playblast"] == [
    "Original Preview", "Mask", "Depth", "Motion Guide", "Timing / Edit",
]
assert prompt.VIDEO_SUB_TYPE_CHOICES["Motion Reference"] == [
    "Local Motion", "Secondary Motion",
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
assert prompt.VIDEO_TAXONOMY_PAIR_MIGRATIONS == expected_migrations
for old_pair, canonical_pair in expected_migrations.items():
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
    assert (migrated["video_main_type"], migrated["video_sub_type"]) == (
        canonical_pair
    )
    assert (migrated["source_type"], migrated["control_role"]) == (
        expected[canonical_pair]
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
    sample_machine = machine
    sample_visible = prompt._build_prompt_package(normalized)


# Two Original Preview rows remain a Prompt authority conflict; neither row is
# silently demoted before publication.
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
try:
    prompt._build_data_only_prompt_package(normalized_primary)
except RuntimeError as error:
    message = str(error)
    assert "[HMB VIDEO AUTHORITY CONFLICT]" in message
    assert "@video1" in message and "@video2" in message
else:
    raise AssertionError("Multiple Original Preview primaries were published.")
assert [row["control_role"] for row in normalized_primary["videos"]] == [
    "Primary Unified Shot Control", "Primary Unified Shot Control",
]


# Legacy FX labels normalize to one Prompt-owned canonical role in both records.
legacy_fx = prompt._default_widget_state()
legacy_fx["videos"][0].update({
    "present": True,
    "label": "legacy-fx.mp4",
    "video_main_type": "FX / Simulation Reference",
    "video_sub_type": "Explosion",
    "control_role": "FX Behavior Only",
})
canonical_fx = prompt._normalize_state(legacy_fx)
assert canonical_fx["videos"][0]["control_role"] == "FX Effect Only"
job, fx = prompt_records(prompt._build_data_only_prompt_package(canonical_fx))
assert job["videos"][0]["control_role"] == "FX Effect Only"
assert fx["sources"][0]["selected_role"] == "FX Effect Only"


# Agent verifies policy identity and transports the exact paired Prompt bytes;
# it does not revalidate video counts, roles, FX ranges, or provider limits.
agent._assert_prompt_policy_identity_matches_signed_runtime()
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
assert agent._is_private_hmb_runtime_prompt(sample_machine)

print("HMB video taxonomy Prompt-authority / opaque Agent boundary: PASS")
