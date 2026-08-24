from __future__ import annotations

"""Regression coverage for per-flow Shot routing admission.

Run with the Griptape engine Python or ordinary Python from the repository root.
"""

import threading
import time
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import _hmb_shot_routing as routing


node_a = SimpleNamespace(name="Flow A Node", flow_name="flow-a")
node_b = SimpleNamespace(name="Flow B Node", flow_name="flow-b")

original_same_flow_nodes = routing._same_flow_nodes
original_subscription_for = routing._subscription_for
original_mark_authoritative = routing._mark_authoritative

flow_a_entered = threading.Event()
release_flow_a = threading.Event()
flow_b_finished = threading.Event()
results: dict[str, dict] = {}


def same_flow_nodes(node):
    return node.flow_name, [node]


def blocking_subscription(node):
    if node is node_a:
        flow_a_entered.set()
        assert release_flow_a.wait(2.0), "flow-a probe was never released"
    return None


def run_a() -> None:
    results["a"] = routing.reconcile_shot_routing(node_a)


def run_b() -> None:
    results["b"] = routing.reconcile_shot_routing(node_b)
    flow_b_finished.set()


try:
    routing._same_flow_nodes = same_flow_nodes
    routing._subscription_for = blocking_subscription
    routing._mark_authoritative = lambda _node: None
    with routing._ROUTING_LOCK:
        routing._ROUTING_FLOW_GATES.clear()

    thread_a = threading.Thread(target=run_a, name="routing-flow-a")
    thread_a.start()
    assert flow_a_entered.wait(1.0)

    started = time.monotonic()
    thread_b = threading.Thread(target=run_b, name="routing-flow-b")
    thread_b.start()
    assert flow_b_finished.wait(0.5), (
        "a slow callback in flow-a blocked independent flow-b reconciliation"
    )
    assert time.monotonic() - started < 0.5

    # A callback in an active flow must still receive the established same-flow
    # re-entry result rather than recurse or wait for its own claim.
    nested_results: list[dict] = []
    nested_once = {"done": False}

    def reentrant_subscription(node):
        if node is node_a and not nested_once["done"]:
            nested_once["done"] = True
            nested_results.append(routing.reconcile_shot_routing(node_a))
        return None

    release_flow_a.set()
    thread_a.join(2.0)
    thread_b.join(2.0)
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert results["a"]["ok"] and results["b"]["ok"]

    routing._subscription_for = reentrant_subscription
    outer = routing.reconcile_shot_routing(node_a)
    assert outer["ok"]
    assert nested_results == [{"ok": True, "code": "reentrant", "changed": 0}]

    # A concurrent update in the same flow must wait for the active pass and
    # then run with a fresh retained-node snapshot.  Returning `reentrant` here
    # would silently lose the second state generation.
    node_c_old = SimpleNamespace(name="Flow C Old", flow_name="flow-c")
    node_c_new = SimpleNamespace(name="Flow C New", flow_name="flow-c")
    flow_c_nodes = {"values": [node_c_old]}
    flow_c_entered = threading.Event()
    release_flow_c = threading.Event()
    flow_c_second_finished = threading.Event()
    flow_c_observed: list[str] = []
    flow_c_results: list[dict] = []

    def same_flow_nodes_with_update(node):
        if node.flow_name == "flow-c":
            return node.flow_name, list(flow_c_nodes["values"])
        return node.flow_name, [node]

    first_flow_c_probe = {"pending": True}

    def blocking_same_flow_subscription(node):
        flow_c_observed.append(str(node.name))
        if node is node_c_old and first_flow_c_probe["pending"]:
            first_flow_c_probe["pending"] = False
            flow_c_entered.set()
            assert release_flow_c.wait(2.0), "flow-c probe was never released"
        return None

    def run_flow_c_first() -> None:
        flow_c_results.append(routing.reconcile_shot_routing(node_c_old))

    def run_flow_c_second() -> None:
        flow_c_results.append(routing.reconcile_shot_routing(node_c_old))
        flow_c_second_finished.set()

    routing._same_flow_nodes = same_flow_nodes_with_update
    routing._subscription_for = blocking_same_flow_subscription
    thread_c_first = threading.Thread(
        target=run_flow_c_first, name="routing-flow-c-first"
    )
    thread_c_first.start()
    assert flow_c_entered.wait(1.0)

    flow_c_nodes["values"] = [node_c_old, node_c_new]
    thread_c_second = threading.Thread(
        target=run_flow_c_second, name="routing-flow-c-second"
    )
    thread_c_second.start()
    assert not flow_c_second_finished.wait(0.1), (
        "same-flow concurrent routing returned before the active pass completed"
    )

    release_flow_c.set()
    thread_c_first.join(2.0)
    thread_c_second.join(2.0)
    assert not thread_c_first.is_alive()
    assert not thread_c_second.is_alive()
    assert len(flow_c_results) == 2
    assert all(result["ok"] for result in flow_c_results)
    assert all(result.get("code") != "reentrant" for result in flow_c_results)
    assert "Flow C New" in flow_c_observed, (
        "the queued same-flow pass did not observe the newest node generation"
    )

    # Keep the singleton post-registration path in this oracle too. It shares
    # the same flow snapshot helper and must not regress while admission locks
    # are shortened.
    class SingletonNode:
        name = "Flow D ImageAsset"
        flow_name = "flow-d"

    singleton_node = SingletonNode()
    singleton_subscription = routing.ShotSubscription(
        node=singleton_node,
        node_name=singleton_node.name,
        kind=routing.KIND_IMAGE_ASSET,
        enabled=True,
        channel_uuid="flow-d-channel",
        shot_uuid="flow-d-shot",
        shot_number=1,
        shot_name="Shot 1",
    )
    routing._same_flow_nodes = lambda node: (node.flow_name, [node])
    routing._subscription_for = lambda node: (
        singleton_subscription if node is singleton_node else None
    )
    assert routing._enforce_singleton_admission(singleton_node) is True
finally:
    release_flow_a.set()
    if "release_flow_c" in globals():
        release_flow_c.set()
    routing._same_flow_nodes = original_same_flow_nodes
    routing._subscription_for = original_subscription_for
    routing._mark_authoritative = original_mark_authoritative
    with routing._ROUTING_LOCK:
        routing._ROUTING_FLOW_GATES.clear()

print("HMB Shot routing flow-isolation regression passed.")
