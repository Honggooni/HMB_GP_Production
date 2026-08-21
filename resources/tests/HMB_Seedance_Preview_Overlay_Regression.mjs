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
  widgetParent.append(container);
  parameter.append(region);
  nodeRoot.append(widgetParent, parameter);
  return { nodeRoot, container, parameter, region };
}

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
fixture.container.__hmbSeedanceLatestProps = {
  value: {
    schema: "hmb-seedance-shot-ui",
    schema_version: 2,
    shot_catalog: {},
    shot: {},
    generation: refreshGeneration,
  },
  onChange(request) {
    assert.equal(
      insideRefreshClickStack,
      false,
      "Refresh publication must be deferred beyond the button click stack.",
    );
    refreshRequests.push(request);
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
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(refreshRequests.length, 1, "One UI pulse must produce at most one backend refresh request.");
assert.deepEqual(
  refreshRequests[0],
  { request: { action: "refresh_existing" } },
  "The transient action must not republish the durable Shot/catalog state.",
);
assert.deepEqual(refreshRequests[0].request, { action: "refresh_existing" });
assert.equal(
  Object.keys(refreshRequests[0].request).includes("job_id"),
  false,
  "The browser action itself must never nominate a task ID.",
);

assert.equal(widget.hmbSeedanceCleanupPreviewOverlay(fixture.container), true);
assert.equal(fixture.region.querySelector(".hmb-seedance-preview-overlay"), null);
assert.equal(fixture.region.getAttribute("data-hmb-seedance-preview-positioned"), "");
await Promise.resolve();
await Promise.resolve();
assert.equal(
  fixture.region.querySelector(".hmb-seedance-preview-overlay"),
  null,
  "Cleanup must invalidate already queued synchronization work instead of reattaching an overlay.",
);

console.log(
  "HMB Seedance native preview status-overlay regression: PASS "
  + "(centre/badge phases, retained video, elapsed status, refresh-only presentation, canplay gate)",
);
