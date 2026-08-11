from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent
import HMBPromptLibrary as prompt_library


def expect_rejected(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("tampered public contract was accepted")


state = prompt_library._default_widget_state()
state["text"]["SCENE_CONTEXT"] = "User-authored scene note."

image = prompt_library._default_image_item(1)
image.update(
    {
        "present": True,
        "label": "Jett image",
        "source_type": "Character Appearance",
        "owner": "JettMini",
        "asset_id": "JettMini",
        "asset_path": "P:/private/project/JettMini.jpg",
        "asset_source_uid": "source:jett",
        "asset_verified": True,
        "color_picks": ["Red"],
        "binding_video_slots": [1],
    }
)
state["images"] = [image]

fx = prompt_library._default_video_item(1)
fx.update(
    {
        "present": True,
        "label": "fx.mp4",
        "source_type": "FX Reference",
        # Main Type is canonical: a stale narrower role cannot reduce FX behavior.
        "control_role": "Context Only",
    }
)
timing = prompt_library._default_video_item(2)
timing.update(
    {
        "present": True,
        "label": "timing.mp4",
        "source_type": "Timing / Edit Reference",
        "control_role": "FX Behavior Only",
    }
)
state["videos"] = [fx, timing]

compiled = prompt_library._build_prompt_package(state)
lines = [line for line in compiled.splitlines() if line.strip()]
assert len(lines) == 7
assert lines[0] == "HMB_GP_Production"
assert lines[1] == "HMB JOB DATA (JSON):"
assert lines[3] == "FX/TIMING SOURCE DATA (JSON):"
assert lines[5] == "USER DESCRIPTION DATA (JSON):"
for forbidden in (
    "PRODUCTION INTEGRATION DEFAULTS:",
    "TARGET GENERATOR:",
    "IMAGE ROLE MAP:",
    "VIDEO ROLE MAP:",
    "REPLACEMENT BINDING:",
    "SOURCE DATA WARNINGS:",
    "P:/private/project/JettMini.jpg",
):
    assert forbidden not in compiled

job = agent._assert_public_job_data_contract(compiled)
fx_contract = agent._assert_fx_timing_source_contract(compiled)
# v4.1 is the active signed server policy, so its canonical FX/Timing facts
# must match the runtime contract instead of being held behind the old
# pending-signature gate.
agent._assert_fx_candidate_matches_signed_runtime(fx_contract)
assert "asset_path" not in job["images"][0]["identity"]
assert [video["control_role"] for video in job["videos"]] == [
    "Context Only",
    "FX Behavior Only",
]
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
assert all(
    set(source).issubset(allowed_source_fact_keys)
    for source in fx_contract["sources"]
)
for source, expected_role in zip(
    fx_contract["sources"], ("Context Only", "FX Behavior Only")
):
    assert source["selected_role"] == expected_role


def all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from all_keys(nested)


serialized_fx_keys = set(all_keys(fx_contract))
assert not any("authority" in key.casefold() for key in serialized_fx_keys)
assert not any(key.casefold().startswith("ignored_") for key in serialized_fx_keys)
for forbidden_policy_key in {
    "video_appearance_authority",
    "effect_behavior_authority",
    "ignored_appearance_properties",
    "ignored_color_properties",
    "playblast_fx_precedence",
    "preserve_playblast_domains",
    "timing_authority",
    "shared_windows",
    "activation",
}:
    assert forbidden_policy_key not in serialized_fx_keys
for forbidden_policy_phrase in (
    "ignore every visible color",
    "full fx-behavior authority",
    "fx reference prevails",
    "preserve playblast",
):
    assert forbidden_policy_phrase not in compiled.casefold()
assert json.loads(lines[6])["SCENE_CONTEXT"] == "User-authored scene note."

empty_contract = agent._assert_fx_timing_source_contract(
    prompt_library._build_prompt_package(prompt_library._default_widget_state())
)
assert empty_contract["sources"] == []
agent._assert_fx_candidate_matches_signed_runtime(empty_contract)

expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        compiled + "legacy generated policy prose\n"
    )
)

tampered_lines = compiled.splitlines()
tampered_job = copy.deepcopy(json.loads(tampered_lines[2]))
tampered_job["images"][0]["identity"]["policy_summary"] = "forbidden"
tampered_lines[2] = json.dumps(tampered_job, separators=(",", ":"))
expect_rejected(
    lambda: agent._assert_public_job_data_contract("\n".join(tampered_lines))
)

manual_emitter = {
    "field": "VIDEO_VFX",
    "line": 1,
    "video": 2,
    "target": "JettMini",
    "function": "emitter",
    "marker": "",
    "boundary": "Locator = NozzleTip, Frame = 118",
}
assert prompt_library._control_binding_timing_cues([manual_emitter], 2) == []
manual_emitter["marker"] = "Red"
cue = prompt_library._control_binding_timing_cues([manual_emitter], 2)[0]
assert cue["emitter"] == {
    "marker_color": "Red",
    "subject_root": "JettMini",
}
assert agent._valid_exact_emitter({"marker_color": "Red"}) is False
assert agent._valid_exact_emitter(cue["emitter"]) is True

secret = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa"
)
for exposed in (secret, json.dumps(secret), json.dumps(json.dumps(secret))):
    assert agent._contains_public_output_state_leak(exposed, secret, secret)

# Structured-connector catch-all text and technical JSON never enter USER DATA.
connector_state = prompt_library._default_widget_state()
connector_state["source_intent_fallbacks"] = [
    {
        "source": "PICKER_IN",
        "reason": "explicit user-authored text extension: description",
        "text": "MALICIOUS CONNECTOR DESCRIPTION",
    },
    {
        "source": "PICKER_IN",
        "reason": "frame metadata",
        "text": '{"decoded_frame_count":62,"maya_start_frame":101}',
    },
]
connector_output = prompt_library._build_prompt_package(connector_state)
assert "MALICIOUS CONNECTOR DESCRIPTION" not in connector_output
assert "decoded_frame_count" not in connector_output
assert json.loads(connector_output.splitlines()[6]) == {}

# Multiple segments on one binding remain independent when one is invalid.
range_state = prompt_library._default_widget_state()
range_video = prompt_library._default_video_item(1)
range_video.update(
    {"present": True, "label": "fx", "source_type": "FX Reference"}
)
range_image = prompt_library._default_image_item(1)
range_image.update(
    {
        "present": True,
        "label": "range image",
        "source_type": "Character Appearance",
        "owner": "JettMini",
        "color_picks": ["Red"],
        "binding_video_slots": [1],
        "frame_range_enabled": True,
        "frame_range_bindings": {
            "@video1::red": {
                "enabled": True,
                "video_slot": "@video1",
                "color_pick": "Red",
                "origin": "manual",
                "start_frame": 1,
                "end_frame": 100,
                "ranges": [
                    {"start": 10, "end": 20},
                    {"start": 90, "end": 120},
                ],
            }
        },
    }
)
range_state["videos"] = [range_video]
range_state["images"] = [range_image]
range_output = prompt_library._build_prompt_package(range_state)
range_job = agent._assert_public_job_data_contract(range_output)
range_fx = agent._assert_fx_timing_source_contract(range_output)
range_record = range_job["frame_ranges"][0]
assert range_record["valid"] is True
assert range_record["segments"] == [{"start_frame": 10, "end_frame": 20}]
assert range_record["unresolved_segments"] == [
    {
        "start_frame": 90,
        "end_frame": 120,
        "error_code": "segment_out_of_domain",
    }
]
assert range_fx["valid"] is False
assert range_fx["sources"][0]["range_on"] is True
assert range_fx["sources"][0]["range_segments"] == [
    {
        "segment_id": "image1-video1-1",
        "image": "@image1",
        "video": "@video1",
        "marker_color": "Red",
        "target_id": "JettMini",
        "target_scope": "",
        "start_frame": 10,
        "end_frame": 20,
    }
]

print(
    "HMB data-only Prompt and protected Agent output regression: PASS "
    "(closed schema / no policy prose / path redaction / exact emitter / encoded leak)"
)
