import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import * as widget from "../../widgets/HMBImageAssetLibraryWidget.js";

const pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j14sAAAAASUVORK5CYII=";
const state = widget.hmbNormalizeImageAssetState({
  language: "en",
  assets: Array.from({ length: 165 }, (_, index) => ({
    asset_library_id: `page-${index}`,
    source_uid: `project:page-${index}`,
    source_kind: "project",
    registered: true,
    asset_id: `page-${index}`,
    image_name: `Image ${index}`,
    relative_path: `Images/image-${index}.png`,
    thumbnail_url: pixel,
    selected: [0, 80, 164].includes(index),
    selection_order: index === 0 ? 1 : index === 80 ? 2 : index === 164 ? 3 : 0,
  })),
});
const first = widget.hmbImageAssetCatalogWindow(state);
const second = widget.hmbImageAssetCatalogWindow(state, undefined, 80);
const third = widget.hmbImageAssetCatalogWindow(state, undefined, 160);
assert.equal(first.limit, 80);
assert.deepEqual([first.rendered.length, second.rendered.length, third.rendered.length], [80, 80, 5]);
assert.deepEqual([...first.rendered, ...second.rendered, ...third.rendered].map(a => a.asset_library_id), state.assets.map(a => a.asset_library_id));
assert.equal(widget.hmbImageAssetCatalogWindow(state, 1000).rendered.length, 80);
assert.equal(widget.hmbImageAssetCatalogWindow(state, undefined, 9999).offset, 160);
assert.match(widget.hmbRenderImageAssetGrid(state).markup, /1-80\/165/);
assert.match(widget.hmbRenderImageAssetGrid(state, undefined, 80).markup, /81-160\/165/);
assert.equal((widget.hmbRenderImageAssetGrid(state).markup.match(/data-asset-key=/g) || []).length, 80);
console.log("PASS ImageAsset 80-card paging: first page, next page, final page, bounded render, complete ordered catalog.");

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const executablePath = process.env.HMB_IMAGE_ASSET_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const widgetSource = fs.readFileSync(new URL("../../widgets/HMBImageAssetLibraryWidget.js", import.meta.url));

// DOM contracts copied from the installed Griptape editor's B3/SWn and native
// ParameterList row builders (main-BJSE77TR.js). In particular an Add item
// ghost row has its parameter name as a class, but no data-parameter-name;
// a collapsed header has data-parameter-name with the same ghost handle id.
// Host connection handlers and stable child UUIDs are deliberately retained.
const html = `<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#111;color:#eee}.react-flow__node{position:relative;width:1100px}.native{height:120px}.native-row{position:relative;height:36px;margin-left:20px}.react-flow__handle{position:absolute;left:0;top:8px;width:16px;height:16px}.native-label{padding-left:30px}.widget{height:780px}
</style><div class="react-flow__node" data-id="asset-node"><div class="native"></div><div id="widget" class="widget"></div></div><div class="react-flow__node" data-id="other-node"><div class="native"></div></div>
<script type="module">
import mount,* as api from '/widget.js';
window.api=api;window.writes=[];window.nativeClicks=0;
const handle=(node,id,color)=>'<div class="react-flow__handle react-flow__handle-left target connectable connectablestart connectableend" data-nodeid="'+node+'" data-handleid="'+id+'" data-handlepos="left"><svg fill="none" width="100%" height="100%" viewBox="0 0 16 16" style="pointer-events:none"><circle cx="8" cy="8" r="7" fill="transparent" stroke="'+color+'" stroke-width="2"/></svg></div>';
window.nativeMarkup=(node,expanded)=>{const ghost='ghost-item-'+node+'-IMAGE_IMPORT_IN';const parent=handle(node,'IMAGE_IMPORT_IN','#3b82f6');const row=(id,content)=>'<div class="native-row" data-param-node="'+node+'" data-parameter-name="'+id+'">'+content+'</div>';return expanded?row('IMAGE_IMPORT_IN',parent+'<span class="native-label">IMAGE_IMPORT_IN</span>')+row('IMAGE_IMPORT_IN_ParameterListUniqueParamID_stable',handle(node,'IMAGE_IMPORT_IN_ParameterListUniqueParamID_stable','#ef4444')+'<span class="native-label">Item 1</span><button title="Remove item">X</button>')+'<div class="native-row '+ghost+'">'+handle(node,ghost,'#ef4444')+'<span class="native-label">Add item to IMAGE_IMPORT_IN</span></div>':row(ghost,handle(node,ghost,'#3b82f6')+'<span class="native-label">IMAGE_IMPORT_IN</span>')+'<div style="position:absolute;opacity:0;pointer-events:none">'+row('IMAGE_IMPORT_IN',parent)+'</div>';};
window.setNativeExpanded=(expanded)=>{const native=document.querySelector('[data-id="asset-node"] .native');native.innerHTML=window.nativeMarkup('asset-node',expanded);native.querySelectorAll('.react-flow__handle').forEach(el=>el.addEventListener('mousedown',()=>window.nativeClicks++));};
window.setNativeExpanded(true);document.querySelector('[data-id="other-node"] .native').innerHTML=window.nativeMarkup('other-node',true);
window.mountWidget=(state)=>{window.container=document.getElementById('widget');window.controller=mount(window.container,{value:state,onChange:value=>window.writes.push(JSON.parse(value))});};window.ready=true;
</script>`;
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", req.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  res.end(req.url === "/widget.js" ? widgetSource : html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1250, height: 1050 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(() => window.ready);
  const parent = page.locator('[data-id="asset-node"] .target[data-handleid="IMAGE_IMPORT_IN"]');
  const ghost = page.locator('[data-id="asset-node"] .target[data-handleid="ghost-item-asset-node-IMAGE_IMPORT_IN"]');
  const parentSize = await parent.boundingBox();
  await page.evaluate(state => window.mountWidget(state), state);
  await page.waitForFunction(() => document.querySelector('[data-hmb-image-import-universal]'));
  assert.equal(await parent.evaluate(el => getComputedStyle(el).visibility), "hidden");
  assert.deepEqual(await parent.boundingBox(), parentSize, "Hidden root retains geometry for existing edges.");
  assert.equal(await ghost.locator("circle").getAttribute("stroke"), "#ef4444");
  assert.equal(await ghost.locator("[data-hmb-image-import-universal]").getAttribute("stroke"), "#3b82f6");
  assert.equal(await page.locator('[data-id="other-node"] [data-hmb-image-import-universal]').count(), 0);
  assert.equal(await page.locator('[data-id="other-node"] [data-handleid="IMAGE_IMPORT_IN"]').evaluate(el => getComputedStyle(el).visibility), "visible");
  assert.equal(await page.locator('[data-handleid="IMAGE_IMPORT_IN_ParameterListUniqueParamID_stable"] [data-hmb-image-import-universal]').count(), 0);
  await ghost.dispatchEvent("mousedown");
  assert.equal(await page.evaluate(() => window.nativeClicks), 1, "Native event handlers remain connected.");

  const cardIds = () => page.locator('#widget [data-asset-key]').evaluateAll(elements => elements.map(el => el.getAttribute("data-asset-key")));
  assert.deepEqual(await cardIds(), state.assets.slice(0, 80).map(a => a.asset_library_id));
  await page.locator("[data-assets-more]").click();
  assert.deepEqual(await cardIds(), state.assets.slice(80, 160).map(a => a.asset_library_id));
  await page.locator("[data-assets-more]").click();
  assert.deepEqual(await cardIds(), state.assets.slice(160).map(a => a.asset_library_id));
  await page.locator("[data-assets-previous]").click();
  assert.deepEqual(await cardIds(), state.assets.slice(80, 160).map(a => a.asset_library_id));
  assert.equal(await page.evaluate(() => window.writes.length), 0, "Paging and handle decoration never publish state.");
  assert.deepEqual(await page.evaluate(() => window.container.__hmbImageAssetLatestState.assets.filter(a => a.selected).map(a => a.source_uid)), state.assets.filter(a => a.selected).map(a => a.source_uid));

  for (let cycle = 0; cycle < 5; cycle++) {
    await page.evaluate(() => window.setNativeExpanded(false));
    await page.waitForFunction(() => document.querySelectorAll('[data-id="asset-node"] [data-hmb-image-import-universal]').length === 0);
    assert.equal(await ghost.evaluate(el => getComputedStyle(el).visibility), "visible", "Collapsed root remains available.");
    await page.evaluate(() => window.setNativeExpanded(true));
    await page.waitForFunction(() => document.querySelectorAll('[data-id="asset-node"] [data-hmb-image-import-universal]').length === 1);
    assert.equal(await parent.evaluate(el => getComputedStyle(el).visibility), "hidden");
  }
  // React may recreate only the SVG beneath the existing handle.
  await ghost.locator("svg").evaluate(svg => { svg.innerHTML = '<circle cx="8" cy="8" r="7" fill="transparent" stroke="#ef4444" stroke-width="2"/>'; });
  await page.waitForFunction(() => document.querySelectorAll('[data-id="asset-node"] [data-hmb-image-import-universal]').length === 1);
  // A second mount in the same node must not remove the first owner's styling.
  await page.evaluate(() => { window.peer = document.createElement('div'); window.container.parentElement.appendChild(window.peer); window.peerCleanup = window.api.hmbInstallImageAssetImportHandleDecoration(window.peer); });
  await page.evaluate(() => window.controller.cleanup());
  assert.equal(await parent.evaluate(el => getComputedStyle(el).visibility), "hidden");
  await page.evaluate(() => { window.peerCleanup(); window.peerCleanup(); window.peer.remove(); });
  assert.equal(await parent.evaluate(el => getComputedStyle(el).visibility), "visible");
  assert.equal(await ghost.locator("[data-hmb-image-import-universal]").count(), 0);
  assert.equal(await ghost.locator("circle").getAttribute("stroke"), "#ef4444");
  await page.evaluate(() => window.setNativeExpanded(true));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await ghost.locator("[data-hmb-image-import-universal]").count(), 0, "Cleanup disconnects the observer.");
  assert.deepEqual(errors, []);
  console.log("PASS ImageAsset browser: 80/80/5 paging; ordered selection; native parent, Add item and child isolation; collapse/expand; SVG replacement; shared owners; exact cleanup; no state writes.");
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
