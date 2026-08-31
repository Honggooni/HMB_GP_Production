from __future__ import annotations

import asyncio
import base64
import io
import importlib.util
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResultSuccess,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.context_events import (
    EnsureWorkflowAndFlowRequest,
    EnsureWorkflowAndFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
    SetParameterValueResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    DeleteWorkflowRequest,
    DeleteWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBSeedanceGeneration.py"
IMAGE_ASSET_MODULE_PATH = ROOT / "HMBImageAssetLibrary.py"
VIDEO_PICKER_MODULE_PATH = ROOT / "HMBVideoPickerLibrary.py"
VALID_MP4_BYTES = (
    b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    b"\x00\x00\x00\x10moov\x00\x00\x00\x08mvhd"
    b"\x00\x00\x00\x10mdat12345678"
)
VALID_MOV_BYTES = (
    b"\x00\x00\x00\x18ftypqt  \x00\x00\x00\x00qt  isom"
    b"\x00\x00\x00\x10moov\x00\x00\x00\x08mvhd"
    b"\x00\x00\x00\x10mdat12345678"
)
VALID_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)


def accept_structural_regression_mp4(path: Path, _verifier=None) -> None:
    """Keep generator tests focused on publication; decode QA has its own suite."""
    content = Path(path).read_bytes()
    assert content in {VALID_MP4_BYTES, VALID_MOV_BYTES}
    assert target._is_structurally_valid_mp4(content)


def load_target():
    spec = importlib.util.spec_from_file_location(
        "hmb_seedance_volcengine_regression_target", MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load HMB Seedance regression target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_image_asset_target():
    spec = importlib.util.spec_from_file_location(
        "hmb_image_asset_seedance_contract_target", IMAGE_ASSET_MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load HMB Image Asset contract target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_video_picker_target():
    spec = importlib.util.spec_from_file_location(
        "hmb_video_picker_seedance_contract_target", VIDEO_PICKER_MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load HMB Video Picker contract target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


target = load_target()
# The dedicated five-Shot concurrency regression validates the production
# 1.05-second create cadence. Keep this broad generator suite deterministic and
# fast while it exercises cancellation after a Broker POST has actually begun.
target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
image_asset_target = load_image_asset_target()
video_picker_target = load_video_picker_target()


class FakeDestination:
    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.location = str(
            Path(self._temporary.name) / "volcengine-regression.mp4"
        )
        self.resolved = False
        self.written: bytes | None = None

    def resolve(self) -> str:
        self.resolved = True
        return self.location

    async def awrite_bytes(self, content: bytes):
        raise AssertionError("Completed MP4 bypassed atomic sibling publication")


class FakeOutputFile:
    def __init__(self, destination: FakeDestination) -> None:
        self.destination = destination

    def build_file(self) -> FakeDestination:
        return self.destination




class FakeBrokerBridge:
    SECRET_VALUES = (
        "broker-access-token-canary",
        "provider-api-key-canary",
        "authorization-canary",
    )

    def __init__(self, refresh_responses: list[dict]) -> None:
        self.refresh_responses = list(refresh_responses)
        self.account_calls = 0
        self.generate_payloads: list[dict] = []
        self.refresh_ids: list[str] = []

    def account_snapshot(self, *, connect: bool):
        assert connect is True
        self.account_calls += 1
        return target._BrokerAccountSnapshot(
            state="connected",
            connected=True,
            account="Broker Artist",
        )

    def generate_seedance(self, payload: dict, *, timeout: float) -> dict:
        assert timeout > 0
        self.generate_payloads.append(dict(payload))
        return {
            "status": "pending",
            "job_id": "broker-job-1",
            "token": self.SECRET_VALUES[0],
            "api_key": self.SECRET_VALUES[1],
            "authorization": self.SECRET_VALUES[2],
            "nested": {"credential": self.SECRET_VALUES[1]},
        }

    def refresh_job(self, job_id: str, *, timeout: float = 60) -> dict:
        assert timeout > 0
        self.refresh_ids.append(job_id)
        if not self.refresh_responses:
            raise AssertionError("Unexpected extra Broker refresh")
        return self.refresh_responses.pop(0)

    @staticmethod
    def is_trusted_broker_url(_url: str) -> bool:
        return False


class RuntimeRegisteredSeedance(target.HMBSeedanceGeneration):
    """Exercise live-node paths without weakening production liveness guards."""

    def _runtime_node_is_live(self, *, require_registered: bool = False) -> bool:
        del require_registered
        return True

    async def _force_save_generation_recovery_checkpoint(
        self,
        *,
        required: bool,
        reason: str,
    ) -> bool:
        # Synthetic nodes in this suite deliberately run without a retained
        # workflow. The dedicated crash/reopen suite verifies the fail-closed
        # save boundary; these cases isolate Broker/media behavior.
        del required, reason
        return True


class BrokerScriptedNode(RuntimeRegisteredSeedance):
    def __init__(self, bridge: FakeBrokerBridge) -> None:
        super().__init__(name="HMB Seedance Broker Scripted Regression")
        self.set_parameter_value(target.TASK_PARAMETER, target.TASK_TEXT_ONLY)
        self.bridge = bridge
        self.destination = FakeDestination()
        self._output_file = FakeOutputFile(self.destination)
        self.downloads: list[str] = []
        self.sleeps: list[float] = []

    def _create_broker_bridge(self):
        return self.bridge

    def _resolve_exact_shot_generation_inputs(
        self,
        params: dict,
        *,
        verify_agent_prompt: bool = True,
    ) -> dict:
        # These cases isolate Broker/upload mechanics. Direct Shot provenance is
        # covered by the dedicated routing regression and must not erase the
        # synthetic references used here.
        del verify_agent_prompt
        return dict(params)

    async def _download_video(self, url: str) -> bytes:
        self.downloads.append(url)
        return VALID_MP4_BYTES

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def _monotonic(self) -> float:
        return 0.0


def assert_constructor_and_public_contract() -> None:
    with mock.patch.object(
        target.GriptapeNodes,
        "SecretsManager",
        side_effect=AssertionError("constructor read a secret"),
    ), mock.patch.object(
        target._HMBAIBrokerBridge,
        "_request_json",
        side_effect=AssertionError("constructor performed a Broker request"),
    ), mock.patch.object(
        target.urllib.request,
        "urlopen",
        side_effect=AssertionError("constructor performed a network request"),
    ):
        node = target.HMBSeedanceGeneration(name="Constructor Regression")

    assert target.HMBSeedanceGeneration.__mro__[1].__name__ == "SuccessFailureNode"
    names = [parameter.name for parameter in node.parameters]
    for required in (
        "exec_in",
        "exec_out",
        "failure",
        "model_id",
        "task",
        "input_mode",
        "prompt",
        "first_frame",
        "last_frame",
        "reference_images",
        "reference_video_1",
        "reference_video_2",
        "reference_video_3",
        "VIDEO_REFERENCES",
        "reference_audio",
        "auto_publish_local_videos",
        "local_video_upload_service",
        "tos_region",
        "tos_endpoint",
        "tos_url_validity_seconds",
        "resolution",
        "ratio",
        "duration",
        "generate_audio",
        "generation_id",
        "generation_status",
        "generation_refresh",
        "broker_connection_status",
        "broker_account",
        "broker_connect_refresh",
        "broker_notice",
        "provider_response",
        "video_url",
        "VIDEO_OUT",
        "output_file",
        "was_successful",
        "result_details",
    ):
        assert required in names, required
    assert names.count("VIDEO_REFERENCES") == 1
    assert names.count("reference_images") == 1
    assert names.count("reference_video_1") == 1
    assert names.count("reference_video_2") == 1
    assert names.count("reference_video_3") == 1
    assert "reference_video_4" not in names
    assert len(names) == len(set(names))
    assert names.index("reference_images") < names.index("reference_video_1")
    assert names.index("reference_video_1") < names.index("reference_video_2")
    assert names.index("reference_video_2") < names.index("reference_video_3")
    assert names.index("reference_video_3") < names.index("VIDEO_REFERENCES")
    assert names.index("VIDEO_REFERENCES") < names.index("reference_audio")
    assert target.MAX_REFERENCE_IMAGES == 30
    assert target.MAX_VIDEO_REFERENCES == 10
    assert target.MAX_REFERENCE_AUDIO == 10
    assert target.LEGACY_VIDEO_REFERENCE_SLOTS == 3
    assert target.MODEL_REFERENCE_LIMITS == {
        target.SEEDANCE_2_0_MODEL_ID: (9, 3, 3),
        target.SEEDANCE_2_0_FAST_MODEL_ID: (9, 3, 3),
        target.SEEDANCE_2_5_MODEL_ID: (30, 10, 10),
    }
    assert target.AI_BROKER_SERVER_URL == "http://192.168.203.245:8080"
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_0_MODEL_ID] == (
        "4k",
        "1080p",
        "720p",
        "480p",
    )
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_0_FAST_MODEL_ID] == (
        "720p",
        "480p",
    )
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_5_MODEL_ID] == (
        "720p",
        "1080p",
    )
    assert target.MODEL_DEFAULT_RESOLUTIONS == {
        target.SEEDANCE_2_0_MODEL_ID: "1080p",
        target.SEEDANCE_2_0_FAST_MODEL_ID: "720p",
        target.SEEDANCE_2_5_MODEL_ID: "720p",
    }
    assert target.MODEL_DURATION_CHOICES == {
        target.SEEDANCE_2_0_MODEL_ID: (-1, *range(4, 16)),
        target.SEEDANCE_2_0_FAST_MODEL_ID: (-1, *range(4, 16)),
        target.SEEDANCE_2_5_MODEL_ID: (*range(4, 31),),
    }
    assert target.TASK_STORAGE_CHOICES == (
        "Text Only",
        "First/Last Frame",
        "Reference to Video",
        "Video Editing",
        "Video Extension",
    )
    assert target.MODEL_TASK_CHOICES == {
        target.SEEDANCE_2_0_MODEL_ID: target.TASK_STORAGE_CHOICES[:3],
        target.SEEDANCE_2_0_FAST_MODEL_ID: target.TASK_STORAGE_CHOICES[:3],
        target.SEEDANCE_2_5_MODEL_ID: target.TASK_STORAGE_CHOICES,
    }

    image_parameter = node.get_parameter_by_name("reference_images")
    assert type(image_parameter).__name__ == "ParameterList"
    assert isinstance(image_parameter, target.ParameterList)
    assert image_parameter.type == "list[ImageUrlArtifact]"
    assert image_parameter.input_types == [
        "list[str]",
        "list[ImageUrlArtifact]",
        "list[ImageArtifact]",
        "list[BytePlusImageAssetReference]",
        "list",
    ]
    assert image_parameter.output_type == "list[str]"
    assert image_parameter.is_incoming_type_allowed("list[str]") is True
    assert image_parameter._max_items == target.MAX_REFERENCE_IMAGES
    assert image_parameter.ui_options["display_name"] == "Reference Images"
    assert "expander" not in image_parameter.ui_options
    assert image_parameter.hide_property is True
    assert image_parameter.hide is False
    assert image_parameter.ui_options.get("hide_handles", False) is False
    assert image_parameter.ui_options.get("hide_label", False) is False
    assert image_parameter.allowed_modes == {target.ParameterMode.INPUT}
    image_child = image_parameter.append_child_parameter()
    assert image_child.type == "ImageUrlArtifact"
    assert image_child.input_types == [
        "str",
        "ImageUrlArtifact",
        "ImageArtifact",
        "BytePlusImageAssetReference",
    ]
    assert image_child.output_type == "str"
    image_parameter.clear_list()

    # The Asset Library source and Seedance target advertise an exact list[str]
    # match, so the complete ordered selection uses one graph connection.
    asset_contract_node = image_asset_target.DataNode(name="Image Asset Port Contract")
    image_asset_target._add_media_output(asset_contract_node)
    asset_media_output = asset_contract_node.get_parameter_by_name(
        image_asset_target.MEDIA_OUTPUT_PARAMETER
    )
    assert asset_media_output.output_type == "list[str]"
    assert asset_media_output.output_type in image_parameter.input_types

    for index in range(1, target.LEGACY_VIDEO_REFERENCE_SLOTS + 1):
        parameter = node.get_parameter_by_name(f"reference_video_{index}")
        assert parameter.type == "VideoUrlArtifact"
        assert parameter.input_types == [
            "VideoUrlArtifact",
            "BytePlusVideoAssetReference",
        ]
        assert parameter.allowed_modes == {target.ParameterMode.INPUT}
        assert parameter.hide_property is True
        assert parameter.ui_options["display_name"] == f"Legacy Reference Video {index}"
        assert parameter.hide is True

    video_list_parameter = node.get_parameter_by_name("VIDEO_REFERENCES")
    assert video_list_parameter.type == "list[VideoUrlArtifact]"
    assert video_list_parameter.hide is False
    assert video_list_parameter.ui_options["display_name"] == "Reference Videos"
    assert video_list_parameter.ui_options.get("hide_handles", False) is False
    assert video_list_parameter.ui_options.get("hide_label", False) is False
    assert video_list_parameter.allowed_modes == {target.ParameterMode.INPUT}
    assert video_list_parameter.hide_property is True
    assert video_list_parameter.input_types == [
        "list[str]",
        "list[VideoUrlArtifact]",
        "list[BytePlusVideoAssetReference]",
        "list",
    ]
    assert type(video_list_parameter).__name__ == "ParameterList"
    assert video_list_parameter.output_type == "list[str]"
    assert video_list_parameter.is_incoming_type_allowed("list[str]") is True
    assert video_list_parameter._max_items == target.MAX_VIDEO_REFERENCES
    video_child = video_list_parameter.append_child_parameter()
    assert video_child.type == "VideoUrlArtifact"
    assert video_child.input_types == [
        "str",
        "VideoUrlArtifact",
        "BytePlusVideoAssetReference",
    ]
    assert video_child.output_type == "str"
    video_list_parameter.clear_list()

    # Picker and Seedance advertise an exact list[str] match, so all selected
    # videos travel over one wire without re-numbering scalar ports.
    picker_contract_node = video_picker_target.HMBVideoPickerLibrary(
        name="Video Picker Port Contract"
    )
    picker_video_output = picker_contract_node.get_parameter_by_name(
        video_picker_target.VIDEO_OUTPUT_PARAMETER
    )
    assert picker_video_output.output_type == "list[str]"
    assert picker_video_output.output_type in video_list_parameter.input_types

    audio_parameter = node.get_parameter_by_name("reference_audio")
    assert type(audio_parameter).__name__ == "ParameterList"
    assert audio_parameter.type == "list[AudioArtifact]"
    assert audio_parameter.input_types == [
        "list[AudioArtifact]",
        "list[AudioUrlArtifact]",
        "list[str]",
        "list[BytePlusAudioAssetReference]",
        "list",
    ]
    assert audio_parameter.is_incoming_type_allowed("list[str]") is True
    assert audio_parameter._max_items == target.MAX_REFERENCE_AUDIO
    assert audio_parameter.hide is False
    assert audio_parameter.ui_options["display_name"] == "Reference Audio"
    assert audio_parameter.ui_options.get("hide_handles", False) is False
    assert audio_parameter.ui_options.get("hide_label", False) is False
    audio_child = audio_parameter.append_child_parameter()
    assert audio_child.type == "AudioArtifact"
    assert audio_child.input_types == [
        "AudioArtifact",
        "AudioUrlArtifact",
        "str",
        "BytePlusAudioAssetReference",
    ]
    assert audio_child.output_type == "AudioArtifact"
    audio_parameter.clear_list()
    assert node.get_parameter_value("auto_publish_local_videos") is True
    assert (
        node.get_parameter_value("local_video_upload_service")
        == target.LOCAL_VIDEO_UPLOAD_GRIPTAPE
    )
    assert node.get_parameter_value("tos_region") == "cn-beijing"
    assert node.get_parameter_value("tos_endpoint") == "tos-cn-beijing.volces.com"
    assert node.get_parameter_value("tos_url_validity_seconds") == 86400
    assert node.get_parameter_by_name("tos_region").hide is True
    assert node.get_parameter_value("model_id") == target.MODEL_NAME_SEEDANCE_2_0
    assert node.get_parameter_by_name("model_id").ui_options["simple_dropdown"] == [
        target.MODEL_NAME_SEEDANCE_2_0,
        target.MODEL_NAME_SEEDANCE_2_0_FAST,
        target.MODEL_NAME_SEEDANCE_2_5,
    ]
    task_parameter = node.get_parameter_by_name("task")
    assert task_parameter is not None
    assert task_parameter.hide is True
    assert task_parameter.hide_property is True
    assert task_parameter.ui_options["display_name"] == ""
    assert node.get_parameter_value("task") == target.TASK_REFERENCE_TO_VIDEO
    assert task_parameter.ui_options["simple_dropdown"] == list(
        target.TASK_STORAGE_CHOICES[:3]
    )
    input_mode_parameter = node.get_parameter_by_name("input_mode")
    assert input_mode_parameter is not None
    assert (
        node.get_parameter_value("input_mode")
        == target.INPUT_MODE_MULTIMODAL_REFERENCES
    )
    assert input_mode_parameter.hide is False
    assert input_mode_parameter.hide_property is False
    assert input_mode_parameter.hide_label is False
    assert input_mode_parameter.ui_options["display_name"] == "Input Mode"
    assert input_mode_parameter.ui_options.get("hide_handles", False) is True
    assert input_mode_parameter.ui_options["simple_dropdown"] == [
        target.INPUT_MODE_TEXT_ONLY,
        target.INPUT_MODE_FIRST_LAST_FRAME,
        target.INPUT_MODE_MULTIMODAL_REFERENCES,
    ]
    # 2.0 authors the stock Input Mode while the hidden task mirror keeps
    # validation and a later 2.5 switch semantically lossless.
    node.set_parameter_value("input_mode", target.INPUT_MODE_TEXT_ONLY)
    assert node.get_parameter_value("task") == target.TASK_TEXT_ONLY
    assert image_parameter.hide is True
    assert video_list_parameter.hide is True
    assert audio_parameter.hide is True
    node.set_parameter_value(
        "input_mode", target.INPUT_MODE_MULTIMODAL_REFERENCES
    )
    assert node.get_parameter_value("task") == target.TASK_REFERENCE_TO_VIDEO
    assert image_parameter.hide is False
    assert video_list_parameter.hide is False
    assert audio_parameter.hide is False
    assert node.get_parameter_value("generate_audio") is False
    assert node.get_parameter_value("resolution") == "1080p"
    assert node.get_parameter_by_name("resolution").ui_options["simple_dropdown"] == [
        "4k",
        "1080p",
        "720p",
        "480p",
    ]
    assert node.get_parameter_value("ratio") == "adaptive"
    assert node.get_parameter_by_name("ratio").ui_options["simple_dropdown"] == list(
        target.RATIOS
    )
    assert node.get_parameter_value("duration") == 5
    assert node.get_parameter_by_name("duration").ui_options["simple_dropdown"] == [
        -1,
        *range(4, 16),
    ]
    assert node.get_parameter_value("resume_generation_id") == ""
    assert node.get_parameter_value("watermark") is False
    assert node.get_parameter_value("return_last_frame") is False
    assert node.get_parameter_value("execution_expires_after") == 172800
    assert node.get_parameter_value("priority") == 0
    assert node.get_parameter_value("poll_interval_seconds") == 30
    assert node.get_parameter_value("generation_timeout_seconds") == 3600
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_0_FAST)
    assert node._get_parameters()["model_id"] == target.SEEDANCE_2_0_FAST_MODEL_ID
    assert node.get_parameter_value("resolution") == "720p"
    assert node.get_parameter_by_name("resolution").ui_options["simple_dropdown"] == [
        "720p",
        "480p",
    ]
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_5)
    assert node._get_parameters()["model_id"] == target.SEEDANCE_2_5_MODEL_ID
    assert task_parameter.hide is False
    assert task_parameter.hide_property is False
    assert task_parameter.ui_options["display_name"] == "Task"
    assert input_mode_parameter.hide is True
    assert input_mode_parameter.hide_property is True
    assert input_mode_parameter.ui_options["display_name"] == ""
    assert node.get_parameter_value("resolution") == "720p"
    assert node.get_parameter_by_name("resolution").ui_options["simple_dropdown"] == [
        "720p",
        "1080p",
    ]
    assert node.get_parameter_by_name("duration").ui_options["simple_dropdown"] == [
        *range(4, 31),
    ]
    assert task_parameter.ui_options["simple_dropdown"] == list(
        target.TASK_STORAGE_CHOICES
    )
    node.set_parameter_value("task", target.TASK_VIDEO_EDITING)
    assert node.get_parameter_value("task") == target.TASK_VIDEO_EDITING
    assert (
        node.get_parameter_value("input_mode")
        == target.INPUT_MODE_MULTIMODAL_REFERENCES
    )
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_0)
    assert node.get_parameter_value("task") == target.TASK_REFERENCE_TO_VIDEO
    assert task_parameter.hide is True
    assert input_mode_parameter.hide is False
    assert input_mode_parameter.ui_options["display_name"] == "Input Mode"
    assert task_parameter.ui_options["simple_dropdown"] == list(
        target.TASK_STORAGE_CHOICES[:3]
    )
    saved_audio_node = target.HMBSeedanceGeneration(
        name="Saved Generate Audio Regression"
    )
    saved_audio_node.set_parameter_value("generate_audio", True, initial_setup=True)
    assert saved_audio_node.get_parameter_value("generate_audio") is True
    assert saved_audio_node._get_parameters()["generate_audio"] is True
    node.set_parameter_value("local_video_upload_service", target.LOCAL_VIDEO_UPLOAD_TOS)
    assert node.get_parameter_by_name("tos_region").hide is False
    node.set_parameter_value(
        "local_video_upload_service", target.LOCAL_VIDEO_UPLOAD_GRIPTAPE
    )

    video_parameter = node.get_parameter_by_name("video_url")
    assert video_parameter.allowed_modes == {target.ParameterMode.PROPERTY}
    video_alias = node.get_parameter_by_name("VIDEO_OUT")
    assert type(video_alias).__name__ == "Parameter"
    assert video_alias.type == "VideoUrlArtifact"
    assert video_alias.allowed_modes == {target.ParameterMode.OUTPUT}
    assert video_alias.hide_property is True
    assert video_alias.ui_options["display_name"] == "video_url"
    assert [
        parameter.name
        for parameter in (video_parameter, video_alias)
        if target.ParameterMode.OUTPUT in parameter.allowed_modes
    ] == ["VIDEO_OUT"]
    refresh_parameter = node.get_parameter_by_name("generation_refresh")
    assert type(refresh_parameter).__name__ == "ParameterButton"
    assert refresh_parameter.label == "Refresh / Retrieve Result"
    assert refresh_parameter.state == "hidden"
    assert refresh_parameter.hide is True
    assert refresh_parameter.hide_property is True
    assert refresh_parameter.serializable is False
    shot_widget_parameter = node.get_parameter_by_name(
        target.SEEDANCE_SHOT_WIDGET_PARAMETER
    )
    assert shot_widget_parameter is not None
    assert shot_widget_parameter.serializable is False
    assert node.get_parameter_value(target.SEEDANCE_SHOT_WIDGET_PARAMETER)[
        "generation"
    ]["schema"] == target.GENERATION_PREVIEW_SCHEMA

    root_children = list(node.root_ui_element.children)
    root_names = [element.name for element in root_children]
    assert root_names[-3:] == [
        "Status",
        "AI Broker",
        target.SEEDANCE_RECOVERY_PARAMETER,
    ]
    assert [
        element.name
        for element in root_children
        if not bool(getattr(element, "hide", False))
    ][-2:] == ["Status", "AI Broker"]
    recovery_parameter = root_children[-1]
    assert recovery_parameter.settable is False
    assert recovery_parameter.serializable is True
    assert recovery_parameter.hide is True
    assert recovery_parameter.hide_property is True
    broker_group = root_children[-2]
    assert type(broker_group).__name__ == "ParameterGroup"
    assert broker_group.ui_options == {"collapsed": True}
    assert [child.name for child in broker_group.children] == [
        "broker_connection_status",
        "broker_account",
        "broker_connect_refresh",
        "broker_notice",
    ]
    assert not any(
        text in child.name.lower()
        for child in broker_group.children
        for text in ("api_key", "token", "usage", "quota", "credit", "register")
    )
    for name in ("broker_connection_status", "broker_account", "broker_notice"):
        parameter = node.get_parameter_by_name(name)
        assert parameter.allowed_modes == {target.ParameterMode.PROPERTY}
        assert parameter.settable is False
        assert parameter.serializable is False
    assert node.get_parameter_by_name("broker_connect_refresh").label == (
        "Connect / Refresh"
    )

    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden_symbol in (
        "ARK" + "_API_KEY",
        "ARK" + "_BASE_URL",
        "CREATE" + "_TASK_PATH",
        "Volcengine" + "APIError",
        "_process_" + "direct",
        "_refresh_" + "direct",
        "USAGE" + "_LEDGER_ROOT",
        "Griptape_" + "list",
    ):
        assert forbidden_symbol not in source
    assert not {
        name
        for name in dir(target.HMBSeedanceGeneration)
        if "usage" in name.casefold()
    }
    assert "_BaseSeedance" not in source
    assert "GriptapeProxyNode" not in source
    assert "ProxyAuthProviderParameter" not in source
    assert "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH" not in source
    assert "from fn_ai_auth_v2" not in source
    assert "import fn_ai_auth_v2" not in source
    assert "from _hmb_broker_bridge" not in source
    assert "import _hmb_broker_bridge" not in source
    assert "def _list_parameter(" not in source
    assert "PublicArtifactUrlParameter" not in source
    assert "GriptapeCloudStorageDriver" in source
    assert 'importlib.import_module("tos")' in source
    assert (
        "Options(choices=list(MODEL_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID]))"
        in source
    )


def assert_seedance_25_output_format_and_last_frame_ui_contract() -> None:
    """Freeze the stock 2.5 surface without leaking it into either 2.0 model."""

    assert list(target.OUTPUT_FORMAT_CHOICES) == ["mp4", "mov"]
    assert target.DEFAULT_OUTPUT_FORMAT == "mp4"

    node = target.HMBSeedanceGeneration(name="Seedance 2.5 Format UI Regression")
    names = [parameter.name for parameter in node.parameters]
    for required in (
        "output_format",
        "return_last_frame",
        "last_frame_url",
        "last_frame_file",
    ):
        assert required in names, required

    output_format = node.get_parameter_by_name("output_format")
    assert type(output_format).__name__ == "ParameterString"
    assert node.get_parameter_value("output_format") == "mp4"
    choices = output_format.ui_options.get("simple_dropdown")
    if choices is None:
        option_traits = output_format.find_elements_by_type(target.Options)
        assert len(option_traits) == 1
        choices = option_traits[0].choices
    assert list(choices) == ["mp4", "mov"]

    return_last_frame = node.get_parameter_by_name("return_last_frame")
    last_frame_output = node.get_parameter_by_name("last_frame_url")
    last_frame_file = node.get_parameter_by_name("last_frame_file")
    assert type(last_frame_output).__name__ == "ParameterImage"
    assert last_frame_output.output_type == "ImageUrlArtifact"
    assert last_frame_output.allowed_modes == {target.ParameterMode.OUTPUT}
    assert last_frame_output.hide_property is False
    assert last_frame_output.ui_options["display_name"] == "Last Frame Image"

    prior_video = target.VideoUrlArtifact(
        value="C:/project/prior-video.mp4",
        name="prior-video.mp4",
    )
    prior_frame = target.ImageUrlArtifact(
        value="C:/project/prior-last-frame.png",
        name="prior-last-frame.png",
    )
    node.parameter_output_values["video_url"] = prior_video
    node.parameter_output_values["last_frame_url"] = prior_frame
    node._set_safe_defaults()
    assert node.parameter_output_values["video_url"] is prior_video
    assert node.parameter_output_values["last_frame_url"] is prior_frame

    # The unified HMB node defaults to 2.0. Both 2.5-only controls and their
    # optional output must therefore start hidden, not merely ignored later.
    assert node.get_parameter_value("model_id") == target.MODEL_NAME_SEEDANCE_2_0
    assert output_format.hide is True
    assert return_last_frame.hide is True
    assert last_frame_output.hide is True
    assert last_frame_file.hide is True

    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_5)
    node.set_parameter_value(target.TASK_PARAMETER, target.TASK_TEXT_ONLY)
    assert output_format.hide is False
    assert return_last_frame.hide is False
    assert node.get_parameter_value("output_format") == "mp4"
    assert str(node.get_parameter_value("output_file")).lower().endswith(".mp4")

    # Serialized output controls are independent fields. Both replay orders
    # must retain the 2.5 MOV/frame choices, while a stale 2.0 replay must
    # deterministically return to the stock MP4/no-frame contract.
    for hydration_order in (
        (
            ("model_id", target.MODEL_NAME_SEEDANCE_2_5),
            ("output_format", "mov"),
            ("return_last_frame", True),
        ),
        (
            ("output_format", "mov"),
            ("return_last_frame", True),
            ("model_id", target.MODEL_NAME_SEEDANCE_2_5),
        ),
    ):
        hydrated = target.HMBSeedanceGeneration(
            name="Seedance 2.5 Output Hydration Regression"
        )
        for parameter_name, saved_value in hydration_order:
            hydrated.set_parameter_value(
                parameter_name,
                saved_value,
                initial_setup=True,
                emit_change=False,
            )
        hydrated._synchronize_model_output_contract()
        assert hydrated.get_parameter_value("model_id") == (
            target.MODEL_NAME_SEEDANCE_2_5
        )
        assert hydrated.get_parameter_value("output_format") == "mov"
        assert hydrated.get_parameter_value("return_last_frame") is True

    for hydration_order in (
        (
            ("model_id", target.MODEL_NAME_SEEDANCE_2_0),
            ("output_format", "mov"),
            ("return_last_frame", True),
        ),
        (
            ("output_format", "mov"),
            ("return_last_frame", True),
            ("model_id", target.MODEL_NAME_SEEDANCE_2_0),
        ),
    ):
        hydrated = target.HMBSeedanceGeneration(
            name="Seedance 2.0 Output Hydration Regression"
        )
        for parameter_name, saved_value in hydration_order:
            hydrated.set_parameter_value(
                parameter_name,
                saved_value,
                initial_setup=True,
                emit_change=False,
            )
        hydrated._synchronize_model_output_contract()
        assert hydrated.get_parameter_value("output_format") == "mp4"
        assert hydrated.get_parameter_value("return_last_frame") is False

    node.set_parameter_value("output_format", "mov")
    assert node.get_parameter_value("output_format") == "mov"
    assert str(node.get_parameter_value("output_file")).lower().endswith(".mov")
    node.set_parameter_value("return_last_frame", True)
    assert last_frame_output.hide is False
    assert last_frame_file.hide is False

    params = node._get_parameters()
    params["prompt"] = "2.5 MOV and durable last frame"
    payload = node._build_broker_payload(params)
    assert payload["output_format"] == "mov"
    assert payload["return_last_frame"] is True

    # Browser or saved-workflow values may outlive a model switch. They must
    # never make either 2.0 request differ from the stock 2.0 contract.
    for legacy_name, legacy_id in (
        (target.MODEL_NAME_SEEDANCE_2_0, target.SEEDANCE_2_0_MODEL_ID),
        (target.MODEL_NAME_SEEDANCE_2_0_FAST, target.SEEDANCE_2_0_FAST_MODEL_ID),
    ):
        node.set_parameter_value("model_id", legacy_name)
        assert output_format.hide is True
        assert return_last_frame.hide is True
        legacy = node._get_parameters()
        legacy.update(
            {
                "model_id": legacy_id,
                "prompt": "legacy request with stale 2.5-only values",
                "output_format": "mov",
                "return_last_frame": True,
            }
        )
        legacy_payload = node._build_broker_payload(legacy)
        assert "output_format" not in legacy_payload
        assert "return_last_frame" not in legacy_payload

    # The bridge is the last client-side trust boundary. Even if a caller
    # bypasses the node and supplies stale fields directly, its final POST body
    # must contain zero 2.5-only fields for both 2.0 variants.
    posted: list[dict] = []
    bridge = target._HMBAIBrokerBridge(opener=object())

    def capture_request(method, path, *, payload, timeout, **kwargs):
        if method == "GET":
            assert path == target.BROKER_SEEDANCE_CAPABILITIES_PATH
            assert payload is None
            assert timeout > 0
            return {
                "schema": target.BROKER_SEEDANCE_CAPABILITIES_SCHEMA,
                "version": target.BROKER_SEEDANCE_CAPABILITIES_VERSION,
                "models": {
                    target.SEEDANCE_2_5_MODEL_ID: {
                        "tasks": list(target.TASK_BROKER_SLUGS.values()),
                        "output_formats": ["mp4", "mov"],
                        "return_last_frame": True,
                    }
                },
            }
        assert method == "POST"
        assert path == "/api/v1/generate/video"
        assert timeout > 0
        del kwargs
        posted.append(dict(payload))
        return {"status": "pending", "job_id": "format-contract-job"}

    bridge._request_json = capture_request
    for model_id in (
        target.SEEDANCE_2_0_MODEL_ID,
        target.SEEDANCE_2_0_FAST_MODEL_ID,
    ):
        bridge.generate_seedance(
            {
                "provider": "volcengine_ark",
                "model": model_id,
                "prompt": "stale format fields",
                "output_format": "mov",
                "return_last_frame": True,
            },
            timeout=1,
        )
        assert "output_format" not in posted[-1]
        assert "return_last_frame" not in posted[-1]

    bridge.generate_seedance(
        {
            "provider": "volcengine_ark",
            "model": target.SEEDANCE_2_5_MODEL_ID,
            "prompt": "active format fields",
            "output_format": "mov",
            "return_last_frame": True,
        },
        timeout=1,
    )
    assert posted[-1]["output_format"] == "mov"
    assert posted[-1]["return_last_frame"] is True
    assert "task" not in posted[-1]
    assert posted[-1]["omni_reference_task_type"] == "reference"

    # Ordinary 2.5 Reference-to-Video is also an explicit provider subtask;
    # MP4/no-last-frame must not fall back to the generic 2.0 multimodal wire.
    bridge.generate_seedance(
        {
            "provider": "volcengine_ark",
            "model": target.SEEDANCE_2_5_MODEL_ID,
            "prompt": "use the supplied image as the subject reference",
            "task": target.TASK_REFERENCE_TO_VIDEO,
            "input_mode": target.INPUT_MODE_MULTIMODAL_REFERENCES,
            "image_urls": ["https://media.example/reference.png"],
            "output_format": "mp4",
            "return_last_frame": False,
        },
        timeout=1,
    )
    assert posted[-1]["omni_reference_task_type"] == "reference"
    assert posted[-1]["output_format"] == "mp4"
    assert posted[-1]["return_last_frame"] is False
    assert "task" not in posted[-1]

    # An older Broker has no capability endpoint. Advanced controls must stop
    # on the authenticated GET boundary without reaching the create-task POST.
    unsupported_calls: list[tuple[str, str]] = []
    unsupported_bridge = target._HMBAIBrokerBridge(opener=object())

    def reject_capability(method, path, *, payload, timeout, **kwargs):
        del payload, timeout, kwargs
        unsupported_calls.append((method, path))
        if method == "POST":
            raise AssertionError("Advanced Seedance reached a billable POST")
        raise target._BrokerProtocolError("capability endpoint unavailable")

    unsupported_bridge._request_json = reject_capability
    try:
        unsupported_bridge.generate_seedance(
            {
                "provider": "volcengine_ark",
                "model": target.SEEDANCE_2_5_MODEL_ID,
                "prompt": "extend the supplied video forward",
                "task": target.TASK_VIDEO_EXTENSION,
                "output_format": "mov",
                "return_last_frame": True,
            },
            timeout=1,
        )
    except target._BrokerProtocolError as exc:
        assert "No media was uploaded" in str(exc)
    else:
        raise AssertionError("Missing Broker capabilities were accepted")
    assert unsupported_calls == [
        ("GET", target.BROKER_SEEDANCE_CAPABILITIES_PATH)
    ]

    before_invalid = len(posted)
    try:
        bridge.generate_seedance(
            {
                "provider": "volcengine_ark",
                "model": target.SEEDANCE_2_5_MODEL_ID,
                "prompt": "invalid container must fail before POST",
                "output_format": "avi",
                "return_last_frame": False,
            },
            timeout=1,
        )
    except (ValueError, target._BrokerProtocolError):
        pass
    else:
        raise AssertionError("An unsupported output format reached the Broker")
    assert len(posted) == before_invalid


def assert_only_shot_task_and_reference_state_contract() -> None:
    """Only owns authored refs; Shot only changes their visibility/authority."""

    node = target.HMBSeedanceGeneration(name="Only Shot Reference State Regression")
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_5)
    node.set_parameter_value("task", target.TASK_VIDEO_EDITING)
    manual_images = [
        "https://cdn.example/manual-image-02.png",
        "https://cdn.example/manual-image-01.png",
    ]
    manual_videos = [
        "https://cdn.example/manual-video-02.mp4",
        "https://cdn.example/manual-video-01.mp4",
    ]
    manual_audio = [
        "https://cdn.example/manual-audio-02.wav",
        "https://cdn.example/manual-audio-01.wav",
    ]
    node.set_parameter_value("reference_images", manual_images)
    node.set_parameter_value(target.VIDEO_REFERENCES_PARAMETER, manual_videos)
    audio_parameter = node.get_parameter_by_name("reference_audio")
    for value in manual_audio:
        child = audio_parameter.append_child_parameter()
        node.set_parameter_value(child.name, value)

    def assert_manual_reference_visibility(visible: bool) -> None:
        for parameter_name in (
            "reference_images",
            target.VIDEO_REFERENCES_PARAMETER,
            "reference_audio",
        ):
            parameter = node.get_parameter_by_name(parameter_name)
            assert parameter.hide is (not visible), parameter_name
            assert parameter.ui_options.get("hide_handles", False) is (
                not visible
            ), parameter_name
            assert parameter.ui_options.get("hide_label", False) is (
                not visible
            ), parameter_name

    node._update_parameter_visibility()
    assert_manual_reference_visibility(True)
    assert node.get_parameter_by_name(target.TASK_PARAMETER).hide is False
    assert node.get_parameter_value("task") == target.TASK_VIDEO_EDITING
    assert node.get_parameter_value("reference_images") == manual_images
    assert node.get_parameter_value(target.VIDEO_REFERENCES_PARAMETER) == manual_videos
    assert node._get_list_input("reference_audio") == manual_audio

    # Hidden Shot identity values are hydrated independently of the custom
    # widget. Entering Shot must hide, never clear, the authored Only values.
    with mock.patch.object(
        target._shot_routing,
        "schedule_post_hydration_reconcile",
        return_value=False,
    ):
        for name, value in (
            (
                target.SHOT_CHANNEL_UUID_PARAMETER,
                "00000000-0000-4000-8000-000000000001",
            ),
            (
                target.SHOT_UUID_PARAMETER,
                "00000000-0000-4000-8000-000000000002",
            ),
            (target.SHOT_NUMBER_PARAMETER, 2),
            (target.SHOT_NAME_PARAMETER, "Shot 2"),
        ):
            node.set_parameter_value(name, value, initial_setup=True)
    assert node._hmb_shot_channel_subscription()["enabled"] is True
    node._update_parameter_visibility()
    assert_manual_reference_visibility(False)
    assert node.get_parameter_by_name(target.TASK_PARAMETER).hide is True
    assert node.get_parameter_value("task") == target.TASK_VIDEO_EDITING
    assert node.get_parameter_value("reference_images") == manual_images
    assert node.get_parameter_value(target.VIDEO_REFERENCES_PARAMETER) == manual_videos
    assert node._get_list_input("reference_audio") == manual_audio

    with mock.patch.object(
        target._shot_routing,
        "schedule_post_hydration_reconcile",
        return_value=False,
    ):
        for name, value in (
            (target.SHOT_CHANNEL_UUID_PARAMETER, ""),
            (target.SHOT_UUID_PARAMETER, ""),
            (target.SHOT_NUMBER_PARAMETER, 0),
            (target.SHOT_NAME_PARAMETER, ""),
        ):
            node.set_parameter_value(name, value, initial_setup=True)
    assert node._hmb_shot_channel_subscription()["enabled"] is False
    node._update_parameter_visibility()
    assert_manual_reference_visibility(True)
    assert node.get_parameter_by_name(target.TASK_PARAMETER).hide is False
    assert node.get_parameter_value("task") == target.TASK_VIDEO_EDITING
    assert node.get_parameter_value("reference_images") == manual_images
    assert node.get_parameter_value(target.VIDEO_REFERENCES_PARAMETER) == manual_videos
    assert node._get_list_input("reference_audio") == manual_audio

    # An explicit empty current value is authoritative. It must not revive an
    # old serialized ParameterList cache or the three retired scalar videos.
    empty_audio_node = target.HMBSeedanceGeneration(
        name="Explicit Empty Audio Regression"
    )
    # Reproduce Griptape's documented stale top-level cache after list rows
    # were deleted. Serialized list replay itself is expanded into real rows.
    empty_audio_node.parameter_values["reference_audio"] = [
        "https://cdn.example/stale-audio.wav"
    ]
    current_audio = empty_audio_node.get_parameter_by_name(
        "reference_audio"
    ).append_child_parameter()
    empty_audio_node.set_parameter_value(
        current_audio.name,
        "https://cdn.example/current-audio.wav",
    )
    assert empty_audio_node._get_list_input("reference_audio") == [
        "https://cdn.example/current-audio.wav"
    ]
    empty_audio_node.get_parameter_by_name("reference_audio").clear_list()
    assert empty_audio_node.get_parameter_value("reference_audio") == []
    assert empty_audio_node._get_list_input("reference_audio") == []
    assert empty_audio_node._get_parameters()["reference_audio"] == []

    empty_video_node = target.HMBSeedanceGeneration(
        name="Explicit Empty Video Regression"
    )
    empty_video_node.set_parameter_value(
        "reference_video_1",
        target.VideoUrlArtifact("https://cdn.example/stale-legacy-video.mp4"),
        initial_setup=True,
    )
    empty_video_node.set_parameter_value(
        target.VIDEO_REFERENCES_PARAMETER,
        ["https://cdn.example/current-video.mp4"],
        initial_setup=True,
    )
    assert empty_video_node._get_parameters()["video_references"] == [
        "https://cdn.example/current-video.mp4"
    ]
    empty_video_node.set_parameter_value(
        target.VIDEO_REFERENCES_PARAMETER,
        [],
        initial_setup=True,
    )
    empty_video_params = empty_video_node._get_parameters()
    assert empty_video_params["video_references"] == []
    assert empty_video_params["video_reference_slots"] == []


def assert_image_asset_single_wire_host_contract() -> None:
    context_manager = GriptapeNodes.ContextManager()
    assert not context_manager.has_current_workflow(), (
        "Host connection regression must run in an isolated process."
    )
    GriptapeNodes.EventManager().initialize_queue()
    stamp = time.time_ns()
    ensured = GriptapeNodes.handle_request(
        EnsureWorkflowAndFlowRequest(
            display_name=f"HMB Seedance Image Batch Regression {stamp}",
            flow_name=f"HMBSeedanceImageBatchFlow_{stamp}",
        )
    )
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess), (
        type(ensured).__name__,
        getattr(ensured, "result_details", ""),
    )
    assert ensured.created_workflow is True
    assert ensured.created_flow is True
    flow = GriptapeNodes.FlowManager().get_flow_by_name(ensured.flow_name)

    def register(node: object) -> None:
        flow.add_node(node)
        GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
        GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name

    def publish_selected(source: object, values: list[str]) -> None:
        state, media_by_uid = image_asset_target._merge_import_input(
            source._current_state(), values
        )
        source._hmb_import_media_by_uid = media_by_uid
        source._publish_state(state)
        assert source.parameter_output_values[
            image_asset_target.MEDIA_OUTPUT_PARAMETER
        ] == values

    def connect(source: object, destination: object) -> None:
        result = GriptapeNodes.handle_request(
            CreateConnectionRequest(
                source_node_name=source.name,
                source_parameter_name=image_asset_target.MEDIA_OUTPUT_PARAMETER,
                target_node_name=destination.name,
                target_parameter_name="reference_images",
            )
        )
        assert isinstance(result, CreateConnectionResultSuccess), (
            type(result).__name__,
            getattr(result, "result_details", ""),
        )

    try:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            image_asset_target, "DEFAULT_PROJECTS_ROOT", Path(temporary)
        ):
            source = image_asset_target.HMBImageAssetLibrary(
                name=f"ImageAssetBatch_{stamp}"
            )
            destination = target.HMBSeedanceGeneration(
                name=f"SeedanceBatch_{stamp}"
            )
            register(source)
            register(destination)
            ordered = [
                f"https://example.test/reference-{index}.png"
                for index in (7, 2, 9, 1, 8, 3, 6, 4, 5)
            ]
            publish_selected(source, ordered)
            destination.set_parameter_value("prompt", "single wire ordered batch")
            connect(source, destination)

            assert destination.get_parameter_value("reference_images") == ordered
            params = destination._get_parameters()
            assert params["reference_images"] == ordered
            destination._validate_parameters(params)
            payload = destination._build_broker_payload(params)
            assert payload["image_urls"] == ordered

            reordered = [ordered[2], ordered[0], ordered[4]]
            reordered_positions = {
                value: index for index, value in enumerate(reordered, start=1)
            }
            reordered_state = source._current_state()
            for asset in reordered_state["assets"]:
                value = asset.get("path")
                asset["selected"] = value in reordered_positions
                asset["selection_order"] = reordered_positions.get(value, 0)
            reordered_result = GriptapeNodes.handle_request(
                SetParameterValueRequest(
                    node_name=source.name,
                    parameter_name=image_asset_target.WIDGET_STATE_PARAMETER,
                    value=json.dumps(reordered_state),
                    data_type="str",
                )
            )
            assert isinstance(reordered_result, SetParameterValueResultSuccess), (
                type(reordered_result).__name__,
                getattr(reordered_result, "result_details", ""),
            )
            assert source.parameter_output_values[
                image_asset_target.MEDIA_OUTPUT_PARAMETER
            ] == reordered
            assert destination.get_parameter_value("reference_images") == reordered
            assert destination._get_parameters()["reference_images"] == reordered

            listed = GriptapeNodes.handle_request(
                ListConnectionsForNodeRequest(node_name=destination.name)
            )
            assert isinstance(listed, ListConnectionsForNodeResultSuccess)
            incoming = [
                edge
                for edge in listed.incoming_connections
                if edge.target_parameter_name == "reference_images"
            ]
            assert len(incoming) == 1
            assert incoming[0].source_node_name == source.name
            assert (
                incoming[0].source_parameter_name
                == image_asset_target.MEDIA_OUTPUT_PARAMETER
            )

            overflow_source = image_asset_target.HMBImageAssetLibrary(
                name=f"ImageAssetOverflow_{stamp}"
            )
            overflow_destination = target.HMBSeedanceGeneration(
                name=f"SeedanceOverflow_{stamp}"
            )
            register(overflow_source)
            register(overflow_destination)
            overflow = [
                f"https://example.test/overflow-{index}.png"
                for index in range(10)
            ]
            publish_selected(overflow_source, overflow)
            overflow_destination.set_parameter_value("prompt", "reject ten images")
            connect(overflow_source, overflow_destination)
            try:
                overflow_destination._validate_parameters(
                    overflow_destination._get_parameters()
                )
            except ValueError as exc:
                assert "at most 9 reference images" in str(exc)
            else:
                raise AssertionError("Connected ten-image batch was accepted")
    finally:
        deleted = asyncio.run(
            GriptapeNodes.ahandle_request(
                DeleteWorkflowRequest(name=ensured.workflow_name)
            )
        )
        assert isinstance(deleted, DeleteWorkflowResultSuccess), (
            type(deleted).__name__,
            getattr(deleted, "result_details", ""),
        )
        assert not context_manager.has_current_workflow()
        assert not context_manager.has_current_flow()
        assert (
            GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(
                ensured.flow_name, type(flow)
            )
            is None
        )


def assert_video_picker_single_wire_host_contract() -> None:
    context_manager = GriptapeNodes.ContextManager()
    assert not context_manager.has_current_workflow(), (
        "Host connection regression must run in an isolated process."
    )
    GriptapeNodes.EventManager().initialize_queue()
    stamp = time.time_ns()
    ensured = GriptapeNodes.handle_request(
        EnsureWorkflowAndFlowRequest(
            display_name=f"HMB Seedance Video Batch Regression {stamp}",
            flow_name=f"HMBSeedanceVideoBatchFlow_{stamp}",
        )
    )
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess), (
        type(ensured).__name__,
        getattr(ensured, "result_details", ""),
    )
    flow = GriptapeNodes.FlowManager().get_flow_by_name(ensured.flow_name)

    def register(node: object) -> None:
        flow.add_node(node)
        GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
        GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name

    try:
        source = video_picker_target.HMBVideoPickerLibrary(
            name=f"VideoPickerBatch_{stamp}"
        )
        destination = target.HMBSeedanceGeneration(
            name=f"SeedanceVideoBatch_{stamp}"
        )
        register(source)
        register(destination)
        selected_numbers = (4, 1, 3)
        ordered = [
            f"https://example.test/reference-video-{number}.mp4"
            for number in selected_numbers
        ]
        state = video_picker_target._default_widget_state()
        state["videos"] = [
            {
                "video_uid": f"video-{number}",
                "source_uid": f"video-{number}",
                "video_path": media,
                "selected": True,
                "selection_order": selection_order,
            }
            for selection_order, (number, media) in enumerate(
                zip(selected_numbers, ordered, strict=True), start=1
            )
        ]
        source._sync_outputs_from_state(state)
        assert source.parameter_output_values[
            video_picker_target.VIDEO_OUTPUT_PARAMETER
        ] == ordered
        connected = GriptapeNodes.handle_request(
            CreateConnectionRequest(
                source_node_name=source.name,
                source_parameter_name=video_picker_target.VIDEO_OUTPUT_PARAMETER,
                target_node_name=destination.name,
                target_parameter_name=target.VIDEO_REFERENCES_PARAMETER,
            )
        )
        assert isinstance(connected, CreateConnectionResultSuccess), (
            type(connected).__name__,
            getattr(connected, "result_details", ""),
        )
        assert destination.get_parameter_value(target.VIDEO_REFERENCES_PARAMETER) == ordered
        destination.set_parameter_value("prompt", "single wire ordered videos")
        params = destination._get_parameters()
        assert params["video_references"] == ordered
        assert params["video_reference_slots"] == []
        destination._validate_parameters(params)
        payload = destination._build_broker_payload(params)
        assert payload["video_urls"] == ordered

        listed = GriptapeNodes.handle_request(
            ListConnectionsForNodeRequest(node_name=destination.name)
        )
        assert isinstance(listed, ListConnectionsForNodeResultSuccess)
        incoming = [
            edge
            for edge in listed.incoming_connections
            if edge.target_parameter_name == target.VIDEO_REFERENCES_PARAMETER
        ]
        assert len(incoming) == 1
        assert incoming[0].source_node_name == source.name
        assert (
            incoming[0].source_parameter_name
            == video_picker_target.VIDEO_OUTPUT_PARAMETER
        )
    finally:
        deleted = asyncio.run(
            GriptapeNodes.ahandle_request(
                DeleteWorkflowRequest(name=ensured.workflow_name)
            )
        )
        assert isinstance(deleted, DeleteWorkflowResultSuccess), (
            type(deleted).__name__,
            getattr(deleted, "result_details", ""),
        )
        assert not context_manager.has_current_workflow()
        assert not context_manager.has_current_flow()




def assert_payload_and_media_contract() -> None:
    node = target.HMBSeedanceGeneration(name="Payload Regression")
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        image_path = temporary_path / "reference.png"
        audio_path = temporary_path / "reference.wav"
        video_path = temporary_path / "reference.mp4"
        image_bytes = b"\x89PNG\r\n\x1a\nimage-regression"
        audio_bytes = b"RIFFaudio-regression"
        image_path.write_bytes(image_bytes)
        audio_path.write_bytes(audio_bytes)
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42video")

        params = node._get_parameters()
        params.update(
            {
                "model_id": target.SEEDANCE_2_0_MODEL_ID,
                "input_mode": target.INPUT_MODE_MULTIMODAL_REFERENCES,
                "prompt": "A precise regression shot",
                "reference_images": [str(image_path), "https://cdn.example/ref.jpg"],
                "video_references": ["asset://video-asset-1"],
                "reference_audio": [str(audio_path)],
                "resolution": "1080p",
                "ratio": "16:9",
                "duration": 8,
                "generate_audio": True,
                "watermark": False,
                "return_last_frame": True,
            }
        )
        payload = node._build_broker_payload(params)

        assert payload["model"] == "doubao-seedance-2-0-260128"
        assert payload["quality"] == "1080p"
        # The 2.0 Broker adapter retains its established pixel-shaped
        # compatibility field; the 2.5 enum contract is asserted below.
        assert payload["resolution"] == "1280x720"
        assert payload["aspect_ratio"] == "16:9"
        assert payload["duration_seconds"] == 8
        assert payload["generate_audio"] is True
        assert payload["watermark"] is False
        assert "output_format" not in payload
        assert "return_last_frame" not in payload
        assert payload["prompt"] == "A precise regression shot"
        assert payload["video_urls"] == ["asset://video-asset-1"]
        encoded_image = payload["image_urls"][0]
        assert payload["image_urls"][1] == "https://cdn.example/ref.jpg"
        encoded_audio = payload["audio_urls"][0]
        assert encoded_image.startswith("data:image/png;base64,")
        assert base64.b64decode(encoded_image.split(",", 1)[1]) == image_bytes
        assert encoded_audio.startswith("data:audio/wav;base64,")
        assert base64.b64decode(encoded_audio.split(",", 1)[1]) == audio_bytes
        for unsupported in ("seed", "frames", "draft", "camera_fixed", "parameters"):
            assert unsupported not in payload

        try:
            node._prepare_media_reference("video", str(video_path))
        except ValueError as exc:
            assert "does not accept Base64/local video" in str(exc)
        else:
            raise AssertionError("Local MP4 was accepted")

        portable_video = r"inputs\test_del\JettMini_test\JettMini_test_playblast_1.mp4"
        with mock.patch.object(target, "File") as project_file:
            project_file.return_value.resolve.return_value = str(video_path)
            try:
                node._prepare_media_reference("video", portable_video)
            except ValueError as exc:
                assert "does not accept Base64/local video" in str(exc)
                assert "file does not exist" not in str(exc)
            else:
                raise AssertionError("Resolved local MP4 was accepted")
            project_file.assert_called_once_with(portable_video)

        portable_image = r"inputs\test_del\reference.png"
        with mock.patch.object(target, "File") as project_file:
            project_file.return_value.resolve.return_value = str(image_path)
            encoded_portable_image = node._prepare_media_reference(
                "image", portable_image
            )
            assert encoded_portable_image.startswith("data:image/png;base64,")
            assert base64.b64decode(encoded_portable_image.split(",", 1)[1]) == image_bytes
            project_file.assert_called_once_with(portable_image)

    node.set_parameter_value(
        "reference_video_1",
        target.VideoUrlArtifact("https://cdn.example/video-1.mp4"),
    )
    node.set_parameter_value(
        "reference_video_2",
        target.VideoUrlArtifact("asset://video-asset-2"),
    )
    collected = node._get_parameters()
    assert [target.HMBSeedanceGeneration._coerce_reference_value(item) for item in collected["video_references"]] == [
        "https://cdn.example/video-1.mp4",
        "asset://video-asset-2",
    ]
    assert node.get_parameter_by_name("reference_video_1").hide is True
    assert node.get_parameter_by_name("reference_video_2").hide is True
    assert node.get_parameter_by_name("reference_video_3").hide is True

    ordered_list_node = target.HMBSeedanceGeneration(
        name="Picker Ordered Video List Regression"
    )
    ordered_list_node.set_parameter_value("prompt", "preserve picker order")
    ordered_videos = [
        "https://cdn.example/video-4.mp4",
        "asset://video-1",
        "https://cdn.example/video-3.mp4",
    ]
    ordered_list_node.set_parameter_value("VIDEO_REFERENCES", ordered_videos)
    ordered_video_params = ordered_list_node._get_parameters()
    assert ordered_video_params["video_references"] == ordered_videos
    assert ordered_video_params["video_reference_slots"] == []
    ordered_video_payload = ordered_list_node._build_broker_payload(
        ordered_video_params
    )
    assert ordered_video_payload["video_urls"] == ordered_videos

    overflow_video_node = target.HMBSeedanceGeneration(
        name="Picker Video Overflow Regression"
    )
    overflow_video_node.set_parameter_value("prompt", "reject four videos")
    overflow_video_node.set_parameter_value(
        "VIDEO_REFERENCES",
        [f"https://cdn.example/video-{index}.mp4" for index in range(1, 5)],
    )
    try:
        overflow_video_node._validate_parameters(overflow_video_node._get_parameters())
    except ValueError as exc:
        assert "at most 3 reference videos" in str(exc)
    else:
        raise AssertionError("A four-video Picker batch was accepted")

    scalar_node = target.HMBSeedanceGeneration(name="Scalar Video Regression")
    scalar_node.set_parameter_value("prompt", "ordered scalar videos")
    scalar_node.set_parameter_value(
        "reference_video_1",
        target.VideoUrlArtifact("https://cdn.example/scalar-1.mp4"),
    )
    scalar_node.set_parameter_value(
        "reference_video_2", {"value": "asset://scalar-video-2"}
    )
    scalar_payload = scalar_node._build_broker_payload(scalar_node._get_parameters())
    assert scalar_payload["video_urls"] == [
        "https://cdn.example/scalar-1.mp4",
        "asset://scalar-video-2",
    ]

    gap_params = node._get_parameters()
    gap_params.update(
        {
            "prompt": "gap validation",
            "video_reference_slots": [None, "https://cdn.example/video-2.mp4", None],
            "video_references": ["https://cdn.example/video-2.mp4"],
        }
    )
    node._validate_parameters(gap_params)
    assert gap_params["video_references"] == [
        "https://cdn.example/video-2.mp4"
    ]

    legacy_node = target.HMBSeedanceGeneration(name="Legacy List Regression")
    legacy_node.set_parameter_value(
        "VIDEO_REFERENCES", ["https://cdn.example/legacy.mp4"]
    )
    assert legacy_node._get_parameters()["video_references"] == [
        "https://cdn.example/legacy.mp4"
    ]

    equivalent_legacy_node = target.HMBSeedanceGeneration(
        name="Legacy and Scalar Payload Equivalence Regression"
    )
    equivalent_legacy_node.set_parameter_value("prompt", "ordered scalar videos")
    equivalent_legacy_node.set_parameter_value(
        "VIDEO_REFERENCES",
        ["https://cdn.example/scalar-1.mp4", "asset://scalar-video-2"],
    )
    assert equivalent_legacy_node._build_broker_payload(
        equivalent_legacy_node._get_parameters()
    ) == scalar_payload

    mixed_node = target.HMBSeedanceGeneration(
        name="Public Video List Overrides Hidden Scalar Regression"
    )
    mixed_node.set_parameter_value(
        "VIDEO_REFERENCES", ["https://cdn.example/public-list.mp4"]
    )
    mixed_node.set_parameter_value(
        "reference_video_1",
        target.VideoUrlArtifact("https://cdn.example/new-scalar.mp4"),
    )
    assert [
        target.HMBSeedanceGeneration._coerce_reference_value(item)
        for item in mixed_node._get_parameters()["video_references"]
    ] == ["https://cdn.example/public-list.mp4"]
    assert mixed_node._get_parameters()["video_reference_slots"] == []

    serialized_list_node = target.HMBSeedanceGeneration(
        name="Serialized List Compatibility Regression"
    )
    serialized_list_node.set_parameter_value(
        "reference_images", ["https://cdn.example/legacy-image.png"], initial_setup=True
    )
    serialized_list_node.set_parameter_value(
        "reference_audio", ["https://cdn.example/legacy-audio.mp3"], initial_setup=True
    )
    assert serialized_list_node.get_parameter_value("reference_images") == [
        "https://cdn.example/legacy-image.png"
    ]
    assert serialized_list_node.get_parameter_value("reference_audio") == [
        "https://cdn.example/legacy-audio.mp3"
    ]
    migrated = serialized_list_node._get_parameters()
    assert migrated["reference_images"] == [
        "https://cdn.example/legacy-image.png"
    ]
    assert migrated["reference_audio"] == [
        "https://cdn.example/legacy-audio.mp3"
    ]

    ordered_image_node = target.HMBSeedanceGeneration(
        name="Single Wire Ordered Image Regression"
    )
    ordered_images = [
        "https://cdn.example/current-image.png",
        "https://cdn.example/current-image-2.png",
    ]
    ordered_image_node.set_parameter_value("reference_images", ordered_images)
    ordered_image_node.set_parameter_value("prompt", "single wire list order")
    assert ordered_image_node.get_parameter_value("reference_images") == ordered_images
    assert ordered_image_node._get_parameters()["reference_images"] == ordered_images
    ordered_list_payload = ordered_image_node._build_broker_payload(
        ordered_image_node._get_parameters()
    )
    assert ordered_list_payload["image_urls"] == ordered_images
    assert ordered_list_payload["prompt"] == "single wire list order"

    empty_child_node = target.HMBSeedanceGeneration(
        name="Empty Single Image List Regression"
    )
    empty_child_node.get_parameter_by_name("reference_audio").append_child_parameter()
    empty_child_node.set_parameter_value(
        target.TASK_PARAMETER,
        target.TASK_TEXT_ONLY,
    )
    empty_child_node.set_parameter_value("prompt", "empty child is ignored")
    assert empty_child_node.get_parameter_value("reference_images") == []
    assert empty_child_node.get_parameter_value("reference_audio") == [[]]
    empty_child_params = empty_child_node._get_parameters()
    assert empty_child_params["reference_images"] == []
    assert empty_child_params["reference_audio"] == []
    empty_child_payload = empty_child_node._build_broker_payload(empty_child_params)
    assert empty_child_payload["prompt"] == "empty child is ignored"
    assert "image_urls" not in empty_child_payload
    assert "audio_urls" not in empty_child_payload

    connected_parent_list_node = target.HMBSeedanceGeneration(
        name="Connected Parent List Regression"
    )
    connected_parent_list_node.set_parameter_value(
        "reference_images", ["https://cdn.example/connected-list.png"]
    )
    assert connected_parent_list_node.get_parameter_value("reference_images") == [
        "https://cdn.example/connected-list.png"
    ]
    assert connected_parent_list_node._get_parameters()["reference_images"] == [
        "https://cdn.example/connected-list.png"
    ]

    assert target.MODEL_ID_ALIASES["dreamina-seedance-2-0-260128"] == (
        target.SEEDANCE_2_0_MODEL_ID
    )
    params = node._get_parameters()
    params.update(
        {
            "model_id": target.SEEDANCE_2_0_FAST_MODEL_ID,
            "resolution": "1080p",
            "prompt": "fast",
        }
    )
    try:
        node._validate_parameters(params)
    except ValueError as exc:
        assert "does not support 1080p" in str(exc)
    else:
        raise AssertionError("Fast model accepted 1080p")

    params = node._get_parameters()
    params.update(
        {
            "model_id": target.SEEDANCE_2_0_MODEL_ID,
            "resolution": "4k",
            "prompt": "standard 4k",
        }
    )
    standard_4k_payload = node._build_broker_payload(params)
    assert standard_4k_payload["model"] == target.SEEDANCE_2_0_MODEL_ID
    assert standard_4k_payload["quality"] == "4k"

    for restricted_model in (
        target.SEEDANCE_2_0_FAST_MODEL_ID,
        target.SEEDANCE_2_5_MODEL_ID,
    ):
        params = node._get_parameters()
        params.update(
            {
                "model_id": restricted_model,
                "resolution": "4k",
                "prompt": "restricted 4k",
            }
        )
        try:
            node._validate_parameters(params)
        except ValueError as exc:
            assert "does not support 4k" in str(exc)
        else:
            raise AssertionError(f"Restricted model accepted 4k: {restricted_model}")

    params = node._get_parameters()
    params.update(
        {
            "model_id": target.SEEDANCE_2_0_FAST_MODEL_ID,
            "resolution": "720p",
            "priority": 0,
            "prompt": "fast priority omission",
        }
    )
    fast_payload = node._build_broker_payload(params)
    assert "priority" not in fast_payload

    params = node._get_parameters()
    params.update(
        {
            "prompt": "too many videos",
            "video_references": [f"https://cdn.example/{index}.mp4" for index in range(4)],
        }
    )
    try:
        node._validate_parameters(params)
    except ValueError as exc:
        assert "at most 3 reference videos" in str(exc)
        assert "No references were discarded" in str(exc)
    else:
        raise AssertionError("Four reference videos were accepted")

    params = node._get_parameters()
    params.update(
        {
            "prompt": "too many images",
            "reference_images": [
                f"https://cdn.example/{index}.png" for index in range(10)
            ],
        }
    )
    try:
        node._validate_parameters(params)
    except ValueError as exc:
        assert "at most 9 reference images" in str(exc)
    else:
        raise AssertionError("Ten reference images were accepted")

    params = node._get_parameters()
    params.update(
        {
            "prompt": "too many audio references",
            "reference_audio": [
                f"https://cdn.example/{index}.mp3" for index in range(4)
            ],
        }
    )
    try:
        node._validate_parameters(params)
    except ValueError as exc:
        assert "at most 3 reference audio" in str(exc)
    else:
        raise AssertionError("Four reference audio files were accepted")

    params = node._get_parameters()
    params.update(
        {
            "task": target.TASK_FIRST_LAST_FRAME,
            "input_mode": target.INPUT_MODE_FIRST_LAST_FRAME,
            "prompt": "",
            "first_frame": None,
            "last_frame": "https://cdn.example/last.png",
            "reference_images": [],
            "video_references": [],
            "reference_audio": [],
        }
    )
    try:
        node._validate_parameters(params)
    except ValueError as exc:
        assert "Last Frame requires First Frame" in str(exc)
    else:
        raise AssertionError("Last Frame without First Frame was accepted")


def assert_seedance_25_model_contract() -> None:
    node = target.HMBSeedanceGeneration(name="Seedance 2.5 Contract Regression")
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_5)

    assert node._get_parameters()["model_id"] == target.SEEDANCE_2_5_MODEL_ID
    assert node.get_parameter_value("resolution") == "720p"
    assert node.get_parameter_by_name("resolution").ui_options["simple_dropdown"] == [
        "720p",
        "1080p",
    ]
    assert node.get_parameter_by_name("duration").ui_options["simple_dropdown"] == [
        *range(4, 31),
    ]

    params = node._get_parameters()
    params.update(
        {
            "model_id": target.SEEDANCE_2_5_MODEL_ID,
            "input_mode": target.INPUT_MODE_MULTIMODAL_REFERENCES,
            "prompt": "Seedance 2.5 model-specific capacity",
            "resolution": "720p",
            "ratio": "adaptive",
            "duration": 30,
            "priority": 0,
            "reference_images": [
                f"https://cdn.example/seedance-25-image-{index}.png"
                for index in range(30)
            ],
            "video_references": [
                f"https://cdn.example/seedance-25-video-{index}.mp4"
                for index in range(10)
            ],
            "video_reference_slots": [],
            "reference_audio": [
                f"https://cdn.example/seedance-25-audio-{index}.mp3"
                for index in range(10)
            ],
        }
    )
    node._validate_parameters(params)
    payload = node._build_broker_payload(params)
    assert payload["model"] == target.SEEDANCE_2_5_MODEL_ID
    assert payload["quality"] == "720p"
    assert payload["resolution"] == "720p"
    assert payload["duration_seconds"] == 30
    assert len(payload["image_urls"]) == 30
    assert len(payload["video_urls"]) == 10
    assert len(payload["audio_urls"]) == 10
    assert "priority" not in payload

    for supported_duration in (4, 30):
        boundary = dict(params)
        boundary["duration"] = supported_duration
        node._validate_parameters(boundary)
    for unsupported_duration in (-1, 3, 31):
        invalid = dict(params)
        invalid["duration"] = unsupported_duration
        try:
            node._validate_parameters(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Seedance 2.5 accepted unsupported duration: {unsupported_duration}"
            )

    high_definition = dict(params)
    high_definition["resolution"] = "1080p"
    high_definition["ratio"] = "9:16"
    node._validate_parameters(high_definition)
    high_definition_payload = node._build_broker_payload(high_definition)
    assert high_definition_payload["quality"] == "1080p"
    assert high_definition_payload["resolution"] == "1080p"
    assert high_definition_payload["aspect_ratio"] == "9:16"
    unsupported_resolution = dict(params)
    unsupported_resolution["resolution"] = "480p"
    try:
        node._validate_parameters(unsupported_resolution)
    except ValueError as exc:
        assert "does not support 480p" in str(exc)
    else:
        raise AssertionError("Seedance 2.5 accepted 480p")

    overflow_cases = (
        (
            "reference_images",
            [f"https://cdn.example/overflow-{index}.png" for index in range(31)],
            "at most 30 reference images",
        ),
        (
            "video_references",
            [f"https://cdn.example/overflow-{index}.mp4" for index in range(11)],
            "at most 10 reference videos",
        ),
        (
            "reference_audio",
            [f"https://cdn.example/overflow-{index}.mp3" for index in range(11)],
            "at most 10 reference audio",
        ),
    )
    for field_name, overflow_values, expected_message in overflow_cases:
        invalid = dict(params)
        invalid[field_name] = overflow_values
        try:
            node._validate_parameters(invalid)
        except ValueError as exc:
            assert expected_message in str(exc)
        else:
            raise AssertionError(f"Seedance 2.5 accepted overflow: {field_name}")


def assert_broker_generation_contract() -> None:
    status_cases = {
        "pending": "queued",
        "submitted": "queued",
        "running": "running",
        "in-progress": "running",
        "completed": "succeeded",
        "success": "succeeded",
        "failed": "failed",
        "rejected": "failed",
        "cancelled": "cancelled",
        "expired": "expired",
    }
    for raw, expected in status_cases.items():
        assert target.HMBSeedanceGeneration._normalize_broker_status(raw) == (
            expected
        )
    assert target.HMBSeedanceGeneration._normalize_broker_status(
        "provider-api-key-canary"
    ) == ""

    oversized_error = target.urllib.error.HTTPError(
        "http://broker.invalid/api/v1/generate/video",
        413,
        "Payload Too Large",
        {},
        io.BytesIO(
            b'{"error_code":"request_body_too_large","token":"secret-canary"}'
        ),
    )
    safe_error_message = target._HMBAIBrokerBridge._safe_http_error_message(
        oversized_error
    )
    assert "oversized reference-media request" in safe_error_message
    assert "secret-canary" not in safe_error_message

    detached_bridge = FakeBrokerBridge([])
    detached = target.HMBSeedanceGeneration(name="Detached Broker Guard Regression")
    detached._broker_bridge_instance = detached_bridge
    detached.set_parameter_value("prompt", "must remain detached")
    asyncio.run(detached._process_generation())
    assert detached_bridge.account_calls == 0
    assert detached_bridge.generate_payloads == []
    assert detached_bridge.refresh_ids == []

    completed = {
        "status": "completed",
        "job_id": "broker-job-1",
        "output": "https://cdn.example/broker-result.mp4",
        "token": FakeBrokerBridge.SECRET_VALUES[0],
        "api_key": FakeBrokerBridge.SECRET_VALUES[1],
        "authorization": FakeBrokerBridge.SECRET_VALUES[2],
    }
    bridge = FakeBrokerBridge([completed])
    node = BrokerScriptedNode(bridge)
    node.set_parameter_value(target.TASK_PARAMETER, target.TASK_TEXT_ONLY)
    node.set_parameter_value("prompt", "Broker-only Seedance regression")
    assert not hasattr(node, "_get_" + "api_key")
    assert not {name for name in dir(node) if "usage" in name.casefold()}
    asyncio.run(node._process_generation())

    assert bridge.account_calls == 1
    assert bridge.refresh_ids == ["broker-job-1"]
    assert len(bridge.generate_payloads) == 1
    payload = bridge.generate_payloads[0]
    assert payload["provider"] == "volcengine_ark"
    assert payload["model"] == target.SEEDANCE_2_0_MODEL_ID
    assert payload["prompt"] == "Broker-only Seedance regression"
    assert payload["duration_seconds"] == 5
    assert payload["quality"] == "1080p"
    assert payload["aspect_ratio"] == "adaptive"
    assert not any(
        sensitive in key.lower()
        for key in payload
        for sensitive in ("api_key", "token", "secret", "credential")
    )
    assert node.parameter_output_values["generation_id"] == "broker-job-1"
    assert node.parameter_output_values["generation_status"] == "succeeded"
    assert node.parameter_output_values["provider_response"] == {
        "transport": "fn_ai_broker",
        "id": "broker-job-1",
        "status": "succeeded",
    }
    assert node.get_parameter_value("broker_connection_status") == "Connected"
    assert node.get_parameter_value("broker_account") == "Broker Artist"
    assert node.downloads == ["https://cdn.example/broker-result.mp4"]
    assert node.parameter_output_values["VIDEO_OUT"].value == node.destination.location

    public_state = json.dumps(
        {
            "parameters": node.parameter_values,
            "outputs": node.parameter_output_values,
        },
        default=str,
        ensure_ascii=False,
    )
    for secret in FakeBrokerBridge.SECRET_VALUES:
        assert secret not in public_state
    assert "••••" not in public_state

    resume_bridge = FakeBrokerBridge(
        [
            {
                "status": "completed",
                "job_id": "broker-resume-9",
                "output": "https://cdn.example/resumed-broker.mp4",
                "token": FakeBrokerBridge.SECRET_VALUES[0],
            }
        ]
    )
    resumed = BrokerScriptedNode(resume_bridge)
    resumed.set_parameter_value("resume_generation_id", "broker-resume-9")
    # Resume/retrieve performs no upload. Broken/stale TOS authoring controls
    # must not make an already-submitted Broker result unrecoverable.
    resumed.set_parameter_value(
        "local_video_upload_service", target.LOCAL_VIDEO_UPLOAD_TOS
    )
    resumed.set_parameter_value("tos_url_validity_seconds", 0)
    asyncio.run(resumed._process_generation())
    assert resume_bridge.generate_payloads == []
    assert resume_bridge.refresh_ids == ["broker-resume-9"]
    assert resumed.downloads == ["https://cdn.example/resumed-broker.mp4"]

    refresh_bridge = FakeBrokerBridge(
        [
            {
                "status": "completed",
                "job_id": "broker-refresh-3",
                "output": "https://cdn.example/refreshed-broker.mp4",
            }
        ]
    )
    refreshed = BrokerScriptedNode(refresh_bridge)
    refreshed.parameter_output_values["generation_id"] = "broker-refresh-3"
    asyncio.run(refreshed._refresh_async())
    assert refresh_bridge.refresh_ids == ["broker-refresh-3"]
    assert refreshed.downloads == ["https://cdn.example/refreshed-broker.mp4"]

    # A response error while polling an already-authoritative task is not a
    # create rejection. It must retain the task and its safe retrieve action,
    # even when the HTTP status happens to match a create-side rejection.
    polling_error = target._BrokerError(
        "FN AI Broker request failed with HTTP 429.",
        status_code=429,
    )
    assert polling_error.definitive_submission_rejection is False
    polling_error_bridge = FakeBrokerBridge([])
    polling_error_bridge.refresh_job = mock.Mock(side_effect=polling_error)
    polling_error_node = BrokerScriptedNode(polling_error_bridge)
    polling_error_node.set_parameter_value(
        "resume_generation_id",
        "broker-authoritative-429",
    )
    polling_status_results: list[dict] = []
    polling_error_node._clear_execution_status = lambda: None
    polling_error_node._set_status_results = (
        lambda **kwargs: polling_status_results.append(dict(kwargs))
    )

    def raise_polling_failure(exc: BaseException) -> None:
        raise exc

    polling_error_node._handle_failure_exception = raise_polling_failure
    try:
        asyncio.run(polling_error_node._aprocess_impl())
    except RuntimeError as exc:
        polling_message = str(exc)
        assert "HTTP 429" in polling_message
        assert "Existing task ID: broker-authoritative-429" in polling_message
        assert "no new render was started" not in polling_message
    else:
        raise AssertionError("Authoritative task polling error was accepted")
    assert polling_error.definitive_submission_rejection is False
    assert polling_error_node.parameter_output_values["generation_id"] == (
        "broker-authoritative-429"
    )
    assert polling_error_node.parameter_output_values["provider_response"] == {
        "transport": "fn_ai_broker",
        "id": "broker-authoritative-429",
        "status": "resuming",
    }
    polling_error_preview = polling_error_node._hmb_generation_preview_state
    assert polling_error_preview["phase"] == "failed"
    assert polling_error_preview["job_id"] == "broker-authoritative-429"
    assert polling_error_preview["action"] == "refresh_existing"
    assert polling_status_results[-1]["was_successful"] is False
    assert "no new render was started" not in polling_status_results[-1][
        "result_details"
    ]


def assert_generation_preview_status_contract() -> None:
    """Keep preview status informative without granting the browser task authority."""

    private_path = "C:/private/artist/seedance-result.mp4"
    public_preview = target._seedance_generation_preview_value(
        {
            "phase": "running",
            "job_id": "authoritative-preview-job-1",
            "started_at_ms": 1_782_000_000_000,
            "elapsed_seconds": 151,
            "action": "refresh_existing",
            "has_existing_video": True,
            "media_revision": 7,
            "local_path": private_path,
            "video_url": "https://signed.example/private-result.mp4?token=secret",
            "provider_response": {"token": "provider-secret"},
        }
    )
    assert set(public_preview) == {
        "schema",
        "version",
        "phase",
        "job_id",
        "started_at_ms",
        "elapsed_seconds",
        "guidance",
        "action",
        "has_existing_video",
        "media_revision",
    }
    assert public_preview == {
        "schema": target.GENERATION_PREVIEW_SCHEMA,
        "version": target.GENERATION_PREVIEW_VERSION,
        "phase": "running",
        "job_id": "authoritative-preview-job-1",
        "started_at_ms": 1_782_000_000_000,
        "elapsed_seconds": 151,
        "guidance": target.GENERATION_PREVIEW_GUIDANCE["running"],
        "action": "refresh_existing",
        "has_existing_video": True,
        "media_revision": 7,
    }
    serialized_preview = json.dumps(public_preview, ensure_ascii=False)
    assert private_path not in serialized_preview
    assert "signed.example" not in serialized_preview
    assert "provider-secret" not in serialized_preview
    assert target._seedance_generation_preview_value(
        {
            "phase": "running",
            "job_id": "../../browser-chosen-job",
            "action": "refresh_existing",
        }
    )["action"] == "none"

    # Exercise a real generation through queued/running/download/verify/success.
    # The prior successful artifact must remain the ParameterVideo value until
    # the replacement file has been atomically published.
    completed = {
        "status": "completed",
        "job_id": "broker-job-1",
        "output": "https://cdn.example/preview-status-result.mp4",
    }
    bridge = FakeBrokerBridge(
        [
            {"status": "running", "job_id": "broker-job-1"},
            completed,
        ]
    )
    node = BrokerScriptedNode(bridge)
    previous_video = target.VideoUrlArtifact(private_path)
    node.parameter_output_values["video_url"] = previous_video
    node.parameter_output_values["VIDEO_OUT"] = previous_video
    node.parameter_output_values["last_frame_url"] = "retained-last-frame"
    node.set_parameter_value("prompt", "Preview status lifecycle regression")
    observed: list[tuple[str, object, dict]] = []
    publish = node._publish_generation_preview

    def observe_preview(phase: str, **kwargs) -> None:
        publish(phase, **kwargs)
        observed.append(
            (
                node._hmb_generation_preview_state["phase"],
                node.parameter_output_values.get("video_url"),
                dict(node._hmb_generation_preview_state),
            )
        )

    node._publish_generation_preview = observe_preview
    asyncio.run(node._process_generation())
    observed_phases = [phase for phase, _video, _state in observed]
    required_phases = [
        "preparing",
        "submitting",
        "queued",
        "running",
        "downloading",
        "verifying",
        "succeeded",
    ]
    phase_cursor = 0
    for phase in observed_phases:
        if phase_cursor < len(required_phases) and phase == required_phases[phase_cursor]:
            phase_cursor += 1
    assert phase_cursor == len(required_phases), observed_phases
    for phase, current_video, state in observed:
        if phase != "succeeded":
            assert current_video is previous_video, phase
        assert private_path not in json.dumps(state, ensure_ascii=False)
    assert bridge.generate_payloads and len(bridge.generate_payloads) == 1
    assert bridge.refresh_ids == ["broker-job-1", "broker-job-1"]
    assert node.downloads == ["https://cdn.example/preview-status-result.mp4"]
    assert node.parameter_output_values["video_url"] is not previous_video
    assert node._hmb_generation_preview_state["phase"] == "succeeded"
    assert node._hmb_generation_preview_state["media_revision"] == 1
    assert private_path not in json.dumps(
        node.get_parameter_value(target.SEEDANCE_SHOT_WIDGET_PARAMETER),
        ensure_ascii=False,
    )

    # A widget action is a pulse only. Even if a compromised browser supplies
    # a different Shot, catalog, or generation object, backend identity and the
    # existing authoritative task ID stay unchanged. This path performs one
    # same-ID status lookup and zero create-task calls.
    action_bridge = FakeBrokerBridge(
        [{"status": "running", "job_id": "authoritative-action-job-7"}]
    )
    action_node = BrokerScriptedNode(action_bridge)
    channel_uuid = "11111111-1111-4111-8111-111111111111"
    shot_uuid = "22222222-2222-4222-8222-222222222222"
    publisher_uuid = "33333333-3333-4333-8333-333333333333"
    shots = [
        {
            "shot_uuid": shot_uuid,
            "number": 2,
            "name": "Action Shot",
            "revision": 4,
        }
    ]
    metadata = {
        "channel_uuid": channel_uuid,
        "generation": 9,
        "shots": shots,
    }
    catalog = {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": publisher_uuid,
        **metadata,
        "metadata_sha256": target.HMBSeedanceGeneration._canonical_sha256(metadata),
    }
    action_node._hmb_shot_catalog_snapshot = catalog
    action_node._hmb_shot_catalog_generation = 9
    action_node._hmb_shot_selector_map = {"02 · Action Shot": shots[0]}
    action_node._hmb_shot_syncing = True
    try:
        action_node.set_parameter_value(target.SHOT_CHANNEL_UUID_PARAMETER, channel_uuid)
        action_node.set_parameter_value(target.SHOT_UUID_PARAMETER, shot_uuid)
        action_node.set_parameter_value(target.SHOT_NUMBER_PARAMETER, 2)
        action_node.set_parameter_value(target.SHOT_NAME_PARAMETER, "Action Shot")
        action_node.set_parameter_value(target.SHOT_SELECTOR_PARAMETER, "02 · Action Shot")
        action_node.set_parameter_value(target.SHOT_AUTOCLAIM_ENABLED_PARAMETER, True)
    finally:
        action_node._hmb_shot_syncing = False
    authoritative_id = "authoritative-action-job-7"
    action_node.parameter_output_values["generation_id"] = authoritative_id
    action_node.parameter_output_values["generation_status"] = "cancelled_locally"
    action_node._hmb_generation_preview_state = (
        target._seedance_generation_preview_value(
            {
                "phase": "cancelled_locally",
                "job_id": authoritative_id,
                "action": "refresh_existing",
            }
        )
    )
    # Model the already-rendered widget value that the backend, not this new
    # browser pulse, previously published. Action-only normalization must use
    # this catalog even if live graph discovery is momentarily unavailable.
    action_node.parameter_values[target.SEEDANCE_SHOT_WIDGET_PARAMETER] = (
        target._seedance_widget_value(
            {"channel_uuid": channel_uuid, "shot_uuid": shot_uuid},
            catalog,
            action_node._hmb_generation_preview_state,
        )
    )
    identity_before = action_node._shot_identity()
    catalog_before = json.dumps(
        action_node._hmb_shot_catalog_snapshot,
        ensure_ascii=False,
        sort_keys=True,
    )
    autoclaim_before = action_node.get_parameter_value(
        target.SHOT_AUTOCLAIM_ENABLED_PARAMETER
    )
    widget_parameter = action_node.get_parameter_by_name(
        target.SEEDANCE_SHOT_WIDGET_PARAMETER
    )
    assert widget_parameter is not None
    browser_value = {
        "request": {"action": "refresh_existing"},
        "shot": {
            "channel_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "shot_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        },
        "shot_catalog": {"browser": "must-not-be-authority"},
        "generation": {
            "phase": "succeeded",
            "job_id": "browser-supplied-job-must-be-ignored",
            "media_revision": 999,
        },
    }
    refresh_invocations: list[tuple[object, object]] = []
    deferred_refresh_callbacks: list[object] = []
    deferred_event_loop = SimpleNamespace(
        is_running=lambda: True,
        call_soon_threadsafe=lambda callback: deferred_refresh_callbacks.append(
            callback
        ),
    )

    def run_authoritative_refresh(button, details) -> None:
        refresh_invocations.append((button, details))
        asyncio.run(action_node._refresh_async())

    with mock.patch.object(
        action_node,
        "_hmb_available_seedance_shot_catalog",
        return_value=catalog,
    ), mock.patch.object(
        action_node,
        "_apply_seedance_shot_selection",
        side_effect=AssertionError("Action pulse changed Shot selection"),
    ), mock.patch.object(
        action_node,
        "_reconcile_shared_shot_routing",
        side_effect=AssertionError("Action pulse reconciled Shot routing"),
    ), mock.patch.object(
        action_node,
        "_on_refresh_clicked",
        side_effect=run_authoritative_refresh,
    ):
        with mock.patch.object(
            target.GriptapeNodes,
            "EventManager",
            return_value=SimpleNamespace(event_loop=deferred_event_loop),
        ):
            normalized = action_node.before_value_set(widget_parameter, browser_value)
            assert normalized["shot"] == {
                "channel_uuid": channel_uuid,
                "shot_uuid": shot_uuid,
                "number": 2,
                "name": "Action Shot",
            }
            assert normalized["generation"]["job_id"] == authoritative_id
            assert "browser-supplied-job" not in json.dumps(normalized)
            # This assignment models the host commit between before/after hooks.
            # The nonserializable value may update at runtime, but no browser-owned
            # generation identity can become the value that the backend publishes.
            action_node.parameter_values[
                target.SEEDANCE_SHOT_WIDGET_PARAMETER
            ] = normalized
            action_node.after_value_set(widget_parameter, normalized)
        assert refresh_invocations == []
        assert len(deferred_refresh_callbacks) == 1
        deferred_refresh_callbacks.pop()()

    assert refresh_invocations == [(None, None)]
    assert action_bridge.generate_payloads == []
    assert action_bridge.refresh_ids == [authoritative_id]
    assert action_node._hmb_generation_preview_state["phase"] == "running"
    assert action_node._hmb_generation_preview_state["job_id"] == authoritative_id
    assert action_node._hmb_generation_preview_state["action"] == "refresh_existing"
    stored_runtime_widget = action_node.get_parameter_value(
        target.SEEDANCE_SHOT_WIDGET_PARAMETER
    )
    assert stored_runtime_widget["generation"]["job_id"] == authoritative_id
    assert "browser-supplied-job" not in json.dumps(stored_runtime_widget)
    assert widget_parameter.serializable is False
    assert action_node._shot_identity() == identity_before
    assert json.dumps(
        action_node._hmb_shot_catalog_snapshot,
        ensure_ascii=False,
        sort_keys=True,
    ) == catalog_before
    assert action_node.get_parameter_value(
        target.SHOT_AUTOCLAIM_ENABLED_PARAMETER
    ) is autoclaim_before

    # Timeout recovery has the same retrieval-only guarantee and begins with
    # an explicit retrieving state before reporting the current server state.
    timeout_bridge = FakeBrokerBridge(
        [{"status": "running", "job_id": "authoritative-timeout-job-8"}]
    )
    timeout_node = BrokerScriptedNode(timeout_bridge)
    timeout_id = "authoritative-timeout-job-8"
    timeout_node.parameter_output_values["generation_id"] = timeout_id
    timeout_node._hmb_generation_preview_state = target._seedance_generation_preview_value(
        {
            "phase": "timed_out",
            "job_id": timeout_id,
            "action": "refresh_existing",
        }
    )
    timeout_phases: list[str] = []
    timeout_publish = timeout_node._publish_generation_preview

    def observe_timeout_preview(phase: str, **kwargs) -> None:
        timeout_publish(phase, **kwargs)
        timeout_phases.append(timeout_node._hmb_generation_preview_state["phase"])

    timeout_node._publish_generation_preview = observe_timeout_preview
    asyncio.run(timeout_node._refresh_async())
    assert timeout_bridge.generate_payloads == []
    assert timeout_bridge.refresh_ids == [timeout_id]
    assert timeout_phases[0] == "retrieving"
    assert timeout_phases[-1] == "running"
    assert timeout_node._hmb_generation_preview_state["action"] == "refresh_existing"


def assert_refresh_during_submission_contract() -> None:
    bridge = FakeBrokerBridge([])
    node = BrokerScriptedNode(bridge)
    node._generation_run_active.set()
    with mock.patch.object(
        node,
        "_ensure_broker_connected",
        side_effect=AssertionError("Refresh connected before a task ID existed"),
    ), mock.patch.object(
        node,
        "_set_status_results",
        side_effect=AssertionError("Refresh overwrote the active render status"),
    ):
        asyncio.run(node._refresh_async())
    node._generation_run_active.clear()
    assert bridge.account_calls == 0

    observed = BrokerScriptedNode(FakeBrokerBridge([]))

    async def observe_active_run() -> None:
        assert observed._generation_run_active.is_set()

    observed._aprocess_impl = observe_active_run
    asyncio.run(observed.aprocess())
    assert not observed._generation_run_active.is_set()

    refresh_owner = BrokerScriptedNode(FakeBrokerBridge([]))
    refresh_started = threading.Barrier(2)
    refresh_release = threading.Event()
    refresh_body_finished = threading.Event()
    reverse_run_calls = 0

    async def blocking_refresh() -> None:
        refresh_started.wait(timeout=2.0)
        assert refresh_release.wait(2.0)
        refresh_body_finished.set()

    async def count_reverse_run() -> None:
        nonlocal reverse_run_calls
        reverse_run_calls += 1

    refresh_owner._refresh_async = blocking_refresh
    refresh_owner._aprocess_impl = count_reverse_run
    no_engine_loop = SimpleNamespace(event_loop=None, put_event=lambda _event: None)
    with mock.patch.object(
        target.GriptapeNodes, "EventManager", return_value=no_engine_loop
    ):
        try:
            refresh_owner._on_refresh_clicked(None, None)
            refresh_started.wait(timeout=2.0)
            asyncio.run(refresh_owner.aprocess())
            assert reverse_run_calls == 0
            assert refresh_owner._generation_refresh_running is True
            assert not refresh_owner._generation_run_active.is_set()
        finally:
            refresh_release.set()
        assert refresh_body_finished.wait(1.0)
        deadline = time.monotonic() + 1.0
        while (
            refresh_owner._generation_refresh_running
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
    assert refresh_owner._generation_refresh_running is False

    duplicate_node = BrokerScriptedNode(FakeBrokerBridge([]))
    simultaneous_start = threading.Barrier(3)
    winner_entered = threading.Barrier(2)
    winner_release = threading.Event()
    duplicate_calls: list[int] = []
    duplicate_calls_lock = threading.Lock()
    runner_errors: list[BaseException] = []

    async def blocking_run() -> None:
        with duplicate_calls_lock:
            duplicate_calls.append(threading.get_ident())
        winner_entered.wait(timeout=2.0)
        assert winner_release.wait(2.0)

    duplicate_node._aprocess_impl = blocking_run

    def run_simultaneously() -> None:
        try:
            simultaneous_start.wait(timeout=2.0)
            asyncio.run(duplicate_node.aprocess())
        except BaseException as exc:
            runner_errors.append(exc)

    runners = [
        threading.Thread(target=run_simultaneously, daemon=True) for _ in range(2)
    ]
    for runner in runners:
        runner.start()
    try:
        simultaneous_start.wait(timeout=2.0)
        winner_entered.wait(timeout=2.0)
        deadline = time.monotonic() + 1.0
        while (
            all(runner.is_alive() for runner in runners)
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert sum(not runner.is_alive() for runner in runners) == 1
        assert len(duplicate_calls) == 1
        assert duplicate_node._generation_run_active.is_set()
    finally:
        winner_release.set()
        for runner in runners:
            runner.join(timeout=2.0)
    assert not any(runner.is_alive() for runner in runners)
    assert runner_errors == []
    assert len(duplicate_calls) == 1
    assert not duplicate_node._generation_run_active.is_set()

    idle = BrokerScriptedNode(FakeBrokerBridge([]))
    with mock.patch.object(
        idle,
        "_ensure_broker_connected",
        side_effect=AssertionError("Empty idle refresh contacted the Broker"),
    ):
        asyncio.run(idle._refresh_async())
    assert "No FN AI Broker task ID is available" in idle.parameter_output_values[
        "result_details"
    ]


def assert_broker_account_and_button_contract() -> None:
    secrets = {
        "token": "account-token-canary",
        "api_key": "account-provider-key-canary",
        "authorization": "account-authorization-canary",
    }
    bridge = target._HMBAIBrokerBridge()
    safe_me = {
        "display_name": "Broker Artist",
        **secrets,
        "credentials": {"provider_key": "nested-provider-key-canary"},
    }
    with mock.patch.object(
        bridge, "_request_json", return_value=safe_me
    ) as request_json:
        snapshot = bridge.account_snapshot(connect=False)
    assert request_json.call_count == 1
    assert snapshot == target._BrokerAccountSnapshot(
        state="connected",
        connected=True,
        account="Broker Artist",
    )
    snapshot_dump = json.dumps(snapshot.__dict__, ensure_ascii=False)
    for secret in (*secrets.values(), "nested-provider-key-canary"):
        assert secret not in snapshot_dump

    with mock.patch.object(
        bridge,
        "_request_json",
        side_effect=target._BrokerUnavailableError("safe unavailable"),
    ), mock.patch.object(
        target,
        "_broker_device_login",
        side_effect=AssertionError("server outage triggered a login exchange"),
    ):
        try:
            bridge.account_snapshot(connect=True)
        except target._BrokerUnavailableError:
            pass
        else:
            raise AssertionError("Broker outage was treated as a logged-out session")

    trusted_asset_path = "/api/assets/" + ("a" * 43)
    assert bridge.is_trusted_broker_url(
        target.AI_BROKER_SERVER_URL + trusted_asset_path
    )
    assert not bridge.is_trusted_broker_url(
        target.AI_BROKER_SERVER_URL + "/result.mp4"
    )
    assert not bridge.is_trusted_broker_url(
        target.AI_BROKER_SERVER_URL + ".evil.example/result.mp4"
    )
    assert target.HMBSeedanceGeneration._broker_result_url(
        trusted_asset_path
    ) == (target.AI_BROKER_SERVER_URL + trusted_asset_path)

    class BlockingBridge:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()
            self.returned = threading.Event()
            self.calls = 0

        def account_snapshot(self, *, connect: bool):
            assert connect is True
            self.calls += 1
            self.started.set()
            assert self.release.wait(2.0)
            self.returned.set()
            return target._BrokerAccountSnapshot(
                state="connected",
                connected=True,
                account="Threaded Artist",
            )

    blocking_bridge = BlockingBridge()
    detached = target.HMBSeedanceGeneration(name="Detached Broker Button Guard")
    detached._broker_bridge_instance = blocking_bridge
    detached._on_broker_connect_clicked(None, None)
    assert blocking_bridge.calls == 0
    assert detached._broker_action_running is False

    node = RuntimeRegisteredSeedance(name="Broker Button Regression")
    node._broker_bridge_instance = blocking_bridge
    no_engine_loop = SimpleNamespace(event_loop=None, put_event=lambda _event: None)
    with mock.patch.object(
        target.GriptapeNodes, "EventManager", return_value=no_engine_loop
    ):
        started_at = time.monotonic()
        node._on_broker_connect_clicked(None, None)
        assert time.monotonic() - started_at < 0.25
        assert blocking_bridge.started.wait(1.0)
        node._on_broker_connect_clicked(None, None)
        assert blocking_bridge.calls == 1
        blocking_bridge.release.set()
        assert blocking_bridge.returned.wait(1.0)
        deadline = time.monotonic() + 1.0
        while node._broker_action_running and time.monotonic() < deadline:
            time.sleep(0.01)
    assert blocking_bridge.calls == 1
    assert node._broker_action_running is False
    assert node.get_parameter_value("broker_connection_status") == "Connected"
    assert node.get_parameter_value("broker_account") == "Threaded Artist"




class FakeCloudDriver:
    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.deletes: list[Path] = []

    def upload_file(self, *, path: Path, file_content: bytes, timeout: float):
        self.uploads.append(
            {"path": path, "file_content": bytes(file_content), "timeout": timeout}
        )
        return "https://storage.example/reference.mp4?signature=temporary-secret"

    def delete_file(self, path: Path) -> None:
        self.deletes.append(path)


class FakeTosClient:
    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.deletes: list[tuple[str, str]] = []
        self.presigns: list[dict] = []
        self.close_count = 0

    def put_object_from_file(
        self, bucket_name: str, object_key: str, file_path: str, *, content_type: str
    ):
        self.uploads.append(
            {
                "bucket": bucket_name,
                "key": object_key,
                "file_path": file_path,
                "content_type": content_type,
            }
        )
        return SimpleNamespace(status_code=200)

    def pre_signed_url(
        self, method, bucket_name: str, object_key: str, *, expires: int
    ):
        self.presigns.append(
            {
                "method": method,
                "bucket": bucket_name,
                "key": object_key,
                "expires": expires,
            }
        )
        return SimpleNamespace(
            signed_url=(
                f"https://team-bucket.tos-cn-beijing.volces.com/{object_key}"
                "?X-Tos-Signature=temporary-tos-secret"
            )
        )

    def delete_object(self, bucket_name: str, object_key: str) -> None:
        self.deletes.append((bucket_name, object_key))

    def close(self) -> None:
        self.close_count += 1


class FakeTosModule:
    class HttpMethodType:
        Http_Method_Get = "GET"


def assert_local_video_temporary_publication() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        local_video = Path(temporary) / "picker-reference.mp4"
        local_bytes = b"\x00\x00\x00\x18ftypmp42local-reference"
        local_video.write_bytes(local_bytes)
        driver = FakeCloudDriver()
        bridge = FakeBrokerBridge(
            [
                {
                    "job_id": "broker-job-1",
                    "status": "completed",
                    "output": "https://cdn.example/result.mp4",
                }
            ]
        )
        node = BrokerScriptedNode(bridge)
        node.set_parameter_value(
            target.TASK_PARAMETER,
            target.TASK_REFERENCE_TO_VIDEO,
        )
        node.set_parameter_value("prompt", "temporary local publication")
        original_artifact = target.VideoUrlArtifact(str(local_video))
        node.set_parameter_value("reference_video_1", original_artifact)
        node._create_gt_cloud_storage_driver = lambda: driver
        asyncio.run(node.aprocess())

        assert len(driver.uploads) == 1
        upload = driver.uploads[0]
        assert upload["file_content"] == local_bytes
        assert upload["timeout"] == 120.0
        assert upload["path"].parts[0] == "artifact_url_storage"
        assert upload["path"].name == "picker-reference.mp4"
        assert driver.deletes == [upload["path"]]
        assert node.get_parameter_value("reference_video_1") is original_artifact
        post_payload = bridge.generate_payloads[0]
        assert post_payload["video_urls"] == [
            "https://storage.example/reference.mp4?signature=temporary-secret"
        ]
        output_dump = json.dumps(node.parameter_output_values, default=str)
        assert "temporary-secret" not in output_dump

        public_node = target.HMBSeedanceGeneration(
            name="Public Video Bypasses Cloud Regression"
        )
        public_node.set_parameter_value(
            "reference_video_1",
            target.VideoUrlArtifact("https://cdn.example/already-public.mp4"),
        )
        public_node._create_gt_cloud_storage_driver = lambda: (_ for _ in ()).throw(
            AssertionError("Public URL initialized Griptape Cloud storage")
        )
        public_params = public_node._prepare_video_references_for_run(
            public_node._get_parameters()
        )
        assert public_params["video_references"] == [
            "https://cdn.example/already-public.mp4"
        ]

        missing_bridge = FakeBrokerBridge([])
        missing_node = BrokerScriptedNode(missing_bridge)
        missing_node.set_parameter_value(
            target.TASK_PARAMETER,
            target.TASK_REFERENCE_TO_VIDEO,
        )
        missing_node.set_parameter_value("prompt", "missing local video diagnosis")
        missing_path = Path(temporary) / "missing-picker-reference.mp4"
        missing_node.set_parameter_value(
            "reference_video_1", target.VideoUrlArtifact(str(missing_path))
        )
        missing_node._create_gt_cloud_storage_driver = (
            lambda: (_ for _ in ()).throw(
                AssertionError("Missing local video initialized cloud storage")
            )
        )
        try:
            asyncio.run(
                missing_node._process_generation_impl()
            )
        except target.LocalReferenceVideoError as exc:
            assert "does not exist in the active project" in str(exc)
            assert "credentials" not in str(exc)
        else:
            raise AssertionError("Missing local video received a generic upload error")
        assert missing_bridge.generate_payloads == []

        disabled_node = target.HMBSeedanceGeneration(
            name="Disabled Local Publication Regression"
        )
        disabled_node.set_parameter_value("reference_video_1", original_artifact)
        disabled_node.set_parameter_value("auto_publish_local_videos", False)
        try:
            disabled_node._prepare_video_references_for_run(
                disabled_node._get_parameters()
            )
        except ValueError as exc:
            assert "does not accept Base64/local video" in str(exc)
        else:
            raise AssertionError("Disabled local-video publication was bypassed")

        failing_driver = FakeCloudDriver()
        failing_bridge = FakeBrokerBridge([])
        failing_node = BrokerScriptedNode(failing_bridge)
        failing_node.set_parameter_value(
            target.TASK_PARAMETER,
            target.TASK_REFERENCE_TO_VIDEO,
        )
        failing_node.set_parameter_value("prompt", "definitive Broker rejection")
        failing_node.set_parameter_value("reference_video_1", original_artifact)
        failing_node._create_gt_cloud_storage_driver = lambda: failing_driver
        previous_video = target.VideoUrlArtifact(
            "https://local.example/previous-success.mp4"
        )
        previous_last_frame = target.ImageUrlArtifact(
            "https://local.example/previous-last-frame.png"
        )
        failing_node.parameter_output_values["video_url"] = previous_video
        failing_node.parameter_output_values["VIDEO_OUT"] = previous_video
        failing_node.parameter_output_values["last_frame_url"] = previous_last_frame

        failing_bridge.generate_seedance = mock.Mock(
            side_effect=target._BrokerError(
                "FN AI Broker request failed with HTTP 429.",
                status_code=429,
            )
        )
        failure_status_results: list[dict] = []
        failing_node._clear_execution_status = lambda: None
        failing_node._set_status_results = (
            lambda **kwargs: failure_status_results.append(dict(kwargs))
        )

        def raise_reported_failure(exc: BaseException) -> None:
            raise exc

        failing_node._handle_failure_exception = raise_reported_failure
        try:
            asyncio.run(failing_node._aprocess_impl())
        except RuntimeError as exc:
            failure_message = str(exc)
            assert "HTTP 429" in failure_message
            assert "no new render was started" in failure_message
            assert "Existing task ID" not in failure_message
            assert "server render can continue" not in failure_message
            assert "Refresh / Retrieve Result" not in failure_message
        else:
            raise AssertionError("Definitive Broker rejection was accepted")
        assert failing_bridge.generate_seedance.call_count == 1
        provisional_payload = failing_bridge.generate_seedance.call_args.args[0]
        assert provisional_payload["client_request_id"].startswith("hmb-")
        assert failing_node.parameter_output_values["generation_id"] == ""
        assert failing_node.parameter_output_values["generation_status"] == "failed"
        assert failing_node.parameter_output_values["provider_response"] is None
        assert failing_node.parameter_output_values["video_url"] is previous_video
        assert failing_node.parameter_output_values["VIDEO_OUT"] is previous_video
        assert (
            failing_node.parameter_output_values["last_frame_url"]
            is previous_last_frame
        )
        rejection_preview = failing_node._hmb_generation_preview_state
        assert rejection_preview["phase"] == "failed"
        assert rejection_preview["job_id"] == ""
        assert rejection_preview["action"] == "none"
        assert rejection_preview["has_existing_video"] is True
        assert failure_status_results[-1]["was_successful"] is False
        assert "no new render was started" in failure_status_results[-1][
            "result_details"
        ]
        assert len(failing_driver.uploads) == 1
        assert failing_driver.deletes == [failing_driver.uploads[0]["path"]]

        unknown_driver = FakeCloudDriver()
        unknown_bridge = FakeBrokerBridge([])
        unknown_node = BrokerScriptedNode(unknown_bridge)
        unknown_node.set_parameter_value(
            target.TASK_PARAMETER,
            target.TASK_REFERENCE_TO_VIDEO,
        )
        unknown_node.set_parameter_value("prompt", "ambiguous submission outcome")
        unknown_node.set_parameter_value("reference_video_1", original_artifact)
        unknown_node._create_gt_cloud_storage_driver = lambda: unknown_driver
        unknown_bridge.generate_seedance = mock.Mock(
            side_effect=target._BrokerUnavailableError(
                "simulated submission transport loss",
                submission_outcome_unknown=True,
            )
        )
        unknown_deferred_uploads: list[tuple[object, Path]] = []

        def capture_unknown_deferred_cleanup() -> None:
            unknown_deferred_uploads.extend(unknown_node._temporary_video_uploads)
            unknown_node._temporary_video_uploads = []

        unknown_node._defer_temporary_video_upload_cleanup = (
            capture_unknown_deferred_cleanup
        )
        try:
            asyncio.run(unknown_node._process_generation())
        except target._BrokerUnavailableError as exc:
            assert exc.submission_outcome_unknown is True
        else:
            raise AssertionError("Ambiguous submission transport loss was accepted")
        assert unknown_bridge.generate_seedance.call_count == 1
        unknown_generation_id = unknown_node.parameter_output_values["generation_id"]
        assert isinstance(unknown_generation_id, str)
        assert unknown_generation_id.startswith("hmb-")
        assert len(unknown_generation_id) == 36
        submitted_payload = unknown_bridge.generate_seedance.call_args.args[0]
        assert submitted_payload["client_request_id"] == unknown_generation_id
        assert unknown_node.parameter_output_values["generation_status"] == (
            "submission_unknown"
        )
        assert unknown_node.parameter_output_values["provider_response"] == {
            "transport": "fn_ai_broker",
            "id": unknown_generation_id,
            "status": "submission_unknown",
        }
        unknown_preview = unknown_node._hmb_generation_preview_state
        assert unknown_preview["phase"] == "submission_unknown"
        assert unknown_preview["job_id"] == unknown_generation_id
        assert unknown_preview["action"] == "refresh_existing"
        assert unknown_driver.deletes == []
        assert len(unknown_deferred_uploads) == 1
        assert unknown_deferred_uploads[0][1] == unknown_driver.uploads[0]["path"]

        class BlockingSubmissionBridge(FakeBrokerBridge):
            def __init__(self) -> None:
                super().__init__([])
                self.started = threading.Event()
                self.release = threading.Event()
                self.returned = threading.Event()

            def generate_seedance(self, payload: dict, *, timeout: float) -> dict:
                assert timeout > 0
                self.generate_payloads.append(dict(payload))
                self.started.set()
                assert self.release.wait(2.0)
                self.returned.set()
                return {
                    "job_id": "broker-job-cancelled-submit",
                    "status": "pending",
                }

        blocking_driver = FakeCloudDriver()
        blocking_bridge = BlockingSubmissionBridge()
        blocking_node = BrokerScriptedNode(blocking_bridge)
        blocking_node.set_parameter_value(
            target.TASK_PARAMETER,
            target.TASK_REFERENCE_TO_VIDEO,
        )
        blocking_node.set_parameter_value("prompt", "cancelled submit retention")
        blocking_node.set_parameter_value("reference_video_1", original_artifact)
        blocking_node._create_gt_cloud_storage_driver = lambda: blocking_driver
        deferred_uploads: list[tuple[object, Path]] = []

        def capture_deferred_cleanup() -> None:
            deferred_uploads.extend(blocking_node._temporary_video_uploads)
            blocking_node._temporary_video_uploads = []

        blocking_node._defer_temporary_video_upload_cleanup = capture_deferred_cleanup

        async def cancel_started_submission() -> None:
            process = asyncio.create_task(blocking_node._process_generation())
            started = await asyncio.to_thread(blocking_bridge.started.wait, 1.0)
            assert started
            process.cancel()
            try:
                await process
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("Cancellation during submit was swallowed")
            assert process.done()
            assert blocking_node._submission_outcome_unknown is True
            assert blocking_node.parameter_output_values["generation_status"] == (
                "submission_unknown"
            )
            blocking_bridge.release.set()
            returned = await asyncio.to_thread(blocking_bridge.returned.wait, 1.0)
            assert returned

        asyncio.run(cancel_started_submission())
        assert blocking_bridge.returned.is_set()
        assert len(blocking_bridge.generate_payloads) == 1
        cancelled_generation_id = blocking_node.parameter_output_values[
            "generation_id"
        ]
        assert cancelled_generation_id.startswith("hmb-")
        assert blocking_node._submission_outcome_unknown is True
        assert blocking_driver.deletes == []
        assert len(deferred_uploads) == 1
        assert deferred_uploads[0][1] == blocking_driver.uploads[0]["path"]


def assert_tos_local_video_temporary_publication() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        local_video = Path(temporary) / "team-reference.mp4"
        local_video.write_bytes(b"\x00\x00\x00\x18ftypmp42tos-reference")
        tos_client = FakeTosClient()
        bridge = FakeBrokerBridge(
            [
                {
                    "job_id": "broker-job-1",
                    "status": "completed",
                    "output": "https://cdn.example/result.mp4",
                }
            ]
        )
        node = BrokerScriptedNode(bridge)
        node.set_parameter_value(
            target.TASK_PARAMETER,
            target.TASK_REFERENCE_TO_VIDEO,
        )
        node.set_parameter_value("prompt", "temporary TOS publication")
        node.set_parameter_value(
            "reference_video_1", target.VideoUrlArtifact(str(local_video))
        )
        node.set_parameter_value(
            "local_video_upload_service", target.LOCAL_VIDEO_UPLOAD_TOS
        )
        node._create_tos_storage_context = lambda _params: (
            FakeTosModule,
            tos_client,
            "team-bucket",
        )
        asyncio.run(node.aprocess())

        assert len(tos_client.uploads) == 1
        upload = tos_client.uploads[0]
        assert upload["bucket"] == "team-bucket"
        assert upload["file_path"] == str(local_video)
        assert upload["content_type"] == "video/mp4"
        assert upload["key"].startswith("hmb-seedance-temp/")
        assert upload["key"].endswith(".mp4")
        assert "team-reference" not in upload["key"]
        assert tos_client.presigns == [
            {
                "method": "GET",
                "bucket": "team-bucket",
                "key": upload["key"],
                "expires": 86400,
            }
        ]
        assert tos_client.deletes == [("team-bucket", upload["key"])]
        assert tos_client.close_count == 1
        post_payload = bridge.generate_payloads[0]
        reference_url = post_payload["video_urls"][0]
        assert reference_url.startswith(
            "https://team-bucket.tos-cn-beijing.volces.com/"
        )
        assert "temporary-tos-secret" in reference_url
        assert "temporary-tos-secret" not in json.dumps(
            node.parameter_output_values, default=str
        )

        assert (
            target.HMBSeedanceGeneration._normalize_tos_endpoint(
                "https://tos-cn-beijing.volces.com/"
            )
            == "tos-cn-beijing.volces.com"
        )
        for invalid_endpoint in (
            "http://tos-cn-beijing.volces.com",
            "https://example.com",
            "https://tos-cn-beijing.volces.com/private",
        ):
            try:
                target.HMBSeedanceGeneration._normalize_tos_endpoint(
                    invalid_endpoint
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"Unsafe TOS endpoint accepted: {invalid_endpoint}")








class BrokerResultDownloadNode(target.HMBSeedanceGeneration):
    def __init__(self) -> None:
        super().__init__(name="Broker Result Download Regression")
        self.sleeps: list[float] = []

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def assert_broker_result_download_contract() -> None:
    node = BrokerResultDownloadNode()
    original_async_client = target.httpx.AsyncClient
    assert target._is_structurally_valid_mp4(VALID_MP4_BYTES)
    assert not target._is_structurally_valid_mp4(b"\x00\x00\x00\x0cftypmp42")
    assert not target._is_structurally_valid_mp4(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        b"\x00\x00\x00\x10mdat12345678"
    )
    assert not target._is_structurally_valid_mp4(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    )
    assert not target._is_structurally_valid_mp4(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        b"\xff\xff\xff\xffmdat"
    )

    download_requests: list[httpx.Request] = []

    async def download_handler(request: httpx.Request) -> httpx.Response:
        download_requests.append(request)
        return httpx.Response(
            200,
            content=VALID_MP4_BYTES,
            headers={"content-type": "video/mp4"},
        )

    download_transport = httpx.MockTransport(download_handler)

    def download_client_factory(*args, **kwargs):
        kwargs["transport"] = download_transport
        return original_async_client(*args, **kwargs)

    public_dns = [
        (
            target.socket.AF_INET,
            target.socket.SOCK_STREAM,
            target.socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    ]
    with mock.patch.object(
        target.httpx, "AsyncClient", side_effect=download_client_factory
    ), mock.patch.object(target.socket, "getaddrinfo", return_value=public_dns):
        downloaded = asyncio.run(
            node._download_video("https://cdn.example/result.mp4?signature=signed")
        )
    assert downloaded[4:8] == b"ftyp"
    assert len(download_requests) == 1
    assert "authorization" not in download_requests[0].headers
    assert download_requests[0].url.host == "93.184.216.34"
    assert download_requests[0].headers["host"] == "cdn.example"
    assert download_requests[0].extensions["sni_hostname"] == "cdn.example"

    mov_requests: list[httpx.Request] = []

    async def mov_download_handler(request: httpx.Request) -> httpx.Response:
        mov_requests.append(request)
        accept = request.headers.get("accept", "").lower()
        assert "video/quicktime" in accept
        return httpx.Response(
            200,
            content=VALID_MOV_BYTES,
            headers={"content-type": "video/quicktime"},
        )

    mov_transport = httpx.MockTransport(mov_download_handler)

    def mov_client_factory(*args, **kwargs):
        kwargs["transport"] = mov_transport
        return original_async_client(*args, **kwargs)

    with mock.patch.object(
        target.httpx, "AsyncClient", side_effect=mov_client_factory
    ), mock.patch.object(target.socket, "getaddrinfo", return_value=public_dns):
        downloaded_mov = asyncio.run(
            node._download_video("https://cdn.example/result.mov?signature=signed")
        )
    assert downloaded_mov == VALID_MOV_BYTES
    assert len(mov_requests) == 1
    assert "authorization" not in mov_requests[0].headers
    assert mov_requests[0].url.host == "93.184.216.34"
    assert mov_requests[0].headers["host"] == "cdn.example"
    assert mov_requests[0].extensions["sni_hostname"] == "cdn.example"

    # The connection target must remain the address returned by the validated
    # DNS lookup. A second attacker-controlled lookup would return loopback.
    rebind_requests: list[httpx.Request] = []
    dns_calls = 0

    def rebinding_dns(*_args, **_kwargs):
        nonlocal dns_calls
        dns_calls += 1
        if dns_calls == 1:
            return public_dns
        return [
            (
                target.socket.AF_INET,
                target.socket.SOCK_STREAM,
                target.socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            )
        ]

    async def rebind_handler(request: httpx.Request) -> httpx.Response:
        rebind_requests.append(request)
        return httpx.Response(
            200,
            content=VALID_MP4_BYTES,
            headers={"content-type": "video/mp4"},
        )

    rebind_transport = httpx.MockTransport(rebind_handler)

    def rebind_client_factory(*args, **kwargs):
        kwargs["transport"] = rebind_transport
        return original_async_client(*args, **kwargs)

    with mock.patch.object(
        target.httpx, "AsyncClient", side_effect=rebind_client_factory
    ), mock.patch.object(target.socket, "getaddrinfo", side_effect=rebinding_dns):
        rebound_safe = asyncio.run(
            node._download_video("https://rebind.example/result.mp4")
        )
    assert rebound_safe == VALID_MP4_BYTES
    assert dns_calls == 1
    assert len(rebind_requests) == 1
    assert rebind_requests[0].url.host == "93.184.216.34"
    assert rebind_requests[0].headers["host"] == "rebind.example"
    assert rebind_requests[0].extensions["sni_hostname"] == "rebind.example"

    try:
        asyncio.run(node._download_video("http://cdn.example/insecure.mp4"))
    except ValueError as exc:
        assert "must use HTTPS" in str(exc)
    else:
        raise AssertionError("External HTTP result URL was accepted")

    redirect_requests: list[httpx.Request] = []

    async def redirect_handler(request: httpx.Request) -> httpx.Response:
        redirect_requests.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://127.0.0.1/private.mp4"},
        )

    redirect_transport = httpx.MockTransport(redirect_handler)

    def redirect_client_factory(*args, **kwargs):
        kwargs["transport"] = redirect_transport
        return original_async_client(*args, **kwargs)

    with mock.patch.object(
        target.httpx, "AsyncClient", side_effect=redirect_client_factory
    ), mock.patch.object(target.socket, "getaddrinfo", return_value=public_dns):
        try:
            asyncio.run(node._download_video("https://cdn.example/redirect.mp4"))
        except ValueError as exc:
            assert "non-public address" in str(exc)
        else:
            raise AssertionError("Private-network download redirect was followed")
    assert len(redirect_requests) == 1

    class TrustedBrokerResultBridge:
        def __init__(self) -> None:
            self.downloads: list[tuple[str, int, str]] = []

        @staticmethod
        def is_trusted_broker_url(url: str) -> bool:
            return url == target.AI_BROKER_SERVER_URL + "/api/assets/trusted-result"

        def download_trusted_result(
            self,
            url: str,
            *,
            max_bytes: int,
            media_type: str,
        ) -> bytes:
            self.downloads.append((url, max_bytes, media_type))
            return VALID_MP4_BYTES

    trusted_bridge = TrustedBrokerResultBridge()
    trusted_node = BrokerResultDownloadNode()
    trusted_node._get_broker_bridge = lambda: trusted_bridge
    trusted_url = target.AI_BROKER_SERVER_URL + "/api/assets/trusted-result"
    trusted_bytes = asyncio.run(trusted_node._download_broker_video(trusted_url))
    assert trusted_bytes == VALID_MP4_BYTES
    assert trusted_bridge.downloads == [
        (trusted_url, target.MAX_DOWNLOAD_BYTES, "video")
    ]


class AtomicLocalDestination:
    def __init__(self, path: Path, policy) -> None:
        self.location = str(path)
        self._existing_file_policy = policy
        self._create_parents = True
        self._append = False

    def resolve(self) -> str:
        return self.location

    async def awrite_bytes(self, _content: bytes):
        raise AssertionError("Completed MP4 used the non-atomic destination writer")


def assert_last_frame_download_security_contract() -> None:
    """A returned frame is image media, never a serializable signed URL."""

    node = BrokerResultDownloadNode()
    assert hasattr(node, "_download_image")
    original_async_client = target.httpx.AsyncClient
    requests: list[httpx.Request] = []

    async def image_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "authorization" not in request.headers
        assert "image/png" in request.headers.get("accept", "").lower()
        return httpx.Response(
            200,
            content=VALID_PNG_BYTES,
            headers={"content-type": "image/png"},
        )

    image_transport = httpx.MockTransport(image_handler)

    def image_client_factory(*args, **kwargs):
        kwargs["transport"] = image_transport
        return original_async_client(*args, **kwargs)

    public_dns = [
        (
            target.socket.AF_INET,
            target.socket.SOCK_STREAM,
            target.socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    ]
    signed_frame_url = (
        "https://cdn.example/result-last-frame.png?token=frame-token-canary"
    )
    with mock.patch.object(
        target.httpx, "AsyncClient", side_effect=image_client_factory
    ), mock.patch.object(target.socket, "getaddrinfo", return_value=public_dns):
        downloaded = asyncio.run(node._download_image(signed_frame_url))
    assert downloaded == VALID_PNG_BYTES
    assert len(requests) == 1


def assert_mov_and_last_frame_pair_refresh_contract() -> None:
    """Retrieve one existing 2.5 job and replace video/frame state as one pair."""

    signed_video_url = "https://cdn.example/result.mov?token=video-token-canary"
    signed_frame_url = (
        "https://cdn.example/result-last-frame.png?token=frame-token-canary"
    )
    response = {
        "status": "completed",
        "job_id": "existing-format-pair-job",
        "content": {
            "video_url": signed_video_url,
            "last_frame_url": signed_frame_url,
        },
    }
    bridge = FakeBrokerBridge([response])
    node = RuntimeRegisteredSeedance(name="MOV Pair Refresh Regression")
    node._broker_bridge_instance = bridge
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_5)
    node.set_parameter_value("output_format", "mov")
    node.set_parameter_value("return_last_frame", True)
    node.parameter_output_values["generation_id"] = "existing-format-pair-job"
    node._monotonic = lambda: 0.0

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        video_path = root / "seedance-result.mov"
        frame_path = root / "seedance-result-last-frame.png"
        old_video_path = root / "previous-video.mp4"
        old_frame_path = root / "previous-last-frame.png"
        old_video_path.write_bytes(VALID_MP4_BYTES)
        old_frame_path.write_bytes(VALID_PNG_BYTES)
        old_video = target.VideoUrlArtifact(
            value=str(old_video_path), name=old_video_path.name
        )
        old_frame = target.ImageUrlArtifact(
            value=str(old_frame_path), name=old_frame_path.name
        )
        node.parameter_output_values["video_url"] = old_video
        node.parameter_output_values["VIDEO_OUT"] = old_video
        node.parameter_output_values["last_frame_url"] = old_frame
        node._hmb_last_success_video = old_video
        node._hmb_last_success_last_frame_url = old_frame
        node._output_file = FakeOutputFile(
            AtomicLocalDestination(video_path, target.ExistingFilePolicy.OVERWRITE)
        )
        node._last_frame_file = FakeOutputFile(
            AtomicLocalDestination(frame_path, target.ExistingFilePolicy.OVERWRITE)
        )

        pair_observations: list[tuple[object, object]] = []

        async def download_video(url: str, *args, **kwargs) -> bytes:
            del args, kwargs
            assert url == signed_video_url
            return VALID_MOV_BYTES

        async def download_frame(url: str, *args, **kwargs) -> bytes:
            del args, kwargs
            assert url == signed_frame_url
            pair_observations.append(
                (
                    node.parameter_output_values.get("video_url"),
                    node.parameter_output_values.get("last_frame_url"),
                )
            )
            return VALID_PNG_BYTES

        node._download_video = download_video
        node._download_image = download_frame
        node._download_broker_image = download_frame

        with mock.patch.object(target.logger, "warning") as warning_log:
            asyncio.run(node._refresh_async())

        # Refresh is authoritative same-job retrieval. Format or frame options
        # must not turn it into a second billable create-task request.
        assert bridge.generate_payloads == []
        assert bridge.refresh_ids == ["existing-format-pair-job"]
        assert pair_observations == [(old_video, old_frame)]
        assert video_path.read_bytes() == VALID_MOV_BYTES
        assert frame_path.read_bytes() == VALID_PNG_BYTES
        assert not list(root.glob(".*.partial.*"))

        video_artifact = node.parameter_output_values["VIDEO_OUT"]
        frame_artifact = node.parameter_output_values["last_frame_url"]
        assert node.parameter_output_values["video_url"] is video_artifact
        assert type(video_artifact).__name__ == "VideoUrlArtifact"
        assert Path(video_artifact.value) == video_path
        assert type(frame_artifact).__name__ == "ImageUrlArtifact"
        assert Path(frame_artifact.value) == frame_path
        assert node.parameter_output_values["generation_status"] == "succeeded"
        assert node.parameter_output_values["was_successful"] is True

        persistent_state = repr(node.parameter_output_values)
        log_text = repr(warning_log.call_args_list)
        for secret in (
            signed_video_url,
            signed_frame_url,
            "video-token-canary",
            "frame-token-canary",
        ):
            assert secret not in persistent_state
            assert secret not in log_text

    # If optional frame retrieval fails, the paid and verified video remains a
    # success, while the prior video's frame must not be paired with the new one.
    failed_frame_bridge = FakeBrokerBridge([response])
    failed_frame_node = RuntimeRegisteredSeedance(
        name="Optional Last Frame Failure Regression"
    )
    failed_frame_node._broker_bridge_instance = failed_frame_bridge
    failed_frame_node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_5)
    failed_frame_node.set_parameter_value("output_format", "mov")
    failed_frame_node.set_parameter_value("return_last_frame", True)
    failed_frame_node.parameter_output_values[
        "generation_id"
    ] = "existing-format-pair-job"
    failed_frame_node._monotonic = lambda: 0.0

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        video_path = root / "video-survives-frame-failure.mov"
        frame_path = root / "invalid-last-frame.png"
        previous_video = target.VideoUrlArtifact(
            value=str(root / "prior.mp4"), name="prior.mp4"
        )
        previous_frame = target.ImageUrlArtifact(
            value=str(root / "prior.png"), name="prior.png"
        )
        failed_frame_node.parameter_output_values["video_url"] = previous_video
        failed_frame_node.parameter_output_values["VIDEO_OUT"] = previous_video
        failed_frame_node.parameter_output_values["last_frame_url"] = previous_frame
        failed_frame_node._hmb_last_success_video = previous_video
        failed_frame_node._hmb_last_success_last_frame_url = previous_frame
        failed_frame_node._output_file = FakeOutputFile(
            AtomicLocalDestination(video_path, target.ExistingFilePolicy.OVERWRITE)
        )
        failed_frame_node._last_frame_file = FakeOutputFile(
            AtomicLocalDestination(frame_path, target.ExistingFilePolicy.OVERWRITE)
        )

        async def download_video_after_frame_failure(
            url: str, *args, **kwargs
        ) -> bytes:
            del args, kwargs
            assert url == signed_video_url
            return VALID_MOV_BYTES

        async def reject_frame(url: str, *args, **kwargs) -> bytes:
            del args, kwargs
            assert url == signed_frame_url
            return b"not a validated PNG"

        failed_frame_node._download_video = download_video_after_frame_failure
        failed_frame_node._download_image = reject_frame
        failed_frame_node._download_broker_image = reject_frame
        with mock.patch.object(target.logger, "warning") as warning_log:
            asyncio.run(failed_frame_node._refresh_async())

        assert failed_frame_bridge.generate_payloads == []
        assert failed_frame_bridge.refresh_ids == ["existing-format-pair-job"]
        assert video_path.read_bytes() == VALID_MOV_BYTES
        assert not frame_path.exists()
        assert failed_frame_node.parameter_output_values["was_successful"] is True
        assert Path(failed_frame_node.parameter_output_values["VIDEO_OUT"].value) == video_path
        assert failed_frame_node.parameter_output_values.get("last_frame_url") is None
        assert "frame-token-canary" not in repr(
            failed_frame_node.parameter_output_values
        )
        assert "frame-token-canary" not in repr(warning_log.call_args_list)


def assert_atomic_final_output_publication() -> None:
    video_bytes = VALID_MP4_BYTES
    old_bytes = b"previous-complete-output"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        final_path = root / "atomic.mp4"
        destination = AtomicLocalDestination(
            final_path,
            target.ExistingFilePolicy.OVERWRITE,
        )

        final_path.write_bytes(old_bytes)
        real_replace = target.os.replace
        replacement_observations: list[tuple[Path, Path]] = []

        def observed_replace(source, target_path) -> None:
            source_path = Path(source)
            destination_path = Path(target_path)
            assert source_path.parent == destination_path.parent == root
            assert source_path.read_bytes() == video_bytes
            assert final_path.read_bytes() == old_bytes
            replacement_observations.append((source_path, destination_path))
            real_replace(source_path, destination_path)

        with mock.patch.object(target.os, "replace", side_effect=observed_replace):
            saved = asyncio.run(
                target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                    destination,
                    video_bytes,
                )
            )
        assert replacement_observations
        assert final_path.read_bytes() == video_bytes
        assert Path(saved.resolve()) == final_path
        assert not list(root.glob(".*.partial.mp4"))
        assert not list(root.glob(".*.output-probe"))

        final_path.write_bytes(old_bytes)
        commit_started = threading.Event()
        commit_release = threading.Event()

        def blocking_replace(source, target_path) -> None:
            commit_started.set()
            assert commit_release.wait(2.0)
            real_replace(source, target_path)

        async def cancel_during_commit():
            with mock.patch.object(
                target.os,
                "replace",
                side_effect=blocking_replace,
            ):
                publication = asyncio.create_task(
                    target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                        destination,
                        video_bytes,
                    )
                )
                started = await asyncio.to_thread(commit_started.wait, 1.0)
                assert started
                publication.cancel()
                await asyncio.sleep(0.05)
                assert not publication.done(), "Commit cancellation outran os.replace"
                assert final_path.read_bytes() == old_bytes
                commit_release.set()
                return await publication

        cancellation_saved = asyncio.run(cancel_during_commit())
        assert Path(cancellation_saved.resolve()) == final_path
        assert final_path.read_bytes() == video_bytes
        assert not list(root.glob(".*.partial.mp4"))

        final_path.write_bytes(old_bytes)
        with mock.patch.object(
            target.os,
            "replace",
            side_effect=OSError("simulated atomic replacement failure"),
        ):
            try:
                asyncio.run(
                    target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                        destination,
                        video_bytes,
                    )
                )
            except OSError as exc:
                assert "replacement failure" in str(exc)
            else:
                raise AssertionError("Atomic replacement failure was accepted")
        assert final_path.read_bytes() == old_bytes
        assert not list(root.glob(".*.partial.mp4"))

        async def partial_stage_failure(file, content: bytes, **_kwargs):
            Path(file.location).write_bytes(content[:8])
            raise OSError("simulated staging write failure")

        with mock.patch.object(
            target.File,
            "awrite_bytes",
            autospec=True,
            side_effect=partial_stage_failure,
        ):
            try:
                asyncio.run(
                    target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                        destination,
                        video_bytes,
                    )
                )
            except OSError as exc:
                assert "staging write failure" in str(exc)
            else:
                raise AssertionError("Partial staging write failure was accepted")
        assert final_path.read_bytes() == old_bytes
        assert not list(root.glob(".*.partial.mp4"))

        create_new_destination = AtomicLocalDestination(
            final_path,
            target.ExistingFilePolicy.CREATE_NEW,
        )
        created = asyncio.run(
            target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                create_new_destination,
                video_bytes,
            )
        )
        indexed_path = root / "atomic_1.mp4"
        assert final_path.read_bytes() == old_bytes
        assert indexed_path.read_bytes() == video_bytes
        assert Path(created.resolve()) == indexed_path
        assert not list(root.glob(".*.partial.mp4"))

        fail_destination = AtomicLocalDestination(
            final_path,
            target.ExistingFilePolicy.FAIL,
        )
        try:
            asyncio.run(
                target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                    fail_destination,
                    video_bytes,
                )
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("FAIL collision policy overwrote an existing MP4")
        assert final_path.read_bytes() == old_bytes
        assert not list(root.glob(".*.partial.mp4"))

    macro_node = target.HMBSeedanceGeneration(name="Atomic Macro Candidate Regression")
    macro_destination = macro_node._output_file.build_file()
    macro_candidate = next(
        target.HMBSeedanceGeneration._output_destination_candidates(
            macro_destination
        )
    )
    assert macro_candidate.name.endswith("_v001.mp4")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        parsed_macro = ParsedMacro(
            root.as_posix() + "/take_{###}/directory-indexed.mp4"
        )
        metadata = SimpleNamespace(
            situation=SimpleNamespace(variables={"file_extension": "mp4"})
        )
        macro_destination = SimpleNamespace(
            _file=SimpleNamespace(
                _file_path=target.MacroPath(parsed_macro, {}),
                _file_metadata=metadata,
            ),
            _existing_file_policy=target.ExistingFilePolicy.CREATE_NEW,
            _create_parents=True,
            _append=False,
        )
        first_macro_path = root / "take_001" / "directory-indexed.mp4"
        first_macro_path.parent.mkdir(parents=True)
        first_macro_path.write_bytes(old_bytes)
        sidecars: list[tuple[Path, object]] = []
        with mock.patch.object(
            target,
            "write_sidecar",
            side_effect=lambda path, value: sidecars.append((Path(path), value)),
        ):
            macro_saved = asyncio.run(
                target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                    macro_destination,
                    video_bytes,
                )
            )
        second_macro_path = root / "take_002" / "directory-indexed.mp4"
        assert first_macro_path.read_bytes() == old_bytes
        assert second_macro_path.read_bytes() == video_bytes
        assert Path(macro_saved.resolve()) == second_macro_path
        assert sidecars[0][0] == second_macro_path
        assert sidecars[0][1].situation.variables["_index"] == 2
        assert "_index" not in metadata.situation.variables
        assert not list(root.rglob(".*.partial.mp4"))
        assert not list(root.rglob(".*.output-probe"))

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        sidecar_failure_path = root / "sidecar-failure.mp4"
        metadata = SimpleNamespace(
            situation=SimpleNamespace(variables={"file_extension": "mp4"})
        )
        sidecar_failure_destination = SimpleNamespace(
            _file=SimpleNamespace(_file_metadata=metadata),
            _existing_file_policy=target.ExistingFilePolicy.OVERWRITE,
            _create_parents=True,
            _append=False,
            resolve=lambda: str(sidecar_failure_path),
        )
        with mock.patch.object(
            target,
            "write_sidecar",
            side_effect=PermissionError("simulated sidecar failure"),
        ):
            saved_after_sidecar_failure = asyncio.run(
                target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                    sidecar_failure_destination,
                    video_bytes,
                )
            )
        assert Path(saved_after_sidecar_failure.resolve()) == sidecar_failure_path
        assert sidecar_failure_path.read_bytes() == video_bytes
        assert not list(root.glob(".*.partial.mp4"))
        assert not list(root.glob(".*.output-probe"))

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        requested_path = root / "project-parameter.mp4"
        requested_path.write_bytes(old_bytes)
        bridge = FakeBrokerBridge(
            [
                {
                    "status": "completed",
                    "job_id": "broker-job-1",
                    "output": "https://cdn.example/atomic-project-result.mp4",
                }
            ]
        )
        project_node = RuntimeRegisteredSeedance(
            name="Atomic ProjectFileParameter Regression"
        )
        project_node._broker_bridge_instance = bridge
        project_node.set_parameter_value(
            target.TASK_PARAMETER,
            target.TASK_TEXT_ONLY,
        )
        project_node.set_parameter_value("prompt", "atomic project output")
        project_node.set_parameter_value("output_file", str(requested_path))

        async def project_download(_url: str) -> bytes:
            return video_bytes

        async def no_wait(_seconds: float) -> None:
            return None

        project_node._download_video = project_download
        project_node._sleep = no_wait
        project_node._monotonic = lambda: 0.0
        asyncio.run(project_node._process_generation())

        indexed_project_path = root / "project-parameter_1.mp4"
        assert requested_path.read_bytes() == old_bytes
        assert indexed_project_path.read_bytes() == video_bytes
        assert (
            Path(project_node.parameter_output_values["VIDEO_OUT"].value)
            == indexed_project_path
        )
        assert (
            project_node.parameter_output_values["video_url"]
            is project_node.parameter_output_values["VIDEO_OUT"]
        )
        assert indexed_project_path.is_absolute()
        assert indexed_project_path.is_file()
        assert indexed_project_path.suffix == ".mp4"
        assert indexed_project_path.read_bytes() == video_bytes
        assert len(bridge.generate_payloads) == 1
        assert not list(root.glob(".*.partial.mp4"))
        assert not list(root.glob(".*.output-probe"))


def assert_unwritable_output_is_rejected_before_submission() -> None:
    bridge = FakeBrokerBridge([])
    node = BrokerScriptedNode(bridge)
    node.set_parameter_value("prompt", "preflight must precede billing")
    with mock.patch.object(
        target.HMBSeedanceGeneration,
        "_probe_output_parent_writable",
        side_effect=PermissionError("simulated unwritable output parent"),
    ):
        try:
            asyncio.run(node._process_generation())
        except PermissionError as exc:
            assert "unwritable output parent" in str(exc)
        else:
            raise AssertionError("Unwritable output parent reached Broker submission")
    assert bridge.account_calls == 0
    assert bridge.generate_payloads == []


def assert_broker_server_accounting_contract() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_markers = (
        "USAGE" + "_LEDGER_ROOT",
        "USAGE" + "_LOCAL_QUEUE_ROOT",
        "USAGE" + "_PRICE_CNY_PER_MILLION",
        "_prepare_" + "usage_tracking",
        "_record_" + "usage_task",
        "_build_" + "usage_event",
        "_flush_" + "usage_queue",
        r"\\fin-rcomp1\Composite_Team" + "\\" + "00" + "." + "CompSource",
    )
    assert not {marker for marker in forbidden_markers if marker in source}
    assert (
        "The Broker generation request is the sole "
        "usage/quota/accounting authority."
    ) in source

    bridge = FakeBrokerBridge(
        [
            {
                "status": "completed",
                "job_id": "broker-job-1",
                "output": "https://cdn.example/broker-accounting.mp4",
            }
        ]
    )
    node = BrokerScriptedNode(bridge)
    node.set_parameter_value("prompt", "Broker accounting authority regression")
    asyncio.run(node._process_generation())
    assert len(bridge.generate_payloads) == 1
    assert bridge.refresh_ids == ["broker-job-1"]
    assert node.parameter_output_values["generation_status"] == "succeeded"
    assert not {name for name in vars(node) if "usage" in name.casefold()}




assert_constructor_and_public_contract()
assert_seedance_25_output_format_and_last_frame_ui_contract()
assert_only_shot_task_and_reference_state_contract()
assert_image_asset_single_wire_host_contract()
assert_video_picker_single_wire_host_contract()
assert_payload_and_media_contract()
assert_seedance_25_model_contract()
with mock.patch.object(
    target,
    "_validate_decodable_mp4_file",
    side_effect=accept_structural_regression_mp4,
):
    assert_broker_generation_contract()
    assert_generation_preview_status_contract()
    assert_refresh_during_submission_contract()
    assert_broker_account_and_button_contract()
    assert_local_video_temporary_publication()
    assert_tos_local_video_temporary_publication()
    assert_broker_result_download_contract()
    assert_last_frame_download_security_contract()
    assert_mov_and_last_frame_pair_refresh_contract()
    assert_atomic_final_output_publication()
    assert_unwritable_output_is_rejected_before_submission()
    assert_broker_server_accounting_contract()

print("HMB Seedance Generation FN AI Broker regression: PASS")
