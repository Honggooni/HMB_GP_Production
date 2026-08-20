import assert from "node:assert/strict";
import fs from "node:fs";


async function importSource(path) {
  const source = fs.readFileSync(path, "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}


const promptPath = new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url);
const pickerPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const promptSource = fs.readFileSync(promptPath, "utf8");
const prompt = await importSource(promptPath);
const picker = await importSource(pickerPath);

assert.deepEqual(
  prompt.normalizeFrameRanges([
    { start: 97, end: 120 },
    { start: 1, end: 48 },
    { start: 121, end: 144 },
    { start: 40, end: 60 },
  ]),
  [
    { start: 1, end: 60 },
    { start: 97, end: 144 },
  ],
);

const image = {
  slot: 1,
  label: "Hero",
  present: true,
  source_type: "Character Appearance",
  owner: "Hero",
  scope: "Full body / full appearance",
  binding_scopes: ["Full body / full appearance"],
  binding_custom_scopes: [""],
  binding_video_slots: [3],
  marker_video: 3,
  color_picks: ["Green"],
  frame_range_enabled: true,
  frame_range_color_index: 0,
  frame_range_bindings: {},
  frame_range_selected_index: -1,
};
const state = {
  ui: { language: "en" },
  images: [image],
  videos: [
    { slot: 1, label: "primary", present: true, source_type: "Maya Preview / Playblast" },
    { slot: 2, label: "aux2", present: true, source_type: "Motion Reference" },
    { slot: 3, label: "aux3", present: true, source_type: "Motion Reference" },
  ],
  picker: {
    enabled: true,
    awaiting_data: false,
    suppressed: false,
    frame_metadata: [
      {
        video_slot: "@video3",
        fps: 24,
        start_frame: 1,
        end_frame: 144,
        frame_count: 144,
        duration_seconds: 6,
        timebase: "24/1",
        available_color_picks: ["Green", "Blue"],
        conflict: false,
        valid: true,
        warnings: [],
      },
    ],
  },
};

prompt.storeCurrentFrameDomain(image, 1, 144);
prompt.storeCurrentFrameRanges(image, [
  { start: 97, end: 144 },
  { start: 1, end: 48 },
], 0);
assert.deepEqual(image.frame_range_bindings["@video3::Green"].ranges, [
  { start: 1, end: 48 },
  { start: 97, end: 144 },
]);
assert.equal(prompt.frameRangeUiStatus(state, image).canEnable, true);
assert.equal(prompt.frameRangeUiStatus(state, image).status, "2 RANGES");

const manualImage = {
  ...image,
  color_picks: ["Green"],
  frame_range_bindings: {
    "@video3::Green": {
      video_slot: "@video3",
      color_pick: "Green",
      origin: "manual",
      start_frame: 1001,
      end_frame: 1120,
      ranges: [{ start: 1010, end: 1020 }],
    },
  },
  frame_range_binding: null,
  frame_range_selected_index: 0,
};
const manualState = {
  ...state,
  images: [manualImage],
  picker: {
    ...state.picker,
    enabled: false,
    awaiting_data: false,
    suppressed: false,
    // Stale metadata must not lock a manually operated Range control.
    frame_metadata: state.picker.frame_metadata,
  },
};
const manualStatus = prompt.frameRangeUiStatus(manualState, manualImage);
assert.equal(manualStatus.canEnable, true, "Manual Range can be enabled without Picker.");
assert.equal(manualStatus.domainReadonly, false);
assert.equal(manualStatus.domainComplete, true);
assert.equal(manualStatus.metadata.origin, "manual");
assert.deepEqual(
  [manualStatus.domainStart, manualStatus.domainEnd],
  [1001, 1120],
);
assert.deepEqual(manualStatus.ranges, [{ start: 1010, end: 1020 }]);
assert.equal(prompt.frameDomainInputValue(0), "0000");
const zeroDomainImage = {
  ...manualImage,
  frame_range_bindings: {},
  frame_range_binding: null,
};
prompt.storeCurrentFrameDomain(zeroDomainImage, "0000", 0);
assert.deepEqual(
  [
    zeroDomainImage.frame_range_bindings["@video3::Green"].start_frame,
    zeroDomainImage.frame_range_bindings["@video3::Green"].end_frame,
  ],
  [0, 0],
  "Frame 0000 remains a valid persisted manual domain instead of becoming null.",
);
const zeroDomainStatus = prompt.frameRangeUiStatus(manualState, zeroDomainImage);
assert.deepEqual([zeroDomainStatus.domainStart, zeroDomainStatus.domainEnd], [0, 0]);
assert.equal(zeroDomainStatus.domainComplete, true);

const legacyEndpointImage = {
  ...manualImage,
  frame_range_binding: {
    video_slot: "@video3",
    color_pick: "Green",
    origin: "manual",
    manual_start_frame: 1001,
    manual_end_frame: 1120,
    ranges: [],
  },
  frame_range_bindings: {
    "@video3::Green": {
      video_slot: "@video3",
      color_pick: "Green",
      origin: "manual",
      ranges: [{ start: 1010, end: 1020 }],
    },
  },
};
const legacyEndpointStatus = prompt.frameRangeUiStatus(manualState, legacyEndpointImage);
assert.deepEqual(
  [legacyEndpointStatus.domainStart, legacyEndpointStatus.domainEnd],
  [1001, 1120],
  "Legacy endpoint aliases survive a canonical range-map entry that omits the domain.",
);
assert.deepEqual(legacyEndpointStatus.ranges, [{ start: 1010, end: 1020 }]);

prompt.storeCurrentFrameDomain(manualImage, 12, null);
let partialManualStatus = prompt.frameRangeUiStatus(manualState, manualImage);
assert.equal(partialManualStatus.canEnable, true);
assert.equal(partialManualStatus.domainComplete, false);
assert.equal(partialManualStatus.status, "SET START / END · OPTIONAL");
const koreanPartialStatus = prompt.frameRangeUiStatus(
  { ...manualState, ui: { ...(manualState.ui || {}), language: "ko" } },
  manualImage,
);
assert.equal(koreanPartialStatus.status, "시작 / 끝 입력 (선택 사항)");
assert.equal(
  manualImage.frame_range_bindings["@video3::Green"].start_frame,
  12,
);
assert.equal(
  manualImage.frame_range_bindings["@video3::Green"].end_frame,
  null,
);
prompt.storeCurrentFrameDomain(manualImage, 12, 34);
partialManualStatus = prompt.frameRangeUiStatus(manualState, manualImage);
assert.equal(partialManualStatus.domainComplete, true);
assert.deepEqual(
  [partialManualStatus.domainStart, partialManualStatus.domainEnd],
  [12, 34],
);

const pickerPriorityImage = {
  ...manualImage,
  frame_range_bindings: {
    "@video3::Green": {
      video_slot: "@video3",
      color_pick: "Green",
      origin: "manual",
      start_frame: 1001,
      end_frame: 1120,
      ranges: [{ start: 1010, end: 1020 }],
    },
  },
};
const pickerPriorityStatus = prompt.frameRangeUiStatus(
  { ...state, images: [pickerPriorityImage] },
  pickerPriorityImage,
);
assert.equal(pickerPriorityStatus.domainReadonly, false);
assert.equal(pickerPriorityStatus.metadata.origin, "manual");
assert.deepEqual(
  [pickerPriorityStatus.domainStart, pickerPriorityStatus.domainEnd],
  [1001, 1120],
  "Picker metadata never replaces the manually authored frame domain.",
);
assert.deepEqual(
  pickerPriorityStatus.suggestedDomain,
  { start_frame: 1, end_frame: 144 },
  "A valid Picker domain remains available only as a non-authoritative suggestion.",
);
const suggestionOnlyImage = {
  ...pickerPriorityImage,
  frame_range_bindings: {},
  frame_range_binding: null,
  frame_range_selected_index: -1,
};
const suggestionOnlyStatus = prompt.frameRangeUiStatus(
  { ...state, images: [suggestionOnlyImage] },
  suggestionOnlyImage,
);
assert.equal(suggestionOnlyStatus.domainReadonly, false);
assert.deepEqual(
  [suggestionOnlyStatus.domainStart, suggestionOnlyStatus.domainEnd],
  [null, null],
  "Even valid Picker endpoints never auto-fill a blank manual domain.",
);
assert.equal(suggestionOnlyStatus.domainComplete, false);
assert.deepEqual(
  suggestionOnlyStatus.suggestedDomain,
  { start_frame: 1, end_frame: 144 },
);
const unknownPickerColorsStatus = prompt.frameRangeUiStatus(
  {
    ...state,
    picker: {
      ...state.picker,
      frame_metadata: state.picker.frame_metadata.map((entry) => ({
        ...entry,
        available_color_picks: [],
      })),
    },
  },
  pickerPriorityImage,
);
assert.equal(
  unknownPickerColorsStatus.reason,
  "",
  "An empty Picker color catalog means unknown authority, not an explicit Color Pick rejection.",
);
assert.equal(unknownPickerColorsStatus.domainReadonly, false);
assert.deepEqual(
  [unknownPickerColorsStatus.domainStart, unknownPickerColorsStatus.domainEnd],
  [1001, 1120],
);

const externalVideoImage = {
  ...image,
  color_picks: ["Green"],
  frame_range_enabled: true,
  frame_range_bindings: {},
  frame_range_binding: null,
  frame_range_selected_index: -1,
};
const incompleteExternalState = {
  ...state,
  images: [externalVideoImage],
  picker: {
    ...state.picker,
    frame_metadata: [{
      video_slot: "@video3",
      fps: 0,
      start_frame: 1,
      end_frame: 0,
      frame_count: 0,
      available_color_picks: ["Green"],
      origin: "external",
      valid: false,
      conflict: false,
      warnings: ["External video end frame is unavailable."],
    }],
  },
};
let externalStatus = prompt.frameRangeUiStatus(incompleteExternalState, externalVideoImage);
assert.equal(externalStatus.domainReadonly, false, "Incomplete external metadata must never lock Range inputs.");
assert.deepEqual(
  [externalStatus.domainStart, externalStatus.domainEnd],
  [null, null],
  "Picker endpoints never populate the user's blank manual domain.",
);
assert.equal(externalStatus.domainComplete, false);
assert.equal(externalStatus.domainInvalid, false);
assert.equal(externalStatus.suggestedDomain, null);

// The user authors both endpoints explicitly; Picker never supplies either
// half of the canonical domain.
prompt.storeCurrentFrameDomain(externalVideoImage, 1, 120);
externalStatus = prompt.frameRangeUiStatus(incompleteExternalState, externalVideoImage);
assert.equal(externalStatus.domainReadonly, false);
assert.equal(externalStatus.domainComplete, true);
assert.equal(externalStatus.domainInvalid, false);
assert.equal(externalStatus.metadata.origin, "manual");
assert.deepEqual([externalStatus.domainStart, externalStatus.domainEnd], [1, 120]);
assert.equal(externalStatus.reason, "");

// An out-of-order rapid edit remains visible and editable so the following
// edit can correct it; validation must not silently swap or erase intent.
prompt.storeCurrentFrameDomain(externalVideoImage, 121, externalStatus.domainEnd);
externalStatus = prompt.frameRangeUiStatus(incompleteExternalState, externalVideoImage);
assert.deepEqual([externalStatus.domainStart, externalStatus.domainEnd], [121, 120]);
assert.equal(externalStatus.domainReadonly, false);
assert.equal(externalStatus.domainComplete, false);
assert.equal(externalStatus.domainInvalid, true);
prompt.storeCurrentFrameDomain(externalVideoImage, externalStatus.domainStart, 144);
externalStatus = prompt.frameRangeUiStatus(incompleteExternalState, externalVideoImage);
assert.deepEqual([externalStatus.domainStart, externalStatus.domainEnd], [121, 144]);
assert.equal(externalStatus.domainComplete, true);

const blankColorExternalImage = {
  ...externalVideoImage,
  color_picks: [""],
  frame_range_bindings: {},
  frame_range_binding: null,
  frame_range_selected_index: -1,
};
const blankColorExternalState = {
  ...incompleteExternalState,
  images: [blankColorExternalImage],
  picker: {
    ...incompleteExternalState.picker,
    frame_metadata: incompleteExternalState.picker.frame_metadata.map((entry) => ({
      ...entry,
      available_color_picks: [],
    })),
  },
};
let blankColorExternalStatus = prompt.frameRangeUiStatus(
  blankColorExternalState,
  blankColorExternalImage,
);
assert.equal(blankColorExternalStatus.color, "");
assert.equal(blankColorExternalStatus.domainReadonly, false);
assert.deepEqual(
  [blankColorExternalStatus.domainStart, blankColorExternalStatus.domainEnd],
  [null, null],
  "A blank Color Pick keeps a blank, editable manual domain.",
);
prompt.storeCurrentFrameDomain(
  blankColorExternalImage,
  1,
  96,
);
blankColorExternalStatus = prompt.frameRangeUiStatus(
  blankColorExternalState,
  blankColorExternalImage,
);
assert.deepEqual([blankColorExternalStatus.domainStart, blankColorExternalStatus.domainEnd], [1, 96]);
assert.equal(blankColorExternalStatus.domainReadonly, false);
assert.equal(blankColorExternalStatus.domainComplete, true);
assert.equal(blankColorExternalStatus.metadata.origin, "manual");
assert.equal(
  blankColorExternalStatus.reason,
  "",
  "Blank Color Pick plus an empty/unknown marker catalog is a video-wide manual Range.",
);
assert.deepEqual(
  blankColorExternalImage.frame_range_bindings["@video3::"],
  {
    video_slot: "@video3",
    color_pick: "",
    enabled: true,
    origin: "manual",
    ranges: [],
    start_frame: 1,
    end_frame: 96,
  },
  "The editable external domain must persist under the canonical blank-color binding key.",
);
prompt.storeCurrentFrameRanges(blankColorExternalImage, [{ start: 12, end: 24 }], 0);
blankColorExternalStatus = prompt.frameRangeUiStatus(
  blankColorExternalState,
  blankColorExternalImage,
);
assert.deepEqual(blankColorExternalStatus.ranges, [{ start: 12, end: 24 }]);
assert.equal(blankColorExternalStatus.domainComplete, true, "A completed blank-color domain enables track storage.");

const blankWithMarkerAuthorityStatus = prompt.frameRangeUiStatus(
  {
    ...blankColorExternalState,
    picker: {
      ...blankColorExternalState.picker,
      frame_metadata: blankColorExternalState.picker.frame_metadata.map((entry) => ({
        ...entry,
        available_color_picks: ["Green"],
      })),
    },
  },
  blankColorExternalImage,
);
assert.equal(
  blankWithMarkerAuthorityStatus.reason,
  "Select a Color Pick.",
  "A nonempty Picker marker catalog remains authoritative and requires a Color Pick.",
);

const missingExternalImage = {
  ...externalVideoImage,
  frame_range_bindings: {},
  frame_range_binding: null,
};
const missingExternalStatus = prompt.frameRangeUiStatus(
  {
    ...incompleteExternalState,
    images: [missingExternalImage],
    picker: { ...incompleteExternalState.picker, frame_metadata: [] },
  },
  missingExternalImage,
);
assert.equal(missingExternalStatus.domainReadonly, false);
assert.deepEqual([missingExternalStatus.domainStart, missingExternalStatus.domainEnd], [null, null]);
assert.equal(missingExternalStatus.domainComplete, false);

const rejectedCompleteStatus = prompt.frameRangeUiStatus(
  {
    ...incompleteExternalState,
    picker: {
      ...incompleteExternalState.picker,
      frame_metadata: [{
        video_slot: "@video3",
        fps: 0,
        start_frame: 1,
        end_frame: 120,
        frame_count: 0,
        available_color_picks: ["Green"],
        valid: false,
        conflict: false,
        warnings: ["Complete Picker domain failed validation."],
      }],
    },
  },
  missingExternalImage,
);
assert.equal(rejectedCompleteStatus.domainReadonly, false, "Known-invalid Picker metadata cannot lock manual Range inputs.");
assert.deepEqual([rejectedCompleteStatus.domainStart, rejectedCompleteStatus.domainEnd], [null, null]);
assert.equal(rejectedCompleteStatus.domainComplete, false);

const rejectedConflictStatus = prompt.frameRangeUiStatus(
  {
    ...incompleteExternalState,
    picker: {
      ...incompleteExternalState.picker,
      frame_metadata: [{
        video_slot: "@video3",
        fps: 24,
        start_frame: 1,
        end_frame: 0,
        frame_count: 120,
        available_color_picks: ["Green"],
        valid: false,
        conflict: true,
        warnings: ["Picker frame metadata conflicts."],
      }],
    },
  },
  missingExternalImage,
);
assert.equal(rejectedConflictStatus.domainReadonly, false, "Conflicting Picker metadata is not manual-domain authority.");
assert.deepEqual([rejectedConflictStatus.domainStart, rejectedConflictStatus.domainEnd], [null, null]);
assert.equal(rejectedConflictStatus.domainInvalid, false);

image.color_picks = ["Blue"];
prompt.storeCurrentFrameRanges(image, [{ start: 30, end: 40 }], 0);
assert.deepEqual(image.frame_range_bindings["@video3::Blue"].ranges, [{ start: 30, end: 40 }]);
assert.deepEqual(image.frame_range_bindings["@video3::Green"].ranges, [
  { start: 1, end: 48 },
  { start: 97, end: 144 },
]);

const resetImage = JSON.parse(JSON.stringify(manualImage));
resetImage.frame_range_bindings["@video2::Blue"] = {
  video_slot: "@video2",
  color_pick: "Blue",
  origin: "manual",
  start_frame: 1,
  end_frame: 10,
  ranges: [{ start: 2, end: 4 }],
};
assert.equal(prompt.setFrameRangeEnabled(resetImage, false), false);
assert.deepEqual(
  resetImage.frame_range_bindings["@video2::Blue"].ranges,
  [{ start: 2, end: 4 }],
  "Range OFF preserves dormant manual bindings.",
);
assert.deepEqual(
  resetImage.frame_range_bindings["@video3::Green"].ranges,
  [{ start: 1010, end: 1020 }],
);
assert.equal(resetImage.frame_range_selected_index, -1);
assert.equal(prompt.setFrameRangeEnabled(resetImage, true), true);
assert.deepEqual(
  resetImage.frame_range_bindings["@video3::Green"],
  {
    video_slot: "@video3",
    color_pick: "Green",
    enabled: true,
    origin: "manual",
    ranges: [{ start: 1010, end: 1020 }],
    start_frame: 12,
    end_frame: 34,
  },
  "Range ON resumes the preserved manual domain and marks that address active.",
);

const dormantImage = {
  ...image,
  color_picks: [""],
  binding_video_slots: [5],
  frame_range_enabled: false,
  frame_range_bindings: {},
  frame_range_binding: null,
};
assert.equal(prompt.setFrameRangeEnabled(dormantImage, true), true);
prompt.storeCurrentFrameDomain(dormantImage, 1001, 1050);
assert.deepEqual(
  dormantImage.frame_range_bindings["@video5::"],
  {
    video_slot: "@video5",
    color_pick: "",
    enabled: true,
    origin: "manual",
    ranges: [],
    start_frame: 1001,
    end_frame: 1050,
  },
  "No video connection or Color Pick is required to author dormant Range intent.",
);
assert.equal(prompt.frameRangeUiStatus({ images: [dormantImage], videos: [], picker: {} }, dormantImage).canEnable, true);

// Range authoring is a user-owned draft control.  It must remain usable even
// before a VideoPicker source, frame metadata, or a Color Pick exists.  The
// backend may keep this address dormant at execution time, but the widget must
// preserve the user's ON/OFF choice and manually entered domain meanwhile.
const unlockedDraftState = prompt.normalizeState({
  ui: { language: "en" },
  images: [{
    slot: 1,
    label: "Unconnected Hero",
    present: true,
    source_type: "Character Appearance",
    binding_scopes: ["Full body / full appearance"],
    binding_video_slots: [1],
    color_picks: [""],
    frame_range_enabled: false,
    frame_range_bindings: {},
    frame_range_binding: null,
  }],
  videos: [],
  picker: {
    enabled: false,
    awaiting_data: false,
    frame_metadata: [],
  },
});
const unlockedDraftImage = unlockedDraftState.images[0];
let unlockedDraftStatus = prompt.frameRangeUiStatus(unlockedDraftState, unlockedDraftImage);
assert.equal(unlockedDraftStatus.canEnable, true, "Range toggle stays enabled without media metadata.");
assert.match(unlockedDraftStatus.reason, /not an active video source/);
assert.equal(prompt.setFrameRangeEnabled(unlockedDraftImage, true), true);
prompt.storeCurrentFrameDomain(unlockedDraftImage, "0012", "0048");
unlockedDraftStatus = prompt.frameRangeUiStatus(unlockedDraftState, unlockedDraftImage);
assert.deepEqual([unlockedDraftStatus.domainStart, unlockedDraftStatus.domainEnd], [12, 48]);
assert.equal(unlockedDraftStatus.domainReadonly, false);
assert.equal(unlockedDraftImage.frame_range_bindings["@video1::"].origin, "manual");

const unlockedDraftPublications = [];
prompt.hmbEmitLocalPromptState(
  {},
  {
    disabled: false,
    onChange(value) { unlockedDraftPublications.push(JSON.parse(value)); },
  },
  unlockedDraftState,
);
assert.deepEqual(
  [
    unlockedDraftPublications[0].images[0].frame_range_bindings["@video1::"].start_frame,
    unlockedDraftPublications[0].images[0].frame_range_bindings["@video1::"].end_frame,
  ],
  [12, 48],
  "Manual START/END must survive the widget state publication without media/color metadata.",
);
assert.equal(prompt.setFrameRangeEnabled(unlockedDraftImage, false), false);
assert.deepEqual(
  [
    unlockedDraftImage.frame_range_bindings["@video1::"].start_frame,
    unlockedDraftImage.frame_range_bindings["@video1::"].end_frame,
  ],
  [12, 48],
  "Range OFF keeps the user's dormant manual domain.",
);
assert.equal(prompt.setFrameRangeEnabled(unlockedDraftImage, true), true);
assert.deepEqual(
  [
    prompt.frameRangeUiStatus(unlockedDraftState, unlockedDraftImage).domainStart,
    prompt.frameRangeUiStatus(unlockedDraftState, unlockedDraftImage).domainEnd,
  ],
  [12, 48],
  "Range ON restores the same editable manual domain.",
);

assert.equal(picker.formatFrameTimecode(67, 1, 24), "00:00:02:18");
assert.equal(picker.formatFrameTimecode(101, 101, 24), "00:00:00:00");

assert.match(promptSource, /data-frame-range-toggle/);
assert.match(promptSource, /data-frame-track/);
assert.match(promptSource, /data-frame-range-handle="start"/);
assert.match(promptSource, /data-frame-range-handle="end"/);
assert.match(promptSource, /movedPixels < 6/);
assert.match(promptSource, /document\.addEventListener\("pointermove", moveHandler, true\)/);
assert.match(promptSource, /document\.addEventListener\("pointerup", upHandler, true\)/);
assert.match(promptSource, /storeCurrentFrameRanges\(item, normalized/);
assert.match(
  promptSource,
  /\.source-row\.image>\.frame-binding-row\{grid-column:1\/5;grid-row:1;align-self:start;margin-top:38px\}/,
  "Wide IMAGE SOURCE BINDING rows reuse the blank area beneath NAME through SUB TYPE.",
);
assert.match(promptSource, /\.frame-binding-row\{grid-column:1\/-1;display:grid;grid-template-columns:3\.55rem minmax\(0,1fr\)/);
assert.match(promptSource, /padStart\(4, "0"\)/);
const frameInteractionSource = promptSource.slice(
  promptSource.indexOf("function hmbInstallFrameRangeInteractions"),
  promptSource.indexOf("function renderColorPickControls"),
);
assert.match(
  frameInteractionSource,
  /querySelectorAll\(\s*"\[data-frame-range-toggle\], \[data-frame-domain-number\]"/,
  "Only the compact Range toggle and full-domain inputs receive direct change handlers.",
);
assert.doesNotMatch(frameInteractionSource, /data-frame-range-number|frame-range-delete/);
assert.match(frameInteractionSource, /querySelectorAll\("\[data-frame-track\]"\)/);
assert.doesNotMatch(
  frameInteractionSource,
  /container\.addEventListener\("(?:change|click|keydown|pointerdown)"/,
  "Range controls must keep their direct handlers after the image-card gesture guard is released.",
);
assert.doesNotMatch(
  frameInteractionSource,
  /\bremount\b/,
  "A Range endpoint edit must patch its row and emit state without remounting or dropping input focus.",
);
const rangeToggleHasDirectPointerActivation = Boolean(
  /\.frame-range-toggle\{[^}]*pointer-events:(?!none)[^;}]+/s.test(promptSource)
  || /data-frame-range-toggle[^\n]*addEventListener\(["']click["']/s.test(frameInteractionSource)
  || /bind\([^\n]*data-frame-range-toggle[^\n]*["']click["']/s.test(frameInteractionSource)
  || /querySelectorAll\([^)]*data-frame-range-toggle[^)]*\)[\s\S]*?bind\([^,]+,\s*["']click["']/s.test(frameInteractionSource),
);
assert.equal(
  rangeToggleHasDirectPointerActivation,
  true,
  "The visible Range toggle must accept a direct pointer click in the Griptape canvas; a 1px pointer-events:none checkbox plus implicit label forwarding is not sufficient.",
);

const imageRowSource = promptSource.slice(
  promptSource.indexOf("function renderImageRow"),
  promptSource.indexOf("function renderVideoRow"),
);
assert.match(imageRowSource, /String\(item\.slot\)\.padStart\(2, "0"\)/);
assert.doesNotMatch(
  imageRowSource,
  /item\.token|<br\/><b>/,
  "Image order displays only 01, 02, 03 without the internal @image token.",
);

const frameRowSource = promptSource.slice(
  promptSource.indexOf("function renderFrameRangeRow"),
  promptSource.indexOf("export function storeCurrentFrameRanges"),
);
assert.match(frameRowSource, /<b>Range<\/b><em>\$\{enabled \? "ON" : "OFF"\}<\/em>/);
assert.doesNotMatch(frameRowSource, /USE FRAME RANGE|프레임 범위 사용/);
assert.doesNotMatch(
  frameRowSource,
  /frame-range-editor|data-frame-range-number|frame-range-delete|frame-binding-context/,
  "The redundant selected-range IN/OUT editor and @video/color context label stay removed.",
);
assert.match(
  frameRowSource,
  /data-frame-domain-number="start" type="text" inputmode="numeric" pattern="\[0-9\]\{1,4\}" maxlength="4"/,
);
assert.match(
  frameRowSource,
  /data-frame-domain-number="end" type="text" inputmode="numeric" pattern="\[0-9\]\{1,4\}" maxlength="4"/,
);
const domainStartMarkup = frameRowSource.indexOf('data-frame-domain-number="start"');
const trackMarkup = frameRowSource.indexOf("data-frame-track");
const domainEndMarkup = frameRowSource.indexOf('data-frame-domain-number="end"');
assert.ok(
  domainStartMarkup >= 0 && domainStartMarkup < trackMarkup && trackMarkup < domainEndMarkup,
  "Four-digit START and END inputs must occupy the left and right ends of the highlighted Range track.",
);
assert.doesNotMatch(
  frameRowSource,
  /domainReadonly|\sreadonly(?:\s|\/?>)/,
  "Manual START and END inputs are never rendered read-only from Picker metadata.",
);
const subtypeSource = promptSource.slice(
  promptSource.indexOf("function renderSubtypeControls"),
  promptSource.indexOf("function frameRangeBarsHtml"),
);
assert.match(subtypeSource, /<div class="binding-scope-entry">[\s\S]*?\$\{customInput\}<\/div>/);
assert.doesNotMatch(subtypeSource, /binding_scopes\.map/);
assert.doesNotMatch(promptSource, /function renderCustomScopeControls/);
const singlePickAssetRow = {
  asset_id: "registered-character",
  binding_scopes: ["Full body / full appearance"],
  color_picks: ["Red"],
};
const twoPickAssetRow = {
  ...singlePickAssetRow,
  color_picks: ["Red", "Yellow"],
};
assert.equal(
  prompt.hmbImageRowHasExpandedLeftFields(singlePickAssetRow),
  false,
  "One Color Pick must not push Range down for a registered asset with no visible expanded field.",
);
assert.equal(
  prompt.hmbImageRowHasExpandedLeftFields(twoPickAssetRow),
  false,
  "Adding a second Color Pick must not change Range geometry.",
);
assert.equal(
  prompt.hmbImageRowHasExpandedLeftFields({
    ...singlePickAssetRow,
    binding_scopes: ["Custom scope"],
  }),
  true,
  "Only the visible Custom Sub Type input should expand the left-side content.",
);
assert.match(
  promptSource,
  /const expandedLeftFields = hmbImageRowHasExpandedLeftFields\(item\);/,
  "Initial render and live refresh must share one Range-layout predicate.",
);
const liveSubtypeRefreshSource = promptSource.slice(
  promptSource.indexOf("function hmbRefreshImageSubtypeControls"),
  promptSource.indexOf("function hmbRefreshImageCustomPanel"),
);
assert.match(liveSubtypeRefreshSource, /hmbImageRowHasExpandedLeftFields\(item\)/);
assert.doesNotMatch(
  liveSubtypeRefreshSource,
  /asset_id/,
  "A hidden Asset ID must never select the 72px expanded Range offset during live Picker refresh.",
);
assert.match(
  promptSource,
  /\.source-row\.image\.image-expanded-left-fields>\.frame-binding-row\{margin-top:72px\}/,
  "Range must move below the visible Custom Sub Type input instead of overlapping it.",
);
assert.doesNotMatch(
  imageRowSource,
  /<small>[\s\S]*?Asset ID:[\s\S]*?<\/small>/,
  "Prompt Image rows must not render the redundant Asset ID helper line.",
);

const previewSource = promptSource.slice(
  promptSource.indexOf("export function updateFrameTrackPreview"),
  promptSource.indexOf("function hmbSyncFrameRangeRowDom"),
);
assert.doesNotMatch(previewSource, /track\.innerHTML/);
assert.match(previewSource, /bar\.style\.left/);
assert.match(previewSource, /existing\.slice\(normalized\.length\)/);
assert.match(promptSource, /hmbConsumePendingFrameRangeEcho/);
assert.match(promptSource, /__hmbPromptPendingLocalValues/);

const canonicalEchoValue = JSON.stringify(prompt.normalizeState(manualState));
const echoContainer = {
  __hmbPromptPendingLocalValues: [{
    value: canonicalEchoValue,
    disabled: false,
  }],
};
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    echoContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  true,
);
assert.equal(echoContainer.__hmbPromptPendingLocalValues, undefined);

const repeatedEchoContainer = {
  __hmbPromptPendingLocalValues: [{
    value: canonicalEchoValue,
    disabled: false,
    expiresAt: Date.now() + 5000,
    remainingEchoes: 3,
  }],
};
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    repeatedEchoContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  true,
);
assert.equal(repeatedEchoContainer.__hmbPromptPendingLocalValues[0].remainingEchoes, 2);
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    repeatedEchoContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  true,
);
assert.equal(repeatedEchoContainer.__hmbPromptPendingLocalValues[0].remainingEchoes, 1);
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    repeatedEchoContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  true,
);
assert.equal(repeatedEchoContainer.__hmbPromptPendingLocalValues, undefined);
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    repeatedEchoContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  false,
  "The identical local echo allowance must stop after its bounded count.",
);

// Native selects close when their DOM is remounted. Every local edit therefore
// carries a serialized monotonic UI revision: after rapid A -> B, a B-first
// host acknowledgement and an arbitrarily late A must both avoid a remount.
function freshLocalState(value) {
  return prompt.normalizeState({
    ...JSON.parse(JSON.stringify(value)),
    ui_edit_revision: 0,
  });
}

function emitLocalStates(states, container = {}) {
  const emitted = [];
  const props = {
    disabled: false,
    onChange(value) { emitted.push(value); },
  };
  for (const item of states) {
    prompt.hmbEmitLocalPromptState(container, props, freshLocalState(item));
  }
  return { container, emitted, props };
}

function assertRapidLocalEchoOrder(olderState, newerState, label) {
  const { container, emitted } = emitLocalStates([olderState, newerState]);
  const [olderValue, newerValue] = emitted;
  const olderSerialized = JSON.parse(olderValue);
  const newerSerialized = JSON.parse(newerValue);
  assert.equal(
    newerSerialized.ui_edit_revision,
    olderSerialized.ui_edit_revision + 1,
    `${label}: each real selection commit must increment ui_edit_revision.`,
  );
  assert.equal(
    prompt.hmbConsumePendingPromptStateEcho(
      container,
      { value: newerValue, disabled: false },
    ),
    true,
    `${label}: newer local echo must be consumed.`,
  );
  assert.ok(container.__hmbPromptPendingLocalValues.length <= 12);
  assert.equal(
    prompt.hmbConsumePendingPromptStateEcho(
      container,
      { value: olderValue, disabled: false },
    ),
    true,
    `${label}: late A must not remount and close the next dropdown.`,
  );
  assert.equal(container.__hmbPromptLastConsumedEchoWasStale, true);
  assert.equal(container.__hmbPromptSupersededLocalValues, undefined);
  clearTimeout(container.__hmbPromptPendingLocalTimer);
  return { olderValue, newerValue, olderSerialized, newerSerialized };
}

const sameFieldMainA = prompt.normalizeState({
  images: [{
    slot: 1,
    label: "Hero",
    present: true,
    source_type: "Character Appearance",
    binding_scopes: [""],
    owner: "",
  }],
});
const sameFieldMainB = prompt.normalizeState({
  images: [{
    slot: 1,
    label: "Hero",
    present: true,
    source_type: "Environment / Background",
    binding_scopes: [""],
    owner: "",
  }],
});
assertRapidLocalEchoOrder(
  sameFieldMainA,
  sameFieldMainB,
  "same Main Type field rapid change",
);

const mainThenSubtype = prompt.normalizeState({
  images: [{
    slot: 1,
    label: "Hero",
    present: true,
    source_type: "Character Appearance",
    binding_scopes: ["Full body / full appearance"],
    owner: "",
  }],
});
const subtypeThenTarget = prompt.normalizeState({
  images: [{
    slot: 1,
    label: "Hero",
    present: true,
    source_type: "Character Appearance",
    binding_scopes: ["Full body / full appearance"],
    owner: "Hero",
  }],
});
assertRapidLocalEchoOrder(
  sameFieldMainA,
  mainThenSubtype,
  "Main Type -> Sub Type rapid change",
);
assertRapidLocalEchoOrder(
  mainThenSubtype,
  subtypeThenTarget,
  "Sub Type -> Target rapid change",
);

const targetThenVideoBinding = prompt.normalizeState({
  images: [{
    slot: 1,
    label: "Hero",
    present: true,
    source_type: "Character Appearance",
    binding_scopes: ["Full body / full appearance"],
    owner: "Hero",
    binding_video_slots: [1],
    color_picks: [""],
  }],
  videos: [{
    slot: 1,
    label: "Shot",
    present: true,
    source_type: "Maya Preview / Playblast",
  }],
});
const videoBindingThenColorPick = prompt.normalizeState({
  ...targetThenVideoBinding,
  images: [{
    ...targetThenVideoBinding.images[0],
    color_picks: ["Red"],
  }],
});
const bindingRapid = assertRapidLocalEchoOrder(
  targetThenVideoBinding,
  videoBindingThenColorPick,
  "Image Video Binding -> Color Pick rapid change",
);
assert.deepEqual(bindingRapid.newerSerialized.images[0].binding_video_slots, [1]);
assert.deepEqual(bindingRapid.newerSerialized.images[0].color_picks, ["Red"]);

const rangeOffRapidState = prompt.normalizeState(JSON.parse(JSON.stringify(unlockedDraftState)));
rangeOffRapidState.images[0].frame_range_enabled = false;
const rangeOnRapidState = prompt.normalizeState(JSON.parse(JSON.stringify(rangeOffRapidState)));
prompt.setFrameRangeEnabled(rangeOnRapidState.images[0], true);
const rangeToggleRapid = assertRapidLocalEchoOrder(
  rangeOffRapidState,
  rangeOnRapidState,
  "Range OFF -> ON retained-mode echo",
);
assert.equal(rangeToggleRapid.olderSerialized.images[0].frame_range_enabled, false);
assert.equal(
  rangeToggleRapid.newerSerialized.images[0].frame_range_enabled,
  true,
  "A late OFF echo must never replace the newer user-authored ON state.",
);

const blankExternalRapidStart = JSON.parse(JSON.stringify(blankColorExternalState));
blankExternalRapidStart.images[0].frame_range_bindings["@video3::"].end_frame = 48;
blankExternalRapidStart.images[0].frame_range_binding.end_frame = 48;
const blankExternalRapidEnd = JSON.parse(JSON.stringify(blankExternalRapidStart));
blankExternalRapidEnd.images[0].frame_range_bindings["@video3::"].end_frame = 96;
blankExternalRapidEnd.images[0].frame_range_binding.end_frame = 96;
const blankExternalRapid = assertRapidLocalEchoOrder(
  blankExternalRapidStart,
  blankExternalRapidEnd,
  "blank Color Pick external END rapid edit",
);
assert.equal(
  blankExternalRapid.newerSerialized.images[0].frame_range_bindings["@video3::"].end_frame,
  96,
);
assert.equal(
  blankExternalRapid.newerSerialized.images[0].frame_range_bindings["@video3::"].color_pick,
  "",
);

const customMainType = prompt.normalizeState({
  images: [{
    slot: 1,
    label: "Custom Hero",
    present: true,
    source_type: "Custom",
    custom_source_type: "",
    binding_scopes: ["Custom scope"],
    binding_custom_scopes: [""],
    owner: "Custom Hero",
  }],
});
const customDetails = prompt.normalizeState({
  ...customMainType,
  images: [{
    ...customMainType.images[0],
    custom_source_type: "Creature Sheet",
    binding_custom_scopes: ["Face / head"],
  }],
});
const customRapid = assertRapidLocalEchoOrder(
  customMainType,
  customDetails,
  "Custom Main Type -> Custom Sub Type/Scope rapid change",
);
assert.equal(customRapid.newerSerialized.images[0].custom_source_type, "Creature Sheet");
assert.deepEqual(customRapid.newerSerialized.images[0].binding_custom_scopes, ["Face / head"]);

const videoMainType = prompt.normalizeState({
  videos: [{
    slot: 1,
    label: "Shot",
    present: true,
    source_type: "Unified Shot-Control Video",
    control_role: "",
  }],
});
const videoControlRole = prompt.normalizeState({
  videos: [{
    slot: 1,
    label: "Shot",
    present: true,
    source_type: "Unified Shot-Control Video",
    control_role: "Primary Unified Shot Control",
  }],
});
const videoRapid = assertRapidLocalEchoOrder(
  videoMainType,
  videoControlRole,
  "Video Main Type -> Control Role rapid change",
);
assert.equal(videoRapid.olderSerialized.videos[0].source_type, "Unified Shot-Control Video");
assert.equal(videoRapid.newerSerialized.videos[0].control_role, "Primary Unified Shot Control");

const boundedRapidContainer = {};
const boundedRapidValues = [];
for (let index = 0; index < 18; index += 1) {
  prompt.hmbEmitLocalPromptState(
    boundedRapidContainer,
    { disabled: false, onChange(value) { boundedRapidValues.push(value); } },
    prompt.normalizeState({ text: { SCENE_CONTEXT: `Bounded rapid state ${index}` } }),
  );
}
assert.ok(boundedRapidContainer.__hmbPromptPendingLocalValues.length <= 12);
const boundedNewest = boundedRapidContainer.__hmbPromptPendingLocalValues.at(-1).value;
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    boundedRapidContainer,
    { value: boundedNewest, disabled: false },
  ),
  true,
);
assert.ok(boundedRapidContainer.__hmbPromptPendingLocalValues.length <= 12);
assert.equal(boundedRapidContainer.__hmbPromptSupersededLocalValues, undefined);
assert.equal(JSON.parse(boundedRapidValues.at(-1)).ui_edit_revision, 18);
clearTimeout(boundedRapidContainer.__hmbPromptPendingLocalTimer);

// A may expire while B remains live. Its lower UI revision is sufficient to
// identify it before or after B's exact acknowledgement.
const expiredPair = emitLocalStates([sameFieldMainA, sameFieldMainB]);
expiredPair.container.__hmbPromptPendingLocalValues[0].expiresAt = Date.now() - 1;
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    expiredPair.container,
    { value: expiredPair.emitted[0], disabled: false },
  ),
  true,
  "Expired A must still be recognized while a newer local B publication is live.",
);
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    expiredPair.container,
    { value: expiredPair.emitted[1], disabled: false },
  ),
  true,
  "B must still be consumable after an expired A arrives first.",
);
clearTimeout(expiredPair.container.__hmbPromptPendingLocalTimer);

const expiredAlone = emitLocalStates([sameFieldMainA]);
expiredAlone.container.__hmbPromptPendingLocalValues[0].expiresAt = Date.now() - 1;
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    expiredAlone.container,
    { value: expiredAlone.emitted[0], disabled: false },
  ),
  false,
  "Expired A without a newer live local publication must remain authoritative.",
);

// Simulate the 750ms queue cleanup without waiting. Revision memory must outlive
// the timer so A at t=900ms is still stale while an unacknowledged B is live.
const nativeSetTimeout = globalThis.setTimeout;
const nativeClearTimeout = globalThis.clearTimeout;
const fakeTimers = new Map();
let fakeTimerId = 0;
globalThis.setTimeout = (callback, delay) => {
  const id = ++fakeTimerId;
  fakeTimers.set(id, { callback, delay });
  return id;
};
globalThis.clearTimeout = (id) => fakeTimers.delete(id);
try {
  const delayedPair = emitLocalStates([sameFieldMainA, sameFieldMainB]);
  const cleanupTimer = [...fakeTimers.values()].find((timer) => timer.delay === 750);
  assert.ok(cleanupTimer, "Local echo cleanup timer must remain bounded to 750ms.");
  cleanupTimer.callback();
  assert.equal(delayedPair.container.__hmbPromptPendingLocalValues, undefined);
  assert.equal(
    prompt.hmbConsumePendingPromptStateEcho(
      delayedPair.container,
      { value: delayedPair.emitted[0], disabled: false },
    ),
    true,
    "A at t=900ms must remain stale after all timer-backed echo history is gone.",
  );
} finally {
  globalThis.setTimeout = nativeSetTimeout;
  globalThis.clearTimeout = nativeClearTimeout;
}

const authoritativePair = emitLocalStates([sameFieldMainA, sameFieldMainB]);
const currentRapidState = JSON.parse(authoritativePair.emitted[1]);
const unrelatedRapidState = prompt.normalizeState({
  ...currentRapidState,
  images: [{ ...currentRapidState.images[0], owner: "External Hero" }],
});
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    authoritativePair.container,
    { value: JSON.stringify(unrelatedRapidState), disabled: false },
  ),
  false,
  "An unrelated state at the current UI revision must remain authoritative.",
);

const newerSourcePair = emitLocalStates([sameFieldMainA, sameFieldMainB]);
const newerSourceRevisionState = prompt.normalizeState({
  ...JSON.parse(newerSourcePair.emitted[0]),
  source_sync_revision: 1,
});
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    newerSourcePair.container,
    { value: JSON.stringify(newerSourceRevisionState), disabled: false },
  ),
  false,
  "A newer Picker/Asset source revision must remain authoritative.",
);

const olderSourceContainer = {};
const sourceTwoState = prompt.normalizeState({
  ...sameFieldMainB,
  source_sync_revision: 2,
});
prompt.hmbEmitLocalPromptState(
  olderSourceContainer,
  { disabled: false, onChange() {} },
  sourceTwoState,
);
const staleSourceState = prompt.normalizeState({
  ...sameFieldMainA,
  source_sync_revision: 1,
  ui_edit_revision: 999,
});
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    olderSourceContainer,
    { value: JSON.stringify(staleSourceState), disabled: true },
  ),
  true,
  "An older source revision must not roll back selects even when disabled changes.",
);
assert.equal(olderSourceContainer.__hmbPromptLastConsumedEchoWasStale, true);
clearTimeout(olderSourceContainer.__hmbPromptPendingLocalTimer);

const higherUiPair = emitLocalStates([sameFieldMainA, sameFieldMainB]);
const higherUiState = prompt.normalizeState({
  ...JSON.parse(higherUiPair.emitted[1]),
  ui_edit_revision: JSON.parse(higherUiPair.emitted[1]).ui_edit_revision + 1,
  images: [{ ...JSON.parse(higherUiPair.emitted[1]).images[0], owner: "New Host State" }],
});
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    higherUiPair.container,
    { value: JSON.stringify(higherUiState), disabled: false },
  ),
  false,
  "A higher UI revision must remain authoritative.",
);

const disabledMismatchContainer = {
  __hmbPromptPendingLocalValues: [{
    value: canonicalEchoValue,
    disabled: true,
    expiresAt: Date.now() + 5000,
    remainingEchoes: 3,
  }],
};
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    disabledMismatchContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  false,
  "An external disabled-state change must not be mistaken for a local selection echo.",
);
assert.equal(
  disabledMismatchContainer.__hmbPromptPendingLocalValues,
  undefined,
  "A disabled-state mismatch must invalidate the local echo window.",
);

const externalState = JSON.parse(JSON.stringify(manualState));
externalState.images[0].label = "Externally renamed";
const externalValue = JSON.stringify(prompt.normalizeState(externalState));
const externalUpdateContainer = {
  __hmbPromptPendingLocalValues: [{
    value: canonicalEchoValue,
    disabled: false,
    expiresAt: Date.now() + 5000,
    remainingEchoes: 3,
  }],
};
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    externalUpdateContainer,
    { value: externalValue, disabled: false },
  ),
  false,
  "A genuinely different external state must reach the normal remount path.",
);
assert.equal(externalUpdateContainer.__hmbPromptPendingLocalValues, undefined);
assert.equal(
  externalUpdateContainer.__hmbPromptSupersededLocalValues,
  undefined,
  "A same-revision ordinary external edit must not create a source-echo quarantine.",
);
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    externalUpdateContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  false,
  "A legitimate same-revision external revert must remain authoritative.",
);

const beforePickerConnect = prompt.normalizeState({
  source_sync_revision: 0,
  images: [{
    label: "Jett",
    source_type: "Character Appearance",
    color_picks: ["Red"],
    binding_video_slots: [1],
  }],
  videos: [{ label: "", source_type: "Role Required / Select Video Type" }],
  picker: { enabled: false },
});
const afterPickerConnect = prompt.normalizeState({
  ...beforePickerConnect,
  source_sync_revision: 1,
  videos: [
    { label: "shot-color", source_type: "Maya Preview / Playblast", present: true },
    { label: "shot-mask", source_type: "Mask / Control Reference", present: true },
    { label: "shot-depth", source_type: "Depth / Spatial Reference", present: true },
  ],
  picker: {
    enabled: true,
    run_id: "picker-first-ready",
    selected_video_count: 3,
    ordered_video_uids: ["color", "mask", "depth"],
    order_managed: true,
  },
});
const beforePickerValue = JSON.stringify(beforePickerConnect);
const afterPickerValue = JSON.stringify(afterPickerConnect);
const firstPickerConnectContainer = {
  __hmbPromptPendingLocalValues: [{
    value: beforePickerValue,
    disabled: false,
    expiresAt: Date.now() + 5000,
    remainingEchoes: 3,
  }],
};
assert.equal(prompt.hmbImagePickerEnabled(beforePickerConnect), false);
assert.equal(prompt.hmbImagePickerEnabled(afterPickerConnect), true);
assert.equal(prompt.hmbPromptVideoRowsLocked(beforePickerConnect), false);
assert.equal(prompt.hmbPromptVideoRowsLocked(afterPickerConnect), true);
assert.equal(prompt.hmbCanAddPromptVideoRow(afterPickerConnect), false);
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    firstPickerConnectContainer,
    { value: afterPickerValue, disabled: false },
  ),
  false,
  "The first populated PICKER_IN payload must reach applyProps and activate Video Source Binding immediately.",
);
assert.equal(firstPickerConnectContainer.__hmbPromptSupersededLocalValues, undefined);
const afterAuthoritativeDisconnect = prompt.normalizeState({
  ...beforePickerConnect,
  source_sync_revision: 2,
});
assert.equal(prompt.hmbPromptVideoRowsLocked(afterAuthoritativeDisconnect), false);
assert.equal(prompt.hmbCanAddPromptVideoRow(afterAuthoritativeDisconnect), true);
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    firstPickerConnectContainer,
    { value: JSON.stringify(afterAuthoritativeDisconnect), disabled: false },
  ),
  false,
  "A newer source revision must allow a real Picker disconnect immediately.",
);
firstPickerConnectContainer.__hmbPromptCurrentSourceSyncRevision = 2;
firstPickerConnectContainer.__hmbPromptCurrentUiEditRevision = 0;
firstPickerConnectContainer.__hmbPromptCurrentDisabled = false;
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    firstPickerConnectContainer,
    { value: beforePickerValue, disabled: false },
  ),
  true,
  "A late pre-connection echo must not deactivate the newly populated video rows.",
);

const expiredEchoContainer = {
  __hmbPromptPendingLocalValues: [{
    value: canonicalEchoValue,
    disabled: false,
    expiresAt: Date.now() - 1,
    remainingEchoes: 3,
  }],
};
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    expiredEchoContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  false,
  "An identical value outside the short echo window is an authoritative host update.",
);
assert.equal(expiredEchoContainer.__hmbPromptPendingLocalValues, undefined);

const sourceSelectHandler = promptSource.slice(
  promptSource.indexOf('container.querySelectorAll(".source-select")'),
  promptSource.indexOf('container.querySelectorAll(".move-image-up, .move-image-down")'),
);
assert.match(sourceSelectHandler, /hmbSyncSourceSelectDom\(container, state, row, kind, index, field\)/);
assert.match(sourceSelectHandler, /hmbEmitLocalPromptState\(container, props, state\)/);
assert.doesNotMatch(sourceSelectHandler, /\bemit\(props, state\)/);
assert.match(promptSource, /HMB_PROMPT_LOCAL_ECHO_TTL_MS = 750/);
assert.match(promptSource, /HMB_PROMPT_LOCAL_ECHO_MAX_CONSUMES = 3/);
assert.match(promptSource, /function hmbRefreshImageColorControls/);
assert.match(promptSource, /function hmbRefreshVideoDependentControls/);
assert.match(promptSource, /function hmbRefreshSourceSummaries/);
assert.match(promptSource, /class="custom-inline-input \$\{scope === "Custom scope" \? "" : "is-hidden"\}"/);
const applyPropsSource = promptSource.slice(
  promptSource.indexOf("const applyProps = (nextProps = {}) =>"),
  promptSource.indexOf("container.__hmbPromptLibraryApplyProps = applyProps"),
);
assert.match(
  applyPropsSource,
  /if \(hmbConsumePendingPromptStateEcho[\s\S]*?__hmbPromptLastConsumedEchoWasStale[\s\S]*?return;/,
  "A lower-revision host echo must return before the authoritative remount path.",
);
assert.equal(
  (applyPropsSource.match(/\bremount\(\);/g) || []).length,
  1,
  "applyProps must retain exactly one remount, exclusively for authoritative state.",
);
assert.match(
  promptSource,
  /const cleanup = \(\) => \{[\s\S]*?delete container\.__hmbPromptCurrentUiEditRevision;[\s\S]*?delete container\.__hmbPromptLatestLocalUiEditRevision;[\s\S]*?delete container\.__hmbPromptCurrentSourceSyncRevision;[\s\S]*?delete container\.__hmbPromptCurrentDisabled;/,
  "Widget cleanup must discard revision baselines before a later workflow remount.",
);
assert.doesNotMatch(promptSource, /<aside class="rail (?:left|right)"/);
assert.doesNotMatch(promptSource, /output-guide/);
assert.doesNotMatch(promptSource, /data-source-token-list/);
assert.doesNotMatch(promptSource, /data-picker-token/);
assert.doesNotMatch(promptSource, /data-image-asset-token/);
assert.doesNotMatch(promptSource, /function (?:sourceTokensHtml|pickerTokenHtml|imageAssetTokenHtml)/);
assert.match(
  promptSource,
  /\.layout\{display:grid;grid-template-columns:minmax\(0,1fr\);gap:0;/,
  "The editor layout must use one full-width center column after both rails are removed.",
);
assert.match(promptSource, /<main class="center">/);
for (const groupId of ["imageSources", "imageText", "videoSources", "videoText"]) {
  assert.match(promptSource, new RegExp(`data-group-id="${groupId}"`));
}

console.log("HMB Prompt frame-track widget interaction regression: PASS");
