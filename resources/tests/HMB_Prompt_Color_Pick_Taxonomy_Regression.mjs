import assert from "node:assert/strict";

import * as prompt from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

const actor = ["Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink"];
const ghost = ["Sky Blue", "Mint", "Beige"];
const patterns = ["Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"];
const object = [...ghost, ...patterns];
const all = [...actor, ...object];

const state = prompt.normalizeState({
  image_taxonomy: {
    actor_color_pick_choices: [...actor, ...ghost],
    object_color_pick_choices: object,
    actor_color_pick_source_types: [
      "Character Appearance",
      "Partial Character Detail",
      "Costume / Clothing",
    ],
    object_color_pick_source_types: [
      "Prop / Accessory",
      "Environment / Background",
    ],
  },
});

assert.deepEqual(
  prompt.colorPickChoicesForSourceType("Character Appearance"),
  [...actor, ...ghost],
  "Actor sources must expose the seven Actor colors plus the three Ghost colors.",
);
assert.deepEqual(
  prompt.colorPickChoicesForSourceType("Environment / Background"),
  object,
  "Background/Object sources must expose the three Ghost colors plus four patterns.",
);
assert.deepEqual(
  prompt.colorPickChoicesForSourceType("Custom"),
  all,
  "Custom must preserve the existing unique fourteen-choice order.",
);
assert.deepEqual(state.image_taxonomy.actor_color_pick_choices, [...actor, ...ghost]);
assert.deepEqual(state.image_taxonomy.object_color_pick_choices, object);
assert.equal(state.schema, "prompt-library-state", "The persisted state schema must remain unchanged.");

// The + action appends an empty structural slot before the user chooses a
// marker. Taxonomy normalization must not collapse that slot back to one.
const pendingThree = {
  image_main_type: "Character",
  image_sub_type: "Full Appearance",
  color_picks: ["", "", ""],
};
prompt.normalizeImageTaxonomy(pendingThree);
assert.deepEqual(
  pendingThree.color_picks,
  ["", "", ""],
  "Three pending Video / Color slots must survive normalization.",
);

const filledThree = {
  image_main_type: "Character",
  image_sub_type: "Full Appearance",
  color_picks: ["Red", "Green", "Blue", "Yellow"],
};
prompt.normalizeImageTaxonomy(filledThree);
assert.deepEqual(
  filledThree.color_picks,
  ["Red", "Green", "Blue"],
  "Video / Color bindings must preserve exactly the supported maximum of three.",
);

console.log("HMB Prompt Color Pick taxonomy regression: PASS");
