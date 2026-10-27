import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const source=fs.readFileSync(path.join(root,'widgets/HMBFinishLookLibraryWidget.js'),'utf8');
const report=path.join(root,'reports/ui-responsive-v804-20261015/finish');fs.mkdirSync(report,{recursive:true});
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
const receipt={schema:'hmb-finish-unified-widget',external_requests:0,paid_calls:0,graph_calls:0,cases:[]};
try{
 const page=await browser.newPage({viewport:{width:1080,height:800}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',route=>{receipt.external_requests++;return route.abort();});
 await page.setContent('<style>body{background:#080b12;margin:20px}.react-flow__node{width:980px;height:640px;box-sizing:border-box;padding-top:48px}#mount{height:900px;width:100%;}</style><div class="react-flow__node"><div id="mount"></div></div>');
 await page.evaluate(async source=>{
  window.widget=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
  window.catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:'publisher',channel_uuid:'channel',generation:1,metadata_sha256:'a'.repeat(64),shots:[1,2,3,4,5].map(n=>({shot_uuid:'uuid-'+n,number:n,name:'Renamed asset '+n+' long project shot',revision:0}))};
  window.initial=widget.hmbNormalizeFinishLookWidgetValue({shot_manager:true,shot_catalog:catalog,shot:{channel_uuid:'channel',...catalog.shots[0]}});
  initial.finish_look.beauty.enabled=true;
  initial.shot_documents=Object.fromEntries(catalog.shots.map(row=>{const state=structuredClone(initial.finish_look);state.beauty.brightness=row.number/2;return ['channel\x1f'+row.shot_uuid,state];}));
  initial.finish_look=structuredClone(initial.shot_documents['channel\x1fuuid-1']);
  window.calls=[];window.requests=[];window.mount=document.querySelector('#mount');
  window.props={value:initial,onChange:value=>{calls.push(structuredClone(value));return new Promise((resolve,reject)=>requests.push({resolve,reject}));}};
  window.controller=widget.default(mount,props);window.originalRoot=mount.querySelector('.hmb-finish-look');window.originalRanges=Array.from(mount.querySelectorAll('[data-finish-step]'));
 },source);
 await page.waitForTimeout(100);
 assert.equal(await page.locator('[data-finish-shot]').count(),5);assert.equal(await page.locator('.hmb-finish-look__content').count(),1);
 assert.equal(await page.locator('[data-shot-selector]').isVisible(),false);assert.equal(await page.locator('[data-finish-step]').count(),11);
 assert.equal(await page.evaluate(()=>Object.values(widget.HMB_FINISH_LOOK_STEPS).reduce((total,list)=>total+list.length,0)),62);
 receipt.cases.push('five named top tabs and one original Beauty body; eleven controls and sixty-two stops retained');
 await page.locator('[data-finish-shot="uuid-4"]').click();
 assert.equal(await page.locator('[data-finish-shot="uuid-4"]').getAttribute('aria-pressed'),'true');
 await page.waitForFunction(()=>calls.length===1);
 assert.equal(await page.evaluate(()=>calls.at(-1).finish_look.beauty.brightness),2);
 assert.equal(await page.evaluate(()=>mount.querySelector('.hmb-finish-look')===originalRoot&&originalRanges.every((item,index)=>item===mount.querySelectorAll('[data-finish-step]')[index])),true);
 await page.evaluate(()=>controller.update({...props,value:structuredClone(initial)}));
 assert.equal(await page.locator('[data-finish-shot="uuid-4"]').getAttribute('aria-pressed'),'true');
 await page.evaluate(()=>{window.acked=structuredClone(calls.at(-1));controller.update({...props,value:acked});requests.at(-1).reject(Error('late transport rejection'));});
 await page.waitForTimeout(0);assert.equal(await page.locator('[data-finish-shot="uuid-4"]').getAttribute('aria-pressed'),'true');
 receipt.cases.push('UUID switch reads its stored values, keeps control IDs and blocks stale selection plus superseded rejection');
 const stable=await page.evaluate(async()=>{
  const mutations=[];const observer=new MutationObserver(records=>mutations.push(...records));observer.observe(mount,{subtree:true,attributes:true,childList:true,characterData:true});const before=calls.length;
  for(let index=0;index<300;index++)controller.update({...props,value:structuredClone(acked)});
  await Promise.resolve();observer.disconnect();return {mutations:mutations.length,commands:calls.length-before};
 });
 assert.deepEqual(stable,{mutations:0,commands:0});receipt.cases.push('300 identical echoes produce zero DOM changes and zero commands');
 await page.evaluate(()=>{window.locked={...structuredClone(acked),remote_connected:true};controller.update({...props,value:locked});});
 assert.equal(await page.locator('[data-enable="beauty"]').isDisabled(),true);
 assert.equal(await page.locator('[data-finish-shot="uuid-2"]').isDisabled(),false);
 await page.locator('[data-finish-shot="uuid-2"]').click();await page.waitForFunction(()=>calls.length===2);assert.equal(await page.evaluate(()=>calls.at(-1).finish_look.beauty.brightness),1);
 receipt.cases.push('REMOTE locks authoring and permits selecting other stored Shot values');
 const heights=[];
 for(const [width,height] of [[980,640],[520,420],[330,300]]){
  await page.evaluate(({width,height})=>{const node=document.querySelector('.react-flow__node');node.style.width=width+'px';node.style.height=height+'px';},{width,height});await page.waitForTimeout(80);
  const geometry=await page.evaluate(()=>{
    const scroll=mount.querySelector('.hmb-finish-look__scroll'),header=mount.querySelector('.hmb-finish-look__topbar'),tabs=mount.querySelector('.hmb-finish-look__shot-tabs');
    const rect=element=>{const r=element.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height};};
    const snapshots=[];
    for(const position of ['top','bottom']){
      scroll.scrollTop=position==='top'?0:scroll.scrollHeight;
      snapshots.push({position,header:rect(header),tabs:rect(tabs),viewport:rect(scroll),buttons:Array.from(mount.querySelectorAll('[data-finish-shot]')).map(rect),last:rect(mount.querySelector('[data-finish-step="beauty.reduce_shine"]'))});
    }
    const last=mount.querySelector('[data-finish-step="beauty.reduce_shine"]');const viewport=rect(scroll),control=rect(last);
    scroll.scrollTop+=control.top-viewport.top-Math.max(0,(viewport.height-control.height)/2);
    return {node:rect(document.querySelector('.react-flow__node')),host:rect(mount),snapshots,reachedLast:rect(last),scrollable:scroll.scrollHeight>=scroll.clientHeight,overflowX:scroll.scrollWidth-scroll.clientWidth};
  });
  const reason=JSON.stringify(geometry);assert.ok(geometry.host.bottom<=geometry.node.bottom+1,reason);assert.ok(geometry.overflowX<=1,reason);
  for(const snapshot of geometry.snapshots){
    assert.equal(snapshot.buttons.length,5);assert.ok(snapshot.header.top>=geometry.host.top-1&&snapshot.header.bottom<=geometry.host.bottom+1,reason);
    assert.ok(snapshot.tabs.top>=snapshot.header.bottom-1&&snapshot.tabs.bottom<=snapshot.viewport.top+1,reason);
    assert.ok(snapshot.viewport.height>=48,reason);
    for(const button of snapshot.buttons){assert.ok(button.top>=snapshot.header.bottom-1&&button.bottom<=snapshot.viewport.top+1,reason);assert.ok(button.left>=geometry.host.left-1&&button.right<=geometry.host.right+1,reason);}
  }
  assert.deepEqual(geometry.snapshots[0].header,geometry.snapshots[1].header,'Body scrolling moved the fixed header');
  assert.deepEqual(geometry.snapshots[0].buttons,geometry.snapshots[1].buttons,'Body scrolling moved or obscured a named Shot tab');
  assert.ok(geometry.reachedLast.top>=geometry.snapshots[0].viewport.top-1&&geometry.reachedLast.bottom<=geometry.snapshots[0].viewport.bottom+1,reason);heights.push(geometry);
 }
 receipt.cases.push('desktop, narrow and small heights keep header and all five tabs fixed above a non-overlapping body at both scroll limits; last control remains reachable');
 await page.screenshot({path:path.join(report,'finish-narrow-tabs.png')});
 await page.evaluate(()=>{mount.querySelector('.hmb-finish-look__scroll').scrollTop=0;});
 await page.screenshot({path:path.join(report,'finish-narrow-tabs-top.png')});
 await page.evaluate(()=>{const scroll=mount.querySelector('.hmb-finish-look__scroll');scroll.scrollTop=scroll.scrollHeight;});
 await page.screenshot({path:path.join(report,'finish-narrow-tabs-bottom.png')});
 const count=await page.evaluate(()=>{const before=calls.length;const button=mount.querySelector('[data-finish-shot="uuid-1"]');controller.cleanup();button.click();return {calls:calls.length-before,maxHeight:mount.style.maxHeight,rows:mount.querySelectorAll('[data-finish-shot]').length};});
 assert.deepEqual(count,{calls:0,maxHeight:'',rows:0});assert.deepEqual(errors,[]);assert.equal(receipt.external_requests,0);
 receipt.cases.push('cleanup removes listeners, resize observer ownership and viewport styles');receipt.passed=true;
 const performanceResult=await page.evaluate(async()=>{
  const host=document.createElement('div');host.style.cssText='width:980px;height:991px';document.body.append(host);
  const events=[],sent=[],failed=[];let start=0,block=100;
  const slowProps={value:structuredClone(initial),onChange:value=>{
    const entered=performance.now();events.push({phase:'host_callback_entry',elapsed_ms:entered-start,pressed:host.querySelector('[aria-pressed="true"]').dataset.finishShot});
    sent.push(structuredClone(value));while(performance.now()-entered<block){};
    return new Promise((resolve,reject)=>failed.push({resolve,reject}));
  }};
  let live=widget.default(host,slowProps);await new Promise(resolve=>requestAnimationFrame(resolve));
  start=performance.now();host.querySelector('[data-finish-shot="uuid-4"]').click();
  events.push({phase:'click_return',elapsed_ms:performance.now()-start,pressed:host.querySelector('[aria-pressed="true"]').dataset.finishShot});
  await new Promise(resolve=>requestAnimationFrame(()=>{events.push({phase:'first_animation_frame',elapsed_ms:performance.now()-start,pressed:host.querySelector('[aria-pressed="true"]').dataset.finishShot});resolve();}));
  await new Promise(resolve=>setTimeout(resolve,150));
  const selected=host.querySelector('[data-finish-shot="uuid-4"]'),other=host.querySelector('[data-finish-shot="uuid-1"]');
  const contrast={selectedBorder:getComputedStyle(selected).borderLeftColor,selectedShadow:getComputedStyle(selected).boxShadow,unselectedBorder:getComputedStyle(other).borderLeftColor,headerRgb:getComputedStyle(host.querySelector('.hmb-finish-look')).getPropertyValue('--hmb-mode-rgb').trim()};
  live.cleanup();sent.length=0;failed.length=0;block=0;live=widget.default(host,slowProps);
  for(const number of [5,4,3])host.querySelector('[data-finish-shot="uuid-'+number+'"]').click();
  const rapidImmediate={selected:host.querySelector('[aria-pressed="true"]').dataset.finishShot,sent:sent.length};
  await new Promise(resolve=>setTimeout(resolve,60));const coalesced=sent.map(value=>value.shot.shot_uuid);
  failed[0].reject(Error('coalesced save rejected'));await Promise.resolve();await Promise.resolve();
  const failedSelection=host.querySelector('[aria-pressed="true"]').dataset.finishShot;
  live.cleanup();sent.length=0;failed.length=0;live=widget.default(host,slowProps);
  host.querySelector('[data-finish-shot="uuid-4"]').click();
  const toggle=host.querySelector('[data-enable="beauty"]');toggle.checked=false;toggle.dispatchEvent(new Event('change',{bubbles:true}));
  const editOrder=sent.map(value=>({shot:value.shot.shot_uuid,enabled:value.finish_look.beauty.enabled}));
  live.cleanup();sent.length=0;failed.length=0;
  live=widget.default(host,{...slowProps,onChange:value=>{sent.push(structuredClone(value));throw Error('selection unavailable');}});
  host.querySelector('[data-finish-shot="uuid-4"]').click();
  const rejectedToggle=host.querySelector('[data-enable="beauty"]');rejectedToggle.checked=false;rejectedToggle.dispatchEvent(new Event('change',{bubbles:true}));
  const rejectedEdit={selected:host.querySelector('[aria-pressed="true"]').dataset.finishShot,sent:sent.map(value=>({shot:value.shot.shot_uuid,enabled:value.finish_look.beauty.enabled}))};
  live.cleanup();sent.length=0;failed.length=0;live=widget.default(host,slowProps);
  host.querySelector('[data-finish-shot="uuid-4"]').click();
  const authority=structuredClone(initial);authority.shot={channel_uuid:'channel',...catalog.shots[3]};authority.finish_look=structuredClone(authority.shot_documents['channel\x1fuuid-4']);
  authority.finish_look.beauty.brightness=1;authority.shot_documents['channel\x1fuuid-4']=structuredClone(authority.finish_look);authority.shot_catalog.generation+=1;
  live.update({...slowProps,value:authority});await new Promise(resolve=>setTimeout(resolve,60));
  const acceptedAuthority={selected:host.querySelector('[aria-pressed="true"]').dataset.finishShot,sent:sent.length,brightness:host.__hmbFinishLookLatestProps.value.finish_look.beauty.brightness};
  live.cleanup();sent.length=0;failed.length=0;
  let oldCallbacks=0,newCallbacks=0;live=widget.default(host,{value:structuredClone(initial),onChange(){oldCallbacks++;}});
  host.querySelector('[data-finish-shot="uuid-4"]').click();
  live.update({value:structuredClone(initial),onChange:value=>{newCallbacks++;sent.push(structuredClone(value));}});
  await new Promise(resolve=>setTimeout(resolve,60));
  const latestCallback={oldCallbacks,newCallbacks,shots:sent.map(value=>value.shot.shot_uuid)};
  const bothRejected=[];
  for(const order of [[0,1],[1,0]]){
    live.cleanup();sent.length=0;failed.length=0;live=widget.default(host,slowProps);
    host.querySelector('[data-finish-shot="uuid-4"]').click();
    const edit=host.querySelector('[data-enable="beauty"]');edit.checked=false;edit.dispatchEvent(new Event('change',{bubbles:true}));
    for(const index of order){failed[index].reject(Error('failed publication '+index));await Promise.resolve();await Promise.resolve();}
    bothRejected.push({order,selected:host.querySelector('[aria-pressed="true"]').dataset.finishShot,enabled:host.querySelector('[data-enable="beauty"]').checked,retainedShot:host.__hmbFinishLookLatestProps.value.shot.shot_uuid});
  }
  live.cleanup();sent.length=0;failed.length=0;
  const synchronousProps={value:structuredClone(initial),onChange:value=>{sent.push(structuredClone(value));live.update({...synchronousProps,value:structuredClone(value)});}};
  live=widget.default(host,synchronousProps);host.querySelector('[data-finish-shot="uuid-4"]').click();
  const syncToggle=host.querySelector('[data-enable="beauty"]');syncToggle.checked=false;syncToggle.dispatchEvent(new Event('change',{bubbles:true}));
  const synchronousToggle={values:sent.map(value=>value.finish_look.beauty.enabled),selected:host.querySelector('[aria-pressed="true"]').dataset.finishShot,checked:host.querySelector('[data-enable="beauty"]').checked};
  live.cleanup();sent.length=0;live=widget.default(host,synchronousProps);host.querySelector('[data-finish-shot="uuid-4"]').click();
  const syncRange=host.querySelector('[data-finish-step="beauty.brightness"]');syncRange.value='0';syncRange.dispatchEvent(new Event('change',{bubbles:true}));
  const synchronousRange={values:sent.map(value=>value.finish_look.beauty.brightness),expected:widget.HMB_FINISH_LOOK_STEPS['beauty.brightness'][0].value,selected:host.querySelector('[aria-pressed="true"]').dataset.finishShot};
  live.cleanup();sent.length=0;failed.length=0;live=widget.default(host,slowProps);
  host.querySelector('[data-finish-shot="uuid-4"]').click();
  const deleted=structuredClone(initial);deleted.shot_catalog.generation+=1;deleted.shot_catalog.shots=deleted.shot_catalog.shots.filter(row=>row.shot_uuid!=='uuid-4');
  live.update({...slowProps,value:deleted});await new Promise(resolve=>setTimeout(resolve,60));
  const deletedSelection={selected:host.querySelector('[aria-pressed="true"]').dataset.finishShot,sent:sent.length,deletedPresent:Boolean(host.querySelector('[data-finish-shot="uuid-4"]'))};
  live.cleanup();sent.length=0;live=widget.default(host,slowProps);host.querySelector('[data-finish-shot="uuid-5"]').click();live.cleanup();
  await new Promise(resolve=>setTimeout(resolve,60));const retiredCalls=sent.length;host.remove();
  return {synthetic_host_sync_work_ms:100,events,contrast,rapidImmediate,coalesced,failedSelection,editOrder,rejectedEdit,acceptedAuthority,latestCallback,bothRejected,synchronousToggle,synchronousRange,deletedSelection,retiredCalls};
 });
 const event=phase=>performanceResult.events.find(value=>value.phase===phase);
 assert.equal(event('click_return').pressed,'uuid-4');assert.ok(event('click_return').elapsed_ms<40,JSON.stringify(performanceResult));
 assert.equal(event('first_animation_frame').pressed,'uuid-4');assert.ok(event('first_animation_frame').elapsed_ms<event('host_callback_entry').elapsed_ms,JSON.stringify(performanceResult));
 assert.equal(event('host_callback_entry').pressed,'uuid-4');
 assert.equal(performanceResult.contrast.selectedBorder,'rgb(139, 92, 246)');assert.match(performanceResult.contrast.selectedShadow,/inset/);assert.notEqual(performanceResult.contrast.selectedBorder,performanceResult.contrast.unselectedBorder);
 assert.equal(performanceResult.contrast.headerRgb,'139,92,246');
 assert.deepEqual(performanceResult.rapidImmediate,{selected:'uuid-3',sent:0});assert.deepEqual(performanceResult.coalesced,['uuid-3']);assert.equal(performanceResult.failedSelection,'uuid-1');
 assert.deepEqual(performanceResult.editOrder,[{shot:'uuid-4',enabled:true},{shot:'uuid-4',enabled:false}]);assert.equal(performanceResult.retiredCalls,0);
 assert.deepEqual(performanceResult.rejectedEdit,{selected:'uuid-1',sent:[{shot:'uuid-4',enabled:true}]});
 assert.deepEqual(performanceResult.acceptedAuthority,{selected:'uuid-4',sent:0,brightness:1});
 assert.deepEqual(performanceResult.latestCallback,{oldCallbacks:0,newCallbacks:1,shots:['uuid-4']});
 assert.deepEqual(performanceResult.bothRejected,[{order:[0,1],selected:'uuid-1',enabled:true,retainedShot:'uuid-1'},{order:[1,0],selected:'uuid-1',enabled:true,retainedShot:'uuid-1'}]);
 assert.deepEqual(performanceResult.synchronousToggle,{values:[true,false],selected:'uuid-4',checked:false});
 assert.deepEqual(performanceResult.synchronousRange.values,[2,performanceResult.synchronousRange.expected]);assert.equal(performanceResult.synchronousRange.selected,'uuid-4');
 assert.deepEqual(performanceResult.deletedSelection,{selected:'uuid-1',sent:0,deletedPresent:false});
 receipt.performance=performanceResult;
 receipt.cases.push('tab and body are visible before a 100ms synchronous host callback; header/active tab use the selected Agent palette and inset indicator');
 receipt.cases.push('rapid tabs coalesce to the latest view, failure restores confirmed state, authoring flushes selection in order and cleanup cancels unsent views');
 receipt.cases.push('synchronous selection rejection blocks authoring on the wrong Shot; authoritative deletion retires a queued selection without sending it');
 receipt.cases.push('accepted newer same-target state cancels queued stale payload; dispatch uses the latest callback once and combined asynchronous failures restore confirmed state in either order');
 receipt.cases.push('synchronous selection acknowledgements cannot overwrite the pending user checkbox or slider edit');
 await page.setViewportSize({width:1080,height:1200});
 await page.evaluate(()=>{
  const node=document.querySelector('.react-flow__node');node.style.width='980px';node.style.height='864px';
  const selected=structuredClone(initial);selected.shot={channel_uuid:'channel',...catalog.shots[3]};selected.finish_look=structuredClone(selected.shot_documents['channel\x1fuuid-4']);
  window.finalPreview=widget.default(mount,{value:selected,onChange(){}});
 });
 await page.waitForTimeout(80);
 await page.screenshot({path:path.join(report,'finish-selected-four-desktop.png')});
 await page.evaluate(()=>finalPreview.cleanup());
 fs.writeFileSync(path.join(report,'latency-after-regression.json'),JSON.stringify(performanceResult,null,2)+'\n');
 console.log('HMB Finish unified widget: PASS ('+receipt.cases.length+' actual Chromium cases)');
}finally{await browser.close();fs.writeFileSync(path.join(report,'widget-regression.json'),JSON.stringify(receipt,null,2)+'\n');}
