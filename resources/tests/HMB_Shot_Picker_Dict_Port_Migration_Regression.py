from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {filename}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt = load_module("hmb_prompt_typed_picker_port_regression", "HMBPromptLibrary.py")
seedance = load_module(
    "hmb_seedance_typed_picker_port_regression", "HMBSeedanceGeneration.py"
)
picker = load_module(
    "hmb_video_picker_typed_port_regression", "HMBVideoPickerLibrary.py"
)


class ParameterProbe:
    def __init__(self) -> None:
        self.parameters: dict[str, object] = {}

    def add_parameter(self, parameter) -> None:
        self.parameters[parameter.name] = parameter

    def get_parameter_by_name(self, name: str):
        return self.parameters.get(name)


producer = ParameterProbe()
picker._add_shot_picker_output(producer)
producer_port = producer.get_parameter_by_name(picker.SHOT_PICKER_OUTPUT_PARAMETER)
assert producer_port is not None
assert producer_port.type == "dict"
assert producer_port.output_type == "dict"
assert producer_port.default_value == {}

prompt_node = prompt.HMBPromptLibrary(name="Typed Prompt")
prompt_port = prompt_node.get_parameter_by_name(prompt.SHOT_PICKER_INPUT_PARAMETER_NAME)
assert prompt_port is not None
assert prompt_port.type == "dict"
assert prompt_port.input_types == ["dict"]
assert prompt_port.default_value == {}
assert producer_port.output_type in prompt_port.input_types

seedance_node = seedance.HMBSeedanceGeneration(name="Typed Seedance")
seedance_port = seedance_node.get_parameter_by_name(
    seedance.SHOT_PICKER_INPUT_PARAMETER
)
assert seedance_port is not None
assert seedance_port.type == "dict"
assert seedance_port.input_types == ["dict"]
assert seedance_port.default_value == {}
assert getattr(seedance_port, "accept_any", False) is False
assert producer_port.output_type in seedance_port.input_types

legacy_value = {
    "schema": "hmb-picker-shot-routing-catalog",
    "version": 1,
    "channel_uuid": "00000000-0000-4000-8000-000000000046",
    "generation": 7,
}
legacy_json = json.dumps(legacy_value, separators=(",", ":"))

# Pre-v0.6.46 saved target caches were strings. Both load orders must migrate
# the JSON object before the host's typed Parameter converter sees it.
prompt_node.set_parameter_value(
    prompt.SHOT_PICKER_INPUT_PARAMETER_NAME,
    legacy_json,
    initial_setup=True,
    emit_change=False,
)
assert prompt_node.get_parameter_value(prompt.SHOT_PICKER_INPUT_PARAMETER_NAME) == legacy_value

seedance_node.set_parameter_value(
    seedance.SHOT_PICKER_INPUT_PARAMETER,
    legacy_json,
    initial_setup=True,
    emit_change=False,
)
assert seedance_node.get_parameter_value(seedance.SHOT_PICKER_INPUT_PARAMETER) == legacy_value

for node, parameter_name in (
    (prompt_node, prompt.SHOT_PICKER_INPUT_PARAMETER_NAME),
    (seedance_node, seedance.SHOT_PICKER_INPUT_PARAMETER),
):
    node.set_parameter_value(
        parameter_name,
        "legacy-non-json-token",
        initial_setup=True,
        emit_change=False,
    )
    assert node.get_parameter_value(parameter_name) == {}

    node.set_parameter_value(
        parameter_name,
        "{\"payload\":\"" + ("x" * (1024 * 1024)) + "\"}",
        initial_setup=True,
        emit_change=False,
    )
    assert node.get_parameter_value(parameter_name) == {}

print(
    "HMB Shot Picker typed-port migration regression: PASS "
    "(dict producer/consumers, strict input types, bounded legacy JSON hydration)"
)
