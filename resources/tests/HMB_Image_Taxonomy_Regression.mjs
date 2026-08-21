import assert from "node:assert/strict";
import {
  colorPickChoicesForImageTaxonomy,
  normalizeImageTaxonomy,
  normalizeState,
} from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

const mainTypes = [
  "Select Image Main Type",
  "Character",
  "Character Prop",
  "Environment / Background",
  "Background Prop",
  "Look Reference",
  "Custom / Context",
];
const subTypes = {
  "Character": ["Full Appearance", "Head / Face", "Eyes / Expression", "Body Part", "Hair / Fur", "Costume Detail", "Full Costume"],
  "Character Prop": ["Handheld Prop", "Attached Accessory", "Character Interactive Prop"],
  "Environment / Background": ["Main Background", "Sky / Exterior", "Ground / Floor", "Foreground"],
  "Background Prop": ["Independent Scene Prop", "Interactive Scene Prop", "Set / Structure"],
  "Look Reference": ["Color Mood", "Lighting / Atmosphere", "Render Look", "Color / Look / Lighting", "Scale", "Composition", "Scale / Composition"],
  "Custom / Context": ["Context", "Custom"],
};

const legacy = normalizeState({
  image_taxonomy: {
    image_main_type_choices: mainTypes,
    image_sub_type_choices: subTypes,
    actor_color_pick_choices: ["Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink"],
    object_color_pick_choices: ["Sky Blue", "Mint", "Beige", "Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"],
  },
  images: [{
    present: true,
    label: "legacy.png",
    asset_id: "legacy",
    source_type: "Character Appearance",
    scope: "Full body / full appearance",
    owner: "hero",
    color_picks: ["Red"],
  }],
});
assert.equal(legacy.images[0].image_main_type, "Select Image Main Type");
assert.equal(legacy.images[0].image_sub_type, "");
assert.equal(legacy.images[0].source_type, "Role Required / Select Source Type");
assert.equal(legacy.images[0].scope, "");
assert.equal(legacy.images[0].owner, "");
assert.deepEqual(legacy.images[0].color_picks, [""]);
assert.equal(legacy.images[0].label, "legacy.png");

const characterProp = {
  image_main_type: "Character Prop",
  image_sub_type: "Handheld Prop",
  color_picks: ["Red", "Mint"],
};
normalizeImageTaxonomy(characterProp);
assert.equal(characterProp.source_type, "Prop / Accessory");
assert.equal(characterProp.scope, "Handheld prop");
assert.deepEqual(characterProp.color_picks, ["Red"]);

const backgroundProp = {
  image_main_type: "Background Prop",
  image_sub_type: "Set / Structure",
  color_picks: ["Mint", "Green"],
};
normalizeImageTaxonomy(backgroundProp);
assert.equal(backgroundProp.source_type, "Set / Structure");
assert.equal(backgroundProp.scope, "Set geometry / structure only");
assert.deepEqual(backgroundProp.color_picks, ["Mint"]);

const look = {
  image_main_type: "Look Reference",
  image_sub_type: "Render Look",
  owner: "Former Character Target",
  interaction_targets: ["Hero"],
  color_picks: ["Red", "Mint"],
};
normalizeImageTaxonomy(look);
assert.equal(look.source_type, "Color / Look Reference");
assert.equal(look.scope, "Render look only");
assert.deepEqual(look.color_picks, [""]);
assert.equal(look.owner, "Global Look");
assert.deepEqual(look.interaction_targets, [""]);
assert.deepEqual(colorPickChoicesForImageTaxonomy("Look Reference", "Render Look"), []);
assert.ok(!mainTypes.includes("Scene / Look Reference"));
assert.ok(!mainTypes.includes("Character Appearance"));

console.log("HMB image taxonomy widget regression: PASS");
