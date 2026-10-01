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
window.mountPicker=mount;
window.props=value=>({value,onChange:next=>{window.publications.push(structuredClone(next));if(window.hold)return new Promise((resolve,reject)=>{window.heldReject=reject;});}});
window.start=value=>{window.controller?.cleanup();const fresh=document.createElement('div');fresh.id='widget';window.host.replaceWith(fresh);window.host=fresh;window.publications=[];window.controller=mount(window.host,window.props(value));};
window.live=()=>window.host.__hmbPickerPaintFirstState||window.host.__hmbPendingPickerState||window.host.__hmbAuthoritativePickerState;
window.oldEcho=value=>window.controller.update(window.props({...structuredClone(value),state_writer:'python',message:'Delayed progress',backend_ack_action_id:'progress-ack'}));
window.active=()=>window.host.querySelector('[data-picker-shot-activate][aria-pressed="true"]')?.getAttribute('data-picker-shot-activate');
window.viewportSnapshot=()=>{
  const live=window.live(),media=window.host.__hmbVideoPickerExpanded===true
    ?window.host.querySelector('#picker-video'):window.host.__hmbCompactSharedVideoPlayer;
  return {mode:window.host.querySelector('.viewport-panel')?.getAttribute('data-picker-tool-mode'),
    liveMode:live.video_tools_by_shot?.[live.active_picker_shot_uuid]?.active_tool||'preview',
    preview:live.preview_video_uid,src:media?.getAttribute('src')||'',uid:media?.getAttribute('data-video-uid')||''};
};
window.observeViewport=()=>{
  window.viewportObserver?.disconnect();window.viewportChanges=[];
  window.viewportObserver=new MutationObserver(records=>{
    records.forEach((record,index)=>{
      if(record.type==='attributes'){
        const name=record.attributeName;
        if(name==='data-picker-tool-mode'&&!record.target.matches('.viewport-panel'))return;
        const activeMedia=window.host.__hmbVideoPickerExpanded===true
          ?record.target.matches('#picker-video'):record.target===window.host.__hmbCompactSharedVideoPlayer;
        if(name!=='data-picker-tool-mode'&&!activeMedia)return;
        // Reading only the final attribute loses an A -> B flash in one turn.
        // The next record's oldValue is the value written by this mutation.
        const following=records.slice(index+1).find(next=>next.type==='attributes'&&next.target===record.target&&next.attributeName===name);
        window.viewportChanges.push({name,value:following?following.oldValue:record.target.getAttribute(name)});
      }else for(const added of record.addedNodes){
        if(added.nodeType!==1)continue;
        for(const element of [added,...added.querySelectorAll('.viewport-panel,#picker-video,.compact-shared-video-player')]){
          if(element.matches('.viewport-panel'))window.viewportChanges.push({name:'data-picker-tool-mode',value:element.getAttribute('data-picker-tool-mode')});
          const activeMedia=window.host.__hmbVideoPickerExpanded===true
            ?element.matches('#picker-video'):element===window.host.__hmbCompactSharedVideoPlayer;
          if(activeMedia)for(const name of ['src','data-video-uid'])window.viewportChanges.push({name,value:element.getAttribute(name)});
        }
      }
    });
  });
  window.viewportObserver.observe(window.host,{subtree:true,childList:true,attributes:true,attributeOldValue:true,attributeFilter:['src','data-video-uid','data-picker-tool-mode']});
};
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
const crossedEchoFixture=()=>{
  const value=fixture(true),row=value.picker_shots[2];
  row.video_asset_uids.push('s3-c');
  value.videos.push({video_uid:'s3-c',source_uid:'s3-c',video_path:'C:/fixture/s3-c.mp4',
    label:'Shot 3 c',picker_shot_uuid:shots[2],frame_count:24,fps:24});
  value.video_tools_by_shot={[shots[2]]:{active_tool:'preview',revision:1,
    concatenate:{inputs:['C:/fixture/s3-b.mp4'],input_uids:['s3-b']},
    crop:{input:'C:/fixture/s3-c.mp4',source_uid:'s3-c'}}};
  return value;
};
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
    await page.evaluate(value=>window.start(value),typeof media==='object'?media:fixture(media));
    if(await page.locator('.hmbvp').getAttribute('data-picker-view')!=='expanded') await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
    await page.waitForTimeout(140);
    await page.evaluate(()=>{window.publications=[];window.baseline=structuredClone(window.live());});
  };
  const check=async(name,body,media=false)=>{try{await reset(media);await body();console.log('PASS '+name);}catch(error){failures.push(name+': '+error.message);console.log('FAIL '+name+': '+error.message);}};
  const publishChoice=async selector=>{
    const before=await page.evaluate(()=>window.publications.length);
    await page.locator(selector).click();
    await page.waitForFunction(count=>window.publications.length>count&&!window.host.__hmbPickerPaintFirstState,before);
    return page.evaluate(()=>structuredClone(window.publications.at(-1)));
  };
  const acknowledgeSetup=async value=>{
    await page.evaluate(value=>{
      window.controller.update(window.props({...structuredClone(value),state_writer:'python'}));
      window.publications=[];
    },value);
  };
  const probeCrossedExactEchoes=async publications=>page.evaluate(async values=>{
    const expected=window.viewportSnapshot();
    const queue=window.host.__hmbPendingPickerStateEchoes||[];
    const queued=values.map(value=>queue.some(entry=>entry.revision===value.state_revision&&entry.publishedAtMs===value.state_published_at_ms));
    window.observeViewport();
    const snapshots=[];
    // These exact Python echoes must arrive while all publications are still
    // in the 1.5-second disposable-echo queue, newest ACK before delayed old ACK.
    for(const value of [...values].reverse()){
      window.controller.update(window.props({...structuredClone(value),state_writer:'python'}));
      snapshots.push({event:'exact '+value.state_revision,...window.viewportSnapshot()});
    }
    // A DOM-noop must not secretly replace controller authority. A subsequent
    // functional progress response exposes that hidden regression on repaint.
    for(const value of values.slice(0,-1)){
      window.oldEcho(value);
      snapshots.push({event:'stale progress '+value.state_revision,...window.viewportSnapshot()});
    }
    window.controller.update(window.props({...structuredClone(values[0]),state_writer:'python',
      message:'Next delayed progress',backend_ack_action_id:'next-progress-ack'}));
    snapshots.push({event:'next stale update',...window.viewportSnapshot()});
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    snapshots.push({event:'after media/update frames',...window.viewportSnapshot()});
    window.viewportObserver.disconnect();
    return {expected,queued,snapshots,changes:window.viewportChanges,backendMessage:window.live().message};
  },publications);
  const assertLatestViewport=(result,label)=>{
    assert.ok(result.queued.every(Boolean),label+': exact publications were not all inside the 1.5-second echo queue');
    assert.equal(result.backendMessage,'Next delayed progress',label+': backend progress was swallowed');
    for(const actual of result.snapshots){
      for(const key of ['mode','liveMode','preview','src','uid'])assert.equal(actual[key],result.expected[key],`${label}: ${actual.event} regressed ${key}`);
    }
    for(const change of result.changes){
      const expected=change.name==='data-picker-tool-mode'?result.expected.mode:change.name==='src'?result.expected.src:result.expected.uid;
      assert.equal(change.value||'',expected||'',`${label}: transient ${change.name} changed to ${change.value}`);
    }
  };
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
  await check('Crop tool paints directly without an intermediate Output or Concatenate mode',async()=>{
    await page.locator('[data-picker-tool-tab="concatenate"]').click();
    await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
    await page.evaluate(()=>{
      window.beforeCrop=structuredClone(window.live());
      window.toolModes=[];
      const panel=window.host.querySelector('.viewport-panel');
      window.toolModeObserver=new MutationObserver(()=>{
        window.toolModes.push(panel.getAttribute('data-picker-tool-mode'));
      });
      window.toolModeObserver.observe(panel,{attributes:true,attributeFilter:['data-picker-tool-mode']});
    });
    await page.locator('[data-picker-tool-tab="crop"]').click();
    await page.evaluate(()=>window.oldEcho(window.beforeCrop));
    await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
    const modes=await page.evaluate(()=>{
      window.toolModeObserver.disconnect();
      return [...window.toolModes,window.host.querySelector('.viewport-panel').getAttribute('data-picker-tool-mode')];
    });
    assert.ok(modes.length>0);
    assert.deepEqual([...new Set(modes)],['crop'],`intermediate tool modes: ${modes}`);
    assert.equal(await page.locator('[data-picker-tool-tab="crop"]').getAttribute('aria-pressed'),'true');
  },true);
  await check('Crop mode survives a host row replacement before deferred publication',async()=>{
    await page.locator('[data-picker-tool-tab="concatenate"]').click();
    await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
    const first=await page.evaluate(()=>{
      const old=structuredClone(window.live());
      window.host.querySelector('[data-picker-tool-tab="crop"]').click();
      const before=window.host.querySelector('.viewport-panel')?.getAttribute('data-picker-tool-mode');
      window.controller=window.mountPicker(window.host,window.props(old));
      return {before,after:window.host.querySelector('.viewport-panel')?.getAttribute('data-picker-tool-mode')};
    });
    assert.equal(first.before,'crop');
    await page.waitForFunction(()=>!!window.host.querySelector('.viewport-panel'));
    assert.equal(await page.locator('.viewport-panel').getAttribute('data-picker-tool-mode'),'crop',`first remount mode: ${JSON.stringify(first)}`);
    await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
    assert.equal(await page.locator('.viewport-panel').getAttribute('data-picker-tool-mode'),'crop');
  },true);
  await check('Crossed same-tool-revision stale echo cannot repaint another tab',async()=>{
    await page.locator('[data-picker-tool-tab="concatenate"]').click();
    await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
    await page.locator('[data-picker-tool-tab="crop"]').click();
    await page.waitForFunction(()=>!window.host.__hmbPickerPaintFirstState);
    const mode=await page.evaluate(()=>{
      const fresh=structuredClone(window.live());
      const stale=structuredClone(fresh);
      stale.video_tools_by_shot[stale.active_picker_shot_uuid].active_tool='concatenate';
      stale.state_revision=Math.max(0,Number(fresh.state_revision||0)-1);
      stale.state_published_at_ms=Math.max(0,Number(fresh.state_published_at_ms||0)-1);
      stale.state_writer='python';
      window.controller.update(window.props(stale));
      return window.host.querySelector('.viewport-panel')?.getAttribute('data-picker-tool-mode');
    });
    assert.equal(mode,'crop');
  },true);
  for(const from of ['preview','concatenate','crop'])for(const to of ['preview','concatenate','crop']){
    if(from===to)continue;
    await check(`Exact ACK ${to} then delayed ${from} cannot regress tab or source`,async()=>{
      const setup=['preview','concatenate','crop'].find(mode=>mode!==from&&mode!==to);
      await acknowledgeSetup(await publishChoice(`[data-picker-tool-tab="${setup}"]`));
      const first=await publishChoice(`[data-picker-tool-tab="${from}"]`);
      const latest=await publishChoice(`[data-picker-tool-tab="${to}"]`);
      const result=await probeCrossedExactEchoes([first,latest]);
      assert.equal(result.expected.mode,to);
      assert.notEqual(first.video_tools_by_shot[shots[2]].active_tool,latest.video_tools_by_shot[shots[2]].active_tool);
      assertLatestViewport(result,`${from} -> ${to}`);
    },crossedEchoFixture());
  }
  const cardUids=['s3-a','s3-b','s3-c'];
  const setupCard=async uid=>{
    if(await page.evaluate(()=>window.live().preview_video_uid)===uid){
      const other=cardUids.find(candidate=>candidate!==uid);
      await acknowledgeSetup(await publishChoice(`[data-play-video-uid="${other}"]`));
    }
    await acknowledgeSetup(await publishChoice(`[data-play-video-uid="${uid}"]`));
  };
  for(const firstUid of cardUids)for(const latestUid of cardUids){
    if(firstUid===latestUid)continue;
    await check(`Play exact ACK ${latestUid} then delayed ${firstUid} never restores old media`,async()=>{
      const setupUid=cardUids.find(uid=>uid!==firstUid&&uid!==latestUid);
      await setupCard(setupUid);
      const first=await publishChoice(`[data-play-video-uid="${firstUid}"]`);
      const latest=await publishChoice(`[data-play-video-uid="${latestUid}"]`);
      const result=await probeCrossedExactEchoes([first,latest]);
      assert.equal(result.expected.preview,latestUid);
      assert.equal(result.expected.mode,'preview');
      assert.ok(result.expected.src.includes(latestUid+'.mp4'),'latest card owns the media source');
      assertLatestViewport(result,`${firstUid} -> ${latestUid}`);
    },crossedEchoFixture());
  }
  for(const firstUid of cardUids)for(const secondUid of cardUids){
    if(firstUid===secondUid)continue;
    const latestUid=cardUids.find(uid=>uid!==firstUid&&uid!==secondUid);
    await check(`Three-card Play ${firstUid} -> ${secondUid} -> ${latestUid} keeps newest ACK authority`,async()=>{
      await setupCard(latestUid);
      const publications=[];
      for(const uid of [firstUid,secondUid,latestUid])publications.push(await publishChoice(`[data-play-video-uid="${uid}"]`));
      const result=await probeCrossedExactEchoes(publications);
      assert.equal(result.expected.preview,latestUid);
      assert.ok(result.expected.src.includes(latestUid+'.mp4'),'third card owns the media source');
      assertLatestViewport(result,`${firstUid} -> ${secondUid} -> ${latestUid}`);
    },crossedEchoFixture());
  }
  await check('Backend progress and terminal error remain live after obsolete exact Play ACK',async()=>{
    await setupCard('s3-c');
    const first=await publishChoice('[data-play-video-uid="s3-a"]');
    const latest=await publishChoice('[data-play-video-uid="s3-b"]');
    const result=await probeCrossedExactEchoes([first,latest]);
    const backend=await page.evaluate(latest=>{
      const before=Number(window.host.__hmbPickerEchoNoopCount||0);
      window.controller.update(window.props({...structuredClone(latest),state_writer:'python',
        state_revision:latest.state_revision+1,message:'Backend progress still live',
        activity_log:[{level:'INFO',message:'Backend progress still live'}]}));
      const progress={message:window.live().message,log:window.host.querySelector('#activity-log-view')?.textContent||''};
      window.controller.update(window.props({...structuredClone(latest),state_writer:'python',
        state_revision:latest.state_revision+2,status:'ERROR',message:'Backend terminal error still live',
        activity_log:[{level:'ERROR',message:'Backend terminal error still live'}]}));
      return {before,after:Number(window.host.__hmbPickerEchoNoopCount||0),progress,
        error:{status:window.live().status,message:window.live().message,
          log:window.host.querySelector('#activity-log-view')?.textContent||''}};
    },latest);
    assert.equal(backend.progress.message,'Backend progress still live');
    assert.ok(backend.progress.log.includes('Backend progress still live'));
    assert.equal(backend.error.status,'ERROR');
    assert.equal(backend.error.message,'Backend terminal error still live');
    assert.ok(backend.error.log.includes('Backend terminal error still live'));
    assert.equal(backend.after,backend.before,'real backend updates must not use disposable echo shortcut');
    assertLatestViewport(result,'backend updates after Play ACK');
  },crossedEchoFixture());
  await check('Compact three-card replay keeps newest media through crossed exact ACKs and progress',async()=>{
    await setupCard('s3-c');
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
    await page.waitForFunction(()=>window.host.querySelector('.hmbvp')?.dataset.pickerView==='compact');
    const publications=[];
    for(const uid of cardUids)publications.push(await publishChoice(`[data-play-video-uid="${uid}"]`));
    const result=await probeCrossedExactEchoes(publications);
    assert.equal(result.expected.preview,'s3-c');
    assert.ok(result.expected.src.includes('s3-c.mp4'),'compact shared player owns the newest source');
    assertLatestViewport(result,'compact A -> B -> C');
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent('dblclick');
    await page.waitForFunction(()=>window.host.querySelector('.hmbvp')?.dataset.pickerView==='expanded');
    assert.equal(await page.evaluate(()=>window.live().preview_video_uid),'s3-c','expanding must retain compact replay authority');
    assert.ok((await page.locator('#picker-video').getAttribute('src')).includes('s3-c.mp4'));
  },crossedEchoFixture());
  await check('Crop intent owns media pause before any old-mode media event',async()=>{
    const installed=await page.evaluate(()=>{
      const media=window.host.querySelector('#picker-video');
      if(!media)return false;
      window.pauseModes=[];
      const original=media.pause.bind(media);
      media.pause=()=>{
        const live=window.live();
        window.pauseModes.push(live.video_tools_by_shot?.[live.active_picker_shot_uuid]?.active_tool||'preview');
        return original();
      };
      return true;
    });
    assert.equal(installed,true);
    await page.locator('[data-picker-tool-tab="crop"]').click();
    const modes=await page.evaluate(()=>window.pauseModes);
    assert.ok(modes.length>0);
    assert.deepEqual([...new Set(modes)],['crop']);
    await page.locator('[data-picker-tool-tab="crop"]').click();
    const reselectedModes=await page.evaluate(()=>window.pauseModes);
    assert.ok(reselectedModes.length>modes.length,'reselecting Crop still pauses media');
    assert.deepEqual([...new Set(reselectedModes)],['crop']);
  },true);
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
