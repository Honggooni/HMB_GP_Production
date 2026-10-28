"""Post-commit CGT lifecycle: mocked helpers, no CGT/network/subprocess writes."""
from __future__ import annotations
import copy, socket, subprocess, sys, threading, unittest
from pathlib import Path
from unittest import mock
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import HMBImageAssetLibrary as image
import _hmb_shot_routing as routing
import _hmb_cgt as cgt


def guid():return str(uuid4())

class CGTWorkNode(unittest.TestCase):
 def setUp(self):
  self.net=mock.patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden'));self.net.start();self.addCleanup(self.net.stop)
  self.net2=mock.patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden'));self.net2.start();self.addCleanup(self.net2.stop)
  self.proc=mock.patch.object(subprocess,'run',side_effect=AssertionError('subprocess forbidden'));self.proc.start();self.addCleanup(self.proc.stop)
  self.proc2=mock.patch.object(subprocess,'Popen',side_effect=AssertionError('subprocess forbidden'));self.proc2.start();self.addCleanup(self.proc2.stop)
  self.account,self.project,self.pipeline=guid(),guid(),guid()
  self.state=image._default_state();self.state.update(project_root='C:/fixture/superwings12',project_id='superwings12',project_uid='fixture-project')
  self.state['assets']=[{'asset_library_id':'fixture-library','asset_id':'fixture-asset',
   'source_uid':'fixture-media','image_name':'fixture-image','path':'C:/fixture/media.png',
   'source_kind':'user','selected':True,'selection_order':1}]
  self.state['shot_routing']['shots'][0]['selected_source_uids']=['fixture-media']
  self.state=image._normalize_state(self.state)
  scope={'origin':'https://fixture.invalid','project_id':self.project,'project_db':'fixture_db','module':'shot','module_type':'task','pipeline_id':self.pipeline,'account_id':self.account}
  self.members=[];rows=[]
  for i,status in enumerate(('Wait','Work'),1):
   task,entity=guid(),guid();name=f'e201s{i:03d}c001__';parsed=routing.hierarchy_parse_name(name)
   identity={'task_id':task,'entity_id':entity,'pipeline_id':self.pipeline}
   row={'task_id':task,'identity':identity,'source_name':name,'episode':'e201','pipeline_id':self.pipeline,'artist':'Fixture','status':status}
   self.members.append({'member_id':'cgt:'+task.lower(),'origin':'cgt','manual_uuid':guid(),
    'source_name':parsed['source_name'],'canonical_name':parsed['canonical_name'],
    'gp_shot_uuid':self.state['shot_routing']['shots'][0]['shot_uuid'] if i==1 else guid(),
    'parent_id':None,'selection_order':i,'cgt_task_id':task,'artist':'Fixture','status':status,'cgt_identity':identity})
   rows.append(row)
  self.members[1]['parent_id']=self.members[0]['member_id']
  self.binding={'schema':routing.SHOT_HIERARCHY_SCHEMA,'version':2,'binding_id':guid(),'revision':1,
   'project_identity':routing.hierarchy_project_key(self.state),'channel_uuid':self.state['shot_routing']['channel_uuid'],
   'cgt_account_id':self.account,'cgt_scope':scope,'members':self.members}
  self.snapshot={'status':'ready','account_id':self.account,'origin':scope['origin'],
   'project':{'id':self.project,'database':'fixture_db','entity':'superwings12'},
   'can_bind':True,'truncated':False,'tls_verified':True,'hostname_verified':True,'tasks':rows}
  self.command={'schema':routing.SHOT_HIERARCHY_REQUEST_SCHEMA,'version':1,
   'expected_generation':self.state['shot_routing']['generation'],'expected_binding_revision':0,
   'removed_member_ids':[],'binding':copy.deepcopy(self.binding)}
  self.node=object.__new__(image.HMBImageAssetLibrary);self.node._hmb_node_deleted=False;self.node.lock=False
  self.holder={'state':copy.deepcopy(self.state),'published':[],'responses':[]}
  self.node._current_state=lambda:copy.deepcopy(self.holder['state'])
  self.node._scan_owner_is_current=lambda:True
  def publish(value,**kwargs):
   self.holder['state']=image._normalize_state(value);self.holder['published'].append(copy.deepcopy(self.holder['state']))
   return self.holder['state']
  self.node._publish_state=publish
  self.node._set_thumbnail_bridge_value=lambda value:self.holder['responses'].append(copy.deepcopy(value))
  self.intent={'schema':image.THUMBNAIL_BRIDGE_SCHEMA,'version':1,'operation':'cgt_confirm','phase':'request',
   'request_id':guid(),'session_id':guid(),'runtime_instance_id':self.node._thumbnail_runtime_id(self.state),
   'project_identity':routing.hierarchy_project_key(self.state),'hierarchy_request':self.command}
  self.observed=[{**copy.deepcopy(row),'status':'Work'} for row in rows]
  self.result={'schema':'hmb-cgt-work-start-result-v1','status':'completed','updated_count':1,'observed_tasks':self.observed}
  self.catalog=mock.patch.object(cgt,'catalog',return_value=copy.deepcopy(self.snapshot));self.catalogmock=self.catalog.start();self.addCleanup(self.catalog.stop)
  self.start=mock.patch.object(cgt,'start_own_wait_after_commit',return_value=copy.deepcopy(self.result));self.startmock=self.start.start();self.addCleanup(self.start.stop)
 def drain(self,which):
  worker=getattr(self.node,which,None)
  if worker is not None:worker.join(4);self.assertFalse(worker.is_alive())
 def commit(self):
  self.node._request_cgt_read(copy.deepcopy(self.intent));self.drain('_hmb_cgt_thread');self.node._consume_cgt_result()
 def consume(self):
  self.drain('_hmb_cgt_work_thread');self.node._consume_cgt_work_results()
 def test_new_wait_only_after_successful_publish_and_duplicate_request_once(self):
  self.commit();self.drain('_hmb_cgt_work_thread')
  self.assertEqual(self.holder['responses'][-1]['outcome'],'committed');self.assertEqual(self.startmock.call_count,1)
  self.assertEqual(self.holder['state']['cgt_work_start_notice']['status'],'queued')
  self.node._queue_cgt_work_start(self.intent,self.state,self.holder['state']);self.drain('_hmb_cgt_work_thread');self.assertEqual(self.startmock.call_count,1)
  self.consume();self.assertEqual(self.holder['state']['cgt_work_start_notice']['status'],'completed')
 def test_failed_publish_never_calls_start_or_changes_committed_state(self):
  def fail(value,**kwargs):
   if value.get('shot_hierarchy',{}).get('members'):raise RuntimeError('fixture publish failure')
   self.holder['state']=image._normalize_state(value)
  self.node._publish_state=fail;self.commit();self.assertEqual(self.startmock.call_count,0)
  self.assertEqual(self.holder['responses'][-1]['outcome'],'rejected');self.assertFalse(self.holder['state']['shot_hierarchy'])
 def test_notice_publish_failure_preserves_successfully_committed_shots(self):
  original=self.node._publish_state
  def fail_queued(value,**kwargs):
   if value.get('cgt_work_start_notice',{}).get('status')=='queued':raise RuntimeError('fixture notice failure')
   return original(value,**kwargs)
  self.node._publish_state=fail_queued;self.commit()
  self.assertEqual(self.holder['responses'][-1]['outcome'],'committed')
  self.assertEqual(self.holder['state']['cgt_work_start_notice']['status'],'failed')
  self.assertEqual([x['member_id'] for x in self.holder['state']['shot_hierarchy']['members']],[x['member_id'] for x in self.members])
  self.assertFalse(self.startmock.called)
 def test_both_notice_publications_failing_still_keep_commit(self):
  original=self.node._publish_state
  def fail_notice(value,**kwargs):
   if value.get('cgt_work_start_notice',{}).get('status') in {'queued','failed'}:
    raise RuntimeError('fixture consecutive notice failures')
   return original(value,**kwargs)
  self.node._publish_state=fail_notice;self.commit()
  self.assertEqual(self.holder['responses'][-1]['outcome'],'committed')
  self.assertEqual([x['member_id'] for x in self.holder['state']['shot_hierarchy']['members']],[x['member_id'] for x in self.members])
  self.assertFalse(self.startmock.called)
 def test_explicit_reconfirm_of_existing_wait_starts_without_replacing_shots(self):
  committed=image._normalize_state(routing.apply_shot_hierarchy_edit(self.state,self.command))
  self.holder['state']=copy.deepcopy(committed)
  before=copy.deepcopy(committed);binding=copy.deepcopy(committed['shot_hierarchy']);binding['revision']+=1
  self.intent['hierarchy_request']={'schema':routing.SHOT_HIERARCHY_REQUEST_SCHEMA,'version':1,
   'expected_generation':committed['shot_routing']['generation'],'expected_binding_revision':committed['shot_hierarchy']['revision'],
   'removed_member_ids':[],'binding':binding}
  self.commit();self.drain('_hmb_cgt_work_thread')
  self.assertEqual(self.holder['responses'][-1]['outcome'],'committed')
  self.assertEqual(self.startmock.call_count,1);self.assertIs(self.startmock.call_args.kwargs.get('include_bound_wait'),True)
  self.assertEqual(self.startmock.call_args.kwargs['previous_binding'],before['shot_hierarchy'])
  self.assertEqual(self.holder['state']['shot_hierarchy'],before['shot_hierarchy'])
  self.assertEqual(self.holder['state']['shot_routing'],before['shot_routing'])
  self.assertEqual(self.holder['state']['assets'],before['assets'])
 def test_confirmed_work_only_never_starts(self):
  self.command['binding']['members'][0]['status']='Work';self.snapshot['tasks'][0]['status']='Work'
  self.catalogmock.return_value=copy.deepcopy(self.snapshot)
  self.commit();self.assertEqual(self.holder['responses'][-1]['outcome'],'committed')
  self.assertFalse(self.startmock.called)
 def test_cancel_after_commit_does_not_cancel_work_start(self):
  entered=threading.Event();release=threading.Event()
  def start(*a,**k):
   entered.set();self.assertTrue(release.wait(3));return copy.deepcopy(self.result)
  self.startmock.side_effect=start
  try:
   self.commit();self.assertTrue(entered.wait(3));cancel={**self.intent,'operation':'cgt_cancel'}
   self.node._request_cgt_read(cancel);self.assertTrue(self.node._hmb_cgt_work_thread.is_alive())
  finally:release.set()
  self.consume();self.assertEqual(self.holder['state']['cgt_work_start_notice']['status'],'completed');self.assertEqual(self.startmock.call_count,1)
 def test_failed_worker_retains_commit(self):
  self.startmock.side_effect=RuntimeError('fixture failure');self.commit();self.consume()
  self.assertEqual(self.holder['responses'][-1]['outcome'],'committed');self.assertEqual(self.holder['state']['cgt_work_start_notice']['status'],'unknown')
  self.assertEqual([x['member_id'] for x in self.holder['state']['shot_hierarchy']['members']],[x['member_id'] for x in self.members])
 def test_saved_queued_notice_restores_unknown_without_a_call(self):
  for phase in ('queued','running'):
   with self.subTest(phase=phase):
    state=copy.deepcopy(self.state);state['cgt_work_start_notice']={'schema':'hmb-cgt-work-start-notice-v1','status':phase,'request_id':'fixture-id'}
    node=object.__new__(image.HMBImageAssetLibrary)
    with mock.patch.object(image,'_get_parameter_raw',return_value=state):
     restored=image.HMBImageAssetLibrary._current_state(node)
    self.assertEqual(restored['cgt_work_start_notice']['status'],'unknown');self.assertFalse(self.startmock.called)
 def test_late_results_are_discarded_for_new_project_or_deleted_node(self):
  for changed in ('project','deleted'):
   with self.subTest(changed=changed):
    self.setUp();self.commit();self.drain('_hmb_cgt_work_thread')
    if changed=='project':self.holder['state']['project_root']='C:/fixture/other-project'
    else:self.node._hmb_node_deleted=True
    before=copy.deepcopy(self.holder['state']);self.node._consume_cgt_work_results()
    self.assertEqual(self.holder['state'],before)
 def test_factual_status_rebase_preserves_names_uuids_and_parent(self):
  self.commit();self.drain('_hmb_cgt_work_thread');before=copy.deepcopy(self.holder['state']);self.node._consume_cgt_work_results();after=self.holder['state']
  self.assertEqual(after['shot_routing'],before['shot_routing'])
  self.assertEqual(after['assets'],before['assets'])
  self.assertEqual(after['shot_routing']['shots'][0]['selected_source_uids'],['fixture-media'])
  old,new=before['shot_hierarchy'],after['shot_hierarchy']
  self.assertEqual(new['revision'],old['revision']+1)
  for a,b in zip(old['members'],new['members']):
   aa,bb=copy.deepcopy(a),copy.deepcopy(b);aa.pop('status');bb.pop('status');self.assertEqual(aa,bb)
  self.assertEqual(new['members'][0]['status'],'Work');self.assertEqual(new['members'][1]['parent_id'],old['members'][1]['parent_id'])

if __name__=='__main__':unittest.main(verbosity=2)
