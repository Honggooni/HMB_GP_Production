import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';

const source=fs.readFileSync(new URL('../../widgets/HMBVideoPickerLibraryWidget_v032.js',import.meta.url),'utf8');
const bridgeSource=fs.readFileSync(new URL('../../widgets/HMBVideoPickerCommandBridgeWidget_v032.js',import.meta.url),'utf8');
const require=createRequire(import.meta.url);
let playwright;
try{playwright=require('playwright');}catch{try{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}catch{
  if(process.env.HMB_PICKER_REQUIRE_BROWSER==='1')throw new Error('Playwright required');console.log('SKIP: Playwright unavailable');process.exit(0);
}}
const executablePath=process.env.HMB_PICKER_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
if(!fs.existsSync(executablePath)){if(process.env.HMB_PICKER_REQUIRE_BROWSER==='1')throw new Error('Browser required');console.log('SKIP: Browser unavailable');process.exit(0);}
const html=`<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#111}#widget{width:1600px;min-height:1200px}</style><div id="widget"></div><div id="bridge"></div><script type="module">
import mount,* as picker from '/widget.js';import bridge from '/bridge.js';
window.mountWidget=mount;window.mountBridge=bridge;window.picker=picker;window.publications=[];window.ready=true;
</script>`;
const server=http.createServer((req,res)=>{const js=req.url==='/widget.js'||req.url==='/bridge.js';res.setHeader('Content-Type',js?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:req.url==='/bridge.js'?bridgeSource:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
  browser=await playwright.chromium.launch({executablePath,headless:true});
  const origin=`http://127.0.0.1:${server.address().port}`,errors=[];
  async function prepare(){
    const page=await browser.newPage({viewport:{width:1700,height:1300}});page.setDefaultTimeout(10000);
    await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
    page.on('pageerror',error=>errors.push(error.message));await page.goto(origin);await page.waitForFunction(()=>window.ready);
    await page.evaluate(()=>{
      window.ids=Array.from({length:5},(_,i)=>'11111111-1111-4111-8111-00000000000'+(i+1));
      const scenes=Object.fromEntries(ids.map(id=>[id,{scene_path:'C:/same/shared.mb',scene_request_path:'C:/same/shared.mb',scene_draft_path:'C:/same/shared.mb',scene_stage:'EMPTY',native_read_ready:false,outliner_nodes:[],cameras:[],selected_camera:''}]));
      window.initial={language:'ko',runtime_instance_id:'matrix-runtime',state_writer:'python',state_revision:10,state_published_at_ms:Date.now(),
        maya_available:true,maya_executable:'C:/Maya/bin/mayabatch.exe',status:'READY',scene_stage:'EMPTY',native_read_ready:false,
        scene_path:'C:/same/shared.mb',scene_request_path:'C:/same/shared.mb',scene_draft_path:'C:/same/shared.mb',picker_scene_states:scenes,picker_scene_owner_uuid:ids[0],active_picker_shot_uuid:ids[0],
        shot_publisher_instance_uuid:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',channel_uuid:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',shot_uuid:ids[0],shot_number:1,shot_name:'Shot 1',
        shot_selections:ids.map((id,i)=>({shot_uuid:id,number:i+1,name:'Shot '+(i+1),revision:1})),
        picker_shots:ids.map((id,i)=>({workspace_uuid:id,bound_shot_uuid:id,number:i+1,name:'Shot '+(i+1),revision:1,video_asset_uids:['old-'+i],selected_video_uids:['old-'+i],preview_video_uid:'old-'+i})),
        videos:ids.map((id,i)=>({video_uid:'old-'+i,source_uid:'old-'+i,video_path:'C:/old/'+i+'.mp4',picker_shot_uuid:id,selected:i===0,selection_order:i===0?1:0,video_slot:i===0?1:0})),
        preview_video_uid:'old-0',selected_video_uid:'old-0',operation_kind:'',active_process_pid:0};
      window.live=()=>structuredClone(document.getElementById('widget').__hmbPendingPickerState||document.getElementById('widget').__hmbAuthoritativePickerState);
    });return page;
  }
  async function expand(page){if(await page.locator('.hmbvp').getAttribute('data-picker-view')!=='expanded')await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');}
  const matrix=[];
  for(const stateString of [false,true])for(const bridgeString of [false,true]){
    const page=await prepare();
    await page.evaluate(({stateString,bridgeString})=>{
      window.encode=value=>stateString?JSON.stringify(value):value;
      const commandState={runtime_instance_id:initial.runtime_instance_id};
      window.bridge=mountBridge(document.getElementById('bridge'),{value:bridgeString?JSON.stringify(commandState):commandState,onChange:command=>publications.push(command)});
      window.props=value=>({value:encode(value)});window.controller=mountWidget(document.getElementById('widget'),props(initial));
    },{stateString,bridgeString});
    await expand(page);await page.locator('#read-scene').click();
    const accepted=await page.evaluate(()=>{
      const command=publications.at(-1);if(!command)throw new Error('Hidden bridge did not receive READ');
      const next={...live(),state_writer:'python',state_revision:20,state_published_at_ms:Date.now()+1,backend_ack_action_id:'',
        read_requests_by_shot:{[ids[0]]:{action_id:command.action_id,status:'queued',scene_path:command.payload.scene_path,message:'읽기 요청 접수'}}};
      controller.update(props(next));
      return {action:command.action,shot:command.payload.picker_shot_uuid,pending:!!document.getElementById('widget').__hmbReadCommandPending};
    });
    assert.equal(accepted.action,'read_scene');assert.equal(accepted.shot,'11111111-1111-4111-8111-000000000001');assert.equal(accepted.pending,false);
    matrix.push({stateString,bridgeString,passed:true});await page.close();
  }
  const page=await prepare();
  await page.evaluate(()=>{
    window.timers=new Map();const originalSet=window.setTimeout.bind(window),originalClear=window.clearTimeout.bind(window);let nextTimer=900000;
    window.setTimeout=(fn,ms,...args)=>{if(ms!==20000)return originalSet(fn,ms,...args);const id=++nextTimer;timers.set(id,()=>fn(...args));return id;};
    window.clearTimeout=id=>{if(timers.has(id))timers.delete(id);else originalClear(id);};
    window.props=value=>({value,onChange:value=>publications.push(structuredClone(value))});window.controller=mountWidget(document.getElementById('widget'),props(initial));
    window.baseline=initial.picker_shots.map(row=>({uuid:row.workspace_uuid,bound:row.bound_shot_uuid,selected:row.selected_video_uids}));
  });
  await expand(page);
  for(let index=0;index<5;index++){
    if(index)await page.locator(`[data-picker-shot-activate="11111111-1111-4111-8111-00000000000${index+1}"]`).first().click();
    assert.equal(await page.locator('#read-scene').isEnabled(),true,'Another Shot pending receipt cannot lock this Shot');
    await page.locator('#read-scene').click();
  }
  const pending=await page.evaluate(()=>{
    const host=document.getElementById('widget'),requests=[...host.__hmbPickerReadRequests.values()];window.requests=requests;
    const beforeText=host.querySelector('#activity-log-view')?.textContent;
    timers.get(requests[0].timer)();
    return {requestCount:requests.length,remaining:host.__hmbPickerReadRequests.size,visibleAction:host.__hmbReadActionId,
      fifthAction:requests[4].actionId,stillPending:host.__hmbReadCommandPending,wrongShotErrorShown:host.querySelector('#activity-log-view')?.textContent!==beforeText};
  });
  assert.equal(pending.requestCount,5);assert.equal(pending.remaining,4);assert.equal(pending.visibleAction,pending.fifthAction);assert.equal(pending.stillPending,true);assert.equal(pending.wrongShotErrorShown,false);
  const receipts=await page.evaluate(()=>{
    const host=document.getElementById('widget');let current=live();
    const next={...current,state_writer:'python',state_revision:current.state_revision+1,state_published_at_ms:Date.now()+1,
      read_requests_by_shot:Object.fromEntries(requests.map(request=>[request.shot,{action_id:request.actionId,status:'queued',scene_path:request.scenePath}]))};
    controller.update(props(next));current=live();
    return {remaining:host.__hmbPickerReadRequests.size,pending:host.__hmbReadCommandPending,errors:host.__hmbPickerReadErrors.size,
      preserved:JSON.stringify(current.picker_shots.map(row=>({uuid:row.workspace_uuid,bound:row.bound_shot_uuid,selected:row.selected_video_uids})))===JSON.stringify(baseline),
      videoCount:current.videos.length};
  });
  assert.equal(receipts.remaining,0);assert.equal(receipts.pending,false);assert.equal(receipts.errors,0);assert.equal(receipts.preserved,true);assert.equal(receipts.videoCount,5);
  await page.close();

  const delayedPage=await prepare();
  await delayedPage.evaluate(()=>{
    const originalSet=window.setTimeout.bind(window);window.setTimeout=(fn,ms,...args)=>{
      if(ms===20000){window.fireReadTimeout=()=>fn(...args);return 900001;}return originalSet(fn,ms,...args);
    };
    window.props=value=>({value,onChange:value=>publications.push(structuredClone(value))});
    window.controller=mountWidget(document.getElementById('widget'),props(initial));
  });
  await expand(delayedPage);await delayedPage.locator('#read-scene').click();
  const timeout=await delayedPage.evaluate(()=>{
    window.delayedCommand=publications.findLast(value=>value.__hmb_picker_command__).__hmb_picker_command__;
    fireReadTimeout();return document.getElementById('widget').querySelector('#activity-log-view').textContent;
  });
  assert.match(timeout,/20초/,'An unacknowledged visible READ displays its timeout');
  const afterQueue=await delayedPage.evaluate(()=>{
    const queued={...live(),state_writer:'python',state_revision:30,state_published_at_ms:Date.now()+1,message:'읽기 요청 접수',
      read_requests_by_shot:{[ids[0]]:{action_id:delayedCommand.action_id,status:'queued',message:'읽기 요청 접수'}}};
    controller.update(props(queued));return document.getElementById('widget').querySelector('#activity-log-view').textContent;
  });
  assert.doesNotMatch(afterQueue,/20초/,'The exact late receipt removes the obsolete timeout');
  const completed=await delayedPage.evaluate(()=>{
    const scene={scene_path:'C:/same/shared.mb',scene_request_path:'C:/same/shared.mb',scene_draft_path:'C:/same/shared.mb',
      scene_stage:'OUTLINER_READY',native_read_ready:true,outliner_nodes:[{name:'FireflyAa1',full_path:'|FireflyAa1'}],
      cameras:[{name:'camera1',full_path:'|camera1'}],selected_camera:'|camera1',camera:'|camera1',start_frame:101,end_frame:186,current_frame:101,source_fps:24,output_fps:24,has_maya_frame_range:true};
    const next={...live(),...scene,state_writer:'python',state_revision:31,state_published_at_ms:Date.now()+2,status:'OUTLINER_READY',message:'읽기 완료',
      picker_scene_states:{...live().picker_scene_states,[ids[0]]:scene},read_requests_by_shot:{[ids[0]]:{action_id:delayedCommand.action_id,status:'complete'}},operation_kind:'',active_process_pid:0};
    controller.update(props(next));return {message:document.getElementById('widget').querySelector('#activity-log-view').textContent,
      readEnabled:!document.getElementById('read-scene').disabled,ready:live().native_read_ready};
  });
  assert.doesNotMatch(completed.message,/20초/);assert.equal(completed.readEnabled,true);assert.equal(completed.ready,true);
  await delayedPage.locator('#read-scene').click();
  assert.equal(await delayedPage.evaluate(()=>publications.filter(value=>value.__hmb_picker_command__?.action==='read_scene').length),2);
  const reopened=await delayedPage.evaluate(()=>{
    const next={...live(),runtime_instance_id:'matrix-runtime-reopened',state_writer:'python',state_revision:1,
      state_published_at_ms:Date.now()+10,read_requests_by_shot:{},backend_ack_action_id:'',status:'OUTLINER_READY',scene_stage:'OUTLINER_READY',message:''};
    controller.update(props(next));const host=document.getElementById('widget');
    return {pending:!!host.__hmbReadCommandPending,requests:host.__hmbPickerReadRequests?.size||0,
      errors:host.__hmbPickerReadErrors?.size||0};
  });
  assert.deepEqual(reopened,{pending:false,requests:0,errors:0},'A reopened runtime cannot inherit old pending delivery/spinner state');
  await expand(delayedPage);assert.equal(await delayedPage.locator('#read-scene').isEnabled(),true);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,matrix,independentPendingReads:5,offShotTimeoutIsolated:true,lateReceiptRecovery:true,reopenedRuntimeCleared:true,preservedBindingsAndVideos:true}));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
