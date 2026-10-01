import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const source = fs.readFileSync(
  new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url),
  "utf8",
);
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  playwright = require(path.join(
    os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
  ));
}
const executablePath = process.env.HMB_PROMPT_TEST_BROWSER
  || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
assert.ok(fs.existsSync(executablePath), `Browser unavailable: ${executablePath}`);

const channel = "11111111-1111-4111-8111-111111111111";
const shot = "22222222-2222-4222-8222-222222222222";
const fixture = () => ({
  ui: { language: "ko" },
  images: [{
    slot: 1, present: true, manual: true, label: "Hero", asset_source_uid: "hero-source",
    image_main_type: "Look Reference", image_sub_type: "Color Mood",
  }],
  videos: [{
    slot: 1, present: true, manual: true, label: "Preview", video_uid: "preview-source",
    video_main_type: "Maya Preview / Playblast", video_sub_type: "Original Preview",
  }],
  image_asset: {
    shot_catalog_routing: {
      publisher_instance_uuid: channel, channel_uuid: channel,
      generation: 1, metadata_sha256: "a".repeat(64),
    },
    shot_catalog: [{ shot_uuid: shot, channel_uuid: channel, number: 1, name: "Shot 1" }],
  },
  shot: { shot_uuid: shot, channel_uuid: channel, number: 1, name: "Shot 1" },
});
const html = `<!doctype html><meta charset="utf-8"><div id="host" style="width:1700px;height:1300px"></div><script type="module">
import mount from "/widget.js";
window.start = (raw) => {
  window.controller?.cleanup();
  const host = document.createElement("div");
  host.id = "host";
  host.style.cssText = "width:1700px;height:1300px";
  document.getElementById("host").replaceWith(host);
  window.host = host;
  window.latest = structuredClone(raw);
  window.publications = [];
  window.props = (value) => ({ value: JSON.stringify(value), disabled: false,
    onChange(next) {
      window.latest = JSON.parse(next);
      window.publications.push(window.latest);
      window.controller.update(window.props(window.latest));
    },
  });
  window.controller = mount(host, window.props(raw));
};
window.updateSibling = (kind) => {
  const next = structuredClone(window.latest);
  if (kind === "shot") {
    next.ui.language = next.ui.language === "ko" ? "en" : "ko";
    next.ui_edit_revision = (next.ui_edit_revision || 0) + 1;
  } else {
    next[kind === "image" ? "images" : "videos"][0].label += " updated";
    next.source_sync_revision = (next.source_sync_revision || 0) + 1;
  }
  window.latest = next;
  window.controller.update(window.props(next));
};
window.ready = true;
</script>`;
const server = http.createServer((request, response) => {
  response.setHeader("Content-Type", request.url === "/widget.js"
    ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  response.end(request.url === "/widget.js" ? source : html);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

const browser = await playwright.chromium.launch({ executablePath, headless: true });
const failures = [];
try {
  const page = await browser.newPage({ viewport: { width: 1800, height: 1400 } });
  page.setDefaultTimeout(8000);
  page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(() => window.ready === true);

  const cases = [
    ["image main type", ".source-row.image[data-index='0'] [data-field='image_main_type']", "image", "Character"],
    ["image subtype", ".source-row.image[data-index='0'] [data-field='image_sub_type']", "image", "Render Style"],
    ["video main type", ".source-row.video[data-index='0'] [data-field='video_main_type']", "video", "Motion Reference"],
    ["video subtype", ".source-row.video[data-index='0'] [data-field='video_sub_type']", "video", "Mask"],
    ["Shot selector", "[data-shot-selector]", "shot", "__hmb_only__"],
  ];
  for (const [name, selector, sibling, targetValue] of cases) {
    await page.evaluate((value) => window.start(value), fixture());
    await page.locator(selector).waitFor();
    await page.evaluate((key) => {
      window.openSelect = document.querySelector(key);
      window.openOption = window.openSelect.options[0];
      window.openSelect.focus();
    }, selector);
    assert.equal(await page.evaluate(() => document.activeElement === window.openSelect), true);
    await page.evaluate((kind) => window.updateSibling(kind), sibling);
    await page.waitForFunction((kind) => kind === "shot"
      ? document.querySelector(".language-button")?.textContent === "EN"
      : document.querySelector(`.source-row.${kind}[data-index='0'] [data-field='label']`)?.value.endsWith(" updated"), sibling);
    assert.equal(await page.evaluate((key) => (
      window.openSelect.isConnected
      && document.activeElement === window.openSelect
      && document.querySelector(key) === window.openSelect
      && window.openSelect.options[0] === window.openOption
    ), selector), true, `${name}: incoming sibling state replaced the open dropdown`);
    await page.evaluate(() => { window.beforeSelection = structuredClone(window.latest); });
    await page.locator(selector).selectOption(targetValue);
    assert.equal(await page.locator(selector).inputValue(), targetValue, `${name}: selection did not paint immediately`);
    await page.waitForFunction(() => window.publications.length > 0);
    assert.equal(await page.evaluate((key) => document.querySelector(key) === window.openSelect, selector), true,
      `${name}: selected control identity changed on its own echo`);
    await page.evaluate(() => window.controller.update(window.props(window.beforeSelection)));
    assert.equal(await page.locator(selector).inputValue(), targetValue,
      `${name}: delayed pre-selection props restored an old value`);
    console.log(`PASS ${name}: focused select survives external repaint and publishes selection`);
  }
  assert.deepEqual(failures, []);
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
