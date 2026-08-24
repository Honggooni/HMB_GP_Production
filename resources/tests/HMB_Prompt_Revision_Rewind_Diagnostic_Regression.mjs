import assert from "node:assert/strict";

const widgetPath = new URL(
  "../../widgets/HMBPromptLibraryScopedBindingWidget.js",
  import.meta.url,
);
const prompt = await import(widgetPath);

function stateAt(sourceRevision, uiRevision, marker) {
  const state = prompt.normalizeState({
    source_sync_revision: sourceRevision,
    ui_edit_revision: uiRevision,
    text: { SCENE_CONTEXT: marker },
  });
  state.text.SCENE_CONTEXT = marker;
  return state;
}

function containerAt(state) {
  const serialized = JSON.stringify(state);
  return {
    __hmbPromptCurrentSourceSyncRevision: state.source_sync_revision,
    __hmbPromptCurrentUiEditRevision: state.ui_edit_revision,
    __hmbPromptLatestLocalUiEditRevision: state.ui_edit_revision,
    __hmbPromptCurrentDisabled: false,
    __hmbPromptLatestLocalStateValue: serialized,
    __hmbPromptLastPaintedValue: serialized,
    querySelector() { return null; },
  };
}

// 1. An exact retained-mode echo is consumed. Publishing a local UI edit may
// advance only the UI clock; it must never lower or advance the source clock.
const exactState = stateAt(129, 83, "exact-base");
const exactContainer = containerAt(exactState);
let exactPublished = "";
let exactConsumed = false;
prompt.hmbEmitLocalPromptState(
  exactContainer,
  {
    disabled: false,
    onChange(value) {
      exactPublished = value;
      exactConsumed = prompt.hmbConsumePendingPromptStateEcho(
        exactContainer,
        { value, disabled: false },
        exactState,
      );
    },
  },
  exactState,
);
const exactEcho = JSON.parse(exactPublished);
assert.equal(exactConsumed, true, "The synchronous exact echo must be consumed.");
assert.equal(exactEcho.source_sync_revision, 129);
assert.equal(exactEcho.ui_edit_revision, 84);
assert.equal(exactContainer.__hmbPromptCurrentSourceSyncRevision, 129);

// If that same exact payload is replayed after source authority reaches 132,
// the durable source watermark—not the short echo queue—must classify it as
// stale. It cannot restore 129 or schedule a crossed-source merge.
const source132 = stateAt(132, 84, "source-132");
Object.assign(exactContainer, {
  __hmbPromptCurrentSourceSyncRevision: 132,
  __hmbPromptCurrentUiEditRevision: 84,
  __hmbPromptLatestLocalUiEditRevision: 84,
  __hmbPromptLatestLocalStateValue: JSON.stringify(source132),
  __hmbPromptLastPaintedValue: JSON.stringify(source132),
});
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    exactContainer,
    { value: exactPublished, disabled: false },
    source132,
  ),
  true,
  "A delayed lower-source exact payload must be consumed as stale.",
);
assert.equal(exactContainer.__hmbPromptLastConsumedEchoWasStale, true);
assert.equal(prompt.hmbTakePromptRevisionMerge(exactContainer), null);
assert.equal(exactContainer.__hmbPromptCurrentSourceSyncRevision, 132);
if (exactContainer.__hmbPromptPendingLocalTimer) {
  clearTimeout(exactContainer.__hmbPromptPendingLocalTimer);
}

// 2. Crossed clocks merge with max(source) and max(UI). Test both directions
// around the observed 129/132 boundary; neither direction may produce 129 from
// a container whose accepted source watermark is already 132.
const crossedContainer = containerAt(source132);
const newerUiOlderSource = stateAt(129, 85, "ui-85-source-129");
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    crossedContainer,
    { value: JSON.stringify(newerUiOlderSource), disabled: false },
    source132,
  ),
  false,
);
const mergedNewUi = prompt.hmbTakePromptRevisionMerge(crossedContainer);
assert.equal(mergedNewUi.source_sync_revision, 132);
assert.equal(mergedNewUi.ui_edit_revision, 85);

Object.assign(crossedContainer, {
  __hmbPromptCurrentSourceSyncRevision: 132,
  __hmbPromptCurrentUiEditRevision: 85,
  __hmbPromptLatestLocalUiEditRevision: 85,
  __hmbPromptLatestLocalStateValue: JSON.stringify(mergedNewUi),
  __hmbPromptLastPaintedValue: JSON.stringify(mergedNewUi),
});
const newerSourceOlderUi = stateAt(133, 84, "source-133-ui-84");
assert.equal(
  prompt.hmbConsumePendingPromptStateEcho(
    crossedContainer,
    { value: JSON.stringify(newerSourceOlderUi), disabled: false },
    mergedNewUi,
  ),
  false,
);
const mergedNewSource = prompt.hmbTakePromptRevisionMerge(crossedContainer);
assert.equal(mergedNewSource.source_sync_revision, 133);
assert.equal(mergedNewSource.ui_edit_revision, 85);

// 3. Host resize feedback is coalesced and revision-neutral. It receives no
// onChange callback, and two requests in one debounce window dispatch one
// resize event without touching either writer clock.
const originalWindow = globalThis.window;
let resizeDispatches = 0;
globalThis.window = {
  dispatchEvent(event) {
    assert.equal(event.type, "resize");
    resizeDispatches += 1;
    return true;
  },
};
const resizeContainer = containerAt(mergedNewSource);
const shell = { offsetHeight: 720 };
assert.equal(prompt.hmbRequestPromptHostResize(resizeContainer, shell), true);
assert.equal(prompt.hmbRequestPromptHostResize(resizeContainer, shell), false);
await new Promise((resolve) => setTimeout(resolve, 120));
assert.equal(resizeDispatches, 1);
assert.equal(resizeContainer.__hmbPromptCurrentSourceSyncRevision, 133);
assert.equal(resizeContainer.__hmbPromptCurrentUiEditRevision, 85);
if (originalWindow === undefined) delete globalThis.window;
else globalThis.window = originalWindow;

// 4. The exact log shape is reproducible without any per-widget rollback when
// events from two independent Prompt instances are shown without node id. This
// is the current main.log format: each node is monotonic, while the flattened
// stream appears to rewind from Prompt A's 132 to Prompt B's 129.
const hostEvents = [];
for (const [nodeId, revisions] of [
  ["HMBPromptLibrary_1", [129, 130, 131, 132]],
  ["HMBPromptLibrary_2", [129, 130, 131]],
]) {
  for (const sourceRevision of revisions) {
    const state = stateAt(sourceRevision, 83, `${nodeId}:${sourceRevision}`);
    hostEvents.push({ nodeId, sourceRevision: state.source_sync_revision });
  }
}
assert.deepEqual(
  hostEvents.map((event) => event.sourceRevision),
  [129, 130, 131, 132, 129, 130, 131],
  "The observed flattened 129->132->129 sequence must be reproducible.",
);
for (const nodeId of new Set(hostEvents.map((event) => event.nodeId))) {
  const revisions = hostEvents
    .filter((event) => event.nodeId === nodeId)
    .map((event) => event.sourceRevision);
  for (let index = 1; index < revisions.length; index += 1) {
    assert.ok(
      revisions[index] >= revisions[index - 1],
      `${nodeId} must remain monotonic even when the flattened log rewinds.`,
    );
  }
}

console.log(
  "HMB Prompt revision-rewind diagnostic: PASS "
  + "(exact echo monotonic / crossed merge max clocks / resize neutral / "
  + "flattened multi-instance stream reproduces 129->132->129)",
);
