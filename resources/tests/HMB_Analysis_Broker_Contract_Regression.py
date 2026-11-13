"""Production adapter contract and pipeline mocks. No live HTTP, token, provider or render."""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_broker_config as config
import _hmb_analysis_broker as broker
import _hmb_reference_analysis as analysis

ORIGIN = 'https://app.funnyflux.kr/GripTapeServer'
REQUEST_ID = 'analysis-' + 'a'*32


def result(model='gemini-4-argon', kind='image', status='completed'):
    observations = {key: [] for key in analysis.ANALYSIS_CATEGORIES[kind]}
    observations[next(iter(observations))] = [{'observation':'원문 OFF 0', 'interpretation':'', 'start':None, 'end':None}]
    return dict(schema='hmb-reference-analysis-response-v1',request_id=REQUEST_ID,model=model,kind=kind,
        status=status,output=observations if status=='completed' else None,output_text='원본 결과',retryable=False,
        usage=dict(input_tokens=12,output_tokens=None,total_tokens=None),estimated_cost=dict(estimated_amount=None))


class FakeBridge:
    instances=[]
    enabled=True
    principal='owner-a'
    reply=result()
    error=None
    after_post=None
    get_error=None
    def __init__(self, *, server_url, opener=None):
        self.server_url=server_url
        self.opener=opener
        self.calls=[]
        type(self).instances.append(self)
    @contextmanager
    def _reference_principal_scope(self):
        yield type(self).principal
    def _request_json(self,method,path,**kwargs):
        self.calls.append((method,path,deepcopy(kwargs)))
        if method=='GET' and type(self).get_error: raise type(self).get_error
        if path=='/api/me': return {'id':123}
        if path.endswith('/capabilities'):
            return dict(schema='hmb-analysis-capabilities-v1', enabled=self.enabled,automatic_retries=0,
                models=[dict(model_id=m,enabled=self.enabled,kinds=['image','video','audio']) for m in broker.MODELS])
        if type(self).error: raise type(self).error
        if method=='POST' and type(self).after_post: type(self).after_post()
        return deepcopy(type(self).reply)


class Contract(unittest.TestCase):
    def setUp(self):
        FakeBridge.instances=[];FakeBridge.enabled=True;FakeBridge.principal='owner-a'
        FakeBridge.reply=result();FakeBridge.error=None;FakeBridge.after_post=None
        FakeBridge.get_error=None
        self.module=patch.dict(sys.modules,{'HMBSeedanceGeneration':SimpleNamespace(_HMBAIBrokerBridge=FakeBridge)})
        self.module.start();self.addCleanup(self.module.stop)
        self.blob=b'\x89PNG\r\n\x1a\n' + b'fixture'
        self.attachments=[('frame 001 / 0.000s',self.blob,'image/png')]
        self.marked=[]
    def client(self,model='gemini-4-argon',kind='image',live=lambda:True):
        return broker.AnalysisClient(model,kind,is_live=live)
    def submit(self,client):
        return client.submit('Exact prompt OFF 0 한국어',self.attachments,{'source_sha256':'c'*64,
            'channel_uuid':'channel','shot_uuid':'shot'},analysis._output_schema(client.kind),lambda:self.marked.append(True))
    def test_exact_production_route_ignores_external_settings(self):
        with patch.object(config, 'load_broker_base_url', side_effect=AssertionError('external settings read')),              patch.dict(os.environ, {'GTN_BROKER_BASE_URL': 'https://bad.invalid'}):
            client = self.client()
        self.assertEqual(client.bridge.server_url, ORIGIN)
        self.assertIsNone(client.bridge.opener)
        self.assertEqual([(m, p) for m, p, _ in client.bridge.calls],
                         [('GET', '/api/me'), ('GET', '/api/v1/analysis/capabilities')])

    def test_changed_default_origin_fails_before_auth(self):
        for value in ('', 'https://127.0.0.1:18443', 'http://192.168.203.245:8080',
                      'https://app.funnyflux.kr', 'https://app.funnyflux.kr/GripTapeServer/'):
            with self.subTest(value=value), patch.object(config, 'DEFAULT_BROKER_BASE_URL', value):
                with self.assertRaises(broker.AnalysisBrokerError) as exc:
                    self.client()
                self.assertEqual(exc.exception.code, 'ANALYSIS_PRODUCTION_ORIGIN_REQUIRED')
        self.assertEqual(FakeBridge.instances, [])

    def test_get_failure_reports_preflight_failure_without_submit(self):
        FakeBridge.get_error = TimeoutError()
        with self.assertRaises(broker.AnalysisBrokerError) as exc:
            self.client()
        self.assertEqual(exc.exception.code, 'ANALYSIS_SERVER_UNAVAILABLE')
        self.assertNotIn('다시 제출', str(exc.exception))
        self.assertEqual([(m, p) for m, p, _ in FakeBridge.instances[-1].calls], [('GET', '/api/me')])

    def test_both_models_preserve_exact_body_and_receipt(self):
        for model in broker.MODELS:
            FakeBridge.reply=result(model)
            client=self.client(model)
            reply=self.submit(client)
            self.assertIsNone(reply['usage']['total_tokens'])
            self.assertIsNone(reply['estimated_cost']['estimated_amount'])
            method,path,opts=client.bridge.calls[-1]
            self.assertEqual((method,path),('POST','/api/v1/analysis'))
            self.assertEqual(opts['timeout'],110)
            self.assertTrue(opts['submission'])
            self.assertEqual(opts['payload']['prompt'],'Exact prompt OFF 0 한국어')
            self.assertEqual(base64.b64decode(opts['payload']['attachments'][0]['data_base64']),self.blob)
            self.assertEqual(opts['payload']['output_schema'],analysis._output_schema('image'))
            self.assertEqual(opts['payload']['context']['shot_uuid'],'shot')
            self.assertEqual(sum(m=='POST' for m,_,_ in client.bridge.calls),1)
    def test_same_payload_reuses_exact_idempotency_key(self):
        client=self.client();self.submit(client);first=client.bridge.calls[-1][2]['idempotency_key']
        self.submit(client);self.assertEqual(client.bridge.calls[-1][2]['idempotency_key'],first)
        client.submit('Changed',self.attachments,{},analysis._output_schema('image'),lambda:None)
        self.assertNotEqual(client.bridge.calls[-1][2]['idempotency_key'],first)
    def test_capability_disabled_and_auth_missing_do_not_submit(self):
        FakeBridge.enabled=False
        with self.assertRaises(broker.AnalysisBrokerError) as exc:self.client()
        self.assertEqual(exc.exception.code,'ANALYSIS_MODEL_UNAVAILABLE')
        self.assertFalse(any(m=='POST' for m,_,_ in FakeBridge.instances[-1].calls))
        FakeBridge.principal=''
        with self.assertRaises(broker.AnalysisBrokerError) as exc:self.client()
        self.assertEqual(exc.exception.code,'ANALYSIS_AUTH_REQUIRED')
    def test_noncompleted_status_never_becomes_success_or_retries(self):
        for status in ('blocked','failed','submission_unknown','submitting'):
            with self.subTest(status=status):
                FakeBridge.reply=result(status=status);client=self.client()
                with self.assertRaises(broker.AnalysisBrokerError) as exc:self.submit(client)
                self.assertEqual(exc.exception.code,'ANALYSIS_'+status.upper())
                self.assertEqual(exc.exception.receipt['request_id'],REQUEST_ID)
                self.assertEqual(sum(m=='POST' for m,_,_ in client.bridge.calls),1)
    def test_empty_mismatched_or_retrying_receipt_rejected(self):
        for change in ({'output':{}},{'model':'other'},{'kind':'audio'},{'retryable':True},{'request_id':'../secret'}):
            with self.subTest(change=change):
                FakeBridge.reply={**result(),**change}
                with self.assertRaises(broker.AnalysisBrokerError):self.submit(self.client())
    def test_timeout_never_resubmits(self):
        client=self.client();FakeBridge.error=TimeoutError()
        with self.assertRaises(broker.AnalysisBrokerError) as exc:self.submit(client)
        self.assertEqual(exc.exception.code,'ANALYSIS_RESULT_UNCONFIRMED')
        self.assertEqual(sum(m=='POST' for m,_,_ in client.bridge.calls),1)
    def test_cancel_before_or_after_submission_discards_late_result(self):
        live=[True];client=self.client(live=lambda:live[0]);live[0]=False
        with self.assertRaises(broker.AnalysisBrokerError):self.submit(client)
        self.assertEqual(self.marked,[])
        live[0]=True;FakeBridge.after_post=lambda:live.__setitem__(0,False)
        with self.assertRaises(broker.AnalysisBrokerError) as exc:self.submit(client)
        self.assertEqual(exc.exception.code,'ANALYSIS_CANCELLED')
        self.assertEqual(len(self.marked),1)
    def test_lookup_is_get_only_and_exact_owner_request(self):
        client=self.client();self.assertEqual(client.lookup(REQUEST_ID)['request_id'],REQUEST_ID)
        self.assertFalse(any(m=='POST' for m,_,_ in client.bridge.calls))
        FakeBridge.principal='other'
        with self.assertRaises(broker.AnalysisBrokerError):client.lookup(REQUEST_ID)
        with self.assertRaises(broker.AnalysisBrokerError):client.lookup('../invalid')
    def test_limits_fail_before_post(self):
        client=self.client()
        for attachments in ([],self.attachments*97,[('x',b'x'*(broker.MAX_MEDIA_BYTES+1),'image/png')],[('x',self.blob,'text/html')]):
            with self.assertRaises(broker.AnalysisBrokerError):
                client.submit('prompt',attachments,{},analysis._output_schema('image'),lambda:self.marked.append(True))
        self.assertEqual(self.marked,[])
        self.assertFalse(any(m=='POST' for m,_,_ in client.bridge.calls))
    def test_analysis_pipeline_normalizes_results_and_keeps_owner_cache_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'reference.png';source.write_bytes(self.blob)
            scope=dict(source=str(source),kind='image',model='gemini-4-carbon',cache_dir=Path(directory)/'cache',
                       analysis_context={'channel_uuid':'channel','shot_uuid':'shot'})
            FakeBridge.reply=result(model='gemini-4-carbon')
            with patch.object(analysis,'_attachments',return_value=(self.attachments,{})),patch.object(analysis,'_native_invoke',side_effect=AssertionError('native fallback forbidden')):
                first=analysis.analyze_reference(None,**scope)
                self.assertEqual(first['observations']['composition'][0]['observation'],'원문 OFF 0')
                self.assertEqual(first['broker_request_id'],REQUEST_ID)
                sent = FakeBridge.instances[-1].calls[-1][2]['payload']
                self.assertIn('one JSON object matching the supplied response schema', sent['prompt'])
                self.assertNotIn('Submit the required output tool', sent['prompt'])
                second=analysis.analyze_reference(None,**scope)
                self.assertTrue(second['cache_hit'])
                self.assertEqual(sum(m=='POST' for b in FakeBridge.instances for m,_,_ in b.calls),1)
                FakeBridge.principal='owner-b'
                third=analysis.analyze_reference(None,**scope)
                self.assertFalse(third['cache_hit'])
                self.assertNotEqual(first['cache_key'],third['cache_key'])
    def test_no_source_data_or_network_when_not_configured(self):
        with patch.object(config,'DEFAULT_BROKER_BASE_URL',''),patch.object(analysis,'_source_suffix',side_effect=AssertionError('must not read media')):
            with self.assertRaises(analysis.AnalysisError) as exc:
                analysis.analyze_reference(None,source='not-a-file',kind='image',model='gemini-4-carbon')
            self.assertEqual(exc.exception.code,'ANALYSIS_PRODUCTION_ORIGIN_REQUIRED')
        self.assertEqual(FakeBridge.instances,[])


if __name__=='__main__':unittest.main()
