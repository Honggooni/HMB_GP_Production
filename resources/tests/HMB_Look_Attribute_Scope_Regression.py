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
common_source = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
legacy_scope_phrases = (
    "explicit user goal may use any visible property",
    "explicit current user goal may use any visible or supplied property",
    "may broaden, narrow, or reframe",
    "broader, narrower, or different use",
    "user's explicit goal may use any readable property",
)
for legacy in legacy_scope_phrases:
    assert legacy.casefold() not in source.casefold(), legacy

# Prompt and Agent must not pin one server revision, prose contract digest, or
# locally reviewed policy candidate.  The signed server session is the sole
# policy source; these retired symbols would recreate a client-side policy gate.
for retired_symbol in (
    "PROMPT_POLICY_SOURCE_VERSION",
    "PROMPT_POLICY_SOURCE_CONTRACT_SHA256",
    "PROMPT_POLICY_CANDIDATE_VERSION",
    "PROMPT_POLICY_CANDIDATE_CONTRACT_SHA256",
    "PROMPT_POLICY_CANDIDATE_STATUS",
):
    assert not hasattr(prompt, retired_symbol), retired_symbol
    assert retired_symbol not in source, retired_symbol
for retired_symbol in (
    "_AGENT_POLICY_VERSION",
    "_AGENT_POLICY_CONTRACT_SHA256",
):
    assert not hasattr(prompt._hmb, retired_symbol), retired_symbol
    assert retired_symbol not in common_source, retired_symbol
for retired_symbol in (
    "_prompt_policy_source_identity",
    "_assert_prompt_policy_identity_matches_signed_runtime",
):
    assert not hasattr(agent, retired_symbol), retired_symbol
    assert retired_symbol not in agent_source, retired_symbol
assert "[HMB SERVER POLICY REQUIRED]" in agent_source
assert "사용자 로컬에 동봉된 hmb_agent_core.dat" not in agent_source
assert "_bootstrap_agent_policy_session()" in agent_source
assert "resources/agent/hmb_agent_core.dat" not in agent_source

def prompt_sections(payload: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert len(lines) == 7
    assert lines[1] == "HMB JOB DATA (JSON):"
    assert lines[3] == "FX/TIMING SOURCE DATA (JSON):"
    assert lines[5] == "USER DESCRIPTION DATA (JSON):"
    return json.loads(lines[2]), json.loads(lines[4]), json.loads(lines[6])


def look_claim_package(*claims: tuple[str, str]) -> str:
    """Build one closed job with two real recipients and typed Look claims."""

    look_state = prompt._default_widget_state()
    look_state["images"] = []
    for slot, label, owner, main_type, sub_type in (
        (1, "hero-sheet.png", "Hero_A", "Character", "Full Appearance"),
        (
            2,
            "forest-sheet.png",
            "Forest_A",
            "Environment / Background",
            "Main Background",
        ),
    ):
        row = prompt._default_image_item(slot)
        row.update({
            "present": True,
            "label": label,
            "owner": owner,
            "image_main_type": main_type,
            "image_sub_type": sub_type,
        })
        look_state["images"].append(row)
    for slot, (sub_type, target) in enumerate(claims, start=3):
        row = prompt._default_image_item(slot)
        row.update({
            "present": True,
            "label": f"look-{slot}.png",
            "owner": target,
            "image_main_type": "Look Reference",
            "image_sub_type": sub_type,
        })
        look_state["images"].append(row)
    return prompt._build_data_only_prompt_package(look_state)


# Public Prompt output is typed job data only; look policy remains exclusively
# in the signed Agent runtime.
prompt_only = prompt._build_data_only_prompt_package(prompt._default_widget_state())
job, fx_contract, user_data = prompt_sections(prompt_only)
assert job["images"] == []
assert job["videos"] == []
assert job["control_only_bindings"] == []
assert fx_contract["sources"] == []
assert fx_contract["control_bindings"] == []
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
assert fx_contract["sources"] == [{
    "video": "@video1",
    "video_main_type": "Maya Preview / Playblast",
    "video_sub_type": "Mask",
    "custom_source_type": "",
    "role": "Mask / Guide Only",
    "custom_role": "",
    "keep_out": "",
    "range_segments": [],
    "authored_timing_cues": [],
}]
assert fx_contract["control_bindings"] == []
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
    "raw": "@video1 | Target = Hero_A | Function = Focus | Marker = Red | Boundary = Frames 48-72",
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
    "video_main_type": "FX Reference",
    "video_sub_type": "FX Effect Only",
})
job, fx_contract, _user_data = prompt_sections(
    prompt._build_data_only_prompt_package(fx_state)
)
assert job["videos"][0]["control_role"] == "FX Effect Only"
fx_source = fx_contract["sources"][0]
assert fx_source["video_main_type"] == "FX Reference"
assert fx_source["role"] == "FX Effect Only"
assert set(fx_source) == {
    "video",
    "video_main_type",
    "video_sub_type",
    "custom_source_type",
    "role",
    "custom_role",
    "keep_out",
    "range_segments",
    "authored_timing_cues",
}

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

# Look authority is an attribute-domain contract, not a last-writer-wins list.
# The same recipient (or Global Look versus any named recipient) may carry
# disjoint color/lighting/render claims, but overlapping domains fail closed.
for valid_claims in (
    (
        ("Color Mood", "Hero_A"),
        ("Lighting / Atmosphere", "Global Look"),
        ("Render Look", "Hero_A"),
    ),
    (
        ("Color Mood", "Hero_A"),
        ("Color Mood", "Forest_A"),
    ),
    (
        ("Color Mood", "Global Look"),
        ("Lighting / Atmosphere", "Global Look"),
    ),
    (
        ("Color Mood", "Global Look"),
        ("Lighting / Atmosphere", "Global Look"),
        ("Render Look", "Global Look"),
    ),
):
    valid_package = look_claim_package(*valid_claims)
    valid_job, _valid_fx, _valid_user = prompt_sections(valid_package)
    assert [
        (row["image_sub_type"], row["target_id"])
        for row in valid_job["images"][2:]
    ] == list(valid_claims)

for invalid_claims, _retired_local_conflict_tokens in (
    (
        (
            ("Color Mood", "Hero_A"),
            ("Color Mood", "Hero_A"),
        ),
        {"@image3", "@image4"},
    ),
    (
        (
            ("Color / Look / Lighting", "Global Look"),
            ("Render Look", "Hero_A"),
        ),
        {"@image4"},
    ),
    (
        (
            ("Color Mood", "Global Look"),
            ("Color Mood", "Hero_A"),
        ),
        {"@image4"},
    ),
    (
        (
            ("Color / Look / Lighting", "Global Look"),
            ("Lighting / Atmosphere", "Global Look"),
        ),
        {"@image4"},
    ),
):
    invalid_package = look_claim_package(*invalid_claims)
    # The public wire contract remains data-only and transmits every authored
    # claim without Agent-side semantic rejection.  The authenticated policy
    # model resolves authority; Generator owns provider/media constraints.
    invalid_job, _invalid_fx, _invalid_user = prompt_sections(invalid_package)
    assert [
        (row["image_sub_type"], row["target_id"])
        for row in invalid_job["images"][2:]
    ] == list(invalid_claims)

assert "_assert_final_output_semantic_integrity" not in agent_source
assert "_build_final_output_semantic_manifest" not in agent_source
assert "_assert_public_job_data_contract(machine_prompt)" not in agent_source

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
