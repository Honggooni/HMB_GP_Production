"""Regression for one-per-flow ImageAsset/VideoPicker reset replacement.

Run with the bundled Griptape Python or ordinary Python from the repository
root.  The host surface is intentionally reduced to the exact retained-mode
identity and scheduling calls used by ``_hmb_shot_routing``.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "_hmb_shot_routing.py"


class FakeLoop:
    def __init__(self) -> None:
        self.pending: list[tuple[object, tuple[object, ...]]] = []

    def is_closed(self) -> bool:
        return False

    def call_soon_threadsafe(self, callback, *args) -> None:
        self.pending.append((callback, args))

    def call_later(self, _delay, callback, *args) -> None:
        self.pending.append((callback, args))

    def drain(self, limit: int = 32) -> None:
        count = 0
        while self.pending:
            callback, args = self.pending.pop(0)
            callback(*args)
            count += 1
            assert count <= limit, "singleton retry loop did not settle"


class DeleteNodeRequest:
    def __init__(self, *, node_name: str) -> None:
        self.node_name = node_name


class FakeFlow:
    def __init__(self) -> None:
        self.nodes: dict[str, FakeNode] = {}


class FakeNode:
    def __init__(self, name: str, kind: str, durable: dict | None = None) -> None:
        self.name = name
        self.kind = kind
        self._hmb_node_deleted = False
        self.durable = deepcopy(durable or {})
        self.handoff_exports = 0
        self.handoff_adoptions = 0
        self.discoveries = 0
        self.hydration_restores = 0
        self.statuses: list[dict] = []

    def _hmb_shot_channel_subscription(self) -> dict:
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": self.kind,
            "enabled": True,
            "channel_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "shot_uuid": "",
            "shot_number": 1,
            "shot_name": "Shot 1",
        }

    def _hmb_export_reset_handoff(self) -> dict:
        self.handoff_exports += 1
        return {"kind": self.kind, "durable": deepcopy(self.durable)}

    def _hmb_adopt_reset_handoff(self, payload: dict) -> bool:
        assert payload["kind"] == self.kind
        self.handoff_adoptions += 1
        self.durable = deepcopy(payload["durable"])
        return True

    def _hmb_post_registration_shot_discovery(self) -> None:
        self.discoveries += 1

    def _hmb_post_hydration_state_restore(self) -> None:
        self.hydration_restores += 1

    def _hmb_apply_shot_routing_status(self, status: dict) -> None:
        self.statuses.append(deepcopy(status))


loop = FakeLoop()
flow = FakeFlow()
node_by_name: dict[str, FakeNode] = {}
deleted_names: list[str] = []


class FakeNodeManager:
    def get_node_by_name(self, name: str):
        return node_by_name.get(name)

    def get_node_parent_flow_by_name(self, name: str) -> str:
        assert node_by_name.get(name) is not None
        return "workflow-main"


class FakeFlowManager:
    def get_flow_by_name(self, name: str) -> FakeFlow:
        assert name == "workflow-main"
        return flow


class FakeGriptapeNodes:
    @staticmethod
    def NodeManager() -> FakeNodeManager:
        return FakeNodeManager()

    @staticmethod
    def FlowManager() -> FakeFlowManager:
        return FakeFlowManager()

    @staticmethod
    def EventManager():
        return types.SimpleNamespace(event_loop=loop)

    @staticmethod
    def handle_request(request):
        assert isinstance(request, DeleteNodeRequest)
        deleted_names.append(request.node_name)
        rejected = node_by_name.pop(request.node_name, None)
        if rejected is not None:
            rejected._hmb_node_deleted = True
            flow.nodes = {
                key: value for key, value in flow.nodes.items() if value is not rejected
            }
        return types.SimpleNamespace(succeeded=lambda: True)


module_names = (
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.events",
    "griptape_nodes.retained_mode.events.node_events",
    "griptape_nodes.retained_mode.griptape_nodes",
)
saved_modules = {name: sys.modules.get(name) for name in module_names}
for name in module_names[:3]:
    sys.modules[name] = types.ModuleType(name)
node_events = types.ModuleType(module_names[3])
node_events.DeleteNodeRequest = DeleteNodeRequest
sys.modules[module_names[3]] = node_events
host_module = types.ModuleType(module_names[4])
host_module.GriptapeNodes = FakeGriptapeNodes
sys.modules[module_names[4]] = host_module

spec = importlib.util.spec_from_file_location("hmb_singleton_reset_routing", TARGET)
assert spec and spec.loader
routing = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = routing
spec.loader.exec_module(routing)


def register(node: FakeNode) -> None:
    node_by_name[node.name] = node
    flow.nodes[node.name] = node


def remove(node: FakeNode) -> None:
    node_by_name.pop(node.name, None)
    flow.nodes = {key: value for key, value in flow.nodes.items() if value is not node}


try:
    for kind, durable in (
        (
            routing.KIND_IMAGE_ASSET,
            {
                "shots": [{"uuid": "shot-a", "images": ["hero.png", "bg.png"]}],
                "imports": ["hero.png"],
            },
        ),
        (
            routing.KIND_VIDEO_PICKER,
            {
                "picker_shots": [
                    {"uuid": "shot-a", "videos": ["playblast-a.mp4"]},
                    {"uuid": "shot-b", "videos": ["playblast-b.mp4"]},
                ]
            },
        ),
    ):
        node_by_name.clear()
        flow.nodes.clear()
        loop.pending.clear()
        deleted_names.clear()

        owner = FakeNode(f"Owner-{kind}", kind, durable)
        register(owner)
        routing._SINGLETON_REGISTRATION_ORDERS[owner] = 1
        assert routing._enforce_singleton_admission(owner) is True

        # A normal palette duplicate remains forbidden and is removed without
        # touching the original owner's durable Shot/Loader content.
        duplicate = FakeNode(f"Duplicate-{kind}", kind, {"wrong": True})
        register(duplicate)
        routing._SINGLETON_REGISTRATION_ORDERS[duplicate] = 2
        assert routing._enforce_singleton_admission(duplicate) is False
        assert deleted_names == [duplicate.name]
        assert owner.durable == durable

        # Griptape reset constructs <old>_temp while the owner still exists.
        # Registration scheduling must not copy state before the replacement
        # has an exact retained-mode flow identity.
        replacement = FakeNode(f"{owner.name}_temp", kind)
        assert routing.schedule_post_registration_reconcile(replacement) is True
        assert replacement.durable == {}
        register(replacement)
        # The original's pre-delete hook is the deterministic same-flow reset
        # boundary and transfers durable state directly to the temp object.
        assert routing.prepare_node_deletion(owner) is True
        assert replacement.durable == durable
        assert owner.handoff_exports == 1
        assert replacement.handoff_adoptions == 1
        assert (
            routing._enforce_singleton_admission(
                replacement, defer_reset_staging=True
            )
            is None
        )
        assert replacement.handoff_adoptions == 1, "bounded retry must not re-adopt"

        # Even exact N/N_temp names can never transfer across workflows. Keep
        # this proof local to the routing oracle rather than relying on the
        # current host's process-global name uniqueness.
        cross_flow_temp = FakeNode(f"{owner.name}_temp", kind)
        original_same_flow = routing._same_flow_nodes
        try:
            routing._same_flow_nodes = lambda candidate: (
                ("workflow-main", [owner])
                if candidate is owner
                else ("workflow-other", [cross_flow_temp])
            )
            assert (
                routing._try_stage_singleton_reset_handoff(
                    cross_flow_temp,
                    owner,
                )
                is False
            )
            assert cross_flow_temp.handoff_adoptions == 0
        finally:
            routing._same_flow_nodes = original_same_flow

        # Complete the real host sequence before the queued callback: delete
        # old, release its identity leases, then rename the exact temp object.
        owner._hmb_node_deleted = True
        routing.release_node_lifecycle(owner)
        remove(owner)
        old_temp_name = replacement.name
        node_by_name.pop(old_temp_name)
        flow.nodes.pop(old_temp_name)
        replacement.name = owner.name
        register(replacement)
        loop.drain()

        assert replacement.discoveries == 1
        assert routing._SINGLETON_ADMISSIONS.get(replacement) == (
            "workflow-main",
            kind,
        )
        assert replacement.durable == durable
        assert owner not in routing._SINGLETON_ADMISSIONS
        assert owner not in routing._SINGLETON_REGISTRATION_ORDERS

        # Delete and recreate under the same name: a stale deleted identity can
        # neither block the replacement nor donate/erase its content.
        replacement._hmb_node_deleted = True
        routing.release_node_lifecycle(replacement)
        remove(replacement)
        recreated = FakeNode(replacement.name, kind, durable)
        assert routing.schedule_post_registration_reconcile(recreated) is True
        register(recreated)
        loop.drain()
        assert recreated.discoveries == 1
        assert routing._SINGLETON_ADMISSIONS.get(recreated) == (
            "workflow-main",
            kind,
        )
        assert recreated.durable == durable

    # Serialized values can supersede the constructor's queued registration
    # callback before the event loop runs. The newest exact-identity hydration
    # callback must still invoke the local-only durable UI restore seam once.
    node_by_name.clear()
    flow.nodes.clear()
    loop.pending.clear()
    hydrated_seedance = FakeNode(
        "Hydrated-Seedance",
        routing.KIND_SEEDANCE,
        {"recovery_task_id": "broker-hydrated-task"},
    )
    assert routing.schedule_post_registration_reconcile(hydrated_seedance) is True
    register(hydrated_seedance)
    assert routing.schedule_post_hydration_reconcile(hydrated_seedance) is True
    loop.drain()
    assert hydrated_seedance.discoveries == 0
    assert hydrated_seedance.hydration_restores == 1
    assert hydrated_seedance.durable == {
        "recovery_task_id": "broker-hydrated-task"
    }

    print(
        "HMB singleton reset lifecycle regression passed "
        "(one-per-flow, reset handoff, rename, delete/recreate, no stale lease)"
    )
finally:
    sys.modules.pop(spec.name, None)
    for name, previous in saved_modules.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
