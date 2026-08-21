import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const picker = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);

function fakeStyle(initial = {}) {
  const values = new Map(Object.entries(initial));
  const priorities = new Map();
  return {
    setProperty(name, value, priority = "") {
      values.set(String(name), String(value));
      priorities.set(String(name), String(priority));
    },
    getPropertyValue(name) { return values.get(String(name)) || ""; },
    getPropertyPriority(name) { return priorities.get(String(name)) || ""; },
    removeProperty(name) {
      const previous = values.get(String(name)) || "";
      values.delete(String(name));
      priorities.delete(String(name));
      return previous;
    },
    snapshot() {
      return JSON.stringify(Array.from(values.entries()).sort());
    },
  };
}

function fakeClassList(value = "") {
  const tokens = new Set(String(value).split(/\s+/).filter(Boolean));
  return {
    contains(token) { return tokens.has(String(token)); },
    add(...items) { items.forEach((item) => tokens.add(String(item))); },
    remove(...items) { items.forEach((item) => tokens.delete(String(item))); },
  };
}

function fakeElement(parent = null, className = "", attributes = {}) {
  const attrs = new Map(Object.entries(attributes));
  const element = {
    parentElement: parent,
    children: [],
    className,
    classList: fakeClassList(className),
    style: fakeStyle(),
    getAttribute(name) { return attrs.get(String(name)) || ""; },
    setAttribute(name, value) { attrs.set(String(name), String(value)); },
    removeAttribute(name) { attrs.delete(String(name)); },
    hasAttribute(name) { return attrs.has(String(name)); },
    contains(candidate) {
      for (let current = candidate; current; current = current.parentElement) {
        if (current === element) return true;
      }
      return false;
    },
    closest(selector) {
      for (let current = element; current; current = current.parentElement) {
        if (selector === ".react-flow__node" && current.classList?.contains("react-flow__node")) return current;
        if (
          selector === "[data-parameter-name=\"HMB_PICKER_STATE\"]"
          && current.getAttribute?.("data-parameter-name") === "HMB_PICKER_STATE"
        ) return current;
      }
      return null;
    },
  };
  if (parent) parent.children.push(element);
  Object.defineProperty(element, "nextElementSibling", {
    get() {
      const siblings = element.parentElement?.children || [];
      const index = siblings.indexOf(element);
      return index >= 0 ? siblings[index + 1] || null : null;
    },
  });
  return element;
}

function allocatorFixture({ validSpacer = true, inset = 72, contentHeight = 252 } = {}) {
  // Editor 0.123 fixture at exact compact outer height inset + content:
  // the host's -24px stack measurement and net 8px bottom reserve allocate the
  // state row 32px short until the exact trailing spacer is reclaimed.
  const shell = fakeElement(null, "react-flow__node");
  shell.style = fakeStyle({ height: `${inset + contentHeight}px` });
  Object.defineProperty(shell, "offsetHeight", {
    get() { return Number.parseFloat(shell.style.getPropertyValue("height")) || 0; },
  });
  shell.getBoundingClientRect = () => {
    const height = shell.offsetHeight;
    return { top: 100, bottom: 100 + height, height, width: 1400 };
  };
  const stack = fakeElement(shell, "relative flex flex-col h-full px-3 pt-2 bg-card");
  const layoutRow = fakeElement(stack, "flex-shrink-0 overflow-hidden");
  layoutRow.style = fakeStyle({ height: `${Math.max(0, contentHeight - 32)}px` });
  const parameterRow = fakeElement(layoutRow, "parameter-row", {
    "data-parameter-name": "HMB_PICKER_STATE",
  });
  const widgetHost = fakeElement(parameterRow, "widget-host");
  const container = fakeElement(widgetHost, "picker-container");
  container.getBoundingClientRect = () => ({
    top: 100 + inset,
    bottom: 100 + inset,
    height: 0,
    width: 1400,
  });
  const clip = fakeElement(container, "hmbvp-clip");
  const root = fakeElement(clip, "hmbvp hmbvp-compact", {
    "data-picker-view": "compact",
  });
  const spacerClasses = validSpacer
    ? "min-h-0 grow shrink-0 basis-0"
    : "min-h-0 grow shrink-0";
  const trailingSpacer = fakeElement(stack, spacerClasses, { "aria-hidden": "true" });
  const measurementLayer = fakeElement(stack, "absolute left-0 right-0 pointer-events-none");
  measurementLayer.style = fakeStyle({ visibility: "hidden" });
  container.querySelector = (selector) => {
    if (selector === ".hmbvp") return root;
    if (selector === ".hmbvp-clip") return clip;
    return null;
  };
  return {
    shell,
    stack,
    layoutRow,
    parameterRow,
    container,
    trailingSpacer,
    measurementLayer,
  };
}

assert.equal(
  typeof picker.hmbApplyVideoPickerCompactTailReclaim,
  "function",
  "compact mode must expose an exact state-row tail reclaim",
);
assert.equal(
  typeof picker.hmbRestoreVideoPickerCompactTailReclaim,
  "function",
  "expanded mode/delete must restore every reclaimed host declaration",
);

const fixture = allocatorFixture();
const shellBefore = fixture.shell.style.snapshot();
const stackBefore = fixture.stack.style.snapshot();
const measurementBefore = fixture.measurementLayer.style.snapshot();
assert.equal(
  picker.hmbApplyVideoPickerCompactTailReclaim(fixture.container, 252),
  32,
  "the Editor allocator fixture must reclaim its exact 32px compact tail",
);
assert.equal(fixture.layoutRow.style.getPropertyValue("height"), "252px");
assert.equal(fixture.layoutRow.style.getPropertyPriority("height"), "important");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("height"), "0px");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("min-height"), "0px");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("flex"), "0 0 0px");
assert.equal(fixture.shell.style.snapshot(), shellBefore, "reclaim must not mutate the React Flow shell");
assert.equal(fixture.stack.style.snapshot(), stackBefore, "reclaim must not mutate the adaptive stack");
assert.equal(
  fixture.measurementLayer.style.snapshot(),
  measurementBefore,
  "reclaim must not mutate the Editor measurement layer",
);

assert.equal(picker.hmbRestoreVideoPickerCompactTailReclaim(fixture.container), true);
assert.equal(fixture.layoutRow.style.getPropertyValue("height"), "220px");
assert.equal(fixture.layoutRow.style.getPropertyPriority("height"), "");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("height"), "");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("min-height"), "");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("flex"), "");
assert.equal(fixture.shell.style.snapshot(), shellBefore);
assert.equal(fixture.stack.style.snapshot(), stackBefore);

const compactContentHeights = [252, 438, 624, 810, 996];
for (const [shotIndex, contentHeight] of compactContentHeights.entries()) {
  const recognizedGeometry = allocatorFixture({ contentHeight });
  const expectedShellHeight = 72 + contentHeight;
  assert.equal(
    picker.hmbApplyVideoPickerCompactGeometry(recognizedGeometry.container, contentHeight),
    expectedShellHeight,
    `recognized Shot ${shotIndex + 1} must use exact inset plus compact content`,
  );
  assert.equal(
    recognizedGeometry.shell.style.getPropertyValue("height"),
    `${expectedShellHeight}px`,
  );
  assert.equal(recognizedGeometry.layoutRow.style.getPropertyValue("height"), `${contentHeight}px`);
  assert.equal(recognizedGeometry.trailingSpacer.style.getPropertyValue("height"), "0px");
  if (shotIndex > 0) {
    assert.equal(
      contentHeight - compactContentHeights[shotIndex - 1],
      186,
      "each additional Shot must add the fixed 180px row plus 6px gap",
    );
  }
  assert.equal(picker.hmbRestoreVideoPickerCompactTailReclaim(recognizedGeometry.container), true);
  assert.equal(
    recognizedGeometry.layoutRow.style.getPropertyValue("height"),
    `${contentHeight - 32}px`,
    `recognized Shot ${shotIndex + 1} must restore the Editor allocation`,
  );
  assert.equal(recognizedGeometry.trailingSpacer.style.getPropertyValue("height"), "");
}

for (const inset of [72, 100, 120]) {
  for (const [shotIndex, contentHeight] of compactContentHeights.entries()) {
    const invalid = allocatorFixture({ validSpacer: false, inset, contentHeight });
    const invalidRowBefore = invalid.layoutRow.style.snapshot();
    const invalidSpacerBefore = invalid.trailingSpacer.style.snapshot();
    const invalidStackBefore = invalid.stack.style.snapshot();
    const invalidMeasurementBefore = invalid.measurementLayer.style.snapshot();
    assert.equal(
      picker.hmbApplyVideoPickerCompactTailReclaim(invalid.container, contentHeight),
      0,
      "an unrecognized host spacer must fail closed",
    );
    assert.equal(invalid.layoutRow.style.snapshot(), invalidRowBefore);
    assert.equal(invalid.trailingSpacer.style.snapshot(), invalidSpacerBefore);

    const expectedSafeHeight = contentHeight + Math.max(108, inset + 32);
    const appliedHeight = picker.hmbApplyVideoPickerCompactGeometry(
      invalid.container,
      contentHeight,
    );
    assert.equal(
      appliedHeight,
      expectedSafeHeight,
      `unrecognized Shot ${shotIndex + 1} at inset ${inset}px must retain 32px allocator safety`,
    );
    assert.equal(invalid.shell.style.getPropertyValue("height"), `${expectedSafeHeight}px`);
    assert.equal(invalid.shell.style.getPropertyValue("min-height"), `${expectedSafeHeight}px`);
    assert.equal(invalid.shell.style.getPropertyValue("max-height"), `${expectedSafeHeight}px`);
    assert.ok(
      appliedHeight - inset - 32 >= contentHeight,
      "fail-closed shell must leave enough allocator space for the entire compact body",
    );
    assert.equal(
      invalid.layoutRow.style.snapshot(),
      invalidRowBefore,
      "fail-closed geometry must not override an unrecognized state row",
    );
    assert.equal(
      invalid.trailingSpacer.style.snapshot(),
      invalidSpacerBefore,
      "fail-closed geometry must not override an unrecognized spacer",
    );
    assert.equal(invalid.stack.style.snapshot(), invalidStackBefore);
    assert.equal(invalid.measurementLayer.style.snapshot(), invalidMeasurementBefore);
  }
}

const geometrySource = widgetSource.slice(
  widgetSource.indexOf("export function hmbApplyVideoPickerCompactGeometry"),
  widgetSource.indexOf("export function hmbRestoreVideoPickerExpandedGeometry"),
);
assert.match(
  geometrySource,
  /hmbApplyVideoPickerCompactTailReclaim\(container, contentHeight\)/,
  "every exact compact shell transaction must reclaim the same state-row tail",
);
const restoreSource = widgetSource.slice(
  widgetSource.indexOf("export function hmbRestoreVideoPickerExpandedGeometry"),
  widgetSource.indexOf("function hmbVideoPickerHybridDocument"),
);
assert.match(
  restoreSource,
  /hmbRestoreVideoPickerCompactTailReclaim\(container\)/,
  "expanded geometry must restore the host row before applying its saved shell",
);
const schedulerSource = widgetSource.slice(
  widgetSource.indexOf("export function hmbInstallVideoPickerCompactHostSizing"),
  widgetSource.indexOf("function hmbApplyPickerInitialNodeSizeOnce"),
);
assert.match(
  schedulerSource,
  /hmbApplyVideoPickerCompactGeometry\(container, compactContentHeight\)/,
  "the settled compact frame must reapply the reclaim after Editor allocation",
);
assert.doesNotMatch(
  schedulerSource,
  /secondFrame|MutationObserver|ResizeObserver/,
  "tail reclaim must not add a persistent host observer or a second layout frame",
);

console.log("HMB VideoPicker exact Editor tail reclaim regression: PASS");
