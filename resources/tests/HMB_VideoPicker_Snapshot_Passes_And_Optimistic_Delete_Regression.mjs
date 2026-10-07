import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const roles = ["original", "mask", "depth"];
const snapshots = roles.map((role, index) => ({ snapshot_uid: `snap-${role}`, artifact_type: role,
  snapshot_batch_uid: "batch-145", frame: 145, video_slot: 1, created_at_ms: index + 1,
  path: `C:/snapshots/${role}.png`, url: `/snap/${role}.svg`, sha256: String(index + 1).repeat(64) }));
const initial = { runtime_instance_id: "snapshot-delete", state_writer: "python", state_revision: 10,
  snapshots, viewport_mode: "snapshot", active_snapshot_uid: "snap-depth", snapshot_active: true,
  snapshot_video_slot: 1, snapshot_frame: 145, snapshot_path: snapshots[2].path, snapshot_url: snapshots[2].url,
  current_frame: 145, slot_assignments: [{ video_slot: 1, bindings: [{ full_dag_path: "|Actor", color: "Red" }] }], videos: [] };
const container = {};
const removed = picker.hmbBeginOptimisticPickerSnapshotDeletion(container, initial, "snap-depth", "delete-depth");
assert.deepEqual(removed.state.snapshots.map(item => item.artifact_type), ["original", "mask"]);
assert.equal(removed.state.active_snapshot_uid, "snap-mask");
assert.equal(removed.state.snapshot_url, "/snap/mask.svg");
assert.equal(removed.state.snapshot_artifact_type, "mask");
assert.deepEqual(removed.state.slot_assignments, initial.slot_assignments);
container.__hmbPendingPickerState = removed.state;
for (const stale of [initial, JSON.stringify(initial)]) {
  const filtered = picker.hmbApplyOptimisticPickerSnapshotDeletions(container, stale);
  assert.equal(filtered.snapshots.some(item => item.snapshot_uid === "snap-depth"), false);
  assert.equal(filtered.active_snapshot_uid, "snap-mask");
}
const acknowledged = picker.hmbApplyOptimisticPickerSnapshotDeletions(container, { ...removed.state,
  state_writer: "python", snapshot_delete_results: { "delete-depth": { status: "removed", snapshot_uid: "snap-depth" } } });
assert.equal(acknowledged.snapshots.length, 2);
assert.equal(picker.hmbApplyOptimisticPickerSnapshotDeletions(container, initial).snapshots.length, 2,
  "A successful deletion still protects against old Python echoes.");
assert.equal(picker.hmbRejectOptimisticPickerSnapshotDeletion(container, acknowledged, "delete-depth").snapshots.length, 2,
  "Late transport failure cannot undo an already confirmed deletion.");
const failedContainer = {};
const pending = picker.hmbBeginOptimisticPickerSnapshotDeletion(failedContainer, initial, "snap-depth", "rejected-depth");
failedContainer.__hmbPendingPickerState = pending.state;
const rejected = picker.hmbApplyOptimisticPickerSnapshotDeletions(failedContainer, { ...initial,
  snapshot_delete_results: { "rejected-depth": { status: "rejected", reason: "Busy" } } });
assert.equal(rejected.active_snapshot_uid, "snap-depth");
assert.equal(rejected.snapshots.length, 3);
assert.equal(failedContainer.__hmbPickerSnapshotDeletions.size, 0);
const navigatedContainer = {};
const navigated = picker.hmbBeginOptimisticPickerSnapshotDeletion(navigatedContainer, initial, "snap-depth", "transport-depth");
const newerSelection = { ...navigated.state, active_snapshot_uid: "snap-original", snapshot_url: snapshots[0].url, snapshot_path: snapshots[0].path };
const restored = picker.hmbRejectOptimisticPickerSnapshotDeletion(navigatedContainer, newerSelection, "transport-depth");
assert.equal(restored.active_snapshot_uid, "snap-original", "Rollback preserves a later preview selection.");
assert.equal(restored.snapshots.length, 3);
const empty = picker.hmbDeletePickerSnapshot({ ...initial, snapshots: [snapshots[2]] }, "snap-depth");
assert.equal(empty.viewport_mode, "video");
assert.equal(empty.active_snapshot_uid, "");
assert.equal(empty.snapshot_active, false);
assert.equal(empty.snapshot_url, "");
const frameZero = picker.hmbDeletePickerSnapshot({ ...initial, snapshots: [{ ...snapshots[1], frame: 0 }, snapshots[2]] }, "snap-depth");
assert.equal(frameZero.snapshot_frame, 0, "Frame zero is a valid remaining snapshot frame.");
assert.equal(picker.hmbSnapshotArtifactType({}), "mask", "Legacy colored snapshots retain their Mask identity.");
const reset = picker.hmbApplyOptimisticPickerSnapshotDeletions(container, { ...initial, runtime_instance_id: "new-runtime" });
assert.equal(reset.snapshots.length, 3);
assert.equal(container.__hmbPickerSnapshotDeletions.size, 0);

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch {
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Playwright is required");
    console.log("PASS snapshot state; browser SKIP (Playwright unavailable)"); process.exit(0);
  }
}
const executablePath = process.env.HMB_PICKER_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Browser is required");
  console.log("PASS snapshot state; browser SKIP (browser unavailable)"); process.exit(0);
}
const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0}#widget{width:1600px;min-height:1200px}</style><div id="widget"></div><script type="module">
import mount from '/widget.js';
window.host=document.getElementById('widget');window.commands=[];window.publications=[];
window.props=value=>({value,onChange:next=>{
  const command=next.__hmb_picker_command__;
  if(command){window.commands.push(structuredClone(command));if(window.holdDelivery)return new Promise((resolve,reject)=>{window.resolveDelivery=resolve;window.rejectDelivery=reject;});}
  else window.publications.push(structuredClone(next));
}});
window.start=value=>{window.controller?.cleanup();const fresh=document.createElement('div');fresh.id='widget';window.host.replaceWith(fresh);window.host=fresh;window.host.__hmbVideoPickerExpanded=true;window.commands=[];window.publications=[];window.holdDelivery=false;window.controller=mount(window.host,window.props(value));};
window.live=()=>window.host.__hmbPickerPaintFirstState||window.host.__hmbPendingPickerState||window.host.__hmbAuthoritativePickerState;
window.echo=value=>window.controller.update(window.props(value));window.ready=true;
</script>`;
const colors = { original: "#777777", mask: "#ff0000", depth: "#aaaaaa" };
const server = http.createServer((req, res) => {
  if (req.url === "/widget.js") { res.setHeader("Content-Type", "text/javascript; charset=utf-8"); res.end(source); }
  else if (req.url?.startsWith("/snap/")) {
    const role = req.url.split("/").at(-1).split(".")[0];
    res.setHeader("Content-Type", "image/svg+xml"); res.end(`<svg xmlns="http://www.w3.org/2000/svg" width="128" height="72"><rect width="128" height="72" fill="${colors[role] || "black"}"/></svg>`);
  } else { res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(html); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
const errors = [];
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1700, height: 1300 } });
  const origin = `http://127.0.0.1:${server.address().port}`;
  await page.route("**/*", route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  page.on("pageerror", error => errors.push(error.message));
  page.setDefaultTimeout(5000);
  await page.goto(origin); await page.waitForFunction(() => window.ready);
  const fixture = () => ({ runtime_instance_id: "snapshot-browser", state_revision: 10, state_writer: "python", language: "en",
    scene_path: "D:/AI/test/e201s095c001__.mb", scene_request_path: "D:/AI/test/e201s095c001__.mb", native_read_ready: true,
    scene_stage: "OUTLINER_READY", status: "READY", maya_available: true, selected_camera: "shotCamera",
    cameras: [{ name: "shotCamera", full_path: "|shotCamera" }], current_frame: 145, preview_frame: 145,
    start_frame: 1, end_frame: 250, source_fps: 24, output_fps: 24, output_width: 1280, output_height: 720,
    original_enabled: false, mask_enabled: true, depth_enabled: false, videos: [], snapshots: [],
    outliner_nodes: [{ name: "Actor", full_path: "|Actor", maya_uuid: "actor-uuid" }],
    slot_assignments: initial.slot_assignments });
  const mountedSnapshotState = () => ({ ...fixture(), ...structuredClone(initial), runtime_instance_id: "snapshot-browser",
    snapshots: snapshots.map(item => ({ ...item, url: origin + item.url })), snapshot_url: origin + snapshots[2].url });
  const start = async value => {
    await page.evaluate(value => window.start(value), value);
    await page.waitForFunction(() => window.host.querySelector('.hmbvp')?.getAttribute('data-picker-view') === 'expanded');
  };
  const expectRole = async role => {
    await page.waitForFunction(role => {
      const image = window.host.querySelector('#picker-snapshot-image');
      return image?.getAttribute('src')?.endsWith('/snap/' + role + '.svg') && !image.hidden && image.naturalWidth > 0;
    }, role);
    assert.match(await page.locator('.viewport-title small').innerText(), new RegExp(role === "original" ? "Original" : role === "mask" ? "Mask" : "Depth"));
  };
  for (let bits = 1; bits < 8; bits++) {
    const state = fixture(); await start(state);
    // Simulate delayed checkbox publication: DOM is the current user choice,
    // while the local state deliberately remains the old Mask-only selection.
    await page.evaluate(bits => {
      [['#original-preview-toggle',1],['#mask-playblast-toggle',2],['#depth-playblast-toggle',4]].forEach(([selector,bit])=>{window.host.querySelector(selector).checked=!!(bits&bit);});
    }, bits);
    await page.locator('#create-snapshot').click();
    const command = await page.evaluate(() => window.commands.find(item => item.action === 'render_snapshot'));
    assert.ok(command, 'Snapshot command must be dispatched');
    const selected = roles.filter((role, index) => bits & (1 << index));
    for (let index = 0; index < roles.length; index++) assert.equal(command.payload['include_' + roles[index]], !!(bits & (1 << index)), roles[index] + ':' + bits);
    assert.equal(command.payload.snapshot_frame, 145);
    assert.equal(command.payload.authoring_state.slot_assignments[0].bindings[0].color, 'Red');
    const records = selected.map((role,index)=>({ ...snapshots[roles.indexOf(role)], snapshot_uid: `batch-${bits}-${role}`,
      snapshot_batch_uid: `batch-${bits}`, url: origin + `/snap/${role}.svg`, created_at_ms: index + 1 }));
    const active = records.at(-1);
    const response = { ...state, original_enabled: !!(bits&1), mask_enabled: !!(bits&2), depth_enabled: !!(bits&4),
      snapshots: records, viewport_mode: 'snapshot', snapshot_active: true, active_snapshot_uid: active.snapshot_uid,
      snapshot_video_slot: 1, snapshot_frame: 145, snapshot_path: active.path, snapshot_url: active.url,
      backend_ack_action_id: command.action_id, operation_kind: 'render_snapshot', operation_started_at_ms: 1, operation_finished_at_ms: 2 };
    await page.evaluate(value => window.echo(value), response);
    await expectRole(selected.at(-1));
    assert.deepEqual(await page.evaluate(() => window.live().snapshots.map(item => item.artifact_type)), selected);
    assert.deepEqual(await page.evaluate(() => window.live().snapshots.map(item => item.snapshot_batch_uid)), selected.map(()=>`batch-${bits}`));
    for (let index = selected.length - 2; index >= 0; index--) { await page.locator('#snapshot-prev').click(); await expectRole(selected[index]); }
    console.log(`PASS Snapshot selected outputs ${selected.join('+')}`);
  }
  const historical = mountedSnapshotState();
  historical.snapshots[1].frame = 100;
  historical.snapshots[1].snapshot_batch_uid = "prior-batch-100";
  await start(historical); await expectRole('depth');
  await page.evaluate(() => { window.holdDelivery=true; });
  const immediate = await page.evaluate(() => {
    window.host.querySelector('#delete-snapshot').click();
    const live = window.live(), image = window.host.querySelector('#picker-snapshot-image');
    return { uids: live.snapshots.map(item=>item.snapshot_uid), active: live.active_snapshot_uid,
      src: image?.getAttribute('src') || '', frame: window.host.querySelector('#video-frame-number').value, command: window.commands.at(-1) };
  });
  assert.deepEqual(immediate.uids, ['snap-original','snap-mask']);
  assert.equal(immediate.active, 'snap-mask');
  assert.equal(immediate.frame, '100', 'Fallback frame controls must use the remaining snapshot frame immediately.');
  assert.equal(immediate.src.endsWith('/snap/depth.svg'), false, 'Deleted preview must disappear in the click transaction, before bridge completion.');
  assert.equal(immediate.command.action, 'delete_snapshot');
  assert.equal(immediate.command.payload.snapshot_uid, 'snap-depth');
  await expectRole('mask');
  await page.evaluate(value => window.echo(value), mountedSnapshotState());
  assert.equal(await page.evaluate(() => window.live().snapshots.some(item=>item.snapshot_uid==='snap-depth')), false);
  await expectRole('mask');
  const confirmed = { ...mountedSnapshotState(), snapshots: mountedSnapshotState().snapshots.slice(0,2), active_snapshot_uid:'snap-mask',
    snapshot_path:snapshots[1].path, snapshot_url:origin + snapshots[1].url,
    backend_ack_action_id:immediate.command.action_id,
    snapshot_delete_results:{[immediate.command.action_id]:{status:'removed',snapshot_uid:'snap-depth'}} };
  await page.evaluate(value=>window.echo(value),confirmed);
  await page.evaluate(value=>window.echo(value),mountedSnapshotState());
  assert.equal(await page.evaluate(()=>window.live().snapshots.some(item=>item.snapshot_uid==='snap-depth')),false);
  await expectRole('mask');
  await page.evaluate(()=>window.resolveDelivery?.());
  console.log('PASS immediate delete and delayed/confirmed stale echoes');

  await start(mountedSnapshotState()); await expectRole('depth');
  await page.evaluate(()=>{window.holdDelivery=true;window.host.querySelector('#delete-snapshot').click();window.rejectDelivery(new Error('delayed transport failure'));});
  await page.waitForFunction(()=>window.live().active_snapshot_uid==='snap-depth'&&window.live().snapshots.length===3);
  await expectRole('depth');
  console.log('PASS delayed transport rejection restores exact snapshot');

  await start(mountedSnapshotState()); await expectRole('depth');
  const rejectedCommand=await page.evaluate(()=>{window.holdDelivery=true;window.host.querySelector('#delete-snapshot').click();return window.commands.at(-1);});
  await page.evaluate(value=>window.echo(value),{...mountedSnapshotState(),backend_ack_action_id:rejectedCommand.action_id,
    snapshot_delete_results:{[rejectedCommand.action_id]:{status:'rejected',snapshot_uid:'snap-depth',reason:'Busy'}}});
  await expectRole('depth');
  assert.equal(await page.evaluate(()=>window.live().snapshots.length),3);
  await page.evaluate(()=>window.resolveDelivery?.());
  console.log('PASS actual backend rejection restores snapshot');
  assert.deepEqual(errors, []);
} finally {
  await browser?.close(); await new Promise(resolve=>server.close(resolve));
}
console.log('PASS Snapshot seven selected-pass combinations, exact history metadata, immediate optimistic deletion, stale echo tombstones and failure rollback.');
