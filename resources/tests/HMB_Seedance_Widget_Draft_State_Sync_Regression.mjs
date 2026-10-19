import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const argument = (name) => { const index = process.argv.indexOf(name); return index < 0 ? "" : process.argv[index + 1] || ""; };
const root = path.resolve(argument("--library-root") || fileURLToPath(new URL("../..", import.meta.url)));
const sourcePath = path.join(root, "widgets/HMBSeedanceGenerationWidget.js");
const source = fs.readFileSync(sourcePath, "utf8");
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const browser = await playwright.chromium.launch({
  executablePath: process.env.HMB_SEEDANCE_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true,
});
const receipt = { schema: "hmb-seedance-draft-state-sync-widget-regression", source_path: sourcePath,
  source_sha256: crypto.createHash("sha256").update(source).digest("hex"),
  scope: "Actual widget in isolated Chromium; retained host command callbacks are mocked. Server responses are fixture projections, never live requests.",
  live_graph_calls: 0, paid_api_calls: 0, external_requests: 0, cases: [] };
try {
  const page = await browser.newPage({ viewport: { width: 950, height: 420 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => { receipt.external_requests += 1; return route.abort(); });
  await page.setContent('<!doctype html><meta charset="utf-8"><style>body{background:#080c14;color:white}.react-flow__node{width:680px;margin:8px}</style><main></main>');
  await page.evaluate(async (code) => {
    window.widget = await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
    const ids = [1, 2, 3, 4].map((n) => `20000000-0000-4000-8000-${String(n).padStart(12, "0")}`);
    const catalog = { schema: "hmb-shot-routing-catalog", version: 1, publisher_instance_uuid: ids[0],
      channel_uuid: ids[1], generation: 1, metadata_sha256: "a".repeat(64),
      shots: [2, 3].map((n) => ({ shot_uuid: ids[n], number: n - 1, name: `Approved ${n - 1}`, revision: 1 })) };
    window.makeState = (shot = 1, changes = {}) => ({ schema: "hmb-seedance-shot-ui", schema_version: 2,
      shot_catalog: catalog, shot: shot ? { channel_uuid: ids[1], shot_uuid: ids[shot + 1], number: shot, name: `Approved ${shot}` } : {},
      generation: { schema: "hmb-seedance-generation-preview", version: 1, phase: "succeeded",
        job_id: `job-${String(shot + 1).padStart(32, "0")}`, media_revision: 1, has_existing_video: true },
      draft: { visible: true, action: "Draft 480p", preview_available: true, final_available: true,
        job_id: `job-${String(shot + 1).padStart(32, "0")}`, effective_resolution: "480p", busy: false,
        final_busy: false, final_state: "available", final_visible: true, final_task_id: "", reason: "", ...changes } });
    window.frames = new Map(); let nextFrame = 0;
    window.requestAnimationFrame = (callback) => { window.frames.set(++nextFrame, callback); return nextFrame; };
    window.cancelAnimationFrame = (id) => window.frames.delete(id);
    window.flushFrames = async () => {
      for (const [id, callback] of [...window.frames]) { window.frames.delete(id); callback(); }
      await new Promise((resolve) => setTimeout(resolve, 0));
    };
    window.fixtures = [];
    window.createFixture = (value = makeState()) => {
      const node = document.createElement("div"); node.className = "react-flow__node";
      node.innerHTML = '<div data-header></div><div data-parameter-name="HMB_SEEDANCE_REFRESH_COMMAND"><div data-command></div></div><input data-parameter-name="resolution" value="480p"><input data-parameter-name="draft_action" value="Draft 480p">';
      document.querySelector("main").append(node);
      const f = { node, container: node.querySelector("[data-header]"), commands: [], authored: [], rejects: [], state: value };
      f.props = (state) => ({ value: state, onChange(next) { f.authored.push(next); return new Promise(() => {}); } });
      f.bridge = widget.default(node.querySelector("[data-command]"), { value: { schema: "hmb-seedance-refresh-command", version: 1 },
        onChange(command) { f.commands.push(command); return new Promise((_, reject) => f.rejects.push(reject)); } });
      f.controller = widget.default(f.container, f.props(value));
      f.update = (state) => { f.state = state; f.controller.update(f.props(state)); };
      f.button = () => f.container.querySelector("[data-hmb-seedance-finalize-draft]");
      f.cleanup = () => { f.controller.cleanup(); f.bridge.cleanup(); node.remove(); };
      fixtures.push(f); return f;
    };
    window.view = (f) => ({ hidden: f.button().hidden, disabled: f.button().disabled,
      text: f.button().textContent, busy: f.button().getAttribute("aria-busy"), title: f.button().title,
      error: f.container.querySelector(".hmb-seedance-shot__status").textContent,
      resolution: f.node.querySelector('[data-parameter-name="resolution"]').value,
      action: f.node.querySelector('[data-parameter-name="draft_action"]').value });
    window.addPlayablePreview = async (f) => {
      const canvas = document.createElement("canvas"); canvas.width = 32; canvas.height = 24;
      canvas.getContext("2d").fillRect(0, 0, 32, 24);
      const stream = canvas.captureStream(8), chunks = [];
      const recorder = new MediaRecorder(stream, { mimeType: "video/webm;codecs=vp8" });
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      const stopped = new Promise((resolve) => recorder.addEventListener("stop", resolve, { once: true }));
      recorder.start(); await new Promise((resolve) => setTimeout(resolve, 180)); recorder.stop(); await stopped;
      stream.getTracks().forEach((track) => track.stop());
      const video = document.createElement("video"); video.muted = true; video.width = 600; video.height = 220;
      video.dataset.rawVideoValue = "https://fixture.invalid/retained-original.mov";
      const ready = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Isolated video did not become playable")), 3000);
        video.addEventListener("canplay", () => { clearTimeout(timeout); resolve(); }, { once: true });
      });
      const url = URL.createObjectURL(new Blob(chunks, { type: "video/webm" })); video.src = url; await ready;
      const parameter = document.createElement("div"); parameter.dataset.parameterName = "video_url";
      parameter.innerHTML = '<div data-vp-video-area style="width:600px;height:220px"><div data-native-player></div></div>';
      parameter.firstElementChild.firstElementChild.append(video); f.node.append(parameter);
      f.region = parameter.firstElementChild; f.video = video; f.loads = 0;
      const nativeLoad = video.load.bind(video); video.load = () => { f.loads += 1; nativeLoad(); };
      f.update(f.state);
      const cleanup = f.cleanup; f.cleanup = () => { cleanup(); URL.revokeObjectURL(url); };
      return f;
    };
  }, source);
  const check = async (name, callback) => {
    await callback(); receipt.cases.push({ name, passed: true });
    await page.evaluate(() => { fixtures.splice(0).forEach((fixture) => fixture.cleanup()); });
  };
  await check("legacy-state-without-additive-fields-retains-final-available-and-busy-compatibility", async () => {
    const result = await page.evaluate(() => {
      const legacy = makeState(); delete legacy.draft.final_state; delete legacy.draft.final_visible; delete legacy.draft.final_task_id;
      const ready = view(createFixture(legacy));
      legacy.draft.final_available = false; legacy.draft.busy = true; legacy.draft.final_busy = true;
      return { ready, busy: view(createFixture(legacy)) };
    });
    assert.equal(result.ready.hidden, false); assert.equal(result.ready.disabled, false); assert.equal(result.ready.text, "Draft final");
    assert.equal(result.busy.disabled, true); assert.equal(result.busy.text, "Final 처리 중…");
  });
  await check("only-local-available-Draft-enables-final-while-checking-and-source-pending-do-not", async () => {
    const results = await page.evaluate(async () => {
      const all = ["checking", "source_pending", "available"].map((final_state) => createFixture(makeState(0,
        { final_state, final_available: final_state === "available" })));
      const views = all.map(view);
      const accepted = all.map((f) => widget.hmbSeedanceRequestDraftFinal(f.container)); await flushFrames();
      return { views, accepted, counts: all.map((f) => f.commands.length) };
    });
    assert.match(results.views[0].text, /상태 확인/);
    assert.deepEqual(results.views.map((value) => value.disabled), [true, true, false]);
    assert.deepEqual(results.accepted, [false, false, true]); assert.deepEqual(results.counts, [0, 0, 1]);
  });
  await check("shared-server-reservation-running-unknown-states-never-dispatch-another-final", async () => {
    const results = await page.evaluate(async () => {
      const all = ["reserved", "running", "unknown", "unavailable"].map((final_state) => createFixture(makeState(1,
        { final_state, final_available: false, final_task_id: `job-${"f".repeat(32)}` })));
      const views = all.map(view); const accepted = all.map((f) => widget.hmbSeedanceRequestDraftFinal(f.container));
      await flushFrames(); return { views, accepted, commands: all.flatMap((f) => f.commands) };
    });
    results.views.forEach((value) => { assert.equal(value.hidden, false); assert.equal(value.disabled, true); });
    results.views.slice(0, 2).forEach((value) => assert.equal(value.text, "Final 처리 중…"));
    assert.equal(results.views[2].text, "Final 확인 필요"); assert.deepEqual(results.accepted, [false, false, false, false]);
    assert.deepEqual(results.commands, []);
  });
  await check("completed-consumed-expired-and-nonDraft-projections-hide-final-and-close-programmatic-action", async () => {
    const results = await page.evaluate(async () => {
      const all = ["completed", "consumed", "expired", "not_draft"].map((final_state) => createFixture(makeState(1,
        { final_state, final_visible: false, final_available: false })));
      const views = all.map(view); const accepted = all.map((f) => widget.hmbSeedanceRequestDraftFinal(f.container));
      await flushFrames(); return { views, accepted, commands: all.flatMap((f) => f.commands) };
    });
    results.views.forEach((value) => { assert.equal(value.hidden, true); assert.equal(value.disabled, true); });
    assert.deepEqual(results.accepted, [false, false, false, false]); assert.deepEqual(results.commands, []);
  });
  await check("explicit-hidden-or-checking-contract-cannot-be-bypassed-by-stale-final-available", async () => {
    const results = await page.evaluate(async () => {
      const all = [makeState(1, { final_visible: false }), makeState(1, { final_state: "checking" })].map(createFixture);
      const accepted = all.map((f) => widget.hmbSeedanceRequestDraftFinal(f.container)); await flushFrames();
      return { accepted, views: all.map(view), commands: all.flatMap((f) => f.commands) };
    });
    assert.deepEqual(results.accepted, [false, false]); assert.equal(results.views[0].hidden, true);
    results.views.forEach((value) => assert.equal(value.disabled, true)); assert.deepEqual(results.commands, []);
  });
  await check("same-Draft-server-state-transitions-do-not-write-authored480-or-schedule-actions", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); const id = f.state.draft.job_id, button = f.button(); const states = [];
      for (const final_state of ["checking", "available", "reserved", "running", "unknown", "completed", "consumed", "expired"]) {
        f.update(makeState(1, { final_state, final_available: final_state === "available",
          final_visible: !["completed", "consumed", "expired"].includes(final_state), final_task_id: `job-${"f".repeat(32)}` }));
        states.push({ ...view(f), sameButton: f.button() === button, sameDraft: f.state.draft.job_id === id });
      }
      await flushFrames(); return { states, commands: f.commands, authored: f.authored };
    });
    result.states.forEach((value) => { assert.equal(value.resolution, "480p"); assert.equal(value.action, "Draft 480p"); assert.ok(value.sameButton && value.sameDraft); });
    assert.deepEqual(result.commands, []); assert.deepEqual(result.authored, []);
  });
  await check("queued-local-click-is-cancelled-by-server-reservation-before-dispatch", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.button().click();
      f.update(makeState(1, { final_state: "reserved", final_available: false, final_task_id: `job-${"f".repeat(32)}` }));
      await flushFrames(); return { ...view(f), commands: f.commands, authored: f.authored };
    });
    assert.equal(result.disabled, true); assert.equal(result.text, "Final 처리 중…");
    assert.deepEqual(result.commands, []); assert.deepEqual(result.authored, []);
  });
  await check("child-task-info-never-replaces-source-Draft-command-id-or-causes-duplicate", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(), source = f.state.draft.job_id;
      f.update(makeState(1, { final_task_id: `job-${"f".repeat(32)}` }));
      f.button().click(); f.button().click(); await flushFrames();
      f.update(makeState(1, { final_state: "running", final_available: false, final_task_id: `job-${"e".repeat(32)}` }));
      return { source, commands: f.commands, authored: f.authored };
    });
    assert.equal(result.commands.length, 1); assert.equal(result.commands[0].expected_draft_job_id, result.source);
    assert.equal(result.commands[0].action, "finalize_draft"); assert.deepEqual(result.authored, []);
  });
  await check("pending-Shot-switch-blocks-stale-old-Draft-availability-and-late-action-errors", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.button().click(); await flushFrames();
      const select = f.container.querySelector("select"); select.value = select.options[2].value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      f.update(makeState(1, { final_state: "checking", final_available: false })); const checking = view(f);
      f.update(makeState(1)); const stale = view(f); f.button().click(); await flushFrames();
      f.update(makeState(2)); f.rejects[0](new Error("Old Draft dispatch rejected")); await Promise.resolve();
      return { checking, stale, current: view(f), commands: f.commands, authored: f.authored };
    });
    assert.ok(result.checking.hidden && result.stale.hidden);
    assert.equal(result.current.hidden, false); assert.equal(result.current.disabled, false); assert.equal(result.current.error, "");
    assert.equal(result.commands.length, 1); assert.equal(result.commands[0].expected_draft_job_id, `job-${"2".padStart(32, "0")}`);
    assert.equal(result.authored.length, 1);
  });
  await check("new-Draft-can-become-available-after-prior-Draft-was-consumed", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(makeState(1, { final_state: "consumed", final_visible: false, final_available: false }));
      const before = view(f); const next = makeState(1); next.draft.job_id = `job-${"a".repeat(32)}`;
      f.update(next); const after = view(f); f.button().click(); await flushFrames();
      return { before, after, commands: f.commands, authored: f.authored };
    });
    assert.equal(result.before.hidden, true); assert.equal(result.after.hidden, false); assert.equal(result.after.disabled, false);
    assert.equal(result.commands.length, 1); assert.equal(result.commands[0].expected_draft_job_id, `job-${"a".repeat(32)}`);
    assert.deepEqual(result.authored, []);
  });
  await check("web-Draft-without-native-source-never-arms-a-native-final", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(makeState(0, { job_id: "", final_state: "not_draft", final_visible: false, final_available: false }));
      const accepted = widget.hmbSeedanceRequestDraftFinal(f.container); f.button().click(); await flushFrames();
      return { ...view(f), accepted, commands: f.commands, authored: f.authored };
    });
    assert.equal(result.hidden, true); assert.equal(result.accepted, false); assert.deepEqual(result.commands, []); assert.deepEqual(result.authored, []);
  });
  await check("status-refreshes-retain-playable-preview-node-source-and-media-revision", async () => {
    const result = await page.evaluate(async () => {
      const f = await addPlayablePreview(createFixture()), video = f.video, src = video.src;
      const originalRevision = f.state.generation.media_revision;
      for (let index = 0; index < 90; index += 1) {
        const states = ["checking", "available", "reserved", "running", "unknown", "completed"];
        const final_state = states[index % states.length];
        const next = makeState(1, { final_state, final_available: final_state === "available", final_visible: final_state !== "completed" });
        f.update(next);
      }
      await flushFrames(); return { retained: f.region.querySelector("video") === video, sameSource: video.src === src,
        loads: f.loads, readyState: video.readyState, revision: f.state.generation.media_revision,
        originalRevision, authored: f.authored, commands: f.commands, ...view(f) };
    });
    assert.ok(result.retained && result.sameSource); assert.equal(result.loads, 0); assert.ok(result.readyState >= 3);
    assert.equal(result.revision, result.originalRevision); assert.equal(result.resolution, "480p");
    assert.equal(result.action, "Draft 480p"); assert.deepEqual(result.authored, []); assert.deepEqual(result.commands, []);
  });
  assert.deepEqual(errors, []); assert.equal(receipt.external_requests, 0);
  receipt.passed = true;
} catch (error) {
  receipt.passed = false; receipt.failure = String(error?.stack || error); throw error;
} finally {
  await browser.close();
  const receiptPath = argument("--receipt-path");
  if (receiptPath) { fs.mkdirSync(path.dirname(path.resolve(receiptPath)), { recursive: true }); fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + "\n"); }
  console.log(JSON.stringify({ passed: receipt.passed, cases: receipt.cases.length, external_requests: receipt.external_requests }));
}
