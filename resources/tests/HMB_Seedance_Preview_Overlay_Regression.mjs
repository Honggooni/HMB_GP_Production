import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL("../../widgets/HMBSeedanceGenerationWidget.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);

const generation = (phase, overrides = {}) => ({
  schema: "hmb-seedance-generation-preview",
  version: 1,
  phase,
  job_id: "broker-job-existing-1",
  started_at_ms: 10_000,
  elapsed_seconds: 151,
  guidance: "",
  action: "none",
  has_existing_video: false,
  media_revision: 0,
  ...overrides,
});

assert.equal(typeof widget.hmbSeedanceGenerationPreview, "function");
assert.equal(typeof widget.hmbSeedancePreviewPresentation, "function");
assert.equal(typeof widget.hmbSeedancePreviewMutationIsRelevant, "function");
assert.equal(
  widget.HMB_SEEDANCE_PREVIEW_ACTION_WATCHDOG_MS,
  10_000,
  "The overlay transport watchdog must release an unacknowledged request after ten seconds.",
);

assert.deepEqual(widget.hmbSeedanceGenerationPreview({ schema: "foreign", version: 99 }), {
  schema: "hmb-seedance-generation-preview",
  version: 1,
  phase: "idle",
  job_id: "",
  started_at_ms: 0,
  elapsed_seconds: 0,
  guidance: "",
  action: "none",
  has_existing_video: false,
  media_revision: 0,
});

for (const [phase, expectedTitle] of Object.entries({
  preparing: "준비 중…",
  submitting: "작업 제출 중…",
  queued: "렌더 대기 중…",
  running: "렌더 중…",
  retrieving: "기존 작업 결과 확인 중…",
  downloading: "완료된 영상 다운로드 중…",
  verifying: "영상 검증 중…",
  cancelled_locally: "로컬 조회가 중단되었습니다",
  timed_out: "자동 조회 시간이 초과되었습니다",
  submission_unknown: "제출 결과 확인이 필요합니다",
  failed: "영상 생성에 실패했습니다",
})) {
  const presentation = widget.hmbSeedancePreviewPresentation(generation(phase));
  assert.equal(presentation.visible, true, `${phase} must remain visible in the native preview.`);
  assert.equal(presentation.mode, "center", `${phase} must use the empty-preview centre.`);
  assert.equal(presentation.title, expectedTitle);
}

assert.equal(
  widget.hmbSeedancePreviewPresentation(generation("running")).elapsed,
  "02:31",
  "Running status must expose a stable elapsed-time label.",
);
assert.equal(
  widget.hmbSeedancePreviewPresentation(generation("queued")).busy,
  true,
  "Queued work is active and must not resemble an empty black preview.",
);
assert.equal(
  widget.hmbSeedancePreviewPresentation(generation("running", {
    has_existing_video: true,
  }), { visibleVideo: true }).mode,
  "badge",
  "A new render must retain the previous playable frame and use only a badge.",
);

const awaitingCanPlay = widget.hmbSeedancePreviewPresentation(generation("succeeded"), {
  playableVideo: false,
  visibleVideo: true,
});
assert.equal(awaitingCanPlay.visible, true);
assert.equal(awaitingCanPlay.title, "완료 영상을 준비 중…");
assert.equal(
  widget.hmbSeedancePreviewPresentation(generation("succeeded"), {
    playableVideo: true,
    visibleVideo: true,
  }).visible,
  false,
  "The completed overlay may disappear only after the video is actually playable.",
);
const unsupportedMovPreview = widget.hmbSeedancePreviewPresentation(
  generation("succeeded"),
  {
    playableVideo: false,
    visibleVideo: true,
    previewError: true,
    mediaFormat: "mov",
  },
);
assert.equal(unsupportedMovPreview.visible, true);
assert.equal(unsupportedMovPreview.busy, false);
assert.equal(unsupportedMovPreview.tone, "warning");
assert.equal(unsupportedMovPreview.title, "MOV 저장 완료 · 내장 미리보기 불가");
assert.equal(
  unsupportedMovPreview.detail,
  "파일은 정상 저장되었습니다. 외부 플레이어에서 MOV 파일을 여세요.",
);

for (const phase of ["cancelled_locally", "timed_out", "submission_unknown"]) {
  const presentation = widget.hmbSeedancePreviewPresentation(generation(phase, {
    action: "refresh_existing",
  }));
  assert.equal(presentation.action, "refresh_existing");
  assert.equal(presentation.tone, "warning");
}

assert.match(widgetSource, /\[data-parameter-name=['"]video_url['"]\]/);
assert.match(widgetSource, /\[data-vp-video-area\]/);
assert.equal(
  (widgetSource.match(/generation_refresh/g) || []).length,
  0,
  "Preview retrieval must never find or click React's native ParameterButton.",
);
assert.equal(
  (widgetSource.match(/return\s+latestProps\.onChange\s*\(\s*\{/g) || []).length,
  1,
  "The hidden command bridge must own exactly one action-only onChange call site.",
);
assert.doesNotMatch(
  widgetSource,
  /refreshButton\.disabled\s*=/,
  "The overlay must never mutate React-owned native ParameterButton state.",
);
assert.doesNotMatch(
  widgetSource,
  /\b(?:fetch|XMLHttpRequest|WebSocket)\s*\(/,
  "The widget must never contact the Broker or submit/retrieve a task itself.",
);

class FakeStyle {
  constructor() { this.values = new Map(); }
  setProperty(name, value) { this.values.set(String(name), String(value)); }
  getPropertyValue(name) { return this.values.get(String(name)) || ""; }
  removeProperty(name) { this.values.delete(String(name)); }
}

class FakeClassList {
  constructor(element) { this.element = element; }
  values() { return new Set(String(this.element.className || "").split(/\s+/).filter(Boolean)); }
  contains(name) { return this.values().has(String(name)); }
  add(...names) {
    const values = this.values();
    names.forEach((name) => values.add(String(name)));
    this.element.className = [...values].join(" ");
  }
  remove(...names) {
    const values = this.values();
    names.forEach((name) => values.delete(String(name)));
    this.element.className = [...values].join(" ");
  }
}

function attributeDatasetKey(name) {
  return String(name).slice(5).replace(/-([a-z])/g, (_all, letter) => letter.toUpperCase());
}

function matchesSelector(element, selector) {
  const candidate = String(selector || "").trim();
  if (!candidate) return false;
  if (candidate.startsWith(".")) return element.classList.contains(candidate.slice(1));
  const attributeMatch = candidate.match(/^([a-z0-9-]+)?\[([^=\]]+)(?:=["']([^"']*)["'])?\]$/i);
  if (attributeMatch) {
    const [, tagName, name, expected] = attributeMatch;
    if (tagName && element.tagName !== tagName.toUpperCase()) return false;
    if (!element.hasAttribute(name)) return false;
    return expected === undefined || element.getAttribute(name) === expected;
  }
  return element.tagName === candidate.toUpperCase();
}

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = String(tagName).toUpperCase();
    this.ownerDocument = ownerDocument;
    this.parentElement = null;
    this.children = [];
    this.attributes = new Map();
    this.dataset = {};
    this.style = new FakeStyle();
    this.className = "";
    this.classList = new FakeClassList(this);
    this.listeners = new Map();
    this.textContent = "";
    this.disabled = false;
    this.readyState = 0;
    this.src = "";
    this.currentSrc = "";
    this.loadCount = 0;
  }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  appendChild(child) {
    if (child.parentElement) child.remove();
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  contains(target) {
    if (target === this) return true;
    return this.children.some((child) => child.contains(target));
  }
  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
    if (name === "class") this.className = String(value);
    if (String(name).startsWith("data-")) {
      this.dataset[attributeDatasetKey(name)] = String(value);
    }
  }
  getAttribute(name) { return this.attributes.get(String(name)) || ""; }
  hasAttribute(name) { return this.attributes.has(String(name)); }
  removeAttribute(name) {
    this.attributes.delete(String(name));
    if (String(name).startsWith("data-")) delete this.dataset[attributeDatasetKey(name)];
  }
  querySelector(selector) {
    for (const child of this.children) {
      if (matchesSelector(child, selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if (matchesSelector(child, selector)) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }
  removeEventListener(type, listener) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter((item) => item !== listener));
  }
  fire(type) {
    const event = {
      type,
      target: this,
      preventDefault() {},
      stopPropagation() {},
    };
    for (const listener of [...(this.listeners.get(type) || [])]) listener(event);
  }
  click() { this.fire("click"); }
  load() {
    this.loadCount += 1;
    this.readyState = 0;
  }
  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
    this.parentElement = null;
  }
}

const fakeDocument = {
  createElement(tagName) { return new FakeElement(tagName, fakeDocument); },
};
const element = (tagName, className = "", attributes = {}) => {
  const value = fakeDocument.createElement(tagName);
  value.className = className;
  for (const [name, content] of Object.entries(attributes)) value.setAttribute(name, content);
  return value;
};

function previewFixture() {
  const nodeRoot = element("div", "react-flow__node");
  const widgetParent = element("div");
  const container = element("div", "seedance-widget");
  const parameter = element("div", "video_url", { "data-parameter-name": "video_url" });
  const region = element("div", "relative bg-black overflow-hidden", {
    "data-vp-video-area": "true",
  });
  const commandParameter = element("div", "HMB_SEEDANCE_REFRESH_COMMAND", {
    "data-parameter-name": "HMB_SEEDANCE_REFRESH_COMMAND",
  });
  const commandContainer = element("div", "seedance-command-widget");
  widgetParent.append(container);
  parameter.append(region);
  commandParameter.append(commandContainer);
  nodeRoot.append(widgetParent, parameter, commandParameter);
  return {
    nodeRoot,
    container,
    parameter,
    region,
    commandContainer,
  };
}

function installCommandBridge(current, onChange) {
  return widget.default(current.commandContainer, {
    value: {
      schema: "hmb-seedance-refresh-command",
      version: 1,
      action: "none",
      action_id: "",
      issued_at_ms: 0,
    },
    onChange,
  });
}

function assertRefreshCommand(value) {
  assert.equal(value?.schema, "hmb-seedance-refresh-command");
  assert.equal(value?.version, 1);
  assert.equal(value?.action, "refresh_existing");
  assert.match(String(value?.action_id || ""), /^refresh-/);
  assert.ok(Number.isSafeInteger(value?.issued_at_ms) && value.issued_at_ms > 0);
  assert.equal("job_id" in value, false, "The browser must not nominate a Broker task ID.");
  assert.deepEqual(
    Object.keys(value).sort(),
    ["action", "action_id", "issued_at_ms", "schema", "version"],
    "The command transport must not echo Shot/catalog/generation state.",
  );
}

const mutationFixture = previewFixture();
const nodeResizer = element("div", "react-flow__node-resizer");
assert.equal(
  widget.hmbSeedancePreviewMutationIsRelevant({
    type: "childList",
    target: mutationFixture.nodeRoot,
    addedNodes: [nodeResizer],
    removedNodes: [],
  }),
  false,
  "React Flow resizer mutations must not trigger a preview rescan.",
);
assert.equal(
  widget.hmbSeedancePreviewMutationIsRelevant({
    type: "attributes",
    attributeName: "class",
    target: mutationFixture.nodeRoot,
    addedNodes: [],
    removedNodes: [],
  }),
  false,
  "Whole-node selection/class mutations must not trigger a preview rescan.",
);
const mutationOverlay = element("div", "hmb-seedance-preview-overlay");
mutationFixture.region.append(mutationOverlay);
assert.equal(
  widget.hmbSeedancePreviewMutationIsRelevant({
    type: "childList",
    target: mutationFixture.region,
    addedNodes: [mutationOverlay],
    removedNodes: [],
  }),
  false,
  "Mounting the overlay inside the preview region must not rescan itself.",
);
assert.equal(
  widget.hmbSeedancePreviewMutationIsRelevant({
    type: "childList",
    target: mutationOverlay,
    addedNodes: [element("span")],
    removedNodes: [],
  }),
  false,
  "The overlay's own DOM writes must not recursively schedule itself.",
);
assert.equal(
  widget.hmbSeedancePreviewMutationIsRelevant({
    type: "attributes",
    attributeName: "data-raw-video-value",
    target: mutationFixture.parameter,
    addedNodes: [],
    removedNodes: [],
  }),
  true,
  "A video_url parameter mutation must resynchronize the preview.",
);
const mutationVideo = element("video");
mutationFixture.region.append(mutationVideo);
assert.equal(
  widget.hmbSeedancePreviewMutationIsRelevant({
    type: "attributes",
    attributeName: "src",
    target: mutationVideo,
    addedNodes: [],
    removedNodes: [],
  }),
  true,
  "A native video source mutation must resynchronize the preview.",
);

const fixture = previewFixture();
assert.equal(widget.hmbSeedanceFindPreviewRegion(fixture.container), fixture.region);
assert.equal(
  widget.hmbSeedanceSyncPreviewOverlay(
    fixture.container,
    { generation: generation("running") },
  ),
  true,
);
let overlay = fixture.region.querySelector(".hmb-seedance-preview-overlay");
assert.ok(overlay, "An empty native ParameterVideo area must receive a status overlay.");
assert.equal(overlay.dataset.phase, "running");
assert.equal(overlay.dataset.mode, "center");
assert.match(
  overlay.querySelector(".hmb-seedance-preview-overlay__title").textContent,
  /렌더 중/,
);

const retainedVideo = element("video");
retainedVideo.src = "http://127.0.0.1:8124/external/old-success.mp4";
retainedVideo.currentSrc = retainedVideo.src;
retainedVideo.readyState = 4;
fixture.region.append(retainedVideo);
widget.hmbSeedanceSyncPreviewOverlay(fixture.container, {
  generation: generation("queued", { has_existing_video: true }),
});
overlay = fixture.region.querySelector(".hmb-seedance-preview-overlay");
assert.ok(overlay, "Queued replacement work must not remove its status from a retained video.");
assert.equal(overlay.dataset.mode, "badge");
assert.equal(retainedVideo.src.includes("old-success.mp4"), true);

// A succeeded backend state can arrive before React swaps the old native video
// source. The old readyState=4 must not satisfy the new media revision.
const completedGeneration = generation("succeeded", {
  has_existing_video: true,
  media_revision: 1,
});
widget.hmbSeedanceSyncPreviewOverlay(fixture.container, {
  generation: completedGeneration,
});
assert.ok(
  fixture.region.querySelector(".hmb-seedance-preview-overlay"),
  "The previous playable video cannot clear a newly completed media revision.",
);

retainedVideo.src = "http://127.0.0.1:8124/external/new-success.mp4";
retainedVideo.currentSrc = retainedVideo.src;
retainedVideo.readyState = 0;
fixture.container.__hmbSeedanceLatestProps = {
  value: {
    schema: "hmb-seedance-shot-ui",
    schema_version: 2,
    shot_catalog: {},
    shot: {},
    generation: completedGeneration,
  },
};
widget.hmbSeedanceSyncPreviewOverlay(fixture.container, {
  generation: completedGeneration,
});
assert.ok(
  fixture.region.querySelector(".hmb-seedance-preview-overlay"),
  "A new source must retain the completion overlay until canplay.",
);
retainedVideo.readyState = 3;
retainedVideo.fire("canplay");
await Promise.resolve();
await Promise.resolve();
assert.equal(
  fixture.region.querySelector(".hmb-seedance-preview-overlay"),
  null,
  "The overlay must disappear after the new media identity fires canplay.",
);

// CREATE_NEW is not the only output policy. OVERWRITE can publish a new file
// at exactly the same local URL, so media_revision must force one native reload
// and wait for that reload's canplay rather than trusting the prior frame.
const sameSourceFixture = previewFixture();
const sameSourceVideo = element("video");
sameSourceVideo.src = "http://127.0.0.1:8124/external/overwritten-result.mp4";
sameSourceVideo.currentSrc = sameSourceVideo.src;
sameSourceVideo.readyState = 4;
sameSourceFixture.region.append(sameSourceVideo);
widget.hmbSeedanceSyncPreviewOverlay(sameSourceFixture.container, {
  generation: generation("running", {
    has_existing_video: true,
    media_revision: 4,
  }),
});
const sameSourceCompleted = generation("succeeded", {
  has_existing_video: true,
  media_revision: 5,
});
sameSourceFixture.container.__hmbSeedanceLatestProps = {
  value: {
    schema: "hmb-seedance-shot-ui",
    schema_version: 2,
    shot_catalog: {},
    shot: {},
    generation: sameSourceCompleted,
  },
};
widget.hmbSeedanceSyncPreviewOverlay(sameSourceFixture.container, {
  generation: sameSourceCompleted,
});
assert.equal(sameSourceVideo.loadCount, 1, "A same-URL new revision must reload exactly once.");
assert.ok(sameSourceFixture.region.querySelector(".hmb-seedance-preview-overlay"));
widget.hmbSeedanceSyncPreviewOverlay(sameSourceFixture.container, {
  generation: sameSourceCompleted,
});
assert.equal(sameSourceVideo.loadCount, 1, "Repeated state echoes must not restart the same reload.");
sameSourceVideo.readyState = 3;
sameSourceVideo.fire("canplay");
await Promise.resolve();
await Promise.resolve();
assert.equal(
  sameSourceFixture.region.querySelector(".hmb-seedance-preview-overlay"),
  null,
  "The same-URL revision may clear only after its own canplay event.",
);
widget.hmbSeedanceCleanupPreviewOverlay(sameSourceFixture.container);

// ParameterVideo is type-compatible with MOV, but the embedded Chromium codec
// set may reject a real provider MOV/10-bit HEVC stream on some team PCs. The
// saved result must not look like an endless render in that case, and no local
// or signed URL may be copied into visible overlay text.
const movFallbackFixture = previewFixture();
const movFallbackVideo = element("video");
movFallbackVideo.src = (
  "http://127.0.0.1:8124/external/seedance-result.mov"
  + "?token=must-not-enter-overlay"
);
movFallbackVideo.currentSrc = movFallbackVideo.src;
movFallbackVideo.readyState = 0;
movFallbackFixture.region.append(movFallbackVideo);
const movCompleted = generation("succeeded", {
  has_existing_video: true,
  media_revision: 8,
});
movFallbackFixture.container.__hmbSeedanceLatestProps = {
  value: {
    schema: "hmb-seedance-shot-ui",
    schema_version: 2,
    shot_catalog: {},
    shot: {},
    generation: movCompleted,
  },
};
widget.hmbSeedanceSyncPreviewOverlay(movFallbackFixture.container, {
  generation: movCompleted,
});
assert.ok(movFallbackFixture.region.querySelector(".hmb-seedance-preview-overlay"));
movFallbackVideo.error = { code: 4 };
movFallbackVideo.fire("error");
await Promise.resolve();
await Promise.resolve();
const movFallbackOverlay = movFallbackFixture.region.querySelector(
  ".hmb-seedance-preview-overlay",
);
assert.ok(movFallbackOverlay, "A native MOV codec error must retain an actionable overlay.");
assert.equal(movFallbackOverlay.dataset.tone, "warning");
assert.equal(movFallbackOverlay.dataset.busy, "false");
assert.equal(
  movFallbackOverlay.querySelector(".hmb-seedance-preview-overlay__title").textContent,
  "MOV 저장 완료 · 내장 미리보기 불가",
);
const movFallbackVisibleText = [
  movFallbackOverlay.querySelector(".hmb-seedance-preview-overlay__title").textContent,
  movFallbackOverlay.querySelector(".hmb-seedance-preview-overlay__detail").textContent,
].join(" ");
assert.doesNotMatch(movFallbackVisibleText, /127\.0\.0\.1|token=|seedance-result/i);

// A late codec installation/source replacement can still make the same MOV
// playable. Its own canplay event should then clear the fallback normally.
movFallbackVideo.error = null;
movFallbackVideo.readyState = 3;
movFallbackVideo.fire("canplay");
await Promise.resolve();
await Promise.resolve();
assert.equal(
  movFallbackFixture.region.querySelector(".hmb-seedance-preview-overlay"),
  null,
);
widget.hmbSeedanceCleanupPreviewOverlay(movFallbackFixture.container);

const refreshRequests = [];
let insideRefreshClickStack = true;
const refreshGeneration = generation("cancelled_locally", {
  action: "refresh_existing",
  has_existing_video: true,
  media_revision: 1,
});
const fixtureCommandBridge = installCommandBridge(fixture, (value) => {
  assert.equal(
    insideRefreshClickStack,
    false,
    "The action-only refresh dispatch must be deferred beyond the overlay click stack.",
  );
  refreshRequests.push(value);
});
fixture.container.__hmbSeedanceLatestProps = {
  value: {
    schema: "hmb-seedance-shot-ui",
    schema_version: 2,
    shot_catalog: {},
    shot: {},
    generation: refreshGeneration,
  },
  onChange() {
    assert.fail("Refresh must not republish the durable Shot/catalog parameter.");
  },
};
widget.hmbSeedanceSyncPreviewOverlay(fixture.container, {
  generation: refreshGeneration,
});
overlay = fixture.region.querySelector(".hmb-seedance-preview-overlay");
const refreshButton = overlay.querySelector("[data-hmb-seedance-preview-action]");
assert.equal(refreshButton.style.getPropertyValue("display"), "");
refreshButton.fire("click");
refreshButton.fire("click");
assert.equal(
  refreshRequests.length,
  0,
  "The click handler must return before entering Griptape's value-set transaction.",
);
insideRefreshClickStack = false;
await Promise.resolve();
assert.equal(refreshButton.disabled, true);
assert.equal(refreshButton.textContent, "기존 작업 확인 중…");
assert.equal(overlay.getAttribute("aria-busy"), "true");
assert.equal(
  overlay.querySelector(".hmb-seedance-preview-overlay__title").textContent,
  "기존 작업 결과 확인 중…",
  "The pending state must be visible before Griptape receives the action.",
);
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(refreshRequests.length, 1, "One UI pulse must produce at most one backend refresh request.");
assertRefreshCommand(refreshRequests[0]);
refreshButton.fire("click");
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(
  refreshRequests.length,
  1,
  "An unresolved backend publication must keep duplicate clicks idempotent.",
);

assert.equal(widget.hmbSeedanceCleanupPreviewOverlay(fixture.container), true);
fixtureCommandBridge.cleanup();
assert.equal(fixture.region.querySelector(".hmb-seedance-preview-overlay"), null);
assert.equal(fixture.region.getAttribute("data-hmb-seedance-preview-positioned"), "");
await Promise.resolve();
await Promise.resolve();
assert.equal(
  fixture.region.querySelector(".hmb-seedance-preview-overlay"),
  null,
  "Cleanup must invalidate already queued synchronization work instead of reattaching an overlay.",
);

// Electron exposes requestAnimationFrame. The backend action must wait until a
// full frame has committed the busy state, then leave that frame through a
// timer. The no-rAF fallback was exercised by the fixture above.
const rafFixture = previewFixture();
const rafRequests = [];
const rafCallbacks = new Map();
let nextRafId = 1;
const previousRequestAnimationFrame = globalThis.requestAnimationFrame;
const previousCancelAnimationFrame = globalThis.cancelAnimationFrame;
globalThis.requestAnimationFrame = (callback) => {
  const id = nextRafId;
  nextRafId += 1;
  rafCallbacks.set(id, callback);
  return id;
};
globalThis.cancelAnimationFrame = (id) => rafCallbacks.delete(id);
try {
  const rafCommandBridge = installCommandBridge(
    rafFixture,
    (value) => rafRequests.push(value),
  );
  rafFixture.container.__hmbSeedanceLatestProps = {
    value: {
      schema: "hmb-seedance-shot-ui",
      schema_version: 2,
      shot_catalog: {},
      shot: {},
      generation: refreshGeneration,
    },
    onChange() { assert.fail("Refresh must not update durable Shot state."); },
  };
  widget.hmbSeedanceSyncPreviewOverlay(rafFixture.container, {
    generation: refreshGeneration,
  });
  const rafOverlay = rafFixture.region.querySelector(".hmb-seedance-preview-overlay");
  const rafButton = rafOverlay.querySelector("[data-hmb-seedance-preview-action]");
  rafButton.fire("click");
  await Promise.resolve();
  assert.equal(rafOverlay.getAttribute("aria-busy"), "true");
  assert.equal(rafRequests.length, 0);
  assert.equal(rafCallbacks.size, 1);
  const [[rafId, rafCallback]] = [...rafCallbacks.entries()];
  rafCallbacks.delete(rafId);
  rafCallback(16.7);
  assert.equal(
    rafRequests.length,
    0,
    "The backend action cannot run inside the frame that paints its busy state.",
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(rafRequests.length, 1);
  assertRefreshCommand(rafRequests[0]);
  assert.equal(widget.hmbSeedanceCleanupPreviewOverlay(rafFixture.container), true);
  rafCommandBridge.cleanup();

  const cancelledRafFixture = previewFixture();
  const cancelledRafRequests = [];
  const cancelledRafCommandBridge = installCommandBridge(
    cancelledRafFixture,
    (value) => cancelledRafRequests.push(value),
  );
  cancelledRafFixture.container.__hmbSeedanceLatestProps = {
    value: {
      schema: "hmb-seedance-shot-ui",
      schema_version: 2,
      shot_catalog: {},
      shot: {},
      generation: refreshGeneration,
    },
    onChange() { assert.fail("Refresh must not update durable Shot state."); },
  };
  widget.hmbSeedanceSyncPreviewOverlay(cancelledRafFixture.container, {
    generation: refreshGeneration,
  });
  cancelledRafFixture.region
    .querySelector("[data-hmb-seedance-preview-action]")
    .fire("click");
  await Promise.resolve();
  assert.equal(rafCallbacks.size, 1);
  assert.equal(
    widget.hmbSeedanceCleanupPreviewOverlay(cancelledRafFixture.container),
    true,
  );
  assert.equal(rafCallbacks.size, 0, "Cleanup must cancel a queued paint-frame action.");
  cancelledRafCommandBridge.cleanup();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(cancelledRafRequests.length, 0);
} finally {
  if (previousRequestAnimationFrame === undefined) delete globalThis.requestAnimationFrame;
  else globalThis.requestAnimationFrame = previousRequestAnimationFrame;
  if (previousCancelAnimationFrame === undefined) delete globalThis.cancelAnimationFrame;
  else globalThis.cancelAnimationFrame = previousCancelAnimationFrame;
}

// Five independent generator nodes may request retrieval together. Each node
// must publish one small action envelope, even when its overlay is double-
// clicked, instead of echoing the full Shot/catalog state over WebSocket.
const parallelRefreshFixtures = Array.from({ length: 5 }, () => previewFixture());
const parallelRefreshRequests = [];
const parallelRefreshCommandBridges = [];
for (const [index, current] of parallelRefreshFixtures.entries()) {
  parallelRefreshCommandBridges.push(installCommandBridge(
    current,
    (value) => parallelRefreshRequests.push({ index, value }),
  ));
  current.container.__hmbSeedanceLatestProps = {
    value: {
      schema: "hmb-seedance-shot-ui",
      schema_version: 2,
      shot_catalog: {},
      shot: {},
      generation: refreshGeneration,
    },
    onChange() { assert.fail("Refresh must not update durable Shot state."); },
  };
  widget.hmbSeedanceSyncPreviewOverlay(current.container, {
    generation: refreshGeneration,
  });
  const button = current.region.querySelector("[data-hmb-seedance-preview-action]");
  button.fire("click");
  button.fire("click");
}
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(
  parallelRefreshRequests.length,
  5,
  "Five nodes must produce exactly five refresh publications, not click or mutation storms.",
);
assert.deepEqual(
  parallelRefreshRequests.map(({ index }) => index),
  [0, 1, 2, 3, 4],
);
for (const { value } of parallelRefreshRequests) {
  assertRefreshCommand(value);
  assert.ok(
    Buffer.byteLength(JSON.stringify(value), "utf8") <= 256,
    "A refresh publication must remain a bounded action-only WebSocket payload.",
  );
}
assert.equal(
  new Set(parallelRefreshRequests.map(({ value }) => value.action_id)).size,
  5,
  "Concurrent nodes must retain distinct idempotency identities.",
);
for (const [index, current] of parallelRefreshFixtures.entries()) {
  widget.hmbSeedanceCleanupPreviewOverlay(current.container);
  parallelRefreshCommandBridges[index].cleanup();
}

// An action-only onChange may never receive a host acknowledgement. The
// watchdog must release the overlay and the exact same button instance must be
// safe to retry; no React-owned native ParameterButton is involved.
const timeoutFixture = previewFixture();
const timeoutRequests = [];
const timeoutCommandBridge = installCommandBridge(timeoutFixture, (value) => {
  timeoutRequests.push(value);
  return new Promise(() => {});
});
const originalSetTimeout = globalThis.setTimeout;
const originalClearTimeout = globalThis.clearTimeout;
const fakeTimers = new Map();
let nextTimerId = 1;
globalThis.setTimeout = (callback, delay = 0) => {
  const id = nextTimerId;
  nextTimerId += 1;
  fakeTimers.set(id, { callback, delay: Number(delay) });
  return id;
};
globalThis.clearTimeout = (id) => fakeTimers.delete(id);
try {
  timeoutFixture.container.__hmbSeedanceLatestProps = {
    value: {
      schema: "hmb-seedance-shot-ui",
      schema_version: 2,
      shot_catalog: {},
      shot: {},
      generation: refreshGeneration,
    },
    onChange() { assert.fail("Refresh must not update durable Shot state."); },
  };
  widget.hmbSeedanceSyncPreviewOverlay(timeoutFixture.container, {
    generation: refreshGeneration,
  });
  const timeoutOverlay = timeoutFixture.region.querySelector(
    ".hmb-seedance-preview-overlay",
  );
  const timeoutButton = timeoutOverlay.querySelector(
    "[data-hmb-seedance-preview-action]",
  );
  timeoutButton.fire("click");
  await Promise.resolve();

  const dispatchTimer = [...fakeTimers.entries()].find(([, timer]) => timer.delay === 0);
  assert.ok(dispatchTimer, "The action-only dispatch must remain outside the overlay click stack.");
  fakeTimers.delete(dispatchTimer[0]);
  dispatchTimer[1].callback();
  assert.equal(timeoutRequests.length, 1);
  assertRefreshCommand(timeoutRequests[0]);
  const firstTimeoutActionId = timeoutRequests[0].action_id;

  const watchdogTimer = [...fakeTimers.entries()].find(
    ([, timer]) => timer.delay === widget.HMB_SEEDANCE_PREVIEW_ACTION_WATCHDOG_MS,
  );
  assert.ok(watchdogTimer, "A ten-second delivery watchdog must be armed.");
  fakeTimers.delete(watchdogTimer[0]);
  watchdogTimer[1].callback();
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(timeoutFixture.container.__hmbSeedancePreviewActionPending, undefined);
  assert.equal(timeoutOverlay.getAttribute("aria-busy"), "false");
  assert.equal(timeoutButton.disabled, false, "The overlay must release its own busy lock.");
  assert.equal(
    timeoutOverlay.querySelector(".hmb-seedance-preview-overlay__detail").textContent,
    "요청 전달을 확인하지 못했습니다. 잠시 후 다시 시도하세요.",
  );

  timeoutButton.fire("click");
  await Promise.resolve();
  const retryDispatchTimer = [...fakeTimers.entries()].find(([, timer]) => timer.delay === 0);
  assert.ok(retryDispatchTimer, "The same overlay button must be retryable after timeout.");
  fakeTimers.delete(retryDispatchTimer[0]);
  retryDispatchTimer[1].callback();
  assert.equal(timeoutRequests.length, 2);
  assertRefreshCommand(timeoutRequests[1]);
  assert.notEqual(
    timeoutRequests[1].action_id,
    firstTimeoutActionId,
    "A retry must receive a fresh idempotency identity.",
  );
} finally {
  widget.hmbSeedanceCleanupPreviewOverlay(timeoutFixture.container);
  timeoutCommandBridge.cleanup();
  fakeTimers.clear();
  globalThis.setTimeout = originalSetTimeout;
  globalThis.clearTimeout = originalClearTimeout;
}

console.log(
  "HMB Seedance native preview status-overlay regression: PASS "
  + "(centre/badge phases, retained video, elapsed status, refresh-only presentation, canplay gate)",
);
