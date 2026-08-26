from __future__ import annotations

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


prompt = load("_hmb_video_taxonomy_prompt", "HMBPromptLibrary.py")
agent = load("_hmb_video_taxonomy_agent", "HMBAgentLibrary.py")

expected = dict(prompt.VIDEO_TAXONOMY_WIRE_MAP)
assert len(prompt.VIDEO_MAIN_TYPE_CHOICES) == 6  # placeholder + five families
assert sum(len(values) for values in prompt.VIDEO_SUB_TYPE_CHOICES.values()) == 13
assert prompt.VIDEO_SUB_TYPE_CHOICES["Maya Preview / Playblast"] == [
    "Original Preview", "Mask", "Depth", "Motion Guide", "Timing / Edit",
]
assert prompt.VIDEO_SUB_TYPE_CHOICES["Motion Reference"] == [
    "Local Motion", "Secondary Motion",
]
assert "Retargeting Guide" not in prompt.VIDEO_SUB_TYPE_CHOICES["Motion Reference"]
assert "Depth / Spatial" not in prompt.VIDEO_SUB_TYPE_CHOICES["Scene / Look Reference"]
assert prompt.VIDEO_SUB_TYPE_CHOICES["FX Reference"] == ["FX Effect Only"]
assert "FX / Simulation Reference" not in prompt.VIDEO_MAIN_TYPE_CHOICES
assert "Explosion" not in prompt.VIDEO_SUB_TYPE_CHOICES["FX Reference"]
assert "Dust" not in prompt.VIDEO_SUB_TYPE_CHOICES["FX Reference"]
assert "Particle" not in prompt.VIDEO_SUB_TYPE_CHOICES["FX Reference"]
assert "Unified Shot-Control Video" not in prompt.VIDEO_MAIN_TYPE_CHOICES
assert "Timing / Edit Reference" not in prompt.VIDEO_MAIN_TYPE_CHOICES

# Both older duplicate homes and the short-lived standalone homes converge on
# the canonical Maya Preview / Playblast children without changing authority.
expected_migrations = {
    ("Scene / Look Reference", "Depth / Spatial"): (
        "Maya Preview / Playblast",
        "Depth",
    ),
    ("Motion Reference", "Retargeting Guide"): (
        "Maya Preview / Playblast",
        "Motion Guide",
    ),
    ("Depth", "Depth / Spatial"): (
        "Maya Preview / Playblast",
        "Depth",
    ),
    ("Motion Guide", "Retargeting Guide"): (
        "Maya Preview / Playblast",
        "Motion Guide",
    ),
    ("FX / Simulation Reference", "Explosion"): (
        "FX Reference",
        "FX Effect Only",
    ),
    ("FX / Simulation Reference", "Dust"): (
        "FX Reference",
        "FX Effect Only",
    ),
    ("FX / Simulation Reference", "Particle"): (
        "FX Reference",
        "FX Effect Only",
    ),
    ("FX / Simulation Reference", "FX Effect Only"): (
        "FX Reference",
        "FX Effect Only",
    ),
    ("FX Reference", "Explosion"): (
        "FX Reference",
        "FX Effect Only",
    ),
    ("FX Reference", "Dust"): (
        "FX Reference",
        "FX Effect Only",
    ),
    ("FX Reference", "Particle"): (
        "FX Reference",
        "FX Effect Only",
    ),
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
    assert (
        migrated["video_main_type"],
        migrated["video_sub_type"],
    ) == canonical_pair
    assert (
        migrated["picker_auto_video_main_type"],
        migrated["picker_auto_video_sub_type"],
    ) == canonical_pair
    assert (
        migrated["source_type"],
        migrated["control_role"],
    ) == expected[canonical_pair]

# Legacy Main/Sub wire selections are deliberately released rather than
# migrated.  Their labels/media remain ordinary durable video state.
legacy = prompt._default_widget_state()
legacy["videos"][0].update({
    "present": True,
    "label": "legacy.mp4",
    "source_type": "Unified Shot-Control Video",
    "control_role": "Primary Unified Shot Control",
})
released = prompt._normalize_state(legacy)["videos"][0]
assert released["video_main_type"] == "Select Video Main Type"
assert released["video_sub_type"] == ""
assert released["source_type"] == "Role Required / Select Video Type"
assert released["control_role"] == ""
assert released["label"] == "legacy.mp4"

# Every new UI pair projects to an already signed/allowed Agent wire pair.
for index, ((main_type, sub_type), wire_pair) in enumerate(expected.items(), start=1):
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
    assert video["source_type"] in agent._PUBLIC_VIDEO_SOURCE_TYPES
    assert video["control_role"] in agent._PUBLIC_VIDEO_ROLES
    package = prompt._build_data_only_prompt_package(normalized)
    validated = agent._assert_public_job_data_contract(package)
    assert validated["videos"][0]["source_type"] == wire_pair[0]
    assert validated["videos"][0]["control_role"] == wire_pair[1]

# Two Original Preview rows both claim the whole shot. Prompt must not choose a
# winner or silently demote either source; publishing fails with actionable
# guidance and leaves both authored classifications unchanged.
multi_primary_state = prompt._default_widget_state()
multi_primary_state["videos"] = []
for slot in (1, 2):
    row = prompt._default_video_item(slot)
    row.update({
        "present": True,
        "label": f"original-{slot}.mp4",
        "video_main_type": "Maya Preview / Playblast",
        "video_sub_type": "Original Preview",
    })
    multi_primary_state["videos"].append(row)
normalized_multi_primary = prompt._normalize_state(multi_primary_state)
try:
    prompt._build_data_only_prompt_package(normalized_multi_primary)
except RuntimeError as error:
    message = str(error)
    assert "[HMB VIDEO AUTHORITY CONFLICT]" in message
    assert "@video1" in message and "@video2" in message
    assert "No video was auto-reclassified" in message
else:
    raise AssertionError("Multiple Original Preview primaries were published.")
assert [
    row["control_role"] for row in normalized_multi_primary["videos"]
] == ["Primary Unified Shot Control", "Primary Unified Shot Control"]

# Explosion, Dust, and Particle migrate to one canonical Prompt pair. Agent retains
# exact old/old public-envelope compatibility without weakening cross-record
# equality: an old/new mixture must still fail closed.
assert expected[("FX Reference", "FX Effect Only")] == (
    "FX Reference", "FX Effect Only",
)
assert "FX Effect Only" in prompt.VIDEO_CONTROL_ROLE_CHOICES
assert "FX Behavior Only" not in prompt.VIDEO_CONTROL_ROLE_CHOICES
assert prompt._canonical_video_role("FX Behavior Only") == "FX Effect Only"
assert "FX Effect Only" in agent._PUBLIC_VIDEO_ROLES
assert "FX Behavior Only" in agent._PUBLIC_VIDEO_ROLES

legacy_role_state = prompt._default_widget_state()
legacy_role_state["videos"][0].update({
    "present": True,
    "label": "legacy-fx.mp4",
    "video_main_type": "FX / Simulation Reference",
    "video_sub_type": "Explosion",
    "control_role": "FX Behavior Only",
})
canonical_role_state = prompt._normalize_state(legacy_role_state)
assert canonical_role_state["videos"][0]["control_role"] == "FX Effect Only"
canonical_package = prompt._build_data_only_prompt_package(canonical_role_state)
canonical_validated_fx = agent._assert_fx_timing_source_contract(
    canonical_package
)
assert canonical_validated_fx["sources"][0]["selected_role"] == "FX Effect Only"


def package_with_fx_roles(job_role: str, selected_role: str) -> str:
    lines = canonical_package.splitlines()
    job = json.loads(lines[2])
    fx = json.loads(lines[4])
    job["videos"][0]["control_role"] = job_role
    fx["sources"][0]["selected_role"] = selected_role
    lines[2] = json.dumps(job, separators=(",", ":"))
    lines[4] = json.dumps(fx, separators=(",", ":"))
    return "\n".join(lines)


legacy_package = package_with_fx_roles(
    "FX Behavior Only", "FX Behavior Only"
)
legacy_validated_job = agent._assert_public_job_data_contract(legacy_package)
legacy_validated_fx = agent._assert_fx_timing_source_contract(legacy_package)
assert legacy_validated_job["videos"][0]["control_role"] == "FX Behavior Only"
assert legacy_validated_fx["sources"][0]["selected_role"] == "FX Behavior Only"
for job_role, selected_role in (
    ("FX Behavior Only", "FX Effect Only"),
    ("FX Effect Only", "FX Behavior Only"),
):
    try:
        agent._assert_fx_timing_source_contract(
            package_with_fx_roles(job_role, selected_role)
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Mixed legacy/canonical FX roles were accepted.")

print(
    "HMB compact video taxonomy regression: PASS "
    "(eleven-pair migration, 13 canonical UI pairs, FX role compatibility)"
)
