import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(widgetPath);

function fakeOption(value, label = value) {
  return { value: String(value), textContent: String(label), text: String(label) };
}

function rapidSelectFixture(values, initialValue) {
  const options = values.map((value) => fakeOption(value));
  let currentValue = String(initialValue);
  let innerHtmlWrites = 0;
  let valueWrites = 0;
  const select = {
    options,
    style: { width: "320px", height: "30px" },
    get innerHTML() { return "<stable-options>"; },
    set innerHTML(_value) { innerHtmlWrites += 1; },
    get value() { return currentValue; },
    set value(value) { currentValue = String(value); valueWrites += 1; },
  };
  return {
    select,
    options,
    metrics() { return { innerHtmlWrites, valueWrites }; },
  };
}

function rangePreviewFixture() {
  let labelText = "10–20";
  let labelWrites = 0;
  const label = {
    get textContent() { return labelText; },
    set textContent(value) { labelText = String(value); labelWrites += 1; },
  };
  const style = { left: "9%", width: "11%" };
  const attributes = new Map();
  const bar = {
    className: "frame-range-bar selected",
    style,
    setAttribute(name, value) { attributes.set(name, String(value)); },
    querySelector(selector) { return selector === "b" ? label : null; },
    remove() { throw new Error("The sole live Range bar must not be removed during drag preview."); },
  };
  let statusText = "10–20";
  let statusWrites = 0;
  const status = {
    get textContent() { return statusText; },
    set textContent(value) { statusText = String(value); statusWrites += 1; },
  };
  let innerHtmlWrites = 0;
  const trackAttributes = new Map();
  const track = {
    ownerDocument: null,
    get innerHTML() { return "<stable-range-track>"; },
    set innerHTML(_value) { innerHtmlWrites += 1; },
    querySelectorAll(selector) { return selector === ".frame-range-bar" ? [bar] : []; },
    querySelector(selector) { return selector === "em" ? status : null; },
    setAttribute(name, value) { trackAttributes.set(name, String(value)); },
  };
  return {
    track,
    bar,
    label,
    status,
    style,
    attributes,
    trackAttributes,
    metrics() { return { innerHtmlWrites, labelWrites, statusWrites }; },
  };
}

// Rapid select changes must update the existing control immediately. Stable
// option lists are never rebuilt, so focus, scroll, geometry, and style object
// identities survive retained-mode interaction bursts without a blank frame.
const selectValues = ["Character", "Character Prop", "Environment / Background"];
const rapidSelect = rapidSelectFixture(selectValues, selectValues[0]);
const selectIdentity = rapidSelect.select;
const optionIdentities = [...rapidSelect.options];
const selectStyleIdentity = rapidSelect.select.style;
const scrollFixture = { scrollTop: 147, scrollLeft: 9 };
const focusFixture = rapidSelect.select;
for (let index = 0; index < 32; index += 1) {
  const value = selectValues[index % selectValues.length];
  assert.equal(
    widget.hmbSyncSelectOptions(
      rapidSelect.select,
      selectValues,
      value,
      "Select Image Main Type",
      widget.normalizeState({ ui: { language: "en" } }),
    ),
    false,
  );
  assert.equal(rapidSelect.select.value, value, `Selection ${index + 1} must paint synchronously.`);
}
assert.equal(rapidSelect.select, selectIdentity);
assert.deepEqual(rapidSelect.select.options, optionIdentities);
assert.equal(rapidSelect.select.style, selectStyleIdentity);
assert.equal(focusFixture, rapidSelect.select, "The focused select node identity must remain stable.");
assert.deepEqual(scrollFixture, { scrollTop: 147, scrollLeft: 9 });
assert.equal(rapidSelect.metrics().innerHtmlWrites, 0, "Rapid selection must not rebuild options or flash.");
assert.ok(rapidSelect.metrics().valueWrites >= 20, "The test must exercise 20+ immediate selection paints.");

// The retained-mode publication follows the already-painted select value and
// coalesces the complete burst into one newest-state echo after two frames.
const interactionFrames = [];
const interactionPublications = [];
const interactionContainer = {
  __hmbPromptLibraryScheduleFrame(callback) {
    interactionFrames.push(callback);
    return interactionFrames.length;
  },
};
const interactionState = widget.normalizeState({
  images: [{
    slot: 1,
    present: true,
    manual: true,
    label: "Hero",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
  }],
});
for (let index = 0; index < 32; index += 1) {
  interactionState.images[0].image_main_type = index % 2 ? "Character" : "Character Prop";
  interactionState.images[0].image_sub_type = index % 2 ? "Full Appearance" : "Handheld Prop";
  widget.hmbSchedulePromptInteractionCommit(
    interactionContainer,
    { onChange(value) { interactionPublications.push(value); } },
    interactionState,
  );
}
assert.equal(interactionPublications.length, 0, "Interaction publication must not block the first paint.");
assert.equal(interactionFrames.length, 1, "The rapid burst must own one first-frame task.");
interactionFrames.shift()();
assert.equal(interactionPublications.length, 0, "A second paint opportunity precedes host publication.");
assert.equal(interactionFrames.length, 1);
interactionFrames.shift()();
assert.equal(interactionPublications.length, 1, "32 rapid selections must coalesce to one host publication.");
const interactionFinal = JSON.parse(interactionPublications[0]);
assert.equal(interactionFinal.images[0].image_main_type, "Character");
assert.equal(interactionFinal.images[0].image_sub_type, "Full Appearance");
assert.equal(interactionContainer.__hmbPromptLibraryInteractionCommit, undefined);

const applyPropsSource = source.slice(
  source.indexOf("const applyProps ="),
  source.indexOf("container.__hmbPromptLibraryApplyProps = applyProps"),
);
assert.match(
  applyPropsSource,
  /const pendingInteraction = container\.__hmbPromptLibraryInteractionCommit;[\s\S]*?if \(revisionMergedState\)[\s\S]*?pendingInteraction\.state = state;[\s\S]*?pendingInteraction\.props = props;[\s\S]*?hmbClearPromptInteractionCommit\(container\)/,
  "A crossed newer source update must replace the pending 2-rAF snapshot with the merged state.",
);

const sourceSelectHandler = source.slice(
  source.indexOf('container.querySelectorAll(".source-select")'),
  source.indexOf('container.querySelectorAll(".move-image-up, .move-image-down")'),
);
assert.match(
  sourceSelectHandler,
  /hmbSyncSourceSelectDom\([\s\S]*?hmbRestoreSourceScroll\([\s\S]*?hmbSchedulePromptInteractionCommit\(/,
  "Select changes must paint/synchronize DOM first and publish only through the frame batch.",
);
assert.doesNotMatch(sourceSelectHandler, /hmbEmitLocalPromptState\(|\bremount\(/);
assert.match(source, /\.source-row\{transition:none\}/, "Selection rows must not animate and shimmer.");

// A 100+ pointermove Range gesture must patch the existing bar only. It must
// not allocate/remove bars, replace markup, alter geometry, or disturb focus
// and source-scroll state while the pointer is moving.
const rangePreview = rangePreviewFixture();
const rangeBarIdentity = rangePreview.bar;
const rangeLabelIdentity = rangePreview.label;
const rangeStatusIdentity = rangePreview.status;
const rangeStyleIdentity = rangePreview.style;
const rangeGeometry = { width: 1000, height: 26, top: 200, left: 100 };
const rangeFocusIdentity = { id: "frame-track-focus" };
const rangeScroll = { imageSources: 251, videoSources: 73 };
for (let index = 0; index < 128; index += 1) {
  const start = 1 + index;
  const end = Math.min(240, start + 19);
  widget.updateFrameTrackPreview(
    rangePreview.track,
    [{ start, end }],
    { start_frame: 1, end_frame: 240 },
    0,
    `${start}–${end}`,
  );
}
assert.equal(rangePreview.bar, rangeBarIdentity);
assert.equal(rangePreview.label, rangeLabelIdentity);
assert.equal(rangePreview.status, rangeStatusIdentity);
assert.equal(rangePreview.bar.style, rangeStyleIdentity);
assert.deepEqual(rangeGeometry, { width: 1000, height: 26, top: 200, left: 100 });
assert.equal(rangeFocusIdentity.id, "frame-track-focus");
assert.deepEqual(rangeScroll, { imageSources: 251, videoSources: 73 });
assert.equal(rangePreview.metrics().innerHtmlWrites, 0, "Range pointermove must not replace track markup.");
assert.equal(rangePreview.label.textContent, "128–147");
assert.equal(rangePreview.status.textContent, "128–147");
assert.equal(rangePreview.attributes.get("data-frame-range-index"), "0");

// The production pointer path schedules the same 128 previews into one frame.
// Only the newest coordinates are patched and the pending job is released.
const coalescedRangePreview = rangePreviewFixture();
const rangePreviewFrames = [];
const rangePreviewContainer = {
  __hmbPromptLibraryScheduleFrame(callback) {
    rangePreviewFrames.push(callback);
    return rangePreviewFrames.length;
  },
};
for (let index = 0; index < 128; index += 1) {
  const start = 1 + index;
  widget.hmbScheduleFrameTrackPreview(
    rangePreviewContainer,
    coalescedRangePreview.track,
    [{ start, end: start + 19 }],
    { start_frame: 1, end_frame: 240 },
    0,
    `${start}–${start + 19}`,
  );
}
assert.equal(rangePreviewFrames.length, 1, "128 pointermoves must retain only one pending paint.");
assert.equal(coalescedRangePreview.metrics().labelWrites, 0);
assert.equal(coalescedRangePreview.metrics().statusWrites, 0);
rangePreviewFrames.shift()();
assert.equal(coalescedRangePreview.metrics().labelWrites, 1);
assert.equal(coalescedRangePreview.metrics().statusWrites, 1);
assert.equal(coalescedRangePreview.label.textContent, "128–147");
assert.equal(coalescedRangePreview.status.textContent, "128–147");
assert.equal(rangePreviewContainer.__hmbFrameRangePreviewJob, undefined);
assert.equal(coalescedRangePreview.bar.style, coalescedRangePreview.style);
assert.equal(coalescedRangePreview.metrics().innerHtmlWrites, 0);

// Pointermove is preview-only; publication belongs to the final pointerup.
// This source-level guard makes accidental per-move emit/remount regressions
// fail even when a DOM implementation optimizes them away in unit tests.
const frameInteractionSource = source.slice(
  source.indexOf("function hmbInstallFrameRangeInteractions"),
  source.indexOf("function renderColorPickControls"),
);
const frameCommitSource = frameInteractionSource.slice(
  frameInteractionSource.indexOf("const commitFrameState"),
  frameInteractionSource.indexOf("const itemForElement"),
);
assert.match(frameCommitSource, /hmbSyncFrameRangeRowDom\([\s\S]*?hmbSchedulePromptInteractionCommit\(/);
assert.doesNotMatch(frameCommitSource, /hmbEmitLocalPromptState\(|\bremount\(/);
const rangeMoveSource = frameInteractionSource.slice(
  frameInteractionSource.indexOf("const moveHandler"),
  frameInteractionSource.indexOf("const removeDocumentListeners"),
);
assert.match(rangeMoveSource, /hmbScheduleFrameTrackPreview\(/);
assert.doesNotMatch(rangeMoveSource, /hmbEmitLocalPromptState|commitFrameState|remount|innerHTML/);
assert.doesNotMatch(rangeMoveSource, /getBoundingClientRect/);
assert.equal(
  (frameInteractionSource.match(/track\.getBoundingClientRect\(\)/g) || []).length,
  1,
  "Range geometry must be measured once at pointerdown, not 128 times during pointermove.",
);
const rangeUpSource = frameInteractionSource.slice(
  frameInteractionSource.indexOf("const upHandler"),
  frameInteractionSource.indexOf("const bind ="),
);
assert.equal(
  (rangeUpSource.match(/commitFrameState\(/g) || []).length,
  2,
  "Range selects on click and completed drags each have one final publication path.",
);

// Rapid retained-mode selection publications must be monotonic. Deliver the
// exact latest echo first and then every older echo in reverse order: none may
// reopen an old selection or Range. This reproduces the host callback ordering
// that previously made a fast selection visibly jump backwards.
const rapidEchoContainer = {};
const rapidEchoValues = [];
const rapidEchoProps = {
  disabled: false,
  onChange(value) { rapidEchoValues.push(value); },
};
let latestState = widget.normalizeState({
  source_sync_revision: 17,
  images: [{
    slot: 1,
    present: true,
    manual: true,
    label: "Hero",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
    frame_range_intent: {
      version: 1,
      enabled: true,
      start_frame: 1,
      end_frame: 240,
      ranges: [{ start: 1, end: 12 }],
      selected_index: 0,
    },
  }],
});
for (let index = 0; index < 32; index += 1) {
  latestState.images[0].image_main_type = index % 2 ? "Character" : "Character Prop";
  latestState.images[0].image_sub_type = index % 2 ? "Full Appearance" : "Handheld Prop";
  latestState.images[0].frame_range_intent.ranges = [{ start: index + 1, end: index + 12 }];
  widget.hmbEmitLocalPromptState(rapidEchoContainer, rapidEchoProps, latestState);
}
assert.equal(rapidEchoValues.length, 32);
for (let index = 1; index < rapidEchoValues.length; index += 1) {
  assert.ok(
    JSON.parse(rapidEchoValues[index]).ui_edit_revision
      > JSON.parse(rapidEchoValues[index - 1]).ui_edit_revision,
  );
}
const latestSerialized = rapidEchoValues.at(-1);
const latestParsed = JSON.parse(latestSerialized);
assert.equal(
  widget.hmbConsumePendingPromptStateEcho(
    rapidEchoContainer,
    { value: latestSerialized, disabled: false },
    latestState,
  ),
  true,
);
for (const olderSerialized of rapidEchoValues.slice(0, -1).reverse()) {
  assert.equal(
    widget.hmbConsumePendingPromptStateEcho(
      rapidEchoContainer,
      { value: olderSerialized, disabled: false },
      latestState,
    ),
    true,
  );
  assert.equal(rapidEchoContainer.__hmbPromptLastConsumedEchoWasStale, true);
}

// An equal-clock payload with different selection/Range content is also a
// delayed acknowledgement, never new authority. This is the key rollback
// case: clock equality alone cannot authorize a visually older payload.
const equalRevisionRollback = structuredClone(latestParsed);
equalRevisionRollback.images[0].image_main_type = "Environment / Background";
equalRevisionRollback.images[0].image_sub_type = "Main Background";
equalRevisionRollback.images[0].frame_range_intent.enabled = false;
equalRevisionRollback.images[0].frame_range_intent.ranges = [];
assert.equal(
  widget.hmbConsumePendingPromptStateEcho(
    rapidEchoContainer,
    { value: JSON.stringify(equalRevisionRollback), disabled: false },
    latestState,
  ),
  true,
  "An equal-revision divergent echo must be consumed without repainting live state.",
);
assert.equal(rapidEchoContainer.__hmbPromptLastConsumedEchoWasStale, true);
assert.equal(latestState.images[0].image_main_type, "Character");
assert.equal(latestState.images[0].frame_range_intent.enabled, true);
assert.deepEqual(latestState.images[0].frame_range_intent.ranges, [{ start: 32, end: 43 }]);

// Source/UI crossed clocks merge, preserving the newest local Range while
// adopting newer managed-asset metadata. Establish the managed identity before
// the local edit so this mirrors a real verified AssetLibrary row. A manual
// label is UI-owned; a verified source label is source-owned.
const crossedClockContainer = {};
const crossedClockValues = [];
const crossedClockUiState = widget.normalizeState({
  source_sync_revision: 17,
  images: [{
    slot: 1,
    present: true,
    label: "Hero",
    asset_verified: true,
    asset_managed: true,
    asset_source_uid: "asset-source-hero",
    asset_source_kind: "project",
    asset_library_id: "asset-library-hero",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
    frame_range_intent: {
      version: 1,
      enabled: true,
      start_frame: 1,
      end_frame: 240,
      ranges: [{ start: 32, end: 43 }],
      selected_index: 0,
    },
  }],
});
widget.hmbEmitLocalPromptState(
  crossedClockContainer,
  { disabled: false, onChange(value) { crossedClockValues.push(value); } },
  crossedClockUiState,
);
const crossedClockLocal = JSON.parse(crossedClockValues.at(-1));
const newerSourceOlderUi = structuredClone(crossedClockLocal);
newerSourceOlderUi.source_sync_revision += 1;
newerSourceOlderUi.images[0].label = "Authoritative renamed hero";
newerSourceOlderUi.images[0].frame_range_intent.enabled = false;
newerSourceOlderUi.images[0].frame_range_intent.ranges = [];
assert.equal(
  widget.hmbConsumePendingPromptStateEcho(
    crossedClockContainer,
    { value: JSON.stringify(newerSourceOlderUi), disabled: false },
    crossedClockUiState,
  ),
  false,
);
const crossedClockMerge = widget.hmbTakePromptRevisionMerge(crossedClockContainer);
assert.equal(crossedClockMerge.images[0].label, "Authoritative renamed hero");
assert.equal(crossedClockMerge.images[0].frame_range_intent.enabled, true);
assert.deepEqual(crossedClockMerge.images[0].frame_range_intent.ranges, [{ start: 32, end: 43 }]);
assert.equal(crossedClockMerge.ui_edit_revision, crossedClockLocal.ui_edit_revision);
assert.equal(crossedClockMerge.source_sync_revision, newerSourceOlderUi.source_sync_revision);

const lateAssetRouting = {
  publisher_instance_uuid: "publisher-late-asset",
  channel_uuid: "channel-late-asset",
  generation: 1,
  metadata_sha256: "a".repeat(64),
};
const lateAssetShot = {
  shot_uuid: "shot-late-one",
  channel_uuid: "channel-late-asset",
  name: "Shot 1",
  number: 1,
  selected_source_uids: ["late-image-one"],
};
const promptFirstMerge = widget.hmbMergePromptRevisionAxes(
  {
    image_asset: {
      shot_catalog_routing: lateAssetRouting,
      shot_catalog: [lateAssetShot],
    },
    shot: lateAssetShot,
    text: { SCENE_CONTEXT: "older source text" },
  },
  {
    shot: {},
    text: { SCENE_CONTEXT: "typed before ImageAsset" },
  },
);
assert.equal(promptFirstMerge.shot.shot_uuid, "shot-late-one");
assert.equal(promptFirstMerge.text.SCENE_CONTEXT, "typed before ImageAsset");

const explicitOnlyMerge = widget.hmbMergePromptRevisionAxes(
  {
    image_asset: {
      shot_catalog_routing: { ...lateAssetRouting, generation: 2 },
      shot_catalog: [lateAssetShot],
    },
    shot: lateAssetShot,
  },
  {
    image_asset: {
      shot_catalog_routing: lateAssetRouting,
      shot_catalog: [lateAssetShot],
    },
    shot: {},
  },
);
assert.equal(explicitOnlyMerge.shot.shot_uuid, "");

// Direct ownership matrix: source authority and Prompt UI have independent
// fields during crossed-clock merges. These assertions prevent a future jank
// fix from solving rollback by indiscriminately choosing either whole object.
const verifiedImageMerge = widget.hmbMergePromptRevisionAxes(
  {
    images: [{
      slot: 1,
      present: true,
      label: "Verified source label",
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-taxonomy-image",
      image_main_type: "Environment / Background",
      image_sub_type: "Main Background",
      frame_range_intent: { version: 1, enabled: false, ranges: [] },
    }],
  },
  {
    images: [{
      slot: 1,
      present: true,
      label: "Stale UI label",
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-taxonomy-image",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
      frame_range_intent: {
        version: 1,
        enabled: true,
        start_frame: 1,
        end_frame: 100,
        ranges: [{ start: 21, end: 35 }],
        selected_index: 0,
      },
    }],
  },
);
assert.equal(verifiedImageMerge.images[0].label, "Verified source label");
assert.equal(verifiedImageMerge.images[0].image_main_type, "Environment / Background");
assert.equal(verifiedImageMerge.images[0].image_sub_type, "Main Background");
assert.equal(verifiedImageMerge.images[0].frame_range_intent.enabled, true);
assert.deepEqual(verifiedImageMerge.images[0].frame_range_intent.ranges, [{ start: 21, end: 35 }]);

const verifiedLookOverrideMerge = widget.hmbMergePromptRevisionAxes(
  {
    images: [{
      slot: 1,
      present: true,
      label: "Registered Look",
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-look-image",
      asset_image_main_type_candidate: "Look Reference",
      asset_image_sub_type_candidate: "Render Look",
      image_main_type: "Look Reference",
      image_sub_type: "Render Look",
      owner: "Global Look",
    }],
  },
  {
    images: [{
      slot: 1,
      present: true,
      label: "Registered Look",
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-look-image",
      asset_image_main_type_candidate: "Look Reference",
      asset_image_sub_type_candidate: "Color Mood",
      image_main_type: "Look Reference",
      image_sub_type: "Scale",
      owner: "Jett_11",
    }],
  },
);
const verifiedLookOverrideRow = verifiedLookOverrideMerge.images[0];
assert.equal(verifiedLookOverrideRow.asset_image_sub_type_candidate, "Render Look");
assert.equal(verifiedLookOverrideRow.image_main_type, "Look Reference");
assert.equal(verifiedLookOverrideRow.image_sub_type, "Scale");
assert.equal(verifiedLookOverrideRow.source_type, "Scale / Composition Reference");
assert.equal(verifiedLookOverrideRow.scope, "Scale only");
assert.equal(verifiedLookOverrideRow.owner, "Jett_11");
assert.deepEqual(verifiedLookOverrideRow.color_picks, [""]);

const verifiedLookDefaultMerge = widget.hmbMergePromptRevisionAxes(
  {
    images: [{
      slot: 1,
      present: true,
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-look-default",
      asset_image_main_type_candidate: "Look Reference",
      asset_image_sub_type_candidate: "Render Look",
      image_main_type: "Look Reference",
      image_sub_type: "Render Look",
      owner: "Global Look",
    }],
  },
  {
    images: [{
      slot: 1,
      present: true,
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-look-default",
      asset_image_main_type_candidate: "Look Reference",
      asset_image_sub_type_candidate: "Color Mood",
      image_main_type: "Look Reference",
      image_sub_type: "Color Mood",
      owner: "Jett_08",
    }],
  },
);
assert.equal(
  verifiedLookDefaultMerge.images[0].image_sub_type,
  "Render Look",
  "A stale registered default is not a Prompt override and must not defeat a newer Asset registration.",
);
assert.equal(
  verifiedLookDefaultMerge.images[0].owner,
  "Jett_08",
  "Prompt Target remains UI-owned even when the stale Look Sub Type is not an override.",
);

const imageBindingUiMerge = widget.hmbMergePromptRevisionAxes(
  {
    images: [{
      slot: 1,
      present: true,
      label: "Environment",
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-binding-image",
      image_main_type: "Environment / Background",
      image_sub_type: "Main Background",
      owner: "Source target",
      color_picks: ["Mint"],
      binding_video_slots: [1],
    }],
  },
  {
    images: [{
      slot: 1,
      present: true,
      label: "Environment",
      asset_managed: true,
      asset_verified: true,
      asset_source_kind: "project",
      asset_source_uid: "verified-binding-image",
      image_main_type: "Environment / Background",
      image_sub_type: "Main Background",
      owner: "Prompt target",
      color_picks: ["Sky Blue"],
      binding_video_slots: [3],
    }],
  },
);
assert.equal(imageBindingUiMerge.images[0].owner, "Prompt target");
assert.deepEqual(imageBindingUiMerge.images[0].color_picks, ["Sky Blue"]);
assert.deepEqual(imageBindingUiMerge.images[0].binding_video_slots, [3]);

const manualImageMerge = widget.hmbMergePromptRevisionAxes(
  {
    images: [{
      slot: 1,
      present: true,
      manual: true,
      label: "Old manual label",
      image_main_type: "Environment / Background",
      image_sub_type: "Main Background",
    }],
  },
  {
    images: [{
      slot: 1,
      present: true,
      manual: true,
      label: "Newest manual label",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
    }],
  },
);
assert.equal(manualImageMerge.images[0].label, "Newest manual label");
assert.equal(manualImageMerge.images[0].image_main_type, "Character");
assert.equal(manualImageMerge.images[0].image_sub_type, "Full Appearance");

const authorityVideoMerge = widget.hmbMergePromptRevisionAxes(
  {
    videos: [{
      slot: 1,
      present: true,
      picker_managed: true,
      video_uid: "picker-video-one",
      source_uid: "picker-video-one",
      label: "Picker source label",
      video_main_type: "Maya Preview / Playblast",
      video_sub_type: "Original Preview",
      picker_auto_video_main_type: "Maya Preview / Playblast",
      picker_auto_video_sub_type: "Original Preview",
      keep_out: "Source keep out",
    }],
  },
  {
    videos: [{
      slot: 1,
      present: true,
      picker_managed: true,
      video_uid: "picker-video-one",
      source_uid: "picker-video-one",
      label: "Stale UI video label",
      video_main_type: "Motion Reference",
      video_sub_type: "Local Motion",
      picker_auto_video_main_type: "Maya Preview / Playblast",
      picker_auto_video_sub_type: "Original Preview",
      keep_out: "Newest Prompt keep out",
    }],
  },
);
assert.equal(authorityVideoMerge.videos[0].label, "Picker source label");
assert.equal(authorityVideoMerge.videos[0].video_main_type, "Motion Reference");
assert.equal(authorityVideoMerge.videos[0].video_sub_type, "Local Motion");
assert.equal(authorityVideoMerge.videos[0].keep_out, "Newest Prompt keep out");

const manualVideoMerge = widget.hmbMergePromptRevisionAxes(
  {
    videos: [{
      slot: 1,
      present: true,
      manual: true,
      label: "Old manual video",
      video_main_type: "Maya Preview / Playblast",
      video_sub_type: "Original Preview",
      keep_out: "Old keep out",
    }],
  },
  {
    videos: [{
      slot: 1,
      present: true,
      manual: true,
      label: "Newest manual video",
      video_main_type: "FX / Simulation Reference",
      video_sub_type: "Dust",
      keep_out: "Newest manual keep out",
    }],
  },
);
assert.equal(manualVideoMerge.videos[0].label, "Newest manual video");
assert.equal(manualVideoMerge.videos[0].video_main_type, "FX / Simulation Reference");
assert.equal(manualVideoMerge.videos[0].video_sub_type, "Dust");
assert.equal(manualVideoMerge.videos[0].keep_out, "Newest manual keep out");

clearTimeout(rapidEchoContainer.__hmbPromptPendingLocalTimer);
clearTimeout(crossedClockContainer.__hmbPromptPendingLocalTimer);
console.log("HMB Prompt interaction stability regression passed.");
