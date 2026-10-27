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

function bridgeOwnerRank(container) {
  // This transport's own element is intentionally zero-height/transparent.
  // Rank its native host instead, so a measurement/footer clone cannot replace
  // a still-mounted interactive row solely because it mounted last.
  if (container?.isConnected === false) return null;
  const view = container?.ownerDocument?.defaultView;
  let rank = 0;
  for (let element = container?.parentElement, depth = 0; element && depth < 32; element = element.parentElement, depth += 1) {
    const style = view?.getComputedStyle?.(element) || element.style || {};
    if (element.hidden || style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") rank -= 100;
    const ownHiddenRow = element.getAttribute?.("data-parameter-name") === "HMB_IMAGE_ASSET_THUMBNAIL_PATCH";
    if (!ownHiddenRow && style.opacity !== "" && style.opacity != null && Number(style.opacity) === 0) rank -= 50;
    if (element.matches?.(".react-flow__node")) break;
  }
  return rank;
}

function bridgeLiveOwner(owners) {
  let chosen = null, chosenRank = -Infinity;
  for (const owner of owners.values()) {
    if (!owner.live()) continue;
    const rank = bridgeOwnerRank(owner.container);
    // Equal ranks retain the previous last-writer behavior. Real visible
    // native rows win over later hidden measurement/footer copies.
    if (rank !== null && rank >= chosenRank) { chosen = owner; chosenRank = rank; }
  }
  return chosen;
}

function publishBridgeOwners(registry, runtimeId, owners) {
  const prior = registry?.get(runtimeId) || {};
  const owner = bridgeLiveOwner(owners);
  if (owner) {
    const entry = { ...prior, bridgeOwners: owners, bridgeToken: owner.token,
      catalogPageVersion: owner.catalogPageVersion,
      dispatch(request) {
        const current = registry?.get(runtimeId);
        if (current?.bridgeOwners !== owners) throw new Error("This image bridge is no longer mounted.");
        const live = bridgeLiveOwner(owners);
        if (!live) throw new Error("This image bridge has no mounted owner.");
        return live.dispatch(request);
      } };
    registry?.set(runtimeId, entry);
    return entry;
  }
  const { bridgeOwners: _owners, bridgeToken: _token, dispatch: _dispatch, ...consumers } = prior;
  if (hasConsumers(consumers)) registry?.set(runtimeId, consumers);
  else registry?.delete(runtimeId);
  return null;
}

function hmbNativeUiImplementation(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  container.__hmbImageAssetThumbnailBridgeCleanup?.();
  makeContainerInert(container);

  let latestProps = props || {};
  let runtimeId = "";
  let disposed = false;
  let deliveredResultKey = "";
  const token = `hmb-image-thumbnail-bridge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const registry = bridgeRegistry();

  const dispatch = (rawRequest) => {
    if (disposed) throw new Error("This image bridge is no longer mounted.");
    if (typeof latestProps?.onChange !== "function") {
      throw new Error("HMB image thumbnail bridge did not receive props.onChange.");
    }
    const source = rawRequest && typeof rawRequest === "object" ? rawRequest : {};
    const operation = ["catalog_probe", "catalog_page", "cgt_catalog", "cgt_confirm", "cgt_cancel"].includes(clean(source.operation))
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
    if (operation.startsWith("cgt_")) {
      request.session_id = clean(source.session_id);
      request.project_identity = clean(source.project_identity);
      if (!request.session_id || !request.request_id || request.runtime_instance_id !== runtimeId
          || (operation === "cgt_confirm" && !request.project_identity)) throw new Error("Invalid CGT dialog request.");
      const cgtProjectId = clean(source.cgt_project_id);
      if (cgtProjectId) {
        if (!/^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$/.test(cgtProjectId)) throw new Error("Invalid CGT project identity.");
        request.cgt_project_id = cgtProjectId;
      }
      if (operation === "cgt_confirm") request.hierarchy_request = source.hierarchy_request;
    } else if (operation === "catalog_page") {
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
    if (!["hydrate", "catalog_probe", "catalog_page", "cgt_catalog", "cgt_confirm", "cgt_cancel"].includes(operation)) return false;
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
    if (runtimeId && runtimeId !== nextRuntimeId) {
      const owners = registry?.get(runtimeId)?.bridgeOwners;
      if (owners instanceof Map) { owners.delete(token); publishBridgeOwners(registry, runtimeId, owners); }
    }
    runtimeId = nextRuntimeId;
    if (runtimeId && registry) {
      const prior = registry.get(runtimeId) || {};
      const owners = prior.bridgeOwners instanceof Map ? prior.bridgeOwners : new Map();
      owners.delete(token);
      owners.set(token, { token, container, dispatch, live: () => !disposed,
        catalogPageVersion: Number(value?.catalog_page_version) || 0 });
      const entry = publishBridgeOwners(registry, runtimeId, owners);
      if (entry) wakeCatalogConsumers(entry);
    }
    deliverResult(value);
  };
  register(bridgeValue(latestProps));

  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    const owners = runtimeId ? registry?.get(runtimeId)?.bridgeOwners : null;
    if (owners instanceof Map && owners.delete(token)) {
      // Teardown restores transport ownership without scheduling fresh work.
      // The surviving visible consumer keeps its existing cadence/requests.
      publishBridgeOwners(registry, runtimeId, owners);
    }
    if (container.__hmbImageAssetThumbnailBridgeCleanup === cleanup) {
      delete container.__hmbImageAssetThumbnailBridgeCleanup;
    }
  };
  container.__hmbImageAssetThumbnailBridgeCleanup = cleanup;

  return {
    cleanup,
    update(nextProps) {
      if (disposed) return;
      latestProps = nextProps || {};
      register(bridgeValue(latestProps));
      makeContainerInert(container);
    },
  };
}


// HMB_NATIVE_DISABLED_ADAPTER_V1_BEGIN -- identical module-local adapter.
const HMB_NATIVE_UI_CALLBACKS = new WeakMap();
function hmbNativeUiReadCommand(value, kind) {
  let v = value;
  if (typeof v === "string") { try { v = JSON.parse(v); } catch { return false; } }
  if (!v || typeof v !== "object") return false;
  if (kind === "thumbnail") return v.schema === "hmb-image-asset-thumbnail-bridge"
    && ["hydrate", "catalog_probe", "catalog_page"].includes(v.operation);
  if (kind === "seedance") return (v.schema === "hmb-seedance-refresh-command"
    && ["refresh_existing", "cancel_draft_final", "open_gallery"].includes(v.action))
    || (v.schema === "hmb-seedance-render-preflight" && ["inspect", "cancel"].includes(v.action))
    || (v.schema === "hmb-seedance-shot-ui" && v.request?.action === "refresh_existing");
  if (kind === "agent") return v.schema === "hmb-agent-shot-row"
    && ["refresh", "cancel_selected"].includes(v.action?.kind);
  if (kind === "finish") return v.ui_transport?.schema === "hmb-finish-ui-transport"
    && v.ui_transport.operation === "refresh";
  if (kind === "lut") return (v.__hmb_color_lut_command__ || v).action === "cancel";
  const command = v.__hmb_picker_command__ || v;
  return ["picker", "picker-bridge"].includes(kind) && command.schema === "hmb-picker-command"
    && (["stop_read", "cancel_pending", "cancel_video_import"].includes(command.action)
      || (command.action === "video_tools" && command.payload?.op === "cancel"));
}
function hmbNativeUiContract(container, props, mount, policy) {
  if (!container) return mount(container, props);
  let c = container.__hmbNativeUiContract;
  if (c && c.kind !== policy.kind) { c.proxy.cleanup(); c = null; }
  if (!c) {
    c = { kind: policy.kind, active: true, props: {}, handle: null, originals: new Map(), observer: null, listening: false };
    const events = ["pointerdown", "mousedown", "click", "dblclick", "keydown", "beforeinput", "input", "change", "paste", "drop", "dragstart", "submit"];
    c.allowed = target => Boolean(target?.matches?.("video,audio")) || Boolean(policy.allowControl?.(target, c.props, container));
    c.guard = event => {
      if (!c.active || !c.props.disabled || c.allowed(event.target)) return;
      event.preventDefault?.(); event.stopImmediatePropagation?.(); event.stopPropagation?.();
    };
    c.restore = () => {
      c.observer?.disconnect?.();
      if (c.listening) { for (const name of events) container.removeEventListener?.(name, c.guard, true); c.listening = false; }
      for (const [el, old] of c.originals) {
        if ("disabled" in el && el.disabled !== old.disabled) el.disabled = old.disabled;
        if (old.editable !== null && el.getAttribute?.("contenteditable") !== old.editable) el.setAttribute?.("contenteditable", old.editable);
      }
      c.originals.clear();
    };
    c.sync = () => {
      // The normal enabled path adds no observers, DOM queries/writes or timers.
      if (!c.active || !c.props.disabled) return;
      if (!c.listening) { for (const name of events) container.addEventListener?.(name, c.guard, true); c.listening = true; }
      for (const [el] of c.originals) if (container.contains && !container.contains(el)) c.originals.delete(el);
      for (const el of container.querySelectorAll?.("button,input,select,textarea,[contenteditable='true']") || []) {
        if (c.allowed(el)) continue;
        if (!c.originals.has(el)) c.originals.set(el, { disabled: Boolean(el.disabled), editable: el.getAttribute?.("contenteditable") ?? null });
        if ("disabled" in el && !el.disabled) el.disabled = true;
        if (el.getAttribute?.("contenteditable") === "true") el.setAttribute?.("contenteditable", "false");
      }
      if (!c.observer) {
        const Observer = container.ownerDocument?.defaultView?.MutationObserver;
        if (Observer) c.observer = new Observer(() => c.sync());
      }
      c.observer?.observe?.(container, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "contenteditable"] });
    };
    c.wrap = () => {
      const p = { ...c.props };
      for (const name of ["onChange", "onCommand"]) if (typeof p[name] === "function") {
        const callback = HMB_NATIVE_UI_CALLBACKS.get(p[name]) || p[name];
        const fn = (...args) => {
          if (!c.active) throw new Error("This widget is no longer mounted.");
          if (c.props.disabled && !hmbNativeUiReadCommand(args[0], c.kind)) throw new Error("This control is disabled by Griptape.");
          return callback?.(...args);
        };
        HMB_NATIVE_UI_CALLBACKS.set(fn, HMB_NATIVE_UI_CALLBACKS.get(p[name]) || p[name]); p[name] = fn;
      }
      return p;
    };
    c.proxy = {
      update(nextProps) {
        if (!c.active || c.closing) return;
        c.restore(); c.props = nextProps || {}; const next = c.wrap();
        if (typeof c.handle?.update === "function") c.handle.update(next);
        else c.handle = mount(container, next);
        c.sync();
      },
      cleanup() {
        if (!c.active || c.closing) return; c.closing = true; c.restore();
        try {
          // Preserve the implementation's synchronous final authored-value flush.
          if (typeof c.handle === "function") c.handle(); else c.handle?.cleanup?.();
        } finally {
          c.active = false;
          if (container.__hmbNativeUiContract === c) delete container.__hmbNativeUiContract;
        }
      },
    };
    container.__hmbNativeUiContract = c;
  }
  c.restore(); c.props = props || c.props || {}; c.handle = mount(container, c.wrap()); c.sync(); return c.proxy;
}
// HMB_NATIVE_DISABLED_ADAPTER_V1_END

export default function HMBImageAssetThumbnailPatchBridgeWidget(container, props) {
  return hmbNativeUiContract(container, props, hmbNativeUiImplementation, { kind: "thumbnail", allowControl: null });
}
