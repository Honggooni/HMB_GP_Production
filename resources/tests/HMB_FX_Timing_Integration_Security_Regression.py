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
from _hmb_private_policy_fixture import install_private_policy_reader


install_private_policy_reader(agent._hmb)
POLICY_DOCUMENT, BINDING_DOCUMENT = agent._hmb._load_verified_behavior_documents()
POLICY_RULES = agent._split_behavior_rules(POLICY_DOCUMENT, 4)
BINDING_RULES = agent._split_behavior_rules(BINDING_DOCUMENT, 4)
SEALED_RUNTIME_TEXT = f"{POLICY_DOCUMENT}\n{BINDING_DOCUMENT}"
for required_signed_semantic in (
    "all readable FX behavior authoritative",
    "Discard every visible color and appearance property from that video",
    "Timing / Edit Reference is a separate Main Type and contributes only readable edit and timing cues",
    "valid Range ON segments as their common allowed time boundary",
):
    assert required_signed_semantic in SEALED_RUNTIME_TEXT


def derive_runtime(contract: dict) -> dict:
    return agent._derive_fx_timing_runtime_scope(
        contract,
        policy_rules=POLICY_RULES,
        binding_rules=BINDING_RULES,
    )


def parse_envelope(compiled: str) -> tuple[list[str], dict, dict, dict]:
    lines = [line for line in compiled.splitlines() if line.strip()]
    assert len(lines) == 7
    assert lines == [
        "HMB_GP_Production",
        "HMB JOB DATA (JSON):",
        lines[2],
        "FX/TIMING SOURCE DATA (JSON):",
        lines[4],
        "USER DESCRIPTION DATA (JSON):",
        lines[6],
    ]
    return (
        lines,
        json.loads(lines[2]),
        json.loads(lines[4]),
        json.loads(lines[6]),
    )


def expect_rejected(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("tampered FX/Timing contract was accepted")


def frame_domain(end_frame: int = 40) -> dict:
    return {
        "schema": "hmb-video-frame-domain",
        "version": 1,
        "timebase": "24/1",
        "start_frame": 1,
        "end_frame": end_frame,
        "frame_count": end_frame,
        "range_addressable": True,
    }


def reference_capabilities(*, exact_cues: bool) -> dict:
    return {
        "schema": "hmb-video-reference-capabilities",
        "version": 1,
        "frame_addressable": True,
        "exact_emitter_cues": exact_cues,
        "image_source_frame_ranges": True,
        "marker_instance_identity_fields": ["maya_uuid", "full_dag_path"],
    }


def video(slot: int, source_type: str, role: str) -> dict:
    item = prompt._default_video_item(slot)
    item.update(
        {
            "present": True,
            "label": f"reference-{slot}.mp4",
            "source_type": source_type,
            "control_role": role,
            "video_uid": f"video-{slot}",
            "frame_domain": frame_domain(),
            "reference_capabilities": reference_capabilities(
                exact_cues=False
            ),
        }
    )
    return item


def two_source_state() -> dict:
    state = prompt._default_widget_state()
    image = prompt._default_image_item(1)
    image.update(
        {
            "present": True,
            "label": "Jett image",
            "source_type": "Character Appearance",
            "owner": "JettMini",
            "asset_id": "JettMini",
            "color_picks": ["Red", "Green"],
            "binding_video_slots": [1, 2],
            "binding_scopes": [
                "Full body / full appearance",
                "Full body / full appearance",
            ],
            "frame_range_enabled": True,
            "frame_range_color_index": 0,
            "frame_range_bindings": {
                "@video1::Red": {
                    "video_slot": "@video1",
                    "color_pick": "Red",
                    "enabled": True,
                    "origin": "manual",
                    "start_frame": 1,
                    "end_frame": 40,
                    "ranges": [
                        {"start": 1, "end": 10},
                        {"start": 20, "end": 30},
                    ],
                },
                "@video2::Green": {
                    "video_slot": "@video2",
                    "color_pick": "Green",
                    "enabled": True,
                    "origin": "manual",
                    "start_frame": 1,
                    "end_frame": 40,
                    "ranges": [
                        {"start": 5, "end": 15},
                        {"start": 25, "end": 35},
                    ],
                },
            },
        }
    )
    fx = video(1, "FX Reference", "Context Only")
    timing = video(2, "Timing / Edit Reference", "FX Behavior Only")
    timing["reference_capabilities"] = reference_capabilities(
        exact_cues=True
    )
    timing["timing_cues"] = [
        {
            "schema": "hmb-video-emitter-timing-cue",
            "version": 1,
            "cue_id": "cue-7",
            "cue_type": "emitter_point",
            "cue_phase": "onset",
            "frame": 7,
            "emitter": {
                "marker_color": "Green",
                "subject_root": "JettMini",
                "maya_uuid": "UUID-JETT",
            },
            "local_point": {
                "kind": "coordinates",
                "space": "local",
                "unit": "centimeter",
                "xyz": [0.0, 1.0, 2.0],
            },
        },
        {
            "schema": "hmb-video-emitter-timing-cue",
            "version": 1,
            "cue_id": "cue-12-outside-shared-window",
            "cue_type": "emitter_point",
            "cue_phase": "peak",
            "frame": 12,
            "emitter": {
                "marker_color": "Green",
                "subject_root": "JettMini",
                "maya_uuid": "UUID-JETT",
            },
            "local_point": {
                "kind": "coordinates",
                "space": "local",
                "unit": "centimeter",
                "xyz": [0.0, 1.0, 2.0],
            },
        },
    ]
    state["images"] = [image]
    state["videos"] = [fx, timing]
    return state


# Main Type, not a stale secondary role, owns FX/Timing interpretation.
readable = prompt._build_prompt_package(two_source_state())
assert "VIDEO SOURCE:" in readable
assert "FX/TIMING SOURCE DATA (JSON):" not in readable
compiled = prompt._build_data_only_prompt_package(two_source_state())
lines, job, contract, user_data = parse_envelope(compiled)
agent._assert_public_job_data_contract(compiled)
agent._assert_fx_timing_source_contract(compiled)

assert user_data == {}
assert [item["control_role"] for item in job["videos"]] == [
    "Context Only",
    "FX Behavior Only",
]
fx_source, timing_source = contract["sources"]
allowed_source_fact_keys = {
    "video",
    "video_uid",
    "source_type",
    "selected_role",
    "role_selected",
    "validation_codes",
    "range_on",
    "range_segments",
    "emitter_binding_declared",
    "timing_cues",
}
assert set(fx_source).issubset(allowed_source_fact_keys)
assert set(timing_source).issubset(allowed_source_fact_keys)
assert fx_source["selected_role"] == "Context Only"
assert timing_source["selected_role"] == "FX Behavior Only"
assert timing_source["timing_cues"][0]["frame"] == 7
assert timing_source["timing_cues"][0]["local_point"]["space"] == "local"
assert [cue["frame"] for cue in timing_source["timing_cues"]] == [7, 12]

# PROMPT_OUT carries each raw selected range. It does not publish the signed
# policy's shared-boundary interpretation or pre-filter cue 12.
assert [
    (segment["start_frame"], segment["end_frame"])
    for segment in fx_source["range_segments"]
] == [(1, 10), (20, 30)]
assert [
    (segment["start_frame"], segment["end_frame"])
    for segment in timing_source["range_segments"]
] == [(5, 15), (25, 35)]
assert "shared_windows" not in contract
for sealed_phrase in (
    "all readable FX behavior authoritative",
    "Discard every visible color and appearance property",
    "common allowed time boundary",
):
    assert sealed_phrase not in compiled

# Only after the signed 4+4 policy has loaded does Agent derive the common
# temporal boundary and remove the cue that lies outside that boundary.
runtime = derive_runtime(contract)
assert [
    (window["start_frame"], window["end_frame"])
    for window in runtime["shared_windows"]
] == [(5, 10), (25, 30)]
for source in runtime["sources"]:
    assert [
        (segment["start_frame"], segment["end_frame"])
        for segment in source["allowed_segments"]
    ] == [(5, 10), (25, 30)]
runtime_timing = runtime["sources"][1]
assert [cue["frame"] for cue in runtime_timing["timing_cues"]] == [7]
assert "emitter_cue_outside_range" in runtime_timing["validation_codes"]
expect_rejected(
    lambda: agent._derive_fx_timing_runtime_scope(
        contract,
        policy_rules=[],
        binding_rules=[],
    )
)

# Range OFF retains dormant widget state but publishes source-local full video.
range_off_state = two_source_state()
range_off_state["images"][0]["frame_range_enabled"] = False
range_off = prompt._build_data_only_prompt_package(range_off_state)
_, range_off_job, range_off_contract, _ = parse_envelope(range_off)
agent._assert_fx_timing_source_contract(range_off)
assert range_off_job["frame_ranges"] == []
assert all(
    source["range_on"] is False and source["range_segments"] == []
    for source in range_off_contract["sources"]
)
assert all(
    source["range_mode"] == "full_video"
    for source in derive_runtime(range_off_contract)["sources"]
)

# One invalid segment does not erase a valid segment from the same binding.
partial_state = prompt._default_widget_state()
partial_image = copy.deepcopy(two_source_state()["images"][0])
partial_image["color_picks"] = ["Red"]
partial_image["binding_video_slots"] = [1]
partial_image["binding_scopes"] = ["Full body / full appearance"]
partial_image["frame_range_bindings"] = {
    "@video1::Red": {
        "video_slot": "@video1",
        "color_pick": "Red",
        "enabled": True,
        "origin": "manual",
        "start_frame": 1,
        "end_frame": 40,
        "ranges": [
            {"start": 1, "end": 10},
            {"start": 50, "end": 60},
        ],
    }
}
partial_state["images"] = [partial_image]
partial_state["videos"] = [video(1, "FX Reference", "Timing Only")]
partial = prompt._build_data_only_prompt_package(partial_state)
_, partial_job, partial_contract, _ = parse_envelope(partial)
agent._assert_fx_timing_source_contract(partial)
partial_range = partial_job["frame_ranges"][0]
assert partial_range["valid"] is True
assert partial_range["segments"] == [
    {"start_frame": 1, "end_frame": 10}
]
assert partial_range["unresolved_segments"] == [
    {
        "start_frame": 50,
        "end_frame": 60,
        "error_code": "segment_out_of_domain",
    }
]
assert [
    (segment["start_frame"], segment["end_frame"])
    for segment in partial_contract["sources"][0]["range_segments"]
] == [(1, 10)]

# A disjoint third source is isolated; it cannot erase an independent overlap.
multi_state = prompt._default_widget_state()
multi_image = prompt._default_image_item(1)
multi_image.update(
    {
        "present": True,
        "label": "multi image",
        "source_type": "Character Appearance",
        "owner": "Hero",
        "color_picks": ["Red", "Green", "Blue"],
        "binding_video_slots": [1, 2, 3],
        "binding_scopes": ["Full body / full appearance"] * 3,
        "frame_range_enabled": True,
        "frame_range_color_index": 0,
        "frame_range_bindings": {
            "@video1::Red": {
                "video_slot": "@video1",
                "color_pick": "Red",
                "enabled": True,
                "origin": "manual",
                "start_frame": 1,
                "end_frame": 200,
                "ranges": [{"start": 1, "end": 100}],
            },
            "@video2::Green": {
                "video_slot": "@video2",
                "color_pick": "Green",
                "enabled": True,
                "origin": "manual",
                "start_frame": 1,
                "end_frame": 200,
                "ranges": [{"start": 1, "end": 10}],
            },
            "@video3::Blue": {
                "video_slot": "@video3",
                "color_pick": "Blue",
                "enabled": True,
                "origin": "manual",
                "start_frame": 1,
                "end_frame": 200,
                "ranges": [{"start": 110, "end": 120}],
            },
        },
    }
)
multi_state["images"] = [multi_image]
multi_state["videos"] = [
    video(1, "FX Reference", "Context Only"),
    video(2, "Timing / Edit Reference", "FX Behavior Only"),
    video(3, "Timing / Edit Reference", "Context Only"),
]
multi = prompt._build_data_only_prompt_package(multi_state)
_, _, multi_contract, _ = parse_envelope(multi)
agent._assert_fx_timing_source_contract(multi)
multi_sources = {
    source["video"]: source for source in multi_contract["sources"]
}
assert [
    (segment["start_frame"], segment["end_frame"])
    for segment in multi_sources["@video1"]["range_segments"]
] == [(1, 100)]
assert [
    (segment["start_frame"], segment["end_frame"])
    for segment in multi_sources["@video3"]["range_segments"]
] == [(110, 120)]
multi_runtime_sources = {
    source["video"]: source
    for source in derive_runtime(multi_contract)["sources"]
}
assert [
    (segment["start_frame"], segment["end_frame"])
    for segment in multi_runtime_sources["@video1"]["allowed_segments"]
] == [(1, 10)]
assert multi_runtime_sources["@video3"]["range_mode"] == "unresolved"
assert "shared_window" in multi_runtime_sources["@video3"]["validation_codes"]

# Manual exact cues require Target + Marker + local point + exact frame.
manual = {
    "field": "VIDEO_VFX",
    "line": 1,
    "video": 2,
    "target": "JettMini",
    "function": "emitter",
    "marker": "Red",
    "boundary": "Locator = NozzleTip, Frame = 118",
}
assert len(prompt._control_binding_timing_cues([manual], 2)) == 1
for missing in ("target", "marker", "boundary"):
    invalid = dict(manual)
    invalid[missing] = ""
    assert prompt._control_binding_timing_cues([invalid], 2) == []
assert agent._valid_exact_emitter({"marker_color": "Red"}) is False

# Agent rejects semantic mutations even when the JSON shape remains valid.
for field, forged in (
    ("target_scope", "forged scope"),
    ("target_id", "DifferentTarget"),
):
    tampered_lines = list(lines)
    tampered_contract = copy.deepcopy(json.loads(tampered_lines[4]))
    tampered_contract["sources"][0]["range_segments"][0][
        field
    ] = forged
    tampered_lines[4] = json.dumps(tampered_contract, separators=(",", ":"))
    expect_rejected(
        lambda value="\n".join(tampered_lines):
        agent._assert_fx_timing_source_contract(value)
    )

tampered_lines = list(lines)
tampered_contract = copy.deepcopy(json.loads(tampered_lines[4]))
tampered_contract["sources"][1]["timing_cues"][0]["frame"] = 999
tampered_lines[4] = json.dumps(tampered_contract, separators=(",", ":"))
expect_rejected(
    lambda: agent._assert_fx_timing_source_contract("\n".join(tampered_lines))
)


print(
    "HMB FX/Timing integration security regression: PASS "
    "(raw facts / signed-runtime scope / exact cue / shared multi-range / "
    "off / partial-invalid / "
    "disjoint isolation / mutation rejection)"
)
