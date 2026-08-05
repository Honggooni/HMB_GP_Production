import assert from "node:assert/strict";
import fs from "node:fs";


async function importSource(path) {
  const source = fs.readFileSync(path, "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}


const promptPath = new URL(
  "../../widgets/HMBPromptLibraryScopedBindingWidget.js",
  import.meta.url,
);
const promptSource = fs.readFileSync(promptPath, "utf8");
const prompt = await importSource(promptPath);


const state = {
  images: [
    {
      slot: 1,
      token: "@image1",
      name: "IMAGE_01",
      present: true,
      label: "Hero",
      source_type: "Character Appearance",
      owner: "Hero",
      scope: "Full body / full appearance",
      binding_scopes: [
        "Full body / full appearance",
        "Head / face only",
      ],
      binding_custom_scopes: ["", ""],
      binding_video_slots: [1, 3],
      marker_video: 1,
      color_picks: ["Red", "Green"],
      frame_range_enabled: false,
      frame_range_color_index: 0,
      frame_range_bindings: {},
      frame_range_binding: null,
      frame_range_selected_index: -1,
      manual: true,
    },
  ],
  videos: [
    {
      slot: 1,
      token: "@video1",
      present: true,
      label: "primary",
      source_type: "Maya Preview / Playblast",
      control_role: "Primary Unified Shot Control",
      manual: true,
    },
    {
      slot: 2,
      token: "@video2",
      present: false,
      label: "",
      source_type: "Role Required / Select Video Type",
      control_role: "",
      manual: true,
    },
    {
      slot: 3,
      token: "@video3",
      present: true,
      label: "head-guide",
      source_type: "Motion Reference",
      control_role: "Context Only",
      manual: true,
    },
  ],
  text: {},
  picker: {
    enabled: false,
    awaiting_data: false,
    suppressed: false,
    frame_metadata: [],
  },
  ui: {},
};


const normalized = prompt.normalizeState(state);
assert.deepEqual(normalized.images[0].binding_video_slots, [1, 3]);
assert.deepEqual(
  normalized.images[0].binding_scopes,
  ["Full body / full appearance", "Full body / full appearance"],
  "Sub Type is image-level authority, so legacy per-binding overrides must collapse to the first value.",
);
assert.equal(
  normalized.images[0].marker_video,
  1,
  "marker_video remains only the first-binding compatibility alias.",
);
assert.deepEqual(
  prompt.normalizeState(normalized).images[0].binding_video_slots,
  [1, 3],
  "Repeated widget normalization must not flatten independent video slots.",
);
assert.deepEqual(
  prompt.normalizeState(normalized).images[0].binding_scopes,
  ["Full body / full appearance", "Full body / full appearance"],
  "Repeated widget normalization must keep the shared image subtype stable.",
);

const customScopeState = prompt.normalizeState({
  ...state,
  images: [{
    ...state.images[0],
    scope: "Custom scope",
    binding_scopes: ["Custom scope", "Head / face only"],
    binding_custom_scopes: ["Hero silhouette", "Face detail"],
  }],
});
assert.deepEqual(customScopeState.images[0].binding_scopes, ["Custom scope", "Custom scope"]);
assert.deepEqual(
  customScopeState.images[0].binding_custom_scopes,
  ["Hero silhouette", "Hero silhouette"],
  "Custom Sub Type text must also be shared by every Color Pick/video binding.",
);

const legacyOwnerState = prompt.normalizeState({
  ...state,
  images: [{
    ...state.images[0],
    owner: "",
    binding_scopes: ["Full body / full appearance", "Handheld prop"],
    interaction_targets: ["Dog"],
  }],
});
assert.deepEqual(
  legacyOwnerState.images[0].binding_scopes,
  ["Full body / full appearance", "Full body / full appearance"],
);
assert.equal(
  legacyOwnerState.images[0].owner,
  "",
  "A discarded secondary Sub Type must not influence migrated image-level Target authority.",
);

const depthProvenanceState = prompt.normalizeState({
  ...state,
  videos: [
    state.videos[0],
    {
      ...state.videos[1],
      label: "generated-depth",
      present: true,
      source_type: "Depth / Spatial Reference",
      control_role: "Spatial Alignment Verification Only",
      picker_auto_label: "generated-depth",
      picker_auto_depth: {
        pair_run_id: "  pair-run-a  ",
        ignored_top_level: "must-not-round-trip",
        fields: {
          label: {
            assigned: "generated-depth",
            previous: "manual-depth",
            ignored: "must-not-round-trip",
          },
          present: { assigned: "true", previous: "false" },
          source_type: {
            assigned: "Depth / Spatial Reference",
            previous: "Custom",
          },
          custom_source_type: {
            assigned: "",
            previous: "Manual source type",
          },
          control_role: {
            assigned: "Spatial Alignment Verification Only",
            previous: "Custom Role",
          },
          custom_control_role: {
            assigned: "",
            previous: "Manual control role",
          },
          picker_auto_label: {
            assigned: "generated-depth",
            previous: "",
          },
          forbidden_field: {
            assigned: "unsafe",
            previous: "unsafe",
          },
        },
      },
      manual: true,
    },
  ],
});
const normalizedDepthProvenance =
  depthProvenanceState.videos[1].picker_auto_depth;
assert.equal(normalizedDepthProvenance.pair_run_id, "pair-run-a");
assert.deepEqual(Object.keys(normalizedDepthProvenance.fields), [
  "label",
  "present",
  "source_type",
  "custom_source_type",
  "control_role",
  "custom_control_role",
  "picker_auto_label",
]);
assert.deepEqual(normalizedDepthProvenance.fields.present, {
  assigned: true,
  previous: false,
});
assert.deepEqual(normalizedDepthProvenance.fields.label, {
  assigned: "generated-depth",
  previous: "manual-depth",
});
assert.equal(
  Object.hasOwn(normalizedDepthProvenance, "ignored_top_level"),
  false,
);
assert.equal(
  Object.hasOwn(normalizedDepthProvenance.fields, "forbidden_field"),
  false,
);
assert.deepEqual(
  prompt.normalizeState(depthProvenanceState).videos[1].picker_auto_depth,
  normalizedDepthProvenance,
  "Prompt Widget normalization must preserve sanitized Depth provenance across repeated UI round-trips.",
);


const frameImage = JSON.parse(JSON.stringify(normalized.images[0]));
frameImage.frame_range_enabled = true;
frameImage.frame_range_color_index = 1;
frameImage.frame_range_bindings = {
  "@video3::Green": {
    video_slot: "@video3",
    color_pick: "Green",
    origin: "manual",
    ranges: [{ start: 5, end: 12 }],
  },
};
frameImage.frame_range_binding = null;
const frameState = {
  ...normalized,
  images: [frameImage],
  picker: {
    enabled: true,
    awaiting_data: false,
    suppressed: false,
    frame_metadata: [
      {
        video_slot: "@video3",
        fps: 24,
        start_frame: 1,
        end_frame: 24,
        frame_count: 24,
        duration_seconds: 1,
        timebase: "24/1",
        available_color_picks: ["Green"],
        origin: "maya",
        conflict: false,
        valid: true,
        warnings: [],
      },
    ],
  },
};
const frameStatus = prompt.frameRangeUiStatus(frameState, frameImage);
assert.equal(frameStatus.colorIndex, 1);
assert.equal(frameStatus.slot, 3);
assert.equal(frameStatus.key, "@video3::Green");
assert.equal(frameStatus.binding.video_slot, "@video3");
assert.deepEqual(frameStatus.ranges, [{ start: 5, end: 12 }]);
assert.equal(frameStatus.canEnable, true);


// Every mapped Color Pick row must render its own indexed video selector. A
// single row-global marker_video selector would recreate the missing-number bug.
const renderStart = promptSource.indexOf("function renderColorPickControls");
const renderEnd = promptSource.indexOf("function videoNumberOptions", renderStart);
assert.ok(renderStart >= 0 && renderEnd > renderStart);
const renderSource = promptSource.slice(renderStart, renderEnd);
assert.match(
  renderSource,
  /item\.color_picks\.map\(\(pick, pickIndex\) => `<div class="color-binding-entry"><select[\s\S]*?data-field="binding_video_slots"[\s\S]*?data-binding-index="\$\{pickIndex\}"[\s\S]*?<select[\s\S]*?data-field="color_picks"[\s\S]*?data-color-index="\$\{pickIndex\}"/,
  "Every color-binding-entry must pair an indexed video number with its indexed Color Pick.",
);
assert.doesNotMatch(
  renderSource,
  /data-field="marker_video"/,
  "The renderer must not fall back to one row-global video selector.",
);

const subtypeRenderStart = promptSource.indexOf("function renderSubtypeControls");
const subtypeRenderEnd = promptSource.indexOf("function frameRangeBarsHtml", subtypeRenderStart);
assert.ok(subtypeRenderStart >= 0 && subtypeRenderEnd > subtypeRenderStart);
const subtypeRenderSource = promptSource.slice(subtypeRenderStart, subtypeRenderEnd);
assert.match(
  subtypeRenderSource,
  /data-field="binding_scopes" data-binding-index="0"/,
  "Each image row must render exactly one image-level Sub Type selector.",
);
assert.doesNotMatch(
  subtypeRenderSource,
  /binding_scopes\.map/,
  "Sub Type controls must not repeat for every Color Pick/video binding.",
);

const removeStart = promptSource.indexOf('container.querySelectorAll(".remove-color-pick")');
const addStart = promptSource.indexOf('container.querySelectorAll(".add-color-pick")');
const addEnd = promptSource.indexOf('container.querySelectorAll(".add-image-source")', addStart);
assert.ok(removeStart >= 0 && addStart > removeStart && addEnd > addStart);
const removeSource = promptSource.slice(removeStart, addStart);
const addSource = promptSource.slice(addStart, addEnd);
assert.match(
  removeSource,
  /videoSlots\.pop\(\)/,
  "Removing a Color Pick must remove its parallel video number.",
);
assert.match(
  addSource,
  /videoSlots\.push\(videoSlots\[videoSlots\.length - 1\] \|\| 1\)/,
  "Adding a Color Pick must inherit the previous binding's video number.",
);
assert.match(
  addSource,
  /scopes\.push\(scopes\[0\] \|\| ""\)/,
  "Adding a Color Pick must inherit the image-level Sub Type.",
);


console.log("HMB independent binding_video_slots widget regression: PASS");
