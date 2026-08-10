from __future__ import annotations

import asyncio
import copy
import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

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


def load_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load regression target: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


picker = load_module(
    "hmb_picker_seedance_video_integration_picker",
    "HMBVideoPickerLibrary.py",
)
seedance = load_module(
    "hmb_picker_seedance_video_integration_seedance",
    "HMBSeedanceGeneration.py",
)


def register_node(flow: Any, node: Any) -> None:
    flow.add_node(node)
    GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name


def video_url(number: int) -> str:
    return f"https://example.test/hmb-picker-video-{number}.mp4"


def submit_picker_order(
    source: Any,
    ordered_numbers: tuple[int, ...],
) -> list[str]:
    """Submit the exact complete widget snapshot used by a card reorder."""
    current = copy.deepcopy(source._picker_state())
    order_by_number = {
        number: selection_order
        for selection_order, number in enumerate(ordered_numbers, start=1)
    }
    current["videos"] = [
        {
            "video_uid": f"video-{number}",
            "source_uid": f"video-{number}",
            "catalog_order": number,
            "video_url": video_url(number),
            "selected": number in order_by_number,
            "selection_order": order_by_number.get(number, 0),
            "video_slot": order_by_number.get(number, 0),
            "source_fps": 24.0,
            "source_frame_count": 24,
            "decoded_frame_count": 24,
            "source_duration_seconds": 1.0,
        }
        for number in range(1, 5)
    ]
    current["state_writer"] = "widget"
    current["runtime_instance_id"] = source._hmb_runtime_instance_id
    current["state_revision"] = int(current.get("state_revision") or 0) + 1
    result = GriptapeNodes.handle_request(
        SetParameterValueRequest(
            node_name=source.name,
            parameter_name=picker.WIDGET_STATE_PARAMETER,
            value=current,
            data_type="dict",
        )
    )
    assert isinstance(result, SetParameterValueResultSuccess), (
        type(result).__name__,
        getattr(result, "result_details", ""),
    )
    expected = [video_url(number) for number in ordered_numbers]
    assert source.parameter_output_values[picker.VIDEO_OUTPUT_PARAMETER] == expected
    return expected


def assert_single_video_output_surface(destination: Any) -> None:
    preview = destination.get_parameter_by_name("video_url")
    connector = destination.get_parameter_by_name("VIDEO_OUT")
    assert type(preview).__name__ == "ParameterVideo"
    assert preview.allowed_modes == {seedance.ParameterMode.PROPERTY}
    assert connector.allowed_modes == {seedance.ParameterMode.OUTPUT}
    assert connector.output_type == "VideoUrlArtifact"

    video_artifact_outputs = [
        parameter.name
        for parameter in destination.parameters
        if seedance.ParameterMode.OUTPUT in parameter.allowed_modes
        and str(parameter.output_type or parameter.type) == "VideoUrlArtifact"
    ]
    assert video_artifact_outputs == ["VIDEO_OUT"], video_artifact_outputs


def assert_single_video_input_surface(source: Any, destination: Any) -> None:
    source_output = source.get_parameter_by_name(picker.VIDEO_OUTPUT_PARAMETER)
    destination_input = destination.get_parameter_by_name(
        seedance.VIDEO_REFERENCES_PARAMETER
    )
    assert source_output.output_type == "list[str]"
    assert destination_input.type == "list[str]"
    assert source_output.output_type in destination_input.input_types
    assert destination_input.allowed_modes == {seedance.ParameterMode.INPUT}
    assert destination_input.hide is False
    assert destination_input.hide_property is True
    assert destination_input.ui_options["display_name"] == "Reference Videos"

    # Scalar ports remain hidden only for saved-workflow migration. The user has
    # one visible list connector, so a Picker selection never needs re-wiring.
    for index in range(1, seedance.MAX_VIDEO_REFERENCES + 1):
        legacy = destination.get_parameter_by_name(f"reference_video_{index}")
        assert legacy.hide is True
        assert legacy.ui_options["display_name"] == (
            f"Legacy Reference Video {index}"
        )


def assert_host_connection_reorder_and_payload() -> None:
    context_manager = GriptapeNodes.ContextManager()
    assert not context_manager.has_current_workflow(), (
        "Picker/Seedance host integration must run in an isolated process."
    )
    GriptapeNodes.EventManager().initialize_queue()
    stamp = time.time_ns()
    ensured = GriptapeNodes.handle_request(
        EnsureWorkflowAndFlowRequest(
            display_name=f"HMB Picker Seedance Video Integration {stamp}",
            flow_name=f"HMBPickerSeedanceVideoFlow_{stamp}",
        )
    )
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess), (
        type(ensured).__name__,
        getattr(ensured, "result_details", ""),
    )
    flow = GriptapeNodes.FlowManager().get_flow_by_name(ensured.flow_name)

    try:
        source = picker.HMBVideoPickerLibrary(name=f"VideoPicker_{stamp}")
        destination = seedance.HMBSeedanceGeneration(
            name=f"Seedance_{stamp}"
        )
        register_node(flow, source)
        register_node(flow, destination)

        assert_single_video_input_surface(source, destination)
        assert_single_video_output_surface(destination)

        initial = submit_picker_order(source, (1, 2, 3, 4))
        connected = GriptapeNodes.handle_request(
            CreateConnectionRequest(
                source_node_name=source.name,
                source_parameter_name=picker.VIDEO_OUTPUT_PARAMETER,
                target_node_name=destination.name,
                target_parameter_name=seedance.VIDEO_REFERENCES_PARAMETER,
            )
        )
        assert isinstance(connected, CreateConnectionResultSuccess), (
            type(connected).__name__,
            getattr(connected, "result_details", ""),
        )
        assert destination.get_parameter_value(
            seedance.VIDEO_REFERENCES_PARAMETER
        ) == initial

        listed = GriptapeNodes.handle_request(
            ListConnectionsForNodeRequest(node_name=destination.name)
        )
        assert isinstance(listed, ListConnectionsForNodeResultSuccess)
        incoming = [
            edge
            for edge in listed.incoming_connections
            if edge.target_parameter_name == seedance.VIDEO_REFERENCES_PARAMETER
        ]
        assert len(incoming) == 1
        assert incoming[0].source_node_name == source.name
        assert incoming[0].source_parameter_name == picker.VIDEO_OUTPUT_PARAMETER

        # This is the reported usability failure: move selected video 4 directly
        # to position 1 without deselecting and rebuilding the full selection.
        reordered_four = submit_picker_order(source, (4, 1, 2, 3))
        assert reordered_four[0] == video_url(4)
        assert destination.get_parameter_value(
            seedance.VIDEO_REFERENCES_PARAMETER
        ) == reordered_four
        assert destination._get_parameters()["video_references"] == reordered_four

        # Four selected videos must fail before any billable POST, and no item may
        # be silently discarded to fit Seedance's three-video provider limit.
        destination.set_parameter_value("prompt", "four-video preflight rejection")
        broker_calls: list[tuple[Any, ...]] = []

        async def forbidden_broker_connection(
            *args: Any, **kwargs: Any
        ) -> dict[str, Any]:
            broker_calls.append((*args, kwargs))
            raise AssertionError("Broker connection occurred before preflight rejection")

        destination._ensure_broker_connected = forbidden_broker_connection
        try:
            asyncio.run(destination._process_generation_impl())
        except ValueError as exc:
            assert "at most 3 reference videos" in str(exc)
        else:
            raise AssertionError("Four connected Picker videos were accepted")
        assert broker_calls == []

        # Deselecting only the fourth-position item leaves the requested 4->1
        # order intact. The resulting three URLs become Broker media in that order.
        ordered_three = submit_picker_order(source, (4, 1, 2))
        assert destination.get_parameter_value(
            seedance.VIDEO_REFERENCES_PARAMETER
        ) == ordered_three
        params = destination._get_parameters()
        assert params["video_references"] == ordered_three
        assert params["video_reference_slots"] == []
        destination._validate_parameters(params)
        payload = destination._build_broker_payload(params)
        assert payload["video_urls"] == ordered_three
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


assert_host_connection_reorder_and_payload()

print("HMB Picker -> Seedance ordered video integration regression: PASS")
