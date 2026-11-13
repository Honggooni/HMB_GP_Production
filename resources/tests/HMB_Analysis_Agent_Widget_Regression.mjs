import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import {createRequire} from "node:module";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"));
}
const executablePath = process.env.HMB_COLOR_LUT_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const source = fs.readFileSync(new URL("../../widgets/HMBAnalysisAgentWidget.js", import.meta.url));
const state = {
  revision: 3, channel_uuid: "channel", shot_uuid: "shot-1",
  result_text: "Generated observation",
  shots: Array.from({length: 5}, (_, i) => ({number: i + 1, shot_uuid: `shot-${i + 1}`, name: `Shot ${i + 1}`})),
  slot: {kind: "video", origin: "prompt", source_id: "video:example", frame_ranges: [{start: 0, end: 95}], guidance: "",
    result: {cache_hit: true, observations: {effect_shape: [{observation: "<script>observe</script>"}],
      effect_timing: [{observation: "visible glow", start: 0, end: 2}]}}, categories: []},
  source: {kind: "video", source_id: "video:example", name: "example.mov", frame_count: 240, frame_rate: 24,
    preview_url: "https://external.invalid/video.mov"},
  sources: [{kind: "video", source_id: "video:example", name: "example.mov"},
    {kind: "image", source_id: "image:example", name: "example.png"},
    {kind: "audio", source_id: "audio:example", name: "example.wav"}],
  categories: ["camera", "motion", "cut_timing", "effect_shape", "effect_timing"],
};
const html = `<!doctype html><meta charset="utf-8"><main id="widget" style="width:640px;height:620px"></main><script type="module">
import mount from '/widget.js';
window.state = ${JSON.stringify(state).replaceAll("<", "\\u003c")};
window.commands = []; window.locked = false;
window.props = () => ({value:window.state, disabled:window.locked, onChange:v=>window.commands.push(v.__hmb_analysis_command)});
window.controller = mount(document.getElementById('widget'), window.props()); window.ready = true;
</script>`;
const server = http.createServer((request, response) => {
  if (request.url === "/fixture.png") {
    response.setHeader("Content-Type", "image/png");
    response.end(Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ZkAAAAASUVORK5CYII=", "base64"));
    return;
  }
  response.setHeader("Content-Type", request.url === "/widget.js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  response.end(request.url === "/widget.js" ? source : html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));

async function assertCategoryRow(page, labels) {
  const row = page.locator(".ha-categories");
  assert.equal(labels.length, 5);
  assert.deepEqual(await row.locator("label").allTextContents(), labels);
  for (const width of [800, 640, 430, 300]) {
    await page.locator("#widget").evaluate((element, width) => { element.style.width = `${width}px`; }, width);
    const layout = await row.evaluate(element => {
      const boxes = [...element.querySelectorAll("label")].map(label => label.getBoundingClientRect());
      const style = getComputedStyle(element);
      const content = element.closest(".ha-content");
      return {aligned: boxes.every(box => Math.abs(box.top - boxes[0].top) <= 1),
        equalSize: boxes.every(box => Math.abs(box.width - boxes[0].width) <= 1 && Math.abs(box.height - boxes[0].height) <= 1),
        noWrap: [...element.querySelectorAll("label")].every(label => getComputedStyle(label).whiteSpace === "nowrap"),
        scrollable: style.overflowX === "auto", overflows: element.scrollWidth > element.clientWidth,
        parentOverflow: content.scrollWidth > content.clientWidth};
    });
    assert.equal(layout.aligned && layout.equalSize && layout.noWrap && layout.scrollable, true,
      `Category switches use equal boxes in one row at ${width}px`);
    assert.equal(layout.parentOverflow, false, `Overflow stays in the checkbox row at ${width}px`);
    if (layout.overflows) {
      assert.equal(await row.evaluate(element => {
        element.scrollLeft = element.scrollWidth;
        const last = element.querySelector("label:last-of-type").getBoundingClientRect();
        return element.scrollLeft > 0 && last.right <= element.getBoundingClientRect().right + 1;
      }), true, "The entire last choice is reachable by horizontal scrolling");
    }
  }
  await page.locator("#widget").evaluate(element => { element.style.width = "640px"; });
}

async function assertSourceRow(page) {
  for (const width of [800, 640, 430, 300]) {
    await page.locator("#widget").evaluate((element, width) => { element.style.width = `${width}px`; }, width);
    const row = await page.locator(".ha-source-row").evaluate(element => {
      const [kind, source, clear] = [...element.children].map(child => child.getBoundingClientRect());
      const outer = element.getBoundingClientRect();
      return {outerWidth: outer.width, kindWidth: kind.width, sourceWidth: source.width,
        aligned: Math.abs(kind.top - source.top) <= 1 && Math.abs(source.top - clear.top) <= 1,
        clearAtRight: Math.abs(clear.right - outer.right) <= 1,
        noOverflow: element.closest(".ha-content").scrollWidth === element.closest(".ha-content").clientWidth};
    });
    assert.equal(row.aligned && row.clearAtRight && row.noOverflow, true, `Source controls fit one row at ${width}px`);
    if (width >= 640) {
      assert.ok(row.kindWidth / row.outerWidth >= .20 && row.kindWidth / row.outerWidth <= .24);
      assert.ok(row.sourceWidth > row.outerWidth * .55, "File selector uses most of the row");
    }
  }
  await page.locator("#widget").evaluate(element => { element.style.width = "800px"; });
}

async function assertWorkspaceLayout(page) {
  const widget = page.locator("#widget");
  for (const [width, height] of [[736, 1055], [800, 1050], [606, 625], [430, 625]]) {
    await widget.evaluate((element, [w, h]) => {
      element.style.width = `${w}px`;
      element.style.height = `${h}px`;
    }, [width, height]);
    const layout = await widget.evaluate(element => {
      const bounds = selector => {
        const {top, left, right, bottom, width, height} = element.querySelector(selector).getBoundingClientRect();
        return {top, left, right, bottom, width, height};
      };
      const guidance = element.querySelector("[data-guidance]");
      return {tabs: bounds(".ha-tabs"), sources: bounds(".ha-source-row"), workspace: bounds(".ha-workspace"),
        preview: bounds(".ha-preview"), guidance: bounds("[data-guidance]"), guidanceBox: bounds(".ha-guidance"),
        range: bounds(".ha-intervals"),
        review: bounds(".ha-review"), actions: bounds(".ha-bottom"), content: bounds(".ha-content"),
        guidanceInWorkspace: guidance.closest(".ha-workspace") !== null};
    });
    assert.ok(layout.tabs.bottom <= layout.sources.top && layout.sources.bottom < layout.workspace.top,
      "The media selector is directly above the media and guidance area");
    assert.ok(layout.guidanceInWorkspace, "Guidance lives in the media area");
    assert.ok(Math.abs(layout.preview.width / layout.preview.height - 16 / 9) < .01,
      "Preview keeps its 16:9 frame");
    assert.ok(width >= 606 ? layout.preview.right < layout.guidance.left : layout.preview.bottom <= layout.guidance.top,
      "Guidance sits beside the preview on a wide node and below it on a narrow node");
    if (width >= 606) {
      for (const edge of ["top", "bottom", "width", "height"]) {
        assert.ok(Math.abs(layout.preview[edge] - layout.guidanceBox[edge]) <= 1,
          `The preview and guidance have matching ${edge} at ${width}px`);
        assert.ok(Math.abs(layout.preview[edge] - layout.guidance[edge]) <= 1,
          `The guidance editor fills its aligned box at ${width}px`);
      }
    }
    assert.ok(layout.workspace.bottom <= layout.range.top && layout.range.bottom <= layout.review.top,
      "The interval selector comes after the media and before the analysis output");
    if (width === 736) {
      assert.ok(layout.actions.bottom <= layout.content.bottom + 1,
        "The analysis action is visible at the new default size");
    }
  }
  await widget.evaluate(element => { element.style.width = "800px"; element.style.height = "1050px"; });
  assert.equal(await page.getByText(/직접 분석하려면|빈 구간을 드래그해/).count(), 0,
    "Source and interval instructions no longer consume a separate line");
  const guidance = page.locator("[data-guidance]");
  assert.equal(await page.getByRole("textbox", {name: "참고 지시 (선택)", exact: true}).count(), 1);
  assert.match(await guidance.getAttribute("placeholder"), /^참고 지시 \(선택\)/);
  assert.equal(await page.locator(".ha-guidance").textContent().then(text => text.trim()), "",
    "The guidance label moves inside the input");
  assert.equal(await guidance.evaluate(element => getComputedStyle(element).resize), "none");
  const before = await guidance.evaluate(element => element.clientHeight);
  await guidance.fill("참고 지시\n".repeat(50));
  assert.deepEqual(await guidance.evaluate(element => ({
    height: element.clientHeight,
    scrollable: element.scrollHeight > element.clientHeight && /^(auto|scroll)$/.test(getComputedStyle(element).overflowY),
  })), {height: before, scrollable: true}, "Long guidance scrolls inside the unchanged editor");
  await widget.evaluate(element => { element.style.height = "1180px"; });
  assert.equal(await guidance.evaluate(element => element.clientHeight), before,
    "Height-only resizing retains the aligned 16:9 bounds");
  await widget.evaluate(element => { element.style.width = "900px"; element.style.height = "1180px"; });
  assert.ok(await guidance.evaluate(element => element.clientHeight) > before,
    "Resizing the whole node enlarges the guidance editor");
  await guidance.fill("");
  await widget.evaluate(element => { element.style.width = "800px"; element.style.height = "1050px"; });
}

async function assertRangeEditorToggle(page) {
  const range = page.locator(".ha-intervals");
  const toggle = range.locator("[data-action=toggle-range]");
  const trackArea = range.locator("[data-ha-key=range-track-area]");
  const track = trackArea.locator("[data-interval-track]");
  const analyze = page.locator("[data-action=analyze]");
  assert.equal(await toggle.getAttribute("aria-expanded"), "false", "Video ranges default to OFF");
  assert.equal(await track.isVisible(), false);
  assert.equal(await analyze.isEnabled(), true);
  assert.equal(await range.locator("[data-interval-message]").textContent(), "전체 영상 분석");
  await analyze.click();
  const fullRun = await page.evaluate(() => window.commands.at(-1));
  assert.equal(fullRun.full_video, true, "OFF uses the whole video even with a saved range");
  assert.deepEqual(fullRun.frame_ranges, [{start: 0, end: 95}], "OFF preserves the saved range");
  await page.evaluate(() => {
    window.state = {...window.state, ack: window.commands.at(-1).id};
    window.controller.update(window.props());
  });
  await page.evaluate(() => {
    window.readySource = window.state.source;
    const {frame_count, ...coldSource} = window.readySource;
    window.state = {...window.state, source: coldSource};
    window.controller.update(window.props());
  });
  assert.equal(await analyze.isEnabled(), true, "Full video does not wait for frame-picker metadata");
  await analyze.click();
  const coldRun = await page.evaluate(() => window.commands.at(-1));
  assert.equal(coldRun.full_video, true);
  assert.equal("frame_ranges" in coldRun, false, "Unavailable metadata does not clear stored ranges");
  await page.evaluate(() => {
    window.state = {...window.state, ack: window.commands.at(-1).id, source: window.readySource};
    window.controller.update(window.props());
  });
  await toggle.click();
  const ranges = await track.locator("[data-interval-index]").evaluateAll(bars => bars.map(bar => bar.title));
  assert.ok(ranges.length > 0);
  const commandCount = await page.evaluate(() => window.commands.length);
  const analyzeDisabled = await analyze.isDisabled();
  await watchStableShell(page);
  await toggle.click();
  assert.equal(await toggle.getAttribute("aria-expanded"), "false");
  assert.equal(await trackArea.getAttribute("hidden"), "");
  assert.equal(await track.isVisible(), false);
  assert.equal(await analyze.isDisabled(), analyzeDisabled, "Full-video mode still allows analysis");
  await toggle.click();
  assert.equal(await toggle.getAttribute("aria-expanded"), "true");
  assert.equal(await track.isVisible(), true);
  assert.deepEqual(await track.locator("[data-interval-index]").evaluateAll(bars => bars.map(bar => bar.title)), ranges);
  assert.equal(await page.evaluate(() => window.commands.length), commandCount,
    "Switching modes does not send a command before execution");
  await assertStableShell(page, "Range editor toggle");
  await range.locator("[data-action=remove-interval]").click();
  assert.equal(await analyze.isEnabled(), true, "Removing the final range still allows analysis");
  assert.equal(await range.locator("[data-interval-message]").textContent(), "전체 영상 분석");
  await analyze.click();
  const emptyRun = await page.evaluate(() => window.commands.at(-1));
  assert.equal(emptyRun.full_video, true);
  assert.deepEqual(emptyRun.frame_ranges, []);
  await page.evaluate(() => {
    window.state = {...window.state, ack: window.commands.at(-1).id};
    window.controller.update(window.props());
  });
}

async function watchStableShell(page) {
  await page.evaluate(() => {
    const root = document.querySelector("#widget");
    const selectors = [".hmb-analysis", ".ha-header", ".ha-tabs", ".ha-content",
      ".ha-preview", "[data-guidance]", "[data-hmb-native-identity]", "[data-hmb-native-actions]"];
    const nodes = new Map(selectors.map(selector => [selector, root.querySelector(selector)]));
    const detached = new Set();
    const observe = records => {
      for (const record of records) {
        for (const removed of record.removedNodes) {
          for (const [selector, node] of nodes) {
            if (node && (removed === node || removed.contains(node))) detached.add(selector);
          }
        }
      }
    };
    const observer = new MutationObserver(observe);
    observer.observe(root, {subtree: true, childList: true});
    window.stableShell = {root, nodes, detached, observe, observer};
  });
}

async function assertStableShell(page, operation) {
  const changed = await page.evaluate(() => {
    const {root, nodes, detached, observe, observer} = window.stableShell;
    observe(observer.takeRecords());
    observer.disconnect();
    return [...nodes].filter(([selector, node]) =>
      node && (detached.has(selector) || root.querySelector(selector) !== node)).map(([selector]) => selector);
  });
  assert.deepEqual(changed, [], `${operation} keeps the existing widget shell attached`);
}

let browser;
try {
  browser = await playwright.chromium.launch({executablePath, headless: true});
  const page = await browser.newPage({viewport: {width: 720, height: 720}});
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => new URL(route.request().url()).hostname === "127.0.0.1" ? route.continue() : route.abort());
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(() => window.ready);
  const modelPicker = page.locator("[data-model]");
  assert.deepEqual(await modelPicker.locator("option").allTextContents(), ["None", "Gemini 4 Carbon", "Gemini 4 Argon"]);
  await modelPicker.selectOption("gemini-4-argon");
  await page.evaluate(() => {
    window.state = {...window.state, default_model: "Claude Sonnet 5.5"};
    window.controller.update(window.props());
  });
  assert.deepEqual(await modelPicker.locator("option").allTextContents(), ["Claude Sonnet 5.5", "Gemini 4 Carbon", "Gemini 4 Argon"]);
  assert.equal(await modelPicker.inputValue(), "gemini-4-argon");
  await modelPicker.selectOption("");
  assert.equal(await page.getByRole("tab").count(), 5);
  assert.equal(await page.getByRole("tab", {name: /01 Shot 1/}).getAttribute("aria-selected"), "true");
  await page.setViewportSize({width: 830, height: 1070});
  await page.locator("#widget").evaluate(element => { element.style.width = "800px"; element.style.height = "1050px"; });
  await assertSourceRow(page);
  assert.equal(await page.locator("[data-category=camera]").isDisabled(), true);
  assert.equal(await page.locator("[data-category=camera]").locator("..").getAttribute("title"), "이 항목의 분석 결과가 없습니다.");
  assert.equal(await page.locator(".ha-model-route").evaluate(el => {
    const center = node => {
      const box = node.getBoundingClientRect();
      return box.top + box.height / 2;
    };
    return Math.abs(center(el.querySelector("[data-model]")) - center(el.querySelector("[data-results-only]"))) <= 2;
  }), true, "Delivery targets share the model row at normal width");
  assert.equal(await page.locator(".ha-content").evaluate(el => el.scrollWidth === el.clientWidth), true,
    "Screenshot-sized panel has no horizontal spill");
  await assertWorkspaceLayout(page);
  assert.ok(await page.locator(".ha-result-text").evaluate(el => el.getBoundingClientRect().height) >= 104,
    "Result editor remains usable below the interval selector");
  const rangeTrack = page.locator("[data-interval-track]");
  assert.equal(await rangeTrack.count(), 1);
  assert.equal(await rangeTrack.getAttribute("data-interval-max"), "239");
  assert.equal(await page.locator("[data-start],[data-end]").count(), 0, "Video has no seconds inputs");
  await assertRangeEditorToggle(page);
  await watchStableShell(page);
  await rangeTrack.focus();
  await rangeTrack.press("ArrowRight");
  assert.equal(await page.locator('[data-interval-index="0"]').getAttribute("title"), "1–96프레임");
  await rangeTrack.press("ArrowLeft");
  assert.equal(await page.locator('[data-interval-index="0"]').getAttribute("title"), "0–95프레임");
  await assertStableShell(page, "Interval selection");
  await assertCategoryRow(page,
    ["카메라", "동작", "컷 타이밍", "이펙트 형태", "이펙트 타이밍"]);
  const effectTiming = page.locator("[data-category=effect_timing]");
  const categoryFill = input => input.evaluate(element => getComputedStyle(element.parentElement).backgroundColor);
  const uncheckedFill = await categoryFill(effectTiming);
  assert.equal(await page.locator(".ha-result script").count(), 0);
  assert.equal(await page.locator(".ha-preview video").count(), 0);
  assert.equal(await page.locator("[data-action=apply],[data-action=unapply]").count(), 0);
  const analyze = page.locator("[data-action=analyze]");
  assert.equal(await analyze.textContent(), "To Agent 실행");
  assert.equal(await analyze.evaluate(button => getComputedStyle(button).fontSize), "18px");
  assert.equal(await analyze.evaluate(button => button.getBoundingClientRect().height), 42);
  await effectTiming.check();
  let delivery = await page.evaluate(() => window.commands.at(-1));
  assert.deepEqual({...delivery, id: "fixture"}, {id: "fixture", action: "delivery", channel_uuid: "channel",
    shot_uuid: "shot-1", revision: 3, categories: ["effect_timing"], results_only: false});
  await page.evaluate(() => {
    window.state = {...window.state, revision: 4, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, categories: ["effect_timing"]}};
    window.controller.update(window.props());
  });
  assert.notEqual(await categoryFill(effectTiming), uncheckedFill, "An enabled category has a distinct fill");
  assert.equal(await page.locator("[data-results-only]").isChecked(), false);
  await page.evaluate(() => { window.routeContentNode = document.querySelector(".ha-content"); });
  await page.locator("[data-results-only]").check();
  assert.equal((await page.evaluate(() => window.commands.at(-1))).results_only, true);
  await page.evaluate(() => window.controller.update({value: {__hmb_analysis_command: window.commands.at(-1)}, onChange: window.props().onChange}));
  assert.equal(await page.locator(".ha-content").count(), 1, "Raw command echo does not replace the widget");
  await page.evaluate(() => {
    window.state = {...window.state, revision: 5, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, results_only: true}};
    window.controller.update(window.props());
  });
  assert.equal(await page.evaluate(() => document.querySelector(".ha-content") === window.routeContentNode), true,
    "Results-only acknowledgement patches the current panel in place");
  await page.locator("[data-results-only]").uncheck();
  await page.evaluate(() => {
    window.state = {...window.state, revision: 6, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, results_only: false}};
    window.controller.update(window.props());
  });
  await page.locator("[data-results-only]").check();
  delivery = await page.evaluate(() => window.commands.at(-1));
  assert.deepEqual({...delivery, id: "fixture"}, {id: "fixture", action: "delivery", channel_uuid: "channel",
    shot_uuid: "shot-1", revision: 6, categories: ["effect_timing"], results_only: true});
  assert.equal(await page.locator("[data-action=analyze]").isDisabled(), true);
  await page.evaluate(() => {
    window.state = {...window.state, revision: 7, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, results_only: true}};
    window.controller.update(window.props());
  });
  const resultEditor = page.locator("[data-result-text]");
  assert.equal(await resultEditor.inputValue(), "Generated observation");
  await resultEditor.fill("Edited result for this Shot");
  await page.locator("[data-guidance]").click();
  await page.waitForFunction(() => window.commands.at(-1)?.result_text === "Edited result for this Shot");
  const textDelivery = await page.evaluate(() => window.commands.at(-1));
  assert.equal(textDelivery.action, "delivery");
  assert.equal(textDelivery.result_text, "Edited result for this Shot");
  assert.deepEqual(textDelivery.result_text_categories, ["effect_timing"]);
  await page.evaluate(() => {
    window.state = {...window.state, revision: 8, ack: window.commands.at(-1).id,
      result_text: "Edited result for this Shot"};
    window.controller.update(window.props());
  });
  await resultEditor.fill("Edited while changing route");
  await page.locator("[data-category=effect_shape]").check();
  const combinedDelivery = await page.evaluate(() => window.commands.at(-1));
  assert.equal(combinedDelivery.action, "delivery", "Click after text blur is not dropped");
  assert.deepEqual(combinedDelivery.categories, ["effect_shape", "effect_timing"]);
  assert.equal(combinedDelivery.result_text, "Edited while changing route", "Text draft accompanies route change");
  assert.deepEqual(combinedDelivery.result_text_categories, ["effect_timing"],
    "Text edit remains scoped to the prior category selection");
  await page.evaluate(() => {
    window.state = {...window.state, revision: 9, ack: window.commands.at(-1).id,
      result_text: "Edited while changing route",
      slot: {...window.state.slot, categories: ["effect_shape", "effect_timing"]}};
    window.controller.update(window.props());
  });
  await page.locator("[data-guidance]").fill("Look at the effect shape");
  await page.locator("[data-action=analyze]").click();
  const run = await page.evaluate(() => window.commands.at(-1));
  assert.equal(run.action, "analyze");
  assert.equal(run.confirmed_paid, true);
  assert.equal(run.guidance, "Look at the effect shape");
  assert.deepEqual(run.frame_ranges, [{start: 0, end: 95}]);
  assert.equal(run.full_video, false);
  assert.equal("start" in run || "end" in run, false);
  assert.equal(run.revision, 9);
  await page.evaluate(() => {
    window.state = {...window.state, revision: 10, ack: window.commands.at(-1).id};
    window.controller.update(window.props());
  });
  await resultEditor.fill("Save draft before switching shots");
  await page.getByRole("tab", {name: /05 Shot 5/}).click();
  assert.equal((await page.evaluate(() => window.commands.at(-1))).result_text,
    "Save draft before switching shots", "Leaving the Shot saves the active edit first");
  const beforeErrorCount = await page.evaluate(() => window.commands.length);
  await page.evaluate(() => {
    window.state = {...window.state, revision: 11, ack: window.commands.at(-1).id,
      error: "ANALYSIS_REQUEST_INVALID", status: "Unable to save result text"};
    window.controller.update(window.props());
  });
  assert.equal(await page.evaluate(() => window.commands.length), beforeErrorCount,
    "Failed delivery must not advance to the queued Shot");
  assert.equal(await resultEditor.inputValue(), "Save draft before switching shots",
    "Failed delivery retains the edit draft");
  await page.locator("[data-guidance]").fill("Unsubmitted guidance for Shot 1");
  await modelPicker.selectOption("gemini-4-argon");
  await watchStableShell(page);
  await page.getByRole("tab", {name: /05 Shot 5/}).click();
  assert.equal((await page.evaluate(() => window.commands.at(-1))).action, "delivery");
  await page.evaluate(() => {
    window.state = {...window.state, revision: 12, ack: window.commands.at(-1).id,
      error: "", status: "", result_text: "Save draft before switching shots"};
    window.controller.update(window.props());
  });
  await page.waitForFunction(() => window.commands.at(-1)?.action === "select_shot" && window.commands.at(-1)?.shot_uuid === "shot-5");
  const analysisCases = [
    {kind: "image", categories: {
      composition: "구도·프레이밍", lighting_reference: "라이팅 참고", color_look: "컬러 룩",
      character_pose: "캐릭터 포즈", appearance: "캐릭터·소품 외형",
    }},
    {kind: "audio", categories: {
      audio_content: "대사·발음", audio_delivery: "말투·감정", audio_rhythm: "리듬·강약",
      audio_effects: "효과음·환경음", audio_timing: "시작·종료 타이밍",
    }},
  ];
  for (const {kind, categories} of analysisCases) {
    await page.evaluate(({kind, keys}) => {
      window.state = {...window.state, shot_uuid: "shot-5", revision: window.state.revision + 1,
        ack: window.commands.at(-1).id, categories: keys, source: {kind, source_id: `${kind}:example`},
        slot: {kind, origin: "prompt", source_id: `${kind}:example`, categories: [],
          result: {cache_hit: true, observations: Object.fromEntries(keys.map(key => [key, [{observation: key}]]))}}};
      window.controller.update(window.props());
    }, {kind, keys: Object.keys(categories)});
    if (kind === "image") {
      await assertStableShell(page, "Shot click, queued save and acknowledgement");
      assert.equal(await page.locator("[data-guidance]").inputValue(), "", "Guidance does not leak into another Shot");
      assert.equal(await modelPicker.inputValue(), "", "Model draft does not leak into another Shot");
    }
    await assertCategoryRow(page, Object.values(categories));
    for (const category of Object.keys(categories)) {
      assert.equal(await page.locator("[data-category]:checked").count(), 0);
      await page.locator(`[data-category="${category}"]`).check();
      const selected = await page.evaluate(() => window.commands.at(-1));
      assert.equal(selected.shot_uuid, "shot-5");
      assert.equal(selected.action, "delivery");
      assert.deepEqual(selected.categories, [category]);
      assert.equal(selected.results_only, false);
      await page.evaluate(() => {
        window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
          slot: {...window.state.slot, categories: window.commands.at(-1).categories}};
        window.controller.update(window.props());
      });
      await page.locator(`[data-category="${category}"]`).uncheck();
      assert.deepEqual((await page.evaluate(() => window.commands.at(-1))).categories, [],
        "No checked categories requests all available results");
      await page.evaluate(() => {
        window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
          slot: {...window.state.slot, categories: []}};
        window.controller.update(window.props());
      });
    }
  }
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, categories: [],
      source: {kind: "image", source_id: "image:original", name: "Original image", preview_url: "/not-selected.png"},
      slot: {kind: "image", origin: "prompt", source_id: "image:original", categories: [], preview_url: "/fixture.png"}};
    window.controller.update(window.props());
  });
  await page.waitForFunction(() => document.querySelector(".ha-preview img")?.naturalWidth === 1);
  assert.equal(await page.locator(".ha-preview img").getAttribute("src"), "/fixture.png");
  assert.equal(await page.locator(".ha-interval-header").getByText("분석 프레임 구간", {exact: true}).isVisible(), true,
    "To Agent keeps the frame header even for an image");
  assert.equal(await page.locator("[data-action=toggle-range]").isDisabled(), true);
  assert.equal(await page.locator("[data-interval-track]").count(), 0);
  assert.equal(await page.locator("[data-results-only]").isEnabled(), true);
  assert.equal(await page.locator("[data-analysis-result-hint]").textContent(),
    "분석이 완료되면 결과가 있는 항목을 선택할 수 있습니다.");
  assert.equal(await page.locator("[data-agent],[data-original],[data-generator]").count(), 0);
  await page.locator("[data-results-only]").check();
  assert.equal((await page.evaluate(() => window.commands.at(-1))).results_only, true);
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, results_only: true}};
    window.controller.update(window.props());
  });
  await page.locator("[data-results-only]").uncheck();
  const paidCount = await page.evaluate(() => window.commands.filter(command => command.action === "analyze").length);
  const original = await page.evaluate(() => window.commands.at(-1));
  assert.deepEqual({...original, id: "fixture", revision: "fixture"}, {id: "fixture", revision: "fixture", action: "delivery",
    channel_uuid: "channel", shot_uuid: "shot-5", categories: [], results_only: false});
  assert.equal(await page.evaluate(() => window.commands.filter(command => command.action === "analyze").length), paidCount);
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, preview_url: "/unplayable-preview.png"}};
    window.controller.update(window.props());
  });
  await page.locator(".ha-preview").getByText("Original image · 미리보기를 열 수 없습니다.").waitFor();
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1,
      source: {...window.state.source, preview_url: ""},
      slot: {...window.state.slot, preview_url: "/\t/example.invalid/fake-preview.png"}};
    window.controller.update(window.props());
  });
  assert.equal(await page.locator(".ha-preview img").count(), 0, "Control characters cannot turn a relative URL into a remote request");
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1,
      source: {}, slot: {kind: "image", origin: "", categories: [], results_only: false},
      result_text: ""};
    window.controller.update(window.props());
  });
  assert.equal(await page.locator("[data-results-only]").isEnabled(), true,
    "Per-Shot results-only policy can be set before choosing a source");
  assert.equal(await page.locator(".ha-results-toggle-ui b").textContent(), "Agent에 분석 결과만 전달");
  assert.equal(await page.locator(".ha-results-toggle-ui em").textContent(), "OFF");
  await page.locator("[data-results-only]").check();
  assert.equal((await page.evaluate(() => window.commands.at(-1))).results_only, true);
  assert.equal(await page.locator(".ha-results-toggle-ui em").textContent(), "ON");
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      source: {kind: "video", source_id: "trimmed", name: "trimmed.mov", frame_count: 120, frame_rate: 24},
      slot: {kind: "video", origin: "prompt", source_id: "trimmed", frame_ranges: [{start: 10, end: 30}],
        categories: [], results_only: true}, result_text: ""};
    window.controller.update(window.props());
  });
  assert.equal(await page.locator("[data-interval-track]").getAttribute("data-interval-min"), "0");
  assert.equal(await page.locator("[data-interval-track]").getAttribute("data-interval-max"), "119");
  await page.locator("[data-action=toggle-range]").click();
  const trimmedTrack = await page.locator("[data-interval-track]").boundingBox();
  const trimEnd = await page.locator('[data-interval-handle="end"]').boundingBox();
  await page.mouse.move(trimEnd.x + trimEnd.width / 2, trimEnd.y + trimEnd.height / 2);
  await page.mouse.down();
  await page.mouse.move(trimmedTrack.x + trimmedTrack.width + 100, trimEnd.y + trimEnd.height / 2, {steps: 4});
  await page.mouse.up();
  assert.equal(await page.locator('[data-interval-index="0"]').getAttribute("title"), "10–119프레임", "Video end bounds the drag");
  const farTrack = await page.locator("[data-interval-track]").boundingBox();
  await page.mouse.move(farTrack.x + farTrack.width * .02, farTrack.y + farTrack.height / 2);
  await page.mouse.down();
  await page.mouse.move(farTrack.x + farTrack.width * .06, farTrack.y + farTrack.height / 2, {steps: 4});
  await page.mouse.up();
  assert.equal(await page.locator("[data-interval-index]").count(), 2, "Disjoint video ranges remain separate");
  await page.locator("[data-results-only]").uncheck();
  assert.equal(await page.locator("[data-interval-index]").count(), 2, "Unsubmitted ranges survive routing refresh");
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, results_only: false}};
    window.controller.update(window.props());
  });
  assert.equal(await page.locator("[data-interval-index]").count(), 2, "Unsubmitted ranges survive routing acknowledgement");
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1,
      source: {kind: "audio", source_id: "trimmed-audio", name: "trimmed.wav", start_seconds: 2, end_seconds: 8, duration_seconds: 20},
      slot: {kind: "audio", origin: "prompt", source_id: "trimmed-audio", time_ranges: [{start: 2, end: 4}],
        categories: [], results_only: false}};
    window.controller.update(window.props());
  });
  assert.equal(await page.locator("[data-interval-track]").getAttribute("data-interval-min"), "2");
  assert.equal(await page.locator("[data-interval-track]").getAttribute("data-interval-max"), "8");
  assert.equal(await page.locator("[data-start],[data-end]").count(), 0, "Audio also has no seconds input fields");
  const audioTrack = await page.locator("[data-interval-track]").boundingBox();
  await page.mouse.move(audioTrack.x + audioTrack.width * .55, audioTrack.y + audioTrack.height / 2);
  await page.mouse.down();
  await page.mouse.move(audioTrack.x + audioTrack.width * .7, audioTrack.y + audioTrack.height / 2, {steps: 4});
  await page.mouse.up();
  assert.equal(await page.locator("[data-interval-index]").count(), 2, "Disjoint audio intervals remain separate");
  await page.locator("[data-action=analyze]").click();
  const audioRun = await page.evaluate(() => window.commands.at(-1));
  assert.equal(audioRun.action, "analyze");
  assert.equal(audioRun.time_ranges.length, 2);
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      role: "after", available_roles: ["before", "after"],
      shots: window.state.shots.filter(shot => [1, 5].includes(shot.number))};
    window.controller.update(window.props());
  });
  assert.deepEqual(await page.locator(".ha-tabs [data-shot]").allTextContents(), ["01 Shot 1", "05 Shot 5"]);
  assert.equal(await page.getByText("Prompt · 리모트 5샷").count(), 0);
  assert.equal(await page.locator(".ha-header [data-action=refresh]").count(), 0);
  assert.equal(await page.locator(".ha-source-heading [data-action=refresh]").count(), 1);
  assert.ok(await page.locator(".ha-header").evaluate(header => {
    window.nativeActions = header.querySelector("[data-hmb-native-actions]");
    const identity = header.querySelector("[data-hmb-native-identity]");
    const root = header.closest(".hmb-analysis");
    root.dispatchEvent(new CustomEvent("hmb-color-lut-header-state", {detail: {active: true}}));
    const rolePicker = root.querySelector(".ha-role");
    return identity.nextElementSibling === rolePicker && rolePicker.nextElementSibling === window.nativeActions;
  }), "Role selector sits between the native identity and actions");
  assert.equal(await page.locator(".ha-role").evaluate(element => {
    const [before, after] = [...element.querySelectorAll("button")].map(button => button.getBoundingClientRect());
    return Math.abs(before.width - after.width) <= 1 && Math.abs(before.height - after.height) <= 1 &&
      before.height <= 28;
  }), true, "The before and after choices are equally sized compact controls");
  const toPrompt = page.getByRole("button", {name: "To Prompt", exact: true});
  const toAgent = page.getByRole("button", {name: "To Agent", exact: true});
  const activeAgentFill = await toAgent.evaluate(button => getComputedStyle(button).backgroundColor);
  await page.evaluate(() => {
    const nativeLink = document.createElement("button");
    nativeLink.textContent = "↔";
    nativeLink.setAttribute("aria-label", "Fixture native link");
    nativeLink.onclick = () => {
      const root = nativeLink.closest(".hmb-analysis");
      root.dispatchEvent(new CustomEvent("hmb-color-lut-header-state", {detail: {active: true}}));
    };
    window.nativeActions.append(nativeLink);
  });
  await watchStableShell(page);
  await page.getByRole("button", {name: "Fixture native link"}).click();
  await assertStableShell(page, "Native header action");
  await watchStableShell(page);
  await page.evaluate(() => {
    window.locked = true;
    window.controller.update(window.props());
  });
  assert.equal(await toPrompt.isDisabled(), true);
  await page.evaluate(() => {
    window.locked = false;
    window.controller.update(window.props());
  });
  await assertStableShell(page, "Lock and unlock");
  await page.locator("[data-guidance]").fill("Keep this guidance through same-Shot changes");
  await modelPicker.selectOption("gemini-4-argon");
  await watchStableShell(page);
  await page.locator(".ha-source-heading [data-action=refresh]").click();
  assert.equal((await page.evaluate(() => window.commands.at(-1))).action, "refresh");
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id};
    window.controller.update(window.props());
  });
  await assertStableShell(page, "Refresh click and acknowledgement");
  assert.equal(await page.locator("[data-guidance]").inputValue(), "Keep this guidance through same-Shot changes");
  assert.equal(await modelPicker.inputValue(), "gemini-4-argon", "Refresh retains the unsubmitted model choice");
  await watchStableShell(page);
  await toPrompt.click();
  const roleCommand = await page.evaluate(() => window.commands.at(-1));
  assert.deepEqual({...roleCommand, id: "fixture", revision: "fixture"}, {
    id: "fixture", revision: "fixture", action: "set_role", role: "before", channel_uuid: "channel", shot_uuid: "shot-5",
  });
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      role: "before", available_roles: ["before"], categories: ["audio_content"],
      slot: {...window.state.slot, fields: {PROJECT_STYLE_LOOK: "Generated look", PRESERVED_TEXT: "\n[Dialogue] Keep exact!"},
        result: {observations: {audio_content: [{observation: "Verified dialogue"}]}}}};
    window.controller.update(window.props());
  });
  await assertStableShell(page, "Role click and acknowledgement");
  assert.equal(await page.locator("[data-guidance]").inputValue(), "Keep this guidance through same-Shot changes");
  assert.equal(await modelPicker.inputValue(), "gemini-4-argon", "Same-source role change retains the unsubmitted model choice");
  assert.equal(await toPrompt.getAttribute("aria-pressed"), "true");
  assert.equal(await toAgent.isDisabled(), true);
  assert.notEqual(await toPrompt.evaluate(button => getComputedStyle(button).backgroundColor), activeAgentFill,
    "To Prompt and To Agent have distinct active colors");
  assert.equal(await analyze.textContent(), "To Prompt 실행");
  const audioToggle = page.locator("[data-action=toggle-range]");
  assert.equal(await audioToggle.getAttribute("aria-expanded"), "true");
  await audioToggle.click();
  assert.equal(await page.locator("[data-interval-track]").isVisible(), false);
  await audioToggle.click();
  assert.equal(await page.locator("[data-interval-track]").isVisible(), true);
  assert.equal(await page.locator("[data-hmb-native-actions]").evaluate(node => node === window.nativeActions), true,
    "Changing role retains the native actions portal");
  assert.deepEqual(await page.locator(".ha-field-tabs [data-field-tab]").allTextContents(),
    ["시각 방향", "장면 사실", "연기·감정", "정확 문자열", "VFX"]);
  for (const width of [800, 606, 430, 300]) {
    await page.locator("#widget").evaluate((element, width) => { element.style.width = `${width}px`; }, width);
    const matchingBoxes = await page.locator(".ha-field-tabs [data-field-tab]").evaluateAll(tabs => {
      const boxes = tabs.map(tab => tab.getBoundingClientRect());
      return boxes.every(box => ["width", "height", "top"].every(edge => Math.abs(box[edge] - boxes[0][edge]) <= 1));
    });
    assert.equal(matchingBoxes, true, `Five result tabs keep equal boxes in one row at ${width}px`);
  }
  await page.locator("#widget").evaluate(element => { element.style.width = "800px"; });
  assert.equal(await page.locator("[data-results-only],[data-result-text]").count(), 0);
  const promptEditor = page.locator("[data-field-text]");
  assert.equal(await promptEditor.inputValue(), "Generated look");
  await promptEditor.fill("Reviewed look");
  await page.getByRole("tab", {name: "정확 문자열"}).click();
  const saveField = await page.evaluate(() => window.commands.at(-1));
  assert.equal(saveField.action, "set_field");
  assert.equal(saveField.field, "PROJECT_STYLE_LOOK");
  assert.equal(saveField.text, "Reviewed look");
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      slot: {...window.state.slot, fields: {...window.state.slot.fields, PROJECT_STYLE_LOOK: "Reviewed look"}}};
    window.controller.update(window.props());
  });
  await page.waitForFunction(() => document.querySelector("[data-field-text]")?.dataset.fieldText === "PRESERVED_TEXT");
  assert.equal(await promptEditor.inputValue(), "\n[Dialogue] Keep exact!");
  await promptEditor.fill("");
  await promptEditor.blur();
  await page.waitForFunction(() => window.commands.at(-1).field === "PRESERVED_TEXT");
  const clearField = await page.evaluate(() => window.commands.at(-1));
  assert.equal(clearField.action, "set_field");
  assert.equal(clearField.text, "", "An explicitly empty field is saved as an authored value");
  await page.evaluate(() => {
    window.state = {...window.state, revision: window.state.revision + 1, ack: window.commands.at(-1).id,
      slot: {kind: "image"}, source: {}};
    window.controller.update(window.props());
  });
  assert.equal(await page.locator(".ha-interval-header").getByText("분석 프레임 구간", {exact: true}).isVisible(), true,
    "To Prompt keeps the frame header when a source is unavailable");
  assert.equal(await page.locator("[data-action=toggle-range]").isDisabled(), true);
  assert.deepEqual(errors, []);
  console.log("Analysis Agent widget: full-video default, saved frame ranges, role-specific run buttons, audio timeline, stable shell and saved Prompt fields PASS");
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
