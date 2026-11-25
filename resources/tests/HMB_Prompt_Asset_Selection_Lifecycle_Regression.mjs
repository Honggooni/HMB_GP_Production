import { listenBrowserSafeLoopback } from "./_hmb_browser_loopback.mjs";
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url);
let playwright;try{playwright=require("playwright");}catch{playwright=require(path.join(os.homedir(),".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"));}
const source=fs.readFileSync(new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js",import.meta.url),"utf8");
const channel="11111111-1111-4111-8111-111111111111";
const shots=Array.from({length:5},(_,i)=>({channel_uuid:channel,shot_uuid:`22222222-2222-4222-8222-${String(i+1).padStart(12,"0")}`,number:i+1,name:`asset_${i+1}`,selected_source_uids:[]}));
const row=(uid,label,main="Character",sub="Full Appearance")=>({slot:1,present:true,label,asset_source_uid:uid,asset_library_id:uid,asset_source_kind:"project",asset_managed:true,asset_verified:true,image_main_type:main,image_sub_type:sub,owner:label,color_picks:[uid.includes("background")?"Green":"Red"],binding_video_slots:[1]});
const fixture={multi_shot_enabled:true,shot:shots[0],images:[row("project:hero","Hero")],videos:[{slot:1,label:"Mask",present:true,manual:true}],source_sync_revision:1,ui_edit_revision:0,
 image_asset:{enabled:true,project_id:"superwings12",selected_assets:1,order_managed:true,ordered_source_uids:["project:hero"],shot_catalog:shots,shot_catalog_routing:{publisher_instance_uuid:channel,channel_uuid:channel,generation:1,metadata_sha256:"a".repeat(64)}}};
const html=`<!doctype html><meta charset="utf-8"><main class="react-flow"><div class="react-flow__node" data-id="Asset"><div id="asset-widget"></div></div><div class="react-flow__edge" aria-label="Edge from Asset to Prompt" data-id="xy-edge__AssetSHOT_ASSET_OUT-PromptSHOT_ASSET_IN"></div><div id="shell" class="react-flow__node" data-id="Prompt" style="width:980px;height:620px"><div style="height:96px">Native header</div><div id="host"></div></div></main><script type="module">
import mount,* as widget from '/widget.js';window.widget=widget;window.latest=widget.normalizeState(${JSON.stringify(fixture)});window.writes=0;
window.props=value=>({value:JSON.stringify(value),disabled:false,onChange(next){window.latest=JSON.parse(next);window.writes++;window.controller.update(window.props(window.latest));}});
window.controller=mount(document.getElementById('host'),window.props(window.latest));window.ready=true;
window.accept=raw=>{window.latest=widget.normalizeState(raw);window.controller.update(window.props(window.latest));};
window.preview=(revision,rows,cancelled=false)=>{
 const detail={schema:'hmb-shot-media-selection-preview-v1',kind:'image_asset',scope:'shot',
   publisher_instance_uuid:window.latest.shot.channel_uuid,channel_uuid:window.latest.shot.channel_uuid,
   shot_uuid:window.latest.shot.shot_uuid,revision,rows,cancelled};
 document.getElementById('asset-widget').dispatchEvent(new CustomEvent(detail.schema,{detail,bubbles:true,composed:true}));
};
window.sourceUpdate=(images,advance=1)=>{
 const state=structuredClone(window.latest);
 state.source_sync_revision+=advance;
 state.image_asset.shot_catalog_routing.generation+=advance;
 state.image_asset.shot_catalog_routing.metadata_sha256=String(state.source_sync_revision).padStart(64,'a');
 state.images=images;
 Object.assign(state.image_asset,{enabled:true,order_managed:true,selected_assets:images.length,verified_assets:images.length,
   ordered_source_uids:images.map(item=>item.asset_source_uid)});
 state.shot.selected_source_uids=[...state.image_asset.ordered_source_uids];
 return state;
};
</script>`;
const server=http.createServer((req,res)=>{res.setHeader("Content-Type",req.url==="/widget.js"?"text/javascript; charset=utf-8":"text/html; charset=utf-8");res.end(req.url==="/widget.js"?source:html);});
await listenBrowserSafeLoopback(server);
const browser=await playwright.chromium.launch({executablePath:process.env.HMB_PROMPT_TEST_BROWSER||"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",headless:true});
let external=0;const failures=[];
try{
 const page=await browser.newPage({viewport:{width:1900,height:1700},hasTouch:true});page.setDefaultTimeout(5000);
 await page.route("**/*",route=>{if(new URL(route.request().url()).hostname!=="127.0.0.1"){external++;return route.abort();}return route.continue();});
 // CI browser/document startup has a separate budget; UI actions stay at 5s.
 page.on('pageerror',error=>failures.push(error.message));await page.goto(`http://127.0.0.1:${server.address().port}`,{timeout:30000});await page.waitForFunction(()=>window.ready,null,{timeout:30000});
 const labels=()=>page.locator('.source-row.image .source-label-input').evaluateAll(inputs=>inputs.map(input=>input.value));
 const waitForLabels=async(expected)=>{
  await page.waitForFunction(names=>{
   const inputs=document.querySelectorAll('.source-row.image .source-label-input');
   return !document.getElementById('host').__hmbPromptLibrarySourcePropsApply
     && inputs.length===names.length && names.every((name,i)=>inputs[i].value===name);
  },expected);
 };
 const accepted=async(images,{deferDelivery=false}={})=>{
  await page.evaluate(({images,deferDelivery})=>{
   const next=window.sourceUpdate(images);
   if (!deferDelivery) { window.accept(next); return; }
   // Model a busy host delivering its authoritative envelope after several paints.
   let remaining=4;
   const deliver=()=>{ if (--remaining>0) requestAnimationFrame(deliver); else window.accept(next); };
   requestAnimationFrame(deliver);
  },{images,deferDelivery});
  await waitForLabels(images.map(image=>image.label));
 };
 assert.deepEqual(await labels(),['Hero']);
 // Keep the current UUID/editor while real source rows are added, deselected,
 // reordered and changed. The original bug discarded staged group sections.
 const editor=await page.evaluate(()=>{window.originalEditor=document.querySelector('.center');return true;});assert.equal(editor,true);
 const expected=[row('project:hero','Hero'),row('project:background','Background','Environment / Background','Main Background')];
 await accepted(expected);
 assert.deepEqual(await labels(),['Hero','Background'],'New selected assets must repaint the existing manager body.');
 const visibleLabels=()=>page.locator('.source-row.image .source-label-input:visible').evaluateAll(inputs=>inputs.map(input=>input.value));
 const heading=page.locator('.image-card h3 b');
 const pending=page.locator('[data-hmb-image-selection-pending]');
 const writesBeforePreview=await page.evaluate(()=>window.writes);
 await page.evaluate(()=>window.preview(1,[{source_uid:'project:hero',label:'Hero'}]));
 assert.deepEqual(await visibleLabels(),['Hero']);
 assert.equal(await heading.textContent(),'1 / 50');
 await page.evaluate(()=>window.preview(2,[{source_uid:'project:hero',label:'Hero'},{source_uid:'project:titan',label:'Titan'}]));
 assert.match(await pending.innerText(),/Titan/);
 assert.equal(await heading.textContent(),'2 / 50');
 await page.evaluate(()=>{window.preview(3,[]);window.preview(2,[{source_uid:'project:titan',label:'Titan'}]);});
 assert.deepEqual(await visibleLabels(),[]);
 assert.equal(await pending.count(),0);
 assert.equal(await heading.textContent(),'0 / 50');
 assert.equal(await page.evaluate(()=>window.writes),writesBeforePreview,'Immediate display must not submit a Prompt edit.');
 await page.evaluate(()=>window.preview(4,[],true));
 assert.deepEqual(await visibleLabels(),['Hero','Background']);
 const crossed=await page.evaluate(async images=>{
  const host=document.getElementById('host');
  const schedule=host.__hmbPromptLibraryScheduleFrame;
  const frames=[];
  const prior=window.latest;
  const writes=window.writes;
  const late=window.sourceUpdate([images[0]]);
  const newest=window.sourceUpdate([...images].reverse(),2);
  window.widget.hmbScheduleImmediateStateCommit(host,window.props(prior),prior,{reconcileOnly:true});
  // Hold the next paint beyond the passive acknowledgement deadline.
  host.__hmbPromptLibraryScheduleFrame=callback=>frames.push(callback);
  try {
   window.accept(newest);
   window.controller.update(window.props(late));
   await new Promise(done=>setTimeout(done,320));
   return {staleWrites:window.writes-writes,keys:newest.images.map(item=>window.widget.hmbPromptSourceIdentity(item,'image'))};
  } finally {
   host.__hmbPromptLibraryScheduleFrame=schedule;
   while(frames.length) frames.shift()();
  }
 },expected);
 assert.equal(crossed.staleWrites,0,'A pending paint for the newer catalog must suppress the former catalog’s passive publication.');
 await waitForLabels(['Background','Hero']);
 assert.deepEqual(await labels(),['Background','Hero'],'A late older delivery in the same frame must not undo the new order.');
 assert.deepEqual(await page.locator('.source-row.image[data-source-key]').evaluateAll(rows=>rows.map(row=>row.dataset.sourceKey)),crossed.keys);
 assert.equal(await page.evaluate(()=>window.latest.shot.shot_uuid),shots[0].shot_uuid);
 assert.equal(await page.evaluate(()=>window.originalEditor===document.querySelector('.center')),true);
 await accepted([expected[1]],{deferDelivery:true});assert.deepEqual(await labels(),['Background'],'Deselection removes the old row from this UUID.');
 await accepted([expected[1],expected[0]]);assert.deepEqual(await labels(),['Background','Hero'],'Upstream image order controls row order.');
 assert.deepEqual(await page.locator('.image-main-type-cell select').evaluateAll(inputs=>inputs.map(input=>input.value)),['Environment / Background','Character']);
 const canonicalRows=()=>page.evaluate(()=>({uids:[...document.querySelectorAll('.source-row.image[data-source-key]')].map(row=>row.getAttribute('data-source-key')),
  expectedUids:window.latest.images.map(item=>window.widget.hmbPromptSourceIdentity(item,'image')),
  subtype:[...document.querySelectorAll('.source-row.image [data-field="image_sub_type"]')].map(input=>input.value),
  expectedSubtype:window.latest.images.map(item=>item.image_sub_type),
  targets:[...document.querySelectorAll('.source-row.image [data-field="owner"]')].map(input=>input.value),
  expectedTargets:window.latest.images.map(item=>item.owner),
  colors:[...document.querySelectorAll('.source-row.image [data-field="color_picks"]')].map(input=>input.value),
  expectedColors:window.latest.images.flatMap(item=>item.color_picks)}));
 let rendered=await canonicalRows();assert.deepEqual(rendered.uids,rendered.expectedUids);assert.deepEqual(rendered.subtype,rendered.expectedSubtype);assert.deepEqual(rendered.colors,rendered.expectedColors);
 assert.deepEqual(rendered.colors,['Green','Red']);assert.deepEqual(rendered.targets,['Background','Hero']);
 await page.locator('.source-row.image [data-field="owner"]').last().focus();
 await page.evaluate(()=>{window.focusedAssetTarget=document.activeElement;window.focusedAssetKey=document.activeElement.closest('.source-row').getAttribute('data-source-key');});
 await accepted([expected[0],expected[1]]);
 assert.deepEqual(await labels(),['Hero','Background']);
 assert.deepEqual(await page.evaluate(()=>({same:document.activeElement===window.focusedAssetTarget,key:document.activeElement.closest('.source-row').getAttribute('data-source-key'),expected:window.focusedAssetKey,index:document.activeElement.closest('.source-row').getAttribute('data-index')})),
  {same:true,key:await page.evaluate(()=>window.focusedAssetKey),expected:await page.evaluate(()=>window.focusedAssetKey),index:'0'},'Image-target focus follows the source UID, never its old row index.');
 rendered=await canonicalRows();assert.deepEqual(rendered.colors,['Red','Green']);assert.deepEqual(rendered.targets,['Hero','Background']);
 await accepted([expected[1],expected[0]]);
 const choose=async(index)=>{await page.locator(`[data-prompt-shot="${shots[index].shot_uuid}"]`).tap();await page.waitForFunction(uuid=>window.latest.shot.shot_uuid===uuid,shots[index].shot_uuid);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));};
 const perShot=new Map([[0,['Background','Hero']]]);
 for(let index=1;index<5;index++){
  await choose(index);const selected=[row('project:actor-'+index,'Selected actor '+index),row('project:scene-'+index,'Selected scene '+index,'Environment / Background','Main Background')];
  await accepted(selected);perShot.set(index,selected.map(item=>item.label));assert.deepEqual(await labels(),perShot.get(index));
  rendered=await canonicalRows();assert.deepEqual(rendered.uids,rendered.expectedUids);assert.deepEqual(rendered.subtype,rendered.expectedSubtype);
 }
 for(let index=4;index>=0;index--){await choose(index);await waitForLabels(perShot.get(index));assert.deepEqual(await labels(),perShot.get(index),'Selection is bound to the stable Shot UUID, including revisiting dormant documents.');}
 // An unrelated Shot number/name change must patch only the tabs and preserve
 // this selected UUID's rows and literal user inputs.
 const identityBefore=await page.evaluate(()=>({uuid:window.latest.shot.shot_uuid,body:document.querySelector('.center')}));
 await page.evaluate(()=>{window.beforeRenumberBody=document.querySelector('.center');const next=structuredClone(window.latest);next.source_sync_revision++;next.image_asset.shot_catalog_routing.generation++;next.image_asset.shot_catalog_routing.metadata_sha256='c'.repeat(64);[next.image_asset.shot_catalog[3].number,next.image_asset.shot_catalog[4].number]=[5,4];next.image_asset.shot_catalog[4].name='renamed unrelated';window.accept(next);});
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))));
 assert.deepEqual(await labels(),['Background','Hero']);assert.equal(await page.evaluate(()=>window.beforeRenumberBody===document.querySelector('.center')),true);
 assert.equal(await page.evaluate(()=>window.latest.shot.shot_uuid),identityBefore.uuid);
 // Source changes cannot drop a concurrent local prompt draft or its caret.
 const text=page.locator('[data-text-key]').first();await text.focus();
 await text.evaluate(input=>{input.value='한글 현재 본문 {literal}';input.dispatchEvent(new InputEvent('input',{bubbles:true,data:'한글'}));input.setSelectionRange(3,5);});
 await accepted([row('project:new','New selected actor')]);
 assert.deepEqual(await labels(),['New selected actor']);assert.equal(await text.inputValue(),'한글 현재 본문 {literal}');
 const selection=await text.evaluate(input=>({focused:document.activeElement===input,start:input.selectionStart,end:input.selectionEnd}));assert.deepEqual(selection,{focused:true,start:3,end:5});
 // A delayed old source state cannot restore earlier selected rows.
 const before=await page.evaluate(()=>structuredClone(window.latest));
 await page.evaluate(()=>{const old=structuredClone(window.latest);old.source_sync_revision=1;old.ui_edit_revision=0;old.images=[];window.controller.update(window.props(old));});
 assert.deepEqual(await labels(),['New selected actor']);
 const recoveryMerge=await page.evaluate(()=>{
  const source=structuredClone(window.latest);window.widget.hmbSwitchPromptShot(source,source.image_asset.shot_catalog.find(shot=>shot.number===2).shot_uuid);
  const key=Object.keys(source.text)[0];source.text[key]='restored target UUID body';source.images[0].owner='Target UUID owner';source.images[0].color_picks=['Blue'];
  const unbound=structuredClone(source);unbound.shot={};unbound.image_asset.shot_catalog=[];unbound.image_asset.shot_catalog_routing={};unbound.text[key]='old unbound body';unbound.images[0].owner='Wrong unbound owner';unbound.images[0].color_picks=['Red'];
  source.source_sync_revision++;const merged=window.widget.hmbMergePromptRevisionAxes(source,unbound);
  const dirtyContainer={},control=document.createElement('textarea');control.setAttribute('data-text-key',key);control.value='pending old unbound draft';
  window.widget.hmbRememberPromptDirtyTextControl(dirtyContainer,control,unbound);
  const dirty=window.widget.hmbMergePromptDirtyTextState(merged,dirtyContainer.__hmbPromptLibraryDirtyText);
  const savedUnbound=JSON.parse(dirty.shot_documents.__unbound__);
  const valid=structuredClone(source);window.widget.hmbSwitchPromptShot(valid,valid.image_asset.shot_catalog.find(shot=>shot.number===3).shot_uuid);valid.text[key]='valid concurrent third body';valid.ui_edit_revision++;
  const crossed=window.widget.hmbMergePromptRevisionAxes(source,valid);
  const foreign=structuredClone(valid);foreign.shot.channel_uuid='99999999-9999-4999-8999-999999999999';foreign.text[key]='foreign body';
  const rejected=window.widget.hmbMergePromptRevisionAxes(source,foreign);
  return {text:merged.text[key],owner:merged.images[0].owner,color:merged.images[0].color_picks[0],dirtyVisible:dirty.text[key],dirtyArchived:savedUnbound.text[key],
   crossedText:crossed.text[key],crossedUuid:crossed.shot.shot_uuid,expectedUuid:valid.shot.shot_uuid,foreignShot:rejected.shot,expectedShot:source.shot,foreignText:rejected.text[key]};
 });
 assert.equal(recoveryMerge.text,'restored target UUID body');assert.equal(recoveryMerge.owner,'Target UUID owner');assert.equal(recoveryMerge.color,'Blue');
 assert.equal(recoveryMerge.dirtyVisible,'restored target UUID body');assert.equal(recoveryMerge.dirtyArchived,'pending old unbound draft');
 assert.equal(recoveryMerge.crossedText,'valid concurrent third body');assert.equal(recoveryMerge.crossedUuid,recoveryMerge.expectedUuid);
 assert.deepEqual(recoveryMerge.foreignShot,recoveryMerge.expectedShot);assert.equal(recoveryMerge.foreignText,'restored target UUID body');
 // A native source-deletion archive is newer than the accepted UI's
 // dormant copy of the active body. Per-document clocks must decide this,
 // independently of the outer source/UI state clocks.
 const archivedMerge=await page.evaluate(()=>{
  const ui=structuredClone(window.latest),uuid=ui.shot.shot_uuid,key=window.widget.hmbPromptDocumentKey(ui.shot);
  ui.images[0].color_picks=['Red'];ui.ui_edit_revision=0;window.widget.hmbStorePromptShotDocument(ui);
  ui.images[0].color_picks=['Blue'];ui.ui_edit_revision=5;
  const source=structuredClone(ui);window.widget.hmbStorePromptShotDocument(source);source.shot={};source.image_asset.shot_catalog=[];source.image_asset.shot_catalog_routing={};source.source_sync_revision++;
  const merged=window.widget.hmbMergePromptRevisionAxes(source,ui);
  const newerUi=structuredClone(ui),newerDoc=JSON.parse(newerUi.shot_documents[key]);newerDoc.ui_edit_revision=6;newerDoc.images[0].color_picks=['Green'];newerUi.shot_documents[key]=JSON.stringify(newerDoc);
  const fresh=window.widget.hmbMergePromptRevisionAxes(source,newerUi);
  return {archived:JSON.parse(merged.shot_documents[key]).images[0].color_picks,newer:JSON.parse(fresh.shot_documents[key]).images[0].color_picks};
 });
 assert.deepEqual(archivedMerge,{archived:['Blue'],newer:['Green']},'A fresh deletion archive wins over stale UI JSON; a newer dormant UI edit still wins.');
 // A lifecycle-restored Color Pick is an authored revision, not an old
 // source-only echo. The real retained controller must paint that revision
 // while a still-newer user choice wins a crossed source acknowledgement.
 await page.evaluate(()=>{const missing=structuredClone(window.latest);missing.source_sync_revision++;missing.ui_edit_revision++;missing.images[0].color_picks=[''];window.accept(missing);});
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 assert.equal(await page.locator('.source-row.image [data-field="color_picks"]').first().inputValue(),'');
 await page.evaluate(()=>{const restored=structuredClone(window.latest);restored.source_sync_revision++;restored.ui_edit_revision++;restored.images[0].color_picks=['Red'];window.restoreAck=structuredClone(restored);window.accept(restored);});
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 assert.equal(await page.locator('.source-row.image [data-field="color_picks"]').first().inputValue(),'Red','The old empty UI projection cannot erase a validated authored restoration.');
 await page.evaluate(()=>{const edited=structuredClone(window.latest);edited.ui_edit_revision++;edited.images[0].color_picks=['Green'];window.accept(edited);const older=structuredClone(window.restoreAck);older.source_sync_revision=edited.source_sync_revision+1;window.accept(older);});
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 assert.equal(await page.locator('.source-row.image [data-field="color_picks"]').first().inputValue(),'Green','A newer local Color Pick wins a crossed older restoration ACK.');
 // Reusing the host for another workflow starts a new publisher clock. One
 // delayed delivery of the old workflow is still queued in this same frame.
 await page.evaluate(({fixture,replacementRow})=>{
  const old=window.sourceUpdate(window.latest.images,2);
  const oldProps=window.props(old);
  window.controller.update(oldProps);
  const next=structuredClone(fixture);
  const owner='77777777-7777-4777-8777-777777777777';
  next.shot={...next.shot,channel_uuid:owner,selected_source_uids:[replacementRow.asset_source_uid]};
  next.image_asset.shot_catalog=[next.shot];
  next.image_asset.shot_catalog_routing={publisher_instance_uuid:owner,channel_uuid:owner,generation:1,metadata_sha256:'7'.repeat(64)};
  next.image_asset.ordered_source_uids=[replacementRow.asset_source_uid];
  next.images=[replacementRow];
  next.text={SCENE_CONTEXT:'Replacement workflow'};
  window.latest=window.widget.normalizeState(next);
  window.replacementWrites=[];
  const newProps=window.props(window.latest);
  newProps.onChange=value=>{window.replacementWrites.push(JSON.parse(value));};
  window.controller.update(newProps);
  window.controller.update(oldProps);
 },{fixture,replacementRow:row('project:replacement','Replacement')});
 await waitForLabels(['Replacement']);
 assert.deepEqual(await labels(),['Replacement']);
 const replacementText=page.locator('textarea[data-text-key="SCENE_CONTEXT"]');
 const replacementStyle=page.locator('textarea[data-text-key="PROJECT_STYLE_LOOK"]');
 assert.equal(await replacementStyle.inputValue(),'','A replacement workflow cannot inherit the former workflow’s focused text.');
 assert.equal(await replacementText.inputValue(),'Replacement workflow');
 await replacementText.focus();
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))));
 assert.equal(await replacementText.evaluate(field=>field===document.activeElement),true,'Deferred caret restoration respects the field selected in the replacement workflow.');
 await page.keyboard.press('ControlOrMeta+a');
 await page.keyboard.insertText('New workspace edit');
 await replacementText.press('Tab');
 await page.waitForFunction(()=>window.replacementWrites.some(state=>state.text.SCENE_CONTEXT==='New workspace edit'));
 assert.equal(await page.evaluate(()=>window.replacementWrites.at(-1).text.PROJECT_STYLE_LOOK),'');
 assert.equal(await page.evaluate(()=>window.replacementWrites.at(-1).shot.channel_uuid),'77777777-7777-4777-8777-777777777777');
 assert.deepEqual(await page.evaluate(()=>Object.keys(window.replacementWrites.at(-1).shot_documents)
   .filter(key=>key.includes('11111111-1111-4111-8111-111111111111'))),[]);
 // All semantic updates retain one body and one instance of each section.
 assert.equal(await page.locator('.center').count(),1);
 assert.deepEqual(await page.locator('[data-group-id]').evaluateAll(groups=>groups.map(group=>group.dataset.groupId)),['imageSources','imageText','videoSources','soundSources','videoText']);
 for (const multiShot of [false,true]) {
  await page.evaluate(multi=>{
   const next=structuredClone(window.replacementWrites.at(-1));
   next.multi_shot_enabled=multi;
   next.source_sync_revision+=multi?2:1;
   window.accept(next);
  },multiShot);
  await page.waitForFunction(multi=>{
   const layouts=document.querySelectorAll('.hmb-dashboard .layout');
   return layouts.length===1 && Boolean(layouts[0].closest('.prompt-shot-list'))===multi;
  },multiShot);
  assert.equal(await replacementText.inputValue(),'New workspace edit');
 }
 const externalImage={...row('import:dingo','Dingo'),asset_source_kind:'user',asset_verified:false,
  asset_last_source_path:'{inputs}/images/Dingo.jpg',color_picks:['Mint']};
 const connected=[row('project:replacement','Replacement'),externalImage];
 await page.evaluate(()=>{window.latest.ui.language='ko';});
 await accepted(connected);
 const missing=[connected[0],{...externalImage,asset_source_unavailable:true}];
 const brokenRow=page.locator('.source-row.image.image-source-missing');
 await accepted(missing);
 await brokenRow.waitFor();
 assert.equal(await brokenRow.locator('[data-field="image_main_type"]').inputValue(),'Character');
 assert.equal(await brokenRow.locator('[data-field="image_sub_type"]').inputValue(),'Full Appearance');
 assert.equal(await brokenRow.locator('[data-field="owner"]').inputValue(),'Dingo');
 assert.equal(await brokenRow.locator('[data-field="color_picks"]').inputValue(),'Mint');
 assert.match(await brokenRow.innerText(),/소스 끊김/);
 assert.match(await brokenRow.innerText(),/\{inputs\}\/images\/Dingo\.jpg/);
 assert.equal(await page.locator('[data-group-id="imageSources"] h3 b').textContent(),'1 / 50');
 await accepted(connected);
 await brokenRow.waitFor({state:'detached'});
 assert.equal(await page.locator('[data-group-id="imageSources"] h3 b').textContent(),'2 / 50');
 await accepted(missing);
 await brokenRow.locator('.clear-source').click();
 await waitForLabels(['Replacement']);
 await page.waitForFunction(()=>!window.latest.images.some(image=>image.asset_source_uid==='import:dingo'));
 assert.equal(await replacementText.inputValue(),'New workspace edit');
 assert.equal(external,0);assert.deepEqual(failures,[]);
 console.log('HMB Prompt Asset selection lifecycle: PASS (same UUID add/remove/reorder, UID/Main/Sub/Color and five documents repaint; unrelated renumber retains UUID/body; one retained editor; Korean draft/caret and stale-echo guard; external0)');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
