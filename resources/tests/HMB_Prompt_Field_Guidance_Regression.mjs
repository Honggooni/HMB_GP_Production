import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBPromptLibraryScopedBindingWidget.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(widgetPath);

// A state saved by the short-lived QA-display build is accepted, but the
// removed display-only member is discarded on the next normalization.
const forged = widget.normalizeState({
  prompt_guidance: {
    schema: "hmb-prompt-input-qa-coverage",
    version: 999,
    profiles: { prompt_only: { IMAGE_SHEET: 999 } },
  },
});
assert.equal(Object.hasOwn(forged, "prompt_guidance"), false);

const globalLook = {
  image_main_type: "Look Reference",
  image_sub_type: "Color / Look / Lighting",
  owner: "Global Look",
};
widget.normalizeImageTaxonomy(globalLook);
assert.equal(globalLook.owner, "Global Look");
assert.match(
  widget.hmbImageSubtypeAuthorityHint(globalLook, { ui: { language: "ko" } }),
  /기본적으로 전체 룩.*개별 대상 또는 사용자 지정 지시.*로컬 범위.*빈 대상도 그대로 유지.*복제하지 않습니다/,
);

const freshGeneralLook = {
  image_main_type: "Look Reference",
  image_sub_type: "Color Mood",
  owner: "ch_all",
  asset_default_target: "Global Look",
};
widget.normalizeImageTaxonomy(freshGeneralLook);
assert.equal(freshGeneralLook.owner, "ch_all");
assert.equal(freshGeneralLook.asset_default_target, "Global Look");
const freshGeneralChoices = widget.imageTargetChoicesForRow(
  freshGeneralLook,
  [{ present: true, label: "Jett_11", image_main_type: "Character" }],
);
assert.ok(freshGeneralChoices.includes("Camera / Composition"));
assert.ok(freshGeneralChoices.includes("Custom"));
assert.ok(freshGeneralChoices.includes("Global Look"));
assert.ok(freshGeneralChoices.includes("Jett_11"));
assert.ok(freshGeneralChoices.includes("ch_all"));
for (const scaleOnlyTarget of ["bg_all", "ch_all / bg_all", "None"]) {
  assert.ok(!freshGeneralChoices.includes(scaleOnlyTarget));
}
freshGeneralLook.owner = "Camera / Composition";
widget.normalizeImageTaxonomy(freshGeneralLook);
assert.equal(freshGeneralLook.owner, "Camera / Composition");
assert.ok(widget.imageTargetChoicesForRow(freshGeneralLook, []).includes("Camera / Composition"));

const scopedLookState = widget.normalizeState({
  images: [
    {
      present: true,
      label: "Jett display",
      owner: "JettCanonical",
      image_main_type: "Character",
      image_sub_type: "Full Appearance",
    },
    {
      present: true,
      label: "Other Look",
      owner: "OtherLookCanonical",
      image_main_type: "Look Reference",
      image_sub_type: "Color Mood",
    },
    {
      present: true,
      label: "Shot notes",
      owner: "NotesCanonical",
      image_main_type: "Custom / Context",
      image_sub_type: "Context",
    },
    {
      present: true,
      label: "Self Look",
      owner: "Self Look",
      image_main_type: "Look Reference",
      image_sub_type: "Color Mood",
    },
    {
      present: true,
      label: "Reserved display",
      owner: "None",
      image_main_type: "Environment / Background",
      image_sub_type: "Main Background",
    },
  ],
});
const scopedLook = scopedLookState.images.find((row) => row.label === "Self Look");
assert.ok(scopedLook);
assert.equal(scopedLook.owner, "Self Look", "An explicitly authored self Target remains intact.");
const scopedChoices = widget.imageTargetChoicesForRow(
  scopedLook,
  scopedLookState.images,
  scopedLookState,
);
assert.ok(scopedChoices.includes("JettCanonical"));
for (const included of [
  "Jett display", "Camera / Composition", "Other Look", "OtherLookCanonical",
  "Shot notes", "NotesCanonical", "Global Look", "Custom",
]) {
  assert.ok(scopedChoices.includes(included), `${included} must remain an available Target candidate.`);
}
assert.ok(scopedChoices.includes("Self Look"), "The current authored Target remains selectable.");

for (const subtype of [
  "Render Look",
]) {
  const targetedReference = {
    image_main_type: "Look Reference",
    image_sub_type: subtype,
    owner: "Jett_11",
  };
  widget.normalizeImageTaxonomy(targetedReference);
  assert.equal(targetedReference.owner, "Jett_11");
  const targetedHint = widget.hmbImageSubtypeAuthorityHint(
    targetedReference,
    { ui: { language: "en" } },
  );
  assert.match(targetedHint, /selected (?:Target|sources)/i);
  assert.doesNotMatch(targetedHint, /apply to every visible|applies globally/i);
  assert.match(targetedHint, /never copied/i);
}

for (const subtype of ["Lighting / Atmosphere", "Color / Look / Lighting"]) {
  const sharedLightingReference = {
    image_main_type: "Look Reference",
    image_sub_type: subtype,
    owner: "Jett_11",
    look_custom_instruction: "Keep the foreground readable.",
  };
  widget.normalizeImageTaxonomy(sharedLightingReference);
  assert.equal(sharedLightingReference.owner, "Jett_11");
  const sharedChoices = widget.imageTargetChoicesForRow(
    sharedLightingReference,
    scopedLookState.images,
  );
  for (const choice of ["JettCanonical", "Global Look", "Custom", "Jett_11"]) {
    assert.ok(sharedChoices.includes(choice));
  }
  const sharedHint = widget.hmbImageSubtypeAuthorityHint(
    sharedLightingReference,
    { ui: { language: "en" } },
  );
  assert.match(sharedHint, /Global Look by default/i);
  assert.match(sharedHint, /affected properties/i);
  assert.match(sharedHint, /named Target or Custom instruction/i);
  assert.match(sharedHint, /local scope/i);
  assert.match(sharedHint, /blank Target is also preserved/i);
  sharedLightingReference.owner = "Custom";
  const restored = widget.normalizeState(JSON.parse(JSON.stringify({
    images: [sharedLightingReference],
  })));
  assert.equal(restored.images[0].owner, "Custom");
  assert.equal(restored.images[0].look_custom_instruction, "Keep the foreground readable.");
}

assert.match(
  source,
  /Specify affected properties and scope: name a target .* or state scene-wide\./,
);
assert.match(
  source,
  /영향 속성과 적용 범위를 직접 작성: 대상 이름\(예: Hero 조명만\) 또는 장면 전체를 명시하세요\./,
);

for (const [subtype, target, phrase] of [
  ["ch_Scale", "ch_all", /character\/Character Prop size/i],
  ["bg_Scale", "bg_all", /background size and placement/i],
  ["ch_Scale / bg_Scale", "ch_all / bg_all", /character\/background relative size/i],
]) {
  const scaleReference = {
    image_main_type: "Look Reference",
    image_sub_type: subtype,
    owner: "Camera / Composition",
  };
  widget.normalizeImageTaxonomy(scaleReference);
  assert.equal(scaleReference.owner, "Camera / Composition");
  const scaleChoices = widget.imageTargetChoicesForRow(scaleReference, []);
  assert.ok(!scaleChoices.includes(target), "Target defaults must not be inferred from Sub Type.");
  assert.ok(scaleChoices.includes("Camera / Composition"));
  const hint = widget.hmbImageSubtypeAuthorityHint(
    scaleReference,
    { ui: { language: "en" } },
  );
  assert.match(hint, phrase);
  assert.match(hint, /never (?:copy|renderable)/i);
}

assert.doesNotMatch(source, /장면 전체 적용 · 컬러 픽 없음/);
assert.doesNotMatch(source, /Scene-wide · no Color Pick/);

const exactLegacyAndCurrent = (
  "[Lip-sync Transcript] 안녕, Jett!\n"
  + "[Lip-sync Speech] legacy stays EXACT."
);
const exactState = widget.normalizeState({
  text: { PRESERVED_TEXT: exactLegacyAndCurrent },
});
assert.equal(exactState.text.PRESERVED_TEXT, exactLegacyAndCurrent);
const whitespaceSensitiveText = "  keep leading space\nkeep trailing space  ";
assert.equal(
  widget.normalizeState({ text: { VIDEO_VFX: whitespaceSensitiveText } }).text.VIDEO_VFX,
  whitespaceSensitiveText,
);

assert.match(source, /EXACT LITERALS \(TEXT ONLY\)/);
assert.match(source, /\[Lip-sync Transcript\]/);
assert.match(source, /Existing \[Lip-sync Speech\] entries remain compatible and unchanged/);
assert.match(source, /it does not activate a media operation/);
assert.match(source, /VIDEO ACTION \/ LIP-SYNC \/ VFX/);
assert.match(source, /video_vfx: "VFX"/);
assert.match(source, /VIDEO_VFX: \["영상 작업 \/ 립싱크 \/ VFX", ""\]/);
assert.doesNotMatch(source, /operational shot direction: named target or emitter/);
assert.doesNotMatch(source, /대상·에미터, 입력 영상·오디오/);
assert.doesNotMatch(source, /HMB_PROMPT_QA_COVERAGE/);
assert.doesNotMatch(source, /class="qa-badge"/);
assert.doesNotMatch(source, /qa_coverage_not_provider_attention/);

console.log(
  "HMB Prompt field guidance regression: PASS "
  + "(no QA display state, lip-sync split, exact legacy text, Look authority hints)",
);
