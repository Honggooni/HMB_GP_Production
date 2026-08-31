import assert from "node:assert/strict";
import fs from "node:fs";

async function importSource(path) {
  const source = fs.readFileSync(path, "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

const promptPath = new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url);
const promptSource = fs.readFileSync(promptPath, "utf8");
const prompt = await importSource(promptPath);
const INT32_MIN = -2147483648;
const INT32_MAX = 2147483647;
const defaultIntent = () => ({
  version: 1,
  enabled: false,
  start_frame: null,
  end_frame: null,
  ranges: [],
  selected_index: -1,
});
const activeIntent = () => ({
  version: 1,
  enabled: true,
  start_frame: -12000,
  end_frame: 24000,
  ranges: [
    { start: -12000, end: -11000 },
    { start: 12001, end: 24000 },
  ],
  selected_index: 1,
});
const baseImage = (overrides = {}) => ({
  slot: 1,
  label: "Hero",
  present: true,
  asset_id: "hero",
  asset_source_uid: "project:hero",
  source_type: "Character Appearance",
  owner: "Hero",
  scope: "Full body / full appearance",
  binding_scopes: ["Full body / full appearance"],
  binding_custom_scopes: [""],
  binding_video_slots: [1],
  marker_video: 1,
  color_picks: [""],
  frame_range_intent: defaultIntent(),
  frame_range_enabled: false,
  frame_range_color_index: 0,
  frame_range_bindings: {},
  frame_range_binding: null,
  frame_range_selected_index: -1,
  ...overrides,
});
const baseState = (image, overrides = {}) => prompt.normalizeState({
  ui: { language: "en" },
  images: [image],
  videos: [],
  picker: { enabled: false, awaiting_data: false, frame_metadata: [] },
  ...overrides,
});

// Full signed INT32 normalization rejects invalid endpoints but preserves the
// user's exact range order, segmentation, overlap, adjacency, and duplicates.
assert.deepEqual(
  prompt.normalizeFrameRanges([
    { start: 97, end: 120 },
    { start: 1, end: 48 },
    { start: 121, end: 144 },
    { start: 40, end: 60 },
  ]),
  [
    { start: 97, end: 120 },
    { start: 1, end: 48 },
    { start: 121, end: 144 },
    { start: 40, end: 60 },
  ],
);
assert.deepEqual(
  prompt.normalizeFrameRanges([
    { start: INT32_MIN, end: INT32_MIN },
    { start: INT32_MIN + 1, end: -1 },
    { start: INT32_MAX - 1, end: INT32_MAX },
    { start: INT32_MAX, end: INT32_MAX },
    { start: INT32_MIN - 1, end: 0 },
    { start: 0, end: INT32_MAX + 0.4 },
    { start: true, end: 1 },
  ]),
  [
    { start: INT32_MIN, end: INT32_MIN },
    { start: INT32_MIN + 1, end: -1 },
    { start: INT32_MAX - 1, end: INT32_MAX },
    { start: INT32_MAX, end: INT32_MAX },
  ],
);
assert.deepEqual(
  prompt.normalizeFrameRanges([
    { start: 10, end: 20 },
    { start: 10, end: 20 },
    { start: 15, end: 25 },
  ]),
  [
    { start: 10, end: 20 },
    { start: 10, end: 20 },
    { start: 15, end: 25 },
  ],
  "Duplicate and overlapping authored segments must not be merged or deduplicated.",
);
assert.deepEqual(
  prompt.normalizeFrameRanges([{ start: -1.5, end: 1.5 }]),
  [{ start: -1, end: 2 }],
  "Frontend rounding matches backend JavaScript-style signed rounding.",
);
assert.equal(prompt.frameDomainInputValue(INT32_MIN), "-2147483648");
assert.equal(prompt.frameDomainInputValue(-12), "-012");
assert.equal(prompt.frameDomainInputValue(12000), "12000");
assert.equal(prompt.frameDomainInputValue(INT32_MAX + 1), "");
assert.equal(prompt.frameDomainInputValue(false), "");

// One-way migration imports manual legacy data only.
const legacyManual = baseImage({
  frame_range_enabled: true,
  frame_range_selected_index: 0,
  frame_range_binding: {
    video_slot: "@video7",
    color_pick: "Green",
    origin: "manual",
    start_frame: -20,
    end_frame: 12000,
    ranges: [{ start: 10, end: 20 }],
  },
});
delete legacyManual.frame_range_intent;
assert.deepEqual(baseState(legacyManual).images[0].frame_range_intent, {
  version: 1,
  enabled: true,
  start_frame: -20,
  end_frame: 12000,
  ranges: [{ start: 10, end: 20 }],
  selected_index: 0,
});

const pickerOnlyLegacy = baseImage({
  frame_range_enabled: true,
  frame_range_selected_index: 0,
  frame_range_binding: {
    origin: "picker_auto",
    start_frame: 1,
    end_frame: 144,
    ranges: [{ start: 1, end: 48 }],
  },
});
delete pickerOnlyLegacy.frame_range_intent;
assert.deepEqual(
  baseState(pickerOnlyLegacy).images[0].frame_range_intent,
  { ...defaultIntent(), enabled: true },
  "Picker-authored endpoints/ranges are never imported into Prompt intent.",
);

const canonicalWins = baseImage({
  frame_range_intent: defaultIntent(),
  frame_range_enabled: true,
  frame_range_selected_index: 0,
  frame_range_binding: {
    origin: "manual",
    start_frame: 1,
    end_frame: 144,
    ranges: [{ start: 1, end: 48 }],
  },
});
assert.deepEqual(
  baseState(canonicalWins).images[0].frame_range_intent,
  defaultIntent(),
  "Canonical field presence is the permanent migration sentinel.",
);

// No video, Picker, Color Pick, or metadata is required to author a Range.
const noVideoState = baseState(baseImage());
const noVideoImage = noVideoState.images[0];
const legacyBeforeEdit = JSON.stringify({
  enabled: noVideoImage.frame_range_enabled,
  colorIndex: noVideoImage.frame_range_color_index,
  bindings: noVideoImage.frame_range_bindings,
  binding: noVideoImage.frame_range_binding,
  selected: noVideoImage.frame_range_selected_index,
});
assert.equal(prompt.setFrameRangeEnabled(noVideoImage, true), true);
prompt.storeCurrentFrameDomain(noVideoImage, -12000, 24000);
prompt.storeCurrentFrameRanges(noVideoImage, [
  { start: 12001, end: 24000 },
  { start: -12000, end: -11000 },
], 1);
assert.deepEqual(noVideoImage.frame_range_intent, {
  ...activeIntent(),
  ranges: [
    { start: 12001, end: 24000 },
    { start: -12000, end: -11000 },
  ],
});
assert.equal(
  JSON.stringify({
    enabled: noVideoImage.frame_range_enabled,
    colorIndex: noVideoImage.frame_range_color_index,
    bindings: noVideoImage.frame_range_bindings,
    binding: noVideoImage.frame_range_binding,
    selected: noVideoImage.frame_range_selected_index,
  }),
  legacyBeforeEdit,
  "Range UI does not project changes into video/color-addressed legacy fields.",
);
let status = prompt.frameRangeUiStatus(noVideoState, noVideoImage);
assert.equal(status.canEnable, true);
assert.equal(status.reason, "");
assert.equal(status.domainReadonly, false);
assert.equal(status.domainComplete, true);
assert.equal(status.metadata.origin, "manual");
assert.deepEqual([status.domainStart, status.domainEnd], [-12000, 24000]);
assert.deepEqual(status.ranges, [
  { start: 12001, end: 24000 },
  { start: -12000, end: -11000 },
]);

const beforeOff = structuredClone(noVideoImage.frame_range_intent);
assert.equal(prompt.setFrameRangeEnabled(noVideoImage, false), false);
assert.deepEqual(noVideoImage.frame_range_intent, { ...beforeOff, enabled: false });
assert.equal(noVideoImage.frame_range_intent.selected_index, 1);
assert.equal(prompt.setFrameRangeEnabled(noVideoImage, true), true);
assert.deepEqual(noVideoImage.frame_range_intent, beforeOff);

prompt.storeCurrentFrameDomain(noVideoImage, INT32_MAX + 1, INT32_MIN - 1);
assert.deepEqual(
  [noVideoImage.frame_range_intent.start_frame, noVideoImage.frame_range_intent.end_frame],
  [null, null],
  "Out-of-domain manual input is rejected rather than clamped.",
);
prompt.storeCurrentFrameDomain(noVideoImage, INT32_MIN, INT32_MAX);

// Source slot/color/Picker changes are orthogonal to canonical intent.
const intentBeforeSourceChanges = structuredClone(noVideoImage.frame_range_intent);
noVideoImage.color_picks = ["Blue", "Green"];
noVideoImage.binding_video_slots = [10, 2];
noVideoImage.marker_video = 10;
noVideoImage.picker_auto_color = "Blue";
noVideoImage.picker_auto_video = 10;
noVideoImage.frame_range_color_index = 1;
noVideoImage.frame_range_enabled = false;
noVideoImage.frame_range_selected_index = -1;
noVideoImage.frame_range_bindings = {
  "@video10::Blue": {
    origin: "picker_auto",
    start_frame: 1,
    end_frame: 12,
    ranges: [{ start: 1, end: 12 }],
  },
};
const afterSlotAndColorChange = prompt.normalizeState(noVideoState);
assert.deepEqual(afterSlotAndColorChange.images[0].frame_range_intent, intentBeforeSourceChanges);

const pickerMutationStatus = prompt.frameRangeUiStatus({
  ...afterSlotAndColorChange,
  videos: [{ slot: 10, present: true, video_uid: "changed-video" }],
  picker: {
    enabled: true,
    awaiting_data: false,
    frame_metadata: [{
      video_slot: "@video10",
      start_frame: 1,
      end_frame: 12,
      frame_count: 12,
      fps: 24,
      available_color_picks: ["Blue"],
      valid: true,
    }],
  },
}, afterSlotAndColorChange.images[0]);
assert.deepEqual(
  {
    intent: pickerMutationStatus.intent,
    domainStart: pickerMutationStatus.domainStart,
    domainEnd: pickerMutationStatus.domainEnd,
    ranges: pickerMutationStatus.ranges,
    reason: pickerMutationStatus.reason,
  },
  {
    intent: intentBeforeSourceChanges,
    domainStart: INT32_MIN,
    domainEnd: INT32_MAX,
    ranges: intentBeforeSourceChanges.ranges,
    reason: "",
  },
  "Picker JSON/metadata cannot veto, fill, cap, or replace manual intent.",
);

// A props update that arrives inside the input debounce window overlays the
// focused endpoint draft onto the authoritative source state.
const dirtyContainer = {};
const dirtyRow = {
  getAttribute(name) {
    return name === "data-kind" ? "image" : name === "data-index" ? "0" : "";
  },
};
const dirtyStartInput = {
  value: "-34567",
  matches(selector) { return selector.includes('input[type="text"]'); },
  getAttribute(name) {
    if (name === "data-frame-domain-number") return "start";
    return "";
  },
  closest(selector) { return selector === ".source-row" ? dirtyRow : null; },
};
assert.equal(
  prompt.hmbRememberPromptDirtyTextControl(dirtyContainer, dirtyStartInput, noVideoState),
  true,
);
const dirtyMerged = prompt.hmbMergePromptDirtyTextState(
  baseState(baseImage({ frame_range_intent: defaultIntent() })),
  dirtyContainer.__hmbPromptLibraryDirtyText,
);
assert.equal(dirtyMerged.images[0].frame_range_intent.start_frame, -34567);
assert.equal(dirtyMerged.images[0].frame_range_intent.enabled, false);

// Keyboard editing works across signed bounds without scanning 4B frames.
assert.deepEqual(
  prompt.hmbApplyFrameRangeKeyboard([], -1, "Enter", {}, INT32_MIN, INT32_MAX),
  {
    handled: true,
    changed: true,
    ranges: [{ start: INT32_MIN, end: INT32_MIN }],
    selectedIndex: 0,
  },
);
const addGap = prompt.hmbApplyFrameRangeKeyboard(
  [{ start: INT32_MIN, end: 0 }], 0, "Enter", { altKey: true }, INT32_MIN, INT32_MAX,
);
assert.equal(addGap.changed, true);
assert.deepEqual(addGap.ranges, [
  { start: INT32_MIN, end: 0 },
  { start: 2, end: 2 },
]);
const fullDomainAdd = prompt.hmbApplyFrameRangeKeyboard(
  [{ start: INT32_MIN, end: INT32_MAX }], 0, "Enter", { altKey: true }, INT32_MIN, INT32_MAX,
);
assert.equal(fullDomainAdd.changed, false);
assert.deepEqual(fullDomainAdd.ranges, [{ start: INT32_MIN, end: INT32_MAX }]);

// Higher-source same/lower-UI echoes retain local intent by stable identity.
const currentState = baseState(baseImage({ frame_range_intent: activeIntent() }), {
  source_sync_revision: 5,
  ui_edit_revision: 9,
});
const incomingStaleIntent = prompt.normalizeState({
  ...structuredClone(currentState),
  source_sync_revision: 6,
  ui_edit_revision: 9,
  images: currentState.images.map((item, index) => index === 0 ? {
    ...structuredClone(item),
    label: "Source refreshed Hero",
    frame_range_intent: defaultIntent(),
  } : structuredClone(item)),
});
const mergeContainer = {
  __hmbPromptCurrentSourceSyncRevision: 5,
  __hmbPromptCurrentUiEditRevision: 9,
  __hmbPromptLatestLocalUiEditRevision: 9,
  __hmbPromptCurrentDisabled: false,
};
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    mergeContainer,
    { value: JSON.stringify(incomingStaleIntent), disabled: false },
    currentState,
  ),
  false,
);
const mergedNewSource = prompt.hmbTakePromptRevisionMerge(mergeContainer);
assert.equal(mergedNewSource.source_sync_revision, 6);
assert.equal(mergedNewSource.images[0].label, "Source refreshed Hero");
assert.deepEqual(mergedNewSource.images[0].frame_range_intent, activeIntent());

const lowerUiIncoming = prompt.normalizeState({
  ...structuredClone(incomingStaleIntent),
  source_sync_revision: 7,
  ui_edit_revision: 8,
});
mergeContainer.__hmbPromptCurrentSourceSyncRevision = 6;
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    mergeContainer,
    { value: JSON.stringify(lowerUiIncoming), disabled: false },
    mergedNewSource,
  ),
  false,
);
assert.deepEqual(
  prompt.hmbTakePromptRevisionMerge(mergeContainer).images[0].frame_range_intent,
  activeIntent(),
);

const directUi = prompt.normalizeState({
  ui_edit_revision: 11,
  source_sync_revision: 7,
  images: [
    baseImage({ slot: 1, asset_id: "a", asset_source_uid: "project:a", frame_range_intent: { ...activeIntent(), start_frame: -9 } }),
    baseImage({ slot: 2, asset_id: "b", asset_source_uid: "project:b", frame_range_intent: { ...activeIntent(), start_frame: -8 } }),
  ],
});
const directSource = prompt.normalizeState({
  ui_edit_revision: 10,
  source_sync_revision: 8,
  images: [
    baseImage({ slot: 1, label: "B refreshed", asset_id: "b", asset_source_uid: "project:b", frame_range_intent: defaultIntent() }),
    baseImage({ slot: 2, label: "A refreshed", asset_id: "a", asset_source_uid: "project:a", frame_range_intent: defaultIntent() }),
  ],
});
const directMerged = prompt.hmbMergePromptRevisionAxes(directSource, directUi);
assert.equal(directMerged.images[0].asset_source_uid, "project:b");
assert.equal(directMerged.images[0].frame_range_intent.start_frame, -8);
assert.equal(directMerged.images[1].asset_source_uid, "project:a");
assert.equal(directMerged.images[1].frame_range_intent.start_frame, -9);

// Canonical no-video state survives widget publication.
const publications = [];
prompt.hmbEmitLocalPromptState(
  {},
  { disabled: false, onChange(value) { publications.push(JSON.parse(value)); } },
  noVideoState,
);
assert.equal(publications.length, 1);
assert.deepEqual(publications[0].images[0].frame_range_intent, noVideoImage.frame_range_intent);

// DOM/source contract: signed fields, low-latency input, focus protection,
// canonical-only revision overlay, and no Color Pick deletion coupling.
const frameRowSource = promptSource.slice(
  promptSource.indexOf("function renderFrameRangeRow"),
  promptSource.indexOf("export function storeCurrentFrameRanges"),
);
assert.match(frameRowSource, /data-frame-domain-number="start"[^>]*pattern="-\?\[0-9\]\+"/);
assert.match(frameRowSource, /data-frame-domain-number="end"[^>]*pattern="-\?\[0-9\]\+"/);
assert.doesNotMatch(frameRowSource, /maxlength=/);
assert.doesNotMatch(frameRowSource, /readonly/);
const interactionSource = promptSource.slice(
  promptSource.indexOf("function hmbInstallFrameRangeInteractions"),
  promptSource.indexOf("function renderColorPickControls"),
);
assert.match(interactionSource, /bind\(element, "input", inputHandler\)/);
assert.match(interactionSource, /status\.intent\.enabled/);
assert.doesNotMatch(interactionSource, /item\.frame_range_enabled|item\.frame_range_selected_index/);
const syncDomSource = promptSource.slice(
  promptSource.indexOf("function hmbSyncFrameRangeRowDom"),
  promptSource.indexOf("const HMB_PROMPT_LOCAL_ECHO_TTL_MS"),
);
assert.match(syncDomSource, /input\.ownerDocument\?\.activeElement !== input/);
const revisionFieldSource = promptSource.slice(
  promptSource.indexOf("const HMB_FRAME_RANGE_UI_FIELDS"),
  promptSource.indexOf("function hmbPromptFrameRangeIdentity"),
);
assert.match(revisionFieldSource, /"frame_range_intent"/);
assert.doesNotMatch(revisionFieldSource, /frame_range_enabled|frame_range_bindings|frame_range_color_index/);
const removeColorSource = promptSource.slice(
  promptSource.indexOf('container.querySelectorAll(".remove-color-pick")'),
  promptSource.indexOf('container.querySelectorAll(".add-image")'),
);
assert.doesNotMatch(removeColorSource, /frame_range_bindings|frame_range_binding|frame_range_intent/);
assert.match(promptSource, /shouldRepublishRevisionMerge/);

console.log("HMB Prompt independent frame-range intent regression: PASS");
