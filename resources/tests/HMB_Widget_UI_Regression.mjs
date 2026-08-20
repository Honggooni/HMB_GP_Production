import assert from "node:assert/strict";
import fs from "node:fs";

function importWidget(relativePath) {
  const source = fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

function fakeClassList() {
  const values = new Set();
  return {
    add(...items) { items.forEach((item) => values.add(item)); },
    remove(...items) { items.forEach((item) => values.delete(item)); },
    contains(item) { return values.has(item); },
  };
}

function fakeStyle(initial = {}) {
  const style = { ...initial };
  const camel = (name) => String(name).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
  style.setProperty = (name, value) => {
    style[camel(name)] = String(value);
  };
  style.removeProperty = (name) => {
    delete style[camel(name)];
  };
  return style;
}

function fakeElement(parentElement = null, className = "", attributes = {}) {
  const handlers = new Map();
  const element = {
    parentElement,
    children: [],
    className,
    style: fakeStyle(),
    dataset: {},
    classList: fakeClassList(),
    getAttribute(name) { return attributes[name] || ""; },
    hasAttribute(name) { return Object.hasOwn(attributes, name); },
    setAttribute(name, value) { attributes[name] = String(value); },
    addEventListener(type, handler) { handlers.set(type, handler); },
    removeEventListener(type, handler) {
      if (handlers.get(type) === handler) handlers.delete(type);
    },
    handler(type) { return handlers.get(type); },
    matches(selector) {
      return String(selector || "").includes("textarea") || String(selector || "").includes("input");
    },
    closest(selector) {
      let current = this;
      while (current) {
        if (current.matches?.(selector)) return current;
        current = current.parentElement;
      }
      return null;
    },
  };
  if (parentElement?.children) parentElement.children.push(element);
  return element;
}

const windowHandlers = new Map();
globalThis.document = {
  body: {},
  documentElement: {},
  activeElement: null,
};
globalThis.window = {
  addEventListener(type, handler, options) {
    windowHandlers.set(`${type}:${String(options)}`, handler);
  },
  removeEventListener(type, handler, options) {
    const key = `${type}:${String(options)}`;
    if (windowHandlers.get(key) === handler) windowHandlers.delete(key);
  },
  getComputedStyle(element) {
    return {
      display: element?.display || "block",
      flexDirection: element?.flexDirection || "column",
      gridTemplateColumns: "none",
      position: "static",
      marginTop: "0",
      marginBottom: "0",
      paddingTop: "0",
      borderTopWidth: "0",
    };
  },
};

const picker = await importWidget("../../widgets/HMBVideoPickerLibraryWidget_v032.js");
const agentWidget = await importWidget("../../widgets/HMBAgentLibraryWidget.js");
const assetWidget = await importWidget("../../widgets/HMBImageAssetLibraryWidget.js");

const assetGestureContainer = fakeElement();
const assetGestureRoot = fakeElement(assetGestureContainer, "hmb-image-assets");
assetGestureContainer.querySelector = (selector) => (
  selector === ".hmb-image-assets" ? assetGestureRoot : null
);
for (const element of [assetGestureContainer, assetGestureRoot]) {
  element.classList.add("nopan", "nowheel");
}
assetWidget.hmbPrepareImageAssetCanvasGestures(assetGestureContainer);
for (const element of [assetGestureContainer, assetGestureRoot]) {
  assert.ok(element.classList.contains("nodrag"));
  assert.equal(element.classList.contains("nopan"), false);
  assert.equal(element.classList.contains("nowheel"), false);
  assert.equal(element.handler("wheel"), undefined);
}

const assetScrollContainer = fakeElement();
const assetScrollViewport = fakeElement(assetScrollContainer, "asset-scroll");
assetScrollViewport.scrollTop = 100;
assetScrollViewport.scrollLeft = 20;
assetScrollViewport.clientHeight = 480;
assetScrollContainer.querySelector = (selector) => (
  selector === "[data-asset-scroll]" ? assetScrollViewport : null
);
const assetScrollListenerOptions = new Map();
assetWidget.hmbInstallImageAssetScrollGestures(
  assetScrollContainer,
  (target, type, handler, options) => {
    if (target === assetScrollViewport) assetScrollListenerOptions.set(type, options);
    target.addEventListener(type, handler, options);
  },
);
assert.equal(assetScrollViewport.classList.contains("nowheel"), true);
assert.equal(assetScrollContainer.__hmbImageAssetViewportPanning, undefined);
assert.equal(assetScrollContainer.__hmbImageAssetCancelViewportPan, undefined);
assert.equal(assetScrollContainer.handler("wheel"), undefined, "Canvas zoom remains available outside the asset viewport.");
let localStops = 0;
let localPrevents = 0;
const localEvent = (overrides = {}) => ({
  preventDefault() { localPrevents += 1; },
  stopPropagation() { localStops += 1; },
  ...overrides,
});
assetScrollViewport.handler("wheel")(localEvent({ deltaY: 120, deltaX: 0, deltaMode: 0 }));
assert.equal(assetScrollViewport.scrollTop, 220, "Wheel pixels scroll only the red asset viewport.");
assetScrollViewport.handler("wheel")(localEvent({ deltaY: -2, deltaX: 0, deltaMode: 1 }));
assert.equal(assetScrollViewport.scrollTop, 140, "Line-mode wheels receive a stable local scroll step.");
assert.equal(localStops, 2);
assert.equal(localPrevents, 2);
assert.equal(assetScrollListenerOptions.get("wheel")?.passive, false);
for (const eventName of [
  "pointerdown",
  "pointermove",
  "pointerup",
  "pointercancel",
  "lostpointercapture",
  "pointerleave",
  "mousedown",
  "mousemove",
  "mouseup",
  "auxclick",
]) {
  assert.equal(
    assetScrollViewport.handler(eventName),
    undefined,
    `Asset viewport must pass ${eventName} through to Griptape canvas panning.`,
  );
}
assert.equal(windowHandlers.has("pointermove:[object Object]"), false);
assert.equal(windowHandlers.has("pointerup:[object Object]"), false);
assert.equal(windowHandlers.has("pointercancel:[object Object]"), false);
assert.equal(windowHandlers.has("mousemove:[object Object]"), false);
assert.equal(windowHandlers.has("mouseup:[object Object]"), false);
assert.equal(windowHandlers.has("blur:true"), false);
assert.equal(assetScrollViewport.scrollLeft, 20);
assert.equal(assetScrollViewport.scrollTop, 140);

const agentGestureContainer = fakeElement();
const agentGestureRoot = fakeElement(agentGestureContainer, "hmb-agent-dashboard");
agentGestureContainer.innerHTML = '<div class="hmb-agent-dashboard nopan nowheel"></div>';
agentGestureContainer.querySelector = (selector) => (
  selector === ".hmb-agent-dashboard" ? agentGestureRoot : null
);
for (const element of [agentGestureContainer, agentGestureRoot]) {
  element.classList.add("nopan", "nowheel");
}
assert.equal(typeof agentWidget.hmbPrepareAgentCanvasGestures, "function");
const agentController = agentWidget.default(agentGestureContainer, {});
assert.match(
  agentGestureContainer.innerHTML,
  /class="hmb-agent-dashboard nodrag"/,
  "Agent remount replaces stale gesture blockers with its nodrag-only background.",
);
assert.doesNotMatch(agentGestureContainer.innerHTML, /\bnopan\b|\bnowheel\b/);
for (const element of [agentGestureContainer, agentGestureRoot]) {
  assert.ok(element.classList.contains("nodrag"), "Agent gesture surfaces prevent whole-node dragging.");
  assert.equal(element.classList.contains("nopan"), false, "Agent gesture surfaces pass canvas panning through.");
  assert.equal(element.classList.contains("nowheel"), false, "Agent gesture surfaces pass wheel zoom through.");
  for (const eventName of ["mousedown", "click", "dblclick", "wheel"]) {
    assert.equal(
      element.handler(eventName),
      undefined,
      `Agent ${eventName} must remain available to Griptape's native canvas gesture handler.`,
    );
  }
}
assert.equal(
  typeof agentGestureContainer.handler("pointerdown"),
  "function",
  "Agent interior pointerdown must stay local so only the native title bar selects the node.",
);
assert.equal(agentGestureRoot.handler("pointerdown"), undefined);
agentController.cleanup();
assert.equal(agentGestureContainer.innerHTML, "");

const shell = fakeElement(null, "react-flow__node");
const outerHost = fakeElement(shell, "parameter-host");
const innerHost = fakeElement(outerHost, "widget-host");
const pickerContainer = fakeElement(innerHost, "picker-container");

picker.hmbNormalizePickerHostAncestors(pickerContainer);
for (const host of [innerHost, outerHost]) {
  assert.equal(host.style.minWidth, "0");
  assert.equal(host.style.width, undefined, "Picker must not overwrite Griptape-owned wrapper width.");
  assert.equal(host.style.height, undefined, "Picker must not overwrite Griptape-owned wrapper height.");
  assert.equal(host.style.flex, undefined, "Picker must not overwrite Griptape-owned wrapper flex allocation.");
  assert.equal(host.style.overflow, undefined, "Picker must not overwrite Griptape-owned wrapper overflow.");
}
shell.style.height = "1200px";
shell.offsetHeight = 1900;
shell.getBoundingClientRect = () => ({ height: 1900 });
assert.equal(
  picker.hmbPickerNodeShellHeight(shell),
  1900,
  "Stable picker fitting measures the rendered node height before applying a minimum.",
);
assert.equal(typeof picker.hmbRenderPickerMarkup, "function");
assert.equal(
  typeof picker.hmbPreparePickerSlotTransition,
  "undefined",
  "The retired fixed VIDEO*_OUT slot-transition shim must stay removed.",
);

const pickerGuardContainer = fakeElement();
const pickerGuardClip = fakeElement(pickerGuardContainer, "hmbvp-clip");
const pickerGuardDashboard = fakeElement(pickerGuardClip, "hmbvp");
const pickerGuardControl = fakeElement(pickerGuardDashboard, "picker-control");
const pickerBroadPanel = fakeElement(pickerGuardDashboard, "right-stack");
pickerGuardDashboard.closest = () => null;
pickerGuardControl.closest = () => pickerGuardControl;
for (const element of [pickerGuardContainer, pickerGuardClip, pickerGuardDashboard]) {
  element.classList.add("nodrag", "nopan", "nowheel");
}
pickerBroadPanel.classList.add("nopan", "nowheel");
pickerGuardContainer.querySelector = (selector) => {
  if (selector === ".hmbvp-clip") return pickerGuardClip;
  if (selector === ".hmbvp") return pickerGuardDashboard;
  return null;
};
pickerGuardContainer.querySelectorAll = (selector) => {
  if (selector === ".right-stack") return [pickerBroadPanel];
  if (String(selector).includes("button")) return [pickerGuardControl];
  return [];
};
const pickerGuardCleanup = [];
picker.hmbInstallPickerInteractionIsolation(pickerGuardContainer, pickerGuardCleanup);
assert.equal(pickerGuardContainer.classList.contains("nodrag"), false);
assert.equal(pickerGuardContainer.classList.contains("nopan"), false);
assert.equal(pickerGuardContainer.classList.contains("nowheel"), false);
assert.ok(pickerGuardClip.classList.contains("nodrag"), "Picker clip prevents whole-node dragging.");
assert.equal(pickerGuardClip.classList.contains("nopan"), false);
assert.equal(pickerGuardClip.classList.contains("nowheel"), false);
for (const className of ["nodrag", "nopan", "nowheel"]) {
  assert.equal(
    pickerGuardDashboard.classList.contains(className),
    false,
    `Picker background must clear stale ${className} gesture guards.`,
  );
}
assert.equal(
  typeof pickerGuardContainer.handler("pointerdown"),
  "function",
  "Picker uses one delegated pointerdown handler instead of one handler per control.",
);
let pickerRootStops = 0;
pickerGuardContainer.handler("pointerdown")({
  type: "pointerdown",
  target: pickerGuardDashboard,
  stopPropagation() { pickerRootStops += 1; },
});
assert.equal(pickerRootStops, 0, "Picker panel backgrounds keep canvas pan/select gestures responsive.");
assert.equal(
  typeof pickerGuardContainer.handler("click"),
  "function",
  "Picker uses one delegated click handler instead of one handler per control.",
);
let pickerBackgroundStops = 0;
pickerGuardContainer.handler("click")({
  type: "click",
  target: { closest() { return null; } },
  stopPropagation() { pickerBackgroundStops += 1; },
});
assert.equal(pickerBackgroundStops, 0, "Picker background clicks still reach the canvas.");
assert.equal(pickerGuardContainer.handler("wheel"), undefined);
assert.equal(pickerBroadPanel.classList.contains("nopan"), false);
assert.equal(pickerBroadPanel.classList.contains("nowheel"), false);
assert.equal(
  pickerBroadPanel.handler("wheel"),
  undefined,
  "Picker broad panels pass wheel zoom through after stale guards are cleared.",
);
for (const className of ["nodrag", "nopan", "nowheel"]) {
  assert.ok(
    pickerGuardControl.classList.contains(className),
    `Picker controls retain ${className} isolation.`,
  );
}
let pickerInteriorStops = 0;
pickerGuardContainer.handler("pointerdown")({
  type: "pointerdown",
  target: pickerGuardControl,
  stopPropagation() { pickerInteriorStops += 1; },
});
pickerGuardContainer.handler("click")({
  type: "click",
  target: pickerGuardControl,
  stopPropagation() { pickerInteriorStops += 1; },
});
assert.equal(
  pickerInteriorStops,
  2,
  "Picker controls remain local while their surrounding panel backgrounds pan the canvas.",
);
assert.equal(pickerGuardControl.handler("click"), undefined, "Controls do not own per-element listeners.");
assert.equal(pickerGuardCleanup.length, 1, "One cleanup owns the delegated interaction and delete guards.");

const startShell = fakeElement(null, "react-flow__node");
startShell.offsetHeight = 1200;
startShell.getBoundingClientRect = () => ({ top: 20, bottom: 1220, height: 1200 });
const startOuterHost = fakeElement(startShell, "parameter-host");
const startInnerHost = fakeElement(startOuterHost, "widget-host");
const startContainer = fakeElement(startInnerHost, "picker-container");
const startClip = fakeElement(startContainer, "hmbvp-clip");
const startPicker = fakeElement(startClip, "hmbvp");
startContainer.querySelector = (selector) => {
  if (selector === ".hmbvp-clip") return startClip;
  if (selector === ".hmbvp") return startPicker;
  return null;
};
startContainer.getBoundingClientRect = () => ({ top: 260, bottom: 1220, height: 960 });
assert.equal(
  picker.hmbStretchPickerAdaptiveStack(startContainer, null, startShell),
  1071,
  "Picker uses one exact Prompt-style dashboard frame without reserving the removed 34px footer.",
);
for (const host of [startContainer, startInnerHost, startOuterHost]) {
  assert.equal(host.style.minHeight, "1071px");
}
assert.equal(startClip.style.height, "1071px");
assert.equal(startClip.style.minHeight, "1071px");
assert.equal(startPicker.style.height, "1071px");
assert.equal(startPicker.style.minHeight, "1071px");
assert.equal(startPicker.style.paddingLeft, "var(--safe-x)");
assert.equal(startPicker.style.paddingRight, "var(--safe-x)");
assert.equal(
  startShell.style.height,
  undefined,
  "Sizing the Prompt-style inner frame must not overwrite the outer node during host propagation.",
);

// With no visible native row above the Picker, the established 1200px shell
// must be fully occupied by the dashboard instead of leaving the former
// 960px-content / 240px-dead-strip split.
const fullStartShell = fakeElement(null, "react-flow__node");
fullStartShell.offsetHeight = 1200;
fullStartShell.getBoundingClientRect = () => ({ top: 0, bottom: 1200, height: 1200 });
const fullStartHost = fakeElement(fullStartShell, "widget-host");
const fullStartContainer = fakeElement(fullStartHost, "picker-container");
const fullStartClip = fakeElement(fullStartContainer, "hmbvp-clip");
const fullStartPicker = fakeElement(fullStartClip, "hmbvp");
fullStartContainer.getBoundingClientRect = () => ({ top: 0, bottom: 1200, height: 1200 });
fullStartContainer.querySelector = (selector) => {
  if (selector === ".hmbvp-clip") return fullStartClip;
  if (selector === ".hmbvp") return fullStartPicker;
  return null;
};
assert.equal(picker.hmbStretchPickerAdaptiveStack(fullStartContainer, null, fullStartShell), 1200);
assert.equal(fullStartContainer.style.minHeight, "1200px");
assert.equal(fullStartClip.style.height, "1200px");
assert.equal(fullStartPicker.style.height, "1200px");
assert.equal(fullStartShell.style.height, undefined, "Inner fill must not rewrite the 1200px outer size.");

// A serialized manual resize at the established 1151px floor remains exact;
// filling available space must not behave like a start-size migration.
const savedResizeShell = fakeElement(null, "react-flow__node");
savedResizeShell.offsetHeight = 1151;
savedResizeShell.getBoundingClientRect = () => ({ top: 0, bottom: 1151, height: 1151 });
const savedResizeHost = fakeElement(savedResizeShell, "widget-host");
const savedResizeContainer = fakeElement(savedResizeHost, "picker-container");
const savedResizeClip = fakeElement(savedResizeContainer, "hmbvp-clip");
const savedResizePicker = fakeElement(savedResizeClip, "hmbvp");
savedResizeContainer.getBoundingClientRect = () => ({ top: 0, bottom: 1151, height: 1151 });
savedResizeContainer.querySelector = (selector) => {
  if (selector === ".hmbvp-clip") return savedResizeClip;
  if (selector === ".hmbvp") return savedResizePicker;
  return null;
};
assert.equal(picker.hmbStretchPickerAdaptiveStack(savedResizeContainer, null, savedResizeShell), 1151);
assert.equal(savedResizeContainer.style.minHeight, "1151px");
assert.equal(savedResizeClip.style.height, "1151px");
assert.equal(savedResizePicker.style.height, "1151px");
assert.equal(savedResizeShell.style.height, undefined, "Saved 1151px outer height must remain user-owned.");

const commandBridge = await importWidget("../../widgets/HMBVideoPickerCommandBridgeWidget_v032.js");
const collapsedPickerShell = fakeElement(null, "react-flow__node");
collapsedPickerShell.offsetWidth = 1400;
collapsedPickerShell.offsetHeight = 1200;
collapsedPickerShell.getBoundingClientRect = () => ({ width: 1400, height: 1200 });
assert.equal(
  commandBridge.hmbEnsurePickerBootstrapNode,
  undefined,
  "The hidden command bridge must not resize the outer node.",
);

const nodeBody = fakeElement(collapsedPickerShell, "flex flex-col h-full");
const contentRegion = fakeElement(nodeBody, "flex-1 min-h-0");
const adaptiveStack = fakeElement(contentRegion, "relative flex flex-col h-full");
nodeBody.getBoundingClientRect = () => ({ top: 40, height: 960 });
contentRegion.getBoundingClientRect = () => ({ top: 80, height: 920 });
adaptiveStack.getBoundingClientRect = () => ({ top: 100, height: 900 });
const commandLayoutRow = fakeElement(adaptiveStack, "adaptive-row");
commandLayoutRow.style.height = "40px";
commandLayoutRow.offsetHeight = 40;
const commandParameterRow = fakeElement(commandLayoutRow, "parameter-row", {
  "data-parameter-name": "HMB_PICKER_COMMAND",
});
const commandHost = fakeElement(commandParameterRow, "widget-host");
const commandContainer = fakeElement(commandHost, "command-container");
assert.equal(commandBridge.hmbCollapseCommandBridgeLayoutRow(commandContainer), 40);
assert.equal(commandLayoutRow.style.height, "0px");
assert.equal(collapsedPickerShell.__hmbPickerCommandRowReclaim, 40);

const stateLayoutRow = fakeElement(adaptiveStack, "adaptive-row");
stateLayoutRow.getBoundingClientRect = () => ({ top: 180, height: 760 });
stateLayoutRow.style.height = "700px";
stateLayoutRow.style.position = "absolute";
stateLayoutRow.style.top = "160px";
stateLayoutRow.style.left = "0px";
stateLayoutRow.style.right = "0px";
stateLayoutRow.style.bottom = "0px";
stateLayoutRow.style.width = "auto";
stateLayoutRow.style.margin = "0px";
stateLayoutRow.offsetHeight = 700;
const stateParameterRow = fakeElement(stateLayoutRow, "parameter-row", {
  "data-parameter-name": "HMB_PICKER_STATE",
});
const stateHost = fakeElement(stateParameterRow, "widget-host");
const stateContainer = fakeElement(stateHost, "picker-container");
const trailingSpacer = fakeElement(adaptiveStack, "grow", { "aria-hidden": "true" });
assert.equal(picker.hmbApplyPickerCommandRowReclaim(stateContainer), 1);
assert.equal(stateLayoutRow.style.height, undefined);
assert.equal(stateLayoutRow.style.maxHeight, undefined);
assert.equal(stateLayoutRow.style.flex, undefined);
assert.equal(stateLayoutRow.style.position, undefined);
assert.equal(stateLayoutRow.style.top, undefined);
assert.equal(stateLayoutRow.style.left, undefined);
assert.equal(stateLayoutRow.style.right, undefined);
assert.equal(stateLayoutRow.style.bottom, undefined);
assert.equal(stateLayoutRow.style.width, undefined);
assert.equal(stateLayoutRow.style.margin, undefined);
assert.equal(stateParameterRow.style.height, undefined);
assert.equal(adaptiveStack.style.height, undefined);
assert.equal(contentRegion.style.height, undefined);
assert.equal(nodeBody.style.height, undefined);
assert.equal(trailingSpacer.style.height, "0px");
assert.equal(trailingSpacer.style.flex, "0 0 0px");
const stableRequiredHeight = picker.hmbStretchPickerAdaptiveStack(
  stateContainer,
  stateLayoutRow,
  collapsedPickerShell,
);
assert.ok(
  stableRequiredHeight >= 960,
  "Stable sizing preserves the v0.2.0 natural content floor.",
);
for (const host of [
  stateContainer,
  stateHost,
  stateParameterRow,
  stateLayoutRow,
  adaptiveStack,
  contentRegion,
  nodeBody,
]) {
  assert.equal(host.style.minHeight, `${stableRequiredHeight}px`);
  assert.equal(host.style.height, undefined, "Natural-height sizing must not force a fixed wrapper height.");
  assert.equal(host.style.flex, undefined, "Natural-height sizing must not force a fixed wrapper flex basis.");
}
assert.equal(
  picker.hmbApplyPickerCommandRowReclaim(stateContainer),
  1,
  "Repeated command-row collapse remains idempotent.",
);

const mayaLayoutRow = fakeElement(adaptiveStack, "adaptive-row");
const mayaParameterRow = fakeElement(mayaLayoutRow, "parameter-row", {
  "data-parameter-name": "MAYA_SCENE",
});
const mayaHost = fakeElement(mayaParameterRow, "maya-picker-host");
mayaParameterRow.contains = (element) => element === mayaHost;
mayaParameterRow.closest = () => mayaParameterRow;
adaptiveStack.contains = (element) => (
  element === stateContainer
  || element === stateHost
  || element === stateParameterRow
  || element === stateLayoutRow
);
collapsedPickerShell.querySelectorAll = (selector) => (
  String(selector).includes("MAYA_SCENE") ? [mayaParameterRow] : []
);
assert.equal(
  picker.hmbCollapseNativeMayaLayoutRows(stateContainer),
  1,
  "The complete hidden native MAYA_SCENE layout branch must be collapsed.",
);
assert.equal(mayaLayoutRow.style.height, "0px");
assert.equal(mayaLayoutRow.style.flex, "0 0 0px");
assert.equal(mayaLayoutRow.style.margin, "0");

const prompt = await importWidget("../../widgets/HMBPromptLibraryScopedBindingWidget.js");
const assetOnlyPromptState = prompt.normalizeState({
  images: [{
    label: "Asset connected without video",
    source_type: "Character Appearance",
    color_picks: ["Red"],
    binding_video_slots: [1],
    asset_managed: true,
    asset_verified: true,
    asset_source_kind: "project",
  }],
  videos: [{ label: "", source_type: "Role Required / Select Video Type" }],
  image_asset: { enabled: true, order_managed: true },
});
const connectedSelectionOnlyState = prompt.normalizeState({
  images: [
    {
      label: "Selected upstream",
      source_type: "Character Appearance",
      asset_source_uid: "source:selected",
      asset_managed: true,
    },
    {
      label: "Dormant native row",
      source_type: "Custom",
      custom_source_type: "Manual concept",
      owner: "Manual target",
    },
  ],
  image_asset: {
    enabled: true,
    order_managed: true,
    dormant_manual_rows: [{
      label: "Cached manual row",
      source_type: "Custom",
      owner: "Cached manual target",
    }],
    dormant_asset_rows: [{
      label: "Cached deselected row",
      source_type: "Character Appearance",
      asset_source_uid: "source:deselected",
      asset_managed: true,
      color_picks: ["Magenta"],
    }],
  },
});
assert.equal(
  connectedSelectionOnlyState.status.active_images,
  1,
  "With ASSET_IN connected, native/manual rows must not claim active @image slots.",
);
assert.equal(
  connectedSelectionOnlyState.image_asset.dormant_manual_rows[0].owner,
  "Cached manual target",
  "Frontend normalization must preserve dormant independent rows.",
);
assert.deepEqual(
  connectedSelectionOnlyState.image_asset.dormant_asset_rows[0].color_picks,
  ["Magenta"],
  "Frontend normalization must preserve source_uid dormant asset settings.",
);
assert.equal(
  prompt.hmbImagePickerEnabled(assetOnlyPromptState),
  false,
  "ASSET_IN must not enable image/video color picking while every video is inactive.",
);
assert.deepEqual(
  assetOnlyPromptState.images[0].color_picks,
  ["Red"],
  "An inactive video disables picker actions but preserves its dormant color binding.",
);
assert.deepEqual(
  prompt.hmbImagePickerActionAvailability(assetOnlyPromptState, assetOnlyPromptState.images[0]),
  { enabled: false, canAdd: true, canRemove: false },
  "No active video keeps the address dormant while independent picker row editing remains available.",
);
const activePrimaryPromptState = prompt.normalizeState({
  images: [{ label: "Image", source_type: "Character Appearance" }],
  videos: [{ label: "playblast.mp4", source_type: "Maya Preview / Playblast" }],
});
assert.equal(
  prompt.hmbImagePickerEnabled(activePrimaryPromptState),
  true,
  "The image/video picker becomes available after any video is active.",
);
assert.deepEqual(
  prompt.hmbImagePickerActionAvailability(activePrimaryPromptState, activePrimaryPromptState.images[0]),
  { enabled: true, canAdd: true, canRemove: false },
);
const auxiliaryOnlyPromptState = prompt.normalizeState({
  images: [{ label: "Image", source_type: "Character Appearance" }],
  videos: [
    { label: "", source_type: "Role Required / Select Video Type" },
    { label: "motion.mp4", source_type: "Motion Reference", control_role: "Context Only", manual: true },
  ],
});
assert.equal(
  prompt.hmbImagePickerEnabled(auxiliaryOnlyPromptState),
  true,
  "An active auxiliary-only video must not require @video1 before image binding controls become available.",
);
const imageRow = (slot, label, detail) => ({
  slot,
  token: `@image${slot}`,
  name: `IMAGE_${String(slot).padStart(2, "0")}`,
  label,
  detail,
  source_type: "Character Appearance",
  color_picks: [`Color-${label}`],
  binding_scopes: [`Scope-${label}`],
  binding_custom_scopes: [`Custom-${label}`],
  binding_video_slots: [1],
  marker_video: 1,
});
const adjacentState = {
  images: [
    imageRow(1, "A", "state-A"),
    imageRow(2, "B", "state-B"),
    imageRow(3, "C", "state-C"),
  ],
  videos: [{ keep_out: "keep A=@image1 B=@image2 C=@image3" }],
  text: {
    SCENE_CONTEXT: "A=@image1 B=@image2 C=@image3",
    PRESERVED_TEXT: "[On-screen Text] literal @image1 + @image2",
  },
};
const originalA = adjacentState.images[0];
assert.equal(prompt.swapImageRowsWithoutReset(adjacentState, 0, 1), true);
assert.deepEqual(adjacentState.images.map((item) => item.label), ["B", "A", "C"]);
assert.equal(adjacentState.images[1], originalA, "One-step arrow movement preserves the complete row object.");
assert.equal(adjacentState.images[1].detail, "state-A");
assert.equal(adjacentState.images[1].token, "@image2");
assert.equal(adjacentState.text.SCENE_CONTEXT, "A=@image2 B=@image1 C=@image3");
assert.equal(
  adjacentState.text.PRESERVED_TEXT,
  "[On-screen Text] literal @image1 + @image2",
  "Exact preserved text must never be rewritten during source reordering.",
);
assert.equal(adjacentState.videos[0].keep_out, "keep A=@image2 B=@image1 C=@image3");

const dragState = {
  images: [
    imageRow(1, "A", "state-A"),
    imageRow(2, "B", "state-B"),
    imageRow(3, "C", "state-C"),
    imageRow(4, "D", "state-D"),
  ],
  videos: [{ keep_out: "A=@image1 B=@image2 C=@image3 D=@image4" }],
  text: { SCENE_CONTEXT: "A=@image1 B=@image2 C=@image3 D=@image4" },
};
const dragSource = dragState.images[0];
assert.equal(prompt.hmbImageDropTargetIndex(0, 2, true, 4), 2);
assert.equal(prompt.hmbImageDropTargetIndex(3, 1, false, 4), 1);
assert.equal(prompt.moveImageRowWithoutReset(dragState, 0, 2), true);
assert.deepEqual(dragState.images.map((item) => item.label), ["B", "C", "A", "D"]);
assert.equal(dragState.images[2], dragSource, "Drag movement preserves every field on the source row.");
assert.equal(dragState.images[2].detail, "state-A");
assert.equal(dragState.text.SCENE_CONTEXT, "A=@image3 B=@image1 C=@image2 D=@image4");
assert.equal(dragState.videos[0].keep_out, "A=@image3 B=@image1 C=@image2 D=@image4");

const deleteState = {
  images: [
    imageRow(1, "A", "state-A"),
    imageRow(2, "B", "state-B"),
    imageRow(3, "C", "state-C"),
    imageRow(4, "D", "state-D"),
  ],
  videos: [{ keep_out: "A=@image1;B=@image2;C=@image3;D=@image4" }],
  text: {
    SCENE_CONTEXT: "A=@image1;B=@image2;C=@image3;D=@image4",
    PRESERVED_TEXT: "[Dialogue] keep @image2 literal",
  },
  picker: { matched_images: 2 },
};
deleteState.images[1].picker_auto_color = "Green";
deleteState.images[1].picker_auto_video = 1;
deleteState.images[1].picker_auto_source = "picker";
const deleteResult = prompt.removeImageRowAndPromote(deleteState, 1);
assert.deepEqual(deleteResult, { changed: true, removedSlot: 2, remaining: 3 });
assert.deepEqual(deleteState.images.map((item) => item.label), ["A", "C", "D"]);
assert.deepEqual(deleteState.images.map((item) => item.slot), [1, 2, 3]);
assert.deepEqual(deleteState.images.map((item) => item.token), ["@image1", "@image2", "@image3"]);
assert.equal(deleteState.images[1].detail, "state-C", "Rows below a deletion promote without losing state.");
assert.equal(deleteState.picker.matched_images, 1, "Deleting an auto-bound row updates the Picker match count.");
assert.equal(deleteState.text.SCENE_CONTEXT, "A=@image1;B=[deselected image source #2];C=@image2;D=@image3");
assert.equal(deleteState.videos[0].keep_out, "A=@image1;B=[deselected image source #2];C=@image2;D=@image3");
assert.equal(deleteState.text.PRESERVED_TEXT, "[Dialogue] keep @image2 literal");

const finalRowState = {
  images: [imageRow(1, "Only", "only-state")],
  videos: [{ keep_out: "Only=@image1" }],
  text: { SCENE_CONTEXT: "Only=@image1" },
};
assert.deepEqual(
  prompt.removeImageRowAndPromote(finalRowState, 0),
  { changed: true, removedSlot: 1, remaining: 1 },
);
assert.equal(finalRowState.images.length, 1, "The final required UI row remains as one blank source row.");
assert.equal(finalRowState.images[0].label, "");
assert.equal(finalRowState.text.SCENE_CONTEXT, "Only=[deselected image source #1]");
assert.equal(finalRowState.videos[0].keep_out, "Only=[deselected image source #1]");

const preservedTaxonomyState = prompt.normalizeState({
  image_taxonomy: {
    source_type_choices: ["Role Required / Select Source Type", "Custom"],
    scope_choices: ["", "Handheld prop", "Custom scope"],
    scope_choices_by_source_type: { Custom: ["", "Custom scope"] },
    actor_color_pick_choices: ["Red", "Green", "Blue"],
    object_color_pick_choices: ["Red", "Green", "Blue"],
    actor_color_pick_source_types: [],
    object_color_pick_source_types: ["Custom"],
  },
  images: [{
    source_type: "Future Image",
    custom_source_type: "Future Image",
    owner: "ExistingTarget",
    binding_scopes: ["Handheld prop"],
    interaction_targets: ["Hero", "Custom"],
    interaction_custom_targets: ["", "Dog"],
  }],
  videos: [{
    source_type: "Future Video",
    custom_source_type: "Future Video",
    control_role: "Future Role",
    custom_control_role: "Future Role",
  }],
});
assert.equal(preservedTaxonomyState.images[0].source_type, "Custom");
assert.equal(preservedTaxonomyState.images[0].custom_source_type, "Future Image");
assert.equal(preservedTaxonomyState.images[0].owner, "ExistingTarget");
assert.deepEqual(preservedTaxonomyState.images[0].legacy_relationship_targets, ["Hero", "Dog"]);
assert.equal(preservedTaxonomyState.videos[0].source_type, "Custom");
assert.equal(preservedTaxonomyState.videos[0].custom_source_type, "Future Video");
assert.equal(preservedTaxonomyState.videos[0].control_role, "Custom Role");
assert.equal(preservedTaxonomyState.videos[0].custom_control_role, "Future Role");

const unnamedMeaningState = prompt.normalizeState({
  images: [{ source_type: "Custom", custom_source_type: "Unnamed idea" }],
  videos: [{ source_type: "Motion Reference", control_role: "Context Only" }],
});
assert.equal(unnamedMeaningState.images[0].present, true);
assert.equal(unnamedMeaningState.videos[0].present, true);

const textInput = fakeElement();
const nextTextInput = fakeElement();
const promptContainer = fakeElement();
const promptGuardClip = fakeElement(promptContainer, "hmb-dashboard-clip");
const promptGuardDashboard = fakeElement(promptGuardClip, "hmb-dashboard");
const promptImageCard = fakeElement(promptGuardDashboard, "group-card image-card");
const promptVideoBackground = fakeElement(promptGuardDashboard, "source-scrollbox video-background");
for (const element of [promptContainer, promptGuardClip, promptGuardDashboard]) {
  element.classList.add("nodrag", "nopan", "nowheel");
}
promptImageCard.classList.add("nodrag", "nopan", "nowheel");
promptContainer.contains = (element) => element === textInput || element === nextTextInput;
promptContainer.querySelector = (selector) => {
  if (selector === ".hmb-dashboard-clip") return promptGuardClip;
  if (selector === ".hmb-dashboard") return promptGuardDashboard;
  if (selector === ".image-card") return promptImageCard;
  return null;
};
promptContainer.querySelectorAll = (selector) => (
  selector.includes("input") || selector === "textarea" ? [textInput, nextTextInput] : []
);
const listeners = [];
prompt.hmbInstallPromptInteractionIsolation(promptContainer, listeners);

let stopped = 0;
let prevented = 0;
for (const element of [promptContainer, promptGuardClip, promptGuardDashboard]) {
  assert.ok(element.classList.contains("nodrag"), "Prompt roots continue to prevent whole-node dragging.");
  assert.equal(element.classList.contains("nopan"), false, "Prompt background must pass drag-pan gestures.");
  assert.equal(element.classList.contains("nowheel"), false, "Prompt background must pass wheel zoom.");
}
assert.equal(
  typeof promptContainer.handler("pointerdown"),
  "function",
  "Prompt interior pointerdown must stay local so only the native title bar selects the node.",
);
let promptRootStops = 0;
promptContainer.handler("pointerdown")({
  stopPropagation() { promptRootStops += 1; },
});
assert.equal(promptRootStops, 1);
assert.equal(
  promptContainer.handler("click"),
  undefined,
  "Prompt background clicks are not swallowed by the widget root.",
);
assert.equal(promptContainer.handler("wheel"), undefined);
for (const className of ["nodrag", "nopan", "nowheel"]) {
  assert.equal(
    promptImageCard.classList.contains(className),
    false,
    `IMAGE SOURCE BINDING clears stale ${className} isolation.`,
  );
}
assert.equal(promptImageCard.handler("pointerdown"), undefined);
assert.equal(promptImageCard.handler("click"), undefined);
assert.equal(promptImageCard.handler("wheel"), undefined);
assert.equal(promptVideoBackground.classList.contains("nopan"), false);
assert.equal(promptVideoBackground.classList.contains("nowheel"), false);
assert.equal(promptVideoBackground.handler("wheel"), undefined);
assert.equal(
  promptVideoBackground.handler("pointerdown"),
  undefined,
  "Non-image source backgrounds remain available for canvas panning.",
);
promptContainer.handler("keydown")({
  key: "Backspace",
  target: textInput,
  stopPropagation() { stopped += 1; },
  preventDefault() { prevented += 1; },
});
assert.equal(stopped, 1, "Backspace is isolated from React Flow.");
assert.equal(prevented, 0, "Backspace keeps its native single-character editing action.");
promptContainer.handler("keydown")({
  key: "Delete",
  target: textInput,
  stopPropagation() { stopped += 1; },
  preventDefault() { prevented += 1; },
});
assert.equal(stopped, 2, "Delete is isolated from React Flow.");
assert.equal(prevented, 0, "Delete keeps its native text editing action.");
assert.ok(textInput.classList.contains("nodrag"));
assert.ok(textInput.classList.contains("nopan"));
assert.ok(textInput.classList.contains("nowheel"));
assert.equal(typeof textInput.handler("mousedown"), "function", "Mouse selection stays inside the text bar.");
textInput.handler("mousedown")({
  stopPropagation() { stopped += 1; },
});
assert.equal(stopped, 3, "Mouse-down does not select the whole library node.");
globalThis.document.activeElement = textInput;
assert.equal(
  prompt.hmbShouldDeferPromptTextCommit(promptContainer),
  false,
  "Focus alone must not suppress the trailing Prompt state publish.",
);
promptContainer.__hmbPromptLibraryCompositionActive = true;
assert.equal(
  prompt.hmbShouldDeferPromptTextCommit(promptContainer),
  true,
  "Only an active IME composition defers the trailing Prompt state publish.",
);
promptContainer.__hmbPromptLibraryCompositionActive = false;
const promptDeleteCapture = windowHandlers.get("keydown:true");
assert.equal(typeof promptDeleteCapture, "function", "Selected Prompt nodes need a capture-phase delete guard.");
let captureStopped = 0;
let capturePrevented = 0;
promptDeleteCapture({
  key: "Backspace",
  target: textInput,
  stopPropagation() { captureStopped += 1; },
  stopImmediatePropagation() { captureStopped += 1; },
  preventDefault() { capturePrevented += 1; },
});
assert.equal(captureStopped, 0, "The capture guard leaves focused text editing untouched.");
assert.equal(capturePrevented, 0, "Backspace keeps its native text editing default.");
let blurFinalizations = 0;
prompt.hmbRememberPromptTextPointerTarget(promptContainer, { target: nextTextInput });
assert.equal(
  prompt.hmbPromptBlurStaysInsideEditable(promptContainer, {
    currentTarget: textInput,
    relatedTarget: null,
  }),
  true,
  "Pointer-down on the next text bar is remembered before the previous bar blurs.",
);
assert.equal(
  prompt.hmbFinalizePromptTextBlur(
    promptContainer,
    { currentTarget: textInput, relatedTarget: nextTextInput },
    () => { blurFinalizations += 1; },
  ),
  false,
  "Switching between text bars must not emit and remount the widget before the first click focuses the target.",
);
assert.equal(blurFinalizations, 0);
prompt.hmbRememberPromptTextPointerTarget(promptContainer, { target: null });
assert.equal(
  prompt.hmbFinalizePromptTextBlur(
    promptContainer,
    { currentTarget: nextTextInput, relatedTarget: null },
    () => { blurFinalizations += 1; },
  ),
  true,
  "Leaving the text-editing area still performs the final persistent state commit.",
);
assert.equal(blurFinalizations, 1);
assert.ok(
  listeners.some(([element, type]) => element === promptContainer && type === "keydown"),
  "The keyboard listener is registered for cleanup.",
);

console.log("HMB Picker layout and Prompt keyboard-interaction regression: PASS");
