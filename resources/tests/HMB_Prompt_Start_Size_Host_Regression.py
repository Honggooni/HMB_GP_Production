"""Real installed SDK: Prompt startup geometry and saved authoring roundtrip.

Uses synthetic commands in an isolated engine only. No user workflow, provider,
desktop graph, or render is opened, saved, loaded, or executed.
"""
from __future__ import annotations

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
SHOTS = [dict(channel_uuid=CHANNEL, shot_uuid=f"22222222-2222-4222-8222-{n:012d}",
    number=n, name=f"Synthetic authored {n}", selected_source_uids=[]) for n in range(1, 6)]
ATTEMPTS = []
CASES = [
    ("small", {"width": 640, "height": 480}),
    ("large", {"width": 2900, "height": 2400, "authored_note": "preserve"}),
    ("partial", {"width": 990}),
    ("invalid_numbers", {"width": "invalid", "height": None}),
    ("string", "invalid saved size"),
    ("list", [640, 480]),
    ("null", None),
    ("absent", ...),
]
CASE_RESULTS = []


def deny(*args, **kwargs):
    ATTEMPTS.append("external/model/render work")
    raise AssertionError("Prompt geometry fixture cannot execute external work")


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def edges(engine, flow):
    return sorted((item.source_node.name, item.source_parameter.name,
        item.target_node.name, item.target_parameter.name)
        for item in engine.flow_manager._get_connections_for_flow(flow))


def expect_start(node, original):
    assert type(node).__name__ == "HMBPromptLibrary", type(node).__name__
    assert node.metadata["size"]["width"] == 1800
    assert node.metadata["size"]["height"] == 1350
    for key, value in (original or {}).items():
        if key != "size":
            assert node.metadata[key] == value, key
    saved_size = (original or {}).get("size")
    if isinstance(saved_size, dict):
        for key, value in saved_size.items():
            if key not in {"width", "height"}:
                assert node.metadata["size"][key] == value, key


async def exercise(engine, selected_case=None):
    import HMBPromptLibrary as prompts
    import HMBSeedanceGeneration as generators
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, SetNodeMetadataRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.flow_events import (
        SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest)
    from griptape_nodes.retained_mode.events.parameter_events import (
        AlterParameterDetailsRequest, SetParameterValueRequest)
    from griptape_nodes.serialization.values import encode_value

    assert (prompts.PROMPT_START_WIDTH, prompts.PROMPT_START_HEIGHT) == (1800, 1350)
    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    classes = {cls.__name__: cls for cls in (prompts.HMBPromptLibrary, generators.HMBSeedanceGeneration)}
    for definition in schema.nodes:
        cls = classes.get(definition.class_name)
        if cls is not None:
            library.register_lazy_node_type(definition.class_name, definition.metadata, lambda cls=cls: cls)
    engine.event_manager.initialize_queue()
    cases = [selected_case] if selected_case is not None else []
    try:
        for case_number, (label, size) in enumerate(cases):
            ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name=f"SyntheticPromptStart-{label}"))
            flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
            metadata = dict(position={"x": -123.25 + case_number, "y": 456.75},
                synthetic_annotation={"tags": ["retain", case_number], "zero": 0, "off": False},
                collapsed=False, backgroundColor="#123456")
            if size is not ...:
                metadata["size"] = deepcopy(size)
            original = deepcopy(metadata)
            prepared = prompts._prompt_start_metadata(metadata)
            assert metadata == original, "Startup helper mutated input metadata"
            assert prepared["size"]["width"] == 1800 and prepared["size"]["height"] == 1350
            result = send(engine, CreateNodeRequest(node_type="HMBPromptLibrary", node_name="Synthetic Prompt",
                specific_library_name=schema.name, metadata=metadata, initial_setup=True,
                create_error_proxy_on_failure=False))
            prompt = engine.node_manager.get_node_by_name(result.node_name)
            expect_start(prompt, original)
            # LibraryRegistry itself adds these registration fields in place.
            # The node must not modify any authored request field or saved size.
            assert {key: metadata[key] for key in original} == original
            assert set(metadata) - set(original) <= {"library_node_metadata", "library", "node_type"}

            # A user's resize remains valid while the current instance is in use.
            runtime_size = dict(width=2000 + case_number, height=1500 + case_number, runtime_note="retain")
            send(engine, SetNodeMetadataRequest(node_name=prompt.name, metadata={"size": runtime_size}))
            assert prompt.metadata["size"] == runtime_size
            # Native serialization must capture that current size honestly; only
            # the next construction normalizes it to the approved startup size.
            serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name,
                include_create_flow_command=True)).serialized_flow_commands
            assert len(serialized.serialized_node_commands) == 1
            saved_create = serialized.serialized_node_commands[0].create_node_command
            assert saved_create.metadata["size"] == runtime_size
            # Model old saved shell sizes through the SDK's real load request.
            saved_create.metadata = deepcopy(original)
            saved_metadata_copy = deepcopy(saved_create.metadata)
            send(engine, DeleteFlowRequest(flow_name=None))
            loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
                serialized_flow_commands=serialized, broadcast_result=False))
            assert loaded.succeeded(), str(loaded.result_details)
            restored_flow = engine.flow_manager.get_flow_by_name(loaded.flow_name)
            restored = restored_flow.nodes[prompt.name]
            expect_start(restored, original)
            assert {key: saved_create.metadata[key] for key in saved_metadata_copy} == saved_metadata_copy
            assert set(saved_create.metadata) - set(saved_metadata_copy) <= {"library_node_metadata", "library", "node_type"}
            # A second ordinary runtime resize is not forcibly reset by the node.
            send(engine, SetNodeMetadataRequest(node_name=restored.name,
                metadata={"size": {"width": 1975, "height": 1437}}))
            assert restored.metadata["size"] == {"width": 1975, "height": 1437}
            CASE_RESULTS.append(label)
            # Each case owns a fresh engine, including the SDK canvas pointer.
            # DeleteFlow alone is not a workflow-close operation in this SDK.

        if selected_case is not None:
            return

        ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="SyntheticPromptFiveDocuments"))
        flow = engine.flow_manager.get_flow_by_name(ensured.flow_name)
        result = send(engine, CreateNodeRequest(node_type="HMBPromptLibrary", node_name="Five Shot Prompt",
            specific_library_name=schema.name, metadata={"position": {"x": 31, "y": -89},
                "size": {"width": 5000, "height": 900}, "annotation": {"retain": [0, False, "literal"]}},
            initial_setup=True, create_error_proxy_on_failure=False))
        prompt = engine.node_manager.get_node_by_name(result.node_name)
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
            state["videos"][0]["keep_out"] = f"Authored boundary {row['number']}"
            state["ui"]["textarea_heights"] = {"video:1:keep_out": 80 + row["number"]}
            state[prompts.UI_EDIT_REVISION_KEY] += 1
            state = prompts._store_prompt_shot_document(state)
        state = prompts._select_prompt_shot_document(state, SHOTS[2])
        state[prompts.SOURCE_SYNC_REVISION_KEY], state[prompts.UI_EDIT_REVISION_KEY] = 100, 30
        send(engine, SetParameterValueRequest(node_name=prompt.name, parameter_name=prompts.WIDGET_PARAMETER_NAME,
            value=prompts._json_dumps(state), initial_setup=True))
        generators_before = {}
        for row in SHOTS:
            created = send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration",
                node_name=f"Synthetic Generator {row['number']}", specific_library_name=schema.name,
                initial_setup=True, create_error_proxy_on_failure=False))
            generator = engine.node_manager.get_node_by_name(created.node_name)
            for name, value in (("shot_channel_uuid", CHANNEL), ("shot_uuid", row["shot_uuid"]),
                ("shot_number", row["number"]), ("shot_name", row["name"]), ("resolution", "480p"),
                ("output_format", "mov"), ("duration", 4), ("generate_audio", False),
                ("draft_job_id", "job-" + str(row["number"]) * 32)):
                generator.set_parameter_value(name, value, initial_setup=True)
            send(engine, CreateConnectionRequest(source_node_name=prompt.name, source_parameter_name="PROMPT_OUT",
                target_node_name=generator.name, target_parameter_name="prompt", initial_setup=True))
            generators_before[generator.name] = {name: encode_value(generator._get_raw_parameter_value(name))
                for name in ("shot_channel_uuid", "shot_uuid", "shot_number", "shot_name", "resolution",
                    "output_format", "duration", "generate_audio", "draft_job_id")}
        await asyncio.sleep(0)
        before = deepcopy(prompt._current_state())
        raw_before = prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME)
        assert len(before["shot_documents"]) == 5
        metadata_before = deepcopy(prompt.metadata)
        edges_before = edges(engine, flow)
        assert len(edges_before) == 5
        # Old saved files also carry parameter-level shell hints. Keep their
        # replay in this actual SDK load; browser containment is a separate test.
        send(engine, AlterParameterDetailsRequest(node_name=prompt.name,
            parameter_name=prompts.WIDGET_PARAMETER_NAME,
            ui_options={"height": 1193, "widget_height": 1193, "synthetic_hint": "retain"}, initial_setup=True))
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow.name,
            include_create_flow_command=True)).serialized_flow_commands
        prompt_create = next(item.create_node_command for item in serialized.serialized_node_commands
            if item.create_node_command.node_type == "HMBPromptLibrary")
        prompt_create.metadata["size"] = {"width": 1100, "height": 1329}
        send(engine, DeleteFlowRequest(flow_name=None))
        loaded = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=serialized, broadcast_result=False))
        assert loaded.succeeded(), str(loaded.result_details)
        restored_flow = engine.flow_manager.get_flow_by_name(loaded.flow_name)
        restored_prompt = restored_flow.nodes[prompt.name]
        assert len(restored_flow.nodes) == 6
        expect_start(restored_prompt, metadata_before)
        assert edges(engine, restored_flow) == edges_before
        assert restored_prompt._get_raw_parameter_value(prompts.WIDGET_PARAMETER_NAME) == raw_before
        assert restored_prompt._current_state() == before
        assert len(restored_prompt._current_state()["shot_documents"]) == 5
        for name, values in generators_before.items():
            generator = restored_flow.nodes[name]
            assert {key: encode_value(generator._get_raw_parameter_value(key)) for key in values} == values
        assert not ATTEMPTS, ATTEMPTS
        print("HMB_PROMPT_START_SIZE_HOST=PASS " + json.dumps({"size": [1800, 1350],
            "saved_size_cases": CASE_RESULTS, "runtime_resize_preserved": True,
            "position_and_custom_metadata_preserved": True, "authored_request_metadata_unmodified": True,
            "sdk_registration_keys_added": ["library_node_metadata", "library", "node_type"],
            "prompt_documents": 5, "nodes": 6, "exact_edges": 5,
            "authored_prompt_state_exact": True, "generator_settings_exact": True,
            "legacy_parameter_height_replayed": 1193, "external_work_attempts": 0}))
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-prompt-start-sdk-") as temporary:
        base = Path(temporary)
        env = {key: str(base / leaf) for key, leaf in (("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
            ("LOCALAPPDATA", "local"), ("APPDATA", "app"), ("GTN_ENGINE_CONFIG_DIR", "engine-config"),
            ("GTN_ENGINE_DATA_DIR", "engine-data"), ("GTN_ENGINE_STATE_DIR", "engine-state"),
            ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "images"))}
        for value in env.values():
            Path(value).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), ExitStack() as guard:
            os.chdir(base)
            try:
                guard.enter_context(mock.patch.object(socket, "create_connection", deny))
                import HMBPromptLibrary as prompts
                import HMBSeedanceGeneration as generators
                import _hmb_shot_routing as routing
                for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                    guard.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
                guard.enter_context(mock.patch.object(prompts.HMBPromptLibrary, "_schedule_prompt_sync", lambda *a, **k: None))
                guard.enter_context(mock.patch.object(prompts.HMBPromptLibrary, "process", deny))
                guard.enter_context(mock.patch.object(generators.HMBSeedanceGeneration, "_process_generation", deny))
                logging.disable(logging.CRITICAL)
                from griptape_nodes.retained_mode.engine import engine_scope
                native_connect = socket.socket.connect
                def guarded_connect(sock, address):
                    caller = sys._getframe(1)
                    if caller.f_code.co_name == "_fallback_socketpair" and Path(caller.f_code.co_filename).name == "socket.py":
                        assert address[0] in {"127.0.0.1", "::1"}
                        return native_connect(sock, address)
                    return deny(sock, address)
                with asyncio.Runner() as runner:
                    runner.get_loop()
                    with mock.patch.object(socket.socket, "connect", guarded_connect), mock.patch.object(socket.socket, "connect_ex", deny):
                        for case in [*CASES, None]:
                            with engine_scope() as engine:
                                runner.run(exercise(engine, case))
            finally:
                logging.shutdown()
                os.chdir(previous)


if __name__ == "__main__":
    main()
