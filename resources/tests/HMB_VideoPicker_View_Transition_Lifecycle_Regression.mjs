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

const toggleStart = source.indexOf("const togglePickerView = () => {");
const toggleEnd = source.indexOf("const commandBridge = () => {", toggleStart);
assert.ok(toggleStart >= 0 && toggleEnd > toggleStart);
const toggleSource = source.slice(toggleStart, toggleEnd);
assert.equal(
  (toggleSource.match(/HMBVideoPickerLibraryWidget\(container, liveProps\)/g) || []).length,
  2,
  "Each direction remorphs the existing authored root exactly once.",
);
assert.doesNotMatch(
  toggleSource,
  /hmbDetachVideoPickerDom|hmbRestoreVideoPickerDom|__hmbVideoPickerExpandedCache|replaceChildren|\.innerHTML\s*=/,
  "Compact/full transitions must not detach, cache, or replace the widget root.",
);
assert.match(
  toggleSource,
  /container\.__hmbVideoPickerExpanded = false;\s*cleanup\(\);[\s\S]*?HMBVideoPickerLibraryWidget\(container, liveProps\)/,
  "Expanded to compact releases listeners and morphs the retained root.",
);
assert.match(
  toggleSource,
  /container\.__hmbVideoPickerExpanded = true;[\s\S]*?cleanup\(\);\s*HMBVideoPickerLibraryWidget\(container, liveProps\)/,
  "Compact to expanded releases compact sizing before morphing the retained root.",
);
assert.equal(
  (toggleSource.match(/hmbRequestVideoPickerNodeInternalsUpdate\(container, liveProps\)/g) || []).length,
  2,
  "Each direction sends one settled node-internals update instead of intermediate updates that can pan the canvas.",
);
assert.match(
  toggleSource,
  /HMBVideoPickerLibraryWidget\(container, liveProps\);\s*hmbSyncVideoPickerHostMeasurement\(container, liveProps\.value, false\);\s*hmbRequestVideoPickerNodeInternalsUpdate/,
  "Compact commits live DOM, measurement, then node internals.",
);
assert.match(
  toggleSource,
  /hmbApplyPickerHostSizing\(container, hmbPickerInnerRequiredHeight\(container\)\);[\s\S]*?hmbSyncVideoPickerHostMeasurement\(container, liveProps\.value, true\);\s*hmbRequestVideoPickerNodeInternalsUpdate/,
  "Expanded commits final geometry before measurement and node internals.",
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
