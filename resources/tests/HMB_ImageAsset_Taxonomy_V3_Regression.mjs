import assert from "node:assert/strict";
import fs from "node:fs";

import {
  hmbImageAssetRegistrationSubTypes,
  hmbNormalizeImageAssetState,
} from "../../widgets/HMBImageAssetLibraryWidget.js";


const widgetPath = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");

assert.match(
  source,
  /const IMAGE_TAXONOMY_VERSION = 3;/,
  "ImageAsset must accept the same v3 taxonomy contract published by Prompt/common.",
);

const taxonomy = {
  schema: "hmb-image-taxonomy",
  version: 3,
  main_type_count: 6,
  sub_type_count: 27,
  pair_count: 27,
  image_main_type_choices: [
    "Select Image Main Type",
    "Character",
    "Character Prop",
    "Environment / Background",
    "Background Prop",
    "Look Reference",
    "Custom / Context",
  ],
  image_sub_type_choices: {
    Character: ["Full Appearance"],
    "Character Prop": ["Handheld Prop"],
    "Environment / Background": ["Main Background"],
    "Background Prop": ["Independent Scene Prop"],
    "Look Reference": [
      "Color Mood",
      "Lighting / Atmosphere",
      "Render Style",
      "Color / Look / Lighting",
      "Camera / Composition",
      "ch_Scale",
      "bg_Scale",
      "ch_Scale / bg_Scale",
    ],
    "Custom / Context": ["Context"],
  },
  semantic_pairs: [{
    main_type: "Look Reference",
    sub_type: "Camera / Composition",
    source_type: "Camera / Composition Reference",
    scope: "Camera framing / composition only",
  }],
  labels: {
    en: { "Camera / Composition": "Camera / Composition" },
    ko: { "Camera / Composition": "카메라 / 구도" },
  },
};

const normalized = hmbNormalizeImageAssetState({ taxonomy });
assert.equal(normalized.taxonomy.version, 3);
assert.deepEqual(
  hmbImageAssetRegistrationSubTypes(
    normalized.taxonomy,
    "Look Reference",
  ),
  taxonomy.image_sub_type_choices["Look Reference"],
  "The ImageAsset registration dialog must expose Camera / Composition as a Look Reference Sub Type.",
);
assert.ok(
  hmbImageAssetRegistrationSubTypes(
    normalized.taxonomy,
    "Look Reference",
  ).includes("Render Style"),
  "The ImageAsset registration dialog must expose the canonical Render Style Sub Type.",
);
assert.ok(
  !hmbImageAssetRegistrationSubTypes(
    normalized.taxonomy,
    "Look Reference",
  ).includes("Render Look"),
  "The retired Render Look label must not remain in ImageAsset registration.",
);
assert.deepEqual(
  normalized.taxonomy.semantic_pairs.find((pair) => (
    pair.main_type === "Look Reference"
    && pair.sub_type === "Camera / Composition"
  )),
  {
    main_type: "Look Reference",
    sub_type: "Camera / Composition",
    source_type: "Camera / Composition Reference",
    scope: "Camera framing / composition only",
  },
  "Registration guidance must retain the exact Agent-wire meaning from the shared taxonomy.",
);

console.log(
  "HMB ImageAsset taxonomy v3 regression: PASS "
  + "(Camera / Composition is a Look Reference Sub Type in registration)",
);
