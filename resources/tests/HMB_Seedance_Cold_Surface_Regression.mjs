/** Actual widget in isolated Chromium. No live graph, media, network or inference. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const arg = key => { const i=process.argv.indexOf(key); return i<0?'':process.argv[i+1]; };
const root=path.resolve(arg('--library-root') || fileURLToPath(new URL('../..',import.meta.url)));
const require=createRequire(import.meta.url);
let pw;try{pw=require('playwright');}catch{pw=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const report={schema:'hmb-seedance-cold-surface/v1',scope:'Isolated actual widget; not Desktop',cases:[],external_requests:0,paid_calls:0};
const browser=await pw.chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{report.external_requests++;return r.abort();});
 await page.setContent('<main></main>');
 await page.evaluate(async code=>{
  window.w=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(code))));
  window.clone=x=>JSON.parse(JSON.stringify(x));
  window.ids=[1,2,3,4,5,6,7].map(n=>`11111111-1111-4111-8111-${String(n).padStart(12,'0')}`);
  window.route={schema:'hmb-seedance-remote-prompt-route',version:1,connected:true,source_node_name:'HMB Agent',target_node_name:'HMB Seedance Generation',source_parameter:'output',target_parameter:'prompt'};
  window.catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:ids[0],channel_uuid:ids[1],generation:1,metadata_sha256:'a'.repeat(64),shots:[1,2,3,4,5].map(n=>({shot_uuid:ids[n+1],number:n,name:'Shot '+n,revision:1}))};
  window.state=(n=1)=>({schema:'hmb-seedance-shot-ui',schema_version:2,shot_catalog:clone(catalog),shot:{channel_uuid:n?ids[1]:'',shot_uuid:n?ids[n+1]:'',number:n||1,name:n?'Shot '+n:'Only'},execution_mode:n?'shot':'only',requested_mode:n?'shot':'only',execution_mode_revision:1,execution_mode_state_revision:1,execution_mode_instance:'a'.repeat(32),remote_prompt_route:n?route:{connected:false}});
  window.make=(depth=2,edges=true,value=state())=>{
   const viewport=document.createElement('div');viewport.className='react-flow__viewport';
   const nodes=document.createElement('div');nodes.className='react-flow__nodes';viewport.append(nodes);
   const node=document.createElement('div');node.className='react-flow__node';nodes.append(node);
   let header=node;for(let i=0;i<depth;i++){const d=document.createElement('div');header.append(d);header=d;}
   document.querySelector('main').append(viewport);
   const f={viewport,header,node,writes:[]};
   f.addEdges=(prefix='')=>{const layer=document.createElement('div');layer.className='react-flow__edges';viewport.prepend(layer);
    const edge=document.createElement('div');edge.className='react-flow__edge';edge.setAttribute('data-id',prefix+'HMB Agent-output-HMB Seedance Generation-prompt-1');edge.setAttribute('aria-label','Edge from HMB Agent to HMB Seedance Generation');layer.append(edge);
    const other=edge.cloneNode();other.setAttribute('data-id','HMB Agent-agent-HMB Seedance Generation-prompt-1');layer.append(other);f.layer=layer;f.edge=edge;f.other=other;};
   if(edges)f.addEdges();
   f.props=value=>({value,onChange(next){f.writes.push(clone(next));}});
   f.controller=w.default(header,f.props(value));f.update=value=>f.controller.update(f.props(value));
   f.cleanup=()=>{f.controller.cleanup();viewport.remove();};return f;
  };
  window.settle=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  window.hidden=e=>getComputedStyle(e).display==='none';
 },fs.readFileSync(path.join(root,'widgets/HMBSeedanceGenerationWidget.js'),'utf8'));
 async function check(name,fn){try{const details=await fn();report.cases.push({name,passed:true,...details});}catch(e){report.cases.push({name,passed:false,error:e.message});}}
 await check('deep_native_parameter_wrappers',async()=>{
  const r=await page.evaluate(async()=>{const f=make(28);await settle();const r={managedHidden:hidden(f.edge),foreignVisible:!hidden(f.other)};f.cleanup();return r;});
  assert.equal(r.managedHidden,true);assert.equal(r.foreignVisible,true);return r;
 });
 await check('late_edge_layer_without_second_widget_update',async()=>{
  const r=await page.evaluate(async()=>{const f=make(2,false);f.addEdges();await settle();const r={managedHidden:hidden(f.edge),foreignVisible:!hidden(f.other)};f.cleanup();return r;});
  assert.equal(r.managedHidden,true);assert.equal(r.foreignVisible,true);return r;
 });
 await check('react_flow_edge_layer_replacement',async()=>{
  const r=await page.evaluate(async()=>{const f=make();f.layer.remove();f.addEdges();await settle();const r={managedHidden:hidden(f.edge)};f.cleanup();return r;});
  assert.equal(r.managedHidden,true);return r;
 });
 await check('temporary_editor_edge_id_and_cleanup',async()=>{
  const r=await page.evaluate(async()=>{const f=make(2,false);f.addEdges('temp-');f.update(state());await settle();const r={managedHidden:hidden(f.edge),foreignVisible:!hidden(f.other)};f.controller.cleanup();r.markerCleared=!f.edge.hasAttribute('data-hmb-seedance-prompt-edge');f.viewport.remove();return r;});
  assert.equal(r.managedHidden,true);assert.equal(r.foreignVisible,true);assert.equal(r.markerCleared,true);return r;
 });
 await check('cold_only_catalog_arrives_without_second_click',async()=>{
  const r=await page.evaluate(()=>{const empty={...state(0),shot_catalog:{}};const f=make(2,false,empty),select=f.header.querySelector('select');
   const before=select.selectedOptions[0].textContent;f.update({...state(0),execution_mode_state_revision:2});
   const r={before,after:select.selectedOptions[0].textContent,options:select.options.length,sameSelector:select===f.header.querySelector('select'),writes:f.writes.length};f.cleanup();return r;});
  assert.equal(r.before,'Only');assert.equal(r.after,'Only');assert.equal(r.options,6);assert.equal(r.sameSelector,true);assert.equal(r.writes,0);return r;
 });
 await check('single_choice_ack_and_repeated_shot_switch',async()=>{
  const r=await page.evaluate(()=>{const f=make(2,false,state(0)),select=f.header.querySelector('select');let rev=1,all=true;
   for(const n of [1,2,3,4,5,0,5,4,3,2,1,0]){select.value=n?ids[1]+'\u001f'+ids[n+1]:'__hmb_shot_only__';select.dispatchEvent(new Event('change',{bubbles:true}));rev++;f.update({...state(n),execution_mode_revision:rev,execution_mode_state_revision:rev});all=all&&!f.header.__hmbSeedancePendingShot&&select.value===(n?ids[1]+'\u001f'+ids[n+1]:'__hmb_shot_only__');}
   const r={allApplied:all,writes:f.writes.length,sameSelector:select===f.header.querySelector('select')};f.cleanup();return r;});
  assert.equal(r.allApplied,true);assert.equal(r.writes,12);assert.equal(r.sameSelector,true);return r;
 });
 report.errors=errors;report.passed=report.cases.every(c=>c.passed)&&!errors.length&&!report.external_requests;
}finally{await browser.close();}
if(arg('--out'))fs.writeFileSync(arg('--out'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
if(!report.passed&&!process.argv.includes('--observe'))process.exitCode=1;
