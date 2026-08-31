from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STANDARD_ROOT = (
    Path.home()
    / "Documents"
    / "GriptapeNodes"
    / "libraries"
    / "griptape-nodes-library-standard"
)
STANDARD_ROOT = Path(
    os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", DEFAULT_STANDARD_ROOT)
)

os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = str(STANDARD_ROOT)
sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as module  # noqa: E402
import HMBPromptLibrary as prompt_module  # noqa: E402
from _hmb_private_policy_fixture import install_private_policy_reader  # noqa: E402


# A source checkout can exist without the Standard Library's import-time
# dependencies being available to this regression interpreter.  Exercise the
# real boundary only when production resolved the actual Standard Agent class;
# the stub boundary remains covered by the other Agent regressions.
if module._BuiltinAgent is None:
    print("HMB_REAL_STANDARD_AGENT_BOUNDARY=SKIP (standard Agent not importable)")
    raise SystemExit(0)


node = module.HMBAgentLibrary(name="hmb_real_standard_boundary")
assert node._hmb_rules_active is False
assert node._hmb_capture_publications is False

base_agent = module.HMBAgentLibrary.__mro__[1]
original_process = base_agent.process


def fake_native_process(self):
    self.append_value_to_parameter("logs", "started")

    def native_scheduler_step():
        self.append_value_to_parameter("output", "PRIVATE_STREAM_FRAGMENT")
        self.append_value_to_parameter("logs", "PRIVATE_TRACE_FRAGMENT")
        return {"scheduler": "result"}

    scheduler_result = yield native_scheduler_step
    assert scheduler_result == {"scheduler": "result"}
    self.set_parameter_value("output", "FINAL_SAFE_OUTPUT")
    return "native-return"


try:
    base_agent.process = fake_native_process
    node._hmb_rules_active = True
    generator = node._run_native_agent_once()
    protected_step = next(generator)
    assert callable(protected_step)
    scheduler_result = protected_step()
    assert "PRIVATE_STREAM_FRAGMENT" not in str(node.parameter_output_values)
    try:
        generator.send(scheduler_result)
    except StopIteration as stop:
        assert stop.value == "native-return"
    else:
        raise AssertionError("protected native generator did not complete")
    assert node.parameter_output_values["output"] == "FINAL_SAFE_OUTPUT"
    assert "PRIVATE_STREAM_FRAGMENT" not in node.parameter_output_values["output"]

    def failing_native_process(self):
        def failing_scheduler_step():
            raise RuntimeError("PRIVATE_PROVIDER_FAILURE_DETAIL")

        yield failing_scheduler_step

    base_agent.process = failing_native_process
    failed = module.HMBAgentLibrary(name="hmb_real_standard_failure_boundary")
    failed._hmb_rules_active = True
    generator = failed._run_native_agent_once()
    protected_step = next(generator)
    assert protected_step() is None
    try:
        generator.send(None)
    except RuntimeError as exc:
        assert "PRIVATE_PROVIDER_FAILURE_DETAIL" not in str(exc)
    else:
        raise AssertionError("protected scheduler failure did not fail closed")
finally:
    base_agent.process = original_process


# Keep the installed Standard Agent's real process implementation in place and
# replace only its billable scheduler step. This proves that the native Agent
# object receives exactly the two sealed 4-rule sets and that the callable-yield
# contract remains intact through final publication and cleanup.
install_private_policy_reader(module._hmb)
standard_module = inspect.getmodule(base_agent)
assert standard_module is not None
original_resolve_cloud_api_key = standard_module.resolve_cloud_api_key
original_require_model_invocation_sync = standard_module.require_model_invocation_sync
original_try_throw_error = standard_module.try_throw_error

canonical_prompt = prompt_module._build_data_only_prompt_package(
    prompt_module._default_widget_state()
)
real_node = module.HMBAgentLibrary(name="hmb_real_standard_4x4_boundary")
real_node._has_canonical_hmb_prompt_connection = types.MethodType(
    lambda self: True,
    real_node,
)
real_node._model_access.raise_if_denied = lambda *args, **kwargs: None
# Production Shot routing executes from the hidden, router-owned Prompt input.
# Keep the private machine envelope out of the native public Prompt editor and
# seed only that authoritative input so this fixture matches current topology.
real_node.set_parameter_value(
    module._AGENT_SHOT_PROMPT_INPUT_PARAMETER,
    canonical_prompt,
)
stored_canonical_prompt = getattr(
    real_node.get_parameter_value(module._AGENT_SHOT_PROMPT_INPUT_PARAMETER),
    "value",
    None,
)
if stored_canonical_prompt is None:
    stored_canonical_prompt = real_node.get_parameter_value(
        module._AGENT_SHOT_PROMPT_INPUT_PARAMETER
    )
stored_canonical_prompt = str(stored_canonical_prompt)
real_node.set_parameter_value("additional_context", "CALLER_CONTEXT_MUST_RUN")
real_node.set_parameter_value("rulesets", ["CALLER_RULE_MUST_RUN"])
real_node.set_parameter_value(
    "agent_memory",
    {"runs": [{"input": "before", "output": "before"}]},
)
real_node.set_parameter_value(
    "output_schema",
    {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
)

captured = {}


def non_billable_model_step(self, agent, prompt):
    rulesets = list(agent.rulesets or [])
    task = agent.tasks[0]
    prompt_value = getattr(prompt, "value", prompt)
    runtime_prompt = str(prompt_value)
    captured["prompt_exact"] = runtime_prompt == (
        self._hmb_runtime_prompt + "\nCALLER_CONTEXT_MUST_RUN"
    )
    captured["public_prompt_prefix_exact"] = runtime_prompt.startswith(
        stored_canonical_prompt.rstrip()
        + "\n"
        + module._RUNTIME_FX_SCOPE_HEADER
        + "\n"
    )
    captured["caller_context_present"] = "CALLER_CONTEXT_MUST_RUN" in runtime_prompt
    captured["rule_counts"] = [len(ruleset.rules or []) for ruleset in rulesets]
    captured["ruleset_names"] = [str(ruleset.name or "") for ruleset in rulesets]
    captured["tool_count"] = len(getattr(task, "tools", ()) or ())
    captured["output_schema"] = getattr(task, "output_schema", None)
    captured["memory_runs"] = len(
        getattr(getattr(agent, "conversation_memory", None), "runs", ()) or ()
    )
    sealed_rule = rulesets[-2].rules[0]
    captured["sealed_rule"] = str(getattr(sealed_rule, "value", sealed_rule))
    self.append_value_to_parameter("output", "PRIVATE_REAL_STREAM_FRAGMENT")
    self.append_value_to_parameter("logs", captured["sealed_rule"])
    task.output = standard_module.TextArtifact(value="FINAL_SAFE_OUTPUT")
    self._last_raw_output = "FINAL_SAFE_OUTPUT"
    return agent


try:
    standard_module.resolve_cloud_api_key = lambda: "non-billable-test-key"
    standard_module.require_model_invocation_sync = lambda *args, **kwargs: None
    standard_module.try_throw_error = lambda *args, **kwargs: None
    real_node._process = types.MethodType(non_billable_model_step, real_node)

    generator = real_node.process()
    protected_step = next(generator)
    assert callable(protected_step)
    assert "PRIVATE_REAL" not in str(real_node.parameter_output_values)
    scheduler_result = protected_step()
    assert "PRIVATE_REAL" not in str(real_node.parameter_output_values)
    try:
        generator.send(scheduler_result)
    except StopIteration:
        pass
    else:
        raise AssertionError("real Standard Agent boundary did not complete")
finally:
    standard_module.resolve_cloud_api_key = original_resolve_cloud_api_key
    standard_module.require_model_invocation_sync = (
        original_require_model_invocation_sync
    )
    standard_module.try_throw_error = original_try_throw_error

assert captured["prompt_exact"] is True
assert captured["public_prompt_prefix_exact"] is True
assert captured["caller_context_present"] is True
assert captured["rule_counts"] == [1, 4, 4]
assert captured["ruleset_names"][0] == "behavior_1"
sealed_ruleset_names = captured["ruleset_names"][-2:]
assert len(set(sealed_ruleset_names)) == 2
assert all(
    len(name) == 32 and all(character in "0123456789abcdef" for character in name)
    for name in sealed_ruleset_names
)
assert captured["tool_count"] == 0
assert captured["output_schema"] is not None
assert captured["memory_runs"] == 1
assert real_node.parameter_output_values["output"] == "FINAL_SAFE_OUTPUT"
assert captured["sealed_rule"] not in str(real_node.parameter_output_values)
assert "CALLER_RULE_MUST_RUN" in str(real_node.parameter_output_values["agent"])
assert all(
    name not in str(real_node.parameter_output_values["agent"])
    for name in sealed_ruleset_names
)
assert real_node._hmb_rules_active is False
assert real_node._hmb_capture_publications is False
assert real_node._hmb_policy == ""
assert real_node._hmb_binding == ""
assert real_node._hmb_policy_rules == []
assert real_node._hmb_binding_rules == []
assert real_node._hmb_ruleset_names == ("", "")
captured["sealed_rule"] = ""

print("HMB_REAL_STANDARD_AGENT_BOUNDARY=PASS")
