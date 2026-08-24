import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const pythonPath = new URL("../../HMBVideoPickerLibrary.py", import.meta.url);
const pythonSource = fs.readFileSync(pythonPath, "utf8");
const picker = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

assert.equal(typeof picker.hmbVideoPickerIsHostMeasurementClone, "function");
assert.equal(typeof picker.hmbMountVideoPickerHostMeasurement, "function");
assert.equal(typeof picker.hmbSyncVideoPickerHostMeasurement, "function");
assert.equal(typeof picker.hmbVideoPickerCompactMeasurementHeight, "function");

function fakeStyle(initial = {}) {
  const values = new Map();
  const priorities = new Map();
  const style = {};
  const camel = (name) => String(name).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
  const remember = (name, value, priority = "") => {
    const property = String(name);
    const text = String(value);
    values.set(property, text);
    if (priority) priorities.set(property, String(priority));
    else priorities.delete(property);
    style[camel(property)] = text;
  };
  Object.entries(initial).forEach(([name, value]) => remember(name, value));
  style.setProperty = remember;
  style.getPropertyValue = (name) => values.get(String(name)) || style[camel(name)] || "";
  style.getPropertyPriority = (name) => priorities.get(String(name)) || "";
  style.removeProperty = (name) => {
    const property = String(name);
    const previous = values.get(property) || style[camel(property)] || "";
    values.delete(property);
    priorities.delete(property);
    delete style[camel(property)];
    return previous;
  };
  return style;
}

function fakeClassList(...initial) {
  const values = new Set(initial.flatMap((value) => String(value || "").split(/\s+/)).filter(Boolean));
  return {
    add(...items) { items.forEach((item) => values.add(String(item))); },
    remove(...items) { items.forEach((item) => values.delete(String(item))); },
    contains(item) { return values.has(String(item)); },
    toString() { return [...values].join(" "); },
  };
}

function fakeElement(className = "", ownerDocument = null) {
  const attributes = new Map();
  const element = {
    className,
    classList: fakeClassList(className),
    dataset: {},
    style: fakeStyle(),
    children: [],
    childNodes: [],
    parentElement: null,
    ownerDocument,
    setAttribute(name, value) {
      attributes.set(String(name), String(value));
      if (String(name).startsWith("data-")) {
        const key = String(name).slice(5).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
        this.dataset[key] = String(value);
      }
    },
    getAttribute(name) { return attributes.get(String(name)) || ""; },
    hasAttribute(name) { return attributes.has(String(name)); },
    removeAttribute(name) {
      attributes.delete(String(name));
      if (String(name).startsWith("data-")) {
        const key = String(name).slice(5).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
        delete this.dataset[key];
      }
    },
    appendChild(child) {
      child.parentElement = this;
      child.ownerDocument ||= this.ownerDocument;
      this.children.push(child);
      this.childNodes = this.children;
      return child;
    },
    replaceChildren(...children) {
      this.children.forEach((child) => { child.parentElement = null; });
      this.children = [];
      this.childNodes = this.children;
      children.forEach((child) => this.appendChild(child));
    },
    querySelector(selector) {
      const text = String(selector || "");
      const matches = (candidate) => {
        if (text === "[data-hmb-video-picker-measurement-box]") {
          return candidate.hasAttribute?.("data-hmb-video-picker-measurement-box");
        }
        if (text === ".hmbvp" || text === ".hmbvp-clip") {
          return candidate.classList?.contains(text.slice(1));
        }
        return false;
      };
      const queue = [...this.children];
      while (queue.length) {
        const candidate = queue.shift();
        if (matches(candidate)) return candidate;
        queue.push(...(candidate.children || []));
      }
      return null;
    },
    closest(selector) {
      let current = this;
      while (current) {
        if (selector === ".react-flow__node" && current.classList?.contains("react-flow__node")) {
          return current;
        }
        current = current.parentElement;
      }
      return null;
    },
  };
  return element;
}

function attach(parent, child) {
  parent.appendChild(child);
  return child;
}

const savedGlobals = Object.fromEntries([
  "document", "window", "MutationObserver", "requestAnimationFrame", "cancelAnimationFrame",
].map((name) => [name, globalThis[name]]));

const observers = [];
class TestMutationObserver {
  constructor(callback) {
    this.callback = callback;
    this.observed = [];
    this.disconnected = false;
    observers.push(this);
  }
  observe(target, options) { this.observed.push({ target, options }); }
  disconnect() { this.disconnected = true; }
  flush() { if (!this.disconnected) this.callback([], this); }
}

let frameSequence = 1;
const frames = new Map();
const requestFrame = (callback) => {
  const handle = frameSequence++;
  frames.set(handle, callback);
  return handle;
};
const cancelFrame = (handle) => frames.delete(handle);
const flushFrames = () => {
  for (let pass = 0; pass < 20 && frames.size; pass += 1) {
    const pending = [...frames.entries()];
    frames.clear();
    pending.forEach(([_handle, callback]) => callback(Date.now()));
  }
  assert.equal(frames.size, 0, "The simulated host must settle without an animation-frame loop.");
};

const documentStub = {
  body: {},
  documentElement: {},
  createElement(className = "") { return fakeElement(className, documentStub); },
};

const emptyShotState = {
  picker_shots: [{ shot_number: 1, video_asset_uids: [] }],
};
const publisherUuid = "11111111-1111-4111-8111-111111111111";
const channelUuid = "22222222-2222-4222-8222-222222222222";
const shotUuids = [
  "31111111-1111-4111-8111-111111111111",
  "32222222-2222-4222-8222-222222222222",
  "33333333-3333-4333-8333-333333333333",
];
const workspaceUuids = [
  "41111111-1111-4111-8111-111111111111",
  "42222222-2222-4222-8222-222222222222",
  "43333333-3333-4333-8333-333333333333",
];
const populatedThreeShotState = {
  shot_publisher_instance_uuid: publisherUuid,
  channel_uuid: channelUuid,
  shot_uuid: shotUuids[0],
  shot_number: 1,
  shot_name: "Shot 1",
  shot_selections: shotUuids.map((shot_uuid, index) => ({
    shot_uuid,
    number: index + 1,
    name: `Shot ${index + 1}`,
    revision: 1,
  })),
  picker_shots: [
    {
      workspace_uuid: workspaceUuids[0],
      number: 1,
      bound_shot_uuid: shotUuids[0],
      video_asset_uids: ["video-1"],
    },
    {
      workspace_uuid: workspaceUuids[1],
      number: 2,
      bound_shot_uuid: shotUuids[1],
      video_asset_uids: [],
    },
    {
      workspace_uuid: workspaceUuids[2],
      number: 3,
      bound_shot_uuid: shotUuids[2],
      video_asset_uids: [],
    },
  ],
  active_picker_shot_uuid: workspaceUuids[0],
  videos: [{ video_uid: "video-1", video_path: "C:/media/one.mp4", label: "one.mp4" }],
};

function pythonFunctionSource(functionName) {
  const start = pythonSource.indexOf(`def ${functionName}(`);
  assert.notEqual(start, -1, `Python function ${functionName} must exist.`);
  const next = pythonSource.indexOf("\ndef ", start + 1);
  return pythonSource.slice(start, next === -1 ? pythonSource.length : next);
}

function expandableContract(functionName) {
  const body = pythonFunctionSource(functionName);
  const match = body.match(/"expandable"\s*:\s*(True|False)/);
  assert.ok(match, `${functionName} must declare its host allocator contract.`);
  return match[1] === "True";
}

// Griptape's adaptive allocator starts an unmeasured custom row at 40px. A
// fill/non-expandable row keeps only that base height and the trailing spacer
// receives the remainder. An expandable row receives the free stack height on
// that same first pass, before the visibility:hidden measurement clone settles.
function adaptiveAllocatorFirstPass(stackHeight, expandable, measuredRowHeight = 0) {
  const initialRowHeight = measuredRowHeight > 0 ? measuredRowHeight : 40;
  const bottomReserve = 16;
  const remaining = Math.max(0, stackHeight - initialRowHeight - bottomReserve);
  return {
    rowHeight: initialRowHeight + (expandable ? remaining : 0),
    trailingSpacerHeight: expandable ? 0 : remaining,
  };
}

try {
  globalThis.document = documentStub;
  globalThis.window = {
    getComputedStyle(element) {
      return {
        display: element?.style?.display || "block",
        visibility: element?.style?.visibility || "visible",
      };
    },
  };
  globalThis.MutationObserver = TestMutationObserver;
  globalThis.requestAnimationFrame = requestFrame;
  globalThis.cancelAnimationFrame = cancelFrame;

  const shell = fakeElement("react-flow__node", documentStub);
  shell.style.height = "360px";
  shell.style.minHeight = "360px";
  shell.style.maxHeight = "360px";

  const measurementLayer = attach(shell, fakeElement(
    "absolute left-0 right-0 pointer-events-none",
    documentStub,
  ));
  measurementLayer.style.visibility = "hidden";
  const measurementRow = attach(measurementLayer, fakeElement("adaptive-row", documentStub));
  const measurementContainer = attach(measurementRow, fakeElement("raw-widget", documentStub));

  assert.equal(picker.hmbVideoPickerIsHostMeasurementClone(measurementContainer), true);
  const measurementController = picker.default(measurementContainer, { value: emptyShotState });
  flushFrames();
  const box = measurementContainer.querySelector("[data-hmb-video-picker-measurement-box]");
  assert.ok(box, "Cold mount keeps an inert height box in the host measurement copy.");
  assert.equal(box.style.height, "252px", "A first mount measures the compact one-Shot Loader row.");
  assert.equal(
    measurementContainer.querySelector(".hmbvp"),
    null,
    "The hidden measurement copy must never mount the live Picker dashboard.",
  );
  assert.equal(shell.style.height, "360px", "Cold measurement cannot resize the shared outer node.");
  assert.equal(shell.style.minHeight, "360px");
  assert.equal(shell.style.maxHeight, "360px");

  const repairedStateExpandable = expandableContract("_configure_picker_widget_parameter");
  const newStateExpandable = expandableContract("_add_picker_widget");
  const mayaTransportExpandable = expandableContract("_configure_hidden_maya_scene_parameter");
  const commandTransportExpandable = expandableContract("_configure_picker_command_parameter");
  assert.equal(repairedStateExpandable, true, "Saved Picker rows are repaired as expandable.");
  assert.equal(newStateExpandable, true, "New Picker rows are created as expandable.");
  assert.equal(mayaTransportExpandable, false, "The hidden MAYA transport cannot consume free height.");
  assert.equal(commandTransportExpandable, false, "The hidden COMMAND transport cannot consume free height.");

  const repairedFirstPass = adaptiveAllocatorFirstPass(252, repairedStateExpandable);
  const newFirstPass = adaptiveAllocatorFirstPass(252, newStateExpandable);
  assert.equal(
    repairedFirstPass.rowHeight,
    236,
    "A restored compact Picker receives the free row height on its initial 40px pass.",
  );
  assert.equal(repairedFirstPass.trailingSpacerHeight, 0);
  assert.deepEqual(newFirstPass, repairedFirstPass);

  const clippedRegression = adaptiveAllocatorFirstPass(252, false);
  assert.equal(clippedRegression.rowHeight, 40);
  assert.equal(
    clippedRegression.trailingSpacerHeight,
    196,
    "expandable=false reproduces the 40px row plus compact trailing-spacer failure.",
  );

  measurementController.update({ value: populatedThreeShotState });
  assert.equal(
    box.style.height,
    "624px",
    "A compact value update grows the measurement exactly with its Shot count.",
  );
  assert.equal(shell.style.height, "360px", "Reload measurement also leaves outer geometry host-owned.");

  const liveLayer = attach(shell, fakeElement("relative", documentStub));
  const liveContainer = attach(liveLayer, fakeElement("raw-widget live", documentStub));
  assert.equal(picker.hmbVideoPickerIsHostMeasurementClone(liveContainer), false);
  assert.equal(
    picker.hmbSyncVideoPickerHostMeasurement(liveContainer, populatedThreeShotState, true),
    1,
    "Expanded inline mode keeps the sibling measurement expanded.",
  );
  assert.equal(
    box.style.height,
    "1200px",
    "Expanded measurement must reserve the fixed 1400x1200 authoring floor.",
  );
  assert.equal(shell.style.height, "360px", "Expanded measurement cannot reposition or resize the shell.");
  assert.equal(
    picker.hmbSyncVideoPickerHostMeasurement(liveContainer, populatedThreeShotState, false),
    1,
    "Returning to compact mode reuses the dynamic compact measurement.",
  );
  const compactThreeShotHeight = picker.hmbVideoPickerCompactMeasurementHeight(populatedThreeShotState);
  assert.equal(compactThreeShotHeight, 624);
  assert.equal(box.style.height, `${compactThreeShotHeight}px`);
  assert.equal(shell.style.height, "360px");
  picker.hmbRememberVideoPickerViewMode(liveContainer, false);

  measurementController.cleanup();
  assert.equal(
    picker.hmbSyncVideoPickerHostMeasurement(liveContainer, emptyShotState, false),
    0,
    "A reload cleanup removes the stale measurement controller.",
  );

  const reloadLayer = attach(shell, fakeElement(
    "absolute left-0 right-0 pointer-events-none",
    documentStub,
  ));
  reloadLayer.style.visibility = "hidden";
  const reloadContainer = attach(reloadLayer, fakeElement("raw-widget reload", documentStub));
  let promotions = 0;
  let promotedValue = null;
  const reloadController = picker.hmbMountVideoPickerHostMeasurement(
    reloadContainer,
    { value: populatedThreeShotState },
    {
      promoteLive(nextProps) {
        promotions += 1;
        promotedValue = nextProps?.value;
      },
    },
  );
  flushFrames();
  assert.equal(promotions, 0, "A still-hidden reload copy cannot install live listeners.");
  assert.equal(
    reloadContainer.querySelector("[data-hmb-video-picker-measurement-box]")?.style?.height,
    `${compactThreeShotHeight}px`,
  );

  // Some Editor builds reuse contentRef instead of invoking the factory again.
  // The measurement controller must promote itself when the same row becomes
  // visible, otherwise it remains an inert blank box after reload.
  reloadLayer.style.visibility = "visible";
  observers.filter((observer) => !observer.disconnected).forEach((observer) => observer.flush());
  flushFrames();
  assert.equal(promotions, 1, "A reused contentRef promotes to the live Picker exactly once.");
  assert.equal(promotedValue, populatedThreeShotState);
  assert.equal(shell.style.height, "360px");
  reloadController.cleanup();
} finally {
  for (const [name, value] of Object.entries(savedGlobals)) {
    if (value === undefined) delete globalThis[name];
    else globalThis[name] = value;
  }
}

assert.doesNotMatch(
  source.slice(
    source.indexOf("export function hmbApplyVideoPickerCompactHostSizing"),
    source.indexOf("export function hmbInstallVideoPickerCompactHostSizing"),
  ),
  /hmbSetPickerStyleIfChanged\(shell,\s*"(?:height|min-height|max-height|top|left|transform)"/,
  "Compact fitting may request host measurement but cannot size or move the React Flow node.",
);

console.log("HMB VideoPicker adaptive allocator cold-mount regression: PASS");
