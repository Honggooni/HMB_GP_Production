"""Prompt deferred edits retain their authority while exact ImageAsset media prepares."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBPromptLibrary as prompt


class Preparing(ValueError):
    hmb_image_asset_selection_preparing = True


class PickerPreparing(ValueError):
    hmb_picker_media_preparing = True


class DeferredLoop:
    def __init__(self):
        self.callbacks = []

    def is_running(self):
        return True

    def call_soon_threadsafe(self, callback):
        self.callbacks.append(callback)

    def call_later(self, delay, callback):
        self.callbacks.append(callback)

    def drain(self):
        while self.callbacks:
            self.callbacks.pop(0)()


class PromptImagePreparationTests(unittest.TestCase):
    pending_type = Preparing

    def setUp(self):
        self.loop = DeferredLoop()
        host = ModuleType('griptape_nodes.retained_mode.griptape_nodes')
        host.GriptapeNodes = SimpleNamespace(EventManager=lambda: SimpleNamespace(event_loop=self.loop))
        self.host = patch.dict(sys.modules, {'griptape_nodes.retained_mode.griptape_nodes': host})
        self.host.start()
        self.addCleanup(self.host.stop)
        self.node = object.__new__(prompt.HMBPromptLibrary)
        self.node._hmb_node_deleted = False
        self.node._hmb_sync_lock = threading.RLock()
        self.node._hmb_sync_generation = 0
        self.node._hmb_sync_queued_token = None
        self.node._hmb_sync_queued_source_burst = False
        self.node._hmb_sync_publish_shot_media_pending = False
        self.authored = {'text': '{{USER}} 한글 원문', 'project': 'ProjectA', 'shot': 'Shot1'}
        self.last_pair = {'visible': 'old visible', 'machine': 'old machine', 'media': ['old.png']}
        self.node.parameter_output_values = copy.deepcopy(self.last_pair)
        self.pending = True
        self.calls = []
        self.error = self.pending_type('Exact media source publication is still preparing.')
        self.node._current_state = lambda: copy.deepcopy(self.authored)

        def sync(**kwargs):
            if self.pending:
                raise self.error
            state = copy.deepcopy(self.authored)
            self.calls.append((state, kwargs))
            self.node.parameter_output_values = {'visible': state['text'], 'machine': str(state),
                                                'media': [state['project'] + '.png'] if state['project'] else []}
            return state

        self.node._sync_prompt_output_from_state = sync
        self.diagnostics = patch.object(prompt, '_diagnostic_exception')
        self.diag = self.diagnostics.start()
        self.addCleanup(self.diagnostics.stop)

    def test_pending_keeps_inputs_pair_and_media_intent_then_publishes_latest_edit(self):
        self.node._schedule_prompt_sync(source_burst=True, publish_shot_media=True)
        self.loop.drain()
        self.assertEqual(self.node.parameter_output_values, self.last_pair)
        self.assertTrue(self.node._hmb_sync_publish_shot_media_pending)
        self.assertEqual(self.authored['text'], '{{USER}} 한글 원문')
        self.assertEqual(self.calls, [])
        self.diag.assert_not_called()
        self.authored.update(text='최종 {{USER}}', project='ProjectB', shot='Shot2')
        self.node._schedule_prompt_sync()
        self.loop.drain()
        self.assertEqual(self.node.parameter_output_values, self.last_pair)
        self.pending = False
        self.node._schedule_prompt_sync(source_burst=True)
        self.loop.drain()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], self.authored)
        self.assertTrue(self.calls[0][1]['publish_shot_media'])
        self.assertEqual(self.node.parameter_output_values['media'], ['ProjectB.png'])
        self.assertFalse(self.node._hmb_sync_publish_shot_media_pending)

    def test_new_project_blank_never_restores_previous_selection_or_text(self):
        self.node._schedule_prompt_sync(source_burst=True, publish_shot_media=True)
        self.loop.drain()
        self.authored.update(project='', shot='', text='새 프로젝트 원문 유지')
        # A local edit supersedes the delayed completion callback. Both read
        # current authority, so the old source event cannot restore ProjectA.
        self.node._schedule_prompt_sync(source_burst=True)
        self.node._schedule_prompt_sync()
        self.pending = False
        self.loop.drain()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], self.authored)
        self.assertEqual(self.node.parameter_output_values['media'], [])
        self.assertEqual(self.node.parameter_output_values['visible'], '새 프로젝트 원문 유지')
        self.diag.assert_not_called()

    def test_explicit_run_propagates_pending_instead_of_using_old_pair(self):
        with self.assertRaises(self.pending_type):
            self.node._sync_prompt_output_now()
        self.assertEqual(self.node.parameter_output_values, self.last_pair)
        self.assertEqual(self.calls, [])

    def test_regular_value_error_and_non_value_marker_errors_still_report(self):
        for error in (ValueError('schema invalid'), RuntimeError('owner lost')):
            error.hmb_image_asset_selection_preparing = not isinstance(error, ValueError)
            error.hmb_picker_media_preparing = not isinstance(error, ValueError)
            self.error = error
            self.node._schedule_prompt_sync()
            self.loop.drain()
            self.assertIs(self.diag.call_args.args[1], error)
        self.assertEqual(self.diag.call_count, 2)

    def test_deleted_node_does_not_rearm_pending_or_publish(self):
        self.node._schedule_prompt_sync(publish_shot_media=True)
        self.node._hmb_node_deleted = True
        self.loop.drain()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.node.parameter_output_values, self.last_pair)


class PromptPickerPreparationTests(PromptImagePreparationTests):
    pending_type = PickerPreparing


if __name__ == '__main__':
    unittest.main(verbosity=2)
