import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(
  new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url),
  "utf8",
);
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

const pythonSource = fs.readFileSync(
  new URL("../../HMBVideoPickerLibrary.py", import.meta.url),
  "utf8",
);
const visibleWidgetOptions = pythonSource.match(
  /def _configure_picker_widget_parameter[\s\S]*?options\.update\(\{([\s\S]*?)\n\s*\}\)/,
);
const newWidgetOptions = pythonSource.match(
  /def _add_picker_widget[\s\S]*?"ui_options": \{([\s\S]*?)\n\s*\},\n\s*\}/,
);
assert.ok(visibleWidgetOptions, "Existing Picker state rows must expose an explicit UI contract.");
assert.ok(newWidgetOptions, "New Picker state rows must expose an explicit UI contract.");
assert.match(visibleWidgetOptions[1], /"expandable": True/);
assert.match(newWidgetOptions[1], /"expandable": True/);
assert.doesNotMatch(visibleWidgetOptions[1], /"expandable": False/);
assert.doesNotMatch(newWidgetOptions[1], /"expandable": False/);

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

function fakeShell(height) {
  const attributes = new Map();
  return {
    className: "react-flow__node",
    classList: fakeClassList(["react-flow__node"]),
    dataset: {},
    style: fakeStyle({ height: `${height}px`, minHeight: `${height}px`, maxHeight: `${height}px` }),
    offsetHeight: height,
    ownerDocument: null,
    getBoundingClientRect() { return { top: 0, bottom: height, height, width: 1400 }; },
    getAttribute(name) { return attributes.get(name) || ""; },
    hasAttribute(name) { return attributes.has(name); },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    addEventListener() {},
    removeEventListener() {},
    appendChild() {},
    contains() { return true; },
    querySelector() { return null; },
  };
}

function fakeDocument() {
  const document = {
    body: {},
    documentElement: {},
    head: { appendChild() {} },
    defaultView: {},
    createElement() {
      const attributes = new Map();
      return {
        style: fakeStyle(),
        dataset: {},
        setAttribute(name, value) { attributes.set(name, String(value)); },
        getAttribute(name) { return attributes.get(name) || ""; },
        remove() {},
      };
    },
  };
  return document;
}

function measurementContainer(shell, document) {
  let placeholder = null;
  return {
    parentElement: shell,
    ownerDocument: document,
    dataset: {},
    style: fakeStyle(),
    classList: fakeClassList(),
    closest(selector) { return selector === ".react-flow__node" ? shell : null; },
    querySelector(selector) {
      return selector === "[data-hmb-video-picker-measurement-box]" ? placeholder : null;
    },
    replaceChildren(next) { placeholder = next; },
    setAttribute() {},
    removeAttribute() {},
  };
}

const document = fakeDocument();
globalThis.document = document;
globalThis.window = {
  getComputedStyle() {
    return {
      display: "block",
      flexDirection: "column",
      gridTemplateColumns: "none",
      position: "static",
      paddingBottom: "0",
      borderBottomWidth: "0",
    };
  },
};

// Cold mount regression: the hidden measurement controller runs before the
// visible widget but must never repair or mutate the outer React Flow node.
const staleShell = fakeShell(158);
staleShell.ownerDocument = document;
staleShell.dataset.hmbVideoPickerCompactHeight = "158";
const hiddenContainer = measurementContainer(staleShell, document);
const measurementController = picker.hmbMountVideoPickerHostMeasurement(hiddenContainer, {
  value: { picker_shots: [] },
});
assert.equal(staleShell.style.height, "158px");
assert.equal(staleShell.style.minHeight, "158px");
assert.equal(staleShell.style.maxHeight, "158px");
assert.equal(staleShell.dataset.hmbVideoPickerCompactHeight, "158");
measurementController.cleanup();

// A measurement clone must not release a valid expanded/user geometry.
const expandedShell = fakeShell(1200);
expandedShell.ownerDocument = document;
const expandedMeasurement = measurementContainer(expandedShell, document);
const expandedController = picker.hmbMountVideoPickerHostMeasurement(expandedMeasurement, {
  value: { picker_shots: [] },
});
assert.equal(expandedShell.style.height, "1200px");
assert.equal(expandedShell.style.minHeight, "1200px");
assert.equal(expandedShell.style.maxHeight, "1200px");
expandedController.cleanup();

// The visible compact widget owns only its inner authored frame. Stable native
// outer geometry must remain unchanged; releasing 1200px here lets the host
// briefly fit the whole workspace against the 252px authored row.
const liveShell = fakeShell(1200);
liveShell.ownerDocument = document;
const host = {
  parentElement: liveShell,
  style: fakeStyle(),
  dataset: {},
  classList: fakeClassList(),
};
const container = {
  parentElement: host,
  ownerDocument: document,
  style: fakeStyle(),
  dataset: {},
  classList: fakeClassList(),
  closest(selector) { return selector === ".react-flow__node" ? liveShell : null; },
  querySelector(selector) {
    if (selector === ".hmbvp") return dashboard;
    if (selector === ".hmbvp-clip") return clip;
    return null;
  },
  setAttribute() {},
  removeAttribute() {},
};
const clip = { parentElement: container, style: fakeStyle(), dataset: {}, classList: fakeClassList() };
const dashboard = {
  parentElement: clip,
  style: fakeStyle(),
  dataset: {},
  classList: fakeClassList(),
  offsetHeight: 0,
  scrollHeight: 0,
  getAttribute(name) { return name === "data-picker-view" ? "compact" : ""; },
  getBoundingClientRect() { return { height: 0 }; },
};

assert.equal(
  picker.hmbApplyVideoPickerCompactHostSizing(container, { picker_shots: [] }),
  252,
);
assert.equal(clip.style.height, "252px");
assert.equal(clip.style.minHeight, "252px");
assert.equal(clip.style.maxHeight, "252px");
assert.equal(dashboard.style.height, "252px");
assert.equal(liveShell.style.height, "1200px");
assert.equal(liveShell.style.minHeight, "1200px");
assert.equal(liveShell.style.maxHeight, "1200px");
assert.equal(container.dataset.hmbVideoPickerCompactContentHeight, "252");

// A host-owned outer geometry is not changed by inner content sizing alone.
const arbitraryHostShell = fakeShell(480);
arbitraryHostShell.ownerDocument = document;
const nativeHost = { parentElement: arbitraryHostShell, style: fakeStyle(), dataset: {}, classList: fakeClassList() };
const nativeContainer = {
  ...container,
  parentElement: nativeHost,
  dataset: {},
  closest(selector) { return selector === ".react-flow__node" ? arbitraryHostShell : null; },
};
assert.equal(
  picker.hmbApplyVideoPickerCompactHostSizing(nativeContainer, { picker_shots: [] }),
  252,
);
assert.equal(arbitraryHostShell.style.height, "480px");
assert.equal(arbitraryHostShell.style.minHeight, "480px");
assert.equal(arbitraryHostShell.style.maxHeight, "480px");

console.log("HMB VideoPicker compact cold-mount regression checks passed.");
