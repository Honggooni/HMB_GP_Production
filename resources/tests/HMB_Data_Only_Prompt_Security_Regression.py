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
import HMBVideoPickerLibrary as picker_library


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
range_segment = range_fx["sources"][0]["range_segments"][0]
assert range_segment["segment_id"].startswith("image1-video1-")
assert {
    key: value
    for key, value in range_segment.items()
    if key != "segment_id"
} == {
    "image": "@image1",
    "video": "@video1",
    "marker_color": "Red",
    "target_id": "JettMini",
    "target_scope": "",
    "start_frame": 10,
    "end_frame": 20,
}

# A saved Range ON address may temporarily outlive its selected video. The
# signed policy keeps only that typed binding unresolved; it must not turn an
# optional/missing source into a whole-Agent gate.
inactive_range_state = prompt_library._default_widget_state()
inactive_range_image = prompt_library._default_image_item(1)
inactive_range_image.update(
    {
        "present": True,
        "label": "temporarily unresolved range image",
        "source_type": "Character Appearance",
        "owner": "JettMini",
        "color_picks": ["Red"],
        "binding_video_slots": [2],
        "frame_range_enabled": True,
        "frame_range_bindings": {
            "@video2::Red": {
                "enabled": True,
                "video_slot": "@video2",
                "color_pick": "Red",
                "origin": "manual",
                "start_frame": 1,
                "end_frame": 10,
                "ranges": [{"start": 2, "end": 4}],
            }
        },
    }
)
inactive_range_state["images"] = [inactive_range_image]
inactive_range_output = prompt_library._build_prompt_package(inactive_range_state)
inactive_range_job = agent._assert_public_job_data_contract(inactive_range_output)
agent._assert_fx_timing_source_contract(inactive_range_output)
inactive_record = inactive_range_job["frame_ranges"][0]
assert inactive_record["video"] == "@video2"
assert inactive_record["valid"] is False
assert inactive_record["segments"] == []
assert "video_inactive" in inactive_record["error_codes"]

inactive_lines = inactive_range_output.splitlines()
inactive_tampered_job = copy.deepcopy(json.loads(inactive_lines[2]))
inactive_tampered_job["frame_ranges"][0]["valid"] = True
inactive_lines[2] = json.dumps(inactive_tampered_job, separators=(",", ":"))
expect_rejected(
    lambda: agent._assert_public_job_data_contract("\n".join(inactive_lines))
)

inactive_lines = inactive_range_output.splitlines()
inactive_tampered_job = copy.deepcopy(json.loads(inactive_lines[2]))
inactive_tampered_job["frame_ranges"][0]["segments"] = [
    {"start_frame": 2, "end_frame": 4}
]
inactive_lines[2] = json.dumps(inactive_tampered_job, separators=(",", ":"))
expect_rejected(
    lambda: agent._assert_public_job_data_contract("\n".join(inactive_lines))
)

inactive_lines = inactive_range_output.splitlines()
inactive_tampered_job = copy.deepcopy(json.loads(inactive_lines[2]))
inactive_tampered_job["frame_ranges"][0]["error_codes"] = ["segment_missing"]
inactive_lines[2] = json.dumps(inactive_tampered_job, separators=(",", ":"))
expect_rejected(
    lambda: agent._assert_public_job_data_contract("\n".join(inactive_lines))
)

# JSON permits these Unicode line-boundary characters unescaped when
# ensure_ascii=False. They are user text, not public-envelope delimiters.
for separator in ("\u2028", "\u2029", "\u0085"):
    unicode_state = prompt_library._default_widget_state()
    expected_unicode_text = f"alpha{separator}beta"
    unicode_state["text"]["SCENE_CONTEXT"] = expected_unicode_text
    unicode_output = prompt_library._build_prompt_package(unicode_state)
    unicode_job = agent._assert_public_job_data_contract(unicode_output)
    assert unicode_job["schema"] == "hmb-public-job-data"
    assert json.loads(unicode_output.split("\n")[6])["SCENE_CONTEXT"] == (
        expected_unicode_text
    )
    crlf_output = unicode_output.replace("\n", "\r\n")
    crlf_job = agent._assert_public_job_data_contract(crlf_output)
    assert crlf_job == unicode_job

    fx_unicode_state = prompt_library._default_widget_state()
    expected_video_uid = f"video{separator}uid"
    fx_unicode_video = prompt_library._default_video_item(1)
    fx_unicode_video.update(
        {
            "present": True,
            "label": "unicode FX source",
            "video_uid": expected_video_uid,
            "source_uid": expected_video_uid,
            "source_type": "FX Reference",
        }
    )
    fx_unicode_state["videos"] = [fx_unicode_video]
    fx_unicode_output = prompt_library._build_prompt_package(fx_unicode_state)
    fx_unicode_job = agent._assert_public_job_data_contract(fx_unicode_output)
    fx_unicode_contract = agent._assert_fx_timing_source_contract(
        fx_unicode_output
    )
    assert fx_unicode_job["videos"][0]["identity"]["video_uid"] == (
        expected_video_uid
    )
    assert fx_unicode_contract["sources"][0]["video_uid"] == expected_video_uid
    fx_unicode_crlf = fx_unicode_output.replace("\n", "\r\n")
    agent._assert_public_job_data_contract(fx_unicode_crlf)
    crlf_fx_contract = agent._assert_fx_timing_source_contract(fx_unicode_crlf)
    assert crlf_fx_contract["sources"][0]["video_uid"] == expected_video_uid


def range_capacity_state(
    image_count: int,
    binding_count: int,
    range_count: int,
    identifier: str,
):
    capacity_state = prompt_library._default_widget_state()
    capacity_video = prompt_library._default_video_item(1)
    capacity_video.update(
        {
            "present": True,
            "label": identifier,
            "video_uid": identifier,
            "source_uid": identifier,
            "order_key": identifier,
            "source_type": "FX Reference",
        }
    )
    capacity_state["videos"] = [capacity_video]
    colors = ["Red", "Green", "Blue"][:binding_count]
    ranges = [
        {"start": index * 2, "end": index * 2}
        for index in range(range_count)
    ]
    capacity_images = []
    for slot in range(1, image_count + 1):
        capacity_image = prompt_library._default_image_item(slot)
        capacity_image.update(
            {
                "present": True,
                "label": identifier,
                "source_type": "Character Appearance",
                "owner": identifier,
                "asset_id": identifier,
                "asset_library_id": identifier,
                "asset_source_uid": identifier,
                "asset_project_uid": identifier,
                "asset_source_kind": "project",
                "asset_verified": True,
                "color_picks": colors,
                "binding_scopes": ["Custom scope"] * binding_count,
                "binding_custom_scopes": [identifier] * binding_count,
                "binding_video_slots": [1] * binding_count,
                "frame_range_enabled": True,
                "frame_range_bindings": {
                    f"@video1::{color}": {
                        "enabled": True,
                        "video_slot": "@video1",
                        "color_pick": color,
                        "origin": "manual",
                        "start_frame": 0,
                        "end_frame": 9999,
                        "ranges": ranges,
                    }
                    for color in colors
                },
            }
        )
        capacity_images.append(capacity_image)
    capacity_state["images"] = capacity_images
    return capacity_state


# Six ordinary images with 100 selected ranges each must not hit the former
# 500-segment Agent gate.
six_hundred_output = prompt_library._build_prompt_package(
    range_capacity_state(6, 1, 100, "capacity-id")
)
six_hundred_fx = agent._assert_fx_timing_source_contract(six_hundred_output)
assert len(six_hundred_fx["sources"][0]["range_segments"]) == 600

# Multiple Color Pick bindings on one Image/Video address receive stable,
# content-addressed IDs rather than colliding on their local range ordinal.
multi_color_state = range_capacity_state(1, 2, 1, "multi-color-id")
multi_color_output = prompt_library._build_prompt_package(multi_color_state)
multi_color_fx = agent._assert_fx_timing_source_contract(multi_color_output)
multi_color_segments = multi_color_fx["sources"][0]["range_segments"]
multi_color_ids = {segment["segment_id"] for segment in multi_color_segments}
assert len(multi_color_segments) == len(multi_color_ids) == 2
reordered_image = multi_color_state["images"][0]
reordered_image["color_picks"] = list(reversed(reordered_image["color_picks"]))
reordered_image["binding_scopes"] = list(
    reversed(reordered_image["binding_scopes"])
)
reordered_image["binding_custom_scopes"] = list(
    reversed(reordered_image["binding_custom_scopes"])
)
reordered_image["binding_video_slots"] = list(
    reversed(reordered_image["binding_video_slots"])
)
reordered_image["frame_range_bindings"] = dict(
    reversed(list(reordered_image["frame_range_bindings"].items()))
)
reordered_fx = agent._assert_fx_timing_source_contract(
    prompt_library._build_prompt_package(multi_color_state)
)
assert {
    segment["segment_id"]
    for segment in reordered_fx["sources"][0]["range_segments"]
} == multi_color_ids

# Distinct valid Picker cues may reuse an external cue_id. Both producers make
# those IDs unique by cue content, independently of source row order.
cue_markers = [
    {
        "color": "Red",
        "asset_id": "JettMini",
        "subject_root": "|JettMini",
        "maya_uuid": "jett-uuid",
    }
]
cue_domain = {
    "schema": "hmb-video-frame-domain",
    "version": 1,
    "timebase": "24/1",
    "start_frame": 1,
    "end_frame": 100,
    "frame_count": 100,
    "range_addressable": True,
}
raw_duplicate_cues = [
    {
        "cue_id": "shared-cue",
        "frame": frame,
        "cue_phase": "point",
        "emitter": {"maya_uuid": "jett-uuid"},
        "local_point": {
            "kind": "locator",
            "locator_id": f"nozzle-{frame}",
        },
    }
    for frame in (10, 20)
]
picker_cues = picker_library._normalize_timing_cues(
    raw_duplicate_cues, cue_markers, cue_domain
)
picker_cues_reordered = picker_library._normalize_timing_cues(
    list(reversed(raw_duplicate_cues)), cue_markers, cue_domain
)
picker_ids_by_frame = {cue["frame"]: cue["cue_id"] for cue in picker_cues}
assert len(set(picker_ids_by_frame.values())) == 2
assert {
    cue["frame"]: cue["cue_id"] for cue in picker_cues_reordered
} == picker_ids_by_frame
prompt_cues = prompt_library._normalize_video_timing_cues(picker_cues)
prompt_cues_reordered = prompt_library._normalize_video_timing_cues(
    list(reversed(picker_cues))
)
assert {cue["frame"]: cue["cue_id"] for cue in prompt_cues} == (
    {cue["frame"]: cue["cue_id"] for cue in prompt_cues_reordered}
)
cue_state = prompt_library._default_widget_state()
cue_video = prompt_library._default_video_item(1)
cue_video.update(
    {
        "present": True,
        "label": "cue FX",
        "source_type": "FX Reference",
        "frame_domain": cue_domain,
        "timing_cues": picker_cues,
        "reference_capabilities": {
            "schema": "hmb-video-reference-capabilities",
            "version": 1,
            "frame_addressable": True,
            "exact_emitter_cues": True,
            "image_source_frame_ranges": True,
            "marker_instance_identity_fields": ["maya_uuid"],
        },
    }
)
cue_state["videos"] = [cue_video]
cue_contract = agent._assert_fx_timing_source_contract(
    prompt_library._build_prompt_package(cue_state)
)
assert len(cue_contract["sources"][0]["timing_cues"]) == 2

# Exercise the complete public UI range capacity with the worst normal JSON
# escaping character. This is the measured boundary behind Agent's finite caps.
escaped_identifier = "\\" * prompt_library.MAX_IDENTIFIER_CHARS
maximum_state = range_capacity_state(
    prompt_library.MAX_IMAGES,
    prompt_library.MAX_COLOR_PICKS,
    prompt_library.MAX_FRAME_RANGES_PER_BINDING,
    escaped_identifier,
)
maximum_state["text"].update(
    {
        "PROJECT_STYLE_LOOK": "\\" * prompt_library.MAX_DESCRIPTION_CHARS,
        "SCENE_CONTEXT": "\\" * prompt_library.MAX_DESCRIPTION_CHARS,
        "EMOTION_INTENT": "\\" * prompt_library.MAX_DESCRIPTION_CHARS,
        "VIDEO_VFX": "\\" * prompt_library.MAX_VIDEO_VFX_CHARS,
        "PRESERVED_TEXT": "\\" * prompt_library.MAX_DESCRIPTION_CHARS,
    }
)
maximum_output = prompt_library._build_prompt_package(maximum_state)
maximum_lines = maximum_output.split("\n")
maximum_fx = json.loads(maximum_lines[4])
maximum_segments = maximum_fx["sources"][0]["range_segments"]
assert len(maximum_segments) == agent._MAX_FX_RANGE_SEGMENTS_PER_SOURCE
assert len(maximum_lines[4]) <= agent._MAX_FX_TIMING_CONTRACT_CHARS
assert len(maximum_output) <= agent._MAX_HMB_PROMPT_CHARS
agent._assert_public_job_data_contract(maximum_output)
agent._assert_fx_timing_source_contract(maximum_output)
measured_capacity = (
    len(maximum_output), len(maximum_lines[2]), len(maximum_lines[4])
)

# One structurally valid-looking segment over the compiler maximum is rejected
# before any per-record trust decision.
excess_segment = dict(maximum_segments[-1])
excess_segment["segment_id"] = "tampered-cap-plus-one"
maximum_segments.append(excess_segment)
maximum_lines[4] = json.dumps(
    maximum_fx, ensure_ascii=False, separators=(",", ":")
)
expect_rejected(
    lambda: agent._assert_fx_timing_source_contract("\n".join(maximum_lines))
)
maximum_segments.pop()

# The byte-independent character gates also reject their exact cap+1 boundary.
oversized_fx_prompt = "\n".join(
    [
        "HMB_GP_Production",
        "HMB JOB DATA (JSON):",
        "{}",
        "FX/TIMING SOURCE DATA (JSON):",
        "x" * (agent._MAX_FX_TIMING_CONTRACT_CHARS + 1),
        "USER DESCRIPTION DATA (JSON):",
        "{}",
    ]
)
expect_rejected(lambda: agent._prompt_fx_timing_contract(oversized_fx_prompt))
expect_rejected(
    lambda: agent._prompt_data_only_envelope(
        "x" * (agent._MAX_HMB_PROMPT_CHARS + 1)
    )
)

print(
    "HMB data-only Prompt and protected Agent output regression: PASS "
    "(closed schema / no policy prose / path redaction / exact emitter / "
    f"encoded leak / capacity total-job-fx={measured_capacity})"
)
