import assert from "node:assert/strict";
import fs from "node:fs";


const ASSET_WIDGET_PATH = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const assetSource = fs.readFileSync(ASSET_WIDGET_PATH, "utf8");
const assetWidget = await import(ASSET_WIDGET_PATH);


const makeSelectedTrayCard = (asset) => {
  const attributes = new Map([["data-selected-key", asset.asset_library_id]]);
  const classes = new Set(["selected-card"]);
  const control = () => ({
    disabled: false,
    attributes: new Map(),
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
    removeAttribute(name) { this.attributes.delete(name); },
  });
  const slot = { textContent: "" };
  const moveLeft = control();
  const moveRight = control();
  const remove = control();
  return {
    imageIdentity: {},
    parentTray: null,
    classList: {
      toggle(name, enabled) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
    },
    getAttribute(name) { return attributes.get(name) || ""; },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    querySelector(selector) {
      if (selector === ".slot") return slot;
      if (selector === '[data-move="-1"]') return moveLeft;
      if (selector === '[data-move="1"]') return moveRight;
      if (selector === "[data-remove-selected]") return remove;
      return null;
    },
    remove() { this.parentTray?.removeChild?.(this); },
  };
};

const makeSelectedTray = (scrollLeft = 0) => ({
  children: [],
  scrollLeft,
  querySelectorAll(selector) {
    return selector === "[data-selected-key]"
      ? this.children.filter((child) => child.getAttribute?.("data-selected-key"))
      : [];
  },
  querySelector(selector) {
    if (selector === ".tray-empty") {
      return this.children.find((child) => child.className === "tray-empty") || null;
    }
    return null;
  },
  appendChild(child) {
    this.removeChild(child);
    child.parentTray = this;
    this.children.push(child);
    return child;
  },
  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    if (child?.parentTray === this) child.parentTray = null;
  },
});

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
const tray = makeSelectedTray(19);
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

assetWidget.hmbApplyImageAssetSelectionFeedback(feedbackContainer, feedbackState, {
  createSelectedCard: makeSelectedTrayCard,
});
assert.equal(
  feedbackClasses.has("selected"),
  true,
  "A click must outline its card locally before the host round trip.",
);
assert.equal(feedbackAttributes.get("aria-pressed"), "true");
assert.equal(trayCount.textContent, "1/50");
assert.equal(
  tray.children[0]?.getAttribute?.("data-selected-key"),
  "asset-feedback",
  "A click must populate the selected tray locally.",
);
assert.equal(tray.scrollLeft, 19, "Local tray replacement must retain scroll position.");
assert.match(status.textContent, /1\/50 SEL/);
assert.deepEqual(
  feedbackState,
  assetWidget.hmbNormalizeImageAssetState(feedbackState),
  "Local feedback must remain canonical so an exact host echo skips remount.",
);
const canonicalStamp = assetWidget.hmbImageAssetAuthorityStamp(feedbackState);
const exactEchoContainer = {};
let exactEchoValue = "";
const publishedCanonical = assetWidget.hmbPublishImageAssetState(
  exactEchoContainer,
  { onChange(value) { exactEchoValue = value; } },
  feedbackState,
  null,
  { suppressMatchingEcho: true },
);
assert.equal(publishedCanonical, feedbackState, "A canonical local state must not be normalized again before publish.");
assert.equal(assetWidget.hmbImageAssetAuthorityStamp(publishedCanonical), canonicalStamp);
assert.equal(assetWidget.hmbConsumeImageAssetStateEcho(exactEchoContainer, { value: exactEchoValue }), true);
assert.equal(assetWidget.hmbConsumeImageAssetStateEcho(exactEchoContainer, { value: exactEchoValue }), false);
const manifestPollEcho = assetWidget.hmbImageAssetAutoSyncPayload(
  feedbackState,
  "manifest-poll-regression",
);
assert.equal(
  assetWidget.hmbIsImageAssetManifestPollEcho(manifestPollEcho),
  true,
  "The exact lightweight manifest envelope must be recognized before normalization.",
);
assert.equal(
  assetWidget.hmbIsImageAssetManifestPollEcho(JSON.parse(manifestPollEcho)),
  true,
  "Hosts that decode JSON before echoing must receive the same transport-only guard.",
);
assert.equal(
  assetWidget.hmbIsImageAssetManifestPollEcho(JSON.stringify({
    ...JSON.parse(manifestPollEcho),
    assets: [],
  })),
  false,
  "A canonical state carrying asset data must never be consumed as a lightweight echo.",
);
const oldCallback = () => "old";
const newCallback = () => "new";
const retainedProps = { value: exactEchoValue, onChange: oldCallback };
assert.equal(
  assetWidget.hmbUpdateImageAssetPropsReference(
    retainedProps,
    { value: manifestPollEcho, onChange: newCallback },
    true,
  ),
  retainedProps,
  "No-remount prop updates must retain the object captured by installed event handlers.",
);
assert.equal(retainedProps.value, exactEchoValue, "A poll echo must not replace canonical props.value.");
assert.equal(retainedProps.onChange, newCallback, "A poll echo must refresh the callback used by card events.");
assert.equal(
  assetWidget.hmbUpdateImageAssetPropsReference(retainedProps, { value: exactEchoValue }),
  retainedProps,
);
assert.equal(
  Object.hasOwn(retainedProps, "onChange"),
  false,
  "Stable prop identity must preserve replace semantics when the host removes a callback.",
);

// A production-sized catalog must keep the same bounded foreground work on
// clicks 3/6/9/12. The former path cloned and stringified all 5,000 records,
// touched every grid card, and rebuilt all selected thumbnail nodes per click.
const cadenceAssetCount = 5000;
const cadenceState = assetWidget.hmbNormalizeImageAssetState({
  project_root: "C:/cadence-project",
  project_id: "cadence-project",
  project_uid: "cadence-project-uid",
  assets: Array.from({ length: cadenceAssetCount }, (_, index) => ({
    asset_library_id: `cadence-${index}`,
    source_uid: `project:cadence-${index}`,
    source_kind: "project",
    asset_project_uid: "cadence-project-uid",
    registered: true,
    asset_id: `Cadence_${index}`,
    image_name: `Cadence ${index}`,
    selected: false,
    selection_order: 0,
  })),
});
let cadenceFullCardScans = 0;
let cadenceRootRemounts = 0;
const cadenceGridCards = cadenceState.assets.map((asset) => {
  const attributes = new Map([["data-asset-key", asset.asset_library_id]]);
  return {
    writes: 0,
    classList: { toggle() { this.owner.writes += 1; }, owner: null },
    getAttribute(name) { return attributes.get(name) || ""; },
    setAttribute(name, value) {
      attributes.set(name, String(value));
      this.writes += 1;
    },
  };
});
cadenceGridCards.forEach((card) => { card.classList.owner = card; });
const cadenceTray = makeSelectedTray(41);
const cadenceTrayCount = { textContent: "" };
const cadenceStatus = { textContent: "", setAttribute() {} };
const cadenceContainer = {
  querySelectorAll(selector) {
    if (selector === "[data-asset-key]") {
      cadenceFullCardScans += 1;
      return cadenceGridCards;
    }
    return [];
  },
  querySelector(selector) {
    if (selector === ".tray-scroll") return cadenceTray;
    if (selector === ".tray-head em") return cadenceTrayCount;
    if (selector === ".toolbar-status strong") return cadenceStatus;
    return null;
  },
};
Object.defineProperty(cadenceContainer, "innerHTML", {
  configurable: true,
  get() { return ""; },
  set() { cadenceRootRemounts += 1; },
});

const cadenceFrames = new Map();
const cadenceTimers = new Map();
let cadenceHandle = 0;
let cadencePublishCount = 0;
const cadenceSavedAnimationFrame = globalThis.requestAnimationFrame;
const cadenceSavedCancelAnimationFrame = globalThis.cancelAnimationFrame;
const cadenceSavedSetTimeout = globalThis.setTimeout;
const cadenceSavedClearTimeout = globalThis.clearTimeout;
globalThis.requestAnimationFrame = (callback) => {
  const id = ++cadenceHandle;
  cadenceFrames.set(id, callback);
  return id;
};
globalThis.cancelAnimationFrame = (id) => cadenceFrames.delete(id);
globalThis.setTimeout = (callback) => {
  const id = ++cadenceHandle;
  cadenceTimers.set(id, callback);
  return id;
};
globalThis.clearTimeout = (id) => cadenceTimers.delete(id);
try {
  let cadenceSelected = [];
  const retainedIdentity = new Map();
  const cadenceCheckpoints = [];
  for (let click = 1; click <= 12; click += 1) {
    const asset = cadenceState.assets[click - 1];
    const card = cadenceGridCards[click - 1];
    const previousSelectedCount = cadenceSelected.length;
    asset.selected = true;
    asset.selection_order = click;
    cadenceSelected = [...cadenceSelected, asset];
    card.writes = 0;
    const result = assetWidget.hmbApplyImageAssetSelectionFeedback(
      cadenceContainer,
      cadenceState,
      {
        changedAsset: asset,
        changedCard: card,
        previousSelectedCount,
        selectedAssets: cadenceSelected,
        createSelectedCard: makeSelectedTrayCard,
      },
    );
    assert.equal(result.cardScanCount, 0);
    assert.deepEqual(result.tray, { created: 1, removed: 0, retained: click - 1 });
    assert.equal(card.writes, 5, "Only the clicked grid card may receive selection writes.");
    cadenceTray.children.forEach((trayCard) => {
      const key = trayCard.getAttribute("data-selected-key");
      if (retainedIdentity.has(key)) {
        assert.equal(trayCard, retainedIdentity.get(key).card);
        assert.equal(trayCard.imageIdentity, retainedIdentity.get(key).image);
      } else {
        retainedIdentity.set(key, { card: trayCard, image: trayCard.imageIdentity });
      }
    });
    assetWidget.hmbScheduleImageAssetSelectionCommit(cadenceContainer, () => {
      cadencePublishCount += 1;
    });
    if (click % 3 === 0) {
      cadenceCheckpoints.push({
        click,
        cardWrites: card.writes,
        fullCardScans: cadenceFullCardScans,
        rootRemounts: cadenceRootRemounts,
        created: result.tray.created,
        removed: result.tray.removed,
      });
    }
  }
  while (cadenceFrames.size) {
    const [id, callback] = cadenceFrames.entries().next().value;
    cadenceFrames.delete(id);
    callback();
  }
  assert.equal(cadencePublishCount, 1, "Twelve rapid clicks must publish one coalesced state.");
  assert.equal(cadenceTimers.size, 0, "The successful commit must cancel its fallback timer.");
  assert.deepEqual(
    cadenceCheckpoints,
    [3, 6, 9, 12].map((click) => ({
      click,
      cardWrites: 5,
      fullCardScans: 0,
      rootRemounts: 0,
      created: 1,
      removed: 0,
    })),
    "Clicks 3/6/9/12 must retain identical bounded foreground work.",
  );
} finally {
  if (cadenceSavedAnimationFrame === undefined) delete globalThis.requestAnimationFrame;
  else globalThis.requestAnimationFrame = cadenceSavedAnimationFrame;
  if (cadenceSavedCancelAnimationFrame === undefined) delete globalThis.cancelAnimationFrame;
  else globalThis.cancelAnimationFrame = cadenceSavedCancelAnimationFrame;
  globalThis.setTimeout = cadenceSavedSetTimeout;
  globalThis.clearTimeout = cadenceSavedClearTimeout;
}

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
{
  let rootWrites = 0;
  let markup = "";
  const container = makeAutoSyncContainer();
  Object.defineProperty(container, "innerHTML", {
    configurable: true,
    get() { return markup; },
    set(value) {
      markup = String(value || "");
      rootWrites += 1;
    },
  });
  const authoritative = assetWidget.hmbNormalizeImageAssetState({
    catalog_root: "C:/projects",
    project_root: "C:/projects/project-a",
    project_id: "project-a",
    project_uid: "project-a-uid",
    manifest_signature: "manifest-stable",
    assets: [{
      asset_library_id: "poll-asset",
      source_uid: "project:poll-asset",
      source_kind: "project",
      registered: true,
      asset_id: "poll-asset",
      image_name: "Poll Asset",
    }],
  });
  const controller = assetWidget.default(container, { value: authoritative, onChange() {} });
  const writesAfterMount = rootWrites;
  const pollValue = assetWidget.hmbImageAssetAutoSyncPayload(
    authoritative,
    "manifest-poll-raw-host-echo",
  );
  controller.update({ value: pollValue, onChange() {} });
  assert.equal(
    rootWrites,
    writesAfterMount,
    "A raw optimistic manifest-poll echo must not empty and remount the asset grid.",
  );
  controller.update({ value: JSON.stringify(authoritative), onChange() {} });
  assert.equal(
    rootWrites,
    writesAfterMount,
    "The unchanged canonical response after a poll must also preserve DOM/image identity.",
  );
  const changedCanonical = assetWidget.hmbNormalizeImageAssetState({
    ...authoritative,
    manifest_signature: "manifest-changed",
    assets: [
      ...authoritative.assets,
      {
        asset_library_id: "poll-asset-new",
        source_uid: "project:poll-asset-new",
        source_kind: "project",
        registered: true,
        asset_id: "poll-asset-new",
        image_name: "New Poll Asset",
      },
    ],
  });
  controller.update({ value: JSON.stringify(changedCanonical), onChange() {} });
  assert.equal(
    rootWrites,
    writesAfterMount + 1,
    "A real canonical manifest change must still remount exactly once.",
  );
  controller.cleanup();
}
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
const ordinaryToggleSource = toggleSource.slice(
  0,
  toggleSource.indexOf("hmbScheduleImageAssetSelectionCommit(container"),
);
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
  toggleSource.indexOf("hmbApplyImageAssetSelectionFeedback(container, state")
    < toggleSource.indexOf("hmbScheduleImageAssetSelectionCommit(container"),
  "Local card/tray feedback must precede host publication.",
);
assert.doesNotMatch(
  ordinaryToggleSource,
  /normalizeState\(|JSON\.stringify\(|compactSelectionOrder\(|remount\(/,
  "Ordinary grid feedback must not clone state, stringify the catalog, compact 5,000 rows, or remount the dashboard.",
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
  /if \(!value\.slice\(0, 256\)\.includes\('"__hmb_manifest_poll_nonce"'\)\) return false;[\s\S]*?JSON\.parse\(value\)/,
  "Canonical catalog props must bypass the poll guard without another full JSON parse.",
);
assert.match(
  assetSource,
  /&& !container\.__hmbImageAssetSelectionCommitPending/,
  "Auto-sync must yield while a local selection commit is pending.",
);
assert.match(
  assetSource,
  /__hmbImageAssetSelectionBasePropValue[\s\S]*?nextProps\?\.value === container\.__hmbImageAssetSelectionBasePropValue[\s\S]*?return;[\s\S]*?__hmbImageAssetPendingAuthoritativeProps = \{\s*state: nextState/,
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
  /rollbackState = pending\.state[\s\S]*?if \(rollbackState\) \{\s*remount\(rollbackState\);[\s\S]*?hmbRestoreImageAssetSelectionSnapshot\(state, baseSelection\)/,
  "A latest selection transport failure must restore pending authority or the compact base selection snapshot.",
);
assert.match(
  assetSource,
  /function runAutoSync\(\) \{[\s\S]*?try \{[\s\S]*?props\.onChange[\s\S]*?Promise\.resolve\(result\)\.then[\s\S]*?\} finally \{[\s\S]*?scheduleAutoSync\(nextDelay\);/,
  "Auto-sync throw/reject paths must always leave the next poll scheduled.",
);
assert.match(
  assetSource,
  /function emit\(props, state, container = null, onFailure = null, options = \{\}\) \{\s*return hmbPublishImageAssetState\(container, props, state, onFailure, options\);/,
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
