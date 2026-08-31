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
const MAX_IMAGE_ASSET_REVISION = Number.MAX_SAFE_INTEGER;
const IMAGE_ASSET_UI_EDIT_REVISION_KEY = "ui_edit_revision";
const ROOT_FOLDER_KEY = "$root";
const IMAGE_ASSET_STATE_VERSION = 4;
const IMAGE_TAXONOMY_SCHEMA = "hmb-image-taxonomy";
const IMAGE_TAXONOMY_VERSION = 3;
const IMAGE_ASSET_SELECTION_COMMIT_FALLBACK_MS = 120;
const IMAGE_ASSET_ECHO_EXPIRY_MS = 1500;
// Search covers the complete in-memory catalog, but foreground DOM work stays
// bounded for projects containing thousands of images.
const IMAGE_ASSET_RENDER_WINDOW = 60;
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

export function hmbRememberImageAssetPresentation(state) {
  const entry = imageAssetPresentationCacheEntry(state, true);
  if (!entry || !Array.isArray(state?.assets)) return 0;
  let remembered = 0;
  state.assets.forEach((asset) => {
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

function hmbUnregisterImageAssetThumbnailConsumer(container) {
  const registry = imageAssetThumbnailBridgeRegistry();
  const runtimeId = clean(container?.__hmbImageAssetThumbnailConsumerRuntimeId);
  const token = container?.__hmbImageAssetThumbnailConsumerToken;
  const current = runtimeId ? registry?.get(runtimeId) : null;
  if (current && token && current.consumerToken === token) {
    if (current.dispatch) {
      const { consumer: _consumer, consumerToken: _consumerToken, ...bridge } = current;
      registry.set(runtimeId, bridge);
    } else {
      registry.delete(runtimeId);
    }
  }
  delete container?.__hmbImageAssetThumbnailConsumerRuntimeId;
  delete container?.__hmbImageAssetThumbnailConsumerToken;
}

function hmbUnregisterImageAssetCatalogProbeConsumer(container) {
  const registry = imageAssetThumbnailBridgeRegistry();
  const runtimeId = clean(container?.__hmbImageAssetCatalogProbeRuntimeId);
  const token = container?.__hmbImageAssetCatalogProbeConsumerToken;
  const current = runtimeId ? registry?.get(runtimeId) : null;
  if (current && token && current.catalogConsumerToken === token) {
    const {
      catalogConsumer: _catalogConsumer,
      catalogConsumerToken: _catalogConsumerToken,
      catalogWake: _catalogWake,
      ...bridge
    } = current;
    if (bridge.dispatch || bridge.consumer) registry.set(runtimeId, bridge);
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
  ) return true;
  hmbUnregisterImageAssetCatalogProbeConsumer(container);
  const registry = imageAssetThumbnailBridgeRegistry();
  const token = `hmb-image-catalog-consumer-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const current = registry?.get(runtimeId) || {};
  registry?.set(runtimeId, {
    ...current,
    catalogConsumer: consumer,
    catalogConsumerToken: token,
    catalogWake: typeof wake === "function" ? wake : null,
  });
  container.__hmbImageAssetCatalogProbeRuntimeId = runtimeId;
  container.__hmbImageAssetCatalogProbeConsumerToken = token;
  container.__hmbImageAssetCatalogProbeConsumer = consumer;
  if (current.catalogPendingResult) {
    const registered = registry?.get(runtimeId) || {};
    const { catalogPendingResult: _pending, ...withoutPending } = registered;
    registry?.set(runtimeId, withoutPending);
    consumer(current.catalogPendingResult);
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
  ) return true;
  hmbUnregisterImageAssetThumbnailConsumer(container);
  const registry = imageAssetThumbnailBridgeRegistry();
  const token = `hmb-image-thumbnail-consumer-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const current = registry?.get(runtimeId) || {};
  registry?.set(runtimeId, { ...current, consumer, consumerToken: token });
  container.__hmbImageAssetThumbnailConsumerRuntimeId = runtimeId;
  container.__hmbImageAssetThumbnailConsumerToken = token;
  container.__hmbImageAssetThumbnailConsumer = consumer;
  if (current.pendingResult) {
    // Consume at most once. The consumer performs exact runtime, pending
    // request, project, manifest, scan, media-signature, and revision checks.
    const registered = registry?.get(runtimeId) || {};
    const { pendingResult: _pendingResult, ...withoutPending } = registered;
    registry?.set(runtimeId, withoutPending);
    consumer(current.pendingResult);
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
    search_placeholder: "이미지 이름, 에셋 ID, 경로, 메인 유형 또는 하위 유형 검색",
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
    main_type: "메인 유형",
    unclassified: "미분류",
    sub_type: "하위 유형",
    sub_unassigned: "하위 유형 후보가 지정되지 않음",
    hmb_project_asset: "HMB 프로젝트 에셋",
    asset_passport: "에셋 등록 정보",
    close_registration: "에셋 등록 창 닫기",
    final_image_name: "최종 이미지 이름",
    main_type_label: "메인 유형 (필수)",
    select_main_type: "메인 유형 선택",
    custom_main_type: "사용자 정의 메인 유형",
    sub_type_label: "하위 유형 (선택)",
    taxonomy_contract: "에이전트 적용 의미",
    select_sub_type: "하위 유형 선택",
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

function normalizeProject(raw) {
  if (!raw || typeof raw !== "object") return null;
  const path = clean(raw.path).replaceAll("\\", "/");
  const name = clean(raw.name) || path.split("/").filter(Boolean).pop() || "";
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
    path: clean(raw.path || raw.asset_path).replaceAll("\\", "/"),
    thumbnail_url: clean(raw.thumbnail_url),
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
  const projectRoot = clean(input.project_root).replaceAll("\\", "/");
  if (projectRoot && !hasExpandedFolders) expandedFolders.push(ROOT_FOLDER_KEY);
  const selectedSourceView = clean(input.selected_source_view).toLowerCase() === "user"
    ? "user"
    : "project";
  const selectedMainType = clean(input.selected_main_type);
  const selectedSubType = clean(input.selected_sub_type);
  return markCanonicalImageAssetState({
    schema: "hmb-image-asset-library-state",
    version: IMAGE_ASSET_STATE_VERSION,
    catalog_root: clean(
      input.catalog_root || "//fin-rcomp1/Composite_Team/projects_AI",
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
    shot_routing: normalizeImageAssetShotRouting(input.shot_routing, assets),
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
    disconnect_import_uid: clean(input.disconnect_import_uid).startsWith("import:")
      ? clean(input.disconnect_import_uid).slice(0, 512)
      : "",
    warnings: uniqueStrings(input.warnings).slice(0, 100),
    error: clean(input.error),
    status: {
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
  hmbRememberImageAssetPresentation(local);
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

function imageAssetShotAssets(state, shot = activeImageAssetShot(state)) {
  if (!shot || !Array.isArray(state?.assets)) return [];
  const bySourceUid = new Map(
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
  const routing = ensureImageAssetShotRouting(state);
  const shot = routing?.shots.find((item) => item.shot_uuid === imageAssetUuid(shotUuid));
  const name = clean(value).slice(0, 128);
  if (!shot || !name || name === shot.name) return false;
  shot.name = name;
  shot.name_is_custom = true;
  bumpImageAssetShotRouting(routing, shot);
  return true;
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

function hmbRememberImageAssetStateEcho(container, value, publicationToken) {
  if (!container || typeof value !== "string") return false;
  const prior = Array.isArray(container.__hmbImageAssetPendingStateEchoes)
    ? container.__hmbImageAssetPendingStateEchoes
    : [];
  container.__hmbImageAssetPendingStateEchoes = [
    ...prior.filter((item) => item?.value !== value),
    { value, publicationToken },
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

export function hmbConsumeImageAssetStateEcho(container, nextProps = {}) {
  if (!container) return false;
  container.__hmbImageAssetLastConsumedEchoWasStale = false;
  delete container.__hmbImageAssetIncomingSerialized;
  let incomingState = null;
  try {
    const retainedIncomingState = container.__hmbImageAssetIncomingState;
    delete container.__hmbImageAssetIncomingState;
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

export function hmbPublishImageAssetState(
  container,
  props,
  state,
  onFailure = null,
  options = {},
) {
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
  const value = JSON.stringify(normalized);
  const publicationToken = ++imageAssetPublicationSequence;
  if (container) container.__hmbImageAssetPublicationOwner = publicationToken;
  if (options?.suppressMatchingEcho === true) {
    hmbRememberImageAssetStateEcho(container, value, publicationToken);
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

function projectOptions(state) {
  const options = [`<option value="">${escapeHtml(imageAssetText(state, "select_project"))}</option>`];
  state.projects.forEach((project) => {
    const selected = project.path.toLowerCase() === state.project_root.toLowerCase();
    options.push(
      `<option value="${escapeHtml(project.path)}" ${selected ? "selected" : ""}>${escapeHtml(project.name)}</option>`,
    );
  });
  return options.join("");
}

function buildFolderTree(state) {
  const projectAssets = state.assets.filter((asset) => asset.source_kind === "project");
  const root = {
    key: ROOT_FOLDER_KEY,
    path: "",
    label: state.project_id || imageAssetText(state, "select_project"),
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
    return node.assetCount;
  };
  finalize(root);
  const importedAssets = state.assets.filter((asset) => asset.source_kind === "user");
  if (importedAssets.length) {
    root.children.push({
      key: "$imports",
      path: "",
      label: imageAssetText(state, "import_in"),
      sourceView: "user",
      children: [],
      assetCount: importedAssets.length,
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
    "data-asset-key",
    "data-selected-key",
    "data-compact-shot-row",
    "data-compact-asset-key",
    "data-shot-uuid",
    "data-folder-key",
    "data-registration-backdrop",
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
  const selectedForShot = imageAssetShotContains(shot, asset.source_uid);
  const selectionBlocked = selectable && !selectedForShot && selectedCount >= MAX_SHOT_IMAGES;
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
  const candidates = options.includeCatalog === false
    ? [...selectedAssets(canonical), ...visible]
    : [...selectedAssets(canonical), ...visible, ...canonical.assets];
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
      { includeWindow: !container.__hmbImageAssetCompact },
    ).filter((key) => !tracking.failed.has(key));
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
    || image.closest?.("[data-selected-key]");
  const libraryId = clean(
    keyedOwner?.getAttribute?.("data-asset-key")
    || keyedOwner?.getAttribute?.("data-selected-key"),
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
    options,
  ).filter((key) => !tracking.requested.has(key));
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
      options,
    ).filter((key) => !currentTracking.requested.has(key));
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
    .map((asset) => renderAssetCard(asset, selectedCount, state.search, state, shot))
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
  const selectedForShot = imageAssetShotContains(shot, asset.source_uid);
  const selectionBlocked = selectable && !selectedForShot && selectedCount >= MAX_SHOT_IMAGES;
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
  const tray = container?.querySelector?.("[data-shot-tray]") || null;
  if (!uuid || !shot || !tray) return false;
  const mountedShotUuid = imageAssetUuid(tray.getAttribute?.("data-shot-tray"));
  if (mountedShotUuid && mountedShotUuid !== uuid) return false;
  const cards = Array.from(tray.querySelectorAll?.("[data-selected-key]") || []);
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
    const slot = card.querySelector?.(".slot");
    if (slot) slot.textContent = String(index + 1).padStart(2, "0");
  });
  return orderedCards.map((card) => clean(card.getAttribute?.("data-shot-source-uid")));
}

function hmbImageAssetShotForDrag(state, shotUuid) {
  const uuid = imageAssetUuid(shotUuid);
  return (Array.isArray(state?.shot_routing?.shots) ? state.shot_routing.shots : [])
    .find((item) => imageAssetUuid(item?.shot_uuid) === uuid) || null;
}

function hmbImageAssetSelectedCardFromDragEvent(container, event) {
  const target = event?.target?.nodeType === 3 ? event.target.parentElement : event?.target;
  const card = target?.closest?.("[data-selected-key]") || null;
  if (!card || (typeof container?.contains === "function" && !container.contains(card))) return null;
  const tray = card.closest?.("[data-shot-tray]") || null;
  if (!tray || (typeof container?.contains === "function" && !container.contains(tray))) return null;
  return { card, tray, target };
}

function hmbClearImageAssetDropTargets(container) {
  Array.from(container?.querySelectorAll?.(".selected-card.drop-target") || []).forEach((card) => {
    card.classList?.remove?.("drop-target");
  });
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
    Array.from(container.querySelectorAll?.(".selected-card.dragging") || []).forEach((card) => {
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
    const cards = Array.from(container.querySelectorAll?.("[data-selected-key]") || []);
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
    Array.from(container.querySelectorAll?.(".selected-card.dragging") || []).forEach((card) => {
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
          <button type="button" class="passport-register" data-registration-submit ${registrationDraftIsComplete(draft) ? "" : "disabled"}>${escapeHtml(imageAssetText(state, "register_asset"))}</button>
        </footer>
      </section>
    </div>
  `;
}

function renderImageAssetShotStack(state) {
  const routing = ensureImageAssetShotRouting(state);
  const active = routing.shots.find((shot) => shot.shot_uuid === routing.active_shot_uuid)
    || routing.shots[0];
  const isKorean = imageAssetLanguage(state) === "ko";
  return `<section class="shot-stack" data-shot-stack data-channel="${escapeHtml(routing.channel_uuid)}">${routing.shots.map((shot) => {
    const isActive = shot.shot_uuid === active.shot_uuid;
    const palette = hmbImageAssetShotPalette(shot.number);
    const shotAssets = imageAssetShotAssets(state, shot);
    const number = String(shot.number).padStart(2, "0");
    const addButton = shot.number === 1
      ? `<button type="button" class="shot-add" data-shot-add ${routing.shots.length >= MAX_IMAGE_ASSET_SHOTS ? "disabled" : ""}>+ Shot</button>`
      : "";
    const tray = isActive
      ? `<div class="tray-scroll" data-shot-tray="${escapeHtml(shot.shot_uuid)}">${shotAssets.map((asset, index) => renderSelectedCard(asset, index, shotAssets, state, shot)).join("") || `<div class="tray-empty">${escapeHtml(imageAssetText(state, "tray_empty"))}</div>`}</div>`
      : "";
    return `<section class="shot-panel ${isActive ? "active" : "collapsed"}" data-shot-panel data-shot-number="${shot.number}" data-shot-uuid="${escapeHtml(shot.shot_uuid)}" style="--shot-accent:${palette.accent};--shot-rgb:${palette.rgb}">
      <header class="shot-panel-head">
        <button type="button" class="shot-panel-toggle" data-shot-tab="${escapeHtml(shot.shot_uuid)}" aria-expanded="${isActive ? "true" : "false"}" title="${escapeHtml(isKorean ? "클릭하여 Shot 열기" : "Open Shot")}">
          <small>${number}</small><b data-shot-name>${escapeHtml(shot.name)}</b><span>${escapeHtml(imageAssetText(state, "selected_images"))}</span><em>${shotAssets.length}/${MAX_SHOT_IMAGES}</em><i>REMOTE</i>
        </button><button type="button" class="shot-rename" data-shot-rename="${escapeHtml(shot.shot_uuid)}" aria-label="${escapeHtml(imageAssetText(state, "rename_shot"))}" title="${escapeHtml(imageAssetText(state, "rename_shot"))}">✎</button><button type="button" class="shot-delete" data-shot-delete="${escapeHtml(shot.shot_uuid)}" aria-label="${escapeHtml(imageAssetText(state, "delete_shot"))}" title="${escapeHtml(routing.shots.length <= 1 ? imageAssetText(state, "keep_one_shot") : imageAssetText(state, "delete_shot"))}" ${routing.shots.length <= 1 ? "disabled" : ""}>&times;</button>${addButton}
      </header>${tray}
    </section>`;
  }).join("")}</section>`;
}

export function hmbImageAssetCompactShotRows(state) {
  const routing = ensureImageAssetShotRouting(state);
  if (!routing) return [];
  return routing.shots.slice(0, MAX_IMAGE_ASSET_SHOTS).map((shot) => ({
    shot_uuid: shot.shot_uuid,
    number: shot.number,
    name: shot.name,
    active: shot.shot_uuid === routing.active_shot_uuid,
    palette: hmbImageAssetShotPalette(shot.number),
    assets: imageAssetShotAssets(state, shot).map((asset, index) => ({
      ...asset,
      order: index + 1,
    })),
  }));
}

function renderImageAssetCompactAsset(asset, index, shotUuid) {
  const sourceUid = clean(asset?.source_uid);
  const key = sourceUid || clean(asset?.asset_library_id) || `compact-${index}`;
  const name = clean(asset?.image_name) || clean(asset?.asset_id) || `Image ${index + 1}`;
  const source = imageSource(asset || {});
  const failed = !source && hmbImageAssetThumbnailFailed(asset);
  const media = source
    ? `<img data-hmb-compact-src="${escapeHtml(source)}" alt="" draggable="false" loading="lazy" decoding="async" fetchpriority="low"/>`
    : `<span class="compact-shot-placeholder" aria-hidden="true">${imageAssetThumbnailFallbackMarkup(asset)}</span>`;
  return `<article class="compact-shot-asset ${source ? "" : failed ? "thumbnail-failed" : "thumbnail-loading"}" data-thumbnail-loading="${source || failed ? "false" : "true"}" data-thumbnail-failed="${failed ? "true" : "false"}" data-compact-asset-key="${escapeHtml(key)}" data-shot-source-uid="${escapeHtml(sourceUid)}" data-shot-uuid="${escapeHtml(shotUuid)}" data-compact-order="${index + 1}" title="${escapeHtml(name)}">
      <div class="compact-shot-thumb">${media}<small>${String(index + 1).padStart(2, "0")}</small></div>
      <b>${escapeHtml(name)}</b>
    </article>`;
}

function renderImageAssetCompactShotRow(state, row) {
  const assets = Array.isArray(row?.assets) ? row.assets.slice(0, MAX_SHOT_IMAGES) : [];
  return `<article class="compact-shot-row ${row.active ? "active" : ""}" data-compact-shot-row="${escapeHtml(row.shot_uuid)}" data-shot-number="${row.number}" style="--shot-accent:${row.palette.accent};--shot-rgb:${row.palette.rgb}">
      <header class="compact-shot-head"><small>${String(row.number).padStart(2, "0")}</small><b data-compact-shot-name>${escapeHtml(row.name)}</b><span>${escapeHtml(imageAssetText(state, "selected_images"))}</span><em data-compact-shot-count>${assets.length}/${MAX_SHOT_IMAGES}</em><i>REMOTE</i></header>
      <div class="compact-shot-assets ${assets.length ? "" : "empty"}" data-compact-shot-assets="${escapeHtml(row.shot_uuid)}">${assets.map((asset, index) => renderImageAssetCompactAsset(asset, index, row.shot_uuid)).join("") || `<span class="compact-shot-empty">${escapeHtml(imageAssetText(state, "tray_empty"))}</span>`}</div>
    </article>`;
}

export function hmbRenderImageAssetCompactSummary(state) {
  const rows = hmbImageAssetCompactShotRows(state);
  return `<section class="library-compact-summary" data-library-compact-summary hidden aria-label="HMBImageAssetLibrary Shot summary">${rows.map(
    (row) => renderImageAssetCompactShotRow(state, row),
  ).join("")}</section>`;
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
  container.__hmbImageAssetByLibraryId = assetsById;
  container.__hmbImageAssetBySourceUid = assetsBySourceUid;
  container.__hmbImageAssetCardByLibraryId = cardById;
  container.__hmbImageAssetSelectedCardByLibraryId = selectedById;
  container.__hmbImageAssetCompactCardsByLibraryId = compactById;
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

function renderImageAssetFixedTop(state) {
  return `<header class="top" data-library-toggle-surface="header">
      <div class="mark">IA</div>
      <div class="heading"><b>HMBImageAssetLibrary</b><span>${escapeHtml(displayWindowsPath(state.catalog_root))} → ${escapeHtml(state.project_id || imageAssetText(state, "select_a_project"))}</span></div>
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
      .hmb-image-assets{--bg:#090c16;--panel:#101523;--line:rgba(148,163,184,.19);--accent:#22d3ee;--pink:#f472b6;--asset-selection:#f472b6;--text:#e6edf7;--muted:#8fa3b8;--selection-rgb:244,114,182;--selection-deep-rgb:190,24,93;--selection-secondary-rgb:217,70,239;--selection-text:#f8c6df;--selection-soft:#f3a8ce;--selection-strong:#ffe4f2;--selection-panel:rgba(30,14,30,.9);--selection-card:rgba(61,23,49,.6);--header-tint:rgba(72,35,101,.44);container-type:inline-size;position:relative;width:100%;height:100%;min-height:680px;display:grid;grid-template-rows:58px minmax(0,1fr);overflow:hidden;border:1px solid var(--line);border-radius:11px;background:radial-gradient(circle at 8% -10%,rgba(168,85,247,.16),transparent 34%),linear-gradient(180deg,#0b1020,#060912);color:var(--text);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;font-synthesis:none;-webkit-font-smoothing:antialiased;box-sizing:border-box}
      .hmb-image-assets *{box-sizing:border-box;min-width:0}.top{display:flex;align-items:center;gap:12px;padding:8px 13px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,rgba(72,35,101,.44),rgba(14,23,38,.9) 44%)}.mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border:1px solid rgba(34,211,238,.7);border-radius:8px;background:rgba(8,145,178,.12);color:var(--accent);font-size:11px;font-weight:950}.heading{display:flex;flex:0 1 auto;flex-direction:column;gap:2px;overflow:hidden}.heading b{overflow:hidden;font-size:15px;letter-spacing:.01em;white-space:nowrap;text-overflow:ellipsis}.heading span{max-width:360px;color:var(--muted);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.project-switch{margin-left:auto;display:grid;grid-template-columns:auto auto minmax(150px,260px);align-items:center;gap:7px;min-width:0}.project-actions{display:flex;align-items:center;gap:5px}.project-action{width:31px;height:31px;display:grid;place-items:center;padding:0;border:1px solid rgba(96,165,250,.5);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.3),rgba(15,23,42,.9));color:#93c5fd;font-size:12px;font-weight:950;cursor:pointer}.project-action:hover{border-color:var(--accent);color:#fff;box-shadow:0 0 10px rgba(34,211,238,.2)}.project-action svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.project-switch label{min-width:max-content;color:#aebed0;font-size:8px;font-weight:900;letter-spacing:.08em;white-space:nowrap;word-break:keep-all}.project-switch select{width:100%;height:31px;border:1px solid rgba(148,163,184,.28);border-radius:7px;background:#080d17;color:#edf5ff;padding:0 8px;font-size:10px;outline:none}.project-switch select:focus{border-color:var(--accent)}.status{display:flex;flex:0 1 auto;flex-direction:column;align-items:flex-end;gap:2px;font-size:8px;color:var(--muted)}.status strong{max-width:260px;color:${state.error ? "#fda4af" : "#86efac"};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .workspace{display:grid;grid-template-columns:minmax(230px,252px) minmax(0,1fr);gap:8px;min-height:0;padding:8px}.panel{min-height:0;border:1px solid var(--line);border-radius:9px;background:rgba(8,13,23,.76);overflow:hidden}.tree-panel{display:flex;flex-direction:column}.panel-title{height:35px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 10px;border-bottom:1px solid var(--line);background:rgba(19,27,42,.78);color:#bed0e3;font-size:9px;font-weight:900;letter-spacing:.07em}.panel-title>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;word-break:keep-all}.panel-title b{flex:0 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--accent);font-size:8px}.tree{padding:6px;overflow:auto;scrollbar-gutter:stable}.tree-row{width:100%;min-height:30px;display:grid;grid-template-columns:13px minmax(0,1fr) auto;align-items:center;gap:5px;margin:0 0 3px;padding:5px 8px 5px calc(8px + var(--tree-depth,0) * 14px);border:1px solid transparent;border-radius:6px;background:transparent;color:#96a9bd;font-size:8px;text-align:left;cursor:pointer;transition:border-color 120ms ease,background-color 120ms ease,color 120ms ease}.tree-row i{color:#61778c;font-style:normal}.tree-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tree-row b{color:#587087}.tree-row:hover{border-color:rgba(34,211,238,.3);color:#def9ff}.tree-row.active{border-color:rgba(34,211,238,.52);background:linear-gradient(90deg,rgba(8,145,178,.2),rgba(8,145,178,.04));color:#e7fcff}.tree-row.root{min-height:35px;color:#fff;font-size:10px;font-weight:850}
      .assets-panel{display:flex;flex-direction:column}.toolbar{height:44px;display:flex;align-items:center;gap:8px;padding:7px 9px;border-bottom:1px solid var(--line)}.toolbar input{flex:1;height:30px;border:1px solid rgba(148,163,184,.25);border-radius:7px;background:#070c15;color:#edf5ff;padding:0 9px;font-size:9px;outline:none}.toolbar input:focus{border-color:var(--accent)}.filter-chip{max-width:260px;padding:5px 8px;border:1px solid rgba(244,114,182,.3);border-radius:99px;background:rgba(131,24,67,.1);color:#f8c6df;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-scroll{flex:1;min-height:0;overflow:auto;scrollbar-gutter:stable;padding:9px}.asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}.asset-card{display:grid;grid-template-columns:112px minmax(0,1fr);gap:10px;min-height:152px;padding:9px;border:1px solid rgba(148,163,184,.16);border-radius:9px;background:linear-gradient(145deg,rgba(19,27,42,.86),rgba(9,14,24,.82));cursor:pointer;outline:none;content-visibility:auto;contain-intrinsic-size:167px;transition:border-color 120ms ease,box-shadow 120ms ease,background-color 120ms ease,opacity 120ms ease}.asset-card:hover{border-color:rgba(34,211,238,.34)}.asset-card:focus-visible{box-shadow:0 0 0 2px rgba(34,211,238,.45)}.asset-card.selected{border-color:var(--asset-selection);box-shadow:inset 0 0 0 .3px rgba(244,114,182,.45),0 0 15px rgba(244,114,182,.34),0 0 4px rgba(217,70,239,.55)}.asset-card.selection-blocked{opacity:.58}.asset-card.unregistered{cursor:default}.asset-card.unregistered .asset-state{color:#f3a8ce}.asset-thumb{position:relative;width:112px;height:132px;display:grid;grid-template-rows:2fr 1fr;overflow:hidden;border:1px solid rgba(148,163,184,.2);border-radius:7px;background:#050910;color:#648198;font-size:9px;font-weight:900}.asset-thumb-media{position:relative;display:grid;place-items:center;min-height:0;overflow:hidden;border-bottom:1px solid rgba(148,163,184,.18)}.asset-thumb-media img{width:100%;height:100%;object-fit:cover}.asset-thumb-media>span{display:none}.asset-thumb.fallback .asset-thumb-media img{display:none}.asset-thumb.fallback .asset-thumb-media>span{display:block}.asset-thumb-footer{display:flex;align-items:center;justify-content:center;gap:6px;min-height:0;padding:4px 6px;background:linear-gradient(180deg,#080d16,#050810)}.asset-source-name{min-width:0;flex:1;color:#a8bdd0;font-size:8px;font-weight:800;line-height:1.25;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-extension-badge{flex:0 0 auto;max-width:48px;padding:3px 5px;border:1px solid rgba(34,211,238,.4);border-radius:5px;background:rgba(8,145,178,.1);color:var(--accent);font-family:inherit;font-size:7px;font-weight:900;line-height:1;letter-spacing:.07em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-thumb-media .asset-add{position:absolute;right:5px;bottom:5px;z-index:2}.asset-add{min-width:56px;height:25px;padding:0 13px;border:1px solid rgba(244,114,182,.7);border-radius:99px;background:rgba(131,24,67,.26);color:#ffd5eb;font-size:9px;font-weight:950;letter-spacing:.04em;cursor:pointer;box-shadow:0 0 10px rgba(244,114,182,.16)}.asset-add:hover{border-color:#f9a8d4;background:rgba(190,24,93,.32);box-shadow:0 0 13px rgba(244,114,182,.3)}.asset-content{display:flex;flex-direction:column;gap:8px}.asset-title{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.asset-title-copy{display:flex;flex:1;flex-direction:column;gap:2px;min-width:0}.asset-state{color:var(--accent);font-size:7px;font-weight:900}.asset-id-line{display:flex;align-items:center;gap:5px;min-width:0;color:#9bacc0;font-size:7px;font-weight:500}.asset-id-line em{flex:0 0 auto;color:#6e859c;font-size:6px;font-style:normal;font-weight:900;letter-spacing:.05em}.asset-id-line span{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-meta{display:flex;flex-direction:column;gap:3px;color:#71879c;font-size:7px}.asset-meta b,.asset-meta span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-meta b{color:#bcd0e2}.empty{grid-column:1/-1;padding:30px;border:1px dashed rgba(148,163,184,.2);border-radius:8px;color:#667e94;font-size:9px;text-align:center}.warnings{max-height:64px;overflow:auto;padding:6px 9px;border-top:1px solid rgba(251,191,36,.2);background:rgba(120,53,15,.1);color:#fcd34d;font-size:7px}
      .asset-window-nav{grid-column:1/-1;display:flex;justify-content:center;gap:8px}.asset-window-more{min-width:160px;min-height:34px;border:1px solid rgba(34,211,238,.3);border-radius:8px;background:rgba(8,145,178,.1);color:#a5f3fc;font-size:9px;font-weight:850;cursor:pointer}.asset-window-more:hover,.asset-window-more:focus-visible{border-color:var(--accent);outline:none;background:rgba(8,145,178,.18)}
      @keyframes hmb-image-leaf-pulse{0%,12.5%{opacity:1;filter:brightness(1.65);box-shadow:0 0 7px rgba(226,232,240,.42)}37.5%,100%{opacity:.2;filter:brightness(.62);box-shadow:none}}.thumbnail-loading .thumbnail-placeholder,.thumbnail-loading .asset-thumb-placeholder,.thumbnail-loading .compact-shot-placeholder{display:grid!important;width:100%;height:100%;place-items:center;background:rgba(5,9,16,.82)}.thumbnail-loading .thumbnail-placeholder{min-width:100%;min-height:100%}.hmb-image-leaf-loader{position:relative;display:block!important;pointer-events:none;width:38px!important;height:38px!important;min-width:38px!important;min-height:38px!important;background:transparent!important}.hmb-image-leaf-loader>i{--leaf-angle:calc(var(--leaf-index) * 45deg);position:absolute;left:50%;top:50%;width:6px;height:12px;margin:-6px 0 0 -3px;border-radius:90% 12% 90% 12%;background:linear-gradient(135deg,#fff 4%,#cbd5e1 48%,#64748b 100%);transform:rotate(var(--leaf-angle)) translateY(-13px) rotate(45deg);transform-origin:50% 50%;opacity:.2;animation:hmb-image-leaf-pulse 1s linear infinite;animation-delay:calc(var(--leaf-index) * .125s)}@media (prefers-reduced-motion:reduce){.hmb-image-leaf-loader>i{animation:none;opacity:.45;filter:none;box-shadow:none}.hmb-image-leaf-loader>i:first-child{opacity:.9}}
      .hmb-image-leaf-loader,.hmb-image-leaf-loader *{pointer-events:none}
      .thumbnail-failed .thumbnail-placeholder,.thumbnail-failed .asset-thumb-placeholder,.thumbnail-failed .compact-shot-placeholder{display:grid!important;width:100%;height:100%;place-items:center;background:rgba(5,9,16,.82)}.thumbnail-failed .thumbnail-placeholder{min-width:100%;min-height:100%}.hmb-image-thumbnail-unavailable{display:grid!important;place-items:center;width:30px!important;height:30px!important;border:1px solid rgba(248,113,113,.42);border-radius:50%;background:rgba(69,10,10,.36)!important;color:#fca5a5;font-size:15px;font-weight:950;line-height:1}.thumbnail-failed{animation:none!important}
      .shot-panel .shot-rename{width:29px;height:29px;flex:0 0 29px;padding:0;border:1px solid rgba(var(--shot-rgb),.42);border-radius:7px;background:rgba(var(--shot-rgb),.10);color:var(--shot-accent);font-size:13px;cursor:pointer}.shot-panel .shot-rename:hover,.shot-panel .shot-rename:focus-visible{border-color:var(--shot-accent);background:rgba(var(--shot-rgb),.22);outline:none}.shot-name-input{width:min(180px,100%);height:24px;border:1px solid var(--shot-accent);border-radius:5px;background:#060b13;color:#f8fafc;padding:0 6px;font:inherit;outline:none;box-shadow:0 0 0 2px rgba(var(--shot-rgb),.2)}
      .toolbar-status{flex:0 0 190px;width:190px;min-width:190px;height:30px;display:flex;align-items:center;justify-content:flex-end;overflow:hidden;color:var(--muted);font-size:8px}.toolbar-status strong{display:block;width:100%;color:${state.error ? "#fda4af" : "#86efac"};font-variant-numeric:tabular-nums;letter-spacing:-.02em;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.toolbar .filter-chip{flex:0 0 120px;width:120px;max-width:120px;text-align:center}
      .asset-view-toggle{flex:0 0 31px;width:31px;height:30px;display:grid;place-items:center;padding:0;border:1px solid rgba(96,165,250,.46);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.2),rgba(15,23,42,.88));color:#7dd3fc;cursor:pointer}.asset-view-toggle:hover,.asset-view-toggle:focus-visible,.asset-view-toggle[aria-pressed="true"]{border-color:var(--accent);background:linear-gradient(180deg,rgba(37,99,235,.38),rgba(15,23,42,.94));color:#e0f2fe;outline:none;box-shadow:0 0 10px rgba(34,211,238,.2)}.asset-view-toggle svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
      .hmb-image-assets .asset-card{min-height:167px;padding:10px}.hmb-image-assets .asset-thumb{width:123px;height:145px}.hmb-image-assets .asset-add{min-width:52px;height:28px;padding:0 10px;font-size:10px}.hmb-image-assets .asset-source-name{font-size:9px}.hmb-image-assets[data-asset-view="image"] .asset-grid{grid-template-columns:repeat(auto-fill,145px);align-content:start;justify-content:start;gap:9px}.hmb-image-assets[data-asset-view="image"] .asset-card{width:145px;grid-template-columns:123px;gap:0}.hmb-image-assets[data-asset-view="image"] .asset-content,.hmb-image-assets[data-asset-view="image"] .asset-extension-badge{display:none}.hmb-image-assets[data-asset-view="detail"] .asset-grid{grid-template-columns:repeat(auto-fill,286px);align-content:start;justify-content:start;gap:9px}.hmb-image-assets[data-asset-view="detail"] .asset-card{width:286px;grid-template-columns:123px minmax(0,1fr);gap:11px}.hmb-image-assets[data-asset-view="detail"] .asset-content{display:flex}
      .tray{margin:0 8px 8px;border:1px solid rgba(244,114,182,.34);border-radius:10px;background:linear-gradient(180deg,rgba(30,14,30,.9),rgba(8,11,19,.96));overflow:hidden}.tray-head{height:34px;display:flex;align-items:center;gap:9px;padding:0 10px;border-bottom:1px solid rgba(244,114,182,.2)}.tray-head b{font-size:9px;letter-spacing:.07em;color:#f9c2df}.tray-head span{color:#8ea3b8;font-size:7px}.tray-head em{margin-left:auto;color:var(--asset-selection);font-size:7px;font-style:normal}.tray-scroll{height:132px;display:flex;align-items:stretch;gap:8px;overflow-x:auto;overflow-y:hidden;padding:7px}.selected-card{position:relative;flex:0 0 244.5px;display:grid;grid-template-rows:25px minmax(0,1fr);padding:6px;border:1px solid rgba(244,114,182,.25);border-radius:8px;background:linear-gradient(145deg,rgba(61,23,49,.6),rgba(12,17,28,.94));cursor:grab}.selected-card:active{cursor:grabbing}.selected-card.dragging{opacity:.35}.selected-card.drop-target{border-color:var(--accent);box-shadow:0 0 0 1px rgba(34,211,238,.28)}.selected-card.missing{border-color:rgba(248,113,113,.5)}.selected-card-top{display:flex;align-items:center;gap:7px}.slot{min-width:30px;height:21px;display:grid;place-items:center;border:1px solid rgba(96,165,250,.68);border-radius:5px;background:rgba(37,99,235,.24);color:#93c5fd;font-size:10px;font-weight:950}.selected-actions{display:flex;gap:3px;margin-left:auto}.selected-actions button{width:23px;height:21px;border:1px solid rgba(148,163,184,.2);border-radius:5px;background:#0a101b;color:#b9cad9;cursor:pointer}.selected-actions button:hover{border-color:var(--accent);color:#fff}.selected-card-body{display:grid;grid-template-columns:102px minmax(0,1fr);align-items:center;gap:9px}.selected-thumb{position:relative;width:102px;height:82px;display:grid;place-items:center;overflow:hidden;border:1px solid rgba(244,114,182,.25);border-radius:6px;background:#060912;color:#725a70;font-size:7px;font-weight:900}.selected-thumb img{width:100%;height:100%;object-fit:cover}.selected-thumb span{display:none}.selected-thumb.fallback span{display:block}.selected-copy{display:flex;flex-direction:column;gap:4px}.selected-copy b,.selected-copy span,.selected-copy small{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.selected-copy b{font-size:10px}.selected-copy span{color:#a7b7c8;font-size:8px}.selected-copy em{color:#f3a8ce;font-size:7px;font-style:normal;font-weight:900}.selected-copy small{color:#667e94;font-size:7px}.tray-empty{min-width:100%;display:grid;place-items:center;border:1px dashed rgba(244,114,182,.18);border-radius:7px;color:#765d70;font-size:9px}
      .selected-card{flex-basis:120px;width:120px;height:118px;grid-template-rows:23px minmax(0,1fr)}.selected-card-top{gap:4px}.slot{flex:0 0 28px;width:28px;min-width:28px;height:21px;font-size:9px;font-variant-numeric:tabular-nums}.selected-actions{display:flex;gap:2px;margin-left:auto}.selected-actions button{width:22px;height:21px;padding:0;display:grid;place-items:center}.selected-card-body{display:grid;grid-template-columns:1fr;place-items:center;gap:0;min-height:0}.selected-thumb{width:106px;height:81px}.selected-copy{display:none}
      .shot-routing{margin:0 8px 8px;border:1px solid rgba(34,211,238,.3);border-radius:9px;background:linear-gradient(180deg,rgba(7,28,40,.94),rgba(6,10,18,.98));overflow:hidden}.shot-routing-head{height:38px;display:flex;align-items:center;gap:7px;padding:0 8px}.shot-toggle,.shot-add,.shot-tab,.shot-source button{border:1px solid rgba(34,211,238,.24);border-radius:6px;background:#08131e;color:#a9c6d8;cursor:pointer}.shot-toggle{width:25px;height:25px;padding:0;color:var(--accent)}.shot-routing-head>b{font-size:8px;letter-spacing:.08em;color:var(--accent);white-space:nowrap}.shot-channel{max-width:58px;color:#5f7f94;font-size:7px;font-family:ui-monospace,monospace}.shot-tabs{display:flex;flex:1;align-items:center;gap:5px;min-width:0;overflow-x:auto;padding:2px}.shot-tab{height:27px;display:flex;align-items:center;gap:5px;padding:0 7px;white-space:nowrap}.shot-tab small{color:#5e7e93;font-size:6px}.shot-tab b{max-width:92px;overflow:hidden;text-overflow:ellipsis;font-size:8px}.shot-tab em{color:#6f90a5;font-size:7px;font-style:normal}.shot-tab.active{border-color:var(--accent);background:rgba(8,145,178,.18);color:#e6fbff}.shot-add{height:27px;padding:0 9px;color:#bceef5;font-size:8px;font-weight:900;white-space:nowrap}.shot-add:disabled,.shot-source button:disabled{opacity:.28;cursor:default}.shot-routing-body{min-height:78px;display:grid;grid-template-columns:190px minmax(0,1fr);gap:8px;padding:7px 9px 9px;border-top:1px solid rgba(34,211,238,.14)}.shot-routing-summary{display:flex;flex-direction:column;gap:3px;padding:7px;border:1px solid rgba(34,211,238,.16);border-radius:7px;background:rgba(4,14,24,.65)}.shot-routing-summary b{color:#d9f8ff;font-size:10px}.shot-routing-summary span{color:var(--accent);font-size:8px;font-weight:900}.shot-routing-summary small{color:#708ba0;font-size:7px;line-height:1.35}.shot-sources{display:flex;align-content:flex-start;gap:5px;overflow-x:auto;padding:3px}.shot-source{height:30px;display:flex;flex:0 0 auto;align-items:stretch}.shot-source>button:first-child{max-width:145px;display:flex;align-items:center;gap:5px;padding:0 7px}.shot-source i{color:#5d7d91;font-size:8px;font-style:normal}.shot-source span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:8px}.shot-source.selected>button:first-child{border-color:rgba(244,114,182,.62);background:rgba(131,24,67,.22);color:#ffe0f1}.shot-source.selected i{color:#f9a8d4}.shot-source .shot-source-move{width:22px;margin-left:2px;padding:0;color:#8eb6ca}.shot-routing-empty{align-self:center;color:#607b90;font-size:8px}
      .shot-stack{max-height:360px;margin:0 8px 8px;display:flex;flex-direction:column;gap:5px;overflow:auto;scrollbar-gutter:stable}.shot-panel{flex:0 0 auto;overflow:hidden;border:1px solid rgba(var(--shot-rgb),.34);border-radius:10px;background:linear-gradient(180deg,rgba(var(--shot-rgb),.10),rgba(8,11,19,.96));box-shadow:0 0 16px rgba(var(--shot-rgb),.07)}.shot-panel-head{height:38px;display:flex;align-items:center;gap:6px;padding:4px 7px;border-bottom:1px solid transparent}.shot-panel.active .shot-panel-head{border-bottom-color:rgba(var(--shot-rgb),.20)}.shot-panel-toggle{height:29px;min-width:0;flex:1;display:grid;grid-template-columns:30px minmax(70px,auto) minmax(120px,1fr) auto auto;align-items:center;gap:7px;padding:0 8px;border:1px solid rgba(var(--shot-rgb),.32);border-radius:7px;background:linear-gradient(90deg,rgba(var(--shot-rgb),.16),rgba(8,13,23,.72));color:#d9e6f3;text-align:left;cursor:pointer}.shot-panel-toggle small{color:var(--shot-accent);font-size:8px;font-weight:950}.shot-panel-toggle b{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#f8fafc;font-size:10px}.shot-panel-toggle span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:rgba(var(--shot-rgb),.92);font-size:8px;font-weight:900;letter-spacing:.06em}.shot-panel-toggle em{color:var(--shot-accent);font-size:8px;font-style:normal;font-weight:900}.shot-panel-toggle i{color:#7f95a8;font-size:7px;font-style:normal;letter-spacing:.08em}.shot-panel.active{border-color:rgba(var(--shot-rgb),.68);box-shadow:0 0 18px rgba(var(--shot-rgb),.14)}.shot-panel.active .shot-panel-toggle{border-color:var(--shot-accent);box-shadow:0 0 10px rgba(var(--shot-rgb),.14)}.shot-panel .shot-delete{width:29px;height:29px;flex:0 0 29px;padding:0;border:1px solid rgba(var(--shot-rgb),.42);border-radius:7px;background:rgba(var(--shot-rgb),.10);color:var(--shot-accent);font-size:16px;line-height:1;cursor:pointer}.shot-panel .shot-delete:hover:not(:disabled),.shot-panel .shot-delete:focus-visible{border-color:var(--shot-accent);background:rgba(var(--shot-rgb),.22);outline:none;box-shadow:0 0 10px rgba(var(--shot-rgb),.18)}.shot-panel .shot-delete:disabled{opacity:.25;cursor:default}.shot-panel .shot-add{height:29px;padding:0 11px;border:1px solid rgba(var(--shot-rgb),.54);border-radius:7px;background:rgba(var(--shot-rgb),.14);color:var(--shot-accent);font-size:8px;font-weight:950;white-space:nowrap;cursor:pointer}.shot-panel .shot-add:disabled{opacity:.3;cursor:default}.shot-panel .tray-scroll{height:132px;display:flex;align-items:stretch;gap:8px;overflow-x:auto;overflow-y:hidden;padding:7px}.shot-panel .selected-card{border-color:rgba(var(--shot-rgb),.30);background:linear-gradient(145deg,rgba(var(--shot-rgb),.15),rgba(12,17,28,.94))}.shot-panel .selected-thumb{border-color:rgba(var(--shot-rgb),.30)}.shot-panel .slot{border-color:rgba(var(--shot-rgb),.70);background:rgba(var(--shot-rgb),.20);color:var(--shot-accent)}.shot-panel .tray-empty{border-color:rgba(var(--shot-rgb),.22);color:rgba(var(--shot-rgb),.72)}.hmb-image-assets .asset-card.selected{border-color:var(--active-shot-accent);box-shadow:inset 0 0 0 .3px rgba(var(--active-shot-rgb),.48),0 0 15px rgba(var(--active-shot-rgb),.34),0 0 4px rgba(var(--active-shot-rgb),.55)}
      .asset-registration-backdrop{position:absolute;inset:0;z-index:80;display:grid;place-items:center;padding:18px;background:rgba(1,4,10,.78);backdrop-filter:blur(5px)}.asset-passport{width:min(390px,100%);max-height:calc(100% - 12px);display:flex;flex-direction:column;overflow:auto;border:1px solid rgba(244,114,182,.62);border-radius:18px 18px 28px 28px;background:radial-gradient(circle at 50% -8%,rgba(190,24,93,.24),transparent 30%),linear-gradient(180deg,#171020,#090d17 45%,#060912);box-shadow:0 24px 70px rgba(0,0,0,.62),0 0 28px rgba(244,114,182,.2)}.passport-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 10px;border-bottom:1px solid rgba(244,114,182,.2)}.passport-head small{display:block;color:#d8a2be;font-size:7px;font-weight:900;letter-spacing:.18em}.passport-head h2{margin:3px 0 0;color:#fff1f8;font-size:15px;letter-spacing:.08em}.passport-head button{width:28px;height:28px;border:1px solid rgba(244,114,182,.25);border-radius:50%;background:#0b0d16;color:#e7b9d1;font-size:18px;line-height:1;cursor:pointer}.passport-photo{position:relative;width:128px;aspect-ratio:3/4;display:grid;place-items:center;align-self:center;margin:14px 0 8px;overflow:hidden;border:1px solid rgba(244,114,182,.38);border-radius:8px;background:#050910;color:#84677a;font-size:10px;font-weight:900;box-shadow:0 0 18px rgba(244,114,182,.12)}.passport-photo img{width:100%;height:100%;object-fit:cover}.passport-photo>span{display:none}.passport-photo.fallback img{display:none}.passport-photo.fallback>span{display:block}.passport-file{display:flex;flex-direction:column;gap:3px;padding:0 18px 12px;text-align:center}.passport-file b,.passport-file span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.passport-file b{color:#d7e2ef;font-size:8px}.passport-file span{color:#73899d;font-size:7px}.passport-fields{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:12px 16px;border-top:1px dashed rgba(244,114,182,.24)}.passport-fields label{display:flex;flex-direction:column;gap:4px}.passport-fields label:nth-last-child(1){grid-column:1/-1}.passport-fields label span{color:#bb8fa8;font-size:7px;font-weight:900;letter-spacing:.06em}.passport-fields input,.passport-fields select{width:100%;height:32px;border:1px solid rgba(148,163,184,.27);border-radius:7px;background:#060b13;color:#eef5ff;padding:0 8px;font-size:9px;outline:none}.passport-fields input:focus,.passport-fields select:focus{border-color:var(--asset-selection);box-shadow:0 0 0 1px rgba(244,114,182,.18)}.passport-fields select:disabled{opacity:.42}.passport-actions{display:flex;justify-content:flex-end;gap:7px;padding:11px 16px 15px}.passport-actions button{height:31px;padding:0 13px;border:1px solid rgba(148,163,184,.24);border-radius:7px;background:#0a101a;color:#bac9d8;font-size:8px;font-weight:900;cursor:pointer}.passport-actions .passport-register{border-color:rgba(244,114,182,.62);background:linear-gradient(180deg,rgba(190,24,93,.55),rgba(88,28,135,.42));color:#ffe4f2;box-shadow:0 0 12px rgba(244,114,182,.18)}.passport-actions button:disabled{opacity:.32;cursor:default;box-shadow:none}
      .passport-fields .passport-folder{grid-column:1/-1}.passport-taxonomy-contract{grid-column:1/-1;display:flex;flex-direction:column;gap:4px;padding:8px 9px;border:1px solid rgba(148,163,184,.18);border-radius:7px;background:rgba(2,6,14,.58)}.passport-taxonomy-contract[hidden]{display:none}.passport-taxonomy-contract small{color:#bb8fa8;font-size:7px;font-weight:900;letter-spacing:.06em}.passport-taxonomy-contract span{color:#cbd8e6;font-size:8px;line-height:1.45}
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
      @media (prefers-reduced-motion:reduce){.hmb-image-assets *{scroll-behavior:auto!important;animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}}
    </style>
    <div class="hmb-image-assets nodrag" data-hmb-library="image-asset" data-library-compact="false" data-theme="P" data-shot-number="${activeShot?.number || 1}" data-asset-view="${detailView ? "detail" : "image"}" data-busy="${state.scan_busy ? "true" : "false"}" ${state.scan_busy ? 'aria-busy="true"' : ""} style="--active-shot-accent:${activePalette.accent};--active-shot-rgb:${activePalette.rgb}" tabindex="0">
      ${renderImageAssetFixedTop(state)}
      <div class="library-expanded" data-library-expanded>
      <main class="workspace">
        <aside class="panel tree-panel">
          <div class="panel-title"><span>${escapeHtml(imageAssetText(state, "project_folders"))}</span><b>${escapeHtml(state.project_id || imageAssetText(state, "ready"))}</b></div>
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

const IMAGE_ASSET_INTERNAL_TOGGLE_INTERACTIVE_SELECTOR = [
  ".project-switch",
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
  let offset = 0;
  for (let current = element, depth = 0; current && depth < 16; depth += 1) {
    if (current === ancestor) return Math.max(0, offset);
    offset += Number(current.offsetTop) || 0;
    current = current.parentElement;
  }
  return 0;
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
    const display = clean(current.style?.display).toLowerCase();
    const visibility = clean(current.style?.visibility).toLowerCase();
    if (display === "none" || visibility === "hidden") return false;
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
  let widgetOffset = hmbImageAssetOffsetWithin(root, nodeRoot);
  if (!(widgetOffset > 0)) {
    try {
      const nodeRect = nodeRoot.getBoundingClientRect?.();
      const widgetRect = root.getBoundingClientRect?.();
      const renderedDelta = Number(widgetRect?.top) - Number(nodeRect?.top);
      const layoutWidth = Number(nodeRoot.offsetWidth) || 0;
      const renderedWidth = Number(nodeRect?.width) || 0;
      const zoom = layoutWidth > 0 && renderedWidth > 0 ? renderedWidth / layoutWidth : 1;
      if (Number.isFinite(renderedDelta) && renderedDelta > 0) {
        widgetOffset = renderedDelta / (Number.isFinite(zoom) && zoom > 0 ? zoom : 1);
      }
    } catch (_error) {}
  }
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
  geometry.records.forEach(({ element }) => {
    if (element === geometry.nodeRoot) return;
    hmbSetImageAssetStyleValue(element, "height", "auto");
    hmbSetImageAssetStyleValue(element, "min-height", "0px");
    hmbSetImageAssetStyleValue(element, "max-height", "none");
  });
  const fixedTop = container.querySelector?.(".top[data-library-toggle-surface='header']");
  const fixedTopHeight = hmbImageAssetLayoutHeight(fixedTop) || 58;
  const targetHeight = Math.max(
    1,
    Math.ceil(
      geometry.chromeHeight
      + fixedTopHeight
      + hmbImageAssetCompactSummaryHeight(summary),
    ),
  );
  const height = `${targetHeight}px`;
  hmbSetImageAssetStyleValue(geometry.nodeRoot, "height", height);
  hmbSetImageAssetStyleValue(geometry.nodeRoot, "min-height", height);
  hmbSetImageAssetStyleValue(geometry.nodeRoot, "max-height", height);
  hmbRequestImageAssetNodeInternals(container, geometry.nodeRoot);
  return true;
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
  if (!shell) return 0;
  let collapsed = 0;
  nativeProjectRootHosts(container).forEach((host) => {
    let branch = host;
    while (
      branch?.parentElement
      && branch.parentElement !== shell
      && !branch.parentElement.contains?.(container)
      && !clean(branch.parentElement.className).toLowerCase().includes("react-flow__")
    ) {
      branch = branch.parentElement;
    }
    if (!branch?.style || branch === shell || branch.contains?.(container)) return;
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

function installEvents(container, state, props, remount, listeners) {
  const on = (target, type, handler, options) => {
    if (!target?.addEventListener) return;
    target.addEventListener(type, handler, options);
    listeners.push([target, type, handler, options]);
  };

  const stopNodeDeleteShortcut = (event) => {
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  on(container, "keydown", stopNodeDeleteShortcut);
  const stopSelectedNodeDeleteShortcut = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  if (typeof window !== "undefined") on(window, "keydown", stopSelectedNodeDeleteShortcut, true);
  const stopInteriorNodeSelection = (event) => {
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
    const baseRouting = cloneImageAssetShotRouting(state.shot_routing);
    const baseSelection = hmbImageAssetSelectionSnapshot(state);
    const baseCurrentScanRevision = container.__hmbImageAssetCurrentScanRevision;
    const baseCurrentUiEditRevision = container.__hmbImageAssetCurrentUiEditRevision;
    const baseLatestLocalUiEditRevision = container.__hmbImageAssetLatestLocalUiEditRevision;
    if (typeof mutate !== "function" || !mutate()) return false;
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
    state = paintState();
    let failedSynchronously = false;
    const published = emit(props, state, container, () => {
      failedSynchronously = true;
      if (baseRouting) state.shot_routing = cloneImageAssetShotRouting(baseRouting);
      hmbRestoreImageAssetSelectionSnapshot(state, baseSelection);
      state[IMAGE_ASSET_UI_EDIT_REVISION_KEY] = hmbNormalizeImageAssetRevision(
        baseCurrentUiEditRevision,
      );
      container.__hmbImageAssetCurrentScanRevision = baseCurrentScanRevision;
      container.__hmbImageAssetCurrentUiEditRevision = baseCurrentUiEditRevision;
      container.__hmbImageAssetLatestLocalUiEditRevision = baseLatestLocalUiEditRevision;
      state = paintState();
      container.__hmbImageAssetLatestState = state;
    }, { suppressMatchingEcho: true });
    if (!failedSynchronously) state = published;
    container.__hmbImageAssetLatestState = state;
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
  const commitSlowProjectMutation = (mutate) => {
    if (container.__hmbImageAssetBusy || typeof mutate !== "function") return false;
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
    const token = `${Date.now()}-${Math.random()}`;
    container.__hmbImageAssetSlowActionToken = token;
    hmbSetImageAssetBusy(container, true, imageAssetText(state, "busy_loading"));
    hmbAfterImageAssetPaint(() => {
      if (container.__hmbImageAssetSlowActionToken !== token) return;
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
  on(container.querySelector("[data-shot-add]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    commitShotMutation(() => hmbAddImageAssetShot(state));
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
      if (event.target?.closest?.("[data-shot-rename]")) return;
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
  const bindShotRenameInput = (input, renameButton, shotUuid) => {
    const routing = ensureImageAssetShotRouting(state);
    const shot = routing.shots.find((item) => item.shot_uuid === shotUuid);
    const ownerDocument = input?.ownerDocument || container.ownerDocument
      || (typeof document !== "undefined" ? document : null);
    if (!shot || !input || !renameButton || !ownerDocument?.createElement) return false;
    renameButton.disabled = true;
    let settled = false;
    const finish = (save) => {
      if (settled) return;
      settled = true;
      const value = clean(input.value);
      const restored = ownerDocument.createElement("b");
      restored.setAttribute("data-shot-name", "");
      restored.textContent = save && value ? value : shot.name;
      input.replaceWith(restored);
      renameButton.disabled = false;
      try { renameButton.focus?.({ preventScroll: true }); } catch (_error) { renameButton.focus?.(); }
      if (save && value && value !== shot.name) {
        commitShotMutation(() => hmbRenameImageAssetShot(state, shotUuid, value));
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
      const routing = ensureImageAssetShotRouting(state);
      const shot = routing.shots.find((item) => item.shot_uuid === shotUuid);
      const panel = renameButton.closest?.("[data-shot-panel]");
      const label = panel?.querySelector?.("[data-shot-name]");
      const ownerDocument = label?.ownerDocument || container.ownerDocument
        || (typeof document !== "undefined" ? document : null);
      if (!shot || !label || !ownerDocument?.createElement) return;
      const input = ownerDocument.createElement("input");
      input.type = "text";
      input.className = "shot-name-input";
      input.setAttribute("data-shot-rename-input", shotUuid);
      input.setAttribute("aria-label", imageAssetText(state, "rename_shot"));
      input.maxLength = 128;
      input.value = shot.name;
      label.replaceWith(input);
      if (!bindShotRenameInput(input, renameButton, shotUuid)) return;
      try { input.focus?.({ preventScroll: true }); } catch (_error) { input.focus?.(); }
      input.select?.();
    });
  });
  const projectSelect = container.querySelector("[data-project-select]");
  on(projectSelect, "change", () => {
    state = container.__hmbImageAssetLatestState || state;
    const path = clean(projectSelect.value).replaceAll("\\", "/");
    if (!path || path === state.project_root) return;
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
    });
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
      if (!hmbImageAssetCanSelect(asset)) return;
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
    const asset = assetsByLibraryId.get(clean(card.getAttribute("data-asset-key")));
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
    const asset = assetsByLibraryId.get(clean(card.getAttribute("data-asset-key")));
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
  const updateRegistrationSubmit = () => {
    const submit = container.querySelector("[data-registration-submit]");
    if (submit) {
      submit.disabled = !registrationDraftIsComplete(
        container.__hmbImageAssetRegistrationDraft,
      );
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
    const nativePath = clean(nativeProjectRootValue(container)).replaceAll("\\", "/");
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

export default function HMBImageAssetLibraryWidget(container, props) {
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
  let state = normalizeState(props?.value);
  hmbRememberImageAssetPresentation(state);
  hmbAdoptImageAssetPresentation(state);
  container.__hmbImageAssetLatestState = state;
  hmbAcceptImageAssetThumbnailResult(container, state);
  hmbRememberImageAssetRevisionState(container, state, false);
  let listeners = [];
  let renderRevision = 0;

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
      hmbScheduleImageAssetThumbnailRequest(container, state, props, {
        includeWindow: false,
      });
      return state;
    }
    const uiMemory = container.__hmbImageAssetCompactUiMemory
      || captureImageAssetUi(container, state);
    const reusableImages = detachReusableImageAssets(container);
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
    const markup = hmbScopeWidgetStyleMarkup(render(
      state,
      container.__hmbImageAssetRegistrationDraft || null,
      container.__hmbImageAssetRenderLimit || IMAGE_ASSET_RENDER_WINDOW,
      container.__hmbImageAssetRenderOffset || 0,
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
    hmbPrepareImageAssetCanvasGestures(container);
    restoreReusableImageAssets(container, reusableImages);
    concealNativeProjectRootPicker(container);
    installEvents(container, state, props, remount, listeners);
    hmbRebuildImageAssetIndexes(container, state);
    restoreImageAssetUi(container, state, uiMemory);
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
    const incomingState = normalizeState(nextProps?.value);
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
    const currentValue = JSON.stringify(state);
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
    delete container.__hmbImageAssetSlowActionToken;
    clearListeners();
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
    container.innerHTML = "";
  };
  container.__hmbImageAssetCleanup = cleanup;
  remount(state);
  return {
    cleanup: container.__hmbImageAssetCleanupProxy,
    update(nextProps) {
      applyProps(nextProps || {});
    },
  };
}
