from __future__ import annotations

import importlib.util
from pathlib import Path
from types import MethodType, SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    module_name = f"_hmb_english_video_progression_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


agent = load("HMBAgentLibrary")
prompt = load("HMBPromptLibrary")
picker = load("HMBVideoPickerLibrary")


# Korean and English remain valid source languages. The paired machine prompt
# stays byte-exact source data; the Agent adds exactly one private contract only
# after native caller context has been merged into the model-bound prompt.
machine_prompt = "USER DESCRIPTION DATA (JSON):\n{\"scene\":\"천천히 줌인\"}\n"
model_prompt = agent._with_english_agent_output_contract(
    machine_prompt.rstrip() + "\n호출자 문맥"
)
assert model_prompt.startswith(machine_prompt.rstrip() + "\n호출자 문맥\n\n")
assert "천천히 줌인" in model_prompt
assert model_prompt.count(agent._AGENT_ENGLISH_OUTPUT_CONTRACT) == 1
assert "Write the complete final generator instruction in English" in model_prompt
assert "@imageN and @videoN" in model_prompt
input_node = object.__new__(agent.HMBAgentLibrary)
input_node._hmb_rules_active = True
input_node._hmb_runtime_prompt = machine_prompt
input_node._hmb_native_prompt_read_active = True
assert input_node.get_parameter_value(agent._AGENT_PROMPT_INPUT_PARAMETER) == (
    machine_prompt
)


def sanitizer_node(output: str):
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_node_deleted = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node.parameter_output_values = {"output": output}

    def set_parameter_value(self, name, value, *args, **kwargs):
        self.parameter_output_values[name] = value

    node.set_parameter_value = MethodType(set_parameter_value, node)
    return node


english_node = sanitizer_node("Use @video1 motion and add a slow camera push-in.")
assert english_node._secure_hmb_outputs() is False
assert english_node.parameter_output_values["output"].startswith("Use @video1")

korean_node = sanitizer_node("@video1의 동작을 유지하고 카메라를 전진시킨다.")
assert korean_node._secure_hmb_outputs() is False
assert korean_node.parameter_output_values["output"].startswith("@video1의 동작")
assert korean_node._hmb_last_sanitizer_status == "clean"


# Agent/generator snapshot readers must be publication-free. In particular,
# they may not re-enter Shot graph reconciliation while holding Prompt's sync
# lock; video hydration and Picker callbacks can otherwise wait on each other.
prompt_node = prompt.HMBPromptLibrary(name="english_video_progression_prompt")
visible = prompt_node._hmb_last_prompt_output


def forbidden_reconcile():
    raise AssertionError("Agent snapshot re-entered Shot graph reconciliation")


prompt_node._reconcile_shared_shot_edges = forbidden_reconcile
paired = prompt_node._hmb_agent_prompt_snapshot(visible)
assert paired["machine_prompt"] == prompt_node._hmb_last_machine_prompt_output
assert agent._paired_machine_prompt(
    SimpleNamespace(_hmb_verified_prompt_source_node=prompt_node),
    visible,
) == paired["machine_prompt"]
assert prompt_node._hmb_agent_shot_context(visible) == (
    prompt_node._hmb_last_shot_context
)
try:
    prompt_node._hmb_generator_shot_snapshot([], [])
except prompt._ShotRoutingContractError:
    # An independent Only Prompt has no generator Shot identity. The important
    # boundary here is that it reached the pure local validator without calling
    # the forbidden graph reconciler above.
    pass


# An unchanged ImageAsset catalog is a normal router cache hit. It must not
# demote a ready VideoPicker to image_catalog_unavailable and block the Prompt
# video snapshot merely because no new catalog generation was committed.
picker_node = picker.HMBVideoPickerLibrary(name="english_video_progression_picker")
picker_node._hmb_shot_route_status = {
    "schema": "hmb-shot-routing-status",
    "version": 1,
    "ok": True,
    "code": "ready",
    "details": "",
}
original_reconcile = picker._shot_routing.reconcile_shot_routing
try:
    picker._shot_routing.reconcile_shot_routing = lambda _node: {
        "ok": True,
        "code": "ready",
        "changed": 0,
    }
    result = picker_node._reconcile_shared_shot_routing()
finally:
    picker._shot_routing.reconcile_shot_routing = original_reconcile
assert result == {"ok": True, "code": "ready", "changed": 0}
assert picker_node._hmb_shot_route_status["ok"] is True
assert picker_node._hmb_shot_route_status["code"] == "ready"


print(
    "HMB Agent English final-output contract / Prompt video progression regression: PASS"
)
