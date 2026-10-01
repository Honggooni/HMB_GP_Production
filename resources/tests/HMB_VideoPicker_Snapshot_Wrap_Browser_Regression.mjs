import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch {
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Playwright required");
    console.log("Picker Snapshot wrap browser: SKIP (Playwright unavailable)");
    process.exit(0);
  }
}
const executablePath = process.env.HMB_PICKER_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Browser required");
  console.log("Picker Snapshot wrap browser: SKIP (browser unavailable)");
  process.exit(0);
}

const svg = (color) => `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="${color}"/></svg>`;
const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#090c16}.viewport-stage{width:640px;height:360px;background:#000;position:relative}
.preview-image,.preview-video,.viewport-empty{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
[hidden]{display:none!important}</style><div id="root"><section class="viewport-panel"><div class="viewport-title"><small>(Snapshot)</small></div><div class="viewport-stage"><video id="picker-video" hidden></video><img id="picker-snapshot-image" class="preview-image"><div class="viewport-empty" hidden></div></div><input id="video-frame-number" max="250"><input id="video-seek" max="250"><b id="frame-info-frame"></b><b id="frame-info-time"></b></section></div><script type="module">
import * as picker from '/widget.js';
window.picker=picker;window.root=document.getElementById('root');
document.getElementById('picker-snapshot-image').src=location.origin+'/img/last.svg';
window.navigate=(name,frame)=>picker.hmbApplySnapshotNavigationFeedback(window.root,{snapshot_uid:name,frame,url:location.origin+'/img/'+name+'.svg'},{snapshot:'Snapshot'},1,24);
window.ready=true;
</script>`;
let releaseFirst;
let releaseLastWrap;
const holdFirst = new Promise((resolve) => { releaseFirst = resolve; });
const holdLastWrap = new Promise((resolve) => { releaseLastWrap = resolve; });
const server = http.createServer(async (request, response) => {
  const pathname = new URL(request.url, "http://127.0.0.1").pathname;
  response.setHeader("Cache-Control", "no-store");
  if (pathname === "/widget.js") {
    response.setHeader("Content-Type", "text/javascript; charset=utf-8");
    response.end(source);
    return;
  }
  if (pathname === "/img/first.svg") await holdFirst;
  if (pathname === "/img/last-wrap.svg") await holdLastWrap;
  if (pathname.startsWith("/img/")) {
    response.setHeader("Content-Type", "image/svg+xml");
    response.end(svg(pathname.includes("first") ? "#39b54a" : "#eb4034"));
    return;
  }
  response.setHeader("Content-Type", "text/html; charset=utf-8");
  response.end(html);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 800, height: 500 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(() => window.ready && document.querySelector("#picker-snapshot-image")?.naturalWidth > 0);
  const original = await page.evaluate(() => {
    window.originalImage = document.querySelector("#picker-snapshot-image");
    return { src: window.originalImage.src, visible: getComputedStyle(window.originalImage).display !== "none" };
  });
  assert.ok(original.visible);

  // Last -> first: hold the HTTP response and assert the old DOM/image remains
  // visible, then release and wait for the decoded element to replace it.
  await page.evaluate(() => window.navigate("first", 1));
  await page.waitForFunction(() => window.root.__hmbPendingPickerSnapshotImage?.url.endsWith("/img/first.svg"));
  const waitingFirst = await page.evaluate(() => ({
    sameNode: document.querySelector("#picker-snapshot-image") === window.originalImage,
    src: document.querySelector("#picker-snapshot-image").src,
    visible: getComputedStyle(window.originalImage).display !== "none",
    frame: document.querySelector("#frame-info-frame").textContent,
  }));
  assert.equal(waitingFirst.sameNode, true);
  assert.equal(waitingFirst.src, original.src);
  assert.equal(waitingFirst.visible, true);
  assert.equal(waitingFirst.frame, "1 / 250");
  releaseFirst();
  await page.waitForFunction(() => document.querySelector("#picker-snapshot-image")?.src.endsWith("/img/first.svg") && document.querySelector("#picker-snapshot-image")?.naturalWidth > 0);

  // First -> last: a second uncached, delayed URL has the same atomic behavior.
  const firstImage = await page.evaluate(() => {
    window.firstImage = document.querySelector("#picker-snapshot-image");
    return window.firstImage.src;
  });
  await page.evaluate(() => window.navigate("last-wrap", 250));
  await page.waitForFunction(() => window.root.__hmbPendingPickerSnapshotImage?.url.endsWith("/img/last-wrap.svg"));
  const waitingLast = await page.evaluate(() => ({
    sameNode: document.querySelector("#picker-snapshot-image") === window.firstImage,
    src: document.querySelector("#picker-snapshot-image").src,
    visible: getComputedStyle(window.firstImage).display !== "none",
  }));
  assert.equal(waitingLast.sameNode, true);
  assert.equal(waitingLast.src, firstImage);
  assert.equal(waitingLast.visible, true);
  releaseLastWrap();
  await page.waitForFunction(() => document.querySelector("#picker-snapshot-image")?.src.endsWith("/img/last-wrap.svg") && document.querySelector("#picker-snapshot-image")?.naturalWidth > 0);
  assert.equal(await page.evaluate(() => document.querySelector("#picker-snapshot-image")?.hidden), false);
  assert.deepEqual(errors, []);
  console.log("Picker Snapshot wrap browser: PASS (both directions keep decoded frame until atomic replacement)");
} finally {
  releaseFirst();
  releaseLastWrap();
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
