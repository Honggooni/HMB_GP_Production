"""Real retained SDK initial_setup boundary for saved Color LUT authoring.

Requires the installed SDK. No media probe, export, command, model, live graph
or user configuration is used. The inherited SDK setter really suppresses
after_value_set for initial_setup, reproducing saved-workflow restoration.
"""
from __future__ import annotations
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT=Path(os.environ.get('HMB_COLOR_LUT_TEST_ROOT',str(Path(__file__).resolve().parents[2])))
sys.path.insert(0,str(ROOT))
import HMBColorLUTLibrary as target
import _hmb_shot_routing as routing
from griptape_nodes.retained_mode.engine import engine_scope
from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest

CHANNEL='11111111-1111-4111-8111-111111111111'
SHOTS=[dict(shot_uuid=f'33333333-3333-4333-8333-{n:012d}',number=n,name=f'Authored {n}',revision=1) for n in range(1,6)]
document=dict(channel_uuid=CHANNEL,generation=1,shots=SHOTS)
CATALOG=dict(schema='hmb-shot-routing-catalog',version=1,publisher_instance_uuid='22222222-2222-4222-8222-222222222222',
    **document,metadata_sha256=hashlib.sha256(json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())

def saved_state():
    state=target.default_state()
    state.update(project_id='project-A',project={'id':'project-A','name':'A'},shot_catalog=copy.deepcopy(CATALOG),revision=20)
    for shot in SHOTS:
        state['shot']={'channel_uuid':CHANNEL,**{k:shot[k] for k in ('shot_uuid','number','name')}}
        state['settings']={**target.default_settings(),'enabled':True,'exposure':shot['number']*.25,'temperature':-.75}
        state['output']={'codec':'hevc10','manual_output_enabled':True,'path':f'C:/synthetic-lut-{shot["number"]}.mov'}
        state['preset_name']=f'Grade {shot["number"]}'
        state['shot_states'][target._selection_key(state)]={k:copy.deepcopy(state[k]) for k in ('settings','output','source','result','preset_name')}
    return state

class ColorLUTHydrationLifecycle(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='hmb-lut-hydration-native-');self.addCleanup(temporary.cleanup)
        self.addCleanup(logging.shutdown)
        folder=Path(temporary.name)
        patch=mock.patch.dict(os.environ,{key:str(folder/key) for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','LOCALAPPDATA','APPDATA')})
        patch.start();self.addCleanup(patch.stop)
        logging.disable(logging.CRITICAL)
        scope=engine_scope();self.engine=scope.__enter__();self.addCleanup(scope.__exit__,None,None,None)
        self.engine.event_manager.initialize_queue()
        ensured=self.engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name='ColorLUTHydration'))
        self.assertTrue(ensured.succeeded(),str(ensured.result_details))
        self.flow=self.engine.flow_manager.get_flow_by_name(ensured.flow_name)
        for name in ('schedule_post_registration_reconcile','schedule_post_hydration_reconcile','reconcile_shot_routing'):
            patch=mock.patch.object(routing,name);patch.start();self.addCleanup(patch.stop)
        self.node=target.HMBColorLUTLibrary(name='Saved Color LUT')
        self.flow.add_node(self.node);self.engine.object_manager.add_object_by_name(self.node.name,self.node)
        self.engine.node_manager._name_to_parent_flow_name[self.node.name]=self.flow.name
        self.publish=mock.patch.object(self.node,'publish_update_to_parameter');self.publisher=self.publish.start();self.addCleanup(self.publish.stop)
        self.queue=mock.patch.object(self.node,'_queue_source');self.queued=self.queue.start();self.addCleanup(self.queue.stop)
        self.command=mock.patch.object(self.node,'_command');self.commands=self.command.start();self.addCleanup(self.command.stop)

    def send(self,value,*,initial=True,parameter=target.UI):
        result=self.engine.handle_request(SetParameterValueRequest(node_name=self.node.name,parameter_name=parameter,value=copy.deepcopy(value),initial_setup=initial,broadcast_result=False))
        self.assertTrue(result.succeeded(),str(result.result_details))

    def select(self,shot):
        value=copy.deepcopy(self.node.get_parameter_value(target.UI));value.pop('shot_states',None)
        value['revision']+=1;value['shot']={'channel_uuid':CHANNEL,**shot}
        self.send(value,initial=False)

    def test_initial_setup_restores_all_five_shot_grades_without_hook(self):
        state=saved_state()
        with mock.patch.object(self.node,'after_value_set',wraps=self.node.after_value_set) as hook:
            self.send(state)
            hook.assert_not_called()
        self.assertTrue(self.node._hydrated)
        self.publisher.assert_not_called();self.queued.assert_not_called();self.commands.assert_not_called()
        self.assertEqual(self.node._hmb_color_lut_state['project_id'],'project-A')
        for shot in reversed(SHOTS):
            self.select(shot)
            self.assertEqual(self.node._hmb_color_lut_state['settings']['exposure'],shot['number']*.25)
            self.assertEqual(self.node._hmb_color_lut_state['preset_name'],f'Grade {shot["number"]}')
            self.assertEqual(self.node._hmb_color_lut_state['output']['path'],f'C:/synthetic-lut-{shot["number"]}.mov')

    def test_repeated_native_hydration_preserves_slots(self):
        state=saved_state()
        self.send(state);self.send(state)
        self.assertEqual(len(self.node._hmb_color_lut_state['shot_states']),5)
        for shot in SHOTS:
            self.select(shot)
            self.assertEqual(self.node._hmb_color_lut_state['settings']['exposure'],shot['number']*.25)

    def test_native_hydration_never_replays_embedded_or_separate_command(self):
        state=saved_state();state['__hmb_color_lut_command__']={'id':'saved-command','action':'export','state':copy.deepcopy(state)}
        self.send(state);self.send(json.dumps({'id':'saved-command','action':'export'}),parameter=target.COMMAND)
        self.commands.assert_not_called();self.queued.assert_not_called();self.publisher.assert_not_called()
        self.assertNotIn('__hmb_color_lut_command__',self.node.get_parameter_value(target.UI))

    def test_authoritative_new_project_rejects_old_saved_ui(self):
        self.node._hmb_follow_image_asset_project({'id':'project-B','name':'B'})
        before=copy.deepcopy(self.node._hmb_color_lut_state)
        self.publisher.reset_mock();self.send(saved_state())
        self.assertEqual(self.node._hmb_color_lut_state['project_id'],'project-B')
        self.assertEqual(self.node.get_parameter_value(target.UI)['project_id'],'project-B')
        self.assertEqual(self.node._hmb_color_lut_state['settings'],before['settings'])
        self.assertFalse(any('project-A' in key for key in self.node._hmb_color_lut_state['shot_states']))
        self.publisher.assert_not_called();self.commands.assert_not_called()

    def test_restored_foreign_shot_source_and_result_are_not_adopted(self):
        state=saved_state();state['source']={'path':'C:/foreign.mp4','channel_uuid':CHANNEL,'shot_uuid':SHOTS[0]['shot_uuid'],'completed':True}
        state['result']={'path':'C:/foreign-graded.mp4','url':'http://fixture.invalid/foreign'}
        self.send(state)
        self.assertEqual(self.node._hmb_color_lut_state['source'],{})
        self.assertEqual(self.node._hmb_color_lut_state['result'],{})
        self.assertEqual(self.node.get_parameter_value(target.UI)['source'],{})
        self.assertEqual(self.node.get_parameter_value(target.UI)['result'],{})
        self.queued.assert_not_called()

    def test_native_hydration_invalidates_older_shot_probe(self):
        self.node._source_token=17
        self.node._source_pending=(17,{'shot_uuid':SHOTS[0]['shot_uuid']},'C:/old-shot.mp4')
        self.node._pending_source_key=('old-shot',)
        self.node._restoring_source={'path':'C:/old-shot.mp4'}
        self.send(saved_state())
        self.assertGreater(self.node._source_token,17)
        self.assertIsNone(self.node._source_pending)
        self.assertIsNone(self.node._pending_source_key)
        self.assertEqual(self.node._restoring_source,{})
        self.assertEqual(self.node._hmb_color_lut_state['source'],{})
        self.queued.assert_not_called()

    def test_actual_late_probe_cannot_replace_restored_shot(self):
        self.node._hmb_follow_image_asset_project({'id':'project-A','name':'A'})
        self.node._hmb_prepare_initial_shot_selection(SHOTS[-1]['shot_uuid'])
        self.node._hmb_reconcile_shot_routing(copy.deepcopy(CATALOG))
        self.assertEqual(self.node._hmb_color_lut_state['shot']['shot_uuid'],SHOTS[-1]['shot_uuid'])
        entered=threading.Event();release=threading.Event()
        with tempfile.TemporaryDirectory(prefix='hmb-lut-late-probe-') as directory:
            media=Path(directory)/'prior-shot.mov';media.write_bytes(b'synthetic media-probe boundary')
            snapshot=dict(path=str(media),shot_uuid=SHOTS[-1]['shot_uuid'],channel_uuid=CHANNEL,completed=True)
            def probe(_path):
                entered.set()
                if not release.wait(3):raise AssertionError('Probe barrier timed out')
                return dict(path=str(media),frame_rate=24,width=96,height=64)
            worker=None
            with mock.patch.object(target,'probe_source',side_effect=probe),mock.patch.object(target,'_media_url',return_value='http://127.0.0.1/synthetic.mov'):
                try:
                    target.HMBColorLUTLibrary._queue_source(self.node,snapshot)
                    worker=self.node._source_worker;self.assertTrue(entered.wait(1))
                    state=saved_state();state['shot']={'channel_uuid':CHANNEL,**{k:SHOTS[0][k] for k in ('shot_uuid','number','name')}}
                    state.update(copy.deepcopy(state['shot_states'][target._selection_key(state)]))
                    self.send(state)
                finally:
                    release.set()
                    if worker:worker.join(3)
            self.assertFalse(worker and worker.is_alive())
            self.assertEqual(self.node._hmb_color_lut_state['shot']['shot_uuid'],SHOTS[0]['shot_uuid'])
            self.assertEqual(self.node._hmb_color_lut_state['source'],{})
            self.assertEqual(self.node._hmb_color_lut_state['settings']['exposure'],.25)

    def test_authoritative_project_rejects_empty_saved_project(self):
        self.node._hmb_follow_image_asset_project({'id':'project-B','name':'B'})
        before=copy.deepcopy(self.node._hmb_color_lut_state)
        self.publisher.reset_mock();self.send(target.default_state())
        self.assertEqual(self.node._hmb_color_lut_state,before)
        self.assertEqual(self.node.get_parameter_value(target.UI)['project_id'],'project-B')
        self.publisher.assert_not_called();self.commands.assert_not_called()

    def test_manual_only_source_is_deferred_until_registration_discovery(self):
        state=target.default_state();state['source']={'path':'C:/synthetic-manual.mov'}
        self.send(state);self.queued.assert_not_called()
        self.node._hmb_post_registration_shot_discovery()
        self.queued.assert_called_once_with(state['source'])

    def test_late_live_edit_from_prior_project_stays_rejected(self):
        state=saved_state();self.send(state)
        self.node._hmb_follow_image_asset_project({'id':'project-B','name':'B'})
        state.pop('shot_states');state['revision']=self.node._hmb_color_lut_state['revision']+100
        state['settings']['exposure']=2.0;self.send(state,initial=False)
        self.assertEqual(self.node._hmb_color_lut_state['project_id'],'project-B')
        self.assertEqual(self.node._hmb_color_lut_state['settings'],target.default_settings())
        self.commands.assert_not_called()

    def test_normal_native_edit_still_updates_authored_grade(self):
        self.send(saved_state())
        value=copy.deepcopy(self.node.get_parameter_value(target.UI));value.pop('shot_states',None)
        value['revision']+=1;value['settings']['exposure']=.75
        self.send(value,initial=False)
        self.assertEqual(self.node._hmb_color_lut_state['settings']['exposure'],.75)
        self.assertTrue(self.node._hmb_color_lut_state['settings']['enabled'])

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ColorLUTHydrationLifecycle)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful() and not result.skipped:print('HMB_COLOR_LUT_HYDRATION_LIFECYCLE=PASS (11 real native initial_setup regressions, synthetic blocked-probe boundary, no export/model execution)')
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
