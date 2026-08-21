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
assert.equal(deselectedPreview.preview_video_uid, "video-b");
assert.notEqual(
  widget.hmbVideoPickerPreviewIdentity(deselectedPreview),
  widget.hmbVideoPickerPreviewIdentity(selectedB),
  "Removing the actual preview must switch once to the retained selection.",
);

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

for (const [startMarker, endMarker] of [
  ["const selectCompactVideo = (", "const deleteCompactVideo = ("],
  ["const toggleVideoSelection = (", "const deleteVideoAsset = ("],
]) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  const handler = source.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.match(handler, /previewIdentityChanged/);
  assert.match(handler, /if \(previewIdentityChanged\) hmbPatchVideoPickerPreviewDom/);
  assert.doesNotMatch(
    handler,
    /hmbApplyVideoPickerCompactGeometry|hmbApplyVideoPickerCompactHostSizing|schedulePickerFit|ResizeObserver|\.style\.height/,
    "A selection event cannot write widget/React Flow geometry.",
  );
}

console.log("HMB VideoPicker selection no-jank/media-load regression: PASS");
