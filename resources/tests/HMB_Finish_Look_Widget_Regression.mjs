import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL("../../widgets/HMBFinishLookLibraryWidget.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");

assert.match(widgetSource, /film:\s*"FILTER APPLICATION"/);
assert.match(widgetSource, /film:\s*"필터 적용"/);
assert.doesNotMatch(widgetSource, /film:\s*"(?:FILM RESPONSE|필름 응답)"/);
assert.match(widgetSource, /beauty:\s*"CHARACTER BEAUTY"/);
assert.match(widgetSource, /beauty:\s*"캐릭터 뷰티"/);
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);

const defaultState = widget.hmbNormalizeFinishLookWidgetValue({});
assert.deepEqual(Object.keys(defaultState), [
  "schema_version",
  "language",
  "remote_connected",
  "shot_catalog",
  "shot",
  "catalog",
  "finish_look",
]);
assert.equal(defaultState.schema_version, 1);
assert.equal(defaultState.language, "ko");
assert.equal(defaultState.remote_connected, false);
assert.deepEqual(defaultState.shot_catalog, {});
assert.deepEqual(defaultState.shot, {
  channel_uuid: "",
  shot_uuid: "",
  number: 1,
  name: "Only",
});
assert.equal(widget.HMB_FINISH_LOOK_ONLY_SHOT_VALUE, "__hmb_only__");
assert.deepEqual(widget.HMB_FINISH_LOOK_SHOT_PALETTE, {
  1: "#F472B6",
  2: "#3B82F6",
  3: "#10B981",
  4: "#8B5CF6",
  5: "#EAB308",
});
assert.equal(widget.hmbFinishLookPaletteShotNumber(defaultState), 0);
assert.equal(widget.hmbFinishLookShotAccent(defaultState), "#64748B");
assert.deepEqual(defaultState.catalog, {
  negative: ["None", "Kodak 5245"],
  print: ["None", "Kodak 2383"],
  reversal: [],
});
assert.deepEqual(Object.keys(defaultState.finish_look.beauty), [
  "enabled",
  "soften_shadows",
  "shadow_threshold",
  "saturation",
  "brightness",
  "glow_brightness",
  "glow_threshold",
  "glow_width",
  "soft_focus",
  "blur_amount",
  "pore_size",
  "reduce_shine",
]);
assert.equal(
  Object.prototype.hasOwnProperty.call(defaultState.finish_look.beauty, "preset"),
  false,
  "BEAUTY is Enable + numeric fields only; it must never serialize a preset.",
);
const backendCatalog = {
  negative: ["None", "Lab Negative A", "Lab Negative B"],
  print: ["None", "Lab Print A", "Lab Reversal"],
  reversal: ["Lab Reversal"],
};
const sparseShotCatalog = {
  schema: "hmb-shot-routing-catalog",
  version: 1,
  publisher_instance_uuid: "image-library-instance",
  channel_uuid: "shared-shot-channel",
  generation: 9,
  metadata_sha256: "a".repeat(64),
  shots: [
    { shot_uuid: "shot-one", number: 1, name: "Opening", revision: 1 },
    { shot_uuid: "shot-three", number: 3, name: "Forest", revision: 2 },
    { shot_uuid: "shot-five", number: 5, name: "Finale", revision: 3 },
  ],
};
const catalogState = widget.hmbNormalizeFinishLookWidgetValue({
  catalog: backendCatalog,
  shot_catalog: sparseShotCatalog,
  value: {
    language: "en",
    shot: {
      channel_uuid: "shared-shot-channel",
      shot_uuid: "shot-three",
      number: 3,
      name: "Forest",
    },
    finish_look: {
      beauty: { enabled: false, preset: "must-be-discarded", saturation: 1.75 },
      film: {
        enabled: true,
        negative_film: "Lab Negative B",
        print_film: "Lab Reversal",
        scale_cc: 0.45,
      },
    },
  },
});
assert.deepEqual(catalogState.catalog, backendCatalog, "Backend catalog must be the UI source of truth.");
assert.equal(catalogState.finish_look.film.negative_film, "Lab Negative B");
assert.equal(catalogState.finish_look.film.print_film, "Lab Reversal");
assert.equal(catalogState.finish_look.beauty.enabled, false);
assert.equal(catalogState.finish_look.beauty.saturation, 1.75);
assert.equal("preset" in catalogState.finish_look.beauty, false);
assert.deepEqual(catalogState.shot_catalog, sparseShotCatalog);
assert.deepEqual(catalogState.shot, {
  channel_uuid: "shared-shot-channel",
  shot_uuid: "shot-three",
  number: 3,
  name: "Forest",
});
assert.deepEqual(
  widget.hmbFinishLookShotOptions(catalogState).map((item) => ({
    number: item.number,
    selected: item.selected,
    only: item.only,
  })),
  [
    { number: 0, selected: false, only: true },
    { number: 1, selected: false, only: false },
    { number: 3, selected: true, only: false },
    { number: 5, selected: false, only: false },
  ],
);
assert.equal(widget.hmbFinishLookPaletteShotNumber(catalogState), 3);
assert.equal(widget.hmbFinishLookShotAccent(catalogState), "#10B981");
assert.equal(
  widget.hmbFinishLookShotOptionLabel(
    widget.hmbFinishLookShotOptions(catalogState)[2],
  ),
  "03 · Forest",
);
const onlySelection = widget.hmbNormalizeFinishLookWidgetValue({
  ...catalogState,
  shot: {},
});
assert.equal(widget.hmbFinishLookShotOptions(onlySelection)[0].selected, true);
assert.equal(widget.hmbFinishLookPaletteShotNumber(onlySelection), 0);
assert.equal(
  widget.hmbFinishLookNonShotStateFingerprint(catalogState),
  widget.hmbFinishLookNonShotStateFingerprint(onlySelection),
  "Shot-only changes must not force a full Finish Look UI remount.",
);
assert.doesNotMatch(
  widgetSource,
  /Kodak 5246|Kodak 5248|Kodak 5274|Kodak 2393|Kodak 5285 Rev/,
  "The widget must not duplicate the backend's complete stock catalog.",
);

const catalogMarkup = widget.hmbRenderFinishLookWidget(catalogState);
assert.match(catalogMarkup, /data-shot-number="3"/);
assert.match(catalogMarkup, /data-shot-bound="true"/);
assert.match(catalogMarkup, /class="hmb-finish-look__shot-select/);
assert.match(catalogMarkup, /03 · Forest/);
assert.match(catalogMarkup, /hmb-finish-look__bound-badge/);
assert.match(catalogMarkup, /Lab Negative A/);
assert.match(catalogMarkup, /Lab Reversal/);
assert.match(
  catalogMarkup,
  /data-stock-dropdown="negative_film"[\s\S]*?data-stock-trigger[\s\S]*? disabled/,
  "A backend-declared reversal print stock must disable the negative selector.",
);
const beautyMarkup = catalogMarkup.match(
  /data-finish-section="beauty"[\s\S]*?data-finish-section="film"/,
)?.[0] || "";
assert.doesNotMatch(beautyMarkup, /preset|custom/i);

const preservedKo = widget.hmbNormalizeFinishLookWidgetValue({...catalogState, language:"ko"});
const preservedEn = widget.hmbNormalizeFinishLookWidgetValue({...preservedKo, language:"en"});
assert.deepEqual(preservedEn.finish_look,preservedKo.finish_look);
assert.deepEqual(preservedEn.catalog,preservedKo.catalog);

const defaultMarkup = widget.hmbRenderFinishLookWidget(defaultState);
// Every numeric authoring control has exactly one discrete, localized slider.
assert.deepEqual(Object.keys(widget.HMB_FINISH_LOOK_STEPS), Object.keys(widget.HMB_FINISH_LOOK_NUMBER_RULES));
assert.equal((defaultMarkup.match(/<input[^>]*type="range"/g) || []).length, 22);
assert.doesNotMatch(defaultMarkup, /<input[^>]*type="number"|data-finish-number/);
let stepCount = 0;
for (const [path, options] of Object.entries(widget.HMB_FINISH_LOOK_STEPS)) {
  const [group, key] = path.split(".");
  assert.ok(options.some((option) => option.value === defaultState.finish_look[group][key]), `${path} default retained`);
  assert.equal(new Set(options.map((option) => option.ko)).size, options.length);
  for (const [index, option] of options.entries()) {
    stepCount += 1;
    assert.ok(option.ko && option.en);
    assert.equal(widget.hmbValidateFinishLookNumber(path, String(option.value)).ok, true);
    assert.equal(widget.hmbFinishLookStepIndex(path, option.value), index);
    assert.equal(widget.hmbFinishLookStepValue(path, String(index)), option.value);
    const changed = structuredClone(defaultState);
    changed.finish_look[group][key] = option.value;
    const restored = widget.hmbFinishLookPublication(JSON.parse(JSON.stringify(changed)));
    assert.equal(restored.finish_look[group][key], option.value, `${path} save/restore`);
    for (const language of ["ko", "en"]) {
      assert.equal(widget.hmbFinishLookStepLabel(path, option.value, language), option[language]);
      const markup = widget.hmbRenderFinishLookWidget({ ...restored, language });
      assert.ok(markup.includes(`aria-valuetext="${option[language]}"`));
    }
  }
  for (const invalid of ["", "-1", "0.5", "Infinity", String(options.length)]) {
    assert.equal(widget.hmbFinishLookStepValue(path, invalid), null);
  }
}
// Legacy and remote values are not silently changed merely by rendering.
const legacySteps = structuredClone(defaultState);
legacySteps.finish_look.beauty.brightness = 1.234;
assert.match(widget.hmbRenderFinishLookWidget(legacySteps), /기존 설정 ≈/);
assert.equal(widget.hmbFinishLookPublication(legacySteps).finish_look.beauty.brightness, 1.234);
console.log(`Finish Look discrete steps: PASS (22 controls, ${stepCount} stops, KO/EN, save/restore)`);
assert.doesNotMatch(defaultMarkup, /<[^>]+data-video-drawer(?:\s|=)/);
assert.equal((defaultMarkup.match(/data-concat-input=/g) || []).length, 0);
assert.match(defaultMarkup, /data-workspace-mode="finish"/);
assert.doesNotMatch(defaultMarkup, /data-workspace-toggle-surface="header"/);
assert.match(defaultMarkup, />FL<\/div>/);
assert.match(defaultMarkup, /<main class="hmb-finish-look__content">/);
assert.doesNotMatch(defaultMarkup, /data-video-workspace/);
assert.match(widgetSource, /height:68px;min-height:68px/);
assert.match(widgetSource, /hmb-finish-look__mark\{flex:0 0 30px;width:30px;height:30px/);
assert.match(widgetSource, /width:210px;min-width:120px;max-width:210px/);
assert.match(widgetSource, /hmb-finish-look__shot-select\{[^}]*height:44px[^}]*font-size:13px/);
assert.match(widgetSource, /hmb-finish-look__language\{[^}]*height:30px[^}]*min-width:58px/);
assert.doesNotMatch(widgetSource, /hmb-finish-look__(?:drawer-toggle|legacy-video)/);

assert.doesNotMatch(widgetSource, /data-video-command|data-concat-input=|data-crop-video|TOOL_COMMAND/);
assert.equal("video_tools" in defaultState, false);

const remoteState = widget.hmbNormalizeFinishLookWidgetValue({
  ...preservedKo,
  remote_connected: true,
});
assert.equal(remoteState.remote_connected, true);
const remoteMarkup = widget.hmbRenderFinishLookWidget(remoteState);
assert.match(remoteMarkup, /data-remote-connected="true"/);
assert.match(remoteMarkup, /hmb-finish-look__remote-badge">REMOTE<\/span>/);
const remoteShotSelect = remoteMarkup.match(
  /<select[^>]*class="hmb-finish-look__shot-select[^>]*>/,
)?.[0] || "";
assert.ok(remoteShotSelect);
assert.doesNotMatch(
  remoteShotSelect,
  / disabled/,
  "REMOTE locks Finish authoring only; the Shot selector remains independent.",
);
const remoteBeautyMarkup = remoteMarkup.match(
  /data-finish-section="beauty"[\s\S]*?data-finish-section="film"/,
)?.[0] || "";
const remoteFilmMarkup = remoteMarkup.match(
  /data-finish-section="film"[\s\S]*?<\/main>/,
)?.[0] || "";
assert.match(remoteBeautyMarkup, /data-enable="beauty"[^>]* disabled/);
assert.match(remoteBeautyMarkup, /data-finish-step="beauty\.saturation"[^>]* disabled/);
assert.match(remoteFilmMarkup, /data-enable="film"[^>]* disabled/);
assert.match(remoteFilmMarkup, /data-stock-trigger[^>]* disabled/);
assert.match(remoteFilmMarkup, /data-finish-step="film\.scale_cc"[^>]* disabled/);
const remoteVideoInputTag = remoteMarkup.match(
  /<input[^>]*data-video-field="crop\.input"[^>]*>/,
)?.[0] || "";
assert.equal(remoteVideoInputTag, "", "Video editing is now only in Picker expanded mode.");
const remoteLanguageTag = remoteMarkup.match(
  /<button[^>]*data-language-toggle[^>]*>/,
)?.[0] || "";
assert.ok(remoteLanguageTag);
assert.doesNotMatch(remoteLanguageTag, / disabled/);
const remotePublication = widget.hmbFinishLookPublication(remoteState);
assert.equal(remotePublication.remote_connected, true);
assert.deepEqual(remotePublication.finish_look, remoteState.finish_look);

assert.deepEqual(widget.hmbValidateFinishLookNumber("beauty.saturation", "2.25"), {
  ok: true,
  value: 2.25,
});
assert.equal(widget.hmbValidateFinishLookNumber("beauty.saturation", "Infinity").ok, false);
assert.equal(widget.hmbValidateFinishLookNumber("beauty.reduce_shine", "1.1").ok, false);
assert.equal(widget.hmbValidateFinishLookNumber("film.input_gamma", "0").ok, false);
assert.equal(widget.hmbValidateFinishLookNumber("film.printer_light_r", "25.5").ok, false);


assert.deepEqual(widget.hmbDropdownNavigationIndex("ArrowDown", 2, 4), 3);
assert.deepEqual(widget.hmbDropdownNavigationIndex("ArrowDown", 3, 4), 0);
assert.deepEqual(widget.hmbDropdownNavigationIndex("ArrowUp", 0, 4), 3);
assert.deepEqual(widget.hmbDropdownNavigationIndex("Home", 3, 4), 0);
assert.deepEqual(widget.hmbDropdownNavigationIndex("End", 0, 4), 3);
assert.match(widgetSource, /pointerdown[\s\S]*?data-stock-dropdown/);
assert.match(widgetSource, /ArrowDown/);
assert.match(widgetSource, /Escape/);
assert.match(widgetSource, /data-stock-option/);

const scopedCss = widget.hmbScopeWidgetCss(
  ".field,.hmb-finish-look .owned{color:red}@media(max-width:2px){button{display:none}}",
  ".hmb-finish-look",
);
assert.match(scopedCss, /\.hmb-finish-look \.field/);
assert.match(scopedCss, /\.hmb-finish-look \.owned/);
assert.match(scopedCss, /@media\(max-width:2px\)\{\.hmb-finish-look button/);

function selectedNode() {
  return {
    className: "react-flow__node selected",
    parentElement: null,
    classList: { contains: (name) => name === "selected" },
    getAttribute: () => null,
    querySelector: () => null,
  };
}

function deletionEvent(editing = false) {
  const calls = { preventDefault: 0, stopPropagation: 0, stopImmediatePropagation: 0 };
  return {
    calls,
    event: {
      key: "Delete",
      target: { closest: () => (editing ? {} : null) },
      preventDefault: () => { calls.preventDefault += 1; },
      stopPropagation: () => { calls.stopPropagation += 1; },
      stopImmediatePropagation: () => { calls.stopImmediatePropagation += 1; },
    },
  };
}

const deleteProbe = deletionEvent(false);
assert.equal(
  widget.hmbGuardSelectedNodeKeyboardDelete({ parentElement: selectedNode() }, deleteProbe.event),
  true,
);
assert.deepEqual(deleteProbe.calls, {
  preventDefault: 1,
  stopPropagation: 1,
  stopImmediatePropagation: 1,
});
const editingDeleteProbe = deletionEvent(true);
assert.equal(
  widget.hmbGuardSelectedNodeKeyboardDelete(
    { parentElement: selectedNode() },
    editingDeleteProbe.event,
  ),
  false,
);

console.log("HMB Finish Look widget regression: PASS");
