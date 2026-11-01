// Exact compiled D208 functions in a controlled VM; no browser/app/API/SDK.
const assert=require('node:assert/strict'),vm=require('node:vm'),path=require('node:path'),fs=require('node:fs');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const {regressionPython}=require('./_hmb_test_runtime.cjs');
const python=regressionPython(root,process.env.HMB_SESSION_BINDING_TEST_PYTHON);
const out=path.resolve(process.env.HMB_SESSION_BINDING_REPORT_DIR||path.join(root,'reports/regression-checks/HMB_Native_Iframe_Session_Binding_Regression'));
fs.mkdirSync(out,{recursive:true});
const read=spawnSync(python,['-I','-B','-c',String.raw`
from pathlib import Path
import ast,hashlib,importlib.util,json,sys
import os
root=Path(sys.argv[1]);path=Path(os.environ.get('HMB_SESSION_BINDING_EDITOR_SOURCE',str(Path.home()/'AppData/Local/ai.griptape.nodes.desktop/current/resources/editor-bundle/assets/index-5XqdCa80.js')))
source=path.read_text('utf8');spec=importlib.util.spec_from_file_location('session_binding_adapter',root/'tools/hmb_native_semantic_adapter.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
tree=ast.parse((root/'tools/hmb_native_semantic_adapter.py').read_text('utf8'))
factory=next(row for row in tree.body if isinstance(row,ast.FunctionDef) and row.name=='_hmb_inline_iframe_session_binding')
constants={target.id:ast.literal_eval(row.value) for row in factory.body if isinstance(row,ast.Assign) for target in row.targets if isinstance(target,ast.Name)}
patch=module._hmb_inline_iframe_session_binding()
candidate,receipt=patch(source)
assert patch(candidate)[0]==candidate
def segment(text,start,end):
 assert text.count(start)==1 and text.count(end)==1,(start,end)
 a=text.index(start);return text[a:text.index(end,a)]
fragments={}
for label,text in [('baseline',source),('candidate',candidate)]:
 fragments[label]={
 'gra':segment(text,'var gra=','},_ra=')+'}',
 'jYt':segment(text,'function jYt(','var FX='),
 'PX':'var '+segment(text,'PX=class',';function kYt(')+';',
 'kYt':segment(text,'function kYt(','var AYt='),
 'AYt':'var '+segment(text,'AYt={sessionId:null',';function jYt(')+';',
 'api':'var '+segment(text,'Dae=class','Oae=(e,t)=>'),
 }
 assert fragments[label]['api'].endswith(',')
 fragments[label]['api']=fragments[label]['api'][:-1]+';'
for name in ('jYt','PX','kYt','AYt','api'):assert fragments['baseline'][name]==fragments['candidate'][name],name
# An already updated installed host has the ordered provider too. Reconstruct
# only its provider's exact pre-binding three substitutions as a controlled
# baseline; no file is rewritten and no full vendor bundle is redistributed.
controlled_baseline=constants['MARKER'] in source
if controlled_baseline:
 for current,previous in (('_PROVIDER_BOUND','_PROVIDER'),('_STATE_BOUND','_STATE'),('_READY_BOUND','_READY')):
  assert fragments['baseline']['gra'].count(constants[current])==1
  fragments['baseline']['gra']=fragments['baseline']['gra'].replace(constants[current],constants[previous],1)
bad=[]
for label,text in [('missing_guard',source.replace(constants['_GUARD'],'removed-guard',1)),('duplicate_provider',source+constants['_PROVIDER']),('partial',candidate.replace(constants['_STATE_BOUND'],constants['_STATE'],1)),('duplicate_marker',candidate+constants['MARKER'])]:
 try:patch(text)
 except ValueError:bad.append(label)
 else:raise AssertionError(label)
print(json.dumps({'path':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(candidate.encode()).hexdigest(),'helper_sha256':hashlib.sha256(constants['HELPER'].encode()).hexdigest(),'helper':constants['HELPER'],'fragments':fragments,'receipt':receipt,'controlled_baseline_provider':controlled_baseline,'invalid_shapes_rejected':bad,'adapter_path':str(root/'tools/hmb_native_semantic_adapter.py'),'adapter_sha256':hashlib.sha256((root/'tools/hmb_native_semantic_adapter.py').read_bytes()).hexdigest()}))
`,root],{encoding:'utf8',maxBuffer:1024*1024});
assert.equal(read.status,0,read.stderr);const input=JSON.parse(read.stdout);
const cases=[];const mark=(name,value)=>{cases.push({name,...value});};
function createEnvironment(kind){
 const messages=[],listeners=new Map();let uuid=0,current=null;
 const context={console,Error,Promise,Map,Set,JSON,crypto:{randomUUID:()=>`fixture-${++uuid}`},setTimeout,clearTimeout,OX:5000,
  EYt:['IFRAME_READY_ACK','SESSION_STATE','AUTH_STATE','CONNECTION_STATE','ENGINE_STATE','WORKFLOW_TO_OPEN','PARENT_HASH','SELECT_ENGINE_RESPONSE','API_RESPONSE'],
  TX:value=>!!value&&typeof value==='object'&&context.EYt.includes(value.type),mra:()=>{},lna:{},
  una:{Provider:'bridge'},xX:{Provider:'auth'},z:{jsx:(type,props)=>({type,props})}};
 const window={addEventListener:(kind,fn)=>{if(!listeners.has(kind))listeners.set(kind,new Set());listeners.get(kind).add(fn)},
  removeEventListener:(kind,fn)=>listeners.get(kind)?.delete(fn),parent:{postMessage:(message,origin)=>messages.push({message,origin})}};
 context.window=window;
 class Renderer{
  constructor(){this.cells=[];this.cursor=0;this.effects=[];this.live=true;}
  render(){current=this;this.cursor=0;const value=context.gra({children:'fixture'});current=null;return value.props.value;}
  flush(){for(const item of this.effects.splice(0)){item.cell.cleanup?.();item.cell.cleanup=item.effect();}}
  unmount(){this.live=false;for(const cell of this.cells)cell?.cleanup?.();}
 }
 const changed=(a,b)=>!a||!b||a.length!==b.length||a.some((x,i)=>x!==b[i]);
 context.C={
  useRef:initial=>{const r=current,i=r.cursor++;return r.cells[i]||=( {current:initial} )},
  useState:initial=>{const r=current,i=r.cursor++;if(!r.cells[i])r.cells[i]={value:typeof initial==='function'?initial():initial};const cell=r.cells[i];return[cell.value,value=>{cell.value=typeof value==='function'?value(cell.value):value}]},
  useEffect:(effect,deps)=>{const r=current,i=r.cursor++,cell=r.cells[i]||=( {} );if(changed(cell.deps,deps)){cell.deps=deps;r.effects.push({cell,effect})}},
  useCallback:(fn,deps)=>{const r=current,i=r.cursor++,cell=r.cells[i]||=( {} );if(changed(cell.deps,deps)){cell.deps=deps;cell.fn=fn;}return cell.fn;},
 };
 vm.createContext(context);
 const f=input.fragments[kind];vm.runInContext(f.api+f.PX+f.kYt+f.AYt+f.jYt+(kind==='candidate'?input.helper:'')+f.gra+';',context);
 const transport={sent:[],requests:new Map(),send(value){this.sent.push(value)},subscribeToRequestEvent(ok,no){const id=`req-${++uuid}`;this.requests.set(id,{ok,no});return id},unsubscribeFromRequestEvent(id){this.requests.delete(id)}};
 context.Id.initialize(transport);
 const emit=data=>{for(const fn of [...(listeners.get('message')||[])])fn({data})};
 const state=sessionId=>emit({type:'SESSION_STATE',sessionId,connectionState:sessionId?'connected':'pending',isBeating:!!sessionId,engineReady:!!sessionId});
 const ready=(sessionId,include=true)=>{const request=messages.filter(x=>x.message.type==='IFRAME_READY').at(-1).message;emit({type:'IFRAME_READY_ACK',requestId:request.requestId,config:{...(include?{sessionId}:{}),parentOrigin:'https://fixture.invalid'},user:null,isAuthenticated:false});};
 return{context,Renderer,state,ready,messages,listeners,transport};
}
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};
async function initialized(kind,{stateBefore,config,include=true}={}){
 const env=createEnvironment(kind),renderer=new env.Renderer();renderer.render();renderer.flush();
 if(stateBefore!==undefined)for(const state of stateBefore)env.state(state);
 env.ready(config,include);await tick();const value=renderer.render();renderer.flush();
 return{...env,renderer,value};
}
(async()=>{
 const before=await initialized('baseline',{stateBefore:['session-S'],include:false});
 assert.equal(before.value.sessionId,'session-S');assert.equal(before.context.Id.getSessionId(),null);
 assert.throws(()=>before.context.Id.send('SetParameterValueRequest',{value:'synthetic'}),/without a session/);assert.equal(before.transport.sent.length,0);before.renderer.unmount();
 mark('compiled_provider_baseline_STATE_then_missing_READY_reproduces_divergence',{baseline:true,controlled_inverse_provider:input.controlled_baseline_provider,react_session:'session-S',api_session:null,actual_requests:0});
 for(const row of [
  {name:'STATE_nonnull_beats_missing_ACK',states:['session-S'],config:undefined,include:false,expected:'session-S'},
  {name:'STATE_nonnull_beats_null_ACK',states:['session-S'],config:null,expected:'session-S'},
  {name:'STATE_explicit_clear_beats_stale_ACK',states:[null],config:'old-config-session',expected:null},
  {name:'latest_STATE_rebind_wins',states:['session-A',null,'session-B'],config:'session-A',expected:'session-B'},
 ]){
  const e=await initialized('candidate',{stateBefore:row.states,config:row.config,include:row.include!==false});
  assert.equal(e.context.Id.getSessionId(),row.expected);assert.equal(e.value.sessionId,row.expected);
  if(row.expected===null){assert.throws(()=>e.context.Id.send('SetParameterValueRequest',{}),/without a session/);assert.equal(e.transport.sent.length,0);}
  else{e.context.Id.send('SetParameterValueRequest',{});assert.equal(e.transport.sent[0].topic,`sessions/${row.expected}/request`);}
  e.renderer.unmount();mark(row.name,{react_api_aligned:true,expected_clear:row.expected===null});
 }
 const fallback=await initialized('candidate',{config:'fallback-session'});assert.equal(fallback.context.Id.getSessionId(),'fallback-session');assert.equal(fallback.value.sessionId,null,'Preserve original React pending state until SESSION_STATE');
 fallback.state(null);await tick();assert.equal(fallback.context.Id.getSessionId(),null);assert.equal(fallback.renderer.render().sessionId,null);
 fallback.state('bound-after-clear');await tick();assert.equal(fallback.context.Id.getSessionId(),'bound-after-clear');assert.equal(fallback.renderer.render().sessionId,'bound-after-clear');fallback.renderer.unmount();mark('config_fallback_only_without_STATE_then_normal_clear_rebind',{pass:true});
 const absent=await initialized('candidate',{include:false});assert.equal(absent.context.Id.getSessionId(),null);absent.renderer.unmount();mark('missing_config_and_STATE_remains_unbound',{pass:true});
 const env=createEnvironment('candidate'),old=new env.Renderer();old.render();old.flush();const oldRequest=env.messages.at(-1).message;
 env.state('prior-provider-session');old.unmount();const next=new env.Renderer();next.render();next.flush();
 env.state('new-provider-session');env.ready(undefined,false);await tick();assert.equal(next.render().sessionId,'new-provider-session');assert.equal(env.context.Id.getSessionId(),'new-provider-session');
 // Old initialize continuation and late ACK cannot invoke a replaced provider.
 for(const fn of [...(env.listeners.get('message')||[])])fn({data:{type:'IFRAME_READY_ACK',requestId:oldRequest.requestId,config:{sessionId:'retired-session'}}});
 await tick();assert.equal(env.context.Id.getSessionId(),'new-provider-session');next.unmount();mark('remount_and_retired_initialize_cannot_overwrite_current_owner',{pass:true});
 const fresh=new env.Renderer();fresh.render();fresh.flush();env.ready('fresh-config-session');await tick();assert.equal(env.context.Id.getSessionId(),'fresh-config-session');fresh.unmount();mark('new_provider_has_fresh_fallback_witness',{pass:true});
 const asyncGuard=createEnvironment('candidate');await assert.rejects(asyncGuard.context.Id.request('SetParameterValueRequest',{}),/without a session/);assert.equal(asyncGuard.transport.sent.length,0);mark('request_rejects_and_send_throws_without_session_guard_preserved',{pass:true});
 assert.equal(input.fragments.baseline.api,input.fragments.candidate.api);assert.equal(input.fragments.baseline.jYt,input.fragments.candidate.jYt);assert.equal(input.fragments.baseline.PX,input.fragments.candidate.PX);
 mark('only_provider_binding_changed_not_transport_or_jYt',{pass:true});
 const result={schema:'hmb-native-session-binding-exact-functions-v1',status:'PASS',case_count:cases.length,cases,
  input:{bundle_path:input.path,source_sha256:input.source_sha256,candidate_sha256:input.candidate_sha256,adapter_path:input.adapter_path,adapter_sha256:input.adapter_sha256},
  idempotent:true,invalid_shapes_rejected:input.invalid_shapes_rejected,scope:'Compiled installed API/PX/jYt/provider functions; if binding already exists the baseline provider is reconstructed by the exact three inverse substitutions. Controlled React hooks/parent messages; no app/browser/API/SDK execution.',controlled_baseline_provider:input.controlled_baseline_provider,
  actual_requests:0,actual_app_access:false,actual_SDK:false,broadcast_bypass:false,installed_writes:0};
 fs.writeFileSync(path.join(out,'SESSION-BINDING-EXACT-FUNCTIONS.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
})().catch(error=>{fs.writeFileSync(path.join(out,'SESSION-BINDING-EXACT-FUNCTIONS-FAIL.json'),JSON.stringify({status:'FAIL',error:String(error),stack:error.stack,cases},null,2)+'\n');console.error(error);process.exitCode=1});
