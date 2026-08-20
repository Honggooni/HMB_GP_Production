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
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_0_MINI_MODEL_ID] == (
        "720p",
        "480p",
    )
    assert target.MODEL_DEFAULT_RESOLUTIONS == {
        target.SEEDANCE_2_0_MODEL_ID: "1080p",
        target.SEEDANCE_2_0_FAST_MODEL_ID: "720p",
        target.SEEDANCE_2_0_MINI_MODEL_ID: "720p",
    }

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
        target.MODEL_NAME_SEEDANCE_2_0_MINI,
    ]
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
    node.set_parameter_value("model_id", target.MODEL_NAME_SEEDANCE_2_0_MINI)
    assert node._get_parameters()["model_id"] == target.SEEDANCE_2_0_MINI_MODEL_ID
    assert node.get_parameter_value("resolution") == "720p"
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
        "USAGE" + "_LEDGER_ROOT",
        "Griptape_" + "list",
    ):
        assert forbidden_symbol not in source
    assert not {
        name
        for name in dir(target.HMBSeedanceGeneration)
        if "usage" in name.casefold() or "direct" in name.casefold()
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
        target.SEEDANCE_2_0_MINI_MODEL_ID,
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
        "_broker_auto_login",
        side_effect=AssertionError("server outage triggered a login exchange"),
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

        unknown_driver = FakeCloudDriver()
        unknown_bridge = FakeBrokerBridge([])
        unknown_node = BrokerScriptedNode(unknown_bridge)
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
        assert unknown_node.parameter_output_values["generation_id"] == ""
        assert unknown_node.parameter_output_values["generation_status"] == (
            "submission_unknown"
        )
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
            await asyncio.sleep(0.05)
            assert not process.done(), "Submit coroutine outran its blocking POST worker"
            blocking_bridge.release.set()
            try:
                await process
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("Cancellation during submit was swallowed")

        asyncio.run(cancel_started_submission())
        assert blocking_bridge.returned.is_set()
        assert len(blocking_bridge.generate_payloads) == 1
        assert (
            blocking_node.parameter_output_values["generation_id"]
            == "broker-job-cancelled-submit"
        )
        assert blocking_node._submission_outcome_unknown is False
        assert blocking_node._remote_task_may_be_active is True
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
        project_node = target.HMBSeedanceGeneration(
            name="Atomic ProjectFileParameter Regression"
        )
        project_node._broker_bridge_instance = bridge
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
assert_image_asset_single_wire_host_contract()
assert_video_picker_single_wire_host_contract()
assert_payload_and_media_contract()
assert_broker_generation_contract()
assert_refresh_during_submission_contract()
assert_broker_account_and_button_contract()
assert_local_video_temporary_publication()
assert_tos_local_video_temporary_publication()
assert_broker_result_download_contract()
assert_atomic_final_output_publication()
assert_unwritable_output_is_rejected_before_submission()
assert_broker_server_accounting_contract()

print("HMB Seedance Generation FN AI Broker regression: PASS")
