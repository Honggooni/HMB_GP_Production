import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const sourcePath=process.env.HMB_AGENT_PRESENTATION_WIDGET || path.join(root,'widgets/HMBAgentLibraryWidget.js');
const source=fs.readFileSync(sourcePath,'utf8');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const out=path.join(root,'reports/prompt-agent-lifecycle-local804-20261016/agent/browser');fs.mkdirSync(out,{recursive:true});
const label=process.env.HMB_AGENT_PRESENTATION_LABEL || 'current';
const receipt={schema:'hmb-agent-catalog-presentation-browser-v1',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),
 cases:[],external_requests:0,model_calls:0,render_calls:0,
 limits:['Chromium renders actual widget code around a synthetic SDK-shaped native form; separate installed-SDK tests verify backend writes and native fields.']};
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
try{
 const page=await browser.newPage({viewport:{width:980,height:900}});const errors=[];
 page.on('pageerror',error=>errors.push(error.message));await page.route('**/*',route=>{receipt.external_requests++;return route.abort();});
 await page.setContent(`<!doctype html><meta charset="utf-8"><style>body{background:#101019;font-family:system-ui;color:white;margin:18px}.mount{width:820px;margin:4px 0}#native{width:780px;height:310px;overflow:auto;background:#252535;padding:20px}textarea{width:95%;height:110px}label{display:block;margin:12px 0}select,input{margin-left:15px}</style><section id="sdk" class="react-flow__node"><div id="header" class="mount"></div>${[1,2,3,4,5].map(n=>`<div id="row${n}" class="mount"></div>`).join('')}<div id="native"><label>Prompt<textarea id="prompt">Authored {literal} RGB(1, 2, 3) OFF 0\n${'Current editable line\n'.repeat(30)}</textarea></label><label>Provider<select id="provider"><option>Dynamic native provider</option></select></label><label>Model<select id="model"><option>Dynamic native model</option></select></label><label>Tool<input id="tool" value="Authored tool OFF 0"></label><label>Ruleset<input id="rules" value="Authored ruleset {literal}"></label><label>Schema<textarea id="schema">{"zero":0,"off":false}</textarea></label><input id="off" type="checkbox"><input id="zero" type="number" value="0"></div></section>`);
 await page.evaluate(async code=>{
  window.widget=await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
  window.catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:'catalog-owner',channel_uuid:'catalog-channel',generation:1,metadata_sha256:'a'.repeat(64),shots:[1,2,3,4,5].map(n=>({shot_uuid:`shot-${n}`,number:n,name:`Authored asset ${n}`,revision:0}))};
  window.selectedUuid='shot-1';window.acks={};window.calls=[];window.requests=[];window.rows=[1,2,3,4,5].map(n=>document.querySelector(`#row${n}`));window.body=document.querySelector('#native');window.expanded=true;
  window.rowValue=n=>{const shot=catalog.shots.find(item=>item.number===n);return {schema:'hmb-agent-shot-row',version:1,shot:shot?{channel_uuid:catalog.channel_uuid,...shot}:{},selected:shot?.shot_uuid===selectedUuid,expanded:shot?.shot_uuid===selectedUuid&&expanded,status:'',request_id:shot?acks[shot.shot_uuid]||'':''};};
  window.headerValue=()=>({schema:'hmb-agent-ui',shot_manager:true,shot_editor_expanded:expanded,shot_catalog:structuredClone(catalog),shot:{channel_uuid:catalog.channel_uuid,...catalog.shots.find(item=>item.shot_uuid===selectedUuid)}});
  window.onRow=next=>{calls.push(structuredClone(next));return new Promise((resolve,reject)=>requests.push({next,resolve,reject}));};
  window.header=widget.default(document.querySelector('#header'),{value:headerValue(),onChange:()=>{throw new Error('Catalog update authored header');}});
  window.handles=rows.map((row,index)=>widget.default(row,{value:rowValue(index+1),onChange:onRow}));
  window.sync=()=>{header.update({value:headerValue(),onChange:()=>{throw new Error('Catalog update authored header');}});handles.forEach((handle,index)=>handle.update({value:rowValue(index+1),onChange:onRow}));const target=rows[catalog.shots.find(item=>item.shot_uuid===selectedUuid).number-1];if(body.previousElementSibling!==target)target.after(body);};
  window.ack=index=>{const request=requests[index];selectedUuid=request.next.shot.shot_uuid;expanded=request.next.action.expanded;acks[selectedUuid]=request.next.action.request_id;sync();request.resolve();};
  sync();window.originalBody=body;window.originalFields=[...body.querySelectorAll('input,textarea,select')];window.originalHeader=document.querySelector('#header').firstElementChild;window.originalRows=rows.map(row=>row.querySelector('.agent-shot-row'));
 },source);
 // Establish a real accepted row nonce before a catalog renumber puts another
 // UUID into the same stable SDK row parameter. This reproduced the stale UI.
 await page.evaluate(()=>rows[1].querySelector('.agent-shot-tab').click());await page.waitForFunction(()=>calls.length===1);await page.evaluate(()=>ack(0));
 await page.evaluate(()=>rows[0].querySelector('.agent-shot-tab').click());await page.waitForFunction(()=>calls.length===2);await page.evaluate(()=>ack(1));
 await page.evaluate(()=>{
  const prompt=document.querySelector('#prompt');prompt.focus();prompt.setSelectionRange(11,29);prompt.scrollTop=90;body.scrollTop=0;
  window.before={text:prompt.value,selection:[prompt.selectionStart,prompt.selectionEnd],textScroll:prompt.scrollTop,bodyScroll:body.scrollTop,
   values:originalFields.map(field=>({value:field.value,checked:field.checked})),bodyOwner:body.previousElementSibling.id};
  window.formMutations=[];window.bodyObserver=new MutationObserver(items=>formMutations.push(...items.map(item=>item.type+':'+item.target.nodeName)));bodyObserver.observe(body,{subtree:true,childList:true,attributes:true,characterData:true});
  catalog.generation++;catalog.metadata_sha256='b'.repeat(64);const second=catalog.shots.find(item=>item.shot_uuid==='shot-2'),third=catalog.shots.find(item=>item.shot_uuid==='shot-3');second.number=3;third.number=2;sync();
  catalog.generation++;catalog.metadata_sha256='c'.repeat(64);third.name='Sibling changed after renumber';third.revision++;sync();
 });
 assert.equal(await page.locator('#row2 .agent-shot-tab b').textContent(),'Sibling changed after renumber');
 receipt.cases.push('An accepted nonce belongs to its Shot UUID; a replacement row accepts its subsequent rename');
 const stable=await page.evaluate(async()=>{
  const start=performance.now();for(let n=0;n<100;n++){catalog.generation++;catalog.metadata_sha256=(n%2?'d':'e').repeat(64);sync();}await new Promise(resolve=>requestAnimationFrame(()=>resolve()));
  const prompt=document.querySelector('#prompt');return {ms:performance.now()-start,text:prompt.value,selection:[prompt.selectionStart,prompt.selectionEnd],textScroll:prompt.scrollTop,bodyScroll:body.scrollTop,
   values:originalFields.map(field=>({value:field.value,checked:field.checked})),bodyOwner:body.previousElementSibling.id,
   sameBody:body===originalBody,sameFields:originalFields.every(field=>field.isConnected),sameRows:rows.every((row,index)=>row.querySelector('.agent-shot-row')===originalRows[index]),sameHeader:document.querySelector('#header').firstElementChild===originalHeader,
   focused:document.activeElement===prompt,mutations:formMutations,calls:calls.length,before};
 });
 for(const key of ['text','selection','textScroll','bodyScroll','values','bodyOwner'])assert.deepEqual(stable[key],stable.before[key],key);
 for(const key of ['sameBody','sameFields','sameRows','sameHeader','focused'])assert.equal(stable[key],true,key);
 assert.deepEqual(stable.mutations,[]);assert.equal(stable.calls,2);
 receipt.catalog_update_100_ms=Number(stable.ms.toFixed(3));receipt.cases.push('100 watermark/sibling metadata updates preserve form DOM, current text, caret, field scroll, native provider/model/tools/ruleset/schema and literal 0/OFF');
 // Delete/recreate during a queued selection: retire the old row's lease and
 // keep the new UUID responsive. No queued old action may reach onChange.
 const retired=await page.evaluate(async()=>{
  const beforeCalls=calls.length;handles[3].update({value:rowValue(4),onChange:onRow});rows[3].querySelector('.agent-shot-tab').click();
  catalog.shots.find(item=>item.number===4).shot_uuid='replacement-shot-4';catalog.shots.find(item=>item.number===4).name='Recreated asset 4';catalog.generation++;sync();
  await new Promise(resolve=>setTimeout(resolve,180));return {newCalls:calls.length-beforeCalls,label:rows[3].querySelector('.agent-shot-tab b').textContent,blocked:rows.some(row=>row.querySelector('.agent-shot-run').disabled),uuid:rows[3].querySelector('.agent-shot-row').dataset.shotUuid};
 });
 assert.equal(retired.newCalls,0);assert.equal(retired.label,'Recreated asset 4');assert.equal(retired.uuid,'replacement-shot-4');assert.equal(retired.blocked,false);
 receipt.cases.push('UUID deletion/recreation before dispatch cancels the old selection and releases the shared lease');
 // A dispatched callback can also settle after cleanup/remount.
 await page.evaluate(()=>rows[4].querySelector('.agent-shot-tab').click());await page.waitForFunction(()=>calls.length===3);
 const cleanup=await page.evaluate(async()=>{
  const old=handles[4];old.cleanup();catalog.shots.find(item=>item.number===5).shot_uuid='replacement-shot-5';catalog.shots.find(item=>item.number===5).name='Recreated asset 5';
  handles[4]=widget.default(rows[4],{value:rowValue(5),onChange:onRow});const current=rows[4].querySelector('.agent-shot-row');requests[2].reject(new Error('Old mount rejection'));old.update({value:{...rowValue(5),selected:true},onChange:onRow});await new Promise(resolve=>setTimeout(resolve,0));
  return {same:rows[4].querySelector('.agent-shot-row')===current,status:rows[4].querySelector('.agent-row-status').textContent,selected:current.dataset.active,blocked:rows.some(row=>row.querySelector('.agent-shot-run').disabled)};
 });
 assert.equal(cleanup.same,true);assert.equal(cleanup.status,'');assert.equal(cleanup.selected,'false');assert.equal(cleanup.blocked,false);
 receipt.cases.push('Late rejection/update from a disposed row cannot affect its new same-container instance');
 await page.screenshot({path:path.join(out,label+'-catalog-stable.png')});
 await page.evaluate(()=>{bodyObserver.disconnect();handles.forEach(handle=>handle.cleanup());header.cleanup();});
 assert.deepEqual(errors,[]);assert.equal(receipt.external_requests,0);receipt.passed=true;
}catch(error){receipt.passed=false;receipt.error=String(error?.stack||error);throw error;}finally{
 fs.writeFileSync(path.join(out,label+'-review.json'),JSON.stringify(receipt,null,2)+'\n');await browser.close();
}
console.log('HMB_AGENT_CATALOG_PRESENTATION_BROWSER=PASS '+JSON.stringify({cases:receipt.cases.length,catalog_update_100_ms:receipt.catalog_update_100_ms,external_requests:receipt.external_requests}));
