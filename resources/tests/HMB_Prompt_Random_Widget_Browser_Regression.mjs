// Seeded real-Chromium UI diagnostic. No desktop graph, SDK engine or provider.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const source=fs.readFileSync(path.join(root,'widgets/HMBPromptLibraryScopedBindingWidget.js'),'utf8');
const out=path.join(root,'reports/release-readiness-local804-20261016/widget-random');
fs.mkdirSync(out,{recursive:true});
const label=process.env.HMB_RANDOM_WIDGET_LABEL||'r1';assert.match(label,/^[A-Za-z0-9-]+$/);
const output=path.join(out,label+'.json');assert.equal(fs.existsSync(output),false);
const server=http.createServer((req,res)=>{
  if(req.url==='/widget.js'){res.setHeader('Content-Type','text/javascript; charset=utf-8');res.end(source);}
  else{res.setHeader('Content-Type','text/html; charset=utf-8');res.end('<!doctype html><meta charset="utf-8"><div class="react-flow__node" id="shell" style="height:1350px;width:1800px"><div style="height:96px">Synthetic SDK header</div><div id="host"></div></div>');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
const receipt={schema:'hmb-prompt-seeded-widget-stress-v1',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),profiles:[],external_requests:0,live_graph_requests:0,paid_submissions:0};
let failure;
try{
 for(const count of [4,50]){
  const page=await browser.newPage({viewport:{width:1900,height:1500}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{if(new URL(route.request().url()).hostname!=='127.0.0.1'){receipt.external_requests++;return route.abort();}return route.continue();});
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const profiler=await page.context().newCDPSession(page);
  await profiler.send('Profiler.enable');await profiler.send('Profiler.setSamplingInterval',{interval:1000});await profiler.send('Profiler.start');
  const result=await page.evaluate(async({count})=>{
   const widget=await import('/widget.js');
   const channel='11111111-1111-4111-8111-111111111111';
   const shots=Array.from({length:5},(_,index)=>({channel_uuid:channel,shot_uuid:`22222222-2222-4222-8222-${String(index+1).padStart(12,'0')}`,number:index+1,name:`Authored asset ${index+1}`,selected_source_uids:[]}));
   const images=n=>Array.from({length:count},(_,index)=>{const uid=`project:shot-${n}-image-${index}`;return {slot:index+1,present:true,label:`Actor ${n}/${index}`,asset_source_uid:uid,asset_library_id:uid,asset_source_kind:'project',asset_managed:true,asset_verified:true,image_main_type:'Character',image_sub_type:'Full Appearance',owner:`Literal Target ${n}/${index}`,color_picks:[index%2?'Green':'Red'],binding_video_slots:[1]};});
   shots.forEach(row=>row.selected_source_uids=images(row.number).map(image=>image.asset_source_uid));
   const videos=Array.from({length:10},(_,index)=>({slot:index+1,present:true,label:`Reference ${index}`,manual:true}));
   let latest=widget.normalizeState({multi_shot_enabled:true,shot:shots[0],images:images(1),videos,source_sync_revision:1,ui_edit_revision:0,
     image_asset:{enabled:true,project_id:'superwings12',selected_assets:count,order_managed:true,ordered_source_uids:shots[0].selected_source_uids,shot_catalog:shots,shot_catalog_routing:{publisher_instance_uuid:channel,channel_uuid:channel,generation:1,metadata_sha256:'a'.repeat(64)}}});
   const textKey=Object.keys(latest.text)[0];
   for(const shot of shots){widget.hmbSwitchPromptShot(latest,shot.shot_uuid);latest.images=images(shot.number);latest.videos=structuredClone(videos);latest.text[textKey]=`Shot ${shot.number} 한글 {literal} OFF 0`;widget.hmbStorePromptShotDocument(latest);}
   widget.hmbSwitchPromptShot(latest,shots[0].shot_uuid);
   const host=document.querySelector('#host');let controller,publications=0,publishedBytes=0;
   const props=value=>({value:JSON.stringify(value),disabled:false,onChange(next){publications++;publishedBytes+=new TextEncoder().encode(next).length;latest=JSON.parse(next);controller.update(props(latest));}});
   const mountStart=performance.now();controller=widget.default(host,props(latest));
   const initialMountMs=performance.now()-mountStart;
   const frames=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   await frames();
   const longTasks=[];let observer;
   if(PerformanceObserver.supportedEntryTypes.includes('longtask')){observer=new PerformanceObserver(list=>longTasks.push(...list.getEntries().map(entry=>({start:entry.startTime,duration:entry.duration}))));observer.observe({type:'longtask'});}
   const timings=[],checks=[],start=performance.now();let random=0x734a2f61;
   const rnd=()=>{random=(Math.imul(random,1664525)+1013904223)>>>0;return random/4294967296;};
   const inspect=()=>{
    const rows=[...host.querySelectorAll('.source-row.image .source-label-input')].map(input=>input.value);
    if(JSON.stringify(rows)!==JSON.stringify(latest.images.map(image=>image.label)))throw Error('Source rows do not match selected UUID');
    if(host.querySelectorAll('.center').length!==1||host.querySelectorAll('[data-group-id]').length!==4)throw Error('Duplicate or missing editor sections');
    if(host.querySelector('[data-text-key="'+textKey+'"]')?.value!==latest.text[textKey])throw Error('Literal text/cross-shot ownership lost');
   };
   inspect();
   for(let index=0;index<60;index++){
    const previous=structuredClone(latest);let target=shots[Math.floor(rnd()*5)];
    if(target.shot_uuid===latest.shot.shot_uuid)target=shots[(target.number)%5];
    const clickStart=performance.now();host.querySelector('[data-prompt-shot="'+target.shot_uuid+'"]').click();
    const clickReturnMs=performance.now()-clickStart;
    await frames();
    let spins=0;while(latest.shot.shot_uuid!==target.shot_uuid&&spins++<30)await frames();
    if(latest.shot.shot_uuid!==target.shot_uuid)throw Error('Tab never acknowledged');
    timings.push({kind:'tab',click_return_ms:clickReturnMs,settle_ms:performance.now()-clickStart});inspect();
    if(index%4===0){
     const next=structuredClone(latest);next.images.reverse();next.images.forEach((image,i)=>image.slot=i+1);
     next.source_sync_revision++;next.image_asset.shot_catalog_routing.generation++;next.image_asset.shot_catalog_routing.metadata_sha256=String(next.source_sync_revision).padStart(64,'a');
     next.image_asset.ordered_source_uids=next.images.map(image=>image.asset_source_uid);next.shot.selected_source_uids=[...next.image_asset.ordered_source_uids];
     const sourceStart=performance.now();latest=widget.normalizeState(next);controller.update(props(latest));await frames();
     timings.push({kind:'source_reorder',settle_ms:performance.now()-sourceStart});inspect();
    }
    if(index%6===0){previous.source_sync_revision=0;previous.ui_edit_revision=0;previous.images=[];controller.update(props(previous));await frames();inspect();checks.push('stale_echo_rejected');}
    if(index%10===0){const remountStart=performance.now();controller.cleanup();controller=widget.default(host,props(latest));await frames();timings.push({kind:'cleanup_remount',settle_ms:performance.now()-remountStart});inspect();checks.push('cleanup_remount');}
   }
   await frames();observer?.disconnect();
   const percentile=values=>{values=[...values].sort((a,b)=>a-b);const at=p=>values[Math.min(values.length-1,Math.round((values.length-1)*p))];return {count:values.length,p50:at(.5),p95:at(.95),max:at(1)};};
   const body=host.querySelector('.center');const before=[body,...host.querySelectorAll('.source-row.image')];
   const noOpStart=performance.now();for(let index=0;index<100;index++)controller.update(props(latest));const noOpMs=performance.now()-noOpStart;
   if(before[0]!==host.querySelector('.center')||before.some(node=>!node.isConnected))throw Error('Same-state update remounted live controls');
   const stats={selected_images_per_shot:count,shots:5,reference_videos_per_shot:10,seed:'0x734a2f61',random_tabs:60,
     source_reorders:15,cleanup_remounts:checks.filter(value=>value==='cleanup_remount').length,stale_echoes:checks.filter(value=>value==='stale_echo_rejected').length,
     initial_mount_ms:initialMountMs,tab_click_ms:percentile(timings.filter(row=>row.kind==='tab').map(row=>row.click_return_ms)),
     tab_settle_ms:percentile(timings.filter(row=>row.kind==='tab').map(row=>row.settle_ms)),source_reorder_ms:percentile(timings.filter(row=>row.kind==='source_reorder').map(row=>row.settle_ms)),
     cleanup_remount_ms:percentile(timings.filter(row=>row.kind==='cleanup_remount').map(row=>row.settle_ms)),
     same_state_updates_100_ms:noOpMs,publications,published_bytes_total:publishedBytes,full_state_bytes:new TextEncoder().encode(JSON.stringify(latest)).length,
     long_tasks:longTasks.filter(row=>row.start>=start),total_seconds:(performance.now()-start)/1000,passed:true};
   controller.cleanup();await frames();if(host.querySelector('.center'))throw Error('Cleanup left an editor behind');
   return stats;
  },{count});
  const {profile}=await profiler.send('Profiler.stop');await profiler.detach();
  const cpuFile=path.join(out,`${label}-cpu-${count}.json`);fs.writeFileSync(cpuFile,JSON.stringify(profile));
  const sampled=new Map(),nodes=new Map(profile.nodes.map(node=>[node.id,node]));
  for(let index=0;index<(profile.samples||[]).length;index++)sampled.set(profile.samples[index],(sampled.get(profile.samples[index])||0)+(profile.timeDeltas?.[index]||0));
  result.cpu_self_ms=[...sampled].map(([id,microseconds])=>{const frame=nodes.get(id)?.callFrame||{};return {function:frame.functionName||'(anonymous)',module:frame.url?.includes('/widget.js')?'Prompt widget':frame.url?'browser fixture':'runtime',line:(frame.lineNumber??-1)+1,self_ms:Math.round(microseconds/100)/10};}).sort((a,b)=>b.self_ms-a.self_ms).slice(0,30);
  result.cpu_profile_sha256=crypto.createHash('sha256').update(fs.readFileSync(cpuFile)).digest('hex');
  result.cpu_profile_file=cpuFile;result.cpu_sampling_enabled=true;
  assert.deepEqual(errors,[]);receipt.profiles.push(result);await page.close();
 }
 assert.equal(receipt.external_requests,0);receipt.passed=true;
}catch(error){receipt.passed=false;receipt.failure=String(error.stack||error);failure=error;}
finally{
 await browser.close();await new Promise(resolve=>server.close(resolve));
 receipt.source_stable=receipt.source_sha256===crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'widgets/HMBPromptLibraryScopedBindingWidget.js'))).digest('hex');
 receipt.passed=Boolean(receipt.passed&&receipt.source_stable);
 receipt.limits=['Actual Chromium and actual Prompt widget with synthetic Source/SDK-shaped callbacks; SDK integration is validated separately.',
   '4-image and 50-image profiles share machine resources with other offline audits. Timings are diagnostic, not a universal latency guarantee.',
   'No real reference media are uploaded; reference rows here exercise UI state only.'];
 fs.writeFileSync(output,JSON.stringify(receipt,null,2)+'\n');
 console.log(JSON.stringify({passed:receipt.passed,profiles:receipt.profiles.map(profile=>({images:profile.selected_images_per_shot,tab_p95_ms:profile.tab_settle_ms.p95,click_p95_ms:profile.tab_click_ms.p95,full_state_bytes:profile.full_state_bytes,long_tasks:profile.long_tasks.length})),report:output}));
}
if(failure)throw failure;
assert.equal(receipt.passed,true);
