/** Original Widget, SDK-shaped sibling fixture, no live graph or inference. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const source=fs.readFileSync(path.join(root,'widgets/HMBAgentLibraryWidget.js'),'utf8');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const out=path.join(root,'reports/agent-ui-stall-fix-20261020');fs.mkdirSync(out,{recursive:true});
const receipt={schema:'hmb-agent-accordion-stable-header/v1',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),cases:[],external_requests:0,model_calls:0,render_calls:0,live_editor_actions:0};
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
try{
 const page=await browser.newPage({viewport:{width:1500,height:1600}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',route=>{receipt.external_requests++;return route.abort();});
 await page.setContent('<!doctype html><style>body{margin:20px}.react-flow__node{width:700px}.field{height:36px}</style><section id="sdk" class="react-flow__node"><div id="header" data-parameter-name="HMB_AGENT_UI"></div></section><section id="other" class="react-flow__node"><div id="other-header" data-parameter-name="HMB_AGENT_UI"></div></section>');
 await page.evaluate(async code=>{
  window.widget=await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
  window.sdk=document.querySelector('#sdk');window.header=document.querySelector('#header');window.otherHeader=document.querySelector('#other-header');
  window.catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:'private-publisher',channel_uuid:'shared-channel',generation:1,metadata_sha256:'a'.repeat(64),shots:[1,2,3,4,5].map(number=>({shot_uuid:`shot-${number}`,number,name:`Authored asset ${number}`,revision:1}))};
  window.selected=1;window.acks={};window.calls=[];window.requests=[];
  window.headerValue=n=>({schema:'hmb-agent-ui',schema_version:2,shot_manager:true,shot_editor_expanded:true,shot:{channel_uuid:catalog.channel_uuid,...catalog.shots[n-1]},shot_catalog:structuredClone(catalog)});
  window.headerProps=n=>({value:headerValue(n),onChange(){throw new Error('Header must not submit');}});
  window.rowValue=n=>({schema:'hmb-agent-shot-row',version:1,shot:{channel_uuid:catalog.channel_uuid,...catalog.shots[n-1]},selected:n===selected,expanded:n===selected,status:'',request_id:acks[n]||''});
  window.onRow=next=>{calls.push(structuredClone(next));return new Promise((resolve,reject)=>requests.push({next,resolve,reject}));};
  window.rowProps=(n,disabled=false)=>({value:rowValue(n),disabled,onChange:onRow});
  window.headerHandle=widget.default(header,headerProps(1));window.otherHandle=widget.default(otherHeader,headerProps(5));
  window.rows=catalog.shots.map(shot=>{const row=document.createElement('div');row.id=`row${shot.number}`;row.setAttribute('data-parameter-name',`HMB_AGENT_SHOT_ROW_${shot.number}`);sdk.append(row);return row;});
  window.fields=Array.from({length:22},(_,i)=>{const field=document.createElement('div');field.id=`native-${i}`;field.className='field';field.setAttribute('data-parameter-name',`native-${i}`);field.textContent=`Native parameter ${i}`;return field;});
  fields[0].innerHTML='<input id="native-input" value="Preserved native input">';
  sdk.append(...fields);window.handles=rows.map((row,i)=>widget.default(row,rowProps(i+1)));
  window.reorder=()=>{sdk.append(header,...rows.slice(0,selected),...fields,...rows.slice(selected));};reorder();
  window.ack=index=>{const {next,resolve}=requests[index];selected=next.shot.number;acks[selected]=next.action.request_id;handles.forEach((handle,i)=>handle.update(rowProps(i+1)));headerHandle.update(headerProps(selected));reorder();resolve();};
  window.originalHeader=header.querySelector('.hmb-agent-dashboard');window.originalLabel=originalHeader.querySelector('.agent-heading b');window.originalRows=rows.map(row=>row.firstElementChild);window.originalFields=[...fields];window.originalInput=document.querySelector('#native-input');
  window.snapshot=()=>({title:originalLabel.textContent,theme:originalHeader.getAttribute('data-shot-number'),accent:getComputedStyle(originalHeader).getPropertyValue('--hmb-shot-accent').trim(),header_top:originalHeader.getBoundingClientRect().top,header_height:originalHeader.getBoundingClientRect().height,node_height:sdk.getBoundingClientRect().height,other_theme:otherHeader.querySelector('.hmb-agent-dashboard').getAttribute('data-shot-number')});
 },source);
 const initial=await page.evaluate(()=>snapshot());
 const immediate=await page.evaluate(()=>{rows[3].querySelector('.agent-shot-tab').click();return snapshot();});
 assert.equal(immediate.theme,'4');assert.equal(immediate.accent,'#8B5CF6');assert.equal(immediate.title,initial.title);assert.equal(immediate.header_top,initial.header_top);assert.equal(immediate.header_height,64);assert.equal(immediate.node_height,initial.node_height);assert.equal(immediate.other_theme,'5');
 await page.waitForFunction(()=>calls.length===1);
 await page.evaluate(()=>{headerHandle.update(headerProps(1));otherHandle.update(headerProps(5));});
 assert.equal(await page.evaluate(()=>snapshot().theme),'4');
 receipt.cases.push('Selecting Shot 4 immediately changes only the fixed AG header color; stale header props and a different node with the same channel cannot undo or adopt it');
 await page.evaluate(()=>ack(0));
 const ordered=await page.evaluate(()=>({ids:Array.from(sdk.children).map(item=>item.id),snapshot:snapshot(),header:header.querySelector('.hmb-agent-dashboard')===originalHeader,input:document.querySelector('#native-input')===originalInput}));
 assert.deepEqual(ordered.ids,['header','row1','row2','row3','row4',...Array.from({length:22},(_,i)=>`native-${i}`),'row5']);assert.equal(ordered.header,true);assert.equal(ordered.input,true);assert.equal(ordered.snapshot.node_height,initial.node_height);
 await page.evaluate(()=>headerHandle.update(headerProps(1)));
 assert.equal(await page.evaluate(()=>snapshot().theme),'4');
 receipt.cases.push('Canonical SDK order remains header, Shots 1–4, one original native form, Shot 5; late header-only props cannot flash the confirmed color backwards');
 const stable=await page.evaluate(async()=>{
  headerHandle.update(headerProps(selected));handles.forEach((handle,i)=>handle.update(rowProps(i+1)));await Promise.resolve();
  const originalQuery=Element.prototype.querySelector;let queries=0,mutations=0;Element.prototype.querySelector=function(...args){queries++;return originalQuery.apply(this,args);};
  const observer=new MutationObserver(records=>mutations+=records.length);observer.observe(sdk,{childList:true,subtree:true,attributes:true,characterData:true});const before=calls.length;
  try{for(let n=0;n<300;n++){headerHandle.update(headerProps(selected));handles.forEach((handle,i)=>handle.update(rowProps(i+1)));}}finally{Element.prototype.querySelector=originalQuery;}
  await Promise.resolve();observer.disconnect();return {queries,mutations,calls:calls.length-before};
 });
 assert.deepEqual(stable,{queries:0,mutations:0,calls:0});receipt.stable_updates=stable;
 receipt.cases.push('300 identical header and five-row updates perform zero subtree queries, DOM mutations or host commands');
 await page.evaluate(()=>rows[1].querySelector('.agent-shot-tab').click());await page.waitForFunction(()=>calls.length===2);
 assert.equal(await page.evaluate(()=>snapshot().theme),'2');
 await page.evaluate(()=>{handles[1].update({...rowProps(2,true),value:{...rowValue(2),rejected_request_id:requests[1].next.action.request_id,error_code:'SHOT_IDENTITY_UNAVAILABLE'}});});
 await page.waitForTimeout(0);await page.evaluate(()=>handles[1].update(rowProps(2,false)));
 assert.equal(await page.evaluate(()=>snapshot().theme),'4');assert.equal(await page.evaluate(()=>rows[1].querySelector('.agent-shot-tab').disabled),false);
 assert.equal(await page.locator('#row2 .agent-row-status').textContent(),'요청 거절됨');
 receipt.cases.push('Exact NACK returns the title to the confirmed Shot, including native lock/unlock around the same value; no cached disabled flag survives');
 const remount=await page.evaluate(()=>{headerHandle=widget.default(header,headerProps(selected));handles=rows.map((row,i)=>widget.default(row,rowProps(i+1)));rows[2].style.setProperty('height','9px','important');handles[2].update(rowProps(3));return {header:header.querySelector('.hmb-agent-dashboard')===originalHeader,rows:rows.every((row,i)=>row.firstElementChild===originalRows[i]),fields:fields.every((field,i)=>field===originalFields[i]),input:document.querySelector('#native-input')===originalInput,repaired_height:rows[2].style.getPropertyValue('height')};});
 assert.deepEqual(remount,{header:true,rows:true,fields:true,input:true,repaired_height:'42px'});
 receipt.cases.push('Repeated widget factory calls retain header/row/native identities; host geometry corrections still run when presentation is unchanged');
 await page.evaluate(()=>{headerHandle.cleanup();otherHandle.cleanup();handles.forEach(handle=>handle.cleanup());});
 assert.deepEqual(errors,[]);assert.equal(receipt.external_requests,0);receipt.passed=true;
 console.log(`HMB Agent stable accordion header: PASS (${receipt.cases.length} cases; original Widget; external/model/render/live calls 0)`);
}finally{await browser.close();fs.writeFileSync(path.join(out,'agent-stable-accordion-header.json'),JSON.stringify(receipt,null,2)+'\n');}
