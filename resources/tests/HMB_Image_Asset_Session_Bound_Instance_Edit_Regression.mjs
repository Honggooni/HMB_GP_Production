// Real widgets' bound structural dispatch entry, synthetic native optimistic
// delivery and exact no-session error. Queue/UI sequencing is tested separately
// in HMB_Image_Asset_Queued_Instance_Edit_Regression.mjs; failure/rollback/read
// boundaries here deliberately dispatch without the click collector.
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import assert from 'node:assert/strict';import {fileURLToPath} from 'node:url';
import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),productRoot=process.env.HMB_SESSION_EDIT_WIDGET_ROOT||root;
const out=path.resolve(process.env.HMB_SESSION_EDIT_REPORT_DIR||path.join(root,'reports/regression-checks/HMB_Image_Asset_Session_Bound_Instance_Edit_Regression'));fs.mkdirSync(out,{recursive:true});
const main=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetLibraryWidget.js'),'utf8'),bridge=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetThumbnailPatchBridgeWidget.js'),'utf8');
const baseline=process.argv.includes('--baseline'),browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});
const result={status:'RUNNING',baseline,scope:'Isolated widgets; controlled optimistic Set echo and no-session failures. No actual Desktop/session or SDK requests.',cases:{},external_requests:0};
try{
 for(const kind of ['throw_compact','throw_full','promise_compact','promise_full','void_compact','void_full','late_ack_compact','late_ack_full','void_reparent_compact','void_move_before_timeout_compact','void_recreated_compact','void_read_reject_compact','void_read_timeout_compact']){
  const page=await browser.newPage({viewport:{width:1400,height:950}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/*',r=>{if(r.request().url()==='http://127.0.0.1/session-edit')return r.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'});result.external_requests++;return r.abort()});
  await page.clock.install({time:new Date(0)});await page.goto('http://127.0.0.1/session-edit');await page.clock.pauseAt(new Date(1000));
  await page.evaluate(async({main,bridge,kind})=>{const imp=s=>import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(s)))),m=await imp(main),b=await imp(bridge),id=n=>`a0000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
   document.body.innerHTML='<article class="react-flow__node" data-id="Session Asset" style="width:1300px"><div id="asset"></div><div data-parameter-name="HMB_IMAGE_ASSET_THUMBNAIL_PATCH"><div id="carrier"></div></div></article>';
   const f={m,b,id,kind,node:document.querySelector('article'),main:document.getElementById('asset'),carrier:document.getElementById('carrier'),calls:[],requests:[],accepted:[],errors:[],bound:kind.startsWith('late_ack'),closed:false};
   f.noSession="Refusing to send SetParameterValueRequest without a session: no topicOptions provided and apiClient has no sessionId. Pass topicOptions explicitly if a broadcast is intended, or wait for the session to bind before issuing the request.";
   f.server=m.hmbNormalizeImageAssetState({schema:'hmb-image-asset-library-state',widget_runtime_lease:id(1),...(kind.endsWith('compact')?{edit_transport_schema:'hmb-image-asset-edit-v1'}:{}),ui_edit_revision:4,scan_revision:1,
    shot_routing:{schema:'hmb-shot-routing',version:1,publisher_instance_uuid:id(2),channel_uuid:id(3),generation:1,active_shot_uuid:id(4),shots:[{shot_uuid:id(4),number:1,name:'Shot 1',revision:0,selected_source_uids:[]}]},
    image_bash_workspace:{workspace_id:id(5),revision:2,instances:[{instance_id:id(6),source_uid:'project:a'},{instance_id:id(7),source_uid:'project:b'}]},image_bash_active:true});f.original=structuredClone(f.server);
   f.props=value=>({value:value??JSON.stringify(f.server),nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_STATE',ui_options:{widget:'HMBImageAssetLibraryWidget',library:'HMB_GP_Production'},disabled:false,onChange:wire=>{
    const sent=JSON.parse(wire);f.calls.push(sent);queueMicrotask(()=>{if(!f.closed)f.mh.update(f.props(wire))});
    if(!f.bound){if(kind.startsWith('throw'))throw Error(f.noSession);if(kind.startsWith('promise'))return Promise.reject(Error(f.noSession));return;}
    const edits=sent.edits||sent,intent=edits.image_bash_workspace_edit,workspace=structuredClone(f.server.image_bash_workspace);
    if(intent.expected_revision!==workspace.revision)throw Error('fixture backend stale expected revision');
    if(intent.operation==='copy'){const i=workspace.instances.findIndex(x=>x.instance_id===intent.instance_id);workspace.instances.splice(i+1,0,{...workspace.instances[i],instance_id:intent.new_instance_id});}
    else if(intent.operation==='remove')workspace.instances=workspace.instances.filter(x=>x.instance_id!==intent.instance_id);else throw Error('unexpected operation');workspace.revision++;
    f.server=m.hmbNormalizeImageAssetState({...f.server,...edits,image_bash_workspace:workspace,ui_edit_revision:sent.ui_edit_revision,scan_revision:f.server.scan_revision+1,image_bash_workspace_edit:{},image_bash_workspace_request:{}});f.accepted.push(structuredClone(f.server));if(!kind.startsWith('late_ack'))queueMicrotask(()=>{if(!f.closed)f.mh.update(f.props())});
   }});
   f.bridgeProps=value=>({value,nodeName:f.node.dataset.id,parameterName:'HMB_IMAGE_ASSET_THUMBNAIL_PATCH',disabled:false,onChange:request=>{if(request.operation==='widget_authority'){f.requests.push(structuredClone(request));if(f.readReject)throw Error(f.noSession)}}});
   f.answer=()=>{const request=f.requests.at(-1);f.mh.update(f.props());f.bh.update(f.bridgeProps({...request,phase:'result',widget_runtime_lease:f.server.widget_runtime_lease,canonical_node_name:f.node.dataset.id,canonical_scope:m.hmbImageAssetAuthorityScope(f.server),catalog_page_version:1}))};
   f.copy=()=>f.main.__hmbImageAssetBashQueueExecute({mutate:candidate=>m.hmbDuplicateImageBashInstance(candidate,id(6)),hint:{operation:'copy',instance_id:id(6)}},null);
   f.remove=()=>f.main.__hmbImageAssetBashQueueExecute({mutate:candidate=>m.hmbRemoveImageBashInstance(candidate,id(7))},null);
   f.summary=()=>{const s=f.main.__hmbImageAssetLatestState;return{rows:s.image_bash_workspace.instances,revision:s.image_bash_workspace.revision,ui:s.ui_edit_revision,localWatermark:f.main.__hmbImageAssetLatestLocalUiEditRevision??null,uiWatermark:f.main.__hmbImageAssetCurrentUiEditRevision,scanWatermark:f.main.__hmbImageAssetCurrentScanRevision,pending:f.main.__hmbImageAssetPendingPublications?.size||0,message:f.main.querySelector('[data-transport-status]')?.textContent||'',calls:f.calls.length,accepted:f.accepted.length,requests:f.requests.length,retainedCommandReceipts:f.main.__hmbImageAssetWorkspaceCommandEchoes?.size||0,hold:!!f.main.__hmbImageAssetWorkspaceAuthorityUnknown,holdRead:!!f.main.__hmbImageAssetWorkspaceAuthorityUnknown?.read,lease:s.widget_runtime_lease}};
   f.mh=m.default(f.main,f.props());f.bh=b.default(f.carrier,f.bridgeProps({schema:'hmb-image-asset-thumbnail-bridge',version:1,phase:'idle',runtime_instance_id:f.server.shot_routing.publisher_instance_uuid,widget_runtime_lease:f.server.widget_runtime_lease,catalog_page_version:1}));f.answer();f.close=()=>{f.closed=true;f.mh.cleanup();f.bh.cleanup()};window.fixture=f;
  },{main,bridge,kind});await page.clock.runFor(30);
  await page.evaluate(()=>fixture.copy());await page.clock.runFor(50);const single=await page.evaluate(()=>fixture.summary());
  await page.evaluate(()=>{const f=fixture;if(f.kind.startsWith('throw'))for(let i=0;i<(f.kind==='throw_full'?35:3);i++){f.copy();f.remove()}else f.remove()});await page.clock.runFor(50);const repeat=await page.evaluate(()=>fixture.summary());
  if(kind==='void_move_before_timeout_compact')await page.evaluate(()=>{const f=fixture,parent=document.createElement('section');document.body.append(parent);parent.append(f.node)});
  await page.clock.fastForward(10100);const timeout=await page.evaluate(()=>fixture.summary());
  let afterEvictedEcho=null;if(kind==='throw_full'){await page.evaluate(()=>fixture.mh.update(fixture.props(JSON.stringify(fixture.calls[0]))));await page.clock.runFor(50);afterEvictedEcho=await page.evaluate(()=>fixture.summary());}
  let unsafeRetry=null;
  if(kind.startsWith('void')){await page.evaluate(()=>{fixture.bound=true;if(fixture.kind==='void_read_reject_compact')fixture.readReject=true;fixture.copy()});await page.clock.runFor(50);unsafeRetry=await page.evaluate(()=>fixture.summary());}
  let ownerBoundary=null;
  if(kind==='void_reparent_compact'){
   await page.evaluate(()=>{const f=fixture;f.oldParent=f.node.parentNode;const parent=document.createElement('section');document.body.append(parent);parent.append(f.node);f.answer()});await page.clock.runFor(50);ownerBoundary=await page.evaluate(()=>fixture.summary());
  }
  if(kind==='void_recreated_compact'){
   await page.evaluate(()=>{const f=fixture;f.oldRequest=f.requests.at(-1);f.oldServer=structuredClone(f.server);f.server={...f.original,widget_runtime_lease:f.id(20)};f.mh.update(f.props());f.bh.update(f.bridgeProps({schema:'hmb-image-asset-thumbnail-bridge',version:1,phase:'idle',runtime_instance_id:f.server.shot_routing.publisher_instance_uuid,widget_runtime_lease:f.server.widget_runtime_lease,catalog_page_version:1}));f.answer()});await page.clock.runFor(50);
   await page.evaluate(()=>{const f=fixture;f.bh.update(f.bridgeProps({...f.oldRequest,phase:'result',widget_runtime_lease:f.oldServer.widget_runtime_lease,canonical_node_name:f.node.dataset.id,canonical_scope:f.m.hmbImageAssetAuthorityScope(f.oldServer)}))});await page.clock.runFor(50);ownerBoundary=await page.evaluate(()=>fixture.summary());
  }
  if(kind==='void_read_timeout_compact'){await page.clock.fastForward(6500);ownerBoundary=await page.evaluate(()=>fixture.summary());}
  if(kind==='void_read_reject_compact'){ownerBoundary=await page.evaluate(()=>fixture.summary());await page.evaluate(()=>{fixture.readReject=false})}
  if(kind.startsWith('late_ack')){await page.evaluate(()=>fixture.mh.update(fixture.props()));await page.clock.runFor(50);ownerBoundary=await page.evaluate(()=>fixture.summary());}
  // A fresh read is explicit fixture recovery, not assumed session rebinding.
  const movedOwner=['void_reparent_compact','void_move_before_timeout_compact'].includes(kind);
  if(!movedOwner){await page.evaluate(()=>{const f=fixture;f.bound=true;f.mh.update(f.props());if(f.main.__hmbImageAssetWorkspaceAuthorityUnknown){if(!f.main.__hmbImageAssetWorkspaceAuthorityUnknown.read)f.copy()}else f.read=f.m.hmbWaitForImageAssetAuthority(f.main,f.main.__hmbImageAssetLatestState,{fresh:true}).catch(e=>{f.errors.push(e.message)});f.answer()});await page.clock.runFor(50);}
  const recovered=await page.evaluate(()=>fixture.summary());
  if(!movedOwner){await page.evaluate(()=>fixture.copy());await page.clock.runFor(50);if(kind.startsWith('late_ack')){await page.evaluate(()=>fixture.mh.update(fixture.props()));await page.clock.runFor(30)}}
  const retried=await page.evaluate(()=>fixture.summary());
  if(!movedOwner){await page.evaluate(()=>{const f=fixture;f.mh.update(f.props(JSON.stringify(f.calls[0])))});await page.clock.runFor(50)}const afterLateEcho=await page.evaluate(()=>fixture.summary());
  result.cases[kind]={single,repeat,timeout,afterEvictedEcho,unsafeRetry,ownerBoundary,recovered,retried,afterLateEcho,server:await page.evaluate(()=>fixture.server.image_bash_workspace),errors,fixtureErrors:await page.evaluate(()=>fixture.errors)};
  if(!baseline){const failedCalls=kind==='throw_full'?71:kind.startsWith('throw')?7:2;if(!kind.startsWith('late_ack')){assert.equal(single.accepted,0);assert.equal(timeout.accepted,0)}assert.equal(timeout.calls,failedCalls);assert.deepEqual(errors,[]);
   if(!movedOwner){if(!kind.startsWith('late_ack'))assert.deepEqual(recovered.rows,await page.evaluate(()=>fixture.original.image_bash_workspace.instances));assert.equal(retried.accepted,kind.startsWith('late_ack')?3:1);assert.equal(retried.rows.length,3);assert.deepEqual(afterLateEcho.rows,retried.rows);assert.equal(recovered.hold,false)}
   if(kind.startsWith('throw')||kind.startsWith('promise')){const original=await page.evaluate(()=>fixture.original.image_bash_workspace.instances);for(const point of [single,repeat,timeout]){assert.deepEqual(point.rows,original,kind);assert.equal(point.revision,2,kind);assert.equal(point.uiWatermark,4,kind);assert.equal(point.localWatermark,null,kind);assert.equal(point.pending,0,kind);assert.match(point.message,/without a session/,kind)}}
   if(kind==='throw_full'){assert.deepEqual(afterEvictedEcho.rows,await page.evaluate(()=>fixture.original.image_bash_workspace.instances));assert.equal(afterEvictedEcho.uiWatermark,4);assert.match(afterEvictedEcho.message,/without a session/)}
   if(kind.startsWith('void')){assert.equal(timeout.hold,true);assert.equal(unsafeRetry.calls,2,'unknown edit sends no semantic command');assert.deepEqual(unsafeRetry.rows,timeout.rows,'unknown is not failed rollback');}
   if(kind==='void_reparent_compact'){assert.equal(ownerBoundary.hold,true);assert.deepEqual(ownerBoundary.rows,timeout.rows);assert.equal(ownerBoundary.calls,2);}
   if(kind==='void_move_before_timeout_compact'){assert.equal(unsafeRetry.hold,true);assert.equal(unsafeRetry.requests,1);assert.match(unsafeRetry.message,/연결이 변경/);assert.deepEqual(recovered.rows,timeout.rows);}
   if(kind==='void_recreated_compact'){assert.equal(ownerBoundary.lease,'a0000000-0000-4000-8000-000000000020');assert.equal(ownerBoundary.hold,false);assert.equal(ownerBoundary.calls,2);assert.equal(ownerBoundary.accepted,0)}
   if(kind==='void_read_reject_compact'){assert.equal(ownerBoundary.hold,true);assert.match(ownerBoundary.message,/without a session/)}
   if(kind==='void_read_timeout_compact'){assert.equal(ownerBoundary.hold,true);assert(ownerBoundary.message);assert.equal(ownerBoundary.requests,3)}
   if(kind.startsWith('late_ack')){assert.equal(timeout.hold,true);assert.equal(ownerBoundary.hold,false);assert.equal(ownerBoundary.calls,2);assert.equal(ownerBoundary.accepted,2)}
  }
  await page.evaluate(()=>fixture.close());await page.close();
 }
 result.status=baseline?'BASELINE_OBSERVED':'PASS';
}catch(error){result.status='FAILED';result.error=String(error).slice(0,2500);throw error}
finally{await browser.close();result.main_sha256=crypto.createHash('sha256').update(main).digest('hex');result.bridge_sha256=crypto.createHash('sha256').update(bridge).digest('hex');fs.writeFileSync(path.join(out,baseline?'SESSION-EDIT-BASELINE.json':'SESSION-EDIT-CANDIDATE.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));}
