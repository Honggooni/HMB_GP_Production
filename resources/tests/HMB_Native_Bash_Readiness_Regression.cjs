// Pure transport/state boundary of the exact native helper; no app or server.
const assert=require('node:assert/strict'),vm=require('node:vm'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const {regressionPython}=require('./_hmb_test_runtime.cjs');
const root=path.resolve(__dirname,'../..'),python=regressionPython(root);
const read=spawnSync(python,['-I','-B','-c',`import ast,json,pathlib,sys
tree=ast.parse((pathlib.Path(sys.argv[1])/'tools/hmb_native_semantic_adapter.py').read_text('utf-8'))
f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_bash_readiness_bridge')
print(json.dumps({t.id:ast.literal_eval(n.value) for n in f.body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name) and t.id in ('helpers','hook')}))`,root],{encoding:'utf8'});
assert.equal(read.status,0,read.stderr);const {helpers,hook}=JSON.parse(read.stdout);
let requests=[],replies=[],notices=[];
const scope={console,Promise,Error,Number,Object,Array,Set,Map,JSON,hmbNativeStudioFlowEpoch:1,
 Id:{request:async(kind,body)=>{requests.push({kind,...body});const value=replies.shift();if(value instanceof Error)throw value;return {value};}},
 CJ:{info:(...args)=>notices.push(args)}};
vm.createContext(scope);vm.runInContext(helpers,scope);
const prep=(revision=1,ready=true,extra={})=>({preparation:{schema:'hmb-image-bash-preparation-v1',phase:ready?'ready':'preparing',ready,
 workspace_id:'ws',workspace_revision:revision,channel_uuid:'ch',node_instance_uuid:'instance',...extra}});
const doc=(revision=1)=>({meta:{hmb_image_bash:{workspace_id:'ws',workspace_revision:revision,channel_uuid:'ch',node_instance_uuid:'instance'}},value:'latest'});
const node=()=>({data:{node_type:'HMBImageBash',metadata:{library:'HMB_GP_Production',hmb_image_bash_workspace_id:'ws',hmb_image_bash_channel_uuid:'ch',hmb_connection_identity_v1:'node-identity'}}});
const reset=(values=[])=>{requests=[];replies=values;notices=[];scope.hmbNativeStudioFlowEpoch=1;};
(async()=>{
 assert.throws(()=>scope.hmbBashPreparation({}),/unavailable/);
 assert.equal(scope.hmbBashPreparation(prep(0,true,{phase:'idle',workspace_id:'',channel_uuid:''})).ready,true);
 reset([prep(2,false)]);const pending=await scope.hmbBashReadCurrent('Bash',()=>true);
 assert.equal(pending.doc,null);assert.equal(requests.length,1,'Do not read/open a stale scene while preparing');
 reset([prep(2),doc(2),prep(2)]);const fresh=await scope.hmbBashReadCurrent('Bash',()=>true);
 assert.equal(fresh.doc.value,'latest');assert.equal(fresh.doc.meta.hmb_image_bash.workspace_revision,2);
 reset([prep(2),doc(2),prep(3,false)]);assert.equal((await scope.hmbBashReadCurrent('Bash',()=>true)).doc,null,'Changed revision must not open');
 reset([prep(2),doc(1),prep(2)]);assert.equal((await scope.hmbBashReadCurrent('Bash',()=>true)).doc,null,'Stale metadata must not open');
 reset([prep(2)]);await assert.rejects(scope.hmbBashReadCurrent('Bash',()=>false),/workspace_changed/);
 reset();const fallback={value:'stock'};assert.equal((await scope.hmbBashOpenSnapshot('Other',fallback,()=>({data:{node_type:'Image'}}))).value,fallback);assert.equal(requests.length,0);
 reset([prep(2,false)]);assert.equal(await scope.hmbBashOpenSnapshot('Bash',fallback,node),null);assert.equal(notices.length,1);
 reset([prep(2),doc(2),prep(2)]);assert.equal((await scope.hmbBashOpenSnapshot('Bash',fallback,node)).value.value,'latest');
 reset([prep(2),doc(2),prep(2)]);let changed=false;const getter=()=>{const n=node();if(changed)n.data.metadata.hmb_image_bash_workspace_id='foreign';changed=true;return n;};
 assert.equal(await scope.hmbBashOpenSnapshot('Bash',fallback,getter),null,'Same-name replacement/workspace change must not open');
 // A delayed initial query must never override a newer execution event.
 let view=null,listener,resolveQuery,clean;
 scope.C={useState:()=>[view,value=>{view=value}],useEffect:effect=>{clean=effect()}};
 scope.xu=()=>({getNode:node});scope.eZ=select=>select({flowName:'fixture'});
 scope.IX=()=>({subscribeToEvent:(kind,callback)=>{listener=callback;return()=>{}}});
 scope.Id.request=()=>new Promise(resolve=>{resolveQuery=resolve});
 const props={nodeName:'Bash',parameterName:'bash_image',ui_options:{modal:'ImageBashModal',button_label:'Open'}};
 scope.hmbUseBashParameterReadiness(props);
 listener({payload_type:'ParameterValueUpdateEvent',payload:{node_name:'Bash',parameter_name:'HMB_IMAGE_BASH_UI',value:prep(2)}});
 resolveQuery({value:prep(1,false)});await Promise.resolve();await Promise.resolve();
 assert.equal(view.workspace_revision,2,'Delayed GET overwrote newer readiness event');assert.equal(view.ready,true);clean();
 // Opening subscribes before snapshot query and accepts an absent initial
 // instance from the authenticated current projection instead of demanding reopen.
 assert.ok(hook.indexOf("const off=hmbLiveSubscribe('ExecutionEvent'")<hook.indexOf('refresh();\n return()=>'));
 assert.match(hook,/scope\.instance=next\.node_instance_uuid/);assert.match(hook,/hmbPending\.current=null;hmbCommit\.current=null;hmbQueued\.current=null/);
 assert.match(hook,/hmbRenderPreparing/);assert.match(hook,/operation:'retry_inputs'/);
 assert.match(hook,/seeded\.some\(layer=>!hmbLayers\.current\.some/);
 assert.match(hook,/if\(!hmbHydrated\.current\)/,'Authored layer deletions must not rerun initial hydration');
 assert.doesNotMatch(hook,/\$e\.current/,'Readiness must not depend on the stock private cache sentinel');
 assert.doesNotMatch(hook,/setInterval/);
 console.log('Native Bash transport/readiness/open-race/scope boundaries PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
