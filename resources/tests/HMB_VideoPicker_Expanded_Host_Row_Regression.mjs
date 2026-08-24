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
      return JSON.stringify({
        values: Array.from(values.entries()).sort(),
        priorities: Array.from(priorities.entries()).filter(([, value]) => value).sort(),
      });
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
    dataset: {},
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
        if (selector === ".react-flow__node" && current.classList?.contains("react-flow__node")) {
          return current;
        }
        if (
          selector === '[data-parameter-name="HMB_PICKER_STATE"]'
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

globalThis.window = {
  getComputedStyle(element) {
    return {
      display: "block",
      position: "static",
      visibility: element?.style?.getPropertyValue?.("visibility") || "visible",
      paddingTop: "0",
      paddingBottom: "0",
      borderTopWidth: "0",
      borderBottomWidth: "0",
      marginTop: "0",
      marginBottom: "0",
      height: element?.style?.getPropertyValue?.("height") || "0",
    };
  },
};
globalThis.document = { body: {}, documentElement: {} };

function expandedAllocatorFixture({
  parameterName = "HMB_PICKER_STATE",
  validSpacer = true,
  validMeasurementLayer = true,
  topInset = 72,
  containerTopInset = topInset,
  allocatedHeight = 620,
} = {}) {
  const shell = fakeElement(null, "react-flow__node");
  shell.style = fakeStyle({ height: "1200px", "min-height": "1200px" });
  Object.defineProperty(shell, "offsetHeight", { get() { return 1200; } });
  shell.getBoundingClientRect = () => ({ top: 100, bottom: 1300, height: 1200, width: 1400 });

  const nodeBody = fakeElement(shell, "flex flex-col h-full");
  const adaptiveStack = fakeElement(nodeBody, "relative flex flex-col h-full px-3 pt-2 bg-card");
  const layoutRow = fakeElement(adaptiveStack, "flex-shrink-0 overflow-hidden");
  layoutRow.style = fakeStyle({
    height: `${allocatedHeight}px`,
    "min-height": "40px",
    "max-height": "none",
    flex: "0 1 auto",
    overflow: "hidden",
  });
  Object.defineProperty(layoutRow, "offsetHeight", { get() { return allocatedHeight; } });
  layoutRow.getBoundingClientRect = () => ({
    top: 100 + topInset,
    bottom: 100 + topInset + allocatedHeight,
    height: allocatedHeight,
    width: 1400,
  });
  const parameterRow = fakeElement(layoutRow, "parameter-row", {
    "data-parameter-name": parameterName,
  });
  const widgetHost = fakeElement(parameterRow, "widget-host");
  const container = fakeElement(widgetHost, "picker-container");
  container.style = fakeStyle({
    height: `${allocatedHeight}px`,
    "min-height": "40px",
    "max-height": "none",
    flex: "0 1 auto",
    overflow: "clip",
    "box-sizing": "content-box",
  });
  container.__hmbVideoPickerExpanded = true;
  container.getBoundingClientRect = () => ({
    top: 100 + containerTopInset,
    bottom: 100 + containerTopInset + allocatedHeight,
    height: allocatedHeight,
    width: 1400,
  });
  const clip = fakeElement(container, "hmbvp-clip");
  const root = fakeElement(clip, "hmbvp", { "data-picker-view": "expanded" });
  const spacerClasses = validSpacer
    ? "min-h-0 grow shrink-0 basis-0"
    : "min-h-0 grow shrink-0";
  const trailingSpacer = fakeElement(adaptiveStack, spacerClasses, { "aria-hidden": "true" });
  const measurementClasses = validMeasurementLayer
    ? "absolute left-0 right-0 pointer-events-none"
    : "absolute left-0 pointer-events-none";
  const measurementLayer = fakeElement(adaptiveStack, measurementClasses);
  measurementLayer.style = fakeStyle({ visibility: "hidden" });
  container.querySelector = (selector) => {
    if (selector === ".hmbvp") return root;
    if (selector === ".hmbvp-clip") return clip;
    return null;
  };
  return {
    shell,
    nodeBody,
    adaptiveStack,
    layoutRow,
    parameterRow,
    widgetHost,
    container,
    clip,
    root,
    trailingSpacer,
    measurementLayer,
    requiredHeight: 1200 - containerTopInset,
    rowAvailableHeight: 1200 - topInset,
  };
}

assert.equal(
  typeof picker.hmbApplyVideoPickerExpandedHostHeightPropagation,
  "function",
  "expanded mode must expose exact HMB_PICKER_STATE host-row propagation",
);
assert.equal(
  typeof picker.hmbRestoreVideoPickerExpandedHostHeightPropagation,
  "function",
  "compact transition/delete must expose exact expanded host-row restoration",
);
assert.equal(
  typeof picker.hmbInstallVideoPickerExpandedHostReconciliation,
  "function",
  "expanded mount must expose settled reconciliation for allocator rewrites and branch replacement",
);

const fixture = expandedAllocatorFixture();
const broadSnapshots = new Map([
  [fixture.shell, fixture.shell.style.snapshot()],
  [fixture.nodeBody, fixture.nodeBody.style.snapshot()],
  [fixture.adaptiveStack, fixture.adaptiveStack.style.snapshot()],
  [fixture.parameterRow, fixture.parameterRow.style.snapshot()],
  [fixture.widgetHost, fixture.widgetHost.style.snapshot()],
  [fixture.measurementLayer, fixture.measurementLayer.style.snapshot()],
]);
const rowBefore = fixture.layoutRow.style.snapshot();
const spacerBefore = fixture.trailingSpacer.style.snapshot();
const containerBefore = fixture.container.style.snapshot();
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    fixture.container,
    fixture.requiredHeight,
    fixture.shell,
  ),
  fixture.requiredHeight,
  "the live 620px overflow-hidden state row must grow to the shell's full available height",
);
assert.equal(fixture.layoutRow.style.getPropertyValue("height"), `${fixture.requiredHeight}px`);
assert.equal(fixture.layoutRow.style.getPropertyPriority("height"), "important");
assert.equal(fixture.layoutRow.style.getPropertyValue("min-height"), `${fixture.requiredHeight}px`);
assert.equal(fixture.layoutRow.style.getPropertyPriority("min-height"), "important");
assert.equal(fixture.layoutRow.style.getPropertyValue("max-height"), `${fixture.requiredHeight}px`);
assert.equal(fixture.layoutRow.style.getPropertyPriority("max-height"), "important");
assert.equal(fixture.layoutRow.style.getPropertyValue("flex"), `0 0 ${fixture.requiredHeight}px`);
assert.equal(fixture.layoutRow.style.getPropertyPriority("flex"), "important");
assert.equal(fixture.layoutRow.style.getPropertyValue("overflow"), "hidden");
assert.equal(fixture.layoutRow.style.getPropertyPriority("overflow"), "important");
assert.equal(fixture.container.style.getPropertyValue("height"), `${fixture.requiredHeight}px`);
assert.equal(fixture.container.style.getPropertyPriority("height"), "important");
assert.equal(fixture.container.style.getPropertyValue("min-height"), `${fixture.requiredHeight}px`);
assert.equal(fixture.container.style.getPropertyValue("max-height"), `${fixture.requiredHeight}px`);
assert.equal(fixture.container.style.getPropertyValue("flex"), `0 0 ${fixture.requiredHeight}px`);
assert.equal(fixture.container.style.getPropertyValue("overflow"), "hidden");
assert.equal(fixture.container.style.getPropertyValue("box-sizing"), "border-box");
assert.equal(
  fixture.container.getAttribute("data-hmb-picker-height-propagation"),
  "expanded-container",
  "the exact widget container must join the reversible ownership transaction",
);
assert.equal(
  fixture.layoutRow.getAttribute("data-hmb-picker-height-propagation"),
  "expanded",
  "the exact state row must carry a scoped ownership marker while overridden",
);
assert.equal(fixture.trailingSpacer.style.getPropertyValue("height"), "0px");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("min-height"), "0px");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("max-height"), "0px");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("flex"), "0 0 0px");
assert.equal(fixture.trailingSpacer.style.getPropertyValue("overflow"), "hidden");
assert.equal(
  fixture.trailingSpacer.getAttribute("data-hmb-picker-height-propagation"),
  "expanded-spacer",
  "the exact spacer must carry the same scoped ownership marker while overridden",
);
for (const [element, snapshot] of broadSnapshots) {
  assert.equal(
    element.style.snapshot(),
    snapshot,
    "only the exact widget container, state layout row, and trailing spacer may be mutated",
  );
}

assert.equal(picker.hmbRestoreVideoPickerExpandedHostHeightPropagation(fixture.container), true);
assert.equal(fixture.container.style.snapshot(), containerBefore, "exact container declarations must restore exactly");
assert.equal(fixture.layoutRow.style.snapshot(), rowBefore, "expanded row declarations must restore exactly");
assert.equal(fixture.trailingSpacer.style.snapshot(), spacerBefore, "expanded spacer declarations must restore exactly");
assert.equal(fixture.layoutRow.hasAttribute("data-hmb-picker-height-propagation"), false);
assert.equal(fixture.trailingSpacer.hasAttribute("data-hmb-picker-height-propagation"), false);
assert.equal(fixture.container.hasAttribute("data-hmb-picker-height-propagation"), false);
assert.equal(picker.hmbRestoreVideoPickerExpandedHostHeightPropagation(fixture.container), false);

// The Editor can wrap the custom widget a few pixels below the exact layout
// row. Propagation is row-bottom based, so that wrapper inset must be retained.
const insetFixture = expandedAllocatorFixture({ topInset: 72, containerTopInset: 84 });
assert.equal(insetFixture.requiredHeight, 1116);
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    insetFixture.container,
    insetFixture.requiredHeight,
    insetFixture.shell,
  ),
  insetFixture.rowAvailableHeight,
  "the state row must include the 12px wrapper inset while the widget keeps its own available height",
);
assert.equal(
  insetFixture.layoutRow.style.getPropertyValue("height"),
  `${insetFixture.rowAvailableHeight}px`,
);
assert.equal(
  insetFixture.container.style.getPropertyValue("height"),
  `${insetFixture.requiredHeight}px`,
  "the exact container must stop at its own shell-available height below the wrapper inset",
);
assert.equal(picker.hmbRestoreVideoPickerExpandedHostHeightPropagation(insetFixture.container), true);

// React's allocator can rewrite inline declarations on the same mounted row
// after the first widget sizing pass. A subsequent pass must capture that new
// host-authored state, reapply the exact override, and restore to the newer host
// values instead of the stale first-mount snapshot.
const overwrittenFixture = expandedAllocatorFixture();
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    overwrittenFixture.container,
    overwrittenFixture.requiredHeight,
    overwrittenFixture.shell,
  ),
  overwrittenFixture.rowAvailableHeight,
);
const overwrittenHostRowValues = {
  height: "644px",
  "min-height": "44px",
  "max-height": "900px",
  flex: "0 1 auto",
  overflow: "clip",
};
const overwrittenHostSpacerValues = {
  height: "484px",
  "min-height": "12px",
  "max-height": "none",
  flex: "1 1 0%",
  overflow: "visible",
};
const overwrittenHostContainerValues = {
  height: "636px",
  "min-height": "36px",
  "max-height": "880px",
  flex: "0 1 auto",
  overflow: "visible",
  "box-sizing": "content-box",
};
for (const [property, value] of Object.entries(overwrittenHostRowValues)) {
  overwrittenFixture.layoutRow.style.setProperty(property, value);
}
for (const [property, value] of Object.entries(overwrittenHostSpacerValues)) {
  overwrittenFixture.trailingSpacer.style.setProperty(property, value);
}
for (const [property, value] of Object.entries(overwrittenHostContainerValues)) {
  overwrittenFixture.container.style.setProperty(property, value);
}
const overwrittenRowBeforeReapply = overwrittenFixture.layoutRow.style.snapshot();
const overwrittenSpacerBeforeReapply = overwrittenFixture.trailingSpacer.style.snapshot();
const overwrittenContainerBeforeReapply = overwrittenFixture.container.style.snapshot();
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    overwrittenFixture.container,
    overwrittenFixture.requiredHeight,
    overwrittenFixture.shell,
  ),
  overwrittenFixture.rowAvailableHeight,
  "a same-DOM allocator overwrite must be repaired on the next sizing pass",
);
assert.equal(
  overwrittenFixture.layoutRow.style.getPropertyValue("height"),
  `${overwrittenFixture.rowAvailableHeight}px`,
);
assert.equal(overwrittenFixture.layoutRow.style.getPropertyPriority("height"), "important");
assert.equal(overwrittenFixture.trailingSpacer.style.getPropertyValue("height"), "0px");
assert.equal(
  overwrittenFixture.container.style.getPropertyValue("height"),
  `${overwrittenFixture.requiredHeight}px`,
);
assert.equal(overwrittenFixture.container.style.getPropertyPriority("height"), "important");
assert.equal(picker.hmbRestoreVideoPickerExpandedHostHeightPropagation(overwrittenFixture.container), true);
assert.equal(
  overwrittenFixture.layoutRow.style.snapshot(),
  overwrittenRowBeforeReapply,
  "cleanup must restore the allocator's newer same-DOM row declarations",
);
assert.equal(
  overwrittenFixture.trailingSpacer.style.snapshot(),
  overwrittenSpacerBeforeReapply,
  "cleanup must restore the allocator's newer same-DOM spacer declarations",
);
assert.equal(
  overwrittenFixture.container.style.snapshot(),
  overwrittenContainerBeforeReapply,
  "cleanup must restore the allocator's newer same-DOM container declarations",
);

// The adaptive allocator may replace the whole state row/spacer pair while
// keeping the widget container alive. Re-discovery must restore the detached
// record safely and transfer ownership to the newly recognized exact pair.
const replacedFixture = expandedAllocatorFixture();
const detachedRowBefore = replacedFixture.layoutRow.style.snapshot();
const detachedSpacerBefore = replacedFixture.trailingSpacer.style.snapshot();
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    replacedFixture.container,
    replacedFixture.requiredHeight,
    replacedFixture.shell,
  ),
  replacedFixture.rowAvailableHeight,
);
const detachedLayoutRow = replacedFixture.layoutRow;
const detachedSpacer = replacedFixture.trailingSpacer;
const replacementHostContainerValues = {
  height: "604px",
  "min-height": "32px",
  "max-height": "840px",
  flex: "0 1 auto",
  overflow: "clip",
  "box-sizing": "content-box",
};
for (const [property, value] of Object.entries(replacementHostContainerValues)) {
  replacedFixture.container.style.setProperty(property, value);
}
const replacementContainerBefore = replacedFixture.container.style.snapshot();
const replacementLayoutRow = fakeElement(
  replacedFixture.adaptiveStack,
  "flex-shrink-0 overflow-hidden",
);
replacementLayoutRow.style = fakeStyle({
  height: "588px",
  "min-height": "40px",
  "max-height": "none",
  flex: "0 1 auto",
  overflow: "hidden",
});
Object.defineProperty(replacementLayoutRow, "offsetHeight", { get() { return 588; } });
replacementLayoutRow.getBoundingClientRect = () => ({
  top: 172,
  bottom: 760,
  height: 588,
  width: 1400,
});
detachedLayoutRow.children = [];
replacedFixture.parameterRow.parentElement = replacementLayoutRow;
replacementLayoutRow.children.push(replacedFixture.parameterRow);
const replacementSpacer = fakeElement(
  replacedFixture.adaptiveStack,
  "min-h-0 grow shrink-0 basis-0",
  { "aria-hidden": "true" },
);
const replacementMeasurement = fakeElement(
  replacedFixture.adaptiveStack,
  "absolute left-0 right-0 pointer-events-none",
);
replacementMeasurement.style = fakeStyle({ visibility: "hidden" });
replacedFixture.adaptiveStack.children = [
  replacementLayoutRow,
  replacementSpacer,
  replacementMeasurement,
];
const replacementRowBefore = replacementLayoutRow.style.snapshot();
const replacementSpacerBefore = replacementSpacer.style.snapshot();
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    replacedFixture.container,
    replacedFixture.requiredHeight,
    replacedFixture.shell,
  ),
  replacedFixture.rowAvailableHeight,
  "a replacement exact row/spacer pair must be rediscovered and filled",
);
assert.equal(detachedLayoutRow.style.snapshot(), detachedRowBefore);
assert.equal(detachedSpacer.style.snapshot(), detachedSpacerBefore);
assert.equal(detachedLayoutRow.hasAttribute("data-hmb-picker-height-propagation"), false);
assert.equal(detachedSpacer.hasAttribute("data-hmb-picker-height-propagation"), false);
assert.equal(
  replacementLayoutRow.style.getPropertyValue("height"),
  `${replacedFixture.rowAvailableHeight}px`,
);
assert.equal(replacementLayoutRow.style.getPropertyPriority("height"), "important");
assert.equal(replacementSpacer.style.getPropertyValue("height"), "0px");
assert.equal(
  replacedFixture.container.style.getPropertyValue("height"),
  `${replacedFixture.requiredHeight}px`,
  "row replacement must reapply the exact container height in the new transaction",
);
assert.equal(
  replacementLayoutRow.getAttribute("data-hmb-picker-height-propagation"),
  "expanded",
);
assert.equal(picker.hmbRestoreVideoPickerExpandedHostHeightPropagation(replacedFixture.container), true);
assert.equal(
  replacedFixture.container.style.snapshot(),
  replacementContainerBefore,
  "the replacement transaction must restore the latest host-authored container values",
);
assert.equal(replacementLayoutRow.style.snapshot(), replacementRowBefore);
assert.equal(replacementSpacer.style.snapshot(), replacementSpacerBefore);

// A compact transition is itself a restore boundary. It must not leave an
// expanded row basis behind to corrupt the compact one-shot shell height.
fixture.container.__hmbVideoPickerExpanded = true;
fixture.root.setAttribute("data-picker-view", "expanded");
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    fixture.container,
    fixture.requiredHeight,
    fixture.shell,
  ),
  fixture.requiredHeight,
);
fixture.container.__hmbVideoPickerExpanded = false;
fixture.root.setAttribute("data-picker-view", "compact");
assert.equal(
  picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
    fixture.container,
    fixture.requiredHeight,
    fixture.shell,
  ),
  0,
  "compact mode must reject expanded propagation",
);
assert.equal(fixture.layoutRow.style.snapshot(), rowBefore);
assert.equal(fixture.trailingSpacer.style.snapshot(), spacerBefore);
assert.equal(fixture.container.style.snapshot(), containerBefore);

for (const invalidOptions of [
  { parameterName: "MAYA_SCENE" },
  { validSpacer: false },
  { validMeasurementLayer: false },
]) {
  const invalid = expandedAllocatorFixture(invalidOptions);
  const invalidSnapshots = new Map([
    [invalid.shell, invalid.shell.style.snapshot()],
    [invalid.nodeBody, invalid.nodeBody.style.snapshot()],
    [invalid.adaptiveStack, invalid.adaptiveStack.style.snapshot()],
    [invalid.layoutRow, invalid.layoutRow.style.snapshot()],
    [invalid.parameterRow, invalid.parameterRow.style.snapshot()],
    [invalid.widgetHost, invalid.widgetHost.style.snapshot()],
    [invalid.container, invalid.container.style.snapshot()],
    [invalid.trailingSpacer, invalid.trailingSpacer.style.snapshot()],
    [invalid.measurementLayer, invalid.measurementLayer.style.snapshot()],
  ]);
  assert.equal(
    picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
      invalid.container,
      invalid.requiredHeight,
      invalid.shell,
    ),
    0,
    "an unrecognized Editor DOM signature must fail closed",
  );
  for (const [element, snapshot] of invalidSnapshots) {
    assert.equal(element.style.snapshot(), snapshot, "fail-closed propagation must not mutate host DOM");
  }
}

assert.match(
  widgetSource,
  /function hmbApplyPickerHostSizing\([\s\S]*?hmbApplyVideoPickerExpandedHostHeightPropagation\(/,
  "every expanded Picker sizing pass must propagate through the exact state row",
);
assert.match(
  widgetSource,
  /function hmbApplyVideoPickerCompactHostSizing\([\s\S]*?hmbRestoreVideoPickerExpandedHostHeightPropagation\(container\)/,
  "compact sizing must restore expanded host-row declarations before measuring",
);
const factoryStart = widgetSource.indexOf("export default function");
const cleanupStart = widgetSource.indexOf("const cleanup = () => {", factoryStart);
const cleanupEnd = widgetSource.indexOf("container.__hmbVideoPickerCleanup = cleanup;", cleanupStart);
const cleanupSource = widgetSource.slice(cleanupStart, cleanupEnd);
assert.match(
  cleanupSource,
  /hmbRestoreVideoPickerExpandedHostHeightPropagation\(container\)/,
  "factory cleanup must restore exact host-row declarations",
);
assert.match(
  widgetSource,
  /hmbInstallVideoPickerExpandedHostReconciliation\(\s*container,\s*\(\) => \{\s*applyPickerFitNow\(true\);[\s\S]*?activeCleanup,\s*\)/,
  "the live factory must install settled allocator reconciliation in its cleanup scope",
);

console.log("HMB VideoPicker expanded exact host-row propagation regression: PASS");
