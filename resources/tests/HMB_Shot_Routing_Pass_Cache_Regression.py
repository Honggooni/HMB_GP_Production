from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "_hmb_shot_routing_pass_cache_regression",
    ROOT / "_hmb_shot_routing.py",
)
assert SPEC is not None and SPEC.loader is not None
routing = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = routing
SPEC.loader.exec_module(routing)


class ListConnectionsForNodeRequest:
    def __init__(self, **kwargs):
        self.node_name = kwargs["node_name"]


class ListConnectionsForNodeResultSuccess:
    def __init__(self, incoming_connections):
        self.incoming_connections = list(incoming_connections)


class CreateConnectionRequest:
    def __init__(self, **kwargs):
        self.values = kwargs


class DeleteConnectionRequest:
    def __init__(self, **kwargs):
        self.values = kwargs


class MutationResult:
    @staticmethod
    def succeeded():
        return True


class FakeGriptapeNodes:
    list_calls = 0

    @staticmethod
    def handle_request(request):
        if isinstance(request, ListConnectionsForNodeRequest):
            FakeGriptapeNodes.list_calls += 1
            return ListConnectionsForNodeResultSuccess([])
        if isinstance(request, (CreateConnectionRequest, DeleteConnectionRequest)):
            return MutationResult()
        raise AssertionError(type(request).__name__)


connection_events = types.ModuleType(
    "griptape_nodes.retained_mode.events.connection_events"
)
connection_events.ListConnectionsForNodeRequest = ListConnectionsForNodeRequest
connection_events.ListConnectionsForNodeResultSuccess = ListConnectionsForNodeResultSuccess
connection_events.CreateConnectionRequest = CreateConnectionRequest
connection_events.DeleteConnectionRequest = DeleteConnectionRequest
griptape_module = types.ModuleType("griptape_nodes.retained_mode.griptape_nodes")
griptape_module.GriptapeNodes = FakeGriptapeNodes
for name in (
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.events",
):
    sys.modules[name] = types.ModuleType(name)
sys.modules[connection_events.__name__] = connection_events
sys.modules[griptape_module.__name__] = griptape_module


class Node:
    def __init__(self, name):
        self.name = name


source = Node("source")
target = Node("target")
routing._ROUTING_PASS_LOCAL.incoming_by_node = {}
assert routing._incoming_connections(target) == []
assert routing._incoming_connections(target) == []
assert FakeGriptapeNodes.list_calls == 1

edge = routing.ShotEdge(source, "out", target, "in")
assert routing._create_connection(edge) is True
cached = routing._incoming_connections(target)
assert len(cached) == 1
assert cached[0].source_node_name == "source"
assert cached[0].target_parameter_name == "in"
assert FakeGriptapeNodes.list_calls == 1
assert routing._delete_connection(cached[0], target) is True
assert routing._incoming_connections(target) == []
assert FakeGriptapeNodes.list_calls == 1

del routing._ROUTING_PASS_LOCAL.incoming_by_node
assert routing._incoming_connections(target) == []
assert FakeGriptapeNodes.list_calls == 2

print(
    "HMB Shot routing pass cache regression: PASS "
    "(one host connection-list request per target; create/delete cache coherent)"
)
