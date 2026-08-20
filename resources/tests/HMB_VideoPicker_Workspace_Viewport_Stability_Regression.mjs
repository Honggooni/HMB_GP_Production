import assert from "node:assert/strict";
import fs from "node:fs";

const pickerPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const bridgePath = new URL("../../widgets/HMBVideoPickerCommandBridgeWidget_v032.js", import.meta.url);
const pythonPath = new URL("../../HMBVideoPickerLibrary.py", import.meta.url);
const pickerSource = fs.readFileSync(pickerPath, "utf8");
const bridgeSource = fs.readFileSync(bridgePath, "utf8");
const pythonSource = fs.readFileSync(pythonPath, "utf8");

assert.match(pythonSource, /PICKER_NATIVE_SIZE_VERSION\s*=\s*4/);
assert.match(pythonSource, /PICKER_COMPACT_NATIVE_HEIGHT\s*=\s*360/);
assert.match(
  pythonSource,
  /prepared_metadata\["size"\]\s*=\s*dict\(compact_size\)[\s\S]*?super\(\)\.__init__\(\*\*prepared_kwargs\)/,
  "Serialized outer geometry is normalized before the host sees the node.",
);

for (const [name, source] of [["Picker", pickerSource], ["Command bridge", bridgeSource]]) {
  assert.doesNotMatch(source, /\.closest\?\.\("\.react-flow"\)|\.closest\("\.react-flow"\)/, `${name} cannot locate the canvas root.`);
  assert.doesNotMatch(source, /updateNodeInternals|hmb:request-node-internals-update/, `${name} cannot publish node geometry.`);
  assert.doesNotMatch(source, /canvasRoot|fitView|fitBounds|setViewport|zoomTo|panBy|setCenter/, `${name} cannot control the viewport.`);
  assert.doesNotMatch(source, /shell\.style|nodeRoot\.style/, `${name} cannot style the outer node.`);
}
assert.doesNotMatch(bridgeSource, /__hmbPickerCommandBridge/, "Command transport cannot be stored on the React Flow node.");
assert.match(bridgeSource, /__hmbVideoPickerCommandBridgeRegistryV1/, "Command transport is runtime-id scoped.");

const picker = await import(`${pickerPath.href}?canvas-boundary=${Date.now()}`);
const commandBridge = await import(`${bridgePath.href}?canvas-boundary=${Date.now()}`);

function style(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    setProperty(name, value) { values.set(name, String(value)); this[name.replace(/-([a-z])/g, (_m, c) => c.toUpperCase())] = String(value); },
    removeProperty(name) { values.delete(name); delete this[name.replace(/-([a-z])/g, (_m, c) => c.toUpperCase())]; },
    getPropertyValue(name) { return values.get(name) || ""; },
    getPropertyPriority() { return ""; },
  };
}

const shell = {
  style: style({ width: "1400px", height: "360px", "min-height": "360px", "max-height": "360px" }),
  dataset: {},
  addEventListener() { throw new Error("VideoPicker attempted to register on the outer node"); },
  dispatchEvent() { throw new Error("VideoPicker attempted to dispatch through the outer node"); },
};
const clip = { style: style(), dataset: {} };
const dashboard = {
  style: style(),
  dataset: {},
  offsetHeight: 0,
  scrollHeight: 0,
  getAttribute(name) { return name === "data-picker-view" ? "compact" : ""; },
  getBoundingClientRect() { return { height: 0 }; },
};
const container = {
  parentElement: shell,
  style: style(),
  dataset: {},
  __hmbVideoPickerExpanded: false,
  querySelector(selector) {
    if (selector === ".hmbvp") return dashboard;
    if (selector === ".hmbvp-clip") return clip;
    return null;
  },
  setAttribute() {},
  removeAttribute() {},
};
const viewportBefore = Object.freeze({ x: -842, y: -116, zoom: 0.42 });
const shellBefore = {
  width: shell.style.getPropertyValue("width"),
  height: shell.style.getPropertyValue("height"),
  minHeight: shell.style.getPropertyValue("min-height"),
  maxHeight: shell.style.getPropertyValue("max-height"),
};

assert.equal(picker.hmbApplyVideoPickerCompactHostSizing(container, { picker_shots: [] }), 158);
assert.deepEqual({
  width: shell.style.getPropertyValue("width"),
  height: shell.style.getPropertyValue("height"),
  minHeight: shell.style.getPropertyValue("min-height"),
  maxHeight: shell.style.getPropertyValue("max-height"),
}, shellBefore, "Compact content cannot alter the outer node.");
assert.equal(clip.style.getPropertyValue("height"), "158px");
assert.equal(dashboard.style.getPropertyValue("height"), "158px");
assert.equal(picker.hmbSetVideoPickerNativeResizeLocked(container, true), false);
assert.equal(picker.hmbReleaseVideoPickerCompactOuterGeometry(container), false);
assert.equal(picker.hmbRequestVideoPickerNodeInternalsUpdate(container, { updateNodeInternals() { throw new Error("must not run"); } }), false);
assert.equal(picker.hmbScheduleVideoPickerNodeInternalsUpdate(container, {}, { force: true }), false);
assert.equal(picker.hmbInstallVideoPickerCanvasMotionDelegation(container, []), false);
assert.deepEqual(viewportBefore, { x: -842, y: -116, zoom: 0.42 });

const firstMount = { __hmbVideoPickerRuntimeInstanceId: "picker-runtime-1" };
const replacementMount = { __hmbVideoPickerRuntimeInstanceId: "picker-runtime-1" };
picker.hmbRememberVideoPickerViewMode(firstMount, true);
assert.equal(picker.hmbVideoPickerStoredViewMode(replacementMount), true, "Runtime-local remount preserves view mode without a node lookup.");

let delivered = null;
const bridgeContainer = {
  style: style(),
  setAttribute() {},
  parentElement: null,
};
const bridgeController = commandBridge.default(bridgeContainer, {
  value: { runtime_instance_id: "picker-runtime-1" },
  onChange(command) { delivered = command; return true; },
});
const registry = globalThis.__hmbVideoPickerCommandBridgeRegistryV1;
assert.ok(registry instanceof Map);
registry.get("picker-runtime-1").dispatch({
  runtime_instance_id: "picker-runtime-1",
  action: "browse_maya_scene",
  action_id: "action-1",
  payload: {},
});
assert.equal(delivered.action, "browse_maya_scene");
bridgeController.cleanup();
assert.equal(registry.has("picker-runtime-1"), false);

console.log("HMB VideoPicker strict canvas-boundary regression: PASS");
