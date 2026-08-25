import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const source = fs.readFileSync(widgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);


const shot = "11111111-1111-4111-8111-111111111111";
const video = (uid) => ({
  video_uid: uid,
  source_uid: uid,
  video_url: `https://example.invalid/${uid}.mp4`,
  selected: uid === "video-a",
  selection_order: uid === "video-a" ? 1 : 0,
  video_slot: uid === "video-a" ? 1 : 0,
});
const stablePreviewState = {
  videos: [video("video-a"), video("video-b")],
  picker_shots: [{
    workspace_uuid: shot,
    number: 1,
    name: "Shot 1",
    video_asset_uids: ["video-a", "video-b"],
    selected_video_uids: ["video-a"],
    preview_video_uid: "video-a",
  }],
  active_picker_shot_uuid: shot,
  preview_video_uid: "video-a",
  selected_video_uid: "video-a",
  selected_video_slot: 1,
  viewport_mode: "video",
};

// Selecting is generator-order work, not a playback request. Once a preview
// exists, selecting another card must preserve its exact media identity.
const selectedB = widget.hmbToggleVideoAssetSelection(stablePreviewState, "video-b");
assert.deepEqual(
  widget.hmbSelectedVideoAssets(selectedB).map((item) => item.video_uid),
  ["video-a", "video-b"],
);
assert.equal(selectedB.preview_video_uid, "video-a");
assert.equal(
  widget.hmbVideoPickerPreviewIdentity(selectedB),
  widget.hmbVideoPickerPreviewIdentity(stablePreviewState),
  "Selecting a second generator card cannot switch or reload the preview.",
);

const deselectedB = widget.hmbToggleVideoAssetSelection(selectedB, "video-b");
assert.equal(deselectedB.preview_video_uid, "video-a");
assert.equal(
  widget.hmbVideoPickerPreviewIdentity(deselectedB),
  widget.hmbVideoPickerPreviewIdentity(stablePreviewState),
  "Deselecting a non-preview card cannot touch media playback.",
);

const deselectedPreview = widget.hmbToggleVideoAssetSelection(selectedB, "video-a");
assert.equal(deselectedPreview.preview_video_uid, "video-a");
assert.equal(
  widget.hmbVideoPickerPreviewIdentity(deselectedPreview),
  widget.hmbVideoPickerPreviewIdentity(selectedB),
  "Name-click deselection cannot switch the Loader preview; only Play may do that.",
);

// Exact reported regression: B is playing while A is the only selected
// generator input. Clicking A empties @video order but must keep B playing.
const playingMedia = {
  paused: false,
  ended: false,
  getAttribute(name) { return name === "data-video-uid" ? "video-b" : ""; },
};
const playbackContainer = {
  querySelector(selector) { return selector === "#picker-video" ? playingMedia : null; },
};
const playbackIntent = widget.hmbBeginVideoPickerPlaybackIntent(
  playbackContainer,
  playingMedia,
  "video-b",
  "viewport",
);
const playbackPinned = widget.hmbPinVideoPickerActivePlaybackPreview(
  stablePreviewState,
  playbackContainer,
);
assert.equal(playbackPinned.preview_video_uid, "video-b");
assert.deepEqual(
  widget.hmbSelectedVideoAssets(playbackPinned).map((item) => item.video_uid),
  ["video-a"],
  "Pinning playback cannot alter generator selection.",
);
const emptiedWhileBPlays = widget.hmbToggleVideoAssetSelection(playbackPinned, "video-a");
assert.deepEqual(widget.hmbSelectedVideoAssets(emptiedWhileBPlays), []);
assert.equal(emptiedWhileBPlays.preview_video_uid, "video-b");
assert.equal(
  widget.hmbVideoPickerPlaybackIntentMatches(
    playbackContainer,
    playingMedia,
    playbackIntent,
  ),
  true,
  "Selecting/deselecting A cannot cancel B's playback intent.",
);
assert.match(
  source,
  /liveState = hmbPinVideoPickerActivePlaybackPreview\(liveState, container\);[\s\S]*?const nextState = hmbToggleVideoAssetSelection\(liveState, uid\);/,
  "The shared compact/expanded name-click handler must pin active playback before selection.",
);

// Cross the real expanded preview patch + media-controller refresh boundary.
// Both selecting and deselecting A must be zero-touch operations for the
// already-playing B media element.
let expandedSrcWrites = 0;
let expandedPauseCalls = 0;
let expandedLoadCalls = 0;
let expandedPlayCalls = 0;
let expandedListenerAdds = 0;
let expandedListenerRemoves = 0;
const expandedAttributes = new Map([
  ["src", "https://example.invalid/video-b.mp4"],
  ["data-video-uid", "video-b"],
]);
const expandedMedia = {
  hidden: false,
  paused: false,
  ended: false,
  currentTime: 1.75,
  readyState: 4,
  get src() { return expandedAttributes.get("src") || ""; },
  set src(value) {
    expandedSrcWrites += 1;
    expandedAttributes.set("src", String(value));
  },
  getAttribute(name) { return expandedAttributes.get(name) || ""; },
  setAttribute(name, value) {
    if (name === "src") expandedSrcWrites += 1;
    expandedAttributes.set(name, String(value));
  },
  addEventListener() { expandedListenerAdds += 1; },
  removeEventListener() { expandedListenerRemoves += 1; },
  pause() { expandedPauseCalls += 1; this.paused = true; },
  load() { expandedLoadCalls += 1; },
  play() { expandedPlayCalls += 1; this.paused = false; return Promise.resolve(); },
};
const expandedStage = {
  ownerDocument: {
    createElement() {
      throw new Error("Stable B playback must retain its expanded media element.");
    },
  },
  querySelector(selector) {
    return selector === "#picker-video" ? expandedMedia : null;
  },
};
const expandedContainer = {
  __hmbVideoPickerExpanded: true,
  querySelector(selector) {
    if (selector === ".compact-preview" || selector === "#picker-video") {
      return selector === ".compact-preview" ? expandedStage : expandedMedia;
    }
    return null;
  },
  querySelectorAll() { return []; },
};
const expandedController = widget.hmbCreateVideoPickerMediaController(expandedContainer, {
  state: playbackPinned,
});
const expandedListenerCount = expandedListenerAdds;
const expandedPlaybackIntent = widget.hmbBeginVideoPickerPlaybackIntent(
  expandedContainer,
  expandedMedia,
  "video-b",
  "viewport",
);
widget.hmbConfirmVideoPickerPlaybackStarted(expandedContainer, expandedMedia, "video-b");
const expandedTimeBeforeClicks = expandedMedia.currentTime;
let expandedClickState = widget.hmbToggleVideoAssetSelection(playbackPinned, "video-a");
assert.deepEqual(widget.hmbSelectedVideoAssets(expandedClickState), []);
assert.equal(widget.hmbPatchVideoPickerPreviewDom(expandedContainer, expandedClickState), expandedMedia);
expandedController.refresh(expandedClickState);
expandedClickState = widget.hmbToggleVideoAssetSelection(expandedClickState, "video-a");
assert.deepEqual(
  widget.hmbSelectedVideoAssets(expandedClickState).map((item) => item.video_uid),
  ["video-a"],
);
assert.equal(widget.hmbPatchVideoPickerPreviewDom(expandedContainer, expandedClickState), expandedMedia);
expandedController.refresh(expandedClickState);
assert.equal(expandedClickState.preview_video_uid, "video-b");
assert.equal(expandedController.currentVideo(), expandedMedia);
assert.equal(expandedMedia.getAttribute("data-video-uid"), "video-b");
assert.equal(expandedMedia.getAttribute("src"), "https://example.invalid/video-b.mp4");
assert.equal(expandedMedia.currentTime, expandedTimeBeforeClicks);
assert.equal(expandedMedia.paused, false);
assert.equal(expandedPauseCalls, 0, "A name selection cannot pause playing B.");
assert.equal(expandedLoadCalls, 0, "A name selection cannot reload playing B.");
assert.equal(expandedSrcWrites, 0, "A name selection cannot replace playing B's source.");
assert.equal(expandedPlayCalls, 0, "A name selection cannot restart playing B.");
assert.equal(expandedListenerAdds, expandedListenerCount);
assert.equal(
  widget.hmbVideoPickerPlaybackIntentMatches(
    expandedContainer,
    expandedMedia,
    expandedPlaybackIntent,
  ),
  true,
);
expandedController.cleanup();
assert.equal(expandedListenerRemoves, expandedListenerCount);

const firstSelection = widget.hmbToggleVideoAssetSelection({
  ...stablePreviewState,
  videos: [
    { ...video("video-a"), selected: false, selection_order: 0, video_slot: 0 },
    video("video-b"),
  ],
  picker_shots: [{
    ...stablePreviewState.picker_shots[0],
    selected_video_uids: [],
    preview_video_uid: "",
  }],
  preview_video_uid: "",
  selected_video_uid: "",
}, "video-a");
assert.equal(firstSelection.preview_video_uid, "video-a", "The first selection supplies the fallback preview.");

// Even if a retained echo asks for the same preview again, the regional media
// patch must not write src or call load(). This directly guards decoder churn.
let srcWrites = 0;
let loadCalls = 0;
let pauseCalls = 0;
const mediaAttributes = new Map([["src", "https://example.invalid/video-a.mp4"]]);
const media = {
  hidden: false,
  paused: true,
  ended: false,
  getAttribute(name) { return mediaAttributes.get(name) || ""; },
  setAttribute(name, value) {
    if (name === "src") srcWrites += 1;
    mediaAttributes.set(name, String(value));
  },
  pause() { pauseCalls += 1; },
  load() { loadCalls += 1; },
};
const stage = {
  ownerDocument: { createElement() { throw new Error("Stable preview must retain its media element."); } },
  querySelector(selector) {
    if (selector === "#picker-video") return media;
    return null;
  },
};
const container = {
  querySelector(selector) {
    if (selector === ".compact-preview") return stage;
    return null;
  },
  querySelectorAll() { return []; },
};
assert.equal(widget.hmbPatchVideoPickerPreviewDom(container, selectedB), media);
assert.equal(srcWrites, 0, "A stable selection cannot rewrite the preview src.");
assert.equal(loadCalls, 0, "A stable selection cannot restart metadata/decode loading.");
assert.equal(pauseCalls, 0, "A stable selection cannot pause the current preview.");

let listenerAdds = 0;
let listenerRemoves = 0;
media.currentTime = 0;
media.addEventListener = () => { listenerAdds += 1; };
media.removeEventListener = () => { listenerRemoves += 1; };
const controllerContainer = {
  querySelector(selector) {
    if (selector === "#picker-video") return media;
    return null;
  },
  querySelectorAll() { return []; },
};
const mediaController = widget.hmbCreateVideoPickerMediaController(controllerContainer, {
  state: stablePreviewState,
});
const listenerCountAfterBind = listenerAdds;
mediaController.refresh(selectedB);
mediaController.refresh(deselectedB);
assert.equal(
  listenerAdds,
  listenerCountAfterBind,
  "Stable selection refreshes must retain one media listener set instead of rebinding it.",
);
assert.equal(loadCalls, 0, "Deferred media-controller refreshes cannot call load().");
assert.equal(srcWrites, 0, "Deferred media-controller refreshes cannot rewrite src.");
mediaController.cleanup();
assert.equal(listenerRemoves, listenerCountAfterBind, "Media cleanup must release the one bound listener set.");

// Selected/unselected cards reserve the same 2px border box. The highlight is
// color/glow only; it cannot push thumbnail or text content by one pixel.
assert.match(
  source,
  /\.hmbvp:not\(\.hmbvp-compact\) \.video-asset-card\{border-width:2px;transition:none\}/,
);
const selectedRule = source.match(/\.video-asset-card\.selected\{border-width:(\d+)px;/);
assert.equal(Number(selectedRule?.[1]), 2);
assert.match(
  source,
  /\.hmbvp\.hmbvp-compact \.compact-shot-slot\{[^}]*border-width:1px;[^}]*transition:none\}/,
);
assert.match(
  source,
  /\.hmbvp\.hmbvp-compact \.compact-shot-slot\.selected\{border-width:1px;/,
);

// Delayed Python/WebSocket rows may carry useful backend status, but a lower
// or same divergent Loader revision cannot repaint the previous border/order.
{
  const selectedLocalState = widget.hmbToggleVideoAssetSelection(
    stablePreviewState,
    "video-b",
  );
  const local = {
    ...selectedLocalState,
    state_revision: 18,
    state_published_at_ms: 1800,
    state_writer: "widget",
    picker_shots: [{
      ...selectedLocalState.picker_shots[0],
      revision: 7,
      selected_video_uids: ["video-a", "video-b"],
      preview_video_uid: "video-a",
      selected_video_slot: 1,
    }],
  };
  const delayed = {
    ...local,
    state_revision: 17,
    state_published_at_ms: 1700,
    state_writer: "python",
    status: "RUNNING",
    videos: local.videos.map((item) => ({
      ...item,
      selected: item.video_uid === "video-a",
      selection_order: item.video_uid === "video-a" ? 1 : 0,
      video_slot: item.video_uid === "video-a" ? 1 : 0,
    })),
    picker_shots: [{
      ...local.picker_shots[0],
      revision: 6,
      selected_video_uids: ["video-a"],
      preview_video_uid: "video-a",
      selected_video_slot: 1,
    }],
  };
  const protectedLower = widget.hmbProtectVideoPickerWorkspaceFromStaleEcho(delayed, local);
  assert.equal(protectedLower.protected, true);
  assert.deepEqual(protectedLower.state.picker_shots[0].selected_video_uids, ["video-a", "video-b"]);
  assert.equal(protectedLower.state.picker_shots[0].preview_video_uid, "video-a");
  assert.equal(protectedLower.state.status, "RUNNING", "Fresh backend status still merges.");
  const localAfterAdd = {
    ...local,
    state_revision: 19,
    videos: [
      ...local.videos,
      { ...video("video-c"), label: "new local card", picker_shot_uuid: shot },
    ],
    picker_shots: [{
      ...local.picker_shots[0],
      revision: 8,
      video_asset_uids: ["video-a", "video-b", "video-c"],
      selected_video_uids: ["video-a", "video-b"],
      preview_video_uid: "video-a",
    }],
  };
  const lowerBeforeAdd = {
    ...delayed,
    state_revision: 18,
    picker_shots: [{
      ...delayed.picker_shots[0],
      revision: 7,
      video_asset_uids: ["video-a", "video-b"],
      selected_video_uids: ["video-a", "video-b"],
      preview_video_uid: "video-a",
    }],
  };
  const protectedAdd = widget.hmbProtectVideoPickerWorkspaceFromStaleEcho(
    lowerBeforeAdd,
    localAfterAdd,
  );
  assert.equal(protectedAdd.protected, true);
  assert.deepEqual(
    protectedAdd.state.picker_shots[0].video_asset_uids,
    ["video-a", "video-b", "video-c"],
    "A strict-lower echo cannot remove a newly finalized local card.",
  );
  assert.equal(
    protectedAdd.state.videos.find((item) => item.video_uid === "video-c")?.label,
    "new local card",
  );
  const protectedAddWithDifferentSelection = widget.hmbProtectVideoPickerWorkspaceFromStaleEcho({
    ...lowerBeforeAdd,
    picker_shots: [{ ...lowerBeforeAdd.picker_shots[0], selected_video_uids: ["video-a"] }],
  }, localAfterAdd);
  assert.deepEqual(
    protectedAddWithDifferentSelection.state.picker_shots[0].video_asset_uids,
    ["video-a", "video-b", "video-c"],
  );
  const localAfterDelete = {
    ...local,
    state_revision: 19,
    videos: [local.videos[0]],
    picker_shots: [{
      ...local.picker_shots[0],
      revision: 8,
      video_asset_uids: ["video-a"],
      selected_video_uids: ["video-a"],
      preview_video_uid: "video-a",
    }],
  };
  const lowerBeforeDelete = {
    ...delayed,
    state_revision: 18,
    videos: [...local.videos],
    picker_shots: [{
      ...delayed.picker_shots[0],
      revision: 7,
      video_asset_uids: ["video-a", "video-b"],
      selected_video_uids: ["video-a", "video-b"],
      preview_video_uid: "video-a",
    }],
  };
  const protectedDelete = widget.hmbProtectVideoPickerWorkspaceFromStaleEcho(
    lowerBeforeDelete,
    localAfterDelete,
  );
  assert.equal(protectedDelete.protected, true);
  assert.deepEqual(protectedDelete.state.picker_shots[0].video_asset_uids, ["video-a"]);
  assert.equal(
    protectedDelete.state.videos.some((item) => item.video_uid === "video-b"),
    false,
    "A strict-lower catalog cannot resurrect a card deleted by the newer local row.",
  );
  const sameRevisionDivergent = widget.hmbProtectVideoPickerWorkspaceFromStaleEcho({
    ...delayed,
    state_revision: 18,
    picker_shots: [{ ...delayed.picker_shots[0], revision: 7 }],
  }, local);
  assert.equal(sameRevisionDivergent.protected, true);
  assert.deepEqual(
    sameRevisionDivergent.state.picker_shots[0].selected_video_uids,
    ["video-a", "video-b"],
  );
  const backendRestoredVideo = {
    ...local.videos[1],
    label: "video-b restored by Python",
    selected: false,
    selection_order: 0,
    video_slot: 0,
  };
  const sameRevisionDeleteRejected = widget.hmbProtectVideoPickerWorkspaceFromStaleEcho({
    ...local,
    state_writer: "python",
    videos: [local.videos[0], backendRestoredVideo],
    picker_shots: [{
      ...local.picker_shots[0],
      revision: 7,
      video_asset_uids: ["video-a", "video-b"],
      selected_video_uids: ["video-a"],
      preview_video_uid: "video-a",
    }],
  }, {
    ...local,
    state_writer: "widget",
    videos: [local.videos[0]],
    picker_shots: [{
      ...local.picker_shots[0],
      revision: 7,
      video_asset_uids: ["video-a"],
      selected_video_uids: ["video-a"],
      preview_video_uid: "video-a",
    }],
  });
  assert.equal(
    sameRevisionDeleteRejected.protected,
    false,
    "A same-revision Python ownership/catalog restoration is authoritative.",
  );
  assert.deepEqual(
    sameRevisionDeleteRejected.state.picker_shots[0].video_asset_uids,
    ["video-a", "video-b"],
  );
  assert.equal(
    sameRevisionDeleteRejected.state.videos[1].label,
    "video-b restored by Python",
    "Fresh backend media metadata cannot be replaced by an optimistic local catalog.",
  );
  const newer = widget.hmbProtectVideoPickerWorkspaceFromStaleEcho({
    ...delayed,
    state_revision: 19,
    picker_shots: [{ ...delayed.picker_shots[0], revision: 8 }],
  }, local);
  assert.equal(newer.protected, false);
  assert.deepEqual(newer.state.picker_shots[0].selected_video_uids, ["video-a"]);
}

const compactFingerprintStart = source.indexOf("function hmbVideoPickerCompactSlotFingerprint");
const compactFingerprintEnd = source.indexOf("function hmbVideoPickerCompactVideoHtml", compactFingerprintStart);
const compactFingerprintSource = source.slice(compactFingerprintStart, compactFingerprintEnd);
assert.doesNotMatch(
  compactFingerprintSource,
  /!!locked/,
  "A publication lock cannot replace compact cards and blink their poster/border.",
);

const sharedSelectionStart = source.indexOf("const toggleSharedLoaderVideoSelection = (");
const sharedSelectionEnd = source.indexOf(
  "const commitSharedLoaderVideoDrag = (",
  sharedSelectionStart,
);
const sharedSelection = source.slice(sharedSelectionStart, sharedSelectionEnd);
assert.ok(sharedSelectionStart >= 0 && sharedSelectionEnd > sharedSelectionStart);
assert.match(sharedSelection, /previewIdentityChanged/);
assert.match(
  sharedSelection,
  /if \(previewIdentityChanged\)\s*\{\s*hmbPatchVideoPickerPreviewDom/,
);
assert.doesNotMatch(
  sharedSelection,
  /hmbApplyVideoPickerCompactGeometry|hmbApplyVideoPickerCompactHostSizing|schedulePickerFit|ResizeObserver|\.style\.height/,
  "A selection event cannot write widget/React Flow geometry.",
);
assert.equal(
  (source.match(/toggleSharedLoaderVideoSelection\(event, selectionSurface\);/g) || []).length,
  2,
  "Compact and expanded name clicks must use one shared Loader selection handler.",
);

console.log("HMB VideoPicker selection no-jank/media-load regression: PASS");
