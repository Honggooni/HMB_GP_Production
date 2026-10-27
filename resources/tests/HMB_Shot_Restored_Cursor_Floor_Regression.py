"""Numeric legacy cursor recovery cannot grant saved catalog authority."""
from __future__ import annotations
from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_shot_routing as routing


class Node:
    def __init__(self, name, kind, *, channel='channel', enabled=True, state=None):
        self.name, self.kind, self.channel, self.enabled = name, kind, channel, enabled
        self.state = deepcopy(state or {})
    def _hmb_shot_channel_subscription(self):
        return dict(schema=routing.SUBSCRIPTION_SCHEMA, version=1, participant_kind=self.kind,
            enabled=self.enabled, channel_uuid=self.channel, shot_uuid='shot', shot_number=1, shot_name='Shot')
    def _current_state(self): return deepcopy(self.state)
    def get_parameter_value(self, _name): return deepcopy(self.state)


class CursorFloor(unittest.TestCase):
    def setUp(self):
        self.source = Node('source', 'image_asset', state={'shot_routing':dict(publisher_instance_uuid='publisher', channel_uuid='channel')})
        self.catalog = dict(publisher_instance_uuid='publisher', channel_uuid='channel', generation=2,
            shots=[{'untrusted_saved_content':'never consumed'}], metadata_sha256='not-authority')
        self.picker = Node('picker', 'video_picker', state=dict(
            accepted_shot_catalog_publisher_instance_uuid='publisher', accepted_shot_catalog_channel_uuid='channel',
            accepted_shot_catalog_generation=2))
        self.nodes = [self.source, self.picker]
        self.guard = patch.object(routing, '_same_flow_nodes', lambda node: ('flow', self.nodes) if node is self.source else ('', []))
        self.guard.start()
    def tearDown(self): self.guard.stop()
    def floor(self, generation=1, **kw):
        return routing.restored_shot_catalog_generation_floor(self.source,
            publisher_instance_uuid=kw.get('publisher', 'publisher'), channel_uuid=kw.get('channel', 'channel'), current_generation=generation)
    def test_matching_picker_numeric_watermark_only(self):
        before = deepcopy(self.picker.state)
        self.assertEqual(self.floor(), 2)
        self.assertEqual(self.picker.state, before)
        self.assertFalse(hasattr(self.source, '_hmb_shot_catalog_snapshot'))
    def test_healthy_cursor_does_not_advance(self): self.assertEqual(self.floor(2), 2)
    def test_all_three_other_durable_watermark_shapes(self):
        self.nodes = [self.source]
        for kind, value in [('agent', {'shot_catalog':self.catalog}), ('finish_look', {'shot_catalog':self.catalog}),
                            ('prompt', {'image_asset':{'shot_catalog_routing':self.catalog}})]:
            with self.subTest(kind=kind):
                self.nodes = [self.source, Node(kind, kind, state=value)]
                self.assertEqual(self.floor(), 2)
    def test_different_channel_publisher_and_only_are_ignored(self):
        for change in ({'accepted_shot_catalog_channel_uuid':'other'}, {'accepted_shot_catalog_publisher_instance_uuid':'other'}):
            with self.subTest(change=change):
                old = deepcopy(self.picker.state); self.picker.state.update(change)
                self.assertEqual(self.floor(), 1); self.picker.state = old
        self.picker.enabled = False
        self.assertEqual(self.floor(), 1)
        self.picker.enabled = True; self.picker.channel = 'other'
        self.assertEqual(self.floor(), 1)
    def test_deleted_candidate_and_source_cannot_supply_cursor(self):
        self.picker._hmb_node_deleted = True
        self.assertEqual(self.floor(), 1)
        self.picker._hmb_node_deleted = False; self.source._hmb_node_deleted = True
        self.assertEqual(self.floor(), 1)
    def test_foreign_flow_or_unregistered_publisher_is_ignored(self):
        with patch.object(routing, '_same_flow_nodes', return_value=('', [])):
            self.assertEqual(self.floor(), 1)
        self.assertEqual(self.floor(publisher='other'), 1)
        self.assertEqual(self.floor(channel='other'), 1)
    def test_safe_integer_bounds_are_exact(self):
        for value in [True, False, 2.0, '2', None, 0, -1, 1 << 53]:
            with self.subTest(value=value):
                self.picker.state['accepted_shot_catalog_generation'] = value
                self.assertEqual(self.floor(), 1)
        self.picker.state['accepted_shot_catalog_generation'] = (1 << 53) - 1
        self.assertEqual(self.floor(), (1 << 53) - 1)
    def test_source_identity_not_proven_by_subscriber_alone(self):
        self.source.state['shot_routing']['publisher_instance_uuid'] = 'new-publisher'
        self.assertEqual(self.floor(), 1)
    def test_rich_media_generation_is_not_a_catalog_cursor(self):
        self.nodes = [self.source, Node('prompt', 'prompt', state={'image_asset':{
            'shot_catalog_routing':self.catalog, 'shot_routing':{**self.catalog, 'generation':6120}}})]
        self.assertEqual(self.floor(), 2)
    def test_cleanup_pass_never_consumes_a_pending_restore(self):
        self.nodes = [self.source]
        self.source._hmb_publication_cursor_restore_pending = True
        from unittest.mock import Mock
        restore = self.source._hmb_restore_publication_cursor = Mock(side_effect=RuntimeError('restore sentinel'))
        with patch.object(routing, '_claim_routing_flow', lambda *a:nullcontext(True)), \
                patch.object(routing, '_flow_migration_blockage', return_value=None), \
                patch.object(routing, '_flow_migration_is_pending', return_value=False):
            result = routing.reconcile_shot_routing(self.source)
            self.assertEqual(result['code'], 'incomplete')
            restore.assert_called_once()
            restore.reset_mock()
            routing.reconcile_shot_routing(self.source, _allow_unready_cleanup=True)
            restore.assert_not_called()
            self.assertTrue(self.source._hmb_publication_cursor_restore_pending)


if __name__ == '__main__': unittest.main(verbosity=2)
