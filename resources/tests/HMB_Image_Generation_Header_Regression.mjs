/** Actual Chrome DOM; static image header cannot change native controls/state. */
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const widgetPath = path.join(root, "widgets/HMBImageGenerationWidget.js");
const source = fs.readFileSync(widgetPath, "utf8");
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const out = path.join(root, "reports/image-generation-header-gap-20261021");
fs.mkdirSync(out, { recursive: true });
const report = {
  passed: false, cases: [], external_page_requests: 0, widget_commands: 0,
  live_editor_actions: 0, paid_calls: 0,
  source_sha256: crypto.createHash("sha256").update(source).digest("hex"),
  screenshot_kind: "synthetic fixture of the actual widget in isolated Chrome; no live Griptape claim",
};
assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest|WebSocket|MutationObserver|ResizeObserver|setInterval|setTimeout)\b/);
assert.doesNotMatch(source, /\b(?:onChange|onCommand)\b/);
// Approved DOM-only portal lifecycle; provider/engine transports remain forbidden.
const listenedEvents = [...source.matchAll(/(?:addEventListener|removeEventListener)\?\.\("([^"]+)"/g)].map(match => match[1]);
assert.deepEqual(listenedEvents, ["hmb-color-lut-header-state", "hmb-color-lut-header-state"]);
assert.deepEqual([...source.matchAll(/announce\("([^"]+)"\)/g)].map(match => match[1]), ["retire", "ready"]);
assert.match(source, /new win\.CustomEvent\(`hmb-color-lut-header-\$\{phase\}`/);
const moduleUrl = "data:text/javascript;base64," + Buffer.from(source).toString("base64");
const browser = await playwright.chromium.launch({
  headless: true,
  executablePath: process.env.HMB_WIDGET_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  args: ["--disable-background-networking", "--no-first-run", "--disable-extensions"],
});
try {
  const page = await browser.newPage({ viewport: { width: 1320, height: 720 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => { report.external_page_requests++; return route.abort(); });
  await page.setContent(`<!doctype html><meta charset="utf-8"><style>
    body{margin:24px;background:#080b13;color:#e6edf7;font:14px system-ui}
    #host{width:440px;min-width:0;box-sizing:border-box}
    #carrier{width:100%;min-width:0}#native{height:28px;width:200px}
    #neighbor{padding:7px;color:rgb(120,130,140)}
  </style><section id="host"><div id="carrier"></div>
  <input id="native" value="Preserved native input"><button id="native-action">Native action</button></section>
  <span id="neighbor">Unrelated native content</span>`);
  await page.evaluate(async url => {
    window.headerModule = await import(url);
    window.forbiddenContext = new Proxy({}, { get() { throw new Error("Static header accessed engine context"); } });
    window.mount = () => headerModule.default(document.querySelector("#carrier"), forbiddenContext);
    window.handle = mount();
    window.originalHeader = document.querySelector(".hmb-image-generation-header");
    window.originalNative = document.querySelector("#native");
    window.nativeClicks = 0;
    document.querySelector("#native-action").addEventListener("click", () => nativeClicks++);
  }, moduleUrl);
  assert.equal(await page.locator(".hmb-image-generation-header__badge").textContent(), "IG");
  assert.equal(await page.locator(".hmb-image-generation-header__title").textContent(), "HMBImageGeneration");
  assert.equal(await page.locator(".hmb-image-generation-header button,.hmb-image-generation-header input,.hmb-image-generation-header select").count(), 0);
  assert.equal(await page.locator(".hmb-image-generation-header").evaluate(node => getComputedStyle(node).backgroundImage.includes("linear-gradient")), true);
  assert.equal(await page.locator(".hmb-image-generation-header__badge").evaluate(node => getComputedStyle(node).color), "rgb(244, 114, 182)");
  report.cases.push("64px HMB jewel-pink gradient, IG badge and exact title; no controls or context access");

  const geometries = [];
  for (const width of [440, 600, 800, 1200]) {
    const geometry = await page.evaluate(width => {
      const host = document.querySelector("#host");
      host.style.width = width + "px";
      const header = document.querySelector(".hmb-image-generation-header");
      const title = document.querySelector(".hmb-image-generation-header__title");
      const rect = header.getBoundingClientRect();
      return { width, height: rect.height, renderedWidth: rect.width,
        hostWidth: host.clientWidth, hostScrollWidth: host.scrollWidth,
        titleClipped: title.scrollWidth > title.clientWidth,
        headerOverflow: header.scrollWidth > header.clientWidth };
    }, width);
    assert.equal(geometry.height, 64);
    assert.equal(geometry.renderedWidth, width);
    assert.equal(geometry.hostScrollWidth, geometry.hostWidth);
    assert.equal(geometry.titleClipped, false);
    assert.equal(geometry.headerOverflow, false);
    geometries.push(geometry);
  }
  report.geometries = geometries;
  report.cases.push("440/600/800/1200px actual Chrome geometry has fixed 64px height and no title/bottom/horizontal clipping");

  // Frontend d8/YTr mounts into a 40px carrier for render(-1). Jkr measures
  // its wrapper; qkr allocates visible row height independently. This reproduces
  // that DOM boundary, not a supposed SDK hardcoded 300px minimum.
  const nodeSource = fs.readFileSync(path.join(root, "HMBImageGeneration.py"), "utf8");
  const metadata = nodeSource.match(/name="HMB_IMAGE_GENERATION_UI"[\s\S]*?ui_options=\{([\s\S]*?)\}\)\)/)?.[1] || "";
  for (const key of ["expandable", "resizable"]) assert.match(metadata, new RegExp(`"${key}": False`));
  for (const key of ["height", "min_height", "max_height", "widget_height"]) assert.match(metadata, new RegExp(`"${key}": 64`));
  assert.match(metadata, /"compact": True/);
  const hostBoundary = await page.evaluate(() => {
    const measure = document.createElement("div");
    measure.style.cssText = "position:absolute;left:0;right:0;visibility:hidden;pointer-events:none;width:600px";
    const ref = document.createElement("div"), wrapper = document.createElement("div"), carrier = document.createElement("div");
    wrapper.style.cssText = "display:flex;flex-direction:column;width:100%;height:100%;min-height:0";
    carrier.className = "widget-container flex flex-col w-full h-full min-h-0 nodrag nowheel";
    carrier.style.cssText = "display:flex;flex-direction:column;width:100%;height:40px;min-height:0";
    wrapper.append(carrier); ref.append(wrapper); measure.append(ref); document.body.append(measure);
    const before = ref.getBoundingClientRect().height;
    const h = headerModule.default(carrier, forbiddenContext);
    const measured = Math.ceil(ref.getBoundingClientRect().height);
    const outer = document.createElement("div"); outer.style.cssText = `flex-shrink:0;overflow:hidden;height:${measured}px`;
    measure.remove(); const body = document.createElement("div");
    body.style.cssText = "display:flex;flex-direction:column;gap:12px;width:600px";
    const native = document.createElement("input"); native.value = "Preserved next native control";
    outer.append(wrapper); body.append(outer, native); document.body.append(body);
    const gap = native.getBoundingClientRect().top - carrier.querySelector(".hmb-image-generation-header").getBoundingClientRect().bottom;
    const result = { before, measured, visibleRowHeight: outer.getBoundingClientRect().height, gap };
    h.cleanup(); body.remove(); return result;
  });
  assert.deepEqual(hostBoundary, { before: 40, measured: 64, visibleRowHeight: 64, gap: 12 });
  report.host_boundary = hostBoundary;
  report.cases.push("40px hidden measurement carrier becomes 64px; non-expandable visible row has 12px native-control gap");

  report.zoom_geometries = [];
  for (const zoom of [0.5, 0.75, 1, 1.25, 1.5]) {
    for (const width of [440, 600, 800, 1200]) {
      const geometry = await page.evaluate(({ zoom, width }) => {
        const host = document.querySelector("#host");
        host.style.width = width + "px"; host.style.transformOrigin = "top left"; host.style.transform = `scale(${zoom})`;
        const header = document.querySelector(".hmb-image-generation-header");
        return { zoom, width, height: header.getBoundingClientRect().height,
          paintedWidth: header.getBoundingClientRect().width, horizontalOverflow: header.scrollWidth > header.clientWidth };
      }, { zoom, width });
      assert.equal(geometry.height, 64 * zoom); assert.equal(geometry.paintedWidth, width * zoom);
      assert.equal(geometry.horizontalOverflow, false); report.zoom_geometries.push(geometry);
    }
  }
  await page.evaluate(() => { document.querySelector("#host").style.transform = ""; });
  report.cases.push("440/600/800/1200px at 0.5/0.75/1/1.25/1.5 canvas zoom retains logical 64px header without clipping");

  await page.locator("#native").focus();
  assert.equal(await page.evaluate(async () => {
    const mutations = [];
    const observer = new MutationObserver(items => mutations.push(...items));
    observer.observe(document.querySelector("#carrier"), { attributes: true, attributeFilter: ["style"] });
    for (let index = 0; index < 1000; index++) {
      handle.update({ disabled: index % 2 === 0, locked: true, value: { job_id: "different-task-" + index } });
      if (mount() !== handle) return false;
    }
    await Promise.resolve(); observer.disconnect();
    window.repeatedStyleMutations = mutations.length;
    return mutations.length === 0 && document.activeElement === originalNative
      && document.querySelector("#native") === originalNative
      && originalNative.value === "Preserved native input"
      && document.querySelector(".hmb-image-generation-header") === originalHeader
      && document.querySelectorAll(".hmb-image-generation-header").length === 1;
  }), true);
  report.repeated_update_style_mutations = await page.evaluate(() => repeatedStyleMutations);
  assert.equal(await page.locator("#neighbor").evaluate(node => getComputedStyle(node).color), "rgb(120, 130, 140)");
  await page.locator("#native-action").click();
  assert.equal(await page.evaluate(() => nativeClicks), 1);
  report.cases.push("1000 update/remount calls, disabled/lock/task changes preserve header identity, native focus/value and native action; CSS is scoped");

  assert.equal(await page.evaluate(() => {
    const carrier = document.querySelector("#carrier");
    const unrelated = document.createElement("span");
    unrelated.textContent = "Unrelated carrier child";
    carrier.appendChild(unrelated);
    handle.cleanup(); handle.cleanup();
    if (carrier.querySelector(".hmb-image-generation-header") || unrelated.parentNode !== carrier) return false;
    const fresh = mount();
    handle.cleanup();
    if (!carrier.querySelector(".hmb-image-generation-header") || fresh === handle) return false;
    fresh.cleanup();
    const absent = headerModule.default(null, forbiddenContext);
    absent.update(); absent.cleanup();
    return unrelated.parentNode === carrier && document.querySelector("#native") === originalNative;
  }), true);
  report.cases.push("Idempotent own-node cleanup, safe remount/stale cleanup, null carrier and untouched neighboring/native DOM");

  const restoration = await page.evaluate(() => {
    const results = [];
    for (const original of [
      "height:40px;min-height:0;max-height:720px;flex:1 1 40px;box-sizing:content-box",
      "height:40px!important;min-height:2px;flex-grow:0;flex-shrink:1;flex-basis:300px!important;box-sizing:content-box",
    ]) {
      const carrier = document.createElement("div"); carrier.style.cssText = original; document.body.append(carrier);
      const keys = ["height", "min-height", "max-height", "flex-grow", "flex-shrink", "flex-basis", "box-sizing"];
      const snapshot = () => Object.fromEntries(keys.map(key => [key, [carrier.style.getPropertyValue(key), carrier.style.getPropertyPriority(key)]]));
      const before = snapshot(); const h = headerModule.default(carrier, forbiddenContext); h.cleanup(); h.cleanup();
      results.push({ before, after: snapshot() }); carrier.remove();
    }
    const carrier = document.createElement("div"); carrier.style.cssText = "height:40px;flex:1 1 40px"; document.body.append(carrier);
    const h = headerModule.default(carrier, forbiddenContext);
    carrier.style.setProperty("height", "87px", "important"); carrier.style.setProperty("flex-basis", "91px", "important");
    h.cleanup(); const external = { height: carrier.style.getPropertyValue("height"), basis: carrier.style.getPropertyValue("flex-basis") };
    const fresh = headerModule.default(carrier, forbiddenContext); carrier.querySelector(".hmb-image-generation-header").remove();
    const remount = headerModule.default(carrier, forbiddenContext); fresh.cleanup();
    const remounted = carrier.querySelectorAll(".hmb-image-generation-header").length; remount.cleanup(); carrier.remove();
    return { results, external, remounted };
  });
  for (const item of restoration.results) assert.deepEqual(item.after, item.before);
  assert.deepEqual(restoration.external, { height: "87px", basis: "91px" }); assert.equal(restoration.remounted, 1);
  report.carrier_cleanup = restoration;
  report.cases.push("Carrier cleanup restores original inline values and priorities, preserves external-owner edits, and supports deleted-header remount");

  const fixture = `<!doctype html><html lang="ko"><meta charset="utf-8"><title>HMB Image Generation header fixture</title>
    <style>body{margin:24px;background:#080b13;color:#b6c3d8;font:14px system-ui}
    main{display:grid;gap:20px}section{max-width:100%;box-sizing:border-box}small{display:block;margin:0 0 7px}
    h1{font-size:17px;color:#e6edf7;margin:0 0 20px}</style>
    <h1>HMB Image Generation · isolated header fixture</h1><main>
    ${[440, 600, 800, 1200].map(width => `<section style="width:${width}px"><small>${width}px</small><div class="fixture-header"></div></section>`).join("")}
    </main><script type="module">import mount from "${moduleUrl}";for(const element of document.querySelectorAll('.fixture-header'))mount(element,{});</script></html>`;
  fs.writeFileSync(path.join(out, "header-fixture.html"), fixture);
  await page.setContent(fixture);
  await page.waitForFunction(() => document.querySelectorAll(".hmb-image-generation-header").length === 4);
  await page.screenshot({ path: path.join(out, "header-440-1200.png"), fullPage: true });
  assert.deepEqual(errors, []);
  assert.equal(report.external_page_requests, 0);
  report.passed = true;
} finally {
  await browser.close();
  fs.writeFileSync(path.join(out, "header-regression.json"), JSON.stringify(report, null, 2) + "\n");
}
console.log(JSON.stringify({ passed: report.passed, cases: report.cases.length,
  external_page_requests: report.external_page_requests, widget_commands: 0, paid_calls: 0 }));
