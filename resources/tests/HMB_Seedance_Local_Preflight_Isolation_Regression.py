"""Local render admission preserves independent shots and existing paid tasks."""
from __future__ import annotations
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import unittest

TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('local_preflight_graph_fixture', TESTS / 'HMB_Seedance_Only_Project_Selection_Regression.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
t = fixture.t

def node(error=None, *, existing=False):
    value = t.HMBSeedanceGeneration.__new__(t.HMBSeedanceGeneration)
    value.name = 'Preflight isolated shot'
    value.parameter_values = {}
    value.get_parameter_value = value.parameter_values.get
    value.parameter_output_values = {'generation_id': 'job-existing', 'generation_status': 'succeeded',
                                    'video_url': 'original.mov', 'VIDEO_OUT': 'original.mov'} if existing else {}
    value._runtime_node_is_live = lambda **kwargs: True
    value._clear_execution_status = mock.Mock()
    value._get_parameters_for_start_validation = mock.Mock(return_value={'model_id': t.SEEDANCE_2_5_MODEL_ID})
    value._validate_parameters = mock.Mock(side_effect=error)
    value._validate_broker_model = mock.Mock()
    value._prepare_managed_agent_shot = mock.AsyncMock()
    value._assert_agent_result_available = mock.Mock()
    value._process_generation = mock.AsyncMock()
    value._generation_recovery_state = lambda: {
        'task_id': 'job-existing', 'status': 'succeeded', 'stage': 'local_succeeded'} if existing else {}
    value._publish_generation_preview = mock.Mock()
    value._set_generation_status = mock.Mock()
    value._set_status_results = mock.Mock()
    value._safe_exception_message = str
    return value

class LocalPreflightTests(unittest.TestCase):
    def test_upstream_resolve_can_never_silently_change_the_clicked_image_order(self):
        value = node()
        active = ('channel', 'shot-3')
        images = {active: ('project:one', 'import:saved', 'project:two')}
        value._shot_identity = lambda: dict(channel_uuid=active[0], shot_uuid=active[1])
        source = SimpleNamespace(_hmb_render_selected_image_uids=lambda channel, shot: images[(channel, shot)])
        edge = SimpleNamespace(target_node=value, source_node=source, source_parameter=SimpleNamespace(name='SHOT_ASSET_OUT'))
        dag = {}
        graph = SimpleNamespace(incoming_index={value.name: {t.SHOT_ASSET_INPUT_PARAMETER: [1]}}, connections={1: edge})
        flow = SimpleNamespace(flows=SimpleNamespace(connections=graph, global_dag_builder=SimpleNamespace(node_to_reference=dag)))
        with (mock.patch.object(t.HMBSeedanceGeneration, 'workflow', flow, create=True),
              mock.patch.object(t.SuccessFailureNode, 'validate_before_workflow_run', return_value=None, create=True)):
            value.validate_before_workflow_run()
            dag[value.name] = object()
            images[active] = ('project:one', 'project:two', 'import:replacement')
            # A concurrent validation while the node is queued cannot bless
            # the replacement. Both the managed model and submission stay idle.
            value.validate_before_workflow_run()
            asyncio.run(value._aprocess_impl())
            value._prepare_managed_agent_shot.assert_not_awaited()
            value._process_generation.assert_not_awaited()
            self.assertIn('이미지 목록', value._hmb_local_preflight_failure)

            # Explicitly clicking again accepts the now-visible selection.
            dag.clear()
            value.validate_before_workflow_run()
            dag[value.name] = object()
            images[('channel', 'shot-4')] = ('import:other',)
            asyncio.run(value._aprocess_impl())
            value._prepare_managed_agent_shot.assert_awaited_once()
            value._process_generation.assert_awaited_once()

    def tearDown(self):
        while fixture.base.TEMPORARIES:
            fixture.base.TEMPORARIES.pop().cleanup()

    def test_hmb_admission_does_not_reject_entire_workflow_or_node_schedule(self):
        value = node(ValueError('Selected Shot is waiting'))
        for hook in ('validate_before_workflow_run', 'validate_before_node_run'):
            with mock.patch.object(t.SuccessFailureNode, hook, return_value=None, create=True):
                self.assertIsNone(getattr(value, hook)())
                self.assertEqual(value._hmb_local_preflight_failure, 'Selected Shot is waiting')
        value._prepare_managed_agent_shot.assert_not_called()
        value._process_generation.assert_not_called()

    def test_native_structural_validation_errors_remain_authoritative(self):
        value = node(ValueError('HMB local admission'))
        native_error = TypeError('Native structural contract')
        for hook in ('validate_before_workflow_run', 'validate_before_node_run'):
            with mock.patch.object(t.SuccessFailureNode, hook, return_value=[native_error], create=True):
                self.assertEqual(getattr(value, hook)(), [native_error])
        self.assertEqual(value._hmb_local_preflight_failure, 'HMB local admission')

    def test_sdk_validation_worker_leaves_routing_to_the_engine_loop(self):
        value = node(ValueError('Selected Shot is waiting'))
        engine = SimpleNamespace(event_manager=SimpleNamespace(event_loop=None))

        async def run():
            engine.event_manager.event_loop = asyncio.get_running_loop()
            native_error = TypeError('Native structural contract')
            with mock.patch.object(t.HMBSeedanceGeneration, 'engine', new=engine, create=True):
                for hook in ('validate_before_workflow_run', 'validate_before_node_run'):
                    with mock.patch.object(t.SuccessFailureNode, hook, return_value=[native_error], create=True):
                        self.assertEqual(await asyncio.to_thread(getattr(value, hook)), [native_error])
                value._get_parameters_for_start_validation.assert_not_called()
                value._process_generation.assert_not_called()
                await value._aprocess_impl()
                value._get_parameters_for_start_validation.assert_called_once()
                self.assertIn('Selected Shot is waiting', value._set_status_results.call_args.kwargs['result_details'])
                value._process_generation.assert_not_called()

        asyncio.run(run())

    def test_each_invalid_shot_is_skipped_before_agent_or_provider(self):
        for error in (ValueError('waiting for original library binding'),
                      t._ProjectSelectionRequired('Select Project'),
                      t._AgentResultUnavailable('Only mode cannot run the shared HMB Shot Agent'),
                      ValueError('Unsupported model'), RuntimeError('Shot UUID mismatch')):
            with self.subTest(error=str(error)):
                value = node(error)
                asyncio.run(value._aprocess_impl())
                value._prepare_managed_agent_shot.assert_not_called()
                value._process_generation.assert_not_called()
                status = value._set_status_results.call_args.kwargs
                self.assertFalse(status['was_successful'])
                self.assertIn('SKIPPED:', status['result_details'])
                self.assertIn('before Agent execution or submission', status['result_details'])
                self.assertIn(str(error), status['result_details'])

    def test_five_independent_execution_boundaries_continue_for_healthy_peers(self):
        values = [node(ValueError('Shot missing')), *[node() for _ in range(4)]]
        async def run():
            await asyncio.gather(*(value._aprocess_impl() for value in values))
        asyncio.run(run())
        self.assertEqual([value._prepare_managed_agent_shot.await_count for value in values], [0, 1, 1, 1, 1])
        self.assertEqual([value._process_generation.await_count for value in values], [0, 1, 1, 1, 1])

    def test_repaired_binding_is_revalidated_instead_of_replaying_cached_failure(self):
        value = node(ValueError('Temporary missing Shot'))
        value._record_local_render_preflight()
        self.assertTrue(value._hmb_local_preflight_failure)
        value._validate_parameters.side_effect = None
        asyncio.run(value._aprocess_impl())
        self.assertEqual(value._hmb_local_preflight_failure, '')
        value._prepare_managed_agent_shot.assert_awaited_once()
        value._process_generation.assert_awaited_once()

    def test_preparing_media_waits_before_agent_and_submission(self):
        for flag in ('hmb_picker_media_preparing', 'hmb_image_asset_selection_preparing', 'hmb_sound_preparing'):
            with self.subTest(flag=flag):
                value = node()
                pending = ValueError('pending media')
                setattr(pending, flag, True)
                value._validate_parameters.side_effect = [pending, None]
                value._capture_imageasset_project_selection = mock.Mock(return_value={'owner': 'A'})
                value._assert_imageasset_project_selection = mock.Mock()
                with mock.patch.object(type(value), 'is_cancellation_requested', False, create=True):
                    asyncio.run(value._aprocess_impl())
                value._assert_imageasset_project_selection.assert_called_once_with({'owner': 'A'})
                value._prepare_managed_agent_shot.assert_awaited_once()
                value._process_generation.assert_awaited_once()

    def test_changed_binding_while_preparing_cannot_submit(self):
        value = node()
        pending = ValueError('pending media')
        pending.hmb_picker_media_preparing = True
        value._validate_parameters.side_effect = pending
        value._capture_imageasset_project_selection = lambda: {'owner': 'A'}
        value._assert_imageasset_project_selection = mock.Mock(side_effect=ValueError('binding changed'))
        with mock.patch.object(type(value), 'is_cancellation_requested', False, create=True):
            asyncio.run(value._aprocess_impl())
        value._prepare_managed_agent_shot.assert_not_awaited()
        value._process_generation.assert_not_awaited()

    def test_accepted_edit_finishes_before_its_shot_locks_for_inference(self):
        value = node()
        scope = {"channel_uuid": "channel", "shot_uuid": "A"}
        value._hmb_requested_edit_shot = scope
        value._hmb_running_edit_shot = None
        value._shot_identity = lambda: dict(scope)
        events = []
        async def finish_edit():
            self.assertIsNone(value._hmb_running_edit_shot)
            events.append("edit")
        value._await_local_render_preflight = finish_edit
        value._sync_render_edit_lock = lambda _: events.append(("lock",value._hmb_running_edit_shot))
        value._prepare_managed_agent_shot = mock.AsyncMock(side_effect=lambda: events.append("agent"))
        asyncio.run(value._aprocess_impl())
        self.assertEqual(events, ["edit", ("lock", scope), "agent"])
        value._process_generation.assert_awaited_once()

        value._hmb_running_edit_shot = None
        value._shot_identity = lambda: dict(scope, shot_uuid="B")
        value._prepare_managed_agent_shot.reset_mock()
        value._process_generation.reset_mock()
        events.clear()
        asyncio.run(value._aprocess_impl())
        self.assertEqual(events, ["edit"])
        value._prepare_managed_agent_shot.assert_not_awaited()
        value._process_generation.assert_not_awaited()

    def test_sound_ticket_scope_preserves_order_and_ignores_other_shot(self):
        scope = dict(channel_uuid='channel', shot_uuid='A')
        rows = [{**scope, 'instance_id': i, 'gain_db': 0} for i in (1, 2)]
        before = dict(project_uid='project', tracks=rows, revision=1)
        view = t.HMBSeedanceGeneration._shot_sound_controls
        expected = view(before, scope)
        self.assertEqual(expected, view(dict(before, tracks=[*rows, {**rows[0], 'shot_uuid': 'B'}], revision=2), scope))
        for changed in (dict(before, tracks=list(reversed(rows))), dict(before, tracks=rows[:1]),
                        dict(before, tracks=[dict(rows[0], gain_db=-3), rows[1]]),
                        dict(before, project_uid='other'), dict(before, preparing=True)):
            self.assertNotEqual(expected, view(changed, scope))

    def test_existing_video_and_task_are_preserved_when_a_new_render_is_skipped(self):
        value = node(ValueError('Current binding unavailable'), existing=True)
        before = dict(value.parameter_output_values)
        asyncio.run(value._aprocess_impl())
        self.assertEqual(value.parameter_output_values, before)
        value._set_generation_status.assert_not_called()
        value._publish_generation_preview.assert_called_once_with('failed', generation_id='job-existing', action='refresh_existing')
        self.assertIn('Existing task job-existing is preserved', value._set_status_results.call_args.kwargs['result_details'])
        value._process_generation.assert_not_called()

    def test_resume_input_still_bypasses_model_submission_admission(self):
        value = node()
        value._get_parameters_for_start_validation.return_value = {'resume_generation_id': 'job-existing'}
        self.assertEqual(value._validate_local_render_preflight(), {'resume_generation_id': 'job-existing'})
        value._validate_broker_model.assert_not_called()

if __name__ == '__main__':
    unittest.main()
