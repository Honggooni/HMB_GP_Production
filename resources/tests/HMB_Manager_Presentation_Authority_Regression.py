"""Manager tabs and display ordering never replace registered routing ownership."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from HMB_Multishot_Manager_Routing_Regression import Node, CHANNEL, SHOTS, routing


class ManagerPresentationAuthority(unittest.TestCase):
    kinds = (routing.KIND_PROMPT, routing.KIND_AGENT, routing.KIND_FINISH_LOOK)

    def remember(self, node):
        fingerprint = routing._subscription_fingerprint(node)
        routing._AUTHORITATIVE_FINGERPRINTS[node] = fingerprint
        return fingerprint

    def test_tab_switch_keeps_authority_for_all_manager_kinds(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                node = Node(kind, kind, manager=True)
                expected = self.remember(node)
                for index in range(5):
                    node.active = index
                    self.assertEqual(node._hmb_shot_channel_subscription()['shot_uuid'], SHOTS[index][0])
                    self.assertEqual(routing._subscription_fingerprint(node), expected)
                    self.assertTrue(routing._subscription_is_authoritative(routing._subscription_for(node)))

    def test_rename_renumber_and_declared_row_order_keep_authority(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                node = Node(kind, kind, manager=True)
                expected = self.remember(node)
                node.rows = [(uid, 6-number, 'Renamed '+name) for uid, number, name in reversed(SHOTS)]
                self.assertEqual(routing._subscription_fingerprint(node), expected)
                self.assertTrue(routing._subscription_is_authoritative(routing._subscription_for(node)))

    def test_each_exact_target_still_resolves_its_own_declared_row(self):
        prompt = Node('Prompt', routing.KIND_PROMPT, manager=True, active=4)
        agent = Node('Agent', routing.KIND_AGENT, manager=True, active=3)
        finish = Node('Finish', routing.KIND_FINISH_LOOK, manager=True, active=2)
        subscriptions = [routing._subscription_for(node) for node in (prompt, agent, finish)]
        for kind in self.kinds:
            for uid, number, name in SHOTS:
                with self.subTest(kind=kind, target=uid):
                    selected, duplicate = routing._single(subscriptions, kind=kind,
                        channel_uuid=CHANNEL, shot_uuid=uid)
                    self.assertFalse(duplicate)
                    self.assertEqual((selected.shot_uuid, selected.shot_number, selected.shot_name), (uid, number, name))

    def test_real_channel_or_representative_membership_change_invalidates_authority(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                node = Node(kind, kind, manager=True)
                old = self.remember(node)
                node.rows = list(SHOTS[1:])
                self.assertNotEqual(routing._subscription_fingerprint(node), old)
                self.assertFalse(routing._subscription_is_authoritative(routing._subscription_for(node)))
                node.rows = list(SHOTS)
                node.channel = '99999999-9999-4999-8999-999999999999'
                self.assertNotEqual(routing._subscription_fingerprint(node), old)
                self.assertFalse(routing._subscription_is_authoritative(routing._subscription_for(node)))

    def test_legacy_individual_selection_remains_part_of_authority(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                node = Node(kind, kind, manager=False)
                old = self.remember(node)
                node.active = 4
                self.assertNotEqual(routing._subscription_fingerprint(node), old)
                self.assertFalse(routing._subscription_is_authoritative(routing._subscription_for(node)))

    def test_invalid_declared_rows_do_not_grant_exact_target_ownership(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                node = Node(kind, kind, manager=True)
                node.rows = [SHOTS[0], SHOTS[0]]
                self.assertEqual(routing._manager_shot_subscriptions(node, kind), ())
                selected, _ = routing._single([routing._subscription_for(node)], kind=kind,
                    channel_uuid=CHANNEL, shot_uuid=SHOTS[0][0])
                self.assertIsNone(selected)
                node._hmb_node_deleted = True
                self.assertIsNone(routing._subscription_for(node))


if __name__ == '__main__':
    unittest.main(verbosity=2)
