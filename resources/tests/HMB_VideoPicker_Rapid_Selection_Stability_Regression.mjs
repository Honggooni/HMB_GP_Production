import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);


class FakeClassList {
  constructor(...names) { this.names = new Set(names); }
  add(...names) { names.forEach((name) => this.names.add(name)); }
  remove(...names) { names.forEach((name) => this.names.delete(name)); }
  toggle(name, enabled) {
    if (enabled) this.names.add(name);
    else this.names.delete(name);
  }
  contains(name) { return this.names.has(name); }
}


class FakeControl {
  constructor(attributes = {}) {
    this.attributes = new Map(Object.entries(attributes));
    this.disabled = false;
    this.textContent = "Select";
  }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
}


class FakeCard {
  constructor(uid) {
    this.uid = uid;
    this.attributes = new Map([["data-video-uid", uid]]);
    this.classList = new FakeClassList("video-asset-card");
    this.selection = new FakeControl({ "data-toggle-video-uid": uid });
    this.play = new FakeControl({
      "data-play-video-uid": uid,
      "data-video-title": uid,
    });
    this.remove = new FakeControl({ "data-delete-video-uid": uid });
    this.ownerDocument = null;
  }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  querySelector(selector) {
    if (selector === "[data-toggle-video-uid]") return this.selection;
    if (selector === "[data-play-video-uid]") return this.play;
    if (selector === "[data-delete-video-uid]") return this.remove;
    return null;
  }
}


class FakeGrid {
  constructor(cards) { this.children = [...cards]; }
  querySelectorAll(selector) {
    return selector === "[data-video-uid]" ? [...this.children] : [];
  }
  insertBefore(card, current) {
    const oldIndex = this.children.indexOf(card);
    if (oldIndex >= 0) this.children.splice(oldIndex, 1);
    const targetIndex = current ? this.children.indexOf(current) : -1;
    if (targetIndex >= 0) this.children.splice(targetIndex, 0, card);
    else this.children.push(card);
  }
  appendChild(card) { this.insertBefore(card, null); }
}


const WORKSPACE_UUID = "70000000-0000-4000-8000-000000000001";
const uids = Array.from({ length: 10 }, (_unused, index) => `rapid-video-${index + 1}`);
const cards = uids.map((uid) => new FakeCard(uid));
const cardsByUid = new Map(cards.map((card) => [card.uid, card]));
const grid = new FakeGrid(cards);
const count = { textContent: "0/10" };
const shell = {
  style: {
    width: "1400px",
    minWidth: "760px",
    maxWidth: "none",
    height: "1200px",
    minHeight: "360px",
    maxHeight: "none",
    transform: "translate(11px, 17px)",
  },
};
const container = {
  style: {
    width: "100%",
    height: "100%",
    minHeight: "0px",
    maxHeight: "none",
    overflow: "visible",
  },
  attributes: new Map(),
  __reactFlowShell: shell,
  querySelectorAll(selector) {
    if (selector === "[data-picker-shot-row][data-picker-shot-layout='compact']") return [];
    return [];
  },
  querySelector(selector) {
    if (selector === ".video-asset-grid") return grid;
    if (selector === ".video-selected-count") return count;
    return null;
  },
  setAttribute(name, value) { this.attributes.set(name, String(value)); },
  removeAttribute(name) { this.attributes.delete(name); },
};


let state = {
  schema: "maya-video-picker-state",
  language: "en",
  active_picker_shot_uuid: WORKSPACE_UUID,
  picker_shots: [{
    workspace_uuid: WORKSPACE_UUID,
    number: 1,
    name: "Shot 1",
    revision: 0,
    bound_shot_uuid: "",
    video_asset_uids: [...uids],
    selected_video_uids: [],
    preview_video_uid: "",
    selected_video_slot: 1,
  }],
  videos: uids.map((uid, index) => ({
    video_uid: uid,
    source_uid: uid,
    picker_shot_uuid: WORKSPACE_UUID,
    label: uid,
    video_url: `file:///C:/media/${uid}.mp4`,
    selected: false,
    selection_order: 0,
    video_slot: 0,
    catalog_order: index + 1,
  })),
  selected_video_slot: 1,
  active_slot_count: 1,
  preview_video_uid: "",
  selected_video_uid: "",
};


const geometrySnapshot = () => JSON.stringify({
  container: container.style,
  shell: shell.style,
});
const initialGeometry = geometrySnapshot();

const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;
const originalSetTimeout = globalThis.setTimeout;
const originalClearTimeout = globalThis.clearTimeout;
const animationFrames = [];
const timers = new Map();
let nextHandle = 1;
globalThis.requestAnimationFrame = (callback) => {
  const handle = nextHandle++;
  animationFrames.push({ handle, callback, cancelled: false });
  return handle;
};
globalThis.cancelAnimationFrame = (handle) => {
  const frame = animationFrames.find((candidate) => candidate.handle === handle);
  if (frame) frame.cancelled = true;
};
globalThis.setTimeout = (callback, delay) => {
  const handle = nextHandle++;
  timers.set(handle, { callback, delay, cancelled: false });
  return handle;
};
globalThis.clearTimeout = (handle) => {
  const timer = timers.get(handle);
  if (timer) timer.cancelled = true;
};

try {
  const clicks = [
    ...uids,
    uids[1], uids[3], uids[5], uids[7], uids[9],
    uids[9], uids[7], uids[5], uids[3], uids[1],
  ];
  const expectedOrder = [];
  const publications = [];

  for (const uid of clicks) {
    const existingIndex = expectedOrder.indexOf(uid);
    if (existingIndex >= 0) expectedOrder.splice(existingIndex, 1);
    else expectedOrder.push(uid);

    state = widget.hmbToggleVideoAssetSelection(state, uid);
    const selected = widget.hmbApplySelectedVideoAssetOrderToDom(container, state);
    assert.deepEqual(selected, expectedOrder, "Immediate selected order diverged during rapid clicks.");

    // The visible card response must be synchronous, before either RAF or the
    // fallback timer has had a chance to publish through Griptape.
    for (const candidateUid of uids) {
      const selectedNow = expectedOrder.includes(candidateUid);
      const surface = cardsByUid.get(candidateUid).selection;
      assert.equal(surface.getAttribute("aria-pressed"), selectedNow ? "true" : "false");
      assert.equal(cardsByUid.get(candidateUid).classList.contains("selected"), selectedNow);
    }
    assert.equal(count.textContent, `${expectedOrder.length}/10`);
    assert.equal(geometrySnapshot(), initialGeometry, "Selection feedback mutated node geometry.");

    const stateAtClick = state;
    widget.hmbScheduleVideoPickerPaintFirstTask(
      container,
      "state-publication",
      () => publications.push(stateAtClick),
      120,
    );
  }

  assert.equal(publications.length, 0, "Publication ran before local DOM feedback could paint.");
  assert.equal(widget.hmbVideoPickerPaintFirstTaskPending(container, "state-publication"), true);
  assert.equal(
    animationFrames.filter((frame) => !frame.cancelled).length,
    1,
    "Twenty rapid selections must share one first-frame publication job.",
  );

  // The scheduler deliberately crosses two compositor frames. Run both and
  // verify that only the newest of twenty states reaches the transport.
  const firstFrame = animationFrames.find((frame) => !frame.cancelled);
  firstFrame.callback();
  const secondFrame = animationFrames.find(
    (frame) => !frame.cancelled && frame.handle !== firstFrame.handle,
  );
  assert.ok(secondFrame, "Second paint boundary was not scheduled.");
  secondFrame.callback();

  const finalExpected = [
    uids[0], uids[2], uids[4], uids[6], uids[8],
    uids[9], uids[7], uids[5], uids[3], uids[1],
  ];
  assert.deepEqual(expectedOrder, finalExpected);
  assert.equal(publications.length, 1, "Rapid selections were not coalesced to one publication.");
  assert.deepEqual(
    widget.hmbSelectedVideoAssets(publications[0]).map((item) => item.video_uid),
    finalExpected,
    "Coalesced publication did not contain the final user selection.",
  );
  assert.equal(widget.hmbVideoPickerPaintFirstTaskPending(container, "state-publication"), false);
  assert.equal(geometrySnapshot(), initialGeometry, "Published selection caused workspace jitter.");
} finally {
  globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
  globalThis.setTimeout = originalSetTimeout;
  globalThis.clearTimeout = originalClearTimeout;
}


console.log(
  "HMB VideoPicker rapid selection stability regression: PASS "
  + "(20 clicks, immediate DOM, one coalesced publication, zero geometry mutation)",
);
