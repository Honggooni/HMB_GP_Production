"""Native SDK: quietly retain editor singletons; preserve legacy hydration and errors."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.metadata
import inspect
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
TEMPORARY = tempfile.TemporaryDirectory(prefix="hmb-prompt-single-load-")
ISOLATED = Path(TEMPORARY.name)
for variable, leaf in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
    ("XDG_STATE_HOME", "state"), ("LOCALAPPDATA", "local"),
    ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"), ("HMB_IMAGE_PROJECTS_ROOT", "images")):
    target = ISOLATED / leaf
    target.mkdir()
    os.environ[variable] = str(target)
try:
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, CreateFlowResultSuccess
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, CreateConnectionResultSuccess
    from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
    from griptape_nodes.retained_mode.events.node_events import (
        CreateNodeRequest, CreateNodeResultFailure, CreateNodeResultSuccess,
        DeserializeSelectedNodesFromCommandsRequest, DeserializeSelectedNodesFromCommandsResultFailure,
        DeserializeSelectedNodesFromCommandsResultSuccess,
        SerializeSelectedNodesToCommandsRequest, SerializeSelectedNodesToCommandsResultSuccess,
        DuplicateSelectedNodesRequest, DuplicateSelectedNodesResultFailure,
    )
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
except ImportError:
    TEMPORARY.cleanup()
    print("HMB Prompt single-load native guard: SKIP (installed Desktop SDK required)")
    raise SystemExit(0)

NETWORK_ATTEMPTS = []


def deny_network(*_args, **_kwargs):
    NETWORK_ATTEMPTS.append("blocked")
    raise AssertionError("Prompt single-load fixture attempted network I/O")


def send(engine, request):
    request.broadcast_result = False
    return engine.handle_request(request)


def create(engine, name, **kwargs):
    return send(engine, CreateNodeRequest(node_type="HMBPromptLibrary", specific_library_name="HMB_GP_Production",
        node_name=name, create_error_proxy_on_failure=False, **kwargs))


def inventory(engine):
    states = {}
    for name in engine.node_manager._name_to_parent_flow_name:
        node = engine.node_manager.get_node_by_name(name)
        states[name] = (copy.deepcopy(node.metadata), copy.deepcopy(dict(node.parameter_values)),
            copy.deepcopy(dict(node.parameter_output_values)))
    edges = sorted((item.source_node.name, item.source_parameter.name,
        item.target_node.name, item.target_parameter.name)
        for item in engine.flow_manager.get_connections().connections.values())
    return (dict(engine.node_manager._name_to_parent_flow_name), dict(engine.object_manager._name_to_objects),
        engine.context_manager.get_current_flow().name,
        engine.context_manager.get_current_node() if engine.context_manager.has_current_node() else None,
        states, edges)


def quiet(result, result_type):
    assert isinstance(result, result_type), str(result.result_details)
    assert "already loaded" in str(result.result_details)
    assert {detail.level for detail in result.result_details.result_details} == {logging.INFO}
    assert result.altered_workflow_state is False


def actual_failure(result, result_type=CreateNodeResultFailure):
    assert isinstance(result, result_type), str(result.result_details)
    assert all(detail.level >= logging.ERROR for detail in result.result_details.result_details)


def fixture(engine):
    raw = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    directory = ISOLATED / "fixture"
    directory.mkdir()
    source = directory / "fixture_nodes.py"
    source.write_text("from griptape_nodes.exe_types.node_types import DataNode\n"
        "from griptape_nodes.exe_types.core_types import Parameter, ParameterMode\n"
        "class FixtureNode(DataNode):\n"
        "    created = []\n"
        "    def __init__(self, name, metadata=None):\n"
        "        if name == 'FailingPrompt': raise ValueError('fixture failure before registration')\n"
        "        super().__init__(name=name, metadata=metadata)\n"
        "        self.add_parameter(Parameter(name='authored', type='str', default_value='default', allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT}))\n"
        "        type(self).created.append(name)\n"
        "class HMBPromptLibrary(FixtureNode):\n"
        "    created = []\n"
        "class HMBAgentLibrary(FixtureNode):\n"
        "    created = []\n"
        "class HMBFinishLookLibrary(FixtureNode):\n"
        "    created = []\n", encoding="utf-8")
    raw.update(advanced_library_path=str(ROOT / "_hmb_library_bootstrap.py"),
        widgets=[], scripts=[], workflows=[], settings=[])
    raw["metadata"]["dependencies"] = None
    raw["nodes"] = [{**definition, "file_path": str(source)} for definition in raw["nodes"]
        if definition["class_name"] in {"HMBPromptLibrary", "HMBAgentLibrary", "HMBFinishLookLibrary"}]
    schema = LibrarySchema.model_validate(raw)
    loading = getattr(engine.library_manager, "module_loading", engine.library_manager)
    advanced_loader = getattr(loading, "load_advanced_library_module", None) or engine.library_manager._load_advanced_library_module
    advanced = advanced_loader(schema, directory)
    library = LibraryRegistry.generate_new_library(schema, advanced_library=advanced)
    fields = {"executes_in_worker": False}
    if "requires_worker" in inspect.signature(LibraryManager.LibraryInfo).parameters:
        fields["requires_worker"] = False
    info = LibraryManager.LibraryInfo(lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
        library_path=str(directory / "manifest.json"), is_sandbox=False, library_name=raw["name"],
        library_version=schema.metadata.library_version, fitness=LibraryManager.LibraryFitness.NOT_EVALUATED,
        problems=[], **fields)
    nodes_loader = getattr(loading, "attempt_load_nodes_from_library", None) or engine.library_manager._attempt_load_nodes_from_library
    nodes_loader(schema, library, directory, info, lazy_loading=True)
    assert not info.problems
    return library, advanced


async def main():
    with mock.patch.object(socket.socket, "connect", side_effect=deny_network), \
         mock.patch.object(socket.socket, "connect_ex", side_effect=deny_network), \
         mock.patch.object(socket, "create_connection", side_effect=deny_network), \
         mock.patch.object(socket, "getaddrinfo", side_effect=deny_network):
        WorkflowRegistry.clear_user_workflows()
        with engine_scope() as engine:
            engine.event_manager.initialize_queue()
            library, advanced = fixture(engine)
            try:
                send(engine, EnsureWorkflowAndFlowRequest(flow_name="PromptFlowA"))
                first = create(engine, "PromptOne", metadata={"position": {"x": 41, "y": 73}, "size": {"width": 720, "height": 1400}})
                assert isinstance(first, CreateNodeResultSuccess), str(first.result_details)
                original = engine.node_manager.get_node_by_name(first.node_name)
                original.set_parameter_value("authored", "Original {{literal}} prompt", initial_setup=True)
                original.parameter_output_values["authored"] = "Original paired output"
                before = inventory(engine)
                created_before = list(type(original).created)
                for settings in ({}, {"set_as_new_context": True}, {"override_parent_flow_name": "PromptFlowA"}):
                    rejected = create(engine, "SecondPrompt", **settings)
                    quiet(rejected, CreateNodeResultFailure)
                    assert inventory(engine) == before and type(original).created == created_before
                print("PASS palette/drop/tab and explicit-parent duplicates quietly retain metadata, authored inputs/outputs and context")

                # Saved legacy workflows retain all original Prompt instances.
                for number in range(2, 6):
                    restored = create(engine, f"LegacyPrompt{number}", initial_setup=True)
                    assert isinstance(restored, CreateNodeResultSuccess), str(restored.result_details)
                assert len(engine.flow_manager.get_flow_by_name("PromptFlowA").nodes) == 5
                connected = send(engine, CreateConnectionRequest(source_node_name="LegacyPrompt2", source_parameter_name="authored",
                    target_node_name=first.node_name, target_parameter_name="authored", initial_setup=True))
                assert isinstance(connected, CreateConnectionResultSuccess), str(connected.result_details)
                print("PASS legacy saved initial_setup=True restores five Prompts without deletion")

                serialized = send(engine, SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[[first.node_name, "fixture"]]))
                assert isinstance(serialized, SerializeSelectedNodesToCommandsResultSuccess), str(serialized.result_details)
                clipboard = DeserializeSelectedNodesFromCommandsRequest(
                    deserialize_commands=serialized.serialized_selected_node_commands, pickled_values=serialized.pickled_values)
                before = inventory(engine)
                rejected = send(engine, clipboard)
                quiet(rejected, DeserializeSelectedNodesFromCommandsResultFailure)
                assert inventory(engine) == before
                duplicate = send(engine, DuplicateSelectedNodesRequest(nodes_to_duplicate=[[first.node_name, "fixture"]]))
                quiet(duplicate, DuplicateSelectedNodesResultFailure)
                assert inventory(engine) == before
                print("PASS official clipboard paste/duplicate remain typed failures at INFO without input/output/edge mutation")

                multi_serialized = send(engine, SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[
                    [first.node_name, "fixture"], ["LegacyPrompt2", "fixture"]]))
                assert isinstance(multi_serialized, SerializeSelectedNodesToCommandsResultSuccess)
                empty_batch_flow = send(engine, CreateFlowRequest(flow_name="EmptyBatchFlow", parent_flow_name=None, set_as_new_context=True))
                assert isinstance(empty_batch_flow, CreateFlowResultSuccess)
                before = inventory(engine)
                rejected_batch = send(engine, DeserializeSelectedNodesFromCommandsRequest(
                    deserialize_commands=multi_serialized.serialized_selected_node_commands,
                    pickled_values=multi_serialized.pickled_values))
                quiet(rejected_batch, DeserializeSelectedNodesFromCommandsResultFailure)
                assert inventory(engine) == before
                print("PASS a two-Prompt paste into an empty flow is refused atomically before either constructor")

                new_flow = send(engine, CreateFlowRequest(flow_name="PromptFlowB", parent_flow_name=None, set_as_new_context=True))
                assert isinstance(new_flow, CreateFlowResultSuccess), str(new_flow.result_details)
                pasted = send(engine, copy.deepcopy(clipboard))
                assert isinstance(pasted, DeserializeSelectedNodesFromCommandsResultSuccess), str(pasted.result_details)
                assert len(engine.flow_manager.get_flow_by_name("PromptFlowB").nodes) == 1
                print("PASS cross-flow paste creates exactly one Prompt")

                first_agent = send(engine, CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name="HMB_GP_Production",
                    node_name="AgentOne", create_error_proxy_on_failure=False))
                assert isinstance(first_agent, CreateNodeResultSuccess), str(first_agent.result_details)
                agent_node = engine.node_manager.get_node_by_name(first_agent.node_name)
                agent_node.set_parameter_value("authored", "Preserved agent prompt", initial_setup=True)
                agent_node.parameter_output_values["authored"] = "Preserved agent result"
                for number in range(2, 6):
                    before_agent = inventory(engine)
                    rejected_agent = send(engine, CreateNodeRequest(node_type="HMBAgentLibrary", specific_library_name="HMB_GP_Production",
                        node_name=f"SecondAgent{number}", create_error_proxy_on_failure=False))
                    quiet(rejected_agent, CreateNodeResultFailure)
                    assert inventory(engine) == before_agent
                agent_serialized = send(engine, SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[[first_agent.node_name, "fixture"]]))
                assert isinstance(agent_serialized, SerializeSelectedNodesToCommandsResultSuccess)
                rejected_agent_paste = send(engine, DeserializeSelectedNodesFromCommandsRequest(
                    deserialize_commands=agent_serialized.serialized_selected_node_commands, pickled_values=agent_serialized.pickled_values))
                quiet(rejected_agent_paste, DeserializeSelectedNodesFromCommandsResultFailure)
                quiet(send(engine, DuplicateSelectedNodesRequest(nodes_to_duplicate=[[first_agent.node_name, "fixture"]])),
                    DuplicateSelectedNodesResultFailure)

                finish = send(engine, CreateNodeRequest(node_type="HMBFinishLookLibrary", specific_library_name="HMB_GP_Production",
                    node_name="FinishOne", create_error_proxy_on_failure=False))
                assert isinstance(finish, CreateNodeResultSuccess), str(finish.result_details)
                finish_node = engine.node_manager.get_node_by_name(finish.node_name)
                finish_node.set_parameter_value("authored", "Preserved Finish controls", initial_setup=True)
                finish_node.parameter_output_values["authored"] = "Preserved Finish output"
                for kind, retained_name in (("HMBPromptLibrary", pasted.node_names[0]),
                        ("HMBAgentLibrary", first_agent.node_name), ("HMBFinishLookLibrary", finish.node_name)):
                    before_editor = inventory(engine)
                    explicit = CreateNodeRequest(node_type=kind, specific_library_name="HMB_GP_Production",
                        node_name="UnusedDuplicate", metadata={"position": {"x": 9999, "y": 8888}},
                        set_as_new_context=True, create_error_proxy_on_failure=False, broadcast_result=False)
                    request_before = copy.deepcopy(vars(explicit))
                    quiet(send(engine, explicit), CreateNodeResultFailure)
                    assert vars(explicit) == request_before, "Expected admission notice mutated the caller request"
                    serialized_editor = send(engine, SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[[retained_name, "fixture"]]))
                    quiet(send(engine, DeserializeSelectedNodesFromCommandsRequest(
                        deserialize_commands=serialized_editor.serialized_selected_node_commands,
                        pickled_values=serialized_editor.pickled_values)), DeserializeSelectedNodesFromCommandsResultFailure)
                    quiet(send(engine, DuplicateSelectedNodesRequest(nodes_to_duplicate=[[retained_name, "fixture"]])),
                        DuplicateSelectedNodesResultFailure)
                    assert inventory(engine) == before_editor
                print("PASS Prompt/Agent/Finish create, paste and duplicate are quiet; same-flow owners and requests unchanged")

                before_error = inventory(engine)
                invalid_parent = create(engine, "InvalidParent", override_parent_flow_name="MissingParent")
                actual_failure(invalid_parent)
                unknown = send(engine, CreateNodeRequest(node_type="UnknownFixtureNode", specific_library_name="HMB_GP_Production",
                    create_error_proxy_on_failure=False))
                actual_failure(unknown, GenericResultFailure)
                assert isinstance(unknown.exception, Exception)
                with mock.patch.object(engine.library_manager, "_is_worker", True):
                    worker_error = create(engine, "FailingPrompt")
                actual_failure(worker_error)
                assert inventory(engine) == before_error
                print("PASS invalid-parent, unrelated node and actual worker constructor errors retain ERROR semantics")

                failure_flow = send(engine, CreateFlowRequest(flow_name="FailureFlow", parent_flow_name=None, set_as_new_context=True))
                assert isinstance(failure_flow, CreateFlowResultSuccess)
                failed = create(engine, "FailingPrompt")
                actual_failure(failed)
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                retried = create(engine, "RetryAfterFailure")
                assert isinstance(retried, CreateNodeResultSuccess), str(retried.result_details)
                print("PASS failed constructor releases its in-flight creation claim")

                race_flow = send(engine, CreateFlowRequest(flow_name="ConcurrentFlow", parent_flow_name=None, set_as_new_context=True))
                assert isinstance(race_flow, CreateFlowResultSuccess)
                def simultaneous_create(number):
                    with engine_scope(engine):
                        return create(engine, f"ConcurrentPrompt{number}")
                with ThreadPoolExecutor(max_workers=8) as executor:
                    results = list(executor.map(simultaneous_create, range(12)))
                assert sum(isinstance(result, CreateNodeResultSuccess) for result in results) == 1
                assert sum(isinstance(result, CreateNodeResultFailure) for result in results) == 11
                for result in results:
                    if isinstance(result, CreateNodeResultFailure): quiet(result, CreateNodeResultFailure)
                assert len(engine.flow_manager.get_flow_by_name("ConcurrentFlow").nodes) == 1
                print("PASS twelve simultaneous new Prompt requests create exactly one node")
            finally:
                LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)
            gate = getattr(engine.event_manager, "_hmb_connected_deletion_lifetime_v2")
            assert engine.event_manager._pre_dispatch_hooks == [gate.hook]
            assert gate.is_registered() and gate.engine_ref() is engine
            assert all(not values for values in engine.event_manager._post_dispatch_hooks.values())
            assert not advanced._registrations
            print("PASS unload removes library pre/post hooks and pending claims while retaining only the engine deletion gate")
        assert NETWORK_ATTEMPTS == []
    print(json.dumps({"status": "PASS", "sdk_engine_version": importlib.metadata.version("griptape-nodes-engine"),
        "native_create_and_paste_handlers_mocked": False, "network_requests": 0, "live_user_workflow_changed": False}))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        logging.shutdown()
        TEMPORARY.cleanup()
