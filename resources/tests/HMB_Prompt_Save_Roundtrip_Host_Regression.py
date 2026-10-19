"""Installed SDK save boundary, using synthetic data and an isolated engine.

No user workflow is read or executed. This exercises the real reference-node
construction, workflow code generation, temporary atomic write and command
roundtrip; it does not establish a live editor or network-share save outcome.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
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
os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(
    Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
CHANNEL = "11111111-1111-4111-8111-111111111111"
SHOTS = [dict(channel_uuid=CHANNEL, shot_uuid=f"22222222-2222-4222-8222-{number:012d}",
    number=number, name=f"Asset authored name {number}", selected_source_uids=[])
    for number in range(1, 6)]
ATTEMPTS: list[str] = []
NATIVE_WAKEUPS: list[bool] = []


def deny(*args, **kwargs):
    ATTEMPTS.append("external work")
    raise AssertionError("Save fixture must not execute models, render or use network")


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def edge_records(engine, flow):
    return sorted((item.source_node.name, item.source_parameter.name,
        item.target_node.name, item.target_parameter.name)
        for item in engine.flow_manager._get_connections_for_flow(flow))


async def exercise(engine, directory):
    import HMBImageAssetLibrary as images
    import HMBVideoPickerLibrary as pickers
    import HMBPromptLibrary as prompts
    import HMBAgentLibrary as agents
    import HMBFinishLookLibrary as finishes
    import HMBSeedanceGeneration as generators
    import _hmb_shot_routing as routing
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.flow_events import (
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest)
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest
    from griptape_nodes.serialization.values import decode_value, encode_value
    from griptape_nodes.utils import file_utils

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    classes = {cls.__name__: cls for cls in (images.HMBImageAssetLibrary, pickers.HMBVideoPickerLibrary,
        prompts.HMBPromptLibrary, agents.HMBAgentLibrary, finishes.HMBFinishLookLibrary,
        generators.HMBSeedanceGeneration)}
    for definition in schema.nodes:
        cls = classes.get(definition.class_name)
        if cls is not None:
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    engine.event_manager.initialize_queue()
    reference_nodes = []
    try:
        ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="SyntheticPromptSaveRoundtrip"))
        flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)

        def create(kind, name):
            result = send(engine, CreateNodeRequest(node_type=kind, node_name=name,
                specific_library_name=schema.name, initial_setup=True))
            return engine.node_manager.get_node_by_name(result.node_name)

        image = create("HMBImageAssetLibrary", "Synthetic Image")
        picker = create("HMBVideoPickerLibrary", "Synthetic Picker")
        prompt = create("HMBPromptLibrary", "Synthetic Prompt manager")
        agent = create("HMBAgentLibrary", "Synthetic Agent manager")
        finish = create("HMBFinishLookLibrary", "Synthetic Finish manager")
        gens = [create("HMBSeedanceGeneration", f"Opaque Generator {9-number}") for number in range(1, 6)]
        catalog_document = dict(channel_uuid=CHANNEL, generation=10,
            shots=[dict(shot_uuid=row["shot_uuid"], number=row["number"], name=row["name"], revision=10)
                for row in SHOTS])
        catalog = dict(schema=prompts.SHOT_ROUTING_CATALOG_SCHEMA, version=1,
            publisher_instance_uuid=CHANNEL, **catalog_document, metadata_sha256=digest(catalog_document))
        state = prompts._normalize_state(dict(prompts._default_widget_state(), multi_shot_enabled=True,
            shot=SHOTS[0], image_asset=dict(project_id="katuri8", shot_catalog=SHOTS,
                shot_catalog_routing=prompts._catalog_routing_projection(catalog))))
        text_key = next(iter(prompts.TEXT_FIELD_DEFAULTS))
        for row in SHOTS:
            state = prompts._select_prompt_shot_document(state, row)
            state["text"][text_key] = f"Synthetic literal {row['number']} {{literal}} RGB(12, 34, 56) OFF 0"
            state["images"][0]["label"] = f"Authored image {row['number']}"
            state["images"][0]["color_picks"] = ["Red" if row["number"] % 2 else "Blue"]
            state["videos"][0]["keep_out"] = f"OFF 0 literal boundary {row['number']}"
            state["ui"]["textarea_heights"] = {"video:1:keep_out": 80 + row["number"]}
            state[prompts.UI_EDIT_REVISION_KEY] += 1
            state = prompts._store_prompt_shot_document(state)
        state = prompts._select_prompt_shot_document(state, SHOTS[2])
        state[prompts.SOURCE_SYNC_REVISION_KEY], state[prompts.UI_EDIT_REVISION_KEY] = 100, 30
        send(engine, SetParameterValueRequest(node_name=prompt.name, parameter_name=prompts.WIDGET_PARAMETER_NAME,
            value=prompts._json_dumps(state), initial_setup=True))
        expected_prompt = deepcopy(prompt._current_state())

        # Distinct native slots and Finish documents make roundtrip data loss
        # visible without constructing any real Agent or provider job.
        for row in SHOTS:
            key = agent._hmb_slot_key(CHANNEL, row["shot_uuid"])
            slot = agent._hmb_native_slot_snapshot()
            slot["values"].update(prompt=f"Synthetic Agent input {row['number']} {{literal}}", include_details=False,
                additional_context=f"RGB(12, 34, 56) OFF 0 {row['number']}", agent=None)
            slot["outputs"] = dict(output=f"Synthetic stored result {row['number']}", logs="", agent=None)
            agent._hmb_shot_slots[key] = slot
        agent._hmb_persist_shot_store()
        expected_agent = deepcopy(agent._native_parameter_value(agents._AGENT_SHOT_STORE_PARAMETER))
        finish_documents = {}
        for row in SHOTS:
            document = finish._hmb_finish_current_document()
            document["finish_look"]["beauty"].update(enabled=row["number"] % 2 == 1,
                brightness=1 + row["number"] / 10, blur_amount=0)
            document["seen_remote_requests"] = [f"synthetic-request-{row['number']}"]
            finish_documents[finish._hmb_finish_key(CHANNEL, row["shot_uuid"])] = document
        finish_store = dict(schema=finishes.SHOT_STORE_SCHEMA, version=1, documents=finish_documents,
            archives={}, remote_owners={}, active=finish._hmb_finish_key(CHANNEL, SHOTS[2]["shot_uuid"]))
        send(engine, SetParameterValueRequest(node_name=finish.name, parameter_name=finishes.SHOT_STORE_PARAMETER_NAME,
            value=deepcopy(finish_store), initial_setup=True))

        for row, generator in zip(SHOTS, gens):
            for name, value in (("shot_channel_uuid", CHANNEL), ("shot_uuid", row["shot_uuid"]),
                ("shot_name", row["name"]), ("shot_number", row["number"]), ("resolution", "480p"),
                ("output_format", "mov"), ("duration", 4), ("generate_audio", False),
                ("draft_job_id", "job-" + str(row["number"]) * 32),
                ("resume_generation_id", "job-" + str(row["number"] + 1) * 32)):
                generator.set_parameter_value(name, value, initial_setup=True)

        def connect(source, output, target, input_name):
            send(engine, CreateConnectionRequest(source_node_name=source.name, source_parameter_name=output,
                target_node_name=target.name, target_parameter_name=input_name, initial_setup=True))

        connect(prompt, "PROMPT_OUT", agent, "SHOT_PROMPT_IN")
        for generator in gens:
            connect(agent, "output", generator, "prompt")
            connect(finish, "SHOT_FINISH_LOOK_OUT", generator, "SHOT_FINISH_LOOK_IN")
            connect(image, "SHOT_ASSET_OUT", generator, "SHOT_ASSET_IN")
            connect(picker, "SHOT_PICKER_OUT", generator, "SHOT_PICKER_IN")
        await asyncio.sleep(0)  # Drain construction-only deferred callbacks.
        # The exact live Prompt state is the authority after initial hydration.
        # A repeated source ACK must leave both native stored state and clocks unchanged.
        expected_prompt = deepcopy(prompt._current_state())
        expected_raw = prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME)
        with mock.patch.object(prompts, "_set_parameter_value", wraps=prompts._set_parameter_value) as writes:
            for _ in range(120):
                prompt._hmb_reconcile_shot_routing(routing_snapshot=deepcopy(catalog))
            assert writes.call_count == 0, "Identical catalog ACK published a native widget update"
        assert prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME) == expected_raw
        assert prompt._current_state() == expected_prompt
        edges_before = edge_records(engine, flow)
        assert len(edges_before) == 21
        assert len(expected_prompt["shot_documents"]) == 5
        generator_values = {node.name: {key: encode_value(node._get_raw_parameter_value(key)) for key in
            ("shot_channel_uuid", "shot_uuid", "shot_name", "shot_number", "resolution", "output_format",
             "duration", "generate_audio", "draft_job_id", "resume_generation_id")} for node in gens}

        with ExitStack() as reference_spy:
            for cls in classes.values():
                original = cls.__init__
                def measured(self, *args, _original=original, **kwargs):
                    if kwargs.get("name") == "REFERENCE NODE":
                        reference_nodes.append(type(self).__name__)
                    _original(self, *args, **kwargs)
                reference_spy.enter_context(mock.patch.object(cls, "__init__", measured))
            serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name,
                include_create_flow_command=True)).serialized_flow_commands
        assert len(reference_nodes) == 10, reference_nodes
        assert reference_nodes.count("HMBSeedanceGeneration") == 5
        assert prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME) == expected_raw
        assert edge_records(engine, flow) == edges_before

        path = directory / "synthetic_save_roundtrip.py"
        promotions = []
        original_promote = file_utils.promote_scratch_file
        def promote(scratch, destination):
            # OSManager uses the equivalent Windows extended-length spelling.
            compared_destination = Path(str(destination).removeprefix("\\\\?\\")).resolve()
            assert compared_destination.is_relative_to(directory.resolve())
            assert scratch.parent == destination.parent and scratch.name.startswith(".gtn-write-partial-")
            if compared_destination == path.resolve():
                promotions.append(scratch.name)
            return original_promote(scratch, destination)
        request = lambda: SaveWorkflowFileFromSerializedFlowRequest(serialized_flow_commands=serialized,
            file_name=path.stem, file_path=str(path), display_name="Synthetic save only", broadcast_result=False)
        original_handle = type(engine).handle_request
        def inspect_file_request(current_engine, value=None, **kwargs):
            value = kwargs.get("request", value)
            result = original_handle(current_engine, value)
            if type(value).__name__ == "WriteFileRequest" and not result.succeeded():
                error = getattr(result, "exception", None)
                if error is not None:
                    import traceback
                    raise AssertionError("Synthetic SDK file write boundary failed: " + "".join(traceback.format_exception(error)))
                raise AssertionError(f"Synthetic SDK file write boundary failed: {result.result_details}")
            return result
        with mock.patch.object(file_utils, "promote_scratch_file", promote), mock.patch.object(type(engine), "handle_request", inspect_file_request):
            saved = await engine.ahandle_request(request())
        assert saved.succeeded(), str(saved.result_details)
        assert promotions and len(promotions) == 1
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(path))
        compile(tree, str(path), "exec")  # Syntax only: do not execute generated Python.
        pool = next(ast.literal_eval(item.value) for item in ast.walk(tree) if isinstance(item, ast.Assign)
            and any(isinstance(name, ast.Name) and name.id == "top_level_unique_values_dict" for name in item.targets))
        decoded = [decode_value(value) for value in pool.values()]
        assert expected_raw in decoded, "Generated Python omitted exact Prompt authoring state"
        assert expected_agent in decoded, "Generated Python omitted native Agent Shot store"
        assert finish_store in decoded, "Generated Python omitted five Finish documents"
        assert not list(directory.glob(".gtn-write-partial-*"))
        complete_bytes = path.read_bytes()
        # Persistent rename failure must not destroy the previous complete file.
        with mock.patch.object(file_utils, "promote_scratch_file", side_effect=PermissionError("synthetic denied rename")):
            failed = await engine.ahandle_request(request())
        assert not failed.succeeded()
        assert path.read_bytes() == complete_bytes
        assert not list(directory.glob(".gtn-write-partial-*"))

        send(engine, DeleteFlowRequest(flow_name=flow.name))
        loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=serialized, broadcast_result=False))
        assert loaded.succeeded(), str(loaded.result_details)
        restored = engine.flow_manager.get_flow_by_name(loaded.flow_name)
        assert len(restored.nodes) == 10
        assert edge_records(engine, restored) == edges_before
        restored_prompt = restored.nodes[prompt.name]
        assert restored_prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME) == expected_raw
        assert restored_prompt._current_state() == expected_prompt
        assert restored.nodes[agent.name]._native_parameter_value(agents._AGENT_SHOT_STORE_PARAMETER) == expected_agent
        assert restored.nodes[finish.name]._get_raw_parameter_value(finishes.SHOT_STORE_PARAMETER_NAME) == finish_store
        for name, values in generator_values.items():
            assert {key: encode_value(restored.nodes[name]._get_raw_parameter_value(key)) for key in values} == values
        for row in SHOTS:
            view = prompts._select_prompt_shot_document(deepcopy(expected_prompt), row)
            assert view["text"][text_key] == f"Synthetic literal {row['number']} {{literal}} RGB(12, 34, 56) OFF 0"
            assert view["videos"][0]["keep_out"] == f"OFF 0 literal boundary {row['number']}"
            assert view["images"][0]["color_picks"] == ["Red" if row["number"] % 2 else "Blue"]
        assert not ATTEMPTS, ATTEMPTS
        print("HMB_PROMPT_SAVE_ROUNDTRIP_HOST=PASS (actual SDK10 reference constructors; 120 catalog ACK/write0; codegen AST; native temp atomic save + denied-rename old-file protection; 10 nodes/21 exact edges + five Prompt/Agent/Finish bodies preserved; RGB/OFF/0/literals; Draft/Resume/480p unchanged; model/render/network0)")
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-prompt-save-sdk-") as temporary:
        base = Path(temporary)
        env = {key: str(base / leaf) for key, leaf in (("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
            ("LOCALAPPDATA", "local"), ("APPDATA", "app"), ("GTN_ENGINE_CONFIG_DIR", "engine-config"),
            ("GTN_ENGINE_DATA_DIR", "engine-data"), ("GTN_ENGINE_STATE_DIR", "engine-state"),
            ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "images"))}
        for target in env.values():
            Path(target).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), ExitStack() as guard:
            os.chdir(base)
            try:
                guard.enter_context(mock.patch.object(socket, "create_connection", deny))
                import HMBImageAssetLibrary as images
                import HMBVideoPickerLibrary as pickers
                import HMBPromptLibrary as prompts
                import HMBAgentLibrary as agents
                import HMBSeedanceGeneration as generators
                import _hmb_shot_routing as routing
                for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                    guard.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
                guard.enter_context(mock.patch.object(images.HMBImageAssetLibrary, "_schedule_catalog_scan", lambda *a, **k: None))
                guard.enter_context(mock.patch.object(pickers.HMBVideoPickerLibrary, "_schedule_video_removal_output_sync", lambda *a, **k: None))
                guard.enter_context(mock.patch.object(prompts.HMBPromptLibrary, "_schedule_prompt_sync", lambda *a, **k: None))
                guard.enter_context(mock.patch.object(agents.HMBAgentLibrary, "process", deny))
                guard.enter_context(mock.patch.object(agents.HMBAgentLibrary, "_hmb_run_agent_shot", deny))
                guard.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", deny))
                logging.disable(logging.CRITICAL)
                from griptape_nodes.retained_mode.engine import engine_scope
                native_connect = socket.socket.connect
                def guarded_connect(sock, address):
                    caller = sys._getframe(1)
                    if caller.f_code.co_name == "_fallback_socketpair" and Path(caller.f_code.co_filename).name == "socket.py":
                        assert address[0] in {"127.0.0.1", "::1"}
                        NATIVE_WAKEUPS.append(True)
                        return native_connect(sock, address)
                    return deny(sock, address)
                # Windows creates a private loopback socketpair for its own
                # event-loop wakeup. SDK ThreadRunner may create another one;
                # allow only that standard-library call site, not transport.
                with asyncio.Runner() as runner:
                    runner.get_loop()
                    with mock.patch.object(socket.socket, "connect", guarded_connect), mock.patch.object(socket.socket, "connect_ex", deny):
                        with engine_scope() as engine:
                            runner.run(exercise(engine, base))
            finally:
                logging.shutdown()
                os.chdir(previous)


if __name__ == "__main__":
    main()
