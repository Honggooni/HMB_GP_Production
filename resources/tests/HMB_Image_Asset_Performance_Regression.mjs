import assert from "node:assert/strict";
import fs from "node:fs";


const ASSET_WIDGET_PATH = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const assetSource = fs.readFileSync(ASSET_WIDGET_PATH, "utf8");
const assetWidget = await import(ASSET_WIDGET_PATH);


const feedbackClasses = new Set();
const feedbackAttributes = new Map([["data-asset-key", "asset-feedback"]]);
const feedbackCard = {
  classList: {
    toggle(name, enabled) {
      if (enabled) feedbackClasses.add(name);
      else feedbackClasses.delete(name);
    },
  },
  getAttribute(name) { return feedbackAttributes.get(name) || ""; },
  setAttribute(name, value) { feedbackAttributes.set(name, String(value)); },
};
const trayCount = { textContent: "" };
const tray = { innerHTML: "", scrollLeft: 19 };
const statusAttributes = new Map();
const status = {
  textContent: "",
  setAttribute(name, value) { statusAttributes.set(name, String(value)); },
};
const feedbackElements = new Map([
  [".tray-head em", trayCount],
  [".tray-scroll", tray],
  [".toolbar-status strong", status],
]);
const feedbackContainer = {
  querySelectorAll(selector) {
    return selector === "[data-asset-key]" ? [feedbackCard] : [];
  },
  querySelector(selector) { return feedbackElements.get(selector) || null; },
};
const feedbackState = assetWidget.hmbNormalizeImageAssetState({
  assets: [{
    asset_library_id: "asset-feedback",
    source_uid: "project:asset-feedback",
    source_kind: "project",
    registered: true,
    asset_id: "Feedback",
    image_name: "Feedback Image",
    selected: true,
    selection_order: 1,
  }],
});

assetWidget.hmbApplyImageAssetSelectionFeedback(feedbackContainer, feedbackState);
assert.equal(
  feedbackClasses.has("selected"),
  true,
  "A click must outline its card locally before the host round trip.",
);
assert.equal(feedbackAttributes.get("aria-pressed"), "true");
assert.equal(trayCount.textContent, "1/50");
assert.match(
  tray.innerHTML,
  /data-selected-key="asset-feedback"/,
  "A click must populate the selected tray locally.",
);
assert.equal(tray.scrollLeft, 19, "Local tray replacement must retain scroll position.");
assert.match(status.textContent, /1\/50 SEL/);
assert.deepEqual(
  feedbackState,
  assetWidget.hmbNormalizeImageAssetState(feedbackState),
  "Local feedback must remain canonical so an exact host echo skips remount.",
);

const scheduledFrames = [];
let commitCount = 0;
const originalAnimationFrame = globalThis.requestAnimationFrame;
globalThis.requestAnimationFrame = (callback) => {
  scheduledFrames.push(callback);
  return scheduledFrames.length;
};
try {
  assetWidget.hmbScheduleImageAssetSelectionCommit({}, () => {
    commitCount += 1;
  });
  assert.equal(commitCount, 0);
  assert.equal(scheduledFrames.length, 1);
  scheduledFrames.shift()();
  assert.equal(commitCount, 0, "The first animation frame must paint local feedback.");
  assert.equal(scheduledFrames.length, 1);
  scheduledFrames.shift()();
  assert.equal(commitCount, 1, "The second frame may publish the canonical state.");
} finally {
  if (originalAnimationFrame === undefined) delete globalThis.requestAnimationFrame;
  else globalThis.requestAnimationFrame = originalAnimationFrame;
}

const originalTimeout = globalThis.setTimeout;
const originalClearTimeout = globalThis.clearTimeout;
const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;
const backgroundFrames = [];
const backgroundTimers = new Map();
let backgroundTimerId = 0;
globalThis.requestAnimationFrame = (callback) => {
  backgroundFrames.push(callback);
  return backgroundFrames.length;
};
globalThis.cancelAnimationFrame = () => {};
globalThis.setTimeout = (callback) => {
  const id = ++backgroundTimerId;
  backgroundTimers.set(id, callback);
  return id;
};
globalThis.clearTimeout = (id) => backgroundTimers.delete(id);
try {
  const backgroundContainer = { __hmbImageAssetMountToken: 41 };
  let backgroundCommits = 0;
  assetWidget.hmbScheduleImageAssetSelectionCommit(backgroundContainer, () => {
    backgroundCommits += 1;
  });
  assert.equal(backgroundFrames.length, 1);
  assert.equal(backgroundTimers.size, 1, "A background-safe fallback must accompany the paint path.");
  [...backgroundTimers.values()][0]();
  assert.equal(backgroundCommits, 1, "The fallback must publish when animation frames are suspended.");
  backgroundFrames.splice(0).forEach((callback) => callback());
  assert.equal(backgroundCommits, 1, "Late animation frames must not duplicate a fallback publish.");

  const flushContainer = { __hmbImageAssetMountToken: 42 };
  const flushed = [];
  assetWidget.hmbScheduleImageAssetSelectionCommit(flushContainer, () => flushed.push("old"));
  assetWidget.hmbScheduleImageAssetSelectionCommit(flushContainer, () => flushed.push("latest"));
  assert.equal(assetWidget.hmbFlushImageAssetSelectionCommit(flushContainer), true);
  assert.deepEqual(flushed, ["latest"], "Rapid clicks must coalesce and remount/cleanup must flush once.");
  assert.equal(assetWidget.hmbFlushImageAssetSelectionCommit(flushContainer), false);

  const staleMount = { __hmbImageAssetMountToken: 43 };
  let staleMountCommits = 0;
  assetWidget.hmbScheduleImageAssetSelectionCommit(staleMount, () => {
    staleMountCommits += 1;
  });
  staleMount.__hmbImageAssetMountToken = 44;
  assert.equal(assetWidget.hmbFlushImageAssetSelectionCommit(staleMount), false);
  assert.equal(staleMountCommits, 0, "A prior mount job must never publish into a reused container.");
} finally {
  globalThis.setTimeout = originalTimeout;
  globalThis.clearTimeout = originalClearTimeout;
  if (originalAnimationFrame === undefined) delete globalThis.requestAnimationFrame;
  else globalThis.requestAnimationFrame = originalAnimationFrame;
  if (originalCancelAnimationFrame === undefined) delete globalThis.cancelAnimationFrame;
  else globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
}

const makeAutoSyncContainer = () => ({
  innerHTML: "",
  setAttribute() {},
  removeAttribute() {},
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {},
  removeEventListener() {},
});
const exerciseAutoSyncFailure = async (failureKind) => {
  const timers = new Map();
  let timerSequence = 0;
  let fakeNow = 100_000;
  const savedSetTimeout = globalThis.setTimeout;
  const savedClearTimeout = globalThis.clearTimeout;
  const savedDateNow = Date.now;
  globalThis.setTimeout = (callback, delay = 0) => {
    const id = ++timerSequence;
    timers.set(id, { callback, delay: Number(delay) || 0 });
    return id;
  };
  globalThis.clearTimeout = (id) => timers.delete(id);
  Date.now = () => fakeNow;
  const runNextTimer = () => {
    const entry = timers.entries().next().value;
    assert.ok(entry, "Auto-sync must leave a next timer installed.");
    const [id, timer] = entry;
    timers.delete(id);
    fakeNow += timer.delay;
    timer.callback();
    return timer.delay;
  };
  const container = makeAutoSyncContainer();
  let calls = 0;
  let mounted;
  try {
    mounted = assetWidget.default(container, {
      value: { project_root: "C:/project", catalog_root: "C:/project" },
      onChange() {
        calls += 1;
        if (calls !== 1) return undefined;
        if (failureKind === "throw") throw new Error("auto-sync throw");
        return Promise.reject(new Error("auto-sync reject"));
      },
    });
    runNextTimer();
    if (failureKind === "reject") await Promise.resolve();
    assert.equal(calls, 1);
    assert.equal(timers.size, 1, `${failureKind} must keep exactly one retry scheduled.`);
    assert.equal(
      [...timers.values()][0].delay,
      1000,
      `${failureKind} must replace the default interval with bounded backoff.`,
    );
    runNextTimer();
    assert.equal(calls, 2, `${failureKind} recovery poll must execute after backoff.`);
    assert.equal(timers.size, 1, "A successful recovery must restore periodic polling.");
  } finally {
    try { mounted?.cleanup?.(); } catch (_error) {}
    globalThis.setTimeout = savedSetTimeout;
    globalThis.clearTimeout = savedClearTimeout;
    Date.now = savedDateNow;
  }
};
await exerciseAutoSyncFailure("throw");
await exerciseAutoSyncFailure("reject");

const selectableAsset = (id, selected = false, order = 0, extra = {}) => ({
  asset_library_id: id,
  source_uid: `project:${id}`,
  source_kind: "project",
  registered: true,
  asset_id: id,
  image_name: id,
  selected,
  selection_order: order,
  ...extra,
});
const mergeBase = assetWidget.hmbNormalizeImageAssetState({
  manifest_signature: "manifest-old",
  assets: [selectableAsset("asset-a", true, 1), selectableAsset("asset-b")],
});
const mergeLocal = JSON.parse(JSON.stringify(mergeBase));
mergeLocal.assets[1].selected = true;
mergeLocal.assets[1].selection_order = 2;
const mergeAuthoritative = assetWidget.hmbNormalizeImageAssetState({
  manifest_signature: "manifest-new",
  assets: [
    selectableAsset("asset-a", true, 1, { image_name: "Backend A" }),
    selectableAsset("asset-b"),
    selectableAsset("asset-c", true, 2),
  ],
});
const mergedSelection = assetWidget.hmbMergeImageAssetSelectionDelta(
  mergeAuthoritative,
  assetWidget.hmbImageAssetSelectionSnapshot(mergeBase),
  mergeLocal,
);
assert.equal(mergedSelection.manifest_signature, "manifest-new");
assert.equal(mergedSelection.assets[0].image_name, "Backend A");
assert.equal(mergedSelection.assets.find((item) => item.asset_library_id === "asset-b")?.selected, true);
assert.equal(mergedSelection.assets.find((item) => item.asset_library_id === "asset-c")?.selected, true);

const revokedAuthoritative = JSON.parse(JSON.stringify(mergeAuthoritative));
const revokedB = revokedAuthoritative.assets.find((item) => item.asset_library_id === "asset-b");
revokedB.registered = false;
const revokedMerge = assetWidget.hmbMergeImageAssetSelectionDelta(
  revokedAuthoritative,
  assetWidget.hmbImageAssetSelectionSnapshot(mergeBase),
  mergeLocal,
);
assert.equal(
  revokedMerge.assets.find((item) => item.asset_library_id === "asset-b")?.selected,
  false,
  "A local click must not resurrect an asset whose authority was revoked during the two-frame window.",
);

const originalConsoleError = console.error;
console.error = () => {};
try {
  const savedRetrySetTimeout = globalThis.setTimeout;
  const savedRetryClearTimeout = globalThis.clearTimeout;
  const genericRetryTimers = new Map();
  let genericRetrySequence = 0;
  globalThis.setTimeout = (callback, delay = 0) => {
    const id = ++genericRetrySequence;
    genericRetryTimers.set(id, { callback, delay: Number(delay) || 0 });
    return id;
  };
  globalThis.clearTimeout = (id) => genericRetryTimers.delete(id);
  try {
    const runGenericRetry = () => {
      const entry = genericRetryTimers.entries().next().value;
      assert.ok(entry, "A failed generic semantic emit must schedule one retry.");
      const [id, timer] = entry;
      genericRetryTimers.delete(id);
      assert.ok(timer.delay >= 0 && timer.delay <= 100, "Retry must remain bounded and prompt.");
      timer.callback();
    };

    const genericSyncContainer = {};
    let genericSyncCalls = 0;
    assetWidget.hmbPublishImageAssetState(genericSyncContainer, {
      onChange() {
        genericSyncCalls += 1;
        if (genericSyncCalls === 1) throw new Error("generic sync failure");
      },
    }, mergeLocal);
    assert.equal(genericSyncCalls, 1);
    assert.equal(genericRetryTimers.size, 1);
    runGenericRetry();
    assert.equal(genericSyncCalls, 2);
    assert.equal(genericRetryTimers.size, 0);
    assert.equal(genericSyncContainer.__hmbImageAssetLastPublishError, undefined);

    const genericAsyncContainer = {};
    let genericAsyncCalls = 0;
    assetWidget.hmbPublishImageAssetState(genericAsyncContainer, {
      onChange() {
        genericAsyncCalls += 1;
        if (genericAsyncCalls === 1) return Promise.reject(new Error("generic async failure"));
        return undefined;
      },
    }, mergeLocal);
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(genericRetryTimers.size, 1);
    runGenericRetry();
    assert.equal(genericAsyncCalls, 2);
    assert.equal(genericAsyncContainer.__hmbImageAssetLastPublishError, undefined);

    const supersededGenericContainer = {};
    let staleGenericCalls = 0;
    assetWidget.hmbPublishImageAssetState(supersededGenericContainer, {
      onChange() {
        staleGenericCalls += 1;
        throw new Error("old generic failure");
      },
    }, mergeBase);
    const staleRetryCallback = [...genericRetryTimers.values()][0].callback;
    assetWidget.hmbPublishImageAssetState(
      supersededGenericContainer,
      { onChange() {} },
      mergeLocal,
    );
    assert.equal(genericRetryTimers.size, 0, "A newer semantic emit must cancel the older retry.");
    staleRetryCallback();
    assert.equal(staleGenericCalls, 1, "A cancelled old retry must remain inert if its callback races.");
  } finally {
    globalThis.setTimeout = savedRetrySetTimeout;
    globalThis.clearTimeout = savedRetryClearTimeout;
  }

  const syncTransportContainer = {};
  let syncRollbackCount = 0;
  assert.doesNotThrow(() => {
    assetWidget.hmbPublishImageAssetState(syncTransportContainer, {
      onChange() { throw new Error("sync selection transport failure"); },
    }, mergeLocal, () => { syncRollbackCount += 1; });
  });
  assert.equal(syncRollbackCount, 1);
  assert.match(syncTransportContainer.__hmbImageAssetLastPublishError.message, /sync selection/);

  const asyncTransportContainer = {};
  let asyncRollbackCount = 0;
  assetWidget.hmbPublishImageAssetState(asyncTransportContainer, {
    onChange() { return Promise.reject(new Error("async selection transport failure")); },
  }, mergeLocal, () => { asyncRollbackCount += 1; });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(asyncRollbackCount, 1);

  let rejectOlderSelection;
  const olderSelectionPromise = new Promise((_resolve, reject) => {
    rejectOlderSelection = reject;
  });
  const staleSelectionContainer = {};
  let staleRollbackCount = 0;
  assetWidget.hmbPublishImageAssetState(staleSelectionContainer, {
    onChange() { return olderSelectionPromise; },
  }, mergeBase, () => { staleRollbackCount += 1; });
  assetWidget.hmbPublishImageAssetState(
    staleSelectionContainer,
    { onChange() {} },
    mergeLocal,
    () => { staleRollbackCount += 1; },
  );
  rejectOlderSelection(new Error("stale selection rejection"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(staleRollbackCount, 0, "An older rejection must not undo a newer selection success.");
  assert.equal(staleSelectionContainer.__hmbImageAssetLastPublishError, undefined);

  let rejectCleanupSelection;
  const cleanupSelectionPromise = new Promise((_resolve, reject) => {
    rejectCleanupSelection = reject;
  });
  const cleanupTransportContainer = { innerHTML: "mounted" };
  let cleanupRollbackCount = 0;
  assetWidget.hmbPublishImageAssetState(cleanupTransportContainer, {
    onChange() { return cleanupSelectionPromise; },
  }, mergeLocal, () => {
    cleanupRollbackCount += 1;
    cleanupTransportContainer.innerHTML = "restored";
  });
  // Cleanup invalidates the publication started by its forced flush before it
  // tears down the DOM. A late rejection must be inert.
  assetWidget.hmbInvalidateImageAssetPublication(cleanupTransportContainer);
  cleanupTransportContainer.innerHTML = "";
  rejectCleanupSelection(new Error("reject after cleanup"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(cleanupRollbackCount, 0);
  assert.equal(cleanupTransportContainer.innerHTML, "");
  assert.equal(cleanupTransportContainer.__hmbImageAssetLastPublishError, undefined);
} finally {
  console.error = originalConsoleError;
}

const installEventsSource = assetSource.match(
  /function installEvents\([\s\S]*?\n\}\n\nexport default function HMBImageAssetLibraryWidget/,
)?.[0] || "";
const toggleSource = installEventsSource.match(
  /const toggle = \(\) => \{[\s\S]*?\n    \};/,
)?.[0] || "";
assert.match(
  installEventsSource,
  /const assetsByLibraryId = new Map\(/,
  "Card event installation must build one linear-time lookup index.",
);
assert.doesNotMatch(
  installEventsSource,
  /state\.assets\.find\(/,
  "Per-card installation must not rescan the full asset list.",
);
assert.ok(
  toggleSource.indexOf("hmbApplyImageAssetSelectionFeedback(container, state)")
    < toggleSource.indexOf("hmbScheduleImageAssetSelectionCommit(container"),
  "Local card/tray feedback must precede host publication.",
);
assert.doesNotMatch(
  toggleSource,
  /remount\(state\)/,
  "Grid selection must not rebuild the complete 5,000-card DOM.",
);
assert.match(
  installEventsSource,
  /const selectedTray = container\.querySelector\("\.tray-scroll"\)[\s\S]*?on\(selectedTray, "dragstart"[\s\S]*?on\(selectedTray, "drop"[\s\S]*?on\(selectedTray, "click"/,
  "Delegated move/remove/drag handlers must survive tray-only replacement.",
);
assert.match(
  installEventsSource,
  /on\(container, "error"[\s\S]*?image\.closest/,
  "One capture listener must handle dynamically replaced thumbnail errors.",
);
assert.match(
  assetSource,
  /now >= autoSyncPendingUntil[\s\S]*?autoSyncPendingUntil = now \+ IMAGE_ASSET_AUTO_SYNC_PENDING_MS/,
  "Rapid auto-sync wakeups must not stack host round trips.",
);
assert.match(
  assetSource,
  /&& !container\.__hmbImageAssetSelectionCommitPending/,
  "Auto-sync must yield while a local selection commit is pending.",
);
assert.match(
  assetSource,
  /if \(baseValue && JSON\.stringify\(nextState\) === baseValue\)[\s\S]*?return;[\s\S]*?__hmbImageAssetPendingAuthoritativeProps = \{\s*state: nextState/,
  "Only an exact pre-click echo may be consumed; newer authority must be retained for selection-delta merge.",
);
assert.match(
  assetSource,
  /const remount = \(nextState = state\) => \{[\s\S]*?hmbFlushImageAssetSelectionCommit\(container\)/,
  "A remount must flush an optimistic selection instead of invalidating its callback.",
);
assert.match(
  assetSource,
  /const cleanup = \(\) => \{[\s\S]*?hmbInvalidateImageAssetPublication\(container\);[\s\S]*?hmbFlushImageAssetSelectionCommit\(container\)[\s\S]*?hmbInvalidateImageAssetPublication\(container\);[\s\S]*?disposed = true/,
  "Cleanup must flush a visible local selection, then invalidate the flush publication before releasing the mount.",
);
assert.match(
  toggleSource,
  /rollbackState = pending\.state[\s\S]*?emit\(props, publishedState, container, \(\) => \{\s*remount\(rollbackState\);/,
  "A latest selection transport failure must repaint the prior authoritative snapshot.",
);
assert.match(
  assetSource,
  /function runAutoSync\(\) \{[\s\S]*?try \{[\s\S]*?props\.onChange[\s\S]*?Promise\.resolve\(result\)\.then[\s\S]*?\} finally \{[\s\S]*?scheduleAutoSync\(nextDelay\);/,
  "Auto-sync throw/reject paths must always leave the next poll scheduled.",
);
assert.match(
  assetSource,
  /function emit\(props, state, container = null, onFailure = null\) \{\s*return hmbPublishImageAssetState\(container, props, state, onFailure\);/,
  "Every generic Image state emit must pass through the owner-guarded transport retry boundary.",
);
assert.match(
  assetSource,
  /Promise\.resolve\(result\)\.then\(\s*\(\) => settle\(\),\s*\(error\) => settle\(error\)/,
  "An asynchronous auto-sync rejection must be handled by the owned request settlement path.",
);
assert.match(
  assetSource,
  /const settle = \(error = null\) => \{[\s\S]*?if \(error\) \{[\s\S]*?scheduleAutoSync\(1000\);/,
  "A failed owned auto-sync request must replace the default poll with a bounded retry.",
);

console.log("HMB ImageAsset immediate feedback + no-remount performance regression: PASS");
