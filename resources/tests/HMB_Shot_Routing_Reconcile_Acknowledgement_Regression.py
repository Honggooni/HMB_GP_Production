"""Regression for ImageAsset Shot-catalog reservation acknowledgements.

Run with ordinary Python from the repository root.  The fake retained-mode
loop exercises the real asynchronous scheduler; only the expensive routing
body is replaced with deterministic result dictionaries.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBImageAssetLibrary as image_asset
import _hmb_shot_routing as routing


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
            assert count <= limit, "routing acknowledgement loop did not settle"


class FakeFlow:
    def __init__(self) -> None:
        self.nodes: dict[str, object] = {}


loop = FakeLoop()
flow = FakeFlow()
node_by_name: dict[str, object] = {}


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


class AckNode:
    _reconcile_hmb_shot_routing = (
        image_asset.HMBImageAssetLibrary._reconcile_hmb_shot_routing
    )
    _hmb_shot_routing_reconcile_finished = (
        image_asset.HMBImageAssetLibrary._hmb_shot_routing_reconcile_finished
    )

    def __init__(self) -> None:
        self.name = "HMBImageAssetLibrary"
        self._hmb_node_deleted = False
        self._hmb_hydration_adopted = True
        self._hmb_last_reconciled_shot_catalog_identity = ""
        self._hmb_reserved_shot_catalog_identity = ""
        self.state = image_asset._default_state()

    def _current_state(self):
        return deepcopy(self.state)

    def _hmb_shot_channel_subscription(self) -> dict:
        shot_routing = self.state["shot_routing"]
        shot = next(
            item
            for item in shot_routing["shots"]
            if item["shot_uuid"] == shot_routing["active_shot_uuid"]
        )
        return {
            "schema": routing.SUBSCRIPTION_SCHEMA,
            "version": routing.SUBSCRIPTION_VERSION,
            "participant_kind": routing.KIND_IMAGE_ASSET,
            "enabled": True,
            "channel_uuid": shot_routing["channel_uuid"],
            "shot_uuid": shot["shot_uuid"],
            "shot_number": shot["number"],
            "shot_name": shot["name"],
        }


module_names = (
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.griptape_nodes",
)
saved_modules = {name: sys.modules.get(name) for name in module_names}
sys.modules[module_names[0]] = types.ModuleType(module_names[0])
sys.modules[module_names[1]] = types.ModuleType(module_names[1])
host_module = types.ModuleType(module_names[2])
host_module.GriptapeNodes = FakeGriptapeNodes
sys.modules[module_names[2]] = host_module

original_reconcile = routing.reconcile_shot_routing
original_asset_routing = image_asset._hmb_shot_routing
result = {"ok": True, "code": "ready", "changed": 0}


def deterministic_reconcile(_node):
    return dict(result)


try:
    image_asset._hmb_shot_routing = routing
    routing.reconcile_shot_routing = deterministic_reconcile
    with routing._ROUTING_LOCK:
        routing._POST_REGISTRATION_PENDING.clear()
        routing._POST_RECONCILE_GENERATIONS.clear()
        routing._AUTHORITATIVE_FINGERPRINTS.clear()
        routing._SINGLETON_ADMISSIONS.clear()
        routing._SINGLETON_REGISTRATION_ORDERS.clear()

    node = AckNode()
    node_by_name[node.name] = node
    flow.nodes[node.name] = node

    # Scheduling reserves the catalog but must not claim completion before the
    # retained event-loop callback actually runs.
    identity_1 = image_asset._shot_routing_catalog_identity(node.state)
    node._reconcile_hmb_shot_routing(identity_1)
    assert node._hmb_reserved_shot_catalog_identity == identity_1
    assert node._hmb_last_reconciled_shot_catalog_identity == ""
    assert len(loop.pending) == 1

    loop.drain()
    assert node._hmb_reserved_shot_catalog_identity == ""
    assert node._hmb_last_reconciled_shot_catalog_identity == identity_1

    # A pure active-Shot switch leaves the public compact catalog unchanged,
    # but changes the ImageAsset subscription and therefore must own a fresh
    # reconcile generation.
    second_shot = deepcopy(node.state["shot_routing"]["shots"][0])
    second_shot.update({
        "shot_uuid": "50000000-0000-4000-8000-000000000002",
        "number": 2,
        "name": "Shot 2",
    })
    node.state["shot_routing"]["shots"].append(second_shot)
    node.state["shot_routing"]["generation"] += 1
    identity_with_two_shots = image_asset._shot_routing_catalog_identity(
        node.state
    )
    node._reconcile_hmb_shot_routing(identity_with_two_shots)
    loop.drain()
    node.state["shot_routing"]["active_shot_uuid"] = second_shot[
        "shot_uuid"
    ]
    active_identity = image_asset._shot_routing_catalog_identity(node.state)
    assert active_identity != identity_with_two_shots
    node._reconcile_hmb_shot_routing(active_identity)
    assert len(loop.pending) == 1
    loop.drain()
    assert node._hmb_last_reconciled_shot_catalog_identity == active_identity

    # An ok-but-non-ready result is not a completed fan-out.  Its reservation
    # is released so a later lifecycle/state signal can retry the same catalog.
    node.state["shot_routing"]["generation"] += 1
    identity_2 = image_asset._shot_routing_catalog_identity(node.state)
    result = {"ok": True, "code": "hydration_pending", "changed": 0}
    node._reconcile_hmb_shot_routing(identity_2)
    assert node._hmb_reserved_shot_catalog_identity == identity_2
    loop.drain()
    assert node._hmb_reserved_shot_catalog_identity == ""
    assert node._hmb_last_reconciled_shot_catalog_identity == active_identity

    # Superseding a queued generation must make its stale callback inert.  The
    # newest owner token alone may acknowledge and commit the current catalog.
    result = {"ok": True, "code": "ready", "changed": 0}
    node._reconcile_hmb_shot_routing(identity_2)
    assert len(loop.pending) == 1
    node.state["shot_routing"]["generation"] += 1
    identity_3 = image_asset._shot_routing_catalog_identity(node.state)
    node._reconcile_hmb_shot_routing(identity_3)
    assert len(loop.pending) == 2
    stale_callback, stale_args = loop.pending.pop(0)
    stale_callback(*stale_args)
    assert node._hmb_reserved_shot_catalog_identity == identity_3
    assert node._hmb_last_reconciled_shot_catalog_identity == active_identity
    loop.drain()
    assert node._hmb_reserved_shot_catalog_identity == ""
    assert node._hmb_last_reconciled_shot_catalog_identity == identity_3

    # A syntactically valid late ACK carrying an older token is also ignored at
    # the ImageAsset hook boundary.
    node._hmb_shot_routing_reconcile_finished({
        "schema": "hmb-shot-routing-reconcile-ack",
        "version": 1,
        "phase": "hydrated",
        "generation": 1,
        "owner_token": identity_2,
        "completed": True,
        "code": "ready",
    })
    assert node._hmb_last_reconciled_shot_catalog_identity == identity_3

    print("HMB Shot routing reconcile acknowledgement regression passed")
finally:
    routing.reconcile_shot_routing = original_reconcile
    image_asset._hmb_shot_routing = original_asset_routing
    routing.release_node_lifecycle(node) if "node" in locals() else None
    for name, previous in saved_modules.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
