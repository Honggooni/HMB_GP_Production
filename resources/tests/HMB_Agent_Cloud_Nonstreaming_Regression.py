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
node._hmb_rules_active = True
node._last_raw_output = None
node.parameter_output_values = {}


def set_value(self, name: str, value: object, *args, **kwargs) -> None:
    self.parameter_output_values[name] = value


node.set_parameter_value = MethodType(set_value, node)
fake_agent = FakeAgent()
result = node._process(fake_agent, "protected prompt")
assert result is fake_agent
assert fake_agent.tasks[0].prompt_driver.stream is False
assert fake_agent.run_calls == [("protected prompt",)]
assert node._last_raw_output == "FINAL NONSTREAMING RESULT"
assert node.parameter_output_values["output"] == "FINAL NONSTREAMING RESULT"


class TaskOutputAgent(FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.output = None
        self.tasks[0].output = FakeOutput("")

    def run(self, *args: object) -> None:
        self.run_calls.append(args)
        self.tasks[0].output = FakeOutput("FINAL TASK OUTPUT")


task_output_agent = TaskOutputAgent()
assert node._process(task_output_agent, "protected prompt") is task_output_agent
assert node.parameter_output_values["output"] == "FINAL TASK OUTPUT"


class ErrorArtifact:
    def __str__(self) -> str:
        return "private provider payload"


class InnerErrorAgent(FakeAgent):
    def run(self, *args: object) -> None:
        self.run_calls.append(args)
        self.output = FakeOutput(ErrorArtifact())


try:
    node._process(InnerErrorAgent(), "protected prompt")
except RuntimeError as exc:
    assert "error artifact" in str(exc)
else:
    raise AssertionError("inner ErrorArtifact was published as FINAL TEXT")
assert node._hmb_native_failure_code == "MODEL_PROVIDER"


class MissingTaskAgent:
    tasks: list[object] = []


try:
    node._process(MissingTaskAgent(), "protected prompt")
except RuntimeError as exc:
    assert "host adapter" in str(exc)
else:
    raise AssertionError("missing Standard Agent task was not rejected")
assert node._hmb_native_failure_stage == "build_agent"
assert node._hmb_native_failure_code == "HOST_ADAPTER"


class RateLimitError(RuntimeError):
    status_code = 429


assert agent._hmb_native_failure_code(RateLimitError("private provider text")) == (
    "MODEL_RATE_LIMIT"
)
assert agent._hmb_native_failure_code(KeyError("text")) == "HOST_ADAPTER"

protected_source = inspect.getsource(
    agent.HMBAgentLibrary._run_protected_agent_non_streaming
)
assert ".run_stream(" not in protected_source
assert "prompt_driver.stream = False" in protected_source

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

# Only mode remains the installed Standard Agent implementation. The temporary
# base method keeps this assertion runnable in public CI where Griptape itself
# may not be installed and HMBAgentLibrary therefore uses the lightweight stub.
base_agent = agent.HMBAgentLibrary.__mro__[1]
had_base_process = hasattr(base_agent, "_process")
original_base_process = getattr(base_agent, "_process", None)
only_calls: list[tuple[object, object]] = []


def only_process(self, native_agent, native_prompt):
    only_calls.append((native_agent, native_prompt))
    return "ONLY NATIVE RESULT"


setattr(base_agent, "_process", only_process)
try:
    node._hmb_rules_active = False
    assert node._process("native-agent", "native prompt") == "ONLY NATIVE RESULT"
finally:
    if had_base_process:
        setattr(base_agent, "_process", original_base_process)
    else:
        delattr(base_agent, "_process")
assert only_calls == [("native-agent", "native prompt")]

print("HMB_AGENT_CLOUD_NONSTREAMING=PASS")
