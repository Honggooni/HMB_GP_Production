/** Backend-authoritative Only/Shot selector in an isolated real browser.
 * Host snapshots, commands and videos are fixtures; no Griptape user graph,
 * provider, Broker, local media or installed files are accessed.
 */
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const argument = name => { const i = process.argv.indexOf(name); return i < 0 ? "" : process.argv[i + 1] || ""; };
const root = path.resolve(argument("--library-root") || fileURLToPath(new URL("../..", import.meta.url)));
const widgetPath = path.join(root, "widgets/HMBSeedanceGenerationWidget.js");
const source = fs.readFileSync(widgetPath, "utf8");
const hash = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const originalCss = "16fb5e7c19e4e1ee1b0dcdd31f827e743ace6cd1c4c89449cd3a8910a4129c34";
const css = source.match(/function render\(state\) \{[\s\S]*?<style>([\s\S]*?)<\/style>/)?.[1];
// The opt-in host header adds only its own slots and excludes host controls
// from generic styling. All legacy header/body/player CSS remains byte-identical.
const legacyCss = css.replace(/^[ \t]*\/\* HMB_NATIVE_HEADER_SLOTS_BEGIN \*\/[\s\S]*?\/\* HMB_NATIVE_HEADER_SLOTS_END \*\/\r?\n/m, "")
  .replaceAll(":not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *))", "");
assert.equal(hash(legacyCss), originalCss, "Native header integration must preserve existing layout, colours and player CSS.");
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = require(path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")); }
const browser = await playwright.chromium.launch({ executablePath: process.env.HMB_SEEDANCE_TEST_BROWSER || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
const report = { schema: "hmb-seedance-execution-mode-widget/v1", passed: false,
  widget_sha256: hash(source), scope: "Production widget in isolated Chrome; synthetic host snapshots and native sibling DOM.",
  cases: [], external_requests: 0, live_graph_calls: 0, paid_calls: 0, css_sha256: originalCss };
try {
  const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => { report.external_requests++; return route.abort(); });
  await page.setContent('<!doctype html><meta charset="utf-8"><style>body{background:#080c14;color:#fff}.react-flow__node{width:800px;margin:10px}[hidden]{display:none!important}</style><main></main>');
  await page.evaluate(async code => {
    window.widget = await import(`data:text/javascript;base64,${btoa(unescape(encodeURIComponent(code)))}`);
    window.clone = value => JSON.parse(JSON.stringify(value));
    window.ids = [1,2,3,4,5,6,7,8,9].map(n => `10000000-0000-4000-8000-${String(n).padStart(12,"0")}`);
    window.instanceA = "a".repeat(32); window.instanceB = "b".repeat(32);
    window.catalog = { schema: "hmb-shot-routing-catalog", version: 1, publisher_instance_uuid: ids[0], channel_uuid: ids[1],
      generation: 1, metadata_sha256: "a".repeat(64), shots: [1,2,3,4,5].map(n => ({ shot_uuid: ids[n+1], number: n, name: `Fixture ${n}`, revision: 1 })) };
    window.identity = n => n ? { channel_uuid: ids[1], shot_uuid: ids[n+1], number: n, name: `Fixture ${n}` } : { channel_uuid: "", shot_uuid: "", number: 1, name: "Only" };
    window.state = (mode = "shot", n = 1, revision = 1, stateRevision = 1, changes = {}) => ({
      schema: "hmb-seedance-shot-ui", schema_version: 2, shot_catalog: clone(catalog), shot: identity(n),
      execution_mode: mode, requested_mode: mode === "waiting" ? "shot" : mode,
      execution_mode_revision: revision, execution_mode_state_revision: stateRevision, execution_mode_instance: instanceA,
      pending_shot: identity(n), generation: { schema: "hmb-seedance-generation-preview", version: 1,
        phase: "succeeded", job_id: "job-" + "3".repeat(32), media_revision: 3, has_existing_video: true },
      draft: { visible: true, action: "Draft 480p", final_available: true, final_visible: true,
        preview_available: true, job_id: "job-" + "4".repeat(32), effective_resolution: "480p", busy: false }, ...changes,
    });
    window.shotKey = n => n ? `${ids[1]}\u001f${ids[n+1]}` : "__hmb_shot_only__";
    window.makeFixture = value => {
      const node = document.createElement("div"); node.className = "react-flow__node";
      node.innerHTML = '<div data-header></div><div data-parameter-name="only_project"><label>Project (Only)</label><select data-native-project><option>까투리8</option></select></div><input data-resolution value="480p"><div data-parameter-name="video_url"><div data-vp-video-area style="width:700px;height:180px"><video controls></video></div></div>';
      document.querySelector("main").append(node);
      const f = { node, header: node.querySelector("[data-header]"), video: node.querySelector("video"), writes: [], rejects: [], loads: 0 };
      f.video.load = () => { f.loads++; };
      f.project = node.querySelector("[data-native-project]"); f.resolution = node.querySelector("[data-resolution]");
      f.props = value => ({ value, onChange(next) { f.writes.push(clone(next)); return new Promise((_, reject) => f.rejects.push(reject)); } });
      f.controller = widget.default(f.header, f.props(value));
      f.initialSelector = f.header.querySelector("select");
      f.update = value => f.controller.update(f.props(value));
      f.view = () => {
        const select = f.header.querySelector("select"), current = widget.hmbSeedanceShotState(f.header.__hmbSeedanceLatestProps);
        return { value: select.value, label: select.selectedOptions[0]?.textContent, badge: f.header.querySelector("[data-seedance-shot-number]").textContent,
          sameSelector: select === f.initialSelector, colour: f.header.querySelector(".hmb-seedance-shot").style.getPropertyValue("--shot-accent"),
          mode: current.execution_mode, intent: current.requested_mode, revision: current.execution_mode_revision,
          stateRevision: current.execution_mode_state_revision, instance: current.execution_mode_instance,
          job: current.generation.job_id, mediaRevision: current.generation.media_revision,
          pending: Boolean(f.header.__hmbSeedancePendingShot), writes: f.writes.length, loads: f.loads,
          projectUnchanged: f.node.querySelector("[data-native-project]") === f.project && f.project.value === "까투리8",
          videoUnchanged: f.node.querySelector("video") === f.video && !f.video.getAttribute("src"),
          resolution: f.resolution.value };
      };
      f.choose = n => { const select = f.header.querySelector("select"); select.value = shotKey(n); select.dispatchEvent(new Event("change", { bubbles: true })); };
      f.cleanup = () => { f.controller.cleanup(); node.remove(); };
      return f;
    };
  }, source);

  // Missing catalog is a waiting Shot, never independent Only. Old hosts keep
  // their previous shape/selector semantics, including their Only fallback.
  let result = await page.evaluate(() => {
    const waiting = widget.hmbSeedanceShotState({ value: state("shot", 4, 7, 10, { shot_catalog: {} }) });
    const only = widget.hmbSeedanceShotState({ value: state("only", 4, 7, 10) });
    const auto = widget.hmbSeedanceShotState({ value: state("auto", 0, 0, 1) });
    const legacy = clone(state("shot", 4));
    for (const key of ["execution_mode", "requested_mode", "execution_mode_revision", "execution_mode_state_revision", "execution_mode_instance", "pending_shot"]) delete legacy[key];
    legacy.shot_catalog = {};
    return { waitingUuid: waiting.shot.shot_uuid, waitingKey: widget.hmbSeedanceShotOptions(waiting)[0],
      waitingColour: widget.hmbSeedanceShotAccent(waiting), onlyUuid: only.shot.shot_uuid,
      autoLabel: widget.hmbSeedanceShotOptions(auto)[0].name, legacy: widget.hmbSeedanceShotState({value: legacy}) };
  });
  assert.equal(result.waitingUuid, "10000000-0000-4000-8000-000000000006");
  assert.equal(result.waitingKey.waiting, true); assert.equal(result.waitingKey.name, "샷 연결 대기");
  assert.equal(result.waitingColour, "#8B5CF6"); assert.equal(result.onlyUuid, "");
  assert.equal(result.autoLabel, "선택 대기"); assert.equal(result.legacy.shot.name, "Only");
  assert.equal(Object.hasOwn(result.legacy, "execution_mode"), false);
  report.cases.push("modern_waiting_is_not_only_and_legacy_shape_preserved");

  await page.evaluate(() => { window.f = makeFixture(state("shot", 4, 7, 10)); f.choose(0); });
  result = await page.evaluate(() => ({ view: f.view(), write: f.writes[0] }));
  assert.equal(result.view.label, "Only · 적용 중"); assert.equal(result.view.badge, "대기");
  assert.equal(result.view.mode, "shot"); assert.equal(result.view.pending, true);
  assert.deepEqual(result.write.selection_request, { schema: "hmb-seedance-mode-selection", version: 1,
    mode: "only", expected_revision: 7, expected_instance: "a".repeat(32) });
  assert.equal(result.write.shot.shot_uuid, ""); assert.equal(result.write.generation.job_id, result.view.job);
  // Neither old authoritative echoes nor the optimistic request echo ACK the
  // mode. Only a newer backend revision does, then late promise failure is inert.
  await page.evaluate(() => {
    f.update(state("shot", 4, 7, 10)); f.update(f.writes[0]);
    f.update(state("only", 0, 8, 11)); f.rejects[0](new Error("late rejection"));
  });
  await page.waitForTimeout(0);
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "Only"); assert.equal(result.badge, "Only"); assert.equal(result.revision, 8); assert.equal(result.pending, false);
  await page.evaluate(() => {
    f.update(state("shot", 4, 7, 99)); // older intent despite larger state revision
    f.update(state("shot", 4, 8, 12)); // same revision, foreign intent
    const legacy = clone(state("shot", 4)); delete legacy.execution_mode; f.update(legacy);
    for (let i=0;i<100;i++) f.update(state("only", 0, 8, 11));
  });
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "Only"); assert.equal(result.revision, 8); assert.equal(result.stateRevision, 11); assert.equal(result.loads, 0);
  report.cases.push("explicit_only_requires_new_backend_ack_and_rejects_late_echo_or_promise");

  // Re-selecting Only is still an explicit user intent with its own revision.
  await page.evaluate(() => f.choose(0));
  result = await page.evaluate(() => ({ view: f.view(), write: f.writes.at(-1) }));
  assert.equal(result.view.label, "Only · 적용 중"); assert.equal(result.write.selection_request.expected_revision, 8);
  await page.evaluate(() => f.update(state("only", 0, 9, 12)));
  assert.equal((await page.evaluate(() => f.view())).label, "Only");
  report.cases.push("same_only_reselection_requires_incremented_intent_revision");

  // Valid explicit Shot return, temporary publisher absence, same UUID restore,
  // and wrong identity/channel rejection at a fixed intent revision.
  await page.evaluate(() => { f.choose(4); f.update(state("shot", 4, 10, 13)); });
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "04 · Fixture 4"); assert.equal(result.badge, "04");
  await page.evaluate(() => f.update(state("waiting", 4, 10, 14, { shot_catalog: {} })));
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "샷 연결 대기"); assert.equal(result.badge, "대기"); assert.equal(result.colour, "#8B5CF6");
  await page.evaluate(() => {
    f.update(state("shot", 4, 10, 13)); // pre-disconnect stale state
    f.update(state("shot", 3, 10, 15)); // same intent revision, different Shot
    const otherChannel = state("waiting", 4, 10, 15); otherChannel.pending_shot.channel_uuid = ids[8]; f.update(otherChannel);
  });
  assert.equal((await page.evaluate(() => f.view())).label, "샷 연결 대기");
  await page.evaluate(() => f.update(state("shot", 4, 10, 15)));
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "04 · Fixture 4"); assert.equal(result.sameSelector, true);
  report.cases.push("shot_waiting_same_uuid_restore_and_wrong_uuid_channel_rejection");

  // All five palette positions keep their native siblings and authored values.
  await page.evaluate(() => {
    for (let n=1;n<=5;n++) { f.choose(n); f.update(state("shot",n,10+n,15+n)); }
  });
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "05 · Fixture 5"); assert.equal(result.projectUnchanged, true);
  assert.equal(result.videoUnchanged, true); assert.equal(result.resolution, "480p"); assert.equal(result.loads, 0);
  report.cases.push("five_shot_selection_keeps_native_video_project_and_480p_properties");

  // A process/node instance reset may start lower counters. It clears pending
  // client ownership without accepting an old instance that arrives afterwards.
  await page.evaluate(() => { f.choose(0); f.update(state("shot",2,15,1,{execution_mode_instance:instanceB})); });
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "02 · Fixture 2"); assert.equal(result.pending, false); assert.equal(result.instance,"b".repeat(32));
  await page.evaluate(() => {
    f.rejects.at(-1)(new Error("retired instance rejection"));
    f.update(state("only",0,999,999));
  });
  await page.waitForTimeout(0);
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "02 · Fixture 2"); assert.equal(result.job,"job-"+"3".repeat(32)); assert.equal(result.mediaRevision,3);
  report.cases.push("new_instance_rebases_but_retired_instance_and_transport_rejection_do_not");

  // Cleanup must invalidate every late promise and revision baseline. A new
  // node using this container can legitimately have the original instance ID.
  await page.evaluate(() => {
    f.choose(0); const reject = f.rejects.at(-1); f.controller.cleanup();
    f.controller = widget.default(f.header,f.props(state("only",0,0,1)));
    f.initialSelector = f.header.querySelector("select"); reject(new Error("deleted node rejection"));
  });
  await page.waitForTimeout(0);
  result = await page.evaluate(() => f.view());
  assert.equal(result.label, "Only"); assert.equal(result.revision,0); assert.equal(result.pending,false);
  assert.equal(result.projectUnchanged,true); assert.equal(result.videoUnchanged,true);
  await page.evaluate(() => f.cleanup());
  report.cases.push("cleanup_recreate_has_fresh_authority_and_rejects_old_pending_promise");

  // Five rapid choices publish only the first request and then the final choice
  // against the ACK's new revision; intermediate selections are never submitted.
  await page.evaluate(() => {
    window.f = makeFixture(state("only",0,1,1));
    for (let n=1;n<=5;n++) f.choose(n);
  });
  result = await page.evaluate(() => ({ view: f.view(), writes: f.writes, queue: f.header.__hmbSeedanceQueuedShot }));
  assert.equal(result.writes.length,1); assert.equal(result.queue.key,"10000000-0000-4000-8000-000000000002\u001f10000000-0000-4000-8000-000000000007");
  await page.evaluate(() => {
    f.update(state("shot",1,2,2));
    for(let i=0;i<100;i++) f.update(state("shot",1,2,2));
  });
  result = await page.evaluate(() => ({view:f.view(),writes:f.writes}));
  assert.equal(result.writes.length,2); assert.equal(result.writes[1].shot.number,5);
  assert.equal(result.writes[1].selection_request.expected_revision,2); assert.equal(result.view.pending,true);
  await page.evaluate(() => { f.update(state("shot",5,3,3)); f.rejects[0](new Error("first request late rejection")); });
  await page.waitForTimeout(0);
  result = await page.evaluate(() => f.view());
  assert.equal(result.label,"05 · Fixture 5"); assert.equal(result.writes,2); assert.equal(result.pending,false);
  await page.evaluate(() => f.cleanup());
  report.cases.push("five_rapid_selections_coalesce_to_last_choice_after_first_ack_without_resubmission_loop");

  await page.evaluate(() => {
    window.f=makeFixture(state("shot",4,1,1));f.choose(1);f.choose(2);f.choose(0);
    f.update(state("shot",1,2,2));
  });
  result=await page.evaluate(()=>({view:f.view(),writes:f.writes}));
  assert.equal(result.writes.length,2);assert.equal(result.writes[1].selection_request.mode,"only");
  assert.equal(result.writes[1].selection_request.expected_revision,2);assert.equal(result.view.label,"Only · 적용 중");
  await page.evaluate(()=>f.update(state("only",0,3,3)));
  assert.equal((await page.evaluate(()=>f.view())).label,"Only");
  await page.evaluate(()=>f.cleanup());
  report.cases.push("rapid_queue_includes_explicit_only_as_final_authoritative_intent");

  await page.evaluate(()=>{
    window.f=makeFixture(state("only",0,1,1));f.choose(1);f.choose(5);
    const ack=state("shot",1,2,2);ack.shot_catalog.shots=ack.shot_catalog.shots.filter(row=>row.number!==5);f.update(ack);
  });
  result=await page.evaluate(()=>({view:f.view(),queue:Boolean(f.header.__hmbSeedanceQueuedShot),error:f.header.querySelector(".hmb-seedance-shot__status").textContent}));
  assert.equal(result.view.writes,1);assert.equal(result.queue,false);assert.equal(result.view.pending,false);
  assert.equal(result.view.label,"01 · Fixture 1");assert.match(result.error,/샷을 사용할 수 없습니다/);
  await page.evaluate(()=>{f.update(state("shot",1,2,3));});
  assert.equal((await page.evaluate(()=>f.view())).writes,1,"Restoring a removed queued UUID must not resurrect an automatic request.");
  await page.evaluate(()=>f.cleanup());
  report.cases.push("deleted_queued_uuid_is_not_submitted_or_resurrected_when_catalog_returns");

  await page.evaluate(()=>{
    window.f=makeFixture(state("only",0,11,11));f.commands=[];
    const parameter=document.createElement("div");parameter.dataset.parameterName="HMB_SEEDANCE_REFRESH_COMMAND";
    const carrier=document.createElement("div");parameter.append(carrier);f.node.append(parameter);
    f.bridge=widget.default(carrier,{value:{schema:"hmb-seedance-refresh-command",version:1},onChange(command){f.commands.push(clone(command));return Promise.resolve();}});
    if(!widget.hmbSeedanceRequestDraftFinal(f.header))throw Error("Expected the current Draft's command to be available");
  });
  await page.waitForFunction(()=>f.commands.length===1,{},{timeout:3000});
  result=await page.evaluate(()=>({view:f.view(),command:f.commands[0]}));
  assert.equal(result.command.action,"finalize_draft");assert.equal(result.view.mode,"only");assert.equal(result.view.revision,11);
  assert.equal(result.view.writes,0);assert.equal(Object.hasOwn(result.command,"execution_mode"),false);
  assert.equal(Object.hasOwn(result.command,"selection_request"),false);assert.equal(Object.hasOwn(result.command,"shot"),false);
  await page.evaluate(()=>{f.bridge.cleanup();f.cleanup();});
  report.cases.push("draft_command_uses_retained_bridge_without_publishing_or_changing_execution_mode");

  await page.clock.install();
  await page.evaluate(()=>{window.f=makeFixture(state("only",0,1,1));f.choose(1);f.choose(5);});
  await page.clock.fastForward(10_001);
  result=await page.evaluate(()=>({view:f.view(),queue:Boolean(f.header.__hmbSeedanceQueuedShot),error:f.header.querySelector(".hmb-seedance-shot__status").textContent}));
  assert.equal(result.queue,false);assert.equal(result.view.pending,false);assert.equal(result.view.writes,1);
  assert.equal(result.view.label,"Only");assert.match(result.error,/응답/);
  await page.evaluate(()=>{f.rejects[0](new Error("late timeout rejection"));f.update(state("shot",2,2,2));});
  assert.match(await page.evaluate(()=>f.header.querySelector(".hmb-seedance-shot__status").textContent),/응답/,
    "A different Shot's late authoritative update does not confirm the timed-out target.");
  await page.evaluate(()=>{f.header.__hmbSeedanceShotChangeError="Separate actual save failure";f.update(state("shot",1,3,3));});
  result=await page.evaluate(()=>({error:f.header.__hmbSeedanceModeSelectionError,actualError:f.header.__hmbSeedanceShotChangeError,view:f.view()}));
  assert.equal(result.error,undefined,"A higher revision for the exact timed-out target confirms that selection.");
  assert.equal(result.actualError,"Separate actual save failure","Confirming a selection must not clear an unrelated actual failure.");
  assert.equal(result.view.label,"01 · Fixture 1");
  await page.evaluate(()=>f.cleanup());
  report.cases.push("ack_timeout_clears_request_queue_without_retry_and_late_rejection_is_inert");
  report.cases.push("late_exact_target_ack_clears_only_its_timeout_notice_and_keeps_other_errors");

  await page.evaluate(()=>{window.f=makeFixture(state("only",0,1,1));f.choose(1);});
  await page.clock.fastForward(10_001);
  await page.evaluate(()=>{
    f.update(state("only",0,1,1,{execution_mode_instance:instanceB}));
    f.header.__hmbSeedanceModeSelectionError="New instance actual error";
    f.update(state("shot",1,50,50));
  });
  result=await page.evaluate(()=>({error:f.header.__hmbSeedanceModeSelectionError,view:f.view()}));
  assert.equal(result.error,"New instance actual error");assert.equal(result.view.instance,"b".repeat(32));
  await page.evaluate(()=>{
    const old=f.controller;f.controller.cleanup();old.update(f.props(state("shot",1,51,51)));
    window.deletedView={empty:f.header.innerHTML==="",baselineGone:!f.header.__hmbSeedanceModeBaseline};f.node.remove();
  });
  assert.deepEqual(await page.evaluate(()=>deletedView),{empty:true,baselineGone:true});
  report.cases.push("new_instance_errors_survive_old_ack_and_deleted_controller_does_not_remount");

  assert.deepEqual(errors,[]); assert.equal(report.external_requests,0);
  assert.equal(hash(fs.readFileSync(widgetPath)),report.widget_sha256);
  report.console_errors=errors; report.source_unchanged=true; report.passed=true;
} finally {
  await browser.close();
  const output=argument("--evidence-path");
  if(output){fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(report,null,2)+"\n");}
  process.stdout.write(JSON.stringify(report)+"\n");
}
