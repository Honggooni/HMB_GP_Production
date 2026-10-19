"""Connection/hydration readiness is a bounded wait, never a partial prompt publish."""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('_hmb_preparing_existing_fixture',Path(__file__).with_name('HMB_Prompt_Image_Preparation_Regression.py'))
fixture_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture_module)
prompt=fixture_module.prompt

class PromptConnectionPreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.PromptImagePreparationTests(methodName='runTest')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.node=self.fixture.node
        self.node.parameter_values={}
        self.node._hmb_connected_source_nodes={}
        self.node._reconcile_connected_source_inputs_from_graph=Mock(return_value=True)
        self.node._schedule_post_hydration_shot_reconcile=Mock(return_value=False)
        parent=prompt.HMBPromptLibrary.__bases__[0]
        def setter(node,name,value,**_kwargs):node.parameter_values[name]=value
        self.parent_setter=patch.object(parent,'set_parameter_value',setter)
        self.parent_setter.start();self.addCleanup(self.parent_setter.stop)
        self.parent_incoming=patch.object(parent,'after_incoming_connection',lambda *_args,**_kwargs:None,create=True)
        self.parent_incoming.start();self.addCleanup(self.parent_incoming.stop)
        self.native=patch.object(prompt,'_set_parameter_value',setter)
        self.native.start();self.addCleanup(self.native.stop)
        self.source=SimpleNamespace(parameter_output_values={'source':'verified-source-envelope'})
        self.source_parameter=SimpleNamespace(name='source')
        self.target=SimpleNamespace(name=prompt.SHOT_ASSET_INPUT_PARAMETER_NAME)

    def invoke(self,entry):
        if entry=='incoming':
            return self.node.after_incoming_connection(self.source,self.source_parameter,self.target)
        return self.node.set_parameter_value(self.target.name,'verified-source-envelope',initial_setup=True)

    def test_each_typed_preparing_entry_keeps_atomic_pair_and_media_intent_then_latest_publish(self):
        for error_type in (fixture_module.Preparing,fixture_module.PickerPreparing):
            for entry in ('incoming','initial'):
                with self.subTest(error=error_type.__name__,entry=entry):
                    self.fixture.pending=True;self.fixture.error=error_type('source preparing')
                    old=copy.deepcopy(self.node.parameter_output_values)
                    self.node._hmb_sync_publish_shot_media_pending=True
                    self.fixture.calls.clear();self.fixture.diag.reset_mock()
                    self.invoke(entry)
                    self.assertEqual(self.node.parameter_output_values,old)
                    self.assertTrue(self.node._hmb_sync_queued_source_burst)
                    self.assertTrue(self.node._hmb_sync_publish_shot_media_pending)
                    self.fixture.loop.drain()
                    self.assertEqual(self.node.parameter_output_values,old)
                    self.assertTrue(self.node._hmb_sync_publish_shot_media_pending)
                    self.assertEqual(self.fixture.calls,[])
                    self.fixture.diag.assert_not_called()
                    self.fixture.authored.update(text='최신 {{USER}} '+entry,project='ProjectB',shot='Shot2')
                    self.fixture.pending=False
                    self.node._schedule_prompt_sync(source_burst=True)
                    self.fixture.loop.drain()
                    self.assertEqual(len(self.fixture.calls),1)
                    self.assertTrue(self.fixture.calls[0][1]['publish_shot_media'])
                    self.assertEqual(self.fixture.calls[0][0],self.fixture.authored)
                    self.assertEqual(self.node.parameter_output_values['visible'],self.fixture.authored['text'])
                    self.fixture.diag.assert_not_called()

    def test_genuine_exceptions_still_diagnose_at_both_entries(self):
        for entry in ('incoming','initial'):
            for error in (ValueError('schema invalid'),RuntimeError('owner lost'),PermissionError('access denied')):
                with self.subTest(entry=entry,error=type(error).__name__):
                    if not isinstance(error,ValueError):
                        error.hmb_image_asset_selection_preparing=True
                        error.hmb_picker_media_preparing=True
                    self.fixture.pending=True;self.fixture.error=error
                    self.fixture.diag.reset_mock()
                    with patch.object(self.node,'_schedule_prompt_sync') as schedule:
                        self.invoke(entry)
                    self.fixture.diag.assert_called_once()
                    self.assertIs(self.fixture.diag.call_args.args[1],error)
                    schedule.assert_not_called()

    def test_truthy_non_boolean_or_false_flags_do_not_hide_value_errors(self):
        for marker in (False,1,'true'):
            for entry in ('incoming','initial'):
                with self.subTest(marker=marker,entry=entry):
                    error=ValueError('not a declared source wait')
                    error.hmb_image_asset_selection_preparing=marker
                    error.hmb_picker_media_preparing=marker
                    self.fixture.error=error;self.fixture.pending=True
                    self.fixture.diag.reset_mock()
                    with patch.object(self.node,'_schedule_prompt_sync') as schedule:self.invoke(entry)
                    self.fixture.diag.assert_called_once()
                    self.assertIs(self.fixture.diag.call_args.args[1],error)
                    schedule.assert_not_called()

    def test_preparing_retry_scheduling_failure_remains_explicit_diagnostic(self):
        for entry in ('incoming','initial'):
            with self.subTest(entry=entry):
                self.fixture.pending=True;self.fixture.error=fixture_module.Preparing('source preparing')
                self.fixture.diag.reset_mock();failure=RuntimeError('host queue unavailable')
                with patch.object(self.node,'_schedule_prompt_sync',side_effect=failure):self.invoke(entry)
                self.fixture.diag.assert_called_once()
                self.assertIs(self.fixture.diag.call_args.args[1],failure)

    def test_initial_reconcile_preparing_before_sync_is_deferred_and_finally_clears_guard(self):
        for error_type in (fixture_module.Preparing,fixture_module.PickerPreparing):
            with self.subTest(error=error_type.__name__):
                error=error_type('source discovery preparing')
                self.node._reconcile_connected_source_inputs_from_graph.side_effect=error
                self.fixture.diag.reset_mock()
                with patch.object(self.node,'_schedule_prompt_sync') as schedule:self.invoke('initial')
                schedule.assert_called_once_with(source_burst=True,publish_shot_media=False)
                self.assertFalse(self.node._hmb_hydration_reconciling)
                self.fixture.diag.assert_not_called()
        self.assertEqual(self.node._schedule_post_hydration_shot_reconcile.call_count,2)

    def test_explicit_execution_still_raises_both_preparing_types_and_keeps_output(self):
        for error_type in (fixture_module.Preparing,fixture_module.PickerPreparing):
            with self.subTest(error=error_type.__name__):
                self.fixture.pending=True;self.fixture.error=error_type('source preparing')
                old=copy.deepcopy(self.node.parameter_output_values)
                with patch.object(self.node,'_schedule_prompt_sync') as schedule:
                    with self.assertRaises(error_type):self.node._sync_prompt_output_now()
                self.assertEqual(self.node.parameter_output_values,old)
                schedule.assert_not_called()

    def test_deleted_node_never_retries_or_publishes(self):
        self.node._hmb_node_deleted=True
        old=copy.deepcopy(self.node.parameter_output_values)
        with patch.object(self.node,'_schedule_prompt_sync') as schedule:
            self.invoke('incoming');self.invoke('initial')
        schedule.assert_not_called()
        self.assertEqual(self.node.parameter_output_values,old)
        self.fixture.diag.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
