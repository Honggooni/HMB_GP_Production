"""Offline consolidated Finish authoring, immutable target snapshots and rollback."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec=importlib.util.spec_from_file_location('hmb_finish_multishot_target',ROOT/'HMBFinishLookLibrary.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

def catalog():
    rows=[{'shot_uuid':f'uuid-{n}','number':n,'name':f'Asset {n}','revision':0} for n in range(1,6)]
    doc={'channel_uuid':'channel','generation':1,'shots':rows}
    return {'schema':m.SHOT_ROUTING_CATALOG_SCHEMA,'version':1,'publisher_instance_uuid':'publisher',**doc,
        'metadata_sha256':hashlib.sha256(json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()}

def node():
    n=m.HMBFinishLookLibrary(name='Offline Finish')
    n._reconcile_shared_shot_routing=Mock(return_value={'ok':True});n._hmb_reconcile_shot_routing(catalog())
    return n

def select(n,number):
    value=copy.deepcopy(n._widget_state);row=catalog()['shots'][number-1]
    value['shot']={'channel_uuid':'channel',**row};n._apply_widget_value(value)

def edit(n,brightness):
    value=copy.deepcopy(n._widget_state);value['finish_look']['beauty'].update(enabled=True,brightness=brightness)
    n._apply_widget_value(value)

class FinishMultishot(unittest.TestCase):
    def setUp(self):
        self.guard=patch.object(socket,'create_connection',side_effect=AssertionError('External networking forbidden'));self.guard.start()
    def tearDown(self):self.guard.stop()

    def test_default_height_adds_tab_chrome_and_preserves_custom_saved_size(self):
        n=m.HMBFinishLookLibrary(name='New default Finish')
        self.assertEqual(m.FINISH_LOOK_SHOT_TAB_HEIGHT,51)
        self.assertEqual(m.FINISH_LOOK_NODE_HEIGHT,864);self.assertEqual(m.FINISH_LOOK_WIDGET_HEIGHT,788)
        self.assertEqual(n.ui_options['default_height'],864)
        saved=m.HMBFinishLookLibrary(name='Saved custom Finish',metadata={'size':{'width':1130,'height':1275}})
        self.assertEqual(saved.height,1275);self.assertEqual(saved.width,1130)
        self.assertEqual(saved.metadata['size'],{'width':1130,'height':1275})
        old_default=m.HMBFinishLookLibrary(name='Saved prior default Finish',metadata={'size':{'width':980,'height':1091}})
        self.assertEqual(old_default.metadata['size'],{'width':980,'height':1091})
        self.assertEqual((old_default.width,old_default.height),(980,1091))

    def test_five_target_states_and_snapshots_are_independent(self):
        n=node()
        for number in range(1,6):select(n,number);edit(n,number/2)
        before=copy.deepcopy((n._widget_state,n._last_valid_state,dict(n.parameter_values),dict(n.parameter_output_values),n._hmb_finish_documents))
        for number in range(1,6):
            snapshot=n._hmb_finish_look_shot_snapshot_for(channel_uuid='channel',shot_uuid=f'uuid-{number}')
            self.assertEqual(snapshot['finish_look_state']['beauty']['brightness'],number/2)
            self.assertEqual(snapshot['shot_name'],f'Asset {number}')
            snapshot['finish_look_state']['beauty']['brightness']=99
        self.assertEqual((n._widget_state,n._last_valid_state,dict(n.parameter_values),dict(n.parameter_output_values),n._hmb_finish_documents),before)
        select(n,2);self.assertEqual(n._last_valid_state['beauty']['brightness'],1)

    def test_same_remote_id_cannot_replay_into_another_selected_shot(self):
        n=node();request={'schema':m.REMOTE_SCHEMA,'version':1,'request_id':'fixed-target','base_revision':0,'changes':{'beauty':{'enabled':True,'brightness':1.5}}}
        n._apply_remote_value(request);first=n._remote_revision
        select(n,2);before=copy.deepcopy((n._last_valid_state,n._remote_status,n._remote_revision))
        n._apply_remote_value(request);self.assertEqual((n._last_valid_state,n._remote_status,n._remote_revision),before)
        select(n,1);self.assertEqual(n._remote_revision,first)
        n._apply_remote_value(request);self.assertEqual(n._remote_status['status'],'duplicate')

    def test_targeted_remote_changes_no_other_ui_or_output(self):
        n=node();before=copy.deepcopy((n._widget_state,n._last_valid_state,dict(n.parameter_output_values),n._remote_revision))
        request={'schema':m.REMOTE_SCHEMA,'version':1,'request_id':'inactive-target','base_revision':0,'changes':{'beauty':{'enabled':True,'brightness':1.25}}}
        status=n._hmb_apply_finish_remote_for(channel_uuid='channel',shot_uuid='uuid-4',request=request)
        self.assertEqual(status['status'],'accepted')
        self.assertEqual((n._widget_state,n._last_valid_state,dict(n.parameter_output_values),n._remote_revision),before)
        self.assertEqual(n._hmb_finish_look_shot_snapshot_for(channel_uuid='channel',shot_uuid='uuid-4')['finish_look_state']['beauty']['brightness'],1.25)

    def test_identical_ui_and_presentation_changes_do_not_compile_or_route(self):
        n=node();n._reconcile_shared_shot_routing.reset_mock()
        with patch.object(m,'compile_finish_look_prompt',side_effect=AssertionError('Presentation compiled Finish prose')):
            for _ in range(100):n._apply_widget_value(copy.deepcopy(n._widget_state))
            value=copy.deepcopy(n._widget_state);value['language']='en';n._apply_widget_value(value)
            select(n,4);select(n,2)
        n._reconcile_shared_shot_routing.assert_not_called()

    def test_initial_value_reload_restores_all_documents_without_after_deserialize(self):
        n=node()
        for number in range(1,6):select(n,number);edit(n,number/3)
        store=copy.deepcopy(m._raw_parameter(n,m.SHOT_STORE_PARAMETER_NAME));ui=copy.deepcopy(n._widget_state)
        restored=m.HMBFinishLookLibrary(name='Restored Finish')
        restored.set_parameter_value(m.WIDGET_PARAMETER_NAME,ui,initial_setup=True)
        restored.set_parameter_value(m.SHOT_STORE_PARAMETER_NAME,store,initial_setup=True)
        restored._hmb_reconcile_shot_routing(catalog())
        for number in range(1,6):
            self.assertAlmostEqual(restored._hmb_finish_look_shot_snapshot_for(channel_uuid='channel',shot_uuid=f'uuid-{number}')['finish_look_state']['beauty']['brightness'],number/3)

    def test_migration_conflict_and_cas_fail_before_change_then_pure_rollback(self):
        n=node();edit(n,1.5);original=n._hmb_finish_merge_snapshot();before=copy.deepcopy((dict(n.parameter_values),dict(n.parameter_output_values)))
        other=node();edit(other,2);other.name='Other Finish';exported=other._hmb_finish_merge_snapshot()
        with self.assertRaises(RuntimeError):n._hmb_import_finish_documents([exported],expected_state_sha256=original['digest'])
        self.assertEqual(n._hmb_finish_merge_snapshot(),original)
        with self.assertRaises(RuntimeError):n._hmb_import_finish_documents([],expected_state_sha256='0'*64)
        n._hmb_finish_documents={};n._hmb_finish_archives={'wrong':{}}
        self.assertTrue(n._hmb_restore_finish_merge_snapshot(original))
        self.assertEqual(n._hmb_finish_merge_snapshot(),original)
        self.assertEqual((dict(n.parameter_values),dict(n.parameter_output_values)),before)

    def test_legacy_raw_blank_identity_and_standalone_output_preserved(self):
        n=m.HMBFinishLookLibrary(name='Legacy Standalone');raw=m.default_widget_state()
        for key in ('shot_manager','shot_editor_expanded','shot_documents'):raw.pop(key)
        raw['finish_look']['beauty'].update(enabled=True,brightness=1.2)
        n.set_parameter_value(m.WIDGET_PARAMETER_NAME,raw,initial_setup=True)
        exported=n._hmb_finish_merge_snapshot();self.assertFalse(exported['active_subscription']['enabled'])
        self.assertEqual(exported['standalone']['finish_look'],raw['finish_look'])
        self.assertEqual(set(exported['documents']),{'__standalone__'})
        n.process();self.assertEqual(n.parameter_output_values[m.FINISH_LOOK_OUTPUT_PARAMETER_NAME],m.compile_finish_look_prompt(raw['finish_look']))

if __name__=='__main__':unittest.main(verbosity=2)
