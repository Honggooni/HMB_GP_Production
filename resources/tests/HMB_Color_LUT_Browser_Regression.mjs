import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch { console.log("HMB Color LUT browser regression: SKIP (optional Playwright runtime unavailable)"); process.exit(0); }
}
const executablePath = process.env.HMB_COLOR_LUT_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const ffmpeg = process.env.HMB_COLOR_LUT_TEST_FFMPEG || "C:\\ffmpeg\\bin\\ffmpeg.exe";
if (!fs.existsSync(executablePath) || !fs.existsSync(ffmpeg)) { console.log("HMB Color LUT browser regression: SKIP (optional local browser/FFmpeg unavailable)"); process.exit(0); }
const workspace = fileURLToPath(new URL("../../", import.meta.url));
const nodeSource = fs.readFileSync(path.join(workspace, "HMBColorLUTLibrary.py"), "utf8");
const initialWidth = Number(/COLOR_LUT_WIDGET_WIDTH = (\d+)/.exec(nodeSource)[1]);
const initialHeight = Number(/COLOR_LUT_WIDGET_HEIGHT = (\d+)/.exec(nodeSource)[1]);
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "hmb-color-lut-browser-"));
const videoPath = path.join(temporary, "source.mp4");
const generated = spawnSync(ffmpeg, ["-hide_banner", "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", videoPath], { encoding: "utf8", timeout: 30000 });
assert.equal(generated.status, 0, generated.stderr);
const widgetSource = fs.readFileSync(path.join(workspace, "widgets/HMBColorLUTLibraryWidget.js"));
const videoBytes = fs.readFileSync(videoPath);
const pageSource = `<!doctype html><html><head><meta charset="UTF-8"><style>body{background:#070910;margin:20px}#widget{width:${initialWidth}px;height:${initialHeight}px}</style></head><body><div id="widget"></div><script type="module">
import mount, * as widget from '/widget.js';
window.widget=widget;window.publications=[];window.media=[];window.drawCount=0;
const create=document.createElement.bind(document);document.createElement=(tag,...args)=>{const el=create(tag,...args);if(tag==='video')window.media.push(el);return el;};
const getContext=HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext=function(type,...args){const context=getContext.call(this,type,...args);if(type==='webgl2'&&context&&!context.__testCapture){context.__testCapture=true;const draw=context.drawArrays.bind(context);context.drawArrays=(...args)=>{draw(...args);const pixels=new Uint8Array(this.width*this.height*4);context.readPixels(0,0,this.width,this.height,context.RGBA,context.UNSIGNED_BYTE,pixels);window.lastPixels=pixels;window.drawCount++;window.glError=context.getError();};}return context;};
const catalog={schema:'hmb-shot-routing-catalog',version:1,publisher_instance_uuid:'test-publisher',channel_uuid:'test-channel',generation:1,metadata_sha256:'a'.repeat(64),shots:[1,2,3,4,5].map(number=>({shot_uuid:'shot-'+number,number,name:'Shot '+number,revision:1}))};
window.state=widget.hmbColorLUTState({shot_catalog:catalog,shot:{channel_uuid:'test-channel',shot_uuid:'shot-1'},source:{path:'test-source.mp4',url:location.origin+'/video.mp4',name:'Live source · 320 × 180',shot_uuid:'shot-1',channel_uuid:'test-channel',revision:'r1',fps:24,duration:3}});
window.controller=mount(document.getElementById('widget'),{value:window.state,onChange:(value)=>window.publications.push(value)});
window.originalCanvas=document.querySelector('[data-preview]');window.ready=true;
</script></body></html>`;
const server = http.createServer((req, res) => {
  if (req.url === "/widget.js") { res.setHeader("Content-Type", "text/javascript; charset=utf-8"); res.end(widgetSource); }
  else if (req.url?.startsWith("/video.mp4")) {
    res.setHeader("Content-Type", "video/mp4"); res.setHeader("Accept-Ranges", "bytes");
    const range = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range || "");
    if (range) { const start = Number(range[1]), end = range[2] ? Math.min(videoBytes.length - 1, Number(range[2])) : videoBytes.length - 1;
      res.statusCode = 206; res.setHeader("Content-Range", `bytes ${start}-${end}/${videoBytes.length}`); res.setHeader("Content-Length", end - start + 1); res.end(videoBytes.subarray(start, end + 1)); }
    else { res.setHeader("Content-Length", videoBytes.length); res.end(videoBytes); }
  }
  else { res.setHeader("Content-Type", "text/html; charset=utf-8"); res.end(pageSource); }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true, args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const page = await browser.newPage({ viewport: { width: initialWidth + 60, height: initialHeight + 60 } });
  const initialLayouts = [];
  async function checkInitialLayout(label) {
    const layout = await page.locator('.hmb-color-lut').evaluate(el => {
      const root = el.getBoundingClientRect(), screen = el.querySelector('.cl-screen').getBoundingClientRect();
      const preview = el.querySelector('.cl-preview').getBoundingClientRect(), grade = el.querySelector('.cl-grade').getBoundingClientRect();
      return {width:el.clientWidth, height:el.clientHeight, scrollWidth:el.scrollWidth,
        contentBottom:el.querySelector('.cl-status').getBoundingClientRect().bottom-root.top,
        previewRatio:screen.width/screen.height, panelsAligned:Math.abs(preview.top-grade.top)<1};
    });
    assert.ok(layout.contentBottom <= layout.height, `${label}: output/status must fit at startup: ${JSON.stringify(layout)}`);
    assert.ok(layout.scrollWidth <= layout.width + 1, `${label}: no horizontal scrolling at startup`);
    assert.ok(layout.panelsAligned, `${label}: preview and grade panels remain side by side`);
    assert.ok(Math.abs(layout.previewRatio - 1.6) < .01, `${label}: preserve the preview aspect ratio`);
    initialLayouts.push({label, ...layout});
  }
  page.setDefaultTimeout(10000);
  const failures = []; page.on("pageerror", (error) => failures.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.ready && window.drawCount > 0 && window.media[0].readyState >= 2);
  await checkInitialLayout('Shot / ko');
  assert.equal(await page.evaluate(() => !!window.originalCanvas.getContext("webgl2")), true, "Real WebGL2 renderer must compile and draw.");
  assert.equal(await page.evaluate(() => window.glError), 0, "WebGL LUT/video upload must have no GL errors.");
  assert.equal(await page.locator('[data-wipe]').count(), 0);
  assert.equal(await page.locator('[data-action="export_lut"]').count(), 0);
  assert.equal(await page.locator('[data-project]').isDisabled(), true);
  const screen = await page.locator('.cl-screen').boundingBox();
  const handle = await page.locator('[data-wipe-handle]').boundingBox();
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.mouse.down();
  await page.mouse.move(screen.x + screen.width * .8, handle.y + handle.height / 2, { steps: 8 });
  await page.mouse.up();
  assert.ok(Math.abs(Number(await page.locator('[data-wipe-handle]').getAttribute('aria-valuenow')) - 80) <= 1);
  await page.locator('[data-wipe-handle]').press('Home');
  assert.equal(await page.locator('[data-wipe-handle]').getAttribute('aria-valuenow'), '0');
  await page.locator('[data-wipe-handle]').press('End');
  assert.equal(await page.locator('[data-wipe-handle]').getAttribute('aria-valuenow'), '100');
  await page.evaluate(() => { window.beforeModeDraw = window.drawCount; });
  await page.locator('[data-view="graded"]').click();
  await page.waitForFunction(() => window.drawCount > window.beforeModeDraw);
  await page.evaluate(() => { window.originalPixels = Array.from(window.lastPixels); window.beforeDraw = window.drawCount; });
  await page.locator('[data-adjust="temperature"]').evaluate((el) => { el.value = "11"; el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); });
  await page.waitForFunction(() => window.drawCount > window.beforeDraw);
  const difference = await page.evaluate(() => {
    let sum = 0, changed = 0;
    window.lastPixels.forEach((value, index) => { if (index % 4 !== 3) { const d = Math.abs(value - window.originalPixels[index]); sum += d; if (d > 2) changed++; } });
    return { mean: sum / (window.lastPixels.length * .75), changed, glError: window.glError, sameCanvas: document.querySelector('[data-preview]') === window.originalCanvas };
  });
  assert.ok(difference.mean > 2, `LUT must visibly change actual decoded pixels: ${JSON.stringify(difference)}`);
  assert.ok(difference.changed > 1000); assert.equal(difference.glError, 0); assert.equal(difference.sameCanvas, true);
  await page.locator("[data-play]").click();
  await page.waitForFunction(() => window.media[0].currentTime > .15);
  await page.locator("[data-play]").click();
  const pausedAt = await page.evaluate(() => window.media[0].currentTime);
  await page.waitForTimeout(120);
  assert.equal(await page.evaluate(() => window.media[0].paused), true);
  assert.equal(await page.evaluate(() => window.media[0].currentTime), pausedAt, "Paused playback must stop immediately.");
  await page.locator("[data-seek]").evaluate((el) => { el.value = "24"; el.dispatchEvent(new Event("input", { bubbles: true })); });
  await page.waitForFunction(() => !window.media[0].seeking && Math.abs(window.media[0].currentTime - 1) < .005);
  await page.locator("[data-step]").click();
  await page.waitForFunction(() => !window.media[0].seeking && Math.abs(window.media[0].currentTime - 25 / 24) < .005);
  await page.locator('[data-view="compare"]').click();
  await page.locator("[data-language-toggle]").click();
  assert.equal(await page.locator("[data-language-toggle]").innerText(), "EN");
  assert.equal(await page.locator('[data-text="manual"]').innerText(), "Set output path");
  await checkInitialLayout('Shot / en');
  await page.locator('[data-action="export"]').click();
  assert.deepEqual(await page.evaluate(() => { const c = window.publications.at(-1).__hmb_color_lut_command__; return { action: c.action, temperature: c.state.settings.temperature, precision: c.state.settings.precision_version, shot: c.state.shot.shot_uuid }; }), { action: "export", temperature: 2.75, precision: 2, shot: "shot-1" });
  for (const key of ['exposure','temperature','contrast','saturation','shadows','highlights']) {
    const slider = page.locator(`[data-adjust="${key}"]`);
    assert.equal(await slider.getAttribute('min'), '-12');
    assert.equal(await slider.getAttribute('max'), '12');
    await slider.press('Home');
    for (let step = -12; step <= 12; step++) {
      assert.equal(await slider.inputValue(), String(step));
      const state = await page.evaluate(() => window.publications.at(-1));
      assert.equal(state.settings[key], step/4, `${key}/${step}: native keyboard value reaches the command state`);
      const label = await page.locator(`[data-value="${key}"]`).innerText();
      assert.equal(label, step === 0 ? 'Neutral' : `${step>0?'+':'−'}${Math.abs(step)} stage`);
      if (step < 12) await slider.press('ArrowRight');
    }
  }
  const wideScreenshot = path.join(temporary, "color-lut-production-wide.png");
  await page.screenshot({ path: wideScreenshot, fullPage: true });
  await page.locator("[data-shot-selector]").selectOption("test-channel\u001fshot-2");
  assert.equal(await page.locator("[data-empty]").isVisible(), true);
  assert.equal(await page.evaluate(() => window.publications.at(-1).shot.shot_uuid), "shot-2");
  assert.equal(await page.evaluate(() => document.querySelector('[data-preview]') === window.originalCanvas), true);
  await page.evaluate(() => { const next = structuredClone(window.state); next.revision = window.publications.at(-1).revision + 1; next.shot = { channel_uuid: 'test-channel', shot_uuid: 'shot-2', number: 2, name: 'Shot 2' }; next.source = { ...next.source, shot_uuid: 'shot-2', revision: 'r2', url: location.origin + '/video.mp4?r2' }; window.controller.update({ value: next, onChange: value => window.publications.push(value) }); });
  await page.waitForFunction(() => window.media.length === 2 && window.media[1].readyState >= 2 && document.querySelector('[data-empty]').hidden);
  assert.equal(await page.evaluate(() => window.media[0].getAttribute("src")), null);
  await page.locator("#widget").evaluate((el) => { el.style.width = "430px"; el.style.height = "1100px"; });
  await page.setViewportSize({ width: 480, height: 1160 });
  const narrowScreenshot = path.join(temporary, "color-lut-production-narrow.png");
  await page.screenshot({ path: narrowScreenshot, fullPage: true });
  assert.equal(await page.locator(".hmb-color-lut").evaluate((el) => el.scrollWidth <= el.clientWidth + 1), true, "Narrow node must not overflow horizontally.");
  await page.setViewportSize({width:initialWidth+60, height:initialHeight+60});
  await page.locator('#widget').evaluate((el, size) => {el.style.width=`${size.width}px`;el.style.height=`${size.height}px`;}, {width:initialWidth, height:initialHeight});
  for (const [index, language] of ['ko', 'en'].entries()) {
    await page.evaluate(({language, revision}) => {window.controller.update({value:{...window.state, revision, language, shot:{}, source:{}}, onChange:value=>window.publications.push(value)});}, {language, revision:1000+index});
    await checkInitialLayout(`Only / ${language}`);
  }
  await page.evaluate(() => window.controller.cleanup());
  assert.equal(await page.locator("#widget").innerHTML(), "");
  assert.deepEqual(failures, []);
  console.log(JSON.stringify({ result: "PASS", initialLayouts, realWebGL2: true, difference, decodedPlayback: true, seekFrame: 25, capturedExport: true, retainedCanvas: true, shots: true, screenshots: [wideScreenshot, narrowScreenshot] }, null, 2));
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
