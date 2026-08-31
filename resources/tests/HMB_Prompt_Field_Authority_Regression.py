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


def replace_user_data(package: str, payload: dict) -> str:
    lines = package.splitlines()
    assert lines[5] == prompt.USER_DESCRIPTION_DATA_HEADER
    lines[6] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return "\n".join(lines)


prompt = load("_hmb_prompt_field_authority_prompt", "HMBPromptLibrary.py")
agent = load("_hmb_prompt_field_authority_agent", "HMBAgentLibrary.py")


def prompt_sections(payload: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert lines[1] == prompt.PUBLIC_JOB_CONTRACT_HEADER
    assert lines[3] == prompt.FX_TIMING_CONTRACT_HEADER
    assert lines[5] == prompt.USER_DESCRIPTION_DATA_HEADER
    return json.loads(lines[2]), json.loads(lines[4]), json.loads(lines[6])

assert "prompt_guidance" not in prompt._default_widget_state()

# All 31 non-empty combinations remain independent typed fields. This protects
# the renewed descriptions from becoming a field merge or an accidental task.
field_values = {
    "PROJECT_STYLE_LOOK": "Project-wide painterly render language",
    "SCENE_CONTEXT": "Rainy rooftop at dusk",
    "EMOTION_INTENT": "Character_A: restrained relief",
    "VIDEO_VFX": "Character_A lip-syncs to @audio1 from 00:01–00:03",
    "PRESERVED_TEXT": (
        "[Lip-sync Transcript] 안녕, Jett!\n"
        "[Lip-sync Speech] legacy stays EXACT."
    ),
}
field_names = list(prompt.TEXT_FIELD_NAMES)
for mask in range(1, 1 << len(field_names)):
    state = prompt._default_widget_state()
    expected = {}
    for index, key in enumerate(field_names):
        if mask & (1 << index):
            state["text"][key] = field_values[key]
            expected[key] = field_values[key]
    package = prompt._build_data_only_prompt_package(state)
    job, _fx_data, user_data = prompt_sections(package)
    assert user_data == expected
    assert "prompt_guidance" not in package
    assert "qa_coverage_not_provider_attention" not in package
    assert "HMB QA" not in package

# Current authored VFX and per-video Keep Out text are opaque values. Retired
# compatibility fields must neither append labeled prose nor merge/deduplicate
# lines into either current field.
verbatim_state = prompt._default_widget_state()
verbatim_state["text"].update({
    "VIDEO_VFX": "  repeat VFX\nrepeat VFX\n  tail VFX  ",
    "FX_ADDITIONAL_INSTRUCTION": "retired additional VFX",
    "FALLBACK_MISSING_FUNCTION": "retired fallback function",
    "FALLBACK_INSTRUCTION": "retired fallback instruction",
    "VIDEO_CONTEXT": "retired video context",
    "VIDEO_MARKER": "retired video marker",
    "VIDEO_DESCRIPTION": "retired video description",
})
verbatim_state["videos"][0].update({
    "present": True,
    "label": "verbatim.mp4",
    "video_main_type": "Custom / Context",
    "video_sub_type": "Custom",
    "keep_out": "  repeat Keep Out\nrepeat Keep Out\n  tail Keep Out  ",
    "keepOut": "retired camel-case Keep Out",
    "exclusion_note": "retired exclusion",
    "negative_prompt": "retired negative prompt",
    "video_marker": "retired marker",
    "marker": "retired marker alias",
    "description": "retired description",
})
normalized_verbatim = prompt._normalize_state(verbatim_state)
assert normalized_verbatim["text"]["VIDEO_VFX"] == (
    "  repeat VFX\nrepeat VFX\n  tail VFX  "
)
assert normalized_verbatim["videos"][0]["keep_out"] == (
    "  repeat Keep Out\nrepeat Keep Out\n  tail Keep Out  "
)
verbatim_package = prompt._build_data_only_prompt_package(normalized_verbatim)
_verbatim_job, verbatim_fx, verbatim_user = prompt_sections(verbatim_package)
assert verbatim_user["VIDEO_VFX"] == "  repeat VFX\nrepeat VFX\n  tail VFX  "
assert verbatim_fx["sources"][0]["keep_out"] == (
    "  repeat Keep Out\nrepeat Keep Out\n  tail Keep Out  "
)
for retired_text in (
    "retired additional VFX",
    "retired fallback function",
    "retired fallback instruction",
    "retired video context",
    "retired video marker",
    "retired video description",
    "retired camel-case Keep Out",
    "retired exclusion",
    "retired negative prompt",
    "retired marker",
    "retired marker alias",
    "retired description",
):
    assert retired_text not in verbatim_package

# A transcript is exact text evidence only. It neither creates media nor adds a
# task/activation field to the public job contract.
transcript_state = prompt._default_widget_state()
transcript_state["text"]["PRESERVED_TEXT"] = field_values["PRESERVED_TEXT"]
transcript_package = prompt._build_data_only_prompt_package(transcript_state)
transcript_job, _transcript_fx, transcript_user_data = prompt_sections(
    transcript_package
)
assert transcript_job["images"] == []
assert transcript_job["videos"] == []
assert set(transcript_user_data) == {"PRESERVED_TEXT"}
assert transcript_user_data["PRESERVED_TEXT"] == field_values["PRESERVED_TEXT"]
assert all("lip" not in key.casefold() for key in transcript_job)

# Prompt authoring still enforces its own UI/storage bounds. Agent no longer
# rejects or truncates an already paired Prompt snapshot based on field size.
limit_state = prompt._default_widget_state()
for key in field_names:
    limit_state["text"][key] = "V" * (
        prompt.MAX_VIDEO_VFX_CHARS
        if key == "VIDEO_VFX"
        else prompt.MAX_DESCRIPTION_CHARS
    )
limit_package = prompt._build_data_only_prompt_package(limit_state)
_limit_job, _limit_fx, limit_user_data = prompt_sections(limit_package)
assert set(limit_user_data) == set(field_names)

base_package = prompt._build_data_only_prompt_package(prompt._default_widget_state())
oversized_style = replace_user_data(
    base_package,
    {"PROJECT_STYLE_LOOK": "X" * (prompt.MAX_DESCRIPTION_CHARS + 1)},
)
oversized_vfx = replace_user_data(
    base_package,
    {"VIDEO_VFX": "X" * (prompt.MAX_VIDEO_VFX_CHARS + 1)},
)
assert len(prompt_sections(oversized_style)[2]["PROJECT_STYLE_LOOK"]) == (
    prompt.MAX_DESCRIPTION_CHARS + 1
)
assert len(prompt_sections(oversized_vfx)[2]["VIDEO_VFX"]) == (
    prompt.MAX_VIDEO_VFX_CHARS + 1
)
agent_source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
assert "_MAX_USER_DESCRIPTION_FIELD_CHARS" not in agent_source
assert "_MAX_USER_VIDEO_VFX_CHARS" not in agent_source
assert "_assert_public_job_data_contract(machine_prompt)" not in agent_source

print(
    "HMB Prompt field authority regression: PASS "
    "(31 field combinations, exact transcript, no QA display state, opaque Agent transport)"
)
