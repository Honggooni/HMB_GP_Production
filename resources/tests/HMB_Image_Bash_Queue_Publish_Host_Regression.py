"""Private SDK: Apply/reopen/save roundtrip and duplicate publication bytes.

Only synthetic media in a private directory; no active Desktop/session access.
"""
from pathlib import Path
import asyncio, hashlib, json, logging, os, socket, sys, tempfile
from copy import deepcopy
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
PRODUCT=Path(os.environ.get('HMB_QUEUE_PRODUCT_ROOT',str(ROOT)))
OUT=Path(os.environ.get('HMB_QUEUE_HOST_REPORT_DIR',str(ROOT/'reports/regression-checks/HMB_Image_Bash_Queue_Publish_Host_Regression')))
OUT.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(PRODUCT),str(ROOT/'resources/tests')];sys.dont_write_bytecode=True
import HMB_Image_Bash_Apply_Worker_Host_Regression as fixture
import HMB_Image_Bash_Apply_Readiness_Host_Regression as readiness
# The shared fixture helpers add the checkout to sys.path. Restore the exact
# requested product before the SDK creates or imports any product node.
sys.path.insert(0,str(PRODUCT))
RESULT={}

async def check(engine,node,source,set_value,candidate,png,directory,context,records,settled,send):
    import HMBImageBash as product
    assert Path(product.__file__).resolve()==(PRODUCT/'HMBImageBash.py').resolve(),product.__file__
    # Existing SDK regression checks editor snapshot readiness, immediate
    # reopens, successful/failed Apply, retained draft and native serializer.
    await readiness.check(engine,node,source,set_value,candidate,png,directory,context,records,settled,send)
    RESULT['apply_readiness']=deepcopy(readiness.RESULT)
    original=engine.event_manager.put_event
    events=[]
    def capture(event,*args,**kwargs):
        # Only lengths/types, never saved media or provider data in reports.
        events.append({'type':type(event).__name__,'bytes':len(json.dumps(event,default=lambda obj:vars(obj),ensure_ascii=False).encode())})
        return original(event,*args,**kwargs)
    current=product._document(node.get_parameter_value('bash_image'))
    current.setdefault('meta',{}).setdefault('hmb_image_bash',{}).setdefault('apply',{})['png_base64']='A'*(2*1024*1024)
    async def measure(legacy):
        events.clear()
        project=deepcopy(current)
        with mock.patch.object(engine.event_manager,'put_event',side_effect=capture):
            if legacy:
                from uuid import uuid4
                project['meta']['hmb_image_bash']['editor_snapshot_id']=str(uuid4())
                previous=node._hmb_syncing;node._hmb_syncing=True
                try:
                    node.set_parameter_value('bash_image',project)
                    node._hmb_editor_snapshot_id=project['meta']['hmb_image_bash']['editor_snapshot_id']
                    node._publish_header();node.publish_update_to_parameter('bash_image',project)
                finally:node._hmb_syncing=previous
            else:node._set_project(project)
        return deepcopy(events)
    legacy=await measure(True);candidate_events=await measure(False)
    before=sum(row['bytes'] for row in legacy);after=sum(row['bytes'] for row in candidate_events)
    assert after<before,(legacy,candidate_events)
    stored=product._document(node.get_parameter_value('bash_image'))
    assert stored['meta']['hmb_image_bash']['apply']['png_base64']==current['meta']['hmb_image_bash']['apply']['png_base64']
    assert stored['meta']['konva_json']==current['meta']['konva_json']
    RESULT['publish']={'legacy_events':legacy,'candidate_events':candidate_events,'legacy_bytes':before,'candidate_bytes':after,
                       'saved_png_and_scene_preserved':True,'scope':'SDK events for one private synthetic 2MiB receipt, not measured network traffic.'}
    RESULT.update(status='PASS',paid_calls=0,network_calls=0,actual_Desktop=False,product_path=product.__file__,
                  product_sha256=hashlib.sha256(Path(product.__file__).read_bytes()).hexdigest())

if __name__=='__main__':
    previous=Path.cwd()
    with tempfile.TemporaryDirectory(prefix='queue-bash-',dir=OUT) as temp:
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
    (OUT/'RESULT.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':RESULT.get('status'),'publish':RESULT.get('publish')},ensure_ascii=False))
