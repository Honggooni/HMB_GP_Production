// Exact supported React/ReactDOM plus the current connection-manager helper.
// All graph/transport state is synthetic; no live editor or provider is used.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import {readNativeEditorSource,nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const original=readNativeEditorSource(root);
const helper=fs.readFileSync(path.join(root,'resources/editor/hmb-color-lut-native-header.js'),'utf8');
const alias=original.indexOf('S=u(p(),1),C=h(),w=x(),T=u(y())');
const runtime=original.slice(0,original.indexOf(',E=`modulepreload`',alias))+';';
const jsxStart=original.indexOf('var Wn=s('),jsxEnd=original.indexOf('function Gn(',jsxStart);
const app=String.raw`
window.calls=[];window.dirty=0;window.inventory=new Map();window.failGet=false;
window.commitTimeout=false;window.holdGet=false;window.held=[];window.hidden=false;
Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.hidden?'hidden':'visible'});
var kq={getState:()=>({setDirty:value=>{if(value)window.dirty++}})},vg=error=>error?.message||String(error);
const initial=(name,allowed=true)=>({node_name:name,detached:false,state_token:'token-'+name,
can_disconnect:allowed,can_reconnect:false,can_forget_missing:false,
details:allowed?'현재 연결 상태':'연결된 툴의 실행을 마치고 편집 잠금을 해제하세요.',
connections:[{kind:'wire',peer_name:'Retained Generator',source_node_name:name,target_node_name:'Retained Generator',
source_parameter_name:'output',target_parameter_name:'prompt',shots:[]}]});
window.seed=(name,allowed=true)=>window.inventory.set(name,initial(name,allowed));
var Xd={request:async(type,payload,options)=>{
window.calls.push({type,payload:structuredClone(payload),options:structuredClone(options)});
if(type==='HMBGetNodeConnectionsRequest'){
 if(window.holdGet){window.holdGet=false;await new Promise(resolve=>window.held.push(resolve))}
 if(window.failGet){window.failGet=false;throw Error('Request timed out after 10000ms')}
 return structuredClone(window.inventory.get(payload.node_name));
}
if(type!=='HMBManageNodeConnectionsRequest')throw Error('Unexpected fixture request '+type);
const previous=window.inventory.get(payload.node_name);
if(payload.expected_state_token!==previous.state_token)throw Error('Stale fixture token');
if(payload.operation==='disconnect')window.inventory.set(payload.node_name,{...previous,detached:true,
state_token:previous.state_token+'-detached',can_disconnect:false,can_reconnect:true,details:'연결 해제됨'});
else if(payload.operation==='reconnect')window.inventory.set(payload.node_name,initial(payload.node_name));
if(window.commitTimeout){window.commitTimeout=false;await new Promise(resolve=>setTimeout(resolve,window.timeoutDelay||20));throw Error('Request timed out after 10000ms')}
return structuredClone(window.inventory.get(payload.node_name));
}};
function Shell(){return hmbUseNativeConnectionManager()}
window.root=w.createRoot(document.getElementById('app'));window.root.render((0,R.jsx)(Shell,{}));
window.open=hmbNativeOpenConnections;window.reset=hmbNativeStudioResetCollapseIntents;
window.testReady=true;
`;
const module=runtime+'\n'+original.slice(jsxStart,jsxEnd)+'\n'+helper+'\n'+app;
const html='<!doctype html><meta charset="utf-8"><title>Private connection readiness</title><div id="app"></div><script type="module" src="/fixture.js"></script>';
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/fixture.js'?'text/javascript':'text/html');res.end(req.url==='/fixture.js'?module:html)});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser,checks=0;
try{
 const {chromium}=nativeTestPlaywright();
 browser=await chromium.launch({executablePath:nativeTestBrowserPath(),headless:true});
 const page=await browser.newPage({viewport:{width:1200,height:900}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 await page.waitForFunction(()=>window.testReady===true);
 // Give React's mount effect a frame before dispatching the public event.
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const disconnect=()=>page.getByRole('button',{name:'연결 해제',exact:true});
 const reconnect=()=>page.getByRole('button',{name:'다시 연결',exact:true});
 const refresh=()=>page.getByRole('button',{name:'새로고침',exact:true});
 const close=()=>page.getByRole('button',{name:'연결 관리 닫기'}).click();
 const ready=()=>page.locator('[data-hmb-connection-manager] article').first().waitFor();
 const getCount=()=>page.evaluate(()=>window.calls.filter(call=>call.type==='HMBGetNodeConnectionsRequest').length);
 const manageCount=()=>page.evaluate(()=>window.calls.filter(call=>call.type==='HMBManageNodeConnectionsRequest').length);

 await page.evaluate(()=>{window.seed('Saved Agent',false);window.open('Saved Agent')});await ready();
 assert.equal(await disconnect().isDisabled(),true);checks++;
 await page.evaluate(()=>window.seed('Saved Agent',true));
 await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(button=>button.textContent==='연결 해제'&&!button.disabled),null,{timeout:4000});
 assert.equal(await manageCount(),0,'Readiness never submits a mutation');checks++;
 const readyCount=await getCount();await page.waitForTimeout(1150);
 assert.equal(await getCount(),readyCount,'A ready dialog stops checking');checks++;
 await disconnect().click();await page.locator('[data-hmb-connections-detached="true"]').waitFor();
 const detachedCount=await getCount();await page.waitForTimeout(1150);
 assert.equal(await getCount(),detachedCount,'Detached recipes never poll');checks++;
 assert.equal(await reconnect().isDisabled(),false);checks++;await close();

 await page.evaluate(()=>{window.seed('Still Running',false);window.open('Still Running')});await ready();
 const runningCount=await getCount();await page.waitForTimeout(1200);
 assert.ok(await getCount()>runningCount);checks++;
 assert.equal(await disconnect().isDisabled(),true,'An active peer is never force enabled');checks++;
 await page.evaluate(()=>{window.originalNow=Date.now;Date.now=()=>window.originalNow()+31000});
 await page.waitForTimeout(1200);const expiredCount=await getCount();await page.waitForTimeout(1150);
 assert.equal(await getCount(),expiredCount,'Disabled rechecks stop after the bounded window');checks++;
 await page.evaluate(()=>Date.now=window.originalNow);
 await close();

 await page.evaluate(()=>{window.hidden=true;window.seed('Hidden Agent',false);window.open('Hidden Agent')});await ready();
 const hiddenCount=await getCount();await page.waitForTimeout(1150);
 assert.equal(await getCount(),hiddenCount,'A hidden dialog never polls');checks++;await close();
 await page.evaluate(()=>window.hidden=false);
 await page.evaluate(()=>{window.seed('Closed Agent',false);window.open('Closed Agent')});await ready();await close();
 const closedCount=await getCount();await page.waitForTimeout(1150);
 assert.equal(await getCount(),closedCount,'Closing cancels the scheduled check');checks++;

 await page.evaluate(()=>{window.failGet=true;window.seed('Timeout Agent');window.open('Timeout Agent')});
 await page.getByRole('alert').waitFor();
 assert.equal(await refresh().isDisabled(),false,'A lost initial reply exits busy and permits explicit refresh');checks++;
 assert.equal(await disconnect().isDisabled(),true);checks++;
 await refresh().click();await ready();assert.equal(await disconnect().isDisabled(),false);checks++;await close();

 await page.evaluate(()=>{window.seed('Uncertain Agent');window.open('Uncertain Agent')});await ready();
 const mutationsBefore=await manageCount(),dirtyBefore=await page.evaluate(()=>window.dirty),readsBefore=await getCount();
 await page.evaluate(()=>window.commitTimeout=true);await disconnect().click();
 await page.waitForFunction(()=>document.querySelector('[role="alert"]')?.textContent.includes('다시 조회했습니다'));
 assert.equal(await manageCount(),mutationsBefore+1,'An uncertain mutation is submitted exactly once');checks++;
 assert.equal(await getCount(),readsBefore+1,'Only one read-only reconciliation follows timeout');checks++;
 assert.equal(await page.evaluate(()=>window.dirty),dirtyBefore+1,'A possibly committed graph remains saveable');checks++;
 assert.equal(await page.locator('[data-hmb-connections-detached="true"]').count(),1);checks++;
 assert.equal(await reconnect().isDisabled(),true,'Uncertainty requires explicit refresh before further writes');checks++;
 await refresh().click();await ready();assert.equal(await reconnect().isDisabled(),false);checks++;await close();

 await page.evaluate(()=>{window.seed('Dismissed Agent');window.open('Dismissed Agent')});await ready();
 const dismissedDirty=await page.evaluate(()=>window.dirty),dismissedMutations=await manageCount(),dismissedReads=await getCount();
 await page.evaluate(()=>{window.commitTimeout=true;window.timeoutDelay=300});await disconnect().click();await close();
 await page.waitForTimeout(450);
 assert.equal(await page.evaluate(()=>window.dirty),dismissedDirty+1,'A timed-out committed mutation remains saveable after dismissal');checks++;
 assert.equal(await manageCount(),dismissedMutations+1);checks++;
 assert.equal(await getCount(),dismissedReads,'Dismissal never starts a reconciliation or reopens its dialog');checks++;
 assert.equal(await page.locator('[data-hmb-connection-manager]').count(),0);checks++;

 await page.evaluate(()=>{window.seed('Old Flow',false);window.open('Old Flow')});await ready();
 await page.evaluate(()=>window.reset());const resetCount=await getCount();await page.waitForTimeout(1150);
 assert.equal(await getCount(),resetCount,'A flow transition cancels readiness');checks++;
 assert.equal(await page.locator('[data-hmb-connection-manager]').count(),0);checks++;
 const calls=await page.evaluate(()=>window.calls);
 assert.ok(calls.length>0&&calls.every(call=>call.options?.timeoutMs===10000),'Every connection list/manage request is bounded');checks++;
 assert.deepEqual(errors,[]);checks++;
 await page.evaluate(()=>window.root.unmount());
 console.log(JSON.stringify({status:'PASS',checks,live_editor_actions:0,paid_calls:0,
  runtime:'supported React/ReactDOM with current product helper',sdk:'synthetic protected graph and bounded request outcomes',
  auto_mutation_retries:0,actual_Desktop_verified:false}));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve))}
