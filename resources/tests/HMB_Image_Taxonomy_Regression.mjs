import assert from "node:assert/strict";

import {
  colorPickChoicesForImageTaxonomy,
  imageTargetChoicesForRow,
  hmbReconcileImageTargetContract,
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
  owner: "Director Camera",
};
normalizeImageTaxonomy(retiredPair);
assert.equal(retiredPair.image_main_type, "Look Reference");
assert.equal(retiredPair.image_sub_type, "Scale / Composition");
assert.equal(retiredPair.source_type, "Role Required / Select Source Type");
assert.equal(retiredPair.scope, "");
assert.equal(retiredPair.owner, "Director Camera");

for (const forbiddenTarget of ["Global Look", "Custom", "Camera / Composition"]) {
  const nonLookRow = {
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
    owner: forbiddenTarget,
    look_custom_instruction: "Hidden look instruction must not survive.",
  };
  normalizeImageTaxonomy(nonLookRow);
  assert.equal(nonLookRow.owner, "", `${forbiddenTarget} must clear outside Look Reference.`);
  assert.equal(
    nonLookRow.look_custom_instruction,
    "",
    "Non-Look rows must not retain a hidden Look custom instruction.",
  );
}

for (const allowedTarget of ["Global Look", "Custom", "Hero_A"]) {
  const lookRow = {
    image_main_type: "Look Reference",
    image_sub_type: "Render Style",
    owner: allowedTarget,
    look_custom_instruction: "Approved Look instruction.",
  };
  normalizeImageTaxonomy(lookRow);
  assert.equal(lookRow.owner, allowedTarget);
  assert.equal(lookRow.look_custom_instruction, "Approved Look instruction.");
}

const transitionedLookRow = {
  image_main_type: "Look Reference",
  image_sub_type: "Render Style",
  owner: "Global Look",
  look_custom_instruction: "Scene-wide finish.",
};
normalizeImageTaxonomy(transitionedLookRow);
transitionedLookRow.image_main_type = "Environment / Background";
transitionedLookRow.image_sub_type = "Main Background";
normalizeImageTaxonomy(transitionedLookRow);
assert.equal(transitionedLookRow.owner, "");
assert.equal(transitionedLookRow.look_custom_instruction, "");

const retiredCameraTarget = {
  image_main_type: "Look Reference",
  image_sub_type: "Camera / Composition",
  owner: "Camera / Composition",
};
normalizeImageTaxonomy(retiredCameraTarget);
assert.equal(
  retiredCameraTarget.owner,
  "",
  "Camera / Composition is a Sub Type and must never survive as a Target.",
);

const lookOnlyNamedTargetRows = hmbReconcileImageTargetContract([
  {
    present: true,
    label: "DawnLook",
    image_main_type: "Look Reference",
    image_sub_type: "Render Style",
    owner: "Global Look",
  },
  {
    present: true,
    label: "Hero",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
    owner: "DawnLook",
  },
]);
assert.equal(
  lookOnlyNamedTargetRows[1].owner,
  "",
  "A non-Look row must clear a Target name supplied exclusively by a Look row.",
);

const sharedNamedTargetRows = hmbReconcileImageTargetContract([
  {
    present: true,
    label: "DawnLook",
    image_main_type: "Look Reference",
    image_sub_type: "Render Style",
    owner: "Global Look",
  },
  {
    present: true,
    label: "DawnLook",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
    owner: "DawnLook",
  },
  {
    present: true,
    label: "Forest",
    image_main_type: "Environment / Background",
    image_sub_type: "Main Background",
    owner: "DawnLook",
  },
]);
assert.equal(sharedNamedTargetRows[1].owner, "DawnLook");
assert.equal(sharedNamedTargetRows[2].owner, "DawnLook");

const arbitraryNamedTargetRows = hmbReconcileImageTargetContract([{
  present: true,
  label: "Hero",
  image_main_type: "Character",
  image_sub_type: "Full Appearance",
  owner: "Director Target",
}]);
assert.equal(arbitraryNamedTargetRows[0].owner, "Director Target");

for (const [mainType, subType] of [
  ["Character", "Full Appearance"],
  ["Environment / Background", "Main Background"],
  ["Look Reference", "Render Style"],
  ["Look Reference", "Camera / Composition"],
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
  "", "Hero", "Hero display", "Forest", "Forest display",
  "Notes", "Global Look", "Custom",
  "Director Target",
]) {
  assert.ok(targetChoices.includes(expected), `Target choices must include ${expected}.`);
}
for (const excluded of ["DawnLook", "Look Sheet", "Camera / Composition"]) {
  assert.ok(!targetChoices.includes(excluded), `${excluded} must not leak into Look Target choices.`);
}
assert.ok(targetChoices.includes("Dormant"), "Saved candidate names must not be hidden by semantic filtering.");
assert.equal(look.owner, "Director Target");

for (const mainType of [
  "Character", "Character Prop", "Environment / Background",
  "Background Prop", "Custom / Context",
]) {
  const row = { present: true, label: `${mainType} row`, image_main_type: mainType, owner: "Named Target" };
  const choices = imageTargetChoicesForRow(row, [
    row,
    { present: true, label: "Look label", owner: "Global Look", image_main_type: "Look Reference" },
    { present: true, label: "Custom look", owner: "Custom", image_main_type: "Look Reference" },
    { present: true, label: "Legacy camera", owner: "Camera / Composition", image_main_type: "Look Reference" },
  ]);
  for (const excluded of [
    "Global Look", "Custom", "Camera / Composition",
    "Look label", "Custom look", "Legacy camera",
  ]) {
    assert.ok(!choices.includes(excluded), `${mainType} must not expose ${excluded}.`);
  }
  assert.ok(choices.includes("Named Target"));
  assert.ok(choices.includes(`${mainType} row`));
}

const cameraComposition = {
  image_main_type: "Look Reference",
  image_sub_type: "Camera / Composition",
};
normalizeImageTaxonomy(cameraComposition);
assert.equal(cameraComposition.source_type, "Camera / Composition Reference");
assert.equal(cameraComposition.scope, "Camera framing / composition only");

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
