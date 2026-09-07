import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const shotA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const shotB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const asset = (uid) => ({ video_uid: uid, video_path: `C:/shots/${uid}.mp4`, video_url: `http://localhost/media/${uid}.mp4`, width: 1920, height: 1080 });
const initial = {
  runtime_instance_id: "tools-test", active_picker_shot_uuid: shotA, language: "en", videos: [asset("a"), asset("b"), asset("c")],
  video_tools_default_output_directory: "C:/project/picker-output",
  preview_video_uid: "a", selected_video_uid: "a",
  picker_shots: [
    { workspace_uuid: shotA, name: "Shot 1", video_asset_uids: ["a", "b"], selected_video_uids: ["b", "a"], preview_video_uid: "a" },
    { workspace_uuid: shotB, name: "Shot 2", video_asset_uids: ["c"], selected_video_uids: ["c"], preview_video_uid: "c" },
  ],
};

// Importing and reordering an edit queue must never change generator ports,
// selection, the viewport cursor, or another Shot's queue.
const copied = picker.hmbCopyPickerSelectionToToolQueue(initial);
assert.deepEqual(copied.video_tools_by_shot[shotA].concatenate.inputs, ["C:/shots/b.mp4", "C:/shots/a.mp4"]);
assert.equal(copied.videos, initial.videos);
assert.equal(copied.picker_shots, initial.picker_shots);
assert.equal(copied.preview_video_uid, "a");
const reordered = picker.hmbMovePickerToolQueue(copied, 1, 0);
assert.deepEqual(reordered.video_tools_by_shot[shotA].concatenate.inputs, ["C:/shots/a.mp4", "C:/shots/b.mp4"]);
assert.deepEqual(picker.hmbSelectedVideoAssets(reordered).map((item) => item.video_uid), ["b", "a"]);
const second = picker.hmbCopyPickerSelectionToToolQueue({ ...reordered, active_picker_shot_uuid: shotB });
assert.deepEqual(second.video_tools_by_shot[shotB].concatenate.inputs, ["C:/shots/c.mp4"]);
assert.deepEqual(second.video_tools_by_shot[shotA], reordered.video_tools_by_shot[shotA]);

// Progress echoes cannot roll an edit draft back, but a new runtime must not
// inherit drafts from the destroyed node instance.
const echoed = picker.hmbPreservePickerToolDrafts({ ...initial, video_tools_status: { status: "running", progress: 0.5 } }, second);
assert.deepEqual(echoed.video_tools_by_shot, second.video_tools_by_shot);
assert.equal(echoed.video_tools_status.progress, 0.5);
assert.equal(picker.hmbPreservePickerToolDrafts({ runtime_instance_id: "new" }, second).video_tools_by_shot, undefined);
assert.deepEqual(picker.hmbNormalizePickerVideoToolsByShot(JSON.parse(JSON.stringify(second.video_tools_by_shot))), second.video_tools_by_shot);

// An 800x600 player letterboxes a 1920x1080 source into 800x450 at y=75.
const geometry = picker.hmbPickerCropContainGeometry({ left: 100, top: 50, width: 800, height: 600 }, 1920, 1080);
assert.equal(geometry.top, 125);
assert.equal(geometry.height, 450);
const crop = picker.hmbPickerCropDragRectangle({ x: 200, y: 200 }, { x: 700, y: 450 }, geometry);
assert.deepEqual(crop, { x: 240, y: 180, width: 1200, height: 600 });
// A 50% React Flow canvas zoom changes every DOM pixel, not source pixels.
const zoomGeometry = picker.hmbPickerCropContainGeometry({ left: 50, top: 25, width: 400, height: 300 }, 1920, 1080);
assert.deepEqual(picker.hmbPickerCropDragRectangle({ x: 100, y: 100 }, { x: 350, y: 225 }, zoomGeometry), crop);
const backwards = picker.hmbPickerCropDragRectangle({ x: 700, y: 450 }, { x: 200, y: 200 }, geometry);
assert.deepEqual(backwards, crop);
const bounded = picker.hmbPickerCropDragRectangle({ x: -100, y: -100 }, { x: 1500, y: 1500 }, geometry);
assert.deepEqual(bounded, { x: 0, y: 0, width: 1920, height: 1080 });
assert.equal(picker.hmbPickerCropContainGeometry({ width: 0, height: 0 }, 1920, 1080), null);
assert.deepEqual(picker.hmbPickerCropRectangle({ crop_size: "Custom", crop_position: "Custom", custom_width: 701, custom_height: 501, custom_left: 1900, custom_top: 1000 }, 1920, 1080), { x: 1220, y: 580, width: 700, height: 500 });

class Element {
  constructor(attributes = {}) { this.attributes = new Map(Object.entries(attributes)); this.hidden = false; this.style = {}; this.writes = 0; this.listeners = new Map(); this.classList = { add() {}, remove() {} }; }
  set innerHTML(value) { this.html = value; this.writes += 1; }
  get innerHTML() { return this.html || ""; }
  getAttribute(name) { return this.attributes.get(name) || null; }
  hasAttribute(name) { return this.attributes.has(name); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return this; }
  addEventListener(name, listener) { const list = this.listeners.get(name) || []; list.push(listener); this.listeners.set(name, list); }
  removeEventListener(name, listener) { this.listeners.set(name, (this.listeners.get(name) || []).filter((fn) => fn !== listener)); }
  emit(name, target, extra = {}) { for (const listener of this.listeners.get(name) || []) listener({ target, preventDefault() {}, stopPropagation() {}, stopImmediatePropagation() {}, ...extra }); }
}

// Logical empty media must hide the retained real player, not merely show a
// placeholder beside it. Explicit author CSS is needed because preview-video
// has display:block, which otherwise overrides the browser's hidden styling.
assert.match(source, /#picker-video\[hidden\],[^\n]*#picker-snapshot-image\[hidden\],[^\n]*\.viewport-empty\[hidden\]\{display:none!important\}/);
const retainedVideo = new Element({ src: "http://localhost/media/a.mp4" });
retainedVideo.paused = false; retainedVideo.pause = () => { retainedVideo.paused = true; };
const retainedSnapshot = new Element(), retainedEmpty = new Element(), emptyTitle = new Element(), emptyBody = new Element();
retainedEmpty.querySelector = (selector) => selector === "b" ? emptyTitle : selector === "span" ? emptyBody : null;
const retainedStage = new Element(); retainedStage.ownerDocument = { createElement() { return new Element(); } };
retainedStage.querySelector = (selector) => ({ "#picker-video": retainedVideo, "#picker-snapshot-image": retainedSnapshot, ".viewport-empty": retainedEmpty })[selector] || null;
const retainedRoot = new Element(); retainedRoot.__hmbVideoPickerExpanded = true;
retainedRoot.querySelector = (selector) => selector === ".viewport-stage" ? retainedStage : null;
const emptyCrop = picker.hmbUpdatePickerVideoTools(initial, (tools) => { tools.active_tool = "crop"; });
picker.hmbPatchVideoPickerPreviewDom(retainedRoot, emptyCrop);
assert.equal(retainedVideo.hidden, true);
assert.equal(retainedVideo.paused, true);
assert.equal(retainedSnapshot.hidden, true);
assert.equal(retainedEmpty.hidden, false);
assert.equal(emptyTitle.textContent, "No tool input");
picker.hmbPatchVideoPickerPreviewDom(retainedRoot, picker.hmbApplyPickerToolSource(emptyCrop, "b", "crop"));
assert.equal(retainedVideo.hidden, false);
assert.equal(retainedEmpty.hidden, true);
assert.equal(retainedVideo.getAttribute("src"), "http://localhost/media/b.mp4");

// A later Loader selection/card reconciliation must retain tool copy-drag
// affordances even for a single selected card and an unselected card.
const loaderCards = ["a", "b"].map((uid) => new Element({ "data-video-uid": uid }));
const loaderGrid = new Element(); loaderGrid.children = loaderCards;
loaderGrid.querySelectorAll = () => loaderCards;
loaderGrid.appendChild = () => {};
const loaderRoot = new Element(); loaderRoot.__hmbVideoPickerExpanded = true;
loaderRoot.querySelector = (selector) => selector === ".video-asset-grid" ? loaderGrid : null;
const oneSelected = { ...emptyCrop, picker_shots: emptyCrop.picker_shots.map((shot) => shot.workspace_uuid === shotA ? { ...shot, selected_video_uids: ["a"] } : shot) };
picker.hmbApplySelectedVideoAssetOrderToDom(loaderRoot, oneSelected);
assert.deepEqual(loaderCards.map((card) => card.getAttribute("draggable")), ["true", "true"]);
picker.hmbApplySelectedVideoAssetOrderToDom(loaderRoot, picker.hmbUpdatePickerVideoTools(oneSelected, (tools) => { tools.active_tool = "preview"; }));
assert.deepEqual(loaderCards.map((card) => card.getAttribute("draggable")), ["false", "false"], "Normal Loader reorder rules remain unchanged outside the tools.");

let liveState = picker.hmbUpdatePickerVideoTools(copied, (tools) => { tools.active_tool = "concatenate"; });
const root = new Element(); root.__hmbVideoPickerExpanded = true;
const panel = new Element(), statusRoot = new Element(), message = new Element(), progress = new Element(), viewport = new Element();
const player = new Element(); player.id = "picker-video"; player.paused = true; player.videoWidth = 1920; player.videoHeight = 1080; player.pause = () => { player.paused = true; }; player.getBoundingClientRect = () => ({ left: 100, top: 50, width: 800, height: 600 });
const overlay = new Element(), box = new Element(), stage = new Element(); stage.clientWidth = 800; stage.clientHeight = 600; stage.getBoundingClientRect = player.getBoundingClientRect;
const buttons = Object.fromEntries(["cancel", "result", "add_result"].map((name) => [name, new Element({ "data-picker-tool-action": name })]));
statusRoot.querySelector = (selector) => selector === "[data-picker-tool-message]" ? message : selector === "progress" ? progress : Object.entries(buttons).find(([key]) => selector.includes(`\"${key}\"`))?.[1] || null;
const elements = new Map([["[data-picker-tools-panel]", panel], ["[data-picker-tools-status]", statusRoot], [".viewport-panel", viewport], ["#picker-video", player], [".viewport-stage", stage], ["[data-picker-crop-overlay]", overlay], ["[data-picker-crop-box]", box]]);
root.querySelector = (selector) => elements.get(selector) || null;
const commands = [], previews = [];
let mediaController = null;
const controller = picker.hmbInstallPickerVideoTools(root, {
  currentState: () => liveState,
  commit(next) { liveState = next; return { state: next, delivered: true }; },
  dispatch(action, payload) { commands.push({ action, payload }); return { delivered: true }; },
  patchPreview(state) {
    const descriptor = picker.hmbVideoPickerPreviewDescriptor(state, root);
    previews.push(descriptor);
    if (mediaController) {
      player.setAttribute("src", descriptor.url);
      player.setAttribute("data-video-uid", descriptor.videoUid);
      mediaController.refresh(state);
    }
  },
});
// A populated Picker and the hidden external metadata index never occupy either
// tool automatically, including the existing viewport or its timeline context.
const populated = liveState;
for (const mode of ["concatenate", "crop"]) {
  liveState = picker.hmbUpdatePickerVideoTools(initial, (tools) => {
    tools.active_tool = mode;
    tools.external_sources = [{ source_uid: "external-hidden", local_path: "C:/external/hidden.mp4", browser_url: "http://localhost/media/hidden.mp4" }];
  });
  controller.refresh(liveState);
  assert.doesNotMatch(panel.innerHTML, /data-picker-tool-source-uid|data-picker-tool-queue=|data-picker-tool-crop-input=|role="dialog"/);
  assert.equal(picker.hmbVideoPickerPreviewDescriptor(liveState, root).kind, "empty");
  assert.equal(picker.hmbVideoPickerPreviewDescriptor(liveState, root).url, "");
  assert.equal(picker.hmbVideoPickerMediaFrameContext(liveState, root).hasRange, false);
  assert.equal(liveState.preview_video_uid, "a");
}
liveState = populated; controller.refresh(liveState);
assert.match(panel.innerHTML, /Edit queue/);
assert.match(panel.innerHTML, /<article draggable="true" data-picker-tool-queue="0"[^>]*><button class="picker-tools-input-remove"/);
assert.doesNotMatch(panel.innerHTML, /data-picker-tool-source-uid|role="dialog"/);
assert.match(panel.innerHTML, /data-picker-tool-field="concatenate.output_path"[^>]*value="C:\/shots"[^>]* disabled/);
assert.doesNotMatch(panel.innerHTML, /data-picker-tool-action="copy"/);
assert.doesNotMatch(panel.innerHTML, /data-picker-tool-action="browse_sources"|data-picker-tool-action="browse_picker"|data-picker-tool-output-hint/);
assert.match(panel.innerHTML, /class="picker-tools-output"><label class="picker-tools-manual">.*?<\/label><input aria-label="Output path"/);
assert.match(panel.innerHTML, /placeholder="Automatic: saves beside the first input video\. Manual: enter the destination file path\."/);
assert.match(source, /\.hmbvp \.picker-tools-dropzone\{[^}]*min-height:140px/);
assert.match(source, /crop: "영상크롭"/);
assert.doesNotMatch(source, /crop: "화면크롭"/);
const manual = new Element({ "data-picker-tool-field": "concatenate.manual_output_enabled" });
manual.checked = true; root.emit("change", manual);
assert.equal(liveState.video_tools_by_shot[shotA].concatenate.manual_output_enabled, true);
assert.doesNotMatch(panel.innerHTML, /data-picker-tool-field="concatenate.output_path"[^>]* disabled/);
const customPath = new Element({ "data-picker-tool-field": "concatenate.output_path" });
const beforePathBlurWrites = panel.writes;
customPath.value = "C:/custom/concat.mp4"; root.emit("change", customPath);
assert.equal(panel.writes, beforePathBlurWrites, "Path blur cannot remount the Run button before its click.");
manual.checked = false; root.emit("change", manual);
assert.equal(liveState.video_tools_by_shot[shotA].concatenate.output_path, "C:/custom/concat.mp4");
assert.equal(liveState.video_tools_by_shot[shotA].crop.manual_output_enabled, false);
assert.match(panel.innerHTML, /value="C:\/shots"/);
customPath.value = "C:/ignored/disabled.mp4"; root.emit("change", customPath);
assert.equal(liveState.video_tools_by_shot[shotA].concatenate.output_path, "C:/custom/concat.mp4", "Disabled-path synthetic edits must be ignored.");
manual.checked = true; root.emit("change", manual);
assert.match(panel.innerHTML, /value="C:\/custom\/concat.mp4"/);
const writes = panel.writes;
liveState = { ...liveState, video_tools_status: { picker_shot_uuid: shotA, status: "running", progress: 0.45 } };
controller.refresh(liveState);
assert.equal(panel.writes, writes, "Progress patches must preserve the control DOM and current player.");
assert.equal(root.querySelector("#picker-video"), player);
assert.equal(message.textContent, "Processing 45%");

// Thumbnail pointer dragging works even where native button dragging is not
// initiated by the host, and still affects only the independent edit queue.
const dragThumb = new Element({ "data-picker-tool-drag": "1" });
const dropCard = new Element({ "data-picker-tool-queue": "0" });
root.ownerDocument = { elementFromPoint() { return dropCard; } };
root.emit("pointerdown", dragThumb, { pointerId: 1, button: 0, clientX: 300, clientY: 100 });
root.emit("pointermove", dragThumb, { pointerId: 1, clientX: 100, clientY: 100 });
root.emit("pointerup", dragThumb, { pointerId: 1, clientX: 100, clientY: 100 });
assert.deepEqual(liveState.video_tools_by_shot[shotA].concatenate.inputs, ["C:/shots/a.mp4", "C:/shots/b.mp4"]);
assert.deepEqual(picker.hmbSelectedVideoAssets(liveState).map((item) => item.video_uid), ["b", "a"]);

const click = (attributes) => root.emit("click", new Element(attributes));
const dropSource = (uid, tool) => {
  const card = new Element({ "data-picker-tool-source-uid": uid });
  card.closest = (selector) => selector.includes("data-picker-tool-source-uid") ? card : null;
  const drop = new Element({ "data-picker-tool-drop": tool });
  drop.closest = (selector) => selector.includes("data-picker-tool-drop") ? drop : null;
  const data = new Map(), dataTransfer = { setData(key, value) { data.set(key, value); }, getData(key) { return data.get(key) || ""; } };
  root.emit("dragstart", card, { dataTransfer });
  root.emit("drop", drop, { dataTransfer });
};
// Retired duplicate browser actions must not add inputs or dispatch work.
// Right-hand source Shot navigation is covered by its own controller test.
const beforeBrowser = JSON.stringify(liveState);
const beforeBrowseCommands = commands.length;
click({ "data-picker-tool-action": "browse_picker" });
click({ "data-picker-tool-action": "browse_sources" });
assert.doesNotMatch(panel.innerHTML, /role="dialog"|data-picker-tool-action="browse/);
assert.equal(commands.length, beforeBrowseCommands);
assert.equal(JSON.stringify(liveState), beforeBrowser);
dropSource("c", "concatenate");
assert.equal(liveState.active_picker_shot_uuid, shotA);
assert.deepEqual(liveState.video_tools_by_shot[shotA].concatenate.input_uids, ["a", "b", "c"]);
assert.doesNotMatch(panel.innerHTML, /role="dialog"|data-picker-tool-source-uid/);
assert.deepEqual(picker.hmbSelectedVideoAssets(liveState).map((item) => item.video_uid), ["b", "a"]);
click({ "data-picker-tool-remove": "2" });
assert.deepEqual(liveState.video_tools_by_shot[shotA].concatenate.input_uids, ["a", "b"]);
assert.equal(liveState.videos.some((item) => item.video_uid === "c"), true);
click({ "data-picker-tool-tab": "crop" });
assert.equal(liveState.video_tools_by_shot[shotA].crop.source_uid, "", "Entering Crop never auto-applies a Picker selection.");
assert.doesNotMatch(panel.innerHTML, /role="dialog"|data-picker-tool-source-uid|data-picker-tool-crop-input=/);
assert.equal(previews.at(-1).kind, "empty");
assert.doesNotMatch(panel.innerHTML, /data-picker-tool-action="copy"|data-picker-tool-source>/);
dropSource("a", "crop");
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(root.__hmbSuppressVideoSelectionClick, undefined, "A drop that replaces the source card must release click suppression without waiting for dragend.");
assert.equal(stage.getAttribute("data-picker-tool-drop"), "crop", "The existing viewport accepts a direct Loader/source-card crop drop.");
assert.equal(liveState.video_tools_by_shot[shotA].crop.source_uid, "a");
assert.equal(liveState.video_tools_by_shot[shotA].crop.input, "C:/shots/a.mp4");
assert.equal(liveState.video_tools_by_shot[shotA].crop.custom_width, 1920);
assert.equal(liveState.video_tools_by_shot[shotA].crop.custom_height, 1080);
assert.equal(previews.at(-1).url, "http://localhost/media/a.mp4");
assert.equal(liveState.preview_video_uid, "a");
assert.equal(player.paused, true);
assert.equal((panel.innerHTML.match(/data-picker-tool-crop-input=/g) || []).length, 1);

const changeCrop = (field, value) => { const control = new Element({ "data-picker-tool-field": `crop.${field}` }); control.value = value; root.emit("change", control); };
changeCrop("custom_width", "800"); changeCrop("custom_height", "600");
const changeSource = (uid) => dropSource(uid, "crop");
changeSource("b"); changeCrop("custom_width", "640"); changeSource("a");
assert.equal((panel.innerHTML.match(/data-picker-tool-crop-input=/g) || []).length, 1, "A replacement is still exactly one Crop card.");
assert.equal(liveState.video_tools_by_shot[shotA].crop.custom_width, 800, "Crop rectangles are source-local.");
assert.equal(liveState.video_tools_by_shot[shotA].crop_by_source.b.custom_width, 640);
const cropManual = new Element({ "data-picker-tool-field": "crop.manual_output_enabled" }); cropManual.checked = true;
const cropDestination = new Element({ "data-picker-tool-field": "crop.output_path" }); cropDestination.value = "D:/instant-crop.mp4";
panel.querySelectorAll = (selector) => selector === "[data-picker-tool-field]" ? [cropManual, cropDestination] : [];
assert.equal(liveState.video_tools_by_shot[shotA].crop.manual_output_enabled, false);
click({ "data-picker-tool-action": "crop" });
panel.querySelectorAll = () => [];
assert.equal(commands.at(-1).action, "video_tools");
assert.equal(commands.at(-1).payload.op, "crop");
assert.equal(commands.at(-1).payload.picker_shot_uuid, shotA);
assert.equal(commands.at(-1).payload.settings.input, "C:/shots/a.mp4");
assert.equal(commands.at(-1).payload.settings.source_uid, "a", "Exact source UID preserves the original import folder during backend resolution.");
assert.equal(commands.at(-1).payload.settings.custom_width, 800);
assert.equal(commands.at(-1).payload.settings.manual_output_enabled, true, "Run captures the checked DOM even without a change event or host echo.");
assert.equal(commands.at(-1).payload.settings.output_path, "D:/instant-crop.mp4");
const concatBeforeCropClear = structuredClone(liveState.video_tools_by_shot[shotA].concatenate);
click({ "data-picker-tool-action": "clear_crop" });
assert.equal(liveState.video_tools_by_shot[shotA].crop.input, "");
assert.doesNotMatch(panel.innerHTML, /data-picker-tool-crop-input=/);
assert.equal(previews.at(-1).kind, "empty");
assert.deepEqual(liveState.video_tools_by_shot[shotA].concatenate, concatBeforeCropClear);
assert.deepEqual(liveState.videos, initial.videos);
changeSource("a");
const beforeShotChange = liveState;
liveState = { ...liveState, active_picker_shot_uuid: shotB };
controller.refresh(liveState);
assert.doesNotMatch(panel.innerHTML, /role="dialog"|data-picker-tool-source-uid/);
liveState = beforeShotChange; controller.refresh(liveState);

// A completed result is a transient preview and a separate explicit import.
liveState = { ...liveState, video_tools_output: "C:/shots/result.mp4", video_tools_output_url: "http://localhost/media/result.mp4", video_tools_status: { picker_shot_uuid: shotA, result_picker_shot_uuid: shotB, job_id: "done", status: "succeeded", metadata: { duration: 2, frame_rate: 24, width: 800, height: 600 } } };
controller.refresh(liveState);
assert.equal(buttons.add_result.textContent, "Add to Shot 2", "Completed results display the captured destination, not the active work Shot.");
click({ "data-picker-tool-action": "result" });
assert.equal(previews.at(-1).url, "http://localhost/media/result.mp4");
assert.equal(liveState.preview_video_uid, "a");
assert.deepEqual(picker.hmbSelectedVideoAssets(liveState).map((item) => item.video_uid), ["b", "a"]);
assert.equal(picker.hmbVideoPickerMediaFrameContext(liveState, root).end, 47);
click({ "data-picker-tool-action": "add_result" });
assert.equal(commands.at(-1).payload.op, "add_result");
assert.deepEqual(picker.hmbSelectedVideoAssets(liveState).map((item) => item.video_uid), ["b", "a"]);
// Source Play during editing is read-only preview; the destination, tool and
// input identity remain intact while the crop overlay is hidden.
const cropBeforeSourcePlay = structuredClone(liveState.video_tools_by_shot[shotA].crop);
// Wire the production play-event guard: an unarmed play would be immediately
// paused even though calling HTMLMediaElement.play itself appeared successful.
const sourceButtons = ["a", "b"].map((uid) => new Element({ "data-play-video-uid": uid }));
root.querySelectorAll = (selector) => selector === "[data-play-video-uid]" ? sourceButtons : [];
const pendingPlay = [];
player.play = () => { player.paused = false; player.emit("play", player); return new Promise((resolve, reject) => pendingPlay.push({ resolve, reject })); };
player.pause = () => { const changed = !player.paused; player.paused = true; if (changed) player.emit("pause", player); };
mediaController = picker.hmbCreateVideoPickerMediaController(root, { currentState: () => liveState });
click({ "data-play-video-uid": "b" });
assert.equal(player.paused, false, "The real play-event guard accepts the source-card playback intent.");
assert.equal(picker.hmbVideoPickerPlaybackIntentMatches(root, player, "tool-source:b"), true);
assert.equal(sourceButtons[1].textContent, "Ⅱ", "Source card displays Pause even with a transient tool preview UID.");
assert.equal(liveState.video_tools_by_shot[shotA].active_tool, "crop");
assert.equal(liveState.active_picker_shot_uuid, shotA);
assert.deepEqual(liveState.video_tools_by_shot[shotA].crop, cropBeforeSourcePlay);
assert.equal(root.__hmbPickerToolsPreview.source_preview, true);
assert.equal(overlay.hidden, true);
click({ "data-play-video-uid": "b" });
assert.equal(player.paused, true, "Source-card Pause is immediate.");
assert.equal(sourceButtons[1].textContent, "▶");
assert.equal(picker.hmbVideoPickerPlaybackIntentMatches(root, player, "tool-source:b"), false);
click({ "data-play-video-uid": "b" });
click({ "data-play-video-uid": "a" });
assert.equal(player.paused, false);
assert.equal(sourceButtons[0].textContent, "Ⅱ");
const messageBeforeOldRejection = message.textContent;
pendingPlay[1].reject(new Error("stale previous-source rejection"));
await Promise.resolve();
assert.equal(message.textContent, messageBeforeOldRejection);
assert.equal(player.paused, false);
assert.equal(picker.hmbVideoPickerPlaybackIntentMatches(root, player, "tool-source:a"), true);
assert.deepEqual(liveState.video_tools_by_shot[shotA].crop, cropBeforeSourcePlay);
click({ "data-play-video-uid": "a" });
// A second click also cancels a pending play before the browser starts media.
player.play = () => new Promise((resolve, reject) => pendingPlay.push({ resolve, reject }));
click({ "data-play-video-uid": "b" });
assert.equal(sourceButtons[1].textContent, "Ⅱ");
click({ "data-play-video-uid": "b" });
assert.equal(picker.hmbVideoPickerPlaybackIntentMatches(root, player, "tool-source:b"), false);
assert.equal(sourceButtons[1].textContent, "▶");
mediaController.cleanup(); mediaController = null;
click({ "data-picker-tool-tab": "preview" });
root.__hmbVideoPickerExpanded = false;
root.__hmbPickerToolsPreview = { picker_shot_uuid: shotA, active_tool: "preview", uid: "result", path: "http://localhost/media/result.mp4" };
assert.equal(picker.hmbVideoPickerPreviewDescriptor(liveState, root).url, "http://localhost/media/a.mp4", "Compact preview never inherits a tools result override.");
const beforeCompact = JSON.stringify(liveState.video_tools_by_shot);
click({ "data-picker-tool-tab": "crop" });
assert.equal(JSON.stringify(liveState.video_tools_by_shot), beforeCompact);
controller.cleanup();
assert.ok([...root.listeners.values()].every((list) => list.length === 0));
assert.equal(root.__hmbPickerToolsController, undefined);
console.log("PASS: Picker Video Tools queue, Shot state, source crop, geometry, regional progress, result preview, and explicit import.");
