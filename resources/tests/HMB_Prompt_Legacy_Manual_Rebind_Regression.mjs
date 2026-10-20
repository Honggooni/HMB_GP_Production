import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const source=fs.readFileSync(new URL('../../widgets/HMBPromptLibraryScopedBindingWidget.js',import.meta.url),'utf8');
const channel='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const rows=Array.from({length:5},(_,i)=>({channel_uuid:channel,shot_uuid:`cccccccc-cccc-4ccc-8ccc-${String(i+1).padStart(12,'0')}`,number:i+1,name:`Asset ${i+1}`,selected_source_uids:[]}));
const html=`<!doctype html><meta charset="utf-8"><div class="react-flow__node" style="width:1800px;height:1350px"><div style="height:96px">Native header fixture</div><div id="host"></div></div><script type="module">
import mount,* as widget from '/widget.js';
window.sent=[];window.install=number=>{
 window.controller?.cleanup();
 window.state=widget.normalizeState({multi_shot_enabled:false,shot:{channel_uuid:'old-channel',shot_uuid:'old-shot-'+number,number,name:'Original '+number},
  text:{SCENE_DIRECTIVE:'Exact legacy literal '+number+' {SIGN}'},images:[{slot:1,label:'Original actor '+number,manual:true}],
  image_asset:{shot_catalog:${JSON.stringify(rows)},shot_catalog_routing:{publisher_instance_uuid:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',channel_uuid:'${channel}',generation:1,metadata_sha256:'a'.repeat(64)}},
  manual_rebind:{required:true,source_node_name:'Original Prompt '+number,expected_source_digest:'b'.repeat(64),message:'Original inputs preserved; explicitly choose this Shot.'}});
 window.before=structuredClone(window.state);
 window.controller=mount(document.getElementById('host'),{value:JSON.stringify(window.state),onChange:value=>window.sent.push(JSON.parse(value))});
};window.install(1);window.ready=true;
</script>`;
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
let external=0;
try{
 const page=await browser.newPage({viewport:{width:1900,height:1500}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',route=>{if(new URL(route.request().url()).hostname!=='127.0.0.1'){external++;return route.abort();}return route.continue();});
 await page.goto('http://127.0.0.1:'+server.address().port);
 await page.waitForFunction(()=>window.ready);
 for(let number=1;number<=5;number++){
  await page.evaluate(n=>window.install(n),number);
  const before=await page.evaluate(()=>({sent:window.sent.length,notice:!!document.querySelector('[data-manual-rebind-notice]'),inert:document.querySelector('.layout')?.inert,disabled:document.querySelector('[data-shot-selector]')?.disabled}));
  assert.equal(before.notice,true);assert.equal(before.inert,true);assert.equal(before.disabled,false);
  await page.locator('[data-shot-selector]').selectOption(rows[number-1].shot_uuid);
  await page.waitForFunction(count=>window.sent.length>count,before.sent);
  const result=await page.evaluate(()=>({request:window.sent.at(-1),before:window.before}));
  assert.deepEqual(result.request.manual_rebind.confirmation,{channel_uuid:channel,shot_uuid:rows[number-1].shot_uuid});
  assert.equal(result.request.manual_rebind.expected_source_digest,'b'.repeat(64));
  assert.equal(result.request.shot.shot_uuid,rows[number-1].shot_uuid);
  assert.deepEqual(result.request.text,result.before.text);
  assert.equal(result.request.images[0].label,result.before.images[0].label);
 }
 assert.deepEqual(errors,[]);assert.equal(external,0);
 console.log('Prompt legacy manual rebind Chromium: PASS (5 explicit UUID selections; visible notice; original body inert; authored literals retained; zero external/live/paid requests)');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
