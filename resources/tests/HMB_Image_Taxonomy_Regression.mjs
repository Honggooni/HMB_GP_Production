import assert from "node:assert/strict";

import {
  colorPickChoicesForImageTaxonomy,
  imageTargetChoicesForRow,
  normalizeImageTaxonomy,
  normalizeState,
} from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

const fullPalette = [
  "Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink",
  "Sky Blue", "Mint", "Beige", "Direction Checker", "Sky Grid",
  "Floor Grid", "Position Pattern",
];

// Saved Main/Sub/custom/Target meaning is authoritative. Unknown or retired
// names remain authored, while stale derived wire metadata is cleared.
const authored = normalizeState({
  images: [{
    present: true,
    label: "legacy.png",
    image_main_type: "Future Image",
    image_sub_type: "Director-defined scope",
    source_type: "Character Appearance",
    scope: "Full body / full appearance",
    custom_source_type: "Director-defined image note",
    owner: "hero",
    color_picks: ["Red", "Mint"],
    binding_scopes: ["Full body", "Face detail"],
    binding_custom_scopes: ["", "Keep freckles"],
  }],
});
assert.equal(authored.images[0].image_main_type, "Future Image");
assert.equal(authored.images[0].image_sub_type, "Director-defined scope");
assert.equal(authored.images[0].source_type, "Role Required / Select Source Type");
assert.equal(authored.images[0].scope, "");
assert.equal(authored.images[0].custom_source_type, "Director-defined image note");
assert.equal(authored.images[0].owner, "hero");
assert.deepEqual(authored.images[0].color_picks, ["Red", "Mint"]);
assert.deepEqual(authored.images[0].binding_scopes, ["Full body", "Face detail"]);

// An exact current Main/Sub pair still derives its legacy wire metadata.
const exactPair = {
  image_main_type: "Character Prop",
  image_sub_type: "Handheld Prop",
  source_type: "stale",
  scope: "stale",
  color_picks: ["Red", "Mint"],
};
normalizeImageTaxonomy(exactPair);
assert.equal(exactPair.source_type, "Prop / Accessory");
assert.equal(exactPair.scope, "Handheld prop");
assert.deepEqual(exactPair.color_picks, ["Red", "Mint"]);

const retiredPair = {
  image_main_type: "Look Reference",
  image_sub_type: "Scale / Composition",
  source_type: "Director Reference",
  scope: "Approved broad scope",
  owner: "Camera / Composition",
};
normalizeImageTaxonomy(retiredPair);
assert.equal(retiredPair.image_main_type, "Look Reference");
assert.equal(retiredPair.image_sub_type, "Scale / Composition");
assert.equal(retiredPair.source_type, "Role Required / Select Source Type");
assert.equal(retiredPair.scope, "");
assert.equal(retiredPair.owner, "Camera / Composition");

for (const [mainType, subType] of [
  ["Character", "Full Appearance"],
  ["Environment / Background", "Main Background"],
  ["Look Reference", "Render Look"],
  ["Custom / Context", "Custom"],
]) {
  assert.deepEqual(
    colorPickChoicesForImageTaxonomy(mainType, subType),
    fullPalette,
    `${mainType}/${subType} must expose the complete non-coercive palette.`,
  );
}

// Target options are convenience candidates, not a semantic gate.
const rows = [
  { present: true, label: "Hero display", owner: "Hero", image_main_type: "Character" },
  { present: true, label: "Forest display", owner: "Forest", image_main_type: "Environment / Background" },
  { present: true, label: "DawnLook", owner: "DawnLook", image_main_type: "Look Reference" },
  { present: true, label: "Notes", owner: "Notes", image_main_type: "Custom / Context" },
  { present: false, label: "Dormant", owner: "Dormant", image_main_type: "Character" },
];
const look = {
  present: true,
  label: "Look Sheet",
  image_main_type: "Look Reference",
  image_sub_type: "Color Mood",
  owner: "Director Target",
};
const targetChoices = imageTargetChoicesForRow(look, [...rows, look]);
for (const expected of [
  "", "Hero", "Hero display", "Forest", "Forest display", "DawnLook",
  "Notes", "Look Sheet", "Global Look", "Custom", "Camera / Composition",
  "Director Target",
]) {
  assert.ok(targetChoices.includes(expected), `Target choices must include ${expected}.`);
}
assert.ok(targetChoices.includes("Dormant"), "Saved candidate names must not be hidden by semantic filtering.");
assert.equal(look.owner, "Director Target");

// Normalization is stable and never rewrites the user's saved taxonomy.
const roundTrip = normalizeState(JSON.parse(JSON.stringify(authored)));
assert.deepEqual(
  roundTrip.images.map((item) => ({
    main: item.image_main_type,
    sub: item.image_sub_type,
    source: item.source_type,
    scope: item.scope,
    owner: item.owner,
    colors: item.color_picks,
    bindingScopes: item.binding_scopes,
  })),
  authored.images.map((item) => ({
    main: item.image_main_type,
    sub: item.image_sub_type,
    source: item.source_type,
    scope: item.scope,
    owner: item.owner,
    colors: item.color_picks,
    bindingScopes: item.binding_scopes,
  })),
);

console.log("HMB image taxonomy widget regression: PASS");
