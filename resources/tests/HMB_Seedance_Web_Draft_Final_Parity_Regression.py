"""One Draft Final intent for local and web; fake transport only, no paid calls."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('web_final_shot_fixture', Path(__file__).with_name('HMB_Seedance_Draft_Shot_Regression.py'))
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t, base = fixture.t, fixture.base


class FinalParityTests(unittest.TestCase):
    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def header_final(self, *, formats=("mp4", "mov")):
        node = fixture.Node()
        profile = node.bridge.capability_response['models'][t.SEEDANCE_2_5_MODEL_ID]
        profile['output_formats'] = list(formats)
        profile['draft_output_formats'] = list(formats)
        source = fixture.completed_source(node)
        node._store_draft_source(source)
        fixture.forbid_upstream_work(node)
        with fixture.run_boundaries(node):
            asyncio.run(node._run_draft_final(source, 'synthetic-web-parity-final'))
        self.assertEqual(len(node.bridge.posts), 1, node._set_status_results.call_args_list)
        return node, node.bridge.posts[0]

    def test_exact_web_key_and_canonical_sparse_payload(self):
        node, body = self.header_final()
        key = 'hmb-draft-final-v1-' + base.JOB
        self.assertEqual(body, {'provider': 'volcengine_ark', 'model': t.SEEDANCE_2_5_MODEL_ID,
            'resolution': '1080p', 'output_format': 'mov', 'draft_job_id': base.JOB,
            **base.PROJECT, 'client_request_id': key})
        self.assertEqual(node.upload_calls, 0)
        node._manual_agent_prompt_source.assert_not_called()
        node._resolve_exact_shot_generation_inputs.assert_not_called()
        self.assertNotIn('prompt', body)
        self.assertNotIn('quality', body)
        self.assertNotIn('reference_images', body)
        self.assertNotIn('reference_videos', body)

    def test_same_draft_different_generator_owner_has_identical_web_intent(self):
        first, one = self.header_final()
        second, two = self.header_final()
        self.assertNotEqual(first._draft_owner_id(), second._draft_owner_id())
        self.assertEqual(one, two)
        # Both transports may reach the Broker. Atomic server idempotency, not
        # a local process lock, owns cross-browser/cross-generator billing.

    def test_header_and_authored_final_share_key_and_body(self):
        _, header_body = self.header_final()
        values = base.params(t.DRAFT_ACTION_FINAL)
        values.update(resolution='1080p', output_format='mov')
        node = base.Node(values)
        node._prepare_video_references_for_run = mock.Mock(side_effect=AssertionError('media upload'))
        node._resolve_exact_shot_generation_inputs = mock.Mock(side_effect=AssertionError('new inputs'))
        with mock.patch.object(t, '_resolve_mp4_decode_verifier', return_value=SimpleNamespace(executable='fixture', backend='test')):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.bridge.posts, [header_body])

    def test_header_and_authored_final_share_declared_mp4_fallback_body(self):
        header, header_body = self.header_final(formats=('mp4',))
        self.assertEqual(header_body['output_format'], 'mp4')
        self.assertTrue(header.saved[0][1].endswith('.mp4'))
        values = base.params(t.DRAFT_ACTION_FINAL)
        values.update(resolution='1080p', output_format='mov')
        node = base.Node(values)
        profile = node.bridge.capability_response['models'][t.SEEDANCE_2_5_MODEL_ID]
        profile['output_formats'] = ['mp4']
        profile['draft_output_formats'] = ['mp4']
        fixture.forbid_upstream_work(node)
        with mock.patch.object(t, '_resolve_mp4_decode_verifier',
                return_value=SimpleNamespace(executable='fixture', backend='test')):
            asyncio.run(node._process_generation_impl())
        self.assertEqual(node.bridge.posts, [header_body])
        self.assertEqual(node.saved[0][2]['output_format'], 'mp4')
        self.assertTrue(node.saved[0][1].endswith('.mp4'))
        self.assertEqual(node.upload_calls, 0)
        node._manual_agent_prompt_source.assert_not_called()

    def test_transport_idempotency_header_matches_body(self):
        _, body = self.header_final()
        bridge = t._HMBAIBrokerBridge(server_url=base.ORIGIN)
        with mock.patch.object(bridge, 'require_seedance_draft_features'), \
             mock.patch.object(bridge, '_request_json', return_value={'job_id': base.JOB}) as request:
            bridge.generate_seedance(body, timeout=1)
        self.assertEqual(request.call_args.args[:2], ('POST', '/api/v1/generate/video'))
        self.assertEqual(request.call_args.kwargs['payload'], body)
        self.assertEqual(request.call_args.kwargs['idempotency_key'], body['client_request_id'])

    def test_reserved_final_disables_button_and_stale_second_click(self):
        node, _ = self.header_final()
        state = node._draft_ui_state()
        self.assertFalse(state['final_available'])
        self.assertIn('already has a Final', state['reason'])
        with self.assertRaises(ValueError):
            node._validated_draft_final_source()
        result = node._on_finalize_draft_clicked(None, None,
            action_id='synthetic-second-click', expected_draft_job_id=base.JOB)
        self.assertFalse(result.success)
        self.assertEqual(len(node.bridge.posts), 1)

    def test_legacy_accepted_final_key_is_retained_for_retrieval(self):
        node = fixture.Node()
        old_key = 'hmb-final-accepted-before-web-contract'
        source = fixture.completed_source(node, final_request_id=old_key)
        node._store_draft_source(source)
        node._set_generation_recovery_checkpoint(stage='accepted', task_id=old_key,
            task_identity='client_request', status='submitted',
            params={**base.params(t.DRAFT_ACTION_FINAL), '_hmb_draft_source': source})
        self.assertEqual(node._draft_source_record()['final_request_id'], old_key)
        self.assertEqual(node._generation_recovery_state()['task_id'], old_key)
        self.assertFalse(node._draft_ui_state()['final_available'])
        self.assertEqual(node.bridge.posts, [])

    def test_canonical_job_only_and_distinct_drafts(self):
        for value in ('', None, True, '../../unsafe', 'cgt-provider-task', 'job-' + 'A' * 32):
            with self.subTest(value=value), self.assertRaises(ValueError):
                t._seedance_draft_final_request_id(value)
        self.assertNotEqual(t._seedance_draft_final_request_id(base.JOB),
                            t._seedance_draft_final_request_id('job-' + 'b' * 32))


if __name__ == '__main__':
    unittest.main()
