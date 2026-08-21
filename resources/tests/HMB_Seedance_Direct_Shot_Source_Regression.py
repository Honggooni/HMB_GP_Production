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
        artifacts.ImageUrlArtifact = StubValue
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
TASK_TEXT_ONLY = "Text Only"
TASK_FIRST_LAST_FRAME = "First/Last Frame"
TASK_REFERENCE_TO_VIDEO = "Reference to Video"
TASK_VIDEO_EDITING = "Video Editing"
TASK_VIDEO_EXTENSION = "Video Extension"
TASK_STORAGE_CHOICES = (
    TASK_TEXT_ONLY,
    TASK_FIRST_LAST_FRAME,
    TASK_REFERENCE_TO_VIDEO,
    TASK_VIDEO_EDITING,
    TASK_VIDEO_EXTENSION,
)


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
resolved = node._resolve_exact_shot_generation_inputs(
    {
        "prompt": "manual Agent text",
        "model_id": target.SEEDANCE_2_5_MODEL_ID,
        "task": TASK_VIDEO_EDITING,
        "duration": -1,
        "first_frame": "manual-first-frame-must-not-leak",
        "last_frame": "manual-last-frame-must-not-leak",
        "reference_images": ["manual-image-must-not-leak"],
        "video_references": ["manual-video-must-not-leak"],
        "video_reference_slots": ["manual-slot-must-not-leak"],
        "reference_audio": ["manual-audio-must-not-leak"],
    }
)
assert resolved["prompt"] == "manual Agent text"
assert resolved["task"] == TASK_REFERENCE_TO_VIDEO
assert resolved["duration"] == 5
assert resolved["first_frame"] is None
assert resolved["last_frame"] is None
assert resolved["reference_images"] == ["@image2", "@image1"]
assert resolved["video_references"] == ["@video1"]
assert resolved["video_reference_slots"] == []
assert resolved["reference_audio"] == []
assert resolved["input_mode"] == target.INPUT_MODE_MULTIMODAL_REFERENCES


def valid_params(*, prompt: str = "") -> dict[str, Any]:
    return {
        "resume_generation_id": "",
        "model_id": target.SEEDANCE_2_0_MODEL_ID,
        "task": TASK_TEXT_ONLY,
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


# Seedance 2.5 is a separate active Broker contract.  Persisted BytePlus model
# values canonicalize to the China-route Doubao ID, while the provider alias is
# never submitted directly to the Broker.  Existing retired Mini workflows keep
# their one-way migration to full 2.0; adding 2.5 must not silently retarget them.
SEEDANCE_2_5_MODEL_ID = "doubao-seedance-2-5-260628"
SEEDANCE_2_5_BYTEPLUS_ALIAS = "dreamina-seedance-2-5-260628"
assert target.MODEL_NAME_SEEDANCE_2_5 == "Seedance 2.5"
assert target.SEEDANCE_2_5_MODEL_ID == SEEDANCE_2_5_MODEL_ID
assert target.MODEL_ID_ALIASES[target.MODEL_NAME_SEEDANCE_2_5] == (
    SEEDANCE_2_5_MODEL_ID
)
assert target.MODEL_ID_ALIASES[SEEDANCE_2_5_BYTEPLUS_ALIAS] == (
    SEEDANCE_2_5_MODEL_ID
)
assert target.MODEL_ID_ALIASES[SEEDANCE_2_5_MODEL_ID] == SEEDANCE_2_5_MODEL_ID
assert target.MODEL_DISPLAY_NAME_BY_ID[SEEDANCE_2_5_MODEL_ID] == (
    target.MODEL_NAME_SEEDANCE_2_5
)
assert target.MODEL_RESOLUTIONS[SEEDANCE_2_5_MODEL_ID] == (
    "720p",
    "1080p",
)
assert target.MODEL_DEFAULT_RESOLUTIONS[SEEDANCE_2_5_MODEL_ID] == "720p"
assert target.DURATION_STORAGE_CHOICES == (-1, *range(4, 31))
assert SEEDANCE_2_5_MODEL_ID in target.BROKER_SUPPORTED_MODEL_IDS
assert SEEDANCE_2_5_BYTEPLUS_ALIAS not in target.BROKER_SUPPORTED_MODEL_IDS
assert SEEDANCE_2_5_MODEL_ID in target._HMBAIBrokerBridge._MODEL_GENERATION_FIELDS
assert target.TASK_PARAMETER == "task"
assert target.TASK_TEXT_ONLY == TASK_TEXT_ONLY
assert target.TASK_FIRST_LAST_FRAME == TASK_FIRST_LAST_FRAME
assert target.TASK_REFERENCE_TO_VIDEO == TASK_REFERENCE_TO_VIDEO
assert target.TASK_VIDEO_EDITING == TASK_VIDEO_EDITING
assert target.TASK_VIDEO_EXTENSION == TASK_VIDEO_EXTENSION
assert target.TASK_STORAGE_CHOICES == TASK_STORAGE_CHOICES
assert target.MODEL_TASK_CHOICES == {
    target.SEEDANCE_2_0_MODEL_ID: TASK_STORAGE_CHOICES[:3],
    target.SEEDANCE_2_0_FAST_MODEL_ID: TASK_STORAGE_CHOICES[:3],
    target.SEEDANCE_2_5_MODEL_ID: TASK_STORAGE_CHOICES,
}
assert "task" in target._HMBAIBrokerBridge._ALLOWED_GENERATION_FIELDS
assert "omni_reference_task_type" in target._HMBAIBrokerBridge._MODEL_GENERATION_FIELDS[
    target.SEEDANCE_2_5_MODEL_ID
]
assert "task" not in target._HMBAIBrokerBridge._MODEL_GENERATION_FIELDS[
    target.SEEDANCE_2_5_MODEL_ID
]
for broker_model_id in (
    target.SEEDANCE_2_0_MODEL_ID,
    target.SEEDANCE_2_0_FAST_MODEL_ID,
):
    assert "task" not in target._HMBAIBrokerBridge._MODEL_GENERATION_FIELDS[
        broker_model_id
    ]
for retired_model in target.RETIRED_SEEDANCE_MODEL_VALUES:
    assert target.MODEL_ID_ALIASES[retired_model] == target.SEEDANCE_2_0_MODEL_ID


# Exercise serialized hydration through the real HMB override while replacing
# only SuccessFailureNode.set_parameter_value with Griptape's relevant Options
# behavior: a value outside ``simple_dropdown`` is coerced to its first choice.
# Both host replay orders must preserve a saved 2.5 duration of 30 seconds, and
# the post-load pass must narrow an incompatible 2.0 workflow back to 4..15.
def hydration_probe() -> tuple[
    target.HMBSeedanceGeneration,
    dict[str, Any],
    dict[str, types.SimpleNamespace],
]:
    state: dict[str, Any] = {
        "model_id": target.MODEL_NAME_SEEDANCE_2_0,
        "resolution": "4k",
        "duration": 5,
        "task": TASK_REFERENCE_TO_VIDEO,
    }
    parameters = {
        "model_id": types.SimpleNamespace(
            ui_options={
                "simple_dropdown": [
                    target.MODEL_NAME_SEEDANCE_2_0,
                    target.MODEL_NAME_SEEDANCE_2_0_FAST,
                    target.MODEL_NAME_SEEDANCE_2_5,
                ]
            }
        ),
        "resolution": types.SimpleNamespace(
            ui_options={"simple_dropdown": ["4k", "1080p", "720p", "480p"]}
        ),
        "duration": types.SimpleNamespace(
            ui_options={"simple_dropdown": [-1, *range(4, 16)]}
        ),
        "task": types.SimpleNamespace(
            ui_options={"simple_dropdown": list(TASK_STORAGE_CHOICES)}
        ),
    }
    probe = object.__new__(target.HMBSeedanceGeneration)
    probe._hmb_hydration_values = state
    probe._hmb_retired_model_migration_pending = False
    probe._hmb_model_migration_active = False
    probe._hmb_node_deleted = False
    probe.get_parameter_value = (  # type: ignore[method-assign]
        lambda name: state.get(name)
    )
    probe.get_parameter_by_name = (  # type: ignore[method-assign]
        lambda name: parameters.get(name)
    )
    probe._clear_remote_prompt_authority = lambda _reason: None  # type: ignore[method-assign]
    probe._remember_direct_prompt = lambda _value: None  # type: ignore[method-assign]
    probe._set_remote_prompt_control_value = (  # type: ignore[method-assign]
        lambda _name, _value: None
    )
    probe._reconcile_shared_shot_routing = (  # type: ignore[method-assign]
        lambda strict=False: {"ok": True, "strict": strict}
    )
    probe._sync_seedance_shot_widget = lambda: None  # type: ignore[method-assign]
    return probe, state, parameters


seedance_base = target.SuccessFailureNode
base_had_set_parameter_value = hasattr(seedance_base, "set_parameter_value")
base_set_parameter_value = getattr(seedance_base, "set_parameter_value", None)


def options_coercing_base_set(
    self: target.HMBSeedanceGeneration,
    param_name: str,
    value: Any,
    **_kwargs: Any,
) -> None:
    parameter = self.get_parameter_by_name(param_name)
    choices = (
        list(parameter.ui_options.get("simple_dropdown") or [])
        if parameter is not None
        else []
    )
    stored = value if not choices or value in choices else choices[0]
    self._hmb_hydration_values[param_name] = stored


original_post_hydration_schedule = (
    target._shot_routing.schedule_post_hydration_reconcile
)
setattr(seedance_base, "set_parameter_value", options_coercing_base_set)
target._shot_routing.schedule_post_hydration_reconcile = lambda _node: False
try:
    duration_2_5_choices = [*range(4, 31)]
    for hydration_order in (
        (("model_id", SEEDANCE_2_5_BYTEPLUS_ALIAS), ("duration", 30)),
        (("duration", 30), ("model_id", SEEDANCE_2_5_BYTEPLUS_ALIAS)),
    ):
        saved_model_probe, saved_model_state, saved_parameters = hydration_probe()
        for parameter_name, saved_value in hydration_order:
            saved_model_probe.set_parameter_value(
                parameter_name,
                saved_value,
                initial_setup=True,
            )
        assert saved_model_state["model_id"] == target.MODEL_NAME_SEEDANCE_2_5
        assert saved_model_state["duration"] == 30
        assert saved_model_probe._synchronize_model_resolution() == (
            SEEDANCE_2_5_MODEL_ID
        )
        assert saved_model_state["model_id"] == target.MODEL_NAME_SEEDANCE_2_5
        assert saved_model_state["resolution"] == "720p"
        assert saved_model_state["duration"] == 30
        assert saved_parameters["duration"].ui_options["simple_dropdown"] == (
            duration_2_5_choices
        )

    # A newly selected/restored 2.5 model inherits 720p when no serialized
    # resolution was supplied. An explicitly serialized 1080p selection must
    # still survive when it arrives before the model field.
    default_resolution_probe, default_resolution_state, _ = hydration_probe()
    default_resolution_state["resolution"] = "1080p"
    default_resolution_probe.set_parameter_value(
        "model_id",
        SEEDANCE_2_5_BYTEPLUS_ALIAS,
        initial_setup=True,
    )
    assert default_resolution_state["resolution"] == "720p"

    explicit_resolution_probe, explicit_resolution_state, _ = hydration_probe()
    explicit_resolution_state["resolution"] = "720p"
    explicit_resolution_probe.set_parameter_value(
        "resolution",
        "1080p",
        initial_setup=True,
    )
    explicit_resolution_probe.set_parameter_value(
        "model_id",
        SEEDANCE_2_5_BYTEPLUS_ALIAS,
        initial_setup=True,
    )
    assert explicit_resolution_state["resolution"] == "1080p"

    # Connected inputs use ordinary setters and their delivery order is host-
    # dependent. The Options converter must not coerce a valid 2.5 duration
    # before the paired model value arrives.
    for runtime_order in (
        (("model_id", SEEDANCE_2_5_BYTEPLUS_ALIAS), ("duration", 30)),
        (("duration", 30), ("model_id", SEEDANCE_2_5_BYTEPLUS_ALIAS)),
    ):
        runtime_probe, runtime_state, runtime_parameters = hydration_probe()
        for parameter_name, runtime_value in runtime_order:
            runtime_probe.set_parameter_value(
                parameter_name,
                runtime_value,
                initial_setup=False,
            )
            if parameter_name == "model_id":
                # The clean-CI base stub does not dispatch after_value_set;
                # mirror the real model callback's dependent-control sync.
                runtime_probe._synchronize_model_resolution()
        assert runtime_state["model_id"] == target.MODEL_NAME_SEEDANCE_2_5
        assert runtime_state["duration"] == 30
        assert runtime_parameters["duration"].ui_options["simple_dropdown"] == (
            duration_2_5_choices
        )

    saved_2_0_probe, saved_2_0_state, saved_2_0_parameters = hydration_probe()
    saved_2_0_probe.set_parameter_value(
        "model_id",
        target.MODEL_NAME_SEEDANCE_2_0,
        initial_setup=True,
    )
    saved_2_0_probe.set_parameter_value("duration", 30, initial_setup=True)
    assert saved_2_0_state["model_id"] == target.MODEL_NAME_SEEDANCE_2_0
    assert saved_2_0_state["duration"] == 5
    assert saved_2_0_parameters["duration"].ui_options["simple_dropdown"] == [
        -1,
        *range(4, 16),
    ]

    # The 2.5 converter expansion must never retire 2.0's smart duration.
    for smart_order in (
        (("model_id", target.MODEL_NAME_SEEDANCE_2_0), ("duration", -1)),
        (("duration", -1), ("model_id", target.MODEL_NAME_SEEDANCE_2_0)),
    ):
        smart_probe, smart_state, smart_parameters = hydration_probe()
        for parameter_name, smart_value in smart_order:
            smart_probe.set_parameter_value(
                parameter_name,
                smart_value,
                initial_setup=True,
            )
        assert smart_state["model_id"] == target.MODEL_NAME_SEEDANCE_2_0
        assert smart_state["duration"] == -1
        assert smart_parameters["duration"].ui_options["simple_dropdown"] == [
            -1,
            *range(4, 16),
        ]

    # Task and model values are independent serialized/connected inputs, so
    # neither replay order may lose a 2.5-only task before the model arrives.
    # The visible dropdown is narrowed only after both values are available.
    for task_hydration_order in (
        (
            ("model_id", SEEDANCE_2_5_BYTEPLUS_ALIAS),
            ("task", TASK_VIDEO_EDITING),
        ),
        (
            ("task", TASK_VIDEO_EDITING),
            ("model_id", SEEDANCE_2_5_BYTEPLUS_ALIAS),
        ),
    ):
        task_probe, task_state, task_parameters = hydration_probe()
        for parameter_name, saved_value in task_hydration_order:
            task_probe.set_parameter_value(
                parameter_name,
                saved_value,
                initial_setup=True,
            )
        task_probe._synchronize_model_resolution()
        assert task_state["model_id"] == target.MODEL_NAME_SEEDANCE_2_5
        assert task_state["task"] == TASK_VIDEO_EDITING
        assert task_parameters["task"].ui_options["simple_dropdown"] == list(
            TASK_STORAGE_CHOICES
        )

    # A stale 2.5-only task cannot survive hydration under either 2.0 model.
    # Fall back to Reference to Video, which preserves the former Multimodal
    # References meaning and is valid for both legacy models.
    for legacy_model_name in (
        target.MODEL_NAME_SEEDANCE_2_0,
        target.MODEL_NAME_SEEDANCE_2_0_FAST,
    ):
        for task_hydration_order in (
            (
                ("model_id", legacy_model_name),
                ("task", TASK_VIDEO_EXTENSION),
            ),
            (
                ("task", TASK_VIDEO_EXTENSION),
                ("model_id", legacy_model_name),
            ),
        ):
            task_probe, task_state, task_parameters = hydration_probe()
            for parameter_name, saved_value in task_hydration_order:
                task_probe.set_parameter_value(
                    parameter_name,
                    saved_value,
                    initial_setup=True,
                )
            task_probe._synchronize_model_resolution()
            assert task_state["model_id"] == legacy_model_name
            assert task_state["task"] == TASK_REFERENCE_TO_VIDEO
            assert task_parameters["task"].ui_options["simple_dropdown"] == list(
                TASK_STORAGE_CHOICES[:3]
            )

    # A live model switch carries an explicit non-default quality forward, but
    # replaces the previous model's untouched default and invalid duration.
    switch_probe, switch_state, switch_parameters = hydration_probe()
    switch_state.update(
        {
            "model_id": target.MODEL_NAME_SEEDANCE_2_5,
            "resolution": "1080p",
            "duration": 30,
        }
    )
    switch_probe._hmb_model_switch_previous_id = target.SEEDANCE_2_0_MODEL_ID
    assert switch_probe._synchronize_model_resolution() == SEEDANCE_2_5_MODEL_ID
    assert switch_state["resolution"] == "720p"
    assert switch_state["duration"] == 30
    switch_state["model_id"] = target.MODEL_NAME_SEEDANCE_2_0
    switch_probe._hmb_model_switch_previous_id = SEEDANCE_2_5_MODEL_ID
    assert switch_probe._synchronize_model_resolution() == (
        target.SEEDANCE_2_0_MODEL_ID
    )
    assert switch_state["resolution"] == "1080p"
    assert switch_state["duration"] == 5
    assert switch_parameters["duration"].ui_options["simple_dropdown"] == [
        -1,
        *range(4, 16),
    ]
finally:
    target._shot_routing.schedule_post_hydration_reconcile = (
        original_post_hydration_schedule
    )
    if base_had_set_parameter_value:
        setattr(seedance_base, "set_parameter_value", base_set_parameter_value)
    else:
        delattr(seedance_base, "set_parameter_value")


def assert_invalid_seedance_params(
    params: dict[str, Any],
    *,
    description: str,
) -> None:
    probe = object.__new__(target.HMBSeedanceGeneration)
    try:
        probe._validate_parameters(params)
    except ValueError:
        return
    raise AssertionError(f"Seedance accepted invalid {description} parameters.")


# Model-specific limits must expand only 2.5.  Full/Fast 2.0 retain their
# existing 4..15 second and 9-image/3-video/3-audio bounds.
seedance_2_5_audio_only = valid_params(prompt="2.5 audio-only reference")
seedance_2_5_audio_only.update(
    {
        "model_id": SEEDANCE_2_5_MODEL_ID,
        "task": TASK_REFERENCE_TO_VIDEO,
        "input_mode": target.INPUT_MODE_MULTIMODAL_REFERENCES,
        "duration": 30,
        "reference_audio": [
            f"https://media.example/audio-{index:02d}.wav"
            for index in range(1, 11)
        ],
    }
)
validation_probe = object.__new__(target.HMBSeedanceGeneration)
validation_probe._validate_parameters(seedance_2_5_audio_only)


def task_params(model_id: str, task_name: str) -> dict[str, Any]:
    if task_name == TASK_VIDEO_EDITING:
        prompt = f"edit the source video for {model_id}"
    elif task_name == TASK_VIDEO_EXTENSION:
        prompt = f"extend the source video for {model_id}"
    else:
        prompt = f"{model_id} {task_name}"
    params = valid_params(prompt=prompt)
    params["model_id"] = model_id
    params["resolution"] = target.MODEL_DEFAULT_RESOLUTIONS[model_id]
    params["task"] = task_name
    if task_name == TASK_TEXT_ONLY:
        params["input_mode"] = target.INPUT_MODE_TEXT_ONLY
    elif task_name == TASK_FIRST_LAST_FRAME:
        params["input_mode"] = target.INPUT_MODE_FIRST_LAST_FRAME
        params["first_frame"] = "https://media.example/task-first.png"
    else:
        params["input_mode"] = target.INPUT_MODE_MULTIMODAL_REFERENCES
        if task_name == TASK_REFERENCE_TO_VIDEO:
            params["reference_images"] = [
                "https://media.example/task-reference.png"
            ]
        else:
            params["video_references"] = [
                "https://media.example/task-source.mp4"
            ]
            if task_name in {TASK_VIDEO_EDITING, TASK_VIDEO_EXTENSION}:
                params["duration"] = -1
    return params


# Only mode exposes exactly three tasks on both 2.0 models and all five tasks
# on 2.5. Validation, not dropdown coercion, remains the final fail-closed
# boundary for a stale or programmatically supplied unsupported task.
for model_id, allowed_tasks in (
    (target.SEEDANCE_2_0_MODEL_ID, TASK_STORAGE_CHOICES[:3]),
    (target.SEEDANCE_2_0_FAST_MODEL_ID, TASK_STORAGE_CHOICES[:3]),
    (SEEDANCE_2_5_MODEL_ID, TASK_STORAGE_CHOICES),
):
    assert target.MODEL_TASK_CHOICES[model_id] == allowed_tasks
    for task_name in allowed_tasks:
        allowed_params = task_params(model_id, task_name)
        validation_probe._validate_parameters(allowed_params)
        assert validation_probe._build_broker_payload(allowed_params)["task"] == (
            task_name
        )

# Stock 2.0 Multimodal References remains a valid prompt-only selection, while
# 2.5 Reference-to-Video is a declared provider subtask and needs a reference.
seedance_2_0_empty_multimodal = task_params(
    target.SEEDANCE_2_0_MODEL_ID,
    TASK_REFERENCE_TO_VIDEO,
)
seedance_2_0_empty_multimodal["reference_images"] = []
seedance_2_0_empty_multimodal["video_references"] = []
seedance_2_0_empty_multimodal["reference_audio"] = []
validation_probe._validate_parameters(seedance_2_0_empty_multimodal)
empty_multimodal_payload = validation_probe._build_broker_payload(
    seedance_2_0_empty_multimodal
)
assert empty_multimodal_payload["input_mode"] == (
    target.INPUT_MODE_MULTIMODAL_REFERENCES
)
assert "image_urls" not in empty_multimodal_payload
assert "video_urls" not in empty_multimodal_payload
assert "audio_urls" not in empty_multimodal_payload

seedance_2_5_empty_reference = task_params(
    SEEDANCE_2_5_MODEL_ID,
    TASK_REFERENCE_TO_VIDEO,
)
seedance_2_5_empty_reference["reference_images"] = []
try:
    validation_probe._validate_parameters(seedance_2_5_empty_reference)
except ValueError as exc:
    assert "Reference to Video requires" in str(exc)
else:
    raise AssertionError("Seedance 2.5 accepted empty Reference-to-Video input.")

for model_id in (
    target.SEEDANCE_2_0_MODEL_ID,
    target.SEEDANCE_2_0_FAST_MODEL_ID,
):
    for unsupported_task in (TASK_VIDEO_EDITING, TASK_VIDEO_EXTENSION):
        try:
            validation_probe._validate_parameters(
                task_params(model_id, unsupported_task)
            )
        except ValueError as exc:
            assert "task" in str(exc).casefold()
        else:
            raise AssertionError(
                f"{model_id} accepted unsupported Only task {unsupported_task!r}."
            )

unknown_task = task_params(SEEDANCE_2_5_MODEL_ID, TASK_REFERENCE_TO_VIDEO)
unknown_task["task"] = "Browser Supplied Unknown Task"
try:
    validation_probe._validate_parameters(unknown_task)
except ValueError as exc:
    assert "task" in str(exc).casefold()
else:
    raise AssertionError("Seedance accepted an unknown Task value.")

# Manual audio is an Only-mode input. An active Shot with no exact ImageAsset or
# VideoPicker source must fail instead of silently treating hidden audio as Shot
# authority.
try:
    generator(None, None)._resolve_exact_shot_generation_inputs(
        seedance_2_5_audio_only,
        verify_agent_prompt=False,
    )
except RuntimeError as exc:
    assert "direct media source" in str(exc)
else:
    raise AssertionError("Shot mode accepted hidden Only-mode reference audio.")

# Audio-only remains valid in 2.5 Only mode and reaches the ordinary reference
# payload without any Shot identity.
seedance_2_5_audio_routed = deepcopy(seedance_2_5_audio_only)
audio_only_payload = validation_probe._build_broker_payload(
    seedance_2_5_audio_routed
)
assert audio_only_payload["audio_urls"] == seedance_2_5_audio_only[
    "reference_audio"
]

seedance_2_5_unrouted_probe = generator(None, None)
seedance_2_5_unrouted_probe._hmb_shot_channel_subscription = lambda: {  # type: ignore[method-assign]
    "enabled": False,
}
seedance_2_5_unrouted_probe._clear_remote_prompt_authority = (  # type: ignore[method-assign]
    lambda _reason: None
)
seedance_2_5_audio_unrouted = (
    seedance_2_5_unrouted_probe._resolve_exact_shot_generation_inputs(
        seedance_2_5_audio_only,
        verify_agent_prompt=False,
    )
)
assert seedance_2_5_audio_unrouted["input_mode"] == (
    target.INPUT_MODE_MULTIMODAL_REFERENCES
)
assert seedance_2_5_audio_unrouted["reference_audio"] == (
    seedance_2_5_audio_only["reference_audio"]
)
validation_probe._validate_parameters(seedance_2_5_audio_unrouted)

seedance_2_5_smart_duration = deepcopy(seedance_2_5_audio_only)
seedance_2_5_smart_duration["duration"] = -1
try:
    validation_probe._validate_parameters(seedance_2_5_smart_duration)
except ValueError:
    pass
else:
    raise AssertionError("Seedance 2.5 must reject smart duration (-1).")

for invalid_duration in (3, 31):
    invalid = deepcopy(seedance_2_5_audio_only)
    invalid["duration"] = invalid_duration
    assert_invalid_seedance_params(
        invalid,
        description=f"2.5 duration {invalid_duration}",
    )

seedance_2_5_nonadaptive_frames = valid_params(prompt="2.5 frame contract")
seedance_2_5_nonadaptive_frames.update(
    {
        "model_id": SEEDANCE_2_5_MODEL_ID,
        "task": TASK_FIRST_LAST_FRAME,
        "input_mode": target.INPUT_MODE_FIRST_LAST_FRAME,
        "first_frame": "https://media.example/first.png",
        "ratio": "16:9",
    }
)
assert_invalid_seedance_params(
    seedance_2_5_nonadaptive_frames,
    description="2.5 non-adaptive First/Last Frame",
)

seedance_2_5_priority = deepcopy(seedance_2_5_audio_only)
seedance_2_5_priority["priority"] = 1
assert_invalid_seedance_params(
    seedance_2_5_priority,
    description="2.5 task priority",
)

for field, values in (
    (
        "reference_images",
        [f"https://media.example/image-{index:02d}.png" for index in range(31)],
    ),
    (
        "video_references",
        [f"https://media.example/video-{index:02d}.mp4" for index in range(11)],
    ),
    (
        "reference_audio",
        [f"https://media.example/audio-{index:02d}.wav" for index in range(11)],
    ),
):
    invalid = deepcopy(seedance_2_5_audio_only)
    invalid[field] = values
    assert_invalid_seedance_params(
        invalid,
        description=f"2.5 {field} overflow",
    )

seedance_2_0_duration_overflow = valid_params(prompt="2.0 duration bound")
seedance_2_0_duration_overflow["duration"] = 16
assert_invalid_seedance_params(
    seedance_2_0_duration_overflow,
    description="2.0 duration 16",
)
for field, values in (
    (
        "reference_images",
        [f"https://media.example/legacy-image-{index:02d}.png" for index in range(10)],
    ),
    (
        "video_references",
        [f"https://media.example/legacy-video-{index:02d}.mp4" for index in range(4)],
    ),
    (
        "reference_audio",
        [f"https://media.example/legacy-audio-{index:02d}.wav" for index in range(4)],
    ),
):
    invalid = valid_params(prompt="2.0 reference bound")
    invalid["task"] = TASK_REFERENCE_TO_VIDEO
    invalid["input_mode"] = target.INPUT_MODE_MULTIMODAL_REFERENCES
    invalid[field] = values
    if field == "reference_audio":
        invalid["reference_images"] = ["https://media.example/anchor.png"]
    assert_invalid_seedance_params(
        invalid,
        description=f"2.0 {field} overflow",
    )


# Direct Shot routing remains model-agnostic: 2.5 receives the exact ordered
# Loader media and does not weaken Shot ownership/provenance while using its
# larger documented reference limits.
seedance_2_5_image_media = {
    f"image-{index:02d}": f"@image{index}"
    for index in range(1, 31)
}
seedance_2_5_video_media = {
    f"video-{index:02d}": f"@video{index}"
    for index in range(1, 11)
}
seedance_2_5_image_order = list(reversed(seedance_2_5_image_media))
seedance_2_5_video_order = list(reversed(seedance_2_5_video_media))
seedance_2_5_image_source = Source(
    "image_asset",
    snapshot(
        kind="image_asset",
        selected=seedance_2_5_image_order,
        media=seedance_2_5_image_media,
    ),
)
seedance_2_5_video_source = Source(
    "video_picker",
    snapshot(
        kind="video_picker",
        selected=seedance_2_5_video_order,
        media=seedance_2_5_video_media,
    ),
)
seedance_2_5_direct_params = valid_params(prompt="exact 2.5 Shot references")
seedance_2_5_direct_params["model_id"] = SEEDANCE_2_5_MODEL_ID
seedance_2_5_direct = generator(
    seedance_2_5_image_source,
    seedance_2_5_video_source,
)._resolve_exact_shot_generation_inputs(seedance_2_5_direct_params)
assert seedance_2_5_direct["model_id"] == SEEDANCE_2_5_MODEL_ID
assert seedance_2_5_direct["reference_images"] == [
    seedance_2_5_image_media[uid] for uid in seedance_2_5_image_order
]
assert seedance_2_5_direct["video_references"] == [
    seedance_2_5_video_media[uid] for uid in seedance_2_5_video_order
]
validation_probe._validate_parameters(seedance_2_5_direct)


# The billable payload and the bridge both use only HMB's canonical China-route
# ID.  Priority remains absent until the Broker explicitly grants it to
# 2.5; an arbitrary similarly named model must still fail closed.
seedance_2_5_payload_params = valid_params(
    prompt="edit the source in the canonical 2.5 Broker payload"
)
seedance_2_5_payload_params.update(
    {
        "model_id": SEEDANCE_2_5_MODEL_ID,
        "task": TASK_VIDEO_EDITING,
        "input_mode": target.INPUT_MODE_MULTIMODAL_REFERENCES,
        "video_references": ["https://media.example/edit-source.mp4"],
        "duration": -1,
        "resolution": target.MODEL_DEFAULT_RESOLUTIONS[SEEDANCE_2_5_MODEL_ID],
    }
)
seedance_2_5_payload = validation_probe._build_broker_payload(
    seedance_2_5_payload_params
)
assert seedance_2_5_payload["model"] == SEEDANCE_2_5_MODEL_ID
assert seedance_2_5_payload["task"] == TASK_VIDEO_EDITING
assert seedance_2_5_payload["duration_seconds"] == -1
assert seedance_2_5_payload["quality"] == "720p"
assert "priority" not in seedance_2_5_payload

# Exercise the final client-side bridge boundary, not just its field map.  The
# bridge must remove a zero-valued legacy priority, preserve the canonical
# model/provider, and fail before network I/O for forbidden values or fields.
bridge_calls: list[dict[str, Any]] = []
seedance_2_5_bridge = target._HMBAIBrokerBridge(opener=object())


def capture_bridge_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None,
    timeout: float,
    submission: bool = False,
    idempotency_key: str = "",
) -> dict[str, Any]:
    if method == "GET":
        assert path == target.BROKER_SEEDANCE_CAPABILITIES_PATH
        assert payload is None
        return {
            "schema": target.BROKER_SEEDANCE_CAPABILITIES_SCHEMA,
            "version": target.BROKER_SEEDANCE_CAPABILITIES_VERSION,
            "models": {
                SEEDANCE_2_5_MODEL_ID: {
                    "tasks": list(target.TASK_BROKER_SLUGS.values()),
                    "output_formats": ["mp4", "mov"],
                    "return_last_frame": True,
                }
            },
        }
    bridge_calls.append(
        {
            "method": method,
            "path": path,
            "payload": deepcopy(payload),
            "timeout": timeout,
            "submission": submission,
            "idempotency_key": idempotency_key,
        }
    )
    return {"id": "seedance-2-5-contract-probe"}


seedance_2_5_bridge._request_json = capture_bridge_request  # type: ignore[method-assign]
bridge_probe_payload = {**seedance_2_5_payload, "priority": 0}
assert seedance_2_5_bridge.generate_seedance(
    bridge_probe_payload,
    timeout=17.0,
) == {"id": "seedance-2-5-contract-probe"}
assert len(bridge_calls) == 1
assert bridge_calls[0]["method"] == "POST"
assert bridge_calls[0]["path"] == "/api/v1/generate/video"
assert bridge_calls[0]["submission"] is True
assert bridge_calls[0]["payload"]["provider"] == "volcengine_ark"
assert bridge_calls[0]["payload"]["model"] == SEEDANCE_2_5_MODEL_ID
assert "task" not in bridge_calls[0]["payload"]
assert bridge_calls[0]["payload"]["omni_reference_task_type"] == "edit"
assert "priority" not in bridge_calls[0]["payload"]

reference_bridge_payload = validation_probe._build_broker_payload(
    task_params(SEEDANCE_2_5_MODEL_ID, TASK_REFERENCE_TO_VIDEO)
)
assert seedance_2_5_bridge.generate_seedance(
    reference_bridge_payload,
    timeout=17.0,
) == {"id": "seedance-2-5-contract-probe"}
assert len(bridge_calls) == 2
assert bridge_calls[1]["payload"]["omni_reference_task_type"] == "reference"
assert bridge_calls[1]["payload"]["output_format"] == "mp4"
assert bridge_calls[1]["payload"]["return_last_frame"] is False
assert "task" not in bridge_calls[1]["payload"]

for forbidden_payload in (
    {**seedance_2_5_payload, "priority": 1},
    {**seedance_2_5_payload, "unapproved_field": True},
):
    calls_before = len(bridge_calls)
    try:
        seedance_2_5_bridge.generate_seedance(forbidden_payload, timeout=17.0)
    except target._BrokerProtocolError:
        pass
    else:
        raise AssertionError("Seedance 2.5 bridge accepted a forbidden payload.")
    assert len(bridge_calls) == calls_before

# The expanded 2.5 list capacity must not create new serialized scalar ports.
# Saved workflows retain exactly reference_video_1..3; larger ordered input is
# carried only by VIDEO_REFERENCES.
assert target.LEGACY_VIDEO_REFERENCE_SLOTS == 3
seedance_source = (ROOT / "HMBSeedanceGeneration.py").read_text(encoding="utf-8")
assert "for index in range(1, LEGACY_VIDEO_REFERENCE_SLOTS + 1):" in seedance_source
assert 'name=f"reference_video_{index}"' in seedance_source
assert "reference_video_4" not in seedance_source
for unsupported_model in (
    SEEDANCE_2_5_BYTEPLUS_ALIAS,
    "doubao-seedance-2-5-latest",
    "Seedance 2.5 beta",
):
    try:
        target.HMBSeedanceGeneration._validate_broker_model(unsupported_model)
    except ValueError:
        pass
    else:
        raise AssertionError(
            f"Broker accepted non-canonical Seedance model {unsupported_model!r}."
        )


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

# Only owns its manual media. The same authored dict can move through
# Only -> Shot -> Only without mutation: Shot uses only exact source snapshots
# and fixes its effective Task to Reference to Video, while returning to Only
# restores the authored Task and every manual reference in its original order.
transition = generator(image, picker)
transition_mode = {"shot": False}


def transition_subscription() -> dict[str, Any]:
    if transition_mode["shot"]:
        return {
            "enabled": True,
            "channel_uuid": CHANNEL,
            "shot_uuid": SHOT,
            "shot_number": 2,
            "shot_name": "Second Shot",
        }
    return {
        "enabled": False,
        "channel_uuid": "",
        "shot_uuid": "",
        "shot_number": 1,
        "shot_name": "Only",
    }


transition._hmb_shot_channel_subscription = transition_subscription  # type: ignore[method-assign]
transition._clear_remote_prompt_authority = lambda _reason: None  # type: ignore[method-assign]
authored_only = {
    "prompt": "manual edit survives mode changes",
    "task": TASK_VIDEO_EDITING,
    "input_mode": target.INPUT_MODE_TEXT_ONLY,
    "first_frame": None,
    "last_frame": None,
    "reference_images": ["manual-image-2", "manual-image-1"],
    "video_references": ["manual-video-2", "manual-video-1"],
    "video_reference_slots": ["manual-legacy-video"],
    "reference_audio": ["manual-audio-2", "manual-audio-1"],
}
authored_snapshot = deepcopy(authored_only)

only_before = transition._resolve_exact_shot_generation_inputs(authored_only)
assert only_before["prompt"] == authored_only["prompt"]
assert only_before["task"] == TASK_VIDEO_EDITING
assert only_before["reference_images"] == authored_only["reference_images"]
assert only_before["video_references"] == authored_only["video_references"]
assert only_before["video_reference_slots"] == authored_only["video_reference_slots"]
assert only_before["reference_audio"] == authored_only["reference_audio"]
assert only_before["input_mode"] == target.INPUT_MODE_MULTIMODAL_REFERENCES
assert authored_only == authored_snapshot

transition_mode["shot"] = True
shot_middle = transition._resolve_exact_shot_generation_inputs(authored_only)
assert shot_middle["task"] == TASK_REFERENCE_TO_VIDEO
assert shot_middle["first_frame"] is None
assert shot_middle["last_frame"] is None
assert shot_middle["reference_images"] == ["@image2", "@image1"]
assert shot_middle["video_references"] == ["@video1"]
assert shot_middle["video_reference_slots"] == []
assert shot_middle["reference_audio"] == []
assert shot_middle["input_mode"] == target.INPUT_MODE_MULTIMODAL_REFERENCES
assert authored_only == authored_snapshot

transition_mode["shot"] = False
only_after = transition._resolve_exact_shot_generation_inputs(authored_only)
assert only_after == only_before
assert authored_only == authored_snapshot

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
