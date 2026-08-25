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

const shotUuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function video(uid) {
  return {
    video_uid: uid,
    source_uid: uid,
    video_path: `C:/shots/${uid}.mp4`,
    label: uid,
  };
}

function stateWithOrder(order = ["video-a", "video-b"]) {
  return {
    shot_uuid: shotUuid,
    shot_number: 1,
    shot_name: "Shot 1",
    videos: [video("video-a"), video("video-b")],
    picker_shots: [{
      workspace_uuid: shotUuid,
      bound_shot_uuid: "",
      number: 1,
      name: "Shot 1",
      video_asset_uids: ["video-a", "video-b"],
      selected_video_uids: [...order],
      preview_video_uid: "video-a",
    }],
    active_picker_shot_uuid: shotUuid,
    preview_video_uid: "video-a",
    selected_video_uid: "video-a",
  };
}

// A decoded frame plus an interrupted or policy-blocked play() is not a broken
// MP4. Only the native media error path may show the red load-failure overlay.
assert.equal(
  widget.hmbVideoPickerPlaybackFailureKind({ name: "AbortError" }),
  "interrupted",
);
assert.equal(
  widget.hmbVideoPickerPlaybackFailureKind({ name: "NotAllowedError" }),
  "playback-blocked",
);
assert.equal(
  widget.hmbVideoPickerPlaybackFailureKind(
    new Error("transient play rejection"),
    { readyState: 2, currentSrc: "http://localhost/video.mp4", error: null },
  ),
  "playback-only",
);
assert.equal(
  widget.hmbVideoPickerPlaybackFailureKind(
    { name: "NotSupportedError" },
    { readyState: 0, currentSrc: "http://localhost/video.mp4", error: { code: 4 } },
  ),
  "media-error",
);

// Selection/reorder metadata cannot be part of compact card identity. Keeping
// the physical card alive prevents blink, preserves native drag, and lets the
// local DOM updater patch order in place.
const compactAB = widget.hmbRenderVideoPickerShotWorkspace(
  stateWithOrder(["video-a", "video-b"]),
  undefined,
  false,
  "compact",
).tabs;
const compactBA = widget.hmbRenderVideoPickerShotWorkspace(
  stateWithOrder(["video-b", "video-a"]),
  undefined,
  false,
  "compact",
).tabs;
function compactCardTag(markup, uid) {
  return markup.match(new RegExp(`<article[^>]*data-video-uid="${uid}"[^>]*>`))?.[0] || "";
}
function compactFingerprint(markup, uid) {
  return compactCardTag(markup, uid).match(/data-compact-video-fingerprint="([^"]+)"/)?.[1] || "";
}
assert.ok(compactFingerprint(compactAB, "video-a"));
assert.equal(
  compactFingerprint(compactAB, "video-a"),
  compactFingerprint(compactBA, "video-a"),
  "Changing selected order must not replace the compact card DOM.",
);
assert.match(
  compactAB,
  /<div class="compact-video-select-label"[^>]*role="button"/,
  "The compact card name must remain a keyboard-accessible selection surface without blocking parent drag.",
);
assert.doesNotMatch(compactAB, /<button[^>]*class="compact-video-select-label"/);
assert.match(
  source,
  /card\.setAttribute\?\.\([\s\S]*?"aria-label",[\s\S]*?workspace\.name[\s\S]*?index \+ 1/,
  "In-place compact reorder must refresh the card's accessible slot label.",
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
      ["data-picker-shot-video-owner", shotUuid],
      ["draggable", "true"],
    ]);
    this.classList = new ClassList("compact-shot-asset", "selected");
    this.badge = { textContent: String(order).padStart(2, "0") };
  }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  hasAttribute(name) { return this.attributes.has(name); }
  closest(selector) {
    if (selector === ".video-asset-card[data-video-uid], .compact-shot-asset[data-video-uid]") return this;
    if (selector === "[data-picker-shot-row]") return null;
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
    if (selector === ".video-asset-card.drop-target, .compact-shot-asset.drop-target") {
      return this.grid.children.filter((card) => card.classList.contains("drop-target"));
    }
    if (selector === ".video-asset-card.dragging, .compact-shot-asset.dragging") {
      return this.grid.children.filter((card) => card.classList.contains("dragging"));
    }
    return [];
  }
  contains(target) { return target === this || this.grid.children.includes(target); }
  dispatch(type, event) { for (const handler of this.listeners.get(type) || []) handler(event); }
}

function dragEvent(target) {
  const event = {
    target,
    relatedTarget: null,
    preventDefaultCount: 0,
    stopPropagationCount: 0,
    dataTransfer: { setData() {}, effectAllowed: "none", dropEffect: "none" },
    preventDefault() { this.preventDefaultCount += 1; },
    stopPropagation() { this.stopPropagationCount += 1; },
  };
  return event;
}

// Compact and expanded drag controllers are retained together. The inactive,
// locked controller must be completely transparent to the active controller.
{
  let live = stateWithOrder(["video-a", "video-b"]);
  const cards = [new Card("video-a", 1), new Card("video-b", 2)];
  const container = new Container(cards);
  let commits = 0;
  const inactiveCleanup = widget.hmbInstallVideoAssetDragReorder(container, {
    enabled: () => false,
    locked: () => true,
    currentState: () => live,
    commitState: () => { throw new Error("inactive drag controller committed"); },
  });
  const activeCleanup = widget.hmbInstallVideoAssetDragReorder(container, {
    enabled: () => true,
    locked: () => false,
    currentState: () => live,
    commitState: (next) => { live = next; commits += 1; },
  });
  const start = dragEvent(cards[1]);
  container.dispatch("dragstart", start);
  assert.equal(start.preventDefaultCount, 0, "The inactive controller must not cancel native dragstart.");
  assert.equal(container.__hmbVideoDragSession?.sourceUid, "video-b");
  const retainedSession = container.__hmbVideoDragSession;
  const lateInactiveCleanup = widget.hmbInstallVideoAssetDragReorder(container, {
    enabled: () => false,
    locked: () => true,
    currentState: () => live,
    commitState: () => { throw new Error("late inactive drag controller committed"); },
  });
  assert.strictEqual(
    container.__hmbVideoDragSession,
    retainedSession,
    "Mounting an inactive controller during a drag must preserve the active session.",
  );
  container.dispatch("dragover", dragEvent(cards[0]));
  container.dispatch("drop", dragEvent(cards[0]));
  container.dispatch("dragend", dragEvent(cards[1]));
  assert.equal(commits, 1);
  assert.deepEqual(
    live.picker_shots[0].selected_video_uids,
    ["video-b", "video-a"],
  );
  lateInactiveCleanup();
  activeCleanup();
  inactiveCleanup();
}

// A selection update writes both the mounted view and the retained detached
// view before a user switches modes, so the next view cannot reveal stale USE
// order while waiting for a host echo.
{
  const mounted = new Container([new Card("video-a", 1), new Card("video-b", 2)]);
  const compactFragment = new Container([new Card("video-a", 1), new Card("video-b", 2)]);
  const expandedFragment = new Container([new Card("video-a", 1), new Card("video-b", 2)]);
  mounted.__hmbVideoPickerCompactFragment = compactFragment;
  mounted.__hmbVideoPickerExpandedFragment = expandedFragment;
  widget.hmbApplySelectedVideoAssetOrderToDom(
    mounted,
    stateWithOrder(["video-b", "video-a"]),
  );
  for (const target of [mounted, compactFragment, expandedFragment]) {
    assert.deepEqual(
      target.grid.children.map((card) => card.getAttribute("data-video-uid")),
      ["video-b", "video-a"],
    );
    assert.deepEqual(
      target.grid.children.map((card) => card.getAttribute("data-selected-video-order")),
      ["1", "2"],
    );
  }
}

// Top-bar output synchronization must not rewrite already-correct checkbox
// properties; property churn itself causes visible check/uncheck flashes.
{
  class Toggle {
    constructor(checked = false, disabled = false) {
      this._checked = checked;
      this._disabled = disabled;
      this.checkedWrites = 0;
      this.disabledWrites = 0;
    }
    get checked() { return this._checked; }
    set checked(value) { this._checked = !!value; this.checkedWrites += 1; }
    get disabled() { return this._disabled; }
    set disabled(value) { this._disabled = !!value; this.disabledWrites += 1; }
  }
  const controls = new Map([
    ["#original-preview-toggle", new Toggle(false)],
    ["#mask-playblast-toggle", new Toggle(true)],
    ["#depth-playblast-toggle", new Toggle(false)],
    ["#motion-guide-toggle", new Toggle(false)],
  ]);
  const container = { querySelector: (selector) => controls.get(selector) || null };
  const choices = {
    original_enabled: false,
    mask_enabled: true,
    depth_enabled: false,
    motion_guide_enabled: false,
  };
  assert.equal(widget.hmbApplyPickerOutputChoicesToDom(container, choices, false), false);
  assert.equal([...controls.values()].reduce((sum, control) => sum + control.checkedWrites, 0), 0);
  assert.equal([...controls.values()].reduce((sum, control) => sum + control.disabledWrites, 0), 0);
  assert.equal(widget.hmbApplyPickerOutputChoicesToDom(
    container,
    { ...choices, depth_enabled: true },
    false,
  ), true);
  assert.equal(controls.get("#depth-playblast-toggle").checkedWrites, 1);
  assert.equal([...controls.values()].reduce((sum, control) => sum + control.checkedWrites, 0), 1);
}

console.log("HMB VideoPicker media, mode-sync, checkbox, and compact-drag stability regression: PASS");
