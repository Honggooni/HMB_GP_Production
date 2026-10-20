"""Native publication failures cannot retain the Picker worker reservation.

Reuses the existing progressive-generation contract fixture. Only validated
role production is synthetic; the real operation worker, state serialization,
retained publication error propagation and terminal catalog commit execute.
No Maya, Blender, FFmpeg, Broker or paid generation runs.
"""
from __future__ import annotations

from contextlib import ExitStack
import inspect
from pathlib import Path
import socket
import sys
import threading
import unittest
import uuid
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
import HMB_VideoPicker_Progressive_Selected_Generation_Regression as fixture

picker = fixture.picker


class WorkerReservationResilience(unittest.TestCase):
    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        self.guards.enter_context(mock.patch.multiple(picker,
            _request_parameter_value=lambda *a, **k: False,
            _notify_parameter_update=lambda *a, **k: None,
            _propagate_parameter_update_to_connections=lambda *a, **k: None,
            _video_asset_thumbnail_url=lambda *a, **k: ('', ''),
            _external_media_url=lambda path: Path(path).resolve().as_uri()))
        self.guards.enter_context(mock.patch.object(socket, 'create_connection',
            side_effect=AssertionError('No network in reservation regression')))
        self.guards.enter_context(mock.patch.object(picker.subprocess, 'Popen',
            side_effect=AssertionError('No DCC/media subprocess in reservation regression')))
        self.diagnostics = self.guards.enter_context(mock.patch.object(picker, '_diagnostic_exception'))

    def case(self):
        return fixture.Scenario('reservation-' + uuid.uuid4().hex, roles=('mask',))

    def reserve(self, node):
        state = node._picker_state()
        action_id = 'private-reservation-' + uuid.uuid4().hex
        state['backend_ack_action_id'] = action_id
        node._hmb_pending_operation_id = action_id
        node._hmb_worker_thread = threading.current_thread()
        return state

    def assert_released(self, node):
        self.assertFalse(node._hmb_process_lock.locked())
        self.assertEqual(node._hmb_pending_operation_id, '')
        self.assertIsNone(node._hmb_worker_thread)
        self.assertIsNone(node._hmb_active_operation)
        # A different thread must be able to enter the catalog as well. An
        # RLock checked only by this same thread could hide leaked ownership.
        acquired = []
        def check():
            with node._hmb_catalog_state_commit():
                acquired.append(True)
        thread = threading.Thread(target=check, daemon=True)
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive(), 'Terminal catalog reservation leaked')
        self.assertEqual(acquired, [True])

    def assert_next_read_runs(self, case):
        node = case.node
        called = []
        node._read_scene_mode = lambda *a, **k: called.append(True)
        node._hmb_cancel_requested.clear()
        state = self.reserve(node)
        state.update(scene_path=str(case.scene), scene_request_path=str(case.scene))
        node._store_initial_parameter_value('MAYA_SCENE', str(case.scene))
        node._start_ui_operation('read_scene', state)
        self.assertEqual(called, [True])
        self.assert_released(node)

    def test_cancelled_worker_releases_when_native_state_publication_rejects(self):
        case = self.case()
        node = case.node
        state = self.reserve(node)
        node._hmb_cancel_requested.set()
        with mock.patch.object(picker, '_request_parameter_value',
                side_effect=RuntimeError('Native retained publication rejected')):
            with self.assertRaisesRegex(RuntimeError, 'Native retained publication'):
                node._start_ui_operation('read_scene', state)
        self.assert_released(node)
        self.assert_next_read_runs(case)

    def test_original_preflight_releases_when_failure_card_publication_rejects(self):
        case = self.case()
        node = case.node
        state = self.reserve(node)
        state.update(scene_path=str(case.root / 'missing.mb'),
            scene_request_path=str(case.root / 'missing.mb'))
        node._store_initial_parameter_value('MAYA_SCENE', state['scene_path'])
        with mock.patch.object(picker, '_request_parameter_value',
                side_effect=RuntimeError('Native retained publication rejected')):
            with self.assertRaisesRegex(RuntimeError, 'Native retained publication'):
                node._start_ui_operation('render_original_preview', state)
        self.assert_released(node)
        self.assert_next_read_runs(case)

    def test_clear_process_card_failure_preserves_completed_mask_and_releases(self):
        case = self.case()
        node = case.node
        produce, clear = node._maya_mode, node._clear_active_process
        def produce_with_process_card(*args, **kwargs):
            result = produce(*args, **kwargs)
            state = node._picker_state()
            state.update(active_process_pid=123, active_process_kind='synthetic-completed-worker')
            node._write_state(state)
            return result
        def rejected_clear(process=None):
            with mock.patch.object(picker, '_request_parameter_value',
                    side_effect=RuntimeError('Native retained publication rejected')):
                return clear(process)
        node._maya_mode = produce_with_process_card
        node._clear_active_process = rejected_clear
        state = self.reserve(node)
        node._start_ui_operation('run_video', state)
        self.assert_released(node)
        result = node._picker_state()
        self.assertEqual(result['status'], 'VIDEO_READY')
        self.assertEqual(result['generation_output_roles'], ['mask'])
        self.assertEqual(len(result['videos']), 1)
        self.assertTrue(Path(result['videos'][0]['video_path']).is_file())
        self.assertEqual(node.parameter_output_values['VIDEO_OUT'], [result['videos'][0]['video_path']])
        self.assertTrue(self.diagnostics.called)
        node._clear_active_process = clear
        self.assert_next_read_runs(case)

    def test_terminal_catalog_rejection_releases_both_reservations(self):
        case = self.case()
        node = case.node
        state = self.reserve(node)
        rejected = []
        def publish(*args, **kwargs):
            if not rejected and any(frame.function == '_commit_generate_terminal_state'
                    for frame in inspect.stack(context=0)):
                rejected.append(True)
                raise RuntimeError('Native terminal catalog publication rejected')
            return False
        with mock.patch.object(picker, '_request_parameter_value', side_effect=publish):
            node._start_ui_operation('run_video', state)
        self.assertEqual(rejected, [True])
        self.assert_released(node)
        self.assert_next_read_runs(case)

    def test_queued_scene_is_applied_after_reservation_release_even_on_cancel_error(self):
        case = self.case()
        node = case.node
        state = self.reserve(node)
        node._hmb_cancel_requested.set()
        pending = (str(case.scene), 'private queued selection')
        node._hmb_pending_scene_selection = pending
        observed = []
        def schedule(*args):
            self.assertFalse(node._hmb_process_lock.locked())
            self.assertEqual(node._hmb_pending_operation_id, '')
            observed.append(args)
        node._schedule_scene_selection = schedule
        with mock.patch.object(picker, '_request_parameter_value',
                side_effect=RuntimeError('Native retained publication rejected')):
            with self.assertRaises(RuntimeError):
                node._start_ui_operation('read_scene', state)
        self.assertEqual(observed, [pending])
        self.assertIsNone(node._hmb_pending_scene_selection)
        self.assert_released(node)

    def test_terminal_base_exception_releases_catalog_and_worker(self):
        class InterruptedTerminal(BaseException):
            pass
        case = self.case()
        node = case.node
        state = self.reserve(node)
        def publish(*args, **kwargs):
            if any(frame.function == '_commit_generate_terminal_state'
                    for frame in inspect.stack(context=0)):
                raise InterruptedTerminal('Interrupted terminal publication')
            return False
        with mock.patch.object(picker, '_request_parameter_value', side_effect=publish):
            with self.assertRaises(InterruptedTerminal):
                node._start_ui_operation('run_video', state)
        self.assert_released(node)
        self.assert_next_read_runs(case)


if __name__ == '__main__':
    unittest.main()
