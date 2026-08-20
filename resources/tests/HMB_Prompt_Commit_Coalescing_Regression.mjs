import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(widgetPath);

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function focusedTextFixture() {
  const input = {
    value: "Focused trailing value",
    selectionStart: 22,
    selectionEnd: 22,
    selectionDirection: "none",
    scrollTop: 0,
    scrollLeft: 0,
    matches() { return true; },
    getAttribute(name) { return name === "data-text-key" ? "SCENE_CONTEXT" : ""; },
    closest() { return null; },
  };
  const container = {
    dataset: {},
    contains(candidate) { return candidate === input; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  return { container, input };
}

const originalDocument = globalThis.document;
const { container, input } = focusedTextFixture();
globalThis.document = { activeElement: input };
const state = widget.normalizeState({
  text: { SCENE_CONTEXT: "Focused trailing value" },
});
const emissions = [];
widget.hmbScheduleImmediateStateCommit(container, {
  onChange(value) { emissions.push(value); },
}, state);
await delay(330);
assert.equal(emissions.length, 1, "Focused Prompt text must publish its trailing value without blur.");
assert.equal(JSON.parse(emissions[0]).text.SCENE_CONTEXT, "Focused trailing value");
clearTimeout(container.__hmbPromptPendingLocalTimer);

const composing = focusedTextFixture();
globalThis.document = { activeElement: composing.input };
composing.container.__hmbPromptLibraryCompositionActive = true;
const compositionEmissions = [];
widget.hmbScheduleImmediateStateCommit(composing.container, {
  onChange(value) { compositionEmissions.push(value); },
}, state);
await delay(300);
assert.equal(compositionEmissions.length, 0, "An unfinished IME composition must remain deferred.");
composing.container.__hmbPromptLibraryCompositionActive = false;
widget.hmbScheduleImmediateStateCommit(composing.container, {
  onChange(value) { compositionEmissions.push(value); },
}, state);
await delay(330);
assert.equal(compositionEmissions.length, 1, "Composition end must arm one reliable trailing publish.");
clearTimeout(composing.container.__hmbPromptPendingLocalTimer);
globalThis.document = originalDocument;

const dirtyTextContainer = {};
const dirtyTextControl = {
  value: "Local IME text survives",
  matches() { return true; },
  getAttribute(name) { return name === "data-text-key" ? "SCENE_CONTEXT" : ""; },
  closest() { return null; },
};
assert.equal(
  widget.hmbRememberPromptDirtyTextControl(
    dirtyTextContainer,
    dirtyTextControl,
    widget.normalizeState({ text: { SCENE_CONTEXT: "Local draft" } }),
  ),
  true,
);
const authoritativePrompt = widget.normalizeState({
  text: {
    SCENE_CONTEXT: "Server text",
    PROJECT_STYLE_LOOK: "Authoritative project look",
  },
  ui: { language: "ko" },
  videos: [{
    slot: 1,
    video_uid: "video-one",
    source_uid: "video-one",
    label: "Backend video label",
    keep_out: "Backend keep out",
    manual: true,
  }],
});
const mergedDirtyText = widget.hmbMergePromptDirtyTextState(
  authoritativePrompt,
  dirtyTextContainer.__hmbPromptLibraryDirtyText,
);
assert.equal(mergedDirtyText.text.SCENE_CONTEXT, "Local IME text survives");
assert.equal(mergedDirtyText.text.PROJECT_STYLE_LOOK, "Authoritative project look");
assert.equal(mergedDirtyText.ui.language, "ko", "Unrelated authoritative UI state must survive dirty text merge.");

const mergedSourceText = widget.hmbMergePromptDirtyTextState(authoritativePrompt, [{
  kind: "source",
  sourceKind: "video",
  sourceKey: "video-source:video-one",
  index: 0,
  slot: 1,
  field: "keep_out",
  arrayField: "",
  arrayIndex: 0,
  value: "Local composing keep out",
}]);
assert.equal(mergedSourceText.videos[0].keep_out, "Local composing keep out");
assert.equal(mergedSourceText.videos[0].label, "Backend video label");
const removedSourceMerge = widget.hmbMergePromptDirtyTextState(
  widget.normalizeState({ videos: [{ slot: 1, manual: true }] }),
  [{
    kind: "source",
    sourceKind: "video",
    sourceKey: "video-source:video-one",
    index: 0,
    slot: 1,
    field: "keep_out",
    value: "Must not resurrect removed source",
  }],
);
assert.notEqual(removedSourceMerge.videos[0].keep_out, "Must not resurrect removed source");

const manualImageState = widget.normalizeState({
  images: [{
    slot: 1,
    label: "Saved manual image",
    source_type: "Custom",
    custom_source_type: "Manual reference",
    manual: true,
  }],
});
const manualImageRow = {
  getAttribute(name) {
    if (name === "data-kind") return "image";
    if (name === "data-index") return "0";
    return "";
  },
};
const manualImageInput = {
  value: "Uncommitted manual image name",
  matches() { return true; },
  getAttribute(name) { return name === "data-field" ? "label" : ""; },
  closest(selector) { return selector === ".source-row" ? manualImageRow : null; },
};
const manualImageContainer = {};
assert.equal(
  widget.hmbRememberPromptDirtyTextControl(
    manualImageContainer,
    manualImageInput,
    manualImageState,
  ),
  true,
);
const managedImageAuthority = widget.normalizeState({
  images: [{
    slot: 1,
    label: "Authoritative managed asset",
    asset_library_id: "managed-asset-one",
    asset_source_uid: "project:managed-asset-one",
    asset_source_kind: "project",
    asset_managed: true,
    asset_verified: true,
    source_type: "Character Appearance",
  }],
  image_asset: {
    enabled: true,
    order_managed: true,
    dormant_manual_rows: [manualImageState.images[0]],
  },
});
const manualToManagedMerge = widget.hmbMergePromptDirtyTextState(
  managedImageAuthority,
  manualImageContainer.__hmbPromptLibraryDirtyText,
);
assert.equal(
  manualToManagedMerge.images[0].label,
  "Authoritative managed asset",
  "A manual @image1 draft must never contaminate a new managed @image1 authority.",
);
assert.equal(
  manualToManagedMerge.image_asset.dormant_manual_rows[0].label,
  "Uncommitted manual image name",
  "The displaced manual draft must follow its manual row into dormant storage.",
);

const orphanedComposition = { __hmbPromptLibraryCompositionActive: true };
assert.equal(widget.hmbReleasePromptCompositionLatch(orphanedComposition), true);
assert.equal(widget.hmbShouldDeferPromptTextCommit(orphanedComposition), false);
assert.equal(widget.hmbReleasePromptCompositionLatch(orphanedComposition), false);

const originalConsoleError = console.error;
const transportDiagnostics = [];
console.error = (...args) => transportDiagnostics.push(args);
const promptTransportState = widget.normalizeState({
  text: { SCENE_CONTEXT: "Unsaved transport value" },
});
const transportControl = {
  value: "Unsaved transport value",
  matches() { return true; },
  getAttribute(name) { return name === "data-text-key" ? "SCENE_CONTEXT" : ""; },
  closest() { return null; },
};
const markTransportDirty = (container, value = "Unsaved transport value") => {
  transportControl.value = value;
  assert.equal(
    widget.hmbRememberPromptDirtyTextControl(container, transportControl, promptTransportState),
    true,
  );
};
try {
  const syncFailureContainer = {};
  markTransportDirty(syncFailureContainer);
  assert.doesNotThrow(() => {
    widget.hmbEmitLocalPromptState(syncFailureContainer, {
      onChange() { throw new Error("sync transport failure"); },
    }, promptTransportState);
  });
  assert.equal(syncFailureContainer.__hmbPromptLibraryDirtyText instanceof Map, true);
  assert.equal(syncFailureContainer.__hmbPromptLibraryCommitPending, true);
  assert.match(syncFailureContainer.__hmbPromptLibraryLastPublishError.message, /sync transport failure/);
  assert.equal(syncFailureContainer.__hmbPromptPendingLocalValues, undefined);
  const retryValues = [];
  assert.equal(widget.hmbFlushImmediateStateCommit(syncFailureContainer, {
    onChange(value) { retryValues.push(value); },
  }, promptTransportState), true);
  assert.equal(retryValues.length, 1, "An explicit flush must retry the latest failed publication.");
  assert.equal(syncFailureContainer.__hmbPromptLibraryDirtyText, undefined);
  clearTimeout(syncFailureContainer.__hmbPromptPendingLocalTimer);

  const savedRetrySetTimeout = globalThis.setTimeout;
  const savedRetryClearTimeout = globalThis.clearTimeout;
  const promptRetryTimers = new Map();
  let promptRetrySequence = 0;
  globalThis.setTimeout = (callback, delayMs = 0) => {
    const id = ++promptRetrySequence;
    promptRetryTimers.set(id, { callback, delay: Number(delayMs) || 0 });
    return id;
  };
  globalThis.clearTimeout = (id) => promptRetryTimers.delete(id);
  try {
    const automaticRetryContainer = {};
    const latestPromptState = widget.normalizeState({
      text: { SCENE_CONTEXT: "Latest prompt required by immediate Agent execution" },
    });
    markTransportDirty(
      automaticRetryContainer,
      "Latest prompt required by immediate Agent execution",
    );
    let automaticRetryCalls = 0;
    let agentVisiblePrompt = "";
    widget.hmbEmitLocalPromptState(automaticRetryContainer, {
      onChange(value) {
        automaticRetryCalls += 1;
        if (automaticRetryCalls === 1) throw new Error("one-shot prompt transport failure");
        agentVisiblePrompt = JSON.parse(value).text.SCENE_CONTEXT;
      },
    }, latestPromptState);
    assert.equal(automaticRetryCalls, 1);
    assert.equal(automaticRetryContainer.__hmbPromptLibraryCommitPending, true);
    assert.equal(promptRetryTimers.size, 1);
    const [retryId, retryTimer] = promptRetryTimers.entries().next().value;
    promptRetryTimers.delete(retryId);
    assert.ok(retryTimer.delay >= 0 && retryTimer.delay <= 100);
    retryTimer.callback();
    assert.equal(automaticRetryCalls, 2);
    assert.equal(
      agentVisiblePrompt,
      "Latest prompt required by immediate Agent execution",
      "The bounded retry must make the latest prompt visible before the next Agent execution.",
    );
    assert.equal(automaticRetryContainer.__hmbPromptLibraryDirtyText, undefined);
    assert.equal(automaticRetryContainer.__hmbPromptLibraryCommitPending, false);
    assert.equal(automaticRetryContainer.__hmbPromptLibraryLastPublishError, undefined);
    delete automaticRetryContainer.__hmbPromptPendingLocalValues;
    delete automaticRetryContainer.__hmbPromptPendingLocalTimer;
    promptRetryTimers.clear();
  } finally {
    globalThis.setTimeout = savedRetrySetTimeout;
    globalThis.clearTimeout = savedRetryClearTimeout;
  }

  const asyncFailureContainer = {};
  markTransportDirty(asyncFailureContainer);
  widget.hmbEmitLocalPromptState(asyncFailureContainer, {
    onChange() { return Promise.reject(new Error("async transport failure")); },
  }, promptTransportState);
  await delay(0);
  assert.equal(asyncFailureContainer.__hmbPromptLibraryDirtyText instanceof Map, true);
  assert.equal(asyncFailureContainer.__hmbPromptLibraryCommitPending, true);
  assert.match(asyncFailureContainer.__hmbPromptLibraryLastPublishError.message, /async transport failure/);
  widget.hmbInvalidatePromptPublication(asyncFailureContainer);

  let rejectOlderPublication;
  const olderPromise = new Promise((_resolve, reject) => {
    rejectOlderPublication = reject;
  });
  const staleFailureContainer = {};
  markTransportDirty(staleFailureContainer, "Older draft");
  const olderTransportState = widget.normalizeState({
    text: { SCENE_CONTEXT: "Older failed payload" },
  });
  const newerTransportState = widget.normalizeState({
    text: { SCENE_CONTEXT: "Newer successful payload" },
  });
  const olderToken = widget.hmbEmitLocalPromptState(staleFailureContainer, {
    onChange() { return olderPromise; },
  }, olderTransportState);
  markTransportDirty(staleFailureContainer, "Newer successful draft");
  const newerToken = widget.hmbEmitLocalPromptState(
    staleFailureContainer,
    { onChange() {} },
    newerTransportState,
  );
  rejectOlderPublication(new Error("stale async rejection"));
  await delay(0);
  assert.equal(
    staleFailureContainer.__hmbPromptLibraryDirtyText,
    undefined,
    "An older rejection must not restore dirty data over a newer success.",
  );
  assert.equal(staleFailureContainer.__hmbPromptLibraryLastPublishError, undefined);
  const liveEchoTokens = (staleFailureContainer.__hmbPromptPendingLocalValues || [])
    .map((item) => item.publicationToken);
  assert.equal(liveEchoTokens.includes(olderToken), false, "A failed stale echo must be removed.");
  assert.equal(liveEchoTokens.includes(newerToken), true, "The newer successful echo must remain consumable.");
  clearTimeout(staleFailureContainer.__hmbPromptPendingLocalTimer);

  const rawBlurContainer = {
    contains(candidate) { return candidate === transportControl; },
  };
  markTransportDirty(rawBlurContainer, "Raw blur draft");
  assert.doesNotThrow(() => {
    widget.hmbFinalizePromptTextBlur(rawBlurContainer, {
      currentTarget: transportControl,
      relatedTarget: null,
    }, () => widget.hmbEmitPromptState(rawBlurContainer, {
      onChange() { throw new Error("raw blur transport failure"); },
    }, promptTransportState));
  });
  assert.equal(rawBlurContainer.__hmbPromptLibraryDirtyText instanceof Map, true);
  assert.equal(rawBlurContainer.__hmbPromptLibraryCommitPending, true);
  widget.hmbInvalidatePromptPublication(rawBlurContainer);

  let rejectCleanupPublication;
  const cleanupPublicationPromise = new Promise((_resolve, reject) => {
    rejectCleanupPublication = reject;
  });
  const cleanupTransportContainer = { innerHTML: "mounted" };
  markTransportDirty(cleanupTransportContainer, "Cleanup draft");
  widget.hmbEmitLocalPromptState(cleanupTransportContainer, {
    onChange() { return cleanupPublicationPromise; },
  }, promptTransportState);
  // Model the cleanup's post-flush owner invalidation and state teardown.
  widget.hmbInvalidatePromptPublication(cleanupTransportContainer);
  clearTimeout(cleanupTransportContainer.__hmbPromptPendingLocalTimer);
  delete cleanupTransportContainer.__hmbPromptPendingLocalValues;
  delete cleanupTransportContainer.__hmbPromptPendingLocalTimer;
  delete cleanupTransportContainer.__hmbPromptLibraryDirtyText;
  cleanupTransportContainer.__hmbPromptLibraryCommitPending = false;
  cleanupTransportContainer.innerHTML = "";
  rejectCleanupPublication(new Error("reject after cleanup"));
  await delay(0);
  assert.equal(cleanupTransportContainer.__hmbPromptLibraryDirtyText, undefined);
  assert.equal(cleanupTransportContainer.__hmbPromptLibraryCommitPending, false);
  assert.equal(cleanupTransportContainer.__hmbPromptLibraryLastPublishError, undefined);
  assert.equal(cleanupTransportContainer.innerHTML, "");
} finally {
  console.error = originalConsoleError;
}
assert.ok(transportDiagnostics.length >= 3, "Transport failures must remain diagnosable.");

assert.match(
  source,
  /const dirtyText = hmbPromptDirtyTextEntries\(container\);[\s\S]*?if \(dirtyText\.length\) \{\s*nextState = hmbMergePromptDirtyTextState\(nextState, dirtyText\);\s*\}[\s\S]*?state = nextState;[\s\S]*?if \(shotRegionOnly\)[\s\S]*?else \{\s*remount\(\);\s*\}[\s\S]*?if \(dirtyText\.length \|\| shouldRepublishRevisionMerge\) \{\s*hmbScheduleImmediateStateCommit/,
  "External props must merge unresolved text and rearm its trailing commit against the authoritative state.",
);
assert.match(
  source,
  /const remount = \(nextState = null\) => \{[\s\S]*?const compositionWasActive = Boolean\([\s\S]*?if \(!hmbPatchPromptDashboard\(container, markup\)\) container\.innerHTML = markup;[\s\S]*?if \(\s*compositionWasActive[\s\S]*?\) hmbReleasePromptCompositionLatch\(container\);/,
  "A remount must patch first and release composition only when the composing control was replaced.",
);
assert.match(
  source,
  /const cleanup = \(\) => \{[\s\S]*?hmbInvalidatePromptPublication\(container\);[\s\S]*?hmbClearImmediateStateCommit\(container\)[\s\S]*?hmbInvalidatePromptPublication\(container\);[\s\S]*?hmbClearPendingPromptStateEchoes\(container\)[\s\S]*?hmbClearPromptDirtyText\(container\)[\s\S]*?container\.innerHTML = ""/,
  "Prompt cleanup must cancel drafts and pending echoes without publishing into a disposed widget.",
);

assert.doesNotMatch(
  source,
  /class="output-guide"|<aside class="rail (?:left|right)"/,
  "Removed dashboard guide rails must not leave decorative PROMPT_OUT UI behind.",
);

const originalWindow = globalThis.window;
const resizeEvents = [];
globalThis.window = {
  dispatchEvent(event) { resizeEvents.push(event.type); },
};
const resizeContainer = {};
assert.equal(widget.hmbRequestPromptHostResize(resizeContainer), true);
assert.equal(widget.hmbRequestPromptHostResize(resizeContainer), false, "Resize invalidation must coalesce while edits are active.");
await delay(120);
assert.deepEqual(resizeEvents, ["resize"], "A shell geometry change must request one standard host resize invalidation.");
globalThis.window = originalWindow;

console.log("HMB Prompt commit/coalescing regression passed.");
