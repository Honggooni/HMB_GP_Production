from pathlib import Path
import importlib.util
import sys

from _hmb_private_policy_fixture import install_private_policy_reader

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
prompt = load("HMBPromptLibrary")
install_private_policy_reader(common)
if agent._hmb is not common:
    install_private_policy_reader(agent._hmb)

policy_file, binding_file = common._load_verified_behavior_documents()
policy_file = policy_file.strip()
binding_file = binding_file.strip()
reloaded_policy, reloaded_binding = common._load_verified_behavior_documents()
assert reloaded_policy.strip() == policy_file
assert reloaded_binding.strip() == binding_file
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
        or ("preserve" in lower and "provided name" in lower)
    )
    assert "seedance" not in lower

assert len(agent._split_behavior_rules(policy_file, 4)) == 4
assert len(agent._split_behavior_rules(binding_file, 4)) == 4

prompt_state = prompt._default_widget_state()
prompt_state["text"]["SCENE_CONTEXT"] = "어두운 창고"
hmb_payload = prompt._build_data_only_prompt_package(prompt_state)
assert agent._is_hmb_prompt_library_payload(hmb_payload)
payload_lines = hmb_payload.splitlines()
assert len(payload_lines) == 7
assert payload_lines[5] == "USER DESCRIPTION DATA (JSON):"
assert __import__("json").loads(payload_lines[6]) == {
    "SCENE_CONTEXT": "어두운 창고",
}
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
