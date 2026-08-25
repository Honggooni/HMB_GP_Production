from __future__ import annotations

import copy
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


prompt = load_module(
    "hmb_prompt_source_reconcile_noop_regression",
    "HMBPromptLibrary.py",
)


class ListConnectionsForNodeRequest:
    def __init__(self, **kwargs: Any) -> None:
        self.node_name = kwargs["node_name"]


class ListConnectionsForNodeResultSuccess:
    def __init__(self, incoming_connections: list[Any]) -> None:
        self.incoming_connections = list(incoming_connections)


class NodeManagerProbe:
    def __init__(self, registry: dict[str, Any]) -> None:
        self._registry = registry

    def get_node_by_name(self, name: str) -> Any:
        return self._registry[name]


class GriptapeNodesProbe:
    registry: dict[str, Any] = {}
    incoming_connections: list[Any] = []
    node_manager = NodeManagerProbe(registry)

    @classmethod
    def NodeManager(cls) -> NodeManagerProbe:
        return cls.node_manager

    @classmethod
    def handle_request(cls, request: Any) -> Any:
        assert isinstance(request, ListConnectionsForNodeRequest)
        return ListConnectionsForNodeResultSuccess(cls.incoming_connections)


# Construct the unit node before replacing retained-mode modules. An installed
# host's real DataNode constructor needs its complete GriptapeNodes surface;
# clean CI uses the lightweight test double installed above.
node = prompt.HMBPromptLibrary(name="Prompt Source Reconcile Probe")

connection_events = types.ModuleType(
    "griptape_nodes.retained_mode.events.connection_events"
)
connection_events.ListConnectionsForNodeRequest = ListConnectionsForNodeRequest
connection_events.ListConnectionsForNodeResultSuccess = (
    ListConnectionsForNodeResultSuccess
)
sys.modules[connection_events.__name__] = connection_events

griptape_nodes_module = types.ModuleType(
    "griptape_nodes.retained_mode.griptape_nodes"
)
griptape_nodes_module.GriptapeNodes = GriptapeNodesProbe
sys.modules[griptape_nodes_module.__name__] = griptape_nodes_module


source = SimpleNamespace(
    name="Source Probe",
    parameter_output_values={"SOURCE_OUT": "fresh-v1"},
    parameter_values={},
)
GriptapeNodesProbe.registry.update({node.name: node, source.name: source})

base_node_type = prompt.HMBPromptLibrary.__mro__[1]
original_parent_setter = base_node_type.set_parameter_value
parent_writes: list[tuple[str, Any, dict[str, Any]]] = []


def counting_parent_setter(
    self: Any,
    name: str,
    value: Any,
    *args: Any,
    **kwargs: Any,
) -> None:
    if self is node:
        parent_writes.append((name, copy.deepcopy(value), dict(kwargs)))
    original_parent_setter(self, name, value, *args, **kwargs)


base_node_type.set_parameter_value = counting_parent_setter


def seed_source_caches(**values: Any) -> None:
    defaults = {
        prompt.PICKER_INPUT_PARAMETER_NAME: "",
        prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME: "",
        prompt.SHOT_ASSET_INPUT_PARAMETER_NAME: "",
        prompt.SHOT_PICKER_INPUT_PARAMETER_NAME: {},
    }
    defaults.update(values)
    for parameter_name, value in defaults.items():
        original_parent_setter(
            node,
            parameter_name,
            copy.deepcopy(value),
            initial_setup=True,
        )
    parent_writes.clear()


def edge(target_parameter_name: str) -> Any:
    return SimpleNamespace(
        source_node_name=source.name,
        source_parameter_name="SOURCE_OUT",
        target_node_name=node.name,
        target_parameter_name=target_parameter_name,
    )


try:
    # A stale connected transport cache is replaced once. Re-reading the same
    # authoritative output must not publish another retained-mode value event.
    seed_source_caches(PICKER_IN="stale")
    GriptapeNodesProbe.incoming_connections = [
        edge(prompt.PICKER_INPUT_PARAMETER_NAME)
    ]
    assert node._reconcile_connected_source_inputs_from_graph() is True
    assert [item[0] for item in parent_writes] == [
        prompt.PICKER_INPUT_PARAMETER_NAME
    ]
    assert node.get_parameter_value(prompt.PICKER_INPUT_PARAMETER_NAME) == "fresh-v1"

    assert node._reconcile_connected_source_inputs_from_graph() is True
    assert len(parent_writes) == 1

    source.parameter_output_values["SOURCE_OUT"] = "fresh-v2"
    assert node._reconcile_connected_source_inputs_from_graph() is True
    assert len(parent_writes) == 2
    assert parent_writes[-1][0:2] == (
        prompt.PICKER_INPUT_PARAMETER_NAME,
        "fresh-v2",
    )

    # A missing graph edge is authoritative. Clear one stale serialized cache,
    # then suppress the identical empty write on every later reconciliation.
    GriptapeNodesProbe.incoming_connections = []
    assert node._reconcile_connected_source_inputs_from_graph() is True
    assert len(parent_writes) == 3
    assert parent_writes[-1][0:2] == (
        prompt.PICKER_INPUT_PARAMETER_NAME,
        "",
    )
    assert node._reconcile_connected_source_inputs_from_graph() is True
    assert len(parent_writes) == 3

    # Pre-v0.6.46 SHOT_PICKER_IN values were JSON strings. The first graph
    # reconcile must materialize the typed dict contract exactly once; a
    # subsequent identical reconcile is a true no-op.
    shot_payload = {
        "schema": "hmb-picker-shot-routing-catalog",
        "version": 1,
        "channel_uuid": "00000000-0000-4000-8000-000000000046",
        "generation": 9,
    }
    legacy_json = json.dumps(
        shot_payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    source.parameter_output_values["SOURCE_OUT"] = copy.deepcopy(shot_payload)
    seed_source_caches(SHOT_PICKER_IN=legacy_json)
    GriptapeNodesProbe.incoming_connections = [
        edge(prompt.SHOT_PICKER_INPUT_PARAMETER_NAME)
    ]

    assert node._reconcile_connected_source_inputs_from_graph() is True
    assert [item[0] for item in parent_writes] == [
        prompt.SHOT_PICKER_INPUT_PARAMETER_NAME
    ]
    assert node.get_parameter_value(
        prompt.SHOT_PICKER_INPUT_PARAMETER_NAME
    ) == shot_payload
    assert node._reconcile_connected_source_inputs_from_graph() is True
    assert len(parent_writes) == 1
finally:
    base_node_type.set_parameter_value = original_parent_setter


print(
    "HMB Prompt source reconcile no-op regression: PASS "
    "(stale/change/disconnect writes once; identical values suppressed; "
    "legacy SHOT_PICKER JSON migrates once)"
)
