/** Original Agent widget: explicit recovery action, no native editor rebuild. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const code=fs.readFileSync(path.join(root,'widgets/HMBAgentLibraryWidget.js'),'utf8');
const require=createRequire(import.meta.url);let playwright;
try{playwright=require('playwright');}catch{playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const out=path.join(root,'reports/critical-agent-isolation-20261020');fs.mkdirSync(out,{recursive:true});
const report={passed:false,cases:[],external_requests:0,live_editor_actions:0,model_calls:0,render_calls:0,
  source_sha256:crypto.createHash('sha256').update(code).digest('hex')};
const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.HMB_WIDGET_TEST_BROWSER||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{report.external_requests++;return route.abort();});
  await page.setContent('<section class="react-flow__node" style="width:720px"><div id="header" data-parameter-name="HMB_AGENT_UI"></div><div data-parameter-name="prompt"><textarea id="native">Original native authored prompt</textarea></div></section>');
  await page.evaluate(async source=>{
    window.widget=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
    const channel='11111111-1111-4111-8111-111111111111';
    window.catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:'publisher',channel_uuid:channel,generation:1,metadata_sha256:'a'.repeat(64),shots:Array.from({length:5},(_,i)=>({shot_uuid:`shot-${i+1}`,number:i+1,name:`Own authored asset ${i+1}`,revision:1}))};
    window.calls=[];window.state={schema:'hmb-agent-ui',schema_version:2,shot_manager:true,shot_catalog:catalog,shot:{channel_uuid:channel,shot_uuid:'shot-1',number:1,name:'Own authored asset 1'}};
    window.props=()=>({value:structuredClone(state),onChange:next=>{calls.push(structuredClone(next));return Promise.resolve();}});
    window.handle=widget.default(document.querySelector('#header'),props());
    window.originalHeader=document.querySelector('.hmb-agent-dashboard');window.originalInput=document.querySelector('#native');
    window.update=()=>handle.update(props());
  },code);
  assert.equal(await page.locator('.hmb-agent-dashboard').evaluate(node=>node.getBoundingClientRect().height),64);
  assert.equal(await page.locator('.agent-rebind-panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>calls.length),0);
  report.cases.push('Normal manager keeps the same 64px header/colors and has no recovery choice visible');
  await page.evaluate(()=>{state.manual_rebind={required:true,status:'required',expected_source_digest:'d'.repeat(64),request_id:'',reason:'Original inputs preserved',source_node_name:'Legacy Agent',backup_path:'private-recovery.json'};update();});
  assert.equal(await page.locator('.hmb-agent-dashboard').evaluate(node=>node.getBoundingClientRect().height),144);
  assert.equal(await page.locator('.agent-rebind-panel').isVisible(),true);
  assert.equal(await page.locator('.agent-rebind-select option').count(),6);
  assert.equal(await page.locator('.agent-rebind-select').inputValue(),'');
  await page.locator('.agent-rebind-select').selectOption('11111111-1111-4111-8111-111111111111\u001fshot-4');
  assert.equal(await page.evaluate(()=>calls.length),0);
  report.cases.push('Only legacy recovery exposes five actual names with no default choice; selecting a target alone never writes');
  await page.locator('.agent-rebind-confirm').click();
  await page.evaluate(()=>document.querySelector('.agent-rebind-confirm').click());
  const action=await page.evaluate(()=>calls[0].action);
  assert.equal(await page.evaluate(()=>calls.length),1);assert.equal(action.kind,'manual_rebind');assert.equal(action.shot_uuid,'shot-4');assert.equal(action.expected_source_digest,'d'.repeat(64));
  assert.match(action.request_id,/^[a-f0-9]{32}$/);
  assert.equal(await page.locator('.agent-rebind-confirm').isDisabled(),true);
  await page.evaluate(()=>{const saved=state;state={...state,manual_rebind:undefined};update();state=saved;});
  assert.equal(await page.locator('.agent-rebind-panel').isVisible(),true);
  report.cases.push('Explicit confirmation sends one exact UUID/token request, transport resolution and stale baseline cannot acknowledge or hide it');
  await page.evaluate(()=>{state.manual_rebind={...state.manual_rebind,request_id:calls[0].action.request_id,status:'rejected',error:'Target already authored'};update();});
  assert.equal(await page.locator('.agent-rebind-confirm').isDisabled(),false);
  assert.match(await page.locator('.agent-rebind-panel>span').innerText(),/Target already authored/);
  assert.equal(await page.evaluate(()=>document.querySelector('#native')===originalInput && originalInput.value==='Original native authored prompt'),true);
  report.cases.push('Canonical rejection releases only its matching lease and preserves original native input/DOM');
  await page.locator('.agent-rebind-confirm').click();
  assert.equal(await page.evaluate(()=>calls.length),2);
  await page.evaluate(()=>{state.shot={channel_uuid:catalog.channel_uuid,...catalog.shots[3]};state.manual_rebind={...state.manual_rebind,required:false,status:'cleared',error:'',request_id:calls[1].action.request_id};update();});
  assert.equal(await page.locator('.agent-rebind-panel').isVisible(),false);
  assert.equal(await page.locator('.hmb-agent-dashboard').evaluate(node=>node.getBoundingClientRect().height),64);
  assert.equal(await page.evaluate(()=>document.querySelector('.hmb-agent-dashboard')===originalHeader && document.querySelector('#native')===originalInput),true);
  assert.equal(await page.evaluate(()=>document.querySelector('#header').__hmbAgentManualPending===undefined),true);
  assert.deepEqual(errors,[]);assert.equal(report.external_requests,0);
  report.cases.push('Confirmed/cleared matching ACK returns the same native body/header to normal layout without another request');
  report.passed=true;
}finally{await browser.close();fs.writeFileSync(path.join(out,'manual-rebind-ui.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({passed:report.passed,cases:report.cases.length,live_editor_actions:0,paid_calls:0}));
