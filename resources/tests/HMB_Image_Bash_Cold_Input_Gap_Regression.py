"""Exact source-method metadata guards for retained cold input-gap recovery.

No SDK/engine/app instance, files/media/network or output verification is
faked as a pass. Scheduling and initial assignment leases are controlled here;
actual SDK/PNG Save/Deserialize is covered by the separate integration proof.
"""
from __future__ import annotations
import ast,contextvars,copy,hashlib,json,os,sys,types
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
PRODUCT=Path(os.environ.get('HMB_BASH_COLD_GAP_SOURCE_ROOT',str(ROOT))).resolve()
OUT=Path(os.environ.get('HMB_BASH_COLD_GAP_REPORT_DIR',str(ROOT/'reports/regression-checks/HMB_Image_Bash_Cold_Input_Gap_Regression')))
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(PRODUCT));sys.dont_write_bytecode=True
from _hmb_image_bash_state import scene_fingerprint
path=PRODUCT/'HMBImageBash.py';tree=ast.parse(path.read_text('utf-8-sig'))
original=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='HMBImageBash')
names={'_queue_saved_editor_readiness','_cold_gap_saved_identity','_initial_bash_assignment_active',
    'before_value_set','_validate_apply_source_bindings','_apply_scope','_remote_source_instance',
    '_clear_output','_sync_metadata_with_input_images','_records','_complete_cold_editor_readiness'}
methods=copy.deepcopy([n for n in original.body if isinstance(n,ast.FunctionDef) and n.name in names])
assert len(methods)==len(names)
for method in methods:
    method.decorator_list=[d for d in method.decorator_list if isinstance(d,ast.Name) and d.id=='staticmethod']
class Base:
    def before_value_set(self,parameter,value):return value
registry={};assignment=contextvars.ContextVar('synthetic_initial_assignment',default=None)
manager=SimpleNamespace(_hmb_bash_initial_assignment_context=assignment)
node_manager=SimpleNamespace(get_node_by_name=lambda name:registry[name])
engine=SimpleNamespace(event_manager=manager,node_manager=node_manager)
api=types.ModuleType('griptape_nodes.retained_mode.griptape_nodes')
api.GriptapeNodes=SimpleNamespace(NodeManager=lambda:node_manager)
sys.modules['griptape_nodes.retained_mode.griptape_nodes']=api
ns={'Base':Base,'Any':object,'Parameter':object,'contextvars':contextvars,'deepcopy':copy.deepcopy,
    'scene_fingerprint':scene_fingerprint,'CONTEXT_SCHEMA':'hmb-image-bash-inputs-v1','RECEIPT_SCHEMA':'hmb-image-bash-apply-v1',
    '_document':lambda value:copy.deepcopy(value),'_url':lambda value:value.get('value','') if isinstance(value,dict) else str(getattr(value,'value','')),
    '_flatten':lambda value:[] if value is None else list(value) if isinstance(value,list) else [value],
    '_hmb_is_registered_node':lambda node,kind:registry.get(node.name) is node}
klass=ast.ClassDef(name='HMBImageBash',bases=[ast.Name(id='Base',ctx=ast.Load())],keywords=[],body=methods,decorator_list=[])
module=ast.fix_missing_locations(ast.Module(body=[klass],type_ignores=[]));exec(compile(module,str(path),'exec'),ns)
Bash=ns['HMBImageBash'];CASES=[]

def make():
    node=Bash();node.name='SyntheticColdGap';registry[node.name]=node;node.engine=engine
    node.metadata={'hmb_image_bash_workspace_id':'workspace','hmb_image_bash_channel_uuid':'channel'}
    node._hmb_prepare_phase='idle';node._hmb_prepare_error='';node._hmb_last_output=None
    node._hmb_node_deleted=False;node._hmb_cold_readiness_scheduled=False;node._hmb_apply_epoch=0
    node._hmb_apply_pending=node._hmb_prepare_pending=node._hmb_cold_restore_pending=None
    node._hmb_cold_input_gap=False;node._hmb_cold_gap_admitted=False;node._hmb_cold_gap_recovery=None
    node._hmb_syncing=False;node._initializing=False;node._hmb_value_callback_depth=0
    node._hmb_apply_work=None;node._hmb_image_bash_live_source_uuid='live-bash'
    node._hmb_auto_pristine_project={'value':'','meta':{'konva_json':{'images':[],'lines':[]},'input_images':[]}}
    values={'bash_image':copy.deepcopy(node._hmb_auto_pristine_project),'image_bash_context':{},'input_images':[]}
    node.values=values;node.get_parameter_value=lambda key:values.get(key)
    node._clear_output_now=lambda:None
    node._status=lambda text:values.update(HMB_BASH_STATUS=text)
    node._publish_header=lambda:True
    node._canvas=lambda:{'width':4,'height':2,'background_color':'#000000'}
    source=SimpleNamespace(name='Source',_hmb_image_bash_live_source_uuid='source-live')
    catalog={'workspaces':[{'workspace_id':'workspace','revision':2,'count':2}]}
    node.source=source;node.catalog=catalog
    node._remote_sources=lambda:[(source,catalog)]
    node._remote_bound_source=lambda candidates:source
    node.callbacks=[];node._schedule_host_callback=lambda callback:node.callbacks.append(callback) or True
    node._queue_prepare=lambda *args,**kwargs:True
    return node

def saved(node):
    records=[{'source_uid':uid,'url':'synthetic:'+uid} for uid in ('a','b')]
    doc={'value':'data:image/png;base64,c3ludGhldGlj','meta':{'created_at':'saved-commit',
        'konva_json':{'images':[],'lines':[]},'input_images':[],
        'hmb_image_bash':{'workspace_id':'workspace','channel_uuid':'channel','workspace_revision':2,
            'node_instance_uuid':'prior-bash','source_bindings':[{'source_uid':row['source_uid']} for row in records]}}}
    receipt={'schema':ns['RECEIPT_SCHEMA'],'editor_commit':'saved-commit','scene_sha256':scene_fingerprint(doc,records,node._canvas()),
        'png_sha256':'1'*64,'rgba_sha256':'2'*64,'width':4,'height':2,'source_hashes':{},'png_base64':'c3ludGhldGlj'}
    doc['meta']['hmb_image_bash']['apply']=receipt
    return doc,records

def gap(node):
    node._sync_metadata_with_input_images()
    assert node._hmb_prepare_phase=='error' and node._hmb_cold_input_gap is True
    assert node._hmb_cold_gap_recovery is None

def arm(node,doc,active=True,target=None):
    lease={'active':active,'node':node if target is None else target};token=assignment.set(lease)
    try:node.before_value_set(SimpleNamespace(name='bash_image'),copy.deepcopy(doc))
    finally:lease['active']=False;assignment.reset(token)

def finish_inputs(node,doc,records):
    node.values['bash_image']=copy.deepcopy(doc)
    node.values['input_images']=[{'value':row['url']} for row in records]
    node.values['image_bash_context']={'schema':ns['CONTEXT_SCHEMA'],'ready':True,'workspace_id':'workspace','revision':2,'records':copy.deepcopy(records)}

def queue(node):
    node._queue_saved_editor_readiness(node.values['image_bash_context'],node._remote_sources(),node.source)

def case(name,fn):
    fn();CASES.append(name)


def dormant():
    n=make();gap(n);doc,records=saved(n);finish_inputs(n,doc,records);queue(n)
    assert n.callbacks==[] and n._hmb_prepare_phase=='error'
case('dormant_gap_without_real_initial_saved_assignment_never_retries',dormant)

def ordinary():
    n=make();doc,records=saved(n);finish_inputs(n,doc,records);n._hmb_prepare_phase='error';n._hmb_prepare_error='unrelated failure';queue(n)
    assert n.callbacks==[] and n._hmb_prepare_error=='unrelated failure'
case('ordinary_live_error_is_not_reset',ordinary)

for label,active,target in [('inactive_copied_context',False,None),('other_node_context',True,object())]:
    def run(active=active,target=target):
        n=make();gap(n);doc,records=saved(n);arm(n,doc,active,target);finish_inputs(n,doc,records);queue(n)
        assert n._hmb_cold_gap_recovery is None and not n.callbacks
    case(label+'_cannot_arm',run)

def valid_once():
    n=make();gap(n);doc,records=saved(n);arm(n,doc);marker=n._hmb_cold_gap_recovery
    assert marker and marker['epoch']==n._hmb_apply_epoch
    n.values['bash_image']=copy.deepcopy(doc);arm(n,doc)
    assert n._hmb_cold_gap_recovery is marker
    finish_inputs(n,doc,records);queue(n)
    assert len(n.callbacks)==1 and n._hmb_prepare_phase=='preparing' and n._hmb_cold_gap_recovery is None
    # A scheduled verifier remains verification, never a ready/output claim.
    queue(n);assert len(n.callbacks)==1
    n._hmb_prepare_phase='error';n._hmb_cold_readiness_scheduled=False;arm(n,doc);queue(n)
    assert len(n.callbacks)==1 and n._hmb_cold_gap_recovery is None
case('valid_initial_and_identical_output_pair_schedule_verifier_only_once',valid_once)

for label,mutate in [
 ('changed_scene',lambda n,d,r:d['meta']['konva_json'].update(future_scene={'changed':True})),
 ('changed_canvas',lambda n,d,r:setattr(n,'_canvas',lambda:{'width':8,'height':2,'background_color':'#000000'})),
 ('foreign_scope',lambda n,d,r:d['meta']['hmb_image_bash'].update(channel_uuid='foreign')),
 ('changed_source_UID',lambda n,d,r:r[0].update(source_uid='different')),
 ('stale_epoch',lambda n,d,r:setattr(n,'_hmb_apply_epoch',n._hmb_apply_epoch+1)),
 ('node_replaced',lambda n,d,r:registry.update({n.name:object()})),
 ('deleted',lambda n,d,r:setattr(n,'_hmb_node_deleted',True)),
]:
    def run(mutate=mutate):
        n=make();gap(n);doc,records=saved(n);arm(n,doc);mutate(n,doc,records);finish_inputs(n,doc,records);queue(n)
        assert not n.callbacks and n._hmb_prepare_phase=='error'
    case(label+'_cannot_publish_or_schedule',run)

for label,mutate in [('bad_receipt_digest',lambda d:d['meta']['hmb_image_bash']['apply'].update(png_sha256='bad')),
    ('missing_receipt_png',lambda d:d['meta']['hmb_image_bash']['apply'].update(png_base64='')),
    ('pending_draft',lambda d:d['meta']['hmb_image_bash'].update(pending_apply={'schema':'hmb-image-bash-pending-apply-v1','editor_commit':'saved-commit'}))]:
    def run(mutate=mutate):
        n=make();gap(n);doc,records=saved(n);mutate(doc);arm(n,doc);finish_inputs(n,doc,records);queue(n)
        assert not n.callbacks and n._hmb_cold_gap_recovery is None
    case(label+'_not_promoted_as_retained',run)

def no_loop():
    n=make();gap(n);doc,records=saved(n);arm(n,doc);finish_inputs(n,doc,records)
    n._schedule_host_callback=lambda callback:False;queue(n);queue(n)
    assert n._hmb_prepare_phase=='error' and not n.callbacks and n._hmb_cold_gap_recovery is None
case('no_host_loop_fails_closed_without_repeat',no_loop)

def failed_verify():
    n=make();gap(n);doc,records=saved(n);arm(n,doc);finish_inputs(n,doc,records);before=copy.deepcopy(doc)
    calls=[]
    def failure(*args):calls.append(True);raise ValueError('synthetic missing/changed PNG source')
    n._restore_saved_output=failure;queue(n);n.callbacks[0]();queue(n);queue(n)
    assert len(calls)==1 and len(n.callbacks)==1 and n._hmb_prepare_phase=='error'
    assert n.values['bash_image']==before and n._hmb_cold_gap_recovery is None
case('verification_failure_preserves_document_and_never_auto_retries',failed_verify)

def live_edit():
    n=make();gap(n);doc,records=saved(n);arm(n,doc);finish_inputs(n,doc,records)
    n.before_value_set(SimpleNamespace(name='bash_image'),doc);queue(n)
    assert n._hmb_cold_gap_recovery is None and not n.callbacks
case('live_Apply_retires_hydration_authority',live_edit)

def clear():
    n=make();gap(n);doc,records=saved(n);arm(n,doc);n._clear_output()
    assert not n._hmb_cold_input_gap and n._hmb_cold_gap_recovery is None
case('explicit_clear_unbind_output_invalidation_retires_marker',clear)

result={'schema':'hmb-cold-initial-input-gap-guards-v1','status':'PASS','case_count':len(CASES),'cases':CASES,
    'product_source':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
    'exact_source_methods':sorted(names),'actualSDK':False,'metadata_only_AST_fixture':True,
    'actual_pixel_verifier_success_claim':False,'actualDesktop_access':False,'paid_calls':0,
    'retained_only_scope':'Pending Apply/prepare are not promoted by this retained recovery; existing cold suites are separate.'}
(OUT/'COLD-INPUT-GAP-GUARDS.json').write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result))
