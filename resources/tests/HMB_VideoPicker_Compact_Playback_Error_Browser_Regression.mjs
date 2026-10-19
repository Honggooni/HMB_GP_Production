import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';

const require=createRequire(import.meta.url);
let playwright;
try {playwright=require('playwright');}
catch {try {playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
  catch {if(process.env.HMB_PICKER_REQUIRE_BROWSER==='1')throw new Error('Playwright required');console.log('Picker compact playback error: SKIP (Playwright unavailable)');process.exit(0);}}
const executablePath=process.env.HMB_PICKER_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
if(!fs.existsSync(executablePath)){if(process.env.HMB_PICKER_REQUIRE_BROWSER==='1')throw new Error('Browser required');console.log('Picker compact playback error: SKIP (browser unavailable)');process.exit(0);}
const source=fs.readFileSync(process.env.HMB_PICKER_TEST_WIDGET||new URL('../../widgets/HMBVideoPickerLibraryWidget_v032.js',import.meta.url),'utf8');
const html=`<!doctype html><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0}#root{width:1600px;min-height:600px}</style><div id="root"></div><script type="module">
import mount,* as api from '/widget.js';window.api=api;window.root=document.getElementById('root');window.publications=[];window.loads=new WeakMap();
const load=HTMLMediaElement.prototype.load;HTMLMediaElement.prototype.load=function(){window.loads.set(this,(window.loads.get(this)||0)+1);return load.call(this);};
window.consoleErrors=0;const error=console.error.bind(console);console.error=(...args)=>{window.consoleErrors++;error(...args);};
window.events=[];for(const name of ['loadstart','error','play','playing','pause','loadeddata','canplay'])document.addEventListener(name,e=>{if(e.target.tagName==='VIDEO')window.events.push({name,uid:e.target.getAttribute('data-video-uid'),error:e.target.error?.code||null,paused:e.target.paused,time:e.target.currentTime,intent:window.root.__hmbVideoPickerPlaybackIntent?.uid||''});},true);
window.mountState=value=>window.controller=mount(window.root,{value,onChange:v=>window.publications.push(structuredClone(v))});window.ready=true;
</script>`;
let fixtureBytes=Buffer.alloc(0),allowA=false;const mediaRequests=[];
const server=http.createServer((request,response)=>{
  const url=new URL(request.url,'http://127.0.0.1');response.setHeader('Cache-Control','no-store');
  if(url.pathname==='/widget.js'){response.setHeader('Content-Type','text/javascript; charset=utf-8');response.end(source);return;}
  if(url.pathname.endsWith('.webm')){
    const unavailable=url.pathname==='/a.webm'&&!allowA||url.pathname==='/b.webm';
    const bytes=unavailable?Buffer.from('temporarily unavailable media'):fixtureBytes;
    mediaRequests.push({path:url.pathname,allowA,size:bytes.length,range:request.headers.range||''});
    if(unavailable){response.statusCode=503;response.setHeader('Content-Type','text/plain');response.end(bytes);return;}
    response.setHeader('Content-Type','video/webm');response.setHeader('Accept-Ranges','bytes');
    const range=/^bytes=(\d+)-(\d*)$/.exec(request.headers.range||''),start=range?Number(range[1]):0,end=range&&range[2]?Math.min(bytes.length-1,Number(range[2])):bytes.length-1;
    if(start>end){response.statusCode=416;response.end();return;}
    if(range){response.statusCode=206;response.setHeader('Content-Range',`bytes ${start}-${end}/${bytes.length}`);}response.setHeader('Content-Length',end-start+1);response.end(bytes.subarray(start,end+1));return;
  }
  response.setHeader('Content-Type','text/html; charset=utf-8');response.end(html);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser,page;
try {
  browser=await playwright.chromium.launch({executablePath,headless:true});
  page=await browser.newPage({viewport:{width:1700,height:1000}});const origin=`http://127.0.0.1:${server.address().port}`;
  const errors=[],external=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():(external.push(route.request().url()),route.abort()));
  page.setDefaultTimeout(10000);await page.goto(origin);await page.waitForFunction(()=>window.ready);
  // A short video is recorded entirely in memory. This test does not convert,
  // copy or write any user's media, and needs no FFmpeg/provider connection.
  fixtureBytes=Buffer.from(await page.evaluate(async()=>{
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const ctx=canvas.getContext('2d'),stream=canvas.captureStream(12),chunks=[];
    const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8'});recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
    const complete=new Promise(resolve=>recorder.onstop=async()=>resolve(Array.from(new Uint8Array(await new Blob(chunks,{type:'video/webm'}).arrayBuffer()))));
    recorder.start();let frame=0;const timer=setInterval(()=>{ctx.fillStyle=frame++%2?'#f36':'#3c8';ctx.fillRect(0,0,160,90);},50);
    await new Promise(resolve=>setTimeout(resolve,550));clearInterval(timer);recorder.stop();stream.getTracks().forEach(t=>t.stop());return complete;
  }));assert.ok(fixtureBytes.length>100);
  await page.evaluate(async origin=>{const video=document.createElement('video');video.muted=true;document.body.append(video);try{await new Promise((resolve,reject)=>{video.addEventListener('loadeddata',resolve,{once:true});video.addEventListener('error',()=>reject(new Error('Memory-only fixture failed to decode: '+video.error?.message)),{once:true});video.src=origin+'/c.webm';video.load();});}finally{video.pause();video.removeAttribute('src');video.load();video.remove();}},origin);
  const shot='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  const value={runtime_instance_id:'compact-error-browser',language:'en',state_revision:1,state_writer:'python',active_picker_shot_uuid:shot,shot_uuid:shot,preview_video_uid:'a',selected_video_uid:'a',viewport_mode:'video',
    picker_shots:[{workspace_uuid:shot,name:'Error retry',number:1,video_asset_uids:['a','b','c'],selected_video_uids:['a'],preview_video_uid:'a'}],
    videos:['a','b','c'].map(id=>({video_uid:id,source_uid:id,video_path:`C:/fixture/${id}.webm`,video_url:origin+`/${id}.webm`,label:id,picker_shot_uuid:shot,frame_count:8,source_fps:12}))};
  await page.evaluate(value=>window.mountState(value),value);await page.waitForFunction(()=>window.root.querySelector('.hmbvp'));
  if(await page.evaluate(()=>window.root.__hmbVideoPickerExpanded===true))await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
  const geometry=await page.locator('[data-video-uid="a"]').first().evaluate(el=>({width:el.offsetWidth,height:el.offsetHeight,border:getComputedStyle(el).borderColor,background:getComputedStyle(el).backgroundColor}));
  await page.locator('[data-play-video-uid="a"]').click();
  await page.waitForFunction(()=>window.root.__hmbCompactSharedVideoPlayer?.error?.code===4);
  await page.locator('[data-compact-preview-load-status="a"]').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-compact-preview-load-status]').count(),1);
  assert.equal(await page.locator('[data-compact-preview-load-status="a"]').getAttribute('role'),'alert');
  assert.equal(await page.locator('[data-retry-compact-video-uid="a"]').innerText(),'Retry');
  assert.equal(await page.locator('[data-play-video-uid="a"]').getAttribute('aria-pressed'),'false');
  assert.deepEqual(await page.locator('[data-video-uid="a"]').first().evaluate(el=>({width:el.offsetWidth,height:el.offsetHeight,border:getComputedStyle(el).borderColor,background:getComputedStyle(el).backgroundColor})),geometry,'Error feedback preserves the existing card geometry/palette.');
  await page.evaluate(()=>{window.failedStatus=window.root.__hmbCompactPlaybackFailure.status;window.ownedMedia=window.root.__hmbCompactSharedVideoPlayer;window.retryLoads=window.loads.get(window.ownedMedia)||0;});
  // Two native failure signals for the same owner retain one stable alert.
  assert.equal(await page.evaluate(origin=>window.api.hmbShowVideoPickerCompactPlaybackFailure(window.root,window.ownedMedia,{uid:'a',url:origin+'/a.webm'},'Duplicate error'),origin),true);
  assert.ok(await page.evaluate(()=>window.root.__hmbCompactPlaybackFailure.status===window.failedStatus));
  const settledFailure=await page.evaluate(()=>({publications:window.publications.length,loads:window.loads.get(window.ownedMedia),logs:window.consoleErrors}));
  await page.waitForTimeout(160);
  assert.deepEqual(await page.evaluate(()=>({publications:window.publications.length,loads:window.loads.get(window.ownedMedia),logs:window.consoleErrors})),settledFailure,'An error must not cause a publication, reload or error-log loop.');
  allowA=true;
  await page.locator('[data-retry-compact-video-uid="a"]').click();
  await page.waitForFunction(()=>{const v=window.root.__hmbCompactSharedVideoPlayer;return v&&!v.error&&!v.paused&&v.currentTime>.1&&v.readyState>=2;});
  assert.equal(await page.locator('[data-compact-preview-load-status]').count(),0);
  assert.equal(await page.evaluate(()=>window.loads.get(window.ownedMedia)-window.retryLoads),1,'One explicit retry reloads the unchanged source exactly once.');
  await page.locator('[data-play-video-uid="b"]').click();await page.locator('[data-compact-preview-load-status="b"]').waitFor({state:'visible'});
  await page.evaluate(()=>window.bStatus=window.root.__hmbCompactPlaybackFailure.status);
  assert.equal(await page.evaluate(origin=>window.api.hmbShowVideoPickerCompactPlaybackFailure(window.root,window.ownedMedia,{uid:'a',url:origin+'/a.webm'},'Late error A'),origin),false);
  assert.ok(await page.evaluate(()=>window.root.__hmbCompactPlaybackFailure.status===window.bStatus));
  assert.equal(await page.locator('[data-compact-preview-load-status]').count(),1);
  assert.equal(await page.evaluate(origin=>{const media=window.root.__hmbCompactSharedVideoPlayer;Object.defineProperty(media,'currentSrc',{configurable:true,get:()=>origin+'/a.webm'});try{return window.api.hmbShowVideoPickerCompactPlaybackFailure(window.root,media,{uid:'b',url:origin+'/b.webm'},'Old source event while new src is pending');}finally{delete media.currentSrc;}},origin),false,'An old currentSrc must not report a failure against a newly assigned src.');
  assert.ok(await page.evaluate(()=>window.root.__hmbCompactPlaybackFailure.status===window.bStatus));
  await page.locator('[data-toggle-video-uid="c"]').click();assert.equal(await page.locator('[data-compact-preview-load-status]').count(),0,'Changing the selected card clears its old failure.');
  await page.locator('[data-play-video-uid="c"]').click();await page.waitForFunction(()=>{const v=window.root.__hmbCompactSharedVideoPlayer;return v&&!v.error&&!v.paused&&v.currentTime>.1;});
  await page.locator('[data-play-video-uid="b"]').click();await page.locator('[data-compact-preview-load-status="b"]').waitFor({state:'visible'});
  await page.evaluate(()=>window.controller.cleanup());assert.equal(await page.locator('[data-compact-preview-load-status]').count(),0);
  assert.equal(await page.evaluate(origin=>window.api.hmbShowVideoPickerCompactPlaybackFailure(window.root,window.ownedMedia,{uid:'b',url:origin+'/b.webm'},'After cleanup'),origin),false);
  assert.ok(await page.evaluate(()=>window.ownedMedia.paused&&!window.ownedMedia.getAttribute('src')));
  await page.evaluate(()=>{const next=document.createElement('div');next.id='root';window.root.replaceWith(next);window.root=next;});
  await page.evaluate(value=>window.mountState({...value,runtime_instance_id:'new-runtime'}),value);
  if(await page.evaluate(()=>window.root.__hmbVideoPickerExpanded===true))await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
  assert.equal(await page.evaluate(origin=>window.api.hmbShowVideoPickerCompactPlaybackFailure(window.root,window.ownedMedia,{uid:'b',url:origin+'/b.webm'},'Previous runtime'),origin),false);
  await page.locator('[data-play-video-uid="a"]').click();await page.waitForFunction(()=>{const v=window.root.__hmbCompactSharedVideoPlayer;return v&&!v.error&&!v.paused&&v.currentTime>.1;});
  assert.equal(await page.locator('[data-compact-preview-load-status]').count(),0);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  await page.evaluate(()=>window.controller.cleanup());
  console.log('Picker compact playback error: PASS (native media-error feedback, same-source retry, exact owner, source/selection switch, cleanup/remount; memory-only fixture)');
} catch(error) {
  console.error(JSON.stringify({mediaRequests,diagnostic:await page?.evaluate(()=>{const v=window.root.__hmbCompactSharedVideoPlayer;return {stage:'failure',media:v?{time:v.currentTime,paused:v.paused,ready:v.readyState,error:v.error?.code||null,source:v.getAttribute('src'),loads:window.loads.get(v)}:null,events:window.events?.slice(-20),status:window.root.querySelector('[data-compact-preview-load-status]')?.textContent||''};}).catch(()=>null)}));
  throw error;
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
