import assert from "node:assert/strict";
import fs from "node:fs";


const ASSET_WIDGET_PATH = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const THUMBNAIL_BRIDGE_WIDGET_PATH = new URL(
  "../../widgets/HMBImageAssetThumbnailPatchBridgeWidget.js",
  import.meta.url,
);
const assetSource = fs.readFileSync(ASSET_WIDGET_PATH, "utf8");
const assetWidget = await import(ASSET_WIDGET_PATH);
const thumbnailBridgeWidget = await import(THUMBNAIL_BRIDGE_WIDGET_PATH);


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
assert.match(status.textContent, /1\/50 (?:SEL|선택)/);
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

const presentationState = assetWidget.hmbNormalizeImageAssetState({
  project_uid: "presentation-project",
  manifest_signature: "presentation-manifest",
  scan_revision: 5,
  ui_edit_revision: 7,
});
const presentationContainer = {};
let presentationEcho = "";
assetWidget.hmbPublishImageAssetState(
  presentationContainer,
  { onChange(value) { presentationEcho = value; } },
  presentationState,
  null,
  { suppressMatchingEcho: true, preserveUiEditRevision: true },
);
assert.equal(JSON.parse(presentationEcho).ui_edit_revision, 7);
assert.equal(presentationContainer.__hmbImageAssetCurrentUiEditRevision, 7);
assert.equal(
  assetWidget.hmbConsumeImageAssetStateEcho(presentationContainer, { value: presentationEcho }),
  true,
  "A presentation-only request must retain exact-echo suppression without advancing UI authority.",
);
const presentationFailureState = assetWidget.hmbNormalizeImageAssetState({
  ...presentationState,
  ui_edit_revision: 8,
});
const presentationFailureContainer = {};
let presentationFailureCount = 0;
const savedPresentationConsoleError = console.error;
console.error = () => {};
try {
  assetWidget.hmbPublishImageAssetState(
    presentationFailureContainer,
    { onChange() { throw new Error("presentation transport failure"); } },
    presentationFailureState,
    () => { presentationFailureCount += 1; },
    { preserveUiEditRevision: true },
  );
} finally {
  console.error = savedPresentationConsoleError;
}
assert.equal(presentationFailureCount, 1);
assert.equal(presentationFailureState.ui_edit_revision, 8);
assert.equal(presentationFailureContainer.__hmbImageAssetCurrentUiEditRevision, 8);

// Card selection and view/type controls can publish faster than retained-mode
// props arrive. Serialized UI revisions make B -> late A deterministic even
// after the short exact-echo timer has discarded all payload history.
const rapidCardBase = {
  scan_revision: 7,
  asset_view_mode: "image",
  assets: [{
    asset_library_id: "rapid-card",
    source_uid: "project:rapid-card",
    source_kind: "project",
    registered: true,
    asset_id: "RapidCard",
    image_name: "Rapid Card Source",
    extension: ".png",
    source_type: "Character Appearance",
    selected: false,
  }],
};
const rapidCardSelected = {
  ...rapidCardBase,
  asset_view_mode: "detail",
  assets: [{ ...rapidCardBase.assets[0], selected: true, selection_order: 1 }],
};
const rapidContainer = {};
const rapidValues = [];
for (const rapidState of [rapidCardBase, rapidCardSelected]) {
  assetWidget.hmbPublishImageAssetState(
    rapidContainer,
    { onChange(value) { rapidValues.push(value); } },
    assetWidget.hmbNormalizeImageAssetState(rapidState),
    null,
    { suppressMatchingEcho: true },
  );
}
const [rapidAValue, rapidBValue] = rapidValues;
const rapidAState = JSON.parse(rapidAValue);
const rapidBState = JSON.parse(rapidBValue);
assert.equal(rapidAState.ui_edit_revision + 1, rapidBState.ui_edit_revision);
assert.equal(rapidAState.assets[0].selected, false);
assert.equal(rapidBState.assets[0].selected, true);
assert.equal(rapidBState.asset_view_mode, "detail");
assert.equal(
  assetWidget.hmbConsumeImageAssetStateEcho(rapidContainer, { value: rapidBValue }),
  true,
  "The newer card/type state B must consume its exact host acknowledgement.",
);
assert.equal(
  assetWidget.hmbConsumeImageAssetStateEcho(rapidContainer, { value: rapidAValue }),
  true,
  "Late card/type state A must not roll back or remount the selected card.",
);
assert.equal(rapidContainer.__hmbImageAssetLastConsumedEchoWasStale, true);

const nativeSetTimeout = globalThis.setTimeout;
const nativeClearTimeout = globalThis.clearTimeout;
const revisionTimers = new Map();
let revisionTimerId = 0;
globalThis.setTimeout = (callback, delay) => {
  const id = ++revisionTimerId;
  revisionTimers.set(id, { callback, delay });
  return id;
};
globalThis.clearTimeout = (id) => revisionTimers.delete(id);
try {
  const delayedContainer = {};
  const delayedValues = [];
  for (const rapidState of [rapidCardBase, rapidCardSelected]) {
    assetWidget.hmbPublishImageAssetState(
      delayedContainer,
      { onChange(value) { delayedValues.push(value); } },
      assetWidget.hmbNormalizeImageAssetState(rapidState),
      null,
      { suppressMatchingEcho: true },
    );
  }
  const echoCleanup = [...revisionTimers.values()].find((timer) => timer.delay === 1500);
  assert.ok(echoCleanup, "ImageAsset exact-echo history must remain time bounded.");
  echoCleanup.callback();
  assert.equal(delayedContainer.__hmbImageAssetPendingStateEchoes, undefined);
  assert.equal(
    assetWidget.hmbConsumeImageAssetStateEcho(
      delayedContainer,
      { value: delayedValues[0] },
    ),
    true,
    "A lower UI revision must remain stale beyond the 1500ms echo TTL.",
  );

  const currentState = JSON.parse(delayedValues[1]);
  const higherScan = assetWidget.hmbNormalizeImageAssetState({
    ...currentState,
    scan_revision: 8,
    ui_edit_revision: 0,
  });
  assert.equal(
    assetWidget.hmbConsumeImageAssetStateEcho(
      delayedContainer,
      { value: JSON.stringify(higherScan) },
    ),
    false,
    "A higher catalog scan revision must remain authoritative.",
  );
} finally {
  globalThis.setTimeout = nativeSetTimeout;
  globalThis.clearTimeout = nativeClearTimeout;
}

const lowerScanContainer = {};
assetWidget.hmbPublishImageAssetState(
  lowerScanContainer,
  { onChange() {} },
  assetWidget.hmbNormalizeImageAssetState({ ...rapidCardSelected, scan_revision: 9 }),
  null,
  { suppressMatchingEcho: true },
);
const lowerScanHigherUi = assetWidget.hmbNormalizeImageAssetState({
  ...rapidCardBase,
  scan_revision: 8,
  ui_edit_revision: 999,
});
assert.equal(
  assetWidget.hmbConsumeImageAssetStateEcho(
    lowerScanContainer,
    { value: JSON.stringify(lowerScanHigherUi) },
  ),
  true,
  "A lower scan revision must be stale even when it carries a higher UI revision.",
);
clearTimeout(lowerScanContainer.__hmbImageAssetStateEchoTimer);

const higherUiContainer = {};
const higherUiValues = [];
assetWidget.hmbPublishImageAssetState(
  higherUiContainer,
  { onChange(value) { higherUiValues.push(value); } },
  assetWidget.hmbNormalizeImageAssetState(rapidCardBase),
  null,
  { suppressMatchingEcho: true },
);
const higherUiBase = JSON.parse(higherUiValues[0]);
const higherUiState = assetWidget.hmbNormalizeImageAssetState({
  ...higherUiBase,
  asset_view_mode: "detail",
  ui_edit_revision: higherUiBase.ui_edit_revision + 1,
});
assert.equal(
  assetWidget.hmbConsumeImageAssetStateEcho(
    higherUiContainer,
    { value: JSON.stringify(higherUiState) },
  ),
  false,
  "A higher UI edit revision at the current scan must remain authoritative.",
);

const oldCallback = () => "old";
const newCallback = () => "new";
const retainedProps = { value: exactEchoValue, onChange: oldCallback };
assert.equal(
  assetWidget.hmbUpdateImageAssetPropsReference(
    retainedProps,
    { value: "newer-authoritative-value", onChange: newCallback },
    true,
  ),
  retainedProps,
  "No-remount prop updates must retain the object captured by installed event handlers.",
);
assert.equal(retainedProps.value, exactEchoValue, "A no-remount update must retain canonical props.value.");
assert.equal(retainedProps.onChange, newCallback, "A no-remount update must refresh the callback used by card events.");
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
  const languageToggleListeners = new Map();
  const languageToggle = {
    isConnected: true,
    addEventListener(type, handler) { languageToggleListeners.set(type, handler); },
    removeEventListener(type, handler) {
      if (languageToggleListeners.get(type) === handler) languageToggleListeners.delete(type);
    },
  };
  const container = makeAutoSyncContainer();
  container.querySelector = (selector) => (
    selector === "[data-language-toggle]" ? languageToggle : null
  );
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
  controller.update({ value: JSON.stringify(authoritative), onChange() {} });
  assert.equal(
    rootWrites,
    writesAfterMount,
    "An unchanged canonical host echo must preserve DOM/image identity.",
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
    writesAfterMount,
    "A real canonical manifest change must patch without replacing the widget root.",
  );
  assert.equal(container.__hmbImageAssetLatestState.manifest_signature, "manifest-changed");
  assert.equal(container.__hmbImageAssetLatestState.assets.length, 2);

  const rapidMountedValues = [];
  const mountedA = assetWidget.hmbNormalizeImageAssetState({
    ...changedCanonical,
    asset_view_mode: "image",
  });
  const mountedB = assetWidget.hmbNormalizeImageAssetState({
    ...changedCanonical,
    asset_view_mode: "detail",
    assets: changedCanonical.assets.map((asset, index) => ({
      ...asset,
      selected: index === 0,
      selection_order: index === 0 ? 1 : 0,
    })),
  });
  assetWidget.hmbPublishImageAssetState(
    container,
    { onChange(value) { rapidMountedValues.push(value); } },
    mountedA,
    null,
    { suppressMatchingEcho: true },
  );
  assetWidget.hmbPublishImageAssetState(
    container,
    { onChange(value) { rapidMountedValues.push(value); } },
    mountedB,
    null,
    { suppressMatchingEcho: true },
  );
  const writesBeforeRapidEchoes = rootWrites;
  let newerCallbackCalls = 0;
  let staleCallbackCalls = 0;
  controller.update({
    value: rapidMountedValues[1],
    onChange() { newerCallbackCalls += 1; },
  });
  controller.update({
    value: rapidMountedValues[0],
    onChange() { staleCallbackCalls += 1; },
  });
  assert.equal(
    rootWrites,
    writesBeforeRapidEchoes,
    "Mounted B then delayed A props must preserve the current card DOM without another remount.",
  );
  assert.equal(container.querySelector("[data-language-toggle]"), languageToggle);
  assert.equal(languageToggle.isConnected, true, "A delayed echo must retain the mounted control identity.");
  assert.equal(container.__hmbImageAssetLastConsumedEchoWasStale, true);
  languageToggleListeners.get("click")?.({ preventDefault() {}, stopPropagation() {} });
  assert.equal(newerCallbackCalls, 1, "The next card action must use B's newest host callback.");
  assert.equal(staleCallbackCalls, 0, "A delayed A echo must not restore its obsolete callback.");
  controller.cleanup();
}
const verifyNoBackgroundAutoSyncPolling = () => {
  const timers = new Map();
  let timerSequence = 0;
  const savedSetTimeout = globalThis.setTimeout;
  const savedClearTimeout = globalThis.clearTimeout;
  globalThis.setTimeout = (callback, delay = 0) => {
    const id = ++timerSequence;
    timers.set(id, { callback, delay: Number(delay) || 0 });
    return id;
  };
  globalThis.clearTimeout = (id) => timers.delete(id);
  const container = makeAutoSyncContainer();
  let calls = 0;
  let mounted;
  try {
    mounted = assetWidget.default(container, {
      value: { project_root: "C:/project", catalog_root: "C:/project" },
      onChange() { calls += 1; },
    });
    assert.equal(calls, 0, "Mounting must not publish an unsolicited catalog poll.");
    assert.equal(timers.size, 0, "The widget must not leave background auto-sync timers running.");
  } finally {
    try { mounted?.cleanup?.(); } catch (_error) {}
    globalThis.setTimeout = savedSetTimeout;
    globalThis.clearTimeout = savedClearTimeout;
  }
};
verifyNoBackgroundAutoSyncPolling();

const selectableAsset = (id, selected = false, order = 0, extra = {}) => ({
  asset_library_id: id,
  source_uid: `project:${id}`,
  source_kind: "project",
  registered: true,
  asset_id: id,
  image_name: id,
  relative_path: `Assets/${id}.png`,
  selected,
  selection_order: order,
  ...extra,
});

// Foreground catalog work is a 60-card page. Selected assets take thumbnail
// priority even when they live outside that page, and browser-safe media does
// not enter the hydration queue.
const thumbnailWindowState = assetWidget.hmbNormalizeImageAssetState({
  project_uid: "thumbnail-window-project",
  manifest_signature: "thumbnail-window-manifest",
  scan_revision: 11,
  assets: Array.from({ length: 70 }, (_value, index) => selectableAsset(
    `thumbnail-window-${index}`,
    index === 65 || index === 69,
    index === 65 ? 1 : index === 69 ? 2 : 0,
    index === 2
      ? { thumbnail_url: "https://static.invalid/already-hydrated.webp" }
      : index === 3
        ? { path: "https://static.invalid/browser-safe.png" }
        : {},
  )),
});
assert.equal(assetWidget.hmbImageAssetCatalogWindow(thumbnailWindowState).rendered.length, 60);
assert.equal(assetWidget.hmbImageAssetCatalogWindow(thumbnailWindowState, 60, 60).rendered.length, 10);
const thumbnailWindowIds = assetWidget.hmbImageAssetThumbnailRequestIds(thumbnailWindowState);
assert.deepEqual(
  thumbnailWindowIds.slice(0, 2),
  ["thumbnail-window-65", "thumbnail-window-69"],
  "Selected assets outside the page must lead the staged-thumbnail batch.",
);
assert.equal(thumbnailWindowIds.includes("thumbnail-window-2"), false);
assert.equal(thumbnailWindowIds.includes("thumbnail-window-3"), false);
const userAssetEligibilityState = assetWidget.hmbNormalizeImageAssetState({
  project_uid: "thumbnail-window-project",
  manifest_signature: "thumbnail-window-manifest",
  scan_revision: 11,
  selected_source_view: "user",
  assets: [
    selectableAsset("thumbnail-window-persisted-user", true, 1, {
      source_kind: "user",
      import_index: 0,
      relative_path: "User/thumbnail-window-persisted-user.png",
    }),
    selectableAsset("thumbnail-window-live-user", true, 2, {
      source_kind: "user",
      import_index: 1,
      relative_path: "User/thumbnail-window-live-user.png",
    }),
    selectableAsset("thumbnail-window-unpersisted-user", true, 3, {
      source_kind: "user",
      import_index: 0,
      relative_path: "",
    }),
  ],
});
assert.deepEqual(
  assetWidget.hmbImageAssetThumbnailRequestIds(userAssetEligibilityState),
  ["thumbnail-window-persisted-user"],
  "Persisted User-folder assets hydrate, while live/unpersisted IMAGE_IMPORT_IN rows do not.",
);
assert.equal(new Set(thumbnailWindowIds).size, thumbnailWindowIds.length);
const thumbnailPlaceholderMarkup = assetWidget.hmbRenderImageAssetGrid(
  thumbnailWindowState,
).markup;
assert.match(thumbnailPlaceholderMarkup, /thumbnail-loading/);
assert.match(thumbnailPlaceholderMarkup, /asset-thumb-placeholder/);

// The staged placeholder is an inert eight-leaf clockwise indicator, never
// the retired full-card shimmer. Keep the visual contract deterministic so a
// later CSS cleanup cannot silently restore the expensive flashing overlay.
const oneLoaderMarkup = assetWidget.hmbRenderImageAssetGrid(
  assetWidget.hmbNormalizeImageAssetState({
    project_uid: "leaf-loader-project",
    assets: [selectableAsset("leaf-loader")],
  }),
).markup;
assert.deepEqual(
  Array.from(oneLoaderMarkup.matchAll(/--leaf-index:(\d+)/g), (match) => Number(match[1])),
  [0, 1, 2, 3, 4, 5, 6, 7],
  "Every missing thumbnail must render exactly eight ordered leaves.",
);
assert.match(assetSource, /--leaf-angle:calc\(var\(--leaf-index\) \* 45deg\)/);
assert.match(assetSource, /animation-delay:calc\(var\(--leaf-index\) \* \.125s\)/);
assert.match(
  assetSource,
  /\.hmb-image-leaf-loader\{[^}]*pointer-events:none/,
  "The loader may not intercept card click or drag hit-testing.",
);
assert.match(
  assetSource,
  /\.thumbnail-loading \.thumbnail-placeholder,[^\n]*display:grid!important/,
  "The loader wrapper must remain centered despite legacy fallback display rules.",
);
assert.match(
  assetSource,
  /\.hmb-image-leaf-loader\{[^}]*display:block!important/,
  "The fixed-size leaf ring must not collapse as an inline span.",
);
assert.match(assetSource, /@media \(prefers-reduced-motion:reduce\)[\s\S]*?\.hmb-image-leaf-loader>i\{animation:none/);
assert.doesNotMatch(assetSource, /@keyframes hmb-image-thumbnail-loading|background-position:120%/);

// Exercise the real hidden bridge widget, not a hand-built request object.
// Request and result share one schema and runtime identity; duplicate/stale
// results are never delivered to the mounted ImageAsset consumer.
const bridgeRuntimeId = "thumbnail-bridge-runtime";
const bridgeRegistry = thumbnailBridgeWidget.hmbImageAssetThumbnailPatchBridgeRegistry();
bridgeRegistry.clear();
const deliveredBridgeResults = [];
bridgeRegistry.set(bridgeRuntimeId, {
  consumer(value) { deliveredBridgeResults.push(value); },
  consumerToken: "test-consumer",
});
const bridgeStyles = new Map();
const bridgeAttributes = new Map();
const bridgeContainer = {
  style: {
    setProperty(name, value, priority) {
      bridgeStyles.set(name, { value, priority });
    },
  },
  setAttribute(name, value) { bridgeAttributes.set(name, String(value)); },
};
const bridgePublished = [];
const bridgeController = thumbnailBridgeWidget.default(bridgeContainer, {
  value: {
    schema: "hmb-image-asset-thumbnail-bridge",
    version: 1,
    runtime_instance_id: bridgeRuntimeId,
    operation: "idle",
    phase: "idle",
    request_id: "",
  },
  onChange(value) { bridgePublished.push(value); },
});
assert.equal(bridgeAttributes.get("aria-hidden"), "true");
assert.equal(bridgeStyles.get("pointer-events")?.value, "none");
const liveBridge = bridgeRegistry.get(bridgeRuntimeId);
assert.equal(typeof liveBridge?.dispatch, "function");
liveBridge.dispatch({
  runtime_instance_id: bridgeRuntimeId,
  request_id: "bridge-request",
  project_uid: "bridge-project",
  manifest_signature: "bridge-manifest",
  scan_revision: 7,
  asset_library_ids: ["bridge-a", "bridge-a", "bridge-b"],
});
assert.deepEqual(bridgePublished, [{
  schema: "hmb-image-asset-thumbnail-bridge",
  version: 1,
  operation: "hydrate",
  phase: "request",
  runtime_instance_id: bridgeRuntimeId,
  request_id: "bridge-request",
  project_uid: "bridge-project",
  manifest_signature: "bridge-manifest",
  scan_revision: 7,
  asset_library_ids: ["bridge-a", "bridge-b"],
}]);
const bridgeResult = {
  schema: "hmb-image-asset-thumbnail-bridge",
  version: 1,
  operation: "hydrate",
  phase: "result",
  runtime_instance_id: bridgeRuntimeId,
  request_id: "bridge-request",
  project_uid: "bridge-project",
  manifest_signature: "bridge-manifest",
  scan_revision: 7,
  thumbnail_revision: 1,
  completed_assets: [],
  failed_asset_library_ids: [],
};
bridgeController.update({ value: bridgeResult, onChange() {} });
bridgeController.update({ value: bridgeResult, onChange() {} });
bridgeController.update({
  value: { ...bridgeResult, runtime_instance_id: "stale-runtime", thumbnail_revision: 2 },
  onChange() {},
});
assert.deepEqual(deliveredBridgeResults, [bridgeResult]);
bridgeController.cleanup();
assert.equal(typeof bridgeRegistry.get(bridgeRuntimeId)?.dispatch, "undefined");
assert.equal(typeof bridgeRegistry.get(bridgeRuntimeId)?.consumer, "function");
assert.equal(
  bridgeRegistry.get(bridgeRuntimeId)?.consumerToken,
  "test-consumer",
  "Bridge-first cleanup must preserve main-consumer ownership for later teardown.",
);
if (bridgeRegistry.get(bridgeRuntimeId)?.consumerToken === "test-consumer") {
  bridgeRegistry.delete(bridgeRuntimeId);
}
assert.equal(
  bridgeRegistry.has(bridgeRuntimeId),
  false,
  "The later main-consumer cleanup must be able to release the runtime entry.",
);
bridgeRegistry.clear();

// With retained indexes already built, thumbnail completion is O(K): only the
// addressed card is visited and the widget root is neither searched nor
// replaced. A tiny DOM double is sufficient because this path must preserve
// the existing card/root identities and morph only the thumbnail fragment.
function thumbnailElement(className = "asset-thumb thumbnail-loading") {
  const values = new Map([["class", className]]);
  return {
    nodeType: 1,
    tagName: "DIV",
    childNodes: [],
    firstChild: null,
    parentNode: null,
    get attributes() {
      return Array.from(values, ([name, value]) => ({ name, value }));
    },
    getAttribute(name) { return values.get(name) ?? null; },
    hasAttribute(name) { return values.has(name); },
    setAttribute(name, value) { values.set(name, String(value)); },
    removeAttribute(name) { values.delete(name); },
    matches() { return false; },
  };
}
const targetThumbnail = thumbnailElement();
const untouchedThumbnail = thumbnailElement("asset-thumb untouched");
const targetCard = {
  querySelector(selector) {
    assert.equal(selector, ".asset-thumb");
    return targetThumbnail;
  },
};
let untouchedCardQueries = 0;
const untouchedCard = {
  querySelector() {
    untouchedCardQueries += 1;
    return untouchedThumbnail;
  },
};
const patchOwnerDocument = {
  createElement(tagName) {
    assert.equal(tagName, "template");
    const template = { content: { firstElementChild: null } };
    Object.defineProperty(template, "innerHTML", {
      set(markup) {
        const className = String(markup).match(/class="([^"]+)"/)?.[1] || "asset-thumb";
        template.content.firstElementChild = thumbnailElement(className);
      },
    });
    return template;
  },
};
targetThumbnail.ownerDocument = patchOwnerDocument;
untouchedThumbnail.ownerDocument = patchOwnerDocument;
let rootSearches = 0;
let rootReplacements = 0;
const targetOnlyContainer = {
  __hmbImageAssetByLibraryId: new Map(),
  __hmbImageAssetCardByLibraryId: new Map([
    ["patch-target", targetCard],
    ["patch-untouched", untouchedCard],
  ]),
  __hmbImageAssetSelectedCardByLibraryId: new Map(),
  __hmbImageAssetCompactCardsByLibraryId: new Map(),
  querySelectorAll() {
    rootSearches += 1;
    throw new Error("Indexed thumbnail completion performed a full DOM search.");
  },
  set innerHTML(_value) { rootReplacements += 1; },
};
const targetOnlyState = assetWidget.hmbNormalizeImageAssetState({
  project_uid: "target-only-project",
  assets: [
    selectableAsset("patch-target", false, 0, { thumbnail_url: "data:image/png;base64,AA==" }),
    selectableAsset("patch-untouched", false, 0, { thumbnail_url: "data:image/png;base64,BB==" }),
  ],
});
targetOnlyState.assets.forEach((asset) => {
  targetOnlyContainer.__hmbImageAssetByLibraryId.set(asset.asset_library_id, asset);
});
assert.equal(
  assetWidget.hmbPatchImageAssetThumbnailMedia(
    targetOnlyContainer,
    targetOnlyState,
    ["patch-target"],
  ),
  1,
);
assert.equal(rootSearches, 0);
assert.equal(rootReplacements, 0);
assert.equal(untouchedCardQueries, 0);
assert.equal(untouchedThumbnail.getAttribute("class"), "asset-thumb untouched");

// The compact thumbnail-only transition must be selected before the legacy
// whole-state stringify comparison; otherwise large catalogs still pay the
// serialization cost on every worker completion.
const applyPropsStart = assetSource.indexOf("const applyProps = (nextProps = {}) => {");
const applyPropsEnd = assetSource.indexOf("const cleanup = () => {", applyPropsStart);
const applyPropsSource = assetSource.slice(applyPropsStart, applyPropsEnd);
assert.ok(applyPropsStart >= 0 && applyPropsEnd > applyPropsStart);
assert.ok(
  applyPropsSource.indexOf("imageAssetThumbnailOnlyTransition(")
    < applyPropsSource.indexOf("const currentValue = JSON.stringify(state)"),
  "Thumbnail-only fast path must precede whole-state serialization.",
);
assert.match(
  applyPropsSource,
  /presentationPatch\.changedAssetLibraryIds/,
  "Compact failed IDs must patch their existing cards, not leave loaders spinning.",
);
assert.match(
  applyPropsSource,
  /const completed = hmbImageAssetThumbnailResultIds\(merged\)/,
  "Full-state thumbnail completion must patch both completed and failed cards.",
);
assert.match(
  assetSource,
  /hmbArmImageAssetThumbnailWatchdog\(container, current, props, bridgeRequest\);/,
  "Every dispatched hydration request must arm the lost-response watchdog.",
);
assert.match(
  assetSource,
  /thumbnail-failed[\s\S]*?hmb-image-thumbnail-unavailable/,
  "Terminal failures must render a static marker instead of an animated leaf loader.",
);
assert.ok(
  applyPropsSource.indexOf("if (nextProps?.value === previousPropValue)")
    < applyPropsSource.indexOf("const incomingState = normalizeState(nextProps?.value)"),
  "A callback-only same-value update must return before full catalog normalization.",
);
const consumeEchoStart = assetSource.indexOf(
  "export function hmbConsumeImageAssetStateEcho(container, nextProps = {}) {",
);
const consumeEchoEnd = assetSource.indexOf(
  "export function hmbPublishImageAssetState(",
  consumeEchoStart,
);
const consumeEchoSource = assetSource.slice(consumeEchoStart, consumeEchoEnd);
assert.ok(consumeEchoStart >= 0 && consumeEchoEnd > consumeEchoStart);
assert.ok(
  consumeEchoSource.indexOf("if (!Array.isArray(pending) || !pending.length)")
    < consumeEchoSource.indexOf("incoming = JSON.stringify(incomingState)"),
  "Echo matching must not serialize a full catalog when no echo is pending.",
);
assert.match(
  applyPropsSource,
  /const incomingSerialized = container\.__hmbImageAssetIncomingSerialized;[\s\S]*?const nextValue = typeof incomingSerialized === "string"[\s\S]*?\? incomingSerialized[\s\S]*?: JSON\.stringify\(nextState\)/,
  "A non-matching echo serialization must be reused by the ordinary state comparison.",
);

// A delayed thumbnail worker response may patch thumbnail_url only. Local
// selection, per-Shot ordering, dimensions, names, and every other semantic
// field remain owned by the latest UI/catalog state.
const thumbnailShotUuid = "11111111-1111-4111-8111-111111111111";
const thumbnailMergeLocal = assetWidget.hmbNormalizeImageAssetState({
  project_uid: "thumbnail-merge-project",
  manifest_signature: "thumbnail-merge-manifest",
  scan_revision: 12,
  ui_edit_revision: 9,
  thumbnail_revision: 3,
  assets: [
    selectableAsset("thumbnail-merge-a", true, 1, {
      image_name: "Local A",
      media_signature: "a".repeat(64),
      width: 640,
      height: 360,
      relative_path: "local/a.png",
    }),
    selectableAsset("thumbnail-merge-b", true, 2, {
      image_name: "Local B",
      media_signature: "b".repeat(64),
      width: 800,
      height: 450,
      relative_path: "local/b.png",
    }),
  ],
  shot_routing: {
    schema: "hmb-shot-routing",
    version: 1,
    channel_uuid: "22222222-2222-4222-8222-222222222222",
    active_shot_uuid: thumbnailShotUuid,
    revision: 7,
    shots: [{
      shot_uuid: thumbnailShotUuid,
      number: 1,
      name: "Local Shot",
      name_is_custom: true,
      revision: 5,
      selected_source_uids: ["project:thumbnail-merge-b", "project:thumbnail-merge-a"],
    }],
  },
});
const thumbnailMergeIncoming = assetWidget.hmbNormalizeImageAssetState({
  ...JSON.parse(JSON.stringify(thumbnailMergeLocal)),
  ui_edit_revision: 4,
  thumbnail_revision: 4,
  thumbnail_busy: false,
  thumbnail_request: {},
  thumbnail_result: {
    request_id: "thumbnail-merge-request",
    project_uid: "thumbnail-merge-project",
    manifest_signature: "thumbnail-merge-manifest",
    scan_revision: 12,
    completed_asset_library_ids: ["thumbnail-merge-a"],
    failed_asset_library_ids: [],
  },
  assets: thumbnailMergeLocal.assets.map((asset) => ({
    ...asset,
    thumbnail_url: `https://static.invalid/${asset.asset_library_id}.webp`,
    selected: false,
    selection_order: 0,
    width: 9999,
    height: 9999,
    image_name: `Worker ${asset.asset_library_id}`,
    relative_path: "worker/changed.png",
  })),
  shot_routing: {},
});
const thumbnailMerged = assetWidget.hmbMergeImageAssetThumbnailResponse(
  thumbnailMergeLocal,
  thumbnailMergeIncoming,
);
assert.equal(
  thumbnailMerged.assets[0].thumbnail_url,
  "https://static.invalid/thumbnail-merge-a.webp",
);
assert.equal(thumbnailMerged.assets[1].thumbnail_url, "");
assert.deepEqual(
  thumbnailMerged.assets.map((asset) => ({
    selected: asset.selected,
    selection_order: asset.selection_order,
    width: asset.width,
    height: asset.height,
    image_name: asset.image_name,
    media_signature: asset.media_signature,
    relative_path: asset.relative_path,
  })),
  thumbnailMergeLocal.assets.map((asset) => ({
    selected: asset.selected,
    selection_order: asset.selection_order,
    width: asset.width,
    height: asset.height,
    image_name: asset.image_name,
    media_signature: asset.media_signature,
    relative_path: asset.relative_path,
  })),
  "Thumbnail hydration must not overwrite semantic asset fields or generator order.",
);
assert.deepEqual(thumbnailMerged.shot_routing, thumbnailMergeLocal.shot_routing);
{
  const staleThumbnailContainer = makeAutoSyncContainer();
  const staleThumbnailController = assetWidget.default(staleThumbnailContainer, {
    value: thumbnailMergeLocal,
  });
  staleThumbnailController.update({ value: thumbnailMergeIncoming });
  const applied = staleThumbnailContainer.__hmbImageAssetLatestState;
  assert.equal(
    applied.assets[0].thumbnail_url,
    "https://static.invalid/thumbnail-merge-a.webp",
    "Mounted applyProps must accept a newer thumbnail revision from a UI-stale response.",
  );
  assert.deepEqual(applied.shot_routing, thumbnailMergeLocal.shot_routing);
  assert.deepEqual(
    assetWidget.hmbImageAssetSelectionSnapshot(applied),
    assetWidget.hmbImageAssetSelectionSnapshot(thumbnailMergeLocal),
  );

  // A publisher/channel reset is semantic Shot authority, not thumbnail-only
  // presentation. It must take the normal remount path so the bridge and Shot
  // registry cannot retain the previous runtime identity.
  const resetPublisherUuid = "33333333-3333-4333-8333-333333333333";
  const resetChannelUuid = "44444444-4444-4444-8444-444444444444";
  const authorityResetIncoming = assetWidget.hmbNormalizeImageAssetState({
    ...JSON.parse(JSON.stringify(applied)),
    thumbnail_revision: applied.thumbnail_revision + 1,
    thumbnail_result: {
      ...applied.thumbnail_result,
      request_id: "thumbnail-authority-reset",
    },
    shot_routing: {
      ...JSON.parse(JSON.stringify(applied.shot_routing)),
      publisher_instance_uuid: resetPublisherUuid,
      channel_uuid: resetChannelUuid,
    },
  });
  staleThumbnailController.update({ value: authorityResetIncoming });
  assert.equal(
    staleThumbnailContainer.__hmbImageAssetLatestState.shot_routing.publisher_instance_uuid,
    resetPublisherUuid,
  );
  assert.equal(
    staleThumbnailContainer.__hmbImageAssetLatestState.shot_routing.channel_uuid,
    resetChannelUuid,
  );
  staleThumbnailController.cleanup();
}
const mismatchedThumbnailResponse = assetWidget.hmbMergeImageAssetThumbnailResponse(
  thumbnailMergeLocal,
  {
    ...thumbnailMergeIncoming,
    thumbnail_revision: 5,
    thumbnail_result: { ...thumbnailMergeIncoming.thumbnail_result, scan_revision: 10 },
  },
);
assert.equal(mismatchedThumbnailResponse.thumbnail_revision, 3);
assert.equal(mismatchedThumbnailResponse.assets[0].thumbnail_url, "");
const mismatchedThumbnailIdentity = assetWidget.hmbMergeImageAssetThumbnailResponse(
  thumbnailMergeLocal,
  {
    ...thumbnailMergeIncoming,
    thumbnail_revision: 5,
    assets: thumbnailMergeIncoming.assets.map((asset, index) => ({
      ...asset,
      media_signature: index === 0 ? "c".repeat(64) : asset.media_signature,
    })),
  },
);
assert.equal(
  mismatchedThumbnailIdentity.assets[0].thumbnail_url,
  "",
  "A thumbnail built from another path/size/mtime identity must be discarded.",
);
const newerPendingRequest = {
  request_id: "thumbnail-newer-request",
  project_uid: thumbnailMergeLocal.project_uid,
  manifest_signature: thumbnailMergeLocal.manifest_signature,
  scan_revision: thumbnailMergeLocal.scan_revision,
  asset_library_ids: ["thumbnail-merge-a"],
};
const mismatchedPendingResponse = assetWidget.hmbMergeImageAssetThumbnailResponse(
  { ...thumbnailMergeLocal, thumbnail_request: newerPendingRequest },
  { ...thumbnailMergeIncoming, thumbnail_revision: 6 },
  newerPendingRequest.request_id,
);
assert.equal(mismatchedPendingResponse.thumbnail_revision, 3);
assert.equal(mismatchedPendingResponse.assets[0].thumbnail_url, "");
assert.equal(
  mismatchedPendingResponse.thumbnail_request.request_id,
  newerPendingRequest.request_id,
  "An older completion must not clear or supersede a newer pending request.",
);

// Missing thumbnails publish after paint as one deduplicated 64-id batch. A
// completion schedules the still-missing remainder once; failed IDs stay
// attempted for that catalog context and cannot create an idle retry loop.
const stagedThumbnailState = assetWidget.hmbNormalizeImageAssetState({
  project_uid: "thumbnail-stage-project",
  manifest_signature: "thumbnail-stage-manifest",
  scan_revision: 13,
  assets: Array.from({ length: 110 }, (_value, index) => selectableAsset(
    `thumbnail-stage-${index}`,
    index >= 60,
    index >= 60 ? index - 59 : 0,
  )),
});
const stagedContainer = {
  __hmbImageAssetLatestState: stagedThumbnailState,
  __hmbImageAssetRenderLimit: 60,
  __hmbImageAssetRenderOffset: 0,
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
const stagedSelectionBefore = assetWidget.hmbImageAssetSelectionSnapshot(
  stagedThumbnailState,
);
const stagedShotRoutingBefore = JSON.parse(JSON.stringify(stagedThumbnailState.shot_routing));
const stagedFrames = [];
const stagedTimers = new Map();
let stagedHandle = 0;
const stagedPublished = [];
const stagedSavedAnimationFrame = globalThis.requestAnimationFrame;
const stagedSavedSetTimeout = globalThis.setTimeout;
const stagedSavedClearTimeout = globalThis.clearTimeout;
globalThis.requestAnimationFrame = (callback) => {
  const id = ++stagedHandle;
  stagedFrames.push({ id, callback });
  return id;
};
globalThis.setTimeout = (callback, delay = 0) => {
  const id = ++stagedHandle;
  stagedTimers.set(id, { callback, delay: Number(delay) || 0 });
  return id;
};
globalThis.clearTimeout = (id) => stagedTimers.delete(id);
const flushStagedAfterPaint = () => {
  stagedFrames.splice(0).forEach(({ callback }) => callback());
  Array.from(stagedTimers.entries())
    .filter(([, timer]) => timer.delay === 0)
    .forEach(([id, timer]) => {
      stagedTimers.delete(id);
      timer.callback();
    });
};
try {
  const stagedProps = { onChange(value) { stagedPublished.push(JSON.parse(value)); } };
  assert.equal(
    assetWidget.hmbScheduleImageAssetThumbnailRequest(
      stagedContainer,
      stagedThumbnailState,
      stagedProps,
    ),
    true,
  );
  assert.equal(
    assetWidget.hmbScheduleImageAssetThumbnailRequest(
      stagedContainer,
      stagedThumbnailState,
      stagedProps,
    ),
    true,
    "Repeated pre-paint scheduling may replace the job but must not duplicate its publish.",
  );
  assert.equal(stagedPublished.length, 0);
  flushStagedAfterPaint();
  assert.equal(stagedPublished.length, 1);
  const firstThumbnailRequest = stagedPublished[0].thumbnail_request;
  assert.equal(stagedPublished[0].thumbnail_busy, true);
  assert.equal(
    stagedPublished[0].ui_edit_revision,
    stagedThumbnailState.ui_edit_revision,
    "A thumbnail request must not advance semantic UI authority.",
  );
  assert.deepEqual(
    assetWidget.hmbImageAssetSelectionSnapshot(stagedPublished[0]),
    stagedSelectionBefore,
    "A presentation request must preserve selection and drag order in its payload.",
  );
  assert.deepEqual(
    stagedPublished[0].shot_routing,
    stagedShotRoutingBefore,
    "A presentation request must preserve all Shot routing state in its payload.",
  );
  assert.deepEqual(
    assetWidget.hmbImageAssetSelectionSnapshot(
      stagedContainer.__hmbImageAssetLatestState,
    ),
    stagedSelectionBefore,
  );
  assert.deepEqual(
    stagedContainer.__hmbImageAssetLatestState.shot_routing,
    stagedShotRoutingBefore,
  );
  assert.deepEqual(stagedContainer.__hmbImageAssetLatestState.thumbnail_request, {});
  assert.equal(stagedContainer.__hmbImageAssetLatestState.thumbnail_busy, true);
  assert.equal(
    stagedContainer.__hmbImageAssetThumbnailPendingRequestId,
    firstThumbnailRequest.request_id,
    "Successful request intent clears locally while busy/pending persists to completion.",
  );
  assert.equal(firstThumbnailRequest.asset_library_ids.length, 64);
  assert.deepEqual(
    firstThumbnailRequest.asset_library_ids.slice(0, 3),
    ["thumbnail-stage-60", "thumbnail-stage-61", "thumbnail-stage-62"],
  );
  assert.deepEqual(
    firstThumbnailRequest.asset_library_ids.slice(50),
    Array.from({ length: 14 }, (_value, index) => `thumbnail-stage-${index}`),
  );

  const firstCompleted = new Set(firstThumbnailRequest.asset_library_ids);
  const firstCompletion = assetWidget.hmbNormalizeImageAssetState({
    ...stagedPublished[0],
    thumbnail_request: {},
    thumbnail_revision: 1,
    thumbnail_busy: false,
    thumbnail_result: {
      request_id: firstThumbnailRequest.request_id,
      project_uid: firstThumbnailRequest.project_uid,
      manifest_signature: firstThumbnailRequest.manifest_signature,
      scan_revision: firstThumbnailRequest.scan_revision,
      completed_asset_library_ids: firstThumbnailRequest.asset_library_ids,
      failed_asset_library_ids: [],
    },
    assets: stagedPublished[0].assets.map((asset) => ({
      ...asset,
      thumbnail_url: firstCompleted.has(asset.asset_library_id)
        ? `https://static.invalid/${asset.asset_library_id}.webp`
        : "",
    })),
  });
  stagedContainer.__hmbImageAssetLatestState = firstCompletion;
  delete stagedContainer.__hmbImageAssetThumbnailPendingRequestId;
  assert.equal(
    assetWidget.hmbScheduleImageAssetThumbnailRequest(
      stagedContainer,
      firstCompletion,
      stagedProps,
    ),
    true,
  );
  flushStagedAfterPaint();
  assert.equal(stagedPublished.length, 2);
  const secondThumbnailRequest = stagedPublished[1].thumbnail_request;
  assert.deepEqual(
    secondThumbnailRequest.asset_library_ids,
    Array.from({ length: 46 }, (_value, index) => `thumbnail-stage-${index + 14}`),
  );

  const failedCompletion = assetWidget.hmbNormalizeImageAssetState({
    ...stagedPublished[1],
    thumbnail_request: {},
    thumbnail_revision: 2,
    thumbnail_busy: false,
    thumbnail_result: {
      request_id: secondThumbnailRequest.request_id,
      project_uid: secondThumbnailRequest.project_uid,
      manifest_signature: secondThumbnailRequest.manifest_signature,
      scan_revision: secondThumbnailRequest.scan_revision,
      completed_asset_library_ids: [],
      failed_asset_library_ids: secondThumbnailRequest.asset_library_ids,
    },
  });
  stagedContainer.__hmbImageAssetLatestState = failedCompletion;
  delete stagedContainer.__hmbImageAssetThumbnailPendingRequestId;
  assert.equal(
    assetWidget.hmbScheduleImageAssetThumbnailRequest(
      stagedContainer,
      failedCompletion,
      stagedProps,
    ),
    false,
    "A failed asset is attempted once per scan context instead of looping while idle.",
  );
  assert.equal(
    assetWidget.hmbScheduleImageAssetThumbnailRequest(
      { __hmbImageAssetLatestState: { ...failedCompletion, scan_busy: true } },
      { ...failedCompletion, scan_busy: true },
      stagedProps,
    ),
    false,
  );
  assert.equal(
    assetWidget.hmbScheduleImageAssetThumbnailRequest(
      { __hmbImageAssetLatestState: { ...failedCompletion, thumbnail_busy: true } },
      { ...failedCompletion, thumbnail_busy: true },
      stagedProps,
    ),
    false,
  );

  const failedTransportState = assetWidget.hmbNormalizeImageAssetState({
    project_uid: "thumbnail-transport-project",
    manifest_signature: "thumbnail-transport-manifest",
    scan_revision: 2,
    ui_edit_revision: 6,
    assets: [selectableAsset("thumbnail-transport-asset")],
  });
  const failedTransportContainer = {
    __hmbImageAssetLatestState: failedTransportState,
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const failedTransportAssetsBefore = JSON.parse(JSON.stringify(failedTransportState.assets));
  const failedTransportShotRoutingBefore = JSON.parse(
    JSON.stringify(failedTransportState.shot_routing),
  );
  const savedTransportConsoleError = console.error;
  console.error = () => {};
  try {
    assert.equal(
      assetWidget.hmbScheduleImageAssetThumbnailRequest(
        failedTransportContainer,
        failedTransportState,
        { onChange() { throw new Error("thumbnail request transport failure"); } },
      ),
      true,
    );
    flushStagedAfterPaint();
  } finally {
    console.error = savedTransportConsoleError;
  }
  assert.equal(failedTransportState.ui_edit_revision, 6);
  assert.equal(failedTransportState.thumbnail_busy, true);
  assert.ok(failedTransportState.thumbnail_request.request_id);
  assert.deepEqual(failedTransportState.assets, failedTransportAssetsBefore);
  assert.deepEqual(failedTransportState.shot_routing, failedTransportShotRoutingBefore);
  assert.ok(failedTransportContainer.__hmbImageAssetThumbnailPendingRequestId);
  assert.equal(failedTransportContainer.__hmbImageAssetThumbnailRequestedIds.size, 1);
  const failedTransportWatchdog = failedTransportContainer.__hmbImageAssetThumbnailWatchdog;
  assert.ok(
    failedTransportWatchdog,
    "A synchronous dispatch failure must retain one bounded recovery lease.",
  );
  const failedTransportTimer = stagedTimers.get(failedTransportWatchdog.timer);
  assert.ok(failedTransportTimer);
  stagedTimers.delete(failedTransportWatchdog.timer);
  failedTransportTimer.callback();
  assert.equal(failedTransportState.thumbnail_busy, false);
  assert.deepEqual(failedTransportState.thumbnail_request, {});
  assert.deepEqual(
    failedTransportState.thumbnail_result.failed_asset_library_ids,
    ["thumbnail-transport-asset"],
  );
  assert.equal(failedTransportContainer.__hmbImageAssetThumbnailPendingRequestId, undefined);
  assert.equal(
    failedTransportContainer.__hmbImageAssetThumbnailFailedIds.has(
      "thumbnail-transport-asset",
    ),
    true,
    "A failed transport must end in a static failed presentation, not a loader.",
  );

  const unavailableTransportState = assetWidget.hmbNormalizeImageAssetState({
    project_uid: "thumbnail-unavailable-project",
    manifest_signature: "thumbnail-unavailable-manifest",
    scan_revision: 3,
    assets: [selectableAsset("thumbnail-unavailable-asset")],
  });
  const unavailableRuntimeId = unavailableTransportState.shot_routing.publisher_instance_uuid;
  bridgeRegistry.delete(unavailableRuntimeId);
  const unavailableTransportContainer = {
    __hmbImageAssetLatestState: unavailableTransportState,
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  assert.equal(
    assetWidget.hmbScheduleImageAssetThumbnailRequest(
      unavailableTransportContainer,
      unavailableTransportState,
      {},
    ),
    true,
  );
  flushStagedAfterPaint();
  const unavailableWatchdog =
    unavailableTransportContainer.__hmbImageAssetThumbnailWatchdog;
  assert.ok(unavailableWatchdog, "Bridge bootstrap races need a bounded lease.");
  const unavailableTimer = stagedTimers.get(unavailableWatchdog.timer);
  assert.ok(unavailableTimer);
  stagedTimers.delete(unavailableWatchdog.timer);
  unavailableTimer.callback();
  assert.equal(unavailableTransportState.thumbnail_busy, false);
  assert.deepEqual(
    unavailableTransportState.thumbnail_result.failed_asset_library_ids,
    ["thumbnail-unavailable-asset"],
  );
  assert.equal(
    unavailableTransportContainer.__hmbImageAssetThumbnailFailedIds.has(
      "thumbnail-unavailable-asset",
    ),
    true,
  );

  const staleUrl = "http://localhost:8124/workspace/static_files/stale.webp";
  const staleUrlState = assetWidget.hmbNormalizeImageAssetState({
    project_uid: "thumbnail-error-project",
    manifest_signature: "thumbnail-error-manifest",
    scan_revision: 4,
    ui_edit_revision: 10,
    assets: [selectableAsset("thumbnail-error-asset", false, 0, {
      thumbnail_url: staleUrl,
      media_signature: "d".repeat(64),
      relative_path: "Assets/stale.png",
    })],
  });
  const staleUrlCard = {
    getAttribute(name) {
      return name === "data-asset-key" ? "thumbnail-error-asset" : "";
    },
  };
  const staleUrlWrapperClasses = new Set();
  const staleUrlWrapper = { classList: { add(name) { staleUrlWrapperClasses.add(name); } } };
  const staleUrlAttributes = new Map([["src", staleUrl]]);
  const staleUrlImage = {
    matches(selector) { return selector === "img"; },
    getAttribute(name) { return staleUrlAttributes.get(name) || ""; },
    removeAttribute(name) { staleUrlAttributes.delete(name); },
    closest(selector) {
      if (selector === "[data-asset-key]") return staleUrlCard;
      if (selector.includes(".asset-thumb")) return staleUrlWrapper;
      return null;
    },
  };
  const staleUrlContainer = {
    __hmbImageAssetLatestState: staleUrlState,
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const retryPublished = [];
  const retryProps = { onChange(value) { retryPublished.push(JSON.parse(value)); } };
  assert.equal(
    assetWidget.hmbHandleImageAssetThumbnailError(
      staleUrlContainer,
      staleUrlState,
      staleUrlImage,
      retryProps,
    ),
    true,
  );
  assert.equal(staleUrlState.assets[0].thumbnail_url, "");
  flushStagedAfterPaint();
  assert.equal(retryPublished.length, 1);
  assert.equal(retryPublished[0].thumbnail_busy, true);
  assert.equal(retryPublished[0].ui_edit_revision, 10);

  const staleUrlRetryCompletion = assetWidget.hmbNormalizeImageAssetState({
    ...retryPublished[0],
    thumbnail_request: {},
    thumbnail_busy: false,
    thumbnail_revision: 1,
    thumbnail_result: {
      request_id: retryPublished[0].thumbnail_request.request_id,
      project_uid: "thumbnail-error-project",
      manifest_signature: "thumbnail-error-manifest",
      scan_revision: 4,
      completed_asset_library_ids: ["thumbnail-error-asset"],
      failed_asset_library_ids: [],
    },
    assets: retryPublished[0].assets.map((asset) => ({
      ...asset,
      thumbnail_url: staleUrl,
    })),
  });
  staleUrlContainer.__hmbImageAssetLatestState = staleUrlRetryCompletion;
  delete staleUrlContainer.__hmbImageAssetThumbnailPendingRequestId;
  staleUrlAttributes.set("src", staleUrl);
  assert.equal(
    assetWidget.hmbHandleImageAssetThumbnailError(
      staleUrlContainer,
      staleUrlRetryCompletion,
      staleUrlImage,
      retryProps,
    ),
    true,
  );
  flushStagedAfterPaint();
  assert.equal(
    retryPublished.length,
    1,
    "The same invalid StaticFiles URL may be retried once, never in an idle loop.",
  );
  assert.equal(staleUrlRetryCompletion.assets[0].thumbnail_url, "");
  assert.equal(
    staleUrlContainer.__hmbImageAssetThumbnailRequestedIds.has("thumbnail-error-asset"),
    true,
  );

  const persistedUserStaleUrl = "http://localhost:8124/workspace/static_files/stale-user.webp";
  const persistedUserStaleState = assetWidget.hmbNormalizeImageAssetState({
    project_uid: "thumbnail-error-project",
    manifest_signature: "thumbnail-error-manifest",
    scan_revision: 4,
    ui_edit_revision: 10,
    selected_source_view: "user",
    assets: [selectableAsset("thumbnail-error-persisted-user", false, 0, {
      source_kind: "user",
      import_index: 0,
      relative_path: "User/stale-user.png",
      thumbnail_url: persistedUserStaleUrl,
      media_signature: "f".repeat(64),
    })],
  });
  const persistedUserCard = {
    getAttribute(name) {
      return name === "data-asset-key" ? "thumbnail-error-persisted-user" : "";
    },
  };
  const persistedUserImage = {
    getAttribute(name) { return name === "src" ? persistedUserStaleUrl : ""; },
    removeAttribute() {},
    closest(selector) {
      if (selector === "[data-asset-key]") return persistedUserCard;
      return null;
    },
  };
  const persistedUserContainer = {
    __hmbImageAssetLatestState: persistedUserStaleState,
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  assert.equal(
    assetWidget.hmbHandleImageAssetThumbnailError(
      persistedUserContainer,
      persistedUserStaleState,
      persistedUserImage,
      retryProps,
    ),
    true,
    "A persisted project User-folder StaticFiles URL must enter bounded recovery.",
  );
  assert.equal(persistedUserStaleState.assets[0].thumbnail_url, "");
  flushStagedAfterPaint();
  assert.equal(retryPublished.length, 2);
  assert.deepEqual(
    retryPublished[1].thumbnail_request.asset_library_ids,
    ["thumbnail-error-persisted-user"],
  );

  const liveImportStaleState = assetWidget.hmbNormalizeImageAssetState({
    project_uid: "thumbnail-error-project",
    manifest_signature: "thumbnail-error-manifest",
    scan_revision: 4,
    assets: [selectableAsset("thumbnail-error-live-user", false, 0, {
      source_kind: "user",
      import_index: 1,
      relative_path: "User/live-user.png",
      thumbnail_url: staleUrl,
    })],
  });
  const liveImportCard = {
    getAttribute(name) {
      return name === "data-asset-key" ? "thumbnail-error-live-user" : "";
    },
  };
  const liveImportImage = {
    getAttribute(name) { return name === "src" ? staleUrl : ""; },
    closest(selector) {
      return selector === "[data-asset-key]" ? liveImportCard : null;
    },
  };
  assert.equal(
    assetWidget.hmbHandleImageAssetThumbnailError(
      { __hmbImageAssetLatestState: liveImportStaleState },
      liveImportStaleState,
      liveImportImage,
      retryProps,
    ),
    false,
    "A live IMAGE_IMPORT_IN row must not enter StaticFiles recovery.",
  );
  assert.equal(liveImportStaleState.assets[0].thumbnail_url, staleUrl);

  const externalUrlState = assetWidget.hmbNormalizeImageAssetState({
    project_uid: "thumbnail-error-project",
    manifest_signature: "thumbnail-error-manifest",
    scan_revision: 4,
    assets: [{
      ...selectableAsset("thumbnail-external-asset"),
      source_uid: "import:thumbnail-external-asset",
      source_kind: "user",
      thumbnail_url: "https://external.invalid/source.png",
    }],
  });
  const externalCard = {
    getAttribute(name) {
      return name === "data-asset-key" ? "thumbnail-external-asset" : "";
    },
  };
  const externalImage = {
    getAttribute(name) {
      return name === "src" ? "https://external.invalid/source.png" : "";
    },
    closest(selector) {
      return selector === "[data-asset-key]" ? externalCard : null;
    },
  };
  assert.equal(
    assetWidget.hmbHandleImageAssetThumbnailError(
      { __hmbImageAssetLatestState: externalUrlState },
      externalUrlState,
      externalImage,
      retryProps,
    ),
    false,
    "External HTTP/data media must never enter the project thumbnail retry path.",
  );
  assert.equal(
    externalUrlState.assets[0].thumbnail_url,
    "https://external.invalid/source.png",
  );
  const dataUrl = "data:image/png;base64,AAAA";
  const dataUrlState = assetWidget.hmbNormalizeImageAssetState({
    project_uid: "thumbnail-error-project",
    manifest_signature: "thumbnail-error-manifest",
    scan_revision: 4,
    assets: [selectableAsset("thumbnail-data-asset", false, 0, {
      thumbnail_url: dataUrl,
      media_signature: "e".repeat(64),
    })],
  });
  const dataUrlCard = {
    getAttribute(name) {
      return name === "data-asset-key" ? "thumbnail-data-asset" : "";
    },
  };
  const dataUrlImage = {
    getAttribute(name) { return name === "src" ? dataUrl : ""; },
    closest(selector) {
      return selector === "[data-asset-key]" ? dataUrlCard : null;
    },
  };
  assert.equal(
    assetWidget.hmbHandleImageAssetThumbnailError(
      { __hmbImageAssetLatestState: dataUrlState },
      dataUrlState,
      dataUrlImage,
      retryProps,
    ),
    false,
    "Inline data media must never enter the project thumbnail retry path.",
  );
  assert.equal(dataUrlState.assets[0].thumbnail_url, dataUrl);
  assetWidget.hmbCancelImageAssetThumbnailRequest(persistedUserContainer);
  assetWidget.hmbCancelImageAssetThumbnailRequest(staleUrlContainer);
} finally {
  assetWidget.hmbCancelImageAssetThumbnailRequest(stagedContainer);
  if (stagedSavedAnimationFrame === undefined) delete globalThis.requestAnimationFrame;
  else globalThis.requestAnimationFrame = stagedSavedAnimationFrame;
  globalThis.setTimeout = stagedSavedSetTimeout;
  globalThis.clearTimeout = stagedSavedClearTimeout;
}

// A bridge result can be lost during a host remount/update race. Keep one
// bounded exact-request probe and then stop every animation with a terminal
// failed presentation state; Refresh explicitly clears that retry boundary.
{
  const savedWatchdogSetTimeout = globalThis.setTimeout;
  const savedWatchdogClearTimeout = globalThis.clearTimeout;
  const watchdogTimers = new Map();
  let watchdogSequence = 0;
  globalThis.setTimeout = (callback, delay = 0) => {
    const id = ++watchdogSequence;
    watchdogTimers.set(id, { callback, delay: Number(delay) || 0 });
    return id;
  };
  globalThis.clearTimeout = (id) => watchdogTimers.delete(id);
  try {
    const longWatchdogId = `asset/${"long-segment-".repeat(22)}image.png`;
    assert.ok(longWatchdogId.length > 128);
    const watchdogState = assetWidget.hmbNormalizeImageAssetState({
      project_uid: "thumbnail-watchdog-project",
      manifest_signature: "thumbnail-watchdog-manifest",
      scan_revision: 9,
      assets: [selectableAsset(longWatchdogId, false, 0, {
        media_signature: "f".repeat(64),
      })],
    });
    const watchdogRequest = {
      schema: "hmb-image-asset-thumbnail-bridge",
      version: 1,
      operation: "hydrate",
      phase: "request",
      runtime_instance_id: watchdogState.shot_routing.publisher_instance_uuid,
      request_id: "thumbnail-watchdog-request",
      project_uid: watchdogState.project_uid,
      manifest_signature: watchdogState.manifest_signature,
      scan_revision: watchdogState.scan_revision,
      asset_library_ids: [longWatchdogId],
    };
    watchdogState.thumbnail_request = { ...watchdogRequest };
    watchdogState.thumbnail_busy = true;
    const watchdogContainer = {
      __hmbImageAssetLatestState: watchdogState,
      __hmbImageAssetMountToken: 77,
      __hmbImageAssetThumbnailPendingRequestId: watchdogRequest.request_id,
      querySelector() { return null; },
      querySelectorAll() { return []; },
    };
    const probes = [];
    bridgeRegistry.set(watchdogRequest.runtime_instance_id, {
      dispatch(request) { probes.push(request); },
    });
    assert.equal(
      assetWidget.hmbArmImageAssetThumbnailWatchdog(
        watchdogContainer,
        watchdogState,
        {},
        watchdogRequest,
      ),
      true,
    );
    const runWatchdogTimer = () => {
      const entry = watchdogTimers.entries().next().value;
      assert.ok(entry, "The thumbnail watchdog must own one bounded timer.");
      const [id, timer] = entry;
      watchdogTimers.delete(id);
      assert.equal(timer.delay, 15000);
      timer.callback();
    };
    runWatchdogTimer();
    assert.equal(probes.length, 1, "One lost result receives one exact-request probe.");
    assert.equal(probes[0].request_id, watchdogRequest.request_id);
    assert.deepEqual(probes[0].asset_library_ids, [longWatchdogId]);
    assert.equal(watchdogTimers.size, 1);
    const savedWarn = console.warn;
    console.warn = () => {};
    try { runWatchdogTimer(); } finally { console.warn = savedWarn; }
    assert.equal(watchdogTimers.size, 0);
    assert.equal(watchdogState.thumbnail_busy, false);
    assert.equal(watchdogState.thumbnail_request.request_id, undefined);
    assert.deepEqual(
      watchdogState.thumbnail_result.failed_asset_library_ids,
      [longWatchdogId],
      "Timeout terminalization must preserve the full path-derived ID.",
    );
    assert.equal(
      watchdogContainer.__hmbImageAssetThumbnailPendingRequestId,
      undefined,
    );
    assert.equal(
      watchdogContainer.__hmbImageAssetThumbnailFailedIds.has(longWatchdogId),
      true,
    );
    assert.equal(
      assetWidget.hmbResetImageAssetThumbnailRetryState(
        watchdogContainer,
        watchdogState,
      ),
      true,
    );
    assert.equal(watchdogContainer.__hmbImageAssetThumbnailFailedIds.size, 0);
    assert.deepEqual(watchdogState.thumbnail_result, {});

    const remountAssetId = "thumbnail-remount-asset";
    const remountState = assetWidget.hmbNormalizeImageAssetState({
      project_uid: "thumbnail-remount-project",
      manifest_signature: "thumbnail-remount-manifest",
      scan_revision: 10,
      thumbnail_busy: true,
      thumbnail_request: {
        request_id: "thumbnail-remount-request",
        project_uid: "thumbnail-remount-project",
        manifest_signature: "thumbnail-remount-manifest",
        scan_revision: 10,
        asset_library_ids: [remountAssetId],
      },
      assets: [selectableAsset(remountAssetId)],
    });
    const remountRuntimeId = remountState.shot_routing.publisher_instance_uuid;
    const remountDispatches = [];
    bridgeRegistry.set(remountRuntimeId, {
      dispatch(request) { remountDispatches.push(request); },
    });
    const remountContainer = {
      __hmbImageAssetLatestState: remountState,
      __hmbImageAssetMountToken: 78,
      querySelector() { return null; },
      querySelectorAll() { return []; },
    };
    assert.equal(
      assetWidget.hmbResumeImageAssetThumbnailRequest(
        remountContainer,
        remountState,
        {},
      ),
      true,
      "A new mount must reconstruct the pending lease from serialized busy state.",
    );
    assert.equal(
      remountContainer.__hmbImageAssetThumbnailPendingRequestId,
      "thumbnail-remount-request",
    );
    assert.equal(remountDispatches.length, 1);
    assert.equal(remountDispatches[0].request_id, "thumbnail-remount-request");
    assert.equal(
      remountContainer.__hmbImageAssetThumbnailRequestedIds.has(remountAssetId),
      true,
    );
    assert.ok(remountContainer.__hmbImageAssetThumbnailWatchdog);
    assetWidget.hmbCancelImageAssetThumbnailRequest(remountContainer);
    bridgeRegistry.delete(remountRuntimeId);
    bridgeRegistry.delete(watchdogRequest.runtime_instance_id);
  } finally {
    globalThis.setTimeout = savedWatchdogSetTimeout;
    globalThis.clearTimeout = savedWatchdogClearTimeout;
  }
}

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
  /const selectedTray = container\.querySelector\("\[data-shot-tray\]"\);[\s\S]*?hmbInstallImageAssetShotDragReorder\(container, \{[\s\S]*?listen: \(eventName, handler\) => on\(container, eventName, handler, true\),[\s\S]*?on\(selectedTray, "click"/,
  "Stable-container drag delegation and active-tray removal must survive tray patching.",
);
assert.match(
  installEventsSource,
  /on\(container, "error"[\s\S]*?image\.closest/,
  "One capture listener must handle dynamically replaced thumbnail errors.",
);
assert.doesNotMatch(
  assetSource,
  /hmbImageAssetAutoSyncPayload|hmbIsImageAssetManifestPollEcho|__hmb_manifest_poll_nonce|IMAGE_ASSET_AUTO_SYNC|function runAutoSync|scheduleAutoSync/,
  "ImageAsset must not retain the retired background manifest polling path.",
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
  /const cleanup = \(\) => \{[\s\S]*?hmbInvalidateImageAssetPublication\(container\);[\s\S]*?hmbCancelImageAssetSelectionCommit\(container\);[\s\S]*?hmbForgetImageAssetStateEcho\(container\);/,
  "Cleanup must cancel pending selection and echo work without publishing a disposed widget.",
);
assert.match(
  toggleSource,
  /rollbackState = pending\.state[\s\S]*?if \(rollbackState\) \{\s*state = remount\(rollbackState\);[\s\S]*?hmbRestoreImageAssetSelectionSnapshot\(state, baseSelection\)/,
  "A latest selection transport failure must restore pending authority or the compact base selection snapshot.",
);
assert.match(
  assetSource,
  /function emit\(props, state, container = null, onFailure = null, options = \{\}\) \{\s*return hmbPublishImageAssetState\(container, props, state, onFailure, options\);/,
  "Every generic Image state emit must pass through the owner-guarded transport retry boundary.",
);
assert.match(
  assetSource,
  /const consumedStateEcho = hmbConsumeImageAssetStateEcho\(container, nextProps\);[\s\S]*?if \(consumedStateEcho\) \{[\s\S]*?__hmbImageAssetLastConsumedEchoWasStale[\s\S]*?return;[\s\S]*?if \(container\.__hmbImageAssetSelectionCommitPending\)/,
  "Revision-stale props must be consumed before selection-delta authority is merged.",
);
assert.match(
  assetSource,
  /const cleanup = \(\) => \{[\s\S]*?delete container\.__hmbImageAssetCurrentScanRevision;[\s\S]*?delete container\.__hmbImageAssetCurrentUiEditRevision;[\s\S]*?delete container\.__hmbImageAssetLatestLocalUiEditRevision;/,
  "Cleanup must discard ImageAsset revision baselines before workflow hydration.",
);
console.log("HMB ImageAsset immediate feedback + no-remount performance regression: PASS");
