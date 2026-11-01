// Native-documented props and adversarial native DOM lifecycle; isolated UI only.
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import assert from 'node:assert/strict';import {fileURLToPath} from 'node:url';
import {nativeTestPlaywright,nativeTestBrowserPath} from './_hmb_native_editor_fixture.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),out=path.resolve(process.env.HMB_LIFECYCLE_REPORT_DIR||path.join(root,'reports/regression-checks/HMB_Image_Asset_Authority_Lifecycle_Regression'));fs.mkdirSync(out,{recursive:true});
const productRoot=process.env.HMB_LIFECYCLE_WIDGET_ROOT||root;
const main=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetLibraryWidget.js'),'utf8'),bridge=fs.readFileSync(path.join(productRoot,'widgets/HMBImageAssetThumbnailPatchBridgeWidget.js'),'utf8');
const baseline=process.argv.includes('--baseline'),browser=await nativeTestPlaywright().chromium.launch({headless:true,executablePath:nativeTestBrowserPath()});
const result={status:'RUNNING',baseline,scope:'Actual source widgets; native documented nodeName/parameterName props, hidden-property carrier and ReactFlow roots simulated. No Desktop or SDK.',cases:{},external_requests:0};
try{
 const page=await browser.newPage({viewport:{width:1500,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/*',r=>{if(r.request().url()==='http://127.0.0.1/hmb-lifecycle')return r.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'});result.external_requests++;return r.abort()});
 await page.goto('http://127.0.0.1/hmb-lifecycle');
 await page.evaluate(async({main,bridge})=>{const imp=s=>import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(s))));const m=await imp(main),b=await imp(bridge),id=n=>`70000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
  const digest=async value=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(n=>n.toString(16).padStart(2,'0')).join('');
  window.make=async(number,depth=0,withBridge=true)=>{const node=document.createElement('article');node.className='react-flow__node';node.dataset.id=`Native Asset ${number}`;node.style.width='1300px';document.body.append(node);
   let branch=node;for(let i=0;i<depth;i++){const p=document.createElement('section');branch.append(p);branch=p;}
   const mainNode=document.createElement('div');branch.append(mainNode);const carrier=document.createElement('div');carrier.dataset.parameterName='HMB_IMAGE_ASSET_THUMBNAIL_PATCH';carrier.style.opacity='0';node.append(carrier);
   const state=m.hmbNormalizeImageAssetState({schema:'hmb-image-asset-library-state',widget_runtime_lease:id(100+number),ui_edit_revision:4,scan_revision:1,
    projects:[{project_id:'One',path:'P:/projects/One/Ai_Ct_image',name:'One'},{project_id:'Two',path:'P:/projects/Two/Ai_Ct_image',name:'Two'}],
    shot_routing:{schema:'hmb-shot-routing',version:1,publisher_instance_uuid:id(number),channel_uuid:id(200+number),generation:1,active_shot_uuid:id(300+number),shots:[{shot_uuid:id(300+number),number:1,name:'Shot 1',revision:0,selected_source_uids:[]}]},
    image_bash_workspace:{workspace_id:id(400+number),revision:2,instances:[{instance_id:id(500+number),source_uid:'project:a'},{instance_id:id(600+number),source_uid:'project:b'}]},image_bash_active:true});
   const f={node,mainNode,carrier,state,requests:[],writes:[],m,b,id,digest};
   f.raw=JSON.stringify(state);f.mainProps=()=>({value:f.raw,nodeName:node.dataset.id,parameterName:'HMB_IMAGE_ASSET_STATE',ui_options:{widget:'HMBImageAssetLibraryWidget',library:'HMB_GP_Production'},disabled:false,onChange:v=>{f.writes.push(JSON.parse(v));return Promise.resolve({})}});
   f.bridgeProps=value=>({value,nodeName:node.dataset.id,parameterName:'HMB_IMAGE_ASSET_THUMBNAIL_PATCH',ui_options:{widget:'HMBImageAssetThumbnailPatchBridgeWidget',library:'HMB_GP_Production'},disabled:false,onChange:v=>{f.requests.push(structuredClone(v));return Promise.resolve({})}});
   f.mountBridge=()=>{f.bh=b.default(carrier,f.bridgeProps({schema:'hmb-image-asset-thumbnail-bridge',version:1,phase:'idle',runtime_instance_id:state.shot_routing.publisher_instance_uuid,widget_runtime_lease:state.widget_runtime_lease,catalog_page_version:1}))};
   f.ack=async()=>{const request=f.requests.filter(x=>x.operation==='widget_authority').at(-1);if(!request)return false;
    f.mh.update(f.mainProps());
    const canonical_scope=m.hmbImageAssetAuthorityScope?m.hmbImageAssetAuthorityScope(state):null;
    f.bh.update(f.bridgeProps({...request,phase:'result',widget_runtime_lease:state.widget_runtime_lease,canonical_node_name:node.dataset.id,...(canonical_scope?{canonical_scope,canonical_scope_sha256:await digest(JSON.stringify(canonical_scope))}:{}),catalog_page_version:1}));return true};
   f.mh=m.default(mainNode,f.mainProps());if(withBridge){f.mountBridge();await f.ack();}
   f.queuedReady=async()=>{await new Promise(r=>setTimeout(r,260));await f.ack();await frames(3)};
   f.drain=async()=>{await f.queuedReady();for(let n=0;n<15;n++){
    for(const wire of f.writes.slice(f.confirmedWrites||0)){Object.assign(state,wire.edits||wire,{ui_edit_revision:wire.ui_edit_revision,image_bash_workspace_edit:{},image_bash_workspace_request:{}});f.confirmedWrites=(f.confirmedWrites||0)+1;}
    f.raw=JSON.stringify(state);f.mh.update(f.mainProps());await frames(3);await f.ack();await frames(3);
    const q=f.mainNode.__hmbImageAssetBashEditQueue?.snapshot();if(!q?.pending&&!q?.active&&!q?.preparing)return;
   }throw Error('Queue fixture did not settle')};
   f.choose=path=>{const select=mainNode.querySelector('[data-project-select]');select.value=path;select.dispatchEvent(new Event('change',{bubbles:true}))};
   f.close=()=>{f.mh.cleanup();f.bh?.cleanup();node.remove()};return f;
  };window.frames=async(n=3)=>{for(let i=0;i<n;i++)await new Promise(requestAnimationFrame)};
 },{main,bridge});
 result.cases.first_mount_latest_project=await page.evaluate(async()=>{const f=await make(1,0,false);f.choose('P:/projects/One/Ai_Ct_image');await frames();f.choose('P:/projects/Two/Ai_Ct_image');await frames();
  const before=f.writes.length;f.mountBridge();await f.ack();await frames(6);const value={before,after:f.writes.length,target:f.writes.at(-1)?.project_root||'',error:f.mainNode.querySelector('[data-transport-status]')?.textContent||''};f.close();return value});
 result.cases.deep_native_groups=await page.evaluate(async()=>{const f=await make(2,21);f.choose('P:/projects/One/Ai_Ct_image');await frames();await f.ack();await frames(6);const value={after:f.writes.length,target:f.writes.at(-1)?.project_root||''};f.close();return value});
 result.cases.rename_without_value_update=await page.evaluate(async()=>{const f=await make(3);f.node.dataset.id='Native Asset Renamed';f.choose('P:/projects/One/Ai_Ct_image');await frames();await f.ack();await frames(6);const value={after:f.writes.length,target:f.writes.at(-1)?.project_root||''};f.close();return value});
 result.cases.hidden_carrier_reparent=await page.evaluate(async()=>{const f=await make(4),replacement=document.createElement('article');replacement.className='react-flow__node';replacement.dataset.id=f.node.dataset.id;document.body.append(replacement);replacement.append(f.mainNode,f.carrier);
  f.choose('P:/projects/One/Ai_Ct_image');await frames();await f.ack();await frames(6);const value={after:f.writes.length,target:f.writes.at(-1)?.project_root||''};f.close();replacement.remove();return value});
 if(!baseline){
 result.cases.same_lease_saved_clock_rollback=await page.evaluate(async()=>{const f=await make(5),old=structuredClone(f.state);old.ui_edit_revision=26;old.image_bash_workspace.revision=17;
  while(old.image_bash_workspace.instances.length<9)old.image_bash_workspace.instances.push({instance_id:crypto.randomUUID(),source_uid:'project:a'});
  f.mh.update({...f.mainProps(),value:JSON.stringify(old)});f.mh.update(f.mainProps());await frames();const before=f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length;
  await f.ack();await frames(6);const current=f.mainNode.__hmbImageAssetLatestState,value={before,after:current.image_bash_workspace.instances.length,ui:current.ui_edit_revision,lease:current.widget_runtime_lease,expectedLease:f.state.widget_runtime_lease,writes:f.writes.length};f.close();return value});
 result.cases.catalog_add_and_explicit_intents=await page.evaluate(async()=>{const f=await make(6);f.state.assets=['a','b','c'].map(id=>({asset_library_id:id,asset_id:id,image_name:id,source_kind:'project',registered:true,source_uid:'project:'+id,relative_path:'BG/'+id+'.png'}));f.raw=JSON.stringify(f.state);f.mh.update(f.mainProps());
  const card=id=>f.mainNode.querySelector('[data-asset-key="'+id+'"]');card('a').click();await f.drain();const existing=f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length;
  card('c').click();card('c').click();await f.drain();const afterAdd=f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length;
  const original=f.state.image_bash_workspace.instances[0].instance_id,copy=f.mainNode.querySelector('[data-image-bash-duplicate="'+original+'"]'),event=new MouseEvent('click',{bubbles:true,cancelable:true});copy.dispatchEvent(event);
  f.mainNode.querySelector('[data-image-bash-duplicate="'+original+'"]').dispatchEvent(event);await f.drain();const afterSameEvent=f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length;
  const copyId=f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.find(row=>row.source_uid==='project:a'&&row.instance_id!==original).instance_id;
  f.mainNode.querySelector('[data-image-bash-remove="'+copyId+'"]').click();await f.drain();
  const live=f.mainNode.__hmbImageAssetLatestState,first=live.image_bash_workspace.instances[0].instance_id,last=live.image_bash_workspace.instances.at(-1).instance_id;
  f.mainNode.querySelector('[data-image-bash-instance="'+first+'"]').dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:new DataTransfer()}));
  f.mainNode.querySelector('[data-image-bash-instance="'+last+'"]').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:new DataTransfer()}));
  await f.drain();const intents=f.writes.map(w=>w.image_bash_workspace_edit||w.edits?.image_bash_workspace_edit).filter(w=>w?.operation_id);
  const value={existing,afterAdd,afterSameEvent,finalRows:f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length,intents,uniqueOperations:new Set(intents.map(i=>i.operation_id)).size};f.close();return value});
 result.cases.authored_eleven_preserved=await page.evaluate(async()=>{const f=await make(7);f.state.ui_edit_revision=30;f.state.image_bash_workspace.revision=17;while(f.state.image_bash_workspace.instances.length<11)f.state.image_bash_workspace.instances.push({instance_id:crypto.randomUUID(),source_uid:'project:a'});f.raw=JSON.stringify(f.state);f.mh.update(f.mainProps());await frames();const value={rows:f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length,writes:f.writes.length};f.close();return value});
 result.cases.native_void_project_server_derived_ack=await page.evaluate(async()=>{const f=await make(8),baseProps=f.mainProps;
  f.mainProps=()=>({...baseProps(),onChange:wire=>{f.writes.push(JSON.parse(wire));f.mh.update({...f.mainProps(),value:wire})}});f.mh.update(f.mainProps());f.choose('P:/projects/One/Ai_Ct_image');await frames();await f.ack();await frames(6);
  const before=f.mainNode.__hmbImageAssetPendingPublications?.size||0,sent=f.writes.at(-1);Object.assign(f.state,sent,{scan_revision:sent.scan_revision+1,thumbnail_revision:sent.thumbnail_revision+3,project_uid:'server-resolved-project',project_cache_uid:'server-cache',image_bash_workspace_edit:{},scan_busy:false});
  f.raw=JSON.stringify(f.state);f.mh.update(f.mainProps());await frames();const value={before,after:f.mainNode.__hmbImageAssetPendingPublications?.size||0,project:f.mainNode.__hmbImageAssetLatestState.project_uid,scan:f.mainNode.__hmbImageAssetLatestState.scan_revision,writes:f.writes.length};f.close();return value});
 result.cases.native_void_copy_canonical_ack=await page.evaluate(async()=>{const f=await make(9);f.state.edit_transport_schema='hmb-image-asset-edit-v1';f.raw=JSON.stringify(f.state);const baseProps=f.mainProps;
  f.mainProps=()=>({...baseProps(),onChange:wire=>{f.writes.push(JSON.parse(wire));f.mh.update({...f.mainProps(),value:wire})}});f.mh.update(f.mainProps());const original=f.state.image_bash_workspace.instances[0].instance_id;
  f.mainNode.querySelector('[data-image-bash-duplicate="'+original+'"]').click();await f.queuedReady();const before=f.mainNode.__hmbImageAssetPendingPublications?.size||0,sent=f.writes.at(-1);
  Object.assign(f.state,sent.edits,{ui_edit_revision:sent.ui_edit_revision,scan_revision:2,thumbnail_revision:4,image_bash_workspace_edit:{}});f.raw=JSON.stringify(f.state);f.mh.update(f.mainProps());await frames();
  const value={before,after:f.mainNode.__hmbImageAssetPendingPublications?.size||0,rows:f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length,writes:f.writes.length};f.close();return value});
 result.cases.late_read_after_local_copy=await page.evaluate(async()=>{const f=await make(10),old=structuredClone(f.state);f.state.edit_transport_schema='hmb-image-asset-edit-v1';f.raw=JSON.stringify(f.state);f.mh.update(f.mainProps());
  let rejected=false;const read=f.m.hmbWaitForImageAssetAuthority(f.mainNode,f.state,{fresh:true}).catch(()=>{rejected=true}),request=f.requests.at(-1),first=f.state.image_bash_workspace.instances[0].instance_id;
  f.mainNode.querySelector('[data-image-bash-duplicate="'+first+'"]').click();await f.queuedReady();const sent=f.writes.at(-1);Object.assign(f.state,sent.edits,{ui_edit_revision:sent.ui_edit_revision,image_bash_workspace_edit:{}});f.raw=JSON.stringify(f.state);f.mh.update(f.mainProps());await frames();
  f.mh.update({...f.mainProps(),value:JSON.stringify(old)});f.bh.update(f.bridgeProps({...request,phase:'result',widget_runtime_lease:old.widget_runtime_lease,canonical_node_name:f.node.dataset.id,canonical_scope:f.m.hmbImageAssetAuthorityScope(old)}));await frames();await f.ack();await frames();await read;
  const value={rejected,rows:f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length,writes:f.writes.length};f.close();return value});
 result.cases.late_read_after_server_canonical=await page.evaluate(async()=>{const f=await make(11),old=structuredClone(f.state);let rejected=false;
  const read=f.m.hmbWaitForImageAssetAuthority(f.mainNode,f.state,{fresh:true}).catch(()=>{rejected=true}),request=f.requests.at(-1);
  f.state.ui_edit_revision=5;f.state.image_bash_workspace.revision=3;f.state.image_bash_workspace.instances.push({instance_id:crypto.randomUUID(),source_uid:'project:a'});f.raw=JSON.stringify(f.state);f.mh.update(f.mainProps());await frames();
  f.mh.update({...f.mainProps(),value:JSON.stringify(old)});f.bh.update(f.bridgeProps({...request,phase:'result',widget_runtime_lease:old.widget_runtime_lease,canonical_node_name:f.node.dataset.id,canonical_scope:f.m.hmbImageAssetAuthorityScope(old)}));await frames();await read;
  const value={rejected,rows:f.mainNode.__hmbImageAssetLatestState.image_bash_workspace.instances.length,writes:f.writes.length};f.close();return value});
 result.cases.old_bridge_protocol_recovery=await page.evaluate(async()=>{const f=await make(12,0,false),registry=f.b.hmbImageAssetThumbnailPatchBridgeRegistry(),runtime=f.state.shot_routing.publisher_instance_uuid;let legacyWrites=0;
  registry.set(runtime,{...registry.get(runtime),dispatch(){legacyWrites++},catalogPageVersion:1});f.choose('P:/projects/One/Ai_Ct_image');await frames(6);const before=f.writes.length,message=f.mainNode.querySelector('[data-transport-status]')?.textContent||'';
  f.mountBridge();await f.ack();f.choose('P:/projects/One/Ai_Ct_image');await frames();await f.ack();await frames(6);const value={before,after:f.writes.length,legacyWrites,message};f.close();return value});
 }
 result.errors=errors;
 if(!baseline){assert.equal(result.cases.first_mount_latest_project.before,0);assert.equal(result.cases.first_mount_latest_project.after,1);assert.equal(result.cases.first_mount_latest_project.target,'P:/projects/Two/Ai_Ct_image');
  for(const name of ['deep_native_groups','rename_without_value_update','hidden_carrier_reparent']){assert.equal(result.cases[name].after,1,name);assert.equal(result.cases[name].target,'P:/projects/One/Ai_Ct_image',name)}assert.deepEqual(errors,[]);}
 if(!baseline){const rollback=result.cases.same_lease_saved_clock_rollback;assert.equal(rollback.before,9);assert.equal(rollback.after,2);assert.equal(rollback.ui,4);assert.equal(rollback.lease,rollback.expectedLease);assert.equal(rollback.writes,0);
  const intent=result.cases.catalog_add_and_explicit_intents;assert.equal(intent.existing,2);assert.equal(intent.afterAdd,3);assert.equal(intent.afterSameEvent,4);assert.equal(intent.finalRows,3);assert.deepEqual(intent.intents.map(i=>i.operation),['add','copy','remove','reorder']);assert.equal(intent.uniqueOperations,4);
  assert.equal(result.cases.authored_eleven_preserved.rows,11);assert.equal(result.cases.authored_eleven_preserved.writes,0);}
 if(!baseline){for(const name of ['native_void_project_server_derived_ack','native_void_copy_canonical_ack']){assert.equal(result.cases[name].before,1,name);assert.equal(result.cases[name].after,0,name);assert.equal(result.cases[name].writes,1,name)}
  assert.equal(result.cases.native_void_project_server_derived_ack.project,'server-resolved-project');assert.equal(result.cases.native_void_copy_canonical_ack.rows,3);
  // The queued local edit now waits for its existing read to complete before
  // writing. A truly superseding external canonical still rejects the read.
  assert.equal(result.cases.late_read_after_local_copy.rejected,false);
  assert.equal(result.cases.late_read_after_server_canonical.rejected,true);
  for(const name of ['late_read_after_local_copy','late_read_after_server_canonical'])assert.equal(result.cases[name].rows,3,name);
  assert.equal(result.cases.old_bridge_protocol_recovery.before,0);assert.equal(result.cases.old_bridge_protocol_recovery.after,1);assert.equal(result.cases.old_bridge_protocol_recovery.legacyWrites,0);assert.match(result.cases.old_bridge_protocol_recovery.message,/완전히 종료/);}
 result.status=baseline?'BASELINE_OBSERVED':'PASS';result.main_sha256=crypto.createHash('sha256').update(main).digest('hex');result.bridge_sha256=crypto.createHash('sha256').update(bridge).digest('hex');
}catch(error){result.status='FAILED';result.error=String(error).slice(0,3000);throw error}
finally{await browser.close();fs.writeFileSync(path.join(out,baseline?'AUTHORITY-LIFECYCLE-BASELINE.json':'AUTHORITY-LIFECYCLE-CANDIDATE.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));}
