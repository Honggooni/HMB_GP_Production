"""Real installed-SDK serializer regression; private process, no engine or render.

Run with the supported SDK interpreter. No saved workflow is executed, and no
installed file is changed. Only this test process's native static method is
temporarily guarded and restored through the library's public lifecycle.
"""
from __future__ import annotations

import gc
import ast
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import dataclasses
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import weakref
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
private = tempfile.TemporaryDirectory(prefix="hmb-save-identity-test-")
for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
        "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
        "GTN_CONFIG_WORKSPACE_DIRECTORY"):
    value = Path(private.name) / key
    value.mkdir()
    os.environ[key] = str(value)

import _hmb_workflow_serialization_compat as target
from griptape_nodes.retained_mode.events.node_events import SerializedParameterValueTracker
from griptape_nodes.retained_mode.managers.node_manager import NodeManager
from griptape_nodes.serialization.values import encode_value
from griptape.artifacts.image_url_artifact import ImageUrlArtifact

class Owner:
    pass

class TrackedList(list):
    pass

original = NodeManager.__dict__[target._METHOD]
parameter = SimpleNamespace(serializable=True)
checks = []

def call(value, tracker, pool, name="parameter", supplied_parameter=parameter):
    return NodeManager._handle_value_hashing(value, tracker, pool,
        supplied_parameter, name, "Isolated serializer test", is_output=False)

def restored(command, pool):
    return pool[command.unique_value_uuid]

def check(label, condition):
    assert condition, label
    checks.append(label)


async def legacy_metadata_context(engine, stale_case=None):
    """Actual native requests and inventory; no user graph, app or provider."""
    from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
    from griptape_nodes.exe_types.node_types import DataNode
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest, GetWorkflowContextRequest
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, SerializeFlowToCommandsRequest, DeserializeFlowFromCommandsRequest, DeleteFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.workflow_events import GetWorkflowMetadataRequest, GetWorkflowMetadataResultFailure, SaveWorkflowRequest
    import _hmb_library_bootstrap as bootstrap
    class MetadataFixture(DataNode):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.add_parameter(Parameter(name="authored", type="str", default_value="", allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT}))
        def process(self):
            raise AssertionError("Metadata recovery must never execute a node")
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
    engine.event_manager.add_pre_dispatch_hook(registration.hook)
    def send(request):
        request.broadcast_result = False
        return engine.handle_request(request)
    def context():
        result = send(GetWorkflowContextRequest())
        return result.workflow_name, result.is_saved
    def metadata():
        request = GetWorkflowMetadataRequest(workflow_name="workflow")
        result = send(request)
        check("original metadata request identity remains unchanged", request.workflow_name == "workflow")
        return result
    def native_failure(label):
        result = metadata()
        check(label, not result.succeeded() and "Workflow 'workflow' not found" in str(result.result_details))
    def inventory():
        return (id(record), id(flow), {name:id(node) for name,node in flow.nodes.items()},
            copy.deepcopy({name:(node.metadata, dict(node.parameter_values), dict(node.parameter_output_values)) for name,node in flow.nodes.items()}),
            sorted((edge.source_node.name,edge.source_parameter.name,edge.target_node.name,edge.target_parameter.name)
                for edge in engine.flow_manager.get_connections().connections.values()))
    assert send(SetWorkflowContextRequest(workflow_name="workflow")).succeeded()
    flow_result = send(CreateFlowRequest(flow_name="MetadataLegacyFixture", parent_flow_name=None))
    assert flow_result.succeeded()
    for name in ("MetadataSource", "MetadataTarget"):
        result = send(CreateNodeRequest(node_type="HMBImageAssetLibrary", specific_library_name=schema.name,
            node_name=name, initial_setup=True, create_error_proxy_on_failure=False))
        assert result.succeeded(), str(result.result_details)
        assert send(SetParameterValueRequest(node_name=result.node_name, parameter_name="authored", value=name+" authored PNG/task/shot sentinel")).succeeded()
    assert send(CreateConnectionRequest(source_node_name="MetadataSource", source_parameter_name="authored", target_node_name="MetadataTarget", target_parameter_name="authored", initial_setup=True)).succeeded()
    record = engine.context_manager._workflow_stack[0]
    flow = engine.context_manager.get_current_flow()
    before = inventory()
    engine.workflow_manager.variable_substitution._enabled["workflow"] = False
    # Refuse foreign, deleted, ambiguous and path-backed canvases without
    # hiding the native metadata result or changing any retained identity.
    registration.active = False
    native_failure("inactive registration retains native metadata failure")
    registration.active = True
    saved_metadata = copy.deepcopy(flow.nodes["MetadataSource"].metadata)
    for node in flow.nodes.values():node.metadata["library"] = "ForeignFixture"
    native_failure("foreign-only flow cannot acquire an HMB metadata alias")
    for node in flow.nodes.values():node.metadata["library"] = schema.name
    flow.nodes["MetadataSource"]._hmb_node_deleted = True
    native_failure("deleted retained node cannot repair a workflow")
    del flow.nodes["MetadataSource"]._hmb_node_deleted
    record._file_path = str(Path(private.name)/"missing-path-backed-workflow.py")
    path_result = metadata()
    check("path-backed workflow keeps its native file failure", not path_result.succeeded() and context()==("workflow",None))
    record._file_path = None
    engine.node_manager._name_to_parent_flow_name["MetadataSource"] = "MissingFlow"
    native_failure("conflicting node inventory preserves native failure")
    engine.node_manager._name_to_parent_flow_name["MetadataSource"] = flow.name
    with mock.patch.object(type(engine.workflow_registry), "ensure_unsaved", lambda *_a, **_k: None):
        native_failure("foreign SDK descriptor is never invoked for recovery")
    check("negative cases retain context flow nodes edges and values", inventory()==before)
    # Force a failure AFTER native scratch registration and context transfer.
    # The original request then reaches its unchanged native failure path.
    native_handle=engine.handle_request
    def reject_translated(request):
        if type(request) is GetWorkflowMetadataRequest and request.workflow_name.startswith("unsaved:"):
            return GetWorkflowMetadataResultFailure(result_details="controlled native metadata failure")
        return native_handle(request)
    keys_before=set(engine.workflow_registry._workflows)
    with mock.patch.object(engine,"handle_request",reject_translated):
        native_failure("failed native metadata lookup rolls the repair back")
    check("rollback removes only fresh scratch entry and retains explicit flag",
        context()==("workflow",None) and set(engine.workflow_registry._workflows)==keys_before
        and engine.workflow_manager.variable_substitution._enabled=={"workflow":False} and inventory()==before)
    # Racing original metadata requests share the registration's synchronous
    # lock. No await, second context, graph rebuild or provider request occurs.
    def concurrent_lookup():
        return send(GetWorkflowMetadataRequest(workflow_name="workflow"))
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda context:context.run(concurrent_lookup), [copy_context() for _ in range(8)]))
    check("concurrent original metadata requests all receive native success", all(result.succeeded() for result in results))
    key,is_saved=context()
    check("one honest scratch identity is shared by duplicate requests", key.startswith("unsaved:") and is_saved is False
        and set(engine.workflow_registry._workflows)==keys_before|{key})
    check("original old-key metadata requests retain their leased alias", metadata().succeeded() and context()==(key,False))
    check("repair retains authored graph and explicit substitution flag", inventory()==before
        and engine.workflow_manager.variable_substitution._enabled=={key:False})
    if stale_case is not None:
        if stale_case == "foreign":
            for node in flow.nodes.values():node.metadata["library"] = "ForeignAfterLease"
        elif stale_case == "deleted":
            engine.workflow_registry.delete_workflow_by_name(key)
        elif stale_case == "path_backed":
            record._file_path = str(Path(private.name)/"path-added-after-lease.py")
        elif stale_case == "unload":
            registration.active=False
            target.release(registration)
        else:raise AssertionError(stale_case)
        expected=inventory()
        native_failure("stale alias preserves native failure after "+stale_case)
        check("stale alias is dropped without touching authored graph after "+stale_case,
            getattr(registration,"_hmb_legacy_metadata_lease",None) is None and inventory()==expected)
        engine.event_manager.remove_pre_dispatch_hook(registration.hook)
        registration.active=False
        target.release(registration)
        LibraryRegistry.unregister_library(schema.name,event_manager=engine.event_manager)
        return
    # Native Save owns the next identity transition. The alias must expire
    # once that saved key is handed back, never redirect a deleted old canvas.
    saved = await engine.ahandle_request(SaveWorkflowRequest(file_name="metadata-context-native-save", display_name="Metadata Context Native Save", broadcast_result=False))
    check("native Save succeeds after old-key metadata recovery", saved.succeeded())
    check("native Save rekeys the same retained graph to a real saved file", context()==(saved.workflow_name,True)
        and Path(saved.file_path).is_file() and inventory()==before)
    check("saved key resolves native metadata", send(GetWorkflowMetadataRequest(workflow_name=saved.workflow_name)).succeeded())
    check("legacy alias expires after native Save", not metadata().succeeded()
        and getattr(registration,"_hmb_legacy_metadata_lease",None) is None)
    tree=ast.parse(Path(saved.file_path).read_text("utf-8"));compile(tree,saved.file_path,"exec")
    commands=send(SerializeFlowToCommandsRequest(flow_name=flow.name,include_create_flow_command=True)).serialized_flow_commands
    authored={name:node.get_parameter_value("authored") for name,node in flow.nodes.items()}
    original_nodes=dict(flow.nodes)
    engine.event_manager.remove_pre_dispatch_hook(registration.hook)
    registration.active=False
    target.release(registration)
    assert send(DeleteFlowRequest(flow_name=flow.name)).succeeded()
    restored=await engine.ahandle_request(DeserializeFlowFromCommandsRequest(serialized_flow_commands=commands,broadcast_result=False))
    check("native commands cold-reopen after metadata recovery", restored.succeeded())
    reopened=engine.flow_manager.get_flow_by_name(restored.flow_name)
    check("cold reopen preserves authored values with fresh objects", {name:node.get_parameter_value("authored") for name,node in reopened.nodes.items()}==authored
        and all(node is not original_nodes[name] for name,node in reopened.nodes.items()))
    check("metadata lease is registration-owned and released on unload", getattr(registration,"_hmb_legacy_metadata_lease",None) is None)
    LibraryRegistry.unregister_library(schema.name,event_manager=engine.event_manager)

try:
    host = target._host()
    check("exact SDK method recognized", host is not None and target._known_descriptor(original, *host))
    # The unchecked native function must exhibit the concrete bug before the
    # fix is tested. The allocated IDs are real, never supplied by a mock.
    tracker = SerializedParameterValueTracker()
    pool = {}
    value = [{"image": "diagnostic-only"}]
    old_id = id(value)
    first = call(value, tracker, pool, "reference_images")
    del value
    value = []
    for _ in range(10000):
        if id(value) == old_id:
            break
        del value
        value = []
    check("native temporary-list identity reuse reproduced", id(value) == old_id)
    second = call(value, tracker, pool, "VIDEO_REFERENCES")
    check("native regression reproduced before correction", restored(second, pool) != [])
    del value, tracker, pool

    first_owner, second_owner = Owner(), Owner()
    check("first owner acquires", target.acquire(first_owner))
    check("duplicate acquire is idempotent", target.acquire(first_owner) and target.diagnostics()["owner_count"] == 1)
    guarded = NodeManager.__dict__[target._METHOD]
    check("descriptor remains staticmethod", type(guarded) is staticmethod)
    check("second owner acquires same wrapper", target.acquire(second_owner) and NodeManager.__dict__[target._METHOD] is guarded)

    tracker = SerializedParameterValueTracker()
    pool = {}
    image = ImageUrlArtifact("https://example.invalid/diagnostic-image.png")
    values = [[], {}, "", 0, False, [image], {"nested": [[], {}, "", 0, False]}]
    for i, value in enumerate(values):
        command = call(value, tracker, pool, str(i))
        check("native encoding preserved " + str(i), restored(command, pool) == encode_value(value))
    shared = [image]
    left = call(shared, tracker, pool, "shared_left")
    right = call(shared, tracker, pool, "shared_right")
    check("shared aliases preserve native pooled key", left.unique_value_uuid == right.unique_value_uuid)
    check("same-content distinct objects keep native deduplication",
        call([image], tracker, pool, "independent").unique_value_uuid == left.unique_value_uuid)

    value = TrackedList([image])
    live_value = weakref.ref(value)
    tracker_ref = weakref.ref(tracker)
    call(value, tracker, pool, "temporary_image_list")
    del value
    gc.collect()
    check("temporary value retained while save tracker lives", live_value() is not None)
    empty = call([], tracker, pool, "VIDEO_REFERENCES")
    check("empty video references never inherit image references", restored(empty, pool) == [])
    check("private references are not serialized tracker fields", target._VALUES_KEY not in dataclasses.asdict(tracker))
    del tracker
    gc.collect()
    check("tracker and temporary media released after save", tracker_ref() is None and live_value() is None)

    failure = RuntimeError("native serialization failure")
    class BrokenParameter:
        @property
        def serializable(self):
            raise failure
    tracker = SerializedParameterValueTracker()
    value = TrackedList(["failed save"])
    live_value, tracker_ref = weakref.ref(value), weakref.ref(tracker)
    try:
        call(value, tracker, {}, supplied_parameter=BrokenParameter())
    except RuntimeError as caught:
        check("native error is propagated unchanged", caught is failure)
    else:
        raise AssertionError("Native failure was suppressed")
    failure.__traceback__ = None
    del value, tracker
    gc.collect()
    check("failed save releases tracker and media", tracker_ref() is None and live_value() is None)

    # Importing the advanced library under another name/reloading it must not
    # add a second wrapper or lose the ownership of its first import.
    spec = importlib.util.spec_from_file_location("_hmb_save_guard_second_import", ROOT / "_hmb_workflow_serialization_compat.py")
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)
    third_owner = Owner()
    check("second module import shares process-wide state", other.acquire(third_owner)
        and NodeManager.__dict__[target._METHOD] is guarded and other.diagnostics()["owner_count"] == 3)
    target.release(first_owner)
    target.release(second_owner)
    check("remaining owner keeps guard", NodeManager.__dict__[target._METHOD] is guarded)
    other.release(third_owner)
    check("last release restores exact native descriptor", NodeManager.__dict__[target._METHOD] is original)
    check("reacquire works after unload", target.acquire(first_owner)
        and NodeManager.__dict__[target._METHOD] is guarded)

    foreign = staticmethod(lambda *args, **kwargs: "foreign")
    NodeManager._handle_value_hashing = foreign
    check("foreign wrapper is never replaced by acquire", not other.acquire(second_owner)
        and NodeManager.__dict__[target._METHOD] is foreign)
    target.release(first_owner)
    check("foreign wrapper survives unload", NodeManager.__dict__[target._METHOD] is foreign)
    NodeManager._handle_value_hashing = original
    ephemeral_owner = Owner()
    check("owner can reacquire after foreign code restores native", target.acquire(ephemeral_owner))
    del ephemeral_owner
    gc.collect()
    check("weak owner collection restores native descriptor", NodeManager.__dict__[target._METHOD] is original)
    check("non-weak owner does not install partial guard", not target.acquire(object())
        and NodeManager.__dict__[target._METHOD] is original)
    check("foreign static function fails source recognition", not target._known_descriptor(foreign, *host))
    from griptape_nodes.retained_mode.engine import engine_scope
    with engine_scope() as engine:
        asyncio.run(legacy_metadata_context(engine))
    for stale_case in ("foreign", "deleted", "path_backed", "unload"):
        with engine_scope() as engine:
            asyncio.run(legacy_metadata_context(engine, stale_case))
    print(json.dumps({"passed": True, "checks": checks, "count": len(checks),
        "scope": "real SDK static serializer and library guard lifecycle; no live editor or render"}, ensure_ascii=False))
finally:
    NodeManager._handle_value_hashing = original
    for name in ("first_owner", "second_owner", "third_owner"):
        if name in globals():
            target.release(globals()[name])
    logging.shutdown()
    private.cleanup()
