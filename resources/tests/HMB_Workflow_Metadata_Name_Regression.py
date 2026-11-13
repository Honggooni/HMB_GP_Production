"""Actual-SDK exact-name metadata recovery; private graph, no app or render.

Run with the bundled SDK interpreter and -I -B. Only this process's native
engine and temporary workspace are used. No installed or user file is changed.
"""
from __future__ import annotations

import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock
from uuid import uuid4
import weakref

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
private = tempfile.TemporaryDirectory(prefix="hmb-metadata-name-test-")
for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
        "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
        "GTN_CONFIG_WORKSPACE_DIRECTORY"):
    value = Path(private.name) / key
    value.mkdir()
    os.environ[key] = str(value)

import _hmb_library_bootstrap as bootstrap
import _hmb_workflow_serialization_compat as target
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
from griptape_nodes.retained_mode.engine import engine_scope
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.events.workflow_events import (
    GetWorkflowMetadataRequest, GetWorkflowMetadataResultFailure, SaveWorkflowRequest,
)

checks = []


def check(label, condition):
    assert condition, label
    checks.append(label)


class Owner:
    pass


class MetadataFixture(DataNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_parameter(Parameter(name="authored", type="str", default_value="",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT}))

    def process(self):
        raise AssertionError("Metadata recovery must never execute a node")


def setup(engine, name):
    raw = json.loads((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
    raw["advanced_library_path"] = None
    definition = copy.deepcopy(raw["nodes"][0])
    definition.update(class_name="HMBImageAssetLibrary", file_path=__file__)
    raw["nodes"] = [definition]
    schema = LibrarySchema.model_validate(raw)
    library = LibraryRegistry.generate_new_library(schema)
    library.register_lazy_node_type("HMBImageAssetLibrary", schema.nodes[0].metadata, lambda: MetadataFixture)
    engine.event_manager.initialize_queue()
    registration = bootstrap._Registration(engine, engine.event_manager)
    registration.start_web_worker = lambda: None
    owner = Owner()
    registration.owners[owner] = weakref.ref(library)

    def send(request):
        request.broadcast_result = False
        return engine.handle_request(request)

    assert send(SetWorkflowContextRequest(workflow_name=name)).succeeded()
    assert send(CreateFlowRequest(flow_name="MetadataFlow", parent_flow_name=None)).succeeded()
    for node_name in ("MetadataSource", "MetadataTarget"):
        created = send(CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
            node_name=node_name, initial_setup=True, create_error_proxy_on_failure=False))
        assert created.succeeded(), str(created.result_details)
        assert send(SetParameterValueRequest(node_name=created.node_name, parameter_name="authored",
            value=node_name + " synthetic shot/task/image sentinel")).succeeded()
    assert send(CreateConnectionRequest(source_node_name="MetadataSource", source_parameter_name="authored",
        target_node_name="MetadataTarget", target_parameter_name="authored", initial_setup=True)).succeeded()
    record = engine.context_manager._workflow_stack[0]
    flow = engine.context_manager.get_current_flow()

    def inventory():
        return (id(record), id(flow), {key:id(node) for key,node in flow.nodes.items()},
            copy.deepcopy({key:(node.metadata, dict(node.parameter_values), dict(node.parameter_output_values))
                for key,node in flow.nodes.items()}),
            sorted((edge.source_node.name, edge.source_parameter.name,
                edge.target_node.name, edge.target_parameter.name)
                for edge in engine.flow_manager.get_connections().connections.values()))

    engine.event_manager.add_pre_dispatch_hook(registration.hook)

    def close():
        engine.event_manager.remove_pre_dispatch_hook(registration.hook)
        registration.active = False
        target.release(registration)
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)

    return registration, owner, library, send, record, flow, inventory, close


async def exact_name_case(name):
    with engine_scope() as engine:
        reg, owner, library, send, record, flow, inventory, close = setup(engine, name)
        try:
            before = inventory()
            original_keys = set(engine.workflow_registry._workflows)
            flags = engine.workflow_manager.variable_substitution._enabled
            flags[name] = False
            flags["UnrelatedFlag"] = True
            wrong = send(GetWorkflowMetadataRequest(workflow_name=name + "_foreign"))
            check(name + ": mismatched request does not register or change canvas",
                not wrong.succeeded() and record._name == name and inventory() == before
                and set(engine.workflow_registry._workflows) == original_keys)
            request = GetWorkflowMetadataRequest(workflow_name=name)
            result = send(request)
            key = record._name
            check(name + ": exact request receives native scratch metadata",
                result.succeeded() and key.startswith("unsaved:") and result.workflow_metadata.name == name
                and request.workflow_name == name)
            check(name + ": one honest native unsaved entry is created",
                set(engine.workflow_registry._workflows) == original_keys | {key}
                and engine.workflow_registry.get_workflow_by_name(key).is_saved is False)
            check(name + ": graph object identity authored values and edges stay intact", inventory() == before)
            check(name + ": substitution flags retain their exact values", flags == {key:False, "UnrelatedFlag":True})
            lease = reg._hmb_legacy_metadata_lease
            check(name + ": lease records only the exact original request name", lease["request_name"] == name)
            check(name + ": unrelated metadata stays native", not send(GetWorkflowMetadataRequest(workflow_name="UnrelatedLookup")).succeeded())
            check(name + ": unrelated lookup retains the same lease", reg._hmb_legacy_metadata_lease is lease)
            check(name + ": native scratch lookup passes through", send(GetWorkflowMetadataRequest(workflow_name=key)).succeeded())
            check(name + ": native scratch lookup retains the same lease", reg._hmb_legacy_metadata_lease is lease)
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(lambda ctx:ctx.run(lambda:send(GetWorkflowMetadataRequest(workflow_name=name))),
                    [copy_context() for _ in range(8)]))
            check(name + ": concurrent original aliases share the same scratch entry",
                all(item.succeeded() for item in results) and set(engine.workflow_registry._workflows) == original_keys | {key}
                and inventory() == before)
            if name == "workflow":
                lease.pop("request_name")
                check("legacy literal lease without new field survives module reload", send(GetWorkflowMetadataRequest(workflow_name=name)).succeeded())
            saved = await engine.ahandle_request(SaveWorkflowRequest(file_name="metadata-names-" + str(uuid4()),
                display_name="Metadata exact-name fixture", overwrite_existing=False, broadcast_result=False))
            check(name + ": native Save succeeds without changing retained graph",
                saved.succeeded() and Path(saved.file_path).is_file() and inventory() == before)
            check(name + ": saved native key resolves metadata", send(GetWorkflowMetadataRequest(workflow_name=saved.workflow_name)).succeeded())
            check(name + ": old alias cannot redirect into saved workflow",
                not send(GetWorkflowMetadataRequest(workflow_name=name)).succeeded()
                and reg._hmb_legacy_metadata_lease is None and inventory() == before)
        finally:
            close()


def registered_mismatch_case():
    with engine_scope() as engine:
        key = "unsaved:" + str(uuid4())
        reg, owner, library, send, record, flow, inventory, close = setup(engine, key)
        try:
            before = inventory()
            entries = dict(engine.workflow_registry._workflows)
            check("registered canonical key remains native", send(GetWorkflowMetadataRequest(workflow_name=key)).succeeded())
            check("stale UI workflow_1 cannot acquire an unrelated canonical canvas",
                not send(GetWorkflowMetadataRequest(workflow_name="workflow_1")).succeeded()
                and record._name == key and engine.workflow_registry._workflows == entries and inventory() == before
                and getattr(reg, "_hmb_legacy_metadata_lease", None) is None)
            engine.workflow_registry.rekey_workflow(old_key=key, new_key="workflow_2")
            record._name = "workflow_2"
            entries = dict(engine.workflow_registry._workflows)
            check("already registered legacy-looking name is not repaired", send(GetWorkflowMetadataRequest(workflow_name="workflow_2")).succeeded()
                and engine.workflow_registry._workflows == entries and record._name == "workflow_2"
                and getattr(reg, "_hmb_legacy_metadata_lease", None) is None and inventory() == before)
        finally:
            close()


def rejection_and_rollback_case():
    with engine_scope() as engine:
        reg, owner, library, send, record, flow, inventory, close = setup(engine, "workflow_2")
        try:
            before = inventory()
            entries = dict(engine.workflow_registry._workflows)
            record._file_path = str(Path(private.name) / "missing-saved-workflow.py")
            check("path-backed workflow retains native metadata failure",
                not send(GetWorkflowMetadataRequest(workflow_name="workflow_2")).succeeded()
                and record._name == "workflow_2" and engine.workflow_registry._workflows == entries and inventory() == before)
            record._file_path = None
            for node in flow.nodes.values():
                node.metadata["library"] = "ForeignFixture"
            foreign = inventory()
            check("foreign-only workflow remains native", not send(GetWorkflowMetadataRequest(workflow_name="workflow_2")).succeeded()
                and inventory() == foreign and engine.workflow_registry._workflows == entries)
            for node in flow.nodes.values():
                node.metadata["library"] = "HMB_GP_Production"
            engine.node_manager._name_to_parent_flow_name["MetadataSource"] = "OtherFlow"
            check("ambiguous graph cannot be repaired", not send(GetWorkflowMetadataRequest(workflow_name="workflow_2")).succeeded()
                and engine.workflow_registry._workflows == entries)
            engine.node_manager._name_to_parent_flow_name["MetadataSource"] = flow.name
            flags = engine.workflow_manager.variable_substitution._enabled
            flags.update({"workflow_2":False, "UnrelatedFlag":True})
            native_handle = engine.handle_request

            def reject_scratch(request):
                if type(request) is GetWorkflowMetadataRequest and request.workflow_name.startswith("unsaved:"):
                    return GetWorkflowMetadataResultFailure(result_details="controlled native metadata failure")
                return native_handle(request)

            with mock.patch.object(engine, "handle_request", reject_scratch):
                failed = send(GetWorkflowMetadataRequest(workflow_name="workflow_2"))
            check("failed recovery preserves original typed error and rolls back only fresh scratch state",
                not failed.succeeded() and "Workflow 'workflow_2' not found" in str(failed.result_details)
                and record._name == "workflow_2" and inventory() == before and engine.workflow_registry._workflows == entries
                and flags == {"workflow_2":False, "UnrelatedFlag":True})
        finally:
            close()


async def main():
    with engine_scope() as engine:
        if hasattr(engine, "current_workflow_or_none"):
            from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
            opened = engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name="MetadataFlow", display_name="Private Metadata"))
            check("native workflow opened", opened.succeeded())
            runtime = engine.current_workflow()
            flow = engine.flow_manager.get_flow_by_name(opened.flow_name)
            key = engine.context_manager.get_current_workflow_name()
            check("exact native key resolves", engine.handle_request(GetWorkflowMetadataRequest(workflow_name=key)).succeeded())
            check("unrelated legacy name cannot acquire current workflow",
                not engine.handle_request(GetWorkflowMetadataRequest(workflow_name="workflow_2")).succeeded())
            saved = await engine.ahandle_request(SaveWorkflowRequest(
                file_name=str(Path(private.name) / "exact-name.py"), display_name="Private Metadata", broadcast_result=False))
            check("native Save preserves runtime and flow", saved.succeeded() and Path(saved.file_path).is_file()
                and engine.current_workflow() is runtime and engine.flow_manager.get_flow_by_name(flow.name) is flow)
            check("saved native key resolves", engine.handle_request(GetWorkflowMetadataRequest(workflow_name=saved.workflow_name)).succeeded())
            print(json.dumps({"passed": True, "checks": checks, "scope": "native workflow names; historical unregistered aliases require the legacy SDK"}))
            return
    for name in ("workflow", "workflow_1", "workflow_2", "Custom HMB Canvas"):
        await exact_name_case(name)
    registered_mismatch_case()
    rejection_and_rollback_case()
    print(json.dumps({"passed":True, "count":len(checks), "checks":checks,
        "scope":"actual SDK public metadata/native Save; private synthetic HMB graph; no app, provider or installed writes"},
        ensure_ascii=False))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        logging.shutdown()
        private.cleanup()
