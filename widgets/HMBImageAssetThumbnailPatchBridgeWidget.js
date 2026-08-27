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
    const operation = clean(source.operation) === "catalog_probe"
      ? "catalog_probe"
      : "hydrate";
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
    if (operation === "catalog_probe") {
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
    if (operation !== "hydrate" && operation !== "catalog_probe") return false;
    const resultKey = `${operation}:${clean(value.request_id)}:${Math.max(0, Math.floor(Number(value.thumbnail_revision) || 0))}:${clean(value.outcome)}`;
    if (!resultKey || resultKey === deliveredResultKey) return false;
    const current = registry?.get(runtimeId) || {};
    if (operation === "hydrate") rememberThumbnailResult(value);
    const consumer = operation === "catalog_probe"
      ? current.catalogConsumer
      : current.consumer;
    if (typeof consumer !== "function") {
      // A result can race the main widget mount/remount. Retain one bounded
      // envelope; the consumer validates request/context/revision before use.
      const pendingKey = operation === "catalog_probe"
        ? "catalogPendingResult"
        : "pendingResult";
      registry?.set(runtimeId, { ...current, [pendingKey]: value });
      deliveredResultKey = resultKey;
      return false;
    }
    consumer(value);
    deliveredResultKey = resultKey;
    const pendingKey = operation === "catalog_probe"
        ? "catalogPendingResult"
        : "pendingResult";
    if (current[pendingKey]) {
      const withoutPending = { ...current };
      delete withoutPending[pendingKey];
      registry?.set(runtimeId, withoutPending);
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
        if (consumerEntry.consumer || consumerEntry.catalogConsumer) {
          registry.set(runtimeId, consumerEntry);
        }
        else registry.delete(runtimeId);
      }
    }
    runtimeId = nextRuntimeId;
    if (runtimeId && registry) {
      const prior = registry.get(runtimeId) || {};
      registry.set(runtimeId, { ...prior, bridgeToken: token, dispatch });
      try { prior.catalogWake?.(); } catch (_error) {}
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
      if (consumerEntry.consumer || consumerEntry.catalogConsumer) {
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
