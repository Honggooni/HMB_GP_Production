import assert from "node:assert/strict";
import {
  compatibleVideoRoleChoices,
  normalizeState,
  normalizeVideoTaxonomy,
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
  ["Motion Reference\0Retargeting Guide", ["Motion Guide / Retargeting Reference", "Derived Motion Decoding Only"]],
  ["Scene / Look Reference\0Camera / Layout", ["Camera / Layout Reference", "Spatial Alignment Verification Only"]],
  ["Scene / Look Reference\0Depth / Spatial", ["Depth / Spatial Reference", "Spatial Alignment Verification Only"]],
  ["Scene / Look Reference\0Lighting / Look", ["Lighting / Look Reference", "Lighting / Look Only"]],
  ["Scene / Look Reference\0Composition", ["Camera / Layout Reference", "Local Composition Check Only"]],
  ["FX / Simulation Reference\0Explosion", ["FX Reference", "FX Behavior Only"]],
  ["FX / Simulation Reference\0Dust", ["FX Reference", "FX Behavior Only"]],
  ["FX / Simulation Reference\0Particle", ["FX Reference", "FX Behavior Only"]],
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

console.log("HMB compact video taxonomy widget regression: PASS");
