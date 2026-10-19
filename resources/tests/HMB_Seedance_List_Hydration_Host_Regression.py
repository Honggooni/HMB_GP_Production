"""Real SDK saved ParameterList parent/child hydration preserves saved identities."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
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
ATTEMPTS = []


def deny(*args, **kwargs):
    ATTEMPTS.append("network_or_generation")
    raise AssertionError("List hydration must not request network or generation")


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


async def exercise(engine):
    import HMBSeedanceGeneration as target
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, SetParameterValueRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest

    schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(row for row in schema.nodes if row.class_name == "HMBSeedanceGeneration")
    library.register_lazy_node_type(definition.class_name, definition.metadata, lambda: target.HMBSeedanceGeneration)
    engine.event_manager.initialize_queue()
    try:
        ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="SyntheticListHydration"))
        flow_name = ensured.flow_name
        created = send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration", node_name="Synthetic Generator",
            specific_library_name=schema.name, initial_setup=True))
        node = engine.node_manager.get_node_by_name(created.node_name)

        def write(name, value, initial=True):
            send(engine, SetParameterValueRequest(node_name=node.name, parameter_name=name,
                value=deepcopy(value), initial_setup=initial))

        saved = {}
        for list_index, name in enumerate(("reference_images", target.VIDEO_REFERENCES_PARAMETER, "reference_audio"), 1):
            container = node.get_parameter_by_name(name)
            names = [f"{name}_ParameterListUniqueParamID_{list_index:02d}{number:030d}" for number in (1, 2)]
            values = [f"synthetic://{name}/first", f"synthetic://{name}/second"]
            for child_name in names:
                send(engine, AddParameterToNodeRequest(node_name=node.name, parameter_name=child_name,
                    parent_container_name=name, type="str", input_types=["str"], output_type="str",
                    default_value="", tooltip="Synthetic saved media reference", initial_setup=True))
            children = list(container.get_child_parameters())
            assert [child.name for child in children] == names
            # This is the native serializer order: Add exact children, restore
            # parent aggregate, then replay the exact saved child parameters.
            write(name, values)
            assert [child.name for child in container.get_child_parameters()] == names, "Saved parent hydration replaced child UUIDs"
            assert all(left is right for left, right in zip(children, container.get_child_parameters()))
            assert node.get_parameter_value(name) == values
            write(names[1], values[1] + "-authored")
            expected = [values[0], values[1] + "-authored"]
            assert node.get_parameter_value(name) == expected
            assert [child.name for child in container.get_child_parameters()] == names
            saved[name] = (names, expected)
        # Keep a real edge attached to an exact saved child. Parent aggregate
        # hydration must preserve that child object and its physical edge.
        source_created = send(engine, CreateNodeRequest(node_type="HMBSeedanceGeneration", node_name="Synthetic source",
            specific_library_name=schema.name, initial_setup=True))
        source = engine.node_manager.get_node_by_name(source_created.node_name)
        audio_names, audio_values = saved["reference_audio"]
        send(engine, AddParameterToNodeRequest(node_name=source.name, parameter_name="synthetic_audio_out", type="str",
            input_types=["str"], output_type="str", default_value="", tooltip="Synthetic saved output", initial_setup=True))
        send(engine, SetParameterValueRequest(node_name=source.name, parameter_name="synthetic_audio_out",
            value=audio_values[0], is_output=True, initial_setup=True))
        send(engine, CreateConnectionRequest(source_node_name=source.name, source_parameter_name="synthetic_audio_out",
            target_node_name=node.name, target_parameter_name=audio_names[0], initial_setup=True))
        child = node.get_parameter_by_name(audio_names[0])
        write("reference_audio", audio_values)
        assert node.get_parameter_by_name(audio_names[0]) is child
        def edges():
            flow = engine.flow_manager.get_flow_by_name(flow_name)
            return {(edge.source_node.name, edge.source_parameter.name, edge.target_node.name, edge.target_parameter.name)
                for edge in engine.flow_manager._get_connections_for_flow(flow)}
        expected_edges = edges()
        assert len(expected_edges) == 1
        # Actual SDK command serialization/deserialization replays both the
        # dynamic child definitions and parent values; no custom decoder stub.
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=flow_name))
        send(engine, DeleteFlowRequest(flow_name=None))
        restored = send(engine, DeserializeFlowFromCommandsRequest(serialized_flow_commands=serialized.serialized_flow_commands))
        flow = engine.flow_manager.get_flow_by_name(restored.flow_name)
        node = flow.nodes[created.node_name]
        assert edges() == expected_edges
        for name, (names, values) in saved.items():
            assert [child.name for child in node.get_parameter_by_name(name).get_child_parameters()] == names
            assert node.get_parameter_value(name) == values
        # Preserve existing explicit authoring semantics and count-mismatch
        # handling: these paths deliberately rebuild list items.
        container = node.get_parameter_by_name("reference_images")
        old_names = [child.name for child in container.get_child_parameters()]
        write("reference_images", ["synthetic://runtime/one", "synthetic://runtime/two"], initial=False)
        assert [child.name for child in container.get_child_parameters()] != old_names
        assert node.get_parameter_value("reference_images") == ["synthetic://runtime/one", "synthetic://runtime/two"]
        write("reference_images", ["synthetic://mismatch/one"])
        assert len(container.get_child_parameters()) == 1
        assert node.get_parameter_value("reference_images") == ["synthetic://mismatch/one"]
        write("reference_images", [])
        assert not container.get_child_parameters() and node.get_parameter_value("reference_images") == []
        assert not node._hmb_list_parent_syncing
        assert not ATTEMPTS
        print("HMB_SEEDANCE_LIST_HYDRATION_HOST=PASS (actual SDK3 lists/6 exact saved child UUIDs; Add/parent/child replay; real child edge + native serialize/reopen; explicit writes/mismatched length/empty behavior; generation/network0)")
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-list-hydration-sdk-") as temporary:
        base = Path(temporary)
        env = {key: str(base / leaf) for key, leaf in (("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
            ("LOCALAPPDATA", "local"), ("APPDATA", "app"), ("GTN_ENGINE_CONFIG_DIR", "engine-config"),
            ("GTN_ENGINE_DATA_DIR", "engine-data"), ("GTN_ENGINE_STATE_DIR", "engine-state"),
            ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"))}
        for directory in env.values():
            Path(directory).mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, env), ExitStack() as guard:
            os.chdir(base)
            try:
                import HMBSeedanceGeneration as target
                import _hmb_shot_routing as routing
                for name in ("schedule_post_registration_reconcile", "schedule_post_hydration_reconcile"):
                    guard.enter_context(mock.patch.object(routing, name, lambda *a, **k: False))
                guard.enter_context(mock.patch.object(target.HMBSeedanceGeneration, "_process_generation", deny))
                guard.enter_context(mock.patch.object(target.HMBSeedanceGeneration, "_prepare_media_reference", deny))
                guard.enter_context(mock.patch.object(target._HMBAIBrokerBridge, "create_generation", deny, create=True))
                guard.enter_context(mock.patch.object(socket, "create_connection", deny))
                native_connect = socket.socket.connect
                def guarded_connect(sock, address):
                    caller = sys._getframe(1)
                    if caller.f_code.co_name == "_fallback_socketpair" and Path(caller.f_code.co_filename).name == "socket.py":
                        assert address[0] in {"127.0.0.1", "::1"}
                        return native_connect(sock, address)
                    return deny(sock, address)
                logging.disable(logging.CRITICAL)
                from griptape_nodes.retained_mode.engine import engine_scope
                with asyncio.Runner() as runner:
                    runner.get_loop()
                    with mock.patch.object(socket.socket, "connect", guarded_connect), mock.patch.object(socket.socket, "connect_ex", deny):
                        with engine_scope() as engine:
                            runner.run(exercise(engine))
            finally:
                logging.shutdown()
                os.chdir(previous)


if __name__ == "__main__":
    main()
