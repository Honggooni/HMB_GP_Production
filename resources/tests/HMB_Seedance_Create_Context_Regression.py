"""Actual SDK CreateNode/lazy Advanced lifecycle, with isolated local discovery.

Run in a fresh Desktop engine Python process. The CreateNode handler is never
mocked. Fixtures replace only library discovery and AI-free node modules; one
case lazily constructs the real HMB Generator. No live engine or Provider runs.
"""
from __future__ import annotations

import asyncio
import argparse
import builtins
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
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument("--library-root", type=Path, help="Read an installed library instead of the workspace source")
_arguments = _parser.parse_args()
if _arguments.library_root is not None:
    ROOT = _arguments.library_root.resolve()
_temporary = tempfile.TemporaryDirectory(prefix="hmb-create-context-")
ISOLATED = Path(_temporary.name)
assert ISOLATED.resolve().parent == Path(tempfile.gettempdir()).resolve()
for variable, leaf in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                       ("XDG_STATE_HOME", "state"), ("LOCALAPPDATA", "local"),
                       ("GTN_CONFIG_WORKSPACE_DIRECTORY", "workspace"),
                       ("HMB_IMAGE_PROJECTS_ROOT", "images")):
    location = ISOLATED / leaf
    location.mkdir(parents=True, exist_ok=True)
    os.environ[variable] = str(location)
sys.dont_write_bytecode = True
for stream in (sys.stdout, sys.stderr):
    if callable(getattr(stream, "reconfigure", None)):
        stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT))
try:
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
    from griptape_nodes.retained_mode.engine import engine_scope
    from griptape_nodes.retained_mode.events.context_events import (
        EnsureWorkflowAndFlowRequest, EnsureWorkflowAndFlowResultSuccess,
        SetWorkflowContextRequest, SetWorkflowContextSuccess,
    )
    from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, CreateFlowResultSuccess
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultFailure, CreateNodeResultSuccess
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
except ImportError:
    _temporary.cleanup()
    print("HMB Create context regression: SKIP (installed Desktop SDK required)")
    raise SystemExit(0)

SOURCE = ROOT / "_hmb_library_bootstrap.py"
assert SOURCE.is_file(), "Advanced cold-canvas source is required"
BASE_SCHEMA = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
NETWORK_ATTEMPTS = []
RESULTS = []
SERIAL = 0


def deny_network(*_args, **_kwargs):
    NETWORK_ATTEMPTS.append("blocked")
    raise AssertionError("Create-context fixture attempted network I/O")


def request(**changes):
    fields = dict(node_type="HMBSeedanceGeneration", specific_library_name="HMB_GP_Production",
                  node_name="ContextFixture", create_error_proxy_on_failure=False)
    fields.update(changes)
    payload = CreateNodeRequest(**fields)
    payload.broadcast_result = False
    return payload


def send(engine, payload):
    payload.broadcast_result = False
    return engine.handle_request(payload)


def snapshot(engine):
    context = engine.context_manager
    def retained(value):
        return dict(value) if type(value) is dict else value
    return (context.get_current_workflow_name() if context.has_current_workflow() else None,
            context.get_current_flow().name if context.has_current_flow() else None,
            retained(engine.flow_manager._name_to_parent_name),
            retained(engine.node_manager._name_to_parent_flow_name),
            retained(engine.object_manager._name_to_objects))


def succeeds(engine, payload):
    result = send(engine, payload)
    assert isinstance(result, CreateNodeResultSuccess), (type(result).__name__, str(result.result_details))
    assert engine.node_manager.get_node_parent_flow_by_name(result.node_name) == result.parent_flow_name
    assert engine.flow_manager.get_flow_by_name(result.parent_flow_name).nodes[result.node_name] is engine.node_manager.get_node_by_name(result.node_name)
    return result


def refuses_without_mutation(engine, payload):
    before = snapshot(engine)
    result = send(engine, payload)
    assert isinstance(result, CreateNodeResultFailure), (type(result).__name__, str(result.result_details))
    assert snapshot(engine) == before, "Refused request changed workflow/flow/node ownership"
    return result


class Fixture:
    """Canonical SDK loader/callbacks, without discovery, pip or AI services."""
    def __init__(self, engine, *, actual=False, actual_image=False, name="HMB_GP_Production"):
        global SERIAL
        SERIAL += 1
        self.engine = engine
        self.name = name
        self.directory = ISOLATED / f"library-{SERIAL}"
        self.directory.mkdir()
        self.fixture_file = self.directory / "fixture_nodes.py"
        self.fixture_file.write_text(
            "from griptape_nodes.exe_types.node_types import DataNode\n"
            "class HMBSeedanceGeneration(DataNode):\n"
            "    created = []\n"
            "    def __init__(self, name, metadata=None):\n"
            "        super().__init__(name=name, metadata=metadata)\n"
            "        type(self).created.append(name)\n"
            "class HMBImageGeneration(DataNode):\n"
            "    pass\n"
            "class HMBImageAssetLibrary(DataNode):\n"
            "    pass\n", encoding="utf-8")
        raw = copy.deepcopy(BASE_SCHEMA)
        raw.update(name=name, advanced_library_path=str(SOURCE), widgets=[], scripts=[], workflows=[], settings=[])
        raw["metadata"]["dependencies"] = None
        definitions = {item["class_name"]: item for item in raw["nodes"]}
        selected = []
        for class_name in ("HMBSeedanceGeneration", "HMBImageGeneration", "HMBImageAssetLibrary"):
            definition = copy.deepcopy(definitions[class_name])
            use_source = (actual and class_name == "HMBSeedanceGeneration") or (actual_image and class_name == "HMBImageGeneration")
            definition["file_path"] = str(ROOT / (class_name + ".py")) if use_source else str(self.fixture_file)
            selected.append(definition)
        raw["nodes"] = selected
        self.schema = LibrarySchema.model_validate(raw)
        # Engine 0.104 moved the real loader into a component. Both paths call
        # the SDK implementation; fixture setup must not mock its lifecycle.
        module_loading = getattr(engine.library_manager, "module_loading", engine.library_manager)
        advanced_loader = getattr(module_loading, "load_advanced_library_module", None)
        if advanced_loader is None:
            advanced_loader = engine.library_manager._load_advanced_library_module
        self.advanced = advanced_loader(self.schema, self.directory)
        self.library = LibraryRegistry.generate_new_library(self.schema, advanced_library=self.advanced)
        worker_fields = {"executes_in_worker": False}
        if "requires_worker" in inspect.signature(LibraryManager.LibraryInfo).parameters:
            worker_fields["requires_worker"] = False
        self.info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            library_path=str(self.directory / "manifest.json"), is_sandbox=False,
            library_name=name, library_version=self.schema.metadata.library_version,
            fitness=LibraryManager.LibraryFitness.NOT_EVALUATED, problems=[],
            **worker_fields)
        nodes_loader = getattr(module_loading, "attempt_load_nodes_from_library", None)
        if nodes_loader is None:
            nodes_loader = engine.library_manager._attempt_load_nodes_from_library
        nodes_loader(
            self.schema, self.library, self.directory, self.info, lazy_loading=True)
        assert not self.info.problems, [type(problem).__name__ for problem in self.info.problems]
        assert self.library._node_types["HMBSeedanceGeneration"]._resolved is None, "Fixture was not lazy"

    def unload(self):
        if self.name in LibraryRegistry.list_libraries():
            LibraryRegistry.unregister_library(self.name, event_manager=self.engine.event_manager)


async def case(name, callback, *, actual=False, actual_image=False):
    WorkflowRegistry.clear_user_workflows()
    with engine_scope() as engine:
        engine.event_manager.initialize_queue()
        fixture = Fixture(engine, actual=actual, actual_image=actual_image)
        try:
            outcome = callback(engine, fixture)
            if asyncio.iscoroutine(outcome):
                await outcome
            await asyncio.sleep(0)
        finally:
            for library_name in tuple(LibraryRegistry.list_libraries()):
                LibraryRegistry.unregister_library(library_name, event_manager=engine.event_manager)
    RESULTS.append(name)
    print("PASS " + name)


def set_unsaved(engine, key=None):
    result = send(engine, SetWorkflowContextRequest(workflow_name=key, display_name="Isolated fixture"))
    assert isinstance(result, SetWorkflowContextSuccess), str(result.result_details)
    return result.workflow_name


def cold(engine, fixture):
    assert snapshot(engine) == (None, None, {}, {}, {})
    payload = request()
    result = succeeds(engine, payload)
    assert payload.override_parent_flow_name == result.parent_flow_name
    assert engine.context_manager.get_current_flow().name == result.parent_flow_name
    assert len(engine.flow_manager._name_to_parent_name) == 1
    assert engine.library_manager.is_worker is False


def cold_image(engine, fixture):
    assert snapshot(engine) == (None, None, {}, {}, {})
    payload = request(node_type="HMBImageGeneration", node_name="ColdImageGenerator")
    result = succeeds(engine, payload)
    assert payload.override_parent_flow_name == result.parent_flow_name
    assert engine.context_manager.get_current_flow().name == result.parent_flow_name
    assert len(engine.flow_manager._name_to_parent_name) == 1
    assert type(engine.node_manager.get_node_by_name(result.node_name)).__name__ == "HMBImageGeneration"
    assert fixture.library._node_types["HMBSeedanceGeneration"]._resolved is None


def active_image(engine, fixture):
    ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="ImageActiveFlow"))
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess)
    before = engine.context_manager.get_current_flow()
    payload = request(node_type="HMBImageGeneration", node_name="ActiveImageGenerator")
    result = succeeds(engine, payload)
    assert payload.override_parent_flow_name is None
    assert engine.context_manager.get_current_flow() is before
    assert result.parent_flow_name == ensured.flow_name


def image_worker(engine, fixture):
    engine.library_manager._is_worker = True
    refuses_without_mutation(engine, request(node_type="HMBImageGeneration"))


def native_baseline(engine, fixture):
    hook = engine.event_manager._pre_dispatch_hooks[0]
    engine.event_manager.remove_pre_dispatch_hook(hook)
    try:
        result = refuses_without_mutation(engine, request())
        assert "Attempted to create Node in the Current Context. Failed because the Current Context was empty." in str(result.result_details)
        assert fixture.library._node_types["HMBSeedanceGeneration"]._resolved is None
    finally:
        engine.event_manager.add_pre_dispatch_hook(hook)
    succeeds(engine, request(node_name="AfterNativeBaseline"))


def unsaved(engine, fixture):
    key = set_unsaved(engine)
    result = succeeds(engine, request())
    assert engine.context_manager.get_current_workflow_name() == key
    assert len(engine.flow_manager._name_to_parent_name) == 1


def active(engine, fixture):
    ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="ActiveFlow"))
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess)
    before = engine.context_manager.get_current_flow()
    payload = request()
    result = succeeds(engine, payload)
    assert payload.override_parent_flow_name is None
    assert engine.context_manager.get_current_flow() is before
    assert result.parent_flow_name == ensured.flow_name


def explicit(engine, fixture):
    ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="AmbientFlow"))
    other = send(engine, CreateFlowRequest(parent_flow_name=None, flow_name="ExplicitFlow", set_as_new_context=False))
    assert isinstance(other, CreateFlowResultSuccess)
    ambient = engine.context_manager.get_current_flow()
    result = succeeds(engine, request(override_parent_flow_name=other.flow_name))
    assert result.parent_flow_name == other.flow_name
    assert engine.context_manager.get_current_flow() is ambient
    assert ambient.name == ensured.flow_name
    engine.context_manager.pop_flow()
    result = succeeds(engine, request(node_name="ExplicitWithoutContext", override_parent_flow_name=other.flow_name))
    assert result.parent_flow_name == other.flow_name and not engine.context_manager.has_current_flow()


def unknown_workflow(engine, fixture, key):
    engine.context_manager.push_workflow(workflow_name=key)
    refuses_without_mutation(engine, request())


def saved_workflow(engine, fixture):
    key = set_unsaved(engine)
    workflow = WorkflowRegistry.get_workflow_by_name(key)
    workflow.file_path = str(ISOLATED / "saved-loading.py")
    assert workflow.is_saved is True
    refuses_without_mutation(engine, request())


def missing_registry(engine, fixture):
    key = set_unsaved(engine)
    WorkflowRegistry.delete_workflow_by_name(key)
    refuses_without_mutation(engine, request())


def lost_flow(engine, fixture, include_node=False):
    ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="ExistingFlow"))
    assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess)
    if include_node:
        succeeds(engine, request(node_name="ExistingNode"))
    engine.context_manager.pop_flow()
    refuses_without_mutation(engine, request(node_name="MustNotCreate"))


def worker(engine, fixture):
    engine.library_manager._is_worker = True
    refuses_without_mutation(engine, request())


def retained_map_guard(engine, fixture, owner, field, *, unsupported=False):
    manager = getattr(engine, owner)
    original = getattr(manager, field)
    if unsupported:
        setattr(manager, field, None)
    else:
        original["orphan-evidence"] = object()
    try:
        if unsupported:
            # An unknown object-table layout can also make the SDK's own
            # result/dirty-state bookkeeping reject a request. The guard must
            # leave that native failure intact and must not bootstrap a graph.
            before = snapshot(engine)
            result = send(engine, request())
            assert result.failed() is True
            assert snapshot(engine) == before
        else:
            refuses_without_mutation(engine, request())
    finally:
        setattr(manager, field, original)


def other_engine_guard(engine, fixture):
    with engine_scope() as other:
        other.event_manager.initialize_queue()
        before_other = snapshot(other)
        refuses_without_mutation(engine, request())
        assert snapshot(other) == before_other


def foreign(engine, fixture):
    foreign_fixture = Fixture(engine, name="ForeignLibrary")
    try:
        refuses_without_mutation(engine, request(specific_library_name="ForeignLibrary"))
    finally:
        foreign_fixture.unload()


def duplicate_unload(engine, fixture):
    assert len(engine.event_manager._pre_dispatch_hooks) == 1
    fixture.advanced.before_library_nodes_loaded(fixture.schema, fixture.library)
    fixture.advanced.before_library_nodes_loaded(fixture.schema, fixture.library)
    assert len(engine.event_manager._pre_dispatch_hooks) == 1
    stale_hook = engine.event_manager._pre_dispatch_hooks[0]
    fixture.unload()
    assert not engine.event_manager._pre_dispatch_hooks
    assert stale_hook(request(), {}) is None
    refuses_without_mutation(engine, request())
    fresh = Fixture(engine)
    assert len(engine.event_manager._pre_dispatch_hooks) == 1
    fixture.advanced.before_library_unregistered(fixture.schema, fixture.library)
    assert len(engine.event_manager._pre_dispatch_hooks) == 1
    succeeds(engine, request(node_name="AfterReload"))
    fresh.unload()
    assert not engine.event_manager._pre_dispatch_hooks


def race(engine, fixture):
    fixture.library.get_node_class("HMBSeedanceGeneration")
    def create(index):
        with engine_scope(engine):
            return succeeds(engine, request(node_name=f"Concurrent{index}"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(create, range(12)))
    assert len({result.parent_flow_name for result in results}) == 1
    assert len(engine.flow_manager._name_to_parent_name) == 1
    assert len(engine.node_manager._name_to_parent_flow_name) == 12


def actual_hmb(engine, fixture):
    result = succeeds(engine, request(node_name="ActualHMBGenerator"))
    node = engine.node_manager.get_node_by_name(result.node_name)
    assert type(node).__name__ == "HMBSeedanceGeneration"
    assert any(base.__name__ == "SuccessFailureNode" for base in type(node).__mro__)
    assert node.get_parameter_by_name("VIDEO_OUT") is not None
    assert node.get_parameter_by_name("generation_id") is not None
    assert node.metadata["library"] == "HMB_GP_Production"
    assert result.parent_flow_name == engine.context_manager.get_current_flow().name


async def old_engine_accessor_unavailable():
    """The real loader/native handler still work without the optional new API."""
    WorkflowRegistry.clear_user_workflows()
    attempted_imports = []
    original_import = builtins.__import__

    def older_import(name, *args, **kwargs):
        if name == "griptape_nodes.retained_mode.engine":
            attempted_imports.append(name)
            raise ModuleNotFoundError("No module named '" + name + "'", name=name)
        return original_import(name, *args, **kwargs)

    with engine_scope() as engine:
        engine.event_manager.initialize_queue()
        with mock.patch.object(builtins, "__import__", side_effect=older_import):
            fixture = Fixture(engine)
        try:
            assert attempted_imports, "The real Advanced loader did not exercise the missing import"
            assert not engine.event_manager._pre_dispatch_hooks
            result = refuses_without_mutation(engine, request())
            assert "Current Context was empty" in str(result.result_details)
            assert fixture.library._node_types["HMBSeedanceGeneration"]._resolved is None
            ensured = send(engine, EnsureWorkflowAndFlowRequest(flow_name="OlderNativeFlow"))
            assert isinstance(ensured, EnsureWorkflowAndFlowResultSuccess)
            payload = request(node_name="OlderNativeNode")
            result = succeeds(engine, payload)
            assert payload.override_parent_flow_name is None
            assert result.parent_flow_name == ensured.flow_name
            engine.context_manager.pop_flow()
            result = succeeds(engine, request(node_name="OlderExplicitNode",
                                             override_parent_flow_name=ensured.flow_name))
            assert result.parent_flow_name == ensured.flow_name
            assert not engine.context_manager.has_current_flow()
        finally:
            fixture.unload()
        assert not engine.event_manager._pre_dispatch_hooks
    RESULTS.append("older engine accessor unavailable: library load/native behavior preserved")
    print("PASS " + RESULTS[-1])


async def main():
    # Create asyncio's local wakeup sockets before enforcing no network in all
    # fixture operations, including constructors and engine callbacks.
    with mock.patch.object(socket.socket, "connect", side_effect=deny_network), \
         mock.patch.object(socket.socket, "connect_ex", side_effect=deny_network), \
         mock.patch.object(socket, "create_connection", side_effect=deny_network), \
         mock.patch.object(socket, "getaddrinfo", side_effect=deny_network):
        await old_engine_accessor_unavailable()
        await case("cold actual native CreateNode", cold)
        await case("cold image CreateNode uses the same guarded official bootstrap", cold_image)
        await case("actual source image constructor through cold lazy native CreateNode", cold_image, actual_image=True)
        await case("active image flow stays current without bootstrap", active_image)
        await case("image worker bypass", image_worker)
        for name, changes in (("image initial_setup bypass", {"initial_setup": True}),
                              ("image set-as-context bypass", {"set_as_new_context": True})):
            await case(name, lambda engine, fixture, changes=changes: refuses_without_mutation(
                engine, request(node_type="HMBImageGeneration", **changes)))
        await case("registered lazy native baseline fails before hook repair", native_baseline)
        await case("registered unsaved workflow without flow", unsaved)
        await case("existing active flow stays current", active)
        await case("explicit parent preserved with ambient/empty flow context", explicit)
        for name, changes in (("initial_setup bypass", {"initial_setup": True}),
                              ("set-as-context bypass", {"set_as_new_context": True}),
                              ("wrong HMB class bypass", {"node_type": "HMBImageAssetLibrary"}),
                              ("wrong library name bypass", {"specific_library_name": "MissingLibrary"}),
                              ("wrong explicit flow bypass", {"override_parent_flow_name": "MissingFlow"}),
                              ("empty explicit flow is not a default", {"override_parent_flow_name": ""})):
            await case(name, lambda engine, fixture, changes=changes: refuses_without_mutation(engine, request(**changes)))
        await case("worker bypass", worker)
        for owner, field in (("flow_manager", "_name_to_parent_name"),
                             ("node_manager", "_name_to_parent_flow_name"),
                             ("object_manager", "_name_to_objects")):
            await case("orphan retained evidence " + owner,
                       lambda engine, fixture, owner=owner, field=field: retained_map_guard(engine, fixture, owner, field))
            await case("unsupported retained map " + owner,
                       lambda engine, fixture, owner=owner, field=field: retained_map_guard(engine, fixture, owner, field, unsupported=True))
        await case("request bound to a different engine bypass", other_engine_guard)
        await case("same class foreign owner bypass", foreign)
        await case("saved workflow may still be loading", saved_workflow)
        await case("invalid unsaved UUID bypass", lambda engine, fixture: unknown_workflow(engine, fixture, "unsaved:not-a-uuid"))
        await case("unknown workflow bypass", lambda engine, fixture: unknown_workflow(engine, fixture, "SavedOrUnknown"))
        await case("canonical unsaved absent registry bypass", lambda engine, fixture: unknown_workflow(engine, fixture, "unsaved:" + str(uuid4())))
        await case("removed workflow registry bypass", missing_registry)
        await case("lost existing flow context refusal", lambda engine, fixture: lost_flow(engine, fixture))
        await case("lost existing node context refusal", lambda engine, fixture: lost_flow(engine, fixture, True))
        await case("duplicate lifecycle/unload/stale/re-register", duplicate_unload)
        await case("concurrent cold native CreateNode requests", race)
        await case("actual source HMB constructor through lazy native CreateNode", actual_hmb, actual=True)
    assert not NETWORK_ATTEMPTS
    print(json.dumps({"status": "PASS", "cases": len(RESULTS), "sdk_engine_version": importlib.metadata.version("griptape-nodes-engine"),
                      "create_node_handler_mocked": False, "official_lazy_lifecycle": True,
                      "actual_hmb_constructor": True, "network_requests": 0, "live_workflow_changed": False}, sort_keys=True))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # The isolated SDK owns a rotating file handler in XDG_STATE_HOME.
        # Windows will refuse temp-tree cleanup until that handle is closed.
        logging.shutdown()
        _temporary.cleanup()
