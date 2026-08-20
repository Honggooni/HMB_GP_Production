import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);


const shotA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const shotB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

function video(uid) {
  return {
    video_uid: uid,
    source_uid: uid,
    video_path: `C:/shots/${uid}.mp4`,
    label: uid,
  };
}

function shotLocalState() {
  return {
    videos: [video("video-a"), video("video-b"), video("video-c"), video("video-d")],
    picker_shots: [
      {
        workspace_uuid: shotA,
        number: 1,
        name: "Shot 1",
        video_asset_uids: ["video-a", "video-b", "video-c"],
        selected_video_uids: ["video-c", "video-a", "video-b"],
        preview_video_uid: "video-a",
      },
      {
        workspace_uuid: shotB,
        number: 2,
        name: "Shot 2",
        video_asset_uids: ["video-d"],
        selected_video_uids: ["video-d"],
        preview_video_uid: "video-d",
      },
    ],
    active_picker_shot_uuid: shotA,
    preview_video_uid: "video-a",
    selected_video_uid: "video-a",
  };
}


// A generator-order edit is Shot-local and cannot take over Preview/playback.
const initial = shotLocalState();
const moved = widget.hmbMoveSelectedVideoAsset(initial, "video-b", 0);
assert.deepEqual(
  widget.hmbSelectedVideoAssets(moved).map((item) => item.video_uid),
  ["video-b", "video-c", "video-a"],
);
assert.equal(moved.preview_video_uid, "video-a");
assert.equal(moved.selected_video_uid, "video-a");
assert.deepEqual(
  moved.picker_shots.find((row) => row.workspace_uuid === shotB).selected_video_uids,
  ["video-d"],
  "Reordering Shot 1 cannot mutate Shot 2.",
);
assert.deepEqual(
  moved.videos.map((item) => item.video_uid),
  initial.videos.map((item) => item.video_uid),
  "Reordering never mutates catalog ownership/order.",
);

// Compact renders selected_video_uids order, with visible slots renumbered
// left-to-right. It no longer falls back to video_asset_uids ownership order.
const compact = widget.hmbRenderVideoPickerShotWorkspace(moved, undefined, false, "compact").tabs;
const rowStart = compact.indexOf(`data-picker-shot-row="${shotA}"`);
const rowEnd = compact.indexOf(`data-picker-shot-row="${shotB}"`, rowStart);
const rowMarkup = compact.slice(rowStart, rowEnd);
const bIndex = rowMarkup.indexOf('data-video-uid="video-b"');
const cIndex = rowMarkup.indexOf('data-video-uid="video-c"');
const aIndex = rowMarkup.indexOf('data-video-uid="video-a"');
assert.ok(bIndex >= 0 && bIndex < cIndex && cIndex < aIndex);
assert.match(rowMarkup, /data-picker-shot-slot="1"[\s\S]*?data-video-uid="video-b"/);
assert.match(rowMarkup, /data-picker-shot-slot="2"[\s\S]*?data-video-uid="video-c"/);
assert.match(rowMarkup, /data-picker-shot-slot="3"[\s\S]*?data-video-uid="video-a"/);
assert.match(
  source,
  /desiredVideos\.forEach\(\(video, videoIndex\) => \{\s*const slot = videoIndex \+ 1;/,
  "Regional compact patches must renumber the reordered cards exactly like a full render.",
);


class ClassList {
  constructor(...names) { this.names = new Set(names); }
  add(...names) { names.forEach((name) => this.names.add(name)); }
  remove(...names) { names.forEach((name) => this.names.delete(name)); }
  contains(name) { return this.names.has(name); }
  toggle(name, enabled) { enabled ? this.add(name) : this.remove(name); }
}

class Card {
  constructor(uid, order) {
    this.attributes = new Map([
      ["data-video-uid", uid],
      ["data-selected-video-uid", uid],
      ["data-selected-video-order", String(order)],
      ["draggable", "true"],
    ]);
    this.classList = new ClassList("video-asset-card", "selected");
    this.badge = { textContent: String(order).padStart(2, "0") };
  }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  hasAttribute(name) { return this.attributes.has(name); }
  closest(selector) {
    if (selector === "[data-video-uid]") return this;
    if (selector === "[data-play-video-uid], [data-delete-video-uid]") return null;
    return null;
  }
  querySelector(selector) {
    if (selector === ".selected-video-order") return this.badge;
    return null;
  }
}

class Grid {
  constructor(cards) { this.children = [...cards]; }
  querySelectorAll(selector) { return selector === "[data-video-uid]" ? [...this.children] : []; }
  insertBefore(card, before) {
    this.children = this.children.filter((item) => item !== card);
    const index = before ? this.children.indexOf(before) : -1;
    if (index < 0) this.children.push(card);
    else this.children.splice(index, 0, card);
  }
  appendChild(card) { this.insertBefore(card, null); }
}

class Container {
  constructor(cards) {
    this.grid = new Grid(cards);
    this.listeners = new Map();
  }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }
  removeEventListener(type, handler) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter((item) => item !== handler));
  }
  querySelector(selector) { return selector === ".video-asset-grid" ? this.grid : null; }
  querySelectorAll(selector) {
    if (selector === "[data-video-uid]") return [...this.grid.children];
    if (selector === ".video-asset-card.drop-target") {
      return this.grid.children.filter((card) => card.classList.contains("drop-target"));
    }
    if (selector === ".video-asset-card.dragging") {
      return this.grid.children.filter((card) => card.classList.contains("dragging"));
    }
    return [];
  }
  contains(target) { return target === this || target === this.grid || this.grid.children.includes(target); }
  dispatch(type, event) { for (const handler of this.listeners.get(type) || []) handler(event); }
}

function dragEvent(target) {
  return {
    target,
    relatedTarget: null,
    dataTransfer: { setData() {}, effectAllowed: "none", dropEffect: "none" },
    preventDefault() {},
    stopPropagation() {},
  };
}

// A Shot switch during a native drag invalidates the session. It must never
// apply Shot 1's source/target indices to Shot 2.
{
  let live = shotLocalState();
  const cards = [new Card("video-c", 1), new Card("video-a", 2), new Card("video-b", 3)];
  const container = new Container(cards);
  let commits = 0;
  const cleanup = widget.hmbInstallVideoAssetDragReorder(container, {
    currentState: () => live,
    commitState: () => { commits += 1; },
  });
  container.dispatch("dragstart", dragEvent(cards[2]));
  container.dispatch("dragover", dragEvent(cards[0]));
  live = { ...live, active_picker_shot_uuid: shotB };
  container.dispatch("dragend", dragEvent(cards[2]));
  assert.equal(commits, 0);
  assert.equal(container.__hmbVideoDragSession, undefined);
  cleanup();
}

// A valid same-Shot drop commits once and retains the current Preview UID.
{
  let live = shotLocalState();
  const cards = [new Card("video-c", 1), new Card("video-a", 2), new Card("video-b", 3)];
  const container = new Container(cards);
  let commits = 0;
  const cleanup = widget.hmbInstallVideoAssetDragReorder(container, {
    currentState: () => live,
    commitState: (next) => { live = next; commits += 1; },
  });
  container.dispatch("dragstart", dragEvent(cards[2]));
  container.dispatch("dragover", dragEvent(cards[0]));
  container.dispatch("drop", dragEvent(cards[0]));
  container.dispatch("dragend", dragEvent(cards[2]));
  assert.equal(commits, 1);
  assert.deepEqual(
    widget.hmbSelectedVideoAssets(live).map((item) => item.video_uid),
    ["video-b", "video-c", "video-a"],
  );
  assert.equal(live.preview_video_uid, "video-a");
  cleanup();
}

console.log("HMB VideoPicker Shot-local reorder regression: PASS");
