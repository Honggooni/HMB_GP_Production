// Delayed native file-input selection. Product functions, no engine/media decode.
import assert from 'node:assert/strict';import crypto from 'node:crypto';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {createRequire} from 'node:module';
const root=path.resolve(import.meta.dirname,'../..'),require=createRequire(import.meta.url);
const {chromium}=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const source=fs.readFileSync(path.join(root,'widgets/HMBVideoPickerLibraryWidget_v032.js'),'utf8');
const receipt={scope:'Actual product file-input functions in isolated Chrome; native Electron OS picker not exercised',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),network:0,paid:0,cases:[]};
const browser=await chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>{receipt.network++;return route.abort();});
 await page.setContent('<div id="mount"><input type="file" id="import-video-asset" hidden><button id="open">open</button></div>');
 await page.evaluate(async code=>{
  window.widget=await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
  window.a='00000000-0000-4000-8000-000000000001';window.b='00000000-0000-4000-8000-000000000002';window.fallback=a;window.results=[];
  window.listeners=new Set();const add=window.addEventListener.bind(window),remove=window.removeEventListener.bind(window);
  window.addEventListener=(type,fn,opt)=>{if(type==='blur'||type==='focus')listeners.add(fn);return add(type,fn,opt);};
  window.removeEventListener=(type,fn,opt)=>{if(type==='blur'||type==='focus')listeners.delete(fn);return remove(type,fn,opt);};
  window.install=()=>{document.querySelector('input').onchange=event=>results.push({target:widget.hmbConsumeVideoPickerFileInputTarget(mount,fallback,event.target),files:event.target.files.length});};install();
  document.querySelector('#open').onclick=()=>widget.hmbOpenVideoPickerFileInput(mount,a);
 },source);
 const choose=async()=>{const pending=page.waitForEvent('filechooser');await page.locator('#open').click();return pending;};
 let chooser=await choose();await page.waitForTimeout(900);
 assert.equal(await page.evaluate(()=>mount.__hmbPendingImportWorkspaceUuid), '00000000-0000-4000-8000-000000000001');
 assert.equal(await page.evaluate(()=>widget.hmbOpenVideoPickerFileInput(mount,b)),false);
 await page.evaluate(()=>window.fallback=b);
 await chooser.setFiles({name:'owner-only.mp4',mimeType:'video/mp4',buffer:Buffer.from('synthetic ownership-only bytes')});
 assert.equal(await page.evaluate(()=>results.at(-1).target),'00000000-0000-4000-8000-000000000001');
 assert.equal(await page.evaluate(()=>listeners.size),0);
 receipt.cases.push('900ms native chooser retains A despite active B; second open blocked until change; no listener residue');
 chooser=await choose();await page.evaluate(()=>document.querySelector('input').dispatchEvent(new Event('cancel')));
 assert.equal(await page.evaluate(()=>Boolean(mount.__hmbVideoImportDialogPending)),false);
 assert.equal(await page.evaluate(()=>widget.hmbConsumeVideoPickerFileInputTarget(mount,b)),'');
 chooser=await choose();await chooser.setFiles([]);
 // Chromium may report an unchanged empty selection as cancel rather than change.
 assert.equal(await page.evaluate(()=>Boolean(mount.__hmbVideoImportDialogPending)),false);
 receipt.cases.push('Cancel and empty native selection retire owner, permit retry, and never fall back to B');
 chooser=await choose();await page.evaluate(()=>{window.oldInput=document.querySelector('input');widget.hmbCancelVideoPickerFileInput(mount);const replacement=oldInput.cloneNode();oldInput.replaceWith(replacement);install();});
 const next=page.waitForEvent('filechooser');await page.evaluate(()=>widget.hmbOpenVideoPickerFileInput(mount,b));await next;
 assert.equal(await page.evaluate(()=>widget.hmbConsumeVideoPickerFileInputTarget(mount,a,oldInput)),'');
 assert.equal(await page.evaluate(()=>mount.__hmbPendingImportWorkspaceUuid),'00000000-0000-4000-8000-000000000002');
 await page.evaluate(()=>{mount.__hmbVideoPickerDeleted=true;window.late=widget.hmbConsumeVideoPickerFileInputTarget(mount,a,oldInput);widget.hmbCancelVideoPickerFileInput(mount);mount.__hmbVideoPickerDeleted=false;});
 assert.equal(await page.evaluate(()=>late),'');assert.equal(await page.evaluate(()=>listeners.size),0);
 receipt.cases.push('Unmount/remount retires old input; late old callback cannot consume new B owner; deleted node ignores late result');
 await page.evaluate(()=>{const input=document.querySelector('input');window.realClick=input.click;input.click=()=>{throw Error('synthetic picker throw');};window.threwOpen=widget.hmbOpenVideoPickerFileInput(mount,a);input.click=realClick;});
 assert.equal(await page.evaluate(()=>threwOpen),false);assert.equal(await page.evaluate(()=>Boolean(mount.__hmbVideoImportDialogPending)),false);
 receipt.cases.push('Opening failure clears owner and listeners for retry');
 chooser=await choose();await page.evaluate(()=>{window.dispatchEvent(new Event('focus'));});await page.waitForTimeout(140);
 assert.equal(await page.evaluate(()=>mount.__hmbPendingImportWorkspaceUuid),'00000000-0000-4000-8000-000000000001');
 await page.evaluate(()=>{window.dispatchEvent(new Event('blur'));window.dispatchEvent(new Event('focus'));});
 await page.waitForTimeout(140);assert.equal(await page.evaluate(()=>Boolean(mount.__hmbVideoImportDialogPending)),false);
 assert.equal(await page.evaluate(()=>listeners.size),0);
 receipt.cases.push('Focus without native blur cannot retire chooser; guarded delayed empty focus-return fallback permits retry');
 assert.deepEqual(errors,[]);assert.equal(receipt.network,0);receipt.errors=errors;receipt.passed=true;
 const out=process.env.HMB_POPUP_REPORT_DIR||path.join(root,'reports/popup-compact-audit-20261023');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'file-chooser-owner-regression.json'),JSON.stringify(receipt,null,2));
 console.log(`HMB VideoPicker file chooser owner: PASS (${receipt.cases.length} Chromium cases; no engine/provider)`);
}finally{await browser.close();}
