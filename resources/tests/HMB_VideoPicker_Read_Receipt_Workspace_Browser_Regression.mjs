// A crossed Shot-row echo must protect media order without hiding a READ ACK
// or retaining the old EMPTY/READING_SCENE state behind completed controls.
import { listenBrowserSafeLoopback } from "./_hmb_browser_loopback.mjs";
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';

const source=fs.readFileSync(new URL('../../widgets/HMBVideoPickerLibraryWidget_v032.js',import.meta.url),'utf8');
const widget=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
// Execute the production controller's raw-receipt boundary independently of
// workflow hydration: a new runtime may remount, but is never this READ's ACK.
const receiptStart=source.indexOf('container.__hmbVideoPickerControllerUpdate = (nextProps) => {',source.indexOf('  schedulePickerFit(true);'));
assert.ok(receiptStart>=0);
const bodyStart=source.indexOf('    let receipt =',receiptStart);
const bodyEnd=source.indexOf('    nextProps = {',bodyStart);
assert.ok(bodyEnd>bodyStart);
const acceptReceipt=new Function('container','state','nextProps','hmbPickerStateFromProps','clean','hmbReconcilePickerCommandAcknowledgements',source.slice(bodyStart,bodyEnd));
for(const [name,patch,expected] of [
  ['matching',{runtime_instance_id:'live',state_writer:'python',backend_ack_action_id:'read-current'},false],
  ['old action',{runtime_instance_id:'live',state_writer:'python',backend_ack_action_id:'read-old'},true],
  ['foreign runtime',{runtime_instance_id:'other',state_writer:'python',backend_ack_action_id:'read-current'},true],
  ['missing runtime',{state_writer:'python',backend_ack_action_id:'read-current'},true],
  ['local draft',{runtime_instance_id:'live',state_writer:'widget',backend_ack_action_id:'read-current'},true],
]){
  const host={__hmbReadCommandPending:true,__hmbReadActionId:'read-current'};
  acceptReceipt(host,{runtime_instance_id:'live'},{value:JSON.stringify(patch)},p=>p.value,v=>String(v??'').trim(),widget.hmbReconcilePickerCommandAcknowledgements);
  assert.equal(host.__hmbReadCommandPending,expected,name);
}

const require=createRequire(import.meta.url);
let playwright;
try{playwright=require('playwright');}catch{try{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}catch{
  if(process.env.HMB_PICKER_REQUIRE_BROWSER==='1')throw new Error('Playwright required');
  console.log('SKIP browser: READ receipt boundary checks passed');process.exit(0);
}}
const executablePath=process.env.HMB_PICKER_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
if(!fs.existsSync(executablePath)){if(process.env.HMB_PICKER_REQUIRE_BROWSER==='1')throw new Error('Browser required');console.log('SKIP browser: browser unavailable');process.exit(0);}
const html=`<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#111}#widget{width:1600px;min-height:1200px}</style><div id="widget"></div><script type="module">
import mount,* as helpers from '/widget.js';window.mountWidget=mount;window.helpers=helpers;window.publications=[];
window.props=value=>({value,onChange:next=>window.publications.push(structuredClone(next))});window.ready=true;
</script>`;
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:html);});
await listenBrowserSafeLoopback(server);
let browser;
try{
  browser=await playwright.chromium.launch({executablePath,headless:true});
  const page=await browser.newPage({viewport:{width:1700,height:1300}});page.setDefaultTimeout(10000);
  const origin=`http://127.0.0.1:${server.address().port}`;
  await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin);await page.waitForFunction(()=>window.ready);
  await page.evaluate(()=>{
    const first='11111111-1111-4111-8111-000000000001',second='11111111-1111-4111-8111-000000000002';
    const state={language:'ko',runtime_instance_id:'read-receipt-runtime',state_writer:'python',state_revision:9,state_published_at_ms:Date.now(),
      status:'VIDEO_READY',scene_stage:'VIDEO_READY',scene_path:'C:/shots/first.mb',scene_request_path:'C:/shots/first.mb',scene_draft_path:'C:/shots/first.mb',
      native_read_ready:true,maya_available:true,maya_executable:'C:/Maya/bin/mayabatch.exe',maya_version:'2026',
      active_picker_shot_uuid:first,picker_scene_owner_uuid:first,picker_scene_states:{},
      shot_publisher_instance_uuid:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',channel_uuid:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',shot_uuid:first,shot_number:1,shot_name:'Shot 1',
      shot_selections:[{shot_uuid:first,number:1,name:'Shot 1',revision:1},{shot_uuid:second,number:2,name:'Shot 2',revision:1}],
      picker_shots:[{workspace_uuid:first,bound_shot_uuid:first,number:1,name:'Shot 1',revision:4,video_asset_uids:['a','b','c'],selected_video_uids:['b','a'],preview_video_uid:'b'},
        {workspace_uuid:second,bound_shot_uuid:second,number:2,name:'Shot 2',revision:1,video_asset_uids:[],selected_video_uids:[],preview_video_uid:''}],
      videos:['a','b','c'].map((uid,index)=>({video_uid:uid,source_uid:uid,video_path:'C:/outputs/'+uid+'.mp4',selected:index<2,selection_order:index===1?1:index===0?2:0,video_slot:index===1?1:index===0?2:0})),
      preview_video_uid:'b',selected_video_uid:'b',start_frame:101,end_frame:150,current_frame:101,source_fps:24,output_fps:24,output_width:1280,output_height:720,
      selected_camera:'|oldCamera',cameras:[{name:'oldCamera',full_path:'|oldCamera'}],outliner_nodes:[{name:'OldRoot',full_path:'|OldRoot',maya_uuid:'old-root'}],
      mask_enabled:true,operation_kind:'',operation_started_at_ms:1,operation_finished_at_ms:2,active_process_pid:0};
    const scope={channel_uuid:state.channel_uuid,shot_uuid:first};
    window.firstScope=scope;window.initialPickerState=structuredClone(state);
    const host=document.getElementById('widget');
    window.leasePacket={runtime_instance_id:state.runtime_instance_id,channel_uuid:state.channel_uuid,
      shot_edit_locks:[scope],verified_shots:[scope],picker_shot_status_revision:1};
    window.controller=mountWidget(host,{...props(state),ui_options:{picker_shot_status:leasePacket}});
    window.live=()=>structuredClone(host.__hmbPendingPickerState||host.__hmbAuthoritativePickerState);
    window.inspect=()=>{const s=live();return {status:s.status,stage:s.scene_stage,ready:s.native_read_ready,rootCount:s.outliner_nodes.length,
      pending:!!host.__hmbReadCommandPending,readDisabled:host.querySelector('#read-scene')?.disabled,generateDisabled:host.querySelector('#run-video')?.disabled,
      firstSelected:s.picker_shots[0].selected_video_uids,catalog:s.videos.map(v=>v.video_uid),scene:s.scene_path,
      frames:[host.querySelector('[data-picker-maya-frame-start]')?.textContent,host.querySelector('[data-picker-maya-frame-end]')?.textContent],
      rows:host.querySelectorAll('.outliner-row').length};};
  });
  const firstRow=page.locator('[data-picker-shot-layout="compact"][data-picker-shot-row="11111111-1111-4111-8111-000000000001"]');
  assert.equal(await page.locator('.hmbvp').getAttribute('data-picker-view'),'compact');
  assert.match(await firstRow.innerText(),/로동중\.\.\. 수정불가/,'Cold compact mount must hydrate an existing render');
  async function assertCheckedNumber(row) {
    const check=row.locator('.picker-shot-number[data-hmb-shot-check="true"]');
    assert.equal(await check.textContent(),'01');
    assert.match(await check.getAttribute('aria-label'),/검증 완료/);
    assert.deepEqual(await check.evaluate(el=>{
      const glyph=getComputedStyle(el,'::before');
      let parent=el;
      while(parent && getComputedStyle(parent).filter==='none' && getComputedStyle(parent).opacity==='1')parent=parent.parentElement;
      return [glyph.content,glyph.color,glyph.fontSize,parent?.className||''];
    }),['"✓"','rgb(74, 222, 128)','20px','']);
  }
  await assertCheckedNumber(firstRow);
  const headerVisibility=await page.evaluate(()=>{
    const actions=document.querySelector('[data-hmb-native-actions]');
    const group=document.createElement('section');
    for(const [status,color] of [['Resolved','green'],['Unresolved','blue'],['Running','orange'],['Error','red']]){
      const node=document.createElement('div');node.className='bg-'+color+'-600';
      const label=document.createElement('span');label.className='leading-none';label.textContent=status;
      node.append(label);group.append(node);
    }
    const button=document.createElement('button');button.textContent='Reset';group.append(button);
    actions.append(group);const display=Array.from(group.children,el=>getComputedStyle(el).display!=='none');
    group.remove();return display;
  });
  assert.deepEqual(headerVisibility,[false,false,true,true,true]);
  await page.evaluate(()=>controller.update({...props(initialPickerState),ui_options:{
    picker_shot_status:{...leasePacket,picker_shot_status_revision:2,shot_edit_locks:[],verified_shots:[]}}}));
  assert.equal(await firstRow.locator('.picker-shot-lock,[data-hmb-shot-check="true"]').count(),0);
  assert.equal(await firstRow.locator('[data-picker-shot-load]').isDisabled(),false);
  await page.evaluate(()=>controller.update({...props(initialPickerState),ui_options:{picker_shot_status:leasePacket}}));
  assert.equal(await firstRow.locator('.picker-shot-lock').count(),0,'Stale received metadata must not relock a completed shot');
  await page.evaluate(()=>controller.update({...props(initialPickerState),ui_options:{
    picker_shot_status:{...leasePacket,runtime_instance_id:'previous-desktop-runtime',picker_shot_status_revision:99}}}));
  assert.equal(await firstRow.locator('.picker-shot-lock').count(),0,'Restored metadata from another Desktop runtime must be ignored');
  await page.evaluate(()=>controller.update(props({...initialPickerState,state_writer:'widget',shot_edit_locks:[firstScope],verified_shots:[firstScope],picker_shot_status_revision:2})));
  assert.equal(await firstRow.locator('.picker-shot-lock').count(),0,'Echoed media edits cannot replace a displayed release');
  await page.evaluate(()=>controller.update(props({...initialPickerState,shot_edit_locks:[firstScope],verified_shots:[],picker_shot_status_revision:3})));
  assert.equal(await firstRow.locator('.picker-shot-lock').count(),1);
  assert.equal(await firstRow.locator('[data-hmb-shot-check="true"]').count(),0,'A render lock alone does not verify an input');
  await page.evaluate(()=>controller.update(props({...initialPickerState,shot_edit_locks:[firstScope],verified_shots:[firstScope],picker_shot_status_revision:4})));
  assert.match(await firstRow.innerText(),/로동중\.\.\. 수정불가/);
  assert.equal(await firstRow.locator('[data-picker-shot-load]').isDisabled(),true);
  await page.evaluate(()=>controller.update(props({...initialPickerState,state_revision:10})));
  assert.match(await firstRow.innerText(),/로동중\.\.\. 수정불가/);
  await assertCheckedNumber(firstRow);
  await page.evaluate(()=>{
    const third='11111111-1111-4111-8111-000000000003';
    const shot={workspace_uuid:third,bound_shot_uuid:third,number:3,name:'Shot 3',revision:1,video_asset_uids:[],selected_video_uids:[]};
    controller.update(props({...initialPickerState,state_revision:11,picker_shots:[...initialPickerState.picker_shots,shot],
      shot_selections:[...initialPickerState.shot_selections,{shot_uuid:third,number:3,name:shot.name,revision:1}]}));
  });
  assert.equal(await page.locator('[data-picker-shot-load="11111111-1111-4111-8111-000000000003"]').isEnabled(),true);
  assert.equal(await firstRow.locator('[data-picker-shot-load]').isDisabled(),true);
  if(await page.locator('.hmbvp').getAttribute('data-picker-view')!=='expanded')await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
  const lockedRow=page.locator('[data-picker-shot-row="11111111-1111-4111-8111-000000000001"]:visible').first();
  assert.match(await lockedRow.textContent(), /로동중\.\.\. 수정불가/);
  await assertCheckedNumber(lockedRow);
  assert.equal(await page.locator('.outliner-scroll:visible').evaluate(el=>el.inert),true);
  await page.locator('[data-picker-shot-activate="11111111-1111-4111-8111-000000000002"]').first().click();
  assert.equal(await page.locator('.outliner-scroll:visible').evaluate(el=>el.inert),false);
  await page.locator('#maya-scene-path').fill('C:/shots/second.mb');await page.locator('#maya-scene-path').dispatchEvent('change');
  await page.locator('#read-scene').click();
  const clicked=await page.evaluate(()=>{
    const transport=publications.findLast(p=>p.__hmb_picker_command__);window.command=transport.__hmb_picker_command__;
    window.backend={...structuredClone(transport),state_writer:'python',state_revision:transport.state_revision+1,state_published_at_ms:Date.now()+1,frontend_seen_revision:transport.state_revision,
      backend_ack_action_id:command.action_id,pending_action:'',pending_action_id:'',status:'READING_SCENE',scene_stage:'MAYA_READING',
      scene_path:command.payload.scene_path,scene_request_path:command.payload.scene_path,scene_draft_path:command.payload.scene_path,
      operation_kind:'read_scene',operation_started_at_ms:Date.now(),operation_finished_at_ms:0,active_process_pid:123};
    delete backend.__hmb_picker_command__;
    // An older progress owner carries the previous Shot's old media order.
    backend.picker_shots[0]={...backend.picker_shots[0],revision:1,selected_video_uids:['a','b'],preview_video_uid:'a'};
    return {action:command.action,target:command.payload.picker_shot_uuid,...inspect()};
  });
  assert.equal(clicked.action,'read_scene');assert.equal(clicked.target,'11111111-1111-4111-8111-000000000002');assert.equal(clicked.pending,true);
  const staleAck=await page.evaluate(()=>{controller.update(props({...backend,backend_ack_action_id:'earlier-read'}));return inspect();});
  assert.equal(staleAck.pending,true,'An older command ACK cannot release this READ');
  const progress=await page.evaluate(()=>{controller.update(props(backend));return inspect();});
  assert.equal(progress.pending,false);assert.equal(progress.status,'READING_SCENE');assert.equal(progress.generateDisabled,true);
  assert.deepEqual(progress.firstSelected,['b','a']);
  const terminal=await page.evaluate(()=>{
    const completed={...backend,state_revision:backend.state_revision+1,state_published_at_ms:Date.now()+2,status:'OUTLINER_READY',scene_stage:'OUTLINER_READY',
      operation_kind:'',active_process_pid:0,operation_finished_at_ms:Date.now()+1,native_read_ready:true,
      outliner_nodes:[{name:'FireflyAa1',full_path:'|FireflyAa1',maya_uuid:'new-root'}],cameras:[{name:'newCamera',full_path:'|newCamera'}],selected_camera:'|newCamera',camera:'|newCamera',
      start_frame:101,end_frame:186,current_frame:101,source_fps:24,output_fps:24,has_maya_frame_range:true};
    const started=performance.now();controller.update(props(completed));return {updateMs:performance.now()-started,...inspect()};
  });
  assert.equal(terminal.status,'OUTLINER_READY');assert.equal(terminal.stage,'OUTLINER_READY');assert.equal(terminal.ready,true);assert.equal(terminal.rootCount,1);
  assert.equal(terminal.pending,false);assert.equal(terminal.readDisabled,false);assert.equal(terminal.generateDisabled,false);assert.equal(terminal.rows,1);
  assert.deepEqual(terminal.frames,['101','186']);assert.deepEqual(terminal.firstSelected,['b','a']);assert.deepEqual(terminal.catalog,['a','b','c']);
  // A next command reads the completed pending state, not the old empty draft.
  await page.locator('#read-scene').click();
  const reload=await page.evaluate(()=>{const publication=publications.findLast(p=>p.__hmb_picker_command__);return {ready:publication.native_read_ready,roots:publication.outliner_nodes.length,scene:publication.__hmb_picker_command__.payload.scene_path};});
  assert.deepEqual(reload,{ready:true,roots:1,scene:'C:/shots/second.mb'});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,rawReceiptCases:5,coldCompactLock:true,staleRelockRejected:true,
    nativeHeaderStatuses:true,newCatalogShotEditable:true,actualReadClick:true,staleAckRejected:true,mediaOrderPreserved:true,completedReload:true,updateMs:terminal.updateMs}));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
