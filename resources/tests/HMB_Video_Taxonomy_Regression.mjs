import assert from "node:assert/strict";
import {
  compatibleVideoRoleChoices,
  normalizeState,
  normalizeVideoTaxonomy,
  primaryVideoTypeChoices,
} from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

// Legacy wire metadata is derived state and cannot survive without an exact
// current authoring pair.
const legacy = normalizeState({
  videos: [{
    present: true,
    label: "legacy.mp4",
    source_type: "Unified Shot-Control Video",
    control_role: "Primary Unified Shot Control",
    custom_source_type: "Keep custom source",
    custom_control_role: "Keep custom role",
  }],
});
assert.equal(legacy.videos[0].video_main_type, "Select Video Main Type");
assert.equal(legacy.videos[0].video_sub_type, "");
assert.equal(legacy.videos[0].source_type, "Role Required / Select Video Type");
assert.equal(legacy.videos[0].control_role, "");
assert.equal(legacy.videos[0].custom_source_type, "Keep custom source");
assert.equal(legacy.videos[0].custom_control_role, "Keep custom role");
assert.equal(legacy.videos[0].label, "legacy.mp4");

// Exact current pairs continue deriving their Agent wire metadata.
const expected = new Map([
  ["Maya Preview / Playblast\0Original Preview", ["Unified Shot-Control Video", "Primary Unified Shot Control"]],
  ["Maya Preview / Playblast\0Mask", ["Maya Preview / Playblast", "Mask / Guide Only"]],
  ["Maya Preview / Playblast\0Depth", ["Depth / Spatial Reference", "Spatial Alignment Verification Only"]],
  ["Maya Preview / Playblast\0Motion Guide", ["Motion Guide / Retargeting Reference", "Derived Motion Decoding Only"]],
  ["Maya Preview / Playblast\0Timing / Edit", ["Timing / Edit Reference", "Timing Only"]],
  ["Motion Reference\0Local Motion", ["Motion Reference", "Local Motion Detail Only"]],
  ["Motion Reference\0Secondary Motion", ["Motion Reference", "Secondary Motion Only"]],
  ["Scene / Look Reference\0Camera / Layout", ["Camera / Layout Reference", "Spatial Alignment Verification Only"]],
  ["Scene / Look Reference\0Lighting / Look", ["Lighting / Look Reference", "Lighting / Look Only"]],
  ["Scene / Look Reference\0Composition", ["Camera / Layout Reference", "Local Composition Check Only"]],
  ["FX Reference\0FX Effect Only", ["FX Reference", "FX Effect Only"]],
  ["Custom / Context\0Context", ["Custom", "Context Only"]],
  ["Custom / Context\0Custom", ["Custom", "Custom Role"]],
]);
for (const [key, wirePair] of expected) {
  const [mainType, subType] = key.split("\0");
  const item = {
    video_main_type: mainType,
    video_sub_type: subType,
    source_type: "stale source",
    control_role: "stale role",
  };
  normalizeVideoTaxonomy(item);
  assert.deepEqual([item.source_type, item.control_role], wirePair, key);
  assert.ok(compatibleVideoRoleChoices(item).includes(subType), key);
}

// Unknown/retired/custom vocabulary is user meaning, not migration input;
// only stale derived wire fields are cleared.
for (const [mainType, subType] of [
  ["FX / Simulation Reference", "Explosion"],
  ["Depth", "Depth / Spatial"],
  ["Motion Guide", "Retargeting Guide"],
  ["Future Video", "Director Scope"],
]) {
  const item = {
    video_main_type: mainType,
    video_sub_type: subType,
    source_type: "Authored source",
    control_role: "Authored role",
    custom_source_type: "Keep source note",
    custom_control_role: "Keep role note",
  };
  assert.deepEqual(normalizeVideoTaxonomy(item), [mainType, subType]);
  assert.equal(item.source_type, "Role Required / Select Video Type");
  assert.equal(item.control_role, "");
  assert.equal(item.custom_source_type, "Keep source note");
  assert.equal(item.custom_control_role, "Keep role note");
  assert.ok(primaryVideoTypeChoices(mainType).includes(mainType));
  assert.ok(compatibleVideoRoleChoices(item).includes(subType));
}

const verbatimKeepOut = "  preserve first line  \nrepeat\nrepeat\n";
const noLegacyTextMigration = normalizeState({
  videos: [{ present: true, label: "clip", keep_out: verbatimKeepOut }],
  text: {
    VIDEO_VFX: "current VFX text",
    FX_ADDITIONAL_INSTRUCTION: "retired VFX text",
    FALLBACK_INSTRUCTION: "retired fallback",
    VIDEO_CONTEXT: "retired context",
    VIDEO_MARKER: "retired marker",
    VIDEO_DESCRIPTION: "retired description",
  },
});
assert.equal(noLegacyTextMigration.videos[0].keep_out, verbatimKeepOut);
assert.equal(noLegacyTextMigration.text.VIDEO_VFX, "current VFX text");

assert.deepEqual(
  primaryVideoTypeChoices(),
  [
    "Select Video Main Type",
    "Maya Preview / Playblast",
    "Motion Reference",
    "Scene / Look Reference",
    "FX Reference",
    "Custom / Context",
  ],
);
assert.deepEqual(
  compatibleVideoRoleChoices({ video_main_type: "Maya Preview / Playblast" }),
  ["Original Preview", "Mask", "Depth", "Motion Guide", "Timing / Edit"],
);

// Picker provenance sanitization must not rewrite its captured taxonomy values.
const pickerState = normalizeState({
  videos: [{
    slot: 1,
    present: true,
    label: "picker-depth",
    video_main_type: "Scene / Look Reference",
    video_sub_type: "Depth / Spatial",
    picker_auto_video_main_type: "Depth",
    picker_auto_video_sub_type: "Depth / Spatial",
    picker_auto_depth: {
      pair_run_id: "depth-pair",
      fields: {
        video_main_type: { assigned: "Depth", previous: "Scene / Look Reference" },
        video_sub_type: { assigned: "Depth / Spatial", previous: "Director Depth" },
      },
    },
  }],
});
const pickerVideo = pickerState.videos[0];
assert.equal(pickerVideo.video_main_type, "Scene / Look Reference");
assert.equal(pickerVideo.video_sub_type, "Depth / Spatial");
assert.equal(pickerVideo.picker_auto_video_main_type, "Depth");
assert.equal(pickerVideo.picker_auto_video_sub_type, "Depth / Spatial");
assert.deepEqual(pickerVideo.picker_auto_depth.fields.video_main_type, {
  assigned: "Depth",
  previous: "Scene / Look Reference",
});
assert.deepEqual(pickerVideo.picker_auto_depth.fields.video_sub_type, {
  assigned: "Depth / Spatial",
  previous: "Director Depth",
});
assert.deepEqual(
  normalizeState(JSON.parse(JSON.stringify(pickerState))).videos[0],
  pickerVideo,
  "Repeated normalization must preserve user taxonomy and provenance.",
);

console.log("HMB compact video taxonomy widget regression: PASS");
