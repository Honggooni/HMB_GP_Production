import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(widgetPath);

function fakeContainer() {
  return {
    dataset: {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    contains() { return false; },
  };
}

const container = fakeContainer();
let emitted = "";
let matchingEchoConsumed = false;
let remounts = 0;
let commitOrder = [];
const props = {
  disabled: false,
  onChange(value) {
    commitOrder.push("emit");
    emitted = value;
    // Reproduce Griptape's synchronous value echo. The local echo guard must
    // consume it while the explicit local remount still repaints the row.
    matchingEchoConsumed = widget.hmbConsumePendingPromptStateEcho(container, {
      value,
      disabled: false,
    });
  },
};

const state = widget.normalizeState({
  images: [{ label: "Image A", present: true }],
  videos: [{ label: "Video A", present: true, manual: true }],
});

const independentImageAddState = widget.normalizeState({
  images: [{ label: "Manual image", present: true, manual: true }],
  image_asset: { enabled: false, order_managed: false },
});
assert.equal(
  widget.hmbCanAddPromptImageRow(independentImageAddState),
  true,
  "Prompt-only mode must keep the image + button available.",
);
const connectedImageAddState = widget.normalizeState({
  images: [{ label: "Selected asset", present: true, asset_managed: true }],
  image_asset: { enabled: true, order_managed: true },
});
assert.equal(
  widget.hmbCanAddPromptImageRow(connectedImageAddState),
  false,
  "An Image Asset connection must lock the Prompt image + button.",
);
connectedImageAddState.image_asset.enabled = false;
assert.equal(
  widget.hmbCanAddPromptImageRow(connectedImageAddState),
  true,
  "Disconnecting Image Asset must immediately restore the Prompt image + button.",
);
const fullIndependentImageState = widget.normalizeState({
  images: Array.from({ length: 50 }, (_value, index) => ({
    label: `Manual image ${index + 1}`,
    present: true,
    manual: true,
  })),
  image_asset: { enabled: false, order_managed: false },
});
assert.equal(
  widget.hmbCanAddPromptImageRow(fullIndependentImageState),
  false,
  "The existing maximum-image lock must remain active without an Asset connection.",
);
assert.match(
  source,
  /function renderImageAddRow[\s\S]*?hmbCanAddPromptImageRow\(state, images\)[\s\S]*?data-asset-locked=[\s\S]*?disabled/,
  "The rendered + button must expose and apply the Asset connection lock.",
);
assert.match(
  source,
  /querySelectorAll\("\.add-image-source"\)[\s\S]*?if \(!hmbCanAddPromptImageRow\(state\)\) return;/,
  "The click path must reject stale or forced clicks while Image Asset is connected.",
);

const independentVideoAddState = widget.normalizeState({
  videos: [{ label: "Manual video", present: true, manual: true }],
  picker: { enabled: false, awaiting_data: false },
});
assert.equal(
  widget.hmbCanAddPromptVideoRow(independentVideoAddState),
  true,
  "Prompt-only mode must keep the video + button available.",
);
const connectedVideoAddState = widget.normalizeState({
  videos: [{ label: "Picker video", present: true, manual: false }],
  picker: { enabled: true, awaiting_data: false },
});
assert.equal(
  widget.hmbCanAddPromptVideoRow(connectedVideoAddState),
  false,
  "A Picker connection must lock the Prompt video + button.",
);
assert.equal(
  widget.hmbPromptVideoRowsLocked(connectedVideoAddState),
  true,
  "A Picker connection must lock all Prompt-owned video row structure.",
);
connectedVideoAddState.picker.enabled = false;
assert.equal(
  widget.hmbCanAddPromptVideoRow(connectedVideoAddState),
  true,
  "Disconnecting Picker must immediately restore the Prompt video + button.",
);
assert.equal(
  widget.hmbPromptVideoRowsLocked(connectedVideoAddState),
  false,
  "Disconnecting Picker must immediately restore video row deletion too.",
);
const fullIndependentVideoState = widget.normalizeState({
  videos: Array.from({ length: 10 }, (_value, index) => ({
    label: `Manual video ${index + 1}`,
    present: true,
    manual: true,
  })),
  picker: { enabled: false, awaiting_data: false },
});
assert.equal(
  widget.hmbCanAddPromptVideoRow(fullIndependentVideoState),
  false,
  "The existing maximum-video lock must remain active without a Picker connection.",
);
assert.match(
  source,
  /function renderVideoAddRow[\s\S]*?hmbCanAddPromptVideoRow\(state, videos\)[\s\S]*?disabled/,
  "The rendered video + button must apply the Picker connection lock.",
);
assert.match(
  source,
  /querySelectorAll\("\.add-video-source"\)[\s\S]*?if \(!hmbCanAddPromptVideoRow\(state\)\) return;/,
  "The video click path must reject stale or forced clicks while Picker is connected.",
);
assert.match(
  source,
  /function renderVideoActions\(state\)[\s\S]*?hmbPromptVideoRowsLocked\(state\)[\s\S]*?data-picker-locked=[\s\S]*?disabled/,
  "The rendered video X button must apply the same Picker connection lock.",
);
assert.match(
  source,
  /querySelectorAll\("\.clear-source"\)[\s\S]*?if \(kind === "video" && hmbPromptVideoRowsLocked\(state\)\) return;/,
  "The video delete click path must reject stale or forced clicks while Picker is connected.",
);

const selectState = widget.normalizeState({ ui: { language: "en" } });
const stableRoleSelect = {
  options: [
    { value: "", textContent: "optional" },
    { value: "Timing Only", textContent: "Timing Only" },
  ],
  value: "Timing Only",
  writes: 0,
  set innerHTML(_value) { this.writes += 1; },
};
assert.equal(
  widget.hmbSyncSelectOptions(
    stableRoleSelect,
    ["", "Timing Only"],
    "Timing Only",
    "optional",
    selectState,
  ),
  false,
  "An unchanged Main/Sub Type option list must keep its live DOM nodes.",
);
assert.equal(stableRoleSelect.writes, 0, "An unchanged select must not rewrite innerHTML and flicker.");
assert.equal(stableRoleSelect.value, "Timing Only");

assert.equal(
  widget.hmbSyncSelectOptions(
    stableRoleSelect,
    ["", "FX Behavior Only"],
    "FX Behavior Only",
    "optional",
    selectState,
  ),
  true,
  "A genuinely changed taxonomy must rebuild the option list once.",
);
assert.equal(stableRoleSelect.writes, 1);
assert.equal(stableRoleSelect.value, "FX Behavior Only");

const manualContextImageFields = [
  "color_picks",
  "binding_scopes",
  "binding_custom_scopes",
  "binding_video_slots",
  "marker_video",
  "preview_marker",
  "picker_auto_video",
  "picker_auto_color",
  "picker_auto_source",
];
const contextImage = {
  identity: "x".repeat(300),
  index: 999,
  unknown_record_field: "drop",
  fields: {
    color_picks: ["Red", "Green", "Blue", "drop"],
    binding_scopes: ["Full body / full appearance", "ignored", "ignored"],
    binding_custom_scopes: ["", "ignored", "ignored"],
    binding_video_slots: [2, 3, 4, 10],
    marker_video: 2,
    preview_marker: "marker",
    picker_auto_video: 2,
    picker_auto_color: "Red",
    picker_auto_source: "picker-run",
    frame_range_enabled: true,
    frame_range_color_index: 1,
    frame_range_bindings: {
      "@video2::Red": {
        video_slot: "@video2",
        color_pick: "Red",
        enabled: true,
        origin: "manual",
        ranges: [{ start: -50, end: 12000 }],
        start_frame: -50,
        end_frame: 12000,
        unknown_binding_field: "drop",
      },
      "@video3::Green": {
        video_slot: "@video3",
        color_pick: "Green",
        enabled: true,
        origin: "manual",
        ranges: [{ start: 101, end: 110 }],
        start_frame: 101,
        end_frame: 110,
      },
      "@video4::Blue": {
        video_slot: "@video4",
        color_pick: "Blue",
        enabled: false,
        ranges: [],
      },
      "@video5::drop": {
        video_slot: "@video5",
        color_pick: "drop",
        enabled: true,
        ranges: [],
      },
    },
    frame_range_binding: {
      video_slot: "@video3",
      color_pick: "Green",
      enabled: true,
      origin: "manual",
      ranges: [{ start: 101, end: 110 }],
      start_frame: 101,
      end_frame: 110,
    },
    frame_range_selected_index: 999,
    unknown_image_field: "drop",
  },
};
const manualContextInput = {
  version: 1,
  unknown_context_field: "drop",
  before: {
    text: {
      PROJECT_STYLE_LOOK: "P".repeat(6100),
      SCENE_CONTEXT: "forest",
      EMOTION_INTENT: "focused",
      VIDEO_VFX: "F".repeat(20100),
      PRESERVED_TEXT: "must not be cached",
      UNKNOWN_TEXT: "drop",
    },
    images: [
      contextImage,
      ...Array.from({ length: 54 }, (_value, index) => ({
        identity: `slot:${index + 2}`,
        index: index + 1,
        fields: {},
      })),
    ],
    textarea_heights: {
      "video:1:keep_out": 120,
      "video:11:keep_out": 120,
      unknown: 120,
    },
    unknown_snapshot_field: "drop",
  },
  after: {
    text: { PROJECT_STYLE_LOOK: "after" },
    images: [contextImage],
    textarea_heights: { "video:2:keep_out": 80 },
  },
};
const manualContextState = widget.normalizeState({
  picker: { manual_video_context: manualContextInput },
});
const manualContext = manualContextState.picker.manual_video_context;
assert.deepEqual(Object.keys(manualContext).sort(), ["after", "before", "version"]);
assert.deepEqual(
  Object.keys(manualContext.before).sort(),
  ["images", "text", "textarea_heights"],
  "The cached snapshot must be a closed object.",
);
assert.deepEqual(
  Object.keys(manualContext.before.text).sort(),
  ["EMOTION_INTENT", "PROJECT_STYLE_LOOK", "SCENE_CONTEXT", "VIDEO_VFX"],
  "PRESERVED_TEXT and unknown text fields must not enter the remap cache.",
);
assert.equal(manualContext.before.text.PROJECT_STYLE_LOOK.length, 6000);
assert.equal(manualContext.before.text.VIDEO_VFX.length, 20000);
assert.equal(manualContext.before.images.length, 50, "The remap cache must retain the legacy image-count bound.");
assert.equal(manualContext.before.images[0].identity.length, 256);
assert.equal(manualContext.before.images[0].index, 49);
assert.deepEqual(Object.keys(manualContext.before.images[0].fields), manualContextImageFields);
assert.equal(
  Object.prototype.hasOwnProperty.call(
    manualContext.before.images[0].fields,
    "frame_range_intent",
  ),
  false,
  "Picker reconnect snapshots never own or replay Prompt frame-range intent.",
);
assert.deepEqual(manualContext.before.textarea_heights, { "video:1:keep_out": 120 });
assert.deepEqual(
  widget.normalizeState(JSON.parse(JSON.stringify(manualContextState))).picker.manual_video_context,
  manualContext,
  "A host JSON echo must preserve the complete closed manual-video snapshot losslessly.",
);
assert.deepEqual(
  widget.normalizeState({ picker: { manual_video_context: { ...manualContextInput, version: "1" } } })
    .picker.manual_video_context,
  {},
  "Non-numeric context versions must fail closed.",
);
assert.deepEqual(
  widget.normalizeState({ picker: { manual_video_context: { version: 1, before: [], after: {} } } })
    .picker.manual_video_context,
  {},
  "Malformed snapshot containers must fail closed.",
);

const targetRefreshSource = source.slice(
  source.indexOf("function refreshImageTargetControls"),
  source.indexOf("function imageScopeChoicesForRow"),
);
assert.match(targetRefreshSource, /hmbSyncSelectOptions\(/);
assert.doesNotMatch(targetRefreshSource, /\.innerHTML\s*=/);
const colorRefreshSource = source.slice(
  source.indexOf("function hmbRefreshImageColorControls"),
  source.indexOf("function hmbRefreshSourceSummaries"),
);
assert.equal(
  (colorRefreshSource.match(/hmbSyncSelectOptions\(/g) || []).length,
  2,
  "Video-slot and Color Pick selects must both use option-diff synchronization.",
);
assert.doesNotMatch(colorRefreshSource, /select\.innerHTML\s*=/);

state.images.push({ slot: 2, label: "", present: false, manual: true });
widget.hmbCommitLocalPromptStructure(container, props, state, () => {
  commitOrder.push("remount");
  remounts += 1;
  return state;
});

assert.equal(matchingEchoConsumed, true, "A matching synchronous props echo must be consumed.");
assert.equal(remounts, 1, "A structural edit must repaint locally even when the host echo is consumed.");
assert.deepEqual(commitOrder, ["remount", "emit"], "Structural feedback must paint before the host transaction.");
assert.equal(JSON.parse(emitted).images.length, 2, "The locally repainted image row must also be persisted.");
assert.equal(JSON.parse(emitted).images[1].manual, true);

state.videos.push({ slot: 2, label: "", present: false, manual: true });
matchingEchoConsumed = false;
widget.hmbCommitLocalPromptStructure(container, props, state, () => { remounts += 1; });
assert.equal(matchingEchoConsumed, true);
assert.equal(remounts, 2);
assert.equal(JSON.parse(emitted).videos.length, 2, "A manual video row must repaint and persist independently.");

assert.equal(widget.moveImageRowWithoutReset(state, 1, 0), true);
widget.hmbCommitLocalPromptStructure(container, props, state, () => { remounts += 1; });
assert.equal(JSON.parse(emitted).images[0].manual, true, "Reordering must persist the same local row state.");

assert.equal(widget.removeImageRowAndPromote(state, 0).changed, true);
widget.hmbCommitLocalPromptStructure(container, props, state, () => { remounts += 1; });
assert.equal(JSON.parse(emitted).images.length, 1, "Deletion must repaint and persist without an external Picker event.");

assert.match(
  source,
  /export function hmbCommitLocalPromptStructure[\s\S]*?hmbCaptureUiBeforeStateEmit\(container, state\);[\s\S]*?rollbackValue[\s\S]*?remount\(\)[\s\S]*?hmbEmitLocalPromptState\(container, props, committedState,[\s\S]*?remount\(rollbackState\)/,
  "Structural commits must capture geometry, repaint locally, then persist through the host.",
);
assert.match(
  source,
  /const remount = \(nextState = null\) => \{[\s\S]*?hmbCapturePromptControlFocus\(container\);[\s\S]*?hmbRestoreSourceScroll\(container\);[\s\S]*?hmbRestorePromptControlFocus\(container\);/,
  "Immediate structural remounts must preserve source scrolling and keyboard focus.",
);
assert.match(
  source,
  /HMB_PROMPT_STRUCTURAL_FOCUS_CLASSES[\s\S]*?kind: "structure"[\s\S]*?memory\.kind === "structure"[\s\S]*?container\.querySelector\(`\.\$\{memory\.action\}`\)/,
  "Structural action buttons must recover focus by stable action identity after a local remount.",
);

for (const selector of [
  ".add-image-source",
  ".add-video-source",
  ".clear-source",
  ".add-color-pick",
  ".remove-color-pick",
  ".move-image-up, .move-image-down",
]) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  assert.match(
    source,
    new RegExp(`querySelectorAll\\(\\"${escaped}\\"\\)[\\s\\S]{0,5000}?hmbCommitLocalPromptStructure\\(container, props, state, remount\\)`),
    `${selector} must use the standalone-safe structural commit path.`,
  );
}

const noLossRoundTrip = widget.normalizeState({
  source_intent_fallbacks: [{
    source: "PICKER_IN",
    reason: "future schema",
    text: "Use the impossible reflection rhythm",
  }],
  images: [{
    present: true,
    label: "Custom marker image",
    source_type: "Custom",
    custom_source_type: "User idea",
    color_picks: ["Infrared dream marker"],
    frame_range_enabled: true,
    frame_range_bindings: {
      "@video5::Infrared dream marker": {
        video_slot: "@video5",
        color_pick: "Infrared dream marker",
        origin: "manual",
        start_frame: 101,
        end_frame: 140,
        ranges: [{ start: 110, end: 120 }],
      },
    },
  }],
});
assert.equal(noLossRoundTrip.images[0].color_picks[0], "Infrared dream marker");
assert.ok(noLossRoundTrip.images[0].frame_range_bindings["@video5::Infrared dream marker"]);
assert.equal(noLossRoundTrip.source_intent_fallbacks[0].text, "Use the impossible reflection rhythm");

const parseDiagnosticKeys = [
  "kind",
  "source",
  "reason",
  "error_code",
  "byte_length",
  "sha256",
  "error_offset",
];
const slash = String.fromCharCode(92);
function malformedHmb(sourceName, generation, padding = 32) {
  const picker = sourceName === "PICKER_IN";
  const schema = picker
    ? "hmb-prompt-library-picker-binding"
    : "hmb-image-asset-library-binding";
  const mode = picker ? "maya" : "image_asset";
  const pathKey = picker ? "video_path" : "project_root";
  return `{"generation":"${generation}","schema":"${schema}","mode":"${mode}","${pathKey}":"C:${slash}Users${slash}team${slash}source","padding":"${"x".repeat(padding)}"}`;
}
function expectedParseDiagnostic(sourceName, text, errorOffset) {
  return {
    kind: "parse_diagnostic",
    source: sourceName,
    reason: "invalid JSON connected input",
    error_code: "invalid_json",
    byte_length: Buffer.byteLength(text, "utf8"),
    sha256: createHash("sha256").update(text, "utf8").digest("hex"),
    error_offset: errorOffset,
  };
}

// Legacy wingtest-style malformed HMB bodies are machine transport failures,
// not user prose. Frontend normalization must produce exactly the same compact
// diagnostic schema as Python without retaining any raw path/body.
const legacyPickerOne = malformedHmb("PICKER_IN", "one", 10_000);
const legacyPickerLatest = malformedHmb("PICKER_IN", "two", 9_000);
const legacyImage = malformedHmb("IMAGE_ASSET_IN", "one", 8_000);
const exactHumanWhitespace = `  사용자가 직접 작성한 의도\n${"장면 설명 🧭 ".repeat(20_000)}END  `;
const compactMixed = widget.normalizeState({
  source_intent_fallbacks: [
    { source: "CONNECTED_SOURCE", reason: "future schema", text: exactHumanWhitespace },
    { source: "PICKER_IN", reason: "readable non-JSON connected input", text: legacyPickerOne },
    { source: "IMAGE_ASSET_IN", reason: "readable non-JSON connected input", text: legacyImage },
    { source: "PICKER_IN", reason: "readable non-JSON connected input", text: legacyPickerLatest },
  ],
});
assert.equal(compactMixed.source_intent_fallbacks.length, 3);
assert.deepEqual(compactMixed.source_intent_fallbacks[0], {
  source: "CONNECTED_SOURCE",
  reason: "future schema",
  text: exactHumanWhitespace,
});
assert.equal(
  compactMixed.source_intent_fallbacks[0].text,
  exactHumanWhitespace,
  "Ordinary user text has no character/byte budget and must retain boundary whitespace.",
);
assert.ok(Buffer.byteLength(exactHumanWhitespace, "utf8") > 200_000);
assert.deepEqual(
  compactMixed.source_intent_fallbacks[1],
  expectedParseDiagnostic("PICKER_IN", legacyPickerLatest, 95),
  "The first same-source diagnostic position must contain the latest failure.",
);
assert.deepEqual(
  compactMixed.source_intent_fallbacks[2],
  expectedParseDiagnostic("IMAGE_ASSET_IN", legacyImage, 102),
);
for (const diagnostic of compactMixed.source_intent_fallbacks.slice(1)) {
  assert.deepEqual(Object.keys(diagnostic), parseDiagnosticKeys);
  assert.equal(Object.hasOwn(diagnostic, "text"), false);
}
const compactMixedJson = JSON.stringify(compactMixed);
assert.equal(compactMixedJson.includes(legacyPickerOne), false);
assert.equal(compactMixedJson.includes(legacyPickerLatest), false);
assert.equal(compactMixedJson.includes(legacyImage), false);
assert.equal(compactMixedJson.includes(`C:${slash}Users`), false);
assert.deepEqual(
  widget.normalizeState(JSON.parse(compactMixedJson)).source_intent_fallbacks,
  compactMixed.source_intent_fallbacks,
  "Compact mixed fallback normalization must be idempotent.",
);

// Transitional tagged records carrying raw text are compacted even when their
// older fields are incomplete. Already compact backend records are canonicalized.
const taggedRaw = malformedHmb("PICKER_IN", "tagged", 4_000);
const taggedAndCanonical = widget.normalizeState({
  source_intent_fallbacks: [
    { kind: "parse_diagnostic", source: "PICKER_IN", reason: "old", text: taggedRaw },
    {
      kind: "parse_diagnostic",
      source: "IMAGE_ASSET_IN",
      reason: "ignored old label",
      error_code: "invalid_json",
      byte_length: "12",
      sha256: "A".repeat(64),
      error_offset: -20,
    },
  ],
});
assert.deepEqual(
  taggedAndCanonical.source_intent_fallbacks[0],
  expectedParseDiagnostic("PICKER_IN", taggedRaw, 98),
);
assert.deepEqual(taggedAndCanonical.source_intent_fallbacks[1], {
  kind: "parse_diagnostic",
  source: "IMAGE_ASSET_IN",
  reason: "invalid JSON connected input",
  error_code: "invalid_json",
  byte_length: 12,
  sha256: "a".repeat(64),
  error_offset: -1,
});
assert.equal(JSON.stringify(taggedAndCanonical).includes(taggedRaw), false);

const taggedHuman = "  user-authored text carrying a future diagnostic tag  ";
const taggedHumanState = widget.normalizeState({
  source_intent_fallbacks: [{
    kind: "parse_diagnostic",
    source: "PICKER_IN",
    reason: "future user extension",
    text: taggedHuman,
  }],
});
assert.deepEqual(taggedHumanState.source_intent_fallbacks, [{
  source: "PICKER_IN",
  reason: "future user extension",
  text: taggedHuman,
}]);

// A legacy reason alone is not machine provenance. Both exact source-specific
// schema and mode signatures must occur inside the bounded prefix.
const signatureAttacks = [
  `  {"mode":"maya","note":"C:${slash}x"}  `,
  `{"schema":"hmb-prompt-library-picker-binding","note":"C:${slash}x"}`,
  `{"schema":"hmb-image-asset-library-binding","mode":"image_asset","note":"C:${slash}x"}`,
  `{"note":"${"z".repeat(4_200)}","schema":"hmb-prompt-library-picker-binding","mode":"maya","path":"C:${slash}x"}`,
  `{"note":"{${slash}"schema${slash}":${slash}"hmb-prompt-library-picker-binding${slash}",${slash}"mode${slash}":${slash}"maya${slash}"}","path":"C:${slash}x"}`,
];
const preservedAttacks = widget.normalizeState({
  source_intent_fallbacks: signatureAttacks.map((text) => ({
    source: "PICKER_IN",
    reason: "readable non-JSON connected input",
    text,
  })),
}).source_intent_fallbacks;
assert.deepEqual(
  preservedAttacks.map((entry) => entry.text),
  signatureAttacks,
  "Schema-only, mode-only, wrong-source, and beyond-prefix prose must remain exact.",
);
assert.ok(preservedAttacks.every((entry) => entry.kind !== "parse_diagnostic"));

// Fallback compaction participates in rapid local echo serialization without
// changing the monotonic revision/stale-echo behavior that keeps selects open.
const fallbackRapidContainer = {};
const fallbackRapidValues = [];
const fallbackRapidProps = {
  disabled: false,
  onChange(value) { fallbackRapidValues.push(value); },
};
for (const sourceType of ["Character Appearance", "Environment / Background"]) {
  widget.hmbEmitLocalPromptState(
    fallbackRapidContainer,
    fallbackRapidProps,
    widget.normalizeState({
      source_intent_fallbacks: compactMixed.source_intent_fallbacks,
      images: [{ present: true, label: "Hero", source_type: sourceType }],
    }),
  );
}
const [fallbackOlder, fallbackNewer] = fallbackRapidValues;
const fallbackOlderState = JSON.parse(fallbackOlder);
const fallbackNewerState = JSON.parse(fallbackNewer);
assert.equal(fallbackNewerState.ui_edit_revision, fallbackOlderState.ui_edit_revision + 1);
assert.deepEqual(
  fallbackNewerState.source_intent_fallbacks,
  fallbackOlderState.source_intent_fallbacks,
);
assert.equal(JSON.stringify(fallbackNewerState).includes(legacyPickerLatest), false);
assert.equal(widget.hmbConsumePendingPromptStateEcho(
  fallbackRapidContainer,
  { value: fallbackNewer, disabled: false },
), true);
assert.equal(widget.hmbConsumePendingPromptStateEcho(
  fallbackRapidContainer,
  { value: fallbackOlder, disabled: false },
), true);
assert.equal(fallbackRapidContainer.__hmbPromptLastConsumedEchoWasStale, true);
clearTimeout(fallbackRapidContainer.__hmbPromptPendingLocalTimer);

const pickerUidEcho = widget.normalizeState(JSON.parse(JSON.stringify(widget.normalizeState({
  videos: [
    {
      video_uid: "video-depth-uid",
      source_uid: "video-depth-uid",
      selection_order: 1,
      order_key: "video-depth-uid",
      picker_managed: true,
      label: "Standalone Depth",
      present: true,
      source_type: "Depth / Spatial Reference",
      picker_companion_kind: "depth",
      picker_companion_source_slot: 0,
      picker_companion_source_uid: "",
      picker_companion_validated: true,
    },
    {
      video_uid: "video-motion-uid",
      selection_order: 2,
      label: "Motion Guide",
      present: true,
      source_type: "Motion Guide / Retargeting Reference",
      picker_companion_kind: "motion_guide",
      source_video_slot: "@video1",
      source_video_uid: "video-depth-uid",
      picker_companion_validated: true,
      picker_motion_guide_summary: {
        profile: "hmb_target_neutral_motion_guide_v5",
        semantic_face: true,
        target_count: 4,
        channel_count: 8,
        semantic_groups: ["mouth", "eyelid"],
        final_blendshape_values_in_sidecar: true,
      },
    },
  ],
  picker: {
    enabled: true,
    run_id: "picker-uid-run",
    selection_id: "picker-selection-uid",
    selected_video_count: 2,
    ordered_video_uids: ["video-depth-uid", "video-motion-uid"],
    order_managed: true,
    dormant_video_rows: [{
      video_uid: "video-dormant-uid",
      selection_order: 7,
      label: "Dormant Depth",
      source_type: "Depth / Spatial Reference",
      picker_companion_kind: "depth",
      source_video_slot: 1,
      source_video_uid: "video-depth-uid",
      picker_companion_validated: true,
    }],
    dormant_manual_rows: [{
      label: "Dormant manual reference",
      source_type: "Custom",
      custom_source_type: "User reference",
    }],
    frame_metadata: [{
      video_slot: 2,
      video_uid: "video-motion-uid",
      selection_order: 2,
      order_key: "video-motion-uid",
      fps: 24,
      start_frame: 1,
      end_frame: 24,
      frame_count: 24,
      valid: true,
    }],
  },
}))));
assert.equal(pickerUidEcho.picker.selection_id, "picker-selection-uid");
assert.deepEqual(
  pickerUidEcho.picker.ordered_video_uids,
  ["video-depth-uid", "video-motion-uid"],
  "Picker selection order must survive a frontend value echo.",
);
assert.equal(pickerUidEcho.picker.selected_video_count, 2);
assert.equal(pickerUidEcho.picker.order_managed, true);
assert.equal(pickerUidEcho.videos[1].video_uid, "video-motion-uid");
assert.equal(pickerUidEcho.videos[1].source_uid, "video-motion-uid");
assert.equal(pickerUidEcho.videos[1].picker_companion_kind, "motion_guide");
assert.equal(pickerUidEcho.videos[1].picker_companion_source_slot, 1);
assert.equal(pickerUidEcho.videos[1].picker_companion_source_uid, "video-depth-uid");
assert.equal(pickerUidEcho.videos[1].picker_companion_validated, true);
assert.deepEqual(
  pickerUidEcho.videos[1].picker_motion_guide_summary.semantic_groups,
  ["eyelid", "mouth"],
);
assert.equal(pickerUidEcho.picker.dormant_video_rows[0].slot, 0);
assert.equal(
  pickerUidEcho.picker.dormant_video_rows[0].video_uid,
  "video-dormant-uid",
  "Deselected Picker rows must retain their stable UID outside active slots.",
);
assert.equal(
  pickerUidEcho.picker.dormant_video_rows[0].picker_companion_source_uid,
  "video-depth-uid",
);
assert.equal(pickerUidEcho.picker.dormant_video_rows[0].picker_companion_source_slot, 1);
assert.equal(pickerUidEcho.picker.dormant_manual_rows[0].slot, 0);
assert.equal(pickerUidEcho.picker.dormant_manual_rows[0].label, "Dormant manual reference");
assert.equal(pickerUidEcho.picker.frame_metadata[0].video_uid, "video-motion-uid");
assert.equal(pickerUidEcho.picker.frame_metadata[0].source_uid, "video-motion-uid");

const slotLocalPickerState = widget.normalizeState({
  videos: [
    { slot: 1, label: "color", present: true, source_type: "Maya Preview / Playblast", manual: true },
    { slot: 2, label: "depth", present: true, source_type: "Depth / Spatial Reference", picker_auto_depth: { pair_run_id: "bundle-a", fields: { label: { assigned: "depth", previous: "" } } }, manual: true },
    { slot: 3, label: "motion", present: true, source_type: "Motion Guide / Retargeting Reference", picker_auto_motion_guide: { bundle_run_id: "bundle-a", fields: { label: { assigned: "motion", previous: "" } } }, manual: true },
  ],
  picker: {
    enabled: true,
    awaiting_data: false,
    run_id: "picker-run-a",
    slot_suppressions: {},
    markers: [{ color: "Red", video_slot: 1 }],
    frame_metadata: [{ video_slot: 1, fps: 24, start_frame: 1, end_frame: 24, frame_count: 24, valid: true }],
  },
});
assert.equal(widget.hmbSuppressPickerVideoSlot(slotLocalPickerState, 2), true);
assert.deepEqual(slotLocalPickerState.picker.slot_suppressions, { "2": "picker-run-a" });
assert.equal(slotLocalPickerState.picker.markers.length, 1, "A slot-local X/Ignore must retain Picker markers.");
assert.equal(slotLocalPickerState.picker.frame_metadata.length, 1, "A slot-local X/Ignore must retain frame metadata.");
assert.ok(slotLocalPickerState.videos[2].picker_auto_motion_guide.fields.label, "Other companion provenance must remain intact.");

matchingEchoConsumed = false;
widget.hmbCommitLocalPromptStructure(container, props, slotLocalPickerState, () => { remounts += 1; });
const slotLocalEmission = JSON.parse(emitted);
assert.deepEqual(slotLocalEmission.picker.slot_suppressions, { "2": "picker-run-a" });
assert.equal(slotLocalEmission.picker.markers.length, 1, "The local slot edit must reach PROMPT_OUT state immediately without clearing Picker data.");
assert.equal(Object.hasOwn(slotLocalEmission.picker, "suppressed"), false);
assert.equal(Object.hasOwn(slotLocalEmission.picker, "suppressed_run_id"), false);

assert.equal(widget.hmbReleasePickerVideoSlotSuppression(slotLocalPickerState, 2), true);
assert.deepEqual(slotLocalPickerState.picker.slot_suppressions, {});
assert.doesNotMatch(source, /suppressCurrentPickerPayload/);
assert.match(source, /select\.value === "Ignore \/ Unused"[\s\S]{0,180}?hmbSuppressPickerVideoSlot/);
assert.match(source, /const removedSlot = Number\([\s\S]{0,180}?hmbSuppressPickerVideoSlot\(state, removedSlot\)/);

console.log("HMB Prompt local structure regression checks passed.");
