import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch { console.log("Other widget stale Shot echo: SKIP (optional Playwright runtime unavailable)"); process.exit(0); }
}
const executablePath = process.env.HMB_WIDGET_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  console.log("Other widget stale Shot echo: SKIP (local browser unavailable)");
  process.exit(0);
}
const workspace = fileURLToPath(new URL("../../", import.meta.url));
const files = {
  agent: "HMBAgentLibraryWidget.js",
  seedance: "HMBSeedanceGenerationWidget.js",
  finish: "HMBFinishLookLibraryWidget.js",
  lut: "HMBColorLUTLibraryWidget.js",
};
const html = `<!doctype html><html><head><meta charset="utf-8"></head><body style="background:#05070d">
<div id="agent"></div><div id="seedance"></div><div id="finish"></div><div id="lut"></div>
<script type="module">
import agent from '/agent.js';
import seedance from '/seedance.js';
import finish from '/finish.js';
import lut from '/lut.js';
const publisher='10000000-0000-4000-8000-000000000001';
const channel='20000000-0000-4000-8000-000000000002';
const ids=[1,2,3,4,5].map(n=>'30000000-0000-4000-8000-'+String(n).padStart(12,'0'));
const catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:publisher,channel_uuid:channel,generation:1,metadata_sha256:'a'.repeat(64),shots:ids.map((shot_uuid,i)=>({shot_uuid,number:i+1,name:'Shot '+(i+1),revision:1}))};
const value=(n, revision=0, shotCatalog=catalog)=>({shot_catalog:shotCatalog,shot:{channel_uuid:channel,shot_uuid:ids[n-1],number:n,name:'Shot '+n},revision});
const mounts={agent,seedance,finish,lut};
window.controllers={}; window.states={}; window.published={}; window.controls={}; window.rejections={}; window.syncEcho={};
for(const kind of Object.keys(mounts)){
  const root=document.getElementById(kind), initial=value(1);
  window.states[kind]=initial; window.published[kind]=[]; window.rejections[kind]=[];
  const props={value:initial,onChange(next){
    window.published[kind].push(next);
    const stale=window.syncEcho[kind];
    if(stale){delete window.syncEcho[kind];window.controllers[kind].update({...window.controls[kind],value:stale});}
    return new Promise((_,reject)=>window.rejections[kind].push(reject));
  }};
  window.controls[kind]=props;
  window.controllers[kind]=mounts[kind](root,props);
}
window.step=(kind, n)=>{
  const root=document.getElementById(kind);
  const select=root.querySelector(kind==='agent'?'.agent-shot-select':kind==='seedance'?'.hmb-seedance-shot__select':'[data-shot-selector]');
  const option=Array.from(select.options).find(item=>item.value.endsWith(ids[n-1]));
  if(!option)throw Error(kind+' missing Shot '+n);
  select.value=option.value; select.dispatchEvent(new Event('change',{bubbles:true}));
};
window.echo=(kind,n,revision)=>window.controllers[kind].update({...window.controls[kind],value:value(n,revision)});
window.ack=(kind)=>window.controllers[kind].update({...window.controls[kind],value:window.published[kind].at(-1)});
window.catalogEcho=(kind,n,generation,count,remount=false)=>{
  const nextCatalog={...catalog,generation,shots:catalog.shots.slice(0,count)};
  const next={...window.controls[kind],value:value(n,window.published[kind].at(-1)?.revision||0,nextCatalog)};
  if(remount)window.controllers[kind]=mounts[kind](document.getElementById(kind),next);
  else window.controllers[kind].update(next);
};
window.setSynchronousEcho=(kind,n,generation,count)=>{
  window.syncEcho[kind]=value(n,window.published[kind].at(-1)?.revision||0,
    {...catalog,generation,shots:catalog.shots.slice(0,count)});
};
window.rejectLast=(kind)=>window.rejections[kind].at(-1)(new Error('mock Shot save failed'));
window.localView=(kind)=>{
  const root=document.getElementById(kind);
  if(kind==='lut')root.querySelector('[data-view="graded"]').click();
  if(kind==='finish')root.querySelector('[data-language-toggle]').click();
};
window.visible=(kind)=>{
  const root=document.getElementById(kind);
  const selector=root.querySelector(kind==='agent'?'.agent-shot-select':kind==='seedance'?'.hmb-seedance-shot__select':'[data-shot-selector]');
  const view=root.querySelector(kind==='agent'?'.hmb-agent-dashboard':kind==='seedance'?'.hmb-seedance-shot':kind==='finish'?'.hmb-finish-look':'.hmb-color-lut');
  return {selected:selector?.value||'',number:view?.getAttribute('data-shot-number')||'',published:window.published[kind].length,
    localView:kind==='lut'?root.querySelector('[data-view="graded"]')?.getAttribute('aria-pressed'):
      kind==='finish'?view?.getAttribute('data-language'):''};
};
window.ready=true;
</script></body></html>`;
const server = http.createServer((req, res) => {
  const key = String(req.url || "").replace(/^\//, "").replace(/\.js$/, "");
  if (Object.hasOwn(files, key)) {
    res.setHeader("Content-Type", "text/javascript; charset=utf-8");
    res.end(fs.readFileSync(path.join(workspace, "widgets", files[key])));
  } else {
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.end(html);
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await playwright.chromium.launch({executablePath, headless:true, args:["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"]});
  const page = await browser.newPage();
  const errors=[]; page.on("pageerror", (error)=>errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`, {waitUntil:"networkidle"});
  await page.waitForFunction(()=>window.ready===true);
  const results={};
  for(const kind of Object.keys(files)){
    results[kind]=await page.evaluate(async (kind)=>{
      const snapshots=[];
      const record=(label)=>snapshots.push({label,...window.visible(kind)});
      record('start');
      for(const n of [5,4,3,2,1]){
        window.step(kind,n);record('select-'+n);
        // An asynchronous retained-mode echo of the previously selected Shot
        // must not briefly restore its screen while this selection is pending.
        window.echo(kind,n===5?1:n+1,window.published[kind].at(-1)?.revision||0);
        record('stale-'+n);
      }
      window.ack(kind);record('ack');
      window.echo(kind,2,window.published[kind].at(-1)?.revision||0);record('external');
      window.catalogEcho(kind,2,2,5);record('catalog-advanced');
      window.setSynchronousEcho(kind,2,2,5);
      window.step(kind,5);record('select-again-5');
      window.localView(kind);record('local-view');
      window.catalogEcho(kind,2,1,4,true);record('older-catalog-echo');
      window.catalogEcho(kind,2,3,4);record('deleted-target');
      window.rejectLast(kind);
      await new Promise((resolve)=>setTimeout(resolve,0));
      record('late-rejection');
      window.step(kind,4);record('select-fail-4');
      window.catalogEcho(kind,2,3,4);record('stale-fail-4');
      window.rejectLast(kind);
      await new Promise((resolve)=>setTimeout(resolve,0));
      record('failed-4');
      if(kind==='lut'){
        // LUT has always reported a transport error locally rather than
        // rolling back immediately; a subsequent host echo restores Shot 2.
        window.catalogEcho(kind,2,3,4);record('post-fail-echo');
      }
      return snapshots;
    },kind);
  }
  assert.deepEqual(errors,[],`Browser errors: ${errors.join('; ')}`);
  const violations=[];
  for(const [kind,snapshots] of Object.entries(results)){
    for(const snapshot of snapshots.filter((item)=>/^(select|stale)-[1-5]$/.test(item.label))){
      const expected=Number(snapshot.label.split('-')[1]);
      if(snapshot.number!==String(expected)) violations.push(`${kind}: ${snapshot.label} showed Shot ${snapshot.number}, expected ${expected}`);
    }
    if(snapshots.find((item)=>item.label==='ack')?.number!=='1') violations.push(`${kind}: authoritative ACK did not keep Shot 1`);
    if(snapshots.find((item)=>item.label==='external')?.number!=='2') violations.push(`${kind}: later external selection was not accepted`);
    if(snapshots.find((item)=>item.label==='catalog-advanced')?.number!=='2') violations.push(`${kind}: catalog refresh lost Shot 2`);
    if(snapshots.find((item)=>item.label==='select-again-5')?.number!=='5') violations.push(`${kind}: new Shot 5 selection was delayed`);
    if(kind==='lut' && snapshots.find((item)=>item.label==='local-view')?.localView!=='true') violations.push('lut: graded tab did not select immediately');
    if(kind==='finish' && snapshots.find((item)=>item.label==='local-view')?.localView!=='en') violations.push('finish: language view did not select immediately');
    if(snapshots.find((item)=>item.label==='older-catalog-echo')?.number!=='5') violations.push(`${kind}: older catalog flashed another Shot`);
    if(kind==='lut' && snapshots.find((item)=>item.label==='older-catalog-echo')?.localView!=='true') violations.push('lut: stale Shot echo reset the graded tab');
    if(kind==='finish' && snapshots.find((item)=>item.label==='older-catalog-echo')?.localView!=='en') violations.push('finish: stale Shot echo reset the language view');
    if(snapshots.find((item)=>item.label==='deleted-target')?.number!=='2') violations.push(`${kind}: deleted target was not released to authoritative Shot 2`);
    if(snapshots.find((item)=>item.label==='late-rejection')?.number!=='2') violations.push(`${kind}: superseded rejection rolled back a deleted Shot`);
    if(snapshots.find((item)=>item.label==='select-fail-4')?.number!=='4') violations.push(`${kind}: Shot 4 selection was delayed`);
    if(snapshots.find((item)=>item.label==='stale-fail-4')?.number!=='4') violations.push(`${kind}: stale echo flashed during a failed request`);
    if(snapshots.find((item)=>item.label==='failed-4')?.number!==(kind==='lut'?'4':'2')) violations.push(`${kind}: failure behavior changed unexpectedly`);
    if(kind==='lut' && snapshots.find((item)=>item.label==='post-fail-echo')?.number!=='2') violations.push('lut: host echo after failed request was not accepted');
  }
  assert.deepEqual(violations,[],`Shot echo errors:\n${violations.join('\n')}`);
  console.log("Other widget stale Shot echo: PASS (Agent, Seedance, Finish Look, Color LUT; 5→1, stale echoes, ACK, external update)");
} finally {
  await browser?.close();
  await new Promise((resolve)=>server.close(resolve));
}
