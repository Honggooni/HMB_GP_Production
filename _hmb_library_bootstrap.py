"""Register a cold-canvas Generator guard before lazy node modules load.

Existing canvas or node state is never repaired, selected, cleared or replayed.
The official engine bootstrap prepares only an otherwise empty editor session.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import threading
import weakref
from typing import Any
from uuid import UUID

from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
try:
    from griptape_nodes.retained_mode.engine import current_engine
except ImportError:
    # The declared Engine 0.93 minimum predates the engine-scoped accessor.
    # Keep the library loadable there; only this optional cold-start guard
    # requires that newer API.
    current_engine = None
from griptape_nodes.retained_mode.events.context_events import (
    EnsureWorkflowAndFlowRequest,
    EnsureWorkflowAndFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultFailure,
)

_LIBRARY_NAME = "HMB_GP_Production"
_NODE_TYPE = "HMBSeedanceGeneration"
_EMPTY_CONTEXT_MESSAGE = (
    "Attempted to create Node in the Current Context. Failed because the Current Context was empty."
)
_REGISTRY_LOCK = threading.RLock()
_REGISTRATIONS: Any = weakref.WeakKeyDictionary()


def _empty_maps(engine: Any) -> tuple[dict, dict, dict] | None:
    """Require positive evidence of no retained objects, not a missing API.

    These SDK inventory maps are read only. The object table also rules out an
    untracked/intermediate object whose ownership map is not populated yet.
    Unknown layouts leave the stock CreateNode failure untouched.
    """
    maps = (
        getattr(engine.flow_manager, "_name_to_parent_name", None),
        getattr(engine.node_manager, "_name_to_parent_flow_name", None),
        getattr(engine.object_manager, "_name_to_objects", None),
    )
    if all(type(mapping) is dict and not mapping for mapping in maps):
        return maps
    return None


def _native_failure() -> CreateNodeResultFailure:
    return CreateNodeResultFailure(result_details=_EMPTY_CONTEXT_MESSAGE)


def _registered_unsaved_workflow(name: Any) -> bool:
    """Do not bootstrap a saved/unknown workflow that may still be loading."""
    if not isinstance(name, str) or not name.startswith("unsaved:"):
        return False
    try:
        identity = UUID(name[len("unsaved:"):])
        if name != "unsaved:" + str(identity):
            return False
        if WorkflowRegistry.has_workflow_with_name(name) is not True:
            return False
        return WorkflowRegistry.get_workflow_by_name(name).is_saved is False
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


class _Registration:
    def __init__(self, engine: Any, manager: Any) -> None:
        self.engine = weakref.ref(engine)
        self.manager = weakref.ref(manager)
        self.owners: Any = weakref.WeakKeyDictionary()
        self.lock = threading.RLock()
        self.active = True
        # Store this exact callable for matching add/remove across lifecycle.
        self.hook = self.before_create
        self.web_worker_module = None

    def start_web_worker(self) -> None:
        engine = self.engine()
        if not self.active or not self.owners or engine is None:
            return
        try:
            loop = engine.event_manager.event_loop
            if loop is None or loop.is_closed() or not loop.is_running():
                return
            if self.web_worker_module is None:
                path = Path(__file__).with_name("_hmb_web_rerender.py")
                name = "_hmb_web_rerender"
                module = sys.modules.get(name)
                if module is None:
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    sys.modules[name] = module
                elif Path(module.__file__).resolve() != path.resolve():
                    return  # Do not bind another installed library's worker.
                self.web_worker_module = module
            self.web_worker_module.ensure_engine_worker(engine)
        except Exception:
            # Older hosts and optional Broker failures cannot block editing.
            return

    def before_create(self, request: Any, _result_context: Any) -> Any:
        # Dispatch is also the late-loop wakeup after a desktop startup that
        # loaded libraries before initializing its event queue.
        self.start_web_worker()
        if (
            type(request) is not CreateNodeRequest
            or request.node_type != _NODE_TYPE
            or request.specific_library_name not in (None, _LIBRARY_NAME)
            or request.override_parent_flow_name is not None
            or request.initial_setup is not False
            or request.set_as_new_context is not False
        ):
            return None
        attempted_bootstrap = False
        try:
            with self.lock:
                engine = self.engine()
                manager = self.manager()
                if (
                    not self.active
                    or not self.owners
                    or engine is None
                    or manager is None
                    or current_engine() is not engine
                    or engine.event_manager is not manager
                    or engine.library_manager.is_worker is not False
                ):
                    return None
                resolved = LibraryRegistry.get_library_for_node_type(
                    node_type=request.node_type,
                    specific_library_name=request.specific_library_name,
                )
                if (
                    resolved.get_library_data().name != _LIBRARY_NAME
                    or not any(reference() is resolved for reference in self.owners.values())
                ):
                    return None
                context = engine.context_manager
                if context.has_current_flow():
                    return None
                maps = _empty_maps(engine)
                if maps is None:
                    return None
                had_workflow = context.has_current_workflow()
                previous_workflow = context.get_current_workflow_name() if had_workflow else None
                if had_workflow and not _registered_unsaved_workflow(previous_workflow):
                    return None
                # Recheck immediately before any mutation. This guard's lock
                # serializes its own bootstrap requests and unload callbacks.
                current_maps = _empty_maps(engine)
                if (
                    context.has_current_flow()
                    or current_maps is None
                    or not all(current is previous for current, previous in zip(current_maps, maps))
                    or context.has_current_workflow() != had_workflow
                    or (had_workflow and context.get_current_workflow_name() != previous_workflow)
                    or (had_workflow and not _registered_unsaved_workflow(previous_workflow))
                ):
                    return None
                attempted_bootstrap = True
                ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(display_name="Untitled"))
                if not isinstance(ensured, EnsureWorkflowAndFlowResultSuccess):
                    return _native_failure()
                flow_name = ensured.flow_name
                if not isinstance(flow_name, str) or not flow_name:
                    return _native_failure()
                flow = engine.flow_manager.get_flow_by_name(flow_name)
                # No other retained data may have appeared while the official
                # bootstrap ran. Pin its exact flow rather than rediscovering
                # a different ambient canvas during the original CreateNode.
                if (
                    not self.active
                    or engine.library_manager.is_worker is not False
                    or ensured.created_flow is not True
                    or ensured.created_workflow is not (not had_workflow)
                    or not context.has_current_flow()
                    or context.get_current_flow() is not flow
                    or context.get_current_workflow_name() != ensured.workflow_name
                    or (had_workflow and ensured.workflow_name != previous_workflow)
                    or not _registered_unsaved_workflow(ensured.workflow_name)
                    or engine.flow_manager._name_to_parent_name != {flow_name: None}
                    or engine.node_manager._name_to_parent_flow_name
                    or set(engine.object_manager._name_to_objects) != {flow_name}
                    or engine.object_manager._name_to_objects[flow_name] is not flow
                ):
                    return _native_failure()
                request.override_parent_flow_name = flow_name
                return None
        except Exception:
            # Unsupported APIs and preflight failures retain native behavior.
            # Once bootstrap was attempted, do not continue against an unknown
            # newly changed context and accidentally create in another canvas.
            return _native_failure() if attempted_bootstrap else None


class HMBProductionLibrary(AdvancedNodeLibrary):
    def __init__(self) -> None:
        self._registrations: set[_Registration] = set()

    def before_library_nodes_loaded(self, library_data: Any, library: Any) -> None:
        """Register at library load, before the first lazy CreateNode check."""
        try:
            if library_data.name != _LIBRARY_NAME or not callable(current_engine):
                return
            engine = current_engine()
            if engine.library_manager.is_worker is not False:
                return
            manager = engine.event_manager
            if not callable(getattr(manager, "add_pre_dispatch_hook", None)) or not callable(
                getattr(manager, "remove_pre_dispatch_hook", None)
            ):
                return
            library_reference = weakref.ref(library)
            with _REGISTRY_LOCK:
                registration = _REGISTRATIONS.get(manager)
                if registration is None or not registration.active:
                    registration = _Registration(engine, manager)
                    manager.add_pre_dispatch_hook(registration.hook)
                    _REGISTRATIONS[manager] = registration
                elif registration.engine() is not engine:
                    return
                with registration.lock:
                    registration.owners[self] = library_reference
                    self._registrations.add(registration)
                    registration.start_web_worker()
        except Exception:
            # Optional cold-start compatibility never blocks library loading.
            return

    def before_library_unregistered(self, _library_data: Any, _library: Any) -> None:
        with _REGISTRY_LOCK:
            for registration in tuple(self._registrations):
                with registration.lock:
                    registration.owners.pop(self, None)
                    if registration.owners:
                        continue
                    registration.active = False
                    engine = registration.engine()
                    if registration.web_worker_module is not None and engine is not None:
                        registration.web_worker_module.stop_engine_worker(engine)
                    manager = registration.manager()
                    if manager is not None:
                        try:
                            manager.remove_pre_dispatch_hook(registration.hook)
                        except Exception:
                            pass  # Inactive stale callbacks cannot bootstrap.
                        if _REGISTRATIONS.get(manager) is registration:
                            _REGISTRATIONS.pop(manager, None)
            self._registrations.clear()
