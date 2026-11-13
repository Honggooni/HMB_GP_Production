// Isolated Chromium widget DOM only: no Desktop, SDK, providers or network.
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const productRoot=path.resolve(process.env.HMB_IMAGE_ASSET_WIDGET_ROOT||root);
const out=path.resolve(process.env.HMB_RUNTIME_LEASE_REPORT_DIR||path.join(root,'reports/regression-checks/HMB_Image_Asset_Runtime_Lease_Regression'));fs.mkdirSync(out,{recursive:true});
const main=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetLibraryWidget.js'),'utf8');
const bridge=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetThumbnailPatchBridgeWidget.js'),'utf8');
const browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});
let proof={};
try{
 const context=await browser.newContext({viewport:{width:1500,height:1000},serviceWorkers:'block'}),page=await context.newPage();
 const blocked=[],errors=[];await context.route('**/*',route=>{blocked.push(route.request().url().split('?')[0]);return route.abort()});
 page.on('pageerror',error=>errors.push(String(error)));
 await page.setContent('<!doctype html><html><body><div class="react-flow__node" data-id="AssetLive"><div id="main"></div><div id="bridge"></div></div><div class="react-flow__node" data-id="OtherAsset"><div id="other"></div></div></body></html>');
 await page.evaluate(async({main,bridge})=>{
  const load=source=>import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
  const m=await load(main),b=await load(bridge);const id=i=>`40000000-0000-4000-8000-${String(i).padStart(12,'0')}`;
  const old=m.hmbNormalizeImageAssetState({schema:'hmb-image-asset-library-state',scan_revision:1,ui_edit_revision:5,widget_runtime_lease:id(8),
   shot_routing:{schema:'hmb-shot-routing',version:1,publisher_instance_uuid:id(1),channel_uuid:id(2),generation:1,active_shot_uuid:id(3),
    shots:[{shot_uuid:id(3),number:1,name:'Shot 1',revision:0,selected_source_uids:[]}]},
   image_bash_workspace:{workspace_id:id(4),revision:3,instances:[{instance_id:id(5),source_uid:'project:a'},{instance_id:id(6),source_uid:'project:b'},{instance_id:id(7),source_uid:'project:b'}]},image_bash_active:true});
  const fresh=structuredClone(old);fresh.ui_edit_revision=4;fresh.widget_runtime_lease=id(9);fresh.image_bash_workspace.revision=2;fresh.image_bash_workspace.instances.pop();
  const node=document.getElementById('main'),bridgeNode=document.getElementById('bridge');const sent=[],requests=[];let handle;
  const projection=(lease,phase='idle',request_id='')=>({schema:'hmb-image-asset-thumbnail-bridge',version:1,operation:phase==='result'?'widget_authority':'idle',phase,
   runtime_instance_id:id(1),widget_runtime_lease:lease,request_id,catalog_page_version:1,
   ...(phase==='result'?{canonical_node_name:'AssetLive',canonical_scope:m.hmbImageAssetAuthorityScope(lease===old.widget_runtime_lease?old:{...fresh,widget_runtime_lease:lease})}:{})});
  const bridgeProps=value=>({value,onChange:request=>{requests.push(structuredClone(request));return Promise.resolve({})}});
  handle=b.default(bridgeNode,bridgeProps(projection(old.widget_runtime_lease)));
  const ack=(lease,requestId=null)=>{const request=requestId||requests.filter(r=>r.operation==='widget_authority').at(-1)?.request_id;
   if(!request)throw Error('No read-only authority request');handle.update(bridgeProps(projection(lease,'result',request)));};
  ack(old.widget_runtime_lease);
  const props=value=>({value:JSON.stringify(value),onChange:wire=>{sent.push(typeof wire==='string'?JSON.parse(wire):structuredClone(wire));return Promise.resolve({})}});
  const mainHandle=m.default(node,props(old));
  window.leaseFixture={m,b,id,old,fresh,node,sent,requests,handle,ack,projection,bridgeProps,mainHandle,props};
 },{main,bridge});
 await page.waitForFunction(()=>document.getElementById('main').__hmbImageAssetLatestState?.image_bash_workspace?.instances?.length===3);
 const correlated=await page.evaluate(()=>{const f=window.leaseFixture;f.staleTimerFired=0;f.node.__hmbImageAssetSearchDraft='stale search';f.node.__hmbImageAssetSearchTimer=setTimeout(()=>f.staleTimerFired++,5);
  f.mainHandle.update(f.props(f.fresh));f.ack(f.fresh.widget_runtime_lease,'retired-query');
  return {held:!!f.node.__hmbImageAssetLeaseTransitionPending,count:f.node.__hmbImageAssetLatestState.image_bash_workspace.instances.length}});
 assert(correlated.held&&correlated.count===3,'An unrelated authority result cannot reset the UI owner');
 const pending=await page.evaluate(()=>{const f=window.leaseFixture;f.mainHandle.update(f.props(f.fresh));
  const count=f.sent.length;f.m.hmbPublishImageAssetState(f.node,f.props(f.old),f.node.__hmbImageAssetLatestState,()=>{});
  return{held:!!f.node.__hmbImageAssetLeaseTransitionPending,count:f.node.__hmbImageAssetLatestState.image_bash_workspace.instances.length,old_emit_blocked:f.sent.length===count,
   request:f.requests.filter(r=>r.operation==='widget_authority').at(-1)}});
 assert(pending.held&&pending.old_emit_blocked&&pending.count===3);assert(pending.request);
 await page.evaluate(()=>{const f=window.leaseFixture;f.ack(f.fresh.widget_runtime_lease)});
 await page.waitForFunction(()=>document.getElementById('main').__hmbImageAssetLatestState?.image_bash_workspace?.instances?.length===2);
 const accepted=await page.evaluate(()=>{const f=window.leaseFixture,s=f.node.__hmbImageAssetLatestState;
  return{lease:s.widget_runtime_lease,scan:s.scan_revision,ui:s.ui_edit_revision,workspace:s.image_bash_workspace,
   search:s.search,stale_timer_fired:f.staleTimerFired,pending:!!f.node.__hmbImageAssetLeaseTransitionPending,retired:f.node.__hmbImageAssetRetiredWidgetLeases.has(f.old.widget_runtime_lease)}});
 assert.equal(accepted.ui,4);assert.equal(accepted.workspace.revision,2);assert(accepted.retired&&!accepted.pending);
 assert.equal(accepted.search,'');assert.equal(accepted.stale_timer_fired,0);
 const retired=await page.evaluate(()=>{const f=window.leaseFixture;f.mainHandle.update(f.props(f.old));return f.node.__hmbImageAssetLatestState.image_bash_workspace.instances.length});assert.equal(retired,2);
 const sameLeaseStale=await page.evaluate(()=>{const f=window.leaseFixture,x=structuredClone(f.fresh);x.ui_edit_revision=1;x.image_bash_workspace.instances=[];f.mainHandle.update(f.props(x));
  return f.node.__hmbImageAssetLatestState.image_bash_workspace.instances.length});assert.equal(sameLeaseStale,2,'Numeric stale-state guards remain active within the confirmed owner');
 await page.evaluate(()=>{const f=window.leaseFixture,c=structuredClone(f.old);c.widget_runtime_lease=f.id(10);c.ui_edit_revision=99;f.mainHandle.update(f.props(c));f.ack(f.fresh.widget_runtime_lease)});
 await page.waitForFunction(()=>!document.getElementById('main').__hmbImageAssetLeaseTransitionPending);
 assert.equal(await page.evaluate(()=>document.getElementById('main').__hmbImageAssetLatestState.image_bash_workspace.instances.length),2);
 const firstId=accepted.workspace.instances[0].instance_id;
 await page.locator(`[data-image-bash-duplicate="${firstId}"]`).first().click();
 // Structural clicks now collect briefly and require a fresh read-only
 // authority reply before their first transmission. Keep every lease assertion.
 await page.waitForTimeout(260);
 await page.evaluate(()=>{const f=leaseFixture;f.mainHandle.update(f.props(f.fresh));f.ack(f.fresh.widget_runtime_lease)});
 await page.waitForTimeout(100);
 const queueProbe=await page.evaluate(()=>({queue:leaseFixture.node.__hmbImageAssetBashEditQueue?.snapshot(),lease:leaseFixture.node.__hmbImageAssetLatestState?.widget_runtime_lease,held:!!leaseFixture.node.__hmbImageAssetLeaseTransitionPending,requests:leaseFixture.requests.map(r=>({operation:r.operation,request_id:r.request_id})),message:leaseFixture.node.querySelector('[data-transport-status]')?.textContent}));
 if(queueProbe.queue?.stopped)throw Error('Queue authority fixture: '+JSON.stringify(queueProbe));
 await page.waitForFunction(()=>document.getElementById('main').__hmbImageAssetLatestState.image_bash_workspace.instances.length===3);
 const copied=await page.evaluate(()=>{const f=window.leaseFixture,s=f.node.__hmbImageAssetLatestState;return{lease:s.widget_runtime_lease,rows:s.image_bash_workspace.instances,
   sent:f.sent.filter(x=>(x.image_bash_workspace||x.edits?.image_bash_workspace)?.instances?.length===3).at(-1)}});
 assert.equal(copied.rows.length,3);assert.equal(new Set(copied.rows.map(r=>r.instance_id)).size,3);assert(copied.sent);assert.equal(copied.sent.widget_runtime_lease,accepted.lease);
 const mixed=await page.evaluate(()=>{const f=window.leaseFixture,queue=[];let h;
  const p=value=>({value,onChange:req=>{queue.push(structuredClone(req));return Promise.resolve({})}});
  h=f.b.default(document.getElementById('other'),p(f.projection(f.id(11))));const q=queue.at(-1);h.update(p({...f.projection(f.id(11),'result',q.request_id),canonical_node_name:'OtherAsset'}));
  f.other=h;const registry=globalThis.__hmbImageAssetThumbnailBridgeRegistry;
  const entry=f.b.hmbImageAssetThumbnailPatchBridgeRegistry().get(f.id(1));
  const clone=document.createElement('div');clone.className='react-flow__node';clone.dataset.id='AssetLive';clone.innerHTML='<div id="same-name"></div>';document.body.append(clone);
  const requests=[],qprops=value=>({value,onChange:request=>{requests.push(request);return Promise.resolve({})}});
  f.same=f.b.default(clone.firstChild,qprops(f.projection(f.id(12))));const request=requests.at(-1);
  f.same.update(qprops(f.projection(f.id(12),'result',request.request_id)));
  const latest=f.b.hmbImageAssetThumbnailPatchBridgeRegistry().get(f.id(1));
  return{live:latest.forNode('AssetLive',f.node.closest('.react-flow__node')).widget_runtime_lease,other:latest.forNode('OtherAsset').widget_runtime_lease,
   sameNameOtherRoot:latest.forNode('AssetLive',clone).widget_runtime_lease,ambiguousNameRejected:latest.forNode('AssetLive')===null}});
 assert.equal(mixed.live,accepted.lease);assert.notEqual(mixed.other,mixed.live);
 assert.notEqual(mixed.sameNameOtherRoot,mixed.live);assert(mixed.ambiguousNameRejected);
 const locked=await page.evaluate(async()=>{const f=window.leaseFixture,c=document.createElement('div');f.node.closest('.react-flow__node').append(c);const requests=[];
  const idle=f.projection(f.fresh.widget_runtime_lease);
  const props=(value,disabled=true,callback='first')=>({disabled,value,onChange:request=>{requests.push({request,callback});return Promise.resolve({})}});
  const h=f.b.default(c,props(idle));
  const owner=[...f.b.hmbImageAssetThumbnailPatchBridgeRegistry().get(f.id(1)).bridgeOwners.values()].find(o=>o.container===c);
  const lockedError=await owner.queryWidgetLease().catch(error=>error.code);
  const lockedReads=requests.length;
  let writeBlocked=false;try{owner.dispatch({operation:'cgt_cancel',widget_runtime_lease:f.fresh.widget_runtime_lease,runtime_instance_id:f.id(1),request_id:'locked-write',session_id:'locked-session'})}catch{writeBlocked=true}
  h.update(props(idle,false,'current'));
  const pending=owner.queryWidgetLease(),last=requests.at(-1);
  h.update(props(f.projection(f.fresh.widget_runtime_lease,'result',last.request.request_id),false,'current'));
  const unlockedLease=await pending;
  const inFlight=owner.queryWidgetLease().catch(error=>error.code);
  const retired=requests.at(-1).request;
  h.update(props(idle));
  h.update(props(f.projection(f.fresh.widget_runtime_lease,'result',retired.request_id)));
  const pendingLockError=await inFlight;
  h.cleanup();return{lockedError,lockedReads,unlockedLease,expectedLease:f.fresh.widget_runtime_lease,pendingLockError,
   fresh_callback:last.callback==='current',write_blocked:writeBlocked,requests:requests.length}});
 assert.deepEqual(locked,{lockedError:'locked',lockedReads:0,unlockedLease:accepted.lease,expectedLease:accepted.lease,
  pendingLockError:'locked',fresh_callback:true,write_blocked:true,requests:2});
 const movedRuntime=await page.evaluate(async()=>{
  const f=window.leaseFixture,node=document.createElement('div');node.className='react-flow__node';node.dataset.id='RuntimeChange';
  const carrier=document.createElement('div');node.append(carrier);document.body.append(node);
  const oldRuntime=f.id(1),runtime=f.id(25),requests=[];
  const props=value=>({value,onChange:request=>requests.push(request)});
  const h=f.b.default(carrier,props(f.projection(f.old.widget_runtime_lease)));
  const request=requests[0],registry=f.b.hmbImageAssetThumbnailPatchBridgeRegistry();
  const pending=registry.get(oldRuntime).forNode(node.dataset.id,node).queryWidgetLease();
  const response=f.projection(f.fresh.widget_runtime_lease,'result',request.request_id);
  response.runtime_instance_id=runtime;
  response.request_runtime_instance_id=oldRuntime;
  response.canonical_node_name=node.dataset.id;
  response.canonical_scope.publisher_instance_uuid=runtime;
  h.update(props(response));
  const lease=await pending;
  h.update(props(request));
  const exact=registry.get(runtime)?.forNode(node.dataset.id,node)?.widget_runtime_lease;
  const old=registry.get(oldRuntime)?.forNode(node.dataset.id,node)??null;
  h.cleanup();node.remove();
  return {lease,exact,old,requests:requests.length};
 });
 assert.deepEqual(movedRuntime,{lease:accepted.lease,exact:accepted.lease,old:null,requests:1});
 const autoemit=await page.evaluate(()=>{const f=window.leaseFixture,s=structuredClone(f.old),node=document.createElement('div');s.shot_routing.publisher_instance_uuid=f.id(90);
  s.project_uid='isolated-project';s.project_cache_uid='isolated-cache';s.manifest_signature='isolated-manifest';s.thumbnail_busy=true;
  s.thumbnail_request={request_id:'stale-auto-resume',project_uid:s.project_uid,manifest_signature:s.manifest_signature,scan_revision:1,asset_library_ids:['a']};
  let writes=0;f.m.hmbResumeImageAssetThumbnailRequest(node,s,{onChange(){writes++}});f.m.hmbClearImageAssetThumbnailWatchdog(node);
  return{writes,rows:s.image_bash_workspace.instances.length}});assert.equal(autoemit.writes,0);assert.equal(autoemit.rows,3,'A legacy saved three-row diagnostic remains authored data, while its stale autoemit is blocked');
 const cache=await page.evaluate(()=>{const f=window.leaseFixture,old=f.m.hmbNormalizeImageAssetState({project_uid:'lease-cache-project',project_cache_uid:'lease-cache-identity',manifest_signature:'same-manifest',widget_runtime_lease:f.old.widget_runtime_lease,
   assets:[{asset_library_id:'cache-a',asset_id:'cache-a',image_name:'cache-a',registered:true,source_uid:'project:cache-a',relative_path:'BG/a.png',media_signature:'same-media',source_kind:'project',thumbnail_url:'data:image/png;base64,unchanged'}]});
  f.m.hmbRememberImageAssetPresentation(old);f.m.hmbResetImageAssetThumbnailRetryState(document.createElement('div'),old);
  const entry=f.m.hmbImageAssetPresentationCacheRegistry().get(f.m.hmbImageAssetPresentationCacheKey(old));entry.requestOwners.get(old.widget_runtime_lease).requested.add('old-inflight');
  const fresh=f.m.hmbNormalizeImageAssetState({...old,widget_runtime_lease:f.fresh.widget_runtime_lease,assets:old.assets.map(a=>({...a,thumbnail_url:''}))});
  f.m.hmbResetImageAssetThumbnailRetryState(document.createElement('div'),fresh);f.m.hmbAdoptImageAssetPresentation(fresh);
  return{media_reused:fresh.assets[0].thumbnail_url===old.assets[0].thumbnail_url,old_request_retained:entry.requestOwners.get(old.widget_runtime_lease).requested.has('old-inflight'),fresh_request_not_suppressed:!entry.requestOwners.get(fresh.widget_runtime_lease).requested.has('old-inflight')}});
 assert(cache.media_reused&&cache.old_request_retained&&cache.fresh_request_not_suppressed);
 await page.clock.install();
 await page.evaluate(()=>{
  const f=leaseFixture,owner=document.createElement('div');
  owner.className='react-flow__node';owner.dataset.id='RecoveryAsset';
  const node=document.createElement('div');owner.append(node);document.body.append(owner);
  const stale=structuredClone(f.old),incoming=structuredClone(f.fresh),live=structuredClone(f.fresh);
  incoming.shot_routing.publisher_instance_uuid=f.id(21);
  live.shot_routing.publisher_instance_uuid=f.id(22);
  const recovery={node,calls:0,writes:0,online:false};
  const props=value=>({value:JSON.stringify(value),nodeName:'RecoveryAsset',onChange:()=>recovery.writes++});
  window.__hmbReadImageAssetAuthority0130=async(name,request)=>{
   if(name!=='RecoveryAsset'||!request.include_view)throw Error('Unscoped recovery read');
   recovery.calls++;
   if(!recovery.online)throw Error('Synthetic transport loss');
   return {schema:request.schema,version:1,operation:request.operation,phase:'result',
    request_id:request.request_id,request_runtime_instance_id:request.runtime_instance_id,canonical_node_name:name,
    widget_runtime_lease:live.widget_runtime_lease,canonical_scope:f.m.hmbImageAssetAuthorityScope(live),canonical_view:JSON.stringify(live)};
  };
  recovery.handle=f.m.default(node,props(stale));
  for(let i=0;i<5;i++)recovery.handle.update(props(incoming));
  window.recoveryAsset=recovery;
 });
 await page.clock.runFor(10100);
 const stopped=await page.evaluate(()=>{const r=recoveryAsset;return{calls:r.calls,writes:r.writes,
  pending:r.node.__hmbImageAssetLeaseTransitionPending,busy:r.node.__hmbImageAssetBusy,
  inert:r.node.querySelector('.hmb-image-assets').hasAttribute('inert'),retry:!!r.node.querySelector('[data-asset-connection-retry]')};});
 assert.deepEqual(stopped,{calls:2,writes:0,pending:true,busy:false,inert:true,retry:true});
 await page.evaluate(()=>{recoveryAsset.online=true;recoveryAsset.node.querySelector('[data-asset-connection-retry]').click();});
 await page.clock.runFor(500);
 const recovered=await page.evaluate(()=>{const r=recoveryAsset;return{calls:r.calls,writes:r.writes,
  runtime:r.node.__hmbImageAssetLatestState.shot_routing.publisher_instance_uuid,
  pending:!!r.node.__hmbImageAssetLeaseTransitionPending,busy:r.node.__hmbImageAssetBusy};});
 assert.deepEqual(recovered,{calls:3,writes:0,runtime:'40000000-0000-4000-8000-000000000022',pending:false,busy:false});
 await page.evaluate(()=>{recoveryAsset.handle.cleanup();recoveryAsset.node.parentElement.remove();delete window.__hmbReadImageAssetAuthority0130;});
 await page.screenshot({path:path.join(out,'SYNTHETIC-WIDGET-LEASE.png')});
 const counts=await page.evaluate(()=>{const f=window.leaseFixture;f.mainHandle.cleanup();f.handle.cleanup();f.other.cleanup();f.same.cleanup();return{semantic:f.sent.length,requests:f.requests.length}});
 assert.equal(errors.length,0,errors.join('\n'));
 proof={status:'PASS',scope:'Synthetic widget DOM in isolated Chromium; no Desktop or SDK requests',correlated,pending,accepted,retired_lease_ignored:true,same_lease_numeric_stale_guard:true,locked_readonly_authority:locked,correlated_runtime_transition:movedRuntime,leased_stale_autoemit_without_bridge:autoemit,presentation_vs_request_cache:cache,
  unknown_lease_cannot_relabel_old_state:true,intentional_copy:copied,mixed_persisted_publisher_scoped_by_actual_node:mixed,
  recovery_after_timeout:recovered,cleanup:true,blocked_network_requests:blocked.length,errors,counts,
  product_root:productRoot,source_test:fileURLToPath(import.meta.url),
  main_sha256:crypto.createHash('sha256').update(main).digest('hex'),bridge_sha256:crypto.createHash('sha256').update(bridge).digest('hex')};
}catch(error){proof={status:'FAILED',error:String(error),stack:error.stack};throw error}
finally{fs.writeFileSync(path.join(out,'RUNTIME-LEASE-FRONTEND.json'),JSON.stringify(proof,null,2)+'\n');await browser.close();console.log(JSON.stringify(proof))}
