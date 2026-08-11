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

prompt.storeCurrentFrameRanges(image, [
  { start: 97, end: 144 },
  { start: 1, end: 48 },
], 0);
assert.deepEqual(image.frame_range_bindings["@video3::Green"].ranges, [
  { start: 1, end: 48 },
  { start: 97, end: 144 },
]);

const normalizedEnabledBindings = prompt.normalizeFrameRangeBindings({
  "@video1::Red": {
    video_slot: "@video1",
    color_pick: "Red",
    enabled: true,
    origin: "picker",
    ranges: [{ start: 1, end: 12 }],
  },
  "@video2::Blue": {
    video_slot: "@video2",
    color_pick: "Blue",
    enabled: true,
    origin: "picker",
    ranges: [{ start: 20, end: 32 }],
  },
  "@video3::Green": {
    video_slot: "@video3",
    color_pick: "Green",
    enabled: false,
    origin: "picker",
    ranges: [{ start: 40, end: 44 }],
  },
});
assert.equal(normalizedEnabledBindings["@video1::Red"].enabled, true);
assert.equal(normalizedEnabledBindings["@video2::Blue"].enabled, true);
assert.equal(normalizedEnabledBindings["@video3::Green"].enabled, false);

const multiActiveImage = {
  ...image,
  color_picks: ["Red", "Blue"],
  binding_video_slots: [1, 2],
  marker_video: 1,
  frame_range_color_index: 0,
  frame_range_bindings: normalizedEnabledBindings,
  frame_range_binding: null,
};
prompt.storeCurrentFrameRanges(multiActiveImage, [{ start: 3, end: 8 }], 0);
assert.equal(multiActiveImage.frame_range_bindings["@video1::Red"].enabled, true);
assert.equal(
  multiActiveImage.frame_range_bindings["@video2::Blue"].enabled,
  true,
  "Saving one Range address must retain a second active @video/ColorPick binding.",
);
assert.equal(prompt.setFrameRangeEnabled(multiActiveImage, false), false);
assert.equal(multiActiveImage.frame_range_bindings["@video1::Red"].enabled, true);
assert.equal(multiActiveImage.frame_range_bindings["@video2::Blue"].enabled, true);
multiActiveImage.frame_range_color_index = 1;
assert.equal(prompt.setFrameRangeEnabled(multiActiveImage, true), true);
assert.equal(multiActiveImage.frame_range_bindings["@video1::Red"].enabled, true);
assert.equal(multiActiveImage.frame_range_bindings["@video2::Blue"].enabled, true);

const normalizedMultiActiveState = prompt.normalizeState({
  ...state,
  images: [JSON.parse(JSON.stringify(multiActiveImage))],
});
assert.equal(normalizedMultiActiveState.images[0].frame_range_bindings["@video1::Red"].enabled, true);
assert.equal(normalizedMultiActiveState.images[0].frame_range_bindings["@video2::Blue"].enabled, true);

assert.equal(
  prompt.applyVideoRoleDefaultForSourceType({ source_type: "FX Reference", control_role: "" }),
  "FX Behavior Only",
);
assert.equal(
  prompt.applyVideoRoleDefaultForSourceType({ source_type: "Timing / Edit Reference", control_role: "" }),
  "Timing Only",
);
const preservedTimingRole = { source_type: "FX Reference", control_role: "Timing Only" };
assert.equal(
  prompt.applyVideoRoleDefaultForSourceType(preservedTimingRole),
  "FX Behavior Only",
  "FX Main Type always owns readable FX behavior regardless of a stale narrower role.",
);
const preservedContextRole = { source_type: "Timing / Edit Reference", control_role: "Context Only" };
assert.equal(
  prompt.applyVideoRoleDefaultForSourceType(preservedContextRole),
  "Timing Only",
  "Timing/Edit Main Type always canonicalizes to its cue-only role.",
);
const incompatibleMotionRole = { source_type: "FX Reference", control_role: "Local Motion Detail Only" };
assert.equal(
  prompt.applyVideoRoleDefaultForSourceType(incompatibleMotionRole),
  "FX Behavior Only",
  "Changing Main Type replaces an incompatible prior role with the target type default.",
);
const incompatibleFxRole = { source_type: "Timing / Edit Reference", control_role: "FX Behavior Only" };
assert.equal(prompt.applyVideoRoleDefaultForSourceType(incompatibleFxRole), "Timing Only");
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
      ranges: [{ start: 10, end: 20 }],
    },
  },
};
const pickerPriorityStatus = prompt.frameRangeUiStatus(
  { ...state, images: [pickerPriorityImage] },
  pickerPriorityImage,
);
assert.equal(pickerPriorityStatus.domainReadonly, true);
assert.equal(pickerPriorityStatus.metadata.origin, "");
assert.deepEqual(
  [pickerPriorityStatus.domainStart, pickerPriorityStatus.domainEnd],
  [1, 144],
  "Picker metadata is the authoritative locked frame domain when available.",
);

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
  "Range ON resumes the preserved manual domain.",
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
assert.match(frameRowSource, /const domainReadonly = frameStatus\.domainReadonly \? "readonly" : "";/);
const subtypeSource = promptSource.slice(
  promptSource.indexOf("function renderSubtypeControls"),
  promptSource.indexOf("function frameRangeBarsHtml"),
);
assert.match(subtypeSource, /<div class="binding-scope-entry">[\s\S]*?\$\{customInput\}<\/div>/);
assert.doesNotMatch(subtypeSource, /binding_scopes\.map/);
assert.doesNotMatch(promptSource, /function renderCustomScopeControls/);
assert.match(
  promptSource,
  /clean\(item\.binding_scopes\[0\]\) === "Custom scope" \|\| Boolean\(clean\(item\.asset_id\)\)/,
  "Custom Sub Type input and Asset ID rows must be marked as expanded left-side content.",
);
assert.match(
  promptSource,
  /\.source-row\.image\.image-expanded-left-fields>\.frame-binding-row\{margin-top:72px\}/,
  "Range must move below the Custom Sub Type input or Asset ID instead of overlapping it.",
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
  prompt.hmbConsumePendingPromptStateEcho(
    externalUpdateContainer,
    { value: canonicalEchoValue, disabled: false },
  ),
  false,
  "A stale local value must not be swallowed after a newer external update.",
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

console.log("HMB Prompt frame-track widget interaction regression: PASS");
