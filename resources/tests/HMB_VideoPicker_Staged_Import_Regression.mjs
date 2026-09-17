import assert from "node:assert/strict";
import fs from "node:fs";
const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const factoryStart = source.indexOf("export default function HMBVideoPickerLibraryWidget");
const listenerHelper = source.indexOf("  const on = ", factoryStart);
const firstRegistration = source.indexOf("  on(", factoryStart);
assert.ok(listenerHelper > factoryStart && firstRegistration > listenerHelper,
  "Cold mount must initialize the event helper before registering any listeners.");
const first = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", second = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const jobs = [first, second].map((shot, index) => ({ import_id: `import-${index}`, picker_shot_uuid: shot,
  label: `clip-${index}.mp4`, runtime_instance_id: "runtime", status: "loading", error: "" }));
const state = { runtime_instance_id: "runtime", language: "ko", active_picker_shot_uuid: first, videos: [], video_imports: jobs,
  shot_publisher_instance_uuid: "11111111-1111-4111-8111-111111111111",
  channel_uuid: "22222222-2222-4222-8222-222222222222",
  shot_selections: [first, second].map((shot_uuid, index) => ({ shot_uuid, number: index + 1, name: `Shot ${index + 1}`, revision: 1 })),
  picker_shots: [first, second].map((workspace_uuid, index) => ({ workspace_uuid, number: index + 1,
    bound_shot_uuid: workspace_uuid,
    name: `Shot ${index + 1}`, video_asset_uids: [], selected_video_uids: [] })) };
assert.deepEqual(picker.hmbPickerPendingImports(state, first), [jobs[0]]);
assert.equal(picker.hmbPickerPendingImports({ ...state, runtime_instance_id: "replacement" }, first).length, 0);
assert.equal(picker.hmbPickerPendingImports(state, first, { __hmbCancelledVideoImports: new Set(["runtime:import-0"]) }).length, 0);
const readyEcho = { ...state, videos: [{ video_uid: "ready", video_path: "C:/ready.mp4", import_request_id: "import-0" }],
  picker_shots: state.picker_shots.map((row) => row.workspace_uuid === first ? { ...row, video_asset_uids: ["ready"], selected_video_uids: ["ready"] } : row) };
assert.equal(picker.hmbApplyOptimisticPickerVideoDeletions({ __hmbCancelledVideoImports: new Set(["runtime:import-0"]) }, readyEcho).videos.length, 0,
  "A crossed ready-card echo cannot repaint a cancelled placeholder as a playable card.");
const html = picker.hmbPickerImportCardHtml({ ...jobs[0], label: '<img src="bad">' });
assert.match(html, /<progress/);
assert.match(html, /data-picker-import-cancel=/);
assert.match(html, /&lt;img/);
assert.doesNotMatch(html, /<video\b|data-video-uid=|data-toggle-video-uid=|draggable="true"|data-picker-tool-source/);
const failed = picker.hmbPickerImportCardHtml({ ...jobs[0], status: "failed", error: "Failed" }, "en");
assert.match(failed, /Import failed/);
assert.doesNotMatch(failed, /<progress/);
const compact = picker.hmbRenderVideoPickerShotWorkspace(state).tabs;
assert.equal((compact.match(/data-picker-import-id=/g) || []).length, 2);
assert.doesNotMatch(compact, /class="compact-shot-assets empty"/, "Loading-only rows must use the card strip, not the centered empty layout.");
assert.equal(picker.hmbSelectedVideoAssets(state).length, 0, "Loading cards are not Generator inputs.");
assert.equal(picker.hmbPickerOutputLength(state).count, 0);
assert.match(source, /hmbPatchPickerImportCards\(container, authoredState\)/);
assert.match(source, /hmbPatchPickerImportCards\(container, state\)/);
console.log("PASS: staged-import cards are Shot/runtime scoped, cancelable, terminal on failure, escaped, and excluded from playback/reorder/render until ready.");
