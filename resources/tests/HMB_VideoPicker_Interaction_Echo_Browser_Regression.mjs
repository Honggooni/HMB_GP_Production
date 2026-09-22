import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const source = fs.readFileSync(new URL('../../widgets/HMBVideoPickerLibraryWidget_v032.js', import.meta.url), 'utf8');
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); }
catch {
  try { playwright = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
  catch {
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === '1') throw new Error('Playwright required');
    console.log('Picker interaction echo browser: SKIP (Playwright unavailable)');process.exit(0);
  }
}
const executablePath = process.env.HMB_PICKER_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === '1') throw new Error('Browser required');
  console.log('Picker interaction echo browser: SKIP (browser unavailable)');process.exit(0);
}
const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0}#widget{width:1600px;min-height:1200px}</style><div id="widget"></div><script type="module">
import mount from '/widget.js';
window.host=document.getElementById('widget');window.publications=[];
window.props=value=>({value,onChange:next=>{window.publications.push(structuredClone(next));if(window.hold)return new Promise((resolve,reject)=>{window.heldReject=reject;});}});
window.start=value=>{window.controller?.cleanup();const fresh=document.createElement('div');fresh.id='widget';window.host.replaceWith(fresh);window.host=fresh;window.publications=[];window.controller=mount(window.host,window.props(value));};
window.live=()=>window.host.__hmbPickerPaintFirstState||window.host.__hmbPendingPickerState||window.host.__hmbAuthoritativePickerState;
window.oldEcho=value=>window.controller.update(window.props({...structuredClone(value),state_writer:'python',message:'Delayed progress',backend_ack_action_id:'progress-ack'}));
window.active=()=>window.host.querySelector('[data-picker-shot-activate][aria-pressed="true"]')?.getAttribute('data-picker-shot-activate');
window.ready=true;
</script>`;
const server = http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const shots = ['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','cccccccc-cccc-4ccc-8ccc-cccccccccccc','dddddddd-dddd-4ddd-8ddd-dddddddddddd','eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'];
const fixture = (media=false) => ({
  runtime_instance_id:'echo-browser-runtime',state_revision:10,state_writer:'python',language:'ko',
  scene_path:'C:/scene.mb',scene_request_path:'C:/scene.mb',native_read_ready:true,
  scene_stage:'OUTLINER_READY',status:'OUTLINER_READY',active_slot_count:1,
  shot_publisher_instance_uuid:'11111111-1111-4111-8111-111111111111',
  channel_uuid:'22222222-2222-4222-8222-222222222222',
  shot_uuid:shots[2],shot_number:3,shot_name:'Shot 3',active_picker_shot_uuid:shots[2],
  shot_selections:shots.map((uid,i)=>({shot_uuid:uid,number:i+1,name:'Shot '+(i+1),revision:1})),
  picker_shots:shots.map((uid,i)=>({workspace_uuid:uid,bound_shot_uuid:uid,number:i+1,name:'Shot '+(i+1),revision:1,
    video_asset_uids:media?[`s${i+1}-a`,`s${i+1}-b`]:[],selected_video_uids:media?[`s${i+1}-a`]:[],preview_video_uid:media?`s${i+1}-a`:''})),
  videos:media?shots.flatMap((uid,i)=>['a','b'].map(letter=>({video_uid:`s${i+1}-${letter}`,source_uid:`s${i+1}-${letter}`,
    video_path:`C:/fixture/s${i+1}-${letter}.mp4`,label:`Shot ${i+1} ${letter}`,picker_shot_uuid:uid,frame_count:24,fps:24}))):[],
  outliner_nodes:[{name:'Actor',full_path:'|Actor',maya_uuid:'root',depth_meshes:[{name:'Eye',full_path:'|Actor|Eye',maya_uuid:'eye'}]}],
  depth_settings:{range:'close',expanded_roots:['|Actor']},
});
let browser;
const failures=[];
try {
  browser=await playwright.chromium.launch({executablePath,headless:true});
  const page=await browser.newPage({viewport:{width:1700,height:1300}});
  const origin=`http://127.0.0.1:${server.address().port}`;
  await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
  page.on('pageerror',error=>failures.push('pageerror: '+error.message));
  page.setDefaultTimeout(5000);
  await page.goto(origin);await page.waitForFunction(()=>window.ready);
  const reset=async(media=false)=>{
    await page.evaluate(value=>window.start(value),fixture(media));
    if(await page.locator('.hmbvp').getAttribute('data-picker-view')!=='expanded') await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
    await page.waitForTimeout(140);
    await page.evaluate(()=>{window.publications=[];window.baseline=structuredClone(window.live());});
  };
  const check=async(name,body,media=false)=>{try{await reset(media);await body();console.log('PASS '+name);}catch(error){failures.push(name+': '+error.message);console.log('FAIL '+name+': '+error.message);}};
  await check('Shot 3 -> 1 retains navigation through delayed progress and duplicate ACK',async()=>{
    await page.locator(`[data-picker-shot-activate="${shots[0]}"]`).click();
    assert.equal(await page.evaluate(()=>window.active()),shots[0]);
    await page.waitForFunction(()=>window.publications.length>0);
    await page.evaluate(()=>window.oldEcho(window.baseline));
    assert.equal(await page.evaluate(()=>window.active()),shots[0],'old progress repainted Shot 3');
    await page.evaluate(()=>{const last=window.publications.at(-1);window.controller.update(window.props({...last,state_writer:'python',frontend_seen_revision:last.state_revision}));});
    await page.waitForTimeout(1600);
    await page.evaluate(()=>window.oldEcho(window.baseline));
    assert.equal(await page.evaluate(()=>window.active()),shots[0],'old response repainted after echo timeout');
  });
  await check('Rapid 3 -> 2 -> 1 keeps latest Shot during crossed exact echoes',async()=>{
    await page.locator(`[data-picker-shot-activate="${shots[1]}"]`).click();
    await page.waitForFunction(()=>window.publications.length===1);
    await page.locator(`[data-picker-shot-activate="${shots[0]}"]`).click();
    await page.waitForFunction(()=>window.publications.length===2);
    await page.evaluate(()=>{for(const index of [1,0,0])window.controller.update(window.props({...window.publications[index],state_writer:'python'}));});
    assert.equal(await page.evaluate(()=>window.active()),shots[0]);
    assert.equal(await page.evaluate(()=>window.live().active_picker_shot_uuid),shots[0],'next click starts from wrong Shot');
  });
  await check('All 20 directed Shot transitions preserve destination through old replies',async()=>{
    for(const from of shots)for(const to of shots) {
      if(from===to)continue;
      await page.locator(`[data-picker-shot-activate="${from}"]`).click();
      await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
      await page.evaluate(()=>{window.transitionOld=structuredClone(window.live());});
      await page.locator(`[data-picker-shot-activate="${to}"]`).click();
      assert.equal(await page.evaluate(()=>window.active()),to,`${from} -> ${to} immediate`);
      await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
      await page.evaluate(()=>window.oldEcho(window.transitionOld));
      assert.equal(await page.evaluate(()=>window.active()),to,`${from} -> ${to} stale`);
      assert.equal(await page.evaluate(()=>window.live().active_picker_shot_uuid),to);
      assert.equal(await page.evaluate(()=>window.live().preview_video_uid),`s${shots.indexOf(to)+1}-a`,'each Shot keeps its own preview');
    }
  },true);
  await check('All 120 rapid five-Shot permutations keep the last click',async()=>{
    const permutations=values=>values.length?values.flatMap((value,index)=>permutations(values.filter((_,i)=>i!==index)).map(tail=>[value,...tail])):[[]];
    for(const order of permutations(shots)) {
      const result=await page.evaluate(order=>{
        const old=structuredClone(window.live());
        for(const uid of order)window.host.querySelector('[data-picker-shot-activate="'+uid+'"]').click();
        window.oldEcho(old);
        return window.active();
      },order);
      assert.equal(result,order.at(-1));
      await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
      assert.equal(await page.evaluate(()=>window.active()),order.at(-1));
    }
  });
  await check('Outliner expansion persists through stale echo',async()=>{
    await page.locator('[data-depth-toggle-path="|Actor"]').click();
    await page.waitForFunction(()=>window.publications.length>0);
    const expected=await page.locator('[data-group-path="|Actor|Eye"]').count();
    await page.evaluate(()=>window.oldEcho(window.baseline));
    assert.equal(await page.locator('[data-group-path="|Actor|Eye"]').count(),expected);
  });
  await check('Eye visibility persists through stale echo',async()=>{
    await page.locator('[data-visibility-path="|Actor"]').click();
    await page.waitForFunction(()=>window.publications.length>0);
    const expected=await page.evaluate(()=>window.live().slot_visibility);
    await page.evaluate(()=>window.oldEcho(window.baseline));
    assert.deepEqual(await page.evaluate(()=>window.live().slot_visibility),expected);
  });
  await check('Tool tabs preserve latest mode and source-shot browsing',async()=>{
    await page.locator('[data-picker-tool-tab="concatenate"]').click();
    await page.locator(`[data-picker-shot-activate="${shots[0]}"]`).click();
    await page.evaluate(()=>window.oldEcho(window.baseline));
    assert.equal(await page.locator('.viewport-panel').getAttribute('data-picker-tool-mode'),'concatenate');
    assert.equal(await page.evaluate(()=>window.active()),shots[0]);
    assert.equal(await page.evaluate(()=>window.live().active_picker_shot_uuid),shots[2],'source browse must not move output owner');
    await page.locator('[data-picker-tool-tab="crop"]').click();
    await page.evaluate(()=>window.oldEcho(window.baseline));
    assert.equal(await page.locator('.viewport-panel').getAttribute('data-picker-tool-mode'),'crop');
  });
  await check('Output checkboxes and resolution retain choices through stale echo',async()=>{
    for(const id of ['original-preview-toggle','mask-playblast-toggle','depth-playblast-toggle','motion-guide-toggle']) {
      const before=await page.locator('#'+id).isChecked();
      await page.locator('#'+id).setChecked(!before);
      await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
      await page.evaluate(()=>window.oldEcho(window.baseline));
      assert.equal(await page.locator('#'+id).isChecked(),!before,id);
    }
    await page.locator('#playblast-resolution').selectOption('1920x1080');
    await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
    await page.evaluate(()=>window.oldEcho(window.baseline));
    assert.equal(await page.locator('#playblast-resolution').inputValue(),'1920x1080');
  });
  await check('Rejected older Shot change cannot overwrite a newer pending choice',async()=>{
    await page.evaluate(()=>{window.hold=true;window.heldReject=null;});
    await page.locator(`[data-picker-shot-activate="${shots[1]}"]`).click();
    await page.waitForFunction(()=>!!window.heldReject);
    const immediate=await page.evaluate(async uid=>{
      window.hold=false;
      window.host.querySelector('[data-picker-shot-activate="'+uid+'"]').click();
      window.heldReject(new Error('older shot publication rejected'));
      await Promise.resolve();await Promise.resolve();await Promise.resolve();
      return window.active();
    },shots[0]);
    assert.equal(immediate,shots[0]);
    await page.waitForFunction(()=>window.publications.length===2);
    assert.equal(await page.evaluate(()=>window.active()),shots[0]);
  });
  await check('All five Shots keep card selections and compact/expanded view through crossed responses',async()=>{
    for(const [index,shot] of shots.entries()) {
      await page.locator(`[data-picker-shot-activate="${shot}"]`).click();
      await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
      await page.evaluate(()=>{window.cardOld=structuredClone(window.live());});
      await page.locator(`[data-toggle-video-uid="s${index+1}-b"]`).click();
      await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
      await page.evaluate(()=>window.oldEcho(window.cardOld));
      assert.equal(await page.locator(`[data-toggle-video-uid="s${index+1}-b"]`).getAttribute('aria-pressed'),'true');
      assert.equal(await page.evaluate(()=>window.active()),shot);
    }
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
    await page.waitForFunction(()=>window.host.querySelector('.hmbvp')?.dataset.pickerView==='compact');
    assert.equal(await page.locator('.hmbvp').getAttribute('data-picker-view'),'compact');
    await page.evaluate(()=>window.oldEcho(window.cardOld));
    assert.equal(await page.locator('.hmbvp').getAttribute('data-picker-view'),'compact');
    for(const [index,shot] of shots.entries()) {
      assert.equal(await page.locator(`[data-picker-shot-row="${shot}"] [data-toggle-video-uid="s${index+1}-b"]`).getAttribute('aria-pressed'),'true');
    }
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
    await page.waitForFunction(()=>window.host.querySelector('.hmbvp')?.dataset.pickerView==='expanded');
    assert.equal(await page.locator('.hmbvp').getAttribute('data-picker-view'),'expanded');
  },true);
  await check('Generate captures every selected Shot and current Maya file before state ACK',async()=>{
    for(const replaceFile of [false,true])for(const [index,shot] of shots.entries()) {
      const scene=replaceFile?`C:/replacement-${index+1}.mb`:'C:/loaded-on-shot-1.mb';
      const value={...fixture(),active_picker_shot_uuid:shots[0],scene_path:scene,scene_request_path:scene,
        scene_draft_path:scene,camera:'camera1',selected_camera:'camera1',cameras:[{name:'camera1',full_path:'camera1'}],
        start_frame:101,end_frame:148,source_fps:24,output_fps:24,output_width:1280,output_height:720,
        mask_enabled:true,slot_assignments:[{video_slot:1,bindings:[{full_dag_path:'|Actor',maya_uuid:'root',color:'Red'}]}]};
      await page.evaluate(value=>window.start(value),value);
      if(await page.locator('.hmbvp').getAttribute('data-picker-view')!=='expanded') {
        await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
        await page.waitForFunction(()=>window.host.querySelector('.hmbvp')?.dataset.pickerView==='expanded');
      }
      assert.equal(await page.locator('#run-video').isEnabled(),true);
      // All clicks occur in one browser turn: the navigation has painted but
      // the deferred state publication has not happened. The command must
      // flush that latest choice and not use the original Shot 1 READ owner.
      const command=await page.evaluate(shot=>{
        const old=structuredClone(window.live());
        window.host.querySelector('[data-picker-shot-activate="'+shot+'"]').click();
        window.oldEcho(old);
        window.host.querySelector('#run-video').click();
        return window.publications.find(value=>value.__hmb_picker_command__)?.__hmb_picker_command__;
      },shot);
      assert.equal(command?.action,'run_video');
      assert.equal(command.payload.picker_shot_uuid,shot);
      assert.equal(command.payload.scene_path,scene);
      assert.equal(command.payload.authoring_state.selected_camera,'camera1');
      assert.equal(command.payload.authoring_state.slot_assignments[0].bindings[0].color,'Red');
      assert.equal(await page.evaluate(()=>window.active()),shot);
    }
  });
  await page.evaluate(()=>window.controller.cleanup());
  assert.deepEqual(failures,[]);
  console.log('Picker interaction echo browser: PASS');
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
