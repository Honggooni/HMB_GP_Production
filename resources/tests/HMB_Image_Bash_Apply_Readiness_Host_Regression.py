"""Actual SDK prepare/Apply races, header coherence and preserved data.

Synthetic local inputs only; the compiled native modal is a separate test.
"""
from __future__ import annotations
import asyncio
import base64
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

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'resources/tests'))
sys.dont_write_bytecode=True
OUT=Path(os.environ.get('HMB_BASH_APPLY_READINESS_REPORT_DIR',str(ROOT/'reports/regression-checks/HMB_Image_Bash_Apply_Readiness_Host_Regression')));OUT.mkdir(parents=True,exist_ok=True)
import HMB_Image_Bash_Apply_Worker_Host_Regression as fixture
RESULT={}

async def check(engine,node,source,set_value,candidate,png,directory,context,records,settled,send):
    import HMBImageBash as product
    from _hmb_image_bash_state import scene_fingerprint
    from griptape_nodes.files.file import File
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.parameter_events import GetParameterValueRequest
    second=directory/'second.png';second.write_bytes(png('purple'))
    records=records+[{'source_uid':'second-source','url':str(second),'name':'Second'}]
    context={**context,'revision':2,'records':records}
    set_value('IMAGE_BASH_IMAGES_OUT',[row['url'] for row in records],target=source,initial=True)
    set_value('IMAGE_BASH_CONTEXT_OUT',context,target=source,initial=True)
    set_value('input_images',[row['url'] for row in records]);set_value('image_bash_context',context)
    await settled()
    def header():
        node._publish_header();return node.get_parameter_value(product.HEADER_PARAMETER)['preparation']
    def document():return product._document(node.get_parameter_value('bash_image'))
    def fresh(commit,color='green'):
        value=candidate(commit,color)
        value['meta']['hmb_image_bash'].pop('editor_snapshot_id',None)
        return value
    start=header();assert start['ready'] and start['editor_snapshot_id']
    assert start['editor_commit'] is None  # A never-Applied stock document has no created_at.
    original_bytes={r['source_uid']:Path(r['url']).read_bytes() for r in records}
    original_snapshot=start['editor_snapshot_id']
    # The successful Apply must supersede its cancelled preparation, mark
    # inputs ready and permit repeated editor opens immediately, without Run.
    node._sync_metadata_with_input_images()
    assert node._hmb_prepare_phase=='preparing' and node._hmb_prepare_pending is not None
    value=fresh('apply-ahead-of-prepare')
    value['meta']['konva_json']['lines'].append({'points':[0,0,2,1],'stroke':'red','strokeWidth':1})
    scope=node._apply_scope()
    value['meta']['hmb_image_bash']['pending_prepare']={'schema':'hmb-image-bash-pending-prepare-v1',
        'scope':{k:scope[k] for k in ('workspace_id','channel_uuid','workspace_revision')},
        'source_uids':[r['source_uid'] for r in records]}
    set_value('bash_image',value);await settled()
    committed=document();ready=header()
    assert ready['ready'] and ready['phase']=='ready',ready
    assert node._hmb_prepare_pending is None and node._hmb_apply_pending is None
    assert '출력 완료' in node.get_parameter_value('HMB_BASH_STATUS')
    assert committed['meta']['konva_json']==value['meta']['konva_json']
    hmb=committed['meta']['hmb_image_bash']
    assert 'pending_apply' not in hmb and 'pending_prepare' not in hmb
    assert ready['editor_snapshot_id']==hmb['editor_snapshot_id']==node._hmb_editor_snapshot_id
    assert ready['editor_snapshot_id']!=original_snapshot
    assert ready['editor_commit']=='apply-ahead-of-prepare'
    receipt=deepcopy(hmb['apply']);output=node.parameter_output_values['output_image']
    output_path=Path(File(output.value).resolve());previous_png=output_path.read_bytes()
    with mock.patch.object(product,'_read_bytes',side_effect=AssertionError('Header projection read pixels')):
        for _ in range(3):assert header()==ready
    assert document()==committed and output_path.read_bytes()==previous_png
    assert {r['source_uid']:Path(r['url']).read_bytes() for r in records}==original_bytes
    # Token minting changes no scene/receipt/source/output content.
    fingerprint=scene_fingerprint(committed,records,node._canvas())
    changed=deepcopy(committed);changed['meta']['hmb_image_bash']['editor_snapshot_id']='client-forged-token'
    assert scene_fingerprint(changed,records,node._canvas())==fingerprint
    assert changed['meta']['hmb_image_bash']['apply']==receipt
    # A stale serialized UI output cache must not beat the freshly updated
    # property map, including a header read during the document notification.
    node.parameter_output_values[product.HEADER_PARAMETER] = {"preparation":deepcopy(ready)}
    original_publish=node.publish_update_to_parameter;observed=[]
    def publish(parameter,value):
        if parameter=="bash_image":
            rpc=engine.handle_request(GetParameterValueRequest(node_name=node.name,parameter_name=product.HEADER_PARAMETER,broadcast_result=False))
            assert rpc.succeeded(),rpc.result_details
            state=rpc.value["preparation"]
            if state["ready"]:assert state["editor_snapshot_id"]==value["meta"]["hmb_image_bash"]["editor_snapshot_id"]
            else:assert state["phase"]=="preparing"
            assert len(str(rpc.result_details))<12000
            observed.append(state)
        return original_publish(parameter,value)
    with mock.patch.object(node,'publish_update_to_parameter',side_effect=publish):node._set_project(changed)
    assert observed
    authoritative=document();nonce=authoritative['meta']['hmb_image_bash']['editor_snapshot_id']
    assert nonce!='client-forged-token' and nonce!=ready['editor_snapshot_id']
    assert authoritative['meta']['hmb_image_bash']['apply']==receipt
    assert header()['editor_snapshot_id']==nonce
    assert output_path.read_bytes()==previous_png
    RESULT.update(two_sources=True,prepare_apply_success_ready=True,repeated_reopen_projection_ready=True,
        no_header_pixel_IO=True,pending_markers_removed_after_success=True,
        host_snapshot_nonce_noncontent=True,missing_editor_commit_is_null=True)
    # External HTTP remains the original synchronous SDK-policy fallback.
    # It must complete an obsolete prepare too; no network is used here.
    node._sync_metadata_with_input_images()
    value=fresh('sync-fallback-ahead-of-prepare','blue');value['value']='https://offline-fixture.invalid/apply.png'
    original_read=product._read_bytes
    def read(url):return png('blue') if url==value['value'] else original_read(url)
    with mock.patch.object(product,'_read_bytes',side_effect=read):
        set_value('bash_image',value);await settled()
    assert header()['ready'] and node._hmb_prepare_phase=='ready'
    assert File(node.parameter_output_values['output_image'].value).read_bytes()==png('blue')
    assert node._hmb_prepare_pending is None
    RESULT['synchronous_fallback_same_ready_fence']=True
    # A lost document event is repaired by one explicit scoped Retry; normal
    # header polling remains metadata-only and never republishes the PNG.
    snapshot_before=header()['editor_snapshot_id'];before_retry=document()
    emitted=[]
    def count_document(parameter,value):
        if parameter=='bash_image':emitted.append(deepcopy(value))
        return original_publish(parameter,value)
    with mock.patch.object(source,'_hmb_retry_image_bash_inputs',return_value={},create=True), \
         mock.patch.object(node,'publish_update_to_parameter',side_effect=count_document):
        set_value(product.HEADER_PARAMETER,{'hmb_image_bash_command':{'operation':'retry_inputs',
            'source_node_name':source.name,'workspace_id':context['workspace_id'],
            'source_instance_id':node._remote_source_instance(source)}})
        await settled()
        snapshot_after=header()['editor_snapshot_id']
        assert snapshot_after and snapshot_after!=snapshot_before and len(emitted)==1
        assert node._hmb_snapshot_republish_pending is None
        for _ in range(3):
            rpc=engine.handle_request(GetParameterValueRequest(node_name=node.name,parameter_name=product.HEADER_PARAMETER,broadcast_result=False))
            assert rpc.succeeded() and rpc.value['preparation']['editor_snapshot_id']==snapshot_after
        assert len(emitted)==1
    after_retry=document()
    assert after_retry['meta']['konva_json']==before_retry['meta']['konva_json']
    assert after_retry['meta']['hmb_image_bash']['apply']==before_retry['meta']['hmb_image_bash']['apply']
    assert after_retry['value']==before_retry['value']
    RESULT.update(explicit_retry_one_verified_document_republish=True,header_poll_no_large_republish=True,
        stale_serialized_header_output_cache_cannot_override_nonce=True,header_reply_fresh_during_doc_event=True)
    # A producer catalog can advance before its consumer notification. A
    # completed old Apply must not make that older workspace ready or write.
    finish=product.HMBImageBash._finish_apply;captured=[]
    current_output=node.parameter_output_values['output_image'];current_file=Path(File(current_output.value).resolve());current_bytes=current_file.read_bytes()
    with mock.patch.object(product.HMBImageBash,'_finish_apply',autospec=True,side_effect=lambda *a,**k:captured.append((a,k))):
        node._sync_metadata_with_input_images();set_value('bash_image',fresh('producer-catalog-ahead','yellow'))
        for _ in range(200):
            if captured:break
            await asyncio.sleep(.005)
    assert captured
    source.set_parameter_value('IMAGE_BASH_CONTEXT_OUT',{**context,'revision':context['revision']+1})
    draft=document();args,kwargs=captured[0];finish(*args,**kwargs)
    assert not header()['ready'] and node._hmb_prepare_phase!='ready'
    assert document()==draft and current_file.read_bytes()==current_bytes
    assert node.parameter_output_values['output_image']==current_output
    source.set_parameter_value('IMAGE_BASH_CONTEXT_OUT',context)
    node._sync_metadata_with_input_images();await settled()
    set_value('bash_image',fresh('after-catalog-catchup','blue'));await settled()
    RESULT['producer_catalog_ahead_cannot_promote_old_apply']=True
    # A new source notification wins over a completed-but-unpublished Apply.
    before=document();old_output=node.parameter_output_values['output_image']
    old_file=Path(File(old_output.value).resolve());old_bytes=old_file.read_bytes()
    finish=product.HMBImageBash._finish_apply;captured=[]
    with mock.patch.object(product.HMBImageBash,'_finish_apply',autospec=True,
            side_effect=lambda *a,**k:captured.append((a,k))):
        node._sync_metadata_with_input_images();set_value('bash_image',fresh('new-context-wins','yellow'))
        for _ in range(200):
            if captured:break
            await asyncio.sleep(.005)
    assert captured
    unready={**context,'ready':False,'preparation_phase':'preparing','requested_count':2}
    set_value('image_bash_context',unready)
    current_draft=document();args,kwargs=captured[0];finish(*args,**kwargs)
    assert not header()['ready'] and node._hmb_prepare_phase!='ready'
    assert document()==current_draft and old_file.read_bytes()==old_bytes
    assert node.parameter_output_values['output_image']==old_output
    RESULT['new_input_not_overwritten_by_old_apply_readiness']=True
    context={**context,'revision':3,'ready':True}
    set_value('IMAGE_BASH_CONTEXT_OUT',context,target=source,initial=True)
    set_value('image_bash_context',context);await settled()
    # Same revision + retained records + ready=False during the synchronous
    # fallback must survive its old callback without inputs_unready being reset.
    set_value('bash_image',fresh('before-sync-false-guard','green'));await settled()
    sync_output=node.parameter_output_values['output_image'];sync_path=Path(File(sync_output.value).resolve());sync_bytes=sync_path.read_bytes()
    value=fresh('sync-context-became-unready','blue');value['value']='https://offline-fixture.invalid/guard.png'
    raw_reader=product._read_bytes
    def change_during_read(url):
        if url==value['value']:
            set_value('image_bash_context',{**context,'ready':False,'preparation_phase':'preparing','requested_count':2})
            return png('blue')
        return raw_reader(url)
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    with mock.patch.object(product,'_read_bytes',side_effect=change_during_read):
        rejected=engine.handle_request(SetParameterValueRequest(node_name=node.name,parameter_name='bash_image',value=value,broadcast_result=False))
    assert rejected.failed()
    assert node._hmb_inputs_unready is True and not header()['ready']
    assert sync_path.read_bytes()==sync_bytes and node.parameter_output_values['output_image']==sync_output
    set_value('image_bash_context',context);await settled()
    RESULT['same_revision_unready_async_and_sync_guard']=True
    # Leave the intentionally non-optimized external-URL branch above before
    # exercising a real queued preparation. The rejected value remains a
    # draft by design; a fresh data-URL Apply restores the worker path.
    set_value('bash_image',fresh('before-invalid-prepare-worker','green'));await settled()
    # Invalid PNG while superseding a prepare must neither publish nor leave
    # an endless preparing state. The complete old file and draft survive.
    node._sync_metadata_with_input_images()
    assert node._hmb_prepare_phase=='preparing' and node._hmb_prepare_pending is not None
    bad=fresh('invalid-output-during-prepare');bad['value']='data:image/png;base64,'+base64.b64encode(b'not PNG').decode()
    previous_receipt=deepcopy(document()['meta']['hmb_image_bash'].get('apply'))
    set_value('bash_image',bad);await settled()
    failed=document()
    assert failed['meta']['konva_json']==bad['meta']['konva_json']
    assert failed['value']==bad['value'] and failed['meta']['hmb_image_bash'].get('apply')==previous_receipt
    assert node._hmb_prepare_phase=='error' and not header()['ready']
    assert node._hmb_prepare_pending is None and node._hmb_apply_pending is None
    assert '다시' in node._hmb_prepare_error and old_file.read_bytes()==old_bytes
    RESULT['failed_apply_no_false_ready_actionable_retry_and_draft_preserved']=True
    node._sync_metadata_with_input_images();await settled();assert header()['ready']
    # An output error with already verified inputs keeps recovery editor open.
    bad=fresh('invalid-output-inputs-already-ready');bad['value']='data:image/png;base64,'+base64.b64encode(b'not PNG').decode()
    set_value('bash_image',bad);await settled()
    assert node._hmb_prepare_phase=='ready' and header()['ready']
    assert document()['value']==bad['value'] and old_file.read_bytes()==old_bytes
    RESULT['known_ready_inputs_keep_failed_draft_openable']=True
    saved=send(SerializeFlowToCommandsRequest(flow_name=engine.node_manager.get_node_parent_flow_by_name(node.name),include_create_flow_command=True))
    assert saved.succeeded()
    assert {r['source_uid']:Path(r['url']).read_bytes() for r in records}==original_bytes
    RESULT.update(status='PASS',product_path=product.__file__,paid_calls=0,network_calls=0,Run_calls=0,
        serializer_success=True,actual_desktop=False)

if __name__=='__main__':
    previous=Path.cwd()
    with tempfile.TemporaryDirectory(prefix='bash-apply-reopen-',dir=OUT) as temp:
        directory=Path(temp)
        keys=('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','GTN_ENGINE_CONFIG_DIR','GTN_ENGINE_DATA_DIR','GTN_ENGINE_STATE_DIR','GTN_CONFIG_WORKSPACE_DIRECTORY')
        env={key:str(directory/key) for key in keys}
        for value in env.values():Path(value).mkdir()
        env.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(fixture.STANDARD),HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(fixture.EDITOR))
        with mock.patch.dict(os.environ,env),mock.patch.object(socket,'create_connection',side_effect=fixture.deny):
            os.chdir(directory);logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:asyncio.run(fixture.exercise(engine,directory,extension=check))
            finally:os.chdir(previous);logging.shutdown()
    (OUT/'APPLY-REOPEN-HOST-RESULT.json').write_text(json.dumps(RESULT,indent=2),encoding='utf-8')
    print(json.dumps(RESULT))
