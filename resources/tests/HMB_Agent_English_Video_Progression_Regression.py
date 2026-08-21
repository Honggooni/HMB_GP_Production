from __future__ import annotations

import importlib.util
from pathlib import Path
from types import MethodType
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


# Korean user input remains valid private source data, but the protected native
# call always receives one final English-only generator-output contract.
machine_prompt = "USER DESCRIPTION DATA (JSON):\n{\"scene\":\"천천히 줌인\"}\n"
runtime_prompt = agent._compose_hmb_runtime_prompt(
    machine_prompt,
    {"sources": [], "shared_windows": []},
)
assert machine_prompt.rstrip() in runtime_prompt
assert agent._ENGLISH_GENERATOR_OUTPUT_CONTRACT_HEADER in runtime_prompt
assert agent._ENGLISH_GENERATOR_OUTPUT_CONTRACT in runtime_prompt
assert runtime_prompt.rstrip().endswith(agent._ENGLISH_GENERATOR_OUTPUT_CONTRACT)
assert not agent._contains_korean_script("Slowly push the camera toward @video1.")
assert agent._contains_korean_script("카메라를 천천히 전진시킨다.")


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
assert korean_node._secure_hmb_outputs() is True
assert korean_node.parameter_output_values["output"] == (
    agent._HMB_ENGLISH_OUTPUT_REQUIRED_MESSAGE
)
assert not agent._contains_korean_script(
    korean_node.parameter_output_values["output"]
)


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
    "HMB Agent English output / Prompt video progression regression: PASS"
)
