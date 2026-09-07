import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const shot = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
class Element {
  constructor(attrs = {}) { this.attrs = { ...attrs }; this.hidden = false; this.style = {}; this.listeners = new Map(); this.classes = new Set(); this.classList = { add: (...keys) => keys.forEach((k) => this.classes.add(k)), remove: (...keys) => keys.forEach((k) => this.classes.delete(k)), contains: (k) => this.classes.has(k) }; }
  getAttribute(key) { return this.attrs[key] ?? null; }
  hasAttribute(key) { return Object.hasOwn(this.attrs, key); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  removeAttribute(key) { delete this.attrs[key]; }
  closest(selector) {
    if (selector.includes("data-picker-tool-source-uid")) return null;
    if (selector.includes(".video-asset-card[data-video-uid]") || selector.includes(".compact-shot-asset[data-video-uid]")) return this.card || (this.hasAttribute("data-video-uid") ? this : null);
    if (selector.includes("data-picker-tool-drop")) return this.hasAttribute("data-picker-tool-drop") ? this : null;
    if (selector.includes("data-play-video-uid")) return this.hasAttribute("data-play-video-uid") ? this : null;
    return null;
  }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  addEventListener(key, fn) { this.listeners.set(key, [...(this.listeners.get(key) || []), fn]); }
  removeEventListener(key, fn) { this.listeners.set(key, (this.listeners.get(key) || []).filter((item) => item !== fn)); }
  emit(key, target, dataTransfer) {
    const event = { target, dataTransfer, defaultPrevented: false, stopped: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, stopImmediatePropagation() { this.stopped = true; } };
    for (const listener of this.listeners.get(key) || []) { listener(event); if (event.stopped) break; }
    return event;
  }
}

function setup(count, mode, order = "tools-first", expanded = true) {
  const selected = ["a", "b", "c"].slice(0, count);
  let state = { runtime_instance_id: "native-owner", language: "en", active_picker_shot_uuid: shot, preview_video_uid: "a", selected_video_uid: "a", videos: ["a", "b", "c"].map((uid) => ({ video_uid: uid, video_path: `C:/source/${uid}.mp4`, video_url: `http://localhost/${uid}.mp4`, width: 800, height: 600 })), picker_shots: [{ workspace_uuid: shot, name: "Shot 1", number: 1, video_asset_uids: ["a", "b", "c"], selected_video_uids: selected, preview_video_uid: "a" }] };
  state = picker.hmbUpdatePickerVideoTools(state, (tools) => { tools.active_tool = mode; });
  const originalSelection = structuredClone(state.picker_shots), originalVideos = structuredClone(state.videos);
  const root = new Element(); root.__hmbVideoPickerExpanded = expanded;
  const cards = ["a", "b", "c"].map((uid) => new Element({ "data-video-uid": uid, "data-picker-shot-video-owner": shot, draggable: selected.includes(uid) && count > 1 ? "true" : "false", ...(selected.includes(uid) ? { "data-selected-video-uid": uid } : {}) }));
  const panel = new Element(), viewport = new Element(), stage = new Element();
  root.querySelector = (selector) => ({ "[data-picker-tools-panel]": panel, ".viewport-panel": viewport, ".viewport-stage": stage })[selector] || null;
  root.querySelectorAll = (selector) => selector === ".video-asset-card[data-video-uid]" || selector === "[data-video-uid]" ? cards : [];
  root.contains = (item) => cards.includes(item) || item === root;
  let toolCommits = 0, reorderCommits = 0, toolController, reorderCleanup;
  const installTools = () => { toolController = picker.hmbInstallPickerVideoTools(root, { currentState: () => state, commit(next) { state = next; toolCommits += 1; return { state }; } }); };
  const installReorder = () => { reorderCleanup = picker.hmbInstallVideoAssetDragReorder(root, { currentState: () => state, commitState(next) { state = next; reorderCommits += 1; } }); };
  if (order === "tools-first") { installTools(); installReorder(); } else { installReorder(); installTools(); }
  const transfer = () => ({ effectAllowed: "none", dropEffect: "none", data: new Map(), setData(k, value) { this.data.set(k, value); }, getData(k) { return this.data.get(k) || ""; } });
  return { root, cards, transfer, originalSelection, originalVideos, state: () => state, counts: () => ({ toolCommits, reorderCommits }), cleanup() { toolController.cleanup(); reorderCleanup(); } };
}

// Exercise the real two controllers together, not only their pure state helper.
// Registration order, selected count, and thumb play child must not change drag
// ownership or accidentally copy all selected cards into an independent tool.
let scenarios = 0;
for (const count of [0, 1, 2, 3]) for (const mode of ["concatenate", "crop"]) for (const order of ["tools-first", "reorder-first"]) for (const surface of ["card", "play-child"]) {
  const test = setup(count, mode, order);
  const card = test.cards[1], child = new Element({ "data-play-video-uid": "b" }); child.card = card;
  assert.equal(card.getAttribute("draggable"), "true");
  const dt = test.transfer(), start = test.root.emit("dragstart", surface === "card" ? card : child, dt);
  assert.equal(start.defaultPrevented, false, `${count} selected ${surface}: native drag must not be cancelled.`);
  assert.equal(dt.effectAllowed, "copyMove", "Loader reorder must not overwrite the tool's allowed copy operation.");
  assert.equal(dt.getData("application/x-hmb-picker-tool-source"), "b");
  assert.equal(test.root.__hmbVideoDragSession, undefined);
  const drop = new Element({ "data-picker-tool-drop": mode });
  assert.equal(test.root.emit("dragover", drop, dt).defaultPrevented, true);
  assert.equal(dt.dropEffect, "copy");
  test.root.emit("drop", drop, dt); test.root.emit("dragend", card, dt);
  assert.deepEqual(test.counts(), { toolCommits: 1, reorderCommits: 0 });
  const tools = test.state().video_tools_by_shot[shot];
  if (mode === "concatenate") { assert.deepEqual(tools.concatenate.input_uids, ["b"]); assert.deepEqual(tools.concatenate.inputs, ["C:/source/b.mp4"]); assert.equal(tools.crop.input, ""); }
  else { assert.equal(tools.crop.source_uid, "b"); assert.equal(tools.crop.input, "C:/source/b.mp4"); assert.deepEqual(tools.concatenate.inputs, []); }
  assert.deepEqual(test.state().picker_shots, test.originalSelection);
  assert.deepEqual(test.state().videos, test.originalVideos);
  assert.equal(test.state().preview_video_uid, "a");
  test.cleanup(); scenarios += 1;
}

// Tool drag handlers are transparent to ordinary selected-card reorder both in
// expanded Video Output mode and the compact Loader mode.
for (const expanded of [true, false]) {
  const test = setup(2, "preview", "tools-first", expanded), dt = test.transfer();
  assert.equal(test.root.emit("dragstart", test.cards[1], dt).defaultPrevented, false);
  assert.equal(dt.effectAllowed, "move");
  test.root.emit("dragover", test.cards[0], dt); test.root.emit("drop", test.cards[0], dt); test.root.emit("dragend", test.cards[1], dt);
  assert.deepEqual(test.counts(), { toolCommits: 0, reorderCommits: 1 });
  assert.deepEqual(test.state().picker_shots[0].selected_video_uids, ["b", "a"]);
  assert.deepEqual(test.state().video_tools_by_shot[shot].concatenate.inputs, []);
  test.cleanup(); scenarios += 1;
}
console.log(`PASS: ${scenarios} native tool-card drag ownership cases; exact one card, 0/1/2/3 selected, both listener orders, play child, compact/expanded reorder.`);
