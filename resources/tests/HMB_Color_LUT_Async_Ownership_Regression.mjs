// Exercise the production controller, not a copied rejection-handler model.
// No browser, media, network or provider is needed for deterministic promise races.
import assert from "node:assert/strict";
import mount, {
  hmbColorLUTState,
  HMB_COLOR_LUT_COMMAND_FIELD,
} from "../../widgets/HMBColorLUTLibraryWidget.js";

const catalog = {
  schema: "hmb-shot-routing-catalog", version: 1,
  publisher_instance_uuid: "async-owner-publisher", channel_uuid: "async-owner-channel",
  generation: 1, metadata_sha256: "a".repeat(64),
  shots: [1, 2].map((number) => ({
    shot_uuid: `async-shot-${number}`, number, name: `Async Shot ${number}`, revision: 1,
  })),
};
function state(overrides = {}) {
  return hmbColorLUTState({
    revision: 10, language: "en", project_id: "async-project-A",
    project: { name: "Async Project A" }, shot_catalog: catalog,
    shot: { channel_uuid: catalog.channel_uuid, shot_uuid: "async-shot-1" },
    settings: { precision_version: 2, enabled: true, exposure: 0 },
    status: { phase: "idle", message: "Original context ready" }, ...overrides,
  });
}
class Element {
  constructor(tag = "div", attributes = "") {
    this.tag = tag; this.attrs = new Map(); this.listeners = new Map();
    this.children = []; this.options = []; this.value = ""; this.textContent = "";
    this.style = { setProperty() {} }; this.classList = { add() {}, remove() {} };
    for (const match of attributes.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) {
      this.attrs.set(match[1], match[2] ?? "");
    }
    this.value = this.attrs.get("value") || "";
    this.checked = this.attrs.has("checked"); this.hidden = this.attrs.has("hidden");
    this.disabled = this.attrs.has("disabled");
  }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  getAttribute(name) { return this.attrs.get(name) ?? null; }
  removeAttribute(name) { this.attrs.delete(name); }
  addEventListener(name, handler) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(handler);
  }
  removeEventListener(name, handler) { this.listeners.get(name)?.delete(handler); }
  dispatch(name) {
    for (const handler of [...(this.listeners.get(name) || [])]) handler({ type: name, target: this });
  }
  closest() { return null; }
}
function matches(element, selector) {
  if (selector.startsWith(".")) return (element.attrs.get("class") || "").split(" ").includes(selector.slice(1));
  const match = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
  return Boolean(match && element.attrs.has(match[1]) && (match[2] === undefined || element.attrs.get(match[1]) === match[2]));
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const settle = async () => { for (let tick = 0; tick < 4; tick++) await Promise.resolve(); };

function harness(kind = "publication", initial = state()) {
  let nextTask = 0;
  const frames = new Map(), timers = new Map(), requests = [];
  const document = new Element("document");
  document.hidden = false;
  document.defaultView = {
    requestAnimationFrame(callback) { frames.set(++nextTask, callback); return nextTask; },
    cancelAnimationFrame(id) { frames.delete(id); },
    setTimeout(callback) { timers.set(++nextTask, callback); return nextTask; },
    clearTimeout(id) { timers.delete(id); },
  };
  document.createElement = () => { throw new Error("This regression must not create a decoder or media source."); };
  const container = new Element();
  container.ownerDocument = document; container.mounts = 0;
  Object.defineProperty(container, "innerHTML", {
    get() { return this.markup || ""; },
    set(markup) {
      this.markup = markup; this.mounts += 1; this.children = [];
      for (const match of markup.matchAll(/<(\w+)([^>]*?)>/g)) {
        if (match[1] === "style") continue;
        const element = new Element(match[1], match[2]);
        if (element.tag === "canvas") element.getContext = () => null;
        this.children.push(element);
      }
    },
  });
  container.querySelectorAll = (selector) => container.children.filter((element) => matches(element, selector));
  container.querySelector = (selector) => container.querySelectorAll(selector)[0] || null;
  const q = (selector) => container.querySelector(selector);
  const props = (value) => ({
    value,
    onChange(captured) {
      const wait = deferred();
      requests.push({ ...wait, captured, command: captured[HMB_COLOR_LUT_COMMAND_FIELD] || null });
      return wait.promise;
    },
    ...(kind === "command" ? { onCommand(serialized) {
      const wait = deferred(), command = JSON.parse(serialized);
      requests.push({ ...wait, captured: command.state, command }); return wait.promise;
    } } : {}),
  });
  const controller = mount(container, props(initial));
  const input = (step, commit = false) => {
    const slider = q('[data-adjust="exposure"]'); slider.value = String(step);
    slider.dispatch("input"); if (commit) slider.dispatch("change");
  };
  const issue = () => {
    const before = requests.length;
    if (kind === "publication") input(4, true);
    else q('[data-action="save_profile"]').dispatch("click");
    assert.equal(requests.length, before + 1, "Each input release/command must capture one request.");
    const request = requests.at(-1);
    assert.equal(Boolean(request.command), kind !== "publication");
    if (request.command) {
      assert.equal(request.command.action, "save_profile");
      assert.equal(request.command.state.project_id, request.captured.project_id);
    }
    return request;
  };
  const snapshot = () => ({
    status: q("[data-status]").textContent, exposure: q('[data-adjust="exposure"]').value,
    project: q("[data-project]").value,
    shot: q("[data-shot-selector]").value,
    shotNumber: q("[data-shot-number]").getAttribute("data-shot-number"),
    mounts: container.mounts,
  });
  return { kind, controller, container, document, q, props, requests, frames, timers, input, issue, snapshot,
    update(incoming) { controller.update(props(incoming)); },
    flushCommit() {
      const callbacks = [...timers.values()]; timers.clear();
      for (const callback of callbacks) callback();
    },
  };
}

const passed = [];
async function check(name, test) { await test(); passed.push(name); console.log(`PASS ${name}`); }
async function obsoleteMustNotChange(ui, old, label) {
  const expected = ui.snapshot();
  old.reject(new Error(label)); await settle();
  assert.deepEqual(ui.snapshot(), expected, "An obsolete rejection must not change status, settings, context or DOM ownership.");
  assert.ok(!ui.snapshot().status.includes(label));
}

for (const kind of ["publication", "command", "command-fallback"]) {
  await check(`${kind}: newer committed edit owns status`, async () => {
    const ui = harness(kind), old = ui.issue();
    ui.input(8, true); ui.requests.at(-1).resolve(); await settle();
    assert.equal(ui.snapshot().exposure, "8");
    assert.equal(old.captured.settings.exposure, kind === "publication" ? 1 : 0, "Captured requests remain immutable after later edits.");
    await obsoleteMustNotChange(ui, old, "obsolete after newer committed edit"); ui.controller.cleanup();
  });
  await check(`${kind}: pending input invalidates old owner before publication`, async () => {
    const ui = harness(kind), old = ui.issue(), count = ui.requests.length;
    ui.input(9); assert.equal(ui.requests.length, count); assert.equal(ui.timers.size, 1);
    await obsoleteMustNotChange(ui, old, "obsolete while edit is still unpublished");
    assert.equal(ui.snapshot().exposure, "9");
    ui.flushCommit(); assert.equal(ui.requests.length, count + 1);
    assert.equal(ui.requests.at(-1).captured.settings.exposure, 2.25); ui.controller.cleanup();
  });
  for (const [name, replacement] of [
    ["same context higher revision", state({ revision: 100, settings: { precision_version: 2, enabled: true, exposure: 0.25 }, status: { phase: "idle", message: "Accepted same-context state" } })],
    ["Project and Shot", state({ revision: 100, project_id: "async-project-B", project: { name: "Async Project B" }, shot: { channel_uuid: catalog.channel_uuid, shot_uuid: "async-shot-2" }, status: { phase: "idle", message: "Accepted Project B / Shot 2" } })],
    ["Project only", state({ revision: 100, project_id: "async-project-B", project: { name: "Async Project B" }, status: { phase: "idle", message: "Accepted Project B / same Shot" } })],
    ["Shot only", state({ revision: 100, shot: { channel_uuid: catalog.channel_uuid, shot_uuid: "async-shot-2" }, status: { phase: "idle", message: "Accepted Shot 2 / same Project" } })],
  ]) {
    await check(`${kind}: accepted ${name} supersedes rejection`, async () => {
      const ui = harness(kind), old = ui.issue(); ui.update(replacement);
      assert.equal(ui.snapshot().status, replacement.status.message);
      assert.equal(ui.snapshot().project, replacement.project_id);
      assert.equal(ui.snapshot().shotNumber, String(replacement.shot.number));
      await obsoleteMustNotChange(ui, old, `obsolete after accepted ${name}`); ui.controller.cleanup();
    });
  }
  await check(`${kind}: equal revision authoritative status supersedes rejection`, async () => {
    const ui = harness(kind), old = ui.issue();
    const incoming = state({ ...old.captured, status: { phase: "idle", message: "Accepted host result at captured revision" } });
    ui.update(incoming); assert.equal(ui.snapshot().status, incoming.status.message);
    await obsoleteMustNotChange(ui, old, "obsolete equal-revision response"); ui.controller.cleanup();
  });
  await check(`${kind}: accepted context ABA cannot resurrect old owner`, async () => {
    const ui = harness(kind), old = ui.issue();
    ui.update(state({ revision: 100, project_id: "async-project-B", shot: { channel_uuid: catalog.channel_uuid, shot_uuid: "async-shot-2" } }));
    ui.update(state({ revision: 200, status: { phase: "idle", message: "Returned to A / Shot 1 authoritatively" } }));
    assert.equal(ui.snapshot().project, "async-project-A"); assert.equal(ui.snapshot().shotNumber, "1");
    await obsoleteMustNotChange(ui, old, "obsolete ABA context rejection"); ui.controller.cleanup();
  });
  await check(`${kind}: accepted host progress during pending edit supersedes old error`, async () => {
    const ui = harness(kind), old = ui.issue(); ui.input(10);
    ui.update(state({ revision: 100, status: { phase: "working", message: "Current host progress during drag", progress: 0.5 } }));
    assert.equal(ui.snapshot().exposure, "10"); assert.equal(ui.snapshot().status, "Current host progress during drag");
    await obsoleteMustNotChange(ui, old, "obsolete before pending edit commits"); ui.controller.cleanup();
  });
  await check(`${kind}: newer command owns pending/error status`, async () => {
    const ui = harness(kind), old = ui.issue();
    ui.q('[data-action="save_profile"]').dispatch("click");
    const newer = ui.requests.at(-1); assert.notEqual(newer, old); assert.ok(newer.command);
    newer.reject(new Error("current newer command failed")); await settle();
    assert.match(ui.snapshot().status, /current newer command failed/);
    await obsoleteMustNotChange(ui, old, "obsolete before newer command"); ui.controller.cleanup();
  });
  await check(`${kind}: local Shot ABA remains current through old error`, async () => {
    const ui = harness(kind), old = ui.issue();
    for (const number of [2, 1]) {
      ui.q("[data-shot-selector]").value = `${catalog.channel_uuid}\u001fasync-shot-${number}`;
      ui.q("[data-shot-selector]").dispatch("change");
    }
    assert.equal(ui.snapshot().shotNumber, "1");
    await obsoleteMustNotChange(ui, old, "obsolete local Shot ABA rejection"); ui.controller.cleanup();
  });
  await check(`${kind}: stale update cannot suppress current request failure`, async () => {
    const ui = harness(kind), current = ui.issue();
    ui.update(state({ revision: 0, status: { phase: "idle", message: "" } }));
    current.reject(new Error(`current ${kind} failure after ignored stale update`)); await settle();
    assert.match(ui.snapshot().status, /failure after ignored stale update/);
    assert.equal(ui.snapshot().exposure, kind === "publication" ? "4" : "0"); ui.controller.cleanup();
  });
  await check(`${kind}: current errors are visible in both languages`, async () => {
    for (const language of ["ko", "en"]) {
      const ui = harness(kind, state({ language })), current = ui.issue();
      current.reject(new Error(`current ${language} transport failure`)); await settle();
      assert.match(ui.snapshot().status, new RegExp(`current ${language} transport failure`));
      ui.controller.cleanup();
    }
  });
  await check(`${kind}: cleanup cancels tasks/listeners and ignores late rejection`, async () => {
    const ui = harness(kind), old = ui.issue(); ui.input(7);
    const before = ui.requests.length; ui.controller.cleanup();
    assert.equal(ui.requests.length, before + 1, "Cleanup preserves the final authored pending value.");
    assert.equal(ui.requests.at(-1).captured.settings.exposure, 1.75);
    assert.equal(ui.container.innerHTML, ""); assert.equal(ui.container.__hmbColorLUTController, undefined);
    assert.equal(ui.frames.size, 0); assert.equal(ui.timers.size, 0);
    assert.equal([...ui.document.listeners.values()].reduce((sum, handlers) => sum + handlers.size, 0), 0);
    old.reject(new Error("obsolete after cleanup")); ui.requests.at(-1).reject(new Error("cleanup commit failure"));
    await settle(); assert.equal(ui.container.innerHTML, "");
    ui.controller.cleanup(); assert.equal(ui.requests.length, before + 1, "Cleanup is idempotent.");
  });
}

for (const kind of ["publication", "command", "command-fallback"]) {
  await check(`${kind}: synchronous accepted callback result is not overwritten by pending`, async () => {
    const ui = harness(kind), accepted = state({ revision: 100, status: { phase: "idle", message: "Reentrant callback accepted current context" } });
    const reentrant = () => { ui.update(accepted); return Promise.resolve(); };
    ui.controller.update({ value: state(), onChange: reentrant, ...(kind === "command" ? { onCommand: reentrant } : {}) });
    if (kind === "publication") ui.input(4, true); else ui.q('[data-action="save_profile"]').dispatch("click");
    await settle(); assert.equal(ui.snapshot().status, accepted.status.message); ui.controller.cleanup();
  });
  await check(`${kind}: synchronous current exception remains visible`, async () => {
    const ui = harness(kind);
    const onFailure = () => { throw new Error(`current synchronous ${kind} failure`); };
    ui.controller.update({ value: state(), onChange: onFailure, ...(kind === "command" ? { onCommand: onFailure } : {}) });
    if (kind === "publication") ui.input(4, true); else ui.q('[data-action="save_profile"]').dispatch("click");
    assert.match(ui.snapshot().status, new RegExp(`current synchronous ${kind} failure`)); ui.controller.cleanup();
  });
  await check(`${kind}: synchronous reentrant authoritative update owns status`, async () => {
    const ui = harness(kind), accepted = state({ revision: 100, status: { phase: "idle", message: "Reentrant accepted host state" } });
    const reentrant = () => { ui.update(accepted); throw new Error(`obsolete synchronous ${kind} failure`); };
    ui.controller.update({ value: state(), onChange: reentrant, ...(kind === "command" ? { onCommand: reentrant } : {}) });
    if (kind === "publication") ui.input(4, true); else ui.q('[data-action="save_profile"]').dispatch("click");
    assert.equal(ui.snapshot().status, accepted.status.message); ui.controller.cleanup();
  });
}

await check("current Shot-selection rejection clears only its own pending navigation", async () => {
  const ui = harness("publication");
  ui.q("[data-shot-selector]").value = `${catalog.channel_uuid}\u001fasync-shot-2`;
  ui.q("[data-shot-selector]").dispatch("change");
  const current = ui.requests.at(-1);
  assert.equal(current.captured.shot.shot_uuid, "async-shot-2");
  current.reject(new Error("current Shot selection failure")); await settle();
  assert.match(ui.snapshot().status, /current Shot selection failure/);
  // Before rejection, this earlier Shot is in pendingShot.blockedKeys. After a
  // legitimate rejection, a current authoritative host selection must work.
  const accepted = state({ revision: 100, status: { phase: "idle", message: "Host restored Shot 1 after rejected request" } });
  ui.update(accepted); assert.equal(ui.snapshot().shotNumber, "1");
  assert.equal(ui.snapshot().status, accepted.status.message); ui.controller.cleanup();
});

console.log(JSON.stringify({ result: "PASS", cases: passed.length, production_widget: "widgets/HMBColorLUTLibraryWidget.js",
  scope: "Deterministic real-controller DOM harness; native onCommand and onChange command fallback, asynchronous/synchronous ownership, no decoder/network", tests: passed }, null, 2));
