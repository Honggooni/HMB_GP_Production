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
    if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Playwright required for cold-mount verification.");
    console.log("Picker cold-mount browser regression: SKIP (optional Playwright unavailable)"); process.exit(0);
  }
}
const executablePath = process.env.HMB_PICKER_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(executablePath)) {
  if (process.env.HMB_PICKER_REQUIRE_BROWSER === "1") throw new Error("Browser required for cold-mount verification.");
  console.log("Picker cold-mount browser regression: SKIP (optional browser unavailable)"); process.exit(0);
}
const root = process.env.HMB_PICKER_WIDGET_ROOT || fileURLToPath(new URL("../../", import.meta.url));
const source = fs.readFileSync(path.join(root, "widgets/HMBVideoPickerLibraryWidget_v032.js"));
const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#111}#widget{width:1600px;min-height:1200px}</style><div id="widget"></div><script type="module">
import mount, * as widget from '/widget.js';
window.widget=widget;window.mountPicker=(value)=>{
  window.controller?.cleanup();
  const old=document.getElementById('widget'), el=document.createElement('div');el.id='widget';old.replaceWith(el);
  window.publications=[];window.current=value;
  window.props=(next)=>({value:next,onChange:(state)=>window.publications.push(state)});
  window.controller=mount(el,window.props(value));
};window.ready=true;
</script>`;
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", req.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  res.end(req.url === "/widget.js" ? source : html);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1700, height: 1300 } });
  page.setDefaultTimeout(6000);
  const origin = `http://127.0.0.1:${server.address().port}`;
  await page.route("**/*", (route) => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto(origin);
  await page.waitForFunction(() => window.ready);
  const first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const shots = [first, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"];
  const bound = {
    language: "ko", runtime_instance_id: "cold-mount-runtime", state_revision: 1,
    shot_publisher_instance_uuid: "11111111-1111-4111-8111-111111111111",
    channel_uuid: "22222222-2222-4222-8222-222222222222", active_picker_shot_uuid: first,
    shot_selections: shots.map((shot_uuid, index) => ({ shot_uuid, number: index + 1, name: `Shot ${index + 1}`, revision: 1 })),
    picker_shots: shots.map((workspace_uuid, index) => ({ workspace_uuid, bound_shot_uuid: workspace_uuid,
      number: index + 1, name: `Shot ${index + 1}`, video_asset_uids: [], selected_video_uids: [] })), videos: [],
  };
  for (const state of [{}, bound, { ...bound, language: "en" }]) {
    const error = await page.evaluate((value) => { try { window.mountPicker(value); return ""; } catch (e) { return `${e.name}: ${e.message}`; } }, state);
    assert.equal(error, "", "The complete production widget factory must mount without an initialization error.");
    await page.waitForFunction(() => document.querySelector('.hmbvp[data-picker-view="compact"]'));
    assert.ok(await page.locator("[data-picker-shot-row]").count() >= 1);
    for (const view of ["expanded", "compact"]) {
      await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent("dblclick");
      await page.waitForFunction((desired) => document.querySelector(".hmbvp")?.getAttribute("data-picker-view") === desired, view);
    }
  }
  const loading = { ...bound, video_imports: [{ import_id: "loading-1", label: "Pending clip.mp4", status: "loading", error: "",
    runtime_instance_id: bound.runtime_instance_id, picker_shot_uuid: first }] };
  // Import progress is authoritative even during a still-pending optimistic
  // Shot/order draft. Test real controller.update, not just cold HTML output.
  for (const expanded of [false, true]) {
    await page.evaluate((value) => window.mountPicker(value), bound);
    const desired = expanded ? "expanded" : "compact";
    if (await page.locator(".hmbvp").getAttribute("data-picker-view") !== desired) {
      await page.locator('[data-picker-toggle-surface="header"]').dispatchEvent("dblclick");
    }
    await page.waitForFunction((view) => document.querySelector(".hmbvp")?.getAttribute("data-picker-view") === view, desired);
    const pendingCount = await page.evaluate((value) => {
      const host = document.getElementById("widget");
      host.__hmbPickerPaintFirstState = window.current;
      window.controller.update(window.props(value));
      const count = host.querySelectorAll("[data-picker-import-id]").length;
      delete host.__hmbPickerPaintFirstState;
      return count;
    }, loading);
    assert.equal(pendingCount, 1, `Loading progress must bypass stale authoring drafts (${expanded ? "expanded" : "compact"}).`);
    if (expanded) {
      const otherShotCount = await page.evaluate(({ value, otherShot }) => {
        const host = document.getElementById("widget");
        host.__hmbPickerPaintFirstState = window.widget.hmbSwitchLocalPickerShot(window.current, otherShot);
        window.controller.update(window.props(value));
        const count = host.querySelector(".video-asset-grid").querySelectorAll("[data-picker-import-id]").length;
        delete host.__hmbPickerPaintFirstState;
        return count;
      }, { value: loading, otherShot: shots[1] });
      assert.equal(otherShotCount, 0, "Background progress must not move the source Shot's cards into an optimistically selected different Shot.");
    }
  }
  await page.evaluate((value) => window.mountPicker(value), loading);
  assert.equal(await page.locator("[data-picker-import-id]").count(), 1);
  await page.locator("[data-picker-import-cancel]").click();
  assert.equal(await page.locator("[data-picker-import-id]").count(), 0);
  const commands = await page.evaluate(() => window.publications.flatMap((state) => Object.values(state).filter((value) => value && typeof value === "object" && value.action === "cancel_video_import")));
  assert.equal(commands.length, 1, "One click must dispatch exactly one cancel command.");
  assert.equal(commands[0].payload.import_id, "loading-1");
  await page.evaluate(() => window.controller.update(window.props(window.current)));
  assert.equal(await page.locator("[data-picker-import-id]").count(), 0, "A stale loading echo cannot repaint the cancelled card.");
  await page.evaluate(() => window.controller.cleanup());
  assert.deepEqual(failures, []);
  console.log("Picker cold-mount browser regression: PASS (actual widget factory, empty/5 Shots, ko/en, compact/expanded, remount, cancel, stale echo, cleanup).");
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
