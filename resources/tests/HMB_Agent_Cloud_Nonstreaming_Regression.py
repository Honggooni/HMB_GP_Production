from __future__ import annotations

import inspect
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

protected_source = inspect.getsource(
    agent.HMBAgentLibrary._run_protected_agent_non_streaming
)
assert ".run_stream(" not in protected_source
assert "prompt_driver.stream = False" in protected_source

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
