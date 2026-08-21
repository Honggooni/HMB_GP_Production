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
  "hmbCancelVideoPickerNodeInternalsUpdate",
  "hmbCaptureVideoPickerExpandedGeometry",
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

// v6 cold-mounts the same expanded geometry that the inline dashboard paints.
// Compact geometry is an explicit session-local header toggle and must never
// become the next workflow's serialized cold-mount authority.
assert.match(pythonSource, /PICKER_START_WIDTH\s*=\s*1400/);
assert.match(pythonSource, /PICKER_START_HEIGHT\s*=\s*1200/);
assert.match(pythonSource, /PICKER_NATIVE_SIZE_VERSION\s*=\s*6/);
assert.match(pythonSource, /PICKER_COMPACT_NATIVE_HEIGHT\s*=\s*360/);
assert.match(pythonSource, /PICKER_WIDGET_COMPACT_MOUNT_HEIGHT\s*=\s*252/);
assert.match(pythonSource, /PICKER_WIDGET_MIN_HEIGHT\s*=\s*1151/);
const migrationBody = pythonSource.match(
  /def _restored_picker_native_geometry\([\s\S]*?return initial_size, expanded_size, not canonical/,
)?.[0] || "";
assert.match(migrationBody, /expanded_size\s*=\s*raw_expanded_size\s+or\s+saved_expanded_size/);
assert.match(migrationBody, /initial_size\s*=\s*dict\(expanded_size\)/);
assert.doesNotMatch(
  migrationBody,
  /initial_size\s*=\s*\{[\s\S]*?"height":\s*PICKER_COMPACT_NATIVE_HEIGHT/,
  "serialized/cold-mount geometry must never be forced back to compact height",
);
assert.match(
  pythonSource,
  /prepared_metadata\["size"\]\s*=\s*dict\(initial_size\)[\s\S]*?prepared_kwargs\["metadata"\]\s*=\s*prepared_metadata[\s\S]*?super\(\)\.__init__\(\*\*prepared_kwargs\)/,
  "expanded v6 geometry must reach DataNode before React Flow observes the node",
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

function makeShell(nodeId, { exact = true, height = 1200, inset = 72 } = {}) {
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
assert.equal(primary.shell.style.getPropertyValue("min-height"), "1151px");
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
assert.equal(zeroHeight.shell.style.getPropertyValue("min-height"), "");
assert.equal(zeroHeight.shell.style.getPropertyValue("max-height"), "");

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
  picker.hmbScheduleVideoPickerNodeInternalsUpdate(primary.container, {
    updateNodeInternals() { throw new Error("must not be called"); },
    fitView() { throw new Error("must not be called"); },
    setViewport() { throw new Error("must not be called"); },
  }),
  false,
);
assert.equal(picker.hmbCancelVideoPickerNodeInternalsUpdate(primary.container), false);

console.log("HMB VideoPicker workspace viewport stability regression checks passed.");
