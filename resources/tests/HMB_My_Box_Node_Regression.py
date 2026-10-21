"""Actual isolated SDK: private Only lifecycle over mocked lowest Broker I/O.

Native node construction, parameter validation, immutable requests, atomic local
files and serialize/delete/reopen are real. Provider, auth and HTTP are fixture
boundaries; this script must never connect to an open editor or real Broker.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from email.message import Message
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import HMBSeedanceGeneration as target
import _hmb_my_box as protocol
import _hmb_my_box_node as controller_module
from griptape.artifacts import VideoUrlArtifact
from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
from griptape_nodes.retained_mode.engine import engine_scope
from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest, DeleteNodeRequest, DeserializeNodeFromCommandsRequest, SerializeNodeToCommandsRequest,
)
from griptape_nodes.serialization.values import decode_value

BASE = 'https://broker.invalid/GripTapeServer'
WID = 'mbx_' + '1' * 32
SELECTION = dict(schema=protocol.SELECTION_SCHEMA, version=1, selection_source='only_my_box',
    scope=protocol.SCOPE, workspace_id=WID, explicit_selection=True)
WORKSPACE = dict(workspace_id=WID, scope=protocol.SCOPE, selection=SELECTION, created_at=1)
CAPABILITIES = dict(schema=protocol.CAPABILITIES_SCHEMA, version=1, implemented=True, enabled=True,
    generation_enabled=True, workspace_management_enabled=True, reason_code=None,
    budget_limits_supported=False, project_source_reuse_enabled=False,
    selection_schema=protocol.SELECTION_SCHEMA, selection_source='only_my_box', scope=protocol.SCOPE,
    publish_to_reviews=False, image_results_included=False, generation_modes=['only'],
    output_media_types=['video'], generation_endpoint='/api/v1/generate/video', workspace=WORKSPACE,
    automatic_deletion_enabled=False, management_deadline_disables_media=False, default_management_days=30)
FINAL_CONTRACT=dict(schema='hmb-only-my-box-draft-final-v1',version=1,detail_field='draft_final',
    projection_scope='preview_source_detail_only',final_child_detail_state='not_draft',eligibility_scope='source_only',
    requires_generation_enabled=True,existing_child_has_precedence=True,resubmit_allowed=False,
    expiry_basis='source_creation_provider_limit',source_ttl_seconds=7*86400,
    final_client_request_id_required=False,client_key_namespace_conflicts_rejected=True,
    states=['available','reserved','running','completed','expired','not_draft'],
    final_client_request_id_rule='mbx-final-v1-{source_task_hex32}')
# Container fixture only. Decoder seam is mocked explicitly; no claim of codec
# or visual quality is derived from these bytes. Atomic storage is unmocked.
MOV = (b'\x00\x00\x00\x18ftypqt  \x00\x00\x00\x00qt  isom'
       b'\x00\x00\x00\x10moov\x00\x00\x00\x08mvhd'
       + (len(b'original-my-box-bytes')+8).to_bytes(4,'big') + b'mdatoriginal-my-box-bytes')
assert target._video_container_matches_format(MOV,'mov'), 'The fixture must pass the real MOV container parser'
MP4=MOV.replace(b'qt  ',b'mp42')
assert target._video_container_matches_format(MP4,'mp4'), 'The fixture must pass the real MP4 container parser'
FORBIDDEN_PROJECT_FIELDS = {'project_id','project_name','hmb_shot','user_id','owner_id',
    'project_selection','hmb_project_selection','shot_id','shot_name','generation_origin'}

def forbidden(*args, **kwargs):
    raise AssertionError('Live HTTP, provider, account secrets or public workflow side effects are forbidden')

original_connect = socket.socket.connect
def local_connect(sock, address):
    if isinstance(address, tuple) and address[0] in {'127.0.0.1','::1','localhost'}:
        return original_connect(sock, address)
    return forbidden()

class VideoResponse(io.BytesIO):
    def __init__(self, url, raw=MOV):
        super().__init__(raw); self.url=url; self.status=200; self.headers=Message()
        self.headers['Content-Type']='video/quicktime' if raw==MOV else 'video/mp4'
        self.headers['Content-Length']=str(len(raw))
        self.headers['ETag']='"'+hashlib.sha256(raw).hexdigest()+'"'
    def geturl(self): return self.url

class Backend:
    def __init__(self):
        self.server_url=BASE; self.calls=[]; self.created=[]; self.downloads=[]; self.jobs={}
        self.capabilities=deepcopy(CAPABILITIES); self.workspace=deepcopy(WORKSPACE)
        self.create_error=None; self.capability_error=None; self.refresh_error=None; self.status='completed'
        self.block_stage=''; self.started=threading.Event(); self.release=threading.Event()
        self.after_download=None; self.before_create=None; self.features=[]
        self.bridge=self.Bridge(self)
    def wait(self, stage):
        if self.block_stage==stage:
            self.started.set()
            if not self.release.wait(8): raise AssertionError('Fixture blocked '+stage+' was not released')
    def job(self, payload, number):
        tid='job-mybox-'+f'{number:032x}'
        url=self.server_url+protocol.API+'/items/'+tid+'/media?download=1'
        job=dict(schema=protocol.JOB_SCHEMA,version=1,task_id=tid,job_id=tid,workspace_id=WID,
            scope=protocol.SCOPE,publish_to_reviews=False,generation_mode='only',resubmit_allowed=False,
            client_request_id=payload['client_request_id'],provider=payload['provider'],model=payload['model'],
            task=payload.get('hmb_generation_task',target.TASK_TEXT_ONLY),
            output_format=payload.get('output_format','mov'),
            status=self.status,download_url=url if self.status=='completed' else None,
            video_url=url if self.status=='completed' else None,created_at=1)
        if self.capabilities.get('draft_final_detail_supported') and payload.get('draft'):
            job['draft_final']=self.projection(tid)
        if payload.get('draft_job_id'):
            job['draft_parent_task_id']=payload['draft_job_id']
        return job
    def projection(self, source, state='available', child=None, child_status=None):
        return dict(schema='hmb-only-my-box-draft-final-v1',version=1,state=state,eligible=state=='available',
            source_task_id=source,child_task_id=child,child_status=child_status,
            expires_at=None if state=='not_draft' else 9999999999,expiry_basis='source_creation_provider_limit',
            workspace_id=WID,selection=deepcopy(SELECTION),final_client_request_id='mbx-final-v1-'+source.removeprefix('job-mybox-'),
            eligibility_scope='source_only',resubmit_allowed=False,reason_code=None if state=='available' else 'my_box_draft_final_'+state)
    def enable_final(self):
        self.capabilities.update(draft_final_detail_supported=True,draft_final_contract=deepcopy(FINAL_CONTRACT))
    class Bridge:
        def __init__(self, backend): self.backend=backend; self.server_url=backend.server_url; self._opener=self
        def _load_access_token(self): return 'OFFLINE_FIXTURE_TOKEN'
        def require_seedance_features(self, **kwargs):
            self.backend.features.append(('normal',deepcopy(kwargs))); return kwargs['output_format']
        def require_seedance_draft_features(self, **kwargs):
            self.backend.features.append(('draft',deepcopy(kwargs))); return kwargs['output_format']
        def _request_json(self, method, path, **kwargs):
            b=self.backend; b.calls.append((method,path,deepcopy(kwargs)))
            if path.endswith('/capabilities'):
                b.wait('capabilities')
                if b.capability_error: raise b.capability_error
                return deepcopy(b.capabilities)
            if path.endswith('/workspace'):
                if method=='POST':
                    assert kwargs['payload']=={'explicit_selection':True}
                    b.workspace=deepcopy(WORKSPACE)
                return dict(schema=protocol.WORKSPACE_SCHEMA,version=1,workspace=deepcopy(b.workspace),created=method=='POST')
            if path=='/api/v1/generate/video':
                payload=deepcopy(kwargs['payload'])
                assert kwargs['submission'] is True and kwargs['idempotency_key']==payload['client_request_id']
                b.created.append(payload)
                job=b.job(payload,len(b.created)); b.jobs[job['task_id']]=job
                if b.before_create: b.before_create(payload)
                b.wait('create')
                if b.create_error: raise b.create_error
                return deepcopy(job)
            if path.endswith('/source-reference'):
                return dict(schema='hmb-only-my-box-source-reference-v1',version=1,scope=protocol.SCOPE,
                    target_client_request_id=kwargs['payload']['target_client_request_id'],expires_at=9999999999,
                    url=b.server_url+protocol.API+'/provider-source/'+'A'*43)
            identifier=path.removesuffix('/refresh').rsplit('/',1)[-1]
            if path.endswith('/refresh') and b.refresh_error: raise b.refresh_error
            matches=[job for key,job in b.jobs.items() if key==identifier or job['client_request_id']==identifier]
            if len(matches)!=1: raise AssertionError('Unmatched private Task lookup: '+identifier)
            return deepcopy(matches[0])
        def open(self, request, timeout):
            b=self.backend; b.downloads.append(request.full_url); b.wait('download')
            matched=[job for job in b.jobs.values() if job.get('download_url')==request.full_url]
            raw=MP4 if matched and matched[0].get('output_format')=='mp4' else MOV
            result=VideoResponse(request.full_url,raw)
            if b.after_download: b.after_download()
            return result
    def posts(self, suffix): return [row for row in self.calls if row[0]=='POST' and row[1].endswith(suffix)]

class MyBoxNodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='hmb-my-box-native-sdk-')
        self.addCleanup(self.temporary.cleanup); self.folder=Path(self.temporary.name); self.origin=BASE
        environment={name:str(self.folder/name) for name in ('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME',
            'XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME')}
        self.patches=[mock.patch.dict(os.environ,environment),
            mock.patch.object(socket,'create_connection',forbidden),
            mock.patch.object(socket.socket,'connect',local_connect),
            mock.patch.object(urllib.request,'urlopen',forbidden),
            mock.patch.object(urllib.request.OpenerDirector,'open',forbidden),
            mock.patch.object(target,'_broker_load_token',forbidden),
            mock.patch.object(target._broker_config,'load_broker_base_url',side_effect=lambda:self.origin),
            mock.patch.object(target,'_validate_decodable_mp4_file',side_effect=self.verify_staged_bytes)]
        for patch in self.patches: patch.start(); self.addCleanup(patch.stop)
        logging.disable(logging.CRITICAL); self.addCleanup(logging.shutdown)
        scope=engine_scope(); self.engine=scope.__enter__(); self.addCleanup(scope.__exit__,None,None,None)
        self.engine.event_manager.initialize_queue()
        result=self.engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name='PrivateOnlyOffline'))
        self.assertTrue(result.succeeded(),str(result.result_details))
        self.flow=self.engine.flow_manager.get_flow_by_name(result.flow_name)
        self.schema=LibrarySchema.model_validate_json((ROOT/'griptape-nodes-library.json').read_text('utf-8-sig'))
        self.library=LibraryRegistry.generate_new_library(self.schema)
        self.addCleanup(LibraryRegistry.unregister_library,self.schema.name,event_manager=self.engine.event_manager)
        definition=next(row for row in self.schema.nodes if row.class_name=='HMBSeedanceGeneration')
        self.library.register_lazy_node_type(definition.class_name,definition.metadata,lambda:target.HMBSeedanceGeneration)
        self.backend=Backend(); self.decode_checks=[]; self.node=self.create('Private Only')
    def verify_staged_bytes(self, path, verifier=None):
        raw=Path(path).read_bytes(); self.assertIn(raw,(MOV,MP4)); self.decode_checks.append(str(path))
    def send(self, request):
        request.broadcast_result=False; result=self.engine.handle_request(request)
        self.assertTrue(result.succeeded(),str(result.result_details)); return result
    def configure(self, node):
        node._ensure_broker_connected=mock.AsyncMock(return_value=self.backend.bridge)
        node._hmb_my_box_broker_factory=protocol.MyBoxBroker
        node._hmb_my_box_journal_root=self.folder/'private-journal'
        node._output_file.build_file=lambda:target._SeedanceDraftOutputDestination(str(self.folder/'original.mov'))
        node.publish_update_to_parameter=mock.Mock()
        for name in ('_prepare_managed_agent_shot','_process_generation','_capture_imageasset_project_selection'):
            setattr(node,name,mock.AsyncMock(side_effect=forbidden) if name.startswith('_prepare') or name=='_process_generation' else mock.Mock(side_effect=forbidden))
        return node
    def create(self, name, mode='only'):
        intent=dict(schema=target.SEEDANCE_EXECUTION_MODE_SCHEMA,version=1,mode=mode,revision=1)
        result=self.send(CreateNodeRequest(node_type='HMBSeedanceGeneration',specific_library_name=self.schema.name,
            node_name=name,metadata={target.SEEDANCE_EXECUTION_MODE_METADATA:intent},create_error_proxy_on_failure=False))
        node=self.configure(self.engine.node_manager.get_node_by_name(result.node_name))
        values=dict(model_id=target.MODEL_NAME_SEEDANCE_2_5,task=target.TASK_TEXT_ONLY,
            prompt='Private exact {literal} 0 OFF 한국어',resolution='480p',duration=4,output_format='mov',
            generate_audio=False,draft_action=target.DRAFT_ACTION_PREVIEW,only_project=protocol.MY_BOX_LABEL,
            output_file=str(self.folder/'original.mov'))
        # Author through the real editor callback path. initial_setup=True
        # deliberately skips metadata refresh and cannot model a user opening
        # the Draft dropdown after changing constructor 1080p to 480p.
        for key,value in values.items(): node.set_parameter_value(key,value)
        return node
    def controller(self, node=None): return (node or self.node)._hmb_my_box_controller()
    def run_node(self, node=None, **kwargs): return asyncio.run(self.controller(node).run(**kwargs))
    def checkpoint(self, node=None): return self.controller(node).checkpoint()
    def authored(self, node=None):
        node=node or self.node
        return {key:deepcopy(node.get_parameter_value(key)) for key in ('model_id','task','prompt','resolution',
            'duration','output_format','generate_audio','draft_action','only_project','output_file')}
    def assert_success(self, node=None, *, expected=MOV):
        node=node or self.node; artifact=node.parameter_output_values.get('VIDEO_OUT')
        self.assertIsInstance(artifact,VideoUrlArtifact,node.parameter_output_values.get('result_details'))
        self.assertEqual(Path(artifact.value).read_bytes(),expected)
        self.assertTrue(node._execution_succeeded,node.parameter_output_values.get('result_details'))
        self.assertTrue(node.parameter_output_values.get('video_url'))
        return Path(artifact.value)
    def reopen(self, node=None):
        node=node or self.node; pool={}
        serialized=self.send(SerializeNodeToCommandsRequest(node_name=node.name,
            unique_parameter_uuid_to_values=pool,serialize_all_parameter_values=True))
        name=node.name; self.send(DeleteNodeRequest(node_name=name))
        commands=deepcopy(serialized.serialized_node_commands); commands.create_node_command.node_name=name
        commands.create_node_command.override_parent_flow_name=self.flow.name
        result=self.send(DeserializeNodeFromCommandsRequest(serialized_node_commands=commands))
        reopened=self.configure(self.engine.node_manager.get_node_by_name(result.node_name))
        for indirect in serialized.set_parameter_value_commands:
            request=deepcopy(indirect.set_parameter_value_command); request.node_name=reopened.name
            request.value=decode_value(deepcopy(pool[indirect.unique_value_uuid])); request.initial_setup=True
            self.send(request)
        return reopened
    def test_constructor_and_selection_are_offline_and_scope_is_exact(self):
        self.assertTrue(controller_module.is_selected(self.node)); self.assertFalse(self.backend.calls)
        self.assertFalse(self.backend.created); self.node._ensure_broker_connected.assert_not_awaited()
        for selected in ('Select Project','슈퍼윙즈12','까투리8','my box',' My Box '):
            self.node.set_parameter_value('only_project',selected,initial_setup=True)
            self.assertFalse(controller_module.is_selected(self.node),selected)
        self.assertFalse(self.backend.calls)
    def test_preflight_has_no_auth_workspace_upload_or_post(self):
        before=self.authored(); self.controller().preflight()
        self.assertEqual(self.authored(),before); self.assertFalse(self.backend.calls)
        self.node._ensure_broker_connected.assert_not_awaited()
    def test_native_run_dispatches_private_only_without_agent_or_public_renderer(self):
        asyncio.run(self.node._aprocess_impl()); self.assert_success()
        self.node._prepare_managed_agent_shot.assert_not_awaited()
        self.node._process_generation.assert_not_awaited()
        self.node._capture_imageasset_project_selection.assert_not_called()
    def test_waiting_shot_or_regular_project_never_enters_private_controller(self):
        controller=self.controller()
        for mode, selected in [('waiting',protocol.MY_BOX_LABEL),('shot',protocol.MY_BOX_LABEL),('only','까투리8')]:
            with self.subTest(mode=mode,selected=selected):
                self.node.set_parameter_value('only_project',selected,initial_setup=True)
                with mock.patch.object(self.node,'_hmb_seedance_execution_mode',return_value=mode):
                    self.assertFalse(controller_module.is_selected(self.node))
                    asyncio.run(controller.run())
                    self.assertFalse(self.backend.calls); self.assertFalse(self.backend.created)
    def test_regular_project_native_dispatch_still_uses_existing_public_path(self):
        self.node.set_parameter_value('only_project','까투리8',initial_setup=True)
        private=mock.AsyncMock(side_effect=AssertionError('Public project entered My Box'))
        with mock.patch.object(self.controller(),'run',private), \
             mock.patch.object(self.node,'_validate_local_render_preflight'), \
             mock.patch.object(self.node,'_prepare_managed_agent_shot',new_callable=mock.AsyncMock) as prepare, \
             mock.patch.object(self.node,'_assert_agent_result_available'), \
             mock.patch.object(self.node,'_process_generation',new_callable=mock.AsyncMock) as process:
            asyncio.run(self.node._aprocess_impl())
        private.assert_not_awaited(); prepare.assert_awaited_once(); process.assert_awaited_once()
        self.assertFalse(self.backend.calls)
    def test_explicit_workspace_creation_and_private_frozen_request(self):
        self.backend.workspace=None; self.backend.capabilities['workspace']=None
        before=self.authored(); self.run_node(); self.assert_success()
        self.assertEqual(self.authored(),before); self.assertEqual(len(self.backend.created),1)
        creates=self.backend.posts('/workspace'); self.assertEqual(len(creates),1)
        self.assertEqual(creates[0][2]['payload'],{'explicit_selection':True})
        methods=[m for m,p,k in self.backend.calls if p.endswith('/workspace')]
        self.assertEqual(methods,['GET','POST'])
        payload=self.backend.created[0]; self.assertEqual(payload['hmb_generation_mode'],'only')
        self.assertEqual(payload['my_box_selection'],SELECTION)
        self.assertFalse(FORBIDDEN_PROJECT_FIELDS & set(payload)); self.assertNotIn('title',payload)
        self.assertEqual(payload['prompt'],before['prompt']); self.assertIs(payload['generate_audio'],False)
        self.node._prepare_managed_agent_shot.assert_not_awaited(); self.node._process_generation.assert_not_awaited()
        self.node._capture_imageasset_project_selection.assert_not_called()
    def test_existing_workspace_is_read_only_get(self):
        self.run_node(); self.assert_success()
        self.assertFalse(self.backend.posts('/workspace'))
        self.assertTrue(any(m=='GET' and p.endswith('/workspace') for m,p,k in self.backend.calls))
    def test_unsupported_capability_cannot_create_or_make_workspace(self):
        self.backend.capability_error=protocol.MyBoxError('fixture unsupported',code='MY_BOX_UNSUPPORTED',status_code=404)
        self.run_node(); self.assertFalse(self.backend.created); self.assertFalse(self.backend.posts('/workspace'))
        self.assertFalse(self.node._execution_succeeded)
    def test_unapproved_or_disconnected_account_cannot_create(self):
        self.node._ensure_broker_connected.side_effect=PermissionError('offline auth fixture denied')
        self.run_node(); self.assertFalse(self.backend.calls); self.assertFalse(self.backend.created)
        self.assertFalse(self.node._execution_succeeded)
    def test_budget_not_supported_reason_cannot_be_bypassed(self):
        self.backend.capabilities.update(generation_enabled=False,reason_code='my_box_budget_limits_unsupported')
        self.run_node(); self.assertFalse(self.backend.created); self.assertFalse(self.node._execution_succeeded)
    def test_repeated_480_runs_keep_all_authored_settings_and_old_files(self):
        before=self.authored(); paths=[]
        for _ in range(4):
            self.run_node(); paths.append(self.assert_success()); self.assertEqual(self.authored(),before)
        self.assertEqual(len({p.resolve() for p in paths}),4)
        self.assertEqual(len({p['client_request_id'] for p in self.backend.created}),4)
        self.assertTrue(all(p.read_bytes()==MOV for p in paths))
        self.assertTrue(all(row['resolution']=='480p' and row['draft'] is True for row in self.backend.created))
    def test_native_output_component_preserves_named_folder_and_basename_mov_mp4(self):
        for output_format, expected in (('mov', MOV), ('mp4', MP4)):
            with self.subTest(output_format=output_format):
                node=self.create('Named local output '+output_format)
                # Restore the actual installed SDK component instead of the
                # generic build_file fixture used by the other lifecycle tests.
                del node._output_file.build_file
                base=self.folder/'사용자 이름'/'기존 영상 위치'/('원본 작업.'+output_format)
                node.set_parameter_value('output_file',str(base))
                node.set_parameter_value('output_format',output_format)
                resolved=Path(node._build_generation_output_destination(draft=True).resolve())
                self.assertEqual(resolved,base)
                with mock.patch.object(node._output_file,'build_file',wraps=node._output_file.build_file) as build:
                    self.run_node(node)
                saved=self.assert_success(node,expected=expected)
                self.assertEqual(saved.parent,base.parent)
                self.assertEqual(saved.name,base.stem+'-mybox-'+self.checkpoint(node)['client_request_id']+'.'+output_format)
                build.assert_called_once_with(_index=1)
                self.assertEqual(node.get_parameter_value('output_file'),str(base))
    def test_native_output_component_reuses_situation_and_node_name(self):
        from griptape_nodes.files.project_file import ProjectFileDestination
        node=self.node; del node._output_file.build_file
        node.set_parameter_value('output_file','사용자 기본 이름.mov')
        base=self.folder/'기존 이름별 저장'/node.name/'사용자 기본 이름.mov'
        # Only project-template resolution is a fixture; the SDK component's
        # filename, situation, node_name and _index propagation are real.
        with mock.patch.object(ProjectFileDestination,'from_situation',
                return_value=target._SeedanceDraftOutputDestination(str(base))) as situation:
            self.run_node(node)
        saved=self.assert_success()
        self.assertEqual(saved.parent,base.parent)
        situation.assert_called_once_with('사용자 기본 이름.mov',node._output_file._situation_name,node_name=node.name,_index=1)
        self.assertEqual(node._output_file._situation_name,'save_node_output')
    def test_native_upstream_output_path_wins_without_overwriting_existing_file(self):
        node=self.node; del node._output_file.build_file
        base=self.folder/'연결된 출력 설정'/'기존 이름.mov'
        base.parent.mkdir(parents=True); base.write_bytes(b'existing-user-video')
        upstream=target._SeedanceDraftOutputDestination(str(base))
        # The connected provider boundary is synthetic, while the SDK's
        # upstream precedence and actual atomic no-overwrite storage are real.
        with mock.patch.object(node._output_file,'_get_upstream_destination',return_value=upstream) as provider:
            self.assertIs(node._build_generation_output_destination(draft=True),upstream)
            self.run_node()
        saved=self.assert_success()
        self.assertTrue(provider.called)
        self.assertEqual(saved.parent,base.parent)
        self.assertTrue(saved.stem.startswith(base.stem+'-mybox-'))
        self.assertEqual(base.read_bytes(),b'existing-user-video')
    def test_named_folder_draft_final_rerender_and_reopen_keep_frozen_paths(self):
        node=self.node; del node._output_file.build_file
        base=self.folder/'사용자 기존 위치'/'작업 이름.mov'
        node.set_parameter_value('output_file',str(base)); self.backend.enable_final()
        self.run_node(); draft=self.assert_success()
        self.run_node(final=True); final=self.assert_success()
        self.run_node(); rerender=self.assert_success()
        self.assertEqual(len({draft,final,rerender}),3)
        self.assertTrue(all(path.parent==base.parent and path.stem.startswith(base.stem+'-mybox-') for path in (draft,final,rerender)))
        self.assertTrue(all(path.read_bytes()==MOV for path in (draft,final,rerender)))
        saved_checkpoint=deepcopy(self.checkpoint()); count=len(self.backend.created)
        node.set_parameter_value('output_file',str(self.folder/'다음 작업 위치'/'다음 작업.mov'))
        reopened=self.reopen()
        self.run_node(reopened,refresh=True)
        self.assertEqual(self.assert_success(reopened),rerender)
        self.assertEqual(self.checkpoint(reopened)['output_file'],saved_checkpoint['output_file'])
        self.assertEqual(self.checkpoint(reopened)['job_id'],saved_checkpoint['job_id'])
        self.assertEqual(len(self.backend.created),count)
        self.assertFalse((self.folder/'다음 작업 위치').exists())
    def test_unknown_create_uses_same_request_refresh_without_repost(self):
        self.backend.create_error=protocol.MyBoxError('offline lost create response',submission_outcome_unknown=True)
        self.run_node(); checkpoint=self.checkpoint(); self.assertEqual(len(self.backend.created),1)
        request=self.backend.created[0]['client_request_id']
        self.assertIn(request,json.dumps(checkpoint)); self.assertFalse(self.node._execution_succeeded)
        self.backend.create_error=None; self.run_node(); self.assert_success()
        self.assertEqual(len(self.backend.created),1)
        self.assertTrue(any(p=='/api/v1/jobs/'+request+'/refresh' for m,p,k in self.backend.calls))
    def test_unknown_request_lookup_failures_never_authorize_a_new_create_or_key(self):
        for failure in ('404','503','timeout'):
            with self.subTest(failure=failure):
                node=self.create('Unknown lookup '+failure); count=len(self.backend.created)
                self.backend.create_error=protocol.MyBoxError('offline response lost',submission_outcome_unknown=True)
                self.run_node(node); self.assertEqual(len(self.backend.created),count+1)
                request=self.backend.created[-1]['client_request_id']; self.backend.create_error=None
                if failure=='timeout':error=TimeoutError('offline lookup timeout')
                else:
                    error=RuntimeError('offline lookup rejected'); error.status_code=int(failure)
                self.backend.refresh_error=error
                for _ in range(2):
                    self.run_node(node)
                    self.assertEqual(len(self.backend.created),count+1)
                    checkpoint=self.checkpoint(node)
                    self.assertEqual(checkpoint['client_request_id'],request)
                    self.assertNotEqual(checkpoint['stage'],'not_submitted')
                    self.assertTrue(any(p=='/api/v1/jobs/'+request+'/refresh' for m,p,k in self.backend.calls))
                self.backend.refresh_error=None; self.run_node(node); self.assert_success(node)
                self.assertEqual(len(self.backend.created),count+1)
                self.assertEqual(self.checkpoint(node)['client_request_id'],request)
    def test_required_durable_journal_failure_blocks_billable_submission(self):
        with mock.patch.object(controller_module,'_write_journal',side_effect=OSError('offline unavailable journal')):
            self.run_node()
        self.assertFalse(self.backend.created); self.assertFalse(self.node._execution_succeeded)
        self.assertNotIn('VIDEO_OUT',self.node.parameter_output_values)

    def enable_queue(self):
        import _hmb_queue_admission as queue
        raw=json.loads((ROOT/'resources/tests/HMB_Maintenance_Queue_Fixture.json').read_text('utf-8'))
        raw['only_syntax']=deepcopy(self.backend.capabilities)
        raw['only_syntax'].update(enabled=False,generation_enabled=False,reason_code='maintenance_queue_only')
        raw['workspace_intent']=None
        admission=queue.parse(raw)
        self.backend.bridge.queue_admission=lambda **kwargs:admission
        def bound(candidate,operation):
            self.assertIs(candidate,admission); candidate.require(operation); return candidate.headers
        self.backend.bridge._queue_admission_headers=bound
        return admission

    def test_queue_only_pending_reopen_keeps_headers_and_same_task_without_create(self):
        admission=self.enable_queue()
        self.backend.create_error=protocol.MyBoxError('Synthetic accepted response loss',submission_outcome_unknown=True)
        self.run_node(); cp=self.checkpoint()
        self.assertEqual(len(self.backend.created),1)
        self.assertEqual(cp['queue_only_headers'],admission.headers)
        self.node=self.reopen(); self.assertEqual(self.checkpoint()['queue_only_headers'],admission.headers)
        self.backend.create_error=None
        self.run_node(refresh=True); self.assert_success()
        self.assertEqual(len(self.backend.created),1)
        self.assertEqual(self.checkpoint()['queue_only_headers'],admission.headers)
        self.assertFalse(self.backend.posts('/workspace'))

    def test_queue_private_editing_uses_owner_get_and_typed_source_no_grant(self):
        self.run_node(); source=self.checkpoint()['job_id']
        admission=self.enable_queue()
        self.node.set_parameter_value('task',target.TASK_VIDEO_EDITING)
        self.node.set_parameter_value(controller_module.SOURCE_PARAMETER,source)
        self.node.set_parameter_value('draft_action',target.DRAFT_ACTION_OFF)
        self.run_node(); self.assert_success()
        self.assertEqual(len(self.backend.created),2,self.node.parameter_output_values.get('result_details'))
        self.assertEqual(self.backend.created[-1]['video_urls'],['hmb-queue-only-source://'+source])
        self.assertEqual(self.backend.created[-1].get('omni_reference_task_type'),'edit')
        self.assertEqual(self.backend.created[-1]['duration_seconds'],-1)
        self.assertEqual(self.backend.created[-1]['aspect_ratio'],'adaptive')
        self.assertFalse(self.backend.posts('/source-reference'))
        self.assertTrue(any(m=='GET' and p==protocol.API+'/items/'+source for m,p,k in self.backend.calls))
        self.assertEqual(self.checkpoint()['queue_only_headers'],admission.headers)

    def test_queue_private_final_preserves_authored480_and_fresh_source(self):
        self.backend.enable_final(); self.run_node(); source=self.checkpoint()['job_id']
        admission=self.enable_queue(); original=self.authored()
        self.run_node(final=True); self.assert_success()
        self.assertEqual(len(self.backend.created),2,self.node.parameter_output_values.get('result_details'))
        self.assertEqual(self.backend.created[-1]['draft_job_id'],source)
        self.assertEqual(self.backend.created[-1]['resolution'],'1080p')
        self.assertEqual(self.authored(),original)
        self.assertEqual(self.checkpoint()['queue_only_headers'],admission.headers)

    def test_local_queue_rejection_is_not_unknown_and_never_submits(self):
        import _hmb_queue_admission as queue
        self.enable_queue()
        with mock.patch.object(protocol.MyBoxBroker,'create',side_effect=queue.QueueAdmissionError('Synthetic stale local admission')):
            self.run_node()
        self.assertFalse(self.backend.created)
        self.assertEqual(self.checkpoint()['stage'],'not_submitted')
        self.assertEqual(self.checkpoint()['status'],'not_submitted')

    def test_private_payload_keeps_native_subtask_for_all_models_and_tasks(self):
        before=self.authored()
        for model,tasks in target.MODEL_TASK_CHOICES.items():
            for task in tasks:
                with self.subTest(model=model,task=task):
                    params=self.node._get_parameters()
                    params.update(model_id=model,task=task,output_format='mov' if model==target.SEEDANCE_2_5_MODEL_ID else 'mp4',
                        _private_source_id='',video_reference_slots=[],video_references=['https://93.184.216.34/synthetic-fixture-only/source.mp4']
                            if task in (target.TASK_REFERENCE_TO_VIDEO,target.TASK_VIDEO_EDITING,target.TASK_VIDEO_EXTENSION) else [],
                        reference_images=[],reference_audio=[],first_frame=None,last_frame=None)
                    frozen=deepcopy(params)
                    controller=self.controller()
                    payload=asyncio.run(controller._payload(params,protocol.MyBoxBroker(self.backend.bridge),SELECTION,
                        'synthetic-task-map',epoch=controller._epoch,origin=BASE))
                    expected=target.TASK_OMNI_REFERENCE_TYPES.get(task) if model==target.SEEDANCE_2_5_MODEL_ID else None
                    self.assertEqual(payload.get('omni_reference_task_type'),expected)
                    self.assertEqual(payload['hmb_generation_task'],task)
                    self.assertEqual(params,frozen)
        self.assertEqual(self.authored(),before)
    def test_save_failure_recovers_accepted_task_without_another_create(self):
        with mock.patch.object(self.node,'_atomic_publish_completed_video',new_callable=mock.AsyncMock,
                side_effect=OSError('offline output folder unavailable')):
            self.run_node()
        self.assertEqual(len(self.backend.created),1); cp=self.checkpoint()
        self.assertTrue(cp.get('job_id')); self.assertFalse(self.node._execution_succeeded)
        self.run_node(); self.assert_success(); self.assertEqual(len(self.backend.created),1)
        self.assertEqual(self.checkpoint()['job_id'],cp['job_id'])
    def test_original_mov_bytes_publish_atomically_and_preview_keeps_original(self):
        self.run_node(); path=self.assert_success()
        self.assertEqual(path.suffix,'.mov'); self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),hashlib.sha256(MOV).hexdigest())
        self.assertTrue(self.decode_checks); self.assertEqual(len(self.backend.downloads),1)
        preview=self.node.parameter_output_values['video_url']
        self.assertIsInstance(preview,VideoUrlArtifact)
        self.assertNotIn('/api/v1/only/my-box/',str(preview.value))
    def test_private_video_is_never_observable_with_stale_production_provenance(self):
        parameter=target.GENERATED_VIDEO_SOURCE_PARAMETER
        old=dict(schema='legacy-production-fixture',project_id='superwings12',shot_name='Old production Shot')
        self.node._hmb_generated_video_source=deepcopy(old)
        self.node.parameter_values[parameter]=deepcopy(old)
        self.node.parameter_output_values[parameter]=deepcopy(old)
        node=self.node; observations=[]
        class ObservedOutputs(dict):
            def __setitem__(self,key,value):
                if key=='VIDEO_OUT':
                    observations.append(dict(
                        internal=deepcopy(node._hmb_generated_video_source),
                        native_value=deepcopy(node.parameter_values.get(parameter)),
                        native_output=deepcopy(self.get(parameter))))
                return super().__setitem__(key,value)
        node.parameter_output_values=ObservedOutputs(node.parameter_output_values)
        self.run_node(); self.assert_success()
        self.assertTrue(observations,'The actual native VIDEO_OUT publication was not observed')
        self.assertTrue(all(row==dict(internal={},native_value={},native_output={}) for row in observations),observations)
    def test_private_output_cannot_be_reclassified_by_old_public_recovery_even_after_mode_switch(self):
        old_file=self.folder/'old-production.mov'; old_file.write_bytes(MOV)
        origin=dict(channel_uuid='11111111-1111-4111-8111-111111111111',
            shot_uuid='22222222-2222-4222-8222-222222222222',number=1,name='Preserved old production Shot',
            source_node_instance_id='33333333-3333-4333-8333-333333333333')
        old=target._seedance_recovery_value(dict(stage='local_succeeded',status='succeeded',terminal=True,
            task_id='job-'+'a'*32,task_identity='broker_task',generation_origin=origin,
            output_file=str(old_file),model_id=target.SEEDANCE_2_5_MODEL_ID,output_format='mov'))
        self.assertEqual(old['generation_origin'],origin)
        self.node.parameter_values[target.SEEDANCE_RECOVERY_PARAMETER]=deepcopy(old)
        self.run_node(); private=self.assert_success()
        self.assertEqual(self.node._hmb_generated_video_source_snapshot(),{})
        with mock.patch.object(self.node,'_hmb_seedance_execution_mode',return_value='shot'):
            self.assertEqual(self.node._hmb_generated_video_source_snapshot(),{})
            self.assertEqual(self.node._restore_completed_video_source_for_lut(),{})
            public=self.folder/'new-production.mov'; public.write_bytes(MOV)
            public_id='job-'+'b'*32
            public_artifact=VideoUrlArtifact(value=str(public),name=public.name)
            self.node.parameter_output_values['VIDEO_OUT']=public_artifact
            self.node.parameter_output_values['video_url']=self.node._native_local_video_preview_artifact(public_artifact)
            self.node.parameter_output_values['generation_id']=public_id
            self.assertTrue(self.node._record_completed_video_source(origin,public_id,target.File(str(public))))
            source=self.node._hmb_generated_video_source_snapshot()
            self.assertEqual(source['task_id'],public_id); self.assertEqual(Path(source['path']),public)
        self.assertEqual(private.read_bytes(),MOV); self.assertEqual(old_file.read_bytes(),MOV)
    def test_alias_only_private_hydration_never_restores_old_public_lut_authority(self):
        origin=dict(channel_uuid='11111111-1111-4111-8111-111111111111',
            shot_uuid='22222222-2222-4222-8222-222222222222',number=1,name='Old production',
            source_node_instance_id='33333333-3333-4333-8333-333333333333')
        self.node.parameter_values[target.SEEDANCE_RECOVERY_PARAMETER]=target._seedance_recovery_value(
            dict(stage='local_succeeded',status='succeeded',task_id='job-'+'a'*32,
                 task_identity='broker_task',generation_origin=origin))
        self.run_node(); private=self.assert_success()
        original=VideoUrlArtifact(value=str(private),name=private.name)
        native_alias=self.node._native_local_video_preview_artifact(original)
        self.node.parameter_output_values.pop('VIDEO_OUT',None)
        self.node.parameter_output_values['generation_id']=''
        for alias in (original,native_alias):
            with self.subTest(alias=str(alias.value)),mock.patch.object(self.node,'_hmb_seedance_execution_mode',return_value='shot'):
                self.node.parameter_output_values['video_url']=alias
                self.assertEqual(self.node._hmb_generated_video_source_snapshot(),{})
                self.assertEqual(self.node._restore_completed_video_source_for_lut(),{})
                self.assertEqual(self.node.parameter_values.get(target.GENERATED_VIDEO_SOURCE_PARAMETER),{})
    def test_native_output_hook_failure_cannot_reverse_committed_local_success(self):
        with mock.patch.object(self.controller(),'_publish_local',side_effect=RuntimeError('offline native UI unavailable')):
            self.run_node()
        cp=self.checkpoint(); self.assertEqual(cp['stage'],'local_succeeded')
        path=Path(cp['output_file']); self.assertEqual(path.read_bytes(),MOV)
        self.assertEqual(cp['saved_file_sha256'],hashlib.sha256(MOV).hexdigest())
        self.assertTrue(self.node._execution_succeeded,self.node.parameter_output_values.get('result_details'))
        self.run_node(refresh=True); self.assertEqual(self.assert_success(),path)
        self.assertEqual(len(self.backend.created),1); self.assertEqual(len(self.backend.downloads),1)
    def test_optional_success_status_hook_failure_cannot_relabel_saved_video_failed(self):
        setter=self.node._set_status_results
        def fail_after_commit(**kwargs):
            if self.checkpoint().get('stage')=='local_succeeded':
                raise RuntimeError('offline status UI unavailable')
            return setter(**kwargs)
        with mock.patch.object(self.node,'_set_status_results',side_effect=fail_after_commit):
            self.run_node()
        cp=self.checkpoint(); self.assertEqual(cp['stage'],'local_succeeded')
        self.assertTrue(self.node._execution_succeeded,self.node.parameter_output_values.get('result_details'))
        self.assertIs(self.node.parameter_output_values.get('was_successful'),True)
        self.assertEqual(self.node.parameter_output_values.get('generation_status'),'succeeded')
        self.run_node(refresh=True); self.assert_success()
        self.assertEqual(len(self.backend.created),1); self.assertEqual(len(self.backend.downloads),1)
    def test_tracked_status_transport_exception_cannot_leave_committed_video_unsuccessful(self):
        node=self.node; armed=[]
        class FlakyOutputs(dict):
            def __setitem__(self,key,value):
                result=super().__setitem__(key,value)
                if key=='generation_id' and node.get_parameter_value(controller_module.CHECKPOINT_PARAMETER).get('stage')=='local_succeeded':
                    armed.append(key)
                    raise ConnectionResetError('offline status event transport reset after commit')
                return result
        node.parameter_output_values=FlakyOutputs(node.parameter_output_values)
        self.run_node(); cp=self.checkpoint()
        self.assertTrue(armed,'The post-commit tracked-output event failure was not exercised')
        self.assertEqual(cp['stage'],'local_succeeded'); self.assertEqual(Path(cp['output_file']).read_bytes(),MOV)
        self.assertTrue(node._execution_succeeded,node.parameter_output_values.get('result_details'))
        self.assertIs(node.parameter_output_values.get('was_successful'),True)
        self.assertEqual(len(self.backend.created),1)
    def test_native_save_reopen_keeps_checkpoint_original_output_and_same_task(self):
        self.run_node(); path=self.assert_success(); checkpoint=self.checkpoint(); before=self.authored()
        reopened=self.reopen(); self.assertEqual(self.authored(reopened),before)
        self.assertEqual(self.checkpoint(reopened),checkpoint)
        restored=reopened.parameter_output_values.get('VIDEO_OUT')
        self.assertIsInstance(restored,VideoUrlArtifact,'Native output did not survive command hydration')
        self.assertEqual(Path(restored.value),path)
        self.assertTrue(reopened.parameter_output_values.get('video_url'))
        self.assertEqual(path.read_bytes(),MOV)
        self.run_node(reopened,refresh=True); self.assertEqual(self.assert_success(reopened),path)
        self.assertEqual(len(self.backend.created),1); self.assertEqual(len(self.backend.downloads),1)
    def test_inputs_frozen_before_first_capability_wait(self):
        self.backend.block_stage='capabilities'; before=self.authored()
        async def exercise():
            task=asyncio.create_task(self.controller().run())
            try:
                self.assertTrue(await asyncio.to_thread(self.backend.started.wait,3))
                self.node.set_parameter_value('prompt','Next Run prompt')
                self.node.set_parameter_value('resolution','720p')
            finally:self.backend.release.set()
            await task
        asyncio.run(exercise()); self.assert_success()
        self.assertEqual(self.backend.created[0]['prompt'],before['prompt'])
        self.assertEqual(self.backend.created[0]['resolution'],before['resolution'])
        self.assertEqual(self.node.get_parameter_value('prompt'),'Next Run prompt')
    def blocked_stale(self, action, stage='create'):
        self.backend.block_stage=stage
        async def exercise():
            task=asyncio.create_task(self.controller().run())
            try:
                self.assertTrue(await asyncio.to_thread(self.backend.started.wait,3))
                action(task)
            finally:self.backend.release.set()
            try:await task
            except asyncio.CancelledError:pass
        asyncio.run(exercise())
        self.assertNotIn('VIDEO_OUT',self.node.parameter_output_values)
        self.assertFalse(self.node._execution_succeeded)
    def test_cancellation_during_create_preserves_identity_without_stale_publication(self):
        self.blocked_stale(lambda task:task.cancel())
        self.assertEqual(len(self.backend.created),1)
    def test_deleted_node_cannot_publish_accepted_result(self):
        self.blocked_stale(lambda task:self.send(DeleteNodeRequest(node_name=self.node.name)))
        self.assertEqual(len(self.backend.created),1)
    def test_broker_switch_during_create_cannot_publish_to_new_broker_context(self):
        self.blocked_stale(lambda task:setattr(self,'origin','https://other-broker.invalid'))
        self.assertEqual(len(self.backend.created),1)
    def test_mode_or_project_switch_before_create_stops_private_submission(self):
        self.blocked_stale(lambda task:self.node.set_parameter_value('only_project','까투리8'),stage='capabilities')
        self.assertFalse(self.backend.created)
    def cleanup_spies(self):
        return mock.patch.object(self.node,'_cleanup_temporary_video_uploads'), \
            mock.patch.object(self.node,'_defer_temporary_video_upload_cleanup')
    def test_pending_task_cancellation_defers_remote_reference_cleanup(self):
        self.backend.status='pending'
        immediate_patch,defer_patch=self.cleanup_spies()
        with immediate_patch as immediate,defer_patch as deferred:
            async def exercise():
                task=asyncio.create_task(self.controller().run())
                deadline=asyncio.get_running_loop().time()+3
                while not self.checkpoint().get('job_id'):
                    self.assertLess(asyncio.get_running_loop().time(),deadline)
                    await asyncio.sleep(0.01)
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
            asyncio.run(exercise())
        self.assertEqual(len(self.backend.created),1); self.assertTrue(self.checkpoint().get('job_id'))
        immediate.assert_not_called(); self.assertTrue(deferred.called,'Accepted remote Task references were not retained')
    def test_pending_task_timeout_defers_remote_reference_cleanup(self):
        self.backend.status='pending'; clock=iter([1,100000])
        private_clock=SimpleNamespace(monotonic=lambda:next(clock,100000),time=time.time)
        immediate_patch,defer_patch=self.cleanup_spies()
        with immediate_patch as immediate,defer_patch as deferred,mock.patch.object(controller_module,'time',private_clock):
            self.run_node()
        self.assertTrue(self.checkpoint().get('job_id')); self.assertFalse(self.node._execution_succeeded)
        immediate.assert_not_called(); self.assertTrue(deferred.called,'Timed-out remote Task references were not retained')
    def test_pending_refresh_transport_failure_defers_remote_reference_cleanup(self):
        self.backend.status='pending'; self.backend.refresh_error=TimeoutError('offline refresh unavailable')
        immediate_patch,defer_patch=self.cleanup_spies()
        original_asyncio=controller_module.asyncio
        # Replace only this module's sleep facade; native asyncio/network guard
        # and event-loop scheduling remain unchanged in the interpreter.
        fast_asyncio=SimpleNamespace(**{key:getattr(original_asyncio,key) for key in dir(original_asyncio) if not key.startswith('__')})
        fast_asyncio.sleep=mock.AsyncMock(return_value=None)
        with immediate_patch as immediate,defer_patch as deferred,mock.patch.object(controller_module,'asyncio',fast_asyncio):
            self.run_node()
        self.assertTrue(self.checkpoint().get('job_id')); self.assertFalse(self.node._execution_succeeded)
        immediate.assert_not_called(); self.assertTrue(deferred.called,'Unconfirmed remote Task references were not retained')
    def test_own_editing_and_extension_use_target_request_bound_source_grant(self):
        source='job-mybox-'+'a'*32
        source_payload=dict(provider='volcengine_ark',model=target.SEEDANCE_2_5_MODEL_ID,
            client_request_id='source-request',hmb_generation_task=target.TASK_TEXT_ONLY)
        self.backend.jobs[source]=dict(self.backend.job(source_payload,10),task_id=source,job_id=source)
        for task in (target.TASK_VIDEO_EDITING,target.TASK_VIDEO_EXTENSION):
            with self.subTest(task=task):
                self.node.set_parameter_value('task',task)
                self.node.set_parameter_value('draft_action',target.DRAFT_ACTION_OFF)
                self.node.set_parameter_value('resolution','720p')
                self.node.set_parameter_value(controller_module.SOURCE_PARAMETER,source)
                self.run_node(); self.assert_success()
                payload=self.backend.created[-1]
                self.assertEqual(payload.get('omni_reference_task_type'),target.TASK_OMNI_REFERENCE_TYPES[task])
                grants=self.backend.posts('/source-reference'); self.assertTrue(grants)
                self.assertEqual(grants[-1][2]['payload'],dict(target_client_request_id=payload['client_request_id'],task=task))
                self.assertIn(BASE+protocol.API+'/provider-source/'+'A'*43,payload['video_urls'])
                self.assertFalse(FORBIDDEN_PROJECT_FIELDS & set(payload))
    def test_foreign_workspace_source_cannot_issue_grant_or_create(self):
        source='job-mybox-'+'b'*32
        source_payload=dict(provider='volcengine_ark',model=target.SEEDANCE_2_5_MODEL_ID,
            client_request_id='source-request',hmb_generation_task=target.TASK_TEXT_ONLY)
        self.backend.jobs[source]=dict(self.backend.job(source_payload,11),task_id=source,job_id=source,
            workspace_id='mbx_'+'b'*32)
        self.node.set_parameter_value('task',target.TASK_VIDEO_EDITING)
        self.node.set_parameter_value(controller_module.SOURCE_PARAMETER,source)
        self.run_node(); self.assertFalse(self.backend.created); self.assertFalse(self.backend.posts('/source-reference'))
    def test_unsupported_final_projection_cannot_enable_or_submit_final(self):
        self.run_node(); self.assert_success(); before=self.authored()
        self.assertFalse(self.controller().draft_ui_state()['final_available'])
        self.run_node(final=True); self.assertEqual(len(self.backend.created),1)
        self.assertEqual(self.authored(),before)
    def test_available_final_submits_once_at_1080_preserving_480_settings_and_source(self):
        self.backend.enable_final(); before=self.authored(); self.run_node(); original=self.assert_success()
        source=self.checkpoint()['job_id']; self.assertTrue(self.controller().draft_ui_state()['final_available'])
        self.run_node(final=True); final=self.assert_success()
        self.assertNotEqual(final,original); self.assertEqual(original.read_bytes(),MOV)
        self.assertEqual(self.authored(),before); self.assertEqual(len(self.backend.created),2)
        payload=self.backend.created[1]; self.assertEqual(payload['draft_job_id'],source)
        self.assertEqual(payload['client_request_id'],'mbx-final-v1-'+source.removeprefix('job-mybox-'))
        self.assertEqual(payload['resolution'],'1080p'); self.assertNotIn('draft',payload)
        self.assertFalse(FORBIDDEN_PROJECT_FIELDS & set(payload))
        self.run_node(final=True); self.assertEqual(len(self.backend.created),2)
        self.run_node(); self.assert_success(); self.assertEqual(len(self.backend.created),3)
        self.assertEqual(self.backend.created[2]['resolution'],'480p'); self.assertEqual(self.authored(),before)
    def test_existing_completed_final_child_is_adopted_even_when_new_generation_is_blocked(self):
        self.backend.enable_final(); self.run_node(); original=self.assert_success(); source=self.checkpoint()['job_id']
        child='job-mybox-'+'f'*32; key='mbx-final-v1-'+source.removeprefix('job-mybox-')
        payload=dict(provider='volcengine_ark',model=target.SEEDANCE_2_5_MODEL_ID,client_request_id=key,hmb_generation_task=target.TASK_TEXT_ONLY)
        self.backend.jobs[child]=dict(self.backend.job(payload,15),task_id=child,job_id=child,
            download_url=BASE+protocol.API+'/items/'+child+'/media?download=1',draft_parent_task_id=source)
        self.backend.jobs[source]['draft_final']=self.backend.projection(source,'completed',child,'completed')
        self.backend.capabilities.update(generation_enabled=False,reason_code='my_box_budget_limits_unsupported')
        before=self.authored(); self.run_node(final=True); self.assert_success()
        self.assertEqual(self.checkpoint()['job_id'],child); self.assertEqual(len(self.backend.created),1)
        self.assertEqual(self.authored(),before); self.assertEqual(original.read_bytes(),MOV)
    def test_expired_or_reserved_failed_child_cannot_submit_replacement_final(self):
        self.backend.enable_final(); self.run_node(); self.assert_success(); source=self.checkpoint()['job_id']
        self.backend.jobs[source]['draft_final']=self.backend.projection(source,'expired')
        self.run_node(final=True); self.assertEqual(len(self.backend.created),1)
        child='job-mybox-'+'e'*32; key='mbx-final-v1-'+source.removeprefix('job-mybox-')
        payload=dict(provider='volcengine_ark',model=target.SEEDANCE_2_5_MODEL_ID,client_request_id=key,hmb_generation_task=target.TASK_TEXT_ONLY)
        self.backend.jobs[child]=dict(self.backend.job(payload,14),task_id=child,job_id=child,status='failed',download_url=None,video_url=None,draft_parent_task_id=source)
        self.backend.jobs[source]['draft_final']=self.backend.projection(source,'reserved',child,'failed')
        self.run_node(final=True); self.assertEqual(len(self.backend.created),1)
        self.assertEqual(self.checkpoint()['job_id'],child); self.assertFalse(self.node._execution_succeeded)
    def test_final_child_requires_exact_original_source_parent(self):
        self.backend.enable_final(); self.run_node(); original=self.assert_success(); source=self.checkpoint()['job_id']
        child='job-mybox-'+'c'*32; key='mbx-final-v1-'+source.removeprefix('job-mybox-')
        payload=dict(provider='volcengine_ark',model=target.SEEDANCE_2_5_MODEL_ID,client_request_id=key,hmb_generation_task=target.TASK_TEXT_ONLY)
        job=dict(self.backend.job(payload,12),task_id=child,job_id=child,
            download_url=BASE+protocol.API+'/items/'+child+'/media?download=1')
        self.backend.jobs[source]['draft_final']=self.backend.projection(source,'completed',child,'completed')
        for parent in (None,'job-mybox-'+'d'*32):
            with self.subTest(parent=parent):
                self.backend.jobs[child]=dict(job)
                if parent is not None:self.backend.jobs[child]['draft_parent_task_id']=parent
                self.run_node(final=True)
                self.assertEqual(len(self.backend.created),1)
                self.assertEqual(self.checkpoint()['job_id'],source)
                self.assertEqual(Path(self.node.parameter_output_values['VIDEO_OUT'].value),original)
                self.assertEqual(original.read_bytes(),MOV)
    def test_other_models_keep_hidden_draft_actions_dormant_during_new_runs(self):
        for model in (target.MODEL_NAME_SEEDANCE_2_0,target.MODEL_NAME_SEEDANCE_2_0_FAST):
            for hidden in (target.DRAFT_ACTION_PREVIEW,target.DRAFT_ACTION_FINAL):
                with self.subTest(model=model,hidden=hidden):
                    node=self.create('Dormant '+model+' '+hidden)
                    for key,value in dict(model_id=model,resolution='720p',output_format='mp4').items():
                        node.set_parameter_value(key,value,initial_setup=True)
                    # A stale hidden value from an older saved workflow is
                    # authored state; it must remain dormant in another model.
                    node.parameter_values['draft_action']=hidden
                    self.assertEqual(node.parameter_values['draft_action'],hidden)
                    before=self.authored(node); count=len(self.backend.created); feature_count=len(self.backend.features)
                    asyncio.run(node._aprocess_impl()); self.assert_success(node,expected=MP4)
                    self.assertEqual(len(self.backend.created),count+1)
                    payload=self.backend.created[-1]
                    self.assertEqual(payload['model'],target.MODEL_ID_ALIASES[model])
                    self.assertNotIn('draft',payload); self.assertNotIn('draft_job_id',payload)
                    self.assertEqual(payload['quality'],'720p'); self.assertEqual(self.authored(node),before)
                    self.assertEqual(node.parameter_values['draft_action'],hidden)
                    self.assertTrue(all(kind=='normal' for kind,kwargs in self.backend.features[feature_count:]))
    def test_old_25_draft_checkpoint_does_not_turn_other_model_run_into_final(self):
        self.backend.enable_final(); self.run_node(); original=self.assert_success()
        source=self.checkpoint()['job_id']
        for key,value in dict(model_id=target.MODEL_NAME_SEEDANCE_2_0,resolution='720p',output_format='mp4').items():
            self.node.set_parameter_value(key,value,initial_setup=True)
        self.node.parameter_values['draft_action']=target.DRAFT_ACTION_FINAL
        before=self.authored(); asyncio.run(self.node._aprocess_impl()); self.assert_success(expected=MP4)
        self.assertEqual(len(self.backend.created),2); self.assertNotIn('draft_job_id',self.backend.created[-1])
        self.assertEqual(self.authored(),before); self.assertEqual(original.read_bytes(),MOV)
        self.assertEqual(self.node.parameter_values['draft_action'],target.DRAFT_ACTION_FINAL)
        self.assertNotEqual(self.checkpoint()['job_id'],source)
    def test_final_scheduler_respects_other_running_flow_and_inactive_node(self):
        self.backend.enable_final(); self.run_node(); self.assert_success(); source=self.checkpoint()['job_id']
        count=len(self.backend.calls)
        with mock.patch.object(self.engine.flow_manager,'check_for_existing_running_flow',return_value=True), \
             mock.patch.object(controller_module.asyncio,'run_coroutine_threadsafe',side_effect=forbidden) as schedule:
            result=self.controller().schedule_final({},source)
        self.assertFalse(result.success); schedule.assert_not_called()
        self.assertFalse(self.node._hmb_draft_finalize_pending); self.assertEqual(len(self.backend.calls),count)
        with mock.patch.object(self.node,'_runtime_node_is_live',return_value=False), \
             mock.patch.object(controller_module.asyncio,'run_coroutine_threadsafe',side_effect=forbidden) as schedule:
            result=self.controller().schedule_final({},source)
        self.assertFalse(result.success); schedule.assert_not_called(); self.assertEqual(len(self.backend.calls),count)
        self.send(DeleteNodeRequest(node_name=self.node.name))
        result=self.controller().schedule_final({},source)
        self.assertFalse(result.success); self.assertEqual(len(self.backend.created),1)
    def test_stale_scheduled_final_cannot_finalize_a_newer_draft_source(self):
        self.backend.enable_final(); self.run_node(); self.assert_success(); old=self.checkpoint()['job_id']
        self.run_node(); self.assert_success(); newest=self.checkpoint()['job_id']
        self.assertNotEqual(newest,old); count=len(self.backend.created)
        self.run_node(final=True,expected_source_task_id=old)
        self.assertEqual(len(self.backend.created),count)
        self.assertEqual(self.checkpoint()['job_id'],newest)

if __name__=='__main__':
    if '--inspect-draft' in sys.argv:
        probe=MyBoxNodeTests('test_preflight_has_no_auth_workspace_upload_or_post')
        try:
            probe.setUp()
            print(json.dumps({'authored_after_hydration':probe.authored(),
                'preview_constant':target.DRAFT_ACTION_PREVIEW,'selected':controller_module.is_selected(probe.node)},ensure_ascii=True))
            probe.node.set_parameter_value('draft_action',target.DRAFT_ACTION_PREVIEW,initial_setup=True)
            print(json.dumps({'authored_after_explicit_preview':probe.authored()},ensure_ascii=True))
            probe.node.set_parameter_value('resolution','480p')
            probe.node.set_parameter_value('draft_action',target.DRAFT_ACTION_PREVIEW)
            print(json.dumps({'authored_after_normal_editor_values':probe.authored(),
                'ui_options':probe.node.get_parameter_by_name('draft_action').ui_options},ensure_ascii=True))
        finally:probe.doCleanups()
        raise SystemExit(0)
    selected_case=sys.argv[sys.argv.index('--case')+1] if '--case' in sys.argv else ''
    suite=unittest.TestSuite([MyBoxNodeTests(selected_case)]) if selected_case else unittest.defaultTestLoader.loadTestsFromTestCase(MyBoxNodeTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'status':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,
        'transport':'mock-only','native_sdk':True,'paid_generation':False,'user_workflow_changes':0}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
