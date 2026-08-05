import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);


assert.equal(
  typeof widget.hmbSnapshotHistory,
  "function",
  "Snapshot history must remain an exported, directly testable state helper.",
);

const snapshotState = {
  videos: [],
  snapshots: [
    {
      snapshot_uid: "snapshot-b",
      video_uid: "video-b",
      frame: 20,
      created_at_ms: 20,
      data_uri: "data:image/png;base64,QkJCQg==",
    },
    {
      snapshot_uid: "snapshot-a",
      video_uid: "video-a",
      frame: 10,
      created_at_ms: 10,
      data_uri: "data:image/png;base64,QUFBQQ==",
    },
    {
      snapshot_id: "legacy-stable-id",
      video_uid: "video-c",
      frame: 30,
      created_at_ms: 30,
      data_uri: "data:image/jpeg;base64,Q0NDQw==",
    },
    {
      video_uid: "video-d",
      frame: 40,
      created_at_ms: 40,
      path: "C:/shot/snapshot-d.png",
      data_uri: "data:image/png;base64,RERERA==",
    },
    {
      snapshot_uid: "not-an-image",
      created_at_ms: 50,
      data_uri: "file:///C:/shot/not-an-image.png",
    },
  ],
};

const firstHistory = widget.hmbSnapshotHistory(snapshotState);
const secondHistory = widget.hmbSnapshotHistory(structuredClone(snapshotState));
assert.deepEqual(
  firstHistory.slice(0, 3).map((item) => item.snapshot_uid),
  ["snapshot-a", "snapshot-b", "legacy-stable-id"],
  "Explicit snapshot identities must survive chronological history sorting.",
);
assert.equal(firstHistory.length, 4, "Only displayable image snapshots belong to history.");
assert.match(firstHistory[3].snapshot_uid, /^snapshot-[0-9a-f]{8}$/);
assert.equal(
  firstHistory[3].snapshot_uid,
  secondHistory[3].snapshot_uid,
  "Compatibility snapshots without an explicit UID need deterministic stable identity.",
);

assert.match(widgetSource, /active_snapshot_uid: ""/);
assert.match(widgetSource, /viewport_mode: "video"/);

const normalizedViewportStart = widgetSource.indexOf("const requestedViewportMode =");
const normalizedViewportEnd = widgetSource.indexOf(
  "state.viewport_mode = viewportMode;",
  normalizedViewportStart,
);
assert.ok(normalizedViewportStart >= 0 && normalizedViewportEnd > normalizedViewportStart);
const normalizedViewportSource = widgetSource.slice(
  normalizedViewportStart,
  normalizedViewportEnd + "state.viewport_mode = viewportMode;".length,
);
assert.match(normalizedViewportSource, /source\?\.viewport_mode/);
assert.match(
  normalizedViewportSource,
  /state\.snapshot_active && activeSnapshotUid \? "snapshot" : "video"/,
  "A successful snapshot backend echo must normalize directly into snapshot mode.",
);
assert.match(normalizedViewportSource, /state\.viewport_mode = viewportMode/);

const viewportModeStart = widgetSource.indexOf("const viewportMode =");
const forceVideoStart = widgetSource.indexOf("const forceVideoPreview", viewportModeStart);
assert.ok(viewportModeStart >= 0 && forceVideoStart > viewportModeStart);
const viewportModeSource = widgetSource.slice(viewportModeStart, forceVideoStart);
assert.match(viewportModeSource, /viewportMode === "snapshot"/);
assert.match(viewportModeSource, /retainedViewportVideo\?\.pause\?\.\(\)/);
assert.match(viewportModeSource, /delete container\.__hmbAutoplayVideoUid/);
assert.match(viewportModeSource, /delete container\.__hmbForceVideoPreviewUid/);

const selectedSnapshotStart = widgetSource.indexOf("const selectedSnapshot =");
const initialViewportFrameStart = widgetSource.indexOf(
  "const initialViewportFrame",
  selectedSnapshotStart,
);
assert.ok(selectedSnapshotStart >= 0 && initialViewportFrameStart > selectedSnapshotStart);
const selectedSnapshotSource = widgetSource.slice(
  selectedSnapshotStart,
  initialViewportFrameStart,
);
assert.match(
  selectedSnapshotSource,
  /snapshotHistory\.find\([\s\S]*?snapshot_uid[\s\S]*?active_snapshot_uid[\s\S]*?\|\|\s*\(viewportMode === "snapshot" \? snapshotHistory\.at\(-1\) : null\)/,
);
assert.match(
  selectedSnapshotSource,
  /snapshotForViewport = viewportMode === "snapshot"[\s\S]*?selectedSnapshot\?\.data_uri/,
);
assert.doesNotMatch(
  selectedSnapshotSource,
  /previewOrder|selectedSlot|video_slot/,
  "An active snapshot must render even when no video is selected.",
);

assert.match(widgetSource, /id="picker-snapshot-image"/);
assert.match(widgetSource, /id="picker-video"/);
assert.match(
  widgetSource,
  /const viewportModeLabel = snapshotForViewport \? \(tr\.snapshot \|\| "Snapshot"\) : \(tr\.preview \|\| "Video"\)/,
);
assert.match(
  widgetSource,
  /class="panel-title viewport-title"[^\n]*\$\{escapeHtml\(viewportModeLabel\)\}/,
  "The shared viewport title must expose Snapshot versus Video mode.",
);

for (const removedOpenContract of [
  /id="open-video"/,
  /id="open-video-file"/,
  /__hmbOpenedVideoUrl/,
  /__hmbOpenedVideoName/,
  /URL\.createObjectURL/,
  /URL\.revokeObjectURL/,
]) {
  assert.doesNotMatch(widgetSource, removedOpenContract);
}
assert.doesNotMatch(widgetSource, /id="video-prev-frame"|id="video-next-frame"/);
assert.match(widgetSource, /id="snapshot-prev"/);
assert.match(widgetSource, /id="video-play-toggle"/);
assert.match(widgetSource, /id="snapshot-next"/);

const snapshotNavigationStart = widgetSource.indexOf("const showAdjacentSnapshot =");
const mainTransportStart = widgetSource.indexOf(
  "on(playToggleButton, \"click\"",
  snapshotNavigationStart,
);
assert.ok(snapshotNavigationStart >= 0 && mainTransportStart > snapshotNavigationStart);
const snapshotNavigationSource = widgetSource.slice(
  snapshotNavigationStart,
  mainTransportStart,
);
assert.match(snapshotNavigationSource, /hmbSnapshotHistory\(liveState\)/);
assert.match(snapshotNavigationSource, /liveState\.active_snapshot_uid/);
assert.match(
  snapshotNavigationSource,
  /\(activeIndex \+ step \+ liveHistory\.length\) % liveHistory\.length/,
  "Snapshot navigation must wrap at both history ends.",
);
assert.match(snapshotNavigationSource, /viewport_mode: "snapshot"/);
assert.match(snapshotNavigationSource, /active_snapshot_uid: clean\(target\.snapshot_uid\)/);
assert.match(snapshotNavigationSource, /delete container\.__hmbAutoplayVideoUid/);
assert.match(snapshotNavigationSource, /delete container\.__hmbForceVideoPreviewUid/);
assert.match(snapshotNavigationSource, /#snapshot-prev/);
assert.match(snapshotNavigationSource, /#snapshot-next/);

const mainTransportEnd = widgetSource.indexOf(
  "on(videoSeekInput, \"input\"",
  mainTransportStart,
);
const mainTransportSource = widgetSource.slice(mainTransportStart, mainTransportEnd);
assert.match(mainTransportSource, /if \(!viewportVideo\)/);
assert.match(mainTransportSource, /container\.__hmbAutoplayVideoUid = livePreviewUid/);
assert.match(mainTransportSource, /commit\(\{ \.\.\.liveState, viewport_mode: "video" \}\)/);
assert.match(mainTransportSource, /viewportVideo\.pause\(\)/);
assert.match(mainTransportSource, /viewportVideo\.play\?\.\(\)/);
assert.match(
  widgetSource,
  /playToggleButton\.textContent = playing \? "Ⅱ" : "▶"/,
  "The single central transport must switch between play and pause glyphs.",
);

const cardPlaybackStart = widgetSource.indexOf(
  'container.querySelectorAll("[data-play-video-uid]")',
  widgetSource.indexOf('on(container.querySelector("#import-video-asset"), "change"'),
);
const cardPlaybackEnd = widgetSource.indexOf(
  'container.querySelectorAll("[data-toggle-video-uid]")',
  cardPlaybackStart,
);
const cardPlaybackSource = widgetSource.slice(cardPlaybackStart, cardPlaybackEnd);
assert.match(cardPlaybackSource, /container\.__hmbAutoplayVideoUid = uid/);
assert.match(cardPlaybackSource, /container\.__hmbForceVideoPreviewUid = uid/);
assert.match(
  cardPlaybackSource,
  /commit\(\{ \.\.\.hmbPreviewVideoAsset\(liveState, uid\), viewport_mode: "video" \}\)/,
);

const createSnapshotStart = widgetSource.indexOf(
  'on(container.querySelector("#create-snapshot")',
);
const deleteSnapshotStart = widgetSource.indexOf(
  'on(container.querySelector("#delete-snapshot")',
  createSnapshotStart,
);
const snapshotCreateSource = widgetSource.slice(createSnapshotStart, deleteSnapshotStart);
assert.match(snapshotCreateSource, /dispatchCommand\("render_snapshot"/);
assert.match(
  snapshotCreateSource,
  /video_uid: clean\(currentLocal\.preview_video_uid \|\| currentLocal\.selected_video_uid\)/,
);

const deleteSnapshotEnd = widgetSource.indexOf(
  'on(container.querySelector("#run-video")',
  deleteSnapshotStart,
);
const snapshotDeleteSource = widgetSource.slice(deleteSnapshotStart, deleteSnapshotEnd);
assert.match(snapshotDeleteSource, /hmbSnapshotHistory\(currentLocal\)\.find/);
assert.match(snapshotDeleteSource, /active_snapshot_uid/);
assert.match(snapshotDeleteSource, /dispatchCommand\("delete_snapshot"/);
assert.match(snapshotDeleteSource, /snapshot_uid: clean\(activeSnapshot\.snapshot_uid\)/);

console.log(
  "HMB VideoPicker snapshot viewport regression: PASS "
  + "(stable UID history, shared Snapshot/Video viewport, circular snapshot navigation, exact commands)",
);
