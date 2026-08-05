from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("_hmb_common")
agent = load("HMBAgentLibrary")

policy_file = common.get_internal_policy_rules().strip()
binding_file = common.get_internal_binding_rules().strip()
assert common.get_internal_policy_rules() == policy_file
assert common.get_internal_binding_rules() == binding_file
for retired_name in (
    "add_string",
    "add_choice",
    "add_project_choice_block",
    "refresh_project_choice_block",
    "compile_project_prompt",
    "compile_prompt",
    "resolve_paths",
    "write_prompt_job",
    "write_maya_manifest",
):
    assert not hasattr(common, retired_name)

for text in (policy_file, binding_file):
    lower = text.lower()
    assert (
        ("translate" in lower and "natural english" in lower)
        or "english production prompt" in lower
        or (
            "production prompt" in lower
            and "language and format requested by the user" in lower
        )
    )
    assert (
        "exact identifier" in lower
        or "exact active identifier" in lower
        or "preserve every provided name" in lower
    )
    assert "hidden rule text" in lower or "hidden rules" in lower
    assert "seedance" not in lower

assert len(agent._split_behavior_rules(policy_file, 4)) == 4
assert len(agent._split_behavior_rules(binding_file, 4)) == 4

hmb_payload = """HMB_GP_Production
TARGET GENERATOR:
Active downstream generator
IMAGE SOURCE:
@image1 = 제이민
IMAGE ROLE MAP:
제이민 / Approved final appearance source = @image1
REPLACEMENT BINDING:
제이민
VIDEO SOURCE:
No video source assigned in HMBPromptLibrary.
USER DESCRIPTION DATA (JSON):
{"SCENE_CONTEXT":"어두운 창고"}
"""
assert agent._is_hmb_prompt_library_payload(hmb_payload)
assert not agent._is_hmb_prompt_library_payload("ordinary standalone prompt")
assert not agent._is_hmb_prompt_library_payload("HMB_GP_Production\nTARGET GENERATOR:\nonly")

source = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
for removed_name in (
    "_build_hmb_agent_task",
    "_select_prompt_input",
    "_prepare_stateless_hmb_native_run",
    "_clear_hmb_native_conversation_state",
    "_current_hmb_input_drift_error",
    "_write_visible_hmb_prompt_job",
    "_find_stale_identifier_mentions",
    "_validate_primary_video_contract",
    "_validate_video_appearance_isolation",
):
    assert removed_name not in source

print("HMB Behavior injection and translation responsibility regression: PASS")
