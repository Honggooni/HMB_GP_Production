const HMB_UI_THEME_STORAGE_KEY = "hmb_gp_production_ui_theme";
const HMB_UI_THEME_EVENT = "hmb-gp-production-theme-change";

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
const ROOT_FOLDER_KEY = "$root";
const IMAGE_ASSET_STATE_VERSION = 4;
const IMAGE_ASSET_AUTO_SYNC_MS = 10000;
const IMAGE_ASSET_AUTO_SYNC_JITTER_MS = 2000;
const IMAGE_ASSET_AUTO_SYNC_PENDING_MS = 5000;
const IMAGE_ASSET_SELECTION_COMMIT_FALLBACK_MS = 120;
const IMAGE_ASSET_ECHO_EXPIRY_MS = 1500;
let imageAssetWidgetMountSequence = 0;
let imageAssetSelectionCommitSequence = 0;
let imageAssetPublicationSequence = 0;
let imageAssetAuthoritySequence = 0;
const IMAGE_ASSET_TRANSPORT_RETRY_MS = 32;
const IMAGE_ASSET_AUTHORITY_STAMP = Symbol("hmbImageAssetAuthorityStamp");
const UNCLASSIFIED_SOURCE_TYPES = new Set([
  "",
  "Role Required / Select Source Type",
  "Select Source Type",
]);

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
    move_left: "Move left",
    move_right: "Move right",
    remove_selection: "Remove from selection",
    remove_external_selection: "Disconnect this external image from IMAGE_IMPORT_IN. Multi-image or ambiguous links must be removed at the input port.",
    disconnecting_external_import: "Disconnecting external image…",
    add: "Add",
    add_image_asset: "Add image asset",
    registered_project_asset: "Registered project asset",
    metadata_pending: "Raster metadata pending",
    register_before_select: "Register this image with Add before selecting it.",
    image_limit: `The ${MAX_SELECTED_IMAGES}-image limit has been reached.`,
    click_select: "Click the card to select or deselect this image.",
    project_state: "PROJECT",
    unregistered_state: "UNREGISTERED",
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
    main_type_label: "MAIN TYPE (OPTIONAL)",
    select_main_type: "Select Main Type (optional)",
    custom_main_type: "CUSTOM MAIN TYPE (OPTIONAL)",
    sub_type_label: "SUB TYPE (OPTIONAL)",
    select_sub_type: "Select Sub Type (optional)",
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
    move_left: "왼쪽으로 이동",
    move_right: "오른쪽으로 이동",
    remove_selection: "선택에서 제거",
    remove_external_selection: "이 외부 이미지를 IMAGE_IMPORT_IN에서 연결 해제합니다. 여러 이미지를 함께 전달하거나 연결이 모호하면 입력 포트에서 직접 해제하세요.",
    disconnecting_external_import: "외부 이미지 연결 해제 중…",
    add: "추가",
    add_image_asset: "이미지 에셋 추가",
    registered_project_asset: "등록된 프로젝트 에셋",
    metadata_pending: "래스터 메타데이터 확인 중",
    register_before_select: "선택하기 전에 추가 버튼으로 이 이미지를 등록하세요.",
    image_limit: `이미지는 최대 ${MAX_SELECTED_IMAGES}개까지 선택할 수 있습니다.`,
    click_select: "카드를 클릭하여 이미지를 선택하거나 선택 해제합니다.",
    project_state: "프로젝트",
    unregistered_state: "미등록",
    image_name: "이미지 이름",
    asset_id: "에셋 ID",
    main_type: "메인 유형",
    unclassified: "미분류 (선택 사항)",
    sub_type: "하위 유형",
    sub_unassigned: "하위 유형 후보가 지정되지 않음",
    hmb_project_asset: "HMB 프로젝트 에셋",
    asset_passport: "에셋 등록 정보",
    close_registration: "에셋 등록 창 닫기",
    final_image_name: "최종 이미지 이름",
    main_type_label: "메인 유형 (선택)",
    select_main_type: "메인 유형 선택 (선택 사항)",
    custom_main_type: "사용자 정의 메인 유형 (선택)",
    sub_type_label: "하위 유형 (선택)",
    select_sub_type: "하위 유형 선택 (선택 사항)",
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
  },
};

function imageAssetLanguage(state) {
  return clean(state?.language).toLowerCase() === "ko" ? "ko" : "en";
}

function imageAssetText(state, key) {
  const language = imageAssetLanguage(state);
  return IMAGE_ASSET_UI_TEXT[language]?.[key] || IMAGE_ASSET_UI_TEXT.en[key] || key;
}

function imageAssetStatusCount(value) {
  return Math.min(9999, Math.max(0, Number.parseInt(value || 0, 10) || 0));
}

export function hmbImageAssetStatusSummary(state) {
  return `${imageAssetStatusCount(state?.status?.registered_asset_count)} ${imageAssetText(state, "registered")} | ${imageAssetStatusCount(state?.status?.unregistered_asset_count)} ${imageAssetText(state, "unregistered")} | ${imageAssetStatusCount(state?.status?.selected_count)}/${MAX_SELECTED_IMAGES} ${imageAssetText(state, "selected")}`;
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

function normalizeTheme(value) {
  return clean(value).toUpperCase() === "T" ? "T" : "P";
}

function readTheme(fallback = "P") {
  try {
    if (typeof window !== "undefined") {
      if (window.__hmbGpProductionUiTheme === "P" || window.__hmbGpProductionUiTheme === "T") {
        return normalizeTheme(window.__hmbGpProductionUiTheme);
      }
      const stored = window.sessionStorage?.getItem(HMB_UI_THEME_STORAGE_KEY);
      if (stored === "P" || stored === "T") {
        window.__hmbGpProductionUiTheme = stored;
        return stored;
      }
    }
  } catch (_error) {}
  return normalizeTheme(fallback);
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
    relative_path: clean(raw.relative_path).replaceAll("\\", "/"),
    extension: clean(raw.extension).toLowerCase(),
    width: Math.max(0, Number.parseInt(raw.width || 0, 10) || 0),
    height: Math.max(0, Number.parseInt(raw.height || 0, 10) || 0),
    source_type: UNCLASSIFIED_SOURCE_TYPES.has(clean(raw.source_type))
      ? "Custom"
      : clean(raw.source_type) || "Custom",
    custom_source_type: clean(raw.custom_source_type),
    scope_candidate: clean(raw.scope_candidate || raw.scope || raw.sub_type),
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
    source_type: clean(raw.source_type).slice(0, 256),
    custom_source_type: clean(raw.custom_source_type).slice(0, 256),
    scope_candidate: clean(raw.scope_candidate || raw.scope).slice(0, 256),
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

function normalizeState(value) {
  const input = parseValue(value);
  const taxonomyInput = input.taxonomy && typeof input.taxonomy === "object"
    ? input.taxonomy
    : {};
  const taxonomy = {
    source_type_choices: uniqueStrings(taxonomyInput.source_type_choices),
    scope_choices: uniqueStrings(taxonomyInput.scope_choices),
    scope_choices_by_source_type:
      taxonomyInput.scope_choices_by_source_type
      && typeof taxonomyInput.scope_choices_by_source_type === "object"
        ? taxonomyInput.scope_choices_by_source_type
        : {},
    actor_color_pick_choices: uniqueStrings(taxonomyInput.actor_color_pick_choices),
    object_color_pick_choices: uniqueStrings(taxonomyInput.object_color_pick_choices),
  };
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
    manifest_signature: clean(input.manifest_signature).slice(0, 128),
    taxonomy,
    folders,
    assets,
    root_edit_enabled: Boolean(input.root_edit_enabled),
    selected_folder_path: folders.includes(selectedFolderPath) ? selectedFolderPath : "",
    expanded_folders: expandedFolders,
    selected_main_type: clean(input.selected_main_type),
    selected_sub_type: clean(input.selected_sub_type),
    selected_source_view: selectedSourceView,
    search: clean(input.search).slice(0, 256),
    language: clean(input.language).toLowerCase() === "ko" ? "ko" : "en",
    asset_view_mode: clean(input.asset_view_mode).toLowerCase() === "detail" ? "detail" : "image",
    scan_revision: Math.max(0, Number.parseInt(input.scan_revision || 0, 10) || 0),
    refresh_revision: Math.max(0, Number.parseInt(input.refresh_revision || 0, 10) || 0),
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

function selectedAssets(state) {
  return state.assets
    .filter((asset) => asset.selected)
    .sort((left, right) => left.selection_order - right.selection_order);
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
  const incoming = nextProps?.value;
  const pending = container?.__hmbImageAssetPendingStateEchoes;
  if (typeof incoming !== "string" || !Array.isArray(pending) || !pending.length) {
    return false;
  }
  const match = pending.find((item) => item?.value === incoming);
  if (!match) return false;
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
      scheduleRetry();
    }
    return false;
  };
  const succeed = () => {
    if (container?.__hmbImageAssetPublicationOwner === publicationToken) {
      delete container.__hmbImageAssetLastPublishError;
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

export function hmbImageAssetAutoSyncPayload(value, nonce) {
  const state = isCanonicalImageAssetState(value) ? value : normalizeState(value);
  return JSON.stringify({
    __hmb_manifest_poll_nonce: clean(nonce).slice(0, 128),
    catalog_root: clean(state.catalog_root),
    project_root: clean(state.project_root),
    project_id: clean(state.project_id),
    project_uid: clean(state.project_uid),
    manifest_signature: clean(state.manifest_signature),
  });
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
    asset.source_type,
    asset.scope_candidate,
  ].map((value) => clean(value).toLowerCase()).join("\n");
}

function assetMatchesSearch(asset, search) {
  const needle = String(search || "").trim().toLowerCase();
  return !needle || assetSearchText(asset).includes(needle);
}

function applyAssetSearchFilter(container, search) {
  const needle = String(search || "").trim().toLowerCase();
  let visibleCount = 0;
  container.querySelectorAll?.("[data-asset-key]").forEach((card) => {
    const visible = !needle || clean(card.getAttribute("data-search-text")).includes(needle);
    card.hidden = !visible;
    if (visible) visibleCount += 1;
  });
  const empty = container.querySelector?.("[data-search-empty]");
  if (empty) empty.hidden = visibleCount > 0;
}

const IMAGE_ASSET_SCROLL_SELECTORS = [".tree", ".asset-scroll", ".tray-scroll", ".asset-passport"];
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
    ? `<img src="${escapeHtml(source)}" alt="" draggable="false"/><span>${fallback}</span>`
    : `<span>${fallback}</span>`;
}

function thumbnailHtml(asset, className = "asset-thumb") {
  const source = imageSource(asset);
  return `<div class="${className} ${source ? "" : "fallback"}">${thumbnailImageMarkup(asset)}</div>`;
}

function assetThumbnailHtml(asset, state) {
  const source = imageSource(asset);
  const format = escapeHtml(
    (asset.extension || ".img").replace(".", "").toUpperCase() || "IMG",
  );
  const footer = asset.registered
    ? `<span class="asset-format" title="${escapeHtml(imageAssetText(state, "registered_project_asset"))}">${format}</span>`
    : `<button type="button" class="asset-add" data-asset-add aria-label="${escapeHtml(imageAssetText(state, "add_image_asset"))}">${escapeHtml(imageAssetText(state, "add"))}</button>`;
  return `
    <div class="asset-thumb ${source ? "" : "fallback"}">
      <div class="asset-thumb-media">${thumbnailImageMarkup(asset)}</div>
      <div class="asset-thumb-footer">${footer}</div>
    </div>
  `;
}

function renderAssetCard(asset, selectedCount, search, state) {
  const dimensions = asset.width && asset.height
    ? `${asset.width} × ${asset.height}`
    : imageAssetText(state, "metadata_pending");
  const selectable = hmbImageAssetCanSelect(asset);
  const selectionBlocked = selectable && !asset.selected && selectedCount >= MAX_SELECTED_IMAGES;
  const cardTitle = !selectable
    ? imageAssetText(state, "register_before_select")
    : selectionBlocked
      ? imageAssetText(state, "image_limit")
      : imageAssetText(state, "click_select");
  const unclassified = imageAssetText(state, "unclassified");
  const sourceTypeLabel = UNCLASSIFIED_SOURCE_TYPES.has(clean(asset.source_type))
    || (clean(asset.source_type) === "Custom" && !clean(asset.custom_source_type))
    ? unclassified
    : clean(asset.source_type) || unclassified;
  const subUnassigned = imageAssetText(state, "sub_unassigned");
  return `
    <article class="asset-card ${asset.selected ? "selected" : ""} ${selectionBlocked ? "selection-blocked" : ""} ${selectable ? "" : "unregistered"}"
      data-asset-key="${escapeHtml(asset.asset_library_id)}"
      data-asset-registered="${asset.registered ? "1" : "0"}"
      data-search-text="${escapeHtml(assetSearchText(asset))}"
      data-selection-disabled="${selectionBlocked ? "1" : "0"}"
      ${assetMatchesSearch(asset, search) ? "" : "hidden"}
      role="${selectable ? "button" : "group"}" tabindex="0" ${selectable ? `aria-pressed="${asset.selected ? "true" : "false"}"` : ""}
      title="${escapeHtml(cardTitle)}">
      ${assetThumbnailHtml(asset, state)}
      <div class="asset-content">
        <div class="asset-title">
          <div class="asset-title-copy">
            <span class="asset-state">${escapeHtml(imageAssetText(state, asset.registered ? "project_state" : "unregistered_state"))}</span>
            <b title="${escapeHtml(imageAssetText(state, "image_name"))}: ${escapeHtml(asset.image_name)}">${escapeHtml(asset.image_name)}</b>
            <small class="asset-id-line" title="${escapeHtml(imageAssetText(state, "asset_id"))}: ${escapeHtml(asset.asset_id)}"><em>${escapeHtml(imageAssetText(state, "asset_id"))}</em><span>${escapeHtml(asset.asset_id)}</span></small>
          </div>
        </div>
        <div class="asset-meta">
          <b title="${escapeHtml(imageAssetText(state, "main_type"))}: ${escapeHtml(sourceTypeLabel)}">${escapeHtml(sourceTypeLabel)}</b>
          <span title="${escapeHtml(imageAssetText(state, "sub_type"))}: ${escapeHtml(asset.scope_candidate || subUnassigned)}">${escapeHtml(asset.scope_candidate || subUnassigned)}</span>
          <span class="asset-location" title="${escapeHtml(`${dimensions} · ${asset.relative_path || asset.media_ref_kind}`)}">${escapeHtml(dimensions)} · ${escapeHtml(asset.relative_path || asset.media_ref_kind)}</span>
        </div>
      </div>
    </article>
  `;
}

function renderSelectedCard(asset, index, selected, state) {
  const number = String(index + 1).padStart(2, "0");
  const externalImport = asset.source_kind === "user" && Number(asset.import_index || 0) > 0;
  const disconnectPending = externalImport && state.disconnect_import_uid === asset.source_uid;
  const removeKey = disconnectPending
    ? "disconnecting_external_import"
    : externalImport
      ? "remove_external_selection"
      : "remove_selection";
  const removeTitle = imageAssetText(state, removeKey);
  return `
    <article class="selected-card ${asset.connected ? "" : "missing"}" draggable="true"
      data-selected-key="${escapeHtml(asset.asset_library_id)}" aria-label="${escapeHtml(`${number} ${asset.image_name}`)}" title="${escapeHtml(asset.image_name)}">
      <div class="selected-card-top">
        <strong class="slot">${number}</strong>
        <div class="selected-actions">
          <button type="button" data-move="-1" title="${escapeHtml(imageAssetText(state, "move_left"))}" aria-label="${escapeHtml(imageAssetText(state, "move_left"))}" ${index === 0 ? "disabled" : ""}>‹</button>
          <button type="button" data-move="1" title="${escapeHtml(imageAssetText(state, "move_right"))}" aria-label="${escapeHtml(imageAssetText(state, "move_right"))}" ${index >= selected.length - 1 ? "disabled" : ""}>›</button>
          <button type="button" data-remove-selected title="${escapeHtml(removeTitle)}" aria-label="${escapeHtml(removeTitle)}" ${disconnectPending ? 'disabled aria-busy="true"' : ""}>×</button>
        </div>
      </div>
      <div class="selected-card-body">
        ${thumbnailHtml(asset, "selected-thumb")}
      </div>
    </article>
  `;
}

function hmbApplyImageAssetCardFeedback(card, asset, selectedCount, state) {
  if (!card || !asset) return false;
  const selectable = hmbImageAssetCanSelect(asset);
  const selectionBlocked = selectable && !asset.selected && selectedCount >= MAX_SELECTED_IMAGES;
  card.classList?.toggle("selected", Boolean(asset.selected));
  card.classList?.toggle("selection-blocked", selectionBlocked);
  card.setAttribute?.("data-selection-disabled", selectionBlocked ? "1" : "0");
  if (selectable) card.setAttribute?.("aria-pressed", asset.selected ? "true" : "false");
  const title = !selectable
    ? imageAssetText(state, "register_before_select")
    : selectionBlocked
      ? imageAssetText(state, "image_limit")
      : imageAssetText(state, "click_select");
  card.setAttribute?.("title", title);
  return true;
}

function hmbCreateSelectedAssetCard(tray, asset, index, selected, state, factory = null) {
  if (typeof factory === "function") {
    return factory(asset, index, selected, state, renderSelectedCard(asset, index, selected, state));
  }
  const ownerDocument = tray?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!ownerDocument?.createElement) return null;
  const template = ownerDocument.createElement("template");
  template.innerHTML = renderSelectedCard(asset, index, selected, state).trim();
  return template.content?.firstElementChild || null;
}

function hmbUpdateSelectedAssetCard(card, asset, index, selected, state) {
  if (!card || !asset) return false;
  const number = String(index + 1).padStart(2, "0");
  const externalImport = asset.source_kind === "user" && Number(asset.import_index || 0) > 0;
  const disconnectPending = externalImport && state.disconnect_import_uid === asset.source_uid;
  const removeKey = disconnectPending
    ? "disconnecting_external_import"
    : externalImport
      ? "remove_external_selection"
      : "remove_selection";
  const removeTitle = imageAssetText(state, removeKey);
  card.classList?.toggle("missing", !asset.connected);
  card.setAttribute?.("data-selected-key", asset.asset_library_id);
  card.setAttribute?.("aria-label", `${number} ${asset.image_name}`);
  card.setAttribute?.("title", asset.image_name);
  const slot = card.querySelector?.(".slot");
  if (slot) slot.textContent = number;
  const moveLeft = card.querySelector?.('[data-move="-1"]');
  if (moveLeft) moveLeft.disabled = index === 0;
  const moveRight = card.querySelector?.('[data-move="1"]');
  if (moveRight) moveRight.disabled = index >= selected.length - 1;
  const remove = card.querySelector?.("[data-remove-selected]");
  if (remove) {
    remove.disabled = disconnectPending;
    remove.setAttribute?.("title", removeTitle);
    remove.setAttribute?.("aria-label", removeTitle);
    if (disconnectPending) remove.setAttribute?.("aria-busy", "true");
    else remove.removeAttribute?.("aria-busy");
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
  const cardsByKey = new Map();
  existingCards.forEach((card) => {
    const key = clean(card.getAttribute?.("data-selected-key"));
    if (key && !cardsByKey.has(key)) cardsByKey.set(key, card);
    else card.remove?.();
  });
  let created = 0;
  let retained = 0;
  let removed = 0;
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
      );
      if (!card) return;
      created += 1;
    }
    hmbUpdateSelectedAssetCard(card, asset, index, ordered, state);
    tray.appendChild?.(card);
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

export function hmbApplyImageAssetSelectionFeedback(container, state, options = {}) {
  if (!container || !state || !Array.isArray(state.assets)) return null;
  const selected = Array.isArray(options.selectedAssets)
    ? options.selectedAssets
    : selectedAssets(state);
  const selectedCount = selected.length;
  state.status = {
    ...(state.status || {}),
    selected_count: selectedCount,
  };
  const previousSelectedCount = Number(options.previousSelectedCount);
  const crossedSelectionLimit = Number.isFinite(previousSelectedCount) && (
    (previousSelectedCount < MAX_SELECTED_IMAGES && selectedCount >= MAX_SELECTED_IMAGES)
    || (previousSelectedCount >= MAX_SELECTED_IMAGES && selectedCount < MAX_SELECTED_IMAGES)
  );
  let cardScanCount = 0;
  if (options.changedCard && options.changedAsset && !crossedSelectionLimit) {
    hmbApplyImageAssetCardFeedback(
      options.changedCard,
      options.changedAsset,
      selectedCount,
      state,
    );
  } else {
    const assetsByLibraryId = options.assetsByLibraryId instanceof Map
      ? options.assetsByLibraryId
      : new Map(state.assets.map((asset) => [clean(asset.asset_library_id), asset]));
    container.querySelectorAll?.("[data-asset-key]").forEach((card) => {
      cardScanCount += 1;
      const asset = assetsByLibraryId.get(clean(card.getAttribute?.("data-asset-key")));
      if (asset) hmbApplyImageAssetCardFeedback(card, asset, selectedCount, state);
    });
  }

  const trayCount = container.querySelector?.(".tray-head em");
  if (trayCount) trayCount.textContent = `${selectedCount}/${MAX_SELECTED_IMAGES}`;
  const tray = container.querySelector?.(".tray-scroll");
  const trayResult = hmbReconcileImageAssetSelectionTray(tray, selected, state, options);
  const status = container.querySelector?.(".toolbar-status strong");
  if (status && !state.error && !state.asset_registration_result?.message) {
    const summary = hmbImageAssetStatusSummary(state);
    status.textContent = summary;
    status.setAttribute?.("title", summary);
  }
  return { cardScanCount, selectedCount, tray: trayResult };
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
  const excluded = new Set([
    "Role Required / Select Source Type",
    "Select Source Type",
    "Ignore / Unused",
  ]);
  return uniqueStrings(taxonomy?.source_type_choices).filter((value) => !excluded.has(value));
}

export function hmbImageAssetRegistrationSubTypes(taxonomy, sourceType) {
  const mapped = taxonomy?.scope_choices_by_source_type?.[clean(sourceType)];
  return uniqueStrings(Array.isArray(mapped) ? mapped : taxonomy?.scope_choices).filter(Boolean);
}

export function hmbCreateImageAssetRegistrationDraft(asset, taxonomy = {}) {
  if (!asset || typeof asset !== "object") return null;
  const mainTypes = registrationMainTypes(taxonomy);
  const sourceType = clean(asset.source_type) === "Custom" && !clean(asset.custom_source_type)
    ? ""
    : mainTypes.includes(clean(asset.source_type))
    ? clean(asset.source_type)
    : "";
  const subTypes = hmbImageAssetRegistrationSubTypes(taxonomy, sourceType);
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
    source_type: sourceType,
    custom_source_type: clean(asset.custom_source_type).slice(0, 256),
    scope_candidate: subTypes.includes(clean(asset.scope_candidate))
      ? clean(asset.scope_candidate)
      : "",
  };
}

function registrationOptions(values, selected, placeholder) {
  return [
    `<option value="">${escapeHtml(placeholder)}</option>`,
    ...values.map((value) => (
      `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(value)}</option>`
    )),
  ].join("");
}

function registrationDraftIsComplete(draft) {
  return Boolean(
    clean(draft?.image_name)
    && clean(draft?.asset_id)
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
    || asset.registered
    || (asset.source_kind !== "project" && !externalImport)
  ) return "";
  const mainTypes = registrationMainTypes(state.taxonomy);
  const subTypes = hmbImageAssetRegistrationSubTypes(state.taxonomy, draft.source_type);
  const customMainType = draft.source_type === "Custom"
    ? `<label><span>${escapeHtml(imageAssetText(state, "custom_main_type"))}</span><input data-registration-field="custom_source_type" maxlength="256" value="${escapeHtml(draft.custom_source_type)}"/></label>`
    : "";
  return `
    <div class="asset-registration-backdrop" data-registration-backdrop>
      <section class="asset-passport" role="dialog" aria-modal="true" aria-labelledby="asset-registration-title">
        <header class="passport-head">
          <div><small>${escapeHtml(imageAssetText(state, "hmb_project_asset"))}</small><h2 id="asset-registration-title">${escapeHtml(imageAssetText(state, "asset_passport"))}</h2></div>
          <button type="button" data-registration-cancel aria-label="${escapeHtml(imageAssetText(state, "close_registration"))}">&times;</button>
        </header>
        <div class="passport-photo ${imageSource(asset) ? "" : "fallback"}">${thumbnailImageMarkup(asset)}</div>
        <div class="passport-file"><b>${escapeHtml(asset.relative_path || asset.path || asset.media_ref_kind)}</b><span>${asset.width && asset.height ? `${asset.width} × ${asset.height}` : escapeHtml(imageAssetText(state, "metadata_pending"))}</span></div>
        <div class="passport-fields">
          ${registrationFolderField(state, draft, externalImport)}
          <label><span>${escapeHtml(imageAssetText(state, "final_image_name"))}</span><input data-registration-field="image_name" maxlength="256" value="${escapeHtml(draft.image_name)}"/></label>
          <label><span>${escapeHtml(imageAssetText(state, "asset_id"))}</span><input data-registration-field="asset_id" maxlength="256" value="${escapeHtml(draft.asset_id)}"/></label>
          <label><span>${escapeHtml(imageAssetText(state, "main_type_label"))}</span><select data-registration-main>${registrationOptions(mainTypes, draft.source_type, imageAssetText(state, "select_main_type"))}</select></label>
          ${customMainType}
          <label><span>${escapeHtml(imageAssetText(state, "sub_type_label"))}</span><select data-registration-sub ${draft.source_type ? "" : "disabled"}>${registrationOptions(subTypes, draft.scope_candidate, imageAssetText(state, "select_sub_type"))}</select></label>
        </div>
        <footer class="passport-actions">
          <button type="button" data-registration-cancel>${escapeHtml(imageAssetText(state, "cancel"))}</button>
          <button type="button" class="passport-register" data-registration-submit ${registrationDraftIsComplete(draft) ? "" : "disabled"}>${escapeHtml(imageAssetText(state, "register_asset"))}</button>
        </footer>
      </section>
    </div>
  `;
}

function render(state, registrationDraft = null) {
  const assets = folderAssets(state);
  const visibleAssets = assets.filter((asset) => assetMatchesSearch(asset, state.search));
  const selected = selectedAssets(state);
  const theme = readTheme();
  const registrationResult = state.asset_registration_result;
  const statusText = state.error
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
      .hmb-image-assets{--bg:#090c16;--panel:#101523;--line:rgba(148,163,184,.19);--accent:#22d3ee;--pink:#f472b6;--asset-selection:#f472b6;--text:#e6edf7;--muted:#8fa3b8;--selection-rgb:244,114,182;--selection-deep-rgb:190,24,93;--selection-secondary-rgb:217,70,239;--selection-text:#f8c6df;--selection-soft:#f3a8ce;--selection-strong:#ffe4f2;--selection-panel:rgba(30,14,30,.9);--selection-card:rgba(61,23,49,.6);--header-tint:rgba(72,35,101,.44);container-type:inline-size;position:relative;width:100%;height:100%;min-height:680px;display:grid;grid-template-rows:58px minmax(0,1fr) 174px;overflow:hidden;border:1px solid var(--line);border-radius:11px;background:radial-gradient(circle at 8% -10%,rgba(168,85,247,.16),transparent 34%),linear-gradient(180deg,#0b1020,#060912);color:var(--text);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;font-synthesis:none;-webkit-font-smoothing:antialiased;box-sizing:border-box}
      .hmb-image-assets[data-theme="T"]{--accent:#38bdf8;--pink:#60a5fa;--asset-selection:#38bdf8;--line:rgba(96,165,250,.22);--selection-rgb:56,189,248;--selection-deep-rgb:3,105,161;--selection-secondary-rgb:37,99,235;--selection-text:#bae6fd;--selection-soft:#7dd3fc;--selection-strong:#e0f2fe;--selection-panel:rgba(8,26,48,.94);--selection-card:rgba(12,48,78,.62);--header-tint:rgba(15,72,126,.46);background:radial-gradient(circle at 8% -10%,rgba(37,99,235,.2),transparent 34%),linear-gradient(180deg,#091525,#050a12)}
      .hmb-image-assets *{box-sizing:border-box;min-width:0}.top{display:flex;align-items:center;gap:12px;padding:8px 13px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,rgba(72,35,101,.44),rgba(14,23,38,.9) 44%)}.mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border:1px solid rgba(34,211,238,.7);border-radius:8px;background:rgba(8,145,178,.12);color:var(--accent);font-size:11px;font-weight:950}.heading{display:flex;flex:0 1 auto;flex-direction:column;gap:2px;overflow:hidden}.heading b{overflow:hidden;font-size:15px;letter-spacing:.01em;white-space:nowrap;text-overflow:ellipsis}.heading span{max-width:360px;color:var(--muted);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.project-switch{margin-left:auto;display:grid;grid-template-columns:auto auto minmax(150px,260px);align-items:center;gap:7px;min-width:0}.project-actions{display:flex;align-items:center;gap:5px}.project-action{width:31px;height:31px;display:grid;place-items:center;padding:0;border:1px solid rgba(96,165,250,.5);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.3),rgba(15,23,42,.9));color:#93c5fd;font-size:12px;font-weight:950;cursor:pointer}.project-action:hover{border-color:var(--accent);color:#fff;box-shadow:0 0 10px rgba(34,211,238,.2)}.project-action svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.project-switch label{min-width:max-content;color:#aebed0;font-size:8px;font-weight:900;letter-spacing:.08em;white-space:nowrap;word-break:keep-all}.project-switch select{width:100%;height:31px;border:1px solid rgba(148,163,184,.28);border-radius:7px;background:#080d17;color:#edf5ff;padding:0 8px;font-size:10px;outline:none}.project-switch select:focus{border-color:var(--accent)}.status{display:flex;flex:0 1 auto;flex-direction:column;align-items:flex-end;gap:2px;font-size:8px;color:var(--muted)}.status strong{max-width:260px;color:${state.error ? "#fda4af" : "#86efac"};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .workspace{display:grid;grid-template-columns:minmax(230px,252px) minmax(0,1fr);gap:8px;min-height:0;padding:8px}.panel{min-height:0;border:1px solid var(--line);border-radius:9px;background:rgba(8,13,23,.76);overflow:hidden}.tree-panel{display:flex;flex-direction:column}.panel-title{height:35px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 10px;border-bottom:1px solid var(--line);background:rgba(19,27,42,.78);color:#bed0e3;font-size:9px;font-weight:900;letter-spacing:.07em}.panel-title>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;word-break:keep-all}.panel-title b{flex:0 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--accent);font-size:8px}.tree{padding:6px;overflow:auto;scrollbar-gutter:stable}.tree-row{width:100%;min-height:30px;display:grid;grid-template-columns:13px minmax(0,1fr) auto;align-items:center;gap:5px;margin:0 0 3px;padding:5px 8px 5px calc(8px + var(--tree-depth,0) * 14px);border:1px solid transparent;border-radius:6px;background:transparent;color:#96a9bd;font-size:8px;text-align:left;cursor:pointer;transition:border-color 120ms ease,background-color 120ms ease,color 120ms ease}.tree-row i{color:#61778c;font-style:normal}.tree-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tree-row b{color:#587087}.tree-row:hover{border-color:rgba(34,211,238,.3);color:#def9ff}.tree-row.active{border-color:rgba(34,211,238,.52);background:linear-gradient(90deg,rgba(8,145,178,.2),rgba(8,145,178,.04));color:#e7fcff}.tree-row.root{min-height:35px;color:#fff;font-size:10px;font-weight:850}
      .assets-panel{display:flex;flex-direction:column}.toolbar{height:44px;display:flex;align-items:center;gap:8px;padding:7px 9px;border-bottom:1px solid var(--line)}.toolbar input{flex:1;height:30px;border:1px solid rgba(148,163,184,.25);border-radius:7px;background:#070c15;color:#edf5ff;padding:0 9px;font-size:9px;outline:none}.toolbar input:focus{border-color:var(--accent)}.filter-chip{max-width:260px;padding:5px 8px;border:1px solid rgba(244,114,182,.3);border-radius:99px;background:rgba(131,24,67,.1);color:#f8c6df;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-scroll{flex:1;min-height:0;overflow:auto;scrollbar-gutter:stable;padding:9px}.asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}.asset-card{display:grid;grid-template-columns:112px minmax(0,1fr);gap:10px;min-height:152px;padding:9px;border:1px solid rgba(148,163,184,.16);border-radius:9px;background:linear-gradient(145deg,rgba(19,27,42,.86),rgba(9,14,24,.82));cursor:pointer;outline:none;transition:border-color 120ms ease,box-shadow 120ms ease,background-color 120ms ease,opacity 120ms ease}.asset-card:hover{border-color:rgba(34,211,238,.34)}.asset-card:focus-visible{box-shadow:0 0 0 2px rgba(34,211,238,.45)}.asset-card.selected{border-color:var(--asset-selection);box-shadow:inset 0 0 0 .3px rgba(244,114,182,.45),0 0 15px rgba(244,114,182,.34),0 0 4px rgba(217,70,239,.55)}.asset-card.selection-blocked{opacity:.58}.asset-card.unregistered{cursor:default}.asset-card.unregistered .asset-state{color:#f3a8ce}.asset-thumb{position:relative;width:112px;height:132px;display:grid;grid-template-rows:2fr 1fr;overflow:hidden;border:1px solid rgba(148,163,184,.2);border-radius:7px;background:#050910;color:#648198;font-size:9px;font-weight:900}.asset-thumb-media{position:relative;display:grid;place-items:center;min-height:0;overflow:hidden;border-bottom:1px solid rgba(148,163,184,.18)}.asset-thumb-media img{width:100%;height:100%;object-fit:cover}.asset-thumb-media>span{display:none}.asset-thumb.fallback .asset-thumb-media img{display:none}.asset-thumb.fallback .asset-thumb-media>span{display:block}.asset-thumb-footer{display:grid;place-items:center;min-height:0;background:linear-gradient(180deg,#080d16,#050810)}.asset-format{display:block;color:#8198ad;font-size:8px;letter-spacing:.08em}.asset-add{min-width:56px;height:25px;padding:0 13px;border:1px solid rgba(244,114,182,.7);border-radius:99px;background:rgba(131,24,67,.26);color:#ffd5eb;font-size:9px;font-weight:950;letter-spacing:.04em;cursor:pointer;box-shadow:0 0 10px rgba(244,114,182,.16)}.asset-add:hover{border-color:#f9a8d4;background:rgba(190,24,93,.32);box-shadow:0 0 13px rgba(244,114,182,.3)}.asset-content{display:flex;flex-direction:column;gap:8px}.asset-title{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.asset-title-copy{display:flex;flex:1;flex-direction:column;gap:2px;min-width:0}.asset-state{color:var(--accent);font-size:7px;font-weight:900}.asset-title-copy>b{font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-id-line{display:flex;align-items:center;gap:5px;min-width:0;color:#9bacc0;font-size:7px;font-weight:500}.asset-id-line em{flex:0 0 auto;color:#6e859c;font-size:6px;font-style:normal;font-weight:900;letter-spacing:.05em}.asset-id-line span{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-meta{display:flex;flex-direction:column;gap:3px;color:#71879c;font-size:7px}.asset-meta b,.asset-meta span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.asset-meta b{color:#bcd0e2}.empty{grid-column:1/-1;padding:30px;border:1px dashed rgba(148,163,184,.2);border-radius:8px;color:#667e94;font-size:9px;text-align:center}.warnings{max-height:64px;overflow:auto;padding:6px 9px;border-top:1px solid rgba(251,191,36,.2);background:rgba(120,53,15,.1);color:#fcd34d;font-size:7px}
      .toolbar-status{flex:0 0 190px;width:190px;min-width:190px;height:30px;display:flex;align-items:center;justify-content:flex-end;overflow:hidden;color:var(--muted);font-size:8px}.toolbar-status strong{display:block;width:100%;color:${state.error ? "#fda4af" : "#86efac"};font-variant-numeric:tabular-nums;letter-spacing:-.02em;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.toolbar .filter-chip{flex:0 0 120px;width:120px;max-width:120px;text-align:center}
      .asset-view-toggle{flex:0 0 31px;width:31px;height:30px;display:grid;place-items:center;padding:0;border:1px solid rgba(96,165,250,.46);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.2),rgba(15,23,42,.88));color:#7dd3fc;cursor:pointer}.asset-view-toggle:hover,.asset-view-toggle:focus-visible,.asset-view-toggle[aria-pressed="true"]{border-color:var(--accent);background:linear-gradient(180deg,rgba(37,99,235,.38),rgba(15,23,42,.94));color:#e0f2fe;outline:none;box-shadow:0 0 10px rgba(34,211,238,.2)}.asset-view-toggle svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
      .hmb-image-assets .asset-card{min-height:167px;padding:10px}.hmb-image-assets .asset-thumb{width:123px;height:145px}.hmb-image-assets .asset-add{min-width:62px;height:28px;padding:0 14px;font-size:10px}.hmb-image-assets .asset-format{font-size:9px}.hmb-image-assets[data-asset-view="image"] .asset-grid{grid-template-columns:repeat(auto-fill,145px);align-content:start;justify-content:start;gap:9px}.hmb-image-assets[data-asset-view="image"] .asset-card{width:145px;grid-template-columns:123px;gap:0}.hmb-image-assets[data-asset-view="image"] .asset-content{display:none}.hmb-image-assets[data-asset-view="detail"] .asset-grid{grid-template-columns:repeat(auto-fill,286px);align-content:start;justify-content:start;gap:9px}.hmb-image-assets[data-asset-view="detail"] .asset-card{width:286px;grid-template-columns:123px minmax(0,1fr);gap:11px}.hmb-image-assets[data-asset-view="detail"] .asset-content{display:flex}
      .tray{margin:0 8px 8px;border:1px solid rgba(244,114,182,.34);border-radius:10px;background:linear-gradient(180deg,rgba(30,14,30,.9),rgba(8,11,19,.96));overflow:hidden}.tray-head{height:34px;display:flex;align-items:center;gap:9px;padding:0 10px;border-bottom:1px solid rgba(244,114,182,.2)}.tray-head b{font-size:9px;letter-spacing:.07em;color:#f9c2df}.tray-head span{color:#8ea3b8;font-size:7px}.tray-head em{margin-left:auto;color:var(--asset-selection);font-size:7px;font-style:normal}.tray-scroll{height:132px;display:flex;align-items:stretch;gap:8px;overflow-x:auto;overflow-y:hidden;padding:7px}.selected-card{position:relative;flex:0 0 244.5px;display:grid;grid-template-rows:25px minmax(0,1fr);padding:6px;border:1px solid rgba(244,114,182,.25);border-radius:8px;background:linear-gradient(145deg,rgba(61,23,49,.6),rgba(12,17,28,.94));cursor:grab}.selected-card.dragging{opacity:.35}.selected-card.drop-target{border-color:var(--accent);box-shadow:0 0 0 1px rgba(34,211,238,.28)}.selected-card.missing{border-color:rgba(248,113,113,.5)}.selected-card-top{display:flex;align-items:center;gap:7px}.slot{min-width:30px;height:21px;display:grid;place-items:center;border:1px solid rgba(96,165,250,.68);border-radius:5px;background:rgba(37,99,235,.24);color:#93c5fd;font-size:10px;font-weight:950}.drag-handle{color:#7f7184;font-size:10px}.selected-actions{display:flex;gap:3px;margin-left:auto}.selected-actions button{width:23px;height:21px;border:1px solid rgba(148,163,184,.2);border-radius:5px;background:#0a101b;color:#b9cad9;cursor:pointer}.selected-actions button:hover{border-color:var(--accent);color:#fff}.selected-actions button:disabled{opacity:.25;cursor:default}.selected-card-body{display:grid;grid-template-columns:102px minmax(0,1fr);align-items:center;gap:9px}.selected-thumb{position:relative;width:102px;height:82px;display:grid;place-items:center;overflow:hidden;border:1px solid rgba(244,114,182,.25);border-radius:6px;background:#060912;color:#725a70;font-size:7px;font-weight:900}.selected-thumb img{width:100%;height:100%;object-fit:cover}.selected-thumb span{display:none}.selected-thumb.fallback span{display:block}.selected-copy{display:flex;flex-direction:column;gap:4px}.selected-copy b,.selected-copy span,.selected-copy small{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.selected-copy b{font-size:10px}.selected-copy span{color:#a7b7c8;font-size:8px}.selected-copy em{color:#f3a8ce;font-size:7px;font-style:normal;font-weight:900}.selected-copy small{color:#667e94;font-size:7px}.tray-empty{min-width:100%;display:grid;place-items:center;border:1px dashed rgba(244,114,182,.18);border-radius:7px;color:#765d70;font-size:9px}
      .selected-card{flex-basis:120px;width:120px;height:118px;grid-template-rows:23px minmax(0,1fr)}.selected-card-top{gap:4px}.slot{flex:0 0 28px;width:28px;min-width:28px;height:21px;font-size:9px;font-variant-numeric:tabular-nums}.selected-actions{display:grid;grid-template-columns:repeat(3,22px);gap:2px;margin-left:auto}.selected-actions button{width:22px;height:21px;padding:0;display:grid;place-items:center}.selected-card-body{display:grid;grid-template-columns:1fr;place-items:center;gap:0;min-height:0}.selected-thumb{width:106px;height:81px}.selected-copy{display:none}
      .asset-registration-backdrop{position:absolute;inset:0;z-index:80;display:grid;place-items:center;padding:18px;background:rgba(1,4,10,.78);backdrop-filter:blur(5px)}.asset-passport{width:min(390px,100%);max-height:calc(100% - 12px);display:flex;flex-direction:column;overflow:auto;border:1px solid rgba(244,114,182,.62);border-radius:18px 18px 28px 28px;background:radial-gradient(circle at 50% -8%,rgba(190,24,93,.24),transparent 30%),linear-gradient(180deg,#171020,#090d17 45%,#060912);box-shadow:0 24px 70px rgba(0,0,0,.62),0 0 28px rgba(244,114,182,.2)}.passport-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 10px;border-bottom:1px solid rgba(244,114,182,.2)}.passport-head small{display:block;color:#d8a2be;font-size:7px;font-weight:900;letter-spacing:.18em}.passport-head h2{margin:3px 0 0;color:#fff1f8;font-size:15px;letter-spacing:.08em}.passport-head button{width:28px;height:28px;border:1px solid rgba(244,114,182,.25);border-radius:50%;background:#0b0d16;color:#e7b9d1;font-size:18px;line-height:1;cursor:pointer}.passport-photo{position:relative;width:128px;aspect-ratio:3/4;display:grid;place-items:center;align-self:center;margin:14px 0 8px;overflow:hidden;border:1px solid rgba(244,114,182,.38);border-radius:8px;background:#050910;color:#84677a;font-size:10px;font-weight:900;box-shadow:0 0 18px rgba(244,114,182,.12)}.passport-photo img{width:100%;height:100%;object-fit:cover}.passport-photo>span{display:none}.passport-photo.fallback img{display:none}.passport-photo.fallback>span{display:block}.passport-file{display:flex;flex-direction:column;gap:3px;padding:0 18px 12px;text-align:center}.passport-file b,.passport-file span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.passport-file b{color:#d7e2ef;font-size:8px}.passport-file span{color:#73899d;font-size:7px}.passport-fields{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:12px 16px;border-top:1px dashed rgba(244,114,182,.24)}.passport-fields label{display:flex;flex-direction:column;gap:4px}.passport-fields label:nth-last-child(1){grid-column:1/-1}.passport-fields label span{color:#bb8fa8;font-size:7px;font-weight:900;letter-spacing:.06em}.passport-fields input,.passport-fields select{width:100%;height:32px;border:1px solid rgba(148,163,184,.27);border-radius:7px;background:#060b13;color:#eef5ff;padding:0 8px;font-size:9px;outline:none}.passport-fields input:focus,.passport-fields select:focus{border-color:var(--asset-selection);box-shadow:0 0 0 1px rgba(244,114,182,.18)}.passport-fields select:disabled{opacity:.42}.passport-actions{display:flex;justify-content:flex-end;gap:7px;padding:11px 16px 15px}.passport-actions button{height:31px;padding:0 13px;border:1px solid rgba(148,163,184,.24);border-radius:7px;background:#0a101a;color:#bac9d8;font-size:8px;font-weight:900;cursor:pointer}.passport-actions .passport-register{border-color:rgba(244,114,182,.62);background:linear-gradient(180deg,rgba(190,24,93,.55),rgba(88,28,135,.42));color:#ffe4f2;box-shadow:0 0 12px rgba(244,114,182,.18)}.passport-actions button:disabled{opacity:.32;cursor:default;box-shadow:none}
      .passport-fields .passport-folder{grid-column:1/-1}
      /* P/T share one polished visual language; only the accent family changes. */
      .hmb-image-assets[data-theme] .top{background:linear-gradient(90deg,var(--header-tint),rgba(14,23,38,.92) 44%,rgba(6,9,18,.96))}.hmb-image-assets[data-theme] .mark{border-color:rgba(var(--selection-rgb),.54);background:linear-gradient(145deg,rgba(var(--selection-rgb),.16),rgba(8,13,23,.86));color:var(--accent);box-shadow:inset 0 0 0 1px rgba(255,255,255,.025),0 0 14px rgba(var(--selection-rgb),.11)}
      .hmb-image-assets[data-theme] .filter-chip{border-color:rgba(var(--selection-rgb),.3);background:rgba(var(--selection-deep-rgb),.1);color:var(--selection-text)}.hmb-image-assets[data-theme] .asset-card.selected{box-shadow:inset 0 0 0 .3px rgba(var(--selection-rgb),.45),0 0 15px rgba(var(--selection-rgb),.34),0 0 4px rgba(var(--selection-secondary-rgb),.55)}.hmb-image-assets[data-theme] .asset-card.unregistered .asset-state{color:var(--selection-soft)}.hmb-image-assets[data-theme] .asset-add{border-color:rgba(var(--selection-rgb),.7);background:rgba(var(--selection-deep-rgb),.26);color:var(--selection-strong);box-shadow:0 0 10px rgba(var(--selection-rgb),.16)}.hmb-image-assets[data-theme] .asset-add:hover{border-color:var(--selection-soft);background:rgba(var(--selection-deep-rgb),.34);box-shadow:0 0 13px rgba(var(--selection-rgb),.3)}
      .hmb-image-assets[data-theme] .tray{border-color:rgba(var(--selection-rgb),.34);background:linear-gradient(180deg,var(--selection-panel),rgba(8,11,19,.96))}.hmb-image-assets[data-theme] .tray-head{border-bottom-color:rgba(var(--selection-rgb),.2)}.hmb-image-assets[data-theme] .tray-head b{color:var(--selection-text)}.hmb-image-assets[data-theme] .selected-card{border-color:rgba(var(--selection-rgb),.25);background:linear-gradient(145deg,var(--selection-card),rgba(12,17,28,.94))}.hmb-image-assets[data-theme] .selected-thumb{border-color:rgba(var(--selection-rgb),.25)}.hmb-image-assets[data-theme] .selected-copy em{color:var(--selection-soft)}.hmb-image-assets[data-theme] .tray-empty{border-color:rgba(var(--selection-rgb),.18);color:rgba(var(--selection-rgb),.48)}
      .hmb-image-assets[data-theme] .asset-passport{border-color:rgba(var(--selection-rgb),.62);background:radial-gradient(circle at 50% -8%,rgba(var(--selection-deep-rgb),.24),transparent 30%),linear-gradient(180deg,#111827,#090d17 45%,#060912);box-shadow:0 24px 70px rgba(0,0,0,.62),0 0 28px rgba(var(--selection-rgb),.2)}.hmb-image-assets[data-theme] .passport-head{border-bottom-color:rgba(var(--selection-rgb),.2)}.hmb-image-assets[data-theme] .passport-head small,.hmb-image-assets[data-theme] .passport-fields label span{color:var(--selection-soft)}.hmb-image-assets[data-theme] .passport-head h2{color:var(--selection-strong)}.hmb-image-assets[data-theme] .passport-head button{border-color:rgba(var(--selection-rgb),.25);color:var(--selection-text)}.hmb-image-assets[data-theme] .passport-photo{border-color:rgba(var(--selection-rgb),.38);box-shadow:0 0 18px rgba(var(--selection-rgb),.12)}.hmb-image-assets[data-theme] .passport-fields{border-top-color:rgba(var(--selection-rgb),.24)}.hmb-image-assets[data-theme] .passport-fields input:focus,.hmb-image-assets[data-theme] .passport-fields select:focus{box-shadow:0 0 0 1px rgba(var(--selection-rgb),.18)}.hmb-image-assets[data-theme] .passport-actions .passport-register{border-color:rgba(var(--selection-rgb),.62);background:linear-gradient(180deg,rgba(var(--selection-deep-rgb),.55),rgba(var(--selection-secondary-rgb),.42));color:var(--selection-strong);box-shadow:0 0 12px rgba(var(--selection-rgb),.18)}
      .project-switch{grid-template-columns:auto auto minmax(150px,260px) auto}.language-button{min-width:58px;height:31px;padding:0 11px;border:1px solid rgba(96,165,250,.5);border-radius:7px;background:linear-gradient(180deg,rgba(37,99,235,.3),rgba(15,23,42,.9));color:#93c5fd;font-size:10px;font-weight:950;cursor:pointer}.language-button:hover,.language-button:focus-visible{border-color:var(--accent);color:#fff;outline:none;box-shadow:0 0 10px rgba(34,211,238,.2)}
      @container(max-width:1100px){.status{display:none}.heading{flex-basis:170px}.heading span{display:none}.project-switch{grid-template-columns:auto auto minmax(120px,210px) auto}}
      @container(max-width:720px){.heading{display:none}.project-switch{grid-template-columns:auto minmax(120px,1fr) auto}.project-switch label{display:none}}
      @container(max-width:920px){.workspace{grid-template-columns:1fr;grid-template-rows:minmax(150px,30%) minmax(0,1fr)}.tree-panel{display:flex}.project-switch{grid-template-columns:auto minmax(130px,1fr) auto}.project-switch label{position:absolute;inline-size:1px;block-size:1px;overflow:hidden;clip-path:inset(50%)}.status{display:flex}}
    </style>
    <div class="hmb-image-assets nodrag" data-theme="${theme}" data-asset-view="${detailView ? "detail" : "image"}" tabindex="0">
      <header class="top">
        <div class="mark">IA</div>
        <div class="heading"><b>HMBImageAssetLibrary</b><span>${escapeHtml(displayWindowsPath(state.catalog_root))} → ${escapeHtml(state.project_id || imageAssetText(state, "select_a_project"))}</span></div>
        <div class="project-switch">
          <div class="project-actions">
            <button type="button" class="project-action" data-project-set aria-label="${escapeHtml(imageAssetText(state, "project_set"))}" title="${escapeHtml(imageAssetText(state, "project_set"))}">S</button>
            <button type="button" class="project-action" data-project-reload aria-label="${escapeHtml(imageAssetText(state, "reload_projects"))}" title="${escapeHtml(imageAssetText(state, "reload_projects"))}">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 9a7 7 0 0 1 11.8-2L20 9"/><path d="M17.9 15a7 7 0 0 1-11.8 2L4 15"/></svg>
            </button>
          </div>
          <label>${escapeHtml(imageAssetText(state, "project"))}</label>
          <select data-project-select>${projectOptions(state)}</select>
          <button type="button" class="language-button" data-language-toggle aria-label="${escapeHtml(imageAssetText(state, "language"))}">${imageAssetLanguage(state) === "ko" ? "한국어" : "EN"}</button>
        </div>
      </header>
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
          <div class="asset-scroll">
            <div class="asset-grid">${assets.map((asset) => renderAssetCard(asset, selected.length, state.search, state)).join("")}<div class="empty" data-search-empty ${visibleAssets.length ? "hidden" : ""}>${escapeHtml(imageAssetText(state, "no_match"))}</div></div>
          </div>
          ${state.warnings.length ? `<div class="warnings">${state.warnings.map((item) => `<div>${escapeHtml(item)}</div>`).join("")}</div>` : ""}
        </section>
      </main>
      <section class="tray">
        <div class="tray-head"><b>${escapeHtml(imageAssetText(state, "selected_images"))}</b><span>${escapeHtml(imageAssetText(state, "drag_hint"))}</span><em>${selected.length}/${MAX_SELECTED_IMAGES}</em></div>
        <div class="tray-scroll">${selected.map((asset, index) => renderSelectedCard(asset, index, selected, state)).join("") || `<div class="tray-empty">${escapeHtml(imageAssetText(state, "tray_empty"))}</div>`}</div>
      </section>
      ${renderRegistrationDialog(state, registrationDraft)}
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
  const stopInteriorNodeSelection = (event) => event.stopPropagation();
  on(container, "pointerdown", stopInteriorNodeSelection);
  const assetsByLibraryId = new Map(
    state.assets.map((asset) => [clean(asset.asset_library_id), asset]),
  );

  const projectSelect = container.querySelector("[data-project-select]");
  on(projectSelect, "change", () => {
    const path = clean(projectSelect.value).replaceAll("\\", "/");
    if (!path || path === state.project_root) return;
    state.project_root = path;
    state.project_id = "";
    state.project_uid = "";
    state.selected_folder_path = "";
    state.expanded_folders = [ROOT_FOLDER_KEY];
    state.selected_main_type = "";
    state.selected_sub_type = "";
    state.selected_source_view = "project";
    state = emit(props, state, container);
    remount(state);
  });

  on(container.querySelector("[data-language-toggle]"), "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
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
    state.refresh_revision = Math.max(0, Number(state.refresh_revision) || 0) + 1;
    state = emit(props, state, container);
    remount(state);
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
    state = emit(props, state, container);
    remount(state);
  };
  on(container, "click", onTreeClick);

  const search = container.querySelector("[data-search]");
  on(search, "input", () => {
    state.search = String(search.value || "").slice(0, 256);
    container.__hmbImageAssetSearchDraft = state.search;
    applyAssetSearchFilter(container, state.search);
  });
  const commitSearch = () => {
    state.search = String(search?.value || "").slice(0, 256);
    state = emit(props, state, container);
    delete container.__hmbImageAssetSearchDraft;
  };
  on(search, "change", commitSearch);

  container.querySelectorAll("[data-asset-key]").forEach((card) => {
    const key = clean(card.getAttribute("data-asset-key"));
    const asset = assetsByLibraryId.get(key);
    if (!asset) return;
    on(card.querySelector("[data-asset-add]"), "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const externalImport = asset.source_kind === "user" && Number(asset.import_index || 0) > 0;
      if (asset.registered || (asset.source_kind !== "project" && !externalImport)) return;
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
      const selected = selectedAssets(state);
      if (!asset.selected && selected.length >= MAX_SELECTED_IMAGES) return;
      // A visible newer click owns transport recovery immediately, even before
      // its two-frame publication. An older Promise rejection cannot roll it back.
      hmbInvalidateImageAssetPublication(container);
      if (!container.__hmbImageAssetSelectionCommitPending) {
        container.__hmbImageAssetSelectionBase = hmbImageAssetSelectionSnapshot(state);
        container.__hmbImageAssetSelectionBaseAuthority = imageAssetAuthorityStamp(state);
        container.__hmbImageAssetSelectionBasePropValue = props?.value;
      }
      asset.selected = !asset.selected;
      asset.selection_order = asset.selected
        ? Math.max(0, ...selected.map((item) => item.selection_order)) + 1
        : 0;
      const nextSelected = asset.selected
        ? [...selected, asset]
        : selected.filter((item) => item !== asset);
      nextSelected.forEach((item, index) => {
        item.selection_order = index + 1;
      });
      hmbApplyImageAssetSelectionFeedback(container, state, {
        assetsByLibraryId,
        changedAsset: asset,
        changedCard: card,
        previousSelectedCount: selected.length,
        selectedAssets: nextSelected,
      });
      hmbScheduleImageAssetSelectionCommit(container, () => {
        const pending = container.__hmbImageAssetPendingAuthoritativeProps;
        const baseSelection = container.__hmbImageAssetSelectionBase || [];
        const baseAuthority = Number(container.__hmbImageAssetSelectionBaseAuthority) || 0;
        delete container.__hmbImageAssetPendingAuthoritativeProps;
        delete container.__hmbImageAssetSelectionBase;
        delete container.__hmbImageAssetSelectionBaseAuthority;
        delete container.__hmbImageAssetSelectionBasePropValue;
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
            remount(rollbackState);
          } else if (imageAssetAuthorityStamp(state) === baseAuthority) {
            hmbRestoreImageAssetSelectionSnapshot(state, baseSelection);
            remount(state);
          }
        }, { suppressMatchingEcho: true });
      });
    };
    on(card, "click", (event) => {
      if (event.target?.closest?.("input,button,select,textarea,a")) return;
      toggle();
    });
    on(card, "keydown", (event) => {
      if (!["Enter", " "].includes(event.key) || event.target !== card) return;
      event.preventDefault();
      toggle();
    });
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
  on(registrationBackdrop, "click", (event) => {
    if (event.target === registrationBackdrop) closeRegistration();
  });
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
    draft.source_type = clean(registrationMain.value);
    if (draft.source_type !== "Custom") draft.custom_source_type = "";
    const choices = hmbImageAssetRegistrationSubTypes(state.taxonomy, draft.source_type);
    if (!choices.includes(draft.scope_candidate)) draft.scope_candidate = "";
    remount(state);
  });
  const registrationSub = container.querySelector("[data-registration-sub]");
  on(registrationSub, "change", () => {
    const draft = container.__hmbImageAssetRegistrationDraft;
    if (!draft) return;
    draft.scope_candidate = clean(registrationSub.value);
    updateRegistrationSubmit();
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
      source_type: clean(draft.source_type),
      custom_source_type: clean(draft.custom_source_type),
      scope_candidate: clean(draft.scope_candidate),
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
  }, true);

  let draggedKey = "";
  const selectedTray = container.querySelector(".tray-scroll");
  const selectedCardForEvent = (event) => {
    const card = event.target?.closest?.("[data-selected-key]");
    return card && selectedTray?.contains?.(card) ? card : null;
  };
  on(selectedTray, "dragstart", (event) => {
    const card = selectedCardForEvent(event);
    if (!card) return;
    const key = clean(card.getAttribute("data-selected-key"));
    draggedKey = key;
    container.__hmbImageAssetDragging = true;
    card.classList.add("dragging");
    try {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", key);
    } catch (_error) {}
  });
  on(selectedTray, "dragend", () => {
    draggedKey = "";
    container.__hmbImageAssetDragging = false;
    selectedTray?.querySelectorAll?.("[data-selected-key]").forEach((item) => {
      item.classList.remove("dragging", "drop-target");
    });
  });
  on(selectedTray, "dragover", (event) => {
    const card = selectedCardForEvent(event);
    if (!card) return;
    event.preventDefault();
    const key = clean(card.getAttribute("data-selected-key"));
    if (draggedKey && draggedKey !== key) card.classList.add("drop-target");
  });
  on(selectedTray, "dragleave", (event) => {
    selectedCardForEvent(event)?.classList?.remove("drop-target");
  });
  on(selectedTray, "drop", (event) => {
    const card = selectedCardForEvent(event);
    if (!card) return;
    event.preventDefault();
    container.__hmbImageAssetDragging = false;
    card.classList.remove("drop-target");
    const key = clean(card.getAttribute("data-selected-key"));
    const sourceKey = draggedKey || clean(event.dataTransfer?.getData?.("text/plain"));
    if (!sourceKey || sourceKey === key || !hmbMoveSelectedAsset(state, sourceKey, key)) return;
    state = emit(props, state, container);
    remount(state);
  });
  on(selectedTray, "click", (event) => {
    const action = event.target?.closest?.("[data-remove-selected],[data-move]");
    const card = selectedCardForEvent(event);
    if (!action || !card) return;
    event.preventDefault();
    event.stopPropagation();
    const key = clean(card.getAttribute("data-selected-key"));
    const asset = assetsByLibraryId.get(key);
    if (!asset) return;
    if (action.matches?.("[data-remove-selected]")) {
      const externalImport = asset.source_kind === "user" && Number(asset.import_index || 0) > 0;
      if (externalImport) {
        if (state.disconnect_import_uid) return;
        state.disconnect_import_uid = asset.source_uid;
        state.error = "";
        state = emit(props, state, container);
        remount(state);
        return;
      }
      asset.selected = false;
      asset.selection_order = 0;
      compactSelectionOrder(state.assets);
      state = emit(props, state, container);
      remount(state);
      return;
    }
    const direction = Number.parseInt(action.getAttribute("data-move") || "0", 10);
    const ordered = selectedAssets(state);
    const index = ordered.findIndex((item) => item.asset_library_id === key);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    ordered.forEach((item, order) => {
      item.selection_order = order + 1;
    });
    state = emit(props, state, container);
    remount(state);
  });

  const syncNativeRoot = () => {
    const nativePath = clean(nativeProjectRootValue(container)).replaceAll("\\", "/");
    if (!nativePath || nativePath.toLowerCase() === state.catalog_root.toLowerCase()) return;
    state.catalog_root = nativePath;
    state = emit(props, state, container);
    remount(state);
  };
  const nodeRoot = findNodeRoot(container);
  on(nodeRoot, "change", syncNativeRoot);
  on(nodeRoot, "input", syncNativeRoot);
  if (typeof window !== "undefined") on(window, "focus", syncNativeRoot);
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
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  let state = normalizeState(props?.value);
  let listeners = [];
  let autoSyncTimer = null;
  let autoSyncPendingUntil = 0;
  let autoSyncRequestSequence = 0;
  let autoSyncActiveRequest = 0;
  let disposed = false;
  let renderRevision = 0;
  const autoSyncListeners = [];

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
    const uiMemory = captureImageAssetUi(container, state);
    const reusableImages = detachReusableImageAssets(container);
    container.__hmbImageAssetDragging = false;
    clearListeners();
    state = normalizeState(nextState);
    if (typeof container.__hmbImageAssetSearchDraft === "string") {
      state.search = container.__hmbImageAssetSearchDraft.slice(0, 256);
    }
    container.innerHTML = hmbScopeWidgetStyleMarkup(render(
      state,
      container.__hmbImageAssetRegistrationDraft || null,
    ), ".hmb-image-assets");
    if (container.__hmbImageAssetRegistrationDraft) {
      const root = container.querySelector(".hmb-image-assets");
      Array.from(root?.children || []).forEach((element) => {
        if (element.hasAttribute?.("data-registration-backdrop")) return;
        element.setAttribute?.("inert", "");
        element.setAttribute?.("aria-hidden", "true");
      });
    }
    hmbPrepareImageAssetCanvasGestures(container);
    restoreReusableImageAssets(container, reusableImages);
    concealNativeProjectRootPicker(container);
    installEvents(container, state, props, remount, listeners);
    restoreImageAssetUi(container, state, uiMemory);
    return state;
  };

  const applyProps = (nextProps = {}) => {
    if (hmbConsumeImageAssetStateEcho(container, nextProps)) {
      props = nextProps || {};
      return;
    }
    if (container.__hmbImageAssetSelectionCommitPending) {
      // Preserve the latest authoritative snapshot and merge only the local
      // selection delta into it when the optimistic click is published.
      autoSyncPendingUntil = 0;
      props = nextProps || {};
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
      autoSyncRequestSequence += 1;
      autoSyncActiveRequest = 0;
      const nextState = normalizeState(nextProps?.value);
      container.__hmbImageAssetPendingAuthoritativeProps = {
        state: nextState,
      };
      return;
    }
    const previousPropValue = props?.value;
    props = nextProps || {};
    if (nextProps?.value === previousPropValue) return;
    hmbInvalidateImageAssetPublication(container);
    autoSyncRequestSequence += 1;
    autoSyncActiveRequest = 0;
    const nextState = normalizeState(nextProps?.value);
    const currentValue = JSON.stringify(state);
    const nextValue = JSON.stringify(nextState);
    autoSyncPendingUntil = 0;
    if (currentValue === nextValue) return;
    if (hmbDeferImageAssetPropsDuringRegistration(container, props)) return;
    remount(nextState);
  };
  container.__hmbImageAssetApplyProps = applyProps;

  const clearAutoSyncTimer = () => {
    if (autoSyncTimer !== null && typeof clearTimeout === "function") {
      clearTimeout(autoSyncTimer);
    }
    autoSyncTimer = null;
  };
  const scheduleAutoSync = (delay = null) => {
    clearAutoSyncTimer();
    if (disposed || typeof setTimeout !== "function") return;
    const jitter = Math.floor(Math.random() * (IMAGE_ASSET_AUTO_SYNC_JITTER_MS + 1));
    autoSyncTimer = setTimeout(
      runAutoSync,
      delay === null ? IMAGE_ASSET_AUTO_SYNC_MS + jitter : Math.max(0, delay),
    );
  };
  const canAutoSync = () => Boolean(
    state.project_root
    && !(typeof document !== "undefined" && document.hidden)
    && !(typeof navigator !== "undefined" && navigator.onLine === false)
    && !container.__hmbImageAssetRegistrationDraft
    && !container.__hmbImageAssetDragging
    && !container.__hmbImageAssetSelectionCommitPending
  );
  function runAutoSync() {
    autoSyncTimer = null;
    const now = Date.now();
    let nextDelay = null;
    try {
      if (
        !disposed
        && canAutoSync()
        && now >= autoSyncPendingUntil
        && typeof props?.onChange === "function"
      ) {
        const nonce = `manifest-poll-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        const requestToken = ++autoSyncRequestSequence;
        autoSyncActiveRequest = requestToken;
        autoSyncPendingUntil = now + IMAGE_ASSET_AUTO_SYNC_PENDING_MS;
        const settle = (error = null) => {
          if (disposed || autoSyncActiveRequest !== requestToken) return false;
          autoSyncActiveRequest = 0;
          if (error) {
            autoSyncPendingUntil = Date.now() + 1000;
            container.__hmbImageAssetAutoSyncError = String(error?.message || error);
            scheduleAutoSync(1000);
          } else {
            autoSyncPendingUntil = 0;
            delete container.__hmbImageAssetAutoSyncError;
          }
          return true;
        };
        try {
          const result = props.onChange(hmbImageAssetAutoSyncPayload(state, nonce));
          if (result && typeof result.then === "function") {
            Promise.resolve(result).then(
              () => settle(),
              (error) => settle(error),
            );
          } else {
            settle();
          }
        } catch (error) {
          if (autoSyncActiveRequest === requestToken) {
            autoSyncActiveRequest = 0;
            autoSyncPendingUntil = Date.now() + 1000;
            container.__hmbImageAssetAutoSyncError = String(error?.message || error);
            nextDelay = 1000;
          }
        }
      }
    } finally {
      // A transport exception must never terminate the polling loop.
      scheduleAutoSync(nextDelay);
    }
  }
  const wakeAutoSync = () => {
    if (canAutoSync()) scheduleAutoSync(250);
    else scheduleAutoSync();
  };
  const onAutoSync = (target, type, handler) => {
    if (!target?.addEventListener) return;
    target.addEventListener(type, handler);
    autoSyncListeners.push([target, type, handler]);
  };
  if (typeof document !== "undefined") {
    onAutoSync(document, "visibilitychange", wakeAutoSync);
  }
  if (typeof window !== "undefined") {
    onAutoSync(window, "online", wakeAutoSync);
    onAutoSync(window, "offline", wakeAutoSync);
  }

  const onTheme = (event) => {
    const root = container.querySelector(".hmb-image-assets");
    if (root) root.dataset.theme = normalizeTheme(event?.detail?.theme);
  };
  if (typeof window !== "undefined") {
    window.addEventListener(HMB_UI_THEME_EVENT, onTheme);
  }

  const cleanup = () => {
    hmbInvalidateImageAssetPublication(container);
    autoSyncRequestSequence += 1;
    autoSyncActiveRequest = 0;
    try { hmbFlushImageAssetSelectionCommit(container); } catch (_error) {
      hmbCancelImageAssetSelectionCommit(container);
    }
    // The flush can start a fresh asynchronous publication.  Teardown owns a
    // later token so its eventual rejection cannot repaint disposed DOM.
    hmbInvalidateImageAssetPublication(container);
    hmbForgetImageAssetStateEcho(container);
    disposed = true;
    autoSyncPendingUntil = 0;
    clearAutoSyncTimer();
    autoSyncListeners.forEach(([target, type, handler]) => {
      try {
        target.removeEventListener(type, handler);
      } catch (_error) {}
    });
    autoSyncListeners.length = 0;
    clearListeners();
    if (typeof window !== "undefined") {
      window.removeEventListener(HMB_UI_THEME_EVENT, onTheme);
    }
    if (container.__hmbImageAssetCleanup === cleanup) {
      delete container.__hmbImageAssetCleanup;
    }
    if (container.__hmbImageAssetApplyProps === applyProps) {
      delete container.__hmbImageAssetApplyProps;
    }
    delete container.__hmbImageAssetDragging;
    delete container.__hmbImageAssetRegistrationDraft;
    delete container.__hmbImageAssetRegistrationReturnFocus;
    delete container.__hmbImageAssetDeferredProps;
    delete container.__hmbImageAssetSelectionCommitPending;
    delete container.__hmbImageAssetSelectionCommitRunning;
    delete container.__hmbImageAssetSelectionCommitJob;
    delete container.__hmbImageAssetSelectionBase;
    delete container.__hmbImageAssetSelectionBaseAuthority;
    delete container.__hmbImageAssetSelectionBasePropValue;
    delete container.__hmbImageAssetPendingAuthoritativeProps;
    delete container.__hmbImageAssetAutoSyncError;
    if (Number(container.__hmbImageAssetMountToken) === mountToken) {
      delete container.__hmbImageAssetMountToken;
    }
    container.removeAttribute?.("data-hmb-node-delete-protected");
    container.innerHTML = "";
  };
  container.__hmbImageAssetCleanup = cleanup;
  remount(state);
  scheduleAutoSync();
  return {
    cleanup: container.__hmbImageAssetCleanupProxy,
    update(nextProps) {
      applyProps(nextProps || {});
    },
  };
}
