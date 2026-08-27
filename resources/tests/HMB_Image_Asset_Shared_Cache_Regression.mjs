import assert from "node:assert/strict";

const widget = await import(new URL(
  "../../widgets/HMBImageAssetLibraryWidget.js",
  import.meta.url,
));
const bridgeWidget = await import(new URL(
  "../../widgets/HMBImageAssetThumbnailPatchBridgeWidget.js",
  import.meta.url,
));

const asset = (id, signature, extra = {}) => ({
  asset_library_id: id,
  source_uid: `project:${id}`,
  source_kind: "project",
  registered: true,
  relative_path: `Characters/${id}.png`,
  media_signature: signature,
  image_name: id,
  asset_id: id,
  ...extra,
});

const presentation = widget.hmbImageAssetPresentationCacheRegistry();
presentation.clear();
const warm = widget.hmbNormalizeImageAssetState({
  project_uid: "shared-project",
  project_cache_uid: "hmbpc1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  project_root: "D:/show/shared-project",
  manifest_signature: "manifest-a",
  assets: [asset("hero", "same-media", {
    thumbnail_url: "http://127.0.0.1/workspace/static_files/hero.webp",
  })],
});
assert.equal(widget.hmbRememberImageAssetPresentation(warm), 1);

const recreated = widget.hmbNormalizeImageAssetState({
  project_uid: "shared-project",
  project_cache_uid: "hmbpc1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  project_root: "V:/moved/shared-project",
  manifest_signature: "manifest-b",
  assets: [asset("hero", "same-media", { selected: true, selection_order: 1 })],
});
const recreatedRuntime = recreated.shot_routing.publisher_instance_uuid;
assert.deepEqual(widget.hmbAdoptImageAssetPresentation(recreated), ["hero"]);
assert.equal(
  recreated.assets[0].thumbnail_url,
  "http://127.0.0.1/workspace/static_files/hero.webp",
  "A recreated node and moved drive must reuse the project presentation URL.",
);
assert.equal(recreated.assets[0].selected, true, "Shared presentation must not own Shot selection.");
assert.equal(
  recreated.shot_routing.publisher_instance_uuid,
  recreatedRuntime,
  "Presentation adoption must not replace workflow-local routing identity.",
);

const changedMedia = widget.hmbNormalizeImageAssetState({
  project_uid: "shared-project",
  project_cache_uid: "hmbpc1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  project_root: "V:/moved/shared-project",
  manifest_signature: "manifest-c",
  assets: [asset("hero", "changed-media")],
});
assert.deepEqual(widget.hmbAdoptImageAssetPresentation(changedMedia), []);
assert.equal(changedMedia.assets[0].thumbnail_url, "");

const unrelatedSameName = widget.hmbNormalizeImageAssetState({
  project_uid: "shared-project",
  project_cache_uid: "hmbpc1:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  project_root: "W:/another/shared-project",
  manifest_signature: "manifest-a",
  assets: [asset("hero", "same-media")],
});
assert.deepEqual(widget.hmbAdoptImageAssetPresentation(unrelatedSameName), []);
assert.equal(
  unrelatedSameName.assets[0].thumbnail_url,
  "",
  "Independent same-name projects must not share presentation thumbnails.",
);

const folderCatalog = widget.hmbNormalizeImageAssetState({
  project_uid: "folder-project",
  project_cache_uid: "hmbpc1:cccccccccccccccccccccccccccccccc",
  project_root: "V:/folder-project",
  manifest_signature: "folder-manifest",
  selected_folder_path: "Characters",
  assets: Array.from({ length: 130 }, (_, index) => asset(
    `catalog-${index}`,
    `signature-${index}`,
    { relative_path: `${index < 3 ? "Characters" : "Backgrounds"}/catalog-${index}.png` },
  )),
});
const eagerIds = widget.hmbImageAssetThumbnailRequestIds(folderCatalog);
assert.equal(eagerIds.length, 64, "One eager batch must remain bounded to 64 thumbnails.");
assert.equal(
  eagerIds.includes("catalog-63"),
  true,
  "The first batch must continue beyond the currently selected folder.",
);

const bridgeRegistry = bridgeWidget.hmbImageAssetThumbnailPatchBridgeRegistry();
bridgeRegistry.clear();
const runtimeId = folderCatalog.shot_routing.publisher_instance_uuid;
const bridgePublished = [];
const catalogResults = [];
bridgeRegistry.set(runtimeId, {
  catalogConsumer(value) { catalogResults.push(value); },
  catalogConsumerToken: "catalog-test",
});
const bridgeContainer = {
  style: { setProperty() {} },
  setAttribute() {},
};
const bridge = bridgeWidget.default(bridgeContainer, {
  value: { runtime_instance_id: runtimeId },
  onChange(value) { bridgePublished.push(value); },
});
bridgeRegistry.get(runtimeId).dispatch({
  schema: "hmb-image-asset-thumbnail-bridge",
  version: 1,
  operation: "catalog_probe",
  phase: "request",
  request_id: "catalog-probe-1",
  runtime_instance_id: runtimeId,
  project_uid: "folder-project",
  project_cache_uid: folderCatalog.project_cache_uid,
  project_root: "V:/folder-project",
  manifest_signature: "folder-manifest",
  scan_revision: folderCatalog.scan_revision,
  probe_kind: "manifest",
});
assert.equal(bridgePublished[0].operation, "catalog_probe");
assert.equal(bridgePublished[0].project_cache_uid, folderCatalog.project_cache_uid);
assert.equal(bridgePublished[0].project_root, "V:/folder-project");
const catalogResult = {
  ...bridgePublished[0],
  phase: "result",
  outcome: "no_change",
};
bridge.update({ value: catalogResult, onChange() {} });
assert.deepEqual(catalogResults, [catalogResult]);
bridge.cleanup();
bridgeRegistry.clear();

const savedSetTimeout = globalThis.setTimeout;
const savedClearTimeout = globalThis.clearTimeout;
const savedDocument = globalThis.document;
const timers = new Map();
let timerSequence = 0;
const visibilityListeners = new Set();
globalThis.setTimeout = (callback, delay = 0) => {
  const id = ++timerSequence;
  timers.set(id, { callback, delay: Number(delay) || 0 });
  return id;
};
globalThis.clearTimeout = (id) => timers.delete(id);
globalThis.document = {
  hidden: false,
  visibilityState: "visible",
  addEventListener(name, callback) {
    if (name === "visibilitychange") visibilityListeners.add(callback);
  },
  removeEventListener(name, callback) {
    if (name === "visibilitychange") visibilityListeners.delete(callback);
  },
};
try {
  const pollState = widget.hmbNormalizeImageAssetState({
    project_uid: "poll-project",
    project_cache_uid: "hmbpc1:dddddddddddddddddddddddddddddddd",
    project_root: "V:/poll-project",
    manifest_signature: "poll-manifest",
    scan_revision: 4,
  });
  const pollRuntime = pollState.shot_routing.publisher_instance_uuid;
  const probes = [];
  bridgeRegistry.set(pollRuntime, { dispatch(value) { probes.push(value); } });
  const pollContainer = { __hmbImageAssetLatestState: pollState };
  assert.equal(widget.hmbStartImageAssetCatalogPolling(pollContainer, pollState), true);
  assert.deepEqual(
    [...timers.values()].map((timer) => timer.delay).sort((a, b) => a - b),
    [3000, 10000],
  );
  const manifestTimer = [...timers.entries()].find(([, timer]) => timer.delay === 3000);
  timers.delete(manifestTimer[0]);
  manifestTimer[1].callback();
  assert.equal(probes[0].operation, "catalog_probe");
  assert.equal(probes[0].probe_kind, "manifest");
  assert.equal(
    widget.hmbAcceptImageAssetCatalogProbeResult(pollContainer, pollState, {
      ...probes[0],
      phase: "result",
      outcome: "no_change",
    }),
    true,
  );
  globalThis.document.hidden = true;
  globalThis.document.visibilityState = "hidden";
  visibilityListeners.values().next().value();
  assert.deepEqual(
    [...timers.values()].map((timer) => timer.delay).sort((a, b) => a - b),
    [15000, 30000],
  );
  widget.hmbStopImageAssetCatalogPolling(pollContainer);
  assert.equal(timers.size, 0, "Unmount must release every adaptive polling timer.");
  assert.equal(visibilityListeners.size, 0, "Unmount must release the visibility listener.");
  bridgeRegistry.delete(pollRuntime);
} finally {
  globalThis.setTimeout = savedSetTimeout;
  globalThis.clearTimeout = savedClearTimeout;
  if (savedDocument === undefined) delete globalThis.document;
  else globalThis.document = savedDocument;
}

presentation.clear();
console.log("HMB ImageAsset shared cache + adaptive catalog probe regression: PASS");
