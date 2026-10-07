import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch {
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Playwright required for compact late allocator verification.");
    console.log("Picker compact late allocator browser regression: SKIP (optional Playwright unavailable)");
    process.exit(0);
  }
}
const executablePath = process.env.HMB_PICKER_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Browser required for compact late allocator verification.");
  console.log("Picker compact late allocator browser regression: SKIP (optional browser unavailable)");
  process.exit(0);
}
const root = process.env.HMB_PICKER_WIDGET_ROOT || fileURLToPath(new URL("../../", import.meta.url));
const source = fs.readFileSync(path.join(root, "widgets/HMBVideoPickerLibraryWidget_v032.js"));
// Match the recognized Editor allocator shape, including its 32px short row.
// React replaces inline height through CSSStyleDeclaration.height, removing
// an earlier !important declaration. This test uses the complete live factory.
const html = `<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:#111;color:white;font-family:Arial}
#canvas{width:1800px;height:1400px;overflow:hidden}
.react-flow__viewport{transform:translate(13px,17px) scale(.9);transform-origin:0 0}
.react-flow__node{position:relative;width:1400px;height:324px;overflow:hidden;background:#090909}
#chrome{height:72px}#stack{position:relative;display:flex;flex-direction:column;height:calc(100% - 72px)}
.flex-shrink-0{flex-shrink:0}.overflow-hidden{overflow:hidden}
#spacer{min-height:0;flex-grow:1;flex-shrink:0;flex-basis:0}
#measurement{position:absolute;left:0;right:0;visibility:hidden;pointer-events:none}
#widget{width:1400px;height:252px}
</style><div id="canvas"><div class="react-flow__viewport"><div id="shell" class="react-flow__node"><div id="chrome"></div>
<div id="stack" class="relative flex flex-col h-full px-3 pt-2 bg-card">
<div id="layout-row" class="flex-shrink-0 overflow-hidden" style="height:220px;min-height:17px"><div data-parameter-name="HMB_PICKER_STATE"><div><div id="widget"></div></div></div></div>
<div id="spacer" class="min-h-0 grow shrink-0 basis-0" aria-hidden="true"></div>
<div id="measurement" class="absolute left-0 right-0 pointer-events-none" style="visibility:hidden"></div></div></div></div></div>
<script type="module">
import mount,* as widget from '/widget.js';window.widget=widget;
window.mountPicker=(value)=>{window.current=value;window.publications=[];window.controller=mount(document.getElementById('widget'),{value,onChange:(next)=>window.publications.push(next)});};
window.measure=()=>{const shell=document.getElementById('shell'),row=document.getElementById('layout-row'),root=document.querySelector('.hmbvp');const r=root.getBoundingClientRect(),h=row.getBoundingClientRect(),s=shell.getBoundingClientRect();return {view:root.getAttribute('data-picker-view'),rootHeight:root.offsetHeight,rowHeight:row.offsetHeight,shellHeight:shell.offsetHeight,clippedPx:Math.max(0,r.bottom-Math.min(h.bottom,s.bottom))/.9,rowMinHeight:row.style.getPropertyValue('min-height'),rowMinPriority:row.style.getPropertyPriority('min-height'),rowInlineHeight:row.style.getPropertyValue('height'),rowHeightPriority:row.style.getPropertyPriority('height')};};
window.viewport=()=>({transform:document.querySelector('.react-flow__viewport').style.transform,computedTransform:getComputedStyle(document.querySelector('.react-flow__viewport')).transform,width:innerWidth,height:innerHeight,scrollX,scrollY});
window.ready=true;
</script>`;
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", req.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  res.end(req.url === "/widget.js" ? source : html);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

function stateFor(shotCount, assetCount) {
  const ids = Array.from({ length: shotCount }, (_unused, i) => `a0000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`);
  const videoIds = Array.from({ length: assetCount }, (_unused, i) => `video-${i + 1}`);
  return {
    language: "ko", runtime_instance_id: "compact-late-allocator-regression", state_revision: 1,
    shot_publisher_instance_uuid: "11111111-1111-4111-8111-111111111111", channel_uuid: "22222222-2222-4222-8222-222222222222",
    active_picker_shot_uuid: ids[0],
    shot_selections: ids.map((shot_uuid, i) => ({ shot_uuid, number: i + 1, name: `Shot ${i + 1}`, revision: 1 })),
    picker_shots: ids.map((workspace_uuid, i) => ({ workspace_uuid, bound_shot_uuid: workspace_uuid, number: i + 1, name: `Shot ${i + 1}`,
      video_asset_uids: i === 0 ? videoIds : [], selected_video_uids: i === 0 ? videoIds.slice(0, 2) : [] })),
    videos: videoIds.map((video_uid, i) => ({ video_uid, video_path: `C:/diagnostic/clip-${i + 1}.mp4`, label: `clip-${i + 1}.mp4` })),
  };
}

let browser;
const failures = [];
let matrixCases = 0;
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1800, height: 1400 } });
  page.setDefaultTimeout(6000);
  page.on("pageerror", (error) => failures.push(error.message));
  await page.route("**/*", (route) => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  // Record production observer registrations and callbacks. Compact protection
  // must not observe allocator style and continually write it back to React.
  await page.addInitScript(() => {
    window.observerRecords = [];
    for (const name of ["MutationObserver", "ResizeObserver"]) {
      const Original = window[name];
      if (!Original) continue;
      window[name] = class extends Original {
        constructor(callback) {
          const record = { type: name, targets: [], callbacks: 0, disconnected: false };
          super((entries, observer) => { record.callbacks += 1; callback(entries, observer); });
          this.record = record; window.observerRecords.push(record);
        }
        observe(target, options) {
          this.record.targets.push({ id: target.id, options: options || {} });
          return super.observe(target, options);
        }
        disconnect() { this.record.disconnected = true; return super.disconnect(); }
      };
    }
  });
  const settle = async () => {
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve)))));
    await page.waitForTimeout(60);
  };
  const measure = () => page.evaluate(() => window.measure());
  const expectedHeight = (shotCount) => 252 + (shotCount - 1) * 186;
  const checkVisible = (metrics, shotCount, context) => {
    assert.equal(metrics.view, "compact", `${context}: compact view must remain selected.`);
    assert.equal(metrics.rootHeight, expectedHeight(shotCount), `${context}: Shot count determines the complete authored frame.`);
    assert.ok(metrics.rowHeight >= metrics.rootHeight, `${context}: allocator row ${metrics.rowHeight}px clips authored root ${metrics.rootHeight}px.`);
    assert.ok(metrics.clippedPx < 1, `${context}: bottom clipping was ${metrics.clippedPx}px.`);
  };
  const checkObservers = async (context) => {
    const illegal = await page.evaluate(() => window.observerRecords.flatMap((record) => record.targets.filter((target) => {
      if (!["layout-row", "stack", "shell"].includes(target.id)) return false;
      if (record.type === "ResizeObserver") return true;
      return target.options.attributes && (!target.options.attributeFilter || target.options.attributeFilter.includes("style"));
    }).map((target) => ({ type: record.type, ...target }))));
    assert.deepEqual(illegal, [], `${context}: compact allocator protection must not install a host geometry feedback observer.`);
    const first = await page.evaluate(() => window.observerRecords.reduce((sum, record) => sum + record.callbacks, 0));
    await page.waitForTimeout(120);
    const second = await page.evaluate(() => window.observerRecords.reduce((sum, record) => sum + record.callbacks, 0));
    assert.equal(second, first, `${context}: observer callbacks must settle after allocation.`);
  };
  const mount = async (state, earlyRewrite = false) => {
    await page.goto(origin); await page.waitForFunction(() => window.ready);
    const viewport = await page.evaluate(() => window.viewport());
    await page.evaluate(({ state, earlyRewrite, height }) => {
      window.mountPicker(state);
      if (earlyRewrite) document.getElementById("layout-row").style.height = `${height - 32}px`;
    }, { state, earlyRewrite, height: expectedHeight(state.picker_shots.length) });
    await page.waitForFunction(() => document.querySelector('.hmbvp[data-picker-view="compact"]'));
    await settle(); return viewport;
  };
  const lateRewrite = async (shotCount) => {
    const immediate = await page.evaluate((height) => {
      document.getElementById("layout-row").style.height = `${height - 32}px`;
      return window.measure();
    }, expectedHeight(shotCount));
    checkVisible(immediate, shotCount, "Late host write before another animation frame");
    assert.equal(immediate.rowHeightPriority, "", "The host assignment must actually replace the earlier important height.");
    await settle(); checkVisible(await measure(), shotCount, "Late host write after settled frames");
  };

  for (let shotCount = 1; shotCount <= 5; shotCount += 1) {
    for (const assetCount of [0, 1, 2, 10]) {
      const state = stateFor(shotCount, assetCount);
      const context = `${shotCount} Shot(s), ${assetCount} video(s)`;
      const viewport = await mount(state, true);
      assert.equal(await page.locator('[data-picker-shot-row][data-picker-shot-layout="compact"]').count(), shotCount, `${context}: every requested Shot must render.`);
      assert.equal(await page.locator('.compact-shot-asset[data-video-uid]').count(), assetCount, `${context}: all fixture videos must render in their owning Shot.`);
      checkVisible(await measure(), shotCount, `${context}: cold mount with early host rewrite`);
      await lateRewrite(shotCount);
      await checkObservers(context);
      assert.deepEqual(await page.evaluate(() => window.viewport()), viewport, `${context}: fitting cannot change the canvas viewport.`);
      await page.evaluate(() => window.controller.cleanup());
      assert.deepEqual(await page.evaluate(() => {
        const row = document.getElementById("layout-row");
        return { value: row.style.getPropertyValue("min-height"), priority: row.style.getPropertyPriority("min-height") };
      }), { value: "17px", priority: "" }, `${context}: cleanup must restore the original host minimum.`);
      matrixCases += 1;
    }
  }

  for (const [shotCount, assetCount] of [[1, 2], [5, 10]]) {
    const state = stateFor(shotCount, assetCount);
    const viewport = await mount(state);
    await lateRewrite(shotCount);
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent("dblclick");
    await page.waitForFunction(() => document.querySelector('.hmbvp[data-picker-view="expanded"]'));
    await settle();
    const expanded = await measure();
    assert.notEqual(expanded.rowMinHeight, `${expectedHeight(shotCount)}px`, "Expanded authoring must release the compact minimum.");
    assert.ok(expanded.rowHeight > expectedHeight(shotCount), "Expanded authoring must receive its full host row.");
    await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent("dblclick");
    await page.waitForFunction(() => document.querySelector('.hmbvp[data-picker-view="compact"]'));
    await settle(); await lateRewrite(shotCount);
    await checkObservers("Expanded -> compact lifecycle");
    assert.deepEqual(await page.evaluate(() => window.viewport()), viewport, "View transitions cannot move the canvas viewport.");
    await page.evaluate(() => window.controller.cleanup());
    assert.equal(await page.evaluate(() => document.getElementById("layout-row").style.minHeight), "17px", "Transition cleanup restores the original host minimum.");
    // JSON persistence is a fresh factory mount with the same saved props.
    await mount(JSON.parse(JSON.stringify(state)), true);
    await lateRewrite(shotCount);
    await page.evaluate(() => window.controller.cleanup());
    assert.equal(await page.evaluate(() => document.getElementById("layout-row").style.minHeight), "17px", "Reload cleanup restores the original host minimum.");
  }

  for (const refreshProtection of [false, true]) {
    await mount(stateFor(1, 2));
    await page.evaluate((refreshProtection) => {
      const row = document.getElementById("layout-row");
      row.style.setProperty("min-height", "19px");
      if (refreshProtection) window.widget.hmbApplyVideoPickerCompactGeometry(document.getElementById("widget"), 252);
    }, refreshProtection);
    if (refreshProtection) {
      const metrics = await measure();
      assert.equal(metrics.rowMinHeight, "252px");
      assert.equal(metrics.rowMinPriority, "important");
    }
    await page.evaluate(() => window.controller.cleanup());
    assert.equal(await page.evaluate(() => document.getElementById("layout-row").style.minHeight), "19px", "Cleanup preserves a newer host-authored minimum, including after protection refresh.");
  }
  assert.deepEqual(failures, [], "Complete widget mounts and view transitions must not produce browser errors.");
  console.log(`Picker compact late allocator browser regression: PASS (${matrixCases} cold mount cases, 1-5 Shots x 0/1/2/10 videos, early/late allocator writes, expanded/compact, save/reload, minimum restoration, no host feedback or viewport changes).`);
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
