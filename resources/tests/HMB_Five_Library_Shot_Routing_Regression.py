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
    routing.KIND_PROMPT,
    routing.KIND_AGENT,
    routing.KIND_SEEDANCE,
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


image = Participant(
    "ImageAsset",
    routing.KIND_IMAGE_ASSET,
    enabled=True,
    channel_uuid=CHANNEL,
    shot_uuid=SHOT,
)
video = Participant("VideoPicker", routing.KIND_VIDEO_PICKER)
prompt = Participant("Prompt", routing.KIND_PROMPT)
agent = Participant("Agent", routing.KIND_AGENT)
seedance = Participant("Seedance", routing.KIND_SEEDANCE)
NODES = [image, video, prompt, agent, seedance]
CATALOG = catalog()
image._hmb_shot_routing_catalog = lambda: CATALOG  # type: ignore[attr-defined]

created_edges: set[tuple[str, str, str, str]] = set()


def ensure_edge(edge: Any, _subscriptions: Any) -> tuple[bool, str]:
    created_edges.add(
        (
            edge.source.name,
            edge.source_parameter,
            edge.target.name,
            edge.target_parameter,
        )
    )
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
assert prompt.catalog_count == 1
assert agent.catalog_count == 1
assert seedance.catalog_count == 1
assert prompt.shot_uuid == SHOT
assert agent.shot_uuid == SHOT
assert seedance.shot_uuid == SHOT

assert created_edges == {
    ("ImageAsset", "SHOT_ASSET_OUT", "Prompt", "SHOT_ASSET_IN"),
    ("VideoPicker", "SHOT_PICKER_OUT", "Prompt", "SHOT_PICKER_IN"),
    ("Prompt", "PROMPT_OUT", "Agent", "SHOT_PROMPT_IN"),
    ("ImageAsset", "SHOT_ASSET_OUT", "Seedance", "SHOT_ASSET_IN"),
    ("VideoPicker", "SHOT_PICKER_OUT", "Seedance", "SHOT_PICKER_IN"),
}


# Seedance must route either media source independently. Prompt text stays on
# the public/manual input and therefore creates no hidden Prompt/Agent edge.
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
    def _hmb_reject_duplicate_shot_selection(self, _reason: Any = "") -> dict[str, Any]:
        self.enabled = False
        self.channel_uuid = ""
        self.shot_uuid = ""
        self.shot_name = "Only"
        return self._hmb_shot_channel_subscription()


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
NODES[:] = [duplicate_image, duplicate_a, duplicate_b]
created_edges.clear()
duplicate_result = routing.reconcile_shot_routing(
    duplicate_image,
    _allow_unready_cleanup=True,
)
assert duplicate_result["ok"] is True, duplicate_result
assert duplicate_a.enabled is False and duplicate_b.enabled is False
assert duplicate_a.statuses[-1]["code"] == "only"
assert duplicate_b.statuses[-1]["code"] == "only"


# Three independent Shot chains must remain exact even though every managed
# edge is hidden from the canvas. No node age/name fallback may cross-connect
# Prompt 1 to Agent/Seedance 2 or 3.
multi_shots = [
    {
        "shot_uuid": f"{number}3333333-3333-4333-8333-333333333333"[:36],
        "number": number,
        "name": f"Shot {number}",
        "revision": 1,
    }
    for number in (1, 2, 3)
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
assert len(created_edges) == 15, created_edges
for shot in multi_shots:
    number = shot["number"]
    exact_edges = {
        ("ImageAssetExact", "SHOT_ASSET_OUT", f"Prompt{number}", "SHOT_ASSET_IN"),
        ("VideoPickerExact", "SHOT_PICKER_OUT", f"Prompt{number}", "SHOT_PICKER_IN"),
        (f"Prompt{number}", "PROMPT_OUT", f"Agent{number}", "SHOT_PROMPT_IN"),
        ("ImageAssetExact", "SHOT_ASSET_OUT", f"Seedance{number}", "SHOT_ASSET_IN"),
        ("VideoPickerExact", "SHOT_PICKER_OUT", f"Seedance{number}", "SHOT_PICKER_IN"),
    }
    assert exact_edges <= created_edges
for source_name, _source_port, target_name, _target_port in created_edges:
    source_number = source_name[-1:] if source_name.startswith(("Prompt", "Agent")) else ""
    target_number = target_name[-1:] if target_name.startswith(("Prompt", "Agent", "Seedance")) else ""
    if source_number and target_number:
        assert source_number == target_number, (source_name, target_name)


source_by_kind = {
    routing.KIND_IMAGE_ASSET: ROOT / "HMBImageAssetLibrary.py",
    routing.KIND_VIDEO_PICKER: ROOT / "HMBVideoPickerLibrary.py",
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
assert "Agent and direct Shot media generations do not match" in seedance_source
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
for name in (
    "HMBAgentLibraryWidget",
    "HMBImageAssetLibraryWidget",
    "HMBPromptLibraryScopedBindingWidget",
    "HMBSeedanceGenerationWidget",
    "HMBVideoPickerLibraryWidget",
):
    assert name in widget_paths, name
    assert widget_paths[name].is_file(), widget_paths[name]

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

seedance_source = source_by_kind[routing.KIND_SEEDANCE].read_text(encoding="utf-8")
assert 'SHOT_CONNECTION_PENDING_LABEL = "Shot connection pending"' in seedance_source
assert 'SHOT_ONLY_LABEL = "Only"' in seedance_source
assert 'SHOT_ASSET_INPUT_PARAMETER = "SHOT_ASSET_IN"' in seedance_source
assert 'SHOT_PICKER_INPUT_PARAMETER = "SHOT_PICKER_IN"' in seedance_source
assert 'resolved["prompt"] = str(params.get("prompt") or "")' in seedance_source

release_builder = (ROOT / "resources/build_developer_release.py").read_text(
    encoding="utf-8"
)
for path in widget_paths.values():
    relative = path.relative_to(ROOT).as_posix()
    assert f'"{relative}"' in release_builder, relative

print(
    "HMB five-library Shot routing regression: PASS "
    "(catalog fan-out, exact managed edges, Prompt-filtered Agent UI, "
    "direct-source Seedance UI, release widget coverage)"
)
