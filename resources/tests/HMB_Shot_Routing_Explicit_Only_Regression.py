"""Explicit Generator intent at the real router's catalog/edge boundaries.

Uses retained-edge doubles only: no SDK, GUI, provider, media or policy I/O.
Legacy participants intentionally omit the new execution-intent API.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("_explicit_only_router_test", ROOT / "_hmb_shot_routing.py")
assert spec is not None and spec.loader is not None
routing = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = routing
spec.loader.exec_module(routing)

CHANNEL = "channel-original"
SHOT = "shot-original"


def catalog(channel=CHANNEL, shot=SHOT):
    return {"schema": "hmb-shot-routing-catalog", "version": 1,
            "channel_uuid": channel, "publisher_instance_uuid": "publisher",
            "generation": 1, "shots": [{"shot_uuid": shot, "number": 1, "name": "Custom A"}]}


class Participant:
    def __init__(self, name, kind, *, enabled=True, channel=CHANNEL, shot=SHOT):
        self.name, self.kind = name, kind
        self.enabled, self.channel_uuid, self.shot_uuid = enabled, channel, shot
        self.shot_number, self.shot_name = 1, "Custom A"
        self.catalogs, self.statuses, self.prepared = [], [], []
        self._hmb_node_deleted = False
        self.authored = {"prompt": "literal {0} OFF", "resolution": "480p", "duration": 4,
                         "references": ["second", "first"], "empty": "", "zero": 0}

    def _hmb_shot_channel_subscription(self):
        return {"schema": routing.SUBSCRIPTION_SCHEMA, "version": 1,
                "participant_kind": self.kind, "enabled": self.enabled,
                "channel_uuid": self.channel_uuid, "shot_uuid": self.shot_uuid,
                "shot_number": self.shot_number, "shot_name": self.shot_name}

    def _hmb_reconcile_shot_routing(self, snapshot):
        self.catalogs.append(copy.deepcopy(snapshot))
        self.channel_uuid = snapshot["channel_uuid"]
        if not self.shot_uuid:
            self.shot_uuid = snapshot["shots"][0]["shot_uuid"]
        self.enabled = True

    def _hmb_shot_routing_status(self, value):
        self.statuses.append(value)

    def _hmb_prepare_remote_prompt_route(self, source):
        self.prepared.append(source.name)
        return True

    def _hmb_clear_shot_routing_catalog(self, reason):
        self.enabled, self.channel_uuid, self.shot_uuid = False, "", ""


class Generator(Participant):
    def __init__(self, mode="only", *, channel=CHANNEL, shot=SHOT, enabled=True):
        super().__init__("Generator", routing.KIND_SEEDANCE, enabled=enabled, channel=channel, shot=shot)
        self.mode = mode
        self.requested = {"channel_uuid": channel, "shot_uuid": shot,
                          "shot_number": 1, "shot_name": "Custom A"}
        self.misbehaving_callback = False

    def _hmb_seedance_execution_mode(self):
        return self.mode

    def _hmb_seedance_requested_shot_identity(self):
        return copy.deepcopy(self.requested)

    def _hmb_reconcile_shot_routing(self, snapshot):
        self.catalogs.append(copy.deepcopy(snapshot))
        self._hmb_shot_catalog_snapshot = copy.deepcopy(snapshot)
        if self.mode == "only" and not self.misbehaving_callback:
            return
        if self.mode == "waiting":
            assert snapshot["channel_uuid"] == self.requested["channel_uuid"]
            assert any(row["shot_uuid"] == self.requested["shot_uuid"] for row in snapshot["shots"])
            self.mode = "shot"
            self.channel_uuid = self.requested["channel_uuid"]
            self.shot_uuid = self.requested["shot_uuid"]
        elif self.mode == "shot" and not any(row["shot_uuid"] == self.shot_uuid for row in snapshot["shots"]):
            self.mode, self.enabled = "waiting", False
            return
        else:
            self.channel_uuid = snapshot["channel_uuid"]
            self.shot_uuid = snapshot["shots"][0]["shot_uuid"]
        self.enabled = True


class ExplicitOnlyRouting(unittest.TestCase):
    def setUp(self):
        self.image = Participant("Image", routing.KIND_IMAGE_ASSET)
        self.image.snapshot = catalog()
        self.image._hmb_shot_routing_catalog = lambda: self.image.snapshot
        self.prompt = Participant("Prompt", routing.KIND_PROMPT)
        self.agent = Participant("Agent", routing.KIND_AGENT)
        self.generator = Generator()
        self.nodes = [self.image, self.prompt, self.agent, self.generator]
        self.edges, self.created, self.deleted = [], [], []
        patches = {
            "_same_flow_nodes": lambda node: ("isolated-flow", list(self.nodes)),
            "_incoming_connections": lambda node: [e for e in self.edges if e.target_node_name == node.name],
            "_create_connection": self.create,
            "_delete_connection": self.delete,
            "_has_parameter": lambda node, name: True,
        }
        for name, replacement in patches.items():
            patch = mock.patch.object(routing, name, replacement)
            patch.start()
            self.addCleanup(patch.stop)

    def connect(self, source, port, target=None, input="prompt"):
        edge = SimpleNamespace(source_node_name=source, source_parameter_name=port,
                               target_node_name=(target or self.generator).name, target_parameter_name=input)
        self.edges.append(edge)
        return edge

    def create(self, edge):
        self.created.append((edge.source.name, edge.source_parameter, edge.target.name, edge.target_parameter))
        self.connect(edge.source.name, edge.source_parameter, edge.target, edge.target_parameter)
        return True

    def delete(self, edge, target):
        self.deleted.append(edge)
        self.edges.remove(edge)
        return True

    def reconcile(self):
        return routing.reconcile_shot_routing(self.image, _allow_unready_cleanup=True)

    def generator_edges(self):
        return [edge for edge in self.edges if edge.target_node_name == self.generator.name]

    def test_01_only_stale_quartet_never_claims_or_routes_and_keeps_authored_inputs(self):
        before = copy.deepcopy(self.generator.authored)
        for _ in range(3):
            self.assertTrue(self.reconcile()["ok"])
        self.assertEqual(len(self.generator.catalogs), 3)
        self.assertFalse(routing._subscription_for(self.generator).enabled)
        self.assertEqual(self.generator.prepared, [])
        self.assertEqual(self.generator_edges(), [])
        self.assertEqual(self.generator.authored, before)

    def test_02_even_auto_adopting_stale_callback_cannot_route_explicit_only(self):
        self.generator.misbehaving_callback = True
        self.reconcile()
        self.assertTrue(self.generator.enabled)
        self.assertEqual(self.generator.mode, "only")
        self.assertEqual(self.generator_edges(), [])
        self.assertIsNone(routing.resolve_shot_agent_owner(self.generator, CHANNEL, SHOT))
        self.assertIsNone(routing.resolve_shot_prompt_owner(self.generator, CHANNEL, SHOT))

    def test_03_only_clears_old_hmb_routes_but_preserves_native_text_media_wires(self):
        self.connect("Agent", "output")
        self.connect("Image", "SHOT_ASSET_OUT", input="SHOT_ASSET_IN")
        native = self.connect("Standard Agent", "output")
        text = self.connect("Text", "text")
        media = self.connect("Video Loader", "video", input="reference_videos")
        self.reconcile()
        self.assertEqual(self.generator_edges(), [native, text, media])
        self.assertEqual(len(self.deleted), 2)

    def test_04_only_survives_publisher_delete_recreate_new_uuid_and_rename(self):
        self.reconcile()
        self.nodes.remove(self.image)
        self.reconcile()
        self.image.snapshot = catalog("replacement-channel", "new-uuid")
        self.image.channel_uuid, self.image.shot_uuid = "replacement-channel", "new-uuid"
        self.nodes.insert(0, self.image)
        self.reconcile()
        self.assertEqual(self.generator.mode, "only")
        self.assertEqual(self.generator.catalogs[-1]["channel_uuid"], "replacement-channel")
        self.assertEqual(self.generator_edges(), [])

    def test_05_waiting_never_adopts_same_number_new_uuid_or_foreign_channel(self):
        self.generator.mode = "waiting"
        for channel, shot in ((CHANNEL, "new-uuid"), ("replacement-channel", SHOT)):
            with self.subTest(channel=channel, shot=shot):
                self.image.channel_uuid = channel
                self.image.snapshot = catalog(channel, shot)
                self.reconcile()
                self.assertEqual(self.generator.mode, "waiting")
                self.assertEqual(self.generator.catalogs, [])
                self.assertEqual(self.generator.prepared, [])
                self.assertEqual(self.generator_edges(), [])
                subscription = routing._subscription_for(self.generator)
                self.assertEqual((subscription.channel_uuid, subscription.shot_uuid), (CHANNEL, SHOT))

    def test_06_waiting_exact_uuid_restore_rebinds_existing_chain(self):
        self.generator.mode = "waiting"
        self.generator.enabled = False
        self.generator.channel_uuid = self.generator.shot_uuid = ""
        self.assertTrue(self.reconcile()["ok"])
        self.assertEqual(self.generator.mode, "shot")
        self.assertEqual(self.generator.prepared, ["Agent"])
        self.assertIn(("Agent", "output", "Generator", "prompt"), self.created)
        self.assertIn(("Image", "SHOT_ASSET_OUT", "Generator", "SHOT_ASSET_IN"), self.created)

    def test_07_shot_deletion_goes_waiting_and_exact_uuid_return_restores(self):
        self.generator.mode = "shot"
        self.reconcile()
        self.image.snapshot = catalog(CHANNEL, "new-uuid")
        self.reconcile()
        self.assertEqual(self.generator.mode, "waiting")
        self.assertEqual(self.generator_edges(), [])
        self.image.snapshot = catalog()
        self.reconcile()
        self.assertEqual(self.generator.mode, "shot")
        self.assertEqual(len(self.generator_edges()), 2)

    def test_08_direct_edge_guard_never_creates_in_only_or_waiting(self):
        edge = routing.ShotEdge(self.agent, "output", self.generator, "prompt")
        for mode in ("only", "waiting"):
            self.generator.mode = mode
            self.assertFalse(routing._ensure_edge(edge, {})[0])
        self.assertEqual(self.created, [])

    def test_09_mode_api_errors_fail_closed_and_legacy_auto_is_unchanged(self):
        self.generator.mode = {"invalid": "mode"}
        self.assertFalse(routing._subscription_for(self.generator).enabled)
        self.assertFalse(routing._seedance_catalog_allowed(self.generator, catalog("other")))
        legacy = Participant("Legacy", routing.KIND_SEEDANCE, enabled=False, channel="", shot="")
        self.nodes[-1] = legacy
        self.reconcile()
        self.assertTrue(routing._subscription_for(legacy).enabled)
        self.assertIn(("Agent", "output", "Legacy", "prompt"), self.created)

    def test_10_only_standalone_picker_options_do_not_restore_suspended_shot(self):
        self.nodes.remove(self.image)
        picker = Participant("Picker", routing.KIND_VIDEO_PICKER, channel="picker-channel")
        picker._hmb_standalone_shot_routing_catalog = lambda: catalog("picker-channel", "picker-shot")
        self.nodes.insert(0, picker)
        self.generator._hmb_suspended_shot_identity = {"channel_uuid": CHANNEL, "shot_uuid": SHOT}
        self.reconcile()
        self.assertEqual(self.generator.mode, "only")
        self.assertEqual(self.generator.catalogs[-1]["channel_uuid"], "picker-channel")
        self.assertEqual(self.generator_edges(), [])

    def test_11_waiting_publisher_disconnect_and_exact_recreation_restores_only_requested_uuid(self):
        self.generator.mode = "shot"
        self.reconcile()
        self.nodes.remove(self.image)
        # DeleteNode removes the deleted publisher's retained edges itself.
        self.edges[:] = [edge for edge in self.edges if edge.source_node_name != self.image.name]
        self.generator.mode = "waiting"
        self.reconcile()
        self.assertEqual(self.generator_edges(), [])
        self.assertEqual(self.generator.requested["shot_uuid"], SHOT)
        self.image = Participant("Recreated Image", routing.KIND_IMAGE_ASSET)
        self.image._hmb_shot_routing_catalog = catalog
        self.nodes.insert(0, self.image)
        self.assertTrue(self.reconcile()["ok"])
        self.assertEqual(self.generator.mode, "shot")
        self.assertIn(("Recreated Image", "SHOT_ASSET_OUT", "Generator", "SHOT_ASSET_IN"), self.created)

    def test_12_only_to_explicit_shot_is_the_only_action_that_reenables_routing(self):
        self.reconcile()
        self.assertEqual(self.generator_edges(), [])
        self.generator.mode = "shot"
        self.assertTrue(self.reconcile()["ok"])
        self.assertEqual(len(self.generator_edges()), 2)
        self.generator.mode = "only"
        self.reconcile()
        self.assertEqual(self.generator_edges(), [])

    def test_13_intent_changes_during_route_preparation_still_cannot_create_edges(self):
        self.generator.mode = "shot"
        def select_only(_source):
            self.generator.mode = "only"
            return True
        self.generator._hmb_prepare_remote_prompt_route = select_only
        self.reconcile()
        self.assertEqual(self.generator.mode, "only")
        self.assertEqual(self.generator_edges(), [])

    def test_14_throwing_mode_api_and_missing_requested_identity_fail_closed(self):
        def unavailable():
            raise RuntimeError("mode unavailable")
        self.generator._hmb_seedance_execution_mode = unavailable
        self.generator._hmb_seedance_requested_shot_identity = lambda: {}
        self.reconcile()
        self.assertFalse(routing._subscription_for(self.generator).enabled)
        self.assertEqual(self.generator.catalogs, [])
        self.assertEqual(self.generator_edges(), [])


if __name__ == "__main__":
    unittest.main()
