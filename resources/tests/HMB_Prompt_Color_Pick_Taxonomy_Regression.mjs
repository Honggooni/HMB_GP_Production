import assert from "node:assert/strict";
import fs from "node:fs";

import * as prompt from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

const actor = ["Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink", "Cyan"];
const ghost = ["Sky Blue", "Mint", "Beige", "Lavender"];
const patterns = ["Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"];
const object = [...ghost, ...patterns];
const all = [...actor, ...object];
const catalog = JSON.parse(fs.readFileSync(
  new URL("../picker/HMB_Marker_Catalog.json", import.meta.url), "utf8",
));
assert.deepEqual(catalog.character.map((item) => item.name), actor);
assert.deepEqual(catalog.background.map((item) => item.name), object);
assert.deepEqual(
  prompt.colorPickChoicesForImageTaxonomy("Character", "Full Appearance"),
  all,
  "A fresh widget must expose the complete catalog before host state hydration.",
);

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

const legacyTaxonomy = structuredClone(state.image_taxonomy);
legacyTaxonomy.actor_color_pick_choices = actor.filter((color) => color !== "Cyan");
legacyTaxonomy.object_color_pick_choices = object.filter((color) => color !== "Lavender");
const restoredLegacyPalette = prompt.normalizeState({ image_taxonomy: legacyTaxonomy });
assert.deepEqual(restoredLegacyPalette.image_taxonomy.actor_color_pick_choices, actor);
assert.deepEqual(restoredLegacyPalette.image_taxonomy.object_color_pick_choices, object);
assert.deepEqual(prompt.colorPickChoicesForImageTaxonomy("Character", "Full Appearance"), all);

const customTaxonomy = structuredClone(legacyTaxonomy);
customTaxonomy.actor_color_pick_choices.push("Custom Actor");
customTaxonomy.object_color_pick_choices.push("Custom Ghost");
const restoredCustomPalette = prompt.normalizeState({ image_taxonomy: customTaxonomy });
assert.deepEqual(restoredCustomPalette.image_taxonomy.actor_color_pick_choices, [...actor, "Custom Actor"]);
assert.deepEqual(restoredCustomPalette.image_taxonomy.object_color_pick_choices, [...object, "Custom Ghost"]);
// Restore the host palette so this test's custom names do not affect the
// standard fresh/default-state checks below.
prompt.normalizeState({ image_taxonomy: state.image_taxonomy });

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

// Display translations must not change the canonical marker values sent to
// the Prompt/Agent contract, or saved video/color and range addresses.
for (const language of ["ko", "en"]) {
  const restored = prompt.normalizeState({
    images: [{
      present: true,
      label: "Extended palette target",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
      color_picks: ["Red", "Cyan", "Lavender"],
      binding_video_slots: [1, 3, 2],
      frame_range_bindings: {
        "@video3::Cyan": {
          video_slot: 3, color_pick: "Cyan", enabled: true,
          start_frame: 101, end_frame: 124,
          ranges: [{ start: 104, end: 118 }], selected_index: 0,
        },
      },
    }],
    ui: { language },
  });
  assert.deepEqual(restored.images[0].color_picks, ["Red", "Cyan", "Lavender"]);
  assert.deepEqual(restored.images[0].binding_video_slots, [1, 3, 2]);
  assert.equal(restored.images[0].frame_range_bindings["@video3::Cyan"].color_pick, "Cyan");
  const select = { options: [], innerHTML: "", value: "" };
  prompt.hmbSyncSelectOptions(select, ["", "Cyan", "Lavender"], "Cyan", "—", restored);
  assert.equal(select.value, "Cyan");
  assert.match(select.innerHTML, language === "ko"
    ? /value="Cyan" selected>시안<\/option>/
    : /value="Cyan" selected>Cyan<\/option>/);
  assert.match(select.innerHTML, language === "ko"
    ? /value="Lavender" >라벤더<\/option>/
    : /value="Lavender" >Lavender<\/option>/);
}

console.log("HMB Prompt Color Pick taxonomy regression: PASS");
