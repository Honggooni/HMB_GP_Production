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

    def get_parameter_by_name(self, name):
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


class FakeRetainedHost:
    def __init__(self, target):
        self.target = target
        self.nodes = {
            f"source_{key}": SimpleNamespace(parameter_output_values={"IMAGE_OUT": image})
            for key, image in zip("abc", target.images)
        }
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
        self.before_delete = None

    def get_node_by_name(self, name):
        return self.nodes[name]

    def handle_request(self, request):
        if isinstance(request, ListConnectionsForNodeRequest):
            self.events.append(("list", request.node_name))
            return ListConnectionsForNodeResultSuccess(
                incoming_connections=list(self.incoming), outgoing_connections=list(self.outgoing)
            )
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
            self.events.append(("remove", request.parameter_name))
            if self.remove_failure:
                return RemoveParameterFromNodeResultFailure(result_details="injected remove failure")
            # Removal must reach the host only after the exact child is disconnected.
            assert not any(e.target_parameter_name == request.parameter_name for e in self.incoming)
            assert not any(e.source_parameter_name == request.parameter_name for e in self.outgoing)
            self.target.children[:] = [p for p in self.target.children if p.name != request.parameter_name]
            self.target.parameters.pop(request.parameter_name, None)
            return RemoveParameterFromNodeResultSuccess()
        raise AssertionError(f"Unexpected retained request: {request!r}")

    @contextmanager
    def installed(self):
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
            EventManager=lambda: SimpleNamespace(event_loop=self.loop),
        )
        with patch.dict(sys.modules, modules), patch.object(library, "ParameterList", ImportList):
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
