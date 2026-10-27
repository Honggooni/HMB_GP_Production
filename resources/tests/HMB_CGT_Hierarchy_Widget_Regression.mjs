// Actual product widgets with a synthetic CGT read/confirmation boundary.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {randomUUID} from 'node:crypto';
import * as w from '../../widgets/HMBImageAssetLibraryWidget.js';

const require=createRequire(import.meta.url);
const playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const browserPath=process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe';
const report=process.env.HMB_CGT_REPORT_DIR;
if(report)fs.mkdirSync(report,{recursive:true});
// Actual product Chrome measurements captured immediately before the static
// guidance removal. This fixture records the outer geometry, not inner copy.
const emptyDialogGeometryBaseline=[
 {width:1250,height:1000,zoom:1,scale:.55,rect:{x:125,y:159,width:1000,height:682}},
 {width:900,height:720,zoom:.8,scale:.7,rect:{x:27,y:19,width:846,height:682}},
 {width:600,height:850,zoom:1,scale:.55,rect:{x:18,y:12,width:564,height:826}},
 {width:1250,height:1000,zoom:1.25,scale:1.1,rect:{x:125,y:159,width:1000,height:682}},
];
if(report)fs.writeFileSync(path.join(report,'cgt-dialog-empty-geometry-baseline.json'),JSON.stringify({
 scope:'Actual product widget in synthetic offline Chrome fixture',captured_before_static_guidance_removal:true,
 test:'HMB_CGT_Hierarchy_Widget_Regression.mjs',cases:emptyDialogGeometryBaseline,
},null,2));
const initial=w.hmbNormalizeImageAssetState({project_root:'C:/fixture/superwings12',project_id:'superwings12',project_uid:'fixture-project'});
const account=randomUUID().toUpperCase(),pipeline=randomUUID().toUpperCase(),projectId=randomUUID().toUpperCase();
const tasks=Array.from({length:6},(_,i)=>{
 const id=randomUUID().toUpperCase();return {task_id:id,identity:{entity_id:randomUUID().toUpperCase(),task_id:id,pipeline_id:pipeline},
  source_name:`e201s${String(i+69).padStart(3,'0')}c001__`,episode:'e201',pipeline_id:pipeline,artist:'Synthetic Artist',status:'Work'};
});
for(const [sourceName,episode] of [['e201s080c001__','CGT Special Episode'],['e202s001c001__',undefined],['CGT Unassigned Shot',undefined]]){
 const id=randomUUID().toUpperCase();tasks.push({task_id:id,identity:{entity_id:randomUUID().toUpperCase(),task_id:id,pipeline_id:pipeline},
  source_name:sourceName,...(episode===undefined?{}:{episode}),pipeline_id:pipeline,artist:'Synthetic Artist',status:'Work'});
}
const expectedNames=['e201_s069c001-s070c001__','e201_s070c001-s071c001__','e201s071c001__','e201_s072c001-s073c001__','e201s073c001__'];
const snapshot={schema:'hmb-cgt-own-tasks',version:1,status:'ready',origin:'https://192.168.200.18:8383',
 account_id:account,account:'fixture-login',account_name:'Synthetic Artist',project:{id:projectId,entity:'superwings12',name:'Synthetic SW12',database:'proj_fixture_sw12',status:'Active'},tasks,
 projects:[{id:projectId,entity:'superwings12',name:'Synthetic SW12',database:'proj_fixture_sw12',status:'Active'},
  {id:randomUUID().toUpperCase(),entity:'Katuri8',name:'Synthetic Katuri8',database:'proj_fixture_katuri8',status:'Active'}],
 can_bind:true,tls_verified:true,hostname_verified:true};
const html=`<!doctype html><html><body style="background:#101420;margin:0"><div id="widget"></div><div id="bridge"></div><script type="module">
import mount,* as w from '/widget.js';import bridgeMount from '/bridge.js';
window.w=w;window.host=w.hmbNormalizeImageAssetState(${JSON.stringify(initial)});window.catalog=${JSON.stringify(snapshot)};
window.requests=[];window.commits=[];window.localWrites=[];window.pending=null;window.rejected=false;window.syncEcho=false;
window.finish=()=>{const req=window.pending;if(!req)return;window.pending=null;let state=structuredClone(window.catalog),outcome='ready';
 if(req.operation==='cgt_catalog'&&state.status==='ready'){
  if(req.cgt_project_id){const selected=state.projects.find(item=>item.id===req.cgt_project_id);
   if(selected){state.project=selected;state.can_bind=Boolean(req.project_identity)&&selected.entity==='superwings12';
    if(!state.can_bind)state.tasks=[{...state.tasks[0],source_name:'e301s001c001__'}].filter(item=>item.task_id);}}
  else if(!req.project_identity){state.project=null;state.tasks=[];state.can_bind=false;}}
 if(req.operation==='cgt_confirm'){
  if(window.rejected){state={status:'SOURCE_CHANGED'};outcome='rejected';}
  else{window.host=w.hmbNormalizeImageAssetState(w.hmbApplyShotHierarchyEdit(window.host,req.hierarchy_request));
   window.commits.push(structuredClone(req.hierarchy_request));outcome='committed';state={status:'committed'};window.controller.update(window.props());}}
 window.bridgeController.update({value:{...req,phase:'result',state,outcome},onChange:window.dispatch});};
window.dispatch=req=>{window.requests.push(structuredClone(req));if(req.operation==='cgt_cancel')window.pending=null;else window.pending=req;};
window.props=()=>({value:JSON.stringify(window.host),onChange:value=>{
 const raw=JSON.parse(value);if(raw.__hmb_manifest_poll_nonce)return;
 const edit=raw.edits||raw,req=edit.shot_hierarchy_request;
 if(req?.schema){
  const cgtRows=binding=>(binding?.members||[]).filter(row=>row.origin==='cgt');
  if(JSON.stringify(cgtRows(req.binding))!==JSON.stringify(cgtRows(window.host.shot_hierarchy)))throw new Error('CGT confirmation bypassed server validation');
  window.host=w.hmbNormalizeImageAssetState(w.hmbApplyShotHierarchyEdit(window.host,req));
 }else window.host=w.hmbNormalizeImageAssetState({...window.host,...edit});
 window.host.ui_edit_revision=raw.ui_edit_revision;window.localWrites.push(structuredClone(edit));
 if(window.syncEcho){window.host.scan_revision+=17;window.host.manifest_signature='canonical-sync-scan';window.controller.update(window.props());}
 else queueMicrotask(()=>window.controller.update(window.props()));
}});
window.openGraph=value=>{window.controller?.cleanup();window.bridgeController?.cleanup();window.host=w.hmbNormalizeImageAssetState(value);
 window.bridgeController=bridgeMount(document.getElementById('bridge'),{value:{schema:'hmb-image-asset-thumbnail-bridge',version:1,runtime_instance_id:window.host.shot_routing.publisher_instance_uuid},onChange:window.dispatch});
 window.controller=mount(document.getElementById('widget'),window.props());};window.ready=true;
</script></body></html>`;
const source=fs.readFileSync(new URL('../../widgets/HMBImageAssetLibraryWidget.js',import.meta.url),'utf8');
const bridge=fs.readFileSync(new URL('../../widgets/HMBImageAssetThumbnailPatchBridgeWidget.js',import.meta.url),'utf8');
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:req.url==='/bridge.js'?bridge:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser,checks=0;
try{
 browser=await playwright.chromium.launch({executablePath:browserPath,headless:true});
 const page=await browser.newPage({viewport:{width:1250,height:1000}}),errors=[];page.setDefaultTimeout(5000);page.on('pageerror',error=>errors.push(error.message));
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
 const assertConciseDialog=async label=>{
  const text=await page.locator('[data-shot-hierarchy-dialog]').innerText();
  for(const removed of ['대표와 하위 모두 독립적으로 실행됩니다.','확정 전에는 기존 샷이 바뀌지 않습니다.',
   '수동 이름을 입력하고 연결할 샷 슬롯을 선택하세요.','연결을 해제해도 기존 샷·입력·결과는 보존됩니다.',
   '수동 입력은 연결 상태와 관계없이 사용할 수 있습니다.','CGT 배정·작업 상태는 변경하지 않습니다.',
   '총 실행 슬롯은 기존 샷을 포함해 최대 5개입니다.','같은 s의 c 항목도 개별 ID·실행 슬롯을 유지합니다.',
   '단일 이름은 그대로 유지합니다.','묶음은 e201_s112c001-s113c002__ 형식이며','128자를 넘으면 확정할 수 없습니다.']){
   assert.ok(!text.includes(removed),`${label}: removed static guidance does not reappear: ${removed}`);
  }
  assert.equal(await page.locator('.hier-body > p').evaluateAll(nodes=>nodes.some(node=>node.textContent.trim().startsWith('프로젝트:'))),false,`${label}: duplicate GP project banner is removed`);
  assert.equal(await page.locator('[data-hier-drag-handle] h2').innerText(),'CGT 샷 선택 · 묶음 구성');
  assert.equal(await page.locator('[data-hier-name-preview] h3').innerText(),'예상 네이밍');
  assert.match(await page.locator('.hier-manual').innerText(),/기존 슬롯을 선택하면 UUID·미디어·설정·결과를 보존하고 이름만 적용합니다\./,`${label}: unmarked manual-slot identity help remains`);
  assert.match(await page.locator('[data-shot-hierarchy-dialog] footer > span').innerText(),/\d개 대표 · \d개 하위/);
  assert.equal(await page.locator('[data-hier-confirm]').count(),1);assert.equal(await page.locator('[data-hier-cancel]').count(),2);
  checks+=18;
 };
 const noProject=await page.evaluate(()=>window.w.hmbNormalizeImageAssetState({}));
 await page.evaluate(value=>window.openGraph(value),noProject);
 const noProjectSlot=noProject.shot_routing.shots[0].shot_uuid;
 await page.locator('[data-shot-add]').click();
 await page.locator('[data-shot-hierarchy-dialog]').waitFor();
 await assertConciseDialog('Empty manual draft');
 const emptySpacing=await page.locator('[data-shot-hierarchy-dialog]').evaluate(dialog=>{
  const list=dialog.querySelector('[data-hier-selected-scroll]'),preview=dialog.querySelector('[data-hier-name-preview]'),manual=dialog.querySelector('.hier-manual'),status=dialog.querySelector('[data-hier-cgt-status]');
  return {listDisplay:getComputedStyle(list).display,listHeight:list.getBoundingClientRect().height,
   manualGap:manual.getBoundingClientRect().top-preview.getBoundingClientRect().bottom,
   statusPaddingTop:parseFloat(getComputedStyle(status).paddingTop),statusPaddingBottom:parseFloat(getComputedStyle(status).paddingBottom),
   manualTitleMargin:getComputedStyle(manual.querySelector('h3')).marginBottom};
 });
 assert.equal(emptySpacing.listDisplay,'none','Empty selected-list strip takes no space');
 assert.equal(emptySpacing.listHeight,0);assert.ok(emptySpacing.manualGap<=12,'Manual controls follow the preview without an empty list band');
 assert.ok(emptySpacing.statusPaddingTop<=6&&emptySpacing.statusPaddingBottom<=6,'CGT status keeps its message with compact vertical padding');
 assert.equal(emptySpacing.manualTitleMargin,'0px');checks+=5;
 if(report)await page.screenshot({path:path.join(report,'cgt-compact-empty-dialog-synthetic.png')});
 assert.equal(await page.locator('[data-hier-message]').innerText(),'');
 assert.equal(await page.evaluate(()=>window.requests.filter(req=>req.operation==='cgt_catalog').length),1,'CGT project discovery does not require a GP project');
 assert.equal(await page.locator('[data-hier-cgt-refresh]').isDisabled(),true,'A pending catalog request cannot be duplicated');
 await page.evaluate(()=>window.finish());
 assert.match(await page.locator('[data-hier-cgt-status]').innerText(),/프로젝트.*선택|선택.*프로젝트/);
 assert.equal(await page.locator('[data-hier-cgt-project]').isEnabled(),true);
 const actualProjectLabels=await page.locator('[data-hier-cgt-project] option').allTextContents();
 assert.ok(actualProjectLabels.some(label=>label.includes('Synthetic SW12'))&&actualProjectLabels.some(label=>label.includes('Synthetic Katuri8')),'Actual CGT projects populate the selector');
 await page.locator('[data-hier-cgt-project]').selectOption(snapshot.projects[1].id);
 await page.waitForFunction(id=>window.pending?.cgt_project_id===id,snapshot.projects[1].id);
 assert.equal(await page.locator('[data-hier-cgt-refresh]').isDisabled(),true);
 await page.evaluate(()=>window.finish());
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),1,'CGT tasks can be browsed without attaching them to another GP project');
 assert.equal(await page.locator('[data-hier-cgt-add]').isDisabled(),true,'Browse-only tasks cannot overwrite the current GP shots');
 await page.locator('[data-hier-manual-name]').fill('Manual only');
 await page.locator('[data-hier-slot]').selectOption(noProjectSlot);
 await page.locator('[data-hier-add]').click();
 assert.equal(await page.locator('[data-hier-member]').count(),1);
 assert.equal(await page.locator('[data-hier-name]').inputValue(),'Manual only');
 assert.equal(await page.locator('[data-hier-confirm]').isEnabled(),true);
 if(report)await page.screenshot({path:path.join(report,'cgt-no-project-manual-synthetic.png')});
 // Editing an existing row commits on the first Confirm click. Blur/change
 // must not replace the button before that click reaches its handler.
 await page.locator('[data-hier-name]').fill('Manual confirm once');
 await page.evaluate(()=>{window.syncEcho=true;});
 await page.locator('[data-hier-confirm]').click();
 await page.waitForFunction(()=>window.localWrites.length===1);
 assert.equal(await page.locator('[data-shot-hierarchy-dialog]').count(),0);
 assert.equal(await page.locator('[data-shot-name]').first().innerText(),'Manual confirm once');
 assert.deepEqual(await page.evaluate(()=>{const latest=document.getElementById('widget').__hmbImageAssetLatestState;return {scan:latest.scan_revision,manifest:latest.manifest_signature,hostScan:window.host.scan_revision};}),
  {scan:17,manifest:'canonical-sync-scan',hostScan:17},'Synchronous canonical host scan is never overwritten by optimistic UI state');
 await page.evaluate(()=>{window.syncEcho=false;});
 checks+=2;
 // The pencil edits a manually authored shot inline, never opens selection.
 await page.locator('[data-shot-rename]').first().click();
 assert.equal(await page.locator('[data-shot-hierarchy-dialog]').count(),0);
 await page.locator('[data-shot-rename-input]').fill('Manual renamed');
 await page.locator('[data-shot-rename-input]').press('Enter');
 await page.waitForFunction(()=>window.host.shot_routing.shots[0].name==='Manual renamed');
 assert.equal(await page.locator('[data-shot-name]').first().innerText(),'Manual renamed');
 const manualSaved=await page.evaluate(()=>JSON.stringify(window.host));
 await page.evaluate(value=>window.openGraph(JSON.parse(value)),manualSaved);
 assert.equal(await page.locator('[data-shot-name]').first().innerText(),'Manual renamed');
 assert.equal(await page.locator('[data-shot-rename]').first().isEnabled(),true);
 checks+=20;
 // The actual product dialog is a viewport portal. A panned/scaled node and
 // browser CSS zoom cannot anchor it to the node's top-left corner.
 const assertDialogCentered=async label=>{
  const box=await page.locator('[data-shot-hierarchy-dialog]').boundingBox();
  const view=await page.evaluate(()=>({width:innerWidth,height:innerHeight,
   directRect:document.querySelector('[data-shot-hierarchy-dialog]').getBoundingClientRect().toJSON(),visualWidth:visualViewport.width,visualHeight:visualViewport.height}));
  const geometry=JSON.stringify({box,view});
  assert.ok(Math.abs(box.x+box.width/2-view.width/2)<=2,`${label}: horizontal viewport center ${geometry}`);
  assert.ok(Math.abs(box.y+box.height/2-view.height/2)<=2,`${label}: vertical viewport center ${geometry}`);
  assert.ok(box.x>=-1&&box.y>=-1&&box.x+box.width<=view.width+1&&box.y+box.height<=view.height+1,`${label}: full dialog remains in viewport`);
  const footer=await page.locator('[data-hier-confirm]').boundingBox();
  assert.ok(footer.y>=0&&footer.y+footer.height<=view.height+1,`${label}: confirmation remains visible without scrolling the entire page`);
  return box;
 };
 const assertCompactSelectedRows=async label=>{
  await assertConciseDialog(label);
  assert.equal(await page.locator('[data-hier-parent]').count(),5,`${label}: every shot exposes its own parent selection`);
  const roleHeaders=await page.locator('[data-hier-member]').evaluateAll(nodes=>nodes.map(node=>{
   const title=node.querySelector('b').getBoundingClientRect(),select=node.querySelector('[data-hier-parent]').getBoundingClientRect(),row=node.getBoundingClientRect();
   return {title:{left:title.left,right:title.right,center:title.y+title.height/2},select:{left:select.left,right:select.right,center:select.y+select.height/2,width:select.width},row:{left:row.left,right:row.right}};
  }));
  assert.ok(roleHeaders.every(row=>Math.abs(row.title.center-row.select.center)<3&&row.title.right<=row.select.left+1&&row.select.right<=row.row.right+1&&row.select.width>=30),`${label}: role selector shares the compact card-title line without overlap`);
  const catalogControls=await page.locator('.hier-project-tools').evaluate(node=>{
   const items=['[data-hier-cgt-project]','[data-hier-cgt-episode]','[data-hier-cgt-refresh]'].map(selector=>node.querySelector(selector).getBoundingClientRect());
   const box=node.getBoundingClientRect();return {items:items.map(item=>({left:item.left,right:item.right,top:item.top,width:item.width})),box:{left:box.left,right:box.right}};
  });
  assert.ok(catalogControls.items.every((item,index)=>Math.abs(item.top-catalogControls.items[0].top)<2&&item.width>=30&&item.left>=catalogControls.box.left-1&&item.right<=catalogControls.box.right+1&&(index===0||catalogControls.items[index-1].right<=item.left)),`${label}: project, episode and refresh remain aligned and non-overlapping`);
  assert.equal(await page.locator('[data-hier-member] .hier-output').count(),0,`${label}: duplicate per-row execution names remain removed`);
  const rows=await page.locator('[data-hier-name-tools]').evaluateAll(nodes=>nodes.map(node=>{
   const input=node.querySelector('[data-hier-name]').getBoundingClientRect(),button=node.querySelector('[data-hier-remove]').getBoundingClientRect();
   return {input:{left:input.left,right:input.right,top:input.top,bottom:input.bottom,width:input.width},button:{left:button.left,right:button.right,top:button.top,bottom:button.bottom}};
  }));
  assert.equal(rows.length,5,`${label}: all five rows retain their name and detach controls`);
  assert.ok(rows.every(row=>Math.abs(row.input.bottom-row.button.bottom)<2&&row.input.right<=row.button.left&&row.input.width>=30),`${label}: name input and detach button share one non-overlapping line`);
  const preview=await page.locator('[data-hier-name-preview]').evaluate(node=>{
   const title=node.querySelector('h3').getBoundingClientRect(),values=node.querySelector('[data-hier-name-values]'),box=values.getBoundingClientRect();
   return {titleY:title.y+title.height/2,valuesY:box.y+box.height/2,overflow:getComputedStyle(values).overflowX,
    nowrap:getComputedStyle(values).flexWrap,clientHeight:values.clientHeight,scrollHeight:values.scrollHeight,
    items:[...values.querySelectorAll('.hier-output')].map(item=>({text:item.textContent,title:item.title,y:item.getBoundingClientRect().y+item.getBoundingClientRect().height/2}))};
  });
  assert.equal(preview.items.length,5,`${label}: preview retains every execution name`);
  assert.ok(Math.abs(preview.titleY-preview.valuesY)<4&&preview.items.every(item=>Math.abs(item.y-preview.valuesY)<3),`${label}: title and all expected names stay on one line`);
  assert.ok(['auto','scroll'].includes(preview.overflow)&&preview.nowrap==='nowrap'&&preview.scrollHeight<=preview.clientHeight+1,`${label}: expected names scroll horizontally without wrapping`);
  assert.ok(preview.items.every(item=>item.title===item.text&&item.title.length>0),`${label}: complete execution names remain available by tooltip`);
  const scrolled=await page.locator('[data-hier-name-values]').evaluate(node=>{
   const before=node.scrollLeft;node.scrollLeft=node.scrollWidth;
   const box=node.getBoundingClientRect(),last=node.lastElementChild.getBoundingClientRect();
   const result={moved:node.scrollLeft,right:last.right,edge:box.right};node.scrollLeft=before;return result;
  });
  assert.ok(scrolled.moved>0&&scrolled.right<=scrolled.edge+2,`${label}: horizontal scrolling actually reveals the fifth complete name`);
  checks+=11;
 };
 for(const size of emptyDialogGeometryBaseline){
  await page.setViewportSize({width:size.width,height:size.height});
  await page.evaluate(value=>{document.body.style.zoom=String(value.zoom);const widget=document.getElementById('widget');
   widget.style.transform='translate(280px,130px) scale('+value.scale+')';widget.style.transformOrigin='top left';
   window.openGraph(window.w.hmbNormalizeImageAssetState({}));document.querySelector('[data-shot-add]').click();},size);
  const box=await assertDialogCentered(`viewport ${size.width}x${size.height}, zoom ${size.zoom}, node scale ${size.scale}`);
  assert.ok(Object.keys(size.rect).every(key=>Math.abs(box[key]-size.rect[key])<1),`Static text removal preserves the recorded outer geometry ${JSON.stringify({expected:size.rect,actual:box})}`);
  assert.equal(await page.locator('[data-shot-hierarchy-dialog]').evaluate(node=>node.parentNode===document.body),true,'Dialog belongs to the viewport, not the scaled widget');
  const sourceBox=await page.locator('[data-hier-source-pane]').boundingBox(),selectedBox=await page.locator('[data-hier-selected-pane]').boundingBox();
  if(Math.abs(sourceBox.y-selectedBox.y)<2)assert.ok(sourceBox.x+sourceBox.width<=selectedBox.x+1,'Source task list is left, selected hierarchy is right');
  else assert.ok(sourceBox.y<selectedBox.y,'Narrow layout keeps source before selected hierarchy');
  await page.evaluate(()=>window.finish());
  const handle=await page.locator('[data-hier-drag-handle]').boundingBox();
  await page.evaluate(()=>{window.lastDragPointer=null;document.addEventListener('pointerdown',event=>{
   window.lastDragPointer={x:event.clientX,y:event.clientY,target:event.target.outerHTML?.slice(0,180),handle:Boolean(event.target.closest?.('[data-hier-drag-handle]'))};
  },{once:true,capture:true});});
  await page.mouse.move(handle.x+60,handle.y+20);await page.mouse.down();
  await page.mouse.move(handle.x+105,handle.y+35,{steps:5});await page.mouse.up();
  const dragged=await page.locator('[data-shot-hierarchy-dialog]').boundingBox();
  const dragPointer=await page.evaluate(()=>window.lastDragPointer);
  assert.ok(Math.abs(dragged.x-box.x)>5||Math.abs(dragged.y-box.y)>5,`Header drag still works after viewport centering and zoom ${JSON.stringify({size,box,handle,dragged,dragPointer})}`);
  await page.evaluate(()=>{window.host.scan_revision++;window.controller.update(window.props());});
  const retained=await page.locator('[data-shot-hierarchy-dialog]').boundingBox();
  assert.ok(Math.abs(retained.x-dragged.x)<1&&Math.abs(retained.y-dragged.y)<1,'A background host remount retains the dragged position');
  if(size.width===1250&&size.zoom===1){
   await page.setViewportSize({width:640,height:720});
   await page.waitForFunction(()=>{const r=document.querySelector('[data-shot-hierarchy-dialog]').getBoundingClientRect();
    return r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1;});
   const resizedFooter=await page.locator('[data-hier-confirm]').boundingBox();
   assert.ok(resizedFooter.y>=0&&resizedFooter.y+resizedFooter.height<=721,'Viewport resize clamps a previously dragged dialog and keeps confirmation reachable');
   await page.setViewportSize({width:size.width,height:size.height});checks+=2;
  }
  await page.keyboard.press('Escape');await page.evaluate(()=>document.querySelector('[data-shot-add]').click());
  const reopened=await assertDialogCentered('Fresh reopen resets to viewport center');
  assert.ok(Object.keys(size.rect).every(key=>Math.abs(reopened[key]-size.rect[key])<1),'Reopening preserves the same recorded empty-dialog geometry');
  await page.keyboard.press('Escape');checks+=13;
 }
 await page.evaluate(()=>{document.body.style.zoom='';const widget=document.getElementById('widget');widget.style.transform='';widget.style.transformOrigin='';});
 await page.setViewportSize({width:1250,height:1000});
 await page.evaluate(value=>window.openGraph(value),initial);
 const openShots=()=>page.locator('[data-shot-add]').first().click();
 await openShots();await page.waitForFunction(()=>window.pending?.operation==='cgt_catalog');
 await page.locator('[data-hier-manual-name]').fill('Preserved typing');
 const dialog=page.locator('[data-shot-hierarchy-dialog]');
 const beforeDrag=await dialog.boundingBox(),handle=await page.locator('[data-hier-drag-handle]').boundingBox();
 const dx=beforeDrag.x>90?-70:70,dy=beforeDrag.y>70?-45:45;
 await page.mouse.move(handle.x+Math.min(70,handle.width/3),handle.y+Math.min(20,handle.height/2));
 await page.mouse.down();await page.mouse.move(handle.x+Math.min(70,handle.width/3)+dx,handle.y+Math.min(20,handle.height/2)+dy,{steps:8});await page.mouse.up();
 const afterDrag=await dialog.boundingBox();
 assert.ok(Math.abs(afterDrag.x-beforeDrag.x)>20||Math.abs(afterDrag.y-beforeDrag.y)>20,'Dialog header drag moves the window');
 assert.ok(afterDrag.x>=-1&&afterDrag.y>=-1&&afterDrag.x+afterDrag.width<=1251&&afterDrag.y+afterDrag.height<=1001,'Dragged dialog remains on screen');
 await page.locator('[data-hier-manual-name]').click();
 const afterInputClick=await dialog.boundingBox();
 assert.ok(Math.abs(afterInputClick.x-afterDrag.x)<1&&Math.abs(afterInputClick.y-afterDrag.y)<1,'Input click never drags the dialog');
 await page.evaluate(()=>window.finish());
 checks+=3;
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'Preserved typing');
 assert.match(await page.locator('[data-hier-cgt-account]').innerText(),/fixture-login/);
 assert.equal(await page.locator('[data-hier-cgt-project]').inputValue(),projectId);
 assert.match(await page.locator('[data-hier-cgt-project] option:checked').innerText(),/Synthetic SW12/,'The selector shows the CGT catalog name, not a GP filesystem token');
 const projectBox=await page.locator('[data-hier-cgt-project]').boundingBox(),episodeBox=await page.locator('[data-hier-cgt-episode]').boundingBox(),refreshBox=await page.locator('[data-hier-cgt-refresh]').boundingBox();
 assert.ok(Math.abs(projectBox.y-refreshBox.y)<2&&Math.abs(projectBox.y-episodeBox.y)<2,'Project, episode and refresh controls align on one row');
 assert.ok(projectBox.x+projectBox.width<=episodeBox.x&&episodeBox.x+episodeBox.width<=refreshBox.x,'Episode selection fits beside the narrower project selector without overlap');
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),tasks.length);checks+=4;
 const episodeOptions=await page.locator('[data-hier-cgt-episode] option').evaluateAll(nodes=>nodes.map(node=>({value:node.value,text:node.textContent})));
 for(const value of ['', 'e201', 'CGT Special Episode', 'e202', '__unassigned__'])assert.ok(episodeOptions.some(option=>option.value===value),`Episode option is retained: ${value}`);
 assert.ok(episodeOptions.some(option=>option.value==='__unassigned__'&&option.text.includes('에피소드 미지정')));
 const beforeEpisodeRequests=await page.evaluate(()=>window.requests.length);
 for(const [value,taskIndex] of [['CGT Special Episode',6],['e202',7],['__unassigned__',8]]){
  await page.locator('[data-hier-cgt-episode]').selectOption(value);
  assert.equal(await page.locator('[data-hier-cgt-add]').count(),1);
  assert.equal(await page.locator(`[data-hier-cgt-add="${tasks[taskIndex].task_id}"]`).count(),1,'CGT episode is authoritative; missing values fall back to parsed names or unassigned');
 }
 await page.locator('[data-hier-cgt-episode]').selectOption('e201');
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),6,'Named CGT episode excludes a differently named CGT episode even when the shot code starts with e201');
 assert.equal(await page.evaluate(()=>window.requests.length),beforeEpisodeRequests,'Changing episode only filters the current authenticated catalog');
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'Preserved typing');checks+=15;
 await page.locator('[data-hier-cgt-project]').selectOption(snapshot.projects[1].id);
 assert.equal(await page.locator('[data-hier-cgt-refresh]').isDisabled(),true);
 await page.evaluate(()=>window.finish());
 assert.equal(await page.locator('[data-hier-cgt-episode]').inputValue(),'','Changing CGT project resets only the episode filter');
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),1);
 assert.equal(await page.locator('[data-hier-cgt-add]').isDisabled(),true,'A different CGT project can be browsed but cannot bind to the current GP project');
 assert.equal(await page.locator('[data-hier-member]').count(),0);
 await page.locator('[data-hier-cgt-project]').selectOption(projectId);await page.evaluate(()=>window.finish());
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),tasks.length);
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'Preserved typing','Project browse and refresh retain the separate manual draft');checks+=6;
 const beforeSlotRequests=await page.evaluate(()=>window.requests.length);
 await page.locator('[data-hier-slot]').selectOption('image_bash');
 assert.equal(await page.locator('[data-image-bash-add]').count(),0,'Image Bash uses the shared slot selector and add action');
 assert.equal(await page.locator('[data-hier-manual-name-field]').isVisible(),false);
 assert.equal(await page.locator('[data-hier-manual-name]').isDisabled(),true);
 assert.equal(await page.locator('[data-hier-add]').innerText(),'HMBImageBash 추가');
 assert.equal(await page.locator('[data-hier-cgt-add]').evaluateAll(buttons=>buttons.every(button=>button.disabled)),true,'CGT tasks cannot bind to the Image Bash workspace sentinel');
 assert.equal(await page.evaluate(()=>window.requests.length),beforeSlotRequests,'Changing the add target is local and does not refetch CGT');
 if(report)await page.screenshot({path:path.join(report,'cgt-image-bash-slot-synthetic.png')});
 await page.locator('[data-hier-cgt-add]').first().dispatchEvent('click');
 assert.equal(await page.locator('[data-hier-member]').count(),0,'The command handler also rejects a forged CGT click while Image Bash is selected');
 assert.match(await page.locator('[data-hier-message]').innerText(),/HMBImageBash/);checks+=2;
 await page.locator('[data-hier-slot]').selectOption('new');
 assert.equal(await page.locator('[data-hier-manual-name]').isVisible(),true);
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'Preserved typing');
 assert.equal(await page.locator('[data-hier-cgt-add]').evaluateAll(buttons=>buttons.every(button=>!button.disabled)),true,'Returning to a shot target restores actual task-selection eligibility');checks+=9;
 await page.locator('[data-hier-cgt-episode]').selectOption('e201');
 for(let i=0;i<5;i++){
  if(i===0)await page.locator('[data-hier-slot]').selectOption(initial.shot_routing.shots[0].shot_uuid);
  await page.locator(`[data-hier-cgt-add="${tasks[i].task_id}"]`).click();
  assert.equal(await page.locator('[data-hier-member]').count(),i+1);
  assert.equal(await page.locator(`[data-hier-cgt-add="${tasks[i].task_id}"]`).isDisabled(),true);
  if(i===1){
   const second=await page.locator('[data-hier-member]').nth(1).getAttribute('data-hier-member');
   await page.locator(`[data-hier-parent="${second}"]`).selectOption('cgt:'+tasks[0].task_id.toLowerCase());
   assert.match(await page.locator('[data-shot-hierarchy-dialog] footer > span').innerText(),/1개 대표 · 1개 하위/);
   assert.ok((await page.locator('[data-hier-name-preview]').innerText()).includes(expectedNames[0]),'Selecting 069 and 070 creates the requested bundle through real UI controls');checks+=2;
  }
  if(i===2){
   const third=await page.locator('[data-hier-member]').nth(2).getAttribute('data-hier-member');
   await page.locator(`[data-hier-parent="${third}"]`).selectOption('cgt:'+tasks[1].task_id.toLowerCase());
   assert.match(await page.locator('[data-shot-hierarchy-dialog] footer > span').innerText(),/2개 대표 · 2개 하위/);checks++;
  }
  if(i===4){
   const fifth=await page.locator('[data-hier-member]').nth(4).getAttribute('data-hier-member');
   await page.locator(`[data-hier-parent="${fifth}"]`).selectOption('cgt:'+tasks[3].task_id.toLowerCase());
  }
 }
 const keys=await page.locator('[data-hier-member]').evaluateAll(rows=>rows.map(row=>row.dataset.hierMember));
 assert.equal(await page.locator('[data-hier-name]').first().getAttribute('readonly'),'');
 await page.locator(`[data-hier-cgt-add="${tasks[5].task_id}"]`).click();
 assert.match(await page.locator('[data-hier-message]').innerText(),/5개/);assert.equal(await page.locator('[data-hier-member]').count(),5);
 assert.equal(await page.locator('[data-hier-parent]').count(),5,'Every selected shot can choose a representative');
 assert.equal(await page.locator(`[data-hier-parent="${keys[0]}"]`).isEnabled(),true,'Having children does not prevent a shot itself becoming a child');
 assert.equal(await page.locator(`[data-hier-parent="${keys[1]}"]`).isEnabled(),true,'070 remains both a child of 069 and a representative of 071');
 const firstParentOptions=await page.locator(`[data-hier-parent="${keys[0]}"] option`).evaluateAll(nodes=>nodes.map(node=>node.value));
 assert.ok(tasks.slice(0,3).every(task=>!firstParentOptions.includes('cgt:'+task.task_id.toLowerCase())),'Self and transitive descendants are excluded from parent choices');
 assert.ok(firstParentOptions.includes('cgt:'+tasks[4].task_id.toLowerCase()),'An unrelated child is an eligible parent when no cycle is introduced');
 assert.equal(await page.locator('[data-hier-member] .hier-output').count(),0,'Per-row execution-name repetition is removed');checks+=15;
 await assertCompactSelectedRows('Five newly selected CGT shots');
 const previewNames=await page.locator('[data-hier-name-preview]').innerText();
 assert.ok(expectedNames.every(name=>previewNames.includes(name)),'All five direct-child aggregate names are visible before confirmation');
 const retainedDraft=await page.locator('[data-hier-manual-name]').inputValue(),beforeFiltered=await page.evaluate(()=>window.requests.length);
 await page.locator('[data-hier-cgt-episode]').selectOption('e202');
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),1);
 assert.equal(await page.locator('[data-hier-member]').count(),5);
 assert.equal(await page.locator('[data-hier-name-preview]').innerText(),previewNames);
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),retainedDraft);
 assert.equal(await page.evaluate(()=>window.requests.length),beforeFiltered);checks+=10;
 await page.locator('[data-hier-cgt-project]').selectOption(snapshot.projects[1].id);await page.evaluate(()=>window.finish());
 assert.equal(await page.locator('[data-hier-member]').count(),5,'Browsing a second project never discards selected identities');
 if(report)await page.screenshot({path:path.join(report,'cgt-five-shots-synthetic.png')});
 await page.locator('[data-hier-confirm]').click();
 assert.equal(await page.locator('[data-hier-cancel]').first().isDisabled(),true);
 assert.equal(await page.evaluate(()=>window.host.shot_routing.shots.length),1);
 assert.equal(await page.evaluate(()=>window.pending.operation),'cgt_confirm');
 assert.equal(await page.evaluate(()=>window.pending.cgt_project_id),projectId,'Confirmation uses the selected binding project, never the currently browsed project');
 const sentMembers=await page.evaluate(()=>structuredClone(window.pending.hierarchy_request.binding.members));
 const parentValues=[null,'cgt:'+tasks[0].task_id.toLowerCase(),'cgt:'+tasks[1].task_id.toLowerCase(),null,'cgt:'+tasks[3].task_id.toLowerCase()];
 assert.deepEqual(sentMembers.map(row=>row.parent_id),parentValues,'CGT confirmation carries the exact user-selected multi-level tree');
 assert.deepEqual(sentMembers.map(row=>row.cgt_identity),tasks.slice(0,5).map(row=>row.identity),'Grouping preserves authenticated CGT IDs');
 assert.deepEqual(sentMembers.map(row=>row.source_name),tasks.slice(0,5).map(row=>row.source_name),'Grouping never edits CGT source names');
 await page.evaluate(()=>window.finish());await page.waitForFunction(()=>window.commits.length===1);
 assert.equal(await page.locator('[data-shot-hierarchy-dialog]').count(),0);
 // Persist the real user-driven confirmation, then remount it. A synthetic
 // parent_id injection is deliberately not used to create the tested tree.
 const saved=await page.evaluate(()=>JSON.stringify(window.host));
 const confirmed=JSON.parse(saved);
 assert.deepEqual(confirmed.shot_hierarchy.members,sentMembers);
 assert.equal(confirmed.shot_routing.shots.length,5);
 assert.equal(confirmed.shot_hierarchy.members[0].gp_shot_uuid,initial.shot_routing.shots[0].shot_uuid);
 assert.equal(new Set(confirmed.shot_hierarchy.members.map(row=>row.gp_shot_uuid)).size,5);
 await page.evaluate(value=>window.openGraph(JSON.parse(value)),saved);
 assert.deepEqual(await page.evaluate(()=>window.host.shot_hierarchy.members),sentMembers,'Cold widget remount retains every task, slot and parent identity');checks+=8;
 await openShots();await page.evaluate(()=>window.finish());
 assert.equal(await page.locator('.hier-child').count(),3,'Actual saved multi-level relationships remain visible');
 assert.equal(await page.locator(`[data-hier-remove="${keys[0]}"]`).isDisabled(),true,'A representative with children cannot be detached');
 assert.equal(await page.locator(`[data-hier-remove="${keys[1]}"]`).isDisabled(),true,'A child which also represents descendants cannot silently discard their parent');
 assert.equal(await page.locator(`[data-hier-remove="${keys[2]}"]`).isEnabled(),true,'A leaf child remains explicitly detachable');
 assert.equal(await page.locator(`[data-hier-parent="${keys[1]}"]`).inputValue(),parentValues[1]);
 assert.equal(await page.locator(`[data-hier-parent="${keys[2]}"]`).inputValue(),parentValues[2]);
 assert.match(await page.locator(`[data-hier-member="${keys[1]}"] b`).innerText(),/하위 · 대표/,'The combined role is visible, not only stored in the hierarchy');checks++;
 const groupedNames=await page.locator('[data-hier-name-preview]').innerText();
 assert.ok(expectedNames.every(name=>groupedNames.includes(name)),'Each parent, including a child/parent, displays only its direct-child execution name');
 await assertCompactSelectedRows('Saved CGT parent/child hierarchy');
 if(report)await page.screenshot({path:path.join(report,'cgt-multilevel-reopened-synthetic.png')});
 await page.setViewportSize({width:600,height:850});
 await assertCompactSelectedRows('Narrow saved CGT hierarchy');
 if(report)await page.screenshot({path:path.join(report,'cgt-multilevel-reopened-narrow-synthetic.png')});
 await page.setViewportSize({width:1250,height:1000});
 await page.locator('[data-hier-manual-name]').fill('Pending Bash target name');
 await page.locator('[data-hier-slot]').selectOption('image_bash');
 await page.locator(`[data-hier-parent="${keys[0]}"]`).selectOption('cgt:'+tasks[4].task_id.toLowerCase());
 assert.equal(await page.locator('[data-hier-slot]').inputValue(),'image_bash','A parent edit preserves the pending Image Bash target');
 assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'Pending Bash target name','A hidden pending name survives parent redraw');
 assert.equal(await page.locator('[data-hier-manual-name-field]').isVisible(),false,'Restored Image Bash target retains its matching visibility');
 assert.equal(await page.locator('[data-hier-manual-name]').isDisabled(),true);
 assert.equal(await page.locator('[data-hier-add]').innerText(),'HMBImageBash 추가');checks+=5;
 assert.match(await page.locator('[data-shot-hierarchy-dialog] footer > span').innerText(),/4개 대표 · 4개 하위/,'An existing root with children may become a child under an unrelated child');
 assert.equal(await page.evaluate(()=>window.commits.length),1,'Changing the draft parent does not commit or contact CGT');
 await page.keyboard.press('Escape');
 assert.equal(await page.evaluate(()=>JSON.stringify(window.host)),saved,'Viewing and cancelling a grouped save does not rewrite its parent relationships');checks+=5;
 assert.equal(JSON.parse(saved).shot_hierarchy.version,2);
 assert.equal(await page.locator('[data-shot-rename]:disabled').count(),5,'CGT-derived names cannot be edited with the pencil');
 assert.equal(await page.locator('[data-shot-add]').isEnabled(),true,'Full slot list still opens shot management');
 if(report)await page.locator('[data-shot-stack]').screenshot({path:path.join(report,'cgt-locked-names-header-synthetic.png')});
 const controls=await page.locator('[data-shot-panel]').first().locator('[data-shot-tab],[data-shot-rename],[data-shot-delete],[data-shot-add]').evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom};}));
 for(let a=0;a<controls.length;a++)for(let b=a+1;b<controls.length;b++){
  const x=Math.min(controls[a].right,controls[b].right)-Math.max(controls[a].left,controls[b].left);
  const y=Math.min(controls[a].bottom,controls[b].bottom)-Math.max(controls[a].top,controls[b].top);
  assert.ok(x<=0.5||y<=0.5,'Shot selector, pencil, delete, and add hit regions never overlap');
 }
 for(const width of [650,900]){
  await page.locator('#widget').evaluate((node,value)=>{node.style.width=value+'px';},width);
  const layout=await page.locator('[data-shot-panel]').first().evaluate(panel=>{
   const header=panel.querySelector('.shot-panel-head').getBoundingClientRect();
   const toggle=panel.querySelector('[data-shot-tab]'),box=toggle.getBoundingClientRect();
   return {header:{left:header.left,right:header.right},controls:[...panel.querySelectorAll('[data-shot-tab],[data-shot-rename],[data-shot-delete],[data-shot-add]')].map(node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right};}),
    contents:[...toggle.children].map(node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right};}),toggle:{left:box.left,right:box.right}};
  });
  assert.ok(layout.controls.every(r=>r.left>=layout.header.left-1&&r.right<=layout.header.right+1),'Every shot control remains inside its header');
  assert.ok(layout.contents.every(r=>r.left>=layout.toggle.left-1&&r.right<=layout.toggle.right+1),'Shot title/status never spill over pencil/delete/add');
 }
 await page.locator('#widget').evaluate(node=>{node.style.width='';});
 checks+=12;
 assert.deepEqual(JSON.parse(saved).shot_routing.shots.map(row=>row.name),expectedNames);checks+=6;
 // Cold reopen retains each task/slot identity; CGT is read afresh, never from
 // saved catalog presentation. A new account does not relabel old tasks.
 await page.evaluate(value=>window.openGraph(JSON.parse(value)),saved);
 await openShots();await page.evaluate(()=>{window.catalog.account_id='00000000-0000-4000-8000-000000000001';window.finish();});
 assert.match(await page.locator('[data-hier-cgt-status]').innerText(),/로그인 계정/);
 assert.equal(await page.locator('[data-hier-member]').count(),5);
 await page.keyboard.press('Escape');
 assert.equal(await page.evaluate(()=>JSON.stringify(window.host)),saved);checks+=3;
 await page.evaluate(value=>{window.catalog.account_id=value;window.rejected=true;},account);
 await openShots();await page.evaluate(()=>window.finish());
 await page.locator(`[data-hier-remove="${keys[2]}"]`).click();await page.locator('[data-hier-confirm]').click();
 await page.evaluate(()=>window.finish());assert.match(await page.locator('[data-hier-message]').innerText(),/적용하지 않았습니다/);
 assert.equal(await page.evaluate(()=>JSON.stringify(window.host)),saved);
 assert.equal(await page.evaluate(()=>window.commits.length),1);await page.keyboard.press('Escape');checks+=3;
 // Real empty list is visible as empty; TLS/auth failure cannot preserve a
 // different account's selectable rows. Closing retires the pending request.
 await openShots();await page.evaluate(()=>{window.catalog.tasks=[];window.finish();});
 assert.match(await page.locator('[data-hier-cgt-status]').innerText(),/배정된 AI_Shot 작업이 없습니다/);
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),0);
 await page.locator('[data-hier-cgt-refresh]').click();const stale=await page.evaluate(()=>structuredClone(window.pending));
 await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>window.pending),null);
 await openShots();await page.evaluate(value=>window.bridgeController.update({value:{...value,phase:'result',outcome:'ready',state:window.catalog},onChange:window.dispatch}),stale);
 assert.match(await page.locator('[data-hier-cgt-status]').innerText(),/조회 중/);
 await page.evaluate(()=>{window.catalog={status:'TLS_REJECTED',tasks:[]};window.finish();});
 assert.match(await page.locator('[data-hier-cgt-status]').innerText(),/인증서 검증/);checks+=5;
 await page.evaluate(value=>{window.catalog={...value,tasks:Array.from({length:120},(_,i)=>({...value.tasks[0],task_id:crypto.randomUUID(),source_name:`e201s${String(i+1).padStart(3,'0')}c001__`}))};},snapshot);
 await page.locator('[data-hier-cgt-refresh]').click();await page.evaluate(()=>window.finish());
 assert.equal(await page.locator('[data-hier-cgt-add]').count(),50);
 assert.equal(await page.locator('[data-hier-cgt-scroll]').evaluate(node=>['auto','scroll'].includes(getComputedStyle(node).overflowY)&&node.scrollHeight>node.clientHeight),true,'Task list has its own bounded scroll viewport');
 const requestsBefore=await page.evaluate(()=>window.requests.length);
 await page.locator('[data-hier-cgt-next]').click();assert.equal(await page.locator('[data-hier-cgt-add]').count(),50);
 await page.locator('[data-hier-cgt-next]').click();assert.equal(await page.locator('[data-hier-cgt-add]').count(),20);
 await page.locator('[data-hier-cgt-query]').fill('s115');assert.equal(await page.locator('[data-hier-cgt-add]').count(),1);
 assert.equal(await page.evaluate(()=>window.requests.length),requestsBefore);checks+=5;
 // A manually authored slot remains editable even when other slots retain
 // authenticated CGT assignments. All CGT identities and results are untouched.
 const mixed=await page.evaluate(value=>{
  const base=JSON.parse(value),prior=base.shot_hierarchy,old=prior.members[4],id=crypto.randomUUID();
  const manual={...old,member_id:'manual:'+id,manual_uuid:id,origin:'manual',source_name:'Manual mixed',canonical_name:'Manual mixed',cgt_task_id:null,cgt_identity:null,artist:null,status:null};
  return window.w.hmbApplyShotHierarchyEdit(base,{schema:'hmb-shot-hierarchy-edit',version:1,expected_generation:base.shot_routing.generation,expected_binding_revision:prior.revision,
   removed_member_ids:[old.member_id],binding:{...prior,revision:prior.revision+1,members:[...prior.members.slice(0,4),manual]}});
 },saved);
 const manualSlot=mixed.shot_hierarchy.members[4].gp_shot_uuid;
 const retainedCgt=JSON.stringify(mixed.shot_hierarchy.members.slice(0,4));
 await page.evaluate(value=>{window.catalog=value;window.rejected=false;},snapshot);
 await page.evaluate(value=>window.openGraph(value),mixed);
 assert.equal(await page.locator('[data-shot-rename]:disabled').count(),4);
 await page.locator(`[data-shot-rename="${manualSlot}"]`).click();
 assert.equal(await page.locator('[data-shot-hierarchy-dialog]').count(),0);
 await page.locator('[data-shot-rename-input]').fill('Manual mixed renamed');
 await page.locator('[data-shot-rename-input]').press('Enter');
 await page.evaluate(()=>{if(window.pending?.operation==='cgt_confirm')window.finish();});
 await page.waitForFunction(slot=>window.host.shot_routing.shots.find(row=>row.shot_uuid===slot)?.name==='Manual mixed renamed',manualSlot);
 assert.equal(await page.evaluate(()=>JSON.stringify(window.host.shot_hierarchy.members.slice(0,4))),retainedCgt);
 const mixedSaved=await page.evaluate(()=>JSON.stringify(window.host));
 await page.evaluate(value=>window.openGraph(JSON.parse(value)),mixedSaved);
 assert.equal(await page.locator('[data-shot-name]').last().innerText(),'Manual mixed renamed');
 assert.equal(await page.locator('[data-shot-rename]:disabled').count(),4);checks+=6;
 assert.deepEqual(errors,[]);
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
console.log(JSON.stringify({status:'PASS',checks,synthetic_cgt_tasks:tasks.length,independent_slots:5,user_driven_multilevel_grouping:true,episode_filter:true,real_product_widgets:true,live_cgt_requests:0,cgt_writes:0,paid_requests:0}));
