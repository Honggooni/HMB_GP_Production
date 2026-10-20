import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const source=fs.readFileSync(path.join(root,'widgets/HMBAgentLibraryWidget.js'),'utf8');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const out=path.join(root,'reports/ui-responsive-v804-20261015/agent-audit');fs.mkdirSync(out,{recursive:true});
const receipt={schema:'hmb-agent-ui-responsiveness',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),cases:[],external_requests:0,model_calls:0,render_calls:0};
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
try{
 const page=await browser.newPage({viewport:{width:820,height:800}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>{receipt.external_requests++;return route.abort();});
 // Match the installed editor's native parameter-row contract. Pending Shot
 // protection intentionally excludes the node header and canvas, not this body.
 await page.setContent('<!doctype html><meta charset="utf-8"><style>body{background:#101019;font-family:system-ui;color:white;margin:20px}.mount{width:720px;margin:6px 0}#native{background:#252535;padding:20px}</style><section id="sdk" class="react-flow__node"><div id="row1" class="mount"></div><div id="row2" class="mount"></div><div id="row3" class="mount"></div><div id="row4" class="mount"></div><div id="row5" class="mount"></div><div id="native" data-parameter-name="prompt" data-param-node="Synthetic Agent">SDK-owned original native body<input id="native-input" value="Authored Shot 1"><button id="native-run">Native Run</button></div></section>');
 await page.evaluate(async code=>{
  window.widget=await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
  window.selected=1;window.expanded=true;window.acks={};window.statuses={};window.calls=[];window.requests=[];window.command=null;window.frames=0;window.timing={};window.frameActive=true;
  const frame=()=>{if(!frameActive)return;frames++;requestAnimationFrame(frame);};requestAnimationFrame(frame);
  window.rows=[1,2,3,4,5].map(n=>document.querySelector(`#row${n}`));window.body=document.querySelector('#native');
  window.value=n=>({schema:'hmb-agent-shot-row',version:1,shot:{channel_uuid:'latency-channel',shot_uuid:`shot-${n}`,number:n,name:`Authored asset ${n}`,revision:1},selected:selected===n,expanded:selected===n&&expanded,status:statuses[n]||'',request_id:acks[n]||''});
  window.onRow=next=>{timing.dispatch_ms=performance.now()-timing.start;timing.dispatch_frame=frames;calls.push(structuredClone(next));return new Promise((resolve,reject)=>{command={next,resolve,reject};requests.push(command);});};
  window.handles=rows.map((row,i)=>widget.default(row,{value:value(i+1),onChange:onRow}));
  window.sync=()=>{handles.forEach((handle,i)=>handle.update({value:value(i+1),onChange:onRow}));body.hidden=!expanded;rows[selected-1].after(body);};
  window.ack=(index=requests.length-1)=>{const {next,resolve}=requests[index];const n=next.shot.number;if(next.action.kind==='select'){expanded=next.action.expanded;selected=n;}acks[n]=next.action.request_id;sync();resolve();command=null;};
  sync();window.originalRows=rows.map(row=>row.firstElementChild);window.originalInput=document.querySelector('#native-input');window.nativeRuns=0;document.querySelector('#native-run').addEventListener('click',()=>nativeRuns++);
 },source);
 const immediate=await page.evaluate(()=>{
  timing={start:performance.now(),start_frame:frames};rows[3].querySelector('.agent-shot-tab').click();
  const visual_ms=performance.now()-timing.start;
  return {visual_ms,calls:calls.length,active:rows[3].querySelector('.agent-shot-row').dataset.active,expanded:rows[3].querySelector('.agent-shot-tab').getAttribute('aria-expanded'),allBlocked:rows.every(row=>row.querySelector('.agent-shot-run').disabled),nativeOwner:body.previousElementSibling.id,nativeValue:originalInput.value};
 });
 assert.equal(immediate.calls,0);assert.equal(immediate.active,'true');assert.equal(immediate.expanded,'true');assert.equal(immediate.allBlocked,true);assert.equal(immediate.nativeOwner,'row1');assert.equal(immediate.nativeValue,'Authored Shot 1');
 const firstFrame=await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>resolve({calls:calls.length,active:rows[3].querySelector('.agent-shot-row').dataset.active}))));
 assert.equal(firstFrame.active,'true');
 await page.waitForFunction(()=>calls.length===1);
 const dispatch=await page.evaluate(()=>({...timing,frame_delta:timing.dispatch_frame-timing.start_frame}));
 assert.ok(dispatch.frame_delta>=1,JSON.stringify(dispatch));
 receipt.latency={visual_ms:immediate.visual_ms,dispatch_ms:dispatch.dispatch_ms,paint_frames_before_dispatch:dispatch.frame_delta};
 receipt.cases.push('Immediate selected color/chevron precedes one deferred dispatch; original native editor/input remains on its acknowledged Shot');
 const stale=await page.evaluate(()=>{
  for(let n=0;n<50;n++)sync();rows[1].querySelector('.agent-shot-tab').click();rows[3].querySelector('.agent-shot-run').click();
  command.resolve();return {calls:calls.length,active:rows[3].querySelector('.agent-shot-row').dataset.active,blocked:rows.every(row=>row.querySelector('.agent-shot-run').disabled),nativeOwner:body.previousElementSibling.id};
 });
 assert.deepEqual(stale,{calls:1,active:'true',blocked:true,nativeOwner:'row1'});
 await page.evaluate(()=>originalInput.focus());await page.keyboard.type('WRONG SHOT');
 const guarded=await page.evaluate(()=>{document.querySelector('#native-run').click();const event=new InputEvent('beforeinput',{bubbles:true,cancelable:true,data:'wrong'});originalInput.dispatchEvent(event);return {text:originalInput.value,runs:nativeRuns,inputPrevented:event.defaultPrevented};});
 assert.deepEqual(guarded,{text:'Authored Shot 1',runs:0,inputPrevented:true});
 await page.evaluate(()=>ack());
 assert.equal(await page.evaluate(()=>body.previousElementSibling.id),'row4');assert.equal(await page.evaluate(()=>rows.some(row=>row.querySelector('.agent-shot-run').disabled)),false);
 receipt.cases.push('50 stale echoes and resolved delivery promise cannot release the channel lease; cross-Shot click/Run cannot overtake matching native ACK');
 const released=await page.evaluate(()=>{document.querySelector('#native-run').click();const event=new InputEvent('beforeinput',{bubbles:true,cancelable:true});originalInput.dispatchEvent(event);return {runs:nativeRuns,inputPrevented:event.defaultPrevented};});
 assert.deepEqual(released,{runs:1,inputPrevented:false});receipt.cases.push('Pending native input, paste/keyboard and native Run events are guarded until exact ACK, then the original editor is usable again');
 const late=await page.evaluate(()=>{const old=value(4);old.selected=false;old.expanded=false;old.request_id='';handles[3].update({value:old,onChange:onRow});return rows[3].querySelector('.agent-shot-row').dataset.active;});
 assert.equal(late,'true');receipt.cases.push('Late unacknowledged row echo cannot undo an accepted selection');
 await page.evaluate(()=>{timing={start:performance.now(),start_frame:frames};rows[2].querySelector('.agent-shot-tab').click();});
 await page.waitForFunction(()=>calls.length===2);
 await page.evaluate(()=>{command.reject(new Error('Rejected offline switch'));command=null;});
 await page.waitForFunction(()=>rows[2].querySelector('.agent-shot-run').getAttribute('aria-label')==='Refresh Agent Shot');
 assert.equal(await page.evaluate(()=>rows[3].querySelector('.agent-shot-row').dataset.active),'true');assert.equal(await page.evaluate(()=>rows[2].querySelector('.agent-shot-row').dataset.active),'false');
 assert.equal(await page.evaluate(()=>body.previousElementSibling.id),'row4');assert.equal(await page.locator('#native-input').inputValue(),'Authored Shot 1');
 assert.equal(await page.evaluate(()=>rows[2].querySelector('.agent-shot-tab').disabled),true);
 await page.evaluate(()=>{timing={start:performance.now(),start_frame:frames};rows[2].querySelector('.agent-shot-run').click();});
 await page.waitForFunction(()=>calls.length===3);assert.equal(await page.evaluate(()=>calls.at(-1).action.kind),'refresh');
 await page.evaluate(()=>ack());assert.equal(await page.evaluate(()=>selected),4);
 assert.equal(await page.evaluate(()=>rows[2].querySelector('.agent-shot-tab').disabled),false);
 receipt.cases.push('Rejected switch restores canonical highlight and keeps editing guarded until explicit read-only refresh acknowledges the actual old Shot; no Run replay');
 await page.evaluate(()=>{timing={start:performance.now(),start_frame:frames};rows[3].querySelector('.agent-shot-run').click();});
 await page.waitForFunction(()=>calls.length===4);assert.equal(await page.evaluate(()=>calls.at(-1).action.kind),'run_selected');
 await page.evaluate(()=>{statuses[4]='running';ack();});
 await page.evaluate(()=>{timing={start:performance.now(),start_frame:frames};rows[3].querySelector('.agent-shot-run').click();});
 await page.waitForFunction(()=>calls.length===5);assert.equal(await page.evaluate(()=>calls.at(-1).action.kind),'cancel_selected');
 await page.evaluate(()=>{statuses[4]='cancelled';ack();});
 receipt.cases.push('Explicit Run and Cancel dispatch once for exactly the selected canonical Shot; no inference or render occurs on selection');
 const stable=await page.evaluate(async()=>{
  sync();await Promise.resolve();let mutations=0;const observer=new MutationObserver(records=>mutations+=records.length);observer.observe(document.querySelector('#sdk'),{subtree:true,attributes:true,childList:true,characterData:true});const before=calls.length;
  for(let n=0;n<300;n++)handles.forEach((handle,i)=>handle.update({value:structuredClone(value(i+1)),onChange:onRow}));
  await Promise.resolve();observer.disconnect();return {mutations,calls:calls.length-before,sameRows:rows.every((row,i)=>row.firstElementChild===originalRows[i]),sameInput:originalInput===document.querySelector('#native-input')};
 });
 assert.deepEqual(stable,{mutations:0,calls:0,sameRows:true,sameInput:true});receipt.cases.push('300 same-state updates: zero DOM mutations, commands, field remounts or native input replacement');
 await page.evaluate(()=>{
  const timer=window.setTimeout;window.setTimeout=(callback,ms,...args)=>{if(ms===15000)window.expirePending=callback;return timer(callback,ms,...args);};
  timing={start:performance.now(),start_frame:frames};rows[1].querySelector('.agent-shot-tab').click();window.setTimeout=timer;
 });
 await page.waitForFunction(()=>calls.length===6);
 const expired=await page.evaluate(()=>{expirePending();return {calls:calls.length,blocked:rows.some(row=>row.querySelector('.agent-shot-run').disabled),selected:rows[3].querySelector('.agent-shot-row').dataset.active,warning:rows[1].querySelector('.agent-row-status').textContent,title:rows[1].querySelector('.agent-shot-run').title};});
 assert.equal(expired.calls,6);assert.equal(expired.blocked,true);assert.equal(expired.selected,'true');assert.equal(expired.warning,'응답 확인 필요');assert.match(expired.title,/다시 실행하지/);
 const timeoutGuard=await page.evaluate(()=>{document.querySelector('#native-run').click();const event=new InputEvent('beforeinput',{bubbles:true,cancelable:true});originalInput.dispatchEvent(event);return {runs:nativeRuns,inputPrevented:event.defaultPrevented,refreshEnabled:!rows[1].querySelector('.agent-shot-run').disabled};});
 assert.deepEqual(timeoutGuard,{runs:1,inputPrevented:true,refreshEnabled:true});
 await page.evaluate(()=>{timing={start:performance.now(),start_frame:frames};rows[1].querySelector('.agent-shot-run').click();});
 await page.waitForFunction(()=>calls.length===7);assert.equal(await page.evaluate(()=>calls.at(-1).action.kind),'refresh');
 await page.evaluate(()=>ack());assert.equal(await page.evaluate(()=>body.previousElementSibling.id),'row4');
 assert.equal(await page.evaluate(()=>rows[1].querySelector('.agent-row-status').textContent),'');
 const oldEcho=await page.evaluate(()=>{const late={...value(2),selected:true,expanded:true,request_id:requests[5].next.action.request_id};handles[1].update({value:late,onChange:onRow});return {target:rows[1].querySelector('.agent-shot-row').dataset.active,actual:rows[3].querySelector('.agent-shot-row').dataset.active,owner:body.previousElementSibling.id};});
 assert.deepEqual(oldEcho,{target:'false',actual:'true',owner:'row4'});
 receipt.cases.push('Missing ACK keeps native editing/Run quarantined; same-size refresh submits only a fresh read-only nonce and accepts canonical A instead of insisting on requested B; stale original ACK cannot undo it');
 await page.evaluate(()=>{
  const timer=window.setTimeout;window.setTimeout=(callback,ms,...args)=>{if(ms===15000)window.expirePending=callback;return timer(callback,ms,...args);};
  timing={start:performance.now(),start_frame:frames};rows[4].querySelector('.agent-shot-tab').click();window.setTimeout=timer;
 });
 await page.waitForFunction(()=>calls.length===8);
 const originalWins=await page.evaluate(async()=>{expirePending();rows[4].querySelector('.agent-shot-run').click();ack(7);await new Promise(resolve=>setTimeout(resolve,180));return {calls:calls.length,owner:body.previousElementSibling.id,blocked:rows.some(row=>row.querySelector('.agent-shot-run').disabled)};});
 assert.deepEqual(originalWins,{calls:8,owner:'row5',blocked:false});receipt.cases.push('Original exact ACK arriving before scheduled refresh wins and cancels the unpublished refresh; no stale follow-up command or permanent lock');
 await page.evaluate(()=>{
  const timer=window.setTimeout;window.setTimeout=(callback,ms,...args)=>{if(ms===15000)window.expirePending=callback;return timer(callback,ms,...args);};
  timing={start:performance.now(),start_frame:frames};rows[1].querySelector('.agent-shot-tab').click();window.setTimeout=timer;
 });
 await page.waitForFunction(()=>calls.length===9);await page.evaluate(()=>{expirePending();rows[1].querySelector('.agent-shot-run').click();});
 await page.waitForFunction(()=>calls.length===10);await page.evaluate(()=>ack(8));
 await page.evaluate(()=>rows[2].querySelector('.agent-shot-tab').click());await page.waitForFunction(()=>calls.length===11);await page.evaluate(()=>ack(10));
 const retiredRefresh=await page.evaluate(()=>{const stale={...value(2),selected:true,expanded:true,request_id:requests[9].next.action.request_id};handles[1].update({value:stale,onChange:onRow});return {selected:rows.flatMap((row,i)=>row.querySelector('[aria-pressed="true"]')?[i+1]:[]),owner:body.previousElementSibling.id,blocked:rows.some(row=>row.querySelector('.agent-shot-run').disabled)};});
 assert.deepEqual(retiredRefresh,{selected:[3],owner:'row3',blocked:false});receipt.cases.push('Original ACK after refresh dispatch releases its confirmed view; a later retired refresh ACK cannot overwrite a subsequent accepted Shot');
 const cleanup=await page.evaluate(async()=>{
  const before=calls.length;timing={start:performance.now(),start_frame:frames};rows[4].querySelector('.agent-shot-tab').click();handles[4].cleanup();await new Promise(resolve=>setTimeout(resolve,180));return {calls:calls.length-before,blocked:rows.slice(0,4).some(row=>row.querySelector('.agent-shot-run').disabled)};
 });
 assert.deepEqual(cleanup,{calls:0,blocked:false});receipt.cases.push('Unmount before paint cancels both frame/timer dispatch and releases remaining rows without a retired callback');
 await page.locator('#sdk').screenshot({path:path.join(out,'agent-responsive.png')});
 await page.evaluate(()=>{frameActive=false;handles.forEach(handle=>handle.cleanup());});
 assert.deepEqual(errors,[]);assert.equal(receipt.external_requests,0);receipt.passed=true;
 console.log(`HMB Agent UI responsiveness: PASS (${receipt.cases.length} cases; visual ${receipt.latency.visual_ms.toFixed(2)}ms; dispatch after ${receipt.latency.paint_frames_before_dispatch} frames)`);
}finally{await browser.close();fs.writeFileSync(path.join(out,'agent-ui-responsiveness.json'),JSON.stringify(receipt,null,2)+'\n');}
