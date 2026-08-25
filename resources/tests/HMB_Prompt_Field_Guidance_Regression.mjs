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
  /선택한 대상에만 적용.*전체 룩/,
);

for (const subtype of [
  "Render Look",
  "Lighting / Atmosphere",
  "Scale",
  "Composition",
  "Scale / Composition",
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
  assert.match(targetedHint, /appl(?:y|ies) only to the selected Target/i);
  assert.doesNotMatch(targetedHint, /apply to every visible|applies globally/i);
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

assert.match(source, /EXACT LITERALS \(TEXT ONLY\)/);
assert.match(source, /\[Lip-sync Transcript\]/);
assert.match(source, /Existing \[Lip-sync Speech\] entries remain compatible and unchanged/);
assert.match(source, /it does not activate a media operation/);
assert.match(source, /VIDEO ACTION \/ LIP-SYNC \/ VFX/);
assert.doesNotMatch(source, /HMB_PROMPT_QA_COVERAGE/);
assert.doesNotMatch(source, /class="qa-badge"/);
assert.doesNotMatch(source, /qa_coverage_not_provider_attention/);

console.log(
  "HMB Prompt field guidance regression: PASS "
  + "(no QA display state, lip-sync split, exact legacy text, Look authority hints)",
);
