"""Isolated regressions for retiring one registered ImageAsset import.

All retained-mode requests use the in-memory fake below. No desktop engine,
project manifest, source media, or network share is modified by this suite.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import hashlib
from pathlib import Path
import sys
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_image_asset_import_child_cleanup_regression", ROOT / "HMBImageAssetLibrary.py"
)
assert SPEC is not None and SPEC.loader is not None
library = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = library
SPEC.loader.exec_module(library)
IMPORT = library.IMAGE_IMPORT_PARAMETER


class Payload(SimpleNamespace):
    pass


class ListConnectionsForNodeRequest(Payload):
    pass


class ListConnectionsForNodeResultSuccess(Payload):
    pass


class DeleteConnectionRequest(Payload):
    pass


class DeleteConnectionResultSuccess(Payload):
    pass


class DeleteConnectionResultFailure(Payload):
    pass


class RemoveParameterFromNodeRequest(Payload):
    pass


class RemoveParameterFromNodeResultSuccess(Payload):
    pass


class RemoveParameterFromNodeResultFailure(Payload):
    pass


class Child(SimpleNamespace):
    def __init__(self, key: str, parent: str = IMPORT):
        super().__init__(
            name=f"{parent}_ParameterListUniqueParamID_{key}",
            parent_container_name=parent,
            user_defined=True,
            default_value=[],
            element_id=f"element_{key}",
        )


class ImportList(SimpleNamespace):
    def __init__(self, children: list[Child]):
        super().__init__(name=IMPORT, children=children, user_defined=False)

    def get_child_parameters(self):
        return list(self.children)


class Target:
    _expand_widget_edit = library.HMBImageAssetLibrary._expand_widget_edit
    def __init__(self):
        self.name = "isolated_image_asset_target"
        self.lock = False
        self.children = [Child(key) for key in ("a", "b", "c")]
        self.parent = ImportList(self.children)
        self.parameters = {IMPORT: self.parent, **{p.name: p for p in self.children}}
        self.images = [f"https://example.test/cleanup-{key}.png" for key in "abc"]
        self.parameter_values = dict(zip((p.name for p in self.children), self.images))
        self.state = {
            "assets": [{"source_uid": "project:registered-b", "registered": True}],
            "shot_routing": [{"selected_source_uids": ["project:registered-b"]}],
        }
        self.applied_values = []
        self.raise_for_missing_parameter = False

    def get_parameter_by_name(self, name):
        if self.raise_for_missing_parameter and name not in self.parameters:
            raise ValueError(f"Parameter '{name}' does not exist")
        return self.parameters.get(name)

    def get_parameter_value(self, name):
        if name == IMPORT:
            return [self.parameter_values.get(child.name, []) for child in self.children]
        return self.parameter_values.get(name)

    def _current_state(self):
        return deepcopy(self.state)

    def _apply_import_value(self, value):
        self.applied_values.append(deepcopy(value))
        return self._current_state()

    def _scan_owner_is_current(self):
        return True


class FakeEventLoop:
    def __init__(self):
        self.pending = []

    def is_running(self):
        return True

    def is_closed(self):
        return False

    def call_soon_threadsafe(self, callback, *args):
        self.pending.append((callback, args))

    def drain(self):
        while self.pending:
            callback, args = self.pending.pop(0)
            callback(*args)


class FakeEventManager:
    """The SDK's public dispatch hooks, without importing a live engine."""

    def __init__(self, loop):
        self.event_loop = loop
        self.pre_hooks = []
        self.post_hooks = {}

    def add_pre_dispatch_hook(self, callback):
        if callback not in self.pre_hooks:
            self.pre_hooks.append(callback)

    def remove_pre_dispatch_hook(self, callback):
        if callback in self.pre_hooks:
            self.pre_hooks.remove(callback)

    def add_post_dispatch_hook(self, event_type, callback):
        callbacks = self.post_hooks.setdefault(event_type, [])
        if callback not in callbacks:
            callbacks.append(callback)

    def remove_post_dispatch_hook(self, event_type, callback):
        callbacks = self.post_hooks.get(event_type, [])
        if callback in callbacks:
            callbacks.remove(callback)


class FakeRetainedHost:
    def __init__(self, target):
        self.target = target
        self.nodes = {
            f"source_{key}": SimpleNamespace(parameter_output_values={"IMAGE_OUT": image})
            for key, image in zip("abc", target.images)
        }
        self.nodes[target.name] = target
        self.incoming = [
            Payload(
                source_node_name=f"source_{key}",
                source_parameter_name="IMAGE_OUT",
                target_parameter_name=child.name,
            )
            for key, child in zip("abc", target.children)
        ]
        self.outgoing = []
        self.events = []
        self.delete_failure = False
        self.delete_noop = False
        self.remove_failure = False
        self.delete_cleanup_flags = []
        self.invoke_removal_hook = False
        self.loop = FakeEventLoop()
        self.event_manager = FakeEventManager(self.loop)
        self.dispatch_requests = []
        self.dispatch_results = []
        self.drain_during_native_remove = False
        self.defer_post_hooks = False
        self.pending_post_hooks = []
        self.supports_dispatch_hooks = True
        self.legacy_event_manager = SimpleNamespace(event_loop=self.loop)
        self.before_delete = None
        self.after_list = None
        self.before_remove = None
        self.remove_results = []

    def forget_child(self, name):
        """Finish an already-owned native deletion without another request."""
        self.target.children[:] = [p for p in self.target.children if p.name != name]
        self.target.parameters.pop(name, None)
        self.target.parameter_values.pop(name, None)

    def get_node_by_name(self, name):
        return self.nodes[name]

    def handle_request(self, request):
        self.dispatch_requests.append(request)
        result = None
        for callback in list(self.event_manager.pre_hooks):
            result = callback(request, SimpleNamespace())
            if result is not None:
                break
        if result is None:
            result = self._handle_request_impl(request)
        self.dispatch_results.append((request, result))
        for callback in list(self.event_manager.post_hooks.get(type(request), [])):
            if self.defer_post_hooks:
                self.pending_post_hooks.append((callback, request, result))
            else:
                callback(request, result)
        return result

    def drain_post_hooks(self, *, reverse=False):
        while self.pending_post_hooks:
            index = -1 if reverse else 0
            callback, request, result = self.pending_post_hooks.pop(index)
            callback(request, result)

    def _handle_request_impl(self, request):
        if isinstance(request, ListConnectionsForNodeRequest):
            self.events.append(("list", request.node_name))
            result = ListConnectionsForNodeResultSuccess(
                incoming_connections=list(self.incoming), outgoing_connections=list(self.outgoing)
            )
            if self.after_list is not None:
                callback, self.after_list = self.after_list, None
                callback()
            return result
        if isinstance(request, DeleteConnectionRequest):
            self.events.append(("delete", request.target_parameter_name))
            self.delete_cleanup_flags.append(bool(getattr(self.target, "_hmb_import_cleanup_active", False)))
            if self.before_delete is not None:
                callback, self.before_delete = self.before_delete, None
                callback()
            if self.delete_failure:
                return DeleteConnectionResultFailure(result_details="injected delete failure")
            if not self.delete_noop:
                self.incoming = [
                    edge for edge in self.incoming
                    if not (
                        edge.source_node_name == request.source_node_name
                        and edge.source_parameter_name == request.source_parameter_name
                        and edge.target_parameter_name == request.target_parameter_name
                    )
                ]
                # Installed INPUT-only ParameterList children reset to default []
                # on wire deletion, while the child object remains in the list.
                self.target.parameter_values[request.target_parameter_name] = []
                if self.invoke_removal_hook:
                    library.HMBImageAssetLibrary.after_incoming_connection_removed(
                        self.target,
                        self.nodes[request.source_node_name],
                        Payload(name=request.source_parameter_name),
                        self.target.get_parameter_by_name(request.target_parameter_name),
                    )
            return DeleteConnectionResultSuccess()
        if isinstance(request, RemoveParameterFromNodeRequest):
            if request.node_name != self.target.name:
                return RemoveParameterFromNodeResultFailure(result_details="Unknown native node")
            self.events.append(("remove", request.parameter_name))
            if self.before_remove is not None:
                callback, self.before_remove = self.before_remove, None
                callback()
            if self.remove_failure:
                result = RemoveParameterFromNodeResultFailure(result_details="injected remove failure")
                self.remove_results.append(result)
                return result
            if request.parameter_name not in self.target.parameters:
                result = RemoveParameterFromNodeResultFailure(
                    result_details=f"Parameter '{request.parameter_name}' does not exist"
                )
                self.remove_results.append(result)
                return result
            if not self.target.parameters[request.parameter_name].user_defined:
                result = RemoveParameterFromNodeResultFailure(
                    result_details="Native host cannot remove a built-in parameter"
                )
                self.remove_results.append(result)
                return result
            # The actual SDK removes matching wires first, emitting the node's
            # disconnection callback, and only then removes the captured child.
            for edge in list(self.incoming):
                if edge.target_parameter_name == request.parameter_name:
                    result = self.handle_request(DeleteConnectionRequest(
                        source_node_name=edge.source_node_name,
                        source_parameter_name=edge.source_parameter_name,
                        target_node_name=self.target.name,
                        target_parameter_name=edge.target_parameter_name,
                    ))
                    if not isinstance(result, DeleteConnectionResultSuccess):
                        failure = RemoveParameterFromNodeResultFailure(
                            result_details="native nested connection deletion failed"
                        )
                        self.remove_results.append(failure)
                        return failure
            assert not any(e.source_parameter_name == request.parameter_name for e in self.outgoing)
            if self.drain_during_native_remove:
                self.loop.drain()
            if request.parameter_name not in self.target.parameters:
                result = RemoveParameterFromNodeResultFailure(
                    result_details="Native child removal lost its captured element to a nested removal"
                )
                self.remove_results.append(result)
                return result
            self.forget_child(request.parameter_name)
            result = RemoveParameterFromNodeResultSuccess()
            self.remove_results.append(result)
            return result
        raise AssertionError(f"Unexpected retained request: {request!r}")

    @contextmanager
    def installed(self, *, observe_native_removals=True):
        names = (
            "griptape_nodes",
            "griptape_nodes.retained_mode",
            "griptape_nodes.retained_mode.events",
            "griptape_nodes.retained_mode.events.connection_events",
            "griptape_nodes.retained_mode.events.parameter_events",
            "griptape_nodes.retained_mode.griptape_nodes",
        )
        modules = {name: ModuleType(name) for name in names}
        for name in names[:3]:
            modules[name].__path__ = []
        connection_module = modules[names[3]]
        parameter_module = modules[names[4]]
        for cls in (
            ListConnectionsForNodeRequest, ListConnectionsForNodeResultSuccess,
            DeleteConnectionRequest, DeleteConnectionResultSuccess, DeleteConnectionResultFailure,
        ):
            setattr(connection_module, cls.__name__, cls)
        for cls in (
            RemoveParameterFromNodeRequest, RemoveParameterFromNodeResultSuccess,
            RemoveParameterFromNodeResultFailure,
        ):
            setattr(parameter_module, cls.__name__, cls)
        modules[names[5]].GriptapeNodes = SimpleNamespace(
            handle_request=self.handle_request,
            NodeManager=lambda: self,
            EventManager=lambda: (
                self.event_manager if self.supports_dispatch_hooks else self.legacy_event_manager
            ),
        )
        with patch.dict(sys.modules, modules), patch.object(library, "ParameterList", ImportList):
            if observe_native_removals:
                ensure_observers = getattr(library, "_ensure_import_child_removal_observers", None)
                if callable(ensure_observers):
                    ensure_observers(self.target)
            yield self


def imported_uid(value):
    rows, _ = library._normalize_import_input(value, [])
    assert len(rows) == 1, rows
    return rows[0]["source_uid"]


class ImportChildCleanupRegression(unittest.TestCase):
    def setUp(self):
        self.target = Target()
        self.host = FakeRetainedHost(self.target)
        self.names = [child.name for child in self.target.children]
        self.state = deepcopy(self.target.state)
        self.uid = imported_uid(self.target.images[1])

    def retire(self):
        return library._retire_registered_import_connection(self.target, self.uid)

    def remove(self, name):
        return library._remove_import_child_parameter(self.target, name)

    def mutations(self):
        return [event for event in self.host.events if event[0] != "list"]

    def assert_survivors(self):
        self.assertEqual([p.name for p in self.target.children], [self.names[0], self.names[2]])
        self.assertEqual(
            [(e.source_node_name, e.target_parameter_name) for e in self.host.incoming],
            [("source_a", self.names[0]), ("source_c", self.names[2])],
        )
        self.assertEqual(self.target.state, self.state)

    def test_retire_middle_child_preserves_remaining_ids_and_registered_selection(self):
        with self.host.installed():
            self.retire()
        self.assert_survivors()
        self.assertEqual(self.mutations(), [("delete", self.names[1]), ("remove", self.names[1])])
        self.assertEqual(self.host.delete_cleanup_flags, [True])
        self.assertFalse(getattr(self.target, "_hmb_import_cleanup_active", False))
        delete_index = self.host.events.index(("delete", self.names[1]))
        remove_index = self.host.events.index(("remove", self.names[1]))
        self.assertTrue(any(event[0] == "list" for event in self.host.events[delete_index+1:remove_index]))

    def test_manual_disconnect_removes_only_its_exact_empty_child(self):
        self.host.incoming.pop(1)
        self.target.parameter_values[self.names[1]] = []
        with self.host.installed():
            self.remove(self.names[1])
        self.assert_survivors()
        self.assertEqual(self.mutations(), [("remove", self.names[1])])

    def test_manual_disconnect_callback_compacts_exact_empty_child(self):
        child = self.target.children[1]
        self.host.incoming.pop(1)
        self.target.parameter_values[child.name] = []
        with self.host.installed():
            library.HMBImageAssetLibrary.after_incoming_connection_removed(
                self.target, self.host.nodes["source_b"], Payload(name="IMAGE_OUT"), child
            )
            self.assertEqual(self.mutations(), [])
            self.assertEqual(len(self.host.loop.pending), 1)
            self.host.loop.drain()
        self.assert_survivors()
        self.assertEqual(self.mutations(), [("remove", child.name)])
        self.assertEqual(
            library._flatten_import_values(self.target.applied_values[-1]),
            [self.target.images[0], self.target.images[2]],
        )

    def test_retire_with_host_callback_removes_child_once(self):
        self.host.invoke_removal_hook = True
        with self.host.installed():
            self.retire()
            self.host.loop.drain()
        self.assert_survivors()
        self.assertEqual(self.mutations(), [("delete", self.names[1]), ("remove", self.names[1])])

    def test_native_minus_removal_finishes_before_deferred_cleanup(self):
        child = self.target.children[1]
        self.host.incoming.pop(1)
        self.target.parameter_values[child.name] = []
        with self.host.installed():
            library.HMBImageAssetLibrary.after_incoming_connection_removed(
                self.target, self.host.nodes["source_b"], Payload(name="IMAGE_OUT"), child
            )
            self.assertEqual(self.mutations(), [])
            # The native request removes its own child before the next loop turn.
            self.target.children.remove(child)
            self.target.parameters.pop(child.name)
            self.host.loop.drain()
        self.assertEqual(self.mutations(), [])
        self.assert_survivors()

    def test_already_removed_child_is_an_idempotent_noop(self):
        self.host.incoming.pop(1)
        self.target.children.pop(1)
        self.target.parameters.pop(self.names[1])
        with self.host.installed():
            self.assertFalse(self.remove(self.names[1]))
        self.assertEqual(self.mutations(), [])

    def test_missing_child_sdk_lookup_failure_is_an_idempotent_noop(self):
        self.target.raise_for_missing_parameter = True
        self.host.incoming.pop(1)
        self.host.forget_child(self.names[1])
        with self.host.installed():
            self.assertFalse(self.remove(self.names[1]))
            self.assertFalse(self.remove(self.names[1]))
        self.assertEqual(self.mutations(), [])
        self.assert_survivors()

    def test_duplicate_disconnect_callbacks_remove_exact_child_once(self):
        child = self.target.children[1]
        self.host.incoming.pop(1)
        self.target.parameter_values[child.name] = []
        with self.host.installed():
            for _ in range(2):
                library.HMBImageAssetLibrary.after_incoming_connection_removed(
                    self.target, self.host.nodes["source_b"], Payload(name="IMAGE_OUT"), child
                )
            self.host.loop.drain()
        self.assertEqual(self.mutations(), [("remove", child.name)])
        self.assertEqual(len(self.host.remove_results), 1)
        self.assertIsInstance(self.host.remove_results[0], RemoveParameterFromNodeResultSuccess)
        self.assert_survivors()

    def test_deferred_cleanup_preserves_reconnected_child_and_latest_media(self):
        child = self.target.children[1]
        old_edge = self.host.incoming.pop(1)
        self.target.parameter_values[child.name] = []
        with self.host.installed(), patch.object(library, "_diagnostic_warning"):
            library.HMBImageAssetLibrary.after_incoming_connection_removed(
                self.target, self.host.nodes["source_b"], Payload(name="IMAGE_OUT"), child
            )
            self.host.incoming.insert(1, old_edge)
            new_image = "https://example.test/reconnected-image.png"
            self.target.parameter_values[child.name] = new_image
            self.host.nodes["source_b"].parameter_output_values["IMAGE_OUT"] = new_image
            self.host.loop.drain()
        self.assertEqual(self.mutations(), [])
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertEqual(self.target.parameter_values[child.name], new_image)
        self.assertEqual(self.target.state, self.state)

    def test_deferred_cleanup_does_not_mutate_a_stale_node_owner(self):
        child = self.target.children[1]
        self.host.incoming.pop(1)
        self.target.parameter_values[child.name] = []
        with self.host.installed():
            library.HMBImageAssetLibrary.after_incoming_connection_removed(
                self.target, self.host.nodes["source_b"], Payload(name="IMAGE_OUT"), child
            )
            self.target._scan_owner_is_current = lambda: False
            self.host.loop.drain()
        self.assertEqual(self.mutations(), [])
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertEqual(self.target.state, self.state)

    def test_native_deletion_wins_before_empty_child_remove_request(self):
        self.host.incoming.pop(1)
        self.target.parameter_values[self.names[1]] = []
        self.host.before_remove = lambda: self.host.forget_child(self.names[1])
        with self.host.installed():
            self.assertFalse(self.remove(self.names[1]))
        self.assertEqual(self.mutations(), [("remove", self.names[1])])
        self.assertIsInstance(self.host.remove_results[0], RemoveParameterFromNodeResultFailure)
        self.assert_survivors()

    def test_native_remove_during_nested_disconnect_never_reenters_child_deletion(self):
        self.host.invoke_removal_hook = True
        self.host.drain_during_native_remove = True
        with self.host.installed():
            result = self.host.handle_request(RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            ))
            self.host.loop.drain()
        self.assertIsInstance(result, RemoveParameterFromNodeResultSuccess)
        self.assertEqual(self.mutations(), [("remove", self.names[1]), ("delete", self.names[1])])
        self.assertEqual(len(self.host.remove_results), 1)
        self.assertEqual(self.host.loop.pending, [])
        self.assert_survivors()

    def test_successful_native_removal_makes_late_duplicate_requests_noops(self):
        self.host.invoke_removal_hook = True
        with self.host.installed():
            request = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            )
            self.assertIsInstance(self.host.handle_request(request), RemoveParameterFromNodeResultSuccess)
            self.host.loop.drain()
            for _ in range(2):
                self.assertIsInstance(self.host.handle_request(request), RemoveParameterFromNodeResultSuccess)
        self.assertEqual(self.mutations(), [("remove", self.names[1]), ("delete", self.names[1])])
        self.assertEqual(len(self.host.remove_results), 1)
        self.assert_survivors()

    def test_successful_owned_cleanup_makes_late_duplicate_request_a_noop(self):
        with self.host.installed():
            self.retire()
            result = self.host.handle_request(RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            ))
        self.assertIsInstance(result, RemoveParameterFromNodeResultSuccess)
        self.assertEqual(self.mutations(), [("delete", self.names[1]), ("remove", self.names[1])])
        self.assertEqual(len(self.host.remove_results), 1)
        self.assert_survivors()

    def test_unknown_child_and_aggregate_native_failures_are_not_intercepted(self):
        with self.host.installed():
            for name in (f"{IMPORT}_ParameterListUniqueParamID_never_seen", IMPORT):
                self.assertIsInstance(self.host.handle_request(RemoveParameterFromNodeRequest(
                    node_name=self.target.name, parameter_name=name
                )), RemoveParameterFromNodeResultFailure)
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertIs(self.target.parameters[IMPORT], self.target.parent)
        self.assertEqual(self.target.state, self.state)

    def test_foreign_child_removal_does_not_authorize_its_late_duplicate(self):
        foreign = Child("foreign", parent="OTHER_INPUT")
        self.target.parameters[foreign.name] = foreign
        with self.host.installed():
            request = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=foreign.name
            )
            self.assertIsInstance(self.host.handle_request(request), RemoveParameterFromNodeResultSuccess)
            self.assertIsInstance(self.host.handle_request(request), RemoveParameterFromNodeResultFailure)
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertEqual(self.target.state, self.state)

    def test_native_result_before_delayed_post_still_protects_late_duplicate(self):
        self.host.invoke_removal_hook = True
        self.host.defer_post_hooks = True
        with self.host.installed():
            first = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            )
            self.assertIsInstance(self.host.handle_request(first), RemoveParameterFromNodeResultSuccess)
            state = self.target._hmb_import_child_removal_state
            self.assertIn(id(first), state["active"])
            self.assertNotIn(self.names[1], state["retired"])
            duplicate = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            )
            self.assertIsInstance(self.host.handle_request(duplicate), RemoveParameterFromNodeResultSuccess)
            self.host.drain_post_hooks(reverse=True)
            self.host.loop.drain()
        self.assertEqual(state["active"], {})
        self.assertIn(self.names[1], state["retired"])
        self.assertEqual(self.mutations(), [("remove", self.names[1]), ("delete", self.names[1])])
        self.assertEqual(len(self.host.remove_results), 1)
        self.assert_survivors()

    def test_out_of_order_posts_release_only_their_matching_native_request(self):
        self.host.invoke_removal_hook = True
        self.host.defer_post_hooks = True
        with self.host.installed():
            first = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            )
            second = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[2]
            )
            self.assertIsInstance(self.host.handle_request(first), RemoveParameterFromNodeResultSuccess)
            self.assertIsInstance(self.host.handle_request(second), RemoveParameterFromNodeResultSuccess)
            state = self.target._hmb_import_child_removal_state
            self.assertEqual(set(state["active"]), {id(first), id(second)})
            callback, request, result = self.host.pending_post_hooks.pop()
            callback(request, result)
            self.assertEqual(set(state["active"]), {id(first)})
            self.assertIn(self.names[2], state["retired"])
            self.assertNotIn(self.names[1], state["retired"])
            for name in (self.names[1], self.names[2]):
                self.assertIsInstance(self.host.handle_request(RemoveParameterFromNodeRequest(
                    node_name=self.target.name, parameter_name=name
                )), RemoveParameterFromNodeResultSuccess)
            self.host.drain_post_hooks(reverse=True)
            self.host.loop.drain()
        self.assertEqual(state["active"], {})
        self.assertEqual(set(state["retired"]), {self.names[1], self.names[2]})
        self.assertEqual(len(self.host.remove_results), 2)
        self.assertEqual([p.name for p in self.target.children], [self.names[0]])
        self.assertEqual([e.source_node_name for e in self.host.incoming], ["source_a"])
        self.assertEqual(self.target.state, self.state)

    def test_reused_child_uuid_cannot_inherit_an_old_success_after_new_failure(self):
        with self.host.installed():
            old_request = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            )
            self.assertIsInstance(self.host.handle_request(old_request), RemoveParameterFromNodeResultSuccess)
            state = self.target._hmb_import_child_removal_state
            self.assertIn(self.names[1], state["retired"])
            replacement = Child("b")
            self.target.children.insert(1, replacement)
            self.target.parameters[replacement.name] = replacement
            self.target.parameter_values[replacement.name] = []
            # The new generation disappears before its native request resolves;
            # that request reports failure, not a successful removal proof.
            self.host.before_remove = lambda: self.host.forget_child(replacement.name)
            failed_request = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=replacement.name
            )
            self.assertIsInstance(self.host.handle_request(failed_request), RemoveParameterFromNodeResultFailure)
            self.assertEqual(state["active"], {})
            self.assertNotIn(replacement.name, state["retired"])
            self.assertIsInstance(self.host.handle_request(RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=replacement.name
            )), RemoveParameterFromNodeResultFailure)
        self.assertEqual(len(self.host.remove_results), 3)
        self.assert_survivors()

    def test_old_success_post_cannot_retire_a_new_failed_child_generation(self):
        self.host.defer_post_hooks = True
        with self.host.installed():
            old_request = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            )
            self.assertIsInstance(self.host.handle_request(old_request), RemoveParameterFromNodeResultSuccess)
            state = self.target._hmb_import_child_removal_state
            replacement = Child("b")
            self.target.children.insert(1, replacement)
            self.target.parameters[replacement.name] = replacement
            self.target.parameter_values[replacement.name] = []
            self.host.before_remove = lambda: self.host.forget_child(replacement.name)
            failed_request = RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=replacement.name
            )
            self.assertIsInstance(self.host.handle_request(failed_request), RemoveParameterFromNodeResultFailure)
            # Resolve the new failure first while the old success post is still
            # detached. Its old active token cannot authorize the new UUID use.
            callback, request, result = self.host.pending_post_hooks.pop()
            self.assertIs(request, failed_request)
            callback(request, result)
            self.assertEqual(set(state["active"]), {id(old_request)})
            self.assertIsInstance(self.host.handle_request(RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=replacement.name
            )), RemoveParameterFromNodeResultFailure)
            self.host.drain_post_hooks(reverse=True)
            self.assertEqual(state["active"], {})
            self.assertNotIn(replacement.name, state["retired"])
            self.assertIsInstance(self.host.handle_request(RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=replacement.name
            )), RemoveParameterFromNodeResultFailure)
            self.host.drain_post_hooks()
        self.assertEqual(len(self.host.remove_results), 4)
        self.assert_survivors()

    def test_child_replaced_during_connection_snapshot_is_preserved(self):
        self.host.incoming.pop(1)
        self.target.parameter_values[self.names[1]] = []
        replacement = Child("b")

        def replace_child():
            self.target.children[1] = replacement
            self.target.parameters[replacement.name] = replacement
            self.target.parameter_values[replacement.name] = "https://example.test/newer-local-child.png"

        self.host.after_list = replace_child
        with self.host.installed():
            self.assertFalse(self.remove(self.names[1]))
        self.assertEqual(self.mutations(), [])
        self.assertIs(self.target.children[1], replacement)
        self.assertEqual(self.target.parameter_values[replacement.name], "https://example.test/newer-local-child.png")
        self.assertEqual(self.target.state, self.state)

    def test_older_sdk_without_dispatch_hooks_keeps_native_removal_safe(self):
        self.host.supports_dispatch_hooks = False
        self.host.invoke_removal_hook = True
        self.host.drain_during_native_remove = True
        with self.host.installed():
            result = self.host.handle_request(RemoveParameterFromNodeRequest(
                node_name=self.target.name, parameter_name=self.names[1]
            ))
            self.host.loop.drain()
        self.assertIsInstance(result, RemoveParameterFromNodeResultSuccess)
        self.assertEqual(self.host.loop.pending, [])
        self.assertEqual(self.mutations(), [("remove", self.names[1]), ("delete", self.names[1])])
        self.assertEqual(len(self.host.remove_results), 1)
        self.assert_survivors()

    def test_older_sdk_keeps_explicit_registered_import_cleanup(self):
        self.host.supports_dispatch_hooks = False
        self.host.invoke_removal_hook = True
        with self.host.installed():
            self.retire()
            self.host.loop.drain()
        self.assertEqual(self.mutations(), [("delete", self.names[1]), ("remove", self.names[1])])
        self.assert_survivors()

    def test_observer_ensure_is_idempotent_and_finalizer_keeps_unrelated_hooks(self):
        sentinel_pre = lambda request, context: None
        sentinel_post = lambda request, result: None
        self.host.event_manager.add_pre_dispatch_hook(sentinel_pre)
        self.host.event_manager.add_post_dispatch_hook(RemoveParameterFromNodeRequest, sentinel_post)
        with self.host.installed():
            for _ in range(3):
                state = library._ensure_import_child_removal_observers(self.target)
            self.assertEqual(len(self.host.event_manager.pre_hooks), 2)
            self.assertEqual(len(self.host.event_manager.post_hooks[RemoveParameterFromNodeRequest]), 2)
            state["finalizer"]()
            # GC cleanup deliberately leaves the SDK dispatch-hook lock before
            # unregistering. Await that bounded worker, not a scheduling race.
            deadline = time.monotonic() + 2
            while (len(self.host.event_manager.pre_hooks) > 1
                    or len(self.host.event_manager.post_hooks[RemoveParameterFromNodeRequest]) > 1):
                self.assertLess(time.monotonic(), deadline, 'Deferred finalizer did not remove only its hooks')
                time.sleep(.001)
        self.assertEqual(self.host.event_manager.pre_hooks, [sentinel_pre])
        self.assertEqual(self.host.event_manager.post_hooks[RemoveParameterFromNodeRequest], [sentinel_post])
        self.assertEqual(self.mutations(), [])

    def test_connected_child_cannot_be_removed(self):
        with self.host.installed():
            try:
                self.remove(self.names[1])
            except RuntimeError:
                pass
        self.assertEqual(self.mutations(), [])
        self.assertEqual([p.name for p in self.target.children], self.names)

    def test_outgoing_connection_blocks_empty_child_removal(self):
        self.host.incoming.pop(1)
        self.target.parameter_values[self.names[1]] = []
        self.host.outgoing.append(Payload(source_parameter_name=self.names[1], target_node_name="other", target_parameter_name="input"))
        with self.host.installed():
            try:
                self.remove(self.names[1])
            except RuntimeError:
                pass
        self.assertEqual(self.mutations(), [])

    def test_nonempty_disconnected_child_is_preserved(self):
        self.host.incoming.pop(1)
        with self.host.installed():
            try:
                self.remove(self.names[1])
            except RuntimeError:
                pass
        self.assertEqual(self.mutations(), [])

    def test_root_and_foreign_child_are_never_removed(self):
        foreign = Child("foreign", parent="OTHER_INPUT")
        self.target.parameters[foreign.name] = foreign
        for name in (IMPORT, foreign.name):
            with self.host.installed():
                try:
                    self.remove(name)
                except RuntimeError:
                    pass
        self.assertEqual(self.mutations(), [])

    def test_delete_failure_preserves_graph_and_registered_state(self):
        self.host.delete_failure = True
        with self.host.installed(), self.assertRaises(RuntimeError):
            self.retire()
        self.assertEqual(self.mutations(), [("delete", self.names[1])])
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertEqual(self.target.parameter_values[self.names[1]], self.target.images[1])
        self.assertEqual(self.target.state, self.state)
        self.assertFalse(getattr(self.target, "_hmb_import_cleanup_active", False))

    def test_delete_success_with_surviving_edge_cannot_remove_child(self):
        self.host.delete_noop = True
        with self.host.installed():
            try:
                self.retire()
            except RuntimeError:
                pass
        self.assertEqual(self.mutations(), [("delete", self.names[1])])
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertEqual(self.target.state, self.state)

    def test_remove_failure_keeps_other_edges_and_registered_state(self):
        self.host.remove_failure = True
        with self.host.installed():
            try:
                self.retire()
            except RuntimeError:
                pass
        self.assertEqual(self.mutations(), [("delete", self.names[1]), ("remove", self.names[1])])
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertEqual([e.source_node_name for e in self.host.incoming], ["source_a", "source_c"])
        self.assertEqual(self.target.state, self.state)

    def test_compound_input_is_not_deleted_for_one_registered_card(self):
        self.host.nodes["source_b"].parameter_output_values["IMAGE_OUT"] = self.target.images[1:]
        with self.host.installed(), self.assertRaises(RuntimeError):
            self.retire()
        self.assertEqual(self.mutations(), [])

    def test_duplicate_source_uid_is_not_deleted_ambiguously(self):
        self.host.nodes["source_c"].parameter_output_values["IMAGE_OUT"] = self.target.images[1]
        with self.host.installed(), self.assertRaises(RuntimeError):
            self.retire()
        self.assertEqual(self.mutations(), [])

    def test_captured_exact_child_can_disambiguate_duplicate_source_uid(self):
        self.host.nodes["source_c"].parameter_output_values["IMAGE_OUT"] = self.target.images[1]
        with self.host.installed():
            library._retire_registered_import_connection(self.target, self.uid, self.names[1])
        self.assert_survivors()
        self.assertEqual(self.mutations(), [("delete", self.names[1]), ("remove", self.names[1])])

    def test_whole_list_edge_never_removes_root_parameter(self):
        self.host.incoming = [Payload(source_node_name="source_b", source_parameter_name="IMAGE_OUT", target_parameter_name=IMPORT)]
        self.target.parameter_values[IMPORT] = [self.target.images[1]]
        with self.host.installed():
            try:
                self.retire()
            except RuntimeError:
                pass
        self.assertEqual(self.mutations(), [])
        self.assertIn(IMPORT, self.target.parameters)


class SourceIdentityAvailabilityRegression(unittest.TestCase):
    def test_windows_and_unc_source_uid_survives_availability_change(self):
        references = (
            r"C:\ImageAssetRegression\source.png",
            r"\\example.test\ImageAssetRegression\source.png",
        )
        for reference in references:
            with self.subTest(reference=reference), patch.object(Path, "resolve", lambda path, *args, **kwargs: path), patch.object(library, "_asset_dimensions", return_value=(1, 1)), patch.object(library, "_asset_thumbnail_url", return_value=""), patch.object(library, "_import_payload_size", return_value=0):
                with patch.object(Path, "is_file", return_value=True):
                    available = imported_uid(reference)
                with patch.object(Path, "is_file", return_value=False):
                    unavailable = imported_uid(reference)
                self.assertEqual(available, unavailable)

    def test_asset_and_uppercase_https_uris_keep_exact_nonlocal_identity(self):
        for reference in ("asset://foo.png", "HTTPS://Example.test/CaseSensitive/Foo.PNG"):
            with self.subTest(reference=reference), patch.object(library, "_import_payload_size", return_value=0):
                rows, media = library._normalize_import_input(reference, [])
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["media_ref_kind"], "url")
                self.assertEqual(rows[0]["path"], reference)
                self.assertEqual(media[rows[0]["source_uid"]], reference)
                expected = "import:" + hashlib.sha256(f"url\n{reference}".encode()).hexdigest()[:24]
                self.assertEqual(rows[0]["source_uid"], expected)
                self.assertEqual(library._canonical_import_path(reference), "")

    def test_legacy_absent_path_uid_and_authored_fields_survive_migration(self):
        reference = r"C:\ImageAssetRegression\legacy-source.png"
        legacy_uid = "import:" + hashlib.sha256(f"url\n{reference}".encode()).hexdigest()[:24]
        previous = {
            "source_uid": legacy_uid, "asset_library_id": legacy_uid,
            "source_kind": "user", "path": reference, "media_ref_kind": "url",
            "selected": False, "selection_order": 0,
            "image_name": "Authored Legacy Name", "asset_id": "AuthoredLegacyID",
        }
        with patch.object(Path, "resolve", lambda path, *args, **kwargs: path), patch.object(library, "_import_payload_size", return_value=0), patch.object(library, "_asset_dimensions", return_value=(1, 1)), patch.object(library, "_asset_thumbnail_url", return_value=""):
            for available in (False, True):
                with self.subTest(available=available), patch.object(Path, "is_file", return_value=available):
                    rows, media = library._normalize_import_input(reference, [previous])
                self.assertEqual(rows[0]["source_uid"], legacy_uid)
                self.assertEqual(rows[0]["asset_library_id"], legacy_uid)
                self.assertFalse(rows[0]["selected"])
                self.assertEqual(rows[0]["image_name"], "Authored Legacy Name")
                self.assertEqual(rows[0]["asset_id"], "AuthoredLegacyID")
                self.assertEqual(rows[0]["media_ref_kind"], "path")
                self.assertEqual(set(media), {legacy_uid})

    def test_legacy_uid_matches_and_retires_exact_edge_with_previous_assets(self):
        target = Target()
        host = FakeRetainedHost(target)
        reference = r"C:\ImageAssetRegression\legacy-source.png"
        legacy_uid = "import:" + hashlib.sha256(f"url\n{reference}".encode()).hexdigest()[:24]
        previous = [{
            "source_uid": legacy_uid, "asset_library_id": legacy_uid,
            "source_kind": "user", "path": reference, "media_ref_kind": "url",
        }]
        host.nodes["source_b"].parameter_output_values["IMAGE_OUT"] = reference
        target.parameter_values[target.children[1].name] = reference
        target.state["assets"] = previous
        exact_name = target.children[1].name
        with host.installed(), patch.object(Path, "resolve", lambda path, *args, **kwargs: path), patch.object(Path, "is_file", return_value=False), patch.object(library, "_import_payload_size", return_value=0):
            match = library._single_import_connection_for_uid(
                host, host.incoming, legacy_uid, {exact_name}, previous
            )
            self.assertEqual(match.target_parameter_name, exact_name)
            captured = library._capture_import_registration_edges(target, legacy_uid)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][2], exact_name)
            library._retire_registered_import_connection(
                target, legacy_uid, exact_name, previous_assets=previous
            )
        self.assertEqual([event for event in host.events if event[0] != "list"], [("delete", exact_name), ("remove", exact_name)])
        self.assertEqual([edge.source_node_name for edge in host.incoming], ["source_a", "source_c"])


class RegistrationCompletionCleanupRegression(unittest.TestCase):
    """Exercise Add's real completion closure with a captured fake scheduler."""

    def setUp(self):
        self.target = Target()
        self.host = FakeRetainedHost(self.target)
        self.names = [child.name for child in self.target.children]
        self.uid = imported_uid(self.target.images[1])
        self.target.state, media = library._merge_import_input(
            library._default_state(), self.target.images
        )
        self.target._hmb_import_media_by_uid = media
        self.target._hmb_manifest_poll_received = False
        self.target._hmb_manifest_poll_pending = False
        self.target._scan_owner_is_current = lambda: True
        self.request = {
            "request_id": "isolated-registration-b",
            "project_uid": "isolated-project",
            "asset_library_id": self.uid,
            "source_kind": "user",
            "source_uid": self.uid,
            "target_folder": "Character",
            "image_name": "Registered B",
            "asset_id": "RegisteredB",
        }
        self.target.state["asset_registration_request"] = self.request
        self.scheduled = []

        def schedule(key, state, work, **kwargs):
            self.scheduled.append({"key": key, "state": state, "work": work, **kwargs})
            return state

        def publish(state):
            self.target.state = deepcopy(state)
            self.host.events.append(("publish", bool(state.get("asset_registration_result", {}).get("ok"))))
            return self.target.state

        self.target._schedule_catalog_scan = schedule
        self.target._publish_state = publish

    def begin(self):
        library.HMBImageAssetLibrary._apply_widget_state(self.target, self.target.state)
        self.assertEqual(len(self.scheduled), 1)
        self.assertTrue(callable(self.scheduled[0].get("on_published")))
        self.assertEqual(self.graph_mutations(), [])
        return self.scheduled[0]["on_published"]

    def completion_state(self, *, ok=True):
        state = deepcopy(self.target.state)
        state["asset_registration_request"] = {}
        state["asset_registration_result"] = {
            "request_id": self.request["request_id"],
            "ok": ok,
            "asset_library_id": "registered-b",
            "message": "registered" if ok else "injected registration failure",
        }
        if ok:
            state["assets"].append({
                "asset_library_id": "registered-b",
                "source_kind": "project",
                "source_uid": "project:registered-b",
                "import_source_uid": self.uid,
                "registered": True,
                "selected": True,
                "selection_order": 2,
            })
        return state

    def graph_mutations(self):
        return [event for event in self.host.events if event[0] in {"delete", "remove"}]

    def assert_saved_registration(self):
        registered = [row for row in self.target.state["assets"] if row.get("source_uid") == "project:registered-b"]
        self.assertEqual(len(registered), 1)
        self.assertTrue(registered[0]["registered"])
        self.assertTrue(registered[0]["selected"])
        self.assertTrue(self.target.state["asset_registration_result"]["ok"])

    def test_published_add_cleanup_runs_once_after_registered_state_is_visible(self):
        with self.host.installed():
            finish = self.begin()
            published = self.target._publish_state(self.completion_state())
            finish(published)
            finish(published)
        self.assertEqual(self.graph_mutations(), [("delete", self.names[1]), ("remove", self.names[1])])
        self.assertLess(self.host.events.index(("publish", True)), self.host.events.index(("delete", self.names[1])))
        self.assertEqual([p.name for p in self.target.children], [self.names[0], self.names[2]])
        self.assert_saved_registration()

    def test_failed_registration_completion_never_changes_graph(self):
        with self.host.installed():
            finish = self.begin()
            finish(self.target._publish_state(self.completion_state(ok=False)))
        self.assertEqual(self.graph_mutations(), [])
        self.assertEqual([p.name for p in self.target.children], self.names)

    def test_source_node_replaced_during_add_preserves_new_connection(self):
        with self.host.installed():
            finish = self.begin()
            self.host.nodes["source_b"] = SimpleNamespace(
                parameter_output_values={"IMAGE_OUT": self.target.images[1]}
            )
            finish(self.target._publish_state(self.completion_state()))
        self.assertEqual(self.graph_mutations(), [])
        self.assertIn("changed during Add", self.target.state["asset_registration_result"]["message"])
        self.assert_saved_registration()

    def test_source_value_changed_during_add_preserves_new_image(self):
        with self.host.installed():
            finish = self.begin()
            new_image = "https://example.test/newer-image.png"
            self.host.nodes["source_b"].parameter_output_values["IMAGE_OUT"] = new_image
            self.target.parameter_values[self.names[1]] = new_image
            finish(self.target._publish_state(self.completion_state()))
        self.assertEqual(self.graph_mutations(), [])
        self.assertEqual(self.target.parameter_values[self.names[1]], new_image)
        self.assert_saved_registration()

    def test_cleanup_failure_preserves_successful_registration_and_other_inputs(self):
        self.host.delete_failure = True
        with self.host.installed():
            finish = self.begin()
            finish(self.target._publish_state(self.completion_state()))
        self.assertEqual(self.graph_mutations(), [("delete", self.names[1])])
        self.assertEqual([p.name for p in self.target.children], self.names)
        self.assertIn("cleanup", self.target.state["asset_registration_result"]["message"])
        self.assert_saved_registration()

    def test_stale_owner_cannot_retire_connections(self):
        with self.host.installed():
            finish = self.begin()
            self.target._scan_owner_is_current = lambda: False
            finish(self.target._publish_state(self.completion_state()))
        self.assertEqual(self.graph_mutations(), [])
        self.assert_saved_registration()

    def test_queued_publication_does_not_reenter_from_delete_value_callback(self):
        with self.host.installed():
            finish = self.begin()
            self.target._ensure_scan_runtime_state = lambda: None
            self.target._hmb_scan_lock = threading.RLock()
            self.target._hmb_scan_generation = 7
            self.target._hmb_scan_pending_key = "queued-registration"
            self.target._hmb_scan_thread = None
            self.target._replace_import_media = lambda media: None
            self.target._publish_completed_catalog_scan = lambda state, key: self.target._publish_state(state)
            self.target._run_catalog_publication_callback = lambda callback, published: library.HMBImageAssetLibrary._run_catalog_publication_callback(self.target, callback, published)
            payload = {
                "state": self.completion_state(),
                "scan_base": deepcopy(self.target.state),
                "result_merger": lambda state, base, live: deepcopy(state),
                "on_published": finish,
            }
            self.target._hmb_scan_pending_result = (7, "queued-registration", "scan-7", payload)
            reentry_results = []

            def native_value_callback():
                self.assertTrue(self.target._hmb_catalog_completion_active)
                reentry_results.append(
                    library.HMBImageAssetLibrary._consume_pending_catalog_scan_result(self.target)
                )

            self.host.before_delete = native_value_callback
            consumed = library.HMBImageAssetLibrary._consume_pending_catalog_scan_result(self.target)
        self.assertTrue(consumed)
        self.assertEqual(reentry_results, [False])
        self.assertEqual([event for event in self.host.events if event[0] == "publish"], [("publish", True)])
        self.assertEqual(self.graph_mutations(), [("delete", self.names[1]), ("remove", self.names[1])])
        self.assertIsNone(self.target._hmb_scan_pending_result)
        self.assertFalse(self.target._hmb_catalog_completion_active)
        self.assert_saved_registration()

    def test_publication_guard_restores_previous_value_when_callback_raises(self):
        for previous in (False, True):
            self.target._hmb_catalog_completion_active = previous

            def failing_callback(published):
                self.assertTrue(self.target._hmb_catalog_completion_active)
                raise RuntimeError("injected publication callback failure")

            with self.assertRaisesRegex(RuntimeError, "injected publication"):
                library.HMBImageAssetLibrary._run_catalog_publication_callback(
                    self.target, failing_callback, self.completion_state()
                )
            self.assertEqual(self.target._hmb_catalog_completion_active, previous)


if __name__ == "__main__":
    unittest.main(verbosity=2)
