import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widgetModule = await import(`data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`);

const sourceState = {
  preview_video_uid: "preview-a",
  selected_video_uid: "preview-a",
  videos: [
    {
      video_uid: "preview-a",
      source_uid: "preview-a",
      video_path: "C:/shot/catalog/preview-a.mp4",
      selected: true,
      selection_order: 1,
    },
    {
      video_uid: "preview-b",
      source_uid: "preview-b",
      video_path: "C:/shot/catalog/preview-b.mp4",
      selected: true,
      selection_order: 2,
    },
  ],
};

const deleted = widgetModule.hmbDeleteVideoAsset(sourceState, "preview-a");
assert.deepEqual(deleted.videos.map((item) => item.video_uid), ["preview-b"]);
assert.equal(deleted.preview_video_uid, "preview-b");
assert.equal(deleted.selected_video_uid, "preview-b");
assert.equal(deleted.selected_video_path, "C:/shot/catalog/preview-b.mp4");

const deleteHandlerStart = widgetSource.indexOf(
  "const deleteVideoAsset = (event, button) =>",
);
const deleteHandlerEnd = widgetSource.indexOf(
  "hmbInstallVideoAssetRootDelegation(",
  deleteHandlerStart,
);
assert.ok(deleteHandlerStart >= 0 && deleteHandlerEnd > deleteHandlerStart);
const deleteHandler = widgetSource.slice(deleteHandlerStart, deleteHandlerEnd);
assert.match(deleteHandler, /preview_video_uid \|\| liveState\.selected_video_uid/);
assert.match(deleteHandler, /container\.__hmbForceVideoPreviewUid/);
assert.match(deleteHandler, /container\.querySelector\("#picker-video"\)\?\.pause\?\.\(\)/);
assert.match(deleteHandler, /delete container\.__hmbForceVideoPreviewUid/);
assert.match(deleteHandler, /delete container\.__hmbAutoplayVideoUid/);
assert.ok(
  deleteHandler.indexOf('container.querySelector("#picker-video")?.pause?.()')
    < deleteHandler.indexOf('dispatchCommand("delete_video_asset"'),
  "The active main preview must pause before the asynchronous delete command is sent.",
);
for (const cleanup of [
  "delete container.__hmbForceVideoPreviewUid",
  "delete container.__hmbAutoplayVideoUid",
]) {
  assert.ok(
    deleteHandler.indexOf(cleanup) < deleteHandler.indexOf('dispatchCommand("delete_video_asset"'),
    `Active-preview delete must run ${cleanup} before command dispatch.`,
  );
}
assert.doesNotMatch(
  deleteHandler,
  /video-asset-thumb-media/,
  "Delete cleanup must never treat a static catalog thumbnail as a playing media element.",
);

let deletedPublications = 0;
const deletedContainer = { __hmbVideoPickerDeleted: true };
const deletedDelivery = widgetModule.hmbDeliverPickerStateIfMounted(
  deletedContainer,
  () => { deletedPublications += 1; },
  { state_revision: 1 },
);
assert.equal(deletedDelivery.delivered, false);
assert.equal(deletedPublications, 0);
const cleanupStart = widgetSource.indexOf("container.__hmbVideoPickerCleanupProxy = () => {");
const cleanupEnd = widgetSource.indexOf("const previousCleanup", cleanupStart);
assert.ok(cleanupStart >= 0 && cleanupEnd > cleanupStart);
const cleanupSource = widgetSource.slice(cleanupStart, cleanupEnd);
for (const requiredCleanup of [
  "container.__hmbVideoPickerDeleted = true",
  "hmbClearPendingPickerStateEcho(container)",
  "delete container.__hmbPendingPickerState",
  "delete container.__hmbAuthoritativePickerState",
  "delete container.__hmbMayaSceneDraftPath",
  "delete container.__hmbMayaSceneDraftRuntimeInstanceId",
  "delete container.__hmbNativePickerDeadlineMs",
  "delete container.__hmbNativePickerPreviousPath",
  "delete container.__hmbReadAckTimer",
  "delete container.__hmbOriginalAckTimer",
]) {
  assert.match(cleanupSource, new RegExp(requiredCleanup.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
}
assert.match(widgetSource, /if \(container\.__hmbVideoPickerDeleted === true\) \{[\s\S]*?delivered: false/);

console.log(
  "HMB VideoPicker delete lifecycle UI regression: PASS "
  + "(active preview cleanup, delete-session timer/cache teardown, zero late publication)",
);
