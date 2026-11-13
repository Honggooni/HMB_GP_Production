import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import * as api from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const source = fs.readFileSync(new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url), "utf8");
const channel = "11111111-1111-4111-8111-111111111111";
const shots = [1, 2].map(number => ({ channel_uuid: channel, shot_uuid: `22222222-2222-4222-8222-${String(number).padStart(12, "0")}`,
  number, name: `Sound Shot ${number}`, selected_source_uids: [] }));
const row = (instance, transcript) => ({ instance_id: instance, source_uid: "sound:same-original", audio: "@audio1", name: "Hero dialogue",
  role: "Dialogue", purpose: "both", transcript, target: "Hero", start_seconds: 0, in_seconds: 0, out_seconds: null,
  gain_db: 0, enabled: true, loop: false, lipsync: false, duration_seconds: 8, path: "C:/private/hidden.wav", media_signature: "private-hash" });
const state = api.normalizeState({ multi_shot_enabled: true, shot: shots[0],
  text: { EMOTION_INTENT: "Keep performance 0 OFF", VIDEO_VFX: "Keep VFX {literal}" },
  sound_sources: [row("track-1", "Original 1"), row("track-2", "Original duplicate")],
  speaker_sources: [
    {kind: "image", source_id: "sheet-hero", label: "Hero sheet"},
    {kind: "image", source_id: "sheet-friend", label: "Friend sheet"},
    {kind: "video", source_id: "shot-mask", label: "Picker mask", is_mask: true, colors: ["Red", "Blue"]},
    {kind: "video", source_id: "shot-playblast", label: "Playblast", is_mask: false, colors: ["Green"]},
  ],
  sound_connection: { enabled: true, project_id: "Show", revision: 1 },
  image_asset: { project_id: "Show", shot_catalog: shots, shot_catalog_routing: {
    publisher_instance_uuid: channel, channel_uuid: channel, generation: 1, metadata_sha256: "a".repeat(64) } },
  ui: { resize_mode: "stacked_outer_1000", group_heights: { imageSources: 560, imageText: 230, videoSources: 250, soundSources: 200, videoText: 180 } },
});
assert.equal("path" in state.sound_sources[0], false);
assert.equal("media_signature" in state.sound_sources[0], false);
assert.equal(state.sound_sources[0].audio_sub_type, "Apply");
assert.equal(api.normalizeState({sound_sources: [{...row("disabled", ""), enabled: false}]}).sound_sources[0].audio_sub_type, "Ignore");
const maskVideo = {video_uid: "shot-mask", present: true, label: "Picker mask", picker_speaker_mask: true};
const editedVideo = {...maskVideo, picker_speaker_mask: false, video_sub_type: "Analysis"};
assert.equal(api.normalizeState({videos: [maskVideo]}).videos[0].picker_speaker_mask, true);
assert.equal(api.hmbMergePromptRevisionAxes({videos: [maskVideo]}, {videos: [editedVideo]}).videos[0].picker_speaker_mask, true);
assert.equal(api.hmbMergePromptRevisionAxes({videos: [editedVideo]}, {videos: [maskVideo]}).videos[0].picker_speaker_mask, undefined);
api.hmbStorePromptShotDocument(state);
api.hmbSwitchPromptShot(state, shots[1].shot_uuid);
state.sound_sources = [row("track-3", "Independent Shot 2")];
state.speaker_sources = [{kind: "image", source_id: "shot-2-sheet", label: "Shot 2 sheet", colors: []}];
state.sound_direction = "Shot 2 exact";
api.hmbStorePromptShotDocument(state);
api.hmbSwitchPromptShot(state, shots[0].shot_uuid);
const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#111827}</style><div id="shell" class="react-flow__node" style="position:relative;width:1700px;height:1250px"><div id="host" style="width:100%;height:100%"></div></div><script type="module">
import mount,* as api from '/widget.js';window.api=api;window.latest=${JSON.stringify(state)};window.writes=[];
window.props=value=>({value:JSON.stringify(value),onChange:next=>{window.latest=JSON.parse(next);window.writes.push(window.latest);window.controller.update(window.props(window.latest));}});
window.host=document.getElementById('host');window.controller=mount(window.host,window.props(window.latest));window.ready=true;
</script>`;
const origin = "http://127.0.0.1:55000";
let browser;
let externalRequests = 0;
try {
  browser = await playwright.chromium.launch({ executablePath: process.env.HMB_PROMPT_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
  const page = await browser.newPage({ viewport: { width: 1800, height: 1500 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin === origin && url.pathname === "/") return route.fulfill({contentType:"text/html; charset=utf-8", body:html});
    if (url.origin === origin && url.pathname === "/widget.js") return route.fulfill({contentType:"text/javascript; charset=utf-8", body:source});
    externalRequests++;
    return route.abort();
  });
  await page.goto(origin);
  await page.waitForFunction(() => window.ready);
  assert.deepEqual(await page.evaluate(() => ({ width: document.getElementById("shell").style.width, height: document.getElementById("shell").style.height })),
    { width: "1700px", height: "1250px" });
  assert.deepEqual(await page.locator("[data-group-id]").evaluateAll(nodes => nodes.map(node => node.dataset.groupId)),
    ["imageSources", "imageText", "videoSources", "soundSources", "videoText"]);
  const field = (instance, key) => page.locator(`[data-sound-instance="${instance}"][data-sound-field="${key}"]`);
  const speaker = (instance, kind) => page.locator(`[data-sound-instance="${instance}"][data-sound-speaker="${kind}"]`);
  const speakerValues = (instance, kind) => speaker(instance, kind).locator("option").evaluateAll(options => options.filter(option => !option.disabled).map(option => option.value));
  const speakerGroups = instance => speaker(instance, "source").locator("optgroup").evaluateAll(groups => groups.map(group => group.label));
  assert.deepEqual(await speakerGroups("track-1"), ["캐릭터 시트", "일반 영상", "마스크 영상"]);
  assert.deepEqual(await speakerValues("track-1", "source"), ["", "image:sheet-hero", "image:sheet-friend", "video:shot-playblast", "video:shot-mask"]);
  await speaker("track-1", "source").selectOption("image:sheet-hero");
  await page.waitForFunction(() => window.latest.sound_overlays?.["track-1"]?.speaker_binding?.source_id === "sheet-hero");
  assert.equal(await speaker("track-1", "color").count(), 0);
  await speaker("track-1", "source").selectOption("video:shot-mask");
  assert.deepEqual(await speakerValues("track-1", "color"), ["", "Red", "Blue"]);
  assert.equal(await speaker("track-1", "color").inputValue(), "");
  await speaker("track-1", "color").selectOption("Red");
  await page.waitForFunction(() => window.latest.sound_overlays?.["track-1"]?.speaker_binding?.color === "Red");
  await speaker("track-2", "source").selectOption("video:shot-playblast");
  await page.waitForFunction(() => window.latest.sound_overlays?.["track-2"]?.speaker_binding?.source_id === "shot-playblast");
  assert.equal(await speaker("track-2", "color").count(), 0);
  await speaker("track-2", "source").selectOption("");
  await page.waitForFunction(() => window.latest.sound_overlays?.["track-2"]?.speaker_binding === null);
  const literal = "  안녕 {0}\nOFF 정확한 대사  ";
  await field("track-1", "transcript").fill(literal);
  await field("track-1", "lipsync").check();
  await field("track-1", "start_seconds").fill("0");
  await field("track-1", "gain_db").fill("0");
  await page.locator('[data-sound-field="sound_direction"]').fill("  대상 Hero\n0 OFF  ");
  await page.locator('[data-group-id="soundSources"] h3').click();
  await page.waitForFunction(() => window.latest.sound_overlays?.["track-1"]?.transcript?.includes("정확한 대사"));
  const edited = await page.evaluate(() => window.latest);
  assert.equal(edited.sound_overlays["track-1"].transcript, literal);
  assert.equal(edited.sound_overlays["track-1"].lipsync, true);
  assert.equal(edited.sound_overlays["track-1"].start_seconds, 0);
  assert.equal(edited.sound_overlays["track-1"].gain_db, 0);
  assert.deepEqual(edited.sound_overlays["track-1"].speaker_binding, {kind: "video", source_id: "shot-mask", color: "Red"});
  assert.equal(await field("track-1", "target").inputValue(), "Hero");
  assert.equal(edited.sound_direction, "  대상 Hero\n0 OFF  ");
  assert.equal(edited.text.EMOTION_INTENT, "Keep performance 0 OFF");
  assert.equal(edited.text.VIDEO_VFX, "Keep VFX {literal}");
  assert.equal(edited.sound_sources[1].transcript, "Original duplicate");
  await field("track-1", "purpose").selectOption("mix");
  await field("track-1", "audio_sub_type").selectOption("Analysis");
  await page.waitForFunction(() => window.latest.sound_overlays?.["track-1"]?.audio_sub_type === "Analysis");
  assert.equal(await field("track-1", "purpose").isDisabled(), true);
  assert.equal(await field("track-1", "purpose").inputValue(), "mix");
  assert.equal(await field("track-2", "audio_sub_type").inputValue(), "Apply");
  await page.locator(`[data-prompt-shot="${shots[1].shot_uuid}"]`).click();
  await page.waitForFunction(uuid => window.latest.shot.shot_uuid === uuid, shots[1].shot_uuid);
  assert.equal(await field("track-3", "transcript").inputValue(), "Independent Shot 2");
  assert.equal(await field("track-3", "audio_sub_type").inputValue(), "Apply");
  assert.deepEqual(await speakerGroups("track-3"), ["캐릭터 시트", "일반 영상", "마스크 영상"]);
  assert.deepEqual(await speakerValues("track-3", "source"), ["", "image:shot-2-sheet"]);
  await page.locator(`[data-prompt-shot="${shots[0].shot_uuid}"]`).click();
  await page.waitForFunction(uuid => window.latest.shot.shot_uuid === uuid, shots[0].shot_uuid);
  assert.equal(await field("track-1", "transcript").inputValue(), literal);
  assert.equal(await field("track-1", "lipsync").isChecked(), true);
  assert.equal(await field("track-1", "audio_sub_type").inputValue(), "Analysis");
  assert.equal(await field("track-1", "purpose").inputValue(), "mix");
  assert.equal(await speaker("track-1", "source").inputValue(), "video:shot-mask");
  assert.equal(await speaker("track-1", "color").inputValue(), "Red");
  assert.deepEqual(await page.locator('[data-group-id="soundSources"]').evaluate(node => ({ minHeight: node.style.minHeight, flexBasis: node.style.flexBasis })),
    { minHeight: "150px", flexBasis: "200px" });
  assert.equal(await page.evaluate(() => window.latest.ui.group_heights.soundSources), 200, "Saved custom Sound group height survives editing and shot switches");
  assert.equal((await page.locator("#host").innerHTML()).includes("C:/private/hidden.wav"), false);
  await page.evaluate(() => {
    const next = {...window.latest, source_sync_revision: window.latest.source_sync_revision + 1,
      speaker_sources: window.latest.speaker_sources.filter(source => source.source_id !== "shot-mask")};
    window.latest = next;
    window.controller.update(window.props(next));
  });
  await page.waitForFunction(() => {
    const select = document.querySelector('[data-sound-instance="track-1"][data-sound-speaker="source"]');
    return select?.selectedOptions[0]?.disabled === true;
  });
  assert.equal(await speaker("track-1", "color").count(), 0);
  assert.deepEqual(await page.evaluate(() => window.latest.sound_overlays["track-1"].speaker_binding),
    {kind: "video", source_id: "shot-mask", color: "Red"});
  assert.deepEqual(errors, []);
  assert.equal(externalRequests, 0);
  const screenshot = process.env.HMB_PROMPT_SOUND_TEST_SCREENSHOT;
  if (screenshot) {
    fs.mkdirSync(path.dirname(screenshot), { recursive: true });
    await page.locator('[data-scroll-id="soundSources"]').evaluate(node => { node.scrollTop = 0; });
    await page.locator('[data-group-id="soundSources"]').screenshot({ path: screenshot });
  }
  console.log(JSON.stringify({ status: "PASS", scope: "isolated Chrome widget, all three speaker reference types, mask-only color, stale source and exact Shot isolation; audio subtype, purpose, exact text/zero/off", external_requests: externalRequests, screenshot }));
} finally {
  await browser?.close();
}
