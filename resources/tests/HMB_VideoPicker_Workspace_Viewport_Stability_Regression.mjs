import assert from "node:assert/strict";
import fs from "node:fs";

const widgetSource = fs.readFileSync(
  new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url),
  "utf8",
);
const picker = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);
const pythonSource = fs.readFileSync(
  new URL("../../HMBVideoPickerLibrary.py", import.meta.url),
  "utf8",
);

for (const exportedName of [
  "hmbApplyVideoPickerCompactHostSizing",
  "hmbCancelVideoPickerNodeInternalsUpdate",
  "hmbRememberVideoPickerViewMode",
  "hmbScheduleVideoPickerNodeInternalsUpdate",
  "hmbVideoPickerNodeIdentity",
  "hmbVideoPickerStoredViewMode",
]) {
  assert.equal(typeof picker[exportedName], "function", `${exportedName} must remain exported.`);
}

// The Python constructor must migrate v3's full-view 1400x1200 metadata before
// DataNode/React Flow can observe it.  The browser harness below therefore
// begins every compact mount at the one canonical 1400x360 outer geometry.
assert.match(pythonSource, /PICKER_START_WIDTH\s*=\s*1400/);
assert.match(pythonSource, /PICKER_START_HEIGHT\s*=\s*1200/);
assert.match(pythonSource, /PICKER_NATIVE_SIZE_VERSION\s*=\s*4/);
assert.match(pythonSource, /PICKER_COMPACT_NATIVE_HEIGHT\s*=\s*360/);
assert.match(
  pythonSource,
  /prepared_metadata\["size"\]\s*=\s*dict\(compact_size\)[\s\S]*?prepared_kwargs\["metadata"\]\s*=\s*prepared_metadata[\s\S]*?super\(\)\.__init__\(\*\*prepared_kwargs\)/,
  "v3 geometry must be rewritten before super().__init__ publishes it to the host.",
);
const migrationBody = pythonSource.match(
  /def _restored_picker_native_geometry\([\s\S]*?\n\s*return compact_size, expanded_size, not canonical/,
)?.[0] || "";
assert.match(migrationBody, /raw_size\s*=\s*metadata\.get\("size"\)/);
assert.match(migrationBody, /expanded_size\s*=\s*raw_expanded_size\s+or\s+saved_expanded_size/);
assert.match(
  migrationBody,
  /compact_size\s*=\s*\{[\s\S]*?"width": PICKER_START_WIDTH,[\s\S]*?"height": PICKER_COMPACT_NATIVE_HEIGHT/,
);

const transitionSource = widgetSource.match(
  /const togglePickerView = \(\) => \{[\s\S]*?\n  const commandBridge =/,
)?.[0] || "";
assert.ok(transitionSource, "compact/full transition implementation must remain auditable");
assert.match(
  transitionSource,
  /hmbRestoreVideoPickerExpandedGeometry\(\s*container,\s*container\.__hmbVideoPickerCompactOuterGeometry,\s*\{ shellOnly: true \},\s*\)/,
  "compact entry must restore the saved compact outer shell before remount",
);
const captureCompactOuterIndex = transitionSource.indexOf(
  "container.__hmbVideoPickerCompactOuterGeometry = hmbCaptureVideoPickerExpandedGeometry(container)",
);
const rememberExpandedIndex = transitionSource.indexOf(
  "hmbRememberVideoPickerViewMode(container, true)",
);
assert.ok(captureCompactOuterIndex >= 0, "expand must capture the current compact outer geometry");
assert.ok(
  captureCompactOuterIndex < rememberExpandedIndex,
  "compact outer geometry must be captured before expanded mode changes shell ownership",
);

// Minimal v3 fixture oracle. The source assertions above bind this behavior to
// production; this object is what the simulated React Flow host is permitted to
// observe on cold load.
const v3Metadata = {
  size: { width: 1400, height: 1200 },
  hmb_picker_native_size_version: 3,
};
const migratedMetadata = {
  ...v3Metadata,
  size: { width: 1400, height: 360 },
  hmb_picker_expanded_size: { ...v3Metadata.size },
  hmb_picker_native_size_version: 4,
};
assert.deepEqual(migratedMetadata.size, { width: 1400, height: 360 });
assert.deepEqual(migratedMetadata.hmb_picker_expanded_size, { width: 1400, height: 1200 });

function fakeStyle(initial = {}) {
  const style = { ...initial };
  const camel = (name) => String(name).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
  style.getPropertyValue = (name) => String(style[camel(name)] || "");
  style.getPropertyPriority = () => "";
  style.setProperty = (name, value) => { style[camel(name)] = String(value); };
  style.removeProperty = (name) => { delete style[camel(name)]; };
  return style;
}

function fakeClassList(values = []) {
  const items = new Set(values);
  return {
    add(...names) { names.forEach((name) => items.add(name)); },
    remove(...names) { names.forEach((name) => items.delete(name)); },
    contains(name) { return items.has(name); },
  };
}

function frameClock() {
  let nextHandle = 1;
  let callbacks = new Map();
  return {
    request(callback) {
      const handle = nextHandle++;
      callbacks.set(handle, callback);
      return handle;
    },
    cancel(handle) { callbacks.delete(handle); },
    flushFrame() {
      const current = callbacks;
      callbacks = new Map();
      for (const callback of current.values()) callback(performance.now());
    },
    flushSettled() {
      this.flushFrame();
      this.flushFrame();
    },
    get pending() { return callbacks.size; },
  };
}

function fakeDocument(clock) {
  const view = {
    requestAnimationFrame: clock.request.bind(clock),
    cancelAnimationFrame: clock.cancel.bind(clock),
    getComputedStyle(element) {
      return {
        display: element?.__computedDisplay || "block",
        visibility: element?.__computedVisibility || "visible",
        flexDirection: "column",
        gridTemplateColumns: "none",
        position: "static",
        paddingBottom: "0",
        borderBottomWidth: "0",
      };
    },
  };
  return {
    body: {},
    documentElement: {},
    head: { appendChild() {} },
    defaultView: view,
    createElement() {
      const attributes = new Map();
      return {
        style: fakeStyle(),
        dataset: {},
        textContent: "",
        setAttribute(name, value) { attributes.set(name, String(value)); },
        getAttribute(name) { return attributes.get(name) || ""; },
        remove() {},
      };
    },
  };
}

function cloneProbeElement(document, options = {}) {
  const attributes = new Map(Object.entries(options.attributes || {}));
  return {
    parentElement: options.parentElement || null,
    ownerDocument: document,
    className: (options.classes || []).join(" "),
    classList: fakeClassList(options.classes || []),
    dataset: {},
    hidden: options.hidden === true,
    style: fakeStyle(options.style || {}),
    __computedDisplay: options.computedDisplay || "block",
    __computedVisibility: options.computedVisibility || "visible",
    getAttribute(name) { return attributes.get(name) || ""; },
    hasAttribute(name) { return attributes.has(name); },
    setAttribute(name, value) { attributes.set(name, String(value)); },
  };
}

function numberFromStyle(style, property, fallback) {
  const value = Number.parseFloat(style[property] || "");
  return Number.isFinite(value) ? value : fallback;
}

function makeShell(document, nodeId, size = migratedMetadata.size) {
  const attributes = new Map([["data-id", nodeId]]);
  const shell = {
    className: "react-flow__node",
    classList: fakeClassList(["react-flow__node"]),
    dataset: {},
    ownerDocument: document,
    style: fakeStyle({
      width: `${size.width}px`,
      height: `${size.height}px`,
      minHeight: `${size.height}px`,
      maxHeight: `${size.height}px`,
    }),
    getAttribute(name) { return attributes.get(name) || ""; },
    hasAttribute(name) { return attributes.has(name); },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return true; },
    contains() { return true; },
    querySelector() { return null; },
    getBoundingClientRect() {
      const width = numberFromStyle(this.style, "width", 1400);
      const height = numberFromStyle(this.style, "height", 360);
      return { x: 0, y: 0, top: 0, left: 0, right: width, bottom: height, width, height };
    },
  };
  Object.defineProperties(shell, {
    offsetWidth: { get() { return shell.getBoundingClientRect().width; } },
    offsetHeight: { get() { return shell.getBoundingClientRect().height; } },
  });
  return shell;
}

function makeContainer(shell, document) {
  const attributes = new Map();
  const host = {
    parentElement: shell,
    ownerDocument: document,
    style: fakeStyle(),
    dataset: {},
    classList: fakeClassList(),
  };
  const clip = {
    parentElement: null,
    ownerDocument: document,
    style: fakeStyle(),
    dataset: {},
    classList: fakeClassList(),
  };
  const dashboard = {
    parentElement: clip,
    ownerDocument: document,
    style: fakeStyle(),
    dataset: {},
    classList: fakeClassList(),
    offsetHeight: 0,
    scrollHeight: 0,
    getAttribute(name) { return name === "data-picker-view" ? "compact" : ""; },
    getBoundingClientRect() { return { height: 0 }; },
  };
  const container = {
    parentElement: host,
    ownerDocument: document,
    style: fakeStyle(),
    dataset: {},
    classList: fakeClassList(),
    closest(selector) { return selector === ".react-flow__node" ? shell : null; },
    querySelector(selector) {
      if (selector === ".hmbvp") return dashboard;
      if (selector === ".hmbvp-clip") return clip;
      return null;
    },
    getAttribute(name) { return attributes.get(name) || ""; },
    hasAttribute(name) { return attributes.has(name); },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
  };
  clip.parentElement = container;
  return { container, clip, dashboard };
}

function shellGeometry(shell) {
  const rect = shell.getBoundingClientRect();
  return { width: rect.width, height: rect.height };
}

function hostHarness({ nodeId, fitViewQueued = true } = {}) {
  const clock = frameClock();
  const document = fakeDocument(clock);
  const shell = makeShell(document, nodeId || "video-picker-1");
  const { container, clip, dashboard } = makeContainer(shell, document);
  const viewport = { x: 73, y: -41, zoom: 0.82 };
  const initialViewport = { ...viewport };
  const internals = [];
  const fitViewConsumptions = [];
  let directViewportMutations = 0;
  let queued = fitViewQueued;
  const props = {
    updateNodeInternals(resolvedId, resolvedShell) {
      assert.equal(resolvedId, nodeId || "video-picker-1");
      assert.equal(resolvedShell, shell);
      const geometry = shellGeometry(shell);
      internals.push(geometry);
      if (queued) {
        fitViewConsumptions.push(geometry);
        queued = false;
      }
    },
    setViewport() { directViewportMutations += 1; },
    fitView() { directViewportMutations += 1; },
    zoomTo() { directViewportMutations += 1; },
  };
  return {
    clock,
    document,
    shell,
    container,
    clip,
    dashboard,
    props,
    viewport,
    initialViewport,
    internals,
    fitViewConsumptions,
    get directViewportMutations() { return directViewportMutations; },
  };
}

const emptyState = { picker_shots: [{ shot_uid: "shot-1", video_asset_uids: [] }] };
const populatedState = {
  videos: [{ video_uid: "video-1", path: "C:/fixtures/video-1.mp4" }],
  picker_shots: [{ shot_uid: "shot-1", video_asset_uids: ["video-1"] }],
};

// Measurement-clone detection must be precise. A live branch can be hidden by
// normal host lifecycle/virtualization and must not be mistaken for the inert
// allocator copy unless a known measurement wrapper or explicit marker owns it.
{
  const clock = frameClock();
  const document = fakeDocument(clock);
  globalThis.document = document;
  globalThis.window = document.defaultView;
  const plainHiddenAncestor = cloneProbeElement(document, {
    attributes: { "aria-hidden": "true" },
    style: { visibility: "hidden" },
  });
  const plainLiveChild = cloneProbeElement(document, { parentElement: plainHiddenAncestor });
  assert.equal(
    picker.hmbVideoPickerIsHostMeasurementClone(plainLiveChild),
    false,
    "generic hidden/aria-hidden live ancestors are not measurement clones",
  );

  const hiddenMeasurementWrapper = cloneProbeElement(document, {
    classes: ["absolute", "left-0", "right-0", "pointer-events-none"],
    style: { visibility: "hidden" },
  });
  const wrappedChild = cloneProbeElement(document, { parentElement: hiddenMeasurementWrapper });
  assert.equal(
    picker.hmbVideoPickerIsHostMeasurementClone(wrappedChild),
    true,
    "known hidden allocator wrapper is a measurement clone",
  );

  const explicitMarker = cloneProbeElement(document, {
    attributes: { "data-hmb-host-measurement": "true" },
  });
  assert.equal(
    picker.hmbVideoPickerIsHostMeasurementClone(explicitMarker),
    true,
    "explicit measurement marker is authoritative even when visible",
  );

  const computedHiddenMeasurementWrapper = cloneProbeElement(document, {
    classes: ["absolute", "left-0", "right-0", "pointer-events-none"],
    computedDisplay: "none",
  });
  const computedWrappedChild = cloneProbeElement(document, {
    parentElement: computedHiddenMeasurementWrapper,
  });
  assert.equal(
    picker.hmbVideoPickerIsHostMeasurementClone(computedWrappedChild),
    true,
    "computed-hidden known measurement wrapper is a clone",
  );
}

function assertStableCompactShell(harness, message) {
  assert.deepEqual(shellGeometry(harness.shell), { width: 1400, height: 360 }, message);
  assert.equal(harness.shell.style.height, "360px");
  assert.equal(harness.shell.style.minHeight, "360px");
  assert.equal(harness.shell.style.maxHeight, "360px");
}

// Cold compact mount: the authored row may measure 158px, but its outer node is
// the migrated 360px native shell. Bursty lifecycle calls coalesce into exactly
// one internals publication, which is also the only geometry fitViewQueued sees.
const cold = hostHarness({ nodeId: "video-picker-stable", fitViewQueued: true });
globalThis.document = cold.document;
globalThis.window = cold.document.defaultView;
assert.equal(picker.hmbVideoPickerNodeIdentity(cold.container), "id:video-picker-stable");
assert.equal(picker.hmbRememberVideoPickerViewMode(cold.container, false), false);
assert.equal(picker.hmbApplyVideoPickerCompactHostSizing(cold.container, emptyState), 158);
assertStableCompactShell(cold, "cold compact sizing must preserve the v4 1400x360 shell");
for (let index = 0; index < 5; index += 1) {
  assert.equal(picker.hmbScheduleVideoPickerNodeInternalsUpdate(
    cold.container,
    cold.props,
    { stateValue: emptyState, expanded: false },
  ), true);
}
assert.equal(cold.clock.pending, 1, "one settled queue owns every cold-mount request");
cold.clock.flushSettled();
assert.equal(cold.internals.length, 1, "cold geometry revision publishes once");
assert.deepEqual(cold.fitViewConsumptions, [{ width: 1400, height: 360 }]);

// A server/props echo of the same revision must be a no-op. A real compact
// content revision publishes once even when repeated, while the outer native
// geometry remains unchanged.
picker.hmbScheduleVideoPickerNodeInternalsUpdate(
  cold.container,
  cold.props,
  { stateValue: emptyState, expanded: false },
);
cold.clock.flushSettled();
assert.equal(cold.internals.length, 1, "equal props echo must not republish internals");
assert.equal(picker.hmbApplyVideoPickerCompactHostSizing(cold.container, populatedState), 252);
assertStableCompactShell(cold, "content growth must not write 252px into the outer shell");
for (let index = 0; index < 4; index += 1) {
  picker.hmbScheduleVideoPickerNodeInternalsUpdate(
    cold.container,
    cold.props,
    { stateValue: populatedState, expanded: false },
  );
}
cold.clock.flushSettled();
assert.equal(cold.internals.length, 2, "one changed compact geometry revision publishes once");

// Explicit compact -> expanded -> compact transitions may expose the saved
// 1200px dashboard geometry, but transition-in-progress notifications are
// rejected and no 158px compact shell is ever published on the way back.
cold.container.__hmbVideoPickerViewTransition = true;
assert.equal(picker.hmbScheduleVideoPickerNodeInternalsUpdate(
  cold.container,
  cold.props,
  { stateValue: populatedState, expanded: true },
), false);
assert.equal(cold.clock.pending, 0);
delete cold.container.__hmbVideoPickerViewTransition;
cold.shell.style.height = "1200px";
cold.shell.style.minHeight = "1200px";
cold.shell.style.maxHeight = "1200px";
picker.hmbRememberVideoPickerViewMode(cold.container, true);
for (let index = 0; index < 3; index += 1) {
  picker.hmbScheduleVideoPickerNodeInternalsUpdate(
    cold.container,
    cold.props,
    { stateValue: populatedState, expanded: true, force: true, afterTransition: true },
  );
}
cold.clock.flushSettled();
assert.equal(cold.internals.length, 3, "expanded transition publishes one final revision");
assert.deepEqual(cold.internals.at(-1), { width: 1400, height: 1200 });

const expandedRemountClock = frameClock();
const expandedRemountDocument = fakeDocument(expandedRemountClock);
const expandedRemountShell = makeShell(
  expandedRemountDocument,
  "video-picker-stable",
  { width: 1400, height: 1200 },
);
cold.shell.setAttribute("data-runtime-instance-id", "runtime-before-reload");
expandedRemountShell.setAttribute("data-runtime-instance-id", "runtime-after-reload");
const expandedRemount = makeContainer(expandedRemountShell, expandedRemountDocument).container;
assert.equal(
  picker.hmbVideoPickerStoredViewMode(expandedRemount),
  true,
  "expanded mode persists across a new shell/container with the same data-id regardless of runtime id",
);

cold.container.__hmbVideoPickerViewTransition = true;
assert.equal(picker.hmbCancelVideoPickerNodeInternalsUpdate(cold.container), true);
delete cold.container.__hmbVideoPickerViewTransition;
cold.shell.style.height = "360px";
cold.shell.style.minHeight = "360px";
cold.shell.style.maxHeight = "360px";
picker.hmbRememberVideoPickerViewMode(cold.container, false);
picker.hmbApplyVideoPickerCompactHostSizing(cold.container, populatedState);
for (let index = 0; index < 3; index += 1) {
  picker.hmbScheduleVideoPickerNodeInternalsUpdate(
    cold.container,
    cold.props,
    { stateValue: populatedState, expanded: false, force: true, afterTransition: true },
  );
}
cold.clock.flushSettled();
assert.equal(cold.internals.length, 4, "compact return publishes one final revision");
assert.deepEqual(cold.internals.at(-1), { width: 1400, height: 360 });

// Warm remount: a new DOM shell with the same stable data-id remembers compact
// mode, publishes once for its own first revision, and gives a newly queued host
// the same final compact bounds as cold load.
const warm = hostHarness({ nodeId: "video-picker-stable", fitViewQueued: true });
globalThis.document = warm.document;
globalThis.window = warm.document.defaultView;
assert.equal(picker.hmbVideoPickerStoredViewMode(warm.container), false);
assert.equal(picker.hmbApplyVideoPickerCompactHostSizing(warm.container, populatedState), 252);
for (let index = 0; index < 5; index += 1) {
  picker.hmbScheduleVideoPickerNodeInternalsUpdate(
    warm.container,
    warm.props,
    { stateValue: populatedState, expanded: false },
  );
}
warm.clock.flushSettled();
assert.equal(warm.internals.length, 1, "warm mount publishes exactly once");
assert.deepEqual(warm.fitViewConsumptions, [{ width: 1400, height: 360 }]);
assertStableCompactShell(warm, "warm compact mount must preserve one canonical outer bound");

const allFitGeometry = [...cold.fitViewConsumptions, ...warm.fitViewConsumptions];
assert.deepEqual(
  [...new Set(allFitGeometry.map(({ width, height }) => `${width}x${height}`))],
  ["1400x360"],
  "fitViewQueued may consume only one stable final compact geometry kind",
);
const allInternalsHeights = [...cold.internals, ...warm.internals].map(({ height }) => height);
assert.equal(allInternalsHeights.includes(158), false, "legacy 158px must never reach React Flow internals");
const outerOscillation1200To158 = allInternalsHeights.slice(1).filter((height, index) => (
  (allInternalsHeights[index] === 1200 && height === 158)
  || (allInternalsHeights[index] === 158 && height === 1200)
)).length;
assert.equal(outerOscillation1200To158, 0, "1200px <-> 158px outer oscillation must be zero");

for (const harness of [cold, warm]) {
  assert.deepEqual(harness.viewport, harness.initialViewport, "picker must preserve viewport x/y/zoom");
  assert.equal(harness.directViewportMutations, 0, "picker must not call viewport mutation APIs");
}
const schedulerBody = widgetSource.match(
  /export function hmbScheduleVideoPickerNodeInternalsUpdate\([\s\S]*?\n}\n\nexport function hmbDetachVideoPickerDom/,
)?.[0] || "";
assert.ok(schedulerBody, "scheduler implementation must remain auditable");
assert.doesNotMatch(
  schedulerBody,
  /\b(?:fitView|fitBounds|setViewport|zoomTo|setTransform)\s*\(/,
  "the Picker scheduler must not directly mutate the workspace viewport",
);

console.log("HMB VideoPicker workspace viewport stability regression checks passed.");
