"""Real SDK saved pending document admission before input hydration; no app/network."""
from __future__ import annotations
import asyncio
import base64
from copy import deepcopy
import contextvars
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
STANDARD=Path.home()/"Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
EDITOR=Path.home()/"AppData/Local/ai.griptape.nodes.desktop/current/resources/editor-bundle"
OUT=Path(os.environ.get("HMB_BASH_COLD_ADMISSION_REPORT_DIR",str(ROOT/"reports/regression-checks/HMB_Image_Bash_Cold_Admission_Host_Regression")));OUT.mkdir(parents=True,exist_ok=True)
RESULT={}

def denied(*a,**k):raise AssertionError("Network/provider forbidden")

async def exercise(engine,directory):
    from PIL import Image
    import HMBImageBash as product
    from _hmb_image_bash_state import validate_png_bytes,scene_fingerprint
    from griptape_nodes.node_library.library_registry import LibraryRegistry,LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.files.file import File
    from griptape.artifacts import ImageUrlArtifact
    schema=LibrarySchema.model_validate_json((ROOT/'griptape-nodes-library.json').read_text('utf-8-sig'))
    library=LibraryRegistry.generate_new_library(schema)
    metadata=next(row.metadata for row in schema.nodes if row.class_name=='HMBImageBash')
    library.register_lazy_node_type('HMBImageBash',metadata,lambda:product.HMBImageBash)
    engine.event_manager.initialize_queue()
    def send(req):
        req.broadcast_result=False;return engine.handle_request(req)
    flow=send(EnsureWorkflowAndFlowRequest(flow_name='PendingColdAdmissionSDK'));assert flow.succeeded(),flow.result_details
    def create(name):
        made=send(CreateNodeRequest(node_type='HMBImageBash',node_name=name,specific_library_name=schema.name,
            override_parent_flow_name=flow.flow_name,initial_setup=True,create_error_proxy_on_failure=False,
            metadata={'size':{'width':800,'height':680},'hmb_image_bash_workspace_id':'w','hmb_image_bash_channel_uuid':'c'}))
        assert made.succeeded(),made.result_details
        return engine.node_manager.get_node_by_name(made.node_name)
    def set_value(node,name,value,initial=True,output=False):
        return send(SetParameterValueRequest(node_name=node.name,parameter_name=name,value=deepcopy(value),initial_setup=initial,is_output=output))
    def png(color):
        b=BytesIO();Image.new('RGBA',(4,2),color).save(b,'PNG');return b.getvalue()
    previous_png=png('green');old_path=directory/'old-complete.png';old_path.write_bytes(previous_png)
    old_url='data:image/png;base64,'+base64.b64encode(previous_png).decode()
    draft_url='data:image/png;base64,'+base64.b64encode(png('blue')).decode()
    try:
        for kind in ('pending','failed','prepare'):
            node=create('Cold-'+kind)
            pristine=deepcopy(node.get_parameter_value('bash_image'))
            project=deepcopy(pristine)
            project['value']=draft_url;project['meta']['created_at']='new-editor-commit'
            project['meta']['input_images']=[]
            project['meta']['konva_json']={'images':[],'lines':[{'points':[0,0,1,1],'stroke':'red','strokeWidth':1}]}
            hmb=project['meta'].setdefault('hmb_image_bash',{})
            hmb.update(workspace_id='w',channel_uuid='c',workspace_revision=1,node_instance_uuid='saved-instance',source_bindings=[])
            receipt={'schema':product.RECEIPT_SCHEMA,'editor_commit':'old-editor-commit',**validate_png_bytes(previous_png),
                'scene_sha256':'1'*64,'source_hashes':{},'png_base64':base64.b64encode(previous_png).decode(),'output_path':str(old_path)}
            hmb['apply']=deepcopy(receipt)
            if kind=='prepare':
                hmb['pending_prepare']={'schema':'hmb-image-bash-pending-prepare-v1','scope':{'workspace_id':'w','channel_uuid':'c','workspace_revision':1},'source_uids':[]}
            else:
                hmb['pending_apply']={'schema':'hmb-image-bash-pending-apply-v1','editor_commit':'new-editor-commit'}
                if kind=='failed':hmb['pending_apply'].update(phase='error',error='synthetic bad PNG')
            # Match native exported file order: the old serialized output is
            # assigned before bash_image; this is not a verified live cache.
            for output in (False,True):
                result=set_value(node,'output_image',ImageUrlArtifact(value=str(old_path)),output=output)
                assert result.succeeded(),result.result_details
            assert node._hmb_last_output is None
            assert File(node.parameter_output_values['output_image'].value).read_bytes()==previous_png
            copied=[];before=node.before_value_set
            def observe(parameter,value):
                copied.append(contextvars.copy_context());return before(parameter,value)
            with mock.patch.object(node,'before_value_set',side_effect=observe):
                first=set_value(node,'bash_image',project)
                assert first.succeeded(),first.result_details
                second=set_value(node,'bash_image',project,output=True)
                assert second.succeeded(),second.result_details
            restored=product._document(node.get_parameter_value('bash_image'))
            assert restored['meta']['konva_json']==project['meta']['konva_json']
            assert restored['meta']['hmb_image_bash']==hmb
            assert restored['value']==draft_url
            assert node._hmb_prepare_phase=='idle' and node._hmb_apply_epoch==0
            assert node._hmb_apply_pending is None and node._hmb_prepare_pending is None
            assert node._hmb_last_output is None and old_path.read_bytes()==previous_png
            # A copied request context is unusable as soon as dispatch ends.
            for context in copied:
                assert context.run(node._admit_pending_cold_assignment,restored) is False
            live=deepcopy(project);live['meta']['created_at']='different-live-commit'
            if 'pending_apply' in live['meta']['hmb_image_bash']:
                live['meta']['hmb_image_bash']['pending_apply']['editor_commit']='different-live-commit'
            for initial in (False,True):
                rejected=set_value(node,'bash_image',live,initial=initial)
                assert rejected.failed(), 'Different live/initial document bypassed pending fences'
                assert product._document(node.get_parameter_value('bash_image'))==restored
            RESULT[kind+'_native_initial_value_output_pair_preserved']=True
        # An incorrect pending marker is never enough to enter cold admission.
        node=create('Malformed-Cold');project=deepcopy(project)
        project['meta']['hmb_image_bash']['pending_prepare']['schema']='forged'
        baseline=deepcopy(node.get_parameter_value('bash_image'))
        rejected=set_value(node,'bash_image',project)
        assert rejected.failed() and node.get_parameter_value('bash_image')==baseline
        # Mandatory admission failure must be explicit at construction; the
        # optional creation-observer fallback must never swallow this error.
        with mock.patch.object(product, "_install_bash_initial_value_admission", side_effect=RuntimeError("synthetic mandatory hydration adapter unavailable")):
            rejected = send(CreateNodeRequest(node_type="HMBImageBash",node_name="UnsupportedColdAdapter",
                specific_library_name=schema.name,override_parent_flow_name=flow.flow_name,
                initial_setup=True,create_error_proxy_on_failure=False))
        assert rejected.failed() and "synthetic mandatory hydration adapter unavailable" in str(rejected.result_details)
        assert old_path.read_bytes()==previous_png
        RESULT["mandatory_admission_constructor_failure_is_not_swallowed"] = True
        RESULT.update(real_initial_setup_handler=True,serialized_old_output_before_document=True,
            stale_live_initial_and_noninitial_rejected=True,copied_context_cannot_authorize=True,
            malformed_marker_rejected=True,network_calls=0,actual_desktop=False,status='PASS')
    finally:
        LibraryRegistry.unregister_library(schema.name,event_manager=engine.event_manager)

if __name__=='__main__':
    previous=Path.cwd()
    with tempfile.TemporaryDirectory(prefix='bash-cold-admission-',dir=OUT) as folder:
        directory=Path(folder)
        env={key:str(directory/key) for key in ('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','GTN_ENGINE_CONFIG_DIR','GTN_ENGINE_DATA_DIR','GTN_ENGINE_STATE_DIR','GTN_CONFIG_WORKSPACE_DIRECTORY')}
        for value in env.values():Path(value).mkdir()
        env.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(STANDARD),HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(EDITOR))
        with mock.patch.dict(os.environ,env),mock.patch.object(socket,'create_connection',side_effect=denied):
            os.chdir(directory);logging.disable(logging.CRITICAL)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:asyncio.run(exercise(engine,directory))
            finally:
                os.chdir(previous);logging.shutdown()
    (OUT/'COLD-ADMISSION-HOST-RESULT.json').write_text(json.dumps(RESULT,indent=2),encoding='utf-8')
    print(json.dumps(RESULT))
