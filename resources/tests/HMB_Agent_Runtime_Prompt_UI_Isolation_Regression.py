from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "_hmb_agent_runtime_prompt_ui_isolation_regression",
    ROOT / "HMBAgentLibrary.py",
)
assert SPEC is not None and SPEC.loader is not None
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)

assert agent._agent_widget_value(execution_phase="authorizing")[
    "execution_phase"
] == "authorizing"
assert agent._agent_widget_value(execution_phase="private-policy-text")[
    "execution_phase"
] == ""


node = object.__new__(agent.HMBAgentLibrary)
node._hmb_node_deleted = False
node._hmb_rules_active = False
node._hmb_capture_publications = False
node._hmb_native_prompt_read_active = False
node._hmb_prompt_preview_syncing = False
node._hmb_prompt_preview_active = False
node._hmb_prompt_preview_value = ""
node._hmb_prompt_before_preview = "Manual Only prompt"
agent.DataNode.__init__(node, name="agent_runtime_prompt_ui_isolation")
node.add_parameter(
    agent.Parameter(
        name=agent._AGENT_PROMPT_INPUT_PARAMETER,
        type="str",
        default_value="Manual Only prompt",
    )
)
node._ensure_hmb_shot_prompt_input()

visible = "HMB_GP_Production\n\nIMAGE SOURCE:\n@image1 = Jett_02\n"
# The private Prompt payload is deliberately opaque here. UI isolation must be
# based on exact active bytes, not recognizable headers or content markers.
machine = "PRIVATE RUNTIME PROMPT\nopaque authenticated bytes\n"
node.set_parameter_value(agent._AGENT_SHOT_PROMPT_INPUT_PARAMETER, visible)
node._hmb_shot_channel_subscription = lambda: {"enabled": True}
node._refresh_routed_prompt_preview()
assert node._native_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER) == visible

# Simulate a host graph/UI refresh reading the protected value during an Agent
# run and echoing it back through either setter path. The public prompt must
# remain the concise Prompt document.
node._hmb_rules_active = True
node._hmb_runtime_prompt = machine
assert node.get_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER) == visible
node._hmb_native_prompt_read_active = True
assert node.get_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER) == machine
node._hmb_native_prompt_read_active = False
node.set_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER, machine)
assert node._native_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER) == visible
prompt_parameter = agent._parameter_by_name(node, agent._AGENT_PROMPT_INPUT_PARAMETER)
assert node.before_value_set(prompt_parameter, machine) == visible

# The narrow guard must still deliver the exact runtime envelope to the native
# Agent while advancing its generator, then close again before host/UI work.
observed_native_prompts: list[str] = []
original_base_process = getattr(agent._BaseAgent, "process", None)


def fake_native_process(self):
    observed_native_prompts.append(str(self.get_parameter_value("prompt") or ""))
    yield lambda: "native-step"


agent._BaseAgent.process = fake_native_process
try:
    node._hmb_native_calls_this_process = 0
    node._hmb_lifecycle_generation = 1
    node._hmb_lifecycle_is_live = lambda _generation: True
    node._hmb_publication_buffer = {"output": "", "logs": ""}
    node._hmb_scheduler_step_failed = False
    node.parameter_output_values = {"output": "", "logs": ""}
    native_wrapper = node._run_native_agent_once(1)
    protected_step = next(native_wrapper)
    assert callable(protected_step)
    assert observed_native_prompts == [machine]
    assert node._hmb_native_prompt_read_active is False
    assert node.get_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER) == visible
    native_wrapper.close()
finally:
    if original_base_process is None:
        delattr(agent._BaseAgent, "process")
    else:
        agent._BaseAgent.process = original_base_process

# An active private prompt is recognized only by exact runtime bytes, never by
# content markers. A near miss must remain ordinary user-authored text.
agent.DataNode.set_parameter_value(node, agent._AGENT_PROMPT_INPUT_PARAMETER, machine)
stored_after_direct_base_set = node._native_parameter_value(
    agent._AGENT_PROMPT_INPUT_PARAMETER
)
assert node._matches_active_private_runtime_prompt(stored_after_direct_base_set)
assert not node._matches_active_private_runtime_prompt(machine + "\n")
assert not hasattr(agent, "_is_private_hmb_runtime_prompt")
if node._matches_active_private_runtime_prompt(stored_after_direct_base_set):
    node._set_native_prompt_preview(visible, enabled=True)
assert node._native_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER) == visible
assert machine not in node._hmb_prompt_before_preview

node._clear_hmb_runtime_policy()
assert node._hmb_native_prompt_read_active is False
assert node._hmb_runtime_prompt == ""

print(
    "HMB Agent runtime prompt UI isolation regression: PASS "
    "(Picker-triggered host echo blocked, public preview restored, native read scoped)"
)
