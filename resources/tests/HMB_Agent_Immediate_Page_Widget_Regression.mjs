// Isolated Chromium: compare actual widget paint/dispatch with a delayed host.
// No provider, workflow, network service or paid call is used.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
let pw;try{pw=require('playwright');}catch{pw=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const root=path.resolve(import.meta.dirname,'../..');
const out=path.join(root,'reports/local-v0870-agent-switch-20261112');
const browser=await pw.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const results={transport_delay_ms:180,environment:'isolated Chromium SDK callback fixture',paid_calls:0,rows:[]};
try{
 const baseline=path.join(out,'before');
 const variants=fs.existsSync(path.join(baseline,'HMBAgentLibraryWidget.js'))?['before','after']:['after'];
 for(const variant of variants)for(const kind of ['Agent','Analysis']){
  const file=kind==='Agent'?'HMBAgentLibraryWidget.js':'HMBAnalysisAgentWidget.js';
  const code=fs.readFileSync(path.join(root,variant==='before'?'reports/local-v0870-agent-switch-20261112/before':'widgets',file),'utf8');
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>route.abort());
  await page.setContent('<main id="sdk" class="react-flow__node" data-id="agent"><div id="widget" style="width:950px;height:1400px"></div><div id="native" data-parameter-name="prompt"><textarea id="prompt">Prompt 1</textarea></div></main>');
  await page.evaluate(async({code,kind})=>{
   const module=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(code))));
   const mount=document.querySelector('#widget');window.calls=[];window.metrics=[];window.deferAck=false;
   const rows=Array.from({length:5},(_,i)=>({number:i+1,name:'Shot '+(i+1),shot_uuid:'s'+(i+1),channel_uuid:'c',revision:0}));
   let revision=1,selected=1;const acks={};
   const pages=Object.fromEntries(rows.map(r=>[r.shot_uuid,{slot:{kind:'video',guidance:'Guide '+r.number,categories:[],result:{observations:{motion:[{observation:"Synthetic observation"}]}}},result_text:'Result '+r.number,source:{},sources:[],categories:['camera','motion','cut_timing','effect_shape','effect_timing']} ]));
   const handles=[];
   window.ack=()=>{};
   if(kind==='Analysis'){
    const state=()=>({revision,ack:acks[selected]||'',role:'after',channel_uuid:'c',shot_uuid:'s'+selected,shots:rows,...pages['s'+selected],display_pages:pages});
    const props=()=>({value:state(),onChange:value=>{
     const c=value.__hmb_analysis_command;calls.push(c);window.sentAt=performance.now();
     window.ack=()=>{selected=Number(c.shot_uuid.slice(1));revision++;acks[selected]=c.id;handles[0].update(props());};
     if(!window.deferAck)setTimeout(()=>window.ack(),180);
    }});
    handles.push(module.default(mount,props()));
    window.getText=()=>mount.querySelector('[data-result-text]').value;
    window.isEditable=()=>!mount.querySelector('[data-result-text]').disabled;
    window.select=n=>mount.querySelector('[data-shot="s'+n+'"]').click();
   }else{
    const rowState=n=>({schema:'hmb-agent-shot-row',version:1,shot:rows[n-1],selected:selected===n,expanded:selected===n,request_id:acks[n]||'',display_page:{prompt:'Prompt '+n,additional_context:'Context '+n,output:'Result '+n}});
    // Emulate the documented live-value store: onChange clears it; undefined
    // returns the native control to its last committed authoritative value.
    let committed='Prompt 1';
    const live=value=>{if('prompt' in value)document.querySelector('#prompt').value=value.prompt??committed;};
    const props=n=>({value:rowState(n),onLiveChange:live,onChange:value=>{
     calls.push(value);window.sentAt=performance.now();live({prompt:undefined});
     window.ack=()=>{selected=value.shot.number;acks[selected]=value.action.request_id;committed='Prompt '+selected;live({prompt:undefined});handles.forEach((h,i)=>h.update(props(i+1)));};
     if(!window.deferAck)setTimeout(()=>window.ack(),180);
    }});
    rows.forEach((r,i)=>{const el=document.createElement('div');el.id='r'+r.number;mount.append(el);handles.push(module.default(el,props(i+1)));});
    window.getText=()=>document.querySelector('#prompt').value;
    window.isEditable=()=>!mount.querySelector('#r'+selected+' .agent-shot-tab').disabled;
    window.select=n=>mount.querySelector('#r'+n+' .agent-shot-tab').click();
   }
   window.dispose=()=>handles.forEach(h=>h.cleanup());
  },{code,kind});
  for(const n of [2,5,1,4,3]){
   const sample=await page.evaluate(async({n,kind})=>{
    const expected=(kind==='Agent'?'Prompt ':'Result ')+n;window.sentAt=0;const start=performance.now();window.select(n);
    const immediate=window.getText();let paint=null,editable=null;
    await new Promise((resolve,reject)=>{const tick=()=>{const now=performance.now();if(paint===null&&window.getText()===expected)paint=now-start;if(paint!==null&&window.isEditable()){editable=now-start;resolve();}else if(now-start>2000)reject(new Error(JSON.stringify({text:window.getText(),expected,editable:window.isEditable(),calls})));else requestAnimationFrame(tick);};requestAnimationFrame(tick);});
    return {shot:n,immediate,paint_ms:paint,editable_ms:editable,dispatch_ms:window.sentAt-start};
   },{n,kind});
   if(variant==='after'){
    assert.equal(sample.immediate,(kind==='Agent'?'Prompt ':'Result ')+n);
    assert.ok(sample.dispatch_ms<60,'command must not wait for animation frames');
   }
   results.rows.push({variant,kind,...sample});
  }
  if(variant==='after'){
   await page.evaluate(()=>{window.deferAck=true;window.select(2);});
   const before=await page.evaluate(()=>calls.length);
   await page.evaluate(()=>window.select(4));
   assert.equal(await page.evaluate(()=>calls.length),before,'no second mutation overtakes unconfirmed identity');
   if(kind==='Agent'){
    assert.equal(await page.evaluate(()=>Object.hasOwn(calls.at(-1),'display_page')),false,'display is not submitted as authoring');
    const blocked=await page.evaluate(()=>{const e=new Event('beforeinput',{bubbles:true,cancelable:true});document.querySelector('#prompt').dispatchEvent(e);return e.defaultPrevented;});
    assert.equal(blocked,true,'native edits remain quarantined until exact ACK');
   }else assert.equal(await page.locator('[data-result-text]').isDisabled(),true);
   await page.evaluate(()=>window.ack());
   assert.equal(await page.evaluate(()=>window.isEditable()),true);
  }
  await page.evaluate(()=>window.dispose());assert.deepEqual(errors,[]);await page.close();
 }
 results.passed=true;
 console.log(JSON.stringify(results));
}finally{await browser.close();fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'paint-comparison.json'),JSON.stringify(results,null,2));}
