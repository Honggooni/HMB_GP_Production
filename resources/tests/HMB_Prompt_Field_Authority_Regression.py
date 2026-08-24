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


def expect_rejected(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("invalid user description contract was accepted")


def replace_user_data(package: str, payload: dict) -> str:
    lines = package.splitlines()
    assert lines[5] == prompt.USER_DESCRIPTION_DATA_HEADER
    lines[6] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return "\n".join(lines)


prompt = load("_hmb_prompt_field_authority_prompt", "HMBPromptLibrary.py")
agent = load("_hmb_prompt_field_authority_agent", "HMBAgentLibrary.py")

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
    job, user_data = agent._prompt_data_only_envelope(package)
    assert user_data == expected
    assert agent._assert_public_job_data_contract(package) == job
    assert "prompt_guidance" not in package
    assert "qa_coverage_not_provider_attention" not in package
    assert "HMB QA" not in package

# A transcript is exact text evidence only. It neither creates media nor adds a
# task/activation field to the public job contract.
transcript_state = prompt._default_widget_state()
transcript_state["text"]["PRESERVED_TEXT"] = field_values["PRESERVED_TEXT"]
transcript_package = prompt._build_data_only_prompt_package(transcript_state)
transcript_job, transcript_user_data = agent._prompt_data_only_envelope(
    transcript_package
)
assert transcript_job["images"] == []
assert transcript_job["videos"] == []
assert set(transcript_user_data) == {"PRESERVED_TEXT"}
assert transcript_user_data["PRESERVED_TEXT"] == field_values["PRESERVED_TEXT"]
assert all("lip" not in key.casefold() for key in transcript_job)

# Python normalization and the Agent boundary enforce the same per-field limits.
limit_state = prompt._default_widget_state()
for key in field_names:
    limit_state["text"][key] = "V" * (
        prompt.MAX_VIDEO_VFX_CHARS
        if key == "VIDEO_VFX"
        else prompt.MAX_DESCRIPTION_CHARS
    )
limit_package = prompt._build_data_only_prompt_package(limit_state)
agent._assert_public_job_data_contract(limit_package)

base_package = prompt._build_data_only_prompt_package(prompt._default_widget_state())
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_user_data(
            base_package,
            {"PROJECT_STYLE_LOOK": "X" * (prompt.MAX_DESCRIPTION_CHARS + 1)},
        )
    )
)
expect_rejected(
    lambda: agent._assert_public_job_data_contract(
        replace_user_data(
            base_package,
            {"VIDEO_VFX": "X" * (prompt.MAX_VIDEO_VFX_CHARS + 1)},
        )
    )
)

print(
    "HMB Prompt field authority regression: PASS "
    "(31 field combinations, exact transcript, no QA display state, server limits)"
)
