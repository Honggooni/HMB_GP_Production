"""Actual private SDK saved-Apply worker: responsiveness and stale-result fences."""
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
import threading
import time
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'resources/tests'))
sys.dont_write_bytecode=True
import HMB_Image_Bash_Apply_Worker_Host_Regression as fixture
OUT=Path(os.environ.get('HMB_BASH_COLD_RESTORE_REPORT_DIR',str(ROOT/'reports/regression-checks/HMB_Image_Bash_Cold_Restore_Worker_Host_Regression')));OUT.mkdir(parents=True,exist_ok=True)
RESULT={}

async def check(engine,node,producer,set_value,candidate,png,directory,context,records,settled,send):
    import HMBImageBash as product
    from _hmb_image_bash_state import scene_fingerprint
    from griptape_nodes.files.file import File
    from griptape_nodes.retained_mode.events.flow_events import GetTopLevelFlowRequest
    from griptape_nodes.retained_mode.events.flow_events import SerializeFlowToCommandsRequest
    from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest,DeleteConnectionRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest,DeleteNodeRequest
    second=directory/'second.png';second.write_bytes(png('purple'))
    records=records+[{'source_uid':'second','url':str(second),'name':'Second'}]
    context={**context,'revision':2,'records':records}
    set_value('IMAGE_BASH_IMAGES_OUT',[r['url'] for r in records],target=producer,initial=True)
    set_value('IMAGE_BASH_CONTEXT_OUT',context,target=producer,initial=True)
    set_value('input_images',[r['url'] for r in records]);set_value('image_bash_context',context);await settled()
    async def drain():
        for _ in range(1000):
            work=node._hmb_apply_work
            if not any((node._hmb_apply_pending,node._hmb_prepare_pending,node._hmb_cold_restore_pending,
                    work['active'],work['completed'],work['publish_scheduled'])):return
            await asyncio.sleep(.005)
        raise AssertionError('Snapshot worker did not drain')
    def document():return product._document(node.get_parameter_value('bash_image'))
    def ready():node._publish_header();return node.get_parameter_value(product.HEADER_PARAMETER)['preparation']['ready']
    async def valid(commit):
        set_value('bash_image',candidate(commit));await drain()
        assert ready(),node.get_parameter_value('HMB_BASH_STATUS')
    await valid('cold-worker-baseline')
    original=deepcopy(document());receipt=deepcopy(original['meta']['hmb_image_bash']['apply'])
    output_path=Path(File(node.parameter_output_values['output_image'].value).resolve());output_bytes=output_path.read_bytes()
    source_bytes={r['url']:Path(r['url']).read_bytes() for r in records}
    urls={r['url'] for r in original['meta']['input_images']}|{r['src'] for r in original['meta']['konva_json']['images']}
    def cold_reset():
        node._hmb_prepare_phase='idle';node._hmb_prepare_error=''
        node._hmb_last_output=None;node._hmb_cold_readiness_scheduled=False
        node._hmb_restore_pending=True
    raw_snapshot=product.HMBImageBash._snapshot_read
    file_read=File.read_bytes;host=threading.get_ident();sdk_worker_calls=[];reads=[]
    def forbid_worker_sdk(file):
        if threading.get_ident()!=host:
            sdk_worker_calls.append(True);raise AssertionError('SDK File read on worker')
        return file_read(file)
    def delayed(task,url):
        if task['kind']=='cold_restore':
            reads.append((url,threading.get_ident()==host))
            if url in urls:time.sleep(.30)
        return raw_snapshot(task,url)
    cold_reset();query={};beats=[];finished=asyncio.Event();stop_beats=asyncio.Event();start=time.perf_counter_ns()
    async def pulse():
        while not stop_beats.is_set():beats.append(time.perf_counter_ns());await asyncio.sleep(.01)
    def query_flow():
        query['started_ns']=time.perf_counter_ns()
        found=engine.handle_request(GetTopLevelFlowRequest(broadcast_result=False))
        query.update(completed_ns=time.perf_counter_ns(),success=found.succeeded())
        finished.set()
    with mock.patch.object(File,'read_bytes',forbid_worker_sdk),mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=delayed):
        pulse_task=asyncio.create_task(pulse());await asyncio.sleep(0)
        asyncio.get_running_loop().call_later(.01,query_flow)
        node._publish_header();await asyncio.wait_for(finished.wait(),2)
        assert query['success'] and query['started_ns']-start<200_000_000
        assert node._hmb_cold_restore_pending is not None and not ready()
        assert node.parameter_output_values.get('output_image') is None
        pending=node._hmb_cold_restore_pending;epoch=node._hmb_apply_epoch
        for _ in range(10):node._restore_saved_output(document(),records)
        assert node._hmb_cold_restore_pending is pending and node._hmb_apply_epoch==epoch
        await drain();stop_beats.set();await pulse_task
    assert not sdk_worker_calls and all(not on_host for _,on_host in reads)
    assert sum(url in urls for url,_ in reads)==4  # Full read/decode + final raw SHA pass.
    assert ready() and document()==original and output_path.read_bytes()==output_bytes
    RESULT['slow_read_responsive']={'query_started_after_ns':query['started_ns']-start,'query_handler_ns':query['completed_ns']-query['started_ns'],
        'host_pulses_while_pending':len(beats),'injected_seconds_per_source_read':.30,'source_reads':4,
        'total_verification_elapsed_ns':time.perf_counter_ns()-start,
        'all_snapshot_reads_off_host':True,'SDK_worker_read_calls':0,'pending_output_not_promoted':True,'same_intent_deduped':True}
    # Run the other saved-restore entry point and preserve non-render edits.
    entered=threading.Event();release=threading.Event()
    def gated(task,url):
        raw=raw_snapshot(task,url)
        current_urls={row['url'] for row in task['project'].get('meta',{}).get('input_images',[])}
        if task['kind']=='cold_restore' and url in current_urls and not entered.is_set():
            entered.set();assert release.wait(3)
        return raw
    async def wait_entered():
        for _ in range(300):
            if entered.is_set():return
            await asyncio.sleep(.005)
        raise AssertionError('Cold worker gate not entered')
    cold_reset()
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._schedule_restore();await wait_entered()
        changed=deepcopy(document());changed['meta']['viewport']={'x':94,'y':17,'scale':1.5};changed['id']='new-envelope';changed['reference']='new-ref'
        set_value('bash_image',changed,initial=True)
        release.set();await drain()
    assert document()['meta']['viewport']==changed['meta']['viewport'] and document()['id']=='new-envelope' and document()['reference']=='new-ref'
    assert document()['meta']['hmb_image_bash']['apply']==receipt and output_path.read_bytes()==output_bytes and ready()
    RESULT['schedule_restore_worker_and_viewport_envelope_preserved']=True
    # Same-URL bytes changed after the first read must fail the fresh worker SHA.
    entered.clear();release.clear();cold_reset();before=deepcopy(document())
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        path=Path(records[0]['url']);stat=path.stat();path.write_bytes(png('blue'));os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        release.set();await drain()
    assert node._hmb_prepare_phase=='error' and not ready() and document()==before
    assert output_path.read_bytes()==output_bytes
    for path,data in source_bytes.items():Path(path).write_bytes(data)
    RESULT['same_url_same_size_mtime_changed_during_worker_rejected']=True
    # Missing source: no silent defaults, scene/output bytes remain unchanged.
    cold_reset();before=deepcopy(document());Path(records[1]['url']).unlink()
    node._restore_saved_output(document(),records);await drain()
    assert node._hmb_prepare_phase=='error' and document()==before and output_path.read_bytes()==output_bytes
    Path(records[1]['url']).write_bytes(source_bytes[records[1]['url']])
    RESULT['missing_source_rejected_without_data_loss']=True
    # Output setting changed with no scene/epoch change still invalidates commit.
    entered.clear();release.clear();cold_reset();before=deepcopy(document());setting=node.get_parameter_value('output_file')
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        set_value('output_file',str(directory/'never-written.png'))
        release.set();await drain()
    assert node._hmb_prepare_phase=='error' and document()==before and output_path.read_bytes()==output_bytes
    assert not (directory/'never-written.png').exists();set_value('output_file',setting)
    RESULT['changed_output_setting_rejects_stale_restore']=True
    # The preceding source failure intentionally leaves input preparation
    # invalid. Re-prepare through the actual current-input path before using
    # the editor again; a stale-source Apply must not be treated as valid.
    node._sync_metadata_with_input_images();await drain();await valid('before-new-apply')
    output_path=Path(File(node.parameter_output_values['output_image'].value).resolve())
    # A new Apply is the latest intent and cannot be overwritten by old restore.
    entered.clear();release.clear();cold_reset()
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        set_value('bash_image',candidate('latest-new-apply','yellow'))
        release.set();await drain()
    assert document()['meta']['hmb_image_bash']['apply']['editor_commit']=='latest-new-apply' and ready(),{
        'commit':document()['meta']['hmb_image_bash']['apply']['editor_commit'],
        'phase':node._hmb_prepare_phase,'status':node.get_parameter_value('HMB_BASH_STATUS'),
        'error':node._hmb_prepare_error}
    RESULT['new_apply_supersedes_old_restore']=True
    output_path=Path(File(node.parameter_output_values['output_image'].value).resolve())
    # A deliberately selected Run keeps its original synchronous verification;
    # the canceled background result must not later turn it into an error.
    entered.clear();release.clear();cold_reset()
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        node.process();release.set();await drain()
    assert ready() and node._hmb_cold_restore_pending is None
    RESULT['explicit_Run_supersedes_old_restore']=True
    output_path=Path(File(node.parameter_output_values['output_image'].value).resolve())
    # Custom/unsupported snapshots retain the original synchronous SDK path.
    cold_reset();host_verify=product.HMBImageBash._verify_apply;called=[]
    def observe_verify(self,*args,**kwargs):called.append(threading.get_ident()==host);return host_verify(self,*args,**kwargs)
    with mock.patch.object(product.HMBImageBash,'_snapshot_read_paths',return_value=None),mock.patch.object(product.HMBImageBash,'_verify_apply',observe_verify):
        node._restore_saved_output(document(),records)
    assert called==[True] and ready() and node._hmb_cold_restore_pending is None
    RESULT['unsupported_transport_original_sync_policy_preserved']=True
    # Legacy receipts may store their only output destination in the separate
    # historical verification field. Pending serialization must retain it.
    legacy=deepcopy(document());legacy['meta']['hmb_image_bash']['apply'].pop('output_path',None)
    set_value('bash_image',legacy,initial=True);legacy_proof=deepcopy(node.get_parameter_value('HMB_BASH_VERIFICATION'))
    assert legacy_proof.get('output')
    entered.clear();release.clear();cold_reset()
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        assert node.parameter_output_values.get('output_image') is None
        assert node.get_parameter_value('HMB_BASH_VERIFICATION')==legacy_proof
        serialized=send(SerializeFlowToCommandsRequest(flow_name=engine.node_manager.get_node_parent_flow_by_name(node.name),include_create_flow_command=True))
        assert any(value==legacy_proof for value in serialized.serialized_flow_commands.unique_parameter_uuid_to_values.values())
        # Controlled new-process task loss, without replaying a saved file.
        node._hmb_apply_epoch+=1;node._hmb_cold_restore_pending=None
        release.set();await drain()
    cold_reset();node._restore_saved_output(document(),records);await drain()
    assert ready() and document()['meta']['hmb_image_bash']['apply']==legacy['meta']['hmb_image_bash']['apply']
    RESULT['legacy_proof_path_preserved_in_pending_save_and_transient_cold_reset']=True
    # Missing/tampered existing completed file never recreates that file and
    # never changes the authored scene or historical receipt.
    for mode in ('tampered','missing'):
        cold_reset();before=deepcopy(document());prior_bytes=output_path.read_bytes()
        if mode=='tampered':output_path.write_bytes(png('red'))
        else:output_path.unlink()
        node._restore_saved_output(document(),records);await drain()
        assert node._hmb_prepare_phase=='error' and document()==before
        assert (output_path.read_bytes()==png('red')) if mode=='tampered' else not output_path.exists()
        output_path.write_bytes(prior_bytes)
        RESULT['existing_output_'+mode+'_rejects_without_rewrite']=True
    # The output driver lease is captured together with source leases. A
    # replacement while the pure worker is running cannot approve old output.
    entered.clear();release.clear();cold_reset();before=deepcopy(document());latest_bytes=output_path.read_bytes()
    lease=product.HMBImageBash._snapshot_driver_lease
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        with mock.patch.object(product.HMBImageBash,'_snapshot_driver_lease',side_effect=lambda paths:tuple((url,object()) for url,_ in lease(paths))):
            release.set();await drain()
    assert document()==before and node._hmb_prepare_phase=='error' and output_path.read_bytes()==latest_bytes
    RESULT['driver_lease_replacement_rejects_stale_restore']=True
    # Deletion invalidation is a controlled flag substitution, not a graph
    # Delete request (connected-node deletion protection is a separate suite).
    entered.clear();release.clear();cold_reset();before=deepcopy(document())
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        node._hmb_node_deleted=True;release.set();await drain()
    assert document()==before and node._hmb_cold_restore_pending is None and output_path.read_bytes()==latest_bytes
    node._hmb_node_deleted=False
    RESULT['deleted_flag_discards_without_scene_or_file_rewrite']=True
    # An actual private SDK wire removal invalidates an already running
    # result even while the records/scene themselves are unchanged.
    entered.clear();release.clear();cold_reset()
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        send(DeleteConnectionRequest(source_node_name=producer.name,source_parameter_name='IMAGE_BASH_CONTEXT_OUT',target_node_name=node.name,target_parameter_name='image_bash_context'))
        after_disconnect=deepcopy(document());release.set();await drain()
    assert document()==after_disconnect and node.parameter_output_values.get('output_image') is None and not ready()
    send(CreateConnectionRequest(source_node_name=producer.name,source_parameter_name='IMAGE_BASH_CONTEXT_OUT',target_node_name=node.name,target_parameter_name='image_bash_context',initial_setup=True))
    set_value('image_bash_context',context);node._sync_metadata_with_input_images();await drain();await valid('after-real-reconnect')
    output_path=Path(File(node.parameter_output_values['output_image'].value).resolve())
    RESULT['actual_connection_change_discards_and_reconnect_recovers']=True
    # A resolver/signing request can re-enter host hooks after the initial
    # CAS. Make the source unready at that exact boundary; no output publishes.
    cold_reset();real_resolve=File.resolve;reentered=[]
    def during_resolve(file):
        value=real_resolve(file)
        if threading.get_ident()==host and not reentered:
            reentered.append(True)
            set_value('image_bash_context',{**context,'ready':False,'preparation_phase':'preparing'})
        return value
    # The saved destination may be macro-shaped after an explicit Run.
    # Inject only inside publication, regardless of its path spelling.
    original_publish=node._publish_verified_saved_output
    def final_only(*args,**kwargs):
        with mock.patch.object(File,'resolve',during_resolve):return original_publish(*args,**kwargs)
    with mock.patch.object(node,'_publish_verified_saved_output',side_effect=final_only):
        node._restore_saved_output(document(),records);await drain()
    assert reentered and node.parameter_output_values.get('output_image') is None and not ready()
    assert node._hmb_prepare_phase=='preparing' and node._hmb_cold_restore_pending is None
    latest_bytes=output_path.read_bytes()
    RESULT['resolver_reentrancy_cannot_publish_or_override_new_preparing']=True
    # Delete the disconnected private node, then create a new instance with
    # its exact old name. The old result must not reach the replacement.
    set_value('image_bash_context',context);node._sync_metadata_with_input_images();await drain();await valid('before-private-recreate')
    output_path=Path(File(node.parameter_output_values['output_image'].value).resolve())
    latest_bytes=output_path.read_bytes();entered.clear();release.clear();cold_reset();old_name=node.name
    with mock.patch.object(product.HMBImageBash,'_snapshot_read',side_effect=gated):
        node._restore_saved_output(document(),records);await wait_entered()
        for output,target in (('IMAGE_BASH_IMAGES_OUT','input_images'),('IMAGE_BASH_CONTEXT_OUT','image_bash_context')):
            send(DeleteConnectionRequest(source_node_name=producer.name,source_parameter_name=output,target_node_name=old_name,target_parameter_name=target))
        flow_name=engine.node_manager.get_node_parent_flow_by_name(old_name)
        send(DeleteNodeRequest(node_name=old_name))
        recreated=send(CreateNodeRequest(node_type='HMBImageBash',specific_library_name='HMB_GP_Production',node_name=old_name,override_parent_flow_name=flow_name,initial_setup=True,create_error_proxy_on_failure=False))
        replacement=engine.node_manager.get_node_by_name(recreated.node_name)
        assert replacement is not node and replacement.name==old_name
        replacement_before=deepcopy(product._document(replacement.get_parameter_value('bash_image')))
        release.set();await drain()
    assert product._document(replacement.get_parameter_value('bash_image'))==replacement_before
    assert replacement.parameter_output_values.get('output_image') is None and output_path.read_bytes()==latest_bytes
    RESULT['actual_delete_recreate_same_name_rejects_old_result']=True
    assert all(Path(path).read_bytes()==data for path,data in source_bytes.items())
    RESULT.update(status='PASS',product_path=product.__file__,product_sha256=hashlib.sha256(Path(product.__file__).read_bytes()).hexdigest(),
        synthetic_local_only=True,actual_desktop=False,actual_live_engine_requests=False,paid_calls=0,network_calls=0,
        caveat='Worker final fresh SHA plus host identity/scene/receipt/connection/driver CAS. External unnotified file changes after final worker read remain a sequential-snapshot window; no atomic file lock claimed.')
    RESULT['stock_image_bash_required']=False

if __name__=='__main__':
    previous=Path.cwd()
    with tempfile.TemporaryDirectory(prefix='cold-restore-worker-',dir=OUT,ignore_cleanup_errors=True) as temporary:
        directory=Path(temporary);keys=('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','GTN_ENGINE_CONFIG_DIR','GTN_ENGINE_DATA_DIR','GTN_ENGINE_STATE_DIR','GTN_CONFIG_WORKSPACE_DIRECTORY')
        env={key:str(directory/key) for key in keys}
        for value in env.values():Path(value).mkdir()
        env.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(fixture.STANDARD),HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(fixture.EDITOR))
        with mock.patch.dict(os.environ,env),mock.patch.object(socket,'create_connection',side_effect=fixture.deny):
            os.chdir(directory);logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:asyncio.run(fixture.exercise(engine,directory,extension=check))
            finally:os.chdir(previous);logging.shutdown()
    (OUT/'COLD-RESTORE-WORKER-HOST-RESULT.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(RESULT,ensure_ascii=False))
