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
