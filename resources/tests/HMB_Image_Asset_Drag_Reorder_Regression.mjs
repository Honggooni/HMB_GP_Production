import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);


for (const helper of [
  "hmbReorderImageAssetShotSource",
  "hmbApplyImageAssetShotSourceOrderToDom",
  "hmbInstallImageAssetShotDragReorder",
]) {
  assert.equal(typeof widget[helper], "function", `${helper} must remain directly testable.`);
}


class FakeClassList {
  constructor(...names) {
    this.names = new Set(names);
  }

  add(...names) {
    names.forEach((name) => this.names.add(name));
  }

  remove(...names) {
    names.forEach((name) => this.names.delete(name));
  }

  contains(name) {
    return this.names.has(name);
  }
}


class FakeCard {
  constructor(uid, shotUuid) {
    this.attributes = new Map([
      ["data-selected-key", `library:${uid}`],
      ["data-shot-source-uid", uid],
      ["data-shot-uuid", shotUuid],
      ["draggable", "true"],
    ]);
    this.classList = new FakeClassList("selected-card");
    this.slot = { textContent: "" };
    this.tray = null;
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  closest(selector) {
    if (selector === "[data-selected-key]") return this;
    if (selector === "[data-shot-tray]") return this.tray;
    return null;
  }

  querySelector(selector) {
    return selector === ".slot" ? this.slot : null;
  }
}


class FakeControl {
  constructor(card) {
    this.card = card;
  }

  closest(selector) {
    if (selector === "[data-selected-key]") return this.card;
    if (selector === "[data-shot-tray]") return this.card.tray;
    if (selector.includes("button")) return this;
    return null;
  }
}


class FakeTray {
  constructor(shotUuid, cards) {
    this.shotUuid = shotUuid;
    this.children = [];
    cards.forEach((card) => this.appendChild(card));
  }

  getAttribute(name) {
    return name === "data-shot-tray" ? this.shotUuid : null;
  }

  querySelectorAll(selector) {
    return selector === "[data-selected-key]" ? [...this.children] : [];
  }

  contains(item) {
    return item === this || this.children.includes(item) || item?.card && this.children.includes(item.card);
  }

  appendChild(card) {
    this.children = this.children.filter((item) => item !== card);
    card.tray = this;
    this.children.push(card);
    return card;
  }

  insertBefore(card, before) {
    this.children = this.children.filter((item) => item !== card);
    card.tray = this;
    const index = before ? this.children.indexOf(before) : -1;
    if (index < 0) this.children.push(card);
    else this.children.splice(index, 0, card);
    return card;
  }
}


class FakeContainer {
  constructor(tray) {
    this.tray = tray;
    this.listeners = new Map();
  }

  addEventListener(name, handler, capture) {
    assert.equal(capture, true, `${name} must use capture-phase root delegation.`);
    const handlers = this.listeners.get(name) || [];
    handlers.push(handler);
    this.listeners.set(name, handlers);
  }

  removeEventListener(name, handler, capture) {
    assert.equal(capture, true);
    this.listeners.set(name, (this.listeners.get(name) || []).filter((item) => item !== handler));
  }

  querySelector(selector) {
    return selector === "[data-shot-tray]" ? this.tray : null;
  }

  querySelectorAll(selector) {
    const cards = [...this.tray.children];
    if (selector === "[data-selected-key]") return cards;
    if (selector === ".selected-card.drop-target") {
      return cards.filter((card) => card.classList.contains("drop-target"));
    }
    if (selector === ".selected-card.dragging") {
      return cards.filter((card) => card.classList.contains("dragging"));
    }
    return [];
  }

  contains(item) {
    return item === this || item === this.tray || this.tray.contains(item);
  }

  dispatch(name, event) {
    for (const handler of this.listeners.get(name) || []) handler(event);
  }
}


function fakeEvent(target, dataTransfer = null) {
  return {
    target,
    dataTransfer,
    relatedTarget: null,
    defaultPrevented: false,
    propagationStopped: false,
    immediatePropagationStopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; },
    stopImmediatePropagation() { this.immediatePropagationStopped = true; },
  };
}


const shotOneUuid = "11111111-1111-4111-8111-111111111111";
const shotTwoUuid = "22222222-2222-4222-8222-222222222222";


function initialState() {
  return {
    assets: ["asset-a", "asset-b", "asset-c", "asset-x", "asset-y"].map((sourceUid, index) => ({
      asset_library_id: `library:${sourceUid}`,
      source_uid: sourceUid,
      source_kind: "user",
      selected: true,
      selection_order: index + 1,
    })),
    shot_routing: {
      publisher_instance_uuid: "44444444-4444-4444-8444-444444444444",
      channel_uuid: "33333333-3333-4333-8333-333333333333",
      active_shot_uuid: shotOneUuid,
      revision: 1,
      shots: [
        {
          shot_uuid: shotOneUuid,
          number: 1,
          name: "Shot 1",
          revision: 1,
          selected_source_uids: ["asset-a", "asset-b", "asset-c"],
        },
        {
          shot_uuid: shotTwoUuid,
          number: 2,
          name: "Shot 2",
          revision: 1,
          selected_source_uids: ["asset-x", "asset-y"],
        },
      ],
    },
  };
}


function makeHarness() {
  let liveState = initialState();
  const cards = ["asset-a", "asset-b", "asset-c"].map((uid) => new FakeCard(uid, shotOneUuid));
  const container = new FakeContainer(new FakeTray(shotOneUuid, cards));
  const commits = [];
  const install = () => widget.hmbInstallImageAssetShotDragReorder(container, {
    currentState: () => liveState,
    commitReorder(details) {
      const changed = widget.hmbReorderImageAssetShotSource(
        liveState,
        details.shotUuid,
        details.sourceUid,
        details.targetUid,
      );
      if (!changed) return false;
      widget.hmbApplyImageAssetShotSourceOrderToDom(container, liveState, details.shotUuid);
      commits.push(details);
      return true;
    },
  });
  return {
    cards,
    container,
    commits,
    currentState: () => liveState,
    install,
  };
}


function dataTransfer() {
  return {
    effectAllowed: "none",
    dropEffect: "none",
    payload: "",
    setData(_type, value) { this.payload = value; },
    getData() { return this.payload; },
  };
}


// One full-card drag commits once, changes only the active Shot's ordered UID
// list, moves the keyed DOM cards optimistically, and suppresses the synthetic
// click that browsers emit after a native drag.
{
  const harness = makeHarness();
  const cleanup = harness.install();
  const transfer = dataTransfer();
  harness.container.dispatch("dragstart", fakeEvent(harness.cards[2], transfer));
  harness.container.dispatch("dragover", fakeEvent(harness.cards[0], transfer));
  harness.container.dispatch("drop", fakeEvent(harness.cards[0], transfer));
  harness.container.dispatch("dragend", fakeEvent(harness.cards[2], transfer));
  assert.equal(harness.commits.length, 1, "drop plus dragend must publish only once.");
  assert.deepEqual(
    harness.currentState().shot_routing.shots[0].selected_source_uids,
    ["asset-c", "asset-a", "asset-b"],
  );
  assert.deepEqual(
    harness.currentState().shot_routing.shots[1].selected_source_uids,
    ["asset-x", "asset-y"],
    "A Shot 1 reorder must not mutate Shot 2.",
  );
  assert.deepEqual(
    harness.container.tray.children.map((card) => card.getAttribute("data-shot-source-uid")),
    ["asset-c", "asset-a", "asset-b"],
  );
  assert.deepEqual(
    harness.container.tray.children.map((card) => card.slot.textContent),
    ["01", "02", "03"],
  );
  const syntheticClick = fakeEvent(harness.cards[2]);
  harness.container.dispatch("click", syntheticClick);
  assert.equal(syntheticClick.defaultPrevented, true, "The post-drag click must be suppressed.");
  cleanup();
}


// The session lives on the persistent widget container. Replacing every card
// during a host morph and reinstalling the capture controller must retain the
// last valid target so dragend can finish the gesture.
{
  const harness = makeHarness();
  let cleanup = harness.install();
  const transfer = dataTransfer();
  harness.container.dispatch("dragstart", fakeEvent(harness.cards[1], transfer));
  harness.container.dispatch("dragover", fakeEvent(harness.cards[2], transfer));
  cleanup();
  assert.ok(harness.container.__hmbImageAssetDragSession, "Cleanup for a morph must retain the drag session.");
  const replacementCards = ["asset-a", "asset-b", "asset-c"]
    .map((uid) => new FakeCard(uid, shotOneUuid));
  harness.container.tray = new FakeTray(shotOneUuid, replacementCards);
  cleanup = harness.install();
  assert.equal(replacementCards[1].classList.contains("dragging"), true);
  assert.equal(replacementCards[2].classList.contains("drop-target"), true);
  harness.container.dispatch("dragend", fakeEvent(replacementCards[1], transfer));
  assert.equal(harness.commits.length, 1, "The dragend fallback must publish once after a card morph.");
  assert.deepEqual(
    harness.currentState().shot_routing.shots[0].selected_source_uids,
    ["asset-a", "asset-c", "asset-b"],
  );
  cleanup();
}


// Dragging from a delete/interactive control is vetoed. A target from a
// different Shot is also rejected even if malformed markup places it in the
// active tray.
{
  const harness = makeHarness();
  const cleanup = harness.install();
  const transfer = dataTransfer();
  const controlStart = fakeEvent(new FakeControl(harness.cards[0]), transfer);
  harness.container.dispatch("dragstart", controlStart);
  assert.equal(controlStart.defaultPrevented, true);
  assert.equal(harness.container.__hmbImageAssetDragSession, undefined);

  harness.container.dispatch("dragstart", fakeEvent(harness.cards[0], transfer));
  const foreignCard = new FakeCard("asset-x", shotTwoUuid);
  harness.container.tray.appendChild(foreignCard);
  harness.container.dispatch("dragover", fakeEvent(foreignCard, transfer));
  harness.container.dispatch("dragend", fakeEvent(harness.cards[0], transfer));
  assert.equal(harness.commits.length, 0, "Cross-Shot drag targets must fail closed.");
  assert.deepEqual(
    harness.currentState().shot_routing.shots[0].selected_source_uids,
    ["asset-a", "asset-b", "asset-c"],
  );
  cleanup();
}


assert.doesNotMatch(source, /data-move=|move_left:|move_right:|hmbMoveImageAssetShotSource/);
assert.match(
  source,
  /listen\("dragstart"[\s\S]*?listen\("dragover"[\s\S]*?listen\("drop"[\s\S]*?listen\("dragend"/,
  "The root controller must own all four native drag lifecycle events.",
);
assert.match(source, /entry\?\.target\?\.closest\?\.\(IMAGE_ASSET_DRAG_CONTROL_SELECTOR\)/);
assert.match(source, /delete container\.__hmbImageAssetDragSession;[\s\S]*?commitReorder\(details\)/);
assert.match(source, /hmbApplyImageAssetShotSourceOrderToDom\(container, state, shotUuid\)/);

console.log("HMB ImageAsset full-card Shot-local drag reorder regression: PASS");
