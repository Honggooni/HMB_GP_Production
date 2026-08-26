from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent
import HMBPromptLibrary as prompt


INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1


def intent(
    *,
    enabled: bool = True,
    start: int | None = -2_000_000_000,
    end: int | None = 2_000_000_000,
    ranges: list[dict[str, int]] | None = None,
    selected_index: int = 1,
) -> dict[str, Any]:
    return {
        "version": 1,
        "enabled": enabled,
        "start_frame": start,
        "end_frame": end,
        "ranges": copy.deepcopy(
            ranges
            if ranges is not None
            else [
                {"start": -1_500_000_000, "end": -1_000_000_000},
                {"start": 1_000_000_000, "end": 1_500_000_000},
            ]
        ),
        "selected_index": selected_index,
    }


def image_row(
    frame_intent: dict[str, Any],
    *,
    color: str = "",
    video_slot: int = 1,
) -> dict[str, Any]:
    row = prompt._default_image_item(1)
    row.update(
        {
            "present": True,
            "label": "RangeHero",
            "asset_id": "range-hero",
            "asset_source_uid": "range-hero-source",
            "image_main_type": "Character",
            "image_sub_type": "Full Appearance",
            "source_type": "Character Appearance",
            "owner": "RangeHero",
            "binding_scopes": ["Full body / full appearance"],
            "binding_custom_scopes": [""],
            "binding_video_slots": [video_slot],
            "marker_video": video_slot,
            "color_picks": [color],
            "frame_range_intent": copy.deepcopy(frame_intent),
        }
    )
    return row


def video_row(
    slot: int = 1,
    *,
    source_type: str = "Maya Preview / Playblast",
) -> dict[str, Any]:
    row = prompt._default_video_item(slot)
    taxonomy = {
        "Maya Preview / Playblast": ("Maya Preview / Playblast", "Mask"),
        "FX Reference": ("FX Reference", "FX Effect Only"),
        "Timing / Edit Reference": ("Maya Preview / Playblast", "Timing / Edit"),
    }
    main_type, sub_type = taxonomy[source_type]
    row.update(
        {
            "present": True,
            "label": f"range-source-{slot}.mp4",
            "video_uid": f"range-video-{slot}",
            "source_uid": f"range-video-{slot}",
            "selection_order": slot,
            "order_key": f"range-video-{slot}",
            "video_main_type": main_type,
            "video_sub_type": sub_type,
        }
    )
    return row


def machine_sections(state: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    machine = prompt._build_data_only_prompt_package(state)
    lines = [line for line in machine.splitlines() if line.strip()]
    assert len(lines) == 7
    assert lines[0] == "HMB_GP_Production"
    job = json.loads(lines[2])
    fx_contract = json.loads(lines[4])
    assert agent._assert_public_job_data_contract(machine) == job
    assert agent._assert_fx_timing_source_contract(machine) == fx_contract
    return machine, job, fx_contract


def normalized_intent(state: dict[str, Any]) -> dict[str, Any]:
    return prompt._normalize_state(copy.deepcopy(state))["images"][0][
        "frame_range_intent"
    ]


def picker_payload(
    ordered_uids: tuple[str, ...],
    *,
    marker_color: str = "PickerBlue",
) -> dict[str, Any]:
    videos: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    for slot, uid in enumerate(ordered_uids, start=1):
        videos.append(
            {
                "video_uid": uid,
                "source_uid": uid,
                "order_key": uid,
                "selected": True,
                "selection_order": slot,
                "video_slot": slot,
                "video_path": f"https://example.test/{uid}.mp4",
                **(
                    {
                        # Additional lifecycle sources are mask companions,
                        # never duplicate shot-wide Original authorities.
                        "generation_role": "mask",
                        "media_kind": "maya_color_assignment_mask",
                        "video_role": "maya_color_assignment_mask",
                    }
                    if slot > 1
                    else {}
                ),
                "reference_capabilities": {
                    "schema": "hmb-video-reference-capabilities",
                    "version": 1,
                    "frame_addressable": False,
                    "exact_emitter_cues": False,
                    "image_source_frame_ranges": False,
                    "marker_instance_identity_fields": [],
                },
                "markers": [],
            }
        )
        metadata.append(
            {
                "video_slot": f"@video{slot}",
                "video_uid": uid,
                "source_uid": uid,
                "fps": 24,
                "start_frame": 1,
                "end_frame": 24,
                "frame_count": 24,
                "available_color_picks": [marker_color],
                "valid": True,
            }
        )
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "media_ready": bool(videos),
        "active_slot_count": len(videos),
        "selected_video_count": len(videos),
        "selection_id": "selection-" + "-".join(ordered_uids),
        "ordered_video_uids": list(ordered_uids),
        "videos": videos,
        "markers": [],
        "frame_metadata": metadata,
    }


def empty_picker_payload() -> dict[str, Any]:
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "media_ready": False,
        "active_slot_count": 0,
        "selected_video_count": 0,
        "selection_id": "selection-empty",
        "ordered_video_uids": [],
        "videos": [],
        "markers": [],
        "frame_metadata": [],
    }


# Canonical Prompt Range accepts the entire signed-int32 domain. Picker-era
# 0..9999 limits must not survive in either endpoints or selected segments.
boundary_state = prompt._default_widget_state()
boundary_state["images"] = [
    image_row(
        intent(
            start=INT32_MIN,
            end=INT32_MAX,
            ranges=[
                {"start": INT32_MIN, "end": INT32_MIN + 100},
                {"start": INT32_MAX - 100, "end": INT32_MAX},
            ],
        )
    )
]
boundary_state["videos"] = [video_row()]
normalized_boundary = normalized_intent(boundary_state)
assert normalized_boundary["start_frame"] == INT32_MIN
assert normalized_boundary["end_frame"] == INT32_MAX
assert normalized_boundary["ranges"] == [
    {"start": INT32_MIN, "end": INT32_MIN + 100},
    {"start": INT32_MAX - 100, "end": INT32_MAX},
]
_, boundary_job, _ = machine_sections(boundary_state)
boundary_record = boundary_job["frame_ranges"][0]
assert boundary_record["domain"] == {
    "start_frame": INT32_MIN,
    "end_frame": INT32_MAX,
    "frame_count": 1 << 32,
    "fps": 0.0,
}
assert boundary_record["marker_color"] == "Video-wide"
assert boundary_record["origin"] == "manual"
assert boundary_record["valid"] is True


# Finite legacy numerics inside signed-int32 still round. Out-of-domain values,
# booleans, and non-finite input are rejected rather than clamped into a
# different user instruction or turned into accidental frame zeroes.
numeric_state = copy.deepcopy(boundary_state)
numeric_state["images"][0]["frame_range_intent"] = {
    "version": 1,
    "enabled": True,
    "start_frame": -9e30,
    "end_frame": "999999999999999999999999",
    "ranges": [
        {"start": "-2147483648", "end": -2147483647.4},
        {"start": True, "end": 10},
        {"start": "nan", "end": 20},
    ],
    "selected_index": 0,
}
normalized_numeric = normalized_intent(numeric_state)
assert normalized_numeric["start_frame"] is None
assert normalized_numeric["end_frame"] is None
assert normalized_numeric["ranges"] == [
    {"start": INT32_MIN, "end": -2147483647}
]


# Range is a user-owned draft even when no video exists. Public Agent v1 has no
# address for that draft, so it emits no fabricated @video1 record and remains
# a valid, non-blocking prompt-only generation contract.
draft = prompt._default_widget_state()
draft_intent = intent()
draft["images"] = [image_row(draft_intent)]
draft["videos"] = []
assert normalized_intent(draft) == draft_intent
draft_machine, draft_job, draft_fx = machine_sections(draft)
assert draft_job["videos"] == []
assert draft_job["frame_ranges"] == []
assert draft_fx == {
    "schema": "hmb-fx-timing-source-facts",
    "version": 3,
    "valid": True,
    "errors": [],
    "sources": [],
}
assert "video_inactive" not in draft_machine
assert agent._derive_fx_timing_runtime_scope(
    draft_fx,
    policy_rules=["loaded"] * 4,
    binding_rules=["loaded"] * 4,
) == {"sources": [], "shared_windows": []}


# Range state alone does not fabricate a public image source. A blank default
# row stays dormant even if the user prepared a temporal draft before adding
# media or image identity.
blank_row_draft = prompt._default_widget_state()
blank_row_draft["images"][0]["frame_range_intent"] = copy.deepcopy(draft_intent)
blank_row_draft["videos"] = [video_row()]
assert normalized_intent(blank_row_draft) == draft_intent
_, blank_row_job, _ = machine_sections(blank_row_draft)
assert blank_row_job["images"] == []
assert blank_row_job["frame_ranges"] == []


# A real manual video is sufficient for v1 projection. Blank Color means the
# stable video-wide address even with no Picker connection or metadata.
manual_video = copy.deepcopy(draft)
manual_video["videos"] = [video_row()]
_, manual_job, _ = machine_sections(manual_video)
manual_record = manual_job["frame_ranges"][0]
assert manual_record["video"] == "@video1"
assert manual_record["marker_color"] == "Video-wide"
assert manual_record["segments"] == [
    {"start_frame": -1_500_000_000, "end_frame": -1_000_000_000},
    {"start_frame": 1_000_000_000, "end_frame": 1_500_000_000},
]
assert manual_record["valid"] is True


# Picker metadata is suggestion-only. Missing, empty, shorter, longer,
# conflicting domains, Color allow-list conflicts, and false capability flags
# all produce the same manual v1 Range record.
picker_oracles = [
    {},
    {
        "enabled": True,
        "awaiting_data": False,
        "markers": [],
        "frame_metadata": [],
    },
    {
        "enabled": True,
        "awaiting_data": False,
        "markers": [{"video_slot": 1, "color": "PickerBlue"}],
        "frame_metadata": [
            {
                "video_slot": "@video1",
                "fps": 24,
                "start_frame": 1,
                "end_frame": 24,
                "frame_count": 24,
                "available_color_picks": ["PickerBlue"],
                "valid": True,
            }
        ],
    },
    {
        "enabled": True,
        "awaiting_data": False,
        "markers": [{"video_slot": 1, "color": "OtherColor"}],
        "frame_metadata": [
            {
                "video_slot": "@video1",
                "fps": 60,
                "start_frame": -2_100_000_000,
                "end_frame": 2_100_000_000,
                "frame_count": 4_200_000_001,
                "available_color_picks": ["OtherColor"],
                "valid": True,
            }
        ],
    },
    {
        "enabled": True,
        "awaiting_data": False,
        "markers": [{"video_slot": 1, "color": "Conflict"}],
        "frame_metadata": [
            {
                "video_slot": "@video1",
                "fps": 24,
                "start_frame": 100,
                "end_frame": 50,
                "frame_count": 999,
                "available_color_picks": ["Conflict"],
                "conflict": True,
                "valid": False,
            }
        ],
    },
]
baseline_record = copy.deepcopy(manual_record)
for picker_state in picker_oracles:
    candidate = copy.deepcopy(manual_video)
    candidate["picker"] = picker_state
    candidate["videos"][0]["reference_capabilities"] = {
        "schema": "hmb-video-reference-capabilities",
        "version": 1,
        "frame_addressable": False,
        "exact_emitter_cues": False,
        "image_source_frame_ranges": False,
        "marker_instance_identity_fields": [],
    }
    _, job, _ = machine_sections(candidate)
    assert job["frame_ranges"] == [baseline_record], (
        picker_state,
        baseline_record,
        job["frame_ranges"],
    )

color_conflict = copy.deepcopy(manual_video)
color_conflict["images"][0]["color_picks"] = ["Pink"]
color_conflict["picker"] = picker_oracles[2]
_, color_job, _ = machine_sections(color_conflict)
assert color_job["frame_ranges"][0]["marker_color"] == "Pink"
assert color_job["frame_ranges"][0]["valid"] is True
assert color_job["frame_ranges"][0]["error_codes"] == []


# FX sources also treat Picker capabilities as non-authoritative for manual
# Prompt Range. The Agent receives the user's exact allowed segments.
fx_state = copy.deepcopy(manual_video)
fx_state["videos"][0]["video_main_type"] = "FX Reference"
fx_state["videos"][0]["video_sub_type"] = "FX Effect Only"
fx_state["videos"][0]["reference_capabilities"] = {
    "schema": "hmb-video-reference-capabilities",
    "version": 1,
    "frame_addressable": False,
    "exact_emitter_cues": False,
    "image_source_frame_ranges": False,
    "marker_instance_identity_fields": [],
}
fx_state["picker"] = picker_oracles[2]
_, _, fx_contract = machine_sections(fx_state)
assert fx_contract["valid"] is True
assert fx_contract["errors"] == []
assert fx_contract["sources"][0]["range_on"] is True
assert agent._derive_fx_timing_runtime_scope(
    fx_contract,
    policy_rules=["loaded"] * 4,
    binding_rules=["loaded"] * 4,
)["sources"][0]["range_mode"] == "selected_segments"


# Source lifecycle operations may change derived video addresses but must not
# mutate the canonical Prompt-authored intent.
lifecycle = prompt._default_widget_state()
lifecycle_intent = intent(
    start=-400,
    end=120_000,
    ranges=[{"start": -50, "end": 10}, {"start": 80_000, "end": 90_000}],
)
lifecycle["images"] = [image_row(lifecycle_intent, color="UserMagenta")]
lifecycle["videos"] = [video_row()]
lifecycle_states = [copy.deepcopy(lifecycle)]
lifecycle_states.append(
    prompt._apply_picker_payload(
        copy.deepcopy(lifecycle_states[-1]),
        picker_payload(("picker-a", "picker-b")),
        connected=True,
    )
)
lifecycle_states.append(
    prompt._apply_picker_payload(
        copy.deepcopy(lifecycle_states[-1]),
        picker_payload(("picker-b", "picker-a"), marker_color="Conflict"),
        connected=True,
    )
)
lifecycle_states.append(
    prompt._apply_picker_payload(
        copy.deepcopy(lifecycle_states[-1]),
        empty_picker_payload(),
        connected=True,
    )
)
lifecycle_states.append(
    prompt._apply_picker_payload(
        copy.deepcopy(lifecycle_states[-1]),
        picker_payload(("picker-a",)),
        connected=True,
    )
)
lifecycle_states.append(
    prompt._apply_picker_payload(
        copy.deepcopy(lifecycle_states[-1]),
        {},
        connected=False,
    )
)
for lifecycle_state in lifecycle_states:
    assert normalized_intent(lifecycle_state) == lifecycle_intent

for lifecycle_index in (0, 1, 2, 4):
    lifecycle_state = lifecycle_states[lifecycle_index]
    _, job, _ = machine_sections(lifecycle_state)
    assert len(job["frame_ranges"]) == 1, (lifecycle_index, job)
    assert job["frame_ranges"][0]["domain"]["start_frame"] == -400
    assert job["frame_ranges"][0]["domain"]["end_frame"] == 120_000
    assert job["frame_ranges"][0]["valid"] is True

for lifecycle_index in (3, 5):
    _, empty_lifecycle_job, _ = machine_sections(lifecycle_states[lifecycle_index])
    assert empty_lifecycle_job["frame_ranges"] == []


# A higher-source stale echo at the same UI revision keeps new source structure
# but cannot roll the local user intent back to OFF.
ui_echo = prompt._normalize_state(copy.deepcopy(lifecycle_states[0]))
ui_echo[prompt.SOURCE_SYNC_REVISION_KEY] = 40
ui_echo[prompt.UI_EDIT_REVISION_KEY] = 7
source_echo = copy.deepcopy(ui_echo)
source_echo[prompt.SOURCE_SYNC_REVISION_KEY] = 41
source_echo[prompt.UI_EDIT_REVISION_KEY] = 7
source_echo["images"][0]["label"] = "New source label"
source_echo["images"][0]["frame_range_intent"] = intent(
    enabled=False,
    start=None,
    end=None,
    ranges=[],
    selected_index=-1,
)
merged_echo = prompt._merge_prompt_revision_axes(source_echo, ui_echo)
assert merged_echo["images"][0]["label"] == "New source label"
assert merged_echo["images"][0]["frame_range_intent"] == lifecycle_intent
assert merged_echo[prompt.SOURCE_SYNC_REVISION_KEY] == 41
assert merged_echo[prompt.UI_EDIT_REVISION_KEY] == 7

revision_node = prompt.HMBPromptLibrary(name="free_range_revision_axes")
revision_node._hmb_last_accepted_widget_state = json.dumps(ui_echo)
instance_merged_echo = revision_node._merge_widget_revision_axes(source_echo)
assert instance_merged_echo["images"][0]["label"] == "New source label"
assert instance_merged_echo["images"][0]["frame_range_intent"] == lifecycle_intent
assert instance_merged_echo[prompt.SOURCE_SYNC_REVISION_KEY] == 41
assert instance_merged_echo[prompt.UI_EDIT_REVISION_KEY] == 7


# One-time legacy migration accepts only user/manual authored bindings. Picker
# auto bindings never become canonical Range intent, and a canonical key is
# permanently authoritative once written.
picker_only = prompt._default_widget_state()
picker_only_row = image_row(intent(enabled=False, start=None, end=None, ranges=[], selected_index=-1))
picker_only_row.pop("frame_range_intent", None)
picker_only_row.update(
    {
        "frame_range_enabled": True,
        "frame_range_selected_index": 0,
        "frame_range_binding": {
            "video_slot": "@video1",
            "color_pick": "Red",
            "origin": "picker_auto",
            "start_frame": 1,
            "end_frame": 48,
            "ranges": [{"start": 10, "end": 20}],
        },
        "frame_range_bindings": {
            "@video1::Red": {
                "video_slot": "@video1",
                "color_pick": "Red",
                "origin": "picker-authored",
                "start_frame": 1,
                "end_frame": 48,
                "ranges": [{"start": 10, "end": 20}],
            }
        },
    }
)
picker_only["images"] = [picker_only_row]
picker_only["videos"] = [video_row()]
normalized_picker_only = prompt._normalize_state(picker_only)
assert normalized_picker_only["images"][0]["frame_range_intent"] == intent(
    enabled=True,
    start=None,
    end=None,
    ranges=[],
    selected_index=-1,
)
_, picker_only_job, picker_only_fx = machine_sections(normalized_picker_only)
assert picker_only_job["frame_ranges"] == []
assert picker_only_fx["valid"] is True


# Incomplete, reversed, and out-of-domain user drafts remain byte-stable local
# intent but are omitted from Agent v1. Generation falls back to full-video use
# instead of turning an optional edit into a workflow-wide validation gate.
invalid_intents = [
    intent(start=-100, end=None, ranges=[{"start": -10, "end": 10}], selected_index=0),
    intent(start=100, end=-100, ranges=[{"start": -10, "end": 10}], selected_index=0),
    intent(start=-100, end=100, ranges=[{"start": -200, "end": 10}], selected_index=0),
    intent(start=-100, end=100, ranges=[{"start": 50, "end": -50}], selected_index=0),
]
for invalid_intent in invalid_intents:
    invalid_state = prompt._default_widget_state()
    invalid_state["images"] = [image_row(invalid_intent)]
    invalid_state["videos"] = [video_row(source_type="FX Reference")]
    assert normalized_intent(invalid_state) == invalid_intent
    _, invalid_job, invalid_fx = machine_sections(invalid_state)
    assert invalid_job["frame_ranges"] == []
    assert invalid_fx["valid"] is True
    assert invalid_fx["errors"] == []
    assert invalid_fx["sources"][0]["range_on"] is False
    assert agent._derive_fx_timing_runtime_scope(
        invalid_fx,
        policy_rules=["loaded"] * 4,
        binding_rules=["loaded"] * 4,
    )["sources"][0]["range_mode"] == "full_video"

manual_migration = copy.deepcopy(picker_only)
manual_migration["images"][0].pop("frame_range_intent", None)
manual_migration["images"][0]["color_picks"] = ["Red", "Blue"]
manual_migration["images"][0]["binding_video_slots"] = [1, 1]
manual_migration["images"][0]["frame_range_color_index"] = 1
manual_migration["images"][0]["frame_range_selected_index"] = 0
manual_migration["images"][0]["frame_range_bindings"]["@video1::Blue"] = {
    "video_slot": "@video1",
    "color_pick": "Blue",
    "origin": "manual",
    "start_frame": -60,
    "end_frame": 60000,
    "ranges": [{"start": -10, "end": 20}],
}
migrated = prompt._normalize_state(manual_migration)
assert migrated["images"][0]["frame_range_intent"] == intent(
    start=-60,
    end=60000,
    ranges=[{"start": -10, "end": 20}],
    selected_index=0,
)
assert migrated["images"][0]["frame_range_intent"].keys() == {
    "version",
    "enabled",
    "start_frame",
    "end_frame",
    "ranges",
    "selected_index",
}

canonical_wins = copy.deepcopy(migrated)
canonical_wins["images"][0]["frame_range_intent"] = intent(
    enabled=False,
    start=None,
    end=None,
    ranges=[],
    selected_index=-1,
)
canonical_wins["images"][0]["frame_range_bindings"]["@video1::Blue"].update(
    {
        "start_frame": 777,
        "end_frame": 999,
        "ranges": [{"start": 800, "end": 900}],
    }
)
canonical_once = prompt._normalize_state(canonical_wins)
canonical_twice = prompt._normalize_state(canonical_once)
expected_default_intent = intent(
    enabled=False,
    start=None,
    end=None,
    ranges=[],
    selected_index=-1,
)
assert canonical_once["images"][0]["frame_range_intent"] == expected_default_intent
assert canonical_twice["images"][0]["frame_range_intent"] == expected_default_intent


print(
    "HMB Prompt free Frame Range contract regression: PASS "
    "(signed int32 / no-video draft / Agent v1 projection / Picker independence / "
    "source echo / manual-only migration)"
)
