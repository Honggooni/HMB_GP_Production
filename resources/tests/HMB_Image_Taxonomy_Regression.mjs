import assert from "node:assert/strict";
import {
  colorPickChoicesForImageTaxonomy,
  imageTargetChoicesForRow,
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
  "Look Reference": ["Color Mood", "Lighting / Atmosphere", "Render Look", "Color / Look / Lighting", "ch_Scale", "bg_Scale", "ch_Scale / bg_Scale"],
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

const rejectedLegacyTaxonomyPayload = normalizeState({
  image_taxonomy: {
    image_main_type_choices: mainTypes,
    image_sub_type_choices: {
      ...subTypes,
      "Look Reference": [
        "Color Mood", "Lighting / Atmosphere", "Render Look",
        "Color / Look / Lighting", "Scale", "Composition", "Scale / Composition",
      ],
    },
  },
  images: [{
    present: true,
    label: "legacy-combined-scale.png",
    image_main_type: "Look Reference",
    image_sub_type: "Scale / Composition",
    owner: "Camera / Composition",
  }],
});
assert.equal(rejectedLegacyTaxonomyPayload.images[0].image_main_type, "Select Image Main Type");
assert.equal(rejectedLegacyTaxonomyPayload.images[0].image_sub_type, "");
assert.equal(rejectedLegacyTaxonomyPayload.images[0].owner, "");

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
  owner: "Jett_11",
  color_picks: ["Red", "Mint"],
};
normalizeImageTaxonomy(look);
assert.equal(look.source_type, "Color / Look Reference");
assert.equal(look.scope, "Render look only");
assert.deepEqual(look.color_picks, [""]);
assert.equal(look.owner, "Jett_11");
assert.deepEqual(colorPickChoicesForImageTaxonomy("Look Reference", "Render Look"), []);

// Target is independent from the transferable Look attributes. Repeated
// Render -> Lighting -> ch_Scale changes rebuild only the wire pair.
for (const [subType, expectedWire] of [
  ["Render Look", ["Color / Look Reference", "Render look only"]],
  ["Lighting / Atmosphere", ["Lighting / Atmosphere Reference", "Lighting mood only"]],
  ["ch_Scale", ["Relative Size Reference", "Character Relative Size Only"]],
]) {
  look.image_sub_type = subType;
  normalizeImageTaxonomy(look);
  assert.equal(
    look.owner,
    subType === "Lighting / Atmosphere"
      ? "Global Look"
      : (subType === "ch_Scale" ? "ch_all" : "Jett_11"),
  );
  assert.deepEqual([look.source_type, look.scope], expectedWire);
}

const lookRoundTrip = normalizeState(JSON.parse(JSON.stringify({
  image_taxonomy: {
    image_main_type_choices: mainTypes,
    image_sub_type_choices: subTypes,
    actor_color_pick_choices: ["Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink"],
    object_color_pick_choices: ["Sky Blue", "Mint", "Beige", "Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"],
  },
  images: [look],
})));
assert.equal(lookRoundTrip.images[0].image_sub_type, "ch_Scale");
assert.equal(lookRoundTrip.images[0].source_type, "Relative Size Reference");
assert.equal(lookRoundTrip.images[0].scope, "Character Relative Size Only");
assert.equal(lookRoundTrip.images[0].owner, "ch_all");

for (const retiredSubtype of ["Scale", "Composition", "Scale / Composition"]) {
  const released = {
    image_main_type: "Look Reference",
    image_sub_type: retiredSubtype,
    owner: "Camera / Composition",
  };
  normalizeImageTaxonomy(released);
  assert.equal(released.image_main_type, "Select Image Main Type");
  assert.equal(released.image_sub_type, "");
  assert.equal(released.owner, "");
}

const targetRows = [
  { present: true, label: "Hero", image_main_type: "Character" },
  { present: true, label: "HeroProp", image_main_type: "Character Prop" },
  { present: true, label: "Forest", image_main_type: "Environment / Background" },
  { present: true, label: "Tree", image_main_type: "Background Prop" },
  { present: true, label: "DawnLook", image_main_type: "Look Reference" },
  { present: true, label: "Notes", image_main_type: "Custom / Context" },
];
const characterScale = {
  image_main_type: "Look Reference",
  image_sub_type: "ch_Scale",
  source_type: "Relative Size Reference",
  owner: "Camera / Composition",
};
assert.deepEqual(
  imageTargetChoicesForRow(characterScale, targetRows),
  ["Hero", "HeroProp", "ch_all"],
);
assert.equal(characterScale.owner, "ch_all");
const backgroundScale = { ...characterScale, image_sub_type: "bg_Scale", owner: "Global Look" };
assert.deepEqual(
  imageTargetChoicesForRow(backgroundScale, targetRows),
  ["Forest", "Tree", "bg_all"],
);
assert.equal(backgroundScale.owner, "bg_all");
const combinedScale = { ...characterScale, image_sub_type: "ch_Scale / bg_Scale", owner: "" };
assert.deepEqual(
  imageTargetChoicesForRow(combinedScale, targetRows),
  ["Hero", "HeroProp", "Forest", "Tree", "ch_all / bg_all"],
);
assert.equal(combinedScale.owner, "ch_all / bg_all");

// General Look attributes may address only renderable image authorities. The
// row's canonical owner wins over its display label, while Look/Custom rows and
// reserved system words never become named Target candidates.
const canonicalTargetRows = [
  {
    present: true,
    label: "Hero display label",
    owner: "HeroCanonical",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
  },
  {
    present: true,
    label: "Forest display label",
    owner: "ForestCanonical",
    image_main_type: "Environment / Background",
    image_sub_type: "Main Background",
  },
  {
    present: true,
    label: "DawnLook",
    owner: "DawnLook",
    image_main_type: "Look Reference",
    image_sub_type: "Render Look",
  },
  {
    present: true,
    label: "Notes",
    owner: "Notes",
    image_main_type: "Custom / Context",
    image_sub_type: "Context",
  },
  {
    present: true,
    label: "Safe display label",
    owner: "Camera / Composition",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
  },
];
const canonicalLook = {
  present: true,
  label: "Canonical Look",
  image_main_type: "Look Reference",
  image_sub_type: "Color Mood",
  source_type: "Color / Look Reference",
  owner: "HeroCanonical",
};
assert.deepEqual(
  imageTargetChoicesForRow(canonicalLook, [...canonicalTargetRows, canonicalLook]),
  ["", "HeroCanonical", "ForestCanonical", "Global Look"],
  "General Look choices must use canonical owners and exclude Look, Custom, self, and reserved names.",
);

for (const subType of ["Lighting / Atmosphere", "Color / Look / Lighting"]) {
  const globalScopeLook = {
    present: true,
    label: `${subType} Sheet`,
    image_main_type: "Look Reference",
    image_sub_type: subType,
    owner: "HeroCanonical",
    look_custom_instruction: "Apply a user-authored shared-lighting exception.",
  };
  assert.deepEqual(
    imageTargetChoicesForRow(globalScopeLook, canonicalTargetRows),
    ["Global Look", "Custom"],
    `${subType} must not expose individual image Targets.`,
  );
  assert.equal(globalScopeLook.owner, "Global Look");
  globalScopeLook.owner = "Custom";
  const customRoundTrip = normalizeState(JSON.parse(JSON.stringify({
    images: [globalScopeLook],
  })));
  assert.equal(customRoundTrip.images[0].owner, "Custom");
  assert.equal(
    customRoundTrip.images[0].look_custom_instruction,
    "Apply a user-authored shared-lighting exception.",
  );
}

const ambiguousDomainRows = [
  {
    present: true,
    label: "hero-shared.png",
    owner: "Shared_Target",
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
  },
  {
    present: true,
    label: "forest-shared.png",
    owner: "Ｓｈａｒｅｄ＿Ｔａｒｇｅｔ",
    image_main_type: "Environment / Background",
    image_sub_type: "Main Background",
  },
];
const ambiguousLook = {
  present: true,
  label: "ambiguous-look.png",
  owner: "shared_target",
  image_main_type: "Look Reference",
  image_sub_type: "Color Mood",
  source_type: "Color / Look Reference",
};
assert.deepEqual(
  imageTargetChoicesForRow(ambiguousLook, [...ambiguousDomainRows, ambiguousLook]),
  ["", "Global Look"],
  "Cross-domain duplicate addresses must not be offered as Look recipients.",
);
const normalizedAmbiguousLook = normalizeState({
  images: [...ambiguousDomainRows, ambiguousLook],
});
assert.equal(
  normalizedAmbiguousLook.images[2].owner,
  "",
  "A restored cross-domain ambiguous Look Target must be released.",
);

// Persisted workflow data and asset labels are not guaranteed to preserve the
// casing used by the current UI. Reserved targets and retired Scale taxonomy
// words must therefore be rejected case-insensitively instead of reappearing
// as apparently valid named recipients.
const reservedTargetCaseVariants = [
  "camera / composition",
  "CAMERA / COMPOSITION",
  "global look",
  "GLOBAL LOOK",
  "CH_ALL",
  "Bg_All",
  "CH_ALL / BG_ALL",
  "none",
  "NONE",
  "Scale",
  "scale",
  "SCALE",
  "Composition",
  "composition",
  "COMPOSITION",
  "Scale / Composition",
  "scale / composition",
  "SCALE / COMPOSITION",
  "Look",
  "look",
  "LOOK",
  "Custom",
  "custom",
  "CUSTOM",
  "self",
  "SELF",
];
const reservedCaseRows = reservedTargetCaseVariants.flatMap((target, index) => ([
  {
    present: true,
    label: `Reserved owner ${index}`,
    owner: target,
    image_main_type: "Character",
    image_sub_type: "Full Appearance",
  },
  {
    present: true,
    label: target,
    owner: "",
    image_main_type: "Environment / Background",
    image_sub_type: "Main Background",
  },
]));
const caseInsensitiveChoices = imageTargetChoicesForRow(
  { ...canonicalLook, owner: "" },
  [...canonicalTargetRows.slice(0, 2), ...reservedCaseRows],
);
assert.ok(caseInsensitiveChoices.includes("Global Look"));
assert.equal(
  caseInsensitiveChoices.filter((target) => target.toLowerCase() === "global look").length,
  1,
  "Only the canonical Global Look system option may survive case folding.",
);
for (const reserved of reservedTargetCaseVariants) {
  assert.ok(
    !caseInsensitiveChoices.includes(reserved),
    `${reserved} must not re-enter general Look targets through owner or label casing.`,
  );
}

for (const forbiddenOwner of reservedTargetCaseVariants.filter(
  (target) => target.toLowerCase() !== "global look",
)) {
  const persistedLook = {
    image_main_type: "Look Reference",
    image_sub_type: "Color Mood",
    owner: forbiddenOwner,
  };
  normalizeImageTaxonomy(persistedLook);
  assert.equal(
    persistedLook.owner,
    "",
    `${forbiddenOwner} must be removed from a persisted general Look row.`,
  );
}
for (const globalLookVariant of ["global look", "GLOBAL LOOK"]) {
  const persistedLook = {
    image_main_type: "Look Reference",
    image_sub_type: "Color Mood",
    owner: globalLookVariant,
  };
  normalizeImageTaxonomy(persistedLook);
  assert.ok(
    ["", "Global Look"].includes(persistedLook.owner),
    `Non-canonical ${globalLookVariant} must be canonicalized or cleared.`,
  );
}

// Version 1 and retired Scale/Composition names are intentionally unsupported.
// Existing assets are reset on this release, so stale rows and registered
// candidates must be released instead of silently migrated.
const rejectedLegacyScaleState = normalizeState({
  image_taxonomy: {
    image_main_type_choices: mainTypes,
    image_sub_type_choices: {
      ...subTypes,
      "Look Reference": [
        "Color Mood",
        "Lighting / Atmosphere",
        "Render Look",
        "Color / Look / Lighting",
        "Scale",
        "Composition",
        "Scale / Composition",
      ],
    },
    source_type_choices: [
      "Role Required / Select Source Type",
      "Scale / Composition Reference",
    ],
    scope_choices: ["", "Scale only", "Composition only", "Scale + composition"],
    scope_choices_by_source_type: {
      "Scale / Composition Reference": [
        "", "Scale only", "Composition only", "Scale + composition",
      ],
    },
  },
  images: [
    ["Scale", "ch_Scale", "ch_all"],
    ["Composition", "bg_Scale", "bg_all"],
    ["Scale / Composition", "ch_Scale / bg_Scale", "ch_all / bg_all"],
  ].map(([legacySubtype], index) => ({
    present: true,
    label: `Legacy Scale registration ${index + 1}`,
    image_main_type: "Look Reference",
    image_sub_type: legacySubtype,
    owner: "Camera / Composition",
    asset_image_main_type_candidate: "Look Reference",
    asset_image_sub_type_candidate: legacySubtype,
    asset_verified: true,
    asset_source_kind: "project",
  })),
});
assert.deepEqual(
  rejectedLegacyScaleState.image_taxonomy.image_sub_type_choices["Look Reference"],
  subTypes["Look Reference"],
  "Legacy taxonomy choices must not be republished.",
);
assert.ok(
  !Array.isArray(rejectedLegacyScaleState.image_taxonomy.source_type_choices),
  "A version-1 taxonomy must not restore the retired wire source type.",
);
for (const retiredScope of ["Scale only", "Composition only", "Scale + composition"]) {
  assert.ok(
    !Array.isArray(rejectedLegacyScaleState.image_taxonomy.scope_choices)
      || !rejectedLegacyScaleState.image_taxonomy.scope_choices.includes(retiredScope),
    `${retiredScope} must not return from a retired saved taxonomy.`,
  );
}
assert.equal(rejectedLegacyScaleState.image_taxonomy.schema, "hmb-image-taxonomy");
assert.equal(rejectedLegacyScaleState.image_taxonomy.version, 2);
for (const row of rejectedLegacyScaleState.images) {
  assert.equal(row.image_main_type, "Select Image Main Type");
  assert.equal(row.image_sub_type, "");
  assert.equal(row.asset_image_main_type_candidate, "");
  assert.equal(row.asset_image_sub_type_candidate, "");
  assert.equal(row.owner, "");
  assert.equal(row.asset_default_target, "");
}
const rejectedLegacyScaleReload = normalizeState(
  JSON.parse(JSON.stringify(rejectedLegacyScaleState)),
);
assert.deepEqual(
  rejectedLegacyScaleReload.image_taxonomy.image_sub_type_choices["Look Reference"],
  subTypes["Look Reference"],
);
assert.deepEqual(
  rejectedLegacyScaleReload.images.map((row) => ([
    row.image_main_type,
    row.image_sub_type,
    row.asset_image_sub_type_candidate,
    row.owner,
    row.asset_default_target,
  ])),
  [
    ["Select Image Main Type", "", "", "", ""],
    ["Select Image Main Type", "", "", "", ""],
    ["Select Image Main Type", "", "", "", ""],
  ],
  "A saved/reloaded state must not reintroduce retired taxonomy names.",
);

// Seven Look Sub Types by eleven persisted Target classes. This mirrors the
// backend matrix and also verifies the choices painted for each normalized row.
const lookSubTypes = [...subTypes["Look Reference"]];
const generalLookSubTypes = new Set(lookSubTypes.slice(0, 4));
const globalScopeLookSubTypes = new Set([
  "Lighting / Atmosphere", "Color / Look / Lighting",
]);
const forbiddenGeneralLookTargets = new Set([
  "Camera / Composition", "Custom", "ch_all", "bg_all", "ch_all / bg_all", "None",
]);
const scaleDefaults = {
  ch_Scale: "ch_all",
  bg_Scale: "bg_all",
  "ch_Scale / bg_Scale": "ch_all / bg_all",
};
const lookTargetMatrix = [
  "",
  "Global Look",
  "Custom",
  "Camera / Composition",
  "ch_all",
  "bg_all",
  "ch_all / bg_all",
  "None",
  "Hero",
  "Sword",
  "Forest",
  "Tree",
  "DawnLook",
  "Notes",
  "Look Sheet",
];
const namedTargetRows = [
  { present: true, label: "Hero", image_main_type: "Character", image_sub_type: "Full Appearance", owner: "Hero" },
  { present: true, label: "Sword", image_main_type: "Character Prop", image_sub_type: "Handheld Prop", owner: "Sword" },
  { present: true, label: "Forest", image_main_type: "Environment / Background", image_sub_type: "Main Background", owner: "Forest" },
  { present: true, label: "Tree", image_main_type: "Background Prop", image_sub_type: "Independent Scene Prop", owner: "Tree" },
  { present: true, label: "DawnLook", image_main_type: "Look Reference", image_sub_type: "Render Look", owner: "DawnLook" },
  { present: true, label: "Notes", image_main_type: "Custom / Context", image_sub_type: "Context", owner: "Notes" },
];
const nonRecipientLookTargets = new Set(["DawnLook", "Notes", "Look Sheet"]);

function expectedLookTarget(subType, target) {
  if (globalScopeLookSubTypes.has(subType)) {
    return target === "Custom" ? "Custom" : "Global Look";
  }
  if (generalLookSubTypes.has(subType)) {
    return forbiddenGeneralLookTargets.has(target) || nonRecipientLookTargets.has(target)
      ? ""
      : target;
  }
  const scaleDefault = scaleDefaults[subType];
  if (subType === "ch_Scale" && ["Hero", "Sword", scaleDefault].includes(target)) return target;
  if (subType === "bg_Scale" && ["Forest", "Tree", scaleDefault].includes(target)) return target;
  if (
    subType === "ch_Scale / bg_Scale"
    && ["Hero", "Sword", "Forest", "Tree", scaleDefault].includes(target)
  ) return target;
  return scaleDefault;
}

let lookTargetMatrixCount = 0;
for (const lookSubType of lookSubTypes) {
  for (const authoredTarget of lookTargetMatrix) {
    const matrixState = normalizeState({
      image_taxonomy: {
        image_main_type_choices: mainTypes,
        image_sub_type_choices: subTypes,
      },
      images: [
        ...namedTargetRows.map((row) => ({ ...row })),
        {
          present: true,
          label: "Look Sheet",
          image_main_type: "Look Reference",
          image_sub_type: lookSubType,
          owner: authoredTarget,
          asset_default_target: authoredTarget,
        },
      ],
    });
    const normalizedLook = matrixState.images.find((row) => row.label === "Look Sheet");
    assert.ok(normalizedLook);
    assert.equal(
      normalizedLook.owner,
      expectedLookTarget(lookSubType, authoredTarget),
      `${lookSubType} / ${authoredTarget || "<blank>"}`,
    );
    assert.equal(
      normalizedLook.asset_default_target,
      globalScopeLookSubTypes.has(lookSubType)
        ? "Global Look"
        : (generalLookSubTypes.has(lookSubType) ? "" : scaleDefaults[lookSubType]),
    );
    const targetChoices = imageTargetChoicesForRow(normalizedLook, matrixState.images);
    if (globalScopeLookSubTypes.has(lookSubType)) {
      assert.deepEqual(targetChoices, ["Global Look", "Custom"]);
    } else if (generalLookSubTypes.has(lookSubType)) {
      assert.ok(targetChoices.includes(""));
      assert.ok(!targetChoices.includes("Camera / Composition"));
      assert.ok(targetChoices.includes("Global Look"));
      for (const forbidden of forbiddenGeneralLookTargets) {
        assert.ok(!targetChoices.includes(forbidden));
      }
      for (const nonRecipient of nonRecipientLookTargets) {
        assert.ok(!targetChoices.includes(nonRecipient));
      }
    }
    lookTargetMatrixCount += 1;
  }
}
assert.equal(lookTargetMatrixCount, lookSubTypes.length * lookTargetMatrix.length);

// When ImageAsset owns the source list, only selected asset-managed rows may
// become Target candidates. Manual rows and both dormant stores remain inert.
const connectedState = normalizeState({
  image_taxonomy: {
    image_main_type_choices: mainTypes,
    image_sub_type_choices: subTypes,
  },
  images: [
    {
      present: true,
      label: "Managed hero display",
      owner: "ManagedHero",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
      asset_managed: true,
      asset_source_uid: "asset:managed-hero",
    },
    {
      present: true,
      label: "Manual hero",
      owner: "ManualHero",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
      asset_managed: false,
    },
    {
      present: true,
      label: "Managed look",
      owner: "ManagedHero",
      image_main_type: "Look Reference",
      image_sub_type: "Render Look",
      asset_managed: true,
      asset_source_uid: "asset:managed-look",
    },
  ],
  image_asset: {
    enabled: true,
    dormant_manual_rows: [{
      present: true,
      label: "Dormant manual",
      owner: "DormantManual",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
    }],
    dormant_asset_rows: [{
      present: true,
      label: "Dormant asset",
      owner: "DormantAsset",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
      asset_managed: true,
      asset_source_uid: "asset:dormant",
    }],
  },
});
const connectedLook = connectedState.images.find((row) => row.label === "Managed look");
assert.ok(connectedLook);
assert.equal(connectedLook.owner, "ManagedHero");
assert.deepEqual(
  imageTargetChoicesForRow(connectedLook, connectedState.images, connectedState),
  ["", "ManagedHero", "Global Look"],
);
for (const excluded of ["ManualHero", "DormantManual", "DormantAsset"] ) {
  assert.ok(
    !imageTargetChoicesForRow(connectedLook, connectedState.images, connectedState).includes(excluded),
    `${excluded} must not become a connected ImageAsset Target candidate.`,
  );
}

// Seven-by-seven canonical subtype transitions. Generated Scale all targets
// are released to blank on every transition back to a general Look subtype.
let lookTransitionMatrixCount = 0;
for (const sourceSubType of lookSubTypes) {
  for (const destinationSubType of lookSubTypes) {
    const transition = {
      image_main_type: "Look Reference",
      image_sub_type: sourceSubType,
      owner: scaleDefaults[sourceSubType] || "",
      asset_default_target: scaleDefaults[sourceSubType] || "",
    };
    normalizeImageTaxonomy(transition);
    transition.image_sub_type = destinationSubType;
    normalizeImageTaxonomy(transition);
    const destinationTarget = scaleDefaults[destinationSubType]
      || (globalScopeLookSubTypes.has(destinationSubType)
        ? "Global Look"
        : (globalScopeLookSubTypes.has(sourceSubType) ? "Global Look" : ""));
    assert.equal(
      transition.owner,
      destinationTarget,
      `${sourceSubType} -> ${destinationSubType}`,
    );
    const destinationDefault = scaleDefaults[destinationSubType]
      || (globalScopeLookSubTypes.has(destinationSubType) ? "Global Look" : "");
    assert.equal(transition.asset_default_target, destinationDefault);
    lookTransitionMatrixCount += 1;
  }
}
assert.equal(lookTransitionMatrixCount, 7 * 7);

assert.ok(!mainTypes.includes("Scene / Look Reference"));
assert.ok(!mainTypes.includes("Character Appearance"));

console.log("HMB image taxonomy widget regression: PASS");
