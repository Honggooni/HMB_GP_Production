// Real widget direct-dispatch seam; isolated native void/optimistic/canonical stream.
// UI click collection and canonical-ACK serialization are independently covered
// by HMB_Image_Asset_Queued_Instance_Edit_Regression.mjs. These adversarial
// overlapping publication/read races intentionally exercise the actual bound
// dispatcher below that queue, without editing or replacing product functions.
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import assert from 'node:assert/strict';import {fileURLToPath} from 'node:url';
import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),productRoot=process.env.HMB_INSTANCE_EDIT_WIDGET_ROOT||root;
const out=path.resolve(process.env.HMB_INSTANCE_EDIT_REPORT_DIR||path.join(root,'reports/regression-checks/HMB_Image_Asset_Instance_Edit_Supersession_Regression'));fs.mkdirSync(out,{recursive:true});
const main=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetLibraryWidget.js'),'utf8'),bridge=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetThumbnailPatchBridgeWidget.js'),'utf8');
const baseline=process.argv.includes('--baseline'),browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});
const result={status:'RUNNING',baseline,scope:'Isolated real widget modules with native void callbacks and delayed/out-of-order canonical acknowledgements. No Desktop/SDK/server calls; virtual time is not production latency.',cases:{},external_requests:0,actual_Desktop:false,SDK_requests:0,paid_requests:0};
try{
 for(const kind of ['confirmed_pending_read','rapid_pending_read','resolved_read_gap','shared_wait_after_edit','new_read_owner','external_canonical_change','foreign_owner','same_text_plain_error','same_code_plain_error','read_timeout','callback_reject']){
  const context=await browser.newContext({viewport:{width:1450,height:950}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/*',r=>{if(r.request().url()==='http://127.0.0.1/instance-edit')return r.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'});result.external_requests++;return r.abort()});
  await page.clock.install({time:new Date(0)});await page.goto('http://127.0.0.1/instance-edit');await page.clock.pauseAt(new Date(1000));
  await page.evaluate(async({main,bridge,kind})=>{const imp=s=>import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(s)))),m=await imp(main),b=await imp(bridge),id=n=>`90000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
   document.body.innerHTML='<article class="react-flow__node" data-id="Instance Asset" style="width:1300px"><div id="asset"></div><div data-parameter-name="HMB_IMAGE_ASSET_THUMBNAIL_PATCH"><div id="carrier"></div></div></article>';
   const f={m,b,id,kind,node:document.querySelector('article'),main:document.getElementById('asset'),carrier:document.getElementById('carrier'),writes:[],requests:[],acks:[],badIntents:[],closed:false};
   f.server=m.hmbNormalizeImageAssetState({schema:'hmb-image-asset-library-state',widget_runtime_lease:id(1),edit_transport_schema:'hmb-image-asset-edit-v1',scan_revision:1,ui_edit_revision:4,
    shot_routing:{schema:'hmb-shot-routing',version:1,publisher_instance_uuid:id(2),channel_uuid:id(3),generation:1,active_shot_uuid:id(4),shots:[{shot_uuid:id(4),number:1,name:'Shot 1',revision:0,selected_source_uids:[]}]},
    image_bash_workspace:{workspace_id:id(5),revision:2,instances:[{instance_id:id(6),source_uid:'project:a'},{instance_id:id(7),source_uid:'project:b'}]},image_bash_active:true});
   f.initial=structuredClone(f.server);f.originalIds=f.server.image_bash_workspace.instances.map(x=>x.instance_id);
   f.props=value=>({value:value===undefined?JSON.stringify(f.server):value,nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_STATE',ui_options:{widget:'HMBImageAssetLibraryWidget',library:'HMB_GP_Production'},disabled:false,onChange:wire=>{
    const sent=JSON.parse(wire),edits=sent.edits||sent,intent=edits.image_bash_workspace_edit;f.writes.push(sent);
    const workspace=structuredClone(f.server.image_bash_workspace);
    if(!intent?.operation_id||intent.expected_revision!==workspace.revision||intent.workspace_id!==workspace.workspace_id)f.badIntents.push({operation:intent?.operation,expected:intent?.expected_revision,actual:workspace.revision});
    else if(intent.operation==='copy'){const index=workspace.instances.findIndex(x=>x.instance_id===intent.instance_id);if(index<0)throw Error('Invalid source instance');workspace.instances.splice(index+1,0,{...workspace.instances[index],instance_id:intent.new_instance_id});workspace.revision++;}
    else if(intent.operation==='remove'){const index=workspace.instances.findIndex(x=>x.instance_id===intent.instance_id);if(index<0)throw Error('Invalid removed instance');workspace.instances.splice(index,1);workspace.revision++;}
    else throw Error('Unexpected semantic operation in fixture');
    f.server=m.hmbNormalizeImageAssetState({...f.server,...edits,ui_edit_revision:sent.ui_edit_revision,scan_revision:f.server.scan_revision+1,image_bash_workspace:workspace,image_bash_workspace_edit:{},image_bash_workspace_request:{}});
    f.acks.push(structuredClone(f.server));queueMicrotask(()=>{if(!f.closed)f.mh.update(f.props(wire))});
   }});
   f.bridgeProps=value=>({value,nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_THUMBNAIL_PATCH',disabled:false,onChange:request=>{if(request.operation!=='widget_authority')return;f.requests.push(structuredClone(request));if(f.rejectRead){const error=Error(f.rejectRead);if(f.rejectCode)error.code=f.rejectCode;return Promise.reject(error);}}});
   f.answer=(request=f.requests.at(-1),server=f.server)=>{f.bh.update(f.bridgeProps({...request,phase:'result',widget_runtime_lease:server.widget_runtime_lease,canonical_node_name:f.node.dataset.id,canonical_scope:m.hmbImageAssetAuthorityScope(server),catalog_page_version:1}))};
   f.canonical=state=>f.mh.update(f.props(JSON.stringify(state)));
   f.copy=instance=>f.main.__hmbImageAssetBashQueueExecute({mutate:candidate=>m.hmbDuplicateImageBashInstance(candidate,instance),hint:{operation:'copy',instance_id:instance}},null);
   f.remove=instance=>f.main.__hmbImageAssetBashQueueExecute({mutate:candidate=>m.hmbRemoveImageBashInstance(candidate,instance)},null);
   f.rows=()=>f.main.__hmbImageAssetLatestState.image_bash_workspace.instances;
   f.close=()=>{if(f.closed)return;f.closed=true;f.mh.cleanup();f.bh.cleanup()};
   f.mh=m.default(f.main,f.props());f.bh=b.default(f.carrier,f.bridgeProps({schema:'hmb-image-asset-thumbnail-bridge',version:1,phase:'idle',runtime_instance_id:f.server.shot_routing.publisher_instance_uuid,widget_runtime_lease:f.server.widget_runtime_lease,catalog_page_version:1}));f.answer();window.fixture=f;
  },{main,bridge,kind});await page.clock.runFor(40);
  if(kind==='confirmed_pending_read'){
   await page.evaluate(()=>{const f=fixture;f.copy(f.originalIds[0])});await page.clock.runFor(30);await page.evaluate(()=>fixture.canonical(fixture.acks[0]));await page.clock.runFor(30);
   await page.evaluate(()=>fixture.copy(fixture.originalIds[0]));await page.clock.runFor(30);await page.evaluate(()=>fixture.canonical(fixture.acks[1]));await page.clock.runFor(30);
  }else{
   await page.evaluate(()=>{const f=fixture;f.copy(f.originalIds[0]);f.copy(f.originalIds[0]);const copy=f.rows().find(x=>!f.originalIds.includes(x.instance_id));f.remove(copy.instance_id)});await page.clock.runFor(30);
   await page.evaluate(()=>fixture.canonical(fixture.acks.at(-1)));await page.clock.runFor(30);
  }
  await page.evaluate(()=>{const f=fixture;if(['same_text_plain_error','same_code_plain_error'].includes(f.kind))f.rejectRead='작업이 변경되었습니다. 최신 상태에서 다시 확인하세요.';if(f.kind==='same_code_plain_error')f.rejectCode='HMB_IMAGE_ASSET_AUTHORITY_LOCAL_SUPERSEDED';if(f.kind==='callback_reject')f.rejectRead='explicit diagnostic read rejection';f.canonical(f.acks[0])});await page.clock.runFor(30);
  const readStart=await page.evaluate(()=>({requests:fixture.requests.length,pending:!!fixture.main.__hmbImageAssetAuthorityWait,publications:fixture.main.__hmbImageAssetPendingPublications?.size||0}));
  if(['confirmed_pending_read','rapid_pending_read'].includes(kind))await page.evaluate(()=>{const f=fixture;f.retiredRequest=f.requests.at(-1);f.copy(f.originalIds[0])});
  if(kind==='resolved_read_gap')await page.evaluate(()=>{const f=fixture;f.retiredRequest=f.requests.at(-1);f.answer();f.copy(f.originalIds[0])});
  if(kind==='shared_wait_after_edit')await page.evaluate(()=>{const f=fixture;f.retiredRequest=f.requests.at(-1);f.copy(f.originalIds[0]);f.canonical(f.acks[0])});
  if(kind==='new_read_owner')await page.evaluate(()=>{const f=fixture;f.retiredRequest=f.requests.at(-1);f.copy(f.originalIds[0]);const entry=f.b.hmbImageAssetThumbnailPatchBridgeRegistry().get(f.server.shot_routing.publisher_instance_uuid).forNode(f.node.dataset.id,f.node);f.newReadResult='pending';entry.queryWidgetLease().then(()=>{f.newReadResult='resolved'},error=>{f.newReadResult=error.message});f.newRequest=f.requests.at(-1)});
  if(kind==='external_canonical_change')await page.evaluate(()=>{const f=fixture;f.retiredRequest=f.requests.at(-1);f.server={...f.server,ui_edit_revision:f.server.ui_edit_revision+50,image_bash_workspace:{...f.server.image_bash_workspace,revision:f.server.image_bash_workspace.revision+1,instances:[...f.server.image_bash_workspace.instances,{instance_id:f.id(99),source_uid:'project:external'}]}};f.canonical(f.server);f.answer(f.retiredRequest,f.acks[0])});
  if(kind==='foreign_owner')await page.evaluate(()=>{const f=fixture;f.node.dataset.id='Another Asset';f.answer()});
  await page.clock.runFor(60);
  const beforeAck=await page.evaluate(()=>({message:fixture.main.querySelector('[data-transport-status]')?.textContent||'',rows:fixture.rows().length,pending:!!fixture.main.__hmbImageAssetAuthorityWait}));
  if(['confirmed_pending_read','rapid_pending_read','resolved_read_gap','shared_wait_after_edit'].includes(kind)){
   await page.evaluate(()=>fixture.canonical(fixture.acks.at(-1)));await page.clock.runFor(30);
   await page.evaluate(()=>{const f=fixture;f.answer(f.retiredRequest,f.acks[0]);const copy=f.rows().find(x=>!f.originalIds.includes(x.instance_id));f.remove(copy.instance_id)});await page.clock.runFor(30);await page.evaluate(()=>fixture.canonical(fixture.acks.at(-1)));await page.clock.runFor(30);
  }
  if(kind==='new_read_owner'){
   await page.evaluate(()=>{const f=fixture;f.canonical(f.acks.at(-1));f.answer(f.retiredRequest,f.acks[0])});await page.clock.runFor(30);
   await page.evaluate(()=>{fixture.newReadAfterRetired=fixture.newReadResult;fixture.answer(fixture.newRequest)});await page.clock.runFor(30);
  }
  if(['confirmed_pending_read','rapid_pending_read'].includes(kind)){
   for(let cycle=0;cycle<8;cycle++){
    await page.evaluate(()=>{const f=fixture;f.cycleStart=structuredClone(f.server);f.cycleStartRows=f.rows().map(x=>x.instance_id);f.copy(f.originalIds[0]);if(f.kind==='rapid_pending_read')f.copy(f.originalIds[0])});await page.clock.runFor(20);
    if(kind==='confirmed_pending_read'){await page.evaluate(()=>fixture.canonical(fixture.acks.at(-1)));await page.clock.runFor(20)}
    else{await page.evaluate(()=>{const f=fixture;f.remove(f.rows().find(x=>!f.cycleStartRows.includes(x.instance_id)).instance_id)});await page.clock.runFor(20);await page.evaluate(()=>fixture.canonical(fixture.acks.at(-1)));await page.clock.runFor(20)}
    await page.evaluate(()=>fixture.canonical(fixture.cycleStart));await page.clock.runFor(20);
    await page.evaluate(()=>{const f=fixture;f.retiredCycleRequest=f.requests.at(-1);f.remove(f.rows().find(x=>!f.cycleStartRows.includes(x.instance_id)).instance_id)});await page.clock.runFor(20);
    await page.evaluate(()=>{const f=fixture;(f.cycleWarnings??=[]).push(f.main.querySelector('[data-transport-status]')?.textContent||'');f.canonical(f.acks.at(-1))});await page.clock.runFor(20);
    await page.evaluate(()=>fixture.answer(fixture.retiredCycleRequest,fixture.cycleStart));await page.clock.runFor(20);
   }
  }
  if(['read_timeout','foreign_owner'].includes(kind))await page.clock.fastForward(10050);
  const state=await page.evaluate(()=>{const f=fixture,live=f.main.__hmbImageAssetLatestState;return{message:f.main.querySelector('[data-transport-status]')?.textContent||'',rows:f.rows().map(x=>({...x})),serverRows:f.server.image_bash_workspace.instances,writes:f.writes.map(w=>({ui:w.ui_edit_revision,intent:w.edits?.image_bash_workspace_edit||w.image_bash_workspace_edit})),requests:f.requests.map(x=>x.request_id),badIntents:f.badIntents,pending:!!f.main.__hmbImageAssetAuthorityWait,pendingPublications:f.main.__hmbImageAssetPendingPublications?.size||0,semanticGeneration:f.main.__hmbImageAssetSemanticGeneration,canonicalGeneration:f.main.__hmbImageAssetCanonicalGeneration,originalIds:f.originalIds,ui:live.ui_edit_revision,workspaceRevision:live.image_bash_workspace.revision,cycleWarnings:f.cycleWarnings||[],newReadResult:f.newReadResult||'',newReadAfterRetired:f.newReadAfterRetired||''}});
  state.readStart=readStart;state.beforeAck=beforeAck;state.errors=errors;result.cases[kind]=state;
  assert.deepEqual(state.badIntents,[],kind);assert.deepEqual(errors,[],kind);assert(readStart.requests>=2,kind+' read really started');
  if(!baseline){
   if(['confirmed_pending_read','rapid_pending_read','resolved_read_gap','shared_wait_after_edit','new_read_owner'].includes(kind)){assert.equal(beforeAck.message,'',kind+' normal supersession must not warn');assert.equal(state.message,'',kind);assert.deepEqual(state.rows,state.serverRows,kind);assert.equal(state.pendingPublications,0,kind);assert.equal(state.pending,false,kind);const extra=state.cycleWarnings.length+(kind==='new_read_owner'?1:0);assert.equal(state.requests.length,readStart.requests+extra,kind+' bounded reads, no semantic retry');for(const id of state.originalIds)assert(state.rows.some(x=>x.instance_id===id),kind);assert.equal(new Set(state.writes.map(w=>w.intent.operation_id)).size,state.writes.length,kind);assert.equal(state.workspaceRevision,2+state.writes.length,kind);assert(state.cycleWarnings.every(x=>x===''),kind+' repeated edits must not warn');if(kind==='new_read_owner'){assert.equal(state.newReadAfterRetired,'pending');assert.equal(state.newReadResult,'resolved');}}
   else assert(state.message,kind+' real failure still warns');
   if(['same_text_plain_error','same_code_plain_error'].includes(kind))assert.match(state.message,/작업이 변경/);
   if(kind==='external_canonical_change'){assert(state.rows.some(x=>x.source_uid==='project:external'));assert.equal(state.writes.length,3);}
  }
  await page.evaluate(()=>fixture.close());await context.close();
 }
 result.status=baseline?'BASELINE_OBSERVED':'PASS';
}catch(error){result.status='FAILED';result.error=String(error).slice(0,2500);throw error}
finally{await browser.close();result.main_sha256=crypto.createHash('sha256').update(main).digest('hex');result.bridge_sha256=crypto.createHash('sha256').update(bridge).digest('hex');fs.writeFileSync(path.join(out,baseline?'INSTANCE-EDIT-BASELINE.json':'INSTANCE-EDIT-CANDIDATE.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));}
