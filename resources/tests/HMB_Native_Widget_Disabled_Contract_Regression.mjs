/** Actual widgets + bounded native disabled adapter in isolated Chrome. */
import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import crypto from 'node:crypto';
import{createRequire}from'node:module';import{fileURLToPath}from'node:url';
const root=fileURLToPath(new URL('../..',import.meta.url)),require=createRequire(import.meta.url);
const files=['HMBSeedanceGenerationWidget.js','HMBAgentLibraryWidget.js','HMBPromptLibraryScopedBindingWidget.js','HMBFinishLookLibraryWidget.js','HMBColorLUTLibraryWidget.js','HMBImageAssetLibraryWidget.js','HMBVideoPickerLibraryWidget_v032.js','HMBVideoPickerCommandBridgeWidget_v032.js','HMBImageAssetThumbnailPatchBridgeWidget.js'];
const hash=v=>crypto.createHash('sha256').update(v).digest('hex');const sources=files.map(f=>fs.readFileSync(path.join(root,'widgets',f),'utf8'));
// Git and the runtime packager canonicalize JS to LF. Compare the same literal
// across Windows checkouts without changing any adapter behavior assertions.
const helper=s=>s.slice(s.indexOf('// HMB_NATIVE_DISABLED_ADAPTER_V1_BEGIN'),s.indexOf('// HMB_NATIVE_DISABLED_ADAPTER_V1_END')).replace(/\r\n?/g,'\n');
for(const s of sources)assert.equal(helper(s),helper(sources[0]),'The bounded module-local lock adapter must remain identical in all nine widgets.');
let playwright;try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const browser=await playwright.chromium.launch({executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',headless:true});
const report={schema:'hmb-native-widget-disabled-contract/v1',passed:false,cases:[],source_sha256:files.map((f,i)=>({file:f,sha256:hash(sources[i])})),helper_sha256:hash(helper(sources[0])),external_requests:0,live_graph_calls:0,paid_calls:0};
try{
 const page=await browser.newPage({viewport:{width:1900,height:1450}});const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',r=>{report.external_requests++;return r.abort();});
 await page.setContent('<!doctype html><meta charset="utf-8"><style>.react-flow__node{width:1800px;min-height:700px}</style><main></main>');
 await page.evaluate(async sources=>{
  window.modules=[];for(const code of sources)modules.push(await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(code+'\nexport { hmbNativeUiContract, hmbNativeUiReadCommand };')))));
  window.ids=[1,2,3].map(n=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`);
  const shot={channel_uuid:ids[1],shot_uuid:ids[2],number:1,name:'Synthetic disabled contract'};
  window.values=[{schema:'hmb-seedance-shot-ui',schema_version:2,shot:{},
   shot_catalog:{schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:ids[0],channel_uuid:ids[1],generation:1,metadata_sha256:'a'.repeat(64),shots:[{shot_uuid:ids[2],number:1,name:shot.name,revision:1}]},
   execution_mode:'only',requested_mode:'only',execution_mode_revision:1,execution_mode_state_revision:1,execution_mode_instance:'a'.repeat(32),generation:{phase:'idle',media_revision:0},draft:{visible:false}},
   {schema:'hmb-agent-shot-row',version:1,shot,selected:true,expanded:true,status:''},{},{},{},{},{},
   {schema:'hmb-picker-command',version:1,runtime_instance_id:'fixture-runtime'},
   {schema:'hmb-image-asset-thumbnail-bridge',version:1,runtime_instance_id:'fixture-runtime'}];
  window.make=(i,disabled)=>{
   const node=document.createElement('div');node.className='react-flow__node';const container=document.createElement('div');node.append(container);document.querySelector('main').append(node);
   const f={node,container,calls:[],commands:[],value:values[i]};
   f.props=disabled=>({value:f.value,disabled,onChange(value){f.calls.push(value);return Promise.resolve();},onCommand(value){f.commands.push(value);return Promise.resolve();}});
   f.handle=modules[i].default(container,f.props(disabled));f.cleanup=()=>{f.handle.cleanup();node.remove();};return f;
  };
 },sources);
 // Default enabled path: the adapter itself adds no host DOM observation,
 // queries, listeners or timers; callbacks preserve exact argument identity.
 const fast=await page.evaluate(()=>{
  let queries=0,listeners=0,writes=0,updates=0,seen=null;
  const c={querySelectorAll(){queries++;return[];},addEventListener(){listeners++;},removeEventListener(){},contains(){return true;}};
  const mount=(_c,p)=>{seen=p;return{update(next){seen=next;updates++;},cleanup(){}};};
  const payload={schema:'fixture',text:'literal'};let exact=false;
  const h=modules[0].hmbNativeUiContract(c,{value:1,disabled:false,onChange:v=>{exact=v===payload;}},mount,{kind:'fixture'});
  seen.onChange(payload);h.update({value:2,disabled:false,onChange:v=>{exact=v===payload;}});seen.onChange(payload);h.cleanup();
  return{queries,listeners,writes,updates,exact};
 });assert.deepEqual(fast,{queries:0,listeners:0,writes:0,updates:1,exact:true});report.cases.push('enabled_adapter_path_adds_no_DOM_scan_listener_observer_or_timer_and_forwards_same_payload');
 const cleanupFlush=await page.evaluate(()=>{
  const c={};let calls=0,cleanups=0,seen=null,controller;
  const h=modules[0].hmbNativeUiContract(c,{disabled:false,onChange(){calls++;controller.update({disabled:false});}},(_c,p)=>{seen=p;return{update(){},cleanup(){cleanups++;p.onChange({text:'final pending edit'});controller.cleanup();}};},{kind:'fixture'});controller=h;
  h.cleanup();h.cleanup();let rejected=false;try{seen.onChange({text:'late'});}catch{rejected=true;}
  return{calls,cleanups,rejected,retired:c.__hmbNativeUiContract===undefined};
 });assert.deepEqual(cleanupFlush,{calls:1,cleanups:1,rejected:true,retired:true});report.cases.push('cleanup_preserves_single_synchronous_final_flush_then_retires_callbacks_even_after_reentrant_update_cleanup');
 for(let i=0;i<files.length;i++){
  await page.evaluate(i=>{window.f=make(i,true);},i);
  let view=await page.evaluate(()=>{
   const c=f.container.__hmbNativeUiContract;const guarded=c.wrap();let blocked=false;try{guarded.onChange({schema:'fixture-write'});}catch{blocked=true;}
   const editable=[...c.originals].filter(([el,old])=>'disabled'in el&&!old.disabled);window.control=editable[0]?.[0]||null;
   const before=f.calls.length;if(control){control.dispatchEvent(new Event('change',{bubbles:true,cancelable:true}));control.click?.();}
   return{blocked,locked:editable.every(([el])=>el.disabled),controls:editable.length,noWrite:f.calls.length===before,kind:c.kind};
  });assert.equal(view.blocked,true,files[i]);assert.equal(view.locked,true,files[i]);assert.equal(view.noWrite,true,files[i]);
  await page.evaluate(()=>f.handle.update(f.props(false)));
  view=await page.evaluate(()=>{const old=f.calls.length,payload={schema:'fixture-unlocked'};f.container.__hmbNativeUiContract.wrap().onChange(payload);return{forwarded:f.calls.length===old+1&&f.calls.at(-1)===payload,observerDisconnected:!f.container.__hmbNativeUiContract.listening};});
  assert.equal(view.forwarded,true,files[i]);assert.equal(view.observerDisconnected,true,files[i]);
  // The same value object is deliberately reused: only disabled changes.
  await page.evaluate(()=>{window.oldCallback=f.container.__hmbNativeUiContract.wrap().onChange;f.handle.update(f.props(true));});
  view=await page.evaluate(()=>{let staleBlocked=false;try{oldCallback({schema:'stale-edit'});}catch{staleBlocked=true;}return{staleBlocked,sameValue:f.value===f.container.__hmbNativeUiContract.props.value};});
  assert.equal(view.staleBlocked,true,files[i]);assert.equal(view.sameValue,true,files[i]);
  const forwarded=await page.evaluate(i=>{
   const values=[{schema:'hmb-seedance-refresh-command',action:'refresh_existing'},{schema:'hmb-agent-shot-row',action:{kind:'cancel_selected'}},null,
    {ui_transport:{schema:'hmb-finish-ui-transport',operation:'refresh'}},{__hmb_color_lut_command__:{action:'cancel'}},null,
    {__hmb_picker_command__:{schema:'hmb-picker-command',action:'video_tools',payload:{op:'cancel'}}},
    {schema:'hmb-picker-command',action:'stop_read'},{schema:'hmb-image-asset-thumbnail-bridge',operation:'hydrate'}];
   const value=values[i];if(!value)return true;const n=f.calls.length;f.container.__hmbNativeUiContract.wrap().onChange(value);
   return f.calls.length===n+1&&f.calls.at(-1)===value;
  },i);assert.equal(forwarded,true,files[i]+' read/cancel envelope must be forwarded without rewriting it');
  await page.evaluate(()=>{window.retiredCallback=f.container.__hmbNativeUiContract.wrap().onChange;});
  await page.evaluate(()=>f.cleanup());
  assert.equal(await page.evaluate(()=>{try{retiredCallback({schema:'late-write'});return false;}catch{return true;}}),true,files[i]);
  report.cases.push(`${files[i]}: mount_lock_same_value_disabled_only_update_fresh_callbacks_cleanup`);
 }
 const exceptions=await page.evaluate(()=>{
  const cases=[['seedance',{schema:'hmb-seedance-refresh-command',action:'refresh_existing'}],['seedance',{schema:'hmb-seedance-refresh-command',action:'cancel_draft_final'}],
   ['agent',{schema:'hmb-agent-shot-row',action:{kind:'cancel_selected'}}],['agent',{schema:'hmb-agent-shot-row',action:{kind:'refresh'}}],
   ['picker',{__hmb_picker_command__:{schema:'hmb-picker-command',action:'stop_read'}}],['picker-bridge',{schema:'hmb-picker-command',action:'cancel_video_import'}],
   ['picker',{schema:'hmb-picker-command',action:'video_tools',payload:{op:'cancel'}}],
   ['thumbnail',{schema:'hmb-image-asset-thumbnail-bridge',operation:'catalog_page'}],['finish',{ui_transport:{schema:'hmb-finish-ui-transport',operation:'refresh'}}],['lut',{__hmb_color_lut_command__:{action:'cancel'}}]];
  return{allowed:cases.every(([kind,v])=>modules[0].hmbNativeUiReadCommand(v,kind)),rejected:[
   ['seedance',{schema:'hmb-seedance-refresh-command',action:'finalize_draft'}],['agent',{schema:'hmb-agent-shot-row',action:{kind:'run_selected'}}],
   ['picker',{schema:'hmb-picker-command',action:'read_scene'}],['picker',{schema:'hmb-picker-command',action:'video_tools',payload:{op:'run'}}],['lut',{action:'export'}],['finish',{ui_transport:{schema:'hmb-finish-ui-transport',operation:'edit'}}],
   ['seedance',{schema:'wrong',action:'refresh_existing'}],['prompt',{schema:'hmb-seedance-refresh-command',action:'refresh_existing'}]
  ].every(([kind,v])=>!modules[0].hmbNativeUiReadCommand(v,kind))};
 });assert.deepEqual(exceptions,{allowed:true,rejected:true});report.cases.push('exact_schema_command_cancel_retrieve_read_exceptions_reject_run_edit_wrong_owner');
 // The adapter never writes native video attributes or blocks its controls.
 const media=await page.evaluate(async()=>{
  const container=document.createElement('div'),video=document.createElement('video');video.controls=true;container.append(video);document.body.append(container);
  video.muted=true;
  const canvas=document.createElement('canvas');canvas.width=32;canvas.height=24;const drawing=canvas.getContext('2d');drawing.fillStyle='#10b981';drawing.fillRect(0,0,32,24);
  const stream=canvas.captureStream(24),recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8'}),chunks=[];
  recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};const stopped=new Promise(resolve=>recorder.addEventListener('stop',resolve,{once:true}));
  let frame=0;const painting=setInterval(()=>{drawing.fillStyle=++frame%2?'#10b981':'#3b82f6';drawing.fillRect(0,0,32,24);},30);
  recorder.start();await new Promise(resolve=>setTimeout(resolve,360));recorder.stop();await stopped;clearInterval(painting);stream.getTracks().forEach(t=>t.stop());
  const url=URL.createObjectURL(new Blob(chunks,{type:'video/webm'}));video.src=url;
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Memory video decode timeout')),3000);video.addEventListener('canplay',()=>{clearTimeout(timer);resolve();},{once:true});});
  let p;const h=modules[0].hmbNativeUiContract(container,{disabled:true,onChange(){}},(_c,next)=>{p=next;return{update(v){p=v;},cleanup(){}};},{kind:'fixture'});
  const event=new MouseEvent('click',{bubbles:true,cancelable:true});video.dispatchEvent(event);
  await video.play();await new Promise(resolve=>setTimeout(resolve,80));const advanced=video.currentTime>0;video.pause();video.currentTime=0;
  const result={controls:video.controls,sameSrc:video.getAttribute('src')===url,clickUnblocked:!event.defaultPrevented,sameVideo:container.firstChild===video,advanced};h.cleanup();container.remove();URL.revokeObjectURL(url);return result;
 });assert.deepEqual(media,{controls:true,sameSrc:true,clickUnblocked:true,sameVideo:true,advanced:true});report.cases.push('native_video_original_element_src_controls_and_actual_local_playback_retained_while_authoring_locked');
 await page.evaluate(()=>{
  const node=document.createElement('div');node.className='react-flow__node';node.innerHTML='<div data-parameter-name="model_id"></div><div data-parameter-name="broker_server_url"><div data-broker></div></div>';document.querySelector('main').append(node);
  window.broker={node,calls:[],container:node.querySelector('[data-broker]')};broker.props=disabled=>({value:'https://broker.invalid',disabled,onChange:v=>broker.calls.push(v)});
  broker.handle=modules[0].default(broker.container,broker.props(true));
 });
 await page.locator('.hmb-seedance-broker-icon').click();
 assert.equal(await page.locator('[data-broker-url]').isDisabled(),true);assert.equal(await page.locator('[data-broker-save]').isDisabled(),true);
 assert.equal(await page.locator('[data-broker-cancel]').isDisabled(),false);
 await page.evaluate(()=>broker.handle.update(broker.props(false)));
 assert.equal(await page.locator('[data-broker-url]').isDisabled(),false);
 await page.evaluate(()=>broker.handle.update(broker.props(true)));
 assert.equal(await page.locator('[data-broker-url]').isDisabled(),true);
 await page.locator('[data-broker-cancel]').click();
 assert.equal(await page.evaluate(()=>broker.calls.length),0);await page.evaluate(()=>{broker.handle.cleanup();broker.node.remove();});
 report.cases.push('external_Broker_dialog_edit_lock_tracks_disabled_only_updates_and_keeps_close_available');
 assert.deepEqual(errors,[]);assert.equal(report.external_requests,0);report.console_errors=errors;
 assert.ok(files.every((f,i)=>hash(fs.readFileSync(path.join(root,'widgets',f),'utf8'))===hash(sources[i])));report.source_unchanged=true;report.passed=true;
}finally{await browser.close();const p=process.argv.indexOf('--evidence-path');if(p>=0){fs.mkdirSync(path.dirname(process.argv[p+1]),{recursive:true});fs.writeFileSync(process.argv[p+1],JSON.stringify(report,null,2)+'\n');}console.log(JSON.stringify(report));}
