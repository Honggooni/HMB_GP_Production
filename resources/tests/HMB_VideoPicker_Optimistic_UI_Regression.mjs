import assert from "node:assert/strict";
import fs from "node:fs";


const widgetUrl = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetUrl, "utf8");

class FakeClassList {
  constructor(...names) { this.names = new Set(names); }
  add(...names) { names.forEach((name) => this.names.add(name)); }
  remove(...names) { names.forEach((name) => this.names.delete(name)); }
  contains(name) { return this.names.has(name); }
}

class FakeElement {
  constructor({ parent = null, classes = [] } = {}) {
    this.parentElement = parent;
    this.classList = new FakeClassList(...classes);
    this.listeners = new Map();
  }
  addEventListener(name, handler) {
    const handlers = this.listeners.get(name) || [];
    handlers.push(handler);
    this.listeners.set(name, handlers);
  }
  removeEventListener(name, handler) {
    const handlers = this.listeners.get(name) || [];
    this.listeners.set(name, handlers.filter((candidate) => candidate !== handler));
  }
  closest() { return this; }
}

const windowListeners = new Map();
globalThis.document = { activeElement: null, body: {}, documentElement: {} };
globalThis.window = {
  addEventListener(name, handler) { windowListeners.set(name, handler); },
  removeEventListener(name, handler) {
    if (windowListeners.get(name) === handler) windowListeners.delete(name);
  },
};

const widget = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);


// Interaction isolation must stay O(1) in listeners even when row/control
// count grows. React Flow classes remain per element, but event handlers are
// delegated once at the widget container.
const clip = new FakeElement({ classes: ["nopan", "nowheel"] });
const picker = new FakeElement({ classes: ["nodrag", "nopan", "nowheel"] });
const controls = Array.from({ length: 1000 }, () => new FakeElement());
const container = new FakeElement();
container.querySelector = (selector) => {
  if (selector === ".hmbvp-clip") return clip;
  if (selector === ".hmbvp") return picker;
  return null;
};
container.querySelectorAll = (selector) => (
  String(selector).includes(",") ? controls : []
);
container.contains = (element) => controls.includes(element);
const cleanup = [];
widget.hmbInstallPickerInteractionIsolation(container, cleanup);
assert.equal(cleanup.length, 1, "One cleanup owns all delegated interaction listeners.");
for (const control of controls) {
  assert.ok(control.classList.contains("nodrag"));
  assert.ok(control.classList.contains("nopan"));
  assert.ok(control.classList.contains("nowheel"));
  assert.equal(
    Array.from(control.listeners.values()).flat().length,
    0,
    "Rows and controls must not receive per-element listeners.",
  );
}
for (const eventName of ["pointerdown", "mousedown", "click", "dblclick", "keydown"]) {
  assert.equal(container.listeners.get(eventName)?.length, 1, `${eventName} is delegated once.`);
}
let delegatedStops = 0;
container.listeners.get("click")[0]({
  type: "click",
  target: controls[0],
  stopPropagation() { delegatedStops += 1; },
});
assert.equal(delegatedStops, 1, "A delegated control click stays inside the widget.");
container.listeners.get("click")[0]({
  type: "click",
  target: { closest() { return null; } },
  stopPropagation() { delegatedStops += 1; },
});
assert.equal(delegatedStops, 1, "Open panel background clicks still reach the canvas.");
container.listeners.get("pointerdown")[0]({
  type: "pointerdown",
  target: { closest() { return null; } },
  stopPropagation() { delegatedStops += 1; },
});
assert.equal(delegatedStops, 1, "Open panel pointerdown keeps canvas pan/select available.");
container.listeners.get("pointerdown")[0]({
  type: "pointerdown",
  target: controls[0],
  stopPropagation() { delegatedStops += 1; },
});
assert.equal(delegatedStops, 2, "Control pointerdown stays inside the widget.");
let deleteStops = 0;
container.listeners.get("keydown")[0]({
  key: "Delete",
  stopPropagation() { deleteStops += 1; },
});
assert.equal(deleteStops, 1, "Delete protection remains intact after delegation.");
cleanup[0]();
for (const eventName of ["pointerdown", "mousedown", "click", "dblclick", "keydown"]) {
  assert.equal(container.listeners.get(eventName)?.length || 0, 0);
}


// Static handler contracts complement the focused behavioral test: local DOM
// feedback happens before publication, while structurally incomplete patches
// retain the normal authoritative morph.
const mainStart = widgetSource.indexOf("export default function HMBVideoPickerLibraryWidget");
assert.ok(mainStart >= 0);
const main = widgetSource.slice(mainStart);
assert.match(main, /outlinerSearchPublishTimer/);
assert.match(main, /dueAtMs: Date\.now\(\) \+ 180/);
assert.match(main, /const pickerLocalInteractionLocked = \(candidateState = null\) =>/);
assert.match(main, /pickerLocalInteractionLocked[\s\S]*?__hmbPickerOperationSubmissionPending[\s\S]*?latestAvailability\.operationBusy/);
assert.match(main, /hmbRenderPickerOutlinerLocal\([\s\S]*?localState,[\s\S]*?pickerLocalInteractionLocked\(localState\)/);
assert.doesNotMatch(main, /hmbRenderPickerOutlinerLocal\([^;]*?\btr,\s*locked\s*\)/);
assert.match(main, /publishOutlinerSearchDraft[\s\S]*?suppressMatchingEcho: true/);
assert.match(main, /on\(outlinerScroll, "click"/);
assert.doesNotMatch(main, /on\(row, "click"/);
assert.match(main, /availability\.operationBusy \|\| container\.__hmbPickerOperationSubmissionPending/);
assert.match(main, /hmbSetPickerVisibilityBusy\(container, true\)/);
assert.match(main, /hmbApplyPickerCameraSelectionToDom\(container, next\);\s*schedulePickerStatePublicationAfterPaint\(next\);/);
assert.match(main, /hmbApplyPickerResolutionToDom\(container, selected\.width, selected\.height\);\s*commit\(next\);/);
assert.match(
  main,
  /hmbApplySelectedVideoAssetOrderToDom\(\s*container,\s*nextState,\s*liveTr,\s*pickerLocalInteractionLocked\(nextState\),?\s*\);[\s\S]*?schedulePickerStatePublicationAfterPaint\(/,
);
assert.match(main, /const snapshotUpdated = hmbApplySnapshotNavigationFeedback/);
assert.match(main, /commit\(next, \{ suppressMatchingEcho: snapshotUpdated \}\)/);
assert.match(widgetSource, /current\.__hmbPendingPickerVideoSource = desiredSource/);
assert.match(
  main,
  /hmbStagePickerViewportVideoSource\([\s\S]*?\(\) => completeRequestedPreviewSwitch\(requestedUid, requestedUrl, requestToken\),[\s\S]*?\(\) => failRequestedPreviewSwitch\(requestedUid, requestToken\),[\s\S]*?requestToken/,
);
assert.match(widgetSource, /HMB_PICKER_VIDEO_PRELOAD_TIMEOUT_MS = 15000/);
assert.match(widgetSource, /id="picker-preview-load-status"[\s\S]*?role="alert"[\s\S]*?id="retry-picker-preview-load"/);
assert.match(main, /completeRequestedPreviewSwitch[\s\S]*?hmbClearPickerPreviewLoadFailure\(container\)/);
assert.match(main, /failRequestedPreviewSwitch[\s\S]*?hmbShowPickerPreviewLoadFailure\(container, tr\.previewLoadFailed\)/);


class FakeMediaElement {
  constructor(attributes = {}) {
    this._attributes = new Map(Object.entries(attributes));
    this.listeners = new Map();
    this.loadCount = 0;
    this.pauseCount = 0;
  }
  get attributes() {
    return Array.from(this._attributes, ([name, value]) => ({ name, value }));
  }
  getAttribute(name) { return this._attributes.get(name) ?? null; }
  setAttribute(name, value) { this._attributes.set(name, String(value)); }
  removeAttribute(name) { this._attributes.delete(name); }
  get src() { return this.getAttribute("src") || ""; }
  set src(value) { this.setAttribute("src", value); }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  removeEventListener(name, handler) {
    if (this.listeners.get(name) === handler) this.listeners.delete(name);
  }
  fire(name) { this.listeners.get(name)?.(); }
  load() { this.loadCount += 1; }
  pause() { this.pauseCount += 1; }
}

const previewFailureMessage = { textContent: "" };
const previewRetryButton = { disabled: true };
const previewFailureStatus = new FakeMediaElement({ hidden: "" });
previewFailureStatus.hidden = true;
previewFailureStatus.querySelector = (selector) => {
  if (selector === "[data-preview-load-message]") return previewFailureMessage;
  if (selector === "#retry-picker-preview-load") return previewRetryButton;
  return null;
};
const previewFailureContainer = {
  querySelector(selector) {
    return selector === "#picker-preview-load-status" ? previewFailureStatus : null;
  },
};
assert.equal(
  widget.hmbShowPickerPreviewLoadFailure(previewFailureContainer, "Previous preview retained; retry available."),
  true,
);
assert.equal(previewFailureStatus.hidden, false);
assert.equal(previewFailureStatus.getAttribute("role"), "alert");
assert.equal(previewFailureStatus.getAttribute("aria-live"), "assertive");
assert.equal(previewFailureStatus.getAttribute("data-preview-load-failed"), "true");
assert.match(previewFailureMessage.textContent, /Previous preview retained/);
assert.equal(previewRetryButton.disabled, false);
assert.equal(widget.hmbClearPickerPreviewLoadFailure(previewFailureContainer), true);
assert.equal(previewFailureStatus.hidden, true);
assert.equal(previewFailureStatus.getAttribute("hidden"), "");
assert.equal(previewFailureMessage.textContent, "");

// Rapid A -> B -> A selection cancels the deferred B source instead of
// allowing its probe to switch the retained preview after A was reselected.
const retainedMedia = new FakeMediaElement({ id: "picker-video", src: "file:///A.mp4" });
const desiredB = new FakeMediaElement({ id: "picker-video", src: "file:///B.mp4" });
const desiredA = new FakeMediaElement({ id: "picker-video", src: "file:///A.mp4" });
widget.hmbSyncPickerElementAttributes(retainedMedia, desiredB);
assert.equal(retainedMedia.getAttribute("src"), "file:///A.mp4");
assert.equal(retainedMedia.__hmbPendingPickerVideoSource, "file:///B.mp4");
widget.hmbSyncPickerElementAttributes(retainedMedia, desiredA);
assert.equal(retainedMedia.__hmbPendingPickerVideoSource, undefined);

const probes = [];
retainedMedia.ownerDocument = {
  createElement() {
    const probe = new FakeMediaElement();
    probes.push(probe);
    return probe;
  },
};
retainedMedia.__hmbPendingPickerVideoSource = "file:///B.mp4";
const successfulProbeCleanup = [];
let previewReady = 0;
assert.equal(
  widget.hmbStagePickerViewportVideoSource(
    retainedMedia,
    successfulProbeCleanup,
    () => { previewReady += 1; },
  ),
  true,
);
probes.at(-1).fire("loadeddata");
assert.equal(retainedMedia.getAttribute("src"), "file:///B.mp4");
assert.equal(retainedMedia.__hmbPendingPickerVideoSource, undefined);
assert.equal(previewReady, 1);
assert.ok(probes.at(-1).loadCount >= 1, "Successful preload releases the probe source.");
successfulProbeCleanup[0]();

// A stale B disposer must release only its own probe. If a newer C/D request
// owns the expando, cleanup cannot erase or apply that newer source.
retainedMedia.__hmbPendingPickerVideoSource = "file:///C.mp4";
const staleProbeCleanup = [];
assert.equal(widget.hmbStagePickerViewportVideoSource(retainedMedia, staleProbeCleanup), true);
const staleProbe = probes.at(-1);
retainedMedia.__hmbPendingPickerVideoSource = "file:///D.mp4";
staleProbeCleanup[0]();
assert.equal(retainedMedia.__hmbPendingPickerVideoSource, "file:///D.mp4");
assert.ok(staleProbe.loadCount >= 1, "Disposed preload releases its media resource.");

// Retrying the same desired URL receives a new owner token. Disposing the old
// attempt cannot clear or apply the retry merely because both URLs match.
const retryOwnedMedia = new FakeMediaElement({ src: "file:///A.mp4" });
retryOwnedMedia.ownerDocument = retainedMedia.ownerDocument;
retryOwnedMedia.__hmbPendingPickerVideoSource = "file:///B.mp4";
const firstSameSourceCleanup = [];
assert.equal(widget.hmbStagePickerViewportVideoSource(retryOwnedMedia, firstSameSourceCleanup), true);
retryOwnedMedia.__hmbPendingPickerVideoSource = "file:///B.mp4";
delete retryOwnedMedia.__hmbPendingPickerVideoOwner;
const retrySameSourceCleanup = [];
assert.equal(widget.hmbStagePickerViewportVideoSource(retryOwnedMedia, retrySameSourceCleanup), true);
firstSameSourceCleanup[0]();
assert.equal(retryOwnedMedia.__hmbPendingPickerVideoSource, "file:///B.mp4");
probes.at(-1).fire("canplay");
assert.equal(retryOwnedMedia.getAttribute("src"), "file:///B.mp4");
assert.equal(retryOwnedMedia.__hmbPendingPickerVideoSource, undefined);
retrySameSourceCleanup[0]();

// Probe failure retains the last verified frame. Only the owned pending source
// is cleared, and failure settles the requesting UI without applying C.
retainedMedia.__hmbPendingPickerVideoSource = "file:///C.mp4";
const failedProbeCleanup = [];
let previewFailures = 0;
assert.equal(
  widget.hmbStagePickerViewportVideoSource(
    retainedMedia,
    failedProbeCleanup,
    () => { previewReady += 1; },
    () => { previewFailures += 1; },
  ),
  true,
);
const failedProbe = probes.at(-1);
failedProbe.fire("error");
assert.equal(retainedMedia.getAttribute("src"), "file:///B.mp4");
assert.equal(retainedMedia.__hmbPendingPickerVideoSource, undefined);
assert.equal(previewReady, 1);
assert.equal(previewFailures, 1);
assert.ok(failedProbe.loadCount >= 1, "Failed preload releases its media resource.");
failedProbeCleanup[0]();

// A slow replacement follows the same retain-current policy when its probe
// reaches the bounded timeout without loadeddata/canplay.
const originalSetTimeout = globalThis.setTimeout;
const originalClearTimeout = globalThis.clearTimeout;
let capturedProbeTimeout = null;
let capturedProbeDelay = null;
globalThis.setTimeout = (callback, delay) => {
  capturedProbeTimeout = callback;
  capturedProbeDelay = delay;
  return 9191;
};
globalThis.clearTimeout = () => {};
try {
  retainedMedia.__hmbPendingPickerVideoSource = "file:///D.mp4";
  const timedOutProbeCleanup = [];
  assert.equal(
    widget.hmbStagePickerViewportVideoSource(
      retainedMedia,
      timedOutProbeCleanup,
      () => { previewReady += 1; },
      () => { previewFailures += 1; },
    ),
    true,
  );
  const timedOutProbe = probes.at(-1);
  assert.equal(typeof capturedProbeTimeout, "function");
  assert.equal(capturedProbeDelay, 15000);
  capturedProbeTimeout();
  assert.equal(retainedMedia.getAttribute("src"), "file:///B.mp4");
  assert.equal(retainedMedia.__hmbPendingPickerVideoSource, undefined);
  assert.equal(previewReady, 1);
  assert.equal(previewFailures, 2);
  assert.ok(timedOutProbe.loadCount >= 1, "Timed-out preload releases its media resource.");
  timedOutProbeCleanup[0]();
} finally {
  globalThis.setTimeout = originalSetTimeout;
  globalThis.clearTimeout = originalClearTimeout;
}

// Browsers normally provide a video probe. If a host cannot create one, the
// request is rejected safely instead of replacing the verified source blind.
const noProbeMedia = new FakeMediaElement({ src: "file:///A.mp4" });
noProbeMedia.ownerDocument = { createElement() { return null; } };
noProbeMedia.__hmbPendingPickerVideoSource = "file:///broken.mp4";
let noProbeFailures = 0;
assert.equal(
  widget.hmbStagePickerViewportVideoSource(
    noProbeMedia,
    [],
    () => { previewReady += 1; },
    () => { noProbeFailures += 1; },
  ),
  true,
);
assert.equal(noProbeMedia.getAttribute("src"), "file:///A.mp4");
assert.equal(noProbeMedia.__hmbPendingPickerVideoSource, undefined);
assert.equal(noProbeFailures, 1);

// Transport rollback is revision-owned: an older rejected publication can
// restore its predecessor, but cannot erase a newer local commit.
const priorPublication = {
  runtime_instance_id: "runtime-a",
  state_revision: 7,
  state_published_at_ms: 700,
  state_writer: "widget",
  selected_camera: "|oldCam",
};
const failedPublication = {
  ...priorPublication,
  state_revision: 8,
  state_published_at_ms: 800,
  selected_camera: "|failedCam",
};
const publicationContainer = {
  __hmbPendingPickerState: { ...failedPublication },
  __hmbAuthoritativePickerState: { ...failedPublication },
};
assert.equal(widget.hmbPendingPickerStateOwnedBy(publicationContainer, failedPublication), true);
assert.equal(
  widget.hmbRollbackFailedPickerStatePublication(
    publicationContainer,
    failedPublication,
    priorPublication,
    priorPublication,
  ),
  true,
);
assert.equal(publicationContainer.__hmbPendingPickerState.state_revision, 7);
assert.equal(publicationContainer.__hmbAuthoritativePickerState.state_revision, 7);

const newerPublication = {
  ...failedPublication,
  state_revision: 9,
  state_published_at_ms: 900,
  selected_camera: "|newCam",
};
publicationContainer.__hmbPendingPickerState = { ...newerPublication };
publicationContainer.__hmbAuthoritativePickerState = { ...newerPublication };
assert.equal(widget.hmbPendingPickerStateOwnedBy(publicationContainer, failedPublication), false);
assert.equal(
  widget.hmbRollbackFailedPickerStatePublication(
    publicationContainer,
    failedPublication,
    priorPublication,
    priorPublication,
  ),
  false,
);
assert.equal(publicationContainer.__hmbPendingPickerState.state_revision, 9);
assert.equal(publicationContainer.__hmbAuthoritativePickerState.state_revision, 9);

const commitBlock = main.slice(
  main.indexOf("const commit ="),
  main.indexOf("const currentWidgetState ="),
);
assert.match(commitBlock, /const rollbackFailedCommit = \(\) =>/);
assert.equal(
  (commitBlock.match(/rollbackFailedCommit\(\)/g) || []).length,
  2,
  "Both synchronous throws and asynchronous rejections use exact-owned rollback.",
);
assert.doesNotMatch(commitBlock, /catch \(error\) => \{\s*hmbClearPendingPickerStateEcho/);

const dispatchBlock = main.slice(
  main.indexOf("const dispatchCommand ="),
  main.indexOf("const scheduleReadAckTimeout ="),
);
assert.ok(
  dispatchBlock.indexOf("reserveVisibilityOperationGuard(resolvedActionId)")
    < dispatchBlock.indexOf("bridge.dispatch(command)"),
  "Operation visibility is reserved before a synchronous bridge can ack/remount.",
);
assert.match(dispatchBlock, /catch \(error\) \{\s*if \(reserveVisibility\) releaseVisibilityOperationGuard\(resolvedActionId\)/);
assert.equal((main.match(/\{ reserveVisibility: true \}/g) || []).length, 2);
assert.doesNotMatch(main, /guardVisibilityDuringOperationSubmission/);


// CSS scoping is deterministic and cached independently from dynamic markup.
const rawMarkup = "<style>.child{color:red}@media (min-width:1px){.nested{display:block}}</style><div class='child'></div>";
const scopedOnce = widget.hmbScopeWidgetStyleMarkup(rawMarkup, ".picker-root");
const scopedTwice = widget.hmbScopeWidgetStyleMarkup(rawMarkup, ".picker-root");
assert.equal(scopedTwice, scopedOnce);
assert.match(scopedOnce, /\.picker-root \.child\{color:red\}/);
assert.match(scopedOnce, /@media \(min-width:1px\)\{\.picker-root \.nested\{display:block\}\}/);
assert.match(widgetSource, /const HMB_SCOPED_STYLE_CACHE_LIMIT = 8/);
assert.match(widgetSource, /HMB_SCOPED_STYLE_CACHE\.has\(key\)/);


// Native MAYA_SCENE discovery is cached within a render burst and event
// scheduling is coalesced to one immediate and one settled scan.
assert.match(widgetSource, /const HMB_NATIVE_PICKER_CACHE_TTL_MS = 350/);
assert.match(widgetSource, /__hmbNativeMayaPickerCache/);
assert.match(main, /for \(const delay of \[0, 500\]\)/);
assert.match(main, /if \(event\?\.target && container\.contains\?\.\(event\.target\)\) return/);


console.log(
  "HMB VideoPicker optimistic UI regression: PASS "
  +
  "(delegation, local feedback, safe morphs, preview staging, cached CSS/native discovery)"
);
