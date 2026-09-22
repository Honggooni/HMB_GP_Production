import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBFinishLookLibraryWidget.js", import.meta.url);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(widgetPath);
const expectedBeauty = {
  enabled: false, soften_shadows: 0.11, shadow_threshold: 0.27,
  saturation: 1, brightness: 1, glow_brightness: 0, glow_threshold: 0.2,
  glow_width: 16, soft_focus: 0, blur_amount: 0, pore_size: 0, reduce_shine: 0,
};
const expectedStops = {
  soften_shadows: [-0.5, -0.1, 0, 0.11, 0.2, 0.5],
  shadow_threshold: [0.1, 0.27, 0.6],
  saturation: [-1.5, -0.8, -0.2, 0, 0.8, 0.95, 1, 1.05, 1.2],
  brightness: [0.5, 0.8, 1, 1.2, 1.5],
  glow_brightness: [0, 0.05, 0.1, 0.2, 0.4, 0.8],
  glow_threshold: [0, 0.2, 0.5, 0.8],
  glow_width: [0, 8, 16, 32, 64],
  soft_focus: [0, 0.05, 0.1, 0.2, 0.4, 0.8],
  blur_amount: [0, 0.05, 0.1, 0.2, 0.4, 0.8],
  pore_size: [0, 0.05, 0.1, 0.2, 0.4, 0.8],
  reduce_shine: [0, 0.05, 0.1, 0.2, 0.4, 0.8],
};
assert.deepEqual(widget.hmbNormalizeFinishLookWidgetValue({}).finish_look.beauty, expectedBeauty);
for (const [key, values] of Object.entries(expectedStops)) {
  assert.deepEqual(widget.HMB_FINISH_LOOK_STEPS[`beauty.${key}`].map(row => row.value), values);
}
assert.equal(Object.keys(widget.HMB_FINISH_LOOK_NUMBER_RULES).length, 11);
assert.equal(Object.keys(widget.HMB_FINISH_LOOK_STEPS).length, 11);
const disabledDefault = widget.hmbNormalizeFinishLookWidgetValue({});
for (const path of Object.keys(widget.HMB_FINISH_LOOK_STEPS)) {
  assert.equal(widget.hmbFinishLookFieldEnabled(disabledDefault, path), false);
}
const enabledState = widget.hmbNormalizeFinishLookWidgetValue({
  finish_look: { schema_version: 1, beauty: { ...expectedBeauty, enabled: true } },
});
assert.equal(enabledState.finish_look.beauty.enabled, true, "An explicit legacy enable is preserved.");
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.glow_brightness"), true);
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.glow_threshold"), false);
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.glow_width"), false);
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.shadow_threshold"), true);
enabledState.finish_look.beauty.soften_shadows = 0;
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.shadow_threshold"), false);
enabledState.finish_look.beauty.glow_brightness = 0.1;
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.glow_threshold"), true);
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.glow_width"), true);
enabledState.remote_connected = true;
assert.equal(widget.hmbFinishLookFieldEnabled(enabledState, "beauty.glow_width"), false);

const legacy = {
  schema_version: 1, language: "en", remote_connected: false,
  catalog: { negative: ["Legacy stock"], print: ["Legacy print"], reversal: [] },
  finish_look: {
    schema_version: 1,
    beauty: { ...expectedBeauty, brightness: 1.234, enabled: false },
    film: { enabled: true, negative_film: "Legacy stock", scale_cc: 1, output_gamma: 3 },
  },
};
function assertBeautyOnly(value) {
  assert.equal(value.schema_version, 1, "Outer transport remains schema 1.");
  assert.deepEqual(Object.keys(value.finish_look), ["schema_version", "beauty"]);
  assert.equal(value.finish_look.schema_version, 2);
  assert.equal("catalog" in value, false);
  assert.equal("film" in value, false);
  assert.equal("film" in value.finish_look, false);
}
for (const input of [legacy, JSON.stringify(legacy), { value: legacy },
  { parameterValue: JSON.stringify(legacy) }, { defaultValue: legacy },
  { catalog: legacy.catalog, value: { language: "en", finish_look: legacy.finish_look } }]) {
  const normalized = widget.hmbFinishLookPublication(input);
  assertBeautyOnly(normalized);
  assert.equal(normalized.language, "en");
  assert.deepEqual(normalized.finish_look.beauty, legacy.finish_look.beauty);
  const restored = widget.hmbFinishLookPublication(JSON.parse(JSON.stringify(normalized)));
  assert.deepEqual(restored, normalized, "Save/reload cannot resurrect Film.");
  for (const language of ["en", "ko"]) {
    const markup = widget.hmbRenderFinishLookWidget({ ...input, value: { ...legacy, language } });
    assert.doesNotMatch(markup, /data-finish-section="film"|data-enable="film"|data-stock-|Legacy stock|필터 적용|FILTER APPLICATION/);
    assert.equal((markup.match(/data-finish-step="beauty\./g) || []).length, 11);
  }
}
assert.equal(widget.hmbFinishLookStepValue("film.output_gamma", 0), null);
assert.equal(widget.hmbValidateFinishLookNumber("film.output_gamma", 2.2).ok, false);
assert.equal(widget.hmbNormalizeFilmStockCatalog, undefined);
assert.equal(widget.HMB_FILM_STOCK_CATALOG_FALLBACK, undefined);
assert.doesNotMatch(source, /hmbStockDropdown|installStockDropdowns|exposureSteps|printerSteps|hmb-finish-look__stock|hmb-finish-look__printer/);

// Execute the real retained widget handler with stale pre-removal DOM controls.
// A delayed Film event must be harmless; normal Beauty/Language events retain
// existing publication, remote-lock and controller cleanup semantics.
function element(attributes = {}) {
  const listeners = new Map();
  return {
    disabled: false, checked: true, value: "", textContent: "", innerHTML: "",
    attributes: { ...attributes },
    classList: { add() {}, remove() {}, contains() { return false; } },
    getAttribute(name) { return this.attributes[name] ?? null; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(name, fn) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(fn);
    },
    removeEventListener(name, fn) { listeners.get(name)?.delete(fn); },
    fire(name) { for (const fn of [...(listeners.get(name) || [])]) fn({ target: this, key: "", stopPropagation() {} }); },
    listenerCount(name) { return listeners.get(name)?.size || 0; },
    querySelector() { return null; }, querySelectorAll() { return []; },
  };
}
const root = element();
const beautyToggle = element({ "data-enable": "beauty" });
const filmToggle = element({ "data-enable": "film" });
const unsafeToggle = element({ "data-enable": "__proto__" });
const beautySlider = element({ "data-finish-step": "beauty.brightness" });
const filmSlider = element({ "data-finish-step": "film.output_gamma" });
const glowSlider = element({ "data-finish-step": "beauty.glow_brightness" });
const glowThreshold = element({ "data-finish-step": "beauty.glow_threshold" });
const glowWidth = element({ "data-finish-step": "beauty.glow_width" });
const softenSlider = element({ "data-finish-step": "beauty.soften_shadows" });
const shadowThreshold = element({ "data-finish-step": "beauty.shadow_threshold" });
const language = element();
const status = element();
const output = element();
const ownerWindow = element();
const container = element();
container.ownerDocument = { defaultView: ownerWindow };
container.querySelector = selector => ({
  ".hmb-finish-look": root, "[data-language-toggle]": language,
  "[data-status]": status, '[data-step-label="beauty.brightness"]': output,
})[selector] || null;
container.querySelectorAll = selector => selector === "[data-enable]"
  ? [beautyToggle, filmToggle, unsafeToggle]
  : selector === "[data-finish-step]"
    ? [beautySlider, filmSlider, glowSlider, glowThreshold, glowWidth, softenSlider, shadowThreshold] : [];
const publications = [];
const onChange = value => publications.push(value);
const controller = widget.default(container, { value: legacy, onChange });
filmToggle.fire("change");
unsafeToggle.fire("change");
filmSlider.value = "3";
filmSlider.fire("input");
filmSlider.fire("change");
assert.equal(publications.length, 0, "Stale Film controls cannot publish or mutate state.");
assert.equal(filmSlider.listenerCount("change"), 0);

beautyToggle.checked = true;
beautyToggle.fire("change");
assert.equal(publications.length, 1);
assertBeautyOnly(publications.at(-1));
assert.equal(publications.at(-1).finish_look.beauty.enabled, true);
beautySlider.value = "3";
beautySlider.fire("input");
assert.equal(publications.length, 1, "Dragging remains local-only.");
beautySlider.fire("change");
assert.equal(publications.length, 2);
assert.equal(publications.at(-1).finish_look.beauty.brightness, 1.2);
assertBeautyOnly(publications.at(-1));
language.fire("click");
assert.equal(publications.at(-1).language, "ko");
assertBeautyOnly(publications.at(-1));

const beforeInactiveDrag = publications.length;
glowThreshold.value = "3";
glowThreshold.fire("change");
assert.equal(publications.length, beforeInactiveDrag, "Inactive dependent controls ignore stale events.");
glowSlider.value = "2";
glowSlider.fire("change");
assert.equal(publications.length, beforeInactiveDrag + 1);
assert.equal(glowThreshold.disabled, false, "Glow activates its dependent controls without remounting.");
assert.equal(glowWidth.disabled, false);
glowSlider.value = "0";
glowSlider.fire("change");
assert.equal(glowThreshold.disabled, true);
assert.equal(glowWidth.disabled, true);
softenSlider.value = "2";
softenSlider.fire("change");
assert.equal(shadowThreshold.disabled, true, "Neutral Soften Shadows disables its threshold.");
softenSlider.value = "1";
softenSlider.fire("change");
assert.equal(shadowThreshold.disabled, false, "Negative nonzero shadow adjustment also uses its threshold.");
assertBeautyOnly(publications.at(-1));

const locked = { ...publications.at(-1), remote_connected: true };
controller.update({ value: locked, onChange });
const countBeforeLock = publications.length;
beautyToggle.fire("change");
beautySlider.value = "4";
beautySlider.fire("change");
filmToggle.fire("change");
assert.equal(publications.length, countBeforeLock, "Remote locks authoring, including stale events.");
language.fire("click");
assert.equal(publications.length, countBeforeLock + 1, "Language remains independent of remote authoring lock.");
assertBeautyOnly(publications.at(-1));
controller.cleanup();
beautyToggle.fire("change");
assert.equal(publications.length, countBeforeLock + 1);
assert.equal(container.innerHTML, "");
console.log("Finish Look beauty-only migration/UI regression: PASS (11 controls, 62 unchanged stops, default OFF, dependencies, stale Film events, remote/lifecycle)");
