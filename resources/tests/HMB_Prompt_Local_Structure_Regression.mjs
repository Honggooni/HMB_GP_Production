import assert from "node:assert/strict";
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
const props = {
  disabled: false,
  onChange(value) {
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

state.images.push({ slot: 2, label: "", present: false, manual: true });
widget.hmbCommitLocalPromptStructure(container, props, state, () => { remounts += 1; });

assert.equal(matchingEchoConsumed, true, "A matching synchronous props echo must be consumed.");
assert.equal(remounts, 1, "A structural edit must repaint locally even when the host echo is consumed.");
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
  /export function hmbCommitLocalPromptStructure[\s\S]*?hmbCaptureUiBeforeStateEmit\(container, state\);[\s\S]*?hmbEmitLocalPromptState\(container, props, state\);[\s\S]*?remount\(\)/,
  "Structural commits must capture UI geometry, queue the local echo, persist, and remount in that order.",
);
assert.match(
  source,
  /const remount = \(\) => \{[\s\S]*?hmbCapturePromptControlFocus\(container\);[\s\S]*?hmbRestoreSourceScroll\(container\);[\s\S]*?hmbRestorePromptControlFocus\(container\);/,
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
