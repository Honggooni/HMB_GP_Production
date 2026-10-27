// Actual Asset/bridge modules; synthetic CGT replies; no SDK, account or live graph calls.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';

const root=new URL('../../',import.meta.url),require=createRequire(import.meta.url);
const playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const sources={
 '/asset.js':fs.readFileSync(new URL('widgets/HMBImageAssetLibraryWidget.js',root),'utf8'),
 '/bridge.js':fs.readFileSync(new URL('widgets/HMBImageAssetThumbnailPatchBridgeWidget.js',root),'utf8'),
};
const html=`<!doctype html><meta charset="utf-8"><style>body{background:#101420}.react-flow__node{width:1300px;position:relative}#measure{position:absolute;visibility:hidden;top:0}#footer{position:absolute;opacity:0;top:0}</style>
<article class="react-flow__node" data-id="Synthetic Asset"><section id="visible"><div id="asset"></div><div data-parameter-name="HMB_IMAGE_ASSET_THUMBNAIL_PATCH"><div id="a"></div></div></section><section id="measure"><div id="b"></div></section><section id="footer"><div id="c"></div></section></article>
<script type="module">
import asset,* as api from '/asset.js';import bridge,{hmbImageAssetThumbnailPatchBridgeRegistry as registry} from '/bridge.js';
window.registry=registry;window.handles={};window.requests=[];window.host=api.hmbNormalizeImageAssetState({});window.runtime=host.shot_routing.publisher_instance_uuid;
window.value=id=>({schema:'hmb-image-asset-thumbnail-bridge',version:1,runtime_instance_id:id||runtime,catalog_page_version:1});
const catalog={schema:'hmb-cgt-own-tasks',version:1,status:'ready',projects:[{id:'11111111-1111-4111-8111-111111111111',entity:'fixture',name:'Synthetic CGT project',database:'proj_fixture',status:'Active'}],project:null,tasks:[],can_bind:false};
window.callback=owner=>request=>{requests.push({owner,operation:request.operation,runtime:request.runtime_instance_id});if(request.operation==='cgt_catalog'){
 handles[owner.startsWith('visible')?'a':owner==='measurement'?'b':'c']?.update({value:{...request,phase:'result',state:catalog,outcome:'ready'},onChange:callback(owner)});
}};
window.mountBridge=(id,owner,runtimeId)=>{handles[id]=bridge(document.getElementById(id),{value:value(runtimeId),onChange:callback(owner)});return handles[id];};
window.assetHandle=asset(document.getElementById('asset'),{value:JSON.stringify(host),onChange(){throw Error('Unexpected authored Asset edit');}});
mountBridge('a','visible');mountBridge('b','measurement');mountBridge('c','footer');
window.send=id=>registry().get(id||runtime).dispatch({schema:'hmb-image-asset-thumbnail-bridge',operation:'cgt_cancel',phase:'request',runtime_instance_id:id||runtime,request_id:crypto.randomUUID(),session_id:crypto.randomUUID(),project_identity:''});
window.ready=true;
</script>`;
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',sources[req.url]?'text/javascript':'text/html');res.end(sources[req.url]||html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser,checks=0;
try{
 browser=await playwright.chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:')?route.continue():route.abort());
 await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.ready);
 assert.deepEqual(await page.evaluate(()=>['a','b','c'].map(id=>document.getElementById(id).getBoundingClientRect().height)),[0,0,0],'Transport mounts without a visible widget height');checks++;
 assert.equal(await page.evaluate(()=>['a','b','c'].some(id=>document.getElementById(id).querySelector('button,input,select,textarea,.react-flow__handle'))),false,'Transport exposes no authoring controls or connection handles');checks++;
 assert.equal(await page.evaluate(()=>registry().get(runtime).bridgeOwners.size),3);checks++;
 await page.locator('[data-shot-add]').click();await page.waitForFunction(()=>document.querySelector('[data-hier-cgt-project] option')?.textContent==='프로젝트 선택 필요');
 await page.waitForFunction(()=>document.querySelector('[data-hier-cgt-project]')?.textContent.includes('Synthetic CGT project'));
 assert.equal(await page.evaluate(()=>requests.filter(row=>row.operation==='cgt_catalog').at(-1).owner),'visible');checks++;
 const beforeCleanup=await page.evaluate(()=>requests.length);
 await page.evaluate(()=>{handles.c.cleanup();handles.b.cleanup();});
 assert.equal(await page.evaluate(()=>requests.length),beforeCleanup,'Owner cleanup restores transport without scheduling new host work');checks++;
 assert.equal(await page.evaluate(()=>typeof registry().get(runtime)?.dispatch),'function');checks++;
 assert.equal(await page.evaluate(()=>registry().get(runtime).bridgeOwners.size),1);checks++;
 await page.locator('[data-hier-cgt-refresh]').click();await page.waitForFunction(()=>requests.filter(row=>row.operation==='cgt_catalog').length===2);
 assert.equal(await page.evaluate(()=>requests.at(-1).owner),'visible');checks++;
 assert.equal(await page.locator('[data-hier-cgt-status]').innerText(),'CGT 프로젝트를 선택하세요.');checks++;
 await page.evaluate(()=>{handles.a.update({value:value(),onChange:callback('visible-latest')});});
 await page.locator('[data-hier-cgt-refresh]').click();await page.waitForFunction(()=>requests.filter(row=>row.operation==='cgt_catalog').length===3);
 assert.equal(await page.evaluate(()=>requests.at(-1).owner),'visible-latest');checks++;
 await page.evaluate(()=>{mountBridge('b','measurement');document.getElementById('visible').style.opacity='0';document.getElementById('measure').style.visibility='visible';send();});
 assert.equal(await page.evaluate(()=>requests.at(-1).owner),'measurement','Dispatch rechecks current visibility without an observer/timer or stale owner callback');checks++;
 await page.evaluate(()=>{document.getElementById('visible').style.opacity='1';document.getElementById('measure').style.visibility='hidden';send();});
 assert.equal(await page.evaluate(()=>requests.at(-1).owner),'visible-latest');checks++;
 await page.evaluate(()=>{window.retired=registry().get(runtime).dispatch;handles.a.cleanup();send();});
 assert.equal(await page.evaluate(()=>requests.at(-1).owner),'measurement','A hidden surviving SDK carrier remains usable after visible teardown');checks++;
 const stale=await page.evaluate(()=>{handles.b.cleanup();try{retired({});return false;}catch{return true;}});
 assert.equal(stale,true);checks++;
 const remount=await page.evaluate(()=>{mountBridge('a','visible');try{retired({});return false;}catch{return true;}});
 assert.equal(remount,true,'A retired group cannot route commands into a replacement group');checks++;
 const moved=await page.evaluate(()=>{window.old=registry().get(runtime).dispatch;handles.a.update({value:value('SYNTHETIC-NEW-RUNTIME'),onChange:callback('visible-latest')});let blocked=false;try{old({});}catch{blocked=true;}return {blocked,oldDispatch:typeof registry().get(runtime)?.dispatch,newDispatch:typeof registry().get('SYNTHETIC-NEW-RUNTIME')?.dispatch};});
 assert.deepEqual(moved,{blocked:true,oldDispatch:'undefined',newDispatch:'function'});checks+=3;
 const mismatch=await page.evaluate(()=>{const before=requests.length;try{send(runtime);}catch{};const wrong={operation:'cgt_catalog',runtime_instance_id:runtime,request_id:crypto.randomUUID(),session_id:crypto.randomUUID()};let blocked=false;try{registry().get('SYNTHETIC-NEW-RUNTIME').dispatch(wrong);}catch{blocked=true;}return {blocked,noCallback:requests.length===before};});
 assert.deepEqual(mismatch,{blocked:true,noCallback:true});checks+=2;
 await page.evaluate(()=>{handles.a.cleanup();assetHandle.cleanup();});
 assert.equal(await page.evaluate(()=>Array.from(registry().values()).some(entry=>entry.dispatch)),false);checks++;
 assert.deepEqual(errors,[]);checks++;
 console.log(JSON.stringify({test:'HMB_Image_Asset_Thumbnail_Bridge_Owner_Regression',status:'PASS',checks,scope:'Actual Asset CGT dialog and bridge modules in isolated Chrome; no SDK/app/account/server calls',external_calls:0,paid_calls:0}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
