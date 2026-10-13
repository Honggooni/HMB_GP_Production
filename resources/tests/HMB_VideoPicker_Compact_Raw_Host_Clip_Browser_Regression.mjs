import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch {
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Playwright required for raw-host clipping verification.");
    console.log("Picker compact raw host browser regression: SKIP (optional Playwright unavailable)"); process.exit(0);
  }
}
const executablePath = process.env.HMB_PICKER_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Chrome required for raw-host clipping verification.");
  console.log("Picker compact raw host browser regression: SKIP (optional browser unavailable)"); process.exit(0);
}
const root = process.env.HMB_PICKER_WIDGET_ROOT || fileURLToPath(new URL("../../", import.meta.url));
const source = fs.readFileSync(path.join(root, "widgets/HMBVideoPickerLibraryWidget_v032.js"));
// Reconstruct the installed Editor's allocator and raw-widget wrapper classes:
// index-CeBXa3xR.js offsets 6861300, 6879538, 6946860. A height-only React
// write does not call controller.update (its effect depends on value/status).
// This is not a live Editor capture. Measure every clipping ancestor.
const html = `<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:#111;color:white;font-family:Arial}
.react-flow__viewport{transform:translate(13px,17px) scale(.9);transform-origin:0 0}
.react-flow__node{position:relative;width:1400px;height:324px;overflow:hidden;background:#090909}
#chrome{height:72px}#stack{position:relative;display:flex;flex-direction:column;height:calc(100% - 72px)}
.flex-shrink-0{flex-shrink:0}.overflow-hidden{overflow:hidden}
.flex{display:flex}.flex-col{flex-direction:column}.flex-row{flex-direction:row}
.items-start{align-items:flex-start}.flex-grow{flex-grow:1}.w-full{width:100%}.h-full{height:100%}.min-h-0{min-height:0}.min-w-0{min-width:0}
#spacer{min-height:0;flex-grow:1;flex-shrink:0;flex-basis:0}
#measurement{position:absolute;left:0;right:0;visibility:hidden;pointer-events:none}
#widget{width:1400px;height:252px}
</style><div class="react-flow__viewport"><div id="shell" class="react-flow__node"><div id="chrome"></div>
<div id="stack" class="relative flex flex-col h-full px-3 pt-2 bg-card">
<div id="layout-row" class="flex-shrink-0 overflow-hidden" style="height:220px;min-height:17px"><div data-parameter-name="HMB_PICKER_STATE" class="flex flex-row items-start"><div id="parameter-content" class="flex flex-col flex-grow overflow-hidden min-w-0"><div class="flex flex-col w-full h-full min-h-0"><div id="widget" class="widget-container flex flex-col w-full h-full min-h-0 nodrag nowheel"></div></div></div></div></div>
<div id="spacer" class="min-h-0 grow shrink-0 basis-0" aria-hidden="true"></div>
<div id="measurement" class="absolute left-0 right-0 pointer-events-none" style="visibility:hidden"></div></div></div></div>
<script type="module">
import mount from '/widget.js';
window.mountPicker=()=>{window.current={language:'ko',runtime_instance_id:'raw-host-clip',state_revision:1,picker_shots:[{workspace_uuid:'a0000000-0000-4000-8000-000000000001',number:1,name:'Shot 1',video_asset_uids:[],selected_video_uids:[]}],active_picker_shot_uuid:'a0000000-0000-4000-8000-000000000001',videos:[]};window.controller=mount(document.getElementById('widget'),{value:window.current,onChange:()=>{}});};
window.measure=()=>{const root=document.querySelector('.hmbvp'),r=root.getBoundingClientRect(),shell=document.getElementById('shell'),s=shell.getBoundingClientRect(),scale=s.height/shell.offsetHeight;let bottom=r.bottom;const clippers=[];for(let p=root.parentElement;p;p=p.parentElement){const css=getComputedStyle(p),rect=p.getBoundingClientRect();if(/^(hidden|clip|auto|scroll)$/.test(css.overflowY)){bottom=Math.min(bottom,rect.bottom);clippers.push({id:p.id||p.className,height:p.offsetHeight,overflow:css.overflowY});}if(p===shell)break;}const host=document.getElementById('widget');return {view:root.dataset.pickerView,rootHeight:root.offsetHeight,rowHeight:document.getElementById('layout-row').offsetHeight,hostHeight:host.offsetHeight,hostInline:host.style.cssText,shellHeight:shell.offsetHeight,clippedPx:Math.max(0,r.bottom-bottom)/scale,blackTailPx:Math.max(0,s.bottom-bottom)/scale,clippers};};
window.ready=true;
</script>`;
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", req.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  res.end(req.url === "/widget.js" ? source : html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const measurements = [];
const cleanupRecords = [];
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1400 } });
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  const settle = async () => { await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve))))); await page.waitForTimeout(80); };
  const record = async name => { const row = {name,...await page.evaluate(() => window.measure())}; measurements.push(row); return row; };
  const viewport = () => page.evaluate(() => ({transform:getComputedStyle(document.querySelector('.react-flow__viewport')).transform,width:innerWidth,height:innerHeight,scrollX,scrollY}));
  const cleanup = async () => page.evaluate(() => {
    window.controller.cleanup(); const host=document.getElementById('widget');
    return {value:host.style.getPropertyValue('min-height'),priority:host.style.getPropertyPriority('min-height'),scheduler:typeof host.__hmbScheduleVideoPickerCompactHostSizing};
  });
  for (const transition of [false, true]) {
    await page.goto(origin); await page.waitForFunction(() => window.ready);
    const viewportBefore = await viewport();
    await page.evaluate(() => window.mountPicker()); await settle();
    assert.equal(await page.evaluate(() => typeof document.getElementById('widget').__hmbScheduleVideoPickerCompactHostSizing), 'function', 'Every live factory must install its guarded compact scheduler.');
    await record(transition ? "before-expanded-transition" : "cold-empty-shot-control");
    if (transition) {
      for(let cycle=0;cycle<5;cycle+=1){
        await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent("dblclick");
        await page.waitForFunction(() => document.querySelector('.hmbvp[data-picker-view="expanded"]'));
        await settle();
        assert.notEqual(await page.evaluate(() => document.getElementById('widget').style.minHeight), '252px', 'Expanded mode must release the compact raw-host minimum.');
        await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent("dblclick");
        await page.waitForFunction(() => document.querySelector('.hmbvp[data-picker-view="compact"]'));
        await settle(); await record('expanded-to-compact-empty-shot-control-'+cycle);
      }
    }
    const prefix = transition ? "expanded-to-compact" : "cold-compact";
    await page.evaluate(() => {
      document.getElementById("layout-row").style.height = "220px";
      const host = document.getElementById("widget");
      host.style.height = "220px";
    });
    await record(prefix + "-late-host-write-immediate");
    await settle(); await record(prefix + "-late-host-write-settled");
    const evidence = process.env.HMB_PICKER_RAW_HOST_REPORT;
    if (evidence && transition) {
      fs.mkdirSync(path.dirname(evidence), {recursive:true});
      await page.screenshot({path:evidence.replace(/\.json$/i,"-before-host-remount.png")});
    }
    for(let index=0;index<5;index+=1){
      await page.evaluate(() => { window.current={...window.current,state_revision:window.current.state_revision+1}; window.controller.update({value:window.current}); });
      await settle(); await record(prefix+'-compact-props-update-'+index);
    }
    // Model the host's outer-title collapse/unmount followed by re-expansion.
    // It reinitializes allocation without changing any authored Picker state.
    const restored = await cleanup(); cleanupRecords.push({name:prefix+'-cleanup',...restored});
    assert.notDeepEqual({value:restored.value,priority:restored.priority},{value:'252px',priority:'important'},'Cleanup must release the owned compact minimum.');
    assert.equal(restored.scheduler,'undefined','Cleanup must detach the compact scheduler.');
    await page.evaluate(() => { document.getElementById("stack").style.display = "none"; });
    await settle();
    await page.evaluate(() => {
      const host = document.getElementById("widget"); host.style.cssText = "width:1400px;height:252px";
      document.getElementById("stack").style.display = "flex"; window.mountPicker();
    });
    await settle(); await record(prefix + "-outer-collapse-expand-remount-control");
    await cleanup();
    assert.deepEqual(await viewport(),viewportBefore,'View transitions and allocation repairs must not move the canvas.');
  }
  for(const refresh of [false,true]){
    await page.goto(origin);await page.waitForFunction(()=>window.ready);await page.evaluate(()=>window.mountPicker());await settle();
    await page.evaluate(()=>document.getElementById('widget').style.setProperty('min-height','19px'));
    if(refresh){
      await page.evaluate(()=>{window.current={...window.current,state_revision:2};window.controller.update({value:window.current});});await settle();
      assert.equal(await page.evaluate(()=>document.getElementById('widget').style.minHeight),'252px');
    }
    const retained=await cleanup();cleanupRecords.push({name:'new-host-minimum-refresh-'+refresh,...retained});
    assert.deepEqual(retained,{value:'19px',priority:'',scheduler:'undefined'},'Cleanup must preserve a newer host minimum, including after props refit.');
  }
  if (process.env.HMB_PICKER_RAW_HOST_REPORT) fs.writeFileSync(process.env.HMB_PICKER_RAW_HOST_REPORT, JSON.stringify({fixture:"installed Editor bundle wrapper classes; controlled height-only raw-host allocation, not live Editor DOM",widgetRoot:root,widgetSha256:createHash("sha256").update(source).digest("hex"),measurements,cleanupRecords,errors},null,2));
  assert.deepEqual(errors, [], "Widget transitions must not raise browser errors.");
  assert.ok(measurements.every(row => row.view === "compact" && row.rootHeight === 252), "Empty Shot 1 must retain its complete 252px authored frame.");
  const clipped = measurements.filter(row => row.clippedPx >= 1);
  assert.deepEqual(clipped, [], "A short raw widget host must not clip the compact Shot, even when its allocator row is protected.");
  console.log("Picker compact raw host browser regression: PASS (empty Shot 1, 5 expanded transitions, 10 compact props updates, late raw-host writes, outer-collapse remount, minimum ownership cleanup, scheduler and viewport).");
} finally {
  await browser?.close(); await new Promise(resolve => server.close(resolve));
}
