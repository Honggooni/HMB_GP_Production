from __future__ import annotations

import asyncio
import base64
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
MODULE_PATH = ROOT / "HMBSeedance20VideoGeneration.py"
IMAGE_ASSET_MODULE_PATH = ROOT / "HMBImageAssetLibrary.py"
VIDEO_PICKER_MODULE_PATH = ROOT / "HMBVideoPickerLibrary.py"


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
        self.location = str(ROOT / ".tmp" / "volcengine-regression.mp4")
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

    def resolve(self) -> str:
        self.resolve_attempts += 1
        raise RuntimeError(
            "Attempted to resolve macro path. Failed because missing required "
            f"variables: {self.missing_variables}"
        )


class ScriptedNode(target.HMBSeedance20VideoGeneration):
    TEST_KEY = "regression-secret-key"

    def __init__(self, scripted_gets: list[dict]) -> None:
        super().__init__(name="HMB Volcengine Scripted Regression")
        self.scripted_gets = list(scripted_gets)
        self.requests: list[dict] = []
        self.downloads: list[str] = []
        self.sleeps: list[float] = []
        self.destination = FakeDestination()
        self._output_file = FakeOutputFile(self.destination)

    @staticmethod
    def _get_api_key() -> str:
        return ScriptedNode.TEST_KEY

    def _capture_usage_identity(self):
        # General transport tests must never touch a real login or network
        # usage share. Dedicated ledger tests exercise that contract below.
        return None

    async def _request_json(
        self,
        method: str,
        path: str,
        api_key: str,
        payload: dict | None = None,
        *,
        retry: bool = False,
        deadline: float | None = None,
    ) -> dict:
        self.requests.append(
            {
                "method": method,
                "path": path,
                "api_key": api_key,
                "payload": payload,
                "retry": retry,
                "deadline": deadline,
            }
        )
        if method == "POST":
            return {"id": "task-regression-1", "status": "queued"}
        if not self.scripted_gets:
            raise AssertionError("Unexpected extra task poll")
        return self.scripted_gets.pop(0)

    async def _download_video(self, url: str) -> bytes:
        self.downloads.append(url)
        return b"\x00\x00\x00\x18ftypmp42regression-video"

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def _monotonic(self) -> float:
        return 0.0

    async def _process_generation_impl(self) -> None:
        """Keep legacy transport assertions isolated from the Broker contract."""
        await self._process_direct_generation_impl()

    async def _refresh_async(self) -> None:
        await self._refresh_direct_async()


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


class BrokerScriptedNode(target.HMBSeedance20VideoGeneration):
    def __init__(self, bridge: FakeBrokerBridge) -> None:
        super().__init__(name="HMB Seedance Broker Scripted Regression")
        self.bridge = bridge
        self.destination = FakeDestination()
        self._output_file = FakeOutputFile(self.destination)
        self.downloads: list[str] = []
        self.sleeps: list[float] = []

    def _create_broker_bridge(self):
        return self.bridge

    def _capture_usage_identity(self):
        return None

    async def _download_video(self, url: str) -> bytes:
        self.downloads.append(url)
        return b"\x00\x00\x00\x18ftypmp42broker-regression-video"

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
        node = target.HMBSeedance20VideoGeneration(name="Constructor Regression")

    assert target.HMBSeedance20VideoGeneration.__mro__[1].__name__ == "SuccessFailureNode"
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
    assert target.ARK_BASE_URL == "https://ark.cn-beijing.volces.com/api/v3"
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_0_MODEL_ID] == (
        "480p",
        "720p",
        "1080p",
        "4k",
    )
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_0_FAST_MODEL_ID] == (
        "480p",
        "720p",
    )
    assert target.MODEL_RESOLUTIONS[target.SEEDANCE_2_0_MINI_MODEL_ID] == (
        "480p",
        "720p",
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
    assert (
        node.get_parameter_value("local_video_upload_service")
        == target.LOCAL_VIDEO_UPLOAD_GRIPTAPE
    )
    assert node.get_parameter_value("tos_region") == "cn-beijing"
    assert node.get_parameter_value("tos_endpoint") == "tos-cn-beijing.volces.com"
    assert node.get_parameter_value("tos_url_validity_seconds") == 86400
    assert node.get_parameter_by_name("tos_region").hide is True
    assert node.get_parameter_value("generate_audio") is False
    saved_audio_node = target.HMBSeedance20VideoGeneration(
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
    assert "_BaseSeedance20" not in source
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
    assert 'Options(choices=["480p", "720p", "1080p", "4k"])' in source


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
            destination = target.HMBSeedance20VideoGeneration(
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
            payload = destination._build_payload(params)
            assert [
                item["image_url"]["url"]
                for item in payload["content"]
                if item["type"] == "image_url"
            ] == ordered

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
            overflow_destination = target.HMBSeedance20VideoGeneration(
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
        destination = target.HMBSeedance20VideoGeneration(
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
        payload = destination._build_payload(params)
        assert [
            item["video_url"]["url"]
            for item in payload["content"]
            if item["type"] == "video_url"
        ] == ordered

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


def assert_secret_manager_contract() -> None:
    calls: list[str] = []

    class FakeSecrets:
        @staticmethod
        def get_secret(name: str):
            calls.append(name)
            return "  user-owned-ark-key  "

    with mock.patch.object(
        target.GriptapeNodes, "SecretsManager", return_value=FakeSecrets()
    ):
        assert target.HMBSeedance20VideoGeneration._get_api_key() == "user-owned-ark-key"
    assert calls == ["ARK_API_KEY"]

    class MissingSecrets:
        @staticmethod
        def get_secret(_name: str):
            return "  "

    with mock.patch.object(
        target.GriptapeNodes, "SecretsManager", return_value=MissingSecrets()
    ):
        try:
            target.HMBSeedance20VideoGeneration._get_api_key()
        except ValueError as exc:
            assert "ARK_API_KEY is missing" in str(exc)
        else:
            raise AssertionError("Blank ARK_API_KEY was accepted")


def assert_payload_and_media_contract() -> None:
    node = target.HMBSeedance20VideoGeneration(name="Payload Regression")
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
        payload = node._build_payload(params)

        assert payload["model"] == "doubao-seedance-2-0-260128"
        assert payload["resolution"] == "1080p"
        assert payload["ratio"] == "16:9"
        assert payload["duration"] == 8
        assert payload["generate_audio"] is True
        assert payload["watermark"] is False
        assert [item["type"] for item in payload["content"]] == [
            "text",
            "image_url",
            "image_url",
            "video_url",
            "audio_url",
        ]
        assert payload["content"][1]["role"] == "reference_image"
        assert payload["content"][3] == {
            "type": "video_url",
            "video_url": {"url": "asset://video-asset-1"},
            "role": "reference_video",
        }
        encoded_image = payload["content"][1]["image_url"]["url"]
        encoded_audio = payload["content"][4]["audio_url"]["url"]
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
    assert [target.HMBSeedance20VideoGeneration._coerce_reference_value(item) for item in collected["video_references"]] == [
        "https://cdn.example/video-1.mp4",
        "asset://video-asset-2",
    ]
    assert node.get_parameter_by_name("reference_video_1").hide is True
    assert node.get_parameter_by_name("reference_video_2").hide is True
    assert node.get_parameter_by_name("reference_video_3").hide is True

    ordered_list_node = target.HMBSeedance20VideoGeneration(
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
    ordered_video_payload = ordered_list_node._build_payload(ordered_video_params)
    assert [
        item["video_url"]["url"]
        for item in ordered_video_payload["content"]
        if item["type"] == "video_url"
    ] == ordered_videos

    overflow_video_node = target.HMBSeedance20VideoGeneration(
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

    scalar_node = target.HMBSeedance20VideoGeneration(name="Scalar Video Regression")
    scalar_node.set_parameter_value("prompt", "ordered scalar videos")
    scalar_node.set_parameter_value(
        "reference_video_1",
        target.VideoUrlArtifact("https://cdn.example/scalar-1.mp4"),
    )
    scalar_node.set_parameter_value(
        "reference_video_2", {"value": "asset://scalar-video-2"}
    )
    scalar_payload = scalar_node._build_payload(scalar_node._get_parameters())
    scalar_video_content = [
        item for item in scalar_payload["content"] if item["type"] == "video_url"
    ]
    assert scalar_video_content == [
        {
            "type": "video_url",
            "video_url": {"url": "https://cdn.example/scalar-1.mp4"},
            "role": "reference_video",
        },
        {
            "type": "video_url",
            "video_url": {"url": "asset://scalar-video-2"},
            "role": "reference_video",
        },
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

    legacy_node = target.HMBSeedance20VideoGeneration(name="Legacy List Regression")
    legacy_node.set_parameter_value(
        "VIDEO_REFERENCES", ["https://cdn.example/legacy.mp4"]
    )
    assert legacy_node._get_parameters()["video_references"] == [
        "https://cdn.example/legacy.mp4"
    ]

    equivalent_legacy_node = target.HMBSeedance20VideoGeneration(
        name="Legacy and Scalar Payload Equivalence Regression"
    )
    equivalent_legacy_node.set_parameter_value("prompt", "ordered scalar videos")
    equivalent_legacy_node.set_parameter_value(
        "VIDEO_REFERENCES",
        ["https://cdn.example/scalar-1.mp4", "asset://scalar-video-2"],
    )
    assert equivalent_legacy_node._build_payload(
        equivalent_legacy_node._get_parameters()
    ) == scalar_payload

    mixed_node = target.HMBSeedance20VideoGeneration(
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
        target.HMBSeedance20VideoGeneration._coerce_reference_value(item)
        for item in mixed_node._get_parameters()["video_references"]
    ] == ["https://cdn.example/public-list.mp4"]
    assert mixed_node._get_parameters()["video_reference_slots"] == []

    serialized_list_node = target.HMBSeedance20VideoGeneration(
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

    ordered_image_node = target.HMBSeedance20VideoGeneration(
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
    ordered_list_payload = ordered_image_node._build_payload(
        ordered_image_node._get_parameters()
    )
    assert [
        item["image_url"]["url"]
        for item in ordered_list_payload["content"]
        if item["type"] == "image_url"
    ] == ordered_images
    assert [item["type"] for item in ordered_list_payload["content"]] == [
        "text",
        "image_url",
        "image_url",
    ]

    empty_child_node = target.HMBSeedance20VideoGeneration(
        name="Empty Single Image List Regression"
    )
    empty_child_node.get_parameter_by_name("reference_audio").append_child_parameter()
    empty_child_node.set_parameter_value("prompt", "empty child is ignored")
    assert empty_child_node.get_parameter_value("reference_images") == []
    assert empty_child_node.get_parameter_value("reference_audio") == [[]]
    empty_child_params = empty_child_node._get_parameters()
    assert empty_child_params["reference_images"] == []
    assert empty_child_params["reference_audio"] == []
    empty_child_payload = empty_child_node._build_payload(empty_child_params)
    assert empty_child_payload["content"] == [
        {"type": "text", "text": "empty child is ignored"}
    ]

    connected_parent_list_node = target.HMBSeedance20VideoGeneration(
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
    standard_4k_payload = node._build_payload(params)
    assert standard_4k_payload["model"] == target.SEEDANCE_2_0_MODEL_ID
    assert standard_4k_payload["resolution"] == "4k"

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
    fast_payload = node._build_payload(params)
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
        assert target.HMBSeedance20VideoGeneration._normalize_broker_status(raw) == (
            expected
        )
    assert target.HMBSeedance20VideoGeneration._normalize_broker_status(
        "provider-api-key-canary"
    ) == ""

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
    with mock.patch.object(
        node,
        "_get_api_key",
        side_effect=AssertionError("Broker flow read ARK_API_KEY"),
    ), mock.patch.object(
        node,
        "_prepare_usage_tracking",
        side_effect=AssertionError("Broker flow collected usage"),
    ), mock.patch.object(
        node,
        "_record_usage_task",
        side_effect=AssertionError("Broker flow recorded usage"),
    ):
        asyncio.run(node._process_generation())

    assert bridge.account_calls == 1
    assert bridge.refresh_ids == ["broker-job-1"]
    assert len(bridge.generate_payloads) == 1
    payload = bridge.generate_payloads[0]
    assert payload["provider"] == "volcengine_ark"
    assert payload["model"] == target.SEEDANCE_2_0_MODEL_ID
    assert payload["prompt"] == "Broker-only Seedance regression"
    assert payload["duration_seconds"] == 5
    assert payload["quality"] == "720p"
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
    with mock.patch.object(
        resumed,
        "_prepare_usage_tracking",
        side_effect=AssertionError("Broker resume collected usage"),
    ), mock.patch.object(
        resumed,
        "_record_usage_task",
        side_effect=AssertionError("Broker resume recorded usage"),
    ):
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
    with mock.patch.object(
        refreshed,
        "_prepare_usage_tracking",
        side_effect=AssertionError("Broker refresh collected usage"),
    ), mock.patch.object(
        refreshed,
        "_record_usage_task",
        side_effect=AssertionError("Broker refresh recorded usage"),
    ):
        asyncio.run(refreshed._refresh_async())
    assert refresh_bridge.refresh_ids == ["broker-refresh-3"]
    assert refreshed.downloads == ["https://cdn.example/refreshed-broker.mp4"]


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
    assert target.HMBSeedance20VideoGeneration._broker_result_url(
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
    node = target.HMBSeedance20VideoGeneration(name="Broker Button Regression")
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


def assert_scripted_success_flow() -> None:
    node = ScriptedNode(
        [
            {"id": "task-regression-1", "status": "queued"},
            {"id": "task-regression-1", "status": "running"},
            {
                "id": "task-regression-1",
                "status": "succeeded",
                "content": {
                    "video_url": "https://cdn.example/result.mp4",
                    "last_frame_url": "https://cdn.example/last.jpg",
                },
                "authorization": "Bearer regression-secret-key",
            },
        ]
    )
    node.set_parameter_value("prompt", "A complete Volcengine flow")
    node.set_parameter_value("poll_interval_seconds", 30)
    asyncio.run(node._process_generation())

    assert node.destination.resolved is True
    assert node.destination.written == b"\x00\x00\x00\x18ftypmp42regression-video"
    assert [request["method"] for request in node.requests] == [
        "POST",
        "GET",
        "GET",
        "GET",
    ]
    assert node.requests[0]["path"] == "/contents/generations/tasks"
    assert node.requests[0]["retry"] is False
    assert all(request["retry"] is True for request in node.requests[1:])
    assert all(request["deadline"] == 3600 for request in node.requests[1:])
    assert all(
        request["path"]
        == "/contents/generations/tasks/task-regression-1"
        for request in node.requests[1:]
    )
    assert node.sleeps == [30, 30]
    assert node.downloads == ["https://cdn.example/result.mp4"]
    assert node.parameter_output_values["generation_id"] == "task-regression-1"
    assert node.parameter_output_values["generation_status"] == "succeeded"
    assert node.parameter_output_values["video_url"].value == node.destination.location
    assert node.parameter_output_values["VIDEO_OUT"].value == node.destination.location
    assert node.parameter_output_values["last_frame_url"] == "https://cdn.example/last.jpg"
    assert node.parameter_output_values["was_successful"] is True
    provider_response = node.parameter_output_values["provider_response"]
    assert provider_response["authorization"] == "[REDACTED]"
    assert provider_response["content"]["video_url"] == "[SIGNED_URL_REDACTED]"
    assert provider_response["content"]["last_frame_url"] == "[SIGNED_URL_REDACTED]"
    assert ScriptedNode.TEST_KEY not in json.dumps(
        node.parameter_output_values, default=str
    )


def assert_indexed_output_macro_contract() -> None:
    # Required {_index} slots are allocated by ProjectFileDestination's write
    # path. The node's non-writing preflight must not reject that valid setup.
    node = ScriptedNode(
        [
            {
                "id": "task-regression-1",
                "status": "succeeded",
                "content": {"video_url": "https://cdn.example/indexed.mp4"},
            }
        ]
    )
    indexed_destination = IndexedMacroDestination()
    node.destination = indexed_destination
    node._output_file = FakeOutputFile(indexed_destination)
    node.set_parameter_value("prompt", "required output index regression")
    asyncio.run(node._process_generation())

    assert indexed_destination.resolve_attempts == 1
    assert indexed_destination.written == b"\x00\x00\x00\x18ftypmp42regression-video"
    assert [request["method"] for request in node.requests] == ["POST", "GET"]
    assert node.parameter_output_values["was_successful"] is True

    # No other missing macro variable may bypass the pre-billing validation.
    invalid = ScriptedNode([])
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
    assert invalid.requests == []


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
        node = ScriptedNode(
            [
                {
                    "id": "task-regression-1",
                    "status": "succeeded",
                    "content": {"video_url": "https://cdn.example/result.mp4"},
                }
            ]
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
        post_payload = node.requests[0]["payload"]
        video_content = [
            item for item in post_payload["content"] if item["type"] == "video_url"
        ]
        assert video_content == [
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://storage.example/reference.mp4?signature=temporary-secret"
                },
                "role": "reference_video",
            }
        ]
        output_dump = json.dumps(node.parameter_output_values, default=str)
        assert "temporary-secret" not in output_dump

        public_node = target.HMBSeedance20VideoGeneration(
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

        missing_node = ScriptedNode([])
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
        assert missing_node.requests == []

        disabled_node = target.HMBSeedance20VideoGeneration(
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
        failing_node = ScriptedNode([])
        failing_node.set_parameter_value("reference_video_1", original_artifact)
        failing_node._create_gt_cloud_storage_driver = lambda: failing_driver

        async def fail_create_task(*_args, **_kwargs):
            raise RuntimeError("simulated create failure")

        failing_node._request_json = fail_create_task
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
        node = ScriptedNode(
            [
                {
                    "id": "task-regression-1",
                    "status": "succeeded",
                    "content": {"video_url": "https://cdn.example/result.mp4"},
                }
            ]
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
        post_payload = node.requests[0]["payload"]
        reference_url = next(
            item["video_url"]["url"]
            for item in post_payload["content"]
            if item["type"] == "video_url"
        )
        assert reference_url.startswith(
            "https://team-bucket.tos-cn-beijing.volces.com/"
        )
        assert "temporary-tos-secret" in reference_url
        assert "temporary-tos-secret" not in json.dumps(
            node.parameter_output_values, default=str
        )

        assert (
            target.HMBSeedance20VideoGeneration._normalize_tos_endpoint(
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
                target.HMBSeedance20VideoGeneration._normalize_tos_endpoint(
                    invalid_endpoint
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"Unsafe TOS endpoint accepted: {invalid_endpoint}")


def assert_resume_flow_skips_post() -> None:
    node = ScriptedNode(
        [
            {
                "id": "task-existing-9",
                "status": "succeeded",
                "content": {"video_url": "https://cdn.example/existing.mp4"},
            }
        ]
    )
    node.set_parameter_value("resume_generation_id", "task-existing-9")
    node.set_parameter_value(
        "reference_video_1", target.VideoUrlArtifact("missing-local-video.mp4")
    )
    node._create_gt_cloud_storage_driver = lambda: (_ for _ in ()).throw(
        AssertionError("Resume initialized Griptape Cloud storage")
    )
    asyncio.run(node._process_generation())
    assert [request["method"] for request in node.requests] == ["GET"]
    assert node.requests[0]["path"].endswith("/task-existing-9")
    assert node.parameter_output_values["generation_id"] == "task-existing-9"
    assert node.parameter_output_values["generation_status"] == "succeeded"
    assert node.downloads == ["https://cdn.example/existing.mp4"]


def assert_refresh_recovery_contract() -> None:
    known = ScriptedNode(
        [
            {
                "id": "task-refresh-1",
                "status": "succeeded",
                "content": {"video_url": "https://cdn.example/refreshed.mp4"},
            }
        ]
    )
    known.parameter_output_values["generation_id"] = "task-refresh-1"
    asyncio.run(known._refresh_async())
    assert [request["method"] for request in known.requests] == ["GET"]
    assert known.requests[0]["path"].endswith("/task-refresh-1")
    assert known.downloads == ["https://cdn.example/refreshed.mp4"]
    assert known.parameter_output_values["video_url"].value == known.destination.location
    assert known.parameter_output_values["VIDEO_OUT"].value == known.destination.location

    ambiguous = ScriptedNode(
        [
            {
                "items": [
                    {
                        "id": "task-candidate-7",
                        "model": target.SEEDANCE_2_0_MODEL_ID,
                        "status": "running",
                        "created_at": 1_780_000_060,
                    },
                    {
                        "id": "task-other-model",
                        "model": target.SEEDANCE_2_0_FAST_MODEL_ID,
                        "status": "running",
                        "created_at": 1_780_000_060,
                    },
                ]
            }
        ]
    )
    ambiguous.parameter_output_values["generation_status"] = "submission_unknown"
    ambiguous.parameter_output_values["provider_response"] = {
        "submission_diagnostic": {
            "submission_outcome": "unknown",
            "started_at_epoch": 1_780_000_000,
            "model": target.SEEDANCE_2_0_MODEL_ID,
        }
    }
    asyncio.run(ambiguous._refresh_async())
    assert [request["method"] for request in ambiguous.requests] == ["GET"]
    assert "page_num=1" in ambiguous.requests[0]["path"]
    assert "task-candidate-7" in ambiguous.parameter_output_values["result_details"]
    assert "task-other-model" not in ambiguous.parameter_output_values["result_details"]
    assert "copy its ID into Resume Task ID" in ambiguous.parameter_output_values[
        "result_details"
    ]


def assert_ambiguous_submission_status_contract() -> None:
    node = ScriptedNode([])
    node.set_parameter_value("prompt", "ambiguous submission regression")

    async def ambiguous_request(
        method: str,
        _path: str,
        _api_key: str,
        _payload: dict | None = None,
        **_kwargs,
    ) -> dict:
        assert method == "POST"
        raise target.VolcengineAPIError(
            "safe ambiguous submission",
            response_json={
                "submission_diagnostic": {
                    "submission_outcome": "unknown",
                    "network_error_type": "ReadError",
                    "network_phase": "response-receive",
                    "started_at_epoch": 1_780_000_000,
                }
            },
            submission_outcome="unknown",
        )

    node._request_json = ambiguous_request
    try:
        asyncio.run(node.aprocess())
    except Exception:
        pass
    assert node.parameter_output_values["generation_status"] == "submission_unknown"
    diagnostic = node.parameter_output_values["provider_response"][
        "submission_diagnostic"
    ]
    assert diagnostic["model"] == target.SEEDANCE_2_0_MODEL_ID
    assert "safe ambiguous submission" in node.parameter_output_values[
        "result_details"
    ]
    assert "30 minutes" in node.parameter_output_values["result_details"]


class FastSleepNode(target.HMBSeedance20VideoGeneration):
    def __init__(self) -> None:
        super().__init__(name="HTTPX Transport Regression")
        self.sleeps: list[float] = []

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def assert_http_transport_contract() -> None:
    node = FastSleepNode()
    original_async_client = target.httpx.AsyncClient
    request_log: list[httpx.Request] = []
    get_attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_attempts
        request_log.append(request)
        if request.method == "POST":
            return httpx.Response(503, json={"error": {"message": "busy"}})
        get_attempts += 1
        if get_attempts < 3:
            return httpx.Response(503, json={"error": {"message": "retry"}})
        return httpx.Response(200, json={"id": "task-httpx", "status": "running"})

    transport = httpx.MockTransport(handler)

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    with mock.patch.object(target.httpx, "AsyncClient", side_effect=client_factory):
        try:
            asyncio.run(
                node._request_json(
                    "POST",
                    target.CREATE_TASK_PATH,
                    "transport-secret",
                    {"model": "test"},
                    retry=True,
                )
            )
        except target.VolcengineAPIError as exc:
            assert exc.status_code == 503
            assert exc.submission_outcome == "unknown"
        else:
            raise AssertionError("POST 503 was accepted")
        assert len(request_log) == 1

        result = asyncio.run(
            node._request_json(
                "GET",
                "/contents/generations/tasks/task-httpx",
                "transport-secret",
                retry=True,
            )
        )
    assert result["status"] == "running"
    assert len(request_log) == 4
    assert get_attempts == 3
    assert node.sleeps == [1, 2]
    assert str(request_log[0].url) == (
        "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    )
    assert request_log[0].headers["authorization"] == "Bearer transport-secret"

    request_error_cases = [
        (httpx.ConnectError, "connection"),
        (httpx.ReadError, "response-receive"),
        (httpx.WriteError, "request-send"),
        (httpx.ReadTimeout, "response-receive"),
        (httpx.RemoteProtocolError, "response-receive"),
        (httpx.DecodingError, "response-receive"),
    ]
    for error_class, expected_phase in request_error_cases:
        error_requests: list[httpx.Request] = []

        async def error_handler(request: httpx.Request) -> httpx.Response:
            error_requests.append(request)
            raise error_class(
                "raw transport detail must remain hidden transport-secret",
                request=request,
            )

        error_transport = httpx.MockTransport(error_handler)

        def error_client_factory(*args, **kwargs):
            kwargs["transport"] = error_transport
            return original_async_client(*args, **kwargs)

        with mock.patch.object(
            target.httpx, "AsyncClient", side_effect=error_client_factory
        ):
            try:
                asyncio.run(
                    node._request_json(
                        "POST",
                        target.CREATE_TASK_PATH,
                        "transport-secret",
                        {"prompt": "private prompt"},
                        retry=True,
                    )
                )
            except target.VolcengineAPIError as exc:
                assert exc.submission_outcome == "unknown"
                assert error_class.__name__ in str(exc)
                assert expected_phase in str(exc)
                assert "raw transport detail" not in str(exc)
                assert "transport-secret" not in str(exc)
                diagnostic = exc.response_json["submission_diagnostic"]
                assert diagnostic["network_error_type"] == error_class.__name__
                assert diagnostic["network_phase"] == expected_phase
                assert "private prompt" not in json.dumps(exc.response_json)
            else:
                raise AssertionError(f"{error_class.__name__} POST was accepted")
        assert len(error_requests) == 1

    download_requests: list[httpx.Request] = []

    async def download_handler(request: httpx.Request) -> httpx.Response:
        download_requests.append(request)
        return httpx.Response(
            200,
            content=b"\x00\x00\x00\x18ftypmp42transport-video",
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


def assert_private_monthly_usage_ledger_contract() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        share_root = temporary_path / "Griptape_list"
        queue_root = temporary_path / "local-queue"
        user_id = "user-regression-123"
        node = target.HMBSeedance20VideoGeneration(name="Usage Ledger Regression")
        node._usage_identity = {"user_id": user_id}
        node._usage_context = {
            "identity": {"user_id": user_id},
            "model": target.SEEDANCE_2_0_MODEL_ID,
            "resolution": "1080p",
            "ratio": "16:9",
            "duration": 5,
            "generate_audio": True,
            "has_video_input": True,
        }
        provider_task = {
            "id": "task-usage-regression-1",
            "status": "succeeded",
            "model": target.SEEDANCE_2_0_MODEL_ID,
            "resolution": "1080p",
            "ratio": "16:9",
            "duration": 5,
            "updated_at": 1785861000,
            "usage": {
                "completion_tokens": 35800,
                "total_tokens": 35800,
            },
            "content": {"video_url": "https://private.example/result.mp4"},
            "authorization": "Bearer must-never-be-recorded",
            "prompt": "must-never-be-recorded",
        }
        event = node._build_usage_event(
            provider_task,
            "task-usage-regression-1",
            "succeeded",
        )
        assert event is not None
        event_dump = json.dumps(event)
        assert "must-never-be-recorded" not in event_dump
        assert "private.example" not in event_dump
        assert event["generator"] == "HMBSeedance20VideoGeneration"
        assert event["total_tokens"] == 35800
        assert event["rate_cny_per_million_tokens"] == "28"
        assert event["estimated_cost_cny"] == "1.0024"
        event["recorded_at"] = "2026-08-05T00:00:00+09:00"

        with mock.patch.object(target, "USAGE_LEDGER_ROOT", share_root), mock.patch.object(
            target, "USAGE_LOCAL_QUEUE_ROOT", queue_root
        ):
            queued = node._enqueue_usage_event(event)
            assert queued.is_file()
            node._flush_usage_queue()
            assert not queued.exists()

            ledger_path = share_root / user_id / f"{user_id}.json"
            assert ledger_path.is_file()
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            assert ledger["generator"] == "HMBSeedance20VideoGeneration"
            assert ledger["user_id"] == user_id
            assert len(ledger["months"]) == 1
            month_key = next(iter(ledger["months"]))
            month = ledger["months"][month_key]
            assert month["summary"]["task_count"] == 1
            assert month["summary"]["succeeded"] == 1
            assert month["summary"]["total_tokens"] == 35800
            assert month["summary"]["estimated_cost_cny"] == "1.0024"
            assert list(month["tasks"]) == ["task-usage-regression-1"]
            assert "content" not in month["tasks"]["task-usage-regression-1"]
            assert "authorization" not in ledger_path.read_text(encoding="utf-8")

            # Replaying a task updates it instead of increasing the count.
            replay = dict(event)
            replay["recorded_at"] = "2026-08-05T23:59:59+09:00"
            node._enqueue_usage_event(replay)
            node._flush_usage_queue()
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            month = next(iter(ledger["months"].values()))
            assert month["summary"]["task_count"] == 1
            assert month["summary"]["total_tokens"] == 35800

            # A newer completion month moves the same task; it is never duplicated.
            next_month = dict(event)
            next_month["billing_month"] = "2026-09"
            next_month["recorded_at"] = "2026-09-01T00:00:01+09:00"
            node._enqueue_usage_event(next_month)
            node._flush_usage_queue()
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            assert list(ledger["months"]) == ["2026-09"]
            assert ledger["months"]["2026-09"]["summary"]["task_count"] == 1

            # A disconnected/unusable share retains the local event for retry.
            offline_root = temporary_path / "offline-root"
            offline_root.write_text("not a directory", encoding="utf-8")
            retry_event = dict(event)
            retry_event["task_id"] = "task-usage-regression-2"
            retry_event["billing_month"] = "2026-09"
            retry_event["recorded_at"] = "2026-09-02T00:00:01+09:00"
            with mock.patch.object(target, "USAGE_LEDGER_ROOT", offline_root):
                retry_path = node._enqueue_usage_event(retry_event)
                node._flush_usage_queue()
                assert retry_path.is_file()
            node._flush_usage_queue()
            assert not retry_path.exists()
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            assert ledger["months"]["2026-09"]["summary"]["task_count"] == 2

            foreign = dict(event)
            foreign["generator"] = "AnotherSeedanceGenerator"
            try:
                node._enqueue_usage_event(foreign)
            except ValueError as exc:
                assert "different generator" in str(exc)
            else:
                raise AssertionError("Another generator entered the HMB usage queue")

            assert not list(share_root.rglob("*.tmp"))
            assert not list(queue_root.rglob("*.tmp"))

        integration_share = temporary_path / "integration-share"
        integration_queue = temporary_path / "integration-queue"

        class UsageScriptedNode(ScriptedNode):
            def _capture_usage_identity(self):
                self._usage_identity = {"user_id": user_id}
                return dict(self._usage_identity)

        integration_node = UsageScriptedNode(
            [
                {
                    "id": "task-regression-1",
                    "status": "succeeded",
                    "model": target.SEEDANCE_2_0_MODEL_ID,
                    "resolution": "720p",
                    "duration": 5,
                    "usage": {"completion_tokens": 1000, "total_tokens": 1000},
                    "content": {"video_url": "https://cdn.example/result.mp4"},
                }
            ]
        )
        integration_node.set_parameter_value("prompt", "private integration prompt")
        with mock.patch.object(
            target, "USAGE_LEDGER_ROOT", integration_share
        ), mock.patch.object(
            target, "USAGE_LOCAL_QUEUE_ROOT", integration_queue
        ), mock.patch.object(
            UsageScriptedNode, "_schedule_usage_flush", return_value=None
        ):
            asyncio.run(integration_node._process_generation())
            assert len(list(integration_queue.glob("*/*.json"))) == 2
            integration_node._flush_usage_queue()
            integration_ledger_path = (
                integration_share / user_id / f"{user_id}.json"
            )
            integration_ledger = json.loads(
                integration_ledger_path.read_text(encoding="utf-8")
            )
            integration_month = next(iter(integration_ledger["months"].values()))
            assert integration_month["summary"]["task_count"] == 1
            assert integration_month["summary"]["succeeded"] == 1
            assert integration_month["summary"]["total_tokens"] == 1000
            integration_dump = json.dumps(integration_ledger)
            assert "private integration prompt" not in integration_dump
            assert "cdn.example" not in integration_dump


assert_constructor_and_public_contract()
assert_image_asset_single_wire_host_contract()
assert_video_picker_single_wire_host_contract()
assert_secret_manager_contract()
assert_payload_and_media_contract()
assert_broker_generation_contract()
assert_broker_account_and_button_contract()
assert_scripted_success_flow()
assert_indexed_output_macro_contract()
assert_local_video_temporary_publication()
assert_tos_local_video_temporary_publication()
assert_resume_flow_skips_post()
assert_refresh_recovery_contract()
assert_ambiguous_submission_status_contract()
assert_http_transport_contract()
assert_private_monthly_usage_ledger_contract()

print("HMB Seedance 2.0 FN AI Broker regression: PASS")
