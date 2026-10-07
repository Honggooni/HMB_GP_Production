import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import zlib from "node:zlib";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); } catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch {
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Playwright is required for Snapshot navigation verification.");
    console.log("Snapshot navigation stale-frame browser regression: SKIP (optional Playwright unavailable)");
    process.exit(0);
  }
}
const browserPath = process.env.HMB_PICKER_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(browserPath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Chrome is required for Snapshot navigation verification.");
  console.log("Snapshot navigation stale-frame browser regression: SKIP (optional browser unavailable)");
  process.exit(0);
}
const root = fileURLToPath(new URL("../../", import.meta.url));
const widgetPath = process.env.HMB_PICKER_WIDGET_SOURCE || path.join(root, "widgets/HMBVideoPickerLibraryWidget_v032.js");
const source = fs.readFileSync(widgetPath);
const evidence = process.env.HMB_PICKER_BROWSER_EVIDENCE || "";
if (evidence) fs.mkdirSync(evidence, { recursive: true });
function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function png(rgb) {
  const width = 80, height = 45;
  const raw = Buffer.alloc((width * 3 + 1) * height);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1)
    for (let channel = 0; channel < 3; channel += 1) raw[y * (width * 3 + 1) + 1 + x * 3 + channel] = rgb[channel];
  const chunk = (name, data) => {
    const kind = Buffer.from(name), length = Buffer.alloc(4), checksum = Buffer.alloc(4);
    length.writeUInt32BE(data.length); checksum.writeUInt32BE(crc32(Buffer.concat([kind, data])));
    return Buffer.concat([length, kind, data, checksum]);
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(width); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 2;
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), chunk("IHDR", header), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}
const colors = { original: [224, 24, 32], mask: [24, 224, 48], depth: [24, 48, 224], slow: [224, 24, 224], fast: [224, 224, 24] };
const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#111;color:#fff}#widget{width:1400px;height:1100px}
</style><div id="widget"></div><script type="module">
import mount,* as picker from '/widget.js';
window.picker=picker;window.root=document.getElementById('widget');
window.publications=[];window.trace=[];window.phase='initial';
const nativeDecode=HTMLImageElement.prototype.decode;
window.decodeGates=new Map();window.decodeStarted=[];
HTMLImageElement.prototype.decode=function(){
 const name=new URL(this.src,location.href).searchParams.get('decode');
 return nativeDecode.call(this).then(()=>{
  if(!name)return;
  window.decodeStarted.push(name);
  return new Promise(resolve=>window.decodeGates.set(name,resolve));
 });
};
window.releaseDecode=(name)=>{const resolve=window.decodeGates.get(name);if(resolve){window.decodeGates.delete(name);resolve();}};
window.mountPicker=value=>{
 window.root.__hmbVideoPickerExpanded=true;
 window.controller=mount(window.root,{value,onChange:next=>window.publications.push(typeof next==='string'?JSON.parse(next):next)});
};
window.echo=value=>window.controller.update({value,onChange:next=>window.publications.push(typeof next==='string'?JSON.parse(next):next)});
window.sample=()=>{
 const stage=window.root.querySelector('.viewport-stage');
 const img=stage?.querySelector('#picker-snapshot-image');
 let pixel=null;
 if(img&&!img.hidden&&img.complete&&img.naturalWidth>0){
  const canvas=document.createElement('canvas');canvas.width=1;canvas.height=1;
  const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,1,1);pixel=[...ctx.getImageData(0,0,1,1).data].slice(0,3);
 }
 return {phase:window.phase,url:img?.getAttribute('src')||'',hidden:!img||img.hidden,pixel,
  pending:window.root.__hmbPendingPickerSnapshotImage?.url||'',
  uid:window.root.__hmbPendingPickerState?.active_snapshot_uid||window.root.__hmbPickerPaintFirstState?.active_snapshot_uid||'',
  label:window.root.querySelector('.viewport-title small')?.textContent||''};
};
function record(){window.trace.push(window.sample());window.recordFrame=requestAnimationFrame(record);}record();
window.ready=true;
</script>`;
const holds = new Map();
function hold(name) { let release; const wait = new Promise(resolve => { release = resolve; }); holds.set(name, wait); return () => { holds.delete(name); release(); }; }
const releases = [];
const server = http.createServer(async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.url === "/widget.js") { res.setHeader("Content-Type", "text/javascript; charset=utf-8"); res.end(source); return; }
  const name = req.url?.match(/^\/img\/([a-z]+)\.png/)?.[1];
  if (name) {
    if (holds.has(name)) await holds.get(name);
    res.setHeader("Content-Type", "image/png"); res.end(png(colors[name])); return;
  }
  res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
function state(active, revision = 1, aliases = active) {
  const snapshots = ["original", "mask", "depth", "slow", "fast"].map((name, i) => ({
    snapshot_uid: name, artifact_type: i === 0 ? "original" : i === 1 ? "mask" : i === 2 ? "depth" : "original",
    snapshot_batch_uid: "batch-one", video_uid: "video-1", render_video_slot: 1, video_slot: 1,
    frame: 101, path: `C:/diagnostic/${name}.png`, url: `${origin}/img/${name}.png${name === "slow" ? "?decode=slow" : ""}`, created_at_ms: i + 1,
  }));
  const alias = snapshots.find(item => item.snapshot_uid === aliases);
  return {
    language: "en", runtime_instance_id: "snapshot-navigation-stale-frame", state_revision: revision,
    state_published_at_ms: revision, state_writer: "python", frontend_seen_revision: 0,
    scene_path: "C:/diagnostic/scene.mb", scene_request_path: "C:/diagnostic/scene.mb",
    videos: [{ video_uid: "video-1", video_path: "C:/diagnostic/clip.mp4", label: "Clip", frame_metadata: { start_frame: 1, end_frame: 250, frame_count: 250, fps: 24 } }],
    selected_video_uids: ["video-1"], selected_video_uid: "video-1", preview_video_uid: "video-1",
    selected_video_slot: 1, active_slot_count: 1, viewport_mode: "snapshot", active_snapshot_uid: active,
    snapshots, snapshot_active: true, snapshot_frame: alias.frame, snapshot_video_slot: 1,
    snapshot_path: alias.path, snapshot_url: alias.url, snapshot_artifact_type: alias.artifact_type,
  };
}
let browser, page;
const errors = [], checks = [], failures = [];
async function settle(frames = 4) {
  await page.evaluate(count => new Promise(resolve => {
    const next = () => count-- > 0 ? requestAnimationFrame(next) : resolve(); next();
  }), frames);
}
async function visible(name) {
  await page.waitForFunction(expected => {
    const value = window.sample();
    return !value.hidden && value.pixel?.every((v,i)=>v === expected[i]);
  }, colors[name]);
}
async function phase(name) { await page.evaluate(name => {window.phase = name;}, name); }
async function checkFrames(name, allowed) {
  await settle(8);
  const samples = await page.evaluate(name => window.trace.filter(sample => sample.phase === name), name);
  assert.ok(samples.length >= 3, `${name}: must inspect several presented animation frames.`);
  const wrong = samples.filter(sample => sample.hidden || !sample.pixel || !allowed.some(color => sample.pixel.every((value,index) => value === color[index])));
  checks.push({ name, samples: samples.length, wrong });
  if (wrong.length) failures.push(`${name}: stale or blank pixels displayed in ${wrong.length}/${samples.length} frames: ${JSON.stringify(wrong.slice(0,3))}`);
  assert.deepEqual(wrong, [], `${name}: displayed Snapshot pixels regressed after the successor was decoded.`);
}
try {
  browser = await playwright.chromium.launch({ executablePath: browserPath, headless: true });
  page = await browser.newPage({ viewport: { width: 1550, height: 1200 } }); page.setDefaultTimeout(8000);
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  await page.goto(origin); await page.waitForFunction(()=>window.ready);
  await page.evaluate(value => window.mountPicker(value), state("original")); await visible("original");
  // Real Previous/Next listeners publish a draft. A crossed Python progress
  // response has the complete history, but stale root compatibility aliases.
  await page.click("#snapshot-next"); await visible("mask"); await settle();
  await phase("same-frame-mask-stale-original-echo");
  await page.evaluate(value => window.echo(value), {...state("original"), operation_status: "running", status_message: "Delayed native progress"});
  await checkFrames("same-frame-mask-stale-original-echo", [colors.mask]);
  const firstAck = await page.evaluate(()=>window.publications.at(-1));
  assert.ok(firstAck, "Navigation must publish a real local state.");
  await page.evaluate(value => window.echo(value), {...firstAck, state_writer: "python", frontend_seen_revision: firstAck.state_revision});
  await page.click("#snapshot-next"); await visible("depth"); await settle();
  await phase("crossed-mask-ack-after-depth");
  await page.evaluate(value => window.echo(value), {...firstAck, state_writer: "python", frontend_seen_revision: firstAck.state_revision});
  await checkFrames("crossed-mask-ack-after-depth", [colors.depth]);
  // Actual PNG network latency keeps the decoded predecessor visible.
  releases.push(hold("slow"));
  await phase("slow-next-network"); await page.click("#snapshot-next");
  await checkFrames("slow-next-network", [colors.depth]);
  releases.at(-1)(); await page.waitForFunction(()=>window.decodeStarted.includes("slow"));
  await phase("slow-next-decode"); await checkFrames("slow-next-decode", [colors.depth]);
  // A subsequent fast target wins while slow decode completes out of order.
  await page.click("#snapshot-next"); await visible("fast");
  await phase("late-slow-decode-after-fast"); await page.evaluate(()=>window.releaseDecode("slow"));
  await checkFrames("late-slow-decode-after-fast", [colors.fast]);
  await phase("crossed-original-progress-after-fast");
  await page.evaluate(value=>window.echo(value), {...state("original"), operation_status: "running"});
  await checkFrames("crossed-original-progress-after-fast", [colors.fast]);
  // Both ends of history must navigate without a blank/previous identity flash.
  await page.click("#snapshot-next"); await visible("original"); await phase("wrap-fast-to-original");
  await checkFrames("wrap-fast-to-original", [colors.original]);
  await page.click("#snapshot-prev"); await visible("fast"); await phase("wrap-original-to-fast");
  await checkFrames("wrap-original-to-fast", [colors.fast]);
  if (evidence) await page.screenshot({ path: path.join(evidence, "navigation-final.png") });
  assert.deepEqual(errors, [], "Browser exceptions invalidate navigation verification.");
  assert.deepEqual(failures, [], "Snapshot pixel identity must not regress after the successor was decoded.");
  console.log(`Snapshot navigation stale-frame browser regression: PASS (${checks.length} actual PNG/animation-frame scenarios)`);
} finally {
  if (evidence && page) await page.screenshot({ path: path.join(evidence, "navigation-last-presented.png") }).catch(()=>{});
  const trace = page ? await page.evaluate(()=>window.trace).catch(()=>[]) : [];
  if (evidence) fs.writeFileSync(path.join(evidence, "report.json"), JSON.stringify({ widgetPath, checks, failures, errors, trace }, null, 2));
  for (const release of releases) release();
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
