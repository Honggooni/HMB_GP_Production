import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../..',import.meta.url));
const source=fs.readFileSync(path.join(root,'widgets/HMBColorLUTLibraryWidget.js'),'utf8');
const {chromium}=nativeTestPlaywright();
const browser=await chromium.launch({executablePath:nativeTestBrowserPath(),headless:true});
try{
 const page=await browser.newPage();let external=0;await page.route('**/*',r=>{external++;return r.abort()});await page.setContent('<main></main>');
 const result=await page.evaluate(async source=>{
  const module=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source+'\nexport {hmbNativeUiContract,hmbNativeUiLockedEchoKey};'))));
  const container=document.querySelector('main');container.innerHTML='<textarea>한글 편집</textarea>'+Array.from({length:50},(_,i)=>`<button>${i}</button>`).join('');
  const buttons=[...container.querySelectorAll('button')];let props,updates=0,calls=[],commands=[];
  const mount=(_c,p)=>{props=p;return {update(next){props=next;updates++;buttons[0].disabled=next.value==='blocked'||next.value?.blocked===true;},cleanup(){}}};
  const options={widget:'Synthetic',library:'HMB_GP_Production',height:300,hide_label:true};
  const h=module.hmbNativeUiContract(container,{disabled:true,value:'same',ui_options:options,nodeName:'Fixture',parameterName:'UI',onChange:v=>calls.push(['old',v]),onCommand:v=>commands.push(['old',v])},mount,{kind:'lut'});
  let mutations=0;const observer=new MutationObserver(rows=>{mutations+=rows.filter(r=>r.attributeName==='disabled').length});observer.observe(container,{attributes:true,subtree:true,attributeFilter:['disabled']});
  const text=container.querySelector('textarea');text.focus();text.setSelectionRange(2,4);const firstCallback=props.onChange,activeBefore=document.activeElement;
  for(let i=0;i<10;i++)h.update({disabled:true,value:'same',ui_options:{...options},nodeName:'Fixture',parameterName:'UI',onChange:v=>calls.push(['new',v]),onCommand:v=>commands.push(['new',v])});
  await Promise.resolve();await Promise.resolve();const same={mutations,updates,allDisabled:buttons.every(b=>b.disabled),sameFocus:document.activeElement===activeBefore,selection:[text.selectionStart,text.selectionEnd]};
  firstCallback({action:'cancel'});props.onCommand({action:'cancel'});
  let editRejected=false;try{firstCallback({action:'export'});}catch{editRejected=true;}
  options.height=301;h.update({disabled:true,value:'same',ui_options:options,nodeName:'Fixture',parameterName:'UI',onChange:v=>calls.push(['option',v])});
  const optionMutationDetected=updates===1;
  h.update({disabled:true,value:'blocked',onChange:v=>calls.push(['changed',v])});
  h.update({disabled:false,value:'blocked',onChange:v=>calls.push(['unlocked',v])});
  const originalOwnedDisabled=buttons[0].disabled;
  h.cleanup();observer.disconnect();
  let retired=false;try{firstCallback({action:'cancel'});}catch{retired=true;}
  const complex=document.createElement('div');complex.innerHTML='<button>x</button>';document.body.append(complex);
  let complexUpdates=0,value={blocked:false};const b=complex.firstChild;
  const ch=module.hmbNativeUiContract(complex,{disabled:true,value},(_c,p)=>({update(next){complexUpdates++;b.disabled=next.value.blocked},cleanup(){}}),{kind:'lut'});
  value.blocked=true;ch.update({disabled:true,value});ch.update({disabled:false,value});const inPlacePreserved=b.disabled;ch.cleanup();
  let retainedCallback,acceptedCalls=0,staleCalls=0;
  const stale=module.hmbNativeUiContract({}, {disabled:true,value:'accepted',onChange(){acceptedCalls++}},(_c,p)=>{retainedCallback=p.onChange;return{update(){/* The widget rejects this stale echo. */},cleanup(){}}},{kind:'lut'});
  stale.update({disabled:true,value:'stale',onChange(){staleCalls++}});
  stale.update({disabled:true,value:'stale',onChange(){staleCalls++}});
  retainedCallback({action:'cancel'});stale.cleanup();
  const cycle={};cycle.self=cycle;
  return {same,calls,commands,editRejected,originalOwnedDisabled,retired,complexUpdates,inPlacePreserved,
   complexFallback:module.hmbNativeUiLockedEchoKey({disabled:true,value:cycle})===null,
   functionFallback:module.hmbNativeUiLockedEchoKey({disabled:true,value:'same',custom(){}})===null,
   staleEchoCallbackPreserved:acceptedCalls===1&&staleCalls===0,
   nestedOptionsFallback:module.hmbNativeUiLockedEchoKey({disabled:true,value:'same',ui_options:{nested:[]}})===null,optionMutationDetected};
 },source);
 assert.deepEqual(result.same,{mutations:0,updates:0,allDisabled:true,sameFocus:true,selection:[2,4]});
 assert.equal(result.calls[0][0],'new');assert.equal(result.commands[0][0],'new');
 for(const key of ['editRejected','originalOwnedDisabled','retired','inPlacePreserved','complexFallback','functionFallback','staleEchoCallbackPreserved','nestedOptionsFallback','optionMutationDetected'])assert.equal(result[key],true,key);
 assert.equal(result.complexUpdates,2);assert.equal(external,0);
 console.log('Locked echo: zero mutations/repaint, fresh guarded callbacks, IME/caret and native disabled ownership PASS');
}finally{await browser.close()}
