import assert from "node:assert/strict";
import * as widget from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const make = () => {
  const handlers = new Map(), frames = [], values = [];
  const inside = {};
  const container = {
    dataset: {}, contains: (target) => target === inside,
    querySelector: () => null, querySelectorAll: () => [],
    __hmbPromptLibraryScheduleFrame: (callback) => frames.push(callback),
    ownerDocument: {
      addEventListener(type, handler, capture) { assert.equal(capture, true); handlers.set(type, handler); },
      removeEventListener(type, handler, capture) { assert.equal(capture, true); assert.equal(handlers.get(type), handler); handlers.delete(type); },
    },
  };
  const props = { onChange: (value) => values.push(JSON.parse(value)) };
  const context = { props, state: widget.normalizeState({}) };
  const stop = widget.hmbInstallPromptExternalCommitBoundary(container, () => context);
  const fire = (event) => handlers.get(event.type)?.({
    preventDefault() { throw new Error("Must not hijack host Run"); },
    stopPropagation() { throw new Error("Must not block other libraries"); },
    ...event,
  });
  const clear = () => {
    stop(); widget.hmbClearPromptInteractionCommit(container);
    widget.hmbInvalidatePromptPublication(container);
    clearTimeout(container.__hmbPromptPendingLocalTimer);
    delete container.__hmbPromptPendingLocalValues;
  };
  return { container, props, context, values, frames, inside, fire, handlers, clear };
};

const burst = make();
let canonicalReads = 0;
for (let i = 0; i < 50; i++) {
  const state = { text: { SCENE_CONTEXT: `Latest ${i}` } };
  Object.defineProperty(state, "images", { get() { canonicalReads++; return []; } });
  widget.hmbSchedulePromptInteractionCommit(burst.container, burst.props, state);
}
assert.equal(canonicalReads, 0, "Intermediate edits must not normalize/serialize the entire state.");
assert.equal(burst.values.length, 0, "Interaction must finish before host publication.");
burst.fire({ type: "click", target: burst.inside });
assert.equal(burst.values.length, 0, "Interior edits keep their paint-first batch.");
burst.fire({ type: "click", target: {} });
assert.equal(burst.values.length, 1, "External Run capture must drain before the host handler.");
assert.equal(burst.values[0].text.SCENE_CONTEXT, "Latest 49");
while (burst.frames.length) burst.frames.shift()();
await delay(150);
assert.equal(burst.values.length, 1, "Old RAF/fallback callbacks cannot duplicate a Run flush.");
burst.clear();
assert.equal(burst.handlers.size, 0, "Unmount must remove all external listeners.");

const hidden = make();
widget.hmbSchedulePromptInteractionCommit(hidden.container, hidden.props, { text: { SCENE_CONTEXT: "Hidden latest" } });
await delay(160); // Simulated suspended RAF: never drain its frame callbacks.
assert.equal(hidden.values.length, 1);
assert.equal(hidden.values[0].text.SCENE_CONTEXT, "Hidden latest");
hidden.clear();

const text = make();
text.context.state.text.SCENE_CONTEXT = "Typed immediately before Run";
widget.hmbScheduleImmediateStateCommit(text.container, text.props, text.context.state);
text.fire({ type: "keydown", key: "Enter", ctrlKey: true, target: text.inside });
assert.equal(text.values.length, 1);
assert.equal(text.values[0].text.SCENE_CONTEXT, "Typed immediately before Run");
await delay(290);
assert.equal(text.values.length, 1);
text.context.state.text.SCENE_CONTEXT = "IME final";
text.container.__hmbPromptLibraryCompositionActive = true;
widget.hmbScheduleImmediateStateCommit(text.container, text.props, text.context.state);
text.fire({ type: "click", target: {} });
assert.equal(text.values.length, 1, "Incomplete composition must never be forced through.");
text.container.__hmbPromptLibraryCompositionActive = false;
text.fire({ type: "keydown", key: "Enter", metaKey: true });
assert.equal(text.values.length, 2);
text.clear();

const deleted = make();
widget.hmbSchedulePromptInteractionCommit(deleted.container, deleted.props, { text: { SCENE_CONTEXT: "Deleted draft" } });
deleted.clear();
await delay(150);
assert.equal(deleted.values.length, 0, "Deletion must cancel, not publish a disposed draft.");
console.log("PASS: Prompt 50-edit coalescing, suspended RAF, Run capture, IME and cleanup.");
