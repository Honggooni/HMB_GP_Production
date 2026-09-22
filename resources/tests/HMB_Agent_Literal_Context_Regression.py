from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
STANDARD_ROOT = Path(
    os.environ.get(
        "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH",
        Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard",
    )
)
os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = str(STANDARD_ROOT)
sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent_module  # noqa: E402
import HMBPromptLibrary as prompt_module  # noqa: E402


CONTEXT_HEADER = "\n\nHMB ADDITIONAL CONTEXT DATA (JSON):\n"
CONTEXT_END = "\nEND HMB ADDITIONAL CONTEXT DATA"
preserved_text = (
    '[On-screen Text] {{SIGN}} / "한국어 간판"\n'
    '[Dialogue] {% if SIGN %}그대로{% endif %}\n'
    '[Lyrics] {{ unknown.value }} {# 문자 그대로 #} {{ 6 * 7 }}'
)
state = prompt_module._default_widget_state()
state["text"]["PRESERVED_TEXT"] = preserved_text
visible_prompt = prompt_module._build_prompt_package(state)
machine_prompt = prompt_module._build_data_only_prompt_package(state)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


snapshot = {
    "schema": agent_module._PAIRED_PROMPT_SNAPSHOT_SCHEMA,
    "version": agent_module._PAIRED_PROMPT_SNAPSHOT_VERSION,
    "generation": 1,
    "visible_sha256": digest(visible_prompt),
    "machine_sha256": digest(machine_prompt),
    "machine_prompt": machine_prompt,
}


class PairedPromptSource:
    @staticmethod
    def _hmb_agent_prompt_snapshot(expected_visible: str) -> dict:
        assert expected_visible == visible_prompt
        return dict(snapshot)

    @staticmethod
    def _hmb_agent_shot_context(_prompt_value: str) -> dict:
        return {}

    @staticmethod
    def _hmb_shot_channel_subscription() -> dict:
        return {"participant_kind": "prompt", "enabled": False}


source = PairedPromptSource()
owner = SimpleNamespace(_hmb_verified_prompt_source_node=source)
verified_machine = agent_module._paired_machine_prompt(owner, visible_prompt)
assert verified_machine == machine_prompt
user_data = json.loads(machine_prompt.split("USER DESCRIPTION DATA (JSON):\n", 1)[1])
assert user_data["PRESERVED_TEXT"] == preserved_text

context = {
    "SIGN": "THIS MUST NOT SUBSTITUTE THE APPROVED SIGN",
    "label": "한국어 추가 자료 {{SIGN}}",
    "nested": {"quoted": '{% if SIGN %}원문{% endif %}', "values": [1, True, None]},
}
original_context = copy.deepcopy(context)
original_snapshot = copy.deepcopy(snapshot)
node = object.__new__(agent_module.HMBAgentLibrary)
node._hmb_rules_active = True
merged = node._handle_additional_context(verified_machine, context)
assert merged.startswith(machine_prompt + CONTEXT_HEADER)
assert merged[: len(machine_prompt)].encode("utf-8") == machine_prompt.encode("utf-8")
assert digest(merged[: len(machine_prompt)]) == snapshot["machine_sha256"]
assert json.loads(merged[len(machine_prompt) + len(CONTEXT_HEADER) : -len(CONTEXT_END)]) == context
assert merged.endswith(CONTEXT_END)
assert context == original_context and snapshot == original_snapshot
assert agent_module._paired_machine_prompt(owner, visible_prompt) == machine_prompt

# An empty mapping must not trigger any template interpretation either.
assert node._handle_additional_context(machine_prompt, {}).startswith(machine_prompt)

# Prove that non-HMB and non-dict calls delegate with the exact original values.
# This portable branch runs even without an installed Standard Agent runtime.
base_agent = agent_module.HMBAgentLibrary.__mro__[1]
native_handler = getattr(base_agent, "_handle_additional_context", None)
delegated = []


def native_sentinel(self, prompt, additional_context):
    delegated.append((self, prompt, additional_context))
    return "NATIVE_CONTEXT_RESULT"


try:
    base_agent._handle_additional_context = native_sentinel
    for active, value in ((False, context), (False, {}), (True, "추가 설명"), (True, 42)):
        node._hmb_rules_active = active
        assert node._handle_additional_context(machine_prompt, value) == "NATIVE_CONTEXT_RESULT"
        assert delegated[-1][1] is machine_prompt and delegated[-1][2] is value
finally:
    if native_handler is None:
        del base_agent._handle_additional_context
    else:
        base_agent._handle_additional_context = native_handler

print("HMB_AGENT_LITERAL_CONTEXT_CORE=PASS")

if agent_module._BuiltinAgent is None:
    print("HMB_AGENT_LITERAL_CONTEXT_NATIVE=SKIP (standard Agent not importable)")
    raise SystemExit(0)

# Run the real installed native lifecycle, replacing only its billable model
# step. This catches a gate that is enabled too late, and a later template pass.
from _hmb_bundled_policy_session import install_bundled_policy_session  # noqa: E402

install_bundled_policy_session(agent_module._hmb)
native_module = inspect.getmodule(base_agent)
assert native_module is not None
original_step = base_agent._process
original_key = native_module.resolve_cloud_api_key
original_invocation = native_module.require_model_invocation_sync
original_throw = native_module.try_throw_error
live = agent_module.HMBAgentLibrary(name="hmb_literal_context_native")
assert live._hmb_rules_active is False
live._hmb_verified_prompt_source_node = source
live._refresh_agent_shot_route = lambda **_kwargs: {"ok": True, "code": "ready", "changed": 0}
live._has_canonical_hmb_prompt_connection = lambda: True
live._model_access.raise_if_denied = lambda *args, **kwargs: None
live.set_parameter_value(agent_module._AGENT_SHOT_PROMPT_INPUT_PARAMETER, visible_prompt)
# The native text editor serializes a dict when entered through its setter.
# Seed the typed input value directly to exercise the dictionary branch that
# Standard Agent explicitly supports for upstream/restored context values.
live.parameter_values["additional_context"] = context
assert isinstance(live.get_parameter_value("additional_context"), dict)
captured = []


def no_model_call(self, agent, prompt):
    value = str(getattr(prompt, "value", prompt))
    assert self._hmb_rules_active is True
    assert self._hmb_runtime_prompt == machine_prompt
    assert value == merged + "\n\n" + agent_module._AGENT_ENGLISH_OUTPUT_CONTRACT
    assert digest(value[: len(machine_prompt)]) == snapshot["machine_sha256"]
    captured.append(value)
    agent.tasks[0].output = native_module.TextArtifact(value="Literal context boundary passed.")
    self._last_raw_output = "Literal context boundary passed."
    return agent


try:
    native_module.resolve_cloud_api_key = lambda: "offline-non-billable-test"
    native_module.require_model_invocation_sync = lambda *args, **kwargs: None
    native_module.try_throw_error = lambda *args, **kwargs: None
    base_agent._process = no_model_call
    iterator = live.process()
    pending = next(iterator)
    assert callable(pending)
    result = pending()
    try:
        iterator.send(result)
    except StopIteration:
        pass
    else:
        raise AssertionError("a second native/model step was requested")
finally:
    base_agent._process = original_step
    native_module.resolve_cloud_api_key = original_key
    native_module.require_model_invocation_sync = original_invocation
    native_module.try_throw_error = original_throw

assert len(captured) == 1
assert live._hmb_rules_active is False
assert live._hmb_runtime_prompt == ""
assert snapshot == original_snapshot and context == original_context
assert "{{SIGN}}" not in str(live.parameter_output_values)

# Ordinary Agent workflows still use the installed Standard Agent's actual
# Jinja semantics, including after the protected HMB execution was cleared.
ordinary_prompt = "{{SIGN}} / 한국어 / {% if flag %}YES{% endif %}"
assert live._handle_additional_context(ordinary_prompt, {"SIGN": "간판", "flag": True}) == "간판 / 한국어 / YES"
assert live._handle_additional_context("{{SIGN}}", {"unrelated": 1}) == ""
assert live._handle_additional_context("{{SIGN}}", "설명") == "{{SIGN}}\n설명"
assert live._handle_additional_context("{{SIGN}}", 42) == "{{SIGN}}\n42"
print("HMB_AGENT_LITERAL_CONTEXT_NATIVE=PASS (real lifecycle; no model invocation)")
