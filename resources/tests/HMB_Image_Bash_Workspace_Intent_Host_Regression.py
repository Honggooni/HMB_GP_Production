"""Actual private SDK assignment hooks for canonical workspace intents.

Metadata-only synthetic source rows; output production is explicitly replaced
with a no-op so this proves assignment/identity/idempotence, not media pixels.
No Desktop, user workflow execution, providers or production services.
"""
from __future__ import annotations
import asyncio
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
PRODUCT=Path(os.environ.get('HMB_WORKSPACE_INTENT_SOURCE_ROOT',str(ROOT)))
OUT=Path(os.environ.get('HMB_WORKSPACE_INTENT_REPORT_DIR',str(ROOT/'reports/regression-checks/HMB_Image_Bash_Workspace_Intent_Host_Regression')))
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(PRODUCT));sys.dont_write_bytecode=True


async def exercise(engine):
    import HMBImageAssetLibrary as p
    from griptape_nodes.node_library.library_registry import LibraryRegistry,LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    schema=LibrarySchema.model_validate_json((PRODUCT/'griptape-nodes-library.json').read_text('utf-8-sig'))
    library=LibraryRegistry.generate_new_library(schema)
    metadata=next(row.metadata for row in schema.nodes if row.class_name=='HMBImageAssetLibrary')
    library.register_lazy_node_type('HMBImageAssetLibrary',metadata,lambda:p.HMBImageAssetLibrary)
    class ReadonlySink(p.DataNode):
        def __init__(self,**kwargs):
            super().__init__(**kwargs)
            for name,kind,default in (('input_images','list',[]),('image_bash_context','dict',{})):
                self.add_parameter(p.Parameter(name=name,type=kind,default_value=default,
                    input_types=['any','list','dict','list[ImageUrlArtifact]'],
                    allowed_modes={p.ParameterMode.INPUT,p.ParameterMode.PROPERTY}))
        def process(self):raise AssertionError('No Run or generation')
    library.register_lazy_node_type('ReadonlySink',metadata,lambda:ReadonlySink)
    engine.event_manager.initialize_queue();cases=[]
    def send(request,ok=True):
        request.broadcast_result=False;result=engine.handle_request(request)
        assert result.succeeded()==ok,str(result.result_details)
        return result
    flow=send(EnsureWorkflowAndFlowRequest(flow_name='ExplicitWorkspaceIntents'))
    def create(name):
        made=send(CreateNodeRequest(node_type='HMBImageAssetLibrary',specific_library_name=schema.name,
            node_name=name,override_parent_flow_name=flow.flow_name,initial_setup=True,create_error_proxy_on_failure=False))
        node=engine.node_manager.get_node_by_name(made.node_name)
        node._hmb_initial_catalog_scan_pending=False
        node._apply_widget_state=lambda value:node._current_state()
        return node
    def setstate(node,value,initial=False,output=False,ok=True):
        return send(SetParameterValueRequest(node_name=node.name,parameter_name=p.WIDGET_STATE_PARAMETER,
            value=deepcopy(value),initial_setup=initial,is_output=output),ok)
    def current(node):return deepcopy(node._current_state())
    def seed(node,count=2):
        state=p._default_state();state['scan_revision']=1;state['ui_edit_revision']=4
        state['assets']=[dict(asset_library_id='import:'+s,source_uid='import:'+s,source_kind='user',
            asset_id=s,image_name=s,path='data:image/png;base64,AA==',selected=False,selection_order=0,
            import_index=i+1,connected=True,registered=False,media_ref_kind='url',media_signature='synthetic-'+s)
            for i,s in enumerate(('a','b','c'))]
        state['image_bash_workspace']={'workspace_id':str(uuid4()),'revision':2,
            'instances':[{'instance_id':str(uuid4()),'source_uid':'import:'+('a' if i%2==0 else 'b')} for i in range(count)]}
        state['image_bash_active']=True
        state=p._normalize_state(state)
        setstate(node,state,initial=True);setstate(node,state,initial=True,output=True)
        return current(node)
    def command(node,operation,**fields):
        state=current(node);workspace=state['image_bash_workspace']
        return dict(schema=p.IMAGE_BASH_WORKSPACE_EDIT_SCHEMA,version=1,operation_id=str(uuid4()),operation=operation,
            workspace_id=workspace['workspace_id'],expected_revision=workspace['revision'],**fields)
    def wire(node,edit,compact=False):
        state=current(node);state['ui_edit_revision']+=1
        if not compact:return {**state,p.IMAGE_BASH_WORKSPACE_EDIT_KEY:deepcopy(edit)}
        return {'schema':p.IMAGE_ASSET_EDIT_SCHEMA,'version':1,'widget_runtime_lease':state['widget_runtime_lease'],
            'ui_edit_revision':state['ui_edit_revision'],'catalog_identity':{key:state[key] for key in (
                'catalog_root','project_root','project_uid','project_cache_uid','manifest_signature','folder_signature','scan_revision')},
            'selected_source_uids':[a['source_uid'] for a in state['assets'] if a['selected']],
            'edits':{'shot_routing':deepcopy(state['shot_routing']),'image_bash_workspace':deepcopy(state['image_bash_workspace']),
                p.IMAGE_BASH_WORKSPACE_EDIT_KEY:deepcopy(edit)}}
    def count(node):return len(current(node)['image_bash_workspace']['instances'])
    def workspace(node):return current(node)['image_bash_workspace']
    try:
        with mock.patch.object(p,'_discover_project_catalog',side_effect=AssertionError('No catalog scan')):
            node=create('IntentSource');base=seed(node)
            old11=deepcopy(base);old11['ui_edit_revision']=26;old11['image_bash_workspace']['revision']=17
            old11['image_bash_workspace']['instances'] += [{'instance_id':str(uuid4()),'source_uid':'import:a'} for _ in range(9)]
            setstate(node,old11)
            assert workspace(node)==base['image_bash_workspace'];cases.append('same_current_lease_full_passive_2_to11_preserves_canonical')
            comp=wire(node,command(node,'add',source_uid='import:c',new_instance_id=str(uuid4())),True)
            comp['edits'].pop(p.IMAGE_BASH_WORKSPACE_EDIT_KEY);comp['edits']['image_bash_workspace']=old11['image_bash_workspace']
            setstate(node,comp);assert workspace(node)==base['image_bash_workspace'];cases.append('compact_passive_2_to11_preserves_canonical')
            add=command(node,'add',source_uid='import:c',new_instance_id=str(uuid4()));payload=wire(node,add)
            setstate(node,payload);assert count(node)==3 and workspace(node)['revision']==3
            setstate(node,payload);assert count(node)==3;cases.append('explicit_Add_and_same_operation_replay_once')
            same=command(node,'add',source_uid='import:a',new_instance_id=str(uuid4()));setstate(node,wire(node,same,True))
            assert count(node)==3 and workspace(node)['revision']==3;cases.append('Add_existing_source_is_noop')
            first=workspace(node)['instances'][0]['instance_id'];copyedit=command(node,'copy',instance_id=first,new_instance_id=str(uuid4()))
            payload=wire(node,copyedit,True);setstate(node,payload)
            assert count(node)==4 and workspace(node)['instances'][1]['instance_id']==copyedit['new_instance_id']
            setstate(node,payload);assert count(node)==4;cases.append('Copy_is_only_duplicate_source_increase_and_replay_once')
            changed=deepcopy(payload);changed['edits'][p.IMAGE_BASH_WORKSPACE_EDIT_KEY]['new_instance_id']=str(uuid4())
            before=deepcopy(workspace(node));setstate(node,changed,ok=False);assert workspace(node)==before
            cases.append('operation_id_cannot_change_payload')
            stale=command(node,'copy',instance_id=first,new_instance_id=str(uuid4()));stale['expected_revision']=2
            setstate(node,wire(node,stale),ok=False);assert workspace(node)==before;cases.append('stale_revision_rejected_without_change')
            remove=command(node,'remove',instance_id=copyedit['new_instance_id']);setstate(node,wire(node,remove))
            assert count(node)==3;cases.append('explicit_Remove')
            rows=deepcopy(workspace(node)['instances']);move=command(node,'reorder',instance_id=rows[0]['instance_id'],target_instance_id=rows[2]['instance_id'])
            setstate(node,wire(node,move,True));assert workspace(node)['instances']==[rows[1],rows[2],rows[0]]
            cases.append('Reorder_matches_old_target_index_semantics')
            preserved=create('AuthoredEleven');original=seed(preserved,11)
            assert workspace(preserved)==original['image_bash_workspace'] and count(preserved)==11
            cases.append('actual_initial_input_output_restore_preserves_authored11')
            bad=wire(node,command(node,'copy',instance_id=first,new_instance_id=str(uuid4())))
            before=deepcopy(workspace(node));setstate(node,bad,output=True,ok=False);assert workspace(node)==before
            cases.append('live_output_assignment_cannot_mutate_structure')
            direct=command(node,'copy',instance_id=first,new_instance_id=str(uuid4()));before_count=count(node)
            node.set_parameter_value(p.WIDGET_STATE_PARAMETER,json.dumps(wire(node,direct)),skip_before_value_set=True)
            assert count(node)==before_count+1;setstate(node,wire(node,direct));assert count(node)==before_count+1
            cases.append('direct_set_skip_before_is_guarded_and_committed_once')
            failing=create('NativeWriteFailure');seed(failing);first2=workspace(failing)['instances'][0]['instance_id']
            retry=command(failing,'copy',instance_id=first2,new_instance_id=str(uuid4()));payload=wire(failing,retry)
            old=deepcopy(workspace(failing))
            with mock.patch.object(p.DataNode,'set_parameter_value',side_effect=RuntimeError('synthetic native write failure')):
                setstate(failing,payload,ok=False)
            assert workspace(failing)==old and p._parse_mapping(failing._hmb_last_accepted_widget_state)['image_bash_workspace']==old
            assert retry['operation_id'] not in failing._hmb_image_bash_mutation_receipts
            setstate(failing,payload);assert count(failing)==3;cases.append('failed_native_write_not_cached_and_retry_adds_exactly_once')
            late=command(failing,'copy',instance_id=first2,new_instance_id=str(uuid4()));payload=wire(failing,late)
            with mock.patch.object(failing,'_apply_widget_state',side_effect=RuntimeError('synthetic after-set publication failure')):
                setstate(failing,payload,ok=False)
            setstate(failing,payload);assert count(failing)==4;cases.append('post_write_failure_retry_never_adds_twice')
            # A foreign direct after-only assignment cannot bypass the wrapper.
            passive=current(failing);before=deepcopy(workspace(failing));passive['image_bash_workspace']=deepcopy(old11['image_bash_workspace'])
            failing.parameter_values[p.WIDGET_STATE_PARAMETER]=json.dumps(passive)
            failing.after_value_set(failing.get_parameter_by_name(p.WIDGET_STATE_PARAMETER),json.dumps(passive))
            assert workspace(failing)==before;cases.append('after_only_passive_assignment_restores_canonical_workspace')
            bounded=create('BoundedLedger');seed(bounded)
            for index in range(p.MAX_IMAGE_BASH_MUTATION_RECEIPTS+3):
                noop=command(bounded,'add',source_uid='import:a',new_instance_id=str(uuid4()))
                setstate(bounded,wire(bounded,noop))
            assert count(bounded)==2 and len(bounded._hmb_image_bash_mutation_receipts)==p.MAX_IMAGE_BASH_MUTATION_RECEIPTS
            cases.append('runtime_operation_ledger_bounded_128_without_collapsing_existing_rows')
            malformed=command(node,'add',source_uid='import:c',new_instance_id=str(uuid4()));malformed['operation']=[]
            before=deepcopy(workspace(node));setstate(node,wire(node,malformed),ok=False);assert workspace(node)==before
            cases.append('malformed_operation_is_visible_rejection_not_state_change')
            # Two actual retained wires terminate at a synthetic metadata sink.
            # This is physical graph coverage, not real Bash pixel coverage.
            sink_result=send(CreateNodeRequest(node_type='ReadonlySink',specific_library_name=schema.name,
                node_name='ReadonlyWireSink',override_parent_flow_name=flow.flow_name,initial_setup=True,create_error_proxy_on_failure=False))
            sink=engine.node_manager.get_node_by_name(sink_result.node_name)
            node.parameter_output_values[p.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER]=[]
            node.parameter_output_values[p.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER]={'synthetic':'unchanged'}
            from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest,ListConnectionsForNodeRequest
            for source,target in ((p.IMAGE_BASH_IMAGES_OUTPUT_PARAMETER,'input_images'),(p.IMAGE_BASH_CONTEXT_OUTPUT_PARAMETER,'image_bash_context')):
                send(CreateConnectionRequest(source_node_name=node.name,source_parameter_name=source,
                    target_node_name=sink.name,target_parameter_name=target))
            def wire_snapshot():
                result=send(ListConnectionsForNodeRequest(node_name=node.name))
                incoming=((edge.source_node_name,edge.source_parameter_name,
                    node.name,edge.target_parameter_name) for edge in result.incoming_connections)
                outgoing=((node.name,edge.source_parameter_name,
                    edge.target_node_name,edge.target_parameter_name) for edge in result.outgoing_connections)
                return tuple(sorted((*incoming,*outgoing)))
            edges_before=wire_snapshot()
            sink_before={name:deepcopy(sink.get_parameter_value(name)) for name in ('input_images','image_bash_context')}
            # Authority must publish a view event, not a STATE output slot.
            from griptape_nodes.retained_mode.events.execution_events import ParameterValueUpdateEvent
            state_before=node.get_parameter_value(p.WIDGET_STATE_PARAMETER);accepted_before=node._hmb_last_accepted_widget_state
            outputs_before={k:deepcopy(v) for k,v in node.parameter_output_values.items() if k!=p.THUMBNAIL_PATCH_PARAMETER}
            receipts_before=deepcopy(node._hmb_image_bash_mutation_receipts);events=[]
            original_put=engine.event_manager.put_event
            def capture(event):events.append(event);return original_put(event)
            request={'schema':p.THUMBNAIL_BRIDGE_SCHEMA,'version':1,'operation':'widget_authority','phase':'request','request_id':'authority-readonly'}
            with mock.patch.object(engine.event_manager,'put_event',capture),mock.patch.object(node,'_apply_widget_state',side_effect=AssertionError('Readonly must not apply state')):
                send(SetParameterValueRequest(node_name=node.name,parameter_name=p.THUMBNAIL_PATCH_PARAMETER,value=request))
            assert node.get_parameter_value(p.WIDGET_STATE_PARAMETER)==state_before and node._hmb_last_accepted_widget_state==accepted_before
            assert {k:v for k,v in node.parameter_output_values.items() if k!=p.THUMBNAIL_PATCH_PARAMETER}==outputs_before
            assert node._hmb_image_bash_mutation_receipts==receipts_before
            response=node.get_parameter_value(p.THUMBNAIL_PATCH_PARAMETER)
            assert response['canonical_scope']==p._image_bash_widget_authority_scope(current(node))
            assert response['canonical_scope_sha256']==hashlib.sha256(p._json_text(response['canonical_scope']).encode()).hexdigest()
            assert response['canonical_node_name']==node.name
            assert any(isinstance(getattr(getattr(e,'wrapped_event',None),'payload',None),ParameterValueUpdateEvent) and e.wrapped_event.payload.parameter_name==p.WIDGET_STATE_PARAMETER for e in events)
            cases.append('readonly_authority_keeps_STATE_accepted_real_outputs_ledger_and_emits_view_only')
            assert wire_snapshot()==edges_before
            assert {name:sink.get_parameter_value(name) for name in sink_before}==sink_before
            cases.append('readonly_authority_preserves_two_actual_retained_wires_and_sink_inputs')
        result={'status':'PASS','case_count':len(cases),'cases':cases,'product_path':p.__file__,
            'source_sha256':hashlib.sha256(Path(p.__file__).read_bytes()).hexdigest(),
            'scope':'Actual isolated SDK assignment hooks; synthetic metadata; normal output-producing method controlled no-op. No media pixel/real Bash proof claimed.',
            'actual_Desktop':False,'user_files_executed':0,'paid_calls':0}
        (OUT/'WORKSPACE-INTENT-HOST.json').write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result))
    finally:LibraryRegistry.unregister_library(schema.name,event_manager=engine.event_manager)


if __name__=='__main__':
    previous=Path.cwd()
    with tempfile.TemporaryDirectory(prefix='intent-private-',dir=OUT,ignore_cleanup_errors=True) as temporary:
        folder=Path(temporary);keys=('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','GTN_ENGINE_CONFIG_DIR','GTN_ENGINE_DATA_DIR','GTN_ENGINE_STATE_DIR','GTN_CONFIG_WORKSPACE_DIRECTORY')
        env={key:str(folder/key) for key in keys}
        for value in env.values():Path(value).mkdir()
        with mock.patch.dict(os.environ,env),mock.patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')):
            os.chdir(folder);logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:asyncio.run(exercise(engine))
            finally:os.chdir(previous);logging.shutdown()
