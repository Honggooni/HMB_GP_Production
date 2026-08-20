from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sys
import time
import types
from copy import deepcopy
from pathlib import Path
from typing import Any


def _install_clean_ci_griptape_stubs() -> None:
    """Provide only the import surface this host-independent regression needs."""

    griptape_missing = importlib.util.find_spec("griptape") is None
    griptape_nodes_missing = importlib.util.find_spec("griptape_nodes") is None
    if not griptape_missing and not griptape_nodes_missing:
        return

    def package(name: str) -> types.ModuleType:
        existing = sys.modules.get(name)
        if existing is not None:
            return existing
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = module
        if "." in name:
            parent_name, child_name = name.rsplit(".", 1)
            setattr(package(parent_name), child_name, module)
        return module

    def module(name: str, **attributes: Any) -> types.ModuleType:
        parent_name, child_name = name.rsplit(".", 1)
        parent = package(parent_name)
        installed = types.ModuleType(name)
        installed.__dict__.update(attributes)
        sys.modules[name] = installed
        setattr(parent, child_name, installed)
        return installed

    class StubValue:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.__dict__.update(kwargs)

        def __enter__(self) -> "StubValue":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    class StubParameterMode:
        INPUT = "INPUT"
        OUTPUT = "OUTPUT"
        PROPERTY = "PROPERTY"

    class StubDataNode:
        pass

    class StubSuccessFailureNode(StubDataNode):
        pass

    class StubFileLoadError(Exception):
        pass

    class StubExistingFilePolicy:
        CREATE_NEW = object()
        FAIL = object()
        OVERWRITE = object()

    class StubGriptapeNodes:
        pass

    if griptape_missing:
        artifacts = package("griptape.artifacts")
        artifacts.VideoUrlArtifact = StubValue
        module(
            "griptape.artifacts.video_url_artifact",
            VideoUrlArtifact=StubValue,
        )

    if not griptape_nodes_missing:
        return

    module(
        "griptape_nodes.drivers.storage.griptape_cloud_storage_driver",
        GriptapeCloudStorageDriver=StubValue,
    )
    module(
        "griptape_nodes.exe_types.core_types",
        Parameter=StubValue,
        ParameterGroup=StubValue,
        ParameterList=StubValue,
        ParameterMode=StubParameterMode,
    )
    module(
        "griptape_nodes.exe_types.node_types",
        DataNode=StubDataNode,
        SuccessFailureNode=StubSuccessFailureNode,
    )
    module(
        "griptape_nodes.exe_types.param_components.project_file_parameter",
        ProjectFileParameter=StubValue,
    )
    for parameter_module, parameter_name in (
        ("parameter_bool", "ParameterBool"),
        ("parameter_button", "ParameterButton"),
        ("parameter_dict", "ParameterDict"),
        ("parameter_image", "ParameterImage"),
        ("parameter_int", "ParameterInt"),
        ("parameter_string", "ParameterString"),
        ("parameter_video", "ParameterVideo"),
    ):
        module(
            f"griptape_nodes.exe_types.param_types.{parameter_module}",
            **{parameter_name: StubValue},
        )
    module(
        "griptape_nodes.files.file",
        File=StubValue,
        FileLoadError=StubFileLoadError,
    )
    module(
        "griptape_nodes.retained_mode.events.os_events",
        ExistingFilePolicy=StubExistingFilePolicy,
    )
    module(
        "griptape_nodes.retained_mode.events.project_events",
        MacroPath=StubValue,
    )
    module(
        "griptape_nodes.retained_mode.file_metadata.sidecar_metadata",
        write_sidecar=lambda *_args, **_kwargs: None,
    )
    module(
        "griptape_nodes.retained_mode.griptape_nodes",
        GriptapeNodes=StubGriptapeNodes,
    )
    module("griptape_nodes.traits.options", Options=StubValue)


_install_clean_ci_griptape_stubs()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import HMBSeedanceGeneration as target
import HMBVideoPickerLibrary as picker_target


CHANNEL = "11111111-1111-4111-8111-111111111111"
SHOT = "22222222-2222-4222-8222-222222222222"


def canonical(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def snapshot(
    *,
    kind: str,
    selected: list[str],
    media: dict[str, str],
) -> dict[str, Any]:
    picker = kind == "video_picker"
    shot: dict[str, Any] = {
        "shot_uuid": SHOT,
        "number": 2,
        "name": "Second Shot",
        "revision": 7,
        "selected_source_uids": list(selected),
    }
    if picker:
        shot["picker_payload"] = {"media_ready": bool(selected)}
    records_key = "ordered_videos" if picker else "ordered_assets"
    records = [
        {"source_uid": uid, "metadata": {"label": uid}}
        for uid in media
    ]
    metadata = {
        "channel_uuid": CHANNEL,
        "generation": 9 if picker else 8,
        "shots": [shot],
        records_key: records,
    }
    descriptors = [
        {
            "source_uid": uid,
            "media_value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        }
        for uid, value in media.items()
    ]
    return {
        "schema": (
            "hmb-picker-shot-routing-snapshot"
            if picker
            else "hmb-shot-routing-snapshot"
        ),
        "version": 1,
        "publisher_instance_uuid": (
            "33333333-3333-4333-8333-333333333333"
            if picker
            else "44444444-4444-4444-8444-444444444444"
        ),
        **metadata,
        "metadata_sha256": canonical(metadata),
        "media_sha256": canonical({"media_descriptors": descriptors}),
        "media_by_source_uid": dict(media),
    }


class Source:
    def __init__(self, kind: str, value: dict[str, Any]) -> None:
        self.kind = kind
        self.value = value

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        return {
            "participant_kind": self.kind,
            "enabled": True,
            "channel_uuid": CHANNEL,
            "shot_uuid": SHOT,
            "shot_number": 2,
            "shot_name": "Second Shot",
        }

    def _hmb_shot_routing_snapshot(self, expected_channel_uuid: str = "") -> dict[str, Any]:
        assert expected_channel_uuid in {"", CHANNEL}
        return deepcopy(self.value)


def generator(
    image: Source | None,
    picker: Source | None,
    agent_source: Any | None = None,
) -> target.HMBSeedanceGeneration:
    node = object.__new__(target.HMBSeedanceGeneration)
    node._reconcile_shared_shot_routing = lambda strict=False: {  # type: ignore[method-assign]
        "ok": True,
        "code": "ready",
    }
    node._hmb_shot_channel_subscription = lambda: {  # type: ignore[method-assign]
        "enabled": True,
        "channel_uuid": CHANNEL,
        "shot_uuid": SHOT,
        "shot_number": 2,
        "shot_name": "Second Shot",
    }
    sources = {}
    if image is not None:
        sources[target.SHOT_ASSET_INPUT_PARAMETER] = image
    if picker is not None:
        sources[target.SHOT_PICKER_INPUT_PARAMETER] = picker

    def exact(
        target_name: str,
        source_name: str,
        *,
        required: bool = True,
    ) -> Source | None:
        expected = {
            target.SHOT_ASSET_INPUT_PARAMETER: "SHOT_ASSET_OUT",
            target.SHOT_PICKER_INPUT_PARAMETER: "SHOT_PICKER_OUT",
        }
        assert source_name == expected[target_name]
        if target_name not in sources:
            if required:
                raise RuntimeError("required source missing")
            return None
        return sources[target_name]

    node._exact_incoming_source = exact  # type: ignore[method-assign]
    node._manual_agent_prompt_source = lambda: agent_source  # type: ignore[method-assign]
    return node


image = Source(
    "image_asset",
    snapshot(
        kind="image_asset",
        selected=["image-b", "image-a"],
        media={"image-a": "@image1", "image-b": "@image2"},
    ),
)
picker = Source(
    "video_picker",
    snapshot(
        kind="video_picker",
        selected=["video-a"],
        media={"video-a": "@video1"},
    ),
)
node = generator(image, picker)

# No Agent or Prompt node participates. Prompt text remains exactly the public
# direct/manual input, while media order comes from the two exact Shot sources.
resolved = node._resolve_exact_shot_generation_inputs({"prompt": "manual Agent text"})
assert resolved["prompt"] == "manual Agent text"
assert resolved["reference_images"] == ["@image2", "@image1"]
assert resolved["video_references"] == ["@video1"]
assert resolved["input_mode"] == target.INPUT_MODE_MULTIMODAL_REFERENCES


def valid_params(*, prompt: str = "") -> dict[str, Any]:
    return {
        "resume_generation_id": "",
        "model_id": target.SEEDANCE_2_0_MODEL_ID,
        "input_mode": target.INPUT_MODE_TEXT_ONLY,
        "prompt": prompt,
        "first_frame": None,
        "last_frame": None,
        "reference_images": [],
        "video_reference_slots": [],
        "video_references": [],
        "reference_audio": [],
        "resolution": "1080p",
        "ratio": "adaptive",
        "duration": 5,
        "generate_audio": True,
        "watermark": False,
        "return_last_frame": False,
        "execution_expires_after": 86400,
        "priority": 0,
        "poll_interval_seconds": 5,
        "generation_timeout_seconds": 60,
        "auto_publish_local_videos": True,
        "local_video_upload_service": target.LOCAL_VIDEO_UPLOAD_GRIPTAPE,
        "tos_region": target.DEFAULT_TOS_REGION,
        "tos_endpoint": target.DEFAULT_TOS_ENDPOINT,
        "tos_url_validity_seconds": target.DEFAULT_TOS_URL_VALIDITY_SECONDS,
    }


# StartFlow used to validate only the empty public parameter lists and reject a
# valid hidden Shot before process() could resolve its ImageAsset/VideoPicker
# snapshot. Preflight must resolve that snapshot without weakening runtime Agent
# provenance checks.
preflight_image = generator(image, None)
preflight_image._get_parameters = lambda: valid_params()  # type: ignore[method-assign]
preflight_image._has_incoming_parameter_connection = (  # type: ignore[method-assign]
    lambda _name: False
)
preflight_image_params = preflight_image._get_parameters_for_start_validation()
assert preflight_image_params["reference_images"] == ["@image2", "@image1"]
assert preflight_image_params["input_mode"] == target.INPUT_MODE_MULTIMODAL_REFERENCES
preflight_image._validate_parameters(preflight_image_params)

# A connected upstream Prompt/Agent has not produced text when whole-flow
# validation runs. A validation-only sentinel permits scheduling; it never
# mutates the real parameter value and runtime still rejects an empty result.
preflight_only = object.__new__(target.HMBSeedanceGeneration)
preflight_only_base = valid_params()
preflight_only._get_parameters = (  # type: ignore[method-assign]
    lambda: deepcopy(preflight_only_base)
)


def resolve_only_preflight(
    params: dict[str, Any],
    *,
    verify_agent_prompt: bool = True,
) -> dict[str, Any]:
    assert verify_agent_prompt is False
    return dict(params)


preflight_only._resolve_exact_shot_generation_inputs = (  # type: ignore[method-assign]
    resolve_only_preflight
)
preflight_only._has_incoming_parameter_connection = (  # type: ignore[method-assign]
    lambda name: name == "prompt"
)
preflight_only_params = preflight_only._get_parameters_for_start_validation()
assert preflight_only_params["prompt"] == "HMB connected prompt pending execution"
assert preflight_only_base["prompt"] == ""
preflight_only._validate_parameters(preflight_only_params)
try:
    preflight_only._validate_parameters(preflight_only_base)
except ValueError as exc:
    assert "Provide a prompt" in str(exc)
else:
    raise AssertionError("Runtime accepted an empty connected prompt result.")


async def assert_blocking_stage_is_background_and_cleanup_safe() -> None:
    stage_node = object.__new__(target.HMBSeedanceGeneration)
    completed: list[str] = []

    def slow_stage(label: str) -> str:
        time.sleep(0.08)
        completed.append(label)
        return label

    running = asyncio.create_task(
        stage_node._run_blocking_generation_stage(slow_stage, "background")
    )
    await asyncio.sleep(0.01)
    assert not running.done(), "Blocking stage unexpectedly ran on the event loop."
    assert await running == "background"

    cancelled = asyncio.create_task(
        stage_node._run_blocking_generation_stage(slow_stage, "cancelled")
    )
    await asyncio.sleep(0.01)
    cancelled.cancel()
    try:
        await cancelled
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Cancellation was not propagated after worker completion.")
    # The helper must not return cancellation while an upload can still append
    # temporary objects after the caller's finally-cleanup has run.
    assert completed == ["background", "cancelled"]


asyncio.run(assert_blocking_stage_is_background_and_cleanup_safe())


class AgentSource:
    def __init__(self, *, shot_uuid: str = SHOT, image_hash: str = "") -> None:
        self.shot_uuid = shot_uuid
        self.image_hash = image_hash

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        return {
            "participant_kind": "agent",
            "enabled": True,
            "channel_uuid": CHANNEL,
            "shot_uuid": self.shot_uuid,
            "shot_number": 2,
            "shot_name": "Second Shot",
        }

    def _hmb_generator_shot_snapshot(self, final_text: Any) -> dict[str, Any]:
        text = str(final_text or "")
        return {
            "schema": "hmb-agent-generator-shot-snapshot",
            "version": 1,
            "channel_uuid": CHANNEL,
            "shot_uuid": self.shot_uuid,
            "shot_number": 2,
            "shot_name": "Second Shot",
            "prompt_generation": 4,
            "visible_prompt_sha256": "1" * 64,
            "image_media_sha256": self.image_hash or target.HMBSeedanceGeneration._media_list_sha256(
                ["@image2", "@image1"]
            ),
            "video_media_sha256": target.HMBSeedanceGeneration._media_list_sha256(
                ["@video1"]
            ),
            "final_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }


# A manually connected HMBAgent prompt is accepted only when its immutable
# result snapshot matches the exact direct media generation for this Shot.
agent_source = AgentSource()
agent_resolved = generator(image, picker, agent_source)._resolve_exact_shot_generation_inputs(
    {"prompt": "Agent FINAL TEXT"}
)
assert agent_resolved["prompt"] == "Agent FINAL TEXT"

try:
    generator(
        image,
        picker,
        AgentSource(shot_uuid="66666666-6666-4666-8666-666666666666"),
    )._resolve_exact_shot_generation_inputs({"prompt": "wrong Shot"})
except RuntimeError as exc:
    assert "another Shot" in str(exc) or "do not match" in str(exc)
else:
    raise AssertionError("Seedance accepted an HMBAgent prompt from another Shot.")

try:
    generator(
        image,
        picker,
        AgentSource(image_hash="f" * 64),
    )._resolve_exact_shot_generation_inputs({"prompt": "stale media"})
except RuntimeError as exc:
    assert "media generations" in str(exc)
else:
    raise AssertionError("Seedance accepted a stale HMBAgent media generation.")

# ImageAsset alone is sufficient for image + prompt generation.
image_only = generator(image, None)._resolve_exact_shot_generation_inputs(
    {"prompt": "image-only prompt"}
)
assert image_only["reference_images"] == ["@image2", "@image1"]
assert image_only["video_references"] == []
assert image_only["input_mode"] == target.INPUT_MODE_MULTIMODAL_REFERENCES

# VideoPicker alone is sufficient for video + prompt generation.
video_only = generator(None, picker)._resolve_exact_shot_generation_inputs(
    {"prompt": "video-only prompt"}
)
assert video_only["reference_images"] == []
assert video_only["video_references"] == ["@video1"]
assert video_only["input_mode"] == target.INPUT_MODE_MULTIMODAL_REFERENCES

# Empty media on one connected source remains authoritative.
empty_picker = Source(
    "video_picker",
    snapshot(kind="video_picker", selected=[], media={}),
)
empty_result = generator(image, empty_picker)._resolve_exact_shot_generation_inputs(
    {"prompt": "image-only prompt"}
)
assert empty_result["video_references"] == []
assert empty_result["reference_images"] == ["@image2", "@image1"]

# Only is a genuine prompt-only mode and clears every stale media field before
# request validation or upload preparation.
only = object.__new__(target.HMBSeedanceGeneration)
only._reconcile_shared_shot_routing = lambda strict=False: {  # type: ignore[method-assign]
    "ok": True,
    "code": "only",
}
only._hmb_shot_channel_subscription = lambda: {  # type: ignore[method-assign]
    "enabled": False,
    "channel_uuid": "",
    "shot_uuid": "",
    "shot_number": 1,
    "shot_name": "Only",
}
only._clear_remote_prompt_authority = lambda _reason: None  # type: ignore[method-assign]
only_result = only._resolve_exact_shot_generation_inputs({
    "prompt": "prompt only",
    "reference_images": ["stale-image"],
    "video_references": ["stale-video"],
    "video_reference_slots": ["stale-slot"],
})
assert only_result["prompt"] == "prompt only"
assert only_result["reference_images"] == []
assert only_result["video_references"] == []
assert only_result["video_reference_slots"] == []
assert only_result["input_mode"] == target.INPUT_MODE_TEXT_ONLY

# Exact UUID/name/number matching is fail-closed.
bad_picker_snapshot = snapshot(
    kind="video_picker",
    selected=["video-a"],
    media={"video-a": "@video1"},
)
bad_picker_snapshot["shots"][0]["name"] = "Wrong Shot"
metadata = {
    "channel_uuid": bad_picker_snapshot["channel_uuid"],
    "generation": bad_picker_snapshot["generation"],
    "shots": bad_picker_snapshot["shots"],
    "ordered_videos": bad_picker_snapshot["ordered_videos"],
}
bad_picker_snapshot["metadata_sha256"] = canonical(metadata)
try:
    generator(image, Source("video_picker", bad_picker_snapshot))._resolve_exact_shot_generation_inputs(
        {"prompt": "must fail"}
    )
except RuntimeError as exc:
    assert "identity" in str(exc)
else:
    raise AssertionError("Mismatched direct Shot identity was accepted.")

source = (ROOT / "_hmb_shot_routing.py").read_text(encoding="utf-8")
assert '(image, "SHOT_ASSET_OUT", "SHOT_ASSET_IN")' in source
assert '(picker, "SHOT_PICKER_OUT", "SHOT_PICKER_IN")' in source
assert 'or (image is None and picker is None)' in source
assert 'ShotEdge(agent.node, "output", target.node, "SHOT_PROMPT_IN")' not in source

# A standalone VideoPicker publishes its local Shot 1 through a private,
# media-free catalog and a matching atomic snapshot.  This is the authority used
# by the video + prompt mode when no ImageAsset node exists.
standalone_picker = object.__new__(picker_target.HMBVideoPickerLibrary)
standalone_state = picker_target._default_widget_state()
standalone_picker._picker_state = lambda: deepcopy(standalone_state)  # type: ignore[method-assign]
standalone_picker._hmb_picker_publisher_uuid = "55555555-5555-4555-8555-555555555555"
standalone_picker._hmb_shot_route_status = {}
standalone_picker._hmb_shot_snapshot_identity = ""
standalone_picker._hmb_shot_snapshot_generation = 0
picker_subscription = standalone_picker._hmb_shot_channel_subscription()
assert picker_subscription["enabled"] is True
assert picker_subscription["participant_kind"] == "video_picker"
assert picker_subscription["shot_number"] == 1
standalone_catalog = standalone_picker._hmb_standalone_shot_routing_catalog()
assert standalone_catalog["channel_uuid"] == picker_subscription["channel_uuid"]
assert [item["number"] for item in standalone_catalog["shots"]] == [1]
standalone_snapshot = standalone_picker._hmb_shot_routing_snapshot(
    picker_subscription["channel_uuid"]
)
assert standalone_snapshot["channel_uuid"] == picker_subscription["channel_uuid"]
assert standalone_snapshot["shots"][0]["shot_uuid"] == picker_subscription["shot_uuid"]
assert standalone_snapshot["shots"][0]["selected_source_uids"] == []


class Participant:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._hmb_node_deleted = False

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        return {
            "participant_kind": self.kind,
            "enabled": True,
            "channel_uuid": CHANNEL,
            "shot_uuid": SHOT,
            "shot_number": 2,
            "shot_name": "Second Shot",
        }


catalog_probe = object.__new__(target.HMBSeedanceGeneration)
catalog_probe._hmb_other_seedance_shot_claims = lambda _channel: set()  # type: ignore[method-assign]
catalog_probe._shot_identity = lambda: {  # type: ignore[method-assign]
    "channel_uuid": "",
    "shot_uuid": "",
}
catalog_value = {
    "channel_uuid": CHANNEL,
    "shots": [{"shot_uuid": SHOT, "number": 2, "name": "Second Shot"}],
}
original_same_flow = target._shot_routing._same_flow_nodes
try:
    for kinds in (
        ("image_asset",),
        ("video_picker",),
        ("image_asset", "video_picker"),
    ):
        target._shot_routing._same_flow_nodes = lambda _node, kinds=kinds: (
            "flow",
            [Participant(kind) for kind in kinds],
        )
        assert catalog_probe._hmb_available_seedance_shot_catalog(catalog_value)
    target._shot_routing._same_flow_nodes = lambda _node: (
        "flow",
        [Participant("image_asset"), Participant("image_asset")],
    )
    assert catalog_probe._hmb_available_seedance_shot_catalog(catalog_value) == {}
finally:
    target._shot_routing._same_flow_nodes = original_same_flow

print(
    "HMB Seedance direct Shot source regression: PASS "
    "(Only, image-only, video-only, combined, exact direct Shot media)"
)
