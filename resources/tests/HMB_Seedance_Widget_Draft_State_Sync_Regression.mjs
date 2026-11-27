import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const argument = (name) => { const index = process.argv.indexOf(name); return index < 0 ? "" : process.argv[index + 1] || ""; };
const root = path.resolve(argument("--library-root") || fileURLToPath(new URL("../..", import.meta.url)));
const sourcePath = path.join(root, "widgets/HMBSeedanceGenerationWidget.js");
const source = fs.readFileSync(sourcePath, "utf8");
// Encode a tiny local fixture independently of the widget's mocked RAF queue.
// Static canvas capture can yield an empty WebM on headless Chromium.
const playableVideo = execFileSync(process.env.HMB_COLOR_LUT_TEST_FFMPEG || "ffmpeg", [
  "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
  "color=c=green:s=32x24:r=8:d=0.5", "-an", "-c:v", "libvpx", "-f", "webm", "pipe:1",
], { timeout: 15000, maxBuffer: 1024 * 1024 }).toString("base64");
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
  await page.evaluate(async ({code, playableVideo}) => {
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
      f.quality = () => f.container.querySelector("select[data-hmb-seedance-final-resolution]");
      f.selectQuality = resolution => {
        f.quality().value = resolution;
        f.quality().dispatchEvent(new Event("change", { bubbles: true }));
      };
      f.chooseFinal = (resolution = "1080p") => { f.selectQuality(resolution); f.button().click(); };
      f.cleanup = () => { f.controller.cleanup(); f.bridge.cleanup(); node.remove(); };
      fixtures.push(f); return f;
    };
    window.view = (f) => ({ hidden: !f.button().getClientRects().length, qualityHidden: !f.quality().getClientRects().length, qualityDisabled: f.quality().disabled, quality: f.quality().value, disabled: f.button().disabled,
      options: Array.from(f.quality().options, option => option.value).filter(Boolean),
      text: f.button().textContent, busy: f.button().getAttribute("aria-busy"), title: f.button().title,
      error: f.container.querySelector(".hmb-seedance-shot__status").textContent,
      resolution: f.node.querySelector('[data-parameter-name="resolution"]').value,
      action: f.node.querySelector('[data-parameter-name="draft_action"]').value });
    window.addPlayablePreview = async (f) => {
      const bytes = Uint8Array.from(atob(playableVideo), char => char.charCodeAt(0));
      const video = document.createElement("video"); video.muted = true; video.width = 600; video.height = 220;
      video.dataset.rawVideoValue = "https://fixture.invalid/retained-original.mov";
      const ready = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Isolated video did not become playable")), 3000);
        video.addEventListener("canplay", () => { clearTimeout(timeout); resolve(); }, { once: true });
      });
      const url = URL.createObjectURL(new Blob([bytes], { type: "video/webm" })); video.src = url; await ready;
      const parameter = document.createElement("div"); parameter.dataset.parameterName = "video_url";
      parameter.innerHTML = '<div data-vp-video-area style="width:600px;height:220px"><div data-native-player></div></div>';
      parameter.firstElementChild.firstElementChild.append(video); f.node.append(parameter);
      f.region = parameter.firstElementChild; f.video = video; f.loads = 0;
      const nativeLoad = video.load.bind(video); video.load = () => { f.loads += 1; nativeLoad(); };
      f.update(f.state);
      const cleanup = f.cleanup; f.cleanup = () => { cleanup(); URL.revokeObjectURL(url); };
      return f;
    };
  }, {code: source, playableVideo});
  const check = async (name, callback) => {
    await callback(); receipt.cases.push({ name, passed: true });
    await page.evaluate(() => { fixtures.splice(0).forEach((fixture) => fixture.cleanup()); });
  };
  await check("render ownership locks only matching shot fields and completion requires current proof", async () => {
    const states = await page.evaluate(async () => {
      const one = makeState(1), two = makeState(2);
      const locks = [{channel_uuid: one.shot.channel_uuid, shot_uuid: one.shot.shot_uuid}];
      const locked = {...one, shot_edit_locks: locks, shot_edit_fields: ["resolution", "draft_action"]};
      const a = createFixture(locked), b = createFixture({...two, shot_edit_locks: locks});
      const observe = fixture => [
        fixture.container.querySelector(".hmb-seedance-shot__progress").textContent,
        fixture.container.querySelector(".hmb-seedance-shot__select").disabled,
        fixture.node.querySelector('[data-parameter-name="resolution"]').inert,
        fixture.container.querySelector("[data-seedance-shot-number]").dataset.hmbShotCheck,
      ];
      const initial = [observe(a), observe(b)];
      const replacement = document.createElement("input");
      replacement.dataset.parameterName = "resolution";
      a.node.querySelector('[data-parameter-name="resolution"]').replaceWith(replacement);
      await Promise.resolve();
      const replaced = replacement.inert;
      a.update({...one, draft: {...one.draft, render_completed:true}});
      const complete = observe(a);
      a.update({...one, draft: {...one.draft, run_locked:true}});
      return {initial, replaced, complete, verifying:observe(a)};
    });
    assert.deepEqual(states, {initial:[["로동중... 수정불가",true,true,"false"],["",false,false,"false"]],replaced:true,
      complete:["",false,false,"true"],verifying:["",false,false,"false"]});
  });
  await check("legacy-state-without-additive-fields-retains-final-available-and-busy-compatibility", async () => {
    const result = await page.evaluate(() => {
      const legacy = makeState(); delete legacy.draft.final_state; delete legacy.draft.final_visible; delete legacy.draft.final_task_id;
      const ready = view(createFixture(legacy));
      legacy.draft.final_available = false; legacy.draft.busy = true; legacy.draft.final_busy = true;
      return { ready, busy: view(createFixture(legacy)) };
    });
    assert.equal(result.ready.hidden, false); assert.equal(result.ready.disabled, false); assert.equal(result.ready.text, "생성");
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
    assert.deepEqual(results.views.map((value) => value.qualityHidden), [true, true, false]);
    assert.deepEqual(results.views.map((value) => value.hidden), [true, true, false]);
    assert.deepEqual(results.views.map((value) => value.disabled), [true, true, false]);
    assert.deepEqual(results.accepted, [false, false, true]); assert.deepEqual(results.counts, [0, 0, 1]);
  });
  for (const shot of [0, 1]) {
    await check(`completed-Draft-480p-status-arrival-unblocks-same-control-after-reopen-${shot ? "shot" : "only"}`, async () => {
      await page.evaluate(shot => {
        const f = createFixture(makeState(shot, { source_completed:true, final_state:"checking",
          final_available:false, final_visible:true }));
        window.originalFinalizeControl = f.button();
      }, shot);
      const button = page.locator("[data-hmb-seedance-finalize-draft]");
      const select = page.locator("select[data-hmb-seedance-final-resolution]");
      assert.equal(await button.isVisible(), true);
      assert.equal(await button.textContent(), "Final 상태 확인 중…");
      assert.equal(await button.isDisabled(), true);
      assert.equal(await select.inputValue(), "1080p");
      await page.evaluate(shot => {
        const f = fixtures[0];
        f.update(makeState(shot, { source_completed:true, final_state:"available", final_available:true,
          finals_by_resolution:{"1080p":"available", "4k":"available"} }));
      }, shot);
      assert.equal(await page.evaluate(() => fixtures[0].button() === window.originalFinalizeControl), true);
      assert.equal(await button.isEnabled(), true);
      assert.equal(await button.textContent(), "생성");
      await select.selectOption("4k");
      assert.equal(await page.evaluate(() => fixtures[0].commands.length), 0, "Reading or selecting does not create a render");
      await button.dblclick();
      const calls = await page.evaluate(async () => { await flushFrames(); return fixtures[0].commands; });
      assert.deepEqual(calls.map(c => [c.action,c.final_resolution]), [["finalize_draft","4k"]]);
    });
  }
  await check("shared-server-reservation-running-unknown-states-never-dispatch-another-final", async () => {
    const results = await page.evaluate(async () => {
      const all = ["reserved", "running", "unknown", "unavailable"].map((final_state) => createFixture(makeState(1,
        { final_state, final_available: false, final_task_id: `job-${"f".repeat(32)}` })));
      const views = all.map(view); const accepted = all.map((f) => widget.hmbSeedanceRequestDraftFinal(f.container));
      await flushFrames(); return { views, accepted, commands: all.flatMap((f) => f.commands) };
    });
    results.views.forEach((value) => assert.equal(value.disabled, true));
    for (const v of results.views.slice(0, 2)) assert.equal(v.hidden, false);
    results.views.slice(0, 2).forEach((value) => assert.equal(value.text, "Final 처리 중…"));
    assert.equal(results.views[2].text, "Final 확인 필요"); assert.deepEqual(results.accepted, [false, false, false, false]);
    assert.deepEqual(results.commands, []);
  });
  await check("deadline-arriving-before-Final-dispatch-preserves-an-existing-child", async () => {
    const result = await page.evaluate(async () => {
      const source = makeState(1, { source_completed: true });
      const f = createFixture(source);
      const armed = !f.button().disabled;
      f.button().click();
      f.update(makeState(1, { source_completed: true, final_state: "expired",
        final_available: false, final_visible: false }));
      await flushFrames();
      const expired = view(f);
      const child = "job-" + "c".repeat(32);
      f.update(makeState(1, { source_completed: true, final_state: "running",
        final_available: false, final_visible: true, final_task_id: child }));
      f.button().click();
      await flushFrames();
      return { armed, expired, running: view(f), id: widget.hmbSeedanceDraftState(f.state.draft).final_task_id,
        child, commands: f.commands };
    });
    assert.equal(result.armed, true);
    assert.equal(result.expired.hidden && result.expired.disabled, true);
    assert.equal(result.running.hidden, false);
    assert.equal(result.running.disabled, true);
    assert.equal(result.running.text, "Final 처리 중…");
    assert.equal(result.id, result.child);
    assert.deepEqual(result.commands, []);
  });
  for (const status of ["unknown", "unavailable"]) {
    await check(`retry-${status}-checks-only-the-completed-Draft-without-generating`, async () => {
      const job = await page.evaluate(status => {
        const f = createFixture(makeState(1, {source_completed:true, final_available:false, final_state:status}));
        return f.state.draft.job_id;
      }, status);
      const retry = page.locator("[data-hmb-seedance-retry-final]");
      assert.equal(await retry.isVisible(), true);
      assert.equal(await retry.textContent(), "상태 다시 조회");
      assert.equal(await page.locator("[data-hmb-seedance-finalize-draft]").isVisible(), false);
      await retry.click();
      const commands = await page.evaluate(async () => {await flushFrames(); return fixtures[0].commands;});
      assert.deepEqual(commands.map(c=>[c.action,c.expected_draft_job_id]), [["refresh_draft_final_status",job]]);
      assert.equal(Object.hasOwn(commands[0],"final_resolution"),false);
      await page.evaluate(() => fixtures[0].update(makeState(1,{source_completed:true,final_state:"available",
        finals_by_resolution:{"1080p":"available","4k":"available"}})));
      assert.equal(await retry.isVisible(), false);
      assert.equal(await page.locator("[data-hmb-seedance-finalize-draft]").isEnabled(), true);
      assert.equal(await page.evaluate(()=>fixtures[0].commands.length),1);
    });
  }
  await check("legacy-receipt-shows-only-the-unconfirmed-alternate-for-a-known-completed-target", async () => {
    const results = await page.evaluate(async () => {
      const all = ["completed", "consumed", "expired", "not_draft"].map((final_state) => createFixture(makeState(1,
        { final_state, final_visible: false, final_available: false, source_completed: final_state !== "not_draft",
          final_task_id: ["completed", "consumed"].includes(final_state) ? "job-" + "c".repeat(32) : "",
          final_resolution: final_state === "completed" ? "4k" : "" })));
      const views = all.map(view); const accepted = all.map((f) => widget.hmbSeedanceRequestDraftFinal(f.container));
      await flushFrames(); return { views, accepted, commands: all.flatMap((f) => f.commands) };
    });
    assert.ok(results.views.every(value => value.disabled));
    assert.equal(results.views[0].qualityDisabled, false);
    assert.deepEqual(results.views.map(value=>value.hidden),[false,true,true,true]);
    assert.deepEqual(results.views.map(value=>value.qualityHidden),[false,true,true,true]);
    assert.deepEqual(results.views[0].options, ["1080p"]);
    assert.equal(results.views[0].quality, "1080p");
    assert.deepEqual(results.views[1].options, [], "An unknown legacy receipt cannot establish a remaining quality.");
    assert.deepEqual(results.accepted, [false, false, false, false]); assert.deepEqual(results.commands, []);
  });
  for (const [first, second] of [["1080p", "4k"], ["4k", "1080p"]]) {
    await check(`one-bound-Draft-can-Final-${first}-then-${second}-without-redrafting`, async () => {
      const initial = await page.evaluate(() => {
        const f = createFixture(makeState(1, { source_completed: true,
          finals_by_resolution: { "1080p": "available", "4k": "available" } }));
        return { source: f.state.draft.job_id, options: view(f).options };
      });
      const { source } = initial;
      assert.deepEqual(initial.options, ["1080p", "4k"]);
      const select = page.locator("select[data-hmb-seedance-final-resolution]");
      const generate = page.locator("[data-hmb-seedance-finalize-draft]");
      const selectTarget = async (target) => {
        await select.focus(); await page.keyboard.press(target === "4k" ? "End" : "Home");
        assert.equal(await select.inputValue(), target);
      };
      const clickTwice = async () => {
        const box = await generate.boundingBox();
        await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2);
        await page.evaluate(() => flushFrames());
      };
      await selectTarget(first);
      assert.equal(await page.evaluate(() => fixtures[0].commands.length), 0);
      await clickTwice();
      const running = await page.evaluate(([first, second]) => {
        const f = fixtures[0];
        f.update(makeState(1, { source_completed: true, final_busy: true, busy: true, final_state: "running",
          final_available: false, final_resolution: first, finals_by_resolution: { [first]: "running", [second]: "available" } }));
        return { during: view(f), crossed: widget.hmbSeedanceRequestDraftFinal(f.container, second), count: f.commands.length };
      }, [first, second]);
      assert.equal(running.count, 1); assert.equal(running.crossed, false); assert.equal(running.during.disabled, true);
      const firstComplete = await page.evaluate(([first, second]) => {
        const f = fixtures[0];
        f.update(makeState(1, { source_completed: true, final_state: "completed", final_visible: true, final_available: true,
          final_resolution: first, final_task_id: "job-" + "b".repeat(32), finals_by_resolution: { [first]: "completed", [second]: "available" } }));
        return { display: view(f), repeated: widget.hmbSeedanceRequestDraftFinal(f.container, first) };
      }, [first, second]);
      assert.equal(firstComplete.repeated, false); assert.equal(firstComplete.display.qualityDisabled, false);
      assert.equal(firstComplete.display.quality, second);
      assert.deepEqual(firstComplete.display.options, [second], "The completed target must be removed from the select DOM.");
      assert.equal(await page.evaluate(() => fixtures[0].commands.length), 1);
      assert.equal(await generate.isEnabled(), true); assert.equal(await generate.textContent(), "생성");
      await clickTwice();
      const sameReceiptEcho = await page.evaluate(async (target) => {
        const f = fixtures[0]; f.update(structuredClone(f.state));
        f.button().click(); const accepted = widget.hmbSeedanceRequestDraftFinal(f.container, target);
        await flushFrames(); return { accepted, count: f.commands.length };
      }, second);
      assert.deepEqual(sameReceiptEcho, { accepted: false, count: 2 });
      const done = await page.evaluate(([first, second]) => {
        const f = fixtures[0];
        f.update(makeState(1, { source_completed: true, final_state: "completed", final_visible: true, final_available: false,
          final_resolution: second, final_task_id: "job-" + "c".repeat(32), finals_by_resolution: { [first]: "completed", [second]: "completed" } }));
        const rejected = [first, second].map(target => widget.hmbSeedanceRequestDraftFinal(f.container, target));
        return { display: view(f), rejected, commands: f.commands, authored: f.authored };
      }, [first, second]);
      assert.equal(done.display.disabled, true); assert.deepEqual(done.rejected, [false, false]);
      assert.deepEqual(done.display.options, []);
      assert.ok(done.display.hidden && done.display.qualityHidden, "Hide the pair once all results are claimed.");
      assert.deepEqual(done.commands.map(command => [command.action, command.expected_draft_job_id, command.final_resolution]),
        [["finalize_draft", source, first], ["finalize_draft", source, second]]);
      assert.notEqual(done.commands[0].action_id, done.commands[1].action_id);
      (receipt.remaining_resolutions ??= []).push({ first, second, initial: initial.options,
        after_first: firstComplete.display.options, after_both: done.display.options,
        physical_double_clicks: 2, dispatched: done.commands.map(c => c.final_resolution) });
      assert.deepEqual(done.authored, []); assert.equal(done.display.action, "Draft 480p"); assert.equal(done.display.resolution, "480p");
    });
  }
  await check("a-completion-between-physical-clicks-cannot-submit-the-newly-selected-quality", async () => {
    await page.evaluate(() => {
      const f = createFixture(makeState(1, { source_completed: true,
        finals_by_resolution: { "1080p": "available", "4k": "available" } }));
      f.clickDetails = [];
      f.node.addEventListener("click", e => {
        if (e.target === f.button() && e.isTrusted) f.clickDetails.push(e.detail);
      }, true);
    });
    const generate = page.locator("[data-hmb-seedance-finalize-draft]");
    const box = await generate.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down({ clickCount: 1 }); await page.mouse.up({ clickCount: 1 });
    const remaining = await page.evaluate(async () => {
      await flushFrames();
      const f = fixtures[0];
      f.update(makeState(1, { source_completed: true, final_state: "completed", final_resolution: "1080p",
        final_task_id: "job-" + "b".repeat(32), finals_by_resolution: { "1080p": "completed", "4k": "available" } }));
      return view(f);
    });
    assert.deepEqual(remaining.options, ["4k"]); assert.equal(remaining.disabled, false);
    await page.mouse.down({ clickCount: 2 }); await page.mouse.up({ clickCount: 2 });
    const clicks = await page.evaluate(async () => {
      await flushFrames();
      return { qualities: fixtures[0].commands.map(c => c.final_resolution), details: fixtures[0].clickDetails };
    });
    assert.deepEqual(clicks, { qualities: ["1080p"], details: [1, 2] });
    await generate.click();
    const approved = await page.evaluate(async () => { await flushFrames(); return fixtures[0].commands.map(c => c.final_resolution); });
    assert.deepEqual(approved, ["1080p", "4k"]);
  });
  await check("legacy-single-completed-receipt-keeps-selector-but-unproven-other-quality-cannot-dispatch", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(makeState(1, { source_completed: true, final_state: "completed", final_visible: false,
        final_available: false, final_resolution: "1080p", final_task_id: "job-" + "d".repeat(32) }));
      const initial = view(f); f.selectQuality("4k"); const chosen = view(f);
      f.button().click(); const accepted = widget.hmbSeedanceRequestDraftFinal(f.container, "4k");
      await flushFrames(); return { initial, chosen, accepted, count: f.commands.length };
    });
    assert.equal(result.initial.qualityDisabled, false); assert.equal(result.chosen.quality, "4k");
    assert.deepEqual(result.initial.options, ["4k"]);
    assert.equal(result.chosen.disabled, true); assert.equal(result.accepted, false); assert.equal(result.count, 0);
  });
  await check("legacy-child-with-late-resolution-reconciles-by-child-id-and-keeps-only-the-remaining-target", async () => {
    const result = await page.evaluate(async () => {
      const receipt = makeState(1, { source_completed: true, final_state: "completed", final_visible: false,
        final_available: false, final_task_id: "job-" + "d".repeat(32) });
      const f = createFixture(receipt);
      const before = view(f);
      const known = structuredClone(receipt); known.draft.final_resolution = "1080p";
      f.update(known); const after = view(f);
      f.update(receipt);
      f.button().click(); await flushFrames();
      return { before, after, replay: view(f), commands: f.commands };
    });
    assert.deepEqual(result.before.options, []);
    for (const item of [result.after, result.replay]) { assert.deepEqual(item.options, ["4k"]); assert.ok(item.disabled); }
    assert.deepEqual(result.commands, []);
  });
  await check("stale-availability-cannot-restore-a-completed-target-after-switching-Shots", async () => {
    const result = await page.evaluate(async () => {
      const fresh = shot => makeState(shot, { source_completed: true,
        finals_by_resolution: { "1080p": "available", "4k": "available" } });
      const f = createFixture(fresh(1));
      const completed = makeState(1, { source_completed: true, final_state: "completed", final_resolution: "1080p",
        final_task_id: "job-" + "b".repeat(32), finals_by_resolution: { "1080p": "completed", "4k": "available" } });
      f.update(completed); const correct = view(f);
      f.update(fresh(1)); const oldEcho = view(f);
      const old = widget.hmbSeedanceRequestDraftFinal(f.container, "1080p");
      f.update(fresh(2)); const otherShot = view(f);
      f.update(fresh(1)); const returned = view(f);
      const returnedAttempt = widget.hmbSeedanceRequestDraftFinal(f.container, "1080p");
      await flushFrames();
      const nextDraft = fresh(1);
      nextDraft.draft.job_id = "job-" + "d".repeat(32);
      f.update(nextDraft);
      return { correct, oldEcho, old, otherShot, returned, returnedAttempt, newSource: view(f),
        authored: f.authored, commands: f.commands };
    });
    for (const state of [result.correct, result.oldEcho, result.returned]) assert.deepEqual(state.options, ["4k"]);
    for (const state of [result.otherShot, result.newSource]) assert.deepEqual(state.options, ["1080p", "4k"]);
    assert.equal(result.old, false); assert.equal(result.returnedAttempt, false);
    assert.deepEqual(result.commands, []); assert.deepEqual(result.authored, []);
  });
  await check("explicit-hidden-or-checking-contract-cannot-be-bypassed-by-stale-final-available", async () => {
    const results = await page.evaluate(async () => {
      const all = [makeState(1, { final_visible: false }), makeState(1, { final_state: "checking" }), makeState(1, { source_completed: false })].map(createFixture);
      const accepted = all.map((f) => widget.hmbSeedanceRequestDraftFinal(f.container)); await flushFrames();
      return { accepted, views: all.map(view), commands: all.flatMap((f) => f.commands) };
    });
    assert.deepEqual(results.accepted, [false, false, false]); assert.ok(results.views.every(value=>value.hidden && value.qualityHidden));
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
      const f = createFixture(); f.chooseFinal();
      f.update(makeState(1, { final_state: "reserved", final_available: false, final_task_id: `job-${"f".repeat(32)}` }));
      await flushFrames(); return { ...view(f), commands: f.commands, authored: f.authored };
    });
    assert.equal(result.disabled, true); assert.equal(result.text, "Final 처리 중…");
    assert.deepEqual(result.commands, []); assert.deepEqual(result.authored, []);
  });
  await check("scope-specific-reservation-before-paint-blocks-the-selected-quality-even-if-the-other-is-available", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(makeState(1, { source_completed: true, finals_by_resolution: { "1080p": "available", "4k": "available" } }));
      f.chooseFinal("4k");
      f.update(makeState(1, { source_completed: true, final_available: true, final_state: "available",
        finals_by_resolution: { "1080p": "available", "4k": "reserved" } }));
      await flushFrames();
      return { accepted: widget.hmbSeedanceRequestDraftFinal(f.container, "4k"), count: f.commands.length, authored: f.authored };
    });
    assert.equal(result.accepted, false); assert.equal(result.count, 0); assert.deepEqual(result.authored, []);
  });
  await check("absent-or-unrecognized-target-authority-cannot-inherit-another-resolutions-availability", async () => {
    const results = await page.evaluate(async () => {
      const states = [{ "1080p": "available" }, { "1080p": "available", "4k": "unrecognized" }];
      const fixtures = states.map(finals_by_resolution => createFixture(makeState(1, { source_completed: true, finals_by_resolution })));
      const accepted = fixtures.map(f => widget.hmbSeedanceRequestDraftFinal(f.container, "4k"));
      await flushFrames();
      return { accepted, commands: fixtures.flatMap(f => f.commands) };
    });
    assert.deepEqual(results.accepted, [false, false]); assert.deepEqual(results.commands, []);
  });
  await check("expired-sibling-does-not-disable-an-explicitly-available-resolution", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(makeState(1, { source_completed: true, finals_by_resolution: { "1080p": "expired", "4k": "available" } }));
      const options = view(f).options;
      const expired = widget.hmbSeedanceRequestDraftFinal(f.container, "1080p"); f.chooseFinal("4k");
      await flushFrames(); return { options, expired, sent: f.commands.map(c => c.final_resolution) };
    });
    assert.deepEqual(result, { options: ["4k"], expired: false, sent: ["4k"] });
  });
  await check("child-task-info-never-replaces-source-Draft-command-id-or-causes-duplicate", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(), source = f.state.draft.job_id;
      f.update(makeState(1, { final_task_id: `job-${"f".repeat(32)}` }));
      f.chooseFinal(); f.button().click(); await flushFrames();
      f.update(makeState(1, { final_state: "running", final_available: false, final_task_id: `job-${"e".repeat(32)}` }));
      return { source, commands: f.commands, authored: f.authored };
    });
    assert.equal(result.commands.length, 1); assert.equal(result.commands[0].expected_draft_job_id, result.source);
    assert.equal(result.commands[0].action, "finalize_draft"); assert.deepEqual(result.authored, []);
  });
  await check("pending-Shot-switch-blocks-stale-old-Draft-availability-and-late-action-errors", async () => {
    const result = await page.evaluate(async () => {
      const f = createFixture(); f.chooseFinal(); await flushFrames();
      const select = f.container.querySelector(".hmb-seedance-shot__select"); select.value = select.options[2].value;
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
      f.update(next); const after = view(f); f.chooseFinal(); await flushFrames();
      return { before, after, commands: f.commands, authored: f.authored };
    });
    assert.equal(result.before.disabled, true);
    assert.ok(result.before.hidden && result.before.qualityHidden);
    assert.deepEqual(result.before.options, []);
    assert.equal(result.after.hidden, false); assert.equal(result.after.disabled, false);
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
