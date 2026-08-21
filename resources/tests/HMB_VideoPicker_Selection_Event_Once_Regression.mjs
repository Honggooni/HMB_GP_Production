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


class FakeContainer {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(handler);
  }

  removeEventListener(type, handler) {
    this.listeners.get(type)?.delete(handler);
  }

  contains(target) {
    return Boolean(target?.ownedByPicker);
  }

  dispatch(type, event) {
    for (const handler of this.listeners.get(type) || []) handler(event);
  }
}


function selectionSurface(tagName = "BUTTON") {
  return {
    tagName,
    ownedByPicker: true,
    closest(selector) {
      return selector === "[data-toggle-video-uid]" ? this : null;
    },
  };
}


assert.equal(typeof widget.hmbInstallVideoAssetRootDelegation, "function");
const container = new FakeContainer();
const cleanupA = [];
const cleanupB = [];
let selectionCount = 0;
const handlers = { select: () => { selectionCount += 1; } };

// A stale delegate can coexist briefly while the widget changes compact/full
// view. One physical click must still mutate selection exactly once.
assert.equal(widget.hmbInstallVideoAssetRootDelegation(container, handlers, cleanupA), true);
assert.equal(widget.hmbInstallVideoAssetRootDelegation(container, handlers, cleanupB), true);
const button = selectionSurface("BUTTON");
container.dispatch("click", { target: button });
assert.equal(selectionCount, 1, "One click must produce one selection mutation.");

// Native buttons synthesize a click for Enter/Space. The keydown delegate must
// not toggle first and then let that browser click toggle a second time.
container.dispatch("keydown", {
  target: button,
  key: "Enter",
  repeat: false,
  preventDefault() { throw new Error("Native button keydown must remain native."); },
});
assert.equal(selectionCount, 1);
container.dispatch("click", { target: button });
assert.equal(selectionCount, 2, "The native keyboard-generated click selects once.");

// A non-button accessibility surface has no native synthesized click and is
// therefore handled by the delegated keydown, still exactly once.
const roleSurface = selectionSurface("DIV");
let prevented = false;
container.dispatch("keydown", {
  target: roleSurface,
  key: " ",
  repeat: false,
  preventDefault() { prevented = true; },
});
assert.equal(prevented, true);
assert.equal(selectionCount, 3);

// The retained hybrid installs both delegates. The inactive expanded delegate
// is registered first on a compact mount, but it must not consume the event
// before the compact delegate can perform the one real mutation.
const hybridContainer = new FakeContainer();
const hybridCleanup = [];
let expanded = false;
let expandedSelections = 0;
let compactSelections = 0;
widget.hmbInstallVideoAssetRootDelegation(hybridContainer, {
  enabled: () => expanded,
  select: () => { expandedSelections += 1; },
}, hybridCleanup);
widget.hmbInstallVideoAssetRootDelegation(hybridContainer, {
  enabled: () => !expanded,
  select: () => { compactSelections += 1; },
}, hybridCleanup);
hybridContainer.dispatch("click", { target: selectionSurface("BUTTON") });
assert.equal(expandedSelections, 0);
assert.equal(compactSelections, 1, "The active compact delegate must receive exactly one click.");
expanded = true;
hybridContainer.dispatch("click", { target: selectionSurface("BUTTON") });
assert.equal(expandedSelections, 1, "The active expanded delegate must receive exactly one click.");
assert.equal(compactSelections, 1);

cleanupA.forEach((cleanup) => cleanup());
cleanupB.forEach((cleanup) => cleanup());
hybridCleanup.forEach((cleanup) => cleanup());
console.log("HMB VideoPicker selection event once regression: PASS");
