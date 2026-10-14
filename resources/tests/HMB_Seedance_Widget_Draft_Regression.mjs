import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const argument = (name) => { const index = process.argv.indexOf(name); return index < 0 ? "" : process.argv[index + 1] || ""; };
const libraryRoot = path.resolve(argument("--library-root") || fileURLToPath(new URL("../..", import.meta.url)));
const sourcePath = path.join(libraryRoot, "widgets/HMBSeedanceGenerationWidget.js");
const source = fs.readFileSync(sourcePath, "utf8");
const evidenceDir = argument("--evidence-dir");
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const executablePath = process.env.HMB_SEEDANCE_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const browser = await playwright.chromium.launch({ executablePath, headless: true });
const receipt = { schema: "hmb-seedance-draft-widget-regression", source_path: sourcePath,
  source_sha256: crypto.createHash("sha256").update(fs.readFileSync(sourcePath)).digest("hex"),
  scope: "Isolated real Chrome DOM, actual widget and retained action bridge; mocked host command callback only",
  live_graph_calls: 0, paid_api_calls: 0, external_requests: 0, cases: [] };
try {
  const page = await browser.newPage({ viewport: { width: 900, height: 340 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => { receipt.external_requests += 1; return route.abort(); });
  await page.setContent('<!doctype html><meta charset="utf-8"><style>body{background:#080c14;color:#fff}.react-flow__node{width:650px;margin:12px}</style><main></main>');
  await page.evaluate(async (code) => {
    window.widget = await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
    const ids = [1, 2, 3, 4].map((n) => `10000000-0000-4000-8000-${String(n).padStart(12, "0")}`);
    const catalog = { schema: "hmb-shot-routing-catalog", version: 1, publisher_instance_uuid: ids[0],
      channel_uuid: ids[1], generation: 1, metadata_sha256: "a".repeat(64),
      shots: [2, 3].map((index) => ({ shot_uuid: ids[index], number: index - 1, name: `Shot ${index - 1}`, revision: 1 })) };
    window.makeState = (shot = 1, changes = {}) => ({ schema: "hmb-seedance-shot-ui", schema_version: 2,
      shot_catalog: catalog, shot: shot ? { channel_uuid: ids[1], shot_uuid: ids[shot + 1], number: shot, name: `Shot ${shot}` } : {},
      generation: { schema: "hmb-seedance-generation-preview", version: 1, phase: "succeeded", job_id: `draft-${shot}`, media_revision: 1 },
      draft: { visible: true, action: "Draft (480p)", preview_available: false, final_available: true,
        job_id: `job-${String(shot).padStart(32, "0")}`, effective_resolution: "1080p", busy: false, reason: "", ...changes } });
    window.frames = new Map(); let frameId = 0;
    window.requestAnimationFrame = (callback) => { window.frames.set(++frameId, callback); return frameId; };
    window.cancelAnimationFrame = (id) => window.frames.delete(id);
    window.flushFrames = async () => {
      for (const [id, callback] of [...window.frames]) { window.frames.delete(id); callback(); }
      await new Promise((resolve) => setTimeout(resolve, 0));
    };
    window.fixtures = [];
    window.createFixture = (state = window.makeState(), transport = true) => {
      const node = document.createElement("div"); node.className = "react-flow__node";
      node.innerHTML = '<div data-header></div><div data-parameter-name="HMB_SEEDANCE_REFRESH_COMMAND"><div data-command></div></div>';
      document.querySelector("main").appendChild(node);
      const container = node.querySelector("[data-header]");
      const f = { node, container, commands: [], authored: [], rejects: [], state, transport };
      f.props = (value) => ({ value, onChange(next) { f.authored.push(next); return new Promise(() => {}); } });
      if (transport) f.bridge = widget.default(node.querySelector("[data-command]"), {
        value: { schema: "hmb-seedance-refresh-command", version: 1 },
        onChange(value) { f.commands.push(value); return new Promise((_, reject) => f.rejects.push(reject)); },
      });
      f.controller = widget.default(container, f.props(state));
      f.update = (value) => { f.state = value; f.controller.update(f.props(value)); };
      f.button = () => container.querySelector("[data-hmb-seedance-finalize-draft]");
      f.cleanup = () => { f.controller.cleanup(); f.bridge?.cleanup(); node.remove(); };
      window.fixtures.push(f); return f;
    };
    window.view = (f) => ({ hidden: f.button().hidden, disabled: f.button().disabled,
      text: f.button().textContent, title: f.button().title, busy: f.button().getAttribute("aria-busy"),
      error: f.container.querySelector(".hmb-seedance-shot__status").textContent });
  }, source);
  const check = async (name, callback) => {
    await callback(); receipt.cases.push({ name, passed: true });
    await page.evaluate(() => { window.fixtures.splice(0).forEach((f) => f.cleanup()); });
  };
  await check("completed-current-Shot-and-Only-visible-without-preview-option", async () => {
    const results = await page.evaluate(() => [1, 0].map((shot) => window.view(createFixture(makeState(shot)))));
    results.forEach((result) => { assert.equal(result.hidden, false); assert.equal(result.disabled, false); assert.equal(result.text, "Draft final"); assert.match(result.title, /Generator만 1회/); assert.match(result.title, /1080p/); assert.match(result.title, /MOV 기본/); assert.match(result.title, /MOV 미지원 시 MP4/); });
  });
  await check("absent-legacy-pending-invalid-deleted-source-fail-closed", async () => {
    const results = await page.evaluate(() => {
      const legacy = makeState(); delete legacy.draft;
      const deleted = makeState(); deleted.shot_catalog = {};
      return [legacy, deleted, makeState(1, { job_id: "" }), makeState(1, { visible: false }),
        makeState(1, { busy: true }), makeState(1, { final_available: false, reason: "Draft 확인 필요" })]
        .map((value) => view(createFixture(value)));
    });
    results.slice(0, 4).forEach((value) => assert.equal(value.hidden, true));
    results.forEach((value) => assert.equal(value.disabled, true));
    assert.equal(results.at(-1).title, "Draft 확인 필요");
  });
  await check("paint-first-double-click-one-bound-action-envelope", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); const button = f.button(); button.click(); button.click();
      const before = { count: f.commands.length, ...view(f) };
      await flushFrames(); f.update(makeState());
      return { before, commands: f.commands, authored: f.authored, retained: f.button() === button, after: view(f) };
    });
    assert.equal(result.before.count, 0); assert.equal(result.before.disabled, true);
    assert.equal(result.commands.length, 1); assert.equal(result.authored.length, 0); assert.equal(result.retained, true);
    assert.equal(result.after.disabled, true);
    assert.deepEqual(Object.keys(result.commands[0]).sort(), ["action", "action_id", "expected_draft_job_id", "issued_at_ms", "schema", "version"]);
    assert.equal(result.commands[0].action, "finalize_draft"); assert.match(result.commands[0].action_id, /^final-/);
    assert.equal(result.commands[0].expected_draft_job_id, `job-${"1".padStart(32, "0")}`);
    assert.equal(result.commands[0].schema, "hmb-seedance-refresh-command");
  });
  await check("Final-bridge-requires-Draft-assertion-refresh-gallery-unchanged", async () => {
    const result = await page.evaluate(() => {
      const f = createFixture();
      const bridge = window.__HMB_SEEDANCE_REFRESH_BRIDGES_V1__.get(f.node);
      let rejected = 0;
      for (const expected of [undefined, "", "arbitrary-id", `job-${"f".repeat(33)}`]) {
        try { bridge.dispatch({ action: "finalize_draft", action_id: "assertion-test", expected_draft_job_id: expected }); }
        catch { rejected += 1; }
      }
      for (const action of ["refresh_existing", "open_gallery"]) {
        bridge.dispatch({ action, action_id: "legacy-test", expected_draft_job_id: f.state.draft.job_id });
      }
      return { rejected, commands: f.commands };
    });
    assert.equal(result.rejected, 4); assert.equal(result.commands.length, 2);
    for (const command of result.commands) assert.deepEqual(Object.keys(command).sort(), ["action", "action_id", "issued_at_ms", "schema", "version"]);
  });
  await check("busy-acknowledgement-dismisses-late-delivery-rejection", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.button().click(); await flushFrames();
      f.update(makeState(1, { busy: true })); f.rejects[0](new Error("old delivery error")); await Promise.resolve();
      return { ...view(f), pending: Boolean(f.container.__hmbSeedanceDraftPending), accepted: widget.hmbSeedanceRequestDraftFinal(f.container) };
    });
    assert.equal(result.disabled, true); assert.equal(result.pending, false); assert.equal(result.error, ""); assert.equal(result.accepted, false);
  });
  await check("Shot-change-before-dispatch-cancels-old-Draft-and-stale-echo", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.button().click();
      const select = f.container.querySelector("select"); select.value = select.options[2].value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      const optimistic = view(f); f.update(makeState()); const stale = view(f);
      await flushFrames(); f.update(makeState(2));
      return { optimistic, stale, acknowledged: view(f), commands: f.commands.length, authored: f.authored.length };
    });
    assert.equal(result.optimistic.hidden, true); assert.equal(result.stale.hidden, true);
    assert.equal(result.commands, 0); assert.equal(result.authored, 1); assert.equal(result.acknowledged.hidden, false);
  });
  await check("node-deletion-before-paint-and-cleanup-cancel-dispatch", async () => {
    const counts = await page.evaluate(async () => {
      const removed = createFixture(); removed.button().click(); removed.node.remove();
      const cleaned = createFixture(); cleaned.button().click(); cleaned.controller.cleanup();
      await flushFrames(); return [removed.commands.length, cleaned.commands.length];
    });
    assert.deepEqual(counts, [0, 0]);
  });
  await check("late-promise-on-new-Shot-never-overwrites-current-state", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.button().click(); await flushFrames();
      f.update(makeState(2)); f.rejects[0](new Error("previous Shot rejected")); await Promise.resolve();
      return view(f);
    });
    assert.equal(result.hidden, false); assert.equal(result.disabled, false); assert.equal(result.error, "");
  });
  await check("delayed-host-consumption-keeps-clicked-Draft-assertion", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); const clicked = f.state.draft.job_id;
      f.button().click(); await flushFrames(); const command = structuredClone(f.commands[0]);
      f.update(makeState(2));
      // Model delayed host consumption only. The actual Python equality guard
      // is exercised separately by the native core regression.
      const currentStoredId = f.state.draft.job_id;
      return { clicked, currentStoredId, command,
        accepted: command.expected_draft_job_id === currentStoredId };
    });
    assert.equal(result.command.expected_draft_job_id, result.clicked);
    assert.notEqual(result.clicked, result.currentStoredId);
    assert.equal(result.accepted, false, "A delayed Shot A click cannot nominate the now-current Shot B Draft.");
  });
  await check("delivery-failure-retry-reuses-idempotency-ID", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.button().click(); await flushFrames();
      f.rejects[0](new Error("delivery not confirmed")); await Promise.resolve();
      const failed = view(f); f.button().click(); await flushFrames();
      return { failed, commands: f.commands };
    });
    assert.equal(result.failed.disabled, false); assert.equal(result.failed.error, "delivery not confirmed");
    assert.equal(result.commands.length, 2); assert.equal(result.commands[0].action_id, result.commands[1].action_id);
  });
  await check("delivery-watchdog-retry-reuses-idempotency-ID", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); const nativeTimeout = window.setTimeout; let timeout;
      window.setTimeout = (callback, delay, ...args) => {
        if (delay === widget.HMB_SEEDANCE_PREVIEW_ACTION_WATCHDOG_MS) { timeout = callback; return 0; }
        return nativeTimeout(callback, delay, ...args);
      };
      try {
        f.button().click(); await flushFrames(); timeout(); const released = view(f);
        f.button().click(); await flushFrames(); return { released, commands: f.commands };
      } finally { window.setTimeout = nativeTimeout; }
    });
    assert.equal(result.released.disabled, false); assert.match(result.released.error, /전달/);
    assert.equal(result.commands.length, 2); assert.equal(result.commands[0].action_id, result.commands[1].action_id);
  });
  await check("missing-or-detached-command-carrier-never-falls-back-to-Run", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(makeState(), false); const noBridge = widget.hmbSeedanceRequestDraftFinal(f.container);
      const g = createFixture(); g.button().click(); g.bridge.cleanup(); await flushFrames();
      return { noBridge, noBridgeView: view(f), commands: g.commands.length, detachedView: view(g) };
    });
    assert.equal(result.noBridge, false); assert.match(result.noBridgeView.error, /전달/);
    assert.equal(result.commands, 0); assert.match(result.detachedView.error, /전달/);
  });
  await check("multiple-generators-isolated-and-retained-factory-no-duplicate-listeners", async () => {
    const result = await page.evaluate(async () => {
      const all = Array.from({ length: 5 }, () => createFixture());
      for (const f of all) { f.controller = widget.default(f.container, f.props(f.state)); f.button().click(); f.button().click(); }
      await flushFrames(); return all.map((f) => f.commands);
    });
    result.forEach((commands) => assert.equal(commands.length, 1));
    assert.equal(new Set(result.flat().map((command) => command.action_id)).size, 5);
  });
  await check("queued-Final-shows-local-Stop-double-click-sends-one-bound-cancel", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.button().click(); await flushFrames();
      const active = f.state.draft.job_id;
      f.update(makeState(1, { busy: true, final_available: false, cancel_available: true, active_job_id: active }));
      const running = view(f); f.button().click(); f.button().click(); const queued = view(f);
      await flushFrames();
      f.update(makeState(1, { final_available: false, reason: "Use existing Task retrieval" }));
      return { active, running, queued, commands: f.commands, acknowledged: view(f) };
    });
    assert.equal(result.running.text, "Final 중지"); assert.equal(result.running.disabled, false);
    assert.match(result.running.title, /로컬.*서버 렌더는 계속/);
    assert.equal(result.queued.disabled, true); assert.equal(result.queued.text, "중지 요청 중…");
    assert.equal(result.commands.length, 2); assert.equal(result.commands[1].action, "cancel_draft_final");
    assert.equal(result.commands[1].expected_draft_job_id, result.active);
    assert.equal(result.acknowledged.disabled, true); assert.notEqual(result.acknowledged.text, "Final 중지");
  });
  await check("Stop-follows-active-Draft-through-Shot-switch-and-missing-catalog", async () => {
    const result = await page.evaluate(async () => {
      const active = makeState(1).draft.job_id;
      const f = createFixture(makeState(1, { busy: true, cancel_available: true, active_job_id: active }));
      const select = f.container.querySelector("select"); select.value = select.options[2].value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      const duringSwitch = view(f); f.button().click();
      const changed = makeState(2, { visible: false, final_available: false, busy: true,
        cancel_available: true, active_job_id: active }); changed.shot_catalog = {};
      f.update(changed); await flushFrames();
      return { active, duringSwitch, commands: f.commands, view: view(f) };
    });
    assert.equal(result.duringSwitch.text, "Final 중지"); assert.equal(result.duringSwitch.hidden, false);
    assert.equal(result.commands.length, 1); assert.equal(result.commands[0].action, "cancel_draft_final");
    assert.equal(result.commands[0].expected_draft_job_id, result.active);
  });
  await check("stale-Stop-rejection-cannot-change-new-active-Final", async () => {
    const result = await page.evaluate(async () => {
      const a = makeState(1).draft.job_id; const b = makeState(2).draft.job_id;
      const f = createFixture(makeState(1, { busy: true, cancel_available: true, active_job_id: a }));
      f.button().click(); await flushFrames();
      f.update(makeState(2, { busy: true, cancel_available: true, active_job_id: b }));
      f.rejects[0](new Error("Old cancel rejected")); await Promise.resolve();
      const current = view(f); f.button().click(); await flushFrames();
      return { a, b, current, commands: f.commands };
    });
    assert.equal(result.current.error, ""); assert.equal(result.current.disabled, false);
    assert.equal(result.commands[0].expected_draft_job_id, result.a);
    assert.equal(result.commands[1].expected_draft_job_id, result.b);
  });
  await check("cleanup-or-deleted-node-never-delivers-pending-Stop", async () => {
    const counts = await page.evaluate(async () => {
      const running = () => makeState(1, { busy: true, cancel_available: true, active_job_id: makeState(1).draft.job_id });
      const a = createFixture(running()); a.button().click(); a.node.remove();
      const b = createFixture(running()); b.button().click(); b.controller.cleanup();
      await flushFrames(); return [a.commands.length, b.commands.length];
    });
    assert.deepEqual(counts, [0, 0]);
  });
  await check("header-geometry-600-and-360-retains-Shot-selector-and-Final", async () => {
    const results = await page.evaluate(() => [600, 360].map((width) => {
      const f = createFixture(); f.node.style.width = `${width}px`;
      const root = f.container.querySelector(".hmb-seedance-shot").getBoundingClientRect();
      return { width, height: root.height, controls: [f.button(), f.container.querySelector("select")].map((element) => {
        const box = element.getBoundingClientRect(); return { left: box.left - root.left, right: box.right - root.right, height: box.height, width: box.width };
      }) };
    }));
    for (const result of results) {
      assert.equal(result.height, 64);
      result.controls.forEach((box) => { assert.ok(box.left >= 0 && box.right <= 0); assert.ok(box.width > 0 && box.height > 0); });
    }
  });
  assert.deepEqual(errors, []); assert.equal(receipt.external_requests, 0);
  assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest|WebSocket)\s*\(/);
  receipt.status = "PASS";
  if (evidenceDir) {
    fs.mkdirSync(evidenceDir, { recursive: true });
    await page.evaluate(() => createFixture());
    await page.screenshot({ path: path.join(evidenceDir, "draft-final-header.png") });
    await page.evaluate(() => {
      const f = window.fixtures.at(-1);
      f.update(makeState(1, { busy: true, final_available: false, cancel_available: true, active_job_id: f.state.draft.job_id }));
    });
    await page.screenshot({ path: path.join(evidenceDir, "draft-stop-header.png") });
  }
  console.log(`HMB Seedance Draft widget: PASS (${receipt.cases.length} real-browser cases; graph/API/paid 0)`);
} catch (error) { receipt.status = "FAIL"; receipt.error = error.stack; throw error; }
finally {
  await browser.close();
  if (evidenceDir) { fs.mkdirSync(evidenceDir, { recursive: true }); fs.writeFileSync(path.join(evidenceDir, "widget-draft-receipt.json"), JSON.stringify(receipt, null, 2)); }
}
