"""Offline Draft/Final authoring invariance and accepted-task retrieval.

Actual Generator methods run against synthetic SDK/transport/publication
boundaries. No provider, Broker, live graph, user media, or paid task is used.
The existing Draft fixture is reused without changing its behavior globally.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import importlib.util
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))
spec = importlib.util.spec_from_file_location(
    'draft_final_authoring_fixture', TESTS / 'HMB_Seedance_Draft_Shot_Regression.py')
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t = fixture.t
base = fixture.base
JOB = fixture.JOB
FINAL_JOB = 'job-' + 'c' * 32

AUTHORING_FIELDS = (
    'model_id', 'resolution', 'draft_action', 'output_format', 'return_last_frame',
    'prompt', 'duration', 'ratio', 'generate_audio', 'watermark',
    'execution_expires_after', 'priority', 'poll_interval_seconds',
    'generation_timeout_seconds', 'auto_publish_local_videos',
    'local_video_upload_service', 'first_frame', 'last_frame',
    'reference_images', 'video_references', 'reference_audio',
)


def authored(node):
    return {key: deepcopy(node.get_parameter_value(key)) for key in AUTHORING_FIELDS}


class DraftFinalAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.boundaries = ExitStack()
        self.addCleanup(self.boundaries.close)
        # A future fixture regression must fail rather than reach any network.
        original_connect = socket.socket.connect

        def local_socketpair_only(sock, address):
            # Windows asyncio implements its wake-up socketpair over loopback.
            # Permit that OS primitive while rejecting external transports.
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return original_connect(sock, address)
            raise AssertionError('Offline regression attempted external network access')

        self.boundaries.enter_context(mock.patch.object(socket.socket, 'connect',
                                                       new=local_socketpair_only))
        self.boundaries.enter_context(mock.patch.object(socket, 'create_connection',
            side_effect=AssertionError('Offline regression attempted network access')))
        for name in ('bind_task_origin', 'bind_task_project', 'update_case'):
            self.boundaries.enter_context(mock.patch.object(t._review, name))
        self.boundaries.enter_context(mock.patch.object(
            t._shot_routing, 'reconcile_completed_video_routes'))

    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def make_node(self, *, shot=True):
        node = fixture.Node(shot=shot)
        node.parameter_values.update(draft_action=t.DRAFT_ACTION_PREVIEW,
            resolution='480p', output_format='mp4', return_last_frame=True,
            prompt='Authored prompt {{SIGN}} remains literal', duration=4,
            ratio='16:9', generate_audio=False)
        return node

    @contextmanager
    def publication(self, node, before, *, download_error=None):
        """Fake only completed bytes; retain source/recovery/publication logic."""
        phases = []

        def phase(name, **kwargs):
            self.assertEqual(authored(node), before, f'Authoring changed at {name}')
            phases.append(name)

        async def publish(destination, data, output_format, verifier):
            self.assertEqual(authored(node), before, 'Authoring changed before file publication')
            path = Path(destination.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'SYNTHETIC-VERIFIED-VIDEO-PUBLICATION')
            return SimpleNamespace(location=str(path), name=path.name,
                                   resolve=lambda: str(path))

        async def save(task, job_id, destination, *args, **kwargs):
            await t.HMBSeedanceGeneration._save_completed_task(
                node, task, job_id, destination, *args, **kwargs)
            node.saved.append((job_id, str(destination.resolve()), kwargs))

        with ExitStack() as stack:
            stack.enter_context(fixture.run_boundaries(node))
            stack.enter_context(mock.patch.object(node, '_save_completed_task', new=save))
            stack.enter_context(mock.patch.object(node, '_extract_video_url',
                return_value='https://synthetic.invalid/completed.mov'))
            stack.enter_context(mock.patch.object(node, '_download_broker_video',
                new=mock.AsyncMock(side_effect=download_error,
                                   return_value=b'SYNTHETIC-VERIFIED-VIDEO')))
            stack.enter_context(mock.patch.object(node, '_atomic_publish_completed_video',
                new=mock.AsyncMock(side_effect=publish)))
            stack.enter_context(mock.patch.object(node, '_publish_generation_preview', side_effect=phase))
            stack.enter_context(mock.patch.object(node, '_schedule_review_sync'))
            stack.enter_context(mock.patch.object(node, '_update_parameter_visibility'))
            stack.enter_context(mock.patch.object(node, '_sync_seedance_shot_widget'))
            yield phases

    def seed_checkpoint(self, node, *, action, source=None, status='succeeded',
                        job_id=JOB, stage='remote_succeeded'):
        values = base.params(action)
        values.update(resolution='480p' if action == t.DRAFT_ACTION_PREVIEW else '1080p',
            output_format='mov', return_last_frame=False,
            _hmb_draft_project=deepcopy(fixture.PROJECT),
            _hmb_broker_server_url=fixture.ORIGIN,
            _hmb_generation_origin=node._capture_generated_video_origin(),
            _hmb_draft_source_bindings={} if node._draft_only_mode() else
                {'image_asset': fixture.PUBLISHER},
            _hmb_draft_started_at_ms=int(time.time() * 1000) - 1000,
            _hmb_output_file=str(Path(node.base.name) / 'saved-paid-stage.mov'))
        if source is not None:
            values['_hmb_draft_source'] = deepcopy(source)
        node._set_generation_recovery_checkpoint(stage='pre_submit',
            task_id='hmb-offline-source', task_identity='client_request',
            status='submitting', params=values)
        node._set_generation_recovery_checkpoint(stage=stage, task_id=job_id,
            task_identity='broker_task', status=status, params=values)
        node.parameter_output_values.update(generation_id=job_id,
            generation_status=status, provider_response={'id': job_id, 'status': status})

    def test_completed_draft_updates_source_and_button_without_changing_authored_settings(self):
        for shot in (False, True):
            with self.subTest(shot=shot):
                node = self.make_node(shot=shot)
                before = authored(node)
                self.seed_checkpoint(node, action=t.DRAFT_ACTION_PREVIEW)
                with self.publication(node, before) as phases:
                    asyncio.run(node._save_completed_task({}, JOB, node.destination,
                        model_id=t.SEEDANCE_2_5_MODEL_ID, output_format='mov',
                        return_last_frame=False))
                self.assertEqual(authored(node), before)
                self.assertEqual(node._draft_source_record()['draft_job_id'], JOB)
                self.assertEqual(node.get_parameter_value('draft_job_id'), JOB)
                self.assertTrue(node._draft_ui_state()['final_available'])
                self.assertEqual(phases, ['downloading', 'verifying', 'succeeded'])
                self.assertEqual(node.bridge.posts, [])

    def test_direct_final_is_ephemeral_sparse_and_consumed_once_with_authored_480p_unchanged(self):
        async def scenario(shot):
            node = self.make_node(shot=shot)
            node._store_draft_source(fixture.completed_source(node))
            before = authored(node)
            original = Path(node.base.name) / 'immutable-draft480p.mov'
            original.write_bytes(b'ORIGINAL-DRAFT-BYTES')
            fixture.forbid_upstream_work(node)
            with self.publication(node, before), \
                 fixture.engine_loop_patch(asyncio.get_running_loop()):
                result = node._on_finalize_draft_clicked(None, None,
                    action_id='offline-direct-final', expected_draft_job_id=JOB)
                self.assertTrue(result.success)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
            self.assertEqual(authored(node), before)
            self.assertEqual(node.bridge.posts, [{
                'provider': 'volcengine_ark', 'model': t.SEEDANCE_2_5_MODEL_ID,
                'draft_job_id': JOB, 'resolution': '1080p', 'output_format': 'mov',
                **fixture.PROJECT,
                'client_request_id': t._seedance_draft_final_request_id(JOB)}])
            source = node._draft_source_record()
            self.assertEqual(source['final_request_id'], t._seedance_draft_final_request_id(JOB))
            self.assertEqual(source['final_job_id'], 'job-' + '1' * 32)
            self.assertFalse(node._draft_ui_state()['final_available'])
            second = node._on_finalize_draft_clicked(None, None,
                action_id='offline-stale-second-click', expected_draft_job_id=JOB)
            self.assertFalse(second.success)
            self.assertEqual(len(node.bridge.posts), 1)
            self.assertEqual(original.read_bytes(), b'ORIGINAL-DRAFT-BYTES')
            node._manual_agent_prompt_source.assert_not_called()
            node._resolve_exact_shot_generation_inputs.assert_not_called()
            node._prepare_video_references_for_run.assert_not_called()
        for shot in (False, True):
            with self.subTest(shot=shot):
                asyncio.run(scenario(shot))

    def test_next_explicit_draft_after_final_uses_original_480p_preview_intent(self):
        async def scenario():
            node = self.make_node()
            node._store_draft_source(fixture.completed_source(node))
            before = authored(node)
            with self.publication(node, before):
                await node._run_draft_final(node._draft_source_record(), 'offline-first-final')
                self.assertEqual(authored(node), before)
                selection = {'schema': t.PROJECT_SELECTION_SCHEMA,
                             'project': deepcopy(fixture.PROJECT)}
                node._capture_imageasset_project_selection = mock.Mock(return_value=selection)
                node._resolve_exact_shot_generation_inputs = mock.Mock(side_effect=lambda values: {
                    **values, **fixture.PROJECT,
                    '_hmb_imageasset_project_selection': deepcopy(selection),
                    '_hmb_generation_origin': node._capture_generated_video_origin(),
                    '_hmb_draft_source_bindings': {'image_asset': fixture.PUBLISHER}})
                await node._process_generation_impl()
            self.assertEqual(authored(node), before)
            self.assertEqual(len(node.bridge.posts), 2)
            self.assertEqual(node.bridge.posts[1]['resolution'], '480p')
            self.assertIs(node.bridge.posts[1]['draft'], True)
            self.assertNotIn('draft_job_id', node.bridge.posts[1])
            self.assertNotEqual(node.bridge.posts[0]['client_request_id'],
                                node.bridge.posts[1]['client_request_id'])
            self.assertTrue(node._draft_ui_state()['final_available'])
        asyncio.run(scenario())

    def test_accepted_final_refresh_ignores_new_submission_getter_and_expired_consumed_source(self):
        for status in ('pending', 'cancelled_locally'):
            with self.subTest(status=status):
                node = self.make_node()
                # Legacy authored Final remains supported for retrieving its
                # existing paid task, even after the source's seven-day TTL.
                node.parameter_values.update(draft_action=t.DRAFT_ACTION_FINAL,
                                             resolution='1080p')
                source = fixture.completed_source(node,
                    created_at_ms=int(time.time() * 1000) - t.DRAFT_SOURCE_TTL_MS - 1,
                    final_request_id=t._seedance_draft_final_request_id(JOB))
                node._store_draft_source(source)
                self.seed_checkpoint(node, action=t.DRAFT_ACTION_FINAL,
                    source=source, status=status, job_id=FINAL_JOB, stage='accepted')
                before = authored(node)
                with self.publication(node, before), \
                     mock.patch.object(node, '_get_parameters',
                         side_effect=AssertionError('Refresh read new-submission settings')) as getter, \
                     mock.patch.object(node, '_validated_draft_final_source',
                         side_effect=AssertionError('Refresh validated a new Final')) as validator, \
                     mock.patch.object(node, '_synchronize_model_resolution',
                         side_effect=AssertionError('Refresh changed authored resolution')) as sync, \
                     mock.patch.object(node, '_build_broker_payload',
                         side_effect=AssertionError('Refresh built a new request')) as payload:
                    asyncio.run(node._refresh_async())
                self.assertEqual(node.bridge.refresh_ids, [FINAL_JOB])
                self.assertEqual(node.bridge.posts, [])
                self.assertEqual(len(node.saved), 1, node._set_status_results.call_args_list)
                self.assertEqual(node.saved[0][0], FINAL_JOB)
                self.assertEqual(node._generation_recovery_state()['stage'], 'local_succeeded')
                self.assertEqual(node._draft_source_record()['final_job_id'], FINAL_JOB)
                self.assertEqual(authored(node), before)
                for boundary in (getter, validator, sync, payload):
                    boundary.assert_not_called()

    def test_final_job_marker_alone_blocks_second_final(self):
        node = self.make_node()
        node._store_draft_source(fixture.completed_source(node, final_job_id=FINAL_JOB))
        self.assertFalse(node._draft_ui_state()['final_available'])
        with self.assertRaises(ValueError):
            node._validated_draft_final_source()
        result = node._on_finalize_draft_clicked(None, None,
            action_id='offline-final-job-only', expected_draft_job_id=JOB)
        self.assertFalse(result.success)
        self.assertEqual(node.bridge.posts, [])

    def test_busy_projection_uses_active_operation_not_authored_final_selection(self):
        cases = (
            ('normal', t.DRAFT_ACTION_OFF, t.DRAFT_ACTION_OFF, False, False),
            ('draft480p', t.DRAFT_ACTION_PREVIEW, t.DRAFT_ACTION_PREVIEW, False, False),
            ('authored-final-but-normal-active', t.DRAFT_ACTION_FINAL,
             t.DRAFT_ACTION_OFF, False, False),
            ('menu-final-active', t.DRAFT_ACTION_FINAL, t.DRAFT_ACTION_FINAL, False, True),
            ('direct-final-pending', t.DRAFT_ACTION_PREVIEW,
             t.DRAFT_ACTION_OFF, True, True),
        )
        for label, authored_action, active_action, pending, expected_final in cases:
            with self.subTest(operation=label):
                node = self.make_node()
                node._store_draft_source(fixture.completed_source(node))
                node.parameter_values['draft_action'] = authored_action
                node._hmb_active_draft_action = active_action
                node._hmb_draft_finalize_pending = pending
                node._generation_run_active.set()
                try:
                    state = node._draft_ui_state()
                    self.assertTrue(state['busy'])
                    self.assertIs(state['final_busy'], expected_final)
                    self.assertEqual(state['active_action'],
                        t.DRAFT_ACTION_FINAL if pending else active_action)
                finally:
                    node._generation_run_active.clear()
                    node._hmb_draft_finalize_pending = False
                idle = node._draft_ui_state()
                self.assertFalse(idle['busy'])
                self.assertFalse(idle['final_busy'])
                self.assertEqual(idle['active_action'], t.DRAFT_ACTION_OFF)

    def test_web_facade_cannot_publish_draft_source_or_enable_native_final(self):
        owner = self.make_node()
        original = fixture.completed_source(owner)
        owner._store_draft_source(original)
        before = deepcopy(owner.parameter_values)
        view = t._HMBWebRerenderExecution.read_view(owner)
        view_before = deepcopy(view.parameter_values)
        web_source = {**original, 'draft_job_id': 'job-' + 'b' * 32}
        view._store_draft_source(web_source)
        self.assertEqual(owner.parameter_values, before)
        self.assertEqual(view.parameter_values, view_before)
        self.assertEqual(owner._draft_source_record(), original)
        self.assertEqual(view._draft_source_record(), {})
        self.assertFalse(view._draft_ui_state()['final_available'])
        self.assertEqual(owner.bridge.posts, [])

    def test_capability_429_keeps_authored_settings_and_draft_unconsumed(self):
        async def scenario():
            node = self.make_node()
            node._store_draft_source(fixture.completed_source(node))
            node.bridge.capability_error = t._BrokerError('Synthetic capability rate limit', status_code=429)
            before = authored(node)
            fixture.forbid_upstream_work(node)
            with self.publication(node, before):
                await node._run_draft_final(node._draft_source_record(), 'offline-capability-429')
            self.assertEqual(authored(node), before)
            self.assertEqual(node.bridge.posts, [])
            self.assertNotIn('final_request_id', node._draft_source_record())
            self.assertTrue(node._draft_ui_state()['final_available'])
        asyncio.run(scenario())

    def test_definitive_create_rejection_releases_only_reservation_and_preserves_480p(self):
        async def scenario(code):
            node = self.make_node()
            node._store_draft_source(fixture.completed_source(node))
            before = authored(node)
            reject = mock.Mock(side_effect=t._BrokerError('Synthetic definitive create rejection',
                                                         status_code=code))
            node.bridge.generate_seedance = reject
            with self.publication(node, before):
                await node._run_draft_final(node._draft_source_record(), 'offline-rejected-final')
            self.assertEqual(authored(node), before)
            self.assertEqual(reject.call_count, 1)
            self.assertEqual(node.bridge.posts, [])
            self.assertNotIn('final_request_id', node._draft_source_record())
            self.assertTrue(node._draft_ui_state()['final_available'])
        for code in (400, 429):
            with self.subTest(code=code):
                asyncio.run(scenario(code))

    def test_accepted_final_download_failure_retains_reservation_and_original_authoring(self):
        async def scenario():
            node = self.make_node()
            node._store_draft_source(fixture.completed_source(node))
            before = authored(node)
            with self.publication(node, before,
                                  download_error=OSError('Synthetic local retrieval failure')):
                await node._run_draft_final(node._draft_source_record(), 'offline-download-failure')
            self.assertEqual(authored(node), before)
            self.assertEqual(len(node.bridge.posts), 1)
            self.assertIn('final_request_id', node._draft_source_record())
            self.assertFalse(node._draft_ui_state()['final_available'])
            self.assertEqual(node.saved, [])
            self.assertFalse(node._on_finalize_draft_clicked(None, None,
                action_id='offline-no-duplicate-after-download-failure',
                expected_draft_job_id=JOB).success)
            self.assertEqual(len(node.bridge.posts), 1)
        asyncio.run(scenario())

    def test_stop_before_dispatch_preserves_authoring_and_does_not_consume_draft(self):
        async def scenario():
            node = self.make_node()
            node._store_draft_source(fixture.completed_source(node))
            before = authored(node)
            with self.publication(node, before), \
                 fixture.engine_loop_patch(asyncio.get_running_loop()):
                started = node._on_finalize_draft_clicked(None, None,
                    action_id='offline-queued-stop', expected_draft_job_id=JOB)
                self.assertTrue(started.success)
                future = node._hmb_draft_finalize_future
                self.assertTrue(node._cancel_draft_final(JOB).success)
                try:
                    await asyncio.wrap_future(future)
                except asyncio.CancelledError:
                    pass
                await fixture.await_final_idle(node)
            self.assertEqual(authored(node), before)
            self.assertEqual(node.bridge.posts, [])
            self.assertNotIn('final_request_id', node._draft_source_record())
            self.assertFalse(node._hmb_draft_finalize_pending)
        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()
