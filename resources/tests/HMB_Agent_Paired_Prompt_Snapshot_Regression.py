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
                "version": 3,
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
assert agent._RUNTIME_FX_SCOPE_HEADER not in machine_prompt


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

# Content markers are not source provenance. Tests/mocks that bypass live
# topology must be rejected even when their input resembles a machine envelope.
legacy = SimpleNamespace(_hmb_verified_prompt_source_node=None)
expect_rejected(lambda: agent._paired_machine_prompt(legacy, machine_prompt))
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
assert live_machine == live_prompt._hmb_last_machine_prompt_output
assert "HMB JOB DATA (JSON):" in live_machine
assert "FX/TIMING SOURCE DATA (JSON):" in live_machine
assert "USER DESCRIPTION DATA (JSON):" in live_machine


# Workflow deserialization creates a fresh Prompt first, then restores persisted
# parameter/input values with ``initial_setup=True``. The host stores those
# values directly and deliberately skips after_value_set, so neither of Prompt's
# normal synchronization hooks runs. The private pair must therefore rebuild
# itself from the restored canonical state before Agent consumes it.
def hydrate_without_lifecycle(
    node: object,
    parameter_name: str,
    value: object,
    *,
    is_output: bool = False,
) -> None:
    if is_output:
        node.parameter_output_values[parameter_name] = value
        return
    parameter_values = getattr(node, "parameter_values", None)
    if isinstance(parameter_values, dict):
        parameter_values[parameter_name] = value
        return
    parameter = prompt._get_parameter_obj(node, parameter_name)
    if parameter is None:
        raise AssertionError(f"missing hydration parameter: {parameter_name}")
    parameter.default_value = value


hydration_failures: list[str] = []

# A saved visible document that differs from the constructor default previously
# exposed the exact SOURCE CONTRACT INVALID path: the Agent input was restored,
# but the source instance still owned the constructor generation's private pair.
restored_visible_prompt = prompt.HMBPromptLibrary(
    name="paired_prompt_restored_visible"
)
restored_visible_publications: list[tuple[object, ...]] = []
restored_visible_prompt.publish_update_to_parameter = (
    lambda *args: restored_visible_publications.append(args)
)
constructor_visible = restored_visible_prompt._hmb_last_prompt_output
restored_visible_state = prompt._normalize_state(prompt._default_widget_state())
restored_visible_state["images"][0].update(
    {
        "present": True,
        "label": "HydratedHero",
        "asset_id": "HydratedHeroAsset",
        "asset_source_uid": "hydrated-hero-source-uid",
        "source_type": "Character Appearance",
        "owner": "HydratedHero",
    }
)
saved_visible = prompt._build_prompt_package(restored_visible_state)
saved_visible_machine = prompt._build_data_only_prompt_package(
    restored_visible_state
)
assert saved_visible != constructor_visible
with restored_visible_prompt._hmb_sync_lock:
    # A constructor callback may still be queued in a standalone engine test.
    # Workflow initial_setup does not queue another callback after hydration, so
    # invalidate the constructor generation and hold the lock through consume.
    restored_visible_prompt._hmb_sync_generation += 1
    hydrate_without_lifecycle(
        restored_visible_prompt,
        prompt.WIDGET_PARAMETER_NAME,
        prompt._json_dumps(restored_visible_state),
    )
    hydrate_without_lifecycle(
        restored_visible_prompt,
        "PROMPT_OUT",
        saved_visible,
        is_output=True,
    )
    assert restored_visible_prompt.parameter_output_values["PROMPT_OUT"] == (
        saved_visible
    )
    assert restored_visible_prompt._hmb_last_prompt_output == constructor_visible
    try:
        restored_pair = agent._paired_machine_prompt(
            SimpleNamespace(
                _hmb_verified_prompt_source_node=restored_visible_prompt
            ),
            saved_visible,
        )
        if restored_pair != saved_visible_machine:
            hydration_failures.append(
                "persisted visible hydration returned a stale machine snapshot"
            )
        # The host strips terminal CR/LF bytes while hydrating an output into
        # the connected Agent input. That transport-only normalization must
        # retain the same private pair and hash the exact incoming bytes.
        trimmed_saved_visible = saved_visible.rstrip("\r\n")
        assert trimmed_saved_visible != saved_visible
        assert agent._paired_machine_prompt(
            SimpleNamespace(
                _hmb_verified_prompt_source_node=restored_visible_prompt
            ),
            trimmed_saved_visible,
        ) == saved_visible_machine

        # Equivalence is terminal-only. Removing an embedded separator changes
        # the visible document identity and must remain fail-closed.
        embedded_changed_visible = trimmed_saved_visible.replace(
            "\n\n",
            "\n",
            1,
        )
        assert embedded_changed_visible != trimmed_saved_visible
        expect_rejected(
            lambda: agent._paired_machine_prompt(
                SimpleNamespace(
                    _hmb_verified_prompt_source_node=restored_visible_prompt
                ),
                embedded_changed_visible,
            )
        )
    except RuntimeError as error:
        hydration_failures.append(
            f"persisted visible hydration was rejected: {error}"
        )
assert restored_visible_publications == []


# USER DESCRIPTION is intentionally absent from the concise public document.
# A restored edit can therefore leave visible bytes equal to the constructor
# default while changing the machine envelope. Visible-hash validation alone
# must not silently accept the stale constructor machine generation.
restored_machine_only_prompt = prompt.HMBPromptLibrary(
    name="paired_prompt_restored_machine_only"
)
restored_machine_only_publications: list[tuple[object, ...]] = []
restored_machine_only_prompt.publish_update_to_parameter = (
    lambda *args: restored_machine_only_publications.append(args)
)
constructor_machine_only_visible = (
    restored_machine_only_prompt._hmb_last_prompt_output
)
constructor_machine_only_machine = (
    restored_machine_only_prompt._hmb_last_machine_prompt_output
)
restored_machine_only_state = prompt._normalize_state(
    prompt._default_widget_state()
)
restored_machine_only_state["text"]["SCENE_CONTEXT"] = (
    "Hydrated private scene direction."
)
saved_machine_only_visible = prompt._build_prompt_package(
    restored_machine_only_state
)
saved_machine_only_machine = prompt._build_data_only_prompt_package(
    restored_machine_only_state
)
assert saved_machine_only_visible == constructor_machine_only_visible
assert saved_machine_only_machine != constructor_machine_only_machine
with restored_machine_only_prompt._hmb_sync_lock:
    restored_machine_only_prompt._hmb_sync_generation += 1
    hydrate_without_lifecycle(
        restored_machine_only_prompt,
        prompt.WIDGET_PARAMETER_NAME,
        prompt._json_dumps(restored_machine_only_state),
    )
    hydrate_without_lifecycle(
        restored_machine_only_prompt,
        "PROMPT_OUT",
        saved_machine_only_visible,
        is_output=True,
    )
    try:
        restored_machine_only_pair = agent._paired_machine_prompt(
            SimpleNamespace(
                _hmb_verified_prompt_source_node=restored_machine_only_prompt
            ),
            saved_machine_only_visible,
        )
        if restored_machine_only_pair != saved_machine_only_machine:
            hydration_failures.append(
                "machine-only hydration silently returned the constructor snapshot"
            )
    except RuntimeError as error:
        hydration_failures.append(
            f"machine-only hydration was rejected: {error}"
        )
assert restored_machine_only_publications == []

assert not hydration_failures, "; ".join(hydration_failures)


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
    target_parameter_name=agent._AGENT_SHOT_PROMPT_INPUT_PARAMETER,
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
