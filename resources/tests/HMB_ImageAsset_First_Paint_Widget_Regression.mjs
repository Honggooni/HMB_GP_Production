import assert from "node:assert/strict";
import * as widget from "../../widgets/HMBImageAssetLibraryWidget.js";
import { hmbImageAssetThumbnailPatchBridgeRegistry } from "../../widgets/HMBImageAssetThumbnailPatchBridgeWidget.js";

const frames = [], timers = new Map();
let handle = 0;
const original = { raf: globalThis.requestAnimationFrame, set: globalThis.setTimeout, clear: globalThis.clearTimeout };
globalThis.requestAnimationFrame = callback => { frames.push(callback); return ++handle; };
globalThis.setTimeout = (callback, delay = 0) => { const id = ++handle; timers.set(id, { callback, delay }); return id; };
globalThis.clearTimeout = id => timers.delete(id);
const flushPaint = () => {
  frames.splice(0).forEach(callback => callback());
  for (const [id, timer] of [...timers]) if (!timer.delay) { timers.delete(id); timer.callback(); }
};
const registry = hmbImageAssetThumbnailPatchBridgeRegistry();
const state = widget.hmbNormalizeImageAssetState({
  project_root: "C:/fixture/FirstProject", project_uid: "first-project",
  project_cache_uid: "hmbpc1:" + "1".repeat(32), manifest_signature: "first-manifest", scan_revision: 7,
  widget_runtime_lease: "12345678-1234-4234-8234-123456789abc", ui_edit_revision: 9,
  assets: Array.from({ length: 150 }, (_, index) => ({
    asset_library_id: `image-${index}`, source_uid: `project:image-${index}`,
    asset_id: `image-${index}`, image_name: `Image ${index}`, source_kind: "project", registered: true,
    path: `C:/fixture/FirstProject/Assets/image-${index}.png`, relative_path: `Assets/image-${index}.png`,
    media_signature: `source-signature-${index}`, selected: index === 145, selection_order: index === 145 ? 1 : 0,
  })),
});
const container = { __hmbImageAssetLatestState: state, querySelector() { return null; }, querySelectorAll() { return []; } };
const requests = [];
registry.set(state.shot_routing.publisher_instance_uuid, { dispatch: request => requests.push(structuredClone(request)) });
const before = structuredClone({ routing: state.shot_routing, selection: widget.hmbImageAssetSelectionSnapshot(state) });

function complete(current, request, revision) {
  const wanted = new Set(request.asset_library_ids);
  const result = widget.hmbNormalizeImageAssetState({
    ...current, thumbnail_busy: false, thumbnail_request: {}, thumbnail_revision: revision,
    thumbnail_result: { ...request, completed_asset_library_ids: [...wanted], failed_asset_library_ids: [] },
    assets: current.assets.map(asset => ({ ...asset,
      thumbnail_url: wanted.has(asset.asset_library_id) ? `https://fixture.invalid/${asset.asset_library_id}.webp` : asset.thumbnail_url,
    })),
  });
  container.__hmbImageAssetLatestState = result;
  widget.hmbClearImageAssetThumbnailWatchdog(container, request.request_id);
  delete container.__hmbImageAssetThumbnailPendingRequestId;
  return result;
}

try {
  assert.equal(widget.hmbScheduleImageAssetThumbnailRequest(container, state, {}), true);
  assert.equal(widget.hmbScheduleImageAssetThumbnailRequest(container, state, {}), true);
  assert.equal(requests.length, 0, "the first request must wait until after paint");
  flushPaint();
  assert.equal(requests.length, 1, "pre-paint scheduling coalesces");
  assert.equal(requests[0].asset_library_ids.length, 12, "first thumbnails must not wait for a 64-item decode batch");
  assert.deepEqual(requests[0].asset_library_ids, ["image-145", ...Array.from({ length: 11 }, (_, i) => `image-${i}`)]);
  assert.equal(requests[0].widget_runtime_lease, state.widget_runtime_lease);
  assert.equal(requests[0].scan_revision, 7);
  assert.equal(requests[0].project_cache_uid, state.project_cache_uid);
  assert.equal(state.ui_edit_revision, 9);
  assert.deepEqual(state.shot_routing, before.routing);
  assert.deepEqual(widget.hmbImageAssetSelectionSnapshot(state), before.selection);
  assert.equal(widget.hmbScheduleImageAssetThumbnailRequest(container, state, {}), false, "first batch remains single-flight");

  const ready = complete(state, requests[0], 1);
  assert.equal(ready.assets.filter(asset => asset.thumbnail_url).length, 12, "the first 12 are displayable independently");
  assert.equal(widget.hmbScheduleImageAssetThumbnailRequest(container, ready, {}), true);
  flushPaint();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].asset_library_ids.length, 64, "background hydration returns to the existing bounded throughput");
  assert.equal(requests[1].asset_library_ids.some(id => requests[0].asset_library_ids.includes(id)), false);

  const next = widget.hmbNormalizeImageAssetState({ ...ready,
    project_uid: "second-project", project_cache_uid: "hmbpc1:" + "2".repeat(32), manifest_signature: "second-manifest",
    thumbnail_busy: false, thumbnail_request: {}, thumbnail_result: {},
    assets: ready.assets.map(asset => ({ ...asset, thumbnail_url: "", media_signature: "second-" + asset.media_signature })),
  });
  container.__hmbImageAssetLatestState = next;
  assert.equal(widget.hmbScheduleImageAssetThumbnailRequest(container, next, {}), true);
  flushPaint();
  assert.equal(requests.length, 3);
  assert.equal(requests[2].asset_library_ids.length, 12, "each changed project gets a new first-paint batch");
  assert.equal(requests[2].project_cache_uid, next.project_cache_uid);
  const stale = widget.hmbMergeImageAssetThumbnailResponse(next, ready, requests[2].request_id);
  assert.equal(stale.assets.some(asset => asset.thumbnail_url), false, "late old-project pixels cannot hydrate the new source");
  assert.deepEqual(next.shot_routing, before.routing);
  assert.equal(next.ui_edit_revision, 9);
  console.log("HMB_IMAGEASSET_FIRST_PAINT_WIDGET=PASS (12 first, 64 continuation, signed scope, coalescing, source switch, stale result)");
} finally {
  widget.hmbClearImageAssetThumbnailWatchdog(container);
  registry.delete(state.shot_routing.publisher_instance_uuid);
  if (original.raf === undefined) delete globalThis.requestAnimationFrame;
  else globalThis.requestAnimationFrame = original.raf;
  globalThis.setTimeout = original.set;
  globalThis.clearTimeout = original.clear;
}
