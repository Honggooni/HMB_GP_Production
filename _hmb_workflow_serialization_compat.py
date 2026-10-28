"""Keep temporary SDK parameter values alive for their save tracker only.

The recognized SDK pools encoded values by content, but looks up an earlier
encoding by object ID. ParameterList readers build temporary lists, so Python
may reuse a released list's ID for a different parameter during the same save.
Retaining the source objects until that tracker dies makes its identity lookup
valid. Native commands, encoding, content keys and parameter values are intact.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import sys
import textwrap
import threading
import weakref
from typing import Any
from uuid import uuid4

_MODULE = "griptape_nodes.retained_mode.managers.node_manager"
_TRACKER_MODULE = "griptape_nodes.retained_mode.events.node_events"
_METHOD = "_handle_value_hashing"
_STATE_KEY = "_hmb_save_value_identity_guard_v1"
_LOCK_KEY = "_hmb_save_value_identity_lock_v1"
_VALUES_KEY = "_hmb_save_retained_values_v1"
_AST_SHA256 = "ec3ed683f0b114ac242232c16a741d49dc12d87b489c470ecfa6493d3d82edad"


def _host() -> tuple[Any, Any, Any] | None:
    try:
        from griptape_nodes.retained_mode.managers.node_manager import NodeManager
        from griptape_nodes.retained_mode.events.node_events import SerializedParameterValueTracker
        module = sys.modules.get(_MODULE)
        tracker_module = sys.modules.get(_TRACKER_MODULE)
        if (module is None or tracker_module is None
                or vars(module).get("NodeManager") is not NodeManager
                or vars(tracker_module).get("SerializedParameterValueTracker") is not SerializedParameterValueTracker
                or NodeManager.__module__ != _MODULE or NodeManager.__qualname__ != "NodeManager"
                or SerializedParameterValueTracker.__module__ != _TRACKER_MODULE
                or SerializedParameterValueTracker.__qualname__ != "SerializedParameterValueTracker"):
            return None
        return module, NodeManager, SerializedParameterValueTracker
    except (ImportError, AttributeError):
        return None


def _known_descriptor(descriptor: Any, module: Any, node_class: Any, tracker_class: Any) -> bool:
    if type(descriptor) is not staticmethod:
        return False
    candidate = descriptor.__func__
    if (not inspect.isfunction(candidate) or hasattr(candidate, "__wrapped__")
            or candidate.__module__ != _MODULE
            or candidate.__qualname__ != "NodeManager._handle_value_hashing"
            or candidate.__globals__ is not vars(module)
            or candidate.__defaults__ is not None or candidate.__kwdefaults__ is not None
            or candidate.__globals__.get("SerializedParameterValueTracker") is not tracker_class
            or node_class.__dict__.get(_METHOD) is not descriptor):
        return False
    try:
        signature = inspect.signature(candidate)
        expected = ("value", "serialized_parameter_value_tracker", "unique_parameter_uuid_to_values",
            "parameter", "parameter_name", "node_name", "is_output")
        if tuple(signature.parameters) != expected:
            return False
        for name, parameter in signature.parameters.items():
            kind = inspect.Parameter.KEYWORD_ONLY if name == "is_output" else inspect.Parameter.POSITIONAL_OR_KEYWORD
            if parameter.kind != kind or parameter.default is not inspect.Parameter.empty:
                return False
        tree = ast.parse(textwrap.dedent(inspect.getsource(candidate)))
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            return False
        canonical = ast.dump(tree.body[0], annotate_fields=True, include_attributes=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest() == _AST_SHA256
    except (OSError, TypeError, SyntaxError, ValueError):
        return False


def _valid_state(state: Any, lock: Any, tracker_class: Any) -> bool:
    return (type(state) is dict and state.get("schema") == _STATE_KEY
        and state.get("lock") is lock and state.get("tracker_class") is tracker_class
        and type(state.get("owners")) is dict
        and type(state.get("original")) is staticmethod
        and type(state.get("wrapper")) is staticmethod
        and getattr(state["wrapper"].__func__, "_hmb_save_identity_state", None) is state)


def _restore_if_unowned(node_class: Any, state: dict[str, Any]) -> None:
    if not state["owners"] and node_class.__dict__.get(_METHOD) is state["wrapper"]:
        setattr(node_class, _METHOD, state["original"])


def _add_owner(node_class: Any, state: dict[str, Any], owner: Any) -> None:
    key = id(owner)
    previous = state["owners"].get(key)
    if previous is not None and previous() is owner:
        return
    def owner_gone(reference: Any) -> None:
        with state["lock"]:
            if state["owners"].get(key) is reference:
                state["owners"].pop(key, None)
                _restore_if_unowned(node_class, state)
    state["owners"][key] = weakref.ref(owner, owner_gone)


def acquire(owner: Any) -> bool:
    """Enable once for recognized SDK code; unknown hosts remain untouched."""
    host = _host()
    if host is None:
        return False
    module, node_class, tracker_class = host
    try:
        weakref.ref(owner)
        lock = vars(module).setdefault(_LOCK_KEY, threading.RLock())
        if type(lock) is not type(threading.RLock()):
            return False
        with lock:
            current = node_class.__dict__.get(_METHOD)
            state = node_class.__dict__.get(_STATE_KEY)
            if state is not None:
                if (not _valid_state(state, lock, tracker_class)
                        or (current is not state["original"] and current is not state["wrapper"])):
                    return False
                _add_owner(node_class, state, owner)
                if current is state["original"]:
                    setattr(node_class, _METHOD, state["wrapper"])
                return True
            if not _known_descriptor(current, module, node_class, tracker_class):
                return False
            state = {"schema": _STATE_KEY, "lock": lock, "tracker_class": tracker_class,
                "original": current, "owners": {}}
            original = current.__func__
            def retain(value: Any, serialized_parameter_value_tracker: Any,
                    unique_parameter_uuid_to_values: dict, parameter: Any,
                    parameter_name: str, node_name: str, *, is_output: bool) -> Any:
                with lock:
                    if state["owners"] and type(serialized_parameter_value_tracker) is tracker_class:
                        # The tracker owns these references. Neither the library
                        # nor this wrapper keeps a tracker or saved media alive.
                        retained = vars(serialized_parameter_value_tracker).setdefault(_VALUES_KEY, {})
                        if type(retained) is not dict:
                            raise RuntimeError("Conflicting workflow serialization compatibility state")
                        retained[id(value)] = value
                return original(value, serialized_parameter_value_tracker,
                    unique_parameter_uuid_to_values, parameter, parameter_name, node_name,
                    is_output=is_output)
            retain._hmb_save_identity_state = state
            state["wrapper"] = staticmethod(retain)
            if (node_class.__dict__.get(_METHOD) is not current
                    or node_class.__dict__.get(_STATE_KEY) is not None):
                return False
            _add_owner(node_class, state, owner)
            setattr(node_class, _STATE_KEY, state)
            try:
                setattr(node_class, _METHOD, state["wrapper"])
            except Exception:
                if node_class.__dict__.get(_STATE_KEY) is state:
                    delattr(node_class, _STATE_KEY)
                state["owners"].clear()
                raise
            return True
    except Exception:
        return False


def release(owner: Any) -> None:
    """Restore the exact original static descriptor after the last owner."""
    # The metadata alias belongs to this engine registration, never to an SDK
    # class or a process-wide name. Unload cannot retain a stale canvas lease.
    if hasattr(owner, "_hmb_legacy_metadata_lease"):
        owner._hmb_legacy_metadata_lease = None
    host = _host()
    if host is None:
        return
    module, node_class, tracker_class = host
    lock = vars(module).get(_LOCK_KEY)
    if type(lock) is not type(threading.RLock()):
        return
    with lock:
        state = node_class.__dict__.get(_STATE_KEY)
        if not _valid_state(state, lock, tracker_class):
            return
        previous = state["owners"].get(id(owner))
        if previous is not None and previous() is owner:
            state["owners"].pop(id(owner), None)
        _restore_if_unowned(node_class, state)


def diagnostics() -> dict[str, Any]:
    host = _host()
    if host is None:
        return {"installed": False, "owner_count": 0}
    module, node_class, tracker_class = host
    lock = vars(module).get(_LOCK_KEY)
    if type(lock) is not type(threading.RLock()):
        return {"installed": False, "owner_count": 0}
    with lock:
        state = node_class.__dict__.get(_STATE_KEY)
        if not _valid_state(state, lock, tracker_class):
            return {"installed": False, "owner_count": 0}
        return {"installed": node_class.__dict__.get(_METHOD) is state["wrapper"],
            "owner_count": len(state["owners"])}


def _native_bound_method(instance: Any, name: str, module_name: str) -> bool:
    """Recognize ownership and an ordinary native descriptor, without versions."""
    module = sys.modules.get(module_name)
    method = getattr(instance, name, None)
    function = getattr(method, "__func__", None)
    return bool(module is not None and inspect.ismethod(method)
        and method.__self__ is instance and inspect.isfunction(function)
        and function.__module__ == module_name and function.__globals__ is vars(module)
        and not hasattr(function, "__wrapped__")
        and type(instance).__dict__.get(name) is function)


def _metadata_context(registration: Any) -> tuple[Any, Any, Any, Any, Any, tuple] | None:
    """Read the one exact retained HMB canvas. Unknown inventories stay native."""
    from griptape_nodes.retained_mode.engine import current_engine
    from griptape_nodes.retained_mode.managers.context_manager import ContextManager
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_types import TrackedParameterOutputValues
    from griptape_nodes.node_library.library_registry import LibraryRegistry
    engine, manager = registration.engine(), registration.manager()
    if (not registration.active or not registration.owners or engine is None or manager is None
            or current_engine() is not engine or engine.event_manager is not manager
            or engine.library_manager.is_worker is not False
            or any(reference() is not None for reference in registration.load_requests.values())
            or registration.snapshot_requests):
        return None
    context, registry = engine.context_manager, engine.workflow_registry
    if type(context) is not ContextManager:
        return None
    for name in ("get_current_workflow_name", "get_current_workflow_file_path", "get_current_flow"):
        if not _native_bound_method(context, name, ContextManager.__module__):
            return None
    registry_module = "griptape_nodes.node_library.workflow_registry"
    native_registry = vars(sys.modules.get(registry_module)).get("_WorkflowRegistry")
    if type(registry) is not native_registry:
        return None
    for name in ("ensure_unsaved", "get_workflow_by_name", "has_workflow_with_name", "delete_workflow_by_name"):
        if not _native_bound_method(registry, name, registry_module):
            return None
    stack = getattr(context, "_workflow_stack", None)
    if type(stack) is not list or len(stack) != 1:
        return None
    record = stack[0]
    if (type(record) is not ContextManager.WorkflowContextState
            or type(record).__setattr__ is not object.__setattr__
            or vars(record).get("_file_path") is not None
            or context.get_current_workflow_file_path() is not None
            or type(vars(record).get("_name")) is not str
            or context.get_current_workflow_name() != vars(record)["_name"]
            or not {"_name", "_file_path", "_working_directory", "_flow_stack"} <= vars(record).keys()
            or type(record._flow_stack) is not list or len(record._flow_stack) != 1
            or context.has_current_node()):
        return None
    flow = context.get_current_flow()
    if type(flow) is not ControlFlow or bool(getattr(flow, "_hmb_flow_deleted", False)):
        return None
    parents = getattr(engine.flow_manager, "_name_to_parent_name", None)
    node_parents = getattr(engine.node_manager, "_name_to_parent_flow_name", None)
    objects = getattr(engine.object_manager, "_name_to_objects", None)
    nodes = getattr(flow, "nodes", None)
    if (type(parents) is not dict or parents != {flow.name: None}
            or type(node_parents) is not dict or type(objects) is not dict
            or type(nodes) is not dict or not nodes
            or set(objects) != {flow.name, *nodes}
            or node_parents != {name: flow.name for name in nodes}
            or objects.get(flow.name) is not flow
            or engine.flow_manager.get_flow_by_name(flow.name) is not flow):
        return None
    hmb_owned = False
    for name, node in nodes.items():
        if (getattr(node, "name", None) != name or objects.get(name) is not node
                or engine.node_manager.get_node_by_name(name) is not node
                or bool(getattr(node, "_hmb_node_deleted", False))):
            return None
        metadata = getattr(node, "metadata", None)
        if isinstance(metadata, dict) and metadata.get("library") == "HMB_GP_Production":
            library = LibraryRegistry.get_library_for_node_type(metadata.get("node_type"), "HMB_GP_Production")
            if (not any(reference() is library for reference in registration.owners.values())
                    or library.get_node_class(metadata.get("node_type")) is not type(node)):
                return None
            hmb_owned = True
    flags = getattr(engine.workflow_manager.variable_substitution, "_enabled", None)
    if not hmb_owned or type(flags) is not dict or any(type(value) is not bool for value in flags.values()):
        return None
    substitution = engine.workflow_manager.variable_substitution
    if not _native_bound_method(substitution, "rekey", "griptape_nodes.retained_mode.managers.workflow.variable_substitution"):
        return None
    connections = engine.flow_manager.get_connections().connections
    if type(connections) is not dict:
        return None
    edge_signature = []
    value_signature = []
    for node in nodes.values():
        for attribute in ("parameter_values", "parameter_output_values"):
            values = getattr(node, attribute, None)
            if type(values) not in (dict, TrackedParameterOutputValues):
                return None
            value_signature.append((node.name, attribute, id(values),
                tuple(sorted((key, id(value)) for key, value in values.items()))))
    for edge in connections.values():
        if (nodes.get(edge.source_node.name) is not edge.source_node
                or nodes.get(edge.target_node.name) is not edge.target_node):
            return None
        edge_signature.append((id(edge), id(edge.source_node), id(edge.source_parameter),
            id(edge.target_node), id(edge.target_parameter)))
    signature = (id(record), id(record._flow_stack), id(record._flow_stack[0]), id(flow),
        tuple(sorted((name, id(node)) for name, node in nodes.items())),
        tuple(sorted(parents.items())), tuple(sorted(node_parents.items())),
        tuple(sorted((name, id(value)) for name, value in objects.items())),
        tuple(sorted(edge_signature)), tuple(sorted(value_signature)))
    return engine, context, record, flow, registry, signature


def recover_workflow_metadata(registration: Any, request: Any) -> Any:
    """Lease the original legacy metadata request to an honest native scratch key.

    Only the current pathless, unregistered literal ``workflow`` HMB canvas is
    eligible. Its existing context/flow/node objects are retained. The native
    metadata handler builds the response; no saved metadata/history is invented.
    """
    try:
        from griptape_nodes.retained_mode.events.workflow_events import (
            GetWorkflowMetadataRequest, GetWorkflowMetadataResultSuccess,
        )
        if type(request) is not GetWorkflowMetadataRequest or request.workflow_name != "workflow":
            return None
        with registration.lock:
            state = _metadata_context(registration)
            if state is None:
                registration._hmb_legacy_metadata_lease = None
                return None
            engine, context, record, flow, registry, signature = state
            lease = getattr(registration, "_hmb_legacy_metadata_lease", None)
            name = context.get_current_workflow_name()
            if lease is not None:
                if (lease["context"]() is not record or lease["flow"]() is not flow
                        or name != lease["key"] or registry.has_workflow_with_name("workflow")
                        or not registry.has_workflow_with_name(name)
                        or registry.get_workflow_by_name(name) is not lease["workflow"]()
                        or registry.get_workflow_by_name(name).is_saved is not False):
                    registration._hmb_legacy_metadata_lease = None
                    return None
                translated = GetWorkflowMetadataRequest(workflow_name=name, broadcast_result=False)
                result = engine.handle_request(translated)
                return result if type(result) is GetWorkflowMetadataResultSuccess else None
            if name != "workflow" or registry.has_workflow_with_name(name):
                return None
            key = "unsaved:" + str(uuid4())
            flags = engine.workflow_manager.variable_substitution._enabled
            old_flag = (name in flags, flags.get(name))
            created = None
            try:
                if registry.has_workflow_with_name(key):
                    return None
                created = registry.ensure_unsaved(key, display_name="workflow")
                if (registry.get_workflow_by_name(key) is not created or created.is_saved is not False
                        or created.file_path is not None or _metadata_context(registration)[-1] != signature):
                    raise RuntimeError("The retained workflow changed during metadata recovery")
                engine.workflow_manager.variable_substitution.rekey(name, key)
                record._name = key
                translated = GetWorkflowMetadataRequest(workflow_name=key, broadcast_result=False)
                result = engine.handle_request(translated)
                current = _metadata_context(registration)
                if (type(result) is not GetWorkflowMetadataResultSuccess or current is None
                        or current[-1] != signature or context.get_current_workflow_name() != key
                        or registry.get_workflow_by_name(key) is not created):
                    raise RuntimeError("Native metadata recovery did not retain the exact canvas")
                registration._hmb_legacy_metadata_lease = {"key": key, "context": weakref.ref(record),
                    "flow": weakref.ref(flow), "workflow": weakref.ref(created)}
                return result
            except Exception:
                # Roll back only this transaction's fresh key/flag/name. Never
                # clear a graph, overwrite another registry entry or touch a file.
                if context._workflow_stack == [record] and record._name == key:
                    record._name = name
                if old_flag[0] and name not in flags:
                    flags[name] = old_flag[1]
                if key in flags and flags[key] == old_flag[1]:
                    flags.pop(key, None)
                if created is not None and registry.has_workflow_with_name(key) and registry.get_workflow_by_name(key) is created:
                    registry.delete_workflow_by_name(key)
                return None
    except Exception:
        # Unsupported or foreign SDK seams preserve the original typed error.
        return None
