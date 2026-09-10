from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_routing() -> Any:
    path = ROOT / "_hmb_shot_routing.py"
    spec = importlib.util.spec_from_file_location(
        "_hmb_five_library_shot_routing_regression",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the Shot router.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


routing = load_routing()

assert routing.KNOWN_KINDS == {
    routing.KIND_IMAGE_ASSET,
    routing.KIND_VIDEO_PICKER,
    routing.KIND_FINISH_LOOK,
    routing.KIND_PROMPT,
    routing.KIND_AGENT,
    routing.KIND_SEEDANCE,
    routing.KIND_COLOR_LUT,
}
assert (
    routing.SHOT_ROUTING_PROTOCOL_VERSION
    == "2026-08-20.shot-routing.v1"
)


CHANNEL = "11111111-1111-4111-8111-111111111111"
PUBLISHER = "22222222-2222-4222-8222-222222222222"
SHOT = "33333333-3333-4333-8333-333333333333"


def catalog() -> dict[str, Any]:
    shots = [
        {
            "shot_uuid": SHOT,
            "number": 1,
            "name": "Opening",
            "revision": 1,
        }
    ]
    document = {
        "channel_uuid": CHANNEL,
        "generation": 1,
        "shots": shots,
    }
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": PUBLISHER,
        **document,
        "metadata_sha256": hashlib.sha256(
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


class Participant:
    def __init__(
        self,
        name: str,
        kind: str,
        *,
        enabled: bool = False,
        channel_uuid: str = "",
        shot_uuid: str = "",
    ) -> None:
        self.name = name
        self.kind = kind
        self.enabled = enabled
        self.channel_uuid = channel_uuid
        self.shot_uuid = shot_uuid
        self.shot_number = 1
        self.shot_name = "Opening" if shot_uuid else "Only"
        self.preferred_shot_uuid = ""
        self.catalog_count = 0
        self.statuses: list[dict[str, Any]] = []
        self.prepared_prompt_sources: list[str] = []
        self.hydrated_picker_sources: list[tuple[str, str]] = []
        self.picker_hydrate_result = True
        self.picker_projection_clears: list[tuple[str, str]] = []
        self._hmb_node_deleted = False

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": self.kind,
            "enabled": self.enabled,
            "channel_uuid": self.channel_uuid,
            "shot_uuid": self.shot_uuid,
            "shot_number": self.shot_number,
            "shot_name": self.shot_name,
        }

    def _hmb_prepare_initial_shot_selection(self, shot_uuid: Any = "") -> None:
        self.preferred_shot_uuid = str(shot_uuid or "")

    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        assert snapshot == CATALOG
        self.catalog_count += 1
        self.channel_uuid = CHANNEL
        if self.kind == routing.KIND_VIDEO_PICKER:
            # VideoPicker publishes all Shot workspaces once the channel is
            # accepted. Its visible local selector may legitimately stay Only.
            self.enabled = True
            self.shot_uuid = ""
            self.shot_name = "Only"
            return
        selected = self.preferred_shot_uuid or SHOT
        self.enabled = True
        self.shot_uuid = selected
        self.shot_name = "Opening"

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if isinstance(value, dict):
            self.statuses.append(dict(value))

    def _hmb_prepare_remote_prompt_route(self, source: Any) -> bool:
        self.prepared_prompt_sources.append(str(source.name))
        return True

    def _hmb_hydrate_shot_picker_from_source(
        self,
        source: Any,
        source_parameter: str,
    ) -> bool:
        self.hydrated_picker_sources.append((str(source.name), source_parameter))
        return self.picker_hydrate_result

    def _hmb_clear_picker_source_projection(
        self,
        code: str = "picker_unavailable",
        message: str = "",
    ) -> bool:
        self.picker_projection_clears.append((code, message))
        return True


image = Participant(
    "ImageAsset",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
video = Participant("VideoPicker", routing.KIND_VIDEO_PICKER)
finish = Participant("FinishLook", routing.KIND_FINISH_LOOK)
prompt = Participant("Prompt", routing.KIND_PROMPT)
agent = Participant("Agent", routing.KIND_AGENT)
seedance = Participant("Seedance", routing.KIND_SEEDANCE)
NODES = [image, video, finish, prompt, agent, seedance]
CATALOG = catalog()
image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]

created_edges: set[tuple[str, str, str, str]] = set()


def ensure_edge(edge: Any, _subscriptions: Any) -> tuple[bool, str]:
    if edge.target_parameter == "prompt":
        assert edge.target.prepared_prompt_sources[-1] == edge.source.name
    identity = (
        edge.source.name,
        edge.source_parameter,
        edge.target.name,
        edge.target_parameter,
    )
    if identity in created_edges:
        return True, "existing"
    created_edges.add(identity)
    return True, "created"


routing._same_flow_nodes = lambda _node: ("FiveLibraryFlow", NODES)
routing._ensure_edge = ensure_edge
routing._clear_hmb_route = lambda *_args, **_kwargs: (0, "absent")
routing._clear_remote_edges = lambda *_args, **_kwargs: (0, [])
routing._incoming_connections = lambda _node: []

result = routing.reconcile_shot_routing(
    image,
    _allow_unready_cleanup=True,
)

assert result["ok"] is True, result
assert result["code"] == "ready", result
assert video.catalog_count == 1
assert finish.catalog_count == 1
assert prompt.catalog_count == 1
assert agent.catalog_count == 1
assert seedance.catalog_count == 1
assert prompt.shot_uuid == SHOT
assert finish.shot_uuid == SHOT
assert agent.shot_uuid == SHOT
assert seedance.shot_uuid == SHOT
assert seedance.prepared_prompt_sources == ["Agent"]

assert created_edges == {
    ("ImageAsset", "SHOT_ASSET_OUT", "Prompt", "SHOT_ASSET_IN"),
    ("VideoPicker", "SHOT_PICKER_OUT", "Prompt", "SHOT_PICKER_IN"),
    ("Prompt", "PROMPT_OUT", "Agent", "SHOT_PROMPT_IN"),
    ("Agent", "output", "Seedance", "prompt"),
    ("ImageAsset", "SHOT_ASSET_OUT", "Seedance", "SHOT_ASSET_IN"),
    ("VideoPicker", "SHOT_PICKER_OUT", "Seedance", "SHOT_PICKER_IN"),
    ("FinishLook", "SHOT_FINISH_LOOK_OUT", "Seedance", "SHOT_FINISH_LOOK_IN"),
}
assert finish.hydrated_picker_sources == []
saved_edges = set(created_edges)
reload_result = routing.reconcile_shot_routing(
    image,
    _allow_unready_cleanup=True,
)
assert reload_result["ok"] is True, reload_result
assert reload_result["changed"] == 0, reload_result
assert created_edges == saved_edges
assert finish.hydrated_picker_sources == []


# Video Tools lives inside Picker. Finish still receives the Shot catalog, but
# never acquires a media dependency with or without a Seedance node present.
finish_only_image = Participant(
    "FinishOnlyImage",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
finish_only_image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
finish_only_picker = Participant("FinishOnlyPicker", routing.KIND_VIDEO_PICKER)
finish_only_target = Participant("FinishOnlyTarget", routing.KIND_FINISH_LOOK)
NODES[:] = [finish_only_image, finish_only_picker, finish_only_target]
created_edges.clear()
finish_only_result = routing.reconcile_shot_routing(
    finish_only_image,
    _allow_unready_cleanup=True,
)
assert finish_only_result["ok"] is True, finish_only_result
assert created_edges == set()
assert finish_only_target.catalog_count == 1
assert finish_only_target.shot_uuid == SHOT
assert finish_only_target.hydrated_picker_sources == []


# A legacy projection callback is not consulted, even when it would fail.
optional_image = Participant(
    "OptionalImage",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
optional_image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
optional_picker = Participant("OptionalPicker", routing.KIND_VIDEO_PICKER)
optional_finish = Participant("OptionalFinish", routing.KIND_FINISH_LOOK)
optional_finish.picker_hydrate_result = False
NODES[:] = [optional_image, optional_picker, optional_finish]
created_edges.clear()
optional_hydrate_result = routing.reconcile_shot_routing(
    optional_image,
    _allow_unready_cleanup=True,
)
assert optional_hydrate_result["ok"] is True, optional_hydrate_result
assert optional_hydrate_result["failures"] == (), optional_hydrate_result
assert optional_finish.hydrated_picker_sources == []
assert created_edges == set()


# A host that cannot create the retired edge must never be asked to do so.
def reject_optional_picker_edge(edge: Any, _subscriptions: Any) -> tuple[bool, str]:
    if (
        edge.source_parameter == "SHOT_PICKER_OUT"
        and edge.target_parameter == "SHOT_PICKER_IN"
        and edge.target.kind == routing.KIND_FINISH_LOOK
    ):
        raise AssertionError("The retired Picker -> Finish edge was requested")
    return ensure_edge(edge, _subscriptions)


routing._ensure_edge = reject_optional_picker_edge
edge_failure_image = Participant(
    "EdgeFailureImage",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
edge_failure_image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
edge_failure_picker = Participant("EdgeFailurePicker", routing.KIND_VIDEO_PICKER)
edge_failure_finish = Participant("EdgeFailureFinish", routing.KIND_FINISH_LOOK)
NODES[:] = [edge_failure_image, edge_failure_picker, edge_failure_finish]
created_edges.clear()
optional_edge_result = routing.reconcile_shot_routing(
    edge_failure_image,
    _allow_unready_cleanup=True,
)
assert optional_edge_result["ok"] is True, optional_edge_result
assert optional_edge_result["failures"] == (), optional_edge_result
assert edge_failure_finish.picker_projection_clears == []
assert created_edges == set()
routing._ensure_edge = ensure_edge


# Seedance must route either media source independently. Without an exact Agent
# for the selected Shot, its public prompt stays authored/manual and no managed
# prompt edge is created.
image_only_source = Participant(
    "ImageOnly",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
image_only_source._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
image_only_seedance = Participant("SeedanceImageOnly", routing.KIND_SEEDANCE)
NODES[:] = [image_only_source, image_only_seedance]
created_edges.clear()
image_only_result = routing.reconcile_shot_routing(
    image_only_source,
    _allow_unready_cleanup=True,
)
assert image_only_result["ok"] is True, image_only_result
assert created_edges == {
    ("ImageOnly", "SHOT_ASSET_OUT", "SeedanceImageOnly", "SHOT_ASSET_IN"),
}

video_only_source = Participant(
    "VideoOnly",
    routing.KIND_VIDEO_PICKER,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
video_only_source._hmb_standalone_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
video_only_seedance = Participant("SeedanceVideoOnly", routing.KIND_SEEDANCE)
NODES[:] = [video_only_source, video_only_seedance]
created_edges.clear()
video_only_result = routing.reconcile_shot_routing(
    video_only_source,
    _allow_unready_cleanup=True,
)
assert video_only_result["ok"] is True, video_only_result
assert created_edges == {
    ("VideoOnly", "SHOT_PICKER_OUT", "SeedanceVideoOnly", "SHOT_PICKER_IN"),
}

only_seedance = Participant("SeedanceOnly", routing.KIND_SEEDANCE)
NODES[:] = [only_seedance]
created_edges.clear()
only_result = routing.reconcile_shot_routing(
    only_seedance,
    _allow_unready_cleanup=True,
)
assert only_result["ok"] is True, only_result
assert created_edges == set()
assert only_seedance.statuses[-1]["code"] == "only"


# Losing every media publisher must clear Seedance's durable quartet, not only
# remove hidden edges and paint a misleading Only status.
class ClearingSeedance(Participant):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.clear_count = 0

    def _hmb_clear_shot_routing_catalog(self, _reason: Any = "") -> dict[str, Any]:
        self.clear_count += 1
        self.enabled = False
        self.channel_uuid = ""
        self.shot_uuid = ""
        self.shot_name = "Only"
        return self._hmb_shot_channel_subscription()


orphan_seedance = ClearingSeedance(
    "SeedanceOrphan",
    routing.KIND_SEEDANCE,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
NODES[:] = [orphan_seedance]
created_edges.clear()
orphan_result = routing.reconcile_shot_routing(
    orphan_seedance,
    _allow_unready_cleanup=True,
)
assert orphan_result["ok"] is True, orphan_result
assert orphan_seedance.clear_count == 1
assert orphan_seedance.enabled is False
assert orphan_seedance.channel_uuid == ""
assert orphan_seedance.shot_uuid == ""
assert orphan_seedance.statuses[-1]["code"] == "only"


# Existing Prompt -> Agent edges must hydrate the non-serializable input after
# reload even though the host does not fire another connection-created hook.
class HydratingAgent(Participant):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hydrated_from: list[tuple[str, str]] = []

    def _hmb_hydrate_shot_prompt_from_source(
        self,
        source: Any,
        source_parameter: str,
    ) -> bool:
        self.hydrated_from.append((source.name, source_parameter))
        return True


hydration_image = Participant(
    "HydrationImage",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
hydration_image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
hydration_prompt = Participant(
    "HydrationPrompt",
    routing.KIND_PROMPT,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
hydration_agent = HydratingAgent(
    "HydrationAgent",
    routing.KIND_AGENT,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
NODES[:] = [hydration_image, hydration_prompt, hydration_agent]
created_edges.clear()


def ensure_existing_agent_edge(edge: Any, _subscriptions: Any) -> tuple[bool, str]:
    created_edges.add(
        (
            edge.source.name,
            edge.source_parameter,
            edge.target.name,
            edge.target_parameter,
        )
    )
    if edge.target is hydration_agent:
        return True, "existing"
    return True, "created"


routing._ensure_edge = ensure_existing_agent_edge
hydration_result = routing.reconcile_shot_routing(
    hydration_image,
    _allow_unready_cleanup=True,
)
assert hydration_result["ok"] is True, hydration_result
assert hydration_agent.hydrated_from == [("HydrationPrompt", "PROMPT_OUT")]
routing._ensure_edge = ensure_edge


# Ambiguous duplicate Seedance claimants are both returned to Only.  The router
# must not leave their selections active while merely removing dependencies.
class RejectingSeedance(Participant):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.auto_claim_enabled = True
        self._hmb_shot_catalog_snapshot: dict[str, Any] | None = None

    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        assert snapshot == CATALOG
        self.catalog_count += 1
        self._hmb_shot_catalog_snapshot = snapshot
        if not self.auto_claim_enabled:
            self.enabled = False
            self.channel_uuid = ""
            self.shot_uuid = ""
            self.shot_name = "Only"

    def _hmb_reject_duplicate_shot_selection(self, _reason: Any = "") -> dict[str, Any]:
        self.auto_claim_enabled = False
        self.enabled = False
        self.channel_uuid = ""
        self.shot_uuid = ""
        self.shot_name = "Only"
        return self._hmb_shot_channel_subscription()


class FreshClaimingSeedance(RejectingSeedance):
    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        assert snapshot == CATALOG
        self.catalog_count += 1
        self._hmb_shot_catalog_snapshot = snapshot
        if self.catalog_count == 1:
            # The first delivery sees Shot 1 occupied by both stale claimants.
            self.enabled = False
            self.channel_uuid = ""
            self.shot_uuid = ""
            self.shot_name = "Only"
            return
        self.enabled = True
        self.channel_uuid = CHANNEL
        self.shot_uuid = SHOT
        self.shot_name = "Opening"


duplicate_image = Participant(
    "DuplicateImage",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
duplicate_image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
duplicate_a = RejectingSeedance(
    "SeedanceDuplicateA",
    routing.KIND_SEEDANCE,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
duplicate_b = RejectingSeedance(
    "SeedanceDuplicateB",
    routing.KIND_SEEDANCE,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
fresh_after_duplicate = FreshClaimingSeedance(
    "SeedanceFreshAfterDuplicate",
    routing.KIND_SEEDANCE,
)
NODES[:] = [
    duplicate_image,
    duplicate_a,
    duplicate_b,
    fresh_after_duplicate,
]
created_edges.clear()
duplicate_result = routing.reconcile_shot_routing(
    duplicate_image,
    _allow_unready_cleanup=True,
)
assert duplicate_result["ok"] is True, duplicate_result
assert duplicate_a.enabled is False and duplicate_b.enabled is False
assert duplicate_a.catalog_count == 2 and duplicate_b.catalog_count == 2
assert duplicate_a.statuses[-1]["code"] == "only"
assert duplicate_b.statuses[-1]["code"] == "only"
assert fresh_after_duplicate.catalog_count == 2
assert fresh_after_duplicate.enabled is True
assert fresh_after_duplicate.shot_uuid == SHOT
assert created_edges == {
    (
        "DuplicateImage",
        "SHOT_ASSET_OUT",
        "SeedanceFreshAfterDuplicate",
        "SHOT_ASSET_IN",
    )
}


# Finish Look ownership follows the same one-node-per-Shot rule. Duplicate
# Finish nodes are released to Only without touching their authored look state,
# and Seedance continues with the existing Image/Video/Agent routes but no
# ambiguous finishing sidecar.
class RejectingFinish(Participant):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.reject_count = 0
        self.finish_state = {"beauty": {"enabled": True}, "film": {"scale_cc": 0.3}}

    def _hmb_reject_duplicate_shot_selection(self, _reason: Any = "") -> dict[str, Any]:
        self.reject_count += 1
        self.enabled = False
        self.channel_uuid = ""
        self.shot_uuid = ""
        self.shot_name = "Only"
        return self._hmb_shot_channel_subscription()


duplicate_finish_image = Participant(
    "DuplicateFinishImage",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
duplicate_finish_image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]
duplicate_finish_a = RejectingFinish(
    "FinishDuplicateA",
    routing.KIND_FINISH_LOOK,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
duplicate_finish_b = RejectingFinish(
    "FinishDuplicateB",
    routing.KIND_FINISH_LOOK,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
duplicate_finish_seedance = Participant(
    "SeedanceAfterFinishDuplicate",
    routing.KIND_SEEDANCE,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
finish_a_state = dict(duplicate_finish_a.finish_state)
finish_b_state = dict(duplicate_finish_b.finish_state)
NODES[:] = [
    duplicate_finish_image,
    duplicate_finish_a,
    duplicate_finish_b,
    duplicate_finish_seedance,
]
created_edges.clear()
duplicate_finish_result = routing.reconcile_shot_routing(
    duplicate_finish_image,
    _allow_unready_cleanup=True,
)
assert duplicate_finish_result["ok"] is True, duplicate_finish_result
assert duplicate_finish_a.reject_count == 1
assert duplicate_finish_b.reject_count == 1
assert duplicate_finish_a.enabled is False and duplicate_finish_b.enabled is False
assert duplicate_finish_a.finish_state == finish_a_state
assert duplicate_finish_b.finish_state == finish_b_state
assert created_edges == {
    (
        "DuplicateFinishImage",
        "SHOT_ASSET_OUT",
        "SeedanceAfterFinishDuplicate",
        "SHOT_ASSET_IN",
    )
}


# Five independent Shot chains across all six libraries must remain exact even
# though every managed
# edge is hidden from the canvas. No node age/name fallback may cross-connect
# Prompt 1 to Agent/Seedance 2 through 5.
multi_shots = [
    {
        "shot_uuid": f"{number}3333333-3333-4333-8333-333333333333"[:36],
        "number": number,
        "name": f"Shot {number}",
        "revision": 1,
    }
    for number in (1, 2, 3, 4, 5)
]


def multi_catalog() -> dict[str, Any]:
    document = {
        "channel_uuid": CHANNEL,
        "generation": 2,
        "shots": multi_shots,
    }
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": PUBLISHER,
        **document,
        "metadata_sha256": hashlib.sha256(
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


class ExactParticipant(Participant):
    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        assert snapshot == MULTI_CATALOG
        self.catalog_count += 1


MULTI_CATALOG = multi_catalog()
multi_image = ExactParticipant(
    "ImageAssetExact",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=multi_shots[0]["shot_uuid"],
)
multi_video = ExactParticipant(
    "VideoPickerExact",
    routing.KIND_VIDEO_PICKER,
    enabled=True,
    channel_uuid=CHANNEL,
)
multi_image._hmb_shot_routing_catalog = lambda: MULTI_CATALOG  # type: ignore[attr-defined]
multi_nodes: list[Participant] = [multi_image, multi_video]
for shot in multi_shots:
    for kind, prefix in (
        (routing.KIND_FINISH_LOOK, "FinishLook"),
        (routing.KIND_PROMPT, "Prompt"),
        (routing.KIND_AGENT, "Agent"),
        (routing.KIND_SEEDANCE, "Seedance"),
    ):
        participant = ExactParticipant(
            f"{prefix}{shot['number']}",
            kind,
            enabled=True,
            channel_uuid=CHANNEL,
            shot_uuid=shot["shot_uuid"],
        )
        participant.shot_number = shot["number"]
        participant.shot_name = shot["name"]
        multi_nodes.append(participant)

NODES[:] = multi_nodes
CATALOG = MULTI_CATALOG
created_edges.clear()
multi_result = routing.reconcile_shot_routing(
    multi_image,
    _allow_unready_cleanup=True,
)
assert multi_result["ok"] is True, multi_result
assert len(created_edges) == 35, created_edges
for shot in multi_shots:
    number = shot["number"]
    exact_edges = {
        ("ImageAssetExact", "SHOT_ASSET_OUT", f"Prompt{number}", "SHOT_ASSET_IN"),
        ("VideoPickerExact", "SHOT_PICKER_OUT", f"Prompt{number}", "SHOT_PICKER_IN"),
        (f"Prompt{number}", "PROMPT_OUT", f"Agent{number}", "SHOT_PROMPT_IN"),
        (f"Agent{number}", "output", f"Seedance{number}", "prompt"),
        ("ImageAssetExact", "SHOT_ASSET_OUT", f"Seedance{number}", "SHOT_ASSET_IN"),
        ("VideoPickerExact", "SHOT_PICKER_OUT", f"Seedance{number}", "SHOT_PICKER_IN"),
        (
            f"FinishLook{number}",
            "SHOT_FINISH_LOOK_OUT",
            f"Seedance{number}",
            "SHOT_FINISH_LOOK_IN",
        ),
    }
    assert exact_edges <= created_edges
for source_name, _source_port, target_name, _target_port in created_edges:
    source_number = source_name[-1:] if source_name.startswith(("Prompt", "Agent", "FinishLook")) else ""
    target_number = target_name[-1:] if target_name.startswith(("Prompt", "Agent", "Seedance")) else ""
    if source_number and target_number:
        assert source_number == target_number, (source_name, target_name)


# Only/clear transitions remove exactly the managed public Agent.output edge.
# A foreign prompt source or a different Agent handle remains user-owned.
cleanup_routing = load_routing()
cleanup_agent_node = Participant("CleanupAgent", cleanup_routing.KIND_AGENT)
cleanup_seedance_node = Participant("CleanupSeedance", cleanup_routing.KIND_SEEDANCE)
cleanup_agent = cleanup_routing.ShotSubscription(
    cleanup_agent_node,
    cleanup_agent_node.name,
    cleanup_routing.KIND_AGENT,
    True,
    CHANNEL,
    SHOT,
    1,
    "Opening",
)
cleanup_seedance = cleanup_routing.ShotSubscription(
    cleanup_seedance_node,
    cleanup_seedance_node.name,
    cleanup_routing.KIND_SEEDANCE,
    False,
    "",
    "",
    1,
    "Only",
)


class Incoming:
    def __init__(self, source: str, source_parameter: str) -> None:
        self.source_node_name = source
        self.source_parameter_name = source_parameter
        self.target_node_name = cleanup_seedance_node.name
        self.target_parameter_name = "prompt"


managed_prompt_edge = Incoming(cleanup_agent_node.name, "output")
foreign_prompt_edge = Incoming("ExternalPrompt", "output")
different_handle_edge = Incoming(cleanup_agent_node.name, "agent")
incoming_edges = [managed_prompt_edge, foreign_prompt_edge, different_handle_edge]
deleted_edges: list[Incoming] = []
cleanup_routing._incoming_connections = lambda _node: list(incoming_edges)


def delete_cleanup_edge(connection: Incoming, _target: Any) -> bool:
    deleted_edges.append(connection)
    incoming_edges.remove(connection)
    return True


cleanup_routing._delete_connection = delete_cleanup_edge
removed, cleanup_failures = cleanup_routing._clear_remote_edges(
    cleanup_seedance,
    {
        cleanup_agent.node_name: cleanup_agent,
        cleanup_seedance.node_name: cleanup_seedance,
    },
)
assert removed == 1
assert cleanup_failures == []
assert deleted_edges == [managed_prompt_edge]
assert foreign_prompt_edge in incoming_edges
assert different_handle_edge in incoming_edges

# Finish Only/delete cleanup owns only the automatic Picker dependency. A
# foreign edge on the same hidden target remains user-owned.
cleanup_picker_node = Participant("CleanupPicker", cleanup_routing.KIND_VIDEO_PICKER)
cleanup_finish_node = Participant("CleanupFinish", cleanup_routing.KIND_FINISH_LOOK)
cleanup_picker = cleanup_routing.ShotSubscription(
    cleanup_picker_node,
    cleanup_picker_node.name,
    cleanup_routing.KIND_VIDEO_PICKER,
    True,
    CHANNEL,
    "",
    1,
    "Only",
)
cleanup_finish = cleanup_routing.ShotSubscription(
    cleanup_finish_node,
    cleanup_finish_node.name,
    cleanup_routing.KIND_FINISH_LOOK,
    False,
    "",
    "",
    1,
    "Only",
)
managed_picker_edge = Incoming(cleanup_picker_node.name, "SHOT_PICKER_OUT")
managed_picker_edge.target_node_name = cleanup_finish_node.name
managed_picker_edge.target_parameter_name = "SHOT_PICKER_IN"
foreign_picker_edge = Incoming("ExternalPicker", "SHOT_PICKER_OUT")
foreign_picker_edge.target_node_name = cleanup_finish_node.name
foreign_picker_edge.target_parameter_name = "SHOT_PICKER_IN"
incoming_edges[:] = [managed_picker_edge, foreign_picker_edge]
deleted_edges.clear()
removed, cleanup_failures = cleanup_routing._clear_remote_edges(
    cleanup_finish,
    {
        cleanup_picker.node_name: cleanup_picker,
        cleanup_finish.node_name: cleanup_finish,
    },
)
assert removed == 1
assert cleanup_failures == []
assert deleted_edges == [managed_picker_edge]
assert incoming_edges == [foreign_picker_edge]


# Loading a saved Finish, including Only, retires the old automatic dependency.
# It must preserve different handles and non-Picker HMB participants, not just
# completely foreign nodes. Legacy projection is cleared only when no manual
# source remains on that input, and a second pass does nothing.
cleanup_other_node = Participant("CleanupPrompt", cleanup_routing.KIND_PROMPT)
cleanup_nodes = [cleanup_picker_node, cleanup_finish_node, cleanup_other_node]
cleanup_routing._same_flow_nodes = lambda _node: ("RetiredFinishRouteFlow", cleanup_nodes)
cleanup_routing._incoming_connections = lambda target: [
    edge for edge in incoming_edges if edge.target_node_name == target.name
]


def reject_retired_finish_edge(edge: Any, _subscriptions: Any) -> tuple[bool, str]:
    assert not (
        edge.target is cleanup_finish_node
        and edge.target_parameter == "SHOT_PICKER_IN"
    ), "Picker -> Finish must not be re-created during workflow restore"
    return True, "existing"


cleanup_routing._ensure_edge = reject_retired_finish_edge
wrong_handle_edge = Incoming(cleanup_picker_node.name, "VIDEO_OUT")
wrong_handle_edge.target_node_name = cleanup_finish_node.name
wrong_handle_edge.target_parameter_name = "SHOT_PICKER_IN"
non_picker_hmb_edge = Incoming(cleanup_other_node.name, "SHOT_PICKER_OUT")
non_picker_hmb_edge.target_node_name = cleanup_finish_node.name
non_picker_hmb_edge.target_parameter_name = "SHOT_PICKER_IN"
incoming_edges[:] = [
    managed_picker_edge, foreign_picker_edge, wrong_handle_edge, non_picker_hmb_edge
]
deleted_edges.clear()
cleanup_finish_node.enabled = True
cleanup_finish_node.channel_uuid = CHANNEL
cleanup_finish_node.shot_uuid = SHOT
migration_result = cleanup_routing.reconcile_shot_routing(
    cleanup_finish_node, _allow_unready_cleanup=True
)
assert migration_result["ok"] is True, migration_result
assert migration_result["changed"] == 1, migration_result
assert deleted_edges == [managed_picker_edge]
assert incoming_edges == [foreign_picker_edge, wrong_handle_edge, non_picker_hmb_edge]
assert cleanup_finish_node.picker_projection_clears == []

incoming_edges[:] = [managed_picker_edge]
deleted_edges.clear()
cleanup_finish_node.enabled = False
cleanup_finish_node.channel_uuid = ""
cleanup_finish_node.shot_uuid = ""
projection_migration_result = cleanup_routing.reconcile_shot_routing(
    cleanup_finish_node, _allow_unready_cleanup=True
)
assert projection_migration_result["ok"] is True, projection_migration_result
assert projection_migration_result["changed"] == 1, projection_migration_result
assert incoming_edges == []
assert cleanup_finish_node.picker_projection_clears == [
    (
        "video_tools_moved_to_picker",
        "Video Tools is available in VideoPicker expanded mode.",
    )
]
repeat_migration_result = cleanup_routing.reconcile_shot_routing(
    cleanup_finish_node, _allow_unready_cleanup=True
)
assert repeat_migration_result["changed"] == 0, repeat_migration_result
assert len(cleanup_finish_node.picker_projection_clears) == 1


source_by_kind = {
    routing.KIND_IMAGE_ASSET: ROOT / "HMBImageAssetLibrary.py",
    routing.KIND_VIDEO_PICKER: ROOT / "HMBVideoPickerLibrary.py",
    routing.KIND_FINISH_LOOK: ROOT / "HMBFinishLookLibrary.py",
    routing.KIND_PROMPT: ROOT / "HMBPromptLibrary.py",
    routing.KIND_AGENT: ROOT / "HMBAgentLibrary.py",
    routing.KIND_SEEDANCE: ROOT / "HMBSeedanceGeneration.py",
}
for kind, path in source_by_kind.items():
    source = path.read_text(encoding="utf-8")
    assert "def _hmb_shot_channel_subscription" in source, kind
    assert "schedule_post_registration_reconcile" in source, kind
    if kind == routing.KIND_IMAGE_ASSET:
        assert "def _hmb_shot_routing_catalog" in source
    else:
        assert "def _hmb_reconcile_shot_routing" in source, kind

agent_source = source_by_kind[routing.KIND_AGENT].read_text(encoding="utf-8")
assert "prompt_owned" in agent_source
assert 'participant_kind == "prompt"' in agent_source

seedance_source = source_by_kind[routing.KIND_SEEDANCE].read_text(encoding="utf-8")
assert 'source_counts = {"image_asset": 0, "video_picker": 0}' in seedance_source
assert "def _manual_agent_prompt_source" in seedance_source
assert "def _validate_direct_media_snapshot" in seedance_source
assert "Seedance selected Shot identity does not match its direct sources" in seedance_source
assert "Agent and direct Shot media generations do not match" not in seedance_source
assert "Prompt changed after the Agent result" not in seedance_source
assert "schedule_post_deletion_reconcile(self)" in seedance_source

picker_source = source_by_kind[routing.KIND_VIDEO_PICKER].read_text(encoding="utf-8")
assert "enabled = bool(channel_uuid)" in picker_source
assert "def _hmb_standalone_shot_routing_catalog" in picker_source

manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)
widget_paths = {
    item["name"]: ROOT / item["path"]
    for item in manifest.get("widgets", [])
}
shot_widget_names = (
    "HMBAgentLibraryWidget",
    "HMBImageAssetLibraryWidget",
    "HMBFinishLookLibraryWidget",
    "HMBPromptLibraryScopedBindingWidget",
    "HMBSeedanceGenerationWidget",
    "HMBVideoPickerLibraryWidget",
)
for name in shot_widget_names:
    assert name in widget_paths, name
    assert widget_paths[name].is_file(), widget_paths[name]

shared_shot_colors = ("#F472B6", "#3B82F6", "#10B981", "#8B5CF6", "#EAB308")
for name in shot_widget_names:
    source = widget_paths[name].read_text(encoding="utf-8")
    for color in shared_shot_colors:
        assert color in source, (name, color)

agent_widget = widget_paths["HMBAgentLibraryWidget"].read_text(encoding="utf-8")
assert "hmbAgentShotOptions" in agent_widget
assert 'class="agent-shot-select' in agent_widget
assert "shot_catalog" in agent_widget

seedance_widget = widget_paths["HMBSeedanceGenerationWidget"].read_text(
    encoding="utf-8"
)
assert "hmbSeedanceShotOptions" in seedance_widget
assert 'class="hmb-seedance-shot__select' in seedance_widget
assert "shot_catalog" in seedance_widget
assert "Remote waiting" not in seedance_widget
assert "data-seedance-shot-number" in seedance_widget
assert 'name: "Only"' in seedance_widget

finish_widget = widget_paths["HMBFinishLookLibraryWidget"].read_text(
    encoding="utf-8"
)
assert "hmbFinishLookShotOptions" in finish_widget
assert 'class="hmb-finish-look__shot-select' in finish_widget
assert "shot_catalog" in finish_widget
assert "data-shot-number" in finish_widget
for color in shared_shot_colors:
    assert color in finish_widget

seedance_source = source_by_kind[routing.KIND_SEEDANCE].read_text(encoding="utf-8")
assert 'SHOT_CONNECTION_PENDING_LABEL = "Shot connection pending"' in seedance_source
assert 'SHOT_ONLY_LABEL = "Only"' in seedance_source
assert 'SHOT_ASSET_INPUT_PARAMETER = "SHOT_ASSET_IN"' in seedance_source
assert 'SHOT_PICKER_INPUT_PARAMETER = "SHOT_PICKER_IN"' in seedance_source
assert 'SHOT_FINISH_LOOK_INPUT_PARAMETER = "SHOT_FINISH_LOOK_IN"' in seedance_source
assert "_compose_finish_look_prompt" in seedance_source
assert 'resolved["prompt"] = str(params.get("prompt") or "")' in seedance_source

release_builder = (ROOT / "tools/package_runtime_release.py").read_text(
    encoding="utf-8"
)
for path in widget_paths.values():
    relative = path.relative_to(ROOT).as_posix()
    assert f'"{relative}"' in release_builder, relative

print(
    "HMB six-library Shot routing regression: PASS "
    "(catalog fan-out, exact managed edges, Prompt-filtered Agent UI, "
    "direct-source Seedance UI, release widget coverage)"
)
