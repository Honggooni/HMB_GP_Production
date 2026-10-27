// Offline SDK construction plus the exact prototype helper and native wjr.
// No live app, installed file, network, media render, or provider is touched.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {readNativeEditorSource} from './_hmb_native_editor_fixture.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const sdk=process.env.HMB_NATIVE_GEOMETRY_SDK || path.join(process.env.LOCALAPPDATA,
 'ai.griptape.nodes.desktop/current/resources/engine-bundle/python/python.exe');
const original=readNativeEditorSource(root);
const nativeResizeStore=original.slice(original.indexOf('function wjr('),original.indexOf('function Tjr('));
assert.ok(nativeResizeStore.startsWith('function wjr('));
const helper=fs.readFileSync(path.join(root,'resources/editor/hmb-color-lut-native-header.js'),'utf8');
const context=vm.createContext({console,Promise});
vm.runInContext(nativeResizeStore+'\n'+helper+`\nglobalThis.testAPI={decorate:hmbColorLUTCreateMetadata,apply:hmbApplyColorLUTInitialGeometry};`,context);
const api=context.testAPI,clone=value=>JSON.parse(JSON.stringify(value));
let checks=0,sequence=0;
const equal=(actual,expected,message)=>{assert.deepEqual(clone(actual),clone(expected),message);checks++;};
const hint=()=>({schema:'hmb-color-lut-native-initial-geometry-v1',version:1,width:1225,height:1057,
 factory_width:1220,factory_height:1160,token:(++sequence).toString(16).padStart(32,'0'),status:'pending'});
const key='hmb_color_lut_native_initial_geometry';
function fixture(queued=false){
 const initial={id:'LUT',width:1220,height:1160,style:{width:1220,height:1160},measured:{width:1220,height:1160},
  data:{node_name:'LUT',node_type:'HMBColorLUTLibrary',metadata:{position:{x:11,y:22},size:{width:1220,height:1160},[key]:hint()},
   elements:[{name:'video_url',modes:['output']}],outputs:{video_url:'preserve-existing.mov'},shot:{shot_uuid:'preserve-shot'}}};
 let nodes=[initial,{id:'Other',data:{node_type:'Other',metadata:{size:{width:99,height:88}}}}],updates=0;
 const calls=[],refreshes=[];
 const queue=[];let scheduled=false;
 const get=()=>nodes,apply=update=>{nodes=typeof update==='function'?update(nodes):update;updates++;};
 const set=update=>{if(!queued){apply(update);return;}queue.push(update);
  if(!scheduled){scheduled=true;queueMicrotask(()=>{scheduled=false;for(const job of queue.splice(0))apply(job);});}};
 const persist=(name,metadata)=>{calls.push({name,metadata:clone(metadata)});return Promise.resolve({});};
 return {initial,get,set,calls,refreshes,persist,refresh:name=>refreshes.push(name),updates:()=>updates};
}
const placement={position:{x:4,y:8},tempId:'placing-synthetic'};
equal(api.decorate('ExampleNode',placement),placement,'Other node placement is unchanged');
assert.equal(api.decorate('HMBColorLUTLibrary',placement,true),placement,'Initial setup never opts in');checks++;
for(const authored of [{...placement,size:{width:900,height:800}},{...placement,expanded_dimensions:{width:1,height:2}},
 {...placement,color:'#123456'}]){assert.equal(api.decorate('HMBColorLUTLibrary',authored),authored);checks++;}
equal(api.decorate('HMBColorLUTLibrary',placement).hmb_color_lut_native_factory_request,
 {schema:'hmb-color-lut-native-factory-request-v1',temp_id:placement.tempId},'Fresh placement gets only a transient request marker');
assert.equal(placement.hmb_color_lut_native_factory_request,undefined,'Decoration never mutates the original metadata');checks++;

{
 const f=fixture(),before=clone(f.initial),other=clone(f.get()[1]);
 await api.apply(f.initial.data,true,f.get,f.set,f.persist,f.refresh);
 equal(f.get()[0].data.metadata.size,{width:1225,height:1057});
 equal(f.get()[0].style,{width:1225,height:1057});equal(f.get()[0].measured,{width:1225,height:1057});
 equal(f.get()[0].data.outputs,before.data.outputs);equal(f.get()[0].data.elements,before.data.elements);equal(f.get()[0].data.shot,before.data.shot);
 equal(f.get()[0].data.metadata.position,before.data.metadata.position);equal(f.get()[1],other);
 assert.equal(f.calls.length,1);checks++;assert.equal(f.get()[0].data.metadata[key].status,'applied');checks++;
 const updates=f.updates();
 for(let i=0;i<12;i++)api.apply(f.initial.data,true,f.get,f.set,f.persist,f.refresh);
 assert.equal(f.calls.length,1);checks++;assert.equal(f.updates(),updates,'No recurring update loop');checks++;
 const saved=clone(f.get()[0]);
 api.apply(saved.data,true,f.get,f.set,f.persist,f.refresh);assert.equal(f.calls.length,1,'Save/reopen consumed hint cannot resize again');checks++;
}
{
 const f=fixture();api.apply(f.initial.data,false,f.get,f.set,f.persist,f.refresh);
 assert.equal(f.calls.length,0,'Stock/fallback host does not apply the hint');checks++;assert.equal(f.updates(),0);checks++;
}
{
 const f=fixture(true),pending=api.apply(f.initial.data,true,f.get,f.set,f.persist,f.refresh);
 assert.equal(f.calls.length,0,'Actual ReactFlow-style node queue has not committed at dispatch time');checks++;
 assert.equal(f.get()[0].data.metadata[key].status,'pending');checks++;
 await pending;
 assert.equal(f.calls.length,1,'Persistence follows the queued updater commit exactly once');checks++;
 equal(f.get()[0].data.metadata.size,{width:1225,height:1057});
}
{
 const f=fixture();f.initial.width=1370;f.initial.height=1175;f.initial.style={width:1370,height:1175};
 f.initial.measured={width:1370,height:1175};f.initial.data.metadata.size={width:1370,height:1175};
 await api.apply(f.initial.data,true,f.get,f.set,f.persist,f.refresh);
 equal(f.get()[0].data.metadata.size,{width:1370,height:1175},'A manual size before activation wins');
 assert.equal(f.calls[0].metadata.size,undefined,'Skipped hint consumption never sends an old factory size');checks++;
 assert.equal(f.get()[0].data.metadata[key].status,'skipped');checks++;
}
{
 const f=fixture(),before=clone(f.initial);
 const result=await api.apply(f.initial.data,true,f.get,f.set,()=>Promise.reject(new Error('Synthetic metadata denial')),f.refresh);
 assert.equal(result.rejected,true);checks++;equal(f.get()[0].style,before.style,'Reject rolls back only the owned optimistic geometry');
 equal(f.get()[0].data.metadata.size,before.data.metadata.size);equal(f.get()[0].data.outputs,before.data.outputs);
 assert.equal(f.get()[0].data.metadata[key].status,'rejected');checks++;
 api.apply(f.initial.data,true,f.get,f.set,f.persist,f.refresh);assert.equal(f.calls.length,0,'Rejection never auto retries');checks++;
}
for(const reject of [false,true]){
 const f=fixture();let finish;
 const pending=api.apply(f.initial.data,true,f.get,f.set,()=>new Promise((resolve,no)=>finish=reject?no:resolve),f.refresh);
 await Promise.resolve();
 f.set(nodes=>nodes.map(node=>node.id==='LUT'?{...node,width:1400,height:1200,style:{width:1400,height:1200},measured:{width:1400,height:1200},
  data:{...node.data,metadata:{...node.data.metadata,size:{width:1400,height:1200}}}}:node));
 finish(reject?new Error('Late denial'):{});await pending;
 equal(f.get()[0].data.metadata.size,{width:1400,height:1200},'A later manual resize survives late acknowledgement or rejection');
 equal(f.get()[0].style,{width:1400,height:1200});
}
{
 const f=fixture();let fail;
 const pending=api.apply(f.initial.data,true,f.get,f.set,()=>new Promise((_resolve,reject)=>fail=reject),f.refresh);
 await Promise.resolve();
 const replacement=fixture().initial;f.set([replacement]);fail(new Error('Old node was deleted'));await pending;
 equal(f.get(),[replacement],'Late old-node rejection cannot change a replacement with the same name');
}

// Real SDK construction verifies that safe stock defaults and authored metadata
// remain authoritative, including a saved pending hint after a disconnect.
const python=String.raw`
import copy,json,logging,os,socket,sys,tempfile
from pathlib import Path
from unittest import mock
sys.path.insert(0,sys.argv[1])
with tempfile.TemporaryDirectory(prefix='hmb-native-geometry-') as folder:
 env={key:str(Path(folder)/key) for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','LOCALAPPDATA','APPDATA')}
 env['GTN_CONFIG_WORKSPACE_DIRECTORY']=folder
 with mock.patch.dict(os.environ,env),mock.patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')):
  logging.disable(logging.CRITICAL)
  from griptape_nodes.retained_mode.engine import engine_scope
  with engine_scope() as engine:
   from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
   from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
   from griptape_nodes.node_library.library_registry import LibraryRegistry,LibrarySchema
   engine.handle_request(EnsureWorkflowAndFlowRequest(flow_name='NativeGeometryOffline'))
   import HMBColorLUTLibrary as lut
   import _hmb_shot_routing as routing
   schema=LibrarySchema.model_validate_json((Path(sys.argv[1])/'griptape-nodes-library.json').read_text('utf-8'))
   library=LibraryRegistry.generate_new_library(schema)
   definition=next(row for row in schema.nodes if row.class_name=='HMBColorLUTLibrary')
   library.register_lazy_node_type('HMBColorLUTLibrary',definition.metadata,lambda:lut.HMBColorLUTLibrary)
   engine.event_manager.initialize_queue()
   key=lut.COLOR_LUT_NATIVE_GEOMETRY_HINT
   with mock.patch.object(routing,'schedule_post_registration_reconcile'):
    stock=lut.HMBColorLUTLibrary(name='Stock',metadata={'position':{'x':1,'y':2},'tempId':'stock'})
    assert stock.metadata['size']=={'width':1220,'height':1160} and key not in stock.metadata
    marked={'position':{'x':3,'y':4},'tempId':'placing-offline','hmb_color_lut_native_factory_request':{'schema':'hmb-color-lut-native-factory-request-v1','temp_id':'placing-offline'}}
    created=engine.handle_request(CreateNodeRequest(node_type='HMBColorLUTLibrary',node_name='Fresh',specific_library_name='HMB_GP_Production',metadata=copy.deepcopy(marked)))
    assert created.succeeded(),created.result_details
    fresh=engine.node_manager.get_node_by_name(created.node_name)
    assert fresh.metadata[key]['status']=='pending' and fresh.metadata[key]['width']==1225 and fresh.metadata[key]['height']==1057
    assert 'hmb_color_lut_native_factory_request' not in fresh.metadata
    assert fresh.get_parameter_by_name(lut.UI).ui_options['height']==1000
    custom={'size':{'width':1370,'height':1175},'position':{'x':12,'y':34}}
    restored=lut.HMBColorLUTLibrary(name='Custom',metadata=copy.deepcopy(custom))
    assert restored.metadata==custom
    pending=copy.deepcopy(fresh.metadata)
    recreated=engine.handle_request(CreateNodeRequest(node_type='HMBColorLUTLibrary',node_name='Reopened',specific_library_name='HMB_GP_Production',metadata=pending,initial_setup=True))
    assert recreated.succeeded(),recreated.result_details
    reopened=engine.node_manager.get_node_by_name(recreated.node_name)
    assert reopened.metadata['size']=={'width':1220,'height':1160} and reopened.metadata[key]['status']=='restored'
    applied=copy.deepcopy(fresh.metadata);applied['size']={'width':1225,'height':1057};applied[key]['status']='applied'
    kept=lut.HMBColorLUTLibrary(name='Applied',metadata=copy.deepcopy(applied))
    assert kept.metadata==applied
    for node in (stock,fresh,restored,reopened,kept):node.after_node_deleted()
    print(json.dumps({'sdk':'PASS','checks':13,'native_CreateNodeRequest':True,'stock_default':[1220,1160],'stock_widget':[1180,1000],'target':[1225,1057]}))
`;
const child=spawnSync(sdk,['-B','-c',python,root],{cwd:root,encoding:'utf8',timeout:60000,maxBuffer:1024*1024});
assert.equal(child.status,0,child.stderr||child.stdout);
const sdkReport=JSON.parse(child.stdout.trim().split('\n').at(-1));checks+=sdkReport.checks;
console.log(JSON.stringify({status:'PASS',checks,native_resize_store:true,sdk:sdkReport,
 paid_requests:0,live_engine_requests:0,installed_files_changed:0}));
