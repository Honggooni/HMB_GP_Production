"""Pure compile memoization and native-loop hydration coalescing contracts."""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('_hmb_prompt_compile_hydration',ROOT/'HMBPromptLibrary.py')
target=importlib.util.module_from_spec(spec);sys.modules[spec.name]=target;spec.loader.exec_module(target)

class CompileCacheHydration(unittest.TestCase):
    def setUp(self):
        self.node=target.HMBPromptLibrary(name='Prompt compile fixture')
        self.state=target._normalize_state(target._default_widget_state())
        self.node._hmb_compiled_prompt_pairs={}
        self.visible=target._build_prompt_package;self.machine=target._build_data_only_prompt_package

    def expected(self,state):
        visible=self.visible(state);machine=self.machine(state)
        return visible,machine,target._prompt_semantic_fingerprint(state,public_prompt=visible,machine_prompt=machine)

    def test_identical_active_input_compiles_once_and_preserves_pair(self):
        expected=self.expected(self.state)
        with mock.patch.object(target,'_build_prompt_package',wraps=self.visible) as visible,mock.patch.object(target,'_build_data_only_prompt_package',wraps=self.machine) as machine:
            for _ in range(10):self.assertEqual(self.node._compiled_prompt_pair_for_state(copy.deepcopy(self.state)),expected)
        self.assertEqual(visible.call_count,1);self.assertEqual(machine.call_count,1)

    def test_machine_only_literals_roles_targets_ranges_are_exact(self):
        first=next(iter(target.TEXT_FIELD_DEFAULTS))
        for number,text in enumerate(('literal {x} 0 OFF\n  exact words  ','','@image1 / @video1','USER DESCRIPTION: keep this 0')):
            state=copy.deepcopy(self.state);state['text'][first]=text;state[target.UI_EDIT_REVISION_KEY]=number
            state['images'][0].update(present=True,label='Hero',owner='Hero',image_main_type='Character',image_sub_type='Full Appearance',binding_video_slots=[1],binding_scopes=['Full body / full appearance'])
            state['videos'][0].update(present=True,label='Timing',video_main_type='Motion / Timing')
            state=target._normalize_state(state)
            self.assertEqual(self.node._compiled_prompt_pair_for_state(state),self.expected(state))

    def test_same_named_replacement_source_and_source_epoch_invalidate(self):
        source=types.SimpleNamespace(name='same publisher',_hmb_node_deleted=False)
        self.node._hmb_connected_source_nodes={'port':source}
        with mock.patch.object(target,'_build_prompt_package',wraps=self.visible) as built:
            self.node._compiled_prompt_pair_for_state(self.state)
            self.node._hmb_connected_source_nodes={'port':types.SimpleNamespace(name='same publisher',_hmb_node_deleted=False)}
            self.node._compiled_prompt_pair_for_state(self.state)
            self.node._hmb_document_source_epoch=1;self.node._compiled_prompt_pair_for_state(self.state)
        self.assertEqual(built.call_count,3)

    def test_ui_and_source_revision_each_invalidate(self):
        with mock.patch.object(target,'_build_prompt_package',wraps=self.visible) as built:
            self.node._compiled_prompt_pair_for_state(self.state)
            for key in (target.UI_EDIT_REVISION_KEY,target.SOURCE_SYNC_REVISION_KEY):
                self.state[key]+=1;self.node._compiled_prompt_pair_for_state(self.state)
        self.assertEqual(built.call_count,3)

    def test_dormant_document_change_does_not_recompile_active_document(self):
        with mock.patch.object(target,'_build_prompt_package',wraps=self.visible) as built:
            original=self.node._compiled_prompt_pair_for_state(self.state)
            self.state['shot_documents']['foreign/channel']='{"text":{"project_context":"dormant only"}}'
            self.assertEqual(self.node._compiled_prompt_pair_for_state(self.state),original)
        self.assertEqual(built.call_count,1)

    def test_per_shot_revisit_reuses_only_exact_old_input(self):
        first=copy.deepcopy(self.state);second=copy.deepcopy(self.state)
        first['shot']={'channel_uuid':'channel-a','shot_uuid':'shot-a','number':1,'name':'A'}
        second['shot']={'channel_uuid':'channel-a','shot_uuid':'shot-b','number':2,'name':'B'}
        with mock.patch.object(target,'_build_prompt_package',wraps=self.visible) as built:
            one=self.node._compiled_prompt_pair_for_state(first);self.node._compiled_prompt_pair_for_state(second)
            self.assertEqual(self.node._compiled_prompt_pair_for_state(first),one)
            first['text'][next(iter(target.TEXT_FIELD_DEFAULTS))]='new machine-only direction'
            self.assertEqual(self.node._compiled_prompt_pair_for_state(first),self.expected(first))
        self.assertEqual(built.call_count,3)

    def test_cache_is_instance_bound_and_bounded(self):
        for number in range(10):
            state=copy.deepcopy(self.state);state['shot']={'channel_uuid':'channel-a','shot_uuid':f'shot-{number}','number':1,'name':'A'}
            self.node._compiled_prompt_pair_for_state(state)
        self.assertEqual(len(self.node._hmb_compiled_prompt_pairs),target.MAX_SHOTS+1)
        other=target.HMBPromptLibrary(name=self.node.name)
        self.assertIsNot(self.node._hmb_compiled_prompt_pairs,other._hmb_compiled_prompt_pairs)

    def loop_modules(self,running=True):
        native=types.ModuleType('griptape_nodes.retained_mode.griptape_nodes')
        native.GriptapeNodes=types.SimpleNamespace(EventManager=lambda:types.SimpleNamespace(event_loop=types.SimpleNamespace(is_running=lambda:running)))
        return {native.__name__:native}

    def test_running_loop_hydration_retains_raw_inputs_then_commits_once(self):
        state=copy.deepcopy(self.state);state['text'][next(iter(target.TEXT_FIELD_DEFAULTS))]='saved literal 0 OFF {keep}'
        writes=[(target.WIDGET_PARAMETER_NAME,target._json_dumps(state)),(target.PICKER_INPUT_PARAMETER_NAME,'{}'),
            (target.IMAGE_ASSET_INPUT_PARAMETER_NAME,'{}'),(target.SHOT_ASSET_INPUT_PARAMETER_NAME,'{}'),(target.SHOT_PICKER_INPUT_PARAMETER_NAME,{})]
        with mock.patch.dict(sys.modules,self.loop_modules()),mock.patch.object(self.node,'_schedule_post_hydration_shot_reconcile',return_value=True),mock.patch.object(self.node,'_reconcile_connected_source_inputs_from_graph',return_value=True) as reconcile,mock.patch.object(self.node,'_sync_prompt_output_now') as sync:
            for name,value in writes:self.node.set_parameter_value(name,value,initial_setup=True)
            self.assertTrue(self.node._hmb_initial_source_hydration_pending)
            self.assertEqual(self.node._current_state()['text'],state['text'])
            for name,value in writes:self.assertEqual(target._get_parameter_raw(self.node,name),value)
            reconcile.assert_not_called();sync.assert_not_called()
            self.node._hmb_post_hydration_state_restore();self.node._hmb_post_hydration_state_restore()
            self.assertEqual(reconcile.call_count,1);self.assertEqual(sync.call_count,1)

    def test_explicit_sync_flushes_latest_hydration_before_run(self):
        state=copy.deepcopy(self.state);state['text'][next(iter(target.TEXT_FIELD_DEFAULTS))]='latest before Run 0 OFF'
        with mock.patch.dict(sys.modules,self.loop_modules()),mock.patch.object(self.node,'_schedule_post_hydration_shot_reconcile',return_value=True):
            self.node.set_parameter_value(target.WIDGET_PARAMETER_NAME,target._json_dumps(state),initial_setup=True)
        with mock.patch.object(self.node,'_reconcile_connected_source_inputs_from_graph',return_value=True),mock.patch.object(self.node,'_reconcile_shared_shot_edges'),mock.patch.object(self.node,'_write_dashboard_state',side_effect=lambda **_kwargs:target._normalize_state(self.node._current_state())),mock.patch.object(self.node,'_schedule_post_hydration_shot_reconcile',return_value=True),mock.patch.object(self.node,'_sync_prompt_output_from_state',wraps=self.node._sync_prompt_output_from_state) as sync:
            self.node._sync_prompt_output_now()
            self.assertFalse(self.node._hmb_initial_source_hydration_pending)
            self.assertEqual(sync.call_count,1)
            self.assertEqual(self.node._hmb_last_machine_prompt_output,self.machine(target._normalize_state(state)))

    def test_no_running_loop_preserves_synchronous_hydration(self):
        with mock.patch.dict(sys.modules,self.loop_modules(False)),mock.patch.object(self.node,'_schedule_post_hydration_shot_reconcile',return_value=False),mock.patch.object(self.node,'_reconcile_connected_source_inputs_from_graph',return_value=True) as reconcile,mock.patch.object(self.node,'_sync_prompt_output_now') as sync:
            self.node.set_parameter_value(target.WIDGET_PARAMETER_NAME,target._json_dumps(self.state),initial_setup=True)
            self.assertEqual(reconcile.call_count,1);self.assertEqual(sync.call_count,1)
            self.assertFalse(self.node._hmb_initial_source_hydration_pending)

    def test_running_loop_scheduler_false_falls_back_synchronously(self):
        state=copy.deepcopy(self.state);state['text'][next(iter(target.TEXT_FIELD_DEFAULTS))]='saved fallback literal 0 OFF'
        raw=target._json_dumps(state)
        with mock.patch.dict(sys.modules,self.loop_modules()),mock.patch.object(self.node,'_schedule_post_hydration_shot_reconcile',return_value=False) as schedule,mock.patch.object(self.node,'_reconcile_connected_source_inputs_from_graph',return_value=True) as reconcile,mock.patch.object(self.node,'_sync_prompt_output_now') as sync:
            self.node.set_parameter_value(target.WIDGET_PARAMETER_NAME,raw,initial_setup=True)
            self.assertEqual(target._get_parameter_raw(self.node,target.WIDGET_PARAMETER_NAME),raw)
            self.assertEqual(self.node._current_state()['text'],state['text'])
            self.assertEqual(reconcile.call_count,1);self.assertEqual(sync.call_count,1)
            self.assertFalse(self.node._hmb_initial_source_hydration_pending)
            schedule.assert_called_once_with()
            self.node._hmb_post_hydration_state_restore()
            self.assertEqual(reconcile.call_count,1);self.assertEqual(sync.call_count,1)

    def test_running_loop_scheduler_exception_falls_back_synchronously(self):
        state=copy.deepcopy(self.state);state['text'][next(iter(target.TEXT_FIELD_DEFAULTS))]='saved exception literal 0 OFF'
        raw=target._json_dumps(state)
        router=types.ModuleType('_hmb_shot_routing')
        router.schedule_post_hydration_reconcile=mock.Mock(side_effect=RuntimeError('fixture scheduler unavailable'))
        with mock.patch.dict(sys.modules,{**self.loop_modules(),'_hmb_shot_routing':router}),mock.patch.object(self.node,'_reconcile_connected_source_inputs_from_graph',return_value=True) as reconcile,mock.patch.object(self.node,'_sync_prompt_output_now') as sync:
            self.node.set_parameter_value(target.WIDGET_PARAMETER_NAME,raw,initial_setup=True)
            self.assertEqual(target._get_parameter_raw(self.node,target.WIDGET_PARAMETER_NAME),raw)
            self.assertEqual(self.node._current_state()['text'],state['text'])
            self.assertEqual(reconcile.call_count,1);self.assertEqual(sync.call_count,1)
            self.assertFalse(self.node._hmb_initial_source_hydration_pending)
            router.schedule_post_hydration_reconcile.assert_called_once_with(self.node)
            self.node._hmb_post_hydration_state_restore()
            self.assertEqual(reconcile.call_count,1);self.assertEqual(sync.call_count,1)

    def test_exact_document_read_does_not_flush_or_publish_pending_hydration(self):
        self.node._hmb_initial_source_hydration_pending=True
        with mock.patch.object(self.node,'_flush_initial_prompt_hydration') as flush,mock.patch.object(self.node,'_sync_prompt_output_now') as publish:
            with self.assertRaisesRegex(RuntimeError,'not in the current ImageAsset catalog'):
                self.node._hmb_prompt_shot_document(channel_uuid='missing-channel',shot_uuid='missing-shot')
            flush.assert_not_called();publish.assert_not_called()
        self.assertTrue(self.node._hmb_initial_source_hydration_pending)

    def test_deleted_owner_cannot_flush_queued_hydration(self):
        self.node._hmb_initial_source_hydration_pending=True;self.node._hmb_node_deleted=True
        with mock.patch.object(self.node,'_reconcile_connected_source_inputs_from_graph') as reconcile:
            self.node._hmb_post_hydration_state_restore();reconcile.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
