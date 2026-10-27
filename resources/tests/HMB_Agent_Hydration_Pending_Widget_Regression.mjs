/** Original widget: saved rows are read-only until a live catalog arrives. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const code=fs.readFileSync(path.join(root,'widgets/HMBAgentLibraryWidget.js'),'utf8');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
let external=0;const errors=[];
try{
 const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{external++;return r.abort();});
 await page.setContent('<section class="react-flow__node" id="host"><input id="native" value="Saved native OFF 0"></section>');
 await page.evaluate(async code=>{
  window.widget=await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
  window.calls=[];window.selected=1;window.pending=true;window.acks={};window.requests=[];
  window.value=n=>({schema:'hmb-agent-shot-row',version:1,shot:{channel_uuid:'channel',shot_uuid:`shot-${n}`,number:n,name:`Saved Shot ${n}`,revision:1},selected:n===selected,expanded:n===selected,...(pending?{routing_pending:true}:{}),request_id:acks[n]||'',status:''});
  window.props=n=>({value:value(n),onChange(next){calls.push(structuredClone(next));return new Promise((resolve,reject)=>requests.push({next,resolve,reject}));}});
  window.rows=Array.from({length:5},(_,i)=>{const e=document.createElement('div');e.id=`row${i+1}`;document.querySelector('#host').append(e);return e;});
  window.handles=rows.map((r,i)=>widget.default(r,props(i+1)));window.original=rows.map(r=>r.firstElementChild);window.native=document.querySelector('#native');
 },code);
 assert.equal(await page.locator('.agent-shot-tab:disabled').count(),5);
 assert.equal(await page.locator('.agent-shot-run:disabled').count(),5);
 assert.equal(await page.locator('#row2 .agent-row-status').textContent(),'샷 연결 확인 중…');
 await page.evaluate(()=>rows.forEach(r=>{r.querySelector('.agent-shot-tab').click();r.querySelector('.agent-shot-run').click();}));
 await page.waitForTimeout(150);
 assert.equal(await page.evaluate(()=>calls.length),0);
 assert.equal(await page.locator('#row2 b').textContent(),'Saved Shot 2');
 await page.evaluate(()=>{pending=false;handles.forEach((h,i)=>h.update(props(i+1)));});
 assert.equal(await page.locator('.agent-shot-tab:disabled').count(),0);
 assert.equal(await page.locator('.agent-shot-run:disabled').count(),0);
 assert.equal(await page.evaluate(()=>rows.every((r,i)=>r.firstElementChild===original[i])&&document.querySelector('#native')===native&&native.value==='Saved native OFF 0'),true);
 await page.locator('#row2 .agent-shot-tab').click();await page.waitForFunction(()=>calls.length===1);
 assert.equal(await page.evaluate(()=>calls[0].action.kind),'select');
 assert.equal(await page.evaluate(()=>calls[0].shot.shot_uuid),'shot-2');
 await page.evaluate(()=>requests[0].reject(new Error('offline uncertain transport')));
 await page.evaluate(()=>{pending=true;handles.forEach((h,i)=>h.update(props(i+1)));});
 assert.equal(await page.locator('.agent-shot-run:disabled').count(),5);
 await page.evaluate(()=>rows[1].querySelector('.agent-shot-run').click());await page.waitForTimeout(150);
 assert.equal(await page.evaluate(()=>calls.length),1);
 await page.evaluate(()=>{pending=false;selected=2;acks[2]=calls[0].action.request_id;handles.forEach((h,i)=>h.update(props(i+1)));});
 assert.equal(await page.locator('.agent-shot-tab:disabled').count(),0);
 assert.equal(await page.locator('#row2 .agent-shot-tab').getAttribute('aria-pressed'),'true');
 assert.equal(await page.evaluate(()=>rows.every((r,i)=>r.firstElementChild===original[i])),true);
 await page.evaluate(()=>handles.forEach(h=>h.cleanup()));
 assert.deepEqual(errors,[]);assert.equal(external,0);
 console.log('HMB_AGENT_HYDRATION_PENDING_WIDGET=PASS (five saved rows, read-only pending, no auto/recovery commands, live enable and exact ACK, native identity preserved; external/render calls 0)');
}finally{await browser.close();}
