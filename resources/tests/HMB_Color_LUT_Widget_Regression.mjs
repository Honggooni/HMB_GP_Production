import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBColorLUTLibraryWidget.js", import.meta.url), "utf8");
const widget = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const defaults = widget.hmbColorLUTState();
assert.equal(defaults.settings.enabled, false);
assert.equal(defaults.language, "ko");
assert.equal(defaults.profiles.length, 0);
assert.equal(defaults.project_id, "");
assert.deepEqual(widget.hmbColorLUTSettings({ enabled: "true", exposure: 99, temperature: -9, contrast: NaN, saturation: 1.7 }), {
  enabled: false, precision_version: 2, exposure: 3, temperature: -3, contrast: 0, saturation: 1, shadows: 0, highlights: 0,
});
assert.deepEqual(widget.hmbColorLUTState({ value: JSON.stringify({ language: "en", settings: { enabled: true, exposure: 2 } }) }).settings, {
  ...defaults.settings, enabled: true, exposure: 2,
});
assert.deepEqual(widget.hmbColorLUTState({ value: "invalid" }), defaults);
assert.deepEqual(widget.hmbColorLUTShotOptions(defaults).map((s) => s.name), ["Only"]);
assert.equal(widget.hmbColorLUTShotAccent(defaults), "#64748B");
const catalog = { schema: "hmb-shot-routing-catalog", version: 1, publisher_instance_uuid: "image-publisher", channel_uuid: "channel", generation: 3, metadata_sha256: "a".repeat(64),
  shots: [1, 3, 5].map((number) => ({ shot_uuid: `shot-${number}`, number, name: `Scene ${number}`, revision: number })) };
const bound = widget.hmbColorLUTState({ shot_catalog: catalog, shot: { channel_uuid: "channel", shot_uuid: "shot-3" },
  source: { url: "https://media.invalid/three.mp4", path: "C:\\video\\three.mp4", shot_uuid: "shot-3", channel_uuid: "channel", revision: 1, fps: 24, duration: 2 } });
assert.deepEqual(widget.hmbColorLUTShotOptions(bound).map((s) => s.number), [0, 1, 3, 5]);
assert.equal(widget.hmbColorLUTShotAccent(bound), "#10B981");
assert.equal(bound.shot.name, "Scene 3");
assert.equal(widget.hmbColorLUTState({ ...bound, source: { ...bound.source, shot_uuid: "shot-1" } }).source.url, undefined, "Never grade another shot's late source.");
assert.deepEqual(widget.hmbColorLUTShotCatalog({ ...catalog, shots: [catalog.shots[0], catalog.shots[0]] }), {});
assert.equal(widget.hmbColorLUTState({ ...bound, shot_catalog: { ...catalog, channel_uuid: "other" } }).shot.name, "Only");

// Domain parity: the preview cube has red-fastest .cube order and uses the same
// trilinear interpolation as FFmpeg, including clipped, non-linear cells.
const identity = widget.hmbColorLUTCube(defaults.settings);
assert.equal(identity.length, 33 ** 3 * 3);
assert.deepEqual(Array.from(identity.slice(3, 6)), [1 / 32, 0, 0]);
assert.deepEqual(Array.from(identity.slice(33 * 3, 33 * 3 + 3)), [0, 1 / 32, 0]);
assert.deepEqual(Array.from(identity.slice(33 * 33 * 3, 33 * 33 * 3 + 3)), [0, 0, 1 / 32]);
const near = (actual, expected, tolerance = 1e-6) => actual.forEach((v, i) => assert.ok(Math.abs(v - expected[i]) < tolerance, `${actual} != ${expected}`));
near(widget.hmbColorLUTSample(identity, [0.1831, 0.7722, 0.935]), [0.1831, 0.7722, 0.935]);
near(widget.hmbColorLUTTransform([0.25, 0.5, 0.75], { ...defaults.settings, enabled: true, temperature: 1 }), [0.25 + 7 / 255, 0.5, 0.75 - 7 / 255]);
near(widget.hmbColorLUTTransform([0.25, 0.5, 0.75], { enabled: true, exposure: 1 }), [0.25, 0.5, 0.75].map((v) => v * 2 ** 0.22));
assert.equal(widget.HMB_COLOR_LUT_MAX_STEP, 12);
for (const key of widget.HMB_COLOR_LUT_CONTROLS) {
  const colors = new Set();
  for (let step = -12; step <= 12; step++) {
    const strength = widget.hmbColorLUTStrengthFromStep(step);
    assert.equal(strength, step / 4);
    const settings = {...defaults.settings, enabled:true, [key]:strength};
    assert.deepEqual(widget.hmbColorLUTSettings(settings), settings, 'Quarter strengths survive normalization.');
    colors.add(JSON.stringify(widget.hmbColorLUTTransform([.2,.4,.6], settings)));
    if (step % 4 === 0) near(widget.hmbColorLUTTransform([.2,.4,.6], settings), widget.hmbColorLUTTransform([.2,.4,.6], {enabled:true,[key]:step/4}));
  }
  assert.equal(colors.size, 25, `${key}: every control position must affect pixels distinctly.`);
}
assert.deepEqual(widget.hmbColorLUTTransform([0.2, 0.5, 0.8], { ...defaults.settings, exposure: 3 }), [0.2, 0.5, 0.8]);
const grade = { enabled: true, exposure: 1, temperature: -2, contrast: 2, saturation: 1, shadows: 2, highlights: -1 };
const cube = widget.hmbColorLUTCube(grade);
for (const [r, g, b] of [[0, 0, 0], [7, 12, 20], [32, 32, 32]]) {
  const offset = ((b * 33 + g) * 33 + r) * 3;
  near(Array.from(cube.slice(offset, offset + 3)), widget.hmbColorLUTTransform([r / 32, g / 32, b / 32], grade));
}
const midpoint = [7.5 / 32, 12.5 / 32, 20.5 / 32], mean = [0, 0, 0];
for (const z of [20, 21]) for (const y of [12, 13]) for (const x of [7, 8]) for (let c = 0; c < 3; c++) mean[c] += cube[((z * 33 + y) * 33 + x) * 3 + c] / 8;
near(widget.hmbColorLUTSample(cube, midpoint), mean);
assert.throws(() => widget.hmbColorLUTCube({}, 0));
const commandState = widget.hmbColorLUTState({ ...bound, settings: grade });
const command = widget.hmbColorLUTCommand("export", commandState, "captured-export-1");
commandState.settings.exposure = -3;
assert.equal(command.state.settings.exposure, 1, "Export owns an immutable snapshot, not a later slider value.");
assert.equal(command.id, "captured-export-1");
assert.throws(() => widget.hmbColorLUTCommand("generate", defaults));

for (const language of ["ko", "en"]) {
  const html = widget.hmbRenderColorLUTWidget({ ...bound, language });
  assert.match(html, /HMB Color LUT/);
  assert.match(html, /Pretendard Variable/);
  assert.match(html, /data-preview/);
  assert.equal((html.match(/data-adjust=/g) || []).length, 6);
  assert.equal((html.match(/min="-12" max="12" step="1"/g) || []).length, 6);
  assert.match(html, /data-manual-output/);
  assert.match(html, /value="hevc10"/); assert.match(html, /value="prores"/); assert.match(html, /value="ffv1"/);
  assert.match(html, language === "ko" ? /프리셋 저장/ : /Save preset/);
  assert.doesNotMatch(html, /data-action="export_lut"|data-wipe type=|class="cl-compare"/);
  assert.match(html, /data-wipe-handle role="slider"/);
  assert.match(html, /data-project disabled/);
  assert.match(html, language === "ko" ? /출력 경로 직접 지정/ : /Set output path/);
  assert.doesNotMatch(html, /data-action="(?:generate|render)"|sample|시연|filter:\s*(?:brightness|contrast|saturate)/i);
}
assert.doesNotMatch(widget.hmbRenderColorLUTWidget({ ...bound, profiles: [{ id: "project-1", name: '<img src=x onerror="alert(1)">' }] }), /<img src=x/);
assert.match(widget.HMB_COLOR_LUT_FRAGMENT_SHADER, /texelFetch\(colorCube/);
assert.doesNotMatch(widget.HMB_COLOR_LUT_FRAGMENT_SHADER, /pow\(/, "Shader must sample the exported cube instead of a different analytic transform.");

// Small DOM/media harness exercises lifecycle ownership without a browser or an
// installed DOM package. Elements are taken from the actual production markup.
class Element {
  constructor(tag = "div", attrs = "") {
    this.tag = tag; this.attrs = new Map(); this.listeners = new Map(); this.value = ""; this.hidden = false; this.disabled = false; this.children = []; this.options = [];
    this.style = { setProperty() {} }; this.classList = { add() {}, remove() {} }; this._html = "";
    for (const match of attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) this.attrs.set(match[1], match[2] ?? "");
    this.value = this.attrs.get("value") || ""; this.hidden = this.attrs.has("hidden"); this.disabled = this.attrs.has("disabled"); this.checked = this.attrs.has("checked");
  }
  setAttribute(k, v) { this.attrs.set(k, String(v)); }
  getAttribute(k) { return this.attrs.get(k) ?? null; }
  removeAttribute(k) { this.attrs.delete(k); }
  addEventListener(k, fn) { if (!this.listeners.has(k)) this.listeners.set(k, new Set()); this.listeners.get(k).add(fn); }
  removeEventListener(k, fn) { this.listeners.get(k)?.delete(fn); }
  dispatch(type, extra = {}) { for (const fn of [...(this.listeners.get(type) || [])]) fn({ type, target: this, ...extra }); }
  get innerHTML() { return this._html; }
  set innerHTML(value) { this._html = value; }
  closest() { return null; }
}
const matchSelector = (el, selector) => {
  if (selector[0] === ".") return (el.attrs.get("class") || "").split(" ").includes(selector.slice(1));
  const match = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
  return match && el.attrs.has(match[1]) && (match[2] === undefined || el.attrs.get(match[1]) === match[2]);
};
class Video extends Element {
  constructor() { super("video"); this.paused = true; this.readyState = 0; this.currentTime = 0; this.duration = 2; this.videoWidth = 4; this.videoHeight = 2; this.frameCallbacks = new Map(); this.nextFrame = 1; }
  load() {}
  ready() { this.readyState = 2; this.dispatch("loadedmetadata"); this.dispatch("loadeddata"); }
  play() { this.paused = false; this.dispatch("play"); return Promise.resolve(); }
  pause() { const changed = !this.paused; this.paused = true; if (changed) this.dispatch("pause"); }
  requestVideoFrameCallback(fn) { const id = this.nextFrame++; this.frameCallbacks.set(id, fn); return id; }
  cancelVideoFrameCallback(id) { this.frameCallbacks.delete(id); }
}
function harness(initial) {
  let nextTask = 1; const frames = new Map(), timers = new Map(), videos = [], publications = [], draws = [];
  const doc = new Element("document"); doc.hidden = false;
  doc.defaultView = { requestAnimationFrame(fn) { const id = nextTask++; frames.set(id, fn); return id; }, cancelAnimationFrame(id) { frames.delete(id); },
    setTimeout(fn) { const id = nextTask++; timers.set(id, fn); return id; }, clearTimeout(id) { timers.delete(id); } };
  doc.createElement = (tag) => { assert.equal(tag, "video"); const v = new Video(); videos.push(v); return v; };
  const container = new Element(); container.ownerDocument = doc; container.mounts = 0;
  Object.defineProperty(container, "innerHTML", { get() { return this._html; }, set(html) {
    this._html = html; this.mounts++; this.children = [];
    for (const match of html.matchAll(/<(\w+)([^>]*?)>/g)) {
      if (match[1] === "style") continue; const el = new Element(match[1], match[2]); this.children.push(el);
      if (el.tag === "canvas") { el.width = 4; el.height = 2; el.getContext = (kind) => kind === "webgl2" ? null : {
        clearRect() {}, drawImage(video) { draws.push(video); }, getImageData() { return { data: new Uint8ClampedArray([50, 100, 150, 255, 200, 150, 100, 255]) }; }, putImageData() {},
      }; }
    }
    const project = this.children.find((el) => el.attrs.has("data-project")); if (project) project.options = defaults.profiles.map((p) => ({ value: p.id, textContent: p.name }));
  } });
  container.querySelectorAll = (selector) => container.children.filter((el) => matchSelector(el, selector));
  container.querySelector = (selector) => container.querySelectorAll(selector)[0] || null;
  const props = (value) => ({ value, onChange(v) { publications.push(v); } });
  const controller = widget.default(container, props(initial));
  return { doc, container, controller, videos, publications, frames, timers, draws, props, q: (s) => container.querySelector(s),
    flushFrames() { const pending = [...frames.values()]; frames.clear(); pending.forEach((fn) => fn(0)); } };
}
const ui = harness(bound);
assert.equal(ui.container.mounts, 1);
assert.equal(ui.videos.length, 1);
const videoA = ui.videos[0]; videoA.ready(); ui.flushFrames(); assert.equal(ui.draws.at(-1), videoA);
const canvas = ui.q("[data-preview]");
ui.q('[data-adjust="exposure"]').value = "2"; ui.q('[data-adjust="exposure"]').dispatch("input");
ui.q('[data-adjust="exposure"]').value = "3"; ui.q('[data-adjust="exposure"]').dispatch("input");
assert.equal(ui.publications.length, 0, "Pointer ticks only update local preview."); assert.equal(ui.timers.size, 1);
ui.q('[data-adjust="exposure"]').dispatch("change");
assert.equal(ui.publications.length, 1); assert.equal(ui.publications[0].settings.exposure, .75); assert.equal(ui.publications[0].settings.enabled, true);
assert.equal(ui.timers.size, 0); assert.equal(ui.container.mounts, 1); assert.equal(ui.q("[data-preview]"), canvas);
ui.controller.update(ui.props({ ...bound, revision: 0 }));
assert.equal(ui.q('[data-adjust="exposure"]').value, "3", "Old host echo cannot undo a committed drag.");
assert.equal(ui.videos.length, 1, "State updates must not reopen the decoder.");
ui.q('[data-action="export"]').dispatch("click");
assert.equal(ui.publications.at(-1).__hmb_color_lut_command__.state.settings.exposure, .75);
assert.equal(ui.publications.at(-1).__hmb_color_lut_command__.action, "export");
assert.equal(ui.q("[data-preview]"), canvas);
ui.q("[data-play]").dispatch("click"); assert.equal(videoA.paused, false); assert.equal(videoA.frameCallbacks.size, 1);
ui.q("[data-play]").dispatch("click"); assert.equal(videoA.paused, true); assert.equal(videoA.frameCallbacks.size, 0);
ui.q("[data-seek]").value = "12"; ui.q("[data-seek]").dispatch("input"); assert.equal(videoA.currentTime, 0.5);
ui.q("[data-step]").dispatch("click"); assert.equal(videoA.currentTime, 13 / 24);
ui.q("[data-language-toggle]").dispatch("click"); assert.equal(ui.q("[data-language-toggle]").textContent, "EN"); assert.equal(ui.container.mounts, 1);
const staleReady = [...videoA.listeners.get("loadeddata")][0];
ui.controller.update(ui.props({ ...bound, revision: 100, source: { ...bound.source, revision: "new", url: "https://media.invalid/new.mp4" } }));
assert.equal(ui.videos.length, 2); assert.equal(ui.q("[data-empty]").hidden, false);
staleReady(); assert.equal(ui.q("[data-empty]").hidden, false, "Late prior-source loadeddata cannot reveal a stale frame.");
const videoB = ui.videos[1]; videoB.ready(); ui.flushFrames(); assert.equal(ui.draws.at(-1), videoB);
ui.q("[data-play]").dispatch("click"); ui.doc.hidden = true; ui.doc.dispatch("visibilitychange");
assert.equal(videoB.paused, true); assert.equal(videoB.frameCallbacks.size, 0); assert.equal(ui.frames.size, 0);
ui.doc.hidden = false; ui.doc.dispatch("visibilitychange"); ui.flushFrames();
ui.q("[data-shot-selector]").value = "channel\u001fshot-5"; ui.q("[data-shot-selector]").dispatch("change");
assert.equal(ui.publications.at(-1).shot.shot_uuid, "shot-5"); assert.equal(ui.q("[data-empty]").hidden, false);
assert.equal(ui.container.mounts, 1);
assert.equal(widget.default(ui.container, ui.props(ui.publications.at(-1))), ui.controller, "Host repeated mount must reuse the controller.");
ui.controller.cleanup(); assert.equal(ui.frames.size, 0); assert.equal(ui.timers.size, 0); assert.equal(ui.container.__hmbColorLUTController, undefined);
const legacyUI = harness({...bound, settings:{enabled:true,exposure:1,contrast:-2,temperature:3}});
assert.equal(legacyUI.q('[data-adjust="exposure"]').value, '4');
assert.equal(legacyUI.q('[data-adjust="contrast"]').value, '-8');
assert.equal(legacyUI.q('[data-adjust="temperature"]').value, '12');
legacyUI.q('[data-action="export"]').dispatch('click');
assert.equal(legacyUI.publications.at(-1).__hmb_color_lut_command__.state.settings.exposure, 1);
legacyUI.q('[data-adjust="exposure"]').value = '5'; legacyUI.q('[data-adjust="exposure"]').dispatch('input');
legacyUI.q('[data-action="export"]').dispatch('click');
const fineCapture = legacyUI.publications.at(-1).__hmb_color_lut_command__.state.settings;
assert.equal(fineCapture.exposure, 1.25); assert.equal(fineCapture.contrast, -2);
assert.equal(fineCapture.precision_version, 2);
legacyUI.controller.cleanup();
await Promise.resolve();
console.log("HMB Color LUT widget regression: PASS (LUT parity, commands, localization, persistent DOM, media ownership, playback cleanup)");
