/** Actual widget/Chrome test: hidden action carriers must preserve native Project (Only) siblings.
 * Native parameter visibility is simulated here and separately verified against the actual SDK.
 * This does not add a second project picker or claim to render the full installed editor.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const arg=(name)=>{const i=process.argv.indexOf(name);return i<0?'':process.argv[i+1]||'';};
const root=path.resolve(arg('--library-root')||fileURLToPath(new URL('../..',import.meta.url)));
const widgetPath=path.join(root,'widgets/HMBSeedanceGenerationWidget.js');
const source=fs.readFileSync(widgetPath,'utf8');
const digest=crypto.createHash('sha256').update(fs.readFileSync(widgetPath)).digest('hex');
const require=createRequire(import.meta.url);
let playwright;
try{playwright=require('playwright');}
catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const browser=await playwright.chromium.launch({executablePath:process.env.HMB_SEEDANCE_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',headless:true});
const report={schema:'hmb-seedance-only-project-native-surface-browser/v1',passed:false,
  widget_sha256:digest,widget_path:widgetPath,scope:'Actual production widget in isolated Chrome; native parameter DOM/visibility is a host fixture, not the installed editor.',
  cases:[],external_requests:0,user_graph_calls:0,paid_calls:0,product_edits:0};
try{
  const page=await browser.newPage({viewport:{width:1000,height:700}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{report.external_requests++;return route.abort();});
  await page.setContent('<!doctype html><meta charset="utf-8"><style>body{background:#080c14;color:#fff}.react-flow__node{width:780px;margin:10px}.native-row{height:44px}select{height:32px}[hidden]{display:none!important}</style><main></main>');
  await page.evaluate(async code=>{
    window.widget=await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
    const ids=[1,2,3,4,5,6,7].map(n=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`);
    const catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:ids[0],channel_uuid:ids[1],generation:1,metadata_sha256:'a'.repeat(64),
      shots:[1,2,3,4,5].map(n=>({shot_uuid:ids[n+1],number:n,name:`Fixture ${n}`,revision:1}))};
    window.state=(number=0)=>({schema:'hmb-seedance-shot-ui',schema_version:2,shot_catalog:catalog,
      shot:number?{channel_uuid:ids[1],shot_uuid:ids[number+1],number,name:`Fixture ${number}`}:{},
      generation:{schema:'hmb-seedance-generation-preview',version:1,phase:'idle',job_id:'',media_revision:0},
      draft:{visible:false,job_id:'',final_visible:false,final_available:false,busy:false}});
    window.makeFixture=shared=>{
      const node=document.createElement('div');node.className='react-flow__node';
      node.innerHTML=`<div data-header></div><div data-stack class="flex-col">
        <div data-command-slot class="flex-shrink-0 overflow-hidden"><div data-parameter-name="HMB_SEEDANCE_REFRESH_COMMAND"><div data-command></div></div></div>
        <div data-native-slot class="flex-shrink-0 overflow-hidden"><div class="native-row" data-parameter-name="only_project"><label>Project (Only)</label><select data-native-project><option>Select Project</option><option>다이노스터</option><option>까투리8</option><option>슈퍼윙즈12</option></select></div></div>
        <div data-broker-slot class="flex-shrink-0 overflow-hidden"><div data-parameter-name="broker_server_url"><div data-broker></div></div></div></div>`;
      document.querySelector('main').append(node);
      const native=node.querySelector('[data-parameter-name="only_project"]');
      if(shared)node.querySelector('[data-command-slot]').append(native);
      const select=native.querySelector('select');const header=node.querySelector('[data-header]');
      const f={node,native,select,header,headerWrites:[],brokerWrites:[],commands:[],projectChanges:0};
      select.addEventListener('change',()=>f.projectChanges++);
      const props=value=>({value,onChange(next){f.headerWrites.push(next);return Promise.resolve();}});
      f.controller=widget.default(header,props(state()));
      f.command=widget.default(node.querySelector('[data-command]'),{value:{schema:'hmb-seedance-refresh-command',version:1},onChange(value){f.commands.push(value);return Promise.resolve();}});
      f.broker=widget.default(node.querySelector('[data-broker]'),{value:'http://127.0.0.1:9',onChange(value){f.brokerWrites.push(value);return Promise.resolve();}});
      f.update=number=>f.controller.update(props(state(number)));
      f.clean=()=>{f.controller.cleanup();f.command.cleanup();f.broker.cleanup();node.remove();};
      return f;
    };
    window.fixtureView=f=>({sameSelect:f.native.querySelector('select')===f.select,
      sameRow:f.node.querySelector('[data-parameter-name="only_project"]')===f.native,
      hidden:f.native.hidden,visible:getComputedStyle(f.native).display!=='none'&&getComputedStyle(f.native).visibility==='visible'&&f.native.getBoundingClientRect().height>0,
      nativeCarrierMarkers:f.native.closest('[data-hmb-seedance-hidden-carrier="true"],[data-hmb-seedance-carrier-slot="true"]')!==null,
      selected:f.select.value,focus:document.activeElement===f.select,
      headerWrites:f.headerWrites.length,brokerWrites:f.brokerWrites.length,commands:f.commands.length,projectChanges:f.projectChanges});
  },source);
  for(const shared of [false,true]){
    const name=shared?'shared-command-native-slot':'separate-native-slot';
    await page.evaluate(shared=>{window.f=makeFixture(shared);},shared);
    await page.locator('[data-native-project]').selectOption('까투리8');
    await page.locator('[data-native-project]').focus();
    await page.evaluate(async()=>{for(let n=0;n<100;n++)f.update(0);await new Promise(resolve=>setTimeout(resolve,30));});
    let view=await page.evaluate(()=>fixtureView(f));
    assert.equal(view.sameSelect,true);assert.equal(view.sameRow,true);assert.equal(view.visible,true);assert.equal(view.focus,true);
    assert.equal(view.selected,'까투리8');assert.equal(view.nativeCarrierMarkers,false);
    assert.equal(view.headerWrites+view.brokerWrites+view.commands,0);assert.equal(view.projectChanges,1);
    for(let number=1;number<=5;number++){
      await page.evaluate(async number=>{f.native.hidden=true;f.update(number);await new Promise(resolve=>setTimeout(resolve,0));},number);
      view=await page.evaluate(()=>fixtureView(f));assert.equal(view.hidden,true);assert.equal(view.visible,false);assert.equal(view.selected,'까투리8');assert.equal(view.sameSelect,true);
    }
    await page.evaluate(async()=>{f.native.hidden=false;f.update(0);for(let n=0;n<100;n++)f.update(0);await new Promise(resolve=>setTimeout(resolve,30));});
    view=await page.evaluate(()=>fixtureView(f));assert.equal(view.visible,true);assert.equal(view.nativeCarrierMarkers,false);assert.equal(view.selected,'까투리8');
    assert.equal(view.headerWrites+view.brokerWrites+view.commands,0);assert.equal(view.projectChanges,1);
    // Cleanup/re-mount must retain the native editable row and authored value.
    await page.evaluate(()=>{f.controller.cleanup();f.command.cleanup();f.broker.cleanup();});
    view=await page.evaluate(()=>fixtureView(f));assert.equal(view.visible,true);assert.equal(view.selected,'까투리8');assert.equal(view.sameSelect,true);
    report.cases.push({name,passed:true,only_status_echoes:200,shot_visibility_projections:5,native_row_identity_retained:true,
      native_value_and_focus_retained:true,native_project_not_written_by_widget:true,cleanup_keeps_native_row:true});
    await page.evaluate(()=>f.node.remove());
  }
  assert.deepEqual(errors,[]);assert.equal(report.external_requests,0);
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(widgetPath)).digest('hex'),digest);
  report.console_errors=errors;report.source_unchanged=true;report.passed=true;
}finally{
  await browser.close();
  const output=arg('--evidence-path');if(output){fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');}
  process.stdout.write(JSON.stringify(report)+'\n');
}
