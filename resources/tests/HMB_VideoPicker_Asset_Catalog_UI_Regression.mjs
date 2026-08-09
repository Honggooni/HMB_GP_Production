import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const imageAssetWidgetPath = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const imageAssetSource = fs.readFileSync(imageAssetWidgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);


function video(uid, path = `C:/shot/${uid}.mp4`) {
  return {
    video_uid: uid,
    source_uid: uid,
    video_path: path,
    label: uid,
    generation_role: "mask",
    selected: false,
    selection_order: 0,
  };
}


for (const helper of [
  "hmbSelectedVideoAssets",
  "hmbToggleVideoAssetSelection",
  "hmbMoveSelectedVideoAsset",
  "hmbApplySelectedVideoAssetOrderToDom",
  "hmbInstallVideoAssetDragReorder",
  "hmbPreviewVideoAsset",
  "hmbDeleteVideoAsset",
]) {
  assert.equal(
    typeof widget[helper],
    "function",
    `${helper} must remain an exported, directly testable UI state helper.`,
  );
}


// The catalog may grow past ten. Only the ordered generator selection is
// capped, and deselection never deletes the underlying card.
let state = {
  videos: Array.from({ length: 12 }, (_value, index) => (
    video(`video-${String(index + 1).padStart(2, "0")}`)
  )),
  preview_video_uid: "",
  selected_video_uid: "",
};
for (let index = 0; index < 10; index += 1) {
  state = widget.hmbToggleVideoAssetSelection(
    state,
    state.videos[index].video_uid,
  );
}
assert.deepEqual(
  widget.hmbSelectedVideoAssets(state).map((item) => item.video_uid),
  Array.from(
    { length: 10 },
    (_value, index) => `video-${String(index + 1).padStart(2, "0")}`,
  ),
);
assert.deepEqual(
  widget.hmbSelectedVideoAssets(state).map((item) => item.selection_order),
  Array.from({ length: 10 }, (_value, index) => index + 1),
);

const blockedAtTen = widget.hmbToggleVideoAssetSelection(state, "video-11");
assert.equal(blockedAtTen.videos.length, 12, "Selection capacity must not trim the catalog.");
assert.deepEqual(
  widget.hmbSelectedVideoAssets(blockedAtTen).map((item) => item.video_uid),
  widget.hmbSelectedVideoAssets(state).map((item) => item.video_uid),
  "Selecting an eleventh video is rejected without changing the ten selected UIDs.",
);
assert.equal(
  blockedAtTen.videos.find((item) => item.video_uid === "video-11").selected,
  false,
);

state = widget.hmbToggleVideoAssetSelection(state, "video-04");
assert.equal(state.videos.length, 12, "Deselecting keeps the video in current-cut history.");
assert.equal(widget.hmbSelectedVideoAssets(state).length, 9);
state = widget.hmbToggleVideoAssetSelection(state, "video-11");
assert.equal(widget.hmbSelectedVideoAssets(state).length, 10);
assert.equal(widget.hmbSelectedVideoAssets(state).at(-1).video_uid, "video-11");

const catalogUidsBeforeMove = state.videos.map((item) => item.video_uid);
state = widget.hmbMoveSelectedVideoAsset(state, "video-11", 0);
assert.equal(widget.hmbSelectedVideoAssets(state)[0].video_uid, "video-11");
assert.deepEqual(
  widget.hmbSelectedVideoAssets(state).map((item) => item.selection_order),
  Array.from({ length: 10 }, (_value, index) => index + 1),
  "Drag/arrow reordering compacts display order without changing stable UID identity.",
);
assert.deepEqual(
  state.videos.map((item) => item.video_uid),
  catalogUidsBeforeMove,
  "Reordering the selected tray must not reorder, delete, or recreate catalog cards.",
);


class FakeClassList {
  constructor(...names) {
    this.names = new Set(names);
  }

  add(...names) {
    names.forEach((name) => this.names.add(name));
  }

  remove(...names) {
    names.forEach((name) => this.names.delete(name));
  }

  contains(name) {
    return this.names.has(name);
  }
}


class FakeVideoCard {
  constructor(uid, order) {
    this.attributes = new Map([
      ["data-video-uid", uid],
      ["data-selected-video-uid", uid],
      ["data-selected-video-order", String(order)],
      ["draggable", "true"],
    ]);
    this.classList = new FakeClassList("video-asset-card", "selected");
    this.badge = { textContent: `@video${order}` };
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  closest(selector) {
    if (selector === "[data-video-uid]") return this;
    if (selector === "[data-play-video-uid], [data-delete-video-uid]") return null;
    return null;
  }

  querySelector(selector) {
    return selector === ".selected-video-order" ? this.badge : null;
  }
}


class FakeVideoGrid {
  constructor(cards) {
    this.children = [...cards];
  }

  querySelectorAll(selector) {
    return selector === "[data-video-uid]" ? [...this.children] : [];
  }

  appendChild(card) {
    this.children = this.children.filter((item) => item !== card);
    this.children.push(card);
    return card;
  }
}


class FakeDragContainer {
  constructor(cards) {
    this.grid = new FakeVideoGrid(cards);
    this.listeners = new Map();
  }

  addEventListener(name, handler, capture) {
    assert.equal(capture, true, `${name} must be delegated in capture phase.`);
    const handlers = this.listeners.get(name) || [];
    handlers.push(handler);
    this.listeners.set(name, handlers);
  }

  removeEventListener(name, handler, capture) {
    assert.equal(capture, true);
    this.listeners.set(name, (this.listeners.get(name) || []).filter((item) => item !== handler));
  }

  querySelector(selector) {
    return selector === ".video-asset-grid" ? this.grid : null;
  }

  querySelectorAll(selector) {
    const cards = [...this.grid.children];
    if (selector === "[data-video-uid]") return cards;
    if (selector === ".video-asset-card.drop-target") {
      return cards.filter((card) => card.classList.contains("drop-target"));
    }
    if (selector === ".video-asset-card.dragging") {
      return cards.filter((card) => card.classList.contains("dragging"));
    }
    return [];
  }

  contains(item) {
    return item === this || item === this.grid || this.grid.children.includes(item);
  }

  closest() {
    return null;
  }

  dispatch(name, event) {
    for (const handler of this.listeners.get(name) || []) handler(event);
  }
}


function fakeDragEvent(target, dataTransfer) {
  return {
    target,
    dataTransfer,
    relatedTarget: null,
    defaultPrevented: false,
    propagationStopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; },
  };
}


function fourVideoDragState() {
  return {
    videos: Array.from({ length: 4 }, (_value, index) => ({
      ...video(`drag-${index + 1}`),
      selected: true,
      selection_order: index + 1,
      video_slot: index + 1,
    })),
    preview_video_uid: "drag-1",
    selected_video_uid: "drag-1",
  };
}


function exerciseDelegatedDrag({ withDrop, remountBeforeFinish = false }) {
  let liveState = fourVideoDragState();
  const cards = Array.from({ length: 4 }, (_value, index) => new FakeVideoCard(`drag-${index + 1}`, index + 1));
  const container = new FakeDragContainer(cards);
  const commits = [];
  const install = () => widget.hmbInstallVideoAssetDragReorder(container, {
      currentState: () => liveState,
      commitState: (nextState, details) => {
        liveState = nextState;
        commits.push(details);
      },
    });
  let cleanup = install();
  const dataTransfer = {
    effectAllowed: "none",
    dropEffect: "none",
    payload: "",
    setData(_type, value) { this.payload = value; },
    getData() { return this.payload; },
  };
  container.dispatch("dragstart", fakeDragEvent(cards[3], dataTransfer));
  container.dispatch("dragover", fakeDragEvent(cards[0], dataTransfer));
  if (remountBeforeFinish) {
    cleanup();
    assert.equal(
      container.__hmbVideoDragSession?.targetUid,
      "drag-1",
      "A host widget remount must retain the in-flight source and last valid target.",
    );
    cleanup = install();
  }
  if (withDrop) container.dispatch("drop", fakeDragEvent(cards[0], dataTransfer));
  container.dispatch("dragend", fakeDragEvent(cards[3], dataTransfer));

  assert.equal(commits.length, 1, "A native drop plus dragend must commit exactly once.");
  assert.equal(commits[0].reason, withDrop ? "drop" : "dragend");
  assert.deepEqual(
    widget.hmbSelectedVideoAssets(liveState).map((item) => item.video_uid),
    ["drag-4", "drag-1", "drag-2", "drag-3"],
    "Moving selected video 4 onto video 1 must persist the exact 4,1,2,3 generator order.",
  );
  assert.deepEqual(
    container.grid.children.map((card) => card.getAttribute("data-video-uid")),
    ["drag-4", "drag-1", "drag-2", "drag-3"],
    "The optimistic keyed card DOM must show the committed order immediately.",
  );
  assert.deepEqual(
    container.grid.children.map((card) => card.badge.textContent),
    ["@video1", "@video2", "@video3", "@video4"],
  );
  cleanup();
}


exerciseDelegatedDrag({ withDrop: true, remountBeforeFinish: true });
exerciseDelegatedDrag({ withDrop: false, remountBeforeFinish: true });

// Leaving the selected-card area clears the last candidate. A later dragend
// must not accidentally apply an old hover position.
{
  let liveState = fourVideoDragState();
  const cards = Array.from({ length: 4 }, (_value, index) => new FakeVideoCard(`drag-${index + 1}`, index + 1));
  const container = new FakeDragContainer(cards);
  let commits = 0;
  const cleanup = widget.hmbInstallVideoAssetDragReorder(container, {
    currentState: () => liveState,
    commitState: (nextState) => { liveState = nextState; commits += 1; },
  });
  const dataTransfer = { setData() {}, dropEffect: "none", effectAllowed: "none" };
  container.dispatch("dragstart", fakeDragEvent(cards[3], dataTransfer));
  container.dispatch("dragover", fakeDragEvent(cards[0], dataTransfer));
  container.dispatch("dragover", fakeDragEvent(container, dataTransfer));
  container.dispatch("dragend", fakeDragEvent(cards[3], dataTransfer));
  assert.equal(commits, 0, "An invalid/outside final target must cancel the reorder fallback.");
  assert.deepEqual(
    widget.hmbSelectedVideoAssets(liveState).map((item) => item.video_uid),
    ["drag-1", "drag-2", "drag-3", "drag-4"],
  );
  cleanup();
}

const deleted = widget.hmbDeleteVideoAsset(state, "video-05");
assert.equal(deleted.videos.length, 11);
assert.equal(
  deleted.videos.some((item) => item.video_uid === "video-05"),
  false,
);
assert.deepEqual(
  deleted.videos.map((item) => item.video_uid),
  catalogUidsBeforeMove.filter((uid) => uid !== "video-05"),
  "Deleting one card removes only that UID and never renames or shifts another identity.",
);
assert.deepEqual(
  widget.hmbSelectedVideoAssets(deleted).map((item) => item.selection_order),
  Array.from({ length: 9 }, (_value, index) => index + 1),
  "Visible @video order compacts after deletion while stable catalog IDs remain intact.",
);

const previewed = widget.hmbPreviewVideoAsset(state, "video-07");
assert.equal(previewed.preview_video_uid, "video-07");
assert.equal(previewed.selected_video_uid, "video-07");
assert.equal(
  previewed.selected_video_path ?? previewed.video_path,
  "C:/shot/video-07.mp4",
  "The compatibility preview helper must still route the exact UID/path into the main viewport.",
);


// Inspect only the rendered main-dashboard template; helper definitions and
// style rules elsewhere in the source cannot accidentally satisfy layout order.
const mainStart = widgetSource.indexOf('<main class="main-grid">');
const mainEnd = widgetSource.indexOf("</main>", mainStart);
assert.ok(mainStart >= 0 && mainEnd > mainStart, "Picker main dashboard markup is present.");
const mainMarkup = widgetSource.slice(mainStart, mainEnd);
const paletteIndex = mainMarkup.indexOf('data-palette-kind="actor"');
const outlinerIndex = mainMarkup.indexOf('id="outliner-search"');
assert.ok(paletteIndex >= 0, "The compact Actor/Object Color Assignment palette remains available.");
assert.ok(outlinerIndex >= 0, "The asset-root Outliner remains available for cut authoring.");
assert.ok(
  paletteIndex < outlinerIndex,
  "Color Assignment palette must render directly above the Outliner instead of in the right stack.",
);

// Removed UI must be removed completely (markup, CSS, and dead click handlers),
// leaving the Outliner width/height for actual asset roots and eye controls.
for (const retiredPattern of [
  /class="scene-status\b|\.scene-status\{/,
  /class="legend\b|\.legend\{|\.legend-title\{|\.legend-grid\{|\.legend-item\{/,
  /assignmentHtml\s*\(|class="assignment-table\b|\.assignment-table\{/,
  /data-remove-binding=/,
  /id="clear-colors"|\.clear-colors\{/,
  /class="empty-assignment\b|\.empty-assignment\{/,
]) {
  assert.doesNotMatch(widgetSource, retiredPattern);
}
const outlinerPanelEnd = mainMarkup.indexOf("</section>", outlinerIndex);
const outlinerMarkup = mainMarkup.slice(outlinerIndex, outlinerPanelEnd);
assert.doesNotMatch(
  outlinerMarkup,
  /escapeHtml\(tr\.status\)/,
  "The Outliner column header must not reserve space for scene Status.",
);


// Current-cut history uses ImageAsset's card/tray visual language: selectable
// catalog cards, a visible @video order, and a glowing selected state.
assert.match(widgetSource, /class="video-asset-(?:grid|library)\b/);
assert.match(widgetSource, /class="video-asset-card[^"`]*\$\{[^}]*selected/);
assert.match(widgetSource, /data-video-uid=/);
assert.match(widgetSource, /class="selected-video-(?:tray|order)\b/);
assert.match(widgetSource, /data-selected-video-uid=/);
assert.match(widgetSource, /data-play-video-uid=/);
const importVideoInput = widgetSource.match(
  /<input\b[^>]*id="import-video-asset"[^>]*>/,
)?.[0] || "";
assert.ok(
  importVideoInput,
  "Current-cut history needs a header MP4 import control backed by a hidden file input.",
);
assert.match(importVideoInput, /type="file"/);
assert.match(importVideoInput, /hidden/);
assert.match(importVideoInput, /\bmultiple\b/);
assert.match(importVideoInput, /accept="[^"]*video\/mp4/);
assert.doesNotMatch(widgetSource, /files\?\.\[0\]/);
assert.match(widgetSource, /Array\.from\(event\.target\?\.files \|\| \[\]\)/);
assert.match(widgetSource, /dispatchCommand\("import_video_assets", \{[\s\S]*?sources,/);
const selectedVideoCardTags = widgetSource.match(
  /<[^>]*data-selected-video-uid=[^>]*>/g,
) || [];
assert.ok(
  selectedVideoCardTags.some((tag) => (
    /draggable="true"/.test(tag) || /draggable=\\"true\\"/.test(tag)
  )),
  "Selected cards must be draggable in their visible left-to-right/top-to-bottom order.",
);
assert.match(widgetSource, /data-delete-video-uid=/);
const thumbnailVideoTags = widgetSource.match(
  /<video\b[^>]*class="video-asset-thumb-media"[^>]*>/g,
) || [];
assert.ok(thumbnailVideoTags.length > 0, "Catalog cards need static video thumbnails.");
assert.ok(
  thumbnailVideoTags.every((tag) => /draggable="false"/.test(tag) && !/\bautoplay\b/.test(tag)),
  "Thumbnail media must stay paused and must not start a native media drag.",
);
assert.ok(
  (widgetSource.match(/<button\b[^>]*>/g) || []).some(
    (tag) => /class="video-asset-play"/.test(tag) && /data-play-video-uid=/.test(tag),
  ),
  "Only the centered transport button may route a catalog video into the main preview.",
);
assert.ok(
  (widgetSource.match(/<div\b[^>]*>/g) || []).every(
    (tag) => !/class="video-asset-thumb"/.test(tag) || !/data-play-video-uid=/.test(tag),
  ),
  "The thumbnail surface must remain available as the selected card's drag origin.",
);
assert.ok(
  (widgetSource.match(/<button\b[^>]*>/g) || []).some(
    (tag) => /data-delete-video-uid=/.test(tag),
  ),
  "Each catalog card needs its own delete action without renumbering stable UIDs.",
);

const cardTemplateStart = widgetSource.indexOf("function videoAssetCardsHtml(");
const cardTemplateEnd = widgetSource.indexOf(
  "export function hmbInstallPickerInteractionIsolation(",
  cardTemplateStart,
);
assert.ok(
  cardTemplateStart >= 0 && cardTemplateEnd > cardTemplateStart,
  "The current-cut video card template must remain directly inspectable.",
);
const cardTemplate = widgetSource.slice(cardTemplateStart, cardTemplateEnd);
assert.match(
  cardTemplate,
  /class="video-asset-copy" data-toggle-video-uid=[^>]*role="button"[^>]*tabindex=[^>]*aria-disabled=/,
  "The complete lower copy area must be the accessible UID selection surface.",
);
assert.doesNotMatch(
  cardTemplate,
  /class="video-asset-title"[^>]*data-toggle-video-uid=/,
  "Selection must no longer be limited to the title text.",
);
assert.match(
  cardTemplate,
  /\.sort\(\(left, right\) => \{[\s\S]*?leftOrder[\s\S]*?rightOrder[\s\S]*?return leftOrder - rightOrder/,
  "Selected cards must render in their mutable @video order before unselected history cards.",
);
assert.doesNotMatch(cardTemplate, /data-preview-video-uid=|\bpreviewing\b/);
assert.doesNotMatch(
  cardTemplate,
  /class="video-asset-footer\b|class="video-order-actions\b|tr\.previewLarge/,
  "Cards must not render the retired Large Preview or Select/Deselect footer area.",
);

const mainPreviewPlaybackStart = widgetSource.indexOf(
  'container.querySelectorAll("[data-play-video-uid]")',
  widgetSource.indexOf('on(container.querySelector("#import-video-asset"), "change"'),
);
const mainPreviewPlaybackEnd = widgetSource.indexOf(
  'container.querySelectorAll("[data-toggle-video-uid]")',
  mainPreviewPlaybackStart,
);
assert.ok(
  mainPreviewPlaybackStart >= 0 && mainPreviewPlaybackEnd > mainPreviewPlaybackStart,
  "The centered play controls must be wired before the lower selection surfaces.",
);
const mainPreviewPlaybackHandler = widgetSource.slice(
  mainPreviewPlaybackStart,
  mainPreviewPlaybackEnd,
);
assert.match(mainPreviewPlaybackHandler, /container\.querySelector\("#picker-video"\)/);
assert.match(mainPreviewPlaybackHandler, /container\.__hmbAutoplayVideoUid = uid/);
assert.match(mainPreviewPlaybackHandler, /container\.__hmbForceVideoPreviewUid = uid/);
assert.match(
  mainPreviewPlaybackHandler,
  /commit\(\{ \.\.\.hmbPreviewVideoAsset\(liveState, uid\), viewport_mode: "video" \}\)/,
  "A card play click must switch the shared viewport into video mode.",
);
assert.match(mainPreviewPlaybackHandler, /previewPlayer\.play\?\.\(\)/);
assert.doesNotMatch(
  mainPreviewPlaybackHandler,
  /video-asset-thumb-media|\bmedia\.play|\bmedia\.pause|\botherMedia\b/,
  "A catalog thumbnail must never be decoded as the playing media element.",
);
assert.doesNotMatch(widgetSource, /syncInlineVideoIndicator|toggleInlineVideo/);
assert.doesNotMatch(
  widgetSource,
  /\.video-asset-card\.is-playing\b/,
  "Main-preview playback must not add a second outer selection outline.",
);
assert.match(
  widgetSource,
  /\.video-asset-thumb\.is-playing \.video-asset-play\{/,
  "Only the centered transport indicator may mirror main-preview playing state.",
);

const selectionHandlerStart = widgetSource.indexOf(
  'container.querySelectorAll("[data-toggle-video-uid]")',
  mainPreviewPlaybackEnd,
);
const selectionHandlerEnd = widgetSource.indexOf(
  'container.querySelectorAll("[data-delete-video-uid]")',
  selectionHandlerStart,
);
assert.ok(selectionHandlerStart >= 0 && selectionHandlerEnd > selectionHandlerStart);
const selectionHandler = widgetSource.slice(selectionHandlerStart, selectionHandlerEnd);
assert.match(selectionHandler, /selectionSurface\.getAttribute\("aria-disabled"\) === "true"/);
assert.match(selectionHandler, /container\.__hmbSuppressVideoSelectionClick/);
assert.match(selectionHandler, /on\(selectionSurface, "click", toggleSelection\)/);
assert.match(selectionHandler, /on\(selectionSurface, "keydown"/);
assert.match(selectionHandler, /\["Enter", " "\]\.includes\(event\.key\)/);
assert.match(selectionHandler, /hmbToggleVideoAssetSelection\(liveState, uid\)/);
assert.match(
  widgetSource,
  /\.video-asset-delete\{top:7px;right:7px;bottom:auto;/,
  "The delete action must be pinned to the card's top-right corner.",
);
assert.match(
  widgetSource,
  /\.selected-video-order\{top:auto;right:7px;bottom:7px\}/,
  "The @video order badge must move to the thumbnail's bottom-right corner.",
);
assert.match(widgetSource, /data-resize-section="color"/);
assert.match(widgetSource, /container\.querySelectorAll\("\[data-resize-section\]"\)/);
assert.match(
  widgetSource,
  /\.video-assets-section>\.section-resize-handle\{border-top-color:transparent;background:transparent\}\.hmbvp\[data-theme\] \.video-assets-section>\.section-resize-handle:before\{display:none\}/,
  "The video section's bottom grip must be visually hidden without removing its resize hit area or handler.",
);

assert.match(widgetSource, /importVideoAsset: "Load"/);
assert.match(widgetSource, /TEXT\.ko\.importVideoAsset = "\\uAC80\\uC0C9";/);
assert.match(widgetSource, /class="import-video-icon"/);
assert.match(
  widgetSource,
  /\.generate-button,\.hmbvp\[data-theme\] \.import-video-button\{[^}]*border-color:var\(--hmb-primary-line\);[^}]*background:linear-gradient\(180deg,var\(--hmb-primary-top\),var\(--hmb-primary-bottom\)\)/s,
  "Load/Search must share the same primary color treatment as READ.",
);
for (const dragEvent of ["dragstart", "dragover", "drop", "dragend"]) {
  assert.match(
    widgetSource,
    new RegExp(`["']${dragEvent}["']`),
    `Selected video cards need a ${dragEvent} handler for direct order editing.`,
  );
}
const dragInstallerStart = widgetSource.indexOf(
  "export function hmbInstallVideoAssetDragReorder(",
);
const dragInstallerEnd = widgetSource.indexOf(
  "export function hmbPreviewVideoAsset(",
  dragInstallerStart,
);
assert.ok(dragInstallerStart >= 0 && dragInstallerEnd > dragInstallerStart);
const dragInstaller = widgetSource.slice(dragInstallerStart, dragInstallerEnd);
assert.match(
  dragInstaller,
  /closest\?\.\("\[data-play-video-uid\], \[data-delete-video-uid\]"\)/,
  "Only play/delete controls may veto a selected-card drag.",
);
assert.doesNotMatch(
  dragInstaller,
  /data-toggle-video-uid/,
  "Dragging from the complete lower selection surface must remain possible.",
);
assert.match(dragInstaller, /container\.__hmbSuppressVideoSelectionClick = true/);
assert.match(
  dragInstaller,
  /container\.addEventListener\(eventName, handler, true\)/,
  "Drag events must be delegated in capture phase so a card morph cannot discard the pending drop.",
);
assert.match(
  dragInstaller,
  /session\.targetUid = targetUid[\s\S]*?finalize\("drop"\)[\s\S]*?finalize\("dragend"\)/,
  "The last valid target must commit on drop or fall back to dragend.",
);
assert.match(
  dragInstaller,
  /hmbMoveSelectedVideoAsset\(liveState, sourceUid, targetIndex\)/,
);
assert.match(
  dragInstaller,
  /setTimeout\(\(\) => \{ delete container\.__hmbSuppressVideoSelectionClick; \}, 0\)/,
  "The click generated after a native drag must not deselect the moved card.",
);
assert.match(dragInstaller, /hmbApplySelectedVideoAssetOrderToDom\(container, nextState\)/);
assert.doesNotMatch(
  widgetSource,
  /on\(card, "(?:dragstart|dragover|drop|dragend)"/,
  "Per-card bubble handlers must not remain as a second, lossy reorder path.",
);
assert.match(widgetSource, /id="picker-video"/);
assert.match(widgetSource, /preview_video_uid/);
assert.match(
  widgetSource,
  /\.video-asset-card\.selected\{border-width:2px;[^}]*border-color:rgb\(var\(--selection-rgb\)\);[^}]*box-shadow:0 0 0 2px rgba\(var\(--selection-rgb\),\.82\),0 0 28px rgba\(var\(--selection-rgb\),\.62\)/,
  "Selected video cards need the requested thicker, stronger neon outline.",
);
assert.match(
  imageAssetSource,
  /\.asset-card\.selected\{[^}]*border-color:[^;}]+;[^}]*box-shadow:/s,
  "The reference Image Asset selection treatment must remain available.",
);
assert.match(
  widgetSource,
  /\.video-asset-card\{[^}]*border:[^;}]+;[^}]*background:/s,
  "Video history needs the same bordered card language as Image Asset.",
);
assert.match(
  widgetSource,
  /\.video-asset-grid\{[^}]*display:grid;[^}]*grid-template-columns:/s,
  "Selection order must be a visual grid read left-to-right and then top-to-bottom.",
);


console.log(
  "HMB VideoPicker asset-catalog UI regression: PASS "
  + "(main-preview playback, full copy selection, native drag order, neon outline, Load/Search styling)",
);
