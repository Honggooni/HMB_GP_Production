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
    from griptape_nodes.retained_mode.events.parameter_events import RemoveParameterFromNodeRequest
    from griptape_nodes.retained_mode.events.node_events import (
        CreateNodeRequest, CreateNodeResultFailure, CreateNodeResultSuccess,
        DeserializeSelectedNodesFromCommandsRequest, DeserializeSelectedNodesFromCommandsResultFailure,
        DeserializeSelectedNodesFromCommandsResultSuccess,
        SerializeSelectedNodesToCommandsRequest, SerializeSelectedNodesToCommandsResultSuccess,
        DuplicateSelectedNodesRequest, DuplicateSelectedNodesResultFailure,
        ResetNodeToDefaultsRequest, ResetNodeToDefaultsResultSuccess,
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


def fixture(engine, directory_name="fixture"):
    raw = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    directory = ISOLATED / directory_name
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
        "    created = []\n"
        "class HMBImageBash(FixtureNode):\n"
        "    created = []\n", encoding="utf-8")
    raw.update(advanced_library_path=str(ROOT / "_hmb_library_bootstrap.py"),
        widgets=[], scripts=[], workflows=[], settings=[])
    raw["metadata"]["dependencies"] = None
    raw["nodes"] = [{**definition, "file_path": str(source)} for definition in raw["nodes"]
        if definition["class_name"] in {"HMBPromptLibrary", "HMBAgentLibrary", "HMBFinishLookLibrary", "HMBImageBash"}]
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

                # Image Bash is one editor per flow as well. Admission happens
                # before any constructor, copied value or copied edge can run.
                bash_first = send(engine, CreateNodeRequest(node_type="HMBImageBash", specific_library_name="HMB_GP_Production",
                    node_name="BashOne", metadata={"size": {"width": 800, "height": 680}}, create_error_proxy_on_failure=False))
                assert isinstance(bash_first, CreateNodeResultSuccess), str(bash_first.result_details)
                bash = engine.node_manager.get_node_by_name(bash_first.node_name)
                bash.set_parameter_value("authored", "Preserved Bash scene and Apply receipt", initial_setup=True)
                bash.parameter_output_values["authored"] = "Preserved Bash PNG"
                bash_serialized = send(engine, SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[[bash.name, "fixture"]]))
                assert isinstance(bash_serialized, SerializeSelectedNodesToCommandsResultSuccess)
                bash_clipboard = DeserializeSelectedNodesFromCommandsRequest(
                    deserialize_commands=bash_serialized.serialized_selected_node_commands,
                    pickled_values=bash_serialized.pickled_values)
                before_bash, bash_constructors = inventory(engine), list(type(bash).created)
                for request, result_type in (
                    (CreateNodeRequest(node_type="HMBImageBash", specific_library_name="HMB_GP_Production",
                        node_name="BashPaletteDuplicate", create_error_proxy_on_failure=False), CreateNodeResultFailure),
                    (copy.deepcopy(bash_clipboard), DeserializeSelectedNodesFromCommandsResultFailure),
                    (DuplicateSelectedNodesRequest(nodes_to_duplicate=[[bash.name, "fixture"]]), DuplicateSelectedNodesResultFailure),
                ):
                    request.broadcast_result = False
                    request_before = copy.deepcopy(vars(request))
                    result = send(engine, request)
                    quiet(result, result_type)
                    assert "existing Image Bash workspace" in str(result.result_details)
                    assert vars(request) == request_before and inventory(engine) == before_bash
                    assert type(bash).created == bash_constructors
                # Saved legacy duplicate canvases are never removed or merged
                # by this new-create guard. Subsequent fresh requests stay blocked.
                restored_bash = send(engine, CreateNodeRequest(node_type="HMBImageBash", specific_library_name="HMB_GP_Production",
                    node_name="LegacyBashTwo", initial_setup=True, create_error_proxy_on_failure=False))
                assert isinstance(restored_bash, CreateNodeResultSuccess), str(restored_bash.result_details)
                legacy_bash = engine.node_manager.get_node_by_name(restored_bash.node_name)
                legacy_bash.set_parameter_value("authored", "Distinct legacy scene", initial_setup=True)
                legacy_bash.parameter_output_values["authored"] = "Distinct legacy PNG"
                before_legacy = inventory(engine)
                quiet(send(engine, CreateNodeRequest(node_type="HMBImageBash", specific_library_name="HMB_GP_Production",
                    node_name="BashAfterLegacy", create_error_proxy_on_failure=False)), CreateNodeResultFailure)
                assert inventory(engine) == before_legacy
                print("PASS Bash palette, duplicate and paste are blocked before construction; existing and legacy scenes/outputs stay exact")

                bash_batch = send(engine, SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[
                    [bash.name, "fixture"], [legacy_bash.name, "fixture"]]))
                assert isinstance(bash_batch, SerializeSelectedNodesToCommandsResultSuccess)
                bash_empty = send(engine, CreateFlowRequest(flow_name="BashEmptyBatchFlow", parent_flow_name=None, set_as_new_context=True))
                assert isinstance(bash_empty, CreateFlowResultSuccess)
                before_bash_batch = inventory(engine)
                quiet(send(engine, DeserializeSelectedNodesFromCommandsRequest(
                    deserialize_commands=bash_batch.serialized_selected_node_commands,
                    pickled_values=bash_batch.pickled_values)), DeserializeSelectedNodesFromCommandsResultFailure)
                assert inventory(engine) == before_bash_batch
                print("PASS a two-Bash paste into an empty flow is refused atomically before either constructor")

                bash_flow = send(engine, CreateFlowRequest(flow_name="BashOtherFlow", parent_flow_name=None, set_as_new_context=True))
                assert isinstance(bash_flow, CreateFlowResultSuccess)
                bash_pasted = send(engine, copy.deepcopy(bash_clipboard))
                assert isinstance(bash_pasted, DeserializeSelectedNodesFromCommandsResultSuccess), str(bash_pasted.result_details)
                assert len(engine.flow_manager.get_flow_by_name("BashOtherFlow").nodes) == 1
                pasted_bash = engine.node_manager.get_node_by_name(bash_pasted.node_names[0])
                assert pasted_bash.get_parameter_value("authored") == bash.get_parameter_value("authored")
                print("PASS cross-flow Bash paste creates exactly one editor with the authored scene")

                bash_race_flow = send(engine, CreateFlowRequest(flow_name="ConcurrentBashFlow", parent_flow_name=None, set_as_new_context=True))
                assert isinstance(bash_race_flow, CreateFlowResultSuccess)
                def simultaneous_bash(number):
                    with engine_scope(engine):
                        return send(engine, CreateNodeRequest(node_type="HMBImageBash", specific_library_name="HMB_GP_Production",
                            node_name=f"ConcurrentBash{number}", create_error_proxy_on_failure=False))
                with ThreadPoolExecutor(max_workers=8) as executor:
                    bash_results = list(executor.map(simultaneous_bash, range(12)))
                assert sum(isinstance(result, CreateNodeResultSuccess) for result in bash_results) == 1
                assert sum(isinstance(result, CreateNodeResultFailure) for result in bash_results) == 11
                for result in bash_results:
                    if isinstance(result, CreateNodeResultFailure): quiet(result, CreateNodeResultFailure)
                assert len(engine.flow_manager.get_flow_by_name("ConcurrentBashFlow").nodes) == 1
                print("PASS twelve simultaneous new Bash requests create exactly one editor")

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

                # Hold an actual detached native wire across unload/reload.
                import _hmb_connection_management as connection_api
                with engine.context_manager.flow("PromptFlowB"):
                    assert send(engine, CreateConnectionRequest(source_node_name=bash.name, source_parameter_name="authored",
                        target_node_name=legacy_bash.name, target_parameter_name="authored", initial_setup=True)).succeeded()
                    connected = connection_api.describe(engine, bash.name)
                    detached = connection_api.manage(engine, bash.name, "disconnect", connected["state_token"])
                    assert detached["detached"]
                    port_refused = send(engine, RemoveParameterFromNodeRequest(node_name=legacy_bash.name, parameter_name="authored"))
                    assert not port_refused.succeeded() and "HMB_CONNECTION_PORT_RETAINED" in str(port_refused.result_details)
                    detached_before_reload = inventory(engine)
            finally:
                LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)
            gate = getattr(engine.event_manager, "_hmb_connected_deletion_lifetime_v2")
            assert engine.event_manager._pre_dispatch_hooks == [gate.hook]
            assert gate.is_registered() and gate.engine_ref() is engine
            assert all(not values for values in engine.event_manager._post_dispatch_hooks.values())
            assert not advanced._registrations
            print("PASS unload removes library pre/post hooks and pending claims while retaining only the engine deletion gate")

            def unrelated_hook(_request, _context):
                return None
            engine.event_manager.add_pre_dispatch_hook(unrelated_hook)
            reloaded_library, reloaded_advanced = fixture(engine, "fixture-reload")
            try:
                registration = next(iter(reloaded_advanced._registrations))
                handler = registration.connection_handlers
                for _ in range(3):
                    assert connection_api.install_request_handlers(engine, registration) is handler
                assert engine.event_manager._pre_dispatch_hooks.count(handler.protect_detached_ports) == 1
                assert engine.event_manager._pre_dispatch_hooks.count(unrelated_hook) == 1
                with engine.context_manager.flow("PromptFlowB"):
                    assert inventory(engine) == detached_before_reload
                    port_refused = send(engine, RemoveParameterFromNodeRequest(node_name=legacy_bash.name, parameter_name="authored"))
                    assert not port_refused.succeeded() and "HMB_CONNECTION_PORT_RETAINED" in str(port_refused.result_details)
                    assert inventory(engine) == detached_before_reload
                    reconnected = connection_api.manage(engine, bash.name, "reconnect",
                        connection_api.describe(engine, bash.name)["state_token"])
                    assert not reconnected["detached"] and len(reconnected["connections"]) == 1
                print("PASS reload reattaches exactly one port guard, retains detached leases/data and leaves unrelated hooks untouched")
            finally:
                LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=engine.event_manager)
            assert engine.event_manager._pre_dispatch_hooks == [gate.hook, unrelated_hook]
            engine.event_manager.remove_pre_dispatch_hook(unrelated_hook)
            assert engine.event_manager._pre_dispatch_hooks == [gate.hook]

        # Reset establishes an engine-lifetime detached-port gate. Exercise it
        # in a distinct engine so the existing admission/unload leak assertion
        # above remains exact and does not mistake that separate gate for a leak.
        with engine_scope() as reset_engine:
            reset_engine.event_manager.initialize_queue()
            reset_library, _reset_advanced = fixture(reset_engine, "fixture-reset")
            try:
                send(reset_engine, EnsureWorkflowAndFlowRequest(flow_name="BashResetFlow"))
                created = send(reset_engine, CreateNodeRequest(node_type="HMBImageBash", specific_library_name="HMB_GP_Production",
                    node_name="ResetBash", metadata={"size": {"width": 800, "height": 680}}, create_error_proxy_on_failure=False))
                assert isinstance(created, CreateNodeResultSuccess), str(created.result_details)
                old = reset_engine.node_manager.get_node_by_name(created.node_name)
                old.set_parameter_value("authored", "Explicitly reset this fixture", initial_setup=True)
                reset = await reset_engine.ahandle_request(ResetNodeToDefaultsRequest(node_name=old.name, broadcast_result=False))
                assert isinstance(reset, ResetNodeToDefaultsResultSuccess), str(reset.result_details)
                current = reset_engine.node_manager.get_node_by_name(created.node_name)
                assert current is not old and current.get_parameter_value("authored") == "default"
                assert current.metadata["size"] == {"width": 800, "height": 680}
                assert len(reset_engine.flow_manager.get_flow_by_name("BashResetFlow").nodes) == 1
                after_reset = inventory(reset_engine)
                quiet(send(reset_engine, CreateNodeRequest(node_type="HMBImageBash", specific_library_name="HMB_GP_Production",
                    node_name="BashAfterReset", create_error_proxy_on_failure=False)), CreateNodeResultFailure)
                assert inventory(reset_engine) == after_reset
                print("PASS official SDK Reset keeps one Bash and its geometry; subsequent palette admission remains guarded")
            finally:
                LibraryRegistry.unregister_library("HMB_GP_Production", event_manager=reset_engine.event_manager)
        assert NETWORK_ATTEMPTS == []
    print(json.dumps({"status": "PASS", "sdk_engine_version": importlib.metadata.version("griptape-nodes-engine"),
        "native_create_and_paste_handlers_mocked": False, "network_requests": 0, "live_user_workflow_changed": False}))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        logging.shutdown()
        TEMPORARY.cleanup()
