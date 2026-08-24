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

let nextFrameId = 0;
const pendingFrames = new Map();
function requestFrame(callback) {
  const id = ++nextFrameId;
  pendingFrames.set(id, callback);
  return id;
}
function cancelFrame(id) {
  pendingFrames.delete(id);
}
function flushFrames(limit = 64) {
  let executed = 0;
  while (pendingFrames.size) {
    assert.ok(executed < limit, "the HMB reconciliation frame queue must terminate");
    const [id, callback] = pendingFrames.entries().next().value;
    pendingFrames.delete(id);
    callback();
    executed += 1;
  }
  return executed;
}

class FakeMutationObserver {
  static instances = [];

  constructor(callback) {
    this.callback = callback;
    this.targets = [];
    this.connected = true;
    FakeMutationObserver.instances.push(this);
  }

  observe(target, options) {
    this.connected = true;
    this.targets.push({ target, options });
  }

  disconnect() {
    this.connected = false;
  }

  emit(records) {
    if (this.connected) this.callback(records, this);
  }
}

function activeObserver() {
  return [...FakeMutationObserver.instances].reverse().find(
    (observer) => observer.connected && observer.targets.length,
  ) || null;
}

globalThis.window = {
  MutationObserver: FakeMutationObserver,
  requestAnimationFrame: requestFrame,
  cancelAnimationFrame: cancelFrame,
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
globalThis.MutationObserver = FakeMutationObserver;
globalThis.requestAnimationFrame = requestFrame;
globalThis.cancelAnimationFrame = cancelFrame;
globalThis.document = { body: {}, documentElement: {} };

function adversarialAllocatorFixture() {
  const shell = fakeElement(null, "react-flow__node");
  shell.style = fakeStyle({ width: "900px", height: "700px" });
  Object.defineProperty(shell, "offsetWidth", { get() { return 1400; } });
  Object.defineProperty(shell, "offsetHeight", { get() { return 1200; } });
  shell.getBoundingClientRect = () => ({
    top: 100,
    bottom: 1300,
    width: 1400,
    height: 1200,
  });

  const nodeBody = fakeElement(shell, "flex flex-col h-full");
  const stack = fakeElement(nodeBody, "relative flex flex-col h-full px-3 pt-2 bg-card");
  const layoutRow = fakeElement(stack, "flex-shrink-0 overflow-hidden");
  const parameterRow = fakeElement(layoutRow, "parameter-row", {
    "data-parameter-name": "HMB_PICKER_STATE",
  });
  const widgetHost = fakeElement(parameterRow, "widget-host");
  const container = fakeElement(widgetHost, "picker-container");
  const clip = fakeElement(container, "hmbvp-clip");
  const root = fakeElement(clip, "hmbvp", { "data-picker-view": "expanded" });
  const trailingSpacer = fakeElement(
    stack,
    "min-h-0 grow shrink-0 basis-0",
    { "aria-hidden": "true" },
  );
  const measurementLayer = fakeElement(
    stack,
    "absolute left-0 right-0 pointer-events-none",
  );
  measurementLayer.style = fakeStyle({ visibility: "hidden" });

  container.__hmbVideoPickerExpanded = true;
  container.querySelector = (selector) => {
    if (selector === ".hmbvp") return root;
    if (selector === ".hmbvp-clip") return clip;
    return null;
  };
  container.getBoundingClientRect = () => ({
    top: 172,
    bottom: 792,
    width: 900,
    height: 620,
  });
  layoutRow.getBoundingClientRect = () => ({
    top: 172,
    bottom: 792,
    width: 900,
    height: 620,
  });
  Object.defineProperty(layoutRow, "offsetHeight", { get() { return 620; } });

  const applyHostGeneration = (generation) => {
    const rowHeight = 600 + (generation % 9);
    layoutRow.style.setProperty("height", `${rowHeight}px`);
    layoutRow.style.setProperty("min-height", "40px");
    layoutRow.style.setProperty("max-height", "none");
    layoutRow.style.setProperty("flex", "0 1 auto");
    trailingSpacer.style.setProperty("height", "500px");
    trailingSpacer.style.setProperty("min-height", "0px");
    trailingSpacer.style.setProperty("max-height", "none");
    trailingSpacer.style.setProperty("flex", "1 1 0%");
    container.style.setProperty("height", `${rowHeight}px`);
    container.style.setProperty("min-height", "40px");
    container.style.setProperty("max-height", "none");
    container.style.setProperty("flex", "0 1 auto");
    shell.style.setProperty("width", `${900 + (generation % 7)}px`);
    shell.style.setProperty("height", `${700 + (generation % 11)}px`);
    return {
      rowHeight: `${rowHeight}px`,
      shellWidth: `${900 + (generation % 7)}px`,
      shellHeight: `${700 + (generation % 11)}px`,
    };
  };

  return {
    shell,
    stack,
    layoutRow,
    container,
    trailingSpacer,
    applyHostGeneration,
  };
}

const fixture = adversarialAllocatorFixture();
let reconcileCalls = 0;
const cleanup = picker.hmbInstallVideoPickerExpandedHostReconciliation(
  fixture.container,
  () => {
    reconcileCalls += 1;
    picker.hmbApplyVideoPickerExpandedGeometryFloor(fixture.container);
    picker.hmbApplyVideoPickerExpandedHostHeightPropagation(
      fixture.container,
      1128,
      fixture.shell,
    );
  },
);

// Drain the install-time settle before the adversarial React allocator begins.
flushFrames();
const initiallyObservedHostTargets = new Set(
  activeObserver()?.targets?.map(({ target }) => target) || [],
);

let preservedHostGenerations = 0;
for (let generation = 1; generation <= 100; generation += 1) {
  const expected = fixture.applyHostGeneration(generation);
  const observer = activeObserver();
  // A safe implementation owns no persistent observer. Keep compatibility
  // with an implementation that observes Picker-owned DOM only, but never feed
  // host allocator mutations back into HMB reconciliation.
  observer?.emit?.([]);
  flushFrames();
  const hostStylesSurvived = (
    fixture.layoutRow.style.getPropertyValue("height") === expected.rowHeight
    && fixture.trailingSpacer.style.getPropertyValue("height") === "500px"
    && fixture.shell.style.getPropertyValue("width") === expected.shellWidth
    && fixture.shell.style.getPropertyValue("height") === expected.shellHeight
  );
  if (hostStylesSurvived) preservedHostGenerations += 1;
}

cleanup();
flushFrames();

const violations = [];
const watchedHostNames = [
  [fixture.shell, "React Flow shell"],
  [fixture.layoutRow, "allocator row"],
  [fixture.trailingSpacer, "allocator spacer"],
];
for (const [target, name] of watchedHostNames) {
  if (initiallyObservedHostTargets.has(target)) {
    violations.push(`${name} is persistently observed by the HMB reconciliation observer`);
  }
}
if (reconcileCalls > 2) {
  violations.push(
    `100 host rewrites caused ${reconcileCalls} HMB reconciliations; the bounded contract allows at most 2`,
  );
}
if (preservedHostGenerations !== 100) {
  violations.push(
    `HMB force-overwrote host-owned geometry in ${100 - preservedHostGenerations}/100 generations`,
  );
}
if (pendingFrames.size !== 0) {
  violations.push(`${pendingFrames.size} reconciliation frames remained queued after cleanup`);
}

assert.deepEqual(
  violations,
  [],
  `React #185 adversarial geometry contract failed:\n${violations.join("\n")}`,
);

console.log(
  "HMB VideoPicker React update-depth adversarial regression: PASS "
  + `(reconciliations=${reconcileCalls}, preserved=${preservedHostGenerations}/100)`,
);
