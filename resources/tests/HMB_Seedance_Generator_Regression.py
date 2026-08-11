from __future__ import annotations

import asyncio
import base64
import http.server
import io
import importlib.util
import json
import os
import socket
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
image_asset_target = load_image_asset_target()
video_picker_target = load_video_picker_target()

# Most generator cases use a deliberately minimal structural MP4 fixture. Keep
# those tests independent of a host codec binary; the real probe implementation
# is exercised with bounded subprocess mocks below.
REAL_MP4_DECODE_PROBE = target._validate_decodable_mp4_file
target._validate_decodable_mp4_file = lambda _path: None


class FakeDestination:
    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.location = str(
            Path(self._temporary_directory.name) / "volcengine-regression.mp4"
        )
        self.resolved = False
        self.written: bytes | None = None

    def resolve(self) -> str:
        self.resolved = True
        return self.location

    async def awrite_bytes(self, content: bytes):
        self.written = bytes(content)
        return SimpleNamespace(location=self.location, name="volcengine-regression.mp4")


class FakeOutputFile:
    def __init__(self, destination: FakeDestination) -> None:
        self.destination = destination

    def build_file(self) -> FakeDestination:
        return self.destination


class IndexedMacroDestination(FakeDestination):
    def __init__(self, missing_variables: str = "_index") -> None:
        super().__init__()
        self.missing_variables = missing_variables
        self.resolve_attempts = 0
        if missing_variables == "_index":
            parsed_macro = ParsedMacro(
                Path(self._temporary_directory.name).as_posix()
                + "/take_{###}/volcengine-regression.mp4"
            )
            self._file = SimpleNamespace(
                _file_path=target.MacroPath(parsed_macro, {}),
                _file_metadata=None,
            )
            self._existing_file_policy = target.ExistingFilePolicy.CREATE_NEW
            self._create_parents = True
            self._append = False

    def resolve(self) -> str:
        self.resolve_attempts += 1
        raise RuntimeError(
            "Attempted to resolve macro path. Failed because missing required "
            f"variables: {self.missing_variables}"
        )




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


class BrokerScriptedNode(target.HMBSeedanceGeneration):
    def __init__(self, bridge: FakeBrokerBridge) -> None:
        super().__init__(name="HMB Seedance Broker Scripted Regression")
        self.bridge = bridge
        self.destination = FakeDestination()
        self._output_file = FakeOutputFile(self.destination)
        self.downloads: list[str] = []
        self.sleeps: list[float] = []

    def _create_broker_bridge(self):
        return self.bridge

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
    assert target.HMBSeedanceGeneration.__name__ == "HMBSeedanceGeneration"
    retired_class_name = "HMB" + "Seedance" + "20VideoGeneration"
    assert not hasattr(target, retired_class_name)
    assert retired_class_name not in target.__all__
    names = [parameter.name for parameter in node.parameters]
    for required in (
        "exec_in",
        "exec_out",
        "failure",
        "model_id",
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
    assert target.MAX_REFERENCE_IMAGES == 9
    assert target.MAX_VIDEO_REFERENCES == 3
    assert target.MAX_REFERENCE_AUDIO == 3
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
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_0_MINI_MODEL_ID] == (
        "720p",
        "480p",
    )

    image_parameter = node.get_parameter_by_name("reference_images")
    assert type(image_parameter).__name__ == "Parameter"
    assert not isinstance(image_parameter, target.ParameterList)
    assert image_parameter.type == "list[str]"
    assert image_parameter.input_types == [
        "list[str]",
        "list[ImageUrlArtifact]",
        "list[ImageArtifact]",
        "list[BytePlusImageAssetReference]",
    ]
    assert image_parameter.ui_options["display_name"] == "Reference Images"
    assert "expander" not in image_parameter.ui_options
    assert image_parameter.hide_property is True
    assert image_parameter.allowed_modes == {target.ParameterMode.INPUT}

    # The Asset Library source and Seedance target advertise an exact list[str]
    # match, so the complete ordered selection uses one graph connection.
    asset_contract_node = image_asset_target.DataNode(name="Image Asset Port Contract")
    image_asset_target._add_media_output(asset_contract_node)
    asset_media_output = asset_contract_node.get_parameter_by_name(
        image_asset_target.MEDIA_OUTPUT_PARAMETER
    )
    assert asset_media_output.output_type == "list[str]"
    assert asset_media_output.output_type in image_parameter.input_types

    for index in range(1, 4):
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
    assert video_list_parameter.type == "list[str]"
    assert video_list_parameter.hide is False
    assert video_list_parameter.ui_options["display_name"] == "Reference Videos"
    assert video_list_parameter.allowed_modes == {target.ParameterMode.INPUT}
    assert video_list_parameter.hide_property is True
    assert video_list_parameter.input_types == [
        "list[str]",
        "list[VideoUrlArtifact]",
        "list[BytePlusVideoAssetReference]",
    ]

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
    assert audio_parameter._max_items == 3
    assert node.get_parameter_value("auto_publish_local_videos") is True
    assert node.get_parameter_value("model_id") == target.MODEL_NAME_SEEDANCE_2_0
    assert node.get_parameter_value("resolution") == "1080p"
    assert (
        node.get_parameter_value("input_mode")
        == target.INPUT_MODE_MULTIMODAL_REFERENCES
    )
    assert node.get_parameter_by_name("input_mode").ui_options[
        "simple_dropdown"
    ] == [
        target.INPUT_MODE_TEXT_ONLY,
        target.INPUT_MODE_FIRST_LAST_FRAME,
        target.INPUT_MODE_MULTIMODAL_REFERENCES,
    ]
    assert target.BROKER_SUPPORTED_MODEL_IDS == frozenset(
        {
            target.SEEDANCE_2_0_MODEL_ID,
            target.SEEDANCE_2_0_FAST_MODEL_ID,
            target.SEEDANCE_2_0_MINI_MODEL_ID,
        }
    )
    assert target.MODEL_DEFAULT_RESOLUTIONS == {
        target.SEEDANCE_2_0_MODEL_ID: "1080p",
        target.SEEDANCE_2_0_FAST_MODEL_ID: "720p",
        target.SEEDANCE_2_0_MINI_MODEL_ID: "720p",
    }
    model_choices = node.get_parameter_by_name("model_id").ui_options[
        "simple_dropdown"
    ]
    assert model_choices == [
        target.MODEL_NAME_SEEDANCE_2_0,
        target.MODEL_NAME_SEEDANCE_2_0_FAST,
        target.MODEL_NAME_SEEDANCE_2_0_MINI,
    ]
    assert node.get_parameter_by_name("resolution").ui_options[
        "simple_dropdown"
    ] == ["4k", "1080p", "720p", "480p"]
    assert node.get_parameter_value("ratio") == "adaptive"
    assert node.get_parameter_by_name("ratio").ui_options["simple_dropdown"] == list(
        target.RATIOS
    )
    assert node.get_parameter_value("duration") == 5
    assert node.get_parameter_by_name("duration").ui_options["simple_dropdown"] == [
        -1,
        *range(4, 16),
    ]
    assert node.get_parameter_value("generate_audio") is False
    assert node.get_parameter_value("resume_generation_id") == ""
    assert node.get_parameter_value("watermark") is False
    assert node.get_parameter_value("return_last_frame") is False
    assert node.get_parameter_value("execution_expires_after") == 172800
    assert node.get_parameter_value("priority") == 0
    assert node.get_parameter_value("poll_interval_seconds") == 30
    assert node.get_parameter_value("generation_timeout_seconds") == 3600
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_0_FAST)
    assert node.get_parameter_value("resolution") == "720p"
    assert node.get_parameter_by_name("resolution").ui_options[
        "simple_dropdown"
    ] == ["720p", "480p"]
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_0_MINI)
    assert node.get_parameter_by_name("resolution").ui_options[
        "simple_dropdown"
    ] == ["720p", "480p"]
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_0)
    assert node.get_parameter_by_name("resolution").ui_options[
        "simple_dropdown"
    ] == ["4k", "1080p", "720p", "480p"]
    assert (
        node.get_parameter_value("local_video_upload_service")
        == target.LOCAL_VIDEO_UPLOAD_GRIPTAPE
    )
    assert node.get_parameter_value("tos_region") == "cn-beijing"
    assert node.get_parameter_value("tos_endpoint") == "tos-cn-beijing.volces.com"
    assert node.get_parameter_value("tos_url_validity_seconds") == 86400
    assert node.get_parameter_by_name("tos_region").hide is True
    assert node.get_parameter_value("generate_audio") is False
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
    assert [
        parameter.name
        for parameter in (video_parameter, video_alias)
        if target.ParameterMode.OUTPUT in parameter.allowed_modes
    ] == ["VIDEO_OUT"]
    refresh_parameter = node.get_parameter_by_name("generation_refresh")
    assert type(refresh_parameter).__name__ == "ParameterButton"
    assert refresh_parameter.label == "Refresh / Retrieve Result"

    root_children = list(node.root_ui_element.children)
    root_names = [element.name for element in root_children]
    assert root_names[-2:] == ["Status", "AI Broker"]
    broker_group = root_children[-1]
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
    ):
        assert forbidden_symbol not in source
    assert "CGTeamwork" not in source
    assert '"/api/device/start"' in source
    assert '"/api/device/token"' in source
    assert 'headers["Idempotency-Key"]' in source
    assert ("_Base" + "Seedance" + "20") not in source
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
    assert "MODEL_DEFAULT_RESOLUTIONS" in source
    assert "MODEL_RESOLUTIONS[SEEDANCE_2_0_MODEL_ID]" in source


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
        assert payload["aspect_ratio"] == "16:9"
        assert payload["duration_seconds"] == 8
        assert payload["generate_audio"] is True
        assert payload["watermark"] is False
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
    try:
        node._validate_parameters(gap_params)
    except ValueError as exc:
        assert "reference_video_2 requires reference_video_1" in str(exc)
    else:
        raise AssertionError("A gap before reference_video_2 was accepted")

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
    assert serialized_list_node.get_parameter_value("reference_audio") == []
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

    for supported_model in (
        target.SEEDANCE_2_0_MODEL_ID,
        target.SEEDANCE_2_0_MINI_MODEL_ID,
    ):
        params = node._get_parameters()
        params.update(
            {
                "model_id": supported_model,
                "resolution": (
                    "4k"
                    if supported_model == target.SEEDANCE_2_0_MODEL_ID
                    else "720p"
                ),
                "prompt": "supported Broker model",
            }
        )
        assert node._build_broker_payload(params)["model"] == supported_model

    unsupported = node._get_parameters()
    unsupported.update(
        {
            "model_id": "doubao-seedance-2-0-unknown",
            "resolution": "720p",
            "prompt": "unsupported Broker model",
        }
    )
    try:
        node._build_broker_payload(unsupported)
    except ValueError as exc:
        assert "Unsupported Volcengine Seedance model" in str(exc)
    else:
        raise AssertionError("Unknown Broker model was accepted")

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

    bridge_contract = target._HMBAIBrokerBridge()
    settings_error = target.urllib.error.HTTPError(
        "http://broker.invalid/api/v1/generate/video",
        400,
        "Bad Request",
        {},
        io.BytesIO(b'{"detail":"resolution is invalid","token":"secret-canary"}'),
    )
    safe_error_message = bridge_contract._safe_http_error_message(settings_error)
    assert "generation settings" in safe_error_message
    assert "secret-canary" not in safe_error_message

    oversized_error = target.urllib.error.HTTPError(
        "http://broker.invalid/api/v1/generate/video",
        413,
        "Payload Too Large",
        {},
        io.BytesIO(
            b'{"error_code":"request_body_too_large","token":"secret-canary"}'
        ),
    )
    oversized_message = bridge_contract._safe_http_error_message(oversized_error)
    assert "oversized reference-media request" in oversized_message
    assert "secret-canary" not in oversized_message

    class ExpiredOpener:
        @staticmethod
        def open(_request, *, timeout: float):
            assert timeout > 0
            raise target.urllib.error.HTTPError(
                "http://broker.invalid/api/v1/jobs/expired-job/refresh",
                410,
                "Gone",
                {},
                io.BytesIO(
                    b'{"status":"expired","job_id":"expired-job"}'
                ),
            )

    expired_bridge = target._HMBAIBrokerBridge(opener=ExpiredOpener())
    with mock.patch.object(target, "_broker_load_token", return_value="saved-token"):
        expired_result = expired_bridge._request_json(
            "POST",
            "/api/v1/jobs/expired-job/refresh",
            payload=None,
            timeout=30,
        )
    assert expired_result == {
        "status": "expired",
        "job_id": "expired-job",
        "_http_status": 410,
    }

    fast_payload = {
        "provider": "volcengine_ark",
        "model": target.SEEDANCE_2_0_FAST_MODEL_ID,
        "prompt": "Broker schema regression",
        "input_mode": target.INPUT_MODE_MULTIMODAL_REFERENCES,
        "duration_seconds": 5,
        "quality": "720p",
        "resolution": "1280x720",
        "aspect_ratio": "adaptive",
        "generate_audio": False,
        "watermark": False,
        "web_search": False,
        "content_filter": True,
        "return_last_frame": False,
        "execution_expires_after": 172800,
        "client_request_id": "hmb-schema-request-1",
    }
    with mock.patch.object(
        bridge_contract,
        "_request_json",
        return_value={"status": "pending", "job_id": "schema-job-1"},
    ) as request_json:
        bridge_contract.generate_seedance(fast_payload, timeout=30)
    submitted = request_json.call_args.kwargs["payload"]
    assert set(submitted) == {
        "provider",
        "model",
        "prompt",
        "input_mode",
        "duration_seconds",
        "quality",
        "resolution",
        "aspect_ratio",
        "generate_audio",
        "watermark",
        "web_search",
        "content_filter",
        "return_last_frame",
        "execution_expires_after",
        "client_request_id",
    }
    assert "input_mode" in submitted
    assert "return_last_frame" in submitted
    assert "execution_expires_after" in submitted
    assert submitted["client_request_id"] == "hmb-schema-request-1"
    assert request_json.call_args.kwargs["idempotency_key"] == (
        "hmb-schema-request-1"
    )

    framed_fast_payload = dict(fast_payload)
    framed_fast_payload.update(
        {
            "input_mode": target.INPUT_MODE_FIRST_LAST_FRAME,
            "first_frame": ["https://cdn.example/first.png"],
            "last_frame": ["https://cdn.example/last.png"],
            "return_last_frame": True,
        }
    )
    with mock.patch.object(
        bridge_contract,
        "_request_json",
        return_value={"status": "pending", "job_id": "schema-job-2"},
    ) as request_json:
        bridge_contract.generate_seedance(framed_fast_payload, timeout=30)
    fast_submitted = request_json.call_args.kwargs["payload"]
    for field in (
        "input_mode",
        "first_frame",
        "last_frame",
        "return_last_frame",
        "execution_expires_after",
    ):
        assert field in fast_submitted

    for supported_model, quality in (
        (target.SEEDANCE_2_0_MODEL_ID, "4k"),
        (target.SEEDANCE_2_0_MINI_MODEL_ID, "720p"),
    ):
        valid = dict(fast_payload)
        valid["model"] = supported_model
        valid["quality"] = quality
        valid["prompt"] = "required prompt"
        if supported_model == target.SEEDANCE_2_0_MODEL_ID:
            valid["priority"] = 1
        with mock.patch.object(
            bridge_contract,
            "_request_json",
            return_value={"status": "pending", "job_id": "all-models-job"},
        ) as request_json:
            bridge_contract.generate_seedance(valid, timeout=30)
        submitted = request_json.call_args.kwargs["payload"]
        assert submitted["model"] == supported_model
        assert submitted["quality"] == quality
        assert ("priority" in submitted) is (
            supported_model == target.SEEDANCE_2_0_MODEL_ID
        )

    media_only_mini = dict(fast_payload)
    media_only_mini.update(
        {
            "model": target.SEEDANCE_2_0_MINI_MODEL_ID,
            "prompt": "",
            "image_urls": ["data:image/png;base64,AA=="],
        }
    )
    with mock.patch.object(
        bridge_contract,
        "_request_json",
        return_value={"status": "pending", "job_id": "media-only-job"},
    ) as request_json:
        bridge_contract.generate_seedance(media_only_mini, timeout=30)
    assert request_json.call_args.kwargs["payload"]["prompt"] == ""
    assert request_json.call_args.kwargs["payload"]["image_urls"]

    rejected_payloads = []
    priority_payload = dict(fast_payload)
    priority_payload["priority"] = 1
    rejected_payloads.append(priority_payload)
    for invalid in rejected_payloads:
        with mock.patch.object(
            bridge_contract,
            "_request_json",
            side_effect=AssertionError("invalid payload reached FN AI Broker"),
        ):
            try:
                bridge_contract.generate_seedance(invalid, timeout=30)
            except target._BrokerProtocolError:
                pass
            else:
                raise AssertionError("Invalid Broker payload was accepted")

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
    node.set_parameter_value("prompt", "Broker-only Seedance regression")
    assert not hasattr(node, "_get_" + "api_key")
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
    assert payload["resolution"] == "1280x720"
    assert payload["aspect_ratio"] == "adaptive"
    assert payload["web_search"] is False
    assert payload["content_filter"] is True
    assert target._TASK_ID_PATTERN.fullmatch(payload["client_request_id"])
    portrait = BrokerScriptedNode(FakeBrokerBridge([]))
    portrait_params = portrait._get_parameters()
    portrait_params.update({"prompt": "portrait", "ratio": "9:16"})
    assert portrait._build_broker_payload(portrait_params)["resolution"] == (
        "720x1280"
    )
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

    class SameKeyRetryBridge(FakeBrokerBridge):
        def refresh_job(self, job_id: str, *, timeout: float = 60) -> dict:
            assert timeout > 0
            self.refresh_ids.append(job_id)
            raise target._BrokerError("not registered", status_code=404)

        def generate_seedance(self, payload: dict, *, timeout: float) -> dict:
            assert timeout > 0
            self.generate_payloads.append(dict(payload))
            return {
                "status": "pending",
                "job_id": payload["client_request_id"],
            }

    stable_request_id = "hmb-stable-request-123"
    retry_bridge = SameKeyRetryBridge([])
    retry_node = BrokerScriptedNode(retry_bridge)
    retry_payload = {
        "provider": "volcengine_ark",
        "model": target.SEEDANCE_2_0_MODEL_ID,
        "prompt": "same idempotent request",
        "client_request_id": stable_request_id,
    }
    retry_node._last_broker_payload = dict(retry_payload)
    retry_node.parameter_output_values["generation_id"] = stable_request_id
    retry_node.parameter_output_values["generation_status"] = "submission_unknown"
    asyncio.run(retry_node._refresh_async())
    assert retry_bridge.refresh_ids == [stable_request_id]
    assert retry_bridge.generate_payloads == [retry_payload]
    assert retry_node.parameter_output_values["generation_id"] == stable_request_id
    assert retry_node.parameter_output_values["generation_status"] == "queued"
    assert retry_node.parameter_output_values["was_successful"] is False
    assert retry_node._execution_succeeded is None
    assert "display_name" not in (
        retry_node.status_component.get_parameter_group().ui_options
    )
    assert "never starts a duplicate render" in retry_node.parameter_output_values[
        "result_details"
    ]

    failed_bridge = FakeBrokerBridge(
        [{"status": "failed", "job_id": "broker-refresh-failed-4"}]
    )
    failed_refresh = BrokerScriptedNode(failed_bridge)
    failed_refresh.parameter_output_values["generation_id"] = (
        "broker-refresh-failed-4"
    )
    asyncio.run(failed_refresh._refresh_async())
    assert failed_refresh.parameter_output_values["generation_status"] == "failed"
    assert failed_refresh.parameter_output_values["was_successful"] is False
    assert failed_refresh._execution_succeeded is False
    assert "display_name" in (
        failed_refresh.status_component.get_parameter_group().ui_options
    )

    submission_unknown_response = {
        "status": "failed",
        "job_id": "job-submission-unknown-5",
        "provider_job_id": "",
        "error_code": "submission_unknown",
        "error": "server detail must not be copied into public node state",
        "message": "server guidance must not be copied into public node state",
        "terminal": True,
        "resubmit_allowed": False,
        "recovery_action": "contact_admin",
        "token": FakeBrokerBridge.SECRET_VALUES[0],
    }
    normalized_unknown = (
        target.HMBSeedanceGeneration._normalize_broker_task(
            submission_unknown_response
        )
    )
    assert normalized_unknown == {
        "id": "job-submission-unknown-5",
        "status": "failed",
        "broker_status": "failed",
        "error_code": "submission_unknown",
        "terminal": True,
        "resubmit_allowed": False,
        "recovery_action": "contact_admin",
        "provider_task_registered": False,
    }

    class TerminalSubmissionUnknownBridge(FakeBrokerBridge):
        def generate_seedance(self, payload: dict, *, timeout: float) -> dict:
            assert timeout > 0
            self.generate_payloads.append(dict(payload))
            response = dict(submission_unknown_response)
            response["job_id"] = payload["client_request_id"]
            return response

    terminal_bridge = TerminalSubmissionUnknownBridge([])
    terminal_node = BrokerScriptedNode(terminal_bridge)
    terminal_node.set_parameter_value("prompt", "terminal submission regression")
    try:
        asyncio.run(terminal_node._aprocess_impl())
    except RuntimeError as exc:
        terminal_message = str(exc)
    else:
        raise AssertionError("A terminal submission_unknown response was accepted")
    assert terminal_node.parameter_output_values["generation_status"] == "failed"
    assert terminal_node.parameter_output_values["provider_response"] == {
        "transport": "fn_ai_broker",
        "id": terminal_node.parameter_output_values["generation_id"],
        "status": "failed",
        "error_code": "submission_unknown",
        "terminal": True,
        "resubmit_allowed": False,
        "recovery_action": "contact_admin",
        "provider_task_registered": False,
    }
    assert "Broker error code: submission_unknown" in terminal_message
    assert "no provider task ID was returned" in terminal_message
    assert "automatic resubmission is disabled" in terminal_message
    assert "This Broker job is terminal" in terminal_message
    assert "server render can continue" not in terminal_message
    assert "server detail must not be copied" not in terminal_message
    assert "server guidance must not be copied" not in terminal_message
    assert FakeBrokerBridge.SECRET_VALUES[0] not in terminal_message
    assert terminal_bridge.refresh_ids == []
    assert len(terminal_bridge.generate_payloads) == 1

    class OfflineTerminalRefreshBridge(FakeBrokerBridge):
        def refresh_job(self, job_id: str, *, timeout: float = 60) -> dict:
            assert timeout > 0
            self.refresh_ids.append(job_id)
            raise target._BrokerUnavailableError("offline terminal refresh")

    offline_bridge = OfflineTerminalRefreshBridge([])
    offline_terminal = BrokerScriptedNode(offline_bridge)
    offline_terminal.parameter_output_values.update(
        {
            "generation_id": "job-submission-unknown-offline-6",
            "generation_status": "failed",
            "provider_response": {
                "transport": "fn_ai_broker",
                "id": "job-submission-unknown-offline-6",
                "status": "failed",
                "error_code": "submission_unknown",
                "terminal": True,
                "resubmit_allowed": False,
                "recovery_action": "contact_admin",
                "provider_task_registered": False,
            },
        }
    )
    asyncio.run(offline_terminal._refresh_async())
    offline_message = offline_terminal.parameter_output_values["result_details"]
    assert offline_bridge.refresh_ids == ["job-submission-unknown-offline-6"]
    assert offline_bridge.generate_payloads == []
    assert "known terminal job" in offline_message
    assert "did not resume, restart, or duplicate" in offline_message
    assert "may still be rendering" not in offline_message
    assert "automatic resubmission is disabled" in offline_message


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


def assert_broker_direct_transport_resilience_contract() -> None:
    assert target.AI_BROKER_DEVICE_START_BACKOFF_SECONDS == (0.0, 0.5, 1.5)
    assert target.AI_BROKER_DEVICE_AUTH_TIMEOUT_SECONDS == 5 * 60
    assert target.AI_BROKER_DEVICE_POLL_MAX_CONSECUTIVE_TRANSPORT_ERRORS == 3
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "urllib.request.install_opener" not in source

    class CountingOriginHandler(http.server.BaseHTTPRequestHandler):
        request_count = 0

        def do_GET(self) -> None:
            type(self).request_count += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def log_message(self, _format: str, *_args) -> None:
            return None

    class CountingProxyHandler(http.server.BaseHTTPRequestHandler):
        request_count = 0

        def do_GET(self) -> None:
            type(self).request_count += 1
            self.send_response(502)
            self.end_headers()

        def log_message(self, _format: str, *_args) -> None:
            return None

    origin_server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), CountingOriginHandler
    )
    proxy_server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), CountingProxyHandler
    )
    origin_thread = threading.Thread(target=origin_server.serve_forever, daemon=True)
    proxy_thread = threading.Thread(target=proxy_server.serve_forever, daemon=True)
    origin_thread.start()
    proxy_thread.start()
    try:
        proxy_url = f"http://127.0.0.1:{proxy_server.server_port}"
        direct_host = "broker-direct-regression.invalid"
        direct_url = f"http://{direct_host}:{origin_server.server_port}"
        original_getaddrinfo = socket.getaddrinfo

        def regression_getaddrinfo(host, *args, **kwargs):
            if host == direct_host:
                host = "127.0.0.1"
            return original_getaddrinfo(host, *args, **kwargs)

        proxy_environment = {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "https_proxy": proxy_url,
        }
        with mock.patch.dict(os.environ, proxy_environment, clear=False):
            for name in ("NO_PROXY", "no_proxy"):
                os.environ.pop(name, None)
            assert target.urllib.request.getproxies()["http"] == proxy_url
            with mock.patch.object(
                target.urllib.request,
                "build_opener",
                wraps=target.urllib.request.build_opener,
            ) as build_opener:
                opener = target._broker_build_opener()
            handlers = build_opener.call_args.args
            assert len(handlers) == 2
            assert isinstance(handlers[0], target.urllib.request.ProxyHandler)
            assert handlers[0].proxies == {}
            assert isinstance(handlers[1], target._BrokerNoRedirectHandler)
            with mock.patch.object(
                socket, "getaddrinfo", side_effect=regression_getaddrinfo
            ):
                with opener.open(direct_url + "/api/health", timeout=2) as response:
                    assert response.status == 200
                    assert json.loads(response.read()) == {"status": "ok"}
        assert CountingOriginHandler.request_count == 1
        assert CountingProxyHandler.request_count == 0
    finally:
        origin_server.shutdown()
        proxy_server.shutdown()
        origin_server.server_close()
        proxy_server.server_close()
        origin_thread.join(timeout=2)
        proxy_thread.join(timeout=2)

    class JsonResponse(io.BytesIO):
        def __init__(self, status: int, payload) -> None:
            super().__init__(json.dumps(payload).encode("utf-8"))
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()
            return False

    class ScriptedOpener:
        def __init__(self, events: list) -> None:
            self.events = list(events)
            self.requests: list[dict] = []

        def open(self, request, *, timeout: float):
            assert 0 < timeout <= 10
            self.requests.append(
                {
                    "url": request.full_url,
                    "body": json.loads(request.data or b"{}"),
                    "headers": {
                        key.lower(): value for key, value in request.header_items()
                    },
                }
            )
            if not self.events:
                raise AssertionError("Unexpected extra Broker transport request")
            event = self.events.pop(0)
            if isinstance(event, BaseException):
                raise event
            status, payload = event
            return JsonResponse(status, payload)

    server_url = target.AI_BROKER_SERVER_URL

    def start_payload(code: str, secret: str) -> dict:
        return {
            "device_code": code,
            "device_secret": secret,
            "verification_url": server_url + "/?device=" + code,
        }

    retry_code = "device-code-start-retry"
    retry_secret = "device-secret-start-retry-canary"
    retry_opener = ScriptedOpener(
        [
            TimeoutError("start-secret-canary"),
            target.urllib.error.URLError(OSError(10060, "proxy-secret-canary")),
            (201, start_payload(retry_code, retry_secret)),
            (200, {"access_token": "permanent-token-after-start-retry"}),
        ]
    )
    with mock.patch.object(
        target, "_broker_build_opener", return_value=retry_opener
    ) as opener_factory, mock.patch.object(
        target.webbrowser, "open", return_value=True
    ) as retry_browser, mock.patch.object(
        target, "_broker_save_token"
    ) as retry_save, mock.patch.object(
        target.time, "sleep"
    ) as retry_sleep, mock.patch.object(target.logger, "warning"):
        assert target._broker_device_login() == {"status": "connected"}
    opener_factory.assert_called_once_with()
    assert [request["url"] for request in retry_opener.requests].count(
        server_url + "/api/device/start"
    ) == 3
    assert [request["url"] for request in retry_opener.requests].count(
        server_url + "/api/device/token"
    ) == 1
    assert retry_sleep.call_args_list == [mock.call(0.5), mock.call(1.5)]
    retry_browser.assert_called_once_with(
        server_url + "/?device=" + retry_code,
        new=2,
        autoraise=True,
    )
    retry_save.assert_called_once_with("permanent-token-after-start-retry")

    poll_code = "device-code-poll-recovery"
    poll_secret = "device-secret-poll-recovery-canary"
    poll_opener = ScriptedOpener(
        [
            (201, start_payload(poll_code, poll_secret)),
            target.urllib.error.URLError(OSError(10054, "poll-secret-one")),
            OSError(10060, "poll-secret-two"),
            (202, {"status": "pending"}),
            (200, {"access_token": "permanent-token-after-poll-recovery"}),
        ]
    )
    with mock.patch.object(
        target.webbrowser, "open", return_value=True
    ) as poll_browser, mock.patch.object(
        target, "_broker_save_token"
    ) as poll_save, mock.patch.object(
        target.time, "sleep"
    ) as poll_sleep, mock.patch.object(target.logger, "warning"):
        assert target._broker_device_login(opener=poll_opener) == {
            "status": "connected"
        }
    start_requests = [
        request
        for request in poll_opener.requests
        if request["url"].endswith("/api/device/start")
    ]
    token_requests = [
        request
        for request in poll_opener.requests
        if request["url"].endswith("/api/device/token")
    ]
    assert len(start_requests) == 1
    assert len(token_requests) == 4
    assert all(
        request["body"]
        == {"device_code": poll_code, "device_secret": poll_secret}
        for request in token_requests
    )
    assert all("/api/v1/generate/" not in request["url"] for request in poll_opener.requests)
    assert poll_sleep.call_count == 3
    poll_browser.assert_called_once_with(
        server_url + "/?device=" + poll_code,
        new=2,
        autoraise=True,
    )
    poll_save.assert_called_once_with("permanent-token-after-poll-recovery")

    failed_poll_code = "device-code-bounded-poll"
    failed_poll_secret = "device-secret-bounded-poll-canary"
    failed_poll_opener = ScriptedOpener(
        [
            (201, start_payload(failed_poll_code, failed_poll_secret)),
            TimeoutError("poll-failure-one"),
            target.urllib.error.URLError(OSError(10054, "poll-failure-two")),
            OSError(10060, "poll-failure-three"),
        ]
    )
    with mock.patch.object(
        target.webbrowser, "open", return_value=True
    ) as failed_poll_browser, mock.patch.object(
        target, "_broker_save_token"
    ) as failed_poll_save, mock.patch.object(
        target.time, "sleep"
    ), mock.patch.object(target.logger, "warning"):
        failed_at = time.monotonic()
        try:
            target._broker_device_login(opener=failed_poll_opener)
        except target._BrokerUnavailableError as exc:
            assert "polling was interrupted" in str(exc)
        else:
            raise AssertionError("Unbounded device-token polling was accepted")
        assert time.monotonic() - failed_at < 1.0
    assert len(failed_poll_opener.requests) == 4
    assert sum(
        request["url"].endswith("/api/device/start")
        for request in failed_poll_opener.requests
    ) == 1
    assert sum(
        request["url"].endswith("/api/device/token")
        for request in failed_poll_opener.requests
    ) == target.AI_BROKER_DEVICE_POLL_MAX_CONSECUTIVE_TRANSPORT_ERRORS
    failed_poll_browser.assert_called_once()
    failed_poll_save.assert_not_called()

    failed_start_opener = ScriptedOpener(
        [
            TimeoutError("bounded-start-one"),
            target.urllib.error.URLError(OSError(10060, "bounded-start-two")),
            OSError(10013, "bounded-start-three"),
        ]
    )
    with mock.patch.object(
        target.webbrowser,
        "open",
        side_effect=AssertionError("Failed start opened a browser"),
    ), mock.patch.object(target.time, "sleep") as failed_start_sleep, mock.patch.object(
        target.logger, "warning"
    ):
        try:
            target._broker_device_login(opener=failed_start_opener)
        except target._BrokerUnavailableError as exc:
            assert "authorization service is unavailable" in str(exc)
        else:
            raise AssertionError("Unbounded device-start retry was accepted")
    assert len(failed_start_opener.requests) == len(
        target.AI_BROKER_DEVICE_START_BACKOFF_SECONDS
    )
    assert all(
        request["url"].endswith("/api/device/start")
        for request in failed_start_opener.requests
    )
    assert failed_start_sleep.call_args_list == [mock.call(0.5), mock.call(1.5)]

    http_error = target.urllib.error.HTTPError(
        server_url + "/api/device/start",
        503,
        "Service Unavailable",
        {},
        io.BytesIO(b'{"device_secret":"must-not-be-retried"}'),
    )
    http_error_opener = ScriptedOpener([http_error])
    with mock.patch.object(
        target.webbrowser,
        "open",
        side_effect=AssertionError("HTTP failure opened a browser"),
    ), mock.patch.object(target.time, "sleep") as http_error_sleep:
        try:
            target._broker_device_login(opener=http_error_opener)
        except target._BrokerAuthenticationError as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("Device-start HTTP error was retried")
    assert len(http_error_opener.requests) == 1
    http_error_sleep.assert_not_called()

    invalid_opener = ScriptedOpener([(201, ["not", "a", "mapping"])])
    with mock.patch.object(
        target.webbrowser,
        "open",
        side_effect=AssertionError("Invalid response opened a browser"),
    ), mock.patch.object(target.time, "sleep") as invalid_sleep:
        try:
            target._broker_device_login(opener=invalid_opener)
        except target._BrokerProtocolError:
            pass
        else:
            raise AssertionError("Invalid device-start response was retried")
    assert len(invalid_opener.requests) == 1
    invalid_sleep.assert_not_called()

    persisted_token = "persisted-dpapi-token-canary"
    with tempfile.TemporaryDirectory() as temporary_directory:
        appdata_root = Path(temporary_directory)
        token_path = appdata_root / "FNAIBroker" / "access_token_v2.dpapi"
        token_path.parent.mkdir(parents=True)
        token_path.write_bytes(b"encrypted-dpapi-token")
        persisted_opener = ScriptedOpener(
            [(200, {"display_name": "Persisted Token Artist"})]
        )
        with mock.patch.dict(
            target.os.environ, {"APPDATA": str(appdata_root)}, clear=False
        ), mock.patch.object(
            target, "_broker_dpapi", return_value=persisted_token.encode("utf-8")
        ), mock.patch.object(
            target,
            "_broker_device_login",
            side_effect=AssertionError("Valid DPAPI token started device login"),
        ) as persisted_device_login, mock.patch.object(
            target.webbrowser,
            "open",
            side_effect=AssertionError("Valid DPAPI token opened a browser"),
        ) as persisted_browser, mock.patch.object(
            target, "_broker_clear_token"
        ) as clear_token:
            persisted_bridge = target._HMBAIBrokerBridge(opener=persisted_opener)
            persisted_snapshot = persisted_bridge.account_snapshot(connect=True)
            assert target._broker_token_path() == token_path
        assert persisted_snapshot == target._BrokerAccountSnapshot(
            state="connected",
            connected=True,
            account="Persisted Token Artist",
        )
        assert len(persisted_opener.requests) == 1
        assert persisted_opener.requests[0]["url"] == server_url + "/api/me"
        assert persisted_opener.requests[0]["headers"]["authorization"] == (
            "Bearer " + persisted_token
        )
        persisted_device_login.assert_not_called()
        persisted_browser.assert_not_called()
        clear_token.assert_not_called()
        assert token_path.read_bytes() == b"encrypted-dpapi-token"

        transport_failure_opener = ScriptedOpener(
            [target.urllib.error.URLError(OSError(10054, "token-must-survive"))]
        )
        with mock.patch.dict(
            target.os.environ, {"APPDATA": str(appdata_root)}, clear=False
        ), mock.patch.object(
            target, "_broker_dpapi", return_value=persisted_token.encode("utf-8")
        ), mock.patch.object(
            target, "_broker_clear_token"
        ) as transport_clear, mock.patch.object(
            target,
            "_broker_device_login",
            side_effect=AssertionError("Transport failure forced device login"),
        ) as transport_device_login, mock.patch.object(
            target.webbrowser,
            "open",
            side_effect=AssertionError("Transport failure opened a browser"),
        ) as transport_browser, mock.patch.object(target.logger, "warning"):
            transport_bridge = target._HMBAIBrokerBridge(
                opener=transport_failure_opener
            )
            try:
                transport_bridge.account_snapshot(connect=True)
            except target._BrokerUnavailableError:
                pass
            else:
                raise AssertionError("Broker transport failure was accepted")
        transport_clear.assert_not_called()
        transport_device_login.assert_not_called()
        transport_browser.assert_not_called()
        assert token_path.read_bytes() == b"encrypted-dpapi-token"

    sentinel_opener = object()
    with mock.patch.object(
        target, "_broker_build_opener", return_value=sentinel_opener
    ) as bridge_factory:
        default_bridge = target._HMBAIBrokerBridge()
    bridge_factory.assert_called_once_with()
    assert default_bridge._opener is sentinel_opener

    sensitive_reason = OSError(13, "device-secret-and-proxy-password-canary")
    sensitive_reason.winerror = 10013
    sensitive_error = target.urllib.error.URLError(sensitive_reason)
    with mock.patch.object(target.logger, "warning") as safe_warning:
        target._broker_log_transport_error(
            stage="device_token_poll",
            attempt=2,
            exc=sensitive_error,
            server_url=(
                "http://proxy-user:proxy-password-canary@192.168.203.245:8080"
            ),
        )
    safe_warning.assert_called_once()
    log_format, *log_values = safe_warning.call_args.args
    rendered_log = log_format % tuple(log_values)
    assert "stage=device_token_poll" in rendered_log
    assert "attempt=2" in rendered_log
    assert "exception=URLError" in rendered_log
    assert f"reason={type(sensitive_reason).__name__}" in rendered_log
    assert "errno=13" in rendered_log
    assert "winerror=10013" in rendered_log
    assert "host=192.168.203.245" in rendered_log
    assert "port=8080" in rendered_log
    for sensitive_value in (
        "device-secret-and-proxy-password-canary",
        "proxy-user",
        "proxy-password-canary",
        persisted_token,
        retry_secret,
        poll_secret,
        failed_poll_secret,
        "Authorization",
    ):
        assert sensitive_value not in rendered_log


def assert_broker_account_and_button_contract() -> None:
    assert target.AI_BROKER_SERVER_URL == "http://192.168.203.245:8080"
    assert target._broker_validated_server_url() == target.AI_BROKER_SERVER_URL

    class DeviceResponse(io.BytesIO):
        def __init__(self, status: int, payload: dict) -> None:
            super().__init__(json.dumps(payload).encode("utf-8"))
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()
            return False

    class DeviceOpener:
        def __init__(self) -> None:
            self.requests: list[tuple[str, dict]] = []
            self.responses = [
                DeviceResponse(
                    201,
                    {
                        "device_code": "device-code-1",
                        "device_secret": "device-secret-abcdefghijklmnopqrstuvwxyz",
                        "verification_url": (
                            target.AI_BROKER_SERVER_URL + "/?device=device-code-1"
                        ),
                    },
                ),
                DeviceResponse(202, {"status": "pending"}),
                DeviceResponse(200, {"access_token": "permanent-device-token"}),
            ]

        def open(self, request, *, timeout: float):
            assert timeout > 0
            body = json.loads(request.data or b"{}")
            self.requests.append((request.full_url, body))
            return self.responses.pop(0)

    device_opener = DeviceOpener()
    with mock.patch.object(target.webbrowser, "open", return_value=True) as browser_open, mock.patch.object(
        target, "_broker_save_token"
    ) as save_token, mock.patch.object(target.time, "sleep") as poll_sleep:
        login_result = target._broker_device_login(opener=device_opener)
    assert login_result == {"status": "connected"}
    assert [url for url, _body in device_opener.requests] == [
        target.AI_BROKER_SERVER_URL + "/api/device/start",
        target.AI_BROKER_SERVER_URL + "/api/device/token",
        target.AI_BROKER_SERVER_URL + "/api/device/token",
    ]
    assert device_opener.requests[0][1] == {}
    assert device_opener.requests[1][1] == device_opener.requests[2][1]
    assert device_opener.requests[1][1]["device_code"] == "device-code-1"
    browser_open.assert_called_once_with(
        target.AI_BROKER_SERVER_URL + "/?device=device-code-1",
        new=2,
        autoraise=True,
    )
    poll_sleep.assert_called_once_with(target.AI_BROKER_DEVICE_POLL_SECONDS)
    save_token.assert_called_once_with("permanent-device-token")

    declined_opener = DeviceOpener()
    with mock.patch.object(
        target.webbrowser, "open", return_value=False
    ), mock.patch.object(target, "_broker_save_token") as declined_save, mock.patch.object(
        target.time, "sleep"
    ) as declined_sleep:
        try:
            target._broker_device_login(opener=declined_opener)
        except target._BrokerUnavailableError as exc:
            assert "authorization page" in str(exc)
        else:
            raise AssertionError("Browser-open refusal entered the polling loop")
    assert [url for url, _body in declined_opener.requests] == [
        target.AI_BROKER_SERVER_URL + "/api/device/start"
    ]
    declined_save.assert_not_called()
    declined_sleep.assert_not_called()

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
    ) as request_json, mock.patch.object(
        target,
        "_broker_device_login",
        side_effect=AssertionError("saved token fast path opened device login"),
    ):
        snapshot = bridge.account_snapshot(connect=True)
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
        side_effect=[
            target._BrokerAuthenticationError("login required"),
            {"display_name": "Direct Signup Artist"},
        ],
    ), mock.patch.object(
        target, "_broker_device_login", return_value={"status": "connected"}
    ) as device_login:
        direct_snapshot = bridge.account_snapshot(connect=True)
    assert direct_snapshot == target._BrokerAccountSnapshot(
        state="connected",
        connected=True,
        account="Direct Signup Artist",
    )
    device_login.assert_called_once_with()

    with mock.patch.object(
        bridge,
        "_request_json",
        side_effect=target._BrokerUnavailableError("safe unavailable"),
    ), mock.patch.object(
        target,
        "_broker_device_login",
        side_effect=AssertionError("server outage opened device authorization"),
    ):
        try:
            bridge.account_snapshot(connect=True)
        except target._BrokerUnavailableError:
            pass
        else:
            raise AssertionError("Broker outage was treated as a logged-out session")

    assert bridge.is_trusted_broker_url(target.AI_BROKER_SERVER_URL + "/result.mp4")
    assert not bridge.is_trusted_broker_url(
        target.AI_BROKER_SERVER_URL + ".evil.example/result.mp4"
    )
    assert target.HMBSeedanceGeneration._broker_result_url(
        "/downloads/result.mp4"
    ) == (target.AI_BROKER_SERVER_URL + "/downloads/result.mp4")

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
    node = target.HMBSeedanceGeneration(name="Broker Button Regression")
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




def assert_indexed_output_macro_contract() -> None:
    # Required {_index} slots are resolved before submission without exposing a
    # partial final file.
    bridge = FakeBrokerBridge(
        [
            {
                "job_id": "broker-job-1",
                "status": "completed",
                "output": "https://cdn.example/indexed.mp4",
            }
        ]
    )
    node = BrokerScriptedNode(bridge)
    indexed_destination = IndexedMacroDestination()
    node.destination = indexed_destination
    node._output_file = FakeOutputFile(indexed_destination)
    node.set_parameter_value("prompt", "required output index regression")
    asyncio.run(node._process_generation())

    assert indexed_destination.resolve_attempts == 0
    published = list(
        Path(indexed_destination._temporary_directory.name).rglob("*.mp4")
    )
    assert len(published) == 1
    assert published[0].read_bytes() == VALID_MP4_BYTES
    assert len(bridge.generate_payloads) == 1
    assert bridge.refresh_ids == ["broker-job-1"]
    assert node.parameter_output_values["was_successful"] is True

    # No other missing macro variable may bypass the pre-billing validation.
    invalid_bridge = FakeBrokerBridge([])
    invalid = BrokerScriptedNode(invalid_bridge)
    invalid_destination = IndexedMacroDestination("_index, shot_name")
    invalid.destination = invalid_destination
    invalid._output_file = FakeOutputFile(invalid_destination)
    invalid.set_parameter_value("prompt", "invalid output macro regression")
    try:
        asyncio.run(invalid._process_generation_impl())
    except RuntimeError as exc:
        assert "_index, shot_name" in str(exc)
    else:
        raise AssertionError("An unrelated missing output macro variable was accepted")
    assert invalid_bridge.generate_payloads == []


class AtomicLocalDestination:
    def __init__(self, path: Path, policy) -> None:
        self.location = str(path)
        self._existing_file_policy = policy
        self._create_parents = True
        self._append = False

    def resolve(self) -> str:
        return self.location

    async def awrite_bytes(self, _content: bytes):
        raise AssertionError("Completed MP4 used a non-atomic destination writer")


def assert_bounded_mp4_decode_probe_contract() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        staged = Path(temporary) / "staged.mp4"
        staged.write_bytes(VALID_MP4_BYTES)
        success = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "frames": [
                        {"media_type": "video", "width": 64, "height": 64}
                    ]
                }
            ).encode("utf-8"),
            stderr=b"",
        )
        with mock.patch.object(
            target,
            "_resolve_ffprobe_executable",
            return_value=Path("C:/ffmpeg/bin/ffprobe.exe"),
        ), mock.patch.object(target.subprocess, "run", return_value=success) as run:
            REAL_MP4_DECODE_PROBE(staged)
        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        assert command[0].lower().endswith("ffprobe.exe")
        assert command[-2:] == ["-i", str(staged.resolve())]
        assert "-show_frames" in command
        assert f"%+#{target.MP4_DECODE_PROBE_PACKET_LIMIT}" in command
        assert kwargs["stdin"] is target.subprocess.DEVNULL
        assert kwargs["stdout"] is target.subprocess.PIPE
        assert kwargs["stderr"] is target.subprocess.PIPE
        assert kwargs["check"] is False
        assert kwargs["timeout"] == target.MP4_DECODE_PROBE_TIMEOUT_SECONDS

        def rejected(completed=None, *, side_effect=None) -> None:
            with mock.patch.object(
                target,
                "_resolve_ffprobe_executable",
                return_value=Path("C:/ffmpeg/bin/ffprobe.exe"),
            ), mock.patch.object(
                target.subprocess,
                "run",
                return_value=completed,
                side_effect=side_effect,
            ):
                try:
                    REAL_MP4_DECODE_PROBE(staged)
                except RuntimeError:
                    return
            raise AssertionError("Invalid ffprobe result was accepted")

        rejected(SimpleNamespace(returncode=1, stdout=b"", stderr=b"decode"))
        rejected(SimpleNamespace(returncode=0, stdout=b"not-json", stderr=b""))
        rejected(
            SimpleNamespace(
                returncode=0,
                stdout=b'{"frames":[]}',
                stderr=b"",
            )
        )
        rejected(
            SimpleNamespace(
                returncode=0,
                stdout=b"x" * (target.MP4_DECODE_PROBE_MAX_OUTPUT_BYTES + 1),
                stderr=b"",
            )
        )
        rejected(
            side_effect=target.subprocess.TimeoutExpired(
                ["ffprobe"], target.MP4_DECODE_PROBE_TIMEOUT_SECONDS
            )
        )

    with mock.patch.object(target.shutil, "which", return_value=None):
        try:
            target._resolve_ffprobe_executable()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Missing ffprobe did not fail closed")


def assert_atomic_output_and_submission_safety() -> None:
    assert target._is_structurally_valid_mp4(VALID_MP4_BYTES)
    assert not target._is_structurally_valid_mp4(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        b"\x00\x00\x00\x10mdat12345678"
    )
    assert not target._is_structurally_valid_mp4(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        b"\x00\x00\x00\x10moov\x00\x00\x00\x08mvhd"
    )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        final_path = root / "atomic.mp4"
        old_bytes = b"previous-complete-output"
        final_path.write_bytes(old_bytes)
        destination = AtomicLocalDestination(
            final_path,
            target.ExistingFilePolicy.OVERWRITE,
        )
        real_replace = target.os.replace
        observations: list[Path] = []
        probe_observations: list[Path] = []

        def observed_probe(source) -> None:
            source_path = Path(source)
            assert source_path.parent == root
            assert source_path.read_bytes() == VALID_MP4_BYTES
            assert final_path.read_bytes() == old_bytes
            probe_observations.append(source_path)

        def observed_replace(source, target_path) -> None:
            source_path = Path(source)
            assert probe_observations == [source_path]
            assert source_path.parent == Path(target_path).parent == root
            assert source_path.read_bytes() == VALID_MP4_BYTES
            assert final_path.read_bytes() == old_bytes
            observations.append(source_path)
            real_replace(source_path, target_path)

        with mock.patch.object(
            target, "_validate_decodable_mp4_file", side_effect=observed_probe
        ), mock.patch.object(target.os, "replace", side_effect=observed_replace):
            saved = asyncio.run(
                target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                    destination,
                    VALID_MP4_BYTES,
                )
            )
        assert observations
        assert probe_observations
        assert final_path.read_bytes() == VALID_MP4_BYTES
        assert Path(saved.resolve()) == final_path
        assert not list(root.glob(".*.partial.mp4"))
        assert not list(root.glob(".*.output-probe"))

        final_path.write_bytes(old_bytes)
        with mock.patch.object(
            target,
            "_validate_decodable_mp4_file",
            side_effect=RuntimeError("simulated undecodable stream"),
        ):
            try:
                asyncio.run(
                    target.HMBSeedanceGeneration._atomic_publish_completed_mp4(
                        destination,
                        VALID_MP4_BYTES,
                    )
                )
            except RuntimeError as exc:
                assert "undecodable" in str(exc)
            else:
                raise AssertionError("Undecodable staged MP4 was published")
        assert final_path.read_bytes() == old_bytes
        assert not list(root.glob(".*.partial.mp4"))

    bridge = FakeBrokerBridge([])
    node = BrokerScriptedNode(bridge)
    node.set_parameter_value("prompt", "preflight must precede billing")
    with mock.patch.object(
        target.HMBSeedanceGeneration,
        "_probe_output_parent_writable",
        side_effect=PermissionError("simulated unwritable output parent"),
    ):
        try:
            asyncio.run(node._process_generation_impl())
        except PermissionError:
            pass
        else:
            raise AssertionError("Unwritable output reached Broker submission")
    assert bridge.account_calls == 0
    assert bridge.generate_payloads == []

    async def cancellation_case() -> None:
        started = threading.Event()
        release = threading.Event()
        worker_finished = threading.Event()

        def blocking_submit() -> dict:
            started.set()
            assert release.wait(2.0)
            worker_finished.set()
            return {"job_id": "broker-job-cancel", "status": "pending"}

        request_id = "hmb-cancelled-submit-1"
        node.parameter_output_values["generation_id"] = request_id
        node.parameter_output_values["generation_status"] = "submitting"
        cleanup_events: list[str] = []
        node._cleanup_temporary_video_uploads = lambda: cleanup_events.append(
            "eager_cleanup"
        )
        node._defer_temporary_video_upload_cleanup = lambda: cleanup_events.append(
            "deferred_cleanup"
        )

        async def submit_only() -> None:
            await node._await_submission_result(blocking_submit)

        node._process_generation_impl = submit_only
        operation = asyncio.create_task(node._process_generation())
        assert await asyncio.to_thread(started.wait, 1.0)
        cancelled_at = time.monotonic()
        operation.cancel()
        try:
            await operation
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Cancelled submission waited for its worker thread")
        assert time.monotonic() - cancelled_at < 0.5
        assert not worker_finished.is_set()
        assert node._submission_outcome_unknown is True
        assert node.parameter_output_values["generation_id"] == request_id
        assert node.parameter_output_values["generation_status"] == "submission_unknown"
        assert node.parameter_output_values["provider_response"] == {
            "transport": "fn_ai_broker",
            "id": request_id,
            "status": "submission_unknown",
        }
        assert cleanup_events == ["eager_cleanup", "deferred_cleanup"]
        assert len(node._detached_submission_tasks) == 1

        release.set()
        for _ in range(100):
            if worker_finished.is_set() and not node._detached_submission_tasks:
                break
            await asyncio.sleep(0.01)
        assert worker_finished.is_set()
        assert not node._detached_submission_tasks

    asyncio.run(cancellation_case())


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
        failing_node.set_parameter_value("reference_video_1", original_artifact)
        failing_node._create_gt_cloud_storage_driver = lambda: failing_driver

        failing_bridge.generate_seedance = mock.Mock(
            side_effect=target._BrokerError("simulated create failure")
        )
        try:
            asyncio.run(failing_node._process_generation())
        except RuntimeError as exc:
            assert "simulated create failure" in str(exc)
        else:
            raise AssertionError("Simulated create failure was accepted")
        assert len(failing_driver.uploads) == 1
        assert failing_driver.deletes == [failing_driver.uploads[0]["path"]]


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

    redirect_requests: list[httpx.Request] = []

    async def redirect_handler(request: httpx.Request) -> httpx.Response:
        redirect_requests.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private.mp4"})

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


def assert_broker_server_accounting_contract() -> None:
    module_source = MODULE_PATH.read_text(encoding="utf-8")
    retired_ledger_name = "".join(("Griptape_", "list"))
    retired_share = "".join(
        (r"\\fin-rcomp1\Composite_Team", "\\", "00", ".", "CompSource")
    )
    for forbidden in (
        "USAGE_LEDGER_ROOT",
        "USAGE_LOCAL_QUEUE_ROOT",
        "USAGE_PRICE_CNY_PER_MILLION",
        "_prepare_usage_tracking",
        "_record_usage_task",
        "_record_current_usage_status",
        "_build_usage_event",
        "_flush_usage_queue",
        retired_ledger_name,
        retired_share,
    ):
        assert forbidden not in module_source

    assert not {
        name
        for name in vars(target)
        if name.startswith("USAGE_") or name.startswith("_USAGE_")
    }
    for runtime_class in (
        target.HMBSeedanceGeneration,
        target.HMBSeedanceGeneration,
    ):
        assert not {
            name for name in dir(runtime_class) if "usage" in name.casefold()
        }

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

    manifest = json.loads(
        (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
    )
    tags = set(manifest["metadata"]["tags"])
    assert not {
        "PrivatePerUserMonthlyUsageLedger",
        "OfflineUsageQueue",
        "AtomicUsageLedger",
    } & tags
    assert "BrokerServerUsageAccounting" in tags
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    assert (
        "The client performs no secondary usage recording; the Broker is the sole "
        "usage, quota, and accounting authority."
    ) in manifest_text


assert_constructor_and_public_contract()
assert_image_asset_single_wire_host_contract()
assert_video_picker_single_wire_host_contract()
assert_payload_and_media_contract()
assert_broker_generation_contract()
assert_refresh_during_submission_contract()
assert_broker_direct_transport_resilience_contract()
assert_broker_account_and_button_contract()
assert_indexed_output_macro_contract()
assert_bounded_mp4_decode_probe_contract()
assert_atomic_output_and_submission_safety()
assert_local_video_temporary_publication()
assert_tos_local_video_temporary_publication()
assert_broker_result_download_contract()
assert_broker_server_accounting_contract()

print("HMB Seedance FN AI Broker regression: PASS")
