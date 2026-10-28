"""Current-state proof for redundant native catalog-clear callbacks.

No SDK, renderer, filesystem media or process-global authoring cache is used.
The existing full routing/native lifecycle suites cover retained topology.
"""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('_routing_empty_catalog_test',ROOT/'_hmb_shot_routing.py')
routing=importlib.util.module_from_spec(spec);sys.modules[spec.name]=routing;spec.loader.exec_module(routing)


class Node:
    def __init__(self,kind):
        self.name='same-name';self.kind=kind;self._hmb_node_deleted=False
        self.calls=[];self.parameter_values={}
        self._hmb_shot_catalog_snapshot={}
        if kind==routing.KIND_FINISH_LOOK:self._hmb_finish_active_key='__standalone__'
        self.archive={f'uuid-{n}':{'text':f'Authored {n} {{literal}} OFF 0'} for n in range(1,6)}
        self._hmb_suspended_shot_identity={'channel_uuid':'retired-channel','shot_uuid':'retired-shot'}
        shot={'channel_uuid':'','shot_uuid':'','name':'Only','number':1}
        ui={'shot':shot,'shot_catalog':{},'shot_states':copy.deepcopy(self.archive)}
        names={routing.KIND_AGENT:'HMB_AGENT_UI',routing.KIND_FINISH_LOOK:'HMB_FINISH_LOOK_UI_STATE',
            routing.KIND_SEEDANCE:'HMB_SEEDANCE_SHOT_UI',routing.KIND_COLOR_LUT:'HMB_COLOR_LUT_UI_STATE'}
        if kind==routing.KIND_PROMPT:
            ui={'shot':shot,'shot_documents':copy.deepcopy(self.archive),
                'image_asset':{'enabled':False,'shot_catalog':[],'shot_routing':{},'shot_catalog_routing':{}},
                'picker':{'enabled':False,'shot_catalog':[],'shot_routing':{}}}
            self._hmb_last_prompt_output='Authored visible';self._hmb_last_machine_prompt_output='Authored machine'
            self.parameter='HMB_UI_STATE'
        elif kind==routing.KIND_VIDEO_PICKER:
            ui={'channel_uuid':'','shot_uuid':'','shot_publisher_instance_uuid':'','shot_selections':[],'workspaces':copy.deepcopy(self.archive)}
            self.parameter='HMB_PICKER_STATE'
        else:self.parameter=names[kind]
        self.parameter_values[self.parameter]=ui
        if kind==routing.KIND_COLOR_LUT:self._hmb_color_lut_state=copy.deepcopy(ui)

    def _hmb_clear_shot_routing_catalog(self,reason):self.calls.append(reason)

    def get_parameter_value(self,name):return getattr(self,'parameter_values',{}).get(name)

    def subscription(self,*,enabled=False,channel='',shot=''):
        return routing.ShotSubscription(self,self.name,self.kind,enabled,channel,shot,1,'Only')


KINDS=(routing.KIND_VIDEO_PICKER,routing.KIND_PROMPT,routing.KIND_AGENT,routing.KIND_FINISH_LOOK,routing.KIND_SEEDANCE,routing.KIND_COLOR_LUT)


class EmptyCatalogNoOp(unittest.TestCase):
    def setUp(self):
        patch=mock.patch.object(routing,'_same_flow_nodes',side_effect=lambda node:('flow',[node]))
        patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(routing,'_mark_authoritative');self.mark=patch.start();self.addCleanup(patch.stop)

    def clear(self,node,reason='publisher_unavailable',subscription=None):
        routing._clear_remote_catalog(node,reason,subscription=subscription or node.subscription())

    def test_01_six_known_native_dashboards_already_local_preserve_five_archives(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                node=Node(kind);before=copy.deepcopy(vars(node))
                self.clear(node);self.clear(node)
                self.assertEqual(node.calls,[])
                self.assertEqual(vars(node),before)
                self.assertEqual(len(node.archive),5)

    def test_02_enabled_or_retired_channel_still_clears(self):
        for change in ({'enabled':True,'channel':'channel','shot':'uuid'},{'channel':'retired'},{'shot':'retired'}):
            node=Node(routing.KIND_PROMPT);self.clear(node,subscription=node.subscription(**change))
            self.assertEqual(node.calls,['publisher_unavailable'])

    def test_03_catalog_or_active_native_projection_change_invalidates_proof_immediately(self):
        node=Node(routing.KIND_PROMPT)
        self.assertTrue(routing._already_local_catalog(node.subscription()))
        node.parameter_values[node.parameter]['image_asset']['shot_catalog']=[{'shot_uuid':'new'}]
        self.clear(node);self.assertEqual(node.calls,['publisher_unavailable'])
        node.parameter_values[node.parameter]['image_asset']['shot_catalog']=[]
        self.assertTrue(routing._already_local_catalog(node.subscription()))
        node.parameter_values[node.parameter]['shot']['channel_uuid']='new-channel'
        self.clear(node);self.assertEqual(len(node.calls),2)

    def test_04_hydration_pending_never_skips_callback(self):
        node=Node(routing.KIND_PROMPT)
        pending=routing._PendingReconcile(1,'hydrated',None)
        routing._POST_REGISTRATION_PENDING[node]=pending
        try:self.clear(node)
        finally:routing._POST_REGISTRATION_PENDING.pop(node,None)
        self.assertEqual(node.calls,['publisher_unavailable'])

    def test_05_same_name_replacement_and_flow_move_cannot_reuse_proof(self):
        old=Node(routing.KIND_PROMPT);new=Node(routing.KIND_PROMPT)
        with mock.patch.object(routing,'_same_flow_nodes',side_effect=lambda node:('flow',[new]) if node is new else ('',[])):
            self.assertFalse(routing._already_local_catalog(old.subscription()))
            self.assertTrue(routing._already_local_catalog(new.subscription()))
        with mock.patch.object(routing,'_same_flow_nodes',return_value=('',[])):
            self.assertFalse(routing._already_local_catalog(new.subscription()))

    def test_06_channel_replacement_clears_even_when_current_catalog_is_empty(self):
        node=Node(routing.KIND_SEEDANCE);self.clear(node,'channel_replaced')
        self.assertEqual(node.calls,['channel_replaced'])

    def test_07_unknown_legacy_and_corrupt_values_use_original_path(self):
        for value in (None,'{invalid',{'shot':{}}):
            node=Node(routing.KIND_AGENT);node.parameter_values[node.parameter]=value
            self.clear(node);self.assertEqual(node.calls,['publisher_unavailable'])
        node=Node(routing.KIND_AGENT);del node.parameter_values
        self.clear(node);self.assertEqual(node.calls,['publisher_unavailable'])
        node=Node(routing.KIND_AGENT);routing._clear_remote_catalog(node,'publisher_unavailable')
        self.assertEqual(node.calls,['publisher_unavailable'])

    def test_08_private_execution_or_cached_source_projection_requires_clear(self):
        for kind,attribute,value in ((routing.KIND_AGENT,'_hmb_shot_context',{'shot_uuid':'old'}),
                (routing.KIND_AGENT,'_hmb_execution_shot_binding',{'shot_uuid':'old'}),
                (routing.KIND_SEEDANCE,'_hmb_shot_selector_map',{'old':'uuid'}),
                (routing.KIND_SEEDANCE,'_hmb_shot_catalog_generation',3),
                (routing.KIND_FINISH_LOOK,'_hmb_finish_route_ready',True),
                (routing.KIND_PROMPT,'_hmb_current_shot_images',['old.png']),
                (routing.KIND_PROMPT,'_hmb_last_shot_context',{'shot_uuid':'old'})):
            node=Node(kind);setattr(node,attribute,value);self.clear(node)
            self.assertEqual(node.calls,['publisher_unavailable'],(kind,attribute))

    def test_09_native_catalog_is_not_empty_when_its_schema_is_unknown(self):
        node=Node(routing.KIND_AGENT)
        node.parameter_values[node.parameter]['shot_catalog']={'schema':'foreign','version':9}
        self.clear(node);self.assertEqual(node.calls,['publisher_unavailable'])

    def test_10_valid_empty_serialized_ui_is_checked_without_changing_inputs(self):
        import json
        node=Node(routing.KIND_PROMPT);node.parameter_values[node.parameter]=json.dumps(node.parameter_values[node.parameter])
        before=copy.deepcopy(node.parameter_values);self.clear(node)
        self.assertEqual(node.calls,[]);self.assertEqual(node.parameter_values,before)

    def test_11_deleted_owner_is_not_a_current_state_proof(self):
        node=Node(routing.KIND_COLOR_LUT);node._hmb_node_deleted=True
        self.assertFalse(routing._already_local_catalog(node.subscription()))

    def test_12_native_computed_or_held_value_reader_is_never_bypassed(self):
        node=Node(routing.KIND_AGENT)
        computed=copy.deepcopy(node.get_parameter_value(node.parameter))
        computed['shot_catalog']={'schema':'hmb-shot-routing-catalog','version':1,'channel_uuid':'computed-live','shots':[{'shot_uuid':'live'}]}
        with mock.patch.object(node,'get_parameter_value',return_value=computed) as reader:
            self.clear(node);reader.assert_called_once_with(node.parameter)
        self.assertEqual(node.calls,['publisher_unavailable'])
        with mock.patch.object(node,'get_parameter_value',side_effect=RuntimeError('held value not available')):
            self.clear(node)
        self.assertEqual(len(node.calls),2)

    def test_13_finish_private_saved_store_owner_requires_real_clear(self):
        node=Node(routing.KIND_FINISH_LOOK)
        node._hmb_finish_active_key='channel\x1fshot-5'
        self.clear(node);self.assertEqual(node.calls,['publisher_unavailable'])
        node._hmb_finish_active_key='__standalone__'
        self.clear(node);self.assertEqual(node.calls,['publisher_unavailable'])
        self.assertEqual(len(node.archive),5)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EmptyCatalogNoOp))
    if result.wasSuccessful():print('HMB_SHOT_ROUTING_EMPTY_CATALOG_NO_OP=PASS (13 boundary groups, active authority invalidation and five authored archives preserved)')
    raise SystemExit(0 if result.wasSuccessful() else 1)
