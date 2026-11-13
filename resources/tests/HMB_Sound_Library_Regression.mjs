// Actual Chrome: transport races, original-audio preview ownership and native disabled state.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {hmbSoundState,hmbSoundShotRows} from '../../widgets/HMBSoundLibraryWidget.js';

assert.deepEqual(hmbSoundState({value:'bad'}).tracks,[]);
assert.deepEqual(hmbSoundState({value:{tracks:'bad',assets:null,shot_catalog:[]}}).assets,[]);
assert.equal(hmbSoundState({value:{busy:'true'}}).busy,false);
const require=createRequire(import.meta.url);
let playwright;
try{playwright=require('playwright');}catch{try{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}catch{}}
const executablePath=process.env.HMB_COLOR_LUT_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
if(!playwright||!fs.existsSync(executablePath)){
 console.log('Sound Library shape checks PASS; real browser not_run (runtime unavailable)');process.exit(0);
}
const source=fs.readFileSync(new URL('../../widgets/HMBSoundLibraryWidget.js',import.meta.url));
const wav=Buffer.alloc(44+48000*2*8);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVE',8);wav.write('fmt ',12);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(48000,24);wav.writeUInt32LE(96000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
const track={instance_id:'clip-1',source_uid:'sound-1',relative_path:'Dialogue/voice.wav',name:'Voice <literal>',role:'Dialogue',purpose:'both',
 channel_uuid:'',shot_uuid:'',duration_seconds:1,in_seconds:0,out_seconds:null,start_seconds:0,gain_db:0,enabled:true,loop:false,lipsync:false,transcript:' exact <script>never()</script> & words ',target:'hero',preview_url:'/tone.wav'};
const state={schema:'hmb-sound-library-ui',version:1,revision:1,project_id:'showA',project_uid:'project-a',project_root:'C:/synthetic/showA/Ai_Ct_audio',
 projects:[{project_id:'showA',project_root:'C:/synthetic/showA/Ai_Ct_audio'}],assets:[{source_uid:'sound-1',name:'Voice',relative_path:'Dialogue/voice.wav',role:'Dialogue',extension:'.wav',preview_url:'/tone.wav'}],
 shot:{channel_uuid:'',shot_uuid:''},shot_catalog:{shots:[]},tracks:[track],busy:false,status:'Ready',error_code:'',ack_command_id:''};
const html=`<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#0a121e}#widget{width:1140px;height:830px}</style><main class="react-flow"><section class="react-flow__node selected" data-id="sound-node" style="height:830px"><div id="widget"></div></section></main><script type="module">
import mount from '/widget.js';window.state=${JSON.stringify(state).replaceAll('<','\\u003c')};window.commands=[];window.throwTransport=false;window.disabled=false;
window.nativeEvents=[];window.geometryUpdates=[];
for(const phase of ['ready','retire'])document.addEventListener('hmb-color-lut-header-'+phase,event=>window.nativeEvents.push([phase,event.detail.container.id]));
window.props=()=>({value:window.state,disabled:window.disabled,updateNodeInternals:id=>window.geometryUpdates.push(id),onChange:v=>{window.commands.push(v);if(window.throwTransport)throw new Error('synthetic transport');}});
window.controller=mount(document.getElementById('widget'),window.props());window.ready=true;</script>`;
const server=http.createServer((req,res)=>{if(/^\/tone(?:[23])?\.wav/.test(req.url)){
 res.setHeader('Content-Type','audio/wav');res.setHeader('Accept-Ranges','bytes');
 const range=String(req.headers.range||'').match(/^bytes=(\d+)-(\d*)$/);
 if(range){const start=Number(range[1]),end=Math.min(wav.length-1,range[2]?Number(range[2]):wav.length-1);res.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${wav.length}`,'Content-Length':end-start+1});res.end(wav.subarray(start,end+1));}
 else{res.setHeader('Content-Length',wav.length);res.end(wav);}
 }else{res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:html);}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 browser=await playwright.chromium.launch({executablePath,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1500,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 page.setDefaultTimeout(6000);
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
 assert.equal(await page.locator('[data-project],.hs-project,[data-action="projects"]').count(),0,'No project-selection UI exists.');
 assert.equal(await page.locator('audio').evaluate(a=>a.paused&&!a.getAttribute('src')),true,'Mount never loads or auto-plays audio.');
 await page.locator('[data-preview-track="clip-1"]').click();
 await page.locator('audio').evaluate(a=>{window.ownedAudio=a;a.currentTime=.1;});
 await page.evaluate(()=>{window.state={...window.state,revision:2,status:'new host status'};window.controller.update(window.props());});
 assert.equal(await page.locator('audio').evaluate(a=>a===window.ownedAudio),true,'Host updates must preserve the actual playing media element.');
 assert.equal(await page.locator('audio').evaluate(a=>a.paused),false);
 await page.locator('audio').evaluate(a=>a.pause());
 await page.locator('[data-detail="clip-1"]').click();
 assert.equal(await page.locator('[data-detail-drawer] [data-field="transcript"]').inputValue(),track.transcript);
 assert.equal(await page.locator('[data-detail-drawer] script,literal').count(),0,'Names and lyrics remain literal escaped text.');
 await page.locator('[data-field="role"]').selectOption('SFX');
 assert.equal(await page.evaluate(()=>window.commands.length),1);
 assert.deepEqual(await page.evaluate(()=>window.commands[0].__hmb_sound_command.context),{project_uid:'project-a',channel_uuid:'',shot_uuid:'',revision:2});
 assert.equal(await page.locator('[data-field="purpose"]').isDisabled(),true,'Pending paint locks all authored controls before transport.');
 await page.evaluate(()=>window.controller.update(window.props()));
 assert.equal(await page.locator('[data-field="purpose"]').isDisabled(),true,'An unchanged old echo must not release a pending command.');
 await page.locator('[data-action="cancel"]').click();
 assert.equal(await page.evaluate(()=>window.commands.at(-1).__hmb_sound_command.action),'cancel');
 await page.evaluate(()=>{const id=window.commands.at(-1).__hmb_sound_command.id;window.state={...window.state,revision:3,ack_command_id:id};window.controller.update(window.props());window.throwTransport=true;});
 await page.locator('[data-field="role"]').selectOption('Music');
 assert.match(await page.locator('[role="status"]').textContent(),/SOUND_TRANSPORT_FAILED/);
 assert.equal(await page.locator('[data-field="purpose"]').isDisabled(),false,'A synchronous transport error must leave a retryable UI.');
 await page.evaluate(()=>{window.throwTransport=false;});
 assert.equal(await page.locator('[data-hmb-native-safety-notice],[data-hmb-native-safety-status]').count(),0,'Normal Sound editing does not show a permanent safety notice.');
 const bindingBefore=await page.evaluate(()=>window.commands.length);
 await page.locator('[data-duplicate="clip-1"]').click();
 assert.equal(await page.evaluate(()=>window.commands.at(-1).__hmb_sound_command.action),'duplicate');
 await page.evaluate(()=>{const id=window.commands.at(-1).__hmb_sound_command.id;window.state={...window.state,revision:window.state.revision+1,ack_command_id:id,tracks:[...window.state.tracks,{...window.state.tracks[0],instance_id:'clip-copy'}]};window.controller.update(window.props());});
 await page.locator('[data-remove="clip-copy"]').click();
 assert.equal(await page.evaluate(()=>window.commands.at(-1).__hmb_sound_command.action),'remove','An internal binding X is not a native node-delete action.');
 await page.evaluate(()=>{const id=window.commands.at(-1).__hmb_sound_command.id;window.state={...window.state,revision:window.state.revision+1,ack_command_id:id,tracks:window.state.tracks.filter(t=>t.instance_id!=='clip-copy')};window.controller.update(window.props());});
 assert.equal(await page.evaluate(()=>window.commands.length),bindingBefore+2);
 assert.equal(await page.locator('[data-hmb-native-safety-notice]').count(),0,'Binding duplicate/remove never triggers the stock node-delete notice.');
 await page.evaluate(()=>{window.throwTransport=false;window.disabled=true;window.controller.update(window.props());});
 assert.equal(await page.locator('[data-field="role"]').isDisabled(),true,'Native Griptape disabled locks authoring.');
 const before=await page.evaluate(()=>window.commands.length);
 await page.locator('[data-preview-track="clip-1"]').click();
 await page.locator('[data-preview-track="clip-1"]').click();
 assert.equal(await page.evaluate(()=>window.commands.length),before,'Playback remains local when native authoring is disabled.');
 await page.evaluate(()=>{window.disabled=false;window.state={...window.state,revision:window.state.revision+1,tracks:[]};window.controller.update(window.props());});
 assert.equal(await page.evaluate(()=>window.ownedAudio.getAttribute('src')),null,'Removed previews release their source.');
 assert.equal(await page.evaluate(()=>window.ownedAudio.paused),true);
 await page.evaluate(()=>{window.deleteEvents=0;document.addEventListener('keydown',event=>{if(event.key==='Delete')window.deleteEvents++;});document.activeElement?.blur();});
 await page.keyboard.press('Delete');
 assert.equal(await page.evaluate(()=>window.deleteEvents),0,'Stock editor without a verified guard must keep Sound node deletion gated.');
 assert.equal(await page.locator('[data-hmb-native-safety-notice]').count(),1);
 await page.evaluate(()=>{document.documentElement.setAttribute('data-hmb-native-deletion-guard','engine-preflight');document.documentElement.setAttribute('data-hmb-native-deletion-protection-version','2');document.activeElement?.blur();});
 await page.keyboard.press('Delete');
 assert.equal(await page.evaluate(()=>window.deleteEvents),1,'Verified native guard remains the deletion authority.');
 assert.deepEqual(errors,[]);
 // The approved A design follows the actual source catalog: 1, 3 or 5 UUID
 // rows, no invented +Shot, and no accidental limit of five audio cards.
 const channel='11111111-1111-4111-8111-111111111111';
 const shots=Array.from({length:5},(_,i)=>({shot_uuid:`shot-${i+1}`,number:i+1,name:`Shot ${i+1} · 원본 이름`,revision:1}));
 const assets=Array.from({length:8},(_,i)=>({source_uid:`source-${i}`,name:['Hero_line.wav','Wing_flap.wav','Forest.wav','Impact.wav','Theme.wav','Door.wav','Steps.wav','Birds.wav'][i],relative_path:`${['Dialogue','SFX','Ambience','SFX','Music','SFX','SFX','Ambience'][i]}/asset-${i}.wav`,role:['Dialogue','SFX','Ambience','SFX','Music','SFX','SFX','Ambience'][i],extension:'.wav',preview_url:i===1?'/tone2.wav':'/tone.wav'}));
 const tracks=assets.slice(0,7).map((a,i)=>({...track,...a,instance_id:`bound-${i}`,channel_uuid:channel,shot_uuid:shots[1].shot_uuid,duration_seconds:8,in_seconds:i===0?1:0,out_seconds:i===0?4:null,start_seconds:100,media_signature:`signature-${i}`}));
 for(const count of [1,3,5]){
   const rows=shots.slice(0,count);
   assert.equal(hmbSoundShotRows(hmbSoundState({value:{shot_catalog:{channel_uuid:channel,shots:rows},shot:{channel_uuid:channel,shot_uuid:rows[0].shot_uuid}}})).length,count);
   await page.evaluate(({rows,assets,tracks,channel})=>{window.state={...window.state,revision:window.state.revision+1,shot_catalog:{channel_uuid:channel,shots:rows},shot:{channel_uuid:channel,shot_uuid:rows[0].shot_uuid},assets,tracks:rows.length>1?tracks:[]};window.controller.update(window.props());},{rows,assets,tracks,channel});
   assert.deepEqual(await page.locator('[data-shot-row]').evaluateAll(nodes=>nodes.map(n=>n.dataset.shotRow)),rows.map(s=>s.shot_uuid));
   assert.deepEqual(await page.locator('.hs-shot-head strong').allTextContents(),rows.map(s=>s.name));
 }
 assert.equal(await page.locator('[data-instance]').count(),7,'Five designs never becomes an audio-card cap.');
 assert.equal(await page.getByRole('button',{name:/\+\s*Shot/}).count(),0);
 const writesBefore=await page.evaluate(()=>window.commands.length);
 await page.locator('[data-shot="shot-3"]').click();
 let request=await page.evaluate(()=>window.commands.at(-1).__hmb_sound_command);
 assert.equal(request.action,'shot');assert.equal(request.shot_uuid,'shot-3');
 await page.evaluate(({id,channel})=>{window.state={...window.state,revision:window.state.revision+1,ack_command_id:id,shot:{channel_uuid:channel,shot_uuid:'shot-3'}};window.controller.update(window.props());},{id:request.id,channel});
 await page.locator('[data-add="source-7"]').click();
 request=await page.evaluate(()=>window.commands.at(-1).__hmb_sound_command);
 assert.equal(request.action,'shot_add');assert.equal(request.source_uid,'source-7');assert.equal(request.shot_uuid,'shot-3');assert.equal(request.context.shot_uuid,'shot-3');
 const bound={...track,...assets[7],instance_id:'bound-shot3',channel_uuid:channel,shot_uuid:'shot-3',duration_seconds:8,media_signature:'signature-3rd'};
 await page.evaluate(({id,bound})=>{window.state={...window.state,revision:window.state.revision+1,ack_command_id:id,tracks:[...window.state.tracks,bound]};window.controller.update(window.props());},{id:request.id,bound});
 assert.equal(await page.locator('[data-shot-row="shot-3"] [data-instance]').count(),1);
 assert.equal(await page.locator('[data-shot-row="shot-2"] [data-instance]').count(),7);
 assert.equal(await page.evaluate(()=>window.commands.length),writesBefore+2);
 const beforePlay=await page.evaluate(()=>({commands:window.commands.length,tracks:JSON.stringify(window.state.tracks)}));
 await page.locator('[data-preview-track="bound-0"]').click();
 await page.waitForFunction(()=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>=1;});
 assert.equal(await page.locator('[data-instance="bound-0"]').evaluate(n=>n.classList.contains('playing')),true);
 assert.equal(await page.locator('[data-scrub="bound-0"]').getAttribute('min'),'1');
 assert.equal(await page.locator('[data-scrub="bound-0"]').getAttribute('max'),'4');
 await page.evaluate(()=>{window.sameAudio=document.querySelector('audio');window.beforeTime=window.sameAudio.currentTime;window.state={...window.state,revision:window.state.revision+1,status:'status echo'};window.controller.update(window.props());});
 assert.equal(await page.locator('audio').evaluate(a=>a===window.sameAudio&&!a.paused&&a.currentTime>=window.beforeTime),true,'Metadata update never restarts or replaces playing audio.');
 await page.locator('[data-preview-track="bound-1"]').click();
 assert.equal(await page.locator('audio').count(),1);
 assert.equal(await page.locator('[data-instance="bound-0"]').evaluate(n=>n.classList.contains('playing')),false);
 await page.waitForFunction(()=>document.querySelector('[data-instance="bound-1"]').classList.contains('playing'));
 await page.locator('[data-preview-track="bound-1"]').click();
 assert.equal(await page.locator('audio').evaluate(a=>a.paused),true);
 await page.locator('[data-scrub="bound-0"]').evaluate(el=>{el.value='2.2';el.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>{const a=document.querySelector('audio');return a.paused&&Math.abs(a.currentTime-2.2)<.2;},{},{timeout:6000}).catch(async error=>{console.log(await page.locator('audio').evaluate(a=>({paused:a.paused,time:a.currentTime,ready:a.readyState,duration:a.duration,src:a.getAttribute('src')})));throw error;});
 await page.evaluate(()=>{window.hostKeys=[];document.addEventListener('keydown',event=>window.hostKeys.push(event.key));});
 await page.locator('[data-preview-track="bound-0"]').focus();await page.keyboard.press('Space');
 await page.waitForFunction(()=>!document.querySelector('audio').paused);
 await page.locator('[data-scrub="bound-0"]').focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('Delete');
 assert.deepEqual(await page.evaluate(()=>window.hostKeys),[],'Playback keys do not reach node shortcuts.');
 await page.locator('audio').evaluate(a=>{a.currentTime=3.98;});
 await page.waitForFunction(()=>document.querySelector('audio').paused);
 assert.equal(await page.locator('.hs-bound.playing').count(),0,'Segment OUT stops without playing another source.');
 await page.locator('[data-preview-asset="source-3"]').click();
 await page.waitForFunction(()=>document.querySelector('[data-preview-asset="source-3"]').getAttribute('aria-pressed')==='true');
 assert.equal(await page.locator('audio').count(),1);assert.equal(await page.locator('.hs-bound.playing').count(),0,'Catalog and bound cards share one preview owner.');
 await page.locator('[data-preview-asset="source-3"]').click();
 assert.equal(await page.evaluate(()=>window.commands.length),beforePlay.commands);
 assert.equal(await page.evaluate(()=>JSON.stringify(window.state.tracks)),beforePlay.tracks);
 // Source replacement and removal retire the same player without playback.
 await page.locator('[data-preview-track="bound-1"]').click();
 await page.evaluate(()=>{window.state={...window.state,revision:window.state.revision+1,tracks:window.state.tracks.map(t=>t.instance_id==='bound-1'?{...t,media_signature:'changed-original'}:t)};window.controller.update(window.props());});
 assert.equal(await page.locator('audio').evaluate(a=>a.paused&&!a.getAttribute('src')),true);
 // Save a representative A layout with three bound cards in its active row.
 await page.evaluate(({shots,tracks,channel})=>{window.state={...window.state,revision:window.state.revision+1,shot_catalog:{channel_uuid:channel,shots},shot:{channel_uuid:channel,shot_uuid:'shot-2'},tracks:tracks.slice(0,3),status:'사운드 준비 완료'};window.controller.update(window.props());},{shots,tracks,channel});
 await page.locator('[data-preview-track="bound-0"]').click();
 await page.waitForFunction(()=>document.querySelector('[data-instance="bound-0"]').classList.contains('playing'));
 await page.evaluate(async()=>{Object.assign(document.getElementById('widget').style,{width:'1430px',height:'620px'});await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
 const defaultGeometry=await page.evaluate(()=>{
   const host=document.getElementById('widget').getBoundingClientRect(),root=document.querySelector('.hmb-sound').getBoundingClientRect(),footer=document.querySelector('.hs-status').getBoundingClientRect();
   const headers=[...document.querySelectorAll('.hs-shot-head')].map(el=>el.getBoundingClientRect());
   const stack=document.querySelector('.hs-shot-stack'),shotArea=stack.getBoundingClientRect();
   return {hostWidth:host.width,hostHeight:host.height,rootHeight:root.height,shotTop:shotArea.top,shotBottom:shotArea.bottom,shotScrollHeight:stack.scrollHeight,footerTop:footer.top,headers:headers.map(r=>[r.top,r.bottom]),allFiveShotHeadersVisible:headers.length===5&&headers.every(r=>r.top>=shotArea.top&&r.bottom<=shotArea.bottom),footerVisible:footer.bottom<=host.bottom+.5&&footer.top>=host.top,rootWithinHost:root.bottom<=host.bottom+.5};
 });
 assert.equal(defaultGeometry.hostWidth,1430);assert.equal(defaultGeometry.hostHeight,620);assert.equal(defaultGeometry.allFiveShotHeadersVisible,true,JSON.stringify(defaultGeometry));assert.equal(defaultGeometry.footerVisible,true,JSON.stringify(defaultGeometry));assert.equal(defaultGeometry.rootWithinHost,true,JSON.stringify(defaultGeometry));
 const defaultScreenshot=path.resolve('reports/sound-start-size-20261104/Sound-Library-Default-1430x620.png');fs.mkdirSync(path.dirname(defaultScreenshot),{recursive:true});await page.locator('#widget').screenshot({path:defaultScreenshot});
 for(const height of [675,500]){
   const custom=await page.evaluate(async height=>{const host=document.getElementById('widget');host.style.height=height+'px';await new Promise(resolve=>requestAnimationFrame(resolve));return {height:host.getBoundingClientRect().height,footer:document.querySelector('.hs-status').getBoundingClientRect().bottom,hostBottom:host.getBoundingClientRect().bottom};},height);
   assert.equal(custom.height,height);assert.ok(custom.footer<=custom.hostBottom+.5,'Custom widget height keeps a visible footer and scrolls its contents.');
 }
 await page.evaluate(()=>{Object.assign(document.getElementById('widget').style,{width:'1140px',height:'830px'});});
 const geometryBefore=await page.locator('[data-id="sound-node"]').boundingBox();
 const beforeMode=await page.evaluate(()=>{
   const host=document.getElementById('widget');
   host.dispatchEvent(new CustomEvent('hmb-color-lut-header-state',{detail:{active:true}}));
   const identity=host.querySelector('[data-hmb-native-identity]');
   const actions=host.querySelector('[data-hmb-native-actions]');
   const control=document.createElement('button');control.textContent='Native minimize';actions.append(control);
   window.soundModeRefs={header:host.querySelector('[data-sound-toggle-surface]'),identity,actions,control,audio:host.querySelector('audio'),search:host.querySelector('[data-search]')};
   return {commands:window.commands.length,events:window.nativeEvents};
 });
 assert.deepEqual(beforeMode.events,[['ready','widget']]);
 assert.equal(await page.locator('#widget').getAttribute('data-hmb-native-node-type'),'HMBSoundLibrary');
 assert.equal(await page.locator('[data-hmb-sound-widget]').getAttribute('data-hmb-native-header'),'active');
 await page.locator('[data-search]').fill('Wing');
 await page.locator('[data-hmb-native-actions] button').dispatchEvent('dblclick',{button:0});
 await page.locator('[data-action="refresh"]').dispatchEvent('dblclick',{button:0});
 await page.locator('.hs-shot-head').first().dispatchEvent('dblclick',{button:0});
 assert.equal(await page.locator('[data-hmb-sound-widget]').getAttribute('data-sound-view'),'expanded');
 await page.locator('[data-sound-toggle-surface]').dispatchEvent('dblclick',{button:0});
 assert.equal(await page.locator('[data-hmb-sound-widget]').getAttribute('data-sound-view'),'compact');
 assert.equal(await page.locator('.hs-main').isVisible(),false);
 assert.equal(await page.locator('.hs-shot-head').first().isVisible(),true);
 assert.equal(await page.locator('[data-preview-track="bound-0"]').isVisible(),true);
 const compactGeometry=await page.locator('[data-id="sound-node"]').boundingBox();
 assert.ok(compactGeometry.height<geometryBefore.height-100,'Compact view releases unused host height.');
 assert.equal(compactGeometry.width,geometryBefore.width);
 await page.evaluate(()=>{window.state={...window.state,revision:window.state.revision+1,status:'Compact update'};window.controller.update(window.props());});
 assert.equal(await page.locator('[data-hmb-sound-widget]').getAttribute('data-sound-view'),'compact');
 assert.equal(await page.evaluate(()=>{
   const refs=window.soundModeRefs,host=document.getElementById('widget');
   return refs.header===host.querySelector('[data-sound-toggle-surface]')&&refs.identity===host.querySelector('[data-hmb-native-identity]')&&refs.actions===refs.control.parentElement&&refs.audio===host.querySelector('audio')&&!refs.audio.paused;
 }),true,'Compact updates keep the original native header, controls and playing audio.');
 await page.locator('[data-sound-toggle-surface]').dispatchEvent('dblclick',{button:0});
 assert.equal(await page.locator('[data-search]').inputValue(),'Wing');
 assert.equal((await page.locator('[data-id="sound-node"]').boundingBox()).height,geometryBefore.height);
 assert.deepEqual(await page.evaluate(()=>window.geometryUpdates),['sound-node','sound-node']);
 assert.equal(await page.evaluate(()=>window.commands.length),beforeMode.commands,'Changing presentation never sends an engine command.');
 await page.evaluate(()=>document.getElementById('widget').dispatchEvent(new CustomEvent('hmb-color-lut-header-state',{detail:{active:false}})));
 const screenshot=process.env.HMB_SOUND_LIBRARY_SCREENSHOT||path.resolve('reports/local0860-sound/Sound-Library-A.png');fs.mkdirSync(path.dirname(screenshot),{recursive:true});await page.locator('#widget').screenshot({path:screenshot});
 await page.locator('[data-detail="bound-0"]').click();
 await page.locator('#widget').screenshot({path:path.resolve('reports/local0860-sound/Sound-Library-A-Details.png')});
 const finalAudio=await page.locator('audio').evaluate(a=>{window.cleanupAudio=a;return a.isConnected;});assert.equal(finalAudio,true);
 await page.evaluate(()=>window.controller.cleanup());
 assert.equal(await page.evaluate(()=>window.cleanupAudio.paused&&!window.cleanupAudio.getAttribute('src')&&!window.cleanupAudio.isConnected),true);
 assert.deepEqual(await page.evaluate(()=>window.nativeEvents),[['ready','widget'],['retire','widget']]);
 console.log(JSON.stringify({result:'PASS',realBrowser:true,design:'A',sourceShotCounts:[1,3,5],audioCap:false,atomicShotAdd:true,previewMutations:0,segmentInOut:true,singlePlayer:true,pendingBeforeTransport:true,oldEchoBlocked:true,cancelAvailable:true,syncThrowRetry:true,nativeDisabled:true,mediaDOMPreserved:true,removedPreviewReleased:true,stockSafetyFallback:true,defaultGeometry,defaultScreenshot,screenshot}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
