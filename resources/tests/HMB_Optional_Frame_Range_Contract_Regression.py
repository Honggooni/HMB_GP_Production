from __future__ import annotations

import copy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent
import HMBPromptLibrary as prompt


assert "Frame Range OFF/미설정" in agent._HMB_SOURCE_CONTRACT_INVALID_MESSAGE
assert "정상적인 선택 상태" in agent._HMB_SOURCE_CONTRACT_INVALID_MESSAGE


def parse_machine(state: dict) -> tuple[str, dict, dict]:
    machine = prompt._build_data_only_prompt_package(state)
    lines = [line for line in machine.splitlines() if line.strip()]
    assert len(lines) == 7
    job = json.loads(lines[2])
    contract = json.loads(lines[4])
    agent._assert_public_job_data_contract(machine)
    assert agent._assert_fx_timing_source_contract(machine) == contract
    return machine, job, contract


def runtime(contract: dict) -> dict:
    return agent._derive_fx_timing_runtime_scope(
        contract,
        policy_rules=["loaded"] * 4,
        binding_rules=["loaded"] * 4,
    )


def video(slot: int, source_type: str) -> dict:
    item = prompt._default_video_item(slot)
    taxonomy = {
        "Maya Preview / Playblast": ("Maya Preview / Playblast", "Mask"),
        "FX Reference": ("FX Reference", "FX Effect Only"),
        "Timing / Edit Reference": ("Maya Preview / Playblast", "Timing / Edit"),
    }
    main_type, sub_type = taxonomy[source_type]
    item.update({
        "present": True,
        "label": f"source-{slot}.mp4",
        "video_main_type": main_type,
        "video_sub_type": sub_type,
    })
    return item


def bound_image(*, range_enabled: bool, valid_range: bool) -> dict:
    item = prompt._default_image_item(1)
    item.update({
        "present": True,
        "label": "approved-character.png",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "source_type": "Character Appearance",
        "owner": "Hero",
        "color_picks": ["Red"],
        "binding_video_slots": [1],
        "binding_scopes": ["Full body / full appearance"],
        "frame_range_intent": {
            "version": 1,
            "enabled": range_enabled,
            "start_frame": 1 if valid_range else 101,
            "end_frame": 48 if valid_range else 40,
            "ranges": [
                {"start": 12, "end": 24}
                if valid_range
                else {"start": 30, "end": 20}
            ],
            "selected_index": 0,
        },
        "frame_range_enabled": range_enabled,
        "frame_range_color_index": 0,
        "frame_range_bindings": {
            "@video1::Red": {
                "video_slot": "@video1",
                "color_pick": "Red",
                "enabled": True,
                "origin": "manual",
                "start_frame": 1 if valid_range else 101,
                "end_frame": 48 if valid_range else 40,
                "ranges": [
                    {"start": 12, "end": 24}
                    if valid_range
                    else {"start": 30, "end": 20}
                ],
            }
        },
    })
    return item


# No FX/Timing source and no Range are ordinary valid inputs. An empty typed
# source list is never a requirement for the user to add another source.
empty = prompt._default_widget_state()
empty["images"] = []
empty["videos"] = [video(1, "Maya Preview / Playblast")]
_, empty_job, empty_contract = parse_machine(empty)
assert empty_job["frame_ranges"] == []
assert empty_contract == {
    "schema": "hmb-fx-timing-source-facts",
    "version": 3,
    "valid": True,
    "errors": [],
    "sources": [],
}
assert runtime(empty_contract) == {"sources": [], "shared_windows": []}


# FX and Timing/Edit Main Types remain full-video sources when the optional
# Range UI is unset. Neither an image binding, role, nor emitter cue is a gate.
for main_type in ("FX Reference", "Timing / Edit Reference"):
    no_range = prompt._default_widget_state()
    no_range["images"] = []
    no_range["videos"] = [video(1, main_type)]
    _, job, contract = parse_machine(no_range)
    assert job["frame_ranges"] == []
    assert contract["valid"] is True and contract["errors"] == []
    assert contract["sources"][0]["role_selected"] is True
    assert contract["sources"][0]["emitter_binding_declared"] is False
    assert contract["sources"][0]["range_on"] is False
    assert contract["sources"][0]["range_segments"] == []
    assert runtime(contract)["sources"][0]["range_mode"] == "full_video"


# Range OFF keeps a dormant authored selection in widget state but publishes
# no active temporal restriction. Full-video use therefore remains available.
range_off = prompt._default_widget_state()
range_off["images"] = [bound_image(range_enabled=False, valid_range=False)]
range_off["videos"] = [video(1, "FX Reference")]
normalized_off = prompt._normalize_state(copy.deepcopy(range_off))
assert normalized_off["images"][0]["frame_range_bindings"]
_, off_job, off_contract = parse_machine(range_off)
assert off_job["frame_ranges"] == []
assert off_contract["sources"][0]["range_on"] is False
assert runtime(off_contract)["sources"][0]["range_mode"] == "full_video"


# A valid explicit Range ON selection wins over the source-local full-video
# default and is exposed as the allowed timing segment.
range_on = prompt._default_widget_state()
range_on["images"] = [bound_image(range_enabled=True, valid_range=True)]
range_on["videos"] = [video(1, "Timing / Edit Reference")]
_, on_job, on_contract = parse_machine(range_on)
assert on_job["frame_ranges"] == [{
    "image": "@image1",
    "video": "@video1",
    "marker_color": "Red",
    "enabled": True,
    "origin": "manual",
    "domain": {
        "start_frame": 1,
        "end_frame": 48,
        "frame_count": 48,
        "fps": 0.0,
    },
    "segments": [{"start_frame": 12, "end_frame": 24}],
    "unresolved_segments": [],
    "valid": True,
    "error_codes": [],
}]
assert on_contract["sources"][0]["range_on"] is True
assert [
    (segment["start_frame"], segment["end_frame"])
    for segment in on_contract["sources"][0]["range_segments"]
] == [(12, 24)]
on_runtime = runtime(on_contract)["sources"][0]
assert on_runtime["range_mode"] == "selected_segments"
assert on_runtime["allowed_segments"] == on_contract["sources"][0][
    "range_segments"
]


# An incomplete/invalid Range ON selection stays in canonical Prompt state but
# is omitted from public Agent v1. The source therefore remains full-video and
# generation cannot be blocked by an optional unfinished edit.
invalid_on = prompt._default_widget_state()
invalid_on["images"] = [bound_image(range_enabled=True, valid_range=False)]
invalid_on["videos"] = [video(1, "FX Reference")]
invalid_machine, invalid_job, invalid_contract = parse_machine(invalid_on)
normalized_invalid = prompt._normalize_state(copy.deepcopy(invalid_on))
assert normalized_invalid["images"][0]["frame_range_intent"] == {
    "version": 1,
    "enabled": True,
    "start_frame": 101,
    "end_frame": 40,
    "ranges": [{"start": 30, "end": 20}],
    "selected_index": 0,
}
assert invalid_job["frame_ranges"] == []
assert invalid_contract["valid"] is True
assert invalid_contract["errors"] == []
assert invalid_contract["sources"][0]["range_on"] is False
assert invalid_contract["sources"][0]["range_segments"] == []
assert runtime(invalid_contract)["sources"][0]["range_mode"] == "full_video"


# A bad optional Range attached to a non-FX video also cannot disable an
# independent FX source. Only the affected Playblast binding stays unresolved.
isolated = prompt._default_widget_state()
isolated["images"] = [bound_image(range_enabled=True, valid_range=False)]
isolated["videos"] = [
    video(1, "Maya Preview / Playblast"),
    video(2, "FX Reference"),
]
_, isolated_job, isolated_contract = parse_machine(isolated)
assert isolated_job["frame_ranges"] == []
assert [source["video"] for source in isolated_contract["sources"]] == [
    "@video2"
]
assert isolated_contract["sources"][0]["range_on"] is False
assert runtime(isolated_contract)["sources"][0]["range_mode"] == "full_video"


print(
    "HMB optional Frame Range contract regression: PASS "
    "(empty / off / unset / valid ON priority / invalid ON non-blocking omission)"
)
