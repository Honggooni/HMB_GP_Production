import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const widget = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const owner = { runtime_instance_id: "r1", active_picker_shot_uuid: "s1", scene_request_path: "C:/scene.mb",
  selected_outliner_path: "|A", selected_outliner_paths: ["|A"], selected_color: "Red",
  slot_assignments: [{ video_slot: 1, bindings: [{ full_dag_path: "|A", color: "Red" }] }] };
const container = {};
widget.hmbRememberPickerOutlinerDraft(container, owner, true);
const stale = { ...owner, selected_color: "Blue", selected_outliner_paths: [], slot_assignments: [],
  status: "READING", last_action_id: "backend-ack", activity_log: [{ message: "progress" }] };
const protectedDraft = widget.hmbProtectPickerOutlinerDraft(container, stale);
assert.equal(protectedDraft.protected, true);
assert.equal(protectedDraft.state.selected_color, "Red");
assert.deepEqual(protectedDraft.state.selected_outliner_paths, ["|A"]);
assert.equal(protectedDraft.state.status, "READING");
assert.equal(protectedDraft.state.last_action_id, "backend-ack");
widget.hmbStampPickerOutlinerDraft(container, { ...owner, state_revision: 12, state_published_at_ms: 120 });
const ack = { ...owner, state_writer: "python", state_revision: 12, frontend_seen_revision: 12, state_published_at_ms: 120 };
assert.equal(widget.hmbProtectPickerOutlinerDraft(container, ack).protected, false);
assert.equal(widget.hmbProtectPickerOutlinerDraft(container, { ...stale, state_revision: 11, state_published_at_ms: 110 }).protected, true);
const rejected = { ...ack, state_revision: 13, slot_assignments: [], selected_color: "" };
assert.equal(widget.hmbProtectPickerOutlinerDraft(container, rejected).protected, false);
assert.equal(container.__hmbPickerOutlinerDraft, undefined);
for (const other of [{ runtime_instance_id: "r2" }, { active_picker_shot_uuid: "s2" }, { scene_request_path: "C:/other.mb" }]) {
  widget.hmbRememberPickerOutlinerDraft(container, owner, true);
  assert.equal(widget.hmbProtectPickerOutlinerDraft(container, { ...stale, ...other }).protected, false);
  assert.equal(container.__hmbPickerOutlinerDraft, undefined);
}

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch {
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Playwright required");
    console.log("Picker outliner paint-first: SKIP browser (draft unit checks passed)"); process.exit(0);
  }
}
const executablePath = process.env.HMB_PICKER_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Browser required");
  console.log("Picker outliner paint-first: SKIP browser (draft unit checks passed)"); process.exit(0);
}
const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#111}#widget{width:1600px;min-height:1200px}</style><div id="widget"></div><script type="module">
import mount from '/widget.js';
window.publications=[];window.rejectPublication=false;
window.props=value=>({value,onChange:next=>{window.publications.push(next);if(window.rejectPublication)return Promise.reject(new Error('test transport rejected'));if(window.holdPublication)return new Promise((resolve,reject)=>{window.rejectHeldPublication=reject;});}});
window.mount=value=>{window.controller=mount(document.getElementById('widget'),window.props(value));};window.ready=true;
</script>`;
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", req.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  res.end(req.url === "/widget.js" ? source : html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1700, height: 1300 } });
  page.setDefaultTimeout(8000);
  const origin = `http://127.0.0.1:${server.address().port}`;
  await page.route("**/*", route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  const failures = [];
  page.on("pageerror", error => failures.push(error.message));
  await page.goto(origin);
  await page.waitForFunction(() => window.ready);
  await page.evaluate(() => window.mount({
    language: "ko", runtime_instance_id: "paint-first-runtime", state_revision: 10, state_writer: "python",
    scene_path: "C:/scene.mb", scene_request_path: "C:/scene.mb", native_read_ready: true,
    scene_stage: "OUTLINER_READY", status: "OUTLINER_READY", active_slot_count: 1,
    outliner_nodes: [{ name: "Actor", full_path: "|Actor", maya_uuid: "root", depth_meshes:
      Array.from({length: 2000}, (_, i) => ({ name: `Mesh${i}`, full_path: `|Actor|Mesh${i}`, maya_uuid: `uuid-${i}` })) }],
    depth_settings: { range: "close", expanded_roots: ["|Actor"] },
  }));
  if (await page.locator(".hmbvp").getAttribute("data-picker-view") !== "expanded") {
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent("dblclick");
  }
  await page.waitForFunction(() => document.querySelector('.hmbvp[data-picker-view="expanded"]'));
  await page.waitForTimeout(150);
  const first = await page.evaluate(() => {
    const host = document.getElementById("widget");
    window.base = structuredClone(host.__hmbPendingPickerState || host.__hmbAuthoritativePickerState);
    window.publications=[];
    window.rowRefs=Array.from(host.querySelectorAll('.outliner-row'));
    window.scrollStart=host.querySelector('.outliner-scroll').scrollTop;
    window.removedRows=0;
    window.observer=new MutationObserver(records=>{
      for(const record of records)for(const node of record.removedNodes) {
        if(node.nodeType===1 && (node.matches('.outliner-row') || node.querySelector('.outliner-row')))window.removedRows++;
      }
    });window.observer.observe(host.querySelector('.outliner-scroll'),{childList:true,subtree:true});
    window.clickRow=(index,options={})=>host.querySelector('[data-group-path="|Actor|Mesh'+index+'"]').dispatchEvent(new MouseEvent('click',{bubbles:true,...options}));
    window.color=name=>host.querySelector('[data-color="'+name+'"]').click();
    window.projection=()=>({selected:Array.from(host.querySelectorAll('.outliner-row.selected')).map(row=>row.dataset.groupPath),
      colors:Array.from(host.querySelectorAll('.outliner-row.selected')).map(row=>row.querySelector('.assigned-chip')?.title||'')});
    const start=performance.now();
    window.clickRow(1);window.clickRow(3,{ctrlKey:true});window.clickRow(5,{metaKey:true});window.color('Yellow');
    const ms=performance.now()-start;
    const immediate=window.projection();
    window.controller.update(window.props({...window.base,message:'Old background progress',state_writer:'python'}));
    return {ms,immediate,afterOld:window.projection(),published:window.publications.length};
  });
  const selected = [1,3,5].map(i=>`|Actor|Mesh${i}`);
  assert.deepEqual(first.immediate, {selected,colors:['Yellow','Yellow','Yellow']});
  assert.deepEqual(first.afterOld, first.immediate, "A pre-paint backend response cannot repaint old colors/selection");
  assert.equal(first.published, 0, "Input feedback must finish before persistence");
  await page.waitForFunction(() => window.publications.length === 1);
  const crossed = await page.evaluate(() => {
    const old=window.publications.at(-1);window.old=structuredClone(old);
    window.color('Red');window.clickRow(6,{ctrlKey:true});window.color('Blue');
    window.controller.update(window.props({...old,state_writer:'python',frontend_seen_revision:old.state_revision,message:'Delayed older ACK'}));
    return window.projection();
  });
  assert.deepEqual(crossed.selected, [...selected, '|Actor|Mesh6']);
  assert.ok(crossed.colors.every(color=>color==='Blue'));
  await page.waitForFunction(() => window.publications.length === 2);
  const acknowledged = await page.evaluate(() => {
    const latest=window.publications.at(-1);window.latest=structuredClone(latest);
    window.controller.update(window.props({...latest,state_writer:'python',frontend_seen_revision:latest.state_revision,message:'Latest ACK'}));
    window.controller.update(window.props({...window.old,state_writer:'python',frontend_seen_revision:window.old.state_revision,message:'Crossed old ACK'}));
    const host=document.getElementById('widget');
    return {projection:window.projection(),sameRows:window.rowRefs.every(row=>row.isConnected),removed:window.removedRows,
      scroll:host.querySelector('.outliner-scroll').scrollTop,initialScroll:window.scrollStart};
  });
  assert.deepEqual(acknowledged.projection,crossed);
  assert.equal(acknowledged.sameRows,true);
  assert.equal(acknowledged.removed,0);
  assert.equal(acknowledged.scroll,acknowledged.initialScroll);
  const range = await page.evaluate(() => {window.clickRow(2);window.clickRow(8,{shiftKey:true});return window.projection();});
  assert.deepEqual(range.selected,Array.from({length:7},(_,i)=>`|Actor|Mesh${i+2}`));
  await page.waitForFunction(() => window.publications.length === 3);
  await page.evaluate(() => {
    window.rejectPublication=true;window.color('Green');
  });
  await page.waitForFunction(() => document.getElementById('widget').__hmbVisiblePickerStatePublicationError);
  const rolledBack = await page.evaluate(() => ({projection:window.projection(),draft:!!document.getElementById('widget').__hmbPickerOutlinerDraft}));
  assert.deepEqual(rolledBack.projection,range,"A rejected publication restores only its owned draft and exposes the failure");
  assert.equal(rolledBack.draft,false);
  await page.evaluate(() => {
    window.rejectPublication=false;window.holdPublication=true;window.color('Orange');
  });
  await page.waitForFunction(() => !!window.rejectHeldPublication);
  const pendingOnFailure = await page.evaluate(async () => {
    window.holdPublication=false;window.color('Pink');
    window.rejectHeldPublication(new Error('older transport rejected'));
    await Promise.resolve();await Promise.resolve();await Promise.resolve();
    return window.projection();
  });
  assert.deepEqual(pendingOnFailure.selected,range.selected);
  assert.ok(pendingOnFailure.colors.every(color=>color==='Pink'),"Failure of an older publication cannot repaint over a newer uncommitted color");
  await page.waitForFunction(() => window.publications.length === 6);
  assert.deepEqual(await page.evaluate(() => window.projection()),pendingOnFailure);
  await page.evaluate(() => {window.observer.disconnect();window.controller.cleanup();});
  assert.deepEqual(failures,[]);
  console.log(`Picker outliner paint-first: PASS (2000 meshes, Ctrl/Cmd/Shift, immediate chips, 0 row removals, crossed ACKs, scoped drafts, rejection rollback; 4 input actions ${first.ms.toFixed(1)}ms)`);
} finally {
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
