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

for (const exportedName of [
  "hmbInstallVideoPickerMountedRootGuard",
  "hmbMountVideoPickerHostMeasurement",
  "hmbRememberVideoPickerViewMode",
  "hmbSetVideoPickerHybridView",
  "hmbSyncVideoPickerHostMeasurement",
  "hmbVideoPickerHasMountedBody",
  "hmbVideoPickerStoredViewMode",
]) {
  assert.equal(typeof picker[exportedName], "function", `${exportedName} must remain exported.`);
}

function fakeStyle(initial = {}) {
  const values = new Map();
  for (const [name, value] of Object.entries(initial)) values.set(String(name), String(value));
  const style = {
    setProperty(name, value) { values.set(String(name), String(value)); },
    getPropertyValue(name) { return values.get(String(name)) || ""; },
    getPropertyPriority() { return ""; },
    removeProperty(name) {
      const previous = values.get(String(name)) || "";
      values.delete(String(name));
      return previous;
    },
  };
  for (const name of ["display", "visibility", "height", "minHeight", "maxHeight"]) {
    Object.defineProperty(style, name, {
      configurable: true,
      enumerable: true,
      get() {
        const dashed = name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
        return values.get(name) || values.get(dashed) || "";
      },
      set(value) { values.set(name, String(value)); },
    });
  }
  return style;
}

function fakeClassList(owner, initial = []) {
  const values = new Set(initial.flatMap((value) => String(value || "").split(/\s+/)).filter(Boolean));
  const sync = () => { owner.className = [...values].join(" "); };
  return {
    add(...names) { names.forEach((name) => values.add(String(name))); sync(); },
    remove(...names) { names.forEach((name) => values.delete(String(name))); sync(); },
    contains(name) { return values.has(String(name)); },
    values() { return [...values]; },
  };
}

function dataKey(name) {
  return String(name).slice(5).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
}

function parseSimpleSelector(selector) {
  let text = String(selector || "").trim();
  if (text.startsWith(":scope > ")) text = text.slice(9).trim();
  const attributes = [];
  text = text.replace(/\[([^=\]]+)(?:=['\"]?([^'\"\]]*)['\"]?)?\]/g, (_match, name, value) => {
    attributes.push({ name, value: value === undefined ? null : value });
    return "";
  });
  const classes = [...text.matchAll(/\.([A-Za-z0-9_-]+)/g)].map((match) => match[1]);
  const tag = text.replace(/\.[A-Za-z0-9_-]+/g, "").trim().toLowerCase();
  return { tag, classes, attributes };
}

function matchesSimple(element, selector) {
  if (!element || element.nodeType !== 1) return false;
  const { tag, classes, attributes } = parseSimpleSelector(selector);
  if (tag && String(element.tagName || "").toLowerCase() !== tag) return false;
  if (classes.some((name) => !element.classList.contains(name))) return false;
  return attributes.every(({ name, value }) => (
    element.hasAttribute(name) && (value === null || element.getAttribute(name) === value)
  ));
}

class FakeNode {
  constructor(nodeType, ownerDocument) {
    this.nodeType = nodeType;
    this.ownerDocument = ownerDocument;
    this.parentElement = null;
    this.parentNode = null;
    this.childNodes = [];
    this.children = this.childNodes;
  }

  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes.at(-1) || null; }
  get nextSibling() {
    const siblings = this.parentNode?.childNodes || [];
    const index = siblings.indexOf(this);
    return index >= 0 ? siblings[index + 1] || null : null;
  }
  get isConnected() {
    let current = this;
    while (current) {
      if (current === this.ownerDocument?.body) return true;
      current = current.parentNode || current.parentElement;
    }
    return false;
  }

  _attachAt(node, index) {
    if (!node) return node;
    if (node.nodeType === 11) {
      for (const child of [...node.childNodes]) this._attachAt(child, index++);
      return node;
    }
    node.parentNode?.removeChild?.(node);
    node.parentNode = this;
    node.parentElement = this.nodeType === 1 ? this : null;
    node.ownerDocument ||= this.ownerDocument;
    this.childNodes.splice(index, 0, node);
    return node;
  }

  appendChild(node) { return this._attachAt(node, this.childNodes.length); }
  append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
  insertBefore(node, reference) {
    const index = reference ? this.childNodes.indexOf(reference) : this.childNodes.length;
    return this._attachAt(node, index < 0 ? this.childNodes.length : index);
  }
  removeChild(node) {
    const index = this.childNodes.indexOf(node);
    if (index >= 0) this.childNodes.splice(index, 1);
    node.parentNode = null;
    node.parentElement = null;
    return node;
  }
  replaceChildren(...nodes) {
    [...this.childNodes].forEach((node) => this.removeChild(node));
    this.append(...nodes);
  }
  remove() { this.parentNode?.removeChild?.(this); }
  contains(candidate) {
    if (candidate === this) return true;
    return this.childNodes.some((child) => child.contains?.(candidate));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) {
    const direct = String(selector).trim().startsWith(":scope > ");
    const effective = direct ? String(selector).trim().slice(9).trim() : selector;
    const candidates = direct
      ? [...this.childNodes]
      : (() => {
        const result = [];
        const visit = (parent) => {
          for (const child of parent.childNodes || []) {
            result.push(child);
            visit(child);
          }
        };
        visit(this);
        return result;
      })();
    return candidates.filter((candidate) => matchesSimple(candidate, effective));
  }
}

class FakeElement extends FakeNode {
  constructor(tagName, ownerDocument, className = "") {
    super(1, ownerDocument);
    this.tagName = String(tagName || "div").toUpperCase();
    this.attributesMap = new Map();
    this.dataset = {};
    this.style = fakeStyle();
    this.className = className;
    this.classList = fakeClassList(this, [className]);
    this.hidden = false;
    this.offsetHeight = 100;
  }
  setAttribute(name, value) {
    this.attributesMap.set(String(name), String(value));
    if (String(name) === "class") {
      this.className = String(value);
      this.classList = fakeClassList(this, [value]);
    }
    if (String(name).startsWith("data-")) this.dataset[dataKey(name)] = String(value);
  }
  getAttribute(name) { return this.attributesMap.get(String(name)) || ""; }
  hasAttribute(name) { return this.attributesMap.has(String(name)); }
  removeAttribute(name) {
    this.attributesMap.delete(String(name));
    if (String(name).startsWith("data-")) delete this.dataset[dataKey(name)];
  }
  closest(selector) {
    let current = this;
    while (current) {
      if (matchesSimple(current, selector)) return current;
      current = current.parentElement;
    }
    return null;
  }
  getBoundingClientRect() {
    const height = Number.parseFloat(this.style.height || this.style.getPropertyValue("height"))
      || Number(this.offsetHeight)
      || 0;
    return { top: 0, bottom: height, height, width: 1400 };
  }
  getRootNode() { return this.ownerDocument; }
  addEventListener() {}
  removeEventListener() {}
}

class FakeFragment extends FakeNode {
  constructor(ownerDocument) { super(11, ownerDocument); }
}

const documentStub = {
  body: null,
  documentElement: null,
  head: null,
  defaultView: null,
  createElement(tagName) { return new FakeElement(tagName, documentStub); },
  createDocumentFragment() { return new FakeFragment(documentStub); },
};
documentStub.body = new FakeElement("body", documentStub);
documentStub.documentElement = documentStub.body;
documentStub.head = new FakeElement("head", documentStub);
documentStub.body.append(documentStub.head);

const observers = [];
class TestMutationObserver {
  constructor(callback) {
    this.callback = callback;
    this.disconnected = false;
    this.observed = [];
    observers.push(this);
  }
  observe(target, options) { this.observed.push({ target, options }); }
  disconnect() { this.disconnected = true; }
  flush() { if (!this.disconnected) this.callback([], this); }
}

let nextFrame = 1;
const pendingFrames = new Map();
const requestFrame = (callback) => {
  const handle = nextFrame++;
  pendingFrames.set(handle, callback);
  return handle;
};
const cancelFrame = (handle) => pendingFrames.delete(handle);
const flushFrames = () => {
  for (let pass = 0; pass < 20 && pendingFrames.size; pass += 1) {
    const callbacks = [...pendingFrames.entries()];
    pendingFrames.clear();
    callbacks.forEach(([_handle, callback]) => callback(Date.now()));
  }
  assert.equal(pendingFrames.size, 0, "Picker lifecycle checks must settle without a RAF loop.");
};

let clockMs = 100_000;
let nextTimer = 1;
const pendingTimers = new Map();
const setTimer = (callback, delay = 0) => {
  const handle = nextTimer++;
  pendingTimers.set(handle, { callback, due: clockMs + Math.max(0, Number(delay) || 0) });
  return handle;
};
const clearTimer = (handle) => pendingTimers.delete(handle);
const advanceTime = (milliseconds) => {
  clockMs += Math.max(0, Number(milliseconds) || 0);
  for (let pass = 0; pass < 50; pass += 1) {
    const due = [...pendingTimers.entries()]
      .filter(([_handle, timer]) => timer.due <= clockMs)
      .sort((left, right) => left[1].due - right[1].due);
    if (!due.length) break;
    for (const [handle, timer] of due) {
      pendingTimers.delete(handle);
      timer.callback();
    }
  }
};

documentStub.defaultView = {
  MutationObserver: TestMutationObserver,
  setTimeout: setTimer,
  clearTimeout: clearTimer,
  getComputedStyle(element) {
    return {
      display: element?.hidden ? "none" : (element?.style?.display || "block"),
      visibility: element?.style?.visibility || "visible",
    };
  },
};

function element(tagName, className = "", attributes = {}) {
  const node = new FakeElement(tagName, documentStub, className);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  return node;
}

function makePickerInstance(nodeId, runtimeId, workflowRoot = null) {
  const shell = element("div", "react-flow__node", { "data-id": nodeId });
  shell.style.height = "1200px";
  shell.style.minHeight = "1151px";
  shell.offsetHeight = 1200;
  const scope = workflowRoot || documentStub.body;
  if (workflowRoot && !workflowRoot.isConnected) documentStub.body.append(workflowRoot);
  scope.append(shell);

  const measurementLayer = element(
    "div",
    "absolute left-0 right-0 pointer-events-none",
  );
  measurementLayer.style.visibility = "hidden";
  const measurementContainer = element("div", "raw-widget measurement");
  measurementLayer.append(measurementContainer);
  shell.append(measurementLayer);

  const liveLayer = element("div", "relative live-layer");
  const liveContainer = element("div", "raw-widget live");
  liveLayer.append(liveContainer);
  shell.append(liveLayer);

  const attachExpandedDashboard = () => {
    liveContainer.replaceChildren();
    const authoredStyle = element("style");
    const clip = element("div", "hmbvp-clip");
    clip.setAttribute("data-picker-view", "expanded");
    const root = element("div", "hmbvp", { "data-picker-view": "expanded" });
    const header = element("header", "app-header top", {
      "data-picker-toggle-surface": "header",
    });
    const sceneBar = element("div", "scene-load-bar");
    const mainGrid = element("main", "main-grid");
    sceneBar.offsetHeight = 50;
    mainGrid.offsetHeight = 900;
    root.append(header, sceneBar, mainGrid);
    clip.append(root);
    liveContainer.append(authoredStyle, clip);
    return { authoredStyle, clip, root, header, sceneBar, mainGrid };
  };

  return {
    nodeId,
    runtimeId,
    shell,
    measurementLayer,
    measurementContainer,
    liveContainer,
    attachExpandedDashboard,
    dashboard: attachExpandedDashboard(),
  };
}

function expandedBodyHealthy(instance) {
  const clip = instance.liveContainer.querySelector(".hmbvp-clip");
  const root = clip?.querySelector(".hmbvp");
  const scene = root?.querySelector(":scope > .scene-load-bar");
  const main = root?.querySelector(":scope > .main-grid");
  const visible = (node) => !!node
    && node.isConnected
    && node.hidden !== true
    && node.style.display !== "none"
    && node.style.visibility !== "hidden";
  return visible(clip)
    && visible(root)
    && visible(scene)
    && visible(main)
    && scene.parentElement === root
    && main.parentElement === root
    && root.childNodes.indexOf(main) > root.childNodes.indexOf(scene);
}

function compactBodyHealthy(instance) {
  const clip = instance.liveContainer.querySelector(".hmbvp-clip");
  const root = clip?.querySelector(".hmbvp");
  const summary = root?.querySelector(":scope > [data-picker-compact-summary='true']");
  return !!summary
    && summary.isConnected
    && summary.hidden !== true
    && summary.style.display !== "none"
    && summary.style.visibility !== "hidden"
    && summary.parentElement === root;
}

function prepareCompactFragment(instance) {
  const fragment = documentStub.createDocumentFragment();
  const style = element("style", "", { "data-picker-compact-style": "true" });
  const summary = element("section", "compact-current-videos", {
    "data-picker-compact-summary": "true",
  });
  summary.offsetHeight = 180;
  fragment.append(style, summary);
  instance.liveContainer.__hmbVideoPickerCompactFragment = fragment;
}

function installRecoveryGuard(instance) {
  let recoveries = 0;
  const cleanupList = [];
  const guard = picker.hmbInstallVideoPickerMountedRootGuard(
    instance.liveContainer,
    cleanupList,
    () => {
      recoveries += 1;
      instance.dashboard = instance.attachExpandedDashboard();
      picker.hmbRememberVideoPickerViewMode(instance.liveContainer, true);
      return true;
    },
  );
  return { guard, cleanupList, recoveries: () => recoveries };
}

const savedGlobals = Object.fromEntries([
  "document", "window", "MutationObserver", "requestAnimationFrame", "cancelAnimationFrame",
].map((name) => [name, globalThis[name]]));
const savedDateNow = Date.now;

try {
  globalThis.document = documentStub;
  globalThis.window = documentStub.defaultView;
  globalThis.MutationObserver = TestMutationObserver;
  globalThis.requestAnimationFrame = requestFrame;
  globalThis.cancelAnimationFrame = cancelFrame;
  Date.now = () => clockMs;

  // Two genuine Picker instances may share a restored runtime id. Their view
  // state is node-local, while a hidden measurement clone and the live row of
  // one node intentionally share the same data-id identity.
  const first = makePickerInstance("picker-node-1", "runtime-shared");
  const second = makePickerInstance("picker-node-2", "runtime-shared");
  const firstMeasurement = picker.hmbMountVideoPickerHostMeasurement(
    first.measurementContainer,
    { value: { runtime_instance_id: first.runtimeId, picker_shots: [{}] } },
  );
  const secondMeasurement = picker.hmbMountVideoPickerHostMeasurement(
    second.measurementContainer,
    { value: { runtime_instance_id: second.runtimeId, picker_shots: [{}] } },
  );
  flushFrames();
  assert.ok(first.measurementContainer.querySelector("[data-hmb-video-picker-measurement-box]"));
  assert.ok(second.measurementContainer.querySelector("[data-hmb-video-picker-measurement-box]"));

  picker.hmbBindVideoPickerRuntimeIdentity(first.liveContainer, first.runtimeId);
  picker.hmbBindVideoPickerRuntimeIdentity(second.liveContainer, second.runtimeId);
  picker.hmbRememberVideoPickerViewMode(first.liveContainer, true);
  picker.hmbRememberVideoPickerViewMode(second.liveContainer, true);
  assert.equal(picker.hmbVideoPickerStoredViewMode(first.measurementContainer), true);
  assert.equal(picker.hmbVideoPickerStoredViewMode(second.measurementContainer), true);
  assert.equal(picker.hmbSyncVideoPickerHostMeasurement(
    first.liveContainer,
    { runtime_instance_id: first.runtimeId, picker_shots: [{}, {}] },
    true,
  ), 1);
  assert.equal(expandedBodyHealthy(first), true, "First Picker must initially expose its expanded body.");
  assert.equal(expandedBodyHealthy(second), true, "Second Picker must initially expose its expanded body.");
  second.dashboard.mainGrid.classList.add("hidden");
  assert.equal(picker.hmbVideoPickerHasMountedBody(second.liveContainer), false);
  second.dashboard.mainGrid.classList.remove("hidden");
  second.dashboard.mainGrid.setAttribute("aria-hidden", "true");
  assert.equal(picker.hmbVideoPickerHasMountedBody(second.liveContainer), false);
  second.dashboard.mainGrid.removeAttribute("aria-hidden");
  assert.equal(picker.hmbVideoPickerHasMountedBody(second.liveContainer), true);

  // A same-runtime sibling cannot inherit a compact choice from another data-id.
  picker.hmbRememberVideoPickerViewMode(first.liveContainer, false);
  assert.equal(picker.hmbVideoPickerStoredViewMode(second.liveContainer), true);
  picker.hmbRememberVideoPickerViewMode(first.liveContainer, true);

  const firstRecovery = installRecoveryGuard(first);
  const secondRecovery = installRecoveryGuard(second);
  const firstLifecycleObserver = observers.find((observer) => observer.observed.some(
    ({ target }) => target === first.liveContainer,
  ));
  assert.ok(firstLifecycleObserver, "The first live Picker must install a lifecycle observer.");
  assert.ok(
    firstLifecycleObserver.observed.some(
      ({ target, options }) => target === first.liveContainer
        && options?.childList === true
        && options?.subtree === true
        && options?.attributes === true
        && ["hidden", "aria-hidden", "style", "class", "data-picker-view"].every(
          (name) => options?.attributeFilter?.includes?.(name),
        ),
    ),
    "Nested body removal and visibility/view attribute changes must be observed.",
  );
  assert.equal(firstRecovery.guard.inspect(), false, "A complete expanded dashboard needs no recovery.");
  assert.equal(secondRecovery.guard.inspect(), false, "A complete sibling dashboard needs no recovery.");

  // Exact screenshot failure: clip/root/header survive, but the authored body
  // disappears. Root-only guards misclassify this as healthy and leave a tall
  // black shell. Recovery must key off the view's substantive body instead.
  first.dashboard.sceneBar.remove();
  first.dashboard.mainGrid.remove();
  assert.equal(expandedBodyHealthy(first), false);
  firstLifecycleObserver.flush();
  flushFrames();
  assert.equal(firstRecovery.recoveries(), 1);
  assert.equal(expandedBodyHealthy(first), true, "Recovery must attach a visible expanded body to the live root.");
  assert.equal(expandedBodyHealthy(second), true, "Recovering one Picker must not detach its sibling body.");

  // Cold compact mount retains the authored expanded subtree in a fragment.
  // A props update and the following expand must put that exact body back in
  // the live DOM, not leave the header above an empty black tail.
  prepareCompactFragment(first);
  assert.equal(picker.hmbSetVideoPickerHybridView(first.liveContainer, false), true);
  assert.equal(compactBodyHealthy(first), true, "Compact mount must expose its summary body.");
  assert.equal(expandedBodyHealthy(first), false, "Expanded body is intentionally detached in compact mode.");
  assert.equal(
    picker.hmbSetVideoPickerHybridView(first.liveContainer, false),
    true,
    "A duplicate compact request must be an idempotent no-op.",
  );
  assert.equal(compactBodyHealthy(first), true, "Duplicate compact requests cannot consume their own summary.");
  firstMeasurement.update({
    value: { runtime_instance_id: "runtime-after-props-update", picker_shots: [{}, {}, {}] },
  });
  assert.equal(picker.hmbSetVideoPickerHybridView(first.liveContainer, true), true);
  assert.equal(expandedBodyHealthy(first), true, "Compact -> expanded must reattach the full authored body.");
  assert.equal(compactBodyHealthy(first), false, "Expanded view cannot leave the compact summary over its body.");
  assert.equal(
    picker.hmbSetVideoPickerHybridView(first.liveContainer, true),
    true,
    "A duplicate expanded request must be an idempotent no-op.",
  );
  assert.equal(expandedBodyHealthy(first), true, "Duplicate expanded requests cannot consume their own body.");

  // A present but hidden body is equally unusable. This catches the case where
  // a host props reconciliation keeps the elements but applies a stale hidden
  // state, which otherwise produces the same black surface as removal.
  first.dashboard.mainGrid.style.display = "none";
  firstLifecycleObserver.flush();
  flushFrames();
  assert.equal(firstRecovery.recoveries(), 2);
  assert.equal(expandedBodyHealthy(first), true, "Hidden expanded content must be replaced by a visible body.");

  // The compact analogue is also substantive-body based. The root and header
  // can survive while the summary is removed by an allocator reconciliation.
  prepareCompactFragment(first);
  assert.equal(picker.hmbSetVideoPickerHybridView(first.liveContainer, false), true);
  const compactSummary = first.liveContainer.querySelector("[data-picker-compact-summary='true']");
  compactSummary.remove();
  assert.equal(compactBodyHealthy(first), false);
  assert.equal(
    firstRecovery.guard.inspect(),
    false,
    "Repeated compact body loss must enter bounded backoff instead of remounting every frame.",
  );
  assert.equal(firstRecovery.recoveries(), 2, "Backoff must not recover synchronously after a burst.");
  assert.equal(pendingTimers.size, 1, "A burst owns only one recovery timer.");
  advanceTime(120);
  assert.equal(firstRecovery.recoveries(), 3);
  assert.equal(expandedBodyHealthy(first), true);

  // The recovery record is container-owned and bounded. Repeated allocator
  // damage receives exponential backoff rather than a 60fps factory-remount
  // loop, while each settled timer can still repair the body.
  for (let attempt = 0; attempt < 10; attempt += 1) {
    first.dashboard.sceneBar.remove();
    first.dashboard.mainGrid.remove();
    firstRecovery.guard.inspect();
    assert.ok(pendingTimers.size <= 1, "Only one backoff timer may exist per Picker container.");
    advanceTime(2000);
    assert.equal(expandedBodyHealthy(first), true);
  }
  assert.ok(
    first.liveContainer.__hmbVideoPickerRootRecoveryPolicy.history.length <= 8,
    "Recovery history must remain bounded.",
  );

  // View and expanded-geometry registries are scoped to their workflow canvas.
  // Two open workflows may legitimately reuse the same serialized node id.
  const workflowA = element("div", "react-flow", { "data-workflow-id": "workflow-a" });
  const workflowB = element("div", "react-flow", { "data-workflow-id": "workflow-b" });
  const collisionA = makePickerInstance("picker-node-shared", "runtime-a", workflowA);
  const collisionB = makePickerInstance("picker-node-shared", "runtime-b", workflowB);
  picker.hmbBindVideoPickerRuntimeIdentity(collisionA.liveContainer, collisionA.runtimeId);
  picker.hmbBindVideoPickerRuntimeIdentity(collisionB.liveContainer, collisionB.runtimeId);
  picker.hmbRememberVideoPickerViewMode(collisionA.liveContainer, false);
  picker.hmbRememberVideoPickerViewMode(collisionB.liveContainer, true);
  assert.equal(picker.hmbVideoPickerStoredViewMode(collisionA.liveContainer), false);
  assert.equal(picker.hmbVideoPickerStoredViewMode(collisionB.liveContainer), true);
  const workflowSnapshot = {
    properties: {
      height: { value: "1333px", priority: "" },
      "min-height": { value: "1151px", priority: "" },
      "max-height": { value: "", priority: "" },
    },
    actualHeight: 1333,
    measuredHeight: 1333,
  };
  picker.hmbRememberVideoPickerExpandedGeometry(collisionA.liveContainer, workflowSnapshot);
  assert.equal(
    picker.hmbVideoPickerRememberedExpandedGeometry(collisionB.liveContainer),
    null,
    "Same node id in another workflow cannot inherit expanded geometry.",
  );
  const collisionARemount = makePickerInstance("picker-node-shared", "runtime-a", workflowA);
  picker.hmbBindVideoPickerRuntimeIdentity(
    collisionARemount.liveContainer,
    collisionARemount.runtimeId,
  );
  assert.equal(
    picker.hmbVideoPickerStoredViewMode(collisionARemount.liveContainer),
    false,
    "Same-data-id remount persistence must remain inside one workflow.",
  );
  assert.equal(
    picker.hmbVideoPickerRememberedExpandedGeometry(collisionARemount.liveContainer)?.properties?.height?.value,
    "1333px",
  );

  // Cleanup disables stale resurrection. A newly mounted controller can then
  // independently recover the same node, including across runtime-id changes.
  first.dashboard.sceneBar.remove();
  first.dashboard.mainGrid.remove();
  firstRecovery.guard.inspect();
  assert.equal(pendingTimers.size, 1, "A throttled repair must own a cleanup-visible timer.");
  const recoveriesBeforeCleanup = firstRecovery.recoveries();
  firstRecovery.guard.cleanup();
  assert.equal(pendingTimers.size, 0, "Guard cleanup must cancel its pending recovery timer.");
  first.dashboard.sceneBar.remove();
  first.dashboard.mainGrid.remove();
  assert.equal(firstRecovery.guard.inspect(), false);
  assert.equal(firstRecovery.recoveries(), recoveriesBeforeCleanup);
  const remountedRecovery = installRecoveryGuard(first);
  assert.equal(
    remountedRecovery.guard.inspect(),
    false,
    "A controller remount keeps the bounded history and cannot bypass its backoff.",
  );
  assert.equal(pendingTimers.size, 1);
  advanceTime(2000);
  assert.equal(remountedRecovery.recoveries(), 1);
  assert.equal(expandedBodyHealthy(first), true);
  assert.equal(expandedBodyHealthy(second), true);

  remountedRecovery.guard.cleanup();
  secondRecovery.guard.cleanup();
  firstMeasurement.cleanup();
  secondMeasurement.cleanup();
} finally {
  Date.now = savedDateNow;
  for (const [name, value] of Object.entries(savedGlobals)) {
    if (value === undefined) delete globalThis[name];
    else globalThis[name] = value;
  }
}

console.log("HMB VideoPicker body attachment regression: PASS");
