import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import {
  hmbNormalizeImageAssetState,
  hmbSyncImageAssetRefreshReview,
  hmbRenderImageAssetRefreshReview,
  hmbImageAssetRefreshCleanupEligible,
  hmbInstallImageAssetRefreshReviewEvents,
  hmbPublishImageAssetState,
} from "../../widgets/HMBImageAssetLibraryWidget.js";

const report = {
  request_id: "review-1",
  project_root: "C:/projects/Example",
  project_id: "Example",
  status: "review",
  registered_count: 7,
  file_count: 8,
  missing_count: 1,
  unregistered_count: 2,
  safe_to_clean: true,
  error: "",
  missing_paths: ['Character/<missing> & "old".png'],
  unregistered_paths: ["Background/new.png", "Background/새 이미지.png"],
  cleaned_count: 0,
  backup_path: "",
  folders: [
    {label:"Ai_Ct_image",project_root:"C:/projects/Example",registered_count:3,file_count:4,missing_count:0,cleaned_count:0,backup_path:""},
    {label:"Partner A",project_root:"D:/Partner A",registered_count:4,file_count:4,missing_count:1,cleaned_count:0,backup_path:""},
  ],
};
const initial = hmbNormalizeImageAssetState({
  project_root: report.project_root,
  project_id: report.project_id,
  asset_refresh_review: report,
});
assert.deepEqual(initial.asset_refresh_review, report);
assert.deepEqual(hmbNormalizeImageAssetState(initial).asset_refresh_review, report);
assert.deepEqual(hmbNormalizeImageAssetState({ asset_refresh_review: [] }).asset_refresh_review, {});
assert.deepEqual(hmbNormalizeImageAssetState({ asset_cleanup_request: { request_id: "review-1", paths: ["injected"] } }).asset_cleanup_request, { request_id: "review-1" });
assert.equal(hmbImageAssetRefreshCleanupEligible(initial), true);
assert.equal(hmbImageAssetRefreshCleanupEligible(initial, { ...report, project_root: report.project_root.toUpperCase() }), true);
for (const change of [
  { safe_to_clean: false }, { safe_to_clean: "true" }, { missing_count: 0 },
  { status: "error" }, { status: "cleaned" }, { project_root: "C:/projects/Other" },
  { project_id: "Other" },
]) {
  assert.equal(hmbImageAssetRefreshCleanupEligible(initial, { ...report, ...change }), false);
}

const lifecycle = {};
let view = hmbSyncImageAssetRefreshReview(lifecycle, initial);
let markup = hmbRenderImageAssetRefreshReview(initial, view);
assert.match(markup, /data-refresh-cleanup-confirm[^>]*>확인</);
assert.match(markup, /이동되었거나 이름이 바뀌었을 수/);
assert.match(markup, /자동으로 등록하지 않습니다/);
assert.match(markup, /검사한 폴더/);
assert.match(markup, /Partner A/);
assert.ok(markup.includes("Character/&lt;missing&gt; &amp; &quot;old&quot;.png"));
assert.ok(!markup.includes("<missing>"));
delete lifecycle.__hmbImageAssetRefreshReviewOpen;
assert.equal(hmbSyncImageAssetRefreshReview(lifecycle, hmbNormalizeImageAssetState(initial)), null, "An echo must not reopen a dismissed report.");
assert.equal(hmbSyncImageAssetRefreshReview(lifecycle, { ...initial, asset_refresh_review: { ...report, status: "cleaned" } }), null, "A dismissed report stays closed when its status changes.");
const next = hmbNormalizeImageAssetState({ ...initial, asset_refresh_review: { ...report, request_id: "review-2" } });
assert.ok(hmbSyncImageAssetRefreshReview(lifecycle, next), "A new refresh token opens a fresh report.");
assert.equal(hmbSyncImageAssetRefreshReview(lifecycle, { ...next, project_root: "C:/projects/Other" }), null);

class Control {
  constructor() { this.handlers = new Map(); this.disabled = false; }
  addEventListener(type, handler) {
    const items = this.handlers.get(type) || [];
    items.push(handler);
    this.handlers.set(type, items);
  }
  focus() { this.focused = true; }
  removeEventListener(type, handler) {
    this.handlers.set(type, (this.handlers.get(type) || []).filter((item) => item !== handler));
  }
  setAttribute() {}
  removeAttribute() {}
  querySelectorAll() { return []; }
  dispatch(type, details = {}) {
    const event = { type, target: this, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; }, ...details };
    for (const handler of this.handlers.get(type) || []) handler(event);
    return event;
  }
}

function makeHarness(value = initial, publish = () => {}) {
  const writes = [];
  const container = {
    controls: new Map(),
    querySelector(selector) { return this.controls.get(selector) || null; },
    querySelectorAll(selector) {
      if (selector === "[data-refresh-review-cancel]") return [this.controls.get(selector)].filter(Boolean);
      return [];
    },
  };
  const props = { onChange(serialized) { writes.push(JSON.parse(serialized)); return publish(serialized); } };
  const remount = (incoming) => {
    const state = hmbNormalizeImageAssetState(incoming);
    container.__hmbImageAssetLatestState = state;
    const current = hmbSyncImageAssetRefreshReview(container, state);
    container.markup = hmbRenderImageAssetRefreshReview(state, current);
    container.controls.clear();
    for (const attribute of ["data-refresh-review-backdrop", "data-refresh-review-cancel", "data-refresh-cleanup-confirm"]) {
      if (container.markup.includes(attribute)) container.controls.set(`[${attribute}]`, new Control());
    }
    hmbInstallImageAssetRefreshReviewEvents(container, state, props, remount, (target, type, handler, options) => target?.addEventListener(type, handler, options));
    return state;
  };
  remount(value);
  return { container, props, writes, remount, click(selector) { return container.querySelector(selector)?.dispatch("click"); } };
}

const cancelled = makeHarness();
assert.match(cancelled.container.markup, /JSON 메타데이터만/);
assert.match(cancelled.container.markup, /실제 이미지 파일은 변경하지 않습니다/);
assert.match(cancelled.container.markup, /백업을 생성/);
assert.match(cancelled.container.markup, /기존 Shot은 수정하지 않습니다/);
assert.equal(cancelled.writes.length, 0, "Displaying the report never publishes.");
cancelled.click("[data-refresh-review-cancel]");
assert.equal(cancelled.writes.length, 0, "Cancel never publishes.");
assert.equal(cancelled.container.markup, "");
cancelled.remount(initial);
assert.equal(cancelled.container.markup, "", "An unrelated remount preserves dismissal.");

const escape = makeHarness();
const escaped = escape.container.querySelector("[data-refresh-review-backdrop]").dispatch("keydown", { key: "Escape" });
assert.equal(escaped.stopped, true);
assert.equal(escape.container.markup, "");
assert.equal(escape.writes.length, 0);

const confirmed = makeHarness();
const confirm = confirmed.container.querySelector("[data-refresh-cleanup-confirm]");
confirm.dispatch("click");
confirm.dispatch("click");
assert.equal(confirmed.writes.length, 1, "A duplicate confirm event cannot publish twice.");
assert.deepEqual(confirmed.writes[0].asset_cleanup_request, { request_id: report.request_id });
assert.deepEqual(confirmed.writes[0].asset_refresh_review, report);
assert.deepEqual(confirmed.container.__hmbImageAssetLatestState.asset_cleanup_request, {}, "The transient request is cleared locally after emission.");
const futureWrites = [];
hmbPublishImageAssetState(confirmed.container, { onChange(value) { futureWrites.push(JSON.parse(value)); } }, confirmed.container.__hmbImageAssetLatestState);
assert.deepEqual(futureWrites[0].asset_cleanup_request, {}, "Later state publications cannot replay cleanup.");
const cleanedState = hmbNormalizeImageAssetState({ ...confirmed.container.__hmbImageAssetLatestState, asset_refresh_review: {
  ...report, status: "cleaned", cleaned_count: 1, backup_path: "D:/Partner A/backup.json",
  folders: [report.folders[0], {...report.folders[1], missing_count:0, cleaned_count:1, backup_path:"D:/Partner A/backup.json"}],
} });
confirmed.remount(cleanedState);
assert.match(confirmed.container.markup, /정리한 등록: 1/);
assert.match(confirmed.container.markup, /backup\.json/);
assert.equal(confirmed.container.__hmbImageAssetRefreshCleanupPending, undefined);
assert.equal(confirmed.container.querySelector("[data-refresh-cleanup-confirm]"), null);

let syncHarness;
syncHarness = makeHarness(initial, () => {
  syncHarness.remount(cleanedState);
});
syncHarness.click("[data-refresh-cleanup-confirm]");
assert.equal(syncHarness.container.__hmbImageAssetLatestState.asset_refresh_review.status, "cleaned", "A synchronous server completion must not be overwritten by the submitted review.");

let rejectTransport;
const failed = makeHarness(initial, () => new Promise((_resolve, reject) => { rejectTransport = reject; }));
failed.click("[data-refresh-cleanup-confirm]");
const previousError = console.error;
console.error = () => {};
try {
  rejectTransport(new Error("cleanup transport failed"));
  await Promise.resolve();
  assert.equal(failed.container.__hmbImageAssetRefreshCleanupPending, undefined);
  assert.match(failed.container.markup, /cleanup transport failed/);
  assert.deepEqual(failed.container.__hmbImageAssetLatestState.asset_cleanup_request, {});
} finally {
  console.error = previousError;
}

const english = hmbNormalizeImageAssetState({ ...initial, language: "en" });
markup = hmbRenderImageAssetRefreshReview(english, { review: english.asset_refresh_review });
assert.match(markup, /Media files are unaffected/);
assert.match(markup, /Existing Shots are not edited/);
assert.match(markup, /not added automatically/);

console.log("HMB ImageAsset Refresh review regression: PASS (safe review, explicit confirmation, dismissal, escaped paths, transient command, completion and failure)");

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch {
  try { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
  catch { /* Pure state/event regressions above remain portable. */ }
}
const executablePath = process.env.HMB_IMAGE_ASSET_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (playwright && fs.existsSync(executablePath)) {
  const widgetSource = fs.readFileSync(new URL("../../widgets/HMBImageAssetLibraryWidget.js", import.meta.url));
  const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#111}#widget{width:1100px;height:780px}</style><div id="widget"></div><script type="module">
    import mount, * as widget from '/widget.js'; window.widget=widget;
    window.mountReview=(state,compact)=>{window.controller?.cleanup();const previous=document.getElementById('widget'),container=document.createElement('div');container.id='widget';previous.replaceWith(container);window.container=container;window.writes=[];window.props=(value)=>({value,onChange:(serialized)=>window.writes.push(JSON.parse(serialized))});window.controller=mount(container,window.props(state));if(compact)widget.hmbSetImageAssetLibraryCompact(container,true,{geometry:false});};window.ready=true;
  </script>`;
  let browser;
  try {
    browser = await playwright.chromium.launch({ executablePath, headless: true });
    const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
    page.setDefaultTimeout(6000);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("http://imageasset.test/**", route => {
      const script = new URL(route.request().url()).pathname === "/widget.js";
      return route.fulfill({ contentType: script ? "text/javascript" : "text/html", body: script ? widgetSource : html });
    });
    await page.goto("http://imageasset.test/");
    await page.waitForFunction(() => window.ready);
    await page.clock.install();
    const saved = { ...initial, project_uid: "example", project_cache_uid: "example-cache", asset_refresh_review: {} };
    await page.evaluate(value => {
      window.bridgeRequests = [];
      const registry = window.__HMB_IMAGE_ASSET_THUMBNAIL_PATCH_BRIDGES_V1__ ||= new Map();
      registry.set(value.shot_routing.publisher_instance_uuid, { dispatch: request => window.bridgeRequests.push(request) });
      window.mountReview(value, false);
    }, saved);
    await page.clock.fastForward(61000);
    await page.evaluate(value => {
      document.dispatchEvent(new Event("visibilitychange"));
      window.dispatchEvent(new Event("focus"));
      window.controller.update(window.props(value));
    }, saved);
    await page.clock.fastForward(61000);
    await page.evaluate(value => window.mountReview(value, false), saved);
    await page.clock.fastForward(61000);
    assert.deepEqual(await page.evaluate(() => window.bridgeRequests.filter(request => request.operation === "catalog_probe")), [],
      "Idle time, focus and reopening a saved widget must never poll the shared catalog.");
    assert.equal(await page.evaluate(() => window.writes.some(value => (value.edits || value).refresh_revision > 0)), false);
    const reload = page.locator("[data-project-reload]");
    await reload.click();
    await page.waitForFunction(() => window.writes.some(value => (value.edits || value).refresh_revision === 1));
    assert.equal(await reload.isDisabled(), true);
    await page.evaluate(() => {
      window.ack = { ...window.container.__hmbImageAssetLatestState, scan_busy: true, scan_request_id: "lost-ack", refresh_revision: 1 };
      window.controller.update(window.props(window.ack));
    });
    await page.clock.fastForward(41000);
    assert.equal(await reload.isEnabled(), true, "A missing completion frees the Refresh button");
    assert.match(await page.locator("[data-transport-status]").textContent(), /새로고침 결과를 받지 못했습니다/);
    await page.evaluate(() => window.controller.update(window.props({ ...window.ack })));
    assert.equal(await reload.isEnabled(), true, "A late busy frame cannot re-lock Refresh");
    await reload.click();
    await page.waitForFunction(() => window.writes.some(value => (value.edits || value).refresh_revision === 2));
    await page.evaluate(() => {
      const result = { ...window.container.__hmbImageAssetLatestState, scan_busy: false, scan_request_id: "refresh-two", refresh_revision: 2 };
      window.controller.update(window.props(result));
      window.controller.update(window.props({ ...result, scan_busy: true }));
    });
    assert.equal(await reload.isEnabled(), true, "A successful retry stays idle after an out-of-order busy frame");
    for (const compact of [false, true]) {
      await page.evaluate(({ value, compact }) => window.mountReview(value, compact), { value: { ...initial, asset_refresh_review: {} }, compact });
      const sizeBefore = await page.locator(".hmb-image-assets").boundingBox();
      await page.evaluate((report) => {
        window.controller.update(window.props({ ...window.container.__hmbImageAssetLatestState, scan_revision: 1, asset_refresh_review: report }));
      }, report);
      const layout = await page.locator("[data-refresh-review-backdrop]").evaluate((backdrop) => ({
        insideHiddenExpanded: Boolean(backdrop.closest("[data-library-expanded]")),
        compact: backdrop.parentElement.getAttribute("data-library-compact"),
        topInert: backdrop.parentElement.querySelector(".top").inert,
        compactContentInert: backdrop.parentElement.querySelector("[data-library-compact-summary]").inert,
        dialogHeight: backdrop.querySelector('[role="dialog"]').getBoundingClientRect().height,
      }));
      assert.equal(layout.insideHiddenExpanded, false);
      assert.equal(layout.compact, String(compact));
      assert.equal(layout.topInert, true);
      assert.equal(layout.compactContentInert, true);
      assert.ok(layout.dialogHeight > 50, JSON.stringify(layout));
      const sizeDuring = await page.locator(".hmb-image-assets").boundingBox();
      assert.equal(sizeDuring.height, sizeBefore.height, "The modal must not resize or switch the compact/expanded layout.");
      assert.equal(await page.evaluate(() => window.writes.length), 0);
      await page.locator("[data-refresh-cleanup-confirm]").click();
      assert.equal(await page.evaluate(() => window.writes.length), 1);
      assert.deepEqual(await page.evaluate(() => window.writes[0].asset_cleanup_request), { request_id: report.request_id });
      await page.evaluate((report) => {
        window.controller.update(window.props({ ...window.container.__hmbImageAssetLatestState, scan_revision: 2, asset_refresh_review: { ...report, status: "cleaned", cleaned_count: 1, backup_path: "backup.json" } }));
      }, report);
      assert.match(await page.locator("[data-refresh-review-backdrop]").textContent(), /정리한 등록: 1/);
      await page.locator("[data-refresh-review-cancel]").first().click();
      assert.equal(await page.locator("[data-refresh-review-backdrop]").count(), 0);
      assert.equal(await page.locator(".top").evaluate((element) => element.inert), false);
      assert.equal(await page.locator(".hmb-image-assets").getAttribute("data-library-compact"), String(compact));
    }
    assert.deepEqual(errors, []);
    console.log("HMB ImageAsset Refresh browser regression: PASS (session catalog stays pinned through idle, focus and reopen; explicit refresh, expanded and compact review, confirm, close)");
  } finally {
    await browser?.close();
  }
} else console.log("HMB ImageAsset Refresh browser regression: SKIP (optional Playwright/Chrome unavailable)");
