import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {nativeTestBrowserPath, nativeTestPlaywright} from './_hmb_native_editor_fixture.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const candidateBytes = fs.readFileSync(process.env.HMB_HEADER_0130_CANDIDATE);
const candidate = candidateBytes.toString('utf8');
assert.ok(candidate.includes('return hmb130IntegratedHeader(hmbHeaderSlots,(0,Z.jsxs)'));
assert.ok(candidate.includes('hmb130ConnectionIcon(e,hmbLibrary),he.map'));
assert.equal((candidate.match(/await hmb130PrepareNewWorkflow\(\);/g)||[]).length,3, 'File New, Workflows New and Mart startup use checked transition');
assert.ok(!candidate.includes('await kt();'));
const transition = candidate.match(/async function hmb130PrepareNewWorkflow\(\)\{(.*?)\}function hFn/)[1];
for (const workflowName of ['', 'saved-fixture']) {
  const calls=[];
  await new Function('fO','hmb130ConnectionRequest','kt',`return (async()=>{${transition};})()`)(
    {getState:()=>({workflowName})}, async (...args)=>calls.push(args),async()=>calls.push(['empty-stock-clear']));
  assert.deepEqual(calls, workflowName ? [['HMBPrepareWorkflowTransitionRequest',{}]] : [['empty-stock-clear']]);
}
const helperStart = candidate.indexOf('function hmbNativeOpenConnections(');
const helperEnd = candidate.indexOf('function hFn(){', helperStart);
assert.ok(helperStart > 0 && helperEnd > helperStart);
const stockPath = process.env.HMB_STOCK_EDITOR_0130_SOURCE;
const stockBytes = fs.readFileSync(stockPath);
const editorSourceHash = sha(stockBytes);
assert.equal(editorSourceHash,'841b879c94cd6bb18601f5b360daf094508bdfbfa0ec88b830a1caaf0df5871e');
const dependencies = new Map(Object.entries({
  'react-Cwox1F5v.js':'0922625a90900001152ac5899de0daf62230d0c18bc54979e9cccb50dad13750',
  'rolldown-runtime-DSDNlrLa.js':'9642411c8411b70e62cea3e38c4093f5fcd4419ec151356d87dc835062db7b69',
  'EngineContext-B0JaCG1N.js':'0eac023d9df0796c79a038ea8c37415fc7c97afb979bc7aa58bc730d1672e5e6',
}).map(([name,hash])=>{
  const bytes=fs.readFileSync(path.join(path.dirname(stockPath),name));
  assert.equal(sha(bytes),hash,`Unexpected Editor 0.130 dependency: ${name}`);
  return [name,bytes];
}));
const stock = stockBytes.toString('utf8');
const reactStart=stock.indexOf('var Fa=i((e=>{'), reactEnd=stock.indexOf(',za=/^(?:',reactStart);
assert.ok(reactStart>=0&&reactEnd>reactStart,'Missing Editor 0.130 React renderer');
const runtime = [
  'import {a as e,t as i} from "./rolldown-runtime-DSDNlrLa.js";',
  'import {t as a} from "./react-Cwox1F5v.js";',
  'import {oi as wn,si as Hn,ci as Et} from "./EngineContext-B0JaCG1N.js";',
  stock.slice(reactStart,reactEnd)+'; const Z=wn(),Cm=e(Hn()),w=Ra;',
].join('\n');
const fixture = `
let hmbNativeStudioFlowEpoch=0;
window.requests=[]; let detached=false, token=0;
window.soundSession='fixture-session'; window.soundReads=[]; window.soundScope=null;
function hmb130SessionId(){return window.soundSession;}
function hmb130SoundScope(){return window.soundScope;}
const fO={getState:()=>({setIsSaved(){}})}, z={success(){},error(){}};
function hmb130ConnectionError(error){return error.message;}
async function hmb130ConnectionRequest(type, payload){
  requests.push({type,payload});
  if(type==='HMBGetSoundUISnapshotRequest'){
    return new Promise(resolve=>soundReads.push(pending=>resolve({node_name:payload.node_name,
      altered_workflow_state:false,snapshot:pending?{}:{__hmb_sound_transport:{stream_id:'sound-fixture-stream'}}})));
  }
  if(type==='HMBManageNodeConnectionsRequest'){
    if(payload.expected_state_token!=='t'+token)throw Error('Unexpected token');
    token+=1;
    if(payload.operation==='disconnect') detached=true;
    if(payload.operation==='reconnect') detached=false;
  }else if(type!=='HMBGetNodeConnectionsRequest')throw Error('Unexpected request');
  return {node_name:payload.node_name,state_token:'t'+token,detached,can_disconnect:!detached,can_reconnect:detached,
    can_refresh:!detached,refresh_confirmed:payload.operation==='refresh',details:'',
    connections:[{kind:'wire',peer_name:'Fixture video',source_node_name:'Fixture video',target_node_name:payload.node_name,
      source_parameter_name:'out',target_parameter_name:'in',shots:[]}]};
}
const types=['HMBAgentLibrary','HMBAnalysisAgent','HMBColorLUTLibrary','HMBFinishLookLibrary','HMBImageAssetLibrary',
  'HMBImageBash','HMBImageGeneration','HMBPromptLibrary','HMBSeedanceGeneration','HMBSoundLibrary','HMBVideoPickerLibrary'];
const h=Y.createElement;
function Widget({type,kind}){
  const ref=Y.useRef(null);
  Y.useLayoutEffect(()=>{
    const element=ref.current;
    const state=event=>{element.dataset.mode=event.detail.active?'integrated':'fallback'};
    element.addEventListener('hmb-color-lut-header-state',state);
    document.dispatchEvent(new CustomEvent('hmb-color-lut-header-ready',{detail:{container:element}}));
    return ()=>{document.dispatchEvent(new CustomEvent('hmb-color-lut-header-retire',{detail:{container:element}}));
      element.removeEventListener('hmb-color-lut-header-state',state);};
  },[]);
  return h('div',{ref,'data-hmb-color-lut-widget':'','data-hmb-native-node-type':type,'data-kind':kind,
    style:kind==='measurement'?{opacity:0}:{}},
    h('header',null,h('span',{'data-hmb-native-identity':''}),h('span',{'data-hmb-native-actions':''}),
      h('span',{'data-widget-tools':''},'Source controls')));
}
function Header({type,library,collapsed}){
  const ref=Y.useRef(null), slots=hmbUse130IntegratedHeader(ref,type,type,library,collapsed);
  return hmb130IntegratedHeader(slots,h('div',{ref,'data-stock-header':''},
    h('b',null,type),h('div',null,hmb130ConnectionIcon(type,library),...hmb130HeaderItems(type,library).map(action=>
      h('button',{key:action,onClick:()=>action==='reset'&&hmb130RefreshConnections(type)},action)))));
}
function App(){
  const [folded,setFolded]=Y.useState(false),[generation,setGeneration]=Y.useState(0);
  window.setFolded=setFolded;window.remount=()=>setGeneration(value=>value+1);
  return h(Y.Fragment,null,hmbUseNativeConnectionManager(),...types.map(type=>
    h('div',{key:type,className:'react-flow__node','data-id':type},h(Header,{type,library:'HMB_GP_Production',collapsed:folded}),
      h(Widget,{type,kind:'measurement'}),!folded&&h('div',{key:generation,'data-visible-wrapper':'',
        style:type==='HMBPromptLibrary'&&generation===0?{opacity:0}:{}},h(Widget,{type,kind:'visible'})))),
    h('div',{className:'react-flow__node','data-id':'Standard'},h(Header,{type:'Standard',library:'Elsewhere'})));
}
w.createRoot(document.querySelector('#app')).render(h(App));
`;

const module = [runtime, '(()=>{', candidate.slice(helperStart, helperEnd), fixture, '})();'].join('\n');
const browser = await nativeTestPlaywright().chromium.launch({headless:true, executablePath:nativeTestBrowserPath()});
try {
  const page = await browser.newPage();
  const errors=[];
  page.on('pageerror', error=>{ errors.push(error.message); console.error(error.stack); });
  page.on('console', message=>{ if (message.type()==='error') console.error(message.text()); });
  page.on('requestfailed', request=>console.error(request.failure()?.errorText,request.url()));
  await page.route('**/*', route => {
    const url=new URL(route.request().url());
    if(url.origin!=='http://hmb-header.test') return route.abort();
    const dependency=dependencies.get(url.pathname.slice(1));
    if(dependency) return route.fulfill({contentType:'text/javascript',body:dependency});
    return url.pathname==='/fixture.js'
      ? route.fulfill({contentType:'text/javascript',body:module})
      : route.fulfill({contentType:'text/html',body:'<!doctype html><div id="app"></div><script type="module" src="/fixture.js"></script>'});
  });
  await page.goto('http://hmb-header.test/');
  await page.waitForFunction(()=>document.querySelectorAll('[data-hmb-0130-integrated-header]').length===10);
  const delayed = page.locator('[data-id="HMBPromptLibrary"]');
  assert.equal(await delayed.locator('[data-stock-header]:visible').count(),1);
  await delayed.locator('[data-visible-wrapper]').evaluate(wrapper=>{wrapper.style.opacity='1';});
  try {
    await page.waitForFunction(()=>document.querySelectorAll('[data-hmb-0130-integrated-header]').length===11, undefined, {timeout:5000});
  } catch (error) {
    console.error(await page.locator('#app').evaluate(node=>node.innerHTML.slice(0,3000)));
    throw error;
  }
  assert.equal(await page.locator('[data-kind="measurement"] [data-hmb-connection-manager-button]').count(),0);
  assert.equal(await page.locator('[data-stock-header]:visible').count(),1);
  // The Editor can recycle the slot elements in place. The header must
  // return to the native surface while the slot contract is incomplete.
  const promptIdentity=delayed.locator('[data-kind="visible"] [data-hmb-native-identity]');
  await promptIdentity.evaluate(slot=>slot.removeAttribute('data-hmb-native-identity'));
  await delayed.locator('[data-stock-header]:visible').waitFor({timeout:2500});
  await delayed.locator('[data-kind="visible"] header > span').first().evaluate(slot=>slot.setAttribute('data-hmb-native-identity',''));
  await delayed.locator('[data-kind="visible"] [data-hmb-connection-manager-button]').waitFor();
  assert.equal(await delayed.locator('[data-stock-header]:visible').count(),0);
  const agent=page.locator('[data-id="HMBAgentLibrary"]');
  await agent.locator('[data-kind="visible"] [data-hmb-connection-manager-button]').click();
  const dialog=page.getByRole('dialog');
  await dialog.getByText('Fixture video',{exact:true}).waitFor();
  await dialog.getByRole('button',{name:'연결 해제',exact:true}).click();
  await dialog.getByText('연결 해제됨 · 샷과 결과 보존').waitFor();
  await dialog.getByRole('button',{name:'다시 연결',exact:true}).click();
  await dialog.getByText('현재 연결 상태').waitFor();
  await dialog.getByRole('button',{name:'연결 관리 닫기',exact:true}).click();
  await agent.getByRole('button',{name:'reset',exact:true}).click();
  await page.waitForFunction(()=>requests.some(row=>row.payload.operation==='refresh'));
  const ops=await page.evaluate(()=>requests.filter(row=>row.type==='HMBManageNodeConnectionsRequest').map(row=>row.payload.operation));
  assert.deepEqual(ops,['disconnect','reconnect','refresh']);
  const sound=page.locator('[data-id="HMBSoundLibrary"] [data-kind="visible"]');
  const requestSound=()=>sound.evaluate(container=>{
    window.soundReplies??=0;
    container.dispatchEvent(new CustomEvent('hmb-sound-read-snapshot',{detail:{
      expectedStreamId:'sound-fixture-stream',receive:()=>window.soundReplies++,
    }}));
  });
  await requestSound();
  assert.equal(await page.evaluate(()=>soundReads.length),0,'No read before the editor canvas has a scope');
  const scope={workflow_name:'saved-fixture',flow_name:'fixture-flow'};
  await page.evaluate(value=>{soundScope=value;},scope);
  for(let attempt=0;attempt<2;attempt++){
    await requestSound();
    await page.evaluate(()=>soundReads.shift()(true));
  }
  assert.equal(await page.evaluate(()=>soundReplies),0,'Pending reads cannot replace the Sound UI');
  await requestSound();
  await page.evaluate(()=>soundReads.shift()());
  await page.waitForFunction(()=>soundReplies===1);
  assert.deepEqual(await page.evaluate(()=>requests.findLast(row=>row.type==='HMBGetSoundUISnapshotRequest').payload),
    {...scope,node_name:'HMBSoundLibrary',expected_stream_id:'sound-fixture-stream'});
  await requestSound();
  await page.evaluate(()=>{soundScope={...soundScope,flow_name:'another-flow'};soundReads.shift()();});
  assert.equal(await page.evaluate(()=>soundReplies),1,'Retired flow cannot restore Sound UI');
  await requestSound();
  await page.evaluate(()=>{soundSession='new-session';soundReads.shift()();});
  assert.equal(await page.evaluate(()=>soundReplies),1,'Retired session cannot restore Sound UI');
  assert.equal(await page.locator('[data-id="HMBImageAssetLibrary"]').getByRole('button',{name:'run',exact:true}).count(),0);
  await page.evaluate(()=>remount());
  await page.waitForFunction(()=>document.querySelectorAll('[data-kind="visible"][data-mode="integrated"] [data-hmb-connection-manager-button]').length===11);
  await page.evaluate(()=>setFolded(true));
  await page.waitForFunction(()=>!document.querySelector('[data-hmb-0130-integrated-header]'));
  assert.equal(await page.locator('[data-stock-header]:visible').count(),12);
  await page.evaluate(()=>setFolded(false));
  await page.waitForFunction(()=>document.querySelectorAll('[data-hmb-0130-integrated-header]').length===11);
  assert.deepEqual(errors,[]);
  if (process.env.HMB_LIFECYCLE_REPORT_DIR) {
    fs.writeFileSync(path.join(process.env.HMB_LIFECYCLE_REPORT_DIR,'header-0130.json'), JSON.stringify({
      passed:true, editor_source_sha256:editorSourceHash, header_sha256:sha(candidateBytes),
      integrated_headers:await page.locator('[data-hmb-0130-integrated-header]').count(),
    }, null, 2)+'\n');
  }
  console.log('11 HMB headers, delayed visibility, remount/fold, link dialog, reconnect and safe refresh: PASS');
} finally { await browser.close(); }
