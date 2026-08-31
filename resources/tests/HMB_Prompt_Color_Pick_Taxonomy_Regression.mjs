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
  },
});

assert.deepEqual(
  prompt.colorPickChoicesForImageTaxonomy("Character", "Full Appearance"),
  all,
  "Character Main/Sub must not filter the user-selectable palette.",
);
assert.deepEqual(
  prompt.colorPickChoicesForImageTaxonomy("Environment / Background", "Main Background"),
  all,
  "Environment Main/Sub must not filter the user-selectable palette.",
);
assert.deepEqual(
  prompt.colorPickChoicesForImageTaxonomy("Custom / Context", "Custom"),
  all,
  "Custom Main/Sub must expose the union palette.",
);
assert.deepEqual(state.image_taxonomy.actor_color_pick_choices, actor);
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
