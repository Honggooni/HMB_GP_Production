"""Offline ownership/edge regression for explicit Prompt and Agent managers."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("_hmb_manager_routing_regression", ROOT / "_hmb_shot_routing.py")
assert SPEC is not None and SPEC.loader is not None
routing = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = routing
SPEC.loader.exec_module(routing)
CHANNEL = "11111111-1111-4111-8111-111111111111"
SHOTS = [(f"33333333-3333-4333-8333-{index:012d}", index, f"Asset {index}") for index in range(1, 6)]


class Node:
    def __init__(self, name, kind, *, manager=False, enabled=True, active=0):
        self.name, self.kind = name, kind
        self.manager, self.enabled, self.active = manager, enabled, active
        self.channel = CHANNEL
        self.rows = list(SHOTS)
        self.statuses = []
        self.catalog_count = 0
        self.hydrate_calls = 0
        self.auto_claim_calls = 0
        self.paused = False
        self._hmb_node_deleted = False

    def _row(self, row):
        uid, number, name = row
        return dict(schema=routing.SUBSCRIPTION_SCHEMA, version=1, participant_kind=self.kind,
                    enabled=self.enabled, channel_uuid=self.channel, shot_uuid=uid,
                    shot_number=number, shot_name=name)

    def _hmb_shot_channel_subscription(self):
        return self._row(self.rows[self.active])

    def _hmb_shot_manager_enabled(self):
        return self.manager

    def _hmb_prompt_shot_subscriptions(self):
        return [self._row(row) for row in self.rows] if self.manager else []

    _hmb_agent_shot_subscriptions = _hmb_prompt_shot_subscriptions
    _hmb_finish_look_shot_subscriptions = _hmb_prompt_shot_subscriptions

    def _hmb_publish_routed_finish_snapshot(self, *, force=False):
        return True

    def _hmb_shot_manager_paused_for(self, *, channel_uuid, shot_uuid):
        return self.paused and channel_uuid == CHANNEL and any(row[0] == shot_uuid for row in self.rows)

    def _hmb_reconcile_shot_routing(self, snapshot):
        self.catalog_count += 1

    def _hmb_shot_routing_catalog(self):
        return dict(schema="hmb-shot-routing-catalog", version=1, channel_uuid=self.channel,
                    shots=[dict(shot_uuid=uid, number=number, name=name) for uid, number, name in SHOTS])

    def _hmb_shot_routing_status(self, value):
        self.statuses.append(value)

    def _hmb_prepare_remote_prompt_route(self, source):
        return True

    def _hmb_hydrate_shot_prompt_from_source(self, source, port):
        self.hydrate_calls += 1
        return True

    def _hmb_prepare_initial_shot_selection(self, *args):
        self.auto_claim_calls += 1


class ManagerRoutingTests(unittest.TestCase):
    def setUp(self):
        self.image = Node("Image", routing.KIND_IMAGE_ASSET)
        self.picker = Node("Picker", routing.KIND_VIDEO_PICKER)
        self.prompt = Node("Prompt manager", routing.KIND_PROMPT, manager=True)
        self.agent = Node("Agent manager", routing.KIND_AGENT, manager=True)
        self.generators = [Node(f"Generator {i + 1}", routing.KIND_SEEDANCE, active=i) for i in range(5)]
        self.nodes = [self.image, self.picker, self.prompt, self.agent, *self.generators]
        self.edges = set()
        self.created = 0
        self.deleted = 0
        routing._same_flow_nodes = lambda node: ("flow", list(self.nodes)) if node in self.nodes else ("", [])
        routing._has_parameter = lambda *args: True
        routing._incoming_connections = self.incoming
        routing._create_connection = self.create
        routing._delete_connection = self.delete

    def incoming(self, node):
        return [SimpleNamespace(source_node_name=s, source_parameter_name=sp,
                                target_node_name=t, target_parameter_name=tp)
                for s, sp, t, tp in self.edges if t == node.name]

    def create(self, edge):
        self.edges.add((edge.source.name, edge.source_parameter, edge.target.name, edge.target_parameter))
        self.created += 1
        return True

    def delete(self, edge, node):
        self.edges.remove((edge.source_node_name, edge.source_parameter_name,
                           edge.target_node_name, edge.target_parameter_name))
        self.deleted += 1
        return True

    def reconcile(self):
        return routing.reconcile_shot_routing(self.image, _allow_unready_cleanup=True)

    def values(self):
        return [routing._subscription_for(node) for node in self.nodes]

    def test_five_generators_share_exact_one_prompt_agent_dependency(self):
        result = self.reconcile()
        self.assertTrue(result["ok"], result)
        self.assertEqual(sum(tp == "SHOT_PROMPT_IN" for _, _, _, tp in self.edges), 1)
        self.assertEqual(sum(tp == "prompt" for _, _, _, tp in self.edges), 5)
        for generator in self.generators:
            self.assertIn((self.agent.name, "output", generator.name, "prompt"), self.edges)
            self.assertIn((self.image.name, "SHOT_ASSET_OUT", generator.name, "SHOT_ASSET_IN"), self.edges)
            self.assertIn((self.picker.name, "SHOT_PICKER_OUT", generator.name, "SHOT_PICKER_IN"), self.edges)
        self.assertEqual(self.agent.hydrate_calls, 0)

    def test_active_editor_switch_changes_no_shared_edges(self):
        self.assertTrue(self.reconcile()["ok"])
        before = set(self.edges)
        counts = self.created, self.deleted
        self.prompt.active = 4
        self.agent.active = 2
        result = self.reconcile()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(self.edges, before)
        self.assertEqual((self.created, self.deleted), counts)

    def test_finish_manager_routes_each_generator_without_following_its_open_row(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True, active=4)
        self.nodes.append(finish)
        result = self.reconcile()
        self.assertTrue(result["ok"], result)
        for generator in self.generators:
            self.assertIn((finish.name, "SHOT_FINISH_LOOK_OUT", generator.name, "SHOT_FINISH_LOOK_IN"), self.edges)
        before, counts = set(self.edges), (self.created, self.deleted)
        for active in (0, 3, 1, 4, 2):
            finish.active = active
            self.assertTrue(self.reconcile()["ok"])
            self.assertEqual(self.edges, before)
            self.assertEqual((self.created, self.deleted), counts)
            self.assertEqual(finish.active, active)

    def test_legacy_finish_retains_its_exact_shot_while_manager_owns_other_four(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True, active=4)
        legacy = Node("Legacy Finish", routing.KIND_FINISH_LOOK)
        self.nodes.extend([finish, legacy])
        self.assertTrue(self.reconcile()["ok"])
        self.assertIn((legacy.name, "SHOT_FINISH_LOOK_OUT", self.generators[0].name, "SHOT_FINISH_LOOK_IN"), self.edges)
        for generator in self.generators[1:]:
            self.assertIn((finish.name, "SHOT_FINISH_LOOK_OUT", generator.name, "SHOT_FINISH_LOOK_IN"), self.edges)

    def test_finish_tab_switch_does_not_reenter_hydration_pending(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True)
        self.nodes.append(finish)
        for node in self.nodes:
            routing._mark_authoritative(node)
        self.assertTrue(routing.reconcile_shot_routing(self.image)["ok"])
        before = set(self.edges)
        finish.active = 4
        result = routing.reconcile_shot_routing(self.image)
        self.assertEqual(result["code"], "ready", result)
        self.assertEqual(self.edges, before)

    def test_invalid_finish_manager_cannot_silently_drop_the_connected_look(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True)
        self.nodes.append(finish)
        self.assertTrue(self.reconcile()["ok"])
        finish._hmb_finish_look_shot_subscriptions = lambda: [finish._row(SHOTS[0])] * 2
        result = self.reconcile()
        self.assertFalse(result["ok"], result)
        self.assertTrue(any("duplicate_finish_look" in str(item) for item in result.get("failures", [])), result)

    def test_unbound_invalid_connected_finish_cannot_become_an_absent_optional_look(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True)
        self.nodes.append(finish)
        self.assertTrue(self.reconcile()["ok"])
        finish.enabled = False
        finish.channel = ""
        finish._hmb_finish_look_shot_subscriptions = lambda: []
        for _ in range(2):
            result = self.reconcile()
            self.assertFalse(result["ok"], result)
            for generator in self.generators:
                self.assertIn((finish.name, "SHOT_FINISH_LOOK_OUT", generator.name, "SHOT_FINISH_LOOK_IN"), self.edges)
            self.assertTrue(any("finish_look_source_unavailable" in item for item in result["failures"]))

    def test_catalog_rejected_connected_finish_stays_failed_across_repeated_runs(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True)
        self.nodes.append(finish)
        self.assertTrue(self.reconcile()["ok"])
        finish._hmb_reconcile_shot_routing = lambda _: (_ for _ in ()).throw(ValueError("Invalid catalog"))
        for _ in range(2):
            self.assertFalse(self.reconcile()["ok"])
            for generator in self.generators:
                self.assertIn((finish.name, "SHOT_FINISH_LOOK_OUT", generator.name, "SHOT_FINISH_LOOK_IN"), self.edges)

    def test_throwing_connected_finish_identity_cannot_become_an_absent_optional_look(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True)
        self.nodes.append(finish)
        self.assertTrue(self.reconcile()["ok"])
        finish._hmb_shot_channel_subscription = lambda: (_ for _ in ()).throw(ValueError("Unavailable identity"))
        for _ in range(2):
            self.assertFalse(self.reconcile()["ok"])
            for generator in self.generators:
                self.assertIn((finish.name, "SHOT_FINISH_LOOK_OUT", generator.name, "SHOT_FINISH_LOOK_IN"), self.edges)

    def test_unknown_finish_manager_flag_is_not_a_legacy_only_transition(self):
        finish = Node("Finish manager", routing.KIND_FINISH_LOOK, manager=True)
        self.nodes.append(finish)
        self.assertTrue(self.reconcile()["ok"])
        finish.enabled, finish.channel = False, ""
        for getter in (lambda: None, lambda: 1, lambda: (_ for _ in ()).throw(ValueError("Unknown manager mode"))):
            finish._hmb_shot_manager_enabled = getter
            for _ in range(2):
                self.assertFalse(self.reconcile()["ok"])
                for generator in self.generators:
                    self.assertIn((finish.name, "SHOT_FINISH_LOOK_OUT", generator.name, "SHOT_FINISH_LOOK_IN"), self.edges)

    def test_exact_legacy_prompt_agent_chain_keeps_ownership(self):
        old_prompt = Node("Legacy Prompt", routing.KIND_PROMPT)
        old_agent = Node("Legacy Agent", routing.KIND_AGENT)
        self.nodes.extend([old_prompt, old_agent])
        result = self.reconcile()
        self.assertTrue(result["ok"], result)
        self.assertIn((old_prompt.name, "PROMPT_OUT", old_agent.name, "SHOT_PROMPT_IN"), self.edges)
        self.assertIn((old_agent.name, "output", self.generators[0].name, "prompt"), self.edges)
        self.assertIs(routing.resolve_shot_prompt_owner(self.agent, CHANNEL, SHOTS[0][0]), old_prompt)
        self.assertIs(routing.resolve_shot_agent_owner(self.prompt, CHANNEL, SHOTS[0][0]), old_agent)
        self.assertIs(routing.resolve_shot_agent_owner(self.prompt, CHANNEL, SHOTS[1][0]), self.agent)

    def test_second_manager_keeps_established_edges_and_unbound_target_is_ambiguous(self):
        self.assertTrue(self.reconcile()["ok"])
        duplicate = Node("Another Agent", routing.KIND_AGENT, manager=True)
        self.nodes.append(duplicate)
        self.edges.remove((self.agent.name, "output", self.generators[4].name, "prompt"))
        result = self.reconcile()
        self.assertFalse(result["ok"])
        self.assertTrue(self.agent.manager)
        self.assertTrue(duplicate.manager)
        self.assertEqual(sum(tp == "prompt" for _, _, _, tp in self.edges), 4)
        for generator in self.generators[:4]:
            self.assertIn((self.agent.name, "output", generator.name, "prompt"), self.edges)
        self.assertIsNone(routing.resolve_shot_agent_owner(self.prompt, CHANNEL, SHOTS[2][0]))

    def test_multiple_agent_managers_preserve_explicit_per_generator_owners(self):
        self.assertTrue(self.reconcile()["ok"])
        second = Node("Second Agent", routing.KIND_AGENT, manager=True)
        self.nodes.append(second)
        self.edges.remove((self.agent.name, "output", self.generators[1].name, "prompt"))
        self.edges.add((second.name, "output", self.generators[1].name, "prompt"))
        result = self.reconcile()
        self.assertTrue(result["ok"], result)
        self.assertIn((self.agent.name, "output", self.generators[0].name, "prompt"), self.edges)
        self.assertIn((second.name, "output", self.generators[1].name, "prompt"), self.edges)
        self.assertIs(routing.resolve_shot_agent_owner(self.generators[1], CHANNEL, SHOTS[1][0]), second)
        before, counts = set(self.edges), (self.created, self.deleted)
        self.agent.active, second.active, self.prompt.active = 4, 3, 2
        self.assertTrue(self.reconcile()["ok"])
        self.assertEqual(self.edges, before)
        self.assertEqual((self.created, self.deleted), counts)

    def test_only_pause_preserves_its_generator_owner_until_explicit_rewire(self):
        self.assertTrue(self.reconcile()["ok"])
        second = Node("Second Agent", routing.KIND_AGENT, manager=True)
        self.nodes.append(second)
        self.agent.manager, self.agent.enabled, self.agent.channel, self.agent.paused = False, False, "", True
        before = set(self.edges)
        result = self.reconcile()
        self.assertFalse(result["ok"])
        self.assertEqual({edge for edge in self.edges if edge[2] in {g.name for g in self.generators}},
                         {edge for edge in before if edge[2] in {g.name for g in self.generators}})
        self.assertTrue(all(g.statuses[-1]["code"] == "agent_manager_paused" for g in self.generators))
        # User rewiring is explicit authority even while the old owner remains paused.
        self.edges.remove((self.agent.name, "output", self.generators[1].name, "prompt"))
        self.edges.add((second.name, "output", self.generators[1].name, "prompt"))
        self.reconcile()
        self.assertEqual(self.generators[1].statuses[-1]["code"], "ready")
        self.assertEqual(self.generators[0].statuses[-1]["code"], "agent_manager_paused")
        self.agent.manager, self.agent.enabled, self.agent.channel, self.agent.paused = True, True, CHANNEL, False
        self.assertTrue(self.reconcile()["ok"])
        self.assertIn((self.agent.name, "output", self.generators[0].name, "prompt"), self.edges)
        self.assertIn((second.name, "output", self.generators[1].name, "prompt"), self.edges)

    def test_two_prompt_managers_never_choose_one_by_order(self):
        self.nodes.append(Node("Second Prompt", routing.KIND_PROMPT, manager=True))
        self.assertFalse(self.reconcile()["ok"])
        self.assertFalse(any(tp in {"prompt", "SHOT_PROMPT_IN"} for _, _, _, tp in self.edges))

    def test_only_opt_out_removes_managed_edges_and_does_not_autoclaim(self):
        self.assertTrue(self.reconcile()["ok"])
        self.agent.manager = False
        self.agent.enabled = False
        self.agent.channel = ""
        result = self.reconcile()
        self.assertTrue(result["ok"], result)
        self.assertFalse(any(t == self.agent.name and tp == "SHOT_PROMPT_IN" for _, _, t, tp in self.edges))
        self.assertFalse(any(tp == "prompt" for _, _, _, tp in self.edges))
        self.assertEqual(self.agent.auto_claim_calls, 0)

    def test_manager_does_not_merge_existing_legacy_prompt_edge(self):
        legacy = Node("Legacy Prompt", routing.KIND_PROMPT)
        self.nodes.append(legacy)
        original = (legacy.name, "PROMPT_OUT", self.agent.name, "SHOT_PROMPT_IN")
        self.edges.add(original)
        result = self.reconcile()
        self.assertFalse(result["ok"])
        self.assertIn(original, self.edges)
        self.assertTrue(any("manager_prompt_conflict" in row for row in result["failures"]))

    def test_missing_wrong_channel_deleted_or_unregistered_owner_is_not_authority(self):
        self.assertIsNone(routing.resolve_shot_prompt_owner(self.agent, "another", SHOTS[0][0]))
        self.assertIsNone(routing.resolve_shot_prompt_owner(Node("Unregistered", routing.KIND_AGENT), CHANNEL, SHOTS[0][0]))
        self.prompt._hmb_node_deleted = True
        self.assertIsNone(routing.resolve_shot_prompt_owner(self.agent, CHANNEL, SHOTS[0][0]))

    def test_invalid_manager_declarations_are_fail_closed(self):
        for rows in ([SHOTS[0], SHOTS[0]], [(*SHOTS[0][:1], 6, "bad")], []):
            with self.subTest(rows=rows):
                self.prompt.rows = rows
                self.assertEqual(routing._manager_shot_subscriptions(self.prompt, routing.KIND_PROMPT), ())

    def test_foreign_prompt_input_is_not_replaced(self):
        foreign = ("User text", "text", self.agent.name, "SHOT_PROMPT_IN")
        self.edges.add(foreign)
        self.assertFalse(self.reconcile()["ok"])
        self.assertIn(foreign, self.edges)


if __name__ == "__main__":
    unittest.main()
