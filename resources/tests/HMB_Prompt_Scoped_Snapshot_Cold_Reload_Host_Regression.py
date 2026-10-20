"""Real SDK cold reopen rebases five exact source views with high saved clocks."""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
CHANNEL = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PUBLISHER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROWS = [dict(shot_uuid=f"cccccccc-cccc-4ccc-8ccc-{n:012d}", number=n,
    name=f"Exact asset {n}", revision=1, selected_source_uids=[f"import:image-{n}"])
    for n in range(1, 6)]


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


async def exercise(engine):
    import HMBImageAssetLibrary as images
    import HMBVideoPickerLibrary as pickers
    import HMBPromptLibrary as prompts
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.flow_events import (
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest)
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    classes = {cls.__name__: cls for cls in (images.HMBImageAssetLibrary,
        pickers.HMBVideoPickerLibrary, prompts.HMBPromptLibrary)}
    for definition in schema.nodes:
        cls = classes.get(definition.class_name)
        if cls:
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    engine.event_manager.initialize_queue()
    try:
        result = send(engine, EnsureWorkflowAndFlowRequest(flow_name="PrivateScopedColdReload"))
        flow = engine.flow_manager.get_flow_by_name(result.flow_name)
        def create(kind, name):
            result = send(engine, CreateNodeRequest(node_type=kind, node_name=name,
                specific_library_name=schema.name, initial_setup=True))
            return engine.node_manager.get_node_by_name(result.node_name)
        image = create("HMBImageAssetLibrary", "Real scoped Image")
        picker = create("HMBVideoPickerLibrary", "Real scoped Picker")
        prompt = create("HMBPromptLibrary", "Real scoped Prompt")
        image_state = images._default_state()
        image_state.update(project_id="superwings12", assets=[dict(
            asset_library_id=f"import:image-{n}", source_uid=f"import:image-{n}", source_kind="user",
            asset_id=f"actor-{n}", image_name=f"Actor {n}", path=f"https://media.invalid/image-{n}.png",
            selected=True, selection_order=n, import_index=n, connected=True,
            registered=False, media_ref_kind="url") for n in range(1, 6)])
        image_state["shot_routing"].update(channel_uuid=CHANNEL, publisher_instance_uuid=PUBLISHER,
            generation=1, active_shot_uuid=ROWS[0]["shot_uuid"], shots=deepcopy(ROWS))
        send(engine, SetParameterValueRequest(node_name=image.name,
            parameter_name=images.WIDGET_STATE_PARAMETER, value=images._json_text(image_state), initial_setup=True))
        image._hmb_initial_catalog_scan_pending = False
        picker_state = pickers._default_widget_state()
        picker_state.update(channel_uuid=CHANNEL, shot_publisher_instance_uuid=PUBLISHER,
            shot_uuid=ROWS[0]["shot_uuid"], shot_number=1, shot_name=ROWS[0]["name"],
            shot_selections=[{**row, "selected_source_uids": []} for row in ROWS], videos=[], picker_shots=[])
        for n, row in enumerate(ROWS, 1):
            uid = f"video-{n}"
            workspace = pickers._new_picker_workspace_row(n, bound_shot_uuid=row["shot_uuid"],
                video_asset_uids=[uid], selected_video_uids=[uid], preview_video_uid=uid)
            picker_state["picker_shots"].append(workspace)
            picker_state["videos"].append(dict(video_uid=uid, source_uid=uid,
                picker_shot_uuid=workspace["workspace_uuid"], label=uid,
                video_url=f"https://media.invalid/video-{n}.mp4", selected=n == 1,
                selection_order=1 if n == 1 else 0, video_slot=1 if n == 1 else 0))
        picker_state["active_picker_shot_uuid"] = picker_state["picker_shots"][0]["workspace_uuid"]
        picker_state["state_writer"] = "python"
        send(engine, SetParameterValueRequest(node_name=picker.name,
            parameter_name=pickers.WIDGET_STATE_PARAMETER, value=picker_state, initial_setup=True))

        def bind_publisher_state(image, picker):
            catalog = image._hmb_shot_routing_catalog()
            picker._hmb_shot_catalog_snapshot = deepcopy(catalog)
            picker._hmb_shot_route_status = dict(ok=True, code="ready")
            return catalog

        catalog = bind_publisher_state(image, picker)
        assert catalog["channel_uuid"] == CHANNEL, ("image", catalog["channel_uuid"])
        assert picker._picker_state()["channel_uuid"] == CHANNEL, ("picker", picker._picker_state()["channel_uuid"])
        state = prompts._normalize_state({**prompts._default_widget_state(), "multi_shot_enabled": True,
            "shot": {**ROWS[0], "channel_uuid": CHANNEL}, "image_asset": dict(project_id="superwings12",
                shot_catalog=[{**row, "channel_uuid": CHANNEL} for row in ROWS],
                shot_catalog_routing=prompts._catalog_routing_projection(catalog))})
        text_field = next(iter(prompts.TEXT_FIELD_DEFAULTS))
        for n, row in enumerate(ROWS, 1):
            state = prompts._select_prompt_shot_document(state, {**row, "channel_uuid": CHANNEL})
            state["text"][text_field] = f"Cold-reload exact literal {n} {{SIGN}} OFF 0"
            state = prompts._store_prompt_shot_document(state)
        prompt._hmb_write_merged_prompt_state(prompts._json_dumps(state))
        for source, output, input_name in ((image, "SHOT_ASSET_OUT", "SHOT_ASSET_IN"),
                (picker, "SHOT_PICKER_OUT", "SHOT_PICKER_IN")):
            send(engine, CreateConnectionRequest(source_node_name=source.name, source_parameter_name=output,
                target_node_name=prompt.name, target_parameter_name=input_name, initial_setup=True))
        prompt._reconcile_connected_source_inputs_from_graph()

        async def warm(image, picker):
            for row in ROWS:
                await asyncio.to_thread(image._hmb_shot_routing_snapshot_for,
                    channel_uuid=CHANNEL, shot_uuid=row["shot_uuid"])
            state = picker._picker_state()
            _payload, _media, cache = await asyncio.to_thread(picker._prepare_execution_media, state)
            picker._hmb_verified_media = (picker._execution_media_identity(state), cache)

        await warm(image, picker)
        for _ in range(24):
            for n, row in enumerate(ROWS, 1):
                state = prompts._select_prompt_shot_document(state, {**row, "channel_uuid": CHANNEL})
                state, image_media, video_media, image_exact, picker_exact = prompt._apply_exact_shot_routes(state)
                assert image_exact and picker_exact
                assert image_media == [f"https://media.invalid/image-{n}.png"]
                assert video_media == [f"https://media.invalid/video-{n}.mp4"]
                state = prompts._store_prompt_shot_document(state)
        prompt._hmb_write_merged_prompt_state(prompts._json_dumps(state))
        saved = deepcopy(prompt._current_state())
        stored = [json.loads(value) for value in saved["shot_documents"].values()]
        assert min(doc["image_asset"]["shot_routing"]["generation"] for doc in stored) > 100
        assert min(doc["picker"]["shot_routing"]["generation"] for doc in stored) > 100
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name)).serialized_flow_commands
        original_names = set(flow.nodes)
        while engine.context_manager.has_current_flow():
            engine.context_manager.pop_flow()
        send(engine, DeleteFlowRequest(flow_name=flow.name))
        loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=serialized, broadcast_result=False))
        assert loaded.succeeded(), str(loaded.result_details)
        cold = engine.flow_manager.get_flow_by_name(loaded.flow_name)
        assert set(cold.nodes) == original_names
        image, picker, prompt = cold.nodes[image.name], cold.nodes[picker.name], cold.nodes[prompt.name]
        bind_publisher_state(image, picker)
        prompt._reconcile_connected_source_inputs_from_graph()
        assert getattr(image, "_hmb_image_snapshot_view_generation", 0) < 100
        assert getattr(picker, "_hmb_shot_snapshot_generation", 0) < 100
        await warm(image, picker)
        assert image._hmb_image_snapshot_view_generation < 100
        raw_before = prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME)
        for n in [5, 1, 4, 2, 3, 1, 5, 2, 4, 3]:
            record = prompt._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=ROWS[n - 1]["shot_uuid"])
            assert f"Cold-reload exact literal {n} {{SIGN}} OFF 0" in record["machine_prompt"]
            assert record["image_media"] == [f"https://media.invalid/image-{n}.png"]
            assert record["video_media"] == [f"https://media.invalid/video-{n}.mp4"]
        assert prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME) == raw_before
        assert len(prompt._current_state()["shot_documents"]) == 5
        print("PASS actual Image/Picker exact readers; 120 alternating views; five saved generations >100; SDK serialize/delete/cold reload; fresh lower source clocks safely rebase all five exact Prompt/media documents without UI writes")
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    from griptape_nodes.retained_mode.engine import engine_scope
    import HMBImageAssetLibrary as images
    import HMBPromptLibrary as prompts
    import _hmb_shot_routing as routing
    with tempfile.TemporaryDirectory(prefix="hmb-scoped-cold-epoch-") as temporary, ExitStack() as stack:
        root = Path(temporary)
        for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY", "HMB_IMAGE_PROJECTS_ROOT"):
            directory = root / name; directory.mkdir()
            stack.enter_context(mock.patch.dict(os.environ, {name: str(directory)}))
        stack.enter_context(mock.patch.object(socket, "create_connection", side_effect=AssertionError("No external work")))
        stack.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
        stack.enter_context(mock.patch.object(prompts.HMBPromptLibrary, "_schedule_prompt_sync", lambda *a, **k: None))
        for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
            stack.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
        logging.disable(logging.CRITICAL)
        with engine_scope() as engine:
            asyncio.run(exercise(engine))


if __name__ == "__main__":
    main()
