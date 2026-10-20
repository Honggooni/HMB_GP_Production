"""Offline boundary: shared Agent editor output cannot replace another Shot.

The real Generator methods are exercised with a bounded retained-edge fixture.
Native getter/setter and serialization use the same raw-value entry point as
the installed SDK; model, Broker, live graph and user configuration stay unused.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("seedance_managed_prompt_projection", ROOT / "HMBSeedanceGeneration.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Generator = module.HMBSeedanceGeneration
Base = Generator.__mro__[1]


def forbidden(*_args, **_kwargs):
    raise AssertionError("Projection must never use transport or run a model")


def identity(number):
    return {"channel_uuid": "11111111-1111-4111-8111-111111111111",
            "shot_uuid": f"22222222-2222-4222-8222-{number:012d}",
            "shot_number": number, "shot_name": f"Authored asset {number}"}


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.edges = {}
        self.records = {number: {"text": f"Exact final text {number}", "shot": identity(number)}
                        for number in range(1, 6)}
        self.source = SimpleNamespace(
            name="shared_agent", _hmb_node_deleted=False,
            _hmb_shot_manager_enabled=lambda: True,
            _hmb_agent_shot_preview=lambda **key: deepcopy(next((value for value in self.records.values()
                if value["shot"]["channel_uuid"] == key["channel_uuid"]
                and value["shot"]["shot_uuid"] == key["shot_uuid"]), None)),
        )
        self.connections = SimpleNamespace(get_incoming_connections_to_parameter=
            lambda node, _parameter: self.edges.get(id(node), []))
        self.patches = [
            mock.patch.object(socket, "create_connection", forbidden),
            mock.patch.object(socket.socket, "connect", forbidden),
            mock.patch.object(urllib.request, "urlopen", forbidden),
            mock.patch.object(module.GriptapeNodes, "FlowManager", return_value=SimpleNamespace(get_connections=lambda: self.connections)),
            # Match the installed SDK's raw getter seam, absent from CI stubs.
            mock.patch.object(Base, "_get_raw_parameter_value", lambda node, name: node.parameter_values.get(name), create=True),
            mock.patch.object(Base, "get_parameter_value", lambda node, name: node._get_raw_parameter_value(name)),
            mock.patch.object(Base, "set_parameter_value", lambda node, name, value, **_kwargs: node.parameter_values.__setitem__(name, value)),
            mock.patch.object(module._shot_routing, "_same_flow_nodes", forbidden),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()

    def node(self, number):
        node = object.__new__(Generator)
        node.name = f"generator_{number}"
        node.parameter_values = {"prompt": f"Saved own text {number}"}
        node.parameter_output_values = {}
        node._hmb_node_deleted = False
        node._shot_identity = lambda: identity(number)
        prompt = SimpleNamespace(name="prompt")
        node.get_parameter_by_name = lambda name: prompt if name == "prompt" else None
        node.before_value_set = lambda parameter, value: value
        node.after_value_set = lambda parameter, value: None
        self.edges[id(node)] = [SimpleNamespace(target_node=node, target_parameter=prompt,
            source_node=self.source, source_parameter=SimpleNamespace(name="output"))]
        return node

    def test_five_bound_generators_keep_distinct_read_save_and_event_values(self):
        nodes = [self.node(number) for number in range(1, 6)]
        for editor_output in ("Final text for open editor 2", "", "Final text for open editor 5"):
            for number, node in enumerate(nodes, 1):
                node.set_parameter_value("prompt", editor_output)
                expected = f"Exact final text {number}"
                self.assertEqual(node.get_parameter_value("prompt"), expected)
                self.assertEqual(node._get_raw_parameter_value("prompt"), expected)
                self.assertEqual(node.parameter_values["prompt"], expected)
                self.assertEqual(node._shot_identity(), identity(number))

    def test_serialized_replay_cannot_restore_other_shot_text(self):
        node = self.node(1)
        node.set_parameter_value("prompt", "Saved selected Agent Shot 2", initial_setup=True)
        self.assertEqual(node.parameter_values["prompt"], "Exact final text 1")
        self.assertEqual(node._get_raw_parameter_value("prompt"), "Exact final text 1")

    def test_unrun_shot_stays_empty_instead_of_inheriting_active_editor(self):
        self.records[2]["text"] = ""
        node = self.node(2)
        node.set_parameter_value("prompt", "Completed other Shot 1")
        self.assertEqual(node.get_parameter_value("prompt"), "")
        self.assertEqual(node.parameter_values["prompt"], "")

    def test_missing_foreign_or_unavailable_shot_has_no_other_shot_fallback(self):
        node = self.node(2)
        for preview in (None, self.records[1], {"text": 42, "shot": identity(2)},
                        {"text": "Foreign channel text", "shot": {**identity(2), "channel_uuid": "another-channel"}}):
            self.source._hmb_agent_shot_preview = lambda **_kwargs: deepcopy(preview)
            node.set_parameter_value("prompt", "Other Shot text")
            self.assertEqual(node._get_raw_parameter_value("prompt"), "")

    def test_same_uuid_rename_and_renumber_does_not_blank_own_text(self):
        node = self.node(2)
        self.records[2]["shot"].update(shot_number=5, shot_name="New authored asset name")
        node.set_parameter_value("prompt", "Other active editor text")
        self.assertEqual(node.parameter_values["prompt"], "Exact final text 2")
        self.assertEqual(node._get_raw_parameter_value("prompt"), "Exact final text 2")

    def test_failed_preview_or_deleted_owner_never_leaks_visible_output(self):
        node = self.node(2)
        self.source._hmb_agent_shot_preview = forbidden
        self.assertEqual(node._get_raw_parameter_value("prompt"), "")
        self.source._hmb_node_deleted = True
        self.assertEqual(node._get_raw_parameter_value("prompt"), "")

    def test_only_direct_prompt_and_standard_or_legacy_agent_remain_native(self):
        for mode in ("only", "manual", "standard", "legacy"):
            node = self.node(1)
            node._shot_identity = lambda: identity(1)
            self.source._hmb_shot_manager_enabled = lambda: True
            self.edges[id(node)][0].source_parameter.name = "output"
            if mode == "only":
                node._shot_identity = lambda: {**identity(1), "channel_uuid": "", "shot_uuid": ""}
            elif mode == "manual":
                self.edges[id(node)] = []
            elif mode == "standard":
                self.edges[id(node)] = [SimpleNamespace(target_node=node,
                    target_parameter=SimpleNamespace(name="prompt"), source_node=SimpleNamespace(),
                    source_parameter=SimpleNamespace(name="output"))]
            else:
                self.edges[id(node)] = [SimpleNamespace(target_node=node,
                    target_parameter=SimpleNamespace(name="prompt"), source_node=self.source,
                    source_parameter=SimpleNamespace(name="output"))]
                self.source._hmb_shot_manager_enabled = lambda: False
            node.set_parameter_value("prompt", f"Native {mode}")
            self.assertEqual(node.get_parameter_value("prompt"), f"Native {mode}")

    def test_same_name_replacement_is_read_from_actual_edge_instance(self):
        node = self.node(1)
        replacement = SimpleNamespace(name=self.source.name, _hmb_node_deleted=False,
            _hmb_shot_manager_enabled=lambda: True,
            _hmb_agent_shot_preview=lambda **_kwargs: {"text": "New owner result", "shot": identity(1)})
        self.edges[id(node)][0].source_node = replacement
        self.assertFalse(node._hmb_refresh_managed_prompt_projection(source_node=self.source, force=True))
        self.assertTrue(node._hmb_refresh_managed_prompt_projection(source_node=replacement, force=True))
        self.assertEqual(node.parameter_values["prompt"], "New owner result")

    def test_notification_is_exact_shot_and_changes_stored_native_value(self):
        node = self.node(2)
        self.assertFalse(node._hmb_refresh_managed_prompt_projection(source_node=self.source,
            channel_uuid=identity(1)["channel_uuid"], shot_uuid=identity(1)["shot_uuid"], force=True))
        self.records[2]["text"] = "New own result 2"
        self.assertTrue(node._hmb_refresh_managed_prompt_projection(source_node=self.source,
            channel_uuid=identity(2)["channel_uuid"], shot_uuid=identity(2)["shot_uuid"], force=True))
        self.assertEqual(node.parameter_values["prompt"], "New own result 2")
        self.assertFalse(node._hmb_refresh_managed_prompt_projection())
        self.assertTrue(node._hmb_refresh_managed_prompt_projection(force=True))

    def test_disconnected_and_reconnected_input_keeps_native_then_own_saved_text(self):
        node = self.node(1)
        edges = self.edges.pop(id(node))
        node.set_parameter_value("prompt", "Detached manual text")
        self.assertEqual(node.get_parameter_value("prompt"), "Detached manual text")
        self.edges[id(node)] = edges
        node._hmb_refresh_managed_prompt_projection(source_node=self.source, force=True)
        self.assertEqual(node.parameter_values["prompt"], "Exact final text 1")

    def test_web_request_adapter_keeps_immutable_prompt(self):
        node = self.node(1)
        node._web_owner = object()
        node.set_parameter_value("prompt", "Immutable web request text")
        self.assertEqual(node.get_parameter_value("prompt"), "Immutable web request text")


if __name__ == "__main__":
    unittest.main(verbosity=2)
