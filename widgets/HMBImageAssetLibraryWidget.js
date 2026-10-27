export function hmbScopeWidgetCss(cssText, rootSelector) {
  const css = String(cssText || "");
  const root = String(rootSelector || "").trim();
  if (!root) return css;
  const rootToken = new RegExp(`${root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w-])`);
  const matchingBrace = (start) => {
    let depth = 0; let quote = ""; let comment = false;
    for (let index = start; index < css.length; index += 1) {
      const char = css[index]; const next = css[index + 1];
      if (comment) { if (char === "*" && next === "/") { comment = false; index += 1; } continue; }
      if (quote) { if (char === "\\") index += 1; else if (char === quote) quote = ""; continue; }
      if (char === "/" && next === "*") { comment = true; index += 1; continue; }
      if (char === "\"" || char === "'") { quote = char; continue; }
      if (char === "{") depth += 1; else if (char === "}" && --depth === 0) return index;
    }
    return css.length - 1;
  };
  const scopeRange = (start, end) => {
    let output = ""; let cursor = start;
    while (cursor < end) {
      const open = css.indexOf("{", cursor);
      if (open < 0 || open >= end) { output += css.slice(cursor, end); break; }
      const close = matchingBrace(open);
      if (close >= end) { output += css.slice(cursor, end); break; }
      const header = css.slice(cursor, open); const trimmed = header.trim();
      if (trimmed.startsWith("@")) {
        const nested = /^@(media|container|supports|layer|document)\b/i.test(trimmed);
        output += `${header}{${nested ? scopeRange(open + 1, close) : css.slice(open + 1, close)}}`;
      } else {
        const leading = header.match(/^\s*/)?.[0] || "";
        const selectors = trimmed.split(",").map((selector) => {
          const cleanSelector = selector.trim();
          if (!cleanSelector) return cleanSelector;
          if (rootToken.test(cleanSelector) || cleanSelector.includes(":root")) return cleanSelector.replaceAll(":root", root);
          return `${root} ${cleanSelector}`;
        }).join(",");
        output += `${leading}${selectors}{${css.slice(open + 1, close)}}`;
      }
      cursor = close + 1;
    }
    return output;
  };
  return scopeRange(0, css.length);
}

export function hmbScopeWidgetStyleMarkup(markup, rootSelector) {
  return String(markup || "").replace(/<style>([\s\S]*?)<\/style>/g, (_match, css) => `<style>${hmbScopeWidgetCss(css, rootSelector)}</style>`);
}
const MAX_SELECTED_IMAGES = 50;
const MAX_IMAGE_ASSET_SHOTS = 5;
const MAX_SHOT_IMAGES = MAX_SELECTED_IMAGES;
const HMB_IMAGE_ASSET_SHOT_PALETTE = Object.freeze([
  Object.freeze({ number: 1, accent: "#F472B6", rgb: "244,114,182" }),
  Object.freeze({ number: 2, accent: "#3B82F6", rgb: "59,130,246" }),
  Object.freeze({ number: 3, accent: "#10B981", rgb: "16,185,129" }),
  Object.freeze({ number: 4, accent: "#8B5CF6", rgb: "139,92,246" }),
  Object.freeze({ number: 5, accent: "#EAB308", rgb: "234,179,8" }),
]);
const SHOT_ROUTING_SCHEMA = "hmb-shot-routing";
const SHOT_ROUTING_VERSION = 1;
const SHOT_HIERARCHY_SCHEMA = "hmb-shot-hierarchy";
const SHOT_HIERARCHY_EDIT_SCHEMA = "hmb-shot-hierarchy-edit";
const MAX_IMAGE_ASSET_REVISION = Number.MAX_SAFE_INTEGER;
const IMAGE_ASSET_UI_EDIT_REVISION_KEY = "ui_edit_revision";
const IMAGE_ASSET_EDIT_SCHEMA = "hmb-image-asset-edit-v1";
const IMAGE_BASH_WORKSPACE_EDIT_SCHEMA = "hmb-image-bash-workspace-edit-v1";
const ROOT_FOLDER_KEY = "$root";
const IMAGE_ASSET_STATE_VERSION = 4;
const IMAGE_TAXONOMY_SCHEMA = "hmb-image-taxonomy";
const IMAGE_TAXONOMY_VERSION = 3;
const IMAGE_ASSET_SELECTION_COMMIT_FALLBACK_MS = 120;
const IMAGE_ASSET_ECHO_EXPIRY_MS = 1500;
// Search covers the complete in-memory catalog, but foreground DOM work stays
// bounded for projects containing thousands of images.
const IMAGE_ASSET_RENDER_WINDOW = 80;
const IMAGE_ASSET_THUMBNAIL_REQUEST_BATCH = 64;
const IMAGE_ASSET_THUMBNAIL_ERROR_RETRY_LIMIT = 1;
const IMAGE_ASSET_THUMBNAIL_WATCHDOG_MS = 15000;
const IMAGE_ASSET_THUMBNAIL_WATCHDOG_RETRIES = 1;
const IMAGE_ASSET_SEARCH_DEBOUNCE_MS = 72;
const HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY =
  "__HMB_IMAGE_ASSET_THUMBNAIL_PATCH_BRIDGES_V1__";
const HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY =
  "__HMB_IMAGE_ASSET_PRESENTATION_CACHE_V1__";
const HMB_IMAGE_ASSET_PRESENTATION_CACHE_LIMIT = 32;
const IMAGE_ASSET_CATALOG_PROBE_ACTIVE_MS = Object.freeze({
  manifest: 3000,
  folder: 10000,
});
const IMAGE_ASSET_CATALOG_PROBE_BACKGROUND_MS = Object.freeze({
  manifest: 15000,
  folder: 30000,
});
let imageAssetWidgetMountSequence = 0;
const imageAssetMountedContainers = new Set();
const imageAssetCompactNodeKeys = new Set();
const imageAssetNativeResizeLocks = new WeakMap();
const imageAssetImportHandleDecorations = new WeakMap();
let imageAssetSelectionCommitSequence = 0;
let imageAssetPublicationSequence = 0;
let imageAssetAuthoritySequence = 0;
const IMAGE_ASSET_TRANSPORT_RETRY_MS = 32;
const IMAGE_ASSET_AUTHORITY_STAMP = Symbol("hmbImageAssetAuthorityStamp");
const IMAGE_ASSET_THUMBNAIL_FAILED_STAMP = Symbol("hmbImageAssetThumbnailFailed");

function imageAssetThumbnailBridgeRegistry() {
  const root = typeof globalThis !== "undefined" ? globalThis : null;
  if (!root) return null;
  if (!(root[HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY] instanceof Map)) {
    root[HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY] = new Map();
  }
  return root[HMB_IMAGE_ASSET_THUMBNAIL_BRIDGE_REGISTRY_KEY];
}

function imageAssetPresentationCacheRegistry() {
  const root = typeof globalThis !== "undefined" ? globalThis : null;
  if (!root) return null;
  if (!(root[HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY] instanceof Map)) {
    root[HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY] = new Map();
  }
  return root[HMB_IMAGE_ASSET_PRESENTATION_CACHE_KEY];
}

export function hmbImageAssetPresentationCacheKey(state) {
  const projectUid = clean(state?.project_cache_uid || state?.project_uid);
  if (!projectUid) return "";
  // The project UUID is location- and manifest-revision-independent. Per-asset
  // media signatures below invalidate only changed files after a teammate Add,
  // instead of discarding every unchanged thumbnail in the project.
  return projectUid;
}

function imageAssetPresentationCacheEntry(state, create = true) {
  const key = hmbImageAssetPresentationCacheKey(state);
  const registry = imageAssetPresentationCacheRegistry();
  if (!key || !registry) return null;
  let entry = registry.get(key);
  if (!entry && create) {
    entry = {
      key,
      thumbnails: new Map(),
      requested: new Set(),
      failed: new Set(),
      errorRetries: new Map(),
      inflight: new Map(),
      touchedAt: Date.now(),
    };
    registry.set(key, entry);
  }
  if (entry) {
    entry.touchedAt = Date.now();
    // A process-level LRU keeps node deletion/recreation fast without letting
    // unrelated projects accumulate for the lifetime of a long Griptape run.
    registry.delete(key);
    registry.set(key, entry);
  }
  while (registry.size > HMB_IMAGE_ASSET_PRESENTATION_CACHE_LIMIT) {
    const oldestKey = registry.keys().next().value;
    if (!oldestKey) break;
    registry.delete(oldestKey);
  }
  return entry;
}

function imageAssetPresentationIdentity(asset) {
  return {
    sourceUid: clean(asset?.source_uid),
    mediaSignature: clean(asset?.media_signature),
    relativePath: clean(asset?.relative_path).replaceAll("\\", "/"),
  };
}

function imageAssetPresentationIdentityMatches(cached, asset) {
  if (!cached || !asset) return false;
  const identity = imageAssetPresentationIdentity(asset);
  if (cached.sourceUid && identity.sourceUid && cached.sourceUid !== identity.sourceUid) {
    return false;
  }
  if (
    cached.mediaSignature
    && identity.mediaSignature
    && cached.mediaSignature !== identity.mediaSignature
  ) return false;
  return Boolean(
    (cached.mediaSignature && identity.mediaSignature)
    || (cached.relativePath && cached.relativePath === identity.relativePath),
  );
}

export function hmbRememberImageAssetPresentation(state, changedAssets = null) {
  const entry = imageAssetPresentationCacheEntry(state, true);
  if (!entry || !Array.isArray(state?.assets)) return 0;
  let remembered = 0;
  (Array.isArray(changedAssets) ? changedAssets : state.assets).forEach((asset) => {
    const key = clean(asset?.asset_library_id);
    const thumbnailUrl = clean(asset?.thumbnail_url);
    const persistedProjectAsset = Number(asset?.import_index || 0) === 0
      && Boolean(clean(asset?.relative_path));
    if (!key || !thumbnailUrl || !persistedProjectAsset) return;
    entry.thumbnails.set(key, {
      ...imageAssetPresentationIdentity(asset),
      thumbnailUrl,
    });
    entry.failed.delete(key);
    entry.requested.delete(key);
    entry.inflight.delete(key);
    remembered += 1;
  });
  return remembered;
}

export function hmbAdoptImageAssetPresentation(state) {
  const entry = imageAssetPresentationCacheEntry(state, false);
  if (!entry || !Array.isArray(state?.assets)) return [];
  const adopted = [];
  state.assets.forEach((asset) => {
    const key = clean(asset?.asset_library_id);
    if (!key || imageSource(asset)) return;
    const cached = entry.thumbnails.get(key);
    if (!imageAssetPresentationIdentityMatches(cached, asset)) {
      if (cached) {
        entry.thumbnails.delete(key);
        entry.requested.delete(key);
        entry.failed.delete(key);
        entry.errorRetries.delete(key);
        entry.inflight.delete(key);
      }
      return;
    }
    asset.thumbnail_url = cached.thumbnailUrl;
    entry.requested.delete(key);
    entry.failed.delete(key);
    entry.inflight.delete(key);
    adopted.push(key);
  });
  return adopted;
}

export function hmbImageAssetPresentationCacheRegistry() {
  return imageAssetPresentationCacheRegistry();
}

function hmbImageAssetBridgeHasConsumers(entry) {
  return Boolean(
    typeof entry?.consumer === "function"
    || typeof entry?.catalogConsumer === "function"
    || (entry?.consumers instanceof Map && entry.consumers.size)
    || (entry?.catalogConsumers instanceof Map && entry.catalogConsumers.size)
    || (entry?.pageConsumers instanceof Map && entry.pageConsumers.size),
  );
}

function hmbDeliverImageAssetBridgeConsumers(entry, catalog, value) {
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
      // Another consumer can synchronously unmount a sibling while receiving
      // the same result. Never call a removed mount from the copied iteration.
      if (consumers.get(token) !== item) continue;
      deliver(catalog ? item.consumer : item);
    }
  }
  if (hasError) throw firstError;
}

function hmbUnregisterImageAssetThumbnailConsumer(container) {
  const registry = imageAssetThumbnailBridgeRegistry();
  const runtimeId = clean(container?.__hmbImageAssetThumbnailConsumerRuntimeId);
  const token = container?.__hmbImageAssetThumbnailConsumerToken;
  const current = runtimeId ? registry?.get(runtimeId) : null;
  if (current && token) {
    const bridge = { ...current };
    bridge.consumers?.delete?.(token);
    if (bridge.consumerToken === token) {
      delete bridge.consumer;
      delete bridge.consumerToken;
    }
    if (bridge.dispatch || hmbImageAssetBridgeHasConsumers(bridge)) registry.set(runtimeId, bridge);
    else registry.delete(runtimeId);
  }
  delete container?.__hmbImageAssetThumbnailConsumerRuntimeId;
  delete container?.__hmbImageAssetThumbnailConsumerToken;
  delete container?.__hmbImageAssetThumbnailConsumer;
}

function hmbUnregisterImageAssetCatalogProbeConsumer(container) {
  const registry = imageAssetThumbnailBridgeRegistry();
  const runtimeId = clean(container?.__hmbImageAssetCatalogProbeRuntimeId);
  const token = container?.__hmbImageAssetCatalogProbeConsumerToken;
  const current = runtimeId ? registry?.get(runtimeId) : null;
  if (current && token) {
    const bridge = { ...current };
    bridge.catalogConsumers?.delete?.(token);
    if (bridge.catalogConsumerToken === token) {
      delete bridge.catalogConsumer;
      delete bridge.catalogConsumerToken;
      delete bridge.catalogWake;
    }
    if (bridge.dispatch || hmbImageAssetBridgeHasConsumers(bridge)) registry.set(runtimeId, bridge);
    else registry.delete(runtimeId);
  }
  delete container?.__hmbImageAssetCatalogProbeRuntimeId;
  delete container?.__hmbImageAssetCatalogProbeConsumerToken;
  delete container?.__hmbImageAssetCatalogProbeConsumer;
}

function hmbRegisterImageAssetCatalogProbeConsumer(
  container,
  state,
  consumer,
  wake,
) {
  if (!container || typeof consumer !== "function") return false;
  const runtimeId = imageAssetThumbnailRuntimeId(state);
  if (!runtimeId) {
    hmbUnregisterImageAssetCatalogProbeConsumer(container);
    return false;
  }
  if (
    container.__hmbImageAssetCatalogProbeRuntimeId === runtimeId
    && container.__hmbImageAssetCatalogProbeConsumer === consumer
    && imageAssetThumbnailBridgeRegistry()?.get(runtimeId)?.catalogConsumers
      ?.get(container.__hmbImageAssetCatalogProbeConsumerToken)?.consumer === consumer
  ) return true;
  hmbUnregisterImageAssetCatalogProbeConsumer(container);
  const registry = imageAssetThumbnailBridgeRegistry();
  const token = `hmb-image-catalog-consumer-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const current = registry?.get(runtimeId) || {};
  const consumers = current.catalogConsumers instanceof Map ? current.catalogConsumers : new Map();
  consumers.set(token, { consumer, wake: typeof wake === "function" ? wake : null });
  registry?.set(runtimeId, {
    ...current,
    catalogConsumers: consumers,
  });
  container.__hmbImageAssetCatalogProbeRuntimeId = runtimeId;
  container.__hmbImageAssetCatalogProbeConsumerToken = token;
  container.__hmbImageAssetCatalogProbeConsumer = consumer;
  if (current.catalogPendingResult) {
    const registered = registry?.get(runtimeId) || {};
    const { catalogPendingResult: _pending, ...withoutPending } = registered;
    registry?.set(runtimeId, withoutPending);
    hmbDeliverImageAssetBridgeConsumers(withoutPending, true, current.catalogPendingResult);
  }
  if (typeof current.dispatch === "function" && typeof wake === "function") wake();
  return true;
}

function hmbRegisterImageAssetThumbnailConsumer(container, state, consumer) {
  if (!container || typeof consumer !== "function") return false;
  const runtimeId = imageAssetThumbnailRuntimeId(state);
  if (!runtimeId) {
    hmbUnregisterImageAssetThumbnailConsumer(container);
    return false;
  }
  if (
    container.__hmbImageAssetThumbnailConsumerRuntimeId === runtimeId
    && container.__hmbImageAssetThumbnailConsumer === consumer
    && imageAssetThumbnailBridgeRegistry()?.get(runtimeId)?.consumers
      ?.get(container.__hmbImageAssetThumbnailConsumerToken) === consumer
  ) return true;
  hmbUnregisterImageAssetThumbnailConsumer(container);
  const registry = imageAssetThumbnailBridgeRegistry();
  const token = `hmb-image-thumbnail-consumer-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const current = registry?.get(runtimeId) || {};
  const consumers = current.consumers instanceof Map ? current.consumers : new Map();
  consumers.set(token, consumer);
  registry?.set(runtimeId, { ...current, consumers });
  container.__hmbImageAssetThumbnailConsumerRuntimeId = runtimeId;
  container.__hmbImageAssetThumbnailConsumerToken = token;
  container.__hmbImageAssetThumbnailConsumer = consumer;
  if (current.pendingResult) {
    // Consume at most once. The consumer performs exact runtime, pending
    // request, project, manifest, scan, media-signature, and revision checks.
    const registered = registry?.get(runtimeId) || {};
    const { pendingResult: _pendingResult, ...withoutPending } = registered;
    registry?.set(runtimeId, withoutPending);
    hmbDeliverImageAssetBridgeConsumers(withoutPending, false, current.pendingResult);
  }
  return true;
}
export function hmbImageAssetShotPalette(value = 1) {
  const number = Number.parseInt(value, 10);
  const index = Number.isInteger(number) && number >= 1 && number <= MAX_IMAGE_ASSET_SHOTS
    ? number - 1
    : 0;
  return HMB_IMAGE_ASSET_SHOT_PALETTE[index];
}

const IMAGE_ASSET_UI_TEXT = {
  en: {
    select_project: "Select Project",
    select_a_project: "Select a project",
    project: "PROJECT",
    reload_projects: "Reload projects",
    project_set: "PROJECT SET",
    registered: "REG",
    unregistered: "UNREG",
    selected: "SEL",
    project_root: "Project Root",
    project_folders: "PROJECT FOLDERS",
    ready: "READY",
    search_placeholder: "Search Image Name, Asset ID, path, Main Type, or Sub Type",
    no_match: "No image asset matches this project folder or search.",
    selected_images: "SELECTED IMAGES / GENERATOR ORDER",
    drag_hint: "Drag cards; Prompt image order updates automatically.",
    tray_empty: "Select a verified project asset or connect IMAGE_IMPORT_IN.",
    name_order_only: "Image + available metadata",
    external_image: "EXTERNAL IMAGE",
    verified_project_asset: "VERIFIED PROJECT ASSET",
    drag_reorder: "Drag to reorder",
    remove_selection: "Remove from selection",
    delete_shot: "Delete Shot",
    keep_one_shot: "At least one Shot must remain.",
    remove_external_selection: "Disconnect this external image from IMAGE_IMPORT_IN. Multi-image or ambiguous links must be removed at the input port.",
    disconnecting_external_import: "Disconnecting external image…",
    add: "Add",
    add_image_asset: "Add image asset",
    registered_project_asset: "Registered project asset",
    metadata_pending: "Raster metadata pending",
    register_before_select: "Register this image with Add before selecting it.",
    image_limit: `The ${MAX_SHOT_IMAGES}-image Shot limit has been reached.`,
    click_select: "Click the card to select or deselect this image.",
    project_state: "PROJECT",
    unregistered_state: "ADD",
    image_name: "Image Name",
    asset_id: "ASSET ID",
    main_type: "Main Type",
    unclassified: "Unclassified",
    sub_type: "Sub Type",
    sub_unassigned: "Sub Type candidate not assigned",
    hmb_project_asset: "HMB PROJECT ASSET",
    asset_passport: "ASSET PASSPORT",
    close_registration: "Close asset registration",
    final_image_name: "FINAL IMAGE NAME",
    main_type_label: "MAIN TYPE (REQUIRED)",
    select_main_type: "Select Main Type",
    custom_main_type: "CUSTOM MAIN TYPE",
    sub_type_label: "SUB TYPE (OPTIONAL)",
    taxonomy_contract: "AGENT MEANING",
    select_sub_type: "Select Sub Type",
    cancel: "Cancel",
    register_asset: "Register Asset",
    import_in: "IMAGE IMPORT IN",
    project_folder: "ASSET FOLDER",
    project_folder_locked: "Existing project assets keep their current folder.",
    project_folder_select: "Select the existing child Asset Folder where the external image will be copied.",
    select_project_folder: "Select Asset Folder",
    details_view: "Details view",
    image_only_view: "Image-only view",
    language: "Language",
    show_more: "Show more images",
    showing_images: "Showing",
    rename_shot: "Rename Shot",
    busy_loading: "Loading project assets…",
    transport_failed: "The change could not be saved. Please try again.",
    refresh_review: "Refresh review",
    refresh_files: "Image files",
    refresh_missing: "Registered paths without files",
    refresh_missing_hint: "These files may have been moved or renamed. Check the paths before removing their registrations.",
    refresh_unregistered: "Unregistered image files",
    refresh_unregistered_hint: "These files are not added automatically. Use Add to register them.",
    refresh_none: "None",
    refresh_cleanup: "Clean registrations without files",
    refresh_confirm: "Confirm cleanup",
    refresh_confirm_hint: "Only the missing registrations in JSON metadata will be removed. Media files are unaffected. A backup is created before cleanup. Existing Shots are not edited.",
    refresh_cleaning: "Cleaning registrations…",
    refresh_cleaned: "Registrations cleaned",
    refresh_backup: "Backup",
    refresh_unsafe: "Cleanup is unavailable for this review. Check the error and refresh again.",
    refresh_close: "Close refresh review",
    close: "Close",
  },
  ko: {
    select_project: "프로젝트 선택",
    select_a_project: "프로젝트를 선택하세요",
    project: "프로젝트",
    reload_projects: "프로젝트 새로고침",
    project_set: "프로젝트 설정",
    registered: "등록",
    unregistered: "미등록",
    selected: "선택",
    project_root: "프로젝트 루트",
    project_folders: "프로젝트 폴더",
    ready: "준비됨",
    search_placeholder: "이미지 이름, 에셋 ID, 경로, 주요 유형 또는 세부 유형 검색",
    no_match: "이 프로젝트 폴더 또는 검색 조건에 맞는 이미지 에셋이 없습니다.",
    selected_images: "선택 이미지 / 생성기 순서",
    drag_hint: "카드를 드래그하면 프롬프트 이미지 순서가 자동으로 갱신됩니다.",
    tray_empty: "검증된 프로젝트 에셋을 선택하거나 IMAGE_IMPORT_IN을 연결하세요.",
    name_order_only: "이미지 + 사용 가능한 메타데이터",
    external_image: "외부 이미지",
    verified_project_asset: "검증된 프로젝트 에셋",
    drag_reorder: "드래그하여 순서 변경",
    remove_selection: "선택에서 제거",
    delete_shot: "Shot 삭제",
    keep_one_shot: "Shot은 최소 1개가 필요합니다.",
    remove_external_selection: "이 외부 이미지를 IMAGE_IMPORT_IN에서 연결 해제합니다. 여러 이미지를 함께 전달하거나 연결이 모호하면 입력 포트에서 직접 해제하세요.",
    disconnecting_external_import: "외부 이미지 연결 해제 중…",
    add: "Add",
    add_image_asset: "이미지 에셋 추가",
    registered_project_asset: "등록된 프로젝트 에셋",
    metadata_pending: "래스터 메타데이터 확인 중",
    register_before_select: "선택하기 전에 추가 버튼으로 이 이미지를 등록하세요.",
    image_limit: `Shot마다 이미지는 최대 ${MAX_SHOT_IMAGES}개까지 선택할 수 있습니다.`,
    click_select: "카드를 클릭하여 이미지를 선택하거나 선택 해제합니다.",
    project_state: "프로젝트",
    unregistered_state: "ADD",
    image_name: "이미지 이름",
    asset_id: "에셋 ID",
    main_type: "주요 유형",
    unclassified: "미분류",
    sub_type: "세부 유형",
    sub_unassigned: "세부 유형 후보가 지정되지 않음",
    hmb_project_asset: "HMB 프로젝트 에셋",
    asset_passport: "에셋 등록 정보",
    close_registration: "에셋 등록 창 닫기",
    final_image_name: "최종 이미지 이름",
    main_type_label: "주요 유형 (필수)",
    select_main_type: "주요 유형 선택",
    custom_main_type: "사용자 지정 주요 유형 입력",
    sub_type_label: "세부 유형 (선택)",
    taxonomy_contract: "에이전트 적용 의미",
    select_sub_type: "세부 유형 선택",
    cancel: "취소",
    register_asset: "에셋 등록",
    import_in: "이미지 가져오기",
    project_folder: "에셋 폴더",
    project_folder_locked: "기존 프로젝트 에셋은 현재 폴더로 고정됩니다.",
    project_folder_select: "외부 이미지를 복사할 기존 하위 에셋 폴더를 선택하세요.",
    select_project_folder: "에셋 폴더 선택",
    details_view: "자세히 보기",
    image_only_view: "이미지만 보기",
    language: "언어",
    show_more: "이미지 더 보기",
    showing_images: "표시 중",
    rename_shot: "Shot 이름 변경",
    busy_loading: "프로젝트 에셋 불러오는 중…",
    transport_failed: "변경 사항을 저장하지 못했습니다. 다시 시도하세요.",
    refresh_review: "새로고침 검토",
    refresh_files: "이미지 파일",
    refresh_missing: "파일이 없는 등록 경로",
    refresh_missing_hint: "파일이 이동되었거나 이름이 바뀌었을 수 있습니다. 등록을 정리하기 전에 경로를 확인하세요.",
    refresh_unregistered: "미등록 이미지 파일",
    refresh_unregistered_hint: "자동으로 등록하지 않습니다. Add로 개별 등록하세요.",
    refresh_none: "없음",
    refresh_cleanup: "파일 없는 등록 정리",
    refresh_confirm: "정리 실행 확인",
    refresh_confirm_hint: "파일이 없는 등록의 JSON 메타데이터만 정리합니다. 실제 이미지 파일은 변경하지 않습니다. 정리 전에 백업을 생성하며, 기존 Shot은 수정하지 않습니다.",
    refresh_cleaning: "등록 정리 중…",
    refresh_cleaned: "정리한 등록",
    refresh_backup: "백업",
    refresh_unsafe: "현재 검토 결과로는 정리할 수 없습니다. 오류를 확인하고 다시 새로고침하세요.",
    refresh_close: "새로고침 검토 닫기",
    close: "닫기",
  },
};

function imageAssetLanguage(state) {
  const language = clean(state?.language).toLowerCase();
  return language === "en" ? "en" : "ko";
}

function imageAssetText(state, key) {
  const language = imageAssetLanguage(state);
  return IMAGE_ASSET_UI_TEXT[language]?.[key] || IMAGE_ASSET_UI_TEXT.en[key] || key;
}

function imageAssetTaxonomyLabel(state, value) {
  const text = clean(value);
  const language = imageAssetLanguage(state);
  return clean(state?.taxonomy?.labels?.[language]?.[text]) || text;
}

function imageAssetTaxonomyMeaning(state, mainType, subType) {
  const main = clean(mainType);
  const sub = clean(subType);
  const pair = (Array.isArray(state?.taxonomy?.semantic_pairs)
    ? state.taxonomy.semantic_pairs
    : []).find((item) => item.main_type === main && item.sub_type === sub);
  if (!pair) return "";
  return [clean(pair.source_type), clean(pair.scope)].filter(Boolean).join(" · ");
}

function imageAssetStatusCount(value) {
  return Math.min(9999, Math.max(0, Number.parseInt(value || 0, 10) || 0));
}

export function hmbImageAssetStatusSummary(state) {
  return `${imageAssetStatusCount(state?.status?.registered_asset_count)} ${imageAssetText(state, "registered")} | ${imageAssetStatusCount(state?.status?.unregistered_asset_count)} ${imageAssetText(state, "unregistered")} | ${imageAssetStatusCount(state?.status?.selected_count)}/${MAX_SELECTED_IMAGES} ${imageAssetText(state, "selected")}`;
}

export function hmbSetImageAssetBusy(container, busy, message = "") {
  if (!container) return false;
  const root = container.querySelector?.(".hmb-image-assets");
  root?.setAttribute?.("data-busy", busy ? "true" : "false");
  if (busy) root?.setAttribute?.("aria-busy", "true");
  else root?.removeAttribute?.("aria-busy");
  const controls = Array.from(container.querySelectorAll?.(
    "[data-project-set],[data-project-reload],[data-project-select]",
  ) || []);
  if (busy) {
    container.__hmbImageAssetBusyControls = controls.map((control) => ({
      control,
      disabled: Boolean(control.disabled),
    }));
    controls.forEach((control) => { control.disabled = true; });
  } else {
    (container.__hmbImageAssetBusyControls || []).forEach(({ control, disabled }) => {
      if (control?.isConnected !== false) control.disabled = Boolean(disabled);
    });
    delete container.__hmbImageAssetBusyControls;
  }
  container.__hmbImageAssetBusy = Boolean(busy);
  const status = container.querySelector?.(".toolbar-status strong");
  if (busy && status) {
    status.textContent = message || "Loading…";
    status.setAttribute?.("title", status.textContent);
  }
  return true;
}

export function hmbShowImageAssetTransportError(container, error, state = null) {
  if (!container) return false;
  const live = container.querySelector?.("[data-transport-status]");
  if (!live) return false;
  const fallback = state ? imageAssetText(state, "transport_failed") : "The change could not be saved. Please try again.";
  live.textContent = clean(error?.message || error) || fallback;
  return true;
}

function hmbClearImageAssetTransportError(container) {
  const live = container?.querySelector?.("[data-transport-status]");
  if (live) live.textContent = "";
}

function hmbAfterImageAssetPaint(callback) {
  const scheduleTask = () => {
    if (typeof setTimeout === "function") setTimeout(callback, 0);
    else callback();
  };
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(scheduleTask);
  else scheduleTask();
}

function clean(value) {
  return String(value ?? "").trim();
}

export function hmbHierarchyShotName(value) {
  if (typeof value !== "string" || !value || value !== value.trim() || value.length > 128
      || /[\\/:?*"<>|#\x00-\x1f\x7f]/.test(value) || [".", ".."].includes(value)
      || /[^\S ]| {2}/.test(value)
      || /https?:\/\/|data:|Bearer\s|(?:api[_-]?key|access[_-]?token)\s*[=:]/i.test(value)) {
    throw new Error("샷 이름은 공백·경로·제어문자 없이 1~128자로 입력하세요. 이름은 자동 축약하지 않습니다.");
  }
  if (/\b(authorization|api[_ -]?key|access[_ -]?token|bearer|password|secret|session[_ -]?token)\b\s*[:=]?\s*\S+/i.test(value)) throw new Error("샷 이름에 인증정보 형식의 문구를 사용할 수 없습니다.");
  return value;
}

export function hmbHierarchyParseName(value) {
  if (typeof value !== "string" || [...value].length > 256) throw new Error("샷 이름이 올바르지 않습니다.");
  const match = /^(?:(e[0-9]{3,})\/)?((e[0-9]{3,})(s[0-9]{3,})(c[0-9]{3,})__)$/.exec(value);
  if (!match) return { source_name: value, canonical_name: hmbHierarchyShotName(value), context_episode: "", episode: "", shot: "", split_cut: "" };
  const [, context, canonical, episode, shot, splitCut] = match;
  if (context && context !== episode) throw new Error("에피소드 접두 문맥과 샷 코드가 다릅니다.");
  return { source_name: value, canonical_name: hmbHierarchyShotName(canonical), context_episode: context || "", episode, shot, split_cut: splitCut };
}

function hierarchyProjectKey(state) {
  return String(state?.project_root || "").replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase() || clean(state?.project_uid);
}

export function hmbHierarchyDerivedNames(binding) {
  const rows = binding?.members || [];
  return Object.fromEntries(rows.map(row => {
    const group = [row, ...rows.filter(child => child.parent_id === row.member_id)];
    const parts = group.map(item => hmbHierarchyParseName(item.source_name));
    const name = group.length > 1 && parts.every(item => item.episode && item.episode === parts[0].episode)
      ? `${parts[0].episode}_${parts.map(item => item.shot + item.split_cut).join("-")}__`
      : group.map(item => item.canonical_name).join("+");
    return [row.gp_shot_uuid, hmbHierarchyShotName(name)];
  }));
}

export function hmbNormalizeShotHierarchy(value) {
  if (value == null || (typeof value === "object" && !Array.isArray(value) && !Object.keys(value).length)) return {};
  const fields = ["schema", "version", "binding_id", "revision", "project_identity", "channel_uuid", "cgt_account_id", "members"];
  if (value.version === 2) fields.push("cgt_scope");
  const exact = (item, keys) => item && !Array.isArray(item) && typeof item === "object" && Object.keys(item).length === keys.length && keys.every(key => Object.hasOwn(item, key));
  const uuid = id => typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id);
  const cgtId = id => typeof id === "string" && /^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$/.test(id);
  if (!exact(value, fields) || value.schema !== SHOT_HIERARCHY_SCHEMA || ![1, 2].includes(value.version)
      || !Number.isSafeInteger(value.revision) || value.revision < 1 || !uuid(value.binding_id) || !uuid(value.channel_uuid)
      || (value.version === 1 && value.cgt_account_id !== null) || typeof value.project_identity !== "string"
      || value.project_identity.length > 4096 || /[\x00-\x1f]/.test(value.project_identity)) throw new Error("지원하지 않는 샷 구성입니다.");
  if (!Array.isArray(value.members) || value.members.length > 5) throw new Error("대표와 하위를 합쳐 최대 5개 샷을 선택할 수 있습니다.");
  const memberFields = ["member_id", "origin", "manual_uuid", "source_name", "canonical_name", "gp_shot_uuid", "parent_id", "selection_order", "cgt_task_id", "artist", "status"];
  const scope = value.cgt_scope;
  if (value.version === 2) {
    memberFields.push("cgt_identity");
    if (value.members.some(row => row?.origin === "cgt")) {
      if (!value.project_identity || !exact(scope, ["origin", "project_id", "project_db", "module", "module_type", "pipeline_id", "account_id"])
          || scope.module !== "shot" || scope.module_type !== "task" || !/^https:\/\/[a-zA-Z0-9.\[\]:-]+$/.test(scope.origin)
          || !/^[A-Za-z0-9_-]{1,128}$/.test(scope.project_db) || !cgtId(scope.project_id) || !cgtId(scope.pipeline_id)
          || !cgtId(scope.account_id) || scope.account_id !== value.cgt_account_id) throw new Error("CGT 계정·프로젝트·공정 범위가 올바르지 않습니다.");
    } else if (scope !== null || value.cgt_account_id !== null) throw new Error("CGT 항목이 없는 구성에 다른 계정 범위를 남길 수 없습니다.");
  }
  const ids = new Set(); const slots = new Set(); const names = new Set();
  const episodes = new Set();
  value.members.forEach((row, i) => {
    if (!exact(row, memberFields) || !(value.version === 2 ? ["manual", "cgt"] : ["manual"]).includes(row.origin) || row.selection_order !== i + 1) throw new Error("샷 구성 항목이 올바르지 않습니다.");
    if (row.origin === "manual") {
      if (row.member_id !== `manual:${row.manual_uuid}` || [row.cgt_task_id, row.artist, row.status, row.cgt_identity ?? null].some(item => item !== null)) throw new Error("수동 항목은 CGT 계정·상태를 가질 수 없습니다.");
    } else if (!exact(row.cgt_identity, ["entity_id", "task_id", "pipeline_id"]) || !cgtId(row.cgt_task_id)
        || row.cgt_identity.task_id !== row.cgt_task_id || !cgtId(row.cgt_identity.entity_id) || row.cgt_identity.pipeline_id !== scope.pipeline_id
        || row.member_id !== `cgt:${row.cgt_task_id.toLowerCase()}` || [row.artist, row.status].some(item => typeof item !== "string" || item.length > 256 || /[\x00-\x1f]/.test(item))) throw new Error("CGT 원본 작업 범위가 일치하지 않습니다.");
    if (!uuid(row.manual_uuid) || !uuid(row.gp_shot_uuid) || ids.has(row.member_id) || slots.has(row.gp_shot_uuid)) throw new Error("같은 컷 또는 같은 샷 슬롯을 두 번 선택할 수 없습니다.");
    const name = hmbHierarchyShotName(row.canonical_name);
    const parsedName = hmbHierarchyParseName(row.source_name);
    if (parsedName.episode) episodes.add(parsedName.episode);
    if (parsedName.canonical_name !== name) throw new Error("입력한 정식 샷 이름과 실행명이 다릅니다.");
    if (names.has(name)) throw new Error("동일한 수동 샷 이름이 있습니다. 서로 다른 이름을 입력하세요.");
    ids.add(row.member_id); slots.add(row.gp_shot_uuid); names.add(name);
  });
  if (episodes.size > 1) throw new Error("서로 다른 에피소드의 샷을 같은 구성에 연결할 수 없습니다.");
  const byId = new Map(value.members.map(row => [row.member_id, row]));
  value.members.forEach(row => {
    if (row.parent_id !== null && !byId.has(row.parent_id)) throw new Error("선택한 대표 샷이 현재 구성에 없습니다.");
  });
  value.members.forEach(row => {
    const seen = new Set([row.member_id]);
    let parent = row.parent_id;
    while (parent !== null) {
      if (seen.has(parent)) throw new Error("자기 자신이나 자신의 하위 샷을 대표로 지정할 수 없습니다.");
      seen.add(parent); parent = byId.get(parent).parent_id;
    }
  });
  hmbHierarchyDerivedNames(value);
  return JSON.parse(JSON.stringify(value));
}

export function hmbValidateHierarchyRouting(binding, routing) {
  const normalized = hmbNormalizeShotHierarchy(binding);
  if (!normalized.schema) return {};
  if (normalized.channel_uuid !== routing?.channel_uuid) throw new Error("다른 라이브러리의 샷 구성을 적용할 수 없습니다.");
  const rows = new Map((routing.shots || []).map(row => [row.shot_uuid, row]));
  for (const [slot, name] of Object.entries(hmbHierarchyDerivedNames(normalized))) {
    if (rows.get(slot)?.name !== name) throw new Error("묶음에 연결된 샷은 + Shot의 샷 구성에서 수정·해제하세요.");
  }
  return normalized;
}

export function hmbApplyShotHierarchyEdit(state, request) {
  const fields = ["schema", "version", "expected_generation", "expected_binding_revision", "removed_member_ids", "binding"];
  if (!request || Object.keys(request).length !== fields.length || fields.some(key => !Object.hasOwn(request, key))
      || request.schema !== SHOT_HIERARCHY_EDIT_SCHEMA || request.version !== 1) throw new Error("샷 구성 요청이 올바르지 않습니다.");
  const routing = state.shot_routing;
  const prior = hmbValidateHierarchyRouting(state.shot_hierarchy, routing);
  if (!Number.isSafeInteger(request.expected_generation) || request.expected_generation !== routing.generation
      || !Number.isSafeInteger(request.expected_binding_revision) || request.expected_binding_revision !== (prior.revision || 0)) throw new Error("샷이 변경되었습니다. 창을 닫고 다시 열어 주세요.");
  const binding = hmbNormalizeShotHierarchy(request.binding);
  if (!binding.schema || binding.channel_uuid !== routing.channel_uuid
      || binding.project_identity !== hierarchyProjectKey(state) || binding.revision !== (prior.revision || 0) + 1
      || (prior.schema && binding.binding_id !== prior.binding_id)) throw new Error("현재 프로젝트·샷 구성의 소유권이 변경되었습니다.");
  const byId = new Map(binding.members.map(row => [row.member_id, row]));
  const removed = request.removed_member_ids;
  const expectedRemoved = (prior.members || []).filter(row => !byId.has(row.member_id)).map(row => row.member_id);
  if (!Array.isArray(removed) || removed.some(key => typeof key !== "string") || new Set(removed).size !== removed.length
      || removed.length !== expectedRemoved.length || expectedRemoved.some(key => !removed.includes(key))) throw new Error("연결 해제 항목을 명시적으로 확인하세요. 기존 실행 샷은 삭제되지 않습니다.");
  if (prior.schema && prior.project_identity !== binding.project_identity && (prior.members || []).some(row => byId.has(row.member_id))) throw new Error("이전 프로젝트의 연결을 먼저 모두 해제하세요. 수동 ID는 다른 프로젝트로 옮기지 않습니다.");
  (prior.members || []).forEach(old => {
    if (byId.has(old.member_id) && byId.get(old.member_id).gp_shot_uuid !== old.gp_shot_uuid) throw new Error("기존 컷의 독립 샷 슬롯은 변경할 수 없습니다.");
    const next = byId.get(old.member_id);
    if (next && next.origin !== old.origin) throw new Error("기존 샷의 생성 출처를 변경할 수 없습니다.");
    if (next && old.origin === "cgt" && (Object.keys(prior.cgt_scope || {}).some(key => prior.cgt_scope[key] !== binding.cgt_scope?.[key])
        || Object.keys(old.cgt_identity || {}).some(key => old.cgt_identity[key] !== next.cgt_identity?.[key])
        || old.source_name !== next.source_name || old.canonical_name !== next.canonical_name)) {
      throw new Error("CGT에서 선택한 샷의 원본 이름과 작업 ID는 변경할 수 없습니다.");
    }
  });
  const rows = routing.shots.map(row => ({ ...row, selected_source_uids: [...row.selected_source_uids] }));
  const bySlot = new Map(rows.map(row => [row.shot_uuid, row]));
  const names = Object.fromEntries((prior.members || []).map(row => [row.gp_shot_uuid, row.canonical_name]));
  Object.assign(names, hmbHierarchyDerivedNames(binding));
  const additions = binding.members.filter(row => !bySlot.has(row.gp_shot_uuid));
  if (rows.length + additions.length > 5) throw new Error("기존 샷을 포함해 최대 5개입니다. 기존 샷 슬롯을 명시적으로 선택하세요.");
  additions.forEach(item => {
    const row = { shot_uuid: item.gp_shot_uuid, number: rows.length + 1, name: names[item.gp_shot_uuid], name_is_custom: true, revision: 0, selected_source_uids: [], media_count: 0, metadata_sha256: "", media_sha256: "" };
    rows.push(row); bySlot.set(row.shot_uuid, row);
  });
  Object.entries(names).forEach(([slot, name]) => {
    const row = bySlot.get(slot);
    if (row && (row.name !== name || !row.name_is_custom)) Object.assign(row, { name, name_is_custom: true, revision: row.revision + 1 });
  });
  if (prior.schema && Object.keys(binding).every(key => key === "revision" || JSON.stringify(binding[key]) === JSON.stringify(prior[key]))) return { ...state };
  const result = { ...state, shot_routing: { ...routing, generation: routing.generation + 1, shots: rows }, shot_hierarchy: binding };
  delete result.shot_hierarchy_request;
  hmbValidateHierarchyRouting(binding, result.shot_routing);
  return result;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function parseValue(value) {
  if (value && typeof value === "object") return value;
  if (typeof value !== "string" || !value.trim()) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function uniqueStrings(value) {
  const seen = new Set();
  return (Array.isArray(value) ? value : [])
    .map(clean)
    .filter((item) => item && !seen.has(item) && seen.add(item));
}

function normalizeRelativeFolder(value) {
  const parts = clean(value)
    .replaceAll("\\", "/")
    .replace(/^\/+|\/+$/g, "")
    .split("/")
    .filter((part) => part && part !== ".");
  return parts.some((part) => part === "..") ? "" : parts.join("/");
}

const PRODUCTION_PROJECTS_ROOT = "//192.168.200.19/v/projects";
const RETIRED_PROJECTS_ROOT = "//fin-rcomp1/Composite_Team/projects_AI";

export function hmbRelocateImageProjectPath(value) {
  const text = clean(value);
  const path = text.replaceAll("\\", "/");
  const prefix = RETIRED_PROJECTS_ROOT;
  if (path.toLowerCase() === prefix.toLowerCase() || path.toLowerCase().startsWith(prefix.toLowerCase() + "/")) {
    const parts = path.slice(prefix.length).replace(/^\/+|\/+$/g, "").split("/");
    if (!parts[0]) return PRODUCTION_PROJECTS_ROOT;
    if (parts.some((part) => part === "." || part === "..")) return text;
    return [PRODUCTION_PROJECTS_ROOT, parts[0], "Ai_Ct_image", ...parts.slice(1)].join("/");
  }
  if (path.includes("://") || path.split("/").some((part) => part === "." || part === "..")) return text;
  const flat = path.match(/^(.*?\/projects)\/ai_ct_image(?:\/([^/]+)(\/.*)?)?\/?$/i);
  if (flat) return flat[2] ? `${flat[1]}/${flat[2]}/Ai_Ct_image${flat[3] || ""}` : flat[1];
  const nested = path.match(/^(.*?\/projects\/([^/]+)\/ai_ct_image)\/([^/]+)(\/.*)?$/i);
  if (nested && nested[2].toLowerCase() === nested[3].toLowerCase()) return nested[1] + (nested[4] || "");
  return text;
}

function normalizeProject(raw) {
  if (!raw || typeof raw !== "object") return null;
  const path = hmbRelocateImageProjectPath(raw.path).replaceAll("\\", "/");
  const name = clean(raw.name) || imageAssetProjectFolderName(path);
  const projectId = clean(raw.project_id);
  if (!path || !name || !projectId) return null;
  return {
    project_id: projectId,
    project_uid: clean(raw.project_uid),
    name,
    path,
  };
}

function normalizeAsset(raw) {
  if (!raw || typeof raw !== "object") return null;
  const assetLibraryId = clean(raw.asset_library_id || raw.asset_key);
  const assetId = clean(raw.asset_id);
  const imageName = clean(raw.image_name || raw.label);
  if (!assetLibraryId || !assetId || !imageName) return null;
  const sourceKind = clean(raw.source_kind).toLowerCase() === "project" ? "project" : "user";
  const registered = sourceKind === "project" && Boolean(raw.registered);
  const imageMainType = clean(raw.image_main_type);
  const imageSubType = clean(raw.image_sub_type);
  return {
    asset_library_id: assetLibraryId,
    source_uid: clean(raw.source_uid) || assetLibraryId,
    source_kind: sourceKind,
    import_source_uid: clean(raw.import_source_uid),
    asset_project_uid: clean(raw.asset_project_uid),
    asset_id: assetId,
    image_name: imageName,
    path: hmbRelocateImageProjectPath(raw.path || raw.asset_path).replaceAll("\\", "/"),
    thumbnail_url: hmbRelocateImageProjectPath(raw.thumbnail_url),
    media_signature: clean(raw.media_signature).slice(0, 64),
    relative_path: clean(raw.relative_path).replaceAll("\\", "/"),
    extension: clean(raw.extension).toLowerCase(),
    width: Math.max(0, Number.parseInt(raw.width || 0, 10) || 0),
    height: Math.max(0, Number.parseInt(raw.height || 0, 10) || 0),
    image_main_type: imageMainType || "Select Image Main Type",
    image_sub_type: imageSubType,
    source_type: clean(raw.source_type) || "Role Required / Select Source Type",
    custom_source_type: clean(raw.custom_source_type),
    scope_candidate: clean(raw.scope_candidate),
    color_pick_candidates: uniqueStrings(raw.color_pick_candidates),
    registered,
    selected: Boolean(raw.selected) && (sourceKind === "user" || registered),
    selection_order: Math.max(0, Number.parseInt(raw.selection_order || 0, 10) || 0),
    import_index: Math.max(0, Number.parseInt(raw.import_index || 0, 10) || 0),
    media_ref_kind: clean(raw.media_ref_kind) || "path",
    connected: raw.connected !== false,
  };
}

function normalizeRegistrationRequest(raw) {
  if (!raw || typeof raw !== "object") return {};
  const requestId = clean(raw.request_id).slice(0, 128);
  const assetLibraryId = clean(raw.asset_library_id).slice(0, 512);
  const sourceKind = clean(raw.source_kind).toLowerCase() === "user" ? "user" : "project";
  const sourceUid = clean(raw.source_uid).slice(0, 512);
  const relativePath = clean(raw.relative_path).replaceAll("\\", "/").slice(0, 1024);
  const targetFolder = normalizeRelativeFolder(raw.target_folder).slice(0, 1024);
  if (
    !requestId
    || !assetLibraryId
    || (sourceKind === "project" && !relativePath)
    || (sourceKind === "user" && !sourceUid)
  ) return {};
  const imageMainType = clean(raw.image_main_type);
  const imageSubType = clean(raw.image_sub_type);
  return {
    request_id: requestId,
    project_uid: clean(raw.project_uid).slice(0, 256),
    asset_library_id: assetLibraryId,
    source_kind: sourceKind,
    source_uid: sourceUid,
    relative_path: relativePath,
    target_folder: targetFolder,
    image_name: clean(raw.image_name).slice(0, 256),
    asset_id: clean(raw.asset_id).slice(0, 256),
    image_main_type: imageMainType.slice(0, 256),
    image_sub_type: imageSubType.slice(0, 256),
    custom_source_type: clean(raw.custom_source_type).slice(0, 256),
  };
}

function normalizeRegistrationResult(raw) {
  if (!raw || typeof raw !== "object") return {};
  const requestId = clean(raw.request_id).slice(0, 128);
  if (!requestId) return {};
  return {
    request_id: requestId,
    ok: Boolean(raw.ok),
    asset_library_id: clean(raw.asset_library_id).slice(0, 512),
    message: clean(raw.message).slice(0, 1000),
  };
}

function normalizeAssetRefreshReview(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const requestId = clean(raw.request_id).slice(0, 128);
  const status = clean(raw.status);
  if (!requestId || !["review", "cleaned", "error"].includes(status)) return {};
  const count = (value) => hmbNormalizeImageAssetRevision(value);
  return {
    request_id: requestId,
    project_root: clean(raw.project_root).replaceAll("\\", "/"),
    project_id: clean(raw.project_id),
    status,
    registered_count: count(raw.registered_count),
    file_count: count(raw.file_count),
    missing_count: count(raw.missing_count),
    unregistered_count: count(raw.unregistered_count),
    safe_to_clean: raw.safe_to_clean === true,
    error: clean(raw.error),
    missing_paths: uniqueStrings(raw.missing_paths),
    unregistered_paths: uniqueStrings(raw.unregistered_paths),
    cleaned_count: count(raw.cleaned_count),
    backup_path: clean(raw.backup_path),
  };
}

function normalizeAssetCleanupRequest(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const requestId = clean(raw.request_id).slice(0, 128);
  return requestId ? { request_id: requestId } : {};
}

function normalizeThumbnailRequest(raw) {
  if (!raw || typeof raw !== "object") return {};
  const requestId = clean(raw.request_id).slice(0, 128);
  const projectUid = clean(raw.project_uid).slice(0, 256);
  const assetLibraryIds = uniqueStrings(raw.asset_library_ids)
    .map((value) => value.slice(0, 512))
    .slice(0, IMAGE_ASSET_THUMBNAIL_REQUEST_BATCH);
  if (!requestId || !projectUid || !assetLibraryIds.length) return {};
  return {
    request_id: requestId,
    project_uid: projectUid,
    project_cache_uid: clean(raw.project_cache_uid).slice(0, 256),
    manifest_signature: clean(raw.manifest_signature).slice(0, 128),
    scan_revision: hmbNormalizeImageAssetRevision(raw.scan_revision),
    asset_library_ids: assetLibraryIds,
  };
}

function normalizeThumbnailResult(raw) {
  if (!raw || typeof raw !== "object") return {};
  const requestId = clean(raw.request_id).slice(0, 128);
  const projectUid = clean(raw.project_uid).slice(0, 256);
  if (!requestId || !projectUid) return {};
  return {
    request_id: requestId,
    project_uid: projectUid,
    project_cache_uid: clean(raw.project_cache_uid).slice(0, 256),
    manifest_signature: clean(raw.manifest_signature).slice(0, 128),
    scan_revision: hmbNormalizeImageAssetRevision(raw.scan_revision),
    completed_asset_library_ids: uniqueStrings(raw.completed_asset_library_ids)
      .map((value) => value.slice(0, 512))
      .slice(0, IMAGE_ASSET_THUMBNAIL_REQUEST_BATCH),
    failed_asset_library_ids: uniqueStrings(raw.failed_asset_library_ids)
      .map((value) => value.slice(0, 512))
      .slice(0, IMAGE_ASSET_THUMBNAIL_REQUEST_BATCH),
  };
}

function compactSelectionOrder(assets) {
  const selected = assets
    .map((asset, index) => ({ asset, index }))
    .filter(({ asset }) => asset.selected)
    .sort((left, right) => {
      const leftOrder = left.asset.selection_order || 100000 + left.index;
      const rightOrder = right.asset.selection_order || 100000 + right.index;
      return leftOrder - rightOrder || left.index - right.index;
    });
  selected.slice(MAX_SELECTED_IMAGES).forEach(({ asset }) => {
    asset.selected = false;
    asset.selection_order = 0;
  });
  selected.slice(0, MAX_SELECTED_IMAGES).forEach(({ asset }, index) => {
    asset.selection_order = index + 1;
  });
  assets.filter((asset) => !asset.selected).forEach((asset) => {
    asset.selection_order = 0;
  });
}

function imageAssetUuid(value) {
  const text = clean(value).toLowerCase();
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(text)
    ? text
    : "";
}

function newImageAssetUuid() {
  if (typeof globalThis?.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID().toLowerCase();
  }
  const bytes = Array.from({ length: 16 }, () => Math.floor(Math.random() * 256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.map((item) => item.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function normalizeImageAssetShotRouting(rawValue, assets) {
  const raw = rawValue && typeof rawValue === "object" ? rawValue : {};
  const masterSourceUids = selectedAssets({ assets });
  const orderedSourceUids = masterSourceUids
    .map((asset) => clean(asset.source_uid))
    .filter(Boolean);
  const masterSet = new Set(orderedSourceUids);
  const seenShotUuids = new Set();
  const shots = [];
  let compacted = false;
  (Array.isArray(raw.shots) ? raw.shots : []).slice(0, MAX_IMAGE_ASSET_SHOTS).forEach((item) => {
    if (!item || typeof item !== "object") return;
    let shotUuid = imageAssetUuid(item.shot_uuid);
    if (!shotUuid || seenShotUuids.has(shotUuid)) shotUuid = newImageAssetUuid();
    seenShotUuids.add(shotUuid);
    const selectedSourceUids = [];
    (Array.isArray(item.selected_source_uids) ? item.selected_source_uids : []).forEach((value) => {
      const sourceUid = clean(value);
      if (
        sourceUid
        && masterSet.has(sourceUid)
        && !selectedSourceUids.includes(sourceUid)
        && selectedSourceUids.length < MAX_SHOT_IMAGES
      ) selectedSourceUids.push(sourceUid);
    });
    const number = shots.length + 1;
    const previousNumber = Math.max(1, Math.floor(Number(item.number) || number));
    const previousName = clean(item.name).slice(0, 128);
    const nameIsCustom = typeof item.name_is_custom === "boolean"
      ? item.name_is_custom
      : Boolean(previousName && previousName !== `Shot ${previousNumber}`);
    const reindexed = previousNumber !== number;
    if (reindexed) compacted = true;
    const metadataSha256 = clean(item.metadata_sha256).toLowerCase();
    const mediaSha256 = clean(item.media_sha256).toLowerCase();
    shots.push({
      shot_uuid: shotUuid,
      number,
      name: nameIsCustom ? previousName || `Shot ${number}` : `Shot ${number}`,
      name_is_custom: nameIsCustom,
      revision: Math.max(0, Math.floor(Number(item.revision) || 0)) + (reindexed ? 1 : 0),
      selected_source_uids: selectedSourceUids,
      media_count: Math.min(
        selectedSourceUids.length,
        Math.max(0, Math.floor(Number(item.media_count) || 0)),
      ),
      metadata_sha256: /^[0-9a-f]{64}$/.test(metadataSha256) ? metadataSha256 : "",
      media_sha256: /^[0-9a-f]{64}$/.test(mediaSha256) ? mediaSha256 : "",
    });
  });
  if (!shots.length) {
    shots.push({
      shot_uuid: newImageAssetUuid(),
      number: 1,
      name: "Shot 1",
      name_is_custom: false,
      revision: orderedSourceUids.length ? 1 : 0,
      selected_source_uids: orderedSourceUids.slice(0, MAX_SHOT_IMAGES),
      media_count: 0,
      metadata_sha256: "",
      media_sha256: "",
    });
  }
  let activeShotUuid = imageAssetUuid(raw.active_shot_uuid);
  if (!shots.some((shot) => shot.shot_uuid === activeShotUuid)) {
    activeShotUuid = shots[0].shot_uuid;
  }
  return {
    schema: SHOT_ROUTING_SCHEMA,
    version: SHOT_ROUTING_VERSION,
    publisher_instance_uuid: imageAssetUuid(raw.publisher_instance_uuid) || newImageAssetUuid(),
    channel_uuid: imageAssetUuid(raw.channel_uuid) || newImageAssetUuid(),
    generation: Math.max(1, Math.floor(Number(raw.generation) || 1)) + (compacted ? 1 : 0),
    active_shot_uuid: activeShotUuid,
    expanded: Boolean(raw.expanded),
    shots,
  };
}

function normalizedFolders(inputFolders, assets) {
  const result = new Set();
  const add = (raw) => {
    const folder = normalizeRelativeFolder(raw);
    if (!folder) return;
    const parts = folder.split("/");
    for (let index = 1; index <= parts.length; index += 1) {
      result.add(parts.slice(0, index).join("/"));
    }
  };
  (Array.isArray(inputFolders) ? inputFolders : []).forEach(add);
  assets.forEach((asset) => {
    const relative = clean(asset.relative_path).replaceAll("\\", "/");
    if (relative.includes("/")) add(relative.slice(0, relative.lastIndexOf("/")));
  });
  return [...result].sort((left, right) => left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  }));
}

function markCanonicalImageAssetState(state) {
  if (!state || typeof state !== "object") return state;
  Object.defineProperty(state, IMAGE_ASSET_AUTHORITY_STAMP, {
    configurable: false,
    enumerable: false,
    writable: false,
    value: ++imageAssetAuthoritySequence,
  });
  return state;
}

function imageAssetAuthorityStamp(state) {
  return Number(state?.[IMAGE_ASSET_AUTHORITY_STAMP]) || 0;
}

function isCanonicalImageAssetState(state) {
  return imageAssetAuthorityStamp(state) > 0;
}

function normalizeImageTaxonomyContract(value) {
  const raw = value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
  if (
    raw.schema !== IMAGE_TAXONOMY_SCHEMA
    || Number(raw.version) !== IMAGE_TAXONOMY_VERSION
  ) return {};
  const mainTypes = uniqueStrings(raw.image_main_type_choices);
  const rawSubTypes = (
    raw.image_sub_type_choices
    && typeof raw.image_sub_type_choices === "object"
    && !Array.isArray(raw.image_sub_type_choices)
  ) ? raw.image_sub_type_choices : {};
  const subTypes = Object.fromEntries(
    Object.entries(rawSubTypes)
      .map(([mainType, values]) => [clean(mainType), uniqueStrings(values)])
      .filter(([mainType, values]) => mainType && values.length),
  );
  const semanticPairs = (Array.isArray(raw.semantic_pairs) ? raw.semantic_pairs : [])
    .map((pair) => ({
      main_type: clean(pair?.main_type),
      sub_type: clean(pair?.sub_type),
      source_type: clean(pair?.source_type),
      scope: clean(pair?.scope),
    }))
    .filter((pair) => pair.main_type && pair.sub_type && pair.source_type);
  const pairKeys = Object.entries(subTypes)
    .flatMap(([mainType, values]) => values.map((subType) => `${mainType}\u0000${subType}`));
  const selectableMainCount = Math.max(0, mainTypes.length - 1);
  const subTypeCount = Object.values(subTypes)
    .reduce((sum, values) => sum + values.length, 0);
  if (mainTypes[0] !== "Select Image Main Type") return {};
  const labels = raw.labels && typeof raw.labels === "object" && !Array.isArray(raw.labels)
    ? {
        en: { ...(raw.labels.en && typeof raw.labels.en === "object" ? raw.labels.en : {}) },
        ko: { ...(raw.labels.ko && typeof raw.labels.ko === "object" ? raw.labels.ko : {}) },
      }
    : { en: {}, ko: {} };
  return {
    schema: IMAGE_TAXONOMY_SCHEMA,
    version: IMAGE_TAXONOMY_VERSION,
    main_type_count: selectableMainCount,
    sub_type_count: subTypeCount,
    pair_count: pairKeys.length,
    image_main_type_choices: mainTypes,
    image_sub_type_choices: subTypes,
    semantic_pairs: semanticPairs,
    labels,
  };
}

export function hmbNormalizeImageBashWorkspace(value) {
  const workspaceId = imageAssetUuid(value?.workspace_id);
  if (!workspaceId) return {};
  const instances = [], seen = new Set();
  for (const raw of Array.isArray(value?.instances) ? value.instances : []) {
    const instanceId = imageAssetUuid(raw?.instance_id), sourceUid = clean(raw?.source_uid).slice(0, 512);
    if (!instanceId || !sourceUid || seen.has(instanceId)) continue;
    seen.add(instanceId); instances.push({ instance_id: instanceId, source_uid: sourceUid });
    if (instances.length >= MAX_SELECTED_IMAGES) break;
  }
  return { workspace_id: workspaceId, revision: hmbNormalizeImageAssetRevision(value.revision), instances };
}

export function hmbCreateImageBashWorkspace(state) {
  if (!state) return false;
  if (!hmbNormalizeImageBashWorkspace(state.image_bash_workspace).workspace_id) {
    state.image_bash_workspace = { workspace_id: newImageAssetUuid(), revision: 0, instances: [] };
  }
  state.image_bash_active = true;
  return true;
}

export function hmbImageBashWorkspaceAssets(state) {
  const byUid = new Map((state?.assets || []).map(asset => [clean(asset.source_uid), asset]));
  return (state?.image_bash_workspace?.instances || []).map(instance => ({
    ...instance, asset: byUid.get(instance.source_uid) || null,
  }));
}

export function hmbAddImageBashSource(state, sourceUid) {
  const workspace = state?.image_bash_workspace, uid = clean(sourceUid);
  const asset = state?.assets?.find(row => row.source_uid === uid);
  if (!workspace?.workspace_id || !asset || !hmbImageAssetCanSelect(asset) || workspace.instances.length >= MAX_SELECTED_IMAGES) return false;
  workspace.instances.push({ instance_id: newImageAssetUuid(), source_uid: uid });
  workspace.revision += 1; return true;
}

export function hmbRemoveImageBashInstance(state, instanceId) {
  const workspace = state?.image_bash_workspace;
  const index = workspace?.instances?.findIndex(row => row.instance_id === instanceId) ?? -1;
  if (index < 0) return false;
  workspace.instances.splice(index, 1); workspace.revision += 1; return true;
}

export function hmbDuplicateImageBashInstance(state, instanceId) {
  const workspace = state?.image_bash_workspace;
  const index = workspace?.instances?.findIndex(row => row.instance_id === instanceId) ?? -1;
  if (index < 0 || workspace.instances.length >= MAX_SELECTED_IMAGES) return false;
  workspace.instances.splice(index + 1, 0, { ...workspace.instances[index], instance_id: newImageAssetUuid() });
  workspace.revision += 1; return true;
}

export function hmbReorderImageBashInstance(state, fromId, toId) {
  const workspace = state?.image_bash_workspace;
  const from = workspace?.instances?.findIndex(row => row.instance_id === fromId) ?? -1;
  const to = workspace?.instances?.findIndex(row => row.instance_id === toId) ?? -1;
  if (from < 0 || to < 0 || from === to) return false;
  const [instance] = workspace.instances.splice(from, 1); workspace.instances.splice(to, 0, instance);
  workspace.revision += 1; return true;
}

function imageBashSourceUids(state) {
  return new Set((state?.image_bash_workspace?.instances || []).map(row => row.source_uid));
}

function normalizeState(value) {
  const input = parseValue(value);
  const taxonomy = normalizeImageTaxonomyContract(input.taxonomy);
  const projects = [];
  const seenProjects = new Set();
  (Array.isArray(input.projects) ? input.projects : []).forEach((raw) => {
    const project = normalizeProject(raw);
    const key = project?.path.toLowerCase();
    if (!project || seenProjects.has(key)) return;
    seenProjects.add(key);
    projects.push(project);
  });
  const assets = [];
  const seenAssets = new Set();
  (Array.isArray(input.assets) ? input.assets : []).forEach((raw) => {
    const asset = normalizeAsset(raw);
    if (!asset || seenAssets.has(asset.asset_library_id)) return;
    seenAssets.add(asset.asset_library_id);
    assets.push(asset);
  });
  compactSelectionOrder(assets);
  const folders = normalizedFolders(input.folders, assets);
  const selectedFolderPath = normalizeRelativeFolder(input.selected_folder_path);
  const hasExpandedFolders = Array.isArray(input.expanded_folders);
  const expandedFolders = uniqueStrings(input.expanded_folders)
    .map((item) => item === ROOT_FOLDER_KEY ? ROOT_FOLDER_KEY : normalizeRelativeFolder(item))
    .filter((item) => item === ROOT_FOLDER_KEY || folders.includes(item));
  const projectRoot = hmbRelocateImageProjectPath(input.project_root).replaceAll("\\", "/");
  if (projectRoot && !hasExpandedFolders) expandedFolders.push(ROOT_FOLDER_KEY);
  const selectedSourceView = clean(input.selected_source_view).toLowerCase() === "user"
    ? "user"
    : "project";
  const selectedMainType = clean(input.selected_main_type);
  const selectedSubType = clean(input.selected_sub_type);
  const shotRouting = normalizeImageAssetShotRouting(input.shot_routing, assets);
  const shotHierarchy = hmbValidateHierarchyRouting(input.shot_hierarchy, shotRouting);
  const selectedProjectKey = hierarchyProjectKey({ project_root: projectRoot, project_uid: input.project_uid });
  if (shotHierarchy.schema && shotHierarchy.project_identity) {
    const previousIdentity = shotHierarchy.project_identity;
    const previousKey = hierarchyProjectKey({ project_root: previousIdentity });
    const canonicalIdentity = hierarchyProjectKey({ project_root: hmbRelocateImageProjectPath(previousIdentity) });
    if (canonicalIdentity !== previousKey && canonicalIdentity === selectedProjectKey) {
      // Address migration retains the same binding, revision and CGT authority.
      shotHierarchy.project_identity = canonicalIdentity;
    }
  }
  if (shotHierarchy.schema && !shotHierarchy.project_identity && selectedProjectKey
      && shotHierarchy.members.every(row => row.origin === "manual")) {
    shotHierarchy.project_identity = selectedProjectKey;
    shotHierarchy.revision = Math.min(Number.MAX_SAFE_INTEGER, shotHierarchy.revision + 1);
  }
  return markCanonicalImageAssetState({
    schema: "hmb-image-asset-library-state",
    version: IMAGE_ASSET_STATE_VERSION,
    edit_transport_schema: clean(input.edit_transport_schema) === IMAGE_ASSET_EDIT_SCHEMA
      ? IMAGE_ASSET_EDIT_SCHEMA : "",
    catalog_root: hmbRelocateImageProjectPath(
      input.catalog_root || PRODUCTION_PROJECTS_ROOT,
    ).replaceAll("\\", "/"),
    projects,
    project_root: projectRoot,
    project_id: clean(input.project_id),
    project_uid: clean(input.project_uid),
    project_cache_uid: clean(input.project_cache_uid),
    manifest_signature: clean(input.manifest_signature).slice(0, 128),
    folder_signature: clean(input.folder_signature).slice(0, 128),
    taxonomy,
    folders,
    assets,
    ...(hmbCatalogPage(input.catalog_page) ? {catalog_page:hmbCatalogPage(input.catalog_page)} : {}),
    shot_routing: shotRouting,
    shot_hierarchy: shotHierarchy,
    shot_hierarchy_request: input.shot_hierarchy_request || {},
    image_bash_workspace: hmbNormalizeImageBashWorkspace(input.image_bash_workspace),
    image_bash_active: Boolean(input.image_bash_active && imageAssetUuid(input.image_bash_workspace?.workspace_id)),
    image_bash_workspace_request: input.image_bash_workspace_request || {},
    root_edit_enabled: Boolean(input.root_edit_enabled),
    selected_folder_path: folders.includes(selectedFolderPath) ? selectedFolderPath : "",
    expanded_folders: expandedFolders,
    selected_main_type: selectedMainType,
    selected_sub_type: selectedSubType,
    selected_source_view: selectedSourceView,
    search: clean(input.search).slice(0, 256),
    language: clean(input.language).toLowerCase() === "en" ? "en" : "ko",
    asset_view_mode: clean(input.asset_view_mode).toLowerCase() === "detail" ? "detail" : "image",
    [IMAGE_ASSET_UI_EDIT_REVISION_KEY]: Math.max(
      0,
      Math.min(
        MAX_IMAGE_ASSET_REVISION,
        Math.floor(Number(input?.[IMAGE_ASSET_UI_EDIT_REVISION_KEY]) || 0),
      ),
    ),
    scan_revision: Math.max(0, Number.parseInt(input.scan_revision || 0, 10) || 0),
    refresh_revision: Math.max(0, Number.parseInt(input.refresh_revision || 0, 10) || 0),
    scan_busy: Boolean(input.scan_busy),
    scan_request_id: clean(input.scan_request_id).slice(0, 128),
    thumbnail_request: normalizeThumbnailRequest(input.thumbnail_request),
    thumbnail_result: normalizeThumbnailResult(input.thumbnail_result),
    thumbnail_revision: hmbNormalizeImageAssetRevision(input.thumbnail_revision),
    thumbnail_busy: Boolean(input.thumbnail_busy),
    asset_registration_request: normalizeRegistrationRequest(input.asset_registration_request),
    asset_registration_result: normalizeRegistrationResult(input.asset_registration_result),
    asset_refresh_review: normalizeAssetRefreshReview(input.asset_refresh_review),
    asset_cleanup_request: normalizeAssetCleanupRequest(input.asset_cleanup_request),
    disconnect_import_uid: clean(input.disconnect_import_uid).startsWith("import:")
      ? clean(input.disconnect_import_uid).slice(0, 512)
      : "",
    warnings: uniqueStrings(input.warnings).slice(0, 100),
    error: clean(input.error),
    status: hmbCatalogPage(input.catalog_page) ? {...input.status,selected_count:assets.filter(asset=>asset.selected).length} : {
      asset_count: assets.length,
      selected_count: assets.filter((asset) => asset.selected).length,
      project_asset_count: assets.filter((asset) => asset.source_kind === "project").length,
      user_asset_count: assets.filter((asset) => asset.source_kind === "user").length,
      registered_asset_count: assets.filter(
        (asset) => asset.source_kind === "project" && asset.registered,
      ).length,
      unregistered_asset_count: assets.filter(
        (asset) => asset.source_kind === "project" && !asset.registered,
      ).length,
    },
  });
}

export function hmbNormalizeImageAssetState(value) {
  return normalizeState(value);
}

function imageAssetThumbnailContextMatches(state, result) {
  return Boolean(
    clean(state?.project_uid)
    && clean(result?.request_id)
    && clean(result?.project_uid) === clean(state?.project_uid)
    && (!clean(result?.project_cache_uid)
      || clean(result?.project_cache_uid) === clean(state?.project_cache_uid))
    && clean(result?.manifest_signature) === clean(state?.manifest_signature)
    && hmbNormalizeImageAssetRevision(result?.scan_revision)
      === hmbNormalizeImageAssetRevision(state?.scan_revision)
  );
}

// A thumbnail completion is allowed to update presentation media only. In
// particular, delayed hydration must never become an authority for Shot
// membership, selection order, raster metadata, paths, or taxonomy fields.
export function hmbMergeImageAssetThumbnailResponse(
  localValue,
  incomingValue,
  expectedRequestId = "",
) {
  const local = normalizeState(localValue);
  const incoming = isCanonicalImageAssetState(incomingValue)
    ? incomingValue
    : normalizeState(incomingValue);
  const result = incoming.thumbnail_result;
  const pendingRequestId = clean(expectedRequestId)
    || clean(local.thumbnail_request?.request_id);
  if (
    !imageAssetThumbnailContextMatches(local, result)
    || (pendingRequestId && result.request_id !== pendingRequestId)
    || incoming.thumbnail_revision <= local.thumbnail_revision
  ) return local;

  const completed = new Set(result.completed_asset_library_ids || []);
  const incomingById = new Map(
    incoming.assets.map((asset) => [clean(asset.asset_library_id), asset]),
  );
  local.assets.forEach((asset) => {
    const key = clean(asset.asset_library_id);
    if (!completed.has(key)) return;
    const hydrated = incomingById.get(key);
    const mediaSignature = clean(asset.media_signature);
    if (
      !hydrated
      || clean(hydrated.source_uid) !== clean(asset.source_uid)
      || !mediaSignature
      || clean(hydrated.media_signature) !== mediaSignature
    ) return;
    const thumbnailUrl = clean(hydrated.thumbnail_url);
    if (thumbnailUrl) asset.thumbnail_url = thumbnailUrl;
  });
  local.thumbnail_revision = incoming.thumbnail_revision;
  local.thumbnail_result = result;
  local.thumbnail_busy = incoming.thumbnail_busy;
  if (local.thumbnail_request?.request_id === result.request_id) {
    local.thumbnail_request = {};
  }
  hmbRememberImageAssetPresentation(local);
  return local;
}

function imageAssetShotAuthorityMatches(localState, incomingState) {
  if (JSON.stringify(localState?.image_bash_workspace) !== JSON.stringify(incomingState?.image_bash_workspace)
      || Boolean(localState?.image_bash_active) !== Boolean(incomingState?.image_bash_active)) return false;
  const localRouting = localState?.shot_routing;
  const incomingRouting = incomingState?.shot_routing;
  const localShots = Array.isArray(localRouting?.shots) ? localRouting.shots : [];
  const incomingShots = Array.isArray(incomingRouting?.shots) ? incomingRouting.shots : [];
  if (
    clean(localRouting?.schema) !== clean(incomingRouting?.schema)
    || Number(localRouting?.version || 0) !== Number(incomingRouting?.version || 0)
    || clean(localRouting?.publisher_instance_uuid)
      !== clean(incomingRouting?.publisher_instance_uuid)
    || clean(localRouting?.channel_uuid) !== clean(incomingRouting?.channel_uuid)
    || Number(localRouting?.generation || 0) !== Number(incomingRouting?.generation || 0)
    || clean(localRouting?.active_shot_uuid) !== clean(incomingRouting?.active_shot_uuid)
    || localShots.length !== incomingShots.length
  ) return false;
  return localShots.every((shot, index) => {
    const incoming = incomingShots[index];
    const localSources = uniqueStrings(shot?.selected_source_uids);
    const incomingSources = uniqueStrings(incoming?.selected_source_uids);
    return Boolean(
      incoming
      && clean(shot?.shot_uuid) === clean(incoming.shot_uuid)
      && Number(shot?.number || 0) === Number(incoming.number || 0)
      && clean(shot?.name) === clean(incoming.name)
      && localSources.length === incomingSources.length
      && localSources.every((sourceUid, sourceIndex) => sourceUid === incomingSources[sourceIndex])
    );
  });
}

function imageAssetThumbnailOnlyTransition(localState, incomingState, expectedRequestId = "") {
  const result = incomingState?.thumbnail_result;
  const pendingRequestId = clean(expectedRequestId)
    || clean(localState?.thumbnail_request?.request_id);
  return Boolean(
    localState
    && incomingState
    && imageAssetThumbnailContextMatches(localState, result)
    && (!pendingRequestId || clean(result?.request_id) === pendingRequestId)
    && hmbNormalizeImageAssetRevision(incomingState.thumbnail_revision)
      > hmbNormalizeImageAssetRevision(localState.thumbnail_revision)
    && clean(localState.project_uid) === clean(incomingState.project_uid)
    && clean(localState.project_cache_uid) === clean(incomingState.project_cache_uid)
    && clean(localState.manifest_signature) === clean(incomingState.manifest_signature)
    && hmbNormalizeImageAssetRevision(localState.scan_revision)
      === hmbNormalizeImageAssetRevision(incomingState.scan_revision)
    && hmbNormalizeImageAssetRevision(localState[IMAGE_ASSET_UI_EDIT_REVISION_KEY])
      === hmbNormalizeImageAssetRevision(incomingState[IMAGE_ASSET_UI_EDIT_REVISION_KEY])
    && Boolean(localState.scan_busy) === Boolean(incomingState.scan_busy)
    && clean(localState.error) === clean(incomingState.error)
    && clean(localState.asset_registration_result?.request_id)
      === clean(incomingState.asset_registration_result?.request_id)
    && JSON.stringify(localState.asset_refresh_review)
      === JSON.stringify(incomingState.asset_refresh_review)
    && imageAssetShotAuthorityMatches(localState, incomingState)
  );
}

// Optional compact host transport. Current hosts continue to deliver the full
// canonical state through `value`; hosts that understand presentation patches
// may instead send this envelope without retransmitting the catalog. The
// project/manifest/scan tuple and per-asset media signature keep the patch from
// becoming semantic state authority.
function hmbApplyImageAssetThumbnailPresentationPatch(localValue, patchValue) {
  const local = isCanonicalImageAssetState(localValue)
    ? localValue
    : normalizeState(localValue);
  const patch = patchValue && typeof patchValue === "object" ? patchValue : null;
  const pendingRequestId = clean(local.thumbnail_request?.request_id);
  if (
    !patch
    || clean(patch.schema) !== "hmb-image-asset-thumbnail-bridge"
    || clean(patch.operation) !== "hydrate"
    || clean(patch.phase) !== "result"
    || clean(patch.project_uid) !== clean(local.project_uid)
    || (clean(patch.project_cache_uid)
      && clean(patch.project_cache_uid) !== clean(local.project_cache_uid))
    || (clean(patch.runtime_instance_id)
      && clean(patch.runtime_instance_id) !== imageAssetThumbnailRuntimeId(local))
    || (pendingRequestId && clean(patch.request_id) !== pendingRequestId)
    || clean(patch.manifest_signature) !== clean(local.manifest_signature)
    || hmbNormalizeImageAssetRevision(patch.scan_revision)
      !== hmbNormalizeImageAssetRevision(local.scan_revision)
    || hmbNormalizeImageAssetRevision(patch.thumbnail_revision)
      <= hmbNormalizeImageAssetRevision(local.thumbnail_revision)
  ) return null;

  const entries = Array.isArray(patch.completed_assets) ? patch.completed_assets : [];
  const localById = new Map(
    local.assets.map((asset) => [clean(asset.asset_library_id), asset]),
  );
  const completed = [];
  const completedAssets = [];
  const rejected = [];
  entries.forEach((entry) => {
    const key = clean(entry?.asset_library_id);
    const asset = localById.get(key);
    const thumbnailUrl = clean(entry?.thumbnail_url);
    if (
      !asset
      || !thumbnailUrl
      || clean(entry?.source_uid) !== clean(asset.source_uid)
      || clean(entry?.media_signature) !== clean(asset.media_signature)
    ) {
      if (key) rejected.push(key);
      return;
    }
    asset.thumbnail_url = thumbnailUrl;
    completed.push(key);
    completedAssets.push(asset);
  });
  const failed = uniqueStrings([
    ...(Array.isArray(patch.failed_asset_library_ids)
      ? patch.failed_asset_library_ids
      : []),
    ...rejected,
  ]).map((value) => value.slice(0, 512));
  local.thumbnail_revision = hmbNormalizeImageAssetRevision(patch.thumbnail_revision);
  local.thumbnail_busy = false;
  local.thumbnail_result = {
    request_id: clean(patch.request_id),
    project_uid: clean(patch.project_uid),
    project_cache_uid: clean(patch.project_cache_uid),
    manifest_signature: clean(patch.manifest_signature),
    scan_revision: hmbNormalizeImageAssetRevision(patch.scan_revision),
    completed_asset_library_ids: uniqueStrings(completed),
    failed_asset_library_ids: failed,
  };
  if (local.thumbnail_request?.request_id === local.thumbnail_result.request_id) {
    local.thumbnail_request = {};
  }
  hmbRememberImageAssetPresentation(local, completedAssets);
  return {
    state: local,
    completedAssetLibraryIds: completed,
    failedAssetLibraryIds: failed,
    changedAssetLibraryIds: uniqueStrings([...completed, ...failed]),
  };
}

function selectedAssets(state) {
  return state.assets
    .filter((asset) => asset.selected)
    .sort((left, right) => left.selection_order - right.selection_order);
}

function ensureImageAssetShotRouting(state) {
  if (!state || !Array.isArray(state.assets)) return null;
  state.shot_routing = normalizeImageAssetShotRouting(state.shot_routing, state.assets);
  return state.shot_routing;
}

function activeImageAssetShot(state) {
  const routing = ensureImageAssetShotRouting(state);
  return routing?.shots.find((shot) => shot.shot_uuid === routing.active_shot_uuid)
    || routing?.shots[0]
    || null;
}

function imageAssetShotAssets(state, shot = activeImageAssetShot(state), selectedByUid = null) {
  if (!shot || !Array.isArray(state?.assets)) return [];
  const bySourceUid = selectedByUid || new Map(
    selectedAssets(state).map((asset) => [clean(asset.source_uid), asset]),
  );
  return shot.selected_source_uids
    .map((sourceUid) => bySourceUid.get(clean(sourceUid)))
    .filter(Boolean)
    .slice(0, MAX_SHOT_IMAGES);
}

function imageAssetShotContains(shot, sourceUid) {
  return Boolean(
    shot
    && clean(sourceUid)
    && shot.selected_source_uids.includes(clean(sourceUid)),
  );
}

function bumpImageAssetShotRouting(routing, shot = null) {
  if (!routing) return;
  routing.generation = Math.max(1, Math.floor(Number(routing.generation) || 1) + 1);
  if (shot) shot.revision = Math.max(0, Math.floor(Number(shot.revision) || 0) + 1);
}

function cloneImageAssetShotRouting(routing) {
  if (!routing || typeof routing !== "object") return null;
  return {
    schema: routing.schema,
    version: routing.version,
    publisher_instance_uuid: routing.publisher_instance_uuid,
    channel_uuid: routing.channel_uuid,
    generation: routing.generation,
    active_shot_uuid: routing.active_shot_uuid,
    expanded: Boolean(routing.expanded),
    shots: (Array.isArray(routing.shots) ? routing.shots : []).map((shot) => ({
      shot_uuid: shot.shot_uuid,
      number: shot.number,
      name: shot.name,
      name_is_custom: Boolean(shot.name_is_custom),
      revision: shot.revision,
      selected_source_uids: [...shot.selected_source_uids],
      media_count: shot.media_count,
      metadata_sha256: shot.metadata_sha256,
      media_sha256: shot.media_sha256,
    })),
  };
}

export function hmbImageAssetShotRouting(state) {
  return ensureImageAssetShotRouting(state);
}

export function hmbImageAssetShotRoutingCatalog(state) {
  const routing = ensureImageAssetShotRouting(state);
  return {
    schema: "hmb-shot-routing-ui-catalog",
    version: 1,
    publisher_kind: "image_asset",
    publisher_instance_uuid: routing.publisher_instance_uuid,
    channel_uuid: routing.channel_uuid,
    generation: routing.generation,
    shots: routing.shots.map((shot) => ({
      shot_uuid: shot.shot_uuid,
      number: shot.number,
      name: shot.name,
      revision: shot.revision,
    })),
  };
}

export function hmbPublishImageAssetShotRoutingCatalog(state, eventTarget = globalThis?.window) {
  const detail = hmbImageAssetShotRoutingCatalog(state);
  const EventConstructor = eventTarget?.CustomEvent || globalThis?.CustomEvent;
  if (eventTarget?.dispatchEvent && typeof EventConstructor === "function") {
    eventTarget.dispatchEvent(new EventConstructor("hmb-shot-routing-catalog-v1", { detail }));
  }
  return detail;
}

export function hmbAddImageAssetShot(state) {
  const routing = ensureImageAssetShotRouting(state);
  if (!routing || routing.shots.length >= MAX_IMAGE_ASSET_SHOTS) return false;
  const number = routing.shots.length + 1;
  const shot = {
    shot_uuid: newImageAssetUuid(),
    number,
    name: `Shot ${number}`,
    name_is_custom: false,
    revision: 0,
    selected_source_uids: [],
    media_count: 0,
    metadata_sha256: "",
    media_sha256: "",
  };
  routing.shots.push(shot);
  routing.active_shot_uuid = shot.shot_uuid;
  routing.expanded = true;
  bumpImageAssetShotRouting(routing);
  return true;
}

export function hmbDeleteImageAssetShot(state, shotUuid) {
  if (state.shot_hierarchy?.members?.some(row => row.gp_shot_uuid === shotUuid)) return false;
  const routing = ensureImageAssetShotRouting(state);
  const target = imageAssetUuid(shotUuid);
  const deleteIndex = routing?.shots.findIndex((shot) => shot.shot_uuid === target) ?? -1;
  if (!routing || routing.shots.length <= 1 || deleteIndex < 0) return false;

  const [removed] = routing.shots.splice(deleteIndex, 1);
  const retainedSourceUids = new Set(
    routing.shots.flatMap((shot) => shot.selected_source_uids),
  );
  const removedSourceUids = new Set(removed.selected_source_uids);
  let masterSelectionChanged = false;
  state.assets.forEach((asset) => {
    const sourceUid = clean(asset.source_uid);
    if (!removedSourceUids.has(sourceUid) || retainedSourceUids.has(sourceUid)) return;
    if (asset.selected || Number(asset.selection_order) > 0) masterSelectionChanged = true;
    asset.selected = false;
    asset.selection_order = 0;
  });
  if (masterSelectionChanged) {
    compactSelectionOrder(state.assets);
    if (state.status && typeof state.status === "object") {
      state.status.selected_count = selectedAssets(state).length;
    }
  }

  routing.shots.forEach((shot, index) => {
    const number = index + 1;
    const previousNumber = Math.max(1, Math.floor(Number(shot.number) || number));
    if (previousNumber === number) return;
    if (!shot.name_is_custom) {
      shot.name = `Shot ${number}`;
    }
    shot.number = number;
    shot.revision = Math.max(0, Math.floor(Number(shot.revision) || 0) + 1);
    shot.media_count = 0;
    shot.metadata_sha256 = "";
    shot.media_sha256 = "";
  });
  if (routing.active_shot_uuid === target) {
    routing.active_shot_uuid = routing.shots[
      Math.min(deleteIndex, routing.shots.length - 1)
    ].shot_uuid;
  }
  bumpImageAssetShotRouting(routing);
  return true;
}

export function hmbActivateImageAssetShot(state, shotUuid) {
  const routing = ensureImageAssetShotRouting(state);
  const target = imageAssetUuid(shotUuid);
  if (!routing?.shots.some((shot) => shot.shot_uuid === target)) return false;
  if (routing.active_shot_uuid === target) return false;
  routing.active_shot_uuid = target;
  return true;
}

export function hmbRenameImageAssetShot(state, shotUuid, value) {
  if (state.shot_hierarchy?.members?.some(row => row.gp_shot_uuid === shotUuid)) return false;
  const routing = ensureImageAssetShotRouting(state);
  const shot = routing?.shots.find((item) => item.shot_uuid === imageAssetUuid(shotUuid));
  const name = clean(value).slice(0, 128);
  if (!shot || !name || name === shot.name) return false;
  shot.name = name;
  shot.name_is_custom = true;
  bumpImageAssetShotRouting(routing, shot);
  return true;
}

export function hmbImageAssetShotCanRename(state, shotUuid) {
  return !state.shot_hierarchy?.members?.some(row => row.gp_shot_uuid === shotUuid && row.origin === "cgt");
}

export function hmbImageAssetManualRenameRequest(state, shotUuid, value) {
  const binding = hmbValidateHierarchyRouting(state.shot_hierarchy, state.shot_routing);
  const member = binding.members?.find(row => row.gp_shot_uuid === shotUuid);
  if (!member) return null;
  if (member.origin !== "manual") throw new Error("CGT에서 선택한 샷의 이름은 변경할 수 없습니다.");
  const parsed = hmbHierarchyParseName(value);
  return { schema: SHOT_HIERARCHY_EDIT_SCHEMA, version: 1,
    expected_generation: state.shot_routing.generation, expected_binding_revision: binding.revision,
    removed_member_ids: [], binding: { ...binding, revision: binding.revision + 1,
      members: binding.members.map(row => row === member
        ? { ...row, source_name: parsed.source_name, canonical_name: parsed.canonical_name } : row) } };
}

export function hmbToggleImageAssetShotSource(state, shotUuid, sourceUid) {
  const routing = ensureImageAssetShotRouting(state);
  const shot = routing?.shots.find((item) => item.shot_uuid === imageAssetUuid(shotUuid));
  const uid = clean(sourceUid);
  const available = new Set(selectedAssets(state).map((asset) => clean(asset.source_uid)));
  if (!shot || !uid || !available.has(uid)) return false;
  const index = shot.selected_source_uids.indexOf(uid);
  if (index >= 0) shot.selected_source_uids.splice(index, 1);
  else {
    if (shot.selected_source_uids.length >= MAX_SHOT_IMAGES) return false;
    shot.selected_source_uids.push(uid);
  }
  shot.media_count = 0;
  shot.metadata_sha256 = "";
  shot.media_sha256 = "";
  bumpImageAssetShotRouting(routing, shot);
  return true;
}

export function hmbReorderImageAssetShotSource(state, shotUuid, sourceUid, targetSourceUid) {
  const routing = ensureImageAssetShotRouting(state);
  const shot = routing?.shots.find((item) => item.shot_uuid === imageAssetUuid(shotUuid));
  const source = clean(sourceUid);
  const target = clean(targetSourceUid);
  const from = shot?.selected_source_uids.indexOf(source) ?? -1;
  const to = shot?.selected_source_uids.indexOf(target) ?? -1;
  if (!shot || from < 0 || to < 0 || from === to) return false;
  const [moved] = shot.selected_source_uids.splice(from, 1);
  shot.selected_source_uids.splice(to, 0, moved);
  shot.media_count = 0;
  shot.metadata_sha256 = "";
  shot.media_sha256 = "";
  bumpImageAssetShotRouting(routing, shot);
  return true;
}

export function hmbToggleImageAssetShotAsset(state, shotUuid, sourceUid, assetHint = null) {
  const routing = ensureImageAssetShotRouting(state);
  const shot = routing?.shots.find((item) => item.shot_uuid === imageAssetUuid(shotUuid));
  const uid = clean(sourceUid);
  const asset = clean(assetHint?.source_uid) === uid
    ? assetHint
    : state?.assets?.find((item) => clean(item?.source_uid) === uid);
  if (!shot || !asset || !uid || !hmbImageAssetCanSelect(asset)) return false;
  const memberIndex = shot.selected_source_uids.indexOf(uid);
  if (memberIndex < 0) {
    if (shot.selected_source_uids.length >= MAX_SHOT_IMAGES) return false;
    if (!asset.selected) {
      const master = selectedAssets(state);
      if (master.length >= MAX_SELECTED_IMAGES) return false;
      asset.selected = true;
      asset.selection_order = Math.max(0, ...master.map((item) => item.selection_order)) + 1;
    }
    shot.selected_source_uids.push(uid);
  } else {
    shot.selected_source_uids.splice(memberIndex, 1);
    const retainedByAnotherShot = routing.shots.some((item) => (
      item !== shot && item.selected_source_uids.includes(uid)
    ));
    if (!retainedByAnotherShot) {
      asset.selected = false;
      asset.selection_order = 0;
      compactSelectionOrder(state.assets);
    }
  }
  shot.media_count = 0;
  shot.metadata_sha256 = "";
  shot.media_sha256 = "";
  bumpImageAssetShotRouting(routing, shot);
  return true;
}

export function hmbReconcileImageAssetShotRouting(state, addedSourceUid = "") {
  const previous = state?.shot_routing && typeof state.shot_routing === "object"
    ? state.shot_routing
    : null;
  const before = new Map(
    (Array.isArray(previous?.shots) ? previous.shots : []).map((shot) => [
      clean(shot?.shot_uuid),
      (Array.isArray(shot?.selected_source_uids) ? shot.selected_source_uids : []).map(clean),
    ]),
  );
  const routing = ensureImageAssetShotRouting(state);
  if (!routing) return false;
  const active = routing.shots.find((shot) => shot.shot_uuid === routing.active_shot_uuid);
  const added = clean(addedSourceUid);
  if (
    added
    && active
    && selectedAssets(state).some((asset) => clean(asset.source_uid) === added)
    && !active.selected_source_uids.includes(added)
    && active.selected_source_uids.length < MAX_SHOT_IMAGES
  ) active.selected_source_uids.push(added);
  let changed = false;
  routing.shots.forEach((shot) => {
    const old = before.get(shot.shot_uuid) || [];
    if (JSON.stringify(old) === JSON.stringify(shot.selected_source_uids)) return;
    shot.media_count = 0;
    shot.metadata_sha256 = "";
    shot.media_sha256 = "";
    shot.revision = Math.max(0, Math.floor(Number(shot.revision) || 0) + 1);
    changed = true;
  });
  if (changed) routing.generation = Math.max(1, Math.floor(Number(routing.generation) || 1) + 1);
  return changed;
}

export function hmbImageAssetSelectionSnapshot(state) {
  if (!state || !Array.isArray(state.assets)) return [];
  return selectedAssets(state).map((asset) => ({
    asset_library_id: clean(asset.asset_library_id),
    selection_order: Math.max(0, Number(asset.selection_order) || 0),
  }));
}

export function hmbRestoreImageAssetSelectionSnapshot(state, snapshot) {
  if (!state || !Array.isArray(state.assets)) return state;
  const selectedById = new Map(
    (Array.isArray(snapshot) ? snapshot : [])
      .map((item) => [
        clean(item?.asset_library_id),
        Math.max(0, Number(item?.selection_order) || 0),
      ])
      .filter(([key, order]) => key && order > 0),
  );
  let restoredCount = 0;
  state.assets.forEach((asset) => {
    const order = selectedById.get(clean(asset.asset_library_id)) || 0;
    asset.selected = order > 0 && hmbImageAssetCanSelect(asset);
    asset.selection_order = asset.selected ? order : 0;
    if (asset.selected) restoredCount += 1;
  });
  compactSelectionOrder(state.assets);
  if (state.status && typeof state.status === "object") {
    state.status.selected_count = restoredCount;
  }
  return state;
}

export function hmbImageAssetAuthorityStamp(state) {
  return imageAssetAuthorityStamp(state);
}

export function hmbMergeImageAssetSelectionDelta(
  authoritativeValue,
  baseSelection,
  localValue,
) {
  const authoritative = normalizeState(authoritativeValue);
  const local = normalizeState(localValue);
  const baseById = new Map(
    (Array.isArray(baseSelection) ? baseSelection : [])
      .map((item) => [
        clean(item?.asset_library_id),
        Math.max(0, Number(item?.selection_order) || 0),
      ])
      .filter(([key]) => key),
  );
  const localById = new Map(
    hmbImageAssetSelectionSnapshot(local)
      .map((item) => [item.asset_library_id, item.selection_order]),
  );
  const authoritativeById = new Map(
    authoritative.assets.map((asset) => [clean(asset.asset_library_id), asset]),
  );
  const changedKeys = new Set([...baseById.keys(), ...localById.keys()]);

  changedKeys.forEach((key) => {
    const asset = authoritativeById.get(key);
    if (!asset) return;
    const wasSelected = baseById.has(key);
    const isSelected = localById.has(key);
    if (wasSelected !== isSelected) {
      asset.selected = isSelected && hmbImageAssetCanSelect(asset);
      asset.selection_order = asset.selected ? localById.get(key) : 0;
      return;
    }
    if (
      isSelected
      && asset.selected
      && baseById.get(key) !== localById.get(key)
    ) {
      asset.selection_order = localById.get(key);
    }
  });
  compactSelectionOrder(authoritative.assets);
  // Shot membership is node-local UI intent just like the master selection.
  // Preserve it across a delayed catalog echo, then filter it against the
  // authoritative master assets during normalization.
  authoritative.shot_routing = local.shot_routing;
  authoritative.shot_hierarchy = local.shot_hierarchy;
  return normalizeState(authoritative);
}

export function hmbImageAssetCanSelect(asset) {
  return Boolean(
    asset
    && (
      clean(asset.source_kind).toLowerCase() === "user"
      || Boolean(asset.registered)
    )
  );
}

export function hmbMoveSelectedAsset(state, sourceKey, targetKey) {
  if (!state || !Array.isArray(state.assets)) return false;
  const ordered = selectedAssets(state);
  const from = ordered.findIndex((asset) => asset.asset_library_id === clean(sourceKey));
  const to = ordered.findIndex((asset) => asset.asset_library_id === clean(targetKey));
  if (from < 0 || to < 0 || from === to) return false;
  const [moved] = ordered.splice(from, 1);
  ordered.splice(to, 0, moved);
  ordered.forEach((asset, index) => {
    asset.selection_order = index + 1;
  });
  return true;
}

function hmbNormalizeImageAssetRevision(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(MAX_IMAGE_ASSET_REVISION, Math.floor(parsed)));
}

function hmbRememberImageAssetRevisionState(container, state, local = false) {
  if (!container || !state) return;
  const scanRevision = hmbNormalizeImageAssetRevision(state.scan_revision);
  const uiEditRevision = hmbNormalizeImageAssetRevision(
    state[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
  );
  container.__hmbImageAssetCurrentScanRevision = scanRevision;
  container.__hmbImageAssetCurrentUiEditRevision = uiEditRevision;
  if (local) {
    container.__hmbImageAssetLatestLocalUiEditRevision = Math.max(
      hmbNormalizeImageAssetRevision(
        container.__hmbImageAssetLatestLocalUiEditRevision,
      ),
      uiEditRevision,
    );
  }
}

function hmbNextImageAssetUiEditRevision(container, state) {
  return Math.min(
    MAX_IMAGE_ASSET_REVISION,
    Math.max(
      hmbNormalizeImageAssetRevision(state?.[IMAGE_ASSET_UI_EDIT_REVISION_KEY]),
      hmbNormalizeImageAssetRevision(
        container?.__hmbImageAssetLatestLocalUiEditRevision,
      ),
    ) + 1,
  );
}

function hmbImageAssetRevisionDisposition(container, incomingState) {
  if (!container || !incomingState) return "unknown";
  const hasCurrentScan = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbImageAssetCurrentScanRevision",
  );
  const incomingScan = hmbNormalizeImageAssetRevision(incomingState.scan_revision);
  const currentScan = hmbNormalizeImageAssetRevision(
    container.__hmbImageAssetCurrentScanRevision,
  );
  if (hasCurrentScan && incomingScan > currentScan) return "authoritative";
  if (hasCurrentScan && incomingScan < currentScan) return "stale";

  const hasCurrentUi = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbImageAssetCurrentUiEditRevision",
  );
  const hasLatestLocalUi = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbImageAssetLatestLocalUiEditRevision",
  );
  if (!hasCurrentUi && !hasLatestLocalUi) return "unknown";
  const latestUi = Math.max(
    hmbNormalizeImageAssetRevision(container.__hmbImageAssetCurrentUiEditRevision),
    hmbNormalizeImageAssetRevision(container.__hmbImageAssetLatestLocalUiEditRevision),
  );
  const incomingUi = hmbNormalizeImageAssetRevision(
    incomingState[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
  );
  if (incomingUi < latestUi) return "stale";
  if (incomingUi > latestUi) return "authoritative";
  return "current";
}

function hmbForgetImageAssetStateEcho(container, publicationToken = null) {
  if (!container) return false;
  const prior = Array.isArray(container.__hmbImageAssetPendingStateEchoes)
    ? container.__hmbImageAssetPendingStateEchoes
    : [];
  const next = publicationToken == null
    ? []
    : prior.filter((item) => item?.publicationToken !== publicationToken);
  if (next.length) container.__hmbImageAssetPendingStateEchoes = next;
  else delete container.__hmbImageAssetPendingStateEchoes;
  if (!next.length && container.__hmbImageAssetStateEchoTimer != null) {
    try { clearTimeout(container.__hmbImageAssetStateEchoTimer); } catch (_error) {}
    delete container.__hmbImageAssetStateEchoTimer;
  }
  return next.length !== prior.length;
}

function hmbRememberImageAssetStateEcho(container, value, publicationToken, compact = false) {
  if (!container || typeof value !== "string") return false;
  const prior = Array.isArray(container.__hmbImageAssetPendingStateEchoes)
    ? container.__hmbImageAssetPendingStateEchoes
    : [];
  container.__hmbImageAssetPendingStateEchoes = [
    ...prior.filter((item) => item?.value !== value),
    { value, publicationToken, compact },
  ].slice(-16);
  if (container.__hmbImageAssetStateEchoTimer != null) {
    try { clearTimeout(container.__hmbImageAssetStateEchoTimer); } catch (_error) {}
  }
  if (typeof setTimeout === "function") {
    container.__hmbImageAssetStateEchoTimer = setTimeout(() => {
      hmbForgetImageAssetStateEcho(container);
    }, IMAGE_ASSET_ECHO_EXPIRY_MS);
  }
  return true;
}

function imageAssetCompactEditEcho(container, value, request = parseValue(value)) {
  if (request?.schema !== IMAGE_ASSET_EDIT_SCHEMA) return null;
  // The host can optimistically echo onChange's request before Python expands
  // it into a canonical state. This command has no assets/projects and must
  // never replace the retained catalog or advance its authority clocks.
  const wire = typeof value === "string" ? value : JSON.stringify(request);
  const known = container?.__hmbImageAssetPendingStateEchoes?.some?.(
    (entry) => entry?.compact && entry.value === wire,
  );
  return {
    current: Boolean(known && hmbImageAssetRevisionDisposition(container, request) !== "stale"),
  };
}

export function hmbConsumeImageAssetStateEcho(container, nextProps = {}) {
  if (!container) return false;
  const retainedIncomingState = container.__hmbImageAssetIncomingState;
  delete container.__hmbImageAssetIncomingState;
  const commandEcho = isCanonicalImageAssetState(retainedIncomingState)
    ? null : imageAssetCompactEditEcho(container, nextProps?.value);
  if (commandEcho) {
    container.__hmbImageAssetLastConsumedEchoWasStale = !commandEcho.current;
    // Keep the pending entry: the later full canonical response is the actual
    // acknowledgement, and must still be matched against this publication.
    return true;
  }
  container.__hmbImageAssetLastConsumedEchoWasStale = false;
  delete container.__hmbImageAssetIncomingSerialized;
  let incomingState = null;
  try {
    incomingState = isCanonicalImageAssetState(retainedIncomingState)
      ? retainedIncomingState
      : normalizeState(nextProps?.value);
  } catch (_error) {
    return false;
  }
  const disposition = hmbImageAssetRevisionDisposition(container, incomingState);
  if (disposition === "stale") {
    container.__hmbImageAssetLastConsumedEchoWasStale = true;
    return true;
  }
  if (disposition === "authoritative") {
    hmbForgetImageAssetStateEcho(container);
    return false;
  }
  const pending = container?.__hmbImageAssetPendingStateEchoes;
  if (!Array.isArray(pending) || !pending.length) {
    return false;
  }
  if (pending.some((item) => item?.compact)) {
    const compact = hmbBuildImageAssetCompactEdit(
      incomingState, imageAssetEditCatalogIdentity(incomingState),
    );
    const incomingCompact = compact ? JSON.stringify(compact) : "";
    const match = pending.find((item) => item?.compact && item.value === incomingCompact);
    if (match) {
      hmbForgetImageAssetStateEcho(container, match.publicationToken);
      return true;
    }
  }
  let incoming = "";
  try {
    incoming = JSON.stringify(incomingState);
    // applyProps reuses this exact canonical serialization when the value is
    // not an echo, avoiding a second full-catalog JSON walk.
    container.__hmbImageAssetIncomingSerialized = incoming;
  } catch (_error) {
    return false;
  }
  const match = pending.find((item) => item?.value === incoming);
  if (!match) return false;
  delete container.__hmbImageAssetIncomingSerialized;
  hmbForgetImageAssetStateEcho(container, match.publicationToken);
  return true;
}

function imageAssetEditCatalogIdentity(state) {
  return {
    catalog_root: clean(state?.catalog_root), project_root: clean(state?.project_root),
    project_uid: clean(state?.project_uid), project_cache_uid: clean(state?.project_cache_uid),
    manifest_signature: clean(state?.manifest_signature), folder_signature: clean(state?.folder_signature),
    scan_revision: hmbNormalizeImageAssetRevision(state?.scan_revision),
  };
}

export function hmbBuildImageAssetCompactEdit(state, acceptedIdentity) {
  if (state?.edit_transport_schema !== IMAGE_ASSET_EDIT_SCHEMA || !acceptedIdentity) return null;
  const identity = imageAssetEditCatalogIdentity(state);
  if (Object.keys(identity).some((field) => identity[field] !== acceptedIdentity[field])) return null;
  const edits = {};
  for (const field of [
    "root_edit_enabled", "selected_folder_path", "expanded_folders", "selected_main_type",
    "selected_sub_type", "selected_source_view", "search", "language", "asset_view_mode",
    "refresh_revision", "thumbnail_request", "asset_registration_request",
    "asset_cleanup_request", "disconnect_import_uid", "shot_routing", "shot_hierarchy", "shot_hierarchy_request",
    "image_bash_workspace", "image_bash_active", "image_bash_workspace_request",
  ]) edits[field] = state[field];
  return {
    schema: IMAGE_ASSET_EDIT_SCHEMA, version: 1,
    catalog_identity: identity, scan_revision: identity.scan_revision,
    [IMAGE_ASSET_UI_EDIT_REVISION_KEY]: state[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
    thumbnail_revision: hmbNormalizeImageAssetRevision(state?.thumbnail_revision),
    selected_source_uids: selectedAssets(state).map((asset) => asset.source_uid), edits,
  };
}

export function hmbPublishImageAssetState(
  container,
  props,
  state,
  onFailure = null,
  options = {},
) {
  // Explicit commands and non-batched transports are ordering boundaries. A
  // visible optimistic Shot edit must become host authority before the command
  // publishes its following state. The coordinator marks its own callback as
  // running, preventing recursive flush when that callback reaches here.
  if (
    container?.__hmbImageAssetSelectionCommitPending
    && !container.__hmbImageAssetSelectionCommitRunning
  ) {
    hmbFlushImageAssetSelectionCommit(container);
    state = container.__hmbImageAssetLatestState || state;
  }
  hmbClearImageAssetTransportRetry(container);
  const normalized = isCanonicalImageAssetState(state) ? state : normalizeState(state);
  const revisionBaseline = {
    currentScanRevision: container?.__hmbImageAssetCurrentScanRevision,
    currentUiEditRevision: container?.__hmbImageAssetCurrentUiEditRevision,
    latestLocalUiEditRevision: container?.__hmbImageAssetLatestLocalUiEditRevision,
  };
  const preserveUiEditRevision = options?.preserveUiEditRevision === true;
  const nextUiEditRevision = preserveUiEditRevision
    ? Math.max(
        hmbNormalizeImageAssetRevision(normalized[IMAGE_ASSET_UI_EDIT_REVISION_KEY]),
        hmbNormalizeImageAssetRevision(container?.__hmbImageAssetCurrentUiEditRevision),
        hmbNormalizeImageAssetRevision(container?.__hmbImageAssetLatestLocalUiEditRevision),
      )
    : hmbNextImageAssetUiEditRevision(container, normalized);
  normalized[IMAGE_ASSET_UI_EDIT_REVISION_KEY] = nextUiEditRevision;
  hmbRememberImageAssetRevisionState(container, normalized, !preserveUiEditRevision);
  const compactEdit = hmbBuildImageAssetCompactEdit(
    normalized, container?.__hmbImageAssetAcceptedEditCatalogIdentity,
  );
  const value = JSON.stringify(compactEdit || normalized);
  if (container) {
    // Cache only the exact canonical snapshot that is about to become host
    // authority. Live state remains mutable; callers may reuse this string only
    // while no optimistic commit is pending and both revision clocks still
    // match, which makes the cache an immutable publication snapshot rather
    // than an object-identity shortcut.
    container.__hmbImageAssetCanonicalSerialization = {
      state: normalized,
      scanRevision: hmbNormalizeImageAssetRevision(normalized.scan_revision),
      uiEditRevision: hmbNormalizeImageAssetRevision(
        normalized[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
      ),
      value: compactEdit ? "" : value,
    };
  }
  const publicationToken = ++imageAssetPublicationSequence;
  if (container) container.__hmbImageAssetPublicationOwner = publicationToken;
  if (options?.suppressMatchingEcho === true) {
    hmbRememberImageAssetStateEcho(container, value, publicationToken, Boolean(compactEdit));
  }
  let attemptCount = 0;
  const maxRetries = typeof onFailure === "function" ? 0 : 1;
  const scheduleRetry = () => {
    if (
      !container
      || container.__hmbImageAssetPublicationOwner !== publicationToken
      || attemptCount > maxRetries
      || typeof setTimeout !== "function"
    ) {
      return false;
    }
    const timer = setTimeout(() => {
      if (container.__hmbImageAssetTransportRetryTimer !== timer) return;
      container.__hmbImageAssetTransportRetryTimer = null;
      if (container.__hmbImageAssetPublicationOwner !== publicationToken) return;
      attemptPublish();
    }, IMAGE_ASSET_TRANSPORT_RETRY_MS);
    container.__hmbImageAssetTransportRetryTimer = timer;
    return true;
  };
  const fail = (error) => {
    if (!container || container.__hmbImageAssetPublicationOwner !== publicationToken) {
      return false;
    }
    hmbForgetImageAssetStateEcho(container, publicationToken);
    container.__hmbImageAssetLastPublishError = {
      message: String(error?.message || error || "Image asset state publication failed"),
      publicationToken,
      at: Date.now(),
    };
    try { console?.error?.("[HMBImageAssetLibrary] state publication failed", error); } catch (_e) {}
    if (typeof onFailure === "function") {
      try { onFailure(error, normalized); } catch (_error) {}
    } else {
      // Generic semantic actions have already updated their local retained
      // state. Retry the exact canonical payload once on the next task so a
      // transient host transport failure cannot leave backend/output state old.
      const retryScheduled = scheduleRetry();
      if (!retryScheduled) {
        // The failed revision never became host authority. Restore the
        // pre-publication watermark so a canonical backend echo can recover
        // the optimistic generic control rather than being rejected as stale.
        normalized[IMAGE_ASSET_UI_EDIT_REVISION_KEY] = hmbNormalizeImageAssetRevision(
          revisionBaseline.currentUiEditRevision
            ?? normalized[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
        );
        container.__hmbImageAssetCurrentScanRevision =
          revisionBaseline.currentScanRevision;
        container.__hmbImageAssetCurrentUiEditRevision =
          revisionBaseline.currentUiEditRevision;
        container.__hmbImageAssetLatestLocalUiEditRevision =
          revisionBaseline.latestLocalUiEditRevision;
      }
    }
    hmbShowImageAssetTransportError(container, error, normalized);
    return false;
  };
  const succeed = () => {
    if (container?.__hmbImageAssetPublicationOwner === publicationToken) {
      delete container.__hmbImageAssetLastPublishError;
      hmbClearImageAssetTransportError(container);
      try { options?.onSuccess?.(normalized); } catch (_error) {}
    }
    return true;
  };
  const attemptPublish = () => {
    if (!container || container.__hmbImageAssetPublicationOwner !== publicationToken) {
      return false;
    }
    attemptCount += 1;
    if (!props || typeof props.onChange !== "function") return succeed();
    try {
      const result = props.onChange(value);
      if (result && typeof result.then === "function") {
        Promise.resolve(result).then(succeed, fail);
      } else {
        succeed();
      }
    } catch (error) {
      fail(error);
    }
    return true;
  };
  attemptPublish();
  return normalized;
}

function hmbClearImageAssetTransportRetry(container) {
  if (!container) return false;
  const timer = container.__hmbImageAssetTransportRetryTimer;
  const hadTimer = timer !== null && timer !== undefined;
  try { if (hadTimer) clearTimeout(timer); } catch (_error) {}
  try { container.__hmbImageAssetTransportRetryTimer = null; } catch (_error) {}
  return hadTimer;
}

export function hmbInvalidateImageAssetPublication(container) {
  hmbClearImageAssetTransportRetry(container);
  const publicationToken = ++imageAssetPublicationSequence;
  if (container) container.__hmbImageAssetPublicationOwner = publicationToken;
  return publicationToken;
}

function emit(props, state, container = null, onFailure = null, options = {}) {
  return hmbPublishImageAssetState(container, props, state, onFailure, options);
}

function hmbCachedImageAssetSerialization(container, state) {
  const cached = container?.__hmbImageAssetCanonicalSerialization;
  if (
    !cached
    || cached.state !== state
    || container.__hmbImageAssetSelectionCommitPending
    || typeof container.__hmbImageAssetSearchDraft === "string"
    || clean(state?.thumbnail_request?.request_id)
    || Boolean(state?.thumbnail_busy)
    || hmbNormalizeImageAssetRevision(state?.scan_revision) !== cached.scanRevision
    || hmbNormalizeImageAssetRevision(state?.[IMAGE_ASSET_UI_EDIT_REVISION_KEY])
      !== cached.uiEditRevision
  ) return "";
  return typeof cached.value === "string" ? cached.value : "";
}

export function hmbDeferImageAssetPropsDuringRegistration(container, nextProps = {}) {
  if (!container?.__hmbImageAssetRegistrationDraft) return false;
  container.__hmbImageAssetDeferredProps = nextProps || {};
  return true;
}

export function hmbTakeDeferredImageAssetProps(container) {
  if (!container) return null;
  const deferred = container.__hmbImageAssetDeferredProps || null;
  delete container.__hmbImageAssetDeferredProps;
  return deferred;
}

export function hmbUpdateImageAssetPropsReference(current, next, preserveValue = false) {
  const target = current && typeof current === "object" ? current : {};
  const authoritativeValue = target.value;
  const replacement = next && typeof next === "object"
    ? (next === target ? { ...next } : next)
    : {};
  Object.keys(target).forEach((key) => { delete target[key]; });
  Object.assign(target, replacement);
  if (preserveValue) target.value = authoritativeValue;
  return target;
}

function imageAssetProjectPathKey(value) {
  const path = clean(value).replaceAll("\\", "/");
  // Display comparison only: retain drive/absolute roots while ignoring a
  // trailing directory separator. Never rewrite backend project authority.
  return (/^(?:[a-z]:)?\/+$/i.test(path) ? path : path.replace(/\/+$/, "")).toLowerCase();
}

function imageAssetProjectFolderName(value) {
  const parts = clean(value).replaceAll("\\", "/").split("/").filter(Boolean);
  if (parts.at(-1)?.toLowerCase() === "ai_ct_image") parts.pop();
  return parts.at(-1) || "";
}

function projectOptions(state) {
  const options = [`<option value="">${escapeHtml(imageAssetText(state, "select_project"))}</option>`];
  const selectedPath = clean(state.project_root).replaceAll("\\", "/");
  const selectedKey = imageAssetProjectPathKey(selectedPath);
  let hasSelected = false;
  state.projects.forEach((project) => {
    const selected = !hasSelected && imageAssetProjectPathKey(project.path) === selectedKey;
    if (selected) hasSelected = true;
    options.push(
      `<option value="${escapeHtml(project.path)}" ${selected ? "selected" : ""}>${escapeHtml(project.name)}</option>`,
    );
  });
  if (selectedPath && !hasSelected) {
    // A partial catalog may omit the current path during a scan. Render its
    // existing selection without adding a project record or fabricating UID.
    const label = hmbImageAssetProjectDisplayName(state)
      || imageAssetProjectFolderName(selectedPath) || selectedPath;
    options.push(`<option value="${escapeHtml(selectedPath)}" selected disabled data-project-selection-display>${escapeHtml(label)}</option>`);
  }
  return options.join("");
}

export function hmbImageAssetProjectDisplayName(state) {
  const resolvedName = clean(state?.project_id);
  if (resolvedName) return resolvedName;
  const selectedPath = imageAssetProjectPathKey(state?.project_root);
  if (!selectedPath) return "";
  const project = (Array.isArray(state?.projects) ? state.projects : []).find((item) => (
    imageAssetProjectPathKey(item?.path) === selectedPath
  ));
  // A selected catalog entry already supplies its display name while the scan
  // resolves media authority. Keep that name out of state: UID/cache/manifest
  // ownership must still come only from the backend's completed snapshot.
  return project ? clean(project.name) || clean(project.project_id) : "";
}

function buildFolderTree(state) {
  const projectAssets = state.assets.filter((asset) => asset.source_kind === "project");
  const root = {
    key: ROOT_FOLDER_KEY,
    path: "",
    label: hmbImageAssetProjectDisplayName(state) || imageAssetText(state, "select_project"),
    children: [],
    assetCount: projectAssets.length,
  };
  const byPath = new Map([["", root]]);
  state.folders.filter((folderPath) => !isUserImportFolder(folderPath)).forEach((folderPath) => {
    const parentPath = folderPath.includes("/")
      ? folderPath.slice(0, folderPath.lastIndexOf("/"))
      : "";
    const node = {
      key: folderPath,
      path: folderPath,
      label: folderPath.split("/").pop(),
      children: [],
      assetCount: 0,
    };
    byPath.set(folderPath, node);
    (byPath.get(parentPath) || root).children.push(node);
  });
  const directCounts = new Map();
  projectAssets.forEach((asset) => {
    const relative = clean(asset.relative_path).replaceAll("\\", "/");
    const folder = relative.includes("/") ? relative.slice(0, relative.lastIndexOf("/")) : "";
    directCounts.set(folder, (directCounts.get(folder) || 0) + 1);
  });
  const finalize = (node) => {
    node.children.sort((left, right) => left.label.localeCompare(right.label, undefined, {
      numeric: true,
      sensitivity: "base",
    }));
    node.assetCount = (directCounts.get(node.path) || 0)
      + node.children.reduce((total, child) => total + finalize(child), 0);
    if(state.catalog_page?.folder_counts && Number.isFinite(state.catalog_page.folder_counts[node.path]))node.assetCount=state.catalog_page.folder_counts[node.path];
    return node.assetCount;
  };
  finalize(root);
  const importedAssets = state.assets.filter((asset) => asset.source_kind === "user");
  if (importedAssets.length || Number(state.catalog_page && state.status?.user_asset_count)>0) {
    root.children.push({
      key: "$imports",
      path: "",
      label: imageAssetText(state, "import_in"),
      sourceView: "user",
      children: [],
      assetCount: state.catalog_page ? Number(state.status?.user_asset_count)||0 : importedAssets.length,
    });
  }
  return root;
}

function renderFolderNode(node, state, depth = 0) {
  const expanded = state.expanded_folders.includes(node.key);
  const sourceView = node.sourceView === "user" ? "user" : "project";
  const selected = sourceView === "user"
    ? state.selected_source_view === "user"
    : state.selected_source_view !== "user" && state.selected_folder_path === node.path;
  const hasChildren = node.children.length > 0;
  const row = `
    <button class="tree-row ${node.key === ROOT_FOLDER_KEY ? "root" : ""} ${selected ? "active" : ""}"
      data-folder-path="${escapeHtml(node.path)}"
      data-folder-key="${escapeHtml(node.key)}"
      data-source-view="${sourceView}"
      data-has-children="${hasChildren ? "1" : "0"}"
      style="--tree-depth:${depth}">
      <i>${hasChildren ? (expanded ? "▾" : "▸") : "·"}</i>
      <span>${escapeHtml(node.label)}</span><b>${node.assetCount}</b>
    </button>`;
  if (!hasChildren || !expanded) return row;
  return row + node.children.map((child) => renderFolderNode(child, state, depth + 1)).join("");
}

function folderAssets(state) {
  if (state.selected_source_view === "user") {
    return state.assets.filter((asset) => asset.source_kind === "user");
  }
  const folder = normalizeRelativeFolder(state.selected_folder_path).toLowerCase();
  return state.assets.filter((asset) => {
    if (asset.source_kind !== "project") return false;
    const relative = clean(asset.relative_path).replaceAll("\\", "/").toLowerCase();
    if (folder && !(relative === folder || relative.startsWith(`${folder}/`))) return false;
    return true;
  });
}

function hmbCatalogPage(value) {
  if(!value || value.version!==1 || !Array.isArray(value.asset_library_ids)
    || value.asset_library_ids.length>80 || !Number.isSafeInteger(value.total) || value.total<0
    || !Number.isSafeInteger(value.offset) || value.offset<0 || !Number.isSafeInteger(value.limit)
    || value.limit<1 || value.limit>80 || !Number.isSafeInteger(value.sequence) || value.sequence<1
    || !clean(value.session_id))return null;
  return {...value,asset_library_ids:uniqueStrings(value.asset_library_ids).slice(0,80)};
}

function hmbImageAssetCatalogFingerprint(assets) {
  const fields=["asset_id","image_name","relative_path","image_main_type","image_sub_type","source_kind","asset_library_id","source_uid"];
  return JSON.stringify((Array.isArray(assets)?assets:[]).map(asset=>fields.map(key=>clean(asset?.[key]))));
}

function hmbCatalogPageContext(state) {
  return {runtime_instance_id:clean(state?.shot_routing?.publisher_instance_uuid),
    project_uid:clean(state?.project_uid),project_cache_uid:clean(state?.project_cache_uid),
    manifest_signature:clean(state?.manifest_signature),folder_signature:clean(state?.folder_signature),
    scan_revision:hmbNormalizeImageAssetRevision(state?.scan_revision)};
}

function hmbCatalogPageContextKey(state) {return JSON.stringify(hmbCatalogPageContext(state));}

function hmbImageAssetLocalPageProjection(value,current,container) {
  const control=container?.__hmbImageAssetPageControl;
  if(control && Array.isArray(value?.assets) && hmbImageAssetRevisionDisposition(container,value)!=="stale") {
    control.fullState=value;
    const fingerprint=hmbImageAssetCatalogFingerprint(value.assets);
    if(fingerprint!==control.fingerprint) {
      control.fingerprint=fingerprint;
      clearTimeout(control.timer);control.pending=null;control.key="";control.acceptedContext="";control.disabledContext="";
      return value;
    }
  }
  const page=hmbCatalogPage(current?.catalog_page);
  if(!page || !Array.isArray(value?.assets) || hmbCatalogPageContextKey(value)!==hmbCatalogPageContextKey(current))return value;
  const wanted=new Set(page.asset_library_ids);
  const workspaceUids=imageBashSourceUids(value);
  return {...value,catalog_page:page,assets:value.assets.filter(asset=>asset.selected || workspaceUids.has(asset.source_uid) || wanted.has(asset.asset_library_id))};
}

export function hmbRequestImageAssetCatalogPage(container,state,offset=0) {
  const control=container?.__hmbImageAssetPageControl;
  const context=hmbCatalogPageContext(state),entry=imageAssetThumbnailBridgeRegistry()?.get(context.runtime_instance_id);
  if(!control || control.disabledContext===hmbCatalogPageContextKey(state)
    || entry?.catalogPageVersion!==1 || !context.project_uid || !entry.dispatch)return false;
  const request={schema:"hmb-image-asset-thumbnail-bridge",version:1,operation:"catalog_page",phase:"request",...context,
    session_id:control.session,query:String(state.search||"").slice(0,256),folder:normalizeRelativeFolder(state.selected_folder_path),
    source_view:state.selected_source_view==="user"?"user":"project",offset:Math.max(0,Number(offset)||0),limit:80};
  const key=JSON.stringify(request);
  if(control.key===key && control.pending)return true;
  const page=hmbCatalogPage(state.catalog_page);
  if(!control.pending && page && page.session_id===control.session && page.query===request.query && page.folder===request.folder
    && page.source_view===request.source_view && page.offset===request.offset && control.acceptedContext===hmbCatalogPageContextKey(state))return false;
  control.sequence+=1;request.sequence=control.sequence;request.request_id=`page-${control.session}-${control.sequence}`;
  control.key=key;control.pending=request;
  clearTimeout(control.timer);
  control.timer=setTimeout(()=>{if(control.pending===request)control.fallback();},15000);
  try{const result=entry.dispatch(request);if(result?.catch)result.catch(()=>{if(control.pending===request)control.fallback();});}
  catch(_error){control.fallback();return true;}
  return true;
}

function hmbInstallImageAssetCatalogPages(container,getState,accept,acceptFallback) {
  const control={session:`${Date.now().toString(36)}-${Math.random().toString(36).slice(2,10)}`,sequence:0,pending:null,key:"",runtime:"",timer:0,
    fingerprint:hmbImageAssetCatalogFingerprint(getState()?.assets),fullState:{...getState()}};
  container.__hmbImageAssetPageControl=control;
  control.fallback=()=>{
    if(container.__hmbImageAssetPageControl!==control)return;
    clearTimeout(control.timer);control.pending=null;control.key="";
    const current=getState();control.disabledContext=hmbCatalogPageContextKey(current);
    if(hmbCatalogPageContextKey(control.fullState)!==hmbCatalogPageContextKey(current))return;
    acceptFallback(control.fullState);
  };
  const wake=()=>{
    const state=getState(),runtime=hmbCatalogPageContext(state).runtime_instance_id;
    if(runtime!==control.runtime){
      const old=imageAssetThumbnailBridgeRegistry()?.get(control.runtime);old?.pageConsumers?.delete(control.session);
      control.runtime=runtime;control.pending=null;control.key="";
    }
    if(!runtime)return;
    const registry=imageAssetThumbnailBridgeRegistry();const entry=registry?.get(runtime)||{};
    if(!(entry.pageConsumers instanceof Map))entry.pageConsumers=new Map();
    entry.pageConsumers.set(control.session,{consumer:receive,wake});registry?.set(runtime,entry);
    if(container.__hmbImageAssetSearchTimer!=null)return;
    hmbRequestImageAssetCatalogPage(container,state,container.__hmbImageAssetRenderOffset||0);
  };
  const receive=result=>{
    const request=control.pending,state=getState();
    if(!request || result?.operation!=="catalog_page" || result.phase!=="result"
      || result.session_id!==control.session || result.request_id!==request.request_id || result.sequence!==request.sequence)return false;
    if(result.outcome!=="ready"){control.fallback();return false;}
    if(JSON.stringify(hmbCatalogPageContext(result.state))!==JSON.stringify(hmbCatalogPageContext(state)))return false;
    const page=hmbCatalogPage(result.state?.catalog_page);if(!page || page.session_id!==control.session || page.sequence!==request.sequence)return false;
    if(page.query!==request.query || page.folder!==request.folder || page.source_view!==request.source_view)return false;
    if(String(state.search||"")!==request.query || normalizeRelativeFolder(state.selected_folder_path)!==request.folder
      || state.selected_source_view!==request.source_view)return false;
    clearTimeout(control.timer);control.pending=null;control.key="";control.acceptedContext=hmbCatalogPageContextKey(state);
    accept(result.state);return true;
  };
  return {wake,cleanup(){clearTimeout(control.timer);control.pending=null;const entry=imageAssetThumbnailBridgeRegistry()?.get(control.runtime);
    entry?.pageConsumers?.delete(control.session);delete container.__hmbImageAssetPageControl;}};
}

function isUserImportFolder(value) {
  const parts = normalizeRelativeFolder(value)
    .split("/")
    .filter(Boolean)
    .map((part) => part.toLowerCase().replace(/[^a-z0-9]+/g, ""));
  return Boolean(
    parts.length
    && (
      ["user", "userimports"].includes(parts[0])
      || (parts[0] === "custom" && ["user", "userimports"].includes(parts[1] || ""))
    )
  );
}

function assetSearchText(asset) {
  return [
    asset.asset_id,
    asset.image_name,
    asset.relative_path,
    asset.image_main_type,
    asset.image_sub_type,
  ].map((value) => clean(value).toLowerCase()).join("\n");
}

function assetMatchesSearch(asset, search) {
  const needle = String(search || "").trim().toLowerCase();
  return !needle || assetSearchText(asset).includes(needle);
}

const IMAGE_ASSET_SCROLL_SELECTORS = [".tree", ".asset-scroll", ".shot-stack", ".tray-scroll", ".asset-passport"];
const IMAGE_ASSET_FOCUSABLE_SELECTOR = "input,select,textarea,button,[tabindex]";

function imageAssetViewKey(state) {
  return `${clean(state?.project_root).toLowerCase()}\n${normalizeRelativeFolder(state?.selected_folder_path).toLowerCase()}`;
}

function imageAssetFocusDescriptor(container) {
  const active = typeof document !== "undefined" ? document.activeElement : null;
  if (!active || !container?.contains?.(active)) return null;
  const directAttributes = [
    "data-search",
    "data-project-set",
    "data-language-toggle",
    "data-asset-view-toggle",
    "data-project-reload",
    "data-project-select",
    "data-shot-add",
    "data-shot-tab",
    "data-shot-rename",
    "data-shot-rename-input",
    "data-shot-delete",
    "data-registration-field",
    "data-registration-folder",
    "data-registration-main",
    "data-registration-sub",
    "data-registration-submit",
    "data-refresh-review-cancel",
    "data-refresh-cleanup-start",
    "data-refresh-cleanup-confirm",
  ];
  for (const attribute of directAttributes) {
    if (!active.hasAttribute?.(attribute)) continue;
    const value = active.getAttribute(attribute) || "";
    const matches = [...container.querySelectorAll(`[${attribute}]`)]
      .filter((element) => (element.getAttribute(attribute) || "") === value);
    return {
      kind: "direct",
      attribute,
      value,
      index: Math.max(0, matches.indexOf(active)),
      start: Number.isFinite(Number(active.selectionStart)) ? Number(active.selectionStart) : null,
      end: Number.isFinite(Number(active.selectionEnd)) ? Number(active.selectionEnd) : null,
    };
  }
  const owner = active.closest?.("[data-asset-key],[data-selected-key],[data-registration-backdrop]");
  if (!owner) return null;
  const ownerAttribute = owner.hasAttribute("data-asset-key")
    ? "data-asset-key"
    : owner.hasAttribute("data-selected-key")
      ? "data-selected-key"
      : "data-registration-backdrop";
  const controls = [owner, ...owner.querySelectorAll(IMAGE_ASSET_FOCUSABLE_SELECTOR)];
  return {
    kind: "owned",
    ownerAttribute,
    ownerValue: owner.getAttribute(ownerAttribute) || "",
    index: Math.max(0, controls.indexOf(active)),
  };
}

function captureImageAssetUi(container, state) {
  if (!container?.querySelector) return null;
  const scroll = {};
  IMAGE_ASSET_SCROLL_SELECTORS.forEach((selector) => {
    const element = container.querySelector(selector);
    if (element) scroll[selector] = {
      top: Number(element.scrollTop) || 0,
      left: Number(element.scrollLeft) || 0,
    };
  });
  return { viewKey: imageAssetViewKey(state), scroll, focus: imageAssetFocusDescriptor(container) };
}

function restoreImageAssetUi(container, state, memory) {
  if (!container?.querySelector || !memory) return;
  const sameView = memory.viewKey === imageAssetViewKey(state);
  IMAGE_ASSET_SCROLL_SELECTORS.forEach((selector) => {
    if (!sameView && selector !== ".tray-scroll") return;
    const element = container.querySelector(selector);
    const position = memory.scroll?.[selector];
    if (!element || !position) return;
    try {
      element.scrollTop = Number(position.top) || 0;
      element.scrollLeft = Number(position.left) || 0;
    } catch (_error) {}
  });
  const focus = memory.focus;
  if (!focus) return;
  let target = null;
  if (focus.kind === "direct") {
    const matches = [...container.querySelectorAll(`[${focus.attribute}]`)]
      .filter((element) => (element.getAttribute(focus.attribute) || "") === focus.value);
    target = matches[focus.index] || matches[0] || null;
  } else if (focus.kind === "owned") {
    const owners = [...container.querySelectorAll(`[${focus.ownerAttribute}]`)]
      .filter((element) => (element.getAttribute(focus.ownerAttribute) || "") === focus.ownerValue);
    const owner = owners[0] || null;
    const controls = owner ? [owner, ...owner.querySelectorAll(IMAGE_ASSET_FOCUSABLE_SELECTOR)] : [];
    target = controls[focus.index] || null;
  }
  if (!target || target.disabled || target.hidden) return;
  try { target.focus({ preventScroll: true }); } catch (_error) { try { target.focus(); } catch (__error) {} }
  if (
    Number.isFinite(focus.start)
    && Number.isFinite(focus.end)
    && typeof target.setSelectionRange === "function"
  ) {
    const maximum = String(target.value || "").length;
    try {
      target.setSelectionRange(
        Math.max(0, Math.min(maximum, focus.start)),
        Math.max(0, Math.min(maximum, focus.end)),
      );
    } catch (_error) {}
  }
}

function imageAssetDomKey(node) {
  if (!node || node.nodeType !== 1) return "";
  for (const attribute of [
    "data-hmb-native-identity",
    "data-hmb-native-actions",
    "data-image-bash-instance",
    "data-image-bash-panel",
    "data-asset-key",
    "data-selected-key",
    "data-compact-shot-row",
    "data-compact-asset-key",
    "data-shot-uuid",
    "data-folder-key",
    "data-registration-backdrop",
    "data-refresh-review-backdrop",
    "id",
  ]) {
    if (!node.hasAttribute?.(attribute)) continue;
    return `${node.tagName}:${attribute}:${node.getAttribute(attribute) || ""}`;
  }
  return "";
}

function hmbSyncImageAssetAttributes(current, desired) {
  const desiredNames = new Set(Array.from(desired.attributes || []).map((item) => item.name));
  Array.from(current.attributes || []).forEach((item) => {
    if (
      item.name === "src"
      && current.matches?.("img[data-hmb-compact-src]")
      && desired.matches?.("img[data-hmb-compact-src]")
    ) return;
    if (!desiredNames.has(item.name)) current.removeAttribute?.(item.name);
  });
  Array.from(desired.attributes || []).forEach((item) => {
    if (current.getAttribute?.(item.name) !== item.value) {
      current.setAttribute?.(item.name, item.value);
    }
  });
  if ("disabled" in current) current.disabled = Boolean(desired.disabled);
  if ("checked" in current) current.checked = Boolean(desired.checked);
  if (
    "value" in current
    && current.tagName !== "SELECT"
    && !current.matches?.("[data-search],[data-shot-rename-input]")
    && current.value !== desired.value
  ) current.value = desired.value;
}

export function hmbShouldPreserveImageAssetInlineRename(current, desired) {
  return Boolean(
    current?.nodeType === 1
    && desired?.nodeType === 1
    && current.matches?.("[data-shot-rename-input]")
    && desired.matches?.("[data-shot-name]"),
  );
}

export function hmbImageAssetRenameKeyIsComposing(event) {
  return Boolean(event?.isComposing || Number(event?.keyCode) === 229);
}

// Small retained-mode morph used by structural controls. It preserves the
// mounted root, scroll containers, focused controls, images, and keyed cards;
// unlike innerHTML replacement it cannot flash the entire widget.
export function hmbPatchImageAssetElement(current, desired) {
  if (!current || !desired || current.nodeType !== desired.nodeType) return false;
  if (current.nodeType === 3) {
    if (current.nodeValue !== desired.nodeValue) current.nodeValue = desired.nodeValue;
    return true;
  }
  if (current.nodeType !== 1 || current.tagName !== desired.tagName) return false;
  if (current.matches?.("[data-hmb-native-identity],[data-hmb-native-actions]")
    && desired.matches?.("[data-hmb-native-identity],[data-hmb-native-actions]")) return true;
  hmbSyncImageAssetAttributes(current, desired);

  const original = Array.from(current.childNodes || []);
  const keyed = new Map();
  original.forEach((child) => {
    const key = imageAssetDomKey(child);
    if (key) keyed.set(key, child);
  });
  const retained = new Set();
  let cursor = current.firstChild || null;
  Array.from(desired.childNodes || []).forEach((desiredChild) => {
    let candidate = null;
    let preserveInlineRename = false;
    const key = imageAssetDomKey(desiredChild);
    if (key) candidate = keyed.get(key) || null;
    if (!candidate && cursor && hmbShouldPreserveImageAssetInlineRename(cursor, desiredChild)) {
      candidate = cursor;
      preserveInlineRename = true;
    }
    if (!candidate && cursor && !retained.has(cursor)) {
      const sameText = desiredChild.nodeType === 3 && cursor.nodeType === 3;
      const sameElement = desiredChild.nodeType === 1
        && cursor.nodeType === 1
        && desiredChild.tagName === cursor.tagName
        && !imageAssetDomKey(cursor);
      if (sameText || sameElement) candidate = cursor;
    }
    if (!candidate) candidate = desiredChild.cloneNode?.(true) || null;
    if (!candidate) return;
    if (candidate !== cursor) current.insertBefore?.(candidate, cursor);
    if (candidate !== desiredChild && !preserveInlineRename) {
      hmbPatchImageAssetElement(candidate, desiredChild);
    }
    retained.add(candidate);
    cursor = candidate.nextSibling || null;
  });
  original.forEach((child) => {
    if (!retained.has(child) && child.parentNode === current) child.remove?.();
  });
  // Option nodes are retained by position. Updating their values/selected
  // attributes (or removing an earlier option) can clear or move selection.
  // Apply the desired value only after the final option list is in place.
  if (current.tagName === "SELECT" && current.value !== desired.value) {
    current.value = desired.value;
  }
  return true;
}

export function hmbPatchImageAssetMarkup(container, markup) {
  const ownerDocument = container?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!container || !ownerDocument?.createElement) return false;
  const template = ownerDocument.createElement("template");
  template.innerHTML = String(markup || "");
  const desiredChildren = Array.from(template.content?.childNodes || []);
  const currentChildren = Array.from(container.childNodes || []);
  if (!container.querySelector?.(".hmb-image-assets")) {
    container.replaceChildren?.(...desiredChildren.map((node) => node.cloneNode(true)));
    return true;
  }
  desiredChildren.forEach((desired, index) => {
    const current = currentChildren[index] || null;
    if (current && hmbPatchImageAssetElement(current, desired)) return;
    const replacement = desired.cloneNode(true);
    if (current) current.replaceWith?.(replacement);
    else container.appendChild?.(replacement);
  });
  currentChildren.slice(desiredChildren.length).forEach((node) => node.remove?.());
  return true;
}

function detachReusableImageAssets(container) {
  const imagesBySource = new Map();
  container?.querySelectorAll?.("img[src]").forEach((image) => {
    const source = image.getAttribute("src") || "";
    if (!source) return;
    const queue = imagesBySource.get(source) || [];
    queue.push({
      image,
      fallback: Boolean(image.closest?.(".asset-thumb,.selected-thumb,.passport-photo")?.classList?.contains("fallback")),
    });
    imagesBySource.set(source, queue);
    image.remove?.();
  });
  return imagesBySource;
}

function restoreReusableImageAssets(container, imagesBySource) {
  if (!imagesBySource?.size) return;
  container?.querySelectorAll?.("img[src]").forEach((placeholder) => {
    const queue = imagesBySource.get(placeholder.getAttribute("src") || "");
    const reusable = queue?.shift?.();
    if (!reusable?.image) return;
    if (reusable.fallback) {
      placeholder.closest?.(".asset-thumb,.selected-thumb,.passport-photo")?.classList?.add("fallback");
    }
    placeholder.replaceWith(reusable.image);
  });
}

function imageSource(asset) {
  const thumbnailUrl = clean(asset.thumbnail_url);
  if (/^(data:image\/|https?:\/\/|blob:)/i.test(thumbnailUrl)) return thumbnailUrl;
  const path = clean(asset.path);
  if (!path) return "";
  if (/^(data:image\/|https?:\/\/|blob:)/i.test(path)) return path;
  // Browsers cannot safely load Windows or UNC files from a custom widget.
  // Project assets receive a backend-generated HTTP thumbnail_url instead.
  return "";
}

export function hmbImageAssetImageSource(asset) {
  return imageSource(asset || {});
}

function thumbnailImageMarkup(asset) {
  const source = imageSource(asset);
  const fallback = escapeHtml((asset.extension || ".img").replace(".", "").toUpperCase() || "IMG");
  return source
    ? `<img src="${escapeHtml(source)}" alt="" draggable="false" loading="lazy" decoding="async" fetchpriority="low"/><span>${fallback}</span>`
    : `<span class="thumbnail-placeholder" aria-hidden="true">${imageAssetThumbnailFallbackMarkup(asset)}</span>`;
}

function imageAssetLeafLoaderMarkup() {
  return `<span class="hmb-image-leaf-loader">${Array.from(
    { length: 8 },
    (_unused, index) => `<i style="--leaf-index:${index}"></i>`,
  ).join("")}</span>`;
}

function imageAssetThumbnailFallbackMarkup(asset) {
  return hmbImageAssetThumbnailFailed(asset)
    ? `<span class="hmb-image-thumbnail-unavailable" title="Thumbnail unavailable; use Refresh to retry">!</span>`
    : imageAssetLeafLoaderMarkup();
}

function assetCardThumbnailImageMarkup(asset) {
  const source = imageSource(asset);
  return source
    ? `<img src="${escapeHtml(source)}" alt="" draggable="false" loading="lazy" decoding="async" fetchpriority="low"/>`
    : `<span class="asset-thumb-placeholder" aria-hidden="true">${imageAssetThumbnailFallbackMarkup(asset)}</span>`;
}

export function hmbImageAssetCanRegister(asset) {
  if (!asset || typeof asset !== "object" || asset.registered) return false;
  const sourceKind = clean(asset.source_kind).toLowerCase();
  if (!sourceKind || sourceKind === "project") return true;
  return sourceKind === "user"
    && Number(asset.import_index || 0) > 0;
}

function thumbnailHtml(asset, className = "asset-thumb") {
  const source = imageSource(asset);
  const failed = !source && hmbImageAssetThumbnailFailed(asset);
  return `<div class="${className} ${source ? "" : failed ? "fallback thumbnail-failed" : "fallback thumbnail-loading"}" data-thumbnail-loading="${source || failed ? "false" : "true"}" data-thumbnail-failed="${failed ? "true" : "false"}">${thumbnailImageMarkup(asset)}</div>`;
}

function assetThumbnailHtml(asset, state) {
  const source = imageSource(asset);
  const failed = !source && hmbImageAssetThumbnailFailed(asset);
  const sourceName = clean(asset.image_name) || clean(asset.asset_id) || "Image";
  const add = hmbImageAssetCanRegister(asset)
    ? `<button type="button" class="asset-add" data-asset-add aria-label="${escapeHtml(imageAssetText(state, "add_image_asset"))}">${escapeHtml(imageAssetText(state, "add"))}</button>`
    : "";
  return `
    <div class="asset-thumb ${source ? "" : failed ? "fallback thumbnail-failed" : "fallback thumbnail-loading"}" data-thumbnail-loading="${source || failed ? "false" : "true"}" data-thumbnail-failed="${failed ? "true" : "false"}">
      <div class="asset-thumb-media">${assetCardThumbnailImageMarkup(asset)}${add}</div>
      <div class="asset-thumb-footer"><span class="asset-source-name" title="${escapeHtml(sourceName)}">${escapeHtml(sourceName)}</span></div>
    </div>
  `;
}

function renderAssetCard(asset, selectedCount, search, state, shot = activeImageAssetShot(state)) {
  const dimensions = asset.width && asset.height
    ? `${asset.width} × ${asset.height}`
    : imageAssetText(state, "metadata_pending");
  const selectable = hmbImageAssetCanSelect(asset);
  const selectedForShot = state.image_bash_active ? imageBashSourceUids(state).has(asset.source_uid) : imageAssetShotContains(shot, asset.source_uid);
  const selectionBlocked = selectable && (state.image_bash_active
    ? state.image_bash_workspace.instances.length >= MAX_SELECTED_IMAGES : !selectedForShot && selectedCount >= MAX_SHOT_IMAGES);
  const cardTitle = !selectable
    ? imageAssetText(state, "register_before_select")
    : selectionBlocked
      ? imageAssetText(state, "image_limit")
      : imageAssetText(state, "click_select");
  const unclassified = imageAssetText(state, "unclassified");
  const sourceTypeLabel = clean(asset.image_main_type) === "Select Image Main Type"
    ? unclassified
    : imageAssetTaxonomyLabel(state, asset.image_main_type) || unclassified;
  const subUnassigned = imageAssetText(state, "sub_unassigned");
  const extension = (asset.extension || ".img").replace(".", "").toUpperCase() || "IMG";
  return `
    <article class="asset-card ${selectedForShot ? "selected" : ""} ${selectionBlocked ? "selection-blocked" : ""} ${selectable ? "" : "unregistered"}"
      data-asset-key="${escapeHtml(asset.asset_library_id)}"
      data-asset-registered="${asset.registered ? "1" : "0"}"
      data-search-text="${escapeHtml(assetSearchText(asset))}"
      data-selection-disabled="${selectionBlocked ? "1" : "0"}"
      ${assetMatchesSearch(asset, search) ? "" : "hidden"}
      role="${selectable ? "button" : "group"}" tabindex="0" ${selectable ? `aria-pressed="${selectedForShot ? "true" : "false"}"` : ""}
      title="${escapeHtml(cardTitle)}">
      ${assetThumbnailHtml(asset, state)}
      <div class="asset-content">
        <div class="asset-title">
          <div class="asset-title-copy">
            <span class="asset-state">${escapeHtml(imageAssetText(state, asset.registered ? "project_state" : "unregistered_state"))}</span>
            <small class="asset-id-line" title="${escapeHtml(imageAssetText(state, "asset_id"))}: ${escapeHtml(asset.asset_id)}"><em>${escapeHtml(imageAssetText(state, "asset_id"))}</em><span>${escapeHtml(asset.asset_id)}</span></small>
          </div>
          <span class="asset-extension-badge" title="${escapeHtml(extension)}">${escapeHtml(extension)}</span>
        </div>
        <div class="asset-meta">
          <b title="${escapeHtml(imageAssetText(state, "main_type"))}: ${escapeHtml(sourceTypeLabel)}">${escapeHtml(sourceTypeLabel)}</b>
          <span title="${escapeHtml(imageAssetText(state, "sub_type"))}: ${escapeHtml(imageAssetTaxonomyLabel(state, asset.image_sub_type) || subUnassigned)}">${escapeHtml(imageAssetTaxonomyLabel(state, asset.image_sub_type) || subUnassigned)}</span>
          <span class="asset-location" title="${escapeHtml(`${dimensions} · ${asset.relative_path || asset.media_ref_kind}`)}">${escapeHtml(dimensions)} · ${escapeHtml(asset.relative_path || asset.media_ref_kind)}</span>
        </div>
      </div>
    </article>
  `;
}

export function hmbImageAssetCatalogWindow(
  state,
  limit = IMAGE_ASSET_RENDER_WINDOW,
  offset = 0,
) {
  const page=hmbCatalogPage(state?.catalog_page);
  if(page){const byId=new Map(state.assets.map(asset=>[asset.asset_library_id,asset]));return {
    matches:{length:page.total},rendered:page.asset_library_ids.map(id=>byId.get(id)).filter(Boolean),
    offset:page.offset,limit:page.limit};}
  const matches = folderAssets(state).filter((asset) => assetMatchesSearch(asset, state.search));
  const boundedLimit = Math.min(
    IMAGE_ASSET_RENDER_WINDOW,
    Math.max(1, Math.floor(Number(limit) || IMAGE_ASSET_RENDER_WINDOW)),
  );
  const requestedOffset = Math.max(0, Math.floor(Number(offset) || 0));
  const lastOffset = matches.length
    ? Math.floor((matches.length - 1) / boundedLimit) * boundedLimit
    : 0;
  const boundedOffset = Math.min(requestedOffset, lastOffset);
  return {
    matches,
    rendered: matches.slice(boundedOffset, boundedOffset + boundedLimit),
    limit: boundedLimit,
    offset: boundedOffset,
  };
}

function imageAssetThumbnailContextKey(state) {
  const projectUid = clean(state?.project_cache_uid || state?.project_uid);
  if (!projectUid) return "";
  return [
    projectUid,
    clean(state?.manifest_signature),
    hmbNormalizeImageAssetRevision(state?.scan_revision),
  ].join("\n");
}

function imageAssetThumbnailRuntimeId(state) {
  return clean(state?.shot_routing?.publisher_instance_uuid);
}

function imageAssetThumbnailRequestMatchesState(state, request) {
  return Boolean(
    clean(request?.request_id)
    && clean(request?.project_uid) === clean(state?.project_uid)
    && (!clean(request?.project_cache_uid)
      || clean(request?.project_cache_uid) === clean(state?.project_cache_uid))
    && clean(request?.manifest_signature) === clean(state?.manifest_signature)
    && hmbNormalizeImageAssetRevision(request?.scan_revision)
      === hmbNormalizeImageAssetRevision(state?.scan_revision)
  );
}

export function hmbImageAssetThumbnailRequestIds(
  state,
  limit = IMAGE_ASSET_RENDER_WINDOW,
  offset = 0,
  options = {},
) {
  const canonical = isCanonicalImageAssetState(state) ? state : normalizeState(state);
  const visible = options.includeWindow === false
    ? []
    : hmbImageAssetCatalogWindow(canonical, limit, offset).rendered;
  // Hydrate the project catalog once instead of coupling thumbnail availability
  // to the currently opened folder or Shot. Selected/visible rows keep
  // priority; the remainder drains through successive 64-item post-paint
  // batches, so a 5,000-item catalog never blocks the initial paint.
  const workspaceAssets = hmbImageBashWorkspaceAssets(canonical).map(row => row.asset).filter(Boolean);
  const candidates = options.includeCatalog === false
    ? [...selectedAssets(canonical), ...workspaceAssets, ...visible]
    : [...selectedAssets(canonical), ...workspaceAssets, ...visible, ...canonical.assets];
  const seen = new Set();
  return candidates
    .filter((asset) => {
      const key = clean(asset?.asset_library_id);
      // The project catalog can legitimately contain source_kind="user"
      // assets after they are registered into its User folder. Eligibility is
      // therefore based on persisted project identity, not source_kind. Live
      // IMAGE_IMPORT_IN rows have import_index > 0 or no relative_path and
      // remain browser-owned instead of entering backend hydration.
      const persistedProjectAsset = Number(asset?.import_index || 0) === 0
        && Boolean(clean(asset?.relative_path));
      return key
        && persistedProjectAsset
        && !imageSource(asset)
        && !options.excludeIds?.has(key)
        && !seen.has(key)
        && seen.add(key);
    })
    .map((asset) => clean(asset.asset_library_id))
    .slice(0, IMAGE_ASSET_THUMBNAIL_REQUEST_BATCH);
}

function imageAssetThumbnailRequestTracking(container, state) {
  const contextKey = imageAssetThumbnailContextKey(state);
  if (!container || !contextKey) {
    return { contextKey, requested: new Set(), failed: new Set() };
  }
  if (container.__hmbImageAssetThumbnailContextKey !== contextKey) {
    hmbClearImageAssetThumbnailWatchdog(container);
    const priorPending = clean(container.__hmbImageAssetThumbnailPendingRequestId);
    const priorInflight = container.__hmbImageAssetThumbnailInflight;
    const priorRequested = container.__hmbImageAssetThumbnailRequestedIds;
    if (priorPending && priorInflight instanceof Map) {
      for (const [key, requestId] of priorInflight.entries()) {
        if (clean(requestId) !== priorPending) continue;
        priorInflight.delete(key);
        priorRequested?.delete?.(key);
      }
    }
    container.__hmbImageAssetThumbnailContextKey = contextKey;
    const shared = imageAssetPresentationCacheEntry(state, true);
    // A new catalog revision may change an asset that previously failed or
    // was in flight. Valid cached URLs survive by media signature; unresolved
    // request bookkeeping must not suppress the new revision.
    const sharedAuthority = [
      clean(state?.manifest_signature),
      hmbNormalizeImageAssetRevision(state?.scan_revision),
    ].join("\n");
    if (shared && shared.authorityContext && shared.authorityContext !== sharedAuthority) {
      shared.requested.clear();
      shared.failed.clear();
      shared.errorRetries.clear();
      shared.inflight.clear();
    }
    if (shared) shared.authorityContext = sharedAuthority;
    container.__hmbImageAssetThumbnailRequestedIds = shared?.requested || new Set();
    container.__hmbImageAssetThumbnailFailedIds = shared?.failed || new Set();
    container.__hmbImageAssetThumbnailErrorRetries = shared?.errorRetries || new Map();
    container.__hmbImageAssetThumbnailInflight = shared?.inflight || new Map();
    delete container.__hmbImageAssetThumbnailPendingRequestId;
  }
  if (!(container.__hmbImageAssetThumbnailRequestedIds instanceof Set)) {
    container.__hmbImageAssetThumbnailRequestedIds = new Set();
  }
  if (!(container.__hmbImageAssetThumbnailErrorRetries instanceof Map)) {
    container.__hmbImageAssetThumbnailErrorRetries = new Map();
  }
  if (!(container.__hmbImageAssetThumbnailFailedIds instanceof Set)) {
    container.__hmbImageAssetThumbnailFailedIds = new Set();
  }
  if (!(container.__hmbImageAssetThumbnailInflight instanceof Map)) {
    container.__hmbImageAssetThumbnailInflight = new Map();
  }
  return {
    contextKey,
    requested: container.__hmbImageAssetThumbnailRequestedIds,
    failed: container.__hmbImageAssetThumbnailFailedIds,
    inflight: container.__hmbImageAssetThumbnailInflight,
  };
}

function hmbImageAssetThumbnailResultIds(state) {
  const result = state?.thumbnail_result;
  return uniqueStrings([
    ...(Array.isArray(result?.completed_asset_library_ids)
      ? result.completed_asset_library_ids
      : []),
    ...(Array.isArray(result?.failed_asset_library_ids)
      ? result.failed_asset_library_ids
      : []),
  ]);
}

function hmbApplyImageAssetThumbnailFailurePresentation(container, state) {
  if (!state || !Array.isArray(state.assets)) return state;
  const failed = container?.__hmbImageAssetThumbnailFailedIds instanceof Set
    ? container.__hmbImageAssetThumbnailFailedIds
    : new Set();
  state.assets.forEach((asset) => {
    try {
      Object.defineProperty(asset, IMAGE_ASSET_THUMBNAIL_FAILED_STAMP, {
        configurable: true,
        enumerable: false,
        writable: true,
        value: failed.has(clean(asset?.asset_library_id)),
      });
    } catch (_error) {}
  });
  return state;
}

function hmbImageAssetThumbnailFailed(asset) {
  return Boolean(asset?.[IMAGE_ASSET_THUMBNAIL_FAILED_STAMP]);
}

function hmbAcceptImageAssetThumbnailResult(container, state) {
  const result = state?.thumbnail_result;
  if (!container || !imageAssetThumbnailContextMatches(state, result)) return false;
  hmbClearImageAssetThumbnailWatchdog(container, result.request_id);
  const tracking = imageAssetThumbnailRequestTracking(container, state);
  uniqueStrings(result.completed_asset_library_ids).forEach((key) => {
    tracking.failed.delete(key);
    tracking.requested.delete(key);
    tracking.inflight.delete(key);
    container.__hmbImageAssetThumbnailErrorRetries?.delete?.(key);
  });
  uniqueStrings(result.failed_asset_library_ids).forEach((key) => {
    tracking.requested.add(key);
    tracking.failed.add(key);
    tracking.inflight.delete(key);
  });
  hmbRememberImageAssetPresentation(state);
  if (container.__hmbImageAssetThumbnailPendingRequestId === result.request_id) {
    delete container.__hmbImageAssetThumbnailPendingRequestId;
  }
  if (
    !state.thumbnail_busy
    && state.thumbnail_request?.request_id === result.request_id
  ) state.thumbnail_request = {};
  hmbApplyImageAssetThumbnailFailurePresentation(container, state);
  return true;
}

export function hmbClearImageAssetThumbnailWatchdog(
  container,
  expectedRequestId = "",
) {
  if (!container) return false;
  const watchdog = container.__hmbImageAssetThumbnailWatchdog;
  if (
    expectedRequestId
    && clean(watchdog?.requestId) !== clean(expectedRequestId)
  ) return false;
  const timer = watchdog?.timer;
  if (timer !== null && timer !== undefined && typeof clearTimeout === "function") {
    try { clearTimeout(timer); } catch (_error) {}
  }
  delete container.__hmbImageAssetThumbnailWatchdog;
  return Boolean(watchdog);
}

export function hmbCancelImageAssetThumbnailRequest(container) {
  if (!container) return false;
  hmbClearImageAssetThumbnailWatchdog(container);
  const pendingRequestId = clean(container.__hmbImageAssetThumbnailPendingRequestId);
  const inflight = container.__hmbImageAssetThumbnailInflight;
  const requested = container.__hmbImageAssetThumbnailRequestedIds;
  if (pendingRequestId && inflight instanceof Map) {
    for (const [key, requestId] of inflight.entries()) {
      if (clean(requestId) !== pendingRequestId) continue;
      inflight.delete(key);
      requested?.delete?.(key);
    }
  }
  container.__hmbImageAssetThumbnailScheduleToken =
    (Number(container.__hmbImageAssetThumbnailScheduleToken) || 0) + 1;
  delete container.__hmbImageAssetThumbnailPendingRequestId;
  delete container.__hmbImageAssetThumbnailRequestedIds;
  delete container.__hmbImageAssetThumbnailFailedIds;
  delete container.__hmbImageAssetThumbnailErrorRetries;
  delete container.__hmbImageAssetThumbnailInflight;
  delete container.__hmbImageAssetThumbnailContextKey;
  return true;
}

export function hmbResetImageAssetThumbnailRetryState(container, state) {
  if (!container || !state) return false;
  hmbClearImageAssetThumbnailWatchdog(container);
  container.__hmbImageAssetThumbnailScheduleToken =
    (Number(container.__hmbImageAssetThumbnailScheduleToken) || 0) + 1;
  const shared = imageAssetPresentationCacheEntry(state, true);
  shared?.requested?.clear?.();
  shared?.failed?.clear?.();
  shared?.errorRetries?.clear?.();
  shared?.inflight?.clear?.();
  container.__hmbImageAssetThumbnailRequestedIds = shared?.requested || new Set();
  container.__hmbImageAssetThumbnailFailedIds = shared?.failed || new Set();
  container.__hmbImageAssetThumbnailErrorRetries = shared?.errorRetries || new Map();
  container.__hmbImageAssetThumbnailInflight = shared?.inflight || new Map();
  delete container.__hmbImageAssetThumbnailPendingRequestId;
  state.thumbnail_request = {};
  state.thumbnail_result = {};
  state.thumbnail_busy = false;
  hmbApplyImageAssetThumbnailFailurePresentation(container, state);
  return true;
}

export function hmbFinalizeImageAssetThumbnailTimeout(container, state, request) {
  if (!container || !state || !request) return false;
  const requestId = clean(request.request_id);
  const contextKey = imageAssetThumbnailContextKey(state);
  if (
    !requestId
    || !contextKey
    || clean(request.project_uid) !== clean(state.project_uid)
    || (clean(request.project_cache_uid)
      && clean(request.project_cache_uid) !== clean(state.project_cache_uid))
    || clean(request.manifest_signature) !== clean(state.manifest_signature)
    || hmbNormalizeImageAssetRevision(request.scan_revision)
      !== hmbNormalizeImageAssetRevision(state.scan_revision)
  ) return false;
  hmbClearImageAssetThumbnailWatchdog(container, requestId);
  const failedIds = uniqueStrings(request.asset_library_ids);
  const tracking = imageAssetThumbnailRequestTracking(container, state);
  failedIds.forEach((key) => {
    tracking.requested.add(key);
    tracking.failed.add(key);
    tracking.inflight.delete(key);
  });
  state.thumbnail_request = {};
  state.thumbnail_busy = false;
  state.thumbnail_result = {
    request_id: requestId,
    project_uid: clean(request.project_uid),
    project_cache_uid: clean(request.project_cache_uid || state.project_cache_uid),
    manifest_signature: clean(request.manifest_signature),
    scan_revision: hmbNormalizeImageAssetRevision(request.scan_revision),
    completed_asset_library_ids: [],
    failed_asset_library_ids: failedIds,
  };
  if (container.__hmbImageAssetThumbnailPendingRequestId === requestId) {
    delete container.__hmbImageAssetThumbnailPendingRequestId;
  }
  container.__hmbImageAssetLatestState = state;
  hmbApplyImageAssetThumbnailFailurePresentation(container, state);
  hmbPatchImageAssetThumbnailMedia(container, state, failedIds);
  return true;
}

export function hmbArmImageAssetThumbnailWatchdog(
  container,
  state,
  props,
  request,
) {
  if (!container || !state || !request || typeof setTimeout !== "function") {
    return false;
  }
  hmbClearImageAssetThumbnailWatchdog(container);
  const watchdog = {
    requestId: clean(request.request_id),
    runtimeId: imageAssetThumbnailRuntimeId(state),
    contextKey: imageAssetThumbnailContextKey(state),
    mountToken: Number(container.__hmbImageAssetMountToken) || 0,
    request: {
      ...request,
      asset_library_ids: uniqueStrings(request.asset_library_ids),
    },
    retries: 0,
    timer: null,
  };
  if (!watchdog.requestId || !watchdog.contextKey) return false;

  const isCurrent = () => {
    const live = container.__hmbImageAssetLatestState || state;
    return Boolean(
      container.__hmbImageAssetThumbnailWatchdog === watchdog
      && imageAssetThumbnailContextKey(live) === watchdog.contextKey
      && (!watchdog.mountToken
        || Number(container.__hmbImageAssetMountToken) === watchdog.mountToken)
      && clean(container.__hmbImageAssetThumbnailPendingRequestId)
        === watchdog.requestId
    );
  };
  const schedule = () => {
    watchdog.timer = setTimeout(onTimeout, IMAGE_ASSET_THUMBNAIL_WATCHDOG_MS);
  };
  const terminalize = () => {
    if (!isCurrent()) {
      hmbClearImageAssetThumbnailWatchdog(container, watchdog.requestId);
      return false;
    }
    const live = container.__hmbImageAssetLatestState || state;
    try {
      console?.warn?.(
        "[HMBImageAssetLibrary] thumbnail response timed out; use Refresh to retry.",
        watchdog.requestId,
      );
    } catch (_error) {}
    return hmbFinalizeImageAssetThumbnailTimeout(
      container,
      live,
      watchdog.request,
    );
  };
  const probe = () => {
    const live = container.__hmbImageAssetLatestState || state;
    const bridge = imageAssetThumbnailBridgeRegistry()?.get(watchdog.runtimeId);
    const dispatch = typeof bridge?.dispatch === "function" ? bridge.dispatch : null;
    try {
      let result;
      if (dispatch) {
        result = dispatch(watchdog.request);
      } else if (typeof props?.onChange === "function") {
        // One bounded legacy wake-up is allowed only after the compact result
        // lease expires. It reuses the exact request ID, so the backend either
        // drains a pending result or republishes its completed envelope rather
        // than starting duplicate decode work.
        result = props.onChange(JSON.stringify({
          ...live,
          thumbnail_request: watchdog.request,
          thumbnail_busy: true,
          __hmb_thumbnail_watchdog_probe: watchdog.requestId,
        }));
      } else {
        return terminalize();
      }
      if (result && typeof result.then === "function") {
        Promise.resolve(result).catch(() => terminalize());
      }
      return true;
    } catch (_error) {
      return terminalize();
    }
  };
  const onTimeout = () => {
    if (!isCurrent()) {
      hmbClearImageAssetThumbnailWatchdog(container, watchdog.requestId);
      return;
    }
    const live = container.__hmbImageAssetLatestState || state;
    const result = live.thumbnail_result;
    if (
      !live.thumbnail_busy
      && imageAssetThumbnailContextMatches(live, result)
      && clean(result?.request_id) === watchdog.requestId
    ) {
      hmbAcceptImageAssetThumbnailResult(container, live);
      hmbPatchImageAssetThumbnailMedia(
        container,
        live,
        hmbImageAssetThumbnailResultIds(live),
      );
      return;
    }
    if (watchdog.retries >= IMAGE_ASSET_THUMBNAIL_WATCHDOG_RETRIES) {
      terminalize();
      return;
    }
    watchdog.retries += 1;
    if (probe() && container.__hmbImageAssetThumbnailWatchdog === watchdog) {
      schedule();
    }
  };

  container.__hmbImageAssetThumbnailWatchdog = watchdog;
  schedule();
  return true;
}

export function hmbResumeImageAssetThumbnailRequest(container, state, props = {}) {
  if (!container || !state || !state.thumbnail_busy) return false;
  const existing = container.__hmbImageAssetThumbnailWatchdog;
  if (
    clean(container.__hmbImageAssetThumbnailPendingRequestId)
    && clean(existing?.requestId)
      === clean(container.__hmbImageAssetThumbnailPendingRequestId)
  ) return true;
  const tracking = imageAssetThumbnailRequestTracking(container, state);
  if (!tracking.contextKey) {
    state.thumbnail_request = {};
    state.thumbnail_busy = false;
    return false;
  }
  let request = state.thumbnail_request;
  if (!imageAssetThumbnailRequestMatchesState(state, request)) {
    // Legacy full-state acknowledgements intentionally clear the consumed
    // request. If React recreates the widget during that short busy interval,
    // reconstruct one bounded lease from the still-missing visible/selected
    // media. Backend single-flight queues this newer intent safely.
    const recoveredIds = hmbImageAssetThumbnailRequestIds(
      state,
      container.__hmbImageAssetRenderLimit || IMAGE_ASSET_RENDER_WINDOW,
      container.__hmbImageAssetRenderOffset || 0,
      {
        includeWindow: !container.__hmbImageAssetCompact,
        excludeIds: tracking.failed,
      },
    );
    if (!recoveredIds.length) {
      state.thumbnail_request = {};
      state.thumbnail_busy = false;
      return false;
    }
    request = {
      request_id: `thumbnail-resume-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      project_uid: state.project_uid,
      project_cache_uid: state.project_cache_uid,
      manifest_signature: state.manifest_signature,
      scan_revision: state.scan_revision,
      asset_library_ids: recoveredIds,
    };
    state.thumbnail_request = request;
  }
  const available = new Map(
    (Array.isArray(state.assets) ? state.assets : [])
      .filter((asset) => asset && typeof asset === "object")
      .map((asset) => [clean(asset.asset_library_id), asset]),
  );
  const requestIds = uniqueStrings(request.asset_library_ids)
    .filter((key) => {
      const asset = available.get(key);
      return asset && !imageSource(asset);
    })
    .slice(0, IMAGE_ASSET_THUMBNAIL_REQUEST_BATCH);
  if (!requestIds.length) {
    state.thumbnail_request = {};
    state.thumbnail_busy = false;
    return false;
  }
  const requestId = clean(request.request_id);
  requestIds.forEach((key) => {
    tracking.requested.add(key);
    tracking.inflight.set(key, requestId);
  });
  container.__hmbImageAssetThumbnailPendingRequestId = requestId;
  container.__hmbImageAssetLatestState = state;
  const bridgeRequest = {
    schema: "hmb-image-asset-thumbnail-bridge",
    version: 1,
    operation: "hydrate",
    phase: "request",
    runtime_instance_id: imageAssetThumbnailRuntimeId(state),
    request_id: requestId,
    project_uid: clean(request.project_uid),
    project_cache_uid: clean(request.project_cache_uid || state.project_cache_uid),
    manifest_signature: clean(request.manifest_signature),
    scan_revision: hmbNormalizeImageAssetRevision(request.scan_revision),
    asset_library_ids: requestIds,
  };
  if (hmbArmImageAssetThumbnailWatchdog(container, state, props, bridgeRequest)) {
    // Wake the backend immediately. Reusing the same request ID is idempotent:
    // it either rejoins the active single-flight or republishes its completion.
    const bridge = imageAssetThumbnailBridgeRegistry()?.get(
      bridgeRequest.runtime_instance_id,
    );
    try {
      let dispatched = null;
      if (typeof bridge?.dispatch === "function") {
        dispatched = bridge.dispatch(bridgeRequest);
      } else if (typeof props?.onChange === "function") {
        dispatched = props.onChange(JSON.stringify({
          ...state,
          thumbnail_request: {
            request_id: requestId,
            project_uid: bridgeRequest.project_uid,
            project_cache_uid: bridgeRequest.project_cache_uid,
            manifest_signature: bridgeRequest.manifest_signature,
            scan_revision: bridgeRequest.scan_revision,
            asset_library_ids: [...requestIds],
          },
          thumbnail_busy: true,
        }));
      }
      if (dispatched && typeof dispatched.then === "function") {
        Promise.resolve(dispatched).catch(() => {});
      }
    } catch (_error) {
      // The watchdog owns the one bounded retry/finalization path.
    }
    return true;
  }
  // A browser without timers cannot own a bounded lease. End the visual state
  // deterministically instead of preserving a loader that can never wake.
  return hmbFinalizeImageAssetThumbnailTimeout(container, state, bridgeRequest);
}

function imageAssetThumbnailAssetForElement(container, state, image) {
  if (!state || !Array.isArray(state.assets) || !image) return null;
  const keyedOwner = image.closest?.("[data-asset-key]")
    || image.closest?.("[data-selected-key]") || image.closest?.("[data-image-bash-asset-key]");
  const libraryId = clean(
    keyedOwner?.getAttribute?.("data-asset-key")
    || keyedOwner?.getAttribute?.("data-selected-key") || keyedOwner?.getAttribute?.("data-image-bash-asset-key"),
  );
  if (libraryId) {
    return state.assets.find((asset) => clean(asset.asset_library_id) === libraryId) || null;
  }
  const compactOwner = image.closest?.("[data-compact-asset-key]");
  const sourceUid = clean(compactOwner?.getAttribute?.("data-shot-source-uid"));
  if (sourceUid) {
    return state.assets.find((asset) => clean(asset.source_uid) === sourceUid) || null;
  }
  if (image.closest?.(".passport-photo")) {
    const draftId = clean(container?.__hmbImageAssetRegistrationDraft?.asset_library_id);
    return state.assets.find((asset) => clean(asset.asset_library_id) === draftId) || null;
  }
  return null;
}

function imageAssetThumbnailElementMatchesAsset(image, asset) {
  const thumbnailUrl = clean(asset?.thumbnail_url);
  const persistedProjectAsset = Number(asset?.import_index || 0) === 0
    && Boolean(clean(asset?.relative_path));
  if (
    !persistedProjectAsset
    // Only process-lifetime StaticFilesManager URLs are eligible for this
    // recovery. Durable external HTTP sources and inline data media remain
    // browser-owned even when their catalog row is persisted.
    || !/^https?:\/\/[^/]+\/workspace\/static_files(?:\/|[?#]|$)/i.test(thumbnailUrl)
  ) return false;
  const elementUrl = clean(
    image?.getAttribute?.("src")
    || image?.getAttribute?.("data-hmb-compact-src"),
  );
  return Boolean(elementUrl && elementUrl === thumbnailUrl);
}

export function hmbHandleImageAssetThumbnailError(container, state, image, props) {
  const liveState = container?.__hmbImageAssetLatestState || state;
  const asset = imageAssetThumbnailAssetForElement(container, liveState, image);
  if (!imageAssetThumbnailElementMatchesAsset(image, asset)) return false;
  const tracking = imageAssetThumbnailRequestTracking(container, liveState);
  if (!tracking.contextKey) return false;
  const key = clean(asset.asset_library_id);
  const retries = container.__hmbImageAssetThumbnailErrorRetries;
  const retryCount = Math.max(0, Number(retries.get(key)) || 0);
  asset.thumbnail_url = "";
  const shared = imageAssetPresentationCacheEntry(liveState, false);
  shared?.thumbnails?.delete?.(key);
  shared?.inflight?.delete?.(key);
  container.__hmbImageAssetLatestState = liveState;
  image.closest?.(".asset-thumb,.selected-thumb,.passport-photo,.compact-shot-asset")
    ?.classList?.add?.("fallback");
  if (retryCount >= IMAGE_ASSET_THUMBNAIL_ERROR_RETRY_LIMIT) {
    tracking.requested.add(key);
    tracking.failed.add(key);
    image.removeAttribute?.("src");
    image.removeAttribute?.("data-hmb-compact-src");
    hmbApplyImageAssetThumbnailFailurePresentation(container, liveState);
    hmbPatchImageAssetThumbnailMedia(container, liveState, [key]);
    return true;
  }
  retries.set(key, retryCount + 1);
  tracking.failed.delete(key);
  tracking.requested.delete(key);
  hmbApplyImageAssetThumbnailFailurePresentation(container, liveState);
  hmbPatchImageAssetThumbnailMedia(container, liveState, [key]);
  hmbScheduleImageAssetThumbnailRequest(container, liveState, props, {
    includeWindow: !container.__hmbImageAssetCompact,
  });
  return true;
}

export function hmbRememberLoadedImageAssetThumbnail(container, state, image) {
  const liveState = container?.__hmbImageAssetLatestState || state;
  const asset = imageAssetThumbnailAssetForElement(container, liveState, image);
  if (!imageAssetThumbnailElementMatchesAsset(image, asset)) return false;
  const tracking = imageAssetThumbnailRequestTracking(container, liveState);
  if (!tracking.contextKey) return false;
  const key = clean(asset.asset_library_id);
  container.__hmbImageAssetThumbnailErrorRetries.delete(key);
  tracking.failed.delete(key);
  hmbApplyImageAssetThumbnailFailurePresentation(container, liveState);
  return true;
}

export function hmbScheduleImageAssetThumbnailRequest(
  container,
  state,
  props,
  options = {},
) {
  if (!container) return false;
  const liveState = container.__hmbImageAssetLatestState || state;
  if (!liveState || liveState.scan_busy || liveState.thumbnail_busy) return false;
  const tracking = imageAssetThumbnailRequestTracking(container, liveState);
  if (!tracking.contextKey) return false;
  if (imageAssetThumbnailRequestMatchesState(liveState, liveState.thumbnail_request)) {
    return false;
  }
  const requestIds = hmbImageAssetThumbnailRequestIds(
    liveState,
    options.limit ?? container.__hmbImageAssetRenderLimit ?? IMAGE_ASSET_RENDER_WINDOW,
    options.offset ?? container.__hmbImageAssetRenderOffset ?? 0,
    { ...options, excludeIds: tracking.requested },
  );
  if (!requestIds.length) return false;

  const token = (Number(container.__hmbImageAssetThumbnailScheduleToken) || 0) + 1;
  container.__hmbImageAssetThumbnailScheduleToken = token;
  hmbAfterImageAssetPaint(() => {
    if (container.__hmbImageAssetThumbnailScheduleToken !== token) return;
    const current = container.__hmbImageAssetLatestState || liveState;
    const currentTracking = imageAssetThumbnailRequestTracking(container, current);
    const runtimeId = imageAssetThumbnailRuntimeId(current);
    const bridge = imageAssetThumbnailBridgeRegistry()?.get(runtimeId);
    const bridgeDispatch = typeof bridge?.dispatch === "function" ? bridge.dispatch : null;
    if (
      !currentTracking.contextKey
      || currentTracking.contextKey !== tracking.contextKey
      || current.scan_busy
      || current.thumbnail_busy
      || imageAssetThumbnailRequestMatchesState(current, current.thumbnail_request)
      || container.__hmbImageAssetThumbnailPendingRequestId
    ) return;
    const currentIds = hmbImageAssetThumbnailRequestIds(
      current,
      options.limit ?? container.__hmbImageAssetRenderLimit ?? IMAGE_ASSET_RENDER_WINDOW,
      options.offset ?? container.__hmbImageAssetRenderOffset ?? 0,
      { ...options, excludeIds: currentTracking.requested },
    );
    if (!currentIds.length) return;

    const requestId = `thumbnail-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    current.thumbnail_request = {
      request_id: requestId,
      project_uid: current.project_uid,
      project_cache_uid: current.project_cache_uid,
      manifest_signature: current.manifest_signature,
      scan_revision: current.scan_revision,
      asset_library_ids: currentIds,
    };
    current.thumbnail_result = {};
    current.thumbnail_busy = true;
    currentIds.forEach((key) => {
      currentTracking.requested.add(key);
      currentTracking.inflight.set(key, requestId);
    });
    container.__hmbImageAssetThumbnailPendingRequestId = requestId;
    container.__hmbImageAssetLatestState = current;
    const bridgeRequest = {
      schema: "hmb-image-asset-thumbnail-bridge",
      version: 1,
      operation: "hydrate",
      phase: "request",
      runtime_instance_id: runtimeId,
      request_id: requestId,
      project_uid: current.project_uid,
      project_cache_uid: current.project_cache_uid,
      manifest_signature: current.manifest_signature,
      scan_revision: current.scan_revision,
      asset_library_ids: [...currentIds],
    };
    // Own one bounded lease for both the compact bridge and legacy transport.
    // A lost result gets one idempotent same-request probe, then becomes a
    // static failure marker instead of an infinite animation.
    hmbArmImageAssetThumbnailWatchdog(container, current, props, bridgeRequest);
    const preservePendingForWatchdog = () => {
      const live = container.__hmbImageAssetLatestState || current;
      if (
        clean(container.__hmbImageAssetThumbnailPendingRequestId) !== requestId
        || imageAssetThumbnailContextKey(live) !== currentTracking.contextKey
      ) return false;
      // The transport itself can fail before the backend sees the request.
      // Keep the exact request lease alive: its watchdog performs one bounded
      // idempotent probe and then turns every affected loader into a static
      // failure marker. Rolling back here would remove that only wake-up path.
      current.thumbnail_request = {
        request_id: requestId,
        project_uid: bridgeRequest.project_uid,
        project_cache_uid: bridgeRequest.project_cache_uid,
        manifest_signature: bridgeRequest.manifest_signature,
        scan_revision: bridgeRequest.scan_revision,
        asset_library_ids: [...bridgeRequest.asset_library_ids],
      };
      current.thumbnail_result = {};
      current.thumbnail_busy = true;
      currentIds.forEach((key) => {
        currentTracking.requested.add(key);
        currentTracking.inflight.set(key, requestId);
      });
      container.__hmbImageAssetLatestState = current;
      return true;
    };
    if (bridgeDispatch) {
      try {
        const dispatched = bridgeDispatch(bridgeRequest);
        if (dispatched && typeof dispatched.then === "function") {
          Promise.resolve(dispatched).catch(preservePendingForWatchdog);
        }
      } catch (_error) {
        preservePendingForWatchdog();
      }
      return;
    }
    emit(props, current, container, preservePendingForWatchdog, {
      suppressMatchingEcho: true,
      preserveUiEditRevision: true,
      onSuccess: () => {
        if (current.thumbnail_request?.request_id === requestId) {
          current.thumbnail_request = {};
        }
      },
    });
  });
  return true;
}

function imageAssetCatalogProbeDelay(kind) {
  const background = typeof document !== "undefined"
    && (document.hidden || document.visibilityState === "hidden");
  const table = background
    ? IMAGE_ASSET_CATALOG_PROBE_BACKGROUND_MS
    : IMAGE_ASSET_CATALOG_PROBE_ACTIVE_MS;
  return table[kind] || table.folder;
}

function imageAssetCatalogProbeContext(state) {
  const runtimeId = imageAssetThumbnailRuntimeId(state);
  const projectUid = clean(state?.project_uid);
  const projectCacheUid = clean(state?.project_cache_uid);
  const projectRoot = clean(state?.project_root || state?.catalog_root).replaceAll("\\", "/");
  if (!runtimeId || !projectUid || !projectRoot) return null;
  return {
    runtimeId,
    projectUid,
    projectCacheUid,
    projectRoot,
    manifestSignature: clean(state?.manifest_signature),
    scanRevision: hmbNormalizeImageAssetRevision(state?.scan_revision),
    key: [
      runtimeId,
      hmbImageAssetPresentationCacheKey(state),
      projectRoot,
      hmbNormalizeImageAssetRevision(state?.scan_revision),
    ].join("\n"),
  };
}

export function hmbAcceptImageAssetCatalogProbeResult(container, state, result) {
  const context = imageAssetCatalogProbeContext(state);
  if (
    !container
    || !context
    || clean(result?.schema) !== "hmb-image-asset-thumbnail-bridge"
    || clean(result?.operation) !== "catalog_probe"
    || clean(result?.phase) !== "result"
    || clean(result?.runtime_instance_id) !== context.runtimeId
    || clean(result?.project_uid) !== context.projectUid
    || (clean(result?.project_cache_uid)
      && clean(result?.project_cache_uid) !== context.projectCacheUid)
    || clean(result?.manifest_signature) !== context.manifestSignature
    || hmbNormalizeImageAssetRevision(result?.scan_revision) !== context.scanRevision
  ) return false;
  const kind = clean(result?.probe_kind);
  if (kind !== "manifest" && kind !== "folder") return false;
  if (!["no_change", "changed", "deferred", "offline"].includes(clean(result?.outcome))) {
    return false;
  }
  const pending = container.__hmbImageAssetCatalogProbePending;
  const request = pending instanceof Map ? pending.get(kind) : null;
  if (request && clean(request.requestId) !== clean(result?.request_id)) return false;
  pending?.delete?.(kind);
  return true;
}

function hmbClearImageAssetCatalogProbeTimers(container) {
  const timers = container?.__hmbImageAssetCatalogProbeTimers;
  if (timers instanceof Map && typeof clearTimeout === "function") {
    for (const timer of timers.values()) {
      try { clearTimeout(timer); } catch (_error) {}
    }
  }
  timers?.clear?.();
}

export function hmbStopImageAssetCatalogPolling(container) {
  if (!container) return false;
  hmbClearImageAssetCatalogProbeTimers(container);
  const visibilityHandler = container.__hmbImageAssetCatalogVisibilityHandler;
  if (visibilityHandler && typeof document !== "undefined") {
    try { document.removeEventListener?.("visibilitychange", visibilityHandler); } catch (_error) {}
  }
  delete container.__hmbImageAssetCatalogVisibilityHandler;
  delete container.__hmbImageAssetCatalogProbeTimers;
  delete container.__hmbImageAssetCatalogProbePending;
  delete container.__hmbImageAssetCatalogProbeContextKey;
  return true;
}

export function hmbStartImageAssetCatalogPolling(container, state) {
  if (!container || typeof setTimeout !== "function") return false;
  const liveState = container.__hmbImageAssetLatestState || state;
  const context = imageAssetCatalogProbeContext(liveState);
  const bridge = context
    ? imageAssetThumbnailBridgeRegistry()?.get(context.runtimeId)
    : null;
  if (!context || typeof bridge?.dispatch !== "function") return false;
  if (container.__hmbImageAssetCatalogProbeContextKey !== context.key) {
    hmbStopImageAssetCatalogPolling(container);
    container.__hmbImageAssetCatalogProbeContextKey = context.key;
    container.__hmbImageAssetCatalogProbeTimers = new Map();
    container.__hmbImageAssetCatalogProbePending = new Map();
  }
  const timers = container.__hmbImageAssetCatalogProbeTimers;
  const pending = container.__hmbImageAssetCatalogProbePending;

  const schedule = (kind) => {
    if (timers.has(kind)) return;
    const delay = imageAssetCatalogProbeDelay(kind);
    const timer = setTimeout(() => {
      timers.delete(kind);
      const current = container.__hmbImageAssetLatestState || liveState;
      const currentContext = imageAssetCatalogProbeContext(current);
      if (
        !currentContext
        || currentContext.key !== container.__hmbImageAssetCatalogProbeContextKey
      ) return;
      const currentBridge = imageAssetThumbnailBridgeRegistry()?.get(currentContext.runtimeId);
      const dispatch = typeof currentBridge?.dispatch === "function"
        ? currentBridge.dispatch
        : null;
      const previous = pending.get(kind);
      const currentDelay = imageAssetCatalogProbeDelay(kind);
      if (
        !current.scan_busy
        && dispatch
        && (!previous || Date.now() - previous.startedAt >= currentDelay * 2)
      ) {
        const requestId = `catalog-${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        const request = {
          schema: "hmb-image-asset-thumbnail-bridge",
          version: 1,
          operation: "catalog_probe",
          phase: "request",
          request_id: requestId,
          runtime_instance_id: currentContext.runtimeId,
          project_uid: currentContext.projectUid,
          project_cache_uid: currentContext.projectCacheUid,
          project_root: currentContext.projectRoot,
          manifest_signature: currentContext.manifestSignature,
          scan_revision: currentContext.scanRevision,
          probe_kind: kind,
        };
        pending.set(kind, { requestId, startedAt: Date.now() });
        try {
          const dispatched = dispatch(request);
          if (dispatched && typeof dispatched.then === "function") {
            Promise.resolve(dispatched).catch(() => pending.delete(kind));
          }
        } catch (_error) {
          pending.delete(kind);
        }
      }
      schedule(kind);
    }, delay);
    timers.set(kind, timer);
  };

  schedule("manifest");
  schedule("folder");
  if (
    !container.__hmbImageAssetCatalogVisibilityHandler
    && typeof document !== "undefined"
    && typeof document.addEventListener === "function"
  ) {
    const visibilityHandler = () => {
      hmbClearImageAssetCatalogProbeTimers(container);
      schedule("manifest");
      schedule("folder");
    };
    container.__hmbImageAssetCatalogVisibilityHandler = visibilityHandler;
    document.addEventListener("visibilitychange", visibilityHandler);
  }
  return true;
}

export function hmbRenderImageAssetGrid(
  state,
  limit = IMAGE_ASSET_RENDER_WINDOW,
  offset = 0,
) {
  const windowed = hmbImageAssetCatalogWindow(state, limit, offset);
  const shot = activeImageAssetShot(state);
  const selectedCount = imageAssetShotAssets(state, shot).length;
  const cards = windowed.rendered
    .map((asset) => renderAssetCard(asset, selectedCount, state.catalog_page?.query ?? state.search, state, shot))
    .join("");
  const empty = windowed.matches.length
    ? ""
    : `<div class="empty" data-search-empty>${escapeHtml(imageAssetText(state, "no_match"))}</div>`;
  const first = windowed.rendered.length ? windowed.offset + 1 : 0;
  const last = windowed.offset + windowed.rendered.length;
  const previous = windowed.offset > 0
    ? `<button type="button" class="asset-window-more" data-assets-previous aria-label="Previous images">&#8592; ${first}-${last}/${windowed.matches.length}</button>`
    : "";
  const more = last < windowed.matches.length
    ? `<button type="button" class="asset-window-more" data-assets-more aria-label="${escapeHtml(imageAssetText(state, "show_more"))}">${escapeHtml(imageAssetText(state, "showing_images"))} ${first}-${last}/${windowed.matches.length} · ${escapeHtml(imageAssetText(state, "show_more"))} &#8594;</button>`
    : "";
  const navigation = previous || more
    ? `<nav class="asset-window-nav" aria-label="Image pages">${previous}${more}</nav>`
    : "";
  return { markup: `<div class="asset-grid">${cards}${empty}${navigation}</div>`, ...windowed };
}

export function hmbReconcileImageAssetCatalog(container, state, options = {}) {
  if(hmbRequestImageAssetCatalogPage(container,state,options.offset ?? container?.__hmbImageAssetRenderOffset ?? 0))return {pending:true};
  const grid = container?.querySelector?.(".asset-grid");
  const ownerDocument = grid?.ownerDocument || container?.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  if (!grid || !ownerDocument?.createElement) return null;
  const limit = Math.min(
    IMAGE_ASSET_RENDER_WINDOW,
    Math.max(
      1,
      Math.floor(Number(options.limit ?? container.__hmbImageAssetRenderLimit) || IMAGE_ASSET_RENDER_WINDOW),
    ),
  );
  const offset = Math.max(
    0,
    Math.floor(Number(options.offset ?? container.__hmbImageAssetRenderOffset) || 0),
  );
  container.__hmbImageAssetRenderLimit = limit;
  const rendered = hmbRenderImageAssetGrid(state, limit, offset);
  container.__hmbImageAssetRenderOffset = rendered.offset;
  const template = ownerDocument.createElement("template");
  template.innerHTML = rendered.markup;
  const desired = template.content?.firstElementChild;
  if (desired) hmbPatchImageAssetElement(grid, desired);
  hmbRebuildImageAssetIndexes(container, state);
  const cardMap = container.__hmbImageAssetCardByLibraryId || new Map();
  return {
    total: rendered.matches.length,
    rendered: rendered.rendered.length,
    domCards: cardMap.size,
  };
}

function renderSelectedCard(asset, index, selected, state, shot = activeImageAssetShot(state)) {
  const number = String(index + 1).padStart(2, "0");
  const removeTitle = imageAssetText(state, "remove_selection");
  return `
    <article class="selected-card ${asset.connected ? "" : "missing"}" draggable="true" aria-grabbed="false"
      data-selected-key="${escapeHtml(asset.asset_library_id)}" data-shot-source-uid="${escapeHtml(asset.source_uid)}" data-shot-uuid="${escapeHtml(shot?.shot_uuid || "")}" aria-label="${escapeHtml(`${number} ${asset.image_name}`)}" title="${escapeHtml(asset.image_name)}">
      <div class="selected-card-top">
        <strong class="slot">${number}</strong>
        <div class="selected-actions">
          <button type="button" data-remove-selected title="${escapeHtml(removeTitle)}" aria-label="${escapeHtml(removeTitle)}">×</button>
        </div>
      </div>
      <div class="selected-card-body">
        ${thumbnailHtml(asset, "selected-thumb")}
      </div>
    </article>
  `;
}

function hmbApplyImageAssetCardFeedback(card, asset, selectedCount, state, shot = activeImageAssetShot(state)) {
  if (!card || !asset) return false;
  const selectable = hmbImageAssetCanSelect(asset);
  const selectedForShot = state.image_bash_active ? imageBashSourceUids(state).has(asset.source_uid) : imageAssetShotContains(shot, asset.source_uid);
  const selectionBlocked = selectable && (state.image_bash_active
    ? state.image_bash_workspace.instances.length >= MAX_SELECTED_IMAGES : !selectedForShot && selectedCount >= MAX_SHOT_IMAGES);
  card.classList?.toggle("selected", selectedForShot);
  card.classList?.toggle("selection-blocked", selectionBlocked);
  card.setAttribute?.("data-selection-disabled", selectionBlocked ? "1" : "0");
  if (selectable) card.setAttribute?.("aria-pressed", selectedForShot ? "true" : "false");
  const title = !selectable
    ? imageAssetText(state, "register_before_select")
    : selectionBlocked
      ? imageAssetText(state, "image_limit")
      : imageAssetText(state, "click_select");
  card.setAttribute?.("title", title);
  return true;
}

function hmbCreateSelectedAssetCard(tray, asset, index, selected, state, factory = null, shot = null) {
  if (typeof factory === "function") {
    return factory(asset, index, selected, state, renderSelectedCard(asset, index, selected, state, shot));
  }
  const ownerDocument = tray?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!ownerDocument?.createElement) return null;
  const template = ownerDocument.createElement("template");
  template.innerHTML = renderSelectedCard(asset, index, selected, state, shot).trim();
  return template.content?.firstElementChild || null;
}

function hmbUpdateSelectedAssetCard(card, asset, index, selected, state, shot = null) {
  if (!card || !asset) return false;
  const number = String(index + 1).padStart(2, "0");
  const removeTitle = imageAssetText(state, "remove_selection");
  card.classList?.toggle("missing", !asset.connected);
  card.setAttribute?.("data-selected-key", asset.asset_library_id);
  card.setAttribute?.("data-shot-source-uid", asset.source_uid);
  card.setAttribute?.("data-shot-uuid", shot?.shot_uuid || "");
  if (!card.classList?.contains?.("dragging")) card.setAttribute?.("aria-grabbed", "false");
  card.setAttribute?.("aria-label", `${number} ${asset.image_name}`);
  card.setAttribute?.("title", asset.image_name);
  const slot = card.querySelector?.(".slot");
  if (slot) slot.textContent = number;
  const remove = card.querySelector?.("[data-remove-selected]");
  if (remove) {
    remove.disabled = false;
    remove.setAttribute?.("title", removeTitle);
    remove.setAttribute?.("aria-label", removeTitle);
    remove.removeAttribute?.("aria-busy");
  }
  return true;
}

function hmbCreateSelectedAssetTrayEmpty(tray, state, factory = null) {
  if (typeof factory === "function") return factory(state);
  const ownerDocument = tray?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!ownerDocument?.createElement) return null;
  const empty = ownerDocument.createElement("div");
  empty.className = "tray-empty";
  empty.textContent = imageAssetText(state, "tray_empty");
  return empty;
}

export function hmbReconcileImageAssetSelectionTray(tray, selected, state, options = {}) {
  if (!tray) return { created: 0, removed: 0, retained: 0 };
  const ordered = Array.isArray(selected) ? selected : [];
  const scrollLeft = Number(tray.scrollLeft || 0);
  const existingCards = Array.from(tray.querySelectorAll?.("[data-selected-key]") || []);
  const cardsByKey = new Map(existingCards.map((card) => [
    clean(card.getAttribute?.("data-selected-key")),
    card,
  ]));
  let removed = 0;
  let created = 0;
  let retained = 0;
  const empty = tray.querySelector?.(".tray-empty");
  if (ordered.length) empty?.remove?.();

  ordered.forEach((asset, index) => {
    const key = clean(asset.asset_library_id);
    let card = cardsByKey.get(key) || null;
    if (card) {
      cardsByKey.delete(key);
      retained += 1;
    } else {
      card = hmbCreateSelectedAssetCard(
        tray,
        asset,
        index,
        ordered,
        state,
        options.createSelectedCard,
        options.shot || null,
      );
      if (!card) return;
      created += 1;
    }
    hmbUpdateSelectedAssetCard(card, asset, index, ordered, state, options.shot || null);
    const current = tray.children?.[index] || null;
    if (current !== card) {
      if (typeof tray.insertBefore === "function") tray.insertBefore(card, current);
      else tray.appendChild?.(card);
    }
  });
  cardsByKey.forEach((card) => {
    card.remove?.();
    removed += 1;
  });
  if (!ordered.length && !tray.querySelector?.(".tray-empty")) {
    const trayEmpty = hmbCreateSelectedAssetTrayEmpty(
      tray,
      state,
      options.createTrayEmpty,
    );
    if (trayEmpty) tray.appendChild?.(trayEmpty);
  }
  try { tray.scrollLeft = scrollLeft; } catch (_error) {}
  return { created, removed, retained };
}

export function hmbApplyImageAssetShotSourceOrderToDom(container, state, shotUuid) {
  const uuid = imageAssetUuid(shotUuid);
  const shot = (Array.isArray(state?.shot_routing?.shots) ? state.shot_routing.shots : [])
    .find((item) => imageAssetUuid(item?.shot_uuid) === uuid);
  if (!uuid || !shot) return false;
  const trays = [
    container?.querySelector?.("[data-shot-tray]"),
    ...Array.from(container?.querySelectorAll?.("[data-compact-shot-assets]") || []),
  ].filter((tray) => tray && imageAssetUuid(
    tray.getAttribute?.("data-shot-tray") || tray.getAttribute?.("data-compact-shot-assets"),
  ) === uuid);
  if (!trays.length) return false;
  trays.forEach((tray) => {
    const compact = Boolean(tray.getAttribute?.("data-compact-shot-assets"));
    const cards = Array.from(tray.querySelectorAll?.(compact ? "[data-compact-asset-key]" : "[data-selected-key]") || []);
    const cardsByUid = new Map(cards.map((card) => [
      clean(card.getAttribute?.("data-shot-source-uid")),
      card,
    ]));
    const orderedCards = shot.selected_source_uids
      .map((sourceUid) => cardsByUid.get(clean(sourceUid)))
      .filter(Boolean);
    orderedCards.forEach((card, index) => {
      const current = tray.children?.[index] || null;
      if (current !== card) {
        if (typeof tray.insertBefore === "function") tray.insertBefore(card, current);
        else tray.appendChild?.(card);
      }
      card.setAttribute?.("data-shot-uuid", uuid);
      card.setAttribute?.("aria-posinset", String(index + 1));
      card.setAttribute?.("aria-setsize", String(orderedCards.length));
      if (compact) card.setAttribute?.("data-compact-order", String(index + 1));
      const slot = card.querySelector?.(compact ? ".compact-shot-thumb > small" : ".slot");
      if (slot) slot.textContent = String(index + 1).padStart(2, "0");
    });
    // The expanded tray may be parked in a detached fragment in compact mode.
    // Rebuild it from the current Shot state on expansion, never its old order.
    if (compact) container.__hmbImageAssetExpandedDirty = true;
  });
  return [...shot.selected_source_uids];
}

function hmbImageAssetShotForDrag(state, shotUuid) {
  const uuid = imageAssetUuid(shotUuid);
  return (Array.isArray(state?.shot_routing?.shots) ? state.shot_routing.shots : [])
    .find((item) => imageAssetUuid(item?.shot_uuid) === uuid) || null;
}

function hmbImageAssetSelectedCardFromDragEvent(container, event) {
  const target = event?.target?.nodeType === 3 ? event.target.parentElement : event?.target;
  const card = target?.closest?.("[data-selected-key]") || target?.closest?.("[data-compact-asset-key]") || null;
  if (!card || (typeof container?.contains === "function" && !container.contains(card))) return null;
  const tray = card.closest?.("[data-shot-tray]") || card.closest?.("[data-compact-shot-assets]") || null;
  if (!tray || (typeof container?.contains === "function" && !container.contains(tray))) return null;
  return { card, tray, target };
}

function hmbClearImageAssetDropTargets(container) {
  hmbImageAssetDragCards(container, ".drop-target").forEach((card) => {
    card.classList?.remove?.("drop-target");
  });
}

function hmbImageAssetDragCards(container, suffix = "") {
  return [".selected-card", ".compact-shot-asset"].flatMap((selector) => (
    Array.from(container?.querySelectorAll?.(`${selector}${suffix}`) || [])
  ));
}

const IMAGE_ASSET_DRAG_CONTROL_SELECTOR = [
  "button",
  "input",
  "select",
  "textarea",
  "a",
  "[role='button']",
  "[contenteditable='true']",
  "[contenteditable='']",
].join(",");

export function hmbInstallImageAssetShotDragReorder(container, options = {}) {
  if (!container || typeof container.addEventListener !== "function") return () => {};
  const currentState = typeof options.currentState === "function" ? options.currentState : () => ({});
  const commitReorder = typeof options.commitReorder === "function" ? options.commitReorder : () => false;
  const listeners = [];
  const listen = (eventName, handler) => {
    if (typeof options.listen === "function") {
      options.listen(eventName, handler);
      return;
    }
    container.addEventListener(eventName, handler, true);
    listeners.push([eventName, handler]);
  };
  const releaseClickSuppression = () => {
    const release = () => { delete container.__hmbSuppressImageAssetCardClick; };
    if (typeof setTimeout === "function") setTimeout(release, 0);
    else Promise.resolve().then(release);
  };
  const clearCandidate = () => {
    const session = container.__hmbImageAssetDragSession;
    if (session && typeof session === "object") {
      session.targetUid = "";
      session.targetIndex = -1;
    }
    hmbClearImageAssetDropTargets(container);
  };
  const clearSession = () => {
    hmbClearImageAssetDropTargets(container);
    hmbImageAssetDragCards(container, ".dragging").forEach((card) => {
      card.classList?.remove?.("dragging");
      card.setAttribute?.("aria-grabbed", "false");
    });
    delete container.__hmbImageAssetDragSession;
    releaseClickSuppression();
  };
  const setCandidate = (entry, event) => {
    const session = container.__hmbImageAssetDragSession;
    const card = entry?.card || null;
    const targetUid = clean(card?.getAttribute?.("data-shot-source-uid"));
    const targetShotUuid = imageAssetUuid(card?.getAttribute?.("data-shot-uuid"));
    if (
      !session
      || !targetUid
      || targetUid === clean(session.sourceUid)
      || !targetShotUuid
      || targetShotUuid !== imageAssetUuid(session.shotUuid)
    ) {
      clearCandidate();
      return false;
    }
    const shot = hmbImageAssetShotForDrag(currentState(), targetShotUuid);
    const targetIndex = shot?.selected_source_uids.indexOf(targetUid) ?? -1;
    if (targetIndex < 0) {
      clearCandidate();
      return false;
    }
    event?.preventDefault?.();
    event?.stopPropagation?.();
    try { if (event?.dataTransfer) event.dataTransfer.dropEffect = "move"; } catch (_error) {}
    hmbClearImageAssetDropTargets(container);
    card.classList?.add?.("drop-target");
    session.targetUid = targetUid;
    session.targetIndex = targetIndex;
    return true;
  };
  const finalize = (reason) => {
    const session = container.__hmbImageAssetDragSession;
    if (!session || session.committed) return false;
    const shotUuid = imageAssetUuid(session.shotUuid);
    const shot = hmbImageAssetShotForDrag(currentState(), shotUuid);
    const sourceUid = clean(session.sourceUid);
    const targetUid = clean(session.targetUid);
    const sourceIndex = shot?.selected_source_uids.indexOf(sourceUid) ?? -1;
    const targetIndex = shot?.selected_source_uids.indexOf(targetUid) ?? -1;
    if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) {
      clearSession();
      return false;
    }
    session.committed = true;
    const details = {
      reason: clean(reason),
      shotUuid,
      sourceUid,
      targetUid,
      sourceIndex,
      targetIndex,
    };
    // Drop and dragend are two completion routes for the same native gesture.
    // Clear the session first so a synchronous host echo/remount cannot publish
    // the same reorder twice. commitReorder owns the optimistic DOM order and
    // the single authoritative state publication.
    clearSession();
    return commitReorder(details) !== false;
  };

  const retainedSession = container.__hmbImageAssetDragSession;
  if (retainedSession) {
    hmbClearImageAssetDropTargets(container);
    const cards = [
      ...Array.from(container.querySelectorAll?.("[data-selected-key]") || []),
      ...Array.from(container.querySelectorAll?.("[data-compact-asset-key]") || []),
    ];
    const sourceCard = cards.find((card) => (
      clean(card.getAttribute?.("data-shot-source-uid")) === clean(retainedSession.sourceUid)
      && imageAssetUuid(card.getAttribute?.("data-shot-uuid")) === imageAssetUuid(retainedSession.shotUuid)
    ));
    const targetCard = cards.find((card) => (
      clean(card.getAttribute?.("data-shot-source-uid")) === clean(retainedSession.targetUid)
      && imageAssetUuid(card.getAttribute?.("data-shot-uuid")) === imageAssetUuid(retainedSession.shotUuid)
    ));
    if (sourceCard) {
      sourceCard.classList?.add?.("dragging");
      sourceCard.setAttribute?.("aria-grabbed", "true");
      targetCard?.classList?.add?.("drop-target");
    } else {
      clearSession();
    }
  }

  listen("dragstart", (event) => {
    const entry = hmbImageAssetSelectedCardFromDragEvent(container, event);
    const card = entry?.card || null;
    const sourceUid = clean(card?.getAttribute?.("data-shot-source-uid"));
    const shotUuid = imageAssetUuid(card?.getAttribute?.("data-shot-uuid"));
    const shot = hmbImageAssetShotForDrag(currentState(), shotUuid);
    const interactive = entry?.target?.closest?.(IMAGE_ASSET_DRAG_CONTROL_SELECTOR) || null;
    if (
      !card
      || card.getAttribute?.("draggable") !== "true"
      || interactive
      || !sourceUid
      || !shotUuid
      || !shot
      || shot.selected_source_uids.length < 2
      || !shot.selected_source_uids.includes(sourceUid)
    ) {
      event?.preventDefault?.();
      return;
    }
    container.__hmbImageAssetDragSession = {
      shotUuid,
      sourceUid,
      targetUid: "",
      targetIndex: -1,
      committed: false,
    };
    container.__hmbSuppressImageAssetCardClick = true;
    card.classList?.add?.("dragging");
    card.setAttribute?.("aria-grabbed", "true");
    event?.stopPropagation?.();
    try {
      if (event?.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData?.("text/plain", sourceUid);
      }
    } catch (_error) {}
  });
  listen("dragover", (event) => {
    if (!container.__hmbImageAssetDragSession) return;
    const entry = hmbImageAssetSelectedCardFromDragEvent(container, event);
    if (!setCandidate(entry, event)) clearCandidate();
  });
  listen("dragleave", (event) => {
    if (!container.__hmbImageAssetDragSession) return;
    const related = event?.relatedTarget || null;
    if (!related || typeof container.contains !== "function" || !container.contains(related)) clearCandidate();
  });
  listen("drop", (event) => {
    const session = container.__hmbImageAssetDragSession;
    if (!session) return;
    const entry = hmbImageAssetSelectedCardFromDragEvent(container, event);
    if (entry) setCandidate(entry, event);
    if (!clean(session.targetUid)) {
      clearSession();
      return;
    }
    event?.preventDefault?.();
    event?.stopPropagation?.();
    finalize("drop");
  });
  listen("dragend", () => {
    // Griptape can morph a selected card before bubble-phase drop is delivered.
    // The last valid capture-phase target remains authoritative for this drag.
    if (!finalize("dragend")) clearSession();
  });
  listen("click", (event) => {
    if (!container.__hmbSuppressImageAssetCardClick) return;
    const entry = hmbImageAssetSelectedCardFromDragEvent(container, event);
    if (!entry) return;
    event?.preventDefault?.();
    event?.stopPropagation?.();
    event?.stopImmediatePropagation?.();
  });

  return () => {
    listeners.forEach(([eventName, handler]) => {
      container.removeEventListener?.(eventName, handler, true);
    });
    hmbClearImageAssetDropTargets(container);
    hmbImageAssetDragCards(container, ".dragging").forEach((card) => {
      card.classList?.remove?.("dragging");
    });
    // Deliberately retain __hmbImageAssetDragSession: a normal host update
    // morphs this widget in-place and the replacement controller resumes it.
  };
}

export function hmbApplyImageAssetSelectionFeedback(container, state, options = {}) {
  if (!container || !state || !Array.isArray(state.assets)) return null;
  const shot = options.activeShot || activeImageAssetShot(state);
  const selected = Array.isArray(options.selectedAssets)
    ? options.selectedAssets
    : imageAssetShotAssets(state, shot);
  const selectedCount = selected.length;
  state.status = {
    ...(state.status || {}),
    selected_count: selectedAssets(state).length,
  };
  const previousSelectedCount = Number(options.previousSelectedCount);
  const crossedSelectionLimit = Number.isFinite(previousSelectedCount) && (
    (previousSelectedCount < MAX_SHOT_IMAGES && selectedCount >= MAX_SHOT_IMAGES)
    || (previousSelectedCount >= MAX_SHOT_IMAGES && selectedCount < MAX_SHOT_IMAGES)
  );
  let cardScanCount = 0;
  if (Array.isArray(options.changedAssets) && !crossedSelectionLimit) {
    const cardMap = options.cardByLibraryId instanceof Map
      ? options.cardByLibraryId
      : container.__hmbImageAssetCardByLibraryId;
    options.changedAssets.forEach((asset) => {
      const card = cardMap?.get?.(clean(asset?.asset_library_id));
      if (card && asset) hmbApplyImageAssetCardFeedback(card, asset, selectedCount, state, shot);
    });
  } else if (options.changedCard && options.changedAsset && !crossedSelectionLimit) {
    hmbApplyImageAssetCardFeedback(
      options.changedCard,
      options.changedAsset,
      selectedCount,
      state,
      shot,
    );
  } else {
    const assetsByLibraryId = options.assetsByLibraryId instanceof Map
      ? options.assetsByLibraryId
      : new Map(state.assets.map((asset) => [clean(asset.asset_library_id), asset]));
    container.querySelectorAll?.("[data-asset-key]").forEach((card) => {
      cardScanCount += 1;
      const asset = assetsByLibraryId.get(clean(card.getAttribute?.("data-asset-key")));
      if (asset) hmbApplyImageAssetCardFeedback(card, asset, selectedCount, state, shot);
    });
  }

  const trayCount = container.querySelector?.(".shot-panel.active .shot-panel-toggle em")
    || container.querySelector?.(".tray-head em");
  if (trayCount) trayCount.textContent = `${selectedCount}/${MAX_SHOT_IMAGES}`;
  const tray = container.querySelector?.("[data-shot-tray]") || container.querySelector?.(".tray-scroll");
  const trayResult = hmbReconcileImageAssetSelectionTray(tray, selected, state, {
    ...options,
    shot,
  });
  const selectedCardById = new Map();
  tray?.querySelectorAll?.("[data-selected-key]").forEach((card) => {
    const key = clean(card.getAttribute?.("data-selected-key"));
    if (key) selectedCardById.set(key, card);
  });
  container.__hmbImageAssetSelectedCardByLibraryId = selectedCardById;
  const status = container.querySelector?.(".toolbar-status strong");
  if (status && !state.error && !state.asset_registration_result?.message) {
    const summary = hmbImageAssetStatusSummary(state);
    status.textContent = summary;
    status.setAttribute?.("title", summary);
  }
  return { cardScanCount, selectedCount, tray: trayResult };
}

export function hmbApplyImageAssetShotSwitchFeedback(container, state, options = {}) {
  if (!container || !state) return false;
  const shot = activeImageAssetShot(state);
  if (!shot) return false;
  const root = container.querySelector?.(".hmb-image-assets");
  const palette = hmbImageAssetShotPalette(shot.number);
  root?.setAttribute?.("data-shot-number", String(shot.number));
  root?.style?.setProperty?.("--active-shot-accent", palette.accent);
  root?.style?.setProperty?.("--active-shot-rgb", palette.rgb);

  const tray = container.querySelector?.("[data-shot-tray]") || null;
  let activePanel = null;
  container.querySelectorAll?.("[data-shot-panel]").forEach((panel) => {
    const active = clean(panel.getAttribute?.("data-shot-uuid")) === shot.shot_uuid;
    panel.classList?.toggle?.("active", active);
    panel.classList?.toggle?.("collapsed", !active);
    panel.querySelector?.("[data-shot-tab]")?.setAttribute?.("aria-expanded", active ? "true" : "false");
    if (active) activePanel = panel;
  });
  if (tray && activePanel && tray.parentElement !== activePanel) {
    activePanel.appendChild?.(tray);
  }
  tray?.setAttribute?.("data-shot-tray", shot.shot_uuid);
  const previousUids = new Set(options.previousShot?.selected_source_uids || []);
  const nextUids = new Set(shot.selected_source_uids || []);
  const changedUids = new Set([
    ...[...previousUids].filter((uid) => !nextUids.has(uid)),
    ...[...nextUids].filter((uid) => !previousUids.has(uid)),
  ]);
  const assetsBySourceUid = options.assetsBySourceUid instanceof Map
    ? options.assetsBySourceUid
    : new Map(state.assets.map((asset) => [clean(asset.source_uid), asset]));
  hmbApplyImageAssetSelectionFeedback(container, state, {
    assetsByLibraryId: options.assetsByLibraryId,
    cardByLibraryId: options.cardByLibraryId || container.__hmbImageAssetCardByLibraryId,
    changedAssets: [...changedUids].map((uid) => assetsBySourceUid.get(uid)).filter(Boolean),
    previousSelectedCount: previousUids.size,
    selectedAssets: imageAssetShotAssets(state, shot),
    activeShot: shot,
  });
  return true;
}

function hmbCancelImageAssetSelectionJobHandles(job) {
  if (!job) return;
  if (job.fallbackTimer != null && typeof clearTimeout === "function") {
    try { clearTimeout(job.fallbackTimer); } catch (_error) {}
  }
  if (typeof cancelAnimationFrame === "function") {
    [job.firstFrame, job.secondFrame].forEach((handle) => {
      if (handle == null) return;
      try { cancelAnimationFrame(handle); } catch (_error) {}
    });
  }
  job.fallbackTimer = null;
  job.firstFrame = null;
  job.secondFrame = null;
}

function hmbSettleImageAssetSelectionCommit(container, job, publish) {
  if (!container || !job || job.settled) return false;
  if (container.__hmbImageAssetSelectionCommitJob !== job) return false;
  const currentMountToken = Number(container.__hmbImageAssetMountToken) || 0;
  if (job.mountToken && currentMountToken !== job.mountToken) publish = false;
  job.settled = true;
  hmbCancelImageAssetSelectionJobHandles(job);
  delete container.__hmbImageAssetSelectionCommitJob;
  container.__hmbImageAssetSelectionCommitPending = false;
  if (!publish) return false;
  container.__hmbImageAssetSelectionCommitRunning = true;
  try {
    job.commit(job.token);
  } finally {
    container.__hmbImageAssetSelectionCommitRunning = false;
  }
  return true;
}

export function hmbCancelImageAssetSelectionCommit(container) {
  const job = container && container.__hmbImageAssetSelectionCommitJob;
  return hmbSettleImageAssetSelectionCommit(container, job, false);
}

export function hmbFlushImageAssetSelectionCommit(container) {
  const job = container && container.__hmbImageAssetSelectionCommitJob;
  return hmbSettleImageAssetSelectionCommit(container, job, true);
}

export function hmbScheduleImageAssetSelectionCommit(container, commit) {
  if (!container || typeof commit !== "function") return 0;
  hmbCancelImageAssetSelectionCommit(container);
  const token = ++imageAssetSelectionCommitSequence;
  const job = {
    token,
    mountToken: Number(container.__hmbImageAssetMountToken) || 0,
    commit,
    settled: false,
    firstFrame: null,
    secondFrame: null,
    fallbackTimer: null,
  };
  container.__hmbImageAssetSelectionCommitJob = job;
  container.__hmbImageAssetSelectionCommitPending = true;
  const run = () => hmbSettleImageAssetSelectionCommit(container, job, true);
  if (typeof setTimeout === "function") {
    // requestAnimationFrame can stop entirely in a background tab. The bounded
    // fallback preserves the click even when no paint callbacks are delivered.
    job.fallbackTimer = setTimeout(run, IMAGE_ASSET_SELECTION_COMMIT_FALLBACK_MS);
  }
  if (typeof requestAnimationFrame === "function") {
    // The first frame paints local card/tray feedback; the second publishes.
    job.firstFrame = requestAnimationFrame(() => {
      if (job.settled || container.__hmbImageAssetSelectionCommitJob !== job) return;
      job.secondFrame = requestAnimationFrame(run);
    });
  } else if (job.fallbackTimer == null) {
    run();
  }
  return token;
}

function displayWindowsPath(value) {
  const path = clean(value);
  return /^[A-Za-z]:\//.test(path) ? path.replaceAll("/", "\\") : path;
}

function registrationMainTypes(taxonomy) {
  return uniqueStrings(taxonomy?.image_main_type_choices).filter(
    (value) => value !== "Select Image Main Type",
  );
}

export function hmbImageAssetRegistrationSubTypes(taxonomy, sourceType) {
  const mapped = taxonomy?.image_sub_type_choices?.[clean(sourceType)];
  return uniqueStrings(Array.isArray(mapped) ? mapped : []).filter(Boolean);
}

export function hmbCreateImageAssetRegistrationDraft(asset, taxonomy = {}) {
  if (!hmbImageAssetCanRegister(asset)) return null;
  const assetMainType = clean(asset.image_main_type);
  const assetSubType = clean(asset.image_sub_type);
  const sourceType = assetMainType !== "Select Image Main Type" ? assetMainType : "";
  const sourceKind = clean(asset.source_kind).toLowerCase() === "user" ? "user" : "project";
  const relativePath = clean(asset.relative_path).replaceAll("\\", "/");
  const lockedFolder = relativePath.includes("/")
    ? relativePath.slice(0, relativePath.lastIndexOf("/"))
    : ROOT_FOLDER_KEY;
  return {
    asset_library_id: clean(asset.asset_library_id),
    source_kind: sourceKind,
    source_uid: clean(asset.source_uid),
    relative_path: relativePath,
    target_folder: sourceKind === "project" ? lockedFolder : "",
    target_folder_confirmed: sourceKind === "project",
    image_name: clean(asset.image_name).slice(0, 256),
    asset_id: clean(asset.asset_id).slice(0, 256),
    image_main_type: sourceType,
    image_sub_type: assetSubType,
    custom_source_type: clean(asset.custom_source_type).slice(0, 256),
  };
}

export function hmbInstallImageAssetRegistrationBackdropDismissal(
  backdrop,
  closeRegistration,
  addListener = null,
) {
  if (!backdrop?.addEventListener || typeof closeRegistration !== "function") return () => {};
  const ownedListeners = [];
  const listen = typeof addListener === "function"
    ? addListener
    : (target, type, handler, options) => {
      target.addEventListener(type, handler, options);
      ownedListeners.push([target, type, handler, options]);
    };
  const dragThresholdSquared = 36;
  let gesture = null;
  const eventCoordinate = (event, key) => {
    const value = Number(event?.[key]);
    return Number.isFinite(value) ? value : null;
  };
  const gestureMatches = (event) => {
    if (!gesture) return false;
    if (gesture.family !== "pointer") return !String(event?.type || "").startsWith("pointer");
    return (
      String(event?.type || "").startsWith("pointer")
      && (gesture.pointerId == null || event?.pointerId == null || event.pointerId === gesture.pointerId)
    );
  };
  const updateGestureMovement = (event) => {
    if (!gestureMatches(event) || gesture.moved) return;
    const x = eventCoordinate(event, "clientX");
    const y = eventCoordinate(event, "clientY");
    if (x == null || y == null || gesture.startX == null || gesture.startY == null) return;
    const deltaX = x - gesture.startX;
    const deltaY = y - gesture.startY;
    if ((deltaX * deltaX) + (deltaY * deltaY) > dragThresholdSquared) gesture.moved = true;
  };
  const beginGesture = (event) => {
    const family = String(event?.type || "").startsWith("pointer") ? "pointer" : "mouse";
    // Ignore the compatibility mousedown that follows a PointerEvent. The
    // PointerEvent carries the stable pointerId needed to keep multitouch and
    // mixed-device sequences from completing one another.
    if (family === "mouse" && gesture?.family === "pointer") return;
    const button = Number(event?.button ?? 0);
    if (button !== 0 || event?.isPrimary === false) {
      gesture = null;
      return;
    }
    gesture = {
      family,
      pointerId: family === "pointer" && event?.pointerId != null ? event.pointerId : null,
      startedOnBackdrop: event?.target === backdrop,
      endedOnBackdrop: false,
      ended: false,
      moved: false,
      startX: eventCoordinate(event, "clientX"),
      startY: eventCoordinate(event, "clientY"),
    };
  };
  const endGesture = (event) => {
    if (!gestureMatches(event)) return;
    updateGestureMovement(event);
    gesture.endedOnBackdrop = event?.target === backdrop;
    gesture.ended = true;
  };
  const cancelGesture = () => {
    gesture = null;
  };
  const cancelMatchingGesture = (event) => {
    if (gestureMatches(event)) cancelGesture();
  };
  const activateBackdrop = (event) => {
    const shouldClose = (
      event?.target === backdrop
      && gesture?.startedOnBackdrop
      && gesture?.endedOnBackdrop
      && gesture?.ended
      && !gesture?.moved
    );
    cancelGesture();
    if (shouldClose) closeRegistration();
  };
  // A browser may target `click` at the nearest common ancestor when text
  // selection starts in an input and the pointer is released on the backdrop.
  // Both ends must therefore be the real backdrop surface. Capture phase keeps
  // this record reliable even when a form control stops its own pointer event.
  for (const type of ["pointerdown", "mousedown"]) {
    listen(backdrop, type, beginGesture, true);
  }
  for (const type of ["pointermove", "mousemove"]) {
    listen(backdrop, type, updateGestureMovement, true);
  }
  for (const type of ["pointerup", "mouseup"]) {
    listen(backdrop, type, endGesture, true);
  }
  listen(backdrop, "pointercancel", cancelMatchingGesture, true);
  listen(backdrop, "lostpointercapture", cancelMatchingGesture, true);
  listen(backdrop, "click", activateBackdrop);
  return () => {
    ownedListeners.forEach(([target, type, handler, options]) => {
      target.removeEventListener?.(type, handler, options);
    });
    ownedListeners.length = 0;
    cancelGesture();
  };
}

function registrationOptions(state, values, selected, placeholder) {
  return [
    `<option value="">${escapeHtml(placeholder)}</option>`,
    ...values.map((value) => (
      `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(imageAssetTaxonomyLabel(state, value))}</option>`
    )),
  ].join("");
}

function registrationDraftIsComplete(draft) {
  return Boolean(
    clean(draft?.image_name)
    && clean(draft?.asset_id)
    && clean(draft?.image_main_type)
    && (
      draft?.source_kind !== "user"
      || (
        draft?.target_folder_confirmed
        && clean(draft?.target_folder)
        && clean(draft?.target_folder) !== ROOT_FOLDER_KEY
      )
    )
  );
}

function registrationFolderOptions(state, draft) {
  const selected = clean(draft?.target_folder);
  const options = [
    `<option value="" ${selected ? "" : "selected"} disabled>${escapeHtml(imageAssetText(state, "select_project_folder"))}</option>`,
  ];
  state.folders
    .filter((folder) => clean(folder) && !isUserImportFolder(folder))
    .forEach((folder) => {
      options.push(
        `<option value="${escapeHtml(folder)}" ${selected === folder ? "selected" : ""}>${escapeHtml(folder)}</option>`,
      );
    });
  return options.join("");
}

function registrationFolderField(state, draft, externalImport) {
  if (!externalImport) return "";
  return (
    `<label class="passport-folder" title="${escapeHtml(imageAssetText(state, "project_folder_select"))}">`
    + `<span>${escapeHtml(imageAssetText(state, "project_folder"))}</span>`
    + `<select data-registration-folder>${registrationFolderOptions(state, draft)}</select>`
    + "</label>"
  );
}

function renderRegistrationDialog(state, draft) {
  if (!draft) return "";
  const asset = state.assets.find(
    (item) => item.asset_library_id === clean(draft.asset_library_id),
  );
  const externalImport = asset?.source_kind === "user" && Number(asset?.import_index || 0) > 0;
  if (
    !asset
    || !hmbImageAssetCanRegister(asset)
  ) return "";
  const mainTypes = uniqueStrings([
    ...registrationMainTypes(state.taxonomy),
    clean(draft.image_main_type),
  ]).filter(Boolean);
  const subTypes = uniqueStrings([
    ...hmbImageAssetRegistrationSubTypes(state.taxonomy, draft.image_main_type),
    clean(draft.image_sub_type),
  ]).filter(Boolean);
  const customMainType = draft.image_main_type === "Custom / Context" && draft.image_sub_type === "Custom"
    ? `<label><span>${escapeHtml(imageAssetText(state, "custom_main_type"))}</span><input data-registration-field="custom_source_type" maxlength="256" value="${escapeHtml(draft.custom_source_type)}"/></label>`
    : "";
  const taxonomyMeaning = imageAssetTaxonomyMeaning(
    state,
    draft.image_main_type,
    draft.image_sub_type,
  );
  const thumbnailSource = imageSource(asset);
  const thumbnailFailed = !thumbnailSource && hmbImageAssetThumbnailFailed(asset);
  return `
    <div class="asset-registration-backdrop" data-registration-backdrop>
      <section class="asset-passport" role="dialog" aria-modal="true" aria-labelledby="asset-registration-title">
        <header class="passport-head">
          <div><small>${escapeHtml(imageAssetText(state, "hmb_project_asset"))}</small><h2 id="asset-registration-title">${escapeHtml(imageAssetText(state, "asset_passport"))}</h2></div>
          <button type="button" data-registration-cancel aria-label="${escapeHtml(imageAssetText(state, "close_registration"))}">&times;</button>
        </header>
        <div class="passport-photo ${thumbnailSource ? "" : thumbnailFailed ? "fallback thumbnail-failed" : "fallback thumbnail-loading"}" data-thumbnail-loading="${thumbnailSource || thumbnailFailed ? "false" : "true"}" data-thumbnail-failed="${thumbnailFailed ? "true" : "false"}">${thumbnailImageMarkup(asset)}</div>
        <div class="passport-file"><b>${escapeHtml(asset.relative_path || asset.path || asset.media_ref_kind)}</b><span>${asset.width && asset.height ? `${asset.width} × ${asset.height}` : escapeHtml(imageAssetText(state, "metadata_pending"))}</span></div>
        <div class="passport-fields">
          ${registrationFolderField(state, draft, externalImport)}
          <label><span>${escapeHtml(imageAssetText(state, "final_image_name"))}</span><input data-registration-field="image_name" maxlength="256" value="${escapeHtml(draft.image_name)}"/></label>
          <label><span>${escapeHtml(imageAssetText(state, "asset_id"))}</span><input data-registration-field="asset_id" maxlength="256" value="${escapeHtml(draft.asset_id)}"/></label>
          <label><span>${escapeHtml(imageAssetText(state, "main_type_label"))}</span><select data-registration-main>${registrationOptions(state, mainTypes, draft.image_main_type, imageAssetText(state, "select_main_type"))}</select></label>
           ${customMainType}
           <label><span>${escapeHtml(imageAssetText(state, "sub_type_label"))}</span><select data-registration-sub ${draft.image_main_type ? "" : "disabled"}>${registrationOptions(state, subTypes, draft.image_sub_type, imageAssetText(state, "select_sub_type"))}</select></label>
          <div class="passport-taxonomy-contract" ${taxonomyMeaning ? "" : "hidden"}><small>${escapeHtml(imageAssetText(state, "taxonomy_contract"))}</small><span>${escapeHtml(taxonomyMeaning)}</span></div>
         </div>
        <footer class="passport-actions">
          <button type="button" data-registration-cancel>${escapeHtml(imageAssetText(state, "cancel"))}</button>
          ${externalImport && state.image_bash_active && state.image_bash_workspace?.workspace_id ? `<button type="button" data-registration-bash-add ${draft.bash_pending || state.image_bash_workspace.instances.length >= MAX_SELECTED_IMAGES ? "disabled" : ""}>HMBImageBash에 추가</button>` : ""}
          <button type="button" class="passport-register" data-registration-submit ${registrationDraftIsComplete(draft) && !draft.bash_pending ? "" : "disabled"}>${escapeHtml(imageAssetText(state, "register_asset"))}</button>
        </footer>
      </section>
    </div>
  `;
}

function imageAssetRefreshReviewKey(review) {
  return review?.request_id
    ? JSON.stringify([clean(review.project_root).toLowerCase(), review.project_id, review.request_id])
    : "";
}

export function hmbImageAssetRefreshCleanupEligible(state, review = state?.asset_refresh_review) {
  return Boolean(
    review?.request_id
    && review.status === "review"
    && review.safe_to_clean === true
    && review.missing_count > 0
    && clean(review.project_root).toLowerCase() === clean(state?.project_root).toLowerCase()
    && clean(review.project_id) === clean(state?.project_id),
  );
}

export function hmbSyncImageAssetRefreshReview(container, state) {
  if (!container) return null;
  const review = state?.asset_refresh_review;
  const key = imageAssetRefreshReviewKey(review);
  if (
    !key
    || clean(review.project_root).toLowerCase() !== clean(state?.project_root).toLowerCase()
    || clean(review.project_id) !== clean(state?.project_id)
  ) {
    delete container.__hmbImageAssetRefreshReviewOpen;
    delete container.__hmbImageAssetRefreshReviewConfirm;
    delete container.__hmbImageAssetRefreshCleanupPending;
    return null;
  }
  const seen = container.__hmbImageAssetRefreshReviewsSeen ||= new Set();
  if (!seen.has(key)) {
    seen.add(key);
    while (seen.size > 64) seen.delete(seen.values().next().value);
    container.__hmbImageAssetRefreshReviewOpen = key;
    delete container.__hmbImageAssetRefreshReviewConfirm;
    delete container.__hmbImageAssetRefreshReviewError;
  }
  if (
    container.__hmbImageAssetRefreshCleanupPending !== key
    || review.status !== "review"
  ) delete container.__hmbImageAssetRefreshCleanupPending;
  if (review.status !== "review") {
    delete container.__hmbImageAssetRefreshReviewConfirm;
    delete container.__hmbImageAssetRefreshReviewError;
  }
  // Dismissal is local UI state. A thumbnail echo or the completion of an
  // already-dismissed report must not reopen that report or write a command.
  if (container.__hmbImageAssetRefreshReviewOpen !== key) return null;
  return {
    review,
    confirming: container.__hmbImageAssetRefreshReviewConfirm === key,
    busy: container.__hmbImageAssetRefreshCleanupPending === key,
    error: clean(container.__hmbImageAssetRefreshReviewError),
  };
}

export function hmbRenderImageAssetRefreshReview(state, view) {
  if (!view?.review?.request_id) return "";
  const { review, confirming, busy } = view;
  const label = (key) => escapeHtml(imageAssetText(state, key));
  const paths = (items) => items.length
    ? `<ul>${items.map((path) => `<li>${escapeHtml(path)}</li>`).join("")}</ul>`
    : `<p>${label("refresh_none")}</p>`;
  const canClean = hmbImageAssetRefreshCleanupEligible(state, review) && !busy && !state.scan_busy;
  return `<div class="asset-registration-backdrop asset-refresh-backdrop nodrag nopan nowheel" data-refresh-review-backdrop>
    <section class="asset-passport asset-refresh-review" role="dialog" aria-modal="true" aria-label="${label(confirming ? "refresh_confirm" : "refresh_review")}" ${busy ? 'aria-busy="true"' : ""}>
      <header class="passport-head"><div><small>${label("project")} · ${escapeHtml(review.project_id)}</small><h2>${label(confirming ? "refresh_confirm" : "refresh_review")}</h2></div><button type="button" data-refresh-review-cancel aria-label="${label("refresh_close")}">&times;</button></header>
      <div class="refresh-review-body">
        <p class="refresh-review-root">${escapeHtml(review.project_root)}</p>
        <p>${label("registered")}: ${review.registered_count} · ${label("refresh_files")}: ${review.file_count}</p>
        ${review.status === "cleaned" ? `<p role="status">${label("refresh_cleaned")}: ${review.cleaned_count}</p>${review.backup_path ? `<p>${label("refresh_backup")}: <span class="refresh-review-path">${escapeHtml(review.backup_path)}</span></p>` : ""}` : ""}
        ${view.error || review.error ? `<p class="refresh-review-error" role="alert">${escapeHtml(view.error || review.error)}</p>` : ""}
        ${review.status === "review" && !review.safe_to_clean ? `<p class="refresh-review-error">${label("refresh_unsafe")}</p>` : ""}
        <h3>${label("refresh_missing")}: ${review.missing_count}</h3><p>${label("refresh_missing_hint")}</p>${paths(review.missing_paths)}
        <h3>${label("refresh_unregistered")}: ${review.unregistered_count}</h3><p>${label("refresh_unregistered_hint")}</p>${paths(review.unregistered_paths)}
        ${confirming ? `<p class="refresh-review-confirm">${label("refresh_confirm_hint")}</p>` : ""}
        ${busy ? `<p role="status">${label("refresh_cleaning")}</p>` : ""}
      </div>
      <footer class="passport-actions"><button type="button" data-refresh-review-cancel>${label(review.status === "review" ? "cancel" : "close")}</button>${review.status === "review" ? `<button type="button" class="passport-register" ${confirming ? "data-refresh-cleanup-confirm" : "data-refresh-cleanup-start"} ${canClean ? "" : "disabled"}>${label(busy ? "refresh_cleaning" : confirming ? "refresh_confirm" : "refresh_cleanup")}</button>` : ""}</footer>
    </section>
  </div>`;
}

function hmbSetImageAssetRefreshReviewInert(container, active) {
  const root = container.querySelector?.(".hmb-image-assets");
  root?.querySelectorAll?.("[data-refresh-review-inert]").forEach((element) => {
    element.removeAttribute?.("inert");
    element.removeAttribute?.("aria-hidden");
    element.removeAttribute?.("data-refresh-review-inert");
  });
  if (!active) return;
  for (const selector of [".top", "[data-library-expanded]", "[data-library-compact-summary]"]) {
    const element = root?.querySelector?.(selector);
    element?.setAttribute?.("inert", "");
    element?.setAttribute?.("aria-hidden", "true");
    element?.setAttribute?.("data-refresh-review-inert", "");
  }
}

export function hmbPatchImageAssetRefreshReview(container, state, view) {
  const root = container.querySelector?.(".hmb-image-assets");
  if (!root) return false;
  const current = root.querySelector?.("[data-refresh-review-backdrop]");
  const ownerDocument = root.ownerDocument || container.ownerDocument;
  if (view && ownerDocument?.createElement) {
    const template = ownerDocument.createElement("template");
    template.innerHTML = hmbRenderImageAssetRefreshReview(state, view).trim();
    const desired = template.content?.firstElementChild;
    if (current && desired) hmbPatchImageAssetElement(current, desired);
    else if (desired) root.appendChild?.(desired);
  } else current?.remove?.();
  hmbSetImageAssetRefreshReviewInert(container, Boolean(view));
  return true;
}

export function hmbInstallImageAssetRefreshReviewEvents(container, state, props, remount) {
  container.__hmbImageAssetRefreshReviewCleanup?.();
  delete container.__hmbImageAssetRefreshReviewCleanup;
  const backdrop = container.querySelector("[data-refresh-review-backdrop]");
  if (!backdrop) return;
  const listeners = [];
  const on = (target, type, handler, options) => {
    if (!target?.addEventListener) return;
    target.addEventListener(type, handler, options);
    listeners.push([target, type, handler, options]);
  };
  container.__hmbImageAssetRefreshReviewCleanup = () => {
    listeners.forEach(([target, type, handler, options]) => target.removeEventListener?.(type, handler, options));
  };
  const currentState = () => container.__hmbImageAssetLatestState || state;
  const close = () => {
    delete container.__hmbImageAssetRefreshReviewOpen;
    delete container.__hmbImageAssetRefreshReviewConfirm;
    delete container.__hmbImageAssetRefreshReviewError;
    remount(currentState());
    container.querySelector("[data-project-reload]")?.focus?.();
  };
  container.querySelectorAll("[data-refresh-review-cancel]").forEach((button) => {
    on(button, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      close();
    });
  });
  hmbInstallImageAssetRegistrationBackdropDismissal(backdrop, close, on);
  for (const type of ["click", "dblclick", "pointerdown", "mousedown", "pointerup", "mouseup", "wheel"]) {
    on(backdrop, type, (event) => event.stopPropagation(), type === "wheel" ? { passive: true } : undefined);
  }
  on(backdrop, "keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const buttons = Array.from(backdrop.querySelectorAll("button:not([disabled])"));
    if (!buttons.length) return;
    const active = typeof document !== "undefined" ? document.activeElement : null;
    const index = buttons.indexOf(active);
    if (event.shiftKey && index <= 0) {
      event.preventDefault();
      buttons[buttons.length - 1].focus?.();
    } else if (!event.shiftKey && (index < 0 || index >= buttons.length - 1)) {
      event.preventDefault();
      buttons[0].focus?.();
    }
  });
  on(container.querySelector("[data-refresh-cleanup-start]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    state = currentState();
    if (!hmbImageAssetRefreshCleanupEligible(state) || state.scan_busy || container.__hmbImageAssetRefreshCleanupPending) return;
    container.__hmbImageAssetRefreshReviewConfirm = imageAssetRefreshReviewKey(state.asset_refresh_review);
    remount(state);
    container.querySelector("[data-refresh-cleanup-confirm]")?.focus?.();
  });
  on(container.querySelector("[data-refresh-cleanup-confirm]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    state = currentState();
    const key = imageAssetRefreshReviewKey(state.asset_refresh_review);
    if (
      !hmbImageAssetRefreshCleanupEligible(state)
      || state.scan_busy
      || container.__hmbImageAssetRefreshCleanupPending
      || container.__hmbImageAssetRefreshReviewConfirm !== key
    ) return;
    container.__hmbImageAssetRefreshCleanupPending = key;
    delete container.__hmbImageAssetRefreshReviewError;
    const baseline = remount(state);
    const commandState = normalizeState(baseline);
    commandState.asset_cleanup_request = { request_id: commandState.asset_refresh_review.request_id };
    const published = emit(props, commandState, container, (error) => {
      if (container.__hmbImageAssetRefreshCleanupPending !== key) return;
      delete container.__hmbImageAssetRefreshCleanupPending;
      container.__hmbImageAssetRefreshReviewError = clean(error?.message || error)
        || imageAssetText(currentState(), "transport_failed");
      remount(currentState());
    });
    // The command belongs only to this publication. Never replay it through a
    // later language/selection/thumbnail update, or replace a synchronous
    // authoritative completion with the pre-cleanup review.
    published.asset_cleanup_request = {};
    delete container.__hmbImageAssetCanonicalSerialization;
    if (container.__hmbImageAssetLatestState === baseline) {
      state = published;
      container.__hmbImageAssetLatestState = state;
    }
  });
}

function renderImageBashWorkspace(state, compact = false) {
  const workspace = state.image_bash_workspace;
  if (!workspace?.workspace_id) return "";
  const active = Boolean(state.image_bash_active), rows = hmbImageBashWorkspaceAssets(state);
  const cards = rows.map(({ instance_id: id, source_uid: sourceUid, asset }, index) => {
    const name = clean(asset?.image_name) || clean(asset?.asset_id) || sourceUid;
    return `<article class="${compact ? "compact-shot-asset" : "selected-card"} image-bash-card ${asset ? "" : "missing"}" data-image-bash-instance="${escapeHtml(id)}" data-image-bash-source="${escapeHtml(sourceUid)}" data-image-bash-asset-key="${escapeHtml(asset?.asset_library_id || "")}" draggable="true" role="listitem" aria-posinset="${index + 1}" aria-setsize="${rows.length}" title="${escapeHtml(name)}"><div class="selected-card-top"><strong class="slot">${String(index + 1).padStart(2, "0")}</strong><div class="selected-actions"><button type="button" data-image-bash-duplicate="${id}" aria-label="Duplicate image" title="${imageAssetLanguage(state) === "ko" ? "이미지 인스턴스 복제" : "Duplicate image instance"}" ${rows.length >= MAX_SELECTED_IMAGES ? "disabled" : ""}>⧉</button><button type="button" data-image-bash-remove="${id}" aria-label="Remove image instance">×</button></div></div><div class="selected-card-body">${asset ? thumbnailHtml(asset, "selected-thumb") : '<span class="image-bash-missing">이미지 연결 확인 필요</span>'}</div>${compact ? `<b>${escapeHtml(name)}</b>` : ""}</article>`;
  }).join("");
  const tray = active || compact ? `<div class="${compact ? "compact-shot-assets" : "tray-scroll"}" data-image-bash-tray="${workspace.workspace_id}" role="list">${cards || `<div class="tray-empty">${imageAssetLanguage(state) === "ko" ? "라이브러리 이미지를 클릭하여 추가하세요. 중복 이미지도 개별로 유지됩니다." : "Click library images to add independent image instances."}</div>`}</div>` : "";
  return `<section class="${compact ? "compact-shot-row" : "shot-panel"} image-bash-panel ${active ? "active" : "collapsed"}" data-image-bash-panel="${workspace.workspace_id}" style="--shot-accent:#22d3ee;--shot-rgb:34,211,238"><header class="shot-panel-head"><button type="button" class="shot-panel-toggle" data-image-bash-tab aria-expanded="${active}"><small>IB</small><b>HMBImageBash</b><span>${escapeHtml(imageAssetText(state, "selected_images"))}</span><em>${rows.length}/${MAX_SELECTED_IMAGES}</em><i>REMOTE</i></button></header>${tray}</section>`;
}

function renderImageAssetShotStack(state) {
  const routing = ensureImageAssetShotRouting(state);
  const active = routing.shots.find((shot) => shot.shot_uuid === routing.active_shot_uuid)
    || routing.shots[0];
  const isKorean = imageAssetLanguage(state) === "ko";
  return `<section class="shot-stack" data-shot-stack data-channel="${escapeHtml(routing.channel_uuid)}">${routing.shots.map((shot) => {
    const isActive = !state.image_bash_active && shot.shot_uuid === active.shot_uuid;
    const palette = hmbImageAssetShotPalette(shot.number);
    const shotAssets = imageAssetShotAssets(state, shot);
    const hierarchyBound = state.shot_hierarchy?.members?.some(row => row.gp_shot_uuid === shot.shot_uuid);
    const number = String(shot.number).padStart(2, "0");
    const canRename = hmbImageAssetShotCanRename(state, shot.shot_uuid);
    const renameLabel = canRename ? imageAssetText(state, "rename_shot") : (isKorean ? "CGT 샷 이름은 원본으로 유지됩니다" : "CGT shot names are fixed");
    const addButton = shot.number === 1
      ? `<button type="button" class="shot-add" data-shot-add title="${escapeHtml(isKorean ? "CGT 선택 · 수동 샷 추가 · 묶음 구성" : "Select CGT shots · Add manual shots · Manage groups")}">+ Shot</button>`
      : "";
    const tray = isActive
      ? `<div class="tray-scroll" data-shot-tray="${escapeHtml(shot.shot_uuid)}">${shotAssets.map((asset, index) => renderSelectedCard(asset, index, shotAssets, state, shot)).join("") || `<div class="tray-empty">${escapeHtml(imageAssetText(state, "tray_empty"))}</div>`}</div>`
      : "";
    return `<section class="shot-panel ${isActive ? "active" : "collapsed"}" data-shot-panel data-shot-number="${shot.number}" data-shot-uuid="${escapeHtml(shot.shot_uuid)}" style="--shot-accent:${palette.accent};--shot-rgb:${palette.rgb}">
      <header class="shot-panel-head">
        <button type="button" class="shot-panel-toggle" data-shot-tab="${escapeHtml(shot.shot_uuid)}" aria-expanded="${isActive ? "true" : "false"}" title="${escapeHtml(isKorean ? "클릭하여 Shot 열기" : "Open Shot")}">
          <small>${number}</small><b data-shot-name>${escapeHtml(shot.name)}</b><span>${escapeHtml(imageAssetText(state, "selected_images"))}</span><em>${shotAssets.length}/${MAX_SHOT_IMAGES}</em><i>REMOTE</i>
        </button><button type="button" class="shot-rename" data-shot-rename="${escapeHtml(shot.shot_uuid)}" aria-label="${escapeHtml(renameLabel)}" title="${escapeHtml(renameLabel)}" ${canRename ? "" : "disabled"}>✎</button><button type="button" class="shot-delete" data-shot-delete="${escapeHtml(shot.shot_uuid)}" aria-label="${escapeHtml(imageAssetText(state, "delete_shot"))}" title="${escapeHtml(hierarchyBound ? "묶음 구성에서 연결 해제 후 삭제하세요" : routing.shots.length <= 1 ? imageAssetText(state, "keep_one_shot") : imageAssetText(state, "delete_shot"))}" ${routing.shots.length <= 1 || hierarchyBound ? "disabled" : ""}>&times;</button>${addButton}
      </header>${tray}
    </section>`;
  }).join("")}${renderImageBashWorkspace(state)}</section>`;
}

export function hmbImageAssetCompactShotRows(state) {
  const routing = ensureImageAssetShotRouting(state);
  if (!routing) return [];
  // One ephemeral index per projection, not five full-catalog scans/sorts.
  // Never cache by array identity: selection is intentionally mutated in place.
  const selectedByUid = new Map(selectedAssets(state).map((asset) => [clean(asset.source_uid), asset]));
  return routing.shots.slice(0, MAX_IMAGE_ASSET_SHOTS).map((shot) => ({
    shot_uuid: shot.shot_uuid,
    number: shot.number,
    name: shot.name,
    active: !state.image_bash_active && shot.shot_uuid === routing.active_shot_uuid,
    palette: hmbImageAssetShotPalette(shot.number),
    assets: imageAssetShotAssets(state, shot, selectedByUid).map((asset, index) => ({
      ...asset,
      order: index + 1,
    })),
  }));
}

function renderImageAssetCompactAsset(asset, index, shotUuid, count) {
  const sourceUid = clean(asset?.source_uid);
  const key = sourceUid || clean(asset?.asset_library_id) || `compact-${index}`;
  const name = clean(asset?.image_name) || clean(asset?.asset_id) || `Image ${index + 1}`;
  const source = imageSource(asset || {});
  const failed = !source && hmbImageAssetThumbnailFailed(asset);
  const media = source
    ? `<img data-hmb-compact-src="${escapeHtml(source)}" alt="" draggable="false" loading="lazy" decoding="async" fetchpriority="low"/>`
    : `<span class="compact-shot-placeholder" aria-hidden="true">${imageAssetThumbnailFallbackMarkup(asset)}</span>`;
  return `<article class="compact-shot-asset ${source ? "" : failed ? "thumbnail-failed" : "thumbnail-loading"}" draggable="true" aria-grabbed="false" role="listitem" aria-posinset="${index + 1}" aria-setsize="${count}" data-thumbnail-loading="${source || failed ? "false" : "true"}" data-thumbnail-failed="${failed ? "true" : "false"}" data-compact-asset-key="${escapeHtml(key)}" data-shot-source-uid="${escapeHtml(sourceUid)}" data-shot-uuid="${escapeHtml(shotUuid)}" data-compact-order="${index + 1}" title="${escapeHtml(name)}">
      <div class="compact-shot-thumb">${media}<small>${String(index + 1).padStart(2, "0")}</small></div>
      <b>${escapeHtml(name)}</b>
    </article>`;
}

function renderImageAssetCompactShotRow(state, row) {
  const assets = Array.isArray(row?.assets) ? row.assets.slice(0, MAX_SHOT_IMAGES) : [];
  return `<article class="compact-shot-row ${row.active ? "active" : ""}" data-compact-shot-row="${escapeHtml(row.shot_uuid)}" data-shot-number="${row.number}" style="--shot-accent:${row.palette.accent};--shot-rgb:${row.palette.rgb}">
      <header class="compact-shot-head"><small>${String(row.number).padStart(2, "0")}</small><b data-compact-shot-name>${escapeHtml(row.name)}</b><span>${escapeHtml(imageAssetText(state, "selected_images"))}</span><em data-compact-shot-count>${assets.length}/${MAX_SHOT_IMAGES}</em><i>REMOTE</i></header>
      <div class="compact-shot-assets ${assets.length ? "" : "empty"}" role="list" data-compact-shot-assets="${escapeHtml(row.shot_uuid)}">${assets.map((asset, index) => renderImageAssetCompactAsset(asset, index, row.shot_uuid, assets.length)).join("") || `<span class="compact-shot-empty">${escapeHtml(imageAssetText(state, "tray_empty"))}</span>`}</div>
    </article>`;
}

export function hmbRenderImageAssetCompactSummary(state) {
  const rows = hmbImageAssetCompactShotRows(state);
  return `<section class="library-compact-summary" data-library-compact-summary hidden aria-label="HMBImageAssetLibrary Shot summary">${rows.map(
    (row) => renderImageAssetCompactShotRow(state, row),
  ).join("")}${renderImageBashWorkspace(state, true)}</section>`;
}

function hmbPatchImageAssetThumbnailFragment(current, markup) {
  const ownerDocument = current?.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  if (!current || !ownerDocument?.createElement) return false;
  const template = ownerDocument.createElement("template");
  template.innerHTML = String(markup || "").trim();
  const desired = template.content?.firstElementChild;
  return Boolean(desired && hmbPatchImageAssetElement(current, desired));
}

function hmbRebuildImageAssetIndexes(container, state) {
  if (!container || !state) return false;
  const assetsById = new Map();
  const assetsBySourceUid = new Map();
  state.assets.forEach((asset) => {
    const assetId = clean(asset.asset_library_id);
    const sourceUid = clean(asset.source_uid);
    if (assetId) assetsById.set(assetId, asset);
    if (sourceUid) assetsBySourceUid.set(sourceUid, asset);
  });
  const cardById = new Map();
  const selectedById = new Map();
  const compactById = new Map();
  const bashById = new Map();
  container.querySelectorAll?.("[data-asset-key]").forEach((card) => {
    const key = clean(card.getAttribute?.("data-asset-key"));
    if (key) cardById.set(key, card);
  });
  container.querySelectorAll?.("[data-selected-key]").forEach((card) => {
    const key = clean(card.getAttribute?.("data-selected-key"));
    if (key) selectedById.set(key, card);
  });
  container.querySelectorAll?.("[data-compact-asset-key]").forEach((card) => {
    const sourceUid = clean(card.getAttribute?.("data-shot-source-uid"));
    const assetId = clean(assetsBySourceUid.get(sourceUid)?.asset_library_id);
    if (!assetId) return;
    const cards = compactById.get(assetId) || [];
    cards.push(card);
    compactById.set(assetId, cards);
  });
  container.querySelectorAll?.("[data-image-bash-asset-key]").forEach((card) => {
    const assetId = clean(card.getAttribute?.("data-image-bash-asset-key"));
    if (!assetId) return;
    const cards = bashById.get(assetId) || [];
    cards.push(card);
    bashById.set(assetId, cards);
  });
  container.__hmbImageAssetByLibraryId = assetsById;
  container.__hmbImageAssetBySourceUid = assetsBySourceUid;
  container.__hmbImageAssetCardByLibraryId = cardById;
  container.__hmbImageAssetSelectedCardByLibraryId = selectedById;
  container.__hmbImageAssetCompactCardsByLibraryId = compactById;
  container.__hmbImageAssetBashCardsByLibraryId = bashById;
  return true;
}

export function hmbPatchImageAssetThumbnailMedia(container, state, assetLibraryIds) {
  if (!container || !state) return 0;
  const changed = new Set(uniqueStrings(assetLibraryIds));
  if (!changed.size) return 0;
  if (!(container.__hmbImageAssetByLibraryId instanceof Map)) {
    hmbRebuildImageAssetIndexes(container, state);
  }
  const assetsById = container.__hmbImageAssetByLibraryId;
  let patched = 0;
  changed.forEach(assetLibraryId => {
    const asset = assetsById.get(assetLibraryId);
    if (!asset) return;
    const cards = container.__hmbImageAssetBashCardsByLibraryId?.get(assetLibraryId) || [];
    cards.forEach(card => {
      const thumbnail = card.querySelector?.(".selected-thumb");
      if (thumbnail && hmbPatchImageAssetThumbnailFragment(thumbnail, thumbnailHtml(asset, "selected-thumb"))) patched += 1;
    });
  });
  changed.forEach((assetLibraryId) => {
    const asset = assetsById.get(assetLibraryId);
    const card = container.__hmbImageAssetCardByLibraryId?.get(assetLibraryId);
    const thumbnail = card?.querySelector?.(".asset-thumb");
    if (!asset || !thumbnail) return;
    if (hmbPatchImageAssetThumbnailFragment(thumbnail, assetThumbnailHtml(asset, state))) {
      patched += 1;
    }
  });
  changed.forEach((assetLibraryId) => {
    const asset = assetsById.get(assetLibraryId);
    const card = container.__hmbImageAssetSelectedCardByLibraryId?.get(assetLibraryId);
    const thumbnail = card?.querySelector?.(".selected-thumb");
    if (!asset || !thumbnail) return;
    if (hmbPatchImageAssetThumbnailFragment(
      thumbnail,
      thumbnailHtml(asset, "selected-thumb"),
    )) patched += 1;
  });
  changed.forEach((assetLibraryId) => {
    const asset = assetsById.get(assetLibraryId);
    const cards = container.__hmbImageAssetCompactCardsByLibraryId?.get(assetLibraryId) || [];
    if (!asset) return;
    cards.forEach((card) => {
      const index = Math.max(0, Number(card.getAttribute?.("data-compact-order")) - 1 || 0);
      const shotUuid = clean(card.getAttribute?.("data-shot-uuid"));
      if (hmbPatchImageAssetThumbnailFragment(
        card,
        renderImageAssetCompactAsset(asset, index, shotUuid),
      )) patched += 1;
    });
  });
  const draftId = clean(container.__hmbImageAssetRegistrationDraft?.asset_library_id);
  if (draftId && changed.has(draftId)) {
    const asset = assetsById.get(draftId);
    const passport = container.querySelector?.(".passport-photo");
    const source = imageSource(asset || {});
    const failed = !source && hmbImageAssetThumbnailFailed(asset);
    if (
      asset
      && passport
      && hmbPatchImageAssetThumbnailFragment(
        passport,
        `<div class="passport-photo ${source ? "" : failed ? "fallback thumbnail-failed" : "fallback thumbnail-loading"}" data-thumbnail-loading="${source || failed ? "false" : "true"}" data-thumbnail-failed="${failed ? "true" : "false"}">${thumbnailImageMarkup(asset)}</div>`,
      )
    ) patched += 1;
  }
  return patched;
}

function hmbSetImageAssetCompactThumbnailsActive(summary, active) {
  summary?.querySelectorAll?.("img[data-hmb-compact-src]").forEach((image) => {
    const source = image.getAttribute?.("data-hmb-compact-src") || "";
    const current = image.getAttribute?.("src") || "";
    if (active) {
      if (source && source !== current) image.setAttribute?.("src", source);
    } else if (current) {
      image.removeAttribute?.("src");
    }
  });
}

// Native Editor controls remain React-owned. Keep each portal container alive
// across retained markup updates and controller rebuilds; never morph its children.
export function hmbInstallImageAssetNativeHeader(container) {
  if (!container) return null;
  if (container.__hmbImageAssetNativeHeader) return container.__hmbImageAssetNativeHeader;
  const doc = container.ownerDocument || globalThis.document;
  const win = doc?.defaultView || globalThis;
  let active = false, disposed = false, announcedRoot = null;
  const slots = container.__hmbImageAssetNativeHeaderSlots || {};
  container.__hmbImageAssetNativeHeaderSlots = slots;
  const toggle = (element, name, value) => {
    if (element?.classList && element.classList.contains(name) !== value) element.classList.toggle(name, value);
  };
  const announce = phase => {
    if (typeof win.CustomEvent === "function") doc?.dispatchEvent?.(new win.CustomEvent(`hmb-color-lut-header-${phase}`, { detail: { container } }));
  };
  const apply = () => {
    const root = container.querySelector?.(".hmb-image-assets");
    if (!root) return;
    const value = active ? "active" : "fallback";
    if (root.getAttribute?.("data-hmb-native-header") !== value) root.setAttribute?.("data-hmb-native-header", value);
    toggle(container, "nodrag", !active);
    toggle(root, "nodrag", !active);

    for (const body of root.querySelectorAll?.("[data-library-expanded],[data-library-compact-summary]") || []) toggle(body, "nodrag", true);
    for (const control of root.querySelectorAll?.(".top > .project-switch,.top > .header-actions") || []) toggle(control, "nodrag", true);
  };
  const onState = event => {
    if (disposed || event.target !== container) return;
    active = event.detail?.active === true;
    apply();
  };
  container.addEventListener?.("hmb-color-lut-header-state", onState);
  const api = {
    sync() {
      if (disposed) return;
      const root = container.querySelector?.(".hmb-image-assets");
      if (!root) return;
      for (const name of ["identity", "actions"]) {
        const incoming = root.querySelector?.(`[data-hmb-native-${name}]`);
        if (!incoming) return;
        if (slots[name] && slots[name] !== incoming) incoming.replaceWith?.(slots[name]);
        else slots[name] = incoming;
      }
      if (!container.hasAttribute?.("data-hmb-color-lut-widget")) container.setAttribute?.("data-hmb-color-lut-widget", "");
      if (container.getAttribute?.("data-hmb-native-node-type") !== "HMBImageAssetLibrary") container.setAttribute?.("data-hmb-native-node-type", "HMBImageAssetLibrary");
      apply();
      if (announcedRoot !== root) { announcedRoot = root; announce("ready"); }
    },
    cleanup() {
      if (disposed) return;
      announce("retire"); active = false; apply(); disposed = true;
      container.removeEventListener?.("hmb-color-lut-header-state", onState);
      container.removeAttribute?.("data-hmb-color-lut-widget");
      container.removeAttribute?.("data-hmb-native-node-type");
      if (container.__hmbImageAssetNativeHeader === api) delete container.__hmbImageAssetNativeHeader;
      // Retain the slots, including React children, until React unmounts them.
    },
  };
  container.__hmbImageAssetNativeHeader = api;
  return api;
}

function renderImageAssetFixedTop(state) {
  return `<header class="top group" data-library-toggle-surface="header">
      <div class="mark">IA</div>
      <div class="heading"><b>HMB ImageAsset Library</b><span>${escapeHtml(displayWindowsPath(state.catalog_root))} → ${escapeHtml(hmbImageAssetProjectDisplayName(state) || imageAssetText(state, "select_a_project"))}</span></div>
      <div class="hmb-native-identity" data-hmb-native-identity></div><div class="hmb-native-actions nodrag" data-hmb-native-actions></div>
      <div class="project-switch">
        <div class="project-actions">
          <button type="button" class="project-action" data-project-set aria-label="${escapeHtml(imageAssetText(state, "project_set"))}" title="${escapeHtml(imageAssetText(state, "project_set"))}" ${state.scan_busy ? "disabled" : ""}>S</button>
          <button type="button" class="project-action" data-project-reload aria-label="${escapeHtml(imageAssetText(state, "reload_projects"))}" title="${escapeHtml(imageAssetText(state, "reload_projects"))}" ${state.scan_busy ? "disabled" : ""}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 9a7 7 0 0 1 11.8-2L20 9"/><path d="M17.9 15a7 7 0 0 1-11.8 2L4 15"/></svg>
          </button>
        </div>
        <label>${escapeHtml(imageAssetText(state, "project"))}</label>
        <select data-project-select ${state.scan_busy ? "disabled" : ""}>${projectOptions(state)}</select>
        <button type="button" class="language-button" data-language-toggle aria-label="${escapeHtml(imageAssetText(state, "language"))}">${imageAssetLanguage(state) === "ko" ? "한국어" : "EN"}</button>
      </div>
    </header>`;
}

export function hmbPatchCompactImageAssetState(container, state) {
  const root = container?.querySelector?.(".hmb-image-assets");
  const summary = root?.querySelector?.("[data-library-compact-summary]");
  const ownerDocument = summary?.ownerDocument || container?.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  if (!root || !summary || !ownerDocument?.createElement) return false;
  const template = ownerDocument.createElement("template");
  template.innerHTML = hmbRenderImageAssetCompactSummary(state).trim();
  const desired = template.content?.firstElementChild;
  if (!desired) return false;
  const wasHidden = Boolean(summary.hidden);
  hmbPatchImageAssetElement(summary, desired);
  summary.hidden = wasHidden;
  const fixedTop = root.querySelector?.(".top[data-library-toggle-surface='header']");
  template.innerHTML = renderImageAssetFixedTop(state).trim();
  const desiredTop = template.content?.firstElementChild;
  if (fixedTop && desiredTop) hmbPatchImageAssetElement(fixedTop, desiredTop);
  const activeShot = activeImageAssetShot(state);
  const palette = hmbImageAssetShotPalette(activeShot?.number || 1);
  root.setAttribute?.("data-shot-number", String(activeShot?.number || 1));
  root.setAttribute?.("data-busy", state.scan_busy ? "true" : "false");
  if (state.scan_busy) root.setAttribute?.("aria-busy", "true");
  else root.removeAttribute?.("aria-busy");
  root.style?.setProperty?.("--active-shot-accent", palette.accent);
  root.style?.setProperty?.("--active-shot-rgb", palette.rgb);
  hmbInstallImageAssetNativeHeader(container)?.sync();
  hmbSetImageAssetCompactThumbnailsActive(summary, !summary.hidden);
  container.__hmbImageAssetLatestState = state;
  hmbRebuildImageAssetIndexes(container, state);
  container.__hmbImageAssetExpandedDirty = true;
  if (container.__hmbImageAssetExpandedGeometry) {
    hmbSetImageAssetCompactShellGeometry(container, true);
  }
  return true;
}

export function hmbSyncImageAssetCompactEntryState(container, state) {
  if (!state || !hmbPatchCompactImageAssetState(container, state)) return false;
  // The expanded subtree already represents this live canonical state. Entry
  // synchronization refreshes only the hidden summary/top and must not force a
  // rebuild when the same subtree is reopened.
  delete container.__hmbImageAssetExpandedDirty;
  container.__hmbImageAssetLatestState = state;
  return true;
}

function render(
  state,
  registrationDraft = null,
  renderLimit = IMAGE_ASSET_RENDER_WINDOW,
  renderOffset = 0,
  refreshReview = null,
) {
  const catalog = hmbRenderImageAssetGrid(state, renderLimit, renderOffset);
  const activeShot = activeImageAssetShot(state);
  const activePalette = hmbImageAssetShotPalette(activeShot?.number || 1);
  const registrationResult = state.asset_registration_result;
  const statusText = state.scan_busy
    ? imageAssetText(state, "busy_loading")
    : state.error
    ? state.error
    : registrationResult?.ok && registrationResult.message
      ? registrationResult.message
      : hmbImageAssetStatusSummary(state);
  const filterLabel = state.selected_source_view === "user"
    ? imageAssetText(state, "import_in")
    : state.selected_folder_path || imageAssetText(state, "project_root");
  const detailView = state.asset_view_mode === "detail";
  const viewToggleLabel = imageAssetText(state, detailView ? "image_only_view" : "details_view");
  return `
    <style>
      .hmb-image-assets :is(button,input,select,textarea):not([data-hmb-native-identity] *,[data-hmb-native-actions] *){font-family:inherit}
      .hmb-image-assets .compact-shot-asset[draggable="true"]{cursor:grab;user-select:none}
      .hmb-image-assets .compact-shot-asset.dragging{cursor:grabbing;opacity:.6}
      .hmb-image-assets .compact-shot-asset.drop-target{border-color:var(--shot-accent);box-shadow:inset 0 0 0 1px var(--shot-accent)}
      .hmb-image-assets{--bg:#090c16;--panel:#101523;--line:rgba(148,163,184,.19);--accent:#22d3ee;--pink:#f472b6;--asset-selection:#f472b6;--text:#e6edf7;--muted:#8fa3b8;--selection-rgb:244,114,182;--selection-deep-rgb:190,24,93;--selection-secondary-rgb:217,70,239;--selection-text:#f8c6df;--selection-soft:#f3a8ce;--selection-strong:#ffe4f2;--selection-panel:rgba(30,14,30,.9);--selection-card:rgba(61,23,49,.6);--header-tint:rgba(72,35,101,.44);container-type:inline-size;position:relative;width:100%;height:100%;min-height:680px;display:grid;grid-template-rows:58px minmax(0,1fr);overflow:hidden;border:1px solid var(--line);border-radius:11px;background:radial-gradient(circle at 8% -10%,rgba(168,85,247,.16),transparent 34%),linear-gradient(180deg,#0b1020,#060912);color:var(--text);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;font-synthesis:none;-webkit-font-smoothing:antialiased;box-sizing:border-box}
      .hmb-image-assets *{box-sizing:border-box;min-width:0}.top{display:flex;align-items:center;gap:12px;padding:8px 13px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,rgba(72,35,101,.44),rgba(14,23,38,.9) 44%)}.mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border:1px solid rgba(34,211,238,.7);border-radius:8px;background:rgba(8,145,178,.12);color:var(--accent);font-size:11px;font-weight:950}.heading{display:flex;flex:0 1 auto;flex-direction:column;gap:2px;overflow:hidden}.heading b{overflow:hidden;font-size:15px;letter-spacing:.01em;white-space:nowrap;text-overflow:ellipsis}.heading span{max-width:360px;color:var(--muted);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.project-switch{margin-left:auto;display:grid;grid-template-columns:auto auto minmax(150px,260px);align-items:center;gap:7px;min-width:0}.project-actions{display:flex;align-items:center;gap:5px}.project-action{width:31px;height:31px;display:grid;place-items:center;padding:0;border:1px solid rgba(96,165,250,.5);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.3),rgba(15,23,42,.9));color:#93c5fd;font-size:12px;font-weight:950;cursor:pointer}.project-action:hover{border-color:var(--accent);color:#fff;box-shadow:0 0 10px rgba(34,211,238,.2)}.project-action svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.project-switch label{min-width:max-content;color:#aebed0;font-size:8px;font-weight:900;letter-spacing:.08em;white-space:nowrap;word-break:keep-all}.project-switch select{width:100%;height:31px;border:1px solid rgba(148,163,184,.28);border-radius:7px;background:#080d17;color:#edf5ff;padding:0 8px;font-size:10px;outline:none}.project-switch select:focus{border-color:var(--accent)}.status{display:flex;flex:0 1 auto;flex-direction:column;align-items:flex-end;gap:2px;font-size:8px;color:var(--muted)}.status strong{max-width:260px;color:${state.error ? "#fda4af" : "#86efac"};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .workspace{display:grid;grid-template-columns:minmax(230px,252px) minmax(0,1fr);gap:8px;min-height:0;padding:8px}.panel{min-height:0;border:1px solid var(--line);border-radius:9px;background:rgba(8,13,23,.76);overflow:hidden}.tree-panel{display:flex;flex-direction:column}.panel-title{height:35px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 10px;border-bottom:1px solid var(--line);background:rgba(19,27,42,.78);color:#bed0e3;font-size:9px;font-weight:900;letter-spacing:.07em}.panel-title>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;word-break:keep-all}.panel-title b{flex:0 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--accent);font-size:8px}.tree{padding:6px;overflow:auto;scrollbar-gutter:stable}.tree-row{width:100%;min-height:30px;display:grid;grid-template-columns:13px minmax(0,1fr) auto;align-items:center;gap:5px;margin:0 0 3px;padding:5px 8px 5px calc(8px + var(--tree-depth,0) * 14px);border:1px solid transparent;border-radius:6px;background:transparent;color:#96a9bd;font-size:8px;text-align:left;cursor:pointer;transition:border-color 120ms ease,background-color 120ms ease,color 120ms ease}.tree-row i{color:#61778c;font-style:normal}.tree-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tree-row b{color:#587087}.tree-row:hover{border-color:rgba(34,211,238,.3);color:#def9ff}.tree-row.active{border-color:rgba(34,211,238,.52);background:linear-gradient(90deg,rgba(8,145,178,.2),rgba(8,145,178,.04));color:#e7fcff}.tree-row.root{min-height:35px;color:#fff;font-size:10px;font-weight:850}
      .assets-panel{display:flex;flex-direction:column}.toolbar{height:44px;display:flex;align-items:center;gap:8px;padding:7px 9px;border-bottom:1px solid var(--line)}.toolbar input{flex:1;height:30px;border:1px solid rgba(148,163,184,.25);border-radius:7px;background:#070c15;color:#edf5ff;padding:0 9px;font-size:9px;outline:none}.toolbar input:focus{border-color:var(--accent)}.filter-chip{max-width:260px;padding:5px 8px;border:1px solid rgba(244,114,182,.3);border-radius:99px;background:rgba(131,24,67,.1);color:#f8c6df;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-scroll{flex:1;min-height:0;overflow:auto;scrollbar-gutter:stable;padding:9px}.asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}.asset-card{display:grid;grid-template-columns:112px minmax(0,1fr);gap:10px;min-height:152px;padding:9px;border:1px solid rgba(148,163,184,.16);border-radius:9px;background:linear-gradient(145deg,rgba(19,27,42,.86),rgba(9,14,24,.82));cursor:pointer;outline:none;content-visibility:auto;contain-intrinsic-size:167px;transition:border-color 120ms ease,box-shadow 120ms ease,background-color 120ms ease,opacity 120ms ease}.asset-card:hover{border-color:rgba(34,211,238,.34)}.asset-card:focus-visible{box-shadow:0 0 0 2px rgba(34,211,238,.45)}.asset-card.selected{border-color:var(--asset-selection);box-shadow:inset 0 0 0 .3px rgba(244,114,182,.45),0 0 15px rgba(244,114,182,.34),0 0 4px rgba(217,70,239,.55)}.asset-card.selection-blocked{opacity:.58}.asset-card.unregistered{cursor:default}.asset-card.unregistered .asset-state{color:#f3a8ce}.asset-thumb{position:relative;width:112px;height:132px;display:grid;grid-template-rows:2fr 1fr;overflow:hidden;border:1px solid rgba(148,163,184,.2);border-radius:7px;background:#050910;color:#648198;font-size:9px;font-weight:900}.asset-thumb-media{position:relative;display:grid;place-items:center;min-height:0;overflow:hidden;border-bottom:1px solid rgba(148,163,184,.18)}.asset-thumb-media img{width:100%;height:100%;object-fit:cover}.asset-thumb-media>span{display:none}.asset-thumb.fallback .asset-thumb-media img{display:none}.asset-thumb.fallback .asset-thumb-media>span{display:block}.asset-thumb-footer{display:flex;align-items:center;justify-content:center;gap:6px;min-height:0;padding:4px 6px;background:linear-gradient(180deg,#080d16,#050810)}.asset-source-name{min-width:0;flex:1;color:#a8bdd0;font-size:8px;font-weight:800;line-height:1.25;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-extension-badge{flex:0 0 auto;max-width:48px;padding:3px 5px;border:1px solid rgba(34,211,238,.4);border-radius:5px;background:rgba(8,145,178,.1);color:var(--accent);font-family:inherit;font-size:7px;font-weight:900;line-height:1;letter-spacing:.07em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-thumb-media .asset-add{position:absolute;right:5px;bottom:5px;z-index:2}.asset-add{min-width:56px;height:25px;padding:0 13px;border:1px solid rgba(244,114,182,.7);border-radius:99px;background:rgba(131,24,67,.26);color:#ffd5eb;font-size:9px;font-weight:950;letter-spacing:.04em;cursor:pointer;box-shadow:0 0 10px rgba(244,114,182,.16)}.asset-add:hover{border-color:#f9a8d4;background:rgba(190,24,93,.32);box-shadow:0 0 13px rgba(244,114,182,.3)}.asset-content{display:flex;flex-direction:column;gap:8px}.asset-title{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.asset-title-copy{display:flex;flex:1;flex-direction:column;gap:2px;min-width:0}.asset-state{color:var(--accent);font-size:7px;font-weight:900}.asset-id-line{display:flex;align-items:center;gap:5px;min-width:0;color:#9bacc0;font-size:7px;font-weight:500}.asset-id-line em{flex:0 0 auto;color:#6e859c;font-size:6px;font-style:normal;font-weight:900;letter-spacing:.05em}.asset-id-line span{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-meta{display:flex;flex-direction:column;gap:3px;color:#71879c;font-size:7px}.asset-meta b,.asset-meta span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-meta b{color:#bcd0e2}.empty{grid-column:1/-1;padding:30px;border:1px dashed rgba(148,163,184,.2);border-radius:8px;color:#667e94;font-size:9px;text-align:center}.warnings{max-height:64px;overflow:auto;padding:6px 9px;border-top:1px solid rgba(251,191,36,.2);background:rgba(120,53,15,.1);color:#fcd34d;font-size:7px}
      .asset-window-nav{grid-column:1/-1;display:flex;justify-content:center;gap:8px}.asset-window-more{min-width:160px;min-height:34px;border:1px solid rgba(34,211,238,.3);border-radius:8px;background:rgba(8,145,178,.1);color:#a5f3fc;font-size:9px;font-weight:850;cursor:pointer}.asset-window-more:hover,.asset-window-more:focus-visible{border-color:var(--accent);outline:none;background:rgba(8,145,178,.18)}
      @keyframes hmb-image-leaf-pulse{0%,12.5%{opacity:1;filter:brightness(1.65);box-shadow:0 0 7px rgba(226,232,240,.42)}37.5%,100%{opacity:.2;filter:brightness(.62);box-shadow:none}}.thumbnail-loading .thumbnail-placeholder,.thumbnail-loading .asset-thumb-placeholder,.thumbnail-loading .compact-shot-placeholder{display:grid!important;width:100%;height:100%;place-items:center;background:rgba(5,9,16,.82)}.thumbnail-loading .thumbnail-placeholder{min-width:100%;min-height:100%}.hmb-image-leaf-loader{position:relative;display:block!important;pointer-events:none;width:38px!important;height:38px!important;min-width:38px!important;min-height:38px!important;background:transparent!important}.hmb-image-leaf-loader>i{--leaf-angle:calc(var(--leaf-index) * 45deg);position:absolute;left:50%;top:50%;width:6px;height:12px;margin:-6px 0 0 -3px;border-radius:90% 12% 90% 12%;background:linear-gradient(135deg,#fff 4%,#cbd5e1 48%,#64748b 100%);transform:rotate(var(--leaf-angle)) translateY(-13px) rotate(45deg);transform-origin:50% 50%;opacity:.2;animation:hmb-image-leaf-pulse 1s linear infinite;animation-delay:calc(var(--leaf-index) * .125s)}@media (prefers-reduced-motion:reduce){.hmb-image-leaf-loader>i{animation:none;opacity:.45;filter:none;box-shadow:none}.hmb-image-leaf-loader>i:first-child{opacity:.9}}
      .hmb-image-leaf-loader,.hmb-image-leaf-loader *{pointer-events:none}
      .thumbnail-failed .thumbnail-placeholder,.thumbnail-failed .asset-thumb-placeholder,.thumbnail-failed .compact-shot-placeholder{display:grid!important;width:100%;height:100%;place-items:center;background:rgba(5,9,16,.82)}.thumbnail-failed .thumbnail-placeholder{min-width:100%;min-height:100%}.hmb-image-thumbnail-unavailable{display:grid!important;place-items:center;width:30px!important;height:30px!important;border:1px solid rgba(248,113,113,.42);border-radius:50%;background:rgba(69,10,10,.36)!important;color:#fca5a5;font-size:15px;font-weight:950;line-height:1}.thumbnail-failed{animation:none!important}
      .shot-panel .shot-rename{width:29px;height:29px;flex:0 0 29px;padding:0;border:1px solid rgba(var(--shot-rgb),.42);border-radius:7px;background:rgba(var(--shot-rgb),.10);color:var(--shot-accent);font-size:13px;cursor:pointer}.shot-panel .shot-rename:disabled{opacity:.28;cursor:default}.shot-panel .shot-rename:hover:not(:disabled),.shot-panel .shot-rename:focus-visible{border-color:var(--shot-accent);background:rgba(var(--shot-rgb),.22);outline:none}.shot-name-input{width:min(180px,100%);height:24px;border:1px solid var(--shot-accent);border-radius:5px;background:#060b13;color:#f8fafc;padding:0 6px;font:inherit;outline:none;box-shadow:0 0 0 2px rgba(var(--shot-rgb),.2)}
      .toolbar-status{flex:0 0 190px;width:190px;min-width:190px;height:30px;display:flex;align-items:center;justify-content:flex-end;overflow:hidden;color:var(--muted);font-size:8px}.toolbar-status strong{display:block;width:100%;color:${state.error ? "#fda4af" : "#86efac"};font-variant-numeric:tabular-nums;letter-spacing:-.02em;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.toolbar .filter-chip{flex:0 0 120px;width:120px;max-width:120px;text-align:center}
      .asset-view-toggle{flex:0 0 31px;width:31px;height:30px;display:grid;place-items:center;padding:0;border:1px solid rgba(96,165,250,.46);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.2),rgba(15,23,42,.88));color:#7dd3fc;cursor:pointer}.asset-view-toggle:hover,.asset-view-toggle:focus-visible,.asset-view-toggle[aria-pressed="true"]{border-color:var(--accent);background:linear-gradient(180deg,rgba(37,99,235,.38),rgba(15,23,42,.94));color:#e0f2fe;outline:none;box-shadow:0 0 10px rgba(34,211,238,.2)}.asset-view-toggle svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
      .hmb-image-assets .asset-card{min-height:167px;padding:10px}.hmb-image-assets .asset-thumb{width:123px;height:145px}.hmb-image-assets .asset-add{min-width:52px;height:28px;padding:0 10px;font-size:10px}.hmb-image-assets .asset-source-name{font-size:9px}.hmb-image-assets[data-asset-view="image"] .asset-grid{grid-template-columns:repeat(auto-fill,145px);align-content:start;justify-content:start;gap:9px}.hmb-image-assets[data-asset-view="image"] .asset-card{width:145px;grid-template-columns:123px;gap:0}.hmb-image-assets[data-asset-view="image"] .asset-content,.hmb-image-assets[data-asset-view="image"] .asset-extension-badge{display:none}.hmb-image-assets[data-asset-view="detail"] .asset-grid{grid-template-columns:repeat(auto-fill,286px);align-content:start;justify-content:start;gap:9px}.hmb-image-assets[data-asset-view="detail"] .asset-card{width:286px;grid-template-columns:123px minmax(0,1fr);gap:11px}.hmb-image-assets[data-asset-view="detail"] .asset-content{display:flex}
      .tray{margin:0 8px 8px;border:1px solid rgba(244,114,182,.34);border-radius:10px;background:linear-gradient(180deg,rgba(30,14,30,.9),rgba(8,11,19,.96));overflow:hidden}.tray-head{height:34px;display:flex;align-items:center;gap:9px;padding:0 10px;border-bottom:1px solid rgba(244,114,182,.2)}.tray-head b{font-size:9px;letter-spacing:.07em;color:#f9c2df}.tray-head span{color:#8ea3b8;font-size:7px}.tray-head em{margin-left:auto;color:var(--asset-selection);font-size:7px;font-style:normal}.tray-scroll{height:132px;display:flex;align-items:stretch;gap:8px;overflow-x:auto;overflow-y:hidden;padding:7px}.selected-card{position:relative;flex:0 0 244.5px;display:grid;grid-template-rows:25px minmax(0,1fr);padding:6px;border:1px solid rgba(244,114,182,.25);border-radius:8px;background:linear-gradient(145deg,rgba(61,23,49,.6),rgba(12,17,28,.94));cursor:grab}.selected-card:active{cursor:grabbing}.selected-card.dragging{opacity:.35}.selected-card.drop-target{border-color:var(--accent);box-shadow:0 0 0 1px rgba(34,211,238,.28)}.selected-card.missing{border-color:rgba(248,113,113,.5)}.selected-card-top{display:flex;align-items:center;gap:7px}.slot{min-width:30px;height:21px;display:grid;place-items:center;border:1px solid rgba(96,165,250,.68);border-radius:5px;background:rgba(37,99,235,.24);color:#93c5fd;font-size:10px;font-weight:950}.selected-actions{display:flex;gap:3px;margin-left:auto}.selected-actions button{width:23px;height:21px;border:1px solid rgba(148,163,184,.2);border-radius:5px;background:#0a101b;color:#b9cad9;cursor:pointer}.selected-actions button:hover{border-color:var(--accent);color:#fff}.selected-card-body{display:grid;grid-template-columns:102px minmax(0,1fr);align-items:center;gap:9px}.selected-thumb{position:relative;width:102px;height:82px;display:grid;place-items:center;overflow:hidden;border:1px solid rgba(244,114,182,.25);border-radius:6px;background:#060912;color:#725a70;font-size:7px;font-weight:900}.selected-thumb img{width:100%;height:100%;object-fit:cover}.selected-thumb span{display:none}.selected-thumb.fallback span{display:block}.selected-copy{display:flex;flex-direction:column;gap:4px}.selected-copy b,.selected-copy span,.selected-copy small{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.selected-copy b{font-size:10px}.selected-copy span{color:#a7b7c8;font-size:8px}.selected-copy em{color:#f3a8ce;font-size:7px;font-style:normal;font-weight:900}.selected-copy small{color:#667e94;font-size:7px}.tray-empty{min-width:100%;display:grid;place-items:center;border:1px dashed rgba(244,114,182,.18);border-radius:7px;color:#765d70;font-size:9px}
      .selected-card{flex-basis:120px;width:120px;height:118px;grid-template-rows:23px minmax(0,1fr)}.selected-card-top{gap:4px}.slot{flex:0 0 28px;width:28px;min-width:28px;height:21px;font-size:9px;font-variant-numeric:tabular-nums}.selected-actions{display:flex;gap:2px;margin-left:auto}.selected-actions button{width:22px;height:21px;padding:0;display:grid;place-items:center}.selected-card-body{display:grid;grid-template-columns:1fr;place-items:center;gap:0;min-height:0}.selected-thumb{width:106px;height:81px}.selected-copy{display:none}
      .shot-routing{margin:0 8px 8px;border:1px solid rgba(34,211,238,.3);border-radius:9px;background:linear-gradient(180deg,rgba(7,28,40,.94),rgba(6,10,18,.98));overflow:hidden}.shot-routing-head{height:38px;display:flex;align-items:center;gap:7px;padding:0 8px}.shot-toggle,.shot-add,.shot-tab,.shot-source button{border:1px solid rgba(34,211,238,.24);border-radius:6px;background:#08131e;color:#a9c6d8;cursor:pointer}.shot-toggle{width:25px;height:25px;padding:0;color:var(--accent)}.shot-routing-head>b{font-size:8px;letter-spacing:.08em;color:var(--accent);white-space:nowrap}.shot-channel{max-width:58px;color:#5f7f94;font-size:7px;font-family:ui-monospace,monospace}.shot-tabs{display:flex;flex:1;align-items:center;gap:5px;min-width:0;overflow-x:auto;padding:2px}.shot-tab{height:27px;display:flex;align-items:center;gap:5px;padding:0 7px;white-space:nowrap}.shot-tab small{color:#5e7e93;font-size:6px}.shot-tab b{max-width:92px;overflow:hidden;text-overflow:ellipsis;font-size:8px}.shot-tab em{color:#6f90a5;font-size:7px;font-style:normal}.shot-tab.active{border-color:var(--accent);background:rgba(8,145,178,.18);color:#e6fbff}.shot-add{height:27px;padding:0 9px;color:#bceef5;font-size:8px;font-weight:900;white-space:nowrap}.shot-add:disabled,.shot-source button:disabled{opacity:.28;cursor:default}.shot-routing-body{min-height:78px;display:grid;grid-template-columns:190px minmax(0,1fr);gap:8px;padding:7px 9px 9px;border-top:1px solid rgba(34,211,238,.14)}.shot-routing-summary{display:flex;flex-direction:column;gap:3px;padding:7px;border:1px solid rgba(34,211,238,.16);border-radius:7px;background:rgba(4,14,24,.65)}.shot-routing-summary b{color:#d9f8ff;font-size:10px}.shot-routing-summary span{color:var(--accent);font-size:8px;font-weight:900}.shot-routing-summary small{color:#708ba0;font-size:7px;line-height:1.35}.shot-sources{display:flex;align-content:flex-start;gap:5px;overflow-x:auto;padding:3px}.shot-source{height:30px;display:flex;flex:0 0 auto;align-items:stretch}.shot-source>button:first-child{max-width:145px;display:flex;align-items:center;gap:5px;padding:0 7px}.shot-source i{color:#5d7d91;font-size:8px;font-style:normal}.shot-source span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:8px}.shot-source.selected>button:first-child{border-color:rgba(244,114,182,.62);background:rgba(131,24,67,.22);color:#ffe0f1}.shot-source.selected i{color:#f9a8d4}.shot-source .shot-source-move{width:22px;margin-left:2px;padding:0;color:#8eb6ca}.shot-routing-empty{align-self:center;color:#607b90;font-size:8px}
      .shot-stack{max-height:360px;margin:0 8px 8px;display:flex;flex-direction:column;gap:5px;overflow:auto;scrollbar-gutter:stable}.shot-panel{flex:0 0 auto;overflow:hidden;border:1px solid rgba(var(--shot-rgb),.34);border-radius:10px;background:linear-gradient(180deg,rgba(var(--shot-rgb),.10),rgba(8,11,19,.96));box-shadow:0 0 16px rgba(var(--shot-rgb),.07)}.shot-panel-head{height:38px;display:flex;align-items:center;gap:6px;padding:4px 7px;min-width:0;border-bottom:1px solid transparent}.shot-panel.active .shot-panel-head{border-bottom-color:rgba(var(--shot-rgb),.20)}.shot-panel-toggle{height:29px;min-width:0;flex:1;display:grid;grid-template-columns:30px minmax(0,1fr) minmax(0,1fr) auto auto;align-items:center;gap:7px;padding:0 8px;border:1px solid rgba(var(--shot-rgb),.32);border-radius:7px;background:linear-gradient(90deg,rgba(var(--shot-rgb),.16),rgba(8,13,23,.72));color:#d9e6f3;text-align:left;cursor:pointer}.shot-panel-toggle small{color:var(--shot-accent);font-size:8px;font-weight:950}.shot-panel-toggle b{max-width:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#f8fafc;font-size:10px}.shot-panel-toggle span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:rgba(var(--shot-rgb),.92);font-size:8px;font-weight:900;letter-spacing:.06em}.shot-panel-toggle em{color:var(--shot-accent);font-size:8px;font-style:normal;font-weight:900}.shot-panel-toggle i{color:#7f95a8;font-size:7px;font-style:normal;letter-spacing:.08em}.shot-panel.active{border-color:rgba(var(--shot-rgb),.68);box-shadow:0 0 18px rgba(var(--shot-rgb),.14)}.shot-panel.active .shot-panel-toggle{border-color:var(--shot-accent);box-shadow:0 0 10px rgba(var(--shot-rgb),.14)}.shot-panel .shot-delete{width:29px;height:29px;flex:0 0 29px;padding:0;border:1px solid rgba(var(--shot-rgb),.42);border-radius:7px;background:rgba(var(--shot-rgb),.10);color:var(--shot-accent);font-size:16px;line-height:1;cursor:pointer}.shot-panel .shot-delete:hover:not(:disabled),.shot-panel .shot-delete:focus-visible{border-color:var(--shot-accent);background:rgba(var(--shot-rgb),.22);outline:none;box-shadow:0 0 10px rgba(var(--shot-rgb),.18)}.shot-panel .shot-delete:disabled{opacity:.25;cursor:default}.shot-panel .shot-add{flex:0 0 auto;height:29px;padding:0 11px;border:1px solid rgba(var(--shot-rgb),.54);border-radius:7px;background:rgba(var(--shot-rgb),.14);color:var(--shot-accent);font-size:8px;font-weight:950;white-space:nowrap;cursor:pointer}.shot-panel .shot-add:disabled{opacity:.3;cursor:default}.shot-panel .tray-scroll{height:132px;display:flex;align-items:stretch;gap:8px;overflow-x:auto;overflow-y:hidden;padding:7px}.shot-panel .selected-card{border-color:rgba(var(--shot-rgb),.30);background:linear-gradient(145deg,rgba(var(--shot-rgb),.15),rgba(12,17,28,.94))}.shot-panel .selected-thumb{border-color:rgba(var(--shot-rgb),.30)}.shot-panel .slot{border-color:rgba(var(--shot-rgb),.70);background:rgba(var(--shot-rgb),.20);color:var(--shot-accent)}.shot-panel .tray-empty{border-color:rgba(var(--shot-rgb),.22);color:rgba(var(--shot-rgb),.72)}.hmb-image-assets .asset-card.selected{border-color:var(--active-shot-accent);box-shadow:inset 0 0 0 .3px rgba(var(--active-shot-rgb),.48),0 0 15px rgba(var(--active-shot-rgb),.34),0 0 4px rgba(var(--active-shot-rgb),.55)}
      .asset-registration-backdrop{position:absolute;inset:0;z-index:80;display:grid;place-items:center;padding:18px;background:rgba(1,4,10,.78);backdrop-filter:blur(5px)}.asset-passport{width:min(390px,100%);max-height:calc(100% - 12px);display:flex;flex-direction:column;overflow:auto;border:1px solid rgba(244,114,182,.62);border-radius:18px 18px 28px 28px;background:radial-gradient(circle at 50% -8%,rgba(190,24,93,.24),transparent 30%),linear-gradient(180deg,#171020,#090d17 45%,#060912);box-shadow:0 24px 70px rgba(0,0,0,.62),0 0 28px rgba(244,114,182,.2)}.passport-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 10px;border-bottom:1px solid rgba(244,114,182,.2)}.passport-head small{display:block;color:#d8a2be;font-size:7px;font-weight:900;letter-spacing:.18em}.passport-head h2{margin:3px 0 0;color:#fff1f8;font-size:15px;letter-spacing:.08em}.passport-head button{width:28px;height:28px;border:1px solid rgba(244,114,182,.25);border-radius:50%;background:#0b0d16;color:#e7b9d1;font-size:18px;line-height:1;cursor:pointer}.passport-photo{position:relative;width:128px;aspect-ratio:3/4;display:grid;place-items:center;align-self:center;margin:14px 0 8px;overflow:hidden;border:1px solid rgba(244,114,182,.38);border-radius:8px;background:#050910;color:#84677a;font-size:10px;font-weight:900;box-shadow:0 0 18px rgba(244,114,182,.12)}.passport-photo img{width:100%;height:100%;object-fit:cover}.passport-photo>span{display:none}.passport-photo.fallback img{display:none}.passport-photo.fallback>span{display:block}.passport-file{display:flex;flex-direction:column;gap:3px;padding:0 18px 12px;text-align:center}.passport-file b,.passport-file span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.passport-file b{color:#d7e2ef;font-size:8px}.passport-file span{color:#73899d;font-size:7px}.passport-fields{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:12px 16px;border-top:1px dashed rgba(244,114,182,.24)}.passport-fields label{display:flex;flex-direction:column;gap:4px}.passport-fields label:nth-last-child(1){grid-column:1/-1}.passport-fields label span{color:#bb8fa8;font-size:7px;font-weight:900;letter-spacing:.06em}.passport-fields input,.passport-fields select{width:100%;height:32px;border:1px solid rgba(148,163,184,.27);border-radius:7px;background:#060b13;color:#eef5ff;padding:0 8px;font-size:9px;outline:none}.passport-fields input:focus,.passport-fields select:focus{border-color:var(--asset-selection);box-shadow:0 0 0 1px rgba(244,114,182,.18)}.passport-fields select:disabled{opacity:.42}.passport-actions{display:flex;justify-content:flex-end;gap:7px;padding:11px 16px 15px}.passport-actions button{height:31px;padding:0 13px;border:1px solid rgba(148,163,184,.24);border-radius:7px;background:#0a101a;color:#bac9d8;font-size:8px;font-weight:900;cursor:pointer}.passport-actions .passport-register{border-color:rgba(244,114,182,.62);background:linear-gradient(180deg,rgba(190,24,93,.55),rgba(88,28,135,.42));color:#ffe4f2;box-shadow:0 0 12px rgba(244,114,182,.18)}.passport-actions button:disabled{opacity:.32;cursor:default;box-shadow:none}
      .passport-fields .passport-folder{grid-column:1/-1}.passport-taxonomy-contract{grid-column:1/-1;display:flex;flex-direction:column;gap:4px;padding:8px 9px;border:1px solid rgba(148,163,184,.18);border-radius:7px;background:rgba(2,6,14,.58)}.passport-taxonomy-contract[hidden]{display:none}.passport-taxonomy-contract small{color:#bb8fa8;font-size:7px;font-weight:900;letter-spacing:.06em}.passport-taxonomy-contract span{color:#cbd8e6;font-size:8px;line-height:1.45}
      .asset-refresh-review{width:min(580px,100%)}.refresh-review-body{padding:4px 16px 12px;font-size:10px;line-height:1.6;color:#cbd8e6}.refresh-review-body h3{margin:14px 0 4px;font-size:11px;color:var(--selection-text)}.refresh-review-body p{margin:7px 0}.refresh-review-body ul{max-height:120px;overflow:auto;margin:8px 0;padding:9px 9px 9px 26px;border:1px solid rgba(148,163,184,.2);border-radius:7px;background:#060b13}.refresh-review-body li,.refresh-review-root,.refresh-review-path{overflow-wrap:anywhere;white-space:pre-wrap}.refresh-review-error{color:#fca5a5}.refresh-review-confirm{padding:10px;border:1px solid var(--selection-soft);border-radius:7px;color:var(--selection-strong);background:rgba(var(--selection-rgb),.12)}
      /* Fixed P-base visual language. Shot 1-5 are the only accent authority. */
      .hmb-image-assets[data-theme] .top{background:linear-gradient(90deg,var(--header-tint),rgba(14,23,38,.92) 44%,rgba(6,9,18,.96))}.hmb-image-assets[data-theme] .mark{border-color:rgba(var(--selection-rgb),.54);background:linear-gradient(145deg,rgba(var(--selection-rgb),.16),rgba(8,13,23,.86));color:var(--accent);box-shadow:inset 0 0 0 1px rgba(255,255,255,.025),0 0 14px rgba(var(--selection-rgb),.11)}
      .hmb-image-assets[data-theme] .filter-chip{border-color:rgba(var(--selection-rgb),.3);background:rgba(var(--selection-deep-rgb),.1);color:var(--selection-text)}.hmb-image-assets[data-theme] .asset-card.selected{box-shadow:inset 0 0 0 .3px rgba(var(--selection-rgb),.45),0 0 15px rgba(var(--selection-rgb),.34),0 0 4px rgba(var(--selection-secondary-rgb),.55)}.hmb-image-assets[data-theme] .asset-card.unregistered .asset-state{color:var(--selection-soft)}.hmb-image-assets[data-theme] .asset-add{border-color:rgba(var(--selection-rgb),.7);background:rgba(var(--selection-deep-rgb),.26);color:var(--selection-strong);box-shadow:0 0 10px rgba(var(--selection-rgb),.16)}.hmb-image-assets[data-theme] .asset-add:hover{border-color:var(--selection-soft);background:rgba(var(--selection-deep-rgb),.34);box-shadow:0 0 13px rgba(var(--selection-rgb),.3)}
      .hmb-image-assets[data-theme] .tray{border-color:rgba(var(--selection-rgb),.34);background:linear-gradient(180deg,var(--selection-panel),rgba(8,11,19,.96))}.hmb-image-assets[data-theme] .tray-head{border-bottom-color:rgba(var(--selection-rgb),.2)}.hmb-image-assets[data-theme] .tray-head b{color:var(--selection-text)}.hmb-image-assets[data-theme] .selected-card{border-color:rgba(var(--selection-rgb),.25);background:linear-gradient(145deg,var(--selection-card),rgba(12,17,28,.94))}.hmb-image-assets[data-theme] .selected-thumb{border-color:rgba(var(--selection-rgb),.25)}.hmb-image-assets[data-theme] .selected-copy em{color:var(--selection-soft)}.hmb-image-assets[data-theme] .tray-empty{border-color:rgba(var(--selection-rgb),.18);color:rgba(var(--selection-rgb),.48)}
      .hmb-image-assets[data-theme] .asset-passport{border-color:rgba(var(--selection-rgb),.62);background:radial-gradient(circle at 50% -8%,rgba(var(--selection-deep-rgb),.24),transparent 30%),linear-gradient(180deg,#111827,#090d17 45%,#060912);box-shadow:0 24px 70px rgba(0,0,0,.62),0 0 28px rgba(var(--selection-rgb),.2)}.hmb-image-assets[data-theme] .passport-head{border-bottom-color:rgba(var(--selection-rgb),.2)}.hmb-image-assets[data-theme] .passport-head small,.hmb-image-assets[data-theme] .passport-fields label span{color:var(--selection-soft)}.hmb-image-assets[data-theme] .passport-head h2{color:var(--selection-strong)}.hmb-image-assets[data-theme] .passport-head button{border-color:rgba(var(--selection-rgb),.25);color:var(--selection-text)}.hmb-image-assets[data-theme] .passport-photo{border-color:rgba(var(--selection-rgb),.38);box-shadow:0 0 18px rgba(var(--selection-rgb),.12)}.hmb-image-assets[data-theme] .passport-fields{border-top-color:rgba(var(--selection-rgb),.24)}.hmb-image-assets[data-theme] .passport-fields input:focus,.hmb-image-assets[data-theme] .passport-fields select:focus{box-shadow:0 0 0 1px rgba(var(--selection-rgb),.18)}.hmb-image-assets[data-theme] .passport-actions .passport-register{border-color:rgba(var(--selection-rgb),.62);background:linear-gradient(180deg,rgba(var(--selection-deep-rgb),.55),rgba(var(--selection-secondary-rgb),.42));color:var(--selection-strong);box-shadow:0 0 12px rgba(var(--selection-rgb),.18)}
      .hmb-image-assets[data-theme] .asset-card.selected{border-color:var(--active-shot-accent);box-shadow:inset 0 0 0 .3px rgba(var(--active-shot-rgb),.48),0 0 15px rgba(var(--active-shot-rgb),.34),0 0 4px rgba(var(--active-shot-rgb),.55)}
      .project-switch{grid-template-columns:auto auto minmax(150px,260px) auto}.language-button{min-width:58px;height:31px;padding:0 11px;border:1px solid rgba(96,165,250,.5);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.3),rgba(15,23,42,.9));color:#93c5fd;font-size:10px;font-weight:950;cursor:pointer}.language-button:hover,.language-button:focus-visible{border-color:var(--accent);color:#fff;outline:none;box-shadow:0 0 10px rgba(34,211,238,.2)}
      @container(max-width:1100px){.status{display:none}.heading{flex-basis:170px}.heading span{display:none}.project-switch{grid-template-columns:auto auto minmax(120px,210px) auto}}
      @container(max-width:720px){.heading{display:none}.project-switch{grid-template-columns:auto minmax(120px,1fr) auto}.project-switch label{display:none}}
      @container(max-width:920px){.workspace{grid-template-columns:1fr;grid-template-rows:minmax(150px,30%) minmax(0,1fr)}.tree-panel{display:flex}.project-switch{grid-template-columns:auto minmax(130px,1fr) auto}.project-switch label{position:absolute;inline-size:1px;block-size:1px;overflow:hidden;clip-path:inset(50%)}.status{display:flex}}
      .hmb-image-assets[data-busy="true"] .project-switch{opacity:.72}.hmb-image-assets[data-busy="true"] .project-action svg{animation:hmb-image-spin .8s linear infinite}@keyframes hmb-image-spin{to{transform:rotate(360deg)}}
      .transport-status{position:absolute;z-index:70;top:48px;left:50%;max-width:min(520px,80%);transform:translateX(-50%);padding:7px 12px;border:1px solid rgba(248,113,113,.65);border-radius:8px;background:rgba(69,10,10,.96);color:#fecaca;font-size:9px;font-weight:800;box-shadow:0 8px 24px rgba(0,0,0,.35)}.transport-status:empty{display:none}
      .library-expanded{height:100%;min-height:622px;display:grid;grid-template-rows:minmax(0,1fr) auto;overflow:hidden}.library-expanded[hidden],.library-compact-summary[hidden]{display:none!important}.top[data-library-toggle-surface="header"]{cursor:default}.library-compact-summary{position:relative;width:100%;display:flex;flex-direction:column;gap:6px;padding:6px;background:#060912;cursor:default}.compact-shot-row{display:flex;flex-direction:column;gap:6px;padding:6px;border:1px solid rgba(var(--shot-rgb),.38);border-radius:7px;background:linear-gradient(90deg,rgba(var(--shot-rgb),.17),rgba(8,13,23,.86));color:#d9e6f3;overflow:hidden}.compact-shot-row.active{border-color:var(--shot-accent);box-shadow:inset 0 0 0 1px rgba(var(--shot-rgb),.16)}.compact-shot-head{height:28px;display:grid;grid-template-columns:34px minmax(90px,auto) minmax(120px,1fr) auto auto;align-items:center;gap:8px;padding:0 4px}.compact-shot-head small{color:var(--shot-accent);font-size:9px;font-weight:950}.compact-shot-head b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.compact-shot-head span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8ea3b8;font-size:7px}.compact-shot-head em{color:var(--shot-accent);font-size:8px;font-style:normal}.compact-shot-head i{color:#688096;font-size:7px;font-style:normal}.compact-shot-assets{height:132px;display:flex;align-items:stretch;gap:8px;padding:7px;overflow-x:auto;overflow-y:hidden;scrollbar-gutter:stable;border-top:1px solid rgba(var(--shot-rgb),.18)}.compact-shot-assets.empty{height:38px;display:grid;place-items:center}.compact-shot-empty{color:#688096;font-size:8px}.compact-shot-asset{position:relative;flex:0 0 120px;width:120px;height:118px;display:grid;grid-template-rows:81px minmax(0,1fr);gap:4px;padding:6px;border:1px solid rgba(var(--shot-rgb),.28);border-radius:8px;background:rgba(5,9,16,.82);overflow:hidden}.compact-shot-thumb{position:relative;width:106px;height:81px;display:grid;place-items:center;overflow:hidden;border-radius:6px;background:#050910}.compact-shot-thumb img{width:100%;height:100%;display:block;object-fit:cover}.compact-shot-thumb>small{position:absolute;top:3px;left:3px;min-width:22px;padding:2px 3px;border-radius:3px;background:rgba(0,0,0,.76);color:var(--shot-accent);font-size:7px;font-weight:950;text-align:center}.compact-shot-placeholder{width:100%;height:100%;background:linear-gradient(135deg,rgba(var(--shot-rgb),.17),rgba(15,23,42,.84))}.compact-shot-asset>b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#cbd8e5;font-size:7px}.hmb-image-assets[data-library-compact="true"]{height:auto!important;min-height:0!important;grid-template-rows:58px auto;background:#060912}.hmb-image-assets[data-library-compact="true"] .library-compact-summary{display:flex}
      .image-bash-panel .shot-panel-head{display:flex;align-items:center;min-height:38px}.image-bash-panel .shot-panel-toggle{min-width:0;flex:1}.image-bash-panel .selected-actions{display:flex;gap:3px}.image-bash-panel .selected-actions button{min-width:18px}.image-bash-panel .selected-actions button:disabled{opacity:.3}.image-bash-card.compact-shot-asset{grid-template-rows:18px 60px 12px;gap:4px}.image-bash-card.compact-shot-asset .selected-thumb{width:100%;height:60px}.image-bash-card.compact-shot-asset .selected-card-top{margin:0}.image-bash-missing{font-size:8px;color:#94a3b8}.image-bash-panel .tray-scroll{min-height:110px}
      .hmb-image-assets .hmb-native-identity,.hmb-image-assets .hmb-native-actions{display:none;min-width:0;--node-header-text:#e8eef7}.hmb-image-assets[data-hmb-native-header="active"]>.top>.mark,.hmb-image-assets[data-hmb-native-header="active"]>.top>.heading{display:none}.hmb-image-assets[data-hmb-native-header="active"]>.top>.hmb-native-identity{display:flex;align-items:center;flex:1;min-width:0}.hmb-image-assets[data-hmb-native-header="active"]>.top>.hmb-native-actions{display:flex;align-items:center;flex:0 0 auto}.hmb-image-assets .hmb-native-identity>div{min-width:0;max-width:100%}.hmb-image-assets .hmb-native-actions svg{flex-shrink:0}.hmb-image-assets[data-hmb-native-header="active"]>.top{cursor:grab}.hmb-image-assets[data-hmb-native-header="active"]>.top:active{cursor:grabbing}
      @media (prefers-reduced-motion:reduce){.hmb-image-assets *{scroll-behavior:auto!important;animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}}
    </style>
    <div class="hmb-image-assets nodrag" data-hmb-library="image-asset" data-library-compact="false" data-theme="P" data-shot-number="${activeShot?.number || 1}" data-asset-view="${detailView ? "detail" : "image"}" data-busy="${state.scan_busy ? "true" : "false"}" ${state.scan_busy ? 'aria-busy="true"' : ""} style="--active-shot-accent:${activePalette.accent};--active-shot-rgb:${activePalette.rgb}" tabindex="0">
      ${renderImageAssetFixedTop(state)}
      <div class="library-expanded" data-library-expanded>
      <main class="workspace">
        <aside class="panel tree-panel">
          <div class="panel-title"><span>${escapeHtml(imageAssetText(state, "project_folders"))}</span><b>${escapeHtml(hmbImageAssetProjectDisplayName(state) || imageAssetText(state, "ready"))}</b></div>
          <div class="tree">${renderFolderNode(buildFolderTree(state), state)}</div>
        </aside>
        <section class="panel assets-panel">
          <div class="toolbar">
            <button type="button" class="asset-view-toggle" data-asset-view-toggle aria-pressed="${detailView ? "true" : "false"}" aria-label="${escapeHtml(viewToggleLabel)}" title="${escapeHtml(viewToggleLabel)}">
              <svg viewBox="0 0 18 18" aria-hidden="true"><rect x="2" y="2.5" width="4.5" height="4.5" rx=".8"/><path d="M9 4.75h7"/><rect x="2" y="11" width="4.5" height="4.5" rx=".8"/><path d="M9 13.25h7"/></svg>
            </button>
            <input data-search value="${escapeHtml(state.search)}" placeholder="${escapeHtml(imageAssetText(state, "search_placeholder"))}" aria-label="${escapeHtml(imageAssetText(state, "search_placeholder"))}"/>
            <div class="toolbar-status" data-count-digits="4" aria-live="polite"><strong title="${escapeHtml(statusText)}">${escapeHtml(statusText)}</strong></div>
            <span class="filter-chip">${escapeHtml(filterLabel)}</span>
          </div>
          <div class="asset-scroll nodrag nopan nowheel" data-asset-scroll>
            ${catalog.markup}
          </div>
          ${state.warnings.length ? `<div class="warnings">${state.warnings.map((item) => `<div>${escapeHtml(item)}</div>`).join("")}</div>` : ""}
        </section>
      </main>
      ${renderImageAssetShotStack(state)}
      ${renderRegistrationDialog(state, registrationDraft)}
      <div class="transport-status" data-transport-status role="alert" aria-live="assertive" aria-atomic="true"></div>
      </div>
      ${hmbRenderImageAssetCompactSummary(state)}
      ${registrationDraft ? "" : hmbRenderImageAssetRefreshReview(state, refreshReview)}
    </div>
  `;
}

function findNodeRoot(container) {
  let current = container?.parentElement || null;
  let fallback = null;
  for (let depth = 0; current && depth < 16; depth += 1, current = current.parentElement) {
    const className = clean(current.className).toLowerCase();
    if (className.includes("react-flow__node")) return current;
    if (!fallback && (
      current.hasAttribute?.("data-node-id")
      || current.hasAttribute?.("data-nodeid")
      || current.hasAttribute?.("data-id")
    )) fallback = current;
  }
  return fallback || container?.parentElement || container || null;
}

// Griptape's ParameterList uses the same ghost handle id for its collapsed
// header and its expanded Add item row. The native header has
// data-parameter-name; the Add item row deliberately omits it. These contracts
// and the 16x16 SVG circle are verified against the installed editor renderer.
// Decorate only this ImageAsset mount's node. Native handles, ids, listeners,
// accepted types and connection state remain owned by the editor.
export function hmbInstallImageAssetImportHandleDecoration(container) {
  const nodeRoot = findNodeRoot(container);
  const document = nodeRoot?.ownerDocument;
  const view = document?.defaultView;
  if (!nodeRoot?.classList?.contains("react-flow__node") || !document?.createElementNS) {
    return () => {};
  }
  let record = imageAssetImportHandleDecorations.get(nodeRoot);
  if (!record) {
    record = { owners: new Set(), parents: new Map(), overlays: new Map(), observer: null, frame: null };
    const restoreParent = (handle, snapshot) => {
      hmbRestoreImageAssetStyleValue(handle, "visibility", snapshot);
      record.parents.delete(handle);
    };
    const sync = () => {
      const nodeId = hmbImageAssetNodeId(nodeRoot);
      const ghostId = `ghost-item-${nodeId}-IMAGE_IMPORT_IN`;
      const handles = Array.from(nodeRoot.querySelectorAll(
        ".react-flow__handle.target[data-handleid]",
      )).filter((handle) => handle.getAttribute("data-nodeid") === nodeId);
      const parents = handles.filter((handle) => handle.getAttribute("data-handleid") === "IMAGE_IMPORT_IN");
      const addHandles = handles.filter((handle) => {
        if (handle.getAttribute("data-handleid") !== ghostId) return false;
        if (handle.closest("[data-parameter-name]")) return false;
        // Confirm the native ghost row, rather than relying on displayed text.
        for (let row = handle.parentElement; row && row !== nodeRoot; row = row.parentElement) {
          if (row.classList?.contains(ghostId)) return true;
        }
        return false;
      });
      const wantedParents = new Set(addHandles.length ? parents : []);
      record.parents.forEach((snapshot, handle) => {
        if (!wantedParents.has(handle)) restoreParent(handle, snapshot);
      });
      const blue = parents[0]?.querySelector("svg circle")?.getAttribute("stroke") || "#3b82f6";
      wantedParents.forEach((handle) => {
        if (!record.parents.has(handle)) record.parents.set(handle, hmbImageAssetStyleValue(handle, "visibility"));
        // visibility preserves the handle's measured box and existing edges.
        hmbSetImageAssetStyleValue(handle, "visibility", "hidden");
      });
      const wantedSvgs = new Set(addHandles.map((handle) => handle.querySelector("svg"))
        .filter((svg) => svg?.getAttribute("viewBox") === "0 0 16 16" && svg.querySelector("circle")));
      record.overlays.forEach((overlay, svg) => {
        if (!wantedSvgs.has(svg) || overlay.parentElement !== svg) {
          overlay.remove();
          record.overlays.delete(svg);
        }
      });
      wantedSvgs.forEach((svg) => {
        let overlay = record.overlays.get(svg);
        if (!overlay) {
          overlay = document.createElementNS("http://www.w3.org/2000/svg", "path");
          overlay.setAttribute("data-hmb-image-import-universal", "");
          overlay.setAttribute("d", "M 8 1 A 7 7 0 0 1 8 15");
          overlay.setAttribute("fill", "none");
          overlay.setAttribute("stroke-width", "2");
          overlay.setAttribute("pointer-events", "none");
          overlay.setAttribute("aria-hidden", "true");
          svg.appendChild(overlay);
          record.overlays.set(svg, overlay);
        }
        if (overlay.getAttribute("stroke") !== blue) overlay.setAttribute("stroke", blue);
      });
    };
    const schedule = () => {
      if (record.frame != null) return;
      if (!view?.requestAnimationFrame) { sync(); return; }
      record.frame = view.requestAnimationFrame(() => { record.frame = null; sync(); });
    };
    if (view?.MutationObserver) {
      record.observer = new view.MutationObserver((mutations) => {
        if (mutations.some(({ target }) => !Array.from(record.owners).some((owner) => owner.contains(target)))) schedule();
      });
      record.observer.observe(nodeRoot, {
        subtree: true, childList: true, attributes: true,
        attributeFilter: ["data-id", "data-nodeid", "data-handleid", "data-parameter-name", "class", "stroke"],
      });
    }
    record.sync = sync;
    record.restoreParent = restoreParent;
    imageAssetImportHandleDecorations.set(nodeRoot, record);
  }
  record.owners.add(container);
  record.sync();
  let disposed = false;
  return () => {
    if (disposed) return;
    disposed = true;
    record.owners.delete(container);
    if (record.owners.size) return;
    record.observer?.disconnect();
    if (record.frame != null) view?.cancelAnimationFrame?.(record.frame);
    record.parents.forEach((snapshot, handle) => record.restoreParent(handle, snapshot));
    record.overlays.forEach((overlay) => overlay.remove());
    record.overlays.clear();
    imageAssetImportHandleDecorations.delete(nodeRoot);
  };
}

const IMAGE_ASSET_INTERNAL_TOGGLE_INTERACTIVE_SELECTOR = [
  ".project-switch",
  "[data-hmb-native-identity]",
  "[data-hmb-native-actions]",
  "button",
  "input",
  "select",
  "textarea",
  "a",
  "[role='button']",
  "[contenteditable='true']",
  "[contenteditable='']",
].join(",");

export function hmbImageAssetInternalToggleSurfaceForEvent(container, event) {
  if (!container || !event || event.type !== "dblclick") return null;
  if (event.defaultPrevented || Number(event.button ?? 0) !== 0) return null;
  const target = event.target?.nodeType === 3 ? event.target.parentElement : event.target;
  if (!target || !container.contains?.(target)) return null;
  const surface = target.closest?.("[data-library-toggle-surface]") || null;
  if (!surface || !container.contains?.(surface)) return null;
  const kind = surface.getAttribute?.("data-library-toggle-surface") || "";
  if (kind === "header") {
    if (!surface.classList?.contains?.("top")) return null;
    const interactive = target.closest?.(IMAGE_ASSET_INTERNAL_TOGGLE_INTERACTIVE_SELECTOR);
    if (interactive && surface.contains?.(interactive)) return null;
    return surface;
  }
  return null;
}

const IMAGE_ASSET_COMPACT_GEOMETRY_PROPERTIES = Object.freeze([
  "height",
  "min-height",
  "max-height",
]);
const IMAGE_ASSET_COMPACT_NODE_ATTRIBUTE = "data-hmb-image-asset-compact";
const IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE = "data-hmb-image-asset-resize-locked";
const IMAGE_ASSET_NATIVE_RESIZE_CONTROL_SELECTOR = ".react-flow__resize-control";

export function hmbSetImageAssetNativeResizeLocked(container, locked) {
  const next = Boolean(locked);
  const previousRoot = container?.__hmbImageAssetResizeLockRoot || null;
  const nodeRoot = next ? findNodeRoot(container) : previousRoot || findNodeRoot(container);
  if (!container || !nodeRoot || typeof nodeRoot !== "object") return false;
  if (next && previousRoot && previousRoot !== nodeRoot) {
    hmbSetImageAssetNativeResizeLocked(container, false);
  }
  if (!next) {
    const record = imageAssetNativeResizeLocks.get(nodeRoot);
    delete container.__hmbImageAssetResizeLockRoot;
    if (!record) return false;
    record.owners.delete(container);
    if (record.owners.size) return true;
    record.listeners.forEach(([type, handler, options]) => {
      try { nodeRoot.removeEventListener?.(type, handler, options); } catch (_error) {}
    });
    record.observer?.disconnect?.();
    record.styleElement?.remove?.();
    if (record.attribute.present) {
      nodeRoot.setAttribute?.(IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE, record.attribute.value);
    } else {
      nodeRoot.removeAttribute?.(IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE);
    }
    imageAssetNativeResizeLocks.delete(nodeRoot);
    return true;
  }

  let record = imageAssetNativeResizeLocks.get(nodeRoot);
  if (!record) {
    const attribute = {
      present: Boolean(nodeRoot.hasAttribute?.(IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE)),
      value: nodeRoot.getAttribute?.(IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE) || "",
    };
    const ownerDocument = nodeRoot.ownerDocument || container.ownerDocument
      || (typeof document !== "undefined" ? document : null);
    const styleElement = ownerDocument?.createElement?.("style") || null;
    if (styleElement) {
      styleElement.setAttribute?.("data-hmb-image-asset-resize-lock-style", "");
      styleElement.textContent = `[${IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE}="true"] ${IMAGE_ASSET_NATIVE_RESIZE_CONTROL_SELECTOR}{display:none!important;visibility:hidden!important;pointer-events:none!important;opacity:0!important}`;
      const styleHost = ownerDocument.head || ownerDocument.querySelector?.("head") || nodeRoot;
      styleHost?.appendChild?.(styleElement);
    }
    const blockNativeResizeStart = (event) => {
      const target = event?.target?.nodeType === 3 ? event.target.parentElement : event?.target;
      const control = target?.closest?.(IMAGE_ASSET_NATIVE_RESIZE_CONTROL_SELECTOR) || null;
      if (!control || !nodeRoot.contains?.(control)) return;
      event.preventDefault?.();
      event.stopImmediatePropagation?.();
      event.stopPropagation?.();
    };
    const options = { capture: true, passive: false };
    const listeners = ["pointerdown", "mousedown", "touchstart"].map((type) => {
      nodeRoot.addEventListener?.(type, blockNativeResizeStart, options);
      return [type, blockNativeResizeStart, options];
    });
    const Observer = ownerDocument?.defaultView?.MutationObserver
      || (typeof MutationObserver === "function" ? MutationObserver : null);
    let observer = null;
    if (Observer) {
      observer = new Observer(() => {
        const current = imageAssetNativeResizeLocks.get(nodeRoot);
        if (
          current?.owners?.size
          && nodeRoot.getAttribute?.(IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE) !== "true"
        ) nodeRoot.setAttribute?.(IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE, "true");
      });
      try {
        observer.observe(nodeRoot, {
          attributes: true,
          attributeFilter: [IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE],
        });
      } catch (_error) {
        observer = null;
      }
    }
    record = { owners: new Set(), attribute, styleElement, listeners, observer };
    imageAssetNativeResizeLocks.set(nodeRoot, record);
  }
  record.owners.add(container);
  container.__hmbImageAssetResizeLockRoot = nodeRoot;
  nodeRoot.setAttribute?.(IMAGE_ASSET_RESIZE_LOCK_ATTRIBUTE, "true");
  return true;
}

function hmbImageAssetNodeId(nodeRoot) {
  return clean(
    nodeRoot?.getAttribute?.("data-id")
    || nodeRoot?.getAttribute?.("data-node-id")
    || nodeRoot?.getAttribute?.("data-nodeid"),
  );
}

function hmbImageAssetNodeIdentity(nodeRoot) {
  const id = hmbImageAssetNodeId(nodeRoot);
  // Temporary ids are recyclable host labels, not stable node identities.
  // Key them by their exact shell until React Flow publishes the final id.
  return id && !id.endsWith("_temp") ? `id:${id}` : nodeRoot;
}

function hmbImageAssetTempFinalIdentityRename(previousId, nextId) {
  return previousId.endsWith("_temp") && nextId === previousId.slice(0, -5);
}

function hmbImageAssetCompactKeyHasOtherOwner(nodeKey, excludedContainer = null) {
  if (!nodeKey) return false;
  return Array.from(imageAssetMountedContainers).some((candidate) => (
    candidate !== excludedContainer
    && candidate.__hmbImageAssetCompact === true
    && candidate.__hmbImageAssetRecordedNodeKey === nodeKey
  ));
}

function hmbReleaseImageAssetCompactKey(nodeKey, excludedContainer = null) {
  if (!nodeKey || hmbImageAssetCompactKeyHasOtherOwner(nodeKey, excludedContainer)) return false;
  return imageAssetCompactNodeKeys.delete(nodeKey);
}

// React Flow assigns a temporary data-id before finalizing a newly-created
// node. Record every identity observed by this mount so teardown never derives
// cleanup solely from the mutable, final DOM attribute. The exact `_temp` ->
// final rename is the only identity transition allowed to carry compact state;
// arbitrary id reuse is treated as a different node.
export function hmbImageAssetRecordedNodeIdentity(container) {
  if (!container) return null;
  const nodeRoot = findNodeRoot(container);
  const currentId = hmbImageAssetNodeId(nodeRoot);
  const currentKey = hmbImageAssetNodeIdentity(nodeRoot);
  if (!currentKey) return null;
  const hasRecordedKey = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbImageAssetRecordedNodeKey",
  );
  const previousKey = hasRecordedKey
    ? container.__hmbImageAssetRecordedNodeKey
    : null;
  const previousId = clean(container.__hmbImageAssetRecordedNodeId);
  if (!hasRecordedKey) {
    container.__hmbImageAssetRecordedNodeKey = currentKey;
    container.__hmbImageAssetRecordedNodeId = currentId;
    container.__hmbImageAssetRecordedNodeRoot = nodeRoot;
  } else if (previousKey !== currentKey) {
    const carryCompact = hmbImageAssetTempFinalIdentityRename(previousId, currentId)
      && (
        imageAssetCompactNodeKeys.has(previousKey)
        || container.__hmbImageAssetCompact === true
      );
    hmbReleaseImageAssetCompactKey(previousKey, container);
    if (carryCompact) imageAssetCompactNodeKeys.add(currentKey);
    container.__hmbImageAssetRecordedNodeKey = currentKey;
    container.__hmbImageAssetRecordedNodeId = currentId;
    container.__hmbImageAssetRecordedNodeRoot = nodeRoot;
  } else {
    container.__hmbImageAssetRecordedNodeId = currentId;
    container.__hmbImageAssetRecordedNodeRoot = nodeRoot;
  }
  let recordedKeys = container.__hmbImageAssetRecordedNodeKeys;
  if (!(recordedKeys instanceof Set)) {
    recordedKeys = new Set();
    container.__hmbImageAssetRecordedNodeKeys = recordedKeys;
  }
  recordedKeys.add(currentKey);
  return currentKey;
}

export function hmbAttachImageAssetRegistryContainer(container) {
  if (!container) return null;
  imageAssetMountedContainers.add(container);
  return hmbImageAssetRecordedNodeIdentity(container);
}

export function hmbRememberImageAssetCompactRegistry(container, compactMode) {
  const nodeKey = hmbImageAssetRecordedNodeIdentity(container);
  if (!nodeKey) return false;
  if (compactMode) imageAssetCompactNodeKeys.add(nodeKey);
  else imageAssetCompactNodeKeys.delete(nodeKey);
  return imageAssetCompactNodeKeys.has(nodeKey);
}

export function hmbImageAssetCompactRegistryHas(container) {
  const nodeKey = hmbImageAssetRecordedNodeIdentity(container);
  return !!nodeKey && imageAssetCompactNodeKeys.has(nodeKey);
}

export function hmbDetachImageAssetRegistryContainer(container) {
  if (!container) return false;
  if (!imageAssetMountedContainers.has(container)) {
    delete container.__hmbImageAssetRecordedNodeKey;
    delete container.__hmbImageAssetRecordedNodeId;
    delete container.__hmbImageAssetRecordedNodeRoot;
    delete container.__hmbImageAssetRecordedNodeKeys;
    return false;
  }
  const nodeRoot = findNodeRoot(container);
  hmbImageAssetRecordedNodeIdentity(container);
  const recordedKeys = container.__hmbImageAssetRecordedNodeKeys instanceof Set
    ? Array.from(container.__hmbImageAssetRecordedNodeKeys)
    : [container.__hmbImageAssetRecordedNodeKey].filter(Boolean);
  const wasMounted = imageAssetMountedContainers.delete(container);
  recordedKeys.forEach((nodeKey) => hmbReleaseImageAssetCompactKey(nodeKey, container));
  const currentKey = hmbImageAssetNodeIdentity(nodeRoot);
  if (!currentKey || !imageAssetCompactNodeKeys.has(currentKey)) {
    nodeRoot?.removeAttribute?.(IMAGE_ASSET_COMPACT_NODE_ATTRIBUTE);
  }
  delete container.__hmbImageAssetRecordedNodeKey;
  delete container.__hmbImageAssetRecordedNodeId;
  delete container.__hmbImageAssetRecordedNodeRoot;
  delete container.__hmbImageAssetRecordedNodeKeys;
  return wasMounted;
}

function hmbImageAssetStyleValue(element, property) {
  const style = element?.style;
  if (!style) return { value: "", priority: "" };
  if (typeof style.getPropertyValue === "function") {
    return {
      value: style.getPropertyValue(property) || "",
      priority: style.getPropertyPriority?.(property) || "",
    };
  }
  const camel = property.replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
  return { value: clean(style[camel]), priority: "" };
}

function hmbSetImageAssetStyleValue(element, property, value, priority = "important") {
  const style = element?.style;
  if (!style) return;
  const previous = hmbImageAssetStyleValue(element, property);
  if (previous.value === value && previous.priority === priority) return;
  if (typeof style.setProperty === "function") {
    style.setProperty(property, value, priority);
    return;
  }
  const camel = property.replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
  style[camel] = value;
}

function hmbRestoreImageAssetStyleValue(element, property, snapshot) {
  const style = element?.style;
  if (!style) return;
  if (snapshot?.value) {
    hmbSetImageAssetStyleValue(element, property, snapshot.value, snapshot.priority || "");
    return;
  }
  if (typeof style.removeProperty === "function") style.removeProperty(property);
  else {
    const camel = property.replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
    style[camel] = "";
  }
}

function hmbImageAssetLayoutHeight(element) {
  const offset = Number(element?.offsetHeight) || 0;
  if (offset > 0) return offset;
  try {
    const height = Number(element?.getBoundingClientRect?.()?.height) || 0;
    if (height > 0) return height;
  } catch (_error) {}
  return Number.parseFloat(hmbImageAssetStyleValue(element, "height").value) || 0;
}

function hmbImageAssetOffsetWithin(element, ancestor) {
  // offsetTop is relative to offsetParent, not parentElement. Summing it for
  // every wrapper counts the same native input rows several times. Rects also
  // reflect list expansion; remove the canvas zoom before using the distance.
  try {
    const outer = ancestor?.getBoundingClientRect?.();
    const inner = element?.getBoundingClientRect?.();
    const width = Number(ancestor?.offsetWidth) || 0;
    const zoom = width > 0 ? Number(outer?.width) / width : 0;
    const delta = Number(inner?.top) - Number(outer?.top);
    if (zoom > 0 && Number.isFinite(delta)) return Math.max(0, delta / zoom);
  } catch (_error) {}
  let offset = 0;
  for (let current = element, depth = 0; current && depth < 16; depth += 1) {
    if (current === ancestor) return Math.max(0, offset);
    offset += Number(current.offsetTop) || 0;
    current = current.offsetParent;
  }
  return null;
}

function hmbImageAssetCompactSummaryHeight(summary) {
  const measured = Number(summary?.scrollHeight) || Number(summary?.offsetHeight) || 0;
  if (measured > 0) return measured;
  const rows = Array.from(summary?.querySelectorAll?.("[data-compact-shot-row]") || []);
  if (!rows.length) return 1;
  const rowsHeight = rows.reduce((total, row) => {
    const ownHeight = hmbImageAssetLayoutHeight(row);
    if (ownHeight > 0) return total + ownHeight;
    const hasAssets = Boolean(row.querySelectorAll?.("[data-compact-asset-key]")?.length);
    return total + (hasAssets ? 180 : 80);
  }, 0);
  return rowsHeight + Math.max(0, rows.length - 1) * 6 + 12;
}

function hmbImageAssetMountIsVisible(container) {
  for (let current = container, depth = 0; current && depth < 16; depth += 1) {
    if (current.hidden || current.hasAttribute?.("hidden")) return false;
    let computed = null;
    try { computed = current.ownerDocument?.defaultView?.getComputedStyle?.(current); } catch (_error) {}
    const display = clean(computed?.display || current.style?.display).toLowerCase();
    const visibility = clean(computed?.visibility || current.style?.visibility).toLowerCase();
    const opacity = Number.parseFloat(computed?.opacity || current.style?.opacity);
    if (display === "none" || ["hidden", "collapse"].includes(visibility) || opacity === 0) return false;
    current = current.parentElement;
  }
  try {
    if (typeof container?.getClientRects === "function" && container.getClientRects().length === 0) {
      return false;
    }
  } catch (_error) {}
  return true;
}

function hmbCaptureImageAssetExpandedGeometry(container) {
  if (!container || container.__hmbImageAssetExpandedGeometry) {
    return container?.__hmbImageAssetExpandedGeometry || null;
  }
  const nodeRoot = findNodeRoot(container);
  const root = container.querySelector?.(".hmb-image-assets");
  if (!nodeRoot || nodeRoot === container || !nodeRoot.style || !root) return null;
  const shells = [];
  for (let current = container, depth = 0; current && depth < 16; depth += 1) {
    if (current.style) shells.push(current);
    if (current === nodeRoot) break;
    current = current.parentElement;
  }
  if (!shells.includes(nodeRoot)) return null;
  const records = shells.map((element) => ({
    element,
    properties: Object.fromEntries(IMAGE_ASSET_COMPACT_GEOMETRY_PROPERTIES.map(
      (property) => [property, hmbImageAssetStyleValue(element, property)],
    )),
  }));
  const expandedNodeHeight = hmbImageAssetLayoutHeight(nodeRoot);
  const expandedWidgetHeight = hmbImageAssetLayoutHeight(root);
  const widgetOffset = hmbImageAssetOffsetWithin(root, nodeRoot);
  const heightDifference = expandedNodeHeight > expandedWidgetHeight
    ? expandedNodeHeight - expandedWidgetHeight
    : 0;
  // In Griptape 0.122 every native row precedes the custom widget.  Its actual
  // top offset is therefore the chrome delta.  A fixed expanded node can have
  // unused height below the widget; treating nodeHeight-widgetHeight as chrome
  // recreates the large black tail compact mode is meant to remove.
  const chromeHeight = Math.max(0, widgetOffset > 0 ? widgetOffset : heightDifference);
  const geometry = { nodeRoot, records, expandedNodeHeight, chromeHeight };
  container.__hmbImageAssetExpandedGeometry = geometry;
  return geometry;
}

function hmbRequestImageAssetNodeInternals(container, nodeRoot) {
  const updater = container?.__hmbImageAssetUpdateNodeInternals
    || container?.updateNodeInternals
    || null;
  if (typeof updater !== "function") return false;
  const nodeId = clean(
    nodeRoot?.getAttribute?.("data-id")
    || nodeRoot?.getAttribute?.("data-node-id")
    || nodeRoot?.getAttribute?.("data-nodeid"),
  );
  try {
    updater(nodeId || nodeRoot);
    return true;
  } catch (_error) {
    return false;
  }
}

export function hmbSetImageAssetCompactShellGeometry(container, compactMode) {
  if (!container) return false;
  if (!compactMode) {
    hmbStopImageAssetCompactGeometryObserver(container);
    const geometry = container.__hmbImageAssetExpandedGeometry;
    if (!geometry) return false;
    geometry.records.slice().reverse().forEach(({ element, properties }) => {
      IMAGE_ASSET_COMPACT_GEOMETRY_PROPERTIES.forEach((property) => {
        hmbRestoreImageAssetStyleValue(element, property, properties[property]);
      });
    });
    delete container.__hmbImageAssetExpandedGeometry;
    hmbRequestImageAssetNodeInternals(container, geometry.nodeRoot);
    return true;
  }
  const geometry = hmbCaptureImageAssetExpandedGeometry(container);
  const summary = container.querySelector?.("[data-library-compact-summary]");
  if (!geometry || !summary) return false;
  // React can replace row wrappers when a native ParameterList changes. Only
  // size the current ancestor chain, and retain each original style for exit.
  const activeShells = new Set([geometry.nodeRoot]);
  for (let element = container, depth = 0; element && depth < 16; depth += 1, element = element.parentElement) {
    if (element === geometry.nodeRoot) break;
    activeShells.add(element);
    if (!geometry.records.some((record) => record.element === element)) {
      geometry.records.push({ element, properties: Object.fromEntries(
        IMAGE_ASSET_COMPACT_GEOMETRY_PROPERTIES.map((property) => [property, hmbImageAssetStyleValue(element, property)]),
      ) });
    }
    hmbSetImageAssetStyleValue(element, "height", "auto");
    hmbSetImageAssetStyleValue(element, "min-height", "0px");
    hmbSetImageAssetStyleValue(element, "max-height", "none");
  }
  geometry.records = geometry.records.filter(({ element, properties }) => {
    if (activeShells.has(element)) return true;
    IMAGE_ASSET_COMPACT_GEOMETRY_PROPERTIES.forEach((property) => {
      hmbRestoreImageAssetStyleValue(element, property, properties[property]);
    });
    return false;
  });
  const root = container.querySelector?.(".hmb-image-assets");
  const liveChrome = hmbImageAssetOffsetWithin(root, geometry.nodeRoot);
  if (liveChrome != null) geometry.chromeHeight = liveChrome;
  const fixedTop = container.querySelector?.(".top[data-library-toggle-surface='header']");
  const fixedTopHeight = hmbImageAssetLayoutHeight(fixedTop) || 58;
  const targetHeight = Math.max(
    1,
    Math.ceil(
      geometry.chromeHeight
      + fixedTopHeight
      + hmbImageAssetCompactSummaryHeight(summary)
      + 2, // widget border; never trim the last compact Shot row
    ),
  );
  const height = `${targetHeight}px`;
  const changed = IMAGE_ASSET_COMPACT_GEOMETRY_PROPERTIES.some((property) => (
    hmbImageAssetStyleValue(geometry.nodeRoot, property).value !== height
    || hmbImageAssetStyleValue(geometry.nodeRoot, property).priority !== "important"
  ));
  hmbSetImageAssetStyleValue(geometry.nodeRoot, "height", height);
  hmbSetImageAssetStyleValue(geometry.nodeRoot, "min-height", height);
  hmbSetImageAssetStyleValue(geometry.nodeRoot, "max-height", height);
  if (changed) hmbRequestImageAssetNodeInternals(container, geometry.nodeRoot);
  hmbWatchImageAssetCompactGeometry(container);
  return true;
}

function hmbStopImageAssetCompactGeometryObserver(container) {
  const watch = container?.__hmbImageAssetCompactGeometryObserver;
  if (!watch) return;
  watch.mutations?.disconnect?.();
  watch.resize?.disconnect?.();
  if (watch.frame != null) watch.view.cancelAnimationFrame?.(watch.frame);
  delete container.__hmbImageAssetCompactGeometryObserver;
}

function hmbWatchImageAssetCompactGeometry(container) {
  const geometry = container.__hmbImageAssetExpandedGeometry;
  const nodeRoot = geometry?.nodeRoot;
  const view = nodeRoot?.ownerDocument?.defaultView;
  if (!nodeRoot || !view?.requestAnimationFrame) return;
  let watch = container.__hmbImageAssetCompactGeometryObserver;
  if (watch && watch.nodeRoot !== nodeRoot) {
    hmbStopImageAssetCompactGeometryObserver(container);
    watch = null;
  }
  if (!watch) {
    watch = { nodeRoot, view, frame: null, targets: new Set() };
    const schedule = () => {
      if (watch.frame != null) return;
      watch.frame = view.requestAnimationFrame(() => {
        watch.frame = null;
        if (container.__hmbImageAssetCompactGeometryObserver !== watch) return;
        if (!container.__hmbImageAssetCompact || !hmbImageAssetMountIsVisible(container)) return;
        hmbSetImageAssetCompactShellGeometry(container, true);
      });
    };
    // No polling or state publication. Native input rows change outside the
    // widget's props/update path; observe their layout, not thumbnail churn.
    if (view.MutationObserver) {
      watch.mutations = new view.MutationObserver((records) => {
        if (records.some(({ target }) => !container.contains?.(target))) schedule();
      });
      watch.mutations.observe(nodeRoot, {
        subtree: true, childList: true, attributes: true,
        attributeFilter: ["style", "class", "hidden", "aria-expanded"],
      });
    }
    if (view.ResizeObserver) watch.resize = new view.ResizeObserver(schedule);
    container.__hmbImageAssetCompactGeometryObserver = watch;
  }
  const targets = new Set([container.querySelector?.("[data-library-compact-summary]")]);
  for (let element = container, depth = 0; element && depth < 16; depth += 1, element = element.parentElement) {
    targets.add(element);
    if (element === nodeRoot) break;
    // Includes IMAGE_IMPORT_IN and any live import children, without changing
    // their native controls or the input handles used for connections.
    Array.from(element.parentElement?.children || []).forEach((sibling) => {
      if (sibling !== element && !["STYLE", "SCRIPT"].includes(sibling.tagName)) targets.add(sibling);
    });
  }
  targets.delete(null);
  targets.delete(undefined);
  watch.targets.forEach((element) => { if (!targets.has(element)) watch.resize?.unobserve?.(element); });
  targets.forEach((element) => { if (!watch.targets.has(element)) watch.resize?.observe?.(element); });
  watch.targets = targets;
}

function hmbCancelImageAssetCompactGeometrySettle(container) {
  const handle = container?.__hmbImageAssetCompactGeometryFrame;
  if (handle != null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(handle);
  if (container) {
    delete container.__hmbImageAssetCompactGeometryFrame;
    delete container.__hmbImageAssetCompactGeometryFramesLeft;
  }
}

function hmbSettleImageAssetCompactGeometry(container) {
  hmbCancelImageAssetCompactGeometrySettle(container);
  if (typeof requestAnimationFrame !== "function") return false;
  container.__hmbImageAssetCompactGeometryFramesLeft = 3;
  const settle = () => {
    delete container.__hmbImageAssetCompactGeometryFrame;
    const root = container?.querySelector?.(".hmb-image-assets");
    if (!root || root.getAttribute?.("data-library-compact") !== "true") {
      delete container.__hmbImageAssetCompactGeometryFramesLeft;
      return;
    }
    hmbSetImageAssetCompactShellGeometry(container, true);
    const framesLeft = Math.max(0, Number(container.__hmbImageAssetCompactGeometryFramesLeft) - 1);
    container.__hmbImageAssetCompactGeometryFramesLeft = framesLeft;
    if (framesLeft > 0) container.__hmbImageAssetCompactGeometryFrame = requestAnimationFrame(settle);
    else delete container.__hmbImageAssetCompactGeometryFramesLeft;
  };
  container.__hmbImageAssetCompactGeometryFrame = requestAnimationFrame(settle);
  return true;
}

export function hmbSetImageAssetLibraryCompact(container, compactMode, options = {}) {
  const root = container?.querySelector?.(".hmb-image-assets");
  const summary = root?.querySelector?.("[data-library-compact-summary]");
  let expanded = root?.querySelector?.("[data-library-expanded]")
    || container?.__hmbImageAssetExpandedElement
    || container?.__hmbImageAssetExpandedFragment?.querySelector?.("[data-library-expanded]")
    || null;
  if (!root || !expanded || !summary) return false;
  const next = Boolean(compactMode);
  if (Boolean(container.__hmbImageAssetCompact) === next) {
    hmbSetImageAssetNativeResizeLocked(container, next);
    return true;
  }
  const ownsGeometry = options.geometry !== false
    && (options.forceGeometry === true || hmbImageAssetMountIsVisible(container));
  hmbCancelImageAssetCompactGeometrySettle(container);
  if (next && ownsGeometry) hmbCaptureImageAssetExpandedGeometry(container);
  if (next) hmbSetImageAssetNativeResizeLocked(container, true);
  root.setAttribute?.("data-library-compact", next ? "true" : "false");
  if (next) {
    container.__hmbImageAssetCompactUiMemory = captureImageAssetUi(
      container,
      container.__hmbImageAssetLatestState || {},
    );
    container.__hmbImageAssetExpandedElement = expanded;
    const ownerDocument = root.ownerDocument || container.ownerDocument
      || (typeof document !== "undefined" ? document : null);
    const fragment = ownerDocument?.createDocumentFragment?.();
    if (fragment) {
      fragment.appendChild(expanded);
      container.__hmbImageAssetExpandedFragment = fragment;
    } else {
      expanded.hidden = true;
    }
    summary.hidden = false;
    hmbSetImageAssetCompactThumbnailsActive(summary, true);
    container.__hmbImageAssetCompact = true;
    if (ownsGeometry) {
      hmbSetImageAssetCompactShellGeometry(container, true);
      hmbSettleImageAssetCompactGeometry(container);
    }
  } else {
    if (expanded.parentElement !== root && expanded.parentNode !== root) {
      root.insertBefore?.(expanded, summary);
    }
    expanded.hidden = false;
    summary.hidden = true;
    hmbSetImageAssetCompactThumbnailsActive(summary, false);
    container.__hmbImageAssetCompact = false;
    if (container.__hmbImageAssetExpandedGeometry) {
      hmbSetImageAssetCompactShellGeometry(container, false);
    }
    hmbSetImageAssetNativeResizeLocked(container, false);
    restoreImageAssetUi(
      container,
      container.__hmbImageAssetLatestState || {},
      container.__hmbImageAssetCompactUiMemory,
    );
    delete container.__hmbImageAssetExpandedFragment;
    delete container.__hmbImageAssetExpandedElement;
  }
  return true;
}

function hmbSetImageAssetLibraryCompactGroup(container, compactMode) {
  const nodeKey = hmbImageAssetRecordedNodeIdentity(container);
  const candidates = [container, ...Array.from(imageAssetMountedContainers).filter(
    (candidate) => (
      candidate !== container
      && hmbImageAssetRecordedNodeIdentity(candidate) === nodeKey
    ),
  )];
  hmbRememberImageAssetCompactRegistry(container, compactMode);
  candidates.forEach((candidate) => {
    const candidateRoot = findNodeRoot(candidate);
    if (compactMode) candidateRoot?.setAttribute?.(IMAGE_ASSET_COMPACT_NODE_ATTRIBUTE, "true");
    else candidateRoot?.removeAttribute?.(IMAGE_ASSET_COMPACT_NODE_ATTRIBUTE);
  });
  const changed = candidates.map((candidate, index) => ({
    candidate,
    ok: hmbSetImageAssetLibraryCompact(candidate, compactMode, {
      geometry: index === 0,
      forceGeometry: index === 0,
    }),
  }));
  if (!compactMode) {
    changed.forEach(({ candidate, ok }) => {
      if (ok) candidate.__hmbImageAssetRefreshAfterCompactExpand?.();
    });
  }
  return changed.some(({ ok }) => ok);
}

export function hmbPrepareImageAssetCanvasGestures(container) {
  if (!container) return;
  const canvasPanRoots = [
    container,
    container.querySelector?.(".hmb-image-assets"),
  ].filter(Boolean);
  canvasPanRoots.forEach((element) => {
    element.classList?.remove("nopan", "nowheel");
    element.classList?.add("nodrag");
  });
}

function hmbImageAssetWheelPixels(event, viewportHeight) {
  const mode = Number(event?.deltaMode) || 0;
  const unit = mode === 1
    ? 40
    : mode === 2
      ? Math.max(1, Number(viewportHeight) || 1)
      : 1;
  return {
    left: (Number(event?.deltaX) || 0) * unit,
    top: (Number(event?.deltaY) || 0) * unit,
  };
}

export function hmbInstallImageAssetScrollGestures(container, on) {
  const assetScroll = container?.querySelector?.("[data-asset-scroll]");
  if (!assetScroll || typeof on !== "function") return null;
  // React Flow treats `nowheel` as a local no-zoom island. It is deliberately
  // scoped to the asset viewport; the rest of the node keeps canvas zoom.
  // Middle-button gestures are deliberately left untouched so Griptape owns
  // whole-canvas panning even when the pointer is over an image card. The
  // host's middle-button path bypasses `nopan`; other local drag gestures do not.
  assetScroll.classList?.add("nowheel");

  const stopLocalGesture = (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
  };

  on(assetScroll, "wheel", (event) => {
    const delta = hmbImageAssetWheelPixels(event, assetScroll.clientHeight);
    if (!delta.left && !delta.top) return;
    assetScroll.scrollLeft = (Number(assetScroll.scrollLeft) || 0) + delta.left;
    assetScroll.scrollTop = (Number(assetScroll.scrollTop) || 0) + delta.top;
    stopLocalGesture(event);
  }, { passive: false });
  return assetScroll;
}

function isSelectedNodeRoot(root) {
  if (!root) return false;
  if (root.classList?.contains("selected")) return true;
  if (clean(root.getAttribute?.("aria-selected")).toLowerCase() === "true") return true;
  if (clean(root.getAttribute?.("data-selected")).toLowerCase() === "true") return true;
  return Boolean(root.querySelector?.(
    ".react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']",
  ));
}

function hmbImageAssetDeleteEditingTarget(event) {
  return Boolean(event?.target?.closest?.(
    "input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor",
  ));
}

export function hmbGuardSelectedNodeKeyboardDelete(container, event) {
  if (!["Backspace", "Delete"].includes(event?.key)) return false;
  if (container?.ownerDocument?.documentElement?.getAttribute?.("data-hmb-native-deletion-guard") === "engine-preflight") return false;
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (hmbImageAssetDeleteEditingTarget(event)) return false;
  if (!isSelectedNodeRoot(findNodeRoot(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

function nativeProjectRootElements(container) {
  const root = findNodeRoot(container);
  if (!root?.querySelectorAll) return [];
  const selectors = [
    '[data-parameter-name="PROJECT_ROOT"] input',
    '[data-parameter-name="PROJECT_ROOT"] textarea',
    '[data-parameter="PROJECT_ROOT"] input',
    '[data-parameter="PROJECT_ROOT"] textarea',
    '[data-parameter-key="PROJECT_ROOT"] input',
    '[data-parameter-key="PROJECT_ROOT"] textarea',
    'input[name="PROJECT_ROOT"]',
    'textarea[name="PROJECT_ROOT"]',
    'input[id*="PROJECT_ROOT" i]',
    'textarea[id*="PROJECT_ROOT" i]',
    'input[aria-label*="PROJECT_ROOT" i]',
    'textarea[aria-label*="PROJECT_ROOT" i]',
  ];
  const found = [];
  const seen = new Set();
  selectors.forEach((selector) => {
    root.querySelectorAll(selector).forEach((element) => {
      if (container.contains?.(element) || seen.has(element)) return;
      seen.add(element);
      found.push(element);
    });
  });
  return found;
}

function nativeProjectRootHosts(container) {
  const root = findNodeRoot(container);
  if (!root?.querySelectorAll) return [];
  const found = [];
  const seen = new Set();
  const add = (host) => {
    if (!host || host === root || container.contains?.(host) || host.contains?.(container) || seen.has(host)) return;
    seen.add(host);
    found.push(host);
  };
  [
    '[data-parameter-name="PROJECT_ROOT"]',
    '[data-parameter="PROJECT_ROOT"]',
    '[data-parameter-key="PROJECT_ROOT"]',
    '[data-parameter-id*="PROJECT_ROOT" i]',
    '[aria-label*="PROJECT_ROOT" i]',
  ].forEach((selector) => root.querySelectorAll(selector).forEach(add));
  nativeProjectRootElements(container).forEach((element) => {
    add(element.closest?.(
      '[data-parameter-name], [data-parameter], [data-parameter-key], [data-parameter-id], [role="group"]',
    ) || element.parentElement);
  });
  return found;
}

function pathFromNativeElement(element) {
  if (!element) return "";
  const values = [
    element.value,
    element.getAttribute?.("value"),
    element.getAttribute?.("title"),
    element.getAttribute?.("data-value"),
    element.getAttribute?.("data-path"),
  ];
  for (const value of values) {
    const path = clean(value).replace(/^["']|["']$/g, "");
    if (path && !/[\\/]fakepath[\\/]/i.test(path)) return path;
  }
  return "";
}

function nativeProjectRootValue(container) {
  for (const element of nativeProjectRootElements(container)) {
    const value = pathFromNativeElement(element);
    if (value) return value;
  }
  return "";
}

export function hmbCollapseNativeProjectRootRows(container) {
  const shell = findNodeRoot(container);
  // Native collapsed footers can contain a third, opacity:0 widget copy in
  // addition to the regular visibility:hidden measurement row. Neither copy
  // may prune the live node's authoring column through a sibling PROJECT_ROOT.
  if (!shell || !hmbImageAssetMountIsVisible(container)) return 0;
  let collapsed = 0;
  nativeProjectRootHosts(container).forEach((host) => {
    let branch = host;
    while (
      branch?.parentElement
      && branch.parentElement !== shell
      && !branch.parentElement.contains?.(container)
      && !branch.parentElement.querySelector?.(".hmb-image-assets")
      && !clean(branch.parentElement.className).toLowerCase().includes("react-flow__")
    ) {
      branch = branch.parentElement;
    }
    if (!branch?.style || branch === shell || branch.contains?.(container)
        || branch.querySelector?.(".hmb-image-assets")) return;
    branch.dataset.hmbProjectRootLayoutCollapsed = "1";
    ["height", "min-height", "max-height", "margin", "padding", "border"].forEach((property) => {
      branch.style.setProperty(property, property.includes("height") ? "0px" : "0", "important");
    });
    branch.style.setProperty("flex", "0 0 0px", "important");
    branch.style.setProperty("overflow", "hidden", "important");
    collapsed += 1;
  });
  return collapsed;
}

function concealNativeProjectRootPicker(container) {
  if (!hmbImageAssetMountIsVisible(container)) return;
  hmbCollapseNativeProjectRootRows(container);
  nativeProjectRootHosts(container).forEach((host) => {
    host.setAttribute("aria-hidden", "true");
    host.style.setProperty("position", "absolute", "important");
    host.style.setProperty("left", "-100000px", "important");
    host.style.setProperty("width", "1px", "important");
    host.style.setProperty("height", "1px", "important");
    host.style.setProperty("overflow", "hidden", "important");
    host.style.setProperty("opacity", "0", "important");
    host.style.setProperty("pointer-events", "none", "important");
  });
}

function openNativeProjectRootPicker(container) {
  const controls = [];
  const seen = new Set();
  nativeProjectRootHosts(container).forEach((host) => {
    host.querySelectorAll?.('input[type="file"], button, [role="button"]').forEach((control) => {
      if (container.contains?.(control) || seen.has(control)) return;
      const description = clean(
        `${control.textContent || ""} ${control.getAttribute?.("title") || ""} ${control.getAttribute?.("aria-label") || ""}`,
      );
      if (/open\s+(?:file|folder|url)|reveal|explorer/i.test(description)) return;
      seen.add(control);
      controls.push(control);
    });
  });
  controls.sort((left, right) => {
    const score = (control) => {
      if (control.matches?.('input[type="file"]')) return 3;
      const label = clean(`${control.textContent || ""} ${control.getAttribute?.("title") || ""}`);
      return /browse|picker|select|choose|찾아|선택/i.test(label) ? 2 : 1;
    };
    return score(right) - score(left);
  });
  for (const control of controls) {
    if (control.matches?.('input[type="file"]') && typeof control.showPicker === "function") {
      try {
        control.showPicker();
        return true;
      } catch (_error) {}
    }
    if (typeof control.click === "function") {
      control.click();
      return true;
    }
  }
  return false;
}

function hmbInstallShotHierarchyDragging(dialog, doc) {
  let drag = null;
  let moved = false;
  const clampPosition = () => {
    if (!dialog.open) return;
    const view = doc.defaultView;
    let ancestorZoom = 1;
    for (let ancestor = dialog.parentElement; ancestor; ancestor = ancestor.parentElement) {
      const raw = String(view.getComputedStyle(ancestor).zoom || "1");
      const zoom = Number.parseFloat(raw) / (raw.endsWith("%") ? 100 : 1);
      if (Number.isFinite(zoom) && zoom > 0) ancestorZoom *= zoom;
    }
    // Chromium's top layer cancels ancestor zoom visually but can retain it in
    // hit testing. Counteract it explicitly so buttons and drag targets agree.
    dialog.style.zoom = String(1 / ancestorZoom);
    const rect = dialog.getBoundingClientRect();
    const sx = rect.width / dialog.offsetWidth || 1, sy = rect.height / dialog.offsetHeight || 1;
    const left = moved ? Math.min(Math.max(0, view.innerWidth - rect.width), rect.left) : (view.innerWidth - rect.width) / 2;
    const top = moved ? Math.min(Math.max(0, view.innerHeight - rect.height), rect.top) : (view.innerHeight - rect.height) / 2;
    // Native dialog auto margins use a zoomed body viewport in Chromium.
    // Position from the actual top-layer bounds so graph/body zoom cannot offset it.
    Object.assign(dialog.style, { margin: "0", right: "auto", bottom: "auto", left: `${Math.max(0, left) / sx}px`, top: `${Math.max(0, top) / sy}px` });
  };
  const stop = event => { if (!drag || (event && event.pointerId !== drag.id)) return; drag = null; };
  dialog.addEventListener("pointerdown", event => {
    if (event.button !== 0 || !event.target.closest?.("[data-hier-drag-handle]")
        || event.target.closest?.("button,input,select,a")) return;
    const rect = dialog.getBoundingClientRect();
    const sx = rect.width / dialog.offsetWidth || 1, sy = rect.height / dialog.offsetHeight || 1;
    moved = true;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top, width: rect.width, height: rect.height, sx, sy };
    Object.assign(dialog.style, { position: "fixed", margin: "0", right: "auto", bottom: "auto", left: `${rect.left / sx}px`, top: `${rect.top / sy}px` });
    dialog.setPointerCapture?.(event.pointerId);
    event.preventDefault(); event.stopPropagation();
  });
  dialog.addEventListener("pointermove", event => {
    if (!drag || drag.id !== event.pointerId) return;
    const view = doc.defaultView;
    const left = Math.max(0, Math.min(Math.max(0, view.innerWidth - drag.width), drag.left + event.clientX - drag.x));
    const top = Math.max(0, Math.min(Math.max(0, view.innerHeight - drag.height), drag.top + event.clientY - drag.y));
    dialog.style.left = `${left / drag.sx}px`; dialog.style.top = `${top / drag.sy}px`;
    event.preventDefault(); event.stopPropagation();
  });
  dialog.addEventListener("pointerup", stop);
  dialog.addEventListener("pointercancel", stop);
  dialog.addEventListener("lostpointercapture", stop);
  doc.defaultView?.addEventListener("resize", clampPosition);
  const dispose = () => doc.defaultView?.removeEventListener("resize", clampPosition);
  dispose.reposition = clampPosition;
  return dispose;
}

export function hmbOpenShotHierarchyDialog(container, state, focusedShotUuid, commit, addImageBash = null) {
  const root = container.querySelector?.(".hmb-image-assets");
  const doc = container.ownerDocument;
  if (!root || !doc?.createElement || container.__hmbHierarchyDialog) return false;
  const prior = hmbValidateHierarchyRouting(state.shot_hierarchy, state.shot_routing);
  const draft = prior.schema ? hmbNormalizeShotHierarchy(prior) : {
    schema: SHOT_HIERARCHY_SCHEMA, version: 1, binding_id: newImageAssetUuid(), revision: 1,
    project_identity: hierarchyProjectKey(state), channel_uuid: state.shot_routing.channel_uuid,
    cgt_account_id: null, members: [],
  };
  draft.revision = (prior.revision || 0) + 1;
  draft.project_identity = hierarchyProjectKey(state);
  const initialGeneration = state.shot_routing.generation;
  const dialog = doc.createElement("dialog");
  dialog.className = "shot-hierarchy-dialog";
  dialog.setAttribute("aria-labelledby", "hmb-hierarchy-title");
  dialog.setAttribute("data-shot-hierarchy-dialog", "");
  container.__hmbHierarchyDialog = dialog;
  const cgtSession = newImageAssetUuid();
  let cgtState = { status: "not_requested", tasks: [], projects: [] };
  let cgtRequest = "";
  let cgtTimer = null;
  let confirmingCgt = false;
  let hierarchyClosed = false;
  let cgtQuery = "";
  let cgtPage = 0;
  let cgtEpisode = "";
  let cgtProjectId = "";
  let cgtProjects = [];
  let disposePositioning = null;
  const sendCgt = (operation, command = null) => {
    if (operation === "cgt_confirm" && !hierarchyProjectKey(state)) return false;
    const bridge = imageAssetThumbnailBridgeRegistry()?.get(imageAssetThumbnailRuntimeId(state));
    if (typeof bridge?.dispatch !== "function") return false;
    const requestId = newImageAssetUuid();
    const request = { schema: "hmb-image-asset-thumbnail-bridge", version: 1, operation, phase: "request",
      runtime_instance_id: imageAssetThumbnailRuntimeId(state), session_id: cgtSession, request_id: requestId,
      project_identity: hierarchyProjectKey(state) };
    const selectedProject = operation === "cgt_confirm" ? command?.binding?.cgt_scope?.project_id : cgtProjectId;
    if (selectedProject) request.cgt_project_id = selectedProject;
    if (command) request.hierarchy_request = command;
    if (operation !== "cgt_cancel") {
      cgtRequest = requestId;
      if (cgtTimer !== null) clearTimeout(cgtTimer);
      cgtTimer = setTimeout(() => {
        cgtRequest = ""; confirmingCgt = false; cgtState = { status: "TIMEOUT", tasks: [] };
        sendCgt("cgt_cancel"); renderDraft(); notice("CGT 응답 시간이 초과됐습니다. 기존 샷은 유지됩니다. 새로고침 후 다시 확인하세요.");
      }, 45000);
    }
    try {
      const delivery = bridge.dispatch(request);
      Promise.resolve(delivery).catch(() => {
        if (cgtRequest !== requestId) return;
        cgtRequest = ""; confirmingCgt = false;
        if (cgtTimer !== null) clearTimeout(cgtTimer);
        cgtState = { status: "SDK_UNAVAILABLE", tasks: [] }; renderDraft();
      });
      return true;
    } catch (error) {
      cgtRequest = ""; confirmingCgt = false;
      if (cgtTimer !== null) clearTimeout(cgtTimer);
      return false;
    }
  };
  const close = () => {
    if (confirmingCgt || hierarchyClosed) return;
    hierarchyClosed = true;
    if (cgtTimer !== null) clearTimeout(cgtTimer);
    disposePositioning?.();
    sendCgt("cgt_cancel");
    delete container.__hmbHierarchyReceive;
    delete container.__hmbHierarchyDispose;
    dialog.close?.(); dialog.remove();
    if (container.__hmbHierarchyDialog === dialog) delete container.__hmbHierarchyDialog;
    container.querySelector?.("[data-shot-add]")?.focus?.({ preventScroll: true });
  };
  const notice = message => { dialog.querySelector("[data-hier-message]").textContent = message; };
  const changed = action => {
    try { action(); renderDraft(); } catch (error) { notice(error.message); }
  };
  const makeRequest = candidate => ({ schema: SHOT_HIERARCHY_EDIT_SCHEMA, version: 1, expected_generation: initialGeneration,
    expected_binding_revision: prior.revision || 0,
    removed_member_ids: (prior.members || []).filter(item => !candidate.members.some(row => row.member_id === item.member_id)).map(item => item.member_id),
    binding: hmbNormalizeShotHierarchy(candidate) });
  const renderCgt = () => {
    const panel = dialog.querySelector("[data-hier-cgt]");
    if (!panel) return;
    const messages = { not_requested: "CGT 연결 확인 필요 · 새로고침으로 본인 작업을 확인하세요.", loading: "CGT 본인 작업 조회 중…",
      LOGIN_REQUIRED: "CGT 앱에서 로그인 후 새로고침하세요.", TLS_REJECTED: "CGT 인증서 검증에 실패했습니다. 관리자에게 인증서 상태를 확인하세요.",
      SELECT_GP_PROJECT: "먼저 이미지 라이브러리의 프로젝트를 선택하세요.", PROJECT_UNAVAILABLE: "선택한 GP 프로젝트의 CGT 접근 권한을 확인하세요.",
      SOURCE_CHANGED: "CGT 계정·프로젝트·작업이 변경되었습니다. 새로고침 후 다시 선택하세요.",
      ACCOUNT_CHANGED: "CGT 로그인 계정이 기존 연결과 다릅니다. 기존 연결은 유지됩니다. 올바른 계정으로 로그인 후 다시 확인하세요.",
      SDK_UNAVAILABLE: "CGT 앱과 설치된 Python SDK 연결을 확인한 뒤 새로고침하세요.", TIMEOUT: "CGT 응답 시간 초과 · 새로고침 후 다시 확인하세요." };
    const ready = cgtState.status === "ready";
    const projects = cgtProjects;
    const project = cgtState.project || null;
    const canBind = !!project && !!hierarchyProjectKey(state) && cgtState.can_bind !== false;
    const imageBashTarget = dialog.querySelector("[data-hier-slot]")?.value === "image_bash";
    const episodeOf = row => {
      if (clean(row.episode)) return clean(row.episode);
      try { return hmbHierarchyParseName(row.source_name).episode || "__unassigned__"; }
      catch { return "__unassigned__"; }
    };
    const episodes = ready ? [...new Set(cgtState.tasks.map(episodeOf))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })) : [];
    if (ready && cgtEpisode && !episodes.includes(cgtEpisode)) cgtEpisode = "";
    const matching = ready ? cgtState.tasks.filter(row => (!cgtEpisode || episodeOf(row) === cgtEpisode)
      && (!cgtQuery || `${row.source_name} ${row.status}`.toLowerCase().includes(cgtQuery.toLowerCase()))) : [];
    cgtPage = Math.min(cgtPage, Math.max(0, Math.ceil(matching.length / 50) - 1));
    const visible = matching.slice(cgtPage * 50, (cgtPage + 1) * 50);
    const selected = new Set(draft.members.filter(row => row.origin === "cgt").map(row => row.cgt_task_id));
    panel.innerHTML = `<div class="hier-tools hier-project-tools"><label>프로젝트<select data-hier-cgt-project aria-label="CGT 프로젝트" ${!projects.length || cgtRequest || confirmingCgt ? "disabled" : ""}><option value="" ${!project ? "selected" : ""}>프로젝트 선택 필요</option>${projects.map(row => `<option value="${escapeHtml(row.id)}" ${row.id === project?.id ? "selected" : ""}>${escapeHtml(row.name)}</option>`).join("")}${project && !projects.some(row => row.id === project.id) ? `<option value="${escapeHtml(project.id)}" selected>${escapeHtml(project.name)}</option>` : ""}</select></label><label>에피소드<select data-hier-cgt-episode aria-label="CGT 에피소드" ${!ready || !project || !episodes.length || cgtRequest || confirmingCgt ? "disabled" : ""}><option value="">전체 에피소드</option>${episodes.map(episode => `<option value="${escapeHtml(episode)}" ${episode === cgtEpisode ? "selected" : ""}>${escapeHtml(episode === "__unassigned__" ? "에피소드 미지정" : episode)}</option>`).join("")}</select></label><button type="button" data-hier-cgt-refresh ${cgtRequest || confirmingCgt ? "disabled" : ""}>새로고침</button></div>
      ${ready && cgtState.account ? `<small data-hier-cgt-account>${escapeHtml(cgtState.account)} / ${escapeHtml(cgtState.account_name)} · AI_Shot · ${cgtState.tasks.length}건${cgtState.truncated ? " (추가 작업 있음)" : ""}</small>` : ""}
      ${ready && project ? `<label class="hier-query">샷 · 상태 검색<input data-hier-cgt-query value="${escapeHtml(cgtQuery)}" autocomplete="off"></label>` : ""}
      <div class="hier-cgt-scroll" data-hier-cgt-scroll><table class="hier-table"><thead><tr><th>Shot</th><th>Artist</th><th>Task status</th><th></th></tr></thead><tbody>${visible.map(row => `<tr><td>${escapeHtml(row.source_name)}</td><td>${escapeHtml(row.artist)}</td><td>${escapeHtml(row.status)}</td><td><button type="button" data-hier-cgt-add="${escapeHtml(row.task_id)}" ${selected.has(row.task_id) || confirmingCgt || !canBind || imageBashTarget ? "disabled" : ""}>${selected.has(row.task_id) ? "선택됨" : "선택 추가"}</button></td></tr>`).join("")}</tbody></table></div>
      ${matching.length > 50 ? `<div class="hier-tools"><button type="button" data-hier-cgt-prev ${cgtPage ? "" : "disabled"}>이전</button><small>${cgtPage + 1} / ${Math.ceil(matching.length / 50)}</small><button type="button" data-hier-cgt-next ${(cgtPage + 1) * 50 < matching.length ? "" : "disabled"}>다음</button></div>` : ""}
      <p class="hier-offline" data-hier-cgt-status>${escapeHtml(ready ? !project ? "CGT 프로젝트를 선택하세요." : !canBind ? !hierarchyProjectKey(state) ? "먼저 이미지 라이브러리의 프로젝트를 선택하세요. CGT 작업은 조회만 할 수 있습니다." : "현재 라이브러리와 다른 CGT 프로젝트입니다. 작업 조회만 가능하며 샷은 연결하지 않습니다." : cgtState.tasks.length ? "CGT 원본의 본인 배정 작업만 표시합니다." : "본인에게 배정된 AI_Shot 작업이 없습니다." : messages[cgtState.status] || "CGT 작업을 확인할 수 없습니다. 새로고침하세요.")}</p>`;
    const loadCatalog = () => {
      cgtState = { ...cgtState, status: "loading", tasks: [] };
      if (!sendCgt("cgt_catalog")) cgtState = { ...cgtState, status: "SDK_UNAVAILABLE", tasks: [] };
      renderCgt();
    };
    panel.querySelector("[data-hier-cgt-refresh]").addEventListener("click", loadCatalog);
    panel.querySelector("[data-hier-cgt-project]").addEventListener("change", event => {
      cgtProjectId = event.target.value;
      cgtQuery = ""; cgtPage = 0; cgtEpisode = "";
      loadCatalog();
    });
    panel.querySelector("[data-hier-cgt-episode]").addEventListener("change", event => {
      cgtEpisode = event.target.value; cgtPage = 0;
      renderCgt();
      panel.querySelector("[data-hier-cgt-episode]")?.focus({ preventScroll: true });
    });
    panel.querySelector("[data-hier-cgt-query]")?.addEventListener("input", event => {
      const start = event.target.selectionStart, end = event.target.selectionEnd;
      cgtQuery = event.target.value; cgtPage = 0; renderCgt();
      const input = panel.querySelector("[data-hier-cgt-query]"); input?.focus({ preventScroll: true }); input?.setSelectionRange(start, end);
    });
    panel.querySelector("[data-hier-cgt-prev]")?.addEventListener("click", () => { cgtPage -= 1; renderCgt(); });
    panel.querySelector("[data-hier-cgt-next]")?.addEventListener("click", () => { cgtPage += 1; renderCgt(); });
    panel.querySelectorAll("[data-hier-cgt-add]").forEach(button => button.addEventListener("click", () => changed(() => {
      if (cgtState.status !== "ready" || confirmingCgt) throw new Error("CGT 본인 작업을 먼저 확인하세요.");
      if (!hierarchyProjectKey(state) || !cgtState.project || cgtState.can_bind === false) throw new Error("현재 라이브러리 프로젝트의 CGT 작업만 연결할 수 있습니다.");
      const task = cgtState.tasks.find(row => row.task_id === button.dataset.hierCgtAdd);
      if (!task) throw new Error("CGT 작업이 변경되었습니다.");
      const scope = { origin: cgtState.origin, project_id: cgtState.project.id, project_db: cgtState.project.database,
        module: "shot", module_type: "task", pipeline_id: task.pipeline_id, account_id: cgtState.account_id };
      if (draft.members.some(row => row.origin === "cgt") && Object.keys(scope).some(key => draft.cgt_scope?.[key] !== scope[key])) throw new Error("다른 CGT 계정·프로젝트·공정은 함께 연결할 수 없습니다.");
      const parsed = hmbHierarchyParseName(task.source_name);
      const slot = dialog.querySelector("[data-hier-slot]").value;
      if (slot === "image_bash") throw new Error("HMBImageBash는 아래 추가 버튼으로 추가하세요.");
      const row = { member_id: `cgt:${task.task_id.toLowerCase()}`, origin: "cgt", manual_uuid: newImageAssetUuid(),
        source_name: parsed.source_name, canonical_name: parsed.canonical_name, gp_shot_uuid: slot === "new" ? newImageAssetUuid() : slot,
        parent_id: null, selection_order: draft.members.length + 1, cgt_task_id: task.task_id, cgt_identity: task.identity, artist: task.artist, status: task.status };
      const next = { ...draft, version: 2, cgt_scope: scope, cgt_account_id: cgtState.account_id,
        members: [...draft.members.map(item => ({ ...item, cgt_identity: item.cgt_identity || null })), row] };
      hmbApplyShotHierarchyEdit(state, makeRequest(next)); Object.assign(draft, next);
    })));
    disposePositioning?.reposition?.();
  };
  container.__hmbHierarchyReceive = response => {
    if (response?.session_id !== cgtSession || response.request_id !== cgtRequest || response.project_identity !== hierarchyProjectKey(state)
        || response.runtime_instance_id !== imageAssetThumbnailRuntimeId(state)) return false;
    if (cgtTimer !== null) clearTimeout(cgtTimer);
    cgtRequest = "";
    if (response.operation === "cgt_confirm") {
      confirmingCgt = false;
      if (response.outcome === "committed") { close(); return true; }
      cgtState = { status: response.state?.status || "SOURCE_CHANGED", tasks: [] }; renderDraft();
      notice("CGT 검증 또는 현재 샷 구성이 변경되어 적용하지 않았습니다. 기존 샷은 유지됩니다.");
      return true;
    }
    cgtState = response.state || { status: "SDK_UNAVAILABLE", tasks: [] };
    if (cgtState.status === "ready") {
      cgtProjectId = cgtState.project?.id || "";
      cgtProjects = Array.isArray(cgtState.projects) ? cgtState.projects : [];
    }
    if (["ACCOUNT_CHANGED", "LOGIN_REQUIRED", "SOURCE_CHANGED"].includes(cgtState.status)
        || (cgtState.status === "ready" && draft.cgt_account_id && draft.cgt_account_id !== cgtState.account_id)) {
      if (cgtState.status === "ready") cgtState = { status: "ACCOUNT_CHANGED", tasks: [] };
      cgtProjects = []; cgtProjectId = "";
    }
    renderCgt(); return true;
  };
  const renderNamePreview = () => {
    const preview = dialog.querySelector("[data-hier-name-preview]");
    if (!preview) return;
    const names = hmbHierarchyDerivedNames(draft);
    preview.innerHTML = `<h3>예상 네이밍</h3><div class="hier-name-values" data-hier-name-values>${draft.members.map(row => `<small class="hier-output" title="${escapeHtml(names[row.gp_shot_uuid])}">${escapeHtml(names[row.gp_shot_uuid])}</small>`).join("") || "<small>샷을 선택하면 예상 실행명이 표시됩니다.</small>"}</div>`;
  };
  const renderDraft = (manualDraft = null) => {
    const scrollPositions = [".hier-body", "[data-hier-cgt-scroll]", "[data-hier-selected-scroll]"].map(selector => [selector, dialog.querySelector(selector)?.scrollTop || 0]);
    const used = new Set(draft.members.map(row => row.gp_shot_uuid));
    const roots = draft.members.filter(row => row.parent_id === null);
    const depths = new Map();
    const visit = (row, depth) => {
      depths.set(row.member_id, depth);
      return [row, ...draft.members.filter(child => child.parent_id === row.member_id).flatMap(child => visit(child, depth + 1))];
    };
    const ordered = roots.flatMap(row => visit(row, 0));
    const slotNumber = row => state.shot_routing.shots.find(shot => shot.shot_uuid === row.gp_shot_uuid)?.number
      || state.shot_routing.shots.length + draft.members.filter(item => !state.shot_routing.shots.some(shot => shot.shot_uuid === item.gp_shot_uuid)).indexOf(row) + 1;
    const canParent = (candidate, row) => {
      let current = candidate;
      const seen = new Set();
      while (current) {
        if (current.member_id === row.member_id || seen.has(current.member_id)) return false;
        seen.add(current.member_id);
        current = draft.members.find(item => item.member_id === current.parent_id);
      }
      return true;
    };
    const representativeCount = draft.members.filter(row => row.parent_id === null
      || draft.members.some(child => child.parent_id === row.member_id)).length;
    const sameBase = row => {
      const p = hmbHierarchyParseName(row.source_name);
      return p.shot && draft.members.some(other => {
        const q = hmbHierarchyParseName(other.source_name);
        return other.member_id !== row.member_id && q.episode === p.episode && q.shot === p.shot;
      });
    };
    dialog.innerHTML = `<style>
      .shot-hierarchy-dialog{box-sizing:border-box;position:fixed;inset:0;margin:auto;transform:none;translate:none;width:min(1000px,94vw);max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px);display:flex;flex-direction:column;padding:0;border:1px solid #9f4a79;border-radius:12px;background:#0b1020;color:#e6edf7;font:12px/1.5 system-ui,sans-serif;box-shadow:0 16px 80px #000a;overflow:hidden}
      .shot-hierarchy-dialog::backdrop{background:#050814b8}.shot-hierarchy-dialog *{box-sizing:border-box}.shot-hierarchy-dialog header,.shot-hierarchy-dialog footer{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px;background:linear-gradient(100deg,#402039,#101626 70%)}
      .shot-hierarchy-dialog h2{margin:0;font-size:15px}.shot-hierarchy-dialog h3{margin:0 0 10px;font-size:13px}.shot-hierarchy-dialog p{margin:6px 0}.shot-hierarchy-dialog small{display:block;color:#9fb0c8}.shot-hierarchy-dialog button,.shot-hierarchy-dialog input,.shot-hierarchy-dialog select{font:inherit;color:inherit;background:#090e1a;border:1px solid #40506a;border-radius:6px;padding:7px 9px;min-height:32px;max-width:100%}.shot-hierarchy-dialog button{cursor:pointer}.shot-hierarchy-dialog button:disabled{opacity:.4;cursor:default}.shot-hierarchy-dialog :focus-visible{outline:2px solid #f472b6;outline-offset:2px}.shot-hierarchy-dialog .hier-primary{background:#88305f;border-color:#f472b6}.shot-hierarchy-dialog .hier-body{padding:14px 18px;overflow:auto;min-height:0}.shot-hierarchy-dialog header,.shot-hierarchy-dialog footer{flex-shrink:0}.shot-hierarchy-dialog .hier-split{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:14px;align-items:start}.shot-hierarchy-dialog .hier-pane{min-width:0;border:1px solid #354058;border-radius:8px;padding:12px;background:#0e1525}.shot-hierarchy-dialog .hier-row{margin:9px 0;padding:10px;border:1px solid var(--shot-accent);border-radius:7px;background:linear-gradient(100deg,rgba(var(--shot-rgb),.18),#0b1020 90%)}.shot-hierarchy-dialog .hier-child{margin-left:20px}.shot-hierarchy-dialog .hier-row input{width:100%;margin:5px 0}.shot-hierarchy-dialog .hier-tools{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.shot-hierarchy-dialog .hier-tools label{flex:1;min-width:130px}.shot-hierarchy-dialog .hier-tools select{width:100%}.shot-hierarchy-dialog .hier-project-tools{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end}.shot-hierarchy-dialog .hier-project-tools label{display:grid;gap:4px;min-width:0}.shot-hierarchy-dialog .hier-project-tools button{white-space:nowrap}.shot-hierarchy-dialog .hier-query{display:grid;gap:4px;margin:10px 0}.shot-hierarchy-dialog .hier-query input{width:100%}.shot-hierarchy-dialog .hier-cgt-scroll{max-height:min(46vh,420px);overflow:auto;overscroll-behavior:contain}.shot-hierarchy-dialog .hier-cgt-scroll thead{position:sticky;top:0;background:#0e1525;z-index:1}.shot-hierarchy-dialog .hier-table td{padding:6px;vertical-align:top;overflow-wrap:anywhere}.shot-hierarchy-dialog .hier-table td:last-child{width:70px}.shot-hierarchy-dialog .hier-selection-list{max-height:min(44vh,420px);overflow:auto;overscroll-behavior:contain}.shot-hierarchy-dialog .hier-name-preview{margin:10px 0;padding:10px;border:1px solid #354058;border-radius:7px;background:#0b1020}.shot-hierarchy-dialog .hier-name-preview h3{margin-bottom:4px}.shot-hierarchy-dialog .hier-manual label{display:grid;gap:4px}.shot-hierarchy-dialog .hier-manual input,.shot-hierarchy-dialog .hier-manual select{width:100%}.shot-hierarchy-dialog .hier-manual{display:grid;gap:8px;margin-top:18px;padding-top:12px;border-top:1px solid #354058}.shot-hierarchy-dialog .hier-table{width:100%;border-collapse:collapse}.shot-hierarchy-dialog th{padding:6px;text-align:left;border-bottom:1px solid #354058}.shot-hierarchy-dialog .hier-offline{padding:12px 4px;color:#e6bd85}.shot-hierarchy-dialog [data-hier-message]{min-height:20px;color:#fda4af;white-space:pre-wrap}.shot-hierarchy-dialog .hier-output{overflow-wrap:anywhere;white-space:pre-wrap}.shot-hierarchy-dialog footer{flex-wrap:wrap}.shot-hierarchy-dialog .hier-actions{display:flex;gap:8px;margin-left:auto}@media(max-width:700px){.shot-hierarchy-dialog .hier-split{grid-template-columns:1fr}.shot-hierarchy-dialog .hier-child{margin-left:10px}}
      .shot-hierarchy-dialog [data-hier-drag-handle]{cursor:move;touch-action:none;user-select:none}.shot-hierarchy-dialog [data-hier-drag-handle] button{cursor:pointer}
      .shot-hierarchy-dialog .hier-name-tools{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px;align-items:end}.shot-hierarchy-dialog .hier-name-tools label{display:grid;gap:4px;min-width:0}.shot-hierarchy-dialog .hier-name-tools input{margin:0;min-width:0}.shot-hierarchy-dialog .hier-name-tools button{white-space:nowrap}.shot-hierarchy-dialog .hier-name-preview{display:flex;align-items:center;gap:10px;min-width:0;overflow:hidden}.shot-hierarchy-dialog .hier-name-preview h3{flex:0 0 auto;margin:0;white-space:nowrap}.shot-hierarchy-dialog .hier-name-values{display:flex;align-items:center;gap:12px;min-width:0;overflow-x:auto;white-space:nowrap;overscroll-behavior:contain}.shot-hierarchy-dialog .hier-name-values small{flex:0 0 auto;white-space:nowrap}
      .shot-hierarchy-dialog{height:min(682px,calc(100dvh - 24px))}.shot-hierarchy-dialog .hier-body{flex:1}.shot-hierarchy-dialog [data-hier-message]:empty,.shot-hierarchy-dialog [hidden],.shot-hierarchy-dialog .hier-selection-list:empty{display:none!important}.shot-hierarchy-dialog .hier-offline{margin:6px 0 0;padding:6px 0;line-height:1.4}.shot-hierarchy-dialog .hier-name-preview{margin:8px 0 0;padding:8px 10px}.shot-hierarchy-dialog .hier-selection-list:not(:empty){margin-top:8px}.shot-hierarchy-dialog .hier-manual{gap:6px;margin-top:10px;padding-top:10px}.shot-hierarchy-dialog .hier-manual h3{margin:0}.shot-hierarchy-dialog .hier-selection-list:empty+.hier-manual{margin-top:8px;padding-top:8px}.shot-hierarchy-dialog .hier-query{margin:8px 0}@media(max-width:700px){.shot-hierarchy-dialog{height:calc(100dvh - 24px)}}
      .shot-hierarchy-dialog .hier-project-tools{grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) auto}.shot-hierarchy-dialog .hier-project-tools select{min-width:0}.shot-hierarchy-dialog .hier-row-head{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:8px}.shot-hierarchy-dialog .hier-row-head b{white-space:nowrap}.shot-hierarchy-dialog .hier-row-head select{width:100%;min-width:0}.shot-hierarchy-dialog .hier-child{margin-left:calc(var(--hier-depth,1) * 12px)}
    </style><header data-hier-drag-handle title="제목 표시줄을 드래그하여 창 이동"><div><h2 id="hmb-hierarchy-title">CGT 샷 선택 · 묶음 구성</h2></div><button type="button" data-hier-cancel aria-label="취소하고 닫기">×</button></header>
    <div class="hier-body"><p data-hier-message role="status" aria-live="polite"></p><div class="hier-split">
    <section class="hier-pane" data-hier-source-pane><h3>CGT 본인 작업 목록</h3><div data-hier-cgt></div></section>
    <section class="hier-pane" data-hier-selected-pane><h3>선택한 샷 · 대표 / 하위 (${draft.members.length}/5)</h3><div class="hier-name-preview" data-hier-name-preview></div><div class="hier-selection-list" data-hier-selected-scroll>${ordered.map(row => {
      const number = slotNumber(row);
      const palette = hmbImageAssetShotPalette(number);
      const parts = hmbHierarchyParseName(row.source_name);
      const hasChildren = draft.members.some(child => child.parent_id === row.member_id);
      const parentOptions = draft.members.filter(candidate => canParent(candidate, row));
      const role = row.parent_id ? hasChildren ? "하위 · 대표" : "하위" : "대표";
      return `<article class="hier-row ${row.parent_id ? "hier-child" : ""}" data-hier-member="${row.manual_uuid}" style="--shot-accent:${palette.accent};--shot-rgb:${palette.rgb};--hier-depth:${depths.get(row.member_id) || 0}"><div class="hier-row-head"><b>${String(number).padStart(2, "0")} · ${role}</b><select data-hier-parent="${row.manual_uuid}" aria-label="${escapeHtml(row.source_name)} 대표·하위 선택" title="하위 샷도 다른 샷의 대표로 선택할 수 있습니다"><option value="" ${row.parent_id === null ? "selected" : ""}>독립 대표</option>${parentOptions.map(parent => `<option value="${escapeHtml(parent.member_id)}" ${parent.member_id === row.parent_id ? "selected" : ""}>${String(slotNumber(parent)).padStart(2, "0")} · ${escapeHtml(parent.canonical_name)}의 하위</option>`).join("")}</select></div><small>${row.origin === "cgt" ? `CGT · ${escapeHtml(row.artist)} · ${escapeHtml(row.status)}` : "수동 · CGT 미연결"}</small>${parts.shot ? `<small>에피소드 ${parts.episode} · 샷 ${parts.shot} · 분리컷 ${parts.split_cut}${sameBase(row) ? " · 같은 원본 샷의 분리컷" : ""}</small>` : ""}<div class="hier-name-tools" data-hier-name-tools><label>정식 이름<input data-hier-name="${row.manual_uuid}" value="${escapeHtml(row.source_name)}" autocomplete="off" ${row.origin === "cgt" ? "readonly" : ""}></label><button type="button" data-hier-remove="${row.manual_uuid}" ${hasChildren ? "disabled title=\"하위를 먼저 선택 해제하세요\"" : ""}>선택 해제</button></div></article>`;
    }).join("")}</div>
    <div class="hier-manual"><h3 data-hier-manual-title>수동 샷 추가</h3><label data-hier-manual-name-field>샷 이름<input data-hier-manual-name placeholder="정식 샷 코드 또는 수동 이름" autocomplete="off"></label><label>연결할 슬롯<select data-hier-slot><option value="new">새 독립 샷 추가</option>${state.shot_routing.shots.map(shot => `<option value="${shot.shot_uuid}" ${used.has(shot.shot_uuid) ? "disabled" : ""}>${String(shot.number).padStart(2, "0")} · ${escapeHtml(shot.name)} (입력·연결 유지)</option>`).join("")}${typeof addImageBash === "function" ? '<option value="image_bash">HMBImageBash</option>' : ""}</select></label><small data-hier-slot-help>기존 슬롯을 선택하면 UUID·미디어·설정·결과를 보존하고 이름만 적용합니다.</small><button type="button" data-hier-add>수동 추가</button></div></section></div></div>
    <footer><span>${representativeCount}개 대표 · ${draft.members.length - roots.length}개 하위</span><div class="hier-actions"><button type="button" data-hier-cancel>취소</button><button type="button" class="hier-primary" data-hier-confirm>선택 확정</button></div></footer>`;
    dialog.querySelectorAll("[data-hier-cancel]").forEach(button => button.addEventListener("click", close));
    const add = () => {
      if (dialog.querySelector("[data-hier-slot]").value === "image_bash") {
        if (typeof addImageBash !== "function") return;
        if (JSON.stringify(draft.members) !== JSON.stringify(prior.members || [])) {
          notice("샷 선택 변경을 먼저 확정한 뒤 HMBImageBash를 추가하세요. 기존 샷은 유지됩니다."); return;
        }
        if (container.__hmbNativeUiContract?.props?.disabled) return;
        close(); addImageBash(); return;
      }
      changed(() => {
        const parsed = hmbHierarchyParseName(dialog.querySelector("[data-hier-manual-name]").value);
        const slot = dialog.querySelector("[data-hier-slot]").value;
        const id = newImageAssetUuid();
        const row = { member_id: `manual:${id}`, origin: "manual", manual_uuid: id, source_name: parsed.source_name, canonical_name: parsed.canonical_name,
          gp_shot_uuid: slot === "new" ? newImageAssetUuid() : slot, parent_id: null, selection_order: draft.members.length + 1, cgt_task_id: null, artist: null, status: null };
        if (draft.version === 2) row.cgt_identity = null;
        const next = { ...draft, members: [...draft.members, row] };
        const request = { schema: SHOT_HIERARCHY_EDIT_SCHEMA, version: 1, expected_generation: initialGeneration, expected_binding_revision: prior.revision || 0,
          removed_member_ids: (prior.members || []).filter(item => !next.members.some(row => row.member_id === item.member_id)).map(item => item.member_id), binding: next };
        hmbApplyShotHierarchyEdit(state, request);
        draft.members = next.members;
      });
    };
    dialog.querySelector("[data-hier-add]").addEventListener("click", add);
    const syncManualSlot = () => {
      const imageBash = dialog.querySelector("[data-hier-slot]").value === "image_bash";
      dialog.querySelector("[data-hier-manual-name-field]").hidden = imageBash;
      dialog.querySelector("[data-hier-manual-name]").disabled = imageBash;
      dialog.querySelector("[data-hier-manual-title]").textContent = imageBash ? "HMBImageBash 추가" : "수동 샷 추가";
      dialog.querySelector("[data-hier-add]").textContent = imageBash ? "HMBImageBash 추가" : "수동 추가";
      dialog.querySelector("[data-hier-slot-help]").textContent = imageBash
        ? "Shot 1~5와 별도의 이미지 작업 공간을 추가합니다."
        : "기존 슬롯을 선택하면 UUID·미디어·설정·결과를 보존하고 이름만 적용합니다.";
    };
    if (manualDraft) {
      dialog.querySelector("[data-hier-manual-name]").value = manualDraft.name;
      dialog.querySelector("[data-hier-slot]").value = manualDraft.slot;
      syncManualSlot();
    }
    dialog.querySelector("[data-hier-slot]").addEventListener("change", () => {
      notice("");
      syncManualSlot();
      renderCgt();
    });
    dialog.querySelector("[data-hier-manual-name]").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); add(); }
    });
    dialog.querySelectorAll("[data-hier-name]").forEach(input => input.addEventListener("change", () => {
      try {
        const row = draft.members.find(item => item.manual_uuid === input.dataset.hierName);
        if (row.origin !== "manual") throw new Error("CGT에서 선택한 샷의 이름은 변경할 수 없습니다.");
        const parsed = hmbHierarchyParseName(input.value);
        const candidate = { ...draft, members: draft.members.map(item => item === row ? { ...item, source_name: parsed.source_name, canonical_name: parsed.canonical_name } : item) };
        hmbNormalizeShotHierarchy(candidate); draft.members = candidate.members;
        // Keep the clicked action alive: blur/change occurs before its click.
        // Replacing the dialog here used to swallow Confirm's first click.
        renderNamePreview();
        notice("");
      } catch (error) { notice(error.message); }
    }));
    dialog.querySelectorAll("[data-hier-parent]").forEach(select => select.addEventListener("change", () => {
      try {
        if (confirmingCgt || container.__hmbNativeUiContract?.props?.disabled) throw new Error("Griptape에서 편집이 잠겨 있습니다.");
        const candidate = { ...draft, members: draft.members.map(row => row.manual_uuid === select.dataset.hierParent
          ? { ...row, parent_id: select.value || null } : row) };
        hmbApplyShotHierarchyEdit(state, makeRequest(candidate));
        draft.members = candidate.members;
        const key = select.dataset.hierParent;
        renderDraft({ name: dialog.querySelector("[data-hier-manual-name]").value,
          slot: dialog.querySelector("[data-hier-slot]").value });
        dialog.querySelector(`[data-hier-parent="${key}"]`)?.focus({ preventScroll: true });
      } catch (error) {
        select.value = draft.members.find(row => row.manual_uuid === select.dataset.hierParent)?.parent_id || "";
        notice(error.message);
      }
    }));
    dialog.querySelectorAll("[data-hier-remove]").forEach(button => button.addEventListener("click", () => changed(() => {
      const row = draft.members.find(item => item.manual_uuid === button.dataset.hierRemove);
      if (draft.members.some(child => child.parent_id === row.member_id)) throw new Error("하위를 먼저 선택 해제하세요.");
      draft.members = draft.members.filter(item => item !== row).map((item, i) => ({ ...item, selection_order: i + 1 }));
      if (draft.version === 2 && !draft.members.some(item => item.origin === "cgt")) { draft.cgt_scope = null; draft.cgt_account_id = null; }
    })));
    dialog.querySelector("[data-hier-confirm]").addEventListener("click", () => {
      try {
        if (container.__hmbNativeUiContract?.props?.disabled) throw new Error("Griptape에서 편집이 잠겨 있습니다.");
        const names = new Map([...dialog.querySelectorAll("[data-hier-name]")].map(input => [input.dataset.hierName, hmbHierarchyParseName(input.value)]));
        const candidate = { ...draft, members: draft.members.map(row => ({ ...row,
          source_name: names.get(row.manual_uuid).source_name, canonical_name: names.get(row.manual_uuid).canonical_name })) };
        const request = { schema: SHOT_HIERARCHY_EDIT_SCHEMA, version: 1, expected_generation: initialGeneration, expected_binding_revision: prior.revision || 0,
          removed_member_ids: (prior.members || []).filter(item => !candidate.members.some(row => row.member_id === item.member_id)).map(item => item.member_id), binding: hmbNormalizeShotHierarchy(candidate) };
        // Validate against current authority again; background changes cannot be
        // overwritten by an older dialog. No render or CGT request is made.
        hmbApplyShotHierarchyEdit(container.__hmbImageAssetLatestState || state, request);
        if (candidate.members.some(row => row.origin === "cgt")) {
          confirmingCgt = true;
          if (!sendCgt("cgt_confirm", request)) { confirmingCgt = false; throw new Error("CGT 확인 연결이 준비되지 않았습니다. 새로고침하세요."); }
          renderDraft(); notice("CGT 계정·본인 배정·샷 구성을 확인하고 있습니다…");
          return;
        }
        close(); commit(request);
      } catch (error) { notice(error.message); }
    });
    renderCgt();
    renderNamePreview();
    scrollPositions.forEach(([selector, top]) => { const target = dialog.querySelector(selector); if (target) target.scrollTop = top; });
    disposePositioning?.reposition?.();
    if (confirmingCgt) dialog.querySelectorAll("button,input,select").forEach(control => { control.disabled = true; });
  };
  dialog.addEventListener("cancel", event => { event.preventDefault(); close(); });
  container.__hmbHierarchyDispose = () => { confirmingCgt = false; close(); };
  dialog.addEventListener("keydown", event => event.stopPropagation());
  disposePositioning = hmbInstallShotHierarchyDragging(dialog, doc);
  try {
    // The modal belongs to the viewport, outside the graph node's zoom and transform.
    renderDraft(); (doc.body || root).appendChild(dialog); dialog.showModal();
    dialog.querySelector("[data-hier-manual-name]").focus({ preventScroll: true });
    cgtState = { ...cgtState, status: "loading", tasks: [] };
    if (!sendCgt("cgt_catalog")) cgtState = { ...cgtState, status: "SDK_UNAVAILABLE", tasks: [] };
    renderCgt();
  } catch (error) { close(); throw error; }
  return true;
}

function installEvents(container, state, props, remount, listeners) {
  const on = (target, type, handler, options) => {
    if (!target?.addEventListener) return;
    target.addEventListener(type, handler, options);
    listeners.push([target, type, handler, options]);
  };

  const stopNodeDeleteShortcut = (event) => {
    if (event?.target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]")) return;
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  on(container, "keydown", stopNodeDeleteShortcut);
  const stopSelectedNodeDeleteShortcut = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  if (typeof window !== "undefined") on(window, "keydown", stopSelectedNodeDeleteShortcut, true);
  const stopInteriorNodeSelection = (event) => {
    const target = event?.target;
    if (target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]")) return;
    const nativeHeader = target?.closest?.('.hmb-image-assets[data-hmb-native-header="active"] > .top');
    if (nativeHeader && !target?.closest?.(".project-switch")) return;
    if (Number(event?.button) !== 1) event.stopPropagation();
  };
  on(container, "pointerdown", stopInteriorNodeSelection);
  on(container, "dblclick", (event) => {
    if (!hmbImageAssetInternalToggleSurfaceForEvent(container, event)) return;
    event.preventDefault?.();
    event.stopPropagation?.();
    const root = container.querySelector?.(".hmb-image-assets");
    const next = root?.getAttribute?.("data-library-compact") !== "true";
    if (next) {
      if (container.__hmbImageAssetSelectionCommitPending) {
        hmbFlushImageAssetSelectionCommit(container);
      }
      const current = container.__hmbImageAssetLatestState || state;
      hmbSyncImageAssetCompactEntryState(container, current);
    }
    hmbSetImageAssetLibraryCompactGroup(container, next);
    hmbScheduleImageAssetThumbnailRequest(
      container,
      container.__hmbImageAssetLatestState || state,
      props,
      { includeWindow: !next },
    );
  });
  const assetsByLibraryId = new Map(
    state.assets.map((asset) => [clean(asset.asset_library_id), asset]),
  );
  const assetsBySourceUid = new Map(
    state.assets.map((asset) => [clean(asset.source_uid), asset]),
  );
  hmbInstallImageAssetScrollGestures(container, on);

  const commitShotMutation = (mutate, paint = null) => {
    const startsBurst = !container.__hmbImageAssetSelectionCommitPending;
    const baseSelection = startsBurst ? hmbImageAssetSelectionSnapshot(state) : null;
    const baseAuthority = startsBurst ? imageAssetAuthorityStamp(state) : 0;
    const basePropValue = startsBurst ? props?.value : undefined;
    const baseRouting = startsBurst
      ? cloneImageAssetShotRouting(state.shot_routing)
      : null;
    const baseCurrentScanRevision = startsBurst
      ? container.__hmbImageAssetCurrentScanRevision
      : null;
    const baseCurrentUiEditRevision = startsBurst
      ? container.__hmbImageAssetCurrentUiEditRevision
      : null;
    const baseLatestLocalUiEditRevision = startsBurst
      ? container.__hmbImageAssetLatestLocalUiEditRevision
      : null;
    if (typeof mutate !== "function" || !mutate()) return false;
    hmbInvalidateImageAssetPublication(container);
    if (startsBurst) {
      container.__hmbImageAssetSelectionBase = baseSelection;
      container.__hmbImageAssetSelectionBaseAuthority = baseAuthority;
      container.__hmbImageAssetSelectionBasePropValue = basePropValue;
      container.__hmbImageAssetShotRoutingBase = baseRouting;
      container.__hmbImageAssetSelectionBaseCurrentScanRevision = baseCurrentScanRevision;
      container.__hmbImageAssetSelectionBaseCurrentUiEditRevision = baseCurrentUiEditRevision;
      container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision =
        baseLatestLocalUiEditRevision;
    }
    delete container.__hmbImageAssetCanonicalSerialization;
    container.__hmbImageAssetLatestState = state;
    // Paint one optimistic frame immediately, then quarantine its exact host
    // echo.  A failed transport restores only when this publication still owns
    // the channel; hmbPublishImageAssetState already ignores an older rejection
    // after a newer Shot action has taken ownership.
    const paintState = () => {
      if (typeof paint === "function") {
        paint();
        return state;
      }
      return remount(state);
    };
    const priorCommitRunning = Boolean(
      container.__hmbImageAssetSelectionCommitRunning,
    );
    container.__hmbImageAssetSelectionCommitRunning = true;
    try {
      state = paintState();
    } finally {
      container.__hmbImageAssetSelectionCommitRunning = priorCommitRunning;
    }
    hmbScheduleImageAssetSelectionCommit(container, () => {
      const pending = container.__hmbImageAssetPendingAuthoritativeProps;
      const baseSelection = container.__hmbImageAssetSelectionBase || [];
      const baseAuthority = Number(container.__hmbImageAssetSelectionBaseAuthority) || 0;
      const baseRouting = container.__hmbImageAssetShotRoutingBase;
      const baseCurrentScanRevision = container.__hmbImageAssetSelectionBaseCurrentScanRevision;
      const baseCurrentUiEditRevision = container.__hmbImageAssetSelectionBaseCurrentUiEditRevision;
      const baseLatestLocalUiEditRevision =
        container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision;
      delete container.__hmbImageAssetPendingAuthoritativeProps;
      delete container.__hmbImageAssetSelectionBase;
      delete container.__hmbImageAssetSelectionBaseAuthority;
      delete container.__hmbImageAssetSelectionBasePropValue;
      delete container.__hmbImageAssetShotRoutingBase;
      delete container.__hmbImageAssetSelectionBaseCurrentScanRevision;
      delete container.__hmbImageAssetSelectionBaseCurrentUiEditRevision;
      delete container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision;
      let publishedState = state;
      let rollbackState = null;
      if (pending) {
        publishedState = hmbMergeImageAssetSelectionDelta(
          pending.state,
          baseSelection,
          state,
        );
        if (JSON.stringify(publishedState) !== JSON.stringify(state)) {
          state = remount(publishedState);
        }
        rollbackState = pending.state;
      }
      emit(props, publishedState, container, () => {
        if (rollbackState) {
          state = remount(rollbackState);
          container.__hmbImageAssetLatestLocalUiEditRevision =
            hmbNormalizeImageAssetRevision(
              state?.[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
            );
        } else if (imageAssetAuthorityStamp(state) === baseAuthority) {
          if (baseRouting) state.shot_routing = cloneImageAssetShotRouting(baseRouting);
          hmbRestoreImageAssetSelectionSnapshot(state, baseSelection);
          state[IMAGE_ASSET_UI_EDIT_REVISION_KEY] = hmbNormalizeImageAssetRevision(
            baseCurrentUiEditRevision ?? state[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
          );
          state = remount(state);
          container.__hmbImageAssetCurrentScanRevision = baseCurrentScanRevision;
          container.__hmbImageAssetCurrentUiEditRevision = baseCurrentUiEditRevision;
          container.__hmbImageAssetLatestLocalUiEditRevision =
            baseLatestLocalUiEditRevision;
        }
      }, { suppressMatchingEcho: true });
    });
    return true;
  };
  const paintActiveShotSelection = () => hmbApplyImageAssetSelectionFeedback(
    container,
    state,
    {
      assetsByLibraryId,
      activeShot: activeImageAssetShot(state),
      selectedAssets: imageAssetShotAssets(state, activeImageAssetShot(state)),
    },
  );
  const commitSlowProjectMutation = (mutate, action = {}) => {
    if (container.__hmbImageAssetBusy || container.__hmbImageAssetRefreshCleanupPending || typeof mutate !== "function") return false;
    const token = `${Date.now()}-${Math.random()}`;
    const pendingAction = {
      token,
      mountToken: container.__hmbImageAssetMountToken,
      runtimeId: imageAssetThumbnailRuntimeId(state),
      channelUuid: clean(state.shot_routing?.channel_uuid),
      catalogRoot: state.catalog_root,
      projectRoot: state.project_root,
      targetProjectRoot: clean(action.projectRoot),
      projects: state.projects.map((project) => ({ ...project })),
      scanRevision: hmbNormalizeImageAssetRevision(state.scan_revision),
      uiEditRevision: hmbNormalizeImageAssetRevision(state[IMAGE_ASSET_UI_EDIT_REVISION_KEY]),
    };
    container.__hmbImageAssetPendingSlowAction = pendingAction;
    container.__hmbImageAssetSlowActionToken = token;
    hmbSetImageAssetBusy(container, true, imageAssetText(state, "busy_loading"));
    hmbAfterImageAssetPaint(() => {
      if (
        container.__hmbImageAssetSlowActionToken !== token
        || container.__hmbImageAssetPendingSlowAction !== pendingAction
        || container.__hmbImageAssetMountToken !== pendingAction.mountToken
        || imageAssetThumbnailRuntimeId(container.__hmbImageAssetLatestState) !== pendingAction.runtimeId
        || clean(container.__hmbImageAssetLatestState?.shot_routing?.channel_uuid) !== pendingAction.channelUuid
      ) return;
      // Same-project metadata may arrive between the click and its first
      // paint. Publish through the latest callbacks/state, rather than losing
      // the click or overwriting that newer catalog with the pre-click object.
      state = container.__hmbImageAssetLatestState || state;
      const previous = {
        catalog_root: state.catalog_root,
        project_root: state.project_root,
        project_id: state.project_id,
        project_uid: state.project_uid,
        project_cache_uid: state.project_cache_uid,
        manifest_signature: state.manifest_signature,
        folder_signature: state.folder_signature,
        selected_folder_path: state.selected_folder_path,
        expanded_folders: [...state.expanded_folders],
        selected_main_type: state.selected_main_type,
        selected_sub_type: state.selected_sub_type,
        selected_source_view: state.selected_source_view,
        refresh_revision: state.refresh_revision,
      };
      delete container.__hmbImageAssetPendingSlowAction;
      mutate();
      container.__hmbImageAssetRenderLimit = IMAGE_ASSET_RENDER_WINDOW;
      container.__hmbImageAssetRenderOffset = 0;
      let failedSynchronously = false;
      const published = emit(props, state, container, (error) => {
        failedSynchronously = true;
        if (container.__hmbImageAssetSlowActionToken !== token) return;
        Object.assign(state, previous);
        delete container.__hmbImageAssetSlowActionToken;
        hmbSetImageAssetBusy(container, false);
        state = remount(state);
        hmbShowImageAssetTransportError(container, error, state);
      }, {
        onSuccess: () => {
          if (container.__hmbImageAssetSlowActionToken !== token) return;
          // The backend first acknowledges a scan_busy snapshot, then publishes
          // the generation-owned result. Keep feedback/duplicate prevention
          // active until that authoritative completion arrives.
          if (typeof props?.onChange !== "function") {
            delete container.__hmbImageAssetSlowActionToken;
            hmbSetImageAssetBusy(container, false);
          }
        },
      });
      if (!failedSynchronously) state = published;
    });
    return true;
  };

  const publishShotRouting = () => hmbPublishImageAssetShotRoutingCatalog(state);
  if (typeof window !== "undefined") {
    on(window, "hmb-shot-routing-discover-v1", publishShotRouting);
    publishShotRouting();
  }
  const commitImageBashMutation = (mutate, create = false, completion = null) => {
    if (container.__hmbNativeUiContract?.props?.disabled || typeof mutate !== "function") return false;
    hmbFlushImageAssetSelectionCommit(container);
    state = container.__hmbImageAssetLatestState || state;
    const previous = state;
    const candidate = { ...state, shot_routing: cloneImageAssetShotRouting(state.shot_routing),
      image_bash_workspace: hmbNormalizeImageBashWorkspace(state.image_bash_workspace), image_bash_workspace_request: {} };
    if (!mutate(candidate)) return false;
    if (create) candidate.image_bash_workspace_request = { schema: IMAGE_BASH_WORKSPACE_EDIT_SCHEMA, version: 1,
      operation: "create", request_id: newImageAssetUuid(), workspace_id: candidate.image_bash_workspace.workspace_id,
      expected_revision: candidate.image_bash_workspace.revision };
    hmbInvalidateImageAssetPublication(container);
    state = remount(candidate);
    const optimistic = state;
    let failed = false, published = null;
    published = emit(props, state, container, error => {
      failed = true;
      try { completion?.onFailure?.(error); } catch (_error) {}
      if (container.__hmbImageAssetLatestState === optimistic || container.__hmbImageAssetLatestState === published) state = remount(previous);
      else if (JSON.stringify(container.__hmbImageAssetLatestState?.image_bash_workspace) === JSON.stringify(candidate.image_bash_workspace)) {
        // A view-only remount replaces the canonical object, but does not
        // supersede this exact workspace edit or its rollback ownership.
        state = remount({ ...container.__hmbImageAssetLatestState, image_bash_workspace: previous.image_bash_workspace,
          image_bash_active: previous.image_bash_active, image_bash_workspace_request: {} });
      }
      hmbShowImageAssetTransportError(container, error, state);
    }, { onSuccess: () => {
      if (typeof completion?.onSuccess !== "function") return;
      Promise.resolve().then(() => {
        // A canonical acknowledgement may advance the publication clock.
        // The accepted workspace and the caller's draft guard own completion.
        if (!failed && JSON.stringify(container.__hmbImageAssetLatestState?.image_bash_workspace) === JSON.stringify(candidate.image_bash_workspace)) completion.onSuccess();
      });
    } });
    if (!failed) {
      // Only the explicit HMBImageBash add publication carries the create command.
      // Selection, page switches and cold restoration never replay it.
      published.image_bash_workspace_request = {};
      if (container.__hmbImageAssetLatestState === optimistic) { state = published; container.__hmbImageAssetLatestState = published; }
    }
    return !failed;
  };
  const commitHierarchyRequest = request => {
    const previous = container.__hmbImageAssetLatestState || state;
    const candidate = hmbApplyShotHierarchyEdit(previous, request);
    candidate.shot_hierarchy_request = request;
    let failed = false;
    let published = null;
    let optimistic = null;
    published = emit(props, candidate, container, error => {
      failed = true;
      if (container.__hmbImageAssetLatestState === previous || container.__hmbImageAssetLatestState === published
          || (optimistic && container.__hmbImageAssetLatestState === optimistic)) state = remount(previous);
      hmbShowImageAssetTransportError(container, error, state);
    });
    if (!failed) {
      published.shot_hierarchy_request = {};
      // A synchronous host acknowledgement may already contain a newer scan
      // or canonical metadata. Never replace it with the optimistic payload.
      if (container.__hmbImageAssetLatestState === previous) { optimistic = remount(published); state = optimistic; }
    }
  };
  on(container.querySelector("[data-shot-add]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (container.__hmbNativeUiContract?.props?.disabled) return;
    hmbFlushImageAssetSelectionCommit(container);
    state = container.__hmbImageAssetLatestState || state;
    hmbOpenShotHierarchyDialog(container, state, state.shot_routing.active_shot_uuid, commitHierarchyRequest,
      () => commitImageBashMutation(candidate => hmbCreateImageBashWorkspace(candidate), true));
  });
  container.querySelectorAll("[data-shot-delete]").forEach((button) => {
    const shotUuid = clean(button.getAttribute("data-shot-delete"));
    on(button, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      commitShotMutation(() => hmbDeleteImageAssetShot(state, shotUuid));
    });
  });
  container.querySelectorAll("[data-shot-tab]").forEach((button) => {
    const shotUuid = clean(button.getAttribute("data-shot-tab"));
    on(button, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.target?.closest?.("[data-shot-rename],[data-shot-rename-input]")) return;
      if (state.image_bash_active) {
        commitImageBashMutation(candidate => { candidate.image_bash_active = false; hmbActivateImageAssetShot(candidate, shotUuid); return true; });
        return;
      }
      const previousShot = activeImageAssetShot(state);
      commitShotMutation(
        () => hmbActivateImageAssetShot(state, shotUuid),
        () => hmbApplyImageAssetShotSwitchFeedback(container, state, {
          assetsByLibraryId,
          assetsBySourceUid,
          previousShot,
        }),
      );
    });
  });
  on(container, "click", event => {
    const tab = event.target?.closest?.("[data-image-bash-tab]");
    const remove = event.target?.closest?.("[data-image-bash-remove]");
    const duplicate = event.target?.closest?.("[data-image-bash-duplicate]");
    const action = tab || remove || duplicate;
    if (!action || !container.contains(action)) return;
    event.preventDefault(); event.stopPropagation();
    if (tab) commitImageBashMutation(candidate => { if (candidate.image_bash_active) return false; candidate.image_bash_active = true; return true; });
    else if (remove) commitImageBashMutation(candidate => hmbRemoveImageBashInstance(candidate, remove.dataset.imageBashRemove));
    else commitImageBashMutation(candidate => hmbDuplicateImageBashInstance(candidate, duplicate.dataset.imageBashDuplicate));
  });
  let imageBashDrag = null;
  on(container, "dragstart", event => {
    const card = event.target?.closest?.("[data-image-bash-instance]");
    if (!card || !container.contains(card) || container.__hmbNativeUiContract?.props?.disabled) return;
    imageBashDrag = { workspace_id: state.image_bash_workspace.workspace_id, instance_id: card.dataset.imageBashInstance };
    event.dataTransfer?.setData("application/x-hmb-image-bash-instance", JSON.stringify(imageBashDrag));
    event.dataTransfer?.setData("text/plain", imageBashDrag.instance_id);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
    event.stopPropagation();
  });
  on(container, "dragover", event => {
    if (imageBashDrag && event.target?.closest?.("[data-image-bash-instance]")) { event.preventDefault(); event.stopPropagation(); }
  });
  on(container, "drop", event => {
    const target = event.target?.closest?.("[data-image-bash-instance]");
    if (!target || !imageBashDrag || !container.contains(target)) return;
    event.preventDefault(); event.stopPropagation();
    const dragged = imageBashDrag; imageBashDrag = null;
    if (dragged.workspace_id !== state.image_bash_workspace.workspace_id) return;
    commitImageBashMutation(candidate => hmbReorderImageBashInstance(candidate, dragged.instance_id, target.dataset.imageBashInstance));
  });
  on(container, "dragend", () => { imageBashDrag = null; });
  const bindShotRenameInput = (input, renameButton, shotUuid) => {
    const routing = ensureImageAssetShotRouting(state);
    const shot = routing.shots.find((item) => item.shot_uuid === shotUuid);
    const ownerDocument = input?.ownerDocument || container.ownerDocument
      || (typeof document !== "undefined" ? document : null);
    if (!shot || !input || !renameButton || !ownerDocument?.createElement) return false;
    const initialName = input.value;
    renameButton.disabled = true;
    let settled = false;
    const finish = (save) => {
      if (settled) return;
      settled = true;
      const value = clean(input.value);
      const restored = ownerDocument.createElement("b");
      restored.setAttribute("data-shot-name", "");
      restored.textContent = save && value && value !== initialName ? value : shot.name;
      input.replaceWith(restored);
      renameButton.disabled = !hmbImageAssetShotCanRename(container.__hmbImageAssetLatestState || state, shotUuid);
      try { renameButton.focus?.({ preventScroll: true }); } catch (_error) { renameButton.focus?.(); }
      if (save && value && value !== initialName) {
        try {
          hmbFlushImageAssetSelectionCommit(container);
          state = container.__hmbImageAssetLatestState || state;
          if (container.__hmbNativeUiContract?.props?.disabled) throw new Error("Griptape에서 편집이 잠겨 있습니다.");
          const request = hmbImageAssetManualRenameRequest(state, shotUuid, value);
          if (request) commitHierarchyRequest(request);
          else commitShotMutation(() => hmbRenameImageAssetShot(state, shotUuid, value));
        } catch (error) {
          restored.textContent = shot.name;
          hmbShowImageAssetTransportError(container, error, state);
        }
      }
    };
    on(input, "keydown", (keyEvent) => {
      keyEvent.stopPropagation();
      if (hmbImageAssetRenameKeyIsComposing(keyEvent)) return;
      if (keyEvent.key === "Enter") {
        keyEvent.preventDefault();
        finish(true);
      } else if (keyEvent.key === "Escape") {
        keyEvent.preventDefault();
        finish(false);
      }
    });
    on(input, "blur", () => finish(true));
    return true;
  };

  container.querySelectorAll("[data-shot-rename-input]").forEach((input) => {
    const shotUuid = clean(input.getAttribute("data-shot-rename-input"));
    const renameButton = input.closest?.("[data-shot-panel]")
      ?.querySelector?.(`[data-shot-rename="${shotUuid}"]`);
    bindShotRenameInput(input, renameButton, shotUuid);
  });
  container.querySelectorAll("[data-shot-rename]").forEach((renameButton) => {
    const shotUuid = clean(renameButton.getAttribute("data-shot-rename"));
    on(renameButton, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      hmbFlushImageAssetSelectionCommit(container);
      state = container.__hmbImageAssetLatestState || state;
      if (renameButton.disabled || container.__hmbNativeUiContract?.props?.disabled
          || !hmbImageAssetShotCanRename(state, shotUuid)) return;
      const label = renameButton.closest("[data-shot-panel]")?.querySelector("[data-shot-name]");
      const shot = state.shot_routing.shots.find(row => row.shot_uuid === shotUuid);
      if (!label || !shot) return;
      const input = container.ownerDocument.createElement("input");
      input.type = "text"; input.className = "shot-name-input"; input.maxLength = 128;
      input.value = state.shot_hierarchy?.members?.find(row => row.gp_shot_uuid === shotUuid)?.source_name || shot.name;
      input.setAttribute("data-shot-rename-input", shotUuid);
      input.setAttribute("aria-label", imageAssetText(state, "rename_shot"));
      label.replaceWith(input);
      bindShotRenameInput(input, renameButton, shotUuid);
      input.focus({ preventScroll: true }); input.select();
    });
  });
  const projectSelect = container.querySelector("[data-project-select]");
  on(projectSelect, "change", () => {
    state = container.__hmbImageAssetLatestState || state;
    const path = clean(projectSelect.value).replaceAll("\\", "/");
    if (!path || imageAssetProjectPathKey(path) === imageAssetProjectPathKey(state.project_root)) return;
    commitSlowProjectMutation(() => {
      state.project_root = path;
      state.project_id = "";
      state.project_uid = "";
      state.project_cache_uid = "";
      state.folder_signature = "";
      state.selected_folder_path = "";
      state.expanded_folders = [ROOT_FOLDER_KEY];
      state.selected_main_type = "";
      state.selected_sub_type = "";
      state.selected_source_view = "project";
    }, { projectRoot: path });
  });

  on(container.querySelector("[data-language-toggle]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    state = container.__hmbImageAssetLatestState || state;
    state.language = imageAssetLanguage(state) === "ko" ? "en" : "ko";
    state = emit(props, state, container);
    remount(state);
  });
  on(container.querySelector("[data-asset-view-toggle]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    state.asset_view_mode = state.asset_view_mode === "detail" ? "image" : "detail";
    state = emit(props, state, container);
    remount(state);
  });
  on(container.querySelector("[data-project-set]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openNativeProjectRootPicker(container);
  });
  on(container.querySelector("[data-project-reload]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    state = container.__hmbImageAssetLatestState || state;
    // Explicit Refresh is also the user-owned retry boundary for thumbnails
    // that reached a terminal decode/network failure in the same catalog.
    hmbResetImageAssetThumbnailRetryState(container, state);
    commitSlowProjectMutation(() => {
      state.refresh_revision = Math.max(0, Number(state.refresh_revision) || 0) + 1;
    });
  });

  const onTreeClick = (event) => {
    const row = event.target?.closest?.("[data-folder-key]");
    if (!row || !container.contains(row)) return;
    const key = clean(row.getAttribute("data-folder-key"));
    const path = normalizeRelativeFolder(row.getAttribute("data-folder-path"));
    state.selected_source_view = row.getAttribute("data-source-view") === "user"
      ? "user"
      : "project";
    state.selected_folder_path = path;
    if (row.getAttribute("data-has-children") === "1") {
      const expanded = new Set(state.expanded_folders);
      if (expanded.has(key)) expanded.delete(key);
      else expanded.add(key);
      state.expanded_folders = [...expanded];
    }
    container.__hmbImageAssetRenderLimit = IMAGE_ASSET_RENDER_WINDOW;
    container.__hmbImageAssetRenderOffset = 0;
    state = emit(props, state, container);
    remount(state);
  };
  on(container, "click", onTreeClick);

  const search = container.querySelector("[data-search]");
  const flushSearch = () => {
    if (container.__hmbImageAssetSearchTimer != null && typeof clearTimeout === "function") {
      clearTimeout(container.__hmbImageAssetSearchTimer);
    }
    delete container.__hmbImageAssetSearchTimer;
    hmbReconcileImageAssetCatalog(container, state);
    hmbScheduleImageAssetThumbnailRequest(container, state, props, {
      includeWindow: true,
    });
  };
  on(search, "input", () => {
    state.search = String(search.value || "").slice(0, 256);
    container.__hmbImageAssetSearchDraft = state.search;
    container.__hmbImageAssetRenderLimit = IMAGE_ASSET_RENDER_WINDOW;
    container.__hmbImageAssetRenderOffset = 0;
    if (container.__hmbImageAssetSearchTimer != null && typeof clearTimeout === "function") {
      clearTimeout(container.__hmbImageAssetSearchTimer);
    }
    if (typeof setTimeout === "function") {
      container.__hmbImageAssetSearchTimer = setTimeout(
        flushSearch,
        IMAGE_ASSET_SEARCH_DEBOUNCE_MS,
      );
    } else {
      flushSearch();
    }
  });
  const commitSearch = () => {
    state.search = String(search?.value || "").slice(0, 256);
    flushSearch();
    state = emit(props, state, container);
    delete container.__hmbImageAssetSearchDraft;
  };
  on(search, "change", commitSearch);
  on(container, "click", (event) => {
    const more = event.target?.closest?.("[data-assets-more]");
    const previous = event.target?.closest?.("[data-assets-previous]");
    const control = more || previous;
    if (!control || !container.contains?.(control)) return;
    event.preventDefault();
    event.stopPropagation();
    const direction = more ? 1 : -1;
    container.__hmbImageAssetRenderLimit = IMAGE_ASSET_RENDER_WINDOW;
    container.__hmbImageAssetRenderOffset = Math.max(
      0,
      (Number(container.__hmbImageAssetRenderOffset) || 0)
        + direction * IMAGE_ASSET_RENDER_WINDOW,
    );
    hmbReconcileImageAssetCatalog(container, state);
    hmbScheduleImageAssetThumbnailRequest(container, state, props, {
      includeWindow: true,
    });
    const nextFocus = container.querySelector?.(
      direction > 0 ? "[data-assets-more]" : "[data-assets-previous]",
    ) || container.querySelector?.(
      direction > 0 ? "[data-assets-previous]" : "[data-assets-more]",
    );
    nextFocus?.focus?.({ preventScroll: true });
  });

  container.querySelectorAll("[data-asset-key]").forEach((card) => {
    const key = clean(card.getAttribute("data-asset-key"));
    const asset = assetsByLibraryId.get(key);
    if (!asset) return;
    on(card.querySelector("[data-asset-add]"), "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!hmbImageAssetCanRegister(asset)) return;
      container.__hmbImageAssetRegistrationReturnFocus = {
        descriptor: imageAssetFocusDescriptor(container),
        assetKey: asset.asset_library_id,
      };
      container.__hmbImageAssetRegistrationDraft = hmbCreateImageAssetRegistrationDraft(
        asset,
        state.taxonomy,
      );
      remount(state);
      Promise.resolve().then(() => {
        container.querySelector?.('[data-registration-field="image_name"]')?.focus?.();
      });
    });
    const toggle = () => {
      const asset = container.__hmbImageAssetByLibraryId?.get(key) || assetsByLibraryId.get(key);
      if (!asset) return;
      if (!hmbImageAssetCanSelect(asset)) return;
      if (state.image_bash_active) {
        commitImageBashMutation(candidate => hmbAddImageBashSource(candidate, asset.source_uid)); return;
      }
      const activeShot = activeImageAssetShot(state);
      if (!activeShot) return;
      const selected = imageAssetShotAssets(state, activeShot);
      // A visible newer click owns transport recovery immediately, even before
      // its two-frame publication. An older Promise rejection cannot roll it back.
      hmbInvalidateImageAssetPublication(container);
      if (!container.__hmbImageAssetSelectionCommitPending) {
        container.__hmbImageAssetSelectionBase = hmbImageAssetSelectionSnapshot(state);
        container.__hmbImageAssetSelectionBaseAuthority = imageAssetAuthorityStamp(state);
        container.__hmbImageAssetSelectionBasePropValue = props?.value;
        container.__hmbImageAssetShotRoutingBase = cloneImageAssetShotRouting(state.shot_routing);
        container.__hmbImageAssetSelectionBaseCurrentScanRevision =
          container.__hmbImageAssetCurrentScanRevision;
        container.__hmbImageAssetSelectionBaseCurrentUiEditRevision =
          container.__hmbImageAssetCurrentUiEditRevision;
        container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision =
          container.__hmbImageAssetLatestLocalUiEditRevision;
      }
      if (!hmbToggleImageAssetShotAsset(state, activeShot.shot_uuid, asset.source_uid, asset)) return;
      container.__hmbImageAssetLatestState = state;
      const nextActiveShot = activeImageAssetShot(state);
      const nextSelected = imageAssetShotAssets(state, nextActiveShot);
      hmbApplyImageAssetSelectionFeedback(container, state, {
        assetsByLibraryId,
        changedAsset: asset,
        changedCard: card,
        previousSelectedCount: selected.length,
        selectedAssets: nextSelected,
        activeShot: nextActiveShot,
      });
      hmbScheduleImageAssetSelectionCommit(container, () => {
        const pending = container.__hmbImageAssetPendingAuthoritativeProps;
        const baseSelection = container.__hmbImageAssetSelectionBase || [];
        const baseAuthority = Number(container.__hmbImageAssetSelectionBaseAuthority) || 0;
        const baseShotRouting = container.__hmbImageAssetShotRoutingBase;
        const baseCurrentScanRevision =
          container.__hmbImageAssetSelectionBaseCurrentScanRevision;
        const baseCurrentUiEditRevision =
          container.__hmbImageAssetSelectionBaseCurrentUiEditRevision;
        const baseLatestLocalUiEditRevision =
          container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision;
        delete container.__hmbImageAssetPendingAuthoritativeProps;
        delete container.__hmbImageAssetSelectionBase;
        delete container.__hmbImageAssetSelectionBaseAuthority;
        delete container.__hmbImageAssetSelectionBasePropValue;
        delete container.__hmbImageAssetShotRoutingBase;
        delete container.__hmbImageAssetSelectionBaseCurrentScanRevision;
        delete container.__hmbImageAssetSelectionBaseCurrentUiEditRevision;
        delete container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision;
        let publishedState = state;
        let rollbackState = null;
        if (pending) {
          const merged = hmbMergeImageAssetSelectionDelta(
            pending.state,
            baseSelection,
            state,
          );
          if (JSON.stringify(merged) !== JSON.stringify(state)) remount(merged);
          publishedState = merged;
          rollbackState = pending.state;
        }
        emit(props, publishedState, container, () => {
          if (rollbackState) {
            state = remount(rollbackState);
            container.__hmbImageAssetLatestLocalUiEditRevision =
              hmbNormalizeImageAssetRevision(
                state?.[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
              );
          } else if (imageAssetAuthorityStamp(state) === baseAuthority) {
            hmbRestoreImageAssetSelectionSnapshot(state, baseSelection);
            if (baseShotRouting) state.shot_routing = baseShotRouting;
            state[IMAGE_ASSET_UI_EDIT_REVISION_KEY] = hmbNormalizeImageAssetRevision(
              baseCurrentUiEditRevision
                ?? state[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
            );
            state = remount(state);
            container.__hmbImageAssetCurrentScanRevision = baseCurrentScanRevision;
            container.__hmbImageAssetCurrentUiEditRevision = baseCurrentUiEditRevision;
            container.__hmbImageAssetLatestLocalUiEditRevision =
              baseLatestLocalUiEditRevision;
          }
        }, { suppressMatchingEcho: true });
      });
    };
    on(card, "click", (event) => {
      if (event.target?.closest?.("input,button,select,textarea,a")) return;
      event.__hmbImageAssetCardHandled = true;
      toggle();
    });
    on(card, "keydown", (event) => {
      if (!["Enter", " "].includes(event.key) || event.target !== card) return;
      event.preventDefault();
      event.__hmbImageAssetCardHandled = true;
      toggle();
    });
  });

  // Cards outside the first render window are inserted later by the keyed
  // catalog reconciler, so card interaction is also delegated from the stable
  // widget root. Existing directly-bound cards mark handled events to avoid a
  // duplicate action during the transition to retained windows.
  const toggleDelegatedAsset = (card, asset) => {
    if (!hmbImageAssetCanSelect(asset)) return;
    if (state.image_bash_active) {
      commitImageBashMutation(candidate => hmbAddImageBashSource(candidate, asset.source_uid)); return;
    }
    const activeShot = activeImageAssetShot(state);
    if (!activeShot) return;
    const selected = imageAssetShotAssets(state, activeShot);
    hmbInvalidateImageAssetPublication(container);
    if (!container.__hmbImageAssetSelectionCommitPending) {
      container.__hmbImageAssetSelectionBase = hmbImageAssetSelectionSnapshot(state);
      container.__hmbImageAssetSelectionBaseAuthority = imageAssetAuthorityStamp(state);
      container.__hmbImageAssetSelectionBasePropValue = props?.value;
      container.__hmbImageAssetShotRoutingBase = cloneImageAssetShotRouting(state.shot_routing);
      container.__hmbImageAssetSelectionBaseCurrentScanRevision =
        container.__hmbImageAssetCurrentScanRevision;
      container.__hmbImageAssetSelectionBaseCurrentUiEditRevision =
        container.__hmbImageAssetCurrentUiEditRevision;
      container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision =
        container.__hmbImageAssetLatestLocalUiEditRevision;
    }
    if (!hmbToggleImageAssetShotAsset(state, activeShot.shot_uuid, asset.source_uid, asset)) return;
    container.__hmbImageAssetLatestState = state;
    const nextActiveShot = activeImageAssetShot(state);
    hmbApplyImageAssetSelectionFeedback(container, state, {
      assetsByLibraryId,
      changedAsset: asset,
      changedCard: card,
      previousSelectedCount: selected.length,
      selectedAssets: imageAssetShotAssets(state, nextActiveShot),
      activeShot: nextActiveShot,
    });
    hmbScheduleImageAssetSelectionCommit(container, () => {
      const pending = container.__hmbImageAssetPendingAuthoritativeProps;
      const baseSelection = container.__hmbImageAssetSelectionBase || [];
      const baseAuthority = Number(container.__hmbImageAssetSelectionBaseAuthority) || 0;
      const baseShotRouting = container.__hmbImageAssetShotRoutingBase;
      const baseCurrentScanRevision = container.__hmbImageAssetSelectionBaseCurrentScanRevision;
      const baseCurrentUiEditRevision = container.__hmbImageAssetSelectionBaseCurrentUiEditRevision;
      const baseLatestLocalUiEditRevision = container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision;
      delete container.__hmbImageAssetPendingAuthoritativeProps;
      delete container.__hmbImageAssetSelectionBase;
      delete container.__hmbImageAssetSelectionBaseAuthority;
      delete container.__hmbImageAssetSelectionBasePropValue;
      delete container.__hmbImageAssetShotRoutingBase;
      delete container.__hmbImageAssetSelectionBaseCurrentScanRevision;
      delete container.__hmbImageAssetSelectionBaseCurrentUiEditRevision;
      delete container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision;
      let publishedState = state;
      let rollbackState = null;
      if (pending) {
        publishedState = hmbMergeImageAssetSelectionDelta(pending.state, baseSelection, state);
        if (JSON.stringify(publishedState) !== JSON.stringify(state)) state = remount(publishedState);
        rollbackState = pending.state;
      }
      emit(props, publishedState, container, () => {
        if (rollbackState) {
          state = remount(rollbackState);
          container.__hmbImageAssetLatestLocalUiEditRevision = hmbNormalizeImageAssetRevision(
            state?.[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
          );
        } else if (imageAssetAuthorityStamp(state) === baseAuthority) {
          hmbRestoreImageAssetSelectionSnapshot(state, baseSelection);
          if (baseShotRouting) state.shot_routing = baseShotRouting;
          state[IMAGE_ASSET_UI_EDIT_REVISION_KEY] = hmbNormalizeImageAssetRevision(
            baseCurrentUiEditRevision ?? state[IMAGE_ASSET_UI_EDIT_REVISION_KEY],
          );
          state = remount(state);
          container.__hmbImageAssetCurrentScanRevision = baseCurrentScanRevision;
          container.__hmbImageAssetCurrentUiEditRevision = baseCurrentUiEditRevision;
          container.__hmbImageAssetLatestLocalUiEditRevision = baseLatestLocalUiEditRevision;
        }
      }, { suppressMatchingEcho: true });
    });
  };
  on(container, "click", (event) => {
    if (event.__hmbImageAssetCardHandled) return;
    const card = event.target?.closest?.("[data-asset-key]");
    if (!card || !container.contains?.(card)) return;
    const key = clean(card.getAttribute("data-asset-key"));
    const asset = container.__hmbImageAssetByLibraryId?.get(key) || assetsByLibraryId.get(key);
    if (!asset) return;
    const add = event.target?.closest?.("[data-asset-add]");
    if (add) {
      event.preventDefault();
      event.stopPropagation();
      if (!hmbImageAssetCanRegister(asset)) return;
      container.__hmbImageAssetRegistrationReturnFocus = {
        descriptor: imageAssetFocusDescriptor(container),
        assetKey: asset.asset_library_id,
      };
      container.__hmbImageAssetRegistrationDraft = hmbCreateImageAssetRegistrationDraft(asset, state.taxonomy);
      remount(state);
      Promise.resolve().then(() => {
        container.querySelector?.('[data-registration-field="image_name"]')?.focus?.();
      });
      return;
    }
    if (event.target?.closest?.("input,button,select,textarea,a")) return;
    toggleDelegatedAsset(card, asset);
  });
  on(container, "keydown", (event) => {
    if (event.__hmbImageAssetCardHandled || !["Enter", " "].includes(event.key)) return;
    const card = event.target?.closest?.("[data-asset-key]");
    if (!card || event.target !== card || !container.contains?.(card)) return;
    const key = clean(card.getAttribute("data-asset-key"));
    const asset = container.__hmbImageAssetByLibraryId?.get(key) || assetsByLibraryId.get(key);
    if (!asset) return;
    event.preventDefault();
    toggleDelegatedAsset(card, asset);
  });

  const restoreRegistrationOpener = (returnFocus) => {
    Promise.resolve().then(() => {
      if (!returnFocus) return;
      restoreImageAssetUi(container, state, {
        viewKey: imageAssetViewKey(state),
        scroll: {},
        focus: returnFocus.descriptor,
      });
      const active = typeof document !== "undefined" ? document.activeElement : null;
      if (!active || !container.contains?.(active)) {
        const card = Array.from(container.querySelectorAll("[data-asset-key]"))
          .find((item) => clean(item.getAttribute("data-asset-key")) === clean(returnFocus.assetKey));
        card?.focus?.();
      }
    });
  };
  const closeRegistration = () => {
    const returnFocus = container.__hmbImageAssetRegistrationReturnFocus;
    const deferredProps = hmbTakeDeferredImageAssetProps(container);
    delete container.__hmbImageAssetRegistrationDraft;
    delete container.__hmbImageAssetRegistrationReturnFocus;
    remount(deferredProps ? normalizeState(deferredProps?.value) : state);
    restoreRegistrationOpener(returnFocus);
  };
  on(container.querySelector("[data-registration-bash-add]"), "click", event => {
    event.preventDefault(); event.stopPropagation();
    if (container.__hmbNativeUiContract?.props?.disabled) return;
    const draft = container.__hmbImageAssetRegistrationDraft;
    if (!draft || draft.bash_pending) return;
    const deferredProps = hmbTakeDeferredImageAssetProps(container);
    if (deferredProps) state = remount(normalizeState(deferredProps.value));
    const current = container.__hmbImageAssetLatestState || state;
    const asset = current.assets.find(row => row.asset_library_id === draft.asset_library_id && row.source_uid === draft.source_uid);
    if (!current.image_bash_active || !current.image_bash_workspace?.workspace_id || !asset
        || asset.source_kind !== "user" || Number(asset.import_index || 0) <= 0
        || !hmbImageAssetCanSelect(asset) || current.image_bash_workspace.instances.length >= MAX_SELECTED_IMAGES) return;
    draft.bash_pending = true;
    const started = commitImageBashMutation(candidate => hmbAddImageBashSource(candidate, asset.source_uid), false, {
      onFailure() { if (container.__hmbImageAssetRegistrationDraft === draft) delete draft.bash_pending; },
      onSuccess() {
        if (container.__hmbImageAssetRegistrationDraft !== draft) return;
        delete draft.bash_pending; closeRegistration();
      },
    });
    if (!started) { delete draft.bash_pending; state = remount(state); }
  });
  container.querySelectorAll("[data-registration-cancel]").forEach((button) => {
    on(button, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      closeRegistration();
    });
  });
  const registrationBackdrop = container.querySelector("[data-registration-backdrop]");
  hmbInstallImageAssetRegistrationBackdropDismissal(
    registrationBackdrop,
    closeRegistration,
    on,
  );
  hmbInstallImageAssetRefreshReviewEvents(container, state, props, remount);
  const updateRegistrationSubmit = () => {
    const submit = container.querySelector("[data-registration-submit]");
    if (submit) {
      submit.disabled = !registrationDraftIsComplete(
        container.__hmbImageAssetRegistrationDraft,
      ) || Boolean(container.__hmbImageAssetRegistrationDraft?.bash_pending);
    }
  };
  container.querySelectorAll("[data-registration-field]").forEach((input) => {
    const field = clean(input.getAttribute("data-registration-field"));
    on(input, "input", () => {
      const draft = container.__hmbImageAssetRegistrationDraft;
      if (!draft || !field) return;
      draft[field] = String(input.value || "").slice(0, 256);
      updateRegistrationSubmit();
    });
  });
  const registrationFolder = container.querySelector("[data-registration-folder]");
  on(registrationFolder, "change", () => {
    const draft = container.__hmbImageAssetRegistrationDraft;
    if (!draft) return;
    draft.target_folder = clean(registrationFolder.value);
    draft.target_folder_confirmed = Boolean(draft.target_folder);
    updateRegistrationSubmit();
  });
  const registrationMain = container.querySelector("[data-registration-main]");
  on(registrationMain, "change", () => {
    const draft = container.__hmbImageAssetRegistrationDraft;
    if (!draft) return;
    draft.image_main_type = clean(registrationMain.value);
    remount(state);
  });
  const registrationSub = container.querySelector("[data-registration-sub]");
  on(registrationSub, "change", () => {
    const draft = container.__hmbImageAssetRegistrationDraft;
    if (!draft) return;
    draft.image_sub_type = clean(registrationSub.value);
    remount(state);
  });
  on(container.querySelector("[data-registration-submit]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const draft = container.__hmbImageAssetRegistrationDraft;
    if (!registrationDraftIsComplete(draft)) return;
    const deferredProps = hmbTakeDeferredImageAssetProps(container);
    if (deferredProps) state = normalizeState(deferredProps?.value);
    state.asset_registration_request = {
      request_id: `asset-registration-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      project_uid: state.project_uid,
      asset_library_id: draft.asset_library_id,
      source_kind: draft.source_kind,
      source_uid: draft.source_uid,
      relative_path: draft.relative_path,
      target_folder: clean(draft.target_folder),
      image_name: clean(draft.image_name),
      asset_id: clean(draft.asset_id),
      image_main_type: clean(draft.image_main_type),
      image_sub_type: clean(draft.image_sub_type),
      custom_source_type: clean(draft.custom_source_type),
    };
    state.asset_registration_result = {};
    const returnFocus = container.__hmbImageAssetRegistrationReturnFocus;
    delete container.__hmbImageAssetRegistrationDraft;
    delete container.__hmbImageAssetRegistrationReturnFocus;
    state = emit(deferredProps || props, state, container);
    remount(state);
    restoreRegistrationOpener(returnFocus);
  });
  on(container, "keydown", (event) => {
    if (!container.__hmbImageAssetRegistrationDraft) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeRegistration();
      return;
    }
    if (event.key !== "Tab") return;
    const dialog = container.querySelector('[role="dialog"]');
    if (!dialog) return;
    const focusable = Array.from(dialog.querySelectorAll(
      'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
    ));
    if (!focusable.length) return;
    const active = typeof document !== "undefined" ? document.activeElement : null;
    const currentIndex = focusable.indexOf(active);
    if (event.shiftKey && currentIndex <= 0) {
      event.preventDefault();
      focusable[focusable.length - 1].focus?.();
    } else if (!event.shiftKey && (currentIndex < 0 || currentIndex >= focusable.length - 1)) {
      event.preventDefault();
      focusable[0].focus?.();
    }
  });

  on(container, "error", (event) => {
    const image = event.target;
    if (!image?.matches?.("img")) return;
    image.closest?.(".asset-thumb,.selected-thumb,.passport-photo")?.classList?.add("fallback");
    hmbHandleImageAssetThumbnailError(
      container,
      container.__hmbImageAssetLatestState || state,
      image,
      props,
    );
  }, true);
  on(container, "load", (event) => {
    const image = event.target;
    if (!image?.matches?.("img")) return;
    hmbRememberLoadedImageAssetThumbnail(
      container,
      container.__hmbImageAssetLatestState || state,
      image,
    );
  }, true);

  const selectedTray = container.querySelector("[data-shot-tray]");
  const selectedCardForEvent = (event) => {
    const card = event.target?.closest?.("[data-selected-key]");
    return card && selectedTray?.contains?.(card) ? card : null;
  };
  hmbInstallImageAssetShotDragReorder(container, {
    listen: (eventName, handler) => on(container, eventName, handler, true),
    currentState: () => container.__hmbImageAssetLatestState || state,
    commitReorder: ({ shotUuid, sourceUid, targetUid }) => {
      const liveState = container.__hmbImageAssetLatestState || state;
      if (liveState !== state) state = liveState;
      return commitShotMutation(
        () => hmbReorderImageAssetShotSource(state, shotUuid, sourceUid, targetUid),
        () => hmbApplyImageAssetShotSourceOrderToDom(container, state, shotUuid),
      );
    },
  });
  on(selectedTray, "click", (event) => {
    const action = event.target?.closest?.("[data-remove-selected]");
    const card = selectedCardForEvent(event);
    if (!action || !card) return;
    event.preventDefault();
    event.stopPropagation();
    const key = clean(card.getAttribute("data-shot-source-uid"));
    const shotUuid = clean(card.getAttribute("data-shot-uuid"));
    const asset = assetsBySourceUid.get(key);
    if (!asset) return;
    if (action.matches?.("[data-remove-selected]")) {
      commitShotMutation(
        () => hmbToggleImageAssetShotAsset(state, shotUuid, key, asset),
        paintActiveShotSelection,
      );
    }
  });

  const syncNativeRoot = () => {
    state = container.__hmbImageAssetLatestState || state;
    const nativePath = hmbRelocateImageProjectPath(nativeProjectRootValue(container)).replaceAll("\\", "/");
    if (!nativePath || nativePath.toLowerCase() === state.catalog_root.toLowerCase()) return;
    commitSlowProjectMutation(() => {
      state.catalog_root = nativePath;
      state.project_root = "";
      state.project_id = "";
      state.project_uid = "";
      state.project_cache_uid = "";
      state.folder_signature = "";
    });
  };
  // PROJECT_ROOT is an explicit host input. Listen only to the actual native
  // controls so unrelated node edits, focus changes, and ambient browser
  // lifecycle events can never trigger a catalog read.
  nativeProjectRootElements(container).forEach((element) => {
    on(element, "change", syncNativeRoot);
    on(element, "input", syncNativeRoot);
  });
}

function hmbNativeUiImplementation(container, props) {
  if (!container) return () => {};
  if (typeof container.__hmbImageAssetCleanupProxy !== "function") {
    container.__hmbImageAssetCleanupProxy = () => {
      const activeCleanup = container.__hmbImageAssetCleanup;
      if (typeof activeCleanup === "function") activeCleanup();
    };
  }
  if (typeof container.__hmbImageAssetApplyProps === "function") {
    container.__hmbImageAssetApplyProps(props || {});
    return {
      cleanup: container.__hmbImageAssetCleanupProxy,
      update(nextProps) {
        container.__hmbImageAssetApplyProps?.(nextProps || {});
      },
    };
  }
  const previousCleanup = container.__hmbImageAssetCleanup;
  if (typeof previousCleanup === "function") previousCleanup();
  const mountToken = ++imageAssetWidgetMountSequence;
  container.__hmbImageAssetMountToken = mountToken;
  hmbAttachImageAssetRegistryContainer(container);
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  props = hmbUpdateImageAssetPropsReference({}, props);
  const rememberNodeInternalsUpdater = (candidate = {}) => {
    const updater = candidate?.updateNodeInternals
      || candidate?.requestNodeInternalsUpdate
      || candidate?.onUpdateNodeInternals;
    if (typeof updater === "function") container.__hmbImageAssetUpdateNodeInternals = updater;
  };
  rememberNodeInternalsUpdater(props);
  const cleanupImportHandles = hmbInstallImageAssetImportHandleDecoration(container);
  let state = normalizeState(props?.value);
  // A saved value is state, not permission to recreate a graph node.
  state.image_bash_workspace_request = {};
  container.__hmbImageAssetAcceptedEditCatalogIdentity = imageAssetEditCatalogIdentity(state);
  hmbRememberImageAssetPresentation(state);
  hmbAdoptImageAssetPresentation(state);
  container.__hmbImageAssetLatestState = state;
  hmbAcceptImageAssetThumbnailResult(container, state);
  hmbRememberImageAssetRevisionState(container, state, false);
  let listeners = [];
  let renderRevision = 0;
  const catalogPages=hmbInstallImageAssetCatalogPages(container,()=>state,(dto)=>{
    const page=normalizeState(dto),selected=selectedAssets(state),selectedIds=new Set(selected.map(asset=>asset.source_uid));
    const retained=[...selected,...hmbImageBashWorkspaceAssets(state).map(row=>row.asset).filter(Boolean)];
    const byId=new Map(retained.map(asset=>[asset.asset_library_id,asset]));
    const visible=new Map(state.assets.map(asset=>[asset.asset_library_id,asset]));
    for(const asset of page.assets)if(!byId.has(asset.asset_library_id)){
      const prior=visible.get(asset.asset_library_id);
      const thumbnail=prior?.thumbnail_url && prior.media_signature===asset.media_signature
        && state.thumbnail_revision>=page.thumbnail_revision ? prior.thumbnail_url : asset.thumbnail_url;
      const retained=prior || {};
      Object.assign(retained,asset,{thumbnail_url:thumbnail,
        selected:selectedIds.has(asset.source_uid),selection_order:0});
      byId.set(asset.asset_library_id,retained);
    }
    state.assets=[...byId.values()];state.catalog_page=page.catalog_page;
    state.status={...page.status,selected_count:selected.length};
    container.__hmbImageAssetLatestState=state;
    container.__hmbImageAssetRenderOffset=page.catalog_page.offset;
    hmbReconcileImageAssetCatalog(container,state);
    hmbScheduleImageAssetThumbnailRequest(container,state,props,{includeWindow:!container.__hmbImageAssetCompact});
  },(full)=>{
    const canonical=normalizeState(full),selected=selectedAssets(state),order=new Map(selected.map((asset,index)=>[asset.source_uid,index+1]));
    const visible=new Map(state.assets.map(asset=>[asset.asset_library_id,asset]));
    state.assets=canonical.assets.map(asset=>Object.assign(visible.get(asset.asset_library_id)||{},asset,
      {selected:order.has(asset.source_uid),selection_order:order.get(asset.source_uid)||0}));
    state.status={...canonical.status,selected_count:selected.length};
    delete state.catalog_page;
    container.__hmbImageAssetLatestState=state;
    hmbReconcileImageAssetCatalog(container,state);
    hmbScheduleImageAssetThumbnailRequest(container,state,props,{includeWindow:!container.__hmbImageAssetCompact});
  });

  const consumeCatalogProbeResult = (result) => hmbAcceptImageAssetCatalogProbeResult(
    container,
    container.__hmbImageAssetLatestState || state,
    result,
  );
  const wakeCatalogPolling = () => hmbStartImageAssetCatalogPolling(
    container,
    container.__hmbImageAssetLatestState || state,
  );

  const consumeThumbnailPresentationPatch = (patch) => {
    if (patch?.operation?.startsWith("cgt_")) return container.__hmbHierarchyReceive?.(patch) || false;
    const applied = hmbApplyImageAssetThumbnailPresentationPatch(
      container.__hmbImageAssetLatestState || state,
      patch,
    );
    if (!applied) return false;
    state = applied.state;
    container.__hmbImageAssetLatestState = state;
    hmbAcceptImageAssetThumbnailResult(container, state);
    hmbPatchImageAssetThumbnailMedia(
      container,
      state,
      applied.changedAssetLibraryIds,
    );
    hmbScheduleImageAssetThumbnailRequest(container, state, props, {
      includeWindow: !container.__hmbImageAssetCompact,
    });
    return true;
  };
  hmbRegisterImageAssetThumbnailConsumer(
    container,
    state,
    consumeThumbnailPresentationPatch,
  );
  hmbRegisterImageAssetCatalogProbeConsumer(
    container,
    state,
    consumeCatalogProbeResult,
    wakeCatalogPolling,
  );
  hmbStartImageAssetCatalogPolling(container, state);

  const clearListeners = () => {
    listeners.forEach(([target, type, handler, options]) => {
      try {
        target.removeEventListener(type, handler, options);
      } catch (_error) {}
    });
    listeners = [];
  };

  const remount = (nextState = state) => {
    const revisionBeforeFlush = renderRevision;
    if (
      container.__hmbImageAssetSelectionCommitPending
      && !container.__hmbImageAssetSelectionCommitRunning
    ) {
      hmbFlushImageAssetSelectionCommit(container);
      // An authoritative selection merge can perform the required remount from
      // inside the flushed job. Do not then paint the stale outer snapshot.
      if (renderRevision !== revisionBeforeFlush) return state;
    }
    renderRevision += 1;
    if (container.__hmbImageAssetCompact) {
      state = normalizeState(nextState);
      hmbRememberImageAssetPresentation(state);
      hmbAdoptImageAssetPresentation(state);
      hmbApplyImageAssetThumbnailFailurePresentation(container, state);
      hmbRememberImageAssetRevisionState(container, state, false);
      if (typeof container.__hmbImageAssetSearchDraft === "string") {
        state.search = container.__hmbImageAssetSearchDraft.slice(0, 256);
      }
      container.__hmbImageAssetLatestState = state;
      catalogPages.wake();
      hmbRegisterImageAssetThumbnailConsumer(
        container,
        state,
        consumeThumbnailPresentationPatch,
      );
      hmbRegisterImageAssetCatalogProbeConsumer(
        container,
        state,
        consumeCatalogProbeResult,
        wakeCatalogPolling,
      );
      hmbStartImageAssetCatalogPolling(container, state);
      hmbResumeImageAssetThumbnailRequest(container, state, props);
      hmbPatchCompactImageAssetState(container, state);
      const refreshReview = hmbSyncImageAssetRefreshReview(container, state);
      hmbPatchImageAssetRefreshReview(container, state, refreshReview);
      hmbInstallImageAssetRefreshReviewEvents(container, state, props, remount);
      hmbScheduleImageAssetThumbnailRequest(container, state, props, {
        includeWindow: false,
      });
      return state;
    }
    const uiMemory = container.__hmbImageAssetCompactUiMemory
      || captureImageAssetUi(container, state);
    const reusableImages = detachReusableImageAssets(container);
    const hierarchyDialog = container.__hmbHierarchyDialog;
    if (hierarchyDialog?.isConnected && container.contains(hierarchyDialog)) { hierarchyDialog.close?.(); hierarchyDialog.remove(); }
    clearListeners();
    state = normalizeState(nextState);
    hmbRememberImageAssetPresentation(state);
    hmbAdoptImageAssetPresentation(state);
    hmbApplyImageAssetThumbnailFailurePresentation(container, state);
    hmbRememberImageAssetRevisionState(container, state, false);
    if (typeof container.__hmbImageAssetSearchDraft === "string") {
      state.search = container.__hmbImageAssetSearchDraft.slice(0, 256);
    }
    container.__hmbImageAssetLatestState = state;
    catalogPages.wake();
    hmbRegisterImageAssetThumbnailConsumer(
      container,
      state,
      consumeThumbnailPresentationPatch,
    );
    hmbRegisterImageAssetCatalogProbeConsumer(
      container,
      state,
      consumeCatalogProbeResult,
      wakeCatalogPolling,
    );
    hmbStartImageAssetCatalogPolling(container, state);
    hmbResumeImageAssetThumbnailRequest(container, state, props);
    const refreshReview = hmbSyncImageAssetRefreshReview(container, state);
    const markup = hmbScopeWidgetStyleMarkup(render(
      state,
      container.__hmbImageAssetRegistrationDraft || null,
      container.__hmbImageAssetRenderLimit || IMAGE_ASSET_RENDER_WINDOW,
      container.__hmbImageAssetRenderOffset || 0,
      refreshReview,
    ), ".hmb-image-assets");
    hmbPatchImageAssetMarkup(container, markup);
    if (container.__hmbImageAssetRegistrationDraft) {
      const root = container.querySelector(".hmb-image-assets");
      const expanded = root?.querySelector?.("[data-library-expanded]");
      Array.from(expanded?.children || []).forEach((element) => {
        if (element.hasAttribute?.("data-registration-backdrop")) return;
        element.setAttribute?.("inert", "");
        element.setAttribute?.("aria-hidden", "true");
      });
    }
    hmbSetImageAssetRefreshReviewInert(container, Boolean(refreshReview && !container.__hmbImageAssetRegistrationDraft));
    hmbPrepareImageAssetCanvasGestures(container);
    hmbInstallImageAssetNativeHeader(container)?.sync();
    restoreReusableImageAssets(container, reusableImages);
    concealNativeProjectRootPicker(container);
    installEvents(container, state, props, remount, listeners);
    hmbRebuildImageAssetIndexes(container, state);
    restoreImageAssetUi(container, state, uiMemory);
    if (hierarchyDialog && container.__hmbHierarchyDialog === hierarchyDialog) {
      if (!hierarchyDialog.isConnected) (container.ownerDocument?.body || container.querySelector(".hmb-image-assets"))?.appendChild(hierarchyDialog);
      if (!hierarchyDialog.open) hierarchyDialog.showModal?.();
    }
    if (refreshReview && !container.__hmbImageAssetRegistrationDraft) {
      const backdrop = container.querySelector("[data-refresh-review-backdrop]");
      const active = typeof document !== "undefined" ? document.activeElement : null;
      if (!active || !backdrop?.contains?.(active)) {
        backdrop?.querySelector?.("[data-refresh-review-cancel]")?.focus?.();
      }
    }
    delete container.__hmbImageAssetCompactUiMemory;
    const currentNodeRoot = findNodeRoot(container);
    if (
      !container.__hmbImageAssetCompact
      && (
        currentNodeRoot?.getAttribute?.(IMAGE_ASSET_COMPACT_NODE_ATTRIBUTE) === "true"
        || hmbImageAssetCompactRegistryHas(container)
      )
    ) {
      hmbSetImageAssetLibraryCompact(container, true, { geometry: false });
    }
    hmbScheduleImageAssetThumbnailRequest(container, state, props, {
      includeWindow: !container.__hmbImageAssetCompact,
    });
    return state;
  };

  container.__hmbImageAssetRefreshAfterCompactExpand = () => {
    if (container.__hmbImageAssetExpandedDirty) {
      delete container.__hmbImageAssetExpandedDirty;
      state = remount(container.__hmbImageAssetLatestState || state);
    } else {
      delete container.__hmbImageAssetCompactUiMemory;
    }
    return state;
  };

  const applyProps = (nextProps = {}) => {
    rememberNodeInternalsUpdater(nextProps);
    const presentationPatch = hmbApplyImageAssetThumbnailPresentationPatch(
      container.__hmbImageAssetLatestState || state,
      nextProps?.thumbnailPresentationPatch || nextProps?.presentationPatch,
    );
    if (presentationPatch) {
      props = hmbUpdateImageAssetPropsReference(props, nextProps);
      hmbInvalidateImageAssetPublication(container);
      state = presentationPatch.state;
      container.__hmbImageAssetLatestState = state;
      hmbAcceptImageAssetThumbnailResult(container, state);
      hmbPatchImageAssetThumbnailMedia(
        container,
        state,
        presentationPatch.changedAssetLibraryIds,
      );
      hmbScheduleImageAssetThumbnailRequest(container, state, props, {
        includeWindow: !container.__hmbImageAssetCompact,
      });
      return;
    }
    const previousPropValue = props?.value;
    if (nextProps?.value === previousPropValue) {
      // A callback-only host update does not change catalog authority. Keep
      // the new callbacks, but avoid normalizing/stringifying the same O(N)
      // state again.
      props = hmbUpdateImageAssetPropsReference(props, nextProps);
      return;
    }
    const rawIncoming = parseValue(nextProps?.value);
    const commandEcho = imageAssetCompactEditEcho(container, nextProps?.value, rawIncoming);
    if (commandEcho) {
      if (commandEcho.current) props = hmbUpdateImageAssetPropsReference(props, nextProps);
      return;
    }
    const incomingState = normalizeState(hmbImageAssetLocalPageProjection(rawIncoming,state,container));
    incomingState.image_bash_workspace_request = {};
    const queuedOwnerAction = container.__hmbImageAssetPendingSlowAction;
    if (
      queuedOwnerAction
      && queuedOwnerAction.token === container.__hmbImageAssetSlowActionToken
      && queuedOwnerAction.mountToken === container.__hmbImageAssetMountToken
    ) {
      // Revision clocks belong to an owner. Only an explicit replacement while
      // a project action awaits its first paint can reset these watermarks;
      // ordinary lower-revision echoes keep the existing stale-state policy.
      const rawRouting = parseValue(nextProps?.value)?.shot_routing;
      const incomingRuntime = imageAssetThumbnailRuntimeId(incomingState);
      const incomingChannel = clean(incomingState.shot_routing?.channel_uuid);
      const runtimeChanged = queuedOwnerAction.runtimeId && incomingRuntime
        && clean(rawRouting?.publisher_instance_uuid) === incomingRuntime
        && incomingRuntime !== queuedOwnerAction.runtimeId;
      const channelChanged = queuedOwnerAction.channelUuid && incomingChannel
        && clean(rawRouting?.channel_uuid) === incomingChannel
        && incomingChannel !== queuedOwnerAction.channelUuid;
      if (runtimeChanged || channelChanged) {
        delete container.__hmbImageAssetPendingSlowAction;
        delete container.__hmbImageAssetSlowActionToken;
        hmbSetImageAssetBusy(container, false);
        hmbForgetImageAssetStateEcho(container);
        delete container.__hmbImageAssetCurrentScanRevision;
        delete container.__hmbImageAssetCurrentUiEditRevision;
        delete container.__hmbImageAssetLatestLocalUiEditRevision;
        delete container.__hmbImageAssetCanonicalSerialization;
      }
    }
    if (hmbImageAssetRevisionDisposition(container, incomingState) !== "stale") {
      container.__hmbImageAssetAcceptedEditCatalogIdentity = imageAssetEditCatalogIdentity(incomingState);
    }
    hmbRememberImageAssetPresentation(incomingState);
    hmbAdoptImageAssetPresentation(incomingState);
    if (imageAssetThumbnailOnlyTransition(
      state,
      incomingState,
      container.__hmbImageAssetThumbnailPendingRequestId,
    )) {
      props = hmbUpdateImageAssetPropsReference(props, nextProps);
      hmbInvalidateImageAssetPublication(container);
      const merged = hmbMergeImageAssetThumbnailResponse(
        state,
        incomingState,
        container.__hmbImageAssetThumbnailPendingRequestId,
      );
      const completed = hmbImageAssetThumbnailResultIds(merged);
      state = merged;
      container.__hmbImageAssetLatestState = state;
      hmbRebuildImageAssetIndexes(container, state);
      hmbAcceptImageAssetThumbnailResult(container, state);
      hmbPatchImageAssetThumbnailMedia(container, state, completed);
      hmbScheduleImageAssetThumbnailRequest(container, state, props, {
        includeWindow: !container.__hmbImageAssetCompact,
      });
      return;
    }
    container.__hmbImageAssetIncomingState = incomingState;
    const consumedStateEcho = hmbConsumeImageAssetStateEcho(container, nextProps);
    const incomingSerialized = container.__hmbImageAssetIncomingSerialized;
    delete container.__hmbImageAssetIncomingSerialized;
    if (consumedStateEcho) {
      // A delayed local echo is older than both the visible state and the
      // callback set delivered with its newer sibling.  Ignore it wholesale;
      // otherwise the next user action can publish through an obsolete host
      // callback even though the card DOM correctly stayed on the newer state.
      if (container.__hmbImageAssetLastConsumedEchoWasStale) {
        const incomingThumbnailState = incomingState;
        const localThumbnailState = container.__hmbImageAssetLatestState || state;
        const priorThumbnailRevision = localThumbnailState.thumbnail_revision;
        const merged = hmbMergeImageAssetThumbnailResponse(
          localThumbnailState,
          incomingThumbnailState,
          container.__hmbImageAssetThumbnailPendingRequestId,
        );
        if (merged.thumbnail_revision > priorThumbnailRevision) {
          state = merged;
          container.__hmbImageAssetLatestState = state;
          hmbRebuildImageAssetIndexes(container, state);
          hmbAcceptImageAssetThumbnailResult(container, state);
          hmbPatchImageAssetThumbnailMedia(
            container,
            state,
            hmbImageAssetThumbnailResultIds(state),
          );
          hmbScheduleImageAssetThumbnailRequest(container, state, props, {
            includeWindow: !container.__hmbImageAssetCompact,
          });
        }
        return;
      }
      props = hmbUpdateImageAssetPropsReference(props, nextProps);
      return;
    }
    const pendingSlowAction = container.__hmbImageAssetPendingSlowAction;
    if (
      pendingSlowAction
      && pendingSlowAction.token === container.__hmbImageAssetSlowActionToken
      && pendingSlowAction.mountToken === container.__hmbImageAssetMountToken
    ) {
      const sameCatalog = imageAssetProjectPathKey(incomingState.catalog_root)
        === imageAssetProjectPathKey(pendingSlowAction.catalogRoot);
      const sameProject = imageAssetProjectPathKey(incomingState.project_root)
        === imageAssetProjectPathKey(pendingSlowAction.projectRoot);
      const sameOwner = imageAssetThumbnailRuntimeId(incomingState) === pendingSlowAction.runtimeId
        && clean(incomingState.shot_routing?.channel_uuid) === pendingSlowAction.channelUuid;
      const targetKey = imageAssetProjectPathKey(pendingSlowAction.targetProjectRoot);
      const targetPresent = !targetKey || incomingState.projects.some((project) => (
        imageAssetProjectPathKey(project.path) === targetKey
      ));
      const advancedClock = hmbNormalizeImageAssetRevision(incomingState.scan_revision)
        > pendingSlowAction.scanRevision
        || hmbNormalizeImageAssetRevision(incomingState[IMAGE_ASSET_UI_EDIT_REVISION_KEY])
          > pendingSlowAction.uiEditRevision;
      if (
        sameOwner && sameCatalog && sameProject
        && (targetPresent || (!incomingState.projects.length && !advancedClock))
      ) {
        // Keep the selected DOM and loading feedback for this bounded paint
        // interval. Metadata stays authoritative and becomes the command's
        // base; an old non-busy echo cannot cancel the deferred user action.
        props = hmbUpdateImageAssetPropsReference(props, nextProps);
        hmbInvalidateImageAssetPublication(container);
        state = !targetPresent && !incomingState.projects.length && !advancedClock
          ? normalizeState({ ...incomingState, projects: pendingSlowAction.projects })
          : incomingState;
        container.__hmbImageAssetLatestState = state;
        hmbRememberImageAssetRevisionState(container, state, false);
        hmbAcceptImageAssetThumbnailResult(container, state);
        return;
      }
      // A different authoritative context or removal of the selected target
      // wins over an unpublished action. Its scheduled callback is now inert.
      delete container.__hmbImageAssetPendingSlowAction;
      delete container.__hmbImageAssetSlowActionToken;
      hmbSetImageAssetBusy(container, false);
    }
    if (container.__hmbImageAssetSelectionCommitPending) {
      // Preserve the latest authoritative snapshot and merge only the local
      // selection delta into it when the optimistic click is published.
      props = hmbUpdateImageAssetPropsReference(props, nextProps);
      const hasBasePropValue = Object.prototype.hasOwnProperty.call(
        container,
        "__hmbImageAssetSelectionBasePropValue",
      );
      if (
        hasBasePropValue
        && nextProps?.value === container.__hmbImageAssetSelectionBasePropValue
      ) {
        // The exact pre-click prop is already represented by the retained
        // authority stamp. It cannot supersede the newer local selection.
        return;
      }
      hmbInvalidateImageAssetPublication(container);
      const nextState = incomingState;
      hmbAcceptImageAssetThumbnailResult(container, nextState);
      container.__hmbImageAssetPendingAuthoritativeProps = {
        state: nextState,
      };
      return;
    }
    props = hmbUpdateImageAssetPropsReference(props, nextProps);
    hmbInvalidateImageAssetPublication(container);
    const nextState = incomingState;
    hmbAcceptImageAssetThumbnailResult(container, nextState);
    const currentValue = hmbCachedImageAssetSerialization(container, state)
      || JSON.stringify(state);
    const nextValue = typeof incomingSerialized === "string"
      ? incomingSerialized
      : JSON.stringify(nextState);
    if (currentValue === nextValue) return;
    if (hmbDeferImageAssetPropsDuringRegistration(container, props)) return;
    remount(nextState);
    if (nextState.scan_busy) {
      container.__hmbImageAssetBusy = true;
    } else {
      delete container.__hmbImageAssetSlowActionToken;
      hmbSetImageAssetBusy(container, false);
    }
  };
  container.__hmbImageAssetApplyProps = applyProps;

  const cleanup = () => {
    container.__hmbHierarchyDispose?.();
    container.__hmbHierarchyDialog?.close?.();
    container.__hmbHierarchyDialog?.remove?.();
    delete container.__hmbHierarchyDialog;
    catalogPages.cleanup();
    cleanupImportHandles();
    hmbCancelImageAssetCompactGeometrySettle(container);
    if (container.__hmbImageAssetExpandedGeometry) {
      hmbSetImageAssetCompactShellGeometry(container, false);
    }
    hmbSetImageAssetNativeResizeLocked(container, false);
    hmbDetachImageAssetRegistryContainer(container);
    hmbUnregisterImageAssetThumbnailConsumer(container);
    hmbUnregisterImageAssetCatalogProbeConsumer(container);
    hmbStopImageAssetCatalogPolling(container);
    hmbInvalidateImageAssetPublication(container);
    // Library removal must be publication-free. A normal structural remount
    // still flushes visible optimistic feedback, but teardown cancels its
    // pending frame/timer so deleting and immediately reloading the Library
    // cannot start an onChange against a disposed widget.
    hmbCancelImageAssetSelectionCommit(container);
    hmbForgetImageAssetStateEcho(container);
    hmbCancelImageAssetThumbnailRequest(container);
    // Invalidate an explicit project action that was queued for the next paint.
    // Its bounded RAF/task may still run, but the token guard makes it inert.
    delete container.__hmbImageAssetPendingSlowAction;
    delete container.__hmbImageAssetSlowActionToken;
    clearListeners();
    container.__hmbImageAssetRefreshReviewCleanup?.();
    delete container.__hmbImageAssetRefreshReviewCleanup;
    if (container.__hmbImageAssetCleanup === cleanup) {
      delete container.__hmbImageAssetCleanup;
    }
    if (container.__hmbImageAssetApplyProps === applyProps) {
      delete container.__hmbImageAssetApplyProps;
    }
    delete container.__hmbImageAssetDragSession;
    delete container.__hmbSuppressImageAssetCardClick;
    delete container.__hmbImageAssetRegistrationDraft;
    delete container.__hmbImageAssetRegistrationReturnFocus;
    delete container.__hmbImageAssetDeferredProps;
    delete container.__hmbImageAssetSelectionCommitPending;
    delete container.__hmbImageAssetSelectionCommitRunning;
    delete container.__hmbImageAssetSelectionCommitJob;
    delete container.__hmbImageAssetSelectionBase;
    delete container.__hmbImageAssetSelectionBaseAuthority;
    delete container.__hmbImageAssetSelectionBasePropValue;
    delete container.__hmbImageAssetSelectionBaseCurrentScanRevision;
    delete container.__hmbImageAssetSelectionBaseCurrentUiEditRevision;
    delete container.__hmbImageAssetSelectionBaseLatestLocalUiEditRevision;
    delete container.__hmbImageAssetPendingAuthoritativeProps;
    delete container.__hmbImageAssetCurrentScanRevision;
    delete container.__hmbImageAssetCurrentUiEditRevision;
    delete container.__hmbImageAssetLatestLocalUiEditRevision;
    delete container.__hmbImageAssetLastConsumedEchoWasStale;
    delete container.__hmbImageAssetCanonicalSerialization;
    delete container.__hmbImageAssetThumbnailScheduleToken;
    if (container.__hmbImageAssetSearchTimer != null && typeof clearTimeout === "function") {
      clearTimeout(container.__hmbImageAssetSearchTimer);
    }
    delete container.__hmbImageAssetSearchTimer;
    delete container.__hmbImageAssetCardByLibraryId;
    delete container.__hmbImageAssetByLibraryId;
    delete container.__hmbImageAssetBySourceUid;
    delete container.__hmbImageAssetSelectedCardByLibraryId;
    delete container.__hmbImageAssetCompactCardsByLibraryId;
    delete container.__hmbImageAssetBashCardsByLibraryId;
    delete container.__hmbImageAssetThumbnailConsumer;
    delete container.__hmbImageAssetCatalogProbeConsumer;
    delete container.__hmbImageAssetRenderLimit;
    delete container.__hmbImageAssetRenderOffset;
    delete container.__hmbImageAssetExpandedFragment;
    delete container.__hmbImageAssetExpandedElement;
    delete container.__hmbImageAssetCompact;
    delete container.__hmbImageAssetCompactUiMemory;
    delete container.__hmbImageAssetExpandedDirty;
    delete container.__hmbImageAssetLatestState;
    delete container.__hmbImageAssetRefreshAfterCompactExpand;
    delete container.__hmbImageAssetUpdateNodeInternals;
    delete container.__hmbImageAssetResizeLockRoot;
    delete container.__hmbImageAssetExpandedGeometry;
    delete container.__hmbImageAssetCompactGeometryFrame;
    delete container.__hmbImageAssetCompactGeometryFramesLeft;
    delete container.__hmbImageAssetBusyControls;
    delete container.__hmbImageAssetBusy;
    if (Number(container.__hmbImageAssetMountToken) === mountToken) {
      delete container.__hmbImageAssetMountToken;
    }
    container.removeAttribute?.("data-hmb-node-delete-protected");
    container.__hmbImageAssetNativeHeader?.cleanup();
    container.innerHTML = "";
  };
  container.__hmbImageAssetCleanup = cleanup;
  remount(state);
  catalogPages.wake();
  return {
    cleanup: container.__hmbImageAssetCleanupProxy,
    update(nextProps) {
      applyProps(nextProps || {});
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

function hmbNativeStockSafetyImplementation(container, props) {
  return hmbNativeUiContract(container, props, hmbNativeUiImplementation, { kind: "asset", allowControl: target => Boolean(target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]")) });
}

// HMB_NATIVE_STOCK_SAFETY_V1_BEGIN
// Public DOM capture only. Never inspect React internals, replay Delete, or
// pretend a disk/Git update installed the native editor safety contract.
function hmbAcquireNativeStockSafety(container) {
  const doc = container?.ownerDocument, win = doc?.defaultView;
  if (!doc?.documentElement || !win?.addEventListener || !doc.createElement) return null;
  const key = "__HMB_NATIVE_STOCK_SAFETY_V1__";
  let shared = doc[key];
  if (!shared) {
    const owners = new Set(), identities = new Map();
    let contextNode = null, badge = null, notice = null, disposed = false;
    const nativeReady = () => doc.documentElement.getAttribute("data-hmb-native-deletion-guard") === "engine-preflight"
      && doc.documentElement.getAttribute("data-hmb-native-deletion-protection-version") === "2";
    const rootOf = value => value?.closest?.(".react-flow__node[data-id]") || null;
    const roots = () => {
      for (const owner of owners) {
        const node = owner.active && owner.container?.isConnected ? rootOf(owner.container) : null;
        if (node) identities.set(node, node.getAttribute("data-id"));
      }
      // A stock fold/virtualized widget unmount is not a node deletion. Keep
      // its exact outer DOM identity until that node actually leaves the view.
      for (const [node] of identities) {
        if (!node.isConnected) identities.delete(node);
        else identities.set(node, node.getAttribute("data-id")); // Native rename keeps this exact retained outer node.
      }
      return new Set(identities.keys());
    };
    const isEditing = target => Boolean(target?.closest?.("input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor"));
    const canvasOf = node => node?.closest?.(".react-flow");
    const managed = () => {
      const current = roots();
      if (!current.size) return false;
      const selected = Array.from(doc.querySelectorAll(".react-flow__node.selected,.react-flow__node[aria-selected='true'],.react-flow__node[data-selected='true']"));
      if (selected.some(node => current.has(node))) return true;
      // Native group ownership is not a public DOM contract. Do not guess its
      // children; an unpatched group in an HMB canvas waits for safe installation.
      return selected.some(node => node.classList.contains("react-flow__node-GroupNode")
        && Array.from(current).some(child => canvasOf(child) && canvasOf(child) === canvasOf(node)));
    };
    const ownedTarget = target => roots().has(rootOf(target));
    const internalTarget = target => Boolean(target?.closest?.("[data-hmb-native-node-type]"))
      && !target.closest("[data-hmb-native-identity],[data-hmb-native-actions]");
    const deleteControl = target => {
      const button = target?.closest?.("button,[role='menuitem']");
      if (!button || internalTarget(button)) return null;
      const label = `${button.getAttribute("aria-label") || ""} ${button.getAttribute("title") || ""} ${button.textContent || ""}`.trim();
      const nodeMenu = /^Delete Node(?:\s|$)/i.test(label);
      const trash = Boolean(button.querySelector("svg.lucide-trash,svg.lucide-trash-2,[data-lucide='trash'],[data-lucide='trash-2']"));
      if (!nodeMenu && !(trash && button.closest(".react-flow"))) return null;
      return { button, nodeMenu };
    };
    const dismiss = () => { notice?.remove(); notice = null; };
    const show = () => {
      if (disposed || nativeReady()) return;
      if (notice?.isConnected) { notice.querySelector("button")?.focus(); return; }
      notice = doc.createElement("section");
      notice.setAttribute("data-hmb-native-safety-notice", "required");
      notice.setAttribute("role", "alert");
      Object.assign(notice.style, { position: "fixed", zIndex: "2147483647", right: "20px", bottom: "64px", maxWidth: "420px", padding: "18px", border: "1px solid #b89458", borderRadius: "18px", background: "#151c29", color: "#f8fafc", font: "13px/1.6 system-ui,sans-serif", boxShadow: "0 8px 32px #0008" });
      const title = doc.createElement("strong"); title.textContent = "HMB 업데이트 상태 확인이 필요합니다";
      const text = doc.createElement("p");
      text.textContent = "Override 업데이트 로그에서 current/applied 확인 → 작업 저장 → Griptape 완전 종료 → 재시작 후 다시 확인하세요. current/applied는 디스크 파일 상태이며 현재 화면의 통합 상태를 보장하지 않습니다. 실패 또는 상태 확인 불가 시 HMB 업데이트 로그의 원인을 확인하세요. 최신 UI와 엔진 보호가 확인되기 전까지 HMB 노드 삭제를 일시 중단하며, 연결된 노드는 계속 보호됩니다.";
      const close = doc.createElement("button"); close.type = "button"; close.textContent = "확인";
      Object.assign(close.style, { border: "1px solid #64748b", borderRadius: "999px", background: "#243044", color: "#f8fafc", padding: "6px 18px", cursor: "pointer" });
      close.addEventListener("click", dismiss); notice.append(title, text, close); doc.body.append(notice); close.focus();
    };
    const stop = event => { event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation(); show(); };
    const keydown = event => {
      if (disposed || nativeReady() || isEditing(event.target)) return;
      if (["Delete", "Backspace"].includes(event.key) && managed()) stop(event);
    };
    const click = event => {
      if (disposed || nativeReady()) return;
      const action = deleteControl(event.target);
      if (action && (ownedTarget(action.button) || managed()
          || action.nodeMenu && contextNode?.isConnected && roots().has(contextNode))) stop(event);
      else if (!event.target?.closest?.("[data-hmb-native-safety-notice],[data-hmb-native-safety-status]")) contextNode = null;
    };
    const contextmenu = event => { contextNode = rootOf(event.target); };
    const dispose = () => {
      if (disposed) return;
      disposed = true; observer?.disconnect(); badge?.remove(); dismiss(); contextNode = null;
      win.removeEventListener("keydown", keydown, true); win.removeEventListener("click", click, true); win.removeEventListener("contextmenu", contextmenu, true);
      if (doc[key] === shared) delete doc[key];
    };
    const sync = () => {
      if (disposed) return;
      const retained = roots();
      if (!owners.size && !retained.size) { dispose(); return; }
      if (nativeReady() || !retained.size) { badge?.remove(); badge = null; dismiss(); return; }
      if (badge?.isConnected || !doc.body) return;
      badge = doc.createElement("button"); badge.type = "button";
      badge.setAttribute("data-hmb-native-safety-status", "required");
      badge.setAttribute("aria-label", "HMB Override 업데이트 및 재시작 안내");
      badge.textContent = "HMB 업데이트 확인 · 안전 삭제 보호 중";
      Object.assign(badge.style, { position: "fixed", zIndex: "2147483646", right: "20px", bottom: "20px", border: "1px solid #b89458", borderRadius: "999px", padding: "7px 14px", background: "#151c29", color: "#f5d49a", font: "12px system-ui,sans-serif", cursor: "pointer", boxShadow: "0 4px 18px #0006" });
      badge.addEventListener("click", show); doc.body.append(badge);
    };
    const observer = typeof win.MutationObserver === "function" ? new win.MutationObserver(sync) : null;
    observer?.observe(doc.documentElement, { attributes: true, attributeFilter: ["data-hmb-native-deletion-guard", "data-hmb-native-deletion-protection-version", "data-id"], childList: true, subtree: true });
    win.addEventListener("keydown", keydown, true); win.addEventListener("click", click, true); win.addEventListener("contextmenu", contextmenu, true);
    shared = { owners, sync, release(owner) {
      owner.active = false; owners.delete(owner);
      sync();
    } };
    doc[key] = shared;
  }
  const owner = { container, active: true };
  shared.owners.add(owner);
  shared.sync();
  return { refresh() { if (owner.active) shared.sync(); }, cleanup() { if (owner.active) shared.release(owner); } };
}

function hmbNativeStockSafetyContract(container, props, mount) {
  const previous = container?.__hmbNativeStockSafety;
  const lease = previous?.active ? previous.lease : hmbAcquireNativeStockSafety(container);
  let handle;
  try { handle = mount(container, props); }
  catch (error) { if (!previous?.active) lease?.cleanup(); throw error; }
  lease?.refresh();
  if (!lease) return handle;
  if (previous?.active && previous.handle === handle) return previous.proxy;
  if (previous) previous.active = false;
  const state = { active: true, lease, handle, proxy: null };
  state.proxy = {
    update(next) {
      if (!state.active) return;
      handle?.update?.(next); lease.refresh();
    },
    cleanup() {
      if (!state.active) return;
      state.active = false;
      try { if (typeof handle === "function") handle(); else handle?.cleanup?.(); }
      finally { lease.cleanup(); if (container.__hmbNativeStockSafety === state) delete container.__hmbNativeStockSafety; }
    },
  };
  container.__hmbNativeStockSafety = state;
  return state.proxy;
}
// HMB_NATIVE_STOCK_SAFETY_V1_END

export default function HMBImageAssetLibraryWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
