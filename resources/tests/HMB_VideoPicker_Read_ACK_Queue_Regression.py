"""Shot-local READ transport/queue contract; no DCC, network, or Desktop."""
from __future__ import annotations
import copy
from contextvars import ContextVar
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker

SHOTS = [f'11111111-1111-4111-8111-{index:012d}' for index in range(1, 6)]
BOUND = [f'22222222-2222-4222-8222-{index:012d}' for index in range(1, 6)]


class ReadQueueRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hmb-read-ack-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.scene = self.base / 'shared.mb'
        self.scene.write_bytes(b'private scene identity, never run')
        self.patches = patch.object(picker, '_request_parameter_value', return_value=False)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.node = picker.HMBVideoPickerLibrary(name='Read ACK Fixture')
        self.node._schedule_missing_video_thumbnail_recovery = lambda: None
        self.node._sync_outputs_from_state = lambda *_a, **_k: None
        self.node._reconcile_shared_shot_routing = lambda: None
        no_dcc = patch.object(self.node, '_read_scene_mode', side_effect=RuntimeError('Private fixture has no DCC'))
        no_dcc.start()
        self.addCleanup(no_dcc.stop)
        diagnostics = patch.object(picker, '_picker_diagnostic_path', return_value=self.base / 'diagnostic.txt')
        diagnostics.start()
        self.addCleanup(diagnostics.stop)
        state = picker._default_widget_state()
        state['picker_shots'] = [picker._new_picker_workspace_row(index, workspace_uuid=shot, bound_shot_uuid=bound)
                                for index, (shot, bound) in enumerate(zip(SHOTS, BOUND), 1)]
        state['active_picker_shot_uuid'] = SHOTS[0]
        for index, shot in enumerate(SHOTS, 1):
            path = self.base / f'preserved-{index}.mp4'
            path.write_bytes(f'original-{index}'.encode())
            state = picker._append_video_asset(state, {'video_uid': f'old-{index}', 'source_uid': f'old-{index}',
                'video_path': str(path), 'generation_role': 'mask'}, picker_shot_uuid=shot, defer_thumbnail=True)
        self.node._write_state(state)

    def command(self, index, action_id=None):
        return {'schema':'hmb-picker-command', 'version':1, 'runtime_instance_id':self.node._hmb_runtime_instance_id,
                'action':'read_scene', 'action_id':action_id or f'read-{index}',
                'payload':{'picker_shot_uuid':SHOTS[index - 1], 'scene_path':str(self.scene)}}

    def receipts(self):
        return self.node._picker_state()['read_requests_by_shot']

    def media(self):
        state = self.node._picker_state()
        return {'videos': [(row['video_uid'], row['picker_shot_uuid'], row['video_path']) for row in state['videos']],
                'rows': [(row['workspace_uuid'],row['bound_shot_uuid'],row['video_asset_uids']) for row in state['picker_shots']]}

    def test_json_string_command_extracted_once_and_never_serialized(self):
        for stringify in (False, True):
            scheduled = []
            self.node._schedule_action_worker = lambda *args: scheduled.append(args)
            command = self.command(2, 'json-' + str(stringify))
            value = {**self.node._picker_state(), picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD:command}
            parameter = picker._get_parameter_obj(self.node, picker.WIDGET_STATE_PARAMETER)
            accepted = self.node.before_value_set(parameter, json.dumps(value) if stringify else value)
            self.assertNotIn(picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD, accepted)
            self.node._store_initial_parameter_value(picker.WIDGET_STATE_PARAMETER, accepted)
            self.node.after_value_set(parameter, accepted)
            self.assertEqual(len(scheduled), 1)
            self.assertEqual(scheduled[0][:2], ('read_scene', command['action_id']))
            self.assertEqual(self.node._hmb_embedded_command_queue, [])

    def test_filesystem_wait_does_not_block_other_shot_acks_and_queue_is_bounded(self):
        entered, release = threading.Event(), threading.Event()
        original_norm = picker._norm_path
        read_order = []
        before = self.media()
        def blocked(value):
            if not entered.is_set():
                entered.set()
                if not release.wait(5): raise RuntimeError('private fixture release missing')
            return original_norm(value)
        def fake_read(scene, context=None):
            read_order.append(context.picker_shot_uuid)
            state = self.node._picker_state_for_operation(context)
            state.update(status='OUTLINER_READY',scene_stage='OUTLINER_READY',native_read_ready=True,
                         message='Fixture read complete', selected_camera='camera-' + context.picker_shot_uuid,
                         start_frame=101, end_frame=105, current_frame=101, source_fps=24)
            self.node._write_state(state)
        with patch.object(picker, '_norm_path', side_effect=blocked), patch.object(self.node, '_read_scene_mode', side_effect=fake_read):
            worker=threading.Thread(target=self.node._handle_picker_command,args=(self.command(1),))
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.receipts()[SHOTS[0]]['status'], 'running')
                self.assertEqual(self.node._picker_state()['backend_ack_action_id'], 'read-1')
                timings=[]
                for index in range(2,6):
                    started=time.perf_counter()
                    self.node._handle_picker_command(self.command(index))
                    timings.append(time.perf_counter()-started)
                    self.assertEqual(self.receipts()[SHOTS[index-1]]['status'],'queued')
                self.assertLess(max(timings), 0.5)
                self.assertEqual(len(self.node._hmb_read_queue),4)
                self.assertEqual(read_order,[])
                self.node._handle_picker_command(self.command(2,'duplicate-2'))
                self.assertEqual(len(self.node._hmb_read_queue),4)
                self.assertEqual(self.receipts()[SHOTS[1]]['action_id'],'duplicate-2')
                cancel = self.command(3,'cancel-3')
                cancel['action']='stop_read'
                self.node._handle_picker_command(cancel)
                self.assertEqual(self.receipts()[SHOTS[2]]['status'],'cancelled')
                cancel['action_id']='cancel-3-repeat'
                self.node._handle_picker_command(cancel)
                self.assertFalse(self.node._hmb_cancel_requested.is_set(), 'Repeated STOP must not cancel another Shot')
                stale_cancel=self.command(2,'stale-cancel-2')
                stale_cancel['action']='stop_read'
                stale_cancel['payload']['target_action_id']='retired-request'
                self.node._handle_picker_command(stale_cancel)
                self.assertEqual(self.receipts()[SHOTS[1]]['status'],'queued')
                state=self.node._picker_state()
                next(row for row in state['picker_shots'] if row['workspace_uuid']==SHOTS[3])['bound_shot_uuid']='33333333-3333-4333-8333-333333333333'
                self.node._write_state(state)
                self.assertEqual(next(row for row in self.node._picker_state()['picker_shots'] if row['workspace_uuid']==SHOTS[3])['bound_shot_uuid'],'33333333-3333-4333-8333-333333333333')
            finally:
                release.set()
                worker.join(8)
            self.assertFalse(worker.is_alive())
        self.assertEqual(read_order,[SHOTS[0],SHOTS[1],SHOTS[4]])
        self.assertEqual([self.receipts()[shot]['status'] for shot in SHOTS],['complete','complete','cancelled','cancelled','complete'])
        self.assertFalse(self.node._hmb_read_queue_running)
        self.assertFalse(self.node._hmb_process_lock.locked())
        self.assertEqual(self.media()['videos'],before['videos'])
        self.assertEqual([row[2] for row in self.media()['rows']],[row[2] for row in before['rows']])
        for index in range(1,6):
            self.assertEqual((self.base/f'preserved-{index}.mp4').read_bytes(),f'original-{index}'.encode())

    def test_missing_scene_has_failed_receipt_and_next_read_is_not_locked(self):
        missing=self.command(1)
        missing['payload']['scene_path']=str(self.base/'absent.mb')
        self.node._handle_picker_command(missing)
        self.assertEqual(self.receipts()[SHOTS[0]]['status'],'failed')
        self.assertFalse(self.node._hmb_read_queue_running)
        self.assertFalse(self.node._hmb_process_lock.locked())
        self.assertEqual(self.node._picker_state()['backend_ack_action_id'],'read-1')
        self.node._handle_picker_command(self.command(2))
        self.assertNotEqual(self.receipts()[SHOTS[1]]['status'],'queued')

    def test_saved_receipts_and_embedded_actions_are_not_replayed(self):
        state=self.node._picker_state()
        state['read_requests_by_shot']={SHOTS[0]:{'action_id':'retired','status':'queued'}}
        state[picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD]=self.command(1)
        recovered, changed=picker._recover_orphaned_runtime_state(state)
        self.assertTrue(changed)
        self.assertNotIn('read_requests_by_shot',recovered)
        self.assertNotIn(picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD,recovered)

    def test_native_worker_preserves_callers_contextvars(self):
        marker=ContextVar('picker-fixture-workflow', default='lost')
        completed=threading.Event()
        observed=[]
        token=marker.set('captured-workflow')
        try:
            self.node._schedule_action_worker('clear_log','context-fixture',lambda:(observed.append(marker.get()),completed.set()))
        finally:
            marker.reset(token)
        self.assertTrue(completed.wait(3))
        self.assertEqual(observed,['captured-workflow'])

    def test_receipt_publication_failure_releases_queue_without_starting_dcc(self):
        with patch.object(self.node, '_write_state', side_effect=RuntimeError('private publication failure')):
            with self.assertRaisesRegex(RuntimeError,'private publication failure'):
                self.node._handle_picker_command(self.command(1))
        self.assertFalse(self.node._hmb_read_queue_running)
        self.assertEqual(self.node._hmb_read_queue,[])
        self.assertEqual(self.node._hmb_read_requests[SHOTS[0]]['status'],'failed')
        self.assertFalse(self.node._hmb_process_lock.locked())


if __name__ == '__main__': unittest.main(verbosity=2)
