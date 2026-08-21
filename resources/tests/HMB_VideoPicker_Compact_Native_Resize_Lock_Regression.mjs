import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const picker = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);

const LOCK_ATTRIBUTE = "data-hmb-video-picker-resize-locked";
const LOCK_STYLE_ATTRIBUTE = "data-hmb-video-picker-resize-lock-style";

function classList(value = "") {
  const values = new Set(String(value).split(/\s+/).filter(Boolean));
  return {
    contains(name) { return values.has(String(name)); },
  };
}

function listenerCapture(options) {
  return options === true || Boolean(options && typeof options === "object" && options.capture);
}

function fakeElement(className = "", ownerDocument = null) {
  const attributes = new Map();
  const listeners = new Map();
  const element = {
    className,
    classList: classList(className),
    ownerDocument,
    parentElement: null,
    children: [],
    style: {},
    textContent: "",
    _attributes: attributes,
    _listeners: listeners,
    setAttribute(name, value) { attributes.set(String(name), String(value)); },
    getAttribute(name) { return attributes.get(String(name)) || ""; },
    hasAttribute(name) { return attributes.has(String(name)); },
    removeAttribute(name) { attributes.delete(String(name)); },
    appendChild(child) {
      child.parentElement = this;
      child.ownerDocument ||= this.ownerDocument;
      this.children.push(child);
      return child;
    },
    remove() {
      if (!this.parentElement) return;
      const index = this.parentElement.children.indexOf(this);
      if (index >= 0) this.parentElement.children.splice(index, 1);
      this.parentElement = null;
    },
    contains(candidate) {
      if (candidate === this) return true;
      return this.children.some((child) => child.contains?.(candidate));
    },
    closest(selector) {
      let current = this;
      while (current) {
        if (selector === ".react-flow__node" && current.classList?.contains("react-flow__node")) {
          return current;
        }
        if (
          selector === ".react-flow__resize-control"
          && current.classList?.contains("react-flow__resize-control")
        ) return current;
        current = current.parentElement;
      }
      return null;
    },
    addEventListener(type, handler, options = false) {
      const key = String(type);
      const entries = listeners.get(key) || [];
      entries.push({ handler, options });
      listeners.set(key, entries);
    },
    removeEventListener(type, handler, options = false) {
      const key = String(type);
      const capture = listenerCapture(options);
      const entries = (listeners.get(key) || []).filter((entry) => (
        entry.handler !== handler || listenerCapture(entry.options) !== capture
      ));
      if (entries.length) listeners.set(key, entries);
      else listeners.delete(key);
    },
    dispatch(type, event) {
      for (const entry of [...(listeners.get(String(type)) || [])]) entry.handler.call(this, event);
    },
  };
  return element;
}

function listenerCounts(element) {
  return Object.fromEntries(
    [...element._listeners.entries()].map(([type, entries]) => [type, entries.length]),
  );
}

function surfaceSnapshot(element) {
  return JSON.stringify({
    attributes: [...element._attributes.entries()].sort(),
    style: Object.entries(element.style).sort(),
    listeners: Object.entries(listenerCounts(element)).sort(),
  });
}

function pointerEvent(target) {
  return {
    target,
    defaultPrevented: false,
    propagationStopped: false,
    immediatePropagationStopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; },
    stopImmediatePropagation() { this.immediatePropagationStopped = true; },
  };
}

const observers = [];
class TestMutationObserver {
  constructor(callback) {
    this.callback = callback;
    this.disconnected = false;
    observers.push(this);
  }
  observe() {}
  disconnect() { this.disconnected = true; }
}

const documentStub = {
  head: null,
  defaultView: { MutationObserver: TestMutationObserver },
  createElement(className = "") { return fakeElement(className, documentStub); },
};
documentStub.head = fakeElement("document-head", documentStub);
const baselineStyle = fakeElement("baseline-style", documentStub);
baselineStyle.textContent = ".workspace{transform:none}";
documentStub.head.appendChild(baselineStyle);

const canvas = fakeElement("react-flow__renderer", documentStub);
canvas.style.transform = "matrix(1,0,0,1,25,30)";
canvas.setAttribute("data-canvas-state", "stable");
const workspace = canvas.appendChild(fakeElement("react-flow__viewport", documentStub));
workspace.style.width = "4096px";
workspace.setAttribute("data-workspace-state", "stable");

const pickerShell = workspace.appendChild(fakeElement("react-flow__node picker-node", documentStub));
pickerShell.setAttribute(LOCK_ATTRIBUTE, "legacy-lock");
pickerShell.style.height = "1200px";
const pickerContainer = pickerShell.appendChild(fakeElement("hmb-picker-widget", documentStub));
const pickerResizeControl = pickerShell.appendChild(fakeElement("react-flow__resize-control", documentStub));
pickerResizeControl.style.display = "inline-flex";
pickerResizeControl.style.visibility = "visible";
pickerResizeControl.style.pointerEvents = "auto";
pickerResizeControl.style.opacity = "0.6";

const siblingShell = workspace.appendChild(fakeElement("react-flow__node sibling-node", documentStub));
siblingShell.setAttribute(LOCK_ATTRIBUTE, "sibling-owned-value");
siblingShell.style.height = "700px";
const siblingResizeControl = siblingShell.appendChild(fakeElement("react-flow__resize-control", documentStub));
siblingResizeControl.style.display = "inline-flex";

let preexistingPickerPointerDowns = 0;
const preexistingPickerPointerDown = () => { preexistingPickerPointerDowns += 1; };
pickerShell.addEventListener("pointerdown", preexistingPickerPointerDown, true);
const untouchedSiblingListener = () => {};
siblingShell.addEventListener("pointerdown", untouchedSiblingListener, true);
const untouchedCanvasListener = () => {};
canvas.addEventListener("pointerdown", untouchedCanvasListener, true);

const siblingBefore = surfaceSnapshot(siblingShell);
const workspaceBefore = surfaceSnapshot(workspace);
const canvasBefore = surfaceSnapshot(canvas);
const pickerControlStyleBefore = JSON.stringify(pickerResizeControl.style);
const siblingControlStyleBefore = JSON.stringify(siblingResizeControl.style);
const baselineHeadChildren = [...documentStub.head.children];

const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };

check(
  picker.hmbSetVideoPickerNativeResizeLocked(pickerContainer, true) === true,
  "compact mode must acquire the exact Picker shell resize lock",
);
check(
  pickerShell.getAttribute(LOCK_ATTRIBUTE) === "true",
  "compact Picker shell must expose data-hmb-video-picker-resize-locked=true",
);
check(
  siblingShell.getAttribute(LOCK_ATTRIBUTE) === "sibling-owned-value",
  "the sibling node resize-lock attribute must remain untouched",
);

const injectedStyles = documentStub.head.children.filter(
  (element) => element.hasAttribute?.(LOCK_STYLE_ATTRIBUTE),
);
check(injectedStyles.length === 1, `one scoped resize-lock style is required; received ${injectedStyles.length}`);
const injectedCss = injectedStyles[0]?.textContent || "";
check(
  injectedCss.includes(`[${LOCK_ATTRIBUTE}="true"] .react-flow__resize-control`),
  "native resize-control hiding CSS must be scoped to a locked Picker shell",
);
for (const declaration of [
  "display:none!important",
  "visibility:hidden!important",
  "pointer-events:none!important",
  "opacity:0!important",
]) {
  check(injectedCss.includes(declaration), `resize-lock CSS must contain ${declaration}`);
}
check(
  JSON.stringify(pickerResizeControl.style) === pickerControlStyleBefore,
  "locking must hide the Picker control through scoped CSS without overwriting its inline style",
);

const lockedPointer = pointerEvent(pickerResizeControl);
pickerShell.dispatch("pointerdown", lockedPointer);
check(lockedPointer.defaultPrevented, "compact Picker resize pointerdown must be prevented");
check(lockedPointer.propagationStopped, "compact Picker resize pointerdown propagation must stop");
check(lockedPointer.immediatePropagationStopped, "compact Picker resize pointerdown must stop immediately");
check(
  preexistingPickerPointerDowns === 1,
  "pre-existing Picker listener remains registered while the capture guard blocks the resize start",
);

const foreignControlPointer = pointerEvent(siblingResizeControl);
pickerShell.dispatch("pointerdown", foreignControlPointer);
check(
  !foreignControlPointer.defaultPrevented,
  "the Picker guard must ignore a resize control outside its exact node shell",
);
const siblingPointer = pointerEvent(siblingResizeControl);
siblingShell.dispatch("pointerdown", siblingPointer);
check(!siblingPointer.defaultPrevented, "sibling node resize pointerdown must remain available");

check(surfaceSnapshot(siblingShell) === siblingBefore, "compact locking must not mutate the sibling node");
check(surfaceSnapshot(workspace) === workspaceBefore, "compact locking must not mutate the workspace");
check(surfaceSnapshot(canvas) === canvasBefore, "compact locking must not mutate the React Flow canvas");
check(
  JSON.stringify(siblingResizeControl.style) === siblingControlStyleBefore,
  "compact locking must not rewrite the sibling resize-control style",
);

const lockedListenerCounts = listenerCounts(pickerShell);
check(lockedListenerCounts.pointerdown === 2, "lock must add exactly one Picker pointerdown guard");
check(lockedListenerCounts.mousedown === 1, "lock must add exactly one Picker mousedown guard");
check(lockedListenerCounts.touchstart === 1, "lock must add exactly one Picker touchstart guard");

check(
  picker.hmbSetVideoPickerNativeResizeLocked(pickerContainer, false) === true,
  "expand/cleanup must release the Picker shell resize lock",
);
check(
  pickerShell.getAttribute(LOCK_ATTRIBUTE) === "legacy-lock",
  "expand/cleanup must restore the Picker shell's prior resize-lock attribute exactly",
);
check(
  pickerContainer.__hmbVideoPickerResizeLockRoot === undefined,
  "expand/cleanup must release the container's resize-lock owner reference",
);
check(
  JSON.stringify(listenerCounts(pickerShell)) === JSON.stringify({ pointerdown: 1 }),
  "expand/cleanup must remove only the three installed guards and retain prior listeners",
);
check(
  documentStub.head.children.length === baselineHeadChildren.length
    && documentStub.head.children.every((element, index) => element === baselineHeadChildren[index]),
  "expand/cleanup must remove only its injected style and preserve pre-existing document styles",
);
check(
  observers.length === 1 && observers[0].disconnected === true,
  "expand/cleanup must disconnect the resize-lock attribute observer",
);
check(
  JSON.stringify(pickerResizeControl.style) === pickerControlStyleBefore,
  "expand/cleanup must preserve the Picker resize-control's prior inline style exactly",
);

const releasedPointer = pointerEvent(pickerResizeControl);
pickerShell.dispatch("pointerdown", releasedPointer);
check(!releasedPointer.defaultPrevented, "released Picker resize pointerdown must no longer be blocked");
check(preexistingPickerPointerDowns === 3, "the pre-existing Picker pointer listener must survive cleanup");
check(surfaceSnapshot(siblingShell) === siblingBefore, "cleanup must leave the sibling node untouched");
check(surfaceSnapshot(workspace) === workspaceBefore, "cleanup must leave the workspace untouched");
check(surfaceSnapshot(canvas) === canvasBefore, "cleanup must leave the React Flow canvas untouched");

const toggleStart = widgetSource.indexOf("const togglePickerView = () => {");
const toggleEnd = widgetSource.indexOf("const commandBridge = () => {", toggleStart);
const toggleSource = widgetSource.slice(toggleStart, toggleEnd);
check(
  /hmbSetVideoPickerNativeResizeLocked\(container, true\)/.test(toggleSource),
  "compact transition must acquire the native resize lock",
);
check(
  /hmbSetVideoPickerNativeResizeLocked\(container, false\)/.test(toggleSource),
  "expanded transition must release the native resize lock",
);

if (failures.length) {
  throw new Error(
    `HMB VideoPicker compact native resize-lock regression failed:\n- ${failures.join("\n- ")}`,
  );
}

console.log("HMB VideoPicker compact native resize-lock regression: PASS");
