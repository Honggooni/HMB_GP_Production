"""Register cold-canvas and singleton guards plus completed-load migration."""
from __future__ import annotations

import importlib.util
import ast
import hashlib
import inspect
import ipaddress
import logging
from pathlib import Path
import socket
import sys
import textwrap
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
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultFailure,
)
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
try:
    from griptape_nodes.retained_mode.events.node_events import (
        DeserializeSelectedNodesFromCommandsRequest,
        DeserializeSelectedNodesFromCommandsResultFailure,
    )
except ImportError:
    DeserializeSelectedNodesFromCommandsRequest = None
    DeserializeSelectedNodesFromCommandsResultFailure = None
try:
    from griptape_nodes.retained_mode.events.node_events import (
        DuplicateSelectedNodesRequest,
        DuplicateSelectedNodesResultFailure,
    )
except ImportError:
    DuplicateSelectedNodesRequest = None
    DuplicateSelectedNodesResultFailure = None

_LIBRARY_NAME = "HMB_GP_Production"
_NODE_TYPE = "HMBSeedanceGeneration"
_PROMPT_NODE_TYPE = "HMBPromptLibrary"
_AGENT_NODE_TYPE = "HMBAgentLibrary"
_FINISH_NODE_TYPE = "HMBFinishLookLibrary"
_EDITOR_NODE_TYPES = (_PROMPT_NODE_TYPE, _AGENT_NODE_TYPE, _FINISH_NODE_TYPE)
_PROMPT_SINGLE_LOAD_MESSAGE = (
    "HMBPromptLibrary is already loaded in this flow. "
    "Use its Shot controls to manage all Shots; another Prompt was not created."
)
_EMPTY_CONTEXT_MESSAGE = (
    "Attempted to create Node in the Current Context. Failed because the Current Context was empty."
)
_REGISTRY_LOCK = threading.RLock()
_REGISTRATIONS: Any = weakref.WeakKeyDictionary()
_WINDOWS_CLOSE_GUARD_MARKER = "_hmb_windows_transport_close_guard_v1"
_WINDOWS_CLOSE_GUARD_AST_SHA256 = "1726d603431044758617fdb85927f558ed7c179445672c34e73ce1712bdc1958"
_WINDOWS_CLOSE_GUARD_LOCK_KEY = "_hmb_windows_transport_close_lock_v1"


def _windows_transport_close_class() -> Any:
    if sys.platform != "win32" or getattr(sys.implementation, "name", "") != "cpython":
        return None
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        return _ProactorBasePipeTransport
    except ImportError:
        return None


def _windows_transport_close_lock() -> Any:
    # Advanced libraries can be imported under different module names. The
    # CPython module is the process-wide anchor; setdefault is atomic here.
    module = sys.modules.get("asyncio.proactor_events")
    if module is None:
        return None
    lock = vars(module).setdefault(_WINDOWS_CLOSE_GUARD_LOCK_KEY, threading.RLock())
    return lock if type(lock) is type(threading.RLock()) else None


def _announce_windows_close_guard(state: dict[str, Any]) -> None:
    with state["lock"]:
        if state.get("install_announced"):
            return
        state["install_announced"] = True
        owners = len(state["owners"])
    try:
        logging.getLogger(__name__).info(
            "HMB Windows normal-teardown compatibility guard enabled "
            "(recognized CPython stdlib, process-wide, owner_count=%s)", owners)
    except Exception:
        pass


def _known_windows_close_function(candidate: Any, transport_class: Any) -> bool:
    """Unknown runtimes/foreign wrappers retain their exact original behavior."""
    if (not inspect.isfunction(candidate) or hasattr(candidate, "__wrapped__")
            or candidate.__module__ != "asyncio.proactor_events"
            or candidate.__qualname__ != "_ProactorBasePipeTransport._call_connection_lost"
            or candidate.__globals__ is not vars(sys.modules["asyncio.proactor_events"])
            or candidate.__defaults__ is not None or candidate.__kwdefaults__ is not None
            or candidate is not transport_class.__dict__.get("_call_connection_lost")):
        return False
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(candidate)))
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            return False
        canonical = ast.dump(tree.body[0], annotate_fields=True, include_attributes=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest() == _WINDOWS_CLOSE_GUARD_AST_SHA256
    except (OSError, TypeError, SyntaxError, ValueError):
        return False


def _windows_close_diagnostic(transport: Any, sock: Any) -> dict[str, Any]:
    extra = getattr(transport, "_extra", None)
    extra = extra if isinstance(extra, dict) else {}
    def address(key: str, getter: str) -> Any:
        value = extra.get(key)
        if value is None:
            try:
                value = getattr(sock, getter)()
            except Exception:
                value = None
        return value
    local, peer = address("sockname", "getsockname"), address("peername", "getpeername")
    def port(value: Any) -> int | None:
        return value[1] if (isinstance(value, tuple) and len(value) >= 2
            and type(value[1]) is int and 0 <= value[1] <= 65535) else None
    loopback = None
    if isinstance(peer, tuple) and peer:
        try:
            loopback = ipaddress.ip_address(peer[0]).is_loopback
        except (TypeError, ValueError):
            pass
    protocol_type = type(transport._protocol)
    return {"protocol_class": (protocol_type.__module__ + "." + protocol_type.__qualname__)[:200],
        "local_port": port(local), "peer_loopback": loopback, "remote_port": port(peer)}


def _record_windows_close_reset(state: dict[str, Any], diagnostic: dict[str, Any]) -> None:
    with state["lock"]:
        state["handled_count"] = min(2 ** 31 - 1, state["handled_count"] + 1)
        first = state["first_diagnostic"] is None
        if first:
            state["first_diagnostic"] = diagnostic
    if first:
        try:
            logging.getLogger(__name__).info(
                "HMB Windows transport teardown cleanup completed after peer reset: "
                "protocol=%s local_port=%s peer_loopback=%s remote_port=%s",
                diagnostic["protocol_class"], diagnostic["local_port"],
                diagnostic["peer_loopback"], diagnostic["remote_port"])
        except Exception:
            pass  # Optional diagnostics must never replace a protocol failure.


def _acquire_windows_transport_close_guard(owner: Any) -> bool:
    """Own one process-wide, recognized CPython cleanup compatibility patch."""
    transport_class = _windows_transport_close_class()
    if transport_class is None:
        return False
    try:
        weakref.ref(owner)
        lock = _windows_transport_close_lock()
        if lock is None:
            return False
        with lock:
            current = transport_class.__dict__.get("_call_connection_lost")
            state = getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None)
            if state is not None:
                if (type(state) is not dict or state.get("schema") != _WINDOWS_CLOSE_GUARD_MARKER
                        or not isinstance(state.get("owners"), weakref.WeakSet)
                        or getattr(state.get("wrapper"), "_hmb_windows_close_guard_state", None) is not state
                        or (current is not state.get("original") and current is not state.get("wrapper"))):
                    return False
                with state["lock"]:
                    state["owners"].add(owner)
                    if current is state["original"]:
                        transport_class._call_connection_lost = state["wrapper"]
                    _announce_windows_close_guard(state)
                return True
            if not _known_windows_close_function(current, transport_class):
                return False
            state = {"schema": _WINDOWS_CLOSE_GUARD_MARKER, "original": current,
                "owners": weakref.WeakSet(), "lock": threading.RLock(),
                "handled_count": 0, "first_diagnostic": None, "install_announced": False}
            def close(transport: Any, exc: Any) -> None:
                with state["lock"]:
                    active = bool(state["owners"])
                if not active:
                    return state["original"](transport, exc)
                if transport._called_connection_lost:
                    return
                # Recognized CPython/PSF teardown sequence: preserve callback,
                # shutdown, close, detach and completion ordering. Only normal
                # teardown's known Windows shutdown reset is recoverable here.
                diagnostic = None
                try:
                    transport._protocol.connection_lost(exc)
                finally:
                    if hasattr(transport._sock, "shutdown") and transport._sock.fileno() != -1:
                        try:
                            transport._sock.shutdown(socket.SHUT_RDWR)
                        except ConnectionResetError as error:
                            if exc is not None or getattr(error, "winerror", None) != 10054:
                                raise
                            diagnostic = _windows_close_diagnostic(transport, transport._sock)
                    transport._sock.close()
                    transport._sock = None
                    server = transport._server
                    if server is not None:
                        server._detach()
                        transport._server = None
                    transport._called_connection_lost = True
                    if diagnostic is not None:
                        _record_windows_close_reset(state, diagnostic)
            state["wrapper"] = close
            close._hmb_windows_close_guard_state = state
            # Another module/owner may have changed the method during source
            # inspection. Never replace a function we did not just recognize.
            if (transport_class.__dict__.get("_call_connection_lost") is not current
                    or getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None) is not None):
                return False
            state["owners"].add(owner)
            setattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, state)
            transport_class._call_connection_lost = close
            _announce_windows_close_guard(state)
            return True
    except Exception:
        return False  # Optional compatibility cannot block library editing.


def _release_windows_transport_close_guard(owner: Any) -> None:
    transport_class = _windows_transport_close_class()
    if transport_class is None:
        return
    try:
        lock = _windows_transport_close_lock()
        if lock is None:
            return
        with lock:
            state = getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None)
            if (type(state) is not dict or state.get("schema") != _WINDOWS_CLOSE_GUARD_MARKER
                    or not isinstance(state.get("owners"), weakref.WeakSet)
                    or getattr(state.get("wrapper"), "_hmb_windows_close_guard_state", None) is not state):
                return
            with state["lock"]:
                state["owners"].discard(owner)
                if (not state["owners"]
                        and transport_class.__dict__.get("_call_connection_lost") is state["wrapper"]):
                    transport_class._call_connection_lost = state["original"]
    except Exception:
        return  # Unknown foreign state cannot break library unload.


def _windows_transport_close_guard_diagnostics() -> dict[str, Any]:
    transport_class = _windows_transport_close_class()
    state = getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None) if transport_class else None
    if type(state) is not dict or state.get("schema") != _WINDOWS_CLOSE_GUARD_MARKER:
        return {"supported": transport_class is not None, "installed": False, "owner_count": 0, "handled_count": 0}
    with state["lock"]:
        return {"supported": True,
            "installed": transport_class.__dict__.get("_call_connection_lost") is state["wrapper"],
            "owner_count": len(state["owners"]), "handled_count": state["handled_count"],
            "first_diagnostic": dict(state["first_diagnostic"]) if state["first_diagnostic"] else None}

try:
    from griptape_nodes.retained_mode.events.flow_events import DeserializeFlowFromCommandsRequest
    from griptape_nodes.retained_mode.events.workflow_events import (
        RunWorkflowFromScratchRequest, RunWorkflowWithCurrentStateRequest,
        RunWorkflowFromRegistryRequest,
    )
    from griptape_nodes.retained_mode.managers.workflow.loading import is_loading_workflow
    _LOAD_TYPES = (DeserializeFlowFromCommandsRequest, RunWorkflowFromScratchRequest,
        RunWorkflowWithCurrentStateRequest, RunWorkflowFromRegistryRequest)
except ImportError:
    _LOAD_TYPES = ()
    is_loading_workflow = lambda: False


def _migration_module() -> Any:
    path = Path(__file__).with_name("_hmb_workflow_migration.py")
    name = "_hmb_workflow_migration"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    elif Path(module.__file__).resolve() != path.resolve():
        raise RuntimeError("Another installed HMB migration module owns this process")
    return module


def _kind_metadata(node: Any) -> Any:
    metadata = getattr(node, "metadata", None)
    return metadata.get("node_type") if isinstance(metadata, dict) and metadata.get("library") == _LIBRARY_NAME else None


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
        self.prompt_post_hook = self.after_prompt_request
        self.prompt_post_types: list[Any] = []
        self.prompt_pending: dict[Any, tuple[Any, Any]] = {}
        self.load_requests: dict[int, Any] = {}
        self.load_post_hook = self.after_workflow_load
        self.load_post_types: list[Any] = []
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
        migration_failure = self._guard_migration_mutation(request)
        if migration_failure is not None:
            return migration_failure
        self._observe_workflow_load(request)
        prompt_failure = self._guard_prompt_creation(request)
        if prompt_failure is not None:
            return prompt_failure
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

    def _prompt_owner(self, engine: Any, manager: Any) -> bool:
        return bool(
            self.active and self.owners and engine is not None and manager is not None
            and callable(current_engine) and current_engine() is engine
            and engine.event_manager is manager and engine.library_manager.is_worker is False
        )

    def _is_hmb_prompt_create(self, request: Any) -> bool:
        if (type(request) is not CreateNodeRequest or request.node_type not in _EDITOR_NODE_TYPES
                or request.specific_library_name not in (None, _LIBRARY_NAME)):
            return False
        try:
            library = LibraryRegistry.get_library_for_node_type(
                node_type=request.node_type, specific_library_name=request.specific_library_name)
            return bool(library.get_library_data().name == _LIBRARY_NAME
                and any(reference() is library for reference in self.owners.values()))
        except Exception:
            return False

    @staticmethod
    def _prompt_target_flow(engine: Any, create_request: Any) -> Any:
        parent_name = create_request.override_parent_flow_name
        if parent_name is not None:
            try:
                return engine.flow_manager.get_flow_by_name(parent_name)
            except (KeyError, ValueError, TypeError):
                return None  # Preserve the native invalid-parent error.
        context = engine.context_manager
        return context.get_current_flow() if context.has_current_flow() else None

    @staticmethod
    def _flow_has_prompt(flow: Any, node_type: str = _PROMPT_NODE_TYPE) -> bool:
        nodes = getattr(flow, "nodes", None)
        if not isinstance(nodes, dict):
            return False
        for node in nodes.values():
            metadata = getattr(node, "metadata", None)
            if (isinstance(metadata, dict)
                    and metadata.get("library") == _LIBRARY_NAME
                    and metadata.get("node_type") == node_type
                    and not bool(getattr(node, "_hmb_node_deleted", False))):
                return True
        return False

    def _guard_prompt_creation(self, request: Any) -> Any:
        is_create = type(request) is CreateNodeRequest
        is_paste = (DeserializeSelectedNodesFromCommandsRequest is not None
            and type(request) is DeserializeSelectedNodesFromCommandsRequest)
        is_duplicate = (DuplicateSelectedNodesRequest is not None
            and type(request) is DuplicateSelectedNodesRequest)
        if not is_create and not is_paste and not is_duplicate:
            return None
        # Saved hydration restores every original first. Completed-load migration
        # takes a recovery snapshot before consolidating those instances.
        if is_create and (request.initial_setup is not False or not self._is_hmb_prompt_create(request)):
            return None
        with self.lock:
            engine, manager = self.engine(), self.manager()
            if not self._prompt_owner(engine, manager):
                return None
            creates = [request]
            if is_duplicate:
                creates = []
                try:
                    for item in request.nodes_to_duplicate:
                        node = engine.node_manager.get_node_by_name(item[0])
                        metadata = getattr(node, "metadata", None)
                        if not isinstance(metadata, dict):
                            continue
                        node_type = metadata.get("node_type")
                        if node_type not in _EDITOR_NODE_TYPES or metadata.get("library") != _LIBRARY_NAME:
                            continue
                        create = CreateNodeRequest(node_type=node_type, specific_library_name=_LIBRARY_NAME)
                        if self._is_hmb_prompt_create(create):
                            creates.append(create)
                except (KeyError, ValueError, TypeError, IndexError, AttributeError):
                    return None  # Preserve native malformed/missing-node errors.
            if is_paste:
                reader = getattr(engine.node_manager, "_read_copied_commands", None)
                if not callable(reader):
                    return None  # Older unsupported clipboard layouts stay native.
                try:
                    # The SDK's clipboard parser validates the same command
                    # envelope its paste handler consumes. No parameter values
                    # are read and no constructors/engine requests run here.
                    commands = reader(request.deserialize_commands)
                    creates = [item.create_node_command for item in commands.serialized_node_commands
                        if self._is_hmb_prompt_create(item.create_node_command)]
                except Exception:
                    return None  # Native paste reports corrupt clipboard input.
            destinations: dict[tuple[int, str], tuple[Any, int]] = {}
            for create in creates:
                flow = self._prompt_target_flow(engine, create)
                if flow is None:
                    continue
                key = (id(flow), create.node_type)
                destinations[key] = (flow, destinations.get(key, (None, 0))[1] + 1)
            for key, (flow, count) in destinations.items():
                pending = self.prompt_pending.get(key)
                if pending is not None and (pending[0]() is not flow or pending[1]() is None):
                    self.prompt_pending.pop(key, None)
                    pending = None
                if count > 1 or self._flow_has_prompt(flow, key[1]) or (pending is not None and pending[1]() is not request):
                    failure = (CreateNodeResultFailure if is_create else
                        DuplicateSelectedNodesResultFailure if is_duplicate else
                        DeserializeSelectedNodesFromCommandsResultFailure)
                    message = (key[1] + " is already loaded in this flow. Use its Shot controls to manage all Shots; "
                        "another editor was not created.")
                    # This is an expected admission decision, not a broken
                    # node. Keep the typed failure so a paste/duplicate caller
                    # cannot apply copied values or edges to the existing
                    # editor. Authored INFO details suppress the error toast
                    # without mutating the request or hiding native failures.
                    return failure(result_details=ResultDetails(message=message, level=logging.INFO))
            if type(request) in self.prompt_post_types:
                for key, (flow, _count) in destinations.items():
                    self.prompt_pending[key] = (weakref.ref(flow), weakref.ref(request))
        return None

    async def after_prompt_request(self, request: Any, _result: Any) -> None:
        # Notification-only official post-dispatch callback. Release a claim
        # after both success and failure; never alter the request, graph or UI.
        with self.lock:
            for key, (_flow, owner) in tuple(self.prompt_pending.items()):
                if owner() is None or owner() is request:
                    self.prompt_pending.pop(key, None)

    def _observe_workflow_load(self, request: Any) -> None:
        engine, manager = self.engine(), self.manager()
        if not self._prompt_owner(engine, manager):
            return
        if type(request) in _LOAD_TYPES:
            with self.lock:
                self.load_requests[id(request)] = weakref.ref(request)
            return
        if type(request) is SetParameterValueRequest and request.initial_setup is True:
            # SDK before_value_set runs even for initial_setup and transforms
            # request.value before the node's setter sees it. Capture original
            # saved identity here; never change that request or its value.
            name = request.node_name
            if name is None and engine.context_manager.has_current_node():
                name = engine.context_manager.get_current_node().name
            try:
                node = engine.node_manager.get_node_by_name(name)
            except (KeyError, ValueError, TypeError):
                node = None
            hook = getattr(node, "_hmb_capture_saved_parameter_value", None)
            if (_kind_metadata(node) in (_AGENT_NODE_TYPE, _FINISH_NODE_TYPE) and callable(hook)
                    and (is_loading_workflow() or self.load_requests)):
                hook(request.parameter_name, request.value, is_output=request.is_output)
            return
        if (type(request) is CreateNodeRequest and request.initial_setup is True
                and self._is_hmb_prompt_create(request)
                and (is_loading_workflow() or self.load_requests)):
            flow = self._prompt_target_flow(engine, request)
            if flow is not None:
                _migration_module().mark_flow_migration_pending(engine, flow.name)

    async def after_workflow_load(self, request: Any, result: Any) -> None:
        """Notification only: coordinator requests run on a later empty context."""
        engine, manager = self.engine(), self.manager()
        if not self._prompt_owner(engine, manager):
            return
        with self.lock:
            self.load_requests.pop(id(request), None)
            self.load_requests = {key: owner for key, owner in self.load_requests.items() if owner() is not None}
            if self.load_requests:
                return
        migration = _migration_module()
        if result.succeeded():
            migration.schedule_loaded_flow_migrations(engine)
        else:
            for name in migration.pending_flow_names(engine):
                migration.clear_flow_migration_pending(engine, name)

    def _guard_migration_mutation(self, request: Any) -> Any:
        engine = self.engine()
        if engine is None:
            return None
        migration = sys.modules.get("_hmb_workflow_migration")
        if migration is None or migration.mutation_is_internal() or not migration.flow_migration_inflight(engine):
            return None
        name = type(request).__name__
        execution = name in {"StartFlowRequest", "StartLocalSubflowRequest", "StartFlowFromNodeRequest",
            "ContinueExecutionStepRequest", "ExecuteNodeRequest", "ResolveNodeRequest",
            "RunWorkflowFromScratchRequest", "RunWorkflowWithCurrentStateRequest", "RunWorkflowFromRegistryRequest"}
        if not execution and not name.startswith(("Create", "Delete", "Remove", "Set", "Alter", "Add", "Move", "Rename", "Reset", "Resolve", "Run", "Clear", "Deserialize", "Duplicate", "Import", "Unregister", "Reload")):
            return None
        flows = {getattr(request, key, None) for key in ("flow_name", "override_parent_flow_name", "parent_flow_name")}
        flows.discard(None)
        for key in ("node_name", "source_node_name", "target_node_name"):
            node_name = getattr(request, key, None)
            parent = engine.node_manager._name_to_parent_flow_name.get(node_name)
            if parent is not None:
                flows.add(parent)
        for key in ("node_names", "nodes_to_delete", "nodes_to_duplicate"):
            for item in getattr(request, key, ()) or ():
                node_name = item[0] if isinstance(item, (list, tuple)) and item else item
                if isinstance(node_name, str):
                    parent = engine.node_manager._name_to_parent_flow_name.get(node_name)
                    if parent is not None:
                        flows.add(parent)
        if not flows and engine.context_manager.has_current_flow():
            flows.add(engine.context_manager.get_current_flow().name)
        # Native migration deletion is permitted only while the whole engine is
        # idle, so execution in a different flow must wait for consolidation too.
        global_mutation = execution or type(request) in _LOAD_TYPES or name.startswith(("ClearAll", "DeleteWorkflow", "ResetWorkflow", "UnregisterLibrary", "ReloadLibrary"))
        if global_mutation or not flows or any(migration.flow_migration_inflight(engine, flow_name) for flow_name in flows):
            from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
            return GenericResultFailure(result_details="HMB editor consolidation is updating this flow. Retry after it finishes; no render was started.")
        return None


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
                    if callable(getattr(manager, "add_post_dispatch_hook", None)) and callable(getattr(manager, "remove_post_dispatch_hook", None)):
                        for request_type in (CreateNodeRequest, DeserializeSelectedNodesFromCommandsRequest):
                            if request_type is not None:
                                manager.add_post_dispatch_hook(request_type, registration.prompt_post_hook)
                                registration.prompt_post_types.append(request_type)
                        for request_type in _LOAD_TYPES:
                            manager.add_post_dispatch_hook(request_type, registration.load_post_hook)
                            registration.load_post_types.append(request_type)
                    _REGISTRATIONS[manager] = registration
                elif registration.engine() is not engine:
                    return
                with registration.lock:
                    registration.owners[self] = library_reference
                    self._registrations.add(registration)
                    _acquire_windows_transport_close_guard(registration)
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
                    _release_windows_transport_close_guard(registration)
                    registration.prompt_pending.clear()
                    registration.load_requests.clear()
                    engine = registration.engine()
                    migration = sys.modules.get("_hmb_workflow_migration")
                    if migration is not None and engine is not None:
                        migration.cancel_queued_flow_migrations(engine)
                    if registration.web_worker_module is not None and engine is not None:
                        registration.web_worker_module.stop_engine_worker(engine)
                    manager = registration.manager()
                    if manager is not None:
                        try:
                            manager.remove_pre_dispatch_hook(registration.hook)
                        except Exception:
                            pass  # Inactive stale callbacks cannot bootstrap.
                        for request_type in registration.prompt_post_types:
                            try:
                                manager.remove_post_dispatch_hook(request_type, registration.prompt_post_hook)
                            except Exception:
                                pass
                        registration.prompt_post_types.clear()
                        for request_type in registration.load_post_types:
                            try:
                                manager.remove_post_dispatch_hook(request_type, registration.load_post_hook)
                            except Exception:
                                pass
                        registration.load_post_types.clear()
                        if _REGISTRATIONS.get(manager) is registration:
                            _REGISTRATIONS.pop(manager, None)
            self._registrations.clear()
