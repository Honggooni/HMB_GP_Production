"""Original/direct versus explicit grade-and-upload; no provider or live uploads."""
import copy,hashlib,sys,threading,unittest
from pathlib import Path
from unittest import mock
sys.path[:0]=[str(Path(__file__).parents[2]),str(Path(__file__).parent)]
import HMB_Color_LUT_Manual_Upload_Regression as fixture
import HMBColorLUTLibrary as target

class DirectUploadRegression(fixture.ManualLUTRegression):
    def test_original_upload_without_export_uses_original_bytes_and_neutral_settings(self):
        state=self.node._hmb_color_lut_state
        state['result']={};state['settings'].update(enabled=True,exposure=.5)
        self.node._web_upload_context={};self.node._web_upload_probe_key=''
        with mock.patch.object(target,'export_video',side_effect=AssertionError('No encoding')):
            self.node._schedule_upload_probe();self.fixture.drain()
            self.assertTrue(self.node._upload_projection()['enabled'])
            context=self.ready()
            with mock.patch.object(self.node,'_upload_request',side_effect=lambda c,**kw:self.ack(c)) as sent:
                self.upload()
        captured=sent.call_args.args[0]
        self.assertEqual(captured['path'],state['source']['path'])
        self.assertEqual(captured['settings'],target.default_settings())
        self.assertEqual(captured['sha256'],hashlib.sha256(Path(state['source']['path']).read_bytes()).hexdigest())
        self.assertNotIn('usage_event',captured)
        self.assertEqual(state['result'],{})

    def test_server_advertised_mybox_selects_and_survives_reopen(self):
        rows=[*fixture.PROJECTS,{'id':'my-box','name':'My Box'}]
        with mock.patch.object(fixture,'PROJECTS',rows):
            self.node._manual_projects=copy.deepcopy(rows)
            self.choose('my-box');context=self.ready()
            self.assertEqual(context['project_id'],'my-box')
            saved=copy.deepcopy(self.node._hmb_color_lut_state)
            restored=target.HMBColorLUTLibrary(name='Restored My Box')
            restored._apply_ui(saved,initial_setup=True)
            self.assertEqual(restored._hmb_color_lut_state['manual_project'],rows[-1])
            with mock.patch.object(self.node,'_upload_request',side_effect=lambda c,**kw:{**self.ack(c),'derived_task_id':'job-mybox-'+'d'*32}):
                self.upload('private-upload')
            self.assertEqual(self.node._web_upload['phase'],'complete')

    def chain(self,identity):
        self.node._command({'id':identity,'action':'export_upload','state':copy.deepcopy(self.node._hmb_color_lut_state)})
        self.fixture.drain()

    def test_explicit_output_then_upload_runs_once_and_keeps_original(self):
        state=self.node._hmb_color_lut_state
        original=Path(state['source']['path']).read_bytes();state['result']={}
        state['settings'].update(enabled=True,exposure=.5)
        with mock.patch.object(target,'export_video',side_effect=self.fixture.successful_export) as encoded, \
             mock.patch.object(self.node,'_upload_request',side_effect=lambda c,**kw:self.ack(c)) as sent:
            self.chain('grade-and-upload')
            self.chain('repeat-frozen-export')
        self.assertEqual(encoded.call_count,1)
        self.assertEqual(sent.call_count,1)
        self.assertEqual(sent.call_args.args[0]['artifact'],'export')
        self.assertNotEqual(sent.call_args.args[0]['path'],state['source']['path'])
        self.assertEqual(sent.call_args.args[0]['settings'],state['settings'])
        self.assertEqual(Path(state['source']['path']).read_bytes(),original)
        self.assertTrue(Path(state['result']['path']).is_file())
        self.assertEqual(state['status']['phase'],'complete')

    def test_output_unknown_retries_same_export_with_get_only(self):
        self.node._hmb_color_lut_state['result']={};calls=[]
        def transport(c,*,retrieve,cancel):
            calls.append((c['upload_id'],retrieve,c['path']))
            if not retrieve:raise TimeoutError('response lost')
            return self.ack(c)
        with mock.patch.object(target,'export_video',side_effect=self.fixture.successful_export) as encoded, \
             mock.patch.object(self.node,'_upload_request',side_effect=transport):
            self.chain('first-export');self.chain('retrieve-export')
        self.assertEqual(encoded.call_count,1)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][0],calls[1][0]);self.assertEqual(calls[0][2],calls[1][2])
        self.assertEqual([c[1] for c in calls],[False,True])
        self.assertEqual(self.node._hmb_color_lut_state['status']['phase'],'complete')

    def test_source_project_settings_cancel_or_delete_during_export_never_auto_uploads(self):
        for change in ('project','settings','source','cancel','delete'):
            with self.subTest(change=change):
                self.node._hmb_node_deleted=False;self.choose('superwings12')
                self.node._hmb_color_lut_state['result']={}
                def encode(*args,**kw):
                    result=self.fixture.successful_export(*args,**kw)
                    if change=='project':self.choose('katuri8')
                    if change=='settings':self.node._hmb_color_lut_state['settings']['exposure']+=.25
                    if change=='source':self.node._source_token+=1
                    if change=='cancel':self.node._cancel.set()
                    if change=='delete':self.node._hmb_node_deleted=True
                    return result
                with mock.patch.object(target,'export_video',side_effect=encode) as encoded,mock.patch.object(self.node,'_upload_request') as sent:
                    self.chain('changed-'+change);sent.assert_not_called();self.assertEqual(encoded.call_count,1)

    def test_changed_output_codec_or_path_never_reuses_previous_export(self):
        state=self.node._hmb_color_lut_state
        with mock.patch.object(target,'export_video',side_effect=self.fixture.successful_export) as encoded, \
             mock.patch.object(self.node,'_upload_request',side_effect=lambda c,**kw:self.ack(c)):
            state['result']={};self.chain('first')
            state['output']['codec']='prores';self.chain('new-codec')
            state['output'].update(manual_output_enabled=True,path=str(self.root/'new-destination.mov'))
            self.chain('new-destination')
        self.assertEqual(encoded.call_count,3)
        self.assertEqual(state['result']['path'],str(self.root/'new-destination.mov'))

    def test_export_without_destination_stays_local(self):
        self.choose('');self.node._hmb_color_lut_state['result']={}
        with mock.patch.object(target,'export_video',side_effect=self.fixture.successful_export),mock.patch.object(self.node,'_upload_request') as sent:
            self.node._command({'id':'local-only','action':'export','state':copy.deepcopy(self.node._hmb_color_lut_state)})
            self.fixture.drain();sent.assert_not_called()
        self.assertTrue(Path(self.node._hmb_color_lut_state['result']['path']).is_file())

if __name__=='__main__':unittest.main(verbosity=2)
