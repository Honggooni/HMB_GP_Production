"""Explicit mode, disconnect/rebind and stale selection guards; no provider I/O."""
from __future__ import annotations
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('explicit_mode_fixture', TESTS / 'HMB_Seedance_Only_Project_Selection_Regression.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
t = fixture.t
CHANNEL = '10000000-0000-4000-8000-000000000001'
PUBLISHER = '20000000-0000-4000-8000-000000000001'
SHOT = '30000000-0000-4000-8000-000000000001'
OTHER = '30000000-0000-4000-8000-000000000002'


def catalog(shot=SHOT, *, channel=CHANNEL, generation=1, name='Authored asset A'):
    rows = [dict(shot_uuid=shot, number=1, name=name, revision=generation)]
    document = dict(channel_uuid=channel, generation=generation, shots=rows)
    return dict(schema='hmb-shot-routing-catalog', version=1, publisher_instance_uuid=PUBLISHER,
                **document, metadata_sha256=t.HMBSeedanceGeneration._canonical_sha256(document))


class Node(fixture.Node):
    _hmb_shot_channel_subscription = t.HMBSeedanceGeneration._hmb_shot_channel_subscription

    def __init__(self):
        super().__init__(fixture.values_for(t.TASK_REFERENCE_TO_VIDEO))
        self.metadata = {'library': 'HMB_GP_Production', 'node_type': 'HMBSeedanceGeneration', 'retained': {'zero': 0, 'off': False}}
        self.parameter_values[t.SHOT_AUTOCLAIM_ENABLED_PARAMETER] = True
        self.parameter_values['prompt'] = 'literal {{SIGN}} 한글'
        self.parameter_values['resolution'] = '480p'
        self.parameter_values['output_file'] = 'custom.mov'
        self._manual_agent_prompt_source = mock.Mock(return_value=None)

    def _hmb_available_seedance_shot_catalog(self, value):
        return deepcopy(value)

    def _sync_seedance_shot_widget(self, **kwargs):
        # Geometry/preview publication has separate real SDK/browser checks.
        pass

    def bind(self, shot=SHOT):
        self._hmb_shot_catalog_snapshot = catalog(shot)
        self._hmb_commit_seedance_mode(shot)
        self._apply_seedance_shot_selection(shot, fallback_to_available=False)

    def choose_only(self):
        self._hmb_commit_seedance_mode()
        self._hmb_suspended_shot_identity = None
        self.parameter_values[t.SHOT_AUTOCLAIM_ENABLED_PARAMETER] = False
        self._apply_seedance_shot_selection('', fallback_to_available=False)


class ExplicitOnlyModeTests(unittest.TestCase):
    def tearDown(self):
        while fixture.base.TEMPORARIES:
            fixture.base.TEMPORARIES.pop().cleanup()

    def test_only_overrides_late_durable_quartet_without_changing_authored_values(self):
        node = Node(); node.bind(); node.choose_only()
        before = {key: deepcopy(node.parameter_values.get(key)) for key in ('prompt', 'resolution', 'output_file', 'reference_images', 'video_references', t.DRAFT_SOURCE_PARAMETER)}
        node.parameter_values.update({t.SHOT_CHANNEL_UUID_PARAMETER: CHANNEL, t.SHOT_UUID_PARAMETER: SHOT,
                                      t.SHOT_SELECTOR_PARAMETER: '01 · Authored asset A'})
        self.assertEqual(node._hmb_seedance_execution_mode(), 'only')
        self.assertFalse(node._hmb_shot_channel_subscription()['enabled'])
        node._hmb_reconcile_shot_routing(catalog(generation=2))
        self.assertEqual(node._hmb_seedance_execution_mode(), 'only')
        self.assertEqual(node._shot_identity()['shot_uuid'], '')
        self.assertEqual(before, {key: node.parameter_values.get(key) for key in before})

    def test_only_remains_only_after_delete_new_uuid_and_new_channel(self):
        node = Node(); node.choose_only()
        for snapshot in (catalog(), catalog(OTHER, generation=2), catalog(channel=PUBLISHER, generation=3)):
            node._hmb_clear_shot_routing_catalog()
            node._hmb_reconcile_shot_routing(snapshot)
            self.assertEqual(node._hmb_seedance_execution_mode(), 'only')
            self.assertFalse(node._hmb_shot_channel_subscription()['enabled'])

    def test_metadata_first_cold_restore_cannot_be_overwritten_by_saved_raw_shot(self):
        first = Node(); first.bind(); first.choose_only()
        restored = Node(); restored.metadata = json.loads(json.dumps(first.metadata))
        restored.parameter_values.update({t.SHOT_CHANNEL_UUID_PARAMETER: CHANNEL, t.SHOT_UUID_PARAMETER: SHOT})
        self.assertEqual(restored._hmb_seedance_execution_mode(), 'only')
        self.assertFalse(restored._hmb_shot_channel_subscription()['enabled'])
        self.assertEqual(restored.metadata['retained'], {'zero': 0, 'off': False})
        self.assertNotEqual(first._hmb_mode_instance_id, restored._hmb_mode_instance_id)

    def test_shot_disconnect_waits_and_same_uuid_restores_with_renamed_metadata(self):
        node = Node(); node.bind()
        node._hmb_clear_shot_routing_catalog()
        self.assertEqual(node._hmb_seedance_execution_mode(), 'waiting')
        self.assertFalse(node._draft_only_mode())
        node._hmb_reconcile_shot_routing(catalog(generation=2, name='Renamed original'))
        self.assertEqual(node._hmb_seedance_execution_mode(), 'shot')
        self.assertEqual(node._shot_identity()['shot_name'], 'Renamed original')

    def test_waiting_never_borrows_same_number_new_uuid_or_other_channel(self):
        node = Node(); node.bind(); node._hmb_clear_shot_routing_catalog()
        for snapshot in (catalog(OTHER, generation=2), catalog(channel=PUBLISHER, generation=3)):
            node._hmb_reconcile_shot_routing(snapshot)
            self.assertEqual(node._hmb_seedance_execution_mode(), 'waiting')
            self.assertEqual(node._hmb_seedance_requested_shot_identity()['shot_uuid'], SHOT)

    def test_mode_widget_revisions_advance_only_for_their_own_changes(self):
        node = Node(); node.bind()
        before = node._hmb_seedance_mode_widget_fields()
        self.assertEqual(before, node._hmb_seedance_mode_widget_fields())
        node._hmb_clear_shot_routing_catalog()
        pending = node._hmb_seedance_mode_widget_fields()
        self.assertEqual(pending['execution_mode_revision'], before['execution_mode_revision'])
        self.assertGreater(pending['execution_mode_state_revision'], before['execution_mode_state_revision'])
        node.choose_only()
        only = node._hmb_seedance_mode_widget_fields()
        self.assertGreater(only['execution_mode_revision'], pending['execution_mode_revision'])
        self.assertEqual(only['requested_mode'], 'only')

    def test_explicit_only_skips_shared_shot_router_and_ignores_stale_hidden_asset(self):
        node = Node(); node.choose_only(); node.select('katuri8')
        graph = fixture.Graph(node)
        graph.direct(hidden=True, project='superwings12')
        node._reconcile_shared_shot_routing = mock.Mock(side_effect=AssertionError('Only entered shared Shot router'))
        authored = deepcopy(node.values)
        with graph.context():
            resolved = node._resolve_exact_shot_generation_inputs(authored)
        self.assertEqual(resolved['_hmb_generation_mode'], 'only')
        self.assertEqual(resolved['project_id'], 'katuri8')
        for key in ('prompt', 'resolution', 'video_references', 'reference_images', 'generate_audio'):
            self.assertEqual(resolved[key], authored[key])
        node._reconcile_shared_shot_routing.assert_not_called()
        self.assertEqual(node.transport.calls, [])

    def test_only_project_is_still_required_and_manual_image_project_still_validated(self):
        node = Node(); node.choose_only(); graph = fixture.Graph(node)
        with graph.context(), self.assertRaises(t._ProjectSelectionRequired):
            node._capture_imageasset_project_selection()
        node.select('katuri8'); graph.direct(project='superwings12')
        with graph.context(), self.assertRaisesRegex(ValueError, 'does not match'):
            node._capture_imageasset_project_selection()

    def test_mode_change_invalidates_in_flight_project_guard_before_post(self):
        node = Node(); node.choose_only(); node.select('katuri8'); graph = fixture.Graph(node)
        with graph.context():
            selection = node._capture_imageasset_project_selection()
            node._hmb_commit_seedance_mode()
            # Reselecting the same Only is an idempotent author action, not
            # a reason to fail an otherwise unchanged in-flight operation.
            node._assert_imageasset_project_selection(selection)
            node.bind()
            with self.assertRaises(t._ProjectSelectionChanged):
                node._assert_imageasset_project_selection(selection)
        self.assertEqual(node.transport.calls, [])

    def test_only_rejects_shared_agent_before_calling_shot_document(self):
        node = Node(); node.choose_only()
        manager = SimpleNamespace(_hmb_shot_manager_enabled=lambda: True,
                                  _hmb_manager_prompt_owner=mock.Mock(side_effect=AssertionError('Shot document entered')))
        node._manual_agent_prompt_source.return_value = manager
        with self.assertRaisesRegex(t._AgentResultUnavailable, 'Only mode cannot run'):
            asyncio.run(node._prepare_managed_agent_shot())
        manager._hmb_manager_prompt_owner.assert_not_called()

    def test_only_allows_native_prompt_sources_and_resume_final_keep_their_bypass(self):
        node = Node(); node.choose_only()
        node._manual_agent_prompt_source.return_value = SimpleNamespace(output='native prompt')
        node._assert_only_mode_inputs()
        node.parameter_values['resume_generation_id'] = 'job-existing'
        node._manual_agent_prompt_source.side_effect = AssertionError('Existing task inspected upstream')
        asyncio.run(node._prepare_managed_agent_shot())

    def test_malformed_and_future_intent_wait_instead_of_auto_claiming(self):
        for raw in ({'schema': t.SEEDANCE_EXECUTION_MODE_SCHEMA, 'version': 2},
                    {'schema': t.SEEDANCE_EXECUTION_MODE_SCHEMA, 'version': 1, 'mode': 'only', 'revision': True},
                    *({'schema': t.SEEDANCE_EXECUTION_MODE_SCHEMA, 'version': 1, 'mode': value, 'revision': 1}
                      for value in ([], {}, None, False, 1))):
            node = Node(); node.metadata[t.SEEDANCE_EXECUTION_MODE_METADATA] = raw
            self.assertEqual(node._hmb_seedance_execution_mode(), 'waiting')
            node._hmb_reconcile_shot_routing(catalog())
            self.assertEqual(node._shot_identity()['shot_uuid'], '')

    def test_workflow_records_local_admission_and_preserves_same_task_bypass(self):
        node = Node(); node.choose_only()
        node._draft_final_requested = lambda: False
        manager = SimpleNamespace(_hmb_shot_manager_enabled=lambda: True)
        node._manual_agent_prompt_source.return_value = manager
        # This graph fixture has no native parameter converters. Keep its
        # admission boundary real while native StartFlow/save tests exercise
        # the complete parameter contract in the installed SDK.
        def inputs():
            if node.get_parameter_value('resume_generation_id') or node._draft_final_requested():
                return {'resume_generation_id': 'job-existing'}
            if node._hmb_seedance_execution_mode() == 'waiting':
                raise ValueError('waiting for its original library binding')
            node._assert_only_mode_inputs()
            return {'model_id': t.SEEDANCE_2_5_MODEL_ID}
        node._get_parameters_for_start_validation = inputs
        node._validate_parameters = lambda params: None
        node._validate_broker_model = lambda model: None
        node._safe_exception_message = str
        with mock.patch.object(t.SuccessFailureNode, 'validate_before_workflow_run', return_value=None, create=True):
            self.assertIsNone(node.validate_before_workflow_run())
            self.assertIn('Only mode cannot run', node._hmb_local_preflight_failure)
            node.parameter_values['resume_generation_id'] = 'job-existing'
            self.assertIsNone(node.validate_before_workflow_run())
            self.assertEqual(node._hmb_local_preflight_failure, '')
            node.parameter_values['resume_generation_id'] = ''
            node._draft_final_requested = lambda: True
            self.assertIsNone(node.validate_before_workflow_run())
            self.assertEqual(node._hmb_local_preflight_failure, '')
            node._draft_final_requested = lambda: False
            node._manual_agent_prompt_source.return_value = None
            self.assertIsNone(node.validate_before_workflow_run())
            node.bind(); node._hmb_shot_catalog_snapshot = None
            self.assertIsNone(node.validate_before_workflow_run())
            self.assertIn('waiting for its original library binding', node._hmb_local_preflight_failure)

    def test_legacy_without_new_metadata_preserves_fresh_autoclaim(self):
        node = Node()
        self.assertEqual(node._hmb_seedance_execution_mode(), 'auto')
        node._hmb_reconcile_shot_routing(catalog())
        self.assertEqual(node._shot_identity()['shot_uuid'], SHOT)
        self.assertNotIn(t.SEEDANCE_EXECUTION_MODE_METADATA, node.metadata)

    def edit(self, node, shot='', *, fields=None):
        node._generation_preview_for_widget = lambda: {}
        node._draft_ui_state = lambda: {}
        node._update_parameter_visibility = lambda: None
        fields = fields or node._hmb_seedance_mode_widget_fields()
        value = t._seedance_widget_value({'channel_uuid': CHANNEL if shot else '', 'shot_uuid': shot},
                                         node._hmb_shot_catalog_snapshot)
        value.update(fields)
        value['selection_request'] = dict(schema=t.SEEDANCE_MODE_SELECTION_SCHEMA, version=1,
            expected_instance=fields['execution_mode_instance'], expected_revision=fields['execution_mode_revision'],
            mode='shot' if shot else 'only')
        parameter = SimpleNamespace(name=t.SEEDANCE_SHOT_WIDGET_PARAMETER)
        normalized = node.before_value_set(parameter, value)
        node.parameter_values[t.SEEDANCE_SHOT_WIDGET_PARAMETER] = normalized
        node.after_value_set(parameter, normalized)
        return value

    def test_actual_widget_callbacks_switch_only_shot_only_without_losing_controls(self):
        node = Node(); node._hmb_shot_catalog_snapshot = catalog()
        expected = deepcopy(node.values)
        self.edit(node)
        self.assertEqual(node._hmb_seedance_execution_mode(), 'only')
        self.edit(node, SHOT)
        self.assertEqual(node._hmb_seedance_execution_mode(), 'shot')
        self.edit(node)
        self.assertEqual(node._hmb_seedance_execution_mode(), 'only')
        self.assertEqual(node.values, expected)
        self.assertEqual(node._hmb_seedance_mode_intent()['revision'], 3)

    def test_old_revision_and_old_instance_selection_cannot_rebind_only(self):
        node = Node(); node._hmb_shot_catalog_snapshot = catalog()
        old_fields = node._hmb_seedance_mode_widget_fields()
        self.edit(node)
        revision = node._hmb_seedance_mode_intent()['revision']
        self.edit(node, SHOT, fields=old_fields)
        self.assertEqual(node._hmb_seedance_mode_intent()['revision'], revision)
        self.assertEqual(node._hmb_seedance_execution_mode(), 'only')
        foreign = {**node._hmb_seedance_mode_widget_fields(), 'execution_mode_instance': '0' * 32}
        self.edit(node, SHOT, fields=foreign)
        self.assertEqual(node._hmb_seedance_execution_mode(), 'only')
        self.edit(node, SHOT)
        self.assertEqual(node._hmb_seedance_execution_mode(), 'shot')


if __name__ == '__main__':
    unittest.main()
