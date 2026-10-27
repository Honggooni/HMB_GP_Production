"""Restored Agent rows remain readable, never executable before live routing."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
from HMB_Agent_Catalog_Presentation_Regression import surface, module, catalog


class RestoredRows(unittest.TestCase):
    def exercise(self):
        node, source, body, rows, writes, publications, setter = surface()
        node._hmb_shot_catalog_snapshot = {}
        return node, source, body, rows, writes, publications, setter
    def test_repeated_layout_and_early_rejection_keep_saved_five_rows(self):
        node, _, body, rows, _, _, setter = self.exercise()
        saved = catalog(2)
        original_slots = deepcopy(node._hmb_shot_slots)
        original_native = {p.name:deepcopy(node.parameter_values.get(p.name)) for p in body}
        with patch.object(module._BaseAgent, 'set_parameter_value', setter), patch.object(module._BaseAgent, 'after_value_set', lambda *a:None):
            node._hmb_layout_shot_editor(restored_catalog=saved)
            for _ in range(3): node._hmb_request_editor_layout()
            for row in rows:
                value = node.parameter_values[row.name]
                self.assertTrue(value['shot']['shot_uuid'])
                self.assertTrue(value['routing_pending'])
                self.assertFalse(row.ui_options.get('hide'))
            command = deepcopy(node.parameter_values[rows[1].name])
            command['action'] = {'kind':'select', 'request_id':'a'*32}
            with self.assertRaisesRegex(RuntimeError, 'identity is unavailable'):
                node._hmb_handle_row_action(rows[1], command)
            self.assertEqual(node.parameter_values[rows[1].name]['shot']['shot_uuid'], 'shot-2')
            self.assertTrue(node.parameter_values[rows[1].name]['routing_pending'])
        self.assertEqual(node._hmb_shot_catalog_snapshot, {})
        self.assertEqual(node._hmb_shot_slots, original_slots)
        self.assertEqual({p.name:node.parameter_values.get(p.name) for p in body}, original_native)
    def test_live_validated_catalog_automatically_enables_same_rows(self):
        node, _, body, rows, _, _, setter = self.exercise()
        node._refresh_routed_prompt_preview = Mock()
        with patch.object(module._BaseAgent, 'set_parameter_value', setter), patch.object(module._BaseAgent, 'after_value_set', lambda *a:None):
            node._hmb_layout_shot_editor(restored_catalog=catalog(2))
            before = [id(row) for row in rows]
            node._hmb_reconcile_shot_routing(catalog(2))
            self.assertEqual(node._hmb_restored_shot_row_catalog, {})
            self.assertTrue(all('routing_pending' not in node.parameter_values[row.name] for row in rows))
            self.assertEqual([id(row) for row in rows], before)
            self.assertEqual(node.parameter_values[rows[0].name]['shot']['shot_uuid'], 'shot-1')
        # The idempotent existing native-slot guard may run for the already
        # selected UUID; restoration must never choose a sibling/default slot.
        self.assertTrue(all(call.args == ('channel', 'shot-1')
                            for call in node._hmb_switch_native_slot.call_args_list))
    def test_real_source_removal_discards_presentation_fallback(self):
        node, _, _, rows, _, _, setter = self.exercise()
        node._set_native_prompt_preview = Mock()
        with patch.object(module._BaseAgent, 'set_parameter_value', setter), patch.object(module._BaseAgent, 'after_value_set', lambda *a:None):
            node._hmb_layout_shot_editor(restored_catalog=catalog(2))
            node._hmb_clear_shot_routing_catalog('publisher_unavailable')
            node._hmb_request_editor_layout()
            self.assertEqual(node._hmb_restored_shot_row_catalog, {})
            self.assertTrue(all(not node.parameter_values[row.name]['shot'] for row in rows))


if __name__ == '__main__': unittest.main(verbosity=2)
