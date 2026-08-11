from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    module_name = f"_hmb_paired_snapshot_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


agent = load("HMBAgentLibrary")
prompt = load("HMBPromptLibrary")


def expect_rejected(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("invalid paired Prompt snapshot was accepted")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


machine_prompt = "\n".join(
    [
        "HMB_GP_Production",
        "HMB JOB DATA (JSON):",
        json.dumps(
            {
                "schema": "hmb-public-job-data",
                "version": 1,
                "images": [],
                "videos": [],
                "control_only_bindings": [],
                "frame_ranges": [],
                "connections": {"image_asset": False, "picker": False},
            },
            separators=(",", ":"),
        ),
        "FX/TIMING SOURCE DATA (JSON):",
        json.dumps(
            {
                "schema": "hmb-fx-timing-source-facts",
                "version": 3,
                "valid": True,
                "errors": [],
                "sources": [],
            },
            separators=(",", ":"),
        ),
        "USER DESCRIPTION DATA (JSON):",
        "{}",
        "",
    ]
)
visible_prompt = """HMB_GP_Production

TARGET GENERATOR:
This prompt is written for the active downstream target generator.

IMAGE SOURCE:
No image source assigned in HMBPromptLibrary.

VIDEO SOURCE:
No video source assigned in HMBPromptLibrary.
"""


class PairedSource:
    def __init__(self, snapshot: dict):
        self.snapshot = snapshot
        self.expected_values: list[str] = []

    def _hmb_agent_prompt_snapshot(self, expected_visible: str) -> dict:
        self.expected_values.append(expected_visible)
        return dict(self.snapshot)


valid_snapshot = {
    "schema": "hmb-prompt-paired-snapshot",
    "version": 1,
    "generation": 7,
    "visible_sha256": digest(visible_prompt),
    "machine_sha256": digest(machine_prompt),
    "machine_prompt": machine_prompt,
}
source = PairedSource(valid_snapshot)
node = SimpleNamespace(_hmb_verified_prompt_source_node=source)
assert agent._paired_machine_prompt(node, visible_prompt) == machine_prompt
assert source.expected_values == [visible_prompt]
assert agent._assert_public_job_data_contract(machine_prompt)["images"] == []
assert agent._assert_fx_timing_source_contract(machine_prompt)["sources"] == []
expect_rejected(lambda: agent._assert_public_job_data_contract(visible_prompt))
runtime_prompt = agent._compose_hmb_runtime_prompt(machine_prompt, {"sources": []})
assert runtime_prompt.startswith(machine_prompt.rstrip() + "\n")
assert visible_prompt not in runtime_prompt


for changed in (
    {**valid_snapshot, "schema": "wrong"},
    {**valid_snapshot, "version": 2},
    {**valid_snapshot, "generation": True},
    {**valid_snapshot, "generation": 0},
    {**valid_snapshot, "visible_sha256": "0" * 64},
    {**valid_snapshot, "machine_sha256": "0" * 64},
    {**valid_snapshot, "machine_prompt": ""},
    {**valid_snapshot, "unexpected": True},
):
    expect_rejected(
        lambda changed=changed: agent._paired_machine_prompt(
            SimpleNamespace(
                _hmb_verified_prompt_source_node=PairedSource(changed)
            ),
            visible_prompt,
        )
    )

expect_rejected(
    lambda: agent._paired_machine_prompt(
        SimpleNamespace(_hmb_verified_prompt_source_node=SimpleNamespace()),
        visible_prompt,
    )
)

# The fallback exists only for legacy tests/mocks that bypass live topology.
legacy = SimpleNamespace(_hmb_verified_prompt_source_node=None)
assert agent._paired_machine_prompt(legacy, machine_prompt) == machine_prompt
expect_rejected(lambda: agent._paired_machine_prompt(legacy, visible_prompt))


# A real Prompt instance publishes only the human view and privately pairs the
# exact seven-line machine envelope from the same initial state.
live_prompt = prompt.HMBPromptLibrary(name="paired_prompt_live")
live_visible = live_prompt.parameter_output_values["PROMPT_OUT"]
assert "TARGET GENERATOR:" in live_visible
assert "HMB JOB DATA (JSON):" not in live_visible
live_machine = agent._paired_machine_prompt(
    SimpleNamespace(_hmb_verified_prompt_source_node=live_prompt),
    live_visible,
)
assert agent._assert_public_job_data_contract(live_machine)["schema"] == (
    "hmb-public-job-data"
)
assert agent._assert_fx_timing_source_contract(live_machine)["schema"] == (
    "hmb-fx-timing-source-facts"
)


# Exact topology verification retains only the registered Prompt instance and
# clears it again when a later lookup no longer has the canonical edge.
topology_source = object.__new__(prompt.HMBPromptLibrary)
topology_source.name = "paired_prompt"
topology_source.metadata = {
    "library": "HMB_GP_Production",
    "node_type": "HMBPromptLibrary",
}
topology_target = SimpleNamespace(name="paired_agent")
edge = SimpleNamespace(
    source_node_name=topology_source.name,
    source_parameter_name="PROMPT_OUT",
    target_parameter_name="prompt",
)
assert agent._is_direct_hmb_prompt_library_connection(
    topology_target,
    connection_lookup=lambda *_args: SimpleNamespace(
        incoming_connections=[edge]
    ),
    node_lookup=lambda name: topology_source if name == topology_source.name else None,
    expected_class_lookup=lambda: prompt.HMBPromptLibrary,
)
assert topology_target._hmb_verified_prompt_source_node is topology_source
assert not agent._is_direct_hmb_prompt_library_connection(
    topology_target,
    connection_lookup=lambda *_args: SimpleNamespace(incoming_connections=[]),
    node_lookup=lambda _name: None,
    expected_class_lookup=lambda: prompt.HMBPromptLibrary,
)
assert topology_target._hmb_verified_prompt_source_node is None

print("HMB Agent paired human/machine Prompt snapshot regression: PASS")
