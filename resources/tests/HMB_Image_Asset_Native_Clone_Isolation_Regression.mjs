// Product widget/PROJECT_ROOT helper in a native allocator-like Chrome tree.
import assert from 'node:assert/strict';import crypto from 'node:crypto';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {createRequire} from 'node:module';
const root=path.resolve(import.meta.dirname,'../..'),require=createRequire(import.meta.url),{chromium}=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const source=fs.readFileSync(path.join(root,'widgets/HMBImageAssetLibraryWidget.js'),'utf8');
const receipt={scope:'Actual product widget in isolated Chromium native allocator/footer clone fixture; no live editor or provider',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),external_requests:0,paid_calls:0,cases:[]};
const browser=await chromium.launch({headless:true,executablePath:process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>{receipt.external_requests++;return route.abort();});
 await page.setContent(`<style>.opacity-0{opacity:0}.pointer-events-none{pointer-events:none}.hidden-measure{visibility:hidden}.live-column{height:1000px;min-height:30px;max-height:1100px;flex:1 1 auto;overflow:auto}</style>
 <div class="react-flow__node" data-id="Synthetic Native Clone" style="height:1200px;width:1400px"><div class="flex flex-col h-full" style="height:100%">
 <div id="live-body" class="live-column flex-1 min-h-0"><div id="project-wrapper"><div data-parameter-name="PROJECT_ROOT" id="project-row"><input value="C:/fixture"></div></div><div id="live-widget"><div class="hmb-image-assets"></div></div></div>
 <div id="other-body" class="live-column"><div id="other-project-wrapper"><div data-parameter-name="PROJECT_ROOT"><input value="C:/other"></div></div><div id="other-widget"><div class="hmb-image-assets"></div></div></div>
 <div class="absolute left-0 right-0 pointer-events-none hidden-measure" style="position:absolute;height:1px"><div id="measurement-widget"><div class="hmb-image-assets"></div></div></div>
 <footer><div id="footer-shell" class="absolute opacity-0 pointer-events-none" style="position:absolute;height:1px"><div id="footer-widget"><div class="hmb-image-assets"></div></div></div></footer></div></div>`);
 await page.evaluate(async code=>{window.w=await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);window.styleSnapshot=()=>['live-body','other-body'].map(id=>document.getElementById(id).getAttribute('style'));window.before=styleSnapshot();},source);
 for(const id of ['footer-widget','measurement-widget']){
  assert.equal(await page.evaluate(id=>w.hmbCollapseNativeProjectRootRows(document.getElementById(id)),id),0);
  assert.deepEqual(await page.evaluate(()=>styleSnapshot()),await page.evaluate(()=>before));
 }
 receipt.cases.push('Opacity-zero footer and visibility-hidden measurement copies cannot mutate live/sibling columns');
 const rows=await page.evaluate(()=>{document.querySelector('#live-widget').style.pointerEvents='none';const changed=w.hmbCollapseNativeProjectRootRows(document.querySelector('#live-widget'));return {changed,columns:styleSnapshot(),wrappers:['project-wrapper','other-project-wrapper'].map(id=>getComputedStyle(document.getElementById(id)).height)};});
 assert.equal(rows.changed,2);assert.deepEqual(rows.columns,await page.evaluate(()=>before));assert.deepEqual(rows.wrappers,['0px','0px']);
 receipt.cases.push('Visible locked/read-only widget may hide PROJECT_ROOT row only; all other widget-bearing ancestors retain exact styles');
 await page.evaluate(()=>{window.live=w.default(document.querySelector('#live-widget'),{value:{assets:[]},onChange:()=>{throw Error('unexpected fixture publication');}});window.liveBaseline=styleSnapshot();});
 for(let cycle=0;cycle<12;cycle++){
  await page.evaluate(()=>{
   const host=document.querySelector('#footer-widget');window.footer=w.default(host,{value:{assets:[]},onChange:()=>{throw Error('hidden copy cannot publish');}});
   w.hmbCollapseNativeProjectRootRows(host);footer.cleanup();
  });
  assert.deepEqual(await page.evaluate(()=>styleSnapshot()),await page.evaluate(()=>liveBaseline));
 }
 assert.equal(await page.locator('#live-widget .hmb-image-assets').count(),1);
 receipt.cases.push('Twelve actual footer factory mount/teardown cycles preserve live body and sibling styles');
 await page.evaluate(()=>live.cleanup());assert.deepEqual(await page.evaluate(()=>styleSnapshot()),await page.evaluate(()=>liveBaseline));
 assert.deepEqual(errors,[]);assert.equal(receipt.external_requests,0);receipt.passed=true;receipt.errors=errors;
 const out=process.env.HMB_POPUP_REPORT_DIR||path.join(root,'reports/popup-compact-audit-20261023');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'asset-native-clone-isolation.json'),JSON.stringify(receipt,null,2));
 console.log(`HMB ImageAsset native clone isolation: PASS (${receipt.cases.length} Chromium cases; no editor/provider)`);
}finally{await browser.close();}
