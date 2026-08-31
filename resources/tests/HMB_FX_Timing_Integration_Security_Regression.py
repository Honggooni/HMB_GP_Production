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
from _hmb_bundled_policy_session import install_bundled_policy_session


install_bundled_policy_session(agent._hmb)
POLICY_DOCUMENT, BINDING_DOCUMENT = agent._hmb._load_verified_behavior_documents()
POLICY_RULES = agent._split_behavior_rules(POLICY_DOCUMENT, 4)
BINDING_RULES = agent._split_behavior_rules(BINDING_DOCUMENT, 4)
SEALED_RUNTIME_TEXT = f"{POLICY_DOCUMENT}\n{BINDING_DOCUMENT}"
assert len(POLICY_RULES) == len(BINDING_RULES) == 4
assert all(rule.strip() for rule in (*POLICY_RULES, *BINDING_RULES))
assert POLICY_RULES != BINDING_RULES


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


def video(
    slot: int,
    main_type: str,
    sub_type: str,
    *,
    end_frame: int = 40,
) -> dict:
    item = prompt._default_video_item(slot)
    item.update(
        {
            "present": True,
            "label": f"reference-{slot}.mp4",
            "video_main_type": main_type,
            "video_sub_type": sub_type,
            "video_uid": f"video-{slot}",
            "frame_domain": frame_domain(end_frame),
            "reference_capabilities": reference_capabilities(
                exact_cues=False
            ),
        }
    )
    return item


def ranged_image(
    slot: int,
    *,
    label: str,
    target: str,
    sub_type: str,
    color: str,
    video_slot: int,
    end_frame: int,
    ranges: list[dict[str, int]],
) -> dict:
    item = prompt._default_image_item(slot)
    wire_pair = prompt.image_taxonomy_wire_pair("Character", sub_type)
    assert wire_pair is not None
    source_type, scope = wire_pair
    item.update(
        {
            "present": True,
            "label": label,
            "image_main_type": "Character",
            "image_sub_type": sub_type,
            "source_type": source_type,
            "owner": target,
            "asset_id": target,
            "color_picks": [color],
            "binding_video_slots": [video_slot],
            "binding_scopes": [scope],
            "frame_range_intent": {
                "version": 1,
                "enabled": True,
                "start_frame": 1,
                "end_frame": end_frame,
                "ranges": copy.deepcopy(ranges),
                "selected_index": 0,
            },
            "frame_range_enabled": True,
            "frame_range_color_index": 0,
        }
    )
    return item


def two_source_state() -> dict:
    state = prompt._default_widget_state()
    images = [
        ranged_image(
            1,
            label="Jett full image",
            target="JettMini",
            sub_type="Full Appearance",
            color="Red",
            video_slot=1,
            end_frame=40,
            ranges=[{"start": 1, "end": 10}, {"start": 20, "end": 30}],
        ),
        ranged_image(
            2,
            label="Jett face image",
            target="JettMini",
            sub_type="Full Appearance",
            color="Green",
            video_slot=2,
            end_frame=40,
            ranges=[{"start": 5, "end": 15}, {"start": 25, "end": 35}],
        ),
    ]
    fx = video(1, "FX Reference", "FX Effect Only")
    timing = video(2, "Maya Preview / Playblast", "Timing / Edit")
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
    state["images"] = images
    state["videos"] = [fx, timing]
    return state


# Main Type, not a stale secondary role, owns FX/Timing interpretation.
compiled = prompt._build_data_only_prompt_package(two_source_state())
lines, job, contract, user_data = parse_envelope(compiled)

assert user_data == {}
assert [item["control_role"] for item in job["videos"]] == [
    "FX Effect Only",
    "Timing Only",
]
fx_source, timing_source = contract["sources"]
assert fx_source["role"] == "FX Effect Only"
assert timing_source["role"] == "Timing Only"
assert timing_source["authored_timing_cues"][0]["frame"] == 7
assert timing_source["authored_timing_cues"][0]["local_point"]["space"] == "local"
assert [cue["frame"] for cue in timing_source["authored_timing_cues"]] == [7, 12]

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

# Agent no longer derives, clips, or rejects Prompt-authored FX/timing data.
assert not hasattr(agent, "_derive_fx_timing_runtime_scope")

# Range OFF retains dormant widget state but publishes source-local full video.
range_off_state = two_source_state()
for range_off_image in range_off_state["images"]:
    range_off_image["frame_range_intent"]["enabled"] = False
    range_off_image["frame_range_enabled"] = False
range_off = prompt._build_data_only_prompt_package(range_off_state)
_, range_off_job, range_off_contract, _ = parse_envelope(range_off)
assert range_off_job["frame_ranges"] == []
assert all(
    source["range_segments"] == []
    for source in range_off_contract["sources"]
)

# A mixed valid/invalid optional Range remains a dormant editing draft. It does
# not block the source or publish a partial temporal authority.
partial_state = prompt._default_widget_state()
partial_image = ranged_image(
    1,
    label="Partial range image",
    target="JettMini",
    sub_type="Full Appearance",
    color="Red",
    video_slot=1,
    end_frame=40,
    ranges=[{"start": 1, "end": 10}, {"start": 50, "end": 60}],
)
partial_state["images"] = [partial_image]
partial_state["videos"] = [video(1, "FX Reference", "FX Effect Only")]
partial = prompt._build_data_only_prompt_package(partial_state)
_, partial_job, partial_contract, _ = parse_envelope(partial)
assert len(partial_job["frame_ranges"]) == 1
assert partial_job["frame_ranges"][0]["segments"] == [
    {"start_frame": 1, "end_frame": 10},
    {"start_frame": 50, "end_frame": 60},
]
assert partial_contract["sources"][0]["range_segments"] == [
    {
        "image": "@image1",
        "video": "@video1",
        "marker_color": "Red",
        "start_frame": 1,
        "end_frame": 10,
    },
    {
        "image": "@image1",
        "video": "@video1",
        "marker_color": "Red",
        "start_frame": 50,
        "end_frame": 60,
    },
]

# A disjoint third source is isolated; it cannot erase an independent overlap.
multi_state = prompt._default_widget_state()
multi_state["images"] = [
    ranged_image(
        1,
        label="Hero full image",
        target="Hero",
        sub_type="Full Appearance",
        color="Red",
        video_slot=1,
        end_frame=200,
        ranges=[{"start": 1, "end": 100}],
    ),
    ranged_image(
        2,
        label="Hero face image",
        target="Hero",
        sub_type="Full Appearance",
        color="Green",
        video_slot=2,
        end_frame=200,
        ranges=[{"start": 1, "end": 10}],
    ),
    ranged_image(
        3,
        label="Hero eye image",
        target="Hero",
        sub_type="Full Appearance",
        color="Blue",
        video_slot=3,
        end_frame=200,
        ranges=[{"start": 110, "end": 120}],
    ),
]
multi_state["videos"] = [
    video(1, "FX Reference", "FX Effect Only", end_frame=200),
    video(2, "Maya Preview / Playblast", "Timing / Edit", end_frame=200),
    video(3, "Maya Preview / Playblast", "Timing / Edit", end_frame=200),
]
multi = prompt._build_data_only_prompt_package(multi_state)
_, _, multi_contract, _ = parse_envelope(multi)
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

# Prompt no longer owns a hidden manual-cue rejection helper.
assert not hasattr(prompt, "_control_binding_timing_cues")
assert not hasattr(agent, "_valid_exact_emitter")

# Agent treats the Prompt envelope as opaque user-authored source data. It no
# longer owns pre-generator semantic rejection helpers.
assert not hasattr(agent, "_assert_public_job_data_contract")
assert not hasattr(agent, "_assert_fx_timing_source_contract")
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
    _, _, forwarded_contract, _ = parse_envelope("\n".join(tampered_lines))
    assert forwarded_contract["sources"][0]["range_segments"][0][field] == forged

tampered_lines = list(lines)
tampered_contract = copy.deepcopy(json.loads(tampered_lines[4]))
tampered_contract["sources"][1]["authored_timing_cues"][0]["frame"] = 999
tampered_lines[4] = json.dumps(tampered_contract, separators=(",", ":"))
_, _, forwarded_contract, _ = parse_envelope("\n".join(tampered_lines))
assert forwarded_contract["sources"][1]["authored_timing_cues"][0]["frame"] == 999


print(
    "HMB FX/Timing integration security regression: PASS "
    "(raw facts / signed-runtime scope / exact cue / shared multi-range / "
    "off / partial-invalid / "
    "disjoint isolation / opaque user-data forwarding)"
)
