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

assert.equal(typeof widget.hmbInstallVideoPickerMountedRootGuard, "function");
assert.equal(typeof widget.hmbSetVideoPickerNativeResizeLocked, "function");

const savedGlobals = Object.fromEntries([
  "MutationObserver", "requestAnimationFrame", "cancelAnimationFrame",
].map((name) => [name, globalThis[name]]));

const observers = [];
class TestMutationObserver {
  constructor(callback) {
    this.callback = callback;
    this.observed = [];
    this.disconnected = false;
    observers.push(this);
  }
  observe(target, options) { this.observed.push({ target, options }); }
  disconnect() { this.disconnected = true; }
  flush() { this.callback([], this); }
}

let frameId = 1;
const frames = new Map();
const requestFrame = (callback) => {
  const id = frameId++;
  frames.set(id, callback);
  return id;
};
const cancelFrame = (id) => frames.delete(id);
const flushOneFrame = () => {
  const pending = [...frames.entries()];
  frames.clear();
  pending.forEach(([_id, callback]) => callback(Date.now()));
};

try {
  globalThis.MutationObserver = TestMutationObserver;
  globalThis.requestAnimationFrame = requestFrame;
  globalThis.cancelAnimationFrame = cancelFrame;

  const container = {
    ownerDocument: { defaultView: { MutationObserver: TestMutationObserver } },
    parentElement: null,
    __hmbVideoPickerDeleted: false,
    __hmbVideoPickerViewTransition: false,
    mounted: true,
    querySelector(selector) {
      if (selector === ".hmbvp" || selector === ".hmbvp-clip") {
        return this.mounted ? { selector } : null;
      }
      return null;
    },
  };
  const cleanup = [];
  let recoveries = 0;
  const guard = widget.hmbInstallVideoPickerMountedRootGuard(
    container,
    cleanup,
    () => {
      recoveries += 1;
      container.mounted = true;
      return true;
    },
  );
  const lifecycleObserver = observers.find((observer) => observer.observed.some(
    ({ target, options }) => target === container && options?.childList === true,
  ));
  assert.ok(lifecycleObserver, "The live parameter container must be watched for host child replacement.");

  // Host replacement can occur while the compact/full function is still on
  // stack. The guard waits through that frame and rebuilds only after the
  // transition commits, without requiring a later controller.update().
  container.mounted = false;
  container.__hmbVideoPickerViewTransition = true;
  lifecycleObserver.flush();
  flushOneFrame();
  assert.equal(recoveries, 0);
  assert.equal(frames.size, 1, "An in-flight view swap retries after it settles.");
  container.__hmbVideoPickerViewTransition = false;
  flushOneFrame();
  assert.equal(recoveries, 1);
  assert.equal(container.mounted, true);

  // A later allocator wipe is independently recovered once and does not need
  // a state echo or another user double-click.
  container.mounted = false;
  lifecycleObserver.flush();
  flushOneFrame();
  assert.equal(recoveries, 2);
  assert.equal(container.mounted, true);

  guard.cleanup();
  assert.equal(lifecycleObserver.disconnected, true);
  container.mounted = false;
  lifecycleObserver.flush();
  flushOneFrame();
  assert.equal(recoveries, 2, "A deleted/unmounted node cannot be resurrected by a stale observer.");
  cleanup.forEach((callback) => callback());
} finally {
  for (const [name, value] of Object.entries(savedGlobals)) {
    if (value === undefined) delete globalThis[name];
    else globalThis[name] = value;
  }
}

function resizeLockHarness(exact = true) {
  const attributes = new Map();
  const listeners = [];
  const styleElement = {
    removed: false,
    setAttribute() {},
    remove() { this.removed = true; },
  };
  const head = { appendChild(element) { this.lastChild = element; } };
  const ownerDocument = {
    head,
    defaultView: {},
    createElement(name) { return name === "style" ? styleElement : null; },
  };
  const node = {
    ownerDocument,
    classList: { contains(name) { return exact && name === "react-flow__node"; } },
    hasAttribute(name) { return attributes.has(name); },
    getAttribute(name) { return attributes.get(name) || ""; },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    addEventListener(type, handler, options) { listeners.push([type, handler, options]); },
    removeEventListener(type, handler) {
      const index = listeners.findIndex((row) => row[0] === type && row[1] === handler);
      if (index >= 0) listeners.splice(index, 1);
    },
    contains() { return true; },
  };
  const container = {
    ownerDocument,
    closest(selector) { return selector === ".react-flow__node" ? node : null; },
    parentElement: node,
  };
  return { container, node, attributes, listeners, styleElement };
}

const exactLock = resizeLockHarness(true);
const unrelatedNode = resizeLockHarness(true);
assert.equal(widget.hmbSetVideoPickerNativeResizeLocked(exactLock.container, true), true);
assert.equal(exactLock.attributes.get("data-hmb-video-picker-resize-locked"), "true");
assert.equal(exactLock.listeners.length, 3);
assert.equal(unrelatedNode.attributes.size, 0, "A compact lock cannot mutate another React Flow node.");
assert.equal(widget.hmbSetVideoPickerNativeResizeLocked(exactLock.container, false), true);
assert.equal(exactLock.attributes.has("data-hmb-video-picker-resize-locked"), false);
assert.equal(exactLock.listeners.length, 0);
assert.equal(exactLock.styleElement.removed, true);

const inexactLock = resizeLockHarness(false);
assert.equal(widget.hmbSetVideoPickerNativeResizeLocked(inexactLock.container, true), false);
assert.equal(inexactLock.attributes.size, 0, "Resize lock must fail closed outside an exact .react-flow__node.");

const toggleStart = source.indexOf("const togglePickerView = () => {");
const toggleEnd = source.indexOf("const commandBridge = () => {", toggleStart);
assert.ok(toggleStart >= 0 && toggleEnd > toggleStart);
const toggleSource = source.slice(toggleStart, toggleEnd);
assert.equal(
  (toggleSource.match(/HMBVideoPickerLibraryWidget\(container, liveProps\)/g) || []).length,
  0,
  "A hybrid view transition must not recursively remount the widget factory.",
);
assert.doesNotMatch(
  toggleSource,
  /\bcleanup\(\)|replaceChildren|\.innerHTML\s*=/,
  "A hybrid view transition must retain the installed controller and listeners.",
);
assert.match(
  toggleSource,
  /hmbSetVideoPickerHybridView\(container, false,[\s\S]*?compactPickerMarkup/,
  "Expanded to compact must detach the expanded subtree and reveal the compact summary in place.",
);
assert.match(
  toggleSource,
  /hmbSetVideoPickerHybridView\(container, true,[\s\S]*?compactPickerMarkup/,
  "Compact to expanded must reattach the retained expanded subtree in place.",
);
assert.equal(
  (toggleSource.match(/hmbRequestVideoPickerNodeInternalsUpdate\(/g) || []).length,
  0,
  "A transition must never publish node internals synchronously against intermediate bounds.",
);
assert.equal(
  (toggleSource.match(/hmbScheduleVideoPickerNodeInternalsUpdate\(container, liveProps/g) || []).length,
  0,
  "Neither transition may schedule React Flow internals updates.",
);
assert.match(source, /hmbRememberVideoPickerViewMode\(container, storedViewMode !== false\)/);
assert.match(source, /const desiredPickerExpanded = container\.__hmbVideoPickerExpanded === true;/);
assert.match(source, /const pickerExpanded = true;/);
assert.doesNotMatch(source, /const pickerMarkup = pickerExpanded\s*\?/);
const finalCompactMount = source.lastIndexOf("if (!desiredPickerExpanded) {");
const finalExpandedDelegation = source.lastIndexOf("hmbInstallVideoAssetRootDelegation(");
assert.ok(
  finalCompactMount > finalExpandedDelegation,
  "A remembered compact mount may detach only after all expanded/direct listeners are installed.",
);
assert.match(
  source.slice(finalCompactMount),
  /hmbSetVideoPickerHybridView\(container, false, compactPickerMarkup\)[\s\S]*?installCompactModeInteractions\(\)/,
);
const recoveryStart = source.indexOf("recoverMissingMountedPicker = (nextProps = {}) => {");
const recoveryEnd = source.indexOf("const patchMountedPicker =", recoveryStart);
assert.match(
  source.slice(recoveryStart, recoveryEnd),
  /const liveExpanded = container\.__hmbVideoPickerExpanded === true;[\s\S]*?hmbRememberVideoPickerViewMode\(container, liveExpanded\)/,
  "Host root recovery must preserve the live compact/expanded choice instead of the mount-time full staging mode.",
);
assert.doesNotMatch(source, /<dialog\b|showModal\(|data-hmb-picker-expanded-surface/);
assert.match(source, /export function hmbSetVideoPickerHybridView\(/);
assert.match(source, /__hmbVideoPickerExpandedFragment/);
assert.match(source, /data-picker-compact-summary/);
assert.match(source, /const HMB_VIDEO_PICKER_HYBRID_GEOMETRY_PROPERTIES = Object\.freeze\(\[\s*"height",\s*"min-height",\s*"max-height",?\s*\]\)/);
assert.doesNotMatch(
  source.slice(
    source.indexOf("const HMB_VIDEO_PICKER_HYBRID_GEOMETRY_PROPERTIES"),
    source.indexOf("export function hmbRestoreVideoPickerExpandedGeometry"),
  ),
  /setProperty\?\.\(\s*["'](?:width|overflow|transform|translate|left|top)["']|fitView|zoom|updateNodeInternals|react-flow__viewport/i,
  "Hybrid geometry may mutate only the exact React Flow node's three vertical size properties.",
);
assert.doesNotMatch(
  source.slice(
    source.indexOf("const HMB_VIDEO_PICKER_GEOMETRY_PROPERTIES"),
    source.indexOf("const HMB_VIDEO_PICKER_RESIZE_LOCK_ATTRIBUTE"),
  ),
  /transform|translate|left|top/,
  "View restoration may resize the node but must never move its canvas position or viewport transform.",
);

console.log("HMB VideoPicker view-transition lifecycle regression: PASS");
