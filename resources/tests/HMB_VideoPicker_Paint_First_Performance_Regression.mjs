import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const imageWidgetPath = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const imageSource = fs.readFileSync(imageWidgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);


assert.equal(typeof widget.hmbScheduleVideoPickerPaintFirstTask, "function");
assert.equal(typeof widget.hmbVideoPickerPaintFirstTaskPending, "function");
assert.equal(typeof widget.hmbCancelVideoPickerPaintFirstTask, "function");

const savedGlobals = Object.fromEntries([
  "requestAnimationFrame", "cancelAnimationFrame", "setTimeout", "clearTimeout",
].map((name) => [name, globalThis[name]]));
let frameId = 1;
let timerId = 1;
const frames = new Map();
const timers = new Map();
const flushFrame = () => {
  const current = [...frames.entries()];
  frames.clear();
  current.forEach(([_id, callback]) => callback(Date.now()));
};

try {
  globalThis.requestAnimationFrame = (callback) => {
    const id = frameId++;
    frames.set(id, callback);
    return id;
  };
  globalThis.cancelAnimationFrame = (id) => frames.delete(id);
  globalThis.setTimeout = (callback) => {
    const id = timerId++;
    timers.set(id, callback);
    return id;
  };
  globalThis.clearTimeout = (id) => timers.delete(id);

  const container = {};
  const events = ["feedback"];
  const firstToken = widget.hmbScheduleVideoPickerPaintFirstTask(
    container,
    "state-publication",
    () => events.push("stale-publication"),
  );
  assert.ok(firstToken > 0);
  assert.equal(widget.hmbVideoPickerPaintFirstTaskPending(container, "state-publication"), true);
  assert.deepEqual(events, ["feedback"], "No publication may run in the input event turn.");

  flushFrame();
  assert.deepEqual(events, ["feedback"], "The first frame is reserved for local feedback paint.");

  const secondToken = widget.hmbScheduleVideoPickerPaintFirstTask(
    container,
    "state-publication",
    () => events.push("latest-publication"),
  );
  assert.ok(secondToken > firstToken);
  assert.equal(frames.size, 1, "Rapid updates coalesce onto the original paint deadline.");
  flushFrame();
  assert.deepEqual(events, ["feedback", "latest-publication"]);
  assert.equal(widget.hmbVideoPickerPaintFirstTaskPending(container, "state-publication"), false);
  assert.equal(timers.size, 0, "The background-tab fallback is cleared after normal paint delivery.");

  widget.hmbScheduleVideoPickerPaintFirstTask(container, "view-transition", () => {
    throw new Error("A cancelled transition cannot execute.");
  });
  assert.equal(widget.hmbCancelVideoPickerPaintFirstTask(container, "view-transition"), true);
  flushFrame();

  // requestAnimationFrame can stop in a minimized/background tab. The bounded
  // fallback must still preserve the interaction and run exactly once.
  delete globalThis.requestAnimationFrame;
  delete globalThis.cancelAnimationFrame;
  let fallbackRuns = 0;
  widget.hmbScheduleVideoPickerPaintFirstTask(
    container,
    "background",
    () => { fallbackRuns += 1; },
  );
  assert.equal(timers.size, 1);
  const fallback = [...timers.values()][0];
  fallback();
  assert.equal(fallbackRuns, 1);
  assert.equal(widget.hmbVideoPickerPaintFirstTaskPending(container, "background"), false);
} finally {
  for (const [name, value] of Object.entries(savedGlobals)) {
    if (value === undefined) delete globalThis[name];
    else globalThis[name] = value;
  }
}

const selectionStart = source.indexOf("const toggleSharedLoaderVideoSelection = (");
const selectionEnd = source.indexOf("const commitSharedLoaderVideoDrag = (", selectionStart);
const selectionSource = source.slice(selectionStart, selectionEnd);
assert.ok(selectionStart >= 0 && selectionEnd > selectionStart);
assert.ok(
  selectionSource.indexOf("hmbApplySelectedVideoAssetOrderToDom")
    < selectionSource.indexOf("schedulePickerStatePublicationAfterPaint"),
  "Selection feedback must be applied before deferred host publication.",
);
assert.match(selectionSource, /suppressMatchingEcho:\s*true/);

const paletteStart = source.indexOf("const applyColor = (color) => {");
const paletteEnd = source.indexOf("const scenePathInput =", paletteStart);
const paletteSource = source.slice(paletteStart, paletteEnd);
assert.ok(paletteStart >= 0 && paletteEnd > paletteStart);
assert.equal(
  (paletteSource.match(/schedulePickerStatePublicationAfterPaint\(/g) || []).length,
  2,
  "Both palette-color mutations must share the paint-first latest-only publisher.",
);
assert.doesNotMatch(
  paletteSource,
  /\bcommit\(/,
  "Palette feedback must not synchronously publish the full picker state.",
);

const outlinerStart = source.indexOf("const selectOutlinerPath = (path) => {");
const outlinerEnd = source.indexOf("on(outlinerScroll", outlinerStart);
const outlinerSource = source.slice(outlinerStart, outlinerEnd);
assert.ok(outlinerStart >= 0 && outlinerEnd > outlinerStart);
assert.equal(
  (outlinerSource.match(/schedulePickerStatePublicationAfterPaint\(/g) || []).length,
  3,
  "Outliner select, expand, and visibility mutations must share one coalescing publisher.",
);
assert.doesNotMatch(
  outlinerSource,
  /\bcommit\(/,
  "Outliner feedback must not synchronously publish the full picker state.",
);

const cameraStart = source.indexOf("hmbInstallPickerValueControlDelegation(\n    container.querySelector(\".picker-camera-control\")");
const cameraEnd = source.indexOf("hmbInstallPickerValueControlDelegation(\n    container.querySelector(\".palette-head\")", cameraStart);
const cameraSource = source.slice(cameraStart, cameraEnd);
assert.ok(cameraStart >= 0 && cameraEnd > cameraStart);
assert.match(cameraSource, /schedulePickerStatePublicationAfterPaint\(next\)/);
assert.doesNotMatch(
  cameraSource,
  /\bcommit\(/,
  "Camera selection must not synchronously publish the full picker state.",
);

const commitStart = source.indexOf("const commit = (next, options = {}) => {");
const commitEnd = source.indexOf("const currentWidgetState = () => {", commitStart);
const commitSource = source.slice(commitStart, commitEnd);
assert.match(
  commitSource,
  /hmbCancelVideoPickerPaintFirstTask\(container, "state-publication"\)/,
  "A newer synchronous mutation must cancel a queued draft before it can replay stale media.",
);
assert.match(commitSource, /delete container\.__hmbPickerPaintFirstPublication/);

const currentStateStart = source.indexOf("const currentWidgetState = () => {");
const currentStateEnd = source.indexOf("const commandBridge = () => {", currentStateStart);
const currentStateSource = source.slice(currentStateStart, currentStateEnd);
assert.ok(currentStateStart >= 0 && currentStateEnd > currentStateStart);
assert.match(
  currentStateSource,
  /container\.__hmbPickerPaintFirstState[\s\S]*container\.__hmbPendingPickerState[\s\S]*state/,
  "Commands must observe the queued paint-first draft before pending or committed state.",
);

const dispatchStart = source.indexOf("const dispatchCommand = (action,");
const dispatchEnd = source.indexOf("const scheduleReadAckTimeout", dispatchStart);
const dispatchSource = source.slice(dispatchStart, dispatchEnd);
assert.ok(dispatchStart >= 0 && dispatchEnd > dispatchStart);
assert.match(
  dispatchSource,
  /\["read_scene", "render_original_preview", "run_video", "render_snapshot"\][\s\S]*flushPickerStatePublicationBeforeCommand\(\)/,
  "READ, Generate, and Snapshot must flush a queued UI draft before command dispatch.",
);

const flushStart = source.indexOf("const flushPickerStatePublicationBeforeCommand = () => {");
const flushEnd = source.indexOf("const toggleSharedLoaderVideoSelection = (", flushStart);
const flushSource = source.slice(flushStart, flushEnd);
assert.ok(flushStart >= 0 && flushEnd > flushStart);
assert.match(flushSource, /hmbCancelVideoPickerPaintFirstTask\(container, "state-publication"\)/);
assert.match(flushSource, /commit\(queuedState/);
assert.match(flushSource, /return currentWidgetState\(\)/);

const toggleStart = source.indexOf("const togglePickerView = () => {");
const toggleEnd = source.indexOf("const commandBridge = () => {", toggleStart);
const toggleSource = source.slice(toggleStart, toggleEnd);
assert.ok(toggleStart >= 0 && toggleEnd > toggleStart);
assert.ok(
  toggleSource.indexOf("data-picker-view-transition-pending")
    < toggleSource.indexOf("hmbScheduleVideoPickerPaintFirstTask"),
  "Mode switching must expose immediate busy feedback before scheduling its morph.",
);
assert.ok(
  toggleSource.indexOf("hmbScheduleVideoPickerPaintFirstTask")
    < toggleSource.indexOf("hmbSetVideoPickerHybridView(container, false"),
  "The retained-subtree view change must run behind the paint boundary.",
);
assert.doesNotMatch(
  toggleSource,
  /HMBVideoPickerLibraryWidget\(container, liveProps\)|\bcleanup\(\)/,
  "A paint-first view change must not remount or clean up the live controller.",
);

const sizingStart = source.indexOf("export function hmbInstallVideoPickerCompactHostSizing(");
const sizingEnd = source.indexOf("function hmbApplyPickerInitialNodeSizeOnce", sizingStart);
const sizingSource = source.slice(sizingStart, sizingEnd);
assert.ok(sizingStart >= 0 && sizingEnd > sizingStart);
assert.doesNotMatch(sizingSource, /secondFrame/);
assert.equal(
  (sizingSource.match(/firstFrame\s*=\s*frame\(/g) || []).length,
  1,
  "Compact sizing coalesces to one settled frame instead of two layout passes.",
);

const selectedThumbStart = imageSource.indexOf("function thumbnailImageMarkup(asset)");
const selectedThumbEnd = imageSource.indexOf("function assetCardThumbnailImageMarkup", selectedThumbStart);
const selectedThumbSource = imageSource.slice(selectedThumbStart, selectedThumbEnd);
assert.match(selectedThumbSource, /loading="lazy"/);
assert.match(selectedThumbSource, /decoding="async"/);
assert.match(selectedThumbSource, /fetchpriority="low"/);

// Performance scheduling must not weaken Shot-local selection ownership.
const shotA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const shotB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const video = (uid) => ({ video_uid: uid, source_uid: uid, video_path: `C:/shots/${uid}.mp4` });
const state = {
  videos: [video("video-a"), video("video-b")],
  picker_shots: [
    {
      workspace_uuid: shotA,
      number: 1,
      name: "Shot 1",
      video_asset_uids: ["video-a"],
      selected_video_uids: [],
      preview_video_uid: "",
    },
    {
      workspace_uuid: shotB,
      number: 2,
      name: "Shot 2",
      video_asset_uids: ["video-b"],
      selected_video_uids: ["video-b"],
      preview_video_uid: "video-b",
    },
  ],
  active_picker_shot_uuid: shotA,
};
const selected = widget.hmbToggleVideoAssetSelection(state, "video-a");
assert.deepEqual(
  selected.picker_shots.find((row) => row.workspace_uuid === shotA).selected_video_uids,
  ["video-a"],
);
assert.deepEqual(
  selected.picker_shots.find((row) => row.workspace_uuid === shotB).selected_video_uids,
  ["video-b"],
  "Paint-first selection cannot mutate another Shot.",
);

console.log("HMB VideoPicker paint-first performance regression: PASS");
