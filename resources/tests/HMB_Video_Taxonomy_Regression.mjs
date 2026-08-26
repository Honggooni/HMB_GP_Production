import assert from "node:assert/strict";
import {
  compatibleVideoRoleChoices,
  normalizeState,
  normalizeVideoTaxonomy,
  primaryVideoTypeChoices,
} from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

const legacy = normalizeState({
  videos: [{
    present: true,
    label: "legacy.mp4",
    source_type: "Unified Shot-Control Video",
    control_role: "Primary Unified Shot Control",
  }],
});
assert.equal(legacy.videos[0].video_main_type, "Select Video Main Type");
assert.equal(legacy.videos[0].video_sub_type, "");
assert.equal(legacy.videos[0].source_type, "Role Required / Select Video Type");
assert.equal(legacy.videos[0].control_role, "");
assert.equal(legacy.videos[0].label, "legacy.mp4");

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
    source_type: "Role Required / Select Video Type",
    control_role: "",
  };
  normalizeVideoTaxonomy(item);
  assert.deepEqual([item.source_type, item.control_role], wirePair, key);
  assert.ok(compatibleVideoRoleChoices(item).includes(subType), key);
}

for (const subType of ["Explosion", "Dust", "Particle"]) {
  const migratedFx = normalizeState({
    videos: [{
      present: true,
      video_main_type: "FX / Simulation Reference",
      video_sub_type: subType,
      source_type: "FX Reference",
      control_role: "FX Behavior Only",
    }],
  }).videos[0];
  assert.deepEqual(
    [migratedFx.source_type, migratedFx.control_role],
    ["FX Reference", "FX Effect Only"],
    `legacy FX role migration: ${subType}`,
  );
  assert.deepEqual(
    [migratedFx.video_main_type, migratedFx.video_sub_type],
    ["FX Reference", "FX Effect Only"],
    `legacy FX taxonomy migration: ${subType}`,
  );
}

const placementMigrations = new Map([
  ["Scene / Look Reference\0Depth / Spatial", ["Maya Preview / Playblast", "Depth"]],
  ["Depth\0Depth / Spatial", ["Maya Preview / Playblast", "Depth"]],
  ["Motion Reference\0Retargeting Guide", ["Maya Preview / Playblast", "Motion Guide"]],
  ["Motion Guide\0Retargeting Guide", ["Maya Preview / Playblast", "Motion Guide"]],
  ["FX / Simulation Reference\0Explosion", ["FX Reference", "FX Effect Only"]],
  ["FX / Simulation Reference\0Dust", ["FX Reference", "FX Effect Only"]],
  ["FX / Simulation Reference\0Particle", ["FX Reference", "FX Effect Only"]],
  ["FX / Simulation Reference\0FX Effect Only", ["FX Reference", "FX Effect Only"]],
  ["FX Reference\0Explosion", ["FX Reference", "FX Effect Only"]],
  ["FX Reference\0Dust", ["FX Reference", "FX Effect Only"]],
  ["FX Reference\0Particle", ["FX Reference", "FX Effect Only"]],
]);

for (const [key, canonicalPair] of placementMigrations) {
  const [mainType, subType] = key.split("\0");
  const item = { video_main_type: mainType, video_sub_type: subType };
  assert.deepEqual(normalizeVideoTaxonomy(item), canonicalPair, `migration: ${key}`);
  assert.deepEqual(
    [item.source_type, item.control_role],
    expected.get(canonicalPair.join("\0")),
    `migration wire pair: ${key}`,
  );
}

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
assert.deepEqual(
  compatibleVideoRoleChoices({ video_main_type: "Motion Reference" }),
  ["Local Motion", "Secondary Motion"],
);
assert.deepEqual(compatibleVideoRoleChoices({ video_main_type: "Motion Guide" }), []);
assert.deepEqual(compatibleVideoRoleChoices({ video_main_type: "Depth" }), []);
assert.deepEqual(
  compatibleVideoRoleChoices({ video_main_type: "Scene / Look Reference" }),
  ["Camera / Layout", "Lighting / Look", "Composition"],
);
assert.deepEqual(
  compatibleVideoRoleChoices({ video_main_type: "FX Reference" }),
  ["FX Effect Only"],
);
assert.deepEqual(compatibleVideoRoleChoices({ video_main_type: "FX / Simulation Reference" }), []);

const pickerMetadataFixture = {
  videos: [
    {
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
          video_main_type: {
            assigned: "Depth",
            previous: "Scene / Look Reference",
          },
          video_sub_type: {
            assigned: "Depth / Spatial",
            previous: "Depth / Spatial",
          },
        },
      },
    },
    {
      slot: 2,
      present: true,
      label: "picker-motion-guide",
      video_main_type: "Motion Reference",
      video_sub_type: "Retargeting Guide",
      picker_auto_video_main_type: "Motion Guide",
      picker_auto_video_sub_type: "Retargeting Guide",
      picker_auto_motion_guide: {
        bundle_run_id: "motion-bundle",
        fields: {
          video_main_type: {
            assigned: "Motion Guide",
            previous: "Motion Reference",
          },
          video_sub_type: {
            assigned: "Retargeting Guide",
            previous: "Retargeting Guide",
          },
        },
      },
    },
  ],
};

const migratedPickerMetadata = normalizeState(pickerMetadataFixture);
const depthMetadata = migratedPickerMetadata.videos[0];
assert.deepEqual(
  [depthMetadata.video_main_type, depthMetadata.video_sub_type],
  ["Maya Preview / Playblast", "Depth"],
);
assert.deepEqual(
  [depthMetadata.picker_auto_video_main_type, depthMetadata.picker_auto_video_sub_type],
  ["Maya Preview / Playblast", "Depth"],
);
assert.deepEqual(depthMetadata.picker_auto_depth.fields.video_main_type, {
  assigned: "Maya Preview / Playblast",
  previous: "Maya Preview / Playblast",
});
assert.deepEqual(depthMetadata.picker_auto_depth.fields.video_sub_type, {
  assigned: "Depth",
  previous: "Depth",
});

const motionMetadata = migratedPickerMetadata.videos[1];
assert.deepEqual(
  [motionMetadata.video_main_type, motionMetadata.video_sub_type],
  ["Maya Preview / Playblast", "Motion Guide"],
);
assert.deepEqual(
  [motionMetadata.picker_auto_video_main_type, motionMetadata.picker_auto_video_sub_type],
  ["Maya Preview / Playblast", "Motion Guide"],
);
assert.deepEqual(motionMetadata.picker_auto_motion_guide.fields.video_main_type, {
  assigned: "Maya Preview / Playblast",
  previous: "Maya Preview / Playblast",
});
assert.deepEqual(motionMetadata.picker_auto_motion_guide.fields.video_sub_type, {
  assigned: "Motion Guide",
  previous: "Motion Guide",
});

const reconnectedPickerMetadata = normalizeState(
  JSON.parse(JSON.stringify(migratedPickerMetadata)),
);
assert.deepEqual(
  reconnectedPickerMetadata.videos.slice(0, 2),
  migratedPickerMetadata.videos.slice(0, 2),
  "Picker disconnect/reconnect normalization must preserve canonical taxonomy and provenance fingerprints.",
);

console.log("HMB compact video taxonomy widget regression: PASS");
