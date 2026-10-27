// Product widget, synthetic offline graph. No CGT/provider/server requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import * as w from '../../widgets/HMBImageAssetLibraryWidget.js';

const initial = w.hmbNormalizeImageAssetState({ project_root:'C:/fixture/Ai_Ct_image/project', project_id:'Synthetic project', project_uid:'fixture-project' });
const slot = initial.shot_routing.shots[0].shot_uuid;
const member = (i, target=undefined, name=`e201s${String(i).padStart(3,'0')}c001__`) => {
  const id=randomUUID(), parsed=w.hmbHierarchyParseName(name);
  return {member_id:`manual:${id}`,origin:'manual',manual_uuid:id,source_name:parsed.source_name,canonical_name:parsed.canonical_name,
    gp_shot_uuid:target||randomUUID(),parent_id:null,selection_order:i,cgt_task_id:null,artist:null,status:null};
};
const request = (state, members) => ({schema:'hmb-shot-hierarchy-edit',version:1,expected_generation:state.shot_routing.generation,
  expected_binding_revision:state.shot_hierarchy.revision||0,binding:{schema:'hmb-shot-hierarchy',version:1,binding_id:state.shot_hierarchy.binding_id||randomUUID(),
    revision:(state.shot_hierarchy.revision||0)+1,project_identity:state.project_root.toLowerCase(),channel_uuid:state.shot_routing.channel_uuid,cgt_account_id:null,members},
    removed_member_ids:(state.shot_hierarchy.members||[]).filter(row=>!members.some(item=>item.member_id===row.member_id)).map(row=>row.member_id)});
let checks=0;
for(let count=0;count<=5;count++) {
  const rows=Array.from({length:count},(_,i)=>member(i+1,i===0?slot:undefined));
  const before=JSON.stringify(initial),result=w.hmbApplyShotHierarchyEdit(initial,request(initial,rows));
  assert.equal(result.shot_routing.shots.length,Math.max(1,count));assert.equal(JSON.stringify(initial),before);checks+=2;
}
const rows=Array.from({length:5},(_,i)=>member(i+1,i===0?slot:undefined));
rows[1].parent_id=rows[0].member_id;rows[2].parent_id=rows[1].member_id;rows[4].parent_id=rows[3].member_id;
const result=w.hmbApplyShotHierarchyEdit(initial,request(initial,rows));
assert.deepEqual(result.shot_routing.shots.map(row=>row.name),['e201_s001c001-s002c001__','e201_s002c001-s003c001__','e201s003c001__','e201_s004c001-s005c001__','e201s005c001__']);
assert.deepEqual(w.hmbApplyShotHierarchyEdit(result,request(result,rows)),result);
for(const change of [r=>r[0].parent_id=r[0].member_id,r=>r[0].parent_id=r[1].member_id,r=>r[0].parent_id=r[2].member_id,
  r=>r[4].parent_id='missing',r=>r[4].gp_shot_uuid=r[0].gp_shot_uuid,r=>r[4].origin='cgt',r=>r[4].artist='guessed account']) {
  const bad=structuredClone(rows);change(bad);assert.throws(()=>w.hmbApplyShotHierarchyEdit(result,request(result,bad)));checks++;
}
assert.throws(()=>w.hmbApplyShotHierarchyEdit(initial,request(initial,Array.from({length:5},(_,i)=>member(i+1)))));
for(const name of ['', ' a','a ','a  b','a/b','../a','x'.repeat(129),'😀'.repeat(65),'a\nb','password abc']) {
  assert.throws(()=>w.hmbHierarchyParseName(name));checks++;
}
const own=[member(1,slot,'e201/e201s112c001__'),member(2,undefined,'e201s113c002__'),member(3,undefined,'e201s114c001__')];
own[1].parent_id=own[0].member_id;own[2].parent_id=own[0].member_id;
assert.equal(w.hmbHierarchyDerivedNames({members:own})[slot],'e201_s112c001-s113c002-s114c001__');
assert.equal(own[0].source_name,'e201/e201s112c001__');
assert.equal(w.hmbHierarchyDerivedNames({members:[own[0]]})[slot],'e201s112c001__');
assert.equal(w.hmbHierarchyParseName('e201s114c002__').shot,'s114');
assert.equal(w.hmbHierarchyParseName('e201s114c002__').split_cut,'c002');
assert.equal(w.hmbHierarchyParseName('미인식_수동__').shot,'');checks+=7;

const require=createRequire(import.meta.url);
let playwright;
try { playwright=require('playwright'); }
catch { playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
const browserPath=process.env.HMB_IMAGE_ASSET_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe';
assert.ok(fs.existsSync(browserPath),'Actual Chrome required');
const source=fs.readFileSync(new URL('../../widgets/HMBImageAssetLibraryWidget.js',import.meta.url));
const html=`<!doctype html><meta charset="utf-8"><title>Synthetic offline HMB hierarchy product fixture</title><style>body{background:#090c16;color:white;font:12px system-ui;margin:0}#widget{width:1100px;height:800px}</style><p>Synthetic offline fixture · Product widget · CGT live list unavailable</p><div id="widget"></div><script type="module">
import mount,*as w from '/widget.js';window.w=w;window.host=null;window.writes=[];window.fail=false;window.syncEcho=false;
window.props=()=>({value:JSON.stringify(window.host),onChange:value=>{
 const raw=JSON.parse(value);if(raw.__hmb_manifest_poll_nonce)return;
 const req=raw.shot_hierarchy_request||raw.edits?.shot_hierarchy_request;
 if(!req?.schema)return;
 if(window.fail)return Promise.reject(new Error('Synthetic transport rejection'));
 window.writes.push(structuredClone(req));window.host=w.hmbNormalizeImageAssetState(w.hmbApplyShotHierarchyEdit(window.host,req));
 window.host.ui_edit_revision=raw.ui_edit_revision;
 if(window.syncEcho){window.host.scan_revision+=17;window.host.manifest_signature='canonical-sync-scan';window.controller.update(window.props());}
 else queueMicrotask(()=>window.controller.update(window.props()));
}});
window.openGraph=value=>{window.controller?.cleanup();window.host=w.hmbNormalizeImageAssetState(value);window.controller=mount(document.getElementById('widget'),window.props());};window.ready=true;
</script>`;
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/widget.js'?'text/javascript; charset=utf-8':'text/html; charset=utf-8');res.end(req.url==='/widget.js'?source:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  browser=await playwright.chromium.launch({executablePath:browserPath,headless:true});
  const page=await browser.newPage({viewport:{width:1200,height:1000}}),errors=[];
  page.setDefaultTimeout(7000);page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>window.ready);
  await page.evaluate(value=>window.openGraph(value),initial);
  const openShots=()=>page.locator('[data-shot-add]').first();
  await openShots().click();await page.locator('[data-shot-hierarchy-dialog]').waitFor();
  const initialDialogBox=await page.locator('[data-shot-hierarchy-dialog]').boundingBox();
  assert.ok(Math.abs(initialDialogBox.width-1000)<1&&Math.abs(initialDialogBox.height-682)<1,'Removing static guidance preserves the existing 1000x682 desktop opening size');
  const compactDialogText=await page.locator('[data-shot-hierarchy-dialog]').innerText();
  assert.ok(!/대표와 하위 모두 독립적으로 실행됩니다|수동 이름을 입력하고 연결할 샷 슬롯을 선택하세요|총 실행 슬롯은 기존 샷을 포함해/.test(compactDialogText));
  assert.match(compactDialogText,/기존 슬롯을 선택하면 UUID·미디어·설정·결과를 보존하고 이름만 적용합니다/);checks+=3;
  assert.match(await page.locator('.hier-offline').innerText(),/CGT 앱과 설치된 Python SDK 연결/);
  assert.equal(await page.locator('.hier-table tbody tr').count(),0);
  await page.locator('[data-hier-manual-name]').fill('cancelled');await page.locator('[data-hier-add]').click();
  await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>window.writes.length),0);
  assert.equal(await page.evaluate(()=>window.host.shot_routing.shots.length),1);checks+=4;
  await openShots().click();
  for(const name of ['pending_parent','pending_child']) {
    await page.locator('[data-hier-manual-name]').fill(name);
    await page.locator('[data-hier-add]').click();
  }
  const pendingIds=await page.locator('[data-hier-member]').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('data-hier-member')));
  await page.locator('[data-hier-manual-name]').fill('Unsubmitted manual shot');
  await page.locator('[data-hier-slot]').selectOption(slot);
  await page.locator(`[data-hier-parent="${pendingIds[1]}"]`).selectOption('manual:'+pendingIds[0]);
  assert.equal(await page.locator('[data-hier-manual-name]').inputValue(),'Unsubmitted manual shot','Changing another shot parent preserves the unsubmitted manual name');
  assert.equal(await page.locator('[data-hier-slot]').inputValue(),slot,'Changing another shot parent preserves the chosen existing slot');
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(()=>window.writes.length),0,'Cancelling a parent edit with a pending manual draft leaves the host untouched');checks+=3;
  await openShots().click();
  for(let i=1;i<=5;i++) {
    await page.locator('[data-hier-manual-name]').fill(`e201s${String(i).padStart(3,'0')}c001__`);
    if(i===1)await page.locator('[data-hier-slot]').selectOption(slot);
    await page.locator('[data-hier-add]').click();
    assert.equal(await page.locator('[data-hier-member]').count(),i);
  }
  const ids=await page.locator('[data-hier-member]').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('data-hier-member')));
  assert.equal(await page.locator('[data-hier-parent]').count(),5);
  // Build the real draft through the same selectors the user operates. No
  // programmatic parent_id injection may stand in for the missing UI path.
  const memberKey=index=>'manual:'+ids[index];
  await page.locator(`[data-hier-parent="${ids[1]}"]`).selectOption(memberKey(0));
  await page.locator(`[data-hier-parent="${ids[2]}"]`).selectOption(memberKey(1));
  await page.locator(`[data-hier-parent="${ids[4]}"]`).selectOption(memberKey(3));
  assert.equal(await page.locator('.hier-child').count(),3);
  assert.match(await page.locator('[data-shot-hierarchy-dialog] footer > span').innerText(),/3개 대표 · 3개 하위/,'A row can count as both a child and a representative');
  assert.equal(await page.locator(`[data-hier-parent="${ids[0]}"]`).isEnabled(),true,'A representative with children can itself move under another representative');
  assert.equal(await page.locator(`[data-hier-parent="${ids[1]}"]`).isEnabled(),true,'A child can remain a representative of its own children');
  const rootOptions=await page.locator(`[data-hier-parent="${ids[0]}"] option`).evaluateAll(nodes=>nodes.map(node=>node.value));
  assert.ok(![memberKey(0),memberKey(1),memberKey(2)].some(value=>rootOptions.includes(value)),'Self and all descendants cannot become the parent');
  assert.ok(rootOptions.includes(memberKey(3))&&rootOptions.includes(memberKey(4)),'Unrelated roots and children remain valid parents');
  const preview=await page.locator('[data-hier-name-preview]').innerText();
  for(const expected of result.shot_routing.shots.map(row=>row.name))assert.ok(preview.includes(expected),'Preview uses each shot and its direct children only');
  checks+=13;
  assert.equal(await page.locator('[data-hier-member] .hier-output').count(),0);
  const report=process.env.HMB_HIERARCHY_REPORT_DIR;
  if(report){fs.mkdirSync(report,{recursive:true});await page.screenshot({path:path.join(report,'hierarchy-desktop-synthetic.png')});}
  await page.evaluate(()=>{window.syncEcho=true;});
  await page.locator('[data-hier-confirm]').click();await page.waitForFunction(()=>window.writes.length===1);
  assert.deepEqual(await page.evaluate(()=>{const latest=document.getElementById('widget').__hmbImageAssetLatestState;return {scan:latest.scan_revision,manifest:latest.manifest_signature,hostScan:window.host.scan_revision};}),
    {scan:17,manifest:'canonical-sync-scan',hostScan:17},'Synchronous host canonical metadata survives optimistic commit completion');
  await page.evaluate(()=>{window.syncEcho=false;});checks++;
  const saved=await page.evaluate(()=>JSON.stringify(window.host));
  const committed=JSON.parse(saved).shot_hierarchy.members;
  assert.deepEqual(committed.map(row=>row.parent_id),[null,memberKey(0),memberKey(1),null,memberKey(3)],'The actual confirmed draft persists all multi-level relations');
  assert.equal(committed[0].gp_shot_uuid,slot,'Binding an existing first slot retains its UUID');
  assert.equal(new Set(committed.map(row=>row.gp_shot_uuid)).size,5,'Grouping keeps five independent slots');checks+=3;
  const names=JSON.parse(saved).shot_routing.shots.map(row=>row.name);
  assert.deepEqual(names,result.shot_routing.shots.map(row=>row.name));
  assert.equal(await page.locator('[data-shot-delete]:disabled').count(),5);
  await page.evaluate(value=>window.openGraph(JSON.parse(value)),saved);
  assert.deepEqual(await page.locator('[data-shot-name]').allTextContents(),names);
  // Grouped parents display A+B but their pencil edits only source A. Leaving
  // that unchanged and blurring must never submit a redundant hierarchy edit.
  const writesBeforeBlur=await page.evaluate(()=>window.writes.length);
  await page.locator('[data-shot-rename]').first().click();
  assert.equal(await page.locator('[data-shot-rename-input]').inputValue(),'e201s001c001__');
  await page.locator('[data-shot-rename-input]').evaluate(node=>node.blur());
  assert.equal(await page.evaluate(()=>window.writes.length),writesBeforeBlur);
  assert.deepEqual(await page.locator('[data-shot-name]').allTextContents(),names);checks+=3;
  await openShots().click();assert.equal(await page.locator('[data-hier-member]').count(),5);
  assert.equal(await page.locator('.hier-child').count(),3,'Existing grouped save retains all child relationships');
  assert.equal(await page.locator(`[data-hier-parent="${ids[1]}"]`).inputValue(),memberKey(0));
  assert.equal(await page.locator(`[data-hier-parent="${ids[2]}"]`).inputValue(),memberKey(1));
  assert.equal(await page.locator(`[data-hier-remove="${ids[0]}"]`).isDisabled(),true,'A representative cannot be detached while its children remain');checks+=2;
  // A background host remount preserves the draft/dialog; a new Shot
  // generation makes its eventual confirmation fail without any host write.
  await page.evaluate(()=>{window.host.scan_revision++;window.controller.update(window.props());});
  assert.equal(await page.locator('[data-shot-hierarchy-dialog]').evaluate(node=>node.open),true);
  await page.evaluate(()=>{window.host.shot_routing.generation++;window.controller.update(window.props());});
  await page.locator('[data-hier-confirm]').click();
  assert.match(await page.locator('[data-hier-message]').innerText(),/변경/);
  assert.equal(await page.evaluate(()=>window.writes.length),1);
  await page.keyboard.press('Escape');
  // Narrow native modal remains readable/scrollable with all controls.
  await page.setViewportSize({width:600,height:850});await openShots().click();
  const bounds=await page.locator('[data-shot-hierarchy-dialog]').boundingBox();
  assert.ok(bounds.x>=0&&bounds.x+bounds.width<=601&&bounds.height<=850);
  assert.ok(Math.abs(bounds.width-564)<1&&Math.abs(bounds.height-826)<1,'The narrow modal retains its measured pre-removal outer size');checks++;
  if(report)await page.screenshot({path:path.join(report,'hierarchy-narrow-synthetic.png')});
  await page.keyboard.press('Escape');
  // A rejected transport restores the complete prior native/binding state.
  await page.evaluate(()=>{window.fail=true;});await openShots().click();
  await page.locator(`[data-hier-remove="${ids[2]}"]`).click();
  await page.locator('[data-hier-confirm]').click();await page.waitForTimeout(150);
  assert.deepEqual(await page.locator('[data-shot-name]').allTextContents(),names);
  assert.equal(await page.evaluate(()=>window.writes.length),1);
  await page.evaluate(value=>{window.fail=false;window.openGraph(JSON.parse(value));},saved);
  await openShots().click();
  await page.locator('[data-hier-name]').first().fill('e201s001c002__');
  const countBeforeConfirm=await page.evaluate(()=>window.writes.length);
  await page.locator('[data-hier-confirm]').click();
  await page.waitForFunction(count=>window.writes.length===count+1,countBeforeConfirm);
  assert.equal(await page.locator('[data-shot-hierarchy-dialog]').count(),0,'One Confirm click saves the changed existing row');
  assert.equal(await page.locator('[data-shot-name]').first().innerText(),'e201_s001c002-s002c001__');
  const renamedSaved=await page.evaluate(()=>JSON.stringify(window.host));
  await page.evaluate(value=>window.openGraph(JSON.parse(value)),renamedSaved);
  assert.equal(await page.locator('[data-shot-name]').first().innerText(),'e201_s001c002-s002c001__');
  assert.deepEqual(errors,[]);checks+=21;
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
console.log(JSON.stringify({status:'PASS',checks,product_browser:true,independent_slots:5,cgt_requests:0,paid_requests:0}));
