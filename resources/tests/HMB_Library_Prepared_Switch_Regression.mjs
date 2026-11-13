import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const out=process.env.HMB_SWITCH_REPORT_DIR;
const before=process.env.HMB_SWITCH_BASELINE_DIR;
const results={schema:'hmb-prepared-library-switch-v1',environment:'isolated Chromium widget callbacks; not Desktop',
 metrics:{paint_ms:'First animation-frame callback observing the target selection; not compositor capture',editable_ms:'First frame observing authoring unlocked after canonical ACK',dispatch_ms:'Click to onChange callback entry'},
 synthetic_ack_ms:180,paid_calls:0,external_requests:0,runs:{}};
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try{
 for(const variant of before?['before','after']:['after']){
  const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',r=>{results.external_requests++;return r.abort();});
  await page.setContent('<div id="sound" style="width:1470px;height:710px"></div><div id="finish"></div>');
  const dir=variant==='before'?before:path.join(root,'widgets');
  await page.evaluate(async source=>{
   const m=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
   window.shots=Array.from({length:5},(_,i)=>({shot_uuid:'shot-'+(i+1),channel_uuid:'channel',number:i+1,name:'Shot '+(i+1)}));
   window.state={schema:'hmb-sound-library-ui',version:1,revision:1,project_id:'fixture',project_uid:'project',project_root:'C:/fixture',shot:shots[0],shot_catalog:{channel_uuid:'channel',shots},status:'Ready',
    assets:Array.from({length:5000},(_,i)=>({source_uid:'source-'+i,name:'Sound '+i,relative_path:'Dialogue/'+i+'.wav',role:'Dialogue',extension:'.wav'})),
    tracks:shots.map((s,i)=>({...s,source_uid:'source-'+i,instance_id:'track-'+i,name:'Sound '+i,role:'Dialogue',duration_seconds:10,in_seconds:0,out_seconds:null,gain_db:0,enabled:true}))};
   window.calls=[];window.timers=[];window.root=document.querySelector('#sound');window.mode='ack';
   window.props=()=>({value:state,onChange:value=>{
    const command=value.__hmb_sound_command;calls.push({command,at:performance.now()});
    if(mode==='reject')return Promise.reject(Error('fixture rejection'));
    if(mode==='hold')return new Promise(()=>{});
    timers.push(setTimeout(()=>{state={...state,shot:shots.find(s=>s.shot_uuid===command.shot_uuid),revision:state.revision+1,ack_command_id:command.id};controller.update(props());},180));
   }});
   window.controller=m.default(root,props());
   window.step=async id=>{
    const card=root.querySelector('[data-asset]'),audio=root.querySelector('audio'),before=calls.length,t0=performance.now();
    root.querySelector('[data-shot="'+id+'"]').click();const clickMs=performance.now()-t0;
    const painted=()=>root.querySelector('[data-shot="'+id+'"]').getAttribute('aria-pressed')==='true';
    let first=null;
    await new Promise(resolve=>{const frame=()=>{if(painted()&&first===null)first=performance.now()-t0;
      if(first!==null&&!root.querySelector('[data-shot="'+id+'"]').disabled)return resolve();requestAnimationFrame(frame);};requestAnimationFrame(frame);});
    return {click_ms:clickMs,paint_ms:first,editable_ms:performance.now()-t0,dispatch_ms:calls[before].at-t0,commands:calls.length-before,
      sameCard:card===root.querySelector('[data-asset]'),sameAudio:audio===root.querySelector('audio')};
   };
  },fs.readFileSync(path.join(dir,'HMBSoundLibraryWidget.js'),'utf8'));
  const samples=[];
  for(const id of [2,3,4,5,1,2,3,4,5,1])samples.push(await page.evaluate(id=>step('shot-'+id),id));
  assert.ok(samples.every(s=>s.commands===1&&s.sameAudio));
  if(variant==='after'){
   assert.ok(samples.every(s=>s.sameCard),'Shot switching must retain the prepared catalog cards');
   assert.ok(samples.every(s=>s.paint_ms<150),'Prepared page must paint before the delayed authority response');
   await page.evaluate(()=>{mode='hold';root.querySelector('[data-shot="shot-2"]').click();controller.update(props());});
   assert.equal(await page.locator('[data-shot="shot-2"]').getAttribute('aria-pressed'),'true','Old echo cannot rewind the pending view');
   assert.equal(await page.locator('[data-add="source-3"]').isDisabled(),true,'Prepared presentation cannot authorize an edit on an unacknowledged shot');
   assert.equal(await page.evaluate(()=>calls.at(-1).command.context.shot_uuid),'shot-1','Command context stays canonical');
   await page.evaluate(()=>{state={...state,revision:state.revision+1,shot:shots[1],ack_command_id:calls.at(-1).command.id};controller.update(props());mode='reject';root.querySelector('[data-shot="shot-3"]').click();});
   await page.waitForFunction(()=>document.querySelector('[data-shot="shot-2"]').getAttribute('aria-pressed')==='true');
   assert.match(await page.locator('.hs-status').textContent(),/SOUND_TRANSPORT_FAILED/);
   await page.evaluate(()=>{state={...state,revision:state.revision+1,assets:state.assets.map((a,i)=>i? a:{...a,name:'Updated catalog'})};controller.update(props());});
   assert.equal(await page.locator('[data-asset="source-0"] .hs-asset-name').textContent(),'Updated catalog','Catalog edits invalidate the prepared view');
   await page.evaluate(()=>{state={...state,revision:state.revision+1,shot_catalog:{...state.shot_catalog,shots:shots.slice(0,1)},shot:shots[0],tracks:[]};controller.update(props());});
   assert.equal(await page.locator('[data-shot]').count(),1,'Deleted UUIDs cannot survive prepared-view reuse');
  }
  await page.evaluate(()=>{timers.forEach(clearTimeout);controller.cleanup();});
  await page.evaluate(async source=>{
   const m=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
   const catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:'publisher',channel_uuid:'channel',generation:1,metadata_sha256:'a'.repeat(64),shots:[1,2,3,4,5].map(n=>({shot_uuid:'uuid-'+n,number:n,name:'Shot '+n,revision:0}))};
   window.value=m.hmbNormalizeFinishLookWidgetValue({shot_manager:true,shot_catalog:catalog,shot:{channel_uuid:'channel',...catalog.shots[0]}});
   window.finishCalls=[];window.finishRoot=document.querySelector('#finish');
   window.finishProps={value,onChange:next=>{finishCalls.push({at:performance.now(),next});queueMicrotask(()=>finishController.update({...finishProps,value:next}));}};
   window.finishController=m.default(finishRoot,finishProps);
  },fs.readFileSync(path.join(dir,'HMBFinishLookLibraryWidget.js'),'utf8'));
  const finish=[];
  for(const id of [2,3,4,5,1,2,3,4,5,1])finish.push(await page.evaluate(async id=>{
   await new Promise(requestAnimationFrame);const n=finishCalls.length,t0=performance.now();
   finishRoot.querySelector('[data-finish-shot="uuid-'+id+'"]').click();
   const immediate=finishRoot.querySelector('[data-finish-shot="uuid-'+id+'"]').getAttribute('aria-pressed')==='true';
   await new Promise(resolve=>{const check=()=>finishCalls.length>n?resolve():setTimeout(check,1);check();});
   return {immediate,dispatch_ms:finishCalls[n].at-t0};
  },id));
  assert.ok(finish.every(s=>s.immediate));
  await page.evaluate(()=>finishController.cleanup());assert.deepEqual(errors,[]);
  const median=(a,key)=>a.map(s=>s[key]).sort((a,b)=>a-b)[Math.floor(a.length/2)];
  results.runs[variant]={sound:{samples,median_paint_ms:median(samples,'paint_ms'),median_click_ms:median(samples,'click_ms'),median_editable_ms:median(samples,'editable_ms')},finish:{samples:finish,median_dispatch_ms:median(finish,'dispatch_ms')}};
  await page.close();
 }
 assert.equal(results.external_requests,0);results.passed=true;
 if(out){fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'prepared-switch-comparison.json'),JSON.stringify(results,null,2));}
 console.log(JSON.stringify(results));
}finally{await browser.close();}
