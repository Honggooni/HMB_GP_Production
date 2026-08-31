from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
from types import MethodType


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent  # noqa: E402


class FakeDriver:
    def __init__(self) -> None:
        self.stream = True


class FakeOutput:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


class FakeAgent:
    def __init__(self) -> None:
        self.tasks = [type("FakeTask", (), {"prompt_driver": FakeDriver()})()]
        self.output = FakeOutput("")
        self.run_calls: list[tuple[object, ...]] = []

    def run(self, *args: object) -> None:
        self.run_calls.append(args)
        self.output = FakeOutput("FINAL NONSTREAMING RESULT")


node = object.__new__(agent.HMBAgentLibrary)
node._last_raw_output = None
node.parameter_output_values = {}


def set_value(self, name: str, value: object, *args, **kwargs) -> None:
    self.parameter_output_values[name] = value


node.set_parameter_value = MethodType(set_value, node)
base_agent = agent.HMBAgentLibrary.__mro__[1]
had_base_process = hasattr(base_agent, "_process")
original_base_process = getattr(base_agent, "_process", None)
native_calls: list[tuple[object, object]] = []


def native_process(self, native_agent, native_prompt):
    native_calls.append((native_agent, native_prompt))
    return native_agent


setattr(base_agent, "_process", native_process)
try:
    for rules_active in (False, True):
        node._hmb_rules_active = rules_active
        fake_agent = FakeAgent()
        result = node._process(fake_agent, "native prompt")
        assert result is fake_agent
        assert fake_agent.tasks[0].prompt_driver.stream is True
        assert fake_agent.run_calls == []
finally:
    if had_base_process:
        setattr(base_agent, "_process", original_base_process)
    else:
        delattr(base_agent, "_process")
assert [prompt for _native_agent, prompt in native_calls] == [
    "native prompt", "native prompt",
]

# Protected HMB execution now has Standard Agent input parity: only the exact
# authenticated prompt bytes are substituted, while ordinary scalar/list
# inputs and caller rulesets remain native inputs.
had_base_get = hasattr(base_agent, "get_parameter_value")
had_base_get_list = hasattr(base_agent, "get_parameter_list_value")
original_base_get = getattr(base_agent, "get_parameter_value", None)
original_base_get_list = getattr(base_agent, "get_parameter_list_value", None)
native_values = {
    "prompt": "VISIBLE PROMPT",
    "additional_context": "CALLER CONTEXT",
    "agent_memory": {"runs": [{"input": "before", "output": "before"}]},
    "output_schema": {"type": "object"},
    "include_details": True,
}
native_lists = {
    "rulesets": ["CALLER RULE"],
    "tools": ["CALLER TOOL"],
}
setattr(base_agent, "get_parameter_value", lambda _self, name: native_values.get(name))
setattr(base_agent, "get_parameter_list_value", lambda _self, name: native_lists.get(name, []))
try:
    node._hmb_rules_active = True
    node._hmb_runtime_prompt = "PRIVATE RUNTIME PROMPT"
    node._hmb_native_prompt_read_active = False
    node._hmb_ruleset_names = ("a" * 32, "b" * 32)
    node._hmb_policy_rules = ["project-1", "project-2", "project-3", "project-4"]
    node._hmb_binding_rules = ["shot-1", "shot-2", "shot-3", "shot-4"]
    assert node.get_parameter_value("prompt") == "VISIBLE PROMPT"
    assert node.get_parameter_value("additional_context") == "CALLER CONTEXT"
    assert node.get_parameter_value("agent_memory") == native_values["agent_memory"]
    assert node.get_parameter_value("output_schema") == native_values["output_schema"]
    assert node.get_parameter_value("include_details") is True
    assert node.get_parameter_list_value("tools") == ["CALLER TOOL"]
    merged_rules = node.get_parameter_list_value("rulesets")
    assert merged_rules[0] == "CALLER RULE"
    assert [entry["name"] for entry in merged_rules[1:]] == ["a" * 32, "b" * 32]
    node._hmb_native_prompt_read_active = True
    assert node.get_parameter_value("prompt") == "PRIVATE RUNTIME PROMPT"
finally:
    node._hmb_rules_active = False
    node._hmb_native_prompt_read_active = False
    if had_base_get:
        setattr(base_agent, "get_parameter_value", original_base_get)
    else:
        delattr(base_agent, "get_parameter_value")
    if had_base_get_list:
        setattr(base_agent, "get_parameter_list_value", original_base_get_list)
    else:
        delattr(base_agent, "get_parameter_list_value")


class RateLimitError(RuntimeError):
    status_code = 429


assert agent._hmb_native_failure_code(RateLimitError("private provider text")) == (
    "MODEL_RATE_LIMIT"
)
assert agent._hmb_native_failure_code(KeyError("text")) == "HOST_ADAPTER"

process_adapter_source = inspect.getsource(agent.HMBAgentLibrary._process)
assert "_run_protected_agent_non_streaming" not in process_adapter_source
assert "prompt_driver.stream = False" not in process_adapter_source
assert "native_processor" in process_adapter_source

process_source = inspect.getsource(agent.HMBAgentLibrary.process)
for retired_gate in (
    "_assert_public_job_data_contract",
    "_assert_fx_timing_source_contract",
    "_assert_fx_candidate_matches_signed_runtime",
    "_derive_fx_timing_runtime_scope",
    "_compose_hmb_runtime_prompt",
):
    assert retired_gate not in process_source

manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
agent_manifest = next(
    item for item in manifest["nodes"] if item["class_name"] == "HMBAgentLibrary"
)
model_usage = next(
    item
    for item in agent_manifest["metadata"]["declarations"]
    if item.get("type") == "model_usage"
)
assert model_usage["model_ids"] == [
    "gtc_claude_sonnet_5",
    "gtc_claude_opus_5",
    "gtc_claude_haiku_4_5",
    "gtc_gemini_3_6_flash",
    "gtc_gemini_3_5_flash",
    "gtc_gemini_3_5_flash_lite",
    "gtc_gemini_3_1_pro",
    "gtc_gemini_3_1_flash_lite",
    "gtc_gemini_3_flash",
    "gtc_gemini_2_5_pro",
    "gtc_gemini_2_5_flash",
    "gtc_gemini_2_5_flash_lite",
    "gtc_gpt_5_2",
    "gtc_gpt_5_2_chat",
    "gtc_gpt_5_1",
    "gtc_gpt_5",
    "gtc_gpt_5_mini",
    "gtc_gpt_5_nano",
    "gtc_gpt_4_1",
    "gtc_gpt_4_1_mini",
    "gtc_gpt_4_1_nano",
    "gtc_gpt_4o",
    "gtc_o4_mini",
    "gtc_o3",
    "gtc_o3_mini",
    "gtc_o1",
    "gtc_deepseek_v3",
    "gtc_deepseek_r1",
    "gtc_llama_3_3_70b",
    "gtc_llama_3_1_70b",
]
model_catalog = next(
    item
    for item in manifest["metadata"]["declarations"]
    if item.get("type") == "model_catalog"
)
catalog_model_ids = {
    model_id
    for provider in model_catalog["providers"].values()
    for model_id in provider["models"]
}
assert len(catalog_model_ids) == 30
assert catalog_model_ids == set(model_usage["model_ids"])

# Direct server-policy disclosure is the only text-content guard retained.
# It is exact and in-memory only: no semantic, translated, encoded, or fuzzy
# inspection is reintroduced.
exact_policy_line = "POLICY SECRET " + ("X" * 96)
node._hmb_node_deleted = False
node._hmb_policy = exact_policy_line
node._hmb_binding = ""
node._hmb_policy_rules = [exact_policy_line]
node._hmb_binding_rules = []
node._hmb_suppress_visible_publication = True
node.parameter_output_values = {
    "agent": {"prompt": exact_policy_line},
    "output": "prefix\n" + exact_policy_line,
    "logs": exact_policy_line,
}
assert node._secure_hmb_outputs() is False
assert node.parameter_output_values["agent"] == {}
assert node.parameter_output_values["output"] == agent._PUBLIC_OUTPUT_BLOCKED
assert node.parameter_output_values["logs"] == agent._PUBLIC_OUTPUT_BLOCKED
assert node._hmb_last_sanitizer_status == "policy"

node._hmb_policy = ""
node._hmb_policy_rules = []
node.parameter_output_values = {
    "agent": {},
    "output": "ordinary generator instruction",
    "logs": "",
}
assert node._secure_hmb_outputs() is False
assert node.parameter_output_values["output"] == "ordinary generator instruction"
assert node._hmb_last_sanitizer_status == "clean"

print("HMB_AGENT_STANDARD_PROCESSOR_PARITY=PASS")
