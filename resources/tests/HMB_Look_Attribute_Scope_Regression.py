from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt = load_module("HMBPromptLibrary")
agent = load_module("HMBAgentLibrary")
source = (ROOT / "HMBPromptLibrary.py").read_text(encoding="utf-8")
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
guide = (ROOT / "resources" / "maya" / "HMBVideoPicker_Maya_Guide.txt").read_text(
    encoding="utf-8-sig"
)
legacy_scope_phrases = (
    "explicit user goal may use any visible property",
    "explicit current user goal may use any visible or supplied property",
    "may broaden, narrow, or reframe",
    "broader, narrower, or different use",
    "user's explicit goal may use any readable property",
)
for legacy in legacy_scope_phrases:
    assert legacy.casefold() not in source.casefold(), legacy
    assert legacy.casefold() not in guide.casefold(), legacy

assert prompt.PROMPT_POLICY_SOURCE_VERSION == "2026-08-12.agent-shot-quality.v4.2"
assert prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256 == (
    "7a40ddf71c115ddef29b3bc428ccd9024649d9fac5af607b96173c1cf77b2199"
)
assert prompt.PROMPT_POLICY_SOURCE_VERSION == prompt._hmb._AGENT_POLICY_VERSION
assert (
    prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256
    == prompt._hmb._AGENT_POLICY_CONTRACT_SHA256
)
assert agent._prompt_policy_source_identity() == (
    prompt.PROMPT_POLICY_SOURCE_VERSION,
    prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256,
)
assert agent._assert_prompt_policy_identity_matches_signed_runtime() == (
    prompt.PROMPT_POLICY_SOURCE_VERSION,
    prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256,
)
assert "[HMB SERVER POLICY REQUIRED]" in agent_source
assert "사용자 로컬에 동봉된 hmb_agent_core.dat" not in agent_source
assert "_assert_prompt_policy_identity_matches_signed_runtime()" in agent_source

def prompt_sections(payload: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert len(lines) == 7
    assert lines[1] == "HMB JOB DATA (JSON):"
    assert lines[3] == "FX/TIMING SOURCE DATA (JSON):"
    assert lines[5] == "USER DESCRIPTION DATA (JSON):"
    return json.loads(lines[2]), json.loads(lines[4]), json.loads(lines[6])


# Public Prompt output is typed job data only; look policy remains exclusively
# in the signed Agent runtime.
prompt_only = prompt._build_data_only_prompt_package(prompt._default_widget_state())
job, fx_contract, user_data = prompt_sections(prompt_only)
assert job["images"] == []
assert job["videos"] == []
assert job["control_only_bindings"] == []
assert fx_contract["sources"] == []
assert user_data == {}
for forbidden in (
    "PRODUCTION INTEGRATION DEFAULTS:",
    "Approved final appearance source",
    "Proxy marker colors",
    "relationship interpretation",
):
    assert forbidden not in prompt_only

# A regular Playblast row exposes source identity and the selected role, but no
# policy explanation.
state = prompt._default_widget_state()
state["videos"][0].update({
    "present": True,
    "label": "animator_color_playblast.mp4",
    "video_main_type": "Maya Preview / Playblast",
    "video_sub_type": "Mask",
})
job, fx_contract, user_data = prompt_sections(
    prompt._build_data_only_prompt_package(state)
)
assert job["videos"][0]["source_type"] == "Maya Preview / Playblast"
assert job["videos"][0]["control_role"] == "Mask / Guide Only"
assert fx_contract["sources"] == []
assert user_data == {}

# Structured control-only data is transported as fields while its direct UI
# source remains user-authored text.
control_state = prompt._default_widget_state()
control_state["videos"][0].update({
    "present": True,
    "label": "shot_control.mp4",
    "video_main_type": "Maya Preview / Playblast",
    "video_sub_type": "Original Preview",
})
control_state["text"]["SCENE_CONTEXT"] = (
    "CONTROL_ONLY_BINDING: @video1 | Target = Hero_A | Function = Focus | "
    "Marker = Red | Boundary = Frames 48-72"
)
job, _fx_contract, user_data = prompt_sections(
    prompt._build_data_only_prompt_package(control_state)
)
assert job["control_only_bindings"] == [{
    "source_field": "SCENE_CONTEXT",
    "line": 1,
    "video": "@video1",
    "target_id": "Hero_A",
    "function": "Focus",
    "marker_color": "Red",
    "boundary": "Frames 48-72",
}]
assert user_data == {"SCENE_CONTEXT": control_state["text"]["SCENE_CONTEXT"]}

# FX Main Type has full readable FX-behavior authority but never video look or
# color authority. Policy-derived authority and preservation rules stay sealed.
fx_state = prompt._default_widget_state()
fx_state["videos"][0].update({
    "present": True,
    "label": "fx_reference.mp4",
    "video_main_type": "FX / Simulation Reference",
    "video_sub_type": "Explosion",
})
job, fx_contract, _user_data = prompt_sections(
    prompt._build_data_only_prompt_package(fx_state)
)
assert job["videos"][0]["control_role"] == "FX Behavior Only"
fx_source = fx_contract["sources"][0]
assert fx_source["source_type"] == "FX Reference"
assert fx_source["selected_role"] == "FX Behavior Only"
assert set(fx_source).issubset({
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
})

# Image look intent and routing remain explicit fields, without generated
# appearance-policy prose.
image_state = prompt._default_widget_state()
image_state["videos"][0].update({
    "present": True,
    "label": "shot_control.mp4",
    "video_main_type": "Maya Preview / Playblast",
    "video_sub_type": "Original Preview",
})
image_state["images"][0].update({
    "present": True,
    "label": "hero_character_sheet.png",
    "image_main_type": "Character",
    "image_sub_type": "Full Appearance",
    "source_type": "Character Appearance",
    "owner": "Hero_A",
    "binding_scopes": ["Full body / full appearance"],
    "color_picks": ["Red"],
    "binding_video_slots": [1],
})
job, _fx_contract, _user_data = prompt_sections(
    prompt._build_data_only_prompt_package(image_state)
)
image = job["images"][0]
assert image["target_id"] == "Hero_A"
assert image["source_type"] == "Character Appearance"
assert image["bindings"] == [{
    "video": "@video1",
    "marker_color": "Red",
    "target_scope": "Full body / full appearance",
}]

# Multiple video sources remain independent rows in one closed job schema.
multi = prompt._default_widget_state()
multi["videos"][0].update({
    "present": True,
    "label": "animator_color_playblast.mp4",
    "video_main_type": "Scene / Look Reference",
    "video_sub_type": "Camera / Layout",
})
second = prompt._default_video_item(2)
second.update({
    "present": True,
    "label": "lighting_reference.mp4",
    "video_main_type": "Scene / Look Reference",
    "video_sub_type": "Lighting / Look",
})
multi["videos"].append(second)
job, _fx_contract, _user_data = prompt_sections(
    prompt._build_data_only_prompt_package(multi)
)
assert [(video["video"], video["source_type"], video["control_role"]) for video in job["videos"]] == [
    ("@video1", "Camera / Layout Reference", "Spatial Alignment Verification Only"),
    ("@video2", "Lighting / Look Reference", "Lighting / Look Only"),
]

print(
    "HMB look attribute-scope compiler regression: PASS "
    "(Playblast authority / proxy isolation / scoped overrides / multi-video)"
)
