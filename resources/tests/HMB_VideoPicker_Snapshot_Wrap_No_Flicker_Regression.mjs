import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

class MockImage {
  constructor(stage, url = "", ready = false) {
    this.stage = stage;
    this.attrs = new Map(url ? [["src", url]] : []);
    this.hidden = false;
    this.complete = ready;
    this.naturalWidth = ready ? 320 : 0;
    this.listeners = new Map();
    this.srcWrites = 0;
    this.decoding = deferred();
  }
  getAttribute(name) { return this.attrs.get(name) || null; }
  setAttribute(name, value) {
    this.attrs.set(name, String(value));
    if (name === "src") this.srcWrites += 1;
  }
  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }
  decode() { return this.decoding.promise; }
  emit(name) {
    if (name === "load") { this.complete = true; this.naturalWidth = 320; }
    for (const callback of this.listeners.get(name) || []) callback();
    this.listeners.delete(name);
  }
  replaceWith(next) { this.stage.image = next; }
  remove() { if (this.stage.image === this) this.stage.image = null; }
}

function makeFixture(initialUrl = "file:///C:/shot/last.png") {
  const stage = {
    image: null,
    video: { hidden: false, paused: true, ended: false, pause() {}, getAttribute() { return ""; } },
    empty: { hidden: true },
    created: [],
    ownerDocument: { createElement(name) {
      assert.equal(name, "img");
      const image = new MockImage(stage);
      stage.created.push(image);
      return image;
    } },
    querySelector(selector) {
      return ({ "#picker-snapshot-image": this.image, "#picker-video": this.video, ".viewport-empty": this.empty })[selector] || null;
    },
    insertBefore(image) { this.image = image; },
  };
  if (initialUrl) stage.image = new MockImage(stage, initialUrl, true);
  const frameInput = { value: "", max: "250", disabled: false };
  const seek = { value: "", max: "250", disabled: false };
  const title = { textContent: "" };
  const frameInfo = { textContent: "" };
  const timeInfo = { textContent: "" };
  const status = {
    hidden: true,
    attrs: new Map(),
    setAttribute(name, value) { this.attrs.set(name, value); },
    removeAttribute(name) { this.attrs.delete(name); },
    querySelector() { return null; },
  };
  const container = {
    stage,
    querySelector(selector) {
      return ({
        ".viewport-stage": this.stage,
        "#picker-snapshot-image": this.stage?.image,
        "#video-frame-number": frameInput,
        "#video-seek": seek,
        ".viewport-title small": title,
        "#frame-info-frame": frameInfo,
        "#frame-info-time": timeInfo,
        "#picker-preview-load-status": status,
      })[selector] || null;
    },
    querySelectorAll() { return []; },
  };
  return { stage, container, frameInput, seek, title, frameInfo, timeInfo, status };
}

const nextTick = () => new Promise((resolve) => setImmediate(resolve));
const first = "file:///C:/shot/first.png";
const last = "file:///C:/shot/last.png";
const fixture = makeFixture(last);
const oldImage = fixture.stage.image;
const firstSnapshot = { snapshot_uid: "first", frame: 1, url: first };
const lastSnapshot = { snapshot_uid: "last", frame: 250, url: last };

// Last -> first wrap must keep the last decoded image on screen through load
// and decode, while frame feedback updates immediately.
assert.equal(picker.hmbApplySnapshotNavigationFeedback(fixture.container, firstSnapshot, { snapshot: "Snapshot" }, 1, 24), true);
assert.equal(fixture.stage.image, oldImage);
assert.equal(oldImage.getAttribute("src"), last);
assert.equal(oldImage.srcWrites, 0, "The visible image src must never be reassigned while waiting.");
assert.equal(fixture.frameInput.value, "1");
assert.equal(fixture.frameInfo.textContent, "1 / 250");
assert.equal(fixture.frameInput.disabled, true);
assert.equal(fixture.seek.disabled, true);
const firstPending = fixture.stage.created.at(-1);
assert.equal(firstPending.getAttribute("src"), first);
firstPending.emit("load");
assert.equal(fixture.stage.image, oldImage, "Load alone must not reveal an undecoded image.");
firstPending.decoding.resolve();
await nextTick();
assert.equal(fixture.stage.image, firstPending);
assert.equal(fixture.stage.video.hidden, true);

// First -> last reverse wrap follows the same atomic path. Two fast clicks
// make only the newest request authoritative, even when loads finish backward.
picker.hmbApplySnapshotNavigationFeedback(fixture.container, lastSnapshot, {}, 1, 24);
const staleLast = fixture.stage.created.at(-1);
picker.hmbApplySnapshotNavigationFeedback(fixture.container, { ...firstSnapshot, url: first }, {}, 1, 24);
assert.equal(fixture.stage.image, firstPending, "Clicking the already visible snapshot cancels the pending request.");
staleLast.emit("load");
staleLast.decoding.resolve();
await nextTick();
assert.equal(fixture.stage.image, firstPending, "A stale decode must not replace the latest image.");
const imageCount = fixture.stage.created.length;
picker.hmbApplySnapshotNavigationFeedback(fixture.container, firstSnapshot, {}, 1, 24);
assert.equal(fixture.stage.created.length, imageCount, "A one-image history/self-wrap is a media no-op.");
assert.equal(firstPending.srcWrites, 1, "Self-wrap must not reload the decoded image.");
picker.hmbApplySnapshotNavigationFeedback(fixture.container, lastSnapshot, {}, 1, 24);
const lastPending = fixture.stage.created.at(-1);
lastPending.emit("load");
lastPending.decoding.resolve();
await nextTick();
assert.equal(fixture.stage.image, lastPending);

// Video -> Snapshot must retain the paused video until the first snapshot is
// decoded, then switch surfaces without waiting for a host state echo.
const fromVideo = makeFixture("");
assert.equal(picker.hmbApplySnapshotNavigationFeedback(fromVideo.container, firstSnapshot, {}, 1, 24), true);
assert.equal(fromVideo.stage.image, null);
assert.equal(fromVideo.stage.video.hidden, false);
const videoPending = fromVideo.stage.created.at(-1);
videoPending.emit("load");
videoPending.decoding.resolve();
await nextTick();
assert.equal(fromVideo.stage.image, videoPending);
assert.equal(fromVideo.stage.video.hidden, true);

// Returning from Video mode to an already mounted but still-loading image
// also waits for decode, including a load that wins the listener race.
const sameSource = makeFixture(first);
sameSource.stage.image.complete = false;
sameSource.stage.image.naturalWidth = 0;
sameSource.stage.image.hidden = true;
picker.hmbStageVideoPickerSnapshotImage(sameSource.container, first);
assert.equal(sameSource.stage.created.length, 0);
sameSource.stage.image.emit("load");
assert.equal(sameSource.stage.image.hidden, true, "A load event alone is not a decoded frame.");
sameSource.stage.image.decoding.resolve();
await nextTick();
assert.equal(sameSource.stage.image.hidden, false);
assert.equal(sameSource.stage.video.hidden, true);

const listenerRace = makeFixture(first);
listenerRace.stage.image.complete = false;
listenerRace.stage.image.naturalWidth = 0;
listenerRace.stage.image.hidden = true;
const originalAddListener = listenerRace.stage.image.addEventListener.bind(listenerRace.stage.image);
listenerRace.stage.image.addEventListener = (name, callback) => {
  originalAddListener(name, callback);
  if (name === "load") {
    listenerRace.stage.image.complete = true;
    listenerRace.stage.image.naturalWidth = 320;
  }
};
picker.hmbStageVideoPickerSnapshotImage(listenerRace.container, first);
assert.equal(listenerRace.stage.image.hidden, true);
listenerRace.stage.image.decoding.resolve();
await nextTick();
assert.equal(listenerRace.stage.image.hidden, false, "A cache-hit completion during listener setup must not be missed.");

// An unrelated state patch/Shot switch invalidates a pending old Shot load.
picker.hmbApplySnapshotNavigationFeedback(fixture.container, firstSnapshot, {}, 1, 24);
const oldShotPending = fixture.stage.created.at(-1);
const newStage = makeFixture("file:///C:/shot/other-shot.png").stage;
fixture.container.stage = newStage;
picker.hmbStageVideoPickerSnapshotImage(fixture.container, "file:///C:/shot/new-shot.png");
oldShotPending.emit("load");
oldShotPending.decoding.resolve();
await nextTick();
assert.equal(fixture.stage.image, lastPending, "The old Shot's image remains untouched by a late callback.");
assert.equal(newStage.image.getAttribute("src"), "file:///C:/shot/other-shot.png");

// Failed target media leaves the prior decoded frame visible; the generic
// state-patch path uses the same predecode helper as navigation.
const failing = newStage.created.at(-1);
failing.emit("error");
assert.equal(newStage.image.getAttribute("src"), "file:///C:/shot/other-shot.png");
assert.equal(fixture.status.hidden, false);
assert.match(source, /else if \(descriptor\.kind === "snapshot"\) \{[\s\S]*?hmbStageVideoPickerSnapshotImage\(container, descriptor\.url\)/);
assert.match(source, /if \(descriptor\.kind === "video"\) \{\s*delete container\.__hmbPendingPickerSnapshotImage/);

// A normal backend echo uses the same staging path, rather than assigning a
// new URL to the visible <img> while the frame is still decoding.
const echo = makeFixture(last);
const echoedState = {
  viewport_mode: "snapshot",
  active_snapshot_uid: "first",
  snapshots: [firstSnapshot],
  videos: [],
};
picker.hmbPatchVideoPickerPreviewDom(echo.container, echoedState);
assert.equal(echo.stage.image.getAttribute("src"), last);
assert.equal(echo.stage.image.srcWrites, 0);
const echoPending = echo.stage.created.at(-1);
assert.equal(echoPending.getAttribute("src"), first);
echoPending.emit("load");
echoPending.decoding.resolve();
await nextTick();
assert.equal(echo.stage.image, echoPending);

// Crop/concatenate tabs retain ownership of the viewport even if a Snapshot
// cursor is changed in Shot state.
const tool = makeFixture(last);
tool.container.__hmbVideoPickerExpanded = true;
const cropState = {
  active_picker_shot_uuid: "shot-1",
  video_tools_by_shot: { "shot-1": { active_tool: "crop" } },
};
picker.hmbApplySnapshotNavigationFeedback(tool.container, firstSnapshot, {}, 1, 24, cropState);
assert.equal(tool.stage.created.length, 0);
assert.equal(tool.stage.video.hidden, false);
// Progress may carry the previous Snapshot aliases while the interaction
// draft protects a newer cursor. Canonical immutable history must own both
// image and pass identity before the decode helper is given a source URL.
const roleHistory = ["original", "mask", "depth"].map((artifact_type, index) => ({
  snapshot_uid: `role-${artifact_type}`, artifact_type, snapshot_batch_uid: "batch-145",
  frame: 145, video_slot: 1, created_at_ms: index + 1,
  path: `C:/snapshot/${artifact_type}.png`, url: `file:///C:/snapshot/${artifact_type}.png`,
}));
for (const oldIndex of [0, 1, 2]) for (const newIndex of [0, 1, 2]) {
  if (oldIndex === newIndex) continue;
  const oldSnapshot = roleHistory[oldIndex], selected = roleHistory[newIndex];
  const oldState = { runtime_instance_id: "snapshot-cursor", scene_path: "C:/scene.mb",
    state_revision: 10, state_published_at_ms: 100, state_writer: "python",
    viewport_mode: "snapshot", snapshot_active: true, snapshots: roleHistory, videos: [],
    active_snapshot_uid: oldSnapshot.snapshot_uid, snapshot_frame: 145, snapshot_video_slot: 1,
    snapshot_path: oldSnapshot.path, snapshot_url: oldSnapshot.url };
  const localState = { ...oldState, state_revision: 11, state_published_at_ms: 200,
    state_writer: "widget", active_snapshot_uid: selected.snapshot_uid,
    snapshot_path: selected.path, snapshot_url: selected.url };
  const draftOwner = {};
  picker.hmbRememberPickerInteractionDraft(draftOwner, localState, oldState);
  picker.hmbStampPickerInteractionDraft(draftOwner, localState);
  // ACK the latest publication first, then deliver crossed old progress twice.
  picker.hmbProtectPickerInteractionDraft(draftOwner, { ...localState, state_writer: "python",
    frontend_seen_revision: 11 });
  for (const revision of [9, 10]) {
    const projected = picker.hmbProtectPickerInteractionDraft(draftOwner,
      { ...oldState, state_revision: revision, message: `Late progress ${revision}` });
    assert.equal(projected.state.active_snapshot_uid, selected.snapshot_uid);
    assert.equal(projected.state.snapshot_url, oldSnapshot.url, "This reproduces mixed stale scalar aliases.");
    const descriptor = picker.hmbVideoPickerPreviewDescriptor(projected.state);
    const normalized = picker.hmbVideoPickerMediaFrameContext(projected.state).state;
    assert.equal(descriptor.uid, selected.snapshot_uid);
    assert.equal(descriptor.url, selected.url, "The previous frame must not become the protected cursor's image.");
    assert.equal(normalized.snapshot_artifact_type, selected.artifact_type);
    assert.equal(normalized.message, `Late progress ${revision}`, "Backend status must remain live.");
    assert.deepEqual(normalized.snapshots.map(item => [item.snapshot_uid, item.url, item.artifact_type]),
      roleHistory.map(item => [item.snapshot_uid, item.url, item.artifact_type]), "Stale scalars cannot rewrite history.");
  }
}
// Old workflows with only scalar Snapshot fields still synthesize history.
const legacyDescriptor = picker.hmbVideoPickerPreviewDescriptor({ viewport_mode: "snapshot",
  snapshot_active: true, snapshot_video_slot: 1, snapshot_frame: 7,
  active_snapshot_uid: "legacy", snapshot_path: "C:/snapshot/legacy.png",
  snapshot_url: "file:///C:/snapshot/legacy.png", snapshots: [] });
assert.equal(legacyDescriptor.uid, "legacy");
assert.equal(legacyDescriptor.url, "file:///C:/snapshot/legacy.png");
console.log("Snapshot wrap, predecode, rapid clicks, video transition, Shot ownership, immutable history and failure: PASS");
