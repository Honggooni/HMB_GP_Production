// Actual ImageAsset product widget; synthetic offline host/creation boundary.
// No engine, app, provider, server, installation or paid-generation calls.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import * as w from '../../widgets/HMBImageAssetLibraryWidget.js';

const root=new URL('../../',import.meta.url);
const report=process.env.HMB_IMAGE_BASH_WORKSPACE_REPORT_DIR;
const pixel='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/vN8AAAAASUVORK5CYII=';
const initial=w.hmbNormalizeImageAssetState({
 project_root:'C:/fixture/Ai_Ct_image/superwings12',project_id:'superwings12',project_uid:'fixture-project',
 edit_transport_schema:'hmb-image-asset-edit-v1',selected_source_view:'user',
 assets:Array.from({length:7},(_,index)=>({asset_library_id:`catalog-${index+1}`,asset_id:`asset-${index+1}`,
  source_uid:`source-${index+1}`,image_name:`Source ${index+1}`,source_kind:'user',
  import_index:index+1,
  path:`C:/fixture/source-${index+1}.png`,thumbnail_url:pixel,selected:index<5,selection_order:index<5?index+1:0,
  media_signature:String(index+1).repeat(64),width:64,height:32})),
});
while(initial.shot_routing.shots.length<5)w.hmbAddImageAssetShot(initial);
initial.shot_routing.shots.forEach((shot,index)=>Object.assign(shot,{
 name:`e201s${String(index+1).padStart(3,'0')}c001__`,name_is_custom:true,revision:11+index,
 selected_source_uids:[`source-${index+1}`],media_count:1,
 metadata_sha256:String(index+1).repeat(64),media_sha256:String(index+2).repeat(64),
}));
initial.shot_routing.active_shot_uuid=initial.shot_routing.shots[2].shot_uuid;
initial.shot_routing.expanded=true;
const boundMembers=initial.shot_routing.shots.map((shot,index)=>{
 const manualUuid=randomUUID();return {member_id:'manual:'+manualUuid,origin:'manual',manual_uuid:manualUuid,
  source_name:shot.name,canonical_name:shot.name,gp_shot_uuid:shot.shot_uuid,parent_id:null,
  selection_order:index+1,cgt_task_id:null,artist:null,status:null};
});
boundMembers[1].parent_id=boundMembers[0].member_id;
initial.shot_hierarchy={schema:'hmb-shot-hierarchy',version:1,binding_id:randomUUID(),revision:7,
 project_identity:initial.project_root.toLowerCase(),channel_uuid:initial.shot_routing.channel_uuid,cgt_account_id:null,members:boundMembers};
const boundNames=w.hmbHierarchyDerivedNames(initial.shot_hierarchy);
initial.shot_routing.shots.forEach(shot=>{shot.name=boundNames[shot.shot_uuid];});
const immutableSnapshot=state=>({shot_routing:structuredClone(state.shot_routing),shot_hierarchy:structuredClone(state.shot_hierarchy),
 assets:state.assets.map(asset=>({source_uid:asset.source_uid,selected:asset.selected,selection_order:asset.selection_order,
  path:asset.path,media_signature:asset.media_signature,image_main_type:asset.image_main_type,image_sub_type:asset.image_sub_type}))});
const baseline=immutableSnapshot(initial);
let checks=0;
const assertShotsUntouched=(state,label)=>{assert.deepEqual(immutableSnapshot(state),baseline,label);checks++;};

for(const name of ['hmbNormalizeImageBashWorkspace','hmbCreateImageBashWorkspace','hmbAddImageBashSource',
 'hmbRemoveImageBashInstance','hmbDuplicateImageBashInstance','hmbReorderImageBashInstance','hmbImageBashWorkspaceAssets']){
 assert.equal(typeof w[name],'function',`Product workspace API ${name} is available`);checks++;
}

// Workspace identities belong to instances, not list positions or image URLs.
const state=w.hmbNormalizeImageAssetState(initial);
w.hmbCreateImageBashWorkspace(state);assertShotsUntouched(state,'Creating Image Bash keeps all five shot records and selections');
const workspaceId=state.image_bash_workspace.workspace_id;
assert.match(workspaceId,/^[0-9a-f-]{36}$/i);checks++;
for(const source of ['source-6','source-7','source-6'])w.hmbAddImageBashSource(state,source);
assertShotsUntouched(state,'Workspace sources do not join or deselect any shot');
assert.equal(state.shot_routing.shots.length,5,'Image Bash is not a sixth shot');
assert.deepEqual(state.image_bash_workspace.instances.map(row=>row.source_uid),['source-6','source-7','source-6']);
const instances=structuredClone(state.image_bash_workspace.instances),revision=state.image_bash_workspace.revision;
assert.equal(new Set(instances.map(row=>row.instance_id)).size,3,'The same source can have independent stable occurrences');checks+=3;
w.hmbReorderImageBashInstance(state,instances[2].instance_id,instances[0].instance_id);
assert.deepEqual(state.image_bash_workspace.instances.map(row=>row.instance_id),[instances[2].instance_id,instances[0].instance_id,instances[1].instance_id]);
assert.ok(state.image_bash_workspace.revision>revision);checks+=2;
w.hmbDuplicateImageBashInstance(state,instances[0].instance_id);
assert.equal(state.image_bash_workspace.instances.filter(row=>row.source_uid==='source-6').length,3);
assert.equal(new Set(state.image_bash_workspace.instances.map(row=>row.instance_id)).size,4);checks+=2;
w.hmbRemoveImageBashInstance(state,instances[2].instance_id);
assert.equal(state.image_bash_workspace.instances.some(row=>row.instance_id===instances[2].instance_id),false);
assert.equal(state.image_bash_workspace.workspace_id,workspaceId);checks+=2;
assertShotsUntouched(state,'Reorder, duplicate and removal retain shot IDs, names, binding and media receipts');
const saved=w.hmbNormalizeImageAssetState(JSON.parse(JSON.stringify(state)));
assert.deepEqual(saved.image_bash_workspace,state.image_bash_workspace,'Save/reopen preserves workspace instance order and identities');checks++;
assertShotsUntouched(saved,'Save/reopen retains all prior shots');
const blockedProject={...initial.assets[0],asset_library_id:'project-unregistered',source_uid:'project-unregistered',source_kind:'project',registered:false,selected:false,selection_order:0};
const blockedState=w.hmbNormalizeImageAssetState({...saved,assets:[...saved.assets,blockedProject]});
const blockedBefore=JSON.stringify(blockedState);
assert.equal(w.hmbImageAssetCanSelect(blockedProject),false);
assert.equal(w.hmbAddImageBashSource(blockedState,blockedProject.source_uid),false,'Project catalog entries still require registration before Bash selection');
assert.equal(w.hmbToggleImageAssetShotAsset(blockedState,blockedState.shot_routing.shots[0].shot_uuid,blockedProject.source_uid),false,'Project catalog entries still require registration before Shot selection');
assert.equal(JSON.stringify(blockedState),blockedBefore);checks+=4;
const missing=w.hmbNormalizeImageAssetState({...saved,assets:saved.assets.filter(asset=>asset.source_uid!=='source-6')});
assert.deepEqual(missing.image_bash_workspace,saved.image_bash_workspace,'A missing library source retains the authored workspace instances');
assert.ok(w.hmbImageBashWorkspaceAssets(missing).filter(row=>row.source_uid==='source-6').every(row=>row.asset===null),'A missing source is never replaced by the next image');checks+=2;
// Exercise the actual Python output-pair builder with this exact JS-authored
// state. Media resolution is synthetic; artifact construction/order is real.
const outputCode=`import ast,json,sys
from pathlib import Path
from typing import Any,Dict
source=Path(sys.argv[1]).read_text(encoding='utf-8-sig')
node=next(row for row in ast.parse(source).body if isinstance(row,ast.FunctionDef) and row.name=='_build_image_bash_outputs')
state=json.load(sys.stdin)
def resolve(scoped,*args,**kwargs):
 return {'resolved':[{'source_uid':row['source_uid'],'asset':row,'media':'file:///'+row['source_uid']+'.png'} for row in scoped['assets'] if row['selected']]}
scope={'Any':Any,'Dict':Dict,'_resolve_selected_assets':resolve,'_clean':lambda value:str(value or '').strip(),'IMAGE_BASH_CONTEXT_SCHEMA':'hmb-image-bash-inputs-v1'}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual HMBImageAsset output-pair builder>','exec'),scope)
images,context=scope['_build_image_bash_outputs'](state)
print(json.dumps({'images':[{'url':image.value,'name':image.name} for image in images],'context':context,'state':state}))`;
const installedPython=path.join(process.env.LOCALAPPDATA||'', 'ai.griptape.nodes.desktop/current/resources/engine-bundle/python/python.exe');
const python=spawnSync(process.env.HMB_IMAGE_BASH_WORKSPACE_PYTHON||(fs.existsSync(installedPython)?installedPython:fileURLToPath(new URL('.venv/Scripts/python.exe',root))),
 ['-B','-c',outputCode,fileURLToPath(new URL('HMBImageAssetLibrary.py',root))],
 {input:JSON.stringify(saved),encoding:'utf8',timeout:30000,maxBuffer:1024*1024});
assert.equal(python.status,0,python.stderr||python.stdout);
const pair=JSON.parse(python.stdout);
assert.deepEqual(pair.state,saved,'The output-pair builder does not mutate JS-authored state');
assert.deepEqual(pair.context.records.map(row=>row.source_uid),saved.image_bash_workspace.instances.map(row=>row.instance_id));
assert.deepEqual(pair.context.records.map(row=>row.catalog_uid),saved.image_bash_workspace.instances.map(row=>row.source_uid));
assert.deepEqual(pair.images.map(row=>row.url),pair.context.records.map(row=>row.url),'Typed image and context outputs have exactly the same instance order');
assert.equal(pair.context.workspace_id,workspaceId);checks+=6;

const require=createRequire(import.meta.url);
const playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const widgetSource=fs.readFileSync(new URL('widgets/HMBImageAssetLibraryWidget.js',root),'utf8');
const html=`<!doctype html><meta charset="utf-8"><title>Offline Image Bash workspace product fixture</title>
<style>body{margin:0;background:#101420;color:white}#widget{width:1100px;height:900px}</style><div id="widget"></div>
<script type="module">
import mount,*as w from '/widget.js';window.w=w;window.initial=${JSON.stringify(initial)};window.host=null;
window.writes=[];window.createRequests=[];window.routingCatalogs=[];window.syncEcho=false;window.disabled=false;window.deferNext=false;window.pendingPublication=null;
addEventListener('hmb-shot-routing-catalog-v1',event=>window.routingCatalogs.push(structuredClone(event.detail)));
window.acceptRaw=raw=>{
 const edit=raw.edits||raw;
 const next={...window.host,...edit};
 const request=edit.image_bash_workspace_request;
 if(request?.schema){window.createRequests.push(structuredClone(request));next.image_bash_workspace_request={};}
 window.host=w.hmbNormalizeImageAssetState(next);window.host.ui_edit_revision=raw.ui_edit_revision;
 if(window.syncEcho)window.controller.update(window.props());else queueMicrotask(()=>window.controller.update(window.props()));
};
window.finishPublication=accepted=>{const pending=window.pendingPublication;if(!pending)return;window.pendingPublication=null;
 if(accepted){window.acceptRaw(pending.raw);pending.resolve();}else pending.reject(new Error('Synthetic Bash selection rejection'));};
window.props=()=>({value:JSON.stringify(window.host),disabled:window.disabled,onChange:value=>{
 const raw=JSON.parse(value);if(raw.__hmb_manifest_poll_nonce)return;
 window.writes.push(structuredClone(raw));
 if(window.deferNext){window.deferNext=false;return new Promise((resolve,reject)=>{window.pendingPublication={raw,resolve,reject};});}
 window.acceptRaw(raw);
}});
window.openGraph=value=>{window.controller?.cleanup();window.host=w.hmbNormalizeImageAssetState(value);
 window.controller=mount(document.getElementById('widget'),window.props());};
window.openGraph(window.initial);window.ready=true;
</script>`;
const server=http.createServer((request,response)=>{response.setHeader('Content-Type',request.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');response.end(request.url==='/widget.js'?widgetSource:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 browser=await playwright.chromium.launch({executablePath:process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1250,height:1100}}),errors=[];page.setDefaultTimeout(7000);
 page.on('pageerror',error=>errors.push(error.message));await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
 const expanded=page.locator('[data-library-expanded]');
 const workspace=()=>expanded.locator('[data-image-bash-panel]');
 const browserSnapshot=()=>page.evaluate(()=>structuredClone(window.host));
 const assertBrowserShots=async label=>assertShotsUntouched(await browserSnapshot(),label);
 const addImageBash=async()=>{await page.locator('[data-hier-slot]').selectOption('image_bash');await page.locator('[data-hier-add]').click();};
 // Product UI assertions follow the public data attributes, rather than a
 // second implementation of workspace actions or node-creation commands.
 assert.equal(await page.locator('[data-shot-panel]').count(),5);
 assert.equal(await page.locator('[data-image-bash-panel]').count(),0,'Existing workflows do not acquire an Image Bash workspace implicitly');
 assert.equal(await page.evaluate(()=>window.createRequests.length),0);checks+=3;
 assert.equal(w.hmbImageAssetCanSelect(initial.assets[5]),true,'Unregistered user imports were already selectable without project registration');checks++;
 await expanded.locator('[data-asset-key="catalog-6"] [data-asset-add]').click();
 assert.equal(await page.locator('[data-registration-backdrop]').count(),1);
 assert.equal(await page.locator('[data-registration-bash-add]').count(),0,'The new passport action is absent while an ordinary Shot is active');checks+=2;
 await page.locator('[data-registration-cancel]').first().click();
 await page.locator('[data-shot-add]').first().click();
 await page.locator('[data-shot-hierarchy-dialog]').waitFor();
 assert.equal(await page.locator('[data-image-bash-add]').count(),0,'Image Bash has no separate add button');
 assert.equal(await page.locator('[data-hier-slot] option[value="image_bash"]').innerText(),'HMBImageBash');
 assert.equal(await page.locator('[data-hier-slot] option').count(),7,'New shot, five existing slots and Image Bash share the same selector');checks+=3;
 await page.locator('[data-hier-manual-name]').fill('Preserved name draft');
 await page.locator('[data-hier-slot]').selectOption('image_bash');
 assert.equal(await page.locator('[data-hier-manual-name-field]').isVisible(),false);
 assert.equal(await page.locator('[data-hier-manual-name]').isDisabled(),true);
 assert.equal(await page.locator('[data-hier-add]').innerText(),'HMBImageBash 추가');
 await page.locator('[data-hier-slot]').selectOption('new');
 assert.equal(await page.locator('[data-hier-manual-name]').isVisible(),true);
 assert.equal(await page.locator('[data-hier-manual-name]').isEnabled(),true);
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'Preserved name draft');
 assert.equal(await page.locator('[data-hier-add]').innerText(),'수동 추가');checks+=7;
 await page.locator(`[data-hier-remove="${boundMembers[1].manual_uuid}"]`).click();
 await addImageBash();
 assert.equal(await page.locator('[data-shot-hierarchy-dialog]').count(),1,'An unconfirmed shot-binding draft cannot be discarded by adding Image Bash');
 assert.equal(await page.evaluate(()=>window.createRequests.length),0);
 await assertBrowserShots('An unconfirmed hierarchy edit does not reach the retained shot data');
 await page.locator('[data-hier-cancel]').first().click();checks+=2;
 await page.locator('[data-shot-add]').first().click();await page.locator('[data-shot-hierarchy-dialog]').waitFor();
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'','Image Bash requires no manual shot name');checks++;
 await addImageBash();
 await page.waitForFunction(()=>Boolean(window.host.image_bash_workspace?.workspace_id));
 assert.equal(await page.locator('[data-shot-panel]').count(),5);
 assert.equal(await workspace().count(),1);
 assert.equal(await workspace().locator('[data-image-bash-tab] b').innerText(),'HMBImageBash');checks++;
 assert.equal(await workspace().locator('[data-image-bash-tab] i').innerText(),'REMOTE','Expanded Bash row uses the same remote-source marker as Shot rows');
 assert.equal(await page.locator('[data-library-compact-summary] [data-image-bash-tab] i').innerText(),'REMOTE','Compact Bash row retains the remote-source marker');checks+=2;
 assert.equal(await page.locator('[data-library-compact-summary] [data-image-bash-panel]').count(),1,'Compact view retains the same separate workspace');checks++;
 assert.equal(await page.locator('[data-shot-panel][data-shot-number="6"]').count(),0);
 assert.equal(await page.evaluate(()=>window.createRequests.length),1,'Only the explicit add issues a node-creation request');checks+=4;
 const afterAdd=await page.evaluate(()=>structuredClone(window.host));assertShotsUntouched(afterAdd,'Browser explicit Image Bash addition leaves five shot states untouched');
 const createRequest=await page.evaluate(()=>window.createRequests[0]);
 assert.deepEqual(Object.keys(createRequest).sort(),['schema','version','operation','request_id','workspace_id','expected_revision'].sort());
 assert.equal(createRequest.schema,'hmb-image-bash-workspace-edit-v1');assert.equal(createRequest.operation,'create');
 assert.equal(createRequest.workspace_id,afterAdd.image_bash_workspace.workspace_id);assert.equal(createRequest.expected_revision,0);checks+=5;
 assert.equal(afterAdd.image_bash_active,true);
 await expanded.locator('[data-asset-key="catalog-6"] [data-asset-add]').click();
 await page.locator('[data-registration-field="image_name"]').fill('Keep my registration draft');
 assert.equal(await page.locator('[data-registration-submit]').isDisabled(),true,'Registration metadata can remain incomplete');
 assert.equal(await page.locator('[data-registration-bash-add]').isEnabled(),true,'An external user import can be added to Bash before project registration');checks+=2;
 if(report){fs.mkdirSync(report,{recursive:true});await page.screenshot({path:path.join(report,'image-bash-unregistered-import-passport-synthetic.png')});}
 await page.evaluate(()=>{window.deferNext=true;});await page.locator('[data-registration-bash-add]').click();
 await page.waitForFunction(()=>Boolean(window.pendingPublication));
 assert.equal(await page.locator('[data-registration-backdrop]').count(),1,'The passport stays open until selection is accepted');
 assert.equal(await page.locator('[data-registration-bash-add]').isDisabled(),true,'A pending selection cannot be submitted twice');checks+=2;
 await page.evaluate(()=>window.finishPublication(false));
 await page.waitForFunction(()=>!document.querySelector('[data-registration-bash-add]').disabled);
 assert.equal(await page.locator('[data-registration-field="image_name"]').inputValue(),'Keep my registration draft');
 assert.equal(await page.evaluate(()=>document.getElementById('widget').__hmbImageAssetLatestState.image_bash_workspace.instances.length),0,'Rejected selection restores the previous workspace');checks+=2;
 // A late failure belongs to its old operation. Cancelling and opening a
 // different passport must never resurrect or overwrite the old draft.
 await page.evaluate(()=>{window.deferNext=true;});await page.locator('[data-registration-bash-add]').click();
 await page.waitForFunction(()=>Boolean(window.pendingPublication));await page.locator('[data-registration-cancel]').first().click();
 await expanded.locator('[data-asset-key="catalog-7"] [data-asset-add]').click();
 await page.locator('[data-registration-field="image_name"]').fill('Newer draft stays here');
 await page.evaluate(()=>window.finishPublication(false));
 assert.equal(await page.locator('[data-registration-field="image_name"]').inputValue(),'Newer draft stays here');
 assert.equal(await page.evaluate(()=>document.getElementById('widget').__hmbImageAssetRegistrationDraft.source_uid),'source-7');
 assert.equal(await page.evaluate(()=>document.getElementById('widget').__hmbImageAssetLatestState.image_bash_workspace.instances.length),0,'Late failure rolls back only its workspace selection after a view-only remount');checks+=3;
 await page.locator('[data-registration-cancel]').first().click();
 await expanded.locator('[data-asset-key="catalog-6"] [data-asset-add]').click();await page.locator('[data-registration-bash-add]').click();
 await page.waitForFunction(()=>window.host.image_bash_workspace.instances.length===1&&!document.querySelector('[data-registration-backdrop]'));
 assert.equal(await page.evaluate(()=>window.host.assets.find(asset=>asset.source_uid==='source-6').registered),false);
 assert.equal(await page.evaluate(()=>window.host.assets.find(asset=>asset.source_uid==='source-6').selected),false);
 assert.equal(await page.evaluate(()=>window.writes.some(raw=>Boolean((raw.edits||raw).asset_registration_request?.request_id))),false,'Bash selection never publishes a registration or JSON-write command');checks+=3;
 await assertBrowserShots('Pre-registration user import enters Bash without changing any Shot or asset registration');
 for(const source of ['catalog-7','catalog-6']){
  const before=await page.evaluate(()=>window.host.image_bash_workspace.instances.length);
  await expanded.locator(`[data-asset-key="${source}"]`).press('Enter');
  await page.waitForFunction(count=>window.host.image_bash_workspace.instances.length===count,before+1);
 }
 const uiInstances=await page.evaluate(()=>structuredClone(window.host.image_bash_workspace.instances));
 assert.deepEqual(uiInstances.map(row=>row.source_uid),['source-6','source-7','source-6']);
 assert.equal(new Set(uiInstances.map(row=>row.instance_id)).size,3);
 assert.equal(await workspace().locator('[data-image-bash-instance]').count(),3);checks+=4;
 await assertBrowserShots('Repeated library clicks add independent Bash instances without toggling shot selections');
 await workspace().locator(`[data-image-bash-duplicate="${uiInstances[0].instance_id}"]`).click();
 await page.waitForFunction(()=>window.host.image_bash_workspace.instances.length===4);
 const duplicated=await page.evaluate(()=>structuredClone(window.host.image_bash_workspace.instances));
 assert.equal(duplicated[0].instance_id,uiInstances[0].instance_id);
 assert.equal(duplicated[1].source_uid,uiInstances[0].source_uid);assert.notEqual(duplicated[1].instance_id,duplicated[0].instance_id);checks+=3;
 const indexedThumbnails=await page.evaluate(()=>{
  const host=document.getElementById('widget'),state=host.__hmbImageAssetLatestState;
  const target='catalog-6',cards=[...host.querySelectorAll('[data-image-bash-asset-key="catalog-6"]')];
  const indexed=host.__hmbImageAssetBashCardsByLibraryId?.get(target)||[];
  const unrelated=[...host.querySelectorAll('[data-image-bash-asset-key="catalog-7"]')].map(card=>card.innerHTML);
  const sameIndex=indexed.length===cards.length&&cards.every(card=>indexed.includes(card));
  const asset=host.__hmbImageAssetByLibraryId.get(target);asset.thumbnail_url+='#indexed-completion';
  const query=host.querySelectorAll;let rootQueries=0;
  host.querySelectorAll=()=>{rootQueries++;throw Error('Thumbnail completion scanned the root');};
  let patched;try{patched=window.w.hmbPatchImageAssetThumbnailMedia(host,state,[target]);}finally{host.querySelectorAll=query;}
  return {sameIndex,count:cards.length,patched,rootQueries,
   updated:cards.every(card=>card.querySelector('img')?.getAttribute('src')===asset.thumbnail_url),
   unrelated:unrelated.every((html,index)=>host.querySelectorAll('[data-image-bash-asset-key="catalog-7"]')[index].innerHTML===html)};
 });
 assert.equal(indexedThumbnails.sameIndex,true);assert.ok(indexedThumbnails.count>=3);
 assert.ok(indexedThumbnails.patched>=indexedThumbnails.count);assert.equal(indexedThumbnails.rootQueries,0);
 assert.equal(indexedThumbnails.updated,true);assert.equal(indexedThumbnails.unrelated,true);checks+=6;
 const drag=async(from,to)=>page.evaluate(({from,to})=>{
  const root=document.querySelector('[data-library-expanded]'),source=root.querySelector(`[data-image-bash-instance="${from}"]`),target=root.querySelector(`[data-image-bash-instance="${to}"]`),dataTransfer=new DataTransfer();
  source.dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer}));
  target.dispatchEvent(new DragEvent('dragover',{bubbles:true,cancelable:true,dataTransfer}));
  target.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer}));
  source.dispatchEvent(new DragEvent('dragend',{bubbles:true,dataTransfer}));
 },{from,to});
 await drag(uiInstances[2].instance_id,uiInstances[0].instance_id);
 await page.waitForFunction(id=>window.host.image_bash_workspace.instances[0].instance_id===id,uiInstances[2].instance_id);
 assert.deepEqual(await workspace().locator('[data-image-bash-instance]').evaluateAll(nodes=>nodes.map(node=>node.dataset.imageBashInstance)),
  await page.evaluate(()=>window.host.image_bash_workspace.instances.map(row=>row.instance_id)),'Drag order and persisted instance order agree');checks++;
 await workspace().locator(`[data-image-bash-remove="${duplicated[1].instance_id}"]`).click();
 await page.waitForFunction(()=>window.host.image_bash_workspace.instances.length===3);
 assert.equal(await page.evaluate(id=>window.host.image_bash_workspace.instances.some(row=>row.instance_id===id),duplicated[1].instance_id),false);checks++;
 await assertBrowserShots('Bash duplicate, remove and drag do not disturb the five shot routes');
 const workspaceBeforePages=await page.evaluate(()=>structuredClone(window.host.image_bash_workspace));
 // Include returning to the already-active shot: it still must exit Bash view
 // even when the underlying Shot active UUID requires no change.
 for(const index of [2,0,4,1,3,2]){
  const shot=initial.shot_routing.shots[index];
  await expanded.locator(`[data-shot-tab="${shot.shot_uuid}"]`).click();
  await page.waitForFunction(id=>!window.host.image_bash_active&&window.host.shot_routing.active_shot_uuid===id,shot.shot_uuid);
  const shotView=await browserSnapshot();
  assert.deepEqual(shotView.image_bash_workspace,workspaceBeforePages);
  assert.deepEqual(shotView.shot_routing.shots,baseline.shot_routing.shots);
  assert.equal(shotView.shot_routing.generation,baseline.shot_routing.generation);
  await expanded.locator('[data-image-bash-tab]').click();
  await page.waitForFunction(()=>window.host.image_bash_active);
  assert.deepEqual(await page.evaluate(()=>window.host.image_bash_workspace),workspaceBeforePages);checks+=4;
 }
 await assertBrowserShots('All five pages and return to original shot preserve names, inputs, bindings and media receipts');
 assert.equal(await page.evaluate(()=>window.createRequests.length),1,'Editing and switching pages never replay node creation');checks++;
 const browserSaved=await page.evaluate(()=>JSON.stringify(window.host));
 await page.evaluate(value=>window.openGraph(JSON.parse(value)),browserSaved);
 assert.deepEqual(await page.evaluate(()=>window.host.image_bash_workspace),workspaceBeforePages);
 assert.equal(await page.evaluate(()=>window.host.image_bash_active),true);
 assert.equal(await workspace().locator('[data-image-bash-instance]').count(),3);
 assert.equal(await page.evaluate(()=>window.createRequests.length),1,'Cold reopen does not issue a new node-creation command');checks+=4;
 await assertBrowserShots('Browser save and cold reopen retain the five-shot state');
 const staleSaved=JSON.parse(browserSaved);
 staleSaved.image_bash_workspace_request={...createRequest,request_id:randomUUID(),expected_revision:workspaceBeforePages.revision};
 await page.evaluate(value=>window.openGraph(value),staleSaved);
 await expanded.locator(`[data-shot-tab="${initial.shot_routing.active_shot_uuid}"]`).click();
 await expanded.locator('[data-image-bash-tab]').click();
 assert.equal(await page.evaluate(()=>window.createRequests.length),1,'A historical create command in a saved workflow is discarded before normal page changes');
 assert.deepEqual(await page.evaluate(()=>window.host.image_bash_workspace_request),{});
 assert.deepEqual(await page.evaluate(()=>window.host.image_bash_workspace),workspaceBeforePages);checks+=3;
 await page.evaluate(command=>{window.host.image_bash_workspace_request=command;window.controller.update(window.props());},staleSaved.image_bash_workspace_request);
 await page.locator('[data-language-toggle]').click();await page.locator('[data-language-toggle]').click();
 assert.equal(await page.evaluate(()=>window.createRequests.length),1,'A stale command arriving in a later props update cannot replay during an unrelated language change');
 assert.deepEqual(await page.evaluate(()=>window.host.image_bash_workspace_request),{});checks+=2;
 await assertBrowserShots('Discarding stale creation commands preserves every existing shot and media receipt');
 // A synchronous canonical echo must also preserve the workspace and clear
 // its one-shot create command before unrelated later publications.
 await page.evaluate(()=>{window.syncEcho=true;});
 await page.locator('[data-shot-add]').first().click();await addImageBash();
 await page.waitForFunction(()=>window.createRequests.length===2);
 assert.equal(await page.evaluate(()=>window.host.image_bash_workspace.workspace_id),workspaceBeforePages.workspace_id,'Explicit re-add addresses the existing workspace identity');
 await expanded.locator(`[data-shot-tab="${initial.shot_routing.active_shot_uuid}"]`).click();
 await expanded.locator('[data-image-bash-tab]').click();
 assert.equal(await page.evaluate(()=>window.createRequests.length),2,'Synchronous host echo cannot leak create command into a page switch');checks+=2;
 await assertBrowserShots('Explicit existing-workspace re-add leaves all original shot data intact');
 const finalWorkspaceSaved=await browserSnapshot();
 // The shared card coordinator has the same async/view-only remount boundary
 // as the passport action and must restore just the rejected workspace edit.
 await page.evaluate(()=>{window.deferNext=true;});await expanded.locator('[data-asset-key="catalog-6"]').press('Enter');
 await page.waitForFunction(()=>Boolean(window.pendingPublication));
 await expanded.locator('[data-asset-key="catalog-7"] [data-asset-add]').click();
 await page.locator('[data-registration-field="image_name"]').fill('Card failure keeps this draft');
 await page.evaluate(()=>window.finishPublication(false));
 assert.equal(await page.locator('[data-registration-field="image_name"]').inputValue(),'Card failure keeps this draft');
 assert.deepEqual(await page.evaluate(()=>document.getElementById('widget').__hmbImageAssetLatestState.image_bash_workspace),finalWorkspaceSaved.image_bash_workspace);
 await page.locator('[data-registration-cancel]').first().click();checks+=2;
 await page.evaluate(()=>{window.deferNext=true;});await expanded.locator('[data-asset-key="catalog-6"]').press('Enter');
 await page.waitForFunction(()=>Boolean(window.pendingPublication));
 await expanded.locator('[data-asset-key="catalog-7"]').press('Enter');
 const newerWorkspace=await page.evaluate(()=>structuredClone(window.host.image_bash_workspace));
 await page.evaluate(()=>window.finishPublication(false));
 assert.deepEqual(await page.evaluate(()=>window.host.image_bash_workspace),newerWorkspace);
 assert.deepEqual(await page.evaluate(()=>document.getElementById('widget').__hmbImageAssetLatestState.image_bash_workspace),newerWorkspace,'A late rejected card edit cannot overwrite a newer accepted workspace edit');checks+=2;
 await page.evaluate(value=>window.openGraph(value),finalWorkspaceSaved);
 const fullWorkspace=structuredClone(finalWorkspaceSaved);
 fullWorkspace.image_bash_workspace.instances=Array.from({length:50},()=>({instance_id:randomUUID(),source_uid:'source-6'}));
 fullWorkspace.image_bash_workspace.revision++;
 await page.evaluate(value=>window.openGraph(value),fullWorkspace);
 await expanded.locator('[data-asset-key="catalog-6"] [data-asset-add]').click();
 assert.equal(await page.locator('[data-registration-bash-add]').isDisabled(),true,'Passport Bash selection respects the 50-instance capacity');
 const beforeFull=await page.evaluate(()=>window.writes.length);await page.locator('[data-registration-bash-add]').dispatchEvent('click');
 assert.equal(await page.evaluate(()=>window.writes.length),beforeFull,'A forged capacity-full click cannot publish a selection');checks+=2;
 await page.locator('[data-registration-cancel]').first().click();
 await page.evaluate(value=>window.openGraph(value),finalWorkspaceSaved);
 await expanded.locator('[data-asset-key="catalog-6"] [data-asset-add]').click();
 await page.evaluate(()=>{window.disabled=true;window.controller.update(window.props());});
 assert.equal(await page.locator('[data-registration-bash-add]').isDisabled(),true);
 const beforeLocked=await page.evaluate(()=>window.writes.length);await page.locator('[data-registration-bash-add]').dispatchEvent('click');
 assert.equal(await page.evaluate(()=>window.writes.length),beforeLocked,'The passport action obeys the host editing lock');checks+=2;
 await page.evaluate(()=>{window.disabled=false;window.controller.update(window.props());});
 await page.locator('[data-registration-cancel]').first().click();
 await expanded.locator('[data-asset-key="catalog-6"] [data-asset-add]').click();
 await page.evaluate(()=>{window.host.image_bash_active=false;window.controller.update(window.props());});
 const beforeModeChange=await page.evaluate(()=>window.writes.length);await page.locator('[data-registration-bash-add]').click();
 assert.equal(await page.evaluate(()=>window.writes.length),beforeModeChange,'The passport revalidates a deferred mode change before adding an image');
 assert.equal(await page.locator('[data-registration-bash-add]').count(),0);
 assert.deepEqual(await page.evaluate(()=>document.getElementById('widget').__hmbImageAssetLatestState.image_bash_workspace),finalWorkspaceSaved.image_bash_workspace);checks+=3;
 await page.locator('[data-registration-cancel]').first().click();
 await page.evaluate(value=>window.openGraph(value),finalWorkspaceSaved);
 assert.equal(await page.evaluate(()=>window.writes.some(raw=>Boolean((raw.edits||raw).asset_registration_request?.request_id))),false,'All pre-registration Bash paths issue zero registration/JSON-write commands');checks++;
 await assertBrowserShots('Capacity, lock and late-failure checks retain every original Shot');
 await page.evaluate(()=>window.controller.cleanup());
 assert.equal(await page.evaluate(()=>document.getElementById('widget').__hmbImageAssetBashCardsByLibraryId===undefined),true,'Cleanup retires the Bash thumbnail card index');checks++;
 await page.evaluate(value=>window.openGraph(value),finalWorkspaceSaved);
 assert.deepEqual(errors,[]);checks++;
 const evidence={status:'PASS',checks,scope:'actual ImageAsset widget in offline Chrome; synthetic host edit/node-creation boundary',
  shot_count:5,paid_requests:0,live_engine_requests:0,installed_files_changed:0};
 if(report){fs.mkdirSync(report,{recursive:true});fs.writeFileSync(path.join(report,'image-bash-workspace-widget.json'),JSON.stringify(evidence,null,2));await page.screenshot({path:path.join(report,'image-bash-workspace-widget.png')});}
 console.log(JSON.stringify(evidence));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
