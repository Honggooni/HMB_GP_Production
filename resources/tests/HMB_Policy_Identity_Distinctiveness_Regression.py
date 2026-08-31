from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import MethodType, SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent = load(
    "_hmb_policy_identity_distinctiveness_agent", "HMBAgentLibrary.py"
)
prompt = load(
    "_hmb_policy_identity_distinctiveness_prompt", "HMBPromptLibrary.py"
)


# Prompt and Agent share one signed contract identity. The local Agent does not
# interpret policy prose or manufacture a second semantic contract.
source_identity = agent._prompt_policy_source_identity()
assert agent._assert_prompt_policy_identity_matches_signed_runtime() == (
    source_identity
)
assert source_identity[0] == prompt.PROMPT_POLICY_SOURCE_VERSION
assert source_identity[1] == prompt.PROMPT_POLICY_SOURCE_CONTRACT_SHA256


def sanitizer_node(output: str, agent_state: dict | None = None):
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_node_deleted = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node._hmb_suppress_visible_publication = False
    node.parameter_output_values = {
        "agent": dict(agent_state or {}),
        "output": output,
        "logs": "",
    }

    def set_parameter_value(self, name, value, *args, **kwargs):
        self.parameter_output_values[name] = value

    node.set_parameter_value = MethodType(set_parameter_value, node)
    return node


# Natural-language policy results are publication data. No local phrase matcher
# may reject a terse, long, Korean, or policy-like generator instruction.
allowed_outputs = (
    "Render the approved shot.",
    "@image1의 캐릭터 정체성을 유지하고 @video1의 동작을 사용한다.",
    (
        "Use @image1 as the sole appearance authority while adapting lighting, "
        "shadow, exposure, atmosphere, camera timing, framing, and occlusion "
        "according to the authenticated production policy."
    ),
)
for value in allowed_outputs:
    node = sanitizer_node(value)
    assert node._secure_hmb_outputs() is False
    assert node.parameter_output_values["output"] == value
    assert node._hmb_last_sanitizer_status == "clean"


# Hidden rules remain non-public even though wording checks are gone.
private_wrapper = {
    "tasks": [],
    "rulesets": [{"name": "private", "rules": ["sealed policy text"]}],
    "memory": "public\nHMB VERIFIED FX/TIMING RUNTIME SCOPE (JSON):\nprivate",
}
node = sanitizer_node("Safe final generator text.", private_wrapper)
assert node._secure_hmb_outputs() is False
assert node.parameter_output_values["output"] == "Safe final generator text."
assert node.parameter_output_values["agent"]["rulesets"] == []
assert node.parameter_output_values["agent"]["memory"] == "public"


# A live Prompt's exact hashed machine snapshot is opaque Agent input.
prompt_node = prompt.HMBPromptLibrary(name="policy_identity_prompt")
visible = prompt_node._hmb_last_prompt_output
machine = prompt_node._hmb_last_machine_prompt_output
snapshot = {
    "schema": "hmb-prompt-paired-snapshot",
    "version": 1,
    "generation": 1,
    "visible_sha256": hashlib.sha256(visible.encode("utf-8")).hexdigest(),
    "machine_sha256": hashlib.sha256(machine.encode("utf-8")).hexdigest(),
    "machine_prompt": machine,
}
source = SimpleNamespace(
    _hmb_agent_prompt_snapshot=lambda _visible: dict(snapshot)
)
assert agent._paired_machine_prompt(
    SimpleNamespace(_hmb_verified_prompt_source_node=source), visible
) == machine
assert agent._is_private_hmb_runtime_prompt(machine)
assert "BEHAVIOR 1" not in visible
assert "BEHAVIOR 2" not in visible

print("HMB signed-policy identity / phrase-neutral non-exposure boundary: PASS")
