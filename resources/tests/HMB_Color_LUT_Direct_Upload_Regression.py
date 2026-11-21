"""Original/direct versus explicit grade-and-upload; no provider or live uploads."""
import copy,hashlib,sys,threading,unittest
from pathlib import Path
from unittest import mock
sys.path[:0]=[str(Path(__file__).parents[2]),str(Path(__file__).parent)]
import HMB_Color_LUT_Manual_Upload_Regression as fixture
import HMBColorLUTLibrary as target

class DirectUploadRegression(fixture.ManualLUTRegression):
    def test_receipt_recovery_obeys_server_handoff(self):
        self.cap.update(client_review_media="client-v1", workstation_review_media="pc-v1")
        context = self.ready()
        response = self.ack(context)
        task = response["derived_task_id"]
        target._write_upload_receipt(context["receipt_id"], {"phase":"complete", "client_review_media":"client-v1",
                                     "response":response, "review_media_state":"pc_pending"})
        status = {"state":"fallback", "task_id":task, "source_sha256":context["sha256"], "source_bytes":context["size"]}
        with mock.patch("_hmb_client_review_media.get_workstation_media_state", return_value=status), \
             mock.patch("_hmb_client_review_media.workstation_media_heartbeat") as beat, \
             mock.patch("_hmb_color_lut.make_review_media") as encode, \
             mock.patch.object(self.node, "_upload_request") as original, \
             mock.patch.object(self.node, "_upload_review_media") as attach:
            self.upload("query-fallback")
            self.assertEqual(target._read_upload_receipt(context["receipt_id"])["review_media_state"], "fallback")
            status["state"] = "ready"
            self.upload("query-published")
            self.assertEqual(target._read_upload_receipt(context["receipt_id"])["review_media_state"], "ready")
            for call in (beat, encode, original, attach):
                call.assert_not_called()

    def test_handoff_during_encoding_keeps_original_receipt(self):
        from concurrent.futures import Future
        self.cap.update(client_review_media="client-v1", workstation_review_media="pc-v1")
        context = self.ready()
        task = self.ack(context)["derived_task_id"]
        cancel = threading.Event()
        encoded = Future()
        lease = mock.Mock(state="waiting")
        def complete_after_handoff():
            lease.state = "fallback"
            cancel.set()
            raise InterruptedError("encoder cancelled")
        with mock.patch("_hmb_client_review_media.workstation_media_heartbeat") as beat, \
             mock.patch.object(encoded, "result",side_effect=complete_after_handoff), \
             mock.patch.object(self.node, "_upload_review_media") as attach:
            beat.return_value.__enter__.return_value = lease
            self.assertEqual(self.node._finish_review_media(context,task,encoded,cancel,True),"fallback")
            self.assertIs(beat.call_args.kwargs["cancel_event"],cancel)
            attach.assert_not_called()

    def test_workstation_retry_only_attaches_to_accepted_original(self):
        self.cap.update(client_review_media="client-v1", workstation_review_media="pc-v1")
        context = self.ready()
        task = self.ack(context)["derived_task_id"]
        status = {"state": "waiting", "task_id": task, "source_sha256": context["sha256"], "source_bytes": context["size"]}
        with mock.patch("_hmb_color_lut.make_review_media", return_value=(self.root / "p.jpg", self.root / "p.mp4")) as encode, \
             mock.patch.object(self.node, "_upload_request", side_effect=lambda ctx, **kwargs: self.ack(ctx)) as original, \
             mock.patch.object(self.node, "_upload_review_media", side_effect=[TimeoutError(), {}]) as attach, \
             mock.patch("_hmb_client_review_media.workstation_media_heartbeat") as heartbeat, \
             mock.patch("_hmb_client_review_media.get_workstation_media_state", return_value=status) as query:
            self.upload("first-pc-attachment")
            receipt = target._read_upload_receipt(context["receipt_id"])
            self.assertEqual((receipt["phase"], receipt["review_media_state"]), ("complete", "pc_pending"))
            self.assertEqual(self.node._upload_projection()["phase"], "media_retry")
            self.upload("retry-pc-attachment")
            self.assertEqual(original.call_count, 1)
            self.assertEqual((attach.call_count, encode.call_count, heartbeat.call_count, query.call_count), (2,2,2,1))
            for call in heartbeat.call_args_list:
                self.assertEqual(call.kwargs["task_id"], task)
                self.assertEqual(call.kwargs["idempotency_key"], context["upload_id"])
                self.assertEqual(call.kwargs["source_sha256"], context["sha256"])
            self.assertEqual(target._read_upload_receipt(context["receipt_id"])["review_media_state"], "ready")

    def test_workstation_ready_skips_local_encode_and_both_posts_after_lost_reply(self):
        self.cap.update(client_review_media="client-v1", workstation_review_media="pc-v1")
        context = self.ready()
        response = self.ack(context)
        target._write_upload_receipt(context["receipt_id"], {"phase": "complete", "client_review_media": "client-v1",
                                     "response": response, "review_media_state": "encoding"})
        state = {"task_id":response["derived_task_id"], "source_sha256":context["sha256"], "source_bytes":context["size"],
                 "state":"ready"}
        with mock.patch("_hmb_client_review_media.get_workstation_media_state", return_value=state), \
             mock.patch("_hmb_client_review_media.workstation_media_heartbeat") as heartbeat, \
             mock.patch.object(self.node, "_upload_request") as original, \
             mock.patch("_hmb_color_lut.make_review_media") as encode, \
             mock.patch.object(self.node, "_upload_review_media") as attach:
            self.upload("already-published")
            for api in (heartbeat, original, encode, attach):
                api.assert_not_called()
        self.assertEqual(target._read_upload_receipt(context["receipt_id"])["review_media_state"], "ready")

    def test_client_media_overlaps_original_and_attaches_after_source_receipt(self):
        self.cap['client_review_media'] = 'client-v1'
        context = self.ready()
        started, accepted = threading.Event(), threading.Event()
        directories = []

        def encode(source, directory, cancel, *, expected_sha256):
            directories.append(directory)
            self.assertEqual((source, expected_sha256), (Path(context['path']), context['sha256']))
            started.set()
            self.assertTrue(accepted.wait(3))
            return directory / 'poster.jpg', directory / 'preview.mp4'

        def upload_original(bound, *, retrieve, cancel):
            self.assertFalse(retrieve)
            self.assertTrue(started.wait(3))
            accepted.set()
            return self.ack(bound)

        def attach(bound, child, poster, preview, *, cancel):
            original = target._read_upload_receipt(context['receipt_id'])
            self.assertEqual(original['phase'], 'complete')
            self.assertEqual(child, original['response']['derived_task_id'])
            self.assertEqual(bound['upload_id'], original['upload_id'])
            self.assertEqual(bound['sha256'], original['response']['sha256'])

        with mock.patch('_hmb_color_lut.make_review_media', side_effect=encode), \
             mock.patch.object(self.node, '_upload_request', side_effect=upload_original) as send, \
             mock.patch.object(self.node, '_upload_review_media', side_effect=attach) as media:
            self.upload()
            send.assert_called_once()
            media.assert_called_once()
        self.assertEqual(target._read_upload_receipt(context['receipt_id'])['review_media_state'], 'ready')
        self.assertFalse(directories[0].exists())

    def test_failed_media_preserves_completed_original_without_another_post(self):
        self.cap['client_review_media'] = 'client-v1'
        context = self.ready()
        with mock.patch('_hmb_color_lut.make_review_media', side_effect=ValueError('fixture encode failure')), \
             mock.patch.object(self.node, '_upload_request', side_effect=lambda c, **_: self.ack(c)) as send, \
             mock.patch.object(self.node, '_upload_review_media') as attach:
            self.upload()
            self.ready()
            self.upload('repeat-completed')
            send.assert_called_once()
            attach.assert_not_called()
        receipt = target._read_upload_receipt(context['receipt_id'])
        self.assertEqual((receipt['phase'], receipt['review_media_state']), ('complete', 'server'))
        self.assertEqual(receipt['response']['sha256'], context['sha256'])

    def test_client_media_status_check_recovers_original_without_encoding_or_posting(self):
        self.cap['client_review_media'] = 'client-v1'
        context = self.ready()
        target._write_upload_receipt(context['receipt_id'], {'phase':'unknown','client_review_media':'client-v1'})
        with mock.patch('_hmb_color_lut.make_review_media') as encode, \
             mock.patch.object(self.node, '_upload_request', side_effect=lambda c, **_: self.ack(c)) as send, \
             mock.patch.object(self.node, '_upload_review_media') as attach:
            self.upload()
            send.assert_called_once()
            self.assertTrue(send.call_args.kwargs['retrieve'])
            encode.assert_not_called()
            attach.assert_not_called()
        self.assertEqual(target._read_upload_receipt(context['receipt_id'])['phase'], 'complete')

    def test_original_alpha_mov_upload_after_native_import_uses_original_hash(self):
        import subprocess
        import _hmb_color_lut as media
        path = self.root / "한글 원본.MOV"
        subprocess.run([media._find_ffmpeg(), "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                        "color=blue:s=96x64:d=0.2", "-c:v", "qtrle", "-pix_fmt", "argb", str(path)], check=True)
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        with mock.patch.object(target, "probe_source", side_effect=media.probe_source):
            self.node._queue_source({"path": str(path)})
            self.fixture.drain()
        source = self.node._hmb_color_lut_state["source"]
        self.assertTrue(path.samefile(source["path"]))
        self.assertIn("ALPHA_UNSUPPORTED", source["grade_unavailable"])
        self.assertIn("preview.mp4", source["url"])
        with mock.patch.object(self.node, "_upload_request", side_effect=lambda ctx, **kw: self.ack(ctx)) as sent:
            self.ready()
            self.upload()
        ctx = sent.call_args.args[0]
        self.assertTrue(path.samefile(ctx["path"]))
        self.assertEqual((ctx["file_name"], ctx["sha256"]), (path.name, expected))

    def test_authored_edit_arriving_with_original_upload_recovers_readiness_without_sending(self):
        self.ready()
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        state['settings'].update(enabled=True, exposure=.5)
        with mock.patch.object(self.node, '_upload_request') as sent:
            self.node._command({'id':'fresh-edit-first-click','action':'upload_web','state':state})
            self.fixture.drain()
            sent.assert_not_called()
        self.assertTrue(self.node._upload_projection()['enabled'])

    def test_sound_update_refreshes_idle_probe_only_if_audio_is_used(self):
        self.ready()
        with mock.patch.object(self.node, '_schedule_upload_probe', wraps=self.node._schedule_upload_probe) as refresh:
            self.node._receive_sound({'sequence':1})
            refresh.assert_not_called()
            self.node._hmb_color_lut_state['audio_mix']['enabled'] = True
            self.ready()
            self.node._receive_sound({'sequence':2})
            self.fixture.drain()
            refresh.assert_called_once()
        self.assertTrue(self.node._upload_projection()['enabled'])

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

    def test_final_export_posts_and_attaches_the_same_graded_file_once(self):
        self.cap['client_review_media'] = 'client-v1'
        state = self.node._hmb_color_lut_state
        state['result'] = {}
        state['settings'].update(enabled=True, exposure=.5)
        settings = target.normalize_settings(state['settings'])
        source = Path(state['source']['path'])
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        encoding, posted = threading.Event(), threading.Event()

        def encode(path, directory, cancel, *, expected_sha256):
            self.assertNotEqual(path, source)
            self.assertEqual(expected_sha256, hashlib.sha256(path.read_bytes()).hexdigest())
            encoding.set()
            self.assertTrue(posted.wait(3))
            return directory / 'poster.jpg', directory / 'preview.mp4'

        def post(context, *, retrieve, cancel):
            self.assertFalse(retrieve)
            self.assertTrue(encoding.wait(3))
            posted.set()
            return self.ack(context)

        with mock.patch.object(target, 'export_video', side_effect=self.fixture.successful_export) as grade, \
             mock.patch('_hmb_color_lut.make_review_media', side_effect=encode) as review, \
             mock.patch.object(self.node, '_upload_request', side_effect=post) as send, \
             mock.patch.object(self.node, '_upload_review_media') as attach:
            self.chain('grade-and-publish')
            self.chain('repeat-graded-publish')
            grade.assert_called_once()
            review.assert_called_once()
            send.assert_called_once()
            attach.assert_called_once()
        bound = send.call_args.args[0]
        output = Path(state['result']['path'])
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        self.assertNotEqual(digest, source_hash)
        self.assertTrue(Path(bound['path']).samefile(output))
        self.assertTrue(review.call_args.args[0].samefile(output))
        self.assertEqual(bound['artifact'], 'export')
        self.assertEqual(bound['client_review_media'], 'client-v1')
        self.assertEqual(bound['sha256'], review.call_args.kwargs['expected_sha256'])
        self.assertEqual(bound['settings'], settings)
        metadata = bound['frozen_metadata']
        self.assertEqual((metadata['export_sha256'], metadata['export_bytes'], metadata['settings_sha256']),
                         (digest, output.stat().st_size, target._digest(settings)))
        receipt = target._read_upload_receipt(bound['receipt_id'])
        self.assertEqual(receipt['phase'], 'complete')
        self.assertEqual(receipt['review_media_state'], 'ready')
        self.assertEqual(attach.call_args.args[:2], (bound, receipt['response']['derived_task_id']))
        self.assertEqual(receipt['upload_id'], bound['upload_id'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)

    def test_explicit_output_then_upload_runs_once_and_keeps_original(self):
        state=self.node._hmb_color_lut_state
        original=Path(state['source']['path']).read_bytes();state['result']={}
        state['settings'].update(enabled=True,exposure=.5)
        with mock.patch.object(target,'export_video',side_effect=self.fixture.successful_export) as encoded, \
             mock.patch.object(self.node,'_upload_request',side_effect=lambda c,**kw:self.ack(c)) as sent, \
             mock.patch('_hmb_color_lut.make_review_media') as review, \
             mock.patch.object(self.node,'_upload_review_media') as attach, \
             mock.patch.object(self.node,'_capture_usage_operation') as usage:
            self.chain('grade-and-upload')
            self.chain('repeat-frozen-export')
            usage.assert_not_called()
            review.assert_not_called()
            attach.assert_not_called()
        self.assertEqual(encoded.call_count,1)
        self.assertEqual(sent.call_count,1)
        self.assertEqual(sent.call_args.args[0]['artifact'],'export')
        self.assertNotEqual(sent.call_args.args[0]['path'],state['source']['path'])
        self.assertEqual(Path(sent.call_args.args[0]['path']).suffix,'.mov')
        self.assertEqual(self.node._upload_metadata(sent.call_args.args[0])['output_format'],'mov')
        self.assertEqual(sent.call_args.args[0]['settings'],state['settings'])
        self.assertEqual(Path(state['source']['path']).read_bytes(),original)
        self.assertTrue(Path(state['result']['path']).is_file())
        self.assertEqual(state['status']['phase'],'complete')

    def test_mybox_output_then_upload_uses_mov_and_same_export_on_retry(self):
        rows=[*fixture.PROJECTS,{'id':'my-box','name':'My Box'}]
        with mock.patch.object(fixture,'PROJECTS',rows):
            self.node._manual_projects=copy.deepcopy(rows);self.choose('my-box')
            state=self.node._hmb_color_lut_state;state['result']={}
            state['output'].update(manual_output_enabled=True,path=str(self.root/'legacy.mp4'))
            with mock.patch.object(target,'export_video',side_effect=self.fixture.successful_export) as encoded, \
                 mock.patch.object(self.node,'_upload_request',side_effect=lambda c,**kw:self.ack(c)) as sent:
                self.chain('mybox-mov');self.chain('same-mybox-mov')
            self.assertEqual(encoded.call_count,1);self.assertEqual(sent.call_count,1)
            context=sent.call_args.args[0]
            self.assertEqual(context['project_id'],'my-box')
            self.assertEqual(Path(context['path']).name,'legacy.mov')
            self.assertEqual(context['file_name'],'11-12.mov')
            self.assertEqual(self.node._upload_metadata(context)['output_format'],'mov')

    def test_output_unknown_retries_same_export_with_get_only(self):
        self.cap['client_review_media'] = 'client-v1'
        self.node._hmb_color_lut_state['result']={};calls=[]
        def transport(c,*,retrieve,cancel):
            calls.append((c['upload_id'],retrieve,c['path']))
            if not retrieve:raise TimeoutError('response lost')
            return self.ack(c)
        with mock.patch.object(target,'export_video',side_effect=self.fixture.successful_export) as encoded, \
             mock.patch.object(self.node,'_upload_request',side_effect=transport), \
             mock.patch('_hmb_color_lut.make_review_media', return_value=(None, None)) as review, \
             mock.patch.object(self.node,'_upload_review_media') as attach:
            self.chain('first-export');self.chain('retrieve-export')
            review.assert_called_once()
            attach.assert_not_called()
        self.assertEqual(encoded.call_count,1)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][0],calls[1][0]);self.assertEqual(calls[0][2],calls[1][2])
        self.assertEqual([c[1] for c in calls],[False,True])
        self.assertEqual(self.node._hmb_color_lut_state['status']['phase'],'complete')

    def test_replaced_export_proof_before_publication_does_not_submit_another_output(self):
        self.cap['client_review_media'] = 'client-v1'
        state = self.node._hmb_color_lut_state
        previous = copy.deepcopy(state['result'])
        state['result'] = {}
        resume = self.node._continue_export_upload
        finished = []

        def replace_with_prior_result(captured, cancel, proof_id):
            finished.append(state['result']['path'])
            self.assertEqual(proof_id, state['result']['web_export_proof'])
            self.assertNotEqual(proof_id, previous['web_export_proof'])
            state['result'] = previous
            self.node._job_id = previous['job_id']
            return resume(captured, cancel, proof_id)

        with mock.patch.object(self.node, '_continue_export_upload', side_effect=replace_with_prior_result) as handoff, \
             mock.patch.object(target, 'export_video', side_effect=self.fixture.successful_export), \
             mock.patch.object(self.node, '_upload_request') as send, \
             mock.patch('_hmb_color_lut.make_review_media') as review, \
             mock.patch.object(self.node, '_upload_review_media') as attach:
            self.chain('grade-then-superseded')
            handoff.assert_called_once()
            send.assert_not_called()
            review.assert_not_called()
            attach.assert_not_called()
        self.assertTrue(Path(finished[0]).is_file())
        self.assertEqual(state['result']['web_export_proof'], previous['web_export_proof'])

    def test_source_project_settings_cancel_or_delete_during_export_never_auto_uploads(self):
        self.cap['client_review_media'] = 'client-v1'
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
                with mock.patch.object(target,'export_video',side_effect=encode) as encoded, \
                     mock.patch.object(self.node,'_upload_request') as sent, \
                     mock.patch('_hmb_color_lut.make_review_media') as review, \
                     mock.patch.object(self.node,'_upload_review_media') as attach:
                    self.chain('changed-'+change);sent.assert_not_called();self.assertEqual(encoded.call_count,1)
                    review.assert_not_called()
                    attach.assert_not_called()

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

    def test_save_only_with_a_ready_upload_project_never_queues_review_media(self):
        self.cap['client_review_media'] = 'client-v1'
        self.ready()
        self.node._hmb_color_lut_state['result'] = {}
        with mock.patch.object(target, 'export_video', side_effect=self.fixture.successful_export) as grade, \
             mock.patch.object(self.node, '_upload_request') as send, \
             mock.patch('_hmb_color_lut.make_review_media') as review, \
             mock.patch.object(self.node, '_upload_review_media') as attach:
            self.fixture.export('save-only')
            grade.assert_called_once()
            send.assert_not_called()
            review.assert_not_called()
            attach.assert_not_called()
        self.assertTrue(Path(self.node._hmb_color_lut_state['result']['path']).is_file())

if __name__=='__main__':unittest.main(verbosity=2)
