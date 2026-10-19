"""Offline same-Task saved-video retrieval and filesystem failure contracts.

Actual Generator refresh/checkpoint/source/publication entry points are used.
Only the SDK shell, Broker GET, download/decode and persistence boundaries are
synthetic. Tests never contact a server, create a render or open user media.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))
spec = importlib.util.spec_from_file_location(
    'saved_task_refresh_fixture', TESTS / 'HMB_Seedance_Draft_Shot_Regression.py')
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t = fixture.t
base = fixture.base
JOB = fixture.JOB
OTHER = 'job-' + 'b' * 32
MOV = (b'\x00\x00\x00\x18ftypqt  \x00\x00\x00\x00qt  isom'
       b'\x00\x00\x00\x10moov\x00\x00\x00\x08mvhd'
       b'\x00\x00\x00\x10mdat12345678')
AUTHORED = ('model_id', 'resolution', 'draft_action', 'output_format',
            'prompt', 'duration', 'ratio', 'generate_audio',
            'return_last_frame', 'resume_generation_id')


def file_identity(path):
    stat = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def output_snapshot(node):
    return {key: {'artifact_value': value.value,
                  'artifact_name': getattr(value, 'name', None)}
            if hasattr(value, 'value') else deepcopy(value)
            for key, value in node.parameter_output_values.items()}


class SavedTaskRefreshTests(unittest.TestCase):
    def setUp(self):
        self.boundaries = ExitStack()
        self.addCleanup(self.boundaries.close)
        original_connect = socket.socket.connect

        def local_wakeup_only(sock, address):
            # Windows asyncio's internal socketpair may use loopback.
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return original_connect(sock, address)
            raise AssertionError('Saved-task fixture attempted external transport')

        self.boundaries.enter_context(mock.patch.object(socket.socket, 'connect',
                                                       new=local_wakeup_only))
        self.boundaries.enter_context(mock.patch.object(socket, 'create_connection',
            side_effect=AssertionError('Saved-task fixture attempted network access')))
        for name in ('bind_task_origin', 'bind_task_project', 'update_case'):
            self.boundaries.enter_context(mock.patch.object(t._review, name))
        self.boundaries.enter_context(mock.patch.object(t._shot_routing,
            'reconcile_completed_video_routes'))
        self.decoder = self.boundaries.enter_context(mock.patch.object(t,
            '_validate_decodable_mp4_file', side_effect=self.accept_synthetic_movie))

    @staticmethod
    def accept_synthetic_movie(path, _verifier=None):
        if Path(path).read_bytes() != MOV:
            raise RuntimeError('Synthetic completed movie is corrupt')

    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def make_node(self, *, job_id=JOB, stage='local_succeeded', shot=True,
                  include_source=True):
        node = fixture.Node(shot=shot)
        node.parameter_values.update(model_id=t.MODEL_NAME_SEEDANCE_2_5,
            resolution='480p', draft_action=t.DRAFT_ACTION_PREVIEW,
            output_format='mov', return_last_frame=False,
            prompt='Authored {{SIGN}} remains literal', duration=4,
            ratio='16:9', generate_audio=False, resume_generation_id='')
        path = Path(node.base.name) / 'immutable-draft480p.mov'
        path.write_bytes(MOV)
        node.destination = SimpleNamespace(resolve=lambda: str(path),
            _existing_file_policy=t.ExistingFilePolicy.FAIL, _create_parents=True)
        node._output_file = SimpleNamespace(build_file=lambda: node.destination,
            _default_filename=str(path))
        node._build_recovery_output_destination = mock.Mock(return_value=node.destination)
        params = base.params(t.DRAFT_ACTION_PREVIEW)
        params.update(model_id=t.SEEDANCE_2_5_MODEL_ID, output_format='mov',
            return_last_frame=False, _hmb_output_file=str(path),
            _hmb_broker_server_url=fixture.ORIGIN,
            _hmb_generation_origin=node._capture_generated_video_origin())
        node._set_generation_recovery_checkpoint(stage='pre_submit',
            task_id='hmb-offline-saved-request', task_identity='client_request',
            status='submitting', params=params)
        node._set_generation_recovery_checkpoint(stage=stage, task_id=job_id,
            task_identity='broker_task', status='succeeded', params=params)
        artifact = t.VideoUrlArtifact(value=str(path), name=path.name)
        node.parameter_output_values.update(generation_id=job_id,
            generation_status='succeeded', provider_response={'id': job_id,
            'status': 'succeeded'}, video_url=artifact, VIDEO_OUT=artifact,
            last_frame_url=None)
        node._hmb_last_success_video = artifact
        if include_source and shot:
            self.assertTrue(node._record_completed_video_source(
                node._capture_generated_video_origin(), job_id,
                SimpleNamespace(location=str(path), resolve=lambda: str(path))))
        node._publish_generation_preview = mock.Mock()
        node._set_status_results = mock.Mock()
        node._schedule_review_sync = mock.Mock()
        node._update_parameter_visibility = mock.Mock()
        node._sync_seedance_shot_widget = mock.Mock()
        node._extract_video_url = mock.Mock(return_value='https://synthetic.invalid/completed.mov')
        node._download_broker_video = mock.AsyncMock(return_value=MOV)
        node._atomic_publish_completed_video = mock.AsyncMock(
            side_effect=AssertionError('A saved same-Task movie was republished'))
        # Do not inherit the fixture's simplified completion method.
        node._save_completed_task = t.HMBSeedanceGeneration._save_completed_task.__get__(node)
        self.boundaries.enter_context(mock.patch.object(node, '_force_save_generation_recovery_checkpoint',
            new=mock.AsyncMock(return_value=True)))
        return node, path

    def authoring(self, node):
        return {key: deepcopy(node.get_parameter_value(key)) for key in AUTHORED}

    def assert_success(self, node, job_id):
        self.assertTrue(node._set_status_results.called,
                        node._publish_generation_preview.call_args_list)
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], True, result)
        self.assertIn(job_id, result['result_details'])
        self.assertEqual(node._generation_recovery_state()['stage'], 'local_succeeded')
        self.assertEqual(node._generation_recovery_state()['task_id'], job_id)
        self.assertEqual(node.parameter_output_values['generation_id'], job_id)
        self.assertEqual(node.parameter_output_values['generation_status'], 'succeeded')
        self.assertEqual(node.bridge.posts, [])

    def assert_no_publication(self, node):
        node._download_broker_video.assert_not_awaited()
        node._atomic_publish_completed_video.assert_not_awaited()
        self.assertEqual(node._hmb_generation_media_revision, 0)

    def test_strict_destination_saved_task_refresh_repairs_failure_without_rewriting(self):
        node, path = self.make_node()
        before, settings = file_identity(path), self.authoring(node)
        source = deepcopy(node._hmb_generated_video_source_snapshot())
        checkpoint = deepcopy(node._generation_recovery_state())
        node._hmb_generation_preview_state = t._seedance_generation_preview_value(
            {'phase': 'failed', 'job_id': JOB, 'action': 'refresh_existing'})
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(file_identity(path), before)
        self.assertEqual(self.authoring(node), settings)
        self.assertEqual(node._hmb_generated_video_source_snapshot(), source)
        self.assertEqual(node._generation_recovery_state(), checkpoint)
        self.assertEqual(node.bridge.refresh_ids, [JOB])

    def test_repeat_refresh_is_idempotent_and_never_uses_create_new_suffix(self):
        node, path = self.make_node()
        before = file_identity(path)
        for _ in range(5):
            asyncio.run(node._refresh_async())
            self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(file_identity(path), before)
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertEqual(node.bridge.refresh_ids, [JOB] * 5)

    def test_explicit_resume_of_already_saved_task_does_not_republish_or_submit(self):
        node, path = self.make_node()
        node.parameter_values['resume_generation_id'] = JOB
        before, settings = file_identity(path), self.authoring(node)
        asyncio.run(node._process_generation_impl())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(file_identity(path), before)
        self.assertEqual(self.authoring(node), settings)
        self.assertEqual(node.bridge.posts, [])

    def test_five_generators_refresh_only_their_own_saved_task(self):
        nodes = [self.make_node(job_id='job-' + str(index) * 32)
                 for index in range(1, 6)]
        before = [(file_identity(path), self.authoring(node)) for node, path in nodes]

        async def refresh_all():
            await asyncio.gather(*(node._refresh_async() for node, _ in nodes))

        asyncio.run(refresh_all())
        for index, ((node, path), (identity, settings)) in enumerate(zip(nodes, before), 1):
            with self.subTest(generator=index):
                job_id = 'job-' + str(index) * 32
                self.assert_success(node, job_id)
                self.assert_no_publication(node)
                self.assertEqual(file_identity(path), identity)
                self.assertEqual(self.authoring(node), settings)
                self.assertEqual(node.bridge.refresh_ids, [job_id])

    def test_only_mode_legacy_saved_checkpoint_and_artifact_can_be_reused(self):
        node, path = self.make_node(shot=False, include_source=False)
        before = file_identity(path)
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(file_identity(path), before)

    def test_shot_to_only_success_reuses_only_artifact_and_preserves_prior_shot_source(self):
        prior, prior_path = self.make_node(job_id=OTHER)
        node, path = self.make_node(shot=False, include_source=False)
        old_source = deepcopy(prior._hmb_generated_video_source_snapshot())
        node._hmb_generated_video_source = deepcopy(old_source)
        node.parameter_values[t.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(old_source)
        node.parameter_output_values[t.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(old_source)
        before, old_before = file_identity(path), file_identity(prior_path)
        self.assertEqual(node._generation_recovery_state()['generation_origin'], {})
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(str(node.parameter_output_values['VIDEO_OUT'].value), str(path))
        self.assertEqual(node._hmb_generated_video_source, old_source)
        self.assertEqual(node.parameter_values[t.GENERATED_VIDEO_SOURCE_PARAMETER], old_source)
        self.assertEqual(node.parameter_output_values[t.GENERATED_VIDEO_SOURCE_PARAMETER], old_source)
        self.assertEqual(file_identity(path), before)
        self.assertEqual(file_identity(prior_path), old_before)

    def test_only_mode_does_not_treat_malformed_prior_source_as_verified_legacy_history(self):
        node, path = self.make_node(shot=False, include_source=False)
        node._hmb_generated_video_source = {'task_id': OTHER, 'path': str(path)}
        node.parameter_values[t.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(
            node._hmb_generated_video_source)
        before = file_identity(path)
        asyncio.run(node._refresh_async())
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], False, result)
        self.assertNotIn('connection is currently unavailable', result['result_details'])
        self.assertEqual(file_identity(path), before)
        self.assertEqual(node.parameter_output_values['generation_id'], JOB)
        self.assert_no_publication(node)
        self.assertEqual(node.bridge.posts, [])

    def test_current_output_field_edit_does_not_redirect_saved_task(self):
        node, path = self.make_node()
        before = file_identity(path)
        foreign = path.with_name('future-explicit-run.mov')
        node.parameter_values['output_file'] = str(foreign)
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(file_identity(path), before)
        self.assertFalse(foreign.exists())
        self.assertEqual(node.parameter_values['output_file'], str(foreign))

    def test_foreign_task_source_does_not_reclassify_existing_collision_as_broker_disconnect(self):
        node, path = self.make_node(stage='remote_succeeded')
        node._hmb_generated_video_source['generation_id'] = OTHER
        node._hmb_generated_video_source['task_id'] = OTHER
        node.parameter_values[t.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(
            node._hmb_generated_video_source)
        before = file_identity(path)
        asyncio.run(node._refresh_async())
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], False, result)
        self.assertNotIn('connection is currently unavailable', result['result_details'])
        self.assertIn('FileExistsError', result['result_details'])
        self.assertIn(JOB, result['result_details'])
        self.assertEqual(file_identity(path), before)
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node._generation_recovery_state()['task_id'], JOB)

    def test_locally_succeeded_checkpoint_does_not_adopt_another_tasks_source(self):
        node, path = self.make_node()
        node._hmb_generated_video_source.update(generation_id=OTHER, task_id=OTHER)
        node.parameter_values[t.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(
            node._hmb_generated_video_source)
        before = file_identity(path)
        asyncio.run(node._refresh_async())
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], False, result)
        self.assertNotIn('connection is currently unavailable', result['result_details'])
        self.assertEqual(file_identity(path), before)
        self.assert_no_publication(node)
        self.assertEqual(node.parameter_output_values['generation_id'], JOB)
        self.assertEqual(node.bridge.posts, [])

    def test_create_new_reuses_the_actual_published_suffix_without_creating_another(self):
        node, original = self.make_node()
        published = original.with_name(original.stem + '_1.mov')
        original.rename(published)
        original.write_bytes(b'FOREIGN-BASE-OUTPUT')
        artifact = t.VideoUrlArtifact(value=str(published), name=published.name)
        node.parameter_output_values.update(video_url=artifact, VIDEO_OUT=artifact)
        node._hmb_last_success_video = artifact
        node._hmb_generated_video_source.update(path=str(published), url=str(published))
        node.parameter_values[t.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(
            node._hmb_generated_video_source)
        node.destination._existing_file_policy = t.ExistingFilePolicy.CREATE_NEW
        saved_before, foreign_before = file_identity(published), file_identity(original)
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(file_identity(published), saved_before)
        self.assertEqual(file_identity(original), foreign_before)
        self.assertEqual(set(original.parent.iterdir()), {original, published})
        self.assertEqual(str(node.parameter_output_values['VIDEO_OUT'].value), str(published))

    def test_final_refresh_preserves_authored_480p_and_draft_record(self):
        node, path = self.make_node()
        source = fixture.completed_source(node, draft_job_id=OTHER,
                                         final_job_id=JOB)
        node._store_draft_source(source)
        checkpoint = node._generation_recovery_state()
        checkpoint.update(draft_action=t.DRAFT_ACTION_FINAL, draft_source=deepcopy(source))
        node.parameter_values[t.SEEDANCE_RECOVERY_PARAMETER] = checkpoint
        before = self.authoring(node)
        draft_before = deepcopy(node._draft_source_record())
        identity = file_identity(path)
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(self.authoring(node), before)
        self.assertEqual(node._draft_source_record(), draft_before)
        self.assertEqual(file_identity(path), identity)

    def test_lookup_disconnect_keeps_a_verified_local_success_without_resubmission(self):
        node, path = self.make_node()
        before = file_identity(path)
        node.bridge.refresh_job = mock.Mock(side_effect=TimeoutError('Synthetic GET timeout'))
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        self.assertEqual(file_identity(path), before)
        self.assertEqual(node.bridge.posts, [])

    def test_stale_failure_flags_are_removed_before_web_readiness_and_hydration(self):
        node, path = self.make_node()
        before = file_identity(path)
        failure_fields = {'terminal': True, 'resubmit_allowed': False,
            'error_code': 'submission_unknown', 'recovery_action': 'contact_admin',
            'error_details': {'message': 'STALE-FAILURE-ONLY'},
            'error': 'STALE-ERROR', 'message': 'STALE-MESSAGE'}
        node.parameter_output_values.update(generation_status='failed',
            provider_response={'id': JOB, 'status': 'submission_unknown',
                               'provider_task_registered': True, **failure_fields})
        self.assertTrue(node._hmb_web_rerender_recovery_blocked())
        node.bridge.refresh_job = mock.Mock(side_effect=TimeoutError('Synthetic GET timeout'))
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        self.assert_no_publication(node)
        response = node.parameter_output_values['provider_response']
        self.assertEqual(response['id'], JOB)
        self.assertEqual(response['status'], 'succeeded')
        self.assertIs(response['provider_task_registered'], True)
        for key in failure_fields:
            self.assertNotIn(key, response)
        self.assertFalse(node._hmb_web_rerender_recovery_blocked())
        node._publish_generation_preview.reset_mock()
        node._restore_generation_recovery_preview()
        self.assertEqual(node._publish_generation_preview.call_args.args, ('succeeded',))
        self.assertEqual(node._publish_generation_preview.call_args.kwargs['action'], 'none')
        self.assertEqual(node.parameter_output_values['provider_response'], response)
        self.assertFalse(node._hmb_web_rerender_recovery_blocked())
        self.assertEqual(file_identity(path), before)

    def test_lookup_disconnect_without_completed_local_evidence_remains_unknown(self):
        node, path = self.make_node(stage='accepted', include_source=False)
        path.unlink()
        node.bridge.refresh_job = mock.Mock(side_effect=TimeoutError('Synthetic GET timeout'))
        asyncio.run(node._refresh_async())
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], False, result)
        self.assertIn('connection is currently unavailable', result['result_details'])
        self.assertEqual(node._generation_recovery_state()['task_id'], JOB)
        self.assertEqual(node.bridge.posts, [])
        self.assert_no_publication(node)

    def test_corrupt_existing_movie_is_not_overwritten_or_reported_as_broker_disconnect(self):
        node, path = self.make_node()
        path.write_bytes(b'CORRUPT-LOCAL-MOVIE')
        before = file_identity(path)
        asyncio.run(node._refresh_async())
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], False, result)
        self.assertNotIn('connection is currently unavailable', result['result_details'])
        self.assertEqual(file_identity(path), before)
        self.assert_no_publication(node)
        self.assertEqual(node.bridge.posts, [])

    def test_task_change_delete_or_cancel_during_validation_cannot_publish_old_success(self):
        async def scenario(kind):
            node, path = self.make_node()
            before = file_identity(path)
            started, release = threading.Event(), threading.Event()

            def decoder(selected, _verifier=None):
                started.set()
                if not release.wait(3):
                    raise AssertionError('Validation cancellation fixture timed out')
                self.accept_synthetic_movie(selected)

            self.decoder.side_effect = decoder
            task = asyncio.create_task(node._refresh_async())
            self.assertTrue(await asyncio.to_thread(started.wait, 2),
                            'Saved result validation did not start')
            if kind == 'deleted':
                node.live = False
            elif kind == 'cancelled':
                node._cancellation_requested.set()
            else:
                node.parameter_output_values['generation_id'] = OTHER
                checkpoint = node._generation_recovery_state()
                checkpoint.update(task_id=OTHER, stage='accepted', status='running')
                node.parameter_values[t.SEEDANCE_RECOVERY_PARAMETER] = checkpoint
            release.set()
            await task
            self.assertFalse(any(call.kwargs.get('was_successful') is True
                                 for call in node._set_status_results.call_args_list))
            self.assert_no_publication(node)
            self.assertEqual(file_identity(path), before)
            self.assertEqual(node.bridge.posts, [])
            if kind == 'replaced':
                self.assertEqual(node.parameter_output_values['generation_id'], OTHER)
                self.assertEqual(node._generation_recovery_state()['task_id'], OTHER)

        for kind in ('deleted', 'cancelled', 'replaced'):
            with self.subTest(operation=kind):
                asyncio.run(scenario(kind))

    def test_late_validation_failure_cannot_replace_newer_task_source_or_artifact_status(self):
        async def scenario(kind):
            node, path = self.make_node()
            before = file_identity(path)
            started, release = threading.Event(), threading.Event()

            def decoder(_selected, _verifier=None):
                started.set()
                if not release.wait(3):
                    raise AssertionError('Late validation failure fixture timed out')
                raise RuntimeError('Synthetic stale decoder failure')

            self.decoder.side_effect = decoder
            task = asyncio.create_task(node._refresh_async())
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            if kind == 'task':
                node.parameter_output_values.update(generation_id=OTHER,
                    generation_status='running')
                checkpoint = node._generation_recovery_state()
                checkpoint.update(task_id=OTHER, stage='accepted', status='running')
                node.parameter_values[t.SEEDANCE_RECOVERY_PARAMETER] = checkpoint
            elif kind == 'source':
                node._hmb_generated_video_source.update(result_revision=27)
                node.parameter_values[t.GENERATED_VIDEO_SOURCE_PARAMETER] = deepcopy(
                    node._hmb_generated_video_source)
            else:
                newer = path.with_name('newer-current-movie.mov')
                newer.write_bytes(MOV + b'CURRENT-ARTIFACT')
                artifact = t.VideoUrlArtifact(value=str(newer), name=newer.name)
                node.parameter_output_values.update(video_url=artifact, VIDEO_OUT=artifact)
            expected_outputs = output_snapshot(node)
            expected_source = deepcopy(node._hmb_generated_video_source)
            expected_checkpoint = deepcopy(node._generation_recovery_state())
            release.set()
            await task
            self.assertEqual(node._set_status_results.call_args_list, [])
            self.assertEqual(output_snapshot(node), expected_outputs)
            self.assertEqual(node._hmb_generated_video_source, expected_source)
            self.assertEqual(node._generation_recovery_state(), expected_checkpoint)
            self.assertEqual(file_identity(path), before)
            self.assert_no_publication(node)
            self.assertEqual(node.bridge.posts, [])

        for kind in ('task', 'source', 'artifact'):
            with self.subTest(changed_during_failed_validation=kind):
                asyncio.run(scenario(kind))

    def test_persistence_error_after_verified_file_commit_does_not_turn_success_into_failure(self):
        node, path = self.make_node(stage='remote_succeeded', include_source=False)
        path.unlink()

        async def publish(destination, content, output_format, verifier):
            target = Path(destination.resolve())
            target.write_bytes(content)
            return SimpleNamespace(location=str(target), name=target.name,
                                   resolve=lambda: str(target))

        node._atomic_publish_completed_video.side_effect = publish
        # The real save sets the durable in-memory completion and source before
        # its best-effort recovery persistence await. Preserve that paid result.
        node._force_save_generation_recovery_checkpoint.side_effect = (
            None, OSError('Synthetic recovery persistence failed after file commit'))
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        node._download_broker_video.assert_awaited_once()
        node._atomic_publish_completed_video.assert_awaited_once()
        self.assertEqual(path.read_bytes(), MOV)
        self.assertEqual(node._hmb_generation_media_revision, 1)
        self.assertEqual(node._hmb_generated_video_source_snapshot()['task_id'], JOB)
        self.assertEqual(node.bridge.posts, [])

    def test_missing_local_movie_is_retrieved_again_instead_of_claiming_success(self):
        node, path = self.make_node()
        path.unlink()
        async def publish(destination, content, output_format, verifier):
            target = Path(destination.resolve())
            self.assertFalse(target.exists())
            target.write_bytes(content)
            return SimpleNamespace(location=str(target), name=target.name,
                                   resolve=lambda: str(target))
        node._atomic_publish_completed_video.side_effect = publish
        asyncio.run(node._refresh_async())
        self.assert_success(node, JOB)
        node._download_broker_video.assert_awaited_once()
        node._atomic_publish_completed_video.assert_awaited_once()
        self.assertEqual(path.read_bytes(), MOV)

    def test_empty_local_movie_is_not_accepted_as_a_completed_artifact(self):
        node, path = self.make_node()
        path.write_bytes(b'')
        asyncio.run(node._refresh_async())
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], False, result)
        self.assertNotIn('connection is currently unavailable', result['result_details'])
        self.assertEqual(path.read_bytes(), b'')
        self.assertEqual(node.bridge.posts, [])

    def test_local_permission_error_is_not_reported_as_a_broker_disconnect(self):
        node, path = self.make_node(stage='remote_succeeded', include_source=False)
        path.unlink()
        node._atomic_publish_completed_video.side_effect = PermissionError('Synthetic local destination denied')
        asyncio.run(node._refresh_async())
        result = node._set_status_results.call_args.kwargs
        self.assertIs(result['was_successful'], False, result)
        self.assertIn('PermissionError', result['result_details'])
        self.assertNotIn('connection is currently unavailable', result['result_details'])
        self.assertIn(JOB, result['result_details'])
        self.assertEqual(node.bridge.posts, [])

    def test_deleted_node_and_active_generation_do_not_refresh_or_touch_media(self):
        for active in (False, True):
            with self.subTest(active_generation=active):
                node, path = self.make_node()
                before = file_identity(path)
                if active:
                    node._generation_run_active.set()
                else:
                    node.live = False
                asyncio.run(node._refresh_async())
                self.assertEqual(node.bridge.refresh_ids, [])
                self.assertEqual(node.bridge.posts, [])
                self.assertEqual(file_identity(path), before)
                self.assert_no_publication(node)


if __name__ == '__main__':
    unittest.main()
