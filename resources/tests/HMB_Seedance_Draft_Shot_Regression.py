"""Offline Shot/Only Draft finalization using actual host methods and synthetic boundaries.

No Broker/provider transport, uploads, user workflows or user media are used.
The installed-SDK runner records whether real Griptape modules were imported.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('draft_shot_fixture', Path(__file__).with_name('HMB_Seedance_Draft_Regression.py'))
assert spec and spec.loader
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)
t = base.t
JOB = base.JOB
ORIGIN = base.ORIGIN
PROJECT = base.PROJECT
CHANNEL = '11111111-1111-4111-8111-111111111111'
SHOT_A = '22222222-2222-4222-8222-222222222222'
SHOT_B = '33333333-3333-4333-8333-333333333333'
OWNER = '44444444-4444-4444-8444-444444444444'
SOURCE_INSTANCE = '55555555-5555-4555-8555-555555555555'
PUBLISHER = '66666666-6666-4666-8666-666666666666'


class Node(base.Node):
    """Real parameter snapshots/Shot identity; only host and provider boundaries are fake."""
    _get_parameters = t.HMBSeedanceGeneration._get_parameters
    _draft_only_mode = t.HMBSeedanceGeneration._draft_only_mode
    _capture_generated_video_origin = t.HMBSeedanceGeneration._capture_generated_video_origin
    _assert_agent_result_available = t.HMBSeedanceGeneration._assert_agent_result_available

    @property
    def is_cancellation_requested(self):
        event = getattr(self, '_cancellation_requested', None)
        return bool(event is not None and event.is_set())

    def __init__(self, *, shot=True):
        self.live = True
        self.source_connected = True
        self.source_channel = CHANNEL
        self.source_publisher = PUBLISHER
        self.source_shots = [SHOT_A, SHOT_B]
        self.current_project = deepcopy(PROJECT)
        self.direct_source = SimpleNamespace(_hmb_node_deleted=False)
        self.direct_source._hmb_shot_channel_subscription = lambda: {
            'participant_kind': 'image_asset', 'enabled': True, 'channel_uuid': self.source_channel}
        self.direct_source._hmb_shot_routing_snapshot = lambda *_args: {
            'channel_uuid': self.source_channel, 'publisher_instance_uuid': self.source_publisher,
            'shots': [{'shot_uuid': shot_id} for shot_id in self.source_shots]}
        self.direct_source._hmb_shot_routing_catalog = self.direct_source._hmb_shot_routing_snapshot
        super().__init__()
        self.parameter_values.update(base.params())
        self.parameter_values.update(model_id=t.MODEL_NAME_SEEDANCE_2_5, resolution='480p',
                                     draft_action=t.DRAFT_ACTION_OFF, draft_job_id='')
        self.parameter_values[t.DRAFT_OWNER_PARAMETER] = str(uuid4())
        self._hmb_generated_source_instance_id = SOURCE_INSTANCE
        self._set_status_results = mock.Mock()
        self._clear_execution_status = mock.Mock()
        self._manual_agent_prompt_source = mock.Mock(return_value=None)
        self._cleanup_temporary_video_uploads = mock.Mock()
        self._hmb_shot_catalog_snapshot = {'schema': 'hmb-shot-routing-catalog', 'version': 1,
            'publisher_instance_uuid': PUBLISHER, 'channel_uuid': CHANNEL,
            'generation': 1, 'metadata_sha256': 'a'*64,
            'shots': [{'shot_uuid': SHOT_A, 'number': 1, 'name': 'Shot 1', 'revision': 1},
                      {'shot_uuid': SHOT_B, 'number': 2, 'name': 'Shot 2', 'revision': 1}]}
        self.bind(shot_uuid=SHOT_A if shot else '')

    def bind(self, *, channel=CHANNEL, shot_uuid=SHOT_A, number=1, name=None):
        enabled = bool(channel and shot_uuid)
        self.parameter_values.update({t.SHOT_CHANNEL_UUID_PARAMETER: channel if enabled else '',
            t.SHOT_UUID_PARAMETER: shot_uuid if enabled else '',
            t.SHOT_NUMBER_PARAMETER: number if enabled else 0,
            t.SHOT_NAME_PARAMETER: name or (f'Shot {number}' if enabled else t.SHOT_ONLY_LABEL),
            t.SHOT_SELECTOR_PARAMETER: f'Shot {number}' if enabled else t.SHOT_ONLY_LABEL})

    def _runtime_node_is_live(self, *, require_registered=False):
        return self.live and not getattr(self, '_hmb_node_deleted', False)

    def _exact_incoming_source(self, parameter, port, *, required=False):
        return self.direct_source if self.source_connected and parameter == t.SHOT_ASSET_INPUT_PARAMETER else None

    def _hmb_generation_project(self):
        return deepcopy(self.current_project)


def completed_source(node, **changes):
    record = {**base.SOURCE, 'completed': True, 'created_at_ms': int(time.time()*1000)-1000,
              'generation_origin': node._capture_generated_video_origin(), 'owner_id': node._draft_owner_id(),
              'source_bindings': {} if node._draft_only_mode() else {'image_asset': node.source_publisher}}
    record.update(changes)
    return record


def run_boundaries(node):
    """Mock external work while retaining parameter, validation, routing and submission logic."""
    stack = ExitStack()
    stack.enter_context(mock.patch.object(t, '_resolve_mp4_decode_verifier',
        return_value=SimpleNamespace(executable='fixture', backend='test')))
    stack.enter_context(mock.patch.object(t._review, 'capture_inputs', return_value={}))
    stack.enter_context(mock.patch.object(t._review, 'update_case'))
    return stack


def forbid_upstream_work(node):
    node._prepare_video_references_for_run = mock.Mock(side_effect=AssertionError('Final uploaded media'))
    node._resolve_exact_shot_generation_inputs = mock.Mock(side_effect=AssertionError('Final rebuilt Shot media'))
    node._manual_agent_prompt_source = mock.Mock(side_effect=AssertionError('Final read Agent result'))


def engine_loop_patch(loop):
    return mock.patch.object(t.GriptapeNodes, 'EventManager', return_value=SimpleNamespace(event_loop=loop))


async def await_final_idle(node):
    # A concurrent Future acknowledges cancel before the underlying coroutine
    # completes its awaited cleanup. Wait on actual host ownership, not ticks.
    deadline = time.monotonic() + 2
    while node._generation_run_active.is_set() or node._hmb_draft_finalize_pending:
        if time.monotonic() >= deadline:
            raise AssertionError('Cancelled Final did not release its host execution ownership')
        await asyncio.sleep(.005)


class DraftShotTests(unittest.TestCase):
    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def test_completed_shot_metadata_is_bounded_and_preserves_provenance_only(self):
        node = Node()
        source = completed_source(node)
        normalized = t._seedance_draft_source_value({**source, 'prompt': 'PRIVATE',
            'image_urls': ['secret://image'], 'video_urls': ['secret://video'], 'token': 'PRIVATE'})
        self.assertEqual(normalized, source)
        self.assertEqual(normalized['generation_origin']['shot_uuid'], SHOT_A)
        for changes in ({'completed': False}, {'created_at_ms': True}, {'created_at_ms': 0},
                        {'owner_id': ''}, {'generation_origin': {'shot_uuid': SHOT_A}}):
            with self.subTest(changes=changes):
                self.assertEqual(t._seedance_draft_source_value({**source, **changes}), {})

    def test_legacy_only_source_keeps_original_four_fields_without_invented_shot(self):
        self.assertEqual(t._seedance_draft_source_value(base.SOURCE), base.SOURCE)

    def test_source_origin_is_captured_from_actual_shot_parameters(self):
        node = Node()
        origin = node._capture_generated_video_origin()
        self.assertEqual(origin, {'channel_uuid': CHANNEL, 'shot_uuid': SHOT_A,
            'source_node_instance_id': SOURCE_INSTANCE, 'number': 1, 'name': 'Shot 1'})
        node.bind(shot_uuid=SHOT_B, number=2)
        self.assertEqual(node._capture_generated_video_origin()['shot_uuid'], SHOT_B)
        node.bind(shot_uuid='')
        self.assertEqual(node._capture_generated_video_origin(), {})

    def test_only_and_shot_expose_preview_at_480_without_premature_final(self):
        for shot in (False, True):
            with self.subTest(shot=shot):
                node = Node(shot=shot)
                state = node._draft_ui_state()
                self.assertTrue(state['visible'])
                self.assertTrue(state['preview_available'])
                self.assertFalse(state['final_available'])
                with self.assertRaises(ValueError):
                    node._validated_draft_final_source()
                node.parameter_values['resolution'] = '1080p'
                self.assertFalse(node._draft_ui_state()['visible'])
                self.assertFalse(node._draft_ui_state()['preview_available'])

    def test_shot_preview_uses_real_parameter_snapshot_and_draft_wire(self):
        node = Node()
        node.parameter_values.update(draft_action=t.DRAFT_ACTION_PREVIEW, output_format='mov', return_last_frame=True)
        values = node._get_parameters()
        self.assertEqual((values['draft_action'], values['resolution'], values['output_format'],
                          values['return_last_frame']), (t.DRAFT_ACTION_PREVIEW, '480p', 'mov', False))
        self.assertIs(values['_hmb_draft_supported'], True)
        wire = node._build_broker_payload(values)
        self.assertIs(wire['draft'], True)
        self.assertEqual(wire['quality'], '480p')
        self.assertEqual(wire['output_format'], 'mov')

    def test_only_and_shot_final_parameter_snapshot_selects_1080p_mov(self):
        for shot in (False, True):
            with self.subTest(shot=shot):
                node = Node(shot=shot)
                node._store_draft_source(completed_source(node))
                node.parameter_values.update(draft_action=t.DRAFT_ACTION_FINAL,
                                             resolution='480p', output_format='mp4')
                values = node._get_parameters()
                self.assertEqual((values['resolution'], values['output_format']), ('1080p', 'mov'))
                wire = node._build_broker_payload(values)
                self.assertEqual((wire['resolution'], wire['output_format']), ('1080p', 'mov'))
                self.assertNotIn('quality', wire)
                self.assertNotIn('prompt', wire)
                self.assertNotIn('reference_images', wire)
                self.assertNotIn('reference_videos', wire)

    def test_completed_matching_shot_enables_final_at_480_and_1080(self):
        node = Node()
        source = completed_source(node)
        node._store_draft_source(source)
        for resolution in ('480p', '1080p'):
            with self.subTest(resolution=resolution):
                node.parameter_values['resolution'] = resolution
                self.assertEqual(node._draft_source_record(), source)
                self.assertEqual(node._validated_draft_final_source(), source)
                self.assertTrue(node._draft_ui_state()['visible'])
                self.assertTrue(node._draft_ui_state()['final_available'])

    def test_shot_switch_retains_each_source_and_never_adopts_other_shot(self):
        node = Node()
        first = completed_source(node)
        node._store_draft_source(first)
        node.bind(shot_uuid=SHOT_B, number=2)
        self.assertEqual(node._draft_source_record(), {})
        self.assertFalse(node._draft_ui_state()['final_available'])
        with self.assertRaises(ValueError):
            node._validated_draft_final_source(first)
        second = completed_source(node, draft_job_id='job-'+'b'*32)
        node._store_draft_source(second)
        self.assertEqual(node._draft_source_record(), second)
        node.bind()
        self.assertEqual(node._draft_source_record(), first)
        self.assertEqual(len(node.get_parameter_value(t.DRAFT_SOURCES_PARAMETER)['sources']), 2)

    def test_incomplete_or_legacy_source_cannot_be_promoted_to_shot_final(self):
        node = Node()
        for source in (base.SOURCE, completed_source(node, completed=False),
                       completed_source(node, generation_origin={})):
            with self.subTest(source=source), self.assertRaises(ValueError):
                node._validated_draft_final_source(source)

    def test_changed_owner_channel_project_or_broker_blocks_final(self):
        mutations = (
            lambda n: n.parameter_values.__setitem__(t.DRAFT_OWNER_PARAMETER, SHOT_B),
            lambda n: n.bind(channel=SHOT_B),
            lambda n: n.current_project.update(project_id='katuri8', project_name='까투리8'),
            lambda n: n.parameter_values.__setitem__(t.BROKER_SERVER_URL_PARAMETER, 'https://synthetic-broker.invalid'),
        )
        for index, change in enumerate(mutations):
            with self.subTest(mutation=index):
                node = Node()
                source = completed_source(node)
                node._store_draft_source(source)
                change(node)
                with self.assertRaises(ValueError):
                    node._validated_draft_final_source(source)
                self.assertFalse(node._draft_ui_state()['final_available'])

    def test_source_disconnect_delete_and_channel_rebind_block_final(self):
        mutations = (lambda n: setattr(n, 'source_connected', False),
                     lambda n: setattr(n.direct_source, '_hmb_node_deleted', True),
                     lambda n: setattr(n, 'source_channel', SHOT_B),
                     lambda n: setattr(n, 'source_publisher', SHOT_B),
                     lambda n: setattr(n, 'source_shots', [SHOT_B]),
                     lambda n: n._hmb_shot_catalog_snapshot.update(shots=[
                         {'shot_uuid': SHOT_B, 'number': 2, 'name': 'Shot 2', 'revision': 1}]))
        for index, change in enumerate(mutations):
            with self.subTest(mutation=index):
                node = Node()
                source = completed_source(node)
                node._store_draft_source(source)
                change(node)
                with self.assertRaises(ValueError):
                    node._validated_draft_final_source(source)
                self.assertFalse(node._draft_ui_state()['final_available'])

    def test_expiry_exact_boundary_and_future_timestamp_are_rejected(self):
        node = Node()
        now_ms = 2_000_000_000_000
        with mock.patch.object(t.time, 'time', return_value=now_ms/1000):
            valid = completed_source(node, created_at_ms=now_ms-t.DRAFT_SOURCE_TTL_MS+1)
            self.assertEqual(node._validated_draft_final_source(valid), valid)
            for created in (now_ms-t.DRAFT_SOURCE_TTL_MS, now_ms+1):
                with self.subTest(created=created), self.assertRaises(ValueError):
                    node._validated_draft_final_source(completed_source(node, created_at_ms=created))

    def test_only_legacy_source_retains_original_endpoint_and_project(self):
        node = Node(shot=False)
        node.parameter_values[t.DRAFT_SOURCE_PARAMETER] = deepcopy(base.SOURCE)
        node.parameter_values[t.BROKER_SERVER_URL_PARAMETER] = 'https://synthetic-broker.invalid'
        self.assertEqual(node._validated_draft_final_source(), base.SOURCE)
        # Deserialized legacy identity is retained, but availability now waits
        # for an advisory GET against that original authenticated Broker.
        asyncio.run(node._query_draft_final_server_state(node._draft_source_record()))
        self.assertTrue(node._draft_ui_state()['final_available'])

    def test_seedance20_cannot_expose_or_submit_draft(self):
        node = Node()
        node._store_draft_source(completed_source(node))
        node.parameter_values.update(model_id=t.MODEL_NAME_SEEDANCE_2_0,
                                     draft_action=t.DRAFT_ACTION_PREVIEW, resolution='720p')
        self.assertFalse(node._draft_ui_state()['visible'])
        self.assertFalse(node._draft_ui_state()['final_available'])
        self.assertEqual(node._get_parameters()['draft_action'], t.DRAFT_ACTION_OFF)
        with self.assertRaises(ValueError):
            node._validated_draft_final_source()

    def test_final_reservation_disables_second_request_and_remains_refreshable(self):
        node = Node()
        source = completed_source(node, final_request_id='hmb-final-synthetic-001')
        node._store_draft_source(source)
        self.assertFalse(node._draft_ui_state()['final_available'])
        with self.assertRaises(ValueError):
            node._validated_draft_final_source()
        self.assertEqual(node._validated_draft_final_source(allow_reserved=True), source)

    def test_saved_source_survives_reopen_with_same_owner_and_stable_publishers(self):
        previous = Node()
        source = completed_source(previous)
        previous._store_draft_source(source)
        previous.live = False
        restored = Node()
        restored.parameter_values[t.DRAFT_OWNER_PARAMETER] = source['owner_id']
        restored.parameter_values[t.DRAFT_SOURCES_PARAMETER] = deepcopy(
            previous.get_parameter_value(t.DRAFT_SOURCES_PARAMETER))
        self.assertEqual(restored._validated_draft_final_source(), source)
        restored.parameter_values[t.DRAFT_OWNER_PARAMETER] = SHOT_B
        with self.assertRaises(ValueError):
            restored._validated_draft_final_source(source)

    def test_busy_generation_refresh_or_pending_action_disables_final(self):
        for busy in ('generation', 'refresh', 'finalize'):
            with self.subTest(busy=busy):
                node = Node()
                node._store_draft_source(completed_source(node))
                if busy == 'generation':
                    node._generation_run_active.set()
                elif busy == 'refresh':
                    node._generation_refresh_running = True
                else:
                    node._hmb_draft_finalize_pending = True
                state = node._draft_ui_state()
                self.assertTrue(state['busy'])
                self.assertFalse(state['final_available'])
                self.assertFalse(state['preview_available'])

    def test_final_runs_only_generator_with_sparse_wire_and_preserved_origin(self):
        node = Node()
        node.bind(name='생성 당시 샷 이름 🎬')
        source = completed_source(node)
        node._store_draft_source(source)
        node.bind(name='현재 변경된 슬롯 이름')
        node.parameter_values.update(prompt='must not be resent', duration=29, ratio='9:16',
                                     generate_audio=True, output_format='mov')
        forbid_upstream_work(node)
        with run_boundaries(node), \
             mock.patch.object(t._review, 'capture_inputs', side_effect=AssertionError('Final captured current media')), \
             mock.patch.object(t.GriptapeNodes, 'handle_request', side_effect=AssertionError('Final dispatched graph execution'), create=True), \
             mock.patch.object(t.GriptapeNodes, 'ahandle_request', side_effect=AssertionError('Final dispatched async graph execution'), create=True):
            asyncio.run(node._run_draft_final(source, 'synthetic-final-01'))
        self.assertEqual(len(node.bridge.posts), 1, node._set_status_results.call_args_list)
        wire = node.bridge.posts[0]
        self.assertEqual(set(wire), {'provider', 'model', 'draft_job_id', 'resolution', 'output_format', 'project_id', 'project_name', 'client_request_id'})
        self.assertEqual({key: wire[key] for key in PROJECT}, PROJECT)
        self.assertEqual((wire['resolution'], wire['output_format'], wire['draft_job_id']), ('1080p', 'mov', JOB))
        self.assertEqual(node.upload_calls, 0)
        node._prepare_video_references_for_run.assert_not_called()
        node._resolve_exact_shot_generation_inputs.assert_not_called()
        node._manual_agent_prompt_source.assert_not_called()
        self.assertEqual(node._generation_recovery_state()['generation_origin'], source['generation_origin'])
        self.assertEqual(node._generation_recovery_state()['generation_origin']['name'], '생성 당시 샷 이름 🎬')
        self.assertEqual(node.get_parameter_value('prompt'), 'must not be resent')
        self.assertEqual(node.get_parameter_value('output_format'), 'mov')
        self.assertEqual(len(node.saved), 1)
        self.assertIn('final1080p', node.saved[0][1])
        self.assertTrue(node.saved[0][1].endswith('.mov'))
        self.assertEqual(node.saved[0][2]['output_format'], 'mov')
        self.assertFalse(Path(node.base.name, 'original.mp4').exists())

    def test_double_click_schedules_one_final_and_later_click_cannot_repeat_it(self):
        async def scenario():
            node = Node()
            source = completed_source(node)
            node._store_draft_source(source)
            forbid_upstream_work(node)
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                first = node._on_finalize_draft_clicked(None, None, action_id='click-one', expected_draft_job_id=JOB)
                future = node._hmb_draft_finalize_future
                second = node._on_finalize_draft_clicked(None, None, action_id='click-two', expected_draft_job_id=JOB)
                self.assertTrue(first.success)
                self.assertTrue(second.success)
                self.assertIs(node._hmb_draft_finalize_future, future)
                await asyncio.wrap_future(future)
                self.assertEqual(len(node.bridge.posts), 1, node._set_status_results.call_args_list)
                third = node._on_finalize_draft_clicked(None, None, action_id='click-three', expected_draft_job_id=JOB)
                self.assertFalse(third.success)
                await asyncio.sleep(0)
                self.assertEqual(len(node.bridge.posts), 1)
        asyncio.run(scenario())

    def test_supported_format_preview_then_direct_final_freezes_inputs_and_runs_generator_once(self):
        async def scenario(shot, ordinary_formats, draft_formats, expected_format):
            node = Node(shot=shot)
            profile = node.bridge.capability_response['models'][t.SEEDANCE_2_5_MODEL_ID]
            profile['output_formats'] = deepcopy(ordinary_formats)
            profile['draft_output_formats'] = deepcopy(draft_formats)
            node.parameter_values.update(draft_action=t.DRAFT_ACTION_PREVIEW,
                                         resolution='480p', output_format='mov')
            selection = {'schema': t.PROJECT_SELECTION_SCHEMA, 'project': deepcopy(PROJECT)}
            origin = node._capture_generated_video_origin()
            node._capture_imageasset_project_selection = mock.Mock(return_value=selection)
            node._resolve_exact_shot_generation_inputs = mock.Mock(side_effect=lambda values: {
                **values, **PROJECT, '_hmb_imageasset_project_selection': deepcopy(selection),
                '_hmb_generation_origin': deepcopy(origin),
                '_hmb_draft_source_bindings': {} if not shot else {'image_asset': PUBLISHER}})
            final_job = 'job-'+'c'*32

            def submit(payload, *, timeout):
                node.bridge.posts.append(deepcopy(payload))
                return {'id': JOB if len(node.bridge.posts) == 1 else final_job,
                        'status': 'succeeded', 'video_url': 'synthetic-boundary'}

            async def save_verified_boundary(task, job_id, destination, *args, **kwargs):
                # The transport/publication boundaries are synthetic. Actual
                # Draft publication and metadata validation have separate tests.
                path = Path(destination.resolve())
                path.write_bytes(b'IMMUTABLE-DRAFT-BYTES' if job_id == JOB else b'FINAL-BYTES')
                node.saved.append((job_id, str(path), kwargs))
                if job_id == JOB:
                    node._store_draft_source(completed_source(node, draft_job_id=JOB))

            node.bridge.generate_seedance = submit
            node._save_completed_task = save_verified_boundary
            with run_boundaries(node):
                await node._process_generation_impl()
            self.assertEqual(len(node.bridge.posts), 1)
            preview_body = deepcopy(node.bridge.posts[0])
            self.assertEqual((preview_body['resolution'], preview_body.get('output_format', 'mp4')),
                             ('480p', expected_format))
            self.assertIs(preview_body['draft'], True)
            self.assertIn(('draft', 'mov', expected_format), node.bridge.format_resolution_calls)
            draft_path = Path(node.saved[0][1])
            self.assertEqual(draft_path.suffix, '.'+expected_format)
            self.assertEqual(node.saved[0][2]['output_format'], expected_format)
            self.assertTrue(node._draft_ui_state()['final_available'])

            node.parameter_values.update(prompt='changed after Draft {{SIGN}}', duration=29,
                                         ratio='9:16', output_format='mp4')
            forbid_upstream_work(node)
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()), \
                 mock.patch.object(t.GriptapeNodes, 'handle_request',
                    side_effect=AssertionError('Final executed upstream graph'), create=True), \
                 mock.patch.object(t.GriptapeNodes, 'ahandle_request',
                    side_effect=AssertionError('Final executed upstream graph'), create=True):
                first = node._on_finalize_draft_clicked(None, None,
                    action_id='mov-final-click', expected_draft_job_id=JOB)
                future = node._hmb_draft_finalize_future
                duplicate = node._on_finalize_draft_clicked(None, None,
                    action_id='mov-final-double-click', expected_draft_job_id=JOB)
                self.assertTrue(first.success)
                self.assertTrue(duplicate.success)
                self.assertIs(node._hmb_draft_finalize_future, future)
                await asyncio.wrap_future(future)

            self.assertEqual(len(node.bridge.posts), 2, node._set_status_results.call_args_list)
            final_body = node.bridge.posts[1]
            self.assertEqual(final_body, {'provider': 'volcengine_ark',
                'model': t.SEEDANCE_2_5_MODEL_ID, 'draft_job_id': JOB,
                'resolution': '1080p', 'output_format': expected_format, **PROJECT,
                'client_request_id': t._seedance_draft_final_request_id(JOB)})
            self.assertEqual(node.bridge.posts[0], preview_body)
            self.assertEqual(node.saved[1][2]['output_format'], expected_format)
            self.assertTrue(node.saved[1][1].endswith('.'+expected_format))
            self.assertNotEqual(node.saved[1][1], str(draft_path))
            self.assertEqual(draft_path.read_bytes(), b'IMMUTABLE-DRAFT-BYTES')
            node._manual_agent_prompt_source.assert_not_called()
            node._resolve_exact_shot_generation_inputs.assert_not_called()
            node._prepare_video_references_for_run.assert_not_called()
            self.assertFalse(node._draft_ui_state()['final_available'])

        for shot in (False, True):
            for ordinary, draft, expected in ((['mp4', 'mov'], ['mp4', 'mov'], 'mov'),
                                              (['mp4'], ['mp4'], 'mp4'),
                                              (['mp4'], ['mp4', 'mov'], 'mov'),
                                              (['mp4', 'mov'], ['mp4'], 'mp4')):
                with self.subTest(shot=shot, ordinary_formats=ordinary, draft_formats=draft):
                    asyncio.run(scenario(shot, ordinary, draft, expected))

    def test_stale_shot_a_click_cannot_finalize_current_shot_b(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            node.bind(shot_uuid=SHOT_B, number=2)
            node._store_draft_source(completed_source(node, draft_job_id='job-'+'b'*32))
            with engine_loop_patch(asyncio.get_running_loop()):
                result = node._on_finalize_draft_clicked(None, None, action_id='stale-a', expected_draft_job_id=JOB)
                self.assertFalse(result.success)
                await asyncio.sleep(0)
            self.assertEqual(node.bridge.posts, [])
            self.assertFalse(node._hmb_draft_finalize_pending)
        asyncio.run(scenario())

    def test_invalid_final_capability_never_falls_back_uploads_or_posts(self):
        async def scenario(shot, failure):
            node = Node(shot=shot)
            node._store_draft_source(completed_source(node))
            if failure is None:
                node.bridge.capability_response = {}
            else:
                node.bridge.capability_error = failure
            forbid_upstream_work(node)
            build = mock.Mock(side_effect=AssertionError('Unproven Final format froze a destination'))
            node._output_file.build_file = build
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                response = node._on_finalize_draft_clicked(None, None,
                    action_id='unsupported-final-format', expected_draft_job_id=JOB)
                self.assertTrue(response.success)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
            self.assertEqual(node.bridge.posts, [])
            self.assertEqual(node.saved, [])
            self.assertEqual(node.upload_calls, 0)
            build.assert_not_called()
            node._manual_agent_prompt_source.assert_not_called()
            node._prepare_video_references_for_run.assert_not_called()
            self.assertNotIn('final_request_id', node._draft_source_record())

        for shot in (False, True):
            for failure in (None, t._BrokerError('Synthetic Final capability 401', status_code=401),
                            t._BrokerError('Synthetic Final capability 503', status_code=503)):
                with self.subTest(shot=shot, failure=repr(failure)):
                    asyncio.run(scenario(shot, failure))

    def test_switch_after_callback_before_worker_revalidation_submits_nothing(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                result = node._on_finalize_draft_clicked(None, None, action_id='before-switch', expected_draft_job_id=JOB)
                self.assertTrue(result.success)
                future = node._hmb_draft_finalize_future
                # No event-loop yield has occurred: the queued worker has not run.
                node.bind(shot_uuid=SHOT_B, number=2)
                node._store_draft_source(completed_source(node, draft_job_id='job-'+'b'*32))
                await asyncio.wrap_future(future)
            self.assertEqual(node.bridge.posts, [])
            self.assertFalse(node._hmb_draft_finalize_pending)
        asyncio.run(scenario())

    def test_inactive_or_deleted_node_and_missing_loop_do_not_schedule_final(self):
        for state in ('inactive', 'deleted', 'no_loop'):
            with self.subTest(state=state):
                node = Node()
                node._store_draft_source(completed_source(node))
                if state == 'inactive':
                    node.live = False
                elif state == 'deleted':
                    node._hmb_node_deleted = True
                with engine_loop_patch(None):
                    result = node._on_finalize_draft_clicked(None, None, expected_draft_job_id=JOB)
                self.assertFalse(result.success)
                self.assertFalse(node._hmb_draft_finalize_pending)
                self.assertEqual(node.bridge.posts, [])

    def test_rebind_during_async_preflight_is_caught_before_provider_submission(self):
        node = Node()
        source = completed_source(node)
        node._store_draft_source(source)
        original_connect = node._ensure_broker_connected
        async def switch_after_connect(**kwargs):
            result = await original_connect(**kwargs)
            node.bind(shot_uuid=SHOT_B, number=2)
            return result
        node._ensure_broker_connected = switch_after_connect
        with run_boundaries(node):
            try:
                asyncio.run(node._run_draft_final(source, 'preflight-rebind'))
            except asyncio.CancelledError:
                pass  # The actual pre-submit cancellation fence won the race.
        self.assertEqual(node.bridge.posts, [])

    def test_unsupported_draft_capability_fails_before_post_and_can_retry_once(self):
        async def scenario():
            node = Node()
            source = completed_source(node)
            node._store_draft_source(source)
            forbid_upstream_work(node)
            capability = mock.Mock(side_effect=t._BrokerProtocolError('Synthetic server has not enabled Draft'),
                                   return_value='mov')
            node.bridge.require_seedance_draft_features = capability
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                first = node._on_finalize_draft_clicked(None, None, action_id='unsupported', expected_draft_job_id=JOB)
                self.assertTrue(first.success)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
                self.assertEqual(node.bridge.posts, [])
                self.assertNotIn('final_request_id', node._draft_source_record())
                self.assertTrue(node._draft_ui_state()['final_available'])
                capability.side_effect = None
                second = node._on_finalize_draft_clicked(None, None, action_id='supported-now', expected_draft_job_id=JOB)
                self.assertTrue(second.success)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
            self.assertEqual(len(node.bridge.posts), 1, node._set_status_results.call_args_list)
        asyncio.run(scenario())

    def test_definitive_http_rejection_releases_final_intent_for_same_key_explicit_retry(self):
        async def scenario(status_code):
            node = Node()
            node._store_draft_source(completed_source(node))
            forbid_upstream_work(node)
            accepted_submit = node.bridge.generate_seedance
            rejection = t._BrokerError('Synthetic definitive create rejection',
                status_code=status_code, submission_outcome_unknown=False)
            submit = mock.Mock(side_effect=rejection)
            node.bridge.generate_seedance = submit
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                first = node._on_finalize_draft_clicked(None, None,
                    action_id='rejected', expected_draft_job_id=JOB)
                self.assertTrue(first.success)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
                self.assertEqual(submit.call_count, 1)
                first_wire = deepcopy(submit.call_args.args[0])
                self.assertTrue(rejection.definitive_submission_rejection)
                self.assertNotIn('final_request_id', node._draft_source_record())
                self.assertTrue(node._draft_ui_state()['final_available'])
                self.assertNotEqual(node._generation_recovery_state().get('status'), 'submission_unknown')
                self.assertEqual(node.parameter_output_values.get('generation_id', ''), '')
                await asyncio.sleep(0)
                self.assertEqual(submit.call_count, 1)  # No automatic retry.
                submit.side_effect = accepted_submit
                second = node._on_finalize_draft_clicked(None, None,
                    action_id='explicit-retry', expected_draft_job_id=JOB)
                self.assertTrue(second.success)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
                self.assertEqual(submit.call_count, 2)
                self.assertEqual(len(node.bridge.posts), 1)  # Exactly one accepted mock task.
                self.assertEqual(submit.call_args.args[0], first_wire)
                self.assertEqual(first_wire['draft_job_id'], JOB)
                self.assertTrue(first_wire['client_request_id'])
                self.assertFalse(node._draft_ui_state()['final_available'])
        for status_code in (400, 422):
            with self.subTest(status_code=status_code):
                asyncio.run(scenario(status_code))

    def test_after_post_unknown_retains_final_intent_and_never_automatically_resubmits(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            submit = mock.Mock(side_effect=t._BrokerError('Synthetic transport timeout after create',
                status_code=502, submission_outcome_unknown=True))
            node.bridge.generate_seedance = submit
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                first = node._on_finalize_draft_clicked(None, None, action_id='unknown', expected_draft_job_id=JOB)
                self.assertTrue(first.success)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
                self.assertEqual(submit.call_count, 1)
                self.assertIn('final_request_id', node._draft_source_record())
                self.assertFalse(node._draft_ui_state()['final_available'])
                second = node._on_finalize_draft_clicked(None, None, action_id='do-not-repeat', expected_draft_job_id=JOB)
                self.assertFalse(second.success)
                await asyncio.sleep(0)
                self.assertEqual(submit.call_count, 1)
            self.assertEqual(node._generation_recovery_state()['status'], 'submission_unknown')
        asyncio.run(scenario())

    def test_expired_draft_source_does_not_prevent_refreshing_accepted_final(self):
        node = Node()
        source = completed_source(node, created_at_ms=int(time.time()*1000)-t.DRAFT_SOURCE_TTL_MS-1,
                                  final_request_id='hmb-final-accepted')
        node._store_draft_source(source)
        final_job = 'job-'+'c'*32
        path = str(Path(node.base.name, 'existing-final-destination.mp4'))
        values = base.params(t.DRAFT_ACTION_FINAL)
        values.update(resolution='1080p', _hmb_draft_source=source,
                      _hmb_draft_project=PROJECT, _hmb_broker_server_url=ORIGIN,
                      _hmb_output_file=path, _hmb_generation_origin=source['generation_origin'])
        node._set_generation_recovery_checkpoint(stage='pre_submit', task_id='hmb-final-accepted',
            task_identity='client_request', status='submitting', params=values)
        node._set_generation_recovery_checkpoint(stage='accepted', task_id=final_job,
            task_identity='broker_task', status='pending', params=values)
        self.assertFalse(node._draft_ui_state()['final_available'])
        with run_boundaries(node):
            asyncio.run(node._refresh_async())
        self.assertEqual(node.bridge.refresh_ids, [final_job])
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(node.saved[0][1], path)

    def test_legacy_mp4_draft_starts_distinct_mov_final_without_rewriting_preview(self):
        node = Node()
        source = completed_source(node)
        node._store_draft_source(source)
        preview_path = Path(node.base.name, 'legacy-frozen-draft480p.mp4')
        preview_path.write_bytes(b'EXISTING-MP4-DRAFT-UNCHANGED')
        values = base.params(t.DRAFT_ACTION_PREVIEW)
        values.update(resolution='480p', output_format='mp4',
                      _hmb_output_file=str(preview_path), _hmb_broker_server_url=ORIGIN,
                      _hmb_draft_project=PROJECT, _hmb_generation_origin=source['generation_origin'])
        node._set_generation_recovery_checkpoint(stage='pre_submit', task_id='hmb-legacy-mp4',
            task_identity='client_request', status='submitting', params=values)
        node._set_generation_recovery_checkpoint(stage='accepted', task_id=JOB,
            task_identity='broker_task', status='succeeded', params=values)
        self.assertEqual(node._generation_recovery_state()['output_format'], 'mp4')
        forbid_upstream_work(node)
        with run_boundaries(node):
            asyncio.run(node._run_draft_final(source, 'legacy-mp4-new-mov-final'))
        self.assertEqual(len(node.bridge.posts), 1, node._set_status_results.call_args_list)
        self.assertEqual((node.bridge.posts[0]['resolution'], node.bridge.posts[0]['output_format']),
                         ('1080p', 'mov'))
        self.assertEqual(node.saved[0][2]['output_format'], 'mov')
        self.assertTrue(node.saved[0][1].endswith('.mov'))
        self.assertNotEqual(node.saved[0][1], str(preview_path))
        self.assertEqual(preview_path.read_bytes(), b'EXISTING-MP4-DRAFT-UNCHANGED')
        node._manual_agent_prompt_source.assert_not_called()
        node._prepare_video_references_for_run.assert_not_called()

    def test_completed_preview_publishes_shot_source_and_enables_final_without_post(self):
        node = Node()
        origin = node._capture_generated_video_origin()
        # A real Draft records submission time before remote generation. The
        # journal's monotonically increasing update time is not its start time.
        started_at_ms = int(time.time()*1000)-1000
        node.parameter_values['draft_action'] = t.DRAFT_ACTION_PREVIEW
        values = base.params(t.DRAFT_ACTION_PREVIEW)
        values.update(resolution='480p', _hmb_draft_project=PROJECT, _hmb_broker_server_url=ORIGIN,
                      _hmb_generation_origin=origin, _hmb_draft_source_bindings={'image_asset': PUBLISHER},
                      _hmb_draft_started_at_ms=started_at_ms)
        node._set_generation_recovery_checkpoint(stage='pre_submit', task_id='hmb-preview',
            task_identity='client_request', status='submitting', params=values)
        node._set_generation_recovery_checkpoint(stage='remote_succeeded', task_id=JOB,
            task_identity='broker_task', status='succeeded', params=values)
        path = Path(node.base.name, 'verified-boundary-draft480p.mp4')
        path.write_bytes(b'SYNTHETIC-VERIFIED-PUBLICATION-BOUNDARY')
        saved = SimpleNamespace(location=str(path), name=path.name, resolve=lambda: str(path))
        with mock.patch.object(node, '_extract_video_url', return_value='https://synthetic.invalid/draft.mp4'), \
             mock.patch.object(node, '_download_broker_video', new=mock.AsyncMock(return_value=b'boundary-fixture')), \
             mock.patch.object(node, '_atomic_publish_completed_video', new=mock.AsyncMock(return_value=saved)), \
             mock.patch.object(node, '_publish_generation_preview'), \
             mock.patch.object(node, '_schedule_review_sync'), \
             mock.patch.object(t._review, 'update_case'), \
             mock.patch.object(t._shot_routing, 'reconcile_completed_video_routes'):
            asyncio.run(t.HMBSeedanceGeneration._save_completed_task(node, {}, JOB, node.destination,
                model_id=t.SEEDANCE_2_5_MODEL_ID, output_format='mp4', return_last_frame=False))
        source = node._draft_source_record()
        self.assertEqual(source['draft_job_id'], JOB)
        self.assertEqual(source['generation_origin'], origin)
        self.assertEqual(source['source_bindings'], {'image_asset': PUBLISHER})
        self.assertIs(source['completed'], True)
        self.assertEqual(source['created_at_ms'], started_at_ms)
        self.assertTrue(node._draft_ui_state()['final_available'])
        self.assertEqual((node.get_parameter_value('resolution'), node.get_parameter_value('draft_action')),
                         ('480p', t.DRAFT_ACTION_PREVIEW))
        published = node.get_parameter_value(t.GENERATED_VIDEO_SOURCE_PARAMETER)
        self.assertEqual((published['channel_uuid'], published['shot_uuid'], published['generation_id']),
                         (CHANNEL, SHOT_A, JOB))
        self.assertEqual(published['source_node_instance_id'], origin['source_node_instance_id'])
        self.assertEqual(node.bridge.posts, [])
        self.assertEqual(path.read_bytes(), b'SYNTHETIC-VERIFIED-PUBLICATION-BOUNDARY')

    def test_runtime_registration_must_still_belong_to_exact_node(self):
        node = Node()
        for registered in (None, object()):
            with self.subTest(registered=registered), mock.patch.object(t.GriptapeNodes, 'NodeManager',
                    return_value=SimpleNamespace(get_node_by_name=lambda _name: registered)):
                self.assertFalse(t.HMBSeedanceGeneration._runtime_node_is_live(node, require_registered=True))
        with mock.patch.object(t.GriptapeNodes, 'NodeManager',
                return_value=SimpleNamespace(get_node_by_name=lambda _name: node)):
            self.assertTrue(t.HMBSeedanceGeneration._runtime_node_is_live(node, require_registered=True))

    def test_running_or_unknown_flow_state_blocks_callback_without_post(self):
        async def scenario():
            for manager in (SimpleNamespace(check_for_existing_running_flow=lambda: True), SimpleNamespace()):
                with self.subTest(manager=manager):
                    node = Node()
                    node._store_draft_source(completed_source(node))
                    with engine_loop_patch(asyncio.get_running_loop()), \
                         mock.patch.object(t.GriptapeNodes, 'FlowManager', return_value=manager):
                        result = node._on_finalize_draft_clicked(None, None, expected_draft_job_id=JOB)
                        self.assertFalse(result.success)
                    self.assertEqual(node.bridge.posts, [])
        asyncio.run(scenario())

    def test_live_clone_cannot_reuse_another_generators_durable_owner(self):
        original = Node()
        source = completed_source(original)
        original._store_draft_source(source)
        cloned = Node()
        cloned.parameter_values[t.DRAFT_OWNER_PARAMETER] = source['owner_id']
        cloned.parameter_values[t.DRAFT_SOURCES_PARAMETER] = deepcopy(
            original.get_parameter_value(t.DRAFT_SOURCES_PARAMETER))
        with self.assertRaises(ValueError):
            cloned._validated_draft_final_source(source)
        self.assertNotEqual(cloned._draft_owner_id(), source['owner_id'])
        self.assertEqual(original._validated_draft_final_source(), source)

    def test_picker_identity_check_never_validates_or_uploads_media(self):
        node = Node()
        source = completed_source(node, source_bindings={'video_picker': PUBLISHER})
        picker = SimpleNamespace(_hmb_node_deleted=False,
            _hmb_shot_channel_subscription=lambda: {
                'participant_kind': 'video_picker', 'enabled': True, 'channel_uuid': CHANNEL})
        picker._hmb_shot_routing_snapshot = mock.Mock(return_value={
            'channel_uuid': CHANNEL, 'publisher_instance_uuid': PUBLISHER,
            'shots': [{'shot_uuid': SHOT_A}]})
        node._exact_incoming_source = lambda parameter, port, **kwargs: (
            picker if parameter == t.SHOT_PICKER_INPUT_PARAMETER else None)
        self.assertEqual(node._validated_draft_final_source(source), source)
        picker._hmb_shot_routing_snapshot.assert_called_once_with(CHANNEL, validate_media=False)
        self.assertEqual(node.upload_calls, 0)

    def test_ordinary_run_cannot_overtake_pending_final_on_same_node(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            forbid_upstream_work(node)
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                response = node._on_finalize_draft_clicked(None, None,
                    action_id='final-owns-pending', expected_draft_job_id=JOB)
                self.assertTrue(response.success)
                future = node._hmb_draft_finalize_future
                # This task is not the queued Final worker. It must leave the
                # pending Final's authoring context and reservation untouched.
                await node.aprocess()
                self.assertEqual(node.bridge.posts, [])
                self.assertTrue(node._hmb_draft_finalize_pending)
                await asyncio.wrap_future(future)
            self.assertEqual(len(node.bridge.posts), 1)
            self.assertIn('draft_job_id', node.bridge.posts[0])
            self.assertFalse(node._hmb_draft_finalize_pending)
            self.assertFalse(node._generation_run_active.is_set())
        asyncio.run(scenario())

    def test_queued_stop_cancels_before_post_and_new_explicit_click_clears_old_stop(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                first = node._on_finalize_draft_clicked(None, None,
                    action_id='queue-then-stop', expected_draft_job_id=JOB)
                self.assertTrue(first.success)
                future = node._hmb_draft_finalize_future
                self.assertTrue(node._draft_ui_state()['cancel_available'])
                self.assertEqual(node._draft_ui_state()['active_job_id'], JOB)
                self.assertTrue(node._cancel_draft_final(JOB).success)
                try:
                    await asyncio.wrap_future(future)
                except asyncio.CancelledError:
                    pass
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                self.assertEqual(node.bridge.posts, [])
                self.assertFalse(node._hmb_draft_finalize_pending)
                self.assertNotIn('final_request_id', node._draft_source_record())
                self.assertTrue(node.is_cancellation_requested)
                retry = node._on_finalize_draft_clicked(None, None,
                    action_id='fresh-explicit-click', expected_draft_job_id=JOB)
                self.assertTrue(retry.success)
                self.assertFalse(node.is_cancellation_requested)
                await asyncio.wrap_future(node._hmb_draft_finalize_future)
            self.assertEqual(len(node.bridge.posts), 1)
        asyncio.run(scenario())

    def test_active_shot_a_can_be_stopped_from_shot_b_but_wrong_id_cannot_cancel(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                result = node._on_finalize_draft_clicked(None, None,
                    action_id='a-active', expected_draft_job_id=JOB)
                self.assertTrue(result.success)
                future = node._hmb_draft_finalize_future
                node.bind(shot_uuid=SHOT_B, number=2)
                second_job = 'job-'+'b'*32
                node._store_draft_source(completed_source(node, draft_job_id=second_job))
                self.assertEqual(node._draft_ui_state()['active_job_id'], JOB)
                self.assertFalse(node._cancel_draft_final(second_job).success)
                self.assertTrue(node._cancel_draft_final(JOB).success)
                try:
                    await asyncio.wrap_future(future)
                except asyncio.CancelledError:
                    pass
                await asyncio.sleep(0)
                await asyncio.sleep(0)
            self.assertEqual(node.bridge.posts, [])
            self.assertEqual(node._draft_source_record()['draft_job_id'], second_job)
        asyncio.run(scenario())

    def test_accepted_final_stop_preserves_same_task_for_refresh_without_new_post(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            final_job = 'job-'+'c'*32
            node.bridge.generate_seedance = mock.Mock(return_value={'id': final_job, 'status': 'queued'})
            accepted = asyncio.Event()
            original_save = node._force_save_generation_recovery_checkpoint
            held = False
            async def hold_after_acceptance(**kwargs):
                nonlocal held
                if not held and node._generation_recovery_state().get('task_id') == final_job:
                    held = True
                    accepted.set()
                    await asyncio.Event().wait()
                return await original_save(**kwargs)
            node._force_save_generation_recovery_checkpoint = hold_after_acceptance
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                result = node._on_finalize_draft_clicked(None, None,
                    action_id='accepted-stop', expected_draft_job_id=JOB)
                self.assertTrue(result.success)
                future = node._hmb_draft_finalize_future
                await asyncio.wait_for(accepted.wait(), timeout=3)
                self.assertEqual(node._generation_recovery_state()['task_id'], final_job)
                self.assertTrue(node._cancel_draft_final(JOB).success)
                try:
                    await asyncio.wrap_future(future)
                except asyncio.CancelledError:
                    pass
                await await_final_idle(node)
                self.assertEqual(node.bridge.generate_seedance.call_count, 1)
                self.assertEqual(node._generation_recovery_state()['task_id'], final_job)
                node._force_save_generation_recovery_checkpoint = original_save
                node.clear_cancellation()
                await node._refresh_async()
            self.assertEqual(node.bridge.generate_seedance.call_count, 1)
            self.assertEqual(node.bridge.refresh_ids, [final_job])
            self.assertEqual(node.saved[0][0], final_job)
        asyncio.run(scenario())

    def test_node_deletion_cancels_queued_final_without_submission(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            with run_boundaries(node), engine_loop_patch(asyncio.get_running_loop()):
                result = node._on_finalize_draft_clicked(None, None,
                    action_id='delete-queued', expected_draft_job_id=JOB)
                self.assertTrue(result.success)
                future = node._hmb_draft_finalize_future
                with mock.patch.object(node, '_discard_dangling_owned_list_connections_before_delete'), \
                     mock.patch.object(node, '_retire_deleted_generation_recovery'), \
                     mock.patch.object(t._shot_routing, 'schedule_post_deletion_reconcile'):
                    t.HMBSeedanceGeneration.after_node_deleted(node)
                try:
                    await asyncio.wrap_future(future)
                except asyncio.CancelledError:
                    pass
                await asyncio.sleep(0)
                await asyncio.sleep(0)
            self.assertTrue(node._hmb_node_deleted)
            self.assertTrue(future.cancelled())
            self.assertEqual(node.bridge.posts, [])
        asyncio.run(scenario())

    def test_missing_expected_id_cannot_start_final(self):
        async def scenario():
            node = Node()
            node._store_draft_source(completed_source(node))
            with engine_loop_patch(asyncio.get_running_loop()):
                result = node._on_finalize_draft_clicked(None, None, action_id='missing-id')
                self.assertFalse(result.success)
            self.assertEqual(node.bridge.posts, [])
        asyncio.run(scenario())


if __name__ == '__main__':
    t.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.0
    unittest.main()
