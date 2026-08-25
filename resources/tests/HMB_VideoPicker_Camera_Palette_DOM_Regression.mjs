import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widgetModule = await import(`data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`);

const tr = {
  noCamera: "NO CAMERA",
  fixed: "FIXED",
  selectCamera: "SELECT CAMERA",
  registered: "REGISTERED",
  renderable: "RENDERABLE",
  cameraLabel: "CAMERA",
};

const attributes = new Map();
const cameraWrapper = {
  innerHTML: "",
  getAttribute(name) { return attributes.get(name) || ""; },
  setAttribute(name, value) { attributes.set(name, String(value)); },
  querySelectorAll() { return []; },
  querySelector() { return null; },
};
const cameraContainer = {
  querySelector(selector) { return selector === ".picker-camera-control" ? cameraWrapper : null; },
};

assert.equal(widgetModule.hmbPatchPickerCameraControlDom(cameraContainer, { cameras: [] }, tr, false), true);
assert.match(cameraWrapper.innerHTML, /NO CAMERA/);
assert.equal(widgetModule.hmbPatchPickerCameraControlDom(cameraContainer, { cameras: [] }, tr, false), false);

const singleCamera = {
  cameras: [{ full_path: "|camera1", name: "camera1", default_camera: false }],
  selected_camera: "|camera1",
};
assert.equal(widgetModule.hmbPatchPickerCameraControlDom(cameraContainer, singleCamera, tr, false), true);
assert.match(cameraWrapper.innerHTML, /camera1/);
assert.doesNotMatch(cameraWrapper.innerHTML, /NO CAMERA/);

const multipleCameras = {
  cameras: [
    { full_path: "|camera1", name: "camera1", default_camera: false },
    { full_path: "|camera2", name: "camera2", default_camera: false },
  ],
  selected_camera: "|camera2",
};
assert.equal(widgetModule.hmbPatchPickerCameraControlDom(cameraContainer, multipleCameras, tr, false), true);
assert.match(cameraWrapper.innerHTML, /data-camera-path="\|camera1"/);
assert.match(cameraWrapper.innerHTML, /data-camera-path="\|camera2"/);
assert.equal(widgetModule.hmbPatchPickerCameraControlDom(cameraContainer, multipleCameras, tr, true), true);
assert.match(cameraWrapper.innerHTML, /disabled/);
assert.equal(widgetModule.hmbPatchPickerCameraControlDom(cameraContainer, { cameras: [] }, tr, false), true);
assert.match(cameraWrapper.innerHTML, /NO CAMERA/);

function delegatedRoot() {
  const listeners = new Map();
  return {
    listeners,
    addEventListener(name, listener) { listeners.set(name, listener); },
    removeEventListener(name, listener) {
      if (listeners.get(name) === listener) listeners.delete(name);
    },
    contains(control) { return control?.owner === this; },
  };
}

function delegatedControl(root, selector, attributeName, value) {
  return {
    owner: root,
    disabled: false,
    nodeType: 1,
    closest(requestedSelector) { return requestedSelector === selector ? this : null; },
    getAttribute(name) { return name === attributeName ? value : ""; },
  };
}

const cameraRoot = delegatedRoot();
const cameraCleanup = [];
const selectedCameras = [];
assert.equal(widgetModule.hmbInstallPickerValueControlDelegation(
  cameraRoot,
  "[data-camera-path]",
  "data-camera-path",
  (value) => selectedCameras.push(value),
  cameraCleanup,
), true);
// The control is created after delegation is installed, matching READ's
// no-camera -> camera-list DOM replacement.
const newCameraButton = delegatedControl(cameraRoot, "[data-camera-path]", "data-camera-path", "|camera2");
cameraRoot.listeners.get("click")({ target: newCameraButton });
assert.deepEqual(selectedCameras, ["|camera2"]);
newCameraButton.disabled = true;
cameraRoot.listeners.get("click")({ target: newCameraButton });
assert.deepEqual(selectedCameras, ["|camera2"]);
cameraCleanup.forEach((cleanup) => cleanup());
assert.equal(cameraRoot.listeners.has("click"), false);

const paletteRoot = delegatedRoot();
const paletteCleanup = [];
const selectedColors = [];
widgetModule.hmbInstallPickerValueControlDelegation(
  paletteRoot,
  "[data-color]",
  "data-color",
  (value) => selectedColors.push(value),
  paletteCleanup,
);
const colorButton = delegatedControl(paletteRoot, "[data-color]", "data-color", "Actor_Red");
paletteRoot.listeners.get("click")({ target: colorButton });
assert.deepEqual(selectedColors, ["Actor_Red"]);
paletteCleanup.forEach((cleanup) => cleanup());

assert.match(
  widgetSource,
  /hmbApplyPickerPaletteSelectionToDom\(container, nextState, immediateMediaLocked\);/,
  "Palette activation must follow the local Maya operation lock, not Shot workspace publication.",
);
assert.match(widgetSource, /class="picker-camera-control"/);

console.log("HMB VideoPicker camera reconstruction and palette delegation regression: PASS");
