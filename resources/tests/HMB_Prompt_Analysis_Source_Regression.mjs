import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {createRequire} from "node:module";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const widget = fs.readFileSync(new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url));
const channel = "11111111-1111-4111-8111-111111111111";
const shots = [1, 2].map(number => ({channel_uuid: channel,
  shot_uuid: `22222222-2222-4222-8222-${String(number).padStart(12, "0")}`, number, name: `Shot ${number}`,
  selected_source_uids: number === 1 ? ["image-1", "image-2"] : []}));
const state = {
  multi_shot_enabled: true, shot: shots[0], text: {
    VIDEO_VFX: "Use the observed effect cue", SCENE_CONTEXT: "Private scene note stays in Prompt",
  },
  images: [{asset_source_uid: "image-1", asset_managed: true, label: "Image one", present: true},
    {asset_source_uid: "image-2", asset_managed: true, label: "Image two", image_sub_type: "Analysis", present: true}],
  videos: [{video_uid: "video-1", picker_managed: true, label: "Video one", video_sub_type: "Analysis", present: true},
    {video_uid: "video-2", picker_managed: true, label: "Video two", present: true}],
  picker: {ordered_video_uids: ["video-1", "video-2"]},
  sound_sources: [
    {instance_id: "audio-1", source_uid: "audio-original", name: "Audio one", enabled: true, purpose: "mix"},
    {instance_id: "audio-2", source_uid: "audio-ignored", name: "Audio two", enabled: false},
    {instance_id: "audio-3", source_uid: "audio-analysis", name: "Audio three", enabled: false, audio_sub_type: "Analysis"},
  ],
  image_asset: {shot_catalog: shots, shot_catalog_routing: {
    publisher_instance_uuid: channel, channel_uuid: channel, generation: 1, metadata_sha256: "a".repeat(64),
  }},
};
const html = `<!doctype html><meta charset="utf-8"><div class="react-flow__node" style="width:1750px;height:1600px"><div id="host" style="width:1700px;height:1500px"></div></div><script type="module">
import mount from '/widget.js';
window.fixture = ${JSON.stringify(state)};
window.requests = [];
window.props = (value, disabled=false) => ({value: JSON.stringify(value), disabled, onChange: async raw => {
  const request = JSON.parse(raw);
  window.requests.push(request);
}});
window.controller = mount(document.getElementById('host'), window.props(window.fixture));
window.ready = true;
</script>`;
const browser = await playwright.chromium.launch({
  executablePath: process.env.HMB_PROMPT_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true,
});
try {
  const page = await browser.newPage({viewport: {width: 1820, height: 1720}});
  const errors = [];
  const origin = "http://127.0.0.1:55000";
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin === origin && url.pathname === "/") return route.fulfill({contentType: "text/html; charset=utf-8", body: html});
    if (url.origin === origin && url.pathname === "/widget.js") return route.fulfill({contentType: "text/javascript; charset=utf-8", body: widget});
    return route.abort();
  });
  await page.goto(origin);
  await page.waitForFunction(() => window.ready);
  const retiredControls = page.locator("[data-prompt-analysis], [data-prompt-analysis-dialog], [data-analysis-send]");
  assert.equal(await retiredControls.count(), 0);
  const imageMode = page.locator('select[data-field="image_sub_type"]');
  const videoMode = page.locator('select[data-field="video_sub_type"]');
  const audioMode = instance => page.locator(`[data-sound-instance="${instance}"][data-sound-field="audio_sub_type"]`);
  assert.equal(await imageMode.nth(1).inputValue(), "Analysis");
  assert.equal(await videoMode.nth(0).inputValue(), "Analysis");
  assert.deepEqual(await audioMode("audio-1").locator("option").allTextContents(), ["적용", "미적용", "분석"]);
  assert.equal(await audioMode("audio-3").inputValue(), "Analysis");

  await imageMode.nth(0).selectOption("Analysis");
  await videoMode.nth(1).selectOption("Analysis");
  await audioMode("audio-1").selectOption("Analysis");
  const purpose = page.locator('[data-sound-instance="audio-1"][data-sound-field="purpose"]');
  assert.equal(await purpose.isDisabled(), true);
  assert.equal(await purpose.inputValue(), "mix");
  await page.waitForFunction(() => window.requests.some(request =>
    request.images?.[0]?.image_sub_type === "Analysis" &&
    request.videos?.[1]?.video_sub_type === "Analysis" &&
    request.sound_overlays?.["audio-1"]?.audio_sub_type === "Analysis"));
  assert.equal(await retiredControls.count(), 0);
  assert.equal(await page.evaluate(() => window.requests.some(request => request.schema === "hmb-prompt-analysis-pick")), false);
  await audioMode("audio-1").selectOption("Apply");
  assert.equal(await purpose.isEnabled(), true);
  assert.equal(await purpose.inputValue(), "mix");
  await page.evaluate(() => window.controller.update(window.props(window.fixture, true)));
  assert.equal(await retiredControls.count(), 0);
  assert.deepEqual(errors, []);
  console.log("Prompt analysis subtype: PASS (image, video and audio edit normally, with no Prompt analysis controls or dispatch)");
} finally { await browser.close(); }
