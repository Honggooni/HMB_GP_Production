// No Desktop/SDK: real widget modules, native void callbacks, virtual clock.
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import assert from 'node:assert/strict';import {fileURLToPath} from 'node:url';
import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),productRoot=process.env.HMB_AUTHORITY_TIMEOUT_WIDGET_ROOT||root;
const out=path.resolve(process.env.HMB_AUTHORITY_TIMEOUT_REPORT_DIR||path.join(root,'reports/regression-checks/HMB_Image_Asset_First_Project_Authority_Timeout_Regression'));fs.mkdirSync(out,{recursive:true});
const main=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetLibraryWidget.js'),'utf8'),bridge=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetThumbnailPatchBridgeWidget.js'),'utf8');
const baseline=process.argv.includes('--baseline'),browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});
const proof={status:'RUNNING',scope:'Isolated real widgets; native void callback and optimistic/canonical event fixture. Virtual time is not measured production latency.',baseline,cases:{},external_requests:0,actual_Desktop:false,SDK_requests:0,paid_requests:0};
try{
 for(const kind of (baseline?['single_selection_drop_first','drop_first','late_first','callback_throw','callback_reject']:['single_selection_drop_first','drop_first','late_first','no_event','scope_changed','disposed','callback_throw','callback_reject','lease_recreated','expired_timer','late_after_deadline'])){
  const context=await browser.newContext({viewport:{width:1450,height:950}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/*',r=>{if(r.request().url()==='http://127.0.0.1/authority-timeout')return r.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'});proof.external_requests++;return r.abort()});
  await page.clock.install({time:new Date(0)});await page.goto('http://127.0.0.1/authority-timeout');await page.clock.pauseAt(new Date(1000));
  await page.evaluate(async({main,bridge,kind})=>{const imp=s=>import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(s)))),m=await imp(main),b=await imp(bridge),id=n=>`80000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
   document.body.innerHTML='<article class="react-flow__node" data-id="Timeout Asset" style="width:1300px"><div id="asset"></div><div data-parameter-name="HMB_IMAGE_ASSET_THUMBNAIL_PATCH"><div id="carrier"></div></div></article>';
   const f={m,b,kind,id,requests:[],writes:[],userSelections:0,node:document.querySelector('article'),main:document.getElementById('asset'),carrier:document.getElementById('carrier'),closed:false};
   f.server=m.hmbNormalizeImageAssetState({schema:'hmb-image-asset-library-state',widget_runtime_lease:id(1),edit_transport_schema:'hmb-image-asset-edit-v1',
    projects:[{project_id:'One',name:'One',path:'P:/projects/One/Ai_Ct_image'},{project_id:'Two',name:'Two',path:'P:/projects/Two/Ai_Ct_image'}],
    shot_routing:{schema:'hmb-shot-routing',version:1,publisher_instance_uuid:id(2),channel_uuid:id(3),generation:1,active_shot_uuid:id(4),shots:[{shot_uuid:id(4),number:1,name:'Shot 1',revision:0,selected_source_uids:[]}]}});
   f.initial=structuredClone(f.server);
   f.mainProps=()=>({value:JSON.stringify(f.server),nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_STATE',ui_options:{widget:'HMBImageAssetLibraryWidget',library:'HMB_GP_Production'},disabled:false,
    onChange:wire=>{const sent=JSON.parse(wire);f.writes.push(sent);queueMicrotask(()=>{if(f.closed)return;f.mh.update({...f.mainProps(),value:wire});f.server=m.hmbNormalizeImageAssetState({...f.server,...(sent.schema==='hmb-image-asset-edit-v1'?sent.edits:sent),ui_edit_revision:sent.ui_edit_revision,scan_revision:(sent.scan_revision||0)+1,project_uid:'server-uid',image_bash_workspace_edit:{},scan_busy:false});f.mh.update(f.mainProps())})}});
   f.response=(request,server=f.server)=>({...request,phase:'result',widget_runtime_lease:server.widget_runtime_lease,canonical_node_name:f.node.dataset.id,canonical_scope:m.hmbImageAssetAuthorityScope(server),catalog_page_version:1});
   f.answer=(request,server=f.server)=>{if(!f.closed)f.bh.update(f.bridgeProps(f.response(request,server)))};
   f.bridgeProps=value=>({value,nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_THUMBNAIL_PATCH',disabled:false,onChange:request=>{
    if(request.operation!=='widget_authority')return;
    f.requests.push({...structuredClone(request),at:Date.now()});
    if(kind==='callback_throw')throw Error('read-only diagnostic callback throw');if(kind==='callback_reject')return Promise.reject(Error('read-only diagnostic callback rejection'));
    queueMicrotask(()=>{if(f.closed)return;f.bh.update(f.bridgeProps(request));f.mh.update(f.mainProps());if(f.requests.length>1&&['drop_first','single_selection_drop_first'].includes(kind))f.answer(request)});
   }});
   f.choose=path=>{f.userSelections++;const select=f.main.querySelector('[data-project-select]');select.value=path;select.dispatchEvent(new Event('change',{bubbles:true}))};
   f.close=()=>{if(f.closed)return;f.closed=true;f.mh.cleanup();f.bh.cleanup()};
   f.mh=m.default(f.main,f.mainProps());
   f.bh=b.default(f.carrier,f.bridgeProps({schema:'hmb-image-asset-thumbnail-bridge',version:1,phase:'idle',runtime_instance_id:f.server.shot_routing.publisher_instance_uuid,widget_runtime_lease:f.server.widget_runtime_lease,catalog_page_version:1}));
   f.stages={after_mount:f.requests.length};f.choose('P:/projects/One/Ai_Ct_image');f.stages.after_first_selection=f.requests.length;window.fixture=f;
  },{main,bridge,kind});
  await page.clock.runFor(200);
  await page.evaluate(()=>{if(fixture.kind!=='single_selection_drop_first')fixture.choose('P:/projects/Two/Ai_Ct_image');fixture.stages.after_second_selection=fixture.requests.length});
  if(kind==='scope_changed')await page.evaluate(()=>{fixture.node.dataset.id='Replaced Asset'});
  if(kind==='disposed')await page.evaluate(()=>fixture.close());
  if(kind==='lease_recreated')await page.evaluate(()=>{const f=fixture;f.server={...f.server,widget_runtime_lease:f.id(9)};f.mh.update(f.mainProps());f.bh.update(f.bridgeProps({schema:'hmb-image-asset-thumbnail-bridge',version:1,phase:'idle',runtime_instance_id:f.server.shot_routing.publisher_instance_uuid,widget_runtime_lease:f.server.widget_runtime_lease,catalog_page_version:1}))});
  if(kind==='late_after_deadline')await page.evaluate(()=>{const original=performance.now;Object.defineProperty(performance,'now',{configurable:true,value:()=>30000});fixture.answer(fixture.requests[0]);Object.defineProperty(performance,'now',{configurable:true,value:original})});
  await page.clock.fastForward(kind==='expired_timer'?11000:2800);await page.clock.runFor(150);
  if(kind==='late_first'){
   const before=await page.evaluate(()=>fixture.writes.length);await page.evaluate(()=>fixture.answer(fixture.requests[0],fixture.initial));await page.clock.runFor(100);
   const afterOld=await page.evaluate(()=>fixture.writes.length);if(!baseline){assert.equal(before,0);assert.equal(afterOld,0);await page.evaluate(()=>fixture.answer(fixture.requests[1]));await page.clock.runFor(150);await page.evaluate(()=>fixture.answer(fixture.requests[0],fixture.initial));await page.clock.runFor(100);}
  }
  if(kind==='lease_recreated'){
   await page.evaluate(()=>{const f=fixture;if(f.requests.length>1)f.answer(f.requests.at(-1))});await page.clock.runFor(150);await page.evaluate(()=>fixture.answer(fixture.requests[0],fixture.initial));await page.clock.runFor(100);
  }
  if(baseline)await page.clock.fastForward(8000);
  else if(kind==='no_event')await page.clock.fastForward(3000);
  if(['callback_throw','callback_reject'].includes(kind))await page.clock.fastForward(8000);
  const state=await page.evaluate(()=>{const f=fixture,entry=f.b.hmbImageAssetThumbnailPatchBridgeRegistry().get(f.server.shot_routing.publisher_instance_uuid);return{user_selections:f.userSelections,additional_user_selections:Math.max(0,f.userSelections-1),stages:{...f.stages,after_time_advance:f.requests.length},requests:f.requests.map(r=>({request_id:r.request_id,at:r.at})),writes:f.writes.length,target:f.writes.at(-1)?.project_root||'',message:f.main.querySelector('[data-transport-status]')?.textContent||'',lease:f.main.__hmbImageAssetWidgetLease||'',bridge_lease:entry?.forNode?.(f.node.dataset.id,f.node)?.widget_runtime_lease||'',server_lease:f.server.widget_runtime_lease}});
  if(!baseline){
   if(['drop_first','late_first'].includes(kind)){assert.equal(state.requests.length,2,kind);assert.equal(new Set(state.requests.map(r=>r.request_id)).size,2,kind);assert.equal(state.writes,1,kind);assert.equal(state.target,'P:/projects/Two/Ai_Ct_image',kind);}
   if(kind==='single_selection_drop_first'){assert.equal(state.user_selections,1);assert.equal(state.additional_user_selections,0);assert.equal(state.requests.length,2);assert.equal(state.writes,1);assert.equal(state.target,'P:/projects/One/Ai_Ct_image');}
   if(kind==='no_event'){assert.equal(state.requests.length,2);assert.equal(state.writes,0);assert(state.message);}
   if(['scope_changed','disposed'].includes(kind)){assert.equal(state.requests.length,1,kind);assert.equal(state.writes,0,kind);}
   if(kind==='callback_throw'){assert.deepEqual(state.stages,{after_mount:1,after_first_selection:2,after_second_selection:3,after_time_advance:3});assert.equal(state.writes,0);}
   if(kind==='callback_reject'){assert.deepEqual(state.stages,{after_mount:1,after_first_selection:1,after_second_selection:2,after_time_advance:2});assert.equal(state.writes,0);}
   if(kind==='lease_recreated'){assert.equal(state.writes,0);assert.equal(state.lease,state.server_lease);}
   if(kind==='lease_recreated')assert.equal(state.requests.length,2,'An old waiter cannot cancel the new lease read');
   if(kind==='expired_timer'){assert.equal(state.requests.length,1);assert.equal(state.writes,0);}
   if(kind==='late_after_deadline'){assert.equal(state.requests.length,1);assert.equal(state.writes,0);assert.equal(state.bridge_lease,'');assert.equal(state.lease,state.server_lease);assert(state.message);}
   assert.deepEqual(errors,[]);
  }
  state.errors=errors;proof.cases[kind]=state;await page.evaluate(()=>fixture.close());await context.close();
 }
 proof.status=baseline?'BASELINE_OBSERVED':'PASS';proof.main_sha256=crypto.createHash('sha256').update(main).digest('hex');proof.bridge_sha256=crypto.createHash('sha256').update(bridge).digest('hex');
}catch(error){proof.status='FAILED';proof.error=String(error).slice(0,3000);throw error}
finally{await browser.close();fs.writeFileSync(path.join(out,baseline?'AUTHORITY-TIMEOUT-BASELINE.json':'AUTHORITY-TIMEOUT-CANDIDATE.json'),JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof));}
