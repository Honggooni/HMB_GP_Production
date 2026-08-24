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
  "hmbApplyVideoPickerCompactGeometry",
  "hmbApplyVideoPickerCompactHostSizing",
  "hmbApplyVideoPickerExpandedGeometryFloor",
  "hmbSetVideoPickerExpandedShellHeight",
  "hmbVideoPickerExpandedShellSize",
  "hmbCancelVideoPickerNodeInternalsUpdate",
  "hmbCaptureVideoPickerExpandedGeometry",
  "hmbVideoPickerExpandedGeometryForCompactMount",
  "hmbRememberVideoPickerExpandedGeometry",
  "hmbVideoPickerRememberedExpandedGeometry",
  "hmbRememberVideoPickerViewMode",
  "hmbRestoreVideoPickerExpandedGeometry",
  "hmbScheduleVideoPickerNodeInternalsUpdate",
  "hmbSetVideoPickerHybridView",
  "hmbSetVideoPickerNativeResizeLocked",
  "hmbVideoPickerNodeIdentity",
  "hmbVideoPickerStoredViewMode",
]) {
  assert.equal(typeof picker[exportedName], "function", `${exportedName} must remain exported.`);
}

// v7 cold-mounts the compact Loader and retains expanded geometry separately.
assert.match(pythonSource, /PICKER_START_WIDTH\s*=\s*1400/);
assert.match(pythonSource, /PICKER_START_HEIGHT\s*=\s*1200/);
assert.match(pythonSource, /PICKER_NATIVE_SIZE_VERSION\s*=\s*7/);
assert.match(pythonSource, /PICKER_COMPACT_NATIVE_HEIGHT\s*=\s*360/);
assert.match(pythonSource, /PICKER_WIDGET_COMPACT_MOUNT_HEIGHT\s*=\s*252/);
assert.match(pythonSource, /PICKER_WIDGET_MIN_HEIGHT\s*=\s*1151/);
assert.match(widgetSource, /const HMB_EXPANDED_NODE_MIN_WIDTH = HMB_DEFAULT_NODE_WIDTH;/);
assert.match(widgetSource, /const HMB_EXPANDED_NODE_MIN_HEIGHT = HMB_DEFAULT_NODE_HEIGHT;/);
assert.match(
  widgetSource,
  /\.center-stack>\.viewport-panel\{height:auto;min-height:\$\{HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT\}px;flex:1 1 0\}\.center-stack>\.activity-section\{height:\$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px;flex:0 0 \$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px;min-height:\$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px;max-height:\$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px/,
  "expanded outer-height deltas must be absorbed automatically while Activity Log stays fixed",
);
assert.doesNotMatch(widgetSource, /data-resize-panel|panel-resize-handle/);
assert.doesNotMatch(
  widgetSource,
  /resizeObserver\.observe\((?:container|shellForResizeSync|hostTargetsForResizeSync\?\.(?:layoutRow|trailingSpacer))\)/,
  "automatic fit must not observe host-owned geometry and feed React Flow updates back into itself",
);
assert.match(
  widgetSource,
  /resizeObserver\.observe\((?:rightStackForResizeSync|centerStackForResizeSync)\)/,
  "expanded bottom-edge synchronization may observe Picker-owned inner stacks only",
);
const migrationBody = pythonSource.match(
  /def _restored_picker_native_geometry\([\s\S]*?return compact_size, expanded_size, not canonical/,
)?.[0] || "";
assert.match(migrationBody, /expanded_size\s*=\s*raw_expanded_size\s+or\s+saved_expanded_size/);
assert.match(
  migrationBody,
  /compact_size\s*=\s*\{[\s\S]*?"height":\s*PICKER_COMPACT_NATIVE_HEIGHT/,
  "serialized/cold-mount geometry must use the compact Loader height",
);
assert.match(
  pythonSource,
  /prepared_metadata\["size"\]\s*=\s*dict\(compact_size\)[\s\S]*?prepared_kwargs\["metadata"\]\s*=\s*prepared_metadata[\s\S]*?super\(\)\.__init__\(\*\*prepared_kwargs\)/,
  "compact v7 geometry must reach DataNode before React Flow observes the node",
);

const transitionSource = widgetSource.match(
  /const togglePickerView = \(\) => \{[\s\S]*?\n  const commandBridge =/,
)?.[0] || "";
assert.ok(transitionSource, "inline compact/expanded transition must remain auditable");
assert.match(transitionSource, /hmbCaptureVideoPickerExpandedGeometry\(container\)/);
assert.match(transitionSource, /hmbSetVideoPickerHybridView\(container, false, compactPickerMarkup\)/);
assert.match(transitionSource, /hmbApplyVideoPickerCompactGeometry\(container, compactContentHeight\)/);
assert.match(transitionSource, /hmbSetVideoPickerNativeResizeLocked\(container, true\)/);
assert.match(transitionSource, /hmbSetVideoPickerHybridView\(container, true, compactPickerMarkup\)/);
assert.match(transitionSource, /hmbRestoreVideoPickerExpandedGeometry\(/);
assert.match(transitionSource, /hmbSetVideoPickerNativeResizeLocked\(container, false\)/);
assert.doesNotMatch(transitionSource, /\b(?:cleanup|factory)\s*\(/);
assert.doesNotMatch(
  transitionSource,
  /\b(?:fitView|fitBounds|setViewport|zoomTo|setTransform|updateNodeInternals)\s*\(/,
  "view toggle must not move or refit the React Flow workspace",
);
assert.doesNotMatch(widgetSource, /<dialog\b|\.showModal\s*\(/);

for (const functionName of [
  "hmbCaptureVideoPickerExpandedGeometry",
  "hmbApplyVideoPickerCompactGeometry",
  "hmbRestoreVideoPickerExpandedGeometry",
]) {
  const start = widgetSource.indexOf(`export function ${functionName}`);
  const next = widgetSource.indexOf("\nexport function ", start + 1);
  const body = widgetSource.slice(start, next > start ? next : start + 2500);
  assert.ok(start >= 0, `${functionName} must exist`);
  assert.match(body, /hmbVideoPickerExactReactFlowNode\(container\)/);
  assert.doesNotMatch(body, /hmbFindVideoPickerReactFlowNode\(container\)/);
}

function fakeStyle(initial = {}) {
  const values = new Map();
  const priorities = new Map();
  for (const [name, value] of Object.entries(initial)) values.set(name, String(value));
  return {
    getPropertyValue(name) { return values.get(String(name)) || ""; },
    getPropertyPriority(name) { return priorities.get(String(name)) || ""; },
    setProperty(name, value, priority = "") {
      values.set(String(name), String(value));
      if (priority) priorities.set(String(name), String(priority));
      else priorities.delete(String(name));
    },
    removeProperty(name) {
      const prior = values.get(String(name)) || "";
      values.delete(String(name));
      priorities.delete(String(name));
      return prior;
    },
  };
}

function classList(names = []) {
  const values = new Set(names);
  return {
    contains(name) { return values.has(name); },
    add(...items) { items.forEach((item) => values.add(item)); },
    remove(...items) { items.forEach((item) => values.delete(item)); },
  };
}

function numericStyle(style, property, fallback = 0) {
  const parsed = Number.parseFloat(style.getPropertyValue(property));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function makeShell(nodeId, {
  exact = true,
  height = 1200,
  inset = 72,
  runtimeId = "picker-runtime-a",
} = {}) {
  const attributes = new Map([["data-id", nodeId]]);
  const style = fakeStyle({
    width: "1400px",
    height: height > 0 ? `${height}px` : "",
    "min-height": height > 0 ? "1151px" : "",
    transform: "translate(31px, -19px)",
    top: "43px",
  });
  const shell = {
    className: exact ? "react-flow__node" : "node-lookalike",
    classList: classList(exact ? ["react-flow__node"] : ["node-lookalike"]),
    parentElement: null,
    style,
    getAttribute(name) { return attributes.get(name) || ""; },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    hasAttribute(name) { return attributes.has(name); },
    getBoundingClientRect() {
      const currentHeight = numericStyle(style, "height", 0);
      return {
        top: 100,
        bottom: 100 + currentHeight,
        height: currentHeight,
        width: numericStyle(style, "width", 1400),
      };
    },
  };
  Object.defineProperty(shell, "offsetHeight", {
    get() { return numericStyle(style, "height", 0); },
  });
  const container = {
    __hmbVideoPickerRuntimeInstanceId: runtimeId,
    parentElement: shell,
    style: fakeStyle(),
    classList: classList(),
    closest(selector) {
      return selector === ".react-flow__node" && exact ? shell : null;
    },
    getBoundingClientRect() {
      return { top: 100 + inset, bottom: 100 + inset, height: 0, width: 1400 };
    },
  };
  return { container, shell };
}

const primary = makeShell("video-picker-stable", { inset: 72 });
const sibling = makeShell("unrelated-node", { inset: 72 });
const siblingBefore = {
  height: sibling.shell.style.getPropertyValue("height"),
  minHeight: sibling.shell.style.getPropertyValue("min-height"),
  maxHeight: sibling.shell.style.getPropertyValue("max-height"),
  transform: sibling.shell.style.getPropertyValue("transform"),
};
const widthBefore = primary.shell.style.getPropertyValue("width");
const transformBefore = primary.shell.style.getPropertyValue("transform");
const topBefore = primary.shell.style.getPropertyValue("top");

const expandedSnapshot = picker.hmbCaptureVideoPickerExpandedGeometry(primary.container);
assert.equal(expandedSnapshot.shell, primary.shell);
assert.equal(expandedSnapshot.properties.height.value, "1200px");
assert.equal(expandedSnapshot.properties["min-height"].value, "1151px");
assert.equal(expandedSnapshot.properties["max-height"].value, "");

const savedExpandedColdMount = makeShell("saved-expanded-cold-mount", {
  height: 360,
  inset: 0,
  runtimeId: "saved-expanded-runtime",
});
const savedExpandedColdSnapshot = picker.hmbVideoPickerExpandedGeometryForCompactMount(
  savedExpandedColdMount.container,
  { expanded_node_size: { width: 1680, height: 1320 } },
);
assert.equal(savedExpandedColdSnapshot.properties.height.value, "1320px");
assert.equal(savedExpandedColdSnapshot.properties.width.value, "1680px");
assert.equal(savedExpandedColdSnapshot.measuredHeight, 1320);
assert.equal(picker.hmbApplyVideoPickerCompactGeometry(savedExpandedColdMount.container, 252), 360);
assert.equal(savedExpandedColdMount.shell.style.getPropertyValue("width"), "1400px");
assert.equal(savedExpandedColdMount.shell.style.getPropertyValue("height"), "360px");
assert.equal(
  picker.hmbRestoreVideoPickerExpandedGeometry(
    savedExpandedColdMount.container,
    savedExpandedColdSnapshot,
  ),
  true,
);
assert.equal(savedExpandedColdMount.shell.style.getPropertyValue("width"), "1680px");
assert.equal(savedExpandedColdMount.shell.style.getPropertyValue("height"), "1320px");

const stalePriorRuntimeShell = makeShell("hot-runtime-reuse", {
  height: 1200,
  inset: 0,
  runtimeId: "runtime-b",
});
const newRuntimeExpandedSnapshot = picker.hmbVideoPickerExpandedGeometryForCompactMount(
  stalePriorRuntimeShell.container,
  { expanded_node_size: { width: 1680, height: 1320 } },
);
assert.equal(
  newRuntimeExpandedSnapshot.properties.width.value,
  "1680px",
  "new-runtime saved geometry must override a stale prior-runtime shell width",
);
assert.equal(
  newRuntimeExpandedSnapshot.properties.height.value,
  "1320px",
  "new-runtime saved geometry must override a stale prior-runtime shell height",
);

assert.equal(picker.hmbApplyVideoPickerCompactGeometry(primary.container, 252), 360);
for (const property of ["height", "min-height", "max-height"]) {
  assert.equal(primary.shell.style.getPropertyValue(property), "360px");
  assert.equal(primary.shell.style.getPropertyPriority(property), "important");
}
assert.equal(primary.shell.style.getPropertyValue("width"), widthBefore);
assert.equal(primary.shell.style.getPropertyValue("transform"), transformBefore);
assert.equal(primary.shell.style.getPropertyValue("top"), topBefore);

assert.equal(picker.hmbApplyVideoPickerCompactGeometry(primary.container, 438), 546);
assert.equal(primary.shell.style.getPropertyValue("height"), "546px");
assert.equal(
  picker.hmbRestoreVideoPickerExpandedGeometry(primary.container, expandedSnapshot),
  true,
);
assert.equal(primary.shell.style.getPropertyValue("height"), "1200px");
assert.equal(primary.shell.style.getPropertyValue("min-height"), "1200px");
assert.equal(primary.shell.style.getPropertyPriority("min-height"), "important");
assert.equal(primary.shell.style.getPropertyValue("max-height"), "");
assert.equal(primary.shell.style.getPropertyValue("width"), widthBefore);
assert.equal(primary.shell.style.getPropertyValue("transform"), transformBefore);
assert.equal(primary.shell.style.getPropertyValue("top"), topBefore);
assert.deepEqual(siblingBefore, {
  height: sibling.shell.style.getPropertyValue("height"),
  minHeight: sibling.shell.style.getPropertyValue("min-height"),
  maxHeight: sibling.shell.style.getPropertyValue("max-height"),
  transform: sibling.shell.style.getPropertyValue("transform"),
});

// Missing saved min/max declarations are removed, never replaced by an
// artificial 1200px max-height that would block the user's expanded resize.
const zeroHeight = makeShell("zero-height", { height: 0, inset: 108 });
const zeroSnapshot = picker.hmbCaptureVideoPickerExpandedGeometry(zeroHeight.container);
assert.equal(picker.hmbApplyVideoPickerCompactGeometry(zeroHeight.container, 252), 392);
assert.equal(
  picker.hmbRestoreVideoPickerExpandedGeometry(zeroHeight.container, zeroSnapshot),
  true,
);
assert.equal(zeroHeight.shell.style.getPropertyValue("height"), "1200px");
assert.equal(zeroHeight.shell.style.getPropertyValue("min-height"), "1200px");
assert.equal(zeroHeight.shell.style.getPropertyPriority("min-height"), "important");
assert.equal(zeroHeight.shell.style.getPropertyValue("max-height"), "");

// Expanded native resize is one-way from the authored 1400x1200 frame.  A
// stale/smaller saved shell is repaired, while a larger user size is retained.
const undersized = makeShell("undersized-expanded", { height: 1040, inset: 0 });
undersized.shell.style.setProperty("width", "920px");
undersized.container.__hmbVideoPickerExpanded = true;
const repairedFloor = picker.hmbApplyVideoPickerExpandedGeometryFloor(undersized.container);
assert.equal(repairedFloor.widthClamped, true);
assert.equal(repairedFloor.heightClamped, true);
assert.equal(undersized.shell.style.getPropertyValue("width"), "1400px");
assert.equal(undersized.shell.style.getPropertyValue("height"), "1200px");
assert.equal(undersized.shell.style.getPropertyValue("min-width"), "1400px");
assert.equal(undersized.shell.style.getPropertyValue("min-height"), "1200px");
assert.equal(undersized.shell.style.getPropertyPriority("min-width"), "important");
assert.equal(undersized.shell.style.getPropertyPriority("min-height"), "important");
undersized.shell.style.setProperty("width", "1760px");
undersized.shell.style.setProperty("height", "1480px");
const retainedExpansion = picker.hmbApplyVideoPickerExpandedGeometryFloor(undersized.container);
assert.equal(retainedExpansion.widthClamped, false);
assert.equal(retainedExpansion.heightClamped, false);
assert.equal(undersized.shell.style.getPropertyValue("width"), "1760px");
assert.equal(undersized.shell.style.getPropertyValue("height"), "1480px");
assert.equal(
  picker.hmbSetVideoPickerExpandedShellHeight(undersized.container, 900),
  1200,
  "the internal viewport handle cannot drag the whole expanded shell below its start height",
);
assert.equal(undersized.shell.style.getPropertyValue("height"), "1200px");
assert.equal(picker.hmbSetVideoPickerExpandedShellHeight(undersized.container, 1675), 1675);
assert.deepEqual(
  {
    width: picker.hmbVideoPickerExpandedShellSize(undersized.container).width,
    height: picker.hmbVideoPickerExpandedShellSize(undersized.container).height,
  },
  { width: 1760, height: 1675 },
  "the saved expanded size source must match the exact shell after a synchronized handle resize",
);

// Geometry ownership fails closed unless the exact nearest React Flow node is
// found. A node-shaped host object must never become a mutation fallback.
const inexact = makeShell("lookalike", { exact: false, height: 1200 });
assert.equal(picker.hmbCaptureVideoPickerExpandedGeometry(inexact.container), null);
assert.equal(picker.hmbApplyVideoPickerCompactGeometry(inexact.container, 252), 0);
assert.equal(inexact.shell.style.getPropertyValue("height"), "1200px");

assert.equal(picker.hmbRememberVideoPickerViewMode(primary.container, false), false);
const remount = makeShell("video-picker-stable", { inset: 108 });
assert.equal(
  picker.hmbVideoPickerStoredViewMode(remount.container),
  false,
  "compact choice must survive a same-data-id controller remount",
);

const rehydrated = makeShell("video-picker-stable", {
  inset: 108,
  runtimeId: "picker-runtime-b",
});
assert.equal(
  picker.hmbVideoPickerStoredViewMode(rehydrated.container),
  null,
  "a new Python runtime must not inherit the prior workflow-load view mode",
);

// A compact controller remount must not replace the user's last expanded
// resize with the 1200px default. Geometry is retained by the same stable node
// id and rebound only to the new exact React Flow shell.
primary.shell.style.setProperty("height", "1444px");
const userExpandedSnapshot = picker.hmbCaptureVideoPickerExpandedGeometry(primary.container);
picker.hmbRememberVideoPickerExpandedGeometry(primary.container, userExpandedSnapshot);
const rememberedForRemount = picker.hmbVideoPickerRememberedExpandedGeometry(remount.container);
assert.equal(rememberedForRemount.shell, remount.shell);
assert.equal(rememberedForRemount.properties.height.value, "1444px");
assert.equal(
  picker.hmbRestoreVideoPickerExpandedGeometry(remount.container, rememberedForRemount),
  true,
);
assert.equal(remount.shell.style.getPropertyValue("height"), "1444px");
assert.equal(
  picker.hmbVideoPickerRememberedExpandedGeometry(rehydrated.container),
  null,
  "a newly hydrated runtime must not inherit stale expanded shell geometry",
);

// Hosts may expose a live row before Python publishes runtime_instance_id.
// Bind that first real id without losing a choice made in the unbound window,
// then prove a later A→B replacement resets instead of migrating it.
const delayedRuntime = makeShell("delayed-runtime", {
  runtimeId: "",
  height: 1200,
});
delayedRuntime.container.__hmbVideoPickerExpanded = true;
delayedRuntime.container.__hmbVideoPickerExpandedGeometry =
  picker.hmbCaptureVideoPickerExpandedGeometry(delayedRuntime.container);
assert.deepEqual(
  picker.hmbBindVideoPickerRuntimeIdentity(delayedRuntime.container, "runtime-a"),
  { changed: true, hydrationReset: false },
);
assert.equal(picker.hmbVideoPickerStoredViewMode(delayedRuntime.container), true);
assert.equal(
  picker.hmbVideoPickerRememberedExpandedGeometry(delayedRuntime.container)?.properties?.height?.value,
  "1200px",
);
assert.deepEqual(
  picker.hmbBindVideoPickerRuntimeIdentity(delayedRuntime.container, "runtime-b"),
  { changed: true, hydrationReset: true },
);
assert.equal(picker.hmbVideoPickerStoredViewMode(delayedRuntime.container), false);
assert.equal(picker.hmbVideoPickerRememberedExpandedGeometry(delayedRuntime.container), null);
assert.equal(
  picker.hmbScheduleVideoPickerNodeInternalsUpdate(primary.container, {
    updateNodeInternals() { throw new Error("must not be called"); },
    fitView() { throw new Error("must not be called"); },
    setViewport() { throw new Error("must not be called"); },
  }),
  false,
);
assert.equal(picker.hmbCancelVideoPickerNodeInternalsUpdate(primary.container), false);

console.log("HMB VideoPicker workspace viewport stability regression checks passed.");
