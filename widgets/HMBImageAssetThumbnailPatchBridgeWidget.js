// Hidden compact thumbnail request/result transport for HMBImageAssetLibrary.
// Persistent catalog and Shot authority remain owned by the main state widget.

const HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY =
  "__HMB_IMAGE_ASSET_THUMBNAIL_PATCH_BRIDGES_V1__";
const HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY =
  "__HMB_IMAGE_ASSET_PRESENTATION_CACHE_V1__";

function clean(value) {
  return String(value == null ? "" : value).trim();
}

function bridgeRegistry() {
  const root = typeof globalThis !== "undefined" ? globalThis : null;
  if (!root) return null;
  if (!(root[HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY] instanceof Map)) {
    root[HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY] = new Map();
  }
  return root[HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY];
}

function hasConsumers(entry) {
  return Boolean(
    typeof entry?.consumer === "function"
    || typeof entry?.catalogConsumer === "function"
    || (entry?.consumers instanceof Map && entry.consumers.size)
    || (entry?.catalogConsumers instanceof Map && entry.catalogConsumers.size)
    || (entry?.pageConsumers instanceof Map && entry.pageConsumers.size),
  );
}

function deliverToConsumers(entry, catalog, value) {
  const consumers = catalog ? entry?.catalogConsumers : entry?.consumers;
  const legacy = catalog ? entry?.catalogConsumer : entry?.consumer;
  const delivered = new Set();
  let firstError;
  let hasError = false;
  const deliver = (consumer) => {
    if (typeof consumer !== "function" || delivered.has(consumer)) return;
    delivered.add(consumer);
    try { consumer(value); } catch (error) {
      if (!hasError) { firstError = error; hasError = true; }
    }
  };
  deliver(legacy);
  if (consumers instanceof Map) {
    for (const [token, item] of Array.from(consumers.entries())) {
      if (consumers.get(token) !== item) continue;
      deliver(catalog ? item.consumer : item);
    }
  }
  if (hasError) throw firstError;
  return delivered.size > 0;
}

function wakeCatalogConsumers(entry) {
  const wakes = new Set();
  if (typeof entry?.catalogWake === "function") wakes.add(entry.catalogWake);
  if (entry?.catalogConsumers instanceof Map) {
    for (const item of entry.catalogConsumers.values()) {
      if (typeof item.wake === "function") wakes.add(item.wake);
    }
  }
  if (entry?.pageConsumers instanceof Map) {
    for (const item of entry.pageConsumers.values()) if (typeof item.wake === "function") wakes.add(item.wake);
  }
  for (const wake of wakes) {
    try { wake(); } catch (_error) {}
  }
}

function presentationRegistry() {
  const root = typeof globalThis !== "undefined" ? globalThis : null;
  if (!root) return null;
  if (!(root[HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY] instanceof Map)) {
    root[HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY] = new Map();
  }
  return root[HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY];
}

function rememberThumbnailResult(value) {
  const projectUid = clean(value?.project_cache_uid || value?.project_uid);
  if (!projectUid) return;
  const registry = presentationRegistry();
  let entry = registry?.get(projectUid);
  if (!entry) {
    entry = {
      key: projectUid,
      thumbnails: new Map(),
      requested: new Set(),
      failed: new Set(),
      errorRetries: new Map(),
      inflight: new Map(),
      touchedAt: Date.now(),
    };
  }
  (Array.isArray(value?.completed_assets) ? value.completed_assets : []).forEach((asset) => {
    const key = clean(asset?.asset_library_id);
    const thumbnailUrl = clean(asset?.thumbnail_url);
    if (!key || !thumbnailUrl) return;
    entry.thumbnails.set(key, {
      sourceUid: clean(asset?.source_uid),
      mediaSignature: clean(asset?.media_signature),
      relativePath: clean(asset?.relative_path).replaceAll("\\", "/"),
      thumbnailUrl,
    });
    entry.requested.delete(key);
    entry.failed.delete(key);
    entry.inflight.delete(key);
  });
  (Array.isArray(value?.failed_asset_library_ids)
    ? value.failed_asset_library_ids
    : []).map(clean).filter(Boolean).forEach((key) => {
    entry.requested.add(key);
    entry.failed.add(key);
    entry.inflight.delete(key);
  });
  entry.touchedAt = Date.now();
  registry?.delete(projectUid);
  registry?.set(projectUid, entry);
  while (registry && registry.size > 32) {
    const oldestKey = registry.keys().next().value;
    if (!oldestKey) break;
    registry.delete(oldestKey);
  }
}

export function hmbImageAssetThumbnailPatchBridgeRegistry() {
  return bridgeRegistry();
}

function makeContainerInert(container) {
  if (!container?.style) return;
  container.setAttribute?.("aria-hidden", "true");
  for (const [property, value] of [
    ["height", "0px"],
    ["min-height", "0px"],
    ["max-height", "0px"],
    ["margin", "0"],
    ["padding", "0"],
    ["border", "0"],
    ["overflow", "hidden"],
    ["opacity", "0"],
    ["pointer-events", "none"],
  ]) container.style.setProperty?.(property, value, "important");
}

function bridgeValue(props) {
  const value = props?.value;
  return value && typeof value === "object" ? value : {};
}

export default function HMBImageAssetThumbnailPatchBridgeWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  container.__hmbImageAssetThumbnailBridgeCleanup?.();
  makeContainerInert(container);

  let latestProps = props || {};
  let runtimeId = "";
  let deliveredResultKey = "";
  const token = `hmb-image-thumbnail-bridge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const registry = bridgeRegistry();

  const dispatch = (rawRequest) => {
    if (typeof latestProps?.onChange !== "function") {
      throw new Error("HMB image thumbnail bridge did not receive props.onChange.");
    }
    const source = rawRequest && typeof rawRequest === "object" ? rawRequest : {};
    const operation = ["catalog_probe", "catalog_page"].includes(clean(source.operation))
      ? clean(source.operation) : "hydrate";
    const request = {
      schema: "hmb-image-asset-thumbnail-bridge",
      version: 1,
      operation,
      phase: "request",
      runtime_instance_id: clean(source.runtime_instance_id),
      request_id: clean(source.request_id),
      project_uid: clean(source.project_uid),
      manifest_signature: clean(source.manifest_signature),
      scan_revision: Math.max(0, Math.floor(Number(source.scan_revision) || 0)),
    };
    const projectCacheUid = clean(source.project_cache_uid);
    if (projectCacheUid) request.project_cache_uid = projectCacheUid;
    if (operation === "catalog_page") {
      Object.assign(request,{session_id:clean(source.session_id),sequence:Math.max(0,Math.floor(Number(source.sequence)||0)),
        query:String(source.query||"").slice(0,256),folder:clean(source.folder).replaceAll("\\","/"),
        folder_signature:clean(source.folder_signature),source_view:source.source_view==="user"?"user":"project",
        offset:Math.max(0,Math.floor(Number(source.offset)||0)),limit:Math.min(80,Math.max(1,Math.floor(Number(source.limit)||80)))});
      if(!request.session_id || !request.request_id || request.runtime_instance_id!==runtimeId || !request.project_uid)
        throw new Error("Invalid HMB image catalog page request.");
    } else if (operation === "catalog_probe") {
      request.project_root = clean(source.project_root).replaceAll("\\", "/");
      request.probe_kind = clean(source.probe_kind);
      if (
        !request.runtime_instance_id
        || request.runtime_instance_id !== runtimeId
        || !request.request_id
        || !request.project_uid
        || !request.project_root
        || !["manifest", "folder"].includes(request.probe_kind)
      ) throw new Error("Invalid HMB image catalog probe request.");
    } else {
      request.asset_library_ids = Array.from(new Set(
        (Array.isArray(source.asset_library_ids) ? source.asset_library_ids : [])
          .map(clean)
          .filter(Boolean),
      ));
      if (
        !request.runtime_instance_id
        || request.runtime_instance_id !== runtimeId
        || !request.request_id
        || !request.project_uid
        || !request.manifest_signature
        || !request.asset_library_ids.length
      ) throw new Error("Invalid HMB image thumbnail bridge request.");
    }
    return latestProps.onChange(request);
  };

  const deliverResult = (value) => {
    if (
      clean(value?.schema) !== "hmb-image-asset-thumbnail-bridge"
      || clean(value?.phase) !== "result"
      || clean(value?.runtime_instance_id) !== runtimeId
    ) return false;
    const operation = clean(value?.operation);
    if (operation !== "hydrate" && operation !== "catalog_probe" && operation !== "catalog_page") return false;
    const resultKey = `${operation}:${clean(value.request_id)}:${Math.max(0, Math.floor(Number(value.thumbnail_revision) || 0))}:${clean(value.outcome)}`;
    if (!resultKey || resultKey === deliveredResultKey) return false;
    const current = registry?.get(runtimeId) || {};
    if(operation==="catalog_page") {
      for(const item of current.pageConsumers?.values?.() || []) {
        try {item.consumer?.(value);} catch(_error) { /* Other mounted clients retain their own result. */ }
      }
      deliveredResultKey=resultKey;return true;
    }
    if (operation === "hydrate") rememberThumbnailResult(value);
    if (!deliverToConsumers(current, operation === "catalog_probe", value)) {
      // A result can race the main widget mount/remount. Retain one bounded
      // envelope; the consumer validates request/context/revision before use.
      const pendingKey = operation === "catalog_probe"
        ? "catalogPendingResult"
        : "pendingResult";
      registry?.set(runtimeId, { ...current, [pendingKey]: value });
      deliveredResultKey = resultKey;
      return false;
    }
    deliveredResultKey = resultKey;
    const pendingKey = operation === "catalog_probe"
        ? "catalogPendingResult"
        : "pendingResult";
    if (current[pendingKey]) {
      // A consumer may synchronously replace the bridge or enqueue a newer
      // envelope. Retire only the exact envelope on the current owner entry.
      const latest = registry?.get(runtimeId);
      if (latest?.[pendingKey] === current[pendingKey]) {
        const withoutPending = { ...latest };
        delete withoutPending[pendingKey];
        registry?.set(runtimeId, withoutPending);
      }
    }
    return true;
  };

  const register = (value) => {
    const nextRuntimeId = clean(value?.runtime_instance_id);
    if (runtimeId) {
      const prior = registry?.get(runtimeId);
      if (prior?.bridgeToken === token) {
        const {
          bridgeToken: _bridgeToken,
          dispatch: _dispatch,
          ...consumerEntry
        } = prior;
        if (hasConsumers(consumerEntry)) {
          registry.set(runtimeId, consumerEntry);
        }
        else registry.delete(runtimeId);
      }
    }
    runtimeId = nextRuntimeId;
    if (runtimeId && registry) {
      const prior = registry.get(runtimeId) || {};
      const entry={ ...prior, bridgeToken: token, dispatch, catalogPageVersion:Number(value?.catalog_page_version)||0 };
      registry.set(runtimeId, entry);
      wakeCatalogConsumers(entry);
    }
    deliverResult(value);
  };
  register(bridgeValue(latestProps));

  const cleanup = () => {
    const current = runtimeId ? registry?.get(runtimeId) : null;
    if (current?.bridgeToken === token) {
      const {
        bridgeToken: _bridgeToken,
        dispatch: _dispatch,
        ...consumerEntry
      } = current;
      if (hasConsumers(consumerEntry)) {
        registry.set(runtimeId, consumerEntry);
      } else registry.delete(runtimeId);
    }
    if (container.__hmbImageAssetThumbnailBridgeCleanup === cleanup) {
      delete container.__hmbImageAssetThumbnailBridgeCleanup;
    }
  };
  container.__hmbImageAssetThumbnailBridgeCleanup = cleanup;

  return {
    cleanup,
    update(nextProps) {
      latestProps = nextProps || {};
      register(bridgeValue(latestProps));
      makeContainerInert(container);
    },
  };
}
